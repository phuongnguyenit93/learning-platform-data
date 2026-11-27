# Distinguishing Authentication Errors from Insufficient Operation Privileges in MongoDB

## 1. Problem Statement and Objectives

A Spring Boot application queries MongoDB. When calling `findOne`, data is returned normally; however, when calling `insertOne`, the application throws an error. The on-call operator says "maybe the password is wrong," resets the database account password, and restarts all Pods. The error persists, while the secret change causes additional connections to fail.

Actual root cause: the account **authenticated successfully**, but it only has the `read` role; it lacks the `insert` action. This is an **authorization** issue, not an **authentication** issue.

~~~text
Application
    |
    v
DNS / TCP / TLS
    |
    v
MongoDB authentication
    |
    +--> Fail: Who are you? (AuthenticationFailed, code 18)
    |
    v
Authenticated principal
    |
    v
MongoDB authorization
    |
    +--> Fail: May you perform this action on this resource?
    |          (Unauthorized, code 13)
    |
    v
Command execution / business logic
~~~

This lesson belongs to the **Database Engine Document MongoDB** module, **Troubleshooting** chapter, covering **Distinguishing Authentication Errors from Insufficient Operation Privileges**.

### 1.1. What Will You Be Able to Do?

- Explain the difference between MongoDB authentication and authorization.
- Correctly read error codes `18 AuthenticationFailed` and `13 Unauthorized`.
- Distinguish wrong username/password, `authSource`, mechanism, secret version, URI encoding, and TLS issues.
- Inspect the identity and effective privileges on the current connection.
- Understand roles, inheritance, resources, actions, and least privilege.
- Distinguish Atlas UI/project users from MongoDB database users.
- Build a lab for the case where login succeeds but data writes are rejected.
- Create a custom role allowing only specific operations.
- Diagnose errors in the MongoDB Java Driver and Spring Data MongoDB.
- Handle permission errors when running aggregations, change streams, transactions, index migrations, and backups.
- Design controlled secret rotation and permission changes.
- Build runbooks, incident reports, tests, and production checklists.

**Principle:** Always determine at **which layer** the error occurs before applying a fix. Do not reset a password if the root cause is a missing privilege; do not grant `root` to fix an unidentified error.

## 2. Authentication: Connection Identity

Authentication answers the question **"Who is connecting?"**.

A MongoDB principal can authenticate using:

1. SCRAM-SHA-256 or SCRAM-SHA-1.
2. X.509 client certificate.
3. OIDC in supported deployments/drivers.
4. AWS IAM in Atlas and corresponding mechanisms.
5. LDAP/Kerberos in supported editions and environments.

The specific mechanism depends on MongoDB Server, Atlas tier, Java Driver, and organizational configuration.

### 2.1. SCRAM

With SCRAM, the client proves it knows the password corresponding to the database user. The server verifies the user, mechanism, and authentication database.

If incorrect:

~~~text
MongoServerError: Authentication failed.
code: 18
codeName: AuthenticationFailed
~~~

This is an example of the error class; the exact display in `mongosh` and the Java Driver may differ.

### 2.2. Authentication Database Is a Critical Part of Identity

Two identically named principals in two authentication databases can be two completely different entities:

~~~text
reader@admin
reader@reporting
~~~

If the user was created in `reporting` but the URI specifies `authSource=admin`, even the right password can be rejected during authentication.

### 2.3. Logging In Without Any Roles

A database user with `roles: []` can still authenticate if credentials are valid. When calling `find` or `insert`, the server rejects the operation due to lack of privileges.

Do not conclude that "login succeeded" means "all application business operations can run."

## 3. Authorization: What Can Be Done on Which Data?

Authorization answers **"Can this principal perform this operation on this resource?"**

MongoDB uses Role-Based Access Control (RBAC):

~~~text
Database User
     |
     +--> Role A
     |      |
     |      +--> find on orders.orders
     |
     +--> Role B
            |
            +--> insert on orders.outbox
     |
     v
Effective privilege set
~~~

A privilege is described as:

~~~javascript
{
  resource: {
    db: "orders",
    collection: "outbox"
  },
  actions: ["insert"]
}
~~~

### 3.1. Resource vs. Action

| Component | Example | Question |
|---|---|---|
| Principal | `orders_api@admin` | Who is this connection? |
| Action | `insert` | What does the command need to do? |
| Database | `orders` | Which DB is it in? |
| Collection | `outbox` | On which collection? |
| Scope | Collection/database/cluster | Does the privilege cover that resource? |

A `find` privilege on `orders.orders` does not allow `insert` into `orders.orders`.

### 3.2. A Role in Another Database Does Not Grant Privileges Automatically

If a user has `readWrite` on `orders_dev`, it cannot automatically write to `orders_prod`. Check the exact database mentioned in the error.

### 3.3. Cluster-Level Privileges Differ from CRUD

An account may read `orders` normally yet be forbidden from running `serverStatus`, `replSetGetStatus`, `createUser`, or backup admin commands. This is not a wrong-password condition.

## 4. Error Codes 18 and 13

Per MongoDB Manual Error Codes:

| Code | codeName | Failing stage | Investigation direction |
|---:|---|---|---|
| 18 | `AuthenticationFailed` | Proving identity | Username, secret, authSource, mechanism |
| 13 | `Unauthorized` | Checking permissions | Principal, command, resource, role/action |

### 4.1. AuthenticationFailed Example

~~~text
Command failed with error 18 (AuthenticationFailed):
'Authentication failed.'
~~~

Possibilities: wrong password, user does not exist in `authSource`, secret rotated, wrong mechanism, broken URI encoding.

### 4.2. Unauthorized Example

~~~text
MongoServerError: not authorized on orders
to execute command { insert: "outbox", ... }
code: 13
codeName: Unauthorized
~~~

Possibilities: principal authenticated but lacks `insert`, role was granted on another database, or deployment uses a narrowly scoped custom role.

### 4.3. Do Not Match Only on Message Strings

There may be wrappers, translations, or message changes across MongoDB/driver versions. Prioritize server error codes, `codeName`, and the exception cause chain.

### 4.4. Preliminary Triage Before Taking Action

~~~text
Error code 18?
  --> Check Authentication

Error code 13?
  --> Check Authorization

Neither of the above codes?
  --> Check DNS, TLS, network, topology, command syntax,
      schema/validation, or business logic.
~~~

## 5. Errors That Look Like Authentication Issues But Are Not

| Symptom | Approximate category | Investigation direction |
|---|---|---|
| `UnknownHostException` | DNS | Host, SRV/TXT, resolver |
| `MongoSocketOpenException` | TCP/network | Firewall, endpoint, port |
| `SSLHandshakeException` | TLS | Certificate chain, CA, SAN, expiry |
| `PKIX path building failed` | TLS trust | Java truststore |
| `MongoTimeoutException` | Timeout/topology | Server selection, network, primary |
| `HostUnreachable` | Network | Node, routing, firewall |
| `CommandNotFound`, code 59 | Command/version | Is the command supported? |
| `NamespaceNotFound`, code 26 | Namespace | Does the collection exist? |
| `DuplicateKey`, code 11000 | Data constraint | Unique index |
| `WriteConflict` | Concurrency | Transaction/retry logic |
| `Unauthorized`, code 13 | RBAC | Action/resource |

### 5.1. Connection Layers in Order

~~~text
Hostname resolved
       |
TCP connection established
       |
TLS handshake / server identity verified
       |
MongoDB handshake/topology discovered
       |
Authentication attempted
       |
Authorization for command
       |
Command executed
~~~

If DNS is not working, there is no evidence of a wrong password. If TLS fails because the CA is untrusted, granting the `readWrite` role will not fix it either.

### 5.2. Avoid Changing Two Things at Once

Do not simultaneously open the firewall wide, disable TLS, and change the password just to "see what works." Doing so destroys evidence, increases risk, and complicates rollback.

