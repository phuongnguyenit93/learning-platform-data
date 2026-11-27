# Navigating the OCI Console and Searching for Resources

The OCI Console is the web interface for viewing and managing Oracle Cloud Infrastructure resources. Learners often start by opening the right service, but accurate actions also depend on **tenancy, region, compartment, filters, and the permissions of the signed-in identity**.

An empty list does not necessarily mean a resource has not been created. You might be in a different region, viewing a parent compartment without including child compartments, keeping filters from a previous session, or lacking read permissions. Conversely, seeing a resource with a matching name is not enough on its own to conclude it belongs to your lab.

This lesson guides you through navigating the Console and finding resources in a verifiable way. The practice steps are read-only; you do not need to create Compute instances, databases, or billable resources to complete the lesson.

## 1. Lesson Objectives

After this lesson, you will be able to:

- Identify the right tenancy, identity, region, and compartment before searching for resources.
- Open a service from the Console menu or search bar.
- Distinguish between searching for services, documentation, and actual resources.
- Find resources by name, type, compartment, or OCID.
- Read the details page to confirm the exact object before taking action.
- Systematically troubleshoot empty lists or empty search results.
- Record the information needed to return to a resource or collaborate with support staff.

Menu group names, button positions, and tool scopes may vary by service or UI version. Therefore, rely on the purpose of navigation areas and the actual displayed metadata rather than memorizing fixed button locations.

## 2. Understanding Context Before Navigating

### 2.1. Five Questions to Answer

Before searching for a resource, determine:

| Question | Information to check | Example in this lesson |
| --- | --- | --- |
| Which system am I in? | Tenancy | Training tenancy provided by your organization |
| Who am I signed in as? | User or identity, and identity domain if relevant | Student account |
| Which region am I searching? | Region | Region assigned by the instructor |
| Which administrative scope am I searching? | Compartment | learning-lab |
| What filters are active? | State, name, tag, or other conditions | Show only running resources |

The name **learning-lab** in this lesson is only an example. Do not create or rename a compartment just to match the example.

If the region or compartment of a target resource is missing, obtain that information from the lab instructions or environment administrator before concluding the resource does not exist.

### 2.2. Tenancy Differs from Identity Domain

A tenancy is the cloud account scope holding related resources and governance structures. An identity domain organizes identity and access management according to the tenancy's configuration.

Multiple login paths or multiple domains may be in use. Two people opening the Console at the same time with different identities may see different sets of resources due to IAM.

Do not look for an instance in another tenancy simply because the username looks the same. Nor should you assume everyone signing into the same tenancy shares the same permissions.

### 2.3. Region Differs from Availability Domain

A region is the deployment area for many OCI resources such as VCNs and Compute instances. An availability domain is an infrastructure scope within a single region under OCI's architecture.

When looking for an instance in region A, switching the availability domain filter inside region B will not find that instance. First, you must select the right region.

IAM resources and operations follow their own scoping rules; do not mechanically apply instance region-filtering habits to every identity management service.

### 2.4. A Compartment Is an Administrative Scope, Not a Region

A compartment is not restricted to "one compartment holds resources from only one region." The same compartment can organize resources across multiple regions, depending on the resource type.

Therefore, if you select the `learning-lab` compartment and the Compute list is empty, you still need to check the region. Selecting the right compartment does not replace selecting the right region.

Compartment names can also repeat across different branches. When verification matters, cross-check the hierarchy path and compartment OCID, not just the display label.

## 3. Recognizing the Main Areas of the Console

### 3.1. Common Functional Areas

| Area | Purpose | What to pay attention to |
| --- | --- | --- |
| Top header bar | Access search, region selector, and account info depending on UI | Check the region before reading regional lists |
| Service navigation menu | Open Compute, Networking, Storage, Database, IAM, and other groups | Search by function; no need to memorize button positions |
| List page | View a collection of resources of one type | Check compartment, filters, and pagination |
| Compartment selector | Choose the display or action scope | Check whether child compartments are included |
| Breadcrumb or path | See the current page and return to a parent level | Do not use as sole proof of resource identity |
| Details page | Inspect a resource's identifier, state, and configuration | Confirm OCID before making changes |
| Related tabs or resource groups | Navigate to VNICs, volumes, subnets, or dependent components | Distinguish the resource you were viewing from the one just opened |
| Actions menu | Perform operations allowed by permissions and state | Some actions modify or delete resources |

The menu may let you open a service page even if you lack permission to view resources in a specific compartment. Being able to open the Compute page does not mean you are permitted to manage every instance.

### 3.2. General Navigation Flow

~~~mermaid
flowchart TD
    A["Sign into the right tenancy and identity"] --> B["Confirm region when the resource is regional"]
    B --> C{"Choose how to reach the resource"}
    C --> D["Service menu"]
    C --> E["Resource search"]
    D --> F["List page: compartment and filters"]
    E --> G["Results: displayed type, region, and scope"]
    F --> H["Details page"]
    G --> H
    H --> I["Cross-check OCID, compartment, region, and state"]
~~~

There are two main paths to the same resource: via the service menu or via search. Regardless of which path you take, confirming on the details page remains essential.

### 3.3. Do Not Confuse Navigation with Action

Opening a details page, inspecting tabs, or copying an OCID are normally read operations. Actions such as create, update, move compartment, stop, terminate, or delete can alter resources.

Before clicking an action button, understand:

- Which object the button acts upon.
- Current state and preconditions.
- Related resources or data affected.
- Lab instructions and assigned permissions.

In this lesson, you do not need to test mutating buttons to prove you found the right resource.

## 4. Method One: Going from Service to Resource

### 4.1. Identify the Resource Type

Translate the operational description into the corresponding OCI resource type:

| What you need to find | Service or keyword to open |
| --- | --- |
| Virtual machine or bare metal instance | Compute, Instances |
| VCN private network | Networking, Virtual Cloud Networks |
| Subnet | Corresponding VCN details or subnet page provided by UI |
| Object Storage bucket | Object Storage, Buckets |
| Block volume | Block Storage, Block Volumes |
| A database service | Exact database category and deployed service type |
| Users, groups, compartments, policies | Appropriate identity and access management section |

"Database" is a broad category. If a lab uses a specific database service type, opening the list page for a different database type can yield an empty result.

Similarly, an object inside a bucket is neither a Compute instance nor a volume. Identify the right resource type before applying name filters.

### 4.2. Example: Finding a Compute Instance

Suppose you are asked to locate an instance with:

~~~text
Display name: lab-web-01
Region:       region specified in the lab
Compartment:  learning-lab
OCID:         provided by the instructor if already available
~~~

Steps:

1. Check the active tenancy and signed-in identity.
2. Select the instance's region.
3. Open the Compute group and the Instances page.
4. Select the right compartment following the hierarchy path.
5. Inspect active state, name, tag, and other filters.
6. If the list spans multiple pages, use search or appropriate filters instead of viewing only the first page.
7. Open the instance with the matching name.
8. Cross-check the OCID, compartment, and region before concluding.

If two instances share the same name, do not pick by list position. Use the OCID or assigned metadata to tell them apart.

### 4.3. Are Child Compartments Included?

Suppose the governance hierarchy is:

~~~text
Root
  + learning
      + learning-lab
      + learning-shared
~~~

Selecting the `learning` compartment does not automatically cause service lists to display resources inside `learning-lab`.

Some pages offer a toggle to include child compartments; behavior depends on the page. Read the label and display scope carefully. When unsure, select `learning-lab` directly to check.

Conversely, if child compartments are included, results may contain resources from multiple branches. In that case, check the compartment column or open the details page to confirm the exact location.

### 4.4. Stale Filters Can Make Resources Disappear from Lists

Examples include:

- Filtering to RUNNING only hides STOPPED instances.
- Filtering by a tag from a previous lab.
- Keeping an obsolete search string in the filter box.
- Viewing only a single availability domain.
- Staying on a sub-page that lists only one related resource type.

When you cannot find a resource, note existing filters first, clear unneeded conditions, and check again. Never modify a resource just to make it match a filter.

## 5. Method Two: Using the Console Search Tool

### 5.1. Distinguish Three Search Intents

The search interface may group results into distinct categories:

| Result group | Meaning | Example |
| --- | --- | --- |
| Services or Console pages | Shortcuts to Console features | Compute, Virtual Cloud Networks |
| Resources | Existing objects you have permission to discover | A specific instance or VCN |
| Documentation or help | Instructional content | Tutorial on creating a VCN |

Searching for "Compute" and opening the service page does not mean you found the target instance. Finding documentation about buckets does not prove the tenancy already contains that bucket.

Before opening a result, read its result category and accompanying metadata.

### 5.2. Searching by Name

When you know the display name:

1. Open the Console search area.
2. Select the resource search mode or group if the interface separates categories.
3. Enter the full name or a sufficiently distinctive portion.
4. Check the region scope, resource type, and active filters.
5. Review all potentially matching results.
6. Open the details page and cross-check identifiers.

Do not assume partial-name search uses the same matching semantics as an equality condition in a query. Text search and structured queries are two distinct mechanisms to understand separately.

### 5.3. Searching by OCID

An OCID identifies a resource more precisely than a display name. If you have an OCID:

- Use the search box or identifier filter supported by the tool.
- Paste the complete string without extra characters or masked portions.
- If the tool supports querying by an identifier attribute, choose the exact attribute documented by the UI.
- If no result appears, open the list page of the exact resource type and re-verify context.

Pasting an OCID string into a documentation search tab may fail to locate the resource. Do not conclude a resource was deleted from a single search in the wrong result group.

If an instructor provides a direct resource link, you may open it after verifying the source and domain. Links do not bypass login, IAM, or other access controls.

### 5.4. Reading the Scope of Search

Do not infer search scope solely from the search bar sitting at the top of the page.

Verify:

- Which resource types is the tool searching?
- Is it scoped to a specific compartment or multiple compartments?
- What region scope is shown?
- Is there a multi-region mode or separate region selector?
- Which resource types are supported by the search service?
- Which resources does the current identity have permission to see?

If the tool searches only the current region, switch regions or repeat the search in the target region. If the tool supports multi-region search, check which regions are actually selected.

Searching across multiple compartments or regions still never bypasses IAM. Nor does the search tool replace every service's detailed listing APIs.

## 6. Getting Familiar with Structured Search

### 6.1. When Should You Use It?

When resource counts grow large, plain-text name search often returns too many unrelated matches. Structured search lets you specify both the resource type and conditions explicitly.

In the OCI Resource Search Structured Search interface, basic queries look like:

~~~text
query all resources
~~~

This query asks for resource types supported by the search tool within the active search scope and permissions. It does not list every object across every OCI service.

To focus on Compute instances:

~~~text
query instance resources
~~~

Resource type names in the query language do not always match Console menu labels verbatim. Use the type list and autocomplete suggestions provided by the UI when writing queries.

### 6.2. Finding an Instance by Display Name

~~~text
query instance resources where displayName = 'lab-web-01'
~~~

This condition uses the `displayName` attribute and an equality comparison. It does not match every name merely containing a substring.

If multiple rows are returned, still verify compartment, region, and OCID. Display names are not unique keys.

If the query is rejected, check that you are in Structured Search mode and verify the supported type name and attributes in the UI. Do not paste this syntax into a simple list-page filter box expecting it to behave like a query engine.

### 6.3. Searching by Compartment

~~~text
query all resources where compartmentId = '<COMPARTMENT_OCID>'
~~~

Replace the placeholder with the full OCID of the compartment you want to inspect. Do not substitute the name `learning-lab`.

Comparing against `compartmentId` matches the resource's compartment value. Do not assume this query automatically includes all child compartments simply because they sit beneath the specified compartment.

For example, if an instance lives in `learning-lab`, querying with the OCID of `learning` may not return that instance when the condition checks the resource's direct `compartmentId`.

