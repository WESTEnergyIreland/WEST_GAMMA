# WEST workflow

How the five of us change the code, the paper and the supplementary material without overwriting each other's work. Applies whether or not you use an AI assistant.

Status: draft for group agreement, 30 October 2026.

## Code (this repository)

1. Never commit straight to `main`. Make a branch, push it and open a pull request.
2. Post the pull request in the Teams chat and ask for a review. The author may merge without waiting for it.
   A review after the merge is still welcome; any fix goes in a new pull request.
3. Any change that moves a result gets a `CHANGELOG.md` entry with an old and new value table, as for 30 October 2026.
4. Do not commit `scenario_outputs/` or other generated output, except files the paper cites directly.
5. Pull `main` before starting work. Keep pull requests small and on one topic.

## Paper (Google Doc)

1. The Google Doc listed in `CONTEXT.md` is the only master. No Word, Markdown or PDF working copies.
2. Each section has one owner. Edit your own sections directly. For anyone else's section, use Suggesting mode or a comment.
3. Numbers in the paper are updated only after the code change behind them is merged.

| Section | Owner |
|---|---|
| Abstract and introduction | TBC |
| Method | TBC |
| Data | TBC |
| Validation | TBC |
| Results | TBC |
| Discussion and conclusion | TBC |

## Supplementary material

Same rules as the paper once its master location is agreed (see `CONTEXT.md`).

## Decisions

Decisions made in the Teams chat or a meeting go into `CONTEXT.md` by pull request. If it is not in `CONTEXT.md`, other members and their AI assistants will not know about it.

## If you use an AI assistant

- Give it `CONTEXT.md`, `STYLE.md` and `WORKFLOW.md` at the start of each session. Claude Code reads `CLAUDE.md` automatically, which points to them.
- Your assistant cannot see anyone else's chats or memory. Anything it needs to know must be in these files.
- It follows the same rules: branches and pull requests for code, own sections only in the paper.
- Check every number and reference it produces against the model output or the source.