## 6. Troubleshooting Decision Tree

~~~text
Application reports MongoDB error
         |
         v
Extract code / codeName / operation / namespace
         |
         +--> No server response?
         |       |
         |       +--> DNS / TCP / TLS / topology
         |
         +--> Code 18?
         |       |
         |       +--> Authentication: user, authSource,
         |             password/token/cert, version
         |
         +--> Code 13?
         |       |
         |       +--> Authorization: principal,
         |             action, resource, roles
         |
         +--> Other code?
                 |
                 +--> Use MongoDB error table,
                       query/server logs, and runbook
~~~

Triage questions:

1. Which command failed?
2. Which namespace appears in the error?
3. Which URI/secret source and active profile is the app using?
4. Which principal actually authenticated?
5. Which commands still succeed?
6. After what change did the error start?
7. Is there an impact on data, security, or SLOs?

## 7. URI: Distinguishing Database and `authSource`

An illustrative URI:

~~~text
mongodb://<user>:<encoded-password>@db1.example.test:27017,db2.example.test:27017/orders?replicaSet=rs0&authSource=admin&tls=true
~~~

Components:

- `/orders`: default database when the application does not override it.
- `authSource=admin`: authentication database containing the SCRAM user.
- `replicaSet=rs0`: expected topology.
- `tls=true`: transport protection.
- Hostnames: seed addresses.
- Username/password: authentication secret credentials.

### 7.1. Authentication DB and Operation DB Are Independent

A user in `admin` can be granted `readWrite` on `orders`. The connection still uses `authSource=admin`.

### 7.2. Passwords with Special Characters

Reserved characters such as `@`, `:`, `/`, `?`, `#`, `%` must be properly percent-encoded when placed in the URI userinfo.

If you insert a raw password containing `@` into the URI, the parser may misread host/userinfo; the resulting error can be a parse error or `AuthenticationFailed`.

### 7.3. Do Not Log Full Connection Strings

A URI containing credentials is a secret. Incident records should use a redacted URI or secret reference ID, never print the raw value.

### 7.4. Do Not Infer Privileges from the Database Path

A connection string containing `/orders` does not mean `MongoClient` is locked to that database. Code can still query `client.getDatabase("payments")`; MongoDB RBAC decides whether it is permitted.

## 8. `mongodb+srv://` on Atlas

Atlas commonly provides SRV connection strings:

~~~text
mongodb+srv://<user>:<encoded-secret>@cluster0.example.mongodb.net/orders?authSource=admin&retryWrites=true&w=majority
~~~

With SRV, the driver uses DNS SRV/TXT to discover hosts; TLS is enabled by default unless configured otherwise per MongoDB URI rules.

### 8.1. Three Distinct Configuration Types

- **Network access:** IP access list, private endpoint, VPC routing, DNS.
- **Authentication:** Database user, SCRAM/X.509/OIDC/IAM.
- **Authorization:** Database roles and specific privileges.

A network error usually does not receive server error code 18/13 because the request never reached that stage.

### 8.2. Do Not Open IP Allowlists Indefinitely for Debugging

Restrict network access, use an approved test runner/Pod IP, and revert temporary access. Do not use `0.0.0.0/0` in production as a long-term fix.

### 8.3. Wrong Replica Set Topology

If a URI uses `directConnection=true` to one node while the application expects failover, server selection after an election can fail. This is a topology setup problem, not automatically authentication.

## 9. SCRAM: Common Causes of Code 18

1. Wrong username or incorrect letter casing.
2. Wrong password or secret not yet updated.
3. Wrong authentication database.
4. User was actually created in a different environment.
5. Mismatched authentication mechanism.
6. URI password not properly encoded.
7. Database user deleted or expired.
8. Secret rotation updated the server side while the application still uses the old version.
9. Some Pods/workers fetch different secret versions.
10. Spring Boot properties/profiles override the intended URI.

### 9.1. Right Password but Wrong `authSource`

~~~text
User created at authz_lab

URI uses authSource=admin

Server looks for user in admin
   |
   v
AuthenticationFailed(18)
~~~

Fix `authSource`; do not grant more roles before proving the user has authenticated.

### 9.2. Wrong Mechanism

If a user is only configured for SCRAM-SHA-256 yet the client forces an unsupported mechanism, authentication can fail. Check user mechanisms and driver/server compatibility.

### 9.3. Do Not Blindly Reset Passwords

Changing the password when only code 13 appears neither grants the missing operation privilege nor helps, and it invalidates new connections still using the old secret.

## 10. X.509 and the Two Layers: TLS vs. Database Identity

X.509 involves two concepts:

- TLS trust/certificate validation establishes a secure connection.
- MongoDB X.509 authentication maps the client identity and corresponding roles.

### 10.1. TLS Handshake Failure

~~~text
Java SSLHandshakeException
  -> Certificate chain/SAN/expiry/truststore
~~~

You cannot conclude that the database user lacks permissions.

### 10.2. TLS Passes but MongoDB Principal Is Invalid

A client certificate may be accepted by the TLS layer, yet its subject/identity lacks a valid MongoDB user mapping. That is an authentication error.

### 10.3. Authentication Passes, Role Missing

If an X.509 principal authenticates yet lacks `find` on a collection, MongoDB returns code 13 just like other mechanisms.

### 10.4. `authSource` with External Mechanisms

X.509 and non-SCRAM mechanisms commonly use `$external` per their respective documentation. Do not switch to `admin` simply because another SCRAM account uses `admin`.

### 10.5. Do Not Disable TLS Verification

`tlsInsecure`, `tlsAllowInvalidHostnames`, or a trust-all Java `SSLContext` are unsafe workarounds. They do not add MongoDB privileges.

## 11. OIDC and AWS IAM Also Require RBAC

In supported environments, OIDC and IAM allow workloads to use identity-based authentication instead of long-lived SCRAM passwords.

~~~text
External Identity Provider
            |
            v
Token / AWS credentials
            |
            v
MongoDB Authentication
            |
            v
Database Principal / Role Mapping
            |
            v
MongoDB Authorization
~~~

If the token is expired, issuer/audience is wrong, or identity mapping is invalid: authentication issue.

If the token is valid and MongoDB recognizes the principal, yet the principal lacks the `insert` action: authorization issue.

### 11.1. IAM Role Does Not Replace MongoDB Database Role

AWS IAM policies and MongoDB collection privileges are two separate permission sets. A workload may be allowed by AWS to obtain credentials yet still have commands rejected by MongoDB.

### 11.2. Do Not Guess the Mechanism from the URI

`authMechanism=MONGODB-OIDC` or AWS IAM requires proper driver, provider, callback/credential configuration, and server support. Do not just add a query parameter and assume the migration is complete.

## 12. MongoDB RBAC: Roles, Privileges, and Resources

A MongoDB role groups privilege actions on resources.

~~~javascript
{
  role: "ordersInserter",
  privileges: [
    {
      resource: {
        db: "authz_lab",
        collection: "orders"
      },
      actions: ["find", "insert"]
    }
  ],
  roles: []
}
~~~

### 12.1. Resources Have Scopes

- Specific collection.
- Database with matching collections.
- Cluster-level actions.
- Other special scopes per the privilege model.

### 12.2. Roles Can Inherit Other Roles

Effective permissions are the union of direct grants and inherited roles. Looking only at a name like `custom_reader` is not enough; check the final actions.

### 12.3. No Simple Deny Rule to Override Broad Grants

MongoDB RBAC is primarily based on positive grants. Do not expect a custom role named `denyWrites` to automatically revoke write permissions from `readWrite`.

### 12.4. Authentication Source Does Not Determine Role Resource Scope

A user created in `admin` can be assigned a role on `orders` or `reporting`. The identity database and the target resource database must be inspected separately.

## 13. Common Built-In Roles

