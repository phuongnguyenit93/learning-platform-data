# Closing Resources and Graceful Shutdown in Spring JMS

> **Context:** Spring Framework JMS, Jakarta Messaging (`jakarta.jms`), Java 17+, and Spring Boot applications. The goal is to stop producers/consumers in the right order, give in-flight work a chance to finish, preserve message state on failures, and cleanly release connections/sessions/consumers and related resources.

## 1. What Does "Safe Application Shutdown" Mean?

A JMS process usually holds **broker connections**, **send/receive sessions**, **producers**, **consumers**, **listener containers**, business-processing threads, and other resources like databases, thread pools, or HTTP clients. Closing a TCP socket does not mean in-flight work is finished.

A controlled shutdown must achieve three outcomes together:

1. **Stop accepting new work beyond the allowed shutdown window.** Internal producers stop emitting new messages; listener containers stop accepting more deliveries when asked to stop.
2. **Handle already-received messages cleanly:** finish business logic and commit/ack, or roll back so eligible messages can be redelivered. Never declare "success" just because a method ran partway through.
3. **Release resources via their proper owners:** close resources created directly by application code; let Spring and connection pools close resources they manage. Closing must occur only after no active work needs them.

**Graceful shutdown** does not promise "zero message loss under all circumstances" or "exactly once." It provides a bounded window for orderly completion and cleanup. Under `kill -9`, power loss, exceeding orchestrator grace timeouts, broker/DB stopping first, or network partitions, the application still needs **retries/redelivery and idempotency**.

### Distinguishing Commonly Confused Verbs

| Action | Meaning | What must NOT be inferred |
| --- | --- | --- |
| **Pause / Stop delivery** | Prevents connections or listeners from receiving more messages while paused | Does not permanently close connections; does not guarantee all received messages committed |
| **Finish handler** | Business code returned without throwing | Does not prove data outside the JVM committed or the broker acknowledged |
| **Ack / Commit** | Confirms to the broker per acknowledge mode or JMS transaction | Does not automatically synchronize with DB transactions or HTTP side effects |
| **Rollback** | Cancels uncommitted JMS work; message may be redelivered | Does not undo already-sent emails or committed database transactions |
| **Close / Destroy** | Releases sessions, consumers, connections, pools/containers | Cannot replace retry design, idempotency, or crash recovery procedures |

## 2. Who Owns Which Resource?

### 2.1. The JMS Resource Hierarchy

~~~text
ConnectionFactory  --create--> Connection / JMSContext
                                    |
                                    +---> Session  --create--> MessageProducer
                                    |                 \-----> MessageConsumer / Listener
                                    |
                                    +---> (shared sessions, depending on provider/pool)
~~~

**`ConnectionFactory` is a factory**, not an already-open connection in all cases. It may be a provider factory, proxy, JNDI-managed object, caching wrapper, or connection pool. Policies for closing factories/pools depend on **ownership**, not solely on the Java type.

| Usage pattern | Who creates/holds the resource? | Who closes it and when? |
| --- | --- | --- |
| Direct JMS API `factory.createConnection()` | App code creates the connection directly | App calls `close()` / try-with-resources |
| Direct JMS API `factory.createContext()` | App creates `JMSContext` | App calls `context.close()` / try-with-resources |
| Manually created `Session`, `MessageProducer`, `MessageConsumer` | App creates children of connection/session | Close when done; closing session/connection closes children |
| `JmsTemplate` + Spring-managed `ConnectionFactory` | Spring manages connection/session/producers for template calls | Caller **must not** retain and close sessions used by the template |
| `@JmsListener` | Spring creates and manages listener containers, sessions, and consumers | Container/`ApplicationContext` coordinates stop and destroy |
| Container-managed `CachingConnectionFactory` / pool | Spring/Boot/pool retains connections for reuse | Calling close on a borrowed handle follows contract; **pool** is destroyed when its owning bean closes |
| External broker | Owned by infrastructure / broker ops team | Stopping **the app** must never shut down a shared broker |

**Simple rule:** Whoever creates the underlying resource and controls its lifecycle is responsible for closing it. Through a proxy/pool, calling `close()` on a **handle** may only return it to the cache rather than closing the physical socket; that is by design.

### 2.2. What Happens to Children When the Parent Closes?

Per Jakarta Messaging:

- `Connection.close()` closes the connection's `Session`, `MessageProducer`, `MessageConsumer`, and browser objects. You do not need to close each session right before closing the connection just to repeat work.
- `Session.close()` closes consumers/producers created from that session; the parent connection can remain open for other sessions.
- `MessageConsumer.close()` stops delivery to that consumer; it **does not automatically commit/ack/roll back** messages tied to the session's transaction or acknowledgement state.
- `JMSContext.close()` closes the context's session and its consumers/producers; the underlying connection is also closed once no active contexts share it, per `JMSContext` connection-sharing rules.
- Closing an already-closed connection/session is required by the spec not to throw errors; still, shutdown logic should avoid redundant closes from multiple places and avoid confusion with proxies/pools.

**Never call `Connection.close()` or `Session.close()` on the listener's own connection/session from inside `onMessage`.** The spec allows providers either to throw `IllegalStateException` or handle closing differently; behavior is non-portable. In Spring, stop containers via lifecycle from a management thread or context shutdown.

## 3. How "Stop" Differs from "Close" in Raw JMS

### 3.1. `Connection.stop()` Temporarily Pauses Delivery

- After `connection.stop()`, message delivery to the connection's consumers pauses; `connection.start()` resumes receiving.
- A `stop()` call must wait for any **currently executing** `MessageListener` calls to return before completing; it can block if a handler runs long.
- Sending messages over the connection can still proceed while stopped; do not use `stop` as a producer-blocking mechanism.
- For synchronous receives, timeout timers keep running; `receive(timeout)` can return `null` when time expires, even while stopped.
- `stop()` **does not** destroy connections/sessions and does not automatically commit or roll back transactions.

### 3.2. `Connection.close()` Ends the Lifecycle

- `close()` blocks until running listeners return and pending receives finish per Jakarta Messaging rules; orchestrator shutdown timeouts must account for that wait.
- A waiting `receive()` can return a message or `null` during close depending on timing; **do not** treat "receiving `null`" as a definitive shutdown signal.
- Closing while an **uncommitted local transacted Session** is open rolls back that transaction; never treat it as `commit()`.
- Closing **does not auto-acknowledge** unacknowledged messages under `CLIENT_ACKNOWLEDGE`.
- After close, further use of the connection/session/consumer fails (aside from redundant close calls permitted by the spec); already-retrieved `Message` bodies may remain readable, though calling `acknowledge` on a closed session is invalid.

### 3.3. Never Close the Connection Inside a Listener Callback

Suppose a handler processing `OrderPlaced` calls `connection.close()`. The caller may block waiting for its own callback to finish or throw a provider-specific exception, creating unpredictable behavior and stranding acknowledgements. If you ever need to stop a consumer upon receiving a "control message," **signal an external management thread** so Spring lifecycle or a dedicated coordinator decides to stop; let the handler finish within its active transaction.

## 4. Acknowledgements and Transactions Decide the Fate of In-Flight Messages

### 4.1. Moments Where Duplicates or Loss Occur

~~~text
Message resides in broker
    |
    v
Consumer receives ------------------> Business processing
    |                                      |
    |                                      +--> DB commit / API call / file write
    |                                      |
    |                                      v
    |                             JMS ACK or JMS COMMIT
    |                                      |
    v                                      v
Not yet completed                       Broker considers completed
~~~

Two classic failure windows:

- **Business work finished, JMS ack/commit not sent yet:** the app exits abruptly; the broker can redeliver the same message. If the action sent an email or debited funds, an idempotency key is needed to avoid repeating it.
- **JMS marked successful before side effects finished:** a later failure prevents redelivery even though the business side effect never completed. With certain listener containers/ack modes, this happens earlier than you might expect.

### 4.2. Impact of Acknowledge Modes

| Mode | What to know during shutdown |
| --- | --- |
| `AUTO_ACKNOWLEDGE` | API vs. listener container behavior can differ; with Spring's `DefaultMessageListenerContainer`, a message may be acked before the listener runs, so errors/stops may not yield reliable redelivery |
| `CLIENT_ACKNOWLEDGE` | App calls acknowledge explicitly; closing the session/connection **does not auto-acknowledge** unconfirmed messages |
| `DUPS_OK_ACKNOWLEDGE` | Can defer acknowledgements and produce duplicates; never use to promise "exactly once" |
| **Transacted JMS Session** | Commits after successful processing; rolls back on failure or if closed before commit. Spring listeners can manage commit/rollback for you |

For queue/durable-topic workloads requiring reliability, a **transacted session** on the listener container is usually the right starting point. In Spring:

~~~java
DefaultJmsListenerContainerFactory factory = new DefaultJmsListenerContainerFactory();
factory.setConnectionFactory(connectionFactory);
factory.setSessionTransacted(true);
~~~

This is only a **configuration snippet** placed in a `@Configuration` `@Bean` with proper imports, not a standalone Java file. With Spring Boot, consider Boot's configurer to inherit converter/transaction/recovery settings before tuning.

### 4.3. A JMS Transaction Does Not Automatically Include the Database

Inside a listener with a local JMS transaction:

1. The app receives the message in a transacted session.
2. The handler executes SQL or calls an external service.
3. Spring or application code commits JMS when the handler succeeds.

If the database commits yet the JVM dies before JMS commits, the broker can redeliver. Conversely, misconfigured independent transactions can leave inconsistent state.

Common solutions: **idempotent consumers**, inbox/dedup tables keyed by `messageId` or business ID, transactional outbox for publishing, plus retry/DLQ policies; use XA/JTA only when genuinely required to coordinate resources atomically and after weighing its operational cost.

**Therefore:** graceful shutdown gives handlers time to finish, while **idempotency** protects against shutdowns that cannot finish cleanly.

## 5. Intentional Shutdown Sequence

A practical deployment sequence for a service handling both HTTP requests and JMS consumption:

1. **Receive stop signal:** SIGTERM, `ApplicationContext.close()`, deploy/scale-down, or admin stop. Avoid `SIGKILL`/`kill -9` whenever possible.
2. **Enter draining state:** flip readiness to "not ready" so load balancers stop sending new HTTP traffic per policy, while keeping liveness healthy so the process can finish. Kubernetes readiness **does not automatically stop JMS listeners**.
3. **Stop generating new work:** halt schedulers/timers/pollers and reject or cleanly gate new requests that publish JMS messages. Do not tear down `ConnectionFactory` while producers still need to send replies.
4. **Ask JMS listener containers to stop receiving:** Spring `SmartLifecycle`/`JmsListenerEndpointRegistry` handles this when closing `ApplicationContext`. Do not open new consumers during shutdown.
5. **Wait for in-flight handlers** within an adequate time budget. Running handlers must finish and commit, or throw to trigger rollback/retry. If interrupted, restore the interrupt flag and stop performing side effects.
6. **Release resource owners:** only after listeners have stopped, destroy Spring-managed sessions/consumers, caches/pools, and connections. Custom shutdown callbacks must follow proper lifecycle ordering.
7. **Record final metrics:** log completed handler counts, duration, retries/DLQ, backlog, and remaining open connections; exit within the orchestrator's allowed window.
8. **Next replica starts:** the broker keeps unfinished messages for other consumers per ack/transaction/retention rules. Do not treat another replica running as proof that old in-flight tasks completed.

~~~text
          SIGTERM / Context close
                    |
           [stop creating new tasks]
                    |
           [stop JMS consumers]
                    |
              +-----+------+
              |            |
      [handler completes]  [handler fails / budget exhausted]
              |            |
      [JMS commit/ack]   [rollback/redelivery per policy]
              |            |
              +-----+------+
                    |
       [destroy listener / resources]
                    |
          [pool/connection cleanup]
                    |
               JVM exit
~~~

**Ordering is not rigid for every architecture.** If a consumer must **publish a reply** to finish its job, the reply producer/connection must stay alive until the consumer finishes. If an HTTP endpoint feeds new jobs upstream, block HTTP writes before stopping consumers or define an explicit handoff boundary. Actual dependencies dictate stop phases.

## 6. How Spring JMS Manages Stopping

### 6.1. `JmsTemplate`

`JmsTemplate` is an operation-scoped adapter: it acquires resources from `ConnectionFactory` for a callback/send/receive and returns/releases them per policy. With `JmsTemplate.convertAndSend`, you never obtain a `Session` to close manually.

Do not write:

~~~java
// Not a sound resource-management pattern:
session = obtainSessionSomehow();
jmsTemplate.convertAndSend("orders.in", "x");
session.close(); // This session is not the session Spring uses to send!
~~~

This is an **illustrative anti-pattern**, not compilable standalone code. `JmsTemplate` does not need `close()` after each `send()`; Spring beans manage the lifecycle of the underlying connection sources.

With `CachingConnectionFactory`, sessions/consumers may be cached for reuse. Closing a borrowed handle returns it to the cache. **Never call `cachingConnectionFactory.destroy()` while listeners or producers are still active.** Caching suitable for templates does not mean sharing that same cache with listener containers; `DefaultMessageListenerContainer` normally manages caching within its own lifecycle, and Spring docs warn against external consumer caching interfering with listener stops and dynamic scaling.

### 6.2. `@JmsListener` and Listener Containers

`@JmsListener` is an endpoint annotation. With `@EnableJms`/auto-configuration, Spring creates `MessageListenerContainer` instances and `JmsListenerEndpointRegistry` to manage annotation-driven containers. A single listener cannot turn closing its session into stopping the whole application.

**`DefaultMessageListenerContainer`** is the common container; it holds consumer tasks, supports stop/restart, and handles broker recovery. The container participates in lifecycle, and `SmartLifecycle.stop(Runnable callback)` guarantees the callback fires only after listener processing has actually stopped.

Brief example illustrating lookup (never call per message):

~~~java
// Snippet in a Spring management class, not inside a @JmsListener handler.
MessageListenerContainer container =
        registry.getListenerContainer("ordersListener");
if (container != null && container.isRunning()) {
    container.stop();
}
~~~

Requires an injected `JmsListenerEndpointRegistry registry` and importing `org.springframework.jms.listener.MessageListenerContainer`. The endpoint must declare `id="ordersListener"`. This can **temporarily pause consumption** while the app stays alive; during normal shutdown, let `ApplicationContext` and the registry handle stopping rather than having listeners stop themselves.

**Subtle detail:** a `stop()` call or lifecycle callback does not cut off message reception at a single mathematical nanosecond. Receives can be in flight right around the stop boundary. `acceptMessagesWhileStopping` defaults to `false` on the relevant Spring listener containers; rejecting messages during stop can increment broker retry counts depending on the provider. Setting it to `true` lets extra messages process while stopping and **can lengthen draining**, so weigh retry tolerance against shutdown time. On `DefaultJmsListenerContainerFactory`, do not assume every container setting has a factory setter; check your Spring version's API for fine-grained tuning.

