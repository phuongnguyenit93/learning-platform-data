# bootstrap servers and broker discovery mechanism

A Spring Kafka application needs to know an address to start connecting to a Kafka cluster. The **bootstrap.servers** property provides the list of initial broker addresses that a Kafka client can contact. After connecting to a broker, the client retrieves the cluster metadata to learn which broker manages each partition, which broker is the leader, and which addresses to connect to in order to send or receive records.

Therefore, bootstrap servers are the starting point of the connection process. This list is not a fixed list that the client uses for every operation. The Kafka client discovers the topology from the metadata returned by the broker and then connects directly to the brokers advertised in the metadata. This mechanism enables producers, consumers, and AdminClient to operate across a multi-broker cluster.

This lesson belongs to the **Connection Configuration** chapter of the **SPRING_KAFKA_MESSAGING** module, focusing on how to configure Spring Kafka, understand metadata discovery, handle broker addresses in container and deployment network environments, and diagnose connection errors to operate messaging flows reliably.

## Learning Outcomes

After this lesson, you will be able to:

- Explain what bootstrap.servers is and why a client only needs a few reachable initial addresses.
- Describe the steps a Kafka client takes to connect to a broker, retrieve metadata, and route requests to the partition leader.
- Distinguish between listeners and advertised.listeners on the broker side.
- Configure bootstrap servers for Spring Boot and Spring Kafka.
- Choose the appropriate addresses when an application runs on a local machine, Docker Compose, Kubernetes, or an external network.
- Recognize why a bootstrap connection succeeds while a producer or consumer still fails to work.
- Inspect metadata and distinguish between DNS, TCP, TLS/SASL, ACL, and leader errors.
- Design connection configurations that are resilient, secure, and testable.

## 1. What is bootstrap.servers?

A Kafka client needs an address to send its first request to the cluster. The bootstrap.servers property is the list of hosts and ports used for this step.

Example:

~~~properties
bootstrap.servers=kafka-1.example.net:9092,kafka-2.example.net:9092,kafka-3.example.net:9092
~~~

Each entry typically has the host:port format. Addresses are comma-separated, without protocol prefixes such as http:// or https://. The security protocol is configured separately using security.protocol and related properties.

A client is not required to know every broker in the cluster upfront. As long as at least one bootstrap address is active and returns valid metadata, the client can discover the other brokers. However, declaring multiple bootstrap addresses gives the client additional options if one broker or initial endpoint is temporarily unreachable.

Example configuration for a development environment:

~~~properties
bootstrap.servers=localhost:9092
~~~

Example configuration for a multi-broker cluster:

~~~properties
bootstrap.servers=kafka-1:9092,kafka-2:9092,kafka-3:9092
~~~

The bootstrap list does not determine which partition resides on which broker. Partition distribution, leaders, and replicas are managed by the Kafka cluster. The client obtains that information through metadata.

Need to distinguish:

| Component | Meaning |
|---|---|
| bootstrap.servers | Initial list of addresses for the client to contact the cluster and fetch metadata. |
| Broker ID | Broker identifier in the cluster, used by metadata to describe the topology. |
| Partition leader | The broker responsible for handling primary read/write requests for that partition. |
| advertised.listeners | The addresses that the broker publishes for clients to connect to after metadata discovery. |
| Metadata | Information about the cluster, brokers, topics, partitions, leaders, replicas, and ISR. |

## 2. Broker discovery and metadata mechanism

The connection process does not stop at opening a TCP connection to a bootstrap server. The Kafka client needs metadata to know the actual destination for its requests.

Overall flow:

~~~mermaid
sequenceDiagram
    participant Client as Kafka Client
    participant Seed as Bootstrap Broker
    participant Leader as Partition Leader
    Client->>Seed: Connect to initial host:port
    Client->>Seed: ApiVersions / Metadata request
    Seed-->>Client: Cluster metadata and advertised endpoints
    Client->>Client: Cache metadata locally
    Client->>Leader: Send request to broker managing partition
    Leader-->>Client: Produce / Fetch response
~~~

Key steps:

1. **Read bootstrap.servers:** the client parses the list of hosts and ports.
2. **DNS resolution:** the operating system resolves hostnames into IP addresses.
3. **Establish connection:** the client opens a connection to a reachable bootstrap endpoint.
4. **Protocol and security negotiation:** the client exchanges API version information; if TLS or SASL is used, the handshake and authentication are performed according to the configuration.
5. **Request metadata:** the client asks the broker for the cluster topology and the topics to be used.
6. **Receive metadata:** the broker returns the broker list along with partition, leader, replica, and ISR information.
7. **Connect to target broker:** the client uses the broker addresses in the metadata to send Produce, Fetch, or administrative requests.
8. **Refresh metadata:** when the topology changes or the client encounters leader-related errors, the client can request fresh metadata.

For example, the topic orders.created has three partitions. Partition 0 has its leader on broker 1, partition 1 has its leader on broker 2, and partition 2 has its leader on broker 3. A producer sending a record with a key routed to partition 2 will need to connect to broker 3 according to the metadata, even though the initial connection was established through broker 1.

~~~mermaid
flowchart TD
    C[Kafka Producer] --> S[Bootstrap endpoint]
    S --> M[Cluster metadata]
    M --> P0[Partition 0 - Leader Broker 1]
    M --> P1[Partition 1 - Leader Broker 2]
    M --> P2[Partition 2 - Leader Broker 3]
    C --> P2
~~~

Consumers also use metadata to know which brokers serve the assigned partitions. In addition, a consumer group needs to locate the group coordinator to join the group, send heartbeats, and commit offsets. The coordinator may be a different broker from the bootstrap broker.

This explains a common situation: a connectivity check command to the bootstrap server succeeds, yet the application still cannot send or receive records. The cause may be that the broker addresses in the metadata are unreachable from the application's network.

## 3. Bootstrap servers are not a proxy for the entire cluster

A common misconception is that declaring one bootstrap address means all Kafka requests go through that address. In reality, the bootstrap server only helps the client initiate the connection and fetch metadata. Afterwards, the client connects to the broker specified in the metadata.

Example:

- The application connects to kafka-bootstrap.example.net:9092.
- The broker returns metadata indicating that the leader of the target partition is kafka-2.internal:9092.
- The client needs to resolve and connect to kafka-2.internal:9092.

If the machine running the application cannot resolve the hostname kafka-2.internal or a firewall blocks port 9092, the client will still fail even though the initial bootstrap endpoint works.

Declaring multiple bootstrap servers provides redundancy for the initial connection step. It does not automatically fix incorrect advertised.listeners addresses, does not create a network route to the leader broker, and does not replace Kafka's replication mechanism.

With a load balancer, you must understand how it works. A TCP load balancer can forward the bootstrap connection to a broker, but the metadata may still contain the individual addresses of each broker. The client must be able to reach those addresses. A generic load balancer does not automatically turn Kafka into a single-endpoint protocol like a typical HTTP API. If a load balancer or DNS is used, the infrastructure must provide proper connection mapping for each advertised broker.

## 4. listeners and advertised.listeners

To understand why a client can connect to the bootstrap server successfully but cannot connect to subsequent brokers, you need to distinguish two configurations on the Kafka broker side.

- **listeners:** the addresses and ports that the broker binds to in order to listen for connections on network interfaces.
- **advertised.listeners:** the addresses and ports that the broker publishes in metadata for clients to use when connecting.

An example of a broker with two listeners:

~~~properties
listeners=INTERNAL://0.0.0.0:9092,EXTERNAL://0.0.0.0:9094
advertised.listeners=INTERNAL://kafka-1:9092,EXTERNAL://broker-1.example.net:9094
listener.security.protocol.map=INTERNAL:PLAINTEXT,EXTERNAL:SASL_SSL
inter.broker.listener.name=INTERNAL
~~~

In this example:

- The broker listens on all interfaces on port 9092 for the INTERNAL listener and port 9094 for EXTERNAL.
- Clients within the same internal network use kafka-1:9092.
- Clients from an external network use broker-1.example.net:9094.
- Brokers communicate internally via the INTERNAL listener.

The address 0.0.0.0 is a bind address, not a hostname for clients to use. The broker must advertise a hostname that is reachable from the client's perspective.

For a cluster, each broker must advertise the exact endpoint corresponding to the listener that the client connected to. If metadata returns internal hostnames to an external client, the client will not be able to connect. If the broker advertises localhost to a client in a container or on another machine, the client will try to connect to its own machine instead of the machine running the broker.

~~~mermaid
flowchart LR
    subgraph Network["Application network"]
        APP[Spring Boot client]
        DNS[DNS / Service discovery]
    end
    subgraph Cluster["Kafka cluster"]
        B1[Broker 1]
        B2[Broker 2]
        B3[Broker 3]
    end
    APP --> DNS
    DNS --> B1
    B1 -. Metadata .-> APP
    APP --> B2
    APP --> B3
~~~

Key principle: every broker endpoint returned in metadata must be resolvable and reachable from the environment where the Kafka client is running.

## 5. Configuring Spring Kafka in Spring Boot

With Spring Boot, the bootstrap servers configuration is usually placed in application.yml:

~~~yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
    consumer:
      group-id: orders-service
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      auto-offset-reset: earliest
~~~

The KAFKA_BOOTSTRAP_SERVERS environment variable allows changing the cluster address per environment without modifying source code. The default value localhost:9092 is only suitable when Kafka runs on the development machine and the application connects from that same machine.

If the cluster has multiple bootstrap endpoints:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1.internal:9092,kafka-2.internal:9092,kafka-3.internal:9092
~~~

Spring Boot uses this shared configuration to create the producer, consumer, and admin components via auto-configuration. Therefore, make sure all addresses in the list belong to the same cluster and the same listener type appropriate for the application's network.

You can verify the loaded values by inspecting the effective configuration in the development environment or logging non-sensitive configuration at application startup. Do not write credentials or the entire SASL configuration to logs.

A minimal producer and consumer can use this configuration:

~~~java
@Service
public class OrderPublisher {

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    public OrderPublisher(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public CompletableFuture<SendResult<String, OrderCreatedEvent>> publish(
            OrderCreatedEvent event) {
        return kafkaTemplate.send(
                "orders.created",
                event.orderId(),
                event
        );
    }
}
~~~

~~~java
@Component
public class OrderListener {

    @KafkaListener(
            topics = "orders.created",
            groupId = "orders-processor"
    )
    public void consume(OrderCreatedEvent event) {
        // Process order event.
    }
}
~~~

KafkaTemplate and @KafkaListener do not need to pass bootstrap servers explicitly in each call. They use the ProducerFactory and ConsumerFactory configured from Spring Boot or the application's Spring Kafka configuration.

## 6. Connecting from a local machine, Docker, and Kubernetes

The bootstrap address must be chosen from the network perspective of the Kafka client process. The same Kafka broker may need to advertise different listeners for different connection environments.

### Application running directly on a local machine

If Kafka runs on a local machine and publishes port 9092 to the host, an application running directly on that machine can use:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
~~~

If the application runs on another machine, localhost will point to the machine running the application. In that case, you need to use the network-reachable hostname or IP of the Kafka machine.

### Application running in Docker Compose

Containers within the same Docker network typically contact each other using the service name. For example, an application container can use kafka:9092 instead of localhost:9092:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka:9092
~~~

Inside the application container, localhost refers to the application container itself. It does not automatically point to the Kafka container.

If both the application and Kafka need to be accessed from the host, the broker needs to configure corresponding internal and external listeners. Illustrative example:

~~~properties
listeners=INTERNAL://0.0.0.0:9092,HOST://0.0.0.0:29092
advertised.listeners=INTERNAL://kafka:9092,HOST://localhost:29092
listener.security.protocol.map=INTERNAL:PLAINTEXT,HOST:PLAINTEXT
inter.broker.listener.name=INTERNAL
~~~

The application container uses the INTERNAL listener and the host uses the HOST listener. Actual configuration also depends on the Kafka image, KRaft or ZooKeeper mode, port publishing setup, and environment variables of the image being used. Do not copy the listener lines alone while omitting the accompanying cluster configuration.

### Application running in Kubernetes

In Kubernetes, clients can use a Service DNS name to initiate the connection. However, the Kafka client still needs to reach the broker endpoints published in the metadata.

A common pattern is a headless Service or a discovery mechanism managed by a Kafka operator so that each broker has a stable hostname. If clients run outside the cluster, an external listener and corresponding endpoint must be configured for each broker.

With Kubernetes, check:

- Whether application pods and broker pods have network policies allowing communication.
- Whether the Service DNS resolves from the application's namespace.
- Whether each broker's port is properly exposed.
- Whether advertised.listeners publishes hostnames suitable for internal or external clients.
- Whether the TLS certificate has SANs matching the hostnames that clients connect to.

A shared bootstrap endpoint may work for the initial step, but each broker published in the metadata must still be reachable.

## 7. Security configuration for bootstrap connections

Bootstrap connections must also comply with the cluster's security mechanisms. When Kafka uses TLS or SASL, the client requires the corresponding security properties.

Example SASL_SSL configuration with SCRAM:

~~~yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS}
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: >-
        org.apache.kafka.common.security.scram.ScramLoginModule required
        username="<username>" password="<password>";
~~~

JAAS values should be supplied from a secret manager or the deployment environment's secret management mechanism. Do not place real usernames and passwords directly in configuration files committed to a repository.

With TLS, the client must trust the broker's certificate. If mutual TLS is used, the client also needs its corresponding certificate and private key. You must check hostname verification: the hostname in advertised.listeners must match the certificate's Subject Alternative Name according to the validation configuration.

Points to distinguish during diagnostics:

- A successful TCP connection does not mean the TLS handshake succeeded.
- A successful TLS handshake does not mean SASL authentication succeeded.
- Successful authentication does not mean the account has ACLs for the topic or consumer group.
- Having access to the bootstrap broker does not guarantee that every broker in the metadata allows the same connection and authentication.

If the cluster uses multiple listeners with different security mechanisms, the bootstrap endpoint and the endpoints returned in metadata must be compatible with the listener configuration used by the client.

## 8. Bootstrap redundancy and metadata refresh

Declaring multiple bootstrap servers enables the client to try another endpoint when the first one is unavailable. This list should contain independent addresses sufficient for the client to start discovering the cluster when a broker experiences an outage.

Example:

~~~yaml
spring:
  kafka:
    bootstrap-servers:
      - kafka-1.internal:9092
      - kafka-2.internal:9092
      - kafka-3.internal:9092
~~~

Spring Boot supports configuring bootstrap servers as a list or a comma-separated string. Choose a consistent representation according to the configuration file format and the Spring Boot version in use.

The Kafka client maintains a metadata cache and refreshes it automatically when needed. Several situations can trigger a metadata update:

- Metadata has exceeded the refresh interval configured on the client.
- The client encounters an error indicating that leader or partition metadata is stale.
- The broker returns errors such as NOT_LEADER_OR_FOLLOWER or LEADER_NOT_AVAILABLE.
- The cluster changes topology or a partition leader is re-elected.

The metadata.max.age.ms property controls the periodic metadata refresh cycle of the Kafka client. The reconnect.backoff.ms and reconnect.backoff.max.ms properties control the wait interval when reconnecting. Specific values should be tuned based on network stability and recovery requirements; do not set them too low, which would cause the client to generate excessive requests or repeated reconnects while the cluster is experiencing issues.

Multiple bootstrap endpoints increase the likelihood of initiating a connection, but they do not replace replication factor, ISR, or leader failover mechanisms. Those mechanisms belong to the Kafka cluster.

## 9. Connecting to multiple Kafka clusters

An application may need to connect to multiple Kafka clusters, such as an internal cluster and a partner cluster, or clusters serving different data domains.

Default Spring Boot configuration typically suits a single shared cluster for producer, consumer, and admin. If multiple clusters are needed, you must separately declare connection components such as ProducerFactory, ConsumerFactory, KafkaTemplate, listener container factory, or AdminClient with their own bootstrap servers and security configuration.

Example of creating an AdminClient for a secondary cluster:

~~~java
@Bean(destroyMethod = "close")
AdminClient auditAdminClient(
        @Value("${app.kafka.audit.bootstrap-servers}") String servers) {

    Map<String, Object> configs = new HashMap<>();
    configs.put(
            AdminClientConfig.BOOTSTRAP_SERVERS_CONFIG,
            servers
    );

    return AdminClient.create(configs);
}
~~~

Corresponding configuration:

~~~yaml
app:
  kafka:
    audit:
      bootstrap-servers: audit-kafka-1:9092,audit-kafka-2:9092
~~~

The snippet only illustrates a separate AdminClient for the secondary cluster. If sending or receiving records on this cluster, you must create the corresponding ProducerFactory or ConsumerFactory and ensure listeners use the correct container factory. Do not mistakenly use the default cluster's KafkaTemplate or consumer factory.

Each cluster can have:

- A different list of bootstrap servers.
- Different internal or external listeners.
- Separate SASL/TLS mechanisms and credentials.
- Separate topics, ACLs, consumer groups, and retention policies.

You should name beans and configurations clearly by purpose, such as primaryKafkaTemplate and auditKafkaTemplate, to avoid mixing up clusters when injecting dependencies.

## 10. Diagnosing connection and metadata discovery errors

When a client cannot connect, analyze layer by layer instead of randomly changing bootstrap servers.

| Symptom | Possible Cause | How to Check |
|---|---|---|
| UnknownHostException | DNS cannot resolve the hostname | Check hostname resolution from the exact environment running the application. |
| Connection refused | Broker is not listening on the port or port is not published | Check listeners, port mapping, and broker status. |
| Connection timed out | Firewall, route, or network policy blocks the connection | Check the network path from the container/pod/host to the broker. |
| TLS handshake failed | Mismatched certificate, truststore, hostname, or protocol | Check certificate chain, SANs, and TLS configuration. |
| SASL authentication failed | Incorrect mechanism, username, password, or JAAS config | Check secrets and the listener's SASL mechanism. |
| Bootstrap connects but other brokers are unreachable | advertised.listeners returns an unsuitable hostname or port | Read metadata and check every advertised broker endpoint. |
| Not authorized | Account authenticated successfully but lacks ACLs | Check permissions on topic, group, or cluster resources. |
| LEADER_NOT_AVAILABLE | Partition has no available leader yet or cluster is recovering | Check partition, controller, and broker status. |
| NOT_LEADER_OR_FOLLOWER | Stale metadata or leader recently changed | Let the client refresh metadata; check cluster health if the error persists. |

A useful diagnostic workflow:

1. Confirm the actual bootstrap servers value that the application is using.
2. Resolve DNS hostnames from the exact machine, container, or pod running the application.
3. Test TCP connectivity to each bootstrap endpoint.
4. Verify TLS/SASL if the cluster is secured.
5. Fetch metadata from the bootstrap endpoint.
6. Check each hostname and port in the metadata.
7. Confirm partition leaders, brokers, and ACLs.
8. Read client logs to determine at which step the failure occurred.

You can use a CLI tool to inspect metadata:

~~~bash
kcat -b kafka-1.internal:9092,kafka-2.internal:9092 -L
~~~

The command above requires kcat to be installed and properly configured with security settings if the cluster requires authentication. The metadata output shows the brokers and partitions visible to the client. If metadata returns internal hostnames unreachable from the machine running kcat, you need to fix advertised.listeners or select an appropriate listener.

You can use kafka-broker-api-versions.sh to check connectivity and API versions:

~~~bash
kafka-broker-api-versions.sh --bootstrap-server kafka-1.internal:9092
~~~

This is a useful check for the bootstrap endpoint; you still need to check the broker endpoints returned in metadata to confirm the full connection path.

## 11. Testing bootstrap servers configuration

Connection testing should verify both bootstrap connectivity and broker discovery capability. A test that only checks a socket to one address does not prove the client can send records to a partition leader or join a consumer group.

Testing layers:

| Test Type | Objective |
|---|---|
| Configuration test | Ensure bootstrap servers are loaded properly by profile and environment variables. |
| Connectivity test | Client establishes a connection and fetches metadata from the cluster. |
| Producer integration test | Send records to a topic and receive broker acknowledgment. |
| Consumer integration test | Consumer joins a group, receives records, and handles partition assignment. |
| Multi-broker test | Metadata contains multiple brokers and the client reaches the respective leaders. |
| Security test | TLS/SASL works; wrong credentials or missing ACLs are detected clearly. |
| Network failure test | One bootstrap endpoint loses connectivity while the client can still discover the cluster via remaining endpoints. |

With Testcontainers, obtain the connection address from the container rather than hardcoding localhost. Example of configuring a Spring test with DynamicPropertySource:

~~~java
@DynamicPropertySource
static void kafkaProperties(DynamicPropertyRegistry registry) {
    registry.add(
            "spring.kafka.bootstrap-servers",
            kafkaContainer::getBootstrapServers
    );
}
~~~

The kafkaContainer variable must be initialized and managed by a test fixture appropriate for the project's Testcontainers version and Kafka image. In a multi-broker environment, tests should verify that metadata contains the required brokers and send records to partitions with different leaders.

Do not use a fixed sleep to wait for the broker to be ready. Use health checks or wait on connection/metadata conditions with an explicit timeout. If testing network failures, bound the duration and restore the network after the test so other tests are not affected.

## 12. Connection operations checklist

When deploying Spring Kafka, verify the following points:

- Bootstrap servers point to the right cluster and the right listener for the application environment.
- Multiple independent bootstrap endpoints are present if the infrastructure requires redundancy.
- Every broker returned in metadata has a reachable hostname and port.
- advertised.listeners matches the client's network.
- DNS, firewalls, routes, and Kubernetes NetworkPolicies allow connections to each broker.
- TLS certificates match the hostnames and are properly trusted.
- SASL mechanisms, credentials, and ACLs are configured following the principle of least privilege.
- The application does not log secrets.
- Timeouts and reconnect backoffs match expected recovery times.
- Logs contain sufficient information to identify the broker and connection error, without containing authentication credentials.
- Health/readiness checks accurately reflect Kafka availability according to business requirements.

When changing a broker's hostname, port, listener, or certificate, assess the impact on all clients using the cluster. Changing advertised.listeners can disrupt clients if DNS or firewalls are not updated in sync.

## 13. Comprehensive exercise: connecting Spring Kafka to a multi-broker cluster

Build a hands-on environment with a Spring Boot application and a Kafka cluster with at least two brokers if the environment permits.

Requirements:

1. Configure bootstrap servers with multiple endpoints.
2. Start the application and record which broker was used for the initial connection.
3. Use AdminClient or kcat to fetch metadata and list the brokers.
4. Create a topic with multiple partitions and identify the leader of each partition.
5. Send OrderCreatedEvent using KafkaTemplate with multiple keys so records are distributed across partitions.
6. Use @KafkaListener to receive records and log the topic, partition, offset, and key.
7. Stop one bootstrap endpoint and verify the client's ability to connect through the remaining endpoint.
8. Intentionally misconfigure advertised.listeners in a test environment to observe metadata discovery errors.
9. Fix the endpoint, re-check DNS, ports, and metadata.
10. Try enabling TLS or SASL if the environment supports it, then verify authentication and ACLs.
11. Write an integration test using the bootstrap address provided by a test container.
12. Document the local, Docker, or Kubernetes configuration so other team members can reproduce the connection.

After the exercise, you should be able to explain why connecting to the bootstrap server alone is not enough to guarantee an application can send and receive records, and why advertised.listeners must be designed around the network location of the Kafka client.

## 14. Learning sequence and completion criteria

| Stage | Core Content | Self-Check Criteria |
|---|---|---|
| 1. Bootstrap | Host, port, endpoint list | Correctly configure one or more bootstrap servers. |
| 2. Metadata | Broker, topic, partition, leader, ISR | Read metadata and identify the leader for a partition. |
| 3. Listener | listeners and advertised.listeners | Explain the difference between bind addresses and advertised addresses. |
| 4. Spring Boot | spring.kafka.bootstrap-servers | Producer, consumer, and admin use the right cluster. |
| 5. Network | Local, Docker, Kubernetes, DNS, firewall | Client can reach every broker in metadata. |
| 6. Security | TLS, SASL, ACL | Connect and authenticate to the right listener. |
| 7. Reliability | Multiple bootstrap endpoints, reconnect, metadata refresh | Distinguish bootstrap redundancy from broker/replica failover. |
| 8. Testing | Testcontainers, CLI, metadata checks | Have tests covering sending, receiving, and broker discovery. |

The lesson is complete when you can configure bootstrap servers in Spring Boot, describe the metadata discovery process, design advertised.listeners suitable for the deployment network, and diagnose cases where bootstrap connects successfully while other brokers remain unreachable.

A Kafka client needs a starting point to discover the cluster, then relies on metadata and advertised broker addresses to route requests. When you understand the relationship between bootstrap.servers, listeners, advertised.listeners, DNS, and networking, you can configure Spring Kafka connections more reliably across local, container, and production environments.

