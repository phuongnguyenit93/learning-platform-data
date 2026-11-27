# Previewing Infrastructure Changes with ARM `what-if`

## 1. Why Preview Infrastructure Changes?

In **Infrastructure as Code (IaC)**, we describe desired infrastructure in code instead of manually editing each resource in the Azure Portal. On Microsoft Azure, resources such as resource groups, virtual networks, storage accounts, VMs, App Services, and security configurations can be declared using **ARM templates** (JSON) or **Bicep** (which compiles to ARM templates).

Suppose an operations team updates a Storage Account from allowing legacy TLS to requiring TLS 1.2 only. A small edit in Bicep can affect existing client applications. Even worse, changing a deployment scope or using an unintended deployment mode can predict resource deletion. Therefore, before applying IaC, we need to know **what Azure expects to create, modify, or delete**.

**ARM `what-if`** is a change-preview operation provided by Azure Resource Manager. It compares the live state of existing resources against the state declared in your template and parameters, returning the projected differences **without deploying any resources**. It can be invoked via Azure CLI, Azure PowerShell, or tools calling the ARM deployment API.

Across the Azure learning track—from subscriptions, resource groups, networking, compute, and storage to security and cost control—`what-if` acts as a vital safeguard before applying infrastructure through CI/CD. It brings impact analysis into code review, testing, and change approval workflows.

After this lesson, you will be able to:

- Explain the difference between **template validation**, **`what-if`**, and **deployment**.
- Run `what-if` with Bicep/ARM templates at resource group scope and recognize how to invoke it at other scopes.
- Analyze **Create, Modify, Delete, NoChange** results along with cases that cannot be predicted with certainty.
- Distinguish the effects of **Incremental** and **Complete** modes, avoiding confusing an omitted declaration with resource deletion.
- Integrate `what-if` output into pull requests, Azure Pipelines, and pre-deployment approval gates.
- Recognize `what-if` limitations and how to verify live state post-deployment.

## 2. How Does ARM `what-if` Work?

Azure Resource Manager (ARM) is the orchestration layer for deploying Azure resources. Given a template and parameters, ARM identifies the target resources, their desired state, and existing resources within the target scope. `what-if` executes the diff analysis phase prior to actual deployment.

~~~mermaid
flowchart TD
    A["Bicep / ARM template"] --> C["ARM what-if"]
    B["Parameters + subscription + scope"] --> C
    D["Current live resource state in Azure"] --> C
    C --> E["Projected result: Create / Modify / Delete / NoChange / other"]
    E --> F{"Evaluate changes"}
    F -->|"Not ready"| G["Adjust template, parameters, or scope"]
    G --> C
    F -->|"Ready + approved"| H["ARM deployment"]
    H --> I["Verify live state after deploy"]
~~~

Key takeaways:

- **`what-if` is a point-in-time prediction.** It calls Azure to read and analyze current state, without creating, modifying, or deleting target resources declared in the template.
- **`what-if` is not a resource lock or a binding plan.** Between preview and deployment, live resources can be altered by users, automation, or another service.
- **`what-if` does not replace application testing.** An API, networking, or permission change may be reported as `Modify` yet still break production workloads if operational impact is not evaluated.
- **`what-if` does not approve changes on its own.** A zero exit code merely indicates the analysis command ran cleanly, even if the output predicts deleting critical resources.

### Comparing Three Common Steps

| Step | Question Answered | Creates or Modifies Resources? | Azure CLI Example |
| --- | --- | --- | --- |
| Template validation | Are declarations valid structurally, in parameters, and in supported checks? | No | `az deployment group validate` |
| `what-if` | Given current Azure state, what changes does the deployment predict? | No | `az deployment group what-if` |
| Deploy | Applies the declared infrastructure state to Azure | Possibly yes | `az deployment group create` |

Passing validation **does not** mean a deployment won't disrupt a system. Nor does `what-if` replace validation—the two steps provide complementary checks.

## 3. Reading Change Types in the Output

ARM `what-if` generally returns the following change types (exact formatting and detail vary by tool version, resource type, and output format):

