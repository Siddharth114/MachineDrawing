import cv2
import numpy as np
import time
import matplotlib.pyplot as plt
import string
import random
from IPython.display import clear_output

class GeneticDrawing:
    def __init__(self, img_path, seed=0, brushesRange=[[0.1, 0.3], [0.3, 0.7]]):
        self.original_img = cv2.imread(img_path)
        self.img_grey = cv2.cvtColor(self.original_img,cv2.COLOR_BGR2GRAY)
        self.img_grads = self._imgGradient(self.img_grey)
        self.myDNA = None
        self.seed = seed
        self.brushesRange = brushesRange
        self.sampling_mask = None
        
        
        self.imgBuffer = [np.zeros((self.img_grey.shape[0], self.img_grey.shape[1]), np.uint8)]
        
    def generate(self, stages=10, generations=100, brushstrokesCount=10, show_progress_imgs=True):
        for s in range(stages):
            
            if self.sampling_mask is not None:
                sampling_mask = self.sampling_mask
            else:
                sampling_mask = self.create_sampling_mask(s, stages)
            self.myDNA = DNA(self.img_grey.shape, 
                             self.img_grads, 
                             self.calcBrushRange(s, stages), 
                             canvas=self.imgBuffer[-1], 
                             sampling_mask=sampling_mask)
            self.myDNA.initRandom(self.img_grey, brushstrokesCount, self.seed + time.time() + s)
            
            for g in range(generations):
                self.myDNA.evolveDNASeq(self.img_grey, self.seed + time.time() + g)
                clear_output(wait=True)
                print("Stage ", s+1, ". Generation ", g+1, "/", generations)
                if show_progress_imgs is True:
                    
                    plt.imshow(self.myDNA.get_cached_image(), cmap='gray')
                    plt.show()
            self.imgBuffer.append(self.myDNA.get_cached_image())
        return self.myDNA.get_cached_image()
    
    def calcBrushRange(self, stage, total_stages):
        return [self._calcBrushSize(self.brushesRange[0], stage, total_stages), self._calcBrushSize(self.brushesRange[1], stage, total_stages)]
        
    def set_brush_range(self, ranges):
        self.brushesRange = ranges
        
    def set_sampling_mask(self, img_path):
        self.sampling_mask = cv2.cvtColor(cv2.imread(img_path),cv2.COLOR_BGR2GRAY)
        
    def create_sampling_mask(self, s, stages):
        percent = 0.2
        start_stage = int(stages*percent)
        sampling_mask = None
        if s >= start_stage:
            t = (1.0 - (s-start_stage)/max(stages-start_stage-1,1)) * 0.25 + 0.005
            sampling_mask = self.calc_sampling_mask(t)
        return sampling_mask
        
    '''
    we'd like to "guide" the brushtrokes along the image gradient direction, if such direction has large magnitude
    in places of low magnitude, we allow for more deviation from the direction. 
    this function precalculates angles and their magnitudes for later use inside DNA class
    '''
    def _imgGradient(self, img):
        
        img = np.float32(img) / 255.0 
        
        gx = cv2.Sobel(img, cv2.CV_32F, 1, 0, ksize=1)
        gy = cv2.Sobel(img, cv2.CV_32F, 0, 1, ksize=1)
        
        mag, angle = cv2.cartToPolar(gx, gy, angleInDegrees=True)
        
        mag /= np.max(mag)
        
        mag = np.power(mag, 0.3)
        return mag, angle
    
    def calc_sampling_mask(self, blur_percent):
        img = np.copy(self.img_grey)
        
        gx = cv2.Sobel(img, cv2.CV_32F, 1, 0, ksize=1)
        gy = cv2.Sobel(img, cv2.CV_32F, 0, 1, ksize=1)
        
        mag, angle = cv2.cartToPolar(gx, gy, angleInDegrees=True)
        
        w = img.shape[0] * blur_percent
        if w > 1:
            mag = cv2.GaussianBlur(mag,(0,0), w, cv2.BORDER_DEFAULT)
        
        scale = 255.0/mag.max()
        return mag*scale
        
    
    def _calcBrushSize(self, brange, stage, total_stages):
        bmin = brange[0]
        bmax = brange[1]
        t = stage/max(total_stages-1, 1)
        return (bmax-bmin)*(-t*t+1)+bmin


