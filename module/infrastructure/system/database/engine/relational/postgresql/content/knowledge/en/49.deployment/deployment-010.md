# Automating Infrastructure, Configuration, and PostgreSQL Handover Documentation

A PostgreSQL deployment may run well right after installation yet still be difficult to operate if infrastructure was built manually, configuration is scattered across machines, and no documentation exists for the team taking over. When scaling out, changing versions, recovering from incidents, or transitioning operations teams, minor differences between environments can lead to downtime and hard-to-reproduce errors.

Deployment automation must manage three layers simultaneously:

1. **Infrastructure:** servers/VMs/containers, networking, storage, firewalls, DNS, load balancers, backup targets, and monitoring.
2. **PostgreSQL configuration and service:** packages, data directory, parameters, authentication, TLS, roles, extensions, replication, backup agents, and service lifecycle.
3. **Operations and handover:** source of truth, change history, runbooks, recovery procedures, ownership, access model, monitoring expectations, and known limitations.

Infrastructure as Code (IaC) describes infrastructure resources in reviewable, version-controlled code. Configuration management brings the operating system and PostgreSQL to the desired state. Deployment automation coordinates steps in order and verifies outcomes. Handover documentation helps the receiving team understand the system, operate it, and recover it during incidents.

This lesson, **"Automating Infrastructure, Configuration, and PostgreSQL Handover Documentation"**, belongs to the **Deployment** chapter of the **Database Engine Relational PostgreSQL** module. It covers designing safe automation workflows, managing configuration with control, deploying PostgreSQL consistently across environments, and preparing practical operational documentation.

> **Principle:** every significant change requires a source of truth, an owner, a deployment method, a verification method, and a recovery plan. Good automation produces a reproducible, observable state rather than merely running a sequence of commands that exit cleanly.

---

## 1. Why Automate Deployment?

Manual PostgreSQL installation often starts simply: install packages, create a data directory, edit configuration, create users, and start the service. When managing multiple servers, staging/production environments, or HA, manual steps easily create drift.

Common risks:

- Parameters differ across nodes.
- One host is missing an extension package.
- Firewall or TLS configurations are inconsistent.
- The backup agent was never enabled.
- A replication slot or monitoring target is missed.
- An operator skips a step in a runbook.
- No one knows who edited a configuration file.
- Recovery procedures exist only in one person's memory.

Automation reduces repetitive steps, makes dependencies explicit, and provides post-deployment evidence.

## 2. Distinguishing Provisioning, Configuration Management, and Deployment

| Activity | Goal | Examples |
|---|---|---|
| Provisioning | Create required resources | VMs, subnets, disks, firewalls |
| Configuration management | Bring hosts to desired state | OS packages, users, sysctl, files |
| Database deployment | Install and configure PostgreSQL | initdb, roles, extensions, parameters |
| Application deployment | Connect applications to the database | connection pools, secret references |
| Operations automation | Perform recurring tasks | backups, monitoring, failover drills |

These activities are related, yet should not be lumped into one monolithic script without boundaries or intermediate states.

## 3. Infrastructure as Code

IaC describes infrastructure using configuration stored in version control. Common tools include Terraform, OpenTofu, cloud-native templates, and corresponding provisioning platforms.

Example VM resource described in HCL:

~~~hcl
resource "example_compute_instance" "postgres" {
  name         = "postgres-primary"
  machine_type = "database-optimized"
  zone         = var.database_zone
  tags         = ["postgres", "private"]
}
~~~

This is an illustrative example; actual resource types and arguments depend on the provider.

IaC enables change review, consistent environments, and dependency management across networking, storage, compute, and security policies.

## 4. Source of Truth

Choose where the desired state lives:

- IaC repository for cloud resources.
- Configuration management repository for OS/PostgreSQL config.
- Migration repository for schema/database objects.
- Secret manager for credentials.
- Monitoring configuration repository for alerts/dashboards.
- Documentation repository for runbooks and architecture.

Do not maintain multiple independent copies of configuration without defining which one is authoritative.

Documentation must specify repositories, branches/tags, owners, and approval workflows.

## 5. Separating Environments

Dev, test, staging, and production usually differ in sizing, availability, retention, and security requirements.

Use one automation structure parameterized by environment variables:

~~~text
inventory/
  dev/
  staging/
  production/
config/
  common/
  postgresql/
  monitoring/
environments/
  dev.tfvars
  staging.tfvars
  production.tfvars
~~~

Do not copy a full production file and edit it manually for staging. Use shared modules and environment-specific inputs to reduce drift.

## 6. Designing Modules and Reusable Components

Separate components with clear responsibilities:

- Network module.
- Compute module.
- Storage module.
- PostgreSQL installation role.
- PostgreSQL configuration role.
- Database bootstrap role.
- Backup/monitoring integration.
- HA/replication role.

Modules should have explicit inputs, outputs, assumptions, and versioning. Avoid giant modules with many unrelated side effects.

## 7. Idempotency

Idempotent automation can run multiple times and bring the system to the exact same desired state without creating extra resources or repeating unintended side effects.

For example, configuration management should ensure the package is installed at the right version, the service is enabled, directories have the desired owner/mode, config files are rendered from templates, and roles/databases are created if missing.

Idempotency does not mean every SQL command is safe to run repeatedly. Use state-aware tasks, migrations, or appropriate upsert semantics.

## 8. Desired State and Actual State

Automation compares actual state against desired state.

| Attribute | Desired State | Actual State |
|---|---|---|
| PostgreSQL major | 17 | 17 |
| Package version | approved build | installed build |
| Port | 5432 | 5432 |
| TLS | required | enabled |
| Backup | WAL archive active | configured |
| Monitoring | all required alerts | one alert missing |

When drift occurs, determine its origin: a legitimate change, an emergency action, unapplied automation, or an out-of-band manual edit.

## 9. Drift Detection

Drift is the divergence between declared configuration and running state.

It can be detected via IaC plan/refresh, configuration management check mode, hashes of managed files, PostgreSQL settings inventories, package version inventories, cloud resource policies, and scheduled compliance reports.

Do not blindly overwrite all drift automatically. An emergency change may need to be folded back into the source of truth before running reconciliation.

## 10. IaC State Management

Some IaC tools maintain state to track which resources are managed.

State must be stored in an appropriate backend with access controls, locking if supported by the tool, backup/versioning, and no plaintext secrets in repositories.

Never edit state files manually without understanding resource identities and provider behavior. When state is lost or out of sync, plan imports/reconciliation carefully.

## 11. Managing Secrets

Database credentials, replication passwords, TLS private keys, and backup credentials must never be hardcoded in IaC, Git, or shell history.

Use a secret manager or appropriate credential management system:

- Cloud secret manager.
- Vault or enterprise secret store.
- Short-lived credentials when supported.
- OS-protected files with least-privilege permissions.

Repositories should store only secret references and injection mechanisms, never secret values.

## 12. Rotating Credentials

Runbooks must document who is authorized to rotate credentials, which consumers depend on each credential, how to update the database role/password, how to update the secret store, how to restart/reload consumers, how to verify new connections, and how to roll back if clients have not transitioned.

Never rotate a database password without first identifying all connection pools, jobs, replication links, and backup agents using that credential.

## 13. OS Baseline for PostgreSQL Hosts

Before installing PostgreSQL, standardize:

- OS distribution and release.
- Kernel and supported filesystems.
- Time synchronization.
- Locale/encoding packages.
- User/group for PostgreSQL.
- Limits and service manager.
- Firewall and routing.
- Monitoring/logging agents.
- Security updates.
- Backup mounts/permissions.

Never run PostgreSQL as root. Use a dedicated service account and restrict read/write access to data, WAL, log, and backup paths.

## 14. Package Repositories and Version Pinning

Install PostgreSQL from approved repositories and pin major/minor/package versions per release policy.

Example on a Debian-based system:

~~~bash
sudo apt-get update
sudo apt-get install postgresql-17 postgresql-client-17
~~~

This is an example; package naming and repositories depend on the distro. Production automation must verify repository signing, package origin, version policies, and update channels.

Do not use arbitrary package sources or let production environments automatically upgrade major versions via latest package tags.

## 15. Installing Extension Packages

If databases use native extensions, automation must install the exact package matching the PostgreSQL major version and OS architecture.

Example:

~~~bash
sudo apt-get install postgresql-17-postgis-3
~~~

Package names are illustrative; verify against your actual repository. SQL extension objects are installed separately inside each database with `CREATE EXTENSION`.

Package installation and database migrations should be independently observable and retryable tasks.

## 16. Filesystem and Storage Layout

Design storage based on workload, durability, and recovery requirements.

You may separate PGDATA, the WAL directory if architecture requires, tablespaces, PostgreSQL logs, backup staging, and archive/WAL storage.

Do not split volumes merely out of habit. Evaluate throughput, IOPS, latency, capacity, failure domains, snapshot semantics, and operational complexity.

## 17. Directory Ownership and Permissions

The PostgreSQL data directory must have ownership/mode matching PostgreSQL requirements. On Linux, for example:

~~~bash
sudo install -d -o postgres -g postgres -m 700 /var/lib/postgresql/data
~~~

Do not place PGDATA on filesystems with unsupported semantics or mount options that compromise durability.

Automation should check free space, mount status, ownership, and permissions before initdb/startup.

## 18. Networking and Firewalls

Clearly define allowed client subnets, replication traffic, monitoring/backup traffic, admin access, DNS names, service endpoints, and egress to secret managers/object storage.

Open only required ports. Do not bind PostgreSQL to all network interfaces if the service only needs a private network.

Network policies must align with `pg_hba.conf` and TLS policies.

## 19. DNS and Service Discovery

Applications should use stable endpoints rather than hardcoded node IPs.

Documentation must specify the primary/write endpoint, read-only/replica endpoints if any, internal DNS names, TTL/cache behavior, post-failover update mechanisms, health/readiness checks, and DNS record owners.

A DNS update does not guarantee all connection pools immediately reconnect. Connection draining and routing checks may be required.

## 20. TLS Configuration

TLS automation must manage server certificates, private keys, certificate chains, CA trust, file ownership/modes, expiration monitoring, and renewal/rotation procedures.

Example PostgreSQL settings:

~~~text
ssl = on
ssl_cert_file = 'server.crt'
ssl_key_file = 'server.key'
ssl_ca_file = 'root.crt'
~~~

Paths must match the host layout and access permissions. Private keys must be protected; never commit keys to Git or public artifacts.

## 21. pg_hba.conf and Authentication

`pg_hba.conf` governs client authentication by rule order.

~~~text
# TYPE  DATABASE  USER          ADDRESS          METHOD
hostssl appdb     app_runtime   10.20.0.0/16     scram-sha-256
hostssl replication repl_user   10.30.0.0/16     scram-sha-256
local   all       postgres                       peer
~~~

This is an illustrative example; adjust to actual networks and roles.

Automation must validate syntax and reload configuration. A broad rule near the top of the file can prevent narrower rules below it from ever matching.

## 22. PostgreSQL Configuration Files

Main configuration files typically include `postgresql.conf`, `pg_hba.conf`, `pg_ident.conf`, any included files, and OS service environment/configuration files.

Use version-controlled templates and variables. Avoid uncontrolled search-and-replace edits when you can render the entire managed section.

Keep local overrides intentional and document include ordering explicitly.

## 23. Parameter Precedence

A setting can originate from multiple sources: default, configuration files, command-line options, `ALTER SYSTEM`, database/role settings, or session `SET`.

The `pg_settings` view provides current settings and their sources:

~~~sql
SELECT
    name,
    setting,
    unit,
    source,
    sourcefile,
    sourceline,
    pending_restart
FROM pg_settings
ORDER BY name;
~~~

Do not assume `postgresql.conf` is the sole source. When multiple layers exist, document the source of truth and how changes are made.

## 24. Reload and Restart

Some settings apply via reload; others require a PostgreSQL restart.

~~~sql
SELECT
    name,
    setting,
    context,
    pending_restart
FROM pg_settings
WHERE name IN (
    'shared_buffers',
    'work_mem',
    'max_connections',
    'log_min_duration_statement',
    'shared_preload_libraries'
)
ORDER BY name;
~~~

- sighup: can be applied via reload.
- postmaster: requires server restart.
- Other contexts have their own rules such as superuser/backend/superuser-backend.

Use `pg_reload_conf()` or the service manager per procedure:

~~~sql
SELECT pg_reload_conf();
~~~

After changing restart-required settings, check `pending_restart` and schedule a controlled restart.

## 25. ALTER SYSTEM

`ALTER SYSTEM` writes settings to `postgresql.auto.conf`:

~~~sql
ALTER SYSTEM SET log_min_duration_statement = '500ms';
SELECT pg_reload_conf();
~~~

This is a mechanism for runtime configuration changes, but it can obscure the source of truth if automation also manages `postgresql.conf`.

Adopt a clear policy: either automation manages `ALTER SYSTEM`/`auto.conf`, or ad-hoc usage is prohibited and changes must go through the repository. Never let multiple systems write the same parameter without documented precedence.

## 26. Checking Configuration Files for Errors

The `pg_file_settings` view shows entries parsed from configuration files and any parse errors:

~~~sql
SELECT
    sourcefile,
    sourceline,
    name,
    setting,
    applied,
    error
FROM pg_file_settings
ORDER BY sourcefile, sourceline;
~~~

This view helps detect typos, duplicate settings, or files not applying as expected.

Do not check only the automation task's exit code. Read PostgreSQL's configuration state after reloading.

## 27. Managing shared_preload_libraries

Some extensions must be loaded at server startup:

~~~text
shared_preload_libraries = 'pg_stat_statements'
~~~

Automation must install the package/library, render the setting, verify the file exists and matches the build, restart per maintenance policy, inspect startup logs, and verify the extension works.

If a module is missing, PostgreSQL may fail to start. Prepare a config file rollback and service recovery procedure.

## 28. Locale, Encoding, and Collation

`initdb` creates a cluster with encoding and locale choices that have long-term consequences.

Example:

~~~bash
initdb \
  --pgdata=/var/lib/postgresql/data \
  --encoding=UTF8 \
  --locale=C.UTF-8
~~~

Locale names can vary across OS distributions. Record the locale provider, collation version, and encoding in the deployment manifest.

Changing the collation environment can invalidate index ordering; evaluate `REINDEX`/collation refreshes according to PostgreSQL version and workload.

## 29. Bootstrapping Roles and Databases

Automation can create roles/databases via SQL scripts or migration tools.

~~~sql
CREATE ROLE app_owner NOLOGIN;
CREATE ROLE app_runtime LOGIN;

CREATE DATABASE appdb OWNER app_owner;
GRANT CONNECT ON DATABASE appdb TO app_runtime;
~~~

Handle idempotency and ownership carefully. `CREATE DATABASE` cannot run inside a transaction block, so it is usually a separate task.

Never store plaintext passwords in SQL files. Inject credentials via a secret manager or provisioning mechanism.

## 30. Privileges and Ownership

Distinguish cluster administrator, database owner, schema owner, migration role, runtime application role, read-only/reporting role, backup/replication role, and monitoring role.

Create roles by responsibility and grant least privilege. Never use superuser for application connections.

Automation must also manage memberships, default privileges, and object ownership after migrations.

## 31. Bootstrap Scripts and Migrations

Bootstrap scripts prepare a new cluster/database: roles, databases, schema prerequisites, and extensions.

Migrations evolve the schema along with application versions.

Do not re-run all migrations as seeds if the migration tool maintains version history. Do not place non-idempotent bootstrap operations into a stateless script.

Specify the exact sequence: packages, initdb, service config, roles/databases, extensions, migrations, baseline data, and application deployment.

## 32. Backup Automation

Backup automation must define base backup cadence, WAL archiving, retention, encryption, storage locations, credentials, monitoring/alerting, restore testing, and RTO/RPO.

Example base backup:

~~~bash
pg_basebackup \
  --host=db-primary.internal \
  --username=backup_user \
  --pgdata=/backup/base \
  --format=plain \
  --wal-method=stream
~~~

This is only an illustrative command; a real backup system must manage WAL, retention, encryption, and metadata consistently.

## 33. Restore Automation

Restore automation must accept a backup identifier, target PostgreSQL major version, target host/storage, recovery target time/LSN for PITR, WAL archive location, tablespace mappings, extension package inventory, and configuration/secret references.

After restoring, do not immediately open traffic. Run startup checks, recovery state checks, database validation, and application smoke tests.

## 34. Monitoring and Alerting as Code

Manage dashboards and alerts in version control where supported by the platform.

Key metrics:

- Connection counts and saturation.
- Transaction rates.
- Query latency.
- Locks/deadlocks.
- Cache hit ratio in workload context.
- WAL generation and archive failures.
- Replication lag.
- Disk capacity/IOPS/latency.
- Checkpoints and autovacuum.
- Backup age and restore test status.
- Certificate expiration.
- PostgreSQL process/service health.

Alerts require severity, an owner, a runbook link, and expected actions. Avoid alerts without an owner or actionable response.

## 35. Log Management

Standardize log destinations, log rotation, retention, structured fields if available, timezone/timestamp formats, slow query thresholds, connection/disconnection logging policies, audit logging, and secret/PII redaction.

Never enable unbounded verbose logging, as it can exhaust disk space and expose sensitive information.

## 36. HA and Replication Automation

For primary/standby topologies, automation must manage node inventories, replication credentials, WAL settings, replication slots, standby configuration, failover orchestration, fencing/single-writer protection, rejoin/reseed processes, and monitoring.

Failover automation must ensure the old primary cannot continue accepting writes after a standby is promoted. Split-brain is a severe risk.

Do not treat a standalone promote script as complete HA automation.

## 37. Upgrade Automation

Major version upgrades require a dedicated pipeline with preflight and gates:

1. Inventory source/target versions.
2. Verify extension packages.
3. Rehearse backups and restores.
4. Run compatibility checks.
5. Prepare target binaries/config.
6. Execute `pg_upgrade` or logical migration.
7. Verify database/extension state.
8. Run `ANALYZE` and application validation.
9. Cut over.
10. Maintain a rollback/recovery window.

Automation must never bypass a GO/NO-GO gate when a critical validation fails.

## 38. CI/CD for Database Infrastructure

A pipeline may consist of:

~~~text
Pull request
    |
    v
Static validation / formatting
    |
    v
IaC plan and review
    |
    v
Configuration lint and syntax checks
    |
    v
Build/test database image
    |
    v
Deploy to ephemeral environment
    |
    v
Smoke tests and restore tests
    |
    v
Approval / change window
    |
    v
Deploy to production
    |
    v
Post-deploy verification
~~~

Do not give production pipelines broader permissions than necessary. Separate build identities, deploy identities, and runtime service identities.

## 39. Change Management

Each change should record a ticket/change ID, objective and scope, affected services/nodes/databases, owner and approver, preflight checks, planned window, commands/automation version, success criteria, rollback/recovery path, evidence, and timestamps.

Emergency changes must be recorded and folded back into the source of truth once stabilized.

## 40. Post-Provisioning Validation

After automation provisions a host/database, verify the actual state.

OS-level checks:

~~~bash
systemctl status postgresql
df -h
lsblk
timedatectl status
~~~

Database checks:

~~~sql
SELECT version();

SHOW data_directory;
SHOW config_file;
SHOW hba_file;
SHOW port;

SELECT
    current_database(),
    current_user,
    inet_server_addr(),
    inet_server_port();
~~~

Verify TLS, roles, extensions, backups, replication, and monitoring according to your actual topology.

## 41. Readiness and Health Checks

Distinguish liveness from readiness:

- Liveness: is the process still running?
- Readiness: does the database meet conditions to accept workload?

Readiness may need to verify that PostgreSQL is accepting connections, the target database exists, the application role can authenticate, required extensions load, primary/standby roles match, replication/backup requirements are met, and disk space is normal.

Do not use a TCP port check as proof that the database is ready to serve business traffic.

## 42. Pre-Rollout Configuration Validation

Before applying to production:

- Parse/format validation for IaC.
- Plan diff reviewed.
- Configuration templates linted.
- PostgreSQL settings validated.
- `pg_hba` rules reviewed in order.
- Secret references verified to exist.
- Package versions resolved.
- Storage/network dependencies ready.
- Rollback artifacts accessible.

An ephemeral database can be spun up to test rendered configuration before restarting production.

## 43. Rolling Deployments and Maintenance Windows

Not every PostgreSQL change is rolling-safe.

Classify reload-only settings, restart-required settings, extension/library changes, schema migrations, major version upgrades, and HA topology changes.

For HA, define node ordering and failover behavior. Restarting a replica before the primary can be safe in some situations, but must follow topology- and version-specific procedures.

Never automate rolling restarts without verifying compatibility and the HA system's quorum/leader semantics.

## 44. Rollback Automation

Rollback planning must identify the previous artifact/config version, whether database state remains compatible with the old application, whether old packages/binaries are still available, whether falling back to the old node is possible or a restore is required, whether post-cutover writes could be lost, whether DNS/endpoints can switch back, who decides on rollback, and the decision deadline.

Rolling back a config file is usually simpler than rolling back data/schema. Never assume reverting a Git commit automatically undoes database migrations or transactions.

## 45. What Is a Runbook?

A runbook is an operational guide for a specific operational scenario.

A good runbook includes purpose/scope, preconditions, required access/roles, exact commands or automation entry points, expected output, verification, timeouts, failure handling, escalation/contacts, evidence capture, last reviewed date, and owner.

Instructions like "restart the database if there is an error" are insufficient for an on-call engineer to execute safely.

## 46. PostgreSQL Deployment Runbook

A deployment runbook may include:

1. Confirm change window and approval.
2. Verify the latest backup.
3. Inspect host/storage/network.
4. Verify package repository/version.
5. Provision host and directories.
6. Install PostgreSQL/extension packages.
7. Render configuration and authentication.
8. Initialize or attach the data directory per design.
9. Start the service.
10. Create roles/databases/extensions.
11. Configure backups/monitoring/replication.
12. Run smoke tests.
13. Record evidence and hand off.

Each step needs an owner and expected result.

## 47. Common Incident Runbooks

Maintain separate runbooks for PostgreSQL failing to start, disk nearly full, WAL archiving failing, rising replication lag, backup job failures, connection saturation, expiring certificates, failover, restore/PITR, missing extension libraries, authentication failures, and unexpected restarts.

Each runbook must separate symptoms, diagnosis, mitigation, and permanent fix.

## 48. Disaster Recovery Documentation

DR documentation must specify RTO/RPO, backup topology, backup retention, WAL archive and restore process, recovery region/account, DNS/service endpoint cutover, secrets/certificates recovery, extension packages and versions, validation criteria, decision authority, communication plan, and the last successful restore drill.

A succeeded backup job does not prove DR can finish within RTO. Record actual restore exercise results.

## 49. Architecture Diagram

Handover documentation should include a diagram:

~~~text
Application services
        |
        v
Private DB endpoint / connection pool
        |
        v
Load balancer or HA routing
        |
        v
PostgreSQL primary
        |
        +----------> Standby node(s)
        |
        +----------> WAL archive / backup storage
        |
        +----------> Monitoring and log platform
        |
        +----------> Secret manager / KMS
~~~

Real diagrams should annotate network boundaries, ports, replication direction, failure domains, storage, DNS names, and owners. Never put passwords or private keys in diagrams.

## 50. System Inventory and Configuration Manifest

The manifest should record:

| Group | Fields to Record |
|---|---|
| Identity | Environment, cluster name, owner |
| Version | PostgreSQL major/minor, OS, extensions |
| Compute | VM/container type, CPU, RAM |
| Storage | PGDATA, WAL, tablespaces, capacity |
| Network | Private endpoints, ports, allowed sources |
| Security | Roles, auth method, TLS, secret references |
| HA | Primary/standby topology, failover manager |
| Backup | Tool, schedule, retention, WAL archive |
| Monitoring | Dashboards, alerts, runbooks |
| Automation | Repository, module version, pipeline |

The manifest must reflect current state and include a last-updated date.

## 51. Access and Ownership Handover

Handover must document the team responsible for PostgreSQL, on-call/escalation paths, DBA/admin roles, application owners, cloud/OS owners, backup/DR owners, monitoring owners, change approvers, and secret manager access procedures.

Never put passwords or tokens in documentation. Record secret reference names and how to request access per policy.

## 52. Operational Procedures and Routine Tasks

Documentation should specify frequency and owner for backup verification, restore testing, capacity reviews, extension/package updates, PostgreSQL minor updates, certificate rotation, role/access reviews, replication health reviews, log/alert reviews, vacuum/analyze monitoring, and disaster recovery exercises.

A task list without frequencies or owners is rarely executed consistently.

## 53. Knowledge Transfer

A handover session should cover:

1. Architecture walkthrough.
2. Deployment pipeline walkthrough.
3. Configuration/source-of-truth walkthrough.
4. Backup and restore demonstration.
5. Failover/rejoin demonstration.
6. Monitoring and alert response.
7. Secret/access process.
8. Known issues and limitations.
9. Escalation and change approval.
10. Q&A and capturing gaps.

The receiving team should execute several procedures under supervision to prove the documentation is usable.

## 54. Documentation Versioning

Every document should list an owner, version or commit, last reviewed date, applicable PostgreSQL version, environment scope, related automation repository, change history, and links to dashboards/tickets/runbooks.

Documentation without review dates quickly becomes stale after upgrades or topology changes.

## 55. Secrets and Handover Documentation

Never include database passwords, private keys, cloud access keys, tokens, connection strings with passwords, or unredacted production dumps in READMEs/runbooks.

You may document secret names/paths, service identities, required permissions, and request/rotation procedures. If a connection string example is needed, use placeholders and never real credentials.

## 56. Known Limitations and Technical Debt

Handover documentation must clearly list extensions unsupported on target versions, restore steps that remain manual, backup retention gaps relative to policy, uncovered monitoring metrics, constrained capacity headroom, expected failover downtime, external dependencies with separate SLAs, and unrehearsed runbooks.

Assign an owner and next action to each gap. Do not mask limitations by claiming "fully automated" when manual steps still exist.

## 57. Operational Acceptance Criteria

A system should be considered ready for handover only when:

- Infrastructure code lives in a repository.
- Configuration has a source of truth.
- Deployment is reproducible.
- Secrets are securely managed.
- Backups and restores are verified.
- Monitoring/alerts have owners.
- HA/failover is rehearsed if required.
- Runbooks are reviewed.
- Access model is clear.
- On-call and escalation are confirmed.
- Known limitations are documented.
- The receiving team can execute basic procedures.

## 58. Example Repository Structure

~~~text
postgres-platform/
  infra/
    modules/
      network/
      compute/
      storage/
    environments/
      dev/
      staging/
      production/
  config/
    os/
    postgresql/
    pgbouncer/
    monitoring/
  database/
    bootstrap/
    migrations/
    seeds/
  backup/
    policies/
    restore/
  runbooks/
    deploy.md
    failover.md
    restore-pitr.md
    disk-full.md
    certificate-rotation.md
  docs/
    architecture.md
    inventory.md
    security.md
    handover.md
  .github/
    workflows/
~~~

This structure is only a suggestion. What matters is that ownership, dependencies, and the release lifecycle are clear.

## 59. Example PostgreSQL Settings Manifest

A YAML file can describe desired settings:

~~~yaml
postgresql:
  port: 5432
  listen_addresses:
    - 10.20.1.10
  timezone: UTC
  max_connections: 200
  shared_buffers: 4GB
  log_min_duration_statement: 500ms
  ssl: true
  password_encryption: scram-sha-256
  shared_preload_libraries:
    - pg_stat_statements
~~~

This is an illustrative example, not a sizing recommendation. Memory/connection values must be calculated from RAM, workload, connection pooling, and platform limits.

Automation must validate types, units, allowed values, and restart contexts before applying.

## 60. Example Configuration Management Task

An illustrative Ansible task:

~~~yaml
- name: Ensure PostgreSQL package is installed
  ansible.builtin.package:
    name: postgresql-17
    state: present

- name: Ensure PostgreSQL data directory exists
  ansible.builtin.file:
    path: /var/lib/postgresql/data
    state: directory
    owner: postgres
    group: postgres
    mode: "0700"

- name: Render PostgreSQL configuration
  ansible.builtin.template:
    src: postgresql.conf.j2
    dest: /etc/postgresql/17/main/postgresql.conf
    owner: postgres
    group: postgres
    mode: "0640"
  notify: Reload PostgreSQL
~~~

The handler can invoke a service reload:

~~~yaml
- name: Reload PostgreSQL
  ansible.builtin.service:
    name: postgresql
    state: reloaded
~~~

Service names and paths depend on the distro. Some settings require a restart; handlers must classify changes accurately instead of using reload for everything.

## 61. Automation Safety and Failure Handling

Each task requires preconditions, timeouts, an appropriate retry policy, failure behavior, idempotency, logging, verification, and compensation/rollback if applicable.

Never blindly retry a non-idempotent operation such as creating a resource with side effects or running a data migration. For database migrations, record version and transaction semantics.

Automation must fail fast when secrets are missing, disk space is insufficient, or the target version is unsupported.

## 62. Limiting Blast Radius

Deploy in narrow scopes: one dev environment, one staging cluster, one canary node if topology allows, one production cluster within a change window, and then broader rollout once evidence is confirmed.

Separate deployment permissions by environment and require approvals for production. Never use the same administrative credential across all pipelines.

## 63. Audit Trail and Evidence

Retain Git commits/tags, IaC plan/apply outputs, configuration management run IDs, PostgreSQL version/settings snapshots, package inventories, change tickets, start/end timestamps, health/validation results, backup/restore evidence, and operator/approver identities.

Redact secrets before storing logs. Evidence must suffice to answer who changed what, where, when, and with what result.

## 64. Production Handover Checklist

**Infrastructure**

- Network, storage, and firewalls documented.
- Compute sizing and capacity headroom recorded.
- DNS/endpoints documented.
- Failure domains and dependencies diagrammed.

**PostgreSQL**

- Versions and packages pinned.
- Configuration source of truth clear.
- `pg_hba`/TLS/authentication documented.
- Roles/ownership/default privileges recorded.
- Extensions and versions inventoried.
- Backup/restore/HA verified.

**Operations**

- Monitoring/alerts have owners.
- Runbooks include preconditions and verification.
- Upgrades/failover/restores rehearsed.
- Secrets/rotation have documented procedures.
- On-call/escalation paths clear.
- Known limitations have owners.

**Automation**

- IaC/config repositories handed over.
- Pipelines and access permissions clear.
- State/backend/locking protected.
- Drift detection scheduled.
- Change approval and rollback documented.

## 65. Frequently Asked Questions

### Does IaC replace configuration management?

Not entirely. IaC typically manages infrastructure resources; configuration management manages OS/service state. A single platform may handle both, but ownership and lifecycles must remain distinct.

### Why must automation be idempotent?

So it can safely re-run after failures or when reconciling drift. However, migrations and operations with side effects still require dedicated version/state management.

### Should `postgresql.conf` be managed using `ALTER SYSTEM`?

It is possible, but requires a single consistent policy. If automation manages files while operators simultaneously write to `postgresql.auto.conf`, the source of truth and precedence become confusing.

### How do I know if a setting requires a restart?

Check `pg_settings.context` and `pending_restart`, and consult parameter/version documentation. Never guess solely from the setting name.

### Can all PostgreSQL configuration be reloaded?

No. Some settings are read only at startup and require a restart. Check `context` and `pending_restart` after reloading.

### Should passwords be stored in Ansible variables or Terraform state?

Never store plaintext in repositories. Terraform state can also contain sensitive values even when marked sensitive; use secret references, encrypted remote state, and strict access controls.

### Why is a package inventory needed?

To accurately reproduce extension libraries and dependencies during restores, failovers, or host rebuilds.

### Do backups belong in IaC?

IaC can provision storage, policies, and backup resources; however, database backup contents, WAL retention, and restore procedures must be managed by the backup platform and runbooks.

### Can a readiness check use only `pg_isready`?

`pg_isready` confirms the server responds with connection status, but does not prove the application, extensions, replication, or business transactions are ready.

### Why record `sourcefile` from `pg_settings`?

To know which file a setting comes from and detect overrides outside the source of truth.

### Should handover documents contain connection passwords?

No. Record endpoints and secret references; credentials are accessed via the secret manager per access policy.

### Who owns a runbook?

A specific team or operational role must own reviewing/updating it. Each runbook should have an owner and review date.

### When should template databases be used?

When schemas/extensions/baselines change infrequently and many test databases must be created quickly. Templates must be versioned alongside migrations and seeds.

### Can failover be fully automated?

Yes, with a properly designed HA platform, but it requires fencing/single-writer protection, quorum/leader semantics, monitoring, and failover drills. A standalone promote command is insufficient.

### When is handover complete?

When the receiving team holds appropriate access, understands the architecture, can run deployment/restore/failover procedures, knows owners/escalation paths, and accepts documented known limitations.

## 66. Summary

Key principles to remember:

1. Separate provisioning, configuration management, database deployment, and operations automation.
2. Use IaC and configuration repositories as the source of truth.
3. Separate environments via variables/modules, not manual config copying.
4. Design idempotent, state-aware automation.
5. Monitor drift and fold emergency changes back into the source of truth.
6. Protect IaC state, secrets, and deployment identities.
7. Standardize OS baselines, packages, storage, networking, and service accounts.
8. Pin PostgreSQL and extension package versions.
9. Manage PGDATA, WAL, tablespaces, logs, and backup storage deliberately.
10. Synchronize firewalls, DNS, TLS, and `pg_hba.conf`.
11. Understand parameter precedence, reload contexts, and restart requirements.
12. Use `pg_settings` and `pg_file_settings` to verify actual configuration.
13. Manage roles, ownership, and default privileges with least privilege.
14. Separate bootstrap scripts from schema migrations and test seeds.
15. Automate backups, yet always test restores.
16. Manage monitoring/alerts as code and attach owners/runbooks.
17. HA automation must prevent split-brain and include rejoin procedures.
18. Upgrade automation needs preflight, gates, validation, and recovery paths.
19. Every change needs evidence and an audit trail.
20. Runbooks need exact commands, expected outputs, timeouts, and escalation paths.
21. Handover requires architecture, inventory, access models, and operational procedures.
22. Never place passwords, tokens, or private keys in documentation.
23. Document known limitations, technical debt, and owners explicitly.
24. Handover is complete only when the receiving team can operate and recover the system.

Lifecycle diagram:

~~~text
Requirements and architecture
             |
             v
       Infrastructure as Code
             |
             v
     Provision network/storage/VM
             |
             v
    Configure OS and PostgreSQL
             |
             v
 Bootstrap roles, databases, extensions
             |
             v
     Deploy backup and monitoring
             |
             v
       Validate actual state
             |
             v
       Run acceptance tests
             |
             v
     Handover docs and runbooks
             |
             v
       Operate / monitor / audit
             |
             v
    Review drift, changes and DR
             |
             +------> Update source of truth
~~~

**Conclusion:** PostgreSQL deployments become reproducible when infrastructure, configuration, and database bootstrapping are defined in a source of truth and automated toward a desired state. Configuration must be verified from PostgreSQL itself, because reloads/restarts, precedence, and overrides can cause actual state to differ from intended files. Handover documentation must equip the receiving team to deploy, monitor, back up, fail over, and recover without relying on the original builder's memory.
