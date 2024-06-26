import torch
import torch.nn as nn
import torch.optim as optim
import torchvision
import torchvision.transforms as transforms
import typer

# Define the neural network architecture
class Net(nn.Module):
    def __init__(self):
        super(Net, self).__init__()
        self.conv1 = nn.Conv2d(1, 32, 3, 1)
        self.conv2 = nn.Conv2d(32, 64, 3, 1)
        self.fc1 = nn.Linear(9216, 128)
        self.fc2 = nn.Linear(128, 10)

    def forward(self, x):
        x = torch.relu(self.conv1(x))
        x = torch.relu(self.conv2(x))
        x = torch.max_pool2d(x, 2)
        x = torch.flatten(x, 1)
        x = torch.relu(self.fc1(x))
        x = self.fc2(x)
        return torch.log_softmax(x, dim=1)

def main(epochs:int = 10, batch_size:int=64, learning_rate:float=0.001, model_filename="model"):
    # Define the device
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

    # Define transforms
    transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize((0.1307,), (0.3081,))
    ])

    # Log
    print('[*] Load MNIST dataset')

    # Load and preprocess the MNIST dataset
    trainset = torchvision.datasets.MNIST(root='/tmp', train=True, download=True, transform=transform)
    trainloader = torch.utils.data.DataLoader(trainset, batch_size=batch_size, shuffle=True)

    testset = torchvision.datasets.MNIST(root='/tmp', train=False, download=True, transform=transform)
    testloader = torch.utils.data.DataLoader(testset, batch_size=batch_size, shuffle=False)

    # Create an instance of the network
    model = Net().to(device)

    # Define the loss function and optimizer
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=learning_rate)

    # Log
    print('[*] Train model')

    # Training the model
    try:
        for epoch in range(epochs):  # loop over the dataset multiple times

            running_loss = 0.0
            for i, data in enumerate(trainloader, 0):
                inputs, labels = data[0].to(device), data[1].to(device)

                optimizer.zero_grad()

                outputs = model(inputs)
                loss = criterion(outputs, labels)
                loss.backward()
                optimizer.step()

                running_loss += loss.item()
                if i % 100 == 99:    # print every 100 mini-batches
                    print('[%d, %5d] loss: %.3f' %
                          (epoch + 1, i + 1, running_loss / 100))
                    running_loss = 0.0
        print('[*] Finished Training')
    except KeyboardInterrupt:
        print("\n[!] Aborted training!")


    # Test the network on the test data
    correct = 0
    total = 0
    with torch.no_grad():
        for data in testloader:
            images, labels = data[0].to(device), data[1].to(device)
            outputs = model(images)
            _, predicted = torch.max(outputs.data, 1)
            total += labels.size(0)
            correct += (predicted == labels).sum().item()

    print('Model accuracy on 10000 test images: %d %%' % (100 * correct / total))

    # Log
    print('[*] Export model to onnx format')

    # Evaluation mode
    model.eval()

    # Define the trace
    trace = torch.zeros(1, 1, 28, 28, dtype=torch.float)

    # Export model in onnx format
    torch.onnx.export(
        model,
        trace,
        model_filename + ".onnx", 
        input_names=['input'],
        output_names=['output']
    )

    # Log
    print('[*] Export model to torch script')
    script_module = torch.jit.trace(model, trace)

    # Test the script module
    script_module(trace)

    # Save the torch script
    script_module.save(model_filename + ".pt")

    # Log
    print('[*] done')

if __name__ == "__main__":
    typer.run(main)
