# Designing Least Privilege by Compartment and Service Group

## 1. Objectives and Context

Least privilege means granting just enough permissions for a person or workload to complete an approved task, within the necessary resource scope and for as long as the need remains. On Oracle Cloud Infrastructure (OCI), this requires coordinating access principals, IAM policies, compartments, resource types, and supplementary conditions.

For example, a team that only needs to view application machine status does not need to manage all of Compute. A Java application that needs to read input files in one bucket does not need permission to manage every storage resource in the tenancy.

This lesson belongs to the **IAM Identity and Access Management** chapter of the **CLOUD_PROVIDERS_ORACLE** module. It connects IAM with tenancy, compartments, VCN, Compute, storage, and Oracle database services to design infrastructure with proper authorization, monitoring, automation, cost control, and availability.

After this lesson, you will be able to:

- Translate a business task into a concrete permission scope.
- Distinguish identity groups from service resource groupings.
- Explain permission inheritance across a compartment tree and cumulative permissions from multiple sources.
- Choose appropriate verbs, resource-types, and conditions instead of granting broad permissions to fix errors.
- Design separated roles for networking, Compute, data, and workloads.
- Verify granted permissions and revocation with appropriate evidence.

## 2. Start from the Task Rather Than Policy Statements

Before writing a policy, describe the requirement using this template:

> Which principal needs to perform which operation, on which resource, in which compartment, for what purpose, and until when?

Examples of clear requirements:

- The support team needs to list and view application instance details in the lab compartment.
- The power operations team needs to execute approved power operations on lab instances.
- The networking team manages the lifecycle of networking resources in the lab networking compartment.
- The application reads objects in a designated input bucket.
- The report export job creates new objects in an output bucket without reading or deleting existing data.

A request like "let the development team use OCI" is insufficient to derive a permission set. It does not clarify whether they may create instances, edit networks, download data, rotate secrets, or delete resources.

### 2.1. Requirements Matrix

| Principal | Approved Operations | Scope | Out-of-Scope Operations |
| --- | --- | --- | --- |
| Compute viewer | List and view instances | Lab application compartment | Create, update, or delete instances |
| Power operator | Role-scoped power operations | Lab instances | Administer networking, alter policies |
| Network administrator | Operate networking lifecycle | Lab networking compartment | Read business data in buckets |
| Application workload | Read input data | Designated bucket | Create buckets or delete objects |
| Data export job | Create new objects | Designated output bucket | Read, overwrite, or delete objects |
| Database observer | View database resource metadata | Lab data compartment | Administer the entire database platform |

This matrix is a design specification. Actual permissions must be cross-checked against each service's APIs and permissions; role names do not automatically enforce limits.

## 3. Two Different Meanings of "Service Group"

In authorization design, distinguish between:

1. **Identity group:** a collection of users, such as a Compute operations team.
2. **Resource family:** a grouping of resource types defined by OCI for writing policies, such as `instance-family`, `virtual-network-family`, or `object-family`.

An identity group can receive multiple statements across multiple resource types. A resource family is neither a user group nor a compartment scope.

| Concept | Example | Effect |
| --- | --- | --- |
| User group | `LabComputeViewers` | Groups users with a shared duty |
| Dynamic group | `LabAppRuntime` | Selects supported resources/workloads as principals |
| Individual resource-type | `instances`, `buckets`, `objects` | Selects the specific resource type to grant access to |
| Resource family | `instance-family`, `object-family` | Bundles multiple resource types and permissions per service definition |
| Compartment | `LabApp`, `LabData` | Defines resource scope and inheritance tree |

Do not assume a family contains only the permissions you have in mind. For example, Oracle notes that `instance-family` includes certain VNIC- and volume-related permissions beyond direct Compute resource types to support common scenarios. [Oracle: Details for the Core Services](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/corepolicyreference.htm)

Families shorten policies, but they are not always the smallest option. When a task is narrow, starting from individual resource-types and checking exact permissions is usually easier to justify.

## 4. Design the Compartment Tree Before Granting Permissions

Suppose the lab environment has this structure:

~~~text
Tenancy
├── Labs
│   ├── LabNetwork
│   ├── LabApp
│   └── LabData
└── Production
    ├── ProdNetwork
    ├── ProdApp
    └── ProdData
~~~

In this example:

- Shared lab VCNs and subnets reside in `LabNetwork`.
- Application instances reside in `LabApp`.
- Lab buckets and database resources reside in `LabData`.
- The production environment resides in a separate branch.

This is an illustrative layout, not a mandatory structure for every tenancy. Splitting compartments should reflect accountability, lifecycle, and control boundaries; there is no need to create a compartment for every individual resource.

### 4.1. Parent-Scope Permissions Affect Child Scopes

When granting permissions on a compartment, account for its child compartments. OCI uses permission inheritance along the compartment tree. Thus, a broad grant at `Labs` can affect `LabApp`, `LabNetwork`, and `LabData`; creating a new child compartment does not strip permissions inherited from above. [Oracle: Managing Compartments](https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/managingcompartments.htm)

Design implications:

- Do not grant broad management access at `Labs` if the principal only needs to operate `LabApp`.
- When evaluating permissions in a child compartment, inspect grants from parent levels and the tenancy as well.
- Do not place lab permissions at `tenancy` scope merely because it is easy to select in the Console.
- When moving resources or compartments, evaluate which permissions will be lost and which new ones will take effect.

A compartment is a boundary for organizing resources and granting permissions; it does not replace VCNs, subnets, NSGs, or in-application authentication. Separating compartments does not automatically block network paths or independently granted SQL privileges.

### 4.2. Policy Placement and Permission Scope Are Two Separate Decisions

A policy is attached to a compartment or root. Attachment placement affects who can manage that policy; the `in compartment ...` clause in a statement determines which resources receive permissions.

In the examples below, assume policies are centrally administered at **Labs**, while `LabApp`, `LabNetwork`, and `LabData` are direct child compartments. Thus, compartment names in statements can be resolved unambiguously within this tree.

If a policy is placed higher up, reference the appropriate compartment path or OCID. Never copy a leaf compartment name while ignoring the actual hierarchy. Attachment syntax and semantics must be verified when choosing where to create policies. [Oracle: How Policies Work](https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/policies.htm)

Do not grant policy-editing permissions to a resource operations team just so they can fix missing-permission errors themselves. The ability to alter policies is an administrative capability that must be evaluated separately.

## 5. Choose the Right Principal in the Identity Domain

Subject syntax can explicitly specify the domain and group:

~~~text
Allow group 'Default'/'LabComputeViewers' to <verb> <resource-type> in compartment LabApp
~~~

`Default` is an illustrative domain name. If the group belongs to another domain, specify that exact domain. Two groups with the same name in two domains are not the same principal. OCI also supports referencing groups by OCID using the corresponding policy syntax. [Oracle: Subjects](https://docs.oracle.com/en-us/iaas/Content/Identity/policysyntax/subject.htm)

Name groups by function, such as viewing Compute or operating networks, and manage memberships through an approved workflow. Never use a group's name as proof that its effective permissions are accurate.

For example, a group named `ReadOnly` can still receive management permissions if another policy grants them. A user belonging to multiple groups must be evaluated across their entire effective permission set.

For workloads, choose appropriate resource identities instead of personal credentials when supported by the service. Dynamic group matching rules are part of the security boundary, not merely a secondary setup step.

## 6. Choose Verbs Based on APIs and Permissions

OCI policies typically follow this structure:

~~~text
Allow <subject> to <verb> <resource-type> in <location> where <conditions>
~~~

The condition clause can be omitted when unneeded. Together, these components determine which requests are allowed. [Oracle: IAM Policies Overview](https://docs.oracle.com/en-us/iaas/Content/Identity/policieshow/Policy_Basics.htm)

Common verbs are `inspect`, `read`, `use`, and `manage`, but you must consult the mapping table for the actual resource type:

| Verb | Design Approach | What Not to Assume |
| --- | --- | --- |
| `inspect` | Check basic observation permissions for the resource type | All services return the exact same kind of data |
| `read` | Check additional contents or read APIs granted | Every read operation is non-sensitive |
| `use` | Check usage and accompanying update operations | Only "using" without changing state |
| `manage` | Check all permissions included at this level | Only creating resources, without delete or critical changes |

### 6.1. Verbs Are Only Ways to Group Permissions

To choose the right permissions, check:

1. Which API operation performs the task?
2. Which permissions does that operation require?
3. Which resource-type and verb cover those permissions?
4. Is there a suitable condition to narrow access further?
5. Are any dependent resources located in a different compartment?

A verb may bundle more permissions than the immediate task needs. Therefore, "pick the lowest verb that looks plausible" is only the starting step, not the entire design process.

### 6.2. Read Permissions Can Also Be Sensitive

Object Storage `read objects` permits reading object contents, not just seeing file names. For Autonomous Database, policy documentation distinguishes `inspect` from `read`; certain APIs for generating or retrieving wallets map to `read autonomous-databases`. Do not treat read permissions as a blanket safe label across every service. [Oracle: Details for Object Storage and Archive Storage](https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/objectstoragepolicyreference.htm), [Oracle: IAM Policies for Autonomous Database](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/autonomous-database-iam-policies.html)

If an observer only needs Autonomous Database resource metadata, consider starting from `inspect autonomous-databases` and checking required operations. OCI permissions to manage database resources must also be distinguished from database users and data privileges inside the database.

## 7. Task-Based Policy Patterns

The following patterns illustrate designs within the lab tree above. Groups, dynamic groups, compartments, and buckets must be created, verified, and approved separately before applying. Strings inside `<...>` are placeholders, not literal identifiers.

You do not need to grant all patterns to one user simultaneously. Each pattern serves a distinct task.

### 7.1. Listing and Viewing Lab Application Instances

~~~text
Allow group 'Default'/'LabComputeViewers' to read instances in compartment LabApp where any {request.operation = 'ListInstances', request.operation = 'GetInstance'}
~~~

This statement keeps the scope at `LabApp`, selects `instances`, and restricts operations to those required for the stated task. It is not intended to populate every item in the Compute Console UI.

If users need to view VNICs or volumes, identify that requirement and grant corresponding permissions separately. Do not immediately switch to managing the whole `instance-family` just because one secondary tab is denied.

`any` is an OR condition: the operation must match one of the listed values. OCI supports `any` and `all` to combine conditions; condition variables must apply to the request being evaluated. [Oracle: Conditions](https://docs.oracle.com/en-us/iaas/Content/Identity/policysyntax/conditions.htm)

### 7.2. Operating Instance Power State

A power operations role may need permission to view instances and execute power actions:

~~~text
Allow group 'Default'/'LabPowerOperators' to read instances in compartment LabApp where any {request.operation = 'ListInstances', request.operation = 'GetInstance'}
Allow group 'Default'/'LabPowerOperators' to use instances in compartment LabApp where request.permission = 'INSTANCE_POWER_ACTIONS'
~~~

Oracle maps the `InstanceAction` operation to the `INSTANCE_POWER_ACTIONS` permission. The condition in the second statement restricts the allowed permission instead of granting all other rights under `use instances`. [Oracle: Permissions Required for Each Core API Operation](https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/corepolicyreference_topic-Permissions_Required_for_Each_API_Operation.htm)

This pattern does not claim to permit only one specific action such as START. Multiple power operations share the same operation and permission; if business requirements need finer restriction, check service-supported variables or design a controlled automation flow.

Power actions can affect availability. Even without permission to create or delete resources, this role still requires approval and an operational audit trail.

### 7.3. Network Administration in a Dedicated Scope

~~~text
Allow group 'Default'/'LabNetworkAdmins' to manage virtual-network-family in compartment LabNetwork
~~~

This pattern is for people responsible for the **networking resource lifecycle** in the lab. It is a broad permission within a bounded service scope, appropriate when the task genuinely requires network administration.

If a team only needs to use an existing subnet to deploy an application, do not use this network admin pattern in place of dependent usage permissions. Managing routes, gateways, and network rules should be assigned separately.

### 7.4. Reading Data in a Single Bucket

Suppose bucket `lab-input` in `LabData` holds test data:

~~~text
Allow group 'Default'/'LabInputReaders' to read buckets in compartment LabData where target.bucket.name = 'lab-input'
Allow group 'Default'/'LabInputReaders' to read objects in compartment LabData where target.bucket.name = 'lab-input'
~~~

The first statement enables reading configuration of the known bucket; the second allows reading objects in that bucket. If there is no need to read bucket configuration, re-evaluate whether the first statement is necessary.

Do not assume a bucket-name condition will allow listing all buckets in the compartment. List operations may not carry the target variable expected by the request. When a condition variable does not apply, verify behavior in documentation and design a separate discovery permission if genuinely needed.

Names in OCI conditions follow specific matching rules; Object Storage documentation notes that bucket name conditions are case-insensitive. Never create two security boundaries differing only by letter case and rely on name conditions to separate them. [Oracle: Details for Object Storage and Archive Storage](https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/objectstoragepolicyreference.htm)

### 7.5. Creating New Objects Without Reading, Overwriting, or Deleting

Suppose a report export job only needs to create new objects in `lab-output`:

~~~text
Allow group 'Default'/'LabReportWriters' to manage objects in compartment LabData where all {target.bucket.name = 'lab-output', request.permission = 'OBJECT_CREATE'}
~~~

The `manage` verb is the grouping tier that includes `OBJECT_CREATE`, while the condition allows only the selected permission in the specified bucket. Do not read the verb name and conclude this statement permits every object management operation.

This pattern supports writing a new object via the appropriate operation. Overwriting an existing name and multipart uploads can require other permissions; test the application with its actual upload method. Do not loosen permissions to delete or overwrite merely because a library uses a different upload flow than expected. [Oracle: Policy Builder Policy Templates](https://docs.oracle.com/en-us/iaas/Content/Identity/policiescommon/commonpolicies.htm)

A valid design outcome may be adjusting the export workflow to use new names and an appropriate upload mechanism, rather than granting extra out-of-scope permissions.

### 7.6. Workload Reading a Bucket Using Resource Identity

Suppose dynamic group `LabAppRuntime` selects only the instances authorized to run the application:

~~~text
Allow dynamic-group 'Default'/'LabAppRuntime' to read objects in compartment LabData where target.bucket.name = 'lab-input'
~~~

The application uses the corresponding resource-identity authentication mechanism, such as instance principals on Compute when properly configured. Do not grant bucket read access to a deployer's personal account and embed that private key in the application.

If the dynamic group matches every instance in `LabApp`, anyone able to launch instances or control code running on those instances can access the workload's permissions. Evaluate indirect membership management, code deployment capabilities, and permissions on target resources together.

## 8. Analyzing Cross-Service Dependent Permissions

Deploying an instance involves more than just the `instances` resource type. `LaunchInstance` can also require permissions to use subnets, VNICs, NSGs, images, and related resources depending on configuration. [Oracle: Details for Verb + Resource-Type Combinations](https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/corepolicyreference_topic-Details_for_Verb__ResourceType_Combinations.htm)

In the example tree, instances live in `LabApp`, subnets in `LabNetwork`, and input data in `LabData`. Those are three separate permission scopes:

~~~mermaid
flowchart LR
    G["Deployment principal"] --> A["Compute lifecycle access in LabApp"]
    G --> N["Network usage access in LabNetwork"]
    R["Post-deploy workload identity"] --> D["Bucket read access in LabData"]
    A --> VM["Application instance"]
    N --> VM
    VM --> R
~~~

The diagram separates the deployment principal from the application identity. They may be operated by the same team, yet they do not need the same permission set.

### 8.1. How to Analyze a Deployment Operation

1. Select the specific operation and deployment configuration.
2. Consult the permission table for that operation.
3. Map each dependent resource to its actual compartment.
4. Identify permissions required to create, use, and observe results.
5. Separate application runtime permissions from deployment permissions.
6. Check newly introduced permissions when adding features such as volumes, custom keys, or custom images.

Statements such as the following can form **part** of network usage access, not a complete deployment permission set:

~~~text
Allow group 'Default'/'LabDeployers' to use subnets in compartment LabNetwork
Allow group 'Default'/'LabDeployers' to use network-security-groups in compartment LabNetwork
~~~

Do not interpret those two lines as a guarantee every instance launch configuration will succeed. Nor should you add `manage virtual-network-family` when all that is missing is one identified dependent usage permission.

### 8.2. Console Observation Permissions May Differ from Minimal API Flows

The Console may call multiple APIs to populate dropdowns, tabs, and related details. A permission set sufficient for a direct API operation may not make every UI screen render completely.

Decide whether users genuinely need that Console flow. If yes, add the justified discovery permissions; if no, keep the appropriate API or automation flow. Do not treat every missing-data notice in the Console as justification for granting full-service admin access.

## 9. Evaluating Effective Permissions and Expansion Risks

### 9.1. Narrow Statements Do Not Cancel Broad Grants from Other Sources

When reviewing Allow policies in this lesson, combine all related grant sources. A user can receive permissions across multiple groups and multiple policies. Adding a bucket-scoped statement does not remove broad permissions already granted by another statement. [Oracle: IAM Policies Overview](https://docs.oracle.com/en-us/iaas/Content/Identity/policieshow/Policy_Basics.htm)

For example, An belongs to `LabInputReaders` while also belonging to a group managing all of `object-family` at `Labs`. A condition reading only `lab-input` does not prove An lost access to other buckets.

Therefore, reviews must cover:

- All user memberships and associated administrator roles.
- Effective policies from tenancy, parent compartments, and target compartment.
- Unconditional statements or statements with broader scopes.
- Dynamic groups and workload membership selection mechanisms.
- Data access paths outside the IAM policies under review.

### 9.2. Permissions That Can Alter Boundaries

Certain permissions should be evaluated by their ability to expand effective access:

| Capability | Why It Requires Separate Review |
| --- | --- |
| Edit policies | Can change which permissions are granted within the managed scope |
| Edit group memberships | Can add more people into existing permission sets |
| Edit dynamic groups or matching rules | Can bring additional workloads into runtime permissions |
| Create or control instances holding runtime rights | Can allow different code to assume the workload identity |
| Edit tags used for access grants | Can alter whether resources/principals satisfy conditions |
| Read secrets or sensitive data | Can open access paths beyond the target resource under review |
| Create data-sharing links | Can open a data access path independent of user profiles |

Do not ask only "can they delete?" Permissions to alter identities, executable code, network configurations, or secrets can also create major impact.

If using tag-based access control, control who can assign or modify the relevant tags. Never build a boundary on an attribute that the permission recipient can edit freely.

## 10. Verifying Against an Allowed and Out-of-Scope Matrix

Permission verification must include both positive tests and out-of-scope negative tests. Running one successful operation does not prove the permission set is minimal.

| Role | Permitted Test | Out-of-Scope Test |
| --- | --- | --- |
| `LabComputeViewers` | List/Get instances in `LabApp` | Update configuration or read instances outside approved scope |
| `LabPowerOperators` | Approved power action on test instance | Manage networking or delete instance |
| `LabInputReaders` | Read `lab-input` bucket/objects | Read another bucket or alter sharing settings |
| `LabReportWriters` | Create new object via approved method | Read, overwrite, or delete objects |
| `LabAppRuntime` | Read input object using workload identity | Access an ungranted bucket |

This is a test plan. Operations that can write data, disrupt services, or delete resources may only be tested on authorized lab objects under an approved plan; never use production resources to test an expected denial.

### 10.1. Confirm the Exact Principal Under Test

With the CLI, verify the active profile and authentication type. A terminal still using administrative credentials will skew results even if the tester believes they are testing a read-only group.

For workloads, verify requests genuinely use instance principals or the chosen mechanism, rather than a leftover API key in config. With the Console, use an isolated session to avoid confusing accounts or contexts.

### 10.2. Resources Must Exist and Be in Scope

A request failing because of a wrong OCID or nonexistent resource does not prove IAM blocked access as designed. Administrators must confirm the test target before evaluating results.

Similarly, timeouts, TLS errors, or DNS failures are not evidence of policy denial. Record the exact error layer and draw conclusions only from valid evidence.

### 10.3. Test Records

Each test should record:

- Identity and authentication method.
- Relevant group or dynamic group.
- Policy/statement expected to grant access.
- Operation, target resource, and target compartment.
- Region if the operation is region-dependent.
- Expected result and actual result.
- Timestamp and request ID when available.

Never store private keys, tokens, or secrets in test records. If prerequisites for running a test are unmet, mark it as unverified rather than marking it passed by assumption.

## 11. Hands-On Lab: Restricting Reads to a Single Bucket

### 11.1. Preparation

You need an authorized lab environment with:

- A confirmed compartment tree or equivalent scope.
- Two existing test buckets in `LabData`: `lab-input` and `lab-other`.
- Mock data containing no sensitive information.
- The `LabInputReaders` group and a test user holding no broad permissions from other sources.
- An independent administrative account authorized to apply policies.
- OCI CLI connected using the test user's profile.

The tests below only read configuration and object lists; they do not require creating buckets or deploying Compute. If test objects are missing, follow lab procedures rather than creating billable resources yourself as substitutes.

### 11.2. Apply the Exact Permission Set

An authorized administrator adds the two statements from section 7.4 at the appropriate place in the compartment tree. Verify memberships and inspect other permission sources before running tests.

Do not assign the test user to an administrator group to work around a setup issue.

### 11.3. Test the Permitted Path

PowerShell example, using a dedicated API key profile for the test user:

~~~powershell
$labNamespace = '<OBJECT_STORAGE_NAMESPACE>'
oci os bucket get --namespace-name $labNamespace --bucket-name 'lab-input' --profile LAB_READER --auth api_key
oci os object list --namespace-name $labNamespace --bucket-name 'lab-input' --profile LAB_READER --auth api_key --limit 5
~~~

Replace placeholders and profile names with actual lab values. If using a session token, select the appropriate profile and `--auth security_token`.

The expected result is retrieving details of the specified bucket and listing objects in that bucket. An empty list can still be a valid result if the bucket has no objects yet; do not confuse it with a permission error.

### 11.4. Test the Out-of-Scope Bucket

After the administrator confirms `lab-other` exists:

~~~powershell
oci os bucket get --namespace-name $labNamespace --bucket-name 'lab-other' --profile LAB_READER --auth api_key
~~~

With the described permission set and no additional grants, this request is not permitted. The service may return an unauthorized or not-found error; cross-check the outcome against administrator-confirmed resource existence.

If the request succeeds, look for broader grant sources or check which credentials are actually in use. Do not conclude the condition was ignored before ruling out those sources.

### 11.5. Revoke and Re-Verify

Remove the user from the test group according to procedure. Read back memberships, then re-test the previously permitted request once the change has taken effect in the appropriate authentication context.

Do not commit to a fixed number of seconds for all IAM changes. If permissions persist beyond the runbook wait threshold, investigate policies, groups, sessions, and the effective identity.

At the end of the lab, archive required evidence and clean up exercise-specific objects per authorization. Do not delete shared buckets or data belonging to other exercises.

## 12. Operating and Narrowing Permissions Over Time

A permission set appropriate at deployment can become excessive as job duties evolve. Bring policies into a governance lifecycle:

1. **Request:** state the task, scope, and duration.
2. **Design:** build the operation–permission–resource–compartment matrix.
3. **Approve:** confirm the owner accountable for resources and risk.
4. **Apply:** update memberships or policies with an audit trail.
5. **Verify:** run positive and out-of-scope tests.
6. **Monitor:** observe relevant activity and configuration changes.
7. **Review:** remove permissions when the task ends or expires.

With automation, policies can be managed as code, reviewed for changes, and rolled back to known versions. Automated deployment permissions must also be bounded; a pipeline able to edit any policy does not become low-risk just because it is a pipeline.

Usage logs help detect unused permissions but are not the sole proof. A permission unused recently might serve incident recovery; review its purpose and approver before removing it.

Temporary permissions should have an expiration mechanism or tracked revocation task in the governance system. Never assume putting the word "temporary" in a group name automatically expires permissions.

## 13. Relationship to Cost and Availability

Least-privilege design shrinks the blast radius of mistakes or compromised credentials:

- Properly scoped resource creation rights curb unplanned deployments, though cost controls and quotas are still needed.
- Power action permissions can disrupt services even without permission to delete instances.
- Permissions to delete backups or rotate encryption keys can impair recoverability.
- Network modification permissions can break connectivity or open additional data access paths.
- Permissions to read secrets, wallets, or data can create impact beyond the resources displayed in the Console.

Conversely, over-revoking without checking dependent permissions can break pipelines, prevent applications from reading data, or strip on-call engineers of incident response capabilities. Test legitimate tasks and maintain a controlled emergency administration path.

The goal is a permission set that is **sufficient for approved tasks and provably bounded**, reviewed against compartment structure, service resource groups, and actual identities in use. When every permission's existence can be explained, operations teams can maintain, investigate, and revoke access far more reliably as OCI infrastructure evolves.