### 6.3. `SmartLifecycle` and Stop Ordering

Spring invokes `SmartLifecycle` beans by **phase**:

- On startup: lowest phase first, highest last.
- On shutdown: highest phase first, lowest last.
- With `stop(Runnable callback)`, the coordinator waits for the callback to know that phase finished, up to the configured phase timeout.
- Beans with explicit dependency relationships also follow dependency order. Never tweak phases arbitrarily just to "stop fast" if it tears down a dependency still needed by consumers.

For example, if a JMS handler needs a database pool to finish its transaction, ensure the pool remains alive while listeners drain. `@PreDestroy` on a business bean is **not** the right sole place to coordinate all in-flight consumers; destroy callbacks normally run after stop phases in a clean shutdown, ordered by Spring bean dependencies.

**Do not alter default phases blindly.** When you need custom ordering across producers, schedulers, listeners, and resource pools, map out dependencies, verify with shutdown tests, and then use `setPhase(...)` or a dedicated `SmartLifecycle`.

### 6.4. Spring Boot Graceful Shutdown Is Not an Automatic JMS "Cure-All"

In Spring Boot, closing `ApplicationContext` triggers stop/destroy lifecycles across beans, including managed JMS listeners. The property:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=30s
~~~

sets the **timeout per shutdown phase**, **not a single global cap for the entire process**. If multiple phases and cleanup steps wait, total shutdown time can exceed 30 seconds.

In Spring Boot 3.5, web servers support graceful shutdown on context close. `server.shutdown` primarily governs the **HTTP server**; never assume `server.shutdown=graceful` solves JMS message/transaction draining by itself. Combine `spring.lifecycle.timeout-per-shutdown-phase` with proper JMS listener/reliability settings.

### 6.5. JVM Shutdown Hooks, IDE Stops, and OS Signals

A typical Spring Boot process registers a JVM shutdown hook to close the context. Terminal `Ctrl+C` or an orchestrator's SIGTERM triggers that hook. Forced kills, JVM crashes, power outages, or IDE "force stop" actions bypass shutdown phases. **Never build a system that relies solely on shutdown hooks to save data**; always rely on broker/DB recovery.

## 7. Java 17 + Spring Boot 3.5 Lab: Observing In-Flight Messages During Stop

This lab uses **embedded Apache ActiveMQ Artemis**, one queue, and a single-consumer listener; each message takes ~4 seconds to process. Stopping right after a message begins shows Spring waiting for the handler before exiting via lifecycle. This tests **stop timing and JMS transactions**, not forced crashes or exactly-once guarantees.

### 7.1. Creating the Project

Using https://start.spring.io/, choose:

- Maven, Java, **Spring Boot 3.5.x**, Java 17+.
- Group `com.example`, artifact `jms-shutdown-lab`, package `com.example.jmsshutdown`.
- Dependency **Spring for Apache ActiveMQ Artemis** (`spring-boot-starter-artemis`).

In the `pom.xml` generated by Spring Initializr, add inside `<dependencies>`:

~~~xml
<dependency>
    <groupId>org.apache.activemq</groupId>
    <artifactId>artemis-jakarta-server</artifactId>
</dependency>
~~~

Let Spring Boot's parent/BOM manage the Artemis version; this example targets Boot **3.5** because auto-configuration packages shift across major versions. The embedded broker is for local lab use and does not represent production persistence or high availability.

File `src/main/resources/application.properties`:

~~~properties
spring.application.name=jms-shutdown-lab
spring.artemis.mode=embedded
spring.artemis.embedded.queues=orders.in
spring.lifecycle.timeout-per-shutdown-phase=30s
~~~

No web server is required to practice a JMS listener; the Artemis starter and listener threads keep the lab running. In real web apps, configure HTTP graceful shutdown per your Boot version.

### 7.2. Complete Java Code

Save in `src/main/java/com/example/jmsshutdown/JmsShutdownLabApplication.java`:

~~~java
package com.example.jmsshutdown;

import java.util.concurrent.TimeUnit;

import jakarta.jms.ConnectionFactory;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer;
import org.springframework.boot.jms.ConnectionFactoryUnwrapper;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableJms
public class JmsShutdownLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(JmsShutdownLabApplication.class, args);
    }

    @Bean("ordersListenerFactory")
    DefaultJmsListenerContainerFactory ordersListenerFactory(
            ConnectionFactory connectionFactory,
            DefaultJmsListenerContainerFactoryConfigurer configurer) {

        var factory = new DefaultJmsListenerContainerFactory();

        // Inherit Boot's auto-configured JMS settings.
        configurer.configure(factory,
                ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory));

        // Rollback/redelivery if the handler throws.
        factory.setSessionTransacted(true);

        // Single consumer to observe ordering in the lab.
        factory.setConcurrency("1");
        factory.setReceiveTimeout(1000L);
        return factory;
    }

    @Bean
    ApplicationRunner seedJobs(JmsTemplate template) {
        return args -> {
            for (int i = 1; i <= 3; i++) {
                String id = "job-" + i;
                template.convertAndSend("orders.in", id);
                System.out.println("PUBLISHED " + id);
            }
        };
    }

    @Component
    public static class OrdersWorker {

        @JmsListener(
                id = "ordersListener",
                destination = "orders.in",
                containerFactory = "ordersListenerFactory")
        public void handle(String jobId) {
            System.out.println("BEGIN " + jobId);

            try {
                TimeUnit.SECONDS.sleep(4);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                // Throw so the transacted session does not commit as success.
                throw new IllegalStateException(
                        "Interrupted while processing " + jobId, ex);
            }

            System.out.println("DONE " + jobId);
        }
    }
}
~~~

**Why is the code structured this way?**

- `JmsTemplate` uses Boot's `ConnectionFactory` to publish three strings into the queue.
- `ordersListenerFactory` uses `DefaultJmsListenerContainerFactoryConfigurer` to retain Boot's required settings; in Boot 3.5, `ConnectionFactoryUnwrapper.unwrapCaching` unwraps the caching wrapper for the listener container, avoiding sharing a bounded cache with consumer containers.
- `setSessionTransacted(true)` marks a message finished for JMS only when the listener's transaction commits; throwing an exception triggers container rollback. It does not automatically include a hypothetical database in the same transaction.
- `setConcurrency("1")` keeps observation simple. `setReceiveTimeout(1000L)` sets a 1-second receive poll timeout—**not** a business handler timeout or shutdown deadline.
- The listener simply processes and returns; it never calls `close()` on sessions, connections, or the broker. Spring owns those resources along this path.

### 7.3. Running and Observing

From the project directory with Maven Wrapper:

~~~bash
./mvnw spring-boot:run
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Example business lines interleaved among Spring and Artemis logs:

~~~text
PUBLISHED job-1
PUBLISHED job-2
PUBLISHED job-3
BEGIN job-1
DONE job-1
BEGIN job-2
DONE job-2
BEGIN job-3
DONE job-3
~~~

**This illustrates log content, not guaranteed stdout ordering**: the listener runs on another thread, may print `BEGIN` before all `PUBLISHED` lines, and if you stop early, only some jobs finish.

Practice steps:

1. Run the app and watch for `BEGIN ...`.
2. While a job is in its 4-second sleep, press `Ctrl+C` **once** to send a normal stop signal.
3. Observe the handler getting a chance to print `DONE ...` before the JVM exits, provided the shutdown hook and grace period trigger properly. The exact number of messages started before stopping is not fixed due to polling races.
4. Re-run for another trial. Because the broker is embedded, **do not assume the same backlog survives across restarts**; to test real recovery/redelivery across process restarts, use an external broker with persistence configured.
5. Read broker metrics/logs rather than relying solely on console output to confirm commits or message loss.

**Verify honestly:** Seeing `DONE job-2` only proves the handler reached that log line. It does not prove DB side effects succeeded, nor does it prove JMS committed if the thread/process crashes right after logging.

### 7.4. Testing Controlled Timeouts

In the lab, change `TimeUnit.SECONDS.sleep(4)` to 8 seconds, set the shutdown phase timeout to 2 seconds, and send `Ctrl+C`. Observe listener/container shutdown behavior and broker logs. This tests an **over-budget** scenario; do not assume identical outcomes across every OS/JVM/provider. Inspecting persistent external broker state is required to properly evaluate uncommitted messages and redelivery.

To test production retries authentically, run a standalone broker, design handlers with idempotency keys, define redelivery policies, and test both graceful stops and hard kills in staging.

## 8. Using the Jakarta Messaging API Directly: try-with-resources

When using raw JMS APIs outside Spring, **closing created resources** is the application code's responsibility. Both `JMSContext` and `Connection` implement `AutoCloseable`, making `try-with-resources` the clearest way to express ownership.

Java 17+ example using Jakarta Messaging 3.x and a configured provider `ConnectionFactory`:

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;

public final class DirectJmsSender {

    private DirectJmsSender() {}

    public static void sendOne(ConnectionFactory factory, String orderId) {
        try (JMSContext context =
                 factory.createContext(JMSContext.SESSION_TRANSACTED)) {

            Queue queue = context.createQueue("orders.in");
            context.createProducer().send(queue, orderId);

            // Commit before context auto-closes.
            context.commit();
        }
    }
}
~~~

`DirectJmsSender.java` **compiles with Jakarta Messaging API on the classpath**, yet cannot run standalone as a full app without a provider `ConnectionFactory`, broker, and caller invoking `sendOne`. Suitable for Java SE or environments allowing local JMS transactions; in Jakarta EE managed web/EJB containers, session/transaction rules can differ.

If `commit` has not happened when the context closes, the open JMS transaction rolls back per spec. Therefore, **never treat `close` as an implicit commit**.

### 8.1. Synchronous Receive Always Bounded by a Timeout

~~~java
// Another illustrative method given a ConnectionFactory.
public static String receiveOne(ConnectionFactory factory) {
    try (JMSContext context =
                 factory.createContext(JMSContext.SESSION_TRANSACTED)) {

        Queue queue = context.createQueue("orders.in");
        String payload = context.createConsumer(queue)
                .receiveBody(String.class, 3000);

        if (payload == null) {
            return null; // Timed out, no message received.
        }

        // Business processing here; throw on incomplete work.
        context.commit();
        return payload;
    }
}
~~~

