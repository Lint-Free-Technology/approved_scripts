---
title: Quick Start
description: Install Approved Scripts and create the first delegated approval.
---

# Quick Start

Approved Scripts is configured in the Home Assistant Devices and services UI.

## Download & install using Marketplace

[![Open your Home Assistant instance and open a repository in the Marketplace.](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=Lint-Free-Technology&repository=approved_scripts&category=integration)

Download and install Approved Scripts via the [Home Assistant Marketplace](https://www.home-assistant.io/integrations/marketplace/). You can do this easily in one step by clicking the button above and then clicking Install.

!!! tip
    Make sure you refresh the browser after installation to load the Frontend script.

??? info "Manual installation"
    Copy `custom_components/approved_scripts` to your Home Assistant configuration directory, restart Home Assistant, add the integration from **Devices & services**, then refresh the browser page.

## Create a script approval

1. Open **Settings → Devices & services → Approved Scripts → Configure**.
2. In the **Approved Scripts** admin page, find a script with a visible **Configure approval** action.
3. Select the active non-admin users who may run it.
4. Review each protected action and, if it uses a template, add the exact rendered values it may produce.
5. Acknowledge the protected actions and save.

The approval applies only to the revision you reviewed. Editing or reloading a script pauses an affected approval until an administrator explicitly approves the new revision.

## What you can approve today

`mqtt.publish` and `zwave_js.set_lock_usercode` are the currently supported protected actions. A script that does not contain a registered protected action shows **Approval not required**. A script that resembles a supported action but fails its safety contract shows **Approval not supported** and has no action button.

## Next up

- [Using Approved Scripts](../using/index.md)
- [Security boundaries](../security/index.md)