| Change Type | Practical Meaning | How to Evaluate |
| --- | --- | --- |
| **Create** | Resource is declared and expected to be newly created | Verify name, region, SKU, cost, permissions, networking, and quota |
| **Modify** | Existing resource is projected to change at least one property | Inspect every before/after property; assess downtime, permission, or security impact |
| **Delete** | Resource within the analyzed scope may be deleted under deployment semantics | Stop to verify scope, mode, data, backups, dependencies, and approval authority |
| **NoChange** | Engine predicts no differences to display | Still verify app health and factors beyond preview prediction |
| **Ignore / Deploy / Unsupported** | Results outside the four types above, often due to scope or evaluation/provider limits | Read the explanation and tool docs; never assume it means safe or fully known |

A `what-if` output can include the resource ID, `changeType`, before/after payloads, and a list of differing fields depending on the format. Illustrative example of how to read it:

~~~text
~ Microsoft.Storage/storageAccounts/stiacdemo12345
  ~ tags.costCenter:
      before: "trial"
      after:  "platform"
  ~ properties.minimumTlsVersion:
      before: "TLS1_0"
      after:  "TLS1_2"
~~~

This is an **illustration**, not verbatim output from a specific Azure CLI version. The `~` symbol denotes modification in this example. When running it for real, read the exact resource IDs, property names, and before/after values in your own output.

**Do not merely count `Modify` entries.** A change to `tags` has a completely different impact than modifying `networkAcls`, `publicNetworkAccess`, `identity`, `sku`, `subnets`, or `ipSecurityRestrictions`. Examine the substance and scope of every change.

## 4. Preparing the Practice Environment

The example below targets a **Storage Account** inside a **resource group**. You need:

1. An Azure subscription and permissions to read/analyze deployments at the target scope. Appropriate ARM and resource provider permissions are required; exact roles vary by deployment and organization.
2. Azure CLI with Bicep support, signed in with an authorized user, service principal, or workload identity.
3. A test resource group. Avoid testing `Complete` mode directly against a resource group holding important resources.
4. Templates and parameters stored in version control so changes are reviewed via pull requests.

The following commands assume you are signed in and know the exact target subscription:

~~~bash
# Check the currently selected account and subscription.
az account show --query "{name:name,id:id,tenantId:tenantId}" -o table

# Select the right subscription before any operation.
az account set --subscription "<subscription-id>"

# Example: create a lab resource group if missing (this ACTUALLY creates a resource group).
az group create --name rg-iac-whatif-dev --location southeastasia
~~~

Only the **`what-if`** command is a preview. `az group create` in setup modifies live resources; clearly separate initial lab provisioning from non-mutating preview steps.

### 4.1 Writing the Bicep Template

Assume `infra/main.bicep` is saved as:

~~~bicep
@description('Storage Account name must be globally unique across Azure, 3-24 lowercase letters/digits.')
@minLength(3)
@maxLength(24)
param storageAccountName string

@description('Deployment location for the Storage Account.')
param location string = resourceGroup().location

@allowed([
  'dev'
  'test'
  'prod'
])
param environment string = 'dev'

param costCenter string

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  tags: {
    environment: environment
    costCenter: costCenter
  }
  properties: {
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
  }
}

output storageAccountId string = storage.id
~~~

This template declares desired state: a `StorageV2` Storage Account with LRS redundancy, HTTPS-only enforced, minimum TLS 1.2, and public blob access disabled. Because resource names must be **globally unique**, the name in this lesson is illustrative and must be replaced with an available valid name.

Save parameter file `infra/parameters/dev.parameters.json`:

~~~json
{
  "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#",
  "contentVersion": "1.0.0.0",
  "parameters": {
    "storageAccountName": {
      "value": "stwhatifdemo12345"
    },
    "environment": {
      "value": "dev"
    },
    "costCenter": {
      "value": "platform"
    }
  }
}
~~~

`location` is omitted so Bicep defaults to the resource group's region. In real environments, follow organizational naming rules and separate parameter files per environment; **never place plaintext passwords, access keys, or secrets** into committed JSON files.

## 5. Running ARM `what-if` with Azure CLI

### 5.1 Validate First, `what-if` Second

From the repository root, run:

~~~bash
az deployment group validate \
  --resource-group rg-iac-whatif-dev \
  --template-file infra/main.bicep \
  --parameters @infra/parameters/dev.parameters.json

az deployment group what-if \
  --resource-group rg-iac-whatif-dev \
  --template-file infra/main.bicep \
  --parameters @infra/parameters/dev.parameters.json \
  --mode Incremental \
  --result-format FullResourcePayloads
~~~