This is an **illustrative method** (does not compile standalone), needing imports for `ConnectionFactory`, `JMSContext`, and `Queue`; in practice, continuous receivers should use listener containers. The `3000` timeout bounds waiting when no message arrives, not processing time after receipt.

If business logic between `receiveBody` and `commit` throws an exception, the context closes and the uncommitted transaction rolls back. Never catch an exception just to log and return normally before `commit` if you want the broker to handle retries properly.

### 8.2. If You Use `Connection` and `Session` Separately

~~~java
// JMS API snippet; factory and destination variables must exist.
try (var connection = factory.createConnection()) {
    try (var session = connection.createSession(
            jakarta.jms.Session.SESSION_TRANSACTED)) {
        var producer = session.createProducer(destination);
        producer.send(session.createTextMessage("order-17"));
        session.commit();
        // session.close() is invoked by try-with-resources.
    }
    // connection.close() is invoked by try-with-resources.
}
~~~

This is a **code snippet**, not a standalone class: it needs `factory`, `destination`, and Jakarta Messaging/provider dependencies. Closing the connection closes its children; nested `try` blocks remain useful when a connection is kept open across multiple sessions.

**Never share a `Session` / `JMSContext` across arbitrary threads.** JMS enforces single-thread-of-control rules; for multiple workers, give each worker its own session/resources managed by the provider or listener container.

## 9. Caching, Pooling, and Resource Cleanup Order

### 9.1. `SingleConnectionFactory` and `CachingConnectionFactory`

Spring provides connection-reusing wrappers. With `SingleConnectionFactory`, `Connection.close()` on a handle may be ignored by the wrapper to preserve the underlying connection; the factory itself must be destroyed/reset via lifecycle. `CachingConnectionFactory` can also cache sessions/producers/consumers. Consequently, code `close()` calls do not map 1-to-1 to closed TCP sockets.

**While running:** resources borrowed through Spring return to the pool/cache per contract. **When shutting down:** Spring/container destroys the pool/cache owner to release final physical connections. Force-closing physical connections inside a business method can break other in-flight messages.

### 9.2. Listener Containers and Separate Caching

`DefaultMessageListenerContainer` caches resources within its own lifecycle. Passing an external `CachingConnectionFactory` to listeners introduces limits around stop/restart and scaling; Javadoc warns against blindly sharing one caching wrapper across every path. Stick to Spring Boot's default configuration or separate sender caching from listener containers when strict ownership control is needed.

### 9.3. Thread Pools, Databases, Schedulers

Stopping JMS is insufficient if a handler:

- Hands work off to an `ExecutorService` and returns immediately.
- Sends async HTTP calls without awaiting real responses/commits.
- Writes to a database on another thread and acknowledges JMS before the DB transaction completes.
- Leaves streams/background callbacks running after the listener method returns.

If the listener returns early, Spring can commit/ack the message **before** background work finishes. Redesign so handlers await completion or hand off async steps to a separate durable queue/outbox with clear contracts. During shutdown, also drain executors/outstanding tasks in an appropriate phase.

## 10. Deployment: SIGTERM, Kubernetes, and Time Budgets

### 10.1. Setting a Sufficient "Shutdown Budget"

Suppose the longest normal handler takes 25 seconds, listener polling timeout is ~1 second, and metrics/cleanup need a few seconds. If `spring.lifecycle.timeout-per-shutdown-phase=5s` while the orchestrator kills the process after 10 seconds, shutdown will not have enough time.

An illustrative policy:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=40s
~~~

and a Kubernetes pod spec:

~~~yaml
spec:
  terminationGracePeriodSeconds: 75
  containers:
    - name: jms-consumer
      image: example/jms-consumer:v1
      # probes, resources, security, and other environment-specific settings
~~~

This is only an **illustrative spec snippet for budget discussion**, not a complete Deployment YAML. Kubernetes grace time spans multiple steps (including any `preStop` hook), whereas Spring's property is **per phase**, so 75/40 seconds here are examples, not a universal formula. Measure real P95/P99 latencies, number of phases, slow-broker cases, and load-balancer draining.

### 10.2. Readiness Differs from JMS Consumer Lifecycle

Kubernetes readiness turning false removes a Pod from HTTP Service traffic, yet the JMS broker can still deliver messages to directly connected consumers. To actually stop JMS receiving, you must **stop the listener/container** or close connections via lifecycle. Never use a `preStop` script that only runs `sleep` and assume messages drained.

When a pod serves both HTTP and consumes JMS, coordinate both inputs: reject new HTTP jobs promptly, halt producer schedulers, stop listeners, and keep DB/connections alive long enough for unfinished tasks. Stop ordering must mirror real dependencies, not arbitrary `@PreDestroy` hooks.

### 10.3. Never Treat Shutdown Hooks as the Only Line of Defense

No graceful mechanism works when a container is OOM-killed, a node vanishes, a process crashes, or grace periods expire. Combine:
- A persistent broker when durable storage is required with matching policies.
- Transacted receive/ack at the right boundary; backoff, retry budgets, and DLQ.
- Idempotent business handlers.
- Observability plus replay/quarantine tooling.
- Restart/network-cut/kill drills in staging.

## 11. Failure Scenarios and Proper Expectations

| Scenario | Behavior to verify |
| --- | --- |
| SIGTERM with no active messages | Listener stops, sessions/connections release, app exits within budget |
| SIGTERM while a handler is running | Handler gets a chance to finish; if incomplete, transaction/ack determines redelivery |
| Broker lost mid-handler | Connection error, commit failure, and provider recovery; never infer "done" from logs |
| Handler throws before JMS commit | With transacted listeners, rollback/redelivery per broker policy |
| DB commits, then JVM dies before JMS commit | Message may return; idempotency prevents duplicate side effects |
| Handler offloads to async executor and returns | JMS may ack too early; await completion or hand off via another durable queue |
| Early stop with long receive timeout | Waiting on poll/stop may add delay; measure shutdown latency and tune timeout |
| Multiple concurrent consumers shutting down | Receive races/rejected deliveries/retry counts can shift; verify DLQ and delivery counts |
| Calling close directly inside listener | Non-portable for Connection/Session; remove this pattern |
| Killed with `kill -9` | Hooks skipped; rely on broker transactions + idempotency |
| Both broker and consumer stopped together | Establish infrastructure order and persistence; app must not stop a shared broker |
| Stop then restart container | Verify container recovery and special connection caches; do not assume stop==destroy |

### Acceptance Test Suite

1. **Startup:** container receives messages, connects to the intended broker, queue exists, and converters match.
2. **Normal finish:** send 10 messages; all business work completes once per business ID without error; broker backlog returns to 0.
3. **Graceful drain:** keep a handler busy, send SIGTERM, measure `drain_duration`, and verify commit/rollback.
4. **Forced kill:** perform a side effect then kill before JMS commit in staging; verify message redelivery and idempotent handling.
5. **Long handler:** simulate work exceeding phase timeout; observe stop behavior, process exit, and DLQ/retries.
6. **Concurrent shutdown:** with multiple consumers, send dozens of messages and stop; distinguish **delivery attempts** from **business completions**.
7. **External dependency failure:** close/slow down the DB mid-handler; never commit JMS as success when dependent work fails.
8. **Restart:** new producer/consumer version reads old backlog; never change serialization/formats without a compatibility plan.
9. **Resources:** after stop, no process-owned threads, JMS sessions, or connections remain; broker does not hold zombie connections past policy.
10. **Readiness/rollout:** one instance leaves inbound traffic while another replica picks up the backlog without abnormal gaps.

## 12. Observability, Alerting, and Diagnosing Slow Shutdowns

Do not stop at reading "Application stopped." Record these signals per service/destination/instance:

- **Shutdown start/end timestamps** and reason: SIGTERM, scale-down, admin stop, fatal error.
- **Listener status:** running/stopping container counts, active consumer counts, active/pending tasks, configured concurrency.
- **In-flight message counts:** currently processing, completed, committed/acked, rolled back, redelivered, backlog, and DLQ.
- **Waiting message age and processing rate:** queue depth, oldest message age, throughput, and saturation during drain.
- **Transactions/side effects:** DB commit latency, timeouts, external API errors, duplicate hits per business ID.
- **Resource cleanup:** open connection/session counts, active/idle pool counts, live executor threads, shutdown duration, cleanup errors.
- **Broker health:** lost connections, failover/recovery loops, session commit errors, redelivery counts, poison messages, retry policies.

Diagnostic patterns:

- **"Got SIGTERM yet container still accepts new jobs"** → readiness does not affect JMS; inspect stop phase/registry, `acceptMessagesWhileStopping`, poll races, and internal publish loops.
- **"Close takes 40 seconds"** → running listener, receive timeout, or hung dependency; measure per-step timing; never use `kill -9` as a workaround for an unexplained timeout.
- **"After deploy an email sent twice"** → redelivery between side effect and JMS commit; add idempotency/inbox.
- **"Messages vanished even though handler threw"** → check `AUTO_ACKNOWLEDGE` and listener container type; switch to transacted sessions for reliability.
- **"Closing connection in `@PreDestroy` caused `JMSException` in handler"** → destroyed resources while listeners still needed them; let containers own lifecycle and fix phase/owner ordering.
- **"Pool reports connection leaks"** → check whether direct JMS API code closed contexts/sessions, whether pooling factories have destroy hooks, and whether forced kills bypassed shutdown.

## 13. Common Mistakes to Avoid

