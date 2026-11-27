# TLS for Application Connections and Internal MongoDB Cluster Communication

An application sends queries, authentication credentials, and user data to MongoDB over the network. In a replica set, members exchange heartbeats, oplog entries, and sync data. In a sharded cluster, `mongos` communicates with shards and config servers. If any part of this path is unprotected, anyone able to observe or intercept the network can read data, spoof endpoints, or tamper with traffic.

**TLS (Transport Layer Security)** protects network connections in transit via encryption, integrity checks, and certificate-based identity verification. In MongoDB, you must distinguish **two scopes**:

1. **Application → MongoDB connections**: drivers, `mongosh`, backend services, and batch jobs connecting to `mongod` or `mongos`.
2. **Internal cluster communication**: replica set members, routers, config servers, and shards talking to one another.

A cluster that enables TLS only for applications while leaving inter-node traffic in plaintext is **not encrypted end-to-end**. Conversely, internal TLS does not protect application connections if clients still use plaintext. Having TLS also does not mean users are **authenticated and authorized** inside MongoDB.

This lesson belongs to the **Security** chapter of the *Database Engine Document MongoDB* module. Examples include `mongod.conf` snippets, `mongosh` commands, Node.js Driver, Java Sync Driver, and rollout diagrams. All hostnames, certificate paths, and identities in examples are **simulated**. Exact options and certificate rotation mechanisms depend on MongoDB server/driver versions, Feature Compatibility Version, OS, and managed service; verify against your target deployment version before production use.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain how TLS protects confidentiality, integrity, and server identity.
2. Distinguish TLS server authentication, mutual TLS (mTLS), SCRAM, `MONGODB-X509`, and internal cluster authentication.
3. Understand Root CA, intermediate CA, certificate chains, trust stores, private keys, SAN, EKU, and validity periods.
4. Read `net.tls.mode`, `certificateKeyFile`, `CAFile`, `clusterFile`, and `clusterCAFile` configurations.
5. Enforce TLS on `mongod`/`mongos` and govern plaintext paths.
6. Describe TLS between replica set members and across sharded cluster components.
7. Distinguish TLS + keyFile authentication from TLS + x.509 cluster authentication.
8. Connect over TLS from `mongosh`, Node.js, and Java without disabling certificate validation.
9. Configure client certificates when using `MONGODB-X509` per policy.
10. Build a node-by-node rollout plan, verify failover, and rotate CAs/leaf certificates.
11. Diagnose errors involving certificate chains, SANs, expired certs, EKUs, TLS versions, clocks, DNS, and key permissions.
12. Monitor TLS handshakes, certificate expiry, and cluster availability.
13. Avoid dangerous choices such as `tlsInsecure` or terminating TLS at a proxy with unencrypted backend hops.

## 2. Threat Model: What Does TLS Protect?

Suppose an API server sends queries to `mongo1.db.internal:27017`. Even inside a private network, traffic traverses network gear, hypervisors, management planes, and gateways. If one component is compromised, plaintext can expose queries, sensitive data, or connection details.

| Property | TLS Contribution | Scenario |
|---|---|---|
| Confidentiality | Encrypts bytes in transit | Eavesdroppers cannot read document contents |
| Integrity | Detects unauthorized modification | Packets cannot be silently altered and accepted as intact |
| Server authentication | Verifies server certificate/hostname | Clients avoid connecting to spoofed endpoints |
| Client authentication (with mTLS) | Server verifies client certificate | Enforces client-side certificate identity policies |

### 2.1. TLS Does Not Replace Other Security Layers

- **MongoDB authorization:** checks users/roles and read/write rights on databases and collections.
- **Application:** authenticates principals, checks tenant/owner access, prevents injection.
- **Encryption at rest:** protects data stored on disk/backups.
- **Field-level encryption:** protects sensitive fields from the client onward when required.
- **Network controls:** firewalls, private subnets, least exposure.
- **Auditing and secret management:** tracks access and protects credentials and private keys.

An encrypted connection to the real server can still run bad queries if the app builds unsafe queries or grants overly broad roles.

### 2.2. Internal Networks Are Not Inherently Safe

A `.internal` hostname or living inside a VPC does not guarantee traffic cannot be observed. TLS is still necessary—especially across availability zones, clusters, datacenters, or multiple infrastructure admin teams.

## 3. Two Connection Paths Diagrams

### 3.1. Replica Set

~~~mermaid
flowchart TD
    App["Application / mongosh"] -->|"TLS"| P["mongod Primary"]
    App -->|"TLS when reading from member"| S1["mongod Secondary A"]
    App -->|"TLS when reading from member"| S2["mongod Secondary B"]
    P <-->|"Internal TLS: replication/heartbeat"| S1
    P <-->|"Internal TLS: replication/heartbeat"| S2
    S1 <-->|"Internal TLS"| S2
~~~

With replica set drivers, applications typically discover member hostnames from cluster configuration. Therefore certificates must match **every hostname the driver actually connects to**, not just the initial seed hostname in the URI.

### 3.2. Sharded Cluster

~~~mermaid
flowchart TD
    Client["Application/driver"] -->|"TLS"| Router["mongos"]
    Router <-->|"Internal TLS"| Config["Config Server Replica Set"]
    Router <-->|"Internal TLS"| ShardA["Shard A Replica Set"]
    Router <-->|"Internal TLS"| ShardB["Shard B Replica Set"]
    ShardA <-->|"Protected admin/metadata connections"| Config
    ShardB <-->|"Protected admin/metadata connections"| Config
~~~

Each shard and config server has its own `mongod` members exchanging replication traffic. Inventory every flow, not just the application-to-router hop.

## 4. TLS Handshake and MongoDB Authentication

~~~mermaid
sequenceDiagram
    participant App as MongoDB Driver
    participant Server as mongod / mongos
    App->>Server: TLS handshake
    Server-->>App: Certificate and chain
    App->>App: Verify CA, SAN, expiry, key usage
    App->>Server: Complete session key agreement
    Note over App,Server: TLS channel established
    App->>Server: MongoDB authentication (e.g., SCRAM)
    Server-->>App: Auth outcome
    App->>Server: ping / find / aggregate
~~~

This diagram illustrates the logical sequence rather than every exact TLS 1.2/1.3 packet. The key point is that **the TLS channel is established before MongoDB protocol commands**.

### 4.1. Verification Checks

The client must verify:

1. The certificate is signed by a trusted CA/issuer chain.
2. The certificate is within its validity period.
3. The DNS name/IP used to connect matches a **Subject Alternative Name**.
4. Key usage and Extended Key Usage (EKU) match the intended role.
5. TLS protocol, cipher suites, and algorithms are permitted.
6. Revocation is handled per the deployment's mechanisms/policies where supported.

If a certificate has a valid signature yet its SAN does not match the hostname, the client must reject it under standard hostname verification.

### 4.2. TLS ≠ Login

After TLS completes, MongoDB may still require **SCRAM username/password** or **MONGODB-X509 certificate-based authentication**. Login mechanisms and roles are a separate layer from transport encryption.

## 5. TLS Server-Auth, mTLS, SCRAM, and X.509

| Scenario | Server Presents Cert | Client Presents Cert | MongoDB Authentication |
|---|---|---|---|
| TLS + SCRAM | Yes | Not necessarily | SCRAM username/password |
| mTLS + SCRAM | Yes | Yes | Can still be SCRAM per policy |
| TLS + `MONGODB-X509` | Yes | Yes | Certificate subject/identity mapped to MongoDB user |
| Internal TLS + keyFile | Has TLS credentials | Per trust/internal TLS config | Shared keyFile secret |
| Internal TLS + cluster x.509 | Yes | Has matching certificate identity | Internal x.509 authentication |

### 5.1. When the Application Uses SCRAM

The application can connect over TLS **without a client certificate** if server policy permits. The client must still verify the server certificate, and the user must still log in with SCRAM.

### 5.2. When the Application Uses mTLS

The server can require/trust a client certificate. However, a client certificate accepted by the TLS layer **does not automatically grant MongoDB roles**. If using `MONGODB-X509`, provision the identity in `$external` and assign appropriate roles.

### 5.3. Internal Auth Differs from App Auth

Replica set and sharded cluster members use dedicated mechanisms to prove valid membership. Never use internal member credentials or certificates as application credentials.

## 6. PKI: CA, Leaf Certificates, Keys, and Trust Stores

A PKI system typically comprises:

- **Root CA:** trust anchor; its private key must be strictly protected.
- **Intermediate CA:** signs server/client certificates on behalf of the root.
- **Leaf server certificate:** certificate of `mongod`/`mongos`.
- **Leaf client certificate:** used when client mTLS/x.509 is required.
- **Private key:** secret matching the leaf certificate; stored only on the owning entity.
- **Trust store / CA bundle:** trusted public CA certificates.

~~~mermaid
flowchart TD
    Root["Root CA"] --> Intermediate["Intermediate CA"]
    Intermediate --> MongoCert["MongoDB server leaf"]
    Intermediate --> AppCert["Application client leaf (if mTLS)"]
    TrustApp["Application trust store"] -->|"Build certificate chain"| MongoCert
    TrustMongo["MongoDB trust CA"] -->|"Verify peer"| AppCert
~~~

### 6.1. Certificate Chain

Peers must be able to build a trust path from the leaf to a trusted CA. A missing intermediate can cause failures even when the Root CA is present in the trust store. Depending on the system, the server must serve both the leaf and intermediate chain appropriately.

### 6.2. Public Certificates Differ from Private Keys

A certificate holds a public key/identity and can be distributed per policy. A private key is a secret: never commit it to Git, bake it into public Docker images, or send it over issue trackers or unencrypted email. Restrict file permissions and use secret managers/secure volumes.

### 6.3. PEM Files and Illustrative Paths

~~~text
/etc/mongodb/tls/mongo1.pem       server certificate + private key
/etc/mongodb/tls/ca-chain.pem     CA/intermediate public certificates
/etc/mongodb/tls/cluster1.pem     separate internal client certificate/key if split
/etc/mongodb/secrets/cluster.key  keyFile secret if using keyFile auth
~~~

`certificateKeyFile` may contain a private key, whereas `CAFile` is trust material. Never swap the two file types.

## 7. SAN, CN, and EKU

### 7.1. SAN

If a replica set advertises:

~~~javascript
rs.conf().members.map(m => m.host)
// [
//   "mongo1.db.internal:27017",
//   "mongo2.db.internal:27017",
//   "mongo3.db.internal:27017"
// ]
~~~

`mongo1`'s certificate needs `DNS:mongo1.db.internal` in its SAN. Ports do not go in DNS SANs. If applications connect by IP, an appropriate IP SAN must exist—or switch to DNS hostnames covered by the certificate.

### 7.2. Do Not Rely on CN-Only Certificates

Modern TLS clients primarily verify hostnames via **SAN** and do not treat CN-only certificates as reliable long-term configurations. Issue leaf certificates with explicit DNS SANs matching canonical endpoint names.

### 7.3. EKU

- `serverAuth` is for certificates acting as a TLS server.
- `clientAuth` is for certificates acting as a TLS client.

A MongoDB member both accepts incoming connections and initiates internal connections. Certificates used for each role must carry matching EKU/key usage. Cluster x.509 also has specific subject and EKU rules; verify the required profile for your version.

### 7.4. Validity Periods and Clocks

`NotBefore` and `NotAfter` govern validity windows. Clock skew or broken NTP can make a valid certificate appear expired or not yet valid. Monitor **system clocks and certificate expiry across every endpoint**.

## 8. Preparing Lab Certificates

For a lab replica set you administer:

1. Issue a dedicated CA for the lab environment—never use a production CA.
2. Issue each server leaf certificate with SANs matching its hostnames.
3. Include EKU `serverAuth`, plus `clientAuth` when internal roles require it.
4. Combine certificate + private key into PEM files per MongoDB configuration.
5. Ensure the server process can read the key while other users cannot.
6. Distribute the public CA cert for app/peer trust.
7. Verify the certificate chain, SANs, and validity dates before startup.

### 8.1. Inspecting Certificates with OpenSSL

~~~bash
openssl x509 -in mongo1.crt -noout -subject -issuer -dates
openssl x509 -in mongo1.crt -noout -ext subjectAltName
openssl x509 -in mongo1.crt -noout -ext extendedKeyUsage
~~~

This is an **inspection** tool, not production certificate issuance. Production PKI requires standardized issuers, SANs, subjects, EKUs, key algorithms, expirations, and rotation.

### 8.2. Protecting Private Keys

Never paste private keys into tickets, logs, artifacts, or shared commands. If private key compromise is suspected, follow certificate revocation/replacement procedures and assess blast radius.

## 9. `net.tls.mode: requireTLS` for `mongod`

Example replica set member using TLS for SCRAM clients and internal `keyFile`:

~~~yaml
# /etc/mongod.conf, condensed example
net:
  bindIp: 127.0.0.1,mongo1.db.internal
  port: 27017
  tls:
    mode: requireTLS
    certificateKeyFile: /etc/mongodb/tls/mongo1.pem
    CAFile: /etc/mongodb/tls/ca-chain.pem
    allowConnectionsWithoutCertificates: true

