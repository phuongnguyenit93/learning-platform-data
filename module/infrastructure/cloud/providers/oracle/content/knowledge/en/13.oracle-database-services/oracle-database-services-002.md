# License Included, BYOL, and Operational Responsibility Scope

In the **Oracle Database on OCI** chapter of the **CLOUD_PROVIDERS_ORACLE** module, choosing a database service requires answering two independent questions: **where software usage rights come from** and **who is responsible for each operational task**.

An application on Compute can connect over a VCN to Base Database Service or Autonomous Database. For the same data requirement, an organization can use the software rights bundled with the service or bring existing licenses if eligible. That choice affects cost and entitlement management, but it does not replace designing IAM, networking, backups, monitoring, or recovery.

## Learning Objectives

After this lesson, learners will be able to:

- Explain License Included and Bring Your Own License in the context of Oracle Database services.
- Distinguish between license model, database edition, compute metric, and level of service management.
- Identify the information that must be reconciled before choosing BYOL or scaling capacity.
- Assign operational tasks between Oracle and customer teams by service type.
- Read license configurations on OCI without confusing technical settings with entitlement evidence.
- Plan costs and resource changes while accounting for backups, DR, clones, and scalability.

## Two Selection Axes to Separate

The **license model** answers how software usage rights are provided or applied. The **service operating model** answers which layers Oracle operates and which layers the customer manages.

~~~mermaid
flowchart TD
    W["Workload requirements"] --> L["Software usage rights"]
    W --> O["Operational scope"]
    L --> LI["License Included"]
    L --> BY["BYOL when eligible"]
    O --> C["Self-managed on Compute"]
    O --> B["Base Database Service"]
    O --> E["Exadata Database Service"]
    O --> A["Autonomous Database"]
    LI --> R["Verify against actual service combination"]
    BY --> R
    C --> R
    B --> R
    E --> R
    A --> R
~~~

The diagram is a way to analyze requirements, not a claim that every service or edition supports every combination. For example, BYOL options for one specific Autonomous workload may differ from another; developer-oriented programs also carry their own restrictions.

Two Base Database DB systems with the same configuration, edition, and management model but different license models still require someone responsible for software updates, data protection, and application handling. Switching the license model does not turn a DB system into an Autonomous Database.

## License Included: Software Rights Bundled with the Chosen Service

With **License Included**, the price of the service resource includes Oracle Database software rights within the scope of the selected edition/package and cloud service. Users do not need to bring existing licenses to cover the rights already included. Base Database creation documentation distinguishes this option directly from BYOL; see [License type when creating a DB system](https://docs.oracle.com/en/cloud/paas/base-database/guide/dbs-create-new.html).

Understand the exact boundaries of the word "included":

| What can be inferred | What must not be assumed |
| --- | --- |
| The chosen service provides the software rights per service terms | Every Oracle product, edition, option, and management pack is usable |
| The service cost reflects the license choice | All storage, backup, DR, and network connectivity have no separate fees |
| Usage rights apply within the scope of the service subscription | You gain a perpetual license you can freely deploy elsewhere |
| Support follows the corresponding subscription scope | Oracle is responsible for fixing all application bugs or administering every schema |

For example, a team building a new application without a suitable license pool can evaluate License Included to avoid allocating existing software rights to that resource. They still must select the right service, edition, and needed features, then calculate costs based on actual consumption.

Do not use a quote stating only "Oracle Database" to conclude all enterprise capabilities are included. You must know the exact SKU/service, edition, version, and applicable feature entitlements.

## BYOL: Applying Existing Rights While Still Paying for the Service

**Bring Your Own License — BYOL** allows applying eligible existing Oracle licenses to the corresponding cloud service. The organization supplies its own entitlement in place of the software rights portion provided by the License Included service.

BYOL still incurs cloud subscription charges and related operational costs. The organization also continues fulfilling applicable support obligations for the brought licenses. Licenses applied to a BYOL service are considered in use; they cannot be treated as idle simply because they reside in the cloud. See [Oracle BYOL billing models](https://docs.oracle.com/en/cloud/get-started/subscriptions-cloud/ocpib/billing-models-offered.html).

**Entitlement** is the scope of usage rights substantiated by contracts and related documentation: product, edition, metric, quantity, deployment scope, and accompanying terms. It is not a configuration flag in OCI.

Three things must be kept distinct:

~~~text
Organization holds a valid license record
    -> allocates entitlement to the cloud workload
    -> configures the BYOL license model on the right resource
~~~

If the first or allocation step is missing, a resource may still display BYOL even though the organization has not proven the corresponding usage rights. API acceptance of the operation only confirms the technical request is valid in the API context.

### BYOL to PaaS Differs from Self-Managed Deployment on IaaS

Bringing licenses into a managed database service is not the same as installing Oracle Database on a standard Compute VM. Additional entitlements, capacity mapping rules, and operational tasks can differ.

Oracle has a BYOL to PaaS program and describes differences from BYOL to IaaS, including certain additional feature entitlements within PaaS scope. Therefore, do not use the PaaS entitlement table to assume similar rights for a self-managed installation on Compute. See [Oracle BYOL FAQ](https://www.oracle.com/cloud/bring-your-own-license/faq/).

Avoid the opposite mistake as well: do not assume you must separately purchase every option already covered in PaaS. Reconcile the extra rights granted by the service against the licenses the organization actually needs to bring.

## Information That Must Be Reconciled for BYOL

Before deployment, connect contractual information with the planned workload configuration:

| Information Group | What to Identify | Why It Is Needed |
| --- | --- | --- |
| Product and edition | Which product and which edition are licensed | The name Oracle Database alone does not match every service |
| Metric | Processor, Named User Plus, or contract-defined metric | Do not convert metrics by guessing user counts or CPU numbers |
| Quantity | Allocatable rights, used rights, and remaining balance | Prevents double-allocating entitlements |
| Options and packs | Which features are licensed and which rights the service includes | Technical availability does not prove usage entitlement |
| Support | Which support contract covers it and its active status | Matches service terms and support channels |
| Target service | Base, Exadata, Autonomous; specific deployment configuration | Mapping and limits may differ |
| Compute model | ECPU, OCPU, or metric of the active offering | Do not treat units as equivalent by default |
| Environments | Production, test, clone, standby, and migration | Usage scope may extend beyond primary |
| Special agreements | ULA terms or dedicated programs if any | Do not mechanically apply rules from another program |

Reference sources include the agreement, ordering document, service description, and policies applicable to the organization. Oracle describes cloud contract structure across these components at [Cloud Services Contracts](https://www.oracle.com/contracts/cloud-services/).

Product documentation helps understand parameters and service capabilities; contractual documents define applicable rights. A Console screenshot or information from another environment cannot replace this chain of evidence.

### Do Not Use One Generic CPU Ratio for Every Case

Do not establish internal rules like "one license always equals one cloud CPU" or take one OCPU mapping and apply it directly to ECPU. Conversion rules must match the exact product, edition, metric, service, and term version.

The practical approach is to record the mapping source, effective date, and applied configuration. When switching compute models or services, recalculate from the corresponding source rather than just renaming a column in a spreadsheet.

The catalog can also change over time. Base Database documentation currently contains change/retirement notices for several older shapes and SKUs; do not use an old tutorial's configuration as proof that new resources can still be provisioned. See [About Oracle Base Database Service](https://docs.oracle.com/en/cloud/paas/base-database/guide/about.html).

## Edition, License Model, and Features Are Three Separate Attributes

A resource can be described by distinct attributes:

~~~text
Service: database service type
Edition: selected software package
License model: LICENSE_INCLUDED or BRING_YOUR_OWN_LICENSE
Compute model: capacity measurement and billing unit
Capacity: configured resource size
Features: capabilities actually used
~~~

The edition name identifies the capability tier; the license model states how rights are supplied. Do not use one attribute as a stand-in for another.

For example, to use RAC, a database option, or a management pack, the project team must verify both service support and the corresponding usage entitlement. Being able to enable a feature does not prove every deployment of that feature is compliant.

For Base Database Service, License Included receives support via the database service subscription. BYOL customers must maintain a valid support contract covering the licenses used in the service. Customers remain responsible for applying database updates promptly. See [Base Database Service Support Requirements](https://docs.oracle.com/en/cloud/paas/base-database/guide/about.html).

Do not generalize Base Database-specific conditions into an identical obligation table for every other offering.

## Operational Responsibilities by Service Level

Oracle is responsible for the layers managed by the service; the customer is responsible for workloads, configurations, and data within their scope. OCI's security model also separates infrastructure responsibilities from protecting Compute workloads and operating systems. See [OCI Shared Security Model](https://docs.oracle.com/en-us/iaas/Content/Security/Concepts/security_overview.htm).

The table below serves as an assignment baseline and must be tailored to the chosen service:

| Task | Self-managed database on Compute | Base Database Service | Exadata Database Service on Dedicated Infrastructure | Autonomous Database |
| --- | --- | --- | --- | --- |
| Cloud infrastructure provided by Oracle | Oracle manages infrastructure layer | Oracle manages | Oracle manages Exadata infrastructure | Oracle manages |
| Database environment Guest OS | Customer manages | Customer responsible for updating DB system OS layer | Customer responsible for Guest VM OS | Oracle manages service runtime layer |
| Database software and routine maintenance | Customer organizes execution | Tooling provided, customer organizes updates and testing | Automation provided, customer responsible for DB/GI of managed environment | Oracle automates service-managed admin tasks |
| Schemas, data, and application permissions | Customer | Customer | Customer | Customer |
| Recovery objectives and business verification | Customer defines and drills | Customer defines and drills | Customer defines and drills | Customer still defines and verifies |
| BYOL entitlement allocation if used | Customer | Customer | Customer | Customer |

### Base Database: Automation Exists, Operations Team Still Needed

Oracle provides the infrastructure and service lifecycle tools. The customer team must still organize OS/database updates, testing, application monitoring, and data backup/recovery management per the responsibility split. Having a Patch button or Backup feature does not mean Oracle has taken over planning and sign-off obligations. See [Base Database security and operational responsibility table](https://docs.oracle.com/en/cloud/paas/base-database/guide/security-guide.html).

The operations team should have an owner to receive patch alerts, choose maintenance windows, perform pre-checks, confirm required backups, and validate the application after changes. Task owners can use automation to execute work while remaining accountable for outcomes.

### Exadata Database Service Does Not Mean Autonomous Database

With Exadata Database Service on Dedicated Infrastructure, Oracle manages the infrastructure; the customer manages accessible components such as Guest VMs and database services, including corresponding maintenance responsibilities. This is not the same operational boundary as Autonomous Database merely because both can run on Exadata technology. See [Exadata Database Service Security Guide](https://docs.oracle.com/en/engineered-systems/exadata-cloud-service/ecscm/ecs-security-guide.html).

### Autonomous: More Automation, Customer Still Manages the Application

Autonomous Database automates tasks such as applying security patches and providing automated backups according to service capabilities and configuration. See [Autonomous Database Security Features Overview](https://docs.oracle.com/en/cloud/paas/autonomous-database/serverless/adbsb/security-features-overview.html).

Customers still must design schemas, control accounts, configure connectivity, protect secrets, and test application behavior. When application-caused data corruption occurs, someone must select the recovery point, coordinate the application, and validate data after restore.

An example of this boundary: database backups do not include external data files in Object Storage used by external tables. The customer must arrange protection and recovery of those files to obtain a consistent dataset. See [Restore and Recover Autonomous Database](https://docs.oracle.com/en/cloud/paas/autonomous-database/serverless/adbsb/backup-recover.html).

Therefore, "Oracle manages backups" and "the entire system recovers accurately for the business" are two different outcomes requiring dedicated ownership.

## Scaling, Cloning, and DR Change the Scope to Calculate

An inventory listing only primary CPU counts during normal operation is rarely sufficient for a design involving scaling and recovery.

| Change | What to Evaluate First |
| --- | --- |
| Increasing primary compute | Entitlement mapping per service metric and post-change capacity |
| Enabling auto scaling | Additional capacity that may be consumed and how the service handles licensing/billing |
| Creating clones for testing | License model, edition, and lifetime of the clone |
| Creating standby | Entitlements for standby deployment, features used on standby, and applicable terms |
| DR drills | Entitlements for activated environments, concurrent runtime, and capacity during failover |
| Migration | Period when source and target run concurrently, applicable rights and transition terms |
| Changing service or compute model | Re-check mapping rules, feature packages, and cost |
| Stopping or deleting resources | Billing conditions, retained data/backups, and updating license allocations |

Do not assume test environments, clones, standbys, or low-activity servers require no licensing calculation. Nor should you apply a generic standby rule to every product without checking the corresponding terms.

With Base Database clones, the clone's license selection applies to the clone and does not alter the source. That demonstrates the need to check each derived resource rather than treating clones as free copies from a usage-rights perspective. See [Clone a DB System](https://docs.oracle.com/en/cloud/paas/base-database/guide/dbs-clone.html).

### BYOL Limits May Cap Covered Entitlement, Not Total Capacity

Autonomous Database with ECPU supports BYOL and edition choices depending on supported workloads. For Enterprise Edition, documentation describes a BYOL ECPU limit option defining the ECPU portion covered by brought licenses. Constraints for Standard Edition differ from Enterprise Edition. See [BYOL on Autonomous Database ECPU](https://docs.oracle.com/en/cloud/paas/autonomous-database/serverless/adbsb/autonomous-update-license.html).

In the Autonomous API/CLI, the `byol-compute-count-limit` attribute describes the CPU limit covered by BYOL; usage exceeding that limit is treated as License Included and billed accordingly. The documented scope also relates to auto scaling and resources used for corresponding DR/tooling. See [BYOL compute count limit parameter](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/db/autonomous-database/create.html).

The key takeaway is that a supported BYOL limit can split how entitlement coverage and billing apply; do not assume it acts as a hard cap blocking all compute demand.

This is documented offering behavior, not a universal rule that every Oracle service allows mixing BYOL and License Included on the same resource. When designing from general FAQs, also verify current documentation for the exact service and compute model.

### Allocation Management Example

Suppose an organization has verified an entitlement pool that, after proper mapping to the target service, can cover **100 hypothetical capacity units**:

~~~text
Workload A allocated: 40
Workload B allocated: 30
Unallocated balance:  30

Proposed workload C:  50
Shortfall:            20
~~~

The units above only illustrate allocation tracking; they are not ECPUs, OCPUs, or Oracle-published ratios. Do not plug those numbers into an actual licensing calculation.

The conclusion to draw is that proposal C needs adjustment or a confirmed additional entitlement/subscription mechanism. The fact that C averages only 10 units during testing does not prove licensing scope only needs 10; the exact metric and measurement rules must be applied.

## Evaluating Cost Across the Whole System

Comparing License Included with BYOL should start from the same workload requirements: same service, same performance targets, same availability strategy, and same protected data scope.

An internal cost model can be written as:

~~~text
Total cost for the period
  = cloud service fees under the chosen license model
  + separately billed storage and backups
  + DR, clone, and test environment resources
  + data transfer and supporting services
  + support or additional software rights not covered elsewhere
  + operational and system change effort
~~~

This is an analytical framework, not a price sheet. When a component is already included in a subscription, do not double-count it. When BYOL uses previously purchased licenses, still account for support obligations and the opportunity cost of no longer having that entitlement free for other workloads.

Common comparison distortions:

- Comparing BYOL primary cost against License Included primary plus DR cost.
- Comparing Base Database requiring administration against Autonomous while omitting all operational work.
- Applying one compute model's price to another compute model's capacity.
- Ignoring concurrent runtime during migrations or drills.
- Assuming stopping compute eliminates all storage, backup, and support charges.
- Using a few days of test costs to forecast production without accounting for peak load.

BYOL can help leverage existing rights; actual benefit depends on usable entitlements and service configuration. License Included may fit when service-supplied rights are needed. There is no universal conclusion that one option is always cheaper for every organization.

## Practice: Reading Configuration and Reconciling Rights

This exercise uses read-only operations. The goal is to separate three layers of evidence: **OCI configuration**, **entitlement records**, and **operational assignment**. There is no need to create a database or switch to BYOL just to inspect a value.

Prepare a lab resource or a resource with read permissions, in the right region and compartment, along with an authenticated OCI CLI. Run only the command group matching the service you have. You do not need both Base Database and Autonomous Database.

### Reading Base Database License Model

The commands below use Bash; replace the region and OCID with an authorized resource:

~~~bash
REGION="ap-singapore-1"
DB_SYSTEM_ID="REPLACE_WITH_BASE_DB_SYSTEM_OCID"

oci db system get \
  --region "$REGION" \
  --db-system-id "$DB_SYSTEM_ID" \
  --query 'data.{id:id,name:"display-name",license:"license-model",edition:"database-edition",shape:shape}' \
  --output json
~~~

This command retrieves DB system metadata and does not access business table data. See [OCI CLI db system get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/db/system/get.html). Do not use this legacy DB system API model as a template for managing all current Exadata resources.

Observe license model and edition independently. Two common license model values are:

~~~text
LICENSE_INCLUDED
BRING_YOUR_OWN_LICENSE
~~~

If the resource returns BYOL, you can only conclude OCI is configured with that model. You cannot yet conclude license counts are sufficient, support is valid, or option entitlements are confirmed.

If a field is missing or returns null, inspect the full output and the exact resource schema; do not turn null into "no license required."

### Reading Autonomous Database Information

For Autonomous Database Serverless, relevant fields can be read as follows:

~~~bash
REGION="ap-singapore-1"
ADB_ID="REPLACE_WITH_AUTONOMOUS_DATABASE_OCID"

oci db autonomous-database get \
  --region "$REGION" \
  --autonomous-database-id "$ADB_ID" \
  --query 'data.{id:id,name:"display-name",license:"license-model",edition:"db-edition",computeModel:"compute-model",computeCount:"compute-count",autoScaling:"is-auto-scaling-enabled",byolLimit:"byol-compute-count-limit"}' \
  --output json
~~~

See [OCI CLI autonomous-database get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/db/autonomous-database/get.html). Fields carry meaning according to the active compute model, workload, and deployment; do not treat `compute-count` as a universal substitute for every capacity attribute across all database types.

In an Autonomous deployment on dedicated infrastructure, the license may be set at the infrastructure resource level per the service model rather than selected independently per database. Therefore, if reconciling that offering, inspect the proper configuration level. Reference [Autonomous license-model description](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/db/autonomous-database/create.html).

### Recording Reconciliation Results

Use a working record like the template below in your organization's resource management process:

~~~text
Resource OCID: value read from OCI
Region / compartment: verified
Service / deployment: identified
Edition: configured value
License model: configured value
Compute model / capacity: specific value and unit
Auto scaling / BYOL limit: value or not applicable
Related clone / standby / DR: inventoried

Entitlement reference: internal record ID, or UNCONFIRMED
Mapping rule reference: term source and effective date
Allocated entitlement: reconciled quantity, or UNCONFIRMED
Support reference: coverage record, or UNCONFIRMED

License owner: responsible role
Patch owner: responsible role
Backup / recovery owner: responsible role
Application validation owner: responsible role
~~~

This is a learning template, not an actual license record or a request to put sensitive contracts into a repository. Reference record IDs in an appropriate repository instead of copying secrets or full contract text into deployment logs.

The exercise achieves its goal when the learner can explain which values were read directly, which have entitlement sources, and which remain unconfirmed. Filling a blank with a guessed number does not complete reconciliation.

## Changing the License Model Is a Controlled Change

Base Database has an operation to update the license type on a DB system. That choice affects metering and billing; it does not create or purchase additional existing entitlements for the organization. See [Manage Licenses on a DB System](https://docs.oracle.com/en/cloud/paas/base-database/guide/dbs-licenses.html).

A change procedure can include:

1. Identify the exact resource, service, edition, and current configuration.
2. Confirm the target model is supported by the service and entitlements are allocatable if using BYOL.
3. Assess compute, auto scaling, clones, DR, support, and cost impacts.
4. Record the decision and accountable owner before making the change.
5. Apply the exact service operation; wait for completion and re-read status.
6. Reconcile usage/billing after the change timestamp and update the allocation ledger.
7. Verify the application, alerts, and related configurations still meet requirements.

Do not assume changing the license model changes the database edition or removes features already used. Nor should it be treated as retroactive licensing validation for all prior runtime.

When forecasting conversion costs, check the service's Known Issues instead of assuming metering switches instantaneously with zero overlap. The [Base Database Known Issues](https://docs.oracle.com/en/cloud/paas/base-database/guide/known-issues.html) documentation has a dedicated item regarding billing when changing license types.

With automated infrastructure, declare the license model intentionally and verify again after provisioning. Do not rely on UI/SDK defaults or copy another team's BYOL template: a default does not confirm your workload holds an entitlement.

## Breaking Down Operational Teams into Concrete Tasks

Statements like "DBAs handle the database" or "Oracle handles the cloud" are too broad to use during an incident. Assign specific tasks, execution permissions, and completion evidence.

The table below is an example assignment **within the customer organization**, and does not alter contractual boundaries between Oracle and the customer:

| Task | Suggested Lead Role | Collaborators | Completion Evidence |
| --- | --- | --- | --- |
| Confirm BYOL rights | License manager | Procurement, DBA, contract owner | Records and entitlement allocation match resources |
| Select sizing and edition | DBA / data architect | Application team, license owner | Configuration meets load and feature entitlements |
| Configure VCN, subnet, NSG | Platform / network team | DBA and security | Connections match source, port, and destination |
| IAM and database permissions | Security team with DBA | Application owner | Administrative and SQL permissions separated properly |
| Schedule patching for customer-managed layers | Database operations team | Application team | Pre-checks, update results, and post-change testing |
| Backup policy and monitoring | Data recovery lead | DBA, platform team | Backups meet scope and retention requirements |
| Restore / DR drills | Recovery lead | Application, network, license owner | Data and business flows verified |
| Cost control | Budget owner / FinOps | DBA, license owner | Usage, allocations, and cost forecasts reconciled |

IAM grants permissions to manage OCI resources; in-database privileges control access to data objects via database mechanisms. Calling an API to view a DB system does not automatically allow selecting from business tables. Conversely, a SQL account cannot implicitly scale or delete cloud resources.

For patching, the owner must know which layers Oracle updates and which layers their own team executes. With Autonomous, the application owner still monitors relevant maintenance notices, tests connectivity, and verifies application recovery; do not plan to SSH into the service OS like a self-managed Compute machine.

For backups, define data scope, retention periods, encryption keys, restore permissions, and required recovery points. Autonomous provides backup/restore management operations per the offering; the customer must still select suitable configurations within provided capabilities. See [Backup and Restore Autonomous Database](https://docs.oracle.com/en/cloud/paas/autonomous-database/serverless/adbsb/backup-restore.html).

A successful backup does not prove system-wide RTO/RPO. **RPO** is the acceptable data loss window in time; **RTO** is the target time to restore service. The application team must verify both database data and dependencies in Object Storage or external systems if present.

## Common Misconceptions

| Statement | Correct Understanding |
| --- | --- |
| Selecting BYOL in the Console means Oracle verified the license | It is a technical setting; entitlement requires separate verification records |
| BYOL means using the cloud database for free | Service charges and related obligations still apply |
| License Included means Oracle operates everything | Operational scope depends on the service, not the license model alone |
| License Included permits all Oracle options | Only usable within the package rights and applicable terms |
| Enterprise Edition automatically covers all rights everywhere | Must verify options, packs, and IaaS/PaaS differences |
| ECPU and OCPU can be swapped one-for-one | Must identify the exact compute model and mapping rules |
| Low average CPU means you only need rights for the average | Must apply the exact metric and measurement rules of the service/contract |
| Licensing primary covers all clones and standbys | Must account for related deployments and active usage periods |
| Automated backups mean no recovery owner is needed | Someone must still decide restores, coordinate, and verify business data |
| Stopping a database eliminates all charges | Must check compute, storage, backups, support, and remaining charges |
| Successful automation proves the whole design is compliant | Automation only executes configuration; entitlement and operational evidence are still required |

A deployment-ready design must connect three parts: actual service configuration, substantiated software rights, and an owned task list. When one part remains unconfirmed, explicitly record what is missing before expanding usage scope.
