# Managing Passwords, Certificates, and Secret Rotation in MongoDB

## 1. Context and Objectives

MongoDB can have authentication and authorization properly enabled yet still suffer security incidents if application passwords are pushed to Git, TLS certificates expire, private keys leak, or swapping a replica set key breaks member-to-member authentication.

**Secret rotation** is the process of issuing new credentials, shifting consumers to the new version, verifying operation, and revoking the old credentials. A solid process goes beyond changing one value in the database: it must govern the secrets manager, connection pools, certificate chains, replica-set health, access permissions, and rollback capability.

This lesson belongs to the **Security** chapter of the **Database Engine Document MongoDB** module, covering **Managing Passwords, Certificates, and Secret Rotation**.

After this lesson, you will be able to:

1. Distinguish SCRAM passwords, TLS private keys, client X.509 certificates, cluster keyfiles, and master encryption keys.
2. Create, inspect, and change database user passwords on self-managed MongoDB.
3. Follow the proper MongoDB Atlas workflow for managing database users.
4. Design low-downtime rotation using **dual-account / blue-green credentials**.
5. Govern TLS connections, CA chains, SANs, EKUs, truststores, and keystores.
6. Reload TLS certificates with `rotateCertificates` on supported deployments.
7. Design safe CA rollovers and client X.509 credential rotation.
8. Rotate cluster membership keyfiles using an old/new key overlap phase.
9. Distinguish cluster keyfiles from data-at-rest encryption keys, KMS/CMKs, and DEKs.
10. Integrate a secrets manager into the Java Sync Driver without hardcoding passwords.
11. Build a prepare → stage → switch → revoke runbook with monitoring and incident response.
12. Troubleshoot common errors and practice on realistic MongoDB scenarios.

**Key takeaway:** No single command rotates every type of secret in MongoDB. Each secret has a different scope, privilege model, operational mechanism, and recovery requirement.

## 2. Classify Secrets Before Rotating

| Secret | Used By | Purpose | Primary Rotation Method |
|---|---|---|---|
| SCRAM password | Application/human DB users | Authenticates clients to MongoDB | Change password or create new user |
| Server TLS certificate + private key | `mongod` / `mongos` | Verifies server, encrypts traffic | Issue new cert, reload or rolling restart |
| Client X.509 certificate + private key | App/`mongosh` | mTLS, client authentication | Issue new client cert, migrate clients, revoke old |
| CA/trust bundle | Clients/servers | Trusts certificate chains | Overlap old CA and new CA |
| Cluster keyfile | Replica-set/sharded members | Internal membership authentication | Overlap old+new keys, rolling restart |
| Internal member X.509 certificate | MongoDB nodes | Internal mTLS authentication | Issue certs, ensure DN/EKU/CA, rotate node by node |
| KMS/CMK master key | Storage encryption | Protects data encryption keys | KMS/KMIP workflow, not SCRAM password change |
| Data Encryption Key (DEK) | CSFLE/Queryable Encryption | Encrypts fields | Rewrap or rotate per encryption mechanism |
| Secret manager token | Workloads/automation | Fetches secrets above | Short-lived identity/token, policy rotation |

First three questions for every secret:

- **Who knows or uses the secret?** Including APIs, workers, cronjobs, ETL, backups, and monitoring.
- **What is the impact if lost?** Just one application, or the entire cluster/backups?
- **Can old and new secrets be accepted simultaneously?** This underpins low-disruption rotation.

### 2.1. Authentication, Authorization, and Encryption Do Not Replace Each Other

~~~text
Authentication                  Authorization                  Encryption
"Who is connecting?"            "What are they allowed to do?" "Is data protected?"
SCRAM / X.509 / OIDC            Roles, privileges              TLS / at rest / CSFLE
~~~

Changing a password while leaving a service on the `root` role does not fix over-privileged access. Enabling TLS without enabling database authentication does not provide authorization either.

### 2.2. Secret Inventories Never Contain Secret Values

Example inventory table:

| Logical Name | Owner | Consumers | Environment | Rotation Deadline |
|---|---|---|---|---|
| `mongo/orders-api/prod` | Orders team | API, worker | production | Per policy |
| `mongo/rs0/internal` | Platform team | `mongod` nodes | production | Per policy |
| `mongo/rs0/tls` | Platform team | `mongod` + `mongos` | production | Before cert expiry |

Store paths and metadata—**never** paste plaintext passwords, private keys, or URIs with credentials into inventory tables.

## 3. Distinguishing MongoDB Atlas and Self-Managed

| Administration | MongoDB Atlas | Self-Managed MongoDB |
|---|---|---|
| Create/edit database users | Atlas UI/CLI/Admin API/supported integrations | `db.createUser`, `db.updateUser` |
| Change database password | Atlas management plane | `db.changeUserPassword` |
| Server TLS certificates | Managed by Atlas infrastructure | Managed by organization |
| Internal keyfile | Managed by Atlas | Manage nodes and keyfiles directly |
| Client X.509 | Via Atlas workflow | X.509 user in `$external` |
| KMS/master keys | Atlas integration per tier/config | Enterprise/KMIP or equivalent solution |

**Never use `db.changeUserPassword()` to modify an Atlas database user.** Atlas requires managing users via the Atlas UI, CLI, Administration API, or supported integrations; MongoDB docs note that direct changes made outside it may be reverted.

### 3.1. Two Types of Users on Atlas

- **Atlas user:** human/identity accessing the project/organization management console.
- **Database user:** principal used by applications or tools to access MongoDB data.

Changing an Atlas console password does not change any database user's password, and vice versa.

### 3.2. Passwordless Options Can Be Better Than Long-Lived Passwords

Mechanisms like X.509, AWS IAM, and OIDC workload identity federation can eliminate long-lived passwords on supported deployments. However, OIDC/IAM still have token lifecycles, trust policies, and permissions to govern, and are not universally available across every tier, edition, or driver.

## 4. Threat Model: Where Do Secrets Commonly Leak?

Common cases:

- Connection URIs containing passwords committed to Git.
- CI jobs printing raw environment variables to logs.
- Passwords passed in command-line args, shell history, or process listings.
- Docker images containing PEM private keys.
- Kubernetes Secrets with overly broad read permissions or unrotated inside running processes.
- TLS errors “fixed” using `tlsInsecure=true`.
- One credential shared across multiple services and environments.
- Staff leaving while accounts/secret manager access remain active.
- Old certificates renewed yet **never revoked** after private key exposure.
- Cluster keyfiles copied into uncontrolled backups.

Baseline controls:

1. Give each service/environment its own principal.
2. Grant only required MongoDB roles.
3. Use TLS to protect credentials in transit.
4. Distribute secrets over authorized, audited channels.
5. Maintain risk/compliance-based rotation schedules.
6. Ensure revocation capability on compromise.
7. Never log plaintext secrets in logs, metrics, or tickets.

## 5. SCRAM Passwords in MongoDB

MongoDB supports SCRAM-SHA-1 and SCRAM-SHA-256; modern versions default appropriately to SCRAM-SHA-256.

SCRAM is a challenge-response mechanism and the server does not store plaintext passwords. **However**, operations creating or changing database passwords can transmit values needing protection over the network. Use TLS whenever performing user management.

### 5.1. authSource Is Where the User Is Defined

A user may live in the `appdata` database:

~~~javascript
use appdata
~~~

When authenticating that user, the connection must select the matching auth database, e.g., `authSource=appdata`. For Atlas SCRAM database users, `admin` is typically the authentication database per Atlas docs.

### 5.2. Password Requirements

- Generated randomly via a trustworthy CSPRNG.
- Sufficiently long per security policy.
- Never reuse passwords between prod and staging.
- Never place passwords in versioned source or config files.
- Never disclose passwords in tickets or chat.
- Never use admin/`root` accounts for daily app read/write workloads.

## 6. Creating a SCRAM User on Self-Managed MongoDB

**Run only on a self-managed MongoDB lab with authentication and TLS enabled and appropriate admin privileges.**

~~~javascript
use appdata

db.createUser({
  user: "orders_svc_v1",
  pwd: passwordPrompt(),
  roles: [
    { role: "readWrite", db: "appdata" }
  ],
  mechanisms: ["SCRAM-SHA-256"]
});
~~~

`passwordPrompt()` prompts interactively instead of hardcoding secrets in commands. It reduces exposure in history/source, though it does not protect secrets if the terminal session is recorded or transport lacks TLS.

### 6.1. Least Privilege

If a report only reads data, assign `read` instead of `readWrite`. When an app only touches a few collections, consider a resource-scoped custom role to narrow blast radius.

Never grant `root`, `dbOwner`, or `userAdminAnyDatabase` just to “stop permission errors”.

### 6.2. Inspecting User Metadata

~~~javascript
use appdata

db.getUser("orders_svc_v1");
~~~

Inspect roles and mechanisms—do not print or attempt to retrieve plaintext passwords. MongoDB does not expose original passwords as readable fields.

### 6.3. Inspecting Current Session Privileges

~~~javascript
db.runCommand({
  connectionStatus: 1,
  showPrivileges: true
});
~~~

The output reports the active principal and privileges. Beyond `ping`, a canary should verify **safe read/write checks on test data**—never run destructive commands on production data.

## 7. Changing Passwords on Self-Managed: Direct Updates and Limits

In the database containing the user:

~~~javascript
use appdata

db.changeUserPassword(
  "orders_svc_v1",
  passwordPrompt()
);
~~~

Or:

~~~javascript
use appdata

db.updateUser(
  "orders_svc_v1",
  { pwd: passwordPrompt() }
);
~~~

Requires appropriate `changePassword` privilege on the managed user.

### 7.1. Why Can Direct Password Changes Cause Disruption?

~~~text
T0: app clients are using oldPassword
T1: server switches to newPassword
T2: pod A receives newPassword
T3: pod B is still using oldPassword
~~~

After T1, **new authentication attempts** with the old password fail. Already-authenticated connections may survive until closed or until pools open fresh connections. Never rely on surviving old connections to assume rotation is error-free.

### 7.2. A Single SCRAM User Does Not Support Old+New Passwords Simultaneously

In standard operation, `changeUserPassword()` replaces the user's credential; it does not create an overlap window accepting both old and new passwords for the same user.

When uptime matters, use **dual-account rotation** instead of changing one user's password live under running pods.

### 7.3. Errors to Distinguish

`AuthenticationFailed` can result from:

- Wrong username.
- Wrong `authSource`.
- Stale password version.
- Incompatible SCRAM mechanism.
- Unencoded special characters in URI password.
- Secret rotated without refreshing the connection pool.

TLS handshake failures happen **before** SCRAM authentication succeeds; do not automatically blame the password.

## 8. Dual-Account Rotation: Low-Downtime Procedure

Suppose service `orders-api` uses `orders_svc_v1`.

Instead of resetting `v1`'s password immediately, create `orders_svc_v2` with equivalent or narrower roles:

~~~javascript
use appdata

db.createUser({
  user: "orders_svc_v2",
  pwd: passwordPrompt(),
  roles: [
    { role: "readWrite", db: "appdata" }
  ],
  mechanisms: ["SCRAM-SHA-256"]
});
~~~

During transition, both `v1` and `v2` can authenticate.

~~~text
                 Secrets Manager
              /                   \
           v1 secret            v2 secret
              |                    |
         Old app pods         New app pods
              \                    /
                     MongoDB
                 users v1 and v2
~~~

### 8.1. Step 1 — Inventory Consumers

List API replicas, background workers, cronjobs, ETL jobs, migration scripts, backup/export tools, and infrequent jobs. Missing a monthly cronjob means failures only surface long after rotation.

### 8.2. Step 2 — Create and Distribute v2

Generate a new password in the secrets manager, create `v2`, and grant read access only to the intended workload identity. Keep passwords out of images, repos, and tickets.

### 8.3. Step 3 — Canary

A fresh instance:

1. Fetches the `v2` secret.
2. Builds a new `MongoClient`/connection pool.
3. Verifies TLS chain and hostname.
4. Authenticates via SCRAM.
5. Runs `ping` and permitted application operations.
6. Monitors authentication errors, pool errors, and latency.

### 8.4. Step 4 — Rollout

Roll through pod groups and workers, watching new connections, error code 18, API 5xxs, and job failures. Confirm every consumer runs on `v2`.

### 8.5. Step 5 — Revoke v1

Only after confirming all consumers have switched:

~~~javascript
use appdata

db.dropUser("orders_svc_v1");
~~~

This is an irreversible privilege change—execute only with approval and a runbook. When a security incident demands urgent revocation, prioritize containment and accept controlled mitigation for any brief disruption.

### 8.6. Rollback

If `v2` is misconfigured, fall back to `v1` **only if `v1` was not compromised** and remains active. If `v1` leaked, rolling back to `v1` is unsafe.

### 8.7. Comparing the Two Strategies

| Criterion | Same-User Password Change | Dual-Account |
|---|---|---|
| Old/new credentials overlap | Not natively | Yes |
| Canary before revoking old | Hard | Yes |
| Server cutover | Single step | Create new, switch, revoke |
| Downtime risk | Higher if consumers reload slowly | Usually lower |
| Cleanup | Simple | Must drop old user |
| Rollback | May need another reset | Can revert to old user if uncompromised |

## 9. Managing Users on MongoDB Atlas

On Atlas:

1. Open the right project.
2. Go to **Security → Database & Network Access**.
3. Open **Database Users**.
4. Edit an existing SCRAM user or create a `v2` user.
5. Assign appropriate roles.
6. Store credentials in your secrets manager.
7. Roll out applications.
8. Revoke the old user after verification.

Atlas CLI and the Atlas Administration API also support database user automation.

**Do not use**:

~~~javascript
// Not a supported way to manage Atlas database users.
db.changeUserPassword("orders_svc_v1", passwordPrompt());
~~~

### 9.1. Atlas Passwordless Options

Depending on tier/driver/version, Atlas supports X.509, AWS IAM, and workload identity federation (OIDC/OAuth 2.0).

If you have trusted cloud/IdP workload identity, this can remove long-lived passwords from app configs. Token refresh, claims, IAM policies, and deployment limits still require governance.

### 9.2. Database Users Differ from Atlas Console Users

Atlas project administration and database access are two separate layers. Never grant an application project-admin permissions just to connect to the database.

## 10. Secrets Managers and How Applications Receive Credentials

A common design:

~~~text
Secret rotation controller
          |
          v
   Secrets Manager
          |
   +------+------+
   |             |
   v             v
App Pod A      App Pod B
   |             |
MongoClient    MongoClient
   \             /
         MongoDB
~~~

The Secrets Manager may be Vault, a cloud secret manager, or an internal platform supporting versioning, policies, and auditing.

### 10.1. Integration Principles

- Each workload reads only the secrets it needs.
- Use workload identity/short-lived tokens to read secrets where available.
- Keep logical secret names stable while versions increment.
- Maintain staging/current/retired lifecycles.
- Never print plaintext to CI logs.
- Audit secret reads and updates.
- Define recovery procedures if the secret manager is unavailable.

### 10.2. Environment Variables Do Not Auto-Reload

A process that read environment variables at startup will not automatically pick up changes when a Kubernetes Secret or cloud secret updates. Mounted secret files may update on disk, yet the application still needs logic to reload them and rebuild clients.

**Updating a secret in the vault does not update already-open connections.**

### 10.3. Never Hardcode Secrets into URIs

Safer placeholder format in docs:

~~~text
mongodb://db1.example.test:27017/?authSource=appdata&tls=true
~~~

If a URI embeds a real username/password, treat the entire URI as a secret. Characters `: / ? # [ ] @` in usernames/passwords must be percent-encoded when placed in a connection string.

### 10.4. Environment Separation

Never reuse production passwords in staging. Never let staging consumers read `mongo/orders/prod`. Audit IAM bindings and namespace secret scopes.

## 11. TLS: Encrypting Traffic and Verifying the Server

TLS protects traffic between applications and `mongod`/`mongos`.

~~~text
Application / mongosh
        |
        | verify server CA + hostname
        v
      TLS
        |
        v
mongod / mongos
~~~

The TLS server certificate ensures the client connects to the genuine server vouched for by a trusted CA; SCRAM verifies database user identity at a separate layer.

### 11.1. Components of TLS

- **Leaf/server certificate:** identifies the endpoint.
- **Private key:** secret proving ownership of the certificate.
- **Intermediate/root CA:** trust chain used to verify certificates.
- **SAN:** hostnames/IPs certified by the certificate.
- **Validity:** Not Before / Not After.
- **EKU:** whether the certificate authenticates servers or clients.

### 11.2. SAN and Hostname

If a client connects to `db1.example.test` while the certificate SAN only contains `db2.example.test`, hostname verification fails.

Never fix this with `tlsInsecure=true` or `tlsAllowInvalidHostnames=true` in production. Fix the certificate or hostname.

### 11.3. TLS Does Not Grant MongoDB Permissions

A client can verify the server certificate yet fail SCRAM auth due to missing user/password or wrong `authSource`. Conversely, even a valid password must never travel over a non-TLS network.

## 12. Configuring TLS on Self-Managed mongod

Illustrative snippet—**not a complete config file for a replica set**:

~~~yaml
net:
  port: 27017
  tls:
    mode: requireTLS
    certificateKeyFile: /etc/mongodb/tls/server.pem
    CAFile: /etc/mongodb/tls/trusted-ca.pem

security:
  authorization: enabled
~~~

- `requireTLS`: requires TLS connections.
- `certificateKeyFile`: PEM holding server certificate and matching private key.
- `CAFile`: trust chain for verifying peer certificates when required.
- `authorization: enabled`: enforces access control.

Replica sets and sharded clusters also need internal authentication and topology settings. Never copy this short snippet over a live `mongod.conf`.

### 12.1. Private Key Permissions

Private keys must be readable only by the service process and authorized operators. Never:

- Commit PEMs to Git.
- Bake private keys into Docker images.
- Send PEMs over tickets or chat.
- Log key contents.
- Leave files world-readable on the host.

### 12.2. Inspecting Certificate Info Without Printing Private Keys

On a machine with OpenSSL:

~~~bash
openssl x509 \
  -in /etc/mongodb/tls/server.pem \
  -noout -dates -subject -issuer -ext subjectAltName
~~~