### 6.4. Test Conditions Before Adding Complexity

A reliable way to build queries:

1. Start with the resource type.
2. Confirm results appear in the current scope.
3. Add a single name or compartment condition.
4. Inspect results after each step.
5. Combine additional conditions only after understanding syntax and supported attributes.

Do not stack multiple filters at once and guess why the result is empty.

Nor should you weaken or remove security controls just to make search return more results. Query conditions and IAM permissions are two separate layers.

## 7. Search Results Are Not the Complete Operational Truth

### 7.1. Not Every Object Is Indexed in Search

The resource search service indexes specific supported resource types and attributes. An object inside a bucket, a table inside a database, or a file inside a VM is not automatically a standalone entry in Resource Search.

When looking for an object, open the exact bucket and use Object Storage's listing or search features. When looking for a table, use appropriate database tools and database privileges.

Do not confuse database infrastructure management permissions with privileges to query data inside the database.

### 7.2. Indexes and Lists Can Update at Different Times

After a resource is created, renamed, moved between compartments, or deleted, search results and service lists may not reflect the change simultaneously.

When discrepancies occur:

- Check whether the prior operation has completed or is still in progress.
- Refresh the page or re-run the query within reasonable bounds.
- Read the resource details page or API directly if you have its OCID.
- Cross-check region, compartment, and identity.
- Do not recreate a resource merely because Search has not indexed it yet.

A search result may also display stale metadata that should be confirmed on the details page. For mutating operations, always rely on the live opened resource and its current state.

### 7.3. An Empty Result Does Not Prove Non-Existence

An empty search result proves only that **the tool returned no matching resources under the query conditions, scope, and permissions at that moment**.

It is not enough to conclude that:

- The resource was never created.
- The resource was deleted.
- The resource does not exist in another region.
- Nobody in the tenancy can see it.
- The lab is broken.

Framing it this way helps learners avoid re-running creation steps and producing duplicate resources.

## 8. Confirming on the Details Page

### 8.1. Information to Cross-Check

When opening a resource, check:

| Information | Purpose |
| --- | --- |
| Resource type | Avoid confusing instances, databases, buckets, or related components |
| Display name | Compare against requirements, though never rely on it alone |
| OCID or relevant identifier | Confirm the exact object |
| Compartment | Confirm the administrative scope |
| Region if regional | Confirm the deployment region |
| Current state | Know whether it is ready, stopped, or mid-operation |
| Tags or recorded owner | Distinguish labs, environments, and owners |
| Related resources | Understand which network, volume, or service it attaches to |

Not every resource type displays the exact same set of fields. Look for the corresponding fields appropriate to that service.

### 8.2. Do Not Confuse Parent and Child Resources

From an instance page, you can navigate to its VNIC, subnet, or boot volume. After switching pages, action buttons may target the newly opened object.

Example:

~~~text
Instance
  -> VNIC
      -> Subnet
          -> VCN
~~~

This is a chain of relationships between distinct resources, not four names for the same resource.

Before taking any action outside this lesson, re-read the page title and identifier. Breadcrumbs help navigation but do not replace verifying the target object.

### 8.3. Interpret Displayed States Correctly

A `RUNNING` instance does not guarantee the website inside it is ready. A listed database does not prove the application has connected via SQL successfully. An existing bucket does not mean a user is allowed to read every object.

The details page shows service-level state and metadata. Testing application functionality is a separate step.

In this lesson, simply read and record states; do not stop, reboot, or delete resources to test them.

## 9. Workflow When a Resource Cannot Be Found

### 9.1. Check from Context Down to Tooling

Follow this sequence:

~~~text
Right tenancy and identity?
           |
Right service type?
           |
Right region or Search region scope?
           |
Right compartment and child-compartment handling?
           |
Any remaining filters or pagination?
           |
Are name/OCID and query syntax correct?
           |
Is the resource type supported by Search?
           |
IAM permissions and recent operation status?
~~~

This sequence does not guarantee every missing-resource case shares one cause, but it eliminates common mistakes before requesting permission changes or recreating resources.

