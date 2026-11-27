# SCRAM Authentication, Authentication Database, and Certificate Mechanisms in MongoDB

> **Module:** Database Engine Document MongoDB  
> **Chapter:** Security

## 1. The Problem: Why Can You Connect to MongoDB Yet Still Fail to Log In?

Suppose an e-commerce system has MongoDB at `mongo1.example.internal:27017` and application data resides in the `commerce` database. The engineering team receives these requirements:

- The Java application must log in with a username and password.
- The `app_reader` user may only read collections in `commerce`.
- Admin accounts are created in the `admin` database, yet still need to operate on `commerce`.
- Connections must be encrypted and verify the server using a TLS certificate.
- An internal CDC service must use a **client certificate** instead of a password.
- The replica set may use separate certificates for **member-to-member authentication**, not just for applications.
- Passwords or private keys must never be stored directly in source code.

A common issue is that engineers have a connection string but do not clearly distinguish:

1. **Authentication mechanism**: how does the client prove its identity? SCRAM or X.509?
2. **Authentication database**: which database does the server look up user credentials in? `admin`, `commerce`, or `$external`?
3. **Authorization**: after logging in, which commands is the user permitted to run, and on which databases/collections?
4. **Transport security**: how does TLS encrypt traffic and verify server/client certificates?

These four aspects are related, but **they do not replace one another**.

Example:

```text
Client ──(TCP/TLS)──> MongoDB server
          │
          ├── TLS: encryption + server certificate verification
          │
          ├── Authentication:
          │     SCRAM → username/password + authSource
          │     X.509 → client certificate + $external
          │
          └── Authorization:
                readWrite/read/user-defined roles
                determine permitted operations
```

A connection can:

- **Be rejected at TLS** because the hostname does not match the certificate.
- **Pass TLS but fail authentication** because `authSource` is wrong.
- **Pass authentication yet receive Unauthorized** because a role is missing.
- **Authenticate via SCRAM without TLS**, leaving data and traffic exposed in transit.

**Lesson objectives:** accurately understand SCRAM, how to choose an authentication database, configure TLS and MONGODB-X509, distinguish user certificates from server certificates and cluster member authentication, implement safely in `mongosh` and the Java Sync Driver, and diagnose common failures.

---

## 2. How Are Authentication, Authorization, and TLS Different?

### 2.1. Authentication: Who Are You?

The client presents proof of identity for the server to verify. In MongoDB, two key cases are:

- **SCRAM**: username and password, via a challenge-response protocol using salts and derived keys.
- **MONGODB-X509**: the client presents an X.509 certificate trusted by the system, and the server validates and maps the certificate identity to a MongoDB user.

Other mechanisms may exist depending on edition/deployment and enterprise identity integration, but this lesson focuses on SCRAM and X.509.

### 2.2. Authorization: What Are You Allowed to Do?

After successful authentication, MongoDB checks permissions from roles.

Example:

```javascript
{
  user: "app_reader",
  roles: [
    { role: "read", db: "commerce" }
  ]
}
```

This user has read privileges matching the role on the `commerce` database; it does not automatically get `readWrite` or administrative privileges on other databases.

A user can be stored in the `admin` database while being granted roles on `commerce`. **Where a user is stored is not its sole permission scope.**

### 2.3. TLS: How Is the Connection Protected?

TLS solves a different problem:

- Encrypts traffic over the network.
- Lets the client verify the server is the intended endpoint via certificate/CA/hostname checks.
- When mutual TLS is configured, allows the server to require and verify a client certificate.

TLS server authentication **does not by default** mean the MongoDB user logged in with X.509. A TLS connection can still use SCRAM to authenticate the user.

### 2.4. Comparison Table

| Question | Responsible Component |
|---|---|
| Which authentication algorithm does the password use? | SCRAM-SHA-256 or SCRAM-SHA-1 |
| Where does the server look up `app_reader`? | Authentication database, e.g., `commerce` |
| Why did login succeed yet insert was denied? | Authorization/roles |
| Why does the server certificate not match the hostname? | TLS certificate verification |
| Why can't the X.509 client log in? | Client certificate, CA trust, DN mapping, `$external`, roles |
| Why is `authSource=admin` different from `authSource=commerce`? | Users are database-scoped identities |
| How do cluster members authenticate each other? | Internal member authentication, e.g., keyfile or X.509 |
| Does TLS automatically replace SCRAM with X.509? | **No** |

---

## 3. What Is SCRAM?

**SCRAM** stands for *Salted Challenge Response Authentication Mechanism*.

MongoDB supports mechanisms such as:

- `SCRAM-SHA-256`.
- `SCRAM-SHA-1`.

**Prefer SCRAM-SHA-256** for new deployments when supported by driver and server; SCRAM-SHA-1 primarily exists for legacy compatibility.

### 3.1. The Challenge-Response Idea

In a simplified flow:

1. The client provides the user identity.
2. The server and client exchange nonces/challenges, salt, and required parameters.
3. The client computes a proof using a key derived from the password; it does not send the password as a plain plaintext field during the SCRAM exchange.
4. The server verifies the proof against stored credentials.
5. The client can also verify the server proof per the protocol.

```text
Java / mongosh                              MongoDB server
     │                                          │
     │ user + client nonce                       │
     ├─────────────────────────────────────────>│
     │                server nonce + salt        │
     │<─────────────────────────────────────────┤
     │ client proof                              │
     ├─────────────────────────────────────────>│
     │                server proof / outcome     │
     │<─────────────────────────────────────────┤
     │                                          │
     └──── authenticated identity + role checks ┘
```

This is a conceptual diagram, not an exact field-by-field breakdown of each SCRAM packet.

### 3.2. Is the Password Sent Directly Over the Network?

SCRAM uses proofs and challenge-response to avoid sending plaintext passwords as raw strings during authentication.

**However, this does not replace TLS.** Application traffic, query payloads/results, and other metadata still need TLS protection. Never run MongoDB with sensitive data over an unencrypted network simply because SCRAM is enabled.

### 3.3. Salt, Iterations, and Credential Storage

SCRAM uses key derivation bound to a salt and iteration count to support password verification. MongoDB does not need to store plaintext passwords to verify a valid proof.

Specific parameters and credential records are managed by MongoDB; never edit user credentials directly inside system collections.

**Never implement SCRAM yourself in application code**: let the MongoDB driver handle the handshake and let the server manage credential mechanisms and policies.

### 3.4. SHA-256 vs. SHA-1

| Criterion | SCRAM-SHA-256 | SCRAM-SHA-1 |
|---|---|---|
| Underlying hash | SHA-256 | SHA-1 |
| Choice for new systems | Usually preferred | Only for compatibility |
| Requires server/driver support | Yes | Yes |
| Replaces TLS? | No | No |
| Requires authentication database? | Yes | Yes |
| Uses username/password? | Yes | Yes |

MongoDB has negotiation/default rules depending on version and how users were created. To enforce a specific mechanism, specify `authMechanism=SCRAM-SHA-256` in the URI or the corresponding `MongoCredential`.

Do not assume “simply setting SCRAM-SHA-256 lets old accounts log in”; the user's stored credentials must support the requested mechanism.

### 3.5. SASLprep and Password Semantics

SCRAM-SHA-256 defines password normalization rules under its supported specification. Do not manually trim, lowercase, or Unicode-normalize passwords in application code before passing them to the driver.

A password is an **intact secret governed by server/driver rules**, not a username or search key.

---

## 4. Authentication Database: The Most Frequently Confused Concept

In MongoDB, a username is scoped to an **authentication database**. Two users:

```text
admin.app_service
commerce.app_service
```

are not inherently the same identity, even with identical usernames.

If you create:

```javascript
use admin

db.createUser({
  user: "app_service",
  pwd: passwordPrompt(),
  roles: [
    { role: "readWrite", db: "commerce" }
  ]
});
```

then `app_service`'s credentials live in the **`admin` authentication database**, even though its role grants permissions on `commerce`.

To log in as this exact user from a Java app:

```text
mongodb://app_service:<PASSWORD>@mongo1.example.internal:27017/commerce?authSource=admin
```

In this URL:

- `app_service` is the username.
- `/commerce` is the **default database** used as the connection context.
- `authSource=admin` is the database the server checks for `app_service`'s credentials.

**The two databases serve two different purposes.**

### 4.1. Auth Source Is Not the Only Accessible Database

An account authenticating in `admin` can be granted roles on `commerce`:

```javascript
{
  user: "app_service",
  roles: [
    { role: "readWrite", db: "commerce" }
  ]
}
```

After login:

- The user can perform operations allowed by `readWrite` on `commerce`.
- The user does not automatically gain admin or root privileges merely because its authentication database is `admin`.
- Querying another database without granted roles may return `Unauthorized`.

### 4.2. User Stored in the Application Database Itself

You can create the user in `commerce`:

```javascript
use commerce

db.createUser({
  user: "app_service",
  pwd: passwordPrompt(),
  roles: [
    { role: "readWrite", db: "commerce" }
  ]
});
```

Then:

```text
mongodb://app_service:<PASSWORD>@mongo1.example.internal:27017/commerce?authSource=commerce
```

or an equivalent URI following default auth database rules.

Placing users in `admin` versus the application database is an identity/role governance decision, not an automatic privilege level.

### 4.3. Default Value of authSource in Standard URIs

For standard URIs and username/password mechanisms:

- If `authSource` is specified, the driver uses that database.
- If `authSource` is omitted but the URI includes a database path component, that database typically becomes the default authentication database.
- If both are absent, the default is typically `admin`.

Examples:

| Connection String | Authentication Database Used |
|---|---|
| `mongodb://u:p@host/commerce?authSource=admin` | `admin` |
| `mongodb://u:p@host/commerce` | `commerce` |
| `mongodb://u:p@host/?authSource=commerce` | `commerce` |
| `mongodb://u:p@host/` | `admin` |
| `mongodb://u:p@host/commerce?authSource=commerce` | `commerce` |

This table reflects standard URI rules for common SCRAM setups. With `mongodb+srv`, DNS TXT options, or managed providers, check the effective URI configuration before assuming defaults.

### 4.4. Why Does Login Fail with the Right Password?

Suppose `app_service` was created in `admin`.

Wrong URI:

```text
mongodb://app_service:<PASSWORD>@host:27017/commerce
```

The driver may look up credentials in `commerce`, fail to find the matching user/password, and fail authentication.

Correct URI:

```text
mongodb://app_service:<PASSWORD>@host:27017/commerce?authSource=admin
```

**The fix is setting `authSource` to match where the user was created**, not granting `root` or creating duplicate users just to “try it out”.

### 4.5. authSource Differs from the Database Selected After Connecting

In `mongosh`:

```javascript
use commerce
db.orders.findOne()
```

`use commerce` switches the shell's database context; it **does not change the authenticated identity established at connection time**.

A session authenticated as `admin.app_service` remains that same user when switching to `commerce` or `reports`.

---

## 5. Preparing a Safe SCRAM Lab

These examples are intended for a MongoDB Server you administer or a local test instance where you have permission to configure security.

**Never put real passwords into repositories, tickets, shell history, or screenshots.** Use `mongosh`'s `passwordPrompt()` or a secret manager. Never create users or alter authorization in production without a runbook and verified admin access recovery.

### 5.1. Create an Admin User for the Lab

Assume the lab MongoDB instance does not yet have authentication enabled or was freshly initialized with no users, and the admin connects via an authorized channel to bootstrap users.

```javascript
use admin

db.createUser({
  user: "lab_user_admin",
  pwd: passwordPrompt(),
  roles: [
    { role: "userAdminAnyDatabase", db: "admin" }
  ]
});
```

The `userAdminAnyDatabase` role grants user management across multiple databases, so use it only for protected admin accounts; **never assign it to application services**.

In production, prefer admin accounts and roles provisioned under least-privilege policies with auditing and rotation.

### 5.2. Enable Authorization

An example `mongod.conf` snippet in the lab:

```yaml
security:
  authorization: enabled
```

Editing config files and restarting MongoDB require host privileges and can disrupt active connections. Perform this only in a controlled lab environment.

If running multi-node replica sets or sharded clusters, design **internal member authentication** and proper startup sequencing; do not enable authorization arbitrarily on one node and consider the cluster securely configured.

### 5.3. Localhost Exception

MongoDB provides a **localhost exception** during bootstrapping when access control is enabled and no users/roles exist yet, allowing the first user to be created from localhost under supported conditions.

Key points:

- It is a limited bootstrapping exception, **not a regular admin login mechanism**.
- Once an appropriate user is created, the exception no longer allows arbitrary unauthenticated logins.
- It can be disabled via configuration; exact behavior depends on deployment/version.
- Never open public networking to “use the localhost exception”.
- Never rely on the localhost exception to recover production when credentials are lost; maintain a dedicated runbook.

### 5.4. Log In as the Admin User

In the shell (illustrative command-line syntax):

```bash
mongosh "mongodb://127.0.0.1:27017/admin" --username lab_user_admin --authenticationDatabase admin --password
```

Depending on the shell version, `--password` without a value opens an interactive password prompt. Never pass passwords directly on the command line, as they can leak via shell history or process listings.

### 5.5. Create Application Users in the commerce Database

Once the admin is authenticated:

```javascript
const commerce = db.getSiblingDB("commerce");

commerce.createUser({
  user: "app_reader",
  pwd: passwordPrompt(),
  roles: [
    { role: "read", db: "commerce" }
  ]
});

commerce.createUser({
  user: "app_writer",
  pwd: passwordPrompt(),
  roles: [
    { role: "readWrite", db: "commerce" }
  ]
});
```

Both users are stored in the **`commerce` authentication database**.

### 5.6. Test Connecting with the Correct authSource

```bash
mongosh "mongodb://127.0.0.1:27017/commerce?authSource=commerce&authMechanism=SCRAM-SHA-256" --username app_reader --password
```

Inside the shell:

```javascript
db.runCommand({ connectionStatus: 1 });
db.getName();
db.getCollectionNames();
```

`connectionStatus` shows authenticated users and roles for the session; returned roles/privileges depend on permissions and command options.

**Check:** `db.getName()` returning `commerce` only tells you the current database context. To see the authenticated user, inspect `connectionStatus`; do not infer `authSource` from `db.getName()`.

### 5.7. Verify Least Privilege

As `app_reader`:

```javascript
db.orders.findOne();
```

Read queries are allowed within the role's limits. However:

```javascript
db.orders.insertOne({
  _id: "lab-order-1",
  status: "NEW"
});
```

must be rejected if the user only holds the `read` role with no additional write privileges.

This demonstrates an **authorization failure** after authentication succeeded.

### 5.8. Which SCRAM Mechanisms Can Newly Created Users Use?

Depending on server version, user create/update options, and stored credential mechanisms, MongoDB can store credentials for different SCRAM mechanisms.

When an application requires `SCRAM-SHA-256`, ensure the account was created to support it. In supported environments, you can specify mechanisms at creation time:

```javascript
db.getSiblingDB("commerce").createUser({
  user: "sha256_service",
  pwd: passwordPrompt(),
  mechanisms: ["SCRAM-SHA-256"],
  roles: [
    { role: "read", db: "commerce" }
  ]
});
```

In supported MongoDB versions, the server stores credentials matching the specified mechanism.

If an older account lacks credentials for that mechanism, simply adding `authMechanism=SCRAM-SHA-256` to the connection string can cause login errors.

---

## 6. Connecting with SCRAM via mongosh and Connection Strings

### 6.1. Full URI

```text
mongodb://USERNAME:PASSWORD@HOST:27017/DEFAULT_DB?authSource=AUTH_DB&authMechanism=SCRAM-SHA-256
```

Illustrative example with the user created in `commerce`:

```text
mongodb://app_reader:<PASSWORD>@mongo1.example.internal:27017/commerce?authSource=commerce&authMechanism=SCRAM-SHA-256
```

**Never use `<PASSWORD>` as a literal secret**; it is only a placeholder.

If you use a URI containing a real username/password, the password must be percent-encoded per URI syntax rules. In exercises, enter passwords via prompt instead of embedding them in URIs.

### 6.2. Passwords with Special Characters

In a URI, characters such as:

- `@`
- `:`
- `/`
- `?`
- `#`
- `[`
- `]`
- `%`

can break URI parsing if not properly percent-encoded.

Conceptual example:

```text
Original password: S3cr@t/Value
URL-safe form:     S3cr%40t%2FValue
```

Do not write your own incomplete character-replacement encoder. Use your language's URI-encoding API or the MongoDB driver's credentials API, and read secrets from a secure channel.

### 6.3. SCRAM Over a TLS Connection

Conventional secure URI example:

```text
mongodb://app_reader:<PASSWORD>@mongo1.example.internal:27017/commerce?authSource=commerce&authMechanism=SCRAM-SHA-256&tls=true
```

TLS handles encryption and server verification; SCRAM authenticates the user.

If the server's CA is not in the client's trust store, configure CA trust properly. **Never enable `tlsInsecure` or `tlsAllowInvalidCertificates` in production to bypass certificate errors.**

### 6.4. SRV URI

Managed deployments may provide:

```text
mongodb+srv://USERNAME:PASSWORD@cluster.example.mongodb.net/commerce?authSource=admin
```

Drivers resolve DNS SRV/TXT records per the driver specification. Do not manually rewrite a `mongodb+srv` hostname into a single-node host or strip provider-required options.

Always verify the **actual `authSource`**, especially when the user was created in `admin` while the application DB is `commerce`.

---

## 7. User Administration Privileges and User Lifecycle

### 7.1. Viewing Users in an Authentication Database

With an appropriately privileged account:

```javascript
use commerce

db.getUsers();
db.getUser("app_reader");
```

`getUsers()` in the current database does not list every user across the entire cluster.

To inspect `admin.app_service`, switch to `admin` or query the corresponding namespace if permitted.

### 7.2. Creating a User in admin with Roles on commerce

```javascript
use admin

db.createUser({
  user: "commerce_service",
  pwd: passwordPrompt(),
  roles: [
    { role: "readWrite", db: "commerce" }
  ]
});
```

Then:

```text
authSource = admin
granted role db = commerce
default database in URI can = commerce
```

Some organizations centralize application users in `admin` for management; others place users in each application database. Choose based on policy and operations, and **never equate the `admin` user database with `root` privileges**.

### 7.3. Changing Passwords

In the user's authentication database, with appropriate privileges:

```javascript
use commerce

db.changeUserPassword(
  "app_reader",
  passwordPrompt()
);
```

Notes:

- Password changes affect new authentication attempts.
- Deployment paths/connection pools may keep existing authenticated connections alive for a time depending on driver and deployment.
- Rotation requires a plan to avoid disruption, especially if multiple services share an account (avoid sharing users).
- Never log the new password.

### 7.4. Updating Roles

```javascript
use commerce

db.updateUser("app_reader", {
  roles: [
    { role: "read", db: "commerce" }
  ]
});
```

In production, assess the impact on running queries and follow your organization's change-management process for privilege updates.

### 7.5. Why Never Edit system.users Directly?

MongoDB manages credentials, roles, and user metadata through administrative commands. **Never update internal collections directly to change passwords or roles**; use `createUser`, `updateUser`, `changeUserPassword`, and `dropUser` per your permissions and runbooks.

---

## 8. TLS Certificates and X.509: Two Roles That Must Not Be Confused

**X.509** is a public key certificate standard. In MongoDB, certificates appear in at least two contexts:

1. **TLS transport**: the client verifies the server certificate; mutual TLS may also use a client certificate.
2. **MONGODB-X509 authentication**: MongoDB maps an identity from the client certificate to a user with roles, replacing SCRAM username/password login.

These are two distinct contexts even though both use certificates.

### 8.1. One-Way TLS

```text
Client                            MongoDB server
  │                                     │
  │──────── TLS handshake ─────────────>│
  │<──────── Server certificate ────────│
  │                                     │
  │ Verify CA + hostname + dates        │
  │ Establish encrypted channel         │
  │                                     │
  │──── SCRAM username/password proof ─>│
  │<──── Authentication result ─────────│
```

In this case:

- The server presents a certificate.
- The client verifies the certificate.
- The client **does not need to send a client certificate** if the server allows TLS connections without one.
- The MongoDB user still authenticates with SCRAM.
- Authorization still checks roles.

### 8.2. Mutual TLS + MONGODB-X509

```text
Client                            MongoDB server
  │                                     │
  │──────── TLS handshake ─────────────>│
  │<──────── Server certificate ────────│
  │──────── Client certificate ────────>│
  │                                     │
  │ Client validates server             │
  │ Server validates client             │
  │                                     │
  │──── MONGODB-X509 authentication ────>│
  │ Server maps certificate DN to user  │
  │ in $external and checks roles       │
  │<──── Authentication result ─────────│
```

With mutual TLS, server and client verify each other's certificates. However, **having a TLS client certificate does not automatically create a MongoDB application user**; authenticating via MONGODB-X509 requires configuring the mechanism and user mapping.

### 8.3. Comparison Table

| Component | TLS Server Cert | TLS Client Cert | MongoDB X.509 User |
|---|---|---|---|
| Subject | Server | Application/client | MongoDB principal |
| Purpose | Verify server endpoint | Verify client identity at TLS | Grant roles/authorization |
| Stored where? | Server PEM/key | Client PEM/key or key store | User in `$external` |
| Has MongoDB password? | Not applicable | Not applicable | No SCRAM password required |
| Involves CA trust? | Yes | Yes | Yes, via TLS/client cert trust |
| Automatically grants readWrite? | No | No | Only if the user is assigned roles |

### 8.4. CA Certificates and Leaf Certificates

In a typical PKI:

- **CA certificate**: the issuer certificate trusted by clients/servers.
- **Server certificate**: the leaf cert used to verify the MongoDB endpoint.
- **Client certificate**: the leaf cert representing the client in mutual TLS.
- **Private key**: belongs to the certificate holder and must remain secret.

Never put private keys into repositories or send them over unapproved chat/email. A server cert is not a “shared password” for every client.

---

## 9. Verifying the Server Certificate with TLS

A TLS client should verify:

1. The certificate chain is validly signed by a trusted CA.
2. The certificate is within its validity period.
3. The connected DNS name/IP matches the server identity in the certificate, typically via **Subject Alternative Name (SAN)**.
4. Key usage/extended key usage are appropriate.
5. The certificate is not revoked under configured revocation checks, if any.
6. The corresponding server private key remains secret.

### 9.1. SAN and Hostname Mismatch

Suppose the server certificate contains:

```text
DNS:mongo1.example.internal
DNS:mongo1
```

A client connecting to:

```text
mongodb://mongo1.example.internal:27017/?tls=true
```

can match the DNS name when the CA and other checks are valid.

However, connecting directly via:

```text
mongodb://192.0.2.10:27017/?tls=true
```

can fail hostname verification if the certificate does not include the corresponding IP SAN.

**Fix:** use a hostname matching the certificate or reissue the certificate with the proper SAN; never disable hostname verification in production.

### 9.2. Inspecting PEM Files with openssl

Example for administrators in an authorized environment:

```bash
openssl x509 -in server.pem -noout -subject -issuer -dates -ext subjectAltName
```

Even if `server.pem` contains a private key, this command only prints certificate metadata, not the private key. Still, the PEM file remains a system secret and must have restricted permissions.

You can verify the certificate chain against a suitable CA file:

```bash
openssl verify -CAfile root-ca.pem server-cert.pem
```

Certificate inspection commands do not replace testing actual connectivity and TLS negotiation from your driver.

### 9.3. Server Configuration with TLS

Conceptual `mongod.conf` example:

```yaml
net:
  bindIp: "127.0.0.1,mongo1.example.internal"
  port: 27017
  tls:
    mode: requireTLS
    certificateKeyFile: /secure/mongo/server.pem
    CAFile: /secure/mongo/ca.pem
    allowConnectionsWithoutCertificates: true

security:
  authorization: enabled
```

Explanation:

- `requireTLS` requires TLS for incoming connections.
- `certificateKeyFile` is the PEM containing the server certificate and private key per MongoDB configuration.
- `CAFile` contains trusted CA certificates, used where applicable to verify peer certificates.
- `allowConnectionsWithoutCertificates: true` lets TLS clients without a client cert connect when services use **SCRAM** instead of MONGODB-X509.
- `authorization: enabled` turns on auth/role checks.

**Important:** This is a simplified illustrative config. Replica sets and sharded clusters also require internal authentication, hostnames, and inter-member TLS trust. Do not apply verbatim in production without accounting for topology.

### 9.4. SCRAM Client Using TLS Without a Client Certificate

When a MongoDB server is configured to allow TLS clients that do not present a client certificate, the client can:

1. Verify the server certificate.
2. Establish the TLS channel.
3. Authenticate with `SCRAM-SHA-256` using username/password.
4. Receive privileges based on roles.

This is a valid configuration. **You do not need to create an X.509 user just because TLS is enabled.**

---

## 10. MONGODB-X509: Authenticating MongoDB Users with Client Certificates

With `MONGODB-X509`, the server identifies the user from the client certificate instead of authenticating with a SCRAM password.

Characteristics:

- The client connects over TLS.
- The client presents a certificate and corresponding private key.
- The certificate must satisfy the server's trust chain and verification rules.
- MongoDB maps the X.509 **Distinguished Name (DN)** identity to a user.
- The user is managed in the **`$external`** authentication database.
- Roles determine permitted operations after authentication.

### 10.1. Why $external?

SCRAM users are created and authenticated using MongoDB credentials stored in a database like `admin` or `commerce`.

An X.509 identity comes from an external authentication mechanism outside the password database, so MongoDB uses **`$external`** as the authentication database.

```text
SCRAM:
  username/password  ──> admin or commerce

MONGODB-X509:
  client certificate  ──> $external
```

**Never create an X.509 user with a password in `commerce` simply because that user needs read access to `commerce`.**

### 10.2. Certificate Distinguished Name

A client certificate has a subject DN, for illustrative example:

```text
CN=payments-reader,OU=Services,O=Example
```

In practice, the DN format must **exactly match the identity MongoDB derives** under the canonicalization/formatting rules required by your server version, typically related to RFC 2253.

Pay close attention to:

- Component ordering and escaping in the DN.
- Exact organization/common names issued in the certificate.
- How multiple certificates sharing the same subject DN affect identity mapping.
- Whether certificate rotation changes the subject DN.
- Never truncating a full DN to a short CN if the server expects the full identity.

### 10.3. Viewing Subject and Issuer

An administrator can run:

```bash
openssl x509 -in client.pem -noout -subject -issuer -dates -nameopt RFC2253
```

Compare the output against how MongoDB canonicalizes the client certificate subject. Never inspect output in a different format and “guess” the X.509 username.

### 10.4. Creating an X.509 User in $external

Suppose a client certificate was issued and MongoDB uses the canonical username:

```text
CN=payments-reader,OU=Services,O=Example
```

An admin authenticated with user-management privileges can create it:

```javascript
const externalDb = db.getSiblingDB("$external");

externalDb.runCommand({
  createUser: "CN=payments-reader,OU=Services,O=Example",
  roles: [
    { role: "read", db: "commerce" }
  ]
});
```

**There is no `pwd`** on this X.509 user. The certificate is the identity proof, not a SCRAM password.

If the certificate DN does not match the canonical username used by the server, authentication can fail even with a valid CA chain.

### 10.5. Connecting with mongosh

Suppose the client certificate and private key are stored in a PEM file with restricted read permissions:

```bash
mongosh "mongodb://mongo1.example.internal:27017/?tls=true&authMechanism=MONGODB-X509&authSource=%24external" --tlsCAFile /secure/certs/ca.pem --tlsCertificateKeyFile /secure/certs/payments-client.pem
```

Explanation:

- `tls=true` enables TLS.
- `authMechanism=MONGODB-X509` selects X.509 MongoDB user authentication.
- `authSource=%24external` is the URI-encoded form of `$external`.
- `--tlsCAFile` lets the client verify the server chain per configuration.
- `--tlsCertificateKeyFile` supplies the client certificate and private key.
- No MongoDB password is needed for an X.509 user.

If driver/mongosh policy requires an explicit username, that username must match the client certificate's canonical DN; never supply arbitrary SCRAM-like usernames/passwords.

### 10.6. X.509 Users Still Need Roles

Having a certificate accepted by TLS does not grant read/write access. The server still requires:

1. A valid X.509 identity mapped to a user.
2. Roles assigned to that user on application databases/collections.
3. Queries/actions covered by the granted privileges.

For instance, a certificate mapped to `payments-reader` with `read` on `commerce` still cannot `insert` unless granted write privileges.

---

## 11. Why Can a Valid Client Certificate Still Trigger Authentication Failed?

This is a multi-layer troubleshooting problem.

### 11.1. TLS Handshake Failure

Possible causes:

- Client certificate expired.
- Client certificate was not signed by a CA trusted by the server.
- Private key does not match the certificate.
- Certificate chain is missing an intermediate CA.
- Extended Key Usage is unsuitable for client authentication.
- Incompatible TLS version/ciphers.
- Server requires a certificate, but the client did not send one.
- Server certificate hostname does not match the name the client connected to.

Here the error occurs **before** any MongoDB authentication mechanism executes.

### 11.2. TLS Succeeds, but MONGODB-X509 Fails

Possible causes:

- Connection string is still using `SCRAM-SHA-256`.
- `authSource` is not `$external`.
- The X.509 user in `$external` has not been created yet.
- Subject DN ordering or canonical format is wrong.
- Explicit username does not match the client certificate.
- Server/driver/deployment does not support or allow the requested mechanism.

### 11.3. Authentication Succeeds, but Unauthorized

This is a different layer:

- User lacks the required role.
- Role was granted on a different database.
- Command requires a privilege missing from the role.
- Service attempts an admin operation while holding only read access.

**Never fix Unauthorized errors by disabling certificate validation.** Fix the role/authorization properly.

---

## 12. Internal Replica Set X.509 Differs from Client X.509

MongoDB may require **internal member authentication** so replica set or sharded cluster members recognize one another.

Common approaches:

- **Keyfile-based internal authentication**.
- **X.509-based internal authentication**.

However, **X.509 member authentication** is not identical to **MONGODB-X509 client user authentication**.

### 12.1. Two Purposes

