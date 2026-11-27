# Designing Custom Roles and Enforcing Least Privilege

In Microsoft Azure, resource access permissions are primarily managed using Azure role-based access control (Azure RBAC). When built-in roles do not accurately describe a team's job function, you can create a custom role to grant only the necessary operations at a specific scope.

Role design is a key part of Azure resource governance. An application architecture may consist of subscriptions, resource groups, virtual networks, virtual machines, storage accounts, and databases. If every member has Contributor permissions across the entire subscription, a single operational mistake can affect multiple workloads. When permissions are scoped by task, boundary, and duration, each person can only perform the duties assigned to them.

This lesson focuses on custom roles in Azure RBAC within the Microsoft Azure ecosystem. You will learn how to analyze operations, design role definitions, choose scopes, assign roles to users/groups/workload identities, verify effective permissions, and maintain least privilege over time.

After this lesson, you will be able to:

- Distinguish security principal, role definition, role assignment, and scope.
- Explain the Actions, NotActions, DataActions, NotDataActions, and AssignableScopes fields.
- Determine when to use a built-in role and when a custom role is needed.
- Design task-based custom roles that separate resource management permissions from data access permissions.
- Create, assign, inspect, update, and remove custom roles using Azure CLI.
- Apply the principle of least privilege, group-based assignments, managed identities, and time-bound access.

## 1. Azure RBAC and the Components of Access Permissions

Azure RBAC determines who can perform which operations on Azure resources and at what scope. Effective access is typically formed from four components:

| Component | Meaning | Example |
|---|---|---|
| Security principal | Identity receiving permissions | User, group, service principal, or managed identity |
| Role definition | Collection of allowed operations | Reader, Contributor, or custom role VM Operator |
| Scope | Resource boundary where permissions apply | Management group, subscription, resource group, or single resource |
| Role assignment | Binding of principal, role, and scope | Assigning VM Operator to the operations group on the app resource group |

A role assignment can be represented as:

~~~text
Principal + Role definition + Scope = Role assignment
~~~

For example: the **grp-orders-operators** group is assigned the custom role **Orders VM Operator** at the **rg-orders-prod** resource group. Group members can perform the operations allowed by the role on resources within that scope and applicable child resources.

### 1.1. Distinguishing Azure RBAC from Microsoft Entra Roles

Microsoft Entra ID manages identities, groups, applications, and authentication. Entra directory roles such as User Administrator or Global Administrator manage identity directory objects and capabilities.

Azure RBAC manages permissions on Azure resources such as virtual machines, networks, storage accounts, databases, and resource groups. For example:

- User Administrator can manage certain user objects in the tenant.
- Reader on a subscription can view management information for resources in the subscription.
- Storage Blob Data Reader can read blob data within the assigned scope.
- A custom role VM Operator can allow reading, starting, and deallocating VMs within the designated scope.

Certain high-level Entra roles can have capabilities to administer Azure permissions, but the two role systems should not be treated as one. When designing permissions, clearly distinguish whether the work involves managing identities or managing Azure resources.

### 1.2. Role Definition vs. Role Assignment

A role definition describes a set of operations. By itself, a role definition does not grant permissions to anyone.

A role assignment is what grants a role to a principal at a specific scope. The same custom role can be assigned to multiple groups or workload identities at different scopes, provided those scopes fall within the role definition's allowed range.

For example:

- Role definition: **Orders VM Operator**.
- Principal: **grp-orders-operators** group.
- Scope: **/subscriptions/<subscription-id>/resourceGroups/rg-orders-prod**.

If the role definition only allows reading, starting, and deallocating VMs, group members do not automatically gain permissions to create virtual networks, assign roles to others, or read blob data.

## 2. Understanding the Structure of a Custom Role

An Azure RBAC custom role has the following key properties:

| Property | Purpose |
|---|---|
| Name | Human-readable name of the role |
| Id | Unique identifier of the role; created or managed by Azure |
| IsCustom | Indicates this is a custom role |
| Description | Describes the task and usage boundaries |
| Actions | Allowed management-plane operations |
| NotActions | Operations excluded from this role definition's Actions set |
| DataActions | Allowed data-plane operations |
| NotDataActions | Operations excluded from this role definition's DataActions set |
| AssignableScopes | Scopes where this role definition can be assigned |

### 2.1. Actions: Resource Management Operations

Actions contain management-plane operations, such as reading VM configuration, starting a VM, creating a resource, or modifying network settings.

An operation typically takes the form:

~~~text
Microsoft.<Provider>/<resource-type>/<operation>
~~~

Examples:

- **Microsoft.Compute/virtualMachines/read**: read VM management information.
- **Microsoft.Compute/virtualMachines/start/action**: start a VM.
- **Microsoft.Compute/virtualMachines/deallocate/action**: deallocate a VM.
- **Microsoft.Network/virtualNetworks/read**: read virtual network management information.

Operation names must come from the corresponding resource provider. Never guess operation names based on Portal button labels or CLI command names.

### 2.2. DataActions: Operations on Data

DataActions describe permissions to access data inside a service. For example, reading blobs, writing data to a container, or accessing content in a service that supports the Azure RBAC data plane.

Reading a storage account's configuration and reading blob contents are two distinct permissions:

- **Microsoft.Storage/storageAccounts/read** is a storage account management operation.
- Reading blob contents requires appropriate data-plane permissions, such as the built-in Storage Blob Data Reader role.

Therefore, someone who only needs to inspect storage account settings does not necessarily need to read the data inside. Conversely, an application that needs to read blobs should typically receive data-plane permissions only on the specific storage account or container it uses.

Not every Azure service models data permissions via DataActions in the same way. Check the documentation and role operations for the exact service before designing.

### 2.3. NotActions and NotDataActions Are Not Deny Rules

This point must be understood accurately. NotActions removes certain operations from a single role definition's Actions set. NotDataActions removes operations from that role definition's DataActions set.

They do not create an independent deny rule. Azure RBAC aggregates permissions from all active role assignments. If a principal is assigned another role that grants an operation excluded by NotActions, the principal can still perform that operation via the other role assignment.

For example:

- Role A allows all virtual machine operations under Microsoft.Compute.
- NotActions in Role A excludes **Microsoft.Compute/virtualMachines/delete/action**.
- The principal is also assigned Role B, which grants permission to delete VMs.

The principal can still have delete permission through Role B. Therefore, do not use NotActions as a deny mechanism or to override permissions granted by another role.

If the goal is to disallow a specific configuration, redesign the role assignments, use Azure Policy for appropriate configuration rules, or use Azure-managed deny assignments in supported scenarios. Azure Policy does not replace all data access control functions.

### 2.4. Limiting Wildcards

Wildcards such as an asterisk (*) or an entire Microsoft.Compute namespace can grant more operations than the task actually requires. They also make the role harder to evaluate when resource providers add new operations.

Prefer listing explicit operations. Only use wildcards when a broad scope is an intentional requirement, has been reviewed, and has an assigned owner responsible for maintenance.

### 2.5. AssignableScopes and Role Assignment Scope

These two concepts are related but not identical:

- AssignableScopes defines where the role definition can be used to create role assignments. Custom roles are typically defined at a management group or subscription scope.
- The scope in a role assignment defines the actual resources where the principal receives permissions.

For example, a custom role whose AssignableScopes is a subscription can be assigned at a resource group inside that subscription. Assigning at the resource group helps limit permissions to the right application or environment.

Common scope paths:

~~~text
/                                    Root scope
/providers/Microsoft.Management/managementGroups/<management-group-id>
/subscriptions/<subscription-id>
/subscriptions/<subscription-id>/resourceGroups/<resource-group-name>
/subscriptions/<subscription-id>/resourceGroups/<resource-group-name>/providers/<provider>/<type>/<resource-name>
~~~

Role assignments at a parent scope are typically inherited down to child scopes. Therefore, assigning a role at the subscription has a broader blast radius than assigning it at a single resource group or resource.

## 3. Process for Designing Least-Privilege Custom Roles

Least privilege means a principal only receives the operations required for its task, at the required scope, and for the required duration. To achieve this, follow the process below.

### Step 1: Describe the Task in Concrete Actions

Start from the job function, not from the role name. For example, an on-call operator needs to:

- View virtual machine status and configuration.
- Start virtual machines when requested.
- Deallocate virtual machines when reducing costs.
- Not create or delete virtual machines.
- Not modify networking, firewalls, or role assignments.
- Not access data inside storage accounts.

The more concrete the description, the easier it is to translate into operations and test.

### Step 2: Check Built-In Roles First

Azure provides many Microsoft-maintained built-in roles. Look for a suitable built-in role before creating a custom role.

| Built-in role | Typical purpose |
|---|---|
| Reader | View resource management information |
| Contributor | Manage most resources without granting Azure RBAC permissions themselves |
| Owner | Manage resources and grant access permissions |
| Virtual Machine Contributor | Manage virtual machines per operations defined in the role |
| Storage Blob Data Reader | Read blob data within the assigned scope |

For example, if the task only requires reading blob data, consider Storage Blob Data Reader instead of granting Contributor on the storage account. If a built-in role already fits the task and scope, a custom role adds management overhead without clear benefit.

### Step 3: Look Up Resource Provider Operations

Azure CLI can list operations published by a resource provider:

~~~bash
# List Microsoft.Compute operations
az provider operation list \
  --namespace Microsoft.Compute \
  --output table

# List Microsoft.Storage operations
az provider operation list \
  --namespace Microsoft.Storage \
  --output table
~~~

Match operations to each task. Pay attention to distinguishing read operations, state-changing actions, delete operations, and data operations. Operation names, supported conditions, and impacts can vary by service or API.

Do not copy all operations of a provider into a role just because a team works with that provider. Select only the exact operations the task requires.

### Step 4: Choose the Smallest Reasonable Scope

Select the scope matching the boundary of responsibility:

- Resource: when the task involves only one specific resource.
- Resource group: when the team is responsible for resources belonging to one application or environment.
- Subscription: when the task applies across multiple resource groups in a subscription.
- Management group: when a governance team must perform the same task across multiple subscriptions.

The higher the scope, the more resources inherit the permissions. Avoid assigning at the management group or subscription just because assigning once feels more convenient.

### Step 5: Choose the Right Principal

Prefer assigning roles to Entra groups rather than repeatedly assigning to individuals. When members change, administrators can update group membership without creating or deleting dozens of role assignments.

For applications or services, prefer managed identities where supported by the service. Managed identities let workloads authenticate to Azure without storing a long-lived client secret in source code or configuration.

Only grant permissions to principals that genuinely need to perform the task. Do not share one account across multiple unrelated applications or job functions.

### Step 6: Define Duration and Verification

Sensitive administrative permissions should be granted only for as long as needed. For privileged roles, you can use Microsoft Entra Privileged Identity Management (PIM) for Azure resources to manage eligible access, time-bound activation, and additional controls where appropriate for your organization's setup.

After assigning, inspect effective permissions, test allowed operations using the recipient's identity, and confirm out-of-scope operations are denied. Testing should be conducted in a safe environment with test data and resources.

## 4. Example: Custom Role Allowing Only VM Operations

Suppose the Orders application has a production resource group named **rg-orders-prod**. The operations team needs to view VM information, start, and deallocate VMs. They must not create or delete VMs, modify networking, or read application data.

### 4.1. Identify Required Permissions

| Task | Required operation |
|---|---|
| View VM information | **Microsoft.Compute/virtualMachines/read** |
| Start VM | **Microsoft.Compute/virtualMachines/start/action** |
| Deallocate VM | **Microsoft.Compute/virtualMachines/deallocate/action** |
| Delete VM | Not granted |
| Modify VM configuration | Not granted |
| Grant roles to others | Not granted |
| Read blob data | No DataActions granted |