def util_sample_from_img(img):
    
    pos = np.indices(dimensions=img.shape)
    pos = pos.reshape(2, pos.shape[1]*pos.shape[2])
    img_flat = np.clip(img.flatten() / img.flatten().sum(), 0.0, 1.0)
    return pos[:, np.random.choice(np.arange(pos.shape[1]), 1, p=img_flat)]

class DNA:

    def __init__(self, bound, img_gradient, brushstrokes_range, canvas=None, sampling_mask=None):
        self.DNASeq = []
        self.bound = bound
        
        
        self.minSize = brushstrokes_range[0] 
        self.maxSize = brushstrokes_range[1] 
        self.maxBrushNumber = 4
        self.brushSide = 300 
        self.padding = int(self.brushSide*self.maxSize / 2 + 5)
        
        self.canvas = canvas
        
        
        self.imgMag = img_gradient[0]
        self.imgAngles = img_gradient[1]
        
        
        self.brushes = self.preload_brushes('brushes/watercolor/', self.maxBrushNumber)
        self.sampling_mask = sampling_mask
        
        
        self.cached_image = None
        self.cached_error = None
        
    def preload_brushes(self, path, maxBrushNumber):
        imgs = []
        for i in range(maxBrushNumber):
            imgs.append(cv2.imread(path + str(i) +'.jpg'))
        return imgs
    
    def gen_new_positions(self):
        if self.sampling_mask is not None:
            pos = util_sample_from_img(self.sampling_mask)
            posY = pos[0][0]
            posX = pos[1][0]
        else:
            posY = int(random.randrange(0, self.bound[0]))
            posX = int(random.randrange(0, self.bound[1]))
        return [posY, posX]
     
    def initRandom(self, target_image, count, seed):
        
        for i in range(count):
            
            color = random.randrange(0, 255)
            
            random.seed(seed-i+4)
            size = random.random()*(self.maxSize-self.minSize) + self.minSize
            
            posY, posX = self.gen_new_positions()
            
            '''
            start with the angle from image gradient
            based on magnitude of that angle direction, adjust the random angle offset.
            So in places of high magnitude, we are more likely to follow the angle with our brushstroke.
            In places of low magnitude, we can have a more random brushstroke direction.
            '''
            random.seed(seed*i/4.0-5)
            localMag = self.imgMag[posY][posX]
            localAngle = self.imgAngles[posY][posX] + 90 
            rotation = random.randrange(-180, 180)*(1-localMag) + localAngle
            
            brushNumber = random.randrange(1, self.maxBrushNumber)
            
            self.DNASeq.append([color, posY, posX, size, rotation, brushNumber])
        
        self.cached_error, self_cached_image = self.calcTotalError(target_image)
        
    def get_cached_image(self):
        return self.cached_image
            
    def calcTotalError(self, inImg):
        return self.__calcError(self.DNASeq, inImg)
        
    def __calcError(self, DNASeq, inImg):
        
        myImg = self.drawAll(DNASeq)

        
        diff1 = cv2.subtract(inImg, myImg) 
        diff2 = cv2.subtract(myImg,inImg) 
        totalDiff = cv2.add(diff1, diff2)
        totalDiff = np.sum(totalDiff)
        return (totalDiff, myImg)
            
    def draw(self):
        myImg = self.drawAll(self.DNASeq)
        return myImg
        
    def drawAll(self, DNASeq):
        
        if self.canvas is None: 
            inImg = np.zeros((self.bound[0], self.bound[1]), np.uint8)
        else:
            inImg = np.copy(self.canvas)
        
        p = self.padding
        inImg = cv2.copyMakeBorder(inImg, p,p,p,p,cv2.BORDER_CONSTANT,value=[0,0,0])
        
        for i in range(len(DNASeq)):
            inImg = self.__drawDNA(DNASeq[i], inImg)
        
        y = inImg.shape[0]
        x = inImg.shape[1]
        return inImg[p:(y-p), p:(x-p)]       
        
    def __drawDNA(self, DNA, inImg):
        
        color = DNA[0]
        posX = int(DNA[2]) + self.padding 
        posY = int(DNA[1]) + self.padding
        size = DNA[3]
        rotation = DNA[4]
        brushNumber = int(DNA[5])

        
        brushImg = self.brushes[brushNumber]
        
        brushImg = cv2.resize(brushImg,None,fx=size, fy=size, interpolation = cv2.INTER_CUBIC)
        
        brushImg = self.__rotateImg(brushImg, rotation)
        
        brushImg = cv2.cvtColor(brushImg,cv2.COLOR_BGR2GRAY)
        rows, cols = brushImg.shape
        
        
        myClr = np.copy(brushImg)
        myClr[:, :] = color

        
        inImg_rows, inImg_cols = inImg.shape
        y_min = int(posY - rows/2)
        y_max = int(posY + (rows - rows/2))
        x_min = int(posX - cols/2)
        x_max = int(posX + (cols - cols/2))
        
        
        foreground = myClr[0:rows, 0:cols].astype(float)
        background = inImg[y_min:y_max,x_min:x_max].astype(float) 
        
        alpha = brushImg.astype(float)/255.0
        

        try:
            
            foreground = cv2.multiply(alpha, foreground)
            
            
            background = cv2.multiply(np.clip((1.0 - alpha), 0.0, 1.0), background)
            
            outImage = (np.clip(cv2.add(foreground, background), 0.0, 255.0)).astype(np.uint8)
            
            inImg[y_min:y_max, x_min:x_max] = outImage
        except:
            print('------ \n', 'in image ',inImg.shape)
            print('pivot: ', posY, posX)
            print('brush size: ', self.brushSide)
            print('brush shape: ', brushImg.shape)
            print(" Y range: ", rangeY, 'X range: ', rangeX)
            print('bg coord: ', posY, posY+rangeY, posX, posX+rangeX)
            print('fg: ', foreground.shape)
            print('bg: ', background.shape)
            print('alpha: ', alpha.shape)
        
        return inImg

        
    def __rotateImg(self, img, angle):
        rows,cols, channels = img.shape
        M = cv2.getRotationMatrix2D((cols/2,rows/2),angle,1)
        dst = cv2.warpAffine(img,M,(cols,rows))
        return dst
        
              
    def __evolveDNA(self, index, inImg, seed):
        
        DNASeqCopy = np.copy(self.DNASeq)           
        child = DNASeqCopy[index]
        
        
        
        random.seed(seed + index)
        indexOptions = [0,1,2,3,4,5]
        changeIndices = []
        changeCount = random.randrange(1, len(indexOptions)+1)
        for i in range(changeCount):
            random.seed(seed + index + i + changeCount)
            indexToTake = random.randrange(0, len(indexOptions))
            
            changeIndices.append(indexOptions.pop(indexToTake))
        
        np.sort(changeIndices)
        changeIndices[:] = changeIndices[::-1]
        for changeIndex in changeIndices:
            if changeIndex == 0:
                child[0] = int(random.randrange(0, 255))
                
            elif changeIndex == 1 or changeIndex == 2:
                child[1], child[2] = self.gen_new_positions()
                
                
            elif changeIndex == 3: 
                child[3] = random.random()*(self.maxSize-self.minSize) + self.minSize
                
            elif changeIndex == 4: 
                
                localMag = self.imgMag[int(child[1])][int(child[2])]
                localAngle = self.imgAngles[int(child[1])][int(child[2])] + 90 
                child[4] = random.randrange(-180, 180)*(1-localMag) + localAngle
                
            elif changeIndex == 5: 
                child[5] = random.randrange(1, self.maxBrushNumber)
                
        
        
        child_error, child_img = self.__calcError(DNASeqCopy, inImg)
        if  child_error < self.cached_error:
            
            self.DNASeq[index] = child[:]
            self.cached_image = child_img
            self.cached_error = child_error
        
    def evolveDNASeq(self, inImg, seed):
        for i in range(len(self.DNASeq)):
            self.__evolveDNA(i, inImg, seed)