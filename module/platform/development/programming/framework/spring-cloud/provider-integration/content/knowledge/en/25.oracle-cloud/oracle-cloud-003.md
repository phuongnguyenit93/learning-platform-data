# Tenancy, Compartment, OCID, Region, and OCI IAM Policy

When deploying a Spring Boot application on Oracle Cloud Infrastructure (OCI), four questions must be answered before calling any API: which tenancy owns the resource, which compartment it lives in, what OCID identifies it, and which region it resides in? Then IAM policies decide which actions a workload or user is allowed to perform on that resource.

These concepts are interconnected but not interchangeable:

- **Tenancy** is the OCI account/organization boundary, containing the root compartment, identities, and the organization's resources.
- **Compartment** is a logical boundary for organizing resources, assigning permissions, and managing costs.
- **OCID** is a unique identifier assigned by Oracle to nearly every OCI resource.
- **Region** is the geographical area where services are deployed; a tenancy must subscribe to a region before using it.
- **OCI IAM policy** is a set of statements granting permissions to users, groups, dynamic groups, or workload principals over resource types within a tenancy/compartment.

A common mistake is using the right API endpoint with the wrong compartment OCID, or creating the right compartment without attaching a policy for the workload. The result is typically "resource not found", authorization failures, or an application that only runs under an administrator account. This lesson builds the mental model from tenancy down to policies and connects it to the OCI Java SDK in Spring Boot.

This lesson belongs to the **Oracle Cloud** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module focuses on integrating Spring Boot with managed services across AWS, Azure, and Google Cloud via the respective Spring Cloud libraries. This lesson focuses on understanding tenancy, compartment, OCID, and region structures, designing least-privilege OCI IAM policies, and configuring OCI SDK identities appropriate for the runtime environment.

## 1. Learning Objectives and Running Scenario

After this lesson, you can:

1. Explain tenancy, root compartment, compartment hierarchy, and policy inheritance.
2. Distinguish a compartment from a region, availability domain, and fault domain.
3. Read OCID structure, locate the right OCID, and use OCIDs in configuration/APIs/policies.
4. Understand home region, realm, and region subscription.
5. Write policy statements by subject, verb, resource type, location, and condition.
6. Choose the right verb: `inspect`, `read`, `use`, or `manage`.
7. Create dynamic groups for Compute instance principals and policies for workloads.
8. Distinguish API key authentication, instance principals, resource principals, and OKE workload identity.
9. Configure OCI Java SDK clients in Spring Boot for local development and production.
10. Troubleshoot authorization errors, wrong OCIDs, wrong regions, and policy scope issues.

Running scenario: **document-service** runs on OCI Compute or Oracle Kubernetes Engine (OKE), reads contracts from Object Storage, and writes metadata to a database. The bucket lives in the `AppData` compartment, compute workloads run in the `AppRuntime` compartment, and the operations team is managed separately. The application must read the right bucket/objects without using an administrator's API key.

~~~mermaid
flowchart TD
    T["Tenancy / Root Compartment"] --> P["Platform"]
    P --> R["AppRuntime"]
    P --> D["AppData"]
    P --> O["Observability"]
    R --> W["Spring Boot workload"]
    D --> S["Object Storage bucket"]
    W --> I["OCI IAM principal"]
    I --> G["Group / Dynamic Group / Workload Identity"]
    G --> POL["OCI IAM policy"]
    POL --> S
    W --> SDK["OCI Java SDK"]
    SDK --> S
~~~

**Permissions do not come from the application knowing an OCID.** An OCID identifies the resource; an IAM policy grants a principal permission to operate on that resource.

## 2. Tenancy and Root Compartment

### 2.1. What Is a Tenancy?

A tenancy is the OCI account of an organization or customer. When signing up for OCI, Oracle creates a tenancy and assigns a tenancy OCID. The tenancy is the scope for managing identity, region subscriptions, quotas/service limits, compartments, and resources.

A tenancy has these main components:

- A root compartment representing the entire tenancy.
- Child compartments to partition resources by environment, product, or team.
- Identity domains, users, groups, dynamic groups, and federation.
- IAM policies defining permissions.
- Region subscriptions for areas the tenancy is permitted to use.
- Compute, network, storage, database, observability, and other service resources.

The tenancy OCID is used in many APIs and SDK configurations. Do not confuse the tenancy OCID with a user OCID, compartment OCID, or a specific resource's OCID.

### 2.2. Root Compartment

When a tenancy is created, OCI provides a root compartment. The root compartment is the tenancy itself and can hold resources directly, though it is standard practice to create child compartments to separate responsibilities.

Example:

~~~text
Tenancy (root)
└── Platform
    ├── Shared-Network
    ├── AppRuntime
    ├── AppData
    └── Observability
~~~

In real-world designs, you can organize by environment first:

~~~text
Tenancy
├── Network
├── Development
│   ├── Runtime
│   └── Data
├── Staging
│   ├── Runtime
│   └── Data
└── Production
    ├── Runtime
    ├── Data
    └── Security
~~~

Or organize by product/owning team:

~~~text
Tenancy
├── Shared-Services
├── Finance
│   ├── Runtime
│   └── Data
└── Documents
    ├── Runtime
    └── Data
~~~

There is no single optimal compartment tree for every organization. Choose a structure reflecting permission boundaries, ownership, cost tracking, and operational requirements.

### 2.3. Tenancy and Compartments Are Not Regions

A compartment is a tenancy-wide IAM resource. One compartment can contain resources across multiple subscribed regions. When switching regions in the Console, the same compartment still exists; only the list of resources for the selected region changes.

This means:

- A single `AppData` compartment can contain a bucket in Singapore and a database in another region.
- An IAM policy applied to a compartment can be enforced across subscribed regions.
- A bucket/database's region is determined by the service and resource configuration, not by the compartment name.
- Compartments do not automatically replicate data or provide disaster recovery.

### 2.4. Compartment Limits and Operations

OCI supports multi-level hierarchies; current documentation cites a limit of up to six nested levels. Keep the tree simple so policy inheritance and ownership remain easy to understand.

