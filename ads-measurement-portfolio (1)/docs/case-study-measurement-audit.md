# Case study: auditing the measurement foundation before a growth plan

The three pages below are fictional samples bundled with the app. The scenario shows how the audit turns a technical review into a prioritized plan for a marketing leader.

## Client situation

An advertiser plans to move more budget into automated bidding. Automated bidding learns from conversion signals, so before the budget moves, the team wants to know how much of that signal survives consent choices, browser restrictions and cookie loss.

## What the audit checks

The audit scores a page out of 100 across six areas: Google tag foundation (15), Consent Mode v2 (25), enhanced conversions (25), first-party or server-side tagging (15), secure transport (5) and tag hygiene (15). The weights reflect how much conversion signal each area can recover.

## Three pages, three stories

**Basic setup, direct tag only: 30 of 100, Exposed.**
The page has a working tag and HTTPS, but no consent signals, no enhanced conversions and no server-side tagging. It also carries a legacy Universal Analytics ID. The two largest recoverable blocks, Consent Mode v2 and enhanced conversions, are worth up to 25 points each, so they lead the priority list.

**Typical setup, Tag Manager with a consent platform: 35 of 100, Exposed.**
The page loads a Tag Manager container and is clean on hygiene. The audit marks Consent Mode v2 and enhanced conversions as **unverifiable**, because those settings usually live inside the container, where a static page check cannot see them. They earn no credit until the user confirms them. This is deliberate: an audit that guesses in the client's favor produces false comfort, and one that guesses against them produces false alarm. The correct output is a short list of items to verify in a Tag Manager session.

**Modern setup, Consent Mode v2, enhanced conversions and server-side tagging: 100 of 100, Resilient.**
Every area is detected. The recommendation shifts from fixes to monitoring.

## Recommendation pattern

1. Verify the unverifiable items first, because they cost the least to confirm and may change the score the most.
2. Implement Consent Mode v2 and a certified consent platform so modeling can recover conversions from unconsented traffic.
3. Enable enhanced conversions with hashed first-party data.
4. Move to first-party or server-side tagging where the business case supports the engineering effort.
5. Retest, then size the automated bidding budget against the improved signal.

## Limits

A static check reads page source only. It cannot see container contents, tags injected after load, or server-side configuration behind a custom domain. It is a screening tool that decides where to look, and it does not replace a tag debugging session.
