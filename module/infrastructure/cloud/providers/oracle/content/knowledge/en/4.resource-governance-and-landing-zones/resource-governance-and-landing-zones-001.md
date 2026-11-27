# Designing Compartments for Organizations, Projects, and Environments

A company is deploying an e-commerce application on Oracle Cloud Infrastructure (OCI). The development team needs to create test VMs on their own; the operations team is responsible for production; the platform team manages shared networking; and finance needs visibility into the cost of each product. If all resources sit in the root compartment and every team holds broad administrative permissions, a single experimental change can impact the live sales system.

Compartments translate those governance requirements into concrete resource organization and permission boundaries. A solid design must answer three questions clearly: who owns the resources, who can do what, and where a change will affect which environments.

This lesson belongs to the **Resource Governance and Landing Zones** chapter under **CLOUD_PROVIDERS_ORACLE**. The examples focus on placing Compute, VCN, storage, and Oracle database services into an OCI structure that supports delegation, cost tracking, and automation. Compartments are one part of a landing zone; monitoring, connectivity, and availability requirements still need to be designed alongside this structure.

## 1. Learning Outcomes

After this lesson, learners will be able to:

- Choose an appropriate hierarchy axis across organizational units, projects, and environments.
- Distinguish a compartment's governance boundary from network boundaries and deployment locations.
- Recognize that IAM permissions can propagate down to child compartments.
- Separate shared resources from resources managed by individual product teams.
- Document ownership, cost attribution, and lifecycle for each compartment before provisioning.
- Create a hands-on compartment tree and verify it using the OCI CLI.

This lesson assumes you already know that a tenancy is the organization's OCI account scope, an IAM policy is a set of rules that grants or controls access, and an OCID is the identifier of an OCI resource. Whenever an example uses a placeholder OCID, replace it with the real identifier from your lab environment.

## 2. What Does a Compartment Represent?

A compartment is a logical grouping of resources within a tenancy. When creating a compartment-aware resource, the deployer selects the compartment that contains it. In the hierarchy tree, a child compartment has a single parent compartment; it cannot sit under both a project branch and a department branch at the same time. Therefore, the tree needs one primary governance axis, while other classification dimensions are represented using tags, reports, or operational documentation.

| Concept | Question it answers | Example |
| --- | --- | --- |
| Tenancy | Which OCI account scope is the organization governing? | Company tenancy |
| Compartment | Which governance scope does the resource belong to? | `shop/prod` |
| Region | Which OCI geographic area is the resource deployed in? | Primary region and disaster recovery region |
| VCN, subnet, and network rules | How do resources connect to one another? | Application network and database subnet |
| Tag | By which attributes is the resource classified? | Owner, cost center, sensitivity level |

Compartments are global in scope, whereas many resources such as Compute instances and VCNs are regional. A single compartment can hold resources across multiple regions; the region filter in the Console still determines which resources appear on a service page. As a result, an empty instance list is not enough to conclude that a compartment contains no resources. See [Working in Regions](https://docs.oracle.com/en-us/iaas/Content/GSG/Concepts/working-with-regions.htm).

Keep two design consequences in mind:

1. **Separating compartments does not automatically create network isolation.** Two VMs in different compartments can still communicate if connectivity configuration and network rules allow it.
2. **Separating compartments does not automatically create high availability.** An application with a single instance still has a single point of failure even if that instance lives in a compartment named `prod`. Fault tolerance depends on deployment architecture, data design, and recovery procedures.

Keep the root compartment for components that truly require tenancy scope and appropriate platform-level administration. Business workloads should have their own compartments so operators do not have to request broad root permissions just to perform local tasks.

## 3. Starting from Governance Requirements

Do not start by copying the entire HR org chart into a compartment tree. Departments can be renamed or merged, while production systems still need stable operational ownership and protection policies.

Before creating the tree, answer the following questions for each group of resources:

| Design question | Impact on structure |
| --- | --- |
| Who is ultimately accountable when the system has an incident? | Identifies the owner of the branch or leaf compartment |
| Do development and operations teams have different permissions? | Consider separating `dev`, `staging`, and `prod` |
| Do two products have independent release schedules and lifecycles? | Consider separate compartments for each product |
| Which team manages networking, connectivity, and encryption keys? | Identifies shared resources and cross-compartment usage permissions |
| Are there distinct sensitive-data requirements? | Consider a separate branch and additional data controls |
| Should costs be accounted for by project or by organizational unit? | Chooses the primary axis and guides supplementary tag design |
| Who is allowed to create child compartments and modify policies? | Determines the scope of administrative delegation |
| When a project ends, who revokes access and handles data disposition? | Defines lifecycle, approvers, and decommissioning procedures |

For example, two teams within the same Engineering department that have different support contracts, data sets, and budgets may need two separate project branches. Conversely, three development teams jointly operating a single product can share one product branch and distinguish roles via IAM instead of creating a separate compartment per team.

A practical rule of thumb is: **if two sets of resources require different administrative permissions, owners, or lifecycles, consider separating compartments; if they only differ in reporting attributes, consider tags first.** This is a design decision guideline, not a mandatory OCI rule.

## 4. Ordering Organizations, Projects, and Environments

### 4.1. Three Common Models

| Model | Strengths | Trade-offs to consider |
| --- | --- | --- |
| Unit → project → environment | Clear delegation and aggregation by organizational unit | Prone to disruption during reorganizations if tied too closely to the org chart |
| Project → environment | Convenient when one team owns the full product lifecycle | A team operating multiple production systems needs policies across multiple branches |
| Environment → project | Convenient when production is operated by a centralized team | A single product team must receive permissions in multiple branches to manage all its environments |

There is no single optimal ordering for every organization. Choose the top-level axis based on where delegation needs to remain stable longest. Then check whether permissions at that level could unintentionally cover environments that need separate protection.

For instance, `workloads/shop/dev` and `workloads/shop/prod` work well when Shop is a stable product, but that does not mean the development team should hold administrative rights at `shop`. Permissions can be granted individually at each environment compartment.

### 4.2. Reference Tree for Two Products

Suppose an organization has two products, Shop and CRM, a shared platform team, and an information security team. The following structure can be used:

```text
tenancy (root)
└── org
    ├── security
    ├── shared
    │   ├── shared-nonprod
    │   └── shared-prod
    ├── workloads
    │   ├── shop
    │   │   ├── dev
    │   │   ├── staging
    │   │   └── prod
    │   └── crm
    │       ├── dev
    │       └── prod
    └── sandbox
```

Role of each branch in the illustrative design:

- `org` serves as the consolidation point for the organization's governance scope within the tenancy.
- `security` holds security resources or log collection owned by the information security team, depending on each service's capabilities.
- `shared-nonprod` and `shared-prod` contain shared platform components that carry different risk levels and change-control processes.
- `workloads` groups business workload resources. The `shop` and `crm` branches serve as product management points; the environment compartments underneath contain the corresponding resources.
- `sandbox` is for experimentation with clearly defined owners, expiration dates, and usage limits.

Nodes such as `workloads` or `shop` may be used primarily to organize the tree, while workloads are placed in environment compartments. This is an operational convention chosen to reduce confusion; OCI does not require parent nodes to be empty.

In this example, paths with `/` are a human-readable notation. When writing IAM policies that reference compartment paths, the examples below use `:` according to OCI syntax.

### 4.3. When Should You Split Another Layer?

Initially, `shop/prod` can hold instances, buckets, and database resources for the same application. Only add compartments such as `application` and `database` when there is a significant difference in ownership or controls.

For example, if DBAs manage databases and the application team must not alter database configurations, splitting them can make the permission scope clearer. However, every subdivision increases policy count, cross-compartment dependencies, and inventory effort. Splitting every resource type into its own compartment from day one usually adds complexity without solving a concrete requirement.

Nor is there any need to duplicate the entire tree simply because you deploy to another region. Add a region axis only when it solves a real governance requirement, such as two operations teams with independent regional responsibilities. If the requirement is only disaster recovery deployment, design resilience together with the service architecture first.

## 5. Designing the Tree Alongside IAM Permissions

### 5.1. Permissions on a Parent Can Affect Children

A policy granting permissions on a parent compartment can apply down to child compartments. With the reference tree, the following statement has a broader scope than a developer who only works in `dev` needs:

```text
Allow group 'Default'/'ShopDevelopers' to manage all-resources in compartment org:workloads:shop
```

That scope covers all environments under `shop`, including `prod`. Merely adding a narrower allow policy in `dev` does not revoke permissions already granted by a broad allow policy on the parent. You must review grants at higher levels and all groups to which a user belongs. See [Policy Inheritance](https://docs.oracle.com/en-us/iaas/Content/Identity/policieshow/Policy_Inheritance.htm).

OCI provides **IAM deny policies** as an opt-in feature. When enabled, deny statements can block permissions that were allowed. Therefore, you should not claim that OCI only has allow policies or that a child compartment can always override parent permissions on its own. The examples in this lesson use allow policies and do not assume deny policies are enabled in the tenancy; if your organization uses deny policies, you must evaluate them as well when verifying effective permissions. See [Deny Policies](https://docs.oracle.com/en-us/iaas/Content/Identity/policysyntax/denypolicies.htm).

### 5.2. Granting Permissions by Environment and Job Function

An initial responsibility matrix might look like this:

| Illustrative group | Primary scope | Expected work |
| --- | --- | --- |
| `ShopDevOperators` | `shop/dev` | Manage assigned development resources |
| `ShopStagingOperators` | `shop/staging` | Deploy and operate integration testing |
| `ShopProdOperators` | `shop/prod` | Operate production under change control |
| `PlatformNetworkAdmins` | Assigned shared network compartments | Manage connectivity and foundational network configuration |
| `SecurityReviewers` | Scopes requiring audit | Read configurations and evidence needed for audits |

You cannot translate a line reading "manage resources" directly into `manage all-resources` for every group. You must analyze which APIs the group needs to call, on which resource types, and what dependencies exist in other compartments.

The example below illustrates grants for Compute, volumes, and networking in **only the dev environment**. The policy is assumed to be attached at root; `Default` is the example identity domain name and must be replaced if the tenancy uses another domain.

```text
Allow group 'Default'/'ShopDevOperators' to manage instance-family in compartment org:workloads:shop:dev
Allow group 'Default'/'ShopDevOperators' to manage volume-family in compartment org:workloads:shop:dev
Allow group 'Default'/'ShopDevOperators' to use virtual-network-family in compartment org:workloads:shop:dev
```

This is an example of compartment scoping, not a complete permission set for every way of launching Compute instances. Using custom images, encryption keys, defined tags, or resources in other compartments may require additional permissions. `use virtual-network-family` also covers many networking actions; a real-world implementation should narrow it down to the APIs and resource types the team actually uses.

In a policy, `:` joins compartment levels relative to where the policy is attached. You can use `in compartment id <COMPARTMENT_OCID>` to target a destination compartment directly. Do not include the tenancy name in the path as if it were a child compartment. See [Policy Syntax](https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/policysyntax.htm).

### 5.3. Where You Attach a Policy Is Also a Governance Decision

Distinguish between:

- **Policy attachment location:** whether the policy object is stored and managed at root or in a specific compartment.
- **Statement scope:** the resources that the rules inside the policy allow access to.

These two factors are related but not identical. Placing a policy at root does not mean every statement grants tenancy-wide access; the example above still specifies the dev compartment. The attachment location also affects who can edit or delete the policy. See [Working with Compartments](https://docs.oracle.com/en-us/iaas/Content/Identity/compartments/Working_with_Compartments.htm).

For production, a sound choice is to have the platform or IAM administration team own the policies that grant operational access, while the product team receives permissions on its assigned resources. If you delegate policy management to a product team, you must evaluate their ability to alter permissions within that delegated scope.

Do not grant broad permissions at `workloads` merely to reduce the number of policy lines, because doing so can open access across every child product. Policy conciseness must serve the agreed-upon permission model.

## 6. Managing Shared Resources and Cross-Compartment Dependencies

Shared resources typically include central networking, on-premises connectivity, or operational components managed by a platform team. Putting them in `shared` clarifies ownership, but does not yet define how workload teams are allowed to use them.

For example, a Shop instance in `shop/dev` may need to use a subnet managed in `shared-nonprod`. The deployment team must identify the required permissions on the network resources in the target compartment, rather than only granting Compute permissions in `shop/dev`. Do not resolve permission errors by moving the subnet into the application compartment or granting `manage all-resources in tenancy`.

A shared-resource usage agreement should explicitly document:

| Item | Example for shared networking |
| --- | --- |
| Owner | Platform team managing subnets and network rules |
| Consumer | Shop dev deployment pipeline or team |
| Allowed actions | Subnet usage operations required by the chosen deployment workflow |
| Actions retained by platform | Modifying routing, security configurations, or deleting networks |
| Blast radius | Workloads sharing the same subnet or connectivity components |
| Change process | Dependency assessment and advance notice before configuration changes |

Separating `shared-prod` from `shared-nonprod` clarifies change-control rigor, but true independence also depends on whether the underlying resources are separated. If both compartments still rely on the same central appliance, circuit, or service, shared risk remains.

Dependencies for backups, logs, keys, and data must be reviewed separately. Do not put all backups from every system into a single compartment solely for Console convenience if doing so creates a group of people able to delete backups across all products.

## 7. Combining Compartments, Tags, and Usage Controls

### 7.1. Using Tags for Additional Classification Dimensions

In a project → environment tree, finance may still need reporting by business unit. Instead of duplicating resources or rebuilding the tree, design defined tags with clear conventions:

| Illustrative attribute | Example value | Purpose |
| --- | --- | --- |
| `Governance.OwnerTeam` | `shop-platform` | Identify the accountable team |
| `Governance.Environment` | `dev`, `staging`, `prod` | Classify environment |
| `Finance.CostCenter` | `commerce` | Allocate internal costs |
| `Governance.DataClass` | `internal`, `restricted` | Support inventory by sensitivity level |
| `Governance.ExpiryDate` | Agreed expiration date | Track sandboxes due for decommissioning |

These are organization-defined namespace and key names for illustration, not mandatory default OCI tags. The team owning the convention must define who can set or modify values. A tag reading `prod` does not automatically create a production approval workflow.

Distinguish **tags applied to a compartment** from **tag defaults**. OCI supports defined-tag inheritance from compartments in metering services such as Cost Analysis, Usage Reports, and Budgets; precedence rules should be reviewed for cost reporting. You should not assume every physical tag attribute on each individual resource is updated identically to those reports. See [Tags and Tag Namespace Concepts](https://docs.oracle.com/en-us/iaas/Content/Tagging/Tasks/managingtagsandtagnamespaces.htm).

Tag defaults are used to apply defined tags when resources are created within the relevant scope, including child compartments. Creating or editing a tag default does not retroactively update all existing resources. After configuration, verify sample resources and identify existing resources that need backfilling. See [Managing Tag Defaults](https://docs.oracle.com/en-us/iaas/Content/Tagging/Tasks/managingtagdefaults.htm).

### 7.2. Do Not Confuse Budgets with Quotas

| Mechanism | Key question | Role in design |
| --- | --- | --- |
| Budget | Is spending exceeding or likely to exceed expected levels? | Track spending and alert responsible owners |
| Compartment quota | How many resources of supported types and scopes may the compartment consume? | Control resource allocation for a project or sandbox |
| Service limit | Up to what level does OCI allow the tenancy to consume in the corresponding scope? | Assess capacity readiness before deployment |

A budget is a soft limit for cost tracking; creating a budget alone does not stop instances when spend crosses the threshold. Therefore, sandboxes still need designated alert recipients and concrete remediation actions. See [Creating a Budget](https://docs.oracle.com/en-us/iaas/Content/Billing/Tasks/create-budget.htm).

Compartment quotas are set by administrators, while service limits are set by OCI for the tenancy per scope. Quotas do not raise service limits and do not guarantee that physical capacity is always available for provisioning. See [Service Limits](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/overview.htm).

In the Shop scenario, you can assign separate budgets for dev and prod, set appropriate quotas for dev, and allocate shared platform costs using an internal convention. Shared cost allocation must be consistent—for example, using utilization ratios or agreed percentages rather than arbitrarily moving resources between compartments to shift who bears the cost.

## 8. Standardizing Information Before Creating Compartments

Every compartment should have a short design record. The following example describes `org/workloads/shop/prod`:

| Field | Illustrative design value |
| --- | --- |
| Purpose | Host production workloads for the Shop product |
| Business owner | Shop product representative |
| Operations team | `ShopProdOperators` |
| Policy manager | Assigned IAM or platform team |
| Expected resources | Compute, storage, and database components within product scope |
| Dependencies | Agreed shared production network, keys, and monitoring services |
| Data rules | Per Shop's actual data classification |
| Cost | Cost center `commerce`, designated alert recipient |
| Availability | Recovery requirements designed at the service architecture level |
| Lifecycle | Decommissioned when the product is retired and data handling is complete |

Names should be clear, follow a stable convention, and avoid sensitive information. OCI requires compartment names to be unique within the same parent compartment; different projects can have child compartments with the same name `dev`. OCIDs distinguish them in automation. See [Creating a Compartment](https://docs.oracle.com/en-us/iaas/Content/Identity/compartments/To_create_a_compartment.htm).

In operational documentation, write out the full path rather than simply saying "the dev compartment." In deployment code, pass the properly scoped OCID into each configuration, avoiding defaults that might accidentally create resources in root or the wrong environment.

## 9. Hands-On: Creating a Project and Environment Tree with the OCI CLI

### 9.1. Lab Scope

This lab creates a sample project under an administrator-provisioned lab compartment:

```text
assigned lab compartment
└── lab-shop
    ├── dev
    ├── staging
    └── prod
```

The name `prod` in this lab only illustrates the organizational model. Do not use real production resources or data to test permissions.

Prerequisites:

- The OCI CLI is installed and authenticated with an appropriate profile.
- You have the lab compartment OCID and permission to create child compartments inside it.
- The name `lab-shop` is not already taken in the parent compartment; if it exists, verify ownership before reusing or renaming it.
- A lab group and an administrator authorized to configure policies for that group have been identified.

The following commands are **PowerShell** examples. Do not embed API keys or credentials inside command text.

### 9.2. Create the Project Compartment and Three Environments

Replace the placeholder string in `$LabParentId` with the real OCID. The `--compartment-id` parameter of the create command is the **OCID of the parent compartment**, and the returned `data.id` value is the OCID of the newly created compartment.

```powershell
$LabParentId = '<OCID_COMPARTMENT_LAB>'

$ShopId = oci iam compartment create `
    --compartment-id $LabParentId `
    --name 'lab-shop' `
    --description 'Lab project: Shop; owner: training team' `
    --wait-for-state ACTIVE `
    --query 'data.id' `
    --raw-output

if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($ShopId)) {
    throw 'Failed to create compartment lab-shop; stopping to inspect.'
}
$ShopId = $ShopId.Trim()

$EnvironmentIds = @{}
foreach ($EnvironmentName in @('dev', 'staging', 'prod')) {
    $EnvironmentId = oci iam compartment create `
        --compartment-id $ShopId `
        --name $EnvironmentName `
        --description "Shop lab environment: $EnvironmentName" `
        --wait-for-state ACTIVE `
        --query 'data.id' `
        --raw-output

    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($EnvironmentId)) {
        throw "Failed to create $EnvironmentName; stopping to inspect."
    }
    $EnvironmentIds[$EnvironmentName] = $EnvironmentId.Trim()
}

$EnvironmentIds
```

The command uses `--wait-for-state ACTIVE` to avoid immediately using an object that is still in the creating state. If it times out, inspect the object before retrying; `create` is not a mechanism that reconciles an existing tree. If the loop stops mid-way, compartments already created successfully will still exist. See [OCI CLI: compartment create](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/iam/compartment/create.html).

For repeatable deployments, model the tree using an Infrastructure as Code tool or a workflow that checks existing state rather than repeatedly running create commands. Each tree needs a single configuration owner to avoid two pipelines managing the same compartment.

### 9.3. Verify Structure and Permissions

List the direct child compartments of the project:

```powershell
oci iam compartment list `
    --compartment-id $ShopId `
    --lifecycle-state ACTIVE `
    --all `
    --query 'data[].{Name:name,Id:id,Parent:"compartment-id",State:"lifecycle-state"}' `
    --output table
```

You should expect `dev`, `staging`, and `prod` with the same `Parent` equal to `$ShopId`. This command checks the structure; it does not prove the user has permissions to act on every resource inside. `--all` fetches all result pages; when querying a non-root compartment, the list operation returns direct children and does not traverse the entire subtree automatically. See [OCI CLI: compartment list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/iam/compartment/list.html).

To test granting permissions by OCID, an administrator can use a statement like the following after substituting placeholders and choosing the right group/domain:

```text
Allow group 'Default'/'ShopLabOperators' to manage instance-family in compartment id <DEV_COMPARTMENT_OCID>
```

This statement only illustrates compartment scoping for instances; it does not automatically grant every dependency needed to launch an instance. The administrator must add the required permissions analyzed for the lab, just as in the IAM design section above.

Use a test account that does not belong to a broad administrative group to verify both directions:

| Test | Expected result |
| --- | --- |
| Perform the assigned action on an existing dev resource | Succeeds if permissions and dependencies are sufficient |
| Perform the corresponding action on a prod resource whose OCID is known | Denied per the lab permission model |
| Attempt to modify a policy outside the assigned scope | Denied |
| Test actions using a shared resource | Succeeds only for explicitly permitted dependencies |

Do not rely on "cannot see prod resources" as the sole proof. You must verify the exact API operation and resource identifier; a "not found" message can stem from permissions, region selection, or an incorrect identifier. If the test account can still perform production actions, inspect other groups and higher-level policies before modifying the compartment tree.

After the lab, inventory what was created, revoke temporary lab permissions, and handle the compartments according to your training environment's cleanup process. Do not treat deleting a compartment as an action that automatically cleans up all resources and data inside it.

## 10. Changing Structure in a Live Environment

Two distinct operations must be evaluated separately:

- **Moving a resource:** changing the compartment that holds a specific resource.
- **Moving a compartment:** changing the position of a branch within the tree.

When moving a resource, permissions in the destination compartment can change who has access. Movability and dependent-resource behavior vary by service; some dependencies move along, while others must be handled separately. Restrictions related to security zones must also be considered if the environment uses that feature. See [Moving a Resource Between Compartments](https://docs.oracle.com/en-us/iaas/Content/Identity/compartments/To_move_a_resource_to_a_different_compartment.htm).

When moving a compartment, you must evaluate inherited permissions from both the old parent and the new parent. OCI may automatically update certain policies containing compartment paths under specific conditions; you should not assume either that all policies are updated or that none are updated. See [Moving a Compartment](https://docs.oracle.com/en-us/iaas/Content/Identity/compartments/To_move_a_compartment.htm) and [Working with Compartments](https://docs.oracle.com/en-us/iaas/Content/Identity/compartments/Working_with_Compartments.htm).

A change plan should include these steps:

1. Inventory resources, dependencies, and active accessing accounts or pipelines.
2. Compare effective permissions before and after the change, including both allow and deny policies if applicable.
3. Assess impacts on cost classification, quotas, monitoring configurations, and automation.
4. Test in a non-production environment with an equivalent structure.
5. Execute within an agreed maintenance window and verify service operation.
6. Update documentation, deployment configurations, and post-change verification evidence.

Do not use moving resources from `dev` to `prod` as a default release process. Releases normally require deploying controlled configurations or artifacts into the production environment; changing compartments only changes resource organization scope and does not replace testing, approvals, or data handling.

## 11. Common Design Mistakes

| Mistake | Consequence | Remediation |
| --- | --- | --- |
| Placing all workloads in root | Routine small tasks require overly broad permissions | Gradually move to project and environment scopes with clear owners |
| Combining dev and prod and relying only on naming | Easy to mis-grant permissions or act on the wrong environment | Separate compartments when permission and lifecycle requirements differ |
| Granting `manage all-resources` on a parent for convenience | Permissions cascade down into branches that need protection | Grant task-specific permissions at the analyzed scope |
| Creating a compartment per instance | Policies, inventory, and automation become hard to maintain | Group by meaningful accountability boundaries |
| Encoding every classification dimension in the tree | Deep hierarchy that churns whenever reporting needs change | Use tags for supplementary attributes |
| Having `shared` without a usage agreement | Leads to overly broad grants or changes impacting multiple teams | Document owners, allowed operations, and dependencies |
| Creating sandboxes without alert recipients or expiration dates | Test resources keep accruing charges | Assign owners, budgets, appropriate quotas, and a retirement workflow |
| Confusing compartments with network or high-availability boundaries | Misjudges isolation and resilience | Verify permissions, connectivity, data, and availability separately |

## 12. Completion Criteria for a Compartment Design

A compartment tree is ready for implementation when the team can explain and verify the following points:

- Every branch has a concrete purpose and owner; naming alone is not the only reason it exists.
- The ordering of organizations, projects, and environments matches long-term delegation patterns.
- Environments with different risk levels receive appropriate permissions, even after accounting for parent grants and other group memberships.
- Shared resources have clearly documented operational ownership and cross-compartment usage rights.
- Cost and data classification dimensions have governed tag conventions.
- Budgets, quotas, and service limits are assigned their proper roles.
- Tree creation and OCID injection into deployment configurations are repeatable and verifiable.
- Processes exist for onboarding new projects, structural changes, and project decommissioning.
- Networking, monitoring, backup, and recovery requirements are tied to the corresponding service designs.

In the Shop example, the desired outcome is that developers can operate in dev, operations can manage production, the platform team controls shared components, and cost owners can account for usage. The compartment tree must make those responsibilities explicit before the organization expands further into OCI services.