### 9.2. Common Scenarios Table

| Symptom | Possibility to check | Appropriate action |
| --- | --- | --- |
| Instance list is empty | Wrong region or compartment | Cross-check lab specifications |
| Selected parent compartment but child resources missing | Child compartments not included | Select the compartment containing the resource directly |
| Only some instances missing | State, tag filter, or pagination page | Check and adjust display filters |
| Two resources share the same name | Duplicate display names | Cross-check OCID, region, and compartment |
| Search misses newly created resource | Index lag or wrong scope | Verify creation status, then inspect directly by identifier |
| Direct link shows access error | IAM, wrong context, or resource gone | Confirm principal, region, and identifier |
| Cannot find object in global search | Searching at the wrong object level | Open the bucket and use Object Storage tools |
| Moved compartment and learner can no longer see it | Effective policies may have changed | Check permissions in the target compartment with an admin |
| Can open service page but cannot see list | UI navigation access differs from resource read access | Verify permissions required for that resource type |

### 9.3. Requesting Support with Useful Details

Instead of simply reporting "cannot find the resource," provide:

~~~text
Goal:            find the lab's Compute instance
Display name:    lab-web-01
Expected region: assigned region
Compartment:     path and OCID if permitted to share
Identity:        account/domain used per organization rules
Methods tried:   Instances page and resource search
Filters:         conditions still enabled
Result:          empty list or error code/message
Timestamp:       time of latest check
~~~

If you have the resource OCID, share it with support via an approved channel. Never send passwords, private keys, MFA codes, or login tokens.

Screenshots can help once sensitive details are redacted, but a clear description of context usually speeds up troubleshooting faster than a screenshot of an empty list alone.

## 10. Read-Only Practice

### 10.1. Preparation

Your instructor or lab administrator provides:

- Tenancy and learning account.
- Permitted region.
- Assigned compartment.
- An existing resource, preferably a VCN or instance supporting the lesson.
- Display name and OCID if available.

If the tenancy does not yet have a sample resource, you can practice opening service pages and verifying context; do not create a resource just to make a row appear.

Do not switch to another team's compartment without authorization, even if you can see its name.

### 10.2. Step 1: Record Context

Record the following in your permitted lab report:

| Attribute | Value to fill in |
| --- | --- |
| Tenancy | Permitted name or identifier |
| Identity/domain | Per learning account |
| Target region | Assigned region |
| Compartment | Hierarchy path |
| Compartment OCID | Full OCID if needed for verification |
| Target resource | Type, name, and OCID if provided |

Do not copy authentication secrets into this table.

### 10.3. Step 2: Locate via the Service Menu

1. Open the right service group.
2. Confirm the region if applicable.
3. Select the compartment containing the resource.
4. Note any active filters.
5. Locate the target resource and open its details.
6. Cross-check identifiers against assigned metadata.
7. Record its state without changing it.

If not found, run the verification flow in Section 9 and note exactly what could not be verified.

### 10.4. Step 3: Locate via the Search Tool

1. Open the Console search tool.
2. Select the resources category.
3. Search by name or identifier using supported features.
4. Check the region scope and conditions.
5. Open the matching result.
6. Confirm the OCID matches the resource opened in the previous step.

If Structured Search is available, try querying by resource type and one simple condition. You do not need to test every query syntax variant to complete the exercise.

### 10.5. Step 4: Navigate to a Related Resource

From the details page, open one related link you are allowed to read:

- For an instance: view the attached VNIC or subnet.
- For a VCN: view an existing subnet.
- For a bucket: inspect bucket configuration; only read object contents if authorized and required.
- For a database: view permitted infrastructure or network metadata; do not attempt to log into the data tier yourself.

Document how the newly opened object differs from the original resource in type and identifier. Then navigate back cleanly.

### 10.6. Step 5: Verify an Empty List Scenario

Change a **display filter** using a hypothetical name that does not exist in the list, and observe the empty result. Then clear the filter to restore the list.

