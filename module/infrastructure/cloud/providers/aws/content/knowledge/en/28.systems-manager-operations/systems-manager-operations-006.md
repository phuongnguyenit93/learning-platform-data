# Inventory and Fleet Software Management

An organization may operate hundreds or thousands of EC2 instances, datacenter servers, and VMs in other environments. As node counts grow, answering questions such as which machines run which operating system, which agent version is installed, which nodes are missing standard software, or which environments contain a given application becomes difficult if you have to log in and inspect manually.

AWS Systems Manager provides two complementary capability groups to solve this problem:

- **Inventory** collects and stores metadata about managed nodes, hardware, operating systems, applications, packages, and related configuration. Operations teams use this data to search, reconcile, and build reports across the fleet.
- **Distributor, Run Command, and State Manager** distribute, install, uninstall, and maintain software on managed nodes. Operations teams can deploy once or declare a desired state for Systems Manager to enforce on a schedule.

Within the **CLOUD_PROVIDERS_AWS** ecosystem, this brings software management across EC2 and hybrid servers into a repeatable workflow governed by IAM, tracked through association status, and backed by audit data. The goal of the module is to help learners select AWS services and design and deploy secure, observable, recoverable, and cost-controlled applications; Inventory and software management contribute by maintaining a consistent operational baseline across the entire fleet.

## 1. What Problems Do Inventory and Software Management Solve?

Inventory answers the question **what is currently on the fleet**. For example, an operations team can find nodes running Amazon Linux, identify which hosts have Amazon CloudWatch Agent installed, compare Java versions across environments, or list servers carrying a package affected by a vulnerability.

Software management answers the question **what should the fleet have and how do we deliver it to the right nodes**. For example, a platform team can standardize CloudWatch Agent, SSM Agent, or a security agent; deploy the approved version to nodes with matching tags; and then maintain installation state with State Manager.

The two capabilities complement each other:

| Need | Appropriate Capability | Outcome |
|---|---|---|
| Know what software is installed on nodes | Systems Manager Inventory | Collected software metadata available for querying |
| Install a package on a group of nodes | Distributor combined with Run Command | Install command dispatched to target managed nodes |
| Maintain a package at a specified version | Distributor combined with a State Manager association | Periodic association enforces the installation configuration |
| Detect nodes drifting from baseline | Inventory, queries, and reporting | List of nodes requiring investigation or remediation |
| Track execution outcomes | Run Command, State Manager, and Systems Manager Compliance | Command status, association status, and compliance details |
| Analyze multi-account/Region fleets | Resource Data Sync and Amazon S3 | Centralized Inventory data for querying and reporting |

Inventory primarily captures observable state at collection time. It does not install software, fix configurations, or prove that software was approved by the organization. To enforce desired state, use Distributor, Run Command, State Manager, or an appropriate configuration management tool.

## 2. Prerequisites for Nodes to Appear in Systems Manager

Systems Manager manages registered nodes that meet connectivity prerequisites. A node can be an EC2 instance or a hybrid server running outside AWS. Before enabling Inventory or deploying packages, verify the foundational conditions.

### 2.1. SSM Agent

SSM Agent runs on the node, receives work from Systems Manager, and reports status or collected data back to the service. The agent must be installed, running, and at a version compatible with the command documents used. Some AWS AMIs include the agent preinstalled; custom images or external servers may require separate installation and updates.

An outdated, stopped, or disconnected agent prevents the node from receiving commands on time, reporting fresh Inventory, or showing accurate status. Thus, SSM Agent is a foundational component that must be monitored like any other operational agent.

### 2.2. IAM and Managed Node Identity

For EC2, attach an instance profile with appropriate Systems Manager permissions. The AWS managed policy **AmazonSSMManagedInstanceCore** is commonly used as a starting point for managed node permissions; environments with stricter requirements can use a custom policy with equivalent least-privilege permissions.

For servers outside AWS, create a hybrid activation and register the node as a managed node. This workflow uses an activation code, activation ID, and an appropriate role. Protect activation details like sensitive credentials, limit expiration and registration counts, and revoke unused activations.