The `what-if` command asks Azure to preview changes for the supplied parameters; it **does not** create the Storage Account. If the resource does not yet exist, expect **Create**. If it already exists in a matching state, expect **NoChange**.

`FullResourcePayloads` returns full details so you can inspect property-level diffs. If you only want to know which resource IDs are affected, consider `--result-format ResourceIdOnly`; however, summary-only output is insufficient for reviewing security settings or high-risk changes.

### 5.2 Adjusting a Property and Reviewing the Diff

Suppose the Storage Account was previously deployed from an earlier template version where `costCenter` was `trial`. Now update the parameter to `platform` and re-run `what-if`.

The projected result will show **Modify**, pinpointing the change in `tags.costCenter`. If you also update `minimumTlsVersion`, `what-if` surfaces that diff too. Reviewers should verify:

- Does the change target the right resource and subscription?
- Are there any unexpected changes to location, name, SKU, replication, network access, or identity?
- Do client applications support the new configuration?
- Are security sign-off, maintenance windows, notifications, or rollback plans needed?

Only deploy once the review passes:

~~~bash
az deployment group create \
  --resource-group rg-iac-whatif-dev \
  --template-file infra/main.bicep \
  --parameters @infra/parameters/dev.parameters.json \
  --mode Incremental
~~~

**Caution:** This is a **real deployment command**. Run it strictly after approval. ARM `what-if` cannot tell you whether a change causes service disruption, and some diffs appear solely because the API/provider normalizes properties.

### 5.3 Interactive Confirmation Option

Azure CLI supports previewing `what-if` and prompting for immediate confirmation on certain deployment commands using `--confirm-with-what-if`:

~~~bash
# For interactive operators reviewing and confirming before deployment.
az deployment group create \
  --resource-group rg-iac-whatif-dev \
  --template-file infra/main.bicep \
  --parameters @infra/parameters/dev.parameters.json \
  --confirm-with-what-if
~~~

This option works well when an operator reads output at a terminal. In non-interactive pipelines, run a **dedicated `what-if` step**, publish the output to authorized reviewers, and enforce an explicit approval gate before the deployment step.

## 6. How Deployment Mode Alters Result Interpretation

In resource-group-scoped ARM deployments, **Incremental** and **Complete** carry critical differences:

| Mode | General Interpretation | Consequence When Existing Resources Are Absent from Template |
| --- | --- | --- |
| **Incremental** | Applies changes to declared resources; typically the default choice | Generally preserves resources outside the template, subject to resource and child-property semantics; absence from the template does not imply deleting everything else |
| **Complete** | Treats the entire resource group as managed by the deployment under its rules | Undeclared resources may be projected for **Delete**; review carefully and avoid running casually on shared resource groups |

Thus, if you delete a resource block from `main.bicep` while using `--mode Incremental`, **do not expect** Azure to delete that live resource. Conversely, running `Complete` on a resource group containing unmanaged resources can trigger a wave of `Delete` predictions.

**Preview-only example**—do not execute deploy:

~~~bash
# Analyze impact only when switching to Complete mode.
az deployment group what-if \
  --resource-group rg-iac-whatif-dev \
  --template-file infra/main.bicep \
  --parameters @infra/parameters/dev.parameters.json \
  --mode Complete
~~~

Never treat `Complete` as a default cleanup tool. For controlled lifecycle and deletion management, investigate **Azure Deployment Stacks** and explicit resource ownership policies. Deletion behavior and APIs vary across resource types, parent/child resources, nested deployments, and tool versions. **A `Delete` in `what-if` is a signal to investigate thoroughly**, never something to approve blindly.

## 7. Limitations to Understand Before Approving

### 7.1 Predicted Results Can Differ from Actual Changes

ARM `what-if` relies on how each Resource Provider models resources and how ARM resolves expressions. Some provider-returned values are normalized, server-computed, or formatted differently from declared inputs. Deployment-time expressions (such as certain uses of `reference()`), read-only fields, or complex provider schemas can introduce **noise**, false positives, or incomplete diffs.

Therefore:

- If `Modify` appears repeatedly with no template edits, compare the flagged properties against provider-returned state, `apiVersion`, and template expressions.
- If `Ignore`, `Deploy`, or `Unsupported` appears, investigate the cause and add supplementary checks; never treat them as `NoChange`.
- With Bicep modules, nested deployments, or extension resources, examine the **actual deployment scope** and inner resources; a high-level summary alone is not enough to assess risk.
- If a template declares `existing` resources, remember these reference pre-existing resources—they are **not requests to redeploy** them.

