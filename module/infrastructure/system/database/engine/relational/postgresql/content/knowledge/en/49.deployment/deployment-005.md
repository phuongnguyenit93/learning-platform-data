# Managing Configuration, Secrets, and TLS by Environment

A PostgreSQL deployment typically spans multiple environments such as development, test, staging, production, and disaster recovery. These environments need a shared, controlled configuration structure, while concrete values differ: hostnames, ports, database names, connection limits, memory budgets, logging, backup destinations, authentication policies, and certificate identities. If configuration is edited manually on individual machines, environments easily drift, bugs become hard to reproduce, and credentials or certificates can accidentally be used in the wrong place.

Secrets and TLS must be managed as part of the deployment lifecycle. Passwords, private keys, client certificates, replication credentials, and API secrets must have clear provisioning sources, access controls, rotation, revocation, and auditing. TLS protects data in transit and also authenticates the server/client according to policy; enabling encryption without verifying server identity can still leave clients connecting to the wrong endpoint. PostgreSQL, applications, poolers, monitoring, and replication configurations must remain consistent regarding certificate trust and credential lifecycles.

This lesson belongs to the **Deployment** chapter of the **Database Engine Relational PostgreSQL** module. It covers organizing configuration by environment, understanding precedence and reload/restart behavior, separating secrets from general configuration, managing roles/passwords, deploying server/client TLS, configuring pg_hba.conf, performing rotation, and operating safely on HA/managed services.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish between general configuration, credentials, and cryptographic material.
- Organize PostgreSQL settings consistently across development, test, staging, production, and DR.
- Understand postgresql.conf, postgresql.auto.conf, include/include_dir, and configuration precedence.
- Use pg_settings, pg_file_settings, SHOW, and pg_reload_conf to inspect configuration.
- Distinguish reloadable settings from settings requiring a restart.
- Manage roles, SCRAM password authentication, and password rotation.
- Protect client passwords using passfiles/secret managers.
- Enable server TLS and verify certificate chains/hostnames on the client.
- Configure client certificate authentication and pg_hba.conf.
- Manage TLS for application, pooler, replication, and FDW connections.
- Plan zero-outage certificate/secret rotation.
- Check configuration drift, auditing, observability, and failure recovery.

## 2. Three Categories of Information to Manage

Not all configuration shares the same sensitivity level or lifecycle.

| Category | Examples | Management Approach |
|---|---|---|
| Configuration | max_connections, work_mem, host, port, log settings | Version control/config management |
| Secret | Password, replication credential, client private key passphrase | Secret manager, access control, rotation |
| Trust material | CA certificate, server/client certificate, public key | PKI/certificate management, expiry tracking |

### 2.1. Configuration

Configuration describes system behavior and endpoints. It requires review, versioning, validation, and promotion across environments.

### 2.2. Secret

Secrets enable authentication or resource access. If exposed, unauthorized parties can impersonate an identity or access data. Secrets must not appear in source code, logs, screenshots, or tickets.

### 2.3. Trust material

CA certificates and public certificates define trusted identities. Private keys must be protected like secrets; certificate expiry and revocation must be tracked.

### 2.4. Do not use a single file for everything

Separating configuration from secrets enables distinct permissions, independent rotation, and prevents readers of general configuration from seeing passwords/private keys.

### 2.5. Data classification

Define sensitivity levels, owners, retention, and permitted access for each category. Values that are not passwords can still be sensitive, such as internal hostnames, database names, and topology.

## 3. Environment-specific configuration

Each environment should share the same declarative structure, with values injected from appropriate sources.

### 3.1. Development

Can use local PostgreSQL, disposable containers, and dedicated test credentials. Never reuse production passwords/certificates.

### 3.2. Test/CI

Use deterministic configuration, short-lived credentials, and certificates issued by a test CA. Test environments should mirror production TLS/authentication if that is a release requirement.

### 3.3. Staging

Staging should match production in PostgreSQL major version, authentication, TLS policy, pooler, extensions, and network boundaries. Use independent staging secrets/certificates.

### 3.4. Production

Use an approved configuration baseline, secret manager/PKI, least privilege, auditing, and change control. Do not rely on unrecorded manual file edits.

### 3.5. Disaster recovery

DR requires credentials/certificates that remain accessible when the primary region is unavailable. Rehearse access paths, secret manager failover, CA trust, and certificate renewal in DR.

## 4. Same structure, different values

A common deployment pattern is keeping templates/config schemas in a repository and supplying values per environment.

~~~text
deployment/
  postgres/
    postgresql.conf.template
    pg_hba.conf.template
    settings/
  environments/
    development/
    test/
    staging/
    production/
    disaster-recovery/
  secret references:
    database role credentials
    TLS private keys
    client certificates
    CA bundles
~~~

### 4.1. Template

Templates describe required settings and expected data types. Do not embed passwords or private keys in templates.

### 4.2. Environment values

Each environment supplies appropriate hostnames, resource limits, storage paths, monitoring endpoints, and authentication policies.

### 4.3. Secret references

Configuration should reference secret paths/identities rather than containing secret values. The runtime/deployment system retrieves secrets from the secret manager according to granted permissions.

### 4.4. Validation

Validate generated files before applying them. Check syntax, duplicate settings, required parameters, path existence, file permissions, and certificate expiry.

### 4.5. Promotion

Promote the same versioned configuration artifact across environments, substituting environment-specific values and secret references. Avoid creating a separate config with no lineage for production.

## 5. PostgreSQL configuration files

PostgreSQL typically uses multiple files to configure the server.

### 5.1. postgresql.conf

The main file containing server parameters such as memory, connections, WAL, logging, replication, and SSL.

### 5.2. postgresql.auto.conf

ALTER SYSTEM writes settings to postgresql.auto.conf in the data directory. PostgreSQL reads this file alongside configuration files, and it is typically used for overrides created by ALTER SYSTEM.

### 5.3. pg_hba.conf

The host-based authentication file governs permitted client connections and authentication methods. It has its own reload lifecycle.

### 5.4. pg_ident.conf

Maps external identities to PostgreSQL roles for authentication methods supporting identity mapping, such as certificate/ident.

### 5.5. Certificate/key files

Server certificates, private keys, CA certificates, and CRLs usually reside outside SQL catalogs. Paths and file permissions must align with the service account and OS policy.

## 6. Configuration includes and file organization

Configuration can be split into multiple files to separate ownership and reduce conflicts.

~~~conf
# postgresql.conf
include_dir = 'conf.d'
include_if_exists = 'local-overrides.conf'
~~~

### 6.1. include

Reads the specified file at the include position in the configuration stream.

### 6.2. include_if_exists

Allows skipping a file if it does not exist. Use carefully because a missing file may cause a critical setting not to be applied.

### 6.3. include_dir

Reads configuration files in the directory in the order defined by PostgreSQL. Do not rely on arbitrary ordering from deployment tooling.

### 6.4. Per-file ownership

Files can be divided by domain: connections, memory, WAL/replication, logging, SSL. Assign owners/reviewers per domain.

### 6.5. Avoiding duplicate/conflicting settings

A setting may be declared in multiple places; the final applied value depends on read order/override source. Use pg_settings.source and pg_file_settings to trace the source of the effective value.

## 7. Configuration precedence and value sources

Do not simply read a file and assume PostgreSQL is using that value.

### 7.1. Effective value

SHOW parameter or pg_settings.setting shows the value PostgreSQL is currently applying in the session/server context.

~~~sql
SHOW max_connections;

SELECT
    name,
    setting,
    unit,
    source,
    sourcefile,
    sourceline,
    pending_restart
FROM pg_settings
WHERE name IN (
    'max_connections',
    'shared_buffers',
    'work_mem',
    'ssl',
    'shared_preload_libraries'
)
ORDER BY name;
~~~

### 7.2. Source

pg_settings.source indicates the setting's origin, such as default, configuration file, command line, database/role/session setting, or ALTER SYSTEM depending on context/version.

### 7.3. Source file and line

sourcefile/sourceline trace the exact file/line that provided the value. Some sources have no file location.

### 7.4. pending_restart

pending_restart=true indicates the new configuration value requires a restart to take effect. The running value may still differ from the desired file value.

### 7.5. Runtime overrides

SET at the session/role/database level can cause a session's value to differ from the global default. Check using the actual application role/session when investigating.

## 8. Inspecting file settings and configuration errors

pg_file_settings lets you inspect entries read from configuration files and detect errors.

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

### 8.1. applied

Indicates whether the entry was applied during configuration parsing. An entry may not be applied because it was overridden or had an error.

### 8.2. error

Displays parse/validation issues. Check before reloading/restarting to avoid introducing invalid config into production.

