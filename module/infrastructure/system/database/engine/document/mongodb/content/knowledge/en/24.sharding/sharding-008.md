# Zone Sharding and Data Locality Constraints in MongoDB

As a MongoDB application grows across geographic regions, enterprise customers, or data groups with distinct operational requirements, the question is no longer only **“how many shards do we split data across?”**, but also **“which shards are allowed to hold which groups of data?”**. A system may need European customer orders on European shards, Asian data on corresponding shards, or a dedicated shard group reserved for a large tenant.

**Zone sharding** (also referred to as *tag-aware sharding* in some documentation) is a MongoDB Sharding feature that binds **one or more shard key value ranges** to **shards belonging to a corresponding zone**. The balancer uses those constraints to place matching **chunks/ranges** onto shards permitted to serve that zone.

It is a very useful tool for organizing data placement, yet also an easy one to misunderstand. Zone sharding **does not create shards by itself**, **does not physically move servers to a country**, **does not replace replication rules**, and **cannot stand alone as legal proof of data residency compliance**.

This lesson explains:

- How zones, shards, shard keys, zone ranges, and chunks/ranges relate to one another.
- How to design a shard key to route regional/tenant data to the right shard group.
- How to configure zones using **`sh.addShardToZone()`** and **`sh.updateZoneKeyRange()`**.
- How to interpret range bounds, inspect the balancer, and observe actual data placement.
- Risks around pre-existing data, migrations, failover, backups, replication, and zone changes.
- When zone sharding fits versus when a separate-cluster architecture is needed.
- How to write Java/Spring Data applications that supply shard keys consistently, query the right region, and limit cross-shard operations.

The commands below are for demonstration on a **multi-shard test cluster** only. Never run commands that alter zones, shard keys, the balancer, or placement on production without change management, proper authorization, and a verification plan.

## 1. Reviewing sharded cluster architecture

A MongoDB sharded cluster typically consists of:

| Component | Role |
|---|---|
| **mongos** | Router accepting application queries, identifying relevant shards, and forwarding commands |
| **Config server replica set (CSRS)** | Manages metadata on sharding, zones, and data distribution |
| **Shard** | Group of machines storing a portion of sharded collection data; typically a replica set |
| **Shard key** | Field or combination of fields used to locate data in the shard key space |
| **Chunk/range** | A shard key value interval assigned to a shard at a given time |
| **Balancer** | Component managing load balancing and enforcing distribution constraints such as zones |

High-level diagram:

~~~text
                     Application
                        |
                        v
                   +---------+
                   |  mongos |
                   +---------+
                        |
              metadata from config servers
                        |
          +-------------+-------------+
          |             |             |
          v             v             v
       Shard A       Shard B       Shard C
     (replica set) (replica set) (replica set)
          |             |             |
       Documents     Documents     Documents
       belonging     belonging     belonging
       to range A    to range B    to range C
~~~

MongoDB does not partition a collection round-robin (“first document on machine 1, next document on machine 2”). It determines storage location from **shard key values** and range/chunk placement metadata.

### 1.1. Key-based sharding vs. replication

These two mechanisms complement each other but solve different problems:

- **Sharding** splits **subsets of a collection’s data** across shards to scale storage and load.
- **Replication** creates and maintains **copies within the same shard/replica set** for fault tolerance and policy-driven reads.

For instance, a shard in an EU zone can still have replica set members deployed in other regions if infrastructure is configured that way. Zones constrain **which shard owns a range**, without automatically controlling the physical location of every replica set member.

### 1.2. The balancer and range ownership

When a range moves from Shard A to Shard B, MongoDB coordinates data transfer and updates metadata. Across versions, documentation and diagnostics may use **chunk**, **range**, or equivalent optimization terms.

Conceptually, zone sharding establishes the rule:

> Ranges whose shard keys fall within zone X must be assigned to shards belonging to zone X.

The balancer works to bring actual placement into compliance. **Configuring a zone does not mean every document has finished moving the instant the command returns.**

## 2. What is zone sharding?

A **zone** is a logical label defined by an administrator, for example:

~~~text
ZONE_EU
ZONE_APAC
ZONE_US
ZONE_TENANT_PREMIUM
~~~

A zone is not a machine, a database, or a separate collection. It describes **the group of shards permitted to hold shard key ranges assigned to that zone**.

Three core relationships exist:

1. **Shard → Zone:** assign shards to one or more zones.
2. **Shard-key range → Zone:** assign a shard key interval of a collection to a zone.
3. **Balancer → Placement:** migrate ranges onto shards belonging to the matching zone.

### 2.1. Data residency partitioning example

Suppose the **geo_orders.orders** collection has shard key:

~~~javascript
{
  dataRegion: 1,
  orderId: 1
}
~~~

Where:

- **dataRegion** is a policy-determined business region code, such as `"EU"`, `"APAC"`, or `"US"`.
- **orderId** distinguishes orders within the same region.

The administrator wants:

~~~text
dataRegion = EU   --> only shards in ZONE_EU
dataRegion = APAC --> only shards in ZONE_APAC
dataRegion = US   --> only shards in ZONE_US
~~~

Diagram:

~~~text
                  Document shard key
                    { dataRegion, orderId }
                              |
               +--------------+--------------+
               |              |              |
          dataRegion=EU  dataRegion=APAC  dataRegion=US
               |              |              |
               v              v              v
           ZONE_EU        ZONE_APAC        ZONE_US
               |              |              |
         +-----+-----+     +--+---+      +---+---+
         |           |     |      |      |       |
       shardEU1   shardEU2 shardAP1 shardAP2 shardUS1
~~~

This diagram uses logical names only. Whether `shardEU1` physically stores data on hardware in the EU depends on **infrastructure/replica set configuration and deployment procedures**, not on the zone name itself.

### 2.2. A zone can contain multiple shards

~~~text
ZONE_EU:
  shardEU1
  shardEU2
  shardEU3
~~~

When a zone contains multiple shards, MongoDB can distribute ranges belonging to that zone across those shards per balancer rules, data sizes, and placement constraints.

Thus, **a zone does not force all data onto a single shard**. This preserves locality constraints while allowing scaling within the zone.

### 2.3. A shard can belong to multiple zones

Example:

~~~text
shardShared:
  ZONE_EU
  ZONE_APAC
~~~

Here `shardShared` is permitted to hold ranges from both EU and APAC. If policy requires **strictly preventing two data groups from co-residing**, assigning one shard to two zones undermines that isolation intent.

**To enforce location isolation, audit each shard’s actual zone memberships**, rather than relying on tidy zone names.

### 2.4. A zone can cover multiple ranges

A zone can be bound to multiple distinct shard key intervals. This helps when several region codes share one shard group:

~~~text
ZONE_EU:
  dataRegion=EU
  dataRegion=EEA

ZONE_APAC:
  dataRegion=APAC
  dataRegion=SEA
~~~

Ranges assigned to zones must be defined so they **do not overlap illegally**, and enough shards must belong to each zone for placement to succeed.

### 2.5. Where does data outside any zone go?

**Unzoned ranges** are intervals not assigned to any specific zone. MongoDB can place them on any eligible shard under normal balancing rules, with no automatic restriction to a country or named shard group.

This is especially dangerous for region fields:

~~~javascript
{
  dataRegion: "UNKNOWN",
  orderId: "O-999"
}
~~~

If `"UNKNOWN"` is not covered by a zone range and writes are still permitted, the document may land outside the intended residency design. **Zone sharding is not a schema validator**; the application must enforce valid region codes and define policy for unclassified data.

## 3. How do zones differ from shard keys and the balancer?

| Concept | Function | What it does NOT guarantee by itself |
|---|---|---|
| Shard key | Defines value space for routing/distribution | Does not inherently know legal data locality goals |
| Zone | Groups shards and allowed ranges | Does not physically relocate machines into a region |
| Balancer | Coordinates placement per cluster rules and state | Does not guarantee instantaneous migration |
| Replica set | Maintains copies of a shard’s data | Not automatically geo-restricted by a zone label |
| Read preference | Selects replica member for eligible reads | Does not change which shard owns a document |
| Schema validation | Enforces field types, presence, or value enums | Does not choose shards/zones for placement |
| Authorization | Controls who can read/write | Does not configure physical residency |

Building “EU data stays in EU only” requires coordinating **shard placement, placement of all replica set members, backup/restore policies, sync pipelines, and access control**. A name like `ZONE_EU` alone is never enough.

## 4. The shard key is the foundation of zone constraints

Zone sharding operates over **shard key value ranges**. Therefore, shard key selection dictates whether zones can cover the desired data subsets.

### 4.1. Design with the region field leading

Suitable example for regional partitioning:

~~~javascript
{ dataRegion: 1, orderId: 1 }
~~~

Order shard key value:

~~~javascript
{
  dataRegion: "EU",
  orderId: "O-EU-1001"
}
~~~

Documents sharing a `dataRegion` sit contiguously in compound shard key order, making zone range definitions straightforward.

### 4.2. Design lacking the region field

Example:

~~~javascript
{ orderId: "hashed" }
~~~

If `orderId` is the sole hashed key, hash values do not group orders by **`dataRegion`** into a contiguous interval. You cannot define a zone range for `dataRegion = "EU"` the way you can when `dataRegion` leads the shard key.

If residency is mandatory, fix the shard key before launch instead of expecting MongoDB to infer zones from a non-key field.

### 4.3. Compound shard keys enable both zoning and load spread

A shard key consisting solely of:

~~~javascript
{ dataRegion: 1 }
~~~

creates **very low cardinality**: with only three regions, an entire region’s data shares a single shard key value, hindering load distribution and range splitting.

Adding a discriminating field such as `orderId`:

~~~javascript
{ dataRegion: 1, orderId: 1 }
~~~

provides many distinct shard key values so MongoDB can split ranges within a region. Still, evaluate real queries, `orderId` monotonicity, write hotspots, per-tenant sizes, and indexes.

### 4.4. Field order determines query targeting

Suppose the shard key is:

~~~javascript
{ dataRegion: 1, orderId: 1 }
~~~

Queries with both fields:

~~~javascript
db.orders.findOne({
  dataRegion: "EU",
  orderId: "O-EU-1001"
});
~~~

favor `mongos` routing directly to the owning range/shard.

Conversely:

~~~javascript
db.orders.findOne({
  orderId: "O-EU-1001"
});
~~~

omits the `dataRegion` prefix and may query multiple shards (*scatter-gather*). Having a secondary index on `orderId` on shards does not make a prefix-less query target a single shard.

### 4.5. Region is business metadata, never trust raw headers blindly

If the server lets clients submit:

~~~json
{
  "dataRegion": "EU",
  "orderId": "O-1234"
}
~~~

users could tag the wrong region and route data into a non-compliant zone.

Derive `dataRegion` from **tenant configuration, customer residency policies, or verified attributes**, validate at the system boundary, check authorization, and audit the decision source. Region fields are not decorative strings to alter casually.

## 5. Preparing a sharded cluster for hands-on practice

Subsequent examples assume a **test sharded cluster** with:

~~~text
mongos router
config server replica set

shardEU1
shardEU2
shardAP1
shardAP2
shardUS1
~~~

These shard names are **illustrative**; substitute the actual shard names reported by your cluster. Administrators have deployed the nodes, added them to the cluster, and connected `mongos` to config servers. This lesson **does not simulate residency** by naming five shards inside a standalone MongoDB; zone sharding is only meaningful in a sharded cluster.

### 5.1. Verify you are connected to mongos

In `mongosh`:

~~~javascript
db.adminCommand({ hello: 1 });
~~~

Through `mongos`, output identifies the router—for example **`msg: "isdbgrid"`** in supported versions.

Another inspection tool:

~~~javascript
sh.status();
~~~

Displays sharding and zone metadata at admin level (requires appropriate privileges). If `sh.status()` fails, verify you did not connect directly to a **`mongod` shard member** by mistake.

### 5.2. List existing shards

~~~javascript
db.adminCommand({ listShards: 1 });
~~~

Inspect each shard’s **`_id`** field to use exact names in subsequent commands. Never guess shard names from hostnames or assume calling a command with `"shardEU1"` creates that shard.

### 5.3. Verify shards are actually deployed in intended locations

Before assigning zones, verify:

1. Are the shard’s **replica set members** placed in the policy-approved country/region?
2. Are **storage volumes, snapshots, and backups** kept in permitted regions?
3. Does the cluster use the required **cloud provider regions, availability zones**, and node placement?
4. Do **logs, audits, exports, or analytics** copy data elsewhere?
5. Do shards hold other collections, and is co-mingling different residency data permitted?

Zones are a metadata layer over **existing shards**. Physical infrastructure and storage governance must be verified independently.

## 6. Assigning shard membership with `sh.addShardToZone()`

Once shard names are confirmed, administrators attach shards to zones:

~~~javascript
sh.addShardToZone("shardEU1", "ZONE_EU");
sh.addShardToZone("shardEU2", "ZONE_EU");

sh.addShardToZone("shardAP1", "ZONE_APAC");
sh.addShardToZone("shardAP2", "ZONE_APAC");

sh.addShardToZone("shardUS1", "ZONE_US");
~~~

Meaning:

- **shardEU1**, **shardEU2** may hold ranges assigned to `ZONE_EU`.
- **shardAP1**, **shardAP2** may hold ranges for `ZONE_APAC`.
- **shardUS1** may hold ranges for `ZONE_US`.

This updates shard-to-zone membership. It **does not bind any collection’s shard key ranges** to a zone, nor does it create documents or collections.

### 6.1. One shard in multiple zones

Functionally, you can assign:

~~~javascript
sh.addShardToZone("shardShared", "ZONE_EU");
sh.addShardToZone("shardShared", "ZONE_APAC");
~~~

However, under strict residency policies separating EU and APAC, this is likely inappropriate. A shard in both zones is eligible to hold ranges from **both zones**.

### 6.2. Membership does not prove physical region

The command:

~~~javascript
sh.addShardToZone("shardEU1", "ZONE_EU");
~~~

does not verify that `shardEU1`’s data center is physically in Europe. **`ZONE_EU`** is just an administrator-assigned label. If `shardEU1` sits in the wrong location, zones will not catch the infrastructure mistake.

### 6.3. Removing a shard from a zone

When changing placement under change control:

~~~javascript
sh.removeShardFromZone("shardEU2", "ZONE_EU");
~~~

This alters which shards may hold `ZONE_EU` ranges. Some removals may be rejected or fail to drain if no eligible shard remains for active zone ranges, depending on cluster state.

**Never remove the last shard from a zone holding data without provisioning a replacement and verifying migration.** Production zone membership changes are storage architecture changes.

## 7. Binding shard key ranges to zones with `sh.updateZoneKeyRange()`

For zones to govern placement of a **specific collection**, assign **shard key ranges** to zones.

General syntax:

~~~javascript
sh.updateZoneKeyRange(
  "<database>.<collection>",
  <minShardKeyDocument>,
  <maxShardKeyDocument>,
  "<zoneName>"
);
~~~

Parameters:

| Parameter | Role |
|---|---|
| Namespace | Database and collection name, e.g. `geo_orders.orders` |
| min | Lower bound of the shard key range |
| max | Upper bound of the shard key range |
| zone | Zone name assigned to the range |

**Zone range bounds form a half-open interval `[min, max)`: `min` is inclusive, `max` is exclusive.** MongoDB compares values using BSON/shard key order for the collection, not intuitive string comparisons on a single field.

### 7.1. Why use MinKey and MaxKey?

When the shard key has two fields:

~~~javascript
{ dataRegion: 1, orderId: 1 }
~~~

and you want a zone covering **every `orderId` within a `dataRegion`**, you must span the full domain of allowed `orderId` values.

Use BSON sentinels **MinKey** and **MaxKey**:

~~~javascript
{
  dataRegion: "EU",
  orderId: MinKey()
}

{
  dataRegion: "EU",
  orderId: MaxKey()
}
~~~

These are **range-boundary sentinels**, not real order IDs. Assuming the schema restricts `orderId` to non-empty Strings, every valid `orderId` lies strictly between these sentinels.

Because **`max` is exclusive**, this excludes the sentinel `MaxKey` value itself at the `orderId` position if a document ever stored that type; with a String-only schema that case never arises.

### 7.2. Creating the EU zone range

~~~javascript
sh.updateZoneKeyRange(
  "geo_orders.orders",
  { dataRegion: "EU", orderId: MinKey() },
  { dataRegion: "EU", orderId: MaxKey() },
  "ZONE_EU"
);
~~~

This binds the shard key band for **dataRegion = "EU"** to **ZONE_EU**.

### 7.3. Creating APAC and US zone ranges

~~~javascript
sh.updateZoneKeyRange(
  "geo_orders.orders",
  { dataRegion: "APAC", orderId: MinKey() },
  { dataRegion: "APAC", orderId: MaxKey() },
  "ZONE_APAC"
);

sh.updateZoneKeyRange(
  "geo_orders.orders",
  { dataRegion: "US", orderId: MinKey() },
  { dataRegion: "US", orderId: MaxKey() },
  "ZONE_US"
);
~~~

These ranges **do not overlap** because their `dataRegion` values differ.

### 7.4. An example illustrating `[min, max)` bounds

Suppose a simple single-field shard key:

~~~javascript
{ score: 1 }
~~~

And zone range:

~~~javascript
sh.updateZoneKeyRange(
  "demo.scores",
  { score: 0 },
  { score: 100 },
  "ZONE_LOW"
);
~~~

Then:

- `score = 0`: inside the range.
- `score = 50`: inside the range.
- `score = 99`: inside the range.
- **`score = 100`: outside the range**.
- `score = -1`: outside the range.

Values outside this range are **not protected by `ZONE_LOW`** simply because a zone exists. Configure covering ranges or enforce explicit rules for out-of-band values.

### 7.5. Do not define overlapping ranges

Suppose Zone A covers:

~~~text
[0, 100)
~~~

and Zone B is assigned:

~~~text
[50, 150)
~~~

Both overlap on `[50, 100)`, creating conflicting zone placement. Within a collection, zone ranges must be **non-overlapping**; MongoDB validates ranges on configuration.

Do not try to handle a document “belonging to two regions” via overlapping zone ranges. Define a single **home region** or redesign data partitioning.

### 7.6. Match the full shard key structure

For compound shard keys, express bounds explicitly in **exact shard key field order**, using `MinKey`/`MaxKey` for fields spanning full domains. Exact prefix/bound shortcuts vary by command and version; supplying all shard key fields as shown avoids ambiguity.

If the collection uses a **hashed shard key**, check bound rules and key behavior carefully; never assume a hash range expresses “every document with `country=EU`” unless `country` forms a valid non-hashed prefix.

### 7.7. Zone ranges are per-namespace

Configuring:

~~~javascript
sh.updateZoneKeyRange(
  "geo_orders.orders",
  { dataRegion: "EU", orderId: MinKey() },
  { dataRegion: "EU", orderId: MaxKey() },
  "ZONE_EU"
);
~~~

does not automatically apply to:

~~~text
geo_orders.payments
geo_orders.orderEvents
geo_orders.customers
~~~

If those collections also require residency by `dataRegion`, configure appropriate shard keys and zone ranges **for each collection** or choose another data layout. Shard zone memberships are cluster-wide and reusable, while range mappings are per-namespace.

## 8. Converting a collection to a sharded collection

For illustration, assume **geo_orders.orders** is unsharded and empty. Run through `mongos` with admin privileges.

### 8.1. Create database and shard key index

~~~javascript
use geo_orders

db.orders.createIndex(
  { dataRegion: 1, orderId: 1 },
  { name: "idx_data_region_order" }
);
~~~

Ensure shard key and index prerequisites are met. For collections with existing unique indexes, verify sharded unique-index constraints before calling `shardCollection`.

### 8.2. Enable sharding and declare the shard key

In environments/versions requiring database sharding enablement:

~~~javascript
sh.enableSharding("geo_orders");
~~~

Then:

~~~javascript
sh.shardCollection(
  "geo_orders.orders",
  { dataRegion: 1, orderId: 1 }
);
~~~

Some newer versions no longer require calling `sh.enableSharding` separately before `sh.shardCollection`; check your environment’s version behavior. The key point is that the collection must be sharded on a key aligned with your zone ranges.

### 8.3. Order of zone setup affects initial cost

Two operational approaches:

**Approach A — Configure before loading data:** assign shard memberships, define zone ranges, and run `shardCollection` on an empty collection in your version’s supported order. MongoDB can use zone ranges during initial chunk creation, reducing the need to migrate misplaced data later.

**Approach B — Configure after data already exists:** add/bind zone ranges on an existing collection. The balancer must then migrate chunks/ranges sitting on non-compliant shards.

For residency-sensitive workloads, **avoid writing live data into a cluster before placement policies and compliant infrastructure are in place**. Adding zones afterward does not erase historical data that previously lived elsewhere or in snapshots/backups.

### 8.4. Insert sample data

~~~javascript
db.orders.insertMany([
  {
    _id: "ORDER-EU-001",
    dataRegion: "EU",
    orderId: "EU-001",
    tenantId: "TENANT-EU-A",
    amountCents: NumberLong("12500"),
    status: "CREATED"
  },
  {
    _id: "ORDER-EU-002",
    dataRegion: "EU",
    orderId: "EU-002",
    tenantId: "TENANT-EU-B",
    amountCents: NumberLong("9800"),
    status: "PAID"
  },
  {
    _id: "ORDER-AP-001",
    dataRegion: "APAC",
    orderId: "AP-001",
    tenantId: "TENANT-AP-A",
    amountCents: NumberLong("15000"),
    status: "CREATED"
  },
  {
    _id: "ORDER-AP-002",
    dataRegion: "APAC",
    orderId: "AP-002",
    tenantId: "TENANT-AP-B",
    amountCents: NumberLong("5900"),
    status: "PAID"
  },
  {
    _id: "ORDER-US-001",
    dataRegion: "US",
    orderId: "US-001",
    tenantId: "TENANT-US-A",
    amountCents: NumberLong("23000"),
    status: "CREATED"
  }
]);
~~~

Run `insertMany` once on an empty test collection; fixed `_id`s will error on re-run. Five documents cannot test balancing/performance; this fixture simply verifies **filter predicates and the shard key model**.

## 9. Verifying zone membership and zone ranges

