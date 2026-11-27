# Checking Connectivity, Startup Logs, and Safely Cleaning Up Test Data

## 1. Practice Session Objectives

After installing or starting MongoDB, three tasks to perform before developing an application are **checking connectivity**, **reading startup logs**, and **cleaning up test data in a controlled manner**. These are small steps, yet they directly determine your ability to catch configuration errors and avoid accidentally deleting real data.

This practice targets a **local MongoDB instance or a test environment you manage**. Examples use MongoDB Shell (`mongosh`), OS commands, and Docker. Choose the branch matching how you run MongoDB; you do not need to install both Docker and a native MongoDB service.

Expected outcomes:

1. Know how to determine whether MongoDB Server is running and listening on the right port.
2. Connect with `mongosh`, run `ping`, and distinguish network connectivity from database permissions.
3. Locate the right log source and recognize startup success messages alongside port-binding, configuration, storage, and authentication errors.
4. Insert a test document carrying a **unique identifier**, read it back, and delete that exact document.
5. Know how to preview deletion scope and verify results without wiping an entire database or collection.

> **Safety Scope:** Perform write and delete commands only on an explicitly identified test database. Before every delete, double-check the server address, database name, collection, and filter condition. Do not use `dropDatabase()`, `drop()`, or unfiltered delete operations in this lesson.

## 2. Understanding the Path of a MongoDB Connection

A connection from an application to MongoDB typically passes through these stages:

```text
Application / mongosh
      |
      | MongoDB connection string (URI)
      v
Host / DNS + TCP port (typically 27017)
      |
      v
MongoDB server (mongod or MongoDB cluster)
      |
      +--> Authenticate account (if authentication is enabled)
      |
      +--> Authorize command / database / collection
      |
      v
Return query result
```

**Opening a TCP port does not mean authentication succeeded.** Likewise, a successful `ping` proves the server responded to that command, not that the account can write to the target collection. Therefore, verify layer by layer: process → network → MongoDB command → actual read/write permissions.

Common connection parameters:

| Parameter | Meaning | Example in Local Environment |
| --- | --- | --- |
| Host | Machine running MongoDB | `127.0.0.1` |
| Port | Port the server listens on | `27017`; Docker example below uses host port `27018` |
| Database | Application or exercise database | `mongo_lab` |
| Username/password | Credentials when server enforces authentication | Dedicated account for test environment |
| `authSource` | Database holding user authentication credentials | Typically `admin` when user was created in `admin` |
| TLS | Transport encryption; typically mandatory on cloud services | Per server/cluster configuration |

MongoDB stores documents in BSON format. Running `db...` query commands is only meaningful once the client has connected to the intended server.

## 3. Preparing the Environment and Identifying the Right Server

### 3.1. If MongoDB Runs as a Local Service

For local MongoDB using the default port, test connecting:

```bash
mongosh "mongodb://127.0.0.1:27017/"
```

Inside `mongosh`, run:

```javascript
db.adminCommand({ ping: 1 })
```

On success, output usually includes `ok: 1`. If `mongosh` is not in `PATH`, install MongoDB Shell or invoke it via its full executable path. `mongosh` is a client tool; having the shell installed does not mean the `mongod` server is installed or running.

Check the service by OS:

**Linux with systemd** (if MongoDB is registered under `mongod`):

```bash
sudo systemctl status mongod
```

**Windows PowerShell** (if MongoDB is installed as a Windows service):

```powershell
Get-Service -Name MongoDB
Test-NetConnection -ComputerName 127.0.0.1 -Port 27017
```

Service name and port may differ on custom installations. When `TcpTestSucceeded : True` is reported, the TCP path to the port is open; you still need `mongosh` to confirm this is the expected MongoDB server.

### 3.2. If You Want an Isolated Practice Container

Example running MongoDB in Docker, mapping **host port 27018** to **container port 27017**, bound strictly to host loopback:

```bash
docker run --name mongo-row37 -d -p 127.0.0.1:27018:27017 mongo:8.0
```

Inspect the container:

```bash
docker ps --filter name=mongo-row37
docker logs --tail 80 mongo-row37
```

Connect from the host when `mongosh` is installed:

```bash
mongosh "mongodb://127.0.0.1:27018/?directConnection=true"
```