Inspect `notBefore`/`notAfter`, subject, issuer, and SAN. If EKU is present, ensure it fits the certificate's role.

### 12.3. Monitoring Expiry

MongoDB logs warnings when a certificate is within 30 days of expiration on connection, yet proactive PKI alerts (e.g., 30/14/7 days prior or per policy) are still essential.

## 13. TLS Certificate Rotation with rotateCertificates

Starting in **MongoDB 5.0**, self-managed `mongod` and `mongos` support reloading certain TLS artifacts via `rotateCertificates`.

Per MongoDB docs, you can rotate:

- TLS certificates.
- CA files.
- CRL files on Linux/Windows under supported conditions.
- OCSP stapled responses can also be refreshed per config.

### 13.1. General Procedure

1. Issue the new certificate.
2. Verify chain, SAN, EKU, validity, and private key.
3. Replace the file at the **exact same path and filename** configured in MongoDB.
4. If an encrypted TLS cert uses `certificateKeyFilePassword`, the new PEM's passphrase must **match** the existing configured password for online rotation.
5. Connect `mongosh` to the specific process.
6. Run the command.
7. Open a **new connection** to verify the new certificate.
8. Inspect logs, errors, and replica health.
9. Repeat systematically across each node/process.

### 13.2. The Command

~~~javascript
use admin

db.runCommand({ rotateCertificates: 1 });
~~~

Or helper:

~~~javascript
db.rotateCertificates();
~~~

Requires the `rotateCertificates` privilege (included in `hostManager`). Never grant that role to an application writer.

### 13.3. Are Existing Connections Dropped?

Per the MongoDB Manual:

- Rotation **does not proactively terminate existing connections**.
- Existing TLS sessions may keep using the old certificate.
- New connections use the new certificate.
- Invalid new cert files cause rotation to fail without tearing down the currently active TLS config.

Therefore, checking through an old connection pool is **not enough**. Verify with a fresh TLS handshake.

### 13.4. This Command Does Not Automatically Run Cluster-Wide

Do not assume calling `db.rotateCertificates()` on one `mongos` rotates every `mongod` and `mongos` in a sharded cluster. Track each process against your inventory/rollout checklist.

### 13.5. Limitations

- A process handles only one rotation request at a time.
- Path and filename must remain unchanged.
- Encrypted PEM passphrases cannot be changed simultaneously via this simple command.
- Do not invoke on unsupported deployments/versions.
- Check version-specific docs for OS certificate store/selector behavior.

## 14. Leaf Certificate Renewal and CA Rollover

**Replacing a leaf certificate** signed by the same CA is usually simpler than **changing the CA**.

When the CA changes, an overlap phase is required:

~~~text
1. Clients trust CA-old only
2. Clients trust CA-old + CA-new
3. Servers switch to certs signed by CA-new
4. Verify every client has the new trust
5. Remove CA-old once safe
~~~

### 14.1. Why Overlap CAs?

If the server switches to a cert signed by `CA-new` while Java's truststore only knows `CA-old`, the TLS handshake fails before SCRAM auth can even run.

### 14.2. Inventory All Clients

- API pods.
- Batch jobs.
- ETL/backup tools.
- Monitoring agents.
- `mongosh`/Compass.
- Replica set internal links.
- `mongos` and config servers in sharded clusters.

### 14.3. CRL and OCSP

Certificate revocation may rely on CRL, OCSP, or other policies depending on client/server. Verify network reachability to revocation responders and failure behavior. Never assume issuing a new cert automatically invalidates the old cert.

### 14.4. If a Private Key Leaks

Renewing the certificate is **not enough**. Revoke the compromised cert per PKI policy, investigate blast radius, and replace the actual key material—not merely the expiration date.

## 15. X.509 Client Authentication and mTLS

One-way TLS lets the client authenticate the server; **mTLS** adds server verification of the client certificate.

~~~text
Client                            MongoDB
  |------ TLS ClientHello ---------->|
  |<----- Server certificate --------|
  |------ Client certificate ------->|
  |        Mutual authentication     |
  |<===== Encrypted traffic ========>|
~~~

MongoDB can use X.509 to authenticate database users without SCRAM passwords.

### 15.1. X.509 Users and $external on Self-Managed

X.509 users are typically identified by certificate subject DN and defined in the special `$external` database.

**Illustrative** example when X.509 is configured and certificate subjects are canonicalized properly:

~~~javascript
const externalDb = db.getSiblingDB("$external");

externalDb.runCommand({
  createUser: "CN=orders-service,OU=Apps,O=Example Corp,C=VN",
  roles: [
    { role: "readWrite", db: "appdata" }
  ]
});
~~~

The actual DN must match the certificate identity per MongoDB certificate-matching rules. This is not how Atlas users are managed.

### 15.2. Rotating Client X.509 Certificates

1. Issue a valid new cert/key.
2. Verify subject/issuer/EKU (`clientAuth`) and trust chain.
3. Ensure MongoDB trusts the new CA.
4. If the subject DN changes, prepare the new user/role mapping.
5. Distribute the private key via secrets manager or protected file mounts.
6. Open new client/TLS sessions and verify roles.
7. Switch all services.
8. Revoke the old cert and confirm no consumers still use it.

If the subject remains unchanged and trust policy matches, the existing principal mapping can stay; if the subject changes, update user mappings.

### 15.3. Atlas-Managed X.509

Atlas has its own X.509 issuance/renewal workflow. Use the Atlas UI/API per project policy instead of applying self-managed user commands.

## 16. Java Sync Driver: SCRAM Over TLS Without Embedding Passwords in URIs

Assume the service uses an application-provided `secretProvider` fetching secrets securely:

~~~java
import com.mongodb.MongoClientSettings;
import com.mongodb.MongoCredential;
import com.mongodb.ServerAddress;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

import java.util.List;

// secretProvider is an application abstraction.
char[] password = secretProvider.readPassword(
    "mongo/orders-api/prod"
);

MongoCredential credential =
    MongoCredential.createScramSha256Credential(
        "orders_svc_v2",
        "appdata",
        password
    );

MongoClientSettings settings =
    MongoClientSettings.builder()
        .applyToClusterSettings(builder ->
            builder.hosts(
                List.of(new ServerAddress("db1.example.test", 27017))
            )
        )
        .credential(credential)
        .applyToSslSettings(builder -> builder.enabled(true))
        .build();

MongoClient mongoClient = MongoClients.create(settings);
~~~

This is a condensed single-host example. Production replica sets/SRV deployments need proper topology, retry, timeout, and pooling settings. Never hardcode real hosts or passwords in tutorials.

### 16.1. Never Splice Raw Passwords into URIs

Special characters like `@`, `:`, `/`, `?`, and `#` in passwords must be percent-encoded in connection strings. Using `MongoCredential` avoids manual URI escaping.

### 16.2. Java TLS Truststore

The JDK can use the default truststore or a custom truststore containing CAs. Common system properties:

~~~text
javax.net.ssl.trustStore
javax.net.ssl.trustStorePassword
~~~

If the server certificate uses a private CA, the client must trust that CA securely.

### 16.3. mTLS Client Keystore

When using a client certificate, Java needs the private key/cert in a keystore or configured `SSLContext`:

~~~text
javax.net.ssl.keyStore
javax.net.ssl.keyStorePassword
~~~

Example attaching a pre-built and tested `SSLContext`:

~~~java
MongoClientSettings settings =
    MongoClientSettings.builder()
        .credential(MongoCredential.createMongoX509Credential())
        .applyToSslSettings(builder -> {
            builder.enabled(true);
            builder.context(sslContext);
        })
        .build();
~~~

`sslContext` is prepared by the application; it does not auto-generate certs or CAs. Never disable hostname verification on misconfiguration.

### 16.4. Credential Rotation and MongoClient

Updating a secret in a mounted file or secrets manager does not automatically re-authenticate a running `MongoClient` with the new secret. You may need to build a new `MongoClient`/`SSLContext`, drain traffic, and close the old pool.

## 17. Managing Cluster Membership Keyfiles

Replica set and sharded cluster members must authenticate one another. Self-managed deployments can use a shared **membership keyfile**.

~~~text
mongod-A ---- internal secret ---- mongod-B
   |
   +-------- internal secret ---- mongod-C
~~~

Example configuration:

~~~yaml
security:
  authorization: enabled
  keyFile: /etc/mongodb/keys/cluster-keyfile
~~~

This keyfile is **not** an app password and **not** the storage engine's `encryptionKeyFile`.

### 17.1. Multi-Key Keyfiles

MongoDB supports YAML keyfiles with one key or a sequence of keys. Two members authenticate if they share **at least one key**.

Keys must use MongoDB-supported characters/lengths, be randomly generated, and be distributed securely. On Unix, the file must not grant group/world permissions.

### 17.2. Two-Phase Rotation

**Phase A:** Nodes accept both old and new:

~~~yaml
- "OLD_KEY_FROM_SECURE_GENERATOR"
- "NEW_KEY_FROM_SECURE_GENERATOR"
~~~

These strings are **placeholders**, never production secrets.

Deploy the dual-key file, then rolling-restart one node at a time, secondaries first. Wait for each secondary to recover and sync after restarting. Step down the primary cleanly, then restart it.

**Phase B:** Once every node accepts old+new, switch to new only:

~~~yaml
- "NEW_KEY_FROM_SECURE_GENERATOR"
~~~

Perform a second rolling restart. Once complete, the old key can no longer authenticate membership.

### 17.3. Why Not Switch One Node Straight to New?

If node A has only `new` while B/C have only `old`, they share no key, causing internal authentication to fail and excluding the node from the replica set.

### 17.4. Never Restart the Whole Replica Set Simultaneously

Preserve quorum, elections, and replication health; check `rs.status()` and metrics before and after. Sharded clusters also include the config server replica set, shards, and `mongos`, requiring a full-topology runbook.

## 18. Membership Keyfile vs. At-Rest Encryption Keyfile

| Criterion | `security.keyFile` | `security.encryptionKeyFile` |
|---|---|---|
| Purpose | Internal authentication | Encryption-at-rest local key management |
| Used by | Replica/sharded members | Encrypted WiredTiger storage engine |
| Multi-key YAML | Yes | Does not use this workflow |
| Rotation | Overlap old/new + rolling restarts | No equivalent local key rotation |
| Risk of mistake | Members fail authentication | Data may become undecryptable |

The MongoDB Manual states **local key management** for encryption at rest does not support direct key rotation. If rotation is needed, use a key manager/KMIP workflow or node-replacement/re-encryption procedure per documentation.

**Never** overwrite `encryptionKeyFile` with a new random string like rotating an app password—that can render encrypted data unreadable.

## 19. X.509 Authentication Between Cluster Members

An alternative to membership keyfiles is X.509 internal authentication.

**Illustrative** configuration example:

~~~yaml
security:
  clusterAuthMode: x509

net:
  tls:
    mode: requireTLS
    certificateKeyFile: /etc/mongodb/tls/server.pem
    clusterFile: /etc/mongodb/tls/member.pem
    CAFile: /etc/mongodb/tls/trusted-ca.pem
~~~

Member certificates must satisfy matching CA, distinguished name, and EKU rules:

- `certificateKeyFile` acting as server certificate needs `serverAuth` when EKU is present.
- `clusterFile` for internal client authentication needs `clientAuth`.
- If one cert serves both server and client roles, EKU must include both per guidance.

When rotating, verify not only expiration dates, but also DN matching, `O`/`OU`/`DC` per MongoDB cluster membership rules, and trust chains across all members.

## 20. Master Keys / KMS / CMK and Data Encrypted at Rest

TLS protects data **in transit**. Encryption at rest protects data stored on disk.

MongoDB Atlas offers infrastructure-managed encryption at rest plus optional customer-managed keys depending on configuration. Self-managed MongoDB Enterprise encrypted storage engines can integrate with KMIP to manage master keys.

~~~text
MongoDB data files
      |
      v
Internal database keys
      |
      v
Master key (KMS/KMIP)
      |
      v
Key manager
~~~

### 20.1. Rotating a Master Key Differs from Rotating Passwords

Running `db.changeUserPassword` does not rotate the master encryption key. `rotateCertificates` does not re-encrypt data at rest either.

### 20.2. KMIP Master Key Rotation

MongoDB provides a Customer Master Key rotation workflow for supported Enterprise/KMIP environments. It can re-encrypt the internal keystore under a new CMK while keeping internal database keys intact, avoiding re-encrypting the entire dataset.

This is a storage-engine/replica-set admin workflow that may involve stepdowns and restarts. Follow exact version docs and rotate one member at a time to preserve write quorum.

### 20.3. Backups Depend on Older Keys

Earlier backups may require older master keys/DEKs to decrypt. Never delete old KMS keys immediately after the production cluster switches to a new key.

Always:

1. Inventory backups and snapshots.
2. Map key dependencies.
3. Verify decryption permissions.
4. Test recovery per policy.
5. Retire an old key only after every dependent backup copy is handled.

## 21. CSFLE / Queryable Encryption: DEKs and CMKs

MongoDB supports client-side field encryption on compatible deployments and drivers.

~~~text
Sensitive field
      |
      v
Data Encryption Key (DEK)
      |
      v
Encrypted DEK in Key Vault
      |
      v
Customer Master Key (CMK)
      |
      v
Cloud KMS / KMIP
~~~

**DEK rotation and CMK rotation are distinct operations.**

- **Rewrap DEK:** re-encrypts the data encryption key wrapped by the CMK using APIs such as `rewrapManyDataKey()` where supported.
- **Replacing the actual DEK:** may require re-encrypting ciphertext fields depending on design and encryption mode.

Never claim rotating a CMK automatically re-encrypted every ciphertext field from scratch.

### 21.1. Key Vault Permissions

Business applications should receive only the minimal permissions needed for encryption operations. Never let a single service credential both read/write business data and administer the entire KMS/Key Vault without justification.

## 22. Rotation Runbook: Prepare → Stage → Switch → Revoke

### Phase 1 — Prepare

1. Identify secret type, owner, and scope.
2. Inventory every consumer.
3. Verify Atlas vs. self-managed and server version.
4. Obtain change approval and check maintenance/SLO windows.
5. Verify backup/recovery if at-rest keys are involved.
6. Define health checks and alerting.
7. Prepare a rollback plan.
8. Review required privileges/ACLs.

### Phase 2 — Stage

1. Generate or issue the new secret/certificate via a trusted channel.
2. Validate metadata: roles, SAN, EKU, CA, expiry, dimensions/key format.
3. Store in secrets manager under a new version.
4. Grant read access to target consumers.
5. Set up old/new overlap if supported.
6. Canary a fresh connection.

### Phase 3 — Switch

1. Roll through app pod/node groups.
2. Open fresh TLS/SCRAM connections.
3. Verify permitted read/write operations.
4. Monitor auth failures, TLS errors, pool churn, and latency.
5. For replica sets, verify health/quorum after each step.
6. Wait for periodic/scheduled consumers to run and verify.

### Phase 4 — Revoke

1. Confirm all consumers have migrated.
2. Revoke the old user/cert/key via the proper mechanism.
3. Revoke stale secret version read access.
4. Verify the old credential is rejected via an approved test.
5. Update inventories and audit trails.
6. Schedule the next rotation deadline.

### 22.1. Never Revoke Before Switching If Uptime Matters

A syntactically valid new account missing collection read permissions can still pass `ping`. Canaries must verify real business queries before revoking the old principal.

### 22.2. Rollback When a Secret Was Compromised

If the old secret leaked, never roll back to it just to keep uptime. Follow incident-response policy: prioritize containment, restrict access/network paths, and switch to a safe replacement principal.

## 23. Monitoring and Auditing During Rotation

### 23.1. Metrics to Track

- `AuthenticationFailed` / error code 18.
- TLS handshake errors.
- Connection pool timeouts.
- API 5xx and p95/p99 latency.
- Count of app pods on the old version.
- Job failures.
- Replica set health/elections/replication lag.
- Certificate expiry.
- Rotation attempts/successes/failures.
- Unusual secret access.

### 23.2. Logs Can Hold Metadata, Never Secrets

Example audit record:

~~~json
{
  "event": "mongo-secret-rotation",
  "service": "orders-api",
  "principalVersion": "v2",
  "result": "success",
  "mechanism": "SCRAM-SHA-256"
}
~~~

Never log:

~~~text
plaintext password
MongoDB URI containing password
private key
full PEM certificate keyfile
KMS key material
secrets manager access token
~~~

### 23.3. Errors Appearing Days Later

A weekly scheduled job may not execute during the rollout window. Consumer inventories and confirming scheduled jobs matter far more than watching API traffic for a few minutes.

## 24. Incident Response When a Secret Leaks

When a connection URI hits public Git or a private key leaks:

1. Identify the leaked secret, leak location, and exposure window.
2. Restrict access, network reachability, and suspected compromised principals.
3. Generate a new secret via a secure channel.
4. Deploy clients with the new credential; revoke the old one urgently per severity.
5. Inspect logs/authentication/audits for anomalous access.
6. Check for exfiltration, backup exposure, and systems sharing the secret.
7. Revoke old certificates/keys per PKI/KMS policy.
8. Fix the leak source: CI logs, repositories, secret manager permissions.
9. Report/notify per security policy.
10. Run a post-mortem and improve automation.

**Changing the password alone is not enough** if the attacker can still read the new secret from CI or the secrets manager.

### 24.1. Private Key Exposure May Require PKI Revocation

If an old TLS private key leaked, issuing a new certificate does not automatically cause peers to reject the old one. Check revocation/trust and everywhere that cert was accepted.

### 24.2. Never Disable TLS Validation to Rescue a Broken Cert Deploy

`tlsInsecure` and `invalidHostNameAllowed` hide trust bugs while weakening security. Always fix the certificate/CA/hostname.

## 25. Low-Impact Verification Commands

### 25.1. Check Session Identity

~~~javascript
db.runCommand({
  connectionStatus: 1,
  showPrivileges: true
});
~~~

### 25.2. Basic Connectivity Check

~~~javascript
db.runCommand({ ping: 1 });
~~~

`ping` does not replace testing business permissions.

### 25.3. Check Replica Set Status

~~~javascript
rs.status();
~~~

Run before and after rolling restarts. Never invoke `stepDown` or `shutdown` just to “inspect” a replica set.

### 25.4. Check Certificate Validity

~~~bash
openssl x509 \
  -in /etc/mongodb/tls/server.pem \
  -noout -dates -subject -issuer -ext subjectAltName
~~~

Never paste private keys into public websites to check them.

## 26. Common Mistakes

| Misconception | Consequence | Right Approach |
|---|---|---|
| Changing Atlas users via `db.changeUserPassword` | Unsupported management path | Atlas UI/CLI/Admin API |
| SCRAM needs no TLS | Exposes data during management commands | Enable TLS |
| Changing password won't affect apps | New auth fails | Dual-account/canary |
| Updating Secrets Manager updates pods automatically | Processes haven't reloaded | Build new `MongoClient`/rolling rollout |
| One credential for every service | Huge blast radius | Per-service principal |
| Giving apps `root` | Excessive privileges | Least privilege |
| Unencoded password in URI | Auth fails | Percent-encode or `MongoCredential` |
| Replacing cert switches open connections immediately | Existing TLS sessions keep old cert | Test new connection |
| One `rotateCertificates` updates whole cluster | Other nodes unchanged | Run per process |
| Changing encrypted PEM passphrase in online rotate | Violates prerequisites | Separate runbook/restart |
| Swapping CA before updating client trust | TLS handshake fails | Overlap CA |
| Issuing a new cert revokes the old one | Old cert may remain valid | PKI revocation |
| Using `tlsInsecure` to fix errors | Loses hostname/CA verification | Fix SAN/trust |
| Membership keyfile equals `encryptionKeyFile` | Risk of unreadable data | Distinguish functions |
| Switching keyfile straight on one node | No shared key left | Overlap old+new |
| Restarting all members simultaneously | Quorum lost | Rolling restart |
| Rotating CMK equals rotating SCRAM | Confuses security layers | KMS workflow |
| Deleting old keys once prod moves on | Backups may become undecryptable | Key dependency inventory |
| Testing `ping` is enough | Missing roles go unnoticed | Test real use cases |
| Ignoring scheduled jobs | Failures appear days later | Consumer inventory |
| Logging full URI/private key | Secret exposure | Redaction |
| Rolling back to leaked secret | Ongoing compromise | Incident process |

## 27. Exercises and Practice Scenarios

Never run DDL or user rotation exercises on production. Self-managed exercises require an appropriate lab replica set or standalone instance with authorized access.

### Exercise 1 — Classify Secrets

Do SCRAM passwords, server TLS private keys, client X.509 keys, membership keyfiles, and KMS CMKs serve the same purpose? Build a comparison table.

### Exercise 2 — Authentication and Authorization

An app rotated its password yet still holds the `root` role. What problem remains unaddressed?

### Exercise 3 — Create a SCRAM User

Create `lab_reporter_v1` in database `appdata` with role `read` and `passwordPrompt()`.

### Exercise 4 — Wrong authSource

The user lives in `appdata` while the client sets `authSource=admin`. Explain what error can occur.

### Exercise 5 — Direct Rotation

Change `lab_reporter_v1`'s password in a self-managed lab. Why can new pooled connections fail before the app picks up the new secret?

### Exercise 6 — Dual Account

Write the steps to create `lab_reporter_v2`, canary, roll out, and revoke `v1`. During which phase do both accounts coexist?

### Exercise 7 — Conditional Rollback

`v2` lacks a permission at 10% rollout, and `v1` has not leaked. How do you safely restore traffic?

### Exercise 8 — Atlas Database Users

Where do you change a database password in Atlas? Why not run `db.changeUserPassword` directly?

### Exercise 9 — URI Passwords

A password contains `@` and `#`. Why must they be percent-encoded if placed in a MongoDB URI?

### Exercise 10 — TLS and SCRAM

The TLS handshake succeeds, yet authentication fails. What does each layer verify?

### Exercise 11 — SAN Mismatch

The client connects to `db1.example.test`, while the cert SAN only lists `db2.example.test`. Should you disable hostname verification?

### Exercise 12 — Expiring Certificates

Design 30/14/7-day pre-expiry alerts; what owners and escalation paths are needed?

### Exercise 13 — rotateCertificates

Which MongoDB version introduced online certificate rotation? What are the constraints on file path/filename and encrypted key passphrases?

### Exercise 14 — New Connections

Why must you test a new TLS connection after `rotateCertificates`?

### Exercise 15 — CA Rollover

Order these steps: clients trust old+new CA; servers switch certs; remove old CA. Why does ordering matter?

### Exercise 16 — X.509 Users

Which database holds X.509 users? How does the subject DN affect principal mapping?

### Exercise 17 — Java TLS

Explain the difference between a Java truststore and keystore.

### Exercise 18 — Java Client Reload

After certificate files update, should you keep using the old `MongoClient` indefinitely? Propose how to transition the client pool.

### Exercise 19 — Internal Keyfile

Why can a keyfile hold old and new keys simultaneously? What condition lets members authenticate each other?

### Exercise 20 — Rolling Restart

In a 3-node replica set, why rotate secondaries before the primary? Which health checks follow each step?

### Exercise 21 — Distinguishing Keyfiles

How do `security.keyFile` and `security.encryptionKeyFile` differ in purpose and rotation capability?

### Exercise 22 — Internal X.509

When EKU is present, why do internal member certs need `clientAuth` and server certs need `serverAuth`?

### Exercise 23 — KMS Master Key

Does changing a database user's password rotate the CMK? Why or why not?

### Exercise 24 — Backups

If an old KMS key is deleted, what can happen to earlier encrypted backups?

### Exercise 25 — DEK vs. CMK

Is rewrapping a DEK the same as re-encrypting every encrypted field with a new DEK?

### Exercise 26 — Secrets Manager

Design metadata tracking secret owner, consumers, version, and rotation deadline. Which fields must never appear in the table?

### Exercise 27 — Kubernetes Secrets

When a Secret object updates yet the app only reads environment variables at startup, why might the app not pick up the new secret?

### Exercise 28 — Incident

A MongoDB URI containing a password was committed to a public repository. Draft a runbook for containment, credential replacement, revocation, auditing, and fixing the leak source.

### Exercise 29 — Debugging Authentication

After rotation, `AuthenticationFailed` hits 20% of requests. List checks covering `v1`/`v2` secrets, `authSource`, driver pools, and roles.

### Exercise 30 — Capstone

Build rotation plans for: an Atlas SCRAM user, self-managed membership keyfile, server TLS cert, Java client X.509 cert, and KMS master key. For each, specify owner, staging, switch timing, verification, rollback, and revocation.

## 28. Production Checklist

### Passwords and Users

- [ ] Application users hold least-privilege roles.
- [ ] Each service/environment has its own principal.
- [ ] Passwords are randomly generated and stored in a secrets manager.
- [ ] No plaintext credentials appear in Git/logs/tickets.
- [ ] `authSource` and `authMechanism` are accurate.
- [ ] SCRAM management commands run over TLS.
- [ ] Atlas user management uses supported Atlas tools.
- [ ] Dual-account rotation used where overlap is needed.
- [ ] Consumer inventory is complete.
- [ ] Canary tests real functionality.
- [ ] `v1` is revoked after verification.

### TLS/X.509

- [ ] SANs match real hostnames.
- [ ] CA chain and validity are verified.
- [ ] EKU `serverAuth`/`clientAuth` are appropriate.
- [ ] Private key permissions are locked down.
- [ ] `tlsInsecure`/`tlsAllowInvalidHostnames` are never enabled.
- [ ] Expiry alerts are configured.
- [ ] `rotateCertificates` version/path/passphrase constraints are checked.
- [ ] New TLS connections have been verified.
- [ ] Old/new CA trust overlap is planned.
- [ ] Old certificate revocation procedures exist.
- [ ] Java truststore/keystore/`SSLContext` are updated.

### Internal Security and Encryption

- [ ] Membership keyfile is kept distinct from at-rest `encryptionKeyFile`.
- [ ] Keyfile rotation uses old+new overlap.
- [ ] Rolling restarts preserve replica-set quorum.
- [ ] Internal X.509 DN/CA/EKU are verified.
- [ ] KMS/CMK rotation has an edition-specific runbook.
- [ ] Backups exist and restores are tested.
- [ ] Old keys are retained while dependent backups exist.
- [ ] DEK rewrap is clearly distinguished from re-encrypting data.

### Operations

- [ ] Owners, deadlines, versions, and consumers are documented.
- [ ] Secrets Manager has auditing and least privilege.
- [ ] Auth error, TLS failure, and pool churn metrics exist.
- [ ] Rollback and incident response plans are ready.
- [ ] Rotation logs contain no secrets.
- [ ] Scheduled jobs are verified.
- [ ] Two rotation jobs cannot concurrently edit the same secret.
- [ ] Production changes carry approval.
- [ ] Revocation timestamp and next rotation are recorded.
- [ ] Tested in staging.

## 29. Summary

In MongoDB, **passwords, certificates, and encryption keys** are all sensitive secrets, yet each serves a distinct layer:

- **SCRAM passwords** authenticate database users. Self-managed supports `db.changeUserPassword`; Atlas uses the Atlas management plane. When downtime cannot be tolerated, use two principals during a transition window.
- **TLS certificates/private keys** protect transit and server/client identity. Verify SAN/CA/EKU and expiry, and use `rotateCertificates` on supported deployments under its specific prerequisites.
- **X.509/mTLS** authenticates clients or cluster members via certificates; rotations require managing trust chains and identity mappings.
- **Internal membership keyfiles** rotate via old+new overlap and rolling restarts, whereas **at-rest encryption keyfiles do not use that workflow**.
- **KMS/CMK/DEKs** have dedicated rotation procedures and must preserve historical data recoverability.
- **Secrets Managers** only distribute credentials; apps still need connection pool reloads/recreation, canaries, monitoring, and revocation.

A reliable pattern for every rotation is: **inventory → issue new → controlled rollout → verify → revoke old → audit**. When a secret is compromised, secure revocation and fixing the leak source take priority over keeping rollback to the old secret.

## Official References

- [MongoDB Manual — db.changeUserPassword](https://www.mongodb.com/docs/manual/reference/method/db.changeuserpassword/)
- [MongoDB Manual — db.createUser](https://www.mongodb.com/docs/manual/reference/method/db.createuser/)
- [MongoDB Manual — db.updateUser](https://www.mongodb.com/docs/manual/reference/method/db.updateuser/)
- [MongoDB Atlas — Configure Database Users](https://www.mongodb.com/docs/atlas/security-add-mongodb-users/)
- [MongoDB Manual — TLS/SSL Transport Encryption](https://www.mongodb.com/docs/manual/core/security-transport-encryption/)
- [MongoDB Manual — Configure TLS](https://www.mongodb.com/docs/manual/tutorial/configure-ssl/)
- [MongoDB Manual — rotateCertificates](https://www.mongodb.com/docs/manual/reference/command/rotatecertificates/)
- [MongoDB Manual — Internal/Membership Authentication](https://www.mongodb.com/docs/manual/core/security-internal-authentication/)
- [MongoDB Manual — Rotate Replica Set Keys](https://www.mongodb.com/docs/manual/tutorial/rotate-key-replica-set/)
- [MongoDB Manual — Deploy Replica Set with Keyfile](https://www.mongodb.com/docs/manual/tutorial/deploy-replica-set-with-keyfile-access-control/)
- [MongoDB Manual — Rotate Encryption Key](https://www.mongodb.com/docs/manual/tutorial/rotate-encryption-key/)
- [MongoDB Manual — Configure Encryption](https://www.mongodb.com/docs/manual/tutorial/configure-encryption/)
- [MongoDB Atlas — Workload Identity Federation](https://www.mongodb.com/docs/atlas/workload-oidc/)
- [MongoDB Java Sync Driver — SCRAM](https://www.mongodb.com/docs/drivers/java/sync/current/security/auth/scram/)
- [MongoDB Java Sync Driver — X.509](https://www.mongodb.com/docs/drivers/java/sync/current/security/auth/x509/)
- [MongoDB Java Sync Driver — TLS](https://www.mongodb.com/docs/drivers/java/sync/current/security/tls/)
- [MongoDB Java Sync Driver — In-Use Encryption](https://www.mongodb.com/docs/drivers/java/sync/current/security/encrypt-fields/)
