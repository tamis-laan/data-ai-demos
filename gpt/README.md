# Decoder only transformer

This is a mini decoder only transformer similar to GPT written from scratch using pytorch.

*Note: You can break out of the training loop using ctl-c and the script will save the model to disk from the last training step.*

Create a virtual environment
``` bash
python -m venv .venv
```

Install required packages
``` bash
pip install -r requirements.txt
```

Activate the environment
``` bash
source .venv/bin/activate
```

Run the script
``` bash
python main.py
```

You can also use docker
``` bash
docker build . --tag gpt:latest
```

``` bash
docker run -v "$(pwd)/out:/out" gpt:latest --steps 2500
```

You can serve the demo using python web server.
``` bash
python -m http.server
```
*NOTE: Browser block tools like ublock origin will block loading the script. Make sure to disable them.*