| Role | Primary permissions | Do not assume |
|---|---|---|
| `read` | Read data in the specified database | Does not allow writes |
| `readWrite` | Read/write and some collection/index operations | Not `root` |
| `dbAdmin` | Database/metadata administration | Not equivalent to `readWrite` |
| `userAdmin` | Manage users/roles within scope | Not a business CRUD role |
| `clusterMonitor` | Observe cluster status | Does not automatically grant CRUD |
| `backup` | Appropriate backup operations | Not synonymous with restore |
| `restore` | Appropriate restore operations | Not an app role |
| `readAnyDatabase` | Read multiple databases within scope | Does not grant writes |
| `root` | Very broad privileges | Do not grant to regular apps |

Detailed actions vary between Atlas/self-managed and across versions; consult the Built-In Roles documentation for your deployment.

### 13.1. `readWrite` Is Not `userAdmin`

A business service with `readWrite` should not be allowed to manage users and grant roles to itself. Identity administration must belong to a DBA/Security workflow.

### 13.2. `dbAdmin` Is Not Synonymous with `find`/`insert`

Role names can be misleading. Check effective privileges by action rather than inferring from the name.

### 13.3. Monitoring Agents Need Appropriate Roles

`serverStatus`, `replSetGetStatus`, or cluster metrics may require privileges beyond an application `read` role. Separate the monitoring agent identity.

## 14. Atlas UI Users vs. Database Users

MongoDB Atlas manages at least two categories of identities that must be distinguished:

| Identity | Privilege system | Purpose |
|---|---|---|
| Atlas organization/project user | Atlas IAM/project roles | Managing Atlas UI/API |
| Atlas service account/API key | Atlas management API roles | Atlas automation |
| MongoDB database user | Database roles/custom privileges | MongoDB Driver, `mongosh` |
| Cloud IAM principal | Cloud permissions, sometimes DB auth identity | Secrets/network/cloud resources |

### 14.1. Project Owner Is Not a SCRAM Login

Logging into the Atlas web console and seeing a cluster does not mean you can put your web email/password into a MongoDB URI and authenticate.

### 14.2. Database Users in Atlas Are Managed via Atlas

Use the Atlas UI, Atlas CLI, Administration API, or supported integrations. Do not use `db.createUser()` on Atlas as a standard administration method; changes may be reverted by Atlas.

### 14.3. Watch Out for Cluster Restrictions

Atlas database users can be restricted to specific clusters/federated instances. The same username connecting to another project/cluster may not have valid access.

### 14.4. Atlas Custom Database Roles

Atlas supports built-in roles, custom roles, and specific privileges, though not every self-managed privilege action applies identically across all Atlas tiers.

### 14.5. Atlas Data Explorer Does Not Prove Driver Permissions

A user may access data through the Atlas UI via a UI role; the Java application still needs a MongoDB database principal with the proper auth mechanism/roles.

## 15. The Most Important Tool: `connectionStatus`

MongoDB provides a command that describes the identity and effective privileges on the **current connection**:

~~~javascript
db.runCommand({
  connectionStatus: 1,
  showPrivileges: true
});
~~~

Example output:

~~~javascript
{
  authInfo: {
    authenticatedUsers: [
      { user: "orders_reader", db: "authz_lab" }
    ],
    authenticatedUserRoles: [
      { role: "read", db: "authz_lab" }
    ],
    authenticatedUserPrivileges: [
      // Actual actions on corresponding resources
    ]
  },
  ok: 1
}
~~~

### 15.1. Three Important Fields

- `authenticatedUsers`: which principal authenticated.
- `authenticatedUserRoles`: which roles are assigned.
- `authenticatedUserPrivileges`: the effective privilege set when `showPrivileges:true`.

### 15.2. Use the Exact Connection Under Investigation

If `mongosh` is logged in as admin, this command returns the admin's permissions, **not** those of the `MongoClient` used by `orders-api`. Test on the application's connection or a canary client using the same principal.

### 15.3. Print Only the Needed Fields

~~~javascript
const result = db.runCommand({
  connectionStatus: 1,
  showPrivileges: true
});

printjson({
  users: result.authInfo.authenticatedUsers,
  roles: result.authInfo.authenticatedUserRoles,
  privileges: result.authInfo.authenticatedUserPrivileges
});
~~~

Privilege/namespace details are still operational metadata requiring appropriate access permissions, even without passwords.

### 15.4. Not a Tool for Inspecting All Users

`connectionStatus` only reports on the current connection. For other users, ask a DBA to use `usersInfo`/`rolesInfo` or the Atlas Access UI with proper viewing rights.

## 16. Checking Users and Roles on Self-Managed Deployments

With valid admin privileges:

~~~javascript
use authz_lab

db.getUser("orders_reader", {
  showPrivileges: true
});
~~~

To view roles:

~~~javascript
db.getRoles({
  showPrivileges: true
});
~~~

Appropriate privileges are needed to view users/roles; do not grant `root` to an application just to run diagnostics.

### 16.1. Comparing Effective Privileges Against the Failing Command

Example:

~~~text
Operation: insertOne
Namespace: authz_lab.orders
Principal: orders_reader@authz_lab

Available: find on authz_lab
Missing: insert on authz_lab.orders

Conclusion: Authorization error, code 13.
~~~

### 16.2. Permission Cache and Propagation Timing

Role changes may not become visible to all clients/mongos/servers simultaneously due to caching and connection lifecycles. After a change, test with a new connection and monitor before closing the incident; do not assume instant role propagation.

### 16.3. Do Not Change Roles Without Approval

Granting/revoking is a security change. Record who, which role, which resource, purpose, timestamp, result, and rollback plan.

## 17. Self-Managed Lab: Enable Authorization First

The hands-on exercises use a **self-managed MongoDB in an isolated lab environment**. Do not run the lab's `createUser`/`createRole` commands on production Atlas.

Prerequisites:

- MongoDB has `security.authorization: enabled`.
- An admin user with user-management privileges exists.
- Test data contains no PII.
- If connecting over a network, use TLS.
- Two or more `mongosh` sessions are available to separate admin and low-privilege users.

### 17.1. Why Use a Separate Session?

MongoDB docs note that `db.auth()` does not act like a "switch user" button that clears every previous identity in the same `mongosh` connection. An admin session may retain admin privileges when you try logging in as `reader`.

To test `reader` permissions, **exit the admin shell completely and open a new shell** as `reader`.

### 17.2. Preparing the Test Database

Log in as admin in the lab:

~~~javascript
use authz_lab

db.createCollection("orders");

db.orders.insertMany([
  {
    _id: "order-001",
    status: "PENDING",
    amount: 100
  },
  {
    _id: "order-002",
    status: "CONFIRMED",
    amount: 250
  }
]);
~~~

Create the collection beforehand so `NamespaceNotFound` is not confused with a permission error.

## 18. Lab: Creating a Read-Only User

In the admin session:

~~~javascript
use authz_lab

db.createUser({
  user: "orders_reader",
  pwd: passwordPrompt(),
  roles: [
    { role: "read", db: "authz_lab" }
  ],
  mechanisms: ["SCRAM-SHA-256"]
});
~~~

`passwordPrompt()` prompts for a password without placing plaintext into command history. TLS is still needed if credentials traverse a network.

### 18.1. Creating a Writer

~~~javascript
db.createUser({
  user: "orders_writer",
  pwd: passwordPrompt(),
  roles: [
    { role: "readWrite", db: "authz_lab" }
  ],
  mechanisms: ["SCRAM-SHA-256"]
});
~~~

### 18.2. Do Not Use a Real Password

Credentials are for lab use only; do not copy production secrets or upload config files containing secrets to a repository.

### 18.3. If the User Already Exists

`db.createUser()` may report a duplicate user. Do not automatically drop the user and retry on a database you are not sure is the lab; verify the namespace and owner.

## 19. Lab: Testing `AuthenticationFailed`

Close the admin `mongosh` and open a new terminal. Example for a local MongoDB lab:

~~~bash
mongosh "mongodb://127.0.0.1:27017/authz_lab" \
  --username orders_reader \
  --authenticationDatabase authz_lab \
  --password
~~~

The terminal prompts for a password.

### 19.1. Entering the Wrong Password

Expect an error at the authentication stage:

~~~text
AuthenticationFailed (18)
~~~

### 19.2. Entering the Right Password with the Wrong `authSource`

If the user was created in `authz_lab` yet the CLI runs:

~~~bash
mongosh "mongodb://127.0.0.1:27017/authz_lab" \
  --username orders_reader \
  --authenticationDatabase admin \
  --password
~~~

you may receive `AuthenticationFailed` because MongoDB looks for the user in the wrong database.

### 19.3. Do Not Confuse Local Lab Errors with Production

If the local `mongod` does not have authorization enabled, the test may not produce the expected signal. If no MongoDB process is running, you get connection refused; that does not test authentication.

## 20. Lab: Testing `Unauthorized`

Open a new `mongosh` session with `orders_reader` and the right password:

~~~javascript
db.runCommand({
  connectionStatus: 1,
  showPrivileges: true
});
~~~

Read command:

~~~javascript
db.orders.findOne({
  _id: "order-001"
});
~~~

Expected to return the document.

Write command:

~~~javascript
db.orders.insertOne({
  _id: "order-003",
  status: "PENDING",
  amount: 400
});
~~~

Expected:

~~~text
MongoServerError: not authorized on authz_lab
to execute command ...
code: 13
codeName: Unauthorized
~~~

### 20.1. Why Doesn't the Password Need Changing?

Because `findOne` executed successfully under the `reader` principal. If `insertOne` is rejected, what needs checking is the `insert` action on the collection.

### 20.2. Do Not Immediately Grant `readWrite`

In the lab, you can test `orders_writer` to observe a different role. In production, however, if only `insert` on a single collection is required, a narrow custom role is usually better than granting `readWrite` on the entire database.

### 20.3. Expectation Matrix

| Credential | Command | Result |
|---|---|---|
| Reader, right password | Login | Success |
| Reader, wrong password | Login | Code 18 |
| Reader, right password, wrong authSource | Login | Code 18 or appropriate config error |
| Reader | `findOne(orders)` | Success |
| Reader | `insertOne(orders)` | Code 13 |
| Writer | `insertOne(orders)` | Success |
| Writer | `find` on another database without role | Code 13 |

## 21. Lab: Creating a Custom Role with Only `find` and `insert`

Log back in with a separate admin session:

~~~javascript
use authz_lab

db.createRole({
  role: "ordersInserter",
  privileges: [
    {
      resource: {
        db: "authz_lab",
        collection: "orders"
      },
      actions: ["find", "insert"]
    }
  ],
  roles: []
});

db.createUser({
  user: "orders_ingest",
  pwd: passwordPrompt(),
  roles: [
    { role: "ordersInserter", db: "authz_lab" }
  ]
});
~~~

### 21.1. Positive Tests

Log in as `orders_ingest` in a separate shell:

~~~javascript
db.orders.findOne({ _id: "order-001" });

db.orders.insertOne({
  _id: "order-ingest-001",
  status: "CREATED"
});
~~~

Both operations are valid per the role.

### 21.2. Negative Tests

~~~javascript
db.orders.updateOne(
  { _id: "order-ingest-001" },
  { $set: { status: "UPDATED" } }
);
~~~

Expected code 13 because `update` is absent.

~~~javascript
db.secret_records.findOne({});
~~~

Expected code 13 because the custom role lacks `find` on this collection.

### 21.3. The Value of Negative Tests

Security testing proves not only "what is needed can be done," but also "what is forbidden cannot be done." That helps detect privilege creep.

## 22. Granting Permissions on the Right Resource

Suppose an app user was granted `readWrite` on `orders_dev`:

~~~text
User: app_writer@admin
Role: readWrite on orders_dev

Request: insert orders_prod.orders
Result: Unauthorized (13)
~~~

### 22.1. Do Not Change `authSource` to Fix a Resource Error

If the app already authenticates in `admin`, switching `authSource` to `orders_prod` can break authentication. You need a role/privilege on the right resource, not a changed identity.

### 22.2. Roles Can Be Assigned from `admin`

A user created in `admin` can be assigned the `readWrite` role on `orders_prod`. During investigation, inspect the identity database and the role resource database separately.

### 22.3. Approved Permission Changes

If a DBA decides to grant an additional privilege in the lab:

~~~javascript
use authz_lab

db.grantRolesToUser("orders_reader", [
  { role: "readWrite", db: "authz_lab" }
]);
~~~

This example teaches syntax and is **not a production recommendation**, because `readWrite` is much broader than many needs.

### 22.4. Re-Test with a New Connection

After a role change, use a new `mongosh` session to log in as the exact principal and test the actual operation. Do not merely look at the `grant` command returning `ok:1`.

## 23. Command-Specific Privileges

You cannot infer command permissions from the collection name alone; you must check the operation type.

| Command | Typical action |
|---|---|
| `find` | `find` |
| `insertOne`/`insertMany` | `insert` |
| `updateOne`/`replaceOne` | `update` |
| `deleteOne`/`deleteMany` | `remove` |
| `createIndex` | `createIndex` |
| `dropIndex` | `dropIndex` |
| `listIndexes` | `listIndexes` |
| `listCollections` | `listCollections` with documented exceptions |
| `aggregate` | Depends on stages/namespaces |
| `watch` | `find` and `changeStream` by scope |
| `serverStatus` | Monitoring privileges |
| `usersInfo`/`rolesInfo` | View users/roles by scope |
| `createUser` | `createUser` and role-granting privileges |
| Backup/restore | Appropriate backup/restore actions/roles |

### 23.1. Aggregations May Need Permissions on Foreign Collections

~~~javascript
db.orders.aggregate([
  {
    $lookup: {
      from: "customers",
      localField: "customerId",
      foreignField: "_id",
      as: "customer"
    }
  }
]);
~~~

If the user has `find` on `orders` but lacks it on `customers`, the pipeline can fail with code 13. Inspect all namespaces touched by the pipeline.

### 23.2. `$out` and `$merge`

These aggregation stages can write data to a target collection. They require privileges matching the stage, not just `find` on the source collection.

### 23.3. `listCollections` Has Exceptions

MongoDB supports certain `listCollections` cases with `authorizedCollections:true` and `nameOnly:true` for users lacking database-wide `listCollections` yet holding permissions on specific collections. Do not generalize this exception to all metadata commands.

### 23.4. Index Migrations and Server Administration

A business service with CRUD permissions should not perform user management, cluster reconfiguration, or out-of-scope migrations. Separate the runtime identity from the migration identity.

## 24. Change Streams: Requires Separate Privileges

An app may succeed calling `find` on `orders`, yet `watch()` receives code 13 if the custom role lacks `changeStream`.

~~~javascript
db.orders.watch();
~~~

### 24.1. Scope Changes Required Permissions

- Collection-level change stream.
- Database-level change stream.
- Deployment-wide change stream.

A role with only `find` on collection `orders` does not necessarily allow watching the entire deployment.

### 24.2. Built-In `read` Roles

MongoDB built-in `read` roles generally include the permissions needed to use change streams within their scope. Custom roles require checking exact actions.

### 24.3. Consumers with Checkpoints

A consumer may need `find` + `changeStream` on the source, as well as `find`/`insert`/`update` on a checkpoint collection. Do not grant `readWriteAnyDatabase` merely because checkpoints reside in another database.

### 24.4. Not Every Stream Error Is Code 13

Invalidate events, expired resume tokens, primary elections, network errors, or TLS issues can also interrupt a change stream. Classify by error code and event semantics.

## 25. Transactions Do Not Bypass Authorization

A Spring `@Transactional` service:

~~~text
Transaction:
  update orders.orders
  insert orders.outbox
~~~

