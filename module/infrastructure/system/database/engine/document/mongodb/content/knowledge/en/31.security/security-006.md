# Authentication Between Replica Set or Sharded Cluster Members in MongoDB

## 1. The Problem: Why Must MongoDB Members Authenticate One Another?

In MongoDB, a **replica set** consists of multiple `mongod` processes maintaining copies of a dataset. A **sharded cluster** also includes `mongos` routers, shards (typically replica sets), and config servers storing routing metadata. These components communicate continuously to:

- Elect and maintain a **primary** in a replica set.
- Stream the **oplog** and sustain secondary replication.
- Synchronize replica set configuration and state.
- Route queries from `mongos` to shards.
- Access metadata from the config server replica set (CSRS).
- Coordinate distributed administrative operations.

If an unauthorized process can impersonate an internal member, the consequences can be worse than a regular client connection: disrupting replication, breaking routing, or gaining privileged cluster-wide access.

**Internal authentication**, also called **membership authentication** or **cluster authentication**, is the mechanism by which MongoDB processes prove they belong to **the same trusted deployment**.

Self-managed MongoDB supports two primary mechanism families:

1. **Keyfile authentication:** members share a secret in a keyfile; MongoDB uses SCRAM challenge-response for membership authentication.
2. **X.509 certificate authentication:** members present X.509 certificates signed by a trusted CA that satisfy membership criteria, over a TLS connection.

Official documentation recommends **X.509 for production**, whereas keyfiles offer a simpler mechanism especially useful for lab/test environments and some existing deployments.

### Learning Objectives

After this lesson, you will be able to:

- Distinguish **internal member authentication**, **client authentication/RBAC**, **TLS encryption**, and **storage encryption**.
- Identify which processes in a replica set or sharded cluster require a consistent internal authentication model.
- Design keyfiles with proper formatting, file permissions, and secret protection policies.
- Understand X.509 certificate attributes: CA, SAN, DN, `O`/`OU`/`DC`, and EKU/KU.
- Read and write `security.keyFile`, `security.clusterAuthMode`, `net.tls.clusterFile`, `net.tls.certificateKeyFile`, and `net.tls.CAFile` configurations.
- Understand the four modes: `keyFile`, `sendKeyFile`, `sendX509`, and `x509`.
- Plan bootstrapping, enabling auth on an unauthenticated cluster, migrating keyfile → X.509, and rotating keys/certificates.
- Diagnose `Authentication failed`, certificate mismatch, permission denied, and lost majority errors without weakening security.
- Design a production checklist covering secret management, TLS, monitoring, least privilege, backups, and recovery.

**Scope:** this lesson focuses on **self-managed** MongoDB. On Atlas or managed services, member-to-member authentication is handled by the platform; do not attempt to edit `mongod.conf` directly using self-managed examples.

---

## 2. Four Frequently Confused Security Layers

| Layer | Question | Example Mechanisms | What It Does Not Do Alone |
| --- | --- | --- | --- |
| **Internal/member authentication** | “Is this process an authorized member of the cluster?” | Shared keyfile; member X.509 | Does not replace ACLs for app users |
| **Client authentication** | “Who is the connecting user or application?” | SCRAM users, X.509 users, external mechanisms | Does not automatically authenticate internal links |
| **Authorization / RBAC** | “What can the authenticated user do?” | Roles `read`, `readWrite`, `clusterMonitor`, etc. | Does not encrypt the network |
| **TLS transport protection** | “Is the channel encrypted and endpoint verified?” | `net.tls.mode: requireTLS`, CA, server cert | Does not define user permissions |
| **Encryption at rest** | “How is data on disk encrypted?” | Storage encryption, cloud KMS | Not a membership keyfile |

A dangerous misconception is “we enabled a keyfile, so inter-node data is encrypted.” **False.** A keyfile only performs **member authentication**; **TLS** is required to encrypt network traffic. Similarly, do not confuse a membership keyfile with an **encrypted storage engine key**: their purposes and rotation procedures differ.

### 2.1. Internal Authentication and User Authentication Are Separate Channels

Example:

```text
Application / mongosh
     |
     | Client auth (e.g., SCRAM user + password)
     v
   mongos
     |
     | Internal auth (keyfile or X.509)
     v
 Shard replica set
```

Clients can log in with SCRAM while `mongos` connects to `mongod` using an **X.509 member certificate**. The two credential types **do not need to match**.

In MongoDB, enabling internal authentication **also enforces client access control/authorization**. Once `security.keyFile` is configured, clients can no longer access resources arbitrarily as they could on an unauthenticated cluster.

### 2.2. Member X.509 Differs from User X.509

- **Member certificate:** proves a `mongod`/`mongos` process belongs to the cluster; receives special internal membership privileges.
- **Client X.509 certificate:** can represent a user in `$external` for `MONGODB-X509` authentication; requires explicit user/role provisioning.
- Never use a **member certificate** as an application client certificate.
- Keep client user DN attributes distinct from cluster membership attributes to avoid confusing identities and privileges.

Never assume that merely holding a CA-signed client certificate qualifies a client as a MongoDB cluster member.

---

## 3. Diagram of Links Requiring Authentication

### 3.1. Replica Set

```text
                       Application
                      Client auth
                           |
                           v
                   mongod R1 (PRIMARY)
                         /   \
             Internal auth   Internal auth
                       /       \
                  mongod R2    mongod R3
                 (SECONDARY)  (SECONDARY)

      Every member-to-member connection is authenticated.
      Every node uses the same cluster mechanism/policy.
```

Members must trust each other's identities. If R3 has a different keyfile with no shared key, it may reach R1/R2's hostname and port, yet **will not be accepted as a valid member**.

### 3.2. Sharded Cluster

```text
                            Application
                                 |
                          Client auth / TLS
                                 |
                           +-----+-----+
                           |  mongos   |
                           | routers   |
                           +-----+-----+
                               /   \
                Member auth   /     \   Member auth
                             v       v
                 +----------------+  +----------------+
                 | Shard A RS     |  | Shard B RS     |
                 | A1 A2 A3       |  | B1 B2 B3       |
                 +----------------+  +----------------+
                             \        /
                              \      /
                               v    v
                       Config Server RS
                          CS1 CS2 CS3
```

In a standard self-managed deployment, **`mongos`, all shard `mongod`s, and all CSRS `mongod`s** must use the same configured membership auth mechanism. With keyfiles, every process must share **at least one common secret**—not just nodes within a single shard.

**Role distinctions:**

- **Primary member of a replica set:** the node accepting writes for that replica set.
- **Primary shard of a database:** a sharding metadata concept, not the “primary MongoDB server” of the entire cluster.
- **Config server replica set:** stores metadata; not an application database for arbitrary logins.
- **`mongos`:** router; does not store full shard data copies.

Having replication within one shard does not mean another shard holds the same data. Internal authentication does not replace replication or backups.

---

## 4. Keyfile Authentication: Shared Secret for Members

A keyfile holds a secret password used for internal authentication between `mongod`/`mongos`. In this mode, MongoDB runs **SCRAM challenge-response**, and authorized processes must know an accepted key.

### 4.1. Technical Requirements

Per the MongoDB Manual:

- A valid key is **6 to 1024 characters** long.
- Key characters must come from the **base64 character set**, not arbitrary UTF-8 or full printable ASCII.
- Keyfile content can be **a single key string** or a **YAML sequence of multiple keys** to support rotation.
- Within a deployment, `mongod`/`mongos` processes must share **at least one key**.
- On **Unix/Linux**, the keyfile must not have group or world permissions; owner-read-only is best practice.
- On **Windows**, MongoDB does not enforce the same Unix permission-bit check, so protect it with Windows ACLs restricted to the service account.
- The keyfile must be locally available on **every host** running a component; do not rely on network shares or removable media.

### 4.2. Generating a Random Keyfile — Linux Lab

**Use only on lab machines/paths; never put keys in Git, Docker images, logs, or chat.**