```text
Application ──(MONGODB-X509)──> Replica set
                                   │
                             Internal X.509
                                   │
                        Member A ←──→ Member B
```

- Application X.509: a user in `$external` with application roles.
- Member X.509: `mongod`/`mongos` servers prove cluster membership, involving `clusterAuthMode` and member-specific certificate requirements.

### 12.2. clusterAuthMode

Some deployments use:

```yaml
security:
  authorization: enabled
  clusterAuthMode: x509
```

within a complete configuration with proper TLS and certificates on supported servers/versions.

**Do not apply this snippet alone to “enable X.509 for the app”.** Transitioning a cluster to X.509 member authentication requires:

- Preparing certificates across all members.
- Trusted CAs and EKU/DN meeting member authentication requirements.
- Safe rolling transition ordering.
- Ensuring router/topology compatibility.
- A rollback runbook.
- Verifying ongoing inter-member communication.

If misconfigured, the replica set can lose internal communication and cause an outage.

### 12.3. Do Not Reuse One Certificate for Everything

As a security principle, separate identities and private keys:

- Server endpoint certificates.
- Application client authentication certificates.
- Cluster member authentication certificates per cluster policy.

Just because a deployment technically lets you reuse one certificate does not make it good design for operations, rotation, or least privilege.

### 12.4. Keyfiles Are Not SCRAM User Passwords

An internal keyfile is a secret for member authentication, **not `app_reader`'s username/password**. Never put a keyfile into an application connection URI.

---

## 13. Comparing SCRAM and MONGODB-X509

| Criterion | SCRAM | MONGODB-X509 |
|---|---|---|
| Proof of identity | Username/password | Client certificate/private key |
| Authentication database | Database where user was created, e.g., `admin` or `commerce` | `$external` |
| Does user have `pwd`? | Yes, at creation | No SCRAM password |
| Is TLS needed? | Should use TLS to protect traffic | TLS is an essential part of the X.509 flow |
| Client certificate required? | No, if server allows TLS clients without certs | Yes |
| Rotation | Password/credential rotation | Certificate/private key rotation |
| User roles | Yes | Yes |
| Secret to protect | Password/token | Private key/key store password |
| Common errors | Wrong `authSource`, wrong password, mechanism mismatch | CA/DN/cert/`$external` mismatch |
| General app usage | Very common | Suitable when organization has PKI/mTLS |
| Replaces authorization? | No | No |

### 13.1. When to Choose SCRAM?

- Environments needing straightforward integration.
- A secret manager already manages passwords.
- Applications use standard MongoDB drivers.
- Password-based authentication meets policy.
- TLS is fully deployed.

### 13.2. When to Choose MONGODB-X509?

- The organization has PKI and certificate issuance/revocation/rotation workflows.
- Service-to-service identity relies on mutual TLS.
- You want private keys/certificates instead of SCRAM passwords.
- You can manage DN mappings/roles in `$external`.
- You have observability over TLS handshakes, certificate expiry, and revocation.

### 13.3. X.509 Is Not Automatically Stronger Than Every SCRAM Deployment

Security depends on the entire system:

- Can private keys be stolen?
- Are certificates rotated and revoked on time?
- Is the CA trust chain overly broad?
- Do roles follow least privilege?
- Are SCRAM passwords strong, protected, and sent over TLS?
- Do services avoid logging credentials?

Choose a mechanism based on real operational security capability, not just algorithm names.

---

## 14. Java Sync Driver: SCRAM-SHA-256

### 14.1. Using a Connection URI

Example Java app reading a URI from a secret manager or environment:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public final class ScramUriExample {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                    "MONGODB_URI must be set securely");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase("commerce");
            MongoCollection<Document> orders =
                    db.getCollection("orders");

            Document sample = orders.find().first();
            System.out.println(sample == null ? "No data" : "Read success");
        }
    }
}
```

A SCRAM URI looks like:

```text
mongodb://app_reader:<SECRET>@mongo1.example.internal:27017/commerce?authSource=commerce&authMechanism=SCRAM-SHA-256&tls=true
```

**Never commit URIs containing real passwords to git.** Even URIs from environment variables must be protected from exposure via process/container configs and logs.

### 14.2. Using MongoCredential to Avoid Embedding Passwords in URIs

The Java driver provides `MongoCredential`.

```java
import com.mongodb.MongoClientSettings;
import com.mongodb.MongoCredential;
import com.mongodb.ServerAddress;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

import java.util.List;

public final class ScramCredentialExample {
    public static void main(String[] args) {
        String password = System.getenv("MONGO_APP_PASSWORD");
        if (password == null || password.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing MONGO_APP_PASSWORD");
        }

        MongoCredential credential =
                MongoCredential.createScramSha256Credential(
                        "app_reader",
                        "commerce",
                        password.toCharArray()
                );

        MongoClientSettings settings =
                MongoClientSettings.builder()
                        .applyToClusterSettings(builder ->
                                builder.hosts(List.of(
                                        new ServerAddress(
                                                "mongo1.example.internal",
                                                27017)
                                )))
                        .credential(credential)
                        .applyToSslSettings(builder ->
                                builder.enabled(true))
                        .build();

        try (MongoClient client = MongoClients.create(settings)) {
            MongoDatabase db = client.getDatabase("commerce");
            db.runCommand(new Document("ping", 1));
            System.out.println("Connected");
        }
    }
}
```

Here:

- `createScramSha256Credential(user, source, password)` explicitly sets the authentication database to `commerce`.
- `credential(...)` configures SCRAM authentication for the user.
- `enabled(true)` enables TLS; the server certificate must still be verified by the JVM trust store.
- No password encoding in a connection URI is needed.

**Deployment note:** For replica sets or sharded clusters, do not use a single host like this example and treat it as production topology; configure seed lists/`replicaSet`/SRV, TLS trust, and timeouts per your real infrastructure.

### 14.3. Separating authSource from getDatabase

These two lines do not need to reference the same database:

```java
MongoCredential credential =
        MongoCredential.createScramSha256Credential(
                "commerce_service",
                "admin",
                password.toCharArray()
        );

MongoDatabase db = client.getDatabase("commerce");
```

The user was created in `admin` but holds roles on `commerce`. Authentication happens in `admin`; queries run against `commerce`.

### 14.4. Do Not Treat Passwords Like Search Strings

Never arbitrarily trim, lowercase, or Unicode-normalize passwords before handing them to the MongoDB driver. The secret manager should supply the exact secret, and the app must never log it.

### 14.5. Java and Trust Stores

When the server certificate is issued by a public or enterprise CA, the JVM must trust that CA. If an internal CA is not in the default trust store, provision a properly managed trust store.

Illustrative JVM options:

```text
-Djavax.net.ssl.trustStore=/secure/client/mongo-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
-Djavax.net.ssl.trustStorePassword=<TRUSTSTORE_SECRET>
```

Never place real trust store passwords in world-readable startup scripts or process arguments if security policy forbids it. Consider a custom `SSLContext` or a secure secret injection mechanism.

---

## 15. Java Sync Driver: X.509 with a Client Certificate

The Java driver can authenticate using `MONGODB-X509` when:

- TLS is enabled.
- The JVM/client has a certificate/private key to present.
- The server trusts the CA and accepts the client certificate.
- The authentication mechanism is `MONGODB-X509`.
- `authSource` is `$external`.
- MongoDB has the matching user/role mapping.

### 15.1. Connecting via an X.509 URI

```text
mongodb://mongo1.example.internal:27017/?tls=true&authMechanism=MONGODB-X509&authSource=%24external
```

There is no SCRAM password in the URI.

### 15.2. Java Client Using SSL Key Store and Trust Store

A common approach is configuring Java TLS at JVM startup per policy:

```text
-Djavax.net.ssl.keyStore=/secure/client/mongo-client.p12
-Djavax.net.ssl.keyStoreType=PKCS12
-Djavax.net.ssl.keyStorePassword=<KEYSTORE_SECRET>