### 8.3. Duplicate entries

Multiple declarations for the same parameter can be valid but easily cause confusion. Remove unnecessary duplicates in the source of truth.

### 8.4. Permission/path errors

Unreadable include/certificate files can cause reload/startup failures or retain old settings. Verify service account permissions and server logs.

### 8.5. Do not edit files when the server uses another source

If config is managed by an operator, container image, orchestration, or cloud parameter group, direct file edits may be overwritten. Make changes through the proper control plane.

## 9. ALTER SYSTEM and usage limits

ALTER SYSTEM writes a parameter into postgresql.auto.conf.

~~~sql
ALTER SYSTEM SET log_min_duration_statement = '500ms';
SELECT pg_reload_conf();
~~~

### 9.1. Use cases

ALTER SYSTEM is useful for intentional server-level changes made by a DBA that must persist across restarts.

### 9.2. Not a session command

ALTER SYSTEM is not equivalent to SET. It writes persistent configuration for the cluster, not just the current session.

### 9.3. Not all parameter contexts are supported

Some settings cannot be changed via ALTER SYSTEM, such as settings restricted to session/user context or limited by parameter semantics.

### 9.4. Configuration drift

If ALTER SYSTEM is used outside config management, the repository may no longer reflect runtime state. Record changes in the source of truth and reconcile auto.conf.

### 9.5. Do not store secrets via ALTER SYSTEM

Do not use auto.conf as a secret store. The file can be read by users with filesystem/DBA access and is usually backed up with the data directory.

## 10. Reload and restart

Each parameter has a context determining how it is applied.

| Context | Typical Application Method |
|---|---|
| postmaster | Server restart |
| sighup | Configuration reload |
| superuser-backend | New backend/session or privileged session depending on setting |
| backend | New backend |
| superuser | Superuser can SET |
| user | User can SET |

### 10.1. Reload

pg_reload_conf() or a service reload sends a signal for PostgreSQL to re-read reloadable files such as postgresql.conf and pg_hba.conf.

### 10.2. Restart

Settings with context postmaster require a server restart. Plan HA/maintenance windows when restarts impact availability.

### 10.3. Checking context

~~~sql
SELECT name, setting, context, pending_restart
FROM pg_settings
WHERE name IN ('ssl', 'ssl_cert_file', 'shared_preload_libraries',
               'max_connections', 'log_min_duration_statement');
~~~

### 10.4. Reload does not alter all sessions

Some settings take effect only for new backends or new connections. Existing sessions may retain previously negotiated session-level values/SSL state.

### 10.5. Confirm after applying

Check pg_settings, pg_file_settings, logs, pg_hba behavior, and actual client connections. A successful reload command does not prove all intended changes took effect.


## 11. Per-database and per-role configuration

Not every difference between applications requires editing postgresql.conf. PostgreSQL lets you set defaults per database and per role.

### 11.1. ALTER ROLE SET

~~~sql
ALTER ROLE reporting_app
SET statement_timeout = '30s';
~~~

The setting applies to new sessions for that role, unless overridden by database/session settings according to precedence.

### 11.2. ALTER DATABASE SET

~~~sql
ALTER DATABASE analytics
SET work_mem = '16MB';
~~~

Use when a database has a distinct workload/resource profile. Evaluate total memory against the number of concurrent operations.

### 11.3. ALTER ROLE IN DATABASE

Settings can be scoped to a specific role within a specific database:

~~~sql
ALTER ROLE reporting_app IN DATABASE analytics
SET statement_timeout = '20s';
~~~

### 11.4. Session SET

Applications can run SET/SET LOCAL for a transaction/session if the parameter context permits. SET LOCAL remains in effect only until the end of the transaction.

### 11.5. Reset and precedence

ALTER ROLE/DATABASE defaults are applied when a session starts; application SET can override them. Check current_setting() inside the actual session when debugging.

## 12. Parameter context and environments

Do not use identical values across all environments if capacity and workloads differ.

### 12.1. Connections

max_connections and pool sizing depend on instance size, app replicas, admin headroom, and replication/worker connections.

### 12.2. Memory

shared_buffers, work_mem, maintenance_work_mem, and effective_cache_size must be chosen based on RAM, concurrency, and workload. work_mem can be allocated multiple times within a single query.

### 12.3. WAL/replication

wal_level, max_wal_senders, max_replication_slots, archive_mode, and retention must fit the topology. A single-node staging setup cannot by itself validate production HA configuration.

### 12.4. Logging

log_min_duration_statement, log_line_prefix, log_connections/disconnections, and logging_collector must balance visibility against storage/privacy.

### 12.5. SSL/authentication

Production typically requires stricter TLS/authentication policies than local development. Staging must mirror those policies to catch issues before release.

## 13. Configuration drift

Configuration drift happens when runtime environments diverge beyond approved differences.

### 13.1. Drift sources

Manual edits, ALTER SYSTEM, emergency SET/ALTER ROLE, operator reconciliation, package defaults, and deployment scripts can all introduce drift.

### 13.2. Snapshot effective config

Periodically export pg_settings including name, setting, unit, source, context, and pending_restart. Do not export secret values from mapping/password files.

### 13.3. Compare by policy

Compare each environment against its baseline. Certain values should vary by capacity/host, but security parameters should meet the same minimum policy.

### 13.4. Detect unknown overrides

Look for source='database', 'user', 'client', or file paths outside the expected inventory. Investigate before resetting.

### 13.5. Reconcile

Fold emergency changes into the source of truth or revert them with a change record. Do not leave unmanaged auto.conf/role settings around.

## 14. Configuration in containers and orchestration

Containerized PostgreSQL still requires a versioned configuration source and a clear secret lifecycle.

### 14.1. Immutable image

Images contain PostgreSQL binaries and packages/extensions; avoid building images containing production secrets.

### 14.2. ConfigMap/config volume

Non-secret settings can be mounted/injected via orchestration config resources. Verify file ownership/paths and reload strategy.

### 14.3. Secret volume

Passwords, private keys, and certificates can be mounted from secret resources/CSI providers. Restrict service account access and filesystem permissions.

### 14.4. Reload behavior

Updating a secret/config volume does not mean PostgreSQL automatically reloads. The controller/operator must trigger an appropriate reload or rolling restart.

### 14.5. Pod replacement

When a pod is replaced, confirm secret versions, certs, data volumes, permissions, and readiness probes are synchronized. Never put secrets into image layers or logs.

## 15. Secret lifecycle

Secrets must be managed from creation to revocation.

### 15.1. Generate

Generate secrets with a cryptographically secure random generator and sufficient length/entropy. Do not use usernames, hostnames, or guessable values.

### 15.2. Store

Store in a secret manager/vault/KMS-backed system or secure OS credential store. Encrypt at rest and restrict which principals can read them.

### 15.3. Distribute

Grant secrets only to the service identities that need them. Prefer workload identity/short-lived credentials where the platform supports them.

### 15.4. Use

Inject at runtime or mount files with strict permissions. Avoid writing secrets to command lines, environment dumps, debug logs, or crash reports.

### 15.5. Rotate/revoke

Establish owners, expiry/rotation cadences, overlap windows, rollback procedures, and how old credentials are revoked after consumers have switched.

## 16. Common Secrets in a PostgreSQL Deployment

The inventory must include both direct credentials and private keys.

| Secret | Consumer | Rotation consideration |
|---|---|---|
| Application DB password | Application/pooler | Dual credential or staged rollout |
| Replication password | Standby/subscriber | Update sender/receiver config |
| Backup credential | Backup agent | Test backup/restore access |
| Monitoring password | Monitoring agent | Update scrape/exporter secrets |
| FDW remote password | postgres_fdw mapping | Update mapping and cached connections |
| Client private key | Application/client | Renew certificate/key pair |
| Server private key | PostgreSQL server | Deploy cert/key and reload/restart as required |
| Secret-manager token | Runtime workload | Short TTL and workload identity |

### 16.1. Per-service identity

Use dedicated roles for applications, migrations, monitoring, backups, replication, and FDW. A single shared password increases the blast radius.

### 16.2. Environment separation

Do not reuse credentials between staging and production. If one environment is compromised, its credentials must not grant access to another environment.

### 16.3. Ownership

Each secret must have an owner/service, purpose, consumers, expiry, rotation procedure, and incident contact.

### 16.4. Inventory without values

Inventory secret names/IDs, versions, owners, and last rotation dates. Never include raw secret values in reports.

### 16.5. Emergency revocation

Be able to disable/revoke a compromised credential quickly, while knowing the impact on services/standbys/jobs before executing.

## 17. PostgreSQL role passwords

PostgreSQL stores password verifiers in system catalogs; plaintext passwords should not be kept in application configuration.

### 17.1. SCRAM-SHA-256

SCRAM-SHA-256 is the modern password authentication method recommended instead of MD5 in supported deployments.

### 17.2. Password encryption setting

~~~sql
SHOW password_encryption;
~~~

Set password_encryption='scram-sha-256' before setting/changing passwords for new roles.

### 17.3. Creating a role

~~~sql
CREATE ROLE app_orders
LOGIN
NOSUPERUSER
NOCREATEDB
NOCREATEROLE;
~~~

### 17.4. Setting passwords safely

Use the psql command \password to avoid typing plaintext passwords directly into SQL command history in an easily exposed manner. Follow your organization's secret manager and audit processes.

### 17.5. Existing MD5 verifiers

Changing password_encryption does not automatically convert old verifiers. Passwords must be rotated/reset to generate SCRAM verifiers, and the pg_hba.conf authentication method updated per the rollout plan.

## 18. pg_hba.conf and authentication policy

pg_hba.conf determines authentication methods by connection type, database, role, and client address.

~~~conf
# Local Unix socket example
local   all       all                         scram-sha-256

# Encrypted TCP clients
hostssl appdb     app_orders  10.20.0.0/16     scram-sha-256

# Reject unencrypted TCP for this database
hostnossl appdb   all         0.0.0.0/0        reject
~~~

### 18.1. First matching rule

PostgreSQL uses the first matching rule. If authentication fails, it does not fall through to subsequent rules; entry ordering is critical.

### 18.2. hostssl

hostssl matches only TCP/IP connections using SSL/TLS. It does not force all cluster connections to use TLS if other host/local rules allow them.

### 18.3. hostnossl

hostnossl matches TCP connections not using SSL. Reject rules can be used to forbid plaintext for specific databases/subnets.

### 18.4. CIDR scope

Restrict source ranges to application subnets, bastions, monitoring, or replication networks. Avoid opening 0.0.0.0/0 without a clear justification/policy.

### 18.5. Reload and inspect

After editing pg_hba.conf, reload and inspect pg_hba_file_rules to catch parse errors or unexpected entries.

~~~sql
SELECT
    line_number,
    type,
    database,
    user_name,
    address,
    auth_method,
    error
FROM pg_hba_file_rules
ORDER BY line_number;
~~~

## 19. Server-side TLS

TLS on PostgreSQL protects network traffic between client and server and can provide server identity.

### 19.1. Enabling SSL

~~~conf
ssl = on
~~~

This parameter typically requires a server restart when changing from off to on or vice versa.

### 19.2. Server certificate

ssl_cert_file points to the PEM certificate chain/server certificate. The certificate must include a Subject Alternative Name (SAN) matching the hostnames clients use.

### 19.3. Private key

ssl_key_file points to the corresponding private key. Protect the file from unnecessary users; on Unix-like systems this usually means owner postgres and mode 0600.

### 19.4. Client CA

ssl_ca_file can specify the CA used to verify client certificates when server authentication requires a client cert. It does not replace the client trusting the server's CA.

### 19.5. TLS protocol

Use ssl_min_protocol_version and a certificate/cipher policy matching the security baseline. Do not enable obsolete protocols just to support unmaintained clients.


## 20. Client-side TLS verification

Clients must verify the server certificate to prevent connecting to the wrong server or man-in-the-middle attacks.

### 20.1. sslmode

libpq provides sslmode values such as disable, allow, prefer, require, verify-ca, and verify-full. Production clients should use verify-full whenever possible.

### 20.2. verify-ca

The client verifies the certificate chain against a trusted CA but does not perform full hostname identity verification like verify-full.

### 20.3. verify-full

The client verifies the certificate chain and checks that the hostname/IP it connects to matches the certificate SAN. This is the strong choice for server identity verification.

### 20.4. sslrootcert

Specifies the CA certificate bundle trusted by the client. Protect the CA source and distribute only approved trusted roots.

### 20.5. Hostname consistency

Use a DNS hostname present in the SAN. Connecting by IP or an alias missing from the certificate can fail verify-full; do not disable verification to mask hostname mismatches.

## 21. Client certificates and mutual TLS

Mutual TLS (mTLS) adds client certificate authentication. The server verifies the client certificate against a CA trust policy.

### 21.1. Client certificate

The client holds its own certificate and private key. The certificate needs an identity/subject aligned with the role mapping policy.

### 21.2. Server trust

The server uses ssl_ca_file to trust the CA issuing client certificates. The CA should be scoped according to PKI policy.

### 21.3. pg_hba cert method

~~~conf
hostssl appdb app_client 10.20.0.0/16 cert
~~~

With the cert method, PostgreSQL verifies the client certificate and matches the certificate identity against the database role or an identity mapping.

### 21.4. clientcert verification option

Client certificate validation can be required alongside another authentication method using clientcert=verify-ca or verify-full on a hostssl rule, depending on version support.

### 21.5. pg_ident mapping

If the certificate CN does not match the role name, use pg_ident.conf to map the external identity to a PostgreSQL role and reference the map in the pg_hba rule.

## 22. Distinguishing Server Authentication and Client Authentication

The two verification directions answer different questions.

| Direction | Mechanism | Question |
|---|---|---|
| Client verifies server | sslmode=verify-full, sslrootcert | Am I connecting to the right PostgreSQL server? |
| Server verifies client | ssl_ca_file, clientcert/cert, pg_ident | Does this client have a trusted identity? |
| Password authentication | SCRAM-SHA-256 | Does the client know a valid credential? |
| Network admission | pg_hba.conf | Is the connection source/database/role permitted? |

### 22.1. TLS does not automatically grant SQL privileges

TLS verifies/protects the channel. PostgreSQL role privileges, schema/table grants, and RLS still determine which data the client can access.

### 22.2. Passwords over TLS

SCRAM protects the password authentication protocol; TLS continues to protect traffic/queries/results and verifies server identity when the client uses verify-full.

### 22.3. Certificates do not replace role privileges

A client certificate authenticates identity per the rule, but that role still needs CONNECT and object privileges.

### 22.4. Network controls

Firewalls/security groups and pg_hba.conf still need clear policies. TLS does not replace network segmentation.

### 22.5. Layered policy

Combine network admission, TLS identity, SCRAM/cert authentication, least-privilege roles, and SQL authorization.

## 23. Configuring libpq clients

libpq clients such as psql, applications, and many drivers support TLS parameters.

~~~bash
psql "host=db.prod.example.internal port=5432 dbname=appdb user=app_orders sslmode=verify-full sslrootcert=/run/secrets/db-ca.pem"
~~~

### 23.1. sslmode

Set verify-full to require encryption and validate the hostname/certificate chain.

### 23.2. sslrootcert

Path to the trusted CA bundle. Update the CA bundle per rotation policy before the server switches to a new CA when an overlap window is used.

### 23.3. sslcert and sslkey

Specify the client certificate/private key if the server requires certificate authentication or client identity.

### 23.4. Connection URI

A connection URI can carry host, port, dbname, user, and SSL parameters. Never embed passwords in URIs that get logged/monitored.

### 23.5. Service file

A libpq service file can store non-sensitive connection parameters and reference a separate passfile. Restrict file permissions per OS account.

## 24. Protecting password files and client credentials

Database passwords should not be passed on the command line or exposed in process listings/logs.

### 24.1. .pgpass

On Unix-like systems, libpq can read the default password file ~/.pgpass. The file must have strict permissions, typically chmod 0600.

### 24.2. PGPASSFILE

A different file can be specified via PGPASSFILE to isolate credentials by service/environment.

### 24.3. Format and escaping

Each line consists of host:port:database:username:password. Colons and backslashes within fields must be escaped according to pgpass rules.

### 24.4. PGPASSWORD caution

The PGPASSWORD environment variable can be exposed via process environment/diagnostics on some platforms. Prefer a passfile or a secure secret injection mechanism.

### 24.5. Service identity

The passfile/private key must be readable only by the exact OS account running the PostgreSQL client/agent. Avoid broad read permissions or mounting the same secret into all containers.

## 25. Application connection configuration

Applications should obtain connection settings and credentials from runtime configuration/secret providers.

### 25.1. Separate parameters

Keep host, port, database, user, SSL mode, and timeouts as validatable configuration. Inject the secret password separately.

### 25.2. No secret in source

Do not commit DSNs with passwords, production .env files, private keys, or client certificates to Git.

### 25.3. No secret in logs

Redact passwords, tokens, full connection strings, and sensitive certificate paths from error reports/telemetry.

### 25.4. Connection pool

Poolers/application pools need correct TLS settings for each hop. Client-to-pooler TLS does not automatically guarantee pooler-to-PostgreSQL TLS.

### 25.5. Fail closed

If production requires TLS verification, CA/hostname errors must fail the connection. Never automatically fall back to plaintext/prefer to work around an outage.

## 26. TLS with connection poolers

A pooler can establish two separate TLS connections: frontend client to pooler, and backend pooler to PostgreSQL.

### 26.1. Frontend TLS

The application verifies the pooler certificate. The pooler holds a server cert/key and may require a client cert per policy.

### 26.2. Backend TLS

The pooler verifies the PostgreSQL server certificate using CA/hostname policy and uses a client cert if the remote PostgreSQL server requires it.

### 26.3. Authentication mapping

A pooler may authenticate clients and then use different backend credentials to connect to PostgreSQL. Clearly define the trust boundary and audit identity.

### 26.4. Certificate rotation

Rotate frontend/backend certs per hop, verify reload semantics, and recycle pool connections.

### 26.5. End-to-end identity

If end-to-end client identity is needed, explicitly design how identity is propagated/delegated and audited. Do not assume PostgreSQL sees the application's certificate when an intermediary pooler is present.

## 27. TLS for replication and logical subscribers

Replication connections are database connections and require the same TLS/authentication standards.

### 27.1. Physical standby

primary_conninfo can contain host, user, passfile, sslmode, and sslrootcert. Do not write plaintext passwords in configuration when a passfile/secret mechanism can be used.

### 27.2. Replication role

Create a dedicated REPLICATION/LOGIN role, restrict source networks, and avoid superuser if unnecessary.

### 27.3. pg_hba replication rule

~~~conf
hostssl replication repl_user 10.30.0.0/16 scram-sha-256
~~~

### 27.4. Logical replication

Publisher/subscriber connection strings also require SSL modes, CA trust, credential rotation, and pg_hba policies. DDL/data replication does not replace certificate management.

### 27.5. Failover readiness

Standby/DR nodes need sufficient CA bundles, passfiles/certificates, and network policies to continue connecting after promotion/repointing.

## 28. TLS for postgres_fdw and integrations

Every outbound database connection must verify its endpoint and follow secret lifecycle management.

### 28.1. postgres_fdw server options

sslmode, sslrootcert, sslcert, sslkey, and appropriate libpq options can be configured in foreign server/user mapping options depending on option support.

### 28.2. Per-user mapping

Remote passwords belong to user mappings; restrict who can inspect/manage mapping options and use least-privilege remote roles.

### 28.3. Remote server certificate

Use verify-full with a hostname present in the SAN and the correct CA bundle. Do not treat verify-ca as equivalent to hostname verification.

### 28.4. Rotation

Update credentials/certificates, test new connections, and manage cached FDW connections. Existing connections may continue using already established sessions.

### 28.5. Other integrations

Backup tools, monitoring exporters, ETL workers, and migration runners also need their own TLS/secret configuration; do not assume they inherit the PostgreSQL server's client settings.

## 29. Certificate lifecycle

Certificates must be managed from issuance through revocation.

### 29.1. Certificate request

Define subject/SAN, key algorithm/size, intended usage, validity period, and CA policy.

### 29.2. Issuance

Use an internal PKI or suitable public CA. Server certificates must have SANs matching the DNS names clients use.

### 29.3. Private key handling

Generate/store private keys in protected paths or KMS/HSM-backed workflows if supported by the platform. Never send private keys via chat/email or commit them to repositories.

### 29.4. Expiry monitoring

Track notBefore/notAfter, chain expiry, and renewal lead times. Alert early enough to test/deploy new certificates.

### 29.5. Revocation

Have a procedure to revoke compromised/obsolete certificates via CA/CRL or identity policy. Test client/server behavior when a cert is revoked.


## 30. Zero-outage certificate rotation

Rotation should use an overlap between old and new trust so clients/servers have time to transition.

### 30.1. Issue a new certificate

Generate a new certificate/key from an approved CA, verifying SAN, chain, validity, and key permissions before deployment.

### 30.2. Trust overlap

If changing CAs, distribute a CA bundle containing both the old and new CAs to clients before the server switches certificates. Remove the old CA only after all clients have migrated.

### 30.3. Deploy server certificate

Install the new certificate/private key in protected paths. Check owner, permissions, chain order, and file readability.

### 30.4. Reload/restart per context

Check pg_settings.context for SSL parameters. Reload or restart as required; then open new connections and confirm the new certificate is in use.

### 30.5. Drain old sessions

Existing TLS sessions negotiated with the old certificate do not switch certificates mid-connection. Recycle pool connections on schedule and confirm all clients have switched.

## 31. Password rotation for application roles

Password rotation must account for clients, poolers, scheduled jobs, and existing sessions.

### 31.1. Inventory consumers

List applications, poolers, migration runners, monitoring, batch jobs, and admin tools using the credential.

### 31.2. Same-role rotation

Changing a role's password affects authentication for new connections using the new credential. Existing sessions generally continue running until they disconnect.

### 31.3. Overlap strategy

A PostgreSQL role holds only one active password verifier at a time. If credential overlap is needed, create a new login role with equivalent memberships, migrate consumers, and then disable/revoke the old login role.

### 31.4. Update and reconnect

Update the secret in consumers, refresh pool connections, and confirm new connections succeed. Do not test only with an admin psql session.

### 31.5. Revoke old credential

After confirming all consumers have switched, disable/drop the old login role or revoke the credential per plan. Drain old sessions and audit authentication failures.

## 32. Rotation for replication, FDW, and service accounts

Integrations often hold long-lived connections or cache credentials.

### 32.1. Replication credentials

Update secrets in standby/subscriber connection configurations and verify receiver reconnection. Keep replication roles at least privilege.

### 32.2. postgres_fdw mappings

Use ALTER USER MAPPING to update remote credentials. Determine whether cached connections need to be disconnected/recycled and test queries using the actual local role.

### 32.3. Backup/monitoring agents

Update secrets in agent/runtime config, test backup/restore or scrape/query access, and then revoke the old credential.

### 32.4. Scheduled jobs

Jobs may run infrequently and not surface errors immediately after rotation. Trigger a controlled test run before revoking the old credential.

### 32.5. Rotation evidence

Record secret version, updated consumers, test results, old credential revocation time, and exceptions. Never record raw secrets in evidence.

## 33. Client certificate rotation

Client certificates can be rotated independently of server certificates.

### 33.1. Issue client identity

Issue a new certificate for the workload identity with the appropriate subject/SAN and extended key usage.

### 33.2. Install key/certificate

Update the certificate/private key on the client host/container, ensuring proper ownership/permissions and CA chain.

### 33.3. Server trust

Ensure PostgreSQL trusts the new CA via ssl_ca_file and pg_hba cert/clientcert policy. Reload according to configuration context.

### 33.4. Test new connections

Open a new connection using the new client certificate and verify authentication and identity mapping via pg_ident if applicable.

### 33.5. Revoke old certificate

Once all clients have transitioned, update CRL/identity policy if needed and revoke the old certificate. Monitor for errors from clients still using the old certificate.

## 34. CA rotation and trust bundle

CA rotation is more complex than replacing a leaf certificate because it affects all clients.

### 34.1. Add new CA first

Distribute a trust bundle containing both the old and new CAs to clients, poolers, FDW hosts, replication nodes, and monitoring agents.

### 34.2. Verify trust deployment

Verify the fingerprint of the deployed CA bundle in each environment/node. Avoid having unplanned bundle mismatches.

### 34.3. Switch issuer

Issue/deploy server/client certificates from the new CA in batches. Maintain overlap for rollback if necessary.

### 34.4. Remove old CA

Remove the old CA only after inventory confirms no active certificates signed by that CA remain.

### 34.5. Revocation/incident

If the old CA is compromised, overlap may be unsafe; execute an emergency revocation plan and accept reconnection/availability impact per incident policy.

## 35. TLS observability in PostgreSQL

Verify that actual connections use TLS and the expected protocol/cipher.

~~~sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.client_addr,
    s.ssl,
    s.version,
    s.cipher,
    s.bits,
    s.client_dn,
    s.client_serial
FROM pg_stat_activity AS a
JOIN pg_stat_ssl AS s USING (pid)
WHERE a.backend_type = 'client backend'
ORDER BY a.application_name, a.usename;
~~~

### 35.1. ssl

Indicates whether the connection is using SSL/TLS.

### 35.2. version and cipher

Displays the negotiated TLS protocol/cipher for the connection. Compare against the environment's security baseline.

### 35.3. client_dn and client_serial

May provide client certificate details if a client certificate was used. Not every password-authenticated TLS connection has a client certificate.

### 35.4. Session sampling

pg_stat_ssl reflects current connections. Inspect while application traffic is active and after pool recycling to verify new clients.

### 35.5. Client-side verification

Server views prove TLS is in use, but clients must independently verify server identity via verify-full/CA policy. Both sides require separate evidence.

## 36. Testing connections from psql and libpq

Client tools help verify the TLS/authentication path.

### 36.1. Connection details

In psql, use \conninfo to view connection parameters and the SSL status visible to the client.

### 36.2. Explicit SSL mode

Use a connection string with sslmode=verify-full and sslrootcert pointing to the approved CA bundle.

### 36.3. Negative hostname test

In a test environment, test a hostname that does not match the certificate to confirm verify-full rejects the connection.

### 36.4. Negative CA test

Test an untrusted CA in a lab and confirm the client rejects the handshake/verification.

### 36.5. No plaintext fallback

Verify client configuration does not silently fall back to disable/allow/prefer when TLS verification fails if production policy requires mandatory TLS.

## 37. Logging and auditing for configuration/security changes

Changes to configuration, roles, and certificates require records for investigation and compliance.

### 37.1. Change identity

Record the person/service executing the change, ticket/change ID, environment, timestamp, and approval.

### 37.2. Configuration diff

Store a diff of non-secret settings before/after, effective source, and pending_restart. Redact sensitive paths/values as needed.

### 37.3. Role changes

Audit CREATE/ALTER/DROP ROLE, grants, memberships, password rotation, and authentication failures per policy.

### 37.4. Certificate events

Record certificate serial/fingerprint, issuer, validity, deployment nodes, reload/restart results, and old certificate retirement.

### 37.5. Logs redaction

Never log passwords, private key contents, tokens, or full connection strings containing credentials. Check application logs, CI output, and support bundles.

## 38. Environment parity and test matrix

Test authentication/configuration across every connection path and environment.

| Test | Development | CI/Test | Staging | Production/DR |
|---|---|---|---|---|
| Correct config source | Yes | Yes | Yes | Yes |
| SCRAM authentication | Optional | Yes | Yes | Yes |
| TLS encryption | Recommended | Yes | Mandatory per policy | Mandatory per policy |
| verify-full | Recommended | Yes | Yes | Yes |
| Client certificate | When needed | Lab test | If production uses | If production uses |
| Secret rotation | Test flow | Automated test | Rehearsal | Controlled change |
| Certificate expiry alert | Test | Test | Yes | Yes |
| Reload/restart behavior | Yes | Yes | Yes | Change-controlled |
| Failover/DR credentials | Not required | Simulated | Rehearsal | Yes |

### 38.1. Same security baseline

Staging should enforce the same authentication/TLS policy as production, even though certificates and credentials differ.

### 38.2. Environment-specific identities

Each environment has its own DB roles, passwords, client certificates, and CA trust per policy. Never copy production secrets to lower environments.

### 38.3. Negative tests

Test wrong passwords, wrong CAs, wrong hostnames, expired certs, unauthorized roles, and plaintext connection rejection.

### 38.4. Restart/reload tests

Confirm the service manager/operator performs reloads/restarts properly and readiness checks do not report healthy before the server accepts connections per policy.

### 38.5. DR tests

Test secret manager availability, CA trust, certificate expiry, and connection strings when failing over to the DR endpoint.

## 39. Managed PostgreSQL services

Managed databases may restrict filesystem access and configuration methods.

### 39.1. Parameter groups

Some settings are configured via provider parameter groups instead of editing postgresql.conf directly.

### 39.2. Certificate bundles

Providers may supply CA bundles and require clients to update when endpoint certificates/CAs change.

### 39.3. Secret integrations

Use the provider's secret manager/workload identity when supported. Do not assume the database service automatically injects application credentials.

### 39.4. Authentication features

Client certificate, IAM/token authentication, and SCRAM support vary by provider/version. Check service documentation and test the actual endpoint.

### 39.5. Provider rotation notices

Monitor maintenance/CA rotation notices and deadlines. Rehearse trust bundle updates before the date the provider enforces the new CA.

## 40. Troubleshooting: configuration not taking effect

### 40.1. Effective value

Use SHOW and pg_settings to determine runtime value, source, context, and pending_restart.

### 40.2. File parsing

Use pg_file_settings to find errors, duplicate entries, and sourcefile/sourceline.

### 40.3. Include order

Check include/include_dir and file precedence. A setting in a file read later can override an earlier value.

### 40.4. Restart requirement

If pending_restart=true or context=postmaster, reload is insufficient. Schedule an appropriate restart/HA switchover.

### 40.5. Control plane

With an operator/managed service, recognize that the source of truth is the custom resource/parameter group. Manual file edits may be reconciled/overwritten.


## 30. Zero-outage certificate rotation

Rotation should use an overlap between old and new trust so clients/servers have time to transition.

### 30.1. Issue a new certificate

Generate a new certificate/key from an approved CA, verifying SAN, chain, validity, and key permissions before deployment.

### 30.2. Trust overlap

If changing CAs, distribute a CA bundle containing both the old and new CAs to clients before the server switches certificates. Remove the old CA only after all clients have migrated.

### 30.3. Deploy server certificate

Install the new certificate/private key in protected paths. Check owner, permissions, chain order, and file readability.

### 30.4. Reload/restart per context

Check pg_settings.context for SSL parameters. Reload or restart as required; then open new connections and confirm the new certificate is in use.

### 30.5. Drain old sessions

Existing TLS sessions negotiated with the old certificate do not switch certificates mid-connection. Recycle pool connections on schedule and confirm all clients have switched.

## 31. Password rotation for application roles

Password rotation must account for clients, poolers, scheduled jobs, and existing sessions.

### 31.1. Inventory consumers

List applications, poolers, migration runners, monitoring, batch jobs, and admin tools using the credential.

### 31.2. Same-role rotation

Changing a role's password affects authentication for new connections using the new credential. Existing sessions generally continue running until they disconnect.

### 31.3. Overlap strategy

A PostgreSQL role holds only one active password verifier at a time. If credential overlap is needed, create a new login role with equivalent memberships, migrate consumers, and then disable/revoke the old login role.

### 31.4. Update and reconnect

Update the secret in consumers, refresh pool connections, and confirm new connections succeed. Do not test only with an admin psql session.

### 31.5. Revoke old credential

After confirming all consumers have switched, disable/drop the old login role or revoke the credential per plan. Drain old sessions and audit authentication failures.

## 32. Rotation for replication, FDW, and service accounts

Integrations often hold long-lived connections or cache credentials.

### 32.1. Replication credentials

Update secrets in standby/subscriber connection configurations and verify receiver reconnection. Keep replication roles at least privilege.

### 32.2. postgres_fdw mappings

Use ALTER USER MAPPING to update remote credentials. Determine whether cached connections need to be disconnected/recycled and test queries using the actual local role.

### 32.3. Backup/monitoring agents

Update secrets in agent/runtime config, test backup/restore or scrape/query access, and then revoke the old credential.

### 32.4. Scheduled jobs

Jobs may run infrequently and not surface errors immediately after rotation. Trigger a controlled test run before revoking the old credential.

### 32.5. Rotation evidence

Record secret version, updated consumers, test results, old credential revocation time, and exceptions. Never record raw secrets in evidence.

## 33. Client certificate rotation

Client certificates can be rotated independently of server certificates.

### 33.1. Issue client identity

Issue a new certificate for the workload identity with the appropriate subject/SAN and extended key usage.

### 33.2. Install key/certificate

Update the certificate/private key on the client host/container, ensuring proper ownership/permissions and CA chain.

### 33.3. Server trust

Ensure PostgreSQL trusts the new CA via ssl_ca_file and pg_hba cert/clientcert policy. Reload according to configuration context.

### 33.4. Test new connections

Open a new connection using the new client certificate and verify authentication and identity mapping via pg_ident if applicable.

### 33.5. Revoke old certificate

Once all clients have transitioned, update CRL/identity policy if needed and revoke the old certificate. Monitor for errors from clients still using the old certificate.

## 34. CA rotation and trust bundle

CA rotation is more complex than replacing a leaf certificate because it affects all clients.

### 34.1. Add new CA first

Distribute a trust bundle containing both the old and new CAs to clients, poolers, FDW hosts, replication nodes, and monitoring agents.

### 34.2. Verify trust deployment

Verify the fingerprint of the deployed CA bundle in each environment/node. Avoid having unplanned bundle mismatches.

### 34.3. Switch issuer

Issue/deploy server/client certificates from the new CA in batches. Maintain overlap for rollback if necessary.

### 34.4. Remove old CA

Remove the old CA only after inventory confirms no active certificates signed by that CA remain.

### 34.5. Revocation/incident

If the old CA is compromised, overlap may be unsafe; execute an emergency revocation plan and accept reconnection/availability impact per incident policy.

## 35. TLS observability in PostgreSQL

Verify that actual connections use TLS and the expected protocol/cipher.

~~~sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.client_addr,
    s.ssl,
    s.version,
    s.cipher,
    s.bits,
    s.client_dn,
    s.client_serial
FROM pg_stat_activity AS a
JOIN pg_stat_ssl AS s USING (pid)
WHERE a.backend_type = 'client backend'
ORDER BY a.application_name, a.usename;
~~~

### 35.1. ssl

Indicates whether the connection is using SSL/TLS.

### 35.2. version and cipher

Displays the negotiated TLS protocol/cipher for the connection. Compare against the environment's security baseline.

### 35.3. client_dn and client_serial

May provide client certificate details if a client certificate was used. Not every password-authenticated TLS connection has a client certificate.

### 35.4. Session sampling

pg_stat_ssl reflects current connections. Inspect while application traffic is active and after pool recycling to verify new clients.

### 35.5. Client-side verification

Server views prove TLS is in use, but clients must independently verify server identity via verify-full/CA policy. Both sides require separate evidence.

## 36. Testing connections from psql and libpq

Client tools help verify the TLS/authentication path.

### 36.1. Connection details

In psql, use the \conninfo command to view connection parameters and the SSL status visible to the client.

### 36.2. Explicit SSL mode

Use a connection string with sslmode=verify-full and sslrootcert pointing to the approved CA bundle.

### 36.3. Negative hostname test

In a test environment, test a hostname that does not match the certificate to confirm verify-full rejects the connection.

### 36.4. Negative CA test

Test an untrusted CA in a lab and confirm the client rejects the handshake/verification.

### 36.5. No plaintext fallback

Verify client configuration does not silently fall back to disable/allow/prefer when TLS verification fails if production policy requires mandatory TLS.

## 37. Logging and auditing for configuration/security changes

Changes to configuration, roles, and certificates require records for investigation and compliance.

### 37.1. Change identity

Record the person/service executing the change, ticket/change ID, environment, timestamp, and approval.

### 37.2. Configuration diff

Store a diff of non-secret settings before/after, effective source, and pending_restart. Redact sensitive paths/values as needed.

### 37.3. Role changes

Audit CREATE/ALTER/DROP ROLE, grants, memberships, password rotation, and authentication failures per policy.

### 37.4. Certificate events

Record certificate serial/fingerprint, issuer, validity, deployment nodes, reload/restart results, and old certificate retirement.

### 37.5. Logs redaction

Never log passwords, private key contents, tokens, or full connection strings containing credentials. Check application logs, CI output, and support bundles.

## 38. Environment parity and test matrix

Test authentication/configuration across every connection path and environment.

| Test | Development | CI/Test | Staging | Production/DR |
|---|---|---|---|---|
| Correct config source | Yes | Yes | Yes | Yes |
| SCRAM authentication | Optional | Yes | Yes | Yes |
| TLS encryption | Recommended | Yes | Mandatory per policy | Mandatory per policy |
| verify-full | Recommended | Yes | Yes | Yes |
| Client certificate | When needed | Lab test | If production uses | If production uses |
| Secret rotation | Test flow | Automated test | Rehearsal | Controlled change |
| Certificate expiry alert | Test | Test | Yes | Yes |
| Reload/restart behavior | Yes | Yes | Yes | Change-controlled |
| Failover/DR credentials | Not required | Simulated | Rehearsal | Yes |

### 38.1. Same security baseline

Staging should enforce the same authentication/TLS policy as production, even though certificates and credentials differ.

### 38.2. Environment-specific identities

Each environment has its own DB roles, passwords, client certificates, and CA trust per policy. Never copy production secrets to lower environments.

### 38.3. Negative tests

Test wrong passwords, wrong CAs, wrong hostnames, expired certs, unauthorized roles, and plaintext connection rejection.

### 38.4. Restart/reload tests

Confirm the service manager/operator performs reloads/restarts properly and readiness checks do not report healthy before the server accepts connections per policy.

### 38.5. DR tests

Test secret manager availability, CA trust, certificate expiry, and connection strings when failing over to the DR endpoint.

## 39. Managed PostgreSQL services

Managed databases may restrict filesystem access and configuration methods.

### 39.1. Parameter groups

Some settings are configured via provider parameter groups instead of editing postgresql.conf directly.

### 39.2. Certificate bundles

Providers may supply CA bundles and require clients to update when endpoint certificates/CAs change.

### 39.3. Secret integrations

Use the provider's secret manager/workload identity when supported. Do not assume the database service automatically injects application credentials.

### 39.4. Authentication features

Client certificate, IAM/token authentication, and SCRAM support vary by provider/version. Check service documentation and test the actual endpoint.

### 39.5. Provider rotation notices

Monitor maintenance/CA rotation notices and deadlines. Rehearse trust bundle updates before the date the provider enforces the new CA.


## 40. Troubleshooting: configuration not taking effect

### 40.1. Effective value

Use SHOW and pg_settings to determine runtime value, source, context, and pending_restart.

### 40.2. File parsing

Use pg_file_settings to find errors, duplicate entries, and sourcefile/sourceline.

### 40.3. Include order

Check include/include_dir and file precedence. A setting in a file read later can override an earlier value.

### 40.4. Restart requirement

If pending_restart=true or context=postmaster, reload is insufficient. Schedule an appropriate restart/HA switchover.

### 40.5. Control plane

With an operator/managed service, recognize that the source of truth is the custom resource/parameter group. Manual file edits may be reconciled/overwritten.

## 41. Troubleshooting: TLS handshake or certificate verification failure

### 41.1. Certificate expired/not yet valid

Check notBefore/notAfter, clock synchronization on client/server, and the intermediate certificate chain.

### 41.2. Hostname mismatch

Ensure the hostname in the connection string is in the server certificate's SAN. Change the endpoint alias or issue a certificate with the right SAN; do not downgrade sslmode to bypass mismatches.

### 41.3. Unknown CA

Check whether the client's sslrootcert has the correct CA bundle and required chain. Do not arbitrarily add CAs from unverified certificate sources.

### 41.4. Key permissions

PostgreSQL may reject a private key with overly broad permissions or an inappropriate owner. Verify service account, ownership, and OS file mode.

### 41.5. Protocol/cipher mismatch

Compare server/client TLS capabilities and ssl_min_protocol_version/cipher policy. Upgrade the client library rather than lowering the security baseline arbitrarily.

## 42. Troubleshooting: client certificate rejected

### 42.1. Client certificate chain

Confirm the certificate is signed by a CA trusted by the server via ssl_ca_file and that the chain is complete.

### 42.2. Certificate identity

Check CN/subject mapping, pg_ident.conf map, and role name. Identity mismatches can cause cert authentication to fail.

### 42.3. pg_hba rule order

Check the first rule matching the connection. An earlier host/hostssl rule may select a different auth method than expected.

### 42.4. Client certificate validity

Check expiry, key usage/extended key usage, and CRL/revocation state per PKI policy.

### 42.5. Logs

Read PostgreSQL server logs to distinguish no matching HBA rule, CA verification, certificate identity, and SQL privilege errors.

## 43. Troubleshooting: SCRAM authentication failed

### 43.1. Password verifier

Confirm the password was set/reset after password_encryption was switched to scram-sha-256. The new setting does not automatically convert old verifiers.

### 43.2. Client driver support

Verify the libpq/driver version supports SCRAM-SHA-256. Upgrade drivers before enforcing the production policy if legacy clients exist.

### 43.3. Role/login state

Check role LOGIN, VALID UNTIL, and account state. Confirm the application uses the right role/database.

### 43.4. Mapping/secret version

Compare the injected secret version against the current password in PostgreSQL. Check for stale pooler/app secrets.

### 43.5. HBA match

Identify the exact pg_hba rule and authentication method applied. Do not edit a rule that does not match the source connection.

## 44. Troubleshooting: app still using old credential/certificate

### 44.1. Connection pool

Pools can hold existing sessions after rotation. Drain/recycle connections according to policy.

### 44.2. Cached credentials

A process may read secrets only at startup. Reload/restart the application or secret watcher per design.

### 44.3. PostgreSQL backend sessions

Changing a password does not automatically disconnect currently authenticated sessions. Identify old sessions and terminate/drain them in a controlled manner if needed.

### 44.4. FDW cached connections

postgres_fdw can keep remote connections cached inside a backend. Test reconnect/disconnect behavior after user mapping rotation.

### 44.5. Consumer inventory

Locate cron jobs, workers, exporters, and failover nodes that have not been updated. Old credentials should only be revoked after confirming all consumers.

## 45. Troubleshooting: pg_hba.conf reload error

### 45.1. pg_hba_file_rules

Inspect the error column, line_number, type, database, user_name, address, and auth_method.

### 45.2. Syntax

Check CIDRs, quoting, method options, map names, and field separators. A single syntax error can prevent entries from being parsed.

### 45.3. First match

Check rule ordering. The first matching rule is used; PostgreSQL does not fall back to the next rule when authentication fails.

### 45.4. Reload confirmation

Call pg_reload_conf() and inspect server logs/pg_hba_file_rules. A true return value from the function only indicates the signal was sent.

### 45.5. Existing sessions

HBA changes apply to new connection attempts; they do not drop already authenticated sessions. Test with a new connection from the actual source network.

## 46. Example: PostgreSQL configuration by environment

Example illustrating common differences. Values must be tuned to capacity and security policies.

| Setting | Development | Staging | Production |
|---|---|---|---|
| max_connections | Small | Close to production topology | Per pool/capacity budget |
| log_min_duration_statement | Can be low for debugging | Per test policy | Per observability budget |
| ssl | Per local policy | On | On |
| Authentication | SCRAM | SCRAM/TLS | SCRAM/TLS or mTLS |
| sslmode client | verify-full when testing TLS | verify-full | verify-full |
| Backup | Disposable/local | Rehearsal | Policy/RPO/RTO |
| Secrets | Local-only | Staging secret scope | Central secret manager |
| Certificates | Test CA | Staging CA | Approved production PKI |

### 46.1. Do not copy production config verbatim to dev

Production values may not fit dev resources and may expose internal topology details. Use the same schema/template with separate values.

### 46.2. Staging as security rehearsal

Staging should mirror auth/TLS, rotation, HBA, pooler, and failover behavior. If staging uses trust-all while production uses verify-full, certificate errors will only surface at release time.

### 46.3. Production baseline

Store approved config artifacts, parameter sources, secret references, and certificate fingerprints.

### 46.4. DR parity

DR requires values tailored to DR topology, but with the same security controls, roles, trust chain, and secret availability.

### 46.5. Change record

Every deviation requires an owner, reason, expiry/review date, and rollback path.

## 47. Example: deploying server TLS and SCRAM

The commands below illustrate the flow. Replace file paths, role names, and addresses for your environment.

### 47.1. Server configuration

~~~conf
ssl = on
ssl_cert_file = 'server.crt'
ssl_key_file = 'server.key'
ssl_min_protocol_version = 'TLSv1.2'
password_encryption = 'scram-sha-256'
~~~

Ensure the certificate SAN matches the hostname and the private key has appropriate permissions.

### 47.2. HBA policy

~~~conf
hostssl appdb app_orders 10.20.0.0/16 scram-sha-256
hostnossl appdb all       10.20.0.0/16 reject
~~~

Rule order and other rules must be reviewed in the context of the full file.

### 47.3. Role

~~~sql
CREATE ROLE app_orders
LOGIN
NOSUPERUSER
NOCREATEDB
NOCREATEROLE;
~~~

Set the password via a secure workflow/psql \password and grant the required database/schema/table privileges.

### 47.4. Apply

Check pg_file_settings and pg_hba_file_rules. Reload reloadable settings; restart if context requires it.

### 47.5. Client test

~~~bash
psql "host=db.prod.example.internal dbname=appdb user=app_orders sslmode=verify-full sslrootcert=/run/secrets/db-ca.pem"
~~~

Verify \conninfo, pg_stat_ssl, and application logs with a new connection.

## 48. Example: password rotation with role overlap

An application needs to rotate credentials without changing the password verifier of the same role at a single instant.

### 48.1. Create a group role

~~~sql
CREATE ROLE app_orders_privileges NOLOGIN;
GRANT CONNECT ON DATABASE appdb TO app_orders_privileges;
GRANT USAGE ON SCHEMA app TO app_orders_privileges;
GRANT SELECT, INSERT, UPDATE ON app.orders TO app_orders_privileges;
~~~

### 48.2. Create a new login identity

~~~sql
CREATE ROLE app_orders_v2 LOGIN;
GRANT app_orders_privileges TO app_orders_v2;
~~~

Set a separate password for app_orders_v2 through a secure channel.

### 48.3. Deploy consumer

Update a batch of application instances/poolers to the new login role. Test authentication, grants, RLS, connection pooling, and query behavior.

### 48.4. Migrate remaining consumers

Switch scheduled jobs, workers, monitoring, and failover processes. Check sessions/connection logs to confirm no old login remains.

### 48.5. Revoke old login

After verifying all consumers, disable/drop the old login role per policy. Retain an audit record of the rotation timestamp and outcome.


## 49. Example: certificate rotation

### 49.1. Check expiry

Record the fingerprint, issuer, SAN, and expiry of the certificate currently in use. Identify all clients trusting the current CA.

### 49.2. Distribute trust

If the CA changes, deploy the overlapping CA bundle to applications, poolers, FDW hosts, replication nodes, and monitoring first.

### 49.3. Deploy new server cert

Install the new server certificate/key with the correct SAN, verifying chain and permissions.

### 49.4. Reload/restart and verify

Apply per pg_settings.context, open new connections with verify-full, and confirm pg_stat_ssl/client verification.

### 49.5. Drain old sessions and retire

Recycle pools, confirm no connections still use the old certificate, and then remove the old trust/certificate per the rotation plan.

## 50. Configuration and secret deployment checklist

A deployment change should follow auditable and reversible steps.

1. Identify environment, owner, change ID, and objective.
2. Capture the current config baseline/effective values.
3. Update templates/values in the source of truth; never write secret values into the repository.
4. Retrieve secrets/certificates from an approved manager/PKI.
5. Validate syntax, required settings, paths, file ownership, and expiry.
6. Render config and inspect the redacted diff.
7. Test in staging using actual application/replication/pooler clients.
8. Deploy per node/role or via operator/parameter group.
9. Reload/restart per context and verify pending_restart.
10. Test new connections, auth/TLS identity, permissions, and application health.
11. Monitor errors/latency/connection churn and replication.
12. Revoke old secrets/certs after consumer inventory confirms migration.
13. Store evidence and update inventory/expiry/rotation schedules.

## 51. Common Mistakes

1. Using completely different config files per environment without a shared baseline.
2. Reading only postgresql.conf while ignoring postgresql.auto.conf and include files.
3. Failing to check pg_settings.source/sourcefile/pending_restart.
4. Using ALTER SYSTEM outside the source of truth without reconciling.
5. Assuming pg_reload_conf applies settings that require a restart.
6. Assuming reloading pg_hba.conf disconnects already authenticated sessions.
7. Putting passwords/private keys into Git, images, command lines, or logs.
8. Using PGPASSWORD in environments with process environment visibility.
9. Reusing database passwords across development/staging/production.
10. Using one shared login for applications, backups, monitoring, and replication.
11. Switching pg_hba to SCRAM before checking client driver support/verifiers.
12. Enabling TLS while clients only use prefer/do not verify hostnames.
13. Using verify-ca and assuming it is equivalent to verify-full.
14. Missing SANs on certificates or mismatched hostnames in connection strings.
15. Leaving overly permissive file permissions on private keys.
16. Configuring client TLS while forgetting pooler backend connections.
17. Rotating passwords while forgetting pool connections and scheduled jobs.
18. Rotating a CA/certificate without trust overlap or a rollback plan.
19. Testing only with an admin connection instead of the real application role.
20. Failing to prepare secrets/certificates on standby/DR.
21. Failing to monitor expiry/rotation deadlines.
22. Skipping negative tests for TLS/authentication failures.

## 52. Practice Exercises

### Exercise 1 — Classification

Distinguish between configuration, secret, and trust material.

**Answer:** Configuration controls behavior; secrets authenticate/grant access; trust material defines trusted certificate/key identities.

### Exercise 2 — Environment

Why does staging need a security policy close to production?

**Answer:** To detect authentication/TLS/rotation errors before release.

### Exercise 3 — Configuration files

Which file does ALTER SYSTEM write to?

**Answer:** postgresql.auto.conf in the data directory.

### Exercise 4 — Effective setting

Which view shows sourcefile and pending_restart?

**Answer:** pg_settings.

### Exercise 5 — File parse

Which view helps inspect configuration entries/errors?

**Answer:** pg_file_settings.

### Exercise 6 — Reload

Does pg_reload_conf restart the server?

**Answer:** No; it requests a configuration reload.

### Exercise 7 — Parameter context

What does a setting with context=postmaster require?

**Answer:** Restarting PostgreSQL to apply the change.

### Exercise 8 — Role defaults

When does ALTER ROLE SET take effect?

**Answer:** When new sessions for that role are started, unless overridden.

### Exercise 9 — Secrets

Why must passwords not be stored in Git?

**Answer:** Repository history/clones/logs make secrets hard to revoke and widen the blast radius.

### Exercise 10 — SCRAM

Does password_encryption='scram-sha-256' automatically convert old password verifiers?

**Answer:** No; passwords must be reset/rotated.

### Exercise 11 — HBA

Which pg_hba.conf rule does PostgreSQL use?

**Answer:** The first rule matching the connection; authentication failure does not advance to subsequent rules.

### Exercise 12 — hostssl

Which connections does hostssl match?

**Answer:** TCP/IP connections using SSL/TLS.

### Exercise 13 — Server TLS

What do ssl_cert_file and ssl_key_file contain?

**Answer:** The server certificate and its corresponding private key.

### Exercise 14 — Client trust

What is sslrootcert used for in libpq?

**Answer:** Providing the trusted CA bundle to verify the server certificate.

### Exercise 15 — verify-full

What extra check does verify-full perform compared to verify-ca?

**Answer:** That the endpoint hostname/IP matches the certificate identity.

### Exercise 16 — mTLS

What does the server need to verify a client certificate?

**Answer:** A trusted client CA, pg_hba cert/clientcert policy, and identity mapping if needed.

### Exercise 17 — TLS and SQL privileges

Does TLS grant SELECT privileges on tables?

**Answer:** No; SQL privileges/RLS still control access.

### Exercise 18 — Existing sessions

Does changing a password automatically disconnect existing sessions?

**Answer:** No; already authenticated connections typically continue until disconnected.

### Exercise 19 — Rotation overlap

Can a single PostgreSQL role normally hold two active password verifiers simultaneously?

**Answer:** No; use separate role overlap if zero-downtime credential transition is required.

### Exercise 20 — Certificate rotation

Why must a new CA be distributed before changing the server certificate?

**Answer:** Clients must trust the new CA before receiving a certificate signed by that CA.

### Exercise 21 — Pooler

Does client-to-pooler TLS guarantee pooler-to-PostgreSQL is encrypted?

**Answer:** No; each network hop requires its own TLS policy.

### Exercise 22 — Replication

Can primary_conninfo use passfile/sslrootcert?

**Answer:** Yes, according to libpq connection parameter support.

### Exercise 23 — pg_stat_ssl

What information does this view provide?

**Answer:** TLS state/protocol/cipher and client certificate metadata for current connections.

### Exercise 24 — HBA reload

Do HBA changes affect already open connections?

**Answer:** No; they apply to new connection attempts.

### Exercise 25 — Configuration drift

Why check pg_settings.source?

**Answer:** To find settings overridden by role/database/session/auto.conf or unexpected sources.

### Exercise 26 — Private key

Why restrict file permissions?

**Answer:** Anyone who can read the private key can impersonate the server/client identity.

### Exercise 27 — Negative test

Name two negative TLS tests.

**Hint:** Wrong hostname, untrusted CA, expired certificate, plaintext connection rejected.

### Exercise 28 — DR

Why does DR need secret/certificate readiness?

**Answer:** After failover, services must connect and verify identities without depending on the primary region.

### Exercise 29 — Managed service

Why can't you always edit postgresql.conf directly on managed PostgreSQL?

**Answer:** The provider may manage settings via parameter groups/control plane and reconcile file state.

### Exercise 30 — Audit

List metadata to store after rotation without storing the secret value.

**Hint:** Secret/cert version, owner, consumers, fingerprint/serial, timestamps, tests, and revocation evidence.


## 53. Environment-based PostgreSQL Configuration Checklist

- [ ] Shared configuration template and separate environment values exist?
- [ ] postgresql.conf, auto.conf, include files, and HBA/ident paths inventoried?
- [ ] Effective settings/source/context/pending_restart captured?
- [ ] Duplicate/invalid settings and unexpected overrides resolved?
- [ ] Reload/restart requirements classified?
- [ ] Parameter values sized to each environment's capacity/workload?
- [ ] Config source of truth (repository/operator/parameter group) clear?
- [ ] Staging parity and DR configuration rehearsed?
- [ ] Change diff/owner/approval/rollback recorded?

## 54. Secrets, Authentication, and TLS Checklist

- [ ] Each service has its own role/credential and least privilege?
- [ ] Secrets stored in an approved manager, not in Git/images/logs?
- [ ] Password encryption/authentication uses SCRAM per compatibility?
- [ ] pg_hba rule order/CIDR/method verified?
- [ ] Server certificate SAN/chain/expiry valid?
- [ ] Private key owner/permissions secure?
- [ ] Clients use verify-full and the correct CA bundle?
- [ ] Client cert/mTLS mapping tested if applicable?
- [ ] Pooler frontend/backend TLS configured separately?
- [ ] Replication/FDW/backup/monitoring credentials inventoried?
- [ ] pg_stat_ssl and client-side verification evidence passing?
- [ ] Negative tests for wrong CA/hostname/password/plaintext executed?

## 55. Rotation and Incident Readiness Checklist

- [ ] Secret/certificate owners and consumers identified?
- [ ] Expiry/rotation alerts configured?
- [ ] Overlap/rollout order and rollback path clear?
- [ ] Applications/poolers/jobs capable of reloading/reconnecting?
- [ ] Existing sessions/cached connections accounted for?
- [ ] New credential/certificate tested across all consumers?
- [ ] Old credential/certificate revoked only after consumers switch?
- [ ] Emergency revocation process rehearsed?
- [ ] DR has secret-manager/CA access?
- [ ] Audit records free of raw secrets/private keys?

## 56. Quick Reference Table

| Component | Role |
|---|---|
| postgresql.conf | Main server configuration |
| postgresql.auto.conf | Persistent overrides from ALTER SYSTEM |
| pg_hba.conf | Connection admission/authentication rules |
| pg_ident.conf | Maps external identities to database roles |
| include/include_dir | Organizes multiple config files |
| pg_settings | Effective setting, source, context, pending_restart |
| pg_file_settings | Parsed configuration entries/errors |
| pg_hba_file_rules | Parsed HBA rules/errors |
| ALTER SYSTEM | Writes persistent server setting |
| pg_reload_conf | Requests reload |
| password_encryption | Selects password verifier format |
| SCRAM-SHA-256 | Password authentication method |
| hostssl | Matches TCP connections with TLS |
| ssl | Enables server-side TLS |
| ssl_cert_file | Server certificate |
| ssl_key_file | Server private key |
| ssl_ca_file | CA trust for client certificate verification |
| ssl_min_protocol_version | TLS protocol floor |
| sslmode=verify-full | Client verifies CA chain and hostname |
| sslrootcert | Client trusted CA bundle |
| sslcert/sslkey | Client certificate/private key |
| .pgpass / PGPASSFILE | libpq password file |
| pg_stat_ssl | TLS state for active connections |
| pg_stat_activity | Active sessions/queries |
| Secret manager | Secure secret storage/distribution |
| PKI | Certificate issuance/trust/revocation |
| Rotation overlap | Period during which consumers switch credentials/certificates |
| DR secret readiness | Ability to authenticate after failover |

## 57. Conclusion

**Managing configuration, secrets, and TLS requires a controlled configuration source alongside distinct lifecycles for credentials and certificates in every environment.** postgresql.conf, postgresql.auto.conf, include files, role/database defaults, and the control plane can all influence effective settings. Use pg_settings, pg_file_settings, and pg_hba_file_rules to identify sources, errors, and restart status; classify parameter context before reloading or restarting.

Secrets must be generated, stored, distributed, rotated, and revoked per service identity with least privilege. Use SCRAM-SHA-256 for password authentication when clients are compatible; never store plaintext passwords in source code, command lines, images, or logs. TLS server certificates protect server identity, while client verify-full verifies the CA chain and hostname. Client certificates/mTLS provide an additional identity layer; role privileges and pg_hba still govern access permissions.

Rotation must account for connection pools, existing sessions, cached FDW connections, replication, scheduled jobs, and DR. Use trust/credential overlap when appropriate, test new connections, recycle sessions, and revoke old credentials only after consumers have migrated. Managed services/operators must be configured through their proper control plane. Evidence consists of effective config, certificate fingerprints/serials, secret versions, test results, and revocation status; never store raw secret values.

Deployment principle: **keep configuration reproducible, keep secrets out of source code, verify both ends of TLS, assign dedicated identities per service, and rehearse rotation/failover before needing them in production.**
