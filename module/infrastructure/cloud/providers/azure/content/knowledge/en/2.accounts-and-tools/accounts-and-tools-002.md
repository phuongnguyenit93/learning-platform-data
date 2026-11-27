# Setting Up a Lab Environment and Initial Budget

Microsoft Azure provides many compute, networking, storage, database, and monitoring services. To learn and experiment with these services, you first need a suitable subscription, access tools, a manageable resource scope, and a way to track costs. Preparing a budget from the start gives the lab clear boundaries and avoids leaving test resources incurring charges after you have finished learning.

This lesson belongs to the **Accounts and Tools** chapter of the **CLOUD_PROVIDERS_AZURE** module. The module explores the Microsoft Azure ecosystem from subscriptions, resource groups, and Microsoft Entra ID to virtual networks, compute services, storage, and data; while also guiding how to deploy, monitor, secure, and control costs for an application architecture. Therefore, the lab environment in this lesson will be prepared in a way that can scale into subsequent lessons.

After this lesson, you will be able to:

- Distinguish between a sign-in account, a Microsoft Entra ID tenant, and an Azure subscription.
- Choose a subscription type suited to your learning goals and existing access permissions.
- Sign into the Azure Portal, Cloud Shell, or Azure CLI and confirm the exact subscription you are operating on.
- Create a resource group with clear naming conventions, region, and tags.
- Set up a budget, configure alerts, and monitor incurred costs.
- Clean up resources after practicing and check for any charges that may still remain.

## 1. Understanding the Components of an Azure Environment

Before creating resources, distinguish three concepts that often appear together:

| Component | Role | Example |
|---|---|---|
| User account | Identity used to sign in and perform actions | Work, school, or personal Microsoft account |
| Microsoft Entra ID tenant | Identity boundary containing users, groups, applications, and authentication settings | Organization's tenant or default tenant created upon service sign-up |
| Azure subscription | Boundary for managing resources, access permissions, and billing | Subscription used for learning or development environments |

One account can access multiple tenants; one tenant can be linked to multiple subscriptions. The subscription defines the scope where you deploy resources and track costs. The tenant manages identities and authentication. Therefore, signing in successfully does not necessarily mean you have a subscription where resources can be deployed.

Within a subscription, a **resource group** is a logical grouping used to organize related resources. For example, a lab might place a virtual machine, virtual network, public IP, and disk in the same resource group. You can view costs, apply tags, and delete the resource group when the lab ends. A resource group is not a separate invoice; costs are still recorded by service and the corresponding billing scope.

Visualize the structure in order:

~~~text
User account
    |
    +-- Microsoft Entra ID Tenant
            |
            +-- Azure subscription
                    |
                    +-- Resource group: rg-azure-lab-dev
                    |       +-- Virtual network
                    |       +-- Compute resource
                    |       +-- Storage account
                    |
                    +-- Other resource groups
~~~

When practicing, always verify the tenant and subscription before creating or deleting resources. This is a simple step that helps avoid operating on a shared or production environment by mistake.

## 2. Choosing an Account and Subscription

Azure can be used through several sign-up models. Program names, credit amounts, trial durations, free service lists, and eligibility criteria can change by country, time, and account type. Read the terms displayed at the time of registration instead of relying on outdated promotional figures.

### Pay-as-you-go subscription

A Pay-As-You-Go subscription is suitable when you need to proactively create resources and pay based on usage. You typically need to provide billing information and may be responsible for incurred costs. Check the payment method, currency, taxes, and resource creation permissions before starting.

### Azure free account

The Azure Free Account program may provide trial credit for a limited period and capped free usage for certain services. Conditions, limits, and how it transitions to paid billing may change. Before deploying, check:

- How long the credit is valid and which services are covered.
- Whether free services have monthly, quantity, or time limits.
- What happens when the credit expires or when the trial period ends.
- Whether the subscription automatically converts to paid pricing or requires user confirmation.

Do not treat the "Free" label as a guarantee that every resource in the subscription is free. A service may be free up to a threshold but billable beyond it; supporting resources such as disks, IP addresses, network traffic, or logs can also incur charges.

### Azure for Students and organization-provided subscriptions

Eligible learners can look into the Azure for Students program. If you are studying at a school or working at an enterprise, check whether your organization has already provided a subscription, tenant, and access permissions. Organization-managed subscriptions typically have policies on regions, service types, quotas, resource creation permissions, and budgets.

If using an organizational subscription:

1. Confirm this is a subscription designated for learning or development.
2. Ask the administrator about spending limits and permitted services.
3. Check the assigned RBAC role. Permission to read resources does not equate to permission to create, modify, or delete resources.
4. Do not create a new tenant or new billing registration yourself if the organization already has a provisioning process.

### Checking permissions before starting

You should have permission to sign into the tenant and permission to deploy the required resource types in the subscription. To create a resource group, an account typically needs appropriate permissions at the subscription or parent scope. To view costs and create budgets, the account also needs the corresponding Cost Management permissions; these may differ from resource deployment permissions.

Enable multi-factor authentication (MFA) if supported by the organization or account. Grant only the minimum permissions necessary for each user. Do not share passwords, verification codes, access tokens, or credentials of administrative accounts.

## 3. Choosing Tools to Access Azure

You can manage Azure using the web interface, a browser-based shell, or a command-line tool installed on your machine. These three approaches complement one another.

| Tool | When to use | Points to note |
|---|---|---|
| Azure Portal | Getting familiar with services, visual configuration, viewing charts and costs | Manual operations can easily target the wrong subscription if context is not checked |
| Azure Cloud Shell | Running commands from a browser without installing all tools locally | Requires sign-in; Cloud Shell storage may create or use a storage account |
| Azure CLI | Automating operations, repeating labs, and writing scripts | Requires installation, sign-in, and selecting the right subscription |

### Azure Portal

Open the [Azure Portal](https://portal.azure.com/) and sign in with an authorized account. In the subscription management section, identify the subscription to use and verify its status. Portal UI layouts may change across versions, but you can generally find services using the search bar at the top of the page.

Before creating resources, check the active subscription name and tenant. If there are multiple subscriptions, do not pick based on similar names; cross-check the subscription ID or information provided by your organization.

### Azure Cloud Shell

Cloud Shell is a command-line environment provided directly inside the Azure Portal. You can choose Bash or PowerShell. Azure CLI and many common administrative tools are preinstalled, making Cloud Shell convenient for short labs.

On first use, Cloud Shell may prompt you to set up storage to persist certain files and configurations. The storage account used for Cloud Shell can incur charges depending on configuration and usage. If the subscription has strict policies or you lack permission to create storage, ask an administrator or use a local Azure CLI.

### Azure CLI on a personal machine

Azure CLI is suitable when you want to save lab commands in scripts and run them repeatedly. Install it following the official guide for your operating system at [Install the Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli). After installation, open a new terminal and check the version:

~~~bash
az version
~~~

Sign in:

~~~bash
az login
~~~

If the environment cannot open a browser, you can use the device code sign-in flow when permitted by organizational policy:

~~~bash
az login --use-device-code
~~~

If you need to specify a tenant, use the tenant ID provided by your organization:

~~~bash
az login --tenant <TENANT_ID>
~~~

Do not put passwords, device codes, or tokens into scripts, shared documents, or repositories.

## 4. Verifying the Active Tenant and Subscription

After signing in, list the subscriptions the account can access:

~~~bash
az account list --output table
~~~

The output usually includes the subscription name, subscription ID, tenant ID, and state. If there are multiple subscriptions, select the right subscription by ID:

~~~bash
az account set --subscription "<SUBSCRIPTION_ID>"
~~~

Verify the current context again:

~~~bash
az account show --output table
~~~

You can also retrieve specific values for use in scripts:

~~~bash
az account show --query "{name:name, id:id, tenantId:tenantId, state:state}" --output json
~~~

Only proceed when the subscription is in an active state and matches the assigned environment. If you do not see the subscription, check the sign-in account, currently selected tenant, and granted permissions. Do not create a new subscription to bypass organizational access issues.

## 5. Creating a Dedicated Resource Group for Practice

You should create a separate resource group for each lab or group of lessons sharing the same lifecycle. When finished, you can inspect and clean up that lesson's resources within a clear scope.

### Choosing a name and region

A resource group name should describe its purpose and environment. For example:

- **rg-azure-lab-dev**: Azure labs in the development environment.
- **rg-azure-lab-network**: labs focused on networking.
- **rg-azure-lab-data**: labs focused on data.

Azure has different naming rules for each resource type. Check the specific service's rules before naming; not every service accepts the same character set.

A region is the geographic location where Azure deploys resources. Choose a region based on these factors:

- Whether the required services and SKUs are available in that region.
- Connection latency from the learner or consuming systems.
- Data residency requirements and organizational policies.
- Service pricing, quotas, and deployment availability in the subscription.

Not every service is available in every region. You can list the regions supported by your subscription using Azure CLI:

~~~bash
az account list-locations --output table
~~~

The example below uses **southeastasia** as an illustrative region. Replace it with a region permitted by your organization that offers the required services.

### Creating a resource group with Azure CLI

~~~bash
az group create --name rg-azure-lab-dev --location southeastasia --tags environment=learning owner=student purpose=azure-practice
~~~

In PowerShell, you can also run the command on a single line as in the example to avoid line-continuation character differences across shells.

View details of the newly created resource group:

~~~bash
az group show --name rg-azure-lab-dev --output table
~~~

Tags such as **environment**, **owner**, and **purpose** help identify intent and assist with cost filtering when services inherit or have matching tags applied. Tags do not create spending limits on their own and do not replace access permissions.

You can also create a resource group in the Azure Portal by searching for **Resource groups**, selecting **Create**, choosing the subscription, entering the name, region, and tags, and confirming. After creation, open the resource group to verify the subscription, region, and tags.

## 6. Setting a Budget Before Deploying Services

Azure bills based on service type, configuration, uptime, capacity, number of transactions, data transfer volume, and many other factors. A virtual machine does not just have compute costs: accompanying disks, IP addresses, backups, bandwidth, and monitoring services can also be billed.

Before creating resources, set a maximum budget you can accept for the practice period. For instance, you can use **10 USD/month** as an illustrative figure in the budget configuration exercise. This is not a price forecast or spending recommendation; choose an amount appropriate for your subscription, billing currency, and financial capacity.

### Estimating costs with Azure Pricing Calculator

Open the [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) and add the services you plan to use. For each service, determine:

- Region and service type or SKU.
- Size, quantity, and usage duration.
- Storage capacity, redundancy type, and expected transaction count.
- Inbound, outbound, and inter-region network traffic.
- Backup, security, support, and monitoring options.

A virtual machine running continuously can cost much more than one running for only a few hours, yet stopping a virtual machine does not necessarily eliminate all costs. Retained disks, IP addresses, snapshots, or network resources may continue to be billed. For services billed by transactions or capacity, also estimate usage outside active runtime hours.

Prices in the calculator are estimates based on the configuration and assumptions you enter. Actual bills also depend on usage, promotional programs, currency, taxes, contracts, and billing terms. Check your subscription's conditions before relying on free credits or free tier limits.

### Frequently overlooked cost categories

| Category | Example charges | How to control while learning |
|---|---|---|
| Compute | Virtual machine, container, app hosting, runtime hours | Choose an appropriately small SKU, schedule stop or delete when done |
| Storage | Disk, blob, file share, snapshot, backup | Provision only needed capacity, check copies and stored data |
| Network | Public IP, NAT Gateway, load balancer, VPN, egress | Avoid creating premium networking components unless required by the lesson |
| Database | Managed database, storage capacity, compute, and backup | Choose small tiers, limit runtime if supported by the service |
| Monitoring | Log Analytics ingestion, retention, metrics, and alerts | Collect only the log types needed to learn, check volume and retention |
| Security and governance | Certain protection services, key management, or support | Check pricing tables and free scopes before enabling |

Pay special attention to networking and monitoring resources. They can exist independently of the virtual machine or application you are testing, so simply shutting down the application does not guarantee all charges have stopped.

## 7. Creating a Budget and Cost Alerts

In Azure Cost Management, a **budget** sets a cost threshold for a scope and time period. When actual or forecasted costs reach an alert threshold, Azure can send notifications to configured recipients.

A budget is a tracking and alerting tool; a budget itself **is not a spending cap**. If 100% of the budget is reached, resources do not automatically stop solely because the threshold was crossed. Cost data also has latency, so notifications may arrive after usage has already increased. To respond automatically, you must design a separate workflow using appropriate automation or action groups, and test thoroughly to avoid impacting active resources.

### Configuring a budget in the Azure Portal

Item names and navigation locations may vary by UI and granted permissions. Typically, you can follow these steps:

1. Open **Cost Management + Billing** in the Azure Portal.
2. Select the correct billing scope or subscription to monitor.
3. Open **Cost Management** and select **Budgets**.
4. Create a new budget and select the scope. If studying in a dedicated resource group, select the resource group when the scope type and account permissions support it; otherwise, create the budget at the subscription level.
5. Give it an easily recognizable name, such as **budget-azure-lab-monthly**.
6. Select the **Monthly** reset period, and appropriate start and expiration dates.
7. Enter the budget amount in the currency displayed for that scope.
8. Add practical alert thresholds, such as 50%, 80%, and 100%.
9. Enter recipient email addresses for notifications. You can also configure an action group if required by your organization's workflow.
10. Review the scope, period, amount, and recipients before saving.

For example, if the illustrative budget is 10 USD/month, the 50%, 80%, and 100% thresholds correspond to 5 USD, 8 USD, and 10 USD. Choose alert thresholds early enough that you still have time to inspect and delete resources. If the scope uses a different currency, enter the amount in the currency displayed at that scope.

### Choosing the right scope

- **Subscription scope** tracks total costs across the subscription. This is suitable if the subscription is solely for you or a small study group.
- **Resource group scope** tracks the scope of a single lab. This option is useful when multiple different resource groups coexist in the subscription.
- **Management group or billing scope** may suit organizations managing multiple subscriptions, though permissions to create budgets at these scopes are usually controlled by governance teams.

Not every account has permission to view costs or create budgets. If you do not see Cost Management data or the button to create a budget, check the scope and Cost Management permissions with an administrator. Do not infer there are no costs simply because you cannot see the report.

### Reviewing costs periodically

After creating a budget:

- Open **Cost analysis** to view costs over time and by service category.
- Filter by subscription, resource group, service, or tags when those dimensions are available.
- Compare actual costs against forecasted costs and budget thresholds.
- Verify that alert recipients can receive the emails.
- Review running resources and any remaining supporting resources.

You should check costs after every lab session and before ending each study week. Do not wait until receiving a 100% alert to review resources.

## 8. Safe Practice Workflow for Every Lesson

Apply the following workflow every time you start an Azure lab:

1. **Confirm identity and subscription:** sign into the right account, tenant, and subscription.
2. **Read lesson requirements:** identify needed services, region, quota, and permissions.
3. **Estimate costs:** look up services in the Pricing Calculator and check free tier conditions if any.
4. **Choose tracking scope:** use a budget at the subscription or resource group level, depending on permissions and learning scope.
5. **Create a dedicated resource group:** attach tags to identify who owns it and what it is used for.
6. **Deploy minimally:** create only the resources needed for the learning goal, prioritizing appropriately small SKUs.
7. **Observe and record:** check status, logs, and costs during practice.
8. **Clean up:** delete unneeded resources and verify status after deletion.
9. **Recheck costs:** inspect remaining charges and handle any overlooked resources.

### Checking context via CLI

Before deploying, you can run these commands again:

~~~bash
az account show --output table
az group list --output table
~~~

If you need to inspect a resource group's tags:

~~~bash
az group show --name rg-azure-lab-dev --query "{name:name, location:location, tags:tags}" --output json
~~~

CLI commands only verify resource metadata; they do not replace checking budgets and cost reports in Cost Management.

## 9. Cleaning Up Resources After Practice

When the lesson ends, identify which resource groups were created solely for the lab. Before deleting, verify whether any resources or data need to be kept. Never delete shared resource groups or production environment resource groups.

If all resources in the group are strictly for the lab and safe to delete, run:

~~~bash
az group delete --name rg-azure-lab-dev --yes
~~~

The command above requests deletion of the resource group and the resources inside it. Deletion can take time. You can check whether the group still exists:

~~~bash
az group exists --name rg-azure-lab-dev
~~~

A **false** result indicates the resource group no longer exists. If the command returns **true**, check the deletion progress or any reported errors.

Deleting a resource group does not always eliminate every charge associated with the lesson. Also check:

- Resources created in another resource group or at the subscription level.
- Disks, snapshots, backups, images, or data retained under service policies.
- Storage accounts used for Cloud Shell.
- Logs, monitoring data, or services with separate retention policies.
- Resources with soft delete, retention, or locks preventing complete deletion.

After cleanup, open Cost analysis and monitor subsequent update cycles to catch any remaining charges. Some cost data updates with a delay; the disappearance of a resource group does not mean cost reports immediately drop to 0.

## 10. Protecting Your Account and Learning Environment

A good lab environment needs to be secure right from sign-in:

- Enable MFA and use an individual account for each learner.
- Use RBAC with least privilege; avoid using a Global Administrator account for routine deployment tasks.
- Do not store passwords, secrets, tokens, or access keys in source code or committed configuration files.
- Do not open public network ports or grant broad access unless required by the lesson.
- Use dedicated resource groups and tags to identify learning resources.
- Check policies, quotas, and region restrictions applied by the organization.
- Delete or revoke test credentials when no longer needed.

If automation with a service principal or managed identity is needed in later lessons, create an identity with appropriate minimal scope and permissions. Do not use personal user credentials as hardcoded secrets in scripts.

## 11. Troubleshooting Common Issues

| Symptom | Possible cause | Resolution |
|---|---|---|
| Sign-in succeeds but no subscription appears | Signed into wrong tenant, account not assigned to a subscription, or missing permissions | Check tenant ID, run **az account list**, and contact an administrator |
| **az group create** reports insufficient permissions | Missing permission to create resource groups at the subscription or parent scope | Verify subscription and request the appropriate RBAC role |
| Cannot create resources in chosen region | Service/SKU unavailable, insufficient quota, or policy blocks the region | Check supported regions, quotas, and policies; choose an allowed region |
| Cannot create a budget | Missing Cost Management permissions or at the wrong scope | Check billing scope, subscription, and Cost Management permissions |
| Not receiving budget alerts | Threshold not reached, wrong email, misconfigured notifications, or delayed cost data | Check budget configuration, recipients, and Cost analysis |
| Costs still appear after deleting a virtual machine | Disks, IPs, snapshots, backups, or supporting resources remain | Check the resource group, other groups, and service-level reports |
| Do not see costs immediately after creating resources | Cost Management data not yet updated | Check again later; do not treat an empty report as proof a service is free |

When encountering an error, save the error message, subscription name, resource group, and commands executed. Do not share tokens or sign-in credentials in bug reports.

## 12. Lab Exercise: Preparing an Azure Sandbox

The objective is to prepare a test scope that can be identified, monitored, and deleted. This exercise only creates a resource group; there is no need to deploy virtual machines or services that could incur significant charges.

### Prerequisites

- Access to an Azure subscription designated for learning or development.
- Ability to open the Azure Portal or use Azure CLI.
- Knowledge of the regions permitted in the subscription.

### Execution steps

1. Sign into the Azure Portal or run **az login**.
2. Run **az account list --output table**, select the right subscription, and verify with **az account show**.
3. Look up supported regions with **az account list-locations --output table**.
4. In Cost Management, create a budget at an appropriate scope. You can use 10 USD/month as an illustrative value if the subscription's currency and permissions allow.
5. Create alerts at 50%, 80%, and 100%; confirm the email recipients.
6. Create a resource group named **rg-azure-lab-dev**, in a permitted region, with tags **environment=learning**, **owner=student**, **purpose=azure-practice**.
7. Open the resource group in the Portal or run **az group show** to verify the name, region, and tags.
8. Delete the resource group with **az group delete --name rg-azure-lab-dev --yes**.
9. Run **az group exists --name rg-azure-lab-dev** to confirm the result.
10. Open Cost analysis and record the inspection time, scope, listed services, and any remaining charges if present.

### Results to record

| Item | Value to record |
|---|---|
| Tenant ID | Currently signed-in tenant |
| Subscription name and ID | Subscription used for the exercise |
| Region | Chosen region |
| Resource group | Group name and tags |
| Budget | Scope, period, amount, and alert thresholds |
| Cleanup | Deletion timestamp and **az group exists** output |
| Cost analysis | Report review time and observed charges |

### Self-check questions

1. What different aspects do a Microsoft Entra ID tenant and an Azure subscription manage?
2. Why is it necessary to run **az account show** before creating or deleting resources?
3. How does a resource group help manage the lifecycle of resources?
4. Does a budget automatically block deployments or stop resources when reaching 100%? Why or why not?
5. Name three charges that may continue to accrue after stopping a virtual machine.
6. Why should you check Cost analysis after deleting a resource group?

## 13. References

- [Azure Portal](https://portal.azure.com/) — management interface for Azure services.
- [Install the Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) — installing Azure CLI.
- [Azure Cloud Shell overview](https://learn.microsoft.com/azure/cloud-shell/overview) — how Cloud Shell works and its requirements.
- [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) — estimating costs by service configuration.
- [Create and manage budgets](https://learn.microsoft.com/azure/cost-management-billing/costs/tutorial-acm-create-budgets) — guide to creating and managing budgets.

Always cross-reference current documentation and pricing tables before deploying. Interfaces, promotional program names, free tier limits, and service prices may change over time, by region, and by billing agreement.
