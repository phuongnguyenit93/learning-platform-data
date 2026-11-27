# Preventing Accidental Actions with Resource Locks

In Azure, an accidental deletion can disrupt an application, lose configuration, or make data difficult to recover. Azure Resource Manager provides **resource locks** to restrict critical management operations at the subscription, resource group, or individual resource level. When placed at the right scope, locks prevent users from accidentally deleting or modifying critical resources, even when they have RBAC permissions for that operation.

This lesson belongs to the **Resource organization and governance** chapter of the **CLOUD_PROVIDERS_AZURE** module. The module explores the Microsoft Azure ecosystem from subscriptions, resource groups, and Microsoft Entra ID to virtual networks, compute services, storage, and data; while teaching how to deploy, monitor, protect, and control costs for an application architecture. Resource locks are one protection layer in resource lifecycle governance and must be coordinated with RBAC, Azure Policy, backups, and change processes.

After this lesson, you will be able to:

- Explain how resource locks protect resources at the Azure management layer.
- Distinguish between the two lock levels: **CanNotDelete** and **ReadOnly**.
- Choose the appropriate lock scope and predict inheritance effects on child resources.
- Create, list, inspect, and remove locks using the Azure Portal or Azure CLI.
- Handle scenarios involving deploying, updating, moving, or deleting locked resources.
- Combine locks with RBAC and other data protection measures.

## 1. What Problem Do Resource Locks Solve?

A resource lock is an Azure Resource Manager (ARM) management object used to restrict management operations on a locked scope. You can place locks at three primary scopes:

1. **Subscription:** protects multiple resource groups and resources within a subscription.
2. **Resource group:** protects the resource group and all resources inside it.
3. **Resource:** protects a specific resource, such as a storage account or virtual network.

For example, a development team might have Contributor permissions to deploy and update resources. If someone accidentally chooses to delete a storage account containing shared data, RBAC might allow that action. A **CanNotDelete** lock placed on the storage account blocks the deletion at the management layer until the lock is removed.

Resource locks are especially useful for:

- Resource groups holding resources shared by multiple teams.
- Storage accounts, databases, virtual networks, or critical platform services.
- Production environments or environments with hard-to-reproduce configurations.
- Resources that must remain intact during audits, operations, or system migrations.

A lock is a safeguard against accidental administrative actions. It does not back up data on its own, replace access permissions, or guarantee that all operations on data are blocked.

## 2. Two Types of Resource Locks

Azure Resource Manager provides two lock levels:

| Lock level | Read resource | Modify configuration | Delete resource |
|---|---|---|---|
| **CanNotDelete** | Allowed if RBAC permits | Allowed if RBAC permits | Blocked |
| **ReadOnly** | Allowed if RBAC permits | Blocked at management layer | Blocked |

### CanNotDelete

**CanNotDelete** allows users to continue reading and updating resources, but prevents deleting resources through Azure Resource Manager. This is usually the right choice when operations teams still need to change configurations while guarding against accidental deletion.

For example, a virtual network used by multiple applications may require planned subnet configuration changes. A **CanNotDelete** lock still permits RBAC-authorized update operations, while blocking requests to delete the virtual network.

### ReadOnly

**ReadOnly** allows reading resources while blocking both update and delete operations through Azure Resource Manager. This lock is stricter than **CanNotDelete** and must be applied carefully.

For example, after finalizing a resource group containing a read-only reference environment, an administrator can apply **ReadOnly** to prevent configuration changes outside approved workflows.

**ReadOnly** can disrupt operational actions in unexpected ways. Some management APIs use the POST method even when the intent is simply retrieving information, such as listing storage account access keys. A ReadOnly lock can block such calls. Test administrative tasks, automation, and application integrations before applying it broadly.

### Choosing a Lock Level by Goal

- Want to keep resources intact while still allowing updates: choose **CanNotDelete**.
- Want to block both updates and deletions through ARM during a stability freeze: consider **ReadOnly**.
- Only want to restrict one person or a group of people: review RBAC and approval processes; locks are not an identity-based authorization tool.