A compartment typically has a name unique within its parent, a description, and an OCID. Names help humans read; OCIDs enable exact API references. Changing a display name does not turn an OCID into a different identifier.

Before deleting a compartment:

- Move or delete resources inside it according to procedure.
- Inspect policies attached to the compartment.
- Check service dependencies and backups.
- Check whether any workloads or automation still reference its resources.

Deleting a compartment is an asynchronous operation and the compartment must be empty. Do not treat renaming or deleting a compartment as a way to revoke a single permission; edit the policy at the appropriate scope instead.

## 3. Compartment Hierarchy and Policy Inheritance

### 3.1. Compartments as Logical Boundaries

Compartments help group resources by:

- Environment: dev, staging, production.
- Product: document, payment, analytics.
- Owning team: platform, security, finance.
- Data classification level.
- Governance and budget boundaries.

An OCI resource is normally created inside a compartment. Policies can be placed at the tenancy/root or at an appropriate compartment.

### 3.2. Policy Inheritance

Child compartments inherit permissions granted by policies on parent compartments. For example:

~~~text
Tenancy
└── Production
    ├── Documents
    └── Payments
~~~

If a policy is scoped to `Production`, granted permissions can flow down to `Documents` and `Payments`. If a policy is scoped only to `Documents`, permissions do not automatically propagate upward to `Production` or sideways to `Payments`.

Illustration:

~~~text
Allow group PlatformAuditors to inspect all-resources in compartment Production
~~~

Placed at the `Production` scope, this policy grants the auditors group permission to inspect resources in `Production` and its child compartments via inheritance.

Inheritance avoids duplicating policies, but it can also make permissions broader than intended. Before placing a policy on root or a parent compartment, review all affected child branches.

### 3.3. Where a Policy Lives vs. What Location States

A policy has two aspects:

- **Where the policy is stored:** tenancy/root or a compartment.
- **Location in the statement:** the tenancy or compartment where permissions apply.

For a policy created in the tenancy, the location can be `tenancy` or a specific compartment. For a policy created in a compartment, the default location is usually that compartment; referencing another compartment in the tree may require a compartment path using OCI syntax.

Example of a narrowly scoped policy:

~~~text
Allow group <identity-domain>/<DocumentReaders> to read objects in compartment AppData
~~~

Example of a policy at root that limits resources to the `Production` compartment:

~~~text
Allow group <identity-domain>/<ProductionAuditors> to inspect all-resources in compartment Production
~~~

Do not use `in tenancy` scope when only a single compartment is needed.

### 3.4. Moving Compartments

Moving a compartment to a different parent can change inherited policies. Previously granted permissions may disappear or be expanded by the new parent. Treat moving a compartment as a security change:

1. Identify the old parent and target parent.
2. Compare inherited policies on both branches.
3. Check policies referencing the compartment's name/OCID.
4. Execute the change with proper approval.
5. Test permissions after the move using actual principals.
6. Record an audit entry and update ownership diagrams.

## 4. OCID: Oracle Cloud Identifier

### 4.1. What Is an OCID Used For?

An OCID is a unique identifier assigned by OCI to most resources. Examples:

- Tenancy OCID.
- Compartment OCID.
- User/group/dynamic group OCID.
- Compute instance OCID.
- VCN, subnet, bucket, database, and key OCIDs.

OCIDs appear in the Console and API responses. Many API operations require an OCID to specify the target resource. Some policies allow using names instead of OCIDs; when names can collide across compartment branches or identity domains, OCIDs provide unambiguous references.

### 4.2. OCID Structure

General syntax:

~~~text
ocid1.<RESOURCE_TYPE>.<REALM>.[REGION][.FUTURE_USE].<UNIQUE_ID>
~~~

Components:

| Component | Meaning |
| --- | --- |
| `ocid1` | OCID format version |
| `RESOURCE_TYPE` | Resource type, e.g., `tenancy`, `compartment`, `instance`, `volume` |
| `REALM` | Realm to which the resource belongs |
| `REGION` | Region if the resource has regional/availability-domain scope |
| `FUTURE_USE` | Reserved for future use; currently may be empty |
| `UNIQUE_ID` | Unique identifier portion assigned by Oracle |

Structure examples:

~~~text
Tenancy:
ocid1.tenancy.oc1..<unique-id>

Compartment:
ocid1.compartment.oc1..<unique-id>

Instance:
ocid1.instance.oc1.phx.<unique-id>
~~~

These strings illustrate the format only and are not valid OCIDs for calling APIs. Copy real OCIDs from the Console/API.

### 4.3. Realm and Region Inside an OCID

A realm is a set of regions sharing certain entities and endpoint domains. For example, the commercial realm typically has the key `oc1`; Government realms have different keys. A tenancy belongs to one realm and cannot access regions outside its realm.

Some OCIDs include the region segment, but not all. Tenancies, compartments, and some IAM resources have tenancy-wide scope, so the region portion can be empty. Therefore, never infer every resource's location solely by splitting the OCID string.

### 4.4. Finding OCIDs in the Console

You can find OCIDs on each resource's detail page:

- Tenancy: Profile menu → Tenancy details.
- Compartment: Identity & Security → Compartments → select compartment.
- Compute instance: Compute → Instances → select instance.
- VCN: Networking → Virtual Cloud Networks.
- Bucket: Object Storage → Buckets → select bucket.

Copy the full OCID without truncating it. When placing it in configuration, verify that the resource type and tenancy/region match the target environment.

### 4.5. OCID vs. Display Name

| Attribute | Name / Display Name | OCID |
| --- | --- | --- |
| Human-readable | Yes | Less readable |
| Mutable | Many resources allow changing name/description | Issued by Oracle as an identifier |
| Used in APIs | Depends on operation | Very frequently |
| Used in policies | Allowed within proper scope | Allowed via `id` syntax |
| Is it a secret? | No | Not a secret, though inventory/config should be protected |