-Djavax.net.ssl.trustStore=/secure/client/mongo-truststore.p12
-Djavax.net.ssl.trustStoreType=PKCS12
-Djavax.net.ssl.trustStorePassword=<TRUSTSTORE_SECRET>
```

Meaning:

- **Key store** holds the client private key + certificate chain.
- **Trust store** holds the CA used to verify the MongoDB server's certificate.

If the application provides a custom `SSLContext`, JVM defaults may be overridden by that `SSLContext`; configure consistently.

### 15.3. Java X.509 Example

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public final class X509Example {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_X509_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                    "MONGODB_X509_URI is required");
        }

        // JVM TLS keyStore/trustStore are configured at startup.
        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase("commerce");
            db.runCommand(new Document("ping", 1));

            Document first = db.getCollection("orders")
                    .find()
                    .first();

            System.out.println(
                    first == null ? "Authenticated" : "Read success");
        }
    }
}
```

**Caution:** `ping` is not enough to prove read permission on `commerce`, because `ping`'s permission semantics differ from collection reads. Verify an operation requiring actual privileges or check `connectionStatus` with appropriate permissions.

### 15.4. Deriving the Username from the Certificate

Depending on driver and configuration, the username may be inferred from the certificate subject or explicitly specified as the X.509 identity. If specified, it must match the canonical DN accepted by MongoDB; never pass an arbitrary username like `app_reader` just because the certificate CN looks similar.

### 15.5. Expired Client Certificates

A common failure: the Java app's keyStore holds an expired cert while the server certificate is still valid.

Either the TLS handshake or X.509 auth can fail. Check all of:

- Server cert.
- Client cert.
- Intermediate CA chain.
- Trust store.
- Key store.
- Validity periods.
- Certificate subject DN.
- Role mapping in `$external`.

---

## 16. Username, Certificate Subject, and Permissions: Comparison Example

Suppose a system has:

```text
Server endpoint:
  mongo1.example.internal

Application database:
  commerce

SCRAM user:
  username = app_reader
  authentication database = admin
  roles = read on commerce

X.509 user:
  subject DN = CN=svc-reader,OU=Services,O=Example
  authentication database = $external
  roles = read on commerce
```

### 16.1. SCRAM Connection

```text
mongodb://app_reader:<SECRET>@mongo1.example.internal:27017/commerce?authSource=admin&authMechanism=SCRAM-SHA-256&tls=true
```

### 16.2. X.509 Connection

```text
mongodb://mongo1.example.internal:27017/commerce?authSource=%24external&authMechanism=MONGODB-X509&tls=true
```

For X.509, the client must also supply its certificate/private key via `mongosh`/JVM/driver TLS settings.

### 16.3. Same Role Does Not Mean Same Credential

Two principals can share the `read` role yet differ in:

- User identity.
- Authentication database.
- Secrets to manage.
- Rotation and revocation.
- Audit attribution.

Do not treat a certificate as a “password swap” for the same SCRAM user.

---

## 17. Troubleshooting Procedure: Four Layers

### 17.1. Layer 1: Network and Endpoint

Check:

- Is DNS resolution correct?
- Is host/port reachable?
- Do firewall/security group rules allow traffic?
- Does the replica set seed list/SRV match the topology?
- Are client/server TLS modes compatible?

If TCP cannot connect, do not start by changing `authSource`.

### 17.2. Layer 2: TLS Handshake

Check:

- Server certificate chain and CA trust.
- Hostname in SAN.
- Expiry/`notBefore`.
- TLS protocol/ciphers.
- Client cert if the server requires mutual TLS.
- EKU/`clientAuth`/`serverAuth`.
- Key file permissions and private key match.
- Recent CA rotation or cert replacement.

TLS errors happen **before** SCRAM/X.509 authentication succeeds.

### 17.3. Layer 3: Authentication

For SCRAM:

- Is the username right?
- Is the password right?
- Which auth DB was the user created in?
- Is `authSource` right?
- Is the mechanism supported by both user and server?
- Did the URI parser misread the password due to missing percent-encoding?

For X.509:

- Is `authMechanism=MONGODB-X509` enabled in the client?
- Is `authSource=$external` set accurately?
- Is the client certificate being sent?
- Does the canonical DN match the user in `$external`?
- Does the deployment accept X.509?

### 17.4. Layer 4: Authorization

If connection and authentication succeeded, yet queries return `not authorized`:

- Does the user have the role on the right database/collection?
- Which action does the command require?
- Were roles changed recently?
- Are you targeting a different database than intended?
- Did the app confuse `default DB` with `authSource`?

### 17.5. Common Errors Table

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Authentication failed with SCRAM | Wrong password/username | Verify secret and user |
| Right password, still cannot log in | Wrong `authSource` | Check which database the user was created in |
| SCRAM-SHA-256 fails, another mechanism works | Missing credential for that mechanism | Check user/server/driver support |
| Login succeeds, insert returns Unauthorized | Read-only role | Grant appropriate role per policy |
| TLS certificate verify failed | Untrusted CA chain | Configure valid CA/trust store |
| TLS hostname mismatch | SAN lacks connected hostname | Use matching DNS or reissue cert |
| TLS handshake fails for SCRAM client | Server requires client cert | Check mutual TLS requirements |
| X.509 auth fails after TLS succeeds | Missing or wrong DN mapping | Check `$external` user and certificate subject |
| X.509 auth fails due to `authSource` | Using `admin`/`commerce` | Use `$external` |
| X.509 app has role yet still fails | Client cert not sent/not trusted | Check PEM/keyStore/trust |
| Replica set disrupted after `clusterAuthMode` | Member certs/trust out of sync | Follow member-auth runbook |
| One client works, another fails | Different CA/hostname/driver settings | Compare endpoints and TLS settings |
| Connections fail only after cert rotation | CA chain/DN/secret changed | Compare old/new certs and user mapping |
| Forgotten admin password | Credential recovery needs dedicated process | Never disable auth arbitrarily in production |

---

## 18. Measuring and Verifying Without Leaking Secrets

### 18.1. Inspect Current Identity

In `mongosh` during an authenticated session:

```javascript
db.runCommand({ connectionStatus: 1 });
```

Displays authenticated users and roles per the command response. Never print credential secrets to the console.

### 18.2. Inspect Users in the Current Database

With an authorized admin user:

```javascript
db.getSiblingDB("admin").getUsers();
db.getSiblingDB("commerce").getUsers();
db.getSiblingDB("$external").getUsers();
```

For `$external`, behavior follows deployment features and permissions; not every application account is allowed to list users.

### 18.3. Verify Permissions with Real Operations

For the `read` role:

```javascript
db.getSiblingDB("commerce").orders.findOne();
```

For `readWrite`, test insert/update on an authorized **lab** collection—never test on live business data.

### 18.4. Do Not Use ping as an Authorization Test

```javascript
db.adminCommand({ ping: 1 });
```

This only confirms basic connectivity at that command level; it does not prove the user can read `commerce.orders` or create users.

### 18.5. Avoid Leakage in Logs

Never log:

- Passwords.
- Full URIs with embedded credentials.
- Client PEM private keys.
- Key store passwords.
- Full private certificate contents.
- Secret manager tokens.
- SCRAM internal credential material.

You may log sanitized details:

- Endpoint/replica set name.
- Intended mechanism.
- Configured `authSource`.
- Principal name sanitized per policy (avoid PII).
- Error code/category.
- Public certificate fingerprint or expiry if policy allows.

---

## 19. Certificate Rotation and Password Rotation

### 19.1. SCRAM Rotation

A basic plan:

1. Identify which accounts use the credential.
2. Prepare the new secret in the secret manager.
3. Test in staging/canary.
4. Perform rotation per supported policy.
5. Ensure clients re-authenticate with the new secret.
6. Monitor authentication error rates.
7. Revoke old/unused credentials if using a dual-account approach.
8. Audit who made the change and when.

For zero-downtime systems, **rolling over between two service accounts** is sometimes easier to manage than changing a single password used simultaneously by every process. Ensure careful role parity and cleanup.

### 19.2. X.509 Rotation

A plan may include:

1. Prepare a new cert and new private key issued by the proper CA.
2. Verify SAN/EKU/validity and subject DN.
3. If the DN changes, prepare the corresponding user mapping/roles in `$external`.
4. Ensure the server trusts the new chain (may require old/new CA overlap).
5. Deploy the new cert/key in waves, restarting/reloading clients per driver APIs.
6. Monitor TLS handshake and auth errors.
7. Revoke the old cert and clean up stale user mappings.
8. Monitor expiry and revocation policies.

**Certificate rotation is not just copying a new PEM.** If the DN changes, the MongoDB X.509 user identity changes too, causing failed logins or altered roles.

### 19.3. CA Rotation

When replacing a CA:

- Clients must trust the CA signing new server certificates.
- Servers must trust the CA signing new client certificates.
- Cluster members may need CA overlap during rolling transitions.
- Never replace everything at once without testing and a rollback plan.

### 19.4. Certificate Expiry Monitoring

Do not wait until a certificate expires to act. Track:

- Days-to-expiry for server certificates.
- Days-to-expiry for X.509 client certificates.
- CA/intermediate expiry.
- Pods/services still using older certs.
- Authentication/TLS failure rates after deploys.
- Lead time needed to issue and roll out new certs.

---

## 20. Real-World Operational Scenarios

### 20.1. App Uses the Right Password but Connects with the Wrong authSource

User created in:

```javascript
use admin
db.createUser({
  user: "commerce_app",
  pwd: passwordPrompt(),
  roles: [{ role: "readWrite", db: "commerce" }]
});
```

Wrong:

```text
mongodb://commerce_app:<SECRET>@host/commerce
```

Without `authSource`, the driver may pick `commerce` as the authentication database.

Correct:

```text
mongodb://commerce_app:<SECRET>@host/commerce?authSource=admin
```

### 20.2. Application TLS Succeeds Without a Client Cert

The server certificate is valid, the client trusts the CA, the server allows TLS clients without certificates, and the app uses SCRAM.

This is **TLS encryption + SCRAM authentication**, not X.509 user authentication.

### 20.3. X.509 Client Certificate Trusted by CA Yet Cannot Log In

Either the matching user in `$external` has not been created or the DN mapping is wrong. TLS trust is one step; MongoDB user authentication is the next.

### 20.4. Client Has a Certificate Yet Still Uses SCRAM

Supplying a client cert in TLS config does not automatically switch the authentication mechanism to `MONGODB-X509`. If the URI or `MongoCredential` still configures SCRAM, the driver authenticates via SCRAM within supported mechanisms.

### 20.5. Authenticated User Lacks Read Permission

A user in `admin` holds roles on `reports`, yet the application queries `commerce`. Even with the right `authSource` and successful SCRAM login, querying `commerce` returns Unauthorized.

### 20.6. Connecting by IP Instead of Hostname

The cert only has a DNS SAN, and the client connects by IP, causing hostname verification to fail. Align DNS and the certificate; never disable hostname verification in production.

### 20.7. Server TLS Cert Replaced and Java Client Fails

The JVM trust store lacks the new CA or the hostname SAN changed. Compare the trust chain and server cert rather than hastily changing SCRAM passwords.

### 20.8. Replica Set Internal Auth Changed and App Loses Connection

If member auth is misconfigured, the cluster can lose its primary or healthy topology. This is a server-to-server authentication issue, not necessarily an application credential issue.

---

## 21. Common Misconceptions

| Misconception | Why It's Wrong | Correct Understanding |
|---|---|---|
| `/commerce` in the URI is always `authSource` | `authSource=admin` may be set | Database context differs from user lookup DB |
| A user in `admin` is `root` | Roles determine privileges | `admin.app` may only have `read` on `commerce` |
| Right password guarantees login | `authSource`/mechanism may be wrong | Verify user, source, and mechanism together |
| SCRAM encrypts all traffic | SCRAM is authentication | TLS protects traffic in transit |
| Enabling TLS means using MONGODB-X509 | TLS can pair with SCRAM | Choose auth mechanism separately |
| An X.509 user has a password | X.509 relies on certificates | Users in `$external` have no SCRAM `pwd` |
| A valid cert grants `readWrite` | Authorization is separate | Assign proper roles |
| Client cert and server cert are the same | They prove different sides | Manage certs and private keys per role |
| A CA file is a user certificate | CA verifies chains, not principals | Client leaf cert represents the app |
| `authSource` for X.509 is `commerce` | X.509 uses `$external` | Roles can still target `commerce` |
| Changing DN doesn't affect the user | DN is the identity mapping | Prepare updated user mappings |
| Expired cert is a SCRAM error | TLS can fail before auth | Check TLS first |
| Disabling cert validation fixes errors | Loses endpoint verification | Fix chain/SAN/CA |
| Setting `clusterAuthMode: x509` enables app X.509 | Internal member auth is a separate layer | Separate member auth from app auth |
| Keyfile is an application password | Keyfiles are for member auth | Apps use dedicated user credentials |
| `ping` success proves `readWrite` | `ping` does not test those privileges | Test an actual privileged operation |
| `use db` switches identity | Session keeps the same principal | Identity binds at auth handshake |
| Passwords in git URIs are fine in private repos | Secrets leak via logs/history/backups | Use secret managers and rotation |
| Sharing one user across all services | Hurts auditing, rotation, least privilege | Dedicated principal per workload |
| Granting `root` to apps stops Unauthorized | Excessive privileges | Fix least-privilege roles |
| One certificate for all services | Hard to isolate and revoke | Separate identity/key per service |
| TLS on one node suffices for a replica set | Topology has multiple endpoints | Synchronize certs/trust across members |

---

## 22. Lab A: SCRAM with Two Different authSources

**Goal:** distinguish the authentication database from the database where roles apply.

1. In the lab, create `app_reader` in `commerce` with the `read` role on `commerce`.
2. Connect with `authSource=commerce` and the correct password.
3. Try a URI with the same username/password but `authSource=admin`; record the authentication outcome.
4. Create a **different** user `app_admin_source` in `admin` with the `read` role on `commerce`.
5. Connect with `authSource=admin` and default DB `commerce`.
6. Check `connectionStatus` and `db.getName()`.
7. Explain why two users with identical read access to `commerce` can live in two different auth databases.

**Key takeaway:** Not just any `authSource` works; it must point to the exact database storing the credentials.

## 23. Lab B: SCRAM-SHA-256 vs. SCRAM-SHA-1

1. On a supported lab server, create a user with `SCRAM-SHA-256` credentials.
2. Connect using `authMechanism=SCRAM-SHA-256`.
3. Try a mechanism not supported by that user if the lab allows and record the error.
4. Inspect roles/privileges.
5. Explain why requesting a mechanism on the client does not make MongoDB synthesize matching credentials automatically.
6. State why SCRAM should still run over TLS.

Never alter authentication mechanisms of production users just for practice.

## 24. Lab C: TLS Server Authentication + SCRAM

On a test instance with a valid CA/server certificate:

1. Enable `requireTLS` and configure the server cert.
2. Have the client trust the right CA.
3. Connect from the client with `tls=true` using a SCRAM user.
4. Inspect the server hostname/SAN.
5. Attempt connecting via a hostname **not in the SAN** in your lab environment and record the error.
6. Fix it via valid DNS/certs, without enabling insecure mode.
7. Explain why the client does not need an X.509 user when using SCRAM.

## 25. Lab D: MONGODB-X509

On a lab supporting mutual TLS:

1. Issue a client certificate with appropriate `clientAuth`.
2. Inspect subject/issuer/validity using `openssl`.
3. Create the matching user in `$external` with the `read` role on `commerce`.
4. Connect using `MONGODB-X509` and `authSource=%24external`.
5. Verify the authenticated user and run a read query in the lab.
6. Attempt an insert and confirm write access is denied.
7. Observe behavior when the DN user mapping does not yet exist—**never delete production users**.
8. Explain why a client certificate trusted by the CA still requires user roles.

## 26. Lab E: Java Sync Driver

Write two programs:

**Program 1 — SCRAM**

- `MongoCredential.createScramSha256Credential()`.
- `source="admin"` or `source="commerce"` matching the user.
- TLS trusting the server.
- Query the authorized collection.
- Never print passwords to logs.

**Program 2 — X.509**

- URI with `authMechanism=MONGODB-X509`.
- `authSource=%24external`.
- JVM `keyStore` containing client certificate/private key.
- JVM `trustStore` containing the CA.
- Query the target database.
- Inspect DN and roles when authentication fails.

Compare the secret paths: password vs. private key.

## 27. Lab F: Layered Troubleshooting

Given four scenarios:

| Scenario | First Place to Investigate |
|---|---|
| Hostname mismatch in TLS | Certificate SAN/endpoint |
| SCRAM Authentication failed | User/password/`authSource`/mechanism |
| X.509 TLS succeeds yet auth fails | `$external` user, subject DN, mechanism |
| Login succeeds yet insert returns Unauthorized | Roles/privileges |

Write a runbook distinguishing each failure. Never use `root`, `tlsInsecure`, or disabling authorization as a quick workaround.

## 28. Lab G: Rotation

Plan for three events:

1. A SCRAM password is suspected of leaking.
2. A client X.509 cert is about to expire.
3. An internal CA is scheduled to be replaced.

For each event, specify:

- Affected identities.
- Secrets/certificates to rotate.
- Granted roles and overlap window.
- Pre-rollout checks.
- How to monitor errors.
- How to roll back/revoke.
- Data that must never be logged.

## 29. Security Deployment Checklist

### 29.1. Authentication

- [ ] Clearly document whether each account uses SCRAM or X.509.
- [ ] SCRAM-SHA-256 is preferred where versions/credentials support it.
- [ ] Users are created in the designated authentication database.
- [ ] URIs/`MongoCredential` set `authSource` accurately.
- [ ] Passwords are read from a secret manager, never committed to source.
- [ ] Passwords are not arbitrarily normalized.
- [ ] Each service has its own dedicated account.
- [ ] Roles follow the principle of least privilege.
- [ ] `root` accounts are never used by applications.

### 29.2. TLS/Certificates

- [ ] TLS is enabled on production connections per policy.
- [ ] Clients verify server certificate chains and hostname SANs.
- [ ] Server private keys are protected.
- [ ] Insecure certificate/hostname bypasses are disabled.
- [ ] If using mTLS, client certs are trusted by the server and have proper EKU.
- [ ] X.509 users exist in `$external` with exact canonical DNs.
- [ ] Client certificates/private keys are not stored in repos.
- [ ] JVM/key stores/CA trust are properly configured.
- [ ] Certificate expiry/rotation is monitored.
- [ ] CA rotation and revocation plans exist.

### 29.3. Topology and Operations

- [ ] Replica sets/sharded clusters have proper internal authentication.
- [ ] `clusterAuthMode` is not confused with app authentication.
- [ ] Member keyfiles are never used as application secrets.
- [ ] Verify `connectionStatus` and permissions via scoped operations.
- [ ] Error logs strip secrets/URI passwords.
- [ ] A runbook distinguishes network/TLS/authentication/authorization issues.
- [ ] Changes to certificates/passwords are tested in staging/canary first.
- [ ] Auditing, monitoring, and rollback plans are in place.

---

## 30. Official MongoDB Documentation

- [MongoDB Manual – Authentication](https://www.mongodb.com/docs/manual/core/authentication/)
- [MongoDB Manual – SCRAM](https://www.mongodb.com/docs/manual/core/security-scram/)
- [MongoDB Manual – Authentication Database](https://www.mongodb.com/docs/manual/core/authentication/#authentication-database)
- [MongoDB Manual – Connection String Options](https://www.mongodb.com/docs/manual/reference/connection-string-options/)
- [MongoDB Manual – db.createUser()](https://www.mongodb.com/docs/manual/reference/method/db.createUser/)
- [MongoDB Manual – db.updateUser()](https://www.mongodb.com/docs/manual/reference/method/db.updateUser/)
- [MongoDB Manual – db.changeUserPassword()](https://www.mongodb.com/docs/manual/reference/method/db.changeUserPassword/)
- [MongoDB Manual – Role-Based Access Control](https://www.mongodb.com/docs/manual/core/authorization/)
- [MongoDB Manual – Configure TLS/SSL](https://www.mongodb.com/docs/manual/tutorial/configure-ssl/)
- [MongoDB Manual – X.509 Certificate Authentication](https://www.mongodb.com/docs/manual/core/security-x.509/)
- [MongoDB Manual – Configure MongoDB with X.509 Certificate Authentication](https://www.mongodb.com/docs/manual/tutorial/configure-x509-client-authentication/)
- [MongoDB Manual – Internal/Membership Authentication](https://www.mongodb.com/docs/manual/core/security-internal-authentication/)
- [MongoDB Manual – Localhost Exception](https://www.mongodb.com/docs/manual/core/localhost-exception/)
- [MongoDB Java Sync Driver – Authentication](https://www.mongodb.com/docs/drivers/java/sync/current/security/authentication/)
- [MongoDB Java Sync Driver – TLS/SSL](https://www.mongodb.com/docs/drivers/java/sync/current/security/tls/)

> Option names and X.509/internal authentication requirements may vary by MongoDB Server version, driver version, or cloud provider. For managed deployments, consult the provider's documentation and verify supported features; do not treat self-managed `mongod.conf` examples as instructions for editing an Atlas cluster.

## 31. Summary

MongoDB has multiple security layers, and the most important lesson is **never mix them up**:

1. **SCRAM** authenticates users with username/password via challenge-response, preferring `SCRAM-SHA-256` in supported environments.
2. **Authentication database** determines where MongoDB looks up user credentials. `authSource=admin` or `authSource=commerce` must match where the user was created; it need not match the database holding the data.
3. **Authorization** is governed by roles and privileges—it does not escalate simply because an account lives in `admin` or because TLS succeeded.
4. **TLS server certificates** let clients verify the server and encrypt traffic, and can be used alongside SCRAM.
5. **MONGODB-X509** uses client certificates for application authentication, typically mapping the subject DN to a user in `$external`.
6. **Internal member X.509** is separate from application X.509; changing it must follow a cluster runbook.
7. **The Java driver** should fetch secrets/key material from secure sources and properly configure credential sources, TLS trust/key stores, and replica set/SRV topology.
8. When troubleshooting errors, inspect **network → TLS → authentication → authorization** in order instead of disabling checks or granting overly broad privileges.

A proper deployment does not merely “connect”—it **verifies the right server, logs in as the right identity, grants the right privileges, protects secrets, and plans for rotation and recovery**.