1. **Using `close()` to commit.** Closing an uncommitted transacted session must roll back; commit explicitly or let the container manage it.
2. **Closing `Connection` inside `onMessage`.** Non-portable, may block/throw; lifecycle belongs outside handlers.
3. **Manually closing `JmsTemplate` resources.** The template manages sessions/connections per callback and factory.
4. **Destroying `CachingConnectionFactory` before listeners stop.** Cuts off active resources; align owners and phases.
5. **Believing `server.shutdown=graceful` covers JMS.** That primarily configures the web server; JMS has separate listener containers and transactions.
6. **Confusing `timeout-per-shutdown-phase` with total process timeout.** Budget for all phases plus orchestrator grace.
7. **Assuming returning from a listener method = database/API work finished.** Never fire-and-forget while acknowledging JMS immediately.
8. **Assuming stop blocks every message at the exact same nanosecond.** In-flight work and receive races exist; handle transactions and retries.
9. **Using `AUTO_ACKNOWLEDGE` for jobs that cannot be lost.** Verify Spring container semantics; usually use transacted listeners.
10. **Forgetting interrupt and deadline handling.** Cancelled handlers must stop safely; if unfinished, throw to roll back instead of logging and committing.
11. **Using an embedded broker demo to prove persistence across restarts.** Embedded brokers stop with the app; test durability on a standalone broker.
12. **Assuming once on the broker = once on business effects.** Be idempotent against redeliveries, especially for DB/HTTP calls.
13. **Shutting down dependent systems before consumers.** DBs, reply producers, and external resources must stay up until in-flight handlers finish.
14. **Ignoring the DLQ during rolling deploys.** A schema mismatch in a new consumer can shunt backlog to retry/DLQ even though shutdown "succeeded."
15. **Enabling caches/pools without clear ownership.** Pools, clients, and listener containers have distinct lifecycles; measure real connections and read provider docs.
16. **Testing only with `Ctrl+C`.** Test SIGTERM, broker loss, force kills, timeouts, and restarts with a live backlog in staging.

## 14. Review Checklist for a Spring JMS Service

- **Connection source:** which factory actually creates connections? Are caching/pooling and bean ownership clear?
- **Send path:** which schedulers/requests/workers could keep publishing during draining?
- **Receive path:** which listener containers manage `@JmsListener`? Are endpoint IDs and phases identified?
- **Reliability:** which `sessionTransacted`/ack mode is used? On failure, who rolls back? Are DLQ/retries configured?
- **Transactions:** DB side effects and JMS commits can diverge; where are idempotency keys stored?
- **In-flight:** what is the real max handler duration? Do tasks offload to async executors and return early?
- **Grace budget:** are `spring.lifecycle.timeout-per-shutdown-phase`, HTTP stop, k8s termination grace, and phases aligned?
- **Ordering:** do producers, listeners, executors, DBs, HTTP clients, JMS caches, and metrics shut down in dependency order?
- **Portability:** is `stop/close` called inside listener callbacks, or are provider-specific behaviors assumed?
- **Operations:** are metrics for drain, queue lag, DLQ, rollbacks, broker connections, and a rollout rollback runbook in place?
- **Tests:** were both graceful stops and process crashes before/after side effects tested?
- **Version changes:** can messages in backlog from the previous release still be read after deployment?

## 15. Practice Questions

1. A listener writes to a database and sends an HTTP request, then receives SIGTERM while waiting on the HTTP response. Sketch at least three interruption points and identify where idempotency is required.
2. Compare `connection.stop()`, `connection.close()`, `session.close()`, and `consumer.close()` when messages remain unacknowledged.
3. In an app where both `JmsTemplate` and `@JmsListener` share a `ConnectionFactory`, explain why a handler must not call `destroy` on the factory itself.
4. Given a max handler time of 25 seconds and shutdown running across 2 phases with 30s timeout per phase, propose a `terminationGracePeriodSeconds` with margin and explain how to measure it in practice.
5. Run the lab with 3 messages and press `Ctrl+C` right after a `BEGIN` line. Record logs, total committed messages, and remaining backlog on an external broker (if configured), then explain why logs are only an indicator.
6. Replace the transacted listener with `AUTO_ACKNOWLEDGE` in a test environment and throw an exception in the handler. Compare `DefaultMessageListenerContainer`'s redelivery behavior with initial expectations.
7. Simulate "handler returns early while executor keeps running." Explain the contract flaw and redesign so ack reflects true completion.
8. Using the Kubernetes model, explain why readiness becoming false does not directly stop a JMS consumer from receiving more messages; what extra step is required?
9. The broker temporarily drops between the `DONE` log and JMS commit. Write how to verify real state via broker/DB metrics rather than deciding from stdout alone.

## Official References

- Jakarta Messaging 3.1 Specification — connection stop/close, session/consumer close, and transactions: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Jakarta Messaging API, `JMSContext` and `Session`: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta/jms/jmscontext
- Spring Framework — Using Spring JMS, acknowledgements, and listener containers: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html
- Spring Framework — Annotation-driven Listener Endpoints: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html
- Spring Framework — `DefaultMessageListenerContainer` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html
- Spring Framework — `AbstractMessageListenerContainer` stop handling: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html
- Spring Framework — `SmartLifecycle` and shutdown callbacks: https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html
- Spring Boot 3.5 — Graceful Shutdown and per-phase timeouts: https://docs.spring.io/spring-boot/3.5/reference/web/graceful-shutdown.html
- Spring Boot 3.5 — JMS messaging configuration: https://docs.spring.io/spring-boot/3.5/how-to/messaging.html