Or use the shell bundled inside the container without depending on a host-installed `mongosh`:

```bash
docker exec -it mongo-row37 mongosh
```

This Docker example is for **personal machine practice**, with no authentication enabled and no persistent storage configured. Restricting the host port to `127.0.0.1` avoids exposing MongoDB directly on other host network interfaces. Never use this exact configuration to deploy a publicly reachable server.

> If port 27018 is already in use or container `mongo-row37` already exists, inspect existing processes/containers before picking a new port or name; never stop or delete resources whose ownership you have not verified.

### 3.3. If Using MongoDB Atlas or an Authenticated Server

Use the exact URI provided by your environment, typically in one of two formats:

```text
mongodb://HOST:PORT/?authSource=admin
mongodb+srv://CLUSTER_HOST/?retryWrites=true&w=majority
```

For servers requiring credentials, pass the username via CLI flag and enter the password at the `mongosh` prompt as supported by your shell version. Never put real passwords into examples, docs, terminal history, or log screenshots. With Atlas, also verify network permissions/IP access list, DNS SRV, and TLS per cluster configuration.

Throughout this lesson, keep a brief note containing only: **environment**, **host/port**, **test database name**, and **test collection name**. Do not record secrets.

## 4. Layer-by-Layer Connection Verification

### 4.1. Confirm You Are Connected to the Right Target

Open `mongosh` with the identified URI and run:

```javascript
// Current database selected by the shell
db.getName()

// Server identification metadata returned by MongoDB
db.adminCommand({ hello: 1 })

// Check whether the server responds to commands
db.adminCommand({ ping: 1 })
```

Typical `ping` output:

```javascript
{ ok: 1 }
```

Responses may include extra metadata depending on version and environment. The `hello` command lets you inspect server or topology details; in a replica set, fields like `isWritablePrimary` help clarify the node's role. Never infer the environment address solely from the active database name, because `use mongo_lab` only switches the client-side working database.

A connection specifying the database explicitly:

```bash
mongosh "mongodb://127.0.0.1:27018/mongo_lab?directConnection=true"
```

For MongoDB running on the default port, replace `27018` with the actual port. Do not copy the Docker example's port into an environment running differently.

### 4.2. Check Permissions Before Test Writes

In `mongosh`:

```javascript
// View authenticated user if the environment enforces authentication
db.runCommand({ connectionStatus: 1 })

// Select the exercise database
const lab = db.getSiblingDB("mongo_lab");
lab.getName();
```

`db.getSiblingDB("mongo_lab")` returns a handle to operate on that database; selecting it alone **creates no new data**. Certain administrative commands, collection listings, or status reads require extra privileges. If you receive `not authorized`, verify the username, `authSource`, and granted roles; do not jump to assuming MongoDB Server is broken.

To verify real write permissions, we will insert and delete **one uniquely tagged document** in Section 6.

### 4.3. Interpreting Common Connection Errors

| Symptom | Related Possibilities | Next Check |
| --- | --- | --- |
| `ECONNREFUSED 127.0.0.1:27017` | No process listening on that host/port or wrong port mapping | Service/container status, `port`, `bindIp`, Docker port mapping |
| `Server selection timed out` | Client cannot locate an eligible server before timeout; network, DNS, topology, or cluster config issue | URI, network connectivity, replica set, DNS/SRV, TLS, and server logs |
| `Authentication failed` | Wrong account, password, auth mechanism, or `authSource` | User origin, login permissions, auth configuration |
| `not authorized on ...` | Reached server, but account lacks permissions for the operation | Roles, target database, permitted actions |
| `Address already in use` on startup | Port is already held by another process | Identify port owner; adjust configuration if appropriate |
| `Connection closed`, TLS error | Connection dropped or security config mismatch | TLS, certificates, proxy, firewall, logs on both ends |
| Connected, but data is missing | Possibly in a different database/cluster or wrong filter | URI, `db.getName()`, database and collection names, query condition |

Error messages are only initial clues. A client-side network error can originate from a server that failed to start; startup logs are the next source to inspect.

## 5. Reading MongoDB Startup Logs

### 5.1. Locate the Log Source Matching Your Runtime

**Docker container:**

```bash
docker logs --tail 100 mongo-row37
docker logs --since 10m mongo-row37
```

