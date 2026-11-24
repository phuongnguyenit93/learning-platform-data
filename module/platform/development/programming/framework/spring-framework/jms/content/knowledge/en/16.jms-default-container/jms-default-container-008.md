# cacheLevel and Interaction with External Transactions

> **Context:** Default container in Spring Framework JMS. `DefaultMessageListenerContainer` (DMLC) can retain `Connection`, `Session`, and `MessageConsumer` to avoid recreating resources after each receive. However, when a listener is wrapped by an external `PlatformTransactionManager` (especially `JtaTransactionManager` in JTA/XA infrastructure), reusing JMS handles can affect **resource enlistment**—registering the JMS resource into the right transaction. Therefore, `cacheLevel` is a decision about **both performance and transaction correctness**.

## 1. Objectives and Key Questions

After this lesson, you can:

1. Distinguish `CACHE_NONE`, `CACHE_CONNECTION`, `CACHE_SESSION`, `CACHE_CONSUMER`, and `CACHE_AUTO`.
2. Explain why `CACHE_AUTO` usually resolves to `CACHE_CONSUMER` when DMLC **has no external transaction manager**, yet resolves to `CACHE_NONE` when **a manager is attached**.
3. Configure the cache level via `DefaultJmsListenerContainerFactory` for `@JmsListener`.
4. Inspect the **effective cache level after container initialization**, not merely `CACHE_AUTO` in source code.
5. Distinguish **local JMS session transactions**, `JmsTransactionManager`, `DataSourceTransactionManager`, and **JTA/XA transactions**.
6. Identify scenarios where reusing connections/sessions prevents the application server from properly enlisting the JMS resource into a transaction.
7. Run a Java 17/Spring Boot 3.3.5/Artemis demo with `sessionTransacted=true`, AUTO cache, listener, and assertions.
8. Plan benchmark and failure-injection tests when raising cache level in XA environments; never trade correctness for throughput.

**Keep in mind upfront:** DMLC `cacheLevel` is not a broker message cache, does not change JMS persistence, does not create XA by itself, does not guarantee exactly-once business side effects, and does not replace ACK/transactions.

## 2. Overview of `DefaultMessageListenerContainer`

A `@JmsListener` using `DefaultJmsListenerContainerFactory` typically executes via `DefaultMessageListenerContainer`. The container manages:

- JMS connections for talking to the broker;
- JMS sessions and acknowledgment/transaction mechanisms;
- JMS consumers bound to a queue, topic, or subscription;
- invoker threads and concurrency;
- the `receive(timeout)` → invoke handler → commit/rollback loop;
- recovery when the broker is temporarily unavailable;
- participation in an external transaction when a `PlatformTransactionManager` is configured.

~~~text
Spring @JmsListener
       |
       v
DefaultJmsListenerContainerFactory
       |
       v
DefaultMessageListenerContainer
       |
       +-- Invoker #1 -------------------------------------+
       |    obtain Connection / Session / MessageConsumer |
       |    receive -> listener -> commit/rollback        |
       |    cacheLevel determines whether handles are reused
       |
       +-- Invoker #2 (if concurrency >= 2) ---------------+
            has its own receive loop and appropriate resources
~~~

In a queue application processing thousands of messages, creating and closing every connection/session/consumer on each turn has significant overhead. In an XA system, reusing a session from a previous transaction can break how the coordinator requires resources to be **enlisted**. Both sides must be verified.

### 2.1. What Does "Cache" Cache Here?

| Layer | Example | What Is Cached? |
| --- | --- | --- |
| **DMLC internal cache** | `container.setCacheLevel(CACHE_SESSION)` | JMS handles managed directly by the listener container |
| **Spring JMS connection cache** | `CachingConnectionFactory` | Resources reused by the factory/wrapper |
| **Provider/server connection pool** | Artemis pool, Jakarta EE JNDI managed factory | Physical connections or handles leased from a pool |
| **Broker storage** | Artemis journal, paging, persistence | Message data on the broker |

These four layers are not equivalent. `CACHE_NONE` on DMLC means **the container does not retain handles across turns**, not that the server definitely opens and closes a new physical socket per message if an underlying factory still pools connections.

## 3. Table of DMLC's Five Cache Levels

Spring Javadoc defines:

| Constant | `int` | Resources Retained in DMLC | Meaning |
| --- | ---: | --- | --- |
| `CACHE_NONE` | 0 | No connection/session/consumer cached | Each turn acquires fresh JMS resources at the container layer |
| `CACHE_CONNECTION` | 1 | JMS `Connection` | Reuses connection; session/consumer are re-acquired |
| `CACHE_SESSION` | 2 | JMS `Connection` and `Session` | Reuses session too; consumer is re-acquired |
| `CACHE_CONSUMER` | 3 | `Connection`, `Session`, `MessageConsumer` | Highest reuse among actual cache levels |
| `CACHE_AUTO` | 4 | **Selected automatically** per transaction manager | Not a level "higher than 3" |

Per the API description, in native JMS environments each listener invoker can use its own retained JMS `Session`/`MessageConsumer`; handles are refreshed on errors/recovery.

### 3.1. Core Rule of `CACHE_AUTO`

~~~text
                  cacheLevel = CACHE_AUTO
                            |
                  DMLC initialize()
                            |
                 +----------+-----------+
                 |                      |
        Has external TM?         No external TM?
                 |                      |
                YES                    NO
                 |                      |
          CACHE_NONE (0)        CACHE_CONSUMER (3)
                 |                      |
        Acquire fresh resources Retain Connection,
        within transaction      Session, Consumer
~~~

**Why?** Some Jakarta EE application servers only enlist a JMS resource into an active XA transaction if the connection/session is freshly acquired **within that transaction**. Spring prioritizes compatibility by disabling internal caching when an external transaction manager is configured.

**Common trap:** having a `@Transactional` service or a `DataSourceTransactionManager` bean in the context is **not enough by itself** to change the cache level. The rule checks **the transaction manager attached to DMLC**, typically via `factory.setTransactionManager(...)`, not merely the existence of DB transactions elsewhere in the application.

### 3.2. Configuring Cache Level via API

On the container:

~~~java
// Snippet: container is DefaultMessageListenerContainer.
container.setCacheLevel(
        DefaultMessageListenerContainer.CACHE_SESSION);

// Or constant name:
container.setCacheLevelName("CACHE_SESSION");
~~~

On the factory:

~~~java
// Snippet: factory is DefaultJmsListenerContainerFactory.
factory.setCacheLevel(
        DefaultMessageListenerContainer.CACHE_AUTO);
factory.setConcurrency("2-4");
~~~

Import constants from `org.springframework.jms.listener.DefaultMessageListenerContainer`. `DefaultJmsListenerContainerFactory` has `setCacheLevel(Integer)` and `setCacheLevelName(String)`; pick **one** way to configure in real applications rather than setting two different levels back-to-back as if they accumulate.

### 3.3. Configured Level vs. Effective Level

When the factory is created:

~~~java
factory.setCacheLevel(DefaultMessageListenerContainer.CACHE_AUTO);
~~~

the intended value is AUTO = 4. However, inside `DefaultMessageListenerContainer.initialize()`, Spring replaces `CACHE_AUTO` with the effective level based on the transaction strategy. Therefore `getCacheLevel()` **on the container after initialization** may be 0 or 3.

Do not merely log the `CACHE_AUTO` constant and claim you measured the effective setting. In the example section, we retrieve the registered DMLC via `JmsListenerEndpointRegistry` to assert the actual level.

## 4. Local JMS Transactions and Caching

Setting:

~~~java
factory.setSessionTransacted(true);
factory.setCacheLevel(
        DefaultMessageListenerContainer.CACHE_AUTO);
~~~

and **not** setting an external transaction manager on the container causes `CACHE_AUTO` to typically pick `CACHE_CONSUMER`.

~~~text
DMLC invoker with cached Session/Consumer
       |
       +-- receive message #1
       +-- handle message #1
       +-- JMS Session.commit()
       |
       +-- receive message #2 on the same cached handle
       +-- listener throws exception
       +-- JMS Session.rollback()
       |         |
       |         +--> message #2 may be redelivered
       |
       +-- receive next message ...
~~~

Reusing a JMS session **does not** mean transaction #1 and #2 are the same transaction. With a transacted session, each `commit()`/`rollback()` ends the current transaction and the session begins a new one per JMS semantics.

### 4.1. Benefits of `CACHE_CONSUMER` Without an External TM

- Less overhead creating/closing sessions and consumers.
- Less resource churn on the broker side.
- Well-suited for long-lived listeners, steady queues, and controlled concurrency.
- Spring still provides recovery to refresh broken resources after broker failures.
- For native JMS listeners, it is an effective choice in many cases.

**Do not infer** "handles are never recreated", because recovery, scaling, reconfiguration, or shutdown can refresh consumers. Handle counts also depend on concurrency, each listener endpoint, and the provider.

### 4.2. Local JMS Commit Does Not Commit the DB

A risky scenario:

~~~text
JMS receive -> listener updates database
                         |
                         +-- JDBC COMMIT succeeds
                         |
                         X  process crashes before JMS COMMIT
                         |
                   Broker redelivery
                         |
                   DB may be updated a second time
~~~

Using `CACHE_CONSUMER` or `CACHE_NONE` **does not solve** two separate commits. For business correctness, you need stable event IDs and an idempotent consumer/deduplication in the same DB transaction, or an appropriate XA/outbox architecture.

## 5. What Is an External Transaction Manager?

On DMLC, `setTransactionManager(PlatformTransactionManager)` allows an external transaction manager to govern the receive loop and listener invocation. However, **not every `PlatformTransactionManager` is XA**.

| Strategy | Transaction Scope | Automatically Combines JMS + JDBC into an Atomic Transaction? |
| --- | --- | --- |
| `sessionTransacted=true`, no external manager | Local JMS session | No |
| `JmsTransactionManager` | Local JMS resource via Spring API | Does not automatically include DB |
| `DataSourceTransactionManager` | A JDBC DataSource | Does not automatically enlist JMS |
| `JtaTransactionManager` + XA-aware JMS/JDBC + real coordinator | Global JTA transaction with enlisted XA resources | Yes, if infrastructure/configuration is right |
| `@Transactional` on DB method while DMLC uses local JMS | DB transaction on method; separate local JMS | Not by default |

**Why does this affect caching?** Spring's `CACHE_AUTO` only checks whether DMLC has an external `PlatformTransactionManager`. Attaching `JmsTransactionManager` or a non-JTA manager can still cause AUTO to pick `CACHE_NONE`. That does not turn the transaction into XA.

### 5.1. `JmsTransactionManager`

`org.springframework.jms.connection.JmsTransactionManager` manages transactions for a JMS `ConnectionFactory`. It is useful for local JMS operations requiring Spring's transaction API, yet does not guarantee a JDBC `DataSource` joins the same transaction.

~~~java
// Spring @Configuration snippet; not a standalone program.
@Bean
JmsTransactionManager jmsTransactionManager(
        ConnectionFactory connectionFactory) {
    return new JmsTransactionManager(connectionFactory);
}
~~~

Requires imports `org.springframework.jms.connection.JmsTransactionManager`, `org.springframework.context.annotation.Bean`, and `jakarta.jms.ConnectionFactory`.

### 5.2. `DataSourceTransactionManager`

`org.springframework.jdbc.datasource.DataSourceTransactionManager` manages JDBC transactions. Setting it as the listener's `transactionManager` does not automatically register the JMS resource in a global transaction. Verify how callbacks ACK/commit JMS per policy rather than trusting the `transactionManager` property name.

### 5.3. `JtaTransactionManager`

`org.springframework.transaction.jta.JtaTransactionManager` is an adapter to a configured JTA transaction coordinator. Having JMS receive and JDBC update belong to the **same XA transaction** requires:
1. A JTA coordinator with recovery logs.
2. An XA-aware JMS connection factory/resource adapter registered with the coordinator.
3. An XA-capable datasource and database support.
4. The listener container wired with the proper `JtaTransactionManager`.
5. Thorough testing of transaction timeout, rollback, commit, and crash recovery.

Merely declaring `new JtaTransactionManager()` in a bare Spring Boot application **does not** create a complete XA coordinator or turn standard clients/DBs into XA.

## 6. Why Does Spring Disable Caching When JTA Participates?

Some application servers manage enlistment at handle-acquisition time. For example:

~~~text
Global transaction TX-101 BEGIN
       |
       +-- obtain JMS Connection and Session (fresh)
       +-- resource adapter enlists JMS into TX-101
       +-- receive message
       +-- update JDBC under same TX-101
       +-- JTA COMMIT / ROLLBACK
       |
Global transaction TX-102 BEGIN
       |
       +-- obtain JMS Connection and Session (fresh)
       +-- JMS resource enlisted into TX-102
       +-- receive and process
       +-- JTA COMMIT / ROLLBACK
~~~

If a session from TX-101 is retained and reused for TX-102, a server/provider may **fail to enlist the session properly** into TX-102. Consequences depend on infrastructure:
- transaction logs report an unenlisted resource or invalid transaction context;
- JMS receive is ACKed outside the transaction;
- DB rolls back yet the message is not redelivered;
- the resource stays tied to the old transaction;
- failures appear only on the second receive, or after failover.

Therefore, external TM defaulting to `CACHE_NONE` is the **broadly compatible** choice. Spring Javadoc also notes that some environments allow reusing at least `Connection` or even `Session` with an external TM. That capability is **not default**: it requires provider/server evidence and integration tests.

### 6.1. Can You Force Caching with JTA?

Yes:

~~~java
// Snippet: factory already has setTransactionManager(jtaManager).
factory.setCacheLevel(
        DefaultMessageListenerContainer.CACHE_CONNECTION);
~~~

This tells DMLC to reuse connections, differing from AUTO/NONE. Before moving to `CACHE_SESSION`, confirm XA enlistment still works when sessions are reused. `CACHE_CONSUMER` also retains consumers, requiring even stricter verification.

| Level in JTA | Expected Performance | Risks to Evaluate |
| --- | --- | --- |
| `CACHE_NONE` | Higher JMS handle churn | Safe compatibility baseline |
| `CACHE_CONNECTION` | Fewer connection creations | Does connection reuse preserve proper enlistment? |
| `CACHE_SESSION` | Fewer connection/session creations | Does session reuse confuse the XA coordinator across transactions? |
| `CACHE_CONSUMER` | Avoids consumer creation too | Consumer/session reuse, subscriptions, recovery, and enlistment |

**Do not conclude level 3 is always fastest**: it also depends on connection factory pooling, broker, consumer prefetch, receive timeout, scaling, and task executor. Throughput measurements must accompany correctness checks.

### 6.2. Mandatory Tests When Overriding in XA

- Send a message and confirm both JMS receive and JDBC update commit.
- Intentionally throw an exception before the listener completes: both DB and JMS must roll back if XA is guaranteed.
- Run **many** messages and sequential transactions: session reuse across transactions is where bugs hide.
- Failover/restart the broker or sever DB near commit time in a **test environment**.
- Inspect transaction coordinator logs, XA resource enlistment, and in-doubt states.
- Benchmark latency/throughput/connection churn under identical load with `CACHE_NONE` vs. the new level.
- Keep a rollback plan back to AUTO/NONE if incorrect behavior is observed.

Seeing the listener "receive a message" **does not prove** XA rollback works. What must be proved is **atomicity of JMS+DB state** under failure.

## 7. Runnable Example: `CACHE_AUTO` with Local JMS Transaction

The example uses Java 17, Spring Boot 3.3.5, and Apache ActiveMQ Artemis. The program:
- creates the default listener factory;
- enables `sessionTransacted=true`;
- configures `CACHE_AUTO`;
- **omits** any external transaction manager;
- retrieves the container via the registry **after initialization**;
- verifies the effective cache level is `CACHE_CONSUMER`;
- sends a `TextMessage` and receives it at `@JmsListener`.

### 7.1. Environment

Requires JDK 17+, Gradle, an Artemis broker at `tcp://localhost:61616`, a test anycast queue `demo.cache.local`, and credentials with send/consume permissions. For an isolated local demo broker, you can run:

~~~bash
docker run --detach --rm --name artemis-cache-test -p 61616:61616 -p 8161:8161 apache/artemis:latest-alpine
~~~

Wait until the broker is ready using `docker logs artemis-cache-test`. The demo image typically creates `artemis/artemis` credentials; only use default credentials on an isolated personal machine, **never in production**. When done: `docker stop artemis-cache-test`. Do not start another container if port 61616 is already occupied by another broker.

Pre-create the test queue or let the demo broker auto-create it. Do not point at a real business queue because the listener will receive/ACK messages.

### 7.2. Project Structure

~~~text
jms-cache-level-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/
    │   ├── CacheLevelApplication.java
    │   └── CacheLevelListener.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-cache-level-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
~~~

`src/main/resources/application.yml`:

~~~yaml
spring:
  main:
    web-application-type: none
  artemis:
    mode: native
    broker-url: "tcp://localhost:61616"
    user: "artemis"
    password: "artemis"
~~~

These credentials only illustrate a local broker. In other environments, override via `SPRING_ARTEMIS_USER`/`SPRING_ARTEMIS_PASSWORD` and `SPRING_ARTEMIS_BROKER_URL` or a secret manager. Never commit real credentials.

### 7.3. Listener Receiving the Exact Message

`src/main/java/demo/CacheLevelListener.java`:

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class CacheLevelListener {

    private final CountDownLatch received = new CountDownLatch(1);
    private volatile String expectedBody;

    public void expect(String value) {
        expectedBody = value;
    }

    @JmsListener(
            id = "cache-level-demo",
            destination = "demo.cache.local")
    public void onMessage(String body) {
        String expected = expectedBody;
        if (expected != null && expected.equals(body)) {
            received.countDown();
        }
    }

    public boolean await(long timeout, TimeUnit unit)
            throws InterruptedException {
        return received.await(timeout, unit);
    }
}
~~~

The listener uses `CountDownLatch` and a body carrying a unique run ID so stale messages do not falsely report success. Note that a stale message on the test queue can still be received and ACKed without triggering the latch; use a clean dedicated queue. This demo is not meant for concurrent requests against the same listener instance.

### 7.4. Application Configuring and Reading Effective Level

`src/main/java/demo/CacheLevelApplication.java`:

~~~java
package demo;

import java.util.UUID;
import java.util.concurrent.TimeUnit;

import jakarta.jms.ConnectionFactory;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.listener.DefaultMessageListenerContainer;
import org.springframework.jms.listener.MessageListenerContainer;

@SpringBootApplication
@EnableJms
public class CacheLevelApplication {

    private static final String QUEUE = "demo.cache.local";

    public static void main(String[] args) {
        SpringApplication.run(CacheLevelApplication.class, args);
    }

    @Bean("jmsListenerContainerFactory")
    DefaultJmsListenerContainerFactory defaultFactory(
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);

        // Native/local JMS session transaction.
        factory.setSessionTransacted(true);
        factory.setConcurrency("1");

        // Spring will resolve AUTO to CONSUMER when there is no external TM.
        factory.setCacheLevel(DefaultMessageListenerContainer.CACHE_AUTO);
        return factory;
    }

    @Bean
    ApplicationRunner verify(
            JmsListenerEndpointRegistry registry,
            JmsTemplate jmsTemplate,
            CacheLevelListener listener) {

        return args -> {
            MessageListenerContainer current =
                    registry.getListenerContainer("cache-level-demo");

            if (!(current instanceof DefaultMessageListenerContainer dmlc)) {
                throw new IllegalStateException(
                        "Expected DefaultMessageListenerContainer");
            }

            // DMLC is initialized: read the active cache level.
            int effective = dmlc.getCacheLevel();
            if (effective != DefaultMessageListenerContainer.CACHE_CONSUMER) {
                throw new IllegalStateException(
                        "Unexpected cache level: " + effective);
            }

            String id = UUID.randomUUID().toString();
            String body = "cache-probe:" + id;
            listener.expect(body);

            jmsTemplate.convertAndSend(QUEUE, body);

            if (!listener.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Listener did not receive probe within 10s");
            }

            System.out.println("EFFECTIVE_CACHE_LEVEL=CACHE_CONSUMER");
            System.out.println("LOCAL_JMS_TRANSACTION=true");
            System.out.println("LISTENER_RECEIVED=true");
        };
    }
}
~~~

**Key verification points:**

1. `@Bean("jmsListenerContainerFactory")` uses the exact default factory name for `@JmsListener` when `containerFactory` is omitted.
2. `@EnableJms` activates listener annotations.
3. `DefaultJmsListenerContainerFactory` creates `DefaultMessageListenerContainer` for the endpoint.
4. `setSessionTransacted(true)` enables a **local JMS transaction**, not XA.
5. Because `setTransactionManager(...)` is not set on the factory, `CACHE_AUTO` resolves to `CACHE_CONSUMER`. The code inspects the **actual container** via the registry instead of guessing from the factory.
6. `JmsTemplate.convertAndSend` converts the `String` to a `TextMessage` using the default converter and sends it to the test queue.
7. The listener uses a fresh run ID; the latch waits at most 10 seconds.
8. Latch completion only proves the method processed the exact body; **the container's JMS commit may happen after the method returns**, so do not cite this output as proof of final JMS commit.
9. If broker/queue/permissions are wrong, the demo does not falsely pass: it throws/times out.
10. The listener container stays running after printing; stop the app with `Ctrl+C` when finished.

### 7.5. Run and Stdout

In the project directory:

~~~bash
gradle bootRun
~~~

When the broker is ready, permissions and listener are valid, the lines printed by the app are:

~~~text
EFFECTIVE_CACHE_LEVEL=CACHE_CONSUMER
LOCAL_JMS_TRANSACTION=true
LISTENER_RECEIVED=true
~~~

Spring Boot/Artemis may print extra logs; the output above is **expected**, not a measurement across every environment. If `getCacheLevel()` does not match expectations, first check whether a transaction manager was attached to the factory by a custom configurer.

**Additional configuration note:** Spring Boot's auto-configured JMS listener factory typically uses the underlying/native `ConnectionFactory` for listeners so the container manages recovery itself. The demo injects `ConnectionFactory` directly to illustrate the API. In production, consider the Boot configurer in section 8 and inspect any wrapper.

## 8. Using the Boot Configurer Without Losing Defaults

In Spring Boot 3.x, instead of building a bare factory from scratch, you can apply `DefaultJmsListenerContainerFactoryConfigurer` to inherit Boot's settings before setting the cache level:

~~~java
// Spring Boot 3.x snippet in @Configuration; not runnable standalone.
@Bean("jmsListenerContainerFactory")
DefaultJmsListenerContainerFactory configuredFactory(
        ConnectionFactory connectionFactory,
        DefaultJmsListenerContainerFactoryConfigurer configurer) {

    var factory = new DefaultJmsListenerContainerFactory();
    configurer.configure(
            factory,
            ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory));

    factory.setCacheLevel(DefaultMessageListenerContainer.CACHE_AUTO);
    return factory;
}
~~~

Imports:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer;
import org.springframework.boot.jms.ConnectionFactoryUnwrapper;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.listener.DefaultMessageListenerContainer;
~~~

In Spring Boot 3, the configurer may attach an auto-detected `JtaTransactionManager`, or enable `sessionTransacted` by default when JTA is absent. Thus, **the exact same `CACHE_AUTO` setting can produce different effective levels** between local Boot and JTA environments.

Do not copy a Spring Boot 3 snippet verbatim to Boot 4 without checking auto-config packages/imports, as Boot 4 reorganized modules. When defining a custom listener factory, verify that converters, destination resolvers, transaction managers, and caching wrappers are passed to the right factory.

### 8.1. Distinguishing DMLC Cache from `CachingConnectionFactory`

A configuration may have two tiers:

~~~text
DefaultMessageListenerContainer
   |
   +-- internal cacheLevel = CACHE_CONSUMER
   |             |
   v             v
Spring CachingConnectionFactory (if wrapped)
                 |
                 v
        Native JMS ConnectionFactory
                 |
                 v
              Broker
~~~

`CachingConnectionFactory.sessionCacheSize` is a setting on the **factory wrapper**, not `DefaultMessageListenerContainer.cacheLevel`. If both layers reuse handles, connection counts and lifecycle become hard to reason about from one setter.

Spring Boot typically unwraps a cached factory before passing it to the auto-configured listener factory. Yet depending on provider/pool/JNDI managed connection factories, **not every wrapper has identical semantics**. With XA, prioritize the transaction coordinator/resource adapter guidance over any generic optimization rule.

## 9. Configuring a Factory for JTA/XA (Snippet, Not Runnable Standalone)

This example is **only for environments with a real JTA coordinator and a registered XA-aware JMS connection factory**:

~~~java
// Snippet in @Configuration with real xaJmsConnectionFactory and JTA.
@Bean("xaListenerContainerFactory")
DefaultJmsListenerContainerFactory xaListenerFactory(
        @Qualifier("xaJmsConnectionFactory")
                ConnectionFactory xaJmsConnectionFactory,
        JtaTransactionManager jtaTransactionManager) {

    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(xaJmsConnectionFactory);
    factory.setTransactionManager(jtaTransactionManager);
    factory.setCacheLevel(DefaultMessageListenerContainer.CACHE_AUTO);
    factory.setConcurrency("1-3");
    return factory;
}
~~~

Imports:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.listener.DefaultMessageListenerContainer;
import org.springframework.transaction.jta.JtaTransactionManager;
~~~

A listener selecting the factory above:

~~~java
// Snippet in @Component supporting JMS annotations.
@JmsListener(
    destination = "orders.xa",
    containerFactory = "xaListenerContainerFactory")
public void handle(String body) {
    // Perform DB operations via a DataSource enlisted in the same JTA.
}
~~~

With `CACHE_AUTO` and an external manager set on the factory, DMLC selects **`CACHE_NONE`**. However, the statement "global XA guarantees JMS+DB commit together" only holds **if** the JMS resource, JDBC resource, coordinator, and recovery are properly configured. Seeing `@Transactional` or `JtaTransactionManager` alone is insufficient.

### 9.1. Do Not Use Cache to Fix Missing Transactions

If you have:

~~~text
DB COMMIT succeeds
          |
          X JVM crashes before JMS COMMIT
          |
   message may redeliver
          |
     duplicate business side effect
~~~

switching `CACHE_CONSUMER` to `CACHE_NONE` does not merge two commits into one. That is a **dual-write/commit boundary problem**, usually solved via an idempotency key in the DB, or XA coordination if requirements and infrastructure permit.

### 9.2. `@Transactional` Inside a Listener

A method annotated with `@Transactional` uses whichever transaction manager Spring selects for that call; with multiple managers, ensure proper selection. The container's local JMS session transaction normally begins before and ends after the listener. A method's JDBC transaction can commit before the JMS commit, and they are **not in one global atomic transaction** merely because both use Spring.

Therefore, tests should include a case where the DB wrote yet JMS rolled back, ensuring the consumer processes idempotently.

## 10. Cache Level, Concurrency, and Subscriptions

### 10.1. Multi-Consumer Queues

If a factory uses `setConcurrency("3-6")`, DMLC can create at least 3 consumer invokers and scale up to 6 under load. With `CACHE_CONSUMER`, each invoker usually retains its corresponding session/consumer. When raising concurrency, measure:

- JMS consumer counts on the broker;
- session/connection counts in pools/providers;
- processing latency and queue age;
- DB pool capacity and concurrent side effects;
- whether message ordering still meets requirements.

There is no overall strict ordering guarantee when multiple consumers pull from one queue. Concurrency tuning and `cacheLevel` are two separate axes.

### 10.2. Non-Durable Topic Subscriptions

The Spring reference warns: **without caching**, the container may recreate connections/sessions on each receive cycle. With a **non-durable topic subscription** under high load, the subscription may vanish in between and drop messages. Therefore:
- Do not apply `CACHE_NONE` to an important non-durable topic without testing this condition.
- If offline delivery is needed, configure a durable subscription properly with `clientId`/subscription name and your JMS provider.
- Verify shared/non-shared subscription semantics before raising concurrency.
- Do not treat producer persistent delivery mode as a substitute for a durable subscription.

### 10.3. Recovery

DMLC has built-in recovery after broker failures and can recreate handles even at high `cacheLevel`. Spring Framework by default retries per `BackOff`/recovery interval of roughly 5 seconds. When consumer counts fluctuate, inspect recovery logs and broker restarts before concluding the cache policy failed.

## 11. Performance and Correctness Testing

Changing cache level requires at least two test suites.

### 11.1. Positive Cases

| Test | Condition | Expectation |
| --- | --- | --- |
| P01 | `sessionTransacted=true`, no external TM, AUTO | DMLC effective `CACHE_CONSUMER` |
| P02 | external TM set, AUTO | DMLC effective `CACHE_NONE` |
| P03 | Local JMS, listener succeeds | JMS transaction commits after handler per container |
| P04 | Local JMS, listener throws exception | JMS rollback/redelivery per broker policy |
| P05 | Full JTA/XA, listener + JDBC update | JMS and DB enlist/commit in the same global transaction |
| P06 | JTA/XA, JDBC update fails | Both JMS receive and DB update roll back |
| P07 | Provider supports reuse, switch NONE → CONNECTION | P05/P06 still pass; measure real overhead reduction |
| P08 | Broker restart during test | DMLC recovers and processes pending messages properly |

### 11.2. Negative/Failure Cases

| Test | Scenario | What to Verify |
| --- | --- | --- |
| N01 | Local JMS DB commits, kill before JMS commit | Redelivery is handled idempotently |
| N02 | JMS XA resource is not enlisted | Transaction logs and data prove the failure |
| N03 | Cached XA session carries stale transaction state | Test many sequential transactions, not just one message |
| N04 | Broker disconnects then recovers | Handles are refreshed and listener resumes |
| N05 | `CACHE_NONE` and non-durable topic | Check for message gaps during subscription churn |
| N06 | Concurrency exceeds DB pool | Backlog, timeouts, error rate |
| N07 | `AUTO_ACKNOWLEDGE` used instead of transacted | Failing handler may not redeliver |
| N08 | Both DMLC and factory cache | Measure resource reuse at each tier accurately |
| N09 | Wrongly set `DataSourceTransactionManager` as DMLC TM | JMS does not automatically join XA |
| N10 | Change cache in production without rollback plan | Unable to compare or safely revert config |

Only perform broker/DB kills and failure injection in **test environments**, never deleting production journals/queues. Do not declare XA "working" based solely on listener stdout.

## 12. Real-World Telemetry to Distinguish Issues

Record for each test:
- Spring Framework/Boot/JMS provider versions.
- Configured `cacheLevel` on the factory and `getCacheLevel()` after initialization on DMLC.
- Actual manager class attached to DMLC; whether a JTA coordinator/XA resources exist.
- Connection factory type, wrappers, vendor pool/JNDI configuration.
- Queue/topic, subscription mode, concurrency, receive timeout.
- Broker connection/session/consumer counts, reconnect/recovery logs.
- Transaction IDs, resource enlistment, rollback/commit evidence.
- Event IDs, JMS redelivery counts, DB deduplication/side-effect outcomes.
- Throughput, p95/p99 latency, CPU/memory, and connection churn.

If `getCacheLevel()` is 0 yet physical sockets are still reused, that may be a provider pool; there is no contradiction with internal `CACHE_NONE`. If `getCacheLevel()` is 3 yet the broker reports a new connection after restart, that may be recovery, not caching "failing to work".

### Symptom-Based Diagnosis

| Symptom | What to Check |
| --- | --- |
| AUTO unexpectedly became NONE | Did a configurer attach an external manager to the factory? |
| AUTO stayed CONSUMER despite JDBC `@Transactional` on service | Was the DB manager actually set on DMLC? |
| JMS did not roll back with DB in XA | Resource adapter/JNDI XA factory, transaction enlistment, manager selection |
| `CACHE_SESSION` fails starting from the second message | Does the provider support reusing a session across multiple JTA transactions? |
| Consumer count rose after raising concurrency | Scaling settings and provider limits; `cacheLevel` does not create messages |
| Messages processed twice | Redelivery/producer retries/idempotency, not just caching |
| Connection error after broker restart | DMLC recovery, stale wrapper resources, broker/TLS credentials |
| Low throughput with `CACHE_NONE` | Measure session creation and pools; override only if correctness tests pass |
| Messages lost on non-durable topic | Subscription recreation/no cache, topic durability semantics |
| Boot custom factory behaves differently from defaults | Use Boot configurer and check cache/transaction policies |

## 13. Decision Checklist

- [ ] Correctly identified `DefaultMessageListenerContainer`, not confused with `SimpleMessageListenerContainer`.
- [ ] Know all 5 cache constants and their integer values.
- [ ] Understand `CACHE_AUTO` picks **`CACHE_CONSUMER` without an external TM** and **`CACHE_NONE` with an external TM**.
- [ ] Read the effective level from the container after Spring initializes.
- [ ] Know whether the listener uses local JMS, `JmsTransactionManager`, `DataSourceTransactionManager`, or JTA/XA.
- [ ] For XA, verify JMS `ConnectionFactory`/DB `DataSource`/coordinator support and proper enlistment.
- [ ] Do not use `cacheLevel` to solve dual-write or exactly-once business side effects.
- [ ] Have an idempotent consumer when JDBC and JMS transactions are separate.
- [ ] When overriding cache in XA, ran multi-transaction rollback/recovery tests.
- [ ] Distinguished DMLC caching from `CachingConnectionFactory` and vendor connection pooling.
- [ ] Checked queue/topic/durable subscription/concurrency interactions.
- [ ] When using a Spring Boot custom factory, preserved appropriate configurer/native factory behavior.
- [ ] Have metrics and logs for resource handles, transaction outcomes, and redeliveries.
- [ ] Have a plan to revert to AUTO/NONE if an optimization breaks atomicity.

### Self-Check Questions

1. What numeric value does `CACHE_AUTO` have, and does it cache the most?
2. Which JMS handles do `CACHE_CONNECTION`, `CACHE_SESSION`, and `CACHE_CONSUMER` retain?
3. Why does `CACHE_AUTO` choose `CACHE_NONE` when DMLC has an external transaction manager?
4. If only `sessionTransacted=true` is enabled with no external manager set, what is the expected effective cache?
5. Why might an app server fail to enlist a cached JMS `Session` into a new XA transaction?
6. Is `JmsTransactionManager` synonymous with `JtaTransactionManager`?
7. Does `@Transactional` on a JDBC method make DMLC automatically choose `CACHE_NONE`?
8. Why is raising `cacheLevel` in JTA only safe after testing rollback of both JMS and DB?
9. Are DMLC `cacheLevel` and `CachingConnectionFactory.sessionCacheSize` the same?
10. Why can a non-durable topic subscription lose messages if consumers are continuously recreated?
11. Why must you read `getCacheLevel()` after initialization instead of just printing the configuration?
12. If the DB commit finishes yet JMS commit has not finished and the JVM crashes, what can happen?
13. If latency improves yet an XA failure test fails, which configuration should go to production?

**Conclusion:** `CACHE_AUTO` is a sensible starting point: **local JMS/no external manager → `CACHE_CONSUMER`**, **with external manager → `CACHE_NONE`**. Disabling caching under external transactions protects resource enlistment compatibility, rather than being a gratuitous slowdown. Override only when infrastructure supports it and **transaction correctness has been proved ahead of throughput**.

## References

1. Spring Framework 6.2 — `DefaultMessageListenerContainer` Javadoc, constants, and `setCacheLevel`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html
2. Spring Framework — Message Listener Containers and transaction management: https://docs.spring.io/spring-framework/reference/integration/jms/using.html
3. Spring Framework — Receiving a Message and JTA: https://docs.spring.io/spring-framework/reference/integration/jms/receiving.html
4. Spring Framework — Annotation-driven JMS Listener Endpoints: https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html
5. Spring Framework 6.2 — `DefaultJmsListenerContainerFactory`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html
6. Spring Boot 3.x — JMS/Artemis and transactional listener defaults: https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html
7. Spring Boot — Messaging how-to, listener factory, and native connection factory: https://docs.spring.io/spring-boot/how-to/messaging.html
8. Jakarta Messaging 3.1 Specification — Sessions, transactions, and acknowledgement: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