### 7.2 Not All Operational Consequences Are Predicted

A `Modify` result does not tell you whether an operation triggers a restart, changes an endpoint, briefly drops connections, or breaks an application dependency. Quota limits, Azure Policy, RBAC, live resource state, regional capacity, or subscription limits can still cause a deployment to fail even after `what-if` succeeds.

Nor is `what-if` a cost estimator. If you plan to add VMs or upgrade SKUs, evaluate **regional pricing, consumption, quotas, and budgets** with dedicated cost tools—never infer exact billing from the number of `Create` or `Modify` entries.

### 7.3 Access Permissions and Sensitive Data

Although `what-if` is read-only/preview, it still requires authentication and appropriate permissions on both the deployment and the evaluated resources. Never bypass RBAC boundaries just because a command does not deploy. `what-if` output can expose configuration metadata, resource IDs, resource names, and property values—restrict access to logs and build artifacts accordingly.

For sensitive values, use secure parameters, Azure Key Vault, managed identities, or pipeline secret injection; never print secrets in outputs or attach them to public reports. Even when tooling attempts to mask sensitive values, **that does not replace securing logs and artifacts**.

### 7.4 Gap Between Preview and Deployment

There is no built-in mechanism locking a `what-if` preview into an immutable "frozen plan" artifact. If someone edits a resource in the Portal after your preview runs, the earlier diff no longer reflects live state. For critical changes, re-run `what-if` close to deployment and require re-approval if the diff changes.

Aim to preview and deploy **the exact same commit, parameters, scope, and mode**—and still verify live state afterward.

## 8. Integrating into Pull Requests and Azure Pipelines

A sound IaC workflow for engineering teams:

1. Author modifies Bicep, ARM templates, or parameters on a feature branch and opens a pull request.
2. CI runs syntax/quality checks, validation, and `what-if` against an appropriate test scope.
3. Reviewers compare `what-if` output against the change request, focusing on `Delete` entries and security/network/identity/SKU edits.
4. Protected branches and environment approval gates govern when deployment runs.
5. Post-deploy, the pipeline verifies resource status, monitors health/metrics/logs, and records the deployment alongside the applied commit.

~~~mermaid
flowchart LR
    PR["Pull request"] --> CI["Validate + What-if"]
    CI --> R{"Review diff"}
    R -->|"Needs fixes"| PR
    R -->|"Approved"| A["Merge + approval gate"]
    A --> DEP["Deploy ARM/Bicep"]
    DEP --> OBS["Verify + monitor"]
~~~

### 8.1 Azure Pipelines YAML Example

Here is a two-stage example using **`AzureCLI@2`**. Assume the repository already contains `infra/main.bicep` and `infra/parameters/dev.parameters.json` from above, and service connection `sc-azure-infra-dev` is configured for the right subscription. The `azure-iac-dev` environment must have **Approvals and checks** configured in Azure DevOps when human sign-off is required: declaring `environment` in YAML does not create approvals on its own.

~~~yaml
# azure-pipelines.yml
trigger:
  - main

# For Azure Repos Git, use Branch Policies -> Build validation for PRs.
pool:
  vmImage: ubuntu-latest

variables:
  azureServiceConnection: 'sc-azure-infra-dev'
  targetResourceGroup: 'rg-iac-whatif-dev'
  templatePath: 'infra/main.bicep'
  parametersPath: 'infra/parameters/dev.parameters.json'