If MongoDB runs via Docker Compose under a service named `mongo`:

```bash
docker compose logs --tail 100 mongo
```

**Linux systemd:**

```bash
sudo journalctl -u mongod -n 100 --no-pager
sudo journalctl -u mongod --since "10 minutes ago" --no-pager
```

Depending on `mongod.conf`, MongoDB may write to a dedicated file via `systemLog.path`. In that case, inspect the exact file used by the instance, for example:

```bash
sudo tail -n 100 /var/log/mongodb/mongod.log
```

The path above is merely a common default in some Linux packages, not mandatory across every system.

**Windows service:** check `systemLog.path` in the active MongoDB instance's config file, then tail the file. For example, once you know the exact path:

```powershell
Get-Content -LiteralPath "C:\path\to\mongodb\mongod.log" -Tail 100
```

**Atlas:** open the monitoring/logs section in MongoDB Atlas for the exact project and cluster, subject to granted permissions. Do not assume OS-level log file access on a managed service.

### 5.2. Reading Log Entries as Structured Events

In modern MongoDB versions, logs use structured JSON with common fields such as:

```json
{
  "t": { "$date": "2026-01-05T09:00:00.000+00:00" },
  "s": "I",
  "c": "NETWORK",
  "id": 23016,
  "ctx": "listener",
  "msg": "Waiting for connections",
  "attr": { "port": 27017 }
}
```

This is an **illustrative structural example**; IDs, timestamps, `ctx`, `attr`, and exact wording can vary by version, platform, and launch method.

| Field | How to Read |
| --- | --- |
| `t` | Log timestamp; pay attention to timezone |
| `s` | Severity: typically `I` = informational, `W` = warning, `E` = error |
| `c` | Component category, e.g., `NETWORK`, `STORAGE`, `ACCESS` |
| `id` | Message ID, useful for looking up corresponding documentation |
| `ctx` | Execution context/thread |
| `msg` | Event message |
| `attr` | Extra attributes identifying ports, paths, causes, etc. |

A `Waiting for connections` entry or equivalent indicates the server reached the client-listening state. However, startup can succeed and errors can still happen afterward; correlate timestamps, process state, and a `ping` test.

### 5.3. What to Inspect in Sequence

1. **Where did the process start?** Check timestamp and loaded instance/version configuration.
2. **Is the configuration valid?** Look for YAML errors, unsupported options, or file/data-directory permission issues.
3. **Did the storage engine initialize?** Look for messages about `dbPath`, directory write permissions, lock files, or disk space.
4. **Did networking bind cleanly?** Check the host/IP and port reported by the server.
5. **Is the server ready for connections?** Find the waiting-for-connections message and run `ping` right after.
6. **Were connections rejected due to auth or permissions?** Match client error timestamps against server logs; do not confuse them with startup failures.

Not every `W` line causes startup failure. Warnings about OS settings or security posture may appear while the server runs normally. Conversely, an `E` error followed by immediate process exit must be resolved before testing CRUD.

### 5.4. Quick Diagnostic Patterns

**Case A — `mongosh` reports it cannot connect:**

```text
mongosh -> ECONNREFUSED
    |
    +--> Is service/container running? -- No --> inspect startup logs
    |
    +--> Yes --> Do host/port match? --> check bindIp, Docker mapping, firewall
    |
    +--> Match --> inspect URI and client/server error details
```

**Case B — Connected, but cannot write:**

```text
ping ok: 1
    |
    +--> insertOne -> Authentication failed?
    |      Check user/password/authSource
    |
    +--> insertOne -> not authorized?
    |      Check database/collection write permissions
    |
    +--> insertOne succeeds
           Read back by _id + runId, then clean up only the created data
```

**Case C — Container starts and immediately exits:** use `docker ps -a --filter name=mongo-row37` to view exit state, then `docker logs mongo-row37` to find the error right before exit. Never keep retrying connections against a server that never finished starting.

## 6. Hands-On Practice: Safely Writing, Reading, and Deleting One Document

A `ping` command only confirms the server responds. To test the full path for an application environment, we will **write one document**, **read back that exact document**, and **delete it**. All operations stay scoped to database `mongo_lab` and collection `row37_probe`.

### 6.1. Create a Unique Identifier for This Run

Inside a `mongosh` session connected to the right test environment:

```javascript
const lab = db.getSiblingDB("mongo_lab");
const probes = lab.getCollection("row37_probe");

// A unique tag for this practice run; save it in case cleanup is needed after disconnect.
const runId = "row37-" + new ObjectId().toHexString();
print("runId=" + runId);

// Insert exactly one test document.
const inserted = probes.insertOne({
  runId: runId,
  kind: "connection-check",
  note: "temporary lab data",
  createdAt: new Date()
});
printjson(inserted);
```

Here:

- `mongo_lab` is a practice-only database. Replace it with an authorized database if your course specifies another name.
- `row37_probe` is a collection dedicated to probe data.
- `runId` separates this run's data from other runs, even when multiple people share an environment.
- `inserted.insertedId` is the identifier of the newly created document. Do not rely on creation timestamps or note strings to identify which record to delete.

`insertOne()` normally returns `acknowledged: true` along with `insertedId` once accepted under the active write concern. If it fails, record the error and do not proceed to deletion referencing an unset variable.

### 6.2. Read Back to Confirm the Exact Record

```javascript
const filter = { _id: inserted.insertedId, runId: runId };
const saved = probes.findOne(filter);
printjson(saved);

if (saved === null) {
  throw new Error("Newly created document not found; stopping cleanup.");
}
```

Filtering on **both `_id` and `runId`** ensures you verify the exact document from this session. Getting back `runId`, `kind`, and `createdAt` as written proves basic writes and reads work on the test collection.

### 6.3. Delete Exactly the One Document You Created

After inspecting `saved` and confirming the right environment:

```javascript
// Deletion scope: one document matching both _id and runId.
const removal = probes.deleteOne(filter);
printjson(removal);

// Must equal 0 once the deleted record no longer exists.
print("remaining=" + probes.countDocuments(filter));
```

In a normal run, `deletedCount` is `1` and `remaining` is `0`. If `deletedCount` is `0`, the record may already have been deleted, the filter may not match, or you may be inspecting the wrong environment; investigate rather than broadening the filter carelessly.

**Why not use `deleteMany({})`?** An empty filter selects every document in the current collection. Being in the wrong database or collection can cause data loss. Combining `_id` and `runId` is explicit and appropriate for connection checks.

## 7. Cleaning Up Leftover Test Data from an Earlier Session

If the shell closed after inserting the document but before deleting it, you can open a new session to clean up. The prerequisite is **knowing the exact `runId` printed during creation** and confirming the server/database/collection.

### 7.1. Preview Records That Will Be Affected

```javascript
const lab = db.getSiblingDB("mongo_lab");
const probes = lab.getCollection("row37_probe");

// Replace with the actual runId saved from your own practice run.
const runId = "row37-PASTE_YOUR_SAVED_RUN_ID";
const filter = { runId: runId, kind: "connection-check" };

print("database=" + lab.getName());
print("collection=" + probes.getName());
print("matchCount=" + probes.countDocuments(filter));

// Preview records within the deletion scope.
printjson(
  probes.find(filter, { _id: 1, runId: 1, kind: 1, createdAt: 1 })
    .limit(10)
    .toArray()
);
```

Do not proceed to the next step if:

- You have not confirmed the URI or connected server.
- You cannot recover the original `runId`, or the match count does not match your run.
- The preview list includes records you did not create or belonging to another purpose.
- The account points to a shared/production database without an approved deletion procedure.

### 7.2. Delete Using the Verified Filter

Only once you observe strictly **one** document belonging to your run in the preview:

```javascript
const expectedCount = probes.countDocuments(filter);
if (expectedCount !== 1) {
  throw new Error("Expected exactly one document to clean up; stopping to inspect.");
}

const target = probes.findOne(filter, { _id: 1, runId: 1 });
if (!target) {
  throw new Error("Document changed; stopping to inspect.");
}

const result = probes.deleteOne({
  _id: target._id,
  runId: runId,
  kind: "connection-check"
});
printjson(result);
print("remaining=" + probes.countDocuments(filter));
```

This still cannot prevent concurrent changes between preview and deletion. However, scoping deletion to a specific `_id` and unique run tag keeps the blast radius tightly bounded. In multi-user environments, coordinate a dedicated procedure for bulk cleanup.

