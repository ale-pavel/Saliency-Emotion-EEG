#!/usr/bin/env python
# coding: utf-8

from statistics import multimode
from Models_DEAP import *
# from Models import *
from Utils import *
from Utils_Bashivan import *
import time
import warnings

warnings.simplefilter("ignore")

t = time.time()

use_cuda = torch.cuda.is_available()
device = torch.device('cuda:0' if use_cuda else 'cpu')
device

deap_path = '../../datasets/DEAP/'
load_deap_data = True

if load_deap_data:
    X_image = np.load('../../datasets/DEAP/image_generation/images.npy') # place here the images representation of EEG
    X_array_all_electrodes = np.load('../../datasets/DEAP/merged/deap_data.npy') # place here the array representation of EEG features
    Label_full = np.load('../../datasets/DEAP/merged/deap_full_labels.npy') # place here the label for each EEG
    Participant = np.load('../../datasets/DEAP/image_generation/participants.npy') # place here the array with each participants

    X_array = X_array_all_electrodes[:, :32, :]
    Label = Label_full[:, 2]
else:
    X_image = np.load('Example_Input/img.npy') # place here the images representation of EEG
    X_array = np.load('Example_Input/array.npy') # place here the array representation of EEG features
    Label = np.load('Example_Input/label.npy') # place here the label for each EEG
    Participant = np.load('Example_Input/participant.npy') # place here the array with each participants

print(X_image.shape)
print(X_array.shape)
print(Label.shape)
print(Participant.shape)

set(Label)
print(set(Participant))

# X_array[0, :5] #maybe it's Raw EEG with 62 channels (SEED dataset has as many) and 3 time samples?

# X_image[0, 0, 5:-4, 6:-6]

# image = np.moveaxis(X_image[0], 0 ,-1)
# image = (image - np.min(image)) / (np.max(image) - np.min(image))

# get_ipython().run_line_magic('matplotlib', 'inline')
# from matplotlib import pyplot as plt
# plt.imshow(image[:, :, :3])
# plt.show()

# freqs = X_array[0, :, :]

# plt.psd(freqs) #sum of the other 3?
# plt.psd(X_array[0, :, 0])
# plt.psd(X_array[0, :, 1])
# plt.psd(X_array[0, :, 2])
# plt.show()

# plt.psd(X_array[0, :, :])
# plt.show()

n_epoch = 150


# In[16]:


Dataset = CombDataset(label=Label, image=X_image, array=X_array) #creation of
#dataset classs in Pytorch


# In[17]:


# electrodes locations in 3D -> 2D projection
locs_3d = np.load('Electroloc/Neuro_loc_DEAP.npy')[:31]
locs_2d = []
for e in locs_3d:
    locs_2d.append(azim_proj(e))

mutl_img = torch.ones((X_image.shape[1], 32, 32)) #initiate the gain matrice


# In[18]:


locs_3d.shape


# In[19]:


np.asarray(locs_2d).shape


# Uses LOSO (Leave One Subject Out) Cross Validation

# In[20]:


for p in range(load_deap_data, len(np.unique(Participant) + load_deap_data)):
    print("Training participant ", p)

    #Splitting in Train and Testing Set
    idx = np.argwhere(Participant == p)[:, 0]
    np.random.shuffle(idx)
    Test = Subset(Dataset, idx)
    idx = np.argwhere(Participant != p)[:, 0]
    np.random.shuffle(idx)
    Train = Subset(Dataset, idx)

    #Train Test Loader Pytorch
    Trainloader = DataLoader(Train, batch_size=128, shuffle=False)
    Testloader = DataLoader(Test, batch_size=128, shuffle=False)

    #Set training parameters
    lr = 1e-3
    wd = 1e-4
    mom = 0.9

    #net = MultiModel(X_image).to(device)
    net = MultiModel().to(device) # Models_DEAP.py doesn't require a parameter here
    #optimizer = optim.SGD(net.parameters(), lr=lr, momentum=mom,  weight_decay=wd)
    optimizer = optim.Adam(net.parameters(), lr=lr,  weight_decay=wd)

    Res = []

    validation_loss = 0.0
    validation_acc = 0.0

    for epoch in range(n_epoch):
        running_loss = 0.0
        evaluation = []

        #Training
        net.train()
        for i, data, data_test in iter_over(Trainloader, Testloader):
            source_img, source_arr, label = data #signals from training
            target_img, target_arr, _ = data_test #signals with unknwon label

            # Image Representaion + multiplication with gain matrix from saliency
            img = torch.cat([source_img, target_img])
            img = img * mutl_img
            img = img.to(device)

            # Array Representation
            arr = torch.cat([source_arr, target_arr])
            arr = arr.to(device)

            # True Domain
            domain_y = torch.cat([torch.ones(source_img.shape[0]),
                                  torch.zeros(target_img.shape[0])])
            domain_y = domain_y.to(device)

            # True Label
            label = label.to(device)

            # Estimation of both feature vectors + concat
            feat_img = net.FeatCNN(img.to(torch.float32).to(device))
            feat_arr = net.FeatRNN(arr.to(torch.float32).to(device))
            feat = torch.cat((feat_img, feat_arr), axis=1)

            # Domain and Label prediction
            domain_pred = net.Discriminator(feat).squeeze()
            label_pred = net.ClassifierFC(feat[:source_img.shape[0]])

            # Loss Computing
            domain_loss = F.binary_cross_entropy_with_logits(domain_pred, domain_y)
            label_loss = F.cross_entropy(label_pred, label.long())

            # Loss Backward
            optimizer.zero_grad()
            loss = domain_loss + label_loss
            loss.backward()
            optimizer.step()
            running_loss += label_loss.item()

            # Prediction and Accuracy
            _, predicted = torch.max(label_pred, 1)
            num_of_true = torch.sum(predicted == label)
            mean = num_of_true/label.shape[0]
            evaluation.append(mean)

        running_loss = running_loss / (i + 1)
        running_acc = sum(evaluation) / len(evaluation)

        evaluation = []

        #Evaluation
        net.eval()
        for j, data in enumerate(Testloader, 0):
            img, arr, label = data

            # Prediction
            pred = net(img.to(torch.float32).to(device), arr.to(torch.float32).to(device))
            loss = F.cross_entropy(pred, label.to(device).long())

            # Loss
            validation_loss += loss.item()

            # Accuracy
            _, predicted = torch.max(pred.cpu().data, 1)
            evaluation.append((predicted == label).tolist())

            # Updating the saliency of RNN
            X = arr.to(torch.float32).to(device)
            X.requires_grad_()
            net.train()
            scores = net.FeatRNN(X)
            score_max_index = scores.mean(axis=0).argmax()
            score_max = scores[0,score_max_index]
            score_max.backward()
            net.eval()
            saliency, _ = torch.max(X.grad.data.abs(),dim=2)
            saliency = saliency.mean(axis=0).cpu().detach().numpy()
            saliency[np.isnan(saliency)] = 0
            # saliency = gen_images(np.asarray(locs_2d), saliency.reshape((1,62)), 32)[0,0]
            saliency = gen_images(np.asarray(locs_2d), saliency.reshape((1, 32)), 32)[0, 0]
            saliency = np.stack(X_image.shape[1]*[saliency])
            saliency[np.isnan(saliency)] = 0
            saliency = saliency**2
            saliency = (saliency/saliency.max()+0.05)*2
            mutl_img = torch.from_numpy(saliency)

        validation_loss = validation_loss /(j+1)
        evaluation = [item for sublist in evaluation for item in sublist]
        validation_acc = sum(evaluation) / len(evaluation)

        print('[%d, %3d] \t loss: %.3f\tAccuracy : %.3f\t\tval-loss: %.3f\tval-Accuracy : %.3f' %
                      (epoch + 1, n_epoch, running_loss, running_acc, validation_loss, validation_acc))

        Res.append((epoch + 1, n_epoch, running_loss, running_acc, validation_loss, validation_acc))
    path =  'res/sub'+str(p)+'/'
    np.save(path+'rec_'+str(len(glob.glob(path+'*.npy')))+'_lr_'+str(lr)+'_wd_'+str(wd)+'_mom_'+str(mom), Res)
    print('End after_'+str(np.round(time.time() - t, 3))+'\n')
    t = time.time()

#!jupyter nbconvert --to script DEAP_Saliency_Test.ipynb