replication:
  replSetName: rs0

security:
  authorization: enabled
  keyFile: /etc/mongodb/secrets/cluster.key
~~~

### 9.1. Option Meanings

| Option | Role |
|---|---|
| `net.tls.mode: requireTLS` | Requires TLS connections; rejects plaintext MongoDB traffic |
| `certificateKeyFile` | PEM containing server certificate/private key |
| `CAFile` | CA trust material for verifying peers per configuration |
| `allowConnectionsWithoutCertificates: true` | Permits TLS clients without client certs; useful when apps use SCRAM |
| `security.authorization: enabled` | Enables MongoDB user/role enforcement |
| `security.keyFile` | Shared secret for internal authentication in keyFile mode |
| `replication.replSetName` | Replica set name; not a TLS setting |

**Note:** `allowConnectionsWithoutCertificates: true` does not allow **plaintext** when `mode: requireTLS` is set. It only allows clients not presenting a **TLS client certificate**. Without a client cert, valid database credentials are still required.

### 9.2. `bindIp` and Firewalls Remain Important

TLS does not replace network segmentation. Never open `27017` arbitrarily to the Internet. Bind only needed network interfaces and restrict allowed sources.

### 9.3. One Certificate for Every Node?

While policy might allow a multi-SAN certificate, sharing one private key across multiple hosts expands blast radius if one host is compromised. Prefer separate identities/keys per endpoint whenever PKI and topology permit.

## 10. TLS Modes on MongoDB Server

`net.tls.mode` typically offers:

| Mode | Meaning | Role |
|---|---|---|
| `disabled` | TLS is off | Unsuitable for encrypting production traffic |
| `allowTLS` | Accepts both TLS and non-TLS during transition | Controlled migration |
| `preferTLS` | Accepts mixed inbound, prefers TLS for internal outbound per server rules | Transition between modes |
| `requireTLS` | Accepts only TLS connections | Target steady state |

### 10.1. Node-by-Node Transition

Do not enable `requireTLS` on a primary before peers and clients have certificates and CA trust. If members cannot connect, the replica set can lose majority, replication, or availability.

### 10.2. Transitional Modes Must Have a Deadline

`allowTLS`/`preferTLS` exist to support mixed clusters during migration; while plaintext remains allowed, traffic can still be observed. Monitor non-TLS flows and schedule completion to `requireTLS` rather than leaving mixed mode indefinitely.

### 10.3. Server Config vs. Driver Options

`mongod.conf` uses `net.tls.*`; Node.js commonly uses `tls`/`tlsCAFile`; URIs use `tls=true`. Never put driver option names inside the server config file.

## 11. Internal Replica Set TLS: keyFile and x.509

**TLS** protects the network; **internal authentication** verifies a node is allowed to join the cluster. These two can be combined in different ways.

### 11.1. TLS + keyFile

~~~text
Member A ↔ Member B channel: protected by TLS
Internal identity: shared security.keyFile secret
Application auth: SCRAM or configured client auth mechanism
~~~

This is a valid replica set configuration. `keyFile` does not encrypt replication by itself, and TLS does not replace the shared internal secret.

### 11.2. TLS + x.509 Cluster Authentication

MongoDB can authenticate members using certificates via `security.clusterAuthMode: x509` on supported versions/topologies.

~~~yaml
# Illustrative x.509 internal authentication design
net:
  tls:
    mode: requireTLS
    certificateKeyFile: /etc/mongodb/tls/mongo1-server.pem
    CAFile: /etc/mongodb/tls/app-client-ca.pem
    clusterFile: /etc/mongodb/tls/mongo1-cluster.pem
    clusterCAFile: /etc/mongodb/tls/cluster-ca.pem

replication:
  replSetName: rs0

security:
  authorization: enabled
  clusterAuthMode: x509
~~~

`clusterFile` can supply a separate certificate/private key when a node authenticates to peers; `clusterCAFile` serves as internal trust when CAs are split. This config is **illustrative of the roles only**—verify exact cert subject, DN, EKU, CA trust, and version rules before applying.

### 11.3. Cluster Member Certificate Rules

Internal x.509 authentication enforces specific requirements on certificate identity—such as consistency of **O/OU/DC** subject attributes across members per MongoDB rules—alongside proper client/server TLS usage. Never self-sign an arbitrary leaf cert and expect `clusterAuthMode: x509` to accept it.

### 11.4. Migrating Internal Auth Is a Separate Change

Moving from `keyFile` to x.509 internal auth is **not just turning on TLS**. It changes how nodes verify each other and may require dedicated transitional modes and rolling procedures. Never change CAs, hostnames, `clusterAuthMode`, and network topology all at once without a rollback plan.

## 12. Internal TLS in a Sharded Cluster

| Source | Destination | Reason to Protect |
|---|---|---|
| Application | `mongos` | Queries/data/auth |
| `mongos` | Config server replica set | Metadata/cluster control |
| `mongos` | Shard replica sets | Routed commands/data |
| Members within each shard | Peers in replica set | Replication/heartbeat |
| Config server members | CSRS peers | Replication/heartbeat |
| Other cluster components | Required endpoints | Coordination and maintenance |

### 12.1. `mongos` Needs a Certificate

Because clients connect to routers, `mongos` must present a server certificate matching the hostname clients use. Simultaneously, the router must verify and be accepted by internal peers per policy.

### 12.2. Not Just One Shard

When adding a new shard, provision valid certificates/SANs and internal identities for every member of that shard; verify trust with routers, config servers, and replica set health. An expired certificate on a single shard can break only part of the workload, making it easy to miss if you only `ping` a router.

### 12.3. TLS Does Not Route Queries

TLS secures the network; it does not help `mongos` locate shards faster or replace shard keys/indexes. If scatter-gather queries are slow, analyze routing, data distribution, indexes, and network latency—never disable TLS to mask a query-plan issue.

## 13. Hostname Discovery and SAN

Replica set drivers can start from one seed host and discover all members:

~~~text
Seed URI: mongo-entry.example.internal
Advertised: mongo1.db.internal
            mongo2.db.internal
            mongo3.db.internal
~~~

Therefore every advertised hostname requires:

- DNS resolution from the client environment.
- Network connectivity.
- Matching leaf certificate SAN.
- A trust chain trusted by the client.

### 13.1. Failover Exposes Certificate Bugs

An app may connect smoothly to `mongo1` for weeks, then fail with hostname mismatch or unknown CA once `mongo2` is elected primary. Test failover and secondary selection before production.

### 13.2. IP Addresses and DNS SANs