This example illustrates a minimal role for direct operations on VMs. If the team needs to use the Azure Portal to view additional status or related resources, extra read permissions may be needed. Identify missing operations through practical testing and add only necessary read permissions.

### 4.2. Create the Role Definition File

Create **vm-operator-role.json**:

~~~json
{
  "Name": "Orders VM Operator",
  "IsCustom": true,
  "Description": "Allows viewing, starting, and deallocating VMs within the assigned role scope.",
  "Actions": [
    "Microsoft.Compute/virtualMachines/read",
    "Microsoft.Compute/virtualMachines/start/action",
    "Microsoft.Compute/virtualMachines/deallocate/action"
  ],
  "NotActions": [],
  "DataActions": [],
  "NotDataActions": [],
  "AssignableScopes": [
    "/subscriptions/<subscription-id>"
  ]
}
~~~

Replace **<subscription-id>** with the actual subscription ID. This example puts only VM management operations into Actions. Do not add data read or write permissions to DataActions because the task does not require data access.

The role description should clearly state who uses it, what they can do, and the intended scope. Clear names and descriptions help administrators evaluate role assignments in the future.

### 4.3. Create the Custom Role

Sign in and verify the current subscription before creating the role:

~~~bash
az login
az account show --output table
az account set --subscription "<subscription-id>"
~~~

Create the role definition from the JSON file:

~~~bash
az role definition create \
  --role-definition ./vm-operator-role.json
~~~

Verify the newly created role:

~~~bash
az role definition list \
  --name "Orders VM Operator" \
  --output json
~~~

If the create command fails with an invalid operation or AssignableScopes error, verify the selected subscription, JSON format, operation names, and scope. Do not broaden to wildcards just to make role creation succeed.

### 4.4. Assign the Role to a Group at the Resource Group

The role definition is declared for use within the subscription, but the operations team only needs permissions on the production resource group.

~~~bash
az role assignment create \
  --assignee-object-id "<group-object-id>" \
  --assignee-principal-type Group \
  --role "Orders VM Operator" \
  --scope "/subscriptions/<subscription-id>/resourceGroups/rg-orders-prod"
~~~

Replace **<group-object-id>** with the Microsoft Entra group's object ID. Using the object ID unambiguously identifies the principal receiving permissions.

Do not assign the role at the subscription if the team is only responsible for **rg-orders-prod**. When a role assignment is placed at the resource group, permissions inherit down to child resources within the appropriate scope.

### 4.5. Verify Role Assignments

List role assignments on the resource group, including inherited permissions:

~~~bash
az role assignment list \
  --scope "/subscriptions/<subscription-id>/resourceGroups/rg-orders-prod" \
  --include-inherited \
  --all \
  --output table
~~~

You can inspect the role definition to confirm the declared operations:

~~~bash
az role definition list \
  --name "Orders VM Operator" \
  --output json
~~~

Evaluate both direct and inherited permissions. A principal can receive permissions from multiple role assignments, multiple groups, or parent scopes. Therefore, reading a single custom role alone is not enough to determine a user's effective permissions.

### 4.6. Task-Based Testing

Use a test account that is a member of the operations group. Verify these scenarios:

| Test action | Expected result |
|---|---|
| View VM information in the assigned resource group | Allowed if required read operations are included |
| Start a test VM | Allowed |
| Deallocate a test VM | Allowed |
| Delete a VM | Denied unless another role grants permission |
| Create a virtual network | Denied unless another role grants permission |
| Grant roles to another user | Denied unless another role grants permission |
| Read blob data | Denied unless another data-plane role grants permission |

Expected results only hold if the principal receives no extra permissions from other role assignments. If an action that should be blocked still succeeds, check direct role assignments, inherited permissions from resource group/subscription/management group, and groups the principal belongs to.

If an allowed action is denied, check the operation name, scope, resource provider, role assignment status, and propagation delay. Some role assignment changes can take time to take effect.

## 5. Enforcing Least Privilege Across the Organization

Custom roles are only one part of access governance. A sound operating model combines role design, principal selection, scope, duration, and monitoring.

