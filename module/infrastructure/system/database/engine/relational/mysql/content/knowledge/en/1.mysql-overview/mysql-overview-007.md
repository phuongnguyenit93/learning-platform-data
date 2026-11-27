# Roles and Work Boundaries of Developers, DBAs, and Operations

MySQL typically sits between the application and the infrastructure: the application sends SQL statements, the database server processes data, and the underlying system provides CPU, memory, storage, and networking. Consequently, a small application change can affect MySQL's load; a server configuration change can affect application latency; and a database maintenance operation can impact both.

To keep systems safe and maintainable, a team should distinguish three roles: **developers**, responsible for how the application uses data; **database administrators (DBAs)**, responsible for the design, integrity, performance, and reliability of the database management system; and **operations**, responsible for keeping the platform stable, observable, recoverable, and scalable. Exact boundaries vary with organization size, but final accountability for every task must be clearly defined.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish the responsibilities of developers, DBAs, and operations across the lifecycle of a MySQL-backed application.
- Identify who prepares, reviews, executes, and verifies a data or infrastructure change.
- Collaborate on handling schema changes, slow queries, connection incidents, and data recovery.
- Design a handoff workflow with least-privilege permissions, audit trails, and post-change verification steps.

## 1. Developers: Ensuring the Application Uses Data Correctly

Developers understand business requirements and application execution flows. They decide which data needs to be read or written, when an operation must reside inside a transaction, and how the application responds when a query fails or data does not exist.

Responsibilities commonly belonging to developers:

- Translate business requirements into a data model and propose appropriate tables, columns, data types, relationships, primary keys, foreign keys, and constraints.
- Write SQL and data access code; use parameterization to prevent SQL injection; handle errors, timeouts, and deadlocks in a safely retryable way.
- Define transaction boundaries so a group of business operations executes consistently; avoid keeping transactions open too long or locking rows unnecessarily.
- Propose indexes based on actual queries, inspect execution plans with `EXPLAIN`, and measure before and after changes.
- Manage migrations alongside application versions, ensuring schema changes remain compatible with deployment rollouts and existing data.
- Monitor application-layer metrics such as query duration, connection counts, error rates, and query volume per feature.

Developers **are accountable for the business semantics and data access behavior of the application**. For instance, if an ordering transaction must update an order and deduct inventory together, the developer must identify which operations belong in the same transaction and how to handle failure in any step.

Developers should not arbitrarily use administrative accounts to modify production data or structures. Nor should they treat adding indexes as a default reflex: indexes consume storage and increase write work, so evidence from actual queries and data is required. For high-impact changes, developers prepare migrations and impact assessments for DBA and operations review.

## 2. DBAs: Ensuring the Database Is Correct, Fast, and Recoverable

A DBA (Database Administrator) has deep expertise in MySQL, storage structures, the query optimizer, locking mechanisms, transactions, replication, backup, and recovery. The DBA views the system from the perspective of data and the database server, bridging application requirements with MySQL's technical constraints.

Responsibilities commonly belonging to DBAs:

- Establish schema design standards: data types, naming conventions, keys, constraints, normalization, and storage strategies.
- Review table designs, migrations, indexes, and queries that carry risks regarding locking, disk space, runtime, or replication impact.
- Analyze execution plans, statistics, cardinality, indexes, and queries to diagnose performance issues; guide application teams toward evidence-based optimization.
- Manage MySQL-layer configuration, connection limits, resource controls, replication mechanisms, and high-availability features within their assigned scope.
- Design backup, recovery, and data retention policies; define RPO/RTO targets with system owners and test recovery capability periodically.
- Design database access privileges following the least-privilege principle; audit accounts, permissions, and sensitive activities.
- Plan MySQL version upgrades, major configuration changes, and incident response involving database integrity or performance.

DBAs **are accountable for the health and operational rules of MySQL**. For example, when a query begins scanning a large table in full, the DBA can inspect the execution plan, examine indexes and statistics, evaluate the impact of remediation options, and collaborate with developers to adjust the SQL query or data model.

DBAs do not unilaterally decide the business meaning of data on behalf of product teams and developers. A DBA can point out that a column needs a `NOT NULL` constraint or an operation needs a transaction, but the business owner must confirm whether that rule matches product requirements. Nor is a DBA by default responsible for the entire operating system, network, deployment platform, or application source code; those areas require coordination with operations and developers.

## 3. Operations: Ensuring the Platform Is Available and Recoverable

Operations (ops, system administrators, or SREs depending on the organization) manage the environment where MySQL and applications run. They focus on service availability, host resources, networking, storage, deployments, monitoring, and incident response processes.

Responsibilities commonly belonging to operations:

- Provision and manage physical hosts, VMs, containers, disks, networks, DNS, certificates, and required platform components.
- Manage environment configurations, secrets, system access permissions, OS patches, and controlled deployment pipelines.
- Monitor CPU, memory, disk capacity, I/O, networking, processes, host health, and availability alerts.
- Operate backup schedules, backup storage repositories, retention policies, and infrastructure-level recovery procedures according to the design agreed upon with the DBA.
- Prepare failover capacity, disaster recovery plans, on-call rotations, and runbooks for common scenarios.
- Collect system logs and metrics, coordinate incident response, record timelines, and verify platform stability after remediation.

Operations **are accountable for the platform and operational procedures**. For example, when a MySQL host runs out of disk space, operations inspects filesystems, volumes, logs, and infrastructure alerts; the DBA evaluates data files, binlogs, backup history, and impact on MySQL; developers check whether the application is generating abnormal data or queries causing sudden growth.

Operations staff should not guess data semantics and run `UPDATE` or `DELETE` statements to fix business bugs. Nor should they execute unreviewed SQL migrations. When emergency data intervention is necessary, there must be a clear owner accountable for the SQL content, affected record scope, approval, and result verification.

## 4. Responsibility Boundaries in Common Tasks

The three roles have overlapping areas. The table below outlines a reference division of responsibilities; organizations may combine roles or reassign executors, yet a single person or team must still hold final accountability for each decision.

| Task | Developer | DBA | Operations |
|---|---|---|---|
| Business rules and data semantics | Primary owner | Advises on integrity | Informed when operationally impacted |
| Schema design and migrations | Proposes, writes, and maintains alongside app code | Reviews data standards, keys, indexes, and MySQL impact | Prepares pipeline, change window, and platform readiness |
| SQL in the application | Primary owner for correctness and invocation | Advises and analyzes performance | Monitors resource impact in the runtime environment |
| Indexes and execution plans | Provides queries and workload context | Leads evaluation at the database layer | Provides CPU, I/O, and resource metrics |
| Database access privileges | Specifies application's minimal requirements | Designs and grants database privileges per policy | Manages secrets and infrastructure access permissions |
| Backup and recovery | Verifies data correctness after restore | Designs strategy and verifies consistency | Operates storage, schedules, and infrastructure restore workflow |
| Monitoring and alerting | Business metrics, app errors, and latency | Query, connection, lock, and replication metrics | Host, network, storage, and alert routing |
| MySQL upgrades | Tests application and driver compatibility | Evaluates database changes and upgrade plan | Prepares hosts, executes rollout, and platform fallback plan |
| Production incidents | Isolates application bugs and access patterns | Isolates data and MySQL issues | Coordinates incident response and checks platform |

Do not read this table as a rigid rule that only one role may touch a given task. For instance, developers may trigger migrations through an automated pipeline; a DBA may write diagnostic queries; operations may initiate a restore workflow. What matters is that execution permissions, approval authority, and verification accountability are defined upfront.

## 5. Collaboration Example: Adding a Column and Index for a New Feature

Suppose an application needs to store delivery status and frequently look up orders by `status` together with `created_at`. The team plans to add a `delivery_status` column and an index to serve the query.

1. **Developer clarifies requirements.** Defines valid statuses, default value, update rules, and which application versions coexist during rollout. The developer writes the migration, the query using the new column, and tests with sample data.
2. **DBA evaluates MySQL impact.** Reviews data type, `NULL` allowance, index, index column order relative to query predicates, table size, locking, and DDL execution time. The DBA checks the MySQL version and algorithm support for that specific schema change operation; never assume every DDL runs online or can be rolled back via a transaction.
3. **Operations prepares the environment.** Checks free disk space, current load, backup status, alerts, deployment permissions, and change window. If running on a topology with replicas or multiple nodes, the team confirms a rollout procedure suited to the active architecture.
4. **Controlled team rollout.** Runs the migration through the approved process, monitoring duration, locks, errors, and replica lag. Separates schema alteration from full feature activation if a multi-step deployment is needed.
5. **Joint verification.** Developers verify business flows and data; the DBA verifies schema, indexes, and execution plans; operations confirms stable resources and services. If issues arise, the team uses the prepared plan: toggle off the feature, roll forward with a fix, or restore according to plan.

With MySQL, exercise particular caution when planning rollbacks. Many DDL operations trigger an implicit commit; atomic DDL capabilities also depend on version and operation type. Therefore, you cannot assume wrapping `ALTER TABLE` inside a transaction and running `ROLLBACK` will undo the change. A safe fallback plan must rely on the specific operation, MySQL version, data size, and tested recovery capabilities.

## 6. Collaboration Example: A Query Suddenly Becomes Slow

An order list page that previously responded quickly now takes several seconds. Do not immediately conclude that the database needs more CPU or that a developer wrote bad SQL. The team should assemble evidence systematically across three layers:

- **Developer** identifies when the slowdown started, recently deployed application versions, query parameters, call frequency, page size, and whether a feature began issuing more queries than before.
- **DBA** inspects the actual query, `EXPLAIN`, indexes, statistics, estimated rows, lock waits, long-running transactions, and connection state. When considering `EXPLAIN ANALYZE`, remember that it executes the query; assess load and choose an appropriate environment before running it on production.
- **Operations** checks CPU, memory, I/O, disk space, networking, container/VM limits, and infrastructure events coinciding with the timeframe.

After pinpointing the cause, the team agrees on a measurable change: fix pagination, reduce query calls, add or adjust an index, resolve lingering transactions, or address resource starvation. The proposer defines success criteria; the authorized role executes the change; all three roles verify impact at their respective layers.

## 7. Principles for Collaboration and Access Control

A sound division of duties typically follows these principles:

**One decision has one clear owner.** For business rules, the owner is typically the product team or assigned developer. For MySQL standards, the DBA leads. For platform and on-call schedules, operations leads. Other groups participate in reviews whenever a decision affects their domain.

**Separate application runtime privileges from schema-change privileges.** The application's runtime account should hold only the data privileges it genuinely needs, such as a scoped set of `SELECT`, `INSERT`, `UPDATE`, or `DELETE` restricted by schema and table. The migration account is a separate identity used inside controlled deployment workflows. Never grant broad administrative privileges to an application just to avoid permission errors.

**Production changes must leave an audit trail.** Migrations, operational commands, or data-fix operations must record purpose, scope, accountable owner, timestamp, outcome, and verification method. High-risk operations require approval and a second reviewer.

**Backups only have value when they can be restored.** The DBA defines data to protect, consistency requirements, and RPO/RTO targets; operations ensures backups are created, retained, and accessible; developers or business owners confirm the application functions properly after restoration. Conduct periodic restore drills rather than merely checking backup job status.

**Incidents are a shared coordination responsibility.** The person who spots an incident does not need to resolve every layer alone. They must provide timestamps, symptoms, recent changes, and blast radius; the incident coordinator aligns teams, maintains a unified communication channel, and records decisions.

## 8. Divisions of Duty That Commonly Cause Incidents

- Developers using high-privilege accounts to directly edit production data, leaving changes unreviewed or untracked.
- DBAs unilaterally altering data rules without confirming business requirements, producing a schema that is technically sound yet wrong for the product.
- Operations running an SQL file solely because of an urgent request without knowing its scope, lock impact, or verification method.
- The team assuming a successful backup means recovery works without ever testing a restore in an isolated environment.
- Each group monitoring only its own metrics, leaving nobody able to correlate application errors with MySQL queries and infrastructure health.
- Having no single accountable owner, resulting in missed changes or multiple groups assuming another group already checked.

## 9. Checklist for Handing Off a MySQL Change

Before modifying schemas, queries, privileges, or configurations in a critical environment, the team should be able to answer these questions:

- What is the business and system goal of the change? Who holds final accountability?
- Which tables, queries, services, and application versions are affected?
- Has the migration or statement been reviewed against production-scale data?
- Have impacts on locking, runtime, storage space, replication, and system load been evaluated?
- Are execution permissions scoped appropriately? Are the executor and outcome logged?
- Does the latest backup meet requirements, and has the recovery plan been verified?
- Are monitoring criteria, stop conditions, failure handling, and post-change verification steps in place?
- Do developers, DBAs, and operations clearly understand their duties and the coordination point of contact?

When these questions are answered clearly, teams can collaborate without dropping responsibilities. Developers ensure data is used properly by the application; DBAs ensure MySQL stores and serves data reliably; operations ensures the platform remains observable, maintainable, and recoverable. All three roles share responsibility for database service quality, with transparent authority and decision ownership.