Node permissions to connect to Systems Manager are distinct from operator permissions to call APIs. Operators need separate IAM policies for actions such as viewing Inventory, creating associations, sending Run Commands, managing packages, or configuring Resource Data Sync.

### 2.3. Network Connectivity

Nodes must be able to reach the required Systems Manager endpoints in their Region. Connectivity can traverse Internet/NAT or VPC interface endpoints depending on network architecture. Endpoints such as **ssm**, **ssmmessages**, and **ec2messages** have requirements that vary by Region, node type, and agent version; verify against AWS documentation for the target Region.

When deploying packages from Distributor, nodes also need access to the package download source used by the workflow, typically involving Amazon S3 or related endpoints. VPC endpoint policies, security groups, routes, DNS, and bucket policies can all interrupt package downloads even when a node appears in Managed nodes.

### 2.4. Pre-Collection Verification

In Systems Manager Fleet Manager or the Managed nodes page, confirm the node is registered, ping status is Online, and Platform and Agent version are recognized. You can use the AWS CLI:

~~~bash
aws ssm describe-instance-information \
  --filters "Key=PingStatus,Values=Online" \
  --query "InstanceInformationList[].{Id:InstanceId,Platform:PlatformName,Version:AgentVersion,Ping:PingStatus}" \
  --output table
~~~

This command shows Online nodes that the current identity is permitted to query. If a node is missing, resolve SSM Agent, instance profile or hybrid activation, and network connectivity before troubleshooting Inventory.

## 3. What Data Does Systems Manager Inventory Collect?

Inventory collects information according to schema-defined data types. Common types include:

| Inventory type | Content | Usage Example |
|---|---|---|
| **AWS:InstanceInformation** | OS, platform, agent version, and node metadata | Find nodes by platform or agent version |
| **AWS:Application** | Applications and software detected on the node | Find hosts with Java, monitoring agents, or a specific package |
| **AWS:Network** | Supported network adapter and network configuration info | Investigate network differences across nodes |
| **AWS:WindowsUpdate** | Collected Windows Update information | Identify Windows updates present on a machine |
| **AWS:PatchSummary** | Patch status summary related to Patch Manager | Quick overview of node patch state |
| **AWS:PatchGroup** | Assigned patch group information | Correlate nodes with patch baselines |
| **AWS:Service** | OS services collected on supported platforms | Check whether a service is installed or detected |
| **AWS:WindowsRole** | Collected Windows roles | Find Windows machines serving specific roles |
| **AWS:File** | File metadata per Inventory configuration | Verify presence and attributes of specified files |
| **AWS:WindowsRegistry** | Registry data per Windows configuration | Inventory registry keys requiring tracking |
| **Custom:...** | Organization-added metadata using a custom schema | Record application owner, runtime environment, or release ID |

Available data types depend on the operating system, node type, SSM Agent version, and configuration parameters. Not every node supports every inventory type. For instance, Windows Update and Windows Registry apply only to Windows; Linux package details vary by OS and package manager.

Inventory stores attributes according to schemas. Because schemas or attribute sets can vary across platforms, call the **GetInventorySchema** API to inspect available types and attributes before building automated queries.

Inventory can collect applications and packages recognized by the agent, but it is not an exhaustive security scanner. Portable software, manually copied binaries, container images, dependencies inside application directories, or components unsupported by the collector may not appear as installed applications. Define inventory scope clearly before using the data for compliance decisions.

## 4. Enabling Inventory Collection Across a Fleet

A common way to enable Inventory is creating a State Manager association with the **AWS-GatherSoftwareInventory** SSM document. The association specifies the document, target nodes, execution schedule, and parameters. SSM Agent on target nodes runs the document on schedule and sends Inventory results back to Systems Manager.

Example creating an association for nodes tagged `Environment=production`:

~~~bash
aws ssm create-association \
  --name "AWS-GatherSoftwareInventory" \
  --association-name "collect-production-inventory" \
  --targets "Key=tag:Environment,Values=production" \
  --schedule-expression "rate(1 day)"
~~~

This example collects Inventory daily for nodes matching the tag when the association runs. You can pick a shorter interval for fleets needing fresher data, weighing agent overhead, node count, and query needs. Inventory is periodic data; it should not be treated as real-time state immediately after every host change.

### Choosing Association Targets

You can target by instance ID, tags, or supported node groups. Using tags expands coverage automatically when new nodes are launched with matching tags. Examples:

- `Environment=development` for development environments.
- `Environment=production` for production.
- `Application=orders` for the Orders application fleet.
- `ManagedBy=platform` for nodes owned by the platform team.

Tags must be governed consistently. If a node lacks a tag or carries the wrong tag, the association may miss it or collect out-of-scope data. Combine tagging standards with AWS Organizations Tag Policies, provisioning pipelines, and periodic audits to keep targeting accurate.

### Choosing a Collection Schedule

The collection schedule depends on fleet churn and inventory goals:

| Fleet Type | Reference Schedule | Rationale |
|---|---|---|
| Stable production | Daily | Sufficient for baseline reporting and periodic reviews |
| Frequently changing application fleet | Every few hours | Reduces staleness window |
| Ephemeral test machines | Per lifecycle or short schedule | Supports checks during machine lifetime |
| Very large fleets | Partitioned groups and staggered schedules | Reduces concurrent load and simplifies fault isolation |

These intervals are design guidelines, not mandatory AWS defaults. Test at small scale before rolling out fleet-wide.

### Checking the Association

After creating the association, monitor its status and last execution. Example:

~~~bash
aws ssm list-associations \
  --association-filter-list "key=AssociationName,value=collect-production-inventory"
~~~

Then use **DescribeAssociationExecutions** and **DescribeAssociationExecutionTargets** to inspect executions per association. An association's existence does not guarantee every node succeeded; check per-target execution status and the latest data capture timestamp.

## 5. Querying and Reconciling Inventory Data

You can inspect Inventory in the Systems Manager console or query it programmatically via APIs. Two useful APIs are:

- **GetInventorySchema:** returns Inventory types and queryable attributes.
- **GetInventory:** queries Inventory across multiple managed nodes using filters or aggregations.

Example listing nodes that have the `AmazonCloudWatchAgent` application:

~~~bash
aws ssm get-inventory \
  --filters "Key=AWS:Application.Name,Values=AmazonCloudWatchAgent,Type=Equal"
~~~

Example filtering nodes by platform name:

~~~bash
aws ssm get-inventory \
  --filters "Key=AWS:InstanceInformation.PlatformName,Values=Amazon Linux,Type=Equal"
~~~

Attribute names must match the inventory type schema and actual collected values. If a query returns empty results, check the schema, node type, association schedule, and exact software name in the collected data before concluding the fleet lacks that software.

To view applications on a specific managed node:

~~~bash
aws ssm list-inventory-entries \
  --instance-id "i-0123456789abcdef0" \
  --type-name "AWS:Application"
~~~

To inspect the application schema:

~~~bash
aws ssm get-inventory-schema \
  --type-name "AWS:Application"
~~~

### Finding Nodes Missing Standard Software

Suppose the baseline requires every node with `Application=orders` to run Amazon CloudWatch Agent. You can follow this workflow:

1. Query the list of managed nodes in the Orders fleet.
2. Query Inventory for `AmazonCloudWatchAgent` within the same scope.
3. Reconcile the two sets by instance ID.
4. Categorize nodes into missing agent, wrong agent version, and stale/missing inventory data.
5. Use Distributor/Run Command or State Manager to remediate.
6. Re-collect Inventory and confirm versions post-deployment.

When writing reconciliation scripts, distinguish three cases: **software absent**, **no Inventory record**, and **node no longer Online**. A missing record does not prove software is absent; the association may not have run yet, the node may be disconnected, or the collector may not recognize the software.

## 6. Adding Custom Inventory for Organizational Metadata

