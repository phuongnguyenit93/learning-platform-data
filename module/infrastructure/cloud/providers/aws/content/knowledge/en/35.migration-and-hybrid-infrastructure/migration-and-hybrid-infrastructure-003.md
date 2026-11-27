# AWS Migration Hub and Migration Progress Tracking

Migrating systems to AWS is a multi-phase program: discovering existing infrastructure, understanding application dependencies, assessing costs, planning waves, executing migrations, testing, and cutting over traffic. An organization may use multiple tools for servers, databases, containers, and enterprise applications. If each team tracks work in a separate spreadsheet, managers struggle to see which applications are ready, which servers are actively replicating, which tasks have failed, and which migration wave is at risk of slipping.

AWS Migration Hub was designed to centralize migration status from multiple AWS and partner tools in one place. It links source resources to applications, surfaces status updates, and tracks progress at the server, database, and application levels. Migration Hub does not perform data replication or conversion itself; specialized tools such as AWS Application Migration Service (AWS MGN) and AWS Database Migration Service (AWS DMS) execute the technical work and report status back to the Hub.

**Service lifecycle note as of November 20, 2026:** AWS Migration Hub and AWS Application Discovery Service stopped accepting new customers on November 7, 2025. Existing customers can continue using ongoing projects to complete their migrations; AWS is not adding new features to Migration Hub. AWS Transform is the AWS-recommended replacement for new projects, providing expanded discovery, assessment, migration planning, wave execution, and progress tracking. This lesson explains Migration Hub so learners understand how existing projects are tracked, while presenting AWS Transform as the current workflow for new migration programs.

## Learning Objectives

After completing this lesson, you will be able to:

- Explain the role of AWS Migration Hub in a multi-tool migration program.
- Distinguish discovery, assessment, migration planning, execution, cutover, and post-migration validation.
- Understand the home Region and why Migration Hub data is centralized in a single Region.
- Interpret server inventory, application groupings, and migration updates.
- Distinguish application status from migration tool task status.
- Combine AWS MGN, AWS DMS, Migration Hub Orchestrator, and partner tools within one tracking plan.
- Use the Migration Hub API/CLI to integrate a custom migration tool.
- Track migration waves, replication, testing, cutover, SLAs, and open risks.
- Explain the transition path to AWS Transform for new projects.

## 1. What Problem Does AWS Migration Hub Solve?

AWS Migration Hub serves as a central hub for progress updates from connected migration tools. It gives teams a unified view of:

- Which servers and databases are being migrated.
- Which resources make up each application.
- Which tool is executing each migration task.
- What state each task is in and when it last reported an update.
- Which applications have not started, are in progress, or have completed.
- Which resources or updates have not yet been mapped accurately to an application.

Migration Hub is especially valuable when multiple teams work in parallel: the infrastructure team rehosting to EC2, the database team using DMS, the SAP team running specialized workflows, and application teams coordinating testing and cutover.

Migration Hub provides aggregation and tracking, while execution remains in dedicated tools:

| Need | Execution Tool | Role of Migration Hub |
|---|---|---|
| Rehost data center servers to EC2 | AWS Application Migration Service (MGN) | Receives server lifecycle/progress updates and groups servers by application. |
| Migrate or replicate databases | AWS Database Migration Service (DMS) | Aggregates migration task status and database resource updates. |
| Orchestrate multi-step workflows | Migration Hub Orchestrator (for existing customers) | Displays workflow progress and remaining steps. |
| Migrate using partner tools | Integrated migration tool | Receives migration updates sent by the tool to the Hub. |
| New migrations and wave planning | AWS Transform | Provides discovery, assessment, planning, execution, and progress reporting for new projects. |

Do not treat Migration Hub as a replacement for MGN or DMS. The Hub answers "where does the overall program stand?", whereas specialized tools answer "how is the technical job running and what action is needed next?".

## 2. Service Status and Path Selection

### 2.1. AWS Migration Hub for Existing Customers

AWS announced that Migration Hub stopped onboarding new customers on November 7, 2025. Existing customers can continue accessing historical data and completing ongoing projects. AWS continues maintaining stability and security updates, without adding new features.

AWS Application Discovery Service also closed new customer onboarding on the same date. Existing discovery projects can continue through completion. Accordingly, instructions for Discovery Agent, Agentless Collector, Migration Hub import, and Orchestrator in this lesson apply to existing customer environments that already have access to those services.

### 2.2. AWS Transform for New Projects

AWS Transform is the next-generation service recommended by AWS for new migration projects. It provides an agentic AI experience supporting discovery, assessment, migration wave planning, landing zone creation, network migration, server rehosting, and supported modernization workflows.

Key points to know:

- No separate data migration process from Migration Hub to AWS Transform is required. Existing Migration Hub projects run through completion; new projects can start directly in AWS Transform.
- AWS Transform can import inventory, analyze dependencies, group applications, generate move groups, and build migration waves.
- Assessment and migration planning can run independently after discovery or together within the same migration job.
- The November 6, 2026 update enables migration jobs to combine discovery, assessment, and wave planning in a single job.
- AWS Transform supports workspace summary reports covering job status, workflow steps, approvals, wave plans, network topology, rehost progress, and artifacts.

AWS Transform uses AI to analyze and propose work. Critical changes such as inventory confirmation, approvals, cutover, and production deployments still require human review by accountable owners under organizational governance.

### 2.3. Choosing a Path by Account Status

| Scenario | Recommended Path |
|---|---|
| Existing Migration Hub / Orchestrator project started before 2025-11-07 | Continue the existing project in Migration Hub until completion; contact AWS Support if assistance is needed. |
| Already using Application Discovery Service to complete discovery | Continue the existing project; use collected data to finalize planning within supported scope. |
| Starting a new migration program | Start with AWS Transform. |
| Rehosting servers with MGN or migrating databases with DMS | Use the appropriate specialized tool; integrate tracking into the migration management process chosen by the organization. |
| Orchestrating a legacy workflow created in Migration Hub Orchestrator | Continue the existing workflow under existing-customer access; use AWS Transform for new projects. |

## 3. Core Concepts in Migration Hub

Migration Hub centers on three core concepts:

1. **Application:** a logical group of one or more resources serving an application or business capability.
2. **Resource:** a source server, database, or resource identified by a migration tool.
3. **Update:** status/progress information sent by a migration tool to the Hub for a resource or migration task.

Other key concepts:

| Concept | Meaning |
|---|---|
| Home Region | Central Region storing Migration Hub discovery data and migration tracking data for an AWS account. |
| Migration tool | Tool executing migration and reporting status to the Hub, such as MGN, DMS, or a partner tool. |
| Progress update stream | Namespace identifying a migration tool; also serves as the authorization boundary for the tool's migration tasks. |
| Migration task | Task migrating a specific server, database, or resource. |
| Migration wave | Group of applications scheduled to migrate in the same batch; prominently used in AWS Transform. |
| Move group | Set of interdependent applications that must move together in wave planning. |
| Cutover | Point in time when production workloads transition from source to target environment. |

An application in Migration Hub is a logical grouping for tracking purposes. Creating an application in the Hub does not automatically provision AWS resources, modify DNS, or move data.

## 4. Home Region and Centralized Data

### 4.1. Why Is a Home Region Required?

Migration Hub requires selecting a home Region before performing discovery or migration tracking. Data is centralized in the home Region so teams have a single place to view inventory, application groupings, and migration updates, even when target resources are deployed in other Regions.

Key rules:

- Choose a Region supported by Migration Hub for the account.
- Select the home Region before installing data collectors or sending migration updates.
- View dashboards and application details in the home Region.
- Write APIs such as create, notify, associate, disassociate, import, and put must be called from the home Region.
- Read operations such as list and describe may be supported outside the home Region, but standardizing automation on the home Region prevents endpoint errors.
- Changing the home Region may require re-collecting data; data in the old home Region does not move automatically to the new Region.

AWS advises customers to contact AWS Support when a home Region change is required. Do not pick a Region out of habit or solely based on the workload's target Region; consider where migration data should reside and how coordination teams access it.

### 4.2. Checking the Home Region

Existing Migration Hub customers can check using AWS CLI:

~~~bash
aws migrationhub-config get-home-region
~~~

This invokes the `GetHomeRegion` API and returns the account's configured home Region. Per AWS documentation, call this API before other Application Discovery Service and Migration Hub APIs to determine which endpoint Region to use.

If the home Region is not configured, write operations can return `HomeRegionNotSetException`. Calling write APIs from another Region can return `InvalidInputException`.

## 5. Discovery and Inventory Collection

Discovery answers: what servers and databases does the organization operate, how are they configured, how are resources utilized, and what systems do they depend on?

For existing Application Discovery Service customers, three collection methods are common:

| Method | Deployment | Typical Data Collected |
|---|---|---|
| Agentless Collector | Deployed as an OVA VM appliance in VMware vCenter. | VM/host inventory, CPU/RAM/disk, utilization, database metadata, and inter-server network traffic. |
| Discovery Agent | Installed on individual physical servers or Linux/Windows VMs. | Configuration, time-series utilization, running processes, and TCP network connections. |
| File-based import | Imports inventory data from supported file formats. | Depends on fields in the file; suitable when CMDB or external inventory already exists. |

### 5.1. Agentless Collector

Agentless Collector fits VMware vCenter environments where the organization wants to minimize installing agents on individual servers. The collector runs as a VM in VMware and uses data collection modules.

Collected data types include:

- Hostname, IP, MAC, and VM metadata.
- CPU count, RAM, and disk capacity.
- Average/peak utilization.
- Database and analytics server metadata via respective modules.
- Inter-server network traffic as supported by the collector.

Agentless collection lacks the same granularity as agent-based discovery. If process-level inventory or per-host time-series network/process detail is needed, evaluate the capabilities of another collection method.

### 5.2. Discovery Agent

Discovery Agent is installed on individual physical servers or VMs. The agent runs with the system privileges needed to collect configuration, processes, and network connections. Data is transmitted securely over TLS to the home Region.

Discovery Agent can collect:

- OS, CPU, RAM, disk, and host configuration.
- Time-series utilization.
- Running processes.
- Inbound/outbound TCP connections.
- Information supporting inter-server dependency mapping.

Before deploying agents, verify OS support, installation permissions, network egress, proxies, and internal security policies. Never deploy agents broadly without server owner approval.

### 5.3. File Import and Partner Data

If the organization already maintains a CMDB, RVTools exports, or partner discovery inventory, file-based import or partner integrations can be used in existing Migration Hub environments. Standardize hostnames, IPs, MACs, FQDNs, and server identifiers to prevent duplicate records.

For new projects, AWS Transform provides discovery inventory import along with new collectors and analytical capabilities. Follow AWS Transform guidance rather than starting a new Application Discovery Service deployment.

### 5.4. Inventory Quality

A high-value inventory must include:

- Stable server IDs and normalized hostnames.
- Environment, application, owner, and business criticality.
- OS, CPU, RAM, storage, and utilization.
- IPs, subnets, network zones, and key connections.
- Database engine/version, size, throughput, and dependencies.
- Licensing, support lifecycle, and constraints.
- Collection timestamp and data completeness level.

Never use an inventory lacking utilization metrics to lock final instance sizes or a business case. Missing data should be logged as an assumption/risk with an owner assigned to close the gap.

## 6. Grouping Servers into Applications

Migration Hub allows grouping discovered servers into applications. An application may include a web tier, application tier, database, message broker, and components that must migrate in coordination.

Grouping should combine two types of relationships:

- **Technical dependencies:** an application calling a database, message queue, shared file system, authentication service, or another application.
- **Business/operational dependencies:** shared business capability, owner, maintenance window, data center, RTO/RPO, or testing workflow.

In existing Migration Hub, teams can open **Servers**, filter servers by metadata, select servers, and use **Group as application** to create a new application or add to an existing one. Tags can store application, owner, environment, or wave attributes.

Before saving a grouping, check:

1. Do the servers truly belong to the same application boundary?
2. Is the database or shared service used by multiple applications?
3. Are there synchronous dependencies or simultaneous cutover requirements?
4. Have owners and testers been identified?
5. Are any resources missing inventory or mis-mapped?

Do not group all servers in the same subnet into one application. A subnet is a network construct; application boundaries must reflect dependencies and business functions.

### 6.1. Verifying Migration Update Mappings

When a migration tool sends updates, Migration Hub attempts to map each update to a discovered server using attributes such as IP, MAC, FQDN, or VMware identifiers. Automatic mapping can misfire or fail to match a server.

If updates do not appear under an application:

- Open the **Updates** page and verify whether updates were received.
- Inspect the **Mapped servers** column.
- Confirm whether the update mapped to the correct server.
- If incorrect, use **Edit server mapping**.
- Return to **Servers** and verify the server is grouped into the right application.
- Refresh application details to view the updated status.

An update can appear on the **Updates** page yet remain absent from the application view if the server is ungrouped or mis-mapped.

## 7. Migration Planning and Migration Waves

A migration wave is a group of applications migrated together in one batch. Wave planning accounts for dependencies, criticality, testability, operations team capacity, downtime windows, and cutover conditions.

In AWS Transform, migration planning consists of four stages:

1. **Scope and analyze:** review inventory, determine in-scope servers, and analyze software/network dependencies.
2. **Group apps:** group servers into applications based on hostnames, network dependencies, business rules, or existing inventory.
3. **Generate move groups:** group interdependent applications, such as those sharing a database, queue, or business function.
4. **Build waves:** sequence move groups into waves by priority, size, user count, complexity, and timeline.

A move group is a set of interdependent applications that must migrate together. A wave may contain one or more move groups.

### 7.1. Dependency Classification

| Dependency Type | Example | Wave Impact |
|---|---|---|
| Hard/critical dependency | Application requires a database or shared service to start. | Usually must migrate in the same wave or use a well-defined connectivity bridge. |
| Soft dependency | Reporting system tolerates data delayed by a few minutes. | Can migrate in a separate wave if latency is acceptable. |
| Business dependency | Two apps support the same business workflow and share a maintenance window. | May require coordinated cutover even without direct network dependencies. |
| Operational dependency | Shared owner, team, data center, or change window. | Requires coordinating staffing and release schedules. |

### 7.2. Wave Sequencing Criteria

Use the following matrix during planning:

| Criterion | Question |
|---|---|
| Business criticality | If cutover fails, what is the revenue or customer impact? |
| Dependencies | Which applications/resources must move together? |
| Complexity | Are there heavy integrations, batch jobs, shared databases, or legacy protocols? |
| Data volume | How do data size and change rate affect replication duration? |
| RTO/RPO | How fast must the workload recover and how much data loss is tolerable? |
| Owner readiness | Are application, database, network, and security teams ready? |
| Testability | Are test data, test environments, and business acceptance criteria available? |
| Target readiness | Are the landing zone, networking, IAM, quotas, logging, and backups ready? |

Start with a small pilot wave with manageable dependencies. Pilot results refine runbooks, duration estimates, and checklists before scaling up.

## 8. Connecting Migration Tools to Migration Hub

Migration Hub receives status updates from migration tools. Before tracking, existing customers must connect/authorize each tool under **Tools** in the console or configure the appropriate IAM roles.

Common integrations:

- **AWS MGN:** rehosts servers and reports replication/test/cutover status.
- **AWS DMS:** full load, change data capture (CDC), task state, and table statistics.
- **Migration Hub Orchestrator:** template-driven workflows with orchestrated steps.
- **Partner migration tools:** report status via supported integrations/APIs.
- **Custom migration tools:** use the Migration Hub API to register tasks and push progress.

Connecting a tool is an authorization step. If a tool is unauthorized or lacks the required IAM role, the Hub will not receive updates even while migration jobs run in the tool's own console.

### 8.1. AWS Application Migration Service (MGN)

MGN is the primary tool for lift-and-shift/rehosting servers to Amazon EC2. MGN replicates block-level data from source servers to an AWS staging area, then launches test instances and cutover instances.

Common lifecycle states:

| Lifecycle State | Meaning |
|---|---|
| Not ready | Initial sync in progress; not yet ready to launch a test instance. |
| Ready for testing | Replication active; a test instance can be launched. |
| Test in progress | Test instance is launching or under validation. |
| Ready for cutover | Tested and ready for cutover. |
| Cutover in progress | Cutover instance is launching. |
| Cutover complete | Data cut over to the cutover instance. |
| Disconnected | Server disconnected from MGN. |

Read lifecycle status alongside replication health/lag, launch status, last test timestamp, and alerts. For example, **Ready for testing** does not mean the application passed UAT; it only means a test instance can be launched.

### 8.2. AWS Database Migration Service (DMS)

DMS supports full load, ongoing replication/CDC, and migration modes tailored to source/target engines. When monitoring, inspect concurrently:

- Task status: Running, Stopped, Failed, Error, or transitional states.
- Table state: Before load, Full load, Table completed, or Table error.
- Full load progress and completed table count.
- CDC latency and backlog during ongoing replication.
- CloudWatch metrics, task logs, and DMS events.

Do not rely solely on completion percentage. DMS estimates progress from table statistics; if source tables lack row count statistics, the task may stay `Running` while the percentage bar stays flat. Check rows loaded, table state, CDC latency, and logs instead.

For homogeneous data migrations, the console uses specific states such as `Load running`, `Load complete, replication ongoing`, `Replication ongoing`, `Stopped`, `Failed`, and `Maintenance`. These states belong to DMS; do not confuse them with Migration Hub's `ApplicationStatus`.

### 8.3. Migration Hub Orchestrator

Orchestrator lets existing Migration Hub customers create template-based workflows and track step groups and steps. Published templates include:

- Migrate SAP NetWeaver applications to AWS.
- Rehost applications on Amazon EC2 using MGN.
- Rehost SQL Server on Amazon EC2 using backup/restore.
- Replatform SQL Server to Amazon RDS.
- Replatform applications to Amazon ECS.
- Import virtual machine images to AWS.
- Custom templates derived from existing templates.

Some templates require an on-premises Orchestrator plugin to connect source and target environments. Workflows can include step groups, dependent steps, scripts executing on-premises or in AWS, and steps requiring manual user attention.

For new projects, use AWS Transform to plan and orchestrate migration workflows instead of starting new Migration Hub Orchestrator workflows.

## 9. Monitoring Progress in the Migration Hub Dashboard

The Migration Hub dashboard aggregates discovery and migration information. Teams can view counts of servers, applications, data collectors, and recently updated application statuses.

A standard inspection flow:

1. Open Migration Hub in the home Region.
2. Go to **Dashboard** and review **Discovery summary**.
3. Open **Most recently updated applications**.
4. Select the application to inspect.
5. Check the server list, migration tools, task updates, and per-resource status.
6. Open **Updates** to inspect status reports sent by migration tools.
7. Cross-check in the MGN or DMS console when deeper troubleshooting is needed.
8. Refresh application details after new updates arrive.

Migration Hub can take up to roughly 5 minutes to display the first update after receiving it from a migration tool. Subsequent updates depend on the reporting cadence of each tool.

### 9.1. Application Status

Migration Hub uses three primary statuses for applications:

| Application Status | Meaning |
|---|---|
| `NOT_STARTED` | Migration has not started. |
| `IN_PROGRESS` | One or more migration tasks are underway. |
| `COMPLETED` | Application has been marked complete per the migration process. |

When the first migration task for a server in an application starts, the application typically transitions automatically to `IN_PROGRESS`. If the status does not update automatically, users can update it manually after verification.

When application details show migration tasks are finished, teams must complete testing and verification before marking the application `COMPLETED`. This status is an application-level rollup; it does not replace verifying that every server and database operates properly.

### 9.2. Migration Task Status

The Migration Hub API uses the following task statuses:

| Task Status | Meaning |
|---|---|
| `NOT_STARTED` | Task is registered but has not begun. |
| `IN_PROGRESS` | Work is actively running. |
| `FAILED` | Task failed and requires investigation. |
| `COMPLETED` | Tool reports the task finished. |

Tasks can include `ProgressPercent` from 0 to 100 and `StatusDetail` explaining the active step or error. `ProgressPercent` is supplied by the migration tool; not every tool can calculate an exact percentage.

### 9.3. Interpreting Progress Properly

Never average completion percentages across all servers to report program-wide progress. A small web VM and a multi-terabyte database do not carry equal work or risk.

Report across multiple layers:

- **Portfolio:** applications in scope, completed, in progress, not started, and blocked.
- **Wave:** move groups/applications/servers passing each gate.
- **Resource:** lifecycle state, replication health, task state, last update, and blockers.
- **Business:** users, transactions, or business capabilities migrated and accepted by owners.
- **Quality:** test pass rate, post-cutover defects, rollbacks, and incidents.
- **Schedule:** planned dates, forecast dates, overdue tasks, and unready dependencies.

## 10. Integrating Custom Migration Tools via API

Existing Migration Hub customers can integrate custom tools using the Migration Hub API. Basic workflow:

1. Identify the home Region and target API calls to that Region.
2. Create a `ProgressUpdateStream` for the migration tool.
3. Register each migration task with `ImportMigrationTask`.
4. Map tasks to source resources via `PutResourceAttributes` or association APIs.
5. Push status updates using `NotifyMigrationTaskState`.
6. Send new updates whenever state or progress changes.
7. Use `DescribeMigrationTask` / `ListMigrationTaskUpdates` to verify recorded data.

`ProgressUpdateStream` acts as the namespace and permission boundary for a migration tool. `MigrationTaskName` identifies the task within the stream; never embed personal data or secrets in this name.

### 10.1. Creating a Stream and Registering a Task

Example using AWS CLI v2 in the home Region:

~~~bash
aws mgh create-progress-update-stream \
  --progress-update-stream-name custom-migrator \
  --region ap-southeast-1

aws mgh import-migration-task \
  --progress-update-stream custom-migrator \
  --migration-task-name app01-web-01 \
  --region ap-southeast-1
~~~

In this example, `ap-southeast-1` is illustrative only. Substitute your account's configured home Region. Register tasks early—even before replication starts—so trackers have visibility into planned tasks.

### 10.2. Sending Progress Updates

~~~bash
aws mgh notify-migration-task-state \
  --progress-update-stream custom-migrator \
  --migration-task-name app01-web-01 \
  --task "Status=IN_PROGRESS,StatusDetail='Copying source data',ProgressPercent=72" \
  --update-date-time 2026-11-20T05:00:00Z \
  --next-update-seconds 300 \
  --region ap-southeast-1
~~~

Key fields:

- `Status`: `NOT_STARTED`, `IN_PROGRESS`, `FAILED`, or `COMPLETED`.
- `ProgressPercent`: integer from 0 to 100, if the tool can estimate progress.
- `StatusDetail`: description of the active step or failure reason.
- `UpdateDateTime`: timestamp when the tool collected the status.
- `NextUpdateSeconds`: seconds the Hub should wait for the next update before marking the task stale.

Tools must retry transient API/throttling errors and send updates upon state changes. If `NextUpdateSeconds` is shorter than the actual reporting interval, tasks may be flagged stale even while migrations run normally.

### 10.3. Updating Application Status

For applications created in Application Discovery Service, `NotifyApplicationState` updates status to `NOT_STARTED`, `IN_PROGRESS`, or `COMPLETED`. The Application ID is the application's `configurationId` in Application Discovery Service.

Never set an application to `COMPLETED` solely because migration tasks returned `COMPLETED`. Verification and business owner acceptance are required first.

### 10.4. IAM for Custom Migration Tools

Grant only required actions, for example:

- `mgh:CreateProgressUpdateStream`
- `mgh:ImportMigrationTask`
- `mgh:NotifyMigrationTaskState`
- `mgh:PutResourceAttributes`
- `mgh:DescribeMigrationTask`
- `mgh:ListMigrationTasks`
- `mgh:GetHomeRegion`

Scope resources to the ARN of the progress update stream and migration task where supported by the API. Never grant `mgh:*` or `AdministratorAccess` to a migration integration role just to push progress updates.

## 11. AWS Transform: Tracking New Migration Projects

AWS Transform uses workspaces and migration jobs to manage one or more projects. A workspace is a logical container holding jobs and artifacts; the workspace Region determines where discovery data and recommendations are stored. The target Region can differ from the workspace Region in supported configurations.

### 11.1. Migration Job Types

AWS Transform supports scoped job types:

- End-to-end migration: discovery, migration planning, connecting target accounts, landing zone, network migration, and server migration.
- Discovery and migration planning: ingesting inventory and building wave plans prior to execution.
- Migration assessment: evaluating cost/TCO and business case before locking scope.
- Jobs can be customized to add or skip steps as needed.

As of the November 6, 2026 update, discovery, assessment, and migration planning can execute within the same migration job. Discovery provides the required input; assessment, planning, or both can then run in the desired order and rerun whenever inventory changes.

### 11.2. Discovery, Assessment, and Planning

Typical workflow:

1. Create a migration job in the workspace.
2. Upload server/application inventory data.
3. Review the discovery summary and data quality warnings.
4. Refine scope and exclude out-of-scope servers.
5. Run assessment to estimate AWS costs, TCO, and business case.
6. Analyze dependencies and group applications.
7. Generate move groups and migration waves.
8. Review, adjust, and approve the wave plan.

Assessments can evaluate compute, database, storage, analytics, and business value. Never treat TCO output as a final quote; validate assumptions around licensing, support, networking, Regions, pricing models, and usage.

### 11.3. Wave Execution

For server rehosting with MGN, AWS Transform guides these steps:

1. Setup migration wave: configure target accounts, verify permissions, and apply tagging.
2. Validate inventory: confirm server configurations, instance recommendations, and network assignments.
3. Deploy replication agents.
4. Continuously replicate block-level data.
5. Launch test instances and validate workloads.
6. Cut over and verify cutover outcomes.

Servers within the same wave do not need to be in identical states at all times. Servers passing tests can proceed to cutover while failed servers are held back for retesting, provided dependencies and business rules allow.

### 11.4. Tracking Server and Wave Status

AWS Transform provides a wave status table showing lifecycle state, replication status, and next steps. Common lifecycle states:

| Status | Meaning |
|---|---|
| Not ready | Initial sync has not completed. |
| Ready for testing | Replication active; test/cutover instance can be launched. |
| Test in progress | Test instance is launching. |
| Ready for cutover | Server tested and ready for cutover. |
| Cutover in progress | Cutover instance is launching. |
| Cutover complete | Data cut over to the cutover instance. |
| Disconnected | Server disconnected from MGN. |

You can query the agent about server, wave, or workflow step status. However, the status table is an orchestration aid; you must still verify health, test outcomes, dependencies, and business acceptance.

### 11.5. Workspace Progress Reports

AWS Transform can generate a PDF workspace summary report compiling:

- Job status and current workflow step.
- User actions and approvals.
- Wave planning details.
- Network migration topology.
- Landing zone configuration.
- Rehost progress.
- Containerization decisions.
- Artifacts generated during migration.

This report is valuable for steering committees and stakeholders reviewing overall progress. Pair it with a RAID log (Risks, Assumptions, Issues, Dependencies), timeline, and program KPIs.

Important limitations per current documentation:

- One migration job targets a single target Region.
- Multiple target accounts in the same Region can be migrated if AWS Organizations prerequisites are met.
- Migrating to multiple target Regions requires separate projects/jobs per Region.
- Stopping a migration job and asking the agent to restart it may restart the job from the beginning and lose prior progress; previously generated artifacts remain. Therefore, never stop/restart a job as routine troubleshooting.

## 12. Measuring Progress and Managing the Migration Portfolio

A dashboard is only useful when metrics map to objectives and owners. Build a portfolio dashboard covering these metric groups:

| Group | Metrics | Meaning |
|---|---|---|
| Inventory | Total servers, databases, apps in scope | Establishes the program denominator. |
| Discovery coverage | Percentage of resources with owner, utilization, dependency data | Assesses plan quality. |
| Application readiness | Apps with dependency maps, test plans, target designs | Measures pre-migration preparedness. |
| Wave progress | Planned, in progress, blocked, completed | Tracks batch progress. |
| Replication | Replication health, lag, transfer throughput | Detects cutover schedule risks. |
| Testing | Tests launched, passed, failed, retested | Measures pre-cutover quality. |
| Cutover | Planned dates, actual dates, successes, rollbacks | Measures cutover execution. |
| Data migration | Full load, CDC latency, table errors, row counts | Evaluates data completeness. |
| Business validation | UAT pass rate, transaction success, owner sign-off | Confirms business readiness. |
| Schedule | On-time wave rate, overdue tasks, dependency delays | Manages timelines and escalations. |
| Quality | Post-cutover incidents, defects, rollbacks, data reconciliation | Measures migration quality. |
| Cost | Cost per server/app/wave, temporary dual-run spend | Controls budget. |

### 12.1. Avoid Relying on a Single Percentage

A program might show 80% of servers replicating while only 30% of applications have passed testing. A database may show full load complete while CDC latency remains too high for cutover. Therefore, separate:

- Technical progress: tool tasks and lifecycle states.
- Application readiness: dependencies, tests, and owner sign-off.
- Wave readiness: target environment, network, IAM, backups, and rollback.
- Business completion: traffic switched, data reconciled, SLOs met, and owner acceptance.

### 12.2. Setting Gates for Each Wave

A wave should advance to the next stage only upon clearing explicit gates:

| Gate | Example Criteria |
|---|---|
| Discovery complete | Inventory complete; owners and dependencies confirmed. |
| Plan approved | Target architecture, network, security, cost, and cutover plans approved. |
| Replication healthy | MGN replication healthy or DMS tasks/CDC meet thresholds. |
| Test passed | Functional, integration, performance, and security tests pass. |
| Cutover approved | Change record, rollback, communications, and owner sign-offs ready. |
| Migration validated | Traffic/data switched, monitoring stable, reconciliation complete. |
| Source decommission approved | Retention, backups, audits, and business owners authorize source shutdown. |

## 13. Cutover and Completion Validation

Cutover is high-risk because it alters production user paths and live data writes. A migration task reporting completion does not mean the overall application is ready to close.

Cutover checklist:

1. Verify replication health and confirm lag is within thresholds.
2. Verify database consistency, row counts, schemas, sequences, and CDC state.
3. Confirm test instances passed functional, integration, security, and performance tests.
4. Freeze or control changes on source per the cutover plan.
5. Execute final sync and stop writes following tool procedures.
6. Switch DNS, load balancers, routes, or client endpoints.
7. Run smoke tests and business validation.
8. Monitor error rates, latency, transaction success, queue backlogs, and data integrity.
9. Maintain the rollback window per policy.
10. Finalize cutover and decommission source only after owner approval.

For CDC databases, confirm no unapplied change backlog remains or defined cutover criteria are met. For rehosted servers, verify application services, scheduled jobs, licensing, monitoring agents, backups, domain joins, and network dependencies.

## 14. Security, Access Control, and Governance

Migrations often expand access to both source and target data and infrastructure. Design governance upfront:

- Use AWS Organizations and account separation to isolate workloads, migration tooling, and log archives.
- Use separate IAM roles for discovery, replication, target provisioning, and cutover.
- Enforce least-privilege permissions per tool and workflow.
- Protect agent/plugin credentials and rotate them upon project completion.
- Use TLS for data in transit; apply encryption at rest per policy.
- Restrict read access to inventory since it exposes hostnames, IPs, processes, database metadata, and network topology.
- Log IAM, resource, network, and cutover changes with CloudTrail.
- Tag resources with application, wave, owner, environment, data classification, and migration status.
- Set retention policies for discovery data, logs, reports, and artifacts.
- Define approvers for production cutover, data retention, and source decommissioning.

Never share inventory or topology with partners beyond contractual scope. Discovery data in particular can reveal internal systems and inter-server connectivity.

## 15. Monitoring and Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| No migration updates visible in Hub | Home Region not set or viewing wrong Region. | Verify home Region and open the correct console Region. |
| Tool running but Hub receives no status | Tool unauthorized or missing IAM role. | Check **Migrate → Tools**, role, and required `mgh` permissions. |
| Update appears on Updates page but not in app | Server ungrouped or mis-mapped. | Check **Mapped servers**, edit mapping, and group server into the app. |
| Initial update not yet visible | Ingest/display latency. | Wait up to ~5 minutes, then verify tool authorization and API calls. |
| Task marked stale | No update received within `NextUpdateSeconds`. | Check scheduler, retries, clock/time source, and update interval. |
| API returns `HomeRegionNotSetException` | Home Region not configured. | Configure home Region before calling write APIs. |
| API returns `InvalidInputException` | Calling write API outside home Region or invalid payload. | Verify endpoint, Region, and request schema. |
| MGN does not reach `Ready for testing` | Initial sync incomplete or replication issue. | Check replication health, network, agent, staging resources, and logs. |
| DMS progress bar stuck | Missing table statistics or task/table error. | Check table state, rows loaded, task logs, and CloudWatch metrics. |
| DMS full load done but cannot cut over | CDC still catching up or latency above threshold. | Check CDC latency, source write rate, and cutover criteria. |
| Application status unchanged | Task updates unmapped or app state requires manual update. | Check **Updates**, resource groupings, and application state. |
| AWS Transform wave blocked | Dependencies, target permissions, inventory, or network unready. | Review job/workflow steps, worklogs, approvals, and next-step recommendations. |

### 15.1. Systematic Investigation Order

When a dashboard does not reflect expected progress, check from the outside in:

1. Correct account, home Region/workspace Region, and target Region.
2. Whether the migration tool or AWS Transform job is actively running.
3. Whether the tool is authorized with a valid IAM role.
4. Whether tasks/resources are registered and mapped accurately.
5. Whether the application grouping is complete.
6. Whether last update, `NextUpdateSeconds`, and clocks are valid.
7. Tool-specific logs, CloudWatch metrics, DMS task logs, or MGN replication health.
8. Network connectivity, endpoints, DNS, proxies, security groups, and service quotas.
9. Whether workflow approvals or dependencies are waiting on an owner.

Never assume a migration has stalled solely from a stale dashboard. Cross-check timestamps and status directly inside the executing migration tool.

## 16. Practical Scenario: Migrating an Order System

An enterprise operates an on-premises order system consisting of:

- Two web servers.
- Three application servers.
- One SQL Server database.
- One message broker.
- One file server storing order documents.
- One batch worker running overnight.

Dependencies: web calls application; application calls database and message broker; batch worker reads data from the database and file server.

### 16.1. Discovery and Scope

For existing Migration Hub customers, use existing discovery data from Agentless Collector/Discovery Agent or imports. Check hostnames, CPU/RAM, disks, utilization, network connections, and database metadata.

For new projects, create an AWS Transform migration job, upload inventory, and review the discovery summary and data quality warnings.

### 16.2. Grouping and Wave Plan

Group the servers into the `order-management` application. The database and message broker are hard dependencies; the batch worker belongs to the same business function and requires coordinated cutover. The file server is evaluated separately for storage protocol and access patterns.

Two waves can be planned:

- **Wave 1 – Pilot:** one web server and one application server in a test environment to validate networking, deployment, and monitoring.
- **Wave 2 – Production application:** web/app servers, database, message broker, file server, and batch worker following the approved dependency/cutover plan.

If the database must start migrating earlier to allow time for CDC, replication can start ahead of time while cutting over together with the application once criteria are met. Wave plans must reflect both replication start times and production cutover dates.

### 16.3. Execution and Tracking

- MGN rehosts servers; monitor lifecycle states and replication health.
- DMS performs full load/CDC for SQL Server; monitor table states, CDC latency, and errors.
- Existing Migration Hub receives updates, maps servers, and displays application progress.
- AWS Transform uses the wave status table and workflow steps for new projects.

Each task has an owner and gate. Never advance a wave to cutover merely because all tasks report 100% progress; require testing, data reconciliation, and business sign-off.

### 16.4. Cutover and Validation

During the maintenance window:

1. Freeze data changes per plan.
2. Wait for DMS CDC latency to reach threshold.
3. Perform final data sync and verify row counts/checksums or business reconciliation.
4. Launch/cut over servers in dependency order.
5. Switch traffic and endpoints.
6. Run order placement, payment, inventory, batch, and notification tests.
7. Monitor SLOs and incidents during the rollback window.
8. Record application migration completed after business owner acceptance.

## 17. Common Misconceptions

1. **Migration Hub migrates servers/databases itself.** The Hub centralizes tracking; MGN, DMS, or other tools execute the migration.
2. **Migration Hub still accepts new customers.** It stopped accepting new customers on November 7, 2025; AWS Transform is the path for new projects.
3. **Application Discovery Service still allows new registrations.** ADS also stopped accepting new customers on November 7, 2025.
4. **Home Region is the target Region.** Home Region centralizes tracking data; the target Region can be different.
5. **Having inventory is enough to build waves.** You also need dependencies, owners, business criticality, RTO/RPO, and cutover windows.
6. **One server equals one application.** Applications typically span multiple interdependent resources.
7. **100% progress means cutover is complete.** You still need testing, final sync, traffic switching, and validation.
8. **DMS progress percent is always exact.** Estimates depend on table statistics and do not replace task/table states.
9. **Ready for testing means tests have passed.** It only indicates a test instance can be launched.
10. **Application Completed is fully automated.** Verification is required and application state may need to be updated manually per process.
11. **Every update maps automatically to the right server.** Check **Mapped servers** and correct mappings when needed.
12. **Write APIs can be called from any Region.** Migration Hub write APIs must execute in the home Region.
13. **No visible updates means the tool stopped.** It could stem from authorization, mapping, Region, or ingest delay.
14. **Waves are just servers grouped by count.** Waves must reflect dependencies and business/operational constraints.
15. **Cutover complete means source systems can be deleted immediately.** Validation, rollback windows, backups/retention, and decommission approvals are required first.

## 18. Self-Check Questions

**1. What role does AWS Migration Hub play in a migration program?**

It centralizes status from multiple migration tools, links tasks/resources to applications, and provides a unified progress view.

**2. Does Migration Hub replicate server data?**

No. MGN, DMS, or specialized tools perform the migration; the Hub receives status updates.

**3. When did Migration Hub stop accepting new customers?**

November 7, 2025. AWS Transform is the recommended replacement for new projects.

**4. What is the purpose of the home Region?**

It centrally stores an account's discovery data and migration tracking data.

**5. Why group servers into applications?**

To track progress by business workload and represent resources that must coordinate during migration.

**6. What is the difference between an application and a migration task?**

An application is a logical group of resources; a migration task is the job migrating a specific resource managed by a tool.

**7. Which tools can send status to Migration Hub?**

For example, MGN, DMS, and integrated partner/custom migration tools.

**8. What does `ProgressUpdateStream` do?**

It identifies a migration tool and serves as the namespace and access boundary for its migration tasks.

**9. What does `NextUpdateSeconds` mean?**

The interval Migration Hub waits for the next update before flagging a task as stale.

**10. Why might the DMS progress bar stop advancing?**

Estimates can lack data when source tables lack row statistics; inspect task status, table state, and rows loaded instead.

**11. How does a move group differ from a migration wave?**

A move group contains interdependent applications that must move together; a wave contains one or more move groups.

**12. What does `Ready for cutover` mean?**

The server has been tested and is ready for cutover; change approvals and cutover validation are still required.

**13. What can an AWS Transform workspace summary report compile?**

Job status, workflow steps, approvals, wave plans, network topology, landing zone configuration, rehost progress, and artifacts.

**14. Can an application be marked Completed as soon as migration tasks finish?**

No. Testing, data verification, and business owner acceptance are required first.

**15. Why track both technical and business metrics?**

Technical tasks may finish while the application still fails, data is inconsistent, or users cannot complete business workflows.

## 19. Migration Operations Checklist

- [ ] Confirmed whether the project is an existing Migration Hub workload or a new project requiring AWS Transform.
- [ ] Selected the proper account, home Region/workspace Region, and target Region.
- [ ] Inventory includes servers, databases, utilization, owners, and dependencies.
- [ ] Data quality warnings are resolved or logged as risks.
- [ ] Application groupings reflect dependencies and business boundaries.
- [ ] Move groups and migration waves have clear owners, timelines, and dependencies.
- [ ] MGN/DMS/partner tools are authorized with appropriate IAM roles.
- [ ] Migration tasks are mapped accurately to source resources and applications.
- [ ] Dashboard tracks last updates, stale tasks, replication health, and blockers.
- [ ] DMS monitors full-load/table state/CDC metrics and logs.
- [ ] MGN monitors lifecycle states, replication health, test status, and cutover readiness.
- [ ] Test plans, data reconciliation, and rollback plans are in place.
- [ ] Cutover has a maintenance window, approvers, and communications plan.
- [ ] Applications are marked Completed only after validation.
- [ ] Portfolio, wave status, SLA, and cost tracking dashboards are active.
- [ ] Audit trails capture IAM, network, resource, and cutover changes.
- [ ] Retention policies cover inventory, logs, reports, and artifacts.
- [ ] Source decommissioning occurs only after approvals and backup/retention checks.

## References

- [AWS Migration Hub – Service overview](https://docs.aws.amazon.com/migrationhub/latest/ug/what-is-migrationhub.html)
- [AWS Migration Hub availability change](https://docs.aws.amazon.com/migrationhub-orchestrator/latest/userguide/migrationhub-availability-change.html)
- [AWS Application Discovery Service availability change](https://docs.aws.amazon.com/application-discovery/latest/userguide/application-discovery-service-availability-change.html)
- [What is AWS Application Discovery Service?](https://docs.aws.amazon.com/application-discovery/latest/userguide/what-is-appdiscovery.html)
- [Application Discovery Service Agentless Collector](https://docs.aws.amazon.com/application-discovery/latest/userguide/agentless-collector.html)
- [AWS Application Discovery Agent](https://docs.aws.amazon.com/application-discovery/latest/userguide/discovery-agent.html)
- [View and explore discovered data](https://docs.aws.amazon.com/application-discovery/latest/userguide/view-and-explore.html)
- [Choosing an AWS Migration Hub home Region](https://docs.aws.amazon.com/migrationhub/latest/ug/select-home-region.html)
- [Managing the AWS Migration Hub home Region](https://docs.aws.amazon.com/migrationhub/latest/ug/home-region.html)
- [AWS Migration Hub API reference](https://docs.aws.amazon.com/migrationhub/latest/ug/api-reference.html)
- [Tracking migration updates in AWS Migration Hub](https://docs.aws.amazon.com/migrationhub/latest/ug/updates-tracking-wt.html)
- [Track the status of your migrations](https://docs.aws.amazon.com/migrationhub/latest/ug/migrate-wt-track.html)
- [Grouping servers in the Migration Hub console](https://docs.aws.amazon.com/application-discovery/latest/userguide/applications.html)
- [NotifyMigrationTaskState API](https://docs.aws.amazon.com/migrationhub/latest/ug/API_NotifyMigrationTaskState.html)
- [Migration Hub troubleshooting](https://docs.aws.amazon.com/migrationhub/latest/ug/troubleshooting.html)
- [Migration Hub Orchestrator templates](https://docs.aws.amazon.com/migrationhub-orchestrator/latest/userguide/templates.html)
- [What is AWS Transform?](https://docs.aws.amazon.com/transform/latest/userguide/)
- [AWS Transform discovery, assessment, and planning](https://docs.aws.amazon.com/transform/latest/userguide/transform-migrations-discover-assess-plan.html)
- [AWS Transform migration planning](https://docs.aws.amazon.com/transform/latest/userguide/transform-vmware-review-groupings-and-waves.html)
- [AWS Transform migration wave execution](https://docs.aws.amazon.com/transform/latest/userguide/transform-vmware-ms-wave-execution.html)
- [AWS Transform server lifecycle states](https://docs.aws.amazon.com/transform/latest/userguide/transform-vmware-ms-server-lifecycle.html)
- [AWS Transform migration jobs and workspace reports](https://docs.aws.amazon.com/transform/latest/userguide/vmware-jobs.html)
- [Monitoring AWS DMS tasks](https://docs.aws.amazon.com/dms/latest/userguide/CHAP_Monitoring.html)
- [AWS CLI create-progress-update-stream](https://docs.aws.amazon.com/cli/latest/reference/mgh/create-progress-update-stream.html)
- [AWS CLI import-migration-task](https://docs.aws.amazon.com/cli/latest/reference/mgh/import-migration-task.html)
- [AWS CLI notify-migration-task-state](https://docs.aws.amazon.com/cli/latest/reference/mgh/notify-migration-task-state.html)
