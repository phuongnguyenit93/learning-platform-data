# Defined Tags, Free-Form Tags, and Tag Defaults

In an Oracle Cloud Infrastructure (OCI) landing zone, compartments organize governance scope, while tags add metadata to identify which application, environment, operations team, and cost center a resource belongs to. When a single application uses VCNs, Compute, Block Volumes, Object Storage, and Oracle databases simultaneously, a consistent tag set connects those components from a business perspective.

This lesson belongs to the **Resource Governance and Landing Zones** chapter of the Oracle Cloud Infrastructure module. The goal is to choose the right tag type, design a shared metadata schema, apply tag defaults by compartment, and control tag modification permissions to support operations, automation, and cost allocation.

## 1. What Problems Do Tags Solve?

Suppose the Orders team deploys the **order-api** service on OCI:

- A VCN and networking components for application connectivity.
- Compute instances running the application; volumes storing processing data.
- Buckets storing reports.
- An Oracle database service storing business data.
- Some resources serving the development environment and others serving production.

Names like vm-02 or data-volume-01 are rarely enough to tell who is accountable, which team owns the cost, or whether a resource may be stopped over the weekend. A metadata contract can supply that information:

| Attribute | Example value | Question to answer |
| --- | --- | --- |
| Service | order-api | Which application does the resource serve? |
| Environment | dev | Is this a development or production resource? |
| Owner team | orders-platform | Who handles incidents? |
| Cost center | CC420 | Which unit is the cost allocated to? |
| Operating schedule | office-hours | Which resources should automation select? |

This is an **illustrative design convention**, not a mandatory OCI tag set required in every tenancy. Organizations should choose a small, sufficient set, clearly define each attribute's meaning, and designate an owner for each.

Tags do not implement monitoring or automation on their own. To stop Compute instances on a schedule, you still need a workflow that reads tags, checks conditions, and calls APIs with appropriate permissions. To meet availability requirements, you still need the corresponding architecture, backups, and recovery plans.

## 2. Distinguishing the Three Concepts