If a practice run intentionally created multiple documents, filter precisely by `runId`, preview the full scope, and consider deleting by individual `_id`; never default to `deleteMany()` merely to save keystrokes.

### 7.3. Distinguishing Document Cleanup from Container Cleanup

Deleting documents in MongoDB and removing a Docker container are two different actions. If you **created** container `mongo-row37` strictly for this exercise and no longer need data inside it, you can stop and remove that container:

```bash
docker stop mongo-row37
docker rm mongo-row37
```

Run these two commands only after confirming the exact container belongs to your practice environment. The `docker run` example in Section 3 did not attach a persistent data volume; removing that container discards data stored inside the container's filesystem. For containers with attached volumes or shared systems, verify data sources and ownership separately before removing resources.

## 8. How to Record Practice Results

A short report helps others diagnose issues without exposing sensitive credentials. Example:

```text
Environment: Local Docker MongoDB (host loopback only)
Endpoint: 127.0.0.1:27018
Test database: mongo_lab
Test collection: row37_probe
Container/server status: Running
Ping: ok = 1
Startup logs: Waiting for connections message present, no fatal errors
CRUD check: 1 document insert -> find -> delete succeeded
Remaining documents matching _id + runId: 0
No passwords, access tokens, or full URIs with credentials stored
```

When pasting logs into a ticket or technical report, include only lines relevant to the failure window and redact sensitive data such as URIs with credentials, tokens, unnecessary internal IPs, customer details, or paths containing personal data. Keep timestamps, error codes, components, error messages, and diagnostic context.

## 9. Real-World Scenarios

### Scenario 1: Server Reports Running, but Connection Fails

A container reports `Up`, yet `mongosh` to `127.0.0.1:27017` gets `ECONNREFUSED`. Checking `docker ps` reveals mapping `127.0.0.1:27018->27017/tcp`. The root cause is **using the wrong host port**. Try the URI with port `27018` and re-run `ping`; no data changes are needed.

### Scenario 2: Ping Succeeds, Insert Fails

Connection and `ping` return `ok: 1`, but `insertOne` reports `not authorized`. The server and network link may be healthy. Verify the database name, username, and user roles. Never switch to a higher-privilege account arbitrarily just to bypass the error.

### Scenario 3: Starts and Immediately Exits

`mongod` does not appear in the process list, while logs show errors involving `dbPath` or opening data files. Start from the last relevant error before process exit, checking path existence, write permissions, disk space, and volume configuration. Retrying `ping` repeatedly will not solve a startup failure.

### Scenario 4: Practice Lab Run Multiple Times

Previous runs left behind a few `row37_probe` documents. Each run has a distinct `runId`. Learners clean up only documents matching their own `runId`, checking `matchCount` and previewing before deletion. Never wipe the entire collection as a "quick cleanup" because it may contain other people's records.

## 10. Pre-Completion Checklist

| Question | Completion Indicator |
| --- | --- |
| Identified the right MongoDB instance? | Clear host, port, environment, and database |
| Server started cleanly? | Process/container running; logs show no fatal errors |
| MongoDB commands working? | `db.adminCommand({ ping: 1 })` returns `ok: 1` |
| Read/write permissions working? | `insertOne` and `findOne` succeed in the test collection |
| Cleaned up strictly the data you created? | `deleteOne` returns `deletedCount: 1`; follow-up query by `_id` + `runId` finds nothing |
| Avoided broad deletes and credential leaks? | Delete filter uses unique tags; notes contain no secrets |

## 11. Practice Questions

1. Why is `Test-NetConnection` reporting an open TCP port insufficient to conclude the application can access a collection?
2. What is the difference between `ECONNREFUSED`, `Authentication failed`, and `not authorized`?
3. When MongoDB fails to start, why should you inspect server logs before retrying insert commands?
4. Why should every test run use a distinct `runId`? How do `_id` and `runId` complement each other during cleanup?
5. What can go wrong if you run `deleteMany({})` on a shared collection?
6. When `deletedCount` is `0`, what should you check before altering the delete filter?

Once completed, you have a repeatable workflow: **identify the right environment → verify connectivity → read logs on error → test tagged write/read → conditional delete → verify zero leftover test data**. This workflow separates operational failures from query issues while bounding the impact of practice operations on data.
