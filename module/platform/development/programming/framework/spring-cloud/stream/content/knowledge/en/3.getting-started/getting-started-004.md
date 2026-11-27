# Preparing Local Kafka or RabbitMQ with Docker Compose

To start developing a Spring Cloud Stream application, your team needs a broker that starts quickly, is easy to inspect, and keeps its data separate from production environments. Docker Compose lets you describe the broker along with ports, credentials, volumes, and health checks in a single file. Once started, a Spring application running on the development machine can connect via the mapped port; an application running inside a container uses the service name on the Compose network.

This lesson walks through preparing a single-node Kafka broker running in KRaft mode or a single-node RabbitMQ broker with the management UI. Choose the broker that matches your exercise. A single-node setup is enough to learn bindings, consumer groups, queues, partitions, and event flow testing; it does not fully replicate the high availability or security of a production cluster.

## 1. Preparing the Environment

Install Docker Desktop or Docker Engine with Docker Compose v2 support. On Windows, Docker Desktop typically runs with the WSL 2 backend. Open a terminal in your project or exercise directory and check:

```bash
docker version
docker compose version
```

Both commands should return valid version information. If `docker version` only displays the Client section and reports that it cannot connect to the daemon, start Docker Desktop or Docker Engine before continuing.

Create a working directory, for example `local-broker`, and place the corresponding Compose file inside it. You can save the two configurations under separate filenames to switch brokers without editing the file each time:

- `compose.kafka.yaml` for Kafka.
- `compose.rabbitmq.yaml` for RabbitMQ.

Validate the Compose structure before starting by running `docker compose -f compose.kafka.yaml config` or `docker compose -f compose.rabbitmq.yaml config`. The `config` command parses and displays the configuration after variable interpolation; it does not create containers yet.

## 2. Starting Local Kafka

Kafka stores messages in topics and splits topics into partitions. Consumer groups coordinate partition assignment across consumers in the same group. The configuration below uses a single node acting as both broker and controller in KRaft mode, without ZooKeeper. Two listeners separate connections from the development machine and connections from other containers on the same Compose network.

Create the file `compose.kafka.yaml`:

```yaml
services:
  kafka:
    image: apache/kafka:4.0.0
    hostname: kafka
    ports:
      - "9092:9092"
    environment:
      KAFKA_NODE_ID: 1
      KAFKA_PROCESS_ROLES: broker,controller
      KAFKA_LISTENERS: EXTERNAL://:9092,INTERNAL://:29092,CONTROLLER://:9093
      KAFKA_ADVERTISED_LISTENERS: EXTERNAL://localhost:9092,INTERNAL://kafka:29092
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: EXTERNAL:PLAINTEXT,INTERNAL:PLAINTEXT,CONTROLLER:PLAINTEXT
      KAFKA_INTER_BROKER_LISTENER_NAME: INTERNAL
      KAFKA_CONTROLLER_LISTENER_NAMES: CONTROLLER
      KAFKA_CONTROLLER_QUORUM_VOTERS: 1@kafka:9093
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
      KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR: 1
      KAFKA_TRANSACTION_STATE_LOG_MIN_ISR: 1
      KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS: 0
      KAFKA_NUM_PARTITIONS: 3
      KAFKA_LOG_DIRS: /var/lib/kafka/data
    volumes:
      - kafka-data:/var/lib/kafka/data
    healthcheck:
      test: ["CMD-SHELL", "/opt/kafka/bin/kafka-broker-api-versions.sh --bootstrap-server localhost:9092 >/dev/null 2>&1"]
      interval: 10s
      timeout: 5s
      retries: 12
      start_period: 20s

volumes:
  kafka-data:
```

Notable settings:

- `KAFKA_PROCESS_ROLES` allows the single process to act as both broker and controller. This is a compact setup for a learning environment.
- `EXTERNAL` advertises `localhost:9092` so applications running directly on the development machine can connect.
- `INTERNAL` advertises `kafka:29092` so other containers can use the `kafka` service DNS on the Compose network.
- `CONTROLLER` uses port 9093 for internal controller communication; there is no need to map this port to the host machine.
- Replication factors of `1` are appropriate for a single broker. They do not provide fault tolerance if the node stops.
- The `kafka-data` volume preserves broker data across container stops and recreations. `KAFKA_LOG_DIRS` points to the exact mounted directory.
- The health check calls the Kafka broker API to confirm the broker is responding, rather than merely checking that the container process is still running.

> **Note on connection addresses:** `localhost` in `KAFKA_ADVERTISED_LISTENERS` is for clients running on the host machine. Clients running inside containers must use `kafka:29092`. Kafka returns the advertised broker addresses in metadata; therefore, misconfiguring advertised listeners can allow initial bootstrap connection while failing when accessing topics or partitions.

Start and check the status:

```bash
docker compose -f compose.kafka.yaml config
docker compose -f compose.kafka.yaml up -d
docker compose -f compose.kafka.yaml ps
docker compose -f compose.kafka.yaml logs -f kafka
```

Wait for the health status to become `healthy`. Press `Ctrl+C` to exit log following mode; the container continues running in the background. You can list existing topics with:

```bash
docker compose -f compose.kafka.yaml exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list
```

### 2.1. Creating a Topic and Sending a Test Message

Create the `orders` topic with three partitions and a replication factor of one:

```bash
docker compose -f compose.kafka.yaml exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --create --topic orders --partitions 3 --replication-factor 1
docker compose -f compose.kafka.yaml exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic orders
```

Open a first terminal to run a consumer reading from the beginning of the topic:

```bash
docker compose -f compose.kafka.yaml exec kafka /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic orders --from-beginning
```

Open a second terminal to run a producer:

```bash
docker compose -f compose.kafka.yaml exec kafka /opt/kafka/bin/kafka-console-producer.sh --bootstrap-server localhost:9092 --topic orders
```

Enter a line of JSON, press Enter, and observe that line appear in the consumer terminal:

```json
{"eventId":"evt-001","orderId":"ord-100","status":"CREATED"}
```

Press `Ctrl+C` in each terminal to exit the interactive command. The `--describe` command shows the partition count and current leader; it helps confirm that the topic was created with the expected configuration.

## 3. Starting Local RabbitMQ

RabbitMQ is commonly used with a model where an exchange routes messages to queues. Consumers receive messages from queues and confirm processing with acknowledgements. The Spring Cloud Stream Rabbit binder maps destinations to exchanges and consumer groups to queues bound to those exchanges.

Create the file `compose.rabbitmq.yaml`:

```yaml
services:
  rabbitmq:
    image: rabbitmq:4.1-management
    hostname: rabbitmq
    ports:
      - "5672:5672"
      - "15672:15672"
    environment:
      RABBITMQ_DEFAULT_USER: stream
      RABBITMQ_DEFAULT_PASS: stream-local
      RABBITMQ_DEFAULT_VHOST: /
    volumes:
      - rabbitmq-data:/var/lib/rabbitmq
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "-q", "ping"]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 15s

volumes:
  rabbitmq-data:
```

The two mapped ports serve different purposes:

- `5672` is the AMQP port for Spring applications to connect.
- `15672` is the web management UI provided by the `management` image.

The `stream` account and `stream-local` password are only for local examples. Creating a dedicated user avoids running into limitations of the default `guest` account, which is typically only allowed to connect from RabbitMQ's own loopback interface. Do not use this sample password in shared or production environments.

The variables `RABBITMQ_DEFAULT_USER`, `RABBITMQ_DEFAULT_PASS`, and `RABBITMQ_DEFAULT_VHOST` are used when RabbitMQ initializes its database for the first time. If the named volume already has data from a previous run, changing the variables in Compose will not automatically update the existing account; you must update the user inside RabbitMQ or recreate the volume when deleting data is acceptable.

Start and check:

```bash
docker compose -f compose.rabbitmq.yaml config
docker compose -f compose.rabbitmq.yaml up -d
docker compose -f compose.rabbitmq.yaml ps
docker compose -f compose.rabbitmq.yaml logs -f rabbitmq
```

Wait for the health status to become `healthy`. Press `Ctrl+C` to exit log following mode; the container continues running in the background. Open `http://localhost:15672` in your browser and log in with:

| Field | Value |
|---|---|
| Username | `stream` |
| Password | `stream-local` |

The management UI lets you view connections, exchanges, queues, ready message counts, and unacknowledged message counts. You can inspect queues from the terminal:

```bash
docker compose -f compose.rabbitmq.yaml exec rabbitmq rabbitmqctl list_queues name messages_ready messages_unacknowledged
```

When the Spring Cloud Stream application initializes a consumer binding, the Rabbit binder can automatically declare the required exchange, queue, and binding if the user has sufficient permissions. Afterward, the queue name and message state will appear in the management UI or in the `list_queues` output.

## 4. Connecting the Spring Cloud Stream Application

The application needs the starter for the corresponding binder. Use a Spring Cloud BOM compatible with your project's Spring Boot version to manage the Spring Cloud Stream and binder versions; do not pick separate library versions independently.

With Gradle, choose one dependency:

```kotlin
// Used when connecting to Kafka
implementation("org.springframework.cloud:spring-cloud-starter-stream-kafka")

// Or used when connecting to RabbitMQ
implementation("org.springframework.cloud:spring-cloud-starter-stream-rabbit")
```

There is no need to declare both starters if the application only exercises one broker. If the application needs to test multiple binders in the same exercise, manage dependencies and configurations explicitly to avoid initializing the wrong binder.

Example of a consumer receiving order-created events:

```java
@Bean
public Consumer<OrderCreated> processOrder(InventoryService inventory) {
    return event -> inventory.reserve(event.orderId(), event.items());
}
```

Declare the common configuration in `application.yml`:

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: inventory
```

The name `processOrder-in-0` is the first input binding of the `processOrder` function bean. `destination` is the logical topic or exchange named `orders`. `group` identifies the processing group. With Kafka, instances sharing the same group split the assigned partitions; with the Rabbit binder, `group` is used to create a queue dedicated to that consumer group. Another group can receive a copy of the event via its own queue in RabbitMQ or its own consumer group in Kafka.

### 4.1. Connecting to Kafka

When the application runs directly from an IDE or terminal on the development machine, configure the binder to use the external listener:

```yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          brokers: localhost:9092
```

When the application runs inside a container on the same Compose network as Kafka, change the address to:

```yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          brokers: kafka:29092
```

Do not use `localhost:9092` inside the application container: `localhost` there refers to the application container itself. Use the service name `kafka` and the internal listener `29092`.

### 4.2. Connecting to RabbitMQ

For an application running on the development machine, configure the AMQP connection:

```yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: stream
    password: stream-local
    virtual-host: /
```

If the application runs in a container on the same Compose network, set `host: rabbitmq`. Keep the port, user, password, and virtual host matching the Compose file.

You can split the configuration into `kafka` and `rabbit` profiles to switch brokers via `SPRING_PROFILES_ACTIVE` while keeping the function definition and common bindings unchanged. This lets the team compare how the binders map the same business flow onto the two brokers.

## 5. Running the Application in Docker Compose

When the broker and the application are in the same Compose file or on the same Compose network, the application can use the service name as its hostname. Example addition for the application service when using Kafka:

```yaml
services:
  order-service:
    build: .
    environment:
      SPRING_PROFILES_ACTIVE: kafka
    depends_on:
      kafka:
        condition: service_healthy
```

For RabbitMQ, replace the dependency with the `rabbitmq` service and use the `rabbit` profile. Declaring `depends_on` with `condition: service_healthy` makes Compose wait until the broker's health check passes before starting the application. If you only use `depends_on` without a health condition, Compose only orders startup; it does not guarantee the broker is ready to accept connections.

If the application is launched separately from an IDE, there is no need to add the application service to the Compose file. Simply wait for the broker to become healthy and then run the application with the matching host configuration.

## 6. Verifying the Connection from the Application

Once the broker is ready, start the application and observe the binding initialization logs. Check the following signs:

1. The application loads the expected profile and broker address.
2. The binder creates or connects to the destination.
3. The consumer binding is initialized with the right group name.
4. Send a test event to the topic or exchange and confirm the `processOrder` function receives the payload.
5. Check consumer group/partition info on Kafka or queue/consumer info on RabbitMQ.

With Kafka, you can inspect the topic again using `kafka-topics.sh --describe`. With RabbitMQ, open the management UI to view exchanges, queues, bindings, and message counters. If using a separate producer application, confirm both the number of published messages and the number of messages processed by the consumer.

A successful broker connection does not prove the entire event contract is right. Also verify payload types, field names, headers, and schema versions. In subsequent exercises, test scenarios where the consumer stops, the broker restarts, and messages are redelivered to observe retry, acknowledgement, and idempotency behavior.

## 7. Common Troubleshooting

| Symptom | Possible cause | How to check or fix |
|---|---|---|
| `docker compose` cannot connect to the daemon | Docker Desktop/Engine is not running | Start the daemon and re-run `docker version` |
| Port 9092, 5672, or 15672 is already in use | Another process or container is occupying the port | Stop the conflicting service or change the host port on the left side of the `HOST:CONTAINER` mapping |
| Application on the host cannot connect to Kafka | Broker is not healthy yet or the external listener does not advertise the right address | View `docker compose logs kafka`, check `EXTERNAL://localhost:9092` and health status |
| Application in container fails to resolve `localhost` | Using the host machine's address instead of service DNS | Use `kafka:29092` or `rabbitmq:5672` from the Compose network |
| Kafka bootstrap connects, but partition access times out | Broker advertises an address unreachable from the client | Check `KAFKA_ADVERTISED_LISTENERS` and pick the right listener for the client's location |
| RabbitMQ reports access refused | Wrong user/password or virtual host; possibly using `guest` from another host | Check `RABBITMQ_DEFAULT_*` variables and `spring.rabbitmq.*` configuration |
| Application starts before broker is ready | Only using `depends_on` ordering without waiting for health | Add a health check and `condition: service_healthy`, along with appropriate connection retry configuration |
| Consumer receives no messages | Wrong destination/group, queue missing, or payload cannot be decoded | Check bindings, topic/queue, binder logs, and payload format |

When you need to inspect broker logs:

```bash
docker compose -f compose.kafka.yaml logs --tail=100 kafka
docker compose -f compose.rabbitmq.yaml logs --tail=100 rabbitmq
```

Only run the command for the Compose file currently in use. Do not change multiple connection properties at once before identifying whether the issue lies in the address, port, credentials, or broker state.

## 8. Stopping the Environment and Managing Data

Stop and remove containers and networks created by Compose:

```bash
docker compose -f compose.kafka.yaml down
docker compose -f compose.rabbitmq.yaml down
```

Named volumes are preserved after `down`, so topics, queues, and broker data may remain when restarting. When you want to delete all exercise data and create a clean environment, run `down -v` for the corresponding broker:

```bash
docker compose -f compose.kafka.yaml down -v
docker compose -f compose.rabbitmq.yaml down -v
```

The `down -v` command deletes volumes declared in the corresponding file and removes local broker data. Only use it when you are sure you do not need to keep existing topics, queues, or messages.

## 9. Scope and Usage Principles

The configurations in this lesson are intended for learning on a personal machine: Kafka has a single node, replication factor of one, and a PLAINTEXT listener; RabbitMQ uses a sample username and password. This environment does not provide sufficient security, redundancy, or monitoring for production. For real deployments, configure TLS, authentication and authorization, network policies, appropriate replication or clustering, backups, alerting, resource limits, and secret management.

In Spring Cloud Stream, binders let applications declare bindings under a unified functional model. However, Kafka's topics/partitions/consumer groups and RabbitMQ's exchanges/queues/acknowledgements still retain their own semantics. Starting with a local broker, confirming connectivity from the exact location where the application runs, and verifying the publish-consume flow builds a solid foundation for learning schemas, retry/DLQ, testing, and delivery guarantees in the next steps.
