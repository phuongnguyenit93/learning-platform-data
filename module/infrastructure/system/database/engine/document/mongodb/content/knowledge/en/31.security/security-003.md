# Users, Roles, and Least-Privilege Authorization in MongoDB

## 1. The Security Problem: One Service Should Not Have Every Privilege

Suppose a housing rental platform has four collections: **listings**, **owners**, **payments**, and **auditLogs**. An apartment search API only needs to read active listings. A listing management API needs to insert and update listings. A payment settlement worker needs to read payments and update a confirmed status. Operations staff need to observe cluster health.

If all four components share a single MongoDB account with the **root** role, a vulnerability in the search API can escalate into deleting transactions, modifying admin accounts, or destroying indexes. That is the reason behind the **principle of least privilege**:

> Each identity is granted only the actions it needs, on the exact resources, for the exact duration and scope required to do its job.

In MongoDB, a core mechanism for enforcing this principle is **Role-Based Access Control (RBAC)**:

~~~text
Application / Staff / Worker
              |
       AUTHENTICATION
       "Who are you?"
              |
              v
         DATABASE USER
              |
       Assigned ROLE(s)
              |
              v
      ROLE holds PRIVILEGE(s)
              |
      +-------+----------+
      |                  |
   RESOURCE            ACTION
 DB / collection    find/insert/
                    update/remove...
      |                  |
      +---------+--------+
                |
         AUTHORIZATION
     "Is this permitted?"
                |
         Allow / Deny
~~~

In this example, the user for the Search API should have the **find** action on **listings**; it does not need **insert**, **update**, **remove**, **createIndex**, **userAdmin**, or access to **payments**.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish **authentication** from **authorization**.
2. Understand **user**, **authentication database**, **role**, **privilege**, **resource**, and **action**.
3. Compare **built-in roles** with **custom roles**.
4. Build a least-privilege matrix for APIs, workers, analytics, CDC, monitoring, and migrations.
5. Create a role scoped to **one collection**, containing only the actions actually needed.
6. Create database users, connect with the right **authSource**, and inspect current permissions.
7. Distinguish login errors from **Unauthorized**.
8. Explain why MongoDB RBAC does not automatically filter documents by **tenantId**.
9. Handle credentials, TLS, rotation, auditing, granting/revoking privileges, and incidents.
10. Practice a safe `mongosh` lab with two roles, two users, and read/write tests.

> **Lab scope:** these commands for creating users and roles are intended for an **isolated self-managed MongoDB lab with authorization enabled**, executed by someone with administrative privileges. On **MongoDB Atlas**, managing database users and custom roles uses its own UI and API; do not assume every self-managed admin command runs on Atlas. Never use these privilege-granting examples on production or shared clusters.

## 2. Authentication and Authorization Are Two Separate Questions

### 2.1. Authentication: Verifying Identity

When a client connects, MongoDB can verify:

- Username and password via **SCRAM**.
- X.509 client certificates.
- Kerberos/LDAP in supported editions and deployments.
- OIDC/federated authentication in supported deployments.

Availability depends on **version, edition, and deployment type**. Authentication can succeed even if the user is not allowed to read any collection.

### 2.2. Authorization: Checking Operation Privileges

After authentication, MongoDB checks the command:

~~~text
User X runs find() on app.listings:
  has privilege find on app.listings?
    -> Yes: allow
    -> No: Unauthorized

User X runs deleteMany() on app.payments:
  has privilege remove on app.payments?
    -> Yes: allow
    -> No: Unauthorized
~~~

This is not only checked at login. Authorization applies to commands requiring privileges throughout the entire session.

### 2.3. Errors to Distinguish

| Symptom | Typical Meaning | What to Check |
| --- | --- | --- |
| **AuthenticationFailed** | Identity could not be verified | User, password, authSource, mechanism |
| **Unauthorized**, typically code 13 | Authenticated, but action not permitted | Roles, resource, inherited privileges |
| **Connection refused/timeout** | Cannot reach server | Host, port, DNS, firewall |
| **TLS handshake/certificate error** | Issue with TLS channel or server identity | CA, hostname, trust chain |
| **Command not found/unsupported** | Feature/version/deployment difference | MongoDB version and supported APIs |

**Never grant `root` to fix all errors.** Changing roles does not fix network or certificate issues; changing a password does not grant `find` permission.

### 2.4. Having Users Does Not Guarantee Authorization Is Enabled

A local MongoDB instance running without access control enabled can allow operations without requiring roles. Therefore, a `find` query succeeding on a dev machine does not prove you have tested RBAC.

Enabling authorization on a server is a dedicated administrative task: you must prepare an admin user, bootstrapping procedure, client cutover plan, TLS, and recovery path. This lesson does **not** perform or recommend changing `mongod` configuration mid-exercise.

## 3. A User Is an Identity, Not a Collection

### 3.1. Users and the Authentication Database

In MongoDB with internal database users, a user is created inside an **authentication database**.

Examples:

~~~text
admin.svc_search
mongo_security_lab_329.svc_search
~~~

These are two distinct identities even though they share the same username.

If you create:

~~~javascript
db.getSiblingDB("mongo_security_lab_329").createUser({
  user: "svc_search",
  pwd: passwordPrompt(),
  roles: []
});
~~~

then the user belongs to the **mongo_security_lab_329** authentication database. The client must authenticate against that database, such as via **authSource=mongo_security_lab_329**. If you create the user in **admin** and assign roles on the application database, `authSource` is typically **admin**.

### 3.2. A Username Does Not Represent Permissions

An account named **readonly** can still be assigned the **readWrite** role. An account named **service_admin** might only have `find` permission. A name is only a convention, not a security control.

To know real permissions, inspect assigned roles, privileges, and inherited permissions.

### 3.3. Separate Identities for Each Workload

Separate:

~~~text
svc_listing_search_prod
svc_listing_writer_prod
job_payment_report_prod
job_audit_append_prod
job_schema_migration_prod
ops_cluster_monitor
human_operator_...
~~~

Because each component has a different function and blast radius, they should never share a single user/password.

### 3.4. Human Identities Differ from Service Identities

Staff need individual accounts, with SSO/MFA or centralized management where supported for approvals and auditing. Services should have workload-issued credentials without staff manually typing passwords into code. CI/CD migrations should have a dedicated account with schema management privileges only for the required window.

## 4. Roles, Privileges, Resources, and Actions

### 4.1. A Specific Privilege

