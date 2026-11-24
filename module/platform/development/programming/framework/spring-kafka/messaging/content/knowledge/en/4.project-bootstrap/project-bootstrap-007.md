# Configuring Kafka in KRaft Mode

## Lesson Objectives

In the **Project Bootstrap** chapter, this lesson guides configuring Apache Kafka in KRaft mode (Kafka Raft Metadata mode), from a single node for local development to a multi-broker and controller architecture for production environments.

**SPRING_KAFKA_MESSAGING** focuses on building event-sending and event-receiving applications with Spring Kafka, KafkaTemplate, and @KafkaListener; while helping learners understand topics, partitions, offsets, consumer groups, serialization, retries, dead-lettering, transactions, exactly-once, concurrency, and testing. Kafka KRaft is the underlying infrastructure the application uses to store and distribute records.

After this lesson, learners can:

- Explain how KRaft changes the way Kafka manages metadata and the controller role.
- Distinguish between a broker, a controller, and a combined broker/controller node.
- Configure process roles, node ID, listeners, advertised addresses, and the controller quorum.
- Initialize storage with a cluster ID and the appropriate format command.
- Start and inspect the cluster and create topics.
- Connect a Spring Kafka application to a KRaft broker.
- Identify differences between development and production configurations, as well as common configuration errors.

## 1. What Is KRaft?

KRaft is the Kafka mode that uses the Raft consensus protocol to manage cluster metadata. Metadata includes information about brokers, topics, partitions, replicas, configurations, and related administrative changes.

In earlier Kafka architectures, ZooKeeper was used to store and coordinate cluster metadata. With KRaft, Kafka brings metadata management inside Kafka itself through a group of controllers. As a result, a KRaft cluster does not need a separate ZooKeeper ensemble.

KRaft does not change how producer and consumer applications send and receive records over the Kafka protocol. Spring applications still connect to the broker's bootstrap address as usual. The main changes lie in cluster management architecture, storage initialization, and controller operations.

~~~mermaid
flowchart TB
    subgraph APP["Application"]
        P["Producer / KafkaTemplate"]
        C["Consumer / @KafkaListener"]
    end
    subgraph KAFKA["KRaft Kafka cluster"]
        B1["Broker 1"]
        B2["Broker 2"]
        B3["Broker 3"]
        Q["Controller quorum"]
        B1 --- Q
        B2 --- Q
        B3 --- Q
    end
    P --> B1
    C --> B2
    Q --> B1
    Q --> B2
    Q --> B3
~~~

Controllers manage metadata and coordinate cluster changes. Brokers accept requests from producers/consumers, store partition logs, and serve record reads. Brokers exchange metadata with controllers over the controller listener.

### 1.1. What Does KRaft Bring?

- Reduces the number of infrastructure components to deploy and operate since ZooKeeper is not needed.
- Manages metadata using a Raft-based controller quorum mechanism.
- Clearly separates metadata coordination responsibilities from data serving.
- Supports scaling and metadata recovery under the controller quorum model.
- Moves Kafka architecture toward a more self-managed system.

KRaft does not automatically guarantee high availability for the cluster. Controller count, data replication, listener configuration, persistent storage, networking, and operational procedures still determine system reliability.

## 2. Distinguishing Brokers and Controllers

### 2.1. Broker

A broker is a node that serves Kafka data. It receives records from producers, stores records in partition logs, serves data reads to consumers, and participates in replication among brokers.

Common responsibilities:

- Accepting connections from producers and consumers.
- Storing partition replicas on disk.
- Coordinating replication, leaders, and followers.
- Serving read/write requests and administrative requests.
- Reporting broker status and metadata to controllers.

### 2.2. Controller

A controller is a node that participates in managing cluster metadata. The group of controllers forms a quorum and uses Raft to reach consensus on metadata changes.

Key responsibilities:

- Managing the cluster's metadata state.
- Coordinating broker membership changes.
- Managing topic, partition, and related configuration changes.
- Coordinating leader changes and replica states.
- Distributing necessary metadata to brokers.

In a quorum, one controller acts as the leader and the remaining controllers follow the metadata log, ready to participate in elections when needed. The quorum can only make changes requiring consensus when enough members are active to meet the majority threshold.

### 2.3. Combined Broker and Controller Node

Kafka allows a single node to hold both roles:

~~~properties
process.roles=broker,controller
~~~

This combined approach is convenient for development or single-node testing. It lets you run Kafka with fewer components, though the broker and controller share CPU, memory, network, and storage resources.

In production, it is usually better to separate dedicated controllers from brokers so data-serving load does not directly impact the ability to maintain the metadata quorum. Deployment decisions should be based on the Kafka version's guidance, cluster scale, and availability requirements.

## 3. Important KRaft Configuration Properties

A Kafka KRaft configuration file typically contains the following property groups.

| Property | Meaning |
|---|---|
| `process.roles` | Roles assumed by the node: `broker`, `controller`, or both |
| `node.id` | Unique ID of the node within the cluster |
| `controller.quorum.voters` | List of controller voters in a static quorum configuration |
| `controller.quorum.bootstrap.servers` | Controller bootstrap addresses in versions supporting dynamic quorum |
| `listeners` | Endpoints the Kafka process binds to in order to accept connections |
| `advertised.listeners` | Addresses the node advertises for clients or other brokers to connect to |
| `controller.listener.names` | Listener name used for controller communication |
| `inter.broker.listener.name` | Listener used for communication between brokers |
| `listener.security.protocol.map` | Maps custom listener names to security protocols |
| `log.dirs` | Directories storing partition logs |
| `metadata.log.dir` | Separate directory storing KRaft metadata logs if configured |

### 3.1. process.roles

The value of `process.roles` determines which role the node takes in the system:

- `broker`: data-serving node.
- `controller`: node managing metadata and participating in the quorum.
- `broker,controller`: node combining both roles.

A controller-only node does not accept data requests from producers/consumers. A broker-only node does not participate in controller elections, but still needs to connect to the controller quorum to receive metadata.

### 3.2. node.id

`node.id` is the unique identifier for each Kafka node. This value must match the identifier declared in the quorum configuration if the node is a controller voter.

Example:

~~~properties
node.id=1
~~~

Do not use the same node ID for two active nodes in a cluster. When replacing a node, follow the cluster's operational and membership procedures rather than arbitrarily copying configurations or storage.

### 3.3. Controller Quorum

With a static quorum configuration, the `controller.quorum.voters` property lists controller voters in the format:

~~~properties
controller.quorum.voters=1@controller-1:9093,2@controller-2:9093,3@controller-3:9093
~~~

Each entry has the form `node-id@host:port`. The node ID must match the `node.id` of the corresponding controller; the host and port must point to a reachable controller listener.

A quorum of 3 voters requires at least 2 active voters to reach a majority. A quorum of 5 voters requires at least 3 voters. Therefore, production deployments commonly use an odd number of controllers such as 3 or 5 to balance fault tolerance and operational cost.

**Version note:** Some Kafka versions support a dynamic controller quorum, using `controller.quorum.bootstrap.servers` and the corresponding storage bootstrap procedure. Do not mix static and dynamic quorum configurations arbitrarily. Use the configuration, format command, and membership procedure specific to the Kafka version being deployed. The `controller.quorum.voters` examples in this lesson illustrate the static quorum model.

### 3.4. Listeners and Advertised Addresses

Kafka can use multiple listeners for different purposes:

- Client listener accepts connections from producers and consumers.
- Inter-broker listener handles communication between brokers.
- Controller listener handles communication between brokers and the controller quorum.

`listeners` specifies the bind address on the node. `advertised.listeners` specifies the address Kafka advertises to clients or other brokers. These two values can differ, especially when running Kafka in containers or behind NAT.

Do not advertise the controller listener address as an application endpoint. Producers and consumers only need to bootstrap to the broker listener; the controller listener should stay on an internal network dedicated to Kafka components.

## 4. Single-Node KRaft Configuration for Development

To learn and develop Spring Kafka applications, you can start with a combined broker/controller node. The configuration below uses a single-voter static quorum and a PLAINTEXT listener on the local machine.

Create `config/kraft/server.properties`:

~~~properties
# Node identity and roles
process.roles=broker,controller
node.id=1

# Static controller quorum: one node for local development
controller.quorum.voters=1@localhost:9093

# Network listeners
listeners=PLAINTEXT://:9092,CONTROLLER://:9093
advertised.listeners=PLAINTEXT://localhost:9092
listener.security.protocol.map=PLAINTEXT:PLAINTEXT,CONTROLLER:PLAINTEXT