An OCID is not a credential. Knowing an OCID does not grant access. Still, avoid dumping entire resource inventories into public logs or unnecessary responses.

### 4.6. Storing OCIDs in Spring Boot

OCIDs and regions are environment configuration and should not be hard-coded into business logic:

~~~yaml
oci:
  tenancy-ocid: OCI_TENANCY_OCID
  compartment-ocid: OCI_COMPARTMENT_OCID
  region: ap-singapore-1
  auth-profile: DEFAULT
~~~

These are illustrative configuration keys. Separate config by profile/environment. Do not use dev OCIDs in production or vice versa. When an application needs multiple compartments, store a map by domain/service and validate OCIDs at startup or provisioning time.

## 5. Region, Realm, and Home Region

### 5.1. What Is a Region?

A region is a localized geographic area containing one or more availability domains. Regional resources are created in a specific region; API clients must send requests to the endpoint for the right region.

Examples of region identifiers:

~~~text
ap-singapore-1
ap-tokyo-1
us-ashburn-1
eu-frankfurt-1
~~~

A region identifier can differ from its abbreviated region key. In the Java SDK, use the official region identifier or the built-in SDK enum.

### 5.2. Realm

A realm is a group of regions sharing domain/identity boundaries. A tenancy belongs to one realm. A region in another realm cannot be added to a tenancy simply by changing an endpoint.

When integrating a custom endpoint or a new region, verify:

- The tenancy's realm.
- Whether the region belongs to that realm.
- Whether the SDK version recognizes the region.
- Whether the service is available in that region.
- That the endpoint domain matches the realm and region.

### 5.3. Home Region

When a tenancy is created, OCI designates a home region. The home region holds the master definitions of IAM resources such as:

- Users.
- Groups.
- Policies.
- Compartments.
- Dynamic groups.
- Federation resources.

The home region cannot be changed after the tenancy is provisioned. When calling APIs to create/update IAM resources, target the home region endpoint; IAM changes propagate to subscribed regions. The Console typically routes requests to the home region automatically.

Important point: the home region does not mean every application resource must reside there. Compute, VCNs, buckets, and databases can be deployed in other regions within the realm if the tenancy is subscribed and the service is supported.

### 5.4. Region Subscription

Region subscriptions happen at the tenancy level:

1. Open the Region menu in the OCI Console.
2. Select Manage Regions.
3. Choose the region to use.
4. Subscribe and wait for activation.

When subscribing to a new region, existing IAM policies take effect in that region. OCI does not allow unsubscribing from an infrastructure region once subscribed. Therefore, choosing a region should be treated as a governance and data-residency decision, not an arbitrary toggle.

### 5.5. Differing Scopes of IAM and Service Resources

| Resource Type | Typical Scope |
| --- | --- |
| Compartments, users, groups, policies | Cross-region / tenancy-wide |
| Object Storage bucket | Regional |
| VCN | Regional |
| Compute instance | Availability-domain-specific |
| Block volume | Availability-domain-specific |
| Certain specialized services | Per service documentation |

Do not assume all resources are regional or all are global. Always verify service availability and resource scope for the specific service.

## 6. Availability Domains and Fault Domains

### 6.1. Availability Domain (AD)

An Availability Domain is one or more data centers within a region. ADs within the same region are engineered to be independent in critical infrastructure such as power, cooling, and internal networking. If one AD experiences an outage, other ADs in the same region can continue operating.

A region may have one or more ADs. Newer regions may have only one AD; do not assume every region has three ADs.

### 6.2. AD Names Are Tenancy-Mapped

OCI randomizes AD name mappings per tenancy to balance capacity. For example, `PHX-AD-1` in tenancy A does not necessarily correspond to the same physical data center as `PHX-AD-1` in tenancy B.

Retrieve a tenancy's AD list via the IAM `ListAvailabilityDomains` API or the Console. Do not hard-code one tenancy's AD names into shared templates intended for another tenancy.

### 6.3. Fault Domain (FD)

Each AD has three fault domains. A fault domain is a grouping of hardware/infrastructure within an AD that lets you distribute instances to avoid placing critical workloads on the same hardware group.

HA design:

- If a region has multiple ADs, spread the application across multiple ADs.
- Within a single AD, use multiple FDs to reduce shared hardware failure risk.
- If a region has only one AD, consider DR in another region.
- Check whether databases, volumes, subnets, and service dependencies share the same distribution capabilities.

### 6.4. Region and Policy

A region is where resources reside; a compartment is the logical scope of a policy. When operations need to be restricted to a specific region, OCI policies can use conditions like `request.region` or `request.ad` where supported by the policy/service.

Illustrative example:

~~~text
Allow group RegionAuditors to inspect all-resources in tenancy
where request.region = 'ap-singapore-1'
~~~

Check condition and resource-type support in the service policy reference. A region condition does not replace selecting the right endpoint when building an SDK client.

## 7. OCI IAM: Principal, Group, and Policy

### 7.1. Who Is a Principal?

A principal is the identity making a request. In OCI, common subjects include:

- User: Console/API user.
- Group: a collection of users assigned shared permissions.
- Dynamic group: a set of resources/workloads defined by a matching rule.
- Instance principal: a Compute instance authenticated via an identity certificate.
- Resource principal: an OCI resource such as a Function calling another service with its own resource identity.
- OKE workload identity: a Kubernetes workload identified by cluster, namespace, and Kubernetes service account.
- Service principals or other supported principals depending on the service.

Distinguish the application's principal from the end user. Spring Boot may authenticate end users with OAuth/JWT, but when calling Object Storage, OCI sees the service's OCI workload principal.

### 7.2. Identity Domains and Groups

OCI Identity Domains manage users, groups, and federation. A policy subject can reference a group within an identity domain:

~~~text
Allow group <identity-domain-name>/<group-name> to read objects in compartment AppData
~~~

For the default identity domain or tenancies not yet migrated to identity domains, syntax/display may vary. Use the exact domain and group names shown in the tenancy's Console; do not copy group names between two tenancies assuming they are identical.

Groups only gather principals. A group has no permissions until a matching policy grants them.

### 7.3. What Is a Policy?

An OCI IAM policy is a document containing one or more policy statements. A policy specifies:

- Subject: which principal receives permissions.
- Verb: level of permission.
- Resource type: type of resource.
- Location: tenancy or compartment.
- Condition: additional restrictions if needed.

Basic syntax:

~~~text
Allow <subject> to <verb> <resource-type> in <location>
~~~

Conditional syntax:

~~~text
Allow <subject> to <verb> <resource-type> in <location> where <conditions>
~~~

Example:

~~~text
Allow group <identity-domain>/DocumentReaders to read objects in compartment AppData
~~~

Standard permission-granting policies begin with `Allow`. If a principal lacks a matching grant for the operation/resource/location, the request is denied. OCI also offers opt-in **Deny Policies**: disabled by default, they must be actively enabled by a tenancy administrator, and enabling them cannot be reversed by turning off the feature. Once enabled, deny statements can block permissions granted by allow policies and take higher precedence. Only enable them when the organization has clear governance, testing, and break-glass procedures; an overly broad deny statement can lock users out of resources. The default Administrators group is exempted as an account-lockout safeguard. Examples in this lesson focus on standard allow policies.

### 7.4. Four Policy Verbs

Verbs ordered from least to most privilege:

| Verb | General Meaning | When to Use |
| --- | --- | --- |
| `inspect` | List and view basic info per resource type | External auditors, inventory |
| `read` | Includes `inspect` plus reading metadata/content per resource type | Internal auditors, readers |
| `use` | Includes `read` plus operating on existing resources; varies by resource type | Users operating already-created resources |
| `manage` | Full permissions on the resource type within scope | Admins/owners with management responsibility |

Verbs are high-level concepts. Actual permitted API operations depend on the resource type.

Object Storage example:

- `inspect objects` allows listing objects and HEAD object; it does not grant downloading content.
- `read objects` includes the ability to download objects.
- `read buckets` allows reading bucket details/listing buckets in scope.
- `manage objects` can include creating, reading, updating/deleting objects per policy and conditions.

Therefore, never choose a verb solely by its English word. Look up the verb + resource type matrix for the exact API operations you need to call.

### 7.5. Resource Types and Families

OCI defines individual resource types as well as resource families grouping related types. For example, Object Storage has `buckets`, `objects`, and `object-family`. Compute has `instance-family`; Networking has `virtual-network-family`.

Using a family can be convenient, but it is often broader than necessary. If you only need to read objects, consider `read objects` and `read buckets` instead of `manage object-family`.

Some APIs require permissions on multiple resource types. For instance, launching an instance may require permissions on instances, volumes, and networks. When troubleshooting authorization failures, inspect the operation-specific permission matrix instead of escalating everything to `manage all-resources`.

## 8. Writing Least-Privilege Policies

### 8.1. Policy for Document Readers

Suppose the contracts bucket lives in compartment `AppData`. The `DocumentReaders` group only needs to list buckets and download objects:

~~~text
Allow group <identity-domain>/DocumentReaders to read buckets in compartment AppData
Allow group <identity-domain>/DocumentReaders to read objects in compartment AppData
~~~

If only one bucket should be allowed, restrict object access with a condition:

~~~text
Allow group <identity-domain>/DocumentReaders to read buckets in compartment AppData

Allow group <identity-domain>/DocumentReaders to read objects in compartment AppData
where target.bucket.name = 'contracts-prod'
~~~

Depending on the use case, listing buckets and reading objects are two separate permissions. Do not grant permission to list all buckets if the application already knows the bucket name and does not need to list them.

### 8.2. Policy for Uploaders

If a service only needs to create new objects in a single bucket, use conditions on bucket and request permission to avoid granting broad read/delete/overwrite access:

~~~text
Allow dynamic-group DocumentService to manage objects in compartment AppData
where all {
  target.bucket.name = 'contract-inbox',
  request.permission = 'OBJECT_CREATE'
}
~~~

This example uses a specific resource permission. Verify operation and condition support in the Object Storage policy reference before using it. Multipart uploads or other operations may require additional related permissions.

### 8.3. Policy for Auditors

Auditors only need inventory access:

~~~text
Allow group <identity-domain>/CloudAuditors to inspect compartments in tenancy
Allow group <identity-domain>/CloudAuditors to inspect all-resources in compartment Production
~~~

Caution: `inspect` does not always mean seeing names only. For policy resource types such as policies or networking, some list/get operations may return sensitive content like policy statements or network rules. Check operation mappings before granting.

### 8.4. Policy for Compartment Admins

A compartment administration team may need to manage resources within a specific compartment:

~~~text
Allow group <identity-domain>/AppDataAdmins to manage all-resources in compartment AppData
~~~

This is broad permission within the compartment. Use it only when the group is genuinely responsible for managing every resource type there. If they only manage buckets, grant `manage buckets`/`objects` accordingly instead of `all-resources`.

### 8.5. Conditions by Bucket/Tag/Region

Conditions restrict policies by target or request attributes. Example:

~~~text
Allow group <identity-domain>/ContractReaders to read objects in compartment AppData
where target.bucket.name = 'contracts-prod'
~~~

Tag conditions can be used if buckets have defined tags attached:

~~~text
Allow group <identity-domain>/TaggedReaders to read objects in compartment AppData
where target.bucket.tag.Security.Classification = 'Confidential'
~~~

Condition by request region:

~~~text
Allow group <identity-domain>/RegionalAuditors to inspect all-resources in tenancy
where request.region = 'ap-singapore-1'
~~~

Tag namespace/key names must match actual definitions. Condition support varies by resource type and API operation; the policy builder or policy reference helps verify.

### 8.6. Avoid Overly Broad `any-user`

`any-user` is a broad subject that can cover many principal types in a tenancy. Never write broad statements like:

~~~text
Allow any-user to manage all-resources in tenancy
~~~

With OKE workload identity, OCI requires `any-user` combined with conditions that precisely identify principal type, namespace, service account, and cluster OCID. The conditions are mandatory to restrict to a specific workload and must never be omitted.

