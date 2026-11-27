# Persisting State with MessageStore

## 1. Practice Objectives

In the **Comprehensive Practice** chapter of **SPRING_INTEGRATION_CORE**, this lesson builds a flow that receives order events, persists in-progress message groups, and resumes processing after an application restart.

After this practice, you will be able to:

- Distinguish storing a single `Message`, storing a `MessageGroup`, and storing business metadata.
- Attach `JdbcMessageStore` to an aggregator using the Java DSL.
- Design a stable correlation key and a release strategy resilient to duplicate events.
- Verify database state across two independent application contexts.
- Define policies for incomplete groups, late messages, and finalized data.
- Identify which parts need transactions, distributed locks, and idempotency in production.

Prerequisites: `Message`, payload/headers, `DirectChannel`, `QueueChannel`, gateways, filters, and aggregators. The JDBC layer serves purely to persist integration state; the focus remains on the behavior of Spring Integration Core components.

## 2. Problem Statement: Application Stops Mid-Order

An order is only ready to complete once it receives all three confirmations:

| Event type | Meaning | Example reference |
| --- | --- | --- |
| `PAYMENT` | Payment succeeded | `PAY-101` |
| `STOCK` | Inventory reserved | `STOCK-101` |
| `SHIPMENT` | Shipment created | `SHIP-101` |

Confirmations may arrive out of order, be redelivered, or arrive minutes apart. The key scenario:

1. Application A receives `PAYMENT` and `STOCK` for `ORD-101`.
2. A stops before receiving `SHIPMENT`.
3. Application B opens the same database.
4. B receives `SHIPMENT` and produces a result containing all three confirmations.

If the message group resided only in A's memory, B would see only the final confirmation. Persisting state here means persisting waiting messages along with group metadata so the new aggregator can continue deciding when new data arrives.

Do not assume an application automatically completes every group upon startup. In this flow, arriving messages trigger release evaluation; groups that stop receiving messages need a separate expiry policy.

## 3. Choosing the Right Store Type

Spring Integration provides storage contracts for different needs:

| Component | State managed | Use case |
| --- | --- | --- |
| `MessageStore` | Messages by message ID | Store and retrieve a single message, such as claim check |
| `MessageGroupStore` | Groups, member messages, and group metadata | Aggregator, resequencer |
| `ChannelMessageStore` | Store/poll operations optimized for channels | Backing queue of `QueueChannel` |
| `MetadataStore` | Key–value pairs for metadata | Ingestion progress, processed-event tracking keys |
| Business tables | Application-defined business truth | Orders, payments, finalized outcomes |