# Controller and inter-broker communication
controller.listener.names=CONTROLLER
inter.broker.listener.name=PLAINTEXT

# Storage
log.dirs=/tmp/kraft-combined-logs

# Single-node development settings
num.partitions=3
default.replication.factor=1
offsets.topic.replication.factor=1
transaction.state.log.replication.factor=1
transaction.state.log.min.isr=1
group.initial.rebalance.delay.ms=0

# Explicitly manage topics during learning
auto.create.topics.enable=false
~~~

Explanation of key points:

- `process.roles=broker,controller` lets the node both serve data and manage metadata.
- `node.id=1` sets the node identifier.
- `controller.quorum.voters=1@localhost:9093` declares this node itself as the sole controller voter.
- `listeners` opens the broker listener on port 9092 and the controller listener on port 9093.
- `advertised.listeners` advertises the broker address for applications running on the same machine.
- `controller.listener.names` specifies the listener for the controller protocol.
- `inter.broker.listener.name` specifies the listener for inter-broker communication.
- `log.dirs` specifies where partition logs are stored.
- Replication factors of 1 are only suitable for a single-node cluster. They provide no fault tolerance if the node stops.

This is a development configuration. Do not use PLAINTEXT, a replication factor of 1, or a single controller as a production configuration.

## 5. Generating a Cluster ID and Formatting Storage

KRaft stores metadata in Kafka's storage. Before starting a node for the first time, generate a cluster ID and format the storage directories according to the node configuration.

### 5.1. Generating a Cluster ID

Use the `kafka-storage` tool bundled with the Kafka distribution:

~~~bash
bin/kafka-storage.sh random-uuid
~~~

The command returns a UUID. Save this value to use for the cluster.

The cluster ID establishes cluster identity. All nodes belonging to the same cluster must be formatted with the same cluster ID. Each node still has its own `node.id`.

### 5.2. Formatting Storage for the First Time

With the static quorum example above:

~~~bash
bin/kafka-storage.sh format \
  -t <CLUSTER_ID> \
  -c config/kraft/server.properties
~~~

Replace `<CLUSTER_ID>` with the generated UUID. The format command initializes the required metadata in the configured storage directories.

Important notes:

- Format storage before starting Kafka for the first time on a new node.
- Use the same cluster ID for nodes in the same cluster.
- Use a unique node ID for each node.
- Each node must format its own storage with its corresponding configuration file.
- Do not run format on every restart.
- Do not delete or reformat directories containing active data to troubleshoot ordinary startup errors.
- For dynamic quorum, use the bootstrap procedure and format flags specific to that version; do not copy static quorum commands as-is.

You can inspect storage information with:

~~~bash
bin/kafka-storage.sh info \
  -c config/kraft/server.properties
~~~

### 5.3. Starting Kafka

After formatting succeeds:

~~~bash
bin/kafka-server-start.sh config/kraft/server.properties
~~~

Kafka will start both the broker and controller in the same process. Monitor logs to confirm the node has started, the controller quorum has formed, and the broker listener is ready to accept connections.

On Windows, the Kafka distribution provides corresponding scripts under `bin\windows`, for example:

~~~powershell
.\bin\windows\kafka-storage.bat random-uuid
.\bin\windows\kafka-storage.bat format -t <CLUSTER_ID> -c .\config\kraft\server.properties
.\bin\windows\kafka-server-start.bat .\config\kraft\server.properties
~~~

Verify script names and parameters against the installed Kafka version. Do not run multiple format commands concurrently on the same storage directory.

## 6. Verifying the KRaft Cluster After Startup

Successfully starting a process is not enough to conclude the cluster works properly. Verify the controller quorum, broker listener, and topic administration operations.

### 6.1. Checking the Controller Quorum

Use the metadata quorum tool:

~~~bash
bin/kafka-metadata-quorum.sh \
  --bootstrap-controller localhost:9093 \
  describe --status
~~~

In a single-node cluster, verify that the controller has formed a quorum and has a leader. In a multi-controller cluster, check the leader, voters, and metadata sync state using the tool for your version.

### 6.2. Checking That the Broker Accepts Connections

~~~bash
bin/kafka-broker-api-versions.sh \
  --bootstrap-server localhost:9092
~~~

This command tests connectivity to the broker listener and displays the API versions supported by the broker.

### 6.3. Creating and Describing a Topic

Create a topic for Spring Kafka examples:

~~~bash
bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create \
  --topic orders.created \
  --partitions 3 \
  --replication-factor 1
~~~

List topics:

~~~bash
bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --list
~~~

Describe the topic:

~~~bash
bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --describe \
  --topic orders.created
~~~

With a single-broker cluster, the replication factor must be 1. If a replication factor greater than the number of available brokers is requested, topic creation will fail.

### 6.4. Testing Sending and Reading Records

Send a record using the console producer:

~~~bash
bin/kafka-console-producer.sh \
  --bootstrap-server localhost:9092 \
  --topic orders.created
~~~

Enter a line of text and end input. In another terminal, run the console consumer:

~~~bash
bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic orders.created \
  --from-beginning
~~~

If the consumer receives the record, the broker listener is serving the basic publish/consume flow. This is a Kafka infrastructure check; Spring Kafka integration tests are performed at the application level.

## 7. Connecting a Spring Kafka Application to a KRaft Cluster

A Spring Kafka application does not need to know how the controller quorum operates. It connects to brokers through the bootstrap server.

Example configuration in `application.yml`:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092

    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer

    consumer:
      group-id: billing-service
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
~~~

A simple producer:

~~~java
@Service
public class EventPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public EventPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(String orderId, String payload) {
        kafkaTemplate.send("orders.created", orderId, payload);
    }
}
~~~

A simple consumer:

~~~java
@Service
public class EventListener {

    @KafkaListener(
        topics = "orders.created",
        groupId = "billing-service"
    )
    public void receive(String payload) {
        // Process the event in billing business logic.
    }
}
~~~

Key points to remember:

- `spring.kafka.bootstrap-servers` points to the broker listener, not the controller listener.
- Applications do not connect directly to the controller quorum to send or receive records.
- Serializers and deserializers must match the data format on both sides.
- Group ID identifies the consumer group and how Kafka distributes partitions.
- When moving from a development cluster to production, update the bootstrap addresses, security, and client properties accordingly.

## 8. Running KRaft in Docker and Distinguishing Network Addresses

When running Kafka in Docker, `localhost` inside a container refers to that container itself. An application running on the host machine and an application running inside the Docker network may require two different broker addresses.

A multi-listener configuration typically follows this idea:

~~~properties
listeners=INTERNAL://:9092,EXTERNAL://:29092,CONTROLLER://:9093
advertised.listeners=INTERNAL://kafka:9092,EXTERNAL://localhost:29092
listener.security.protocol.map=INTERNAL:PLAINTEXT,EXTERNAL:PLAINTEXT,CONTROLLER:PLAINTEXT
inter.broker.listener.name=INTERNAL
controller.listener.names=CONTROLLER
~~~

In this example:

- Application containers in the same Docker network connect to `kafka:9092`.
- Applications running on the host machine connect to `localhost:29092`.
- The controller listener uses port 9093 for internal Kafka communication.
- The hostname `kafka` must be resolvable within the Docker network.
- The external port must be published to the host if applications outside Docker need access.

This is only the illustrative listener configuration; it still must be combined with `process.roles`, `node.id`, quorum, storage, and appropriate replication properties. Environment variables and storage formatting depend on the chosen Kafka Docker image. Do not assume variable names from one image apply to another.

### 8.1. Common Addressing Mistakes

- Application in a container connects to `localhost:9092` while Kafka runs in another container: `localhost` mistakenly points to the application container.
- Kafka advertises `localhost:9092` to clients inside the Docker network: clients receive an address unreachable from their container.
- Application uses controller port 9093 as the bootstrap server: this is not a broker client listener.
- `listeners` binds properly, but `advertised.listeners` is wrong: initial bootstrap may succeed, yet the client fails when connecting to the broker returned in metadata.

## 9. Multi-Node KRaft Architecture for Production

A production cluster typically separates controllers and brokers into distinct node groups.

Example architecture:

~~~mermaid
flowchart TB
    subgraph CTRL["Controller quorum - 3 nodes"]
        C1["Controller 1"]
        C2["Controller 2"]
        C3["Controller 3"]
        C1 --- C2
        C2 --- C3
        C3 --- C1
    end
    subgraph BR["Broker pool"]
        B1["Broker 1"]
        B2["Broker 2"]
        B3["Broker 3"]
    end
    APP["Spring applications"] --> B1
    APP --> B2
    APP --> B3
    B1 --> C1
    B2 --> C2
    B3 --> C3
~~~

### 9.1. Controller-Only Node

Example of a controller in a three-node static quorum:

~~~properties
process.roles=controller
node.id=100

listeners=CONTROLLER://controller-1.internal:9093
controller.listener.names=CONTROLLER
controller.quorum.voters=100@controller-1.internal:9093,101@controller-2.internal:9093,102@controller-3.internal:9093

listener.security.protocol.map=CONTROLLER:SSL
metadata.log.dir=/var/lib/kafka/controller-metadata
~~~

Other controllers use their own node IDs and addresses, while declaring the same quorum voter list. The controller listener must be resolvable and allow quorum members to communicate.

### 9.2. Broker-Only Node

Example of a broker:

~~~properties
process.roles=broker
node.id=1

listeners=INTERNAL://broker-1.internal:9092
advertised.listeners=INTERNAL://broker-1.internal:9092
inter.broker.listener.name=INTERNAL

controller.listener.names=CONTROLLER
controller.quorum.voters=100@controller-1.internal:9093,101@controller-2.internal:9093,102@controller-3.internal:9093

listener.security.protocol.map=INTERNAL:SSL,CONTROLLER:SSL
log.dirs=/var/lib/kafka/data
~~~

A broker-only node does not bind a controller listener to accept connections from controllers. It uses the controller listener configuration and quorum addresses to connect to controllers. Brokers need consistent quorum configuration and security matching the cluster.

These are directional examples for a static quorum. Real TLS configuration also needs truststores, keystores, principals, ACLs, and appropriate authentication properties. Check the requirements of your Kafka version and deployment platform before using directly.

### 9.3. Replication and Fault Tolerance

A production cluster needs enough brokers to place replicas for partitions. A common example is replication factor 3, with `min.insync.replicas=2` per topic or broker according to write requirements.

The controller quorum and partition replication solve two different kinds of state:

- The controller quorum ensures metadata consistency.
- Partition replication protects records when a broker fails.

Having 3 controllers does not mean topic data automatically has 3 replicas. You must configure replication factor, min ISR, rack awareness, and replica placement separately.

## 10. Storage and Cluster Lifecycle

### 10.1. Distinguishing Cluster ID, Node ID, and Directory

| Identifier | Scope | Purpose |
|---|---|---|
| Cluster ID | Entire cluster | Identifies a Kafka cluster |
| Node ID | Per node | Identifies a broker/controller within the cluster |
| Directory ID | Per storage directory in supported workflows | Identifies a node's storage directory |

The cluster ID must be consistent across nodes in the same cluster. The node ID must be unique. Do not use a cluster ID in place of a node ID, and do not generate a new cluster ID when simply restarting a node.

### 10.2. Partition Logs and Metadata Logs

Partition logs hold records sent by producers to topics. Metadata logs store metadata changes agreed upon by the controller quorum.

You can configure `log.dirs` to store partition data and `metadata.log.dir` to specify a separate location for metadata logs. If a separate metadata log directory is not configured, the default location depends on Kafka's storage configuration.

These directories need persistent storage in production. When running in containers, mount appropriate volumes so data is not lost when containers are replaced.

### 10.3. Restarting and Replacing Nodes

Restarting a node with its existing storage is a normal operational procedure. Kafka uses the stored metadata and data to recover state.

When replacing a node, do not simply copy the entire storage directory from another node and change `node.id`. Follow the broker/controller replacement procedure for your Kafka version, ensuring membership, directory identity, replica reassignment, and quorum are handled properly.

Do not reformat storage containing existing data to fix startup errors without determining the root cause and recovery plan. Formatting is a storage initialization operation, not a safe reset command.

## 11. Listener and Connection Security

Development examples use PLAINTEXT to minimize initial setup. Production requires designing security for the client listener, inter-broker listener, and controller listener.

Areas to consider:

- TLS to encrypt connections.
- SASL when client or node authentication is required.
- ACLs to restrict read, write, topic creation, and administrative permissions.
- Separating the controller network from client-access networks.
- Not exposing controller endpoints to the Internet or untrusted networks.
- Managing certificates, keys, and secrets with a secret manager.
- Verifying hostnames and certificates when clients use TLS.

Listener names can be mapped to `SSL` or `SASL_SSL` via `listener.security.protocol.map`. Each listener must be configured with the corresponding credentials and security policies. Do not simply change the protocol value while omitting the required truststore, keystore, SASL mechanism, or ACLs.

## 12. Connecting KRaft with the Spring Project Bootstrap Workflow

When bootstrapping a Spring Kafka project, the work can be divided into steps:

1. Choose the Kafka version and identify the appropriate quorum model.
2. Prepare broker/controller configuration and listener addresses.
3. Generate a cluster ID and format storage for the first time.
4. Start Kafka and verify the controller quorum.
5. Create topics, partitions, and replication factors according to the environment.
6. Configure `spring.kafka.bootstrap-servers` for the application.
7. Choose serializers/deserializers and consumer groups.
8. Test the producer, consumer, and integration tests.
9. Set up logs, metrics, alerts, and operational procedures.

Spring Kafka is the application-side integration layer. Provisioning the KRaft cluster is the responsibility of the Kafka platform; the two parts connect through the broker listener and the Kafka protocol.

## 13. Common KRaft Errors

| Symptom | Possible Cause | Troubleshooting Direction |
|---|---|---|
| Kafka fails to start due to missing role configuration | Missing or invalid `process.roles` | Check the node's roles and Kafka version |
| Controller fails to form a quorum | Wrong voter ID, hostname, port, or controller listener | Compare `node.id`, quorum list, and controller addresses |
| Node reports cluster ID mismatch | Storage was formatted with a different cluster ID | Check each node's cluster ID and format history |
| Broker starts but clients cannot connect | Wrong `listeners`, firewall, or port mapping | Check bound endpoints and broker logs |
| Bootstrap succeeds but subsequent requests fail | `advertised.listeners` advertises an unreachable host | Check the addresses the broker returns to clients |
| Client connects to the controller port by mistake | Using the controller listener as the bootstrap server | Use the broker listener |
| Cannot create topic with requested RF | Replication factor exceeds the number of eligible brokers | Check broker count and replication factor |
| Transaction topic cannot be created on a single-node cluster | Transaction replication factor or min ISR exceeds cluster capacity | Use values suitable for development or add brokers |
| Docker client cannot resolve broker | Advertising a hostname for the wrong network | Use internal addresses for containers and external addresses for the host |
| Restart loses data | Storage is not persisted on a persistent volume | Check volume mounts and permissions |

## 14. Pre-Use Checklist

### Development

- [ ] Choose the right Kafka version and a supported quorum mode.
- [ ] Declare `process.roles` and `node.id`.
- [ ] Configure separate broker and controller listeners.
- [ ] Set `advertised.listeners` to addresses clients can actually reach.
- [ ] Generate a cluster ID and format storage for the first time.
- [ ] Use replication factor 1 only for a single-node cluster.
- [ ] Verify the controller quorum and broker listener are working.
- [ ] Create topics and test sending/receiving records.
- [ ] Connect Spring Kafka via the broker bootstrap server.

### Production

- [ ] Separate dedicated controllers and brokers according to cluster design.
- [ ] Use a controller quorum with an appropriate voter count, typically 3 or 5.
- [ ] Maintain explicit cluster ID, node ID, and storage identity for each node.
- [ ] Use persistent storage and have recovery procedures in place.
- [ ] Configure replication factor, min ISR, and rack awareness.
- [ ] Separate client, inter-broker, and controller listeners.
- [ ] Enable TLS/SASL and ACLs per security requirements.
- [ ] Do not expose the controller listener to application clients.
- [ ] Monitor quorum, brokers, partitions, replicas, and storage capacity.
- [ ] Have procedures for upgrades, node replacement, and incident recovery.

## Conclusion

KRaft brings metadata management and cluster coordination into Kafka through a Raft-based controller quorum. Each node is configured with roles and a node ID; listeners define endpoints for clients, brokers, and controllers; storage is initialized with a cluster ID following the procedure for your Kafka version.

For a Spring Kafka application, the connection point remains the broker listener advertised via the bootstrap server. By understanding the boundary between controllers, brokers, and the application, learners can quickly bootstrap a development environment while knowing what configurations are required to advance toward a fault-tolerant, secure, and stably operated production cluster.
