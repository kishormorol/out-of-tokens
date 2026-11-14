---
id: OOT-0001
title: Plain-language summaries of every city council meeting
authors:
  - name: Example Author
submitted: 2026-11-14
status: open
category: civic
tags: [civic-tech, summarisation, local-news]
why_unfinished: [llm-api-cost, time]
estimated_cost: "Roughly USD 400 a month in LLM API calls for 50 cities (illustrative figure)"
example: true
---

> **Example entry.** This file shows the format. It is not a real submission, and its
> numbers are made up for illustration.

## Problem

City council meetings decide zoning, budgets and school funding, but they run for hours
and the minutes come out weeks later as scanned PDFs. Most residents never learn what was
decided until it affects them.

## Idea

A free site that publishes a one-page, plain-language summary of each council meeting
within a day: what was voted on, who voted how, what it costs, and what comes up next.
Every statement links to the timestamp in the public recording, so a reader can check it.

## Approach

1. Collect the public video or audio feed for each council.
2. Transcribe it with an open speech model that runs on a CPU overnight.
3. Split the transcript by agenda item and summarise each item with an LLM, keeping the
   timestamps.
4. Publish as static pages, with an email digest per city.

The transcription is cheap. The summarisation is what costs money: a four-hour meeting is
a long transcript, and it has to be read more than once to get votes right.

## What's done

- A scraper for one city's meeting feed.
- Transcription working end to end on a laptop.
- Twelve meetings summarised by hand-run prompts, checked against the official minutes.

The author stopped when the API bill for the second city passed what they could pay
out of pocket.

## Links

- No public code yet. A real entry would link its repository or notes here.