URI `mongodb://10.20.0.5:27017` will not match a certificate containing only `DNS:mongo1.db.internal`. Use canonical DNS names or issue appropriate IP SANs. Never use `tlsAllowInvalidHostnames` as a fix.

### 13.3. Kubernetes/Containers

On Kubernetes, certificates must cover the names MongoDB members advertise via StatefulSet/service discovery. Do not issue only `DNS:localhost` and connect via Pod FQDN. When using an operator with built-in certificate management, prefer the operator's lifecycle workflow.

## 14. Mongosh with TLS Server Authentication + SCRAM

Connect:

~~~bash
mongosh "mongodb://mongo1.db.internal:27017/?tls=true" \
  --tlsCAFile /etc/app/tls/mongo-ca.pem \
  --username appUser \
  --authenticationDatabase admin
~~~

`mongosh` can prompt interactively for the password, keeping secrets out of command history.

Connect to a replica set:

~~~bash
mongosh "mongodb://mongo1.db.internal:27017,mongo2.db.internal:27017,mongo3.db.internal:27017/?replicaSet=rs0&tls=true" \
  --tlsCAFile /etc/app/tls/mongo-ca.pem \
  --username appUser \
  --authenticationDatabase admin
~~~

Once connected:

~~~javascript
db.adminCommand({ ping: 1 })
db.runCommand({ connectionStatus: 1 })
~~~

`ping` confirms the server processed a command and the TLS handshake succeeded; `connectionStatus` reports auth/roles, not a complete list of TLS protocols/ciphers.

### 14.1. Never Hardcode Passwords

Never place real passwords inside URIs in source code, CI logs, screenshots, or shell history. Use a secret manager and protected credential delivery. Special characters in URI credentials must also be properly percent-encoded when using URI syntax.

### 14.2. Client-Side TLS Validation

`--tlsCAFile` must point to the right public CA cert/bundle. If a cert lacks a SAN or is expired, fix the certificate/hostname instead of skipping validation.

## 15. Node.js Driver with TLS and SCRAM

~~~javascript
import { MongoClient } from "mongodb";

const uri =
  "mongodb://mongo1.db.internal:27017,mongo2.db.internal:27017,mongo3.db.internal:27017/" +
  "?replicaSet=rs0&authSource=admin&tls=true";

const client = new MongoClient(uri, {
  auth: {
    username: process.env.MONGODB_USERNAME,
    password: process.env.MONGODB_PASSWORD
  },
  tls: true,
  tlsCAFile: "/etc/app/tls/mongo-ca.pem",
  serverSelectionTimeoutMS: 5000
});

try {
  await client.connect();
  console.log(await client.db("admin").command({ ping: 1 }));
} finally {
  await client.close();
}
~~~

### 15.1. Node.js Options

| Option | Meaning |
|---|---|
| `tls: true` | Enables TLS |
| `tlsCAFile` | CA bundle for verifying the server |
| `tlsCertificateKeyFile` | Client cert + private key if mTLS is required |
| `tlsCertificateKeyFilePassword` | Password to unlock client private key if supported |
| `serverSelectionTimeoutMS` | Server selection timeout; does not bypass TLS errors |

When MongoDB uses a private CA, `tlsCAFile` lets the application trust the right issuer. With public CAs already in the default trust store, exact requirements may differ.

### 15.2. Reuse MongoClient

Creating a `MongoClient` per HTTP request causes excessive TLS handshakes, CPU load, latency, and socket churn. Reuse a pooled client across the service lifecycle; close it only on shutdown or controlled reconfiguration.

### 15.3. Avoid Anti-Patterns

~~~javascript
// DO NOT use in production.
const unsafe = new MongoClient(uri, {
  tls: true,
  tlsAllowInvalidCertificates: true,
  tlsAllowInvalidHostnames: true
});
~~~

Flags that skip certificate or hostname checks weaken peer verification and enable MITM attacks. They are never a valid fix for CA/SAN issues.

## 16. Java Sync Driver: TLS with CA Trust

~~~java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.MongoCredential;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import org.bson.Document;

public class MongoTlsDemo {
    public static void main(String[] args) {
        String uri =
            "mongodb://mongo1.db.internal:27017," +
            "mongo2.db.internal:27017," +
            "mongo3.db.internal:27017/" +
            "?replicaSet=rs0&tls=true";

        MongoCredential credential =
            MongoCredential.createScramSha256Credential(
                System.getenv("MONGODB_USERNAME"),
                "admin",
                System.getenv("MONGODB_PASSWORD").toCharArray()
            );

        MongoClientSettings settings = MongoClientSettings.builder()
            .applyConnectionString(new ConnectionString(uri))
            .credential(credential)
            .applyToSslSettings(ssl -> ssl.enabled(true))
            .build();

        try (MongoClient client = MongoClients.create(settings)) {
            Document ping = client.getDatabase("admin")
                .runCommand(new Document("ping", 1));
            System.out.println(ping.toJson());
        }
    }
}
~~~

### 16.1. Java Trust Store

If a private CA is absent from the JVM default truststore, use a PKCS#12 truststore or a custom `SSLContext` per organizational standards.

~~~bash
# Illustrates option names only. Never put real passwords into command history.
java \
  -Djavax.net.ssl.trustStore=/etc/app/tls/mongo-truststore.p12 \
  -Djavax.net.ssl.trustStoreType=PKCS12 \
  -Djavax.net.ssl.trustStorePassword=PLACEHOLDER_FROM_SECRET \
  -jar app.jar
~~~

In production, supply secrets securely rather than hardcoding them into startup scripts. JVM/JDK versions and truststore reload behavior can differ from Node.js. Never use a “trust-all” `TrustManager`.

### 16.2. Hostname Verification

The Java driver must verify server SANs. In a replica set, certificates must match every advertised hostname; succeeding against one seed host does not prove failover will succeed.

### 16.3. TLS Versions

TLS 1.2/1.3 support depends on MongoDB server, JDK/Java TLS provider, OS/OpenSSL, and security policy. If handshakes fail from protocol/cipher mismatch, align versions and ciphers—never disable certificate validation.

## 17. Client Certificates with `MONGODB-X509`

To authenticate an app with a certificate:

1. PKI issues a client leaf cert + private key with appropriate EKU (`clientAuth`).
2. The server trusts the CA signing the client certificate.
3. The driver presents the client certificate during the TLS handshake.
4. MongoDB extracts the subject/identity via `MONGODB-X509`.
5. A matching user in `$external` holds the required roles.

### 17.1. Mongosh

~~~bash
mongosh "mongodb://mongo1.db.internal:27017/?tls=true&authMechanism=MONGODB-X509&authSource=%24external" \
  --tlsCAFile /etc/app/tls/mongo-server-ca.pem \
  --tlsCertificateKeyFile /etc/app/tls/app-client.pem
