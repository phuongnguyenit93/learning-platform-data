# IAM Policy Syntax with Subject, Verb, Resource, and Location

## Objectives and Scope

An IAM policy in Oracle Cloud Infrastructure (OCI) answers the question: **which principal is allowed to perform which type of action, on which resource type, in which scope?** Reading these four parts accurately helps you grant permissions for VCN, Compute, storage, and database labs without defaulting to tenancy-wide privileges.

This lesson belongs to the **IAM Identity and Access Management** chapter. After this lesson, you will be able to:

- Break down a policy statement into subject, verb, resource-type, and location.
- Write a subject with the correct identity domain or OCID.
- Look up specific API permissions instead of guessing from the verb name alone.
- Distinguish between the granted scope, policy attachment location, and inheritance effects.
- Add simple conditions and verify both permitted and out-of-scope access.

The examples use hypothetical group, compartment, and bucket names. They illustrate syntax and must be replaced with actual resources and identifiers before applying. Oracle documentation was cross-checked on **November 20, 2026**; verify detailed service permissions before deployment.

## 1. Syntax Framework and How to Read a Statement

Basic syntax:

```text
Allow <subject> to <verb> <resource-type> in <location>
```

You can restrict further with conditions:

```text
Allow <subject> to <verb> <resource-type> in <location> where <conditions>
```

A policy can contain multiple statements. In this lesson, always specify the location explicitly; detailed Oracle documentation defines this as a mandatory component. See [IAM Policies Overview](https://docs.oracle.com/en-us/iaas/Content/Identity/policieshow/Policy_Basics.htm) and [Locations](https://docs.oracle.com/en-us/iaas/Content/Identity/policysyntax/location.htm).

Running example:

```text
Allow group 'Default'/'LabVmReaders' to read instances in compartment Lab
```

Assume `Lab` is a direct child compartment of root and the policy is created at root.

| Part | Value in Example | Interpretation |
| --- | --- | --- |
| Subject | `group 'Default'/'LabVmReaders'` | The `LabVmReaders` group in the `Default` identity domain |
| Verb | `read` | Read level as defined for the resource-type |
| Resource-type | `instances` | Compute instances, not all Compute resources |
| Location | `compartment Lab` | The `Lab` compartment scope, plus downward inheritance |

Read it as a sentence: "Allow the LabVmReaders group in the Default domain to read instances in Lab." Then look up which permissions and APIs `read instances` covers.

A policy name, such as `lab-vm-readers-policy`, is for managing the policy object. The name does not override the statements inside. A policy named "ReadOnly" can still contain a statement granting `manage` if the author configures it that way.

### 1.1. IAM Policies Grant Permissions, Not Sign-On Rules

Within the syntax scope covered here, statements begin with `Allow`; this is the mechanism for granting resource access. It differs from sign-on policies used to require MFA during sign-in. Oracle notes that policies only grant permissions and do not have `Deny` statements in [IAM Policies Overview](https://docs.oracle.com/en-us/iaas/Content/Identity/policieshow/Policy_Basics.htm).

A user may have authenticated with MFA yet still receive an API denial due to missing permissions. Conversely, having IAM permissions will not make a password or MFA device work again when the sign-in path fails.

## 2. Subject: Who Receives Permission?

### 2.1. Groups in an Identity Domain

For human users, the standard approach is granting permissions to a group and managing group memberships. When using names, specify the identity domain:

```text
Allow group 'Default'/'LabVmReaders' to read instances in compartment Lab
```

If the group resides in another domain:

```text
Allow group 'Engineering'/'LabVmReaders' to read instances in compartment Lab
```

Two groups with the same name in two domains are two different subjects. Never check only the group name while ignoring the user's and group's domain.

The domain portion can be omitted for groups in Default; the policy then resolves against the Default domain. Writing it out explicitly makes examples and configurations easier to read. See [Subjects](https://docs.oracle.com/en-us/iaas/Content/Identity/policysyntax/subject.htm).

For names containing spaces, preserve the proper single-quote syntax, for example:

```text
Allow group 'Engineering'/'Lab VM Readers' to read instances in compartment Lab
```

### 2.2. Using a Group's OCID

You can specify a group by OCID:

```text
Allow group id <GROUP_OCID> to read instances in compartment Lab
```

`<GROUP_OCID>` is a placeholder that must be replaced with the actual group OCID, including removing `<` and `>`. Do not substitute a user OCID or identity domain OCID. OCID syntax is also covered in [Subjects](https://docs.oracle.com/en-us/iaas/Content/Identity/policysyntax/subject.htm).

Using names is convenient for readability; using OCIDs ensures an unambiguous reference to a specific object. With either approach, still record which environment the group belongs to and who is allowed to modify memberships.

### 2.3. Dynamic Groups and Service Principals

A subject can also be a dynamic group or an OCI service. Dynamic groups apply to resources matching a matching rule; a resource's membership in the group and the policy granting permissions to the group are two separate configurations. Service principals are used in scenarios where a service needs to act on your behalf.

Syntax framework example for a dynamic group:

```text
Allow dynamic-group 'Default'/'LabInstances' to read objects in compartment Lab
```

This line illustrates a subject for resources running workloads, not a human user group. It also grants permission to read objects across the entire corresponding Lab scope, so it is not yet restricted to a single bucket.

Do not change `group` to `dynamic-group` merely to fix a user sign-in error. When moving to automation, determine which principal type the SDK, CLI, or service actually uses when calling APIs.

Broad subjects such as `any-user` or `any-group` have a different scope from a specific lab group. Use them only when you understand all covered principals and required restricting conditions; do not use them as a shortcut to make an API stop reporting missing permissions.

## 3. Verb: What Level of Permission Is Granted?

The four common verbs in ascending order are:

```text
inspect → read → use → manage
```

| Verb | General Meaning |
| --- | --- |
| `inspect` | Ability to observe or list per resource-type; exceptions exist regarding returned metadata |
| `read` | Includes `inspect` plus additional read capabilities per resource type |
| `use` | Includes `read` plus operations on existing resources as defined by the service |
| `manage` | Includes all permissions for the resource-type within the statement's scope |

This is a guideline, not a strict CRUD table applicable uniformly across all services. `use` typically excludes create/delete; some update operations also require `manage`. See [Verbs](https://docs.oracle.com/en-us/iaas/Content/Identity/policieshow/Verbs.htm).

### 3.1. Verbs Only Have Concrete Meaning Together with Resource-Types

Each combination of verb and resource-type maps to a set of **permissions** defined by Oracle. An API operation requires one or more permissions. Therefore, look them up along this chain:

```text
User requirement
    → API operation
    → required permissions
    → verb + resource-type that grant those permissions
    → appropriate location and conditions
```

For example, `inspect volumes` and `read volumes` do not necessarily differ in permissions; Oracle notes cases where there is no additional permission between these two levels in [Advanced Policy Features — Relation to Verbs](https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/policyadvancedfeatures.htm).

A notable point for the Compute example: according to current reference tables, `ListInstances` and `GetInstance` both use `INSTANCE_READ`, which is covered by `read instances`. Never assume an API named "List..." always requires only `inspect`. See [Permissions Required for Each API Operation](https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/corepolicyreference_topic-Permissions_Required_for_Each_API_Operation.htm).

### 3.2. Observational Permissions Can Still Expose Notable Information

`inspect` does not guarantee every response contains only names and OCIDs. For instance, inspecting policies can reveal policy contents; inspecting networking resources can include routes or security rules. Exceptions are documented by Oracle at [Verbs](https://docs.oracle.com/en-us/iaas/Content/Identity/policieshow/Verbs.htm).

Similarly, permission to read instance details does not mean seeing only a VM icon in the Console. When deciding grants, examine what data the API returns and avoid placing secrets in metadata while assuming readers cannot view them.

### 3.3. Choose Permissions by Task, Not by Job Title

A requirement to "read VM configurations" leads to checking read APIs. A requirement to "administer the system" must be broken down into specific tasks: reading, updating, operating, creating, or deleting which resources.

Do not pick `manage` simply because the user belongs to an engineering team. For an observation-only lab, granting create/delete widens both data-impact blast radius and cost risk unnecessarily for the lesson.

## 4. Resource: Which Resource Type?

Resource-type names belong to the policy language, not arbitrary service names in the UI.

| Resource-Type Example | Scope Interpretation |
| --- | --- |
| `instances` | Compute instances |
| `vcns` | Virtual Cloud Networks |
| `volumes` | Block volumes as defined by the service |
| `buckets` | Object Storage buckets |
| `objects` | Objects inside buckets |

A VM named `java-lab-01` is not a resource-type. Nor does "Compute" on the navigation menu automatically become a `compute` keyword in policies. Look up the resource-types published by Oracle for each service.

### 4.1. Individual Resource-Types vs. Resource Families

A family groups resource-types commonly managed together, such as `virtual-network-family`, `volume-family`, and `object-family`. Choosing a family reduces statement count but typically expands the covered resource types. See [Resources](https://docs.oracle.com/en-us/iaas/Content/Identity/policiesgs/policies_topic-ResourceTypes.htm).

Compare:

```text
Allow group 'Default'/'LabNetworkReaders' to read vcns in compartment Lab
```

```text
Allow group 'Default'/'LabNetworkReaders' to read virtual-network-family in compartment Lab
```

The two statements are not equivalent in resource scope. The second line covers additional networking components in the family; do not substitute it for the first without reviewing requirements.

`instance-family` also includes additional permissions documented separately by Oracle. Do not assume every family is just the list of names visible in the Console. As services add new resource-types, family definitions can also expand. See [Details for the Core Services](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/corepolicyreference.htm) and [Resources](https://docs.oracle.com/en-us/iaas/Content/Identity/policiesgs/policies_topic-ResourceTypes.htm).

### 4.2. `all-resources` Is a Broad Scope

```text
Allow group 'Default'/'LabAdmins' to manage all-resources in compartment Lab
```

This statement grants broad permissions across Lab along with inheritance effects, not just for a single lab VM. Use it only when the genuine requirement is administering that entire scope and group membership is strictly controlled.

Changing `compartment Lab` to `tenancy` expands the scope to the entire tenancy for the granted resources. That is not a routine fix for missing-permission errors.

## 5. Location: Where Do Permissions Take Effect?

Common locations are `tenancy`, `compartment <name>`, or `compartment id <OCID>`. When using compartment names, resolution depends on where the policy is created; nested compartment paths use colons. Region and Availability Domain cannot be substituted directly for location; to restrict by them, use appropriate conditions. See [Locations](https://docs.oracle.com/en-us/iaas/Content/Identity/policysyntax/location.htm).

Suppose you have this compartment tree:

```text
Root tenancy
├── Lab
│   ├── ComputeLab
│   └── NetworkLab
└── Production
```

### 5.1. Scope of a Compartment Branch

With a policy placed at root:

```text
Allow group 'Default'/'LabVmReaders' to read instances in compartment Lab
```

This permission applies to instances in Lab and its child branch via inheritance, so ComputeLab and NetworkLab are included if they contain instances. Do not assume the user can also read instances in Production.

If only ComputeLab is needed, write the explicit path from the policy attachment location:

```text
Allow group 'Default'/'LabVmReaders' to read instances in compartment Lab:ComputeLab
```

You can reference the compartment by OCID:

```text
Allow group 'Default'/'LabVmReaders' to read instances in compartment id <COMPUTE_LAB_COMPARTMENT_OCID>
```

The placeholder string must be replaced with the actual **compartment** OCID. Do not use an instance OCID or identity domain OCID here.

### 5.2. Statement Scope Differs from Policy Attachment Location

**Policy attachment** is where the policy object is stored/attached in the compartment hierarchy. It determines policy administration scope and who can edit or delete that policy. Oracle explains this mechanism in [Policy Attachment](https://docs.oracle.com/en-us/iaas/Content/Identity/policieshow/Policy_Attachment.htm).

For example, a policy placed at root can still contain a statement granting only `read instances in compartment Lab`. Attaching the policy object at root does not automatically turn the statement's location into `tenancy`.

Conversely, attaching a policy at a child compartment does not allow that compartment's administrators to grant permissions across other branches. When organizing policy administration privileges, consider both attachment placement and referenceable scope.

In the example tree, if creating the policy at Lab to reference direct child compartment ComputeLab, the name-based location can be:

```text
Allow group 'Default'/'LabVmReaders' to read instances in compartment ComputeLab
```

This line must be read alongside the context "policy is created at Lab." Moving it to root without updating the location can break compartment name resolution.

### 5.3. Inheritance from Parent to Child

Compartments inherit permissions from policies effective at parent levels. If you grant resource management permissions in Lab, those permissions continue down to child compartments within that scope. See [Policy Inheritance](https://docs.oracle.com/en-us/iaas/Content/Identity/policieshow/Policy_Inheritance.htm).

Learning example:

```text
Allow group 'Default'/'LabNetworkAdmins' to manage virtual-network-family in compartment Lab
```

If you want to create an observation-only area within the Lab branch, adding a `read` statement at a child compartment does not remove the `manage` permission the same user already inherited from the parent. You must redesign the groups or narrow the broader parent grant.

Inheritance promotes consistent administration, which is also why you must inspect root and ancestor policies whenever someone has more permissions than expected.

## 6. Conditions: Narrowing Grants When the Four Basic Parts Are Not Enough

`where` adds conditions a request must satisfy to receive permission from that statement. For example, allowing a group to read objects in the `lab-input` bucket:

```text
Allow group 'Default'/'LabObjectReaders' to read objects in compartment Lab where target.bucket.name = 'lab-input'
```

Assume the bucket belongs to Lab and the `target.bucket.name` variable is supported for the required operation. Oracle documents this variable in [Details for Object Storage and Archive Storage](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/objectstoragepolicyreference.htm).

### 6.1. Single Condition, AND, and OR

Syntax framework:

```text
where <variable> = '<value>'
where all {<condition-1>, <condition-2>}
where any {<condition-1>, <condition-2>}
```

- `all` requires every condition in the set to evaluate true.
- `any` requires at least one condition in the set to evaluate true.
- String values are enclosed in single quotes per syntax.

Example allowing reading objects in either of two buckets:

```text
Allow group 'Default'/'LabObjectReaders' to read objects in compartment Lab where any {target.bucket.name = 'lab-input', target.bucket.name = 'lab-reference'}
```

See [Conditions](https://docs.oracle.com/en-us/iaas/Content/Identity/policysyntax/conditions.htm). Do not use SQL keywords like `AND` or `OR`, or insert JSON into a plain-text policy statement.

### 6.2. Condition Variables Must Match the API

Not every request carries every target attribute. If a variable does not apply to a request, the condition cannot grant permission for that request. For instance, a condition targeting a single specific target may not work for an API listing multiple targets. See [Advanced Policy Features — Variables that Aren't Applicable to a Request](https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/policyadvancedfeatures.htm).

Therefore, when a list operation is denied while reading a known resource works, check supported variables and permissions for each API. Do not hastily strip all conditions or switch to `manage all-resources`.

An important note: **condition matching is case-insensitive**, even when a service's resource names are case-sensitive. A condition matching `BucketA` can also match `bucketA`. Oracle gives this example in [Conditions](https://docs.oracle.com/en-us/iaas/Content/Identity/policysyntax/conditions.htm). Do not rely on letter-case differences to design access boundaries between two buckets.

### 6.3. Conditions Restrict a Statement, Not Other Grants

Suppose the same user receives:

```text
Allow group 'Default'/'LabObjectReaders' to read objects in compartment Lab where target.bucket.name = 'lab-input'
```

and from another group:

```text
Allow group 'Default'/'LabStorageAdmins' to manage object-family in compartment Lab
```

If that person belongs to both groups, the first statement does not constrain the broad permissions granted by the second statement. To restrict reads to only the target bucket, address the broader grant source or group memberships.

This is why permission audits must examine all groups and grants matching a principal. Placing a narrow statement before a broad statement does not create a deny rule.

## 7. A Single Task May Require Multiple Permissions

APIs do not necessarily correspond one-to-one with a single resource-type. For example, creating a VM also involves images and networking; attaching a volume involves volumes, attachments, and instances. Required permissions are listed per API in [Permissions Required for Each API Operation](https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/corepolicyreference_topic-Permissions_Required_for_Each_API_Operation.htm).

A statement such as:

```text
Allow group 'Default'/'LabVmBuilders' to manage instances in compartment Lab
```

is insufficient to conclude the group has all permissions required for a Console VM creation flow. Users may also need read permissions for UI selection lists and access to dependent components.

Analyze according to each actual operation:

1. Identify the denied API, not just the Console button name.
2. Look up the permissions required by that API.
3. Look up the verb/resource-type combinations providing those permissions.
4. Determine the compartment of each involved resource.
5. Verify principals and conditions on each required grant.

For example, a VM is created in Lab while its subnet resides in a shared Networking compartment. Checking only `instances` permissions in Lab will miss the networking access in Networking.

Required grants may span multiple policies or come from multiple groups held by the same user, as Oracle explains in [Resources — Access That Requires Several Resource Types](https://docs.oracle.com/en-us/iaas/Content/Identity/policiesgs/policies_topic-ResourceTypes.htm). Saving a statement successfully only proves valid syntax; it does not prove the entire workflow succeeds.

## 8. Three Practical Examples with Clear Boundaries

In all three examples below, assume policies are at root, the named compartments are direct children of root, groups already exist, and test users receive no broader permissions elsewhere.

### 8.1. Reading Lab VM Details

```text
Allow group 'Default'/'LabVmReaders' to read instances in compartment Lab
```

The goal is reading Compute instance details. It does not grant permission to operate VMs, SSH in, or read every service in Lab.

Per current Compute tables, `read instances` covers `ListInstances` and `GetInstance`. Steps such as viewing IP addresses via VNICs or inspecting related resources may require separate permissions. See [Details for the Core Services](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/corepolicyreference.htm).

### 8.2. Listing Lab Buckets and Reading Objects in One Bucket

```text
Allow group 'Default'/'LabObjectReaders' to inspect buckets in compartment Lab
Allow group 'Default'/'LabObjectReaders' to read objects in compartment Lab where target.bucket.name = 'lab-input'
```

The two lines separate viewing the bucket list from reading objects. Per service permission tables, `inspect buckets` covers `ListBuckets`, while `read objects` includes reading objects via `GetObject`. See [Details for Object Storage and Archive Storage](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/objectstoragepolicyreference.htm).

This illustrates the stated APIs, not a promise that every Object Storage UI screen will work. If the Console requires `GetBucket` or another API, look up the additional permission and grant it only as needed. Never expand from reading one bucket to managing all of Object Storage just to clear an error on one screen.

### 8.3. Network Administration in a Dedicated Compartment

```text
Allow group 'Default'/'LabNetworkAdmins' to manage virtual-network-family in compartment Networking
```

The group receives broad permissions over the networking family in Networking. This example suits delegating responsibilities to a lab networking team; it is not a default permission level for someone merely deploying a Java application.

A user in this group can alter components affecting connectivity and network security within the granted scope. When a lab only needs to use an existing subnet, analyze permissions to use that resource instead of granting management over the entire family.

## 9. Workflow for Writing a Policy from a Real Requirement

Suppose the requirement is: "The support team may view VM details in Lab, and must not manage Production resources."

### Step 1 — Identify the Principal and Tasks

Specify the recipient group, the group's domain, the test user, and the APIs to call. "May view" must be made concrete as tasks such as listing instances or retrieving details of a known instance.

### Step 2 — Lock Down Resource and Scope

Choose `instances` if the goal is solely Compute instance details. Determine whether Lab has child compartments and whether propagating permissions down to them fits the requirement.

Record where the policy is placed. In this example placed at root with Lab as a direct child, the statement is:

```text
Allow group 'Default'/'LabVmReaders' to read instances in compartment Lab
```

Do not add permissions in Production simply because the user sees that compartment's name in the Console. Visibility of compartment structure and permission to read resources inside are two scopes that must be analyzed separately.

### Step 3 — Check Other Permission Sources

Before testing, verify the user does not belong to `Administrators` or another group granting broader permissions than intended. Review policies effective from root and parent compartments.

Someone who already holds administrative privileges can almost always perform the read operation in this example. Testing with that identity will not prove that the new policy granted the right access or enforced the intended boundary.

### Step 4 — Write Expectations for Both Permitted and Out-of-Scope Cases

| Task | Expectation When User Holds Only Lab `read instances` |
| --- | --- |
| `ListInstances` in Lab | Permitted for standard identified instance cases |
| `GetInstance` for a VM in Lab | Permitted |
| Read instance in a child branch of Lab | Account for inheritance; grants at Lab can apply downward |
| Read instance in Production | Not granted by this policy set |
| Read bucket or object merely because it is in Lab | Not granted by resource-type `instances` |
| Create, edit, or delete VM | Not granted by `read instances` |

This table reflects the lab model expectation and does not guarantee outcomes if the identity receives permissions from other sources. For APIs with special conditions, such as instances in a compute cluster, verify additional permissions in service documentation.

### Step 5 — Add Permissions Only for Identified Causes

If an intended API is denied, identify the missing permission and the compartment containing the relevant resource before editing the policy. Each change should answer "which operation is this line added to allow?"

Do not change subject, verb, resource, and location all at once by trial and error; you will struggle to tell which edit solved the issue and which permissions were broadened unnecessarily.

## 10. Hands-On Verification Using Read-Only APIs

### 10.1. Prepare the Test Environment

Use a lab tenancy you are authorized to manage, a reader group, and a test user without broad administrative privileges. Prepare:

- Exact identity domain and group name.
- Lab compartment plus an existing lab instance, if testing detail retrieval.
- Region containing the instance and actual compartment/instance OCIDs.
- An OCI CLI profile for the exact test user, configured with appropriate credentials.
- Notes on where the policy is attached, applied statements, and other user permissions.

There is no need to create extra VMs solely to test policy syntax in this lesson. If Lab has no instances yet, a successful list returning an empty list shows the API executed, though it does not verify reading a specific resource.

### 10.2. List Instances in Lab

PowerShell example, with placeholders that must be replaced before running:

```powershell
$profileName = 'LAB_VM_READER'
$regionId = 'REPLACE_WITH_REGION_ID'
$labCompartmentOcid = 'REPLACE_WITH_LAB_COMPARTMENT_OCID'

oci compute instance list --profile $profileName --region $regionId --compartment-id $labCompartmentOcid --all
```

Check the output, any error codes, and the exact compartment queried. `--all` fetches all result pages; it does not expand IAM permissions or scope across all compartments. See [OCI CLI — instance list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/compute/instance/list.html).

### 10.3. Read a Known Instance

```powershell
$instanceOcid = 'REPLACE_WITH_LAB_INSTANCE_OCID'

oci compute instance get --profile $profileName --region $regionId --instance-id $instanceOcid
```

This command retrieves instance details without starting or stopping the machine. See [OCI CLI — instance get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/compute/instance/get.html).

Displaying IP addresses may require additional VNIC API calls and corresponding permissions. Do not treat a successful `instance get` as proof that every operation on the VM details page is permitted.

### 10.4. Verify Out-of-Scope Boundaries with Read Operations

Use the same test identity and an out-of-scope test resource prepared by the administrator. Execute a read-only query to verify permissions are bounded as expected; never use delete or create operations to test a read-only grant.

If out-of-scope access succeeds, audit memberships, ancestor policies, and other grants before editing the lesson statement. The narrow statement may already be correct while the user inherits broad access from another group.

If the request fails, verify the exact region, OCID, and resource existence with the environment administrator. A request using wrong identifiers does not prove permission boundaries are functioning correctly.

### 10.5. Record Sufficient Evidence for Verification

Suggested template:

```text
Principal/profile used for testing:
Domain and granting group:
Policy attachment location:
Applied statement:
API or operation tested:
Target region, compartment, and resource:
Expected result:
Actual result:
Other permission sources checked:
Additional permissions needed, if any:
```

Never record private keys, tokens, or secret authentication configuration values in lab evidence. What matters is the link between the statement and observed API behavior.

## 11. Categorizing Common Errors

| Symptom | What to Check First |
| --- | --- |
| Cannot save statement | Keywords, `to`/`in` placement, quotes, condition braces, and valid resource-type |
| Group exists but user lacks permission | Right domain, right group, membership, and actual session/CLI principal |
| Can read Lab but Console sub-pages fail | Dependent APIs and permissions for related resource-types |
| Have `manage instances` yet cannot create VM | Image, subnet, VNIC, NSG, or related components per actual API |
| Policy is at root yet Production is unreadable | Statement location may only be Lab; attachment does not grant tenancy-wide scope |
| User can still manage resources after adding read rule | Another broad grant, another membership, or inherited policy |
| Condition works for one API but not another | Whether target variable applies to that request and which permissions the API requires |
| Compartment name resolves unexpectedly | Policy attachment point, compartment path, duplicate names, or wrong OCID type |
| Read command returns no resources | Region, compartment, filters, identifier, and permissions; an empty list does not guarantee missing access |

Some errors sit outside IAM: quotas, service limits, capacity, network configuration, or resource state. Having the right permissions does not guarantee every deployment action succeeds. Preserve exact error details and categorize before expanding permissions.

## 12. Completion Criteria

You have completed this lesson when you can:

- Read a statement as a full sentence specifying subject, permission level, resource type, and scope.
- Write subjects with the correct domain or OCID without confusing users, groups, and dynamic groups.
- Trace at least one API to its required permissions and corresponding verb/resource-type combination.
- Explain statement scope, policy attachment location, and inheritance effects.
- Explain why a narrow condition does not revoke a broad grant from another policy.
- Write a policy to read resources in Lab, test with a low-privilege identity, and verify out-of-scope behavior.
- Document test limitations and avoid using tenancy-wide admin privileges to mask specific missing-permission errors.

When reading or writing policies for VCN, Compute, storage, or Oracle databases in subsequent lessons, start from the task to be performed and identify all four parts and related permissions. This keeps access aligned with practical requirements while keeping blast radius and costs under control.