If the principal has `update` on `orders` but lacks `insert` on `outbox`, the transaction can fail and abort.

### 25.1. `@Transactional` Does Not Grant Permissions

The annotation establishes a transaction boundary via `MongoTransactionManager`; it cannot turn a database user into `root`.

### 25.2. Multiple `MongoClient` Instances May Have Different Principals

If Services A and B use two different `MongoDatabaseFactory`/`MongoClient` beans, they may carry different credentials/roles even when pointing to the same cluster. Check wiring, not just the database URI hostname.

### 25.3. Errors Must Not Be Swallowed

If a transaction encounters `MongoCommandException(13)`, rollback/propagation must be handled properly. Catching and ignoring it can cause application logic to falsely report success.

## 26. Metadata, Backup, and Monitoring

### 26.1. `serverStatus`

`serverStatus` is a monitoring command, not a business read. An app principal with `read` on `orders` may lack sufficient privileges.

### 26.2. `createIndexes`

Spring Data MongoDB or migration scripts may invoke `createIndexes`. CRUD still works, yet startup fails when the principal lacks index creation rights or uses a narrow custom role.

### 26.3. `usersInfo`

An app user is not necessarily allowed to inspect other users/roles. Do not grant user administration rights just to run diagnostics.

### 26.4. Backup and Restore

Backup/restore require distinct operations/privileges. A principal with the `backup` role does not automatically have `restore` permissions, and vice versa.

### 26.5. Separating Identities

~~~text
orders-api        -> business CRUD
orders-indexer    -> changeStream/find/checkpoint
db-migrator       -> DDL/index changes per release
monitoring-agent  -> monitoring privileges
backup-agent      -> backup privileges
security-admin    -> user/role management
~~~

Such separation reduces the blast radius and quickly pinpoints the source of code 13 errors.

## 27. Java Sync Driver: Classification Principles

In a Java application, MongoDB errors may be:

- `MongoSecurityException`.
- `MongoCommandException`.
- General `MongoException`.
- `MongoTimeoutException`, `MongoSocketException`, or TLS/network causes.
- Spring `DataAccessException` wrapping at a higher layer.

### 27.1. Do Not Rely on Message Substrings

Instead of:

~~~java
if (error.getMessage().contains("auth")) {
    // Too broad and unreliable.
}
~~~

prioritize server error codes and the cause chain.

### 27.2. Sample Classifier

~~~java
import com.mongodb.MongoCommandException;
import com.mongodb.MongoException;
import com.mongodb.MongoSecurityException;

import javax.net.ssl.SSLHandshakeException;
import java.net.UnknownHostException;

public final class MongoFailureClassifier {

    public enum Kind {
        AUTHENTICATION,
        AUTHORIZATION,
        TLS,
        DNS,
        OTHER
    }

    public static Kind classify(Throwable failure) {
        for (Throwable current = failure;
             current != null;
             current = current.getCause()) {

            if (current instanceof MongoCommandException cmd) {
                if (cmd.getErrorCode() == 18) {
                    return Kind.AUTHENTICATION;
                }
                if (cmd.getErrorCode() == 13) {
                    return Kind.AUTHORIZATION;
                }
            }

            if (current instanceof MongoException mongo) {
                if (mongo.getCode() == 18) {
                    return Kind.AUTHENTICATION;
                }
                if (mongo.getCode() == 13) {
                    return Kind.AUTHORIZATION;
                }
                if (current instanceof MongoSecurityException) {
                    return Kind.AUTHENTICATION;
                }
            }

            if (current instanceof SSLHandshakeException) {
                return Kind.TLS;
            }
            if (current instanceof UnknownHostException) {
                return Kind.DNS;
            }
        }

        return Kind.OTHER;
    }
}
~~~

This is an illustrative classifier for Java supporting pattern-matching `instanceof`. It does not replace full error handling because network/driver errors take many forms. With `MongoSecurityException`, you still must check the exact cause and auth mechanism.

### 27.3. Do Not Print Raw Exception Messages Arbitrarily

Driver exceptions may contain sensitive hostnames/URIs/metadata. Only log sanitized category, operation, principal reference, trace ID, and error code when available.

## 28. Java: Performing a Safe Permission Probe

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

public final class ReadOnlyPermissionProbe {

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");

        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException(
                "Missing MONGODB_URI");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> orders =
                client.getDatabase("authz_lab")
                      .getCollection("orders");

            Document one = orders.find(
                new Document("_id", "order-001")
            ).first();

            System.out.println("Read operation completed; found="
                + (one != null));
        }
    }
}
~~~

### 28.1. `MongoClients.create` Does Not Confirm Login

The Java Driver typically establishes connections when executing an operation. Creating `MongoClient` alone is not sufficient proof that SCRAM/TLS succeeded.

### 28.2. `ping` Does Not Verify CRUD Rights

`db.adminCommand({ping:1})` is useful for checking connectivity, but it does not prove `insert` on `orders.orders` is permitted.

### 28.3. Do Not Blindly Insert into Production Data

If write permissions must be tested, use a dedicated canary fixture/collection and an approved cleanup policy to avoid side effects or synthetic data leaking into billing.

## 29. Spring Data MongoDB: Translated Exceptions

Spring Data MongoDB can translate driver exceptions into `DataAccessException` subclasses. When a repository fails, the top-level exception is not necessarily `MongoCommandException`.

### 29.1. Finding the Root Cause

~~~java
import org.springframework.dao.DataAccessException;
import org.springframework.stereotype.Service;

@Service
public class OrderLookupService {

    private final OrderRepository orders;

    public OrderLookupService(OrderRepository orders) {
        this.orders = orders;
    }

    public Order load(String id) {
        try {
            return orders.findById(id).orElseThrow();
        } catch (DataAccessException e) {
            MongoFailureClassifier.Kind category =
                MongoFailureClassifier.classify(e);

            recordFailure(category, "find-order");
            throw e;
        }
    }

    private void recordFailure(
        MongoFailureClassifier.Kind category, String operation) {
        // Metric/tracing hook; do not log documents/URIs.
    }
}
~~~

`Order` and `OrderRepository` are application domain types, not classes built into the Java Driver.

### 29.2. `@Transactional` Does Not Fix Roles

The transaction interceptor manages commit/abort; if the principal lacks `insert` on a collection, the role is still missing. Test business operations through the exact repository and principal.

### 29.3. Multiple Database Factories

Two repositories in the same app can use two `MongoClient` instances carrying different identities. When only one repository reports code 13, check bean wiring and the effective database name.

## 30. Spring Boot Version and URI Configuration

For Spring Boot 3.5:

~~~yaml
spring:
  data:
    mongodb:
      uri: "${MONGODB_URI}"
~~~

For Spring Boot 4.x:

~~~yaml
spring:
  mongodb:
    uri: "${MONGODB_URI}"
~~~

Check the Spring Boot properties metadata for your exact version and verify the active profile.

### 30.1. App Connecting to the Wrong Place

An app running Boot 4.x while keeping Boot 3.x property keys may not pick up the intended URI; the error may be connection refused/timeout or logging in with the wrong user on a different cluster.

### 30.2. Property Source Precedence

Environment variables, command-line args, external config, configtree, and application profiles can override each other. Do not grep a single YAML file and assume the runtime uses that URI.

### 30.3. Do Not Expose Actuator `env`/`configprops` Publicly

These endpoints risk leaking config metadata and secrets. Inspect effective config through secured, redacted diagnostics rather than dumping the entire environment into an incident ticket.

## 31. Secret Rotation: When Does Code 18 Appear Intermittently?

~~~text
T0: orders_api_v1 + password v1
    12 Pods running

T1: Server password switches to v2
    Secret Manager has v2

T2: 5 Pods restarted with secret v2
    7 Pods still hold client/pool v1

T3: Old Pods need to open a new connection
    -> AuthenticationFailed(18)
~~~

### 31.1. Existing Pooled Connections Can Mask Errors

