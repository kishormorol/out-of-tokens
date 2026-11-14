---
id: OOT-0002
title: Open model that reads handwritten family recipe cards
authors:
  - name: Example Author
  - name: Second Example Author
submitted: 2026-11-14
status: open
tags: [handwriting, ocr, open-model, fine-tuning]
why_unfinished: [gpu-cost, data-cost]
estimated_cost: "About 300 GPU-hours on a 24 GB card, plus labelling 5,000 cards (illustrative figure)"
example: true
---

> **Example entry.** This file shows the format. It is not a real submission, and its
> numbers are made up for illustration.

## Problem

Families keep recipes on handwritten index cards, in cursive, with stains, abbreviations
and notes in the margin. General OCR tools read them badly, and the people who wrote them
are often no longer around to ask.

## Idea

A small open model, fine-tuned for handwritten recipe cards, that turns a phone photo into
a structured recipe: title, ingredients with quantities, steps, and the margin notes kept
as notes. It should run on a phone or a modest laptop, so nobody has to upload family
papers to a paid service.

## Approach

1. Gather a few thousand photographed cards with permission and transcribe them.
2. Fine-tune a small open vision-language model on the pairs.
3. Add a second pass that normalises units and flags words the model was unsure of.
4. Ship it as a local app and publish the weights.

## What's done

- 600 cards photographed and transcribed by two people.
- A baseline measured with an off-the-shelf OCR tool, for comparison.
- One short fine-tuning run on a rented GPU that showed the approach works, before the
  rental budget ran out.

## Links

- No public code yet. A real entry would link its repository or notes here.
