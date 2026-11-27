# Inventorying Resources with Resource Search and Tags

## Lesson Objectives

An Oracle Cloud Infrastructure (OCI) landing zone typically spans multiple compartments, multiple regions, and multiple teams deploying applications concurrently. When you need to know which resources an application uses, who is accountable for them, or which resources remain unclassified, opening individual Compute, Networking, Storage, and Database pages quickly becomes unmanageable.

Within the **Resource Governance and Landing Zones** topic of the **CLOUD_PROVIDERS_ORACLE** module, this lesson combines Resource Search with tags to build a scoped, identifier-backed, and reconcilable inventory. You will practice writing queries, collecting results via the OCI CLI, detecting missing tags, and turning inventory data into inputs for cost governance, monitoring, and OCI infrastructure operations.

All namespace, compartment, and application names and figures below are examples. The CLI snippets are meant for learners to run in an authorized environment; they do not represent live resources of any specific tenancy.

## 1. What Questions Must an Inventory Answer?

Suppose the platform team manages the `orders` application consisting of Compute instances, VCNs, boot volumes, block volumes, and an Oracle database service. Production and development reside in separate compartments; some recovery resources reside in a second region.

The team needs to answer:

- Which resources are associated with the `orders` application within the surveyed scope?
- In which region and compartment does each resource reside, and what is its state?
- Which team is accountable when an incident occurs or costs accrue?
- Which resources are missing environment, owner, or cost center metadata?
- Which parts of the infrastructure lack sufficient data to conclude the inventory is complete?

Resource Search discovers resources based on indexed metadata; tags add governance context to each resource. A useful inventory combines both with an **observation scope**: tenancy, region list, compartments, executing principal, and collection timestamp.

Never report merely "120 resources exist." State the full scope, such as: "Observed 120 unique OCIDs across supported resource types, within two inspected compartments and two inspected regions, using the inventory principal at the recorded timestamp."

## 2. What Does Resource Search See?

### 2.1. Service Support Scope

