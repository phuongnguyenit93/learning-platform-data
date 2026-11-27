# Database Management and Centralized Database Management

As the number of databases grows, operational work is no longer just logging into each database to check CPU or storage capacity. Administrators need to know which databases are experiencing issues, whether monitoring data is still being collected, who is permitted to investigate, and which tasks can be performed across multiple databases.

**OCI Database Management** provides a unified console for monitoring, performance management, diagnostics, and administration of supported targets. This lesson focuses on **Diagnostics & Management for Oracle Database**, placed in the context of Oracle Cloud Infrastructure tenancy, compartments, IAM, VCN, secrets, and cost control. Refer to the [Database Management documentation page](https://docs.oracle.com/en-us/iaas/database-management/home.htm).

After this lesson, learners will be able to:

- Distinguish between an actual database, a Managed Database, a fleet, and a Database Group.
- Choose the appropriate connection path, credential type, and permissions when onboarding a database to management.
- Read the overview screen to prioritize investigations without confusing missing data with a stopped database.
- Practice enabling the service, verifying data collection, and organizing databases into groups.
- Identify the limitations of centralized management regarding regions, features, costs, and scope of impact.

## 1. Why Is Centralized Management Needed?

Suppose an organization has databases serving sales, reporting, and integration. They belong to multiple compartments, have different owners, and do not share a common maintenance schedule.

If managed only through manual connections, the following questions are difficult to answer consistently:

- Among critical databases, which ones have lost their monitoring connection?
- In which databases is storage growing, and is the growth rate abnormal compared to the baseline?
- Are alerts appearing individually or simultaneously across multiple systems?
- Can an on-call operator view the overview without being allowed to modify configurations?
- Across how many databases did an inspection task run successfully?

Centralized management establishes a common way to observe and coordinate. Each database continues running where it is deployed; registering or enabling monitoring does not move datafiles, merge schemas, or shift workloads to another database.

Example operational organization:

| Database | Illustrative Deployment Location | Criticality | Responsible Team |
| --- | --- | --- | --- |
| Sales CDB | Base Database Service | High | Transactional DBAs |
| Reporting DB | Another supported Oracle Database deployment | Medium | Analytics DBAs |
| Integration DB | System external to OCI | High | Integration DBAs |

The names in the table are hypothetical data. A useful fleet must include both technical information and operational metadata such as owner, environment, and criticality. Simply putting all databases on one screen is not enough to determine incident triage priority.

## 2. Concepts to Distinguish

### 2.1. Database, CDB, PDB, and Instance

| Concept | Operational Understanding |
| --- | --- |
| Oracle Database | The database system being monitored or administered |
| CDB | Container Database, containing the root and PDBs in a multitenant architecture |
| PDB | Pluggable Database, having its own data context and accounts in the multitenant model |
| Instance | Memory and background processes serving the database |
| RAC database | A database accessed concurrently by multiple instances in a RAC configuration |
| DB system or VM cluster | The infrastructure deployment resource of the corresponding database service |
| Managed Database | A database with Diagnostics & Management enabled |

Oracle uses the term **Managed Database** for a database that has Diagnostics & Management enabled. This term does not mean the database has been converted to an Autonomous Database or that all DBA work has been automated. See [Monitor and Manage a Specific Managed Database](https://docs.oracle.com/en-us/iaas/database-management/doc/monitor-manage-specific-managed-database.html).

Example relationship:

~~~text
Database deployment resource
└── CDB-style Oracle Database
    ├── CDB root
    ├── PDB SALES
    └── PDB REPORTING

Database Management
├── Management target corresponding to the enabled CDB
└── Enabled PDBs per support conditions
~~~

Do not count a CDB, PDBs, and RAC instances as independent copies of the same business unit. When reconciling counts or aggregating metrics, you must know which level you are viewing.

### 2.2. Fleet and Database Group

A **Fleet** is the set of databases currently being observed within the active scope and filters. A **Database Group** is an OCI resource used to group Managed Databases, including databases belonging to different compartments.

A Database Group is useful for viewing a set of databases with a shared operational purpose and executing group tasks when supported. See [Create and Use Database Groups](https://docs.oracle.com/en-us/iaas/database-management/doc/create-use-database-groups.html).

Distinguish the three organizational mechanisms:

| Mechanism | Primary Role | Example |
| --- | --- | --- |
| Compartment | Organizes resources and defines IAM policy scope | `ProductionDatabases` |
| Tag | Attaches metadata for classification, filtering, and governance | `Environment=Prod`, `Owner=SalesDBA` |
| Database Group | Groups Managed Databases for monitoring and group operations | `sales-production-fleet` |

Adding a database to a group does not change the database's compartment, create a replica, set up Data Guard, or automatically grant permissions to users viewing the group.

For a group containing databases across multiple compartments, permissions on the group and permissions on its members are two separate scopes to evaluate. A group created for general observation is also not necessarily suitable for running the same modification task.

### 2.3. Centralized Management Is Region-Scoped

When enabling an Oracle Cloud Database or External Database, you must select the correct region. Current Oracle documentation states that **cross-region monitoring and management of Oracle Databases is not supported** in this workflow.

Therefore, design your inventory and on-call procedures per region; do not assume that selecting the root compartment will create a global fleet. See [enable Oracle Cloud Databases](https://docs.oracle.com/en-us/iaas/database-management/doc/enable-database-management-oracle-cloud-databases.html) and [enable External Databases](https://docs.oracle.com/en-us/iaas/database-management/doc/enable-database-management-external-databases.html).

## 3. Which Databases Can Be Brought Under Management?

Diagnostics & Management covers Oracle Database deployment types such as:

- Oracle Cloud Databases on Base Database Service and supported Exadata forms.
- External Databases connected via External Database resources.
- Autonomous AI Databases according to their own workflows and conditions.
- Selected multicloud models announced as supported by Oracle.

Capabilities also depend on database type, version, edition, and feature. See [Diagnostics & Management for Oracle Databases](https://docs.oracle.com/en-us/iaas/database-management/doc/database-management-oracle-databases.html).

Database Management also includes sections for HeatWave and External MySQL. This lesson does not apply Oracle Database configurations to all database engines. Before deploying, verify the exact target in the [feature support matrix](https://docs.oracle.com/en-us/iaas/database-management/doc/database-management-feature-support-matrix.html).

### 3.1. Basic and Full Are Not Equivalent

For Oracle Cloud Databases on Base Database Service, ExaDB-D, and ExaDB-XS:

| Management Option | Intended Use | Things to Note |
| --- | --- | --- |
| Basic management | Basic set of metrics and certain published capabilities | Does not replace the full fleet feature set |
| Full management | Fleet monitoring and broader diagnostic and administrative capabilities | Incurs additional service costs; features still depend on edition and database type |

Basic incurs no additional service cost within the scope stated by Oracle. Full does not make every feature available on every edition; for example, Standard Edition has limitations on Performance Hub and other tools. ExaDB-C@C does not have a Basic option like the deployments listed above.

When the goal is practicing fleet and Database Group workflows, choose the option that supports those capabilities. See [About Management Options](https://docs.oracle.com/en-us/iaas/database-management/doc/enable-database-management-oracle-cloud-databases.html).

Do not use this table to make assumptions about pricing or feature entitlements for External Databases or Autonomous Databases. Those groups have separate enablement workflows and terms.

### 3.2. Related Services Address Different Needs

| Component | Appropriate Question |
| --- | --- |
| Database Management | Which database needs attention; how to monitor and investigate a specific database? |
| OCI Monitoring and Alarms | Which metric exceeded an alert condition and where should notifications be sent? |
| Ops Insights | How are long-term utilization, capacity, and performance trends changing? |
| Log Analytics or configured log pipeline | What events are recorded in database logs? |
| APM | Where is an application request slowing down across its cross-service journey? |
| Database service and backup/HA tools | How are backup, restore, patching, scaling, and data protection performed? |

Ops Insights complements Database Management with long-term trend and capacity analysis. The two services can be linked from the console, but each requires enablement and appropriate permissions; do not assume data from one service automatically appears in the other. Refer to [Accessing Related Services](https://docs.oracle.com/en-us/iaas/operations-insights/doc/accessing-related-services.html).

## 4. Connectivity and Data Collection Architecture

Two questions must be solved independently:

1. Is Database Management permitted to use the resources and credentials?
2. Can the collection component reach the database over the network?

Correct IAM permissions cannot fix an unreachable listener; an open network path cannot substitute for database privileges.

### 4.1. Private Endpoint Path

For the Base Database Service lab, Database Management uses a private endpoint in a VCN that can reach the database:

~~~mermaid
flowchart LR
    O["Operator"] --> IAM["OCI IAM"]
    IAM --> DBM["Database Management"]
    DBM --> PE["Private endpoint in VCN"]
    PE --> L["Database listener"]
    L --> DB["Oracle Database"]
    DBM -. "Read secret per permissions" .-> V["OCI Vault secret"]
~~~

The private endpoint represents Database Management inside the VCN and uses a private IP address. It does not have to be in the same subnet as the database, but it must be able to communicate with the database. For the Oracle Cloud Database private endpoint type discussed here, Oracle scopes the endpoint per VCN; do not assume a single endpoint can manage databases across all VCNs.

There are separate endpoint types for single-instance and RAC databases; choose the right one. See [Create a Database Management Private Endpoint for Oracle Cloud Databases](https://docs.oracle.com/en-us/iaas/database-management/doc/create-database-management-private-endpoint.html).

This private endpoint is distinct from private endpoints of other OCI services. Having a private IP address on a resource does not mean it already has appropriate connectivity for Database Management.

### 4.2. Management Agent Path

For an External Database, the typical workflow includes:

~~~text
Database outside OCI
   ↑ database connection from agent
Management Agent able to reach the database
   ↓ connection to OCI service as required
External Database connection + Database Management
~~~

You must register the database, establish a connection through Management Agent, and enable Database Management only after the database is connected. A resource handle only represents the external resource; it does not create a data copy in OCI. Refer to [External Database-related Prerequisite Tasks](https://docs.oracle.com/en-us/iaas/database-management/doc/external-database-related-prerequisite-tasks.html).

Some Exadata deployments also have a Management Agent option; do not generalize that all Oracle Cloud Databases use the same agent or private endpoint path. Check the [prerequisites by Oracle Cloud Database deployment](https://docs.oracle.com/en-us/iaas/database-management/doc/oracle-cloud-database-related-prerequisite-tasks.html).

### 4.3. Controlling Network Access by Actual Source and Destination

Record the following details:

| Detail | Meaning During Verification |
| --- | --- |
| Hostname or SCAN name | Name that the collection component must resolve |
| Listener port | Actual connection port |
| Service name | Database service to connect to, which may correspond to a CDB or PDB |
| Protocol | TCP or TCPS according to configuration |
| Source | IP/NSG of the private endpoint or agent host |
| Destination | Listener and related targets of the database configuration |

Open ingress on the database side and egress on the source side along the required connection path. Check NSGs/security lists, host firewalls, DNS, and the listener. For TCPS, there are also corresponding wallet, certificate, and authentication configurations. See [Enable Communication Between Database Management and Oracle Cloud Databases](https://docs.oracle.com/en-us/iaas/database-management/doc/enable-communication-between-database-management-oracle-cloud-databases.html).

Do not open the listener to `0.0.0.0/0` just to troubleshoot an enablement error. A successful connection from a laptop or bastion also does not prove the private endpoint has the same access path: traffic sources and rules may differ.

## 5. Layer-by-Layer Authorization

### 5.1. Four Independent Permission Layers

| Layer | What Does It Allow? | Common Errors |
| --- | --- | --- |
| Operator IAM | List resources, open fleet views, enable services, or create jobs | Database exists, but action buttons are missing |
| Service resource IAM | Read required secrets using a resource principal | User can see the secret, but the service cannot read it |
| Privileges inside Oracle Database | Log in, read monitoring metadata, or perform specific tasks | Connection succeeds, but a feature reports missing privileges |
| Network connectivity and TLS | Reach the listener and establish a session | Timeout, unrecognized service, invalid wallet |

All of the layers above must be configured properly for the corresponding task. An IAM account granted permissions to administer OCI resources does not automatically become `SYSDBA` inside an Oracle Database.

### 5.2. Separating Fleet Viewers from System Changers

Example starter policy for a read-only overview group in the lab compartment:

~~~text
Allow group Default/DbFleetReaders to read dbmgmt-managed-databases in compartment ObservabilityLab
Allow group Default/DbFleetReaders to read dbmgmt-managed-database-groups in compartment ObservabilityLab
Allow group Default/DbFleetReaders to read metrics in compartment ObservabilityLab
Allow group Default/DbFleetReaders to read alarms in compartment ObservabilityLab
~~~

Replace `Default`, the group name, and the compartment with actual values. If the group and databases are in different compartments, permissions must be granted at the corresponding resource scopes.

This is not a complete permission set for using all diagnostic tools. Some APIs require the `use` level or different credentials; the `use` level may also include mutating operations. When enabling additional capabilities, check APIs and permissions individually rather than elevating the entire reader group to `manage dbmgmt-family`. See [Policy Details for Database Management](https://docs.oracle.com/en-us/iaas/database-management/doc/policy-details-database-management.html).

Roles can be separated as follows:

- **Fleet readers**: monitor the overview, view alarms, and escalate incidents.
- **Onboarding administrators**: enable databases, prepare endpoints, and configure connections.
- **Diagnostic operators**: use authorized diagnostic tools.
- **Database administrators**: apply approved changes according to organizational procedures.

### 5.3. Onboarding Permissions Also Involve Other Services

A user enabling an Oracle Cloud Database needs Database Management permissions along with corresponding permissions on database, networking, and secret resources. Creating an endpoint may require operations on VNICs, subnets, and NSGs; viewing progress may require work request permissions.

In addition to user permissions, the Managed Database resource principal must be allowed to read the secret containing the password and wallet if used. Policies can be scoped to specific secrets. See [Permissions Required to Enable Diagnostics & Management for Oracle Cloud Databases](https://docs.oracle.com/en-us/iaas/database-management/doc/permissions-required-enable-database-management-oracle-cloud-databases.html).

If the Console offers to generate policies, review the statements before applying them to the tenancy: check the scope, principal, and which secrets are granted access. Do not assume that because a user can select a secret, every component in the pipeline already has permission to read it.

## 6. Credentials and Secrets in Centralized Management

### 6.1. Monitoring Accounts Differ from Administration Accounts

Oracle distinguishes preferred credentials for:

- **Basic monitoring**: metric collection and fleet observation.
- **Advanced diagnostics**: using appropriate diagnostic tools.
- **Administration**: executing administrative tasks.

The monitoring user needs the exact set of privileges required for monitoring; do not grant full DBA privileges by default to work around errors. Official privilege scripts and requirements are referenced in [Database User Privileges Required for Diagnostics & Management](https://docs.oracle.com/en-us/iaas/database-management/doc/database-user-privileges-required-database-management.html).

The database username, the container where the user resides, and the service used to connect must match the target being enabled. A local user inside a PDB does not automatically have monitoring roles for the CDB root.

### 6.2. Preferred, Named, and Session Credentials

| Credential | Role |
| --- | --- |
| Preferred credential | Default connection configuration by task type |
| Named credential | Resource storing user details and a password secret reference, centrally manageable |
| Session credential | Credential configured for the corresponding interactive session |

Credentials used for background collection and credentials used for an administrative task can differ. Choose credentials with privileges matching the task; do not set a high-privilege account as the default for everyone. See [Set and Use Credentials](https://docs.oracle.com/en-us/iaas/database-management/doc/use-credentials.html).

For named credentials, you must manage permissions to use the credential resource, permissions on the Managed Database, and permissions to access the required secret. A named credential is not a mechanism that automatically grants new privileges inside the database. Refer to [Create and Manage Named Credentials](https://docs.oracle.com/en-us/iaas/database-management/doc/create-manage-named-credentials.html).

### 6.3. Password Rotation Is a Pipeline Change

For database passwords stored in an OCI Vault secret, you must update the secret when changing the password. If only one side is updated, monitoring connections or jobs may fail.

Recommended operational workflow:

1. Identify the database user, secret, and connections using them.
2. Select a change window and rollover mechanism if supported by the version and configuration.
3. Update the password and secret version according to plan.
4. Test the monitoring connection and an appropriate task.
5. Monitor the timestamp of the most recent data collection after the change.

Store metadata such as the secret OCID and owner; never copy passwords into inventories, tickets, or shared scripts.

## 7. Lab: Onboarding a Base Database into a Managed Fleet

### 7.1. Practice Scope

The lab uses **an existing single-instance CDB Oracle Database Enterprise Edition 19c on Base Database Service** in a non-production environment. Select Full management to practice the corresponding fleet capabilities.

There is no need to create a new database for this lesson. If a suitable environment is not yet available, you can explore demo mode on the Overview page to understand the interface; demo data does not prove a real connection path works. The [Database Management Overview](https://docs.oracle.com/en-us/iaas/database-management/doc/access-database-management-overview.html) page describes the entry point and demo mode.

Illustrative preparation table:

| Item | Illustrative Value or Source |
| --- | --- |
| Region | Region containing the practice database |
| Database compartment | `ObservabilityLab` |
| Database | Existing test CDB |
| Management option | Full management |
| Connection mode | Private endpoint for single instance |
| Host, port, service | From actual listener and database service configuration |
| Monitoring user | User prepared by DBA with proper CDB privileges |
| Password secret | OCI Vault secret for the monitoring user |
| Group | `database-operations-lab` |
| Tags | `Environment=Lab` and the practice owner |

Names in the table are examples; do not use a display name string in place of an OCID when calling APIs.

### 7.2. Step 1: Verify Database Prerequisites

Verify that the database is running and identify the exact CDB to enable. Ask the DBA to confirm:

- The monitoring user is not locked and its password is not expired.
- The user exists in the appropriate container and has the documented privilege set.
- The service name is registered with the listener.
- The hostname and listener port match the intended connection path.
- The secret contains the corresponding password.

If a SQL client is available on an authorized machine, you can inspect the session context:

~~~sql
SELECT
    SYS_CONTEXT('USERENV', 'DB_NAME')      AS db_name,
    SYS_CONTEXT('USERENV', 'CON_NAME')     AS container_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user,
    SYSTIMESTAMP                         AS captured_at
FROM dual;
~~~

This is a session-identification query for the lab's 19c environment. It does not grant privileges and does not prove that the Database Management private endpoint has the same network reachability as the SQL client.

If the output shows you are in a PDB when the target is the CDB, fix the connection configuration before continuing. Do not run additional broad privilege-grant commands just because the wrong connection was chosen.

### 7.3. Step 2: Prepare the Secret and Usage Permissions

Create or select a Vault secret for the monitoring user. Place the secret in a compartment with clear ownership and verify permissions for:

1. The operator performing onboarding.
2. The Managed Database resource principal.
3. Other tasks expected to use the same credential, if any.

If using TCPS, also prepare a wallet secret in a supported format. TCP inside a private network does not automatically mean the connection is TLS-encrypted; the protocol choice must match the environment's security configuration.

Do not record the password in the preparation table. If the Console displays a warning about a missing resource principal policy, inspect the statement and scope before adding it.

### 7.4. Step 3: Create or Select a Private Endpoint

In the Console:

1. Select the region containing the database.
2. Open **Observability & Management → Database Management → Administration**.
3. Go to **Private Endpoints**.
4. Select an existing suitable single-instance endpoint, or create a new endpoint in the intended VCN/subnet.
5. Attach an NSG and configure the required access path to the listener.
6. Record the endpoint, VCN, subnet, and related addresses to support troubleshooting.

A single endpoint can serve multiple databases per support conditions; do not create a new endpoint for each database if an existing endpoint is already suitable. Also, check regional service limits before designing at large scale.

Proceed only when the endpoint and rules are ready. Saving a rule does not prove database connectivity succeeds.

### 7.5. Step 4: Enable Diagnostics & Management

From Database Management Administration or the Database Management section of the Base Database resource:

1. Select the correct database system, database home, and database.
2. For this lab, select the **CDB only** scope to avoid accidentally enabling all PDBs.
3. Verify the service name, protocol, and port.
4. Select the monitoring user, password secret, and wallet secret if using TCPS.
5. Select the appropriate private endpoint.
6. Select **Full management** and confirm the service selection and cost impact for your environment.
7. Submit the request, monitor the progress/work request, and inspect any errors if they occur.

The workflow from the Base Database resource is described in [Manage Database Management for Base Database Service Resources](https://docs.oracle.com/en/cloud/paas/base-database/dbm-manage/).

If the panel displays additional services such as Ops Insights, select only the services within the lab scope. Each service's enablement outcome must be verified individually; do not infer that all succeeded from a single general status.

### 7.6. Step 5: Verify Both Enablement and Collected Data

After enablement succeeds:

- Confirm the database appears in the Managed Databases list.
- Open its details and check the Monitoring status.
- Select a time range that includes the enablement timestamp.
- Verify that new data points appear for the right database and at the CDB level.
- Check the monitoring user/connection if errors appear.

There are two separate pieces of evidence:

~~~text
Enablement succeeded
    → the service configuration was accepted

New metrics collected
    → the pipeline is actively working at the time of observation
~~~

An Enabled label does not guarantee the pipeline will stay healthy after a password change, network rule change, or listener reconfiguration.

### 7.7. Step 6: Create a Database Group

Go to **Diagnostics & Management → Database Groups**:

1. Select the compartment that will hold the group resource.
2. Create `database-operations-lab`, describe its purpose, and add appropriate tags.
3. Open the group and select **Add managed database**.
4. Select the compartment containing the Managed Database and add the database you just enabled.
5. Open the group's **Fleet summary**.

Creating a group and adding members are described in [Create a Database Group](https://docs.oracle.com/en-us/iaas/database-management/doc/create-database-group.html) and [Add Managed Databases to a Database Group](https://docs.oracle.com/en-us/iaas/database-management/doc/add-managed-database-database-group.html).

A group with a single database is sufficient to verify the organizational pattern. If a second authorized non-production database is available, add it and verify the list; do not create a database solely to increase member count.

If members do not appear, check the region, compartment, management option, and permissions on each resource before modifying IAM policies.

### 7.8. Step 7: Cross-Check with OCI CLI

The Bash commands below are read operations. A configured OCI CLI profile and appropriate IAM permissions are required.

Example listing Managed Databases of deployment type VM with management option `ADVANCED`:

~~~bash
dbm_compartment_id='<compartment-ocid>'
dbm_region='<oci-region>'

oci database-management managed-database list \
  --compartment-id "$dbm_compartment_id" \
  --deployment-type VM \
  --management-option ADVANCED \
  --region "$dbm_region" \
  --all \
  --output json
~~~

`ADVANCED` is the CLI enum value for the advanced management scope; do not substitute the Console label string `Full management`. The command above uses specific filters and is not an inventory across all deployment types. See [CLI managed-database list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/database-management/managed-database/list.html).

Use the returned Managed Database OCID to inspect details:

~~~bash
dbm_database_id='<managed-database-ocid>'

oci database-management managed-database get \
  --managed-database-id "$dbm_database_id" \
  --region "$dbm_region" \
  --output json
~~~

Compare the output against the object in the Console. Never guess an OCID from a database name or swap OCID types across APIs. Refer to [CLI managed-database get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/database-management/managed-database/get.html).

You do not need to run mutating commands to prove that a database has been onboarded to centralized management.

## 8. Reading the Fleet to Prioritize Investigations

### 8.1. Navigating from Scope to an Individual Database

In **Diagnostics & Management**, select the compartment or Database Group, time range, and comparison period. Fleet summary provides inventory, monitoring status, resource usage, alarms, and the member list.

Filters such as deployment, database type, lifecycle state, tag, and CDB/PDB level help narrow the scope. From the member list, open the database to investigate. See [Monitor the Health of Your Oracle Database Fleet](https://docs.oracle.com/en-us/iaas/database-management/doc/monitor-health-your-oracle-database-fleet.html).

A useful reading order:

~~~text
Right scope?
→ Is the data fresh?
→ Which database is critical and showing anomalous signs?
→ When did the anomaly start?
→ Are other databases affected at the same time?
→ Open the specific database for deep inspection
~~~

Use the same time window when comparing databases. If one view looks at peak hours while another looks at a full-day average, conclusions about anomaly severity may be wrong.

### 8.2. Monitoring Status Is Not the Whole Service Status

Distinguish between:

1. Database **lifecycle/availability**.
2. Database Management **collection capability**.
3. Application **business-service availability**.

A database may continue serving applications while monitoring loses connectivity due to a password or network rule change. Conversely, normal CPU metrics do not prove that business transactions are succeeding.

When data gaps occur, inspect the Monitoring status timeline and associated errors if available. Mechanisms for missing-collection alerts and availability sources also vary by database type; do not apply one metric or alarm template to every deployment. See [Monitor Database Availability](https://docs.oracle.com/en-us/iaas/database-management/doc/monitor-database-availability.html).

### 8.3. Interpreting Metrics in Context

| Observation | Follow-Up Question |
| --- | --- |
| CPU increases | Did load increase, did CPU count change, or did SQL behavior change? |
| Average Active Sessions increases | Is time mostly spent on CPU or waiting on resources? |
| I/O increases | Is there more data, a changed access pattern, or high latency? |
| Storage usage increases | Is the growth rate normal and how much headroom remains? |
| One RAC instance differs | Is there load imbalance, a service change, or an instance issue? |
| Multiple databases anomalous together | Was there an infrastructure change or shared dependency issue? |

Average Active Sessions is the average number of active sessions, which differs from the total number of connected sessions. A connection pool with many idle connections does not mean the database has high processing load.

Do not directly sum CPU percentages of databases with different denominators. Also avoid double-counting metrics across CDB and PDB levels or between RAC totals and individual instances. Check units, scope, and aggregation before producing fleet reports.

### 8.4. Prioritizing by Impact and Data Reliability

Hypothetical figures during an on-call shift:

| Database | Collected Data | Symptom | First Action |
| --- | --- | --- | --- |
| Sales | Fresh | Activity rising and application reports slowness | Inspect the database during the incident window |
| Reporting | Fresh | CPU rising on scheduled batch window | Compare against baseline and batch duration target |
| Integration | No fresh data | Secret recently rotated | Check pipeline and credentials while verifying application status |

You should not necessarily investigate the database with the highest CPU first. Sales has direct user impact; Reporting may be running a known workload; Integration needs its true state verified because monitoring data is missing.

Initial conclusions should separate evidence from hypotheses:

~~~text
Evidence:
- Sales has data up to 10:20.
- The application recorded increased latency between 10:10–10:20.
- Database activity increased during the same window.

Hypothesis:
- A workload or dependency change increased processing time.

Next step:
- Open database details, compare activity and changes near that timestamp.
~~~

An overview screen helps pick a starting point; more data is needed before concluding root cause or running tuning changes.

## 9. Binding Alarms to the Right Database

OCI Monitoring Alarms evaluate configured metrics and conditions. For an alarm to appear linked inside Diagnostics & Management, Oracle requires identifying the database OCID via the `resourceId` dimension, along with necessary Monitoring permissions. See [Monitor Alarms for Managed Databases](https://docs.oracle.com/en-us/iaas/database-management/doc/monitor-alarms-managed-databases.html).

When designing an alarm, specify clearly:

- The database or resource scope being monitored.
- Namespace, metric, dimension, and aggregation.
- Threshold, trigger delay/duration, and severity.
- Recipients and first action.
- How maintenance windows and missing data are handled.

For example, an operational policy may require investigation when storage exceeds a threshold continuously rather than alerting on brief spikes. Realistic thresholds must account for headroom, growth rate, and the time needed to expand resources.

Do not guess a metric name from the UI and apply it to every database type. Choose metrics actually emitted in the environment and cross-check documentation per deployment.

An alarm does not replace a runbook. An alert saying only "database error" is hard to act on without the database OCID, region, timestamp, and instructions for distinguishing database failure from collection failure.

## 10. Centralized Jobs and Scope of Impact

### 10.1. What Is a Database Management Job?

Database Management supports asynchronous SQL jobs running on a single Managed Database or across databases in a Database Group. **Job definition**, **run**, and **execution** must be distinguished: a group run can have multiple executions, each associated with one database.

Jobs support multiple SQL types; Query jobs store results in Object Storage and require the corresponding permissions. See [Create and Monitor Jobs](https://docs.oracle.com/en-us/iaas/database-management/doc/create-monitor-jobs.html).

A Database Management job also differs from an Oracle Scheduler job inside the database. The Database Management interface can manage Scheduler jobs within supported scope, but those are different objects with a different lifecycle. See [Monitor and Manage Scheduler Jobs](https://docs.oracle.com/en-us/iaas/database-management/doc/monitor-manage-scheduler-jobs.html).

### 10.2. Optional Practice with a Query Job on One Database

Perform this section only when the environment has job creation permissions, appropriate credentials, and an Object Storage bucket for results. Keep the target to **a single non-production Managed Database**.

On the database page:

1. Open **Management → Jobs → Definitions → Create job**.
2. Choose create new, SQL type **Query**.
3. Choose run once immediately.
4. Select the credential and result bucket allowed for use.
5. Enter the following small query without a trailing semicolon:

~~~sql
SELECT
    SYS_CONTEXT('USERENV', 'DB_NAME') AS db_name,
    SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name,
    SYSTIMESTAMP AS checked_at
FROM dual
~~~

After submitting, open the run and execution to confirm the target, status, and result. Running a small query successfully proves the credential and execution path for that task; it does not prove that every administrative task has permissions or will succeed.

The result bucket requires appropriate access controls and retention policies. A query retrieving business data can create a copy of sensitive information outside the database, so both the query and its output must be controlled.

### 10.3. Group Monitoring and Group Execution Have Different Requirements

You can group databases that do not share credentials for observation. However, current job documentation states that when running a job for a Database Group:

- Named credentials cannot be used for group jobs.
- The provided credential must apply to all databases in the group.

Therefore, do not broaden privileges or synchronize passwords across multiple systems solely for the convenience of running a group job. If members have different access policies, use individual jobs or split execution groups appropriately.

A "submitted" status is not proof that all databases ran successfully. Inspect each execution and handle failed, timed-out, or incomplete targets individually.

### 10.4. Do Not Treat a Group Job as a Cross-Database Transaction

Suppose a mutating job runs on three databases:

~~~text
Database A: succeeded
Database B: failed
Database C: timed out, final state unknown
~~~

Do not assume A automatically rolls back because B failed. An orchestrated batch of tasks does not create an atomic transaction across databases.

Before automating mutating operations:

1. Lock down the target list and applicability conditions.
2. Pilot on a small scope.
3. Define how to verify results on each database.
4. Design idempotent retries or appropriate rollback/compensation.
5. Distinguish pre-execution failures from unknown states after a timeout.
6. Verify group membership before each run.

For recurring schedules, you must also manage credential changes, membership changes, and terminating schedules when no longer needed. A group created for monitoring is not implicitly a safe scope for DDL or DML.

## 11. Stable Fleet Operations and Cost Control

### 11.1. Maintaining a Usable Inventory

Fields that should be in the operational ledger:

| Field | Purpose |
| --- | --- |
| Database/Managed Database identifier | Avoid confusing objects with duplicate display names |
| Region and compartment | Locate the exact management scope |
| CDB/PDB, RAC/single instance, primary/standby | Understand observation level and role |
| Management option | Know the feature set and cost scope |
| Owner, environment, criticality | Prioritize handling and escalation |
| Endpoint or agent/connection | Trace the data collection path |
| Credential reference, secret OCID | Coordinate rotation without recording password values |
| Group membership | Know monitoring scope and group job exposure |
| Last verified date | Assess inventory freshness |

The inventory must be updated when a database moves compartments, changes connections, adds PDBs, switches roles, or is decommissioned. A stale list can cause jobs to hit the wrong targets or alarms to notify the wrong people.

### 11.2. Checking After Related Changes

Re-verify the pipeline after:

- Changing the monitoring password or secret version.
- Modifying NSGs, security lists, firewalls, DNS, or listeners.
- Changing service names or TCPS configuration.
- Restarting, patching, or upgrading an agent.
- Modifying CDB/PDB configuration or database role.
- Adding or removing databases from a group.

With Data Guard, check monitoring conditions by role and standby state in the relevant documentation. Do not assume that because a primary is monitored, every state after a switchover is supported by the same configuration.

If multiple databases lose metrics at the same time, inspect shared components such as the endpoint, agent, secret policy, or network before troubleshooting each database independently.

### 11.3. Tracking Costs by Actual Scope

Separate cost categories:

| Category | Examples to Track |
| --- | --- |
| Management service | Management option and additional enabled services |
| Database | Compute, storage, and database deployment choices |
| Supporting components | Agent host machines, secrets, result Object Storage, and related networking |
| Operations | Credential maintenance, alert handling, and fleet support |

Do not treat disabling a monitoring feature as stopping all database costs. Also do not calculate per-database costs solely from the number of rows in the fleet view, because CDB/PDB levels, deployment types, and service terms may differ.

Before expanding Full management or enabling extra services, check the current pricing page from Overview, resource scope, and actual tenancy usage reports. Use owner/environment tags to allocate and review unused resources.

### 11.4. Controlled Offboarding

When removing a database from management scope:

1. Identify groups, jobs, alarms, and credentials still referencing it.
2. Stop or adjust schedules for tasks that are no longer appropriate.
3. Remove the member from groups as needed.
4. Disable Diagnostics & Management according to the chosen scope.
5. Delete endpoints, secrets, or agents only when certain no other resources share them.
6. Update the inventory and retain required evidence.

Do not delete the actual database in place of stopping monitoring. For the lab, the existing database is an environment resource; clean up only components created separately that you are permitted to remove.

## 12. Common Errors in Centralized Management

| Symptom | First Check |
| --- | --- |
| Database not visible in Console | Region, compartment, filters, permissions, and enablement status |
| Database visible but missing fleet features | Management option, edition, and feature support matrix |
| Endpoint created but connection times out | Correct VCN/endpoint type, source rules, listener, and firewall |
| Secret selectable but enablement fails | User permissions differ from resource principal; check secret and policies |
| Connection rejected after rotation | New password, secret version, user lock/expiry, and change timestamp |
| Service name not recognized | Service registered with listener and matching CDB/PDB |
| TCPS fails | Port, wallet, certificates, and actual TLS configuration |
| Database Enabled but metrics stop updating | Monitoring status, credentials, network, and collection component |
| Fleet visible but a tool reports missing permissions | Corresponding IAM APIs and preferred/session credentials |
| Group missing members | Member compartments, permissions, and support prerequisites |
| Query job fails on output | Bucket, Object Storage permissions, and executing principal policy |
| Alarm exists in Monitoring but not on database | `resourceId` dimension, OCID, filters, and permissions |
| A group job succeeds only partially | Individual execution status, credentials, and target-specific traits |

Oracle provides error-by-error guidance for enablement in [Errors Encountered When Enabling Diagnostics & Management for Oracle Cloud Databases](https://docs.oracle.com/en-us/iaas/database-management/doc/errors-encountered-when-enabling-database-management-oracle-cloud-databases.html).

When logging an incident, record at minimum:

~~~text
Region:
Compartment:
Database or Managed Database identifier:
Timestamp and observation window:
Task being performed:
Enablement and monitoring status:
Work request / request identifier if available:
Error code and sanitized message:
Most recent change:
Evidence of whether the application is still serving:
~~~

This information helps separate three troubleshooting paths: access permissions, collection path, and database state. Never include passwords, wallet contents, or secret values in reports.

## 13. Expected Outcomes After Practice

The lab is complete when you can point to:

- Which actual database became a Managed Database, in which region and compartment.
- Which private endpoint or agent path serves data collection.
- Which user and secret reference are used, along with their corresponding permission scopes.
- Fresh data on the details screen and the database placed in the right Database Group.
- Cross-check output via CLI or Query job if the optional section was completed.
- How to distinguish missing data, performance issues, and application-serving issues.
- Which components incur cost or are shared and therefore must be checked before lab cleanup.

The value of centralized management lies in a clearly scoped fleet, trustworthy data, and controlled operations. From there, operators have a solid basis to select databases for deep investigation, expand monitoring, and automate appropriate tasks.