### 8.7. Policy Inheritance and Cumulative Permissions

A principal can receive permissions from multiple groups or policies. If a user belongs to two groups, permissions from both groups apply together. Policies on parent compartments are also inherited down to children.

Therefore, a policy review should examine:

- The user's membership across all groups.
- Dynamic group matching rules.
- Policies at tenancy/root.
- Policies on parent compartments.
- Policies on the current compartment.
- Policy conditions and resource types.
- The actual principal type used to call the API.

Never read a single policy statement in isolation and conclude whether a user does or does not have permission.

## 9. Dynamic Groups and Instance Principals

### 9.1. What Is an Instance Principal?

Instance principal allows a Compute instance to authenticate with OCI using an identity certificate issued and rotated by the platform. The application does not need to carry a user's API private key onto the machine.

High-level flow:

1. Create a dynamic group.
2. Define a matching rule for allowed instances.
3. Write a policy granting permissions to the dynamic group.
4. Configure the OCI Java SDK to use the Instance Principals provider.
5. The SDK signs requests using the instance's identity.

A dynamic group does not grant permissions by itself. Policies still need to be created separately.

### 9.2. Matching Rules by Compartment

Example putting instances in `AppRuntime` into a dynamic group:

~~~text
ALL {
  instance.compartment.id = '<APP_RUNTIME_COMPARTMENT_OCID>'
}
~~~

You can narrow it by instance OCID or tags. Tag-based illustration:

~~~text
ALL {
  instance.compartment.id = '<APP_RUNTIME_COMPARTMENT_OCID>',
  tag.Application.Role.value = 'document-service'
}
~~~

If using tags to drive authorization decisions, control who can attach or modify tags. If a principal can self-assign the tag used in a matching rule, they could elevate an instance into the privileged group.

### 9.3. Policy for a Dynamic Group

~~~text
Allow dynamic-group DocumentServiceInstances to read buckets in compartment AppData
Allow dynamic-group DocumentServiceInstances to read objects in compartment AppData
~~~

This grants read-only access for the workload. If the service only needs one bucket, add a `target.bucket.name` condition.

### 9.4. Java SDK with Instance Principal

~~~java
import com.oracle.bmc.Region;
import com.oracle.bmc.auth.InstancePrincipalsAuthenticationDetailsProvider;
import com.oracle.bmc.objectstorage.ObjectStorage;
import com.oracle.bmc.objectstorage.ObjectStorageClient;

public final class OciObjectStorageFactory {

    public ObjectStorage create(String regionId) {
        var provider =
                InstancePrincipalsAuthenticationDetailsProvider.builder().build();

        return ObjectStorageClient.builder()
                .region(Region.fromRegionId(regionId))
                .build(provider);
    }
}
~~~

The SDK uses the Compute instance's identity. No user OCID, fingerprint, or private key path is needed in the application config. Protect SSH/OS access to the instance, because anyone with shell access on the machine can exercise the permissions granted to the instance principal.

### 9.5. Securing Dynamic Groups

- Avoid tenancy-wide matching rules unless truly needed.
- Prefer compartment, instance OCID, or tightly governed tags.
- Separate dynamic groups per workload/service.
- Grant policies on the target compartment, not the tenancy by default.
- Review matching rules when moving instances or changing tags.
- Audit requests by the instance's principal ID.
- If an instance is compromised, remove it from the dynamic group or adjust the policy immediately.

Changes to matching rules can take time for membership/policy updates to propagate. OCI documentation notes it can take roughly an hour for matching rule changes to take effect; account for this latency in incident response playbooks.

## 10. Resource Principal and OKE Workload Identity

### 10.1. Resource Principal

Resource principal allows certain OCI resources, such as Functions, to act as principals to call other services. This is the resource's own identity, not a user API key.

General workflow:

1. Confirm the resource supports resource principal.
2. Create a dynamic group/matching rule matching the resource.
3. Grant a policy to the dynamic group.
4. Configure the OCI SDK with the Resource Principal provider.
5. Audit requests to verify the principal and resource scope.

The Java SDK provides `ResourcePrincipalAuthenticationDetailsProvider`. Initialization depends on the resource runtime and resource principal protocol version. Do not set fake environment variables to simulate resource principal on a developer laptop.

### 10.2. OKE Workload Identity

With OKE enhanced clusters, workload identity identifies a workload by a triple:

- Cluster.
- Kubernetes namespace.
- Kubernetes service account.

OCI IAM policies can scope permissions based on principal type, namespace, service account, and cluster OCID. This gives each workload its own identity, avoiding granting the same permissions to an entire node or every pod in the cluster.

### 10.3. Policy for OKE Workloads

Example for a workload named `document-service` running in namespace `documents`:

~~~text
Allow any-user to read objects in compartment AppData where all {
  request.principal.type = 'workload',
  request.principal.namespace = 'documents',
  request.principal.service_account = 'document-service',
  request.principal.cluster_id = '<OKE_CLUSTER_OCID>'
}
~~~

If bucket listing is needed, add a separate statement for `buckets` with the same conditions. Do not omit the principal conditions simply because the subject uses `any-user`.

### 10.4. Java SDK for OKE

~~~java
import com.oracle.bmc.Region;
import com.oracle.bmc.auth.okeworkloadidentity
        .OkeWorkloadIdentityAuthenticationDetailsProvider;
import com.oracle.bmc.objectstorage.ObjectStorage;
import com.oracle.bmc.objectstorage.ObjectStorageClient;

public final class OkeOciClientFactory {

    public ObjectStorage create(String regionId) {
        var provider =
                new OkeWorkloadIdentityAuthenticationDetailsProvider
                        .OkeWorkloadIdentityAuthenticationDetailsProviderBuilder()
                        .build();

        return ObjectStorageClient.builder()
                .region(Region.fromRegionId(regionId))
                .build(provider);
    }
}
~~~