This step changes only the view filter—never create, rename, or delete a resource.

The goal is demonstrating that an empty list can stem from query conditions rather than actual disappearance of resources.

### 10.7. Expected Deliverable

A brief report should cover:

- Tenancy, region, and compartment context verified.
- Confirmed resource type and identifier.
- Both search/navigation paths used.
- Filters that affected results.
- One related resource opened and how you navigated back.
- Explanation of why an empty result does not prove a resource does not exist.

If no sample resource was provided or permissions are insufficient, accurately report your observation limits instead of creating resources yourself or requesting tenancy-wide admin rights.

## 11. Building Repeatable Navigation Habits

### 11.1. Use Consistent Names and Tags

A name like `lab-web-01` is easier to locate than a vague name. Tags for environment, owner, or lab can help classify resources when your organization defines conventions.

However:

- Names are not guaranteed to be unique.
- Tags can be missing or mistyped.
- Tag-based search only helps where supported by the tool and resource type.
- Names and tags do not replace IAM permissions or OCIDs.

In this navigation lesson, only read and recognize existing conventions. Do not add tags to shared resources on your own.

### 11.2. Save Links Together with Context

Bookmarks or detail URLs help you reopen pages quickly, but store them alongside:

- Resource type.
- OCID.
- Region if applicable.
- Compartment.
- Role in the lab.

A link can stop working if a resource is deleted, replaced, or your access is revoked. A new OCID for a recreated resource must not be treated as the old OCID simply because the name stayed the same.

Never use URLs or bookmarks to store authentication credentials.

### 11.3. Connect Search Habits to Lab Cleanup

Being able to locate exact resources helps control costs after labs. You can combine naming conventions, tags, compartments, and a resource inventory to track created components.

However, Search results are not a complete billing statement. A stopped resource can still have attached volumes, backups, or other components remaining active.

Cleanup is a separate workflow: confirm owner, data to preserve, dependent resources, and delete permissions before removing anything. This lesson only helps locate and inspect the details needed for that workflow.

## 12. Self-Check

### Question 1: Is selecting the right compartment enough to see every instance in a lab?

Not yet. You also need the right region, resource type, filters, child-compartment scope, and appropriate IAM permissions.

### Question 2: Two results share the name `lab-web-01`; should you pick the first one?

No. Cross-check the OCID, region, compartment, and assigned metadata. Result ordering does not prove which resource is yours.

### Question 3: You searched for "VCN" and saw a tutorial article; have you found the lab's network?

No. That is a documentation result. Open a resource result or the VCN list page and confirm the specific network.

### Question 4: Does selecting a parent compartment always include resources in child compartments?

Do not assume so. Check how the current page behaves or select the compartment holding the resource directly.

### Question 5: Search does not show a newly created resource; should you recreate it immediately?

No. Verify the creation operation, region, compartment, permissions, and index update timing; if you have the OCID, inspect it directly by identifier.

### Question 6: Can a query using `compartmentId` take the compartment name as its value?

No. The `compartmentId` attribute expects the compartment's identifier, not its display name.

### Question 7: Does opening a `RUNNING` instance details page prove the website is working?

No. Infrastructure state differs from network reachability and application readiness. Application functionality must be checked through its own procedure.

## 13. Pre-Conclusion Checklist Before Saying You Found the Right Resource

- [ ] Correct tenancy and assigned identity.
- [ ] Correct service type and resource type.
- [ ] Correct region or verified Search region scope.
- [ ] Correct compartment, path, and child-compartment handling.
- [ ] Checked active filters, pagination, and leftover search strings.
- [ ] Distinguished service, documentation, and resource results.
- [ ] Cross-checked OCID or appropriate identifier on the details page.
- [ ] Read current state and necessary related resources.
- [ ] Did not treat an empty search result as sole proof of non-existence.
- [ ] Did not run mutating actions merely to test navigation.

Effective OCI Console navigation starts with holding the right context and ends with confirming the exact identifier. Once you master those two habits, you can locate resources across services without depending on fixed menu positions or potentially duplicate display names.
