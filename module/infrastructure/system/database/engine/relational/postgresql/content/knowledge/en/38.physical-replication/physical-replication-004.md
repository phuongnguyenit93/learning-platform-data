# Replication Roles, TLS, and Access Restrictions in PostgreSQL

Physical replication enables a PostgreSQL standby to receive and replay WAL from the primary to maintain a physical copy of the cluster. The connection between the standby and primary typically uses the replication protocol over TCP. Because this connection can stream WAL containing changes across multiple databases, replication privileges must be granted deliberately, restricted by connection source, and protected with TLS.

Three control layers must work together:

1. **Role** determines which account is permitted to log in and use the replication protocol.
2. **pg_hba.conf and network controls** determine where connections can originate from and which authentication methods are allowed.
3. **TLS** encrypts data in transit and can verify server/client identity via certificates.

A role with the REPLICATION attribute is not automatically allowed to connect from any address. A pg_hba.conf line allowing a connection also does not create a role or grant replication privileges. Successful TLS does not replace PostgreSQL authentication either.

~~~mermaid
flowchart TD
    S["Standby / pg_basebackup"] --> N["Network firewall"]
    N --> T["TLS handshake"]
    T --> H["pg_hba.conf: hostssl + source CIDR"]
    H --> A["Authentication: SCRAM or certificate"]
    A --> R["Role: LOGIN + REPLICATION"]
    R --> P["Replication protocol / WAL sender"]
    P --> W["WAL stream to standby"]
~~~

This lesson belongs to the **Physical Replication** chapter, module **Database Engine Relational PostgreSQL**. We will cover replication roles, HBA rules, password authentication, TLS server/client certificates, standby configuration, connection limits, replication slots, and how to monitor secure connections.

## 1. Learning objectives

After this lesson, you will be able to:

1. Explain why physical replication requires a role with the REPLICATION attribute.
2. Create a replication role with the minimum required privileges.
3. Distinguish between LOGIN, REPLICATION, and SUPERUSER privileges.
4. Understand that replication connections use a special database selector in pg_hba.conf.
5. Write HBA rules restricting user, source address, and TLS.
6. Understand rule matching order in pg_hba.conf.
7. Distinguish SCRAM-SHA-256, MD5, password files, and certificate authentication.
8. Enable TLS on the primary and configure certificates/keys.
9. Configure the standby to verify the server using sslmode=verify-full.
10. Understand mutual TLS and client certificate verification.
11. Combine TLS with pg_basebackup and streaming replication.
12. Restrict connections via firewall, listen_addresses, and role connection limits.
13. Understand max_wal_senders and max_replication_slots.
14. Manage passwords, certificates, and rotation lifecycles.
15. Monitor connections via pg_stat_replication and pg_stat_ssl.
16. Inspect HBA rules and reload configuration safely.
17. Diagnose authentication, TLS, certificate, and replication errors.
18. Build a security checklist and test failover/rotation.

## 2. What connection does physical replication use?

Physical streaming replication transmits WAL records from the primary to the standby. The primary runs a WAL sender process; the standby runs a WAL receiver process. This connection uses the replication protocol rather than a normal SQL session attached to an application database.

~~~text
Primary PostgreSQL
  |
  +-- WAL sender
        |
        | TCP + TLS + PostgreSQL authentication
        |
        v
Standby PostgreSQL
  |
  +-- WAL receiver
        |
        +-- write and replay WAL
~~~

A standby can be initialized with pg_basebackup and then continue streaming WAL. When the standby reconnects after a restart or network interruption, it uses the settings in primary_conninfo and the configured authentication mechanism.

### A replication connection is not a normal SQL connection

In pg_hba.conf, a physical replication connection is usually matched using a special database field:

~~~conf
hostssl  replication  standby_repl  10.20.0.12/32  scram-sha-256
~~~

The `replication` keyword in the database field matches replication connections. It is not an application database name to be created.

With logical replication, a subscriber connects to a specific database and uses the replication protocol for logical replication; the HBA rule typically must specify the actual database instead of assuming all replication connections use this keyword.

## 3. What is a replication role?

PostgreSQL uses roles to define user privileges. For an account to log in using the replication protocol, the role needs:

- The LOGIN attribute so it can open a session.
- The REPLICATION attribute to be allowed to initiate a replication connection and perform supported replication operations.
- No SUPERUSER attribute just for standard physical replication.

Example role creation:

~~~sql
CREATE ROLE standby_repl
    WITH LOGIN
         REPLICATION
         NOSUPERUSER
         NOCREATEDB
         NOCREATEROLE
         NOINHERIT;
~~~

This role can be used for replication connections. The password should be set via a secure prompt in psql:

~~~text
\password standby_repl
~~~

The `\password` command prompts for the password and avoids writing a plaintext password in SQL statements that get saved to history or logs.

### Why not use postgres/superuser for the standby?

A superuser has privileges far beyond what streaming replication needs. If credentials are exposed, an attacker can perform many dangerous administrative operations.

Creating a dedicated role helps:

- Scope the intended purpose.
- Simplify rotation and revocation.
- Make tracking in logs/statistics easier.
- Reduce blast radius if a secret is compromised.
- Separate replication privileges from DBA and application accounts.

### REPLICATION does not mean SELECT on all tables

The REPLICATION attribute permits using the replication protocol as defined by PostgreSQL. It is not simply a GRANT SELECT on all tables, nor does it make the role a superuser. Privileges of a replication role must be evaluated separately from normal SQL privileges.

## 4. Verifying role attributes

You can view role attributes:

~~~sql
SELECT
    rolname,
    rolcanlogin,
    rolreplication,
    rolsuper,
    rolcreatedb,
    rolcreaterole,
    rolconnlimit,
    rolvaliduntil
FROM pg_roles
WHERE rolname = 'standby_repl';
~~~

Key columns:

- rolcanlogin: whether the role is allowed to log in.
- rolreplication: whether the role has the REPLICATION attribute.
- rolsuper: whether the role has superuser privileges.
- rolcreatedb: whether it can create databases.
- rolcreaterole: whether it can create/alter other roles.
- rolconnlimit: connection limit for the role.
- rolvaliduntil: password expiration timestamp, if set.

Do not export password hashes from catalogs into unnecessary reports. pg_roles masks password hashes for users without sufficient privileges, but authentication details still require protection.

## 5. Role connection limits

You can set a connection limit:

~~~sql
ALTER ROLE standby_repl CONNECTION LIMIT 3;
~~~

This limits concurrent connections for the role according to PostgreSQL semantics. Account for standbys, backup jobs, and administrative tools sharing that credential.

You can set a role/password expiration:

~~~sql
ALTER ROLE standby_repl VALID UNTIL '2027-01-01 00:00:00+00';
~~~

This is an example timestamp; set it according to your actual rotation schedule. If the password expires while the standby still uses old credentials, reconnects may fail. Schedule updating credentials on the standby before expiration.

### When to use a separate role per standby?

If there are multiple standbys, creating a separate role per node helps:

- Revoke a single compromised/decommissioned standby individually.
- Distinguish connections in logs.
- Rotate credentials independently.
- Enforce per-node connection limits.
- Narrow the HBA source address to the exact machine.

In trade-off, you must manage multiple secrets and avoid leaving unused old roles active long-term.

## 6. Granting REPLICATION to an existing role

If a role already exists and needs to be used for replication:

~~~sql
ALTER ROLE standby_repl WITH LOGIN REPLICATION;
~~~

The REPLICATION attribute is a sensitive privilege. Grant it only to controlled, dedicated roles.

If an existing application role already has broad SQL privileges, do not casually add REPLICATION to it. Separating accounts clarifies responsibility and narrows access scope.

Revoke when no longer needed:

~~~sql
ALTER ROLE standby_repl NOREPLICATION;
~~~

Or disable login:

~~~sql
ALTER ROLE standby_repl NOLOGIN;
~~~

This change can cause active streaming replication or the next reconnect to fail. Perform it only after confirming the standby has been removed from the topology or has replacement credentials.

## 7. pg_hba.conf controls who can connect

pg_hba.conf is the Host-Based Authentication configuration. This file specifies:

- Connection type: local, host, hostssl, hostnossl.
- Database or replication connection.
- User/role.
- Source address.
- Authentication method.
- Additional options.

Example allowing only the standby at 10.20.0.12 to connect over TLS:

~~~conf
hostssl  replication  standby_repl  10.20.0.12/32  scram-sha-256
~~~

Meaning:

| Field | Value | Purpose |
| --- | --- | --- |
| Type | hostssl | Accept only TCP connections using SSL/TLS |
| Database | replication | Replication protocol connection |
| User | standby_repl | Permitted role |
| Address | 10.20.0.12/32 | A specific IPv4 address |
| Method | scram-sha-256 | SCRAM password authentication |

If the standby uses an IPv6 address, add a corresponding rule, such as a `/128` prefix for a single IPv6 address.

### Restricting by subnet

If you have a dedicated standby range:

~~~conf
hostssl  replication  standby_repl  10.20.0.0/24  scram-sha-256
~~~

A broader range is easier to manage but widens the possible source addresses that can connect. Prefer `/32` or `/128` addresses when the topology is fixed.

## 8. Rule ordering in pg_hba.conf

PostgreSQL evaluates pg_hba.conf from top to bottom. **The first rule matching the connection attributes is selected.** If authentication under that rule fails, PostgreSQL does not continue trying subsequent lines as a fallback.

Example:

~~~conf
host     replication  all  0.0.0.0/0       reject
hostssl  replication  standby_repl 10.20.0.12/32 scram-sha-256
~~~

The first line matches all IPv4 replication connections and rejects them, so the allow rule below is never reached for that connection.

Correct order:

~~~conf
hostssl  replication  standby_repl  10.20.0.12/32  scram-sha-256
host     replication  all           0.0.0.0/0      reject
~~~

You can add corresponding IPv6 rules. Keep specific rules before broad rules.

### Distinguishing host, hostssl, and hostnossl

- host: matches TCP connections with or without TLS.
- hostssl: matches only TCP connections using SSL/TLS.
- hostnossl: matches only TCP connections not using SSL/TLS.
- local: connections over Unix-domain sockets on supported operating systems.

If you want to enforce TLS for replication, use hostssl for allow rules and ensure no broader host rule permits the same user/source unencrypted.

## 9. Blocking non-TLS replication connections

You can place reject rules for non-TLS connections ahead of other matching rules:

~~~conf
hostnossl  replication  all  0.0.0.0/0  reject
hostnossl  replication  all  ::/0       reject

hostssl    replication  standby_repl  10.20.0.12/32  scram-sha-256
hostssl    replication  standby_repl  2001:db8:20::12/128  scram-sha-256
~~~

The `2001:db8::/32` addresses in the example belong to the documentation prefix, not production addresses. Replace them with actual managed IPv6 addresses.

Inspect the entire HBA file because another `host` line may grant access to an unintended source. Review rules in exact order, including include files if the configuration uses them.

## 10. Authentication with SCRAM-SHA-256

SCRAM-SHA-256 is the recommended password authentication method for modern PostgreSQL configurations.

Example:

~~~conf
hostssl  replication  standby_repl  10.20.0.12/32  scram-sha-256
~~~

You can configure password encryption for new passwords:

~~~conf
password_encryption = 'scram-sha-256'
~~~

Then reset the role's password so PostgreSQL stores the verifier in the desired format. Changing password_encryption does not automatically convert existing password hashes.

### Why avoid trust?

The trust method allows connections without normal password verification. If used for replication from an untrusted network, any client matching the rule can impersonate the role.

Do not use trust for production replication.

### MD5

MD5 authentication is deprecated in modern PostgreSQL. Migrate to SCRAM and verify client compatibility. Older clients may not support SCRAM; upgrade clients rather than lowering system-wide security when possible.

## 11. Passwords and password files

A standby must reconnect automatically after restarts or network interruptions. Interactive password entry is unsuitable for an automated service.

Libpq supports the `.pgpass` password file on Unix-like systems or `pgpass.conf` in the corresponding location on Windows.

Example line:

~~~text
primary.example.net:5432:replication:standby_repl:REPLACE_WITH_SECRET
~~~

The database field uses `replication` for replication connections.

### File permissions

On Unix-like systems, the password file needs strict permissions; libpq ignores the file if permissions allow others to read it. Typically use:

~~~bash
chmod 0600 ~/.pgpass
~~~

On Windows, the password file has its own location and ACL mechanism; grant permissions only to the required service account.

Do not commit password files to Git, and do not log secrets in logs, tickets, or command history.

### Escaping in pgpass

The `:` and `\` characters inside fields must be escaped according to password file syntax. If a password contains these characters, check libpq's escaping rules and test the connection before deploying to the standby.

## 12. TLS protects the replication connection

TLS provides:

- Encryption of data transmitted over the network.
- Server authentication when the client verifies the certificate.
- Optional client certificate authentication when mutual TLS is configured.
- Protection against eavesdropping and certain endpoint spoofing attacks.

TLS does not replace:

- Role privileges.
- pg_hba.conf.
- Firewall/network segmentation.
- Secret management.
- Replication slot controls.
- Monitoring and rotation.

An encrypted connection where the client does not verify the server certificate can still connect to a rogue server if DNS/routing is controlled by an attacker.

## 13. Enabling TLS on the primary

Example server configuration:

~~~conf
ssl = on
ssl_cert_file = 'server.crt'
ssl_key_file = 'server.key'
ssl_ca_file = 'root.crt'
ssl_min_protocol_version = 'TLSv1.2'
~~~

Meaning:

- ssl=on: enables the SSL/TLS listener.
- ssl_cert_file: server certificate.
- ssl_key_file: server private key.
- ssl_ca_file: CA certificate used for verifying client certificates when needed.
- ssl_min_protocol_version: minimum TLS version per policy.

File paths can be relative to the data directory or absolute paths per PostgreSQL configuration rules.

### What does the server certificate need?

The server certificate should:

- Be signed by a CA trusted by the standby.
- Have a SAN (Subject Alternative Name) containing the hostname the standby uses to connect.
- Not be expired.
- Have the proper certificate chain.
- Use a matching key/certificate pair.

When the standby connects via hostname `primary.example.net`, the certificate must validate that hostname. Do not use an IP in `primary_conninfo` if the certificate only has a DNS SAN without a matching IP SAN.

### Private key permissions

The private key must be protected so only the PostgreSQL service account or appropriate administrator can read it. On Unix-like systems, PostgreSQL requires strict private key file permissions; common setups are owner-only read (`0600`), or certain root-owned layouts per PostgreSQL rules. Check documentation for your OS/version.

## 14. Verifying the server certificate from the standby

On the standby, libpq needs a trusted CA certificate and an appropriate `sslmode`.

Use:

~~~text
sslmode=verify-full
sslrootcert=/etc/postgresql/certs/root.crt
~~~

`verify-full` does two things:

1. Verifies the certificate chain against a trusted CA.
2. Verifies that the connected hostname matches the certificate identity.

Comparison of common modes:

| sslmode | Encryption | CA check | Hostname check |
| --- | --- | --- | --- |
| disable | No | No | No |
| allow/prefer | Possibly not | No in the verify sense | No |
| require | Yes | Does not guarantee identity verification | No |
| verify-ca | Yes | Yes | No |
| verify-full | Yes | Yes | Yes |

For replication over untrusted networks, `verify-full` is usually the most suitable choice when PKI and hostnames are properly managed.

`require` only ensures the connection uses TLS in the applicable configuration; do not treat it as equivalent to `verify-full`.

## 15. Configuring primary_conninfo on the standby

The standby uses `primary_conninfo` to connect to the primary.

Example:

~~~conf
primary_conninfo = 'host=primary.example.net port=5432 user=standby_repl application_name=standby_1 sslmode=verify-full sslrootcert=/etc/postgresql/certs/root.crt'
~~~

Do not write the password directly in the configuration file when a password file can be used. Combine `.pgpass` with the database line set to `replication`.

If a client certificate needs to be specified:

~~~conf
primary_conninfo = 'host=primary.example.net port=5432 user=standby_repl application_name=standby_1 sslmode=verify-full sslrootcert=/etc/postgresql/certs/root.crt sslcert=/etc/postgresql/certs/standby.crt sslkey=/etc/postgresql/certs/standby.key'
~~~

The connection parameters are libpq parameters; verify exact paths and read permissions on the standby host.

### Where is the configuration written?

When using `pg_basebackup -R`, PostgreSQL creates `standby.signal` and writes connection configuration into `postgresql.auto.conf` per version behavior. Administrators can append TLS parameters to the managed configuration accordingly.

Do not edit the wrong configuration file or leave conflicting `primary_conninfo` entries. Identify the setting source via `pg_settings` and `SHOW primary_conninfo` (taking care not to print secrets if any exist).

## 16. Mutual TLS: authenticating both client and server

Mutual TLS (mTLS) requires the client to present a certificate so the server verifies client identity, while the client simultaneously verifies the server certificate.

On the primary:

- Configure server certificate/key.
- Configure the trusted CA in `ssl_ca_file`.
- HBA rule requires a client certificate per policy.
- Ensure the client certificate is signed by the trusted CA.

Example HBA:

~~~conf
hostssl  replication  standby_repl  10.20.0.12/32  scram-sha-256 clientcert=verify-full
~~~

This rule requires client certificate verification alongside the SCRAM authentication method. `clientcert` behavior and options can depend on the PostgreSQL version; check the Client Certificate Authentication page for your running version.

On the client, provide `sslcert` and `sslkey` in libpq connection parameters.

### Certificate authentication instead of password

You can use the `cert` method in `pg_hba.conf`:

~~~conf
hostssl  replication  standby_repl  10.20.0.12/32  cert
~~~

With `cert` authentication, PostgreSQL verifies the client certificate against the CA and matches the certificate identity to the database user per cert auth rules, defaulting to CN unless an appropriate map is configured.

This is a distinct authentication method. Do not confuse `clientcert=verify-full` with `cert`: a configuration requiring a client certificate can still combine with a password method like SCRAM; the `cert` method uses the certificate itself as the basis for role authentication.

## 17. When to choose SCRAM vs mTLS?

| Criterion | TLS + SCRAM | TLS + client certificate |
| --- | --- | --- |
| Traffic encryption | Yes | Yes |
| Server verification | Can use verify-full | Can use verify-full |
| Client-side secret | Password | Private key + certificate |
| Rotation | Rotate password | Rotate certificate/key |
| Identity | Database role + password | Certificate mapping/identity |
| Administration | Simpler | Requires PKI/certificate lifecycle |
| Suitable for | Many standard environments | Environments with PKI requiring mTLS |

You can combine client certificate verification with SCRAM for two layers of client identity verification, depending on policy. However, more mechanisms require clearer rotation and troubleshooting procedures.

## 18. pg_hba.conf with SCRAM and TLS: complete example

Assume:

- Primary hostname: primary.example.net.
- Standby IP: 10.20.0.12.
- Role: standby_repl.
- Primary listens on port 5432.
- The CA is configured and the standby can verify the certificate.

HBA:

~~~conf
# Allow the identified standby to open replication connections with TLS + SCRAM
hostssl  replication  standby_repl  10.20.0.12/32  scram-sha-256

# Reject unencrypted replication from IPv4/IPv6
hostnossl replication  all          0.0.0.0/0      reject
hostnossl replication  all          ::/0           reject
~~~

Allow rules must be placed before reject rules because PostgreSQL uses first-match semantics. Beyond the illustrative lines, audit the entire HBA file to make sure no broader rule permits non-TLS connections.

If using mTLS:

~~~conf
hostssl  replication  standby_repl  10.20.0.12/32  scram-sha-256 clientcert=verify-full
~~~

Do not copy example addresses, users, or paths verbatim into production without replacing them with real values and verifying certificates.

## 19. Network controls: listen_addresses and firewall

TLS and pg_hba.conf do not replace the network perimeter.

On the primary:

~~~conf
listen_addresses = '10.20.0.10'
port = 5432
~~~

Bind only to required interfaces. The default usually listens only on loopback; exact configuration depends on topology.

Firewalls/security groups should:

- Allow TCP 5432 only from the exact standby IP/subnet.
- Block unnecessary sources.
- Restrict access from the public internet.
- Use private networks/VPNs when appropriate.
- Log blocked connections per policy.
- Separate the management network from the replication network if architecture requires it.

Do not open `0.0.0.0/0` for PostgreSQL just to fix a connection error. Identify the real source and open the minimum scope.

## 20. Configuring related replication parameters

The primary typically needs:

~~~conf
wal_level = replica
max_wal_senders = 10
max_replication_slots = 10
~~~

Meaning:

- wal_level=replica: generates sufficient WAL information for physical replication.
- max_wal_senders: maximum concurrent WAL sender processes.
- max_replication_slots: maximum number of replication slots.

Values are examples only. Count standbys, backup jobs, logical subscribers, and headroom for reconnect/failover.

### Other parameters

- wal_keep_size: minimum amount of WAL retained in pg_wal per configuration.
- max_slot_wal_keep_size: caps WAL retained by replication slots, depending on version.
- wal_sender_timeout: detects hung sender connections.
- wal_receiver_timeout: detects when the receiver stops receiving timely responses.
- hot_standby: allows read-only queries on the standby.

Do not use `wal_keep_size` as a universal substitute for replication slots across all topologies. Each mechanism has different retention semantics.

### Slots can fill the disk

A physical replication slot whose consumer stops advancing can retain WAL long-term. Monitor slot lag and pg_wal disk usage. Have a runbook for long standby disconnects; do not drop a slot needed by a standby without understanding the consequences.

## 21. Initializing a standby with pg_basebackup

Example command:

~~~bash
pg_basebackup \
  -h primary.example.net \
  -p 5432 \
  -U standby_repl \
  -D /var/lib/postgresql/data \
  -R \
  -X stream \
  -P
~~~

Meaning:

- -h, -p, -U: connect to primary.
- -D: target data directory.
- -R: create standby configuration, including standby.signal and primary connection settings.
- -X stream: stream WAL during backup.
- -P: display progress.

On the standby, configure libpq SSL parameters and the password file according to your deployment approach. You can pass a connection string with `sslmode=verify-full` and `sslrootcert` using the corresponding connection option; check `pg_basebackup --help` for your client.

### Output data

`pg_basebackup` creates a physical base backup, not a logical archive like `pg_dump`. The data directory must be prepared per procedure; do not overwrite a running data directory.

## 22. Replication slots when creating a standby

You can use a physical replication slot to retain WAL for the standby when it temporarily disconnects.

Example creating a slot on the primary:

~~~sql
SELECT *
FROM pg_create_physical_replication_slot('standby_1_slot');
~~~

Then configure the standby to use the slot:

~~~conf
primary_slot_name = 'standby_1_slot'
~~~

Some `pg_basebackup` workflows support creating the slot simultaneously via `-C -S slot_name`; check `pg_basebackup --help` and your exact version before using.

### Slot lifecycle

- Slot names must be unique within the cluster.
- Slots can exist even when the standby is not running.
- WAL retention grows if the consumer stops advancing.
- Monitor `restart_lsn` and `wal_status` per version.
- Drop a slot only after confirming no standby/consumer needs it.

A slot is a stateful resource; it is not a credential or an HBA rule.

## 23. Restricting access with connection limits and topology

A secure design should apply multiple layers:

| Layer | Mechanism | Goal |
| --- | --- | --- |
| Network | Firewall/security group | Restrict IP/subnet |
| Listener | listen_addresses | Bind only necessary interfaces |
| HBA | hostssl + user + replication + CIDR | Filter connections and authentication |
| Role | LOGIN + REPLICATION | Limit account privileges |
| Authentication | SCRAM or cert | Verify client |
| TLS | verify-full, CA, certificate | Encrypt and verify server |
| Operations | Monitoring/rotation | Detect and handle changes |

A tight HBA rule does not protect you if the firewall is overly permissive and another HBA rule permits an unintended source. Conduct a holistic review.

## 24. Verifying HBA rules before reload

PostgreSQL provides the `pg_hba_file_rules` view to inspect parsed content from the HBA file:

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

Find errors:

~~~sql
SELECT
    line_number,
    error
FROM pg_hba_file_rules
WHERE error IS NOT NULL;
~~~

This view helps detect syntax errors and inspect parsed rules. It does not simulate every real connection or prove which rule matches first; review rule order and test from the actual source host.

### Reload HBA

After editing the file:

~~~sql
SELECT pg_reload_conf();
~~~

Or use `pg_ctl reload` per server operating practice.

HBA changes are usually applied via reload without needing a restart. If reload fails, inspect server logs and `pg_hba_file_rules.error`.

Do not remove the rule sustaining the only replication connection before verifying the replacement rule. An already open connection may remain active, but a standby reconnect after a restart will fail if the new HBA is wrong.

## 25. Checking active TLS usage

The `pg_stat_ssl` view reports the SSL status of backends:

~~~sql
SELECT
    pid,
    ssl,
    version,
    cipher,
    bits,
    client_dn,
    issuer_dn
FROM pg_stat_ssl
ORDER BY pid;
~~~

Meaning:

- ssl: whether the session uses SSL/TLS.
- version: TLS protocol version.
- cipher: cipher suite.
- bits: reported cipher key length.
- client_dn: distinguished name of the client certificate if present.
- issuer_dn: CA issuer of the client certificate if present.

Not every connection has a client certificate. With SCRAM over TLS, `client_dn` may be NULL while TLS is still in use.

### Joining with pg_stat_activity

~~~sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.client_addr,
    a.backend_type,
    s.ssl,
    s.version,
    s.cipher
FROM pg_stat_activity AS a
LEFT JOIN pg_stat_ssl AS s
    ON s.pid = a.pid
WHERE a.backend_type = 'walsender'
ORDER BY a.pid;
~~~

Backend type names and visibility depend on version. This query helps verify whether WAL sender sessions use TLS.

## 26. Monitoring standbys on the primary

View connected standbys:

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication
ORDER BY application_name;
~~~

Useful fields:

- client_addr: standby client address.
- application_name: standby name.
- state: streaming/catchup status...
- sync_state: synchronous replication state if applicable.
- LSN fields: progress of WAL send/write/flush/replay.
- Lag fields: statistically estimated latency, may be NULL when idle or lacking enough samples.

Combine with `pg_stat_ssl` to confirm TLS for the corresponding PID.

### Do not conclude from a single query

Lag varies with workload and sampling time. Track trends, WAL generation, replay rate, and disk usage. A missing standby may be down, not yet connected, rejected by HBA/authentication, or outside the current topology.

## 27. Checking effective configuration

Use `pg_settings`:

~~~sql
SELECT
    name,
    setting,
    unit,
    source,
    context,
    pending_restart
FROM pg_settings
WHERE name IN (
    'ssl',
    'ssl_min_protocol_version',
    'ssl_cert_file',
    'ssl_key_file',
    'ssl_ca_file',
    'listen_addresses',
    'port',
    'wal_level',
    'max_wal_senders',
    'max_replication_slots',
    'wal_keep_size',
    'max_slot_wal_keep_size'
)
ORDER BY name;
~~~

Parameters have different contexts:

- Some changes require a restart.
- Some can be reloaded.
- Some can change per session or role/database.
- `pending_restart` indicates a pending restart for the corresponding setting.

Do not assume every TLS or listener parameter can be applied via reload. Check context, source, and version documentation.

## 28. Diagnosing errors: no pg_hba.conf entry

Message like:

~~~text
FATAL: no pg_hba.conf entry for replication connection
       from host "10.20.0.12", user "standby_repl", SSL encryption
~~~

Check:

1. Is the database selector set to `replication`?
2. Is the username right?
3. Does the source IP match the CIDR?
4. Does HBA have a `hostssl` rule?
5. Which rule appears first and matches?
6. Is the client using TLS?
7. Was the HBA file reloaded?
8. Does any include file contain conflicting rules?

Do not widen the CIDR to the whole network as a quick fix. Identify the exact source address seen by the primary, including NAT.

## 29. Diagnosing errors: password authentication failed

Message:

~~~text
FATAL: password authentication failed for user "standby_repl"
~~~

Check:

- Does the role exist and have LOGIN?
- Does the role have the REPLICATION attribute?
- Is the secret in the password file accurate?
- Does the pgpass entry have the database field set to `replication`?
- Are file permissions/ACLs valid?
- Does the HBA method match SCRAM/client support?
- Was the password rotated on the primary without updating the standby?
- Did `VALID UNTIL` expire?
- Is the standby targeting the right primary host/port?

Changing a password on the primary does not automatically update the secret on the standby. Execute rotation in a controlled sequence.

## 30. Diagnosing TLS errors: certificate verify failed

Common causes:

- Wrong or untrusted CA certificate.
- Expired server certificate.
- Hostname does not match SAN.
- Standby uses an IP while the certificate only has a DNS SAN.
- Certificate chain missing intermediate CA.
- `sslrootcert` file has wrong path/permissions.
- System clock drift causing the certificate to appear not yet valid/expired.
- Client using an inappropriate `sslmode`.

Inspect the certificate using your organization's PKI tools or openssl per approved procedures. Do not downgrade `sslmode` to `require` as a permanent fix when `verify-full` fails.

## 31. Diagnosing errors: server does not support SSL

If the client requires TLS but the server does not support it:

- Check `ssl=on`.
- Check that the PostgreSQL build has SSL support.
- Check server certificate/key paths.
- Inspect startup/reload logs.
- Check that you are connecting to the right host/port.
- Check for an intervening proxy/load balancer.

A server with `ssl=on` but an invalid certificate/key may fail to start or fail to reload the desired configuration. Read server logs rather than inferring from a single client error message.

## 32. Diagnosing a standby that is not streaming

If role/HBA/TLS are right yet the standby is not streaming:

1. Check `pg_stat_replication` on the primary.
2. Check logs on both standby and primary.
3. Verify `primary_conninfo`.
4. Check `standby.signal`.
5. Check `primary_slot_name` if using a slot.
6. Check `max_wal_senders` for available capacity.
7. Check `max_replication_slots` and slot state.
8. Check firewall, DNS, and routing.
9. Check TLS/password authentication.
10. Check WAL availability and timeline/history.

A streaming error may stem from a WAL gap or timeline mismatch rather than credentials. Do not immediately recreate the base backup before reading logs and identifying the root cause.

## 33. Restricting access with connection limits and topology

Restrictions should match the topology:

- A dedicated role per standby.
- A clear source IP or subnet.
- HBA restricted to replication connections.
- Firewall opening the port only from standbys.
- Connection limit sufficient for reconnect/failover.
- `max_wal_senders` sufficient for standbys and backup operations.
- `max_replication_slots` sufficient for managed slots.

If multiple standbys and `pg_basebackup` run simultaneously, sender slots can be exhausted. Leave headroom for backup/failover operations per your capacity plan.

### Connection limit does not replace HBA

A role connection limit only caps the number of sessions for that role. It does not restrict source IP or database type. HBA must still restrict source and connection type.

## 34. Rotating replication passwords

A safe rotation procedure:

1. Identify which standbys use the role/secret.
2. Generate new credentials or prepare the password change window.
3. Update the password file/secret store on the standby per procedure.
4. Change the role password on the primary at the scheduled time.
5. Verify connection/reconnect and `pg_stat_replication`.
6. Watch logs for auth failures.
7. Revoke old credentials and update inventory.
8. Record timestamp, owner, and outcome.

With one role shared across multiple standbys, rotation requires coordinating all nodes. Separating roles per standby makes credential rotation more independent.

### Using two roles in parallel for rotation

In systems needing to avoid interruption, you can create a new role, switch one standby or group of standbys to the new credential, verify connectivity, and only then revoke the old role. Coordinate this with HBA rules and capacity so unintended duplicate replication streams are not created.

## 35. Rotating TLS certificates

Certificate rotation requires planning for CA, server, and client certificates.

### When rotating the server certificate

- Add the new CA to the standby trust store first.
- Install the new certificate/key on the primary.
- Verify SAN, chain, expiry, and file permissions.
- Reload/restart as required by the setting/version.
- Confirm the standby reconnects and TLS still passes `verify-full`.
- After the transition period, remove the old CA from the trust store.

### When rotating the client certificate

- Add the new client CA to `ssl_ca_file` on the primary if the CA changed.
- Install the client cert/key on the standby.
- Verify identity mapping and certificate expiry.
- Switch the standby to the new cert.
- Verify `pg_stat_ssl.client_dn`.
- Revoke or stop trusting the old certificate per PKI policy.

Do not remove the old CA from the trust store before all valid standbys finish switching, or replication connections may break.

## 36. TLS and certificate expiration

Expired certificates can cause reconnects to fail. Monitor:

- `notBefore` and `notAfter`.
- CA chain expiry.
- Server certificate SAN.
- Client certificate identity.
- Certificate revocation policy if applied by your organization.
- System clock/NTP.
- Time remaining until expiry.

Set alerts far enough ahead of expiration to allow time for coordinated rotation and testing. Do not wait until the standby goes down to discover an expired certificate.

## 37. Restricting permissions and protecting configuration files

Protect:

- postgresql.conf.
- postgresql.auto.conf.
- pg_hba.conf.
- Server private key.
- Client private key.
- .pgpass/pgpass.conf.
- CA bundles.
- Configuration backups.

Only authorized administrators and required service accounts should read/modify these files. Do not place private keys in repositories, public shared folders, or uncontrolled build artifacts.

`SHOW primary_conninfo` can display the connection string. Avoid placing output containing passwords/secrets into logs, tickets, or dashboards.

## 38. How does logical replication differ from physical replication?

This lesson focuses on physical streaming replication, though it helps to distinguish:

| Characteristic | Physical replication | Logical replication |
| --- | --- | --- |
| Transmitted data | Physical WAL changes | Logical row changes |
| Scope | Cluster-level physical standby | Database/publication/subscription |
| Connection | Replication protocol | Replication protocol on a specific database |
| Role | LOGIN + REPLICATION | LOGIN + REPLICATION plus required SQL privileges |
| HBA database selector | `replication` for physical connection | Specific database of the subscriber |
| Standby state | Physical standby/recovery | Subscriber applies changes into tables |
| DDL | Follows physical WAL | Does not automatically replicate all DDL like physical |

Logical replication has different privilege and object requirements. Do not blindly copy the `replication` HBA database selector for a subscriber without checking the actual connection type/database.

## 39. Post-deployment role/HBA verification

### Role

~~~sql
SELECT
    rolname,
    rolcanlogin,
    rolreplication,
    rolsuper,
    rolcreatedb,
    rolcreaterole,
    rolconnlimit,
    rolvaliduntil
FROM pg_roles
WHERE rolname LIKE 'standby_%'
ORDER BY rolname;
~~~

### HBA parse errors

~~~sql
SELECT line_number, error
FROM pg_hba_file_rules
WHERE error IS NOT NULL;
~~~

### Standby connection

~~~sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    sync_state
FROM pg_stat_replication
ORDER BY application_name;
~~~

### TLS state

~~~sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.client_addr,
    s.ssl,
    s.version,
    s.cipher,
    s.client_dn
FROM pg_stat_activity AS a
JOIN pg_stat_ssl AS s USING (pid)
WHERE a.backend_type = 'walsender';
~~~

These queries are only part of verification. Test from the actual standby host and check logs on both sides.

## 40. End-to-end configuration example: TLS + SCRAM

Assume primary:

- Hostname: primary.example.net.
- Address: 10.20.0.10.
- Port: 5432.

Standby:

- Address: 10.20.0.12.
- Role: standby_repl.

### Step 1: Create the role on the primary

~~~sql
CREATE ROLE standby_repl
    WITH LOGIN
         REPLICATION
         NOSUPERUSER
         NOCREATEDB
         NOCREATEROLE;

\password standby_repl
~~~

### Step 2: Configure TLS on the primary

~~~conf
ssl = on
ssl_cert_file = 'server.crt'
ssl_key_file = 'server.key'
ssl_min_protocol_version = 'TLSv1.2'
~~~

The certificate must be signed by a trusted CA and the SAN must contain `primary.example.net`.

### Step 3: HBA

~~~conf
hostssl  replication  standby_repl  10.20.0.12/32  scram-sha-256
hostnossl replication all           0.0.0.0/0      reject
hostnossl replication all           ::/0           reject
~~~

Ensure specific rules precede reject rules and no broader allow rules exist.

### Step 4: Configure the password file on the standby

~~~text
primary.example.net:5432:replication:standby_repl:REPLACE_WITH_SECRET
~~~

Set file permissions appropriate for the OS/service account.

### Step 5: Initialize the base backup

~~~bash
pg_basebackup \
  -h primary.example.net \
  -p 5432 \
  -U standby_repl \
  -D /var/lib/postgresql/data \
  -R \
  -X stream \
  -P
~~~

Ensure the libpq connection from the standby uses `sslmode=verify-full` and `sslrootcert` pointing to the appropriate CA. This can be set via a service definition or connection parameters accepted by `pg_basebackup`.

### Step 6: Start the standby and verify

On the primary:

~~~sql
SELECT
    application_name,
    client_addr,
    state,
    sync_state
FROM pg_stat_replication;
~~~

Check TLS for walsender:

~~~sql
SELECT
    a.pid,
    a.application_name,
    s.ssl,
    s.version,
    s.cipher
FROM pg_stat_activity AS a
JOIN pg_stat_ssl AS s USING (pid)
WHERE a.backend_type = 'walsender';
~~~

Complete deployment only when the standby is streaming, TLS is confirmed, and there are no auth/TLS errors in the logs.

## 41. End-to-end example: mutual TLS

Assume the organization has its own PKI:

- Primary certificate signed by an internal server CA.
- Standby client certificate signed by an internal client CA.
- Primary trusts the client CA.
- Standby trusts the server CA.

On the primary:

~~~conf
ssl = on
ssl_cert_file = 'server.crt'
ssl_key_file = 'server.key'
ssl_ca_file = 'client-root.crt'
~~~

HBA:

~~~conf
hostssl replication standby_repl 10.20.0.12/32 scram-sha-256 clientcert=verify-full
~~~

On the standby, `primary_conninfo` has parameters:

~~~text
host=primary.example.net
port=5432
user=standby_repl
sslmode=verify-full
sslrootcert=/etc/postgresql/certs/server-root.crt
sslcert=/etc/postgresql/certs/standby.crt
sslkey=/etc/postgresql/certs/standby.key
~~~

These can be placed in a single connection string in the configuration. Ensure private keys are readable only by the service account.

Verify the client certificate is recorded via `pg_stat_ssl.client_dn` if the version/configuration provides that field.

## 42. Anomaly monitoring and auditing

Signals to monitor:

- Repeated authentication failures for replication roles.
- Connections from source IPs not in inventory.
- TLS versions/ciphers violating policy.
- Certificates nearing expiration.
- Repeated standby reconnects.
- Expected standbys missing from `pg_stat_replication`.
- Increasing replication lag.
- Inactive replication slots with growing WAL retention.
- Role attribute changes outside change windows.
- HBA file modifications or parse errors.

Record:

- Role owner.
- Standby node mapping.
- Source IP/CIDR.
- Certificate serial/expiry.
- HBA rule line/change ticket.
- Rotation timestamp.
- Approver and test results.

Do not log passwords or private key material.

## 43. Common security mistakes

1. **Using SUPERUSER for the standby**, increasing impact if credentials leak.
2. **Using an application role for replication**, mixing unrelated privileges.
3. **Using trust authentication over the network**, allowing unauthenticated connections.
4. **Using broad host rules**, accidentally allowing unencrypted connections.
5. **Placing reject rules before allow rules**, preventing the standby from matching the allow rule.
6. **Using an application database name in a physical replication HBA rule**, instead of the `replication` selector.
7. **Forgetting the real source IP behind NAT**, causing HBA mismatches.
8. **Opening the firewall to the entire internet**, instead of restricting to the standby subnet.
9. **Enabling TLS with sslmode=require**, and assuming hostname/server identity is verified.
10. **Not checking SAN**, causing `verify-full` to fail or using the wrong hostname.
11. **Storing passwords in primary_conninfo, shell history, or logs**, leaking secrets.
12. **Leaving .pgpass with overly broad read permissions**, exposing secrets.
13. **Not rotating passwords/certificates**, leading to expired or overly long-lived credentials.
14. **Removing the old CA too early**, disconnecting standbys that have not yet switched certificates.
15. **Not monitoring replication slots**, retaining WAL until the disk fills up.
16. **Increasing connection limits/worker counts without capacity planning**, exhausting connection resources.
17. **Not checking pg_hba_file_rules**, leaving syntax errors after edits.
18. **Not checking pg_stat_ssl**, not knowing whether replication sessions actually use TLS.
19. **Not distinguishing physical and logical replication**, writing the wrong database selector in HBA.
20. **Revoking a role while the standby is still running**, causing reconnects after restart to fail.

## 44. Practice exercises with answers

### Exercise 1. Which attributes does a physical replication role need?

**Answer:** LOGIN and REPLICATION. SUPERUSER is not required for standard streaming replication.

### Exercise 2. Create a replication role

~~~sql
CREATE ROLE standby_repl WITH LOGIN REPLICATION NOSUPERUSER;
~~~

**Answer:** Creates a role that can log in and use the replication protocol without superuser privileges.

### Exercise 3. Is REPLICATION equivalent to SUPERUSER?

**Answer:** No. It is a separate attribute granting access to the replication protocol and related operations.

### Exercise 4. What is the HBA database field for physical replication?

**Answer:** The special keyword `replication`.

### Exercise 5. Write a TLS + SCRAM rule for a standby

~~~conf
hostssl replication standby_repl 10.20.0.12/32 scram-sha-256
~~~

**Answer:** Permits the role from the exact IPv4 source over TLS and SCRAM.

### Exercise 6. How does hostssl differ from host?

**Answer:** `hostssl` matches only TCP connections using TLS; `host` can match both TLS and non-TLS.

### Exercise 7. What order does HBA use?

**Answer:** The first line matching the connection is selected; an authentication failure does not make PostgreSQL try the next line.

### Exercise 8. Why must broad reject rules be placed after specific allow rules?

**Answer:** If the reject rule matches first, the allow rule below it is never evaluated.

### Exercise 9. Is SCRAM-SHA-256 transport encryption?

**Answer:** No. SCRAM is password authentication; TLS protects data in transit.

### Exercise 10. What does sslmode=verify-full do?

**Answer:** Encrypts traffic, verifies the certificate chain, and checks that the hostname matches the certificate identity.

### Exercise 11. Does sslmode=require verify the hostname?

**Answer:** Not guaranteed. It is not equivalent to `verify-full`.

### Exercise 12. What basic TLS settings does the server need?

**Answer:** `ssl=on`, `ssl_cert_file`, and `ssl_key_file`; `ssl_ca_file` when verifying client certificates.

### Exercise 13. What is primary_conninfo used for?

**Answer:** Provides connection parameters for the standby to connect to the primary.

### Exercise 14. What does pg_basebackup -R do?

**Answer:** Creates standby configuration, including `standby.signal` and connection settings depending on version.

### Exercise 15. Why does the password file database field use replication?

**Answer:** Physical replication connections use the `replication` pseudo-database selector in libpq authentication.

### Exercise 16. What is Mutual TLS?

**Answer:** Both client and server verify each other's certificate identity.

### Exercise 17. How does clientcert=verify-full differ from cert?

**Answer:** `clientcert` requires/verifies a client certificate and can be combined with password authentication; `cert` uses certificate authentication as the method to authenticate the role.

### Exercise 18. What is pg_stat_ssl used for?

**Answer:** Checking SSL/TLS status, protocol, cipher, and client certificate metadata of sessions.

### Exercise 19. What does pg_stat_replication show?

**Answer:** Connected standbys, addresses, streaming status, sync state, and LSN/lag metrics.

### Exercise 20. What is the role of max_wal_senders?

**Answer:** Limits the number of concurrent WAL sender processes.

### Exercise 21. What is the role of max_replication_slots?

**Answer:** Limits the number of replication slots that can exist.

### Exercise 22. Why can a replication slot fill the disk?

**Answer:** The slot retains WAL needed for the consumer; if the consumer stops advancing, WAL can accumulate.

### Exercise 23. What is pg_hba_file_rules used for?

**Answer:** Viewing parsed HBA rules and detecting syntax errors.

### Exercise 24. How do you reload pg_hba.conf?

~~~sql
SELECT pg_reload_conf();
~~~

**Answer:** Instructs PostgreSQL to reload reloadable configuration settings, including HBA.

### Exercise 25. Should the same role be used for the application and the standby?

**Answer:** No. Separating roles reduces privileges and allows independent credential management.

### Exercise 26. What happens if the certificate SAN does not contain the hostname in primary_conninfo?

**Answer:** `verify-full` fails because the hostname does not match the certificate identity.

### Exercise 27. When rotating a CA, what should be done first?

**Answer:** Add the new CA to clients' trust stores before switching the server certificate, maintaining planned trust overlap.

### Exercise 28. What happens if the password on the primary is changed but the standby is not updated?

**Answer:** New connections/reconnects may fail with `password authentication failed`.

### Exercise 29. Do physical and logical replication use the same HBA database selector?

**Answer:** Not by default. Physical replication uses the `replication` selector; a logical subscriber connects to a specific database.

### Exercise 30. What are the completion criteria for a secure replication deployment?

**Answer:** Least-privilege role, HBA restricted to the exact source, TLS `verify-full` or mTLS per policy, standby streaming, `pg_stat_ssl` confirming TLS, clean logs, and monitoring/rotation in place.

## 45. Operations checklist

- [ ] Use a dedicated role with LOGIN and REPLICATION.
- [ ] Do not grant SUPERUSER to the standby unless there is a specific administrative reason.
- [ ] Disable CREATEDB/CREATEROLE on the replication role.
- [ ] Set a connection limit appropriate for the topology.
- [ ] Maintain an inventory of roles, standbys, source IPs, and owners.
- [ ] Use the `replication` database selector for physical HBA rules.
- [ ] Allow only necessary source IPs/CIDRs.
- [ ] Place specific HBA allow rules before broad reject rules.
- [ ] Enforce TLS using `hostssl`.
- [ ] Reject unencrypted replication connections.
- [ ] Use SCRAM-SHA-256 or certificate authentication.
- [ ] Do not use `trust` over the network.
- [ ] Configure server certificate/key properly.
- [ ] Protect private keys with file permissions/ACLs.
- [ ] Ensure server certificate SAN matches the hostname.
- [ ] Use `sslmode=verify-full` on the standby.
- [ ] Configure `sslrootcert` with the right CA.
- [ ] Use client certificates if policy requires mTLS.
- [ ] Protect `.pgpass`/secret store and do not log passwords.
- [ ] Verify `listen_addresses` and firewall.
- [ ] Configure `max_wal_senders`/`max_replication_slots` according to capacity.
- [ ] Monitor replication slots and WAL retention.
- [ ] Check HBA parse errors before/after reload.
- [ ] Inspect `pg_stat_replication` and `pg_stat_ssl`.
- [ ] Schedule password/certificate rotation.
- [ ] Test reconnects after rotation and restarts.
- [ ] Maintain CA overlap during transitions.
- [ ] Maintain runbooks for authentication/TLS/replication failures.
- [ ] Distinguish physical and logical replication in HBA.
- [ ] Do not open production traffic before verifying streaming and TLS.

## 46. Official PostgreSQL documentation

Read the documentation matching the major version you are deploying:

- [Database Roles](https://www.postgresql.org/docs/current/user-manag.html) — role attributes and privileges.
- [CREATE ROLE](https://www.postgresql.org/docs/current/sql-createrole.html) — LOGIN, REPLICATION, CONNECTION LIMIT, and VALID UNTIL.
- [ALTER ROLE](https://www.postgresql.org/docs/current/sql-alterrole.html) — changing role attributes and passwords.
- [The pg_hba.conf File](https://www.postgresql.org/docs/current/auth-pg-hba-conf.html) — HBA rule syntax, ordering, and authentication methods.
- [Password Authentication](https://www.postgresql.org/docs/current/auth-password.html) — SCRAM and password methods.
- [Client Certificate Authentication](https://www.postgresql.org/docs/current/auth-cert.html) — cert and clientcert options.
- [SSL Support](https://www.postgresql.org/docs/current/ssl-tcp.html) — TLS server configuration, certificates, and client verification.
- [libpq Connection Parameters](https://www.postgresql.org/docs/current/libpq-connect.html) — sslmode, sslrootcert, sslcert, and sslkey.
- [The Password File](https://www.postgresql.org/docs/current/libpq-pgpass.html) — password file and replication connection entries.
- [Streaming Replication](https://www.postgresql.org/docs/current/warm-standby.html) — physical streaming replication.
- [pg_basebackup](https://www.postgresql.org/docs/current/app-pgbasebackup.html) — creating physical base backups and standby configuration.
- [Replication Configuration](https://www.postgresql.org/docs/current/runtime-config-replication.html) — wal_level, WAL senders, slots, and related settings.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — pg_stat_replication, pg_stat_ssl, and pg_stat_activity.
- [System View pg_hba_file_rules](https://www.postgresql.org/docs/current/view-pg-hba-file-rules.html) — inspecting HBA parsing.
- [Replication Slots](https://www.postgresql.org/docs/current/warm-standby.html#STREAMING-REPLICATION-SLOTS) — slot behavior and WAL retention.

The `/current/` URLs point to the current PostgreSQL documentation. Certain options, authentication behaviors, TLS protocol defaults, and view columns can differ between major versions; check the documentation matching your server/client version before deploying.

## 47. Summary

**Securing physical replication requires proper role authentication, strict source restrictions, and encrypted/verified connections with TLS.** All three layers must be configured consistently and verified after every change.

1. **A dedicated role needs LOGIN and REPLICATION.** Do not use superuser for standard streaming replication.
2. **Physical replication HBA uses the `replication` database selector.** Restrict the user and exact source CIDR.
3. **HBA uses first-match semantics.** Specific allow rules must precede broad reject rules.
4. **SCRAM authenticates passwords; TLS protects data in transit.** The two mechanisms serve different goals.
5. **sslmode=verify-full verifies both CA and hostname.** `require` alone is insufficient to verify server identity.
6. **mTLS can verify client certificates.** Distinguish `clientcert` verification from `cert` authentication.
7. **Firewall, listen_addresses, and HBA complement each other.** Do not expose PostgreSQL to all sources.
8. **Password files and private keys must be protected.** Never store secrets in source control or logs.
9. **Replication slots require monitoring.** A stalled consumer can retain WAL and fill the disk.
10. **pg_stat_replication and pg_stat_ssl help verify topology and TLS.**
11. **Rotations must include overlap and reconnect testing.** Uncoordinated password/certificate changes can stall standby streaming.
12. **Logical replication has different connection/database semantics from physical replication.** Write HBA rules matching the actual connection type.

When roles, HBA, TLS, network, and monitoring are deployed together, PostgreSQL can maintain physical standbys over authenticated, encrypted, and topology-restricted connections.