```bash
# Generate a random secret per MongoDB example.
umask 077
openssl rand -base64 756 > /etc/mongodb/cluster.key

# Owner-readable only; the service account must own/read the file.
chmod 400 /etc/mongodb/cluster.key
```

`openssl rand -base64 756` generates a sufficiently long random value (about 1024 base64 characters excluding newlines). In production, use a secrets manager, distribute securely, and set ownership to the MongoDB service identity.

If `mongod` runs as `mongodb` while the file is owned by `root` with `chmod 400`, `mongod` **cannot read it**. Fix ownership/ACLs appropriately; never work around it with `chmod 777`.

### 4.3. Distributing Keyfiles Securely

- Use a secrets manager or audited secure pipeline for distribution.
- Keep the file out of repositories, CI logs, and container image layers.
- Avoid passing secrets on command lines visible in process listings.
- Allow read access only for the OS account running MongoDB.
- Avoid storing plaintext keyfiles in shared or public backup artifacts.
- Verify the file is unaltered by copy or encoding conversions.
- Never reuse the same keyfile secret across unrelated production, staging, and development environments.

**Never attach keyfile contents** to support tickets or incident chats. Metadata hashes or audits can be used where appropriate, without logging the key itself.

### 4.4. A Keyfile with Multiple Keys

YAML format:

```yaml
# Structural illustration ONLY, NOT real keys.
- "<OLD_BASE64_RANDOM_KEY>"
- "<NEW_BASE64_RANDOM_KEY>"
```

MongoDB will not accept placeholders with `<`/`>` as valid keys; they are strictly illustrative. When deploying, replace them with **two real random base64 keys** of valid length.

Accepting **at least one shared key** enables rolling rotation instead of requiring every member to swap secrets simultaneously.

---

## 5. Configuring a Replica Set with a Keyfile

Suppose three DNS hosts:

```text
mongo1.example.net:27017
mongo2.example.net:27017
mongo3.example.net:27017

Replica set name: rs0
Keyfile: /etc/mongodb/cluster.key
```

Each host has its own data directory and receives the shared membership key.

### 5.1. Configuration File for `mongo1`

Illustrative `/etc/mongod.conf` on **host `mongo1`**:

```yaml
storage:
  dbPath: /var/lib/mongodb

net:
  port: 27017
  bindIp: localhost,mongo1.example.net

replication:
  replSetName: rs0

security:
  keyFile: /etc/mongodb/cluster.key
  authorization: enabled
```

On `mongo2` and `mongo3`, adjust the hostname in `net.bindIp` for each machine while keeping:

- `replication.replSetName: rs0`.
- The keyfile containing the shared secret.
- Consistent internal authentication settings.
- Network policies letting members talk on the right port.

`security.keyFile` **implies authorization is enabled**; `authorization: enabled` makes intent explicit. This is **not yet a complete production config**, because TLS is omitted here. Production requires TLS and proper network/OS protections.

### 5.2. Do Not Substitute IPs for DNS Arbitrarily

MongoDB recommends **DNS hostnames** for replica set and sharded cluster configurations, especially with network horizons. Starting in MongoDB 5.0, IP-only configurations face startup validation constraints and may fail to start.

Member DNS names must:

- Resolve from all peer hosts.
- Point to the right endpoint and port.
- Match certificate SANs when using TLS.
- Remain stable when VMs/containers are replaced.
- Never resolve to unauthorized hosts due to DNS/network misconfiguration.

### 5.3. Enabling Authentication on a New Cluster

Conceptual sequence:

1. Generate a secure keyfile and distribute it to **every member**.
2. Configure `replSetName`, networking, keyfile, and TLS per topology.
3. Start `mongod` on all three hosts.
4. Bootstrap the replica set with `rs.initiate()` in an authorized environment.
5. Use the **localhost exception** where appropriate when no users exist yet to create the first admin user.
6. Create cluster admin and least-privilege application users.
7. Connect clients with valid credentials.
8. Verify `rs.status()`, replication sync, elections, and absence of auth errors.

Run `rs.initiate()` **only when initializing a brand-new replica set**, never again on a live production cluster:

```javascript
rs.initiate({
  _id: "rs0",
  members: [
    { _id: 0, host: "mongo1.example.net:27017" },
    { _id: 1, host: "mongo2.example.net:27017" },
    { _id: 2, host: "mongo3.example.net:27017" }
  ]
});
```

**Localhost exception:** When authorization is enabled and no users exist yet, MongoDB provides a narrow exception to bootstrap the first user from a local connection. It is **not** a long-term operational method. Once the first user is created, the exception closes. Follow the official tutorial and lock down local access; once users exist, never rely on this exception.

### 5.4. Creating the Initial Admin User

Example executed from an authorized bootstrap session connected to the primary:

```javascript
const admin = db.getSiblingDB("admin");

admin.createUser({
  user: "securityAdmin",
  pwd: passwordPrompt(),
  roles: [
    { role: "userAdminAnyDatabase", db: "admin" }
  ]
});
```

`userAdminAnyDatabase` can grant powerful privileges via user/role management; treat this as a strictly protected bootstrap account, **never as an application credential**.

Next, log in as the admin to provision additional least-privilege users. Maintain protected emergency/break-glass accounts and recovery runbooks.

### 5.5. Client Authentication Once Keyfile Is Enabled

`mongosh` example:

```bash
mongosh "mongodb://mongo1.example.net:27017,mongo2.example.net:27017,mongo3.example.net:27017/?replicaSet=rs0&authSource=admin" \
  --username securityAdmin --password
```

The command prompts for the password rather than writing plaintext into shell history. This example **omits TLS options**; when `requireTLS` is active, clients must use TLS and verify CAs/hostnames.

Never hand the internal keyfile to client applications. Clients log in using user-specific credentials.

---

## 6. Adding TLS with a Keyfile: Authentication and Encryption Differ

Enabling a keyfile alone does not encrypt network traffic. In production, best practice is **TLS 1.2+**, valid certificates, CA trust, network segmentation, and membership authentication.

Condensed per-host configuration:

```yaml
net:
  port: 27017
  bindIp: localhost,mongo1.example.net
  tls:
    mode: requireTLS
    certificateKeyFile: /etc/mongodb/tls/mongo1-server.pem
    CAFile: /etc/mongodb/tls/ca.pem

replication:
  replSetName: rs0

security:
  keyFile: /etc/mongodb/cluster.key
  authorization: enabled
```

PEM files must be provisioned beforehand with matching SAN/CA/trust chains and protected private keys. Each server typically holds its own **server certificate/key** matching its hostname.

With **`requireTLS`**:

- Connections to the server require TLS.
- The server presents its certificate for peers to verify.
- The keyfile remains the membership secret.
- Client user authentication still uses its own mechanism such as SCRAM.
- The CA certificate must be distributed wherever verification occurs.

Watch out: a valid TLS server certificate **does not prove a member belongs to the replica set** when `clusterAuthMode` is `keyFile`: membership auth still relies on the keyfile.

---

## 7. Keyfile Configuration for a Sharded Cluster

Example sharded cluster:

```text
Router:    router1.example.net:27017

CSRS:      cfg1.example.net:27019
           cfg2.example.net:27019
           cfg3.example.net:27019

Shard A:   a1.example.net:27018
           a2.example.net:27018
           a3.example.net:27018

Shard B:   b1.example.net:27018
           b2.example.net:27018
           b3.example.net:27018
```

**All** `mongos` and `mongod` instances across shards and config servers must share at least one key when using keyfile membership.

### 7.1. Config Server Replica Set

Config on `cfg1`:

```yaml
sharding:
  clusterRole: configsvr

replication:
  replSetName: cfgRS

net:
  port: 27019
  bindIp: localhost,cfg1.example.net

storage:
  dbPath: /var/lib/mongodb-config

security:
  keyFile: /etc/mongodb/cluster.key
```

