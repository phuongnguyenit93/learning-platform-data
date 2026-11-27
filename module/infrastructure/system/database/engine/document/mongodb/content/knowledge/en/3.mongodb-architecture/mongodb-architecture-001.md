# Roles of mongod, mongos, and Config Servers in MongoDB Architecture

When using MongoDB on a single machine, an application typically connects to a single **mongod** process to read and write data. When a system requires high availability, multiple **mongod** processes can be organized into a **replica set**. When distributing a dataset across multiple groups of machines is needed, MongoDB uses **sharding**: the **mongos** process routes requests, the **mongod** processes of the shards store the data, and **config servers** maintain metadata so the entire cluster knows where the data resides.

These three names represent different roles, not three independent types of databases. In particular, a **config server still runs using the mongod process**, with a specialized configuration role; **mongos** is a routing process distinct from **mongod**.

## 1. Starting from the Three Deployment Models

MongoDB architecture is typically approached at three levels:

| Deployment Model | Core Components | Primary Goal |
| --- | --- | --- |
| **Standalone** | One mongod | Learning, experimentation, or simple requirements |
| **Replica set** | Multiple mongod processes holding copies of a dataset | Redundancy, primary election, recovery when a member fails |
| **Sharded cluster** | Shards consisting of mongod, one or more mongos, and a config server replica set | Distributing data and processing load across multiple shards |

Simplified diagram:

~~~text
Standalone
Application ──> mongod ──> data

Replica set
                        ┌──> mongod PRIMARY
Application / driver ───┤
                        ├──> mongod SECONDARY
                        └──> mongod SECONDARY

Sharded cluster
                           ┌──> Shard A: replica set mongod
Application ──> mongos ────┤
                           └──> Shard B: replica set mongod
                               ▲
mongos <── metadata ── Config Server Replica Set (mongod)
~~~

The purpose of this diagram is to distinguish between the **request path** and **where data is stored**. In a replica set, the mongod instances hold copies of the same dataset. In a sharded cluster, different shards can hold different portions of the data; within each shard, a replica set replicates that portion of data for redundancy.

**Replication** and **sharding** solve two separate problems: replication increases the fault tolerance of a dataset; sharding distributes data to increase horizontal scalability. A production sharded cluster typically uses both.

## 2. mongod: The Database Process That Actually Processes and Stores Data

**mongod** is the MongoDB server process. It is the component that receives database operations, executes queries, manages collections/indexes, and coordinates with the storage engine to store data on disk.

A mongod typically handles:

- Managing the databases, collections, documents, and indexes assigned to that process.
- Executing read, write, update, delete, and portions of aggregation processing.
- Using a storage engine, commonly **WiredTiger**, to manage data, cache, and storage mechanisms.
- Coordinating with the journal, checkpoints, and data durability mechanisms according to configuration.
- Participating in replication and elections if it is a member of a replica set.
- Serving a portion of distributed data if configured as a member of a shard.

In a standalone deployment, mongod is both the connection point and the query execution engine. In a replica set, the driver knows the mongod members of the cluster; normal write requests are sent to the **primary**, while where reads are executed depends on the **read preference** and availability.

### 2.1. mongod in a Replica Set

Consider an example replica set **rsBooks** consisting of three processes:

~~~text
Replica set rsBooks
├── mongod books-db-1  PRIMARY
├── mongod books-db-2  SECONDARY
└── mongod books-db-3  SECONDARY
~~~

The primary receives normal write operations; secondaries replay changes through the replication mechanism. When the primary fails, eligible members can elect a new primary if the replica set still meets election requirements.

It is important to distinguish **primary/secondary** from **mongod/mongos**:

- **mongod** is a process type.
- **primary** and **secondary** are roles of a member in a replica set at a given point in time.
- A mongod can transition from secondary to primary after an election; the process itself remains mongod.
- mongos does not become a primary or secondary of a replica set.

A replica set does not create multiple shards on its own. The entire group still manages **a single logical dataset**.

### 2.2. mongod in a Shard

A **shard** is a unit that holds a portion of a sharded cluster's data. In modern deployment models, a shard is organized as a replica set. For example:

~~~text
Shard A = rsShardA
  ├── mongod A1 PRIMARY
  ├── mongod A2 SECONDARY
  └── mongod A3 SECONDARY

Shard B = rsShardB
  ├── mongod B1 PRIMARY
  ├── mongod B2 SECONDARY
  └── mongod B3 SECONDARY
~~~

If a collection is sharded, its documents can be distributed between Shard A and Shard B according to the **shard key** and partitioning metadata.

Two shards are not two identical copies. On the contrary, **A1/A2/A3** replicate the portion of data owned by Shard A; **B1/B2/B3** replicate the portion of data owned by Shard B.

When a shard receives a request from mongos, the mongod belonging to the shard actually reads indexes, accesses data, and executes the assigned part of the query. mongos does not replace the storage engine or query execution engine of mongod.

### 2.3. Commonly Confused Terms

| Term | Meaning |
| --- | --- |
| mongod | Database server process |
| Replica set | Group of mongod instances replicating a single dataset |
| Primary | Replica set member that receives normal write operations |
| Secondary | Member that synchronizes a copy of data via replication |
| Shard | Unit storing a portion of a sharded cluster's data, usually an entire replica set |
| mongos | Process that routes requests to shards |
| Config server | A mongod role dedicated to holding metadata for a sharded cluster; may also serve as a shard in supported configurations |

## 3. mongos: Entry Point and Router of a Sharded Cluster

**mongos** (MongoDB Query Router) is the process that provides the logical access interface of the **entire sharded cluster** to applications.

Instead of the application knowing which machine a collection lives on, the application connects to one or more mongos instances. The router identifies the relevant shards, forwards requests, gathers results when needed, and returns the results to the client.

~~~text
            Request: find order ORD-1001
Application -----------------------------------> mongos
                                                   |
                                                   | Check shard metadata
                                                   v
                                          Select target shard
                                                   |
                                                   v
                                                Shard B
                                                   |
                                                   v
Application <----------------------------------- result
~~~

The main responsibilities of mongos include:

1. Receiving requests from applications over the MongoDB wire protocol.
2. Using data distribution metadata to decide which shards need to process the request.
3. Sending requests to the relevant shards and applying appropriate replica set member selection.
4. Combining results when a request involves multiple shards.
5. Returning results to the application, making the sharded cluster appear as a single logical database system.

**mongos does not durably store business documents.** It caches routing information and multiple instances can be run to increase availability. Caching metadata does not turn mongos into a primary data store.

### 3.1. Routing by Shard Key

Suppose the **shop.orders** collection is partitioned based on the **customerId** shard key. To illustrate, assume metadata describes three value ranges:

~~~text
customerId < 1000          -> Shard A
1000 <= customerId < 2000  -> Shard B
customerId >= 2000         -> Shard C
~~~

This is an **illustrative example of range sharding**, not MongoDB's default partitioning rule.

When the application sends:

~~~javascript
db.orders.find({ customerId: 1450 });
~~~

mongos can use the shard key and metadata to direct the query to Shard B. This is a **targeted query**: only the necessary shards are queried.

Conversely:

~~~javascript
db.orders.find({ status: "PAID" });
~~~

If the condition does not allow identifying the shard containing matching documents, mongos may have to send the request to multiple or all shards. This is the **scatter/gather** or **broadcast query** pattern.

| Query Type | Typical Path | Consequence |
| --- | --- | --- |
| Has shard key condition sufficient to narrow scope | One or a small subset of shards | Reduces the number of places to query |
| Cannot determine target shard | Multiple or all shards | Increases distributed work, may increase latency |
| Multi-shard sort/aggregation query | Shards execute their parts, results are merged where appropriate | Adds coordination and merging overhead |

Having a shard key does not guarantee touching only one shard: efficiency also depends on the shard key type, query expression, and how data is currently distributed. With **hashed sharding**, range queries on the original value also have different routing characteristics compared to range sharding.

### 3.2. Where Does mongos Get Data Locations?

mongos retrieves partitioning metadata from **config servers** and caches the parts it needs. For example, metadata indicates:

- Which collections are sharded and which shard keys they use.
- Which ranges or units of data belong to which shards.
- Which shards are currently participating in the cluster.
- Which metadata has changed after data redistribution operations.

When topology or data placement changes, mongos needs to refresh its routing information. Therefore, saying "mongos knows where every document lives" is only a simplification: normally it routes using **metadata about collections, shard keys, and data ranges**, rather than maintaining an individual list for every document.

### 3.3. One or Multiple mongos?

Multiple mongos instances can be run to avoid depending on a single router:

~~~text
                        ┌──> mongos-1 ──┐
Application / driver ───┤               ├──> Shards
                        └──> mongos-2 ──┘
~~~

mongos instances do not need to form a replica set and do not elect a shared primary. They can all access the metadata of the same sharded cluster; drivers or the connection layer can use multiple configured routers.

mongos is a critical service entry point. If all routers that an application can use become unreachable, the application cannot continue communicating with the cluster through that connection path, even if the data on the shards remains intact.

### 3.4. Do Not Access Shards Directly Instead of mongos

Connecting directly to a shard's mongod can serve certain specialized administrative operations, but it is **not the normal business access path** in a sharded cluster.

A direct connection may see only **a portion** of a sharded collection's data, while bypassing the cluster-wide routing and coordination mechanisms. For applications, connect through mongos when working with a sharded cluster.

## 4. Config Server: Where the Map and State of the Sharded Cluster Are Stored

**Config server** is the component that manages **cluster metadata**: information describing the topology, how data is distributed, and the configurations required for components to coordinate with one another.

A config server **is not a completely separate binary** like mongos. It runs using **mongod** configured with the **config server** role. Multiple config servers are grouped into a **Config Server Replica Set (CSRS)**.

For example:

~~~text
Config Server Replica Set: cfgRS
├── cfg-1: mongod (PRIMARY, config server role)
├── cfg-2: mongod (SECONDARY, config server role)
└── cfg-3: mongod (SECONDARY, config server role)
~~~

In the **dedicated config server** model, this group is dedicated to cluster metadata and coordination tasks; business data resides on separate shards.

### 4.1. What Does Metadata Include?

Config servers store information such as:

- The list of shards in the cluster.
- Information about databases and collections participating in the cluster.
- Sharding configuration, shard keys, and related metadata.
- Metadata about ranges/chunks and the shards currently owning the data.
- History or state required for certain administrative and partition coordination operations.
- Other cluster configurations, including information for authentication and authorization in self-managed deployments.

Conceptual example:

~~~text
Collection: shop.orders
Shard key:  { customerId: 1 }

Metadata:
  Range 1 -> shardA
  Range 2 -> shardB
  Range 3 -> shardC
~~~

When a data range is moved from one shard to another, metadata must be updated so mongos knows where to route subsequent requests.

In MongoDB, cluster metadata is stored in collections belonging to the **config database** on config servers. This is sensitive system data; **do not manually modify, delete, or insert documents directly** into these metadata collections.

### 4.2. Why Must Config Servers Be a Replica Set?

If metadata is lost or unavailable, components can hardly coordinate data across the cluster. Therefore, MongoDB deploys config servers as a **replica set**, typically with **three members** in production environments to maintain a majority if one member fails.

Critical metadata changes must be written and acknowledged with appropriate consensus mechanisms. When the CSRS loses its primary and cannot elect a new primary, metadata becomes **unwritable**; operations requiring metadata changes such as moving or splitting ranges/chunks may pause. Some data operations on shards may still work depending on cluster state; if all config servers become unavailable, the cluster risks being unable to operate normally.

The key point is that **config servers ensure metadata remains consistent and available**, rather than directly replacing mongos to route every query.

### 4.3. Dedicated Config Server vs. Config Shard Starting in MongoDB 8.0

Starting in **MongoDB 8.0**, the architecture supports **config shards**: a replica set can serve **both** as the config server **and** as a shard storing application data.

| Layout | Role | Characteristics |
| --- | --- | --- |
| **Dedicated config server** | Replica set dedicated to holding cluster metadata | Separates metadata from business data |
| **Config shard** | Replica set holding metadata while also acting as a shard | Can reduce the number of replica sets/nodes to operate |

This avoids an oversimplified claim that "config servers never store application data." In the **dedicated model**, they are not used to store business data. In the supported **config shard model**, the same mongod instances can store both metadata and application data.

Regardless of the choice, the cluster still requires the config server role and routing information must still be managed consistently. Do not attempt to manually turn a dedicated config server into a shard by manipulating data; mode transitions use administrative mechanisms supported by MongoDB.

## 5. Overall Architecture: How the Three Components Work Together

Example sharded cluster architecture with two routers, two shard replica sets, and a dedicated CSRS:

~~~text
                  +-----------------------+
                  |      APPLICATION      |
                  |  Java / Node / Python |
                  +-----------+-----------+
                              |
                     MongoDB driver
                              |
                 +------------+------------+
                 |                         |
           +-----v-----+             +-----v-----+
           | mongos A  |             | mongos B  |
           | Router    |             | Router    |
           +-----+-----+             +-----+-----+
                 |                         |
                 +-------------+-----------+
                               |
                     routing CRUD/query
                               |
              +----------------+----------------+
              |                                 |
        +-----v----------------+        +-------v--------------+
        | Shard A / rsShardA   |        | Shard B / rsShardB   |
        | mongod A1 PRIMARY    |        | mongod B1 PRIMARY    |
        | mongod A2 SECONDARY  |        | mongod B2 SECONDARY  |
        | mongod A3 SECONDARY  |        | mongod B3 SECONDARY  |
        +----------------------+        +----------------------+

                 metadata / topology
              mongos <--------------------> CSRS
                                        +-------------------------+
                                        | cfgRS                   |
                                        | mongod cfg1 PRIMARY     |
                                        | mongod cfg2 SECONDARY   |
                                        | mongod cfg3 SECONDARY   |
                                        +-------------------------+
~~~

The connections in the diagram represent logical relationships. In real operation, mongos, shards, and CSRS also have internal communication flows to detect topology changes, manage metadata, and coordinate cluster tasks.

From the diagram, three distinguishing statements can be drawn:

- **Shard mongod instances store and process the portion of data that the shard is responsible for.**
- **mongos receives requests at the cluster level and routes them to the necessary shards.**
- **Config servers manage metadata so routing and cluster coordination decisions have a consistent foundation.**

## 6. Tracing a Read Request and a Data Modification Operation

Consider the **shop.orders** collection sharded by **customerId**.

### 6.1. Read Request with Shard Key

The application sends:

~~~javascript
db.orders.find({ customerId: 1450 });
~~~

Typical sequence:

1. The driver sends the command to an available mongos.
2. mongos checks its cached metadata to deduce which shard manages the data range containing **customerId = 1450**.
3. mongos forwards the request to the target shard.
4. mongod on the shard executes the query and uses indexes when appropriate.
5. Results are returned through mongos to the application.

If metadata changes due to data redistribution, the router needs to update its routing information. Config servers provide metadata as the source of truth for this operation.

### 6.2. Read Request That Cannot Target a Shard

The application sends:

~~~javascript
db.orders.find({ status: "PAID" }).sort({ createdAt: -1 });
~~~

If the shard key does not allow narrowing the scope, mongos may forward the request to the relevant shards. Each shard processes its own portion of data; results are coordinated to produce the exact output for the query.

The merging step may happen on mongos or on a shard depending on the query type and execution plan, especially with aggregation. Therefore, not every case should be described as "mongos performs the entire join/sort/aggregate itself."

### 6.3. Write Operation

The application sends a new document:

~~~javascript
db.orders.insertOne({
  orderNo: "ORD-1001",
  customerId: 1450,
  amount: 850000,
  status: "NEW",
  createdAt: new Date()
});
~~~

For a sharded collection, mongos routes the insert operation to the shard responsible for the document's shard key value. mongod on the target shard executes the write operation; replication within the shard copies the change according to the replica set mechanism.

**Config servers do not receive and store this order record in the dedicated config server model.** They manage information about data placement and cluster configuration. If the cluster uses a **config shard**, the shard holding the config server role itself can also store application records when partitioning metadata assigns them to it.

### 6.4. When Data Is Migrated Between Shards

Suppose the cluster needs to redistribute a data range:

~~~text
Before: Range X resides on Shard A
After:  Range X resides on Shard B
~~~

The data migration process is carried out collaboratively by cluster components, with metadata updated to reflect the new ownership. mongos uses the updated metadata to direct subsequent requests to the correct location.

Do not picture mongos reading each document from Shard A and saving it all into Shard B like an application data-copy tool. It is a router; data migration is an administrative mechanism between shards and MongoDB's coordination components.

## 7. Role of Each Component During Failures

Because a cluster has multiple components, how the system reacts depends on which component fails.

| Scenario | Typical Impact | Architectural Meaning |
| --- | --- | --- |
| Standalone mongod stops | That database is unavailable until recovered | No redundant member |
| One secondary mongod in a shard fails | The shard can still serve if primary and required conditions remain available | Replica set provides redundancy |
| Shard's primary mongod fails | Brief interruption possible during new primary election; if election conditions aren't met, writes are affected | Replication requires quorum and election |
| One mongos fails | Application can continue via another mongos if configured and reachable | Router is not where data is stored |
| CSRS loses primary but can still elect a new one | Metadata operations may pause briefly during primary transition | Metadata depends on CSRS availability |
| CSRS cannot elect a primary | Metadata update operations are restricted; some data queries/writes may still work depending on state | Metadata is no longer writable |
| All config servers become unreachable | Cluster risks widespread interruption or failure to operate | This is a core component that must be protected and backed up |
| One shard becomes unavailable | Data/operations related to that shard may be interrupted | Sharded data is not replicated to every shard |

There is no rule that "having three members means zero downtime." Availability depends on quorum, network conditions, number of available members, synchronized data, read/write concern, and specific topology.

### Example: mongos Failure and mongod Failure Are Not the Same

- If **mongos-1** goes down, data still resides on the shards. When **mongos-2** exists and the application is configured properly, the client can continue after detecting the failed connection.
- If **Shard A's primary mongod** goes down, routers still operate, but queries/writes involving Shard A must wait or are affected according to the replica set state.
- If the **CSRS encounters an issue**, shards may still retain full data, but the cluster loses part of its metadata-based coordination capability.

These scenarios explain why production monitoring must track routers, shard replica sets, and the config server replica set.

## 8. Inspecting Roles in mongosh

The following commands are for **observing** an existing deployment. Results depend on permissions, version, and whether you are connected to mongos or mongod.

### 8.1. Determining Whether You Are Connected to mongos or mongod

~~~javascript
db.adminCommand({ hello: 1 });
~~~

Common characteristics:

- If connected to **mongos**, the response contains the **msg** field with the value **isdbgrid**.
- If connected to **mongod in a replica set**, the response typically contains fields like **setName** and member state.
- If it is a mongod configured as a **config server**, it is still a mongod; you must cross-reference configuration/cluster info to identify the specialized role rather than relying solely on the absence of **isdbgrid**.

You can perform a quick check:

~~~javascript
const hello = db.adminCommand({ hello: 1 });

print("msg:", hello.msg);
print("setName:", hello.setName);
print("isWritablePrimary:", hello.isWritablePrimary);
~~~

Note: **isWritablePrimary** in a mongos response does not mean mongos is a replica set primary. When connected to mongos, the meaning of response properties must be interpreted according to the server type and how clients determine topology.

### 8.2. Viewing Sharded Cluster Status

Connect mongosh through **mongos** with appropriate administrative/observation privileges:

~~~javascript
sh.status();
~~~

This command provides information about shards, databases, sharded collections, and related status depending on the version. It is a useful way to verify you are inspecting the **entire cluster**, rather than an individual shard mongod.

List shards via an administrative command:

~~~javascript
db.adminCommand({ listShards: 1 });
~~~

Typical output represents each shard with its name, host/replica set, and status. Illustrative example:

~~~javascript
{
  shards: [
    { _id: "shardA", host: "rsShardA/a1.example.net:27018,a2.example.net:27018" },
    { _id: "shardB", host: "rsShardB/b1.example.net:27018,b2.example.net:27018" }
  ],
  ok: 1
}
~~~

Actual responses may have additional fields or detailed structures depending on the version. Do not infer the number of replica set members solely from the shortened host list in the example.

### 8.3. Identifying a Config Shard in MongoDB 8.0+

On a cluster supporting config shards, when connected to mongos, you can inspect the shard list:

~~~javascript
const result = db.adminCommand({ listShards: 1 });
const configShard = result.shards.find(shard => shard._id === "config");

print(configShard ? "Config shard present" : "No config shard");
~~~

If a shard with **_id = "config"** exists, the cluster uses a config shard. Otherwise, in a corresponding topology, the cluster uses dedicated config servers.

Do not manually update collections in the **config** database to try changing sharding behavior. Only use supported administrative commands when cluster configuration changes are needed.

### 8.4. Viewing the Replica Set Status of mongod

When connected to a mongod that is a replica set member with appropriate privileges:

~~~javascript
rs.status();
~~~

This command helps observe the replica set name, members, and primary/secondary states. This is a **replica-set-level** inspection, not a complete report of every shard across the entire cluster.

If connected to mongos, to observe the entire sharded cluster topology, prefer cluster-level commands like **sh.status()** or appropriate management/monitoring tools.

## 9. Visualizing How to Start and Connect

The two key binaries are **mongod** and **mongos**. Roles are determined by configuration and how processes participate in the topology.

| Task | Binary | Configuration Idea |
| --- | --- | --- |
| Run standalone MongoDB | mongod | Storage path, network, security |
| Run replica set member | mongod | Replica set name, storage, network |
| Run shard replica set member | mongod | Replica set name and **shardsvr** role |
| Run dedicated config server | mongod | Replica set name and **configsvr** role |
| Run query router | mongos | **Config server replica set** address |

### 9.1. Illustrative Configuration Examples

Below are **standalone configuration snippets to illustrate roles**, not a complete cluster deployment procedure. You still need to initialize replica sets, add shards, configure internal authentication, secure connections, and perform other administrative steps before operating.

Configuration of a mongod belonging to a shard replica set:

~~~yaml
# shard-a.yml
storage:
  dbPath: /var/lib/mongodb/shard-a
net:
  port: 27018
replication:
  replSetName: rsShardA
sharding:
  clusterRole: shardsvr
~~~

Configuration of a mongod belonging to a **dedicated config server replica set**:

~~~yaml
# config-a.yml
storage:
  dbPath: /var/lib/mongodb/config-a
net:
  port: 27019
replication:
  replSetName: cfgRS
sharding:
  clusterRole: configsvr
~~~

Configuration of a mongos router:

~~~yaml
# router.yml
net:
  port: 27017
sharding:
  configDB: cfgRS/cfg-a.example.net:27019,cfg-b.example.net:27019,cfg-c.example.net:27019
~~~

The configuration snippets above use illustrative hostnames and do not represent a real system. mongos **does not need to declare storage.dbPath** to store application collections.

Running the binaries with their corresponding configuration files:

~~~bash
mongod --config /etc/mongodb/shard-a.yml
mongod --config /etc/mongodb/config-a.yml
mongos --config /etc/mongodb/router.yml
~~~

These three commands only illustrate the difference between binaries and roles. **They do not automatically create a complete sharded cluster**: for instance, they do not cover preparing directories, hostnames, security configuration, initializing replica sets, or registering shards.

### 9.2. Where Should Applications Connect?

Standalone:

~~~text
mongodb://standalone.example.net:27017/bookstore
~~~

Replica set:

~~~text
mongodb://db-a.example.net:27017,db-b.example.net:27017,db-c.example.net:27017/bookstore?replicaSet=rsBooks
~~~

Sharded cluster (applications connect to mongos):

~~~text
mongodb://router-a.example.net:27017,router-b.example.net:27017/bookstore
~~~

These are sample URIs. In real environments, TLS, authentication, DNS, network policies, and connection options required by the deployment must be taken into account.

Java Driver example connecting through two mongos instances:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public class ReadBooks {
    public static void main(String[] args) {
        String uri = "mongodb://router-a.example.net:27017,"
                + "router-b.example.net:27017/bookstore";

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase("bookstore");
            MongoCollection<Document> books = db.getCollection("books");

            Document book = books.find(new Document("isbn", "9786040000123"))
                    .first();

            System.out.println(book);
        }
    }
}
~~~

The application only needs to use the collection query API; the driver together with mongos manages the path to the appropriate shards. If the environment is not sharded, the application connects to standalone or replica set mongod and does not need mongos/config servers.

## 10. Comparing Responsibilities by Operational Question

| Question | Primary Answering Component |
| --- | --- |
| Which machine is this document stored on? | mongod belonging to the shard owning the data; mongos routes based on metadata |
| Who directly executes queries against indexes and documents? | mongod of the shard |
| Who receives queries at the logical connection point of a sharded cluster? | mongos |
| Who knows which shard owns a range/chunk? | Metadata on config servers; mongos uses cached metadata |
| Who replicates data after the primary writes? | mongod members in the same replica set |
| Who elects a new shard primary after a failure? | Replica set members of the shard |
| Who provides availability for metadata? | Config Server Replica Set |
| Can multiple routers be deployed for redundancy? | Yes, multiple mongos instances |
| Can config servers be used to store application data? | Yes in the config shard model supported since MongoDB 8.0; not the purpose of a dedicated config server |
| With sharding, must applications always connect directly to each shard? | No; applications normally connect via mongos |

### Common Misconceptions

**Misconception 1: mongos is a database server with its own data.**  
mongos is a query router; durable data is managed by mongod inside shards. The router has a metadata cache but does not hold application documents like an independent data store.

**Misconception 2: A config server is a different binary from mongod.**  
A config server is a role of mongod. Only mongos is a router process with a separate binary.

**Misconception 3: Sharding and replica sets are the same thing.**  
A replica set holds copies of the same data; sharding splits data across shards. In practice, each shard uses a replica set.

**Misconception 4: Every query always goes through the config server.**  
mongos caches metadata and uses it for routing. It does not necessarily query the config server for every document on every read.

**Misconception 5: You can replace mongos by connecting directly to a shard.**  
A shard holds only a portion of partitioned data; connecting an application directly may return incomplete results or bypass proper coordination mechanisms.

**Misconception 6: Simply adding more mongos instances allows storing more data.**  
mongos does not increase data storage capacity. Storage capacity and data volume scalability depend on shards, partitioning strategy, and workload design.

**Misconception 7: Config servers in all versions can never contain application data.**  
That is true for the traditional dedicated role, but MongoDB 8.0+ supports config shards holding both metadata and application data.

## 11. Practice Exercise: Observing the Architecture

This exercise prioritizes **read-only** commands, suitable when you have a test MongoDB deployment and the necessary observation privileges.

### Scenario A: Connecting to a Replica Set

1. Connect via mongosh to a test replica set.
2. Run the commands:

~~~javascript
db.adminCommand({ hello: 1 });
rs.status();
~~~

3. Find the replica set name, the current primary member, and the secondaries.
4. Identify which components are **mongod**; explain why mongos is not needed in this replica-set-only topology.

### Scenario B: Connecting to a Sharded Cluster

1. Connect mongosh through mongos.
2. Run:

~~~javascript
const info = db.adminCommand({ hello: 1 });
print(info.msg);

sh.status();

const shards = db.adminCommand({ listShards: 1 });
printjson(shards);
~~~

3. Observe the **isdbgrid** value and the shard list.
4. From the observed configuration, distinguish between **router**, **shard**, and **config server**.
5. If the version is 8.0 or higher, check whether a shard with **_id = "config"** exists to see if a config shard is being used.

### Scenario C: Explaining the Path of a Query

Suppose **shop.orders** is sharded by **customerId** and has two shards:

~~~javascript
db.orders.find({ customerId: 1450 });
db.orders.find({ status: "PAID" });
~~~

Answer the following:

1. Is the first request likely to be routed to one shard or multiple shards? Why?
2. Why might the second request require scatter/gather?
3. Which component holds the long-term partitioning map?
4. Which component directly uses indexes and reads documents?
5. If the currently connected mongos fails while a backup mongos is available, does the data on the shards disappear?
6. If a shard's replica set loses its primary, which components participate in electing a new primary?

A good answer clearly distinguishes the three responsibilities: **mongos routes**, **mongod on shards processes and stores data**, and **config servers manage metadata**. Understanding each role individually is the foundation for continuing to learn replication, sharding, shard keys, the balancer, availability, and MongoDB monitoring.

## References

- [MongoDB — Sharded Cluster Components](https://www.mongodb.com/docs/manual/core/sharded-cluster-components/)
- [MongoDB — Routing with mongos](https://www.mongodb.com/docs/manual/core/sharded-cluster-query-router/)
- [MongoDB — Config Servers](https://www.mongodb.com/docs/manual/core/sharded-cluster-config-servers/)
- [MongoDB — Config Shards](https://www.mongodb.com/docs/manual/core/config-shard/)
- [MongoDB — Shards](https://www.mongodb.com/docs/manual/core/sharded-cluster-shards/)
