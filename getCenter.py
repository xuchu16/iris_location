import cv2
import numpy as np
###########################################################region grow#########################################
def regionGrow(src,threshold):
    extend=cv2.copyMakeBorder(src,0,0,0,0,cv2.BORDER_REPLICATE)
    height=src.shape[0]
    width=src.shape[1]
    dst = np.zeros((height, width, 1), np.uint8)
    L=1
    for row in range(height):
        for col in range(width):
            if dst[row,col]>0:
                continue
            value=extend[row,col]
            dst=helper(extend,dst,row,col,L,value,threshold)
            L=L+1
    return dst

def helper(src,dst,row,col,L,value,threshold):
    if row<0 or row>=dst.shape[0] or col<0 or col>=dst.shape[1]:
        return dst
    if dst[row,col]>0:
        return dst
    if abs(src[row,col]-value)>=threshold:
        return dst
    dst[row,col]=L
    dst=helper(src, dst, row+1, col, L, value,threshold)
    dst=helper(src, dst, row-1, col, L, value,threshold)
    dst=helper(src, dst, row, col+1, L, value,threshold)
    dst=helper(src, dst, row, col-1, L, value,threshold)
    return dst

##########################################################thresholding methods#########################################
def calHistCircle(img,center_x,center_y,radius):
    hist=[]
    for i in range(256):
        hist.append(0)
    for row in range(img.shape[0]):
        for col in range(img.shape[1]):
            if (row-center_y)**2+(col-center_x)**2>=radius**2:
                continue
            hist[img[row,col]]+=1
    return hist

def otsu_thresholding(hist):
    sumHist=[0]

    for i in range(1,256):
        sumHist.append(sumHist[-1]+hist[i]*i)
    thresh=sumHist[255]/sum(hist)
    preThresh=-100
    count=0
    while abs(preThresh-thresh)<1 or count>100:
        x1 = sumHist[thresh] / sum(hist[thresh])
        x2 = sumHist[thresh] / sum(hist[thresh])
        preThresh=thresh
        thresh=(x1+x2)/2
        count+=1
    return thresh

def peak_thresholding(hist,min_d):
    max1=0
    max1_pos=0
    max2=0
    max2_pos=0
    for i in range(256):
        if max1<=hist[i]:
            if i-max1_pos>=min_d:
                max2=max1
                max2_pos=max1_pos
            max1=hist[i]
            max1_pos=i
            continue
        if max2<hist[i]:
            if i-max1_pos>=min_d:
                max2=hist[i]
                max2_pos=i
            continue
    thresh=(max1_pos+max2_pos)/2
    return thresh

############################################################get final result from boundary#############################
def getCenterFromContours(contours):
    pupil=contours[0]
    if len(contours)>1:
        for i in range(len(contours)):
            if contours[i].shape[0]>10 and contours[i].shape[0]<300:
                pupil=contours[i]
                break
    x_mean=0
    y_mean=0
    for i in pupil:
        x_mean+=i[0,0]
        y_mean+=i[0,1]
    total=pupil.shape[0]
    x_mean/=pupil.shape[0]
    y_mean /= pupil.shape[0]
    return (x_mean,y_mean)

##############################################################get Hough circle#########################################
def adactiveHoughPara(gray_edge,dp):
    nRows=gray_edge.shape[0]
    nCols=gray_edge.shape[1]
    start=0
    end=4*nRows
    while start<=end:
        param2 = int((start + end) / 2)

        try:
            circles = cv2.HoughCircles(gray_edge,
                                       cv2.HOUGH_GRADIENT,
                                       dp,
                                       5,
                                       minRadius=int(nRows / 20),
                                       maxRadius=int(nRows / 7),
                                       param2=param2)
        except:
            return [[]]

        if circles is None:
            end=param2-1
            continue

        #print(circles)
        #print(circles.shape)
        if circles.shape[1]>1:
            start=param2+1
            continue
        if circles.shape[1]==1:
            #print(circles[0,0,:])
            return circles
    return [[]]

############################################################algorithm part 1 ###########################################
def getRoughCircle(src,
                   smooth_method='median',
                   edge_method='canny',
                   filter_size=11,
                   hough_dp=1.5,
                   edge_thresh1=30,
                   edge_thresh2=120):

    src_img = src.copy()
    nRows = src_img.shape[0]
    nCols = src_img.shape[1]
    ##########################################preprocess############################
    src_img = cv2.cvtColor(src_img, cv2.COLOR_BGR2GRAY)
    gray = src_img.copy()
    #smooth
    if smooth_method=='mean':
        gray = cv2.blur(gray, (filter_size, filter_size))
    if smooth_method=='median':
        gray=cv2.medianBlur(gray,filter_size)
    if smooth_method=='morph':
        kernel_pre = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (filter_size, filter_size))
        gray = cv2.morphologyEx(gray, cv2.MORPH_OPEN, kernel_pre)

    #edge detect
    if edge_method=='canny':
        gray_edge = cv2.Canny(gray, edge_thresh1, edge_thresh2)
    if edge_method=='sobel':
        sobelx = cv2.Sobel(gray, cv2.CV_8UC1, 1, 0, ksize=filter_size)
        sobely = cv2.Sobel(gray, cv2.CV_8UC1, 0, 1, ksize=filter_size)
        gray_edge=cv2.addWeighted(sobelx,0.5,sobely,0.5,0)
    if edge_method=='laplacian':
        gray_edge=cv2.Laplacian(gray,cv2.CV_8UC1,ksize=filter_size)

    ##########################################getRoughCircle########################

    # circles = cv2.HoughCircles(gray_edge,cv2.HOUGH_GRADIENT, 2, 10,maxRadius=int(gray_edge.shape[0]/7),param2=50)
    circles = adactiveHoughPara(gray_edge,hough_dp)
    circles = np.uint16(np.around(circles))

    try:
        ret=circles[0,0,:]
    except:
        return (gray,[-1,-1,-1])

    ret[2]*=2
    return (gray,ret)


#############################################################algorithm part 2 ########################################
def preciseLocation(gray,
                    circle,
                    morph_kernel_size_rate=3,
                    contour_size_range_rate=10,
                    thresholding_method='peak'):
    # calculate histogram of ROI (in circle)
    hist = calHistCircle(gray, circle[0], circle[1], circle[2])
    # thresholding
    if thresholding_method=='peak':
        threshold = peak_thresholding(hist, 20)
    if thresholding_method=='otsu':
        threshold = otsu_thresholding(hist)
    #print('thresh', threshold)
    (threshold, binary) = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY_INV)
    # set region out of circle all 0
    for row in range(binary.shape[0]):
        for col in range(binary.shape[1]):
            if (row - circle[1]) ** 2 + (col - circle[0]) ** 2 >= circle[2] ** 2:
                binary[row, col] = 0
    cv2.imshow('canny1', binary)


    # morph method to solve high light in eye
    if morph_kernel_size_rate>0:
        kernel1 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (int(circle[2] / morph_kernel_size_rate), int(circle[2] / morph_kernel_size_rate)))
        kernel2 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (int(circle[2] / 8), int(circle[2] / 8)))
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel1)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel1)
    cv2.imshow('canny2', binary)

    # extract the boundray of the pupil
    contours = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)[1]

    # calculate the center
    (x, y) = getCenterFromContours(contours)
    return(x, y)



def getCorneaCenter(src):
    src_img=src.copy()
    nRow = src_img.shape[0]
    nCol = src_img.shape[1]
    ft=240/nRow
    src_img=cv2.resize(src_img,None,fx=ft,fy=ft,interpolation = cv2.INTER_CUBIC)

    (gray,circle)=getRoughCircle(src_img)
    if circle[0]==-1:
        (x,y)=(src_img.shape[0]/2,src_img.shape[1]/2)
        return (x,y)
    cv2.circle(src_img,(int(circle[0]),int(circle[1])),int(circle[2]),(255,0,0),thickness=2)
    cv2.imshow('circle',src_img)
    return (circle[0]/ft,circle[1]/ft)
    (x,y)=preciseLocation(gray,circle)
    x/=ft
    y/=ft
    return (x,y)