`cfg2` and `cfg3` use matching configs with their own hostnames and `dbPath`. Real clusters also need TLS, firewalls, and service-management options. Do not copy this snippet verbatim into production.

### 7.2. Shard Replica Set

Config on `a1`:

```yaml
sharding:
  clusterRole: shardsvr

replication:
  replSetName: shardA

net:
  port: 27018
  bindIp: localhost,a1.example.net

storage:
  dbPath: /var/lib/mongodb-shard

security:
  keyFile: /etc/mongodb/cluster.key
```

Members `a2` and `a3` share `replSetName: shardA`. Shard B uses `replSetName: shardB`. The internal key must still match the CSRS and routers.

### 7.3. `mongos` Router

Config file for the router:

```yaml
sharding:
  configDB: cfgRS/cfg1.example.net:27019,cfg2.example.net:27019,cfg3.example.net:27019

net:
  port: 27017
  bindIp: localhost,router1.example.net

security:
  keyFile: /etc/mongodb/cluster.key
```

`mongos` has no `storage.dbPath` like data-bearing shards. It still requires matching membership auth to connect internally to config servers and shards.

**Note:** Examples in this section show only auth and topology snippets. Production requires TLS on **every** link, version-specific settings, and a deployment plan covering replica set initialization, proper shard registration, users/RBAC, and backups.

### 7.4. Why Putting the Keyfile Only on Shards Is Not Enough

If the keyfile is missing or `clusterAuthMode` mismatches on the router:

```text
Application -> mongos (no internal key)
                     |
                     X  Auth fails
                     |
                  Shard A
```

The application may authenticate to `mongos` fine, yet the router cannot authenticate internally to the shard, causing queries to fail.

Similarly, routers will fail to authenticate to the CSRS if configured incompatibly.

---

## 8. X.509 Member Authentication: Identity via Certificates

In X.509 mode, MongoDB processes use **TLS certificates** to prove internal identity. A member connection goes through key checks:

1. Network connection to the right endpoint.
2. Successful TLS handshake.
3. Certificate chain verification against a trusted CA.
4. Verification that the certificate is neither expired nor revoked.
5. Hostname/SAN and certificate usage validation.
6. Verification of valid **membership identity** (DN attributes or configured alternative).
7. Admission to internal cluster operations.

**Having TLS does not mean X.509 membership auth is active.** A deployment can encrypt traffic with TLS while still using a keyfile for membership credentials. Only when `clusterAuthMode: x509` (or an appropriate transitional mode) is set do certificates serve as the primary membership mechanism.

### 8.1. CA: Source of Trust

Member certificates in a replica set or sharded cluster must be issued according to MongoDB's CA requirements. Use an internal/enterprise CA or trusted issuer with clear lifecycle and rotation management.

Never self-sign unrelated certificates on each node and expect all nodes to trust one another without managing CA/trust chains. Never distribute the **CA private key** to database servers; distribute only the **public CA certificate chain** needed for verification.

### 8.2. Subject Distinguished Name

Example certificate subjects:

```text
CN=mongo1.example.net, OU=MongoDBMembers, O=ExampleOrg, DC=example, DC=net
CN=mongo2.example.net, OU=MongoDBMembers, O=ExampleOrg, DC=example, DC=net
CN=mongo3.example.net, OU=MongoDBMembers, O=ExampleOrg, DC=example, DC=net
```

- `CN` identifies each individual server and can differ.
- `OU`, `O`, and `DC` are the default membership attributes MongoDB matches.
- Members of the same cluster must share matching membership values **exactly per MongoDB rules**.
- If a certificate has multiple `OU` entries, the full multi-valued list must match per validation rules.

Validation is not merely “same CA means same cluster.” A user certificate signed by the same CA that lacks matching membership attributes **is not treated as a cluster member**.

### 8.3. Subject Alternative Name (SAN)

`mongo1.example.net`'s certificate must include at least one SAN matching the hostname peers connect to:

```text
DNS:mongo1.example.net
```

If peers connect to `mongo1.example.net` while the certificate only lists `DNS:other.example.net`, TLS hostname validation will fail.

MongoDB falls back to Common Name when SAN is absent under some conditions, but **CN-only hostname verification is deprecated** and subject to warnings/client restrictions. Production must issue proper SANs.

### 8.4. EKU and KU

X.509 defines extensions specifying allowed key usage:

| Certificate | Extended Key Usage (if extension present) | Meaning |
| --- | --- | --- |
| `net.tls.certificateKeyFile` | `serverAuth` | Server presents certificate to clients/peers |
| `net.tls.clusterFile` | `clientAuth` | Member uses certificate for internal client authentication |
| Shared `certificateKeyFile` only, no `clusterFile` | Needs both `serverAuth` **and** `clientAuth` if EKU present | Single certificate serving both roles |

When the KU extension is present, MongoDB documentation specifies corresponding requirements/recommendations; for example:

```ini
# Server certificate:
keyUsage = digitalSignature, keyEncipherment, keyAgreement
extendedKeyUsage = serverAuth

# Cluster/member certificate:
keyUsage = digitalSignature
extendedKeyUsage = clientAuth
```

Do not assume `serverAuth` alone suffices for member X.509 if that file is also used for outbound internal client connections. Verify EKU/KU, TLS paths, and your MongoDB version.

### 8.5. `clusterFile` and `certificateKeyFile`

- `net.tls.certificateKeyFile`: PEM holding the server certificate/private key for TLS server connections and some internal connections.
- `net.tls.clusterFile`: dedicated member certificate/private key PEM for membership authentication.
- `net.tls.CAFile`: CA chain used to verify peers.

If `clusterFile` is omitted, MongoDB can use `certificateKeyFile` as the membership certificate; that certificate must include **both `serverAuth` and `clientAuth`** when EKU is present.

Splitting the two files separates server and member certificate lifecycles, at the cost of managing more secret files.

---

## 9. Replica Set Example with X.509 and requireTLS

Example on `mongo1.example.net`:

```yaml
storage:
  dbPath: /var/lib/mongodb

net:
  port: 27017
  bindIp: localhost,mongo1.example.net
  tls:
    mode: requireTLS
    certificateKeyFile: /etc/mongodb/tls/mongo1-server.pem
    clusterFile: /etc/mongodb/tls/mongo1-member.pem
    CAFile: /etc/mongodb/tls/ca.pem

replication:
  replSetName: rs0

security:
  clusterAuthMode: x509
  authorization: enabled
```

Other nodes use:

- The same replica set name.
- The same X.509 membership definition/criteria.
- The matching CA/trust chain.
- **Unique certificates/keys** per node with SANs matching each node's hostname.
- Member certificates carrying matching `O`/`OU`/`DC` or configured alternative membership attributes.

This **does not mean** copying an identical private key PEM onto every node. X.509 allows each node to hold its own keypair alongside compatible trust chains and membership attributes.

### 9.1. X.509 Configuration for a Sharded Cluster

On every shard/CSRS `mongod` and every `mongos`, add matching TLS and auth settings:

```yaml
net:
  tls:
    mode: requireTLS
    certificateKeyFile: /etc/mongodb/tls/this-node-server.pem
    clusterFile: /etc/mongodb/tls/this-node-member.pem
    CAFile: /etc/mongodb/tls/ca.pem

security:
  clusterAuthMode: x509
```

Combine this snippet with role-specific `replication`, `sharding`, `storage`, and `net.bindIp` sections. This is **only the shared portion**, not a complete `mongod`/`mongos` config file.

### 9.2. Custom Membership DN Configuration in MongoDB 7.0+

MongoDB provides options to validate member X.509 certificates against non-default attributes. For instance, matching on `O` and `OU`:

```yaml
net:
  tls:
    clusterAuthX509:
      attributes: "O=ExampleOrg, OU=MongoDBMembers"
```

All members must share the **exact same setting and matching values**. Never apply it to one node expecting the cluster to stay compatible without a coordinated plan.

You can also use the membership extension OID:

```text
1.3.6.1.4.1.34601.2.1.2
```

with `net.tls.clusterAuthX509.extensionValue` in supported versions when matching by extension rather than DN attributes. The certificate extension must use the **exact ASN.1 UTF8String** and matching value. These options are never a reason to skip hostname or CA verification.

### 9.3. Risk of Confusing Client Certificates with Member Certificates

Only member certificates may carry membership-specific attribute/extension values. Client certificates for `$external` authentication must have distinct identities.

**Never set `enforceUserClusterSeparation=false` as an “X.509 fix.”** Per MongoDB documentation, this enables client/membership identity confusion and is incompatible with relevant X.509 cluster auth modes. It is a critical security guard, not an optional production toggle.

---

## 10. `security.clusterAuthMode`: Four Modes to Remember

MongoDB supports:

| Mode | Node **Sends** When Authenticating | Node **Accepts** from Peers | Purpose |
| --- | --- | --- | --- |
| `keyFile` | Keyfile credential | **Keyfile only** | Cluster using shared secret |
| `sendKeyFile` | Keyfile credential | **Keyfile or X.509** | Migration prep phase |
| `sendX509` | Member X.509 certificate | **Keyfile or X.509** | Transition phase |
| `x509` | Member X.509 certificate | **X.509 only** | Recommended target state |

`sendKeyFile` and `sendX509` are not optimal long-term security states. They are **transitional modes** for rolling members gradually.

### 10.1. Why Not Switch Every Node Straight to x509?

Suppose:

```text
Node A: x509 -> accepts certificates only
Node B: keyFile -> sends/accepts keyfile only
```

Those two nodes have **no common mechanism** to authenticate each other. Switching nodes sequentially without intermediate steps can break replication, quorum, or routing.

Therefore migrations move all nodes to a state that **accepts both**, then switches what is sent, and finally restricts acceptance to X.509 only.

### 10.2. Do Not Confuse `clusterAuthMode` with `tls.mode`

- `security.clusterAuthMode` selects the **membership credential**.
- `net.tls.mode` selects **TLS usage** on connections, e.g., `requireTLS`.
- `sendX509` does not guarantee all client connections require TLS unless `tls.mode` and migration are configured properly.

Production targets typically combine `clusterAuthMode: x509` with `net.tls.mode: requireTLS`.

---

## 11. Rolling Migration from Keyfile to X.509

**This is a conceptual guide and illustrative config for learning.** Never execute directly on a production cluster without reading the exact version tutorial and having backups, admin access, a runbook, a maintenance window, and election/quorum monitoring.

Assume the cluster already runs keyfile auth with **TLS enabled**.

### Phase 1: Provision Certificates and Allow Both Mechanisms

On **every** `mongod`/`mongos`:

1. Issue member certificates/keys from a trusted CA.
2. Verify SANs, `O`/`OU`/`DC` or membership extensions, EKUs, and validity.
3. Add `net.tls.clusterFile` and CA/trust settings.
4. Set `security.clusterAuthMode: sendKeyFile`.
5. Retain the existing `security.keyFile`.
6. Rolling-restart each process per topology to preserve availability.

Example:

```yaml
net:
  tls:
    mode: requireTLS
    certificateKeyFile: /etc/mongodb/tls/node-server.pem
    clusterFile: /etc/mongodb/tls/node-member.pem
    CAFile: /etc/mongodb/tls/ca.pem

security:
  clusterAuthMode: sendKeyFile
  keyFile: /etc/mongodb/cluster.key
```

In this state, nodes **still send the keyfile** while **accepting either keyfile or X.509**. Achieve this across the **entire cluster** before advancing.

### Phase 2: Switch What Each Node Sends to X.509

Per supported version tutorials, from an appropriately privileged `mongosh` session **connected to each node**:

```javascript
db.adminCommand({
  setParameter: 1,
  clusterAuthMode: "sendX509"
});
```

In `sendX509` mode, members **send X.509** while **still accepting both mechanisms**, avoiding cutting off peers still mid-transition.

Advance only once every node has certificates, CA trust, and `sendKeyFile` ready; never test this on an isolated node while peers are unready.

### Phase 3: Accept X.509 Only

Once every member runs `sendX509`, switch to:

```javascript
db.adminCommand({
  setParameter: 1,
  clusterAuthMode: "x509"
});
```

Members now send and accept only X.509.

### Phase 4: Persist Configuration

Because runtime `setParameter` does not survive restarts, update config files:

```yaml
security:
  clusterAuthMode: x509
```

Keep TLS, CA, and member cert settings. Retire the old keyfile per plan once cluster stability is confirmed. Verify with a canary restart that it does not revert to the old mode.

### 11.1. Cluster Without Existing TLS

Moving from non-TLS keyfile to X.509 also requires transitioning **TLS transport mode** per MongoDB's supported procedure. Tutorials use `allowTLS`/`preferTLS`/`requireTLS` phases so connections are not severed prematurely.

Never simply add `clusterAuthMode: x509` to a non-TLS cluster and expect it to work. Plan certificate provisioning and the rolling sequence separately.

### 11.2. Do Not Confuse Member X.509 Migration with Client Migration

Migrating **member authentication** from keyfile to X.509 **does not force** SCRAM application users to migrate to client X.509. Both auth channels are independent.

---

## 12. Enabling Keyfile Authentication on an Unauthenticated Running Cluster

This differs from keyfile → X.509 migration. An existing cluster may be running with no `authorization` and no membership auth.

### 12.1. Planned-Downtime Approach

MongoDB tutorials describe stopping members in sequence and restarting them with `security.keyFile`, then creating an admin user via the localhost exception where conditions permit.

Risks:

- Planned downtime occurs.
- Legacy apps without user credentials will be rejected.
- Loss of majority if restarts are sequenced poorly.
- Failure to create the initial admin can lock operators out.

### 12.2. Zero-Downtime Transition Approach

MongoDB also provides a tutorial using `security.transitionToAuth: true` for a transitional window:

```yaml
security:
  keyFile: /etc/mongodb/cluster.key
  transitionToAuth: true

replication:
  replSetName: rs0
```

**Critically important:** While `transitionToAuth` is enabled, the server can **accept unauthenticated connections** and therefore does not yet enforce the target security posture. This is a **temporary** migration phase, never a permanent production setting.

A proper roadmap requires:

1. Preparing the keyfile and user accounts.
2. Distributing configs and secrets completely.
3. Rolling-restarting members into the transition state per the guide.
4. Migrating all applications onto proper credentials.
5. Rolling-restarting to remove `transitionToAuth`.
6. Verifying unauthenticated clients are rejected.
7. Confirming cluster health and no unprotected endpoints remain.

Never abort or leave the transition phase open indefinitely. Sharded deployments impose additional sequencing rules across CSRS, shards, and routers.

---

## 13. Safe Key Rotation Without Breaking Quorum

A keyfile is a **shared secret**, so rotate it periodically or upon suspected exposure.

MongoDB supports YAML keyfiles containing **multiple keys**, provided nodes share at least one key. Rotate using an **old + new overlap** strategy.

### 13.1. Initial State

```text
Node A: [OLD]
Node B: [OLD]
Node C: [OLD]
```

All nodes authenticate using `OLD`.

### 13.2. Phase 1 — Add NEW While Keeping OLD

On each node, one by one, update the keyfile to:

```yaml
- "<OLD_RANDOM_KEY>"
- "<NEW_RANDOM_KEY>"
```

After a **rolling restart** following official procedure:

```text
Node A: [OLD, NEW]
Node B: [OLD, NEW]
Node C: [OLD, NEW]
```

Even while some nodes have not restarted yet, `OLD` remains common to all.

### 13.3. Phase 2 — Keep NEW Only

Once every node runs `[OLD, NEW]`, update each node to:

```yaml
- "<NEW_RANDOM_KEY>"
```

Perform another rolling restart:

```text
Node A: [NEW]
Node B: [NEW]
Node C: [NEW]
```

Nodes still share `NEW`. At completion, **OLD is revoked** across the entire deployment.

### 13.4. Verification Points

- Two communicating members must never lack a **shared key**.
- Restart one member at a time to preserve voting majority.
- For the primary, follow the **step-down before restart** procedure.
- Check replication lag, elections, `rs.status()`, and logs.
- Sharded clusters must cover CSRS, every shard replica set, and `mongos`.
- Never rotate only three data nodes while routers or config servers still hold the old key.
- New keys must be genuine random secrets, never copied from examples.
- Audit and execute revocation of the old secret.

**Note:** Keyfile rotation here **does not apply** directly to local key management for encrypted storage engines. Storage encryption keyfiles have separate constraints and rotation documentation.

---

## 14. X.509 Certificates: Issuance, Rotation, and Revocation

Unlike a shared keyfile, each node can hold its own certificate and private key. That improves identity granularity and revocation, while requiring PKI and certificate lifecycle management.

### 14.1. Certificate Issuance Checklist

1. Generate a node keypair per PKI policy.
2. Issue the certificate from a trusted CA.
3. Ensure SAN matches the exact DNS hostname peers connect to.
4. Ensure `O`/`OU`/`DC` (or alternative membership attributes) match across the cluster.
5. Match EKU (`serverAuth`/`clientAuth`) to file usage.
6. Ensure valid KU and certificate chain.
7. Protect the private key; never emit it into logs.
8. Set validity periods and a renewal plan.
9. Ensure all members trust the issuing CA.
10. Test in staging and canary before wide rollout.

### 14.2. Inspecting Certificates with OpenSSL

Example checking **only public certificate metadata**:

```bash
openssl x509 \
  -in /etc/mongodb/tls/mongo1-member.pem \
  -noout -subject -issuer -dates

openssl x509 \
  -in /etc/mongodb/tls/mongo1-member.pem \
  -noout -text
```

Look for:

```text
Subject
Issuer
Not Before / Not After
X509v3 Subject Alternative Name
X509v3 Key Usage
X509v3 Extended Key Usage
```

**Never** print private keys via `openssl pkey -text` into logs or tickets. Because PEM files can contain private keys, restrict access to the file itself.

### 14.3. Rotation May Require CA Overlap

When changing CAs, nodes during a rolling update may need to trust both old and new chains per a **supported CA rotation procedure**. Pushing a new-CA certificate to one node while peers do not yet trust the new CA causes TLS handshake failures.

Check:

- Can every pair of nodes authenticate during the mixed window?
- Has the updated CA bundle rolled out to every host?
- Did SANs or hostnames change?
- Do separate certificates have the right EKUs?
- Is there time to roll back to the still-valid old certificate?
- Are automated renewal and pre-expiry alerts active?

Do not change CAs, hostnames, and cluster auth mode in a single rollout without compelling reason and a clear plan—failures become hard to isolate.

### 14.4. Certificate Expiry and Availability

When a certificate expires, members fail authentication, breaking replication and routing. If all nodes received certificates expiring on the same day, simultaneous cluster failure can occur.

Per MongoDB documentation, the server logs a warning when an X.509 certificate approaches expiration within roughly **30 days** under applicable conditions. Still implement dedicated monitoring with longer lead thresholds per policy rather than relying solely on startup logs.

---

## 15. TLS Is Not an “Ignore Verification Errors” Option

These settings are **never production fixes**:

```yaml
net:
  tls:
    allowInvalidCertificates: true
    allowInvalidHostnames: true
```

These flags weaken TLS verification; in many cases invalid certificates might pass a handshake yet **still fail X.509 member authentication**.

**Common reasons admins are tempted to enable them:**

- CN/SAN does not match hostname.
- CA has not been distributed.
- Certificate expired.
- `clusterFile`/`certificateKeyFile` points to the wrong file.
- Certificate lacks required `clientAuth`/`serverAuth`.
- Host clock skew makes validity appear invalid.
- `O`/`OU`/`DC` differs across nodes.
- Inconsistent TLS mode during rollout.

The right fix is **fixing the certificate, trust chain, and rollout plan**, not bypassing verification.

Moreover, a valid TLS server certificate without valid membership identity still cannot admit a node under X.509 authentication.

---

## 16. Diagnostic Workflow When Members Cannot Connect

### 16.1. Separate Four Failure Layers

```text
Step A: DNS + TCP connectivity
         |
         v
Step B: TLS handshake + CA + SAN + EKU
         |
         v
Step C: MongoDB membership authentication
         |
         v
Step D: Replication / routing / election
```

**Never** start by changing `clusterAuthMode` if DNS fails to resolve or firewalls block the port.

### 16.2. Useful Tools and Checks

**Name/address:**

```bash
# Run from an authorized host in the lab environment.
getent hosts mongo2.example.net

# Test TCP reachability (does not prove auth succeeds).
nc -vz mongo2.example.net 27017
```

**TLS certificate:**

```bash
# Use only on environments and paths you own.
openssl s_client \
  -connect mongo2.example.net:27017 \
  -servername mongo2.example.net \
  -CAfile /etc/mongodb/tls/ca.pem
```

TCP/TLS success **does not** mean MongoDB accepted the member. Inspect server logs and replica set status.

**MongoDB (requires appropriate privileges):**

```javascript
// Member status, heartbeat errors, elections.
rs.status();

// Node role and primary details.
db.hello();

// For a sharded cluster, connected to mongos:
sh.status();
```

In self-managed environments, inspect active startup config using authorized admin commands; never print passwords, keys, or private keys to stdout.

### 16.3. Reading Logs by Root Cause

Common error categories:

- **Permission denied** reading keyfile.
- **Authentication failed** between peers.
- **No common auth mechanism** or `clusterAuthMode` mismatch.
- **SSL/TLS handshake failed**, certificate verify failed.
- **Hostname mismatch**.
- **Certificate expired/not yet valid**.
- **Member certificate subject/attributes mismatch**.
- **No primary**, unreachable members, heartbeat failures.
- **Unable to reach config servers** or router unable to reach shards.

Exact log strings vary across MongoDB versions, so never match solely on one string. Gather timestamps, hostnames, server versions, and recent changes.

---

## 17. Common Troubleshooting Table

| Symptom | Possible Cause | Investigation / Resolution |
| --- | --- | --- |
| `mongod` fails startup after enabling keyfile | Missing path, wrong owner/permissions, bad key format | Check file permissions, service identity, parser, and logs |
| Node starts but cannot join replica set | No shared key, mismatched `clusterAuthMode` | Compare policies, membership secrets, and logs |
| Secondary replication stops after rotation | One node has only NEW, peer has only OLD | Restore overlap and follow rolling process |
| Legacy clients fail login after enabling auth | Users not created or credentials unconfigured | Create admin/app users per bootstrap/runbook |
| Client authenticates yet gets `Unauthorized` | Missing RBAC role | Inspect user roles; never grant `root` hastily |
| TLS `certificate verify failed` | Wrong CA, missing chain, expired | Verify CA, chain, and dates |
| TLS hostname mismatch | SAN misses DNS hosts in replica config | Issue certs with matching SANs; align DNS |
| Member X.509 rejected | `O`/`OU`/`DC` or extension mismatch | Inspect member cert DN/extension |
| Member cert has `serverAuth` only | Missing `clientAuth` for internal client role | Reissue cert with appropriate EKUs |
| Failures right after CA swap | Peers do not trust new CA | Follow trust-chain overlap plan |
| `mongos` cannot read config metadata | Router/CSRS auth mismatch or DNS/TLS | Check full topology, not only shards |
| `rs.status()` shows multiple unhealthy members | Network, TLS/auth, or election issue | Collect logs from all members; check majority |
| No primary after restarting multiple nodes | Lost voting majority | Halt rollout; restore quorum safely |
| Node starts but clients only use IPs | DNS/TLS SAN mismatch or address validation | Use matching hostnames and SANs |
| Secrets exposed in Git/CI | Poor secret hygiene | Revoke, rotate, audit, and scrub pipeline |
| X.509 user gets wrong access | Client certificate confused with member certificate | Separate PKI/identities; verify separation |
| TLS succeeds yet auth fails | TLS ≠ MongoDB membership auth | Check `clusterAuthMode` and DN/key |
| Disabling TLS validation as a “quick fix” | Masks CA/SAN bugs and weakens security | Fix certificates; never bypass |
| Keyfile rotated on one shard, router stays old | No common key across whole deployment | Rotate cluster-wide |
| Simultaneous certificate expiration | Unmanaged renewals | Alerting and staged rotation with buffer |

---

## 18. Replica Set Health and Quorum During Auth Maintenance

To preserve write availability, respect replica set **majority**.

With **3 voting members**, majority is:

\[
\left\lfloor \frac{3}{2} \right\rfloor + 1 = 2
\]

If you restart **two voting members simultaneously**, the remaining member lacks a majority to maintain or elect a primary, causing loss of write availability.

### 18.1. Controlled Rolling Restart

Standard procedure:

1. Confirm the replica set is healthy with low replication lag.
2. Restart **one secondary**.
3. Wait until it returns healthy/`SECONDARY` and replication catches up.
4. Repeat for the other secondary as needed.
5. **Step down the primary** cleanly and wait for a new primary election.
6. Restart the former primary.
7. Verify `rs.status()`, write paths, and app error rates.

Never restart all nodes simultaneously just because keyfile rotation updated files. In a sharded cluster, each shard replica set **and the CSRS** has its own quorum, and `mongos` routers need redundancy for client ingress.

### 18.2. Auth Failures Impact Availability

When members cannot authenticate each other, heartbeats and replication connections fail, indirectly causing elections and application writes to fail.

Proper diagnosis: **loss of primary** is only the final symptom—distinguish network, DNS, TLS handshake, and membership authentication failures.

---

## 19. Designing a Production Security Policy

### 19.1. Environment Separation

- Keep secrets/certificates separate across production, staging, and development.
- Never share one membership key across unrelated clusters.
- Scope member certificates strictly to each deployment.
- Maintain key/certificate revocation plans for compromised hosts or accounts.

### 19.2. Secrets Management

- Protect keyfiles and private keys with strict OS ACLs.
- Grant read access only to authorized MongoDB/automation processes.
- Never log, echo, or commit credentials.
- Rotate secrets per policy and after incidents.
- Restrict CI/CD secret access to least privilege.
- Audit who distributed, modified, or read secrets.

### 19.3. Network Protection

- Open only required ports between members, routers, config servers, and authorized clients.
- Use private networks, security groups, and firewalls.
- Restrict listening interfaces via `net.bindIp`.
- Enforce TLS; never expose MongoDB directly to the Internet.
- Manage DNS hostnames and cert SANs alongside topology.

### 19.4. RBAC

- Provision application accounts with roles scoped to **required databases and operations**.
- Separate security admin, cluster admin, and backup/monitoring identities.
- Never assign `root` or `userAdminAnyDatabase` to applications.
- Use password prompts or secret managers instead of hardcoding.

### 19.5. Certificate Policy

- Unified CA/trust policy for members meeting MongoDB rules.
- Accurate SANs.
- Consistent DN/membership extensions kept distinct from client certificates.
- Proper EKU/KU values.
- Automated renewal and pre-expiration alerts.
- Managed CA rotation.
- Staging tests before production.

### 19.6. Auditing and Recovery

- Log changes to `security.keyFile`, `clusterAuthMode`, and TLS settings.
- Monitor authentication failures and replica set membership changes.
- Back up configs, CA public chains, and secret retrieval procedures.
- Never store unencrypted plaintext secrets inside shared backups.
- Maintain runbooks for lost members or lost primary due to auth mismatch.
- Practice recovery drills so teams do not “fix” issues by disabling authorization.

---

## 20. Scenario 1: One Node Has a Different Keyfile and Is Rejected

Assumed state:

```text
R1: keyfile = K1
R2: keyfile = K1
R3: keyfile = K2
```

R3 starts `mongod`, yet membership auth with R1/R2 fails. The problem is **not necessarily** replica set config or port 27017.

Safe resolution steps:

1. Verify DNS/TCP reachability to R3.
2. Inspect authentication logs on R3 and peers.
3. Check whether R3 received the right secret version (without printing the key).
4. If mid-rotation, check whether each node has the overlap key.
5. Fix the keyfile via the secret manager with proper file permissions.
6. Restart R3 per runbook.
7. Wait for R3 to return healthy and catch up on replication.

Never fix this by setting `authorization: disabled` or altering replica set config to admit an unauthenticated node.

---

## 21. Scenario 2: X.509 CA Matches, but O/OU Differs

Assumed state:

```text
mongo1:
  CN=mongo1.example.net
  O=ExampleOrg
  OU=MongoDBMembers

mongo2:
  CN=mongo2.example.net
  O=ExampleOrg
  OU=ApplicationClients
```

Both certificates may come from the **same CA**, have valid SANs, and pass the TLS handshake. Yet MongoDB membership auth can reject `mongo2` because `OU` mismatches.

Fix: reissue the certificate or align membership configuration per official policy, keeping `O`/`OU`/`DC` or alternative attributes consistent. Never disable `enforceUserClusterSeparation` or enable `allowInvalidCertificates`.

**Takeaway:** CA trust and membership identity are **two separate checks**.

---

## 22. Scenario 3: Only One Router Holds the Old Keyfile

Suppose a sharded cluster just rotated keys:

```text
CSRS:     NEW
Shard A:  NEW
Shard B:  NEW
mongos 1: NEW
mongos 2: OLD
```

`mongos 2` fails connecting to members accepting only `NEW`. Clients load-balanced to `mongos 1` still succeed, causing **intermittent** errors.

Investigation:

- Correlate client errors per router instance.
- Verify secret versions across every `mongos`.
- Coordinate cluster-wide rotation using old+new overlap.
- Never treat success on a single router as proof the whole cluster finished rotating.

---

## 23. Scenario 4: Switching Keyfile to X.509 Loses the Primary

An admin switches R1 straight to `x509` while R2/R3 remain on `keyFile`. R1 and its peers no longer share an accepted/sent mechanism, causing auth failures and unstable elections/replication.

Prevention: step through modes sequentially:

```text
keyFile
   |
sendKeyFile  (sends keyfile, accepts both)
   |
sendX509     (sends certificate, accepts both)
   |
x509         (sends/accepts certificates)
```

Ensure TLS/CA/certs are ready first, transition node by node per your version guide, preserve majority, and monitor recovery. Never change the whole cluster in one unplanned shot.

---

## 24. Verification Commands and Operations

These are **diagnostic tools**, not automated production repair scripts.

### 24.1. Inspect Replica Set Status

As a user with monitor privileges:

```javascript
const s = rs.status();

printjson({
  set: s.set,
  myState: s.myState,
  members: s.members.map(m => ({
    name: m.name,
    stateStr: m.stateStr,
    health: m.health
  }))
});
```

If a member is down, inspect **logs and networking** to pinpoint the failure. `rs.status()` does not prove whether internal auth uses keyfile or X.509; it reports replication and heartbeat health.

### 24.2. Inspect Router/Sharded Topology

From `mongos` with appropriate privileges:

```javascript
sh.status();
```

On auth mismatches, parts of the output or queries can fail; distinguish membership, TLS, DNS, and config metadata failures.

### 24.3. Inspect Certificates Without Exposing Private Keys

```bash
openssl x509 -in node-member.pem -noout \
  -subject -issuer -dates
```

Inspect SANs and EKUs with:

```bash
openssl x509 -in node-member.pem -noout -text
```

Remember the input PEM may contain a private key—**access it only from authorized machines/roles**, and never upload PEM files to untrusted online certificate checkers.

### 24.4. Check Keyfile Permissions (Linux)