`SimpleMessageStore` stores in memory and therefore does not survive JVM shutdown. A persistent store keeps data outside the process; at the same time, you must evaluate how payloads and headers are serialized. [Message Store Documentation](https://docs.spring.io/spring-integration/reference/6.5/message-store.html).

With JDBC, choose `JdbcMessageStore` for aggregator groups. When persisting channel queues, use `JdbcChannelMessageStore` with a query provider matching the database. These two choices serve different roles in the same system. [JDBC Message Store Documentation](https://docs.spring.io/spring-integration/reference/6.5/jdbc/message-store.html).

Having a store bean in the Spring context does not make a flow durable by itself. The aggregator must actually be configured to use that bean.

## 4. State Contract and Processing Flow

The practice exercise uses these conventions:

| Property | Value or rule |
| --- | --- |
| Correlation key | `order-assembly:v1:<orderId>` |
| Store region | `orders-assembly-v1` |
| Release condition | All three confirmation kinds present; each kind has a single distinct reference |
| Identical duplicate events | Do not cause premature group completion |
| Same kind with different reference | Keep group incomplete to handle conflict |
| Normal completion | Remove member messages, retain completed-group marker |
| Expired group | Route messages to discard channel without creating a completed order |
| Result observation channel in lab | In-memory `QueueChannel` |

~~~mermaid
flowchart LR
    P["OrderPart"] --> G["One-way Gateway"]
    G --> I["orderParts: DirectChannel"]
    I --> F{"Valid data?"}
    F -->|No| V["invalidParts"]
    F -->|Yes| A["Aggregator"]
    A <-->|Persist and read group| S[("JdbcMessageStore")]
    A -->|Ready| O["completedOrders"]
    A -->|Expired or late| D["discardedParts"]
    R["Scheduled Reaper"] -->|Check group age| S
~~~

This lesson intentionally uses an in-memory output queue to read results in tests. Once a result is emitted onto that queue, restarting loses unconsumed results. The recovery test therefore stops the application while the group is **still incomplete**.

The correlation key must be generated identically across runs. Never include a per-startup random UUID in the key or region. In multi-tenant systems, include the tenant in the key and test two tenants with the same `orderId`.

## 5. Preparing the Practice Project

The example pins illustrative versions at Java 17, Spring Boot 3.5.0, and Spring Integration 6.5.0. This is a baseline to reproduce the lesson; when applying to a project, use that project's compatible BOM. Spring Boot 3.5.0 manages Spring Integration 6.5.0 in its BOM. [Official Dependency Declarations](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.5.0/spring-boot-project/spring-boot-dependencies/build.gradle).

The files below are sample code for learners to create in a separate lab project.

### 5.1. Dependencies

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>vn.example</groupId>
    <artifactId>message-store-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-integration</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.integration</groupId>
            <artifactId>spring-integration-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 5.2. DataSource and Schema

`src/main/resources/application.properties`:

~~~properties
spring.main.web-application-type=none

spring.datasource.url=jdbc:h2:file:./target/message-store-lab/state;DB_CLOSE_ON_EXIT=FALSE
spring.datasource.username=sa
spring.datasource.password=

spring.integration.jdbc.initialize-schema=never
spring.sql.init.mode=never
spring.sql.init.schema-locations=classpath:org/springframework/integration/jdbc/schema-h2.sql
~~~

Two schema initialization mechanisms can appear in a Boot application: generic SQL initialization and Integration's JDBC initialization. The example uses only generic SQL initialization when tests pass `spring.sql.init.mode=always`; the other is disabled to avoid creating tables twice.

The script inside the `spring-integration-jdbc` JAR defines tables such as:

| Table | Role in this lesson |
| --- | --- |
| `INT_MESSAGE` | Stores message data |
| `INT_MESSAGE_GROUP` | Stores group metadata |
| `INT_GROUP_TO_MESSAGE` | Links groups to messages |
| `INT_LOCK` | Can support JDBC locks when scaling to multiple instances |

Column names and data types must follow the script for the exact version and database engine. Do not create a simplistic custom payload table and expect `JdbcMessageStore` to use it. [Spring Integration 6.5.0 H2 Schema](https://raw.githubusercontent.com/spring-projects/spring-integration/v6.5.0/spring-integration-jdbc/src/main/resources/org/springframework/integration/jdbc/schema-h2.sql).

In the restart test, the first context creates the schema on a fresh database; the second context uses `never`. Unconditionally rerunning table-creation scripts against an existing database causes errors. In deployed environments, manage DDL with migrations and preserve data across releases.

### 5.3. Serializable Payload

`src/main/java/vn/example/messagestore/OrderPart.java`:

~~~java
package vn.example.messagestore;

import java.io.Serial;
import java.io.Serializable;

public record OrderPart(
        String orderId,
        Kind kind,
        String reference) implements Serializable {

    @Serial
    private static final long serialVersionUID = 1L;

    public enum Kind {
        PAYMENT, STOCK, SHIPMENT
    }
}
~~~

`src/main/java/vn/example/messagestore/OrderSummary.java`:

~~~java
package vn.example.messagestore;

import java.util.Map;

public record OrderSummary(
        String orderId,
        Map<OrderPart.Kind, String> references) {
}
~~~

`OrderPart` is persisted to JDBC, so it implements `Serializable`. `OrderSummary` in the lab only goes to an in-memory queue. If switching to a store using Java serialization for output, you must design serializability for both the result type and all nested data inside it.

Do not place connections, entity proxies, or service beans inside payloads. A small DTO with explicit IDs and references makes recovery across future deployments much easier to control.

### 5.4. Entry Point via Gateway

`src/main/java/vn/example/messagestore/OrderGateway.java`:

~~~java
package vn.example.messagestore;

import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway(defaultRequestChannel = "orderParts")
public interface OrderGateway {

    void accept(OrderPart part);
}
~~~

The gateway returns `void` because an order may have to wait a long time for other events. Do not hold an HTTP request or a request–reply gateway call open until all confirmations arrive. Completed results have a dedicated output at `completedOrders`.

`src/main/java/vn/example/messagestore/MessageStoreLabApplication.java`:

~~~java
package vn.example.messagestore;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.integration.annotation.IntegrationComponentScan;

@SpringBootApplication
@IntegrationComponentScan
public class MessageStoreLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(MessageStoreLabApplication.class, args);
    }
}
~~~

The application has no runner automatically submitting data. Tests will precisely control which messages arrive before and after closing the context.

## 6. Configuring the Aggregator with JdbcMessageStore

`src/main/java/vn/example/messagestore/OrderFlowConfiguration.java`:

~~~java
package vn.example.messagestore;

import java.util.EnumMap;
import java.util.EnumSet;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import javax.sql.DataSource;

import org.springframework.boot.sql.init.dependency.DependsOnDatabaseInitialization;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jdbc.store.JdbcMessageStore;
import org.springframework.integration.store.MessageGroup;
import org.springframework.messaging.Message;

@Configuration
@EnableIntegration
public class OrderFlowConfiguration {

    public static final String REGION = "orders-assembly-v1";

    public static String groupId(String orderId) {
        return "order-assembly:v1:" + orderId;
    }

    @Bean
    @DependsOnDatabaseInitialization
    public JdbcMessageStore orderGroupStore(DataSource dataSource) {
        JdbcMessageStore store = new JdbcMessageStore(dataSource);
        store.setRegion(REGION);
        store.setTimeoutOnIdle(false);
        return store;
    }

    @Bean
    public DirectChannel orderParts() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel completedOrders() {
        return new QueueChannel(100);
    }

    @Bean
    public QueueChannel invalidParts() {
        return new QueueChannel(100);
    }

    @Bean
    public QueueChannel discardedParts() {
        return new QueueChannel(100);
    }

    @Bean
    public IntegrationFlow assembleOrderFlow(JdbcMessageStore orderGroupStore) {
        return IntegrationFlow.from("orderParts")
                .filter(OrderPart.class, OrderFlowConfiguration::valid,
                        f -> f.discardChannel("invalidParts"))
                .aggregate(a -> a
                        .messageStore(orderGroupStore)
                        .correlationStrategy(message -> groupId(
                                ((OrderPart) message.getPayload()).orderId()))
                        .releaseStrategy(OrderFlowConfiguration::ready)
                        .outputProcessor(OrderFlowConfiguration::summarize)
                        .expireGroupsUponCompletion(false)
                        .expireGroupsUponTimeout(false)
                        .sendPartialResultOnExpiry(false)
                        .minimumTimeoutForEmptyGroups(300_000)
                        .discardChannel("discardedParts"))
                .channel("completedOrders")
                .get();
    }

    private static boolean valid(OrderPart part) {
        return part.orderId() != null
                && !part.orderId().isBlank()
                && part.kind() != null
                && part.reference() != null
                && !part.reference().isBlank();
    }

    private static boolean ready(MessageGroup group) {
        Map<OrderPart.Kind, Set<String>> references =
                new EnumMap<>(OrderPart.Kind.class);

        for (Message<?> message : group.getMessages()) {
            OrderPart part = (OrderPart) message.getPayload();
            references.computeIfAbsent(part.kind(), key -> new HashSet<>())
                    .add(part.reference());
        }

        return references.keySet().equals(EnumSet.allOf(OrderPart.Kind.class))
                && references.values().stream()
                        .allMatch(values -> values.size() == 1);
    }

    private static OrderSummary summarize(MessageGroup group) {
        Map<OrderPart.Kind, String> references =
                new EnumMap<>(OrderPart.Kind.class);
        String orderId = null;

        for (Message<?> message : group.getMessages()) {
            OrderPart part = (OrderPart) message.getPayload();
            orderId = part.orderId();
            references.putIfAbsent(part.kind(), part.reference());
        }

        return new OrderSummary(orderId, Map.copyOf(references));
    }
}
~~~

Three key configuration decisions:

1. `.messageStore(orderGroupStore)` connects the aggregator's state to JDBC.
2. `groupId(orderId)` ensures all confirmations for an order enter the same group.
3. `ready()` inspects business data instead of merely counting `Message` instances.

For instance, `PAYMENT, PAYMENT, STOCK` has three messages yet lacks `SHIPMENT`, so it is not released. Two `PAYMENT` messages with the same reference remain in the group; checking the reference set prevents them from falsely triggering completion.

If two `PAYMENT` messages carry different references, `ready()` returns `false`. The lab keeps that group waiting for expiry to observe the conflict rather than arbitrarily picking one payment. In a real system, you can emit a conflict event and route the group into a dedicated handling workflow.

`summarize()` does not rely on retrieval order from the store. Because the release strategy guarantees each kind has only one reference, combining identical duplicates produces a deterministic result.

### Group Lifecycle in This Configuration

- Upon receiving the first part: the group exists, is not complete, and holds member messages.
- When all data is present: the aggregator builds `OrderSummary`, removes processed members, and retains the completion marker.
- When a message with the same key arrives late: it is routed to `discardedParts` while the completion marker still exists.
- Once the completion marker is purged: the same key can open a new group.

Retaining metadata after completion helps block late messages for a window of time. Deleting the whole group right after release allows the same key to reopen immediately. This policy must align with how long upstream sources may redeliver data. [Aggregator Lifecycle](https://docs.spring.io/spring-integration/reference/6.5/aggregator.html).

## 7. Testing Recovery, Redelivery, and Expiry

A test that only sends three messages within the same context does not prove state can be recovered. You must close the first context, create a second context, and read the group back from the same database.

`src/test/java/vn/example/messagestore/MessageStoreRecoveryTest.java`:

~~~java
package vn.example.messagestore;

import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.jdbc.store.JdbcMessageStore;
import org.springframework.integration.store.MessageGroupStoreReaper;
import org.springframework.messaging.Message;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import static org.assertj.core.api.Assertions.assertThat;
import static vn.example.messagestore.OrderPart.Kind.PAYMENT;
import static vn.example.messagestore.OrderPart.Kind.SHIPMENT;
import static vn.example.messagestore.OrderPart.Kind.STOCK;

class MessageStoreRecoveryTest {

    @TempDir
    Path tempDirectory;

    private String databaseUrl() {
        String path = tempDirectory.resolve("state").toAbsolutePath()
                .toString().replace('\\', '/');
        return "jdbc:h2:file:" + path + ";DB_CLOSE_ON_EXIT=FALSE";
    }

    private ConfigurableApplicationContext open(String initMode) {
        return new SpringApplicationBuilder(MessageStoreLabApplication.class)
                .web(WebApplicationType.NONE)
                .run(
                        "--spring.datasource.url=" + databaseUrl(),
                        "--spring.sql.init.mode=" + initMode,
                        "--lab.expiry.enabled=false");
    }

    @Test
    void resumesIncompleteGroupAfterContextRestart() {
        String key = OrderFlowConfiguration.groupId("ORD-101");

        try (ConfigurableApplicationContext first = open("always")) {
            OrderGateway gateway = first.getBean(OrderGateway.class);
            JdbcMessageStore store = first.getBean(JdbcMessageStore.class);
            QueueChannel output = first.getBean(
                    "completedOrders", QueueChannel.class);

            gateway.accept(new OrderPart("ORD-101", PAYMENT, "PAY-101"));
            gateway.accept(new OrderPart("ORD-101", STOCK, "STOCK-101"));

            assertThat(output.receive(0)).isNull();
            assertThat(store.getMessageGroup(key).size()).isEqualTo(2);
            assertThat(store.getMessageGroup(key).isComplete()).isFalse();
        }

        try (ConfigurableApplicationContext second = open("never")) {
            OrderGateway gateway = second.getBean(OrderGateway.class);
            JdbcMessageStore store = second.getBean(JdbcMessageStore.class);
            QueueChannel output = second.getBean(
                    "completedOrders", QueueChannel.class);
            QueueChannel discarded = second.getBean(
                    "discardedParts", QueueChannel.class);

            assertThat(store.getMessageGroup(key).size()).isEqualTo(2);

            gateway.accept(new OrderPart("ORD-101", SHIPMENT, "SHIP-101"));

            Message<?> message = output.receive(1_000);
            assertThat(message).isNotNull();
            OrderSummary summary = (OrderSummary) message.getPayload();

            assertThat(summary.orderId()).isEqualTo("ORD-101");
            assertThat(summary.references())
                    .containsEntry(PAYMENT, "PAY-101")
                    .containsEntry(STOCK, "STOCK-101")
                    .containsEntry(SHIPMENT, "SHIP-101")
                    .hasSize(3);

            assertThat(output.receive(0)).isNull();
            assertThat(store.getMessageGroup(key).size()).isZero();
            assertThat(store.getMessageGroup(key).isComplete()).isTrue();

            gateway.accept(new OrderPart("ORD-101", PAYMENT, "PAY-101"));

            assertThat(discarded.receive(1_000)).isNotNull();
            assertThat(output.receive(0)).isNull();
        }
    }

    @Test
    void duplicateKindDoesNotSatisfyMissingConfirmation() {
        try (ConfigurableApplicationContext context = open("always")) {
            OrderGateway gateway = context.getBean(OrderGateway.class);
            JdbcMessageStore store = context.getBean(JdbcMessageStore.class);
            QueueChannel output = context.getBean(
                    "completedOrders", QueueChannel.class);

            gateway.accept(new OrderPart("ORD-202", PAYMENT, "PAY-202"));
            gateway.accept(new OrderPart("ORD-202", PAYMENT, "PAY-202"));
            gateway.accept(new OrderPart("ORD-202", STOCK, "STOCK-202"));

            assertThat(output.receive(0)).isNull();
            assertThat(store.getMessageGroup(
                    OrderFlowConfiguration.groupId("ORD-202")).size())
                    .isEqualTo(3);

            gateway.accept(new OrderPart("ORD-202", SHIPMENT, "SHIP-202"));

            Message<?> message = output.receive(1_000);
            assertThat(message).isNotNull();
            OrderSummary summary = (OrderSummary) message.getPayload();

            assertThat(summary.references()).hasSize(3);
            assertThat(output.receive(0)).isNull();
        }
    }

    @Test
    void expiryDiscardsIncompleteGroupWithoutProducingSummary() {
        try (ConfigurableApplicationContext context = open("always")) {
            OrderGateway gateway = context.getBean(OrderGateway.class);
            JdbcMessageStore store = context.getBean(JdbcMessageStore.class);
            QueueChannel output = context.getBean(
                    "completedOrders", QueueChannel.class);
            QueueChannel discarded = context.getBean(
                    "discardedParts", QueueChannel.class);

            gateway.accept(new OrderPart("ORD-303", PAYMENT, "PAY-303"));

            MessageGroupStoreReaper reaper = new MessageGroupStoreReaper(store);
            reaper.setTimeout(0);
            reaper.setExpireOnDestroy(false);
            reaper.start();

            try {
                TransactionTemplate transaction = new TransactionTemplate(
                        context.getBean(PlatformTransactionManager.class));
                transaction.executeWithoutResult(status -> reaper.run());
            }
            finally {
                reaper.stop();
            }

            assertThat(output.receive(0)).isNull();
            assertThat(discarded.receive(1_000)).isNotNull();
            assertThat(store.getMessageGroup(
                    OrderFlowConfiguration.groupId("ORD-303")).size())
                    .isZero();
            assertThat(store.getMessageGroup(
                    OrderFlowConfiguration.groupId("ORD-303")).isComplete())
                    .isTrue();
        }
    }
}
~~~

Learners run:

~~~shell
mvn test
~~~

Each test method has its own temporary directory. Both contexts in the first test share the database file, yet do not share store beans, channels, or aggregator memory. Arguments passed to `run(...)` override default configuration to control schema creation.

The second test calls the gateway twice with the same data. Each call creates a new message; this is a business redelivery scenario, not reusing the same message ID.

The third test sets timeout to 0 to trigger expiry immediately rather than sleeping through a real timeout. A manually constructed `MessageGroupStoreReaper` must be started with `start()` before calling `run()`. [Reaper 6.5.0 Source](https://raw.githubusercontent.com/spring-projects/spring-integration/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/store/MessageGroupStoreReaper.java).

### Scope of Proof of the Tests

The restart test above proves an incomplete group is read back after replacing the entire Spring context. It does not prove crash recovery between two SQL statements, concurrent processing across two JVMs, or transactions spanning brokers and HTTP.

To test a real process restart, use one program to send two confirmations into the file database, exit the JVM, and then run another program with schema initialization disabled to send the final confirmation. Keep the payload package/class, JDBC URL, region, and correlation strategy identical.

Do not use `jdbc:h2:mem:...` if you want test data to survive JVM exit. File-based H2 in the lab also requires closing contexts sequentially; running multiple instances concurrently requires a proper database server.

## 8. Cleaning Up Expired Groups After Restart

There are two distinct timing requirements:

- **Wait time for data:** a group missing confirmations must not live forever.
- **Completion-marker retention:** a completed group still needs to block redelivered messages for a period.

In the lab configuration:

| Parameter | Policy |
| --- | --- |
| `store.setTimeoutOnIdle(false)` | Group age measured from group creation |
| Reaper timeout | 60 seconds for groups considered for expiry |
| Reaper interval | 5 seconds |
| `minimumTimeoutForEmptyGroups` | Retain empty group markers at least 5 minutes from last update |
| `sendPartialResultOnExpiry(false)` | Incomplete groups must not produce a success summary |
| `expireGroupsUponTimeout(false)` | Keep completion marker after timeout processing |

The reaper inspects persisted data and can therefore find leftover groups from a previous run. An in-memory timer per group does not automatically become a persistent timer just because messages are stored in JDBC.

If `setTimeoutOnIdle(true)` is enabled, expiration is based on the latest update. A source continuously resending duplicates can keep extending the group's lifetime. Choose the rule per your business SLA and use the same rule in tests. [How group store calculates timeout](https://raw.githubusercontent.com/spring-projects/spring-integration/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/store/AbstractMessageGroupStore.java).

### Configuring the Sweep Schedule

Add the following file when you want automatic expiry to run.

`src/main/java/vn/example/messagestore/ExpiryConfiguration.java`:

~~~java
package vn.example.messagestore;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.jdbc.store.JdbcMessageStore;
import org.springframework.integration.store.MessageGroupStoreReaper;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@Configuration
@EnableScheduling
@ConditionalOnProperty(name = "lab.expiry.enabled", havingValue = "true")
public class ExpiryConfiguration {

    @Bean
    public MessageGroupStoreReaper orderGroupReaper(
            JdbcMessageStore orderGroupStore) {
        MessageGroupStoreReaper reaper =
                new MessageGroupStoreReaper(orderGroupStore);
        reaper.setTimeout(60_000);
        reaper.setExpireOnDestroy(false);
        return reaper;
    }

    @Bean
    public ExpiryTask expiryTask(
            MessageGroupStoreReaper orderGroupReaper,
            PlatformTransactionManager transactionManager) {
        return new ExpiryTask(
                orderGroupReaper,
                new TransactionTemplate(transactionManager));
    }

    public static class ExpiryTask {

        private final MessageGroupStoreReaper reaper;
        private final TransactionTemplate transaction;

        public ExpiryTask(MessageGroupStoreReaper reaper,
                          TransactionTemplate transaction) {
            this.reaper = reaper;
            this.transaction = transaction;
        }

        @Scheduled(fixedDelay = 5_000, initialDelay = 5_000)
        public void expire() {
            transaction.executeWithoutResult(status -> reaper.run());
        }
    }
}
~~~

Enable with `lab.expiry.enabled=true`. The tests in the previous section always pass `false` so the background schedule does not interfere with test data under inspection.

With a 60-second timeout and a 5-second sweep, a group is processed on a sweep after it reaches the age threshold; exact timing also depends on scheduler load, transaction time, and lock contention. Do not interpret these numbers as millisecond-exact guarantees.

`setExpireOnDestroy(false)` preserves data when the reaper stops. Shutting down the application in the recovery test must not turn into a request to flush all groups.

`ExpiryTask`'s transaction wraps the sweep in the lab. When group counts are large, evaluate transaction hold duration, partition sweep load, and per-group handling policies. Writing to `discardedParts` is still an in-memory queue operation, so there is no corresponding JDBC rollback for it.

An error from a `@Scheduled` method does not automatically become an `ErrorMessage` on an Integration flow's `errorChannel`. Configure the scheduler's error handler when operations require receiving errors through an error flow.

### Bounded-Lifetime Completion Markers

Retaining completion metadata for five minutes protects only within that window. Once metadata is purged, an old event can reopen a group. If sources may redeliver days later, use a mechanism that recognizes finalized business outcomes with an appropriate retention period.

A unique `orderId` record in the result table, or an idempotency key with an explicit namespace and retention, is usually the right place to guard long-term business side effects. Do not keep every group forever just as a substitute for that rule.

## 9. Transactions: Persistent State Needs Clear Boundaries

The aggregator configuration in section 6 does not automatically open a transaction around each gateway call. Multiple JDBC statements may commit independently without an enclosing transaction.

To process an incoming message inside a JDBC transaction, you can place the boundary at the application service calling the gateway:

~~~java
TransactionTemplate transaction = new TransactionTemplate(transactionManager);

transaction.executeWithoutResult(status ->
        gateway.accept(new OrderPart("ORD-404", PAYMENT, "PAY-404")));
~~~

This snippet assumes `transactionManager` manages the exact DataSource of `JdbcMessageStore`. Because the input uses `DirectChannel`, the aggregator's synchronous processing runs on the calling thread and joins that transaction. Moving to an executor or asynchronous boundary requires redefining transactions at the consumer. [Transaction Support](https://docs.spring.io/spring-integration/reference/6.5/transactions.html).

A meaningful rollback test injects an error after adding **part** of a group:

~~~java
String key = OrderFlowConfiguration.groupId("ORD-ROLLBACK");
int groupsBefore = store.getMessageGroupCount();

assertThrows(IllegalStateException.class, () ->
        transaction.executeWithoutResult(status -> {
            gateway.accept(new OrderPart(
                    "ORD-ROLLBACK", PAYMENT, "PAY-ROLLBACK"));
            throw new IllegalStateException("Error after adding message");
        }));

assertThat(store.getMessageGroup(key).size()).isZero();
assertThat(store.getMessageGroupCount()).isEqualTo(groupsBefore);
~~~

This additional test snippet requires `import static org.junit.jupiter.api.Assertions.assertThrows;`; `store`, `gateway`, and transaction are obtained from the test context. Because the group is not ready to release, this test focuses on state rollback without producing output.

### The Gap Between Persisting State and External Effects

Consider the sequence:

~~~text
Final confirmation arrives
    -> aggregator emits result
    -> call shipping API
    -> mark group as complete
~~~

If the API succeeded yet the JDBC transaction rolled back, a redelivery may call the API again. If the group was marked complete while the output resided only in memory when the JVM stopped, the final side effect may never have occurred.

An extended design for this problem:

1. Wrap input processing in the DataSource transaction.
2. Replace the in-memory output queue with a handler writing an outbox record on the same DataSource and in the same transaction.
3. Put a unique constraint on the side-effect key, such as `order-completed:<orderId>`.
4. Have a worker read the outbox, send to the external system, and record progress with a retry policy.
5. Have the downstream consumer or API support idempotency because redeliveries can still occur.

This is a recommended design for the order problem. `MessageStore` durability is part of the design; ensuring a business effect occurs only once also depends on the commit point, communication protocol, and receiver-side duplicate detection.

## 10. Extension: Persisting the Input Queue as Well

The aggregator's store holds only messages **that have already reached the aggregator**. If an in-memory `QueueChannel` sits upstream, messages waiting in that queue can still be lost.

You can add a JDBC-backed queue as an extension exercise. Place the following beans in a `@Configuration` class; keep the `Bean`, `DataSource`, `QueueChannel`, and `DependsOnDatabaseInitialization` imports from earlier, plus:

~~~java
import org.springframework.integration.jdbc.store.JdbcChannelMessageStore;
import org.springframework.integration.jdbc.store.channel.H2ChannelMessageStoreQueryProvider;
import org.springframework.integration.store.MessageGroupQueue;
~~~

~~~java
@Bean
@DependsOnDatabaseInitialization
public JdbcChannelMessageStore inboxStore(DataSource dataSource) {
    JdbcChannelMessageStore store = new JdbcChannelMessageStore(dataSource);
    store.setRegion("orders-inbox-v1");
    store.setChannelMessageStoreQueryProvider(
            new H2ChannelMessageStoreQueryProvider());
    return store;
}

@Bean
public QueueChannel durableOrderInbox(JdbcChannelMessageStore inboxStore) {
    return new QueueChannel(
            new MessageGroupQueue(inboxStore, "order-inbox-v1"));
}
~~~

The queue needs a consumer with a poller. With additional imports `IntegrationFlow`, `Pollers`, and `PlatformTransactionManager`:

~~~java
@Bean
public IntegrationFlow consumeDurableInbox(
        PlatformTransactionManager transactionManager) {
    return IntegrationFlow.from("durableOrderInbox")
            .bridge(endpoint -> endpoint.poller(
                    Pollers.fixedDelay(250)
                            .maxMessagesPerPoll(1)
                            .transactional(transactionManager)))
            .channel("orderParts")
            .get();
}
~~~

Change the gateway's `defaultRequestChannel` to `durableOrderInbox` when trying this variant. If you leave it as `orderParts`, the gateway still goes straight to the aggregator and never exercises the new queue.

With a JDBC channel store and matching transaction, pulling from the queue and synchronous downstream processing share a single transaction; when an error triggers rollback, the message poll itself rolls back too. A queue that merely persists messages while being polled outside a transaction does not provide that guarantee. [Persistent Channel Configuration](https://docs.spring.io/spring-integration/reference/6.5/channel/configuration.html).

This extension requires two additional tests:

- Stop the consumer, send a message to the queue, restart the application, and verify the message is still retrieved.
- Inject an error in the consumer after polling, verify the message can be received again after rollback, and confirm group state was not corrupted.

The query provider must match the target database. Also verify the channel store schema for the exact version; do not reuse H2 configuration verbatim for PostgreSQL.

## 11. When Multiple Instances Process Concurrently

Sharing persisted state and locking operations on that state solve two different problems. Two instances can simultaneously read an incomplete group, add data, and both decide to release if only local locks are used.

With a shared JDBC store, you can use `JdbcLockRegistry` backed by `DefaultLockRepository` to coordinate per-group locks across instances. [JDBC Lock Registry](https://docs.spring.io/spring-integration/reference/6.5/jdbc/lock-registry.html).

When scaling out the configuration:

- Configure an appropriate distributed lock registry on the aggregator via `.lockRegistry(orderLocks)`.
- With the group store abstraction in 6.5, consider configuring the same lock mechanism for metadata operations via `store.setLockRegistry(orderLocks)`.
- Keep database, table prefix, store region, correlation namespace, and lock configuration consistent across instances owning the flow.
- Ensure lock lease duration fits processing time; test cases where an instance loses connectivity or stops while holding a lock.
- Use uniquely keyed business outcomes to control duplicate side effects after retries.

Locks do not replace transactions: locks restrict who may operate concurrently, whereas transactions define which changes commit together.

Do not arbitrarily share one `MessageGroupStore` bean across multiple aggregators with different lifecycles. Separate beans and regions per flow, and schedule expiry specifically for each flow's store. That prevents a reaper from accidentally applying one flow's timeout policy to another flow's data.

In multi-instance tests, use a database server, send concurrent events for the same key, and count committed business outcomes. Simply counting logs or verifying the JVM threw no exceptions is insufficient to prove correctness.

## 12. Payloads, Headers, and Legacy Data Compatibility

State persisted today may have to be read by next week's release. Establish upfront:

| Component | Recommended rule for the problem |
| --- | --- |
| Payload | Small DTO containing only the data needed to complete the group |
| Business headers | IDs, tenant, trace ID, and values safe to persist long-term |
| Payload class | Maintain backward-compatible reading or provide migration |
| Region/key | Change intentionally; never inject random versions |
| Sensitive data | Persist the minimum required for processing and retention |
| Finalized outcomes | Have a dedicated business key for long-term deduplication |

With the JDBC store's default serializer, evaluate both payload persistence and whether all headers can be preserved intact. A header pointing to a live channel or JVM-local resource is not a durable address across restarts.

Registry-based conversion of `replyChannel` into a name helps in some flows, yet an in-memory temporary channel does not automatically resurrect in another JVM. This lesson uses a one-way gateway and a fixed output channel so it does not depend on a waiting caller.

When using Java serialization, `serialVersionUID` is part of the compatibility contract; keeping the same value does not guarantee every structural or semantic change is safe. Testing deserialization of data created by a prior release is an essential release check.

If choosing a different serializer, configure both write and read paths and re-test real messages across restarts. Changing storage format without handling existing records will prevent old groups from continuing.

## 13. Observing State and Troubleshooting

In the lab, you can inspect a group's state via the API:

~~~java
String key = OrderFlowConfiguration.groupId("ORD-101");

MessageGroup group = store.getMessageGroup(key);
System.out.println("size=" + group.size());
System.out.println("complete=" + group.isComplete());
System.out.println("created=" + group.getTimestamp());
System.out.println("lastModified=" + group.getLastModified());
~~~

The `store` and `group` variables are strictly for observation at inspection time. Never mutate a group's message collection directly outside the active aggregator.

To inspect aggregate counts in the H2 database:

~~~sql
SELECT REGION, COMPLETE, COUNT(*) AS GROUP_COUNT
FROM INT_MESSAGE_GROUP
WHERE REGION = 'orders-assembly-v1'
GROUP BY REGION, COMPLETE;

SELECT REGION, COUNT(*) AS STORED_MESSAGE_COUNT
FROM INT_MESSAGE
WHERE REGION = 'orders-assembly-v1'
GROUP BY REGION;

SELECT REGION, COUNT(*) AS MEMBERSHIP_COUNT
FROM INT_GROUP_TO_MESSAGE
WHERE REGION = 'orders-assembly-v1'
GROUP BY REGION;
~~~

`GROUP_KEY` in the table is the store's internal representation; do not assume it equals the literal string `order-assembly:v1:ORD-101` when writing business SQL queries. When checking a specific group, prefer the API with the original correlation key.

With lazy-loading stores, iterating over all of `getMessages()` across many groups can trigger extra queries and payload deserialization. Use counts and metadata for routine metrics; read full group details only when investigating.

Metrics worth tracking for this problem:

- Count of waiting groups and age of the oldest group.
- Stored message/record count and storage volume.
- Expired group count, late-arrival event count, and groups with conflicting references.
- Latency of adding messages, releasing groups, and waiting for locks.
- Serialization/deserialization errors, SQL errors, rollbacks, and retries.
- Committed business outcomes and idempotency blocks.

### Common Issues

| Symptom | Cause to check | How to fix |
| --- | --- | --- |
| Old group missing after restart | Changed database, region, key, or still using in-memory store | Compare actual configuration and inspect group before sending more |
| Application reports missing tables | Schema not created, wrong DataSource, or prefix mismatch | Check migrations and initialization ordering |
| Second run reports table already exists | Re-running schema creation script | Disable initialization when reopening an existing database |
| Three messages arrived yet wrong result | Only counting message count instead of checking confirmation kinds | Change release strategy to check kind set and business contract |
| Group never releases | Missing confirmation kind or conflicting references | Inspect state, handle upstream sender, and check timeout policy |
| Store grows unboundedly | No expiry, completion marker kept too long, or heavy duplicate traffic | Define retention, schedule sweeps, and add load limits |
| Results existed before restart then vanished | Output channel still in memory | Persist outputs or write an outbox |
| Errors reading old payloads | Incompatible DTO/serializer | Test reading prior-version data and implement migration |
| Two instances produce two side effects | Missing lock or idempotency, wrong commit boundary | Test concurrency and protect outcomes with business keys |

## 14. Advanced Exercises and Acceptance Criteria

### 14.1. Scenarios to Add

| Scenario | Expected result |
| --- | --- |
| Permute order of the three confirmations | Still produces one complete summary |
| Two interleaved orders | Two independent groups, no mixed references |
| Resend `PAYMENT` multiple times | Does not complete before `SHIPMENT` arrives |
| Two `PAYMENT` events with different references | Group stays unreleased; conflict evidence available for handling |
| Blank `orderId` | Goes to `invalidParts`, creates no valid group |
| Restart after two confirmations | Reads back two confirmations and completes on the third message |
| Restart when a group is expired | Reaper processes old group after sweep schedule is enabled |
| Late message while completion marker exists | Goes to discard, creates no new summary |
| Old message after completion marker purged | May open a new group; business idempotency still protects side effects |
| Error after partial addition inside transaction | Does not retain rolled-back addition |
| Two instances with same key | Committed outcomes obey business uniqueness rules |

### 14.2. Extension Implementation Requirements

1. Add `eventId` and design a duplicate-detection step before the aggregator; clarify when the ID is recorded vs. when state commits to avoid marking an event processed without persisting its data.
2. Split `discardedParts` into separate timeout-handling and late-message-handling sinks if operations require two different policies.
3. Persist diagnostic fields of timed-out groups before purging member messages.
4. Replace in-memory output with an outbox, inject failures at commit points, and prove retries do not cause invalid business side effects.
5. Run a compatibility test: create a group using an older DTO version and read it with a newer application version.
6. Measure the impact of an order receiving thousands of duplicate events; propose appropriate group-size limits, ingress limits, and deduplication mechanisms.

### 14.3. Acceptance Criteria

The practice exercise meets requirements when the learner provides:

- A Java DSL flow clearly showing which store manages aggregator state.
- Evidence proving an incomplete group survives closing and reopening the context.
- Tests showing duplicate messages cannot substitute for a missing confirmation.
- Timeout policy and completion-marker retention duration with explicit time units.
- Outputs distinguishing invalid messages, expired groups, and late messages.
- A description of transaction boundaries and how outputs are handled if the process stops.
- Concurrency control and idempotency plans for multi-instance deployments.

These outcomes properly validate the state-persistence goal: the aggregator can resume from persisted data, while post-release behavior is protected according to the designed business contract and storage boundaries.