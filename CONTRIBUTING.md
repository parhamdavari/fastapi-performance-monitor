# Contributing to FastAPI Performance Monitor

First off, thank you for considering contributing! It's people like you that make the open-source community such a great place.

## Where do I go from here?

If you've noticed a bug or have a feature request, please [check the issue tracker](https://github.com/parhamdavari/fastapi-performance-monitor/issues) to see if someone has already reported it. If you don't see it, please feel free to [open a new issue](https://github.com/parhamdavari/fastapi-performance-monitor/issues/new/choose).

## Getting Started

To get started with development, you'll need to set up the project on your local machine.

1.  **Fork the repository** on GitHub.
2.  **Clone your fork** to your local machine:
    ```bash
    git clone https://github.com/YOUR_USERNAME/fastapi-performance-monitor.git
    cd fastapi-performance-monitor
    ```
3.  **Set up a virtual environment** and install the dependencies for development:
    ```bash
    python -m venv venv
    source venv/bin/activate
    pip install -e ".[test,dev]"
    ```
4.  **Run the tests** to make sure everything is set up correctly:
    ```bash
    pytest
    ```

## Making Changes

1.  Create a new branch for your changes:
    ```bash
    git checkout -b your-feature-branch-name
    ```
2.  Make your changes and add or update tests as needed.
3.  Ensure the tests still pass:
    ```bash
    pytest
    ```
4.  Commit your changes with a clear and descriptive commit message.
5.  Push your changes to your fork on GitHub:
    ```bash
    git push origin your-feature-branch-name
    ```
6.  **Submit a pull request** to the `main` branch of the original repository.

Thank you for your contribution!