A connection authenticated before rotation may continue working for some time. Only new connections expose the stale secret. Rotation testing must open a **new `MongoClient`/TLS/SCRAM connection**.

### 31.2. Dual-Account Pattern

~~~text
Provision app_user_v2 with approved roles
            |
Stage secret v2
            |
Canary new MongoClient
            |
Business read/write permission tests
            |
Rollout all Pods/workers
            |
Confirm no consumers using v1
            |
Revoke app_user_v1
~~~

### 31.3. Role Parity Is the Real Trap

If user v2 is created with the right password yet lacks v1's custom role:

~~~text
Authentication PASS
find PASS
insert Unauthorized(13)
~~~

Do not reset v2's password; review approved roles/actions and run permission smoke tests before continuing rollout.

### 31.4. Secret Compromise Differs from Scheduled Rotation

If v1 is compromised, do not keep v1 around indefinitely for rollback convenience. Follow the security incident process: revoke, rotate, and monitor for abuse.

## 32. Atlas: Distinguishing User Access from Database Access

In Atlas, you must distinguish:

- **Project/Organization access**: who administers the project.
- **Database users**: which principals can authenticate to `mongod`/`mongos`.
- **Database roles/specific privileges**: what they may do with data.
- **Network Access**: whether the application can reach the cluster.

### 32.1. Project Owner Does Not Replace a Database User

Successfully logging into the Atlas web UI does not mean an app can use that same email/password as SCRAM credentials.

### 32.2. Atlas Users Are Managed via the Proper UI/API

Modify database users and custom roles via the Atlas UI, Atlas CLI, Atlas Administration API, or supported integrations—not with `db.createUser` inside an Atlas cluster.

### 32.3. Restrict Access to Specific Clusters

A DB user may exist in a project yet only be authorized on selected clusters. When auth fails on a new cluster, check restrictions, username/credentials, and project.

### 32.4. Temporary Database Users

Atlas supports temporary database users with an expiration time. When expired, do not assume someone changed the password; check user lifecycle and the approved access window.

## 33. Case Study A: Read-Only Service Now Needs Writes

### Symptoms

`orders-api` ran for months with only GET endpoints; today a new POST endpoint to create orders was released. POST fails with `Unauthorized(13)`, while GET still succeeds.

### Investigation

- Exact action: `insert`.
- Exact namespace: `orders.orders`.
- `connectionStatus`: authenticated principal is still correct.
- Role: `read` on `orders`.
- Change timeline: new POST endpoint released.

### Remediation

Design a write policy for the service, approve the `insert` privilege on the needed collection, or separate a write service principal if appropriate. Test both GET/POST with canary data.

### What Not to Do

Change the password, disable auth, or grant `root`.

## 34. Case Study B: MongoDB Query with `$lookup`

### Symptoms

`find` on `orders` succeeds; a new aggregation with `$lookup` from `customers` fails with code 13.

### Investigation

The pipeline touches both `orders` and `customers`. The user has `find` on the source collection, but not necessarily `find` on the foreign collection.

### Remediation

If the business requirement is valid, grant read privileges on the foreign collection with approval. Do not grant `readWrite` across the whole database when only `find` is needed.

### Verification

Run the actual pipeline with the newly authorized principal, not just `ping` or `find` on the source alone.

## 35. Case Study C: After Deploy, Spring Index Creation Fails

### Symptoms

Application context startup fails during `createIndexes`. The user can read/write data if CRUD is invoked directly.

### Root Cause

The runtime user only holds data privileges, while the application tries to create indexes automatically or uses a custom role missing `createIndex`.

### Remediation

Move schema/index migrations to a pipeline and principal with the right permissions, rather than granting permanent admin rights to the application.

### Verification

Indexes are created per plan, the app runtime continues running with least privileges, and startup does not execute out-of-scope migrations.

## 36. Case Study D: Atlas User Sees Cluster, Yet App Cannot Log In

### Symptoms

A staff member has Project Owner in the Atlas UI; the Java Driver receives `AuthenticationFailed(18)`.

### Investigation

Has a database user been created for the Java app? Are the authentication mechanism, `authSource`, secret version, project/cluster restrictions, and URI correct?

### Remediation

Use a dedicated database principal; do not put Atlas web credentials into the URI.

### Verification

A new `MongoClient` authenticates and passes permission smoke tests on the target database/collection.

## 37. Case Study E: One Pod Still Uses Old Password

### Symptoms

Authentication failure rates spike only when the autoscaler spins up new Pods or when the connection pool opens additional sockets.

### Investigation

Compare secret references/versions per Pod, app release, Kubernetes ConfigTree/environment, and `MongoClient` lifecycle.

### Remediation

Complete the rollout of the new secret and proper permissions, and test with canary new connections; do not modify roles if the server code is 18.

### Verification

Auth error rate returns to baseline across all Pods; write operations succeed; no old consumer still uses v1.

## 38. Case Study F: Monitoring Agent Cannot Read `serverStatus`

### Symptoms

Application business queries are normal. The monitoring exporter reports code 13 on `serverStatus`.

### Root Cause

The exporter is using a business user with only read/CRUD rights and lacks monitoring privileges.

### Remediation

Create a monitoring principal with the appropriate role/actions, separate from the app user. Test the commands the exporter actually requires.

### Verification

The exporter is healthy, metrics recover, and the business database user's privileges remain unchanged.

## 39. Standard Runbook for `AuthenticationFailed(18)`

1. Confirm MongoDB server returned code 18 rather than a TCP/TLS error.
2. Identify the expected principal and auth mechanism.
3. Verify the database containing the user and `authSource`.
4. Check the secret source/version, percent-encoding, and config precedence.
5. Review recent changes: rotation, deleted user, project change.
6. Test a new connection/canary with credentials via a secure channel.
7. If credentials were compromised, use security incident rotation rather than blind rollback.
8. Verify actual business operations after authentication succeeds.
9. Monitor error rates and retry/connection churn.
10. Save the redacted timeline, actions, and evidence.

### 39.1. Stop Condition

If signs of brute force/credential leakage appear, coordinate with Security instead of merely increasing retries or accidentally locking out all accounts.

## 40. Standard Runbook for `Unauthorized(13)`

1. Capture the rejected command and namespace.
2. Confirm the user authenticated and the connection uses the intended principal.
3. Run `connectionStatus(showPrivileges:true)` on the current principal.
4. Determine the exact action required by the command.
5. Check the resource scope: database/collection/cluster.
6. Check custom role inheritance, Atlas restrictions, and app profile.
7. Review the release/DDL/role change timeline.
8. Grant only the minimum approved privilege or fix the code/target DB.
9. Test the exact command on a canary fixture.
10. Run negative permission tests to ensure no over-granting occurred.
11. Record audit trail, owner, and expiration if privileges are temporary.
12. Monitor the Unauthorized rate and service SLO after the change.

### 40.1. Do Not Reflexively Change Passwords for Code 13

Code 13 is evidence to check authorization. If code 18 appears at the same time, investigate each separately rather than merging them into one cause.

## 41. Sample Incident Evidence

~~~yaml
incidentId: INC-2026-11-14-DB-AUTH
service: orders-api
environment: production
firstObservedUtc: 2026-11-14T06:15:00Z
operation: insertOne
namespace: orders.outbox
errorCode: 13
errorCodeName: Unauthorized
databasePrincipal: orders_api_v2
authDatabase: admin
mechanism: SCRAM-SHA-256
secretReference: secret-version-id-not-the-value
changeReference: CHG-2026-0442
hypothesis: missing-insert-privilege
observedImpact: writes-fail-for-new-pods
status: investigating
~~~

This is illustrative incident YAML, not a MongoDB configuration. Never store passwords, real URIs, or raw customer documents.

### 41.1. Example Timeline

~~~text
06:10Z  orders_api_v2 provisioned
06:12Z  Canary rollout
06:15Z  INSERT errors code 13
06:17Z  READ calls pass with same principal
06:20Z  Effective privileges lack insert on outbox
06:25Z  Approved role fix
06:29Z  New connection + canary write PASS
06:35Z  Error rate back to baseline
~~~

### 41.2. Observation vs. Hypothesis

- Observation: Server returned code 13 for `insertOne`.
- Hypothesis: user v2 lacks `insert`.
- Evidence: effective privileges lack `insert` on the target resource.
- Mitigation: grant a narrow privilege or fix role provisioning.
- Root cause: credential rotation workflow did not verify role parity.
- Prevention: positive/negative permission smoke tests.

## 42. Logs, Alerts, and Information Security

Fields safe to log:

- Error category/code/codeName.
- Operation name.
- Namespace if allowed by policy.
- Logical principal ID.
- Application release/Pod ID.
- Secret version **reference**, not the value.
- Trace ID and UTC timestamp.
- Relevant change/incident ID.

Do not log:

- Full connection URI containing passwords.
- Private keys, JWT/IdP tokens, SCRAM secrets.
- Full documents or query filters containing PII.
- Full `process.env` or Actuator `env` output.
- Raw stack traces sent to external notifications without redaction.

### 42.1. `AuthenticationFailed` Alert Spike

Could indicate a broken rollout or brute-force attempt. Segment metrics by logical principal/service, source network (if policy permits), environment, and rotation window.

### 42.2. `Unauthorized` Alert Spike

Could indicate a new release, role drift, or unauthorized access attempts. Correlate action/namespace, app version, and the change calendar.

### 42.3. Do Not Retry Indefinitely

A bad password or missing role is a configuration or security policy error and should not be retried indefinitely every millisecond; doing so creates log storms and connection pressure.

## 43. HTTP 401 and 403 Are Not MongoDB Codes 18 and 13

~~~text
End user -> API authentication & authorization
                      |
                      v
                Spring service
                      |
                      v
              MongoDB app identity
                      |
                      v
             MongoDB authN / authZ
~~~

- HTTP 401 typically refers to the **API caller's** credentials.
- HTTP 403 typically refers to the **API caller's** permissions.
- MongoDB codes 18 and 13 refer to the **application's database principal**.

If the backend app user lacks `insert`, returning HTTP 403 to every end user misleads them into thinking they are forbidden from placing orders. Applications usually need to handle this as a backend failure and log an incident per API error policy.

### 43.1. Tenant Authorization Is a Separate Layer

MongoDB `readWrite` on a collection does not automatically ensure a service only returns orders for the current tenant. The app must enforce its own tenant/user authorization and appropriate query filters.

## 44. Automated Positive and Negative Permission Testing

| Scenario | User | Operation | Expected |
|---|---|---|---|
| Valid login | reader | authenticate | PASS |
| Login wrong password | reader | authenticate | Code 18 |
| Login wrong authSource | reader | authenticate | Code 18 |
| Read data | reader | find orders | PASS |
| Write data | reader | insert orders | Code 13 |
| Read/write | writer | insert orders | PASS |
| Cross database | writer | find another DB | Code 13 |
| Narrow collection | orders_ingest | insert orders | PASS |
| Narrow action | orders_ingest | update orders | Code 13 |
| Create index | custom CRUD user | createIndex | Code 13 if action missing |
| Monitor | read-only user | serverStatus | Code 13 if privilege missing |
| Change stream | custom user | watch | Requires `changeStream`/`find` |
| Secret rotation | user v2 | CRUD canary | PASS if role parity holds |
| Wrong CA | test client | connect | TLS failure |
| Broken DNS | test runner | connect | Network/DNS failure |

### 44.1. Test Against Real MongoDB

Mocks help test classifiers, but they do not prove server RBAC. Use a MongoDB lab with authorization enabled to verify real credentials, roles, and commands.

### 44.2. Positive and Negative Tests

Do not only assert that `reader.find` succeeds. Also assert that `reader.insert` is rejected. If both PASS, the app may be using admin credentials or overly broad roles.

### 44.3. Do Not Use Production `root` in CI

CI should have dedicated test users, dedicated databases, and a cleanup policy. Do not call role management APIs in production to run negative tests.

### 44.4. Re-Test After Every Change

After role grant/revoke or rotation, create a new client/connection and test the exact business operation; a green cluster status does not prove app permissions.

## 45. Situation-Based Diagnosis

| Situation | Likely cause to check |
|---|---|
| Fails immediately at login | Username/password/authSource/mechanism |
| Fails when new Pods launch | Secret rotation/client lifecycle |
| `find` PASS, `insert` FAIL | Missing `insert` action |
| CRUD PASS, `createIndex` FAIL | Migration permission |
| CRUD PASS, `serverStatus` FAIL | Cluster-monitoring role |
| `find` PASS, aggregate lookup FAIL | Foreign collection `find` |
| `find` PASS, `watch` FAIL | `changeStream` privilege |
| App A PASS, App B FAIL | Different principal/MongoClient config |
| Atlas UI PASS, Java auth FAIL | Atlas user vs. DB user |
| Login PASS, operations on another DB FAIL | Wrong role scope |
| Same user, new role not yet effective | Propagation/cache/client lifecycle |
| Network timeout, no code 18 | DNS/network/topology |
| TLS exception, no code 13 | CA/SAN/truststore |
| Backend code 13, API returns 403 | Misclassified HTTP layer |

## 46. Production Checklist

### Authentication

- [ ] Each service/environment has its own principal.
- [ ] Mechanism matches server/driver.
- [ ] `authSource` matches where the user exists.
- [ ] URI credentials properly percent-encoded.
- [ ] Full TLS CA/hostname verification enabled.
- [ ] No hardcoded secrets/URIs in Git or images.
- [ ] Secret versions tracked by reference ID.
- [ ] New `MongoClient` tested after rotation.
- [ ] Revocation plan exists for compromised credentials.
- [ ] DNS/Atlas network access managed securely.

### Authorization

- [ ] Permission matrix exists per service.
- [ ] Role/action/resource scopes are accurate.
- [ ] `root` is never granted to business runtime.
- [ ] Migration/backup/monitoring identities are separated.
- [ ] Atlas users and DB users managed in their proper systems.
- [ ] Inherited/effective privileges audited.
- [ ] Both positive and negative tests exist.
- [ ] Role grants are formally approved.
- [ ] Temporary privileges have revocation deadlines.
- [ ] Tenant/user authorization enforced at the app layer.

### Troubleshooting

- [ ] Log error codes 13/18 and exact operation.
- [ ] Do not lump network/TLS/timeouts into authentication.
- [ ] `connectionStatus` inspected under the exact principal.
- [ ] Do not test permissions in a shell retaining an admin identity.
- [ ] Do not print full URIs/credentials/PII.
- [ ] Runbooks exist for rotation and RBAC drift.
- [ ] Alerts configured for auth failures and unauthorized activity.
- [ ] Incidents include timeline, owner, and change references.
- [ ] Canary permission smoke tests run after mitigation.
- [ ] Do not close incidents solely because `ping` succeeded.

## 47. Practice Exercises

Only run exercises involving users/roles/secrets or writing data on a **lab** MongoDB instance with authorization enabled.

### Exercise 1 — Two Definitions

Distinguish authentication from authorization. Can a user with the right password but empty roles log in?

### Exercise 2 — Error Codes

Explain codes 18 and 13. Why shouldn't classification rely solely on the substring "auth" in the error message?

### Exercise 3 — Diagnostic Layers

Order DNS, TCP, TLS, authentication, authorization, and query execution.

### Exercise 4 — `authSource`

The user is created in `admin`, and the app DB is `orders`. Which `authSource` does the URI need?

### Exercise 5 — Wrong `authSource`

The user exists in `orders`, yet `authSource=admin`. What error can occur?

### Exercise 6 — URI Encoding

A password contains `@` and `#`. How do you prevent misparsing and secret exposure?