~~~

`%24external` is the URI-encoded form of `$external`. Username/subject mapping and driver options must follow your MongoDB version—never pick arbitrary identities.

### 17.2. Node.js

~~~javascript
import { MongoClient } from "mongodb";

const client = new MongoClient(
  "mongodb://mongo1.db.internal:27017/?tls=true&authMechanism=MONGODB-X509&authSource=%24external",
  {
    tls: true,
    tlsCAFile: "/etc/app/tls/mongo-server-ca.pem",
    tlsCertificateKeyFile: "/etc/app/tls/app-client.pem"
  }
);

try {
  await client.connect();
  console.log(await client.db("admin").command({ ping: 1 }));
} finally {
  await client.close();
}
~~~

### 17.3. Does Not Automatically Grant Permissions

A client cert signed by a trusted CA only passes TLS verification; MongoDB still requires a matching user/identity and roles to execute commands. Never use a cluster member certificate as an application client credential.

### 17.4. mTLS Is Not Necessary for Every Application

If policy allows TLS server-auth + SCRAM, applications do not need separate client certificates. Decide on mTLS based on threat model and issuance/rotation overhead, not as a mandatory default for every MongoDB TLS deployment.

## 18. Distinguishing Authentication Failures from TLS Handshake Failures

| Symptom | Error Layer | What to Check |
|---|---|---|
| `certificate verify failed` | TLS trust | CA/intermediate/chain |
| `hostname mismatch` | TLS peer identity | SAN, DNS, URI host |
| `certificate expired` | TLS validity | Expiry, NTP/clock |
| `unsupported protocol` | TLS negotiation | MongoDB/JDK/Node/OpenSSL versions |
| `bad decrypt`/PEM error | TLS private key | File format, key password |
| `permission denied` reading PEM | OS security | Ownership/mount mode |
| `Authentication failed` | Post-TLS MongoDB auth | User/password/`authSource`/x509 subject |
| `Unauthorized` | MongoDB RBAC | Roles/permissions |
| `ServerSelectionTimeout` | Driver topology/connectivity | Nested TLS/DNS/network cause |

TLS errors usually occur **before** MongoDB user authentication. If TLS succeeded yet username/password failed, fix database credentials/roles instead of replacing server certificates.

### 18.1. Nested Causes

Drivers may surface a top-level `MongoServerSelectionError` or Java `MongoTimeoutException`. Inspect nested causes and driver logs to spot underlying cert/SAN/DNS errors, while redacting URI credentials.

### 18.2. One Client Succeeding Does Not Prove All Clients Will

`mongosh` may work using `--tlsCAFile` while a Java process lacks the CA in its truststore. Node may trust the CA via `tlsCAFile` while a new container image omits the file. Verify the **actual trust environment** of every runtime.

## 19. Probing a TLS Endpoint with OpenSSL

Only probe endpoints you are authorized to test:

~~~bash
openssl s_client \
  -connect mongo1.db.internal:27017 \
  -servername mongo1.db.internal \
  -CAfile /etc/app/tls/mongo-server-ca.pem \
  -verify_return_error
~~~

Inspect the certificate chain, issuer, validity, verify result, SNI, and protocol/cipher (where displayed). Inspect leaf certificates on the filesystem:

~~~bash
openssl x509 -in /etc/mongodb/tls/mongo1.crt \
  -noout -subject -issuer -dates -ext subjectAltName
~~~

### 19.1. Do Not Skip Verification in Probes and Declare Success

A probe can establish an encrypted TLS connection without fully checking chains/hostnames if invoked without verification flags. Run probes with strict validation and confirm using the actual driver.

### 19.2. Ping After OpenSSL

`openssl s_client` only diagnoses TLS—it does not prove MongoDB auth or topology works. Follow up with `mongosh`/driver `ping`, role checks, and failover connection tests.

## 20. Rolling Out TLS to a Replica Set

Never turn on `requireTLS` haphazardly on a live cluster. A controlled rollout:

1. Inventory members, advertised hostnames, client environments, and CAs/trust stores.
2. Issue and distribute certificates to **every node**; verify SAN/EKU/expiry/key permissions.
3. Update driver trust stores and test in staging.
4. Use migration modes such as `allowTLS`/`preferTLS` if needed, **following your version's supported procedure**.
5. Rolling-update members—typically secondaries first per runbook while maintaining majority.
6. Verify replication lag, heartbeats, election status, and client connections.
7. Confirm no plaintext clients remain, then switch all members to `requireTLS`.
8. Test failover and connections to all advertised hostnames.
9. Set up expiry/handshake monitoring and close out the migration.

This is a **conceptual plan**, not a substitute for your server version's exact command sequence. Some changes require rolling restarts/reconfigs, while some certificate rotations use dedicated commands.

### 20.1. Why Is Secondary-First Usually Helpful?

Keeping the primary and majority online during rolling updates minimizes downtime, though actual topology/HA capacity must be accounted for. Never restart multiple voting members simultaneously if doing so risks losing quorum.

### 20.2. Test Real Failover

Normal traffic might only touch `mongo1`. After a primary step-down, drivers must talk to `mongo2`/`mongo3`; if cert SANs differ or CA trust is wrong, errors appear only then. Test all nodes and paths.

## 21. Rollout in a Sharded Cluster

In addition to per-replica-set steps, verify:

- All `mongos` routers have valid certificates and trust.
- The config server replica set maintains majority and metadata availability.
- All shard replica sets share consistent TLS and internal auth.
- `mongos`↔config servers and `mongos`↔shards links work.
- All cluster members hold valid certificate identities (if using cluster x.509).
- Newly added routers are not missing CAs/certs.
- Applications connect only via topology-appropriate `mongos` endpoints, if that is the cluster design.

### 21.1. Never Change the Whole Cluster at Once

Switching all `mongos`, config servers, and shards in one step without overlap or rollback can cause an outage. Break into phases, test, and closely monitor each component group.

### 21.2. Protect Coordination Traffic Too

TLS on app→`mongos` is not enough. If `mongos`→shards runs in plaintext, MongoDB data is exposed on internal paths. Inventory all real network segments, including cross-AZ links.

## 22. CA Rotation and Trust Overlap

Replacing a leaf certificate under the same CA rarely breaks trust stores. Replacing the **issuing CA** can cause clients and nodes to reject every endpoint.

~~~mermaid
flowchart LR
    Old["Clients trust old CA only"] --> Bundle["Distribute trust: old CA + new CA"]
    Bundle --> Rotate["Rotate leaf certs to new CA"]
    Rotate --> Verify["Verify all nodes/clients"]
    Verify --> Remove["Remove old CA once no dependencies remain"]
~~~

### 22.1. Reference Procedure

1. Issue the new CA and verify its chain and policy.
2. Add the new CA to all clients'/peers' trust bundles while keeping the old CA during overlap.
3. Verify Java/Node/`mongosh` processes actually load the updated trust; some runtimes require restart/reload.
4. Rotate server/internal leaf certificates via a rolling plan.
5. Test **new** connections, auth, replication, failover, and `mongos` routing.
6. Remove the old CA only after confirming no certificate or dependency still relies on it.

### 22.2. Wrong Ordering Causes Outages

Switching `mongod` to a leaf signed by the new CA before application truststores are updated causes clients to reject connections en masse. For cluster x.509, internal member trust is equally critical.

### 22.3. Certificate Pinning

Pinning a leaf certificate causes rotations even under the same CA to fail. If pinning policy exists, maintain an inventory and separate overlap/rollout plan instead of hardcoding fingerprints and forgetting certificate lifecycles.

## 23. Runtime Certificate Rotation

MongoDB supports runtime certificate rotation in certain versions, subject to rules on PEM paths, file contents, CAs, and commands.

~~~javascript
// Use only per runbook/version support with appropriate admin privileges.
db.adminCommand({ rotateCertificates: 1 })
~~~

Do not assume this command works identically on every version or updates all open TLS sessions. Always:

1. Check server version and command support.
2. Prepare new cert/key with proper SAN, issuer, EKU, and permissions.
3. Swap key material safely via OS/secret mount mechanisms.
4. Rotate or rolling-restart per runbook.
5. Test **new** handshakes, because existing pooled connections may hold old TLS sessions.
6. Monitor replication, router health, and client errors.

### 23.1. Cert Expiry Monitoring

Example thresholds:

~~~text
T-30 days: ticket and rotation plan
T-14 days: verify rollout status
T-7 days: escalation
T-1 day: urgent alert
~~~

These are illustrative policy milestones, not MongoDB defaults. For short-lived certificates, use automated PKI and monitoring with an appropriate cadence.

## 24. Load Balancers, TLS Termination, and End-to-End Encryption

A path with a load balancer:

~~~text
App --TLS--> Load Balancer --plaintext--> mongos
~~~

cannot be called **end-to-end encrypted**. Data on LB→`mongos` travels in plaintext. If policy requires end-to-end encryption, choose:

- **TLS passthrough** to the MongoDB endpoint.
- **TLS termination + re-encryption** from the LB to `mongos`, with proper certificate/hostname validation on the backend hop.

### 24.1. Trust Boundary

A load balancer that terminates TLS sees plaintext in memory. It must be treated as a trusted component with auditing, admin controls, and key management.

### 24.2. MongoDB Is Not HTTP

MongoDB drivers perform topology discovery, pooling, and failover. Never place an HTTP-only proxy in front of a replica set assuming it understands the protocol; choose networking components that genuinely support MongoDB connection semantics.

### 24.3. Hostname Must Match on the Client Side

If the app connects to `mongo.example.com`, the presented certificate needs a SAN matching `mongo.example.com`. Passing traffic straight through to a server carrying only `mongo1.db.internal` will fail hostname verification. Design DNS/PKI/LB properly instead of disabling hostname checks.

## 25. Anti-Patterns to Avoid

| Anti-Pattern | Risk | Alternative |
|---|---|---|
| `tlsAllowInvalidCertificates: true` | Skips full issuer/cert validation; enables MITM | Fix trust chain |
| `tlsAllowInvalidHostnames: true` | Allows connecting to spoofed endpoints | Issue proper SAN / use matching DNS |
| `tlsInsecure: true` | Disables critical TLS checks | Configure TLS properly |
| CN-only certificate | Incompatible with modern hostname checks | DNS/IP SAN |
| Connecting by IP with DNS-only SAN | TLS hostname mismatch | Canonical DNS or IP SAN |
| Thinking `keyFile` encrypts replication | Internal traffic may remain plaintext | TLS alongside auth mode |
| Thinking `requireTLS` enables x.509 | Confuses transport with member auth | Configure `clusterAuthMode`/`keyFile` separately |
| Using cluster member cert for apps | Identity/privilege exposure risk | Dedicated client cert profile |
| Committing PEM private keys to Git | Exposes endpoint identity | Secret manager/private storage |
| One cert/key shared across all nodes | Expands blast radius | Per-node identity/key where feasible |
| Testing only the seed hostname | Failover exposes SAN mismatches | Test all advertised members |
| CA rotation without overlap | Clients lose trust | Distribute CA bundle before rotating leaves |
| Enabling `requireTLS` on one node before peers | Risks losing majority/replication | Controlled rolling migration |
| Terminating TLS at LB with plaintext backend | Breaks end-to-end encryption | Passthrough/re-encryption |
| Creating a `MongoClient` per HTTP request | Handshake storm | Reuse pooled client |
| Disabling TLS when latency rises | Leaves data unprotected | Profile queries/network/handshakes |

## 26. Security Policy: TLS Does Not Replace RBAC and Encryption at Rest

| Mechanism | Scope |
|---|---|
| TLS | Data in transit over the network |
| SCRAM / MONGODB-X509 | Application/user identity |
| KeyFile / cluster x.509 | Internal member authentication |
| MongoDB RBAC | Command execution and data access privileges |
| Application authorization | Tenant/business permissions |
| Encryption at rest | Data files/backups on storage |
| Client-side/field-level encryption | Sensitive fields at the application layer |
| Audit/monitoring | Detection and investigation capability |

TLS lets apps connect safely to trusted endpoints, yet the server still processes plaintext of fields not encrypted client-side. If your threat model restricts database operators from reading sensitive fields, evaluate application-side/field-level encryption separately.

## 27. Monitoring and Alerting on TLS

| Category | Metric/Observation | Why It Matters |
|---|---|---|
| Certificate inventory | Issuer, SAN, serial/fingerprint, `NotAfter` | Know which cert is on which node |
| Expiry | Days until expiry | Proactive rotation |
| TLS handshakes | Failure rate, protocol versions | Catch CA/SAN/cipher errors |
| MongoDB auth | SCRAM/x509 authentication failures | Separate TLS errors from credential errors |
| Connection pools | New/active/idle sockets | Detect reconnect/handshake storms |
| Replica health | Members, elections, lag | Internal TLS affects quorum |
| Sharded health | `mongos` reachability, shard/config errors | Partial cluster failures |
| Rotation status | Deployed cert version per node | Avoid missed members |
| Clock | NTP drift | False not-yet-valid/expired errors |
| Key permissions | Mount/read errors | Prevent startup failures |

These names are **instrumentation suggestions**, not verbatim MongoDB metric names. Combine infrastructure monitoring, logs, driver command monitoring, and PKI certificate exporters.

### 27.1. Never Log Credentials

When diagnosing issues, record hostname, error reason, timestamp, and policy-approved fingerprints; never log passwords, private keys, or full URIs with credentials. Nested exceptions are helpful, provided secrets are redacted.

### 27.2. Separate Handshake Failures from Login Failures

A TLS handshake failure means the client never established a trusted channel; a login failure means TLS likely passed while MongoDB user/`authSource`/roles failed. Alert on both separately to pinpoint root causes quickly.

## 28. Exercise A — Verifying CA and SAN

Given:

~~~text
Root CA: CorpRoot
Intermediate CA: CorpIntermediate
Server leaf SAN: DNS:mongo1.db.internal
Client URI: mongo1.db.internal
Client trust: CorpRoot and sufficient chain to verify
~~~

Answer:

1. Does the URI hostname match the SAN?
2. What happens if you change the URI to `10.20.0.5` when the certificate lacks an IP SAN?
3. If the intermediate CA is missing, where should it be fixed?
4. If the leaf expires, can you use `tlsAllowInvalidCertificates: true` as a production fix?

## 29. Exercise B — TLS + SCRAM

A system has:

~~~text
Server: net.tls.mode=requireTLS
Server: allowConnectionsWithoutCertificates=true
User authentication: SCRAM
Application: tls=true, valid CA and hostname
Application client certificate: none
~~~

Can the application connect with a valid username/password? Why does `allowConnectionsWithoutCertificates` not permit plaintext? If credentials are wrong, which layer fails?

## 30. Exercise C — Hostname Failover

Replica set:

~~~text
mongo1.db.internal:27017
mongo2.db.internal:27017
mongo3.db.internal:27017
~~~

`mongo1`'s certificate has the right SAN, while `mongo2` only has `DNS:localhost`. Why can the client work for a while and then fail during a topology change? How would you fix PKI/DNS, and what would you test?

## 31. Exercise D — mongod Configuration

Explain:

~~~yaml
net:
  tls:
    mode: requireTLS
    certificateKeyFile: /etc/mongodb/tls/mongo1.pem
    CAFile: /etc/mongodb/tls/ca-chain.pem

security:
  authorization: enabled
  keyFile: /etc/mongodb/secrets/cluster.key
~~~

Distinguish the server certificate, CA trust, internal `keyFile`, and MongoDB authorization. Why must you not omit `authorization` simply because `requireTLS` is enabled?

## 32. Exercise E — keyFile vs. Internal x.509

A colleague says:

> “Because the replica set uses TLS, `clusterAuthMode` must default to x.509.”

Correct this statement and contrast **TLS + keyFile** with **TLS + cluster x.509**, including certificate/subject/secret requirements.

## 33. Exercise F — Node.js Private CA

~~~javascript
const client = new MongoClient(uri, {
  tls: true,
  tlsCAFile: "/etc/app/tls/mongo-ca.pem",
  auth: {
    username: process.env.MONGODB_USERNAME,
    password: process.env.MONGODB_PASSWORD
  }
});
~~~

Explain what `tlsCAFile` does. If the server permits SCRAM clients without certs, is `tlsCertificateKeyFile` required? Why avoid creating a `MongoClient` per request?

## 34. Exercise G — Java Trust Store

Node connects using `tlsCAFile`; Java fails with `PKIX path building failed`. Check the JVM trust store, intermediate CA, JDK TLS protocols, and DNS/SAN. Why not solve this with a trust-all `TrustManager`?

## 35. Exercise H — CA Rotation

An old CA signed leaf certificates across the entire cluster; the team wants to replace the CA. Plan from **distributing new CA trust** to **rotating leaves** and **removing the old CA**. What must you verify for Java containers that have not reloaded trust and for failover?

## 36. Exercise I — Load Balancer

~~~text
App --TLS--> LB --plaintext--> mongos
~~~

Does this count as end-to-end encryption? Propose two architectures that satisfy a policy protecting the LB→`mongos` hop. Which hostname must the client-facing certificate match?

## 37. Exercise J — MONGODB-X509

The TLS handshake succeeds with a client certificate signed by a trusted CA, yet the database returns `Authentication failed`. Check:

- `authMechanism=MONGODB-X509`.
- `authSource=$external`.
- Certificate subject/DN mapping.
- Whether the MongoDB user was provisioned.
- Roles and EKU/issuer policy.

Why must cluster member certificates never be used as app certificates?

## 38. Exercise K — Observability

Design a dashboard including:

~~~text
Certificate days-to-expiry
TLS handshake failure rate
MongoDB authentication failure rate
Replica set member health and lag
Mongos/config/shard connectivity
Client pool reconnect rate
Certificate version per node
~~~

Assign owners and alert thresholds; explain how to distinguish an expired certificate from a wrong password.

## 39. Answer Hints

**A:** The hostname matches the DNS SAN. Using an IP fails hostname verification without an IP SAN. Ensure complete CA/intermediate chains and replace expired certs instead of disabling validation.

**B:** Server-auth TLS + SCRAM works when the server allows clients without certificates; `requireTLS` still forbids plaintext. Wrong credentials cause a post-TLS MongoDB auth failure.

**C:** During failover, the driver switches to `mongo2` and rejects the cert because its SAN is only `localhost`. Issue certificates for every advertised hostname; test each member and failover.

**D:** `requireTLS` protects transport; `certificateKeyFile` supplies server identity; `CAFile` provides trust; `keyFile` authenticates members internally; `authorization` enforces user roles.

**E:** TLS does not dictate `clusterAuthMode`. `keyFile` is shared-secret auth; x.509 is certificate-based member identity with specific subject/EKU/trust requirements.

**F:** `tlsCAFile` verifies a private CA. SCRAM does not necessarily require a client certificate. Pool `MongoClient` to avoid handshake storms.

**G:** Java uses its own JVM truststore; import the CA or configure a proper `SSLContext`, and check protocols/SANs. Trust-all opens MITM risks.

**H:** Distribute new trust first, keep overlap, rolling-rotate leaves, test new connections/replication/failover, and remove the old CA only after dependencies are gone.

**I:** Not end-to-end encrypted. Use TLS passthrough or terminate+re-encrypt; the client-visible endpoint certificate must match the hostname the app connects to.

**J:** A valid TLS certificate does not automatically provision MongoDB users/roles. Configure proper x.509 mechanism/`authSource`/user identity and keep app profiles separate from members.

**K:** Monitor expiry alongside handshake failures, auth failures, and member health; triage by layer to address the true cause.

## 40. Review Questions

**1. What does TLS protect?** — Traffic confidentiality and integrity, plus certificate-based endpoint verification.

**2. Does TLS automatically enable MongoDB RBAC?** — No; you must configure users/roles and authorization.

**3. How does TLS differ from mTLS?** — In server-auth TLS the client verifies the server; mTLS also verifies the client certificate.

**4. Can SCRAM work over TLS without a client cert?** — Yes, if server policy permits it.

**5. What is a SAN?** — Subject Alternative Name, containing DNS/IP identities for hostname verification.

**6. Why avoid CN-only certs?** — Modern clients rely on SANs; CN-only lacks reliable compatibility.

**7. What does `net.tls.mode: requireTLS` do?** — Enforces TLS for incoming connections.

**8. Is `certificateKeyFile` a CA trust store?** — No; it contains the server's identity certificate and private key.

**9. What is `CAFile` used for?** — Supplies CA trust for peer certificate validation per configuration.

**10. How does `clusterFile` differ from `certificateKeyFile`?** — It can hold a separate identity for internal member authentication.

**11. Does `keyFile` encrypt replication traffic?** — Not by itself; TLS encrypts the network channel.

**12. Are internal x.509 auth and `MONGODB-X509` client auth identical?** — Both are certificate-based, but differ in role, identity, and trust policy.

**13. Why test all replica set hosts?** — Driver discovery/failover can connect to members beyond the seed host.

**14. Does an IP URI match a DNS SAN?** — Not by default; you need an IP SAN or matching DNS name.

**15. Which Node.js option specifies a private CA?** — Typically `tlsCAFile`.

**16. Where does Java read CAs from?** — The JVM truststore or a properly configured `SSLContext`/trust manager.

**17. Why avoid `tlsAllowInvalidCertificates`?** — It weakens peer verification and creates MITM risk.

**18. Does CA rotation need overlap?** — Usually yes, so clients trust both old and new CAs during transition.

**19. Is terminating TLS at an LB and sending plaintext afterward end-to-end encrypted?** — No.

**20. Can an expired cert disrupt a replica set?** — Yes, internal handshakes can fail.

**21. When is `$external` used?** — As the authentication database for external mechanisms such as `MONGODB-X509`.

**22. Does TLS encrypt data at rest?** — No; separate at-rest mechanisms are needed.

**23. Is creating one `MongoClient` per request good?** — No; it causes excessive handshakes and resource overhead.

**24. Does a successful `ping` prove cluster-wide certificate rotation succeeded?** — No; test all peers, new connections, failover, and trust across all clients.

**25. Is a MongoDB `Authentication failed` error always a CA error?** — Not necessarily; check credentials, `authSource`, and x.509 roles.

## 41. Quick Reference Table

| Need | Setting |
|---|---|
| Enforce server TLS | `net.tls.mode: requireTLS` |
| Server cert/key | `net.tls.certificateKeyFile` |
| CA trust | `net.tls.CAFile` |
| Member cert/key | `net.tls.clusterFile` when used |
| Member CA | `net.tls.clusterCAFile` when used |
| Client without cert using SCRAM | `allowConnectionsWithoutCertificates` per policy |
| KeyFile internal auth | `security.keyFile` |
| X.509 internal auth | `security.clusterAuthMode: x509` |
| MongoDB RBAC | `security.authorization: enabled` |
| Mongosh TLS | `tls=true` and `--tlsCAFile` |
| Node TLS | `tls: true` and `tlsCAFile` |
| Node client mTLS | `tlsCertificateKeyFile` |
| Java CA | JVM truststore/`SSLContext` |
| Client x.509 login | `MONGODB-X509` and `$external` |
| Inspect cert file | `openssl x509` |
| Probe TLS | `openssl s_client` |
| Test MongoDB | Driver/`mongosh` `ping` |
| CA rotation | Trust overlap + rolling leaf replacement |
| Avoid | `tlsInsecure`/invalid certificates/hostnames |

## 42. Pre-Production TLS Checklist

- [ ] Have all application→`mongod`/`mongos` and internal connections been inventoried?
- [ ] Do all leaf certificates carry SANs matching advertised hostnames?
- [ ] Are CA/intermediate chains complete and driver truststores aligned?
- [ ] Do EKUs, validity periods, key lengths, and issuers meet PKI policy?
- [ ] Are private keys protected and absent from repos/logs?
- [ ] Is `requireTLS` enforced on all endpoints after rollout?
- [ ] Are `authorization: enabled` and least-privilege roles configured?
- [ ] Is transport TLS clearly separated from SCRAM/x.509/`keyFile` internal auth?
- [ ] If apps omit client certs, does server policy explicitly allow it?
- [ ] For cluster x.509, are DN/subject rules and cluster CAs verified?
- [ ] Do replica set seeds and advertised hosts resolve via DNS?
- [ ] Have all members, failover, and secondary selection been tested?
- [ ] Are Node/Java/`mongosh` free of invalid-cert/hostname flags?
- [ ] Are `MongoClient` pooling and timeouts configured sensibly?
- [ ] Do firewalls/private networks restrict database exposure?
- [ ] Do LBs/proxies avoid unapproved plaintext hops?
- [ ] Are staging, rolling rollout, and rollback plans aligned with server version?
- [ ] Are cert expiry, handshake errors, and auth errors monitored separately?
- [ ] Does CA rotation include trust overlap and trust-reload checks?
- [ ] Have sharded cluster config/shard/`mongos` links been tested?
- [ ] Is TLS clearly distinguished from at-rest and field-level encryption?
- [ ] Are secrets provisioned securely with no hardcoded passwords?

## 43. Conclusion

**TLS protects MongoDB traffic across both layers: applications connecting to the database and cluster members communicating with one another.** A sound deployment requires trusted certificate chains, SANs matching hostnames, unexpired certificates, protected private keys, and ultimately `net.tls.mode: requireTLS` across all protected endpoints.

Keep **transport encryption** separate from **authentication**: SCRAM or `MONGODB-X509` authenticates applications; `keyFile` or cluster x.509 authenticates internal members; MongoDB RBAC governs access privileges. `tls=true` offers incomplete protection if clients skip certificate validation, and enabling TLS does not replace encryption at rest, application authorization, or network controls.

In production, the decisive factors are **certificate lifecycle management and cluster-wide consistency**. Issue proper SANs/EKUs, distribute CAs before rotating, replace certificates using a rolling runbook, test new connections and failover, monitor expiry/handshakes, and leave no plaintext hops outside approved security policy.