A **free-form tag** is a direct key–value pair on a resource. A **defined tag** uses a namespace and key declared in the tenancy. A **tag default** is a configuration that applies a defined tag when resources are created within a compartment scope. A tag default is not a third type of tag stored on a resource; its output is a defined tag. See [Overview of Tagging](https://docs.oracle.com/en-us/iaas/Content/Tagging/Concepts/taggingoverview.htm).

Example describing the same environment:

~~~json
{
  "freeformTags": {
    "Environment": "dev"
  },
  "definedTags": {
    "Governance": {
      "Environment": "dev"
    }
  }
}
~~~

These two attributes exist independently. Environment in free-form tags does not become Governance.Environment; editing one does not automatically update the other. In this lesson's convention, **defined tags are the authoritative source of metadata**, while free-form tags serve supplementary needs.

| Design need | Mechanism to choose |
| --- | --- |
| Attach a short-lived test ID or ticket | Free-form tag |
| Standardize environment, service, and owner | Defined tag |
| Restrict environment to dev, test, prod | Defined tag with a predefined value list |
| Populate environment by compartment at creation | Tag default |
| Require deployers to choose a valid value | Defined tag with predefined values combined with a required tag default |

## 3. Free-Form Tags: Flexible but Easy to Fragment

Free-form tags have no namespace and do not require creating key definitions beforehand. Example:

~~~json
{
  "LabRun": "landing-zone-01",
  "Ticket": "CHG1042"
}
~~~

Both keys and values in free-form tags are case-sensitive. Owner and owner are two different keys; Prod and prod are two different values. Adding or editing tags requires update permissions on the corresponding resource. Free-form tags cannot be used in IAM policies, tag defaults, predefined value lists, or tag variables. See [Understanding Free-form Tags](https://docs.oracle.com/en-us/iaas/Content/Tagging/Concepts/understandingfreeformtags.htm).

In the Orders example, Ticket=CHG1042 helps link test resources to a change request. However, using free-form tags for cost data easily leads to inconsistent variants:

~~~text
CostCenter=CC420
costcenter=cc420
CostCentre=CC420
~~~

Finance teams end up normalizing variants before aggregation. Maintenance overhead grows as multiple teams use different deployment tools.

A practical rule is to use free-form tags only for attributes with narrow scope, short lifecycles, and no role in authorization decisions. Once an attribute is used across teams, consider moving it into the defined tags schema.

## 4. Defined Tags: Namespace, Key Definition, and Value

A defined tag takes the form:

~~~text
Governance.Environment = dev

Namespace: Governance
Key:       Environment
Value:     dev
~~~

A namespace groups related keys. A key definition declares an allowed key; concrete values live on individual resources. Namespace and defined key names are case-insensitive, whereas values are case-sensitive. Namespaces also serve as the permission boundary for using the keys inside them. See [Tags and Tag Namespace Concepts](https://docs.oracle.com/en-us/iaas/Content/Tagging/Tasks/managingtagsandtagnamespaces.htm) and [Overview of Tagging](https://docs.oracle.com/en-us/iaas/Content/Tagging/Concepts/taggingoverview.htm).

Proposed schema for the landing zone in this lesson:

| Namespace | Key | Example values | Recommended governance |
| --- | --- | --- | --- |
| Governance | Environment | dev, test, prod | Predefined value list |
| Governance | Service | order-api | Identifier from service catalog |
| Governance | OwnerTeam | orders-platform | Team code in operations directory |
| FinOps | CostCenter | CC420 | Managed by finance team |
| Automation | Schedule | office-hours, always-on | Predefined value list |
| Automation | ExpiresOn | 2026-12-31 | Date convention validated by pipeline |

This table reflects three design decisions:

1. OwnerTeam uses a team code so accountability does not depend on a single individual.
2. CostCenter lives in a separate namespace because permissions to alter financial metadata may differ from application declaration permissions.
3. ExpiresOn is a convention-based string. The key name does not cause OCI to validate dates or automatically delete resources.

Never place passwords, tokens, private keys, or sensitive personal data in tags. Anyone with permission to view a resource can view its metadata. Oracle recommends avoiding sensitive information in tags and resource descriptions. See [Resource Tags](https://docs.oracle.com/en-us/iaas/Content/General/Concepts/resourcetags.htm).

### 4.1. A Defined Key Alone Does Not Standardize Values

If Environment accepts arbitrary strings, users can still enter production, PROD, or prd. To standardize values, configure a list of allowed values.

With a list of dev, test, prod, a request setting production is rejected. The list constrains choices when applying the tag; it does not force every resource to carry that key. It can be combined with a tag default that requires a value. See [Using Predefined Values](https://docs.oracle.com/en-us/iaas/Content/Tagging/Tasks/usingpredefinedvalues.htm).

In the Orders catalog, add staging only after agreeing on its meaning and reporting impact. If one team calls testing test and another calls it qa, pick one standard before expanding the list.

### 4.2. Three Layers of Metadata Control

When designing a tag set, distinguish:

- **Schema:** does the Environment key exist in the Governance namespace?
- **Value domain:** which values are accepted?
- **Presence:** which process ensures resources actually carry the tag?

Creating the OwnerTeam key does not prove deployers supplied an accountable team. Filling in unknown on every resource may make reports look complete on paper while still failing to identify who handles incidents.

## 5. Tag Defaults: Metadata at Creation Time

Tag defaults only use defined tags and take effect on newly created resources in the compartment and its child compartments. They do not apply retroactively; editing or deleting a default does not edit or delete tags already applied.

You can prefill a default value or require a value at creation time. Users with sufficient permissions can override defaults and edit tags afterward. Therefore, defaults do not create immutability. See [Managing Tag Defaults](https://docs.oracle.com/en-us/iaas/Content/Tagging/Tasks/managingtagdefaults.htm).

### 5.1. Placing Defaults According to Compartment Meaning

Proposed compartment tree:

~~~text
Tenancy
├── WorkloadTagCatalog
│   ├── namespace Governance
│   └── namespace Automation
├── FinanceTagCatalog
│   └── namespace FinOps
└── Orders
    ├── OrdersDev
    └── OrdersProd
~~~

The namespace lines describe objects managed inside those compartments, not child compartments.

Convention design for this example:

- At Orders: default FinOps.CostCenter=CC420.
- At OrdersDev: default Governance.Environment=dev.
- At OrdersProd: default Governance.Environment=prod.
- Governance.Service is supplied by the application pipeline.
- Governance.OwnerTeam is taken from the approved team catalog.

A new VCN for OrdersDev is expected to carry both Orders cost attribution and OrdersDev environment metadata. Avoid scattering defaults for the same key across too many levels unnecessarily; a readable design helps governance teams control changes.

A resource carrying Environment=prod does not prove it sits in the right compartment, has proper IAM permissions, or meets availability requirements. Deployment workflows should verify both the compartment OCID and the tag set.

### 5.2. When to Prefill vs. When to Require a Value?

In a compartment dedicated to development, Environment=dev can be inferred from the deployment location. Prefilling reduces repetitive manual input.

In a compartment hosting multiple applications, Service must be chosen per deployed application. A required tag default paired with a valid service list is better than prefilling shared-service for everything. OCI lets you combine predefined values with a user-required value default. See [Using Predefined Values](https://docs.oracle.com/en-us/iaas/Content/Tagging/Tasks/usingpredefinedvalues.htm).

Pipelines should validate metadata before calling APIs—for instance reporting: "Missing Governance.OwnerTeam for service order-api." Specific error messages help deployers fix configurations upfront.

### 5.3. Moving Resources Requires Metadata Reconciliation

When moving a resource from OrdersDev to OrdersProd, include tag reconciliation in the change workflow. Do not rely on a move operation to automatically fix all metadata.

Checklist to reconcile:

1. Destination compartment and access permissions.
2. Existing Environment, OwnerTeam, and CostCenter values.
3. Automation schedules reading those tags.
4. External reports and configurations referencing the resource.

A production server still tagged Automation.Schedule=office-hours could be picked up mistakenly by an internal shutdown tool. Always inspect both live state and metadata before letting automation act.

## 6. Tag Variables and Provenance Metadata

Tag variables allow OCI to substitute expressions with runtime data when applying a defined tag:

| Expression | Meaning |
| --- | --- |
| ${iam.principal.name} | Name of the principal applying the tag |
| ${iam.principal.type} | Type of the principal applying the tag |
| ${oci.datetime} | Timestamp when the tag is applied |

Variables can be used in defined tags or tag defaults; they cannot be used in free-form tags or predefined value lists. Values are resolved at application time and do not continuously tick with the clock. See [Using Tag Variables](https://docs.oracle.com/en-us/iaas/Content/Tagging/Tasks/usingtagvariables.htm).

Recommended example:

~~~text
Governance.TaggedBy = ${iam.principal.name}
Governance.TaggedAt = ${oci.datetime}
~~~

Both corresponding keys must be created before use. If a pipeline runs under an automation principal, TaggedBy identifies that principal; it does not automatically identify the human who approved the deployment.

Some tenancies come with an Oracle-Tags namespace containing CreatedBy and CreatedOn defaults. Administrators can modify or delete them, so inspect the live configuration before depending on these two tags. See [Understanding Automatic Tag Defaults](https://docs.oracle.com/en-us/iaas/Content/Tagging/Concepts/understandingautomaticdefaulttags.htm).

Provenance tags assist lookups, but change investigations should still cross-reference OCI Audit and deployment records. Authorized users can update tags, so a single tag value alone is not proof of history.

## 7. Access Control: Managing Schema Differs from Applying Tags

Permissions should reflect at least three distinct responsibilities:

| Role | Responsibility |
| --- | --- |
| Tag catalog administrator | Create namespaces, keys, and predefined value lists |
| Landing zone administrator | Configure tag defaults at compartments |
| Deployment team | Create resources and supply allowed metadata |

To apply or edit defined tags, a user needs appropriate permissions on the resource plus permission to use the namespace. In the Console, inspect permission on tag-namespaces in the tenancy enables browsing the catalog. See [Required Permissions for Working with Defined Tags](https://docs.oracle.com/en-us/iaas/Content/Tagging/Tasks/managingtagsandtagnamespaces.htm).

Example policy for a deployment group in the Default identity domain:

~~~text
Allow group Default/AppDeployers to inspect tag-namespaces in tenancy
Allow group Default/AppDeployers to use tag-namespaces in compartment WorkloadTagCatalog
~~~

These two statements only grant tag-related permissions. Permissions to create, read, or update VCNs, Compute, and other services must be granted per job function. Substitute your actual domain, group, and compartment names.

In this design, Governance and Automation live in WorkloadTagCatalog. FinOps lives in FinanceTagCatalog, so the two statements above do not grant permission to use the finance namespace. Always check other policies because a principal can inherit permissions from multiple groups.

Example permissions for the tag default administration group:

~~~text
Allow group Default/TagDefaultAdmins to inspect tag-namespaces in tenancy
Allow group Default/TagDefaultAdmins to use tag-namespaces in compartment WorkloadTagCatalog
Allow group Default/TagDefaultAdmins to use tag-namespaces in compartment FinanceTagCatalog
Allow group Default/TagDefaultAdmins to manage tag-defaults in compartment Orders
~~~

This pattern pairs manage tag-defaults at the application target compartment with use tag-namespaces where the schemas are managed, per [Required Permissions for Working with Tag Defaults](https://docs.oracle.com/en-us/iaas/Content/Tagging/Tasks/managingtagdefaults.htm).

A common design flaw is using a tag to make authorization decisions while also granting the same user permission to edit that tag. If a mechanism treats OwnerTeam=finance as a condition for action, check who can change OwnerTeam. Every workflow using tags as authorization inputs must evaluate metadata modification permissions as well.

## 8. Hands-On with the OCI CLI

The following commands trace the path from schema to resource. This uses **Bash syntax**, intended for a Bash session with the OCI CLI configured. Execute inside a lab compartment with appropriate permissions. This lab creates a VCN to observe metadata without deploying Compute or databases.

Assumptions:

- A compartment managing the tag catalog and a lab compartment equivalent to OrdersDev exist.
- The principal has permissions to create namespaces, keys, defaults, and VCNs in the respective scopes.
- The Governance namespace does not already exist; if it does, use the assigned namespace rather than creating a duplicate.
- If the tenancy enforces other required tags, supply all required metadata when creating the VCN.

### 8.1. Declare Scopes and Create the Namespace

Replace placeholder values with real OCIDs:

~~~bash
export TAG_CATALOG_OCID='ocid1.compartment.oc1..replace_tag_catalog'
export APP_DEV_OCID='ocid1.compartment.oc1..replace_orders_dev'

NAMESPACE_OCID=$(oci iam tag-namespace create \
  --compartment-id "$TAG_CATALOG_OCID" \
  --name Governance \
  --description 'Workload governance metadata for lab' \
  --query 'data.id' \
  --raw-output)
~~~

TAG_CATALOG_OCID is where the namespace is managed. APP_DEV_OCID is where resources are created and defaults are placed. The two OCIDs serve different roles. See [OCI CLI: tag-namespace create](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/iam/tag-namespace/create.html).

### 8.2. Create Key Definitions

Create Environment with an allowed value list and capture the OCID of the **key definition**:

~~~bash
ENVIRONMENT_KEY_OCID=$(oci iam tag create \
  --tag-namespace-id "$NAMESPACE_OCID" \
  --name Environment \
  --description 'Workload environment' \
  --validator '{"validatorType":"ENUM","values":["dev","test","prod"]}' \
  --query 'data.id' \
  --raw-output)
~~~

Create two keys that accept deployer-supplied strings:

~~~bash
for TAG_KEY in Service OwnerTeam; do
  oci iam tag create \
    --tag-namespace-id "$NAMESPACE_OCID" \
    --name "$TAG_KEY" \
    --description "Workload metadata: $TAG_KEY"
done
~~~

Using free strings for Service and OwnerTeam keeps the example compact. In a real landing zone, you can configure allowed value lists or validate against an organizational catalog. See [OCI CLI: tag create](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/iam/tag/create.html).

### 8.3. Create a Tag Default for Environment

~~~bash
ENVIRONMENT_DEFAULT_OCID=$(oci iam tag-default create \
  --compartment-id "$APP_DEV_OCID" \
  --tag-definition-id "$ENVIRONMENT_KEY_OCID" \
  --value dev \
  --is-required false \
  --query 'data.id' \
  --raw-output)
~~~

The tag-definition-id parameter takes the OCID of the Environment key, not the namespace OCID. In this example, is-required=false chooses to prefill the value dev. In required-value mode, resource creation is blocked if no value is supplied. See [OCI CLI: tag-default create](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/iam/tag-default/create.html).

### 8.4. Create a VCN with Both Tag Types

~~~bash
VCN_OCID=$(oci network vcn create \
  --compartment-id "$APP_DEV_OCID" \
  --display-name orders-dev-tag-lab \
  --cidr-blocks '["10.42.0.0/16"]' \
  --defined-tags '{"Governance":{"Service":"order-api","OwnerTeam":"orders-platform"}}' \
  --freeform-tags '{"LabRun":"landing-zone-01","Ticket":"CHG1042"}' \
  --query 'data.id' \
  --raw-output)
~~~

The command intentionally omits Governance.Environment to observe the default in action. The CIDR is an example only; choose a range that fits your network plan. The cidr-blocks parameter expects a JSON array. See [OCI CLI: VCN create](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/network/vcn/create.html).

Read back the result:

~~~bash
oci network vcn get \
  --vcn-id "$VCN_OCID" \
  --query 'data."defined-tags"'

oci network vcn get \
  --vcn-id "$VCN_OCID" \
  --query 'data."freeform-tags"'
~~~

The get command takes the VCN OCID and reads its state after creation. See [OCI CLI: VCN get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/network/vcn/get.html).

Minimum expected defined tags output:

~~~json
{
  "Governance": {
    "Environment": "dev",
    "Service": "order-api",
    "OwnerTeam": "orders-platform"
  }
}
~~~

Additional tags may appear due to other defaults in the tenancy. The free-form tags output should contain the LabRun and Ticket values passed in.

### 8.5. Observe Defaults and Value Validation

In the lab, issue another request with Environment=production. Because the enum only allows dev, test, and prod, the request using that value must be rejected.

Next, test a valid value different from the default, such as test, using a principal authorized to use the namespace. Record the resulting tag and compare it against compartment conventions. The goal is to recognize that a tenancy-wide allowed list can be broader than the values appropriate for a specific compartment.

If OrdersDev must always carry environment dev, the design must account for override permissions, namespace scope, and pipeline checks. Setting a dev default alone does not enforce that entire requirement.

After the lab, clean up lab resources per tenancy procedures. Before removing a shared key or namespace, verify whether any defaults or other resources still reference it.

## 9. Using Tags for Cost and Operations

### 9.1. Cost Allocation

In this example, FinOps.CostCenter answers "which unit bears the cost," while Governance.Service answers "which application consumes the resource." Combining them separates shared infrastructure from resources dedicated to order-api.

Do not assume only tags marked for cost-tracking appear in Cost Analysis or Cost and Usage Reports. OCI documentation notes that tags do not need to be marked cost-tracking to be included in those tools. See [Overview of Tagging — Cost Tracking](https://docs.oracle.com/en-us/iaas/Content/Tagging/Concepts/taggingoverview.htm).

During acceptance, pick a representative group of resources and reconcile actual data in the cost tools. Explicitly specify the reporting period, compartment scope, and shared-cost splitting rules. Do not assume adding a tag today automatically reclassifies all historical costs.

Example internal allocation rule:

~~~text
Direct cost of order-api
  = sum of resource costs with Service=order-api for the reporting period

Shared cost allocated to Orders
  = sum of shared group costs for the period × agreed allocation ratio
~~~

Allocation ratios are a business decision; tags provide part of the input data. Applying CostCenter also does not automatically set a budget, cap spending, or stop resources when thresholds are exceeded.

### 9.2. Accountability Monitoring and Automation

Operations teams can maintain a Service → OwnerTeam → escalation channel directory. When an alert fires, tooling looks up metadata to locate the right team. Validate that team codes exist and have active responders; merely having an OwnerTeam key does not guarantee an operational response path.

For tools that stop development resources, combine multiple conditions:

~~~text
Compartment is within the allowed scope
AND Governance.Environment = dev
AND Automation.Schedule = office-hours
AND resource is of a supported type
AND no operational exception is currently active
~~~

This is proposed design logic, not an OCI policy you can paste directly. The tool also needs an exclusion list, audit logging of actions, and scope-limited IAM permissions.

For databases and high-availability systems, verify backups, recovery, and application dependencies before using tags to select automation targets.

## 10. Legacy Resources and Schema Lifecycle

When introducing a tag standard into a running tenancy, split work into two streams: configuration for new resources and metadata backfilling for existing resources.

Recommended workflow for legacy resources:

1. Inventory resources by service type and compartment.
2. Reconcile against actual owners.
3. Map old variants to standardized values.
4. Backfill missing keys using APIs or appropriate tooling.
5. Read back results and log exceptions where no owner has been found.

Mapping examples:

| Legacy data | Target standardized value | Needs confirmation |
| --- | --- | --- |
| Free-form env=prd | Governance.Environment=prod | Resource actually serves prod |
| Free-form team=orders | Governance.OwnerTeam=orders-platform | Team still owns responsibility |
| Missing cost center | FinOps.CostCenter=CC420 | Finance unit approves |

When updating via API or IaC, check the semantics of the specific operation: do not assume passing a new map merges with all existing tags. Read current state, construct the desired set, preview changes, and apply to the verified scope.

OCI distinguishes **retire** from delete: retiring prevents new applications while preserving existing tags; deleting a definition can remove tags from associated resources. See [Overview of Tagging — Retire](https://docs.oracle.com/en-us/iaas/Content/Tagging/Concepts/taggingoverview.htm).

When replacing an old convention, plan a transition: create new keys, update data-reading tools, migrate resources, track exceptions, and then retire the old convention. Avoid deleting a shared schema just to rename a label.

## 11. Situations That Frequently Cause Confusion

| Symptom | Where to check |
| --- | --- |
| Namespace not visible in Console | Inspect permissions, domain/group, where namespace is managed |
| VCN created successfully but cannot attach defined tag | Namespace use permission alongside VCN permissions |
| production rejected | Whether the enum only permits prod |
| New resources have the tag but older resources do not | Creation timestamp vs. when the default was configured |
| Costs fragmented into near-duplicate groups | Case variants and value conventions |
| Changed default, yet existing resources keep the old value | Separate metadata update pass needed |
| Automation selects the wrong resources | Cross-check compartment, defined tags, and exceptions |

When troubleshooting, record the principal, resource OCID, compartment, namespace, and submitted value. Those details help distinguish permission errors from schema or workflow errors.

## 12. Completion Criteria for a Tagging Design

A landing zone tagging design should meet these criteria:

- Has a catalog of namespaces, keys, meanings, and schema owners.
- Important attributes use defined tags with clear value rules.
- Free-form tags have a narrow purpose and do not create a parallel source of truth.
- Tag defaults are placed at compartment levels matching business meaning.
- Permissions to create schemas, manage defaults, and apply tags are granted by responsibility.
- A backfill plan exists for legacy resources.
- Cost, monitoring, and automation workflows clearly specify how tags are read.
- Processes exist for exceptions, ownership changes, and schema changes.

For the Orders application, the desired result is reliably locating order-api resources, identifying accountable teams, and allocating costs by convention. Decisions impacting permissions, lifecycles, or availability must still consider actual runtime state and operational conditions.