### 5.1. Separation of Duties

Do not bundle every task into one large role. For example, you can separate:

| Duty group | Appropriate permission |
|---|---|
| View inventory and configuration | Reader at the scope requiring visibility |
| Operate VMs | Custom VM Operator or appropriate built-in role |
| Read blobs | Storage Blob Data Reader on storage account/container |
| Deploy infrastructure | Deployment role scoped to resource group or pipeline identity |
| Manage access | Role-assignment management role reserved for an authorized team |

Infrastructure deployers do not necessarily need permission to read all application data. Data readers do not necessarily need permission to edit storage account configurations. Access administrators should also not simultaneously be the application runtime principal without a clear operational reason.

### 5.2. Assigning Permissions to Groups and Managed Identities

For staff, use groups aligned to duties or responsibilities. For example:

- **grp-orders-readers**: view management information for the Orders application.
- **grp-orders-operators**: operate VMs under the custom role.
- **grp-orders-data-readers**: read blob data within approved scopes.

For workloads, use a managed identity attached to the application or service. Assign roles to the managed identity at the scope the workload needs to access. Avoid embedding personal account credentials into pipelines or applications.

Do not share one managed identity across multiple unrelated workloads if doing so expands permission scope or makes accountability tracking difficult.

### 5.3. Using PIM for Privileged Permissions

Some tasks only require elevated privileges briefly, such as incident response or performing production changes. PIM for Azure resources can help:

- Assign permissions in an eligible state for users to activate when needed.
- Limit activation duration.
- Require justification or approval depending on policy.
- Record activation history for auditing.

PIM must be configured and meet your organization's licensing requirements. Avoid granting permanent Owner or User Access Administrator to every team member simply for convenience.

### 5.4. Using Azure Policy for Configuration Rules

Azure RBAC determines which operations a principal can invoke. Azure Policy evaluates and enforces rules on resource configurations, such as:

- Allowing deployments only in approved regions.
- Requiring resources to have owner and environment tags.
- Controlling public network access configurations per policy.
- Auditing SKUs or configurations permitted by the organization.

Azure Policy and Azure RBAC complement each other. Policy is not a replacement for role assignments to grant blob read access or VM start permissions.

### 5.5. Periodic Access Reviews

Least privilege can erode over time when employees change teams, projects finish, or temporary role assignments are not removed. Periodically:

1. List role assignments at critical scopes.
2. Identify broad roles such as Owner, Contributor, or User Access Administrator.
3. Inspect permissions granted directly, through groups, and via inherited scopes.
4. Confirm each principal still has duties requiring that permission.
5. Remove unnecessary assignments and update group memberships.
6. Review custom roles for excess or missing operations compared to current duties.
7. Check Activity Logs and your organization's access review workflows.

Maintain an owner for every custom role. The owner is responsible for explaining its purpose, reviewing operations, and proposing updates when workloads change.

## 6. Updating and Removing Custom Roles Safely

When duties change, a custom role may need operations added or removed. Update the role definition in version control, review the changes, and deploy them through the same workflow as infrastructure code.

Update a role definition from a JSON file:

~~~bash
az role definition update \
  --role-definition ./vm-operator-role.json
~~~

Before updating, assess the impact on all principals currently assigned the role. A change to a role definition can change permissions for multiple groups or workloads simultaneously.

When a role is no longer used:

1. Find all role assignments referencing the custom role.
2. Confirm with the owner that no remaining duties depend on the role.
3. Remove the role assignments from principals at all relevant scopes.
4. Re-check role assignments and any pipelines or configurations referencing the role.
5. Delete the role definition once no assignments use it.

Locate the role assignment to remove from the earlier listing output, obtain its exact role assignment ID, and delete it:

~~~bash
az role assignment delete \
  --ids "<role-assignment-id>"
~~~

Once all assignments have been removed, you can delete the custom role:

~~~bash
az role definition delete \
  --name "Orders VM Operator"
~~~

If the role definition is still in use or deletion fails, inspect remaining assignments and remove them through an approved change process. Never delete a role based solely on its name or an assumption that the team no longer uses it.

## 7. Troubleshooting Errors and Evaluating Effective Permissions

When an operation is denied, errors typically appear as AuthorizationFailed or a message citing missing permissions for a specific operation. Troubleshoot in order:

1. Confirm the signed-in principal or active workload identity.
2. Confirm the target tenant and subscription.
3. Record the denied operation and resource ID.
4. Check direct role assignments, group-based assignments, and inherited assignments.
5. Verify the role definition contains the exact operation and an appropriate assignable scope.
6. Check Azure Policy or role assignment conditions if applicable.
7. Wait for permission changes to propagate to the service and retest in a safe environment.

Common causes:

| Symptom | Possible cause | How to resolve |
|---|---|---|
| Cannot start VM | Missing start/action operation or scope does not include the VM | Inspect role definition and role assignment |
| Can read storage account but cannot read blobs | Only has management-plane permissions | Grant appropriate data role at storage account or container |
| Operation denied even though custom role includes operation | Principal lacks assignment, wrong scope, or role has not propagated yet | Check principal, scope, and propagation delay |
| User can still delete resources despite NotActions excluding the operation | Another role assignment grants delete permission | Check all direct and inherited role assignments |
| Role cannot be assigned at desired scope | Scope is not listed in AssignableScopes | Adjust where the role is defined or the assignment scope per design |
| Cannot delete custom role | Role still has referencing role assignments | List and remove assignments first |

Azure Activity Log can assist in investigating management operations and role assignment changes. Record the timestamp, principal, resource ID, operation, and correlation ID if available to cross-reference related events.

## 8. Checklist Before Promoting a Custom Role to Production

Before putting a custom role into use, check:

- [ ] The principal's duties are clearly described and have an owner.
- [ ] Built-in roles were evaluated before deciding to create a custom role.
- [ ] Actions and DataActions contain only required operations.
- [ ] NotActions/NotDataActions are not misunderstood as deny mechanisms.
- [ ] Wildcards are removed or have explicit justification and approval.
- [ ] AssignableScopes and role assignment scopes match the scope of work.
- [ ] Permissions are assigned to the right group or managed identity.
- [ ] Privileged access has time bounds or activation controls where appropriate.
- [ ] Allowed actions were tested and out-of-scope actions were verified denied.
- [ ] Effective permissions from other role assignments and inheritance were checked.
- [ ] Processes exist for review, updates, access reviews, and role removal when no longer needed.

## 9. Practice Exercises

1. List the duties of an operations team running an application with a virtual machine, virtual network, and storage account. Split the duties into management-plane and data-plane permissions.
2. Look up Microsoft.Compute operations. Select operations so a team can only view, start, and deallocate VMs; explain why create, edit, and delete VM permissions are omitted.
3. Create a JSON file for the Orders VM Operator custom role using AssignableScopes at the subscription level and assign the role at a test resource group.
4. Use a test principal to verify allowed and denied actions. Check whether the principal has any other role assignments that could expand permissions.
5. Create a group for reading blob data only. Compare Storage Blob Data Reader with Reader to explain the difference between the management plane and data plane.
6. Write a periodic custom role review procedure: who owns it, which operations to check, how to handle group membership, and when to remove role assignments.

## 10. References

- [Azure role-based access control (Azure RBAC)](https://learn.microsoft.com/azure/role-based-access-control/overview)
- [Understand Azure role definitions](https://learn.microsoft.com/azure/role-based-access-control/role-definitions)
- [Steps to create a custom role](https://learn.microsoft.com/azure/role-based-access-control/custom-roles)
- [Assign Azure roles using Azure CLI](https://learn.microsoft.com/azure/role-based-access-control/role-assignments-cli)
- [Azure built-in roles](https://learn.microsoft.com/azure/role-based-access-control/built-in-roles)
- [What is Microsoft Entra Privileged Identity Management?](https://learn.microsoft.com/entra/id-governance/privileged-identity-management/pim-configure)