Create only one provider instance and reuse it across the application to take advantage of token caching. Use an OCI Java SDK version that supports OKE workload identity; current docs cite legacy Java SDK from 2.93.0 and standard SDK from 3.88.0. Workload identity requires an OKE enhanced cluster and does not use dynamic groups.

## 11. API Key Authentication and Local Development

### 11.1. When to Use an API Key?

API key-based authentication suits developer workstations, CLI tools, or controlled automation where workload identity is not available. Configuration typically contains:

- User OCID.
- Tenancy OCID.
- Fingerprint of the registered public key.
- Path to the PEM private key.
- Region.
- Passphrase if the private key is encrypted.

API keys are not the default choice for production workloads when instance/resource/workload identity is available.

### 11.2. OCI Config File

Example local profile:

~~~ini
[DEFAULT]
user=ocid1.user.oc1..REPLACE_WITH_USER_OCID
fingerprint=REPLACE_WITH_KEY_FINGERPRINT
key_file=C:\\Users\\developer\\.oci\\oci_api_key.pem
tenancy=ocid1.tenancy.oc1..REPLACE_WITH_TENANCY_OCID
region=ap-singapore-1
~~~

This is an illustrative structure. Replace the values with details from your tenancy. Private keys must be protected with appropriate file permissions and passphrases; never commit config files or PEM keys to Git.

You can define multiple profiles, such as `DEFAULT`, `DEV_USER`, or `READ_ONLY_USER`. Do not use an admin profile for everyday tasks.

### 11.3. Java SDK with a Config Profile

~~~java
import com.oracle.bmc.Region;
import com.oracle.bmc.auth.ConfigFileAuthenticationDetailsProvider;
import com.oracle.bmc.objectstorage.ObjectStorage;
import com.oracle.bmc.objectstorage.ObjectStorageClient;

public final class LocalOciClientFactory {

    public ObjectStorage create(String profile, String regionId)
            throws java.io.IOException {

        var provider =
                new ConfigFileAuthenticationDetailsProvider(profile);

        return ObjectStorageClient.builder()
                .region(Region.fromRegionId(regionId))
                .build(provider);
    }
}
~~~

The profile supplies the user identity and request-signing credentials. The user still needs to belong to a group with appropriate policies for the target resource/compartment.

### 11.4. Session Tokens

The OCI SDK/CLI also supports session token-based authentication. Session tokens are commonly used with short-lived CLI login sessions and avoid using API private keys directly in certain workflows. Tokens expire and must be refreshed according to the session mechanism.

Do not copy session tokens into `application.yml` or logs. When a session expires, create a new session instead of trying to extend a token by altering timestamps in config.

## 12. Integrating the OCI Java SDK in Spring Boot

### 12.1. Choosing an Authentication Provider by Environment

| Environment | Recommended Provider |
| --- | --- |
| Developer laptop | Config file profile or session token |
| Compute instance | Instance principal |
| OCI Functions | Resource principal |
| OKE enhanced cluster | OKE workload identity |
| External CI/CD outside OCI | Workload identity federation if configured; API key only under tight control |
| Local integration tests | Test double or dedicated test provider; avoid production privileges |

Decouple the authentication provider from business services. Services only need an Object Storage client or an application interface—they should not know where private keys reside.

### 12.2. Spring Configuration Properties

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "oci")
public record OciProperties(
        String region,
        String compartmentOcid,
        String authMode,
        String profile) {
}
~~~

Local configuration:

~~~yaml
oci:
  region: ap-singapore-1
  compartment-ocid: OCI_COMPARTMENT_OCID
  auth-mode: config-file
  profile: DEFAULT
~~~

Production should select `auth-mode` from deployment configuration and validate it explicitly. Do not automatically fall back to an API key if instance/workload principal fails; fallback can mask IAM errors and inadvertently open a stronger identity.

### 12.3. Spring Bean for Local Profile

~~~java
import com.oracle.bmc.Region;
import com.oracle.bmc.auth.ConfigFileAuthenticationDetailsProvider;
import com.oracle.bmc.objectstorage.ObjectStorage;
import com.oracle.bmc.objectstorage.ObjectStorageClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OciLocalConfiguration {

    @Bean(destroyMethod = "close")
    ObjectStorage objectStorage(OciProperties properties)
            throws java.io.IOException {

        var provider =
                new ConfigFileAuthenticationDetailsProvider(
                        properties.profile());

        return ObjectStorageClient.builder()
                .region(Region.fromRegionId(properties.region()))
                .build(provider);
    }
}
~~~

The bean manages the client lifecycle and closes resources when the Spring context shuts down. Configure a compatible OCI Java SDK Object Storage dependency and manage versions consistently using the OCI SDK BOM or your project's version catalog.

### 12.4. Spring Bean for Compute Instance Principal

~~~java
import com.oracle.bmc.Region;
import com.oracle.bmc.auth.InstancePrincipalsAuthenticationDetailsProvider;
import com.oracle.bmc.objectstorage.ObjectStorage;
import com.oracle.bmc.objectstorage.ObjectStorageClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OciInstanceConfiguration {

    @Bean(destroyMethod = "close")
    ObjectStorage objectStorage(OciProperties properties) {
        var provider =
                InstancePrincipalsAuthenticationDetailsProvider.builder().build();

        return ObjectStorageClient.builder()
                .region(Region.fromRegionId(properties.region()))
                .build(provider);
    }
}
~~~

Only use this configuration in an OCI Compute environment that already has a dynamic group and policy. Do not run this bean on a laptop expecting the SDK to magically obtain an instance certificate.

### 12.5. Using the Object Storage Client

Example listing buckets in the configured compartment:

~~~java
import com.oracle.bmc.objectstorage.ObjectStorage;
import com.oracle.bmc.objectstorage.requests.ListBucketsRequest;
import org.springframework.stereotype.Service;

@Service
public class BucketCatalogService {
    private final ObjectStorage objectStorage;
    private final OciProperties properties;

    public BucketCatalogService(
            ObjectStorage objectStorage,
            OciProperties properties) {
        this.objectStorage = objectStorage;
        this.properties = properties;
    }