Search finds resources across the tenancy and selected regions. Only resource types and attributes supported by indexing can be queried. The supported set evolves by service; `ListResourceTypes` is the authoritative reference for current resource types and queryable fields. [Oracle: Overview of Search](https://docs.oracle.com/en-us/iaas/Content/Search/Concepts/queryoverview.htm).

This has three consequences for inventory design:

| Observation limitation | How to handle in inventory |
| --- | --- |
| Some resource types or attributes are not yet indexed by Search | Supplement with the owning service's List/Get APIs |
| Only a subset of regions was queried | Explicitly record which regions were checked and which were not |
| Search returns summary metadata | Read details from the owning service when configuration or authoritative state matters |

For instance, inventorying an OCI database service does not mean listing every table and schema inside the database. Likewise, a bucket list does not replace an inventory of individual objects or data versions. Define the level of resource you need to govern before selecting data sources.

### 2.2. IAM Permissions Determine Visible Results

Search does not require a separate policy just to invoke search APIs, but returned results depend on permissions on the target resources. Typically, `inspect` permission on a resource type exposes metadata in Search; some services require `read` rather than `inspect` alone. [Oracle: Details for Search](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/searchpolicyreference.htm).

Therefore, **empty results do not prove resources do not exist**. A principal permitted to inspect Compute only may not see database systems even though both belong to the same application.

The platform team should define a stable inventory principal, grant the required read permissions, and document the permission scope. Expanding permissions for inventory must strictly follow observability needs; never grant create, delete, or update permissions just to list resources.

### 2.3. The Index Does Not Reflect Every Change Instantaneously

Search is eventually consistent: newly created resources or freshly updated metadata may not appear immediately. At times, a service's list view shows a resource before Search does. When results differ from expectations, verify permissions, resource types, query predicates, and allow index lag before drawing conclusions. [Oracle: Query or Search Results are Not as Expected](https://docs.oracle.com/en-us/iaas/Content/Search/Troubleshooting/noresults.htm).

For operational decisions such as bulk tag edits or confirming a resource has been decommissioned, read the resource back through the owning service's API. A Search inventory supports discovery and reconciliation; it is not an atomic snapshot of the entire tenancy.

## 3. Designing Tags for Meaningful Inventory

### 3.1. Free-Form Tags and Defined Tags

| Attribute | Free-form tags | Defined tags |
| --- | --- | --- |
| Structure | Key and value | Namespace, key, and value |
| Example | `environment=prod` | `Governance.Environment=prod` |
| Definition management | Entered directly by users on resources | Administrators create namespaces and key definitions |
| Consistency | Must normalize key and value variants manually | Can govern schemas and allowed value lists |
| Appropriate role | Simple metadata, experiments, or legacy compatibility | Shared metadata for long-term governance |

Defined tags let organizations manage definitions centrally and separate permission to create definitions from permission to apply tags. They are the right foundation for consistent inventory data. [Oracle: Overview of Tagging](https://docs.oracle.com/en-us/iaas/Content/Tagging/Concepts/taggingoverview.htm).

Free-form tags have no namespace; keys and values are case-sensitive. They do not support predefined values, tag variables, or tag conditions in IAM policies. [Oracle: Understanding Free-form Tags](https://docs.oracle.com/en-us/iaas/Content/Tagging/Concepts/understandingfreeformtags.htm).

### 3.2. Minimum Tag Set for the Landing Zone Example

An illustrative schema:

| Defined tag | Example | Meaning during inventory |
| --- | --- | --- |
| `Governance.Application` | `orders` | Group resources by application |
| `Governance.Environment` | `dev`, `test`, `prod`, `recovery` | Distinguish environments |
| `Governance.OwnerTeam` | `team-orders` | Operational point of contact |
| `Governance.CostCenter` | `CC-210` | Reconcile cost accountability |
| `Governance.ManagedBy` | `terraform`, `manual` | Configuration management source |

These are organizational conventions in this example, not mandatory OCI tags. Agree on spelling and value sets before using them as reporting criteria.

Defined tags in the API model take this structure:

```json
{
  "Governance": {
    "Application": "orders",
    "Environment": "prod",
    "OwnerTeam": "team-orders",
    "CostCenter": "CC-210",
    "ManagedBy": "terraform"
  }
}
```

A key that exists with an empty value does not satisfy "accountable owner identified." A value like `unknown` must also be explicitly defined: it represents an open exception under remediation, not complete metadata.

The `OwnerTeam` tag should point to a stable accountable team; never assume the person who created a resource is still operating it. An application tag also does not express full dependency relationships: a shared VCN can serve multiple applications.

Metadata that drives automation must have a schema owner and controlled modification rights. Never put passwords, private keys, or business data payloads into tags.

### 3.3. Tags on a Compartment Differ from Actual Tags on Resources

Tags attached to a compartment should not be treated as proof that those exact tags exist in the metadata of every resource inside. When verifying resource tags, inspect the actual resource tags.

**Tag defaults** are a separate mechanism for defined tags: they apply tags at resource creation time within the compartment and child compartments per inheritance rules. They do not backfill existing resources; editing or deleting a tag default also does not automatically modify or delete previously applied values. [Oracle: Managing Tag Defaults](https://docs.oracle.com/en-us/iaas/Content/Tagging/Tasks/managingtagdefaults.htm).

Therefore, after deploying tag defaults, still run inventories to detect legacy resources missing tags or resources whose tags were altered. When compartments are moved, tags do not automatically update to match the new location; re-verify governance conventions after any move. [Oracle: Working with Compartments](https://docs.oracle.com/en-us/iaas/Content/Identity/compartments/Working_with_Compartments.htm).

## 4. Writing Resource Search Queries

Resource Search uses its own query language. It is not SQL; use the resource type names and attributes supported by Search.

### 4.1. Start with the Observable Resource Set

```text
query all resources
```

This is the baseline query, finding supported resources that the principal is permitted to view within the applicable region scope. The `all` keyword does not expand IAM permissions or cover unselected regions.

To view a subset of resource types:

```text
query instance, volume resources
```

To query resources directly inside a specific compartment:

```text
query all resources
where compartmentId = '<compartment-ocid>'
```

An equality condition on `compartmentId` matches the specified compartment; it does not automatically traverse an entire subtree. If the scope spans parent and child compartments, resolve the list of OCIDs and query or combine predicates for each compartment.

Official sample queries illustrate selecting resource types and filtering by compartment. [Oracle: Sample Queries](https://docs.oracle.com/en-us/iaas/Content/Search/Concepts/samplequeries.htm).

### 4.2. Searching by Defined Tag

Suppose you need to find resources with `Governance.Application=orders`:

```text
query all resources
where
  (definedTags.namespace = 'Governance' &&
   definedTags.key = 'Application' &&
   definedTags.value = 'orders')
```

The predicate group expresses namespace, key, and value explicitly. Do not replace this syntax with JSON path notation like `definedTags.Governance.Application` in Search queries.

To simultaneously restrict to a single compartment:

```text
query all resources
where
  compartmentId = '<production-compartment-ocid>' &&
  (definedTags.namespace = 'Governance' &&
   definedTags.key = 'Application' &&
   definedTags.value = 'orders')
```

Oracle demonstrates writing tag condition clauses in Console, CLI, and API query guides. [Oracle: Running a Custom, Free-Form Query](https://docs.oracle.com/en-us/iaas/Content/Search/Tasks/queryingresources_topic-To_run_a_custom_freeform_query_to_find_a_resource.htm).

### 4.3. Finding Legacy Free-Form Tags

If some legacy resources use `application=orders` as a free-form tag:

```text
query all resources
where
  (freeformTags.key = 'application' &&
   freeformTags.value = 'orders')
```

This set must be reconciled against the defined tags schema. Do not conclude two resources adhere to the same governance standard merely because the string `orders` appears somewhere in metadata.

Searching with `matching 'orders'` can match multiple indexed attributes. It is useful for initial exploration, but is not equivalent to the exact predicate "Application tag equals orders."

### 4.4. Filtering Lifecycle State and Sorting

Example finding running instances in a compartment:

```text
query instance resources
where
  compartmentId = '<production-compartment-ocid>' &&
  lifeCycleState = 'RUNNING'
sorted by timeCreated desc
```

Do not apply `lifeCycleState = 'RUNNING'` across all resource types: lifecycle states are service-specific. To inventory all resources that can accrue cost or need cleanup, you usually need to inspect other states as well.

Search supports `where`, `matching`, `sorted by`, and operators defined by the query grammar. String `=` comparisons in Search are case-insensitive. Therefore, search results alone do not prove tag casing follows conventions; to detect `Prod` instead of `prod`, inspect raw values returned by the API or CLI. [Oracle: Search Language Syntax](https://docs.oracle.com/en-us/iaas/Content/Search/Concepts/querysyntax.htm).

## 5. Running in the Console and Reading Details at the Right Time

In the OCI Console search bar, switch to **Advanced resource query**, enter the query, and confirm the target regions. When the number of regions to survey exceeds what the UI allows in a single search, split into multiple documented passes or orchestrate via API/CLI.

Console inventory workflow:

1. Select the region and query a known resource by OCID or narrow scope to confirm visibility.
2. Run the baseline query for the target compartment.
3. Run queries filtered by application or environment tags.
4. Open details on several representative resources to verify tags, compartment, and state.
5. Record the query text, region scope, and timestamp; never save just a contextless screenshot of a list.

Search results provide summary metadata. APIs and the CLI expose tags and structured fields much more cleanly for downstream processing than the UI results view. Whenever specialized details are needed—such as VM shape configuration, volume attachments, or database configuration—fetch them from the owning resource service. [Oracle: Overview of Search](https://docs.oracle.com/en-us/iaas/Content/Search/Concepts/queryoverview.htm).

## 6. Collecting Inventory with the OCI CLI

### 6.1. Single-Page Query to Verify Scope

Once the OCI CLI and an appropriately authorized read principal are configured, learners can run this PowerShell snippet:

```powershell
$ociInventoryRegion = '<region-id>'
$ociInventoryCompartment = '<compartment-ocid>'
$ociInventoryQuery = "query all resources where compartmentId = '$ociInventoryCompartment'"

oci --region $ociInventoryRegion search resource structured-search --query-text $ociInventoryQuery --limit 100 --output json
```

`--query-text` uses Search query syntax; the OCI CLI `--query` parameter, if used, is a separate client-side output filter. Never use output filtering as a substitute for properly scoping the server-side query.

The `structured-search` command provides `--limit` and `--page`. Receiving a page of results does not mean everything has been retrieved; keep following page tokens until no token remains. Consult the exact options of the command in use rather than assuming every OCI CLI command shares identical pagination flags. [Oracle: OCI CLI structured-search](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/search/resource/structured-search.html).

### 6.2. Collecting Across Multiple Pages and Regions

The snippet below uses **PowerShell 7**, loads JSON responses into memory, and preserves tags intact. `ConvertFrom-Json -AsHashtable` avoids coercing tag keys into PowerShell object property names. This example inspects **one exact compartment** across declared regions:

```powershell
$ociInventoryRegions = @('<region-id-1>', '<region-id-2>')
$ociInventoryCompartment = '<compartment-ocid>'
$ociInventoryQuery = "query all resources where compartmentId = '$ociInventoryCompartment'"
$ociInventoryRows = [System.Collections.Generic.List[object]]::new()
$ociScanStartedAt = [DateTime]::UtcNow.ToString('o')

foreach ($ociRegion in $ociInventoryRegions) {
    $ociNextPage = $null
    do {
        $ociArguments = @(
            '--region', $ociRegion,
            'search', 'resource', 'structured-search',
            '--query-text', $ociInventoryQuery,
            '--limit', '100', '--output', 'json'
        )
        if (-not [string]::IsNullOrEmpty($ociNextPage)) {
            $ociArguments += @('--page', $ociNextPage)
        }

        $ociJsonLines = & oci @ociArguments
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to complete inventory in region $ociRegion"
        }
        $ociResponse = ($ociJsonLines -join "`n") |
            ConvertFrom-Json -AsHashtable
        if ($null -eq $ociResponse['data'] -or
            -not $ociResponse['data'].Contains('items')) {
            throw "Missing items collection in region $ociRegion"
        }

        foreach ($ociItem in $ociResponse['data']['items']) {
            $ociInventoryRows.Add([pscustomobject]@{
                ObservedRegion = $ociRegion
                CapturedAtUtc = [DateTime]::UtcNow.ToString('o')
                Resource = $ociItem
            })
        }
        $ociNextPage = $ociResponse['opc-next-page']
    } while (-not [string]::IsNullOrEmpty($ociNextPage))
}

$ociScanFinishedAt = [DateTime]::UtcNow.ToString('o')
$ociInventoryRows.Count
```

OCI uses the `opc-next-page` response header to indicate the next page; the CLI exposes this token in the JSON response metadata. Terminate pagination based on the token, not because a page returned fewer items than requested. [Oracle: REST APIs — List Pagination](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/usingapi.htm), [Oracle: Get Started with the CLI](https://docs.oracle.com/en-us/iaas/Content/GSG/Tasks/gettingstartedwiththeCLI.htm).

The example fails fast with an error if any read call fails. Rows collected prior to the failure may remain in memory, but must never be reported as a complete inventory. When evolving this into an operational job, add bounded retries, capture request IDs, track per-region status, and record execution duration.

### 6.3. Normalizing Without Losing Original Data

Field names in REST JSON and CLI-rendered JSON can differ in casing/format. For instance, the CLI typically emits `compartment-id`, `display-name`, and `defined-tags`, while the REST API model uses camelCase. The validation snippet below uses the CLI JSON from the example above; verify output schemas when switching to an SDK.

An inventory record should retain:

| Field | Purpose |
| --- | --- |
| Tenancy OCID | Distinguish the inventoried environment |
| `identifier` | OCID for uniquely identifying the resource |
| Resource type | Group by service and select detail-read APIs |
| Compartment OCID and resolved path | Identify where the resource is organized |
| Observed region and AD if applicable | Preserve location context |
| Display name | Aid human operator recognition |
| Lifecycle state and time created | Support lifecycle classification |
| Raw defined tags and free-form tags | Detect missing, non-standard, or conflicting tags |
| Collection start/end times and status | Assess freshness and completeness |

Use OCIDs as the reconciliation key, never display names. Two resources can share the same name. When merging multiple regional scans or multiple sources, a global resource may be observed multiple times; count by normalized identifier key while preserving all observed regions and sources.

Rows in `$ociInventoryRows` are raw observations. `.Count` on that collection does not necessarily equal the count of unique resources. Before computing tag coverage percentages, deduplicate by tenancy and OCID within the exact reporting scope.

## 7. Finding Untagged Resources Using a Complete Baseline Set

### 7.1. Why Querying Only for Valid Tags Creates Blind Spots

If you only query `Governance.Application=orders`, you only see resources that already carry the matching tag. A volume missing the application tag will not appear even if it actually serves `orders`.

For an `OwnerTeam` audit requirement, you can express it as:

```text
A = set of OCIDs observed within the inventory scope
B = set of OCIDs in A with a valid OwnerTeam per convention
Resources needing tag remediation = A minus B
```

You must determine **A independently of the tag being audited**. When inventorying an incompletely tagged application, start from known compartments, IaC state, and resource-relationship APIs to gather evidence of application components.

Do not conclude "missing OwnerTeam" solely from a value not equal to `team-orders`. A resource might belong to another team, have an empty key, lack the namespace, or lack tag data in the source being read. Classify those cases separately.

### 7.2. Example In-Memory Tag Classification

The snippet below continues from the collected `$ociInventoryRows`. It checks `Governance.OwnerTeam` against the example schema and only produces classification results without modifying any resources:

```powershell
$ociOwnerFindings = foreach ($ociRow in $ociInventoryRows) {
    $ociResource = $ociRow.Resource
    $ociOwnerState = 'VALID'
    $ociOwnerValue = $null

    if (-not $ociResource.Contains('defined-tags') -or
        $null -eq $ociResource['defined-tags']) {
        $ociOwnerState = 'TAG_DATA_UNAVAILABLE'
    } else {
        $ociTags = $ociResource['defined-tags']
        if (-not $ociTags.Contains('Governance')) {
            $ociOwnerState = 'MISSING_NAMESPACE'
        } elseif ($null -eq $ociTags['Governance'] -or
                  -not $ociTags['Governance'].Contains('OwnerTeam')) {
            $ociOwnerState = 'MISSING_KEY'
        } else {
            $ociOwnerValue = $ociTags['Governance']['OwnerTeam']
            if ([string]::IsNullOrWhiteSpace([string]$ociOwnerValue)) {
                $ociOwnerState = 'EMPTY_VALUE'
            }
        }
    }

    [pscustomobject]@{
        Region = $ociRow.ObservedRegion
        OCID = $ociResource['identifier']
        OwnerTeam = $ociOwnerValue
        Check = $ociOwnerState
    }
}

$ociOwnerFindings | Where-Object { $_.Check -ne 'VALID' }
```

`VALID` here only means **matching namespace/key and a non-empty value**. To confirm a team actually exists, validate against the organization's approved team directory. This snippet does not prove `team-orders` has active on-call staff, nor does it check every other required tag.

For case-sensitive values and keys, preserve original casing when comparing against the schema. Do not lowercase everything and erase evidence distinguishing `OwnerTeam` from `ownerteam`.

### 7.3. Calculating Ratios with an Explicit Denominator

Suppose after deduplication there are 12 resources in scope requiring OwnerTeam; 9 have valid values, 2 are missing the key, and 1 has an empty value:

```text
Valid OwnerTeam rate = 9 / 12 × 100% = 75%
```

If one region failed to collect, never use 75% to describe the entire tenancy. If a resource type lacks tag data, report the undetermined share separately rather than marking it compliant or silently dropping it from the denominator without explanation.

Separate two metrics:

- **Inventory coverage:** which regions, compartments, resource types, and sources were successfully collected.
- **Tag compliance:** proportion of resources within the evaluated set meeting the published standard.

These two metrics answer different questions. A high tag percentage does not compensate for missing an entire production region.

## 8. Reconciling and Remediating Metadata by Accountability

An inventory finding should lead to owned remediation:

| Finding | Additional evidence needed | Expected action |
| --- | --- | --- |
| Volume missing Application | Attachments, IaC config, app team confirmation | Add tag in the authoritative management source |
| OwnerTeam no longer valid | Team directory and service handover owner | Update accountable contact |
| Production tag inside development compartment | Change history and resource purpose | Fix tag or review resource placement |
| Two inventory rows share an OCID | Observed regions and collection sources | Merge by identifier, retain observation evidence |
| Resource appears in List API but not Search | Permissions, resource-type support, and change timestamp | Record observation gap and re-verify |

Someone permitted to run inventories is not necessarily permitted to edit tags. For defined tags, beyond resource update permissions, the principal needs permission to use the relevant tag namespace. Managing namespace/key definitions is a separate responsibility. [Oracle: Tags and Tag Namespace Concepts](https://docs.oracle.com/en-us/iaas/Content/Tagging/Tasks/managingtagsandtagnamespaces.htm).

Search supports bulk tag management actions on search results, but you must verify the exact OCID set and target values before applying changes. After editing, read the resources back and verify in Search once the index catches up. [Oracle: Managing Tags from Search Results](https://docs.oracle.com/en-us/iaas/Content/Search/Tasks/manage-tags.htm).

If resources are managed by Terraform or another IaC tool, update the corresponding configuration source so the next deployment does not revert tags to old values. Tag defaults and child-resource tags should also be checked against provider behavior; Oracle documents drift scenarios involving these components. [Oracle: Known Issues for Tagging](https://docs.oracle.com/en-us/iaas/Content/Tagging/Tasks/knownissues_tagging.htm).

An untagged resource is not automatically eligible for deletion. Confirming a resource is unused also requires checking with accountable owners, dependency links, utilization metrics, and data retention rules.

## 9. Using Inventory Results for Cost and Availability

Combining inventory with tags helps group resources by cost center, uncover unowned environments, or identify components needing review before maintenance. However, resource count is not total cost: two VMs can differ in shape, uptime, storage, or database service model.

For cost governance, reconcile identifiers and tags against OCI Cost Analysis or Cost and Usage Reports over the exact billing period. Current tags on resources do not automatically explain full historical spend.

For availability, a tag like `Environment=recovery` only reflects governance classification. Independently verify regions, network configuration, data replicas, standby resources, and restoration capability. An inventory can flag that a recovery volume lacks an OwnerTeam, but it cannot prove the replica meets recovery objectives.

When feeding inventories into monitoring or automation, maintain a status record for each collection run:

```text
Intended scope: tenancy + regions + compartments + resource types
Sources: Resource Search and supplementary List/Get APIs
Collection outcome: succeeded / partial / failed
Observation window: UTC start and end timestamps
Data: raw records + OCID-deduplicated resources
Findings: missing tags, invalid values, conflicts, or undetermined
Routing: team receiving each finding
```

Comparing two inventory runs must also account for changes in scope or permissions. An OCID disappearing from Search could stem from a changed query, IAM change, region filter, or index lag; always verify via the owning service API before recording a resource as deleted.

## 10. Hands-On Lab and Completion Criteria

### Part A — Define the Observation Set

1. Choose a lab compartment and a region you are authorized to read.
2. Select at least two resource types appropriate to the environment, such as instance and volume.
3. Run a compartment query and record the principal, timestamp, and scope.
4. Cross-check at least one known resource against its detail page or the service's Get API.
5. Explicitly record which resource types or regions were excluded from this scan.

There is no need to create extra resources if suitable lab data already exists. If using simulated data, mark it clearly as simulated rather than live tenancy output.

### Part B — Query by Tags

1. Select a namespace and key authorized in the lab; do not assume the `Governance` namespace already exists.
2. Write a query for a specific namespace/key/value combination.
3. Compare the tag-filtered set against the compartment baseline set.
4. Inspect raw tag payloads to distinguish missing keys, empty values, and casing/spelling errors.
5. Check whether a known resource is absent due to permissions or index lag.

### Part C — Paginated Inventory Collection

Run the PowerShell 7 collection example after substituting placeholders. Use a small page size if you want to observe pagination transitions, but always follow tokens until exhausted. Record raw row count, unique OCID count, and per-region status. Only mark an inventory run complete when every intended scope succeeds or is explicitly reported as an unresolved exception.

### Part D — Build a Remediation List

For each finding, record the OCID, issue category, evidence, receiving team, and configuration source to fix. If permitted to edit tags in the lab, update one resource, read it back via the owning service API, and check Search after index refresh. Never modify production resources or perform bulk tag edits solely to complete a lab exercise.

The result meets expectations when a reader of your report can tell **where you inventoried, with which permissions, what was observed, and what remains uncovered**—and can reproduce the query, identify resources by OCID, and explain how missing tags were detected. That is the foundation for sustaining an OCI landing zone with clear operational accountability and trustworthy governance data.