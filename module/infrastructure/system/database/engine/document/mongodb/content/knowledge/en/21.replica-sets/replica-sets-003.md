# Initializing a Replica Set, Configuring Members, and Inspecting `rs.status()` in MongoDB

## 1. Objectives and Context

A single MongoDB server can store and query documents, but if that `mongod` process stops or the host loses connectivity, the application has nowhere to send normal read/write operations. A **replica set** is MongoDB's mechanism for organizing multiple `mongod` processes to jointly maintain copies of a dataset so that a **new primary member can be elected** when the old primary can no longer serve.

This lesson focuses on three administrative tasks:

1. **Initializing a replica set**: configuring `mongod` instances to belong to the same set, running `rs.initiate()`, and verifying primary election.
2. **Configuring members**: identifying `_id`, `host`, `priority`, `votes`, arbiters, and non-electable secondaries; adding or modifying members with the appropriate tools.
3. **Inspecting `rs.status()`**: reading PRIMARY/SECONDARY states, reachability, heartbeat info, replication progress, and abnormal indicators.

By the end of the lesson, you should be able to distinguish:

- **Replica set name** vs. database or collection name.
- **Primary** vs. **secondary** and **arbiter**.
- **Election majority of votes** vs. **completed data replication**.
- `rs.conf()` as the **desired configuration**, vs. `rs.status()` as the **observed state** at invocation time.
- **One node being DOWN** vs. **the entire replica set having no primary**.
- Safe local simulation examples vs. configurations required for production.

## 2. How Does a Replica Set Operate?

### 2.1. Primary, Secondary, and Oplog

In the basic model, a replica set has one **primary** and **secondaries**:

```text
                  MongoDB replica set "rsLab"

  Application / MongoDB driver
              |
              | Normal writes
              v
     +---------------------+
     | Node A — PRIMARY    |
     | localhost:27117     |
     +---------------------+
              |
       Oplog / replication
         /             \
        v               v
 +----------------+  +----------------+
 | Node B         |  | Node C         |
 | SECONDARY      |  | SECONDARY      |
 | localhost:27118|  | localhost:27119|
 +----------------+  +----------------+

      Nodes exchange heartbeats and participate in elections.
```

The **primary** normally receives application write operations. **Secondaries** replicate changes from the **oplog** (operation log) stream of an appropriate member and apply them to their own data. Replication is **asynchronous**, so a secondary can lag behind the primary for a short or long interval depending on load and system health.

Secondaries are not, by default, destinations for business data writes. To read from a secondary, the driver needs an appropriate read preference; such reads may see older data than the primary.

### 2.2. Electing a Primary Does Not Mean There Is Always a Primary

Voting members participate in choosing the primary. A primary requires a **majority of votes from configured voting members** to be elected and retain its position. With three members each having `votes: 1`, the majority is **two votes**.

```text
Initially:
  A PRIMARY    B SECONDARY    C SECONDARY
      1             1              1      => 3 votes

A disconnects, B and C still see each other:
  B + C = 2 votes / 3 => can elect a new primary

Only B remains, both A and C are lost:
  B = 1 vote / 3      => lacks majority to elect a primary
```

**A replica set increases availability; it does not guarantee the system always serves writes in every type of incident.** If a majority of voting members can no longer communicate with each other, the system may temporarily have no primary, and write operations depending on a primary will fail.

### 2.3. Node Count and Common Choices

| Configuration | Characteristics | Suitable For |
|---|---|---|
| 1 data-bearing member | Can be a single-member replica set; no node fault tolerance | Practice, some development environments |
| 3 data-bearing members | One primary, two secondaries when healthy; 2/3 majority | Common production model |
| 2 data-bearing + 1 arbiter | Has three votes but only two data copies | Resource-constrained cases; requires careful write concern planning |
| 5 data-bearing members | 3/5 majority, higher fault tolerance | When topology requirements and resources justify it |

More nodes is not automatically better. The number of voting members is capped; replication overhead, bandwidth, storage, sessions, cross-region latency, and operational complexity all grow with the topology.

**Recommendation for lab:** run three `mongod` processes on **one machine**, using different ports and different data directories. This model helps you learn `rs.status()`, but **is not real high availability**, because a single machine failure stops all three nodes.

## 3. Preparation Before Initialization

### 3.1. Minimum Prerequisites

Each `mongod` participating in a replica set must:

- Be configured with the same **replica set name**, e.g., `rsLab`.
- Have its **own `dbPath`**; never allow two `mongod` processes to access the same data directory.
- Have its own **`host:port`**, which other members can resolve and connect to at that exact address.
- Have a compatible MongoDB version and configuration for the topology; check version upgrade rules if mixing versions.
- Have appropriate networking, firewalls, DNS, hostnames, and clock synchronization.
- Have internal authentication and connection protection if deployed outside a lab.

The replica set name must match between startup configuration and the config passed to `rs.initiate()`. A node started with `--replSet rsOther` cannot simply join the `rsLab` configuration.

### 3.2. Distinguishing Learning Environments from Production

In the lab below:

- Three processes run on **the same machine**.
- All three bind to `127.0.0.1`/`localhost`, not exposed externally.
- Hostname `localhost` and three distinct ports are used.
- No sensitive datasets are used.
- No public network configuration is enabled that could expose an unauthenticated MongoDB to the Internet.

In production, you also need **authentication/authorization**, **internal authentication** (e.g., keyfile or x.509 per security architecture), **TLS where appropriate**, stable DNS, private networking, monitoring, backups, and a recovery plan. Do not copy unauthenticated lab commands onto public servers.

### 3.3. Hostnames Instead of Fixed IP Addresses

Members must use names that **all expected nodes and clients** can resolve and connect to. For multi-machine deployments, use stable hostnames:

```text
mongo-a.internal.example:27017
mongo-b.internal.example:27017
mongo-c.internal.example:27017
```

These names are **examples** only, not real hosts. Modern MongoDB versions include checks related to split-horizon DNS and IP-only configs; verify the hostname rules for your deployed version rather than habitually using raw IP addresses.

**Important note:** drivers discover members from the replica set configuration. If an application running on another machine connects to `localhost:27117` and the server returns `localhost:27118`, `localhost:27119`, then `localhost` on the application side points to the **application machine itself**, causing topology discovery errors. Using `localhost` is only for single-machine labs.

## 4. Starting Three `mongod` Processes on the Same Machine

This section describes a **local lab**. Commands assume MongoDB server binaries and `mongosh` are already installed. Use a fresh, separate set of directories.

### 4.1. Create Three Data Directories

PowerShell example on Windows:

```powershell
New-Item -ItemType Directory -Force -Path "C:\mongo-rs-lab\node1"
New-Item -ItemType Directory -Force -Path "C:\mongo-rs-lab\node2"
New-Item -ItemType Directory -Force -Path "C:\mongo-rs-lab\node3"
```

On Linux/macOS:

```bash
mkdir -p ~/mongo-rs-lab/node1
mkdir -p ~/mongo-rs-lab/node2
mkdir -p ~/mongo-rs-lab/node3
```

Each folder is an **independent data directory**. Never share the same `dbPath` across nodes.

### 4.2. Run Each Process in a Separate Terminal

Windows example: open **three PowerShell terminals** and run them one by one:

Terminal 1:

```powershell
mongod --replSet rsLab --port 27117 --dbpath "C:\mongo-rs-lab\node1" --bind_ip localhost
```

Terminal 2:

```powershell
mongod --replSet rsLab --port 27118 --dbpath "C:\mongo-rs-lab\node2" --bind_ip localhost
```

Terminal 3:

```powershell
mongod --replSet rsLab --port 27119 --dbpath "C:\mongo-rs-lab\node3" --bind_ip localhost
```

On Linux/macOS, replace `dbpath` with the corresponding folders under `~/mongo-rs-lab`:

```bash
# Terminal 1
mongod --replSet rsLab --port 27117 \
  --dbpath "$HOME/mongo-rs-lab/node1" \
  --bind_ip localhost

# Terminal 2
mongod --replSet rsLab --port 27118 \
  --dbpath "$HOME/mongo-rs-lab/node2" \
  --bind_ip localhost

# Terminal 3
mongod --replSet rsLab --port 27119 \
  --dbpath "$HOME/mongo-rs-lab/node3" \
  --bind_ip localhost
```

The processes run in the foreground and write logs to the terminal, so you must **keep all three terminals open** during practice. Do not run all three commands sequentially in a single foreground terminal expecting them to run in parallel.

### 4.3. Why Choose These Options?

| Option | Role |
|---|---|
| `--replSet rsLab` | Starts the node in the context of a replica set named `rsLab` |
| `--port 27117` | Selects the node's TCP port; three nodes on the same machine must use distinct ports |
| `--dbpath ...` | Storage location for that specific node's data |
| `--bind_ip localhost` | Listens only on loopback; reduces risk of access from outside the lab machine |

Starting with `--replSet` **does not mean the replica set is initialized yet**. The processes are merely ready to receive configuration and join the set.

### 4.4. Configuring via YAML File Instead of Command Line

In operational environments, file-based configuration is usually easier to manage:

```yaml
# Example for node A; path and host are for lab use only.
storage:
  dbPath: /home/student/mongo-rs-lab/node1

net:
  port: 27117
  bindIp: localhost

replication:
  replSetName: rsLab
```

Run:

```bash
mongod --config /path/to/mongod-a.conf
```

Each node needs **its own separate config file**, with its own port and `dbPath`. For production, you add security, logging, process management, storage, and other sections. Do not infer from this brief example that the file above is a complete production configuration.

## 5. Connecting to the First Node and Calling `rs.initiate()`

### 5.1. Connect with `mongosh`

Open a fourth terminal:

```bash
mongosh "mongodb://localhost:27117/?directConnection=true"
```

The `directConnection=true` parameter is useful here during initialization, when the node does not yet have an active replica set topology and we want to connect specifically to the first node. Do not use this URL as a production application config that needs automatic primary discovery and failover.

### 5.2. Initialize All Three Members at Once

In `mongosh` connected to node A:

```javascript
rs.initiate({
  _id: "rsLab",
  members: [
    {
      _id: 0,
      host: "localhost:27117",
      priority: 2
    },
    {
      _id: 1,
      host: "localhost:27118",
      priority: 1
    },
    {
      _id: 2,
      host: "localhost:27119",
      priority: 1
    }
  ]
});
```

Meaning:

- Top-level `_id: "rsLab"` is the **replica set name**, which must match `--replSet rsLab`.
- `members` is the list of desired members.
- `members[n]._id` is the **integer member identifier in the configuration**, not a document `_id`.
- `members[n].host` is **`hostname:port`** so nodes can find each other.
- `priority: 2` on A gives A higher preference in elections **when other conditions permit**; it does not guarantee A is always primary.
- B and C have `priority: 1` so they can also become primary if eligible.

Do not call `rs.initiate()` on all three nodes. **Initialize the replica set only once** with the shared config. The other nodes join using the configuration distributed by the replica set.

### 5.3. Why Wait for the Election?

`rs.initiate()` may return an acknowledgment response before all nodes are ready. After initialization:

1. Members receive the configuration.
2. Members communicate and exchange state.
3. The replica set runs a primary election if conditions are met.
4. Secondaries sync data and continue applying the oplog.

`rs.status()` may display transitional states like `STARTUP2` or `RECOVERING` initially. Do not assume any state that is not immediately SECONDARY right after `rs.initiate()` is an unrecoverable error.

### 5.4. Verify That a Primary Exists

```javascript
rs.status();
```

Once the election stabilizes, the lab's expected view is:

```text
localhost:27117   PRIMARY
localhost:27118   SECONDARY
localhost:27119   SECONDARY
```

This is **one likely outcome** because A has higher priority. However, if node A is not ready, misses heartbeats, is ineligible, or another election event occurs, the primary might temporarily be on another node. Always inspect actual state; do not build applications that hard-depend on A.

## 6. Initializing a Single-Node Replica Set for Quick Learning

If you only have one `mongod` on your learning machine, MongoDB can still run a **single-node replica set** to test features requiring a replica set configuration, such as transactions in supported setups.

Example of a lab **completely independent** of `rsLab` above:

```bash
# Run mongod with its own dbPath on port 27217.
mongod --replSet rsSingle --port 27217 \
  --dbpath "/path/to/single-node-data" \
  --bind_ip localhost
```

Once the data directory is created and the process is running, connect:

```bash
mongosh "mongodb://localhost:27217/?directConnection=true"
```

Then:

```javascript
rs.initiate({
  _id: "rsSingle",
  members: [
    { _id: 0, host: "localhost:27217" }
  ]
});

rs.status();
```

A single node can elect itself primary because it holds a majority of votes in a one-member set. However, if that process stops, **no other node remains to keep serving**. Do not mistake a "single-node replica set" for a high-availability architecture.

**Do not reuse `rsLab`'s `dbPath` for `rsSingle`.** Each example is a separate environment.

## 7. `rs.status()`: Reading the Actual State

### 7.1. Syntax

After connecting to a replica set member:

```javascript
rs.status();
```

This command provides replication status information as observed by the connected member at the time of invocation. Results can vary depending on which node is queried, heartbeat timing, and MongoDB version.

### 7.2. Illustrative Result Structure

```javascript
{
  set: "rsLab",
  date: ISODate("2026-11-14T04:00:00Z"),
  myState: 1,
  term: NumberLong("1"),
  heartbeatIntervalMillis: NumberLong("2000"),
  members: [
    {
      _id: 0,
      name: "localhost:27117",
      health: 1,
      state: 1,
      stateStr: "PRIMARY",
      uptime: 1200,
      optimeDate: ISODate("2026-11-14T03:59:59Z"),
      self: true
    },
    {
      _id: 1,
      name: "localhost:27118",
      health: 1,
      state: 2,
      stateStr: "SECONDARY",
      uptime: 1180,
      optimeDate: ISODate("2026-11-14T03:59:58Z")
    },
    {
      _id: 2,
      name: "localhost:27119",
      health: 1,
      state: 2,
      stateStr: "SECONDARY",
      uptime: 1180,
      optimeDate: ISODate("2026-11-14T03:59:58Z")
    }
  ],
  ok: 1
}
```

This is an **illustrative abbreviated version**, not the full JSON output or real lab values. MongoDB normally returns many more fields covering optimes, heartbeats, config version, sync source, elections, and storage state.

### 7.3. Top-Level Fields

| Field | Meaning |
|---|---|
| `set` | Name of the replica set the node believes it belongs to |
| `date` | Server timestamp when the status response was generated |
| `myState` | State code **of the currently connected node** |
| `term` | Election term; helps identify the election epoch in the modern protocol |
| `members` | List of status details for each member observed by this node |
| `ok` | Command execution status; `ok: 1` does not mean every member is healthy |

Specifically: **`ok: 1` only indicates the status command ran successfully**; it does not guarantee the replica set has a majority, has a primary, or is free of replication lag.

### 7.4. Per-Member Fields

| Field | Practical Meaning |
|---|---|
| `_id` | Member ID in the replica set config |
| `name` | Member's `hostname:port` |
| `health` | Observed reachability indicator; typically 1 means reachable/healthy, 0 means unreachable |
| `state` | Numeric state code |
| `stateStr` | State name, e.g., `PRIMARY`, `SECONDARY`, or `ARBITER` |
| `uptime` | Seconds the member has been running as reported |
| `optime` / `optimeDate` | Corresponding replication position/timestamp; display format varies by version |
| `lastHeartbeat` | Timestamp of recent heartbeat contact, when reported |
| `lastHeartbeatRecv` | Timestamp of recent heartbeat received, when reported |
| `lastHeartbeatMessage` | Message associated with heartbeat, useful when errors occur |
| `pingMs` | Observed heartbeat RTT |
| `syncSourceHost` | Sync source the secondary is currently using, if any |
| `self` | Indicates the entry representing the queried node itself |

Not every member and every version provides all of these fields. A missing field **is not automatically an error**; read it alongside `stateStr`, `health`, and node logs.

## 8. Common `stateStr` Values

### 8.1. PRIMARY and SECONDARY

`PRIMARY` is the member elected to accept normal writes. A healthy replica set typically has only **one primary** at any point in a configuration, and multiple secondaries ready to sync.

`SECONDARY` is a member that has entered the proper secondary state, is tracking/applying the oplog, and can participate in elections if configuration permits.

### 8.2. State Reference Table

| `state` Code | `stateStr` | Interpretation |
|---:|---|---|
| 0 | `STARTUP` | Member is starting up |
| 1 | `PRIMARY` | Current primary member |
| 2 | `SECONDARY` | Secondary member |
| 3 | `RECOVERING` | Recovering, not yet serving as a normal secondary |
| 5 | `STARTUP2` | Initialization/initial sync phase |
| 6 | `UNKNOWN` | Member state unknown from the queried node's perspective |
| 7 | `ARBITER` | Voting member that does not store the application dataset |
| 8 | `DOWN` | Member observed as unreachable |
| 9 | `ROLLBACK` | Member rolling back operations not retained in the chosen history |
| 10 | `REMOVED` | Member removed from the replica set configuration |

Other internal states may exist on specific nodes or MongoDB versions. The names above are common operational states for guidance, not an identical response prescription for every situation.

### 8.3. When Is a State Merely Transitional?

For example, after adding a new secondary, the node must perform **initial sync**:

```text
Startup -> STARTUP/STARTUP2 -> data synchronization -> SECONDARY
```

During that time, seeing `STARTUP2` is not necessarily an incident. However, if the state persists longer than expected, inspect logs, disk space, network, sync speed, data size, and sync source reachability.

Similarly, `RECOVERING` can appear during normal recovery or due to a prolonged problem. **A single state alone is not enough to diagnose the root cause.**

## 9. Filtering `rs.status()` for Easier Inspection

`rs.status()` output can be very long. In `mongosh`, we can print only key fields:

```javascript
const s = rs.status();

s.members.map(m => ({
  memberId: m._id,
  host: m.name,
  state: m.stateStr,
  health: m.health,
  optimeDate: m.optimeDate,
  syncSourceHost: m.syncSourceHost,
  lastHeartbeatMessage: m.lastHeartbeatMessage
}));
```

Example to identify the primary:

```javascript
rs.status().members
  .filter(m => m.stateStr === "PRIMARY")
  .map(m => m.name);
```

When the system is stable and has a primary, the resulting array should contain the name of the PRIMARY member as observed by the current node. If the array is empty, check further whether an election is in progress or majority votes were lost.

### 9.1. Do Not Rely on `name` for a Fixed Role

One day `localhost:27117` may be PRIMARY; another day another member is elected. Even when A is configured with higher priority, **applications should not hard-code writes to a single host**.

Connecting with a replica set URI lets the driver discover the new primary. `rs.status()` aids operational visibility; it does not replace driver topology discovery.

### 9.2. Status Observed from One Node Can Lag Behind Reality

Heartbeats are exchanged periodically and networks have latency. After a node stops, another node might not immediately update `health: 0` or `stateStr: "DOWN"`. Therefore:

- Capture status at multiple points in time when investigating an incident.
- When needed, check from both the primary and reachable secondaries.
- Combine with logs, metrics, and actual connectivity checks.
- Do not make destructive decisions based on a single transient `rs.status()` snapshot.

## 10. How Does `rs.conf()` Differ from `rs.status()`?

### 10.1. `rs.conf()` Describes Configuration

```javascript
rs.conf();
```

The output contains details like:

```javascript
{
  _id: "rsLab",
  version: 1,
  members: [
    { _id: 0, host: "localhost:27117", priority: 2, votes: 1 },
    { _id: 1, host: "localhost:27118", priority: 1, votes: 1 },
    { _id: 2, host: "localhost:27119", priority: 1, votes: 1 }
  ]
  // Other settings and metadata follow...
}
```

This structure is illustrative. `rs.conf()` describes the **configured members**, priorities, votes, and replica set settings.

### 10.2. `rs.status()` Describes Operational State

```javascript
rs.status();
```

A member B can **exist in `rs.conf()`** yet **show as DOWN in `rs.status()`**. The configuration only states that B is an intended member; it does not guarantee process B is running or reachable.

### 10.3. Comparison Table

| Question | Appropriate Command |
|---|---|
| Which hosts belong to the replica set per configuration? | `rs.conf()` |
| What are each member's current priority and votes? | `rs.conf()` |
| Which member is currently PRIMARY? | `rs.status()` or `hello` on the relevant node |
| Is node B reachable? | `rs.status()`, logs, and network checks |
| Are secondaries keeping up? | `rs.status()` and replication metrics |
| What is the configuration version? | `rs.conf().version` |

Do not alter configuration just because `rs.status()` shows a node temporarily DOWN. First determine **why it is unreachable**.

## 11. Checking Role with the `hello` Command

`rs.status()` provides broad overview information. When you only want to check whether the connected node is primary, use:

```javascript
db.adminCommand({ hello: 1 });
```

Common fields include:

- `isWritablePrimary`: whether the node is in the writable primary role under this protocol.
- `secondary`: whether the node is in the secondary role.
- `setName`: replica set name.
- `hosts`: list of replica set hosts advertised by the node, when present.
- `primary`: primary host known to the node, when present.
- `me`: host of the queried node itself.

Abbreviated example:

```javascript
{
  isWritablePrimary: true,
  secondary: false,
  setName: "rsLab",
  hosts: [
    "localhost:27117",
    "localhost:27118",
    "localhost:27119"
  ],
  primary: "localhost:27117",
  me: "localhost:27117",
  ok: 1
}
```

This is an illustrative sample; actual responses contain more fields. Older APIs may mention `isMaster`, but modern applications should use `hello`/`isWritablePrimary` per current drivers and servers.

### 11.1. Inspecting Individual Nodes in the Lab

Connect directly to secondary B:

```bash
mongosh "mongodb://localhost:27118/?directConnection=true"
```

Run:

```javascript
db.adminCommand({ hello: 1 });
rs.status();
```

A normal secondary reports `secondary: true` and `isWritablePrimary: false`. Direct inspection helps distinguish the **connected node** from the **set's primary**.

## 12. Monitoring Replication Lag and Optime

A replica set having a primary and secondaries does not guarantee every secondary has the latest data at the same instant. `rs.status()` provides fields to monitor replication progress, such as:

- `optime`: logical point reached by the node in the oplog.
- `optimeDate`: timestamp associated with the optime.
- `lastAppliedWallTime` and `lastDurableWallTime` when available: wall-clock timestamps for applied/durable operations.
- `syncSourceHost`: node that the secondary uses as its sync source.
- Replica-set-level optime/majority commit info, depending on version.

### 12.1. Example Reading Optime

```javascript
rs.status().members.map(m => ({
  member: m.name,
  state: m.stateStr,
  optimeDate: m.optimeDate,
  syncSourceHost: m.syncSourceHost
}));
```

If the primary applied an operation at 10:00:05 while a secondary is at 10:00:02, the secondary appears behind based on observation. However, comparing timestamps **is not a perfect measure of replication lag**:

- Clocks across machines must be synchronized.
- When there are no new writes, the optime timestamp may not advance.
- A secondary undergoing initial sync or recently switching sync sources may behave differently.
- Timestamp fields in specific MongoDB versions have specific semantics.

Avoid writing an alert saying "secondary is 3 seconds behind" simply by subtracting `optimeDate` from the current time without checking whether the system actually has new writes.

### 12.2. Helpers in `mongosh`

You can use common replication helpers:

```javascript
rs.printReplicationInfo();
rs.printSecondaryReplicationInfo();
```

These helpers display oplog details and secondary lag differences depending on the shell version. If a command is unsupported in a specific environment, rely on `rs.status()`, monitoring commands, and official deployment metrics.

### 12.3. Oplog Window and Initial Sync

The oplog is a capped collection storing enough operation history for secondaries to catch up to the primary unless they fall too far behind. If a secondary disconnects for a long time and the missing operations roll off the oplog, continuing normal replication may no longer be possible; the node may need a **fresh initial sync** or an appropriate recovery procedure.

Therefore, monitor not only current lag, but also the **oplog window**, write load, storage capacity, recovery time, and connectivity. A secondary that has fallen far behind cannot be fixed simply by raising `priority`.

## 13. Member Configuration: `priority` and `votes`

### 13.1. `priority` Controls Election Preference

In the initial configuration:

```javascript
members: [
  { _id: 0, host: "localhost:27117", priority: 2 },
  { _id: 1, host: "localhost:27118", priority: 1 },
  { _id: 2, host: "localhost:27119", priority: 1 }
]
```

The `priority` value affects which member is preferred as primary. A member with `priority: 0` **cannot be elected primary**.

Do not interpret:

```text
priority = 2
```

as the member having **two votes**. Priority and votes are **two different properties**.

### 13.2. `votes` Determines Voting Rights

Typically:

```javascript
{ host: "mongo-b.example:27017", priority: 1, votes: 1 }
```

A member with `votes: 1` is a voting member. If `votes: 0`, that member does not participate in normal voting and must have `priority: 0`.

MongoDB limits a replica set to **at most seven voting members**; a configuration can include more members overall, though not all may have voting rights. Do not use `votes: 2` to "give extra votes" to a node: a member's vote count is 0 or 1 per configuration rules.

### 13.3. Combination Rules to Remember

| Configuration | Can Be Elected PRIMARY? | Has a Vote? |
|---|---|---|
| `priority: 1, votes: 1` | Yes, if eligible | Yes |
| `priority: 2, votes: 1` | Yes; higher preference | Yes |
| `priority: 0, votes: 1` | No | Yes |
| `priority: 0, votes: 0` | No | No |
| `priority: 1, votes: 0` | Invalid configuration per standard constraints | No |

**Priority does not determine percentage of synced data.** A member with high priority that is ineligible or lagging may still not be elected.

### 13.4. Impact of Changing Priority

Changing priority can trigger a new election or primary transfer when conditions allow. Thus, even an operation that looks like "just editing metadata" can cause **temporary write disruption**.

Do not adjust priorities en masse during peak hours without assessing majority, replication lag, and impact on driver connections.

## 14. `rs.add()` and `rs.addArb()`: Adding Members

### 14.1. Adding a New Secondary

Suppose the set is currently initialized with **two** data-bearing members A and B, and you just started a new `mongod` C with the same replica set name on port 27119. You can connect to the primary and run:

```javascript
rs.add({
  host: "localhost:27119",
  priority: 0,
  votes: 0
});
```

**This is a separate scenario** from the three-node `rs.initiate()` in section 5; if you already included C in `rs.initiate()`, **do not run `rs.add()` again for C**.

This example initially sets `priority: 0, votes: 0` so the node can complete initial sync before the administrator evaluates whether to let it participate in elections. Once the node stabilizes, you can consider updating `votes`/`priority` per the target topology.

If the new node is syncing a large dataset, its state may progress from `STARTUP2` to `SECONDARY`. Monitor `rs.status()` and initial sync progress; do not assume it has full data immediately after `rs.add()`.

### 14.2. Adding with a Simple Hostname

With appropriate default settings, MongoDB also permits:

```javascript
rs.add("mongo-d.internal.example:27017");
```

This address is an example only. The new member must be a previously prepared `mongod` process reachable by other members; `rs.add()` **does not install or start a new MongoDB machine by itself**.

### 14.3. What Is an Arbiter?

An **arbiter** has the right to participate in **elections** but **does not store application data like a primary/secondary**:

```text
  A — PRIMARY          B — SECONDARY
      (data)               (data)
         \                  /
          \                /
            C — ARBITER
             (vote only)
```

Helper:

```javascript
rs.addArb("mongo-arb.internal.example:27017");
```

An arbiter can help achieve a voting majority in certain resource-constrained cases, yet **does not create an extra data copy** and cannot be elected primary. A 2 data-bearing + 1 arbiter (PSA) topology carries significant trade-offs regarding majority write concern and write durability when one data node becomes unavailable. For systems needing high availability and write durability, **three data-bearing members** are generally the better choice.

Do not use an arbiter as the default solution for every high-availability problem or to mask network issues.

### 14.4. Hidden Secondary

A hidden secondary:

- Stores data like a secondary.
- Cannot be elected primary, so it requires `priority: 0`.
- Is not advertised as a normal read member in topology discovery per replica set rules.
- Can be useful for specialized workloads such as backups/reporting depending on architecture and direct connection handling.

Example configuration for a dedicated member:

```javascript
{
  _id: 3,
  host: "mongo-hidden.internal.example:27017",
  priority: 0,
  hidden: true,
  votes: 0
}
```

Do not apply this example directly to a running lab config without creating an actual node first. If a hidden member is targeted for direct reads for a specialized task, you must understand read preference and potential effects on data freshness.

### 14.5. Delayed Secondary

A secondary can be configured to **delay applying the oplog** using `secondaryDelaySecs` in supported versions. It can be useful to provide a buffer window against certain operational mistakes, yet **does not replace backups** and does not by itself recover from all data errors.

Conceptual configuration example:

```javascript
{
  _id: 4,
  host: "mongo-delayed.internal.example:27017",
  priority: 0,
  hidden: true,
  secondaryDelaySecs: 3600,
  votes: 0
}
```

The `secondaryDelaySecs` field and associated rules depend on the MongoDB version. You must verify the oplog window, storage capacity, suitability of an intentionally lagging node, and write concern impact when choosing votes.

## 15. `rs.reconfig()`: Modifying Replica Set Configuration

### 15.1. Why Is Reconfiguration Needed?

After a replica set is running, you may need to:

- Adjust a member's `priority`.
- Add/remove voting roles, hide a secondary, or modify member settings.
- Change hostnames during infrastructure migration.
- Adjust replica set settings per operational plans.

`rs.reconfig()` is a powerful command because **member configuration directly affects elections and writability**. Use it only after confirming the current configuration and majority state.

### 15.2. Example Changing a Member's Priority

Connect to the primary and run:

```javascript
const cfg = rs.conf();

const memberB = cfg.members.find(
  m => m.host === "localhost:27118"
);

if (!memberB) {
  throw new Error("Member B not found in rs.conf()");
}

memberB.priority = 0;

rs.reconfig(cfg);
```

Afterward:

```javascript
rs.conf().members.map(m => ({
  host: m.host,
  priority: m.priority,
  votes: m.votes
}));

rs.status().members.map(m => ({
  host: m.name,
  state: m.stateStr,
  health: m.health
}));
```

With `priority: 0`, member B cannot be elected primary, yet can still act as a secondary syncing data and voting if `votes: 1`.

This example illustrates the technique and should **only be run in a lab**, as changing election eligibility of production nodes must be planned.

### 15.3. `rs.reconfig()` Can Trigger an Election

A reconfiguration can cause the current primary to step down or trigger a new election, depending on the change. The driver needs time to pick up the new topology and route writes to the new primary.

In production deployments:

1. Observe `rs.status()` and replication lag.
2. Verify sufficient majority remains active after the change.
3. Record the configuration prior to changing.
4. Change few voting members at a time per MongoDB version constraints.
5. Monitor state after reconfiguration and ensure application failover works.

Do not use `rs.reconfig(cfg, { force: true })` as a way to "force a healthy cluster" when majority is lost. **Force reconfig** carries risks of diverging history, rollbacks, or losing unacknowledged writes; consider it only inside a carefully evaluated disaster recovery procedure.

### 15.4. Removing a Member with `rs.remove()`

Syntax example:

```javascript
rs.remove("localhost:27119");
```

This command alters replica set membership. **Do not use it as a fix for a temporarily DOWN secondary.** If you need to maintain or replace a node:

- Check whether the remaining nodes still have majority.
- Recalculate voting members and majority votes after the change.
- Consider data safety and election conditions.
- Remove only when that is genuinely the intended topology change.

A removed node does not automatically lose its data on disk; cleaning up a data directory is a separate, potentially destructive action outside normal configuration management.

## 16. Connecting Applications via Replica Set URI

A common operational mistake is configuring an application to connect only to **a single fixed node address**:

```text
mongodb://mongo-a.internal.example:27017
```

When the primary moves to another node, the application needs a driver capable of **discovering topology and routing operations**. An illustrative replica set URI:

```text
mongodb://mongo-a.internal.example:27017,mongo-b.internal.example:27017,mongo-c.internal.example:27017/?replicaSet=rsProduction
```

In the lab:

```text
mongodb://localhost:27117,localhost:27118,localhost:27119/?replicaSet=rsLab
```

In this URI:

- The host list is a **seed list** helping the driver locate the replica set, not a fixed rule that "the first host is always primary."
- `replicaSet=rsLab` specifies the expected set name.
- The driver validates the topology and discovers members from the server.
- Hosts advertised by the server must be resolvable from the **application machine**.

For production, the URI also requires credentials, authentication mechanism, TLS, and appropriate timeout/read preference settings. Avoid embedding passwords directly in source code or logs.

### 16.1. Java Sync Driver Example

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

public class ReplicaSetReadExample {
    public static void main(String[] args) {
        String uri =
            "mongodb://localhost:27117,localhost:27118,localhost:27119/" +
            "?replicaSet=rsLab";

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> sample = client
                .getDatabase("rsLesson")
                .getCollection("events");

            sample.insertOne(new Document("type", "APP_STARTED"));
            System.out.println(sample.countDocuments());
        }
    }
}
```

This example is for a lab without authentication enabled. In real environments, create appropriate users and privileges, use a secret manager, and secure connections. The driver handles selection/retries within supported capabilities, yet the application must still handle exceptions when no primary exists or write concern fails.

### 16.2. Can You Read from a Secondary?

MongoDB supports read preferences such as `primary` (commonly default) and secondary read options when appropriate. However:

- Secondaries can lag, so data is not guaranteed to be the latest.
- Do not use secondary reads to guarantee "read-your-own-writes immediately" without designing causal consistency and suitable read policies.
- Another read preference does not turn a secondary into a writable primary.
- Secondary reads can offload some primary load, yet can also slow down a secondary's replication if overloaded.

Choose read preference based on consistency and latency requirements, not merely to "even out request counts."

## 17. Write Concern, Majority, and Durability

**Electing a primary** and **confirming a write has been replicated** are two distinct issues.

### 17.1. The Concept of `w: "majority"`

When an application requests majority write concern, the write must be acknowledged according to the replica set's majority criteria. This is an important part of reducing the risk that acknowledged data gets rolled back during a primary transition, per MongoDB's guarantees.

Example in `mongosh`:

```javascript
db.getSiblingDB("rsLesson").events.insertOne(
  { type: "PAYMENT_CONFIRMED", createdAt: new Date() },
  { writeConcern: { w: "majority", wtimeout: 10000 } }
);
```

This snippet only illustrates how to request majority write concern; it does not mean every such operation will succeed when the cluster lacks votes or secondaries fail to keep up.

### 17.2. Majority Votes Do Not Mean Majority Data-Bearing Members

In the topology:

```text
P (data) + S (data) + A (arbiter)
```

The arbiter can vote to elect a primary, yet **does not store write operations** like a data-bearing secondary. This creates significant trade-offs when performing majority writes on a PSA configuration, especially if one of the two data nodes becomes unavailable.

Do not conclude "two out of three nodes are alive so all majority writes are safe and can continue." You must know **which nodes hold data**, write concern rules, journaling, topology, and the active incident.

### 17.3. When the Primary Stops Before a Write Is Replicated

If a write is acknowledged only on the primary without reaching the durability/replication level required by the business, a failover event may result in that write not being present on the new primary, and the old member may have to roll back part of its history.

Therefore, a replica set **does not replace** choosing an appropriate write concern for critical transactions. Conversely, requiring majority can increase latency and require enough members to acknowledge; balance this against application goals.

## 18. Replica Set Security: From Lab to Production

### 18.1. Why Does the Lab Bind Only to Localhost?

The lab commands use:

```text
--bind_ip localhost
```

to avoid exposing the MongoDB port to external networks. Using `--bind_ip_all` or `0.0.0.0` without authentication/firewalling can expose the database to unauthorized access from any machine able to reach the port.

Do not copy network-opening flags into production merely to let members talk to one another.

### 18.2. Internal Authentication Between Nodes

In a secured production configuration, `mongod` instances in a replica set must authenticate with each other. One common option is a **keyfile** distributed securely to participating nodes, with restricted file permissions per platform requirements and identical secret contents.

Conceptual configuration example:

```yaml
security:
  authorization: enabled
  keyFile: /secure/path/rs-keyfile

replication:
  replSetName: rsProduction
```

This YAML snippet is not a complete guide for creating credentials, distributing secrets, or bootstrapping users. In practice, you need plans for administrative users, roles, rotation, application accounts, TLS, firewalls, and secret storage. **Never commit keyfile contents into documentation, git repositories, or logs.**

### 18.3. TLS and Network Trust Boundaries

When nodes reside on different machines/zones, traffic must be protected according to security policy. TLS, hostname verification, certificate management, and network routing configuration are essential elements in many production deployments.

Do not treat the fact that a replica set elects a primary as proof that data is encrypted in transit or that only authorized parties can access the database.

### 18.4. Backups Remain Essential

A replica set replicates **unwanted changes as well** (e.g., accidental deletions, mass erroneous updates). It is not a backup capable of rolling back to an arbitrary point in time.

A production plan needs backups, verified restores, off-infrastructure copy retention, and data recovery policies for human or application errors.

## 19. Troubleshooting Common Errors When `rs.initiate()` or `rs.status()` Behaves Unexpectedly

### 19.1. Error: Server Not Started with `--replSet`

If you start a normal `mongod` and call `rs.initiate()` or `rs.status()`, the server may report it is not running in replication mode.

Check:

- Does the startup option include `--replSet rsLab`?
- Does the config file have `replication.replSetName: rsLab`?
- Are you connected to the right replica set node's port rather than another standalone `mongod`?

The fix is to **start the process with the correct replication configuration**, not call `rs.initiate()` repeatedly to "retry."

### 19.2. Error: Replica Set Name Mismatch

`--replSet rsLab` combined with `rs.initiate({ _id: "wrongName", ... })` can cause an error or rejected configuration.

Ensure the set name matches across startup, `rs.initiate()`, and client URIs. If old data/config already exists on `dbPath`, inspect node history before changing; **do not delete the data directory to fix errors in production**.

### 19.3. Error: Members Cannot Connect to Each Other

In `rs.status()`, you might see:

```javascript
{
  name: "mongo-b.internal.example:27017",
  health: 0,
  stateStr: "DOWN",
  lastHeartbeatMessage: "..."
}
```

Common causes:

- Hostname does not resolve from one or more nodes.
- Port is not listening, blocked by a firewall, or `mongod` is not running.
- `bindIp` does not allow connections from other members.
- Mismatched keyfile/TLS/internal authentication configuration.
- Cross-zone network issues or excessive latency.
- Node is overloaded or taking a long time to start.

Do not rush to run `rs.remove()` just to clear a DOWN indicator from the screen. First check connectivity and logs.

### 19.4. Error: No PRIMARY

For example, only one voting node remains in a three-voting-member set:

```text
A (DOWN)    B (SECONDARY)    C (DOWN)
```

Node B may be healthy yet **lack majority** to elect itself primary. In this state, normal write commands will fail.

Steps to take:

1. Identify which nodes are alive and hold votes.
2. Check networking to see whether nodes can reach each other.
3. Restore nodes or network paths to regain majority where possible.
4. Read election logs and `rs.status()`.
5. Avoid using force reconfig or initializing a new replica set over old data without a disaster recovery procedure.

**A healthy secondary cannot unilaterally become primary when election conditions are not met.**

### 19.5. Error: Repeated Elections

If primary keeps bouncing between nodes, check:

- Is the network between voting members stable?
- Is CPU/disk overload delaying heartbeats?
- Are system clocks synchronized?
- Do priority and votes create conflicting expectations?
- Is automation or an administrator repeatedly running reconfigurations/stepDown?
- Are there underlying infrastructure, cloud, or container scheduler failover events?

Do not crank one node's priority very high as a substitute for fixing networking or storage.

### 19.6. Error: Secondary Stuck in STARTUP2/RECOVERING for Long Periods

Investigate:

- Is initial sync running and how far has it progressed?
- Is the sync source's oplog window large enough?
- Does the data size exceed what can sync within the expected timeframe?
- Does the disk have sufficient space and speed?
- Are permissions, security settings, or networking blocking replication?
- Are there specific errors in the logs?

**Do not delete secondary data or re-seed haphazardly** simply because `rs.status()` does not show SECONDARY yet.

### 19.7. Error: Application Connects to Only One Host and Fails to Failover

If a URI uses `directConnection=true` to an old secondary node, the driver may not discover the primary as expected. For applications needing failover, use a **replica set URI** containing a seed list and `replicaSet`, ensuring advertised hostnames resolve from the application.

Do not use `localhost` URIs across remote containers/machines when server and client are not in the same network namespace.

## 20. Safe Operational Procedure for Adding/Removing/Replacing Members

A production replica set change plan should address:

### Step 1 — Record Configuration and Status

```javascript
rs.conf();
rs.status();
db.adminCommand({ hello: 1 });
```

Record set name, member list, priorities/votes, current primary, replication status, and vote majority.

### Step 2 — Define the Change Objective

Examples:

- Add a secondary to increase data copies.
- Replace a server with failed hardware.
- Move a member to a different availability zone.
- Create a hidden secondary for a dedicated workload.
- Adjust priority after evaluating election behavior.

**Do not modify configuration merely because a command can execute.**

### Step 3 — Prepare the New Server Independently

Prepare `dbPath`, compatible version, DNS, firewalls, internal authentication, monitoring, and capacity. Never let the new server share data files with a running old server.

### Step 4 — Change Few Members at a Time and Monitor

Use `rs.add()`, `rs.remove()`, or `rs.reconfig()` as appropriate. Avoid simultaneous voting member changes unsupported by your version/configuration. After each change:

```javascript
rs.conf();
rs.status();
```

Wait for the new member to finish initial sync, replication lag to stabilize, and majority to remain intact.

### Step 5 — Verify Application Behavior

Confirm the driver:

- Sees the current primary.
- Can execute reads/writes per permissions and write concern.
- Survives controlled failover according to application requirements.
- Does not depend on the previous primary's hostname/port.

### Step 6 — Prepare Rollback and Recovery

Save before/after configs and status evidence. If a change causes issues, revert using a **controlled procedure**, without running force commands or wiping data directories to shortcut recovery.

## 21. Anti-Patterns in Replica Set Administration

| Anti-Pattern | Why It Is Dangerous | Correct Mindset |
|---|---|---|
| Calling `rs.initiate()` on every node | Independent initialization breaks set configuration | Initialize the set once; nodes share the config |
| Sharing `dbPath` across multiple `mongod`s | Contention/data corruption risk | One dedicated `dbPath` per process |
| Advertising `localhost` in multi-host production | Remote nodes/clients interpret localhost differently | Use hostnames resolvable across the entire topology |
| Exposing `0.0.0.0` unsecured | Exposes data over the network | Configure authentication, firewalls, and TLS properly |
| Assuming high-priority node is always primary | Elections also depend on node health/majority | Read actual role via `hello`/`rs.status()` |
| Assuming `votes: 1` means it holds data | Arbiters also vote without storing data | Distinguish voting from data-bearing |
| Assuming `health: 1` means synced up to primary | Health mainly reflects node reachability | Monitor optime/lag and state |
| Seeing `ok: 1` and concluding cluster is healthy | A successful command can still report DOWN nodes | Inspect every member and primary/quorum |
| Removing a member immediately when DOWN | Can alter majority and break failover | Investigate network/process first |
| Using `force: true` to fix every config error | Risks losing writes or diverging history | Use only in planned disaster recovery |
| Adding an arbiter thinking you added a data copy | Arbiters do not store application data | Prefer data-bearing members when redundancy is needed |
| Reading secondary assuming it is as fresh as primary | Replication is asynchronous and can lag | Pick read preference/consistency per requirement |
| Treating replica set as backup | Accidental deletes also replicate | Maintain independent backups/restores |
| Connecting application via a fixed direct host | Cannot discover a new primary automatically | Use a replica set URI |
| Measuring lag solely as current time minus optime | Can trigger false alerts when there are no writes | Combine optime, write activity, and metrics |
| Tweaking priority mid-incident without root cause | Can cause additional disruptive elections | Analyze majority, logs, network, and storage |

## 22. Hands-On Exercises

### Exercise 1 — Local Three-Node Initialization

Create three separate data directories and run `mongod` on ports 27117, 27118, and 27119 with `--replSet rsLab`. Then:

1. Connect to node A with `mongosh`.
2. Call `rs.initiate()` with all three members.
3. Check `rs.status()` until there is a PRIMARY and secondaries are ready.
4. Record the PRIMARY node name, member IDs, and health values.
5. Run `rs.conf()` to verify member count and priorities.

Explain why three nodes on one machine help learn operations but cannot tolerate physical single-machine failure.

### Exercise 2 — Distinguishing `rs.conf()` and `rs.status()`

Suppose `rs.conf()` shows:

```javascript
[
  { _id: 0, host: "A:27017", priority: 2, votes: 1 },
  { _id: 1, host: "B:27017", priority: 1, votes: 1 },
  { _id: 2, host: "C:27017", priority: 1, votes: 1 }
]
```

Yet `rs.status()` on A shows B as `DOWN`. Answer:

- Is B still a configured member?
- Why is B not necessarily removed?
- What kinds of failures could make B unreachable?
- Should you immediately call `rs.remove("B:27017")`?

### Exercise 3 — Calculating Majority

With three voting members, calculate the votes needed to elect a primary when:

1. All three are active.
2. One node is lost.
3. Two nodes are lost.

Then compare with a five-voting-member set. Why does a replica set with two voting members usually have worse availability than three voting members when one node fails?

### Exercise 4 — `priority` Differs from `votes`

Analyze the four configurations:

```javascript
{ priority: 2, votes: 1 }
{ priority: 1, votes: 1 }
{ priority: 0, votes: 1 }
{ priority: 0, votes: 0 }
```

Which members can be elected primary? Which member can still vote even though it cannot become primary? Why can you not interpret `priority: 2` as two votes?

### Exercise 5 — Stopping a Secondary in the Lab

In the **three-node local lab**, stop only the terminal running node C on port 27119 (without deleting data). Then observe:

```javascript
rs.status();
```

Record:

- What state does member C transition to as observed after heartbeats?
- Does the primary still serve writes while the other two voting members are running?
- When restarting C with the same `dbPath` and `replSetName`, how does its state change?
- Why might you need to wait for replication catch-up?

Perform this in the lab only. Do not stop a production node without a fault-tolerance plan.

### Exercise 6 — Simulating Loss of Majority

**No need to actually stop two nodes** if you do not want to disrupt the lab. Starting from a three-voting-member model, analyze the case where A and C are DOWN, leaving only B.

- Can B elect itself primary?
- What problem will a write-performing driver encounter?
- Why can a secondary remain locally healthy yet fail election eligibility?
- Should you prioritize restoring network/nodes or using `force`?

### Exercise 7 — Reading Fields in `rs.status()`

Write a `mongosh` snippet to print the fields:

```javascript
{
  host: "...",
  health: 1,
  state: "SECONDARY",
  optimeDate: ISODate("..."),
  syncSourceHost: "..."
}
```

from `rs.status().members`. Explain which field describes reachability, which describes role, and which helps inspect replication progress. Can you conclude a secondary has no lag solely because `health: 1`?

### Exercise 8 — Designing an Application URI

Given a production set:

```text
rsShop
mongo-a.internal.example:27017
mongo-b.internal.example:27017
mongo-c.internal.example:27017
```

Write a URI so the driver discovers all three members. Explain:

- The effect of `replicaSet=rsShop`.
- Why the first host is not necessarily the primary.
- Why `localhost` should not be used when the client is on another machine.
- Which security settings must be configured beyond the demo URI.

### Exercise 9 — Adding a Secondary and Checking Initial Sync

Suppose a set already has A and B, and needs C added:

1. Prepare process C with its own `dbPath` and the same `replSetName`.
2. Call `rs.add()` from the primary.
3. Observe the states C may pass through before `SECONDARY`.
4. When should you consider increasing `votes` or `priority`?
5. Why check the oplog window, storage capacity, and sync speed?

### Exercise 10 — Comparing PSS and PSA

Two topologies:

```text
PSS = Primary + Secondary + Secondary
PSA = Primary + Secondary + Arbiter
```

Analyze:

- How many data-bearing members does each topology have?
- How many voting members can each topology have?
- If the data secondary is lost, how might majority write acknowledgment capability differ?
- Why must an arbiter not be used as a substitute for a data copy?

### Exercise 11 — Config Changes That Can Cause Unavailability

An administrator wants to set two out of three members to `votes: 0` in a single operation. Explain why voting majority should be recalculated and reconfiguration limits followed before editing. Propose a procedure for preparation, config backup, step-by-step changes, monitoring, and application verification.

### Exercise 12 — Diagnosing Connection Errors

Suppose:

```text
MongoDB Node A: mongo-a.internal.example:27017
MongoDB Node B: mongo-b.internal.example:27017
MongoDB Node C: mongo-c.internal.example:27017
Application runs on another container.
```

The application connects to seed A successfully but subsequently fails when the driver tries to connect to B and C. List the possibilities:

- Hostnames B/C do not resolve from the container.
- Firewall/network policy blocks port connections.
- Server advertises unsuitable hostnames.
- Mismatched TLS, auth, or `replicaSetName` configuration.

Explain why this may be a **topology discovery** error rather than MongoDB having lost data.

## 23. Summary

**A replica set is a group of `mongod` instances that jointly manage data copies and participate in primary elections.** A common topology has three data-bearing members; to elect and maintain a primary, voting members must hold a majority of votes. Replication is asynchronous, so never confuse reachability with having replicated every write.

**Proper initialization starts per node:** identical `replSetName`, a separate `dbPath` per node, mutually reachable host/port, and appropriate security. Then call `rs.initiate()` **once**, wait for the election, and observe transitional states instead of assuming a primary appears instantaneously.

**`rs.conf()` is configuration; `rs.status()` is reality.** Use `rs.conf()` to view members/priority/votes; use `rs.status()` to view PRIMARY/SECONDARY, health, heartbeats, and replication progress; use `db.adminCommand({ hello: 1 })` to identify the connected node's role.

**Changing members changes availability.** `rs.add()`, `rs.addArb()`, `rs.remove()`, and `rs.reconfig()` can alter elections, voting majority, and data safety. Never force reconfig, remove members, or wipe data directories as a knee-jerk reaction when a node is DOWN.

**A reliable replica set requires more than syntactically valid commands:** stable hostnames/DNS, internal authentication, secure networking, appropriate write concerns, replication lag monitoring, backups, and clear failover/recovery procedures. When you master the three pillars—**initialization — configuration — status inspection**—you can operate replica sets with decisions grounded in actual state rather than hostnames or fixed assumptions.