    public int countBuckets(String namespace) {
        var response = objectStorage.listBuckets(
                ListBucketsRequest.builder()
                        .namespaceName(namespace)
                        .compartmentId(properties.compartmentOcid())
                        .build());

        return response.getItems().size();
    }
}
~~~

This operation requires appropriate list/read bucket permissions in the compartment. The Object Storage namespace is tenancy-specific information; it can be retrieved via the `GetNamespace` API. Do not pass the namespace as a compartment OCID.

### 12.6. Closing Clients and Error Handling

OCI SDK clients use HTTP connection pools and should be reused rather than created per Spring HTTP request. Manage their lifecycle with Spring beans.

When handling errors:

- Log the request ID returned by OCI to aid investigation.
- Do not log `Authorization` headers, private keys, session tokens, or document contents.
- Distinguish authentication errors from policy errors.
- Verify the region endpoint and compartment OCID.
- Apply bounded timeouts/retries suited to the operation's semantics.
- For upload/create retries, use idempotency or status checks to avoid creating duplicates.

## 13. Designing Compartments and Policies for `document-service`

### 13.1. Proposed Compartment Tree

~~~text
Tenancy
└── Platform
    ├── AppRuntime
    │   └── document-service instances / OKE cluster
    ├── AppData
    │   └── contract bucket / database
    └── Security
        └── audit and key resources
~~~

Runtime and data resources are separated into distinct compartments so compute permissions do not automatically become data-administration permissions. Operations teams, data-reading teams, and workloads each have distinct policies.

### 13.2. Groups and Permissions

| Principal | Scope | Desired Permissions |
| --- | --- | --- |
| PlatformAdmins | Platform | Administer resources per responsibility |
| DocumentReaders | AppData | Read permitted buckets/objects |
| DocumentServiceInstances | AppData | Read objects or upload objects per use case |
| SecurityAuditors | Tenancy/AppData | Inspect/audit within scope |
| NetworkAdmins | Shared-Network | Manage VCN and network resources |

Do not grant `PlatformAdmins` to runtime workloads. If a service needs to read objects, it does not need permission to create buckets, edit IAM policies, or delete compartments.

### 13.3. Sample Read-Only Policy

~~~text
Allow group <identity-domain>/DocumentReaders to read buckets in compartment AppData

Allow group <identity-domain>/DocumentReaders to read objects in compartment AppData
where target.bucket.name = 'contracts-prod'
~~~

### 13.4. Sample Policy for Compute Workload

Matching rule:

~~~text
ALL {
  instance.compartment.id = '<APP_RUNTIME_COMPARTMENT_OCID>',
  tag.Application.Role.value = 'document-service'
}
~~~

Policy:

~~~text
Allow dynamic-group DocumentServiceInstances to read buckets in compartment AppData

Allow dynamic-group DocumentServiceInstances to read objects in compartment AppData
where target.bucket.name = 'contracts-prod'
~~~

### 13.5. Sample Policy for OKE Workload

~~~text
Allow any-user to read objects in compartment AppData where all {
  request.principal.type = 'workload',
  request.principal.namespace = 'documents',
  request.principal.service_account = 'document-service',
  request.principal.cluster_id = '<OKE_CLUSTER_OCID>',
  target.bucket.name = 'contracts-prod'
}
~~~

This policy binds permissions to the exact workload identity and bucket. OKE workload identity does not use dynamic groups; it must use policy conditions identifying the workload.

### 13.6. Verifying Permissions Before Deployment

Before deploying to production:

1. Verify OCIDs of the tenancy, compartments, instance/cluster, and bucket.
2. Verify the bucket's region and the client's region endpoint.
3. Verify the runtime principal is the right type.
4. Check dynamic group matching rules or OKE workload identity.
5. Check policy statements at the right scope.
6. Test a read-only operation first.
7. Test a denied request to confirm permissions do not exceed scope.
8. Inspect Audit logs to verify the principal OCID/workload identity.

## 14. Troubleshooting Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `401 NotAuthenticated` | Wrong API key/fingerprint, unregistered key, expired token, or certificate rotated mid-request | Check provider, fingerprint, token refresh, and retry in a controlled manner |
| `403 NotAuthorizedOrNotFound` | Principal lacks policy or scope is wrong | Check group/dynamic group, verb, resource type, compartment, and conditions |
| Bucket not found | Wrong region, wrong namespace, or wrong compartment OCID | Verify region endpoint, namespace, and compartment |
| Policy looks right yet instance is denied | Instance is not yet in dynamic group or matching rule is wrong | Check instance OCID/compartment/tags and propagation time |
| OKE workload denied | Cluster is not enhanced, wrong service account, or wrong cluster OCID condition | Check OKE workload identity setup and SDK version |
| API calls right region yet resource doesn't exist | Tenancy hasn't subscribed to that region or service isn't available there | Check region subscription and service availability |
| SDK calls wrong endpoint | Config file region or builder region is incorrect | Set the region identifier explicitly |
| One operation needs multiple permissions | API operation spans multiple resource types | Consult the detailed policy reference and add specific statements |
| Unexpected permission in parent compartment | Policy inheritance | Review policies at tenancy and parent compartments |
| Dynamic group change hasn't taken effect | Matching rule propagation | Wait for propagation per docs and verify membership |
| Can read objects but cannot list objects | Missing inspect/list permission or operation needs separate permission | Check exact API operation and verb-resource mapping |
| Works locally but fails in production | Local uses a stronger API key than the workload principal | Check production principal and least-privilege policies |

### 14.1. Using Request IDs for Investigation

OCI responses typically include a request ID, such as `opc-request-id`. When errors occur:

- Save the request ID along with timestamp, service, region, and environment.
- Do not log private keys, tokens, or sensitive request bodies.
- Check Audit events filtered by `principalId`.
- Cross-check the API operation and resource OCID.
- Confirm policies were applied in the home region and the right compartment scope.

### 14.2. Verifying Policies via Console and SDK