```bash
# Read metadata on lab; does not print the secret.
ls -l /etc/mongodb/cluster.key
stat /etc/mongodb/cluster.key
```

Permissions `-rw-r--r--` allow group/world read access: **unsafe**. Permissions `-r--------` owned by the wrong user prevent MongoDB from reading it. Fix owner/permissions per policy rather than widening permissions.

### 24.5. Never Test “Can I Still Read Without a Password?” in Production

When testing authentication, use staging or dedicated test accounts and non-destructive reads. Verify that unauthenticated connections **cannot read/modify protected resources**—never spin up a rogue node in production to test.

---

## 25. Decision Guide: Keyfile or X.509?

| Criterion | Keyfile | X.509 Member Auth |
| --- | --- | --- |
| Identity | Deployment-wide shared secret | Certificate/keypair and membership attributes |
| Setup | Simpler | Requires CA/PKI and TLS/cert config |
| TLS policy | Must configure separately | X.509 requires TLS |
| Credential granularity | Usually one shared key/set | Unique certificate per node |
| Rotation | Multi-key YAML + rolling restart | Renew/reissue certs/CA trust + rollout |
| On exposure | Can affect all members sharing the key | Per-node cert/key helps contain impact |
| Operational cost | Managing shared secret and file permissions | PKI, SAN, DN/EKU, expiry, and CA rotation |
| MongoDB recommendation | Minimal baseline, suited for lab/dev | Recommended for production |

**Never** conclude X.509 “cannot be spoofed.” If a private key or CA is compromised, the risk remains severe. PKI's value depends on proper issuance, private key protection, validity periods, rotation, and monitoring.

### 25.1. Managed Environments

Atlas and other managed MongoDB platforms handle membership security internally. Never try applying self-managed `mongod --keyFile` commands to a cluster whose processes you do not directly manage.

In operational documentation, clearly distinguish:

- **Self-managed MongoDB**: operations team manages config files, secrets, and certs.
- **Managed deployment**: uses provider UI/API and documented platform controls.
- **Containers/Kubernetes**: secret mounts, operator reconciliation, service DNS, and rolling update policies; manual edits may be overwritten by controllers.

---

## 26. Quick Parameter Reference Table

| Parameter | Role | When Used |
| --- | --- | --- |
| `security.keyFile` | Shared secret file path | Keyfile membership auth |
| `--keyFile` | CLI equivalent of keyfile config | Controlled labs/automation |
| `security.authorization` | Client RBAC | Enforces access control |
| `security.clusterAuthMode` | Internal auth mode | `keyFile`, `sendKeyFile`, `sendX509`, `x509` |
| `security.transitionToAuth` | Temporarily allows auth/unauth connections | Migration only per tutorial |
| `net.tls.mode` | TLS transport mode | Typically `requireTLS` for production targets |
| `net.tls.certificateKeyFile` | Server certificate/key | TLS server identity; can serve membership if suitable |
| `net.tls.clusterFile` | Member certificate/key | Internal X.509 identity |
| `net.tls.CAFile` | CA trust bundle | Certificate verification |
| `net.tls.clusterAuthX509.attributes` | Match X.509 DN per config | Option in MongoDB 7.0+ |
| `net.tls.clusterAuthX509.extensionValue` | Match certificate extension | Option in MongoDB 7.0+ |
| `replication.replSetName` | Replica set name | All data members of the set |
| `sharding.clusterRole` | `configsvr` or `shardsvr` | Config servers and shard members |
| `sharding.configDB` | CSRS endpoint list for `mongos` | Router |
| `net.bindIp` | Bound interfaces | Reduces network exposure |
| `net.port` | MongoDB process port | Inter-member/client connections |

Crucially, **multiple parameters work together**. Setting `clusterAuthMode: x509` without valid certificates/trust fails, and `security.keyFile` does not automatically enable `requireTLS`.

---

## 27. Security Implementation and Change Checklist

### Before Deployment

- [ ] Identify all `mongod` and `mongos` processes, including CSRS, arbiters, and standby routers.
- [ ] Maintain an accurate topology diagram, DNS names, and ports.
- [ ] Choose keyfile or X.509 per requirements and server version.
- [ ] Generate and distribute secrets/certificates over secure channels.
- [ ] Verify SAN/CA/EKU/DN membership requirements.
- [ ] Prepare users/RBAC and bootstrap plans without locking out admins.
- [ ] Configure TLS, network policies, and firewalls.
- [ ] Ensure backups, recovery secret access, and an approved runbook.
- [ ] Test in staging matching topology and version.
- [ ] Schedule a maintenance window and incident communication plan.
- [ ] Set up monitoring for quorum, replication lag, app errors, and TLS expiry.

### During Rollout

- [ ] Update members one by one following the tutorial's exact sequence.
- [ ] Never restart multiple voting members simultaneously.
- [ ] Wait for each member to return healthy before proceeding.
- [ ] Monitor authentication failures and network/TLS errors.
- [ ] If using a transitional mode, enforce a firm completion deadline.
- [ ] Ensure key overlap or dual acceptance during transition.
- [ ] Verify all routers, CSRS, and shards stay compatible.
- [ ] Never disable certificate validation as a quick fix.

### After Rollout

- [ ] `rs.status()` is healthy for every replica set.
- [ ] `mongos` routes queries properly per tenant/roles.
- [ ] No node remains in an unintended transitional mode.
- [ ] Verify unauthorized users are properly denied.
- [ ] Test application credentials and rotation.
- [ ] Audit key/certificate versions and dates.
- [ ] Update runbooks, monitoring, and secret inventories.
- [ ] Schedule the next key/certificate rotation.

---

## 28. Hands-On Exercises

### Exercise 1 — Two Authentication Channels

An app logs into `mongos` as a SCRAM user. `mongos` connects to shards using X.509. Is there any conflict? Which mechanism governs the user's query permissions?

**Answer:** No conflict. Client auth and member auth are independent channels; RBAC governs user permissions.

### Exercise 2 — Keyfile and TLS

A replica set sets `security.keyFile` without enabling TLS. Is replication traffic on the network encrypted?

**Answer:** No; a keyfile only authenticates members. TLS is required for transport encryption.

### Exercise 3 — Shared Secrets

Three nodes hold:

```text
A: [K1]
B: [K1, K2]
C: [K2]
```

Which keys does each pair share? Why should you not leave this uneven state during an ongoing rotation?

**Hint:** A/B share K1, B/C share K2, and A/C share no key. Maintain deployment-wide overlap during rolling steps to avoid severed links.

### Exercise 4 — Linux File Permissions

A keyfile has permissions `0644` and `mongod` runs as `mongodb`. What is wrong, and what permissions are safer?

**Answer:** Group/world can read the secret; set proper ownership and `0400`.

### Exercise 5 — Initializing a Replica Set

Write `mongod` configs for three nodes with `replSetName: rs0`, keyfile, `net.bindIp`, and TLS. Which fields match across nodes, and which are host-specific?

### Exercise 6 — Client Without User

After enabling `security.keyFile`, an app still connects using a credential-free URI. What happens? What role does the localhost exception play in bootstrapping?

**Answer:** Authorization is enabled; the app needs a username/password or supported client auth. The localhost exception only serves restricted bootstrapping when no users exist yet.

### Exercise 7 — Sharded Cluster

A cluster has two shard replica sets, one CSRS, and two routers. Which components must share compatible membership auth/keyfiles?

**Answer:** All `mongod` and `mongos` processes, not only shard primaries.

### Exercise 8 — `mongos` Configuration

Why does `mongos` need `sharding.configDB` and `security.keyFile` in a keyfile cluster? Does it need `replication.replSetName` like a shard node?

**Answer:** The router must connect internally to CSRS/cluster members; it is not a data-bearing replica set member.

### Exercise 9 — X.509 Attributes

Certificates:

```text
A: O=Company, OU=MongoDBMembers, CN=mongo1.example.net
B: O=Company, OU=MongoDBMembers, CN=mongo2.example.net
C: O=Company, OU=Developers,    CN=mongo3.example.net
```

If membership policy matches `O` and `OU`, will node C be accepted?

**Answer:** No, `OU` differs.

### Exercise 10 — SAN

Peers connect to `mongo1.example.net`, yet the certificate only has `DNS:mongo1.internal.local`. What fails, and how should it be fixed?

**Answer:** Hostname validation fails; issue a cert with a SAN matching the connection name or update naming configuration per procedure. Never enable `allowInvalidHostnames`.

### Exercise 11 — EKU

A member uses `net.tls.clusterFile`, yet its cert only has `serverAuth`. What can fail?

**Answer:** `clusterFile` requires `clientAuth` when EKU is present. Reissue the cert with the proper purpose.

### Exercise 12 — Single Certificate for Two Roles

If `clusterFile` is omitted and `certificateKeyFile` serves both TLS server and membership roles, what EKU is needed?

**Answer:** If EKU is present, both `serverAuth` and `clientAuth` are needed.

### Exercise 13 — Mode Matrix

Fill in what `keyFile`, `sendKeyFile`, `sendX509`, and `x509` send and accept.

**Answer:** See the table in Section 10; the two `send*` modes send one type while accepting both.

### Exercise 14 — Keyfile → X.509 Migration

Why not switch each member straight from `keyFile` to `x509`? Outline the rolling migration sequence.

**Answer:** Peers could lose a common auth mechanism. Use `sendKeyFile` → `sendX509` → `x509` once TLS/certs are ready.

### Exercise 15 — Transitioning an Unauthenticated Cluster

What does `transitionToAuth` do, and why must it be removed after migration?

**Answer:** It temporarily allows both authenticated and unauthenticated connections for migration; leaving it enabled leaves access control open.

### Exercise 16 — Key Rotation

Outline the steps `OLD` → `[OLD,NEW]` → `NEW`, including restarts. Why must at least one key remain shared?

### Exercise 17 — Majority

A three-voting-member replica set restarts two nodes at the same time. What happens to write availability?

**Answer:** Only one vote remains, which is insufficient for a majority to hold a primary; write availability can be lost.

### Exercise 18 — Certificate Expiry

Three nodes received certificates expiring on the same day. Propose an alerting and renewal plan to prevent simultaneous outages.

### Exercise 19 — CA vs. Membership

A client certificate is signed by the trusted CA yet carries `OU=ApplicationClients`, not `MongoDBMembers`. Is it accepted as a cluster member simply because the CA matches?

**Answer:** No; it must satisfy membership identity checks.

### Exercise 20 — TLS Handshake Succeeds, Replication Fails

TCP connects and `openssl s_client` verifies the CA cleanly, yet `rs.status()` still reports unreachable/auth failure. List three next checks.

**Hint:** `clusterAuthMode`, keyfile overlap or member DN/extension, certificate EKU, MongoDB logs, and `replSetName`.

### Exercise 21 — Sharded Router Skew

Two routers: only `router1` works after rotating to `NEW`, while `router2` still holds `OLD`. Why does the app see random per-request failures?

**Answer:** The load balancer sends some requests to `router2`, which fails authentication against shards/CSRS accepting only `NEW`.

### Exercise 22 — Exposed Secrets

A keyfile was committed to a repo and printed in CI logs. What security actions are needed beyond “delete the commit”?

**Hint:** Revoke/rotate via overlap, audit access, invalidate the old secret, fix the pipeline, and file an incident report.

### Exercise 23 — Production Security Policy

Compare keyfile and X.509 across shared secrets, CA/PKI, granular identity, rotation, TLS, and operational cost. Choose an option for a production environment with existing PKI and explain.

### Exercise 24 — Operations Checklist

Design an internal authentication runbook for a sharded cluster with 2 shards + 3-node CSRS + 2 `mongos`: DNS, TLS, CA, secrets/certs, rolling rotation, health checks, monitoring, and quorum-loss recovery.

---

## 29. Summary

**Member-to-member authentication** ensures only `mongod`/`mongos` processes holding valid membership credentials can participate in critical internal cluster links.

Key principles to remember:

1. **Internal auth differs from client auth/RBAC and TLS.** Design all layers properly.
2. **Keyfiles** use shared secrets/SCRAM; all members need at least one common key, protected by OS file permissions.
3. **X.509** uses certificates/CA/TLS and matching membership attributes; production requires clear PKI and rotation.
4. **SAN and EKU/KU matter**: a trusted CA alone does not guarantee hostname or membership validity.
5. **`security.clusterAuthMode` has four states**; `sendKeyFile`/`sendX509` are transitional migration steps.
6. **Sharded clusters must protect every `mongod` and `mongos`**—not just shard primaries.
7. **`security.keyFile` implies client authorization**, making user bootstrapping and RBAC part of the rollout.
8. **Rotations must preserve overlap and majority**; never restart multiple voting members simultaneously.
9. **Never bypass TLS verification or `enforceUserClusterSeparation`** to work around certificate errors.
10. **Diagnose logs and health by layer**: DNS/TCP → TLS → membership auth → replication/routing.
11. **Never place credentials in repositories or logs**; use secret managers and audits.
12. **Check MongoDB version documentation** before any config change or production migration.

A secure deployment does not merely “turn on auth”—it establishes **secret/certificate lifecycles, safe key rotation, node-failure recovery, and properly scoped client privileges**.

### Official MongoDB Documentation

- [Self-Managed Internal/Membership Authentication](https://www.mongodb.com/docs/manual/core/security-internal-authentication/) — keyfile/X.509, member certificate attributes.
- [Self-Managed X.509 Authentication](https://www.mongodb.com/docs/manual/core/security-x.509/) — CA, SAN, EKU/KU, client vs. member separation.
- [Self-Managed Configuration File Options](https://www.mongodb.com/docs/manual/reference/configuration-options/) — `security.keyFile`, `security.clusterAuthMode`, `net.tls.*`.
- [Deploy Replica Set with Keyfile Access Control](https://www.mongodb.com/docs/manual/tutorial/deploy-replica-set-with-keyfile-access-control/) — replica set bootstrap.
- [Update Replica Set to Keyfile Authentication](https://www.mongodb.com/docs/manual/tutorial/enforce-keyfile-access-control-in-existing-replica-set/) — enabling keyfile on existing deployments.
- [Update Replica Set without Downtime](https://www.mongodb.com/docs/manual/tutorial/enforce-keyfile-access-control-in-existing-replica-set-without-downtime/) — `transitionToAuth` and rolling rollout.
- [Update Sharded Cluster to Keyfile Authentication](https://www.mongodb.com/docs/manual/tutorial/enforce-keyfile-access-control-in-existing-sharded-cluster/) — CSRS, shards, `mongos`.
- [Verify Cluster Membership with X.509](https://www.mongodb.com/docs/manual/tutorial/configure-x509-member-authentication/) — preparing member certificates.
- [Upgrade Keyfile to X.509](https://www.mongodb.com/docs/manual/tutorial/upgrade-keyfile-to-x509/) — `sendKeyFile`, `sendX509`, `x509`.
- [Rotate Keys in Replica Sets](https://www.mongodb.com/docs/manual/tutorial/rotate-key-replica-set/) — multi-key YAML and rolling rotation.
- [Rotate Keys in Sharded Clusters](https://www.mongodb.com/docs/manual/tutorial/rotate-key-sharded-cluster/) — cluster-wide rotation.
- [Configure MongoDB for TLS](https://www.mongodb.com/docs/manual/tutorial/configure-ssl/) — TLS certificates and CAs.
- [Authentication](https://www.mongodb.com/docs/manual/core/authentication/) — user authentication.
- [Role-Based Access Control](https://www.mongodb.com/docs/manual/core/authorization/) — MongoDB authorization.
- [Replica Set Elections](https://www.mongodb.com/docs/manual/core/replica-set-elections/) — quorum/primary availability.