Locks do not grant extra permissions to users. If RBAC does not permit reading or updating, adding a lock will not make that action valid.

## 3. Scope and Inheritance Mechanism

A lock takes effect at the scope where it is created and is inherited by child resources within that scope. For example:

~~~text
Subscription: sub-production
    |
    +-- Resource group: rg-app-prod
    |       [CanNotDelete]
    |       |
    |       +-- Virtual network: vnet-app
    |       +-- Virtual machine: vm-app-01
    |       +-- Storage account: stappdata
    |
    +-- Resource group: rg-monitoring
            +-- Log Analytics workspace
~~~

In the diagram, the **CanNotDelete** lock on **rg-app-prod** protects the resource group and its contained resources from deletion via ARM. Resources in **rg-monitoring** are not affected by the lock on **rg-app-prod**.

### Which Scope Should You Lock?

| Scope | Impact radius | When appropriate |
|---|---|---|
| Subscription | Resource groups and resources in the subscription | Subscription dedicated to a critical environment needing broad protection |
| Resource group | The resource group itself and its child resources | An application or environment sharing a single lifecycle |
| Resource | Only the selected resource | Protecting a specific database, storage account, or individual platform component |

Locks at a parent scope remain in effect for child resources. If a resource group inherits **ReadOnly** from a subscription, adding **CanNotDelete** at the resource group does not restore update capability. You must handle the lock at the parent scope according to proper procedures and permissions.

Multiple locks can affect a single resource simultaneously. Evaluate all inherited and direct locks before concluding which operations are allowed. A more restrictive lock at any parent scope can still block an operation even if the resource's direct lock is less restrictive.

### Considerations When Choosing Scope

Locking at the subscription protects many resources but can easily interfere with routine deployments. Locking at the resource group aligns protection with an application's lifecycle. Locking an individual resource limits impact when only one component needs protection.

Before applying a lock at a broad scope, determine:

- Which teams and resources will inherit the lock.
- Whether deployment teams need to create, update, or delete resources in that scope.
- Whether CI/CD tooling, autoscaling, or managed services need to perform locked operations.
- Who holds permission to manage locks and the procedure for removing locks during emergency changes.

## 4. How Do Resource Locks and RBAC Work Together?

Azure RBAC determines **who is allowed to perform which action** on a scope. Resource locks determine **which management operations are restricted** at that scope. Both mechanisms work together.

| Scenario | RBAC | Resource lock | Outcome |
|---|---|---|---|
| User lacks delete permission, resource unlocked | Denies deletion | No lock | Cannot delete |
| User has delete permission, resource has **CanNotDelete** | Allows deletion | Blocks deletion | Cannot delete |
| User has update permission, resource has **ReadOnly** | Allows updates | Blocks updates via ARM | Cannot update |
| User has read permission, resource has **CanNotDelete** | Allows read | Does not block read | Can read |

To create or delete a management lock, the caller needs lock-management permissions at the corresponding scope, typically via the Owner or User Access Administrator role, or a custom role with the required lock management actions under **Microsoft.Authorization/locks**. The standard Contributor role does not implicitly include permissions to manage these locks.

This explains why someone can manage resources yet cannot remove a lock blocking an operation. In enterprise environments, reserving lock management permissions for an administrative group prevents deployers from removing safeguards themselves to complete a deletion.

## 5. Creating and Managing Locks with the Azure Portal

You can create locks at a subscription, a resource group, or an individual resource's management page.

### Create a Lock for a Resource Group

1. Open the [Azure Portal](https://portal.azure.com/) and sign in with an account having appropriate permissions.
2. Search for **Resource groups** and open the resource group to protect.
3. Under **Settings**, open **Locks**. Menu names or locations may vary by Portal version.
4. Select **Add**.
5. Enter a descriptive name, such as **lock-protect-rg-app-prod**.
6. Choose **Delete** corresponding to **CanNotDelete**, or **Read-only** corresponding to **ReadOnly**.
7. Add notes explaining the lock rationale and accountable team if the interface supports it.
8. Save the lock, then check the Locks list to confirm it appears at the right scope.

### Inspect Locks on a Resource

Open the target resource and inspect **Locks**. If an operation is blocked, check both direct locks on the resource and locks inherited from the resource group or subscription. Checking only the resource's page is sometimes insufficient to understand the full protection scope.

### Remove a Lock in the Portal

1. Open the exact scope where the lock was created.
2. Go to **Settings > Locks**.
3. Select the lock to remove and verify its name, lock type, scope, and change justification.
4. Delete the lock using an account with lock-management permissions.
5. Perform the approved change.
6. Recreate the lock if the resource still needs protection.

You cannot remove an inherited lock by trying to delete it at a child resource. Locate the exact scope where the lock was created and handle it there.

## 6. Creating and Managing Locks with Azure CLI

Azure CLI provides the **az lock** command group to manage resource locks. Before running commands, sign in and verify the subscription:

~~~bash
az login
az account show --output table
~~~

If the account has multiple subscriptions, select the right one:

~~~bash
az account set --subscription "<SUBSCRIPTION_ID>"
az account show --output table
~~~

### Create CanNotDelete on a Resource Group

Suppose the resource group to protect is **rg-app-prod**:

~~~bash
az lock create --name lock-protect-rg-app-prod --lock-type CanNotDelete --resource-group rg-app-prod --notes "Prevent accidental deletion of production app resources"
~~~

The **--lock-type** parameter accepts **CanNotDelete** or **ReadOnly**. The lock name should convey its purpose and scope for operators.

### List and View Lock Details

~~~bash
az lock list --resource-group rg-app-prod --output table
~~~

To view details of a specific lock:

~~~bash
az lock show --name lock-protect-rg-app-prod --resource-group rg-app-prod --output json
~~~

Inspect attributes such as lock name, lock level, notes, and scope. If an operation remains blocked after creating or removing a lock, check locks at the subscription and parent scopes as well.

### Create a Lock on a Specific Resource

For example, lock a specific storage account:

~~~bash
az lock create --name lock-protect-storage --lock-type CanNotDelete --resource-group rg-app-prod --resource-name stappdata --resource-type Microsoft.Storage/storageAccounts --notes "Protect shared storage account"
~~~

When locking a specific resource, provide the exact resource group, resource name, and resource type. For resources with compound names or nested resource types, confirm the resource ID and provider syntax before creating the lock.

### Remove a Lock

If the lock was created at the resource group level, remove it with:

~~~bash
az lock delete --name lock-protect-rg-app-prod --resource-group rg-app-prod
~~~

If the lock was created at the resource level, specify the exact resource identifiers:

~~~bash
az lock delete --name lock-protect-storage --resource-group rg-app-prod --resource-name stappdata --resource-type Microsoft.Storage/storageAccounts
~~~

After removal, list locks again to confirm. If locks share the same name across multiple scopes, do not rely on the name alone; target the exact scope or resource ID.

### Lock at the Subscription Level

To protect an entire subscription from deletion operations, you can create a lock at the subscription scope:

~~~bash
az lock create --name lock-protect-subscription --lock-type CanNotDelete --scope "/subscriptions/<SUBSCRIPTION_ID>" --notes "Prevent accidental deletion of resources in subscription"
~~~

Subscription-level locks can affect multiple teams and deployment workflows. Use them only when subscription scope is agreed upon with operations teams and backed by clear lock management procedures.

## 7. Impacts to Check Before Applying

Resource locks protect operations on the **management plane** (the resource management layer through Azure Resource Manager). Locks are not a mechanism to control all data operations inside a service.

For example, **CanNotDelete** on a storage account blocks deleting the storage account itself via ARM, but does not prevent an application or user with data-plane permissions from deleting blobs inside. Similarly, locking a resource group does not replace database or storage data-protection mechanisms.

Before placing locks in an operational environment, evaluate:

- **Deployments:** do templates, pipelines, or IaC tools need to create, modify, or delete resources in that scope?
- **Autoscaling:** does the service need to create or delete instances, NICs, disks, or auxiliary components?
- **Integrations:** which application management operations call APIs affected by **ReadOnly**?
- **Moves:** moving resources between resource groups or subscriptions can be blocked by locks on either the source or destination.
- **Lifecycle cleanup:** test environment teardown workflows may fail to finish if the resource group or resources remain locked.
- **Data operations:** data reads/writes require RBAC and dedicated data protection mechanisms, which cannot be inferred from resource locks.

A **ReadOnly** lock at the subscription can block creating new resource groups or resources in that scope. A **CanNotDelete** lock on a resource group still permits updates, while blocking deletion of the group or child resources. Therefore, do not apply **ReadOnly** broadly just to guard against accidental deletion.

## 8. Resource Locks Do Not Replace Other Protections

To protect an Azure application, combine multiple layers of control:

| Mechanism | Primary purpose | Usage example |
|---|---|---|
| Azure RBAC | Restrict identities and allowed actions | Only the admin group has permission to delete resource groups |
| Resource lock | Block deletion or updates on the management plane | **CanNotDelete** on critical databases |
| Azure Policy | Enforce and evaluate deployment rules | Allow only approved regions or SKUs |
| Backup and recovery | Recover data after errors or deletion | Database backups, VM restoration |
| Soft delete or immutable storage | Protect data from deletion or modification per service policy | Retain deleted blobs or lock immutable storage policies |
| Change process | Control requests, approvals, and change timing | Change ticket to remove lock before maintenance |

Resource locks do not create data copies and do not guarantee application recoverability. For critical data, configure backups, retention, soft delete, or immutable storage suited to the service and recovery objectives.

## 9. Safe Lock Operations Workflow

A lock management workflow should clearly define purpose, ownership, and removal steps:

1. **Classify resources:** identify critical resources and the consequences if deleted or modified by mistake.
2. **Choose the smallest scope meeting the goal:** prefer resource or resource group locks when full-subscription protection is unnecessary.
3. **Select the lock level:** use **CanNotDelete** to prevent deletion; only use **ReadOnly** when blocking updates is genuinely required.
4. **Assess impact:** review pipelines, autoscaling, management APIs, backup workflows, moves, and cleanup jobs.
5. **Name and document notes:** record purpose, owner, ticket, or related procedure if applicable.
6. **Verify after creation:** check scope, lock type, inheritance, and lock listing.
7. **Review periodically:** confirm locks remain appropriate, owners are current, and no obsolete locks linger.
8. **Remove locks under control:** record justification, approver, and timestamp; remove only necessary locks.
9. **Restore protection:** after changes finish, recreate the lock and verify it is active.

Resource locks do not expire automatically. If a lock is only needed temporarily, record its planned end date and include lock review/removal in operational procedures. Never let temporary locks become permanent unowned configurations.

## 10. Troubleshooting Common Issues

| Symptom | Possible cause | How to resolve |
|---|---|---|
| Cannot delete resource despite Owner permissions | Resource has a **CanNotDelete** or **ReadOnly** lock | Check Locks on the resource, resource group, and subscription; remove at the right scope if approved |
| Cannot update configuration | Direct or inherited **ReadOnly** lock exists | Identify the lock causing the block; assess required action before removing |
| Cannot create new resources in resource group | Resource group or subscription has a **ReadOnly** lock | Inspect parent scopes and coordinate with the lock management team |
| Removed lock on resource but operation still blocked | Lock is inherited from resource group or subscription | List locks at each parent scope and re-verify |
| Contributor cannot remove lock | Contributor lacks required lock management permissions | Request Owner, User Access Administrator, or a custom role holder to act |
| App cannot read access keys after ReadOnly lock | Management API using POST is blocked | Check API method and consider changing lock level or authentication design |
| Deployment pipeline fails when deleting or replacing resources | Lock blocks IaC or lifecycle action | Identify exact blocked operation; design approved lock-removal and re-locking steps |
| Cannot move resources | Lock on source or destination scope blocks move | Inspect both scopes, plan temporary lock removal, and verify after move |

When troubleshooting, record the resource ID, denied operation, error code, and inspected scopes. Never bulk-remove locks just to test whether an operation works.

## 11. Hands-On Lab: Protecting an Application Resource Group

In this exercise, you will create a **CanNotDelete** lock on a test resource group, inspect the lock, and remove it. Use a permitted learning subscription or sandbox environment. Never run commands on shared or production resource groups without approval.

### Preparation

- Sign in to Azure CLI and select the right subscription.
- Have a test resource group named **rg-lock-lab**.
- Have permissions to create and delete resource locks at the resource group scope.

If the test resource group does not exist yet, create a dedicated one:

~~~bash
az group create --name rg-lock-lab --location southeastasia --tags environment=learning purpose=resource-lock-lab
~~~

Replace the region with one permitted in your subscription.

### Create and Verify the Lock

Create a delete-prevention lock:

~~~bash
az lock create --name lock-protect-rg-lock-lab --lock-type CanNotDelete --resource-group rg-lock-lab --notes "Resource lock lab exercise"
~~~

List locks:

~~~bash
az lock list --resource-group rg-lock-lab --output table
~~~

View details:

~~~bash
az lock show --name lock-protect-rg-lock-lab --resource-group rg-lock-lab --output json
~~~

Compare the lock type, name, and scope against what you created.

### Observe Impact and Clean Up

1. Open the resource group in the Azure Portal and confirm the lock appears under **Settings > Locks**.
2. Try deleting the resource group from the Portal in the lab environment. The delete request must be blocked by the **CanNotDelete** lock.
3. There is no need to create billable resources to test this behavior; the test resource group is sufficient to observe locking of group deletion.
4. Remove the lock with:

~~~bash
az lock delete --name lock-protect-rg-lock-lab --resource-group rg-lock-lab
~~~

5. Re-run the listing command to confirm the lock is gone:

~~~bash
az lock list --resource-group rg-lock-lab --output table
~~~

6. If the group was only for this exercise and is no longer needed, delete the resource group:

~~~bash
az group delete --name rg-lock-lab --yes
~~~

### Results to Record

| Item | Value to record |
|---|---|
| Subscription | Name and ID of subscription used for lab |
| Resource group | **rg-lock-lab** |
| Lock name | **lock-protect-rg-lock-lab** |
| Lock level | **CanNotDelete** |
| Scope | Resource group |
| Verification | Lock listing output and observed blocked deletion |
| Cleanup | Result after removing lock and deleting resource group |

### Self-Check Questions

1. How do **CanNotDelete** and **ReadOnly** differ?
2. If **CanNotDelete** is placed on a resource group, how are child resources affected?
3. Why might a user with Owner permissions still be unable to delete a locked resource?
4. Why do resource locks not replace backups or immutable storage?
5. How can a **ReadOnly** lock at the subscription affect deployment pipelines?
6. If you remove a lock directly on a resource and the action is still blocked, which scopes should you check?

## 12. References

- [Lock your resources to protect your infrastructure](https://learn.microsoft.com/azure/azure-resource-manager/management/lock-resources) — concepts, scopes, and how resource locks work.
- [Azure CLI: az lock](https://learn.microsoft.com/cli/azure/lock) — commands to create, list, show, and delete locks.
- [Azure role-based access control (Azure RBAC)](https://learn.microsoft.com/azure/role-based-access-control/overview) — authorization model in Azure.
- [Azure Policy documentation](https://learn.microsoft.com/azure/governance/policy/overview) — resource policy governance and enforcement.

Portal section names, command syntax, and individual service behaviors can vary across versions. In real environments, consult current documentation, verify permissions, and test lock impacts in a non-critical environment first.
