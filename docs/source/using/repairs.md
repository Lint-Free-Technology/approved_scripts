---
title: Repairs and changed scripts
---
# Repairs and changed scripts

An approval belongs to one script revision. Saving, editing, or reloading a script changes its canonical snapshot and pauses any affected approval.

Home Assistant creates a Repair so an administrator can explicitly approve the new revision. The Repair flow describes why delegated execution was paused and offers the current approval form. Click **Submit** to reapprove it.

An administrator may ignore the Repair when the script should intentionally remain unapproved. Ignoring a Repair never restores delegated execution; it only dismisses the reminder.