Standard Inventory does not know every internal business attribute. An application may need metadata such as service owner, application tier, release code, business unit, runtime, or support end date. You can add custom data using a custom inventory type prefixed with **Custom:**.

Example pushing internal application metadata to a managed node:

~~~bash
aws ssm put-inventory \
  --instance-id "i-0123456789abcdef0" \
  --items '[
    {
      "TypeName": "Custom:ApplicationOwnership",
      "SchemaVersion": "1.0",
      "CaptureTime": "2026-11-20T00:00:00Z",
      "Content": [
        {
          "Application": "orders",
          "OwnerTeam": "commerce-platform",
          "Release": "2026.11.3",
          "Tier": "critical"
        }
      ]
    }
  ]'
~~~

This example illustrates the payload structure; replace the instance ID, timestamp, and content with your organization's real data. Keep type names and schemas stable so teams can query them reliably over time. When changing structure, increment the schema version and maintain backward compatibility during transitions.

Custom inventory can be pushed via the `PutInventory` API or collected by scripts/automated tasks on nodes. Control who can write custom inventory, validate data sources, and avoid storing secrets, tokens, or unnecessary personal data. Node-reported metadata should be treated as asserted data requiring verification; never rely on a self-reported field as sole proof for critical security decisions.

## 7. Distributor: Packaging and Distributing Software

AWS Systems Manager Distributor is the package management capability in Systems Manager. Administrators can use AWS-provided packages or build custom packages to distribute software, agents, and operational tools to managed nodes.

A Distributor package typically defines:

- Package name and version.
- Supported operating systems, architectures, or platforms.
- Installation payload and supporting files.
- Install and uninstall scripts.
- Parameters or prerequisites needed during installation.
- Manifest metadata and package structure in Distributor-supported format.

Examples of software managed this way include Amazon CloudWatch Agent, security agents, backup tools, or internal utilities. Verify that the package supports the exact OS and architecture of the fleet before deployment.

### Designing Internal Packages

For internally packaged software, maintain source artifacts with version, checksum, download source, license, and approver records. Install scripts should be idempotent, log enough detail for troubleshooting, and return proper exit codes. Uninstall scripts must handle cases where the package is absent or already upgraded, and avoid deleting application data outside scope.

A package release workflow should include:

1. Verify artifact source and integrity.
2. Test on each supported operating system and architecture.
3. Verify install/uninstall scripts and required permissions.
4. Create a new version in Distributor.
5. Test installation on a canary group.
6. Expand in batches after monitoring for errors.
7. Record the approved version and rollback plan.

### Package Versions and Lifecycle

Do not rely solely on the `latest` label in production. When a new package version is published, nodes may receive different versions at different times depending on schedules and connectivity. For critical systems, pin tested versions, roll out new versions in waves, and retain the previous version for rollback.

## 8. Installing Software with Run Command

Run Command fits intentional, on-demand actions across one or more managed nodes. For Distributor packages, the **AWS-ConfigureAWSPackage** document can install or uninstall packages.

Example installing Amazon CloudWatch Agent on nodes tagged `Application=orders`:

~~~bash
aws ssm send-command \
  --document-name "AWS-ConfigureAWSPackage" \
  --targets "Key=tag:Application,Values=orders" \
  --parameters '{"action":["Install"],"name":["AmazonCloudWatchAgent"],"version":["latest"]}' \
  --comment "Install CloudWatch Agent on Orders fleet"
~~~

This example demonstrates a quick rollout using `latest`. In production, replace it with a specific tested and approved version. Pinning versions keeps outcomes reproducible and simplifies investigation when nodes behave differently.

Run Command returns a command ID. You can check aggregate status and per-node status:

~~~bash
aws ssm list-command-invocations \
  --command-id "COMMAND_ID" \
  --details
~~~

Command success must be verified on every node. A command sent to 100 nodes can succeed across most of the fleet while failing on a few nodes due to disconnections, missing permissions, incompatible packages, or full disks.

To uninstall a package:

~~~bash
aws ssm send-command \
  --document-name "AWS-ConfigureAWSPackage" \
  --targets "Key=tag:Application,Values=orders" \
  --parameters '{"action":["Uninstall"],"name":["AmazonCloudWatchAgent"]}' \
  --comment "Remove CloudWatch Agent from Orders fleet"
~~~

Before uninstalling an agent in production, assess the impact on logging, monitoring, security, or backups. Have a replacement or recovery plan ready if the software is operationally mandatory.

## 9. State Manager: Maintaining Desired Software State

Run Command executes once on demand. State Manager uses associations to define the document, parameters, targets, and schedule. Once scheduled, Systems Manager continues enforcing the configuration on target nodes, including new nodes matching the tag when the association is evaluated.

Example creating an association to maintain CloudWatch Agent on the Orders fleet:

~~~bash
aws ssm create-association \
  --name "AWS-ConfigureAWSPackage" \
  --association-name "ensure-orders-cloudwatch-agent" \
  --targets "Key=tag:Application,Values=orders" \
  --parameters '{"action":["Install"],"name":["AmazonCloudWatchAgent"],"version":["latest"]}' \
  --schedule-expression "rate(1 day)"
~~~

This association illustrates the package enforcement pattern. In production, replace `latest` with a pinned version and update the association only after a new version is approved. For safe rollouts, partition the fleet by tags or canary groups, monitor results, and then expand scope.

State Manager associations can be used to:

- Install or uninstall packages.
- Maintain agent configuration.
- Run periodic verification or configuration scripts.
- Enforce an operational baseline across a group of nodes.

### Associations and Compliance

State Manager records association execution status and can provide related compliance status. Administrators should monitor failed associations, nodes not receiving commands, overdue executions, or nodes missing compliance data.

An association in the `Success` state only indicates the document ran successfully under its reporting logic. It does not prove the entire application is healthy or that the package has no vulnerabilities. Combine Inventory version checks, application health checks, logs, metrics, and post-deployment testing.

## 10. Combining Inventory, Distributor, and State Manager

A complete software management workflow can be structured as a closed loop:

~~~mermaid
flowchart TD
    A[Managed nodes and SSM Agent] --> B[AWS-GatherSoftwareInventory]
    B --> C[Schema-based Inventory]
    C --> D[Query and compare against baseline]
    D --> E{Any nodes out of compliance?}
    E -->|No| F[Periodic monitoring]
    E -->|Yes| G[Select approved package and version]
    G --> H[Distributor]
    H --> I[Run Command or State Manager]
    I --> J[Verify execution and compliance]
    J --> K[Re-collect Inventory]
    K --> C
~~~

For example, the platform baseline requires every EC2 instance with `Application=orders` to run an approved version of Amazon CloudWatch Agent. The workflow:

1. Periodically collect Inventory across the Orders fleet.
2. Query `AWS:Application` records and extract agent versions.
3. Compare against the approved baseline version in the release process.
4. Classify nodes into compliant version, missing agent, wrong version, and stale/missing data.
5. Form a canary group to test a new version.
6. Deploy to the canary group using Distributor and State Manager.
7. Verify association status, command output, agent health, and CloudWatch telemetry.
8. Expand rollout in waves.
9. Re-collect Inventory to verify actual installed versions.
10. Retain change evidence, outcomes, and exception lists.

This workflow can be automated with EventBridge, Lambda, or internal pipelines if needed. When automating, scope the execution role tightly, prevent duplicate command loops, handle unknown states explicitly, and require approvals for high-risk production changes.

## 11. Centralizing Inventory Data Across Multi-Account and Multi-Region Fleets

In an AWS Organizations environment, data scattered across many accounts and Regions is hard to analyze if auditors must query every place separately. Systems Manager Resource Data Sync can synchronize Inventory to Amazon S3 to build a central data store.

Reference architecture:

~~~mermaid
flowchart LR
    A[Application Account A] --> D[Systems Manager Inventory]
    B[Application Account B] --> E[Systems Manager Inventory]
    C[Application Account C] --> F[Systems Manager Inventory]
    D --> G[Resource Data Sync]
    E --> G
    F --> G
    G --> H[Central Amazon S3]
    H --> I[Amazon Athena]
    I --> J[Amazon QuickSight or reporting]
~~~

Resource Data Sync can aggregate data across multiple Regions and supports AWS Organizations multi-account setups when properly configured. Administrators must enable trusted access and required organizational permissions, select source accounts/OUs and Regions, configure the S3 destination, and verify the synchronized data scope.

### Designing the Data Store

When sending Inventory to S3:

- Dedicate a bucket and prefix for Systems Manager data.
- Enable appropriate encryption and restrict read/write permissions by account or role.
- Set lifecycle and retention policies aligned with audit requirements.
- Control access to sensitive fields such as internal software names, file paths, or application metadata.
- Use Athena for querying and QuickSight or BI tools for trend reporting.
- Monitor sync latency and delivery failures to avoid reporting on stale data.

S3 Resource Data Sync is a centralized analytics copy; it does not replace the authoritative managed node state in Systems Manager. Preserve account, Region, instance ID, and capture timestamps to trace records back to their source.

For example, an organization can build reports on:

- Node counts by OS, account, Region, and environment.
- Percentage of nodes running a supported SSM Agent version.
- Number of nodes with monitoring or security agents installed.
- Runtime version distribution per application.
- List of nodes with stale Inventory data.
- Packages present in production that are absent from the baseline.

## 12. Security and Auditing in Software Management

Inventory can contain application names, versions, OS details, network configurations, file paths, and custom organizational metadata. These details help auditing, yet can also expose internal architecture. Govern this data under least privilege.

### Separation of Duties

A reference authorization model:

| Role | Responsibility | Permissions to Restrict |
|---|---|---|
| Fleet operator | View nodes and Inventory | Read access scoped to assigned accounts/Regions or groups |
| Software publisher | Build and publish packages | Manage packages and versions within assigned scope |
| Deployment operator | Send Run Commands or manage associations | Run only approved documents targeting authorized tags/instances |
| Auditor | Read data and evidence | No permission to install or modify packages |
| Central data analyst | Query centralized S3 data | Read-only access to authorized prefixes and datasets |

Do not use a single full-admin role for package authors, approvers, and production deployers. For critical changes, separating publishing from deployment strengthens governance.

### Securing Artifacts and Scripts

Installation packages can execute with elevated privileges on nodes. Distribute artifacts only from trusted sources, verify integrity, restrict package write permissions, and safeguard scripts. Never embed passwords, access keys, tokens, or private keys in payloads, command parameters, or logs.

### Activity Logging

CloudTrail records management API actions such as creating associations, sending commands, managing packages, and configuring sync. Run Command and State Manager provide execution status; output can be sent to Amazon S3 or CloudWatch Logs for detailed logs. On nodes, SSM Agent logs aid in troubleshooting execution or connectivity failures.

For auditing, retain:

- User or role that created and modified associations.
- Document, parameters, targets, and execution schedule.
- Package name, version, artifact source, and approver.
- Command ID, association execution ID, and per-node status.
- Pre- and post-rollout Inventory snapshots.
- Exceptions, risk acceptance decisions, and remediation evidence.

## 13. Cost and Performance at Scale

Systems Manager Inventory is more than enabling a single document. At fleet scale, execution frequency, data volume, attribute counts, and sync cadence all affect operations and associated costs.

Practical guidelines:

1. Collect only the data types you actually need. Do not enable broad file or registry inventory without a clear purpose.
2. Choose schedules based on change velocity and acceptable data staleness.
3. Partition the fleet into groups so thousands of nodes do not run documents simultaneously.
4. Use tags and OUs to control scope.
5. Monitor S3 storage, requests, Athena scan volume, and retention duration of synced data.
6. Capture enough logs for investigation without generating excessive unnecessary output.
7. Monitor association executions and command concurrency to catch backlogs.

Before increasing collection frequency, clarify which operational question requires fresher data. A weekly license or inventory report rarely needs runs every few minutes. Conversely, production agent enforcement may warrant shorter intervals and post-deployment verification.

## 14. Real-World Scenario: Standardizing Agents Across an Application Fleet

An enterprise has three accounts: Development, Staging, and Production. Each account hosts many EC2 instances across various applications. The platform team requires every production node to run SSM Agent and Amazon CloudWatch Agent at tested versions.

Operational design:

1. All EC2 instances use appropriate instance profiles and register as managed nodes.
2. Nodes carry `Application`, `Environment`, `OwnerTeam`, and `ManagedBy` tags.
3. An `AWS-GatherSoftwareInventory` association collects scheduled metadata for each fleet.
4. Resource Data Sync pushes Inventory to central S3 for multi-account reporting.
5. The platform team publishes the CloudWatch Agent version via Distributor.
6. A State Manager association installs the approved version on a canary group.
7. After verifying metrics, logs, and agent health, rollout proceeds to Staging and then Production.
8. Inventory is re-collected and reconciled against the baseline.
9. Failed nodes are categorized by root cause: offline, wrong permissions, package download failure, OS incompatibility, or installation error.
10. Auditors can trace changes via CloudTrail, association executions, command output, and Inventory snapshots.

Rollout diagram:

~~~mermaid
flowchart TD
    A[Publish new package version] --> B[Test on canary]
    B --> C{Health check passed?}
    C -->|No| D[Halt rollout and investigate]
    C -->|Yes| E[Deploy to Staging]
    E --> F{Staging passed?}
    F -->|No| D
    F -->|Yes| G[Roll out in waves to Production]
    G --> H[Collect post-rollout Inventory]
    H --> I[Compare against baseline and archive evidence]
~~~

This design shows operations teams what software is running, which versions are approved, and which nodes need attention. It also provides a clear fallback: if a new version causes issues, the team can halt rollout, revert to the prior version via the package workflow, and verify state after recovery.

## 15. Common Troubleshooting

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Node missing from Inventory | Node unregistered, SSM Agent stopped, missing IAM, or lost connectivity | Check Managed nodes, Agent status, instance profile, and endpoints |
| Association exists but no new data | Target mismatch, schedule not reached, document error, or agent offline | Inspect association executions and execution targets |
| Inventory missing a specific data type | Unsupported OS, collection parameter disabled, or software unrecognized | Check schema, platform, and document configuration |
| `GetInventory` returns empty | Wrong filter key/value, data not yet collected, or node in another Region | Check schema, capture time, and Region |
| Package install fails | Wrong version, OS/architecture mismatch, missing permissions, or artifact download failure | Inspect command invocation, output, and SSM Agent logs |
| Package installed successfully but absent in Inventory | Inventory has not re-run or collector does not recognize package | Trigger/wait for Inventory association and check package directly on OS |
| State Manager association keeps failing | Bad parameters, incompatible document, or insufficient role permissions | Check association status, execution output, and IAM |
| New node does not receive configuration | Wrong tags, node not Online, or association target excludes node | Check tags, managed node status, and association targets |
| S3 data not updating | Misconfigured Resource Data Sync, bucket policy, KMS, or Region | Check sync status, CloudTrail, bucket policy, and key policy |
| Rollout affects part of fleet | Differences in OS, architecture, permissions, or disk space across nodes | Group by platform, inspect per-invocation errors, halt wave rollout |

When investigating, always separate Inventory collection failures from software deployment failures. Both workflows use different documents, executions, and logs; success in one does not prove success in the other.

## 16. Misconceptions to Avoid

**Inventory installs software automatically.** Inventory only collects metadata. Use Distributor with Run Command or State Manager to deploy packages.

**No Inventory record means the software does not exist.** Data may not have been collected yet, the node may be disconnected, or the software may fall outside collector detection scope.

**Run Command enforces configuration permanently.** Run Command performs on-demand executions. Use State Manager associations when configuration must be maintained on a schedule.

**Association Success proves the application is healthy.** It only reflects document execution status under its reporting rules. Health checks, metrics, logs, and application testing are still required.

**Every piece of software appears in `AWS:Application`.** Inventory records only what the collector supports and can detect. Portable binaries or custom software may require custom inventory.

**The `latest` version fits all environments.** Production requires tested, explicitly pinned versions and a rollback plan.

**Having Resource Data Sync guarantees real-time data.** Sync depends on collection schedules, node reporting times, and S3 synchronization. Reports must display capture timestamps.

**Managed node Online guarantees every command will succeed.** IAM permissions, package download connectivity, OS compatibility, and disk space can still cause commands to fail.

## 17. Inventory and Software Management Implementation Checklist

- [ ] Managed nodes are registered and in the Online state.
- [ ] SSM Agent is installed, running steadily, and on a supported version.
- [ ] Instance profiles or hybrid activations have least-privilege permissions.
- [ ] Nodes can reach Systems Manager endpoints and package sources.
- [ ] Target tags are standardized and accurately reflect owner/application/environment.
- [ ] `AWS-GatherSoftwareInventory` association has appropriate targets and schedule.
- [ ] Required Inventory schemas and types have been verified.
- [ ] Queries distinguish nodes missing software from nodes missing data.
- [ ] Distributor packages have tested versions, artifact sources, and install/uninstall scripts.
- [ ] Run Command is tested on canary nodes before fleet-wide rollout.
- [ ] State Manager associations pin production versions and follow explicit schedules.
- [ ] Post-install verification uses Inventory, health checks, metrics, and logs.
- [ ] Resource Data Sync, S3, KMS, and Athena follow least privilege if centralizing data.
- [ ] CloudTrail and command/association outputs are retained sufficiently for auditing.
- [ ] Procedures exist for rollback, offline nodes, and exception handling.

## 18. Key Takeaways

Systems Manager Inventory provides visibility into software and configurations present on managed nodes. Distributor packages and distributes software; Run Command executes on-demand operations; State Manager maintains desired state via associations; Resource Data Sync centralizes Inventory data for multi-account and multi-Region fleet analysis.

To manage software reliably, start with managed node identity, SSM Agent, and network connectivity; collect Inventory on an appropriate schedule; define baselines with clear owners; deploy tested package versions; monitor per-node status; and re-collect data to confirm outcomes. Combining IAM, CloudTrail, execution logs, and a central data store helps organizations govern changes, maintain traceability, and keep AWS fleets secure.

## References

- [Working with Inventory in AWS Systems Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-inventory.html)
- [Configuring Inventory Collection](https://docs.aws.amazon.com/systems-manager/latest/userguide/inventory-collection.html)
- [Querying Inventory Data](https://docs.aws.amazon.com/systems-manager/latest/userguide/inventory-query.html)
- [Working with Custom Inventory](https://docs.aws.amazon.com/systems-manager/latest/userguide/inventory-custom.html)
- [Creating Resource Data Sync for Inventory](https://docs.aws.amazon.com/systems-manager/latest/userguide/inventory-create-resource-data-sync.html)
- [What is Distributor?](https://docs.aws.amazon.com/systems-manager/latest/userguide/distributor.html)
- [Creating a Distributor Package](https://docs.aws.amazon.com/systems-manager/latest/userguide/distributor-working-with-packages-create.html)
- [Installing or Updating Packages](https://docs.aws.amazon.com/systems-manager/latest/userguide/distributor-working-with-packages-deploy.html)
- [Working with Run Command](https://docs.aws.amazon.com/systems-manager/latest/userguide/run-command.html)
- [Working with State Manager Associations](https://docs.aws.amazon.com/systems-manager/latest/userguide/state-manager-associations.html)
- [Setting Up AWS Systems Manager for EC2 Instances](https://docs.aws.amazon.com/systems-manager/latest/userguide/setup-instance-permissions.html)
- [Setting Up AWS Systems Manager for Hybrid and Multicloud Environments](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-managedinstances.html)
