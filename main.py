import os
import requests
import torch
from torch.nn import MultiheadAttention


# Set the torch seed
torch.manual_seed(1337)

# Download dataset
def dataset():
    filename = "input.txt"
    url = "https://raw.githubusercontent.com/karpathy/char-rnn/master/data/tinyshakespeare/input.txt"
    # Download dataset
    if not os.path.exists(filename):
        response = requests.get(url)
        if response.status_code == 200:
            with open(filename, 'wb') as file:
                file.write(response.content)
        else:
            raise ValueError("Failed to download tinyshakespeare dataset")
    # Load dataset from disk
    with open(filename, 'r', encoding='utf-8') as file:
        content = file.read()
    return content

# Generate tokeniser from dataset
def tokeniser(dataset):
    # Extract unique characters used
    vocab = sorted(list(set(dataset)))
    # Construct string to int mapping
    stoi = { ch:i for i,ch in enumerate(vocab) }
    # Construct int to string mapping
    itos = { i:ch for i,ch in enumerate(vocab) }
    # Construct tokeniser encoder
    encode = lambda s: [stoi[c] for c in s]
    # Construct tokeniser decoder
    decode = lambda l: ''.join([itos[i] for i in l])
    # Return encoder decoder
    return encode, decode, vocab

# Sample a training batch from source dataset
def batch(source, block_size=8, batch_size=4):
    # Generate random sample positions
    ix = torch.randint(len(source)-block_size, (batch_size,))
    # Sample chunks
    x  = torch.stack([source[i:i+block_size] for i in ix])
    # Sample chunks with offset of 1
    y  = torch.stack([source[i+1:i+block_size+1] for i in ix])
    return x,y

# Self Attention Head
class SelfAttentionHead(torch.nn.Module):
    def __init__(self, T, C, H=16, encoder=True):
        super().__init__()
        self.T = T # Block size
        self.C = C # Channels
        self.H = H # Head size
        self.encoder    = encoder
        self.key   = torch.nn.Linear(C, H, bias=False)
        self.query = torch.nn.Linear(C, H, bias=False)
        self.value = torch.nn.Linear(C, H, bias=False)
        self.register_buffer('t', torch.tril(torch.ones(T,T)))
    def forward(self, x):
        # Compute the key
        k = self.key(x) # B,T,H
        # Compute the query
        q = self.query(x) # B,T,H
        # Compute the weights
        # (B,T,H) @ (B,H,T) --> (B,T,T)
        w = q @ k.transpose(-2,-1) * self.H**-0.5 
        # Mask the weights
        if self.encoder:
            w = w.masked_fill(self.t[:self.T,:self.T] == 0, float('-inf'))
        # Apply the softwax 
        w = torch.nn.functional.softmax(w, dim=-1)
        # Return result
        return w @ self.value(x)

class MultiSelfAttentionHead(torch.nn.Module):
    def __init__(self, T, C, H=16, heads=10, encoder=True):
        super().__init__()
        self.heads = torch.nn.ModuleList([SelfAttentionHead(T,C,H,encoder) for _ in range(heads)])

    def forward(self, x):
        return torch.cat([h(x) for h in self.heads], dim=-1)

class FeedForward(torch.nn.Module):
    def __init__(self, C):
        super().__init__()
        self.net = torch.nn.Sequential(
            torch.nn.Linear(C,4*C), 
            torch.nn.ReLU(),
            torch.nn.Linear(4*C,C), 
        )
    def forward(self,x):
        return self.net(x)

class Block(torch.nn.Module):
    def __init__(self, T, C, H=16, heads = 10, encoder = True):
        super().__init__()
        self.ln1  = torch.nn.LayerNorm(C)
        self.head = MultiSelfAttentionHead(T,C,H, heads, encoder)
        self.ln2  = torch.nn.LayerNorm(C)
        self.ff   = FeedForward(H*heads)
    def forward(self,x):
        x = x + self.head(self.ln1(x))
        x = x + self.ff(self.ln2(x))
        return x

# Bigram language model
class GPT(torch.nn.Module):

    def __init__(self, vocab_size, block_size, blocks=3, head_size = 16, heads=2):
        # Init super
        super().__init__()
        # Store parameters
        self.vocab_size = vocab_size
        self.block_size = block_size
        self.head_size  = head_size
        self.heads      = heads
        # Create bigram
        self.token_embedding_table = torch.nn.Embedding(vocab_size, head_size*heads)
        # Encode token position
        self.pos = torch.nn.Embedding(block_size, head_size*heads)
        # Create self attention heads
        # self.blocks = Block(block_size, head_size, heads)
        self.blocks = torch.nn.Sequential(
            *[Block(block_size, head_size*heads, head_size, heads) for _ in range(blocks)]
        )
        # Layer norm for last layer
        self.ln = torch.nn.LayerNorm(head_size*heads)
        # Create linear layer for head
        self.last = torch.nn.Linear(head_size*heads, vocab_size)

    def forward(self, idx, targets=None):
        # Get dims
        B,T = idx.shape
        # Embed tokens
        token_embed = self.token_embedding_table(idx) # (B,T,C)
        # Token position embedding
        pos_embed = self.pos(torch.arange(T)) # (T,C)
        # Cat emebddings
        x = token_embed + pos_embed # (B,T,C)
        # Apply self attention
        x = self.blocks(x)
        # Get logits
        logits = self.last(self.ln(x)) # (B,T, vocab_size)
        # Return
        if targets is None:
            return logits, None
        # Get dims
        B, T, C = logits.shape
        # Reshape logits
        rlogits = logits.view(B*T, C)
        # Reshape targets
        targets = targets.view(B*T)
        # Compute the loss
        loss = torch.nn.functional.cross_entropy(rlogits,targets)
        # Return 
        return logits, loss

    def generate(self, x):
        # Crop input
        x_cropped = x[:, -self.block_size:]
        logits, _ = self(x_cropped)
        logits = logits[:,-1,:]
        probs  = torch.nn.functional.softmax(logits, dim=1)
        x_next = torch.multinomial(probs, num_samples=1)
        x_new  = torch.cat((x, x_next), dim=1)
        return x_new


# Train Bigram Language
def train_bigram(model, train, block_size=8, batch_size=32, steps=1000, lr=1e-3):
    # Create optimizer
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr)
    # Start training
    for step in range(steps):
        xb, yb = batch(train, block_size, batch_size)
        _, loss = model(xb,yb)
        print(f"\repoch: {step} loss: {loss}", end="", flush=True)
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()

# Main
if __name__ == "__main__":
    # # Load dataset
    text = dataset()
    # # Create tokeniser
    encode,decode,vocab = tokeniser(text)
    # Encode text
    data = torch.tensor(encode(text), dtype=torch.long)
    # Split dataset
    n = int(0.9*len(data))
    # Training dataset
    train = data[:n]
    # Validation dataset
    val = data[n:]
    # Create bigram model
    model = GPT(len(vocab), 64, 4, 64, 4)
    # Train model
    train_bigram(model, train, batch_size=32, block_size=64, steps=5000, lr=1e-4)
    # Start with new line character
    idx = torch.zeros((1,64), dtype=torch.long)
    # Generate words
    for _ in range(1000):
        idx = model.generate(idx)
    # Decode it to text
    novel = decode(idx[0].tolist())
    # Print generated text
    print(novel)