~~~javascript
{
  resource: {
    db: "mongo_security_lab_329",
    collection: "listings"
  },
  actions: ["find"]
}
~~~

This privilege permits **find** on the **listings** collection in the **mongo_security_lab_329** database. It does not allow inserting into `listings`, nor does it allow `find` on `payments`.

### 4.2. Broad vs. Narrow Resources

Resource scope types in MongoDB include:

- **A specific collection** within one database.
- **Collections within a database** per the applicable declaration rules.
- **Cluster-wide scope** for applicable administrative actions.

Custom roles in non-admin databases have restrictions on defining privileges across other databases or the cluster; if cross-database or cluster privileges are needed, follow server role-creation rules. **Never** use a cluster-scoped role when a task only needs one collection.

### 4.3. Representative Actions

| Action | Operation / Need |
| --- | --- |
| **find** | Read documents |
| **insert** | Insert documents |
| **update** | Modify documents |
| **remove** | Delete documents |
| **createIndex** | Create indexes |
| **listIndexes** | View index definitions |
| **createCollection** | Create collections |
| **dropCollection** | Drop collections |
| **listCollections** | View collection metadata |
| **collStats**, **dbStats** | View statistics |
| **changeStream** | Watch Change Streams within supported scope |
| **listDatabases** | List databases per permissions |

The RBAC action **remove** corresponds to delete operations such as `deleteOne`/`deleteMany`. **userAdmin** is the name of a built-in role, not an action that substitutes for individual user-management actions.

### 4.4. Multiple Roles Are a Union of Privileges

Suppose user U has:

~~~text
Role A: find on app.listings
Role B: insert/update on app.listings
Role C: readWrite on app
~~~

U's effective permissions are the union of privileges from **A, B, and C**. The narrow Role A does not restrict permissions granted by Role C.

This is a dangerous misconception: **standard MongoDB RBAC has no automatic “deny role” that overrides broader permissions from another role**. If a user already has `readWrite` on the entire database, adding a read-only role does not strip write access.

### 4.5. Role Inheritance

A custom role can inherit from another role:

~~~javascript
{
  role: "listingViewerPlus329",
  privileges: [],
  roles: [
    {
      role: "listingReader329",
      db: "mongo_security_lab_329"
    }
  ]
}
~~~

A user assigned `listingViewerPlus329` inherits privileges from `listingReader329`. Effective permissions must account for both **direct privileges** and **inherited privileges**. Modifying a parent role can affect all inheriting roles and users.

## 5. When to Use Built-In Roles?

### 5.1. Data Management Roles

| Built-In Role | General Meaning | Warning |
| --- | --- | --- |
| **read** | Read data in a database per role definition | Can be too broad if only one collection is needed |
| **readWrite** | Read/write and related operations in a database | Too broad for a read-only API |
| **dbAdmin** | Manage metadata, indexes, schemas, etc. on a database | Not a CRUD role or root |
| **userAdmin** | Manage users/roles within applicable scope | Privilege escalation risk |
| **dbOwner** | Combines data, database admin, and user admin groups | Do not grant to ordinary applications |

The exact actions in each built-in role are defined by MongoDB and can change across versions. When auditing, check the **server version documentation** or **rolesInfo** rather than guessing permissions from the role name.

### 5.2. Cluster and Operational Roles

| Role | Common Use Case |
| --- | --- |
| **clusterMonitor** | Observe cluster info/metrics |
| **clusterManager** | Certain cluster management tasks |
| **hostManager** | System/host management per server capabilities |
| **backup** | Backup operations supported by backup tools |
| **restore** | Restore operations |
| **root** | Very broad administrative privileges |

A monitoring agent does not need `restore` or `userAdmin` just to inspect CPU and replication. A backup job's credentials should never double as a web API's credentials.

### 5.3. readWrite Is Not Least Privilege for Every Write Workload

Database-wide `readWrite` is broader than **find, insert, and update on the `listings` collection**. If the database contains `payments` and `users`, the listing management API should not be permitted to write to those collections.

Create custom roles to restrict both **resources** and **actions**.

### 5.4. dbAdmin Differs from userAdmin

An index-creation job may need schema/index permissions. It does not need to manage passwords or grant roles. Conversely, an IAM admin needs to manage users/roles, not necessarily read transaction data.

Do not bundle all administrative needs into a single **dbOwner** account when duties can be separated.

### 5.5. Be Careful with userAdmin

The **userAdmin** role permits many user and role management operations within its scope. If it can assign broad privileges, it becomes a privilege escalation path. Accounts holding `userAdmin` must be governed as privileged accounts and never placed into web API environment variables.

## 6. Designing a Business-Driven Permission Matrix

| Component | Resource | Actions to Consider | Should Not Be Granted |
| --- | --- | --- | --- |
| **Listing Search API** | listings | find | insert, update, remove, createIndex |
| **Listing Write API** | listings | find, insert, update | remove if no deletes, userAdmin |
| **Payment Dashboard** | paymentSummaries | find | app-wide readWrite, unnecessary raw PII access |
| **Payment Settlement Worker** | settlements | find/update or insert as needed | user/admin privileges |
| **Audit Append Worker** | auditLogs | insert | update/remove if audit is append-only |
| **Change Stream Worker** | source collection | find + changeStream per watch scope | cluster admin |
| **Migration Job** | target collections | createIndex, listIndexes, createCollection... when needed | permanent root |
| **Monitoring** | applicable cluster info | monitoring privileges | data writes, userAdmin |
| **Backup** | data/metadata per backup tool | backup role/equivalent privileges | API credentials |
| **Human DBA** | authorized scope | administrative privileges via approval | daily use inside APIs |

This is a **starting matrix**, not a universal whitelist for every MongoDB version. To translate it into real roles, inspect the exact commands the service/driver executes, then grant permissions on the exact resources.

### 6.1. Read-Only API

~~~javascript
db.listings.find({ status: "active" });

db.listings.aggregate([
  { $match: { status: "active" } },
  { $group: {
    _id: "$city",
    count: { $sum: 1 }
  } }
]);
~~~

If both queries only read `listings`, the **find** action on `listings` is the foundational privilege. However, aggregation pipelines reading other collections or writing output require additional privileges.

### 6.2. Update-Only Worker

A worker that only updates a status without reading the full document might only need **update**. If it must read data first to decide, it also needs `find`. Distinguish the real requirement instead of assuming “if it updates, it must read everything”.

### 6.3. Migrations Should Not Run Under the App User

A framework might auto-create indexes on startup. If the app user lacks **createIndex**, startup errors can occur. The proper solution is:

1. Extract schema migrations into a dedicated deployment job.
2. Use an identity with the required index/schema privileges.
3. Disable automatic index creation across every production app instance where possible.
4. Keep the app runtime on narrow CRUD privileges.

Never grant `createIndex` to every API instance just to avoid changing framework settings.

## 7. Creating Custom Roles Scoped to One Collection

### 7.1. Read-Only Role

~~~javascript
{
  role: "listingReader329",
  privileges: [
    {
      resource: {
        db: "mongo_security_lab_329",
        collection: "listings"
      },
      actions: ["find"]
    }
  ],
  roles: []
}
~~~

This role **lacks** `insert`, `update`, `remove`, `createIndex`, or any access to `payments`.

### 7.2. Editor Role

~~~javascript
{
  role: "listingEditor329",
  privileges: [
    {
      resource: {
        db: "mongo_security_lab_329",
        collection: "listings"
      },
      actions: ["find", "insert", "update"]
    }
  ],
  roles: []
}
~~~

This role allows reading, inserting, and updating `listings`, **without `remove`**. Any action omitted from a role can still be exercised if the user receives it from another role; always inspect **all roles assigned to the user**.

### 7.3. Do Not Name Roles After Endpoints

Naming a role **canUseAdminPage** does not describe its MongoDB permissions. A well-designed role is defined by resources/actions and documented with authorized workloads.

Example:

~~~text
Role: listingReader329
Owner: Listing Search team
Resource: mongo_security_lab_329.listings
Actions: find
Denied by omission: insert/update/remove/createIndex
Reason: Search API only needs to read listings
~~~

### 7.4. Roles Do Not Create Row-Level Policies

A `find` role on `listings` is interpreted by MongoDB as search access **across that collection**. It **does not automatically inject a `tenantId` predicate** into queries. This is examined in depth in Section 13.

## 8. Self-Contained mongosh Lab: Data, Roles, and Users

### 8.1. Environment Requirements

Use only on a **self-managed MongoDB lab** with:

- Authorization enabled.
- An admin user you are authorized to use to create databases, roles, and users.
- A dedicated database **mongo_security_lab_329**.
- No existing users/roles colliding with the lesson names.
- Two `mongosh` sessions: one connected as admin, one as the test user.

If using MongoDB Atlas, refer to creating **Database Users/Custom Roles via the Atlas UI/API**. Do not run self-managed `createUser` commands on an Atlas cluster where the deployment does not support them.

### 8.2. Seed Three Listings Using the Lab Admin

Run in `mongosh` **authenticated as the admin account**:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_security_lab_329");

  if (!lab.getCollectionNames().includes("listings")) {
    lab.createCollection("listings");
  }

  const listings = lab.getCollection("listings");
  const samples = [
    {
      _id: "lab329-001",
      title: "Studio with work desk",
      tenantId: "t001",
      city: "HCM",
      status: "active",
      rentMillion: 12
    },
    {
      _id: "lab329-002",
      title: "Two-bedroom apartment",
      tenantId: "t001",
      city: "HN",
      status: "draft",
      rentMillion: 18
    },
    {
      _id: "lab329-003",
      title: "Apartment near the park",
      tenantId: "t002",
      city: "HCM",
      status: "active",
      rentMillion: 14
    }
  ];

  for (const item of samples) {
    listings.replaceOne(
      { _id: item._id },
      item,
      { upsert: true }
    );
  }

  printjson({
    count: listings.countDocuments({
      _id: { $in: samples.map(s => s._id) }
    }),
    docs: listings.find({
      _id: { $in: samples.map(s => s._id) }
    }).sort({ _id: 1 }).toArray()
  });
})();
~~~

**Expected result:** `count` = **3**, including two `t001` listings and one `t002` listing. The script only uses three fixed lab `_id`s and does not drop the collection. Re-running resets the sample documents to their initial state.

### 8.3. Create the listingReader329 Role

Run **once** as the lab admin:

~~~javascript
const lab = db.getSiblingDB("mongo_security_lab_329");

lab.createRole({
  role: "listingReader329",
  privileges: [
    {
      resource: {
        db: "mongo_security_lab_329",
        collection: "listings"
      },
      actions: ["find"]
    }
  ],
  roles: []
});
~~~

Do not add database-wide built-in **read**; doing so would open read access to other collections as well.

### 8.4. Create the listingEditor329 Role

~~~javascript
const lab = db.getSiblingDB("mongo_security_lab_329");

lab.createRole({
  role: "listingEditor329",
  privileges: [
    {
      resource: {
        db: "mongo_security_lab_329",
        collection: "listings"
      },
      actions: ["find", "insert", "update"]
    }
  ],
  roles: []
});
~~~

The editor **does not have `remove`** and does not have `userAdmin`.

### 8.5. Create Two Users

~~~javascript
const lab = db.getSiblingDB("mongo_security_lab_329");

lab.createUser({
  user: "svc_listing_reader329",
  pwd: passwordPrompt(),
  roles: [
    {
      role: "listingReader329",
      db: "mongo_security_lab_329"
    }
  ]
});

lab.createUser({
  user: "svc_listing_editor329",
  pwd: passwordPrompt(),
  roles: [
    {
      role: "listingEditor329",
      db: "mongo_security_lab_329"
    }
  ]
});
~~~

**`passwordPrompt()`** prompts for the secret interactively. Each user needs a strong, distinct password. Never copy real passwords into code, commits, terminal history, or study notes.

Both users are created in **mongo_security_lab_329**, so their authentication database is also **mongo_security_lab_329**. If the user or role already exists, `createUser`/`createRole` may fail; do not use `updateUser` to overwrite an object whose origin you do not know.

### 8.6. Inspect Role Definitions

~~~javascript
const lab = db.getSiblingDB("mongo_security_lab_329");

printjson(lab.getRole(
  "listingReader329",
  { showPrivileges: true }
));

printjson(lab.getRole(
  "listingEditor329",
  { showPrivileges: true }
));
~~~

In `mongosh`/versions supporting this helper, the output lists privileges. You can also use **rolesInfo** directly if helper behavior differs.

### 8.7. Inspect User Roles

~~~javascript
const lab = db.getSiblingDB("mongo_security_lab_329");

printjson(lab.getUser(
  "svc_listing_reader329",
  {
    showPrivileges: true,
    showCredentials: false
  }
));
~~~

Check **roles**, **inheritedRoles**, and **inheritedPrivileges** when returned—not just the username.

## 9. authSource and Connecting with the Read-Only User

### 9.1. Logging In from mongosh

On a local self-managed MongoDB lab:

~~~bash
mongosh "mongodb://127.0.0.1:27017/mongo_security_lab_329" --username svc_listing_reader329 --authenticationDatabase mongo_security_lab_329 --password
~~~

`mongosh` prompts for the password interactively. If the lab uses another hostname/port, substitute the right address. This is a local setup; **network connections in production require TLS and server verification**.

### 9.2. Authentication Database Differs from Target Database

The corresponding URI can contain:

~~~text
mongodb://127.0.0.1:27017/mongo_security_lab_329?authSource=mongo_security_lab_329
~~~

If a user is created in **admin** with roles on the lab database, `authSource` typically must be **admin**. If a user is created in the lab database yet the client tries authenticating in `admin`, `AuthenticationFailed` can occur even with the right password.

Never grant broader permissions to “fix” an `authSource` mismatch.

### 9.3. Verify Current Identity

~~~javascript
const lab = db.getSiblingDB("mongo_security_lab_329");

const status = lab.runCommand({
  connectionStatus: 1,
  showPrivileges: true
});

printjson({
  users: status.authInfo?.authenticatedUsers,
  roles: status.authInfo?.authenticatedUserRoles,
  privileges: status.authInfo?.authenticatedUserPrivileges
});
~~~

The goal is confirming **which account the current session is using**. With multiple `mongosh` sessions open, it is easy to accidentally run a test as admin instead of the reader user.

### 9.4. Positive Test — Read Succeeds

~~~javascript
const lab = db.getSiblingDB("mongo_security_lab_329");
const listings = lab.getCollection("listings");

printjson(
  listings.find(
    { status: "active" },
    { _id: 1, title: 1, tenantId: 1 }
  ).sort({ _id: 1 }).toArray()
);
~~~

If logged in as **svc_listing_reader329**, `find` on `listings` is permitted. It can return both **lab329-001 and lab329-003**, even though those two documents belong to different tenants. This is an important demonstration that collection-level RBAC **does not automatically enforce tenant filters**.

### 9.5. Negative Test — Update Must Be Denied

To avoid destructive changes, test against an **`_id` guaranteed not to exist**, without `upsert`, and **verify your identity first**:

~~~javascript
const lab = db.getSiblingDB("mongo_security_lab_329");
const status = lab.runCommand({
  connectionStatus: 1
});

const authenticatedUsers = status.authInfo?.authenticatedUsers || [];
const isReader = authenticatedUsers.some(u =>
  u.user === "svc_listing_reader329" &&
  u.db === "mongo_security_lab_329"
);

if (!isReader) {
  throw new Error(
    "Wrong identity; skipping permission test."
  );
}

let allowedUnexpectedly = false;

try {
  lab.getCollection("listings").updateOne(
    { _id: "lab329-NOT-EXISTING-permission-check" },
    { $set: { status: "active" } }
  );
  allowedUnexpectedly = true;
} catch (error) {
  printjson({
    expectedDenial: true,
    code: error.code,
    codeName: error.codeName,
    message: error.message
  });
}

if (allowedUnexpectedly) {
  throw new Error(
    "Update was unexpectedly permitted; check roles!"
  );
}
~~~

Expected result: MongoDB denies the operation with **Unauthorized**. If permissions are unexpectedly broader, the query matches no document and alters no data. **Never use `deleteMany({})`** or `dropCollection` as a negative test—if you accidentally hold permissions, real data could be destroyed.

### 9.6. “show collections” Can Fail Even When find Succeeds

A role with only **find** on `listings` does not necessarily permit:

~~~javascript
show dbs
show collections
db.listings.getIndexes()
db.stats()
~~~

Those commands can require **listDatabases**, **listCollections**, **listIndexes**, or **dbStats**. If an application only needs `find()` on a known collection, `show collections` being denied is no reason to grant `dbAdmin`.

## 10. Inspecting Permissions with connectionStatus, rolesInfo, and usersInfo

### 10.1. View Which Actions a Role Has

As admin:

~~~javascript
const lab = db.getSiblingDB("mongo_security_lab_329");

printjson(lab.runCommand({
  rolesInfo: {
    role: "listingReader329",
    db: "mongo_security_lab_329"
  },
  showPrivileges: true
}));
~~~

### 10.2. View What Is Assigned to a User

~~~javascript
const lab = db.getSiblingDB("mongo_security_lab_329");

printjson(lab.getUser(
  "svc_listing_reader329",
  {
    showPrivileges: true,
    showCredentials: false
  }
));
~~~

### 10.3. Inspect the Current Connection

~~~javascript
printjson(
  db.runCommand({
    connectionStatus: 1,
    showPrivileges: true
  })
);
~~~

**Do not rely solely on role names.** A role named `reader` can inherit write privileges. Effective privileges are what matter during an audit.

### 10.4. When Permissions Are Missing

Resolution workflow:

1. Record the **database, collection, command, and missing action**.
2. Confirm the current authenticated user and `authSource`.
3. Inspect effective privileges.
4. Determine whether the operation belongs to that service's responsibilities.
5. If yes, consider granting **one specific action on one required resource**.
6. If no, move the operation to the proper service identity or deployment workflow.
7. Test both allowed operations and operations that must be denied.

Never treat a single `Unauthorized` error as justification to assign `readWriteAnyDatabase`.

## 11. Aggregations, $lookup, and Additional Actions

### 11.1. Read-Only Aggregation

~~~javascript
db.getSiblingDB("mongo_security_lab_329")
  .getCollection("listings")
  .aggregate([
    { $match: { status: "active" } },
    {
      $group: {
        _id: "$city",
        count: { $sum: 1 }
      }
    }
  ]);
~~~

This pipeline reads `listings`. The **find** privilege on the source collection is the baseline requirement.

### 11.2. $lookup Adds Another Source

~~~javascript
db.listings.aggregate([
  {
    $lookup: {
      from: "owners",
      localField: "ownerId",
      foreignField: "_id",
      as: "owners"
    }
  }
]);
~~~

This pipeline reads data from **owners**, so read permission on `owners` must be evaluated per command/version. Never grant database-wide `read` just for one `$lookup`, especially if `owners` contains PII. Consider maintaining a **publicOwnerSummary** collection to avoid exposing detailed personal records.

### 11.3. $out/$merge Have Side Effects

Pipelines using **$out** or **$merge** write data to a target collection. An account with only `find` on the source should not be expected to have write access on the target.

If an API accepts arbitrary client pipelines, output-writing stages are a serious hazard. The server should allowlist pipelines, restrict collections, and use task-scoped roles.

### 11.4. Change Streams

A consumer watching only `listings` may need:

~~~javascript
{
  resource: {
    db: "mongo_security_lab_329",
    collection: "listings"
  },
  actions: ["find", "changeStream"]
}
~~~

This is a reference privilege shape for a collection-level Change Stream in supported environments. Watching an entire database or deployment requires different scopes/privileges. **Never grant `root` to a CDC worker** to fix cursor-opening errors.

### 11.5. Aggregations/Transactions Do Not Elevate Privileges

If a transaction updates `listings` and inserts into `auditLogs`, the identity must hold **update on `listings`** and **insert on `auditLogs`**. Using a transaction does not allow commands to bypass RBAC.

## 12. Least Privilege Across the Deployment Lifecycle

### 12.1. Runtime User

The runtime user handles business requests. When an API is read-only, **find** should be the primary privilege. Never attach IAM or schema migration privileges to runtime identities.

### 12.2. Migration User

A migration job may need **createIndex**, **listIndexes**, **createCollection**, and other actions required by actual schema migrations. It can be restricted to deploy windows within controlled CI/CD environments.

### 12.3. Monitoring User

Monitoring needs server/replica set/shard telemetry, not queries against `payments`. Consider built-in **clusterMonitor** or a custom scope matched to your monitoring tool.

### 12.4. Backup/Restore User

Backup and restore can require cluster-level privileges and procedures beyond `find`. Use a separate identity and restrict which people/workers can access its credentials. Restore privileges can overwrite/delete data on a massive scale if abused.

### 12.5. Human Administrator

Human DBAs need administrative privileges governed by procedure, MFA/SSO where available, auditing, and emergency access policies. Never put human admin accounts into API connection strings.

### 12.6. Temporary Access

A one-night index creation task does not justify permanent `createIndex` privileges on the API:

~~~text
Approval -> grant temporary privilege/identity
         -> run migration
         -> verify output
         -> revoke privilege
         -> record audit/change log
~~~

A long-lived role with broad privileges and no remaining owner is a standing risk.

## 13. RBAC Does Not Automatically Provide Row-Level Tenant Isolation

### 13.1. The Shared Collection Problem

In the lab:

~~~javascript
{
  _id: "lab329-001",
  tenantId: "t001",
  title: "Studio..."
}

{
  _id: "lab329-003",
  tenantId: "t002",
  title: "Apartment..."
}
~~~

A MongoDB user with **find on `listings`** can run:

~~~javascript
db.listings.find({});
~~~

and read documents for both `t001` and `t002` unless constrained at the application/architecture layer. That role **contains no built-in condition** saying “only return `tenantId=t001` documents”.

### 13.2. Derive tenantId from the Security Context

Node.js backend:

~~~javascript
const tenantId = authenticatedContext.tenantId;
const requestedListingId = validatedParams.listingId;

const listing = await db
  .collection("listings")
  .findOne({
    _id: requestedListingId,
    tenantId: tenantId
  });
~~~

In production, `tenantId` must be verified server-side from the user's token/session/permissions. Never blindly trust:

~~~javascript
const tenantId = req.query.tenantId;
~~~

if the user is not authorized to choose that tenant.

### 13.3. Updates and Deletes Also Need Tenant Predicates

~~~javascript
await db.collection("listings").updateOne(
  {
    _id: validatedListingId,
    tenantId: authenticatedContext.tenantId,
    status: "draft"
  },
  {
    $set: { status: "active" }
  }
);
~~~

The filter includes both **tenantId** and **status** to protect ownership and business state transitions. An `update` role on the collection only bounds the collection scope—it does not ensure the app updates the right document.

### 13.4. Object Spread Bugs

Wrong:

~~~javascript
const filter = {
  tenantId: authenticatedContext.tenantId,
  ...req.body.filter
};
~~~

If the client sends a different `tenantId`, the trailing spread can overwrite the verified `tenantId`.

Better:

~~~javascript
const filter = {
  status: validatedStatus,
  city: validatedCity,
  tenantId: authenticatedContext.tenantId
};
~~~

Only allow clients to supply allowlisted filter fields and operators; never execute arbitrary pipelines without strict controls.

### 13.5. When Stronger Isolation Is Required

Consider:

| Model | Advantage | Trade-Off |
| --- | --- | --- |
| Shared collection + `tenantId` | Fewer collections, centralized operations | Application must enforce tenant filters |
| Collection per tenant | Can scope collection roles separately | Many indexes/collections and complex lifecycle |
| Database per tenant | Clearer per-tenant permissions and operations | Higher provisioning, migration, connection overhead |
| Dedicated cluster/region | Stronger infrastructure isolation | Higher cost and operational overhead |

There is no “free” option, but be candid: **core MongoDB RBAC grants permissions on resources like databases/collections and does not automatically inject row-level predicates into every `find`**.

## 14. Atlas Project Roles Differ from MongoDB Database Roles

On Atlas there are at least two layers:

1. **Atlas organization/project roles**: permissions to manage projects, clusters, networking, backups, and Atlas settings.
2. **MongoDB database users/roles**: permissions for connection identities executing `find`/`insert`/`update`/commands inside the cluster.

Holding **Project Owner** in the Atlas UI does not mean an application connection automatically has database `root`. Conversely, a database user with `readWrite` cannot arbitrarily alter Atlas project network settings.

When deploying:

- Use Atlas UI/API to grant organization/project management roles to the right staff.
- Use **Database Access** to provision identities/roles for clients.
- Never place Atlas Project Owner credentials inside a web API.
- Check **custom database roles** support for your deployment.
- Do not assume `db.createUser()` works on every Atlas-managed cluster.

## 15. Secrets, TLS, and Authentication Mechanisms

### 15.1. SCRAM Passwords

For SCRAM, passwords must be strong, service-specific, and managed via a secret manager. When running `mongosh` interactively, use **`--password`** without a plaintext argument so it prompts interactively.

Never store:

~~~text
mongodb://admin:PlaintextPassword@prod-host:27017/app
~~~

in source code, logs, or tickets. URL-encoding a password does not make it safe public data.

### 15.2. TLS

TLS protects the transport channel and verifies the server endpoint. A strong password does not replace TLS. When encountering certificate errors:

- Check the CA bundle/trust chain.
- Check that the hostname matches the certificate.
- Check server/client TLS versions and configuration.
- Never disable certificate verification in production as a “quick fix”.

### 15.3. X.509

X.509 can use client certificates for authentication in supported environments. You still must:

- Protect private keys.
- Rotate certificates.
- Validate CA/hostname properly.
- Map users/roles according to policy.

A valid certificate **does not automatically grant `find` or `update`** if authorization does not permit it.

### 15.4. OIDC/Federated Authentication

Deployments supporting OIDC can integrate with an IdP. Authentication is performed by the identity provider, while identities/roles must still be mapped in MongoDB/Atlas appropriately. SSO does not imply full database privileges.

### 15.5. Never Log Secrets

Never write:

~~~javascript
console.log(process.env.MONGODB_URI);
~~~

if the URI contains a username/password. Error reporting, analytics, and crash logs must also **redact credentials**. Never post outputs containing secrets or sensitive data to public forums.

## 16. Privilege Rotation and Revocation

### 16.1. Grant and Revoke

MongoDB provides commands/helpers such as **grantRolesToUser** and **revokeRolesFromUser** to manage role assignments.

**Illustrative only**—do not run this step in the lab if you want to keep the reader negative test intact:

~~~javascript
const lab = db.getSiblingDB("mongo_security_lab_329");

// DO NOT RUN on the lab reader if you want to preserve the negative test.
lab.grantRolesToUser(
  "svc_listing_reader329",
  [
    {
      role: "listingEditor329",
      db: "mongo_security_lab_329"
    }
  ]
);
~~~

If granted unintentionally, an admin must investigate/review and revoke the role:

~~~javascript
lab.revokeRolesFromUser(
  "svc_listing_reader329",
  [
    {
      role: "listingEditor329",
      db: "mongo_security_lab_329"
    }
  ]
);
~~~

**Revoking a role is not the same as dropping a user.** Revoking a role changes permissions, whereas dropping a user removes the identity from the authentication database.

### 16.2. Editing a Role Affects Multiple Users

If an admin edits the custom role `listingReader329` to add `update`, every user inheriting that role gains write capability. Before editing a role, check:

1. Which users are assigned or inherit the role.
2. Actions/resources before and after.
3. Whether it creates a privilege escalation path.
4. Positive/negative tests in staging.
5. Rollout, auditing, and rollback mechanisms.

### 16.3. Rotating Across Multiple Instances

If five API replicas share one credential:

~~~text
1. Prepare a new identity/secret with matching roles.
2. Deliver the new secret to runtime.
3. Gradually roll replicas onto the new credential.
4. Verify all replicas connect successfully.
5. Monitor authentication failures.
6. Revoke the old credential after verification.
~~~

Never delete the old password immediately after updating only one instance, unless responding to an emergency credential compromise. During an incident, prioritize containment and coordinated recovery per your playbook.

### 16.4. Permissions on Already-Open Connections

When role/credential changes take effect on open connections can depend on topology/caching and version. For sensitive changes, test both **new connections** and **existing connections** per server/deployment documentation rather than assuming `grant`/`revoke` returning `OK` is sufficient.

## 17. Node.js: Read-Only App with a Dedicated Identity

Standalone example (MongoDB driver, URL supplied by a secret manager):

~~~javascript
import { MongoClient } from "mongodb";

const client = new MongoClient(
  process.env.MONGODB_SEARCH_READ_URI
);

await client.connect();

try {
  const listings = client
    .db("mongo_security_lab_329")
    .collection("listings");

  // Production: obtain from security context after authentication.
  const authorizedTenantId = "t001";

  const result = await listings.find(
    {
      tenantId: authorizedTenantId,
      status: "active"
    },
    {
      projection: {
        _id: 1,
        title: 1,
        city: 1,
        rentMillion: 1
      },
      limit: 20,
      maxTimeMS: 3000
    }
  ).toArray();

  console.log(result);
} finally {
  await client.close();
}
~~~

This is a **demo script**, not a runtime architecture. In production HTTP services, a `MongoClient` should typically be long-lived with a connection pool rather than created and closed per request.

### 17.1. Separate Read and Write Identities

~~~text
Search API:
  MONGODB_SEARCH_READ_URI
  role = listingReader329

Mutation API:
  MONGODB_LISTING_EDIT_URI
  role = listingEditor329
~~~

If both URIs reside in the same process, compromising that process exposes both. Separating identities is a good step, but real isolation is much stronger when **separating workloads, processes, and secret delivery**.

### 17.2. Tenant- and State-Scoped Update

~~~javascript
import { MongoClient } from "mongodb";

const client = new MongoClient(
  process.env.MONGODB_LISTING_EDIT_URI
);

await client.connect();

try {
  const listings = client
    .db("mongo_security_lab_329")
    .collection("listings");

  const result = await listings.updateOne(
    {
      _id: "lab329-002",
      tenantId: "t001",
      status: "draft"
    },
    {
      $set: { status: "active" }
    }
  );

  console.log({
    matched: result.matchedCount,
    modified: result.modifiedCount
  });
} finally {
  await client.close();
}
~~~

This update does not require `remove` or `createIndex`. If the service needs other operations, list those exact actions—never grant `root`.

## 18. Change Streams, Monitoring, and Backup Need Dedicated Scopes

### 18.1. Collection-Scoped CDC

A CDC worker only needs changes on `listings`. Watching the entire deployment requires broader privileges and delivers events from unrelated namespaces. **Watch the narrowest collection** that satisfies the business need.

### 18.2. Monitoring

Monitoring agents observe `serverStatus`/replication/performance. Never grant `readWrite` “to collect metrics” when the task is reading metadata/metrics. Cross-check built-in **clusterMonitor** or custom privileges against the exact commands your monitoring tool runs.

### 18.3. Backup

Backups may require privileges across multiple collections/metadata and must follow consistent replica set or sharded cluster procedures. Backup identities should be separate from application identities, with protected credentials and audited access to backup artifacts.

### 18.4. Restore

Restores carry the risk of overwriting or deleting data at massive scale. Someone permitted to restore does not automatically need that ability in daily operations. Use approvals, runbooks, and dedicated identities.

### 18.5. Sharded Clusters

CRUD in a sharded cluster normally routes through **mongos** rather than connecting directly to individual shard `mongod` nodes. Applications do not gain config server or shard replication admin privileges simply because a cluster is sharded.

## 19. Operational Auditing and Periodic Access Reviews

### 19.1. Identity Inventory

An access review must answer:

- Which user belongs to which service and environment.
- Who the owner is and whether it is still in use.
- Direct roles and inherited roles.
- Which collections/databases are actually accessed.
- Accounts holding `root`/`userAdmin`/`dbOwner`/`restore`.
- Temporary permissions past their expiration.
- Shared credentials.
- Accounts overdue for rotation.

### 19.2. Do Not Blindly Delete Rarely Used Users

A monthly backup account may not appear in daily logs. A DR account used only during recovery still has a purpose. Always verify owners and dependencies before deleting an account.

### 19.3. Audit Trails

Audit logging capabilities and scope depend on MongoDB edition/Atlas deployment. In supported environments, track sensitive events such as user creation, role changes, authentication policy changes, and sensitive data access.

Do not treat the database audit log as the sole source for the **business actor** if the app uses a shared service account for all end users. Add API-layer auditing with `userId`/`requestId` and proper data policies.

### 19.4. When a Credential Is Compromised

Response workflow:

1. Identify the compromised user and its effective privileges.
2. Bound the scope of data that could have been read or modified.
3. Revoke/rotate according to urgency.
4. Monitor related connections/sessions.
5. Inspect audit/operation logs per permissions and retention.
6. Check for unusual role grants or metadata changes.
7. Restore least-privilege configuration and update tests.

If the credential only had **find on `listings`**, its blast radius is far smaller than `root`—yet `listings` data may still have been read without authorization. Least privilege reduces impact; it does not eliminate incident response.

## 20. Common Mistakes

| Mistake | Why It Is Dangerous | Fix |
| --- | --- | --- |
| Using `root` for every service | One flaw can impact the entire cluster | Workload-scoped identity |
| Using `readWrite` for Search API | Allows writes when only reads are needed | `find` on collection |
| Using database-wide `read` to read `listings` | Can also read `payments`/`users` | Custom role on `listings` resource |
| Adding a narrow role while keeping a broad role | Effective privileges are the union | Remove the broad role |
| Trusting a role named `readonly` | Role may inherit write privileges | Inspect `inheritedPrivileges` |
| Assuming authenticated means authorized | Login succeeded, action still missing | Verify both layers separately |
| Wrong `authSource` | `AuthenticationFailed` despite right password | Use the database storing the user |
| Granting `root` on `Unauthorized` | Expands blast radius | Identify exact missing action/resource |
| Role has `find` only, worker opens Change Stream | May lack `changeStream` | Grant exact required scope |
| Framework runs `createIndex` as app user | Runtime demands schema privileges | Separate migration job |
| Using `userAdmin` in API | Privilege escalation risk | Separate IAM account |
| Thinking RBAC filters `tenantId` | Cross-tenant reads in shared collection | Application-level authorization |
| Letting client filter overwrite `tenantId` | Users can pick another tenant | Server enforces tenant filter |
| Logging URIs/passwords | Secret exposure | Secret manager, redaction |
| Disabling TLS verification to connect fast | MITM/endpoint spoofing | Fix CA/hostname |
| Using dev credentials in prod | Dev leak impacts prod | Separate identities/environments |
| Confusing Atlas project role with DB user | Grants wrong layer of access | Distinguish project vs. database |
| Shared human accounts | Breaks accountability | Individual identities, auditing |
| Granting roles without reviewing inheritance | Accidentally opens extra privileges | Inspect effective privileges |
| Deleting old credential before rollout finishes | Service outage | Staged rotation |
| Testing denial with `deleteMany({})` | If privileges are broad, destroys data | Guarded test on non-existent ID |

## 21. Least-Privilege Implementation Checklist

### 21.1. Before Creating a User

1. Identify the service/job/human owner.
2. List collections that require access.
3. List required commands and MongoDB actions.
4. Choose the narrowest built-in or custom role.
5. Inspect all inherited privileges.
6. Choose authentication mechanism, `authSource`, and secret lifecycle.
7. Document justification, environment, and next review date.

### 21.2. Before Deploying

1. Verify authentication and TLS.
2. Verify URIs are never logged.
3. Test **permitted** operations.
4. Test operations that **must be denied** using safe tests.
5. Verify the app enforces `tenantId` on reads and writes.
6. Verify schema/index migrations run under a separate identity.
7. Configure alerts for unusual `Unauthorized` errors and auth failures.
8. Ensure rotation/revocation playbooks exist.

### 21.3. During Periodic Reviews

1. Export the user/role inventory using authorized accounts.
2. Compare against the expected permission matrix.
3. Identify ownerless or decommissioned accounts.
4. Flag out-of-scope administrative roles.
5. Review secrets and rotation history.
6. Verify multi-tenant application authorization.
7. Record findings and re-approve still-needed privileges.

## 22. Hands-On Exercises

### Exercise 1 — Distinguish AuthN/AuthZ

A user logs in successfully, yet `insertOne` returns `Unauthorized`. Explain which step succeeded, which failed, and why changing the password will not fix the permission error.

### Exercise 2 — Resource/Action

Write a privilege containing only **find** on `mongo_security_lab_329.listings`. Why does that privilege not allow `find` on `payments`?

### Exercise 3 — Read vs. readWrite

A service only needs `find`. Compare built-in `read`, `readWrite`, and a custom `find` role on a single collection. Choose the least-privileged option.

### Exercise 4 — Role Inheritance

A user has `listingReader329` and `readWrite` on the lab database. Can that user update `payments`? Why does a narrow custom role not negate a broader role?

### Exercise 5 — Create Sample Data

Run the lab seed from Section 8. Verify the three IDs, `tenantId`, statuses, and active database. Why must an admin account create the collection and seed data first?

### Exercise 6 — Create Custom Roles

Create `listingReader329` and `listingEditor329`. List the action differences—specifically, does `remove` appear in Editor?

### Exercise 7 — Create Database Users

Create both corresponding users using `passwordPrompt`. Which authentication database do they reside in?

### Exercise 8 — authSource

A user was created in the lab database, yet the URI specifies `authSource=admin`. Predict the error. If the user was created in `admin` with roles on the lab database, what should `authSource` be?

### Exercise 9 — ConnectionStatus

Log in as the reader and print `authenticatedUsers` and `authenticatedUserRoles`. Why must you verify your identity before testing a forbidden command?

