# Wonder SOP Assistant (Preview Repo)

> **Note:** This is a **preview repository** for showcase purposes. Detailed logic, prompts, and architectural specifics can be found in [this document](https://docs.google.com/document/d/1IdzxGQVtmp7pX_4bOqg7EbxsgH8cbBe5gK9mG_KO__U/edit?usp=sharing).

**Wonder SOP Assistant** is an internal web application for restaurant staff to ask plain-English questions about company procedures and receive instant, sourced answers.

## Key Features

* **Staff Chat:** A voice/text interface that retrieves accurate answers from the SOP library.
* **Admin Panel:** A conversational workspace to edit or create SOPs with a **Proposal Card** system and conflict detection.
* **Source Transparency:** Every response is tagged with the specific SOP ID and title used to generate it.

## How It Works

The system utilizes a high-efficiency, dual-pass AI pipeline to maximize accuracy and minimize latency:

1.  **Search & Interpret:** Uses **BM25 search** to find the top 8 relevant SOPs. A lightweight AI call (Haiku 4.5) determines if the query needs one source (**Route A**) or multiple (**Route B**).
2.  **Contextual Response:** The system pulls the full text of the selected SOPs and streams the final answer to the user via **Server-Sent Events (SSE)**.
3.  **Shortcuts:** Direct mentions of an SOP ID (e.g., "SOP-042") bypass the interpreter step for instant retrieval.