One of the biggest mistakes is running `sh.updateZoneKeyRange` and assuming data **is already in the right place**. Verify both **configuration** and **actual placement** from reliable sources.

### 9.1. Overview with `sh.status()`

~~~javascript
sh.status();
~~~

Depending on version and collection count, output displays:

- List of shards and attributes.
- Sharded namespaces.
- Shard keys and partitioning modes.
- Range/chunk distribution details.
- Declared zone/tag ranges.

**`sh.status()` inspects metadata**, not proof that no data copies linger in backups, snapshots, or out-of-region replica members.

### 9.2. Check membership in config metadata

With metadata read privileges:

~~~javascript
db.getSiblingDB("config")
  .shards
  .find(
    {},
    { _id: 1, host: 1, tags: 1 }
  );
~~~

In versions storing zone membership in **`tags`**, results look like:

~~~javascript
{
  _id: "shardEU1",
  tags: ["ZONE_EU"]
}
~~~

Field/metadata names may vary by version. **Never edit `config.shards` directly** to add zones; use MongoDB’s supported admin helpers/commands.

### 9.3. View collection zone ranges

~~~javascript
db.getSiblingDB("config")
  .tags
  .find({
    ns: "geo_orders.orders"
  });
~~~

Zone range metadata in supported versions typically shows:

~~~javascript
{
  ns: "geo_orders.orders",
  min: {
    dataRegion: "EU",
    orderId: MinKey()
  },
  max: {
    dataRegion: "EU",
    orderId: MaxKey()
  },
  tag: "ZONE_EU"
}
~~~

This confirms **the EU range is declared for `ZONE_EU`**. It **does not yet prove all corresponding chunks are currently owned by `shardEU1` or `shardEU2`**.

### 9.4. Separate checking “rules” from checking “enforcement”

| Question | Appropriate observation source |
|---|---|
| Which shards belong to `ZONE_EU`? | `sh.status` / shard membership metadata |
| Which key ranges belong to `ZONE_EU`? | `sh.status` / `config.tags` by namespace |
| Which shard currently owns a chunk/range? | Collection placement metadata, supported sharding tools |
| Is the balancer running or failing? | `sh.getBalancerState` / `sh.isBalancerRunning` / logs & monitoring per version |
| Have migrations finished? | Balancer status, per-shard distribution, verified outside transition windows |
| Do copies exist outside the EU? | Audit all replica sets, backups, logs, exports, and infrastructure |

Only combining all these checks yields a complete residency picture.

### 9.5. Checking balancer status

Common helpers:

~~~javascript
sh.getBalancerState();
sh.isBalancerRunning();
~~~

In supported `mongosh` versions, these report balancer enablement and active running status. Never conclude from a single **`isBalancerRunning() = false`** call that all migrations are complete or all ranges sit in the right zones: the balancer may simply be between rounds or disabled.

In production, inspect migration history, monitoring alerts, and range placement using your version’s supported tools.

### 9.6. Inspect collection-level distribution

In supported `mongosh`/server versions:

~~~javascript
db.getSiblingDB("geo_orders")
  .orders
  .getShardDistribution();
~~~

Commands/helpers vary by shell and server version. Per-shard document/byte stats show current distribution, yet **do not prove every EU document sits on an EU shard** from totals alone.

Verifying compliance requires checking **range boundaries, current ownership, and zone membership**, not just per-shard document counts.

### 9.7. Reading config metadata must stay read-only

Never run:

~~~javascript
// Never perform manual metadata edits like these.
db.getSiblingDB("config").tags.updateOne(...);
db.getSiblingDB("config").chunks.deleteMany(...);
~~~

Sharding metadata is managed by MongoDB. Direct edits risk metadata corruption and cluster failures. Use published, version-appropriate zone/migration admin helpers.

## 10. How does the balancer enforce zone constraints?

Once zone ranges are bound and zones have member shards, MongoDB’s balancer moves non-compliant chunks/ranges into place.

For example, before enabling zones:

~~~text
EU range:
  shardAP1 owns one part
  shardEU1 owns the rest

New zone rule:
  EU range -> ZONE_EU
  ZONE_EU members -> shardEU1, shardEU2
~~~

Target state after balancing:

~~~text
EU range:
  shardEU1
  shardEU2

shardAP1:
  no longer owns EU ranges in metadata
~~~

### 10.1. Logical flow

~~~text
Declare zone range
        |
        v
MongoDB tracks range placement
        |
        v
Is any range on a non-zone shard?
        |
       Yes
        |
        v
Balancer evaluates migration/range management
        |
        v
Transfers ownership to a shard in the zone
        |
        v
Updates placement metadata
        |
        v
Continues checking remaining non-compliant ranges
~~~

Exact ordering, timing, and execution mechanics depend on version, collection type, shard count, and current load. This is a conceptual flow, not a literal sequential log of MongoDB internals.

### 10.2. Instant migration is not guaranteed

A command like:

~~~javascript
sh.updateZoneKeyRange(
  "geo_orders.orders",
  { dataRegion: "EU", orderId: MinKey() },
  { dataRegion: "EU", orderId: MaxKey() },
  "ZONE_EU"
);
~~~

primarily sets **the rule**. If EU chunks previously resided in the wrong zone, MongoDB needs time to complete migrations.

Duration depends on:

- Data volume to move.
- Number of ranges/chunks and fragmentation.
- Concurrent read/write load.
- Inter-shard bandwidth.
- Balancer configuration and state.
- Migration limits, network errors, or node health.

During transition, **never declare residency achieved** just because the configuration command returned `ok`.

### 10.3. What happens if the balancer is stopped?

If zones are defined while the balancer is disabled, ranges sitting on non-compliant shards **will not automatically migrate** as expected. Recording a placement policy does not mean the system moved the data.

In test environments, check status with the helpers above. Toggling the balancer in production requires dedicated operational procedures since it affects all sharded collections.

### 10.4. Moving data consumes resources

Migrations can increase:

- Inter-shard network I/O.
- Disk I/O and CPU on source/destination shards.
- Memory consumption during transfers.
- Query latency at certain moments.
- Capacity pressure on shards inside the zone.

Do not funnel a massive region onto one small shard merely because it is the only shard with the right zone label. When a region needs high capacity, provision **multiple shards in the zone** with a shard key capable of splitting ranges.

### 10.5. “In the right zone” differs from “evenly balanced”

If `ZONE_EU` has three shards, the constraint ensures EU ranges live on **permitted shards in `ZONE_EU`**. It does not guarantee each EU shard holds exactly one-third of documents or bytes.

Actual sizes and load depend on shard key distribution, document sizes, write patterns, balancer state, and range-splitting limits. Monitor **disk usage, IOPS, CPU, and hotspots**, not just shard counts.

## 11. Query targeting in zone sharding

Zone sharding governs placement; **`mongos` still routes queries using the shard key and metadata**.

### 11.1. Query with full shard key

~~~javascript
db.orders.find({
  dataRegion: "EU",
  orderId: "EU-001"
});
~~~

With shard key:

~~~javascript
{ dataRegion: 1, orderId: 1 }
~~~

`mongos` targets the range holding that key pair. Once zone placement converges, the query goes straight to the EU shard currently owning that range.

### 11.2. With `dataRegion` only

~~~javascript
db.orders.find({
  dataRegion: "EU",
  status: "PAID"
});
~~~

The query supplies the **shard key prefix**, so `mongos` restricts targeting to shards/ranges for `dataRegion: "EU"`. If `ZONE_EU` has multiple shards, the query may read **multiple shards inside `ZONE_EU`**, not necessarily just one.

Secondary indexes such as:

~~~javascript
db.orders.createIndex({
  dataRegion: 1,
  status: 1,
  orderId: 1
});
~~~

assist filtering within each shard depending on query patterns and planner. Still, **secondary indexes do not replace the shard key** and cannot make a query missing `dataRegion` target the right region.

### 11.3. With `orderId` only

~~~javascript
db.orders.find({
  orderId: "EU-001"
});
~~~

Without `dataRegion`, `mongos` may have to query many shards. If the application primarily looks up by `orderId`, choose a strategy:

- Include `dataRegion` in order-creation API responses and send it back on lookups.
- Maintain an **`orderId → dataRegion`** mapping with clear consistency and residency rules.
- Redesign the shard key/data model if most queries lack the region prefix.

Never create zones purely for operational preference while ignoring the application’s primary query patterns.

### 11.4. Explain to check which shards are queried

~~~javascript
db.orders.find({
  dataRegion: "EU",
  orderId: "EU-001"
}).explain("queryPlanner");
~~~

And:

~~~javascript
db.orders.find({
  orderId: "EU-001"
}).explain("queryPlanner");
~~~

In a sharded cluster, `explain` shows participating shards, plan trees, and stages. Exact field positions like **`shards`**, **`winningPlan`**, and **`SHARD_MERGE`** vary across versions and execution engines.

Compare the **set of shards receiving the query**, not just whether `IXSCAN` or `COLLSCAN` appears.

### 11.5. Zones do not guarantee regional locality from every app node

If an application running in Asia sends an EU query through an Asian `mongos`, the router still must forward commands to the EU shard per placement. This incurs **cross-region network latency** even though data sits in the right zone.

To achieve “EU data in EU, and EU requests served near EU,” align **application/API gateway routing, service deployment regions, and `mongos` placement**. Zones only govern where sharded collection data lives.

## 12. Moving out of a zone or changing boundaries

An organization may change data policies, add shards, or adjust partitions. Treat these changes as **data migrations**, not a casual one-line config tweak.

### 12.1. Removing a zone range

Common helper:

~~~javascript
sh.removeRangeFromZone(
  "geo_orders.orders",
  { dataRegion: "EU", orderId: MinKey() },
  { dataRegion: "EU", orderId: MaxKey() }
);
~~~

This removes the zone binding for a declared range. **Removing a range from a zone does not instantly move EU documents elsewhere.** Once unconstrained, the range becomes eligible for general balancing and placement must be monitored.

### 12.2. Migrating EU from an old zone to a new zone

A sound change plan typically includes:

1. Provision/verify shards in the new region, including all replica set members.
2. Add new shards to the target zone or create the new zone.
3. Reconfigure range mappings as supported by your version.
4. Ensure the balancer runs according to plan.
5. Wait for and monitor migrations until metadata ownership converges.
6. Handle residual data/backups in the old region per policy.
7. Only then remove old zone memberships or decommission old shards.

Never remove the last shard from a zone before a replacement target is ready. Nor should you alter key ranges on live data without accounting for in-flight requests and downstream readers.

### 12.3. Does changing the shard key update zones automatically?

Zone ranges are defined in the **shard key space**. If you change shard key structure via resharding or remodeling, ranges/zones must be **re-evaluated and reconfigured for the new key**.

Never assume zone ranges for `{dataRegion:1,orderId:1}` carry over as-is to `{tenantId:1,dataRegion:1}` or `{orderId:"hashed"}`. Verify version support and resharding/zone prerequisites separately.

### 12.4. Moving a document between regions is not just editing a string

If a customer changes residency from APAC to EU:

~~~javascript
{
  dataRegion: "APAC",
  orderId: "AP-001"
}
~~~

changing it to:

~~~javascript
{
  dataRegion: "EU",
  orderId: "AP-001"
}
~~~

modifies **a shard key value** and may require moving the document to another shard. MongoDB imposes specific prerequisites on shard key updates depending on version and execution mode; never fire off an arbitrary `updateMany` expecting a whole tenant to relocate safely.

At the business level, decide:

- Must historical data move, or only newly created records?
- Is downtime or a write freeze required during region transfer?
- How are references, unique keys, transactions, and indexes affected?
- How are old backups handled under compliance rules?
- If the transfer fails midway, how does application-level recovery/rollback work?

Residency changes usually require a **dedicated migration workflow**, not an uncontrolled field update.

## 13. Data placement constraints do not equal data residency certification

**Data residency** generally refers to storing or processing data within a specific geographic/legal boundary. **Data sovereignty** may further encompass legal jurisdiction and control. Exact requirements depend on contracts, data classification, and applicable regulations; never draw legal conclusions from zone names alone without context.

Zone sharding supports **range placement policies for a sharded collection**, not the entire information lifecycle.

### 13.1. Layers that must be audited

| Layer | Critical question |
|---|---|
| Sharded data | Are EU ranges bound to the EU zone and has placement converged? |
| Replica sets | Where are primary, secondary, hidden, and delayed shard members located? |
| Config servers | What metadata is stored on config servers and where do they run? |
| Backups/snapshots | In which regions are snapshots, PITR, cold archives, and replicas kept? |
| Migrations | Is residual data on out-of-region donor shards cleaned up and retained per policy? |
| Application logging | Do error logs, audits, traces, or request payloads leak sensitive data? |
| Query processing | Do query results pass through routers/services in other regions? |
| Export/ETL | Where are data lakes, warehouses, search indexes, or analytics pipelines hosted? |
| Access control | Are users/services in other regions permitted to read data per policy? |
| Disaster recovery | During DR recovery, into which region is data restored? |
| Encryption/key management | Where do encryption keys, KMS, access rules, and security infra reside? |
| Retention/deletion | On what schedule are live records and backup copies retained or purged? |

A system where **every EU chunk sits on `shardEU1`** yet `shardEU1`’s backups live in an unapproved region still fails data residency.

### 13.2. Replica sets can replicate data out of the region

Suppose the EU zone contains shard **`EU_RS`**, configured as:

~~~text
EU_RS
  primary:   Frankfurt
  secondary: Frankfurt
  secondary: Singapore
~~~

Zone sharding ensures EU ranges belong to `EU_RS`. However, the Singapore secondary still replicates **that shard’s** data via normal replication.

If policy requires **every physical copy of EU data to stay in the EU**, place **all data-bearing replica set members** accordingly—not just the primary or shard name.

Special members, snapshots, and DR setups must also be reviewed individually against policy.

### 13.3. Data can exist outside the zone during migration

If zones are applied **after data was already written**, documents may have started on other shards. During migration, MongoDB transfers ownership and cleans up old records per version rules.

Never treat **metadata range ownership transfer** as immediate proof that zero bytes remain on donor shards, snapshots, or historical backups. Verify cleanup status and storage retention at the infrastructure layer.

### 13.4. Cross-region queries still send data over the network

An aggregation not filtering on `dataRegion`:

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$status",
      totalOrders: { $sum: 1 }
    }
  }
]);
~~~

reads across shards in multiple zones to compute totals. Depending on the query plan, intermediate or final results cross through a router or merge shard.

**Zone placement does not automatically block cross-region queries.** If policy forbids raw data crossing borders, architecture must govern query paths, `mongos`/app placement, aggregations, and allowed data egress.

### 13.5. Do not self-certify legal compliance

Zone sharding is a **technical control**, not certification of GDPR, data localization laws, or contractual clauses. Compliance reviews require concrete legal/contractual criteria, operational policies, and end-to-end system evidence.

A practical approach separates two artifacts:

- **Placement design:** which `dataRegion` maps to which zone, and which shards belong to each zone.
- **Compliance evidence:** physical locations of all replicas, backups, network paths, logs, access flows, retention, audits, and periodic verification.

## 14. Designing zones for multi-tenant SaaS

A SaaS system can share one cluster while isolating placement by tenant.

### 14.1. Option A: zone by home region

Each tenant has a trusted configuration attribute:

~~~javascript
{
  tenantId: "TENANT-123",
  homeRegion: "EU"
}
~~~

Each business document contains:

~~~javascript
{
  dataRegion: "EU",
  tenantId: "TENANT-123",
  orderId: "ORD-100"
}
~~~

Candidate shard key:

~~~javascript
{
  dataRegion: 1,
  tenantId: 1,
  orderId: 1
}
~~~

Pros:

- Region sits at the prefix for zone ranges.
- Queries knowing `tenantId` and `dataRegion` leverage the shard key prefix.
- `tenantId`/`orderId` provide enough distinct values to split data within a zone when needed.

Cons:

- Queries by `orderId` without `dataRegion`/`tenantId` may query many shards.
- Changing a tenant’s `homeRegion` becomes a migration project.
- One oversized tenant can create hotspots or require dedicated capacity.

### 14.2. Option B: dedicated zone for a large tenant

Suppose tenant **ENTERPRISE-A** needs isolated infrastructure in a dedicated zone:

~~~text
ZONE_ENTERPRISE_A
  shardDedicatedA1
  shardDedicatedA2
~~~

For accurate zoning, the shard key must express ranges isolating that tenant. With shard key:

~~~javascript
{ tenantId: 1, orderId: 1 }
~~~

you can bind:

~~~javascript
sh.updateZoneKeyRange(
  "saas.orders",
  { tenantId: "ENTERPRISE-A", orderId: MinKey() },
  { tenantId: "ENTERPRISE-A", orderId: MaxKey() },
  "ZONE_ENTERPRISE_A"
);
~~~

And shard membership:

~~~javascript
sh.addShardToZone(
  "shardDedicatedA1",
  "ZONE_ENTERPRISE_A"
);

sh.addShardToZone(
  "shardDedicatedA2",
  "ZONE_ENTERPRISE_A"
);
~~~

Note that zones do not build an **absolute performance firewall**. Shards can share zones, and `mongos`, config servers, network links, and shared infra remain common. If a customer demands strict multi-layer isolation, a **dedicated cluster** may fit better.

### 14.3. Option C: region and tenant together in the key

To zone by region while querying primarily by tenant:

~~~javascript
{ dataRegion: 1, tenantId: 1, orderId: 1 }
~~~

A zone range covering all of EU uses:

~~~javascript
sh.updateZoneKeyRange(
  "saas.orders",
  {
    dataRegion: "EU",
    tenantId: MinKey(),
    orderId: MinKey()
  },
  {
    dataRegion: "EU",
    tenantId: MaxKey(),
    orderId: MaxKey()
  },
  "ZONE_EU"
);
~~~

With schema validation ensuring `tenantId` and `orderId` are valid Strings, the sentinels span the full expected business domain.

**Pay close attention to compound key field order and bound structure.** Never reorder fields or supply mismatched BSON types when defining ranges on an active collection.

### 14.4. One tenant with data in multiple regions

Not every tenant has a single home region. A global enterprise with offices in EU and US may need each order stored by **where the transaction occurred**. In that case:

- Assign `dataRegion` per document rather than per tenant.
- Enforce per-document authorization and routing policies.
- Accept that global tenant queries span zones, or maintain approved summary read models.
- Avoid moving historical records just because a tenant’s default preference changes.

Partitioning must match **actual data constraints**, rather than forcing one region per tenant if individual documents have independent residency rules.

## 15. Range sharding, hashed sharding, and zone sharding

**Range-based sharding** and **hashed sharding** govern how shard key values distribute; **zone sharding** adds placement constraints on the resulting ranges.

| Criterion | Ranged shard key with region prefix | Pure hashed shard key |
|---|---|---|
| Grouping all `dataRegion=EU` into a contiguous domain | Straightforward with region at prefix | Unnatural if region is not a suitable prefix |
| Regional queries | Can leverage prefix | Often scatter-gathers depending on key |
| Monotonic insert distribution | Can form hotspots if poorly designed | Hashing spreads values in hash space |
| Zoning by region | Intuitive, easy range mapping | Requires evaluating compound keys and actual hash ranges |
| Key range queries | Fits ordered range lookups | Hashing loses original value range targeting |

An engineering design can combine a **region prefix** with trailing fields designed for distribution. Never assume every hashed/range combination is identically supported or optimal: check your MongoDB version, compound hashed shard key features, `shardCollection` rules, and zone bound constraints.

### 15.1. Why not pick a shard key solely for zones?

A sound shard key balances:

1. **Load/write distribution** within each zone.
2. **Query targeting** for common access patterns.
3. Sufficient **cardinality** to split data.
4. **Cost of changing** the shard key or business fields.
5. **Unique index constraints** on the collection.
6. **Residency and isolation** requirements.
7. **Independent scaling** per region.

If `dataRegion` has only three values and all EU orders hammer one shard, being in the right zone still produces a hot shard. Consider **`orderId`/`tenantId`**, real distributions, and chunk/range sizes.

### 15.2. Must regional ranges use country code strings?

Not necessarily. Region codes can be business enums like **`REG_EU`**, **`REG_APAC`**, **`REG_US`**, or clearly ordered numeric IDs.

What matters:

- Stable BSON type.
- Mandatory, validated field.
- Auditable `business policy → dataRegion` mapping.
- All valid values covered by zone ranges.
- Zone updates rolled out **before** accepting data for a newly added region code when placement is strict.

## 16. Unique indexes, identifiers, and regional data

In a sharded collection, uniqueness constraints must be designed alongside the shard key. Never assume arbitrary unique indexes are automatically enforced globally as desired.

### 16.1. Unique index with the shard key as prefix

If a new collection uses:

~~~javascript
{ dataRegion: 1, orderId: 1 }
~~~

and business logic requires **each `(dataRegion, orderId)` pair to appear only once**, consider a unique index:

~~~javascript
db.orders.createIndex(
  { dataRegion: 1, orderId: 1 },
  {
    unique: true,
    name: "uq_region_order"
  }
);
~~~

On sharded collections, unique indexes generally require **the shard key as a prefix** under MongoDB’s supported rules. Never create a unique index on `orderId` alone and trust the cluster to enforce global uniqueness if `orderId` is not a shard-key prefix.

**Practical note:** the snippet shows **initial index design**. If a non-unique index already exists on the exact same key pattern as in section 8, do not simply run another `createIndex` differing only by `unique` expecting MongoDB to convert it automatically. Follow your MongoDB version’s index migration procedure.

### 16.2. Global `orderId` vs. regional `orderId` are different invariants

If business rules state:

~~~text
In EU: `EU-001` appears at most once.
In US: `EU-001` is allowed to exist too.
~~~

then uniqueness of **`(dataRegion, orderId)`** fits.

If the rule states:

~~~text
orderId = O-123 must be unique across the entire cluster,
regardless of dataRegion.
~~~

then a per-region unique compound key is **logically insufficient**: it allows `("EU", "O-123")` and `("US", "O-123")` to coexist.

You may need:

- An ID generator guaranteeing global uniqueness.
- A business-key registry with proper uniqueness enforcement.
- IDs embedding region info under a strict contract.
- Re-evaluating the shard key if lookups/identities are primarily global by `orderId`.

Never assume auto-generated `ObjectId` substitutes for **a strict business uniqueness invariant** across every sharded collection design.

### 16.3. `_id` is not always cluster-wide unique as expected

In sharded collections whose shard key **does not include `_id` under qualifying rules**, the unique `_id` index may be enforced **per shard**; the application must still prevent cluster-wide `_id` collisions by design.

Therefore, if APIs allow clients to set `_id` or multiple services generate `_id`s, analyze uniqueness under your exact topology/shard key rather than assuming “MongoDB always enforces global `_id` uniqueness” in every sharding setup.

### 16.4. Deduplicating requests in zone sharding

An API creating an order in the EU may receive:

~~~json
{
  "dataRegion": "EU",
  "requestId": "R-100",
  "orderId": "EU-001"
}
~~~

When a client retries the same request, the backend uses **the same `requestId`** without creating a duplicate order. Include `requestId` in a shard-key-compatible unique business index—e.g., `(dataRegion, requestId)` if the shard key/collection permits that constraint.

Do not force arbitrary fields into unique indexes if sharded unique index rules forbid it. When multiple independent uniqueness invariants must hold simultaneously, use a **dedicated registry collection or revised identity model**.

## 17. Enforcing region codes and preventing data “leaking outside zones”

Zone ranges only cover declared shard key values. If the application permits:

~~~javascript
{ dataRegion: null, orderId: "X-1" }
{ orderId: "X-2" }
{ dataRegion: "eu", orderId: "X-3" }
{ dataRegion: "EU ", orderId: "X-4" }
{ dataRegion: "MARS", orderId: "X-5" }
~~~

those documents may fall outside the ranges defined for String **`"EU"`**, **`"APAC"`**, or **`"US"`**.

### 17.1. Schema validation

Example creating a **new collection** permitting only three valid region codes:

~~~javascript
use geo_orders

db.createCollection("validatedOrders", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["dataRegion", "orderId", "tenantId"],
      properties: {
        dataRegion: {
          bsonType: "string",
          enum: ["EU", "APAC", "US"]
        },
        orderId: {
          bsonType: "string",
          minLength: 1
        },
        tenantId: {
          bsonType: "string",
          minLength: 1
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
~~~

The validator rejects inserts or updates with missing/mistyped/invalid regions when validation rules apply.

However:

- The validator **does not create zone ranges**.
- The validator **does not verify shard membership**.
- The validator **does not bind a tenant to its proper region**; if a user can pick any of the three enum values, authorization/mapping logic is still required.
- The new **`validatedOrders` collection is not automatically sharded**; to use zone sharding on it, shard it and configure ranges separately.

### 17.2. Protecting the `tenant → region` mapping

Suppose a tenant carries a trusted attribute:

~~~javascript
{
  tenantId: "T-EU-001",
  allowedDataRegion: "EU"
}
~~~

The backend must not allow creating an order for this tenant with `dataRegion = "US"` just because `"US"` is in the enum. Authenticate the caller, look up policy, determine `dataRegion`, then insert the document.

Multi-region API flow:

~~~text
Auth principal
      |
      v
Resolve trusted tenantId
      |
      v
Load tenant residency policy
      |
      v
Determine dataRegion
      |
      v
Validate allowed value
      |
      v
Insert document with matching shard key
~~~

If policies or regions change, enforce versioning and transactions/workflows instead of letting concurrent requests write conflicting `dataRegion` values for the same tenant unnoticed.

### 17.3. Do not rely on collation to fix sloppy region codes

Strings `"EU"`, `"eu"`, and `"EU "` must be normalized at the contract level from day one. Never expect a case-insensitive collation on an ad-hoc query to make a zone range for `"EU"` magically cover all casing variants. Zone ranges follow exact shard key value ordering, not arbitrary application normalization.

### 17.4. New region codes require a rollout procedure

Suppose the business adds region **LATAM**. Before the API writes LATAM data:

1. Provision physical shards and replication in the compliant location.
2. Add those shards to **`ZONE_LATAM`**.
3. Add zone ranges for `dataRegion = "LATAM"` on every relevant namespace.
4. Verify non-overlapping ranges, balancer state, and capacity.
5. Update validators and tenant policies.
6. Only then enable writes for the new region.

Shipping application code that accepts LATAM before configuring zones creates a window where LATAM documents land unzoned.

## 18. When a zone lacks shards or shards fill up

### 18.1. A zone has no remaining member shards

If a zone range is assigned yet the zone has no eligible shard to hold data, the balancer cannot place those ranges properly. Depending on the action, version, and cluster state, configuration commands or related operations may be rejected, stall, or error.

Never write application logic assuming **“if `ZONE_EU` runs out of shards, MongoDB will automatically spill EU data onto a US shard to stay online.”** Such fallback defeats zone constraints and is not a safe operational contract.

### 18.2. Running out of capacity inside one zone

~~~text
ZONE_EU: shardEU1 95% disk, shardEU2 94% disk
ZONE_US: shardUS1 20% disk
~~~

If EU data is restricted to `ZONE_EU`, spare capacity on `shardUS1` does not relieve EU’s disk limit. To add EU capacity:

- Expand storage/resources on EU shards.
- Add eligible shards to `ZONE_EU`.
- Tune the shard key and mitigate hotspots if needed.
- Review data partitioning or retention policies.

Never add a US shard to `ZONE_EU` just to clear a disk alert if doing so violates data residency constraints.

### 18.3. Jumbo or hard-to-split ranges

Massive data sharing a single shard key value or heavily skewed distributions can create ranges difficult to move or split under certain conditions. With a region-only shard key and few region values, a giant region becomes a bottleneck.

A compound shard key adding `orderId`/`tenantId` increases cardinality, though you must still examine monotonic values, query patterns, and your server version’s balancer behavior.

### 18.4. Single-region outages vs. availability requirements

If all EU shards reside in the EU and the EU suffers a broad infrastructure outage, EU data may become temporarily unavailable. This is an explicit trade-off:

~~~text
Strict geographic placement
             |
             v
No EU copies allowed outside region
             |
             v
Cross-region failover is restricted
             |
             v
Design DR within permitted boundaries
~~~

Strict residency policies restrict disaster recovery topologies. Agree on **RPO/RTO, secondary/backup locations, and recovery playbooks** before an outage happens, rather than silently replicating to unapproved regions.

## 19. Zones and hashed shard keys: practical design limits

Suppose a system wants both partitioning by `country` and uniform spread:

~~~javascript
{
  country: 1,
  customerId: "hashed"
}
~~~

Such a compound hashed shard key helps in supported versions because `country` at the prefix groups geographically while the hashed suffix spreads within each country. Still:

- Never change a shard key casually on a populated collection.
- Verify **server version** and index/`shardCollection` rules for compound hashed keys.
- Zone ranges must match the **actual shard key order**, not plaintext fields when hashed.
- Query targeting and unique indexes carry specific constraints.

In particular, never write:

~~~javascript
{ customerId: "hashed" }
~~~

expecting MongoDB to define a contiguous range covering every customer with `country = "EU"` when `country` is merely a non-key document field.

### 19.1. Time-based shard keys instead of region keys

If the shard key is:

~~~javascript
{ createdAt: 1, orderId: 1 }
~~~

EU and US documents interleave by `createdAt`. There is no direct way to bind **all of EU** to one zone via a `createdAt` interval when `country` is absent from the key.

Zone ranges can separate **hot/cold data tiers by time** if that is your goal, but that is a different placement problem from geographic residency. Never confuse **hot/cold storage zones** with **geographic residency zones**.

### 19.2. Not every collection needs the same shard key

Orders, customers, and analytics collections have distinct query patterns. However, if all share regional residency requirements, they need a coordinated strategy:

- Each collection has a shard key supporting regional zones.
- Or separate data into dedicated regional databases/clusters.
- Or strictly restrict which data is allowed to be aggregated elsewhere.

If one collection uses a shard key unable to express region, it becomes a compliance gap in your residency design even if the main collection is properly zone-sharded.

## 20. Java MongoDB Sync Driver: writing the right shard key and querying the right region

Regular Java applications **do not call `sh.updateZoneKeyRange` per request**. Cluster administration manages zones and the balancer; the backend sends documents with **the right shard key**, validates data, and uses targetable filters.

In the examples below:

- The MongoDB cluster is sharded on **`{dataRegion:1,orderId:1}`**.
- EU/APAC/US zone ranges are configured as shown earlier.
- The app includes **`mongodb-driver-sync`** and **`MONGODB_URI`** pointing to `mongos`.
- The region is resolved from a **trusted backend policy**, never copied blindly from a user header.

### 20.1. Writing a document with the full shard key

~~~java
import com.mongodb.WriteConcern;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import java.util.Map;
import java.util.Set;
import java.util.UUID;

public class ZonedOrderWriteDemo {
    // Demo: replace with a controlled policy service / tenant registry
    // in a real system.
    private static final Map<String, String> TENANT_REGION = Map.of(
            "TENANT-EU-A", "EU",
            "TENANT-AP-A", "APAC",
            "TENANT-US-A", "US"
    );

    private static final Set<String> ALLOWED =
            Set.of("EU", "APAC", "US");

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI is required");
        }

        String tenantId = "TENANT-EU-A";
        String dataRegion = TENANT_REGION.get(tenantId);

        if (dataRegion == null || !ALLOWED.contains(dataRegion)) {
            throw new IllegalArgumentException(
                    "Tenant has no validated data region");
        }

        String orderId = UUID.randomUUID().toString();

        Document order = new Document("dataRegion", dataRegion)
                .append("orderId", orderId)
                .append("tenantId", tenantId)
                .append("status", "CREATED")
                .append("amountCents", 12500L);

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> orders = client
                    .getDatabase("geo_orders")
                    .getCollection("orders")
                    .withWriteConcern(WriteConcern.MAJORITY);

            orders.insertOne(order);
            System.out.println("Created order " + orderId);
        }
    }
}
~~~

Key properties of this code:

1. **`dataRegion`** is resolved from backend-controlled tenant policy.
2. **`orderId`** distinguishes documents within the region.
3. The insert supplies the full shard key.
4. The driver sends the command to `mongos`; `mongos` uses sharding metadata to route.
5. **`WriteConcern.MAJORITY`** governs write acknowledgment durability, not which country the shard sits in.

This snippet creates a new order on each run to demonstrate inserts. In APIs with retries, add a **business `requestId` and idempotency** to avoid duplicates on network drops.

### 20.2. Reading with a filter containing the shard key

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.bson.conversions.Bson;

public class ZonedOrderRead {
    public static Document findOrder(
            MongoCollection<Document> orders,
            String dataRegion,
            String orderId) {

        Bson filter = Filters.and(
                Filters.eq("dataRegion", dataRegion),
                Filters.eq("orderId", orderId)
        );

        return orders.find(filter).first();
    }
}
~~~

The filter spans `dataRegion` and `orderId` matching the shard key pattern, allowing `mongos` to pinpoint the relevant range; never open direct Java connections to `shardEU1` or `shardAP1` to “route manually.”

**Never connect directly to shard replica sets for regular application operations on a sharded collection** to bypass `mongos`. The router manages metadata, routing, migrations, and sharding invariants.

### 20.3. Counting orders by region

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import org.bson.Document;

public class ZonedOrderCount {
    public static long countByRegion(
            MongoCollection<Document> orders,
            String region) {

        return orders.countDocuments(
                Filters.eq("dataRegion", region)
        );
    }
}
~~~

Counting by `dataRegion` can hit multiple shards within that zone if the region splits across multiple ranges. That can still be a valid design: zones define **permitted shard groups**, without forcing every regional query onto one shard.

### 20.4. Explain via Java

~~~java
import com.mongodb.ExplainVerbosity;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import org.bson.Document;

public class ZonedOrderExplain {
    public static Document explainByRegionAndId(
            MongoCollection<Document> orders,
            String region,
            String orderId) {

        return orders.find(
                Filters.and(
                        Filters.eq("dataRegion", region),
                        Filters.eq("orderId", orderId)
                )
        ).explain(ExplainVerbosity.QUERY_PLANNER);
    }
}
~~~

Explain output helps verify shard targeting and index selection. Never cite a single `explain` as sole proof that **all physical copies** live in the approved region.

### 20.5. Updating with a sufficiently specific shard key

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

public class ZonedOrderUpdate {
    public static boolean markPaid(
            MongoCollection<Document> orders,
            String dataRegion,
            String orderId) {

        UpdateResult result = orders.updateOne(
                Filters.and(
                        Filters.eq("dataRegion", dataRegion),
                        Filters.eq("orderId", orderId),
                        Filters.eq("status", "CREATED")
                ),
                Updates.set("status", "PAID")
        );

        return result.getMatchedCount() == 1;
    }
}
~~~

The **`status = CREATED`** condition guards the document update against overwriting changed state. Never allow clients to change **`dataRegion`** during a payment status update.

## 21. Spring Data MongoDB: keeping region in Query and Criteria

In Spring Data MongoDB, **`MongoTemplate`** executes queries with shard-key fields without the application needing to know specific shards.

### 21.1. Querying with `MongoTemplate`

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public class OrderLookupService {
    private final MongoTemplate mongoTemplate;

    public OrderLookupService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public Document findByRegionAndOrderId(
            String dataRegion,
            String orderId) {

        Query query = Query.query(
                Criteria.where("dataRegion").is(dataRegion)
                        .and("orderId").is(orderId)
        );

        return mongoTemplate.findOne(
                query,
                Document.class,
                "orders"
        );
    }
}
~~~

The backend must supply `dataRegion` from trusted tenant policy so callers cannot pick another region to read another tenant’s orders.

### 21.2. Creating documents with a verified region

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;

public class OrderCreationService {
    private final MongoTemplate mongoTemplate;

    public OrderCreationService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public Document create(
            String trustedRegion,
            String tenantId,
            String orderId) {

        Document order = new Document("dataRegion", trustedRegion)
                .append("tenantId", tenantId)
                .append("orderId", orderId)
                .append("status", "CREATED");

        return mongoTemplate.insert(order, "orders");
    }
}
~~~

This illustrates the write operation only. Real systems must validate region, caller permissions, unique keys, idempotency, and write concern, and ensure `MongoTemplate` connects to **`mongos`** on the zone-sharded cluster.

### 21.3. Entity annotations do not configure zones automatically

Even when Spring Data models annotate `dataRegion`/`orderId` and indexes, those annotations **do not create cluster zone memberships or zone ranges**.

Zones belong to **cluster administration** and must be declared and monitored using appropriate MongoDB tooling. Application migrations can coordinate index/sharding setup via DevOps pipelines, rather than letting every API instance invoke `sh.addShardToZone` concurrently on startup.

### 21.4. Avoid APIs trusting arbitrary region parameters

Never blindly trust:

~~~http
GET /orders/O-123?dataRegion=EU
~~~

just because the client passed `"EU"`. In multi-tenant architectures, the service must:

1. Authenticate the caller.
2. Determine tenant/authorization scope.
3. Look up the `tenant → region` mapping or per-document policy.
4. Filter using the verified `dataRegion`.
5. Confirm returned documents belong to the authorized tenant.

**Zone sharding solves placement, not authorization.**

## 22. Cross-shard and cross-zone transactions

MongoDB supports multi-shard transactions in qualifying deployments/versions, yet cross-shard operations are more complex and resource-intensive than single-shard operations.

Suppose a transaction updates both an EU order and a US payment:

~~~text
Transaction
    |
    +-- EU shard: update order
    |
    +-- US shard: insert payment
    |
    +-- coordination / commit
~~~

The system must coordinate across shards and send data over the network. Zone sharding **does not automatically block** an authorized application from running a cross-region transaction.

### 22.1. When to avoid cross-zone transactions?

- When residency rules forbid raw data crossing regional borders.
- When the flow runs at very high frequency needing low latency and minimal contention.
- When one region’s outage would stall the entire transaction.
- When data can be modeled so one business unit resides within a single shard/zone.

Never force all business entities onto one shard if doing so destroys scalability. Balance **atomicity, latency, isolation, data location, and availability**.

### 22.2. How does regional colocation help?

If order, payment, and inventory all share `dataRegion` and queries pass full shard keys, fewer shards participate in operations. However, **same zone does not mean same shard**: `ZONE_EU` can contain multiple shards, and each collection distributes ranges independently.

Therefore, to guarantee two documents live on the same shard for transaction optimization, sharing a zone is **not enough**. Evaluate shard keys, range mappings, and data layout.

## 23. Safe zone sharding deployment workflow

Zone changes affect shard capacity, network latency, availability, and data residency compliance. Production changes require a **runbook with explicit acceptance criteria**, not just a snippet of `mongosh` commands.

### 23.1. Phase 1 — Gather requirements

Determine:

- Which collections require location constraints.
- Which regions exist: EU, APAC, US, or policy-specific zones.
- Whether region is derived by tenant, document, residency, or transaction origin.
- Whether data must stay within **a specific country**, cloud region, or dedicated host group.
- Requirements for **replication, backups, logs, audits, exports, and search indexes**.
- **RPO/RTO** requirements if one region loses connectivity.
- Frequent query patterns and latency SLOs.

Example policy matrix:

| Data class | Region key | Allowed zone | Backup constraint | Query scope |
|---|---|---|---|---|
| EU customer order | `dataRegion=EU` | `ZONE_EU` | Approved region only | Usually EU + tenant |
| APAC customer order | `dataRegion=APAC` | `ZONE_APAC` | Approved region only | Usually APAC + tenant |
| Global aggregate | May be aggregated summaries | Per policy | Verify cross-region aggregation is permitted | May be cross-zone |

This table is a technical example; legal/commercial terms must be verified by authorized governance teams.

### 23.2. Phase 2 — Design the shard key

For `orders`, consider:

~~~javascript
{ dataRegion: 1, tenantId: 1, orderId: 1 }
~~~

Questions to answer:

1. Can zone ranges cover each region accurately?
2. Does each region have enough distinct values to split ranges?
3. Do critical APIs always know `dataRegion`/`tenantId`?
4. Do unique business keys fit the shard key and index rules?
5. Will a large tenant create a hotspot?
6. If a tenant switches regions, how is migration handled?

If the shard key fails these checks, **fixing the design before writing billions of documents** is far easier than changing it later.

### 23.3. Phase 3 — Prepare infrastructure

- Verify shards are deployed in the right physical/cloud regions.
- Verify locations of **every replica set member**.
- Check capacity against projected growth per zone.
- Verify backups/PITR and DR.
- Confirm proper zone admin privileges.
- Confirm balancer/migration observability works.
- Define rollback or halt criteria.

Never assign a shard to a zone based solely on hostname; verify physical storage and replication placement evidence.

### 23.4. Phase 4 — Prepare indexes and zones

For an empty collection, a typical supported workflow:

~~~text
Create/verify shards
        |
        v
Add shard membership to zones
        |
        v
Define non-overlapping zone ranges
        |
        v
Create shard-key index / shard collection
        |
        v
Insert representative test data
        |
        v
Observe chunk/range placement
~~~

For a populated collection, the sequence must account for existing sharding state and balancer migrations. Never copy an empty-collection procedure onto a busy live system without evaluating migrations.

### 23.5. Phase 5 — Block out-of-domain data

Before opening traffic:

- Validator requires `dataRegion` to exist and belong to the allowed enum.
- Backend enforces `tenant/region` mapping.
- Importers, batch jobs, and admin scripts obey the same policy.
- No **`UNKNOWN`**, null, or mistyped region can enter an unzoned range when prohibited.
- A process exists for onboarding future region codes.

Fixing only the main API is insufficient if background workers or importers can still insert non-compliant documents.

### 23.6. Phase 6 — Monitor placement convergence

After configuration:

1. Check zone membership.
2. Check namespace zone ranges.
3. Verify range ownership across shards.
4. Confirm the balancer is active with no migration errors.
5. Monitor shard capacity and network I/O.
6. Wait for cleanup of residual donor data after migrations.
7. Verify snapshots/backups and secondary pipelines.

Until convergence completes, report only **“zone policy declared”**, never **“all data has finished moving.”**

### 23.7. Phase 7 — Test application paths

Run representative queries:

~~~javascript
db.orders.find({
  dataRegion: "EU",
  tenantId: "TENANT-EU-A",
  orderId: "EU-001"
}).explain("queryPlanner");
~~~

And a prefix-less query:

~~~javascript
db.orders.find({
  orderId: "EU-001"
}).explain("queryPlanner");
~~~

Compare targeted shard scope, latency, index plans, and returned volume. A compliant residency layout that forces every API to scatter-gather may still miss operational SLOs.

### 23.8. Phase 8 — Acceptance and ongoing monitoring

Do not check only once at launch. Continuously monitor:

- Unauthorized shards added to or removed from zones.
- Overlapping or missing zone ranges.
- Zone shards being decommissioned or running low on capacity.
- Newly created collections missing zone configurations.
- Records carrying unapproved region codes.
- Changes in backup/replica placement after failover or DR.

A strong acceptance runbook specifies **who owns each check**, which evidence is archived, and what triggers a rollout halt.

## 24. Observability, monitoring, and alerting

A zone-sharded system needs placement-specific metrics and alerts, not only CPU and latency.

### 24.1. Useful metrics

| Metric / observation | Purpose |
|---|---|
| Zone membership snapshot | Detects shards added/removed outside policy |
| Zone range snapshot | Detects gaps, overlaps, or unconfigured namespaces |
| Non-compliant range placement | Flags ranges sitting on shards outside their required zone |
| Balancer status/history | Detects stopped, failing, or stalled balancing |
| Migration duration/failures | Measures transfer cost and errors |
| Per-zone disk usage | Alerts before a zone runs out of storage |
| Per-shard write/read latency | Spots hot shards |
| Scatter-gather query ratio | Spots APIs omitting the shard-key prefix |
| Unknown/invalid `dataRegion` count | Detects data outside defined domains |
| New namespaces without zone policy | Spots new collections lacking residency config |
| Backup/replica location inventory | Provides evidence of where copies reside |

These names are **recommended observability signals**, not literal built-in metric names emitted identically by every MongoDB deployment.

### 24.2. Alert when a zone’s shards near capacity

Example organization-defined threshold alert:

~~~text
ZONE_EU:
  shardEU1 disk utilization > threshold
  shardEU2 disk utilization > threshold

Action:
  - Inspect growth and workload
  - Expand capacity inside approved region
  - Check shard key / hotspots
  - Never spill EU onto a US shard
~~~

Exact thresholds depend on storage setup, migration headroom, write rate, and infrastructure expansion lead time.

### 24.3. Alert when a `dataRegion` is uncovered

Suppose telemetry sees `dataRegion = "LATAM"`, yet the cluster only defines EU/APAC/US zones. Treat this as a signal to act before persisting sensitive data:

~~~text
Invalid / unapproved region value
           |
           v
Reject or quarantine by policy
           |
           v
Review tenant-region mapping
           |
           v
Provision new zone if authorized
~~~

Never default unknown region codes to `ZONE_US` simply because it has spare capacity.

### 24.4. Audit log of zone configuration changes

For every change, record:

- Operator/automation and approver.
- Namespace and zone name.
- Before/after shard membership.
- Before/after range bounds.
- Timestamp of change.
- Balancer/migration state at sign-off.
- Link to replica, backup, and region inventory report.

Auditing zone changes supports root-cause investigations if data ever appears in an unexpected place.

## 25. Common troubleshooting scenarios

### 25.1. Zone created yet EU documents remain on an APAC shard

Possible causes:

- `sh.updateZoneKeyRange` was not run on the exact namespace.
- EU ranges existed before the zone; balancer has not finished migrating.
- Balancer is disabled or migrations are failing.
- The APAC shard was accidentally also added to `ZONE_EU`.
- Metadata and shard IDs were misread.

**Investigation:** verify membership, range mappings, balancer status, current range owners, and migration history. Never manually run `deleteMany` on a donor shard.

### 25.2. New records with `"EU "` leak into another zone

Cause: trailing whitespace differs from `"EU"` and falls outside expected bounds. Fix: normalize and validate at both the API and schema layers. Never widen zone ranges loosely to sweep up typos.

### 25.3. `orderId` queries slow down after enabling sharding

If the shard key starts with `dataRegion` and the API queries only by `orderId`, `mongos` must query multiple shards. Update the API contract to pass region, add an appropriate mapping service, or revisit the shard key.

**Do not blame zone sharding** when the actual issue is queries omitting the shard-key prefix.

### 25.4. Zone EU is full while US has spare space

This is an expected consequence of zone partitioning, not necessarily a broken balancer. The balancer must not violate EU constraints just to “even out the cluster.” Add capacity to `ZONE_EU` or manage workload within approved bounds.

### 25.5. New collection holds EU data without a zone

For example, a team creates **`geo_orders.orderAuditEvents`** and shards it on `createdAt` without region. New collections do not inherit `orders`’ zone ranges automatically. Standardize collection creation and namespace audits rather than checking only the primary collection.

### 25.6. Migration completed yet old backups remain in another region

New zone placement does not erase historical snapshots. This is a retention/backup/compliance process issue. Never delete backups impulsively if recovery or legal retention policies require keeping them.

### 25.7. Zone has multiple shards yet documents are uneven

Causes include low shard key distinctness, data skew, unsplit ranges, pending balancer work, or capacity limits. Check per-shard stats, `explain`, and metrics rather than assuming adding a zone label balances skew.

### 25.8. After changing `homeRegion`, tenant data lingers in the old region

Updating a single tenant config field does not automatically migrate existing collections or backups. Run an inventoried migration covering historical scope, range ownership verification, and active read/write cutover.

### 25.9. Cross-zone transactions see higher latency

A workflow updating records across multiple regions triggers cross-shard/cross-region communication. Review business logic, shard key filters, transaction boundaries, and service placement. Never assume “same zone name = same shard.”

### 25.10. Cannot add the desired unique index

On sharded collections, unique indexes are constrained by the shard key and existing data state. An index on `orderId` alone may be invalid for cluster-wide uniqueness under the active shard key. Revisit the business ID model and migration plan rather than dropping the constraint and relying on check-before-insert.

## 26. Zone sharding vs. separate clusters per region?

Zone sharding is powerful, yet not the only partitioning architecture. When locality constraints are strict, compare alternatives.

| Criterion | One multi-zone sharded cluster | Separate clusters per region |
|---|---|---|
| MongoDB clusters | One logical cluster, multiple shards/zones | Multiple independent clusters |
| Metadata/routers | Shared cluster control components | Each cluster has its own control plane/metadata |
| Placement by shard key | Zone ranges and balancer | Application routes to the matching cluster |
| Risk of cross-region queries | Exists if queries touch multiple shards/zones | Requires app-layer coordination for cross-region queries |
| Operational isolation | Some resources and changes are shared | Stronger isolation per cluster |
| Cross-region transactions | Supported sharded transactions under rules, with high cost | No simple MongoDB transaction across independent clusters |
| Strict residency | Must audit all replicas/backups/metadata/processes | Must audit every component per cluster, though scope is clearer |
| Regional scaling | Adding shards to a zone scales capacity | Scale each cluster independently |
| Application management | Single cluster connection; shard key matters | Multiple connections, routing, and ownership are harder |
| Blast radius | Some control-plane changes affect multiple zones | Smaller blast radius per cluster, more clusters to operate |

**No single choice fits every system.** A multi-zone cluster works well when regions can share a common sharding plane under approved policy. Separate clusters fit better when strict operational/security boundaries prohibit shared metadata or control planes.

### 26.1. Zone sharding for hot/cold resource tiers

Zones are not strictly geographic. You can place ranges by **time, tenant tier, or workload type** onto shard groups with distinct hardware profiles, given a compatible shard key.

Example:

~~~text
ZONE_HOT:
  Shards with storage/CPU sized for active workload

ZONE_ARCHIVE:
  Shards serving older, infrequently accessed data
~~~

However, if zoning by `createdAt` and documents age from “hot” to “archive,” understand how range placement and updates interact; simply changing zone tags will not rearrange everything instantaneously.

### 26.2. Do not confuse zones with latency-based read preferences

Read preference picks **a replica node** for reads within an already targeted shard, not the shard key or range owner. Even with **`readPreference: nearest`**, `mongos` must still route queries to shards owning the matching ranges.

If EU data is zone-sharded to the EU while the primary application runs in APAC, network latency remains. Zones do not route end users to a closer frontend deployment.

### 26.3. Decision matrix

Choose zone sharding when:

- Regions may share one sharded cluster under approved policy.
- The shard key can express the required locality attribute.
- Load within a region needs scaling across multiple shards.
- Admins can control placement, replication, backups, and migrations per zone.
- Applications routinely supply the shard-key prefix in queries.

Consider separate clusters when:

- Strict separation of control plane/metadata or operations is mandatory.
- Policy forbids sharing any data/backup/log components across regions.
- Regions have independent upgrade cycles, versions, or operational teams.
- Most queries are intra-region and can route at the application layer.
- Multi-cluster routing overhead is acceptable.

You can also combine both: dedicated clusters for strict regions, with sharding and zones inside each cluster for specialized workloads.

## 27. Common design mistakes

| Mistake | Consequence | How to avoid |
|---|---|---|
| Labeling an out-of-EU shard `ZONE_EU` | Violates real geographic constraints | Audit physical infra and replica placement |
| Configuring membership without binding ranges | Zone governs no shard key values yet | Run `sh.updateZoneKeyRange` per namespace |
| Binding ranges without eligible shards | Balancer has nowhere valid to place ranges | Provision zone members and capacity first |
| Putting one shard in both EU and US when isolation is required | Shard may hold both datasets | Audit memberships against isolation policy |
| Choosing a shard key omitting region when regional zoning is needed | Cannot express contiguous regional ranges | Design shard-key prefix for requirements |
| Using `{region:1}` alone with few values | Low cardinality, hard to spread load | Consider compound key with `orderId`/`tenantId` |
| Defining zone range min/max out of order | Config error or wrong range | Supply full shard-key fields and valid sentinels |
| Overlapping two zone ranges | Conflicting placement | Design strictly non-overlapping intervals |
| Forgetting `[min, max)` half-open bounds | Record at `max` falls outside range | Use exact bounds and test boundary values |
| Allowing `UNKNOWN`/null regions | Data lands in unzoned ranges | Enforce schema validation and policy mapping |
| Trusting client-supplied region | Clients can pick non-compliant regions | Resolve from trusted policy and authorize |
| Assuming zone command success means moves finished | Residency has not converged yet | Monitor balancer and actual placement |
| Stopping balancer and expecting automatic moves | Ranges stay on old shards | Operate balancer per procedure |
| Checking only primary location | Secondaries may replicate outside the region | Inventory all replica members |
| Forgetting backups/exports | Copies persist outside allowed region | Govern the entire data lifecycle |
| Assuming same zone equals same shard | Transactions/queries can still cross shards | Design explicit shard keys and ranges |
| Querying by `orderId` alone | `mongos` may scatter-gather | Pass shard-key prefix or maintain mapping |
| Adding US shards to relieve full EU disk | Can violate residency | Scale capacity within allowed zone |
| Removing the last shard from a zone | Leaves ranges without valid placement | Provision replacement first |
| Changing `homeRegion` with a casual update | Old data, backups, other collections stay behind | Run a controlled migration |
| Unique index lacking shard-key prefix | Fails to enforce desired uniqueness | Design indexes alongside the shard key |
| Opening API for a new region before configuring zones | Window of unzoned data | Roll out infra/zones/schema before app |
| Using zones as sole legal compliance proof | Misses everything outside the sharded collection | Audit replication, logs, backups, and processing |

## 28. Hands-on exercises and scenario questions

Exercises assume a **test** cluster with sufficient shards and `mongos`. Only run zone/range modifications with admin privileges on known test namespaces. If you only have a standalone `mongod`, complete the diagram and syntax analysis without executing cluster commands.

### Exercise 1. Identify the three parts of zone sharding

Suppose:

~~~text
shardEU1, shardEU2 -> ZONE_EU
shardAP1           -> ZONE_APAC

EU shard-key range   -> ZONE_EU
APAC shard-key range -> ZONE_APAC
~~~

**Question:** What defines shard membership, what defines range-to-zone, and what drives placement convergence?

**Guided answer:** `sh.addShardToZone` binds shards to zones; `sh.updateZoneKeyRange` binds ranges to zones; the balancer coordinates ownership/range migrations per constraints—not as one single atomic step.

### Exercise 2. Write commands to add shards to a zone

Given shards named **`shardEU1`** and **`shardEU2`**, add both to `ZONE_EU`.

~~~javascript
sh.addShardToZone("shardEU1", "ZONE_EU");
sh.addShardToZone("shardEU2", "ZONE_EU");
~~~

**Question:** Do these commands verify the shards are in Frankfurt? Do they bind the `orders` collection to the zone?

**Answer:** No. Infrastructure placement must be verified separately, and zone ranges must be declared for the relevant namespace.

### Exercise 3. Create a zone range for a compound shard key

Collection **`geo_orders.orders`** has shard key:

~~~javascript
{ dataRegion: 1, orderId: 1 }
~~~

Declare the EU range covering all valid String `orderId` values.

~~~javascript
sh.updateZoneKeyRange(
  "geo_orders.orders",
  { dataRegion: "EU", orderId: MinKey() },
  { dataRegion: "EU", orderId: MaxKey() },
  "ZONE_EU"
);
~~~

**Explanation:** `MinKey` and `MaxKey` act as sentinels spanning the entire String `orderId` domain. Since the upper bound is exclusive, schema validation should restrict `orderId` so no document stores `MaxKey` as a literal value.

### Exercise 4. Half-open bounds of a zone range

Single-field shard key:

~~~javascript
{ score: 1 }
~~~

Zone range:

~~~text
[score=10, score=20)
~~~

**Question:** Are `score=10`, `score=19`, `score=20`, and `score=9` inside the range?

**Answer:** `10` and `19` are inside; `20` and `9` are outside. If `score=20` must belong to the same zone, adjust the upper bound rather than assuming `max` is inclusive.

### Exercise 5. Spot the flaw in a shard key design

Requirement: data with `country="EU"` must stay in the EU zone.

Design:

~~~javascript
{ orderId: "hashed" }
~~~

And `country` is stored in documents only, outside the shard key.

**Question:** Why is it hard to express the country-based zone rule?

**Guided answer:** Zone ranges operate in the shard key space. With pure hashed `orderId`, EU documents scatter across the hash space; `country` does not form a contiguous shard key interval. Revise the shard key/model or storage architecture.

### Exercise 6. Which query targets best?

Given shard key:

~~~javascript
{ dataRegion: 1, orderId: 1 }
~~~

Three queries:

~~~javascript
// A
db.orders.find({ dataRegion: "EU", orderId: "EU-001" });

// B
db.orders.find({ dataRegion: "EU" });

// C
db.orders.find({ orderId: "EU-001" });
~~~

**Question:** Which query supplies the full shard key, which uses the prefix, and which lacks the prefix?

**Answer:** A supplies the full key; B supplies the region prefix and targets EU ranges; C lacks the prefix and risks scatter-gather. B may still read multiple EU shards if the zone has multiple shards.

### Exercise 7. Distinguish configuration from placement

An admin creates `ZONE_EU` and `sh.updateZoneKeyRange` succeeds, yet an EU range still sits on `shardAP1`.

**Question:** Can you declare EU migration finished? What must you check?

**Guided answer:** Not yet. Inspect zone membership, range metadata, balancer state, migration errors, and current shard ownership; then check residual data/backups if residency applies.

### Exercise 8. One shard in two zones

~~~text
shardShared:
  ZONE_EU
  ZONE_APAC
~~~

**Question:** Is this suitable if EU data must never reside on any shard holding APAC data?

**Guided answer:** Unsuitable for that isolation goal, because `shardShared` can own ranges from both zones. Revise membership and separate shard groups.

### Exercise 9. Unzoned range

A collection defines zone ranges for EU, APAC, and US. An application inserts:

~~~javascript
{
  dataRegion: "LATAM",
  orderId: "LA-001"
}
~~~

**Question:** Which zone constrains LATAM data? How do you prevent non-compliant placement?

**Guided answer:** No LATAM zone is defined, so it is not pinned to any fixed zone. Enforce a policy/validator rejection or provision `ZONE_LATAM` before ingesting data.

### Exercise 10. Replica set spanning regions

`ShardEU1` has:

~~~text
Primary: Frankfurt
Secondary A: Frankfurt
Secondary B: Singapore
~~~

**Question:** If policy forbids any EU data copy outside the EU, is zone sharding sufficient?

**Answer:** No. The replica set replicates shard data to every data-bearing member. Adjust replica placement plus all backups/DR accordingly.

### Exercise 11. One region runs out of disk

Both shards in `ZONE_EU` are nearly full, while `ZONE_US` has plenty of free space.

**Question:** Should you add `shardUS1` to `ZONE_EU` just to give the balancer more capacity?

**Guided answer:** Only if policy genuinely permits EU data on `shardUS1`; if residency forbids it, no. Expand capacity inside the permitted region or add compliant EU shards.

### Exercise 12. Globally unique `orderId`

A system requires `orderId` to be unique cluster-wide. Current shard key and unique index:

~~~javascript
{ dataRegion: 1, orderId: 1 }
~~~

**Question:** Do `("EU","O-123")` and `("US","O-123")` violate pair uniqueness? What is needed if `O-123` must be globally unique?

**Answer:** They do not violate pair uniqueness because `dataRegion` differs. You need an ID generator/business registry guaranteeing global uniqueness or a redesigned constraint/shard key.

### Exercise 13. Opening a new region

The product team wants to enable **`dataRegion="LATAM"`** next week. Write a safe rollout plan.

**A sound answer includes:**

1. Verify compliant infrastructure and replication/backups for LATAM.
2. Provision/verify shards in that region.
3. Add shards to `ZONE_LATAM`.
4. Declare LATAM zone ranges for every required namespace.
5. Verify metadata and placement.
6. Add LATAM to validators and tenant policies.
7. Enable app traffic and monitor new records and alerts.

Never ship an API accepting LATAM before zones are configured if unzoned placement is forbidden.

### Exercise 14. Tenant changes home region

Tenant `T-1` moves from APAC to EU, with millions of historical orders and backups.

**Question:** Why is merely updating `T-1`’s config to EU insufficient? List migration components to address.

**Guided answer:** Historical records retain old shard key/range values; plan whether history moves or stays per policy, check transactions, mappings/unique keys, concurrent read/write flows, balancer, and backup retention. Never mutate shard keys across millions of documents casually.

### Exercise 15. Comparing zone sharding vs. separate clusters

A customer mandates complete isolation of data, metadata, backups, and operations within one legal jurisdiction from other regions.

**Question:** Why might a shared cluster with zones fall short? When should separate clusters be considered?

**Guided answer:** Zones primarily constrain range placement; the cluster still shares metadata, routers, and operational control planes. When broader isolation is mandated, separate clusters fit better—though every replica, backup, log, export, and access path of each cluster must still be audited.

### Exercise 16. Reading explain output

Two queries:

~~~javascript
db.orders.find({
  dataRegion: "EU",
  orderId: "EU-001"
}).explain("queryPlanner");

db.orders.find({
  orderId: "EU-001"
}).explain("queryPlanner");
~~~

**Task:** Record participating shards, indexes used, and range scope for each query. Explain why the second query can be far costlier despite looking up the same `orderId`.

**Guided answer:** The first supplies the full shard key and can target narrowly; the second omits `dataRegion` and may scatter-gather. Exact figures come from live `explain` output rather than assuming fixed shard counts.

## 29. Zone sharding command cheat sheet

The entries below are a **syntax reference**. In production, substitute real namespace/shard/zone names and follow approved change control.

| Purpose | Command / concept |
|---|---|
| Inspect sharded cluster | `sh.status()` |
| List shards | `db.adminCommand({listShards:1})` |
| Add shard to zone | `sh.addShardToZone(shardName, zoneName)` |
| Remove shard from zone | `sh.removeShardFromZone(shardName, zoneName)` |
| Bind range to zone | `sh.updateZoneKeyRange(namespace, min, max, zoneName)` |
| Remove range from zone | `sh.removeRangeFromZone(namespace, min, max)` |
| Inspect zone metadata | `config.tags` (read via `config` database) |
| Inspect membership metadata | `config.shards` (read via `config` database) |
| Inspect balancer status | `sh.getBalancerState()`, `sh.isBalancerRunning()` |
| Inspect collection distribution | `getShardDistribution()` when supported by shell/server |
| Inspect query shard targeting | `explain("queryPlanner")` |
| Shard a collection | `sh.shardCollection(namespace, shardKey)` |
| Block invalid/out-of-enum regions | `$jsonSchema` validator + policy checks |

### 29.1. Compact sample configuration

Assuming the shards below already exist in a test cluster and the collection uses shard key **`dataRegion + orderId`**:

~~~javascript
// 1. Shard membership
sh.addShardToZone("shardEU1", "ZONE_EU");
sh.addShardToZone("shardEU2", "ZONE_EU");
sh.addShardToZone("shardAP1", "ZONE_APAC");
sh.addShardToZone("shardUS1", "ZONE_US");

// 2. Namespace-specific zone ranges
sh.updateZoneKeyRange(
  "geo_orders.orders",
  { dataRegion: "EU", orderId: MinKey() },
  { dataRegion: "EU", orderId: MaxKey() },
  "ZONE_EU"
);

sh.updateZoneKeyRange(
  "geo_orders.orders",
  { dataRegion: "APAC", orderId: MinKey() },
  { dataRegion: "APAC", orderId: MaxKey() },
  "ZONE_APAC"
);

sh.updateZoneKeyRange(
  "geo_orders.orders",
  { dataRegion: "US", orderId: MinKey() },
  { dataRegion: "US", orderId: MaxKey() },
  "ZONE_US"
);

// 3. Observe configuration
sh.status();

db.getSiblingDB("config").tags.find({
  ns: "geo_orders.orders"
});
~~~

**Do not treat the snippet above as a complete bootstrap script**: it assumes shard membership, cluster topology, collection shard key/index, and admin privileges are already prepared per earlier steps. For production compliance, verify balancer convergence and audit replicas, backups, and metadata.

### 29.2. Three-layer model to remember

~~~text
Layer 1 — Business policy
  Which region does a tenant/document belong to?
  Who is authorized to decide the region?
                  |
                  v
Layer 2 — MongoDB zone placement
  shard key includes region field
  region range -> zone
  zone -> permitted shards
  balancer -> converged ownership
                  |
                  v
Layer 3 — Physical and operational controls
  replica set members
  storage, backups, logs
  exports, disaster recovery
  auth/audit, migrations
~~~

If any of the three layers is broken, having a “declared zone” is not enough to claim data locality compliance.

## 30. Conclusion

**Zone sharding** lets MongoDB govern where shard key ranges live inside a sharded cluster. Instead of letting every range scatter indiscriminately across all shards, administrators can enforce rules such as:

~~~text
{ dataRegion: "EU", orderId: ... }
    -> ZONE_EU
    -> shardEU1 / shardEU2

{ dataRegion: "APAC", orderId: ... }
    -> ZONE_APAC
    -> shardAP1 / shardAP2
~~~

Yet this feature must be understood through **six principles**:

1. **Zones are placement constraints for shard-key ranges.** They neither create shards nor verify physical machine locations.
2. **The shard key must express the target data groups.** For regional residency, region typically leads as a prefix; fields outside the shard key cannot form contiguous zone ranges.
3. **Shard membership and zone ranges are separate configurations**, while the balancer drives convergence toward compliant placement. Command success does not mean migrations finished instantly.
4. **Unzoned ranges still need policy.** Null, mistyped, inconsistent, or newly introduced region codes can break residency if the application fails to validate.
5. **Zone sharding does not replace replication, backups, routing, authorization, or compliance audits.** Protecting data location requires governing the entire lifecycle and all copies.
6. **Scalability and latency still require design.** Multiple shards can share one zone, queries omitting the shard-key prefix scatter-gather, and spare capacity in one zone cannot automatically rescue a full zone.

By combining a sound shard key, non-overlapping zone ranges, accurate shard membership, balancer monitoring, schema validation, tenant-region policies, and infrastructure controls, zone sharding becomes a powerful tool to **keep data within permitted shard groups per policy** while retaining MongoDB’s horizontal scalability.

Ultimately, verify not only **“which zones were declared?”**, but **“right now and across the full data lifecycle, where can these records physically reside, where are they replicated, and who is permitted to move them across boundaries?”**.