### Exercise 10 — Positive/Negative Tests

Run a successful `find` and an `updateOne` on a non-existent ID to observe `Unauthorized`. Explain why you must never use `deleteMany({})` as a negative test.

### Exercise 11 — Show Collections

The reader can `find` `listings`, yet `show collections` fails. Why? Should you grant `listCollections` or adjust the app so it does not require introspection?

### Exercise 12 — Aggregation

One pipeline uses only `$match`/`$group` on `listings`, while another uses `$merge` into `reports`. Distinguish the required privileges.

### Exercise 13 — $lookup

A pipeline queries `listings` and runs `$lookup` into `owners`. Identify the secondary resource to evaluate and explain why you should not grant `read` across all collections to a public API.

### Exercise 14 — Change Streams

A worker only watches `listings`. Describe the required role and explain why watching the entire deployment is not least privilege.

### Exercise 15 — Insert-Only Audit

Design a role with only `insert` on `auditLogs`, without `update`/`remove`. Why does this role not guarantee log immutability against a `root` admin?

### Exercise 16 — Migration

A framework auto-runs `createIndex` on startup, while the app user only has `find`. Propose a CI/CD migration identity instead of broadening app privileges.

### Exercise 17 — UserAdmin

Why is `userAdmin` a sensitive role that can enable privilege escalation? Does a listing-processing app need this role?

### Exercise 18 — Atlas

Distinguish an Atlas Project Owner from a MongoDB database user with `readWrite`. Why must Project admin credentials never be placed in a runtime API?

### Exercise 19 — Multi-Tenant

One collection stores `t001`/`t002` data; the DB role has `find` on the collection. Why does MongoDB not automatically exclude `t002` from `t001`'s `find({})`? Propose app-level authorization.

### Exercise 20 — Tenant-Scoped Update

Write an `updateOne` filtering by `_id` + `tenantId` from the security context + `status`. What risk arises if only `_id` is used?

### Exercise 21 — Object Spread

A client sends a filter containing another `tenantId`. Point out the flaw in **`{tenantId:authenticatedTenantId, ...clientFilter}`**, then write a non-overridable version.

### Exercise 22 — Secret Hygiene

Analyze the risks of storing `mongodb://user:password@host` in source code or debug logs. Propose a secret manager and redaction.

### Exercise 23 — TLS

A developer wants to disable certificate validation in production due to a connection error. What should you inspect, and why must server verification never be disabled?

### Exercise 24 — Rotation

Five API replicas share a credential. Outline the sequence to introduce a new credential, verify it, roll it out gradually, and revoke the old one without downtime.

### Exercise 25 — Temporary Privileges

An index-creation job runs for one night only. Specify the identity/privileges, approval process, and post-completion revocation steps.

### Exercise 26 — Audit Role Graph

A role is named `readonly`, yet `inheritedPrivileges` includes `update`. Why is the role name insufficient proof? Which commands would you run to inspect it?

### Exercise 27 — Monitoring

A monitoring agent needs replica set status without reading `payments`. Identify `clusterMonitor`/custom scope considerations.

### Exercise 28 — Backup/Restore

Why do backup and restore need separate accounts? How does the impact of a leaked `restore` credential differ from a `reader` account?

### Exercise 29 — Incident

Search API credentials leak. Compare the impact when it only has `find` on `listings` versus `root`. Outline revoke/rotate/audit steps.

### Exercise 30 — Deploy Checklist

Draft a pre-production checklist covering per-environment accounts, TLS, `authSource`, roles, permission tests, tenant authorization, secret rotation, and incident response.

### Exercise 31 — Transaction

A transaction updates `listings` and then inserts into `auditLogs`. If the user only has `update` on `listings`, does the transaction automatically permit inserting into `auditLogs`?

### Exercise 32 — Complete Design

Given four workloads—Search API, Listing Editor, Audit Writer, Index Migration—build a resource/action matrix, create matching custom roles, and specify which privileges must **not be granted**.

## 23. MongoDB References

- MongoDB Manual — [Authorization](https://www.mongodb.com/docs/manual/core/authorization/).
- MongoDB Manual — [Users](https://www.mongodb.com/docs/manual/core/security-users/).
- MongoDB Manual — [Built-In Roles](https://www.mongodb.com/docs/manual/reference/built-in-roles/).
- MongoDB Manual — [User-Defined Roles](https://www.mongodb.com/docs/manual/core/security-user-defined-roles/).
- MongoDB Manual — [Privilege Actions](https://www.mongodb.com/docs/manual/reference/privilege-actions/).
- MongoDB Manual — [db.createUser()](https://www.mongodb.com/docs/manual/reference/method/db.createUser/).
- MongoDB Manual — [db.createRole()](https://www.mongodb.com/docs/manual/reference/method/db.createRole/).
- MongoDB Manual — [rolesInfo](https://www.mongodb.com/docs/manual/reference/command/rolesInfo/).
- MongoDB Manual — [connectionStatus](https://www.mongodb.com/docs/manual/reference/command/connectionStatus/).
- MongoDB Manual — [grantRolesToUser](https://www.mongodb.com/docs/manual/reference/method/db.grantRolesToUser/).
- MongoDB Manual — [revokeRolesFromUser](https://www.mongodb.com/docs/manual/reference/method/db.revokeRolesFromUser/).
- MongoDB Manual — [Authentication](https://www.mongodb.com/docs/manual/core/authentication/).
- MongoDB Manual — [Transport Encryption/TLS](https://www.mongodb.com/docs/manual/core/security-transport-encryption/).
- MongoDB Atlas — [Database Users](https://www.mongodb.com/docs/atlas/security-add-mongodb-users/).

**Conclusion:** In MongoDB, **authentication** verifies identity and **authorization** governs what is permitted. Users are assigned one or more roles; each role holds privileges structured as **resource + actions**, and effective permissions include inherited privileges. **Least privilege** means every API, worker, and job holds only the exact permissions required—never granting `readWrite` or `root` just to make errors go away. Create **collection-scoped custom roles**, separate application identities from migration/monitoring/backup, configure **`authSource` and TLS properly**, protect credentials, run positive/negative permission tests, and audit privileges regularly. Above all, **RBAC does not automatically filter documents by `tenantId` in a shared collection**: applications must still enforce tenant authorization on every read and write. When a service is flawed or a credential leaks, solid permission design **contains the damage to the minimal resources and actions deliberately permitted**.