### Exercise 7 — Atlas SRV

A Pod cannot resolve the hostname in an SRV URI. Can you conclude the password is wrong?

### Exercise 8 — TLS

Java reports `PKIX path building failed`. Is this MongoDB authentication or certificate trust?

### Exercise 9 — X.509

TLS handshake PASS, X.509 user mapping FAIL. Are these two steps the same?

### Exercise 10 — OIDC/IAM

The token is valid, yet the user lacks `find`. What kind of error is this?

### Exercise 11 — `connectionStatus`

Explain `authenticatedUsers`, `authenticatedUserRoles`, and `authenticatedUserPrivileges`.

### Exercise 12 — Admin Session

Why shouldn't you call `db.auth(reader)` in an existing admin `mongosh` session and use the result to test `reader` permissions?

### Exercise 13 — `read` Role

Create `reader`, test `findOne` and `insertOne`. What is expected for each command?

### Exercise 14 — `readWrite` Role

A user has the `readWrite` role on `dev`. Can it automatically write to `prod`?

### Exercise 15 — `dbAdmin`

Why should the `dbAdmin` role not be treated as a business `readWrite` role?

### Exercise 16 — Custom Role

Create a role with `find` + `insert` on `orders`, without `update`. Design negative tests.

### Exercise 17 — Role Inheritance

A role can inherit another role. How do you check effective privileges?

### Exercise 18 — Atlas UI

Can a Project Owner directly use their Atlas email/password as a MongoDB SCRAM login?

### Exercise 19 — Atlas Cluster Restriction

Can a database user be restricted to only a subset of clusters?

### Exercise 20 — Aggregation

A pipeline with `$lookup` on foreign collection `customers` fails with code 13. What should you inspect?

### Exercise 21 — Index

Spring Data startup `createIndexes` fails with code 13. Should you reset the password?

### Exercise 22 — Change Streams

A user has `find`, yet `watch` fails with code 13. Which action might still be missing?

### Exercise 23 — Transactions

A transaction updates `orders` then inserts into `outbox`. Missing `insert` on `outbox` leads to what?

### Exercise 24 — Backup

A backup agent authenticates successfully, yet metadata/oplog operations fail. Which role should you inspect?

### Exercise 25 — Monitoring

A business read user fails `serverStatus` with Unauthorized. Design a monitoring account.

### Exercise 26 — Spring Boot

Compare the MongoDB property prefixes of Boot 3.5 and 4.x.

### Exercise 27 — Lazy Connection

`MongoClients.create(uri)` runs without throwing an error. Is SCRAM guaranteed to have passed?

### Exercise 28 — Java Classifier

Write code classifying `MongoCommandException.getErrorCode()` into `AUTHENTICATION`/`AUTHORIZATION`.

### Exercise 29 — Spring Data Cause Chain

A repository throws `DataAccessException`. How do you find the underlying `MongoException`?

### Exercise 30 — Password Rotation

After rotation, only a few Pods receive code 18. How do you inspect secret versions and new connections?

### Exercise 31 — Role Parity

Canary user v2 login PASS, yet `insert` FAIL. Why won't changing the password solve it?

### Exercise 32 — HTTP Mapping

If the backend lacks a DB `insert` privilege, should it return HTTP 403 to the end user?

### Exercise 33 — Data Privacy

Which fields should be logged in an incident alert, and which fields must be redacted?

### Exercise 34 — Permission Matrix

Design permissions for `orders-api`, `order-indexer`, `migrator`, and `backup-agent`.

### Exercise 35 — Negative Tests

Why must you assert that `reader` cannot write, in addition to asserting that `reader` can read?

### Exercise 36 — Two Faults

A service has both server selection timeouts and code 18 across different Pods. Why shouldn't you merge them into one root cause?

### Exercise 37 — Brute Force

`AuthenticationFailed` spikes from an unfamiliar IP. Distinguish a secret rollout bug from malicious attempts.

### Exercise 38 — Role Propagation

A DBA just granted a role, yet an old Pod still reports code 13. How will you check client/session/cache/rollout?

### Exercise 39 — Tenant Isolation

Does a MongoDB `readWrite` role on `orders` automatically isolate `tenantId`? What must the app do?

### Exercise 40 — Incident RCA

Write an RCA for a case where user v2 authenticates after rotation yet `insert` on `orders.outbox` fails with code 13: trigger, impact, evidence, fix, and prevention.

## 48. Summary

When MongoDB reports a security error, do not treat every case as a password problem:

1. **Authentication** answers *who is connecting*. Typical error: **18 — `AuthenticationFailed`**. Check principal, `authSource`, mechanism, credentials/token/certificate, secret version, and URI encoding.
2. **Authorization** answers *whether that principal is allowed to perform this action on this resource*. Typical error: **13 — `Unauthorized`**. Read effective privileges, command, namespace, and role scope.
3. **Network/TLS/topology** are separate layers. Do not change passwords or grant `root` before receiving a server authentication/authorization error.
4. **Atlas UI/project users differ from MongoDB database users**. Manage DB principals using Atlas-supported mechanisms.
5. **Java/Spring Data** involve wrapper exceptions; inspect error codes/cause chains rather than relying on log strings or `MongoClient` creation succeeding.
6. **Minimal, audited remediation**. Grant only approved actions/resources, test both positive and negative permissions, never disable TLS, and never expose secrets.
7. **Reliable operations** require canary new connections, role parity after rotation, monitoring, and runbooks for auth failures and Unauthorized incidents.

**Remember:** *Code 18 asks "Who are you?"; code 13 asks "Are you allowed to do this here?".*

## Official References

- [MongoDB Manual — Error Codes](https://www.mongodb.com/docs/manual/reference/error-codes/)
- [MongoDB Manual — connectionStatus](https://www.mongodb.com/docs/manual/reference/command/connectionStatus/)
- [MongoDB Manual — Authentication](https://www.mongodb.com/docs/manual/core/authentication/)
- [MongoDB Manual — Authorization](https://www.mongodb.com/docs/manual/core/authorization/)
- [MongoDB Manual — Built-In Roles](https://www.mongodb.com/docs/manual/reference/built-in-roles/)
- [MongoDB Manual — Privilege Actions](https://www.mongodb.com/docs/manual/reference/privilege-actions/)
- [MongoDB Manual — Create a User on Self-Managed Deployments](https://www.mongodb.com/docs/manual/tutorial/create-users/)
- [MongoDB Manual — db.createUser()](https://www.mongodb.com/docs/manual/reference/method/db.createUser/)
- [MongoDB Manual — db.createRole()](https://www.mongodb.com/docs/manual/reference/method/db.createRole/)
- [MongoDB Manual — db.getUser()](https://www.mongodb.com/docs/manual/reference/method/db.getUser/)
- [MongoDB Manual — listCollections](https://www.mongodb.com/docs/manual/reference/command/listCollections/)
- [MongoDB Atlas — Database Users](https://www.mongodb.com/docs/atlas/security-add-mongodb-users/)
- [MongoDB Atlas — Custom Database Roles](https://www.mongodb.com/docs/atlas/security-add-mongodb-roles/)
- [MongoDB Atlas — Organization and Project Access](https://www.mongodb.com/docs/atlas/organizations-projects/)
- [MongoDB Atlas — Atlas User Roles](https://www.mongodb.com/docs/atlas/reference/user-roles/)
- [MongoDB Java Sync Driver — Connection Troubleshooting](https://www.mongodb.com/docs/drivers/java/sync/current/connection/connection-troubleshooting/)
- [MongoDB Java Sync Driver — Authentication](https://www.mongodb.com/docs/drivers/java/sync/current/security/authentication/)
- [Spring Data MongoDB — Reference](https://docs.spring.io/spring-data/mongodb/reference/)
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html)
- [Spring Boot 4.0 — Common Application Properties](https://docs.spring.io/spring-boot/4.0/appendix/application-properties/index.html)
