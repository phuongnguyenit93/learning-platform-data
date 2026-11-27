# Installing Azure CLI and Managing Sign-In Sessions

Azure CLI is a command-line tool for working with Microsoft Azure services. After installing and signing in, you can use the `az` command to view subscriptions, select a working environment, manage resource groups, and deploy infrastructure. This lesson focuses on two foundational tasks: preparing Azure CLI on your machine and accurately controlling the active identity and subscription.

In the **CLOUD_PROVIDERS_AZURE** ecosystem, Azure CLI is an essential administrative tool alongside the Azure Portal, Azure Cloud Shell, and automated deployment tools. It enables you to perform repeatable tasks via commands, save them as scripts, and integrate them into CI/CD pipelines.

## 1. Understanding Context Before Signing In

There are several Azure concepts to distinguish:

| Concept | Role |
|---|---|
| Microsoft Entra tenant | Identity directory containing users, groups, applications, and access policies |
| Azure subscription | Scope for managing resources, access permissions, and billing |
| Resource group | Logical grouping containing related Azure resources |
| Azure CLI | Tool that sends management requests to Azure using the `az` command |

One user can be granted permissions across multiple subscriptions, including subscriptions belonging to different tenants. Therefore, signing in successfully is not enough to guarantee that subsequent commands run against the right environment. You need to verify the currently selected tenant and subscription before creating, modifying, or deleting resources.

Azure CLI also does not grant permissions on its own. Permission to perform an operation is still controlled by Azure role-based access control (Azure RBAC), organizational policies, and identity protection mechanisms in Microsoft Entra ID.

## 2. Preparing Before Installation

You need:

- A computer with permissions to install software or use the operating system's package manager.
- An Internet connection to download Azure CLI and authenticate with Azure.
- A Microsoft Entra account permitted to access the target tenant or subscription.
- Appropriate Azure permissions for the intended operations. For example, subscription read permission is sufficient to view metadata; creating a resource group requires corresponding write permissions.

If your organization requires multi-factor authentication (MFA), prepare your registered authentication method. Some organizations also enforce Conditional Access, device restrictions, or sign-in location policies; these policies remain in effect when you use Azure CLI.

## 3. Installing Azure CLI

Choose the installation method appropriate for your operating system. Use official installation sources or your system's trusted package manager.

### Windows

On Windows 10 or Windows 11 with Windows Package Manager (winget), open PowerShell or Windows Terminal and run:

```powershell
winget install --exact --id Microsoft.AzureCLI
```

You can also use Microsoft's MSI installer if your computer environment does not use winget. After installation completes, close and reopen the terminal so the operating system reloads the program path.

### macOS

If Homebrew is installed on the machine, run:

```bash
brew update
brew install azure-cli
```

If Azure CLI was already installed via Homebrew, you can update it with:

```bash
brew update
brew upgrade azure-cli
```

### Ubuntu and Debian

For Ubuntu or Debian, Microsoft provides an Azure CLI installation script to configure the package repository and install the CLI:

```bash
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
```

This command requires an Internet connection and `sudo` privileges. For other Linux distributions, select the corresponding installation guide in the official Azure CLI documentation; do not assume Debian packages fit every distribution.

### Verifying the installation

Open a new terminal and run:

```bash
az version
```

The command returns Azure CLI version details and related components. If the terminal reports that `az` is not found, check the installation process, open a new terminal, and confirm the installation directory is in the `PATH` environment variable.

You can update Azure CLI with:

```bash
az upgrade
```

If your operating system or corporate policy manages versions through a package manager, follow that update mechanism.

## 4. Signing In to Azure with a User Account

On a machine with a browser, the standard way to sign in is:

```bash
az login
```

Azure CLI opens a browser for you to pick an account and complete the Microsoft Entra ID authentication flow. If your organization requires MFA or additional verification steps, complete them in the browser.

After signing in, the CLI displays information about the subscriptions the account can access. This output helps you see which environments are available, but you should not rely on the display order to guess the default subscription.

### Signing in when a browser cannot be opened

On a remote server, a terminal without a graphical interface, or an environment that cannot automatically launch a browser, use device code:

```bash
az login --use-device-code
```

The CLI will display the verification page URL and a one-time code. Open the indicated page in an accessible browser, enter the code, and confirm sign-in. Do not share the verification code with others; this code is part of the sign-in flow.

### Specifying a tenant when signing in

If the account belongs to multiple tenants or you need to access a specific tenant, pass the tenant ID:

```bash
az login --tenant "<TENANT_ID>"
```

Replace `<TENANT_ID>` with the Microsoft Entra tenant ID provided by your organization. You can also use the tenant domain name if appropriate for your organization's setup, though the tenant ID is usually clearer in scripts or runbooks.

Signing into a tenant only establishes the identity context. You still need to select an accessible subscription before performing operations on resources.

## 5. Viewing and Selecting the Active Subscription

This is the most important step to avoid operating on the wrong environment.

List the subscriptions the CLI recognizes:

```bash
az account list --output table
```

The table output usually includes the subscription name, subscription ID, tenant ID, state, and default subscription indicator. Use the subscription ID when precise selection is needed, especially when multiple subscriptions have similar names.

View the current context:

```bash
az account show --output json
```

Set the subscription to work with:

```bash
az account set --subscription "<SUBSCRIPTION_ID_OR_NAME>"
```

Then verify again:

```bash
az account show --query "{subscription:name, subscriptionId:id, tenant:tenantId, state:state}" --output json
```

The `az account set` command changes the default subscription Azure CLI uses for subsequent commands. It does not create a subscription, grant additional permissions, or alter user permissions.

**Safe habit:** before running commands that create, modify, or delete resources, run `az account show` and verify both the subscription ID and tenant ID. In critical scripts, you can pass the `--subscription` parameter directly to commands that support it to state the execution scope explicitly.

## 6. Confirming Access Permissions

After selecting a subscription, you can test a simple read operation:

```bash
az group list --output table
```

If the command returns a list of resource groups, the current identity can read that list in the selected subscription. If the list is empty, the subscription may not have any resource groups yet or your access scope does not expose any resources.

If you receive an authorization error, check in order:

1. Is the selected subscription correct?
2. Is the signed-in tenant the one hosting that subscription?
3. Has the account been granted an appropriate Azure RBAC role at the subscription or resource group level?
4. Is a Conditional Access policy or organizational policy blocking the operation?

Signing in successfully only proves the CLI has authenticated the identity. It does not prove that identity has permission to read or modify every resource.

## 7. Working with Different Identity Types

### User accounts

Interactive sign-in with `az login` is suitable for direct engineer operations. Users can complete MFA and verification steps required by the organization. Personal accounts should not be used as the identity running long-term automated tasks.

### Service principals

A service principal represents an application or workload in Microsoft Entra ID. It is commonly used in pipelines or automated tasks when a workload needs an application identity.

Sign-in command format using a client secret:

```bash
az login --service-principal \
  --username "<APPLICATION_CLIENT_ID>" \
  --password "<CLIENT_SECRET>" \
  --tenant "<TENANT_ID>"
```

Values inside angle brackets are placeholders, not usable credentials. Never place real client secrets into source code, committed config files, logs, or shared command history. When designing automated systems, prefer workload identity federation or certificates if supported by the platform; if a secret must be used, store it in a protected secret store, restrict access, and rotate it per policy.

A service principal can only perform actions it is granted permission for. Assign the minimum required role at the necessary scope rather than defaulting to Owner across the entire subscription.

### Managed identities

When an application runs on an Azure resource with managed identity enabled and appropriately authorized, it can sign in without storing a client secret:

```bash
az login --identity
```

For a user-assigned managed identity, you can specify the client ID:

```bash
az login --identity --client-id "<MANAGED_IDENTITY_CLIENT_ID>"
```

These commands only work inside an Azure environment that has the corresponding managed identity. Running them on a personal computer without a managed identity will not automatically create an Azure identity.

**Choosing the right method:** use user accounts for interactive operations; use service principals or workload identity federation for pipelines; use managed identities for workloads running on Azure when supported by the architecture.

## 8. Signing Out and Refreshing Local Context

When finishing a session on a shared machine or needing to switch accounts, run:

```bash
az logout
```

Without arguments, the command signs out all accounts logged into the Azure CLI cache. If you only want to sign out one account, pass the `--username` option with that account's sign-in name.

When the subscription list in the local cache is outdated or needs refreshing, use:

```bash
az account clear
```

This command clears subscription data from the local Azure CLI cache. Afterward, sign in again so the CLI reloads account and subscription details:

```bash
az login
az account list --output table
```

The two commands serve different purposes: `az logout` handles authentication state; `az account clear` clears the local subscription cache. They do not delete Azure resources and do not cancel subscriptions on the Azure platform.

## 9. Useful Options When Using the CLI

### Choosing output formats

Azure CLI supports multiple output formats. For example:

```bash
az account list --output table
az account list --output json
az account list --output yaml
```

- `table` is easy to read during manual work.
- `json` is convenient for programs or data processing tools.
- `yaml` is useful when a human-readable format is needed in certain configuration workflows.
- `tsv` suits scripts that need tab-separated fields.
- `none` suppresses output when results do not need to be displayed.

You can configure a default output format for the CLI:

```bash
az config set core.output=table
```

You can still override the format for individual commands using `--output`.

### Filtering data with --query

The `--query` option uses JMESPath to select fields or filter results. For example, retrieving the names and IDs of subscriptions:

```bash
az account list --query "[].{name:name, id:id, tenant:tenantId}" --output table
```

When writing scripts, filter only the fields you need and verify actual output. Never include access tokens, client secrets, or authentication data in outputs merely for debugging convenience.

## 10. Troubleshooting Common Errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| `az` command not found | CLI not installed, terminal has not reloaded PATH, or installation failed | Open a new terminal, check installation and PATH, then rerun `az version` |
| Browser does not open during sign-in | Server has no GUI or remote terminal session | Use `az login --use-device-code` |
| Desired subscription not visible | Signed into wrong tenant, account lacks permissions, or subscription unavailable | Use `az login --tenant "<TENANT_ID>"`, check `az account list`, and confirm permissions with an administrator |
| Command reports AuthorizationFailed | Identity is authenticated but lacks permissions for the action or resource scope | Check the subscription, tenant, and required Azure RBAC role |
| Operating on the wrong subscription | CLI holds a different default subscription than intended | Stop immediately, run `az account show`, then reselect using `az account set` |
| Sign-in session no longer valid | Token expired, authentication policy changed, or session requires re-verification | Run `az login` again and complete the required verification steps |

When encountering an error, read the full message and determine whether the error belongs to installation, authentication, subscription selection, or authorization. Do not repeat a command that writes or deletes resources before confirming the root cause.

## 11. Security and Operational Principles

- Verify the tenant and subscription before any operation affecting infrastructure.
- Comply with your organization's MFA and Conditional Access policies.
- Use Azure RBAC with least privilege; separate read, deployment, and administrative permissions where appropriate.
- Do not share an active signed-in terminal session or the Azure CLI authentication cache directory.
- Do not place access tokens, client secrets, or device login codes into Git, public tickets, screenshots, or logs.
- Use managed identities or workload identity federation for workloads whenever possible; manage secret and certificate lifecycles under security procedures when they are required.
- For scripts with destructive actions, require environment and resource scope confirmation before execution.

These principles are especially important when a development machine is used to access multiple subscriptions or when Azure CLI commands are integrated into automated pipelines.

## 12. Lab Exercise

Perform the following steps on a test subscription you are permitted to access:

1. Install Azure CLI and confirm the version with `az version`.
2. Sign in with `az login`; if using a machine without a browser, switch to `az login --use-device-code`.
3. Run `az account list --output table` and identify the subscription to use.
4. Select the subscription with `az account set --subscription "<SUBSCRIPTION_ID>"`.
5. Run `az account show` to verify the subscription ID and tenant ID.
6. Run `az group list --output table` to confirm read permission for resource groups.
7. Sign out with `az logout` when finished.

**Completion criteria:** you can explain how a tenant and a subscription differ, install Azure CLI, sign in using an appropriate method, select the right subscription, and verify context before working with resources.

## Conclusion

Azure CLI provides a consistent command-line interface for managing Azure. A safe workflow starts with installing the right version, authenticating with an appropriate identity, verifying the tenant and subscription, and only then performing operations on resources. Once you master `az login`, `az account list`, `az account show`, `az account set`, and `az logout`, you have the foundation needed to continue learning how to manage resource groups, networking, compute, storage, and data on Microsoft Azure.