The Console helps inspect policies, groups, dynamic groups, and the compartment hierarchy. With the SDK/CLI, fetch compartment, group, and resource metadata to compare OCIDs. When testing permissions, use the workload's actual principal; testing with an administrator account does not prove the application has permission.

## 15. Comprehensive Practice Exercise

You are tasked with deploying `document-service` on OCI. Compute runs in `AppRuntime`, and contracts are stored in the `contracts-prod` bucket inside `AppData`. The application needs to read objects, while the operations team has bucket management privileges. The test environment uses an API key profile, whereas production uses an instance principal or OKE workload identity.

**Tasks:**

1. Sketch the tenancy root and create compartments `Platform`, `AppRuntime`, `AppData`, and `Security`.
2. Record the tenancy OCID and compartment OCIDs from the Console.
3. Identify the home region and realm, and subscribe to a target deployment region.
4. Retrieve the region identifier and list of availability domains for the tenancy.
5. Design a dynamic group for Compute instances by compartment and tag.
6. Write policies allowing the workload to only read buckets/objects in `AppData`.
7. Create an OKE workload identity policy restricted by namespace, service account, and cluster OCID.
8. Configure a local OCI Java SDK profile and a production instance principal client.
9. Create a Spring `ObjectStorage` client bean and call `ListBuckets`/`GetObject` within scope.
10. Inspect request IDs and Audit events to verify the principal.
11. Attempt a request outside the granted compartment/bucket and confirm it is denied.
12. Write an operations runbook covering region changes, compartment moves, matching rule updates, and policy reviews.

**Self-Assessment Questions:**

- How does a tenancy differ from a compartment?
- Why is a compartment considered global across multiple regions?
- How do policies on a parent compartment affect child compartments?
- What components make up an OCID, and why doesn't every OCID contain a region?
- Can the home region be changed after a tenancy is created?
- Are region subscriptions applied at the user level or tenancy level?
- How do availability domains and fault domains differ?
- How do the four verbs `inspect`/`read`/`use`/`manage` differ?
- Why is `inspect objects` not equivalent to `read objects`?
- Why might a single API operation require policies for multiple resource types?
- How does a dynamic group differ from a user group?
- Where does an instance principal obtain its identity?
- Which attributes identify an OKE workload identity?
- Why doesn't OKE workload identity use dynamic groups?
- When do you use an API key profile vs. an instance principal?
- Why shouldn't you use `manage all-resources` to quickly fix a 403 error?

**Guided Answers:** A tenancy is the account/root boundary while a compartment is a logical boundary; compartments and IAM policies are cross-region resources; parent policies inherit down to children; an OCID contains version/resource type/realm/optional region/unique ID; the home region cannot be changed; region subscriptions apply at the tenancy level and cannot be unsubscribed; an AD is a group of data centers in a region while an FD is a hardware grouping inside an AD; verbs grant progressively broader privilege; `inspect objects` does not download content; operations may span multiple resource types; dynamic groups determine membership via matching rules; instance principals use OCI-issued/rotated certificates; OKE workload identity uses cluster, namespace, and service account; OKE workload identity does not use dynamic groups; API keys suit controlled local usage while instance/workload identity suits runtime environments; `manage all-resources` widens the blast radius and masks imprecise policies.

## 16. Official References

- [OCI – Managing Compartments](https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/managingcompartments.htm): creating, managing, and moving compartments; inherited permissions.
- [OCI – Policy Inheritance](https://docs.oracle.com/en-us/iaas/Content/Identity/policieshow/Policy_Inheritance.htm): how child compartments inherit policies from parents.
- [OCI – Resource Identifiers](https://docs.oracle.com/en-us/iaas/Content/General/Concepts/identifiers.htm): OCID structure, realm, region, and finding the tenancy OCID.
- [OCI – Regions and Availability Domains](https://docs.oracle.com/en-us/iaas/Content/General/Concepts/regions.htm): regions, realms, ADs, FDs, and resource scope.
- [OCI – Managing Regions](https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/managingregions.htm): home region and region subscriptions.
- [OCI – IAM Policies Overview](https://docs.oracle.com/en-us/iaas/Content/Identity/policieshow/Policy_Basics.htm): policy grammar, subject, verb, resource, location, and condition.
- [OCI – Deny Policies](https://docs.oracle.com/en-us/iaas/Content/Identity/policysyntax/denypolicies.htm): opt-in deny feature, precedence over allow, and account lockout warnings.
- [OCI – Verbs](https://docs.oracle.com/en-us/iaas/Content/Identity/policieshow/Verbs.htm): `inspect`, `read`, `use`, `manage`, and exceptions.
- [OCI – Common Policies](https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/commonpolicies.htm): policy examples for Object Storage and other resources.
- [OCI – Managing Dynamic Groups](https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/managingdynamicgroups.htm): dynamic groups and matching rules.
- [OCI – Calling Services from an Instance](https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/callingservicesfrominstances.htm): instance principals, dynamic groups, and Java SDK.
- [OCI – SDK and CLI Configuration File](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/sdkconfig.htm): profiles, tenancy/user OCIDs, fingerprint, key file, and region.
- [OCI – Java SDK Getting Started](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/javasdkgettingstarted.htm): `AuthenticationDetailsProvider`, config profiles, and client setup.
- [OCI – Granting Workloads Access to OCI Resources](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contenggrantingworkloadaccesstoresources.htm): OKE workload identity, policy conditions, and Java SDK support.
- [OCI Java SDK – ObjectStorageClient](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/objectstorage/ObjectStorageClient.html): builder and service client.
- [OCI – SDK Authentication Methods](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/sdk_authentication_methods.htm): API keys, session tokens, instance principals, and resource principals.

**Key Takeaways:** Tenancy defines the account boundary; compartments organize resources and inherit policies; OCIDs uniquely identify resources; regions determine endpoints and deployment locations; IAM policies connect principals with verbs, resource types, and scope. In Spring Boot production, prefer instance principals, resource principals, or OKE workload identity matching the runtime, then grant the narrowest policy so the application operates only on the required compartments and resources.
