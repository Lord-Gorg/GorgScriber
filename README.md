# GorgScriber POC

GorgScriber POC is a dockerized service for local transcription of lectures and meetings with a multilingual UI and smart post-processing.

## Features

- **Local Transcription:** All transcription is done locally using faster-whisper, ensuring privacy and security. Your audio and video files are never sent to external services.
- **Multilingual UI:** The user interface supports English, German, French, Russian, and Chinese.
- **Intelligent Post-processing:**
    - **For Lectures:** Generate summaries, structured plans, key term lists, and Q&A based on the transcript.
    - **For Meetings:** Create summaries, protocols, and task lists.
- **LLM Integration:** Post-processing can leverage cloud-based LLMs like OpenAI, Claude, Grok, and OpenRouter.

## Getting Started

### Prerequisites

- Docker
- Docker Compose

### Installation

1.  **Clone the repository:**

    ```bash
    git clone https://github.com/your-username/gorgscriber.git
    cd gorgscriber
    ```

2.  **Create and configure the environment file:**

    ```bash
    cp .env.example .env
    ```

    Open the `.env` file and add your API keys for the LLM providers you want to use. Local transcription will work without any API keys.

3.  **Build and run the application:**

    The first time you run the application, it will download the necessary models, which may take some time.

    ```bash
    docker compose up --build
    ```

    For subsequent launches, you can use:

    ```bash
    docker compose up
    ```

4.  **Access GorgScriber:**

    Open your web browser and navigate to `http://localhost:7860`.

## Important Notes

-   **Transcription is always local.** Your audio and video files are not sent to any external services.
-   **LLM post-processing uses external APIs** but only sends the text transcript, not the original audio or video.
