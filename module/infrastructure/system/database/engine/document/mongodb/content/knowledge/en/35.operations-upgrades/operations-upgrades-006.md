# Rolling Upgrades, Feature Compatibility Version, and Downgrade Conditions in MongoDB

## 1. Why Is Upgrading MongoDB More Than Replacing a Binary?

Imagine an ordering application running on a three-node MongoDB replica set:

```text
                     Application
                          |
                          v
                  MongoDB Replica Set
                          |
          +---------------+---------------+
          |               |               |
          v               v               v
      Node A          Node B          Node C
      PRIMARY         SECONDARY       SECONDARY
      MongoDB 7.0     MongoDB 7.0     MongoDB 7.0
```

The operations team wants to upgrade to MongoDB 8.0 for patches, performance gains, and new features. Stopping all three nodes at once to install 8.0 takes the entire system offline. Upgrading one node without checking compatibility can leave a node unable to start or resume replication.

Even after all three processes run MongoDB 8.0, the job is not finished: the database may still use **Feature Compatibility Version (FCV) 7.0**. Once you raise FCV to 8.0, certain features can begin persisting metadata or data in formats incompatible with older releases. That makes **downgrading** harder or unsupported under the release policy.

This lesson clarifies three related yet **distinct** operations:

1. **Rolling upgrade:** replacing binaries member by member in sequence to preserve quorum and minimize disruption.
2. **Raising FCV:** activating newer features or on-disk formats that may be backward-incompatible, after the entire deployment has been upgraded.
3. **Downgrade/rollback:** returning to an older version **only when the downgrade path is officially supported and data, FCV, and topology preconditions are met**.

> **Key principle:** The running binary version, FCV, and downgrade eligibility are three separate things to verify. Never conclude "rollback is possible" merely because you just swapped binaries or still have a backup.

---

## 2. Scope and Version Notes

The primary examples illustrate upgrading **MongoDB 7.0 → 8.0** on a **self-managed replica set**, as it provides a clear official rolling upgrade procedure.

This lesson also covers policy changes in the **8.3 and 9.0** lines, without treating one static runbook as valid for every release:

- For **MongoDB 8.0 → 7.0**, 8.0 documentation states **Community Edition does not support binary downgrades**, while Enterprise requires working with MongoDB Support.
- **Starting with MongoDB 8.3**, documentation describes downgrade support to an adjacent minor or major release along supported paths.
- For **MongoDB 9.0**, downgrade guides document dedicated paths to 8.3 or conditionally to 8.0 as specified.
- MongoDB Atlas, Ops Manager, and Cloud Manager have **their own version management workflows**; never apply all self-managed commands blindly to managed clusters.
- Releases can change features, FCV prerequisites, mandatory parameters, and topology support.

**Never use this lesson as an automated production upgrade/downgrade script.** Before acting, consult the official documentation matching your **source version, target version, edition, deployment type, FCV, and active features**.

---

## 3. Core Concepts

| Concept | Meaning | Example |
| --- | --- | --- |
| **Binary version** | Running `mongod`/`mongos` software version | `8.0.x` |
| **Patch release** | Bug-fix release within the same series | `8.0.a → 8.0.b` |
| **Major/minor release** | Release milestone with potential feature/compatibility changes | `7.0 → 8.0` |
| **FCV** | Feature Compatibility Version, gating features that persist data incompatible with prior releases | `"7.0"` or `"8.0"` |
| **Rolling upgrade** | Upgrading one node at a time, waiting for stability before the next | Secondary B, secondary C, former primary A |
| **Mixed-version state** | Members temporarily running different binary versions mid-upgrade | A=7.0; B/C=8.0 |
| **Primary stepdown** | Transitioning the primary to secondary so the replica set elects a new primary | `rs.stepDown()` |
| **Quorum/majority** | Voting members required for elections, and data-bearing majority for certain operations | 2/3 voting members |
| **Burn-in period** | Observation window on new binaries before raising FCV | Several days per policy |
| **Downgrade path** | Officially supported path to step down to an older version | Depends on release/edition |
| **Rollback plan** | Response strategy if an upgrade fails—does not always mean binary downgrade | Config fix, node replacement, restore |
| **Backup restore** | Recovering state from backup when binary downgrade is unavailable | Snapshot + PITR |

### 3.1. Upgrade Rollback Differs from Replication Rollback

MongoDB also uses the term **rollback** when a replica set node discards uncommitted writes after replication history diverges. That is a **replica set rollback**.

In this lesson, "upgrade rollback" means **returning to a prior deployment state or version**. The two concepts have different semantics and neither replaces the other.

---

## 4. Separating Binary Version from Feature Compatibility Version

A deployment can run:

```text
mongod binary: MongoDB 8.0.x
FCV:           7.0
```

This is an **intentional state after upgrading binaries from 7.0 to 8.0**. Documentation allows running 8.0 binaries on the older FCV during an evaluation window before enabling features that write data incompatible with 7.0.

After the burn-in period, operators can raise it to:

```text
mongod binary: MongoDB 8.0.x
FCV:           8.0
```

Now features gated by FCV 8.0 can be enabled as documented.

### 4.1. Why Does MongoDB Need FCV?

If a new binary immediately wrote catalog, index, or metadata structures understood only by the new version, reverting to the old binary would break right at startup.

FCV creates a **controlled transition phase**:

```text
        Replace binaries             Enable incompatible features
              |                                 |
              v                                 v

7.0 binary / 7.0 FCV
          |
          v
8.0 binary / 7.0 FCV  ---- burn-in ---->  8.0 binary / 8.0 FCV
          |                                 |
          |                           Downgrade risk grows
          v
Potential fallback, only when
release policy permits
```

### 4.2. FCV Does Not Fully Emulate the Old Binary

Running MongoDB 8.0 at FCV 7.0 **does not turn 8.0 into MongoDB 7.0**:

- The runtime and query planner may have changed.
- 8.0 behaviors and bug fixes are active.
- Wire protocols, startup options, and driver interactions still require verification.
- Not every new feature is gated by FCV.
- An older FCV does not automatically grant binary downgrade permission under release policy.

---

## 5. Checking Binary Version and FCV

### 5.1. Check Server Binary Version

In `mongosh`:

```javascript
db.version();
```

Or:

```javascript
db.adminCommand({ buildInfo: 1 });
```

On a self-managed host:

```bash
mongod --version
mongos --version
```

**Note:** `PATH` may point to a newly installed binary while the **currently running process** still executes the older binary. To verify the effective running version, query the running server node and inspect process details.

### 5.2. Check FCV

Run in `mongosh` with required privileges:

```javascript
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
});
```

Typical output in steady state:

```javascript
{
  featureCompatibilityVersion: {
    version: "7.0"
  },
  ok: 1
}
```

During a transition, output may include fields such as `targetVersion` or intermediate states depending on release. Do not read `version` alone and assume transition is finished.

### 5.3. Check Every Replica Set Member

Run against each node or via appropriate automation:

```javascript
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
});
```

Confirm that **all members report the expected FCV and none are stuck mid-transition**.

---

## 6. What Is a Rolling Upgrade?

For a replica set with three data-bearing members:

```text
Before upgrade:
  A PRIMARY   7.0
  B SECONDARY 7.0
  C SECONDARY 7.0

Step 1:
  A PRIMARY   7.0
  B SECONDARY 8.0
  C SECONDARY 7.0

Step 2:
  A PRIMARY   7.0
  B SECONDARY 8.0
  C SECONDARY 8.0

Step 3:
  Step down A, elect B/C as PRIMARY.

Step 4:
  A SECONDARY 8.0
  B/C running 8.0

Step 5:
  Stabilize, observe, then raise FCV to 8.0.
```

The core principle is **never taking too many nodes down together**. The replica set must retain enough members to sustain a primary and satisfy application write concerns.

### 6.1. Rolling Upgrades Minimize Downtime, Not Promises of Zero Interruption

When stepping down a primary:

- Elections can briefly interrupt writes.
- Existing TCP connections, cursors, and transactions may be affected.
- Drivers rely on server discovery and retries.
- Non-idempotent operations need explicit protection.
- Some change streams may need to resume.

Thus "rolling" means **avoiding full planned deployment downtime**, not guaranteeing zero impact on every in-flight request.

---

## 7. Before Upgrading: A Reliable Baseline

Capture current state:

| Group | What to Record |
| --- | --- |
| Versions | Per-node binary, FCV, driver versions, tools |
| Topology | Node names, `PRIMARY`/`SECONDARY`, votes, priorities, hidden/delayed members |
| Replication | Majority availability, replication lag, oplog window |
| Storage | Free disk, IOPS, WiredTiger cache, filesystem |
| Queries | p50/p95/p99, slow queries, index usage |
| Cluster workload | Read/write throughput, transactions, connections |
| Security | TLS, auth, KMIP/KMS, auditing |
| Backup | Last successful backup, PITR window, restore drill |
| Applications | Driver/ORM compatibility, deprecations, feature usage |
| Automation | Package repositories, config files, service managers, IaC |
| External integrations | CDC connectors, BI, ETL, Search, monitoring, backup agents |

### 7.1. Define Non-Negotiable Invariants

Examples:

- Never lose the ability for a majority of members to acknowledge writes.
- Never allow replication lag to exceed RPO policy.
- Never alter TLS/key permissions mid-rollout without verification.
- Never enable new features/FCV before binary upgrade finishes.
- Never downgrade binaries against policy.

---

## 8. Planning a Valid Version Upgrade Path

Never jump arbitrarily from a much older binary to a new one simply by swapping executables.

Example for **7.0 → 8.0**:

```text
MongoDB 6.0
    |
    v
MongoDB 7.0
    |
    v
MongoDB 8.0
```

MongoDB 8.0 documentation requires the source to be on the **7.0-series** before upgrading to 8.0. If running 6.0, upgrade through each required release step.

### 8.1. Changing Release Cadence in 8.x and 9.0

MongoDB now distinguishes major, minor, feature updates, and patch releases. When planning a path:

- Check whether source and target are adjacent releases.
- Check whether a release targets self-managed deployments or specific Atlas tracks.
- Check whether intermediate minor hops are mandatory per release line policy.
- Never assume from version numbers that intermediate releases can be skipped.
- Target a recommended, supported patch release.

For example, with 9.0, official docs provide guides to 9.0 from supported source branches. Always open the **exact upgrade procedure page** matching your source and target.

### 8.2. Driver Version Differs from Server Version

The Java MongoDB Sync Driver has its own versioning; it does not have to match the server version number. A 5.x driver can support multiple server releases, subject to the compatibility matrix.

Takeaway:

- Never bump a driver version simply to "match the MongoDB server number".
- Review driver compatibility, API deprecations, connection settings, and TLS/SSL requirements.
- Evaluate ORM/framework wrappers (Spring Data MongoDB, Quarkus, Micronaut, Mongoose, etc.).
- Check external tools such as `mongosh`, `mongodump`, `mongorestore`, and `mongosync` separately.

---

## 9. Checking Backups and Recoverability Before Upgrading

An upgrade checklist must answer:

1. Did the latest backup succeed?
2. Has a backup been restore-tested in an isolated environment?
3. Does the backup match the target recovery version and topology?
4. Are KMS/CMK/key versions needed to decrypt the backup preserved?
5. If errors arise after raising FCV, is there a restore plan to a compatible deployment?
6. Does a snapshot/PITR window cover the moment right before the upgrade?
7. If using GridFS, are `files`/`chunks` backed up completely?
8. If sharded, is the backup consistent across shards and config servers?

### 9.1. Backups Differ from Binary Downgrades

Suppose binary downgrade is unsupported:

- You **must not** drop the old binary onto the new server's data files.
- You may need to restore a **pre-upgrade** snapshot onto a deployment running the compatible version.
- Such a restore can lose valid writes committed after the snapshot without PITR/reconciliation.
- Your plan must cover external systems, backup encryption, and application traffic.

### 9.2. Snapshots Are Not a System-Wide Undo Button

Suppose an upgrade runs for two days before exposing an incompatible query behavior. The pre-upgrade backup still exists, yet cutting back to it requires accounting for two days of new data and external side effects.

---

## 10. Replica Set State Required Before Rollout

Run on the primary:

```javascript
rs.status();
```

Or:

```javascript
db.adminCommand({
  replSetGetStatus: 1
});
```

Inspect:

- Is there exactly one `PRIMARY`?
- Are data-bearing secondaries in `SECONDARY` and healthy?
- Is any member in `RECOVERING`, `ROLLBACK`, or initial sync?
- Is a majority of voting members available?
- Do any secondaries have replication lag?
- Are there delayed/hidden members needing special coordination?

### 10.1. Do Not Upgrade an Unhealthy Cluster

If a three-node replica set already lost one node, taking a second node down loses majority and write availability. Repair replication health before upgrading.

### 10.2. Arbiters Do Not Replace Data-Bearing Members

An arbiter participates in voting/elections, yet **holds no data to acknowledge majority writes like a data-bearing secondary**. A Primary + Secondary + Arbiter topology has different fault tolerance and durability from three data-bearing members.

Never count "2/3 nodes are up" while ignoring write concern and replication capacity.

---

## 11. Checking FCV Before Upgrading 7.0 → 8.0

On a 7.0 deployment, FCV must be stably set to `"7.0"` prior to binary upgrades per the 8.0 guide.

```javascript
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
});
```

Expected:

```javascript
{
  featureCompatibilityVersion: {
    version: "7.0"
  },
  ok: 1
}
```

If output shows an ongoing transition or a different version, **halt binary changes**, investigate why, and resolve per version guidance.

### 11.1. Never Raise FCV to 8.0 While 7.0 Members Remain

Enabling FCV 8.0 can permit data/metadata formats incompatible with 7.0 binaries. Execute it only after **all members run 8.0 and are stable**.

### 11.2. Do Not Leave FCV 7.0 Indefinitely Either

Keeping the old FCV is for short-term validation and risk reduction. To use FCV 8.0 features, raise FCV once ready and approved.

---

## 12. Rolling Upgrade of a Replica Set: General Workflow

This example logically follows the self-managed **7.0 → 8.0** guide in the MongoDB Manual.

### Phase 1 — Upgrade SECONDARIES One by One

For secondary B:

1. Confirm B is truly `SECONDARY`, not in initial sync or rollback.
2. Confirm A/C remain healthy with majority.
3. Gracefully stop `mongod` on B per service runbook.
4. Upgrade B's binary/package to the supported 8.0 release.
5. Keep the exact `dbPath`, certificates, keyfile, port, replica set name, and storage config.
6. Start B.
7. Wait for B to reach `SECONDARY` and catch up within acceptable lag.
8. Inspect logs, FCV, and metrics.
9. Proceed to C only after B stabilizes.

Repeat for C, **one node at a time**.

### 12.1. Why Not Upgrade SECONDARIES Simultaneously?

Stopping B and C together leaves A alone. The replica set loses majority, cannot elect or sustain a writable primary per policy, and loses failover protection.

### 12.2. Graceful Shutdown Commands

In `mongosh` connected to the **target secondary**:

```javascript
db.adminCommand({
  shutdown: 1
});
```

Or via the service manager:

```bash
# Linux systemd example, run only inside an approved maintenance window
sudo systemctl stop mongod
```

Both commands directly affect availability. Never run them blindly across all nodes.

---

## 13. Upgrading Binaries/Packages: Preserving Config and Data Safety

When installing via a package manager:

- Select the exact repository and version.
- Confirm architecture and OS support.
- Pin the target version.
- Verify service unit, config file path, data dir owner, and permissions.
- Prevent package install scripts from restarting multiple instances simultaneously.
- Retain prior packages/binaries if release policy supports rollback.

Example:

```bash
mongod --version

# Use your distro's package manager to install the exact release,
# then start the service per runbook.
sudo systemctl start mongod
```

**Never** run a parallel configuration-management job to swap binaries across the entire replica set at once.

### 13.1. Keep Keys and Certificates Intact

MongoDB can fail to start if:

- `security.keyFile` for internal auth is missing.
- TLS certificates mismatch.
- KMIP/ESE keys are unreachable.
- `dbPath` permissions changed.
- Package update altered default config files.
- Bind IP/port differs from before.

Upgrading the binary is necessary, yet **must never break the node's ability to rejoin the replica set**.

---

## 14. After Each Secondary: Verifying Catch-Up

On the primary or appropriate member:

```javascript
rs.status();
```

Operational checks:

- Node returned to `SECONDARY`.
- No crash/restart loop.
- Replication lag is within target.
- No prolonged `ROLLBACK` or `RECOVERING`.
- Oplog window sufficed for catch-up.
- No abnormal spikes in error rates, disk usage, or write concern timeouts.

### 14.1. A Caught-Up Secondary Does Not Mean the App Is Fully Proven

The primary may still run the old binary. Applications must be validated **after an 8.0 secondary becomes primary** to surface any real behavioral differences.

### 14.2. Timing the Next Node

Wait until the upgraded node stays stable across multiple metric intervals—not just the first instant `SECONDARY` appears. Heavy workloads or large index sets may require longer observation.

---

## 15. Primary Stepdown: Intentional Controlled Disruption

Once secondaries are upgraded and healthy, step down the old primary:

```javascript
rs.stepDown();
```

This can drop the current shell connection or return an error as the node leaves primary status. **Reconnect** after the election.

### 15.1. Why Step Down Before Upgrading the Primary?

Stopping the old primary directly also triggers an election, yet a controlled stepdown lets you:

- Verify an upgraded candidate is ready first.
- Observe the failover cleanly.
- Minimize surprises for applications.
- Keep administrative work tightly bounded within the maintenance window.

### 15.2. Preconditions Before Stepdown

- Healthy majority.
- At least one upgraded secondary eligible to become primary.
- Sufficient oplog and replication synchronization.
- Appropriate write concern and driver retry settings.
- No critical conflicting transactions or background jobs.
- Application owners alerted to potential transient errors.

### 15.3. After Stepdown

Confirm an 8.0 node became `PRIMARY`, then stop and upgrade the **former primary** from 7.0 to 8.0.

---

## 16. Upgrading the Former Primary and Completing the Binary Phase

Once former primary A becomes `SECONDARY`:

1. Stop A.
2. Replace the 7.0 binary with 8.0.
3. Restart with existing configuration preserved.
4. Wait for A to return to `SECONDARY`.
5. Confirm A, B, and C all run the same 8.0 release while FCV remains 7.0 initially.
6. Record the completion marker.

```text
Binary phase completed:

A SECONDARY  8.0
B PRIMARY    8.0
C SECONDARY  8.0

Feature Compatibility Version:
             7.0
```

This is the expected state before enabling new features requiring FCV 8.0.

---

## 17. FCV After Binary Upgrade: Why Hold a Burn-In Period?

MongoDB documentation recommends waiting before enabling backward-incompatible features right after swapping binaries. A **burn-in period** allows you to:

- Monitor query regressions and CPU.
- Test Java/Node/Python drivers while the primary runs the new binary.
- Observe transactions, failovers, and replication.
- Confirm backup/restore hooks function normally.
- Confirm monitoring agents and tools remain compatible.
- Evaluate schema/index behavior before permitting backward-incompatible formats.

### 17.1. Burn-In Has No Single Fixed Day Count

Organizations choose hours or days depending on:

- System criticality.
- Deployment scale.
- Traffic seasonality.
- Peak vs. low-traffic windows.
- SLAs.
- Rollback rehearsal needs.

There is no universal "wait 48 hours" rule for every deployment.

### 17.2. Tie-In with Release Policy

Keeping the older FCV creates a **technical safety boundary** for persisted formats, yet **does not grant downgrade rights** if edition/release policy forbids it. Thus, burn-in either leads to raising FCV or **recovering via backups/supported paths**, not necessarily downgrading binaries.

---

## 18. Enabling FCV 8.0 When Ready

On the **PRIMARY** of the MongoDB 8.0 replica set, against `admin`:

```javascript
db.adminCommand({
  setFeatureCompatibilityVersion: "8.0",
  confirm: true
});
```

Starting in MongoDB 7.0, `confirm: true` is mandatory when changing FCV.

### 18.1. Re-Verify

```javascript
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
});
```

Expected:

```javascript
{
  featureCompatibilityVersion: {
    version: "8.0"
  },
  ok: 1
}
```

In a replica set, confirm all data-bearing members received the new FCV via replication and none remain mid-transition.

### 18.2. More Than Updating a Label

`setFeatureCompatibilityVersion` can:

- Write to system collections.
- Require a majority of data-bearing replica set members.
- Apply release-specific internal configuration updates.
- Wait for changes to propagate to a majority.
- Be blocked by certain background operations.
- Fail if incompatible data or catalog structures exist.

For instance, 8.0 docs note that raising FCV to 8.0 internally updates the replica set config `term` field.

### 18.3. Idempotency Does Not Mean Blind Infinite Retries

Documentation notes that the FCV command is idempotent and can be retried if interrupted. Still:

- Target the exact primary or `mongos`.
- Inspect whether a transition or another error is underway.
- Avoid retry storms when a member is down or an index build is running.
- Never run parallel FCV changes thinking "it's idempotent".

---

## 19. FCV in Transition State

During an FCV change, not every member settles instantaneously.

You may observe:

```javascript
{
  featureCompatibilityVersion: {
    version: "7.0",
    targetVersion: "8.0"
  }
}
```

This is an **illustrative structure** of an intermediate state; exact output fields depend on MongoDB version.

### 19.1. If the Command Fails Mid-Way

Never manually edit internal FCV documents in `admin.system.version` using `updateOne`.

Instead:

1. Preserve logs and command output.
2. Check what `getParameter` reports.
3. Verify majority and replica set health.
4. Check background operations, initial syncs, and schema/index prerequisites.
5. Follow the exact release's recovery/retry procedure.
6. Contact Support if stuck in an undocumented state.

### 19.2. Initial Sync and FCV

MongoDB recommends **not changing FCV while an initial sync is running**; doing so can restart the initial sync or trigger oplog replay compatibility errors.

### 19.3. Running Index Builds

In newer releases such as 9.0, `setFeatureCompatibilityVersion` can fail fast if an index build is active. Schedule FCV changes outside concurrent index builds or DDL maintenance.

---

## 20. MongoDB 8.3 Specifics to Know

Do not apply 7.0/8.0 commands verbatim across all MongoDB 8.x releases, as FCV and downgrade policies changed.

Per newer documentation:

- Starting in **8.3**, adjacent version downgrades are supported per release conditions.
- `setFeatureCompatibilityVersion` adds a `dryRun` option in 8.3 to detect incompatible data before certain FCV upgrades/downgrades.
- Do not include `dryRun` in 7.0 → 8.0 examples, as that syntax did not exist across older releases.
- Follow the dedicated 8.2/8.3 guides when operating in the 8.x line.

### 20.1. Dry-Run Concept in Supporting Releases

Example **only for supporting releases**:

```javascript
db.adminCommand({
  setFeatureCompatibilityVersion: "<supported-target>",
  confirm: true,
  dryRun: true
});
```

`"<supported-target>"` is a placeholder. **Never run** this without knowing the valid target FCV and actual server version.

### 20.2. Dry-Run Does Not Replace a Restore Drill

A dry-run catches incompatible persisted data early, yet does not prove:

- Application driver compatibility.
- Binary downgrade success.
- KMS/backup restore health.
- App latency/consistency meeting SLAs.
- External tool compatibility.

---

## 21. Upgrading a Sharded Cluster: Different Order from a Single Replica Set

A sharded cluster consists of:

```text
                      Applications
                           |
                     mongos routers
                           |
              +------------+------------+
              |                         |
         Shard replica set A       Shard replica set B
              |
              +---- Config Server Replica Set (CSRS)
```

For **MongoDB 7.0 → 8.0**, official docs specify this exact order:

1. Stop the **balancer**.
2. Upgrade the **config server replica set**.
3. Upgrade **each shard replica set**, one shard at a time.
4. Upgrade **`mongos` routers**.
5. Re-enable the **balancer**.
6. Once all binaries are aligned and burn-in finishes, raise **FCV via `mongos`**.

**Never apply an arbitrary order like "upgrade shards, then `mongos`, then config servers last".** Compatibility across routers, config metadata, and shards is strictly enforced.

---

## 22. Stopping the Balancer in a Sharded Cluster

Connect to a `mongos`:

```javascript
sh.stopBalancer();
```

Verify:

```javascript
sh.getBalancerState();
sh.isBalancerRunning();
```

Meaning:

- `sh.getBalancerState()` shows whether the balancer is enabled or disabled.
- `sh.isBalancerRunning()` indicates whether a balancing round is active per release semantics.
- If a chunk migration is in flight, stopping the balancer waits for it to finish.

### 22.1. Why Stop the Balancer?

Chunk migrations and placement updates concurrent with metadata and binary upgrades introduce complexity and prolong rollout windows.

### 22.2. Do Not Leave It Disabled Indefinitely

A cluster with continuous growth can become imbalanced if the balancer stays off too long. Record the disable timestamp and plan to re-enable it post-upgrade.

### 22.3. Other Sharding Operations

Even with the balancer off, guard against concurrent:

- Resharding.
- Adding or removing shards.
- FCV transitions.
- Active index builds.
- Large DDL or collection migrations.
- Background restores/backups.

Avoid mixing major topology changes with a major version upgrade without a dedicated runbook.

---

## 23. Upgrading the Config Server Replica Set (CSRS)

Config servers store critical sharded cluster metadata. Under the 7.0 → 8.0 workflow:

1. Upgrade CSRS `SECONDARY` members one at a time.
2. Wait for `SECONDARY` state and majority after each node.
3. Step down the CSRS `PRIMARY`.
4. Upgrade the former CSRS `PRIMARY`.
5. Confirm CSRS is healthy and on the target binary version.

### 23.1. Why Must CSRS Come Before Shards?

Router and shard operations depend on config metadata. MongoDB mandates this order to avoid unsupported mixed binary/metadata combinations.

### 23.2. Do Not Treat CSRS Like an Ordinary Application Replica Set

CSRS manages sharding metadata, so outages or upgrade errors affect routing and cluster-wide metadata operations.

### 23.3. Config Shards in Newer Releases

MongoDB 8.0+ distinguishes config shards from dedicated config servers; some upgrade/downgrade paths specify extra rules for config shards.

**Never follow dedicated CSRS steps blindly on a config-shard topology without reading the release-specific guide.**

---

## 24. Upgrading Shard Replica Sets

For each shard:

1. Verify the shard is healthy with a `PRIMARY` and synced secondaries.
2. Upgrade shard `SECONDARIES` one by one.
3. Step down the shard `PRIMARY`.
4. Upgrade the former shard `PRIMARY`.
5. Wait for the whole shard to stabilize and lag to return within thresholds.
6. Proceed to the next shard.

```text
CSRS all 8.0

Shard A:
  A1 primary 7.0
  A2 secondary 7.0
  A3 secondary 7.0

Step 1 A2 -> 8.0
Step 2 A3 -> 8.0
Step 3 stepdown A1
Step 4 A1 -> 8.0

Then Shard B ... 
```

### 24.1. Never Upgrade All Shard Primaries Simultaneously

Even though each shard has independent majority, simultaneous elections trigger widespread application errors. Rolling shard-by-shard limits blast radius and isolates regressions.

### 24.2. Track Replication Lag per Shard

No single global average replaces per-shard monitoring. One shard may lag heavily due to skewed data, index builds, or hardware differences.

---

## 25. Upgrading `mongos` and Re-Enabling the Balancer

Once CSRS and **all shards** run 8.0 in the supported order, upgrade `mongos` instances:

1. Start with a router carrying little or no traffic.
2. Drain/stop routing incoming requests via load balancer if used.
3. Replace the `mongos` binary.
4. Restart and verify routing and queries.
5. Advance to the next router.
6. Confirm all routers run the target version.

### 25.1. Why Can't Old `mongos` Stay Forever?

Documentation warns that a 7.0 `mongos` **cannot connect** to a MongoDB 8.0 sharded cluster once FCV is raised to 8.0. Prior to raising FCV, temporary mixed compatibility applies under FCV 7.0.

Therefore, **every `mongos` must be upgraded before raising FCV**.

### 25.2. Re-Enabling the Balancer

Once the binary phase is stable:

```javascript
sh.startBalancer();
```

Monitor migrations and shard balance. Never forget to re-enable the balancer after maintenance.

---

## 26. FCV on a Sharded Cluster

Unlike a standalone replica set, on a sharded cluster the FCV command runs through **`mongos`**:

```javascript
db.adminCommand({
  setFeatureCompatibilityVersion: "8.0",
  confirm: true
});
```

Preconditions:

- All config servers, shards, and `mongos` run supported target binaries.
- No conflicting initial sync, rollback, or major background operations.
- Verified backup and rollback/restore plan ready.
- Burn-in completed.
- Admin approval granted for raising FCV.

### 26.1. Effects

- Updates cluster-wide metadata/config across shards.
- Requires majority propagation.
- While running, chunk migrations, splits, or merges may hit `ConflictingOperationInProgress` depending on release.
- Never leave an unmonitored old `mongos` outside the topology.

### 26.2. Verifying Success

- FCV command succeeds.
- Every shard and config server reports the target FCV.
- No lingering intermediate transition states.
- Routing, sharded queries, transactions, and balancing run normally.

---

## 27. Disruption Profile: Standalone, Replica Set, and Sharded Cluster

| Topology | Upgrade Path | Expected Disruption |
| --- | --- | --- |
| Standalone | Stop → replace binary → start | Planned downtime |
| Replica set | Secondaries one by one → stepdown primary → former primary | Minimized downtime; elections can briefly interrupt writes |
| Sharded cluster | CSRS → shards → `mongos` per release procedure | Can stay serving; more coordination points |
| Atlas managed | UI/API or Auto Upgrades | Platform handles rollout; app still needs retries/monitoring |
| Ops Manager / Cloud Manager | Automation deployment workflows | Never bypass automation with manual shell changes |

### 27.1. Standalone Cannot Be Upgraded "Rolling"

A standalone deployment has a single `mongod` holding all data. Stopping it to swap binaries creates unavailability unless a separate migration/topology strategy is used.

### 27.2. Rolling Does Not Eliminate Client-Visible Errors

Even with server majority preserved, clients can observe:

- `NotWritablePrimary`.
- `InterruptedDueToReplStateChange`.
- Network timeouts.
- Transient transaction errors.
- Cursor invalidations.
- Read preference rerouting.

Handle these properly at the driver and application layers.

---

## 28. Java MongoDB Sync Driver: Election Readiness

In a Java application:

```java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.ReadConcern;
import com.mongodb.WriteConcern;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

public final class MongoClientFactory {

    public static MongoClient createClient(
            String uri
    ) {
        ConnectionString cs =
            new ConnectionString(uri);

        MongoClientSettings settings =
            MongoClientSettings.builder()
                .applyConnectionString(cs)
                .retryWrites(true)
                .readConcern(ReadConcern.MAJORITY)
                .writeConcern(WriteConcern.MAJORITY)
                .build();

        return MongoClients.create(settings);
    }
}
```

This is an example client setup—**not a guarantee every operation retries automatically**. `retryWrites` covers eligible operations and requires compatible server/driver versions. Transactions, bulk operations, custom commands, and external side effects have distinct retry semantics.

### 28.1. Never Retry Writes Blindly Without Idempotency

Suppose an order API executes:

1. Charge payment gateway.
2. Insert order into MongoDB.
3. Hit a timeout during stepdown.
4. Client retries the entire HTTP request.

If the code repeats step 1 without an idempotency key, the customer can be charged twice. MongoDB retryable writes **do not make external payment calls idempotent**.

### 28.2. Connect via a Replica Set URI

Example:

```text
mongodb://nodeA:27017,nodeB:27017,nodeC:27017/
  ?replicaSet=rs0&retryWrites=true
```

In real code, keep the URI on a single line and manage secrets securely. Never pin the app to a single primary hostname in a replica set deployment.

---

## 29. Signals to Monitor During a Rolling Upgrade

| Category | Metrics to Watch |
| --- | --- |
| Availability | `PRIMARY` exists, members healthy |
| Replication | Lag, oplog window, majority availability |
| Write behavior | Write errors, write concern timeouts, retry counts |
| Read behavior | Read errors, stale reads per read preference |
| Latency | p50/p95/p99 for queries and HTTP APIs |
| Performance | CPU, WiredTiger cache, IOPS, storage latency |
| Topology | Elections, stepdown count, restarts |
| Resources | Disk free, RAM, connections, open file handles |
| Transactions | Commit/abort/retry rates |
| Drivers | Pool checkout timeouts, reconnects, topology changes |
| Logs | Startup warnings, incompatible config/feature errors |
| Sharding | Balancer state, chunk migrations, targeted reads |
| Backup | Snapshot/PITR state, archive lag |
| Search | MongoDB Search/Vector Search index readiness |
| Security | TLS/KMIP/KMS availability, audit alerts |

### 29.1. Monitor Per Node

Do not look solely at cluster averages. A newly upgraded secondary may show different CPU/disk behavior while the old primary looks fine—only for regressions to surface once the upgraded node becomes primary.

### 29.2. Define Rollout Stop Thresholds

Example policy:

```text
Stop upgrade if:
  - no healthy majority,
  - replication lag exceeds agreed threshold,
  - persistent write errors,
  - p99 latency breaches SLO for sustained interval,
  - backup/restore capability is lost,
  - a newly upgraded node fails to stay SECONDARY,
  - KMS/TLS or authentication fails.
```

Tailor thresholds to your application rather than copying numbers blindly.

---

## 30. What Does "Downgrade" Actually Mean?

Four very different situations exist:

| Situation | State | Approach |
| --- | --- | --- |
| New binary installed on **one secondary**, old FCV | Mixed-version upgrade mid-flight | Halt rollout, fix fault, or follow release-supported rollback |
| All binaries new, old FCV | Binary phase complete, incompatible features not yet enabled | Downgrade may be possible if edition/release supports it; verify policy |
| New FCV enabled, new features/data written | Backward-incompatible data may exist | Clean up features, lower FCV per procedure, and verify support |
| Binary downgrade unsupported | Even if old FCV remains | Use patches, restores, or support-approved migrations—never force-start old binary |

### 30.1. Unsafe Rollback Practices

- Stopping MongoDB 8.0 and swapping in a 7.0 executable on the same data directory outside official instructions.
- Running `--repair` to "force the database down to an older version".
- Manually editing `admin.system.version` to alter FCV.
- Dropping indexes/collections that look "new" without understanding app dependencies.
- Restoring straight into production without reconciling post-snapshot writes.
- Downgrading the entire cluster simultaneously to "save downtime".

---

## 31. Downgrade Policies Across MongoDB Lines

Crucial constraint: **downgrade eligibility is a release and edition policy**, not arithmetic on version numbers.

### 31.1. From MongoDB 7.0 to 8.0 Releases

The *Downgrade 8.0 to 7.0* guide states:

- **Binary downgrades are unsupported for MongoDB Community Edition**.
- **MongoDB Enterprise requires assistance from MongoDB Support** for binary downgrades.
- Only single adjacent-version downgrades are covered by policy.
- Persisted incompatible data/features must be removed before lowering FCV/binaries.

Consequently, even when an 8.0 cluster runs at FCV 7.0, **you cannot assume Community Edition permits an 8.0→7.0 binary downgrade** via a command.

### 31.2. Starting in MongoDB 8.3

Current docs announce downgrade support to an **adjacent minor or major release** along supported paths. For instance, 9.0→8.3 has a concrete workflow lowering FCV and removing new features.

This is **not** a blanket license to downgrade 9.0→6.0 or copy data files across arbitrary topologies.

### 31.3. Multiple Paths from 9.0

MongoDB provides separate guides for 9.0→8.3 and conditional paths to 8.0; never mix steps from two different guides.

A runbook must lock in:

- Exact source patch version.
- Exact target patch version.
- Valid target FCV.
- Replica set vs. standalone vs. sharded cluster.
- Self-managed vs. Atlas.
- Feature incompatibility checklist.

---

## 32. FCV Downgrade Differs from Binary Downgrade

Suppose you run MongoDB 9.0 binary + FCV 9.0 and need to return to 8.3 along a supported path.

**Conceptual order**:

```text
9.0 binary + 9.0 FCV
         |
         | remove 9.0 incompatible features/data
         v
9.0 binary + 8.3 FCV
         |
         | follow supported rolling binary downgrade
         v
8.3 binary + 8.3 FCV
```

Never invert this order to:

```text
9.0 binary + 9.0 FCV
         |
         | replace binaries first
         v
8.3 binary + 9.0 FCV   <-- may be incompatible
```

### 32.1. Why Clean Up Incompatible Features First?

FCV gates features and persisted formats, yet it does not automatically delete data, indexes, or metadata already created using new features.

Examples of release-specific checks:

- New index types or index options.
- Incompatible collection settings or schema validators.
- Time-series data/catalog changes.
- Queryable Encryption / CSFLE metadata requirements.
- Sharding / config shard topology features.
- New catalog or config fields.
- Storage/index structures unrecognized by the older server.
- Startup parameters or feature flags invalid on the target release.

**Never delete a new feature without checking dependent business data first**; migrate or export data safely beforehand.

---

## 33. Conditional Example: Downgrading a 9.0 Replica Set to 8.3

This is an **illustrative sequencing template**, not a complete production runbook.

### Phase A — Prerequisites

1. Confirm you are following the exact **Downgrade 9.0 Replica Set to 8.3** guide.
2. Verify source and target patch releases.
3. Verify backups and complete a restore rehearsal.
4. Confirm all replica set members are running and healthy.
5. Review and remediate the 9.0 backward-incompatible features list.
6. Confirm no initial sync, no `newlyAdded` members, and no member in `ROLLBACK`/`RECOVERING`.
7. Verify admin and index-management privileges.
8. Schedule a maintenance window with continuous monitoring.

### Phase B — Lower FCV First

On the 9.0 primary:

```javascript
db.adminCommand({
  setFeatureCompatibilityVersion: "8.3",
  confirm: true
});
```

Wait for completion, then verify across all members:

```javascript
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
});
```

Expect FCV `"8.3"` on every member.

### Phase C — Downgrade Binaries per Procedure

Following the 9.0→8.3 replica set guide:

1. Use the matching supported 8.3 patch binary.
2. Downgrade secondaries one by one, waiting for `SECONDARY` after each.
3. If an arbiter exists, follow the **dedicated arbiter downgrade steps**; never apply data-bearing node steps carelessly.
4. Step down the old primary.
5. Downgrade the former primary once a new primary is elected.
6. Verify versions/FCV, replication, query tests, and backups.

Never copy an **arbiter** directory-wipe step onto data-bearing members—that destroys data.

### 33.1. Why Is the Latest Target Patch Required?

Downgrade guides commonly require the latest supported patch release in the target series to ensure compatibility fixes are present.

---

## 34. Is FCV Downgrade an "Undo Everything" Switch?

**No.**

`setFeatureCompatibilityVersion` toggles compatibility gating for features and updates internal metadata. It does not automatically:

- Undo business writes.
- Drop all incompatible new indexes.
- Revert application schemas.
- Recover deleted data.
- Restore backups.
- Guarantee the old binary can read data files.
- Roll back Search/Vector Search indexes.
- Roll back Kafka events, payments, or external systems.

### 34.1. If the Command Returns CannotDowngrade

The cause is usually **persisted backward-incompatible data or features**.

Remediation:

1. Read the full error message and blocker list.
2. Consult the release's downgrade documentation.
3. Identify affected features or data.
4. Design a controlled migration or feature removal.
5. Test on staging or a restored backup.
6. Retry only once all prerequisites pass.

**Never** delete incompatible business data carelessly just to make the command succeed.

---

## 35. Atlas Upgrades: Managed Mechanics Differ from Self-Managed

MongoDB Atlas manages cluster infrastructure, maintenance, and most binary rollout steps.

Depending on deployment:

- **Manual Upgrades:** cluster owners choose the target major version and timing.
- **Auto Upgrades:** Atlas applies release upgrades automatically per release track and maintenance windows.
- **FCV on Auto Upgrades:** Atlas manages FCV elevation per platform lifecycle.
- **Atlas Core/Infinite:** differ in release cadence and feature availability.

### 35.1. Do Not SSH to Swap `mongod` on Atlas

Customers never swap binaries host-by-host with package managers on Atlas-managed clusters. Use the Atlas UI/API and follow the "Change/Upgrade Major MongoDB Version" documentation.

### 35.2. FCV and the "Point of No Return" in Atlas

MongoDB Versions and Upgrade Paths documentation notes that once FCV is raised on Atlas and new-format features are enabled, **downgrading is no longer available in Atlas** under that upgrade model.

Before selecting a target release or Auto Upgrades, confirm:

- Do operators control burn-in / FCV timing?
- When does Atlas automatically raise FCV?
- If a regression occurs, what is the valid rollback path?
- Must we restore into a separate cluster rather than downgrading?
- Are maintenance windows and backups/PITR aligned?

### 35.3. Base Atlas Rollback Plans on Real Capabilities

Never claim "Atlas always supports one-click downgrade" or "restoring a snapshot preserves every recent write" without proof. Verify documentation and Support guidance for your exact cluster configuration.

---

## 36. Ops Manager / Cloud Manager: Do Not Break Automation State

If a self-managed deployment is managed by **Ops Manager** or **Cloud Manager** Automation:

- Perform version upgrades through the tool's Automation/Upgrade workflows.
- Never restart or upgrade nodes manually via shell if Automation will overwrite configs.
- Check agent versions (monitoring, backup, automation) and compatibility.
- Review maintenance prerequisites and supported targets.
- Never change FCV outside the workflow when the management plane expects control.

### 36.1. "Self-Managed" Does Not Mean "No Automation"

Servers may run in your own data center while Automation orchestrates upgrades. Establish **one single source of truth** for version and FCV control.

---

## 37. Application and Driver Compatibility

Layers to verify:

| Layer | Examples |
| --- | --- |
| Drivers | Java Sync Driver, Node.js, Python, Go compatibility |
| Connection setup | TLS versions, SCRAM mechanisms, `authSource` |
| Commands | Deprecated/removed commands or options |
| Queries | Behavior changes, collations, aggregation semantics |
| Indexes | New types/features, planner behavior |
| Transactions | Error labels, retry semantics, majority availability |
| Change Streams | Resume behavior after restarts/elections |
| Time-series | Schema/catalog/FCV-specific changes |
| Sharding | Router/config metadata compatibility |
| Search | `mongot`/Atlas Search and Vector Search compatibility |
| Backup | Ops Manager / Database Tools compatibility |
| External consumers | Connectors, CDC, BI, ETL, monitoring |

### 37.1. Do Not Test Only Database Connectivity

An app can connect cleanly yet fail when:

- Creating indexes.
- Running aggregations whose operators changed behavior.
- Opening transactions.
- Resuming Change Streams via tokens.
- Executing bulk writes.
- Querying Search/Vector Search.
- Connecting under TLS/key rotation.
- Running migration scripts.

Test suites must exercise representative queries and writes.

---

## 38. Stable API Does Not Replace FCV

MongoDB offers the **Stable API** so applications can rely on a versioned set of commands with compatibility guarantees.

Java example:

```java
import com.mongodb.MongoClientSettings;
import com.mongodb.ServerApi;
import com.mongodb.ServerApiVersion;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

public final class MongoClientWithStableApi {

    public static MongoClient create(String uri) {
        ServerApi api = ServerApi.builder()
            .version(ServerApiVersion.V1)
            .strict(true)
            .deprecationErrors(true)
            .build();

        MongoClientSettings settings =
            MongoClientSettings.builder()
                .applyConnectionString(
                    new com.mongodb.ConnectionString(uri)
                )
                .serverApi(api)
                .build();

        return MongoClients.create(settings);
    }
}
```

### 38.1. What Does Stable API Help With?

- Reduces risk of depending on commands outside the stable contract.
- Supports strict and deprecation-error enforcement.
- Preserves application behavior for covered APIs.

### 38.2. What Does Stable API Not Help With?

- Does not bypass binary upgrade prerequisites.
- Does not replace FCV.
- Does not eliminate performance regressions.
- Does not make an unsupported old driver compatible with a new server.
- Does not make transactions or external side effects idempotent.
- Does not authorize binary downgrades against policy.

---

## 39. Environment Rollout Progression

A sound organizational progression:

```text
Development
   |
   v
Staging with production-like data
   |
   v
DR/backup restore rehearsal
   |
   v
Canary/less-critical production cluster
   |
   v
Main production clusters
   |
   v
FCV enablement after burn-in
```

### 39.1. Do Not Use Tiny Staging Datasets

If production runs:

- 500 GiB of data.
- 100 indexes.
- 10,000 requests/s.
- Complex multi-shard transactions.
- Change Streams and Search.

and staging holds 100 documents, you cannot validate latency, index builds, disk pressure, or replication behavior.

### 39.2. Coordinating Data Migrations or New Features

Avoid performing simultaneously:

- Major MongoDB upgrade.
- Major driver upgrade.
- Schema migration.
- New shard key.
- Authentication changes.
- FCV elevation.
- Massive background index builds.

Split into waves where possible to isolate root causes if anything fails.

---

## 40. How Upgrades Affect Backups and PITR

A MongoDB deployment is typically backed up via:

- Atlas Cloud Backup/PITR.
- Ops Manager/Cloud Manager backup.
- Filesystem snapshots.
- Third-party tools.
- `mongodump`/`mongorestore`.

### 40.1. FCV and Backup Compatibility

After enabling new features or raising FCV:

- Newer backups may contain formats incompatible with older servers.
- Restoring to an older cluster version may be blocked.
- Some PITR windows may be bounded across FCV/catalog changes.
- Search indexes or encrypted metadata may require rebuilds or compatible keys.

### 40.2. Capture Snapshots Before Risky Steps

Recommendations:

1. Take a backup/restore point before upgrading binaries.
2. Verify backup restoration works.
3. Record a marker before raising FCV.
4. Maintain rollback/restore runbooks matched to each stage.
5. Never delete old key versions or pre-upgrade backups immediately after upgrading.

### 40.3. Backups Must Remain Decryptable

If backups/volumes use a CMK, disabling or deleting the KMS key renders snapshots unusable. Upgrade plans must cover KMS, certificates, and secret lifecycles.

---

## 41. MongoDB Search and Auxiliary Components During Upgrades

If the application uses MongoDB Search/Vector Search or a service syncing derived indexes:

- Check compatibility with the MongoDB binary, version, and FCV.
- Verify whether Search index definitions persist or rebuild on restore/cluster changes.
- Monitor `mongot`/Atlas Search node availability.
- Do not assume Search query latency stays unchanged while MongoDB nodes step down or restore.
- Separate Search regression testing from schema/index migrations where possible.

### 41.1. Derived Indexes May Need Separate Warm-Up Time

A finished database restore or binary upgrade does not automatically mean Search indexes are `READY`. Verify Search readiness separately and factor it into RTO and maintenance windows.

---

## 42. FCV and Backward-Incompatible Features: Conceptual Model

Suppose version N+1 introduces a feature changing how index metadata is stored:

```text
Binary N+1 can read:
   old format
   new format

Binary N can read:
   old format
   but does not support new format

FCV=N:
   keeps writes in old format for gated features

FCV=N+1:
   allows writing new format
```

If an application writes data using the new feature:

```text
Existing persisted data: new format
Attempt to start old binary: unsafe/unsupported
```

Therefore, **lowering FCV** requires removing or converting **newly persisted objects** first.

### 42.1. Not Every New Feature Waits for FCV

Some optimizations or behavior changes take effect immediately regardless of FCV. Burn-in testing is still essential even while keeping the old FCV.

---

## 43. Failure Scenario: Upgraded 8.0 Secondary Fails to Reach SECONDARY

Suppose B restarts on the new binary and errors:

```text
B state: STARTUP2 / RECOVERING / down
Primary A: still healthy
Secondary C: healthy
```

Actions:

1. **Halt the rollout.**
2. Keep A and C running; do not stop additional nodes.
3. Inspect MongoDB process logs and startup config.
4. Check `dbPath` ownership, certificates, keyfile, and KMIP.
5. Check binary/FCV and patch compatibility.
6. Check oplog window and initial sync conditions.
7. Recover B using official procedures.
8. Resume only once B is stable.

Never:
- Delete `dbPath` arbitrarily.
- Downgrade the binary outside supported paths.
- Edit raw system collections.
- Restart A and C together "to sync".

---

## 44. Failure Scenario: Primary Stepped Down, No New Primary Elected

Situation:

```text
A stepped down
B/C ineligible or lagging
No PRIMARY
```

Possible causes:

- Majority unavailable.
- Unusual voting/priority configuration.
- B/C lagging behind.
- Network partition.
- TLS/internal authentication failure.
- Member stuck in `RECOVERING`.
- Configuration mid-transition.

### 44.1. Response

- Inspect `rs.status()`.
- Verify networking, TLS, majority, and election log messages.
- Never alter voting configuration blindly without knowing the impact.
- Follow the incident runbook and escalate to DBA/on-call.

### 44.2. Why Not Simply "Force Primary"?

Improper forced reconfigs or elections risk split-brain assumptions or rolling back unacknowledged writes. Preserve proper replica set semantics first.

---

## 45. Failure Scenario: New FCV Enabled, Now Need to Revert

Situation:

```text
All binaries: 8.0
FCV:          8.0
New features already used
Application regression found
```

**Mistake:** merely running:

```javascript
// Do not treat this as a complete rollback recipe:
db.adminCommand({
  setFeatureCompatibilityVersion: "7.0",
  confirm: true
});
```

and swapping in 7.0 binaries.

Right steps:

1. Check the 8.0→7.0 binary downgrade policy for your edition.
2. Check the list of persisted backward-incompatible features.
3. On Enterprise 8.0, work with MongoDB Support per docs.
4. On Community 8.0, do not attempt a binary downgrade, as it is unsupported.
5. If no downgrade path exists, evaluate a forward fix or restoring/migrating to a compatible deployment.
6. Preserve data and backups for investigation—never force-start the old binary.

### 45.1. Disabling a New Feature Does Not Convert Existing Data

Toggling a feature flag OFF stops new writes of that type, yet documents/indexes in the new format remain on disk. FCV or binary downgrades still have explicit prerequisites.

---

## 46. Failure Scenario: Post-Upgrade Performance Drop Without Incompatibility

Suppose:

```text
Before: MongoDB 7.0, p95 query = 25 ms
After:  MongoDB 8.0, p95 query = 80 ms
FCV:    7.0
```

Hypotheses:

- Query planner chose a different plan.
- Index/collection statistics or workload changed.
- Cold cache after restart.
- Storage I/O backlog from initial sync or rebuilds.
- Driver connection pool behavior changed.
- Background Search/index build running.
- OS or VM tier changed at the same time.
- Application traffic spiked.

**Investigation steps**:

- Compare query shapes and `explain` plans.
- Check disk, cache, CPU, and network metrics.
- Check topology and connection pools.
- Perform controlled plan inspection, hints, or index experiments.
- Evaluate patch fixes or support escalation.
- Do not treat binary downgrade as the first move if release policy forbids it.

---

## 47. Failure Scenario: FCV Upgrade Blocked by an Index Build

A large collection is building an index. FCV elevation may be blocked by concurrent background operations depending on release.

### 47.1. Inspect Active Operations

```javascript
db.currentOp();
```

Or:

```javascript
db.adminCommand({
  currentOp: 1
});
```

Requires appropriate privileges and understanding of returned namespaces/operations. Never kill an index build blindly just to rush FCV.

### 47.2. Options

- Wait for the index build to finish.
- Assess business impact before safely aborting a build.
- Schedule FCV changes when no DDL or major background jobs are running.
- Retry in a controlled way based on the exact error.

---

## 48. Downgrading a Sharded Cluster

Sharded cluster downgrades have stricter prerequisites:

- FCV across the sharded topology.
- Config server, shard, and router version compatibility.
- Balancer state.
- Shard placement metadata and chunk migrations.
- Newer topology features such as config shards.
- Resharding/unsharding or catalog changes.
- Health of every replica set.

### 48.1. Do Not Simply Reverse the Upgrade Order

Release-specific downgrade order can differ in subtle details. Never assume "upgrade is CSRS→shards→mongos, so downgrade must be mongos→shards→CSRS" without reading the official downgrade page.

### 48.2. Config Shards May Require Reconfiguration

On certain FCV downgrade paths, MongoDB docs require transitioning back to a dedicated config server before lowering FCV below a threshold.

Never perform config-shard topology transitions in production based on an abbreviated snippet; follow the dedicated workflow.

### 48.3. `mongos` and FCV

Ensure all routers stay compatible with the actual FCV before switching versions. Never leave an old `mongos` unmonitored outside the load balancer.

---

## 49. Downgrade and Data Migration Operations

If an incompatible structure must be removed:

1. Identify the exact object(s).
2. Capture a backup/snapshot before migrating.
3. Plan conversion back to the old format.
4. Check permissions and business invariants.
5. Test the migration on a clone.
6. Allocate extra disk, memory, and IOPS for the migration.
7. Execute inside a maintenance window.
8. Verify counts, checksums, and indexes.
9. Only then lower FCV per supported procedure.
10. Only then downgrade binaries if edition/release permits.

### 49.1. Do Not Drop New Indexes Without Checking Unique Constraints

A new index might enforce uniqueness or serve a critical query. Dropping it just to pass a preflight check can:

- Allow duplicate data.
- Slow down queries.
- Break application invariants.
- Spike disk I/O.

Prepare an equivalent index or schema design on the target version first.

---

## 50. Should You Run Old and New Versions Side-by-Side?

In some organizations, instead of downgrading data files in place, teams use:

```text
Old version cluster          New version cluster
       |                            ^
       |                            |
       +---- data migration --------+
       |
       +---- application canary
```

A side-by-side migration offers controlled traffic cutover/rollback options, yet:

- Requires initial sync or a supported migration tool.
- Must manage writes arriving during dual operation.
- Bidirectional sync between versions is not guaranteed.
- Change stream history and schema compatibility matter.
- May require briefly freezing writes at cutover.
- Requires a data rollback plan, not just DNS rollback.

**Never treat dual-writes across two versions as trivial.** Dual writes risk divergence if one cluster succeeds while the other fails.

---

## 51. Deciding Between Downgrade and Forward-Fix

When an issue appears post-upgrade, options include:

| Option | When Appropriate | Risk |
| --- | --- | --- |
| **Fix config/query** | New behavior can be tuned safely | Requires accurate diagnosis |
| **Patch upgrade** | Bug already fixed in a newer patch | Another deployment change |
| **Disable app feature** | App feature triggered the regression | Reduced functionality |
| **Restore/cutover** | Valid old copy exists; data loss bounded | Needs reconciliation |
| **Supported downgrade** | Explicit path exists and prerequisites pass | Complexity, outage/compatibility risks |
| **Support-assisted downgrade** | Release mandates vendor assistance | Depends on incident coordination |
| **Forward migration** | Data is already incompatible with old binaries | Time and resource cost |

There is no universal rule saying "if an upgrade fails, downgrade immediately". The lowest-risk choice depends on severity, already-written data, and support constraints.

---

## 52. Role of Application Feature Flags

A risk-reduction strategy avoids enabling app features that depend on new server capabilities right away.

Hypothetical app config example:

```yaml
application:
  mongoFeatures:
    useNewServerCapability: false
    enableNewIndexPattern: false
```

Enable only after binaries and FCV are stable:

```yaml
application:
  mongoFeatures:
    useNewServerCapability: true
    enableNewIndexPattern: true
```

### 52.1. This Is Not MongoDB Syntax

This is a hypothetical application manifest, not `mongod.conf` or MongoDB server feature flags.

### 52.2. Why Is It Useful?

- Avoids exercising new capabilities during the mixed-version window.
- Enables gradual canary rollout by traffic or tenant.
- Lets you disable an application feature quickly on errors.
- Reduces simultaneous variables changing at once.

**However:** toggling an application flag OFF after writing persisted data does not automatically make that data compatible with older binaries.

---

## 53. Upgrade Success Criteria

A major upgrade does not succeed merely because commands return `ok: 1`.

Define clear verification targets:

| Objective | Evidence |
| --- | --- |
| Correct binary versions | `buildInfo` / effective process versions |
| Expected FCV | `getParameter` across all members |
| Availability | `PRIMARY` exists; secondaries healthy |
| Durability | Majority writes, replication lag, and backups |
| Application | Critical APIs pass smoke/integration tests |
| Query performance | p95/p99 within SLO |
| Transactions | Stable commit/abort behavior |
| Sharding | Router compatibility, balancer running properly |
| Security | Auth/TLS/KMS healthy |
| Backups | Snapshot/PITR pipeline running, restore plan valid |
| Monitoring | Alerts/logs free of sustained errors |
| Rollback posture | Known downgrade eligibility status |
| Documentation | Runbooks updated with source/target/FCV |

### 53.1. Success Does Not Mean Zero Log Warnings

An upgrade can emit brief transient warnings during the mixed-version window. Classify severity instead of triggering a panic rollback on every warning—yet investigate FCV, catalog, corruption, or replication errors immediately.

---

## 54. Practice Exercises — State Checks

### Exercise 1: Binary and FCV

A node reports:

```text
Binary: 8.0
FCV:    7.0
```

**Question:** Is this definitely an error?

**Answer:** No. This can be an intentional intermediate state after binary upgrade before raising FCV.

### Exercise 2: Raising FCV Too Early

A replica set still has one 7.0 secondary while other nodes run 8.0. The team wants to set FCV 8.0.

**Answer:** No. Finish upgrading all members and confirm stability before raising FCV.

### Exercise 3: Replica Set Order

Three members: A primary, B and C secondaries.

**Answer:** Upgrade B then C one at a time, wait for health, step down A, upgrade former primary A, and only then consider FCV.

### Exercise 4: Stepdown

After `rs.stepDown()`, the shell reports a network/not-primary error.

**Answer:** Expected election behavior; reconnect and check the new primary rather than assuming the whole deployment broke.

### Exercise 5: Majority

One secondary is already down before maintenance, and the team wants to shut down the remaining secondary.

**Answer:** Halt the upgrade; this risks losing majority and write availability.

### Exercise 6: Sharded Cluster

A team plans to upgrade `mongos` to 8.0 before shards and config servers in a 7→8 upgrade.

**Answer:** Violates official order; 7→8 requires CSRS → shards → `mongos`, with balancer stop/start steps.

### Exercise 7: Where to Run FCV?

All binaries in a sharded cluster are upgraded.

**Answer:** Run `setFeatureCompatibilityVersion` through a supported `mongos`.

### Exercise 8: Retrying FCV

The FCV command timed out with an unclear state.

**Answer:** Check FCV status, health, and logs, then retry per idempotency guidance if appropriate; never edit system collections manually.

### Exercise 9: Community 8.0 Downgrade

A team runs Community 8.0 / FCV 7.0 and wants to swap back to 7.0 binaries.

**Answer:** Unsupported. The 8.0→7.0 policy does not support Community binary downgrades.

### Exercise 10: Enterprise 8.0 Downgrade

A team runs Enterprise 8.0 and wants to downgrade to 7.0.

**Answer:** Documentation requires contacting MongoDB Support rather than performing an unassisted downgrade.

### Exercise 11: 9.0→8.3

A team used a 9.0 feature with persisted formats incompatible with 8.3.

**Answer:** Remove or convert those features/data per documentation before lowering FCV and binaries.

### Exercise 12: Atlas Auto Upgrades

A team assumes they can hold FCV down for 30 days on an Atlas Auto Upgrades cluster.

**Answer:** Do not assume this control; Atlas manages FCV per Auto Upgrades release lifecycle.

### Exercise 13: FCV 9.0 and 8.3

A self-managed 9.0 cluster has FCV 9.0 and needs to downgrade to 8.3.

**Answer:** Follow the 9.0→8.3 procedure: remove incompatible features, lower FCV to 8.3, verify all members, then downgrade binaries in supported order.

### Exercise 14: Data Backups

A backup succeeded, yet the old KMS key was deleted.

**Answer:** The backup may be undecryptable. Upgrade/rollback plans must cover key lifecycles.

### Exercise 15: Post-Upgrade Backup

A team restores a newer snapshot containing 9.0 features onto an 8.3 binary.

**Answer:** Do not assume restore compatibility. Verify snapshot version, FCV, and feature formats.

### Exercise 16: Driver Connection

An application connects to one specific `PRIMARY` via a fixed hostname.

**Answer:** Fragile during elections. Use a replica set connection string with proper driver server discovery.

### Exercise 17: External Payment

During an upgrade, an API retries an entire request that calls a payment gateway.

**Answer:** Enforce idempotency for external side effects; retryable writes do not protect external payment calls.

### Exercise 18: Search

MongoDB nodes finished upgrading, yet Search returns incomplete data.

**Answer:** Check Search service/index readiness, sync lag, and compatibility—not solely `mongod` status.

### Exercise 19: Cache

After an upgrade/restart, p99 rises for 10 minutes then drops.

**Answer:** Likely cache warm-up. Check disk/cache metrics before assuming a version regression.

### Exercise 20: Running Index Build

`setFeatureCompatibilityVersion` is blocked by a background index build.

**Answer:** Wait or manage the build per runbook, avoiding retry storms; newer releases enforce stricter preflight checks.

### Exercise 21: Downgrade Anytime

"As long as FCV stays low, you can downgrade binaries as often as you want."

**Answer:** False. Binary downgrade depends on release, edition, upgrade path, and persisted features.

### Exercise 22: Swapping `dbPath` Directly

An admin plans to take `dbPath` from MongoDB 8.0 and start MongoDB 7.0 binaries on it to "undo".

**Answer:** Unsafe and unsupported by default. Follow an official downgrade procedure or restore from backup.

### Exercise 23: Arithmetic Versions

Jumping directly from 7.0 to a 9.x release without checking upgrade paths.

**Answer:** Check version roadmaps and official upgrade paths; intermediate hops and FCV steps may be mandatory.

### Exercise 24: Migrations Alongside Upgrades

A team wants to bundle in one maintenance window: major upgrade, resharding, schema migration, FCV elevation, and 10 index builds.

**Answer:** Extremely high risk. Separate into waves to minimize concurrent changes and simplify rollback/triage.

---

## 55. Pre-Upgrade (Preflight) Checklist

- [ ] Source binary and FCV confirmed on every node?
- [ ] Supported target release and patch version selected?
- [ ] Exact upgrade guide read for standalone/replica set/sharded topology?
- [ ] Release notes, deprecations, and compatibility changes reviewed?
- [ ] Driver/ORM/framework/tool compatibility verified?
- [ ] OS/CPU/storage/TLS/KMS requirements verified?
- [ ] Restore-tested backup/PITR available?
- [ ] Change ticket, on-call, and rollback/restore runbook ready?
- [ ] Maintenance window and application notifications scheduled?
- [ ] Replica set healthy with majority available?
- [ ] No prolonged initial sync, rollback, or `RECOVERING`?
- [ ] Oplog window and replication lag healthy?
- [ ] Sufficient disk, IOPS, and headroom available?
- [ ] Baseline p50/p95/p99, error rates, and throughput recorded?
- [ ] Tested in staging with a representative workload?
- [ ] Index builds and long-running operations checked?
- [ ] Search/Vector Search/CDC/connectors accounted for?
- [ ] Plan in place not to use new features during mixed-version window?
- [ ] If sharded: CSRS → shards → `mongos` sequence verified?
- [ ] If Atlas: Manual vs. Auto Upgrades and FCV ownership understood?

---

## 56. Rolling Upgrade Checklist

- [ ] Only one member stopped at a time per runbook.
- [ ] `SECONDARIES` upgraded first, waiting for sync.
- [ ] Halt if a node stays in `RECOVERING`/`ROLLBACK` too long.
- [ ] Actual running version verified on each node after restart.
- [ ] No manual edits to `dbPath` or system collections.
- [ ] TLS/auth/KMS verified after each restart.
- [ ] Healthy majority confirmed before stepdown.
- [ ] Former primary upgraded only after new primary stabilizes.
- [ ] Application observed closely when an upgraded node becomes `PRIMARY`.
- [ ] For sharded clusters: balancer and routers coordinated properly.
- [ ] All nodes and routers on target binary before FCV enablement.
- [ ] Binary-phase completion timestamp recorded.
- [ ] Old FCV held during the burn-in period per policy.
- [ ] New features kept off until approved.
- [ ] Rollout halted immediately if SLOs or availability degrade.

---

## 57. Raising FCV Checklist

- [ ] Burn-in and application tests passed?
- [ ] Cluster healthy with no active initial sync?
- [ ] No conflicting background index builds or DDL?
- [ ] Valid target FCV confirmed for the release?
- [ ] All binaries running the compatible target release?
- [ ] Accounted for loss/restriction of binary downgrade?
- [ ] Valid backup/restoration path confirmed?
- [ ] Release-specific incompatible features reviewed?
- [ ] Formal approval granted to raise FCV?
- [ ] `confirm: true` executed on the primary or appropriate `mongos`?
- [ ] FCV verified across all members?
- [ ] No lingering intermediate `targetVersion`?
- [ ] Features requiring the new FCV tested?
- [ ] Runbooks, monitoring, and baselines updated?

---

## 58. Downgrade Checklist

- [ ] Is the downgrade path **supported by release and edition**?
- [ ] Exact official source→target downgrade guide read?
- [ ] If Enterprise policy requires it, MongoDB Support engaged?
- [ ] Backup saved and restore-tested before downgrading?
- [ ] All members, shards, and routers healthy?
- [ ] Explicit list of backward-incompatible features prepared?
- [ ] Persisted incompatible features/data removed in a controlled manner?
- [ ] Config shard vs. dedicated config server topology checked?
- [ ] Valid target FCV lowered in the proper sequence?
- [ ] FCV verified across the entire deployment?
- [ ] No initial sync, `RECOVERING`, `ROLLBACK`, or `newlyAdded` members?
- [ ] Exact target patch binaries ready?
- [ ] Dedicated arbiter steps included if required by docs?
- [ ] Topology-specific rolling binary downgrade workflow ready?
- [ ] Application driver/feature-flag rollback plan ready?
- [ ] Post-downgrade data and critical API verification planned?
- [ ] Rollback-of-downgrade / restore plan ready if downgrade fails?
- [ ] Pre- and post-change backups and audit logs preserved?

---

## 59. Common Misconceptions That Cause Incidents

| Misconception | Reality |
| --- | --- |
| "Upgrading the binary already upgrades FCV." | Two separate steps. |
| "FCV always equals the `mongod` version." | After binary upgrade, FCV normally stays at the old version until raised. |
| "Old FCV makes the new binary identical to the old binary." | Runtime and query planner behavior can still change. |
| "Raising FCV just edits a string." | Writes internal metadata and enables persisted incompatible features. |
| "FCV can be changed mid-initial sync." | Can restart or fail initial sync; avoid it. |
| "One healthy primary is enough during upgrades." | Majority/quorum and write concerns must stay intact. |
| "Rolling upgrades cause zero request errors." | Elections and reconnects can produce transient errors. |
| "Upgrading secondaries in parallel is faster and fine." | Risks losing majority or spiking replication lag. |
| "Upgrade the primary first since it's most important." | Replica sets typically upgrade secondaries first. |
| "Stepdown is always invisible to applications." | Clients need proper retries and server discovery. |
| "`MongoClient` pointing to one primary hostname is enough." | Replica set URI/discovery is required for failover. |
| "Every version has the same downgrade path." | Depends on release, edition, and topology. |
| "Community 8→7 only needs lowering FCV." | Binary downgrade is unsupported under 8.0→7.0 policy. |
| "Enterprise 8→7 can downgrade freely anytime." | Requires MongoDB Support per docs. |
| "Starting in 8.3, you can downgrade across any number of releases." | Only supported adjacent paths apply. |
| "Lowering FCV auto-deletes all incompatible data." | Persisted incompatible features/data must be handled separately. |
| "Running an old binary on a new `dbPath` is safe." | Risks incompatibility and data corruption. |
| "A successful backup guarantees restore works." | Requires restore drills plus key/version compatibility. |
| "Database rollback rolls back payments or Kafka." | External side effects require reconciliation. |
| "Sharded clusters can upgrade `mongos` first." | 7→8 order is CSRS → shards → `mongos`. |
| "Raising FCV with an old `mongos` still works." | Older routers may fail against the newer FCV. |
| "Leaving the balancer off doesn't matter." | Causes long-term shard imbalance. |
| "Config shards match dedicated CSRS across all versions." | Topology-specific procedures apply. |
| "Once upgraded, monitoring is done." | Burn-in and post-upgrade validation are critical. |
| "Stable API replaces FCV." | Two distinct mechanisms with different purposes. |
| "Retryable writes make all requests idempotent." | External side effects still need idempotency. |
| "Patch releases only touch minor UI details." | Can alter server/driver behavior; read release notes. |
| "Healthy `serverStatus` means the app works." | Requires business, transaction, and Search integration tests. |
| "Bundle binary, FCV, and schema upgrades to save time." | Expands blast radius and hinders triage. |
| "If an error occurs post-upgrade, downgrade first." | Forward fixes or support-guided restores can be safer. |

---

## 60. Condensed Runbook for 7.0 → 8.0 Replica Set Exercise

**Execute only in staging/lab or with production approval**.

```text
PREPARE
  1. Backup + restore test
  2. Release/driver compatibility
  3. All members 7.0, FCV 7.0
  4. Replica healthy + majority
  5. Baseline metrics

ROLLING BINARIES
  6. Secondary B: stop -> 8.0 -> start -> healthy
  7. Secondary C: stop -> 8.0 -> start -> healthy
  8. rs.stepDown() on primary A
  9. Wait for new PRIMARY
 10. Former primary A: stop -> 8.0 -> start -> healthy

BURN-IN
 11. Confirm all 8.0 binaries, FCV still 7.0
 12. Run app smoke/integration tests
 13. Monitor errors, p99, replication, backup

ENABLE FCV
 14. Approve compatibility boundary
 15. Run setFeatureCompatibilityVersion "8.0"
 16. Verify FCV 8.0 on all members

CLOSE
 17. Validate application and operations
 18. Update runbook/backup plan/metrics
```

This is a study outline; consult exact MongoDB 8.0 documentation and add commands/checks tailored to your real deployment.

---

## 61. Official Reference Documentation

The links below help verify version-specific behavior:

1. [MongoDB Versions and Upgrade Paths](https://www.mongodb.com/docs/mongodb-versions/) — release cadence, binary upgrades vs. FCV, and Atlas/self-managed details.
2. [Upgrade a Replica Set to 8.0](https://www.mongodb.com/docs/v8.0/release-notes/8.0-upgrade-replica-set/) — 7.0→8.0, secondaries first, stepdown, FCV.
3. [Upgrade a Sharded Cluster to 8.0](https://www.mongodb.com/docs/v8.0/release-notes/8.0-upgrade-sharded-cluster/) — balancer, CSRS, shards, `mongos`, FCV.
4. [setFeatureCompatibilityVersion](https://www.mongodb.com/docs/manual/reference/command/setFeatureCompatibilityVersion/) — syntax, `confirm`, `dryRun` from 8.3, transition behavior.
5. [Downgrade 8.0 to 7.0](https://www.mongodb.com/docs/v8.0/release-notes/8.0-downgrade/) — Community/Enterprise policies.
6. [Upgrade Replica Set to 9.0](https://www.mongodb.com/docs/manual/release-notes/9.0-upgrade-replica-set/) — upgrade procedure for eligible source paths.
7. [Upgrade 8.0 Replica Set to 9.0](https://www.mongodb.com/docs/manual/release-notes/9.0-upgrade-from-8.0-replica-set/) — a specific upgrade path.
8. [Upgrade 8.0 Sharded Cluster to 9.0](https://www.mongodb.com/docs/manual/release-notes/9.0-upgrade-from-8.0-sharded-cluster/) — config servers, shards, `mongos`, and FCV.
9. [Downgrade 9.0 Replica Set to 8.3](https://www.mongodb.com/docs/manual/release-notes/9.0-downgrade-replica-set/) — prerequisites, FCV, and binary downgrade.
10. [Downgrade 9.0 to 8.0](https://www.mongodb.com/docs/manual/release-notes/9.0-downgrade-to-8.0/) — alternate path with dedicated prerequisites.
11. [Replica Set Status](https://www.mongodb.com/docs/manual/reference/method/rs.status/) — inspecting members and health.
12. [Replica Set Step Down](https://www.mongodb.com/docs/manual/reference/method/rs.stepDown/) — election behavior.
13. [FCV Compatibility Reference](https://www.mongodb.com/docs/manual/reference/command/getParameter/) — querying effective parameters.
14. [Upgrade Major MongoDB Version for an Atlas Cluster](https://www.mongodb.com/docs/atlas/tutorial/major-version-change/) — Atlas managed workflow.
15. [MongoDB Release Notes](https://www.mongodb.com/docs/manual/release-notes/) — compatibility changes and prerequisites.
16. [Java Sync Driver Compatibility](https://www.mongodb.com/docs/drivers/java/sync/current/compatibility/) — driver/server version matrix.
17. [MongoDB Server Stable API](https://www.mongodb.com/docs/manual/reference/stable-api/) — API guarantees and limits.
18. [MongoDB Backup Methods](https://www.mongodb.com/docs/manual/core/backups/) — backup/restore for self-managed deployments.
19. [Sharded Cluster Balancer](https://www.mongodb.com/docs/manual/core/sharding-balancer-administration/) — managing balancing during maintenance.
20. [MongoDB Operations Checklist](https://www.mongodb.com/docs/manual/administration/production-notes/) — production deployment and operational constraints.

**Note:** MongoDB updated release cadence and downgrade policies across the 8.x/9.x lines. Documentation pages may render by version selector or evolve per release. When planning production work, lock in the exact URL/version selector and verify the exact support matrix rather than relying solely on a "current" page.

---

## 62. Conclusion

**Rolling upgrades** in MongoDB focus on keeping replica sets or sharded clusters healthy with majority intact while swapping binaries—specifically upgrading **SECONDARIES first**, then stepping down and upgrading the former PRIMARY. For sharded clusters, follow the release-mandated dependency order of **config servers → shards → `mongos`**.

**Feature Compatibility Version** controls when the deployment allows features that persist backward-incompatible data. Running 8.0 binaries with FCV 7.0 during burn-in preserves compatibility boundaries, whereas raising FCV to 8.0 can restrict downgrade paths. FCV is not a full-data undo switch.

**Downgrading** is a separate decision constrained by release, edition, topology, persisted features, and MongoDB policy. Major differences exist between 8.0 and 8.3/9.0; never point an older binary directly at a newer data directory just to force a rollback.

A sound upgrade plan relies on **verified backups, a valid upgrade path, driver/app compatibility tests, baseline metrics, healthy majority, a burn-in period, approved FCV enablement, and a genuinely supported restore/downgrade runbook**.

**A successful upgrade is not just running the new version number; it is transitioning the entire system into its new state while maintaining control over availability, data integrity, performance, and recoverability.**