stages:
  - stage: Preview
    displayName: 'Preview projected infrastructure'
    jobs:
      - job: WhatIf
        steps:
          - checkout: self
          - task: AzureCLI@2
            displayName: 'Validate and ARM what-if'
            inputs:
              azureSubscription: 'sc-azure-infra-dev'
              scriptType: bash
              scriptLocation: inlineScript
              inlineScript: |
                set -euo pipefail
                az deployment group validate \
                  --resource-group "$(targetResourceGroup)" \
                  --template-file "$(templatePath)" \
                  --parameters @"$(parametersPath)"
                az deployment group what-if \
                  --resource-group "$(targetResourceGroup)" \
                  --template-file "$(templatePath)" \
                  --parameters @"$(parametersPath)" \
                  --mode Incremental \
                  --result-format FullResourcePayloads

  - stage: Deploy
    displayName: 'Apply after approval'
    dependsOn: Preview
    condition: succeeded()
    jobs:
      - deployment: Apply
        environment: 'azure-iac-dev'
        strategy:
          runOnce:
            deploy:
              steps:
                - checkout: self
                - task: AzureCLI@2
                  displayName: 'Apply same commit and parameters'
                  inputs:
                    azureSubscription: 'sc-azure-infra-dev'
                    scriptType: bash
                    scriptLocation: inlineScript
                    inlineScript: |
                      set -euo pipefail
                      az deployment group create \
                        --resource-group "$(targetResourceGroup)" \
                        --template-file "$(templatePath)" \
                        --parameters @"$(parametersPath)" \
                        --mode Incremental
~~~

**Safety notes on this example:**

- Both stages run within the same pipeline using the exact commit that triggered the run. Keep template and parameter versions immutable throughout review and deployment.
- The `Preview` stage fails if validate or `what-if` exits with an error. However, **a successful `what-if` can still predict `Delete`**. To block deletions automatically, parse **structured output** or enforce a policy gate—`condition: succeeded()` alone is not enough.
- The `Deploy` stage is a **deployment job** bound to `azure-iac-dev`. Approvals are configured under Azure DevOps Environments and must actually be set up before treating this as an approval gate.
- Service connections should follow least privilege and run only on trusted branches/jobs. Never grant deployment credentials to workflows executing untrusted PR code. Consider separating preview and deploy service connections with distinct permissions.
- For production, add branch protection, mandatory reviewers, change summaries, preview freshness checks, and post-deployment monitoring.

### 8.2 Automatically Blocking `Delete` Requires Parsing JSON

For organizations enforcing "allow deploy only when zero resources are deleted", parse **machine-readable output** rather than grepping colored terminal text. Have Azure CLI output JSON:

~~~bash
az deployment group what-if \
  --resource-group rg-iac-whatif-dev \
  --template-file infra/main.bicep \
  --parameters @infra/parameters/dev.parameters.json \
  --mode Incremental \
  --output json > whatif.json
~~~

In ARM `what-if` responses, changes are typically represented under `changes`, each with a `changeType`. Below is an **abbreviated JSON structure for illustration**, not every possible response shape:

~~~json
{
  "changes": [
    {
      "resourceId": "/subscriptions/.../resourceGroups/rg-iac-whatif-dev/providers/Microsoft.Storage/storageAccounts/stwhatifdemo12345",
      "changeType": "Modify"
    }
  ]
}
~~~

When implementing automated policy checks, verify the exact schema for your CLI/API version; if fields are missing, parsing fails, or the format is unexpected, **fail closed** instead of assuming "zero deletes". For example, on JSON containing a `changes` array as shown, the following `jq` check validates the minimal schema and blocks any `changeType == "Delete"`:

~~~bash
set -euo pipefail
jq -e '(.changes | type) == "array" and
       all(.changes[]; (.changeType | type) == "string")' whatif.json >/dev/null

delete_count=$(jq '[.changes[] | select(.changeType == "Delete")] | length' whatif.json)
if [ "$delete_count" -gt 0 ]; then
  echo "ARM what-if predicts deleting $delete_count resource(s); review required."
  exit 1
fi
~~~

This is only a **sample policy** blocking deletions; it does not yet inspect public network exposure, RBAC changes, SKU downgrades, or cost risks. For production, add checks for critical properties, allowed scopes, and approved exceptions. Also restrict read access and retention on `whatif.json` to prevent leaking infrastructure configuration.

## 9. Other Deployment Scopes

ARM/Bicep supports **resource group**, **subscription**, **management group**, and **tenant** deployment scopes. `what-if` must be invoked at the scope matching your template. A Bicep file declaring `targetScope = 'subscription'` should not be passed to `az deployment group what-if` expecting Azure to switch scopes automatically.

For example, a subscription-scoped template creating a resource group uses the `sub` command group along with `--location` for the deployment record:

~~~bash
az deployment sub what-if \
  --location southeastasia \
  --template-file infra/subscription.bicep \
  --parameters @infra/parameters/sub.parameters.json
~~~

Similarly, `az deployment mg ...` and `az deployment tenant ...` exist for their respective scopes and permissions. When working at broader scopes:

- Double-check the subscription ID, tenant ID, or management group ID before running.
- Inspect modules deploying resources into scopes different from the parent deployment, as supported by Bicep/ARM.
- Enforce stricter approvals on policies, role assignments, or cross-subscription changes.
- Never assume a preview in one subscription guarantees identical behavior in another; each environment has different live state and permissions.

## 10. Troubleshooting Errors and Unexpected Results

| Symptom | Possible Cause | Remediation |
| --- | --- | --- |
| Cannot run `what-if` due to authorization error | Wrong subscription, expired token, or missing deployment/provider permissions | Check `az account show`, scope, service connection, and RBAC; never grant Owner casually |
| Template validation fails | Bicep syntax error, missing/mismatched parameter, invalid resource ID or API version | Fix template/parameters and re-run validate before `what-if` |
| Numerous `Modify` results with no code edits | Provider-normalized defaults, dynamic expressions, read-only fields, or ARM comparison behavior | Inspect exact property deltas; check API/provider behavior and filter known noise carefully—never ignore all `Modify` |
| Unexpected `Delete` appears | Wrong scope, `Complete` mode, template missing existing resources, or conditional flags | Stop; verify template, mode, resource group, dependent resources, and owners |
| `what-if` reports no changes, yet app fails post-deploy | Runtime side effects, out-of-template config, post-preview drift, or provider limits | Check logs, metrics, health, deployment history, and app config; never treat `NoChange` as end-to-end testing |
| `what-if` predicts `Create`, yet deployment fails | Globally taken name, quota, Azure Policy, unsupported region/SKU, or resource lock | Read resource provider error and environment limits, adjust configuration, and re-run |
| Missing diff details needed for review | Summary output format used or preview truncated | Switch to full payload format and inspect warnings; add manual review for critical resources |

When unexpected results occur, retain at least the **commit SHA**, **template/parameters**, **scope**, **mode**, tool versions, timestamp, and sanitized `what-if` output. These records make it possible to compare the preview against the actual deployment during incident investigations.

## 11. Hands-On Exercises and Self-Check Questions

### Exercise 1: Create and Then Modify a Test Resource

1. Create a dedicated lab resource group; set `storageAccountName` in parameters to a unique name.
2. Run `az deployment group validate` followed by `az deployment group what-if`; confirm the resource projected for **Create**.
3. Deploy to the lab resource group if authorized and ready to provision resources; then re-run `what-if` with the unchanged template.
4. Update `costCenter` and run `what-if`; locate the property projected for **Modify**.
5. Change `minimumTlsVersion` or `publicNetworkAccess` in an appropriate test environment, inspect the diff, and explain its security impact before deciding whether to deploy.

**Expected outcome:** you observe the difference between initial state, post-deployment state, and parameter-change diffs, seeing how a small code edit can carry major operational significance.

### Exercise 2: Assessing Deletion Risk

Suppose resource group `rg-shared` contains two resources, `A` and `B`, while the template declares only `A`. Predict:

- Under `Incremental`, what typically happens when `B` is omitted?
- Under `Complete`, how might `B` be projected for handling?
- If `Delete` appears on `B`, what details must you confirm before permitting deployment?

**Suggested answer:** `Incremental` generally preserves `B` despite its omission; `Complete` may project `Delete` under its semantics. Stop immediately to verify scope/mode, owner, data, backups, dependencies, change request, and approvals. Never run a `Complete` deployment on `rg-shared` just to test a hypothesis.

### Self-Check Questions

1. How does ARM `what-if` differ from `az deployment group validate`?
2. Why isn't an exit code of `0` from `what-if` enough to approve a change for deployment?
3. What causes `Modify` results to reappear even when nobody edited Bicep?
4. Why doesn't using the exact same commit, template, and parameters guarantee the preview matches the subsequent deployment 100%?
5. Should a workflow triggered by a forked pull request be allowed to use a service connection with production write permissions? Explain.
6. When `Delete` or major changes to networking, RBAC, Key Vault, or storage appear, who should be involved in the review and what evidence is required?

**Key takeaway:** ARM `what-if` makes code-driven infrastructure changes observable and reviewable before execution. The safe workflow is **validate → `what-if` → impact assessment → approval → deploy → verify**, under strictly controlled scope, parameters, and deployment mode. Preview output is evidence to guide decisions—not an absolute guarantee of real-world outcomes.
