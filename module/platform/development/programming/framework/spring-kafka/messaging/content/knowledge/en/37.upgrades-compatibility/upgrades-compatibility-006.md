# Migrating from Legacy Embedded Brokers

Older Spring Kafka projects commonly used embedded Kafka running with ZooKeeper via `EmbeddedKafkaZKBroker` or `EmbeddedKafkaRule`. Starting in Spring Kafka 3.1, the framework added an embedded broker running KRaft. By Spring Kafka 4.0, since Kafka 4.0 supports only KRaft, the ZooKeeper implementation, ZooKeeper dependencies, and related testing APIs were removed.

Migration requires reviewing broker creation, JUnit rules, annotation attributes, port configurations, broker properties, and test lifecycles. If you simply bump dependencies while keeping legacy APIs, tests will fail to compile or fail to start the broker.

This lesson focuses on the **embedded broker in Spring Kafka tests**. Changing the embedded broker does not automatically migrate a production Kafka cluster from ZooKeeper to KRaft; that is a separate cluster upgrade procedure.

## 1. What is the legacy embedded broker?

Before the KRaft embedded broker existed, `spring-kafka-test` started an embedded ZooKeeper alongside one or more embedded Kafka brokers. The implementation used was `EmbeddedKafkaZKBroker`.

Some projects constructed the broker directly:

```java
EmbeddedKafkaBroker broker =
    new EmbeddedKafkaZKBroker(1, false, 1, "orders");
```

Some projects used the JUnit 4 rule:

```java
@ClassRule
public static EmbeddedKafkaRule broker =
    new EmbeddedKafkaRule(1, false, "orders");
```

Or used `@EmbeddedKafka` to register the broker inside the Spring Test context.

In the legacy model, tests ran both a Kafka broker and a ZooKeeper process. The broker needed ZooKeeper to store cluster metadata. KRaft replaces this metadata mechanism with an integrated quorum controller inside Kafka.

## 2. Spring Kafka version roadmap

Not every 3.x version shares the same behavior. Identify your active version before modifying code.

| Spring Kafka | Embedded broker | How mode is selected |
|---|---|---|
| 2.x to 3.0 | `EmbeddedKafkaZKBroker` | Embedded Kafka using ZooKeeper |
| 3.1 | Added `EmbeddedKafkaKraftBroker` | Can instantiate the KRaft broker directly; KRaft broker does not support JUnit 4 |
| 3.2 | Both ZooKeeper and KRaft present | Use `@EmbeddedKafka(kraft = true)` to select KRaft |
| 3.3 | Both implementations present | `@EmbeddedKafka` still defaults to ZooKeeper; set `kraft = true` to switch to KRaft |
| 4.0 and higher | Only `EmbeddedKafkaKraftBroker` remains | KRaft is the sole option; ZooKeeper APIs removed |

Key milestones:

- Spring Kafka 3.1 introduced `EmbeddedKafkaKraftBroker`.
- Spring Kafka 3.2 added the `kraft` attribute to `@EmbeddedKafka`.
- In Spring Kafka 3.3, the ZooKeeper implementation remained the annotation default.
- Spring Kafka 4.0 upgraded to Kafka client 4.0 and removed all ZooKeeper functionality.

Therefore, if a project is on 3.3 and wants to switch early, enable KRaft explicitly. When moving to 4.0, remove ZooKeeper references and the KRaft toggle attribute since KRaft is the only default.

## 3. Distinguishing test migration from production Kafka migration

Both involve KRaft, yet differ in scope:

| Aspect | Embedded broker migration | Production cluster migration |
|---|---|---|
| Goal | Run tests using a KRaft broker | Migrate cluster metadata from ZooKeeper to KRaft |
| Components changed | Test dependencies, classes, annotations, JUnit, broker properties | Brokers/controllers, metadata, quorum, cluster config |
| Data | Usually reproducible test data | Must preserve cluster data and metadata |
| Done just by changing an annotation? | Possibly, if tests only use embedded broker | No |
| Tools/process | Spring Kafka Test and JUnit | Apache Kafka ZooKeeper-to-KRaft migration procedure |

Kafka 4.0 no longer supports ZooKeeper mode. Production clusters running ZooKeeper must be migrated to KRaft before upgrading brokers to Kafka 4.0. Apache Kafka specifies upgrading to broker 4.0 from 3.3.x–3.9.x releases and requires matching metadata/software versions. Do not use this embedded broker migration guide as a runbook for migrating a production cluster.

`EmbeddedKafkaKraftBroker` runs broker and controller in combined mode. It is suitable for testing the Kafka protocol and Spring integration, though it does not fully simulate a multi-node controller quorum, network topology, production ACL/TLS, or cluster node failures. For those scenarios, use dedicated Kafka containers or test clusters.

## 4. Inspecting the project before making changes

Search for legacy references in test sources and configuration:

```bash
rg -n "EmbeddedKafkaZKBroker|EmbeddedKafkaRule|SPRING_EMBEDDED_ZOOKEEPER_CONNECT|zookeeperPort|zkConnectionTimeout|zkSessionTimeout|kraft" src/test pom.xml build.gradle*
```

If using PowerShell without `rg`, search with:

```powershell
Get-ChildItem -Recurse src/test |
    Select-String -Pattern 'EmbeddedKafkaZKBroker|EmbeddedKafkaRule|SPRING_EMBEDDED_ZOOKEEPER_CONNECT|zookeeperPort|zkConnectionTimeout|zkSessionTimeout|kraft'
```

Review these locations:

- Imports of `EmbeddedKafkaZKBroker`.
- Instantiations `new EmbeddedKafkaZKBroker(...)`.
- JUnit 4 `EmbeddedKafkaRule`, `@ClassRule`, or `@Rule`.
- The `kraft` attribute on annotations or global embedded broker config.
- ZooKeeper attributes such as `zookeeperPort`, `zkConnectionTimeout`, `zkSessionTimeout`.
- The `SPRING_EMBEDDED_ZOOKEEPER_CONNECT` constant.
- Broker properties or system properties named `zookeeper.*`.
- Tests assuming the Kafka broker uses a fixed port.
- ZooKeeper dependencies declared directly only to support embedded tests.

Inspect the dependency tree to identify the actual versions of `spring-kafka`, `spring-kafka-test`, and `kafka-clients`. Do not rely only on declared versions in build files, as the Spring Boot BOM may manage a different version.

## 5. Switching @EmbeddedKafka from ZooKeeper to KRaft

### Before migration: Spring Kafka 3.3 using ZooKeeper

A legacy test may declare:

```java
@SpringBootTest
@EmbeddedKafka(
    partitions = 1,
    topics = "orders"
)
class OrderKafkaIntegrationTest {
    // EmbeddedKafkaZKBroker is created by default.
}
```

In Spring Kafka 3.3, to keep the annotation setup while switching the broker to KRaft, add `kraft = true`:

```java
@SpringBootTest
@EmbeddedKafka(
    kraft = true,
    partitions = 1,
    topics = "orders",
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class OrderKafkaIntegrationTest {
    // EmbeddedKafkaKraftBroker is created.
}
```

You can inject the `EmbeddedKafkaBroker` interface just as before:

```java
@Autowired
EmbeddedKafkaBroker embeddedKafka;
```

Prefer injecting the interface over the concrete implementation so tests depend less on the specific broker class.

### After migration: Spring Kafka 4.x

In Spring Kafka 4.0 and above, remove `kraft = true` because the annotation no longer has this attribute:

```java
@SpringBootTest
@EmbeddedKafka(
    partitions = 1,
    topics = "orders",
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class OrderKafkaIntegrationTest {

    @Autowired
    EmbeddedKafkaBroker embeddedKafka;
}
```

Since Spring Kafka 3.0.10, `bootstrapServersProperty` defaults to `spring.kafka.bootstrap-servers`. You can omit this attribute if your project uses the default and does not need to spell it out:

```java
@SpringBootTest
@EmbeddedKafka(
    partitions = 1,
    topics = "orders"
)
class OrderKafkaIntegrationTest {
}
```

When using Spring Boot, this property lets `KafkaTemplate`, consumer factories, and listener containers automatically connect to the ephemeral broker created for the test.

## 6. Migrating from EmbeddedKafkaZKBroker to EmbeddedKafkaKraftBroker

Some tests or test fixtures instantiate the broker via constructor. In those cases, update the class and constructor signature.

### Legacy approach

```java
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.EmbeddedKafkaZKBroker;

EmbeddedKafkaBroker broker =
    new EmbeddedKafkaZKBroker(
        1,
        false,
        1,
        "orders"
    );

broker.afterPropertiesSet();
```

The legacy constructor took broker count, `controlledShutdown`, partition count, and topics.

### Modern approach

```java
import org.springframework.kafka.test.EmbeddedKafkaBroker;
import org.springframework.kafka.test.EmbeddedKafkaKraftBroker;

EmbeddedKafkaBroker broker =
    new EmbeddedKafkaKraftBroker(
        1,
        1,
        "orders"
    );

broker.afterPropertiesSet();
```

The KRaft constructor takes broker count, partition count, and the list of topics. The `controlledShutdown` parameter from the ZooKeeper implementation no longer exists in the KRaft constructor.

If a fixture manages the lifecycle manually, it must call `destroy()` when the suite finishes. Inside a Spring Test context, prefer letting Spring manage the bean lifecycle rather than manually calling `afterPropertiesSet()` and `destroy()` repeatedly.

The snippet above illustrates the constructor API. In most Spring tests, `@EmbeddedKafka` is cleaner and lets the framework manage the lifecycle.

## 7. Migrating JUnit 4 EmbeddedKafkaRule to JUnit Jupiter

`EmbeddedKafkaRule` was a JUnit 4 wrapper for `EmbeddedKafkaZKBroker`. The KRaft embedded broker does not support JUnit 4. Spring Kafka 4.0 removed `EmbeddedKafkaRule` along with JUnit 4 support.

### Legacy approach: JUnit 4

```java
@RunWith(SpringRunner.class)
@SpringBootTest
public class OrderKafkaIntegrationTest {

    @ClassRule
    public static EmbeddedKafkaRule broker =
        new EmbeddedKafkaRule(1, false, "orders");

    @Autowired
    private KafkaTemplate<String, String> kafkaTemplate;

    @Test
    public void sendsOrder() {
        // Test sending message.
    }
}
```

### Modern approach: JUnit Jupiter

```java
@SpringBootTest
@EmbeddedKafka(
    partitions = 1,
    topics = "orders"
)
class OrderKafkaIntegrationTest {

    @Autowired
    KafkaTemplate<String, String> kafkaTemplate;

    @Test
    void sendsOrder() {
        // Test sending message.
    }
}
```

Key changes:

| JUnit 4 | JUnit Jupiter / Modern Spring Kafka |
|---|---|
| `@RunWith(SpringRunner.class)` | Spring Boot tests use `@SpringBootTest`; plain Spring tests use `@ExtendWith(SpringExtension.class)` or `@SpringJUnitConfig` |
| `@ClassRule` | `@EmbeddedKafka` at the class level |
| `EmbeddedKafkaRule` | Spring-managed `EmbeddedKafkaBroker` |
| `org.junit.Test` | `org.junit.jupiter.api.Test` |
| `@Before`, `@After` | `@BeforeEach`, `@AfterEach` |
| `@BeforeClass`, `@AfterClass` | `@BeforeAll`, `@AfterAll` |

If the test needs access to the broker address, inject `EmbeddedKafkaBroker`:

```java
@Autowired
EmbeddedKafkaBroker embeddedKafka;

@Test
void brokerIsAvailable() {
    String bootstrapServers = embeddedKafka.getBrokersAsString();

    assertThat(bootstrapServers).isNotBlank();
}
```

Do not retain `EmbeddedKafkaRule` in code just to keep running tests on JUnit 4 once upgraded to Spring Kafka 4.x.

## 8. Removing ZooKeeper attributes in @EmbeddedKafka

Spring Kafka 4.0 removes annotation attributes specific to ZooKeeper:

- `zookeeperPort`
- `zkConnectionTimeout`
- `zkSessionTimeout`
- `kraft`

Legacy configuration example:

```java
@EmbeddedKafka(
    kraft = true,
    zookeeperPort = 0,
    zkConnectionTimeout = 20_000,
    zkSessionTimeout = 20_000,
    topics = "orders"
)
```

Spring Kafka 4.x configuration:

```java
@EmbeddedKafka(
    topics = "orders",
    partitions = 1
)
```

Do not try to replace ZooKeeper attributes with equivalent KRaft attributes. The KRaft embedded broker manages controller/broker internals and does not start a ZooKeeper process.

Client configurations such as `bootstrap.servers`, serializers, deserializers, consumer groups, and listener concurrency are still used normally. They are not ZooKeeper configurations.

## 9. Handling removed ZooKeeper system properties and constants

With the ZooKeeper embedded broker, tests could read:

```java
String zookeeperConnect =
    System.getProperty(
        EmbeddedKafkaBroker.SPRING_EMBEDDED_ZOOKEEPER_CONNECT
    );
```

Or reference the `SPRING_EMBEDDED_ZOOKEEPER_CONNECT` constant.

When migrating to Spring Kafka 4.x, remove this logic. The embedded KRaft broker does not expose a ZooKeeper connect string.

If the test application only needs to connect to Kafka, use:

```java
String bootstrapServers = embeddedKafka.getBrokersAsString();
```

Or use the property published by the broker:

```java
import org.springframework.beans.factory.annotation.Value;

@Value("${spring.kafka.bootstrap-servers}")
String bootstrapServers;
```

The default `spring.embedded.kafka.brokers` system property still represents the Kafka broker addresses. Do not confuse it with the removed ZooKeeper property.

## 10. Switching the global embedded broker to KRaft

Spring Kafka 3.x provides `GlobalEmbeddedKafkaTestExecutionListener` for JUnit Platform. This feature is disabled by default.

In Spring Kafka 3.3, if using the global broker and wanting KRaft, set:

```properties
spring.kafka.global.embedded.enabled=true
spring.kafka.embedded.kraft=true
spring.kafka.embedded.topics=orders
spring.kafka.embedded.partitions=1
```

The `spring.kafka.embedded.kraft` property selects `EmbeddedKafkaKraftBroker` instead of the ZooKeeper implementation in supported versions.

When moving to Spring Kafka 4.x:

```properties
spring.kafka.global.embedded.enabled=true
spring.kafka.embedded.topics=orders
spring.kafka.embedded.partitions=1
```

Remove `spring.kafka.embedded.kraft` because KRaft is the only implementation. There is no longer a ZooKeeper option to toggle.

Do not mix the global embedded broker and per-test-class `@EmbeddedKafka` in the same suite without a clear lifecycle design. Both share system properties and can overwrite each other's broker addresses.

## 11. Adjusting tests that depend on fixed ports

An important difference of the KRaft embedded broker is that it does not support configuring custom Kafka ports like the legacy ZooKeeper implementation.

If a test previously called:

```java
new EmbeddedKafkaZKBroker(1, false, "orders")
    .kafkaPorts(19092);
```

that fixed-port assumption cannot be kept when migrating to the KRaft embedded broker.

Use the dynamic address returned by the broker:

```java
String bootstrapServers = embeddedKafka.getBrokersAsString();
```

With Spring Boot, to have the broker write its address to `spring.kafka.bootstrap-servers`:

```java
@EmbeddedKafka(
    topics = "orders",
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
@SpringBootTest
class OrderKafkaIntegrationTest {
}
```

If an external process outside the JVM must connect to the broker on a fixed port, embedded KRaft may not be the right tool. Use a Kafka container or a dedicated test broker with controllable port mappings.

Do not hard-code `localhost:9092` in tests when the broker starts on a random port.

## 12. Checking broker properties and replication factors

KRaft does not use ZooKeeper, so remove ZooKeeper-only broker properties such as:

- `zookeeper.connect`
- `zookeeper.connection.timeout.ms`
- `zookeeper.session.timeout.ms`
- ZooKeeper client authentication/SSL configurations used solely to connect to ZooKeeper.

Other Kafka broker and topic configurations may still be needed. However, tests must match the actual broker count.

With a single-node embedded broker:

- Test topic replication factor must not exceed the broker count.
- If testing transactions, internal transaction state topics must use a replication factor suitable for a single broker.
- Do not copy multi-node production cluster replication factors directly into a single-node test.
- When testing with multiple embedded brokers, check the broker count and min ISR before setting replication factors.

Example single-broker setup for a transaction test:

```java
@EmbeddedKafka(
    partitions = 1,
    topics = "orders",
    brokerProperties = {
        "transaction.state.log.replication.factor=1",
        "transaction.state.log.min.isr=1"
    }
)
@SpringBootTest
class TransactionalKafkaIntegrationTest {
}
```

Broker properties should only be added when the test actually uses transactions. You do not need to configure every internal topic for simple producer/consumer tests.

## 13. Post-migration integration test example

A basic test can keep the same send/receive logic; the main changes are the embedded broker and JUnit.

Test listener:

```java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;

import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class OrderTestListener {

    private final BlockingQueue<String> received =
        new LinkedBlockingQueue<>();

    @KafkaListener(
        id = "orders-test-listener",
        topics = "orders",
        groupId = "orders-test-group"
    )
    public void listen(String payload) {
        received.add(payload);
    }

    public BlockingQueue<String> received() {
        return received;
    }
}
```

Test:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.test.context.EmbeddedKafka;

@SpringBootTest
@EmbeddedKafka(
    partitions = 1,
    topics = "orders",
    bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class OrderKafkaIntegrationTest {

    @Autowired
    KafkaTemplate<String, String> kafkaTemplate;

    @Autowired
    OrderTestListener listener;

    @Test
    void publishesAndConsumesOrder() throws Exception {
        kafkaTemplate.send(
            "orders",
            "order-42",
            "ORDER_CREATED"
        ).get(10, TimeUnit.SECONDS);

        String received =
            listener.received().poll(10, TimeUnit.SECONDS);

        assertThat(received).isEqualTo("ORDER_CREATED");
    }
}
```

To prevent timing-dependent flakiness, real test suites should wait for listener assignment before sending records, use isolated topics/groups, and enforce bounded timeouts. This is a general Kafka testing principle, not a KRaft-specific change.

## 14. Lifecycle management and Spring Test context

`EmbeddedKafkaBroker` implements Spring's lifecycle interfaces. When the broker is registered via `@EmbeddedKafka` in a Spring Test context, let Spring manage initializing and destroying the broker.

If a test instantiates the broker manually:

- Initialize once in an appropriate fixture.
- Do not call `afterPropertiesSet()` repeatedly on the same instance.
- Call `destroy()` when all tests using the broker have completed.
- Close any producers/consumers created manually by the test.
- Do not leave brokers lingering inside a Gradle daemon or Maven Surefire fork.

When combining `@EmbeddedKafka` with `@SpringJUnitConfig`, consider `@DirtiesContext` if the suite hits races during JVM shutdown. This helps Spring close the application context before the broker and temporary directories are cleaned up. Do not add the annotation mechanically to every test because recreating the context can slow down the suite.

Use dedicated topics per test whenever possible. If reusing topics, explicitly control whether consumers seek to the beginning or end of partitions; embedded broker helpers may seek to the beginning by default.

## 15. Common errors after migration

| Error/symptom | Cause | Resolution |
|---|---|---|
| `cannot find symbol EmbeddedKafkaZKBroker` | Spring Kafka 4.0 removed the class | Switch to `EmbeddedKafkaKraftBroker` or inject `EmbeddedKafkaBroker` |
| `cannot find symbol EmbeddedKafkaRule` | JUnit 4 rule was removed | Migrate to JUnit Jupiter and `@EmbeddedKafka` |
| `kraft()` does not exist | 4.x annotation no longer has `kraft` attribute | Remove the attribute; KRaft is the default |
| `zookeeperPort` or `zkSessionTimeout` not found | ZooKeeper annotation properties removed | Remove ZooKeeper configurations |
| Cannot resolve `SPRING_EMBEDDED_ZOOKEEPER_CONNECT` | ZooKeeper constant no longer exists | Use `getBrokersAsString()` or bootstrap servers property |
| Broker does not bind to chosen port | KRaft embedded broker does not support custom ports | Use dynamic ports or a Kafka container |
| Topic creation fails due to replication factor | Replication factor exceeds test broker count | Adjust topic/internal topic replication to match broker count |
| Test hangs after version upgrade | Listener not yet assigned or client using wrong bootstrap property | Wait for assignment and check `spring.kafka.bootstrap-servers` |
| Tests behave flakily across classes | Global broker and per-class broker both write system properties | Pick one lifecycle strategy for the suite |
| Tests compile but fail at runtime due to Kafka client | `kafka-clients` overridden out of sync with Spring Kafka | Use compatible dependency management/BOM |

When hitting compile errors, look up removed classes/properties before altering test logic. When tests compile but cannot connect to the broker, check bootstrap servers, lifecycle, and ports before investigating listeners.

## 16. Step-by-step migration roadmap

Execute the migration on a reviewable branch:

1. Record the active versions of Spring Boot, Spring Kafka, `spring-kafka-test`, and Kafka client.
2. Search for all references to `EmbeddedKafkaZKBroker`, `EmbeddedKafkaRule`, and ZooKeeper properties.
3. If currently on Spring Kafka 3.3, add `kraft = true` to `@EmbeddedKafka` to move tests to KRaft first.
4. Migrate JUnit 4 Rules to JUnit Jupiter if the suite still uses JUnit 4.
5. Replace direct `EmbeddedKafkaZKBroker` constructors with `EmbeddedKafkaKraftBroker`, or better yet, use the `EmbeddedKafkaBroker` interface and annotation.
6. Replace fixed ports with dynamic bootstrap addresses.
7. Remove ZooKeeper constants and properties from tests.
8. If using the global broker on 3.x, enable `spring.kafka.embedded.kraft=true`; when moving to 4.x, remove this property.
9. Verify replication factors and broker properties in tests.
10. Upgrade Spring Kafka via dependency management compatible with Spring Boot and the Kafka client.
11. Run the full test suite, especially producer/listener, transaction, retry/DLT, and multi-broker tests.
12. Only remove direct ZooKeeper dependencies if no other part of the project uses them.

If a production Kafka cluster needs to be upgraded to 4.x, create a separate cluster migration plan. Do not perform cluster metadata operations as part of this test migration step.

## 17. Verification after moving to KRaft

A complete migration must verify test behavior, not just compilation.

| Check | Expected outcome |
|---|---|
| Test context startup | Spring creates `EmbeddedKafkaBroker` |
| Bootstrap property | Kafka client connects to the dynamic broker address |
| Producer send | Records are acknowledged by the broker |
| Listener receive | Listener receives the right keys/values/headers |
| Topic/partitions | Topics are created with the expected partition count |
| Consumer group | Listeners are assigned and commit offsets per config |
| Transaction test | Transaction commit/rollback works with matching internal topic replication |
| Retry/DLT test | Error handlers and DLT continue working |
| Lifecycle | Broker shuts down cleanly after the test suite |
| CI | Tests run in CI without depending on an external ZooKeeper service |

If the test suite uses both embedded brokers and Testcontainers, keep clear boundaries: which tests use the embedded broker and which need a container. Avoid letting a single test class accidentally read bootstrap servers from two different sources.

## 18. Checklist before upgrading to Spring Kafka 4

- No imports of `EmbeddedKafkaZKBroker` remain.
- No `EmbeddedKafkaRule`, `@ClassRule`, or JUnit 4 runners for embedded brokers remain.
- No references to `SPRING_EMBEDDED_ZOOKEEPER_CONNECT` remain.
- No `zookeeperPort`, `zkConnectionTimeout`, `zkSessionTimeout` remain.
- No `kraft` annotation attribute remains.
- No `spring.kafka.embedded.kraft` global property remains.
- Tests use the `EmbeddedKafkaBroker` interface or `EmbeddedKafkaKraftBroker`.
- Tests use JUnit Jupiter.
- Broker addresses are read dynamically, not hard-coded ports.
- Replication factors match the embedded broker count.
- Kafka client version is managed compatibly with Spring Kafka.
- Transaction, listener, retry, and DLT tests run on embedded KRaft.
- Broker and Spring context lifecycles close properly.
- CI does not require a separate ZooKeeper service to run embedded Kafka tests.

## 19. Key takeaways

- `EmbeddedKafkaZKBroker` is the legacy embedded Kafka implementation backed by ZooKeeper.
- `EmbeddedKafkaKraftBroker` was introduced in Spring Kafka 3.1.
- Spring Kafka 3.2 allows selecting KRaft with `@EmbeddedKafka(kraft = true)`.
- Spring Kafka 3.3 still defaults `@EmbeddedKafka` to ZooKeeper unless `kraft` is enabled.
- Spring Kafka 4.0 supports KRaft only, removing `EmbeddedKafkaZKBroker`, `EmbeddedKafkaRule`, ZooKeeper dependencies, and ZooKeeper attributes.
- The KRaft embedded broker does not support custom Kafka ports; obtain the address via `getBrokersAsString()` or the bootstrap property.
- Injecting the `EmbeddedKafkaBroker` interface reduces coupling to the implementation.
- Migrating the embedded broker is not migrating a production Kafka cluster.
- Tests must verify producers, listeners, assignments, transactions, and lifecycles after switching the broker.

Migrating the embedded broker from ZooKeeper to KRaft keeps the Spring Kafka test suite aligned with Apache Kafka's direction. Once API, JUnit, annotation, port, and lifecycle changes are handled properly, the test suite continues validating messaging flows without depending on ZooKeeper.

## References

- [Spring Kafka 3.3 – Testing Applications](https://docs.spring.io/spring-kafka/reference/3.3/testing.html)
- [Spring Kafka 4.1 – Testing Applications](https://docs.spring.io/spring-kafka/reference/testing.html)
- [Spring Kafka – Change History](https://docs.spring.io/spring-kafka/reference/appendix/change-history.html)
- [EmbeddedKafkaKraftBroker API](https://docs.spring.io/spring-kafka/docs/3.3.x/api/org/springframework/kafka/test/EmbeddedKafkaKraftBroker.html)
- [EmbeddedKafkaZKBroker API](https://docs.spring.io/spring-kafka/docs/3.3.x/api/org/springframework/kafka/test/EmbeddedKafkaZKBroker.html)
- [Apache Kafka – Upgrading to 4.0](https://kafka.apache.org/40/getting-started/upgrade/)
- [Apache Kafka – KRaft vs ZooKeeper](https://kafka.apache.org/44/getting-started/zk2kraft/)


