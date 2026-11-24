# Configuring a Local Broker with Docker Compose

A Spring Kafka application needs to connect to a running Kafka broker. When developing on a personal machine, Docker Compose lets you start a broker along with its network and storage configuration in a single command. This approach creates a reproducible environment across team members, convenient for experimenting with `KafkaTemplate`, `@KafkaListener`, topics, partitions, consumer groups, and error scenarios.

This lesson sets up a single-node Kafka broker in KRaft mode using the official `apache/kafka` image. The configuration targets local development and integration testing. It uses plaintext, a single broker, and a replication factor of one, so it does not provide high availability or data protection like a production cluster.

## 1. Preparing Docker and Docker Compose

Docker Engine or Docker Desktop with Docker Compose v2 support is required. Check the following commands in a terminal:

```bash
docker --version
docker compose version
```

The official Kafka image requires Docker version 20.10.4 or later to avoid certain write-permission errors when the container initializes its configuration. Use a supported and up-to-date Docker Desktop or Docker Engine.

Create a dedicated directory for local infrastructure, for example:

```text
local-infrastructure/
└── kafka/
    └── compose.yaml
```

Place the Compose file in the `kafka` directory so the `docker compose` commands below are run from the right location.

## 2. Understanding KRaft and Node Roles

Modern Kafka can run in KRaft mode, using a controller quorum to manage metadata without needing ZooKeeper. In a simple local setup, a single Kafka process can simultaneously hold two roles:

- **broker:** receives requests from producers and consumers, stores partition logs, and serves reads/writes.
- **controller:** participates in managing metadata and cluster state.

When `process.roles` includes both `broker,controller`, the node runs in combined mode. This is a convenient configuration for a personal machine; production clusters typically separate controllers and brokers according to architecture, node count, and operational requirements.

One point to understand before writing Compose is that Kafka has two distinct connection addresses:

1. `listeners` specifies the addresses and ports the broker binds to in order to accept connections.
2. `advertised.listeners` specifies the addresses the broker returns to clients in metadata. Clients use these addresses for subsequent connections.

Because applications may run directly on the host machine or inside another container, a single address is usually unsuitable for both cases. The configuration below uses two listeners:

| Listener | Advertised Address | Used by Clients |
| --- | --- | --- |
| `PLAINTEXT_HOST` | `localhost:9092` | Applications running directly on the development host |
| `PLAINTEXT` | `broker:19092` | Applications running in the same Docker Compose network |
| `CONTROLLER` | `broker:29093` | Internal KRaft controller communication |

Do not configure Spring Boot inside a container to point to `localhost:9092`: inside a container, `localhost` is the application container itself. When both containers are on the same Compose network, use the service name `broker` and internal port `19092`.

## 3. Creating the `compose.yaml` File

Create `compose.yaml` with the following contents:

```yaml
services:
  broker:
    image: apache/kafka:4.4.0
    hostname: broker
    ports:
      - "9092:9092"
    environment:
      KAFKA_NODE_ID: 1
      KAFKA_PROCESS_ROLES: "broker,controller"
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: "CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT,PLAINTEXT_HOST:PLAINTEXT"
      KAFKA_LISTENERS: "CONTROLLER://:29093,PLAINTEXT_HOST://:9092,PLAINTEXT://:19092"
      KAFKA_ADVERTISED_LISTENERS: "PLAINTEXT_HOST://localhost:9092,PLAINTEXT://broker:19092"
      KAFKA_CONTROLLER_QUORUM_VOTERS: "1@broker:29093"
      KAFKA_CONTROLLER_LISTENER_NAMES: "CONTROLLER"
      KAFKA_INTER_BROKER_LISTENER_NAME: "PLAINTEXT"
      CLUSTER_ID: "4L6g3nShT-eMCtK--X86sw"
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
      KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS: 0
      KAFKA_TRANSACTION_STATE_LOG_MIN_ISR: 1
      KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR: 1
      KAFKA_SHARE_COORDINATOR_STATE_TOPIC_REPLICATION_FACTOR: 1
      KAFKA_SHARE_COORDINATOR_STATE_TOPIC_MIN_ISR: 1
      KAFKA_LOG_DIRS: "/tmp/kraft-combined-logs"
    volumes:
      - kafka-data:/tmp/kraft-combined-logs
    healthcheck:
      test:
        - CMD-SHELL
        - "/opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list >/dev/null 2>&1"
      interval: 10s
      timeout: 5s
      retries: 12
      start_period: 20s
    restart: unless-stopped

volumes:
  kafka-data:
```

The `apache/kafka:4.4.0` image is the official JVM-based Apache Kafka image. Pin a specific tag so subsequent runs use the same version; when upgrading the tag, read release notes and re-run integration tests before using it in a project.

### Key Configuration Explanations

| Property | Meaning |
| --- | --- |
| `KAFKA_NODE_ID` | Unique ID of the node within the cluster |
| `KAFKA_PROCESS_ROLES` | Configures the node to take both broker and controller roles |
| `KAFKA_LISTENERS` | Addresses/ports Kafka binds to inside the container |
| `KAFKA_ADVERTISED_LISTENERS` | Addresses the broker advertises to clients after bootstrap |
| `KAFKA_LISTENER_SECURITY_PROTOCOL_MAP` | Maps listener names to security protocols |
| `KAFKA_CONTROLLER_QUORUM_VOTERS` | List of controller nodes and quorum addresses |
| `KAFKA_CONTROLLER_LISTENER_NAMES` | Listener used for controller communication |
| `KAFKA_INTER_BROKER_LISTENER_NAME` | Listener used for broker-to-broker communication |
| `CLUSTER_ID` | KRaft cluster identifier used when formatting storage |
| `KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR` | Replication factor for the internal topic storing consumer group offsets |
| `KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR` | Replication factor for the topic storing transaction state |
| `KAFKA_LOG_DIRS` | Directory storing Kafka log data |
| `kafka-data` | Named volume so data persists across container recreations |

Because there is only one broker, internal topics require a replication factor of one. This choice allows a single-node broker to start; it does not provide broker fault tolerance. The `KAFKA_SHARE_COORDINATOR_*` settings are also set to one to suit a single-node environment when using share group/coordinator features in newer Kafka versions.

`CLUSTER_ID` is a sample ID for the learning environment. Keep this value stable when continuing to reuse an already formatted volume. If creating a new cluster with empty storage, generate a new valid ID or use a sample ID for an independent local environment; do not arbitrarily change the ID while old cluster data still exists.

## 4. Starting and Verifying the Broker

From the directory containing `compose.yaml`, validate the Compose syntax and configuration:

```bash
docker compose config
```

Start the broker in the background:

```bash
docker compose up -d
```

Check status:

```bash
docker compose ps
```

Follow logs if the broker is not healthy or fails to start:

```bash
docker compose logs -f broker
```

The healthcheck in the Compose file invokes the Kafka CLI to check whether the broker is accepting metadata requests on the host listener. Once the status transitions to `healthy`, you can start connecting from the application. If the healthcheck fails, read the logs to find causes such as an occupied port, misconfigured listeners, volume write-permission errors, or storage formatting failures.

Check the broker using the Kafka CLI inside the container:

```bash
docker compose exec broker /opt/kafka/bin/kafka-broker-api-versions.sh --bootstrap-server broker:19092
```

If the command returns broker info and API versions, the internal listener is serving connections. You can use the host listener from the development machine via `localhost:9092`.

## 5. Creating Topics and Testing Send/Receive

Create the `orders.created` topic with three partitions and a replication factor of one:

```bash
docker compose exec broker /opt/kafka/bin/kafka-topics.sh --bootstrap-server broker:19092 --create --topic orders.created --partitions 3 --replication-factor 1
```

List topics:

```bash
docker compose exec broker /opt/kafka/bin/kafka-topics.sh --bootstrap-server broker:19092 --list
```

Inspect topic partitions and metadata:

```bash
docker compose exec broker /opt/kafka/bin/kafka-topics.sh --bootstrap-server broker:19092 --describe --topic orders.created
```

Open one terminal to consume data from the beginning of the topic:

```bash
docker compose exec broker /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server broker:19092 --topic orders.created --from-beginning
```

Open a second terminal to send data:

```bash
docker compose exec -it broker /opt/kafka/bin/kafka-console-producer.sh --bootstrap-server broker:19092 --topic orders.created
```

Enter a few lines, each line being one message, then observe the consumer terminal. Press `Ctrl+C` to stop the producer or consumer. These commands use the Docker network's internal listener; the Kafka CLI inside the container can resolve the name `broker`.

## 6. Connecting the Spring Boot Application

### Application Running Directly on the Host Machine

If running Spring Boot from an IDE or Maven/Gradle on the development machine, use the host listener:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    consumer:
      group-id: order-service
      auto-offset-reset: earliest
```

`localhost:9092` is the host port mapped to the broker's `PLAINTEXT_HOST` listener. If port 9092 is already used by another process, update the port mapping and advertised listener consistently, then update `bootstrap-servers`.

### Spring Boot Application Also Running in Docker Compose

When the application is in the same Compose project/network, use the service name and internal listener:

```yaml
spring:
  kafka:
    bootstrap-servers: broker:19092
    consumer:
      group-id: order-service
      auto-offset-reset: earliest
```

If configuring via environment variables on the application container, the corresponding property is:

```yaml
environment:
  SPRING_KAFKA_BOOTSTRAP_SERVERS: broker:19092
```

The application must join the same Docker network as the `broker` service. You can declare `depends_on` to coordinate startup order; to wait until the broker is ready, use the `service_healthy` condition with a healthcheck as in the example. Using `depends_on` in its default list form alone does not guarantee the broker is accepting connections when the application starts.

## 7. Stopping, Restarting, and Managing Data

Stop the container while keeping the volume:

```bash
docker compose down
```

Restart:

```bash
docker compose up -d
```

Because `kafka-data` is a named volume, topic data and KRaft metadata persist across normal `down` and `up` cycles. This avoids having to recreate topics and resend data after each environment stop.

If you want to delete all local data and create a clean cluster, use:

```bash
docker compose down -v
```

The `-v` flag removes named volumes managed by Compose, so all topics, records, offsets, and metadata stored in the volume will be lost. Run this only when intentionally resetting the learning environment.

## 8. Troubleshooting Common Errors

| Symptom | Possible Cause | How to Check/Resolve |
| --- | --- | --- |
| Container exits right after start | Missing or invalid KRaft configuration, volume not writable | Check `docker compose logs broker`; inspect node ID, roles, quorum voters, and directory permissions |
| Host connects initially but then gets metadata errors | Advertised listener returns a hostname unresolvable by the client | Use `localhost:9092` for host and `broker:19092` for containers |
| Spring Boot in a container reports it cannot resolve `localhost` | Application is pointing to the Spring Boot container itself | Change bootstrap server to `broker:19092` |
| Port 9092 is already in use | Another Kafka broker or process is occupying the port | Stop that process or change the host port and advertised listener consistently |
| Cannot create topic with replication factor three | Local cluster has only one broker | Use replication factor one for single-node exercises |
| Data disappears after recreating the container | Named volume not mounted to `KAFKA_LOG_DIRS` or volume was deleted | Verify `kafka-data` mapping and avoid `docker compose down -v` if you want to keep data |
| Broker remains unhealthy | Broker is not ready yet or healthcheck uses an inactive listener | Check logs and run Kafka CLI manually to distinguish broker failure from healthcheck failure |

## 9. Limitations of the Local Environment

The configuration above uses one node in combined mode, plaintext, and a replication factor of one. It is suitable for learning APIs, trying out listeners, observing partitions, offsets, and consumer groups, and running simple integration tests. It does not fully simulate a production Kafka cluster.

For real deployments, design multiple brokers and controllers following an appropriate KRaft architecture, configure replication factor and `min.insync.replicas`, SASL authentication, TLS encryption, ACL authorization, monitoring, backup/restore, disk capacity, and upgrade procedures. Do not expose a local plaintext listener to public networks or use this configuration as-is for critical data.

## 10. Conclusion

Docker Compose helps create a consistent local Kafka broker for developing Spring Kafka applications. The single-node KRaft setup uses the official Apache Kafka image, a named volume to retain data, and two listeners to support both applications running on the host and applications running inside a Docker network.

When debugging connections, check both the addresses the broker binds to (`listeners`) and the addresses the broker advertises (`advertised.listeners`). After the broker is healthy, create a topic, test sending/receiving with the Kafka CLI, and then configure `spring.kafka.bootstrap-servers` according to where the application runs. Always remember this is a single-node local environment; production clusters require dedicated configuration and operations.

## References

- [Apache Kafka — Docker](https://kafka.apache.org/documentation/#docker)
- [Apache Kafka — Docker Compose single-node example](https://github.com/apache/kafka/blob/trunk/docker/examples/docker-compose-files/single-node/plaintext/docker-compose.yml)
- [Apache Kafka — Docker image examples](https://github.com/apache/kafka/blob/trunk/docker/examples/README.md)
