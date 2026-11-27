# Managing mongod, mongos Configuration and Startup Parameters in MongoDB

> **Module:** Database Engine Document MongoDB  
> **Chapter:** Operations and Upgrades  
> **Lesson:** Managing mongod, mongos Configuration and Startup Parameters

## 1. Why is MongoDB configuration a critical part of operations?

An e-commerce system runs a MongoDB replica set in staging and a sharded cluster in production. After a deployment, the operations team runs into these situations:

- The server fails to start due to invalid YAML indentation.
- The service runs, but only listens on `127.0.0.1`; applications from other hosts cannot connect.
- `storage.dbPath` is changed in the configuration, and MongoDB starts with an empty data directory.
- A replica set member cannot join because `replication.replSetName` differs from the other members.
- `mongos` cannot connect to the config server replica set.
- An operator edits `mongod.conf`, but a CLI flag or environment override causes the effective value to differ from what was expected.
- `security.authorization` is enabled on a replica set without preparing internal authentication, causing nodes to fail to communicate.
- A TLS certificate is rotated without following the proper restart/reload procedure; some clients lose connectivity.
- A `setParameter` takes effect immediately, whereas changing `net.port` requires a restart.
- After an upgrade, a legacy option has been removed and MongoDB refuses to start up.

These issues are not CRUD or query syntax problems; they belong to **MongoDB process lifecycle management**.

A proper procedure must answer:

1. Is the process `mongod` or `mongos`?
2. Where is the configuration file loaded from?
3. What command-line arguments or environment overrides are present?
4. What are the actual values parsed by the server?
5. Is the option applied at startup or changeable at runtime?
6. Does it affect a single process, a replica set, or the entire sharded cluster?
7. Does the change require a rolling restart, failover, or migration?
8. How do you verify success and recover on failure?
9. How are secrets/private keys in the configuration protected?

**Core principle:** Do not just "edit YAML and restart". Clearly determine the **scope, effective timing, version support, actual state, dependencies, and rollback**.

### 1.1. Learning Objectives

After this lesson, you will be able to:

- Distinguish the responsibilities of `mongod` and `mongos`.
- Write valid YAML configurations for standalone, replica set member, shard, and router processes.
- Map config file settings to CLI options such as `--dbpath`, `--port`, `--replSet`, and `--configdb`.
- Understand CLI override precedence and cases where options conflict.
- Use `getCmdLineOpts` to inspect the active startup configuration.
- Distinguish between startup-only and runtime-changeable `setParameter` settings.
- Configure network, storage, system log, authorization, TLS, member authentication, and sharding.
- Manage systemd, Windows service, and container/Kubernetes deployments.
- Build runbooks for validation, rolling restarts, rollback, and monitoring.
- Identify when a config change must be coordinated with an upgrade and Feature Compatibility Version (FCV).

---

## 2. Two Different Processes: mongod and mongos

MongoDB has two process types that must be clearly distinguished.

### 2.1. mongod — the data storage and processing server

`mongod` is the MongoDB database server. It can operate in these roles:

- Standalone server.
- Replica set member.
- Shard server in a sharded cluster.
- Config server member in a config server replica set.

`mongod` manages:

- The storage engine and data files.
- Document reads and writes.
- Indexes.
- Replication/oplog when acting as a replica set member.
- Authorization.
- Transaction/query execution.
- Cache, journaling, and background tasks.

Typical options:

```yaml
storage:
  dbPath: /var/lib/mongodb

replication:
  replSetName: rs0

net:
  port: 27017
```

### 2.2. mongos — the query router of a sharded cluster

`mongos` is the router that receives requests from MongoDB clients and dispatches them to shards.

It:

- Uses sharded cluster metadata/routing information.
- Routes queries to the appropriate shards.
- Coordinates results for certain distributed operations.
- Manages connections to the config server replica set.
- Has its own network/TLS/logging/process runtime settings.

It does **not** store collections like a `mongod` shard and does not have `storage.dbPath` for storing application data.

Key option:

```yaml
sharding:
  configDB: cfgRS/cfg1.example.internal:27019,cfg2.example.internal:27019,cfg3.example.internal:27019
```

### 2.3. Role Diagram

```text
                 Application / Java Driver
                           │
                           ▼
                    mongos routers
                    ┌─────┴─────┐
                    │           │
                    ▼           ▼
              Shard rsA     Shard rsB
              mongod x3     mongod x3
                    │           │
                    └─────┬─────┘
                          │
                     Config RS
                     mongod x3
```

In a standalone or non-sharded replica set, applications connect directly to `mongod` using the appropriate topology connection string, **without needing mongos**.

### 2.4. Comparison Table

| Attribute | mongod | mongos |
|---|---|---|
| Stores data collections | Yes | No |
| Has `storage.dbPath` | Yes | No |
| Uses `replication.replSetName` when a replica set member | Yes | No |
| Uses `sharding.clusterRole` | Yes, when a shard/config server | No |
| Uses `sharding.configDB` | No, cannot replace shard role | Yes, requires config server RS |
| Listens for client TCP connections | Yes | Yes |
| Has `net.tls` | Yes | Yes |
| Has `systemLog` | Yes | Yes |
| Has `setParameter` | Yes, depending on parameter | Yes, depending on parameter |
| Has `security.authorization` option | Yes | Not via the same config field |
| Uses `security.keyFile` for keyfile member authentication | Yes | May be needed on mongos |
| Supports `getCmdLineOpts` | Yes | Yes |

**Do not copy `mongod.conf` verbatim to `mongos.conf`.** The storage, replication, and sharding sections have distinct scopes.

---

## 3. Configuration Layers: Defaults, YAML File, CLI, and Runtime

A MongoDB process receives settings from multiple sources:

```text
Server binary + version defaults
       │
       ├─ Configuration file (*.conf/*.cfg)
       │      net.port, storage.dbPath, ...
       │
       ├─ Startup CLI arguments
       │      --config, --port, --bind_ip, ...
       │
       ├─ Supported environment overrides /
       │   external expansion directives
       │
       └─ Runtime changes when supported
              setParameter, setLogLevel, ...
```

These layers can interact with each other. **Do not apply a blanket precedence order to every option** when the documentation specifies dedicated overrides or conflicts.

Examples from the official documentation:

- `--bind_ip` can override `net.bindIp` in the config file.
- `net.bindIp` and `net.bindIpAll` are **mutually exclusive**: they cannot be specified together.
- `MONGODB_CONFIG_OVERRIDE_NOFORK` has a specific effect on `processManagement.fork`.
- Some flags/values cannot be combined, causing startup failure rather than silently picking one side.

**Always inspect the effective parsed startup options** instead of trusting only the contents of a single file.

### 3.1. Common Configuration Locations

| Environment | Common Path | Notes |
|---|---|---|
| Debian/Ubuntu package install | `/etc/mongod.conf` | Package service may assume default data/log paths |
| RHEL/CentOS package install | `/etc/mongod.conf` | Check unit file and distribution |
| macOS via Homebrew | `/usr/local/etc/mongod.conf` or `/opt/homebrew/etc/mongod.conf` | Depends on CPU/installation |
| Windows MSI | Usually `mongod.cfg` in the `bin` directory | Check Windows service command |
| Docker/container | Image entrypoint/config volume/env | No single immutable path |
| Kubernetes Operator | Custom Resource, Secret, ConfigMap | Operator may recreate Pod/config |
| MongoDB Atlas | Control plane/service configuration | Do not manually edit `mongod.conf` |

Example paths do not replace checking the **actual running process**.

### 3.2. The File Is Only Part of the Desired State

Server state also depends on:

- Binary version.
- Config file and CLI.
- OS/service permissions.
- DNS/TLS CA/certificates.
- Data inside `storage.dbPath`.
- Existing replica set/shard metadata.
- Secrets/keyfiles.
- Runtime settings.
- Orchestrator lifecycle.

A valid YAML file does not guarantee a healthy cluster if the remaining conditions are wrong.

---

## 4. MongoDB YAML Syntax

Self-managed MongoDB uses YAML-formatted configuration files.

### 4.1. Basic Structure

Local lab standalone example, **with authorization not yet enabled**:

~~~yaml
systemLog:
  destination: file
  path: /var/log/mongodb/mongod-lab.log
  logAppend: true

storage:
  dbPath: /var/lib/mongodb-lab

net:
  bindIp: 127.0.0.1
  port: 27017
~~~

Each level is indented with **spaces**. YAML does not use tabs for indentation.

### 4.2. Data Types

Common values:

~~~yaml
net:
  port: 27017
  bindIp: "127.0.0.1"

systemLog:
  logAppend: true
  verbosity: 0

security:
  authorization: enabled
~~~

- `27017` is an integer.
- `true` is a boolean.
- `0` is an integer.
- `"127.0.0.1"` is a string.
- `enabled` is an exact-case string enum.

A typo such as `authorization: Enabled` can cause MongoDB to refuse startup on versions requiring a case-sensitive enum.

### 4.3. Tabs, Indentation, and Duplicate Keys

Wrong:

~~~yaml
net:
    port: 27017
  bindIp: 127.0.0.1
~~~

Inconsistent indentation, invalid.

Wrong organization:

~~~yaml
net:
  port: 27017

net:
  bindIp: 127.0.0.1
~~~

Duplicate YAML keys may be rejected or interpreted unexpectedly, and must not be relied upon to merge configuration.

Correct:

~~~yaml
net:
  port: 27017
  bindIp: 127.0.0.1
~~~

### 4.4. Quoting Special Characters

Quote strings containing commas, special characters, or values that YAML might interpret as another type:

~~~yaml
net:
  bindIp: "127.0.0.1,mongo1.example.internal"
~~~

In YAML, `*` denotes an alias. If you need wildcard binding using MongoDB syntax, quote it and perform a security evaluation:

~~~yaml
net:
  bindIp: "*"
~~~

**Do not use wildcard binding in production just for convenience:** it opens the listener across multiple network interfaces.

### 4.5. Windows Paths

In YAML, using forward slashes is the easiest way to avoid escaping issues:

~~~yaml
storage:
  dbPath: "C:/MongoDB/data"

systemLog:
  destination: file
  path: "C:/MongoDB/log/mongod.log"
  logAppend: true
~~~

If using Windows backslashes inside YAML double-quoted strings, pay attention to escaping. Do not assume Windows paths are automatically valid when copying Linux syntax verbatim.

### 4.6. Config File Encoding

Official `mongod`/`mongos` documentation states that configuration files must use **ASCII encoding**; do not rely on MongoDB supporting arbitrary Unicode content in YAML.

For reliable compatibility:

- Use only ASCII in config files.
- Write config comments in ASCII English; avoid accented characters in config files.
- Do not create files with a UTF-8 BOM or convert encoding arbitrarily.
- This Markdown guide content uses UTF-8; **do not confuse the lesson's encoding with the encoding of an actual MongoDB config file**.

### 4.7. Do Not Put Secrets in Public Examples

Avoid:

~~~yaml
net:
  tls:
    certificateKeyFilePassword: super-secret-real-password
~~~

When secrets are required, use secret management and server-supported mechanisms for your version; never commit passwords/private keys to a repository.

---

## 5. Starting with --config or -f

### 5.1. mongod

~~~bash
mongod --config /etc/mongod.conf
~~~

Or:

~~~bash
mongod -f /etc/mongod.conf
~~~

### 5.2. mongos

~~~bash
mongos --config /etc/mongos.conf
~~~

Or:

~~~bash
mongos -f /etc/mongos.conf
~~~

If MongoDB was installed via a package and runs as a systemd service, the service already knows its config file. Do not manually launch a second `mongod` process pointing to the same `dbPath` while the service is running.

### 5.3. CLI Flags Corresponding to YAML

| Config file | Corresponding CLI | Process |
|---|---|---|
| `storage.dbPath` | `--dbpath` | mongod |
| `net.port` | `--port` | mongod, mongos |
| `net.bindIp` | `--bind_ip` | mongod, mongos |
| `net.bindIpAll` | `--bind_ip_all` | mongod, mongos |
| `systemLog.path` | `--logpath` | mongod, mongos |
| `systemLog.logAppend` | `--logappend` | mongod, mongos |
| `replication.replSetName` | `--replSet` | mongod |
| `sharding.configDB` | `--configdb` | mongos |
| `sharding.clusterRole: shardsvr` | `--shardsvr` | mongod |
| `sharding.clusterRole: configsvr` | `--configsvr` | mongod |
| `security.keyFile` | `--keyFile` | mongod, mongos |
| `net.tls.mode` | `--tlsMode` | mongod, mongos |
| `net.tls.certificateKeyFile` | `--tlsCertificateKeyFile` | mongod, mongos |
| `setParameter.<name>` | `--setParameter name=value` | Depends on parameter/process |

Consult the official mapping table for all options of your **exact MongoDB Server version**.

### 5.4. CLI Can Override Config File

Suppose the file contains:

~~~yaml
net:
  bindIp: 127.0.0.1
  port: 27017
~~~

And startup runs:

~~~bash
mongod --config /etc/mongod.conf --bind_ip 127.0.0.1,10.20.0.15
~~~

In this situation, `--bind_ip` overrides `net.bindIp`. To know what addresses the process is actually listening on, check the parsed options and active listeners rather than just opening the file.

**Warning:** Do not use this override example to expose a listener to an external network before access control/TLS/firewall protections are in place.

### 5.5. Do Not Treat Every Option as "Last Flag Wins"

Some options are:

- Mutually exclusive.
- Available only on `mongod` or only on `mongos`.
- Removed.
- Required to be paired with another option.
- Supported only in a specific edition/version.
- Disallowed from changing if the deployment already has incompatible metadata/data.

When a conflict occurs, the server may refuse to start. Always check the error log.

---

## 6. Converting CLI Flags to YAML

If you are running a long command:

~~~bash
mongod --dbpath /var/lib/mongodb --port 27017 --bind_ip 127.0.0.1 --logpath /var/log/mongodb/mongod.log --logappend
~~~

you can translate the options into YAML:

~~~yaml
storage:
  dbPath: /var/lib/mongodb

net:
  port: 27017
  bindIp: 127.0.0.1

systemLog:
  destination: file
  path: /var/log/mongodb/mongod.log
  logAppend: true
~~~

MongoDB supports `--outputConfig` to output the equivalent configuration of command-line options in supported versions:

~~~bash
mongod --dbpath /var/lib/mongodb-lab --port 27018 --bind_ip 127.0.0.1 --outputConfig
~~~

**Note:** The command above is a configuration conversion example, not an instruction to start another `mongod` against a data directory already used by a service. Check help/version and output location before using it in automation.

### 6.1. Benefits of Config Files

- Easier to review/diff.
- Easier to track change history.
- Easier to deploy consistently across nodes.
- Less error-prone than long command lines.
- Easier to separate configurations by `mongod`/`mongos`.
- Well-suited for infrastructure as code.

### 6.2. Risks of Config Files

- May contain paths to secrets.
- May be modified outside the deployment pipeline.
- Does not guarantee runtime has reloaded.
- May be overridden by CLI/environment overrides.
- May become incompatible when upgrading the server version.
- The config file on disk and effective running settings can drift apart.

**The config file is desired state; effective parsed startup settings are partial evidence of actual state.**

---

## 7. Configuring Standalone mongod in a Local Lab

A minimal template for a self-managed lab on Linux, **binding only to localhost**:

~~~yaml
systemLog:
  destination: file
  path: /var/log/mongodb/mongod-lab.log
  logAppend: true
  verbosity: 0

storage:
  dbPath: /var/lib/mongodb-lab

net:
  bindIp: 127.0.0.1
  port: 27017

operationProfiling:
  mode: off
  slowOpThresholdMs: 100
~~~

### 7.1. Explanation

- `systemLog.destination: file`: writes diagnostic messages to a file.
- `systemLog.path`: log file path.
- `logAppend: true`: appends to the log on startup per configuration semantics.
- `verbosity: 0`: does not enable server-wide verbose debug logging.
- `storage.dbPath`: data directory location.
- `net.bindIp`: listens only on loopback.
- `net.port`: MongoDB port.
- `operationProfiling.mode: off`: disables the database profiler, though it does not disable all slow operation logs.

### 7.2. Preparing Directories and Permissions

Example commands an authorized Linux administrator can run in a lab:

~~~bash
sudo mkdir -p /var/lib/mongodb-lab /var/log/mongodb
sudo chown -R mongodb:mongodb /var/lib/mongodb-lab /var/log/mongodb
~~~

The service user name depends on the installation package. Do not run `chown -R` on a production data directory without verifying ownership, ACLs, and system requirements.

### 7.3. Starting

~~~bash
mongod --config /etc/mongod-lab.conf
~~~

If running `mongod` under a service manager, use the corresponding service configuration instead of launching another process on the same data directory.

### 7.4. Verifying from mongosh

~~~bash
mongosh "mongodb://127.0.0.1:27017/"
~~~

In the shell:

~~~javascript
db.adminCommand({ ping: 1 });
db.adminCommand({ getCmdLineOpts: 1 });
~~~

Do not treat a successful `ping: 1` as proof that authorization/TLS/replication are configured properly; it is only a limited connectivity check.

### 7.5. Should This Config Be Used in Production?

Not as-is. This is only for a local lab; production requires:

- Authentication/authorization.
- TLS.
- Member authentication when running a replica set.
- Backup and DR.
- Network segmentation/firewall.
- Monitoring/logging.
- Least-privilege service account.
- Capacity planning and disk/memory headroom.
- Version/upgrade policy.

---

## 8. storage: Data Path, Engine, and WiredTiger

### 8.1. storage.dbPath

`storage.dbPath` is where `mongod` stores data files:

~~~yaml
storage:
  dbPath: /var/lib/mongodb
~~~

It is **for `mongod` only**.

A dangerous mistake:

1. Actual data resides at `/var/lib/mongodb`.
2. Someone edits the config to `/data/new-mongodb`.
3. The server starts with a new empty path.
4. The application sees an "empty" database as if all data vanished.

The data may still sit at the old path, but starting up on the wrong data dir is a severe incident. **Do not copy/move WiredTiger data files while `mongod` is running without a supported procedure.**

### 8.2. Package Defaults Differ

Common paths:

| Install method | Typical data dir |
|---|---|
| Ubuntu/Debian apt | `/var/lib/mongodb` |
| RHEL/CentOS yum | `/var/lib/mongo` |
| Manual binary Linux/macOS | Usually `/data/db` if not overridden |
| Windows manual | Usually `\data\db` in examples/defaults |
| Container image | Depends on image/volume mapping |

Do not hardcode legacy paths in new deployments; verify the config of the actual service.

### 8.3. WiredTiger

WiredTiger is the default storage engine in modern MongoDB versions.

Options you may encounter:

~~~yaml
storage:
  dbPath: /var/lib/mongodb
  wiredTiger:
    engineConfig:
      cacheSizeGB: 2
    collectionConfig:
      blockCompressor: snappy
~~~

**This is only a syntax illustration.** Do not set cache size arbitrarily in production, especially inside containers with memory limits, because MongoDB already calculates defaults based on the environment and version.

### 8.4. Cache Size and Memory Limits

When tuning cache:

- Measure WiredTiger cache utilization.
- Measure page faults/disk I/O.
- Measure OS/container memory.
- Reserve memory for aggregations, connections, filesystem cache, and other processes.
- Check options/limits in your current server version.

Increasing cache does not always make queries faster. It can cause OOM kills if memory headroom is insufficient.

### 8.5. Journaling

Starting in MongoDB 6.1, journaling is always enabled and `storage.journal.enabled`, `--journal`, and `--nojournal` were removed.

Do not copy an old config like:

~~~yaml
storage:
  journal:
    enabled: false
~~~

into a newer server and expect it to be valid.

When upgrading, review removed options before restarting.

### 8.6. Storage Engine Is Not an Arbitrary Setting

Changing `storage.engine` or data format parameters is not a "one-line YAML edit"; it requires an official migration/backup/upgrade procedure.

---

## 9. net: Port, bindIp, and Secure Networking

### 9.1. net.port

~~~yaml
net:
  port: 27017
~~~

Common defaults by role:

- Standard `mongod`: 27017.
- Shard member `mongod`: commonly 27018.
- Config server member `mongod`: commonly 27019.
- `mongos`: commonly 27017.

These are defaults/conventions, **not a strict rule that every topology must use those exact ports**. Administrators may choose different ports, but must update DNS, firewalls, connection strings, and peers accordingly.

### 9.2. bindIp Specifies Listeners

~~~yaml
net:
  bindIp: "127.0.0.1,mongo1.example.internal"
~~~

The server listens only on the specified network interfaces matching addresses present on the host.

If `mongo1.example.internal` does not resolve to a local address, startup may fail with a bind error.

### 9.3. Binding All Interfaces

Configuration:

~~~yaml
net:
  bindIpAll: true
~~~

allows listening on all interfaces according to platform configuration.

Risks:

- The service can be exposed to untrusted networks.
- Misconfigured firewall rules create unintended access paths.
- Even with authorization/TLS enabled, network segmentation is still required.

**Do not use `bindIpAll: true` to quickly fix a connection error without a security review.**

### 9.4. bindIp and bindIpAll Are Mutually Exclusive

Wrong:

~~~yaml
net:
  bindIp: "127.0.0.1"
  bindIpAll: true
~~~

The server may refuse to start.

Choose one appropriate configuration approach.

### 9.5. Hostnames and Replica Sets

Modern MongoDB versions recommend or enforce hostnames for replica set configuration instead of raw IPs, especially in deployments requiring split-horizon DNS and TLS SANs.

Do not change a hostname/IP in a replica set merely by editing `bindIp`; you must also account for:

- `rs.conf()` member hostnames.
- DNS resolution from all members/clients.
- TLS certificate SANs.
- Replica set reconfiguration.
- Firewall/connectivity.
- Sharded cluster metadata.

### 9.6. IPv6

If deploying IPv6, verify compatibility of `net.ipv6` and `net.bindIp`, and ensure OS/network policies support it. Do not assume adding an IPv6 address to `bindIp` automatically enables all IPv6 behavior across versions.

---

## 10. systemLog: Destination, Log Path, Rotation, and Verbosity

### 10.1. Config Example

~~~yaml
systemLog:
  destination: file
  path: /var/log/mongodb/mongod.log
  logAppend: true
  verbosity: 0
  timeStampFormat: iso8601-utc
~~~

### 10.2. Log Destination

Depending on deployment:

- File: `systemLog.destination: file`.
- Stdout/stderr: via service manager/container.
- Syslog on supported platforms/configurations.

If the destination is a file, prepare the path and permissions. If stdout is handled by a log collector, do not manually redirect it to an unrotated file.

### 10.3. Log Append and Rotation

`logAppend: true` prevents truncating/overwriting the log on startup per configuration semantics.

MongoDB provides log rotation; example command:

~~~javascript
db.getSiblingDB("admin").runCommand({
  logRotate: 1
});
~~~

Modes such as `rename`/`reopen` affect how MongoDB coordinates with OS logrotate.

Do not delete an open `mongod.log` file and expect the server and collector to handle it seamlessly.

### 10.4. Verbosity

`verbosity: 0` does not mean "log nothing". MongoDB still emits informational, warning, error, and slow-operation messages.

Increasing global verbosity can generate excessive logs and expose sensitive data. When debugging, prefer targeted component verbosity for a controlled duration.

### 10.5. Distinguishing Diagnostic Logs from the Profiler

- `systemLog` handles diagnostic messages.
- `operationProfiling` controls the profiler/slow operations mechanism.
- `system.profile` is the collection storing profile records when profiling is enabled.

Do not change `systemLog.verbosity` and assume all `system.profile` behavior will change accordingly.

### 10.6. Log Path Too Small or Missing Permissions

Startup failures can be caused by:

- Missing log directory.
- Service user lacking write permissions.
- Read-only filesystem.
- Disk full.
- SELinux/AppArmor policy.
- Log path colliding with another process's file.

Read the service error output before blindly changing permissions.

---

## 11. security.authorization: Enabling Access Control

### 11.1. Right Process

`security.authorization` is a setting for `mongod`:

~~~yaml
security:
  authorization: enabled
~~~

It enables role-based access control. Do not simply add this exact field to `mongos.conf` and treat the entire sharded cluster as having authentication configured.

### 11.2. No Admin User Yet: Preparing Bootstrap

Enabling access control abruptly on an instance with no users can complicate administration if there is no bootstrap procedure.

MongoDB provides the localhost exception under specific conditions to create the first user when authorization is enabled. This is **not** a general recovery fallback for a lost admin account.

In production, you must have:

- A prepared admin principal.
- Authentication database and roles.
- Credential rotation.
- A backup/recovery path.
- Internal authentication for replica set/sharded components.

### 11.3. Replica Set mongod Requires Internal Authentication

For a replica set with authorization enabled, members must prove their identity to one another, for example via a keyfile or X.509.

Do not just add:

~~~yaml
replication:
  replSetName: rs0

security:
  authorization: enabled
~~~

and skip member authentication when the topology requires it. That is not a complete production configuration.

### 11.4. Keyfile

An example replica set member using a keyfile:

~~~yaml
replication:
  replSetName: rs0

security:
  keyFile: /secure/mongodb/keyfile
  authorization: enabled
~~~

MongoDB documentation notes that `security.keyFile` **implies enabling authorization** in the `mongod` context.

The keyfile must:

- Be securely distributed to the right members.
- Have matching contents across members.
- Have strict file permissions (especially on Unix).
- Have rotation/overlap managed via a runbook.
- Not live in Git or public container images.

### 11.5. A Keyfile Is Not an Application Password

`security.keyFile` is an internal shared secret for member authentication, **not** the `app_user` SCRAM password in a Java URI.

### 11.6. Secrets and Access Controls

Do not grant an application account `root` privileges just because you hit `Unauthorized`. Fix the users/roles properly rather than disabling authorization.

---

## 12. TLS: Securing Traffic in Configuration

### 12.1. TLS Server Config

Self-managed example:

~~~yaml
net:
  bindIp: "127.0.0.1,mongo1.example.internal"
  port: 27017
  tls:
    mode: requireTLS
    certificateKeyFile: /secure/mongodb/server.pem
    CAFile: /secure/mongodb/ca.pem
~~~

This requires:

- A valid server certificate/private key.
- Proper CA trust.
- Hostname/SAN match.
- Client TLS configuration.
- Filesystem permissions on the PEM/key files.

### 12.2. TLS Does Not Replace Authorization

TLS protects transport and verifies endpoints. Users can still authenticate via SCRAM:

~~~text
mongodb://app_user:<SECRET>@mongo1.example.internal:27017/commerce?authSource=admin&tls=true
~~~

Here `authSource=admin` determines where credentials are looked up if the user was created in `admin`; TLS and `authSource` serve two different purposes.

### 12.3. TLS Client Certificates vs. SCRAM

The server can accept TLS clients without a client certificate if configured to allow it, and then authenticate the user with SCRAM.

If using `MONGODB-X509`, the client needs a certificate/private key and user identity is mapped via `$external`.

Do not enforce client certificates cluster-wide without checking SCRAM clients that do not present a client cert.

### 12.4. Internal TLS Between Cluster Members

A replica set or sharded cluster must account for all connections:

- Application → mongos/mongod.
- Mongos → config servers/shards.
- Mongod member → member.

A TLS certificate intended solely for client endpoints may not satisfy all internal authentication and cluster TLS requirements.

### 12.5. Do Not Disable Certificate Validation

Options that skip certificate or hostname verification remove peer verification and open MITM risks.

When encountering a TLS handshake error, check:

- CA chain.
- SAN hostname.
- Expiry.
- Key/cert match.
- EKU.
- DNS.
- TLS mode.
- Driver trust store.

Do not fix it by allowing invalid certificates in production.

---

## 13. Configuring a Replica Set Member

Suppose `rs0` consists of three `mongod` instances, each running on its own host with dedicated data and log paths.

Template for **the first member's `mongod`**, in a deployment with keyfile, users/roles, and security bootstrap prepared:

~~~yaml
systemLog:
  destination: file
  path: /var/log/mongodb/mongod.log
  logAppend: true

storage:
  dbPath: /var/lib/mongodb

net:
  bindIp: "127.0.0.1,mongo1.example.internal"
  port: 27017
  tls:
    mode: requireTLS
    certificateKeyFile: /secure/mongodb/mongo1.pem
    CAFile: /secure/mongodb/ca.pem
    allowConnectionsWithoutCertificates: true

replication:
  replSetName: rs0

security:
  authorization: enabled
  keyFile: /secure/mongodb/keyfile
~~~

**This is a skeleton**, not a copy-paste config for arbitrary clusters. You must verify internal member TLS, certificate identity, topology, and keyfile policy. The `allowConnectionsWithoutCertificates: true` setting in the example allows TLS clients using SCRAM without a client cert as configured; it does not disable TLS.

### 13.1. Replica Set Initialization Is a Separate Operation

Starting with:

~~~yaml
replication:
  replSetName: rs0
~~~

only identifies the replica set name the process intends to join. It **does not automatically run `rs.initiate()`** or create membership configuration.

In `mongosh` with appropriate privileges:

~~~javascript
rs.status();
rs.conf();
~~~

Only run `rs.initiate()`/`rs.reconfig()` according to a runbook, never arbitrarily on an active cluster.

### 13.2. Hostnames Must Stay Consistent

Members in `rs.conf()`, DNS, TLS SANs, and firewall rules must align.

If changing a member's port or hostname:

1. Update the process config.
2. Update the replica set config if required.
3. Update DNS/TLS/firewalls.
4. Assess the impact on elections and client topology.
5. Perform a rolling change.

Do not change `net.port` on one node and assume the replica set will automatically discover the new address.

### 13.3. Rolling Restart

A common procedure for safe changes when topology permits:

1. Record baseline `rs.status()` and replication lag.
2. Prepare and review the config.
3. Update one secondary.
4. Restart the secondary via the service manager.
5. Wait until it is healthy, `SECONDARY`, and caught up.
6. Repeat for the other secondary if present.
7. Finally handle the primary via the stepdown/rolling upgrade runbook.
8. Verify majority/write availability and application errors.
9. Record change results and rollback state.

Do not follow this rigidly if the cluster has only two data-bearing members, is degraded, or cannot maintain majority.

### 13.4. Impact of Keyfile/TLS Rotation

Changing member authentication is high-risk. If members stop trusting each other after a restart, a node can become isolated.

You must follow a MongoDB-supported overlap/transition plan when rotating certificates, CAs, or keyfiles.

---

## 14. Sharded Cluster: Distinguishing Config Server, Shard, and mongos

A sharded cluster has at least these component groups:

1. Config server replica set.
2. Shards (typically replica sets).
3. Mongos routers.

### 14.1. Config Server mongod

A config server member has a dedicated configuration:

~~~yaml
sharding:
  clusterRole: configsvr

replication:
  replSetName: cfgRS

storage:
  dbPath: /var/lib/mongodb-config

net:
  bindIp: "127.0.0.1,cfg1.example.internal"
  port: 27019
~~~

This covers only the core role settings; production requires TLS, internal authentication, system logging, and appropriate security controls.

### 14.2. Shard mongod

A shard member can be configured as:

~~~yaml
sharding:
  clusterRole: shardsvr

replication:
  replSetName: shardA

storage:
  dbPath: /var/lib/mongodb-shard

net:
  bindIp: "127.0.0.1,shard-a1.example.internal"
  port: 27018
~~~

Each shard replica set has its own name and membership.

### 14.3. Mongos Router

The router uses `sharding.configDB` to locate the config server replica set:

~~~yaml
sharding:
  configDB: cfgRS/cfg1.example.internal:27019,cfg2.example.internal:27019,cfg3.example.internal:27019

net:
  bindIp: "127.0.0.1,mongos1.example.internal"
  port: 27017

systemLog:
  destination: file
  path: /var/log/mongodb/mongos.log
  logAppend: true
~~~

This skeleton omits security. `mongos` does not have a `storage.dbPath` for collection data.

### 14.4. Mongos with Keyfile/TLS

In a cluster configured with keyfile internal authentication, `mongos` may require:

~~~yaml
security:
  keyFile: /secure/mongodb/keyfile

net:
  tls:
    mode: requireTLS
    certificateKeyFile: /secure/mongodb/mongos1.pem
    CAFile: /secure/mongodb/ca.pem
~~~

Combine this with the `sharding.configDB` and listener settings above; do not use one fragment in isolation. If the cluster uses X.509 member authentication, the configuration differs from keyfile.

### 14.5. configDB Is Not a Regular MongoDB URL

Important format:

~~~text
<config-server-replica-set-name>/<host1>:<port1>,<host2>:<port2>,...
~~~

Example:

~~~text
cfgRS/cfg1.example.internal:27019,cfg2.example.internal:27019,cfg3.example.internal:27019
~~~

Do not write:

~~~text
mongodb://cfg1.example.internal:27019
~~~

into `sharding.configDB` when the version requires the replica set connection identifier format.

### 14.6. Changing the Config Server List

This is not just editing hostnames in YAML. You must ensure config RS membership, DNS, security, router configuration, and supported reload/restart procedures are aligned.

A `mongos` pointing to a wrong `configDB` may fail to start or fail to route properly.

### 14.7. Mongos Is Not a Shard Member

Do not put:

~~~yaml
storage:
  dbPath: /data/shard

replication:
  replSetName: shardA
~~~

into `mongos.conf` expecting the router to store data like a shard `mongod`.

---

## 15. systemd and Service Managers on Linux

### 15.1. How the Service Starts

With apt/yum packages, MongoDB is usually managed by systemd:

~~~bash
sudo systemctl status mongod
~~~

To inspect the unit config and start command (with sufficient permissions):

~~~bash
systemctl cat mongod
~~~

Use the service unit to verify:

- Which config file is loaded.
- Service user/group.
- Environment overrides.
- Restart policy.
- Working directory.
- Startup dependencies.

### 15.2. Do Not Arbitrarily Change Service Defaults

MongoDB docs note that package init scripts may depend on:

- `systemLog.path`.
- `storage.dbPath`.
- `processManagement.fork`.
- `MONGODB_CONFIG_OVERRIDE_NOFORK`.

Changing these values can prevent the service from starting under package assumptions.

### 15.3. Restart and Reload Are Not the Same

A startup-only change requires restarting the process. Do not assume:

~~~bash
sudo systemctl reload mongod
~~~

reloads all configuration; many MongoDB options cannot be reloaded dynamically.

When applying a new config:

~~~bash
sudo systemctl restart mongod
~~~

**only execute per runbook**, after review, approval, and backup/HA checks. Restarting a primary `mongod` can trigger failover and drop connections.

### 15.4. Checking Logs on Startup Failure

~~~bash
sudo systemctl status mongod
journalctl -u mongod -n 100 --no-pager
~~~

If the server writes to a separate diagnostic log file, also check the file specified in `systemLog.path`.

### 15.5. processManagement.fork

When running under a service manager, `mongod` should typically run in the foreground so the service manager tracks its lifecycle as packaged.

Adding:

~~~yaml
processManagement:
  fork: true
~~~

without checking unit defaults can break service status, stop, and restart tracking.

### 15.6. One Process per dbPath

Never run two `mongod` processes writing to the same `storage.dbPath`. File locking and data files do not support shared access like that.

When encountering "Address already in use" or "Unable to lock data directory", check which process is currently running before deleting lock files or killing processes.

---

## 16. Windows Service and Config File

### 16.1. Windows Paths

Example `C:/MongoDB/conf/mongod.cfg`:

~~~yaml
storage:
  dbPath: "C:/MongoDB/data"

systemLog:
  destination: file
  path: "C:/MongoDB/log/mongod.log"
  logAppend: true

net:
  bindIp: "127.0.0.1"
  port: 27017
~~~

Create the directories and set appropriate ACLs for the service account before starting.

### 16.2. Testing in an Elevated Terminal

~~~powershell
mongod --config "C:\MongoDB\conf\mongod.cfg"
~~~

This starts the process in the terminal when not using a Windows Service. Do not run it if a MongoDB Windows Service is already using the same `dbPath` or port.

### 16.3. Checking the Windows Service

~~~powershell
Get-Service -Name MongoDB
~~~

Inspect the actual startup command registered in Service Control Manager; do not assume it uses the file you just edited.

### 16.4. processManagement.fork Is Not Supported on Windows

MongoDB documentation states that `processManagement.fork` is not supported on Windows. Do not copy a Linux config and leave `fork: true` in a Windows server config.

### 16.5. File Permissions

Windows requires appropriate ACLs on:

- Data directory.
- Log directory.
- Config file.
- TLS private key / certificate.
- Internal keyfile if used.
- Backup file paths.

Run the service under a least-privilege account rather than defaulting to LocalSystem/root-like access unnecessarily.

---

## 17. Docker/Containers and Kubernetes

### 17.1. Containers Typically Use a Foreground Process

Container runtimes expect the main process to run in the foreground:

~~~text
ENTRYPOINT/CMD
  └── mongod --config /etc/mongod.conf
~~~

Do not enable `processManagement.fork: true` inside a container just because the bare-metal host previously used daemon mode.

### 17.2. Data Volumes

Example architecture:

```text
Host/Persistent Volume
       │
       └── /data/db inside container
                 │
               mongod
~~~

If a container is recreated without a persistent volume attached, data may not persist as expected. `storage.dbPath` must match the mounted volume path.

### 17.3. ConfigMap/Secret

In Kubernetes:

- ConfigMap is typically used for non-secret configuration.
- Secret is used for sensitive values/credentials, though RBAC and encryption policies are still required.
- PersistentVolumeClaim holds data.
- StatefulSet/Operator orchestrates members.
- Liveness/readiness probes must reflect topology.
- TLS/keyfiles are mounted via volumes/secrets with proper permissions.

Do not store private keys in a ConfigMap or bake them into an image/repository.

### 17.4. Operator Configuration Is the Source of Truth

If a MongoDB Operator manages the cluster, editing `mongod.conf` directly inside a Pod will be lost when the Pod is recreated.

Update the Custom Resource/Operator spec using the supported method.

### 17.5. Pod Restarts and Replica Sets

Restarting multiple Pods at once can cause:

- Loss of majority.
- Elections.
- Increased replication lag.
- Server selection timeouts on clients.
- Temporary write unavailability.

Configure a proper rollout strategy, PodDisruptionBudget, and quorum checks instead of restarting an entire StatefulSet simultaneously.

### 17.6. Atlas Managed MongoDB

With Atlas, customers configure supported options through the Atlas UI/API rather than editing `mongod.conf`/`mongos.conf` directly.

Do not use self-managed `systemctl`/`kubectl` procedures on Atlas-managed infrastructure.

---

## 18. Startup Parameters and Runtime Server Parameters

These are two distinct concepts.

### 18.1. Startup Options

A startup option is read when the process starts:

~~~yaml
net:
  port: 27017

storage:
  dbPath: /var/lib/mongodb
~~~

Changing these values in the file while the process is running **does not automatically change the listener or data path**.

An appropriate restart or migration procedure is normally required.

### 18.2. Server Parameters

MongoDB provides server parameters to tune deployment behavior.

Startup configuration example:

~~~yaml
setParameter:
  enableLocalhostAuthBypass: false
~~~

Or via CLI:

~~~bash
mongod --setParameter enableLocalhostAuthBypass=false --config /etc/mongod.conf
~~~

**Note:** `enableLocalhostAuthBypass: false` is just an example of a security-related server parameter; disabling the localhost exception before an admin user exists can affect bootstrapping. Do not apply it without a runbook for creating the first user.

### 18.3. Runtime setParameter Command

When a parameter is documented as **runtime-changeable**, you can run:

~~~javascript
db.getSiblingDB("admin").runCommand({
  setParameter: 1,
  PARAMETER_NAME: "VALUE"
});
~~~

The snippet above is an illustrative template; it is not executable verbatim because the parameter name and value are placeholders.

A real command requires:

- Exact parameter name.
- Correct data type.
- Appropriate admin privileges.
- Runtime support on your current version and process.

### 18.4. Not Every Parameter Is Runtime-Changeable

MongoDB docs distinguish between:

- Startup-only.
- Startup and runtime.
- `mongod`-only.
- `mongos`-only.
- Role/edition/version-specific.
- Deprecated/removed.

If you attempt `setParameter` on a startup-only parameter, the server will return an error. Do not attempt to force it via direct storage edits.

### 18.5. setParameter Differs from setProfilingLevel/setLogLevel

Some dynamic settings have dedicated helpers:

~~~javascript
db.getSiblingDB("admin").setLogLevel(1, "network");
~~~

Or:

~~~javascript
db.getSiblingDB("commerce").setProfilingLevel(1, {
  slowms: 100,
  sampleRate: 0.1
});
~~~

These helpers still require privileges and have their own effects and scope. Not every helper is equivalent to changing a startup option.

---

## 19. Reading Effective Configuration with getCmdLineOpts

### 19.1. Main Command

In `mongosh` with required privileges:

~~~javascript
db.getSiblingDB("admin").runCommand({
  getCmdLineOpts: 1
});
~~~

Or the helper:

~~~javascript
db.serverCmdLineOpts();
~~~

The output typically includes:

- `argv`: the arguments used to invoke `mongod`/`mongos`.
- `parsed`: options parsed from the CLI and config file.

### 19.2. Illustrative Output

~~~javascript
{
  argv: [
    "/usr/bin/mongod",
    "--config",
    "/etc/mongod.conf"
  ],
  parsed: {
    config: "/etc/mongod.conf",
    net: {
      bindIp: "127.0.0.1",
      port: 27017
    },
    storage: {
      dbPath: "/var/lib/mongodb"
    },
    systemLog: {
      destination: "file",
      path: "/var/log/mongodb/mongod.log",
      logAppend: true
    }
  },
  ok: 1
}
~~~

This output is illustrative; actual results depend on the binary/version and specified flags.

### 19.3. Why Use getCmdLineOpts?

A classic incident:

- `mongod.conf` specifies `bindIp: 127.0.0.1`.
- The service unit passes `--bind_ip 127.0.0.1,10.0.0.5`.
- An engineer only checks the YAML file and misreads the security posture.

`getCmdLineOpts.parsed` reveals what the process actually parsed at startup.

### 19.4. Do Not Treat parsed as All Runtime Values

`parsed` reflects the parsed startup configuration. A runtime `setParameter` can cause the current effective value to differ from startup, and some server defaults may not appear identically to explicit fields.

Therefore, distinguish:

~~~text
Desired config on disk
       ≠
Parsed startup config
       ≠
Current runtime parameters
       ≠
Cluster metadata / app observed behavior
~~~

### 19.5. Warning About Secrets in Output

`argv`/`parsed` may include paths, sensitive configuration, or options exposed depending on MongoDB version/redaction.

Do not paste raw `getCmdLineOpts` output into public tickets, especially when passwords or secret references are present. Review and sanitize before sharing.

---

## 20. Inspecting Runtime Parameters with getParameter

### 20.1. Reading a Specific Parameter

Example:

~~~javascript
db.getSiblingDB("admin").runCommand({
  getParameter: 1,
  logComponentVerbosity: 1
});
~~~

### 20.2. Checking Additional Permitted Parameters

~~~javascript
db.getSiblingDB("admin").runCommand({
  getParameter: 1,
  diagnosticDataCollectionEnabled: 1
});
~~~

**Do not assume every parameter exists on every MongoDB Server version.** If a parameter is absent or restricted on a managed deployment, the command may return an error. Choose parameters from the official reference table.

### 20.3. getParameter Does Not Replace getCmdLineOpts

- `getCmdLineOpts`: parsed startup CLI/config options.
- `getParameter`: current or supported value of a server parameter.
- `serverStatus`: runtime statistics.
- `hello`: topology/role information.
- `rs.status()`: replica set health.

Each source answers a different question.

### 20.4. Changing Log Verbosity at Runtime

In an authorized lab:

~~~javascript
const admin = db.getSiblingDB("admin");

admin.setLogLevel(1, "network");

// After investigation, restore the exact original value.
admin.setLogLevel(0, "network");
~~~

In production, record the **original value**, including inheritance settings; do not assume `0` is the exact rollback value in every case.

### 20.5. setParameter Does Not Always Persist Across Restarts

If a parameter is changed at runtime without being written into the startup config or management layer, a restart may revert it to its default or configured value.

Therefore, a runbook must distinguish:

1. Temporary change for debugging.
2. Permanent change via IaC/config.
3. Verifying both runtime and startup sources of truth.
4. Preventing drift after restarts.

---

## 21. Parameter Groups to Know

| Group | Examples | Process | Impact |
|---|---|---|---|
| Network | `net.port`, `net.bindIp`, `net.ipv6` | mongod/mongos | Listener/connectivity |
| TLS | `net.tls.mode`, `certificateKeyFile`, `CAFile` | mongod/mongos | Encryption/trust |
| Storage | `storage.dbPath`, WiredTiger cache | mongod | Files/IO/cache |
| Replication | `replication.replSetName`, oplog settings | mongod | Replica set membership |
| Sharding role | `sharding.clusterRole` | mongod | Shard/configsvr |
| Router config | `sharding.configDB` | mongos | Config RS routing |
| Security | `security.authorization` | mongod | RBAC |
| Member auth | `security.keyFile`, cluster auth mode | mongod/mongos by role | Cluster identity |
| Logging | `systemLog.*` | mongod/mongos | Diagnostics |
| Profiling | `operationProfiling.*` | mongod | Profile/slow ops |
| Process | `processManagement.*` | mongod/mongos by OS | Startup lifecycle |
| Server params | `setParameter.*` | Depends on parameter | Features/tuning |
| Auditing | `auditLog.*` | Edition/version specific | Security audit |

### 21.1. Startup-Only or Runtime?

There is no rule such as "all `net` options are startup-only, all `setParameter` options are runtime".

Best practice:

1. Select an option/parameter.
2. Check the reference for your exact Server version.
3. Verify `Available for mongod/mongos`.
4. Verify `Available at startup/runtime`.
5. Assess operational impact.
6. Apply the change only through a supported mechanism.

### 21.2. Startup Parameters May Have Feature Dependencies

For example, a server parameter related to query execution, sharding, or security may only be supported when the corresponding role or feature is enabled. Configuring it without understanding its dependencies can cause startup failures or unintended behavior.

---

## 22. External Configuration Values and Expansion Directives

Some MongoDB versions support **external configuration values** to retrieve settings from external sources.

Documented directives include:

- `__rest`: fetches from a REST endpoint.
- `__exec`: executes an external command to supply a value.

To permit expansion, use the option:

~~~bash
mongod --config /etc/mongod.conf --configExpand "rest,exec"
~~~

Or:

~~~bash
mongos --config /etc/mongos.conf --configExpand "rest,exec"
~~~

### 22.1. Purpose

- Keep certain secrets out of static config files.
- Integrate external data sources aligned with secret management systems.
- Allow dynamic configuration via MongoDB-supported mechanisms.

### 22.2. Serious Risks

`__exec` can invoke external commands in the startup context. If an attacker modifies the config or command path, they can affect the process.

MongoDB docs enforce strict file permission requirements for expansion directives on Unix-like systems.

Do not use:

~~~yaml
# Example only; do not paste an untrusted command here.
~~~

and never allow external clients/users to inject shell commands into the configuration.

### 22.3. Do Not Enable configExpand Unnecessarily

If a config file uses directives while startup does not permit expansion, the server may fail to start.

Conversely, enabling `--configExpand "rest,exec"` without justification widens the permitted attack surface.

Prefer whitelisting only the strictly required directives, using trusted sources, and enforcing tight file permissions.

### 22.4. Where Should Secrets Live?

Options include:

- Secret manager.
- Mounted files with strict permissions.
- Operator/Kubernetes Secret.
- OS secure store.
- Supported external expansion configuration.
- TLS key material in a protected volume.

Do not keep private keys or passwords directly in Git or command history.

### 22.5. Mind the Lifecycle

If a secret changes in an external source while the process only reads it at startup, the effective value may not update until the process reloads or restarts through a supported mechanism.

Verify the specific rotation semantics rather than assuming "updating the secret manager makes MongoDB use the new secret immediately."

---

## 23. Validating Configuration Before Changing Production

### 23.1. Schema/Version Review

For every change, verify:

- Exact option name and spelling.
- Valid YAML structure.
- Correct data types.
- Exact case-sensitive enum values.
- Correct process (`mongod` vs. `mongos`).
- No mutually exclusive options.
- Edition/version support.
- Startup-only vs. runtime behavior.
- OS path permissions.
- Cluster topology dependencies.

### 23.2. Use the Official Mapping Reference

When converting legacy command-line flags to YAML:

- Use the `Self-Managed Configuration and Command-Line Options Mapping` reference.
- Do not guess the camelCase form of every CLI flag.
- Do not copy deprecated flags.
- Do not use mongo shell options as `mongod` server options.

### 23.3. Test in an Isolated Lab

A YAML file can parse cleanly and still fail to start because of:

- Port already in use.
- `dbPath` locked.
- Missing CA/PEM/keyfile.
- Unresolved DNS.
- Replica set role/security mismatch.
- Insufficient OS permissions.

**Never use a production data directory to test an unfamiliar config file.**

### 23.4. Validate with --outputConfig Where Appropriate

MongoDB supports `--outputConfig` to render config/CLI options into YAML on supported versions. It is a useful conversion and diagnostic aid.

However, it does not replace startup testing in an isolated environment, connectivity checks, cluster authentication tests, or application smoke tests.

### 23.5. Verify Effective Config After Startup

~~~javascript
const admin = db.getSiblingDB("admin");

printjson(admin.runCommand({
  getCmdLineOpts: 1
}));
~~~

Then verify:

- Network listener.
- TLS handshake.
- `db.adminCommand({hello:1})`.
- `rs.status()` for replica sets.
- `sh.status()` for sharded clusters/appropriate roles.
- Health/metrics.

Do not treat a successful `getCmdLineOpts` call as complete end-to-end validation.

---

## 24. Runbook for Safely Changing mongod Configuration

### Step 1 — Define Scope

Record:

~~~text
Change ID:
Environment:
Cluster:
Replica set:
Member host:
Binary version:
FCV:
Config file path:
Service manager:
Owner:
Rollback owner:
Maintenance window:
~~~

### Step 2 — Snapshot Current State

- Back up the current config in a controlled repository.
- Capture sanitized `getCmdLineOpts`.
- Capture relevant `getParameter` values.
- Capture `rs.status()` / member health.
- Measure application p95/p99, CPU, memory, disk, and lag.
- Verify backups and recovery readiness.

Do not dump raw secrets into change tickets.

### Step 3 — Review the Change

Check against:

- Version support.
- Startup-only/runtime nature.
- Security impact.
- Network/TLS/DNS.
- Replication/quorum.
- Disk/storage path.
- Service user permissions.
- Compatibility across members.

### Step 4 — Test in Staging/Canary

- Use an equivalent configuration.
- Test startup.
- Test authentication/TLS.
- Test replica membership.
- Test the application.
- Watch for log warnings.

### Step 5 — Roll Out in Order

If no restart is needed and the parameter supports runtime changes:

- Apply the change via the appropriate API.
- Observe and verify effectiveness.
- Sync IaC if persistence is required.

If a restart is required:

- Perform a topology-aware rolling restart.
- Avoid losing majority.
- Wait for replication catch-up.
- Verify status between each step.

### Step 6 — Verify

- Process is running.
- Parsed options are correct.
- Runtime parameters are correct.
- Port/bind/TLS are correct.
- Replica set/sharded routing is healthy.
- Application queries succeed.
- Metrics have not degraded.

### Step 7 — Rollback

- Restore the exact previous config/parameter values.
- Restore secrets/trust chains if rollback is supported.
- Restart per runbook if required.
- Observe healthy state.
- Document the event timeline.

### Step 8 — Close Out

- Update the config repository/operational docs.
- Clear temporary debug overrides.
- Archive metrics.
- Write a post-change review.

---

## 25. Rolling Changes for Replica Sets: Key Details

### 25.1. Initial State

Suppose:

~~~text
rs0:
  mongo-a PRIMARY
  mongo-b SECONDARY
  mongo-c SECONDARY
~~~

You want to update the TLS certificate or command logging across all three members.

### 25.2. Preconditions

- All members are healthy.
- No rollback risk or large replication lag.
- No election in progress.
- Majority can be maintained while one node restarts.
- New certificate/CA is trusted by members and clients per the transition plan.
- Backup/rollback plan is ready.

### 25.3. Secondaries First

1. Update config/cert on `mongo-b`.
2. Restart `mongo-b` via its service manager.
3. Wait until it returns to `SECONDARY`.
4. Check replication lag.
5. Repeat with `mongo-c`.

### 25.4. Primary Last

Use a controlled stepdown/maintenance procedure per runbook, then restart the former primary once a new healthy primary is elected.

Do not simply run `systemctl restart mongod` on the primary without accounting for writer impact.

### 25.5. Keyfile or clusterAuthMode

This category carries higher risk than logging changes. Use a MongoDB-supported protocol/transition path; never swap all credentials at once and break inter-member authentication.

### 25.6. If the Cluster Is Degraded

If only one healthy primary remains without sufficient redundancy, restarting can cause an outage. Re-evaluate the change window and risk instead of blindly following the checklist.

---

## 26. Changing mongos Configuration in a Sharded Cluster

### 26.1. Multiple mongos Instances Are Typically Deployed

Example:

~~~text
App clients
  ├── mongos-a
  └── mongos-b
         │
     Sharded cluster
~~~

When updating `mongos` router config, you can usually update one router while routing traffic through the other, **provided clients/topology/load balancers support it**.

### 26.2. Do Not Modify Every Router at Once

A standard workflow:

1. Confirm config server RS and shards are healthy.
2. Check `sharding.configDB` and TLS/keyfile.
3. Update `mongos-a`.
4. Restart `mongos-a` per runbook.
5. Verify client routing through `mongos-a`.
6. Monitor server selection/errors.
7. Update `mongos-b` once the first router is healthy.

### 26.3. Router Config and Cluster Metadata

Changing `sharding.configDB` in the `mongos` file does not alter config server RS membership. You must know the actual members of the config server RS.

Similarly, changing the port on `mongos` requires updating application URIs, service discovery, and load balancers.

### 26.4. Mongos Metrics/Logging

`mongos` has diagnostic logs and runtime parameters, but does not store collection data like a shard `mongod`. Do not treat `mongos` as having a shard `storage.dbPath` volume.

---

## 27. Upgrading MongoDB Server and Config Option Compatibility

A configuration file valid on MongoDB 5.0 may be rejected on MongoDB 8.0 or 9.0 due to deprecated or removed options.

### 27.1. Legacy Journaling Option Example

Starting in MongoDB 6.1, journaling is always enabled and legacy journal toggles are no longer supported.

If a config contains `storage.journal.enabled` from an old tutorial, startup during an upgrade may fail.

### 27.2. Networking/Role Rule Changes Example

Newer server versions may enforce different requirements for hostnames, minimum TLS protocols, sharding configuration, or cluster parameters.

Do not rely on documentation from an arbitrary version; consult the MongoDB Manual matching your target server binary.

### 27.3. FCV Differs from Binary Version

Server binary version and Feature Compatibility Version (FCV) are not the same thing.

An upgrade typically follows stages:

1. Upgrade binaries along a supported upgrade path.
2. Wait for cluster health.
3. Evaluate and update FCV per runbook.
4. Enable new version-specific features once prerequisites are met.

You cannot simply edit `setParameter` or a config file to "change the MongoDB version". FCV is a cluster setting managed through a supported procedure.

### 27.4. Removed Parameters

A parameter from an older blog post may not exist in the target version. The server may report an unknown option or invalid value.

Solution:

- Read release notes.
- Read removed/deprecated parameters lists.
- Update config files in staging.
- Review binary/systemd/container compatibility.
- Test rolling upgrades.

### 27.5. Do Not Change storage.engine to Upgrade

Upgrading MongoDB version does not mean you can arbitrarily alter storage engine or data paths. Existing data must go through a supported upgrade path.

---

## 28. Troubleshooting: Server Fails to Start

### 28.1. YAML Parse Error

Symptoms:

~~~text
Failed to parse config file
Invalid YAML
Unrecognized option
~~~

Action:

- Check indentation for tabs.
- Check for duplicate keys.
- Check quoting and data types.
- Check ASCII encoding.
- Read the exact line/option reported by the server.
- Compare against the version-specific config reference.

### 28.2. Unknown Option

Causes:

- Field typo.
- `mongod`-only option placed in `mongos` config.
- Deprecated/removed option.
- Unsupported version/edition.

Do not guess alternative option names; check the official mapping.

### 28.3. Port Already in Use

Example:

~~~text
Address already in use
~~~

Check which service/process holds the port; never kill an unidentified production process.

Linux:

~~~bash
ss -ltnp | grep 27017
~~~

PowerShell:

~~~powershell
Get-NetTCPConnection -LocalPort 27017
~~~

Appropriate privileges are needed to see process details.

### 28.4. Data Directory Inaccessible

Causes:

- Wrong path.
- Directory does not exist.
- Ownership/permissions.
- SELinux/AppArmor.
- Volume not mounted.
- Filesystem read-only/full.
- Data file lock held by another `mongod`.

Do not delete data/lock files indiscriminately. Confirm which process is actually using the directory.

### 28.5. Log Path Inaccessible

The server may fail to write the log file due to permissions or a full disk. If the server crashes before opening its log, stderr or the service journal often holds the critical error.

### 28.6. TLS Certificate Error

Check:

- PEM file exists and is readable.
- Certificate and private key match.
- CA chain/hostname SAN.
- Certificate expiry.
- TLS mode/cluster requirements.
- Member/client certificate trust.

Do not disable verification in production.

### 28.7. Keyfile Authentication Mismatch

Replica set members fail to communicate after a keyfile change:

- Different secret contents.
- Wrong file permissions.
- Cluster auth mode mismatch.
- Host/TLS identity mismatch.
- Improper rolling transition.

Halt the rollout and follow the member auth runbook.

### 28.8. Replica Set Name Mismatch

Server runs:

~~~yaml
replication:
  replSetName: rsDifferent
~~~

while cluster config expects `rs0`. The member may fail to join the proper replica set.

Fix it to match cluster metadata rather than initializing a new replica set over existing cluster data.

### 28.9. Mongos Cannot See Config Server

Causes:

- Invalid `sharding.configDB`.
- DNS/firewall/port issue.
- TLS/CA/keyfile mismatch.
- Unhealthy config server RS.
- Wrong config RS name.
- Routing metadata/incomplete sharded cluster setup.

Do not add `storage.dbPath` to `mongos` as a "fix".

### 28.10. File Edited but Runtime Did Not Change

Possible causes:

- Forgot to restart for a startup-only option.
- Edited the wrong file; service uses another config.
- CLI override.
- Config overwritten by an Operator.
- Runtime parameter changed without updating startup config.
- Inspecting a different `mongod` node or `mongos` router.
- Restart failed, leaving the old process running.

Use `getCmdLineOpts` and service/OS inspection to verify.

### 28.11. Server Starts but App Cannot Connect

Possible causes:

- `net.bindIp` restricted to localhost.
- Firewall.
- Wrong host/port/replicaSet in URI.
- TLS trust/hostname mismatch.
- Wrong `authSource`.
- Authorization roles.
- DNS propagation.
- Load balancer/Service discovery.

Do not solve every connectivity issue with `bindIpAll: true`.

---

## 29. Lab Exercise A: Comparing CLI and YAML in Standalone Mode

### 29.1. Prepare the Environment

Use a local MongoDB lab containing no important data.

Create a config matching:

~~~yaml
systemLog:
  destination: file
  path: /tmp/mongod-config-lab.log
  logAppend: true

storage:
  dbPath: /tmp/mongod-config-lab

net:
  bindIp: 127.0.0.1
  port: 27028
~~~

Create the data directory and ensure the user running `mongod` has permissions. The `/tmp` paths are Linux/macOS lab examples, not production guidance.

### 29.2. Start

~~~bash
mongod --config /path/to/mongod-lab.conf
~~~

Do not start if port 27028 or the `dbPath` is already used by another instance.

### 29.3. Connect

~~~bash
mongosh "mongodb://127.0.0.1:27028/"
~~~

In the shell:

~~~javascript
db.adminCommand({ ping: 1 });
db.adminCommand({ getCmdLineOpts: 1 });
~~~

### 29.4. Test Override

After cleanly stopping the lab `mongod`, run:

~~~bash
mongod --config /path/to/mongod-lab.conf --port 27029
~~~

Connect:

~~~bash
mongosh "mongodb://127.0.0.1:27029/"
~~~

Inspect `getCmdLineOpts.parsed.net.port` and note the difference between the config file and the CLI argument.

Never use CLI overrides to open production ports without review.

### 29.5. Questions

- What port does the config on disk specify?
- What port do the effective parsed startup options report?
- Does changing the port take effect while the server is running?
- Is the CLI flag written back into the YAML file?
- If restarted via a service that only reads the YAML file, which port will be used?

---

## 30. Lab Exercise B: Startup-Only and Runtime Parameters

In the lab:

1. Read `getCmdLineOpts`.
2. Read `getParameter` for a supported parameter.
3. Try changing the log level for a component where permitted.
4. Verify the runtime value.
5. Restore the original value.
6. Identify a startup-only option such as `net.port`.
7. Explain why editing the port in YAML does not change the listener immediately.

Sample commands:

~~~javascript
const admin = db.getSiblingDB("admin");

printjson(admin.runCommand({
  getParameter: 1,
  logComponentVerbosity: 1
}));

// In a permitted lab only:
admin.setLogLevel(1, "network");

// Restore based on actual original value, not assumption.
admin.setLogLevel(0, "network");
~~~

If a component was inheriting its value from a parent (e.g., corresponding to `-1`), rollback must restore the original value rather than blindly setting `0`.

---

## 31. Lab Exercise C: Replica Set Configuration

Given three hosts:

~~~text
mongo1.example.internal
mongo2.example.internal
mongo3.example.internal
~~~

Tasks:

1. Design the `mongod` configuration for each member.
2. Set a matching `replication.replSetName`.
3. Use separate data/log paths on each host.
4. Design TLS SANs/CA and keyfile.
5. Identify who manages users/roles.
6. Describe the `rs.initiate()` or membership configuration procedure.
7. Write a rolling restart plan for changing `systemLog.verbosity` or certificates.
8. Propose when to use runtime `setLogLevel` instead of restarting.

Only deploy on a lab replica set; never run cluster commands arbitrarily on production.

---

## 32. Lab Exercise D: Sharded Cluster Configuration

Given:

~~~text
Config RS: cfgRS
  cfg1:27019
  cfg2:27019
  cfg3:27019

Shard RS: shardA
  shard-a1:27018
  shard-a2:27018
  shard-a3:27018

Routers:
  mongos1:27017
  mongos2:27017
~~~

Write 3 skeleton configs:

1. Config server `mongod`.
2. Shard `mongod`.
3. `mongos` router.

Compare:

- `sharding.clusterRole`.
- `replication.replSetName`.
- `sharding.configDB`.
- `storage.dbPath`.
- `security.keyFile`.
- TLS paths.

Explain why `mongos` does not have `storage.dbPath`.

---

## 33. Lab Exercise E: Startup Incident

A config file contains:

~~~yaml
net:
    bindIp: "127.0.0.1"
  port: 27017

storage:
  dbPath: /var/lib/mongodb

security:
  authorization: Enabled
~~~

Identify:

1. The YAML indentation error.
2. The wrong-case authorization enum value in newer MongoDB versions.
3. OS path/permission checks to perform.
4. How to verify the service is reading the right file.
5. Why you must not fix permissions with `chmod 777`.
6. How to test in a lab before restarting production.

---

## 34. Lab Exercise F: Drift Between File and Runtime

File:

~~~yaml
net:
  bindIp: 127.0.0.1
  port: 27017
~~~

Yet the service starts with:

~~~text
mongod --config /etc/mongod.conf --bind_ip 127.0.0.1,10.0.0.5
~~~

Questions:

- Where is the server actually listening?
- Why is checking only the YAML file insufficient?
- How do you gather evidence using `getCmdLineOpts`?
- What firewall/TLS/authorization checks are needed?
- How do you fix the config source of truth to prevent future drift?

---

## 35. Lab Exercise G: Changes on Kubernetes

A MongoDB cluster managed by an Operator.

1. Identify whether desired state resides in the CR, ConfigMap, or operator spec.
2. Explain why editing files inside a Pod is not durable.
3. Explain how Secrets/TLS/private keys should be handled.
4. Describe how Data PVCs, headless Services, and DNS affect configuration.
5. Design a rolling update that preserves quorum.
6. Track Pod restarts, replica set primary, and lag.
7. Explain why `processManagement.fork: true` is usually unsuitable for containers.

---

## 36. Lab Exercise H: Upgrade Compatibility

A legacy server config contains:

~~~yaml
storage:
  journal:
    enabled: false
~~~

Tasks:

1. Identify the version where this option ceased to be supported.
2. Read the release notes for the target version.
3. Propose how to fix the config.
4. Explain why journaling cannot be disabled in newer versions.
5. Distinguish binary upgrades from changing FCV.
6. Design smoke tests after a rolling upgrade.

---

## 37. Lab Exercise I: Security and Secret Management

A `mongos` config was committed to Git containing a private key password or keyfile content.

Tasks:

1. Assess the risk.
2. Identify which secrets must be rotated.
3. Propose storing secrets via protected files or a secret manager.
4. Compare `__exec`/`__rest` with plain YAML.
5. Explain permission requirements.
6. Propose audit/change controls.
7. Never place real secrets in answers, logs, or tickets.

---

## 38. Lab Exercise J: Writing a Change Runbook

Suppose you are replacing `net.tls.certificateKeyFile` on a production replica set.

The runbook must cover:

1. Scope/approval.
2. Member inventory.
3. Version/FCV.
4. Backups and baseline health.
5. CA trust and SAN checks.
6. Secret/key permissions.
7. Rolling update order.
8. Quorum/stepdown policy.
9. TLS/Java Driver connectivity validation.
10. Monitoring and stop conditions.
11. Rollback/overlap.
12. Post-change cleanup.

---

## 39. Operational Checklist Before Committing Config

### 39.1. Configuration

- [ ] Correct process (`mongod` or `mongos`).
- [ ] Correct MongoDB Server version.
- [ ] Valid YAML indentation and ASCII encoding.
- [ ] No duplicate keys or unsupported options.
- [ ] No mutually exclusive options.
- [ ] No deprecated/removed options.
- [ ] Cross-checked CLI mapping and environment overrides.
- [ ] Clear file source of truth.
- [ ] Plan in place to verify `getCmdLineOpts`.

### 39.2. Network and Storage

- [ ] `net.bindIp` scoped to proper interfaces.
- [ ] Correct port; firewall/DNS aligned.
- [ ] No uncontrolled wildcard binding.
- [ ] `storage.dbPath` points to the right data directory if `mongod`.
- [ ] Storage/volume mounted with sufficient disk space.
- [ ] Owner/ACL/SELinux/AppArmor reviewed.
- [ ] No two `mongod` processes sharing a single `dbPath`.

### 39.3. Replica Set/Sharding

- [ ] `replSetName` matches metadata.
- [ ] Member hostnames/ports/TLS SANs aligned.
- [ ] Keyfile/X.509 member auth synchronized.
- [ ] Config server has `clusterRole: configsvr`.
- [ ] Shard server has `clusterRole: shardsvr`.
- [ ] `mongos` has valid `sharding.configDB`.
- [ ] Rolling restart preserves majority.
- [ ] Never change cluster roles merely by editing YAML outside a runbook.

### 39.4. Security

- [ ] Authorization and users/roles prepared.
- [ ] TLS trust chain/hostname validated.
- [ ] Certificate verification is not disabled.
- [ ] Keyfiles/private keys have restricted permissions.
- [ ] Secrets are absent from Git/logs.
- [ ] Applications are not unnecessarily granted `root`.
- [ ] Rotation and rollback plan exists when changing secrets.

### 39.5. Lifecycle

- [ ] Service manager/Operator source of truth identified.
- [ ] Verified whether options are startup-only or runtime-changeable.
- [ ] Verified whether runtime config persists across restarts.
- [ ] Baseline metrics and parsed options recorded.
- [ ] Tested in staging.
- [ ] Post-rollout monitoring in place.
- [ ] Rollback plan ready.
- [ ] IaC/runbooks updated.

---

## 40. Common Misconceptions

| Misconception | Reality |
|---|---|
| `mongos` also stores collections like `mongod` | `mongos` only routes; data resides on `mongod` shards |
| `mongos` needs `storage.dbPath` | Not in the sense of a `mongod` data directory |
| Having `mongod.conf` means the server uses that file | Must check the service command and `getCmdLineOpts` |
| Editing YAML updates runtime immediately | Many options require a restart |
| Every CLI flag writes back into YAML | No |
| When CLI and YAML conflict, the last value always wins | Some options override, while others are mutually exclusive or fail |
| YAML allows tabs for indentation | No |
| Option names/values are case-insensitive | Many enum names are case-sensitive |
| Saving YAML as UTF-8 Vietnamese is always compatible | MongoDB docs require ASCII config files |
| `bindIpAll` fixes all connection errors | It can dangerously expose the network |
| `security.authorization` on `mongos` works the same as `mongod` | This option is for `mongod` |
| Enabling authorization on a replica set needs no member auth | Appropriate internal authentication is required |
| A keyfile is an app password | It is a shared secret for member authentication |
| TLS replaces all users/roles | TLS transport and authentication/authorization are separate |
| `storage.dbPath` can be changed to hot-migrate data | Requires a migration procedure |
| You can copy WiredTiger files while `mongod` is writing | Not a valid backup/migration method by default |
| `storage.journal.enabled` works on all MongoDB versions | Removed in MongoDB 6.1+ |
| Replica set name can be changed with one line of YAML | Involves metadata, membership, and reconfiguration |
| `mongos` `configDB` is any `mongodb://` URL | Requires the proper config server replica set identifier |
| Restarting all replica set members together is a rolling restart | Can lose majority |
| `systemctl reload` always reloads all MongoDB settings | No |
| `setParameter` works for every setting | Has startup-only, role, and version restrictions |
| `getCmdLineOpts` shows all current runtime values | Primarily parsed startup options; use `getParameter`/metrics |
| Runtime `setParameter` persists permanently | Can reset across restarts |
| `processManagement.fork` suits every OS | Unsupported on Windows and usually unsuitable in containers |
| Editing config inside a Pod is durable | Operator can overwrite it during reconciliation |
| Atlas `mongod.conf` can be edited via SSH | Atlas manages infrastructure/configuration |
| Enabling max log verbosity is harmless | Adds overhead and risks exposing sensitive data |
| A `ping` test is enough to verify config | Must verify TLS/auth/roles/replica/shard/client semantics |
| Rollback is just copying the old file | Also involves runtime settings, secrets, topology, and startup |
| Upgrading the binary does not affect config | Options may be deprecated or removed |
| FCV and binary version are the same | They are different and follow separate upgrade procedures |

---

## 41. Official MongoDB Documentation

The links below provide version-specific references. Select the manual matching the MongoDB Server version you run, as some fields and behaviors change across releases.

- [MongoDB Manual — Self-Managed Configuration File Options](https://www.mongodb.com/docs/manual/reference/configuration-options/)
- [MongoDB Manual — mongod](https://www.mongodb.com/docs/manual/reference/program/mongod/)
- [MongoDB Manual — mongos](https://www.mongodb.com/docs/manual/reference/program/mongos/)
- [MongoDB Manual — Configuration and Command-Line Options Mapping](https://www.mongodb.com/docs/manual/reference/configuration-file-settings-command-line-options-mapping/)
- [MongoDB Manual — Run-time Database Configuration for Self-Managed Deployments](https://www.mongodb.com/docs/manual/administration/configuration/)
- [MongoDB Manual — Convert Command-Line Options to YAML](https://www.mongodb.com/docs/manual/tutorial/convert-command-line-options-to-yaml/)
- [MongoDB Manual — getCmdLineOpts command](https://www.mongodb.com/docs/manual/reference/command/getcmdlineopts/)
- [MongoDB Manual — db.serverCmdLineOpts()](https://www.mongodb.com/docs/manual/reference/method/db.servercmdlineopts/)
- [MongoDB Manual — MongoDB Server Parameters](https://www.mongodb.com/docs/manual/reference/parameters/)
- [MongoDB Manual — getParameter command](https://www.mongodb.com/docs/manual/reference/command/getParameter/)
- [MongoDB Manual — setParameter command](https://www.mongodb.com/docs/manual/reference/command/setParameter/)
- [MongoDB Manual — External Configuration Values](https://www.mongodb.com/docs/manual/core/security-external-config-values/)
- [MongoDB Manual — Configure TLS/SSL](https://www.mongodb.com/docs/manual/tutorial/configure-ssl/)
- [MongoDB Manual — Security Checklist](https://www.mongodb.com/docs/manual/administration/security-checklist/)
- [MongoDB Manual — Self-Managed Internal Authentication](https://www.mongodb.com/docs/manual/core/security-internal-authentication/)
- [MongoDB Manual — Deploy a Self-Managed Replica Set](https://www.mongodb.com/docs/manual/tutorial/deploy-replica-set/)
- [MongoDB Manual — Deploy a Self-Managed Sharded Cluster](https://www.mongodb.com/docs/manual/tutorial/deploy-shard-cluster/)
- [MongoDB Manual — Feature Compatibility Version](https://www.mongodb.com/docs/manual/reference/command/setFeatureCompatibilityVersion/)
- [MongoDB Atlas — Configure Additional Settings](https://www.mongodb.com/docs/atlas/cluster-config/)

> **Version Note:** MongoDB Server, MongoDB Atlas, and orchestration tools have different configuration limits. The illustrative snippets here focus on self-managed MongoDB; always check the documentation for your target version, edition, platform, and topology before deploying. Do not run a production configuration merely because an example YAML looks valid.

---

## 42. Summary

1. **`mongod` and `mongos` have distinct roles**: `mongod` stores and queries data; `mongos` routes queries in a sharded cluster.
2. MongoDB receives configuration via **YAML files, CLI flags, and supported environment/external mechanisms**. Some CLI settings override files, while some options conflict and cause startup errors.
3. **`getCmdLineOpts`** is essential for inspecting parsed startup options, though it does not replace `getParameter`/metrics for runtime state.
4. Distinguish **startup-only options** such as listeners/data paths from **runtime-changeable server parameters**; not every file edit takes effect immediately.
5. **Network, storage, TLS, and authorization** must be evaluated in a security context. `bindIpAll`, private keys, keyfiles, and file permissions require strict control.
6. **Replica sets** require matching `replSetName`, internal authentication, aligned hostnames/certificates, and rolling changes that preserve quorum.
7. **Sharded clusters** require separating config server `mongod`, shard `mongod`, and `mongos` `sharding.configDB`. Never copy one config file across all roles.
8. **systemd/Windows/containers/Operators** differ in startup mechanics and where desired state lives. Editing the wrong file or misusing `fork` can prevent the service from starting.
9. **Upgrades** require checking removed/deprecated options, binary versions, and FCV. Never assume old configs remain compatible.
10. **Safe operations follow baseline → review → staging → rollout → verify → rollback**, rather than editing YAML and hoping every node behaves properly.

**Conclusion:** Good MongoDB configuration management means ensuring the **right process, right version, right source of truth, right blast radius, and a clear recovery path**. A configuration line is only truly "right" when the version supports it, the process has loaded it effectively, the cluster remains healthy, access is protected, and the application operates as intended.
