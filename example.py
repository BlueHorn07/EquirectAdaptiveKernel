import argparse
from spherenet import OmniMNIST, OmniFashionMNIST
import torch
from torch import nn
import torch.nn.functional as F
import numpy as np

from omni import OmniConv2d, OmniMaxPool2d, Equirect2Omni


class OmniNet(nn.Module):
  def __init__(self):
    super(OmniNet, self).__init__()
    self.e2a = Equirect2Omni()
    self.conv1 = OmniConv2d(1, 32, kernel_size=5, stride=1)  # 논문에서 conv-kernel 사이즈가 5x5라고 나오넹
    self.pool1 = OmniMaxPool2d(stride=2)
    self.conv2 = OmniConv2d(32, 64, kernel_size=5, stride=1)
    self.pool2 = OmniMaxPool2d(stride=2)

    self.fc = nn.Linear(64 * 15 * 15, 10)

  def forward(self, x):
    x = self.e2a(x)

    x = F.relu(self.pool1(self.conv1(x)))
    x = F.relu(self.pool2(self.conv2(x)))
    x = x.view(-1, 64 * 15 * 15)  # flatten, [B, C, H, W) -> (B, C*H*W)
    x = self.fc(x)
    return x


def train(args, model, device, train_loader, optimizer, epoch):
  model.train()
  for batch_idx, (data, target) in enumerate(train_loader):
    data, target = data.to(device), target.to(device)
    optimizer.zero_grad()
    if data.dim() == 3:
      data = data.unsqueeze(1)  # (B, H, W) -> (B, C, H, W)
    output = model(data)
    loss = F.cross_entropy(output, target)
    loss.backward()
    optimizer.step()
    if batch_idx % args.log_interval == 0:
      print('Train Epoch: {} [{}/{} ({:.0f}%)]\tLoss: {:.6f}'.format(
        epoch, batch_idx * len(data), len(train_loader.dataset),
               100. * batch_idx / len(train_loader), loss.item()))


def test(args, model, device, test_loader):
  model.eval()
  test_loss = 0
  correct = 0
  with torch.no_grad():
    for data, target in test_loader:
      data, target = data.to(device), target.to(device)
      if data.dim() == 3:
        data = data.unsqueeze(1)  # (B, H, W) -> (B, C, H, W)
      output = model(data)
      test_loss += F.cross_entropy(output, target).item()  # sum up batch loss
      pred = output.max(1, keepdim=True)[1]  # get the index of the max log-probability
      correct += pred.eq(target.view_as(pred)).sum().item()

  test_loss /= len(test_loader.dataset)
  print('\nTest set: Average loss: {:.4f}, Accuracy: {}/{} ({:.0f}%)\n'.format(
    test_loss, correct, len(test_loader.dataset),
    100. * correct / len(test_loader.dataset)))
  with open("log.txt", "a") as f:
    f.write('Test set: Average loss: {:.4f}, Accuracy: {}/{} ({:.0f}%)\n'.format(
      test_loss, correct, len(test_loader.dataset),
      100. * correct / len(test_loader.dataset)))


def main():
  # Training settings
  parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument('--data', type=str, default='MNIST',
                      help='dataset for training, options={"FashionMNIST", "MNIST"}')
  parser.add_argument('--batch-size', type=int, default=128, metavar='N',
                      help='input batch size for training')
  parser.add_argument('--test-batch-size', type=int, default=128, metavar='N',
                      help='input batch size for testing')
  parser.add_argument('--epochs', type=int, default=100, metavar='N',
                      help='number of epochs to train')
  parser.add_argument('--optimizer', type=str, default='adam',
                      help='optimizer, options={"adam, sgd"}')
  parser.add_argument('--lr', type=float, default=1e-4, metavar='LR',
                      help='learning rate')
  parser.add_argument('--momentum', type=float, default=0.9, metavar='M',
                      help='SGD momentum')
  parser.add_argument('--no-cuda', action='store_true', default=False,
                      help='disables CUDA training')
  parser.add_argument('--seed', type=int, default=1, metavar='S',
                      help='random seed')
  parser.add_argument('--log-interval', type=int, default=1, metavar='N',
                      help='how many batches to wait before logging training status')
  parser.add_argument('--save-interval', type=int, default=1, metavar='N',
                      help='how many epochs to wait before saving model weights')
  args = parser.parse_args()
  use_cuda = not args.no_cuda and torch.cuda.is_available()

  torch.manual_seed(args.seed)

  device = torch.device('cuda' if use_cuda else 'cpu')

  kwargs = {'num_workers': 1, 'pin_memory': True} if use_cuda else {}

  np.random.seed(args.seed)
  if args.data == 'FashionMNIST':
    train_dataset = OmniFashionMNIST(fov=120, flip=True, h_rotate=True, v_rotate=True, img_std=255, train=True)
    test_dataset = OmniFashionMNIST(fov=120, flip=True, h_rotate=True, v_rotate=True, img_std=255, train=False,
                                    fix_aug=True)
  elif args.data == 'MNIST':
    train_dataset = OmniMNIST(fov=120, flip=True, h_rotate=True, v_rotate=True, train=True)
    test_dataset = OmniMNIST(fov=120, flip=True, h_rotate=True, v_rotate=True, train=False, fix_aug=True)
  train_loader = torch.utils.data.DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True, **kwargs)
  test_loader = torch.utils.data.DataLoader(test_dataset, batch_size=args.test_batch_size, shuffle=False, **kwargs)

  # Train
  omni_model = OmniNet().to(device)
  if args.optimizer == 'adam':
    omni_optimizer = torch.optim.Adam(omni_model.parameters(), lr=args.lr)
  elif args.optimizer == 'sgd':
    omni_optimizer = torch.optim.SGD(omni_model.parameters(), lr=args.lr, momentum=args.momentum)

  for epoch in range(1, args.epochs + 1):
    # OmniCNN
    print('{} OmniCNN {}'.format('=' * 10, '=' * 10))
    train(args, omni_model, device, train_loader, omni_optimizer, epoch)
    test(args, omni_model, device, test_loader)
    if epoch % args.save_interval == 0:
      torch.save(omni_model.state_dict(), 'Omni_model.pkl')


if __name__ == '__main__':
  main()
