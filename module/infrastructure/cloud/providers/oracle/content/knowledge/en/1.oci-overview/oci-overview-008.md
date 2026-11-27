# Reading OCI Documentation, Service Limits, and Change Announcements

## Lesson Objectives

After this lesson, you can find the right Oracle Cloud Infrastructure (OCI) documentation, check applicability prerequisites before following a guide, read your tenancy's resource limits, and classify change announcements. You can also turn what you read into an evidence-based deployment decision.

This lesson belongs to the **Oracle Cloud Infrastructure Overview** section of the CLOUD_PROVIDERS_ORACLE module. The running example is a team preparing to deploy a Java API, a database, and file storage on OCI. The team needs to know which guides apply, whether permissions and limits are sufficient, and which changes might impact the system.

Hypothetical numbers and announcements in this lesson are for explanation only. When deploying for real, inspect current documentation alongside data from the exact tenancy, subscription, and resource scope.

## 1. Reading Documentation Is Part of an Engineering Decision

A guide may describe a product accurately yet still not fit your environment. Differences can lie in the region, tool version, deployment model, account type, or access permissions.

For example, a lab that creates a VM successfully in one region does not prove your tenancy has the same limit or remaining provisioning capacity in your chosen location. Similarly, a Java example using a newer API may require an SDK version your project does not yet use.

Before copying a deployment step, determine three things:

1. **Who or what does the guide apply to?** Which service, feature, version, and environment?
2. **Does your environment meet the prerequisites?** Are permissions, networking, limits, deployment region, and tools aligned?
3. **What outcomes and impacts does the operation produce?** Which resources are created, modified, billed, or potentially disrupted?

The goal is to turn a statement like “follow the OCI docs” into a concrete specification: “use the guide for the chosen service, verify prerequisites in this environment, and validate the outcome this way”.

## 2. Picking the Right Documentation Type for the Question

The starting point is [Oracle Cloud Infrastructure Documentation](https://docs.oracle.com/en-us/iaas/Content/home.htm). From there you can navigate to service guides, developer documentation, architecture guidance, release notes, and change pages.

| Question to Answer | Documentation Type to Open | What to Extract |
| --- | --- | --- |
| What problem does this service solve? | Overview, Concepts | Concepts, objects, and operating model |
| What needs preparation before creating resources? | Prerequisites, Getting Started | Permissions, configuration, and dependencies |
| How is an operation performed? | Tasks, How-to | Steps and how to verify results |
| Which parameters does calling the API need? | API Reference | Parameters, data types, responses, and errors |
| Which CLI command should be used? | CLI Command Reference | Syntax, required parameters, and pagination |
| How is the Java library used? | SDK Guide, API Reference, version-matched examples | Classes, methods, and client configuration |
| Why did an operation fail? | Troubleshooting, Known Issues | Error conditions and appropriate workarounds |
| What was recently added? | Release Notes | New features or capabilities |
| Are there changes breaking existing integrations? | Service Change Announcements | Impact scope and required actions |
| How many resources can the tenancy use? | Service Limits and tenancy data | Limit name, scope, value, and current usage |

Architecture docs and task guides serve different purposes. A reference diagram helps explain how services combine; a task guide describes how to create a component. Before applying a diagram, evaluate your own system's security, cost, and recovery goals.

Community articles can help discover approaches. For provisioning conditions, API syntax, limits, or change deadlines, cross-check against official product documentation.

## 3. Checking Scope Before Reading Details

### 3.1. Identifying the Exact Product and Deployment Model

Similar names can belong to different models. For example, a database guide for a managed service does not automatically apply to a database your team installs on Compute.

Likewise, guides for public cloud, Cloud@Customer, or a legacy generation product can differ in permissions, interfaces, and operations.

A brief reading note might include:

~~~text
Goal: determine how to deploy component X

Service and features:
Deployment model:
Relevant region / realm:
Tool or software version:
IAM prerequisites:
Network and data dependencies:
Official source:
Date verified:
~~~

This is a note-taking template for learners to use when needed, not an OCI configuration.

### 3.2. Distinguishing Documentation Version From Environment Version

Separate the following details:

| Information | What Does It Tell You? |
| --- | --- |
| Page last updated date | When the page content was edited |
| SDK or CLI version | Capabilities and behavior of client-side tooling |
| API version | Communication contract used by the operation |
| Database or Kubernetes version | Software version of the running resource |
| Feature release date | When a capability was announced per the scope in the notice |
| Effective date of change | Milestone when behavior or capability is adjusted |

A recently updated page does not guarantee examples work with an older SDK. Nor is a new feature guaranteed available in every region or resource type. Read accompanying conditions rather than looking only at dates or titles.

### 3.3. For Java, Match the Exact SDK in Use

The [SDK for Java](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/javasdk.htm) documentation is the starting point for developing with OCI. Examples and references must match your project's SDK version.

Oracle notes that incompatible SDK changes are described in the changelog; see [Setup and Prerequisites](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/devguidesetupprereq.htm).

When a sample snippet does not work, check first:

- Does the SDK version have the same classes and methods?
- Do dependencies and HTTP clients align?
- Is the client pointing to the right region or endpoint?
- Does the identity have permissions for the operation being called?
- Do parameters match the expected types and resources of your environment?

Upgrading a library requires evaluating related dependencies together. Changing only a version number without reading migration guides can cause runtime errors elsewhere.

## 4. How to Read a Task Guide

Read in the flow **prerequisites → actions → outcome → impact**.

### 4.1. Prerequisites

Look for sections on IAM permissions, pre-existing resources, network requirements, and limits. If a guide says “select an existing subnet”, understand which characteristics that subnet must have and who has permission to use it.

Do not resolve every permission error by granting tenancy-wide administration. Match permissions to the exact operations and resource scope actually used.

### 4.2. Actions

Distinguish Console, CLI, and API methods. Parameters may have different names or representations, yet all must reference the right target object.

Documentation examples may use the Bash shell. When practicing on PowerShell, adjust variable assignment and line continuation; do not copy line-continuation syntax verbatim between the two shells.

### 4.3. Outcome

A resource appearing in a list does not always mean the operation is complete. Some services have lifecycle states or work requests to track.

Before taking a dependent step, read how the documentation defines success: which state, which fields, or which connectivity checks are required.

### 4.4. Impact

Determine whether the operation restarts a service, changes an address, creates billable resources, or makes data inaccessible.

For example, a resource cleanup step must be understood alongside volume and backup retention policies. The practice goal is completing the lesson while knowing which data must be kept and which resources still exist.

## 5. Distinguishing Types of Limits

A provisioning request can be blocked for several different reasons.

| Concept | Meaning | Initial Investigation Direction |
| --- | --- | --- |
| Service limit | Quota/limit set by Oracle for a resource within a defined scope | Limit name and current tenancy value |
| Compartment quota | Allocation or restriction set by administrators via quota policies | Policies applied to the compartment and parent tree |
| Host capacity | Actual physical infrastructure capacity to fulfill the config at the requested location | Shape, region, AD, and FD |
| API throttling | Rate limiting on API calls | Error code, concurrency level, and retry policy |
| Service technical limits | Constraints such as size, element count, or supported configurations | Feature-specific documentation |

Oracle explains service limits and compartment quotas at [Service Limits](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/overview.htm). Quotas are configured by administrators; setting a higher quota cannot exceed the service limit. See [Quota Policy Syntax](https://docs.oracle.com/en-us/iaas/Content/Quotas/Concepts/quota_policy_syntax.htm).

Not every resource type supports the same quota or usage query mechanisms. Check the capabilities of the specific limit or service.

### 5.1. Read the Full Name, Unit, and Scope

A number without a unit and scope cannot be used for planning.

For example, determine what the limit measures:

- Resource count or capacity quantity?
- Unit of CPU, memory, storage, or another count?
- Tenancy-wide, regional, or AD scope?
- Tied to a specific subscription?
- Applicable to the exact shape family or service type chosen?

[Limits by Service](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/default.htm) publishes default limits and scopes. Actual values must be cross-checked against your tenancy; do not treat the default table as a guaranteed record for your account.

For example, receiving more instance count limit may not solve a capacity-unit shortage for the configuration you need. A VM also depends on boot volume, subnet, and related resource limits.

### 5.2. Having Limit Does Not Guarantee Provisioning Capacity

Host capacity is physical infrastructure availability. A request can still fail even when service limits are not exhausted.

[Resolving Out of Host Capacity error](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/troubleshooting-out-of-host-capacity.htm?Highlight=Sea+sha) describes capacity shortages by configuration and placement; options may include changing shape or provisioning location.

Changing AD or region can also entail changes to connectivity, data, latency, and recovery requirements. Re-evaluate the architecture before adopting an alternative.

## 6. Reading Actual Limits in the Console

The **Limits, Quotas and Usage** page lets you view limits with appropriate filters. The official guide is [Viewing a Tenancy's Limits and Usage](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/view-tenancy.htm).

Reading order:

1. Identify the tenancy and region you are working in.
2. Select the service.
3. Check subscription if that filter applies.
4. Select scope and compartment.
5. Cross-check limit name, value, usage, and available.
6. Check related quotas alongside additional provisioning needs.

Common fields:

| Field | How to Read It |
| --- | --- |
| Limit Name | Technical name for lookup and reference |
| Service Limit | Total limit for the selected scope |
| Usage | Consumed amount per displayed data |
| Available | Remaining limit per the displayed field's calculation |
| Scope | Scope to which the limit applies |

Available on the limits page is not a guarantee that hardware for a shape is ready. Separate limit checks from provisioning capacity checks.

The UI may not display every limit for every service. If an item is missing, check service documentation and access permissions before concluding the resource has no limit.

For resources with fractional units or rounding rules, read the field explanation. Do not apply integer arithmetic to every limit type.

## 7. Querying With the CLI Without Modifying Resources

The following example uses PowerShell and illustrates read-only queries. Prerequisites are an authenticated OCI CLI, an appropriate profile, and an identity with required read permissions. Values in angle brackets must be replaced with real environment data.

### 7.1. Finding Limit Definitions and Values

~~~powershell
$tenancyOcid = '<TENANCY_OCID>'
$regionId = '<REGION_ID>'
$profileName = 'LEARNING'

oci limits definition list --compartment-id $tenancyOcid --service-name compute --region $regionId --profile $profileName --all

oci limits value list --compartment-id $tenancyOcid --service-name compute --region $regionId --profile $profileName --all
~~~

The first command helps find supported limit names and characteristics; the second retrieves values for the service in the queried scope. Refer to [limit definition list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/limits/definition/list.html) and [limit value list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/limits/value/list.html).

Depending on the limit type, subscription or AD filters may be needed. The `--all` option fetches all pages of results; reading only the first page can miss the item you need to check.

Do not guess a limit name from a shape's display name. Retrieve the exact technical name and scope from definition data or related documentation.

### 7.2. Reading Compartment Usage and Availability

~~~powershell
$projectCompartmentOcid = '<PROJECT_COMPARTMENT_OCID>'
$limitName = '<IDENTIFIED_LIMIT_NAME>'
$limitScope = '<AD_OR_REGION_OR_GLOBAL>'

$availabilityArguments = @(
    'limits'
    'resource-availability'
    'get'
    '--compartment-id'
    $projectCompartmentOcid
    '--service-name'
    'compute'
    '--limit-name'
    $limitName
    '--region'
    $regionId
    '--profile'
    $profileName
)

if ($limitScope -eq 'AD') {
    $availabilityDomainName = '<AD_NAME_IN_TENANCY>'
    $availabilityArguments += @(
        '--availability-domain'
        $availabilityDomainName
    )
}

oci @availabilityArguments
~~~

According to [resource-availability get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/limits/resource-availability/get.html), the AD parameter must be provided when the limit's scope is AD and omitted when the scope is not AD. Not every limit supports this API; the documentation also notes returning 404 when the value is unavailable.

The availability result checks quota/limit room. It is not a survey of physical hardware capacity for a shape.

### 7.3. Reading Query Errors Properly

If the command fails, check the limit name, scope parameter, region, subscription where applicable, and identity permissions together.

In the Limits API permission model, reading definitions and values has different requirements from reading resource availability by compartment. Cross-check the IAM section in Service Limits documentation instead of assuming a profile that can list VMs can read all limit data.

Do not include private keys, tokens, or full authentication configs in error reports. Keep only details needed to identify the operation and query scope.

## 8. Example: Is There Enough Limit for a Deployment?

Suppose the Java API deployment team wants to create three additional VMs. Each VM needs two units of an identified capacity limit.

The numbers below are entirely hypothetical. Assume only one relevant quota exists, all metrics share the same scope and unit, there are no in-flight provisioning requests, and there are no additional quota constraints on parent compartments.

| Data | Hypothetical Value |
| --- | --- |
| Service limit | 24 units |
| Scope-wide usage of the limit | 18 units |
| Quota for project compartment | 12 units |
| Usage of project compartment | 8 units |
| Additional demand | 3 VMs × 2 units = 6 units |

Analysis:

~~~text
Remaining under service limit: 24 - 18 = 6
Remaining under project quota: 12 - 8 = 4

Under the example assumptions:
additional allocatable capacity is capped at 4 units.

Demand is 6 units:
the project compartment quota is not satisfied.
~~~

In this case, simply requesting a service limit increase does not resolve the project's quota constraint. The team must discuss actual needs and deployment plans with the quota administrator.

If quotas exist at multiple levels or other policies apply, the illustrative arithmetic above is insufficient. Inspect the applicable policies and availability data for the exact scope.

### 8.1. Do Not Count Only Steady State

An application running two VMs in steady state may temporarily need a third VM during updates that create the replacement first, shift traffic, and only then terminate the old machine.

Therefore, demand calculations may need to include:

- Currently serving resources.
- Temporary resources during updates or replacements.
- Resources for recovery drills.
- Dependent resources such as volumes and networking components.

A plan that fits tightly against limits in steady state may fail during updates or recovery. When sizing headroom, still evaluate costs and cleanup for temporary resources.

### 8.2. When to Request a Service Limit Increase?

Submit a request only after identifying the exact limit blocking demand. The request should state service, limit name, scope, current value, desired level, and deployment rationale.

[Creating a Limit Increase Request](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/create-request.htm) describes how to submit and track requests. Do not assume an increase is approved immediately or that raising a limit reserves physical hardware.

If the issue is internal quota, work with your quota administrator. If the issue is host capacity, check provisioning capacity guidance. If it is a technical limit that does not support the desired configuration, adjust the design or verify with support.

## 9. Reading Errors to Pick the Right Documentation

HTTP status codes are the starting point. Read the error code, message, request ID, and resource or work request state when available.

| Symptom | Investigation Direction |
| --- | --- |
| LimitExceeded | Check service limit and scope |
| QuotaExceeded | Check quotas applied to the compartment |
| Out of host capacity | Check capacity for the configuration and provisioning location |
| TooManyRequests / HTTP 429 | Check call rate, concurrency, and backoff |
| NotAuthorizedOrNotFound | Check permissions, identifiers, and resource scope |
| InvalidParameter | Cross-check parameter types, values, and constraints |

Common API error codes are described in [API Errors](https://docs.oracle.com/en-us/iaas/Content/API/References/apierrors.htm); Compute capacity issues have dedicated guidance in Compute documentation.

A limit or quota error is not solved by retrying continuously while conditions stay unchanged. For retryable errors, follow operation guidance and account for the possibility that an earlier request already took effect.

For Java applications using the SDK, inspect existing retry configuration before adding retries at the application layer. Two uncoordinated retry layers can multiply call counts and prolong processing.

Minimum details for technical escalation:

~~~text
Operation and service:
Timestamp with time zone:
Relevant region / AD / compartment:
CLI or SDK version:
HTTP status and error code:
Request ID or work request ID:
Expected result:
Actual result:
Conditions already checked:
~~~

This template connects observed errors to the right documentation while avoiding premature conclusions that every creation error stems from limit exhaustion.

## 10. Distinguishing Change Information Channels

| Channel | Intended Purpose |
| --- | --- |
| Release Notes | Track newly announced features and capabilities |
| Service Change Announcements | Track behavior changes, deprecations of features or APIs, and migration requirements |
| Known Issues | Look up documented issues and workarounds or related limits |
| Console Announcements | Read operational notices relevant to the environment by notice scope |
| OCI Status | Check public service status within the provided scope |
| SDK, CLI, or provider Changelogs | Evaluate changes in client-side tooling |

Official entry points:

- [OCI Release Notes](https://docs.oracle.com/en-us/iaas/releasenotes/index.htm).
- [Service Change Announcements](https://docs.oracle.com/en-us/iaas/Content/servicechanges.htm).
- [Known Issues](https://docs.oracle.com/en-us/iaas/Content/knownissues.htm).
- [Console Announcements](https://docs.oracle.com/en-us/iaas/Content/General/Concepts/announcements.htm).
- [OCI Status](https://ocistatus.oraclecloud.com/).

### 10.1. Release Notes: What Is New and Usable?

When reading a release note, capture service name, release date, deployment scope, and link to detailed documentation.

A new feature may help with system monitoring or automation, yet applicability conditions must be evaluated. You do not need to upgrade production immediately upon seeing a new announcement.

Hypothetical example: a service adds a new metric. The team needs to verify whether the metric appears on their resources, whether read permissions align, and which alarms genuinely need that metric.

### 10.2. Service Changes: What Needs Adjustment?

The Service Change Announcements page describes changes that can affect compatibility, including deprecated APIs, retired features, and service behavior changes.

Key fields are:

| Field or Question | Meaning to Extract |
| --- | --- |
| Date Announced | Date the notice was published |
| Date in Effect | Date the change begins taking effect |
| Details | Content of the adjustment |
| Does this impact me? | Conditions placing a system in the affected scope |
| What do I need to do? | Required action or migration path |

Announcement date and effective date play different roles. An older announcement can still be relevant if its effective date is approaching; a brand-new notice may also describe a change already in effect.

### 10.3. Known Issues and Operational Status

Known Issues helps identify documented problems. Any workaround must be checked against your active configuration and version, since it may change performance or operating models.

OCI Status provides service status info; an example of how to reference this page is described in [Oracle Database Overview](https://docs.oracle.com/en-us/iaas/doc/database-overview.html).

Seeing no incident on the status page is not enough to conclude your application configuration is right. You still must inspect your own system's networking, permissions, resources, and logs.

## 11. Reading Console Announcements by Impact Level

Console Announcements communicate important operational information. Typical categories include **Required action**, **Recommended action**, **Scheduled maintenance**, **Planned change**, and **Information**. Full meanings and categories reside in Console Announcements documentation.

You do not need to memorize the entire label list. Determine whether an announcement requires action, has an impact window, or simply provides information to monitor.

When opening an announcement, answer:

1. Which services and environments are affected?
2. Which regions, resources, or scopes are listed?
3. When does it start and end, and in which time zone?
4. Is action required before a deadline?
5. Might restarts, connection drops, or behavior changes occur?
6. Are there schedule updates or completion confirmations?

If the interface shows no announcements or only summaries, check permissions. Documentation notes that viewing lists and details depends on granted permissions; do not conclude “no changes” solely from a blank screen.

### 11.1. Reading Details and Update History

An announcement may include a description, OCID, and reference ID for communicating with Support. See [Viewing the Details of an Announcement](https://docs.oracle.com/en-us/iaas/Content/General/Concepts/announcements_topic-To_view_the_details_of_an_announcement.htm).

A maintenance schedule can be updated. When preparing to act, reopen the announcement and verify the current version rather than relying solely on the initial email.

Timestamps should be recorded in both the original reference and local time. Hypothetical example:

~~~text
Window in notice:        01:00–02:00 UTC
Vietnam time, UTC+7:     08:00–09:00 same day
~~~

If timezone conversion crosses midnight, the local calendar date changes too. Also, do not infer impact scope solely from a region name appearing in the sender email address.

### 11.2. Setting Up Notification Channels

OCI supports announcement subscriptions with filters and a Notifications topic to forward notices to configured endpoints. See [Subscribing to Announcements](https://docs.oracle.com/en-us/iaas/Content/General/Concepts/announcements_topic-Subscribing.htm).

Operationally, define:

- Who reads notices for each service group?
- Do filters miss any resources or regions in use?
- Are receiving endpoints active and monitored?
- Who handles items when the primary owner is away?
- After system scope changes, are filters updated?

Merely creating a subscription does not prove the whole team receives and acts on notices. Verify delivery channels within supported capabilities and establish clear response accountability.

These guidelines describe procedures for learners' own systems; this lesson does not create subscriptions or send notifications.

## 12. Turning an Announcement Into a Change Plan

An announcement only has operational value when linked to the resources and code actually in use.

### 12.1. Impact Assessment Workflow

~~~mermaid
flowchart TD
    A["Receive release note or announcement"] --> B["Identify service, scope, and timeline"]
    B --> C["Cross-check resources, versions, and configuration"]
    C --> D{"Is the system in the affected scope?"}
    D -->|"Unclear"| E["Gather more evidence or ask Support"]
    E --> C
    D -->|"No"| F["Record rationale and conditions to revisit"]
    D -->|"Yes"| G["Plan action, owner, and deadline"]
    G --> H["Test in an appropriate environment"]
    H --> I["Deploy per change plan"]
    I --> J["Verify results and monitor post-change"]
~~~

To conclude your system is unaffected, you need evidence. For example, the notice applies to an endpoint type the system does not use. Saying “no errors seen yet” does not prove independence from an upcoming change.

### 12.2. Hypothetical Example With a Java Application

Suppose Oracle announces that after a milestone date, a service will stop accepting an older TLS configuration. This is an illustrative scenario, not a representation of a current schedule.

The team must clarify:

| Step | Evidence or Outcome Needed |
| --- | --- |
| Identify dependencies | Which Java clients and intermediate components connect to the affected endpoint |
| Check current state | Runtime version, HTTP library, and TLS config actually running |
| Select change | Update method matching documentation and supportability |
| Test beforehand | Connectivity, authentication, representative load, and error cases tested |
| Deploy | Defined timestamp, owner, and monitoring signals |
| Confirm | Business requests traversing the full chain still complete |

Updating the SDK alone may not suffice if connections also pass through a proxy or another component with its own settings. Conversely, if the issue lies in client-side code, modifying VM configuration alone may not address the root cause.

Rollback plans must also be evaluated against effective dates. Once a provider retires an older capability, reverting a client to old settings may not restore service. In that case, fallback options must stay within still-supported capabilities.

### 12.3. Writing an Auditable Action Item

~~~text
Official source:
Announcement ID or URL:
Last checked date:
Effective date / maintenance window:
Affected resources and environments:
Impact conclusion and evidence:
Action:
Owner:
Internal deadline:
Test method and success criteria:
Fallback plan if change fails:
Status and completion evidence:
~~~

Internal deadlines should leave room for testing and adjustments before mandatory cutoffs. For rescheduled announcements, update the plan with the revised details.

## 13. Practice Reading Documentation Before an OCI Lab

Suppose you are preparing to build an environment for a Java API, connect an Oracle Database service, and store files on Object Storage.

Before provisioning, complete these steps:

1. **Choose sources:** open the official documentation for each service and identify the deployment model.
2. **Read prerequisites:** note IAM permissions, network requirements, and required components.
3. **Match tooling:** note the intended CLI or SDK version and open its corresponding documentation.
4. **Read limits:** identify limit name, unit, scope, and value in the tenancy.
5. **Calculate demand:** include initial resources plus temporary headroom needed for updates or recovery tests.
6. **Check changes:** read service changes, known issues, and relevant announcements.
7. **Define outcomes:** record how to tell resources and application flows are working.
8. **Prepare teardown:** identify data to retain and resources to clean up.

Results can be presented in a table:

| Component | Applicable Documentation | Key Prerequisites | Limits to Check | Completion Signal |
| --- | --- | --- | --- | --- |
| Java API | Guide for Compute or chosen execution platform | Permissions, image, networking, runtime | Limits related to configuration and volumes | API passes health checks |
| Oracle Database | Docs for the exact service and model | Connectivity, permissions, deployment choices | Capacity, storage, and related resource limits | Application executes required data operations |
| Object Storage | Bucket and object access guides | Permissions, authentication mechanism, network path | Constraints on buckets, objects, and operations used | Writing and reading back a mock file succeeds |

You do not need to create resources to practice documentation identification. If you do not yet have a tenancy or permission to view limits, mark the missing data; default tables remain reference material only until the real environment is checked.

## 14. Misconceptions to Avoid

| Misconception | Correct Way to Read and Handle |
| --- | --- |
| The newest doc page always fits the project | Cross-check the product, model, and version in use |
| A successful tutorial means production is ready | Add permissions, cost controls, operations, and recovery per requirements |
| Default limits are guaranteed tenancy values | Check actual values and active filters |
| Available means a VM can definitely be created | Check hardware capacity and provisioning prerequisites separately |
| Raising quota bypasses service limits | Service limits still remain enforced |
| Every 404 error means the resource does not exist | Read the error code, permissions, and API-specific conditions |
| Continuous retries will resolve limit errors | Address the blocking limit or quota condition |
| Release notes replace all operational notices | Follow service changes and environment announcements too |
| Receiving the email means the change is handled | An owner, action, and completion evidence are needed |
| Seeing no alerts means zero impact | Verify scope, permissions, filters, and actual dependencies |

As you study subsequent OCI topics, maintain the habit of tying each decision to **official source, applicable scope, environment data, and verification timestamp**. Doing so grounds authorized deployments, automation, cost control, and availability readiness in verifiable conditions.