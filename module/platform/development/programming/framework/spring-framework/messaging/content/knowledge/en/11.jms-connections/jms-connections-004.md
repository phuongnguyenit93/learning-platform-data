# CachingConnectionFactory and Session, Producer, and Consumer Caching

When sending messages via JMS, repeatedly creating and closing `Connection`, `Session`, `MessageProducer`, or `MessageConsumer` can add overhead for both the application and the JMS provider. Spring JMS provides **CachingConnectionFactory** to reuse a `Connection` and cache certain JMS resources after they are returned.

`CachingConnectionFactory` helps reduce resource creation count, but the scope of each cache must be understood properly. The factory shares a `Connection`, caches `Session` by acknowledgement mode, caches `Producer` within a `Session`, and caches `Consumer` only when enabled. Caching does not make `Session` thread-safe, does not create a multi-connection pool by itself, and does not guarantee persistent message storage.

## 1. JMS Resources and Initialization Cost

A message-sending flow typically passes through these resources:

- **ConnectionFactory:** creates connections to the JMS provider.
- **Connection:** physical or logical connection to the provider.
- **Session:** single-threaded context for creating messages, producers, and consumers, and managing acknowledgement/transactions.
- **MessageProducer:** sends messages to a `Queue` or `Topic`.
- **MessageConsumer:** receives messages from a destination.

Creating resources can be costly because the provider must allocate objects, establish protocol state, register consumers, create producers, and exchange metadata with the broker. If an application sends many short messages across different requests, continually creating and closing `Session` and `Producer` can increase latency and load on the provider.

A simple approach is to keep the `Connection` longer and reuse `Session`/`Producer`. However, manually storing resources in singleton services easily leads to sharing a `Session` across multiple threads. `CachingConnectionFactory` provides a cache management mechanism so the application reuses resources while still borrowing/returning them per usage.

## 2. What Is CachingConnectionFactory?

**CachingConnectionFactory** belongs to package **org.springframework.jms.connection**. It is a wrapper around a target JMS `ConnectionFactory`. It extends **SingleConnectionFactory**, thereby managing a shared `Connection` and adding caching for `Session`, `MessageProducer`, and optionally `MessageConsumer`.

Primary roles:

1. Maintain one shared `Connection` instead of creating a new physical `Connection` for each operation.
2. Cache `Session` after the client closes the `Session` proxy.
3. Cache `MessageProducer` scoped to `Session` and destination.
4. Optionally cache `MessageConsumer` if the corresponding setting is enabled.
5. Optionally reset the shared `Connection` when a connection error occurs, per reconnect configuration.

Distinguish `CachingConnectionFactory` from a general-purpose connection pool. `CachingConnectionFactory` focuses on sharing a single `Connection` and reusing internal `Session`/resources. If the application needs to pool multiple physical connections, cap connection count, and manage per-connection leases, consider a pool provided by the JMS provider or a pooling library.

### 2.1. Lifecycle when using the cache

With `JmsTemplate`, a send operation typically borrows a `Session` and `Producer`, performs the send, and then closes the resources afterward. When the `ConnectionFactory` is a `CachingConnectionFactory`, calling `close` on the proxy can return the `Session` or `Producer` to the cache rather than closing the physical resource immediately.

~~~mermaid
flowchart TD
    A["JmsTemplate operation"] --> B["Borrow Session"]
    B --> C["Borrow/create Producer"]
    C --> D["Send Message"]
    D --> E["Close Producer / Session proxy"]
    E --> F{"Cache has room?"}
    F -->|Yes| G["Return resource to cache"]
    F -->|No| H["Close physical resource"]
    G --> I["Reuse on later operation"]
~~~

As a result, business code continues using `JmsTemplate` in the normal way. The template manages operation scope; `CachingConnectionFactory` decides which resources are reused upon return.

## 3. How Does Session Caching Work?

`Session` is the most important resource because `Producer` and `Consumer` are created from a `Session`. `CachingConnectionFactory` retains returned sessions so the next usage can borrow them again.

### 3.1. Separate cache per acknowledgement mode

Sessions are cached by acknowledgement mode. For example, a `Session` using `AUTO_ACKNOWLEDGE` is kept in its corresponding cache bucket; a transacted `Session` belongs to a different bucket. This prevents reusing a `Session` with an incompatible acknowledgement/transaction mode.

Common modes:

- **AUTO_ACKNOWLEDGE:** the provider automatically acknowledges messages according to JMS semantics.
- **CLIENT_ACKNOWLEDGE:** the application explicitly calls acknowledge.
- **DUPS_OK_ACKNOWLEDGE:** the provider may delay acknowledgement and allow duplicates.
- **SESSION_TRANSACTED:** the `Session` manages JMS transactions via commit/rollback.

Configuring session cache size:

~~~java
CachingConnectionFactory cachingFactory =
        new CachingConnectionFactory(providerConnectionFactory);

cachingFactory.setSessionCacheSize(10);
~~~

`sessionCacheSize` defines the maximum number of sessions kept in the cache for each acknowledgement mode. The default value of this property is `1`. If the application uses multiple modes, each mode has its own cache group.

### 3.2. Cache size is not a concurrency limit

This is an easily misunderstood point. `sessionCacheSize` does not necessarily limit the number of sessions that can be active concurrently.

For instance, if cache size is `5` but at a given moment `12` threads send messages simultaneously, the factory may have to create enough sessions to serve the concurrent borrows. When those threads return their sessions:

- Up to `5` sessions of that acknowledgement mode are kept in the cache.
- Excess sessions may be physically closed instead of retained.

Therefore, cache size determines how many idle sessions can be reused, not a semaphore limiting threads or requests. If you want to limit concurrency, use an executor/semaphore or cap resources at the appropriate layer.

### 3.3. Sessions do not become thread-safe

`CachingConnectionFactory` does not allow multiple threads to use the same `Session` at the same time. Each `Session` borrow grants exclusive use; only after the `Session` is returned to the cache can another operation borrow that resource again.

A singleton service can be called by multiple threads if it uses a properly configured `JmsTemplate` and `ConnectionFactory`. Never extract a `Session` from a callback, store it in a field, and share it across other requests.

## 4. Caching MessageProducer

`MessageProducer` is created from a `Session` and sends messages to a destination. Creating a `Producer` may require communicating with the provider or initializing send state.

`CachingConnectionFactory` enables `Producer` caching by default. Producers are cached inside the `Session`, keyed to the destination they send to. When the `Session` is reused, the matching `Producer` can also be reused.

Configuration:

~~~java
cachingFactory.setCacheProducers(true);
~~~

If `Producer` caching is disabled:

~~~java
cachingFactory.setCacheProducers(false);
~~~

then the `Producer` is closed at the end of the operation lifecycle instead of being retained for reuse. This can be useful when a provider exhibits special behavior or the application needs lifecycle control, though it usually increases resource creation cost.

Caching a `Producer` does not mean one `Producer` object is shared concurrently across all threads. A `Producer` belongs to a `Session`; the `Session` is borrowed per usage scope and is not used concurrently by multiple threads. Thus, caching `Producer` inside a `Session` does not violate the single-threaded rule of `Session`.

## 5. Caching MessageConsumer

`Consumer` receives messages from a destination, either using synchronous `receive` or registering a listener depending on the integration style.

`CachingConnectionFactory` **does not cache Consumers by default**. You can enable it:

~~~java
cachingFactory.setCacheConsumers(true);
~~~

When enabled, consumers can be retained in the cache per `Session` along with identifying attributes such as destination, selector, and related subscription settings. Exact caching behavior depends on the implementation and Spring version.

`Consumer` has a more complex lifecycle than `Producer` because it can hold message-receiving state, selectors, subscriptions, prefetch, and listeners. Holding a `Consumer` too long can alter expected behavior, especially when the application uses dynamic selectors, durable subscriptions, or listener containers.

Therefore:

- Keep the default `cacheConsumers=false` unless there is a clear, measured reason to enable it.
- If enabled, thoroughly test selectors, destinations, durable/shared subscriptions, and close/reuse behavior on the actual JMS provider.
- Do not use `Consumer` caching to replace listener container lifecycle management.
- Avoid enabling consumer caching simultaneously with another layer that already caches consumers unless you understand how the two layers interact.

## 6. Configuring CachingConnectionFactory in Spring

Typically, the provider creates the underlying `ConnectionFactory`; `CachingConnectionFactory` wraps that factory and serves as the `ConnectionFactory` for `JmsTemplate`.

Configuration example:

~~~java
@Configuration
public class JmsCacheConfiguration {

    @Bean
    @Primary
    public CachingConnectionFactory cachingConnectionFactory(
            @Qualifier("providerConnectionFactory")
            ConnectionFactory providerConnectionFactory) {

        CachingConnectionFactory factory =
                new CachingConnectionFactory(providerConnectionFactory);

        factory.setSessionCacheSize(10);
        factory.setCacheProducers(true);
        factory.setCacheConsumers(false);
        factory.setReconnectOnException(true);

        return factory;
    }
}
~~~

In the example, `providerConnectionFactory` is the `ConnectionFactory` bean configured by the application or JMS provider. `@Qualifier` prevents the cache bean from injecting itself. `@Primary` makes components needing a `ConnectionFactory` prefer the cache-wrapped factory.

If the application uses a different bean name, adjust the qualifier accordingly. Do not create a circular dependency where `CachingConnectionFactory` receives itself as its target.

`JmsTemplate` can use this factory:

~~~java
@Bean
public JmsTemplate jmsTemplate(
        CachingConnectionFactory cachingConnectionFactory) {
    return new JmsTemplate(cachingConnectionFactory);
}
~~~

Or let Spring Boot auto-configure `JmsTemplate` from the selected primary `ConnectionFactory`. Bean names and auto-configuration behavior depend on the application structure.

### 6.1. Properties commonly worth reviewing

| Property | Role | Common default |
|---|---|---|
| `sessionCacheSize` | Number of idle `Session` instances retained per acknowledgement mode | `1` |
| `cacheProducers` | Whether to cache `MessageProducer` inside `Session` | `true` |
| `cacheConsumers` | Whether to cache `MessageConsumer` inside `Session` | `false` |
| `reconnectOnException` | Reset the shared `Connection` on connection error per the factory's mechanism | `true` |

Check the Javadocs for the exact Spring Framework version in use before relying on defaults in a specific system. The provider, JMS API version, and transaction setup can affect how resources are created and managed.

## 7. How Do JmsTemplate and CachingConnectionFactory Work Together?

`JmsTemplate` is a high-level abstraction for sending and receiving messages. It manages acquiring `Connection`/`Session`/`Producer`, performing the work, and closing resources within the scope of the call.

When `JmsTemplate` uses `CachingConnectionFactory`:

1. `JmsTemplate` requests a `Session`.
2. `CachingConnectionFactory` returns a `Session` from the cache if available, or creates a new `Session`.
3. `JmsTemplate` requests a `Producer` for the destination.
4. The factory returns a cached `Producer` in the `Session` if available, or creates a new `Producer`.
5. `JmsTemplate` sends the message.
6. When the operation finishes, the resource proxies are closed and returned to the cache per policy.

Example service that can use the template from multiple threads:

~~~java
@Service
public class NotificationPublisher {

    private final JmsTemplate jmsTemplate;

    public NotificationPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void publish(String destination, String payload) {
        jmsTemplate.convertAndSend(destination, payload);
    }
}
~~~

`NotificationPublisher` can be a singleton. Multiple requests can call `publish` concurrently because `JmsTemplate` is designed to be reused once configured. Each operation borrows resources via the factory's mechanism; a `Session` currently in use by one operation is not shared concurrently with another operation.

Do not manually open a `Session` as a field on `NotificationPublisher` to "optimize" further. Doing so can break the cache management, transactions, and thread safety provided by Spring.

## 8. CachingConnectionFactory and Listener Containers

Asynchronous consumers are usually managed by a Spring JMS listener container such as **DefaultMessageListenerContainer** or **SimpleMessageListenerContainer**. The container is responsible for creating and managing `Session`, `MessageConsumer`, threads, and listener lifecycle.

Listener containers have their own resource caching mechanisms, including cache levels/caching policies. Therefore, avoid blindly enabling multiple caching layers:

- Check at what level the listener container caches `Connection`, `Session`, or `Consumer`.
- Do not enable `cacheConsumers=true` on `CachingConnectionFactory` by default when the listener container also manages `Consumer`.
- With `DefaultMessageListenerContainer`, consider the cache level and transaction manager in use.
- Test reconnect, shutdown, durable subscriptions, and redelivery against a real provider.

For long-lived managed listener containers, the container typically keeps consumer/session resources for the lifetime of the listener rather than recreating them per message. `CachingConnectionFactory` may still share the `Connection` or support other operations, but it should not be treated as the sole mechanism managing consumer concurrency.

## 9. Transactions and Acknowledgement with Session Caching

Caching only changes resource reuse; it does not alter JMS transaction and acknowledgement semantics.

### 9.1. Sessions by acknowledgement mode

Because sessions are cached per acknowledgement mode, an operation using `AUTO_ACKNOWLEDGE` will not accidentally pick up a transacted `Session`. If the application mixes operation types, check how `JmsTemplate` and the transaction manager request sessions.

### 9.2. Transactions tied to Session

A JMS transacted `Session` has its own transaction. `commit()` and `rollback()` apply to send/receive operations belonging to that `Session`. Returning the `Session` to the cache does not merge its transaction into a shared transaction with other sessions.

When Spring manages transactions, let `JmsTransactionManager` or the appropriate transaction manager handle resources as configured. Do not manually call `commit`/`rollback` on a `Session` managed by a Spring transaction manager.

### 9.3. Database and JMS do not automatically form an atomic transaction

`CachingConnectionFactory` does not create distributed transactions. If atomicity between a database and JMS is required, use JTA/XA with a supporting provider and database, or use a Transactional Outbox suited to the architecture.

An outbox writes business data and the intent to publish a message in the same database transaction, and a relay then sends the message. Consumers still need idempotency to handle duplicates.

## 10. Choosing sessionCacheSize and Measuring Performance

Do not pick a cache size merely because of a popular number. Measure concurrency and resource hold times:

1. Estimate the number of concurrent send/receive operations.
2. Identify the number of acknowledgement modes actually used.
3. Measure `Session` and `Producer` creation time on the provider.
4. Measure throughput and latency before and after enabling caching.
5. Observe open `Session` counts and provider resource consumption.
6. Tune cache size to balance reuse against retained idle resources.

If the cache size is too small relative to steady concurrency, excess sessions may be closed upon return and recreated on the next call. If the cache is too large, the application holds many idle sessions, increasing client- and broker-side resource usage.

Distinguish brief peak concurrency from steady-state concurrency. Caching helps most when resources are reused frequently. For very sparse workloads, a large cache may not yield proportional benefits.

## 11. CachingConnectionFactory Is Not a Connection Pool

| Criterion | CachingConnectionFactory | Provider connection pool |
|---|---|---|
| Connection | Shares one `Connection` under the `SingleConnectionFactory` model | Can manage multiple physical `Connection` instances |
| Session | Caches `Session` after return | Usually pools/leases `Session` per configuration |
| Producer | Cached per `Session` | Depends on implementation/pool |
| Consumer | Not cached by default; can be enabled | Depends on provider/pool |
| Goal | Reduce JMS resource recreation cost in a shared-connection model | Manage count and reuse of multiple connections/resources |
| Concurrency limit | Not a semaphore limiting active `Session` count | May enforce explicit pool limits |

If you need load isolation across multiple physical connections, limits on broker connections, or per-application pooling, use a suitable provider pool. Do not expect increasing `sessionCacheSize` to create additional connections.

## 12. Common Pitfalls

### 12.1. Increasing sessionCacheSize while still sharing a Session

Increasing cache size does not make `Session` thread-safe. Each concurrent operation still needs its own `Session`; the cache only reuses a `Session` after an operation returns it.

### 12.2. Confusing cache size with max worker count

Cache size is the number of idle sessions retained per acknowledgement mode. When concurrency exceeds that number, the factory can still create additional sessions and close the excess ones upon return.

### 12.3. Enabling cacheConsumers without testing

Consumers hold selectors, subscriptions, and message-receiving state. Caching consumers can alter receive behavior or conflict with listener containers. Defaulting to `false` is the safe choice when no specific measured requirement exists.

### 12.4. Using CachingConnectionFactory as a multi-Connection pool

The factory shares a single `Connection`. If multiple physical connections or pool limits are required, choose a provider pool instead of merely increasing the `Session` cache.

### 12.5. Closing the shared Connection while another worker is running

The shared `Connection`'s lifecycle is managed by the factory. Never manually close the target `Connection` from a worker. Let the Spring container close the factory on application shutdown.

### 12.6. Double caching with a listener container

Listener containers have their own `Session`/`Consumer` caching mechanisms. Enabling consumer caching on `ConnectionFactory` as well can create two resource-holding layers, obscuring lifecycle and reconnect behavior. Choose a strategy aligned with the container type and provider.

### 12.7. Not monitoring reconnects and provider errors

When a `Connection` fails, the factory can reset/reconnect according to configuration. The application still must monitor exceptions, broker availability, reconnect counts, and message retry/redelivery. Caching does not replace broker monitoring.

## 13. Java 17 Example: Simulating Session Caching by Acknowledgement Mode

The following example uses plain JDK classes to simulate a small `Session` cache. It illustrates `Session` caching by acknowledgement mode, `Producer` caching by destination within a `Session`, and exclusive use per borrow. This is not the implementation of Spring's `CachingConnectionFactory` or a JMS provider.

Create file **SessionResourceCacheDemo.java**:

~~~java
import java.util.ArrayDeque;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public class SessionResourceCacheDemo {

    enum AckMode {
        AUTO_ACKNOWLEDGE,
        CLIENT_ACKNOWLEDGE,
        TRANSACTED
    }

    record DemoProducer(String id, String destination) {}

    static final class DemoSession {
        private final String id;
        private final AckMode ackMode;
        private final Map<String, DemoProducer> producers = new HashMap<>();

        DemoSession(String id, AckMode ackMode) {
            this.id = id;
            this.ackMode = ackMode;
        }

        String id() {
            return id;
        }

        DemoProducer producer(
                String destination,
                AtomicInteger producerIds) {
            return producers.computeIfAbsent(
                    destination,
                    key -> new DemoProducer(
                            "producer-" + producerIds.incrementAndGet(),
                            key
                    )
            );
        }
    }

    static final class SessionLease implements AutoCloseable {
        private final DemoCachingConnectionFactory factory;
        private final DemoSession session;
        private boolean closed;

        SessionLease(
                DemoCachingConnectionFactory factory,
                DemoSession session) {
            this.factory = factory;
            this.session = session;
        }

        DemoSession session() {
            if (closed) {
                throw new IllegalStateException("Lease is closed");
            }
            return session;
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                factory.release(session);
            }
        }
    }

    static final class DemoCachingConnectionFactory {
        private final int sessionCacheSize;
        private final Map<AckMode, ArrayDeque<DemoSession>> cache =
                new EnumMap<>(AckMode.class);
        private final AtomicInteger sessionIds = new AtomicInteger();
        private final AtomicInteger producerIds = new AtomicInteger();

        DemoCachingConnectionFactory(int sessionCacheSize) {
            this.sessionCacheSize = sessionCacheSize;
            for (AckMode mode : AckMode.values()) {
                cache.put(mode, new ArrayDeque<>());
            }
        }

        synchronized SessionLease acquire(AckMode mode) {
            DemoSession session = cache.get(mode).pollFirst();

            if (session == null) {
                session = new DemoSession(
                        "session-" + sessionIds.incrementAndGet(),
                        mode
                );
            }

            return new SessionLease(this, session);
        }

        synchronized void release(DemoSession session) {
            ArrayDeque<DemoSession> sessions = cache.get(session.ackMode);

            if (sessions.size() < sessionCacheSize) {
                sessions.addLast(session);
            }
            // If the cache is full, the simulation discards the excess resource.
        }

        AtomicInteger producerIds() {
            return producerIds;
        }
    }

    public static void main(String[] args) throws Exception {
        DemoCachingConnectionFactory factory =
                new DemoCachingConnectionFactory(1);

        try (SessionLease lease =
                     factory.acquire(AckMode.AUTO_ACKNOWLEDGE)) {
            DemoProducer producer = lease.session().producer(
                    "orders.queue",
                    factory.producerIds()
            );
            System.out.println(
                    "First lease: " + lease.session().id()
                            + ", " + producer.id());
        }

        try (SessionLease lease =
                     factory.acquire(AckMode.AUTO_ACKNOWLEDGE)) {
            DemoProducer producer = lease.session().producer(
                    "orders.queue",
                    factory.producerIds()
            );
            System.out.println(
                    "Second lease: " + lease.session().id()
                            + ", " + producer.id());
        }

        try (SessionLease lease =
                     factory.acquire(AckMode.TRANSACTED)) {
            DemoProducer producer = lease.session().producer(
                    "orders.queue",
                    factory.producerIds()
            );
            System.out.println(
                    "Transacted lease: " + lease.session().id()
                            + ", " + producer.id());
        }

        ExecutorService workers = Executors.newFixedThreadPool(2);
        CountDownLatch acquired = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);

        try {
            var task = (java.util.concurrent.Callable<String>) () -> {
                try (SessionLease lease =
                             factory.acquire(AckMode.AUTO_ACKNOWLEDGE)) {
                    acquired.countDown();
                    release.await();
                    return lease.session().id();
                }
            };

            Future<String> first = workers.submit(task);
            Future<String> second = workers.submit(task);

            if (!acquired.await(5, java.util.concurrent.TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Workers did not acquire sessions in time");
            }

            release.countDown();

            boolean distinctSessions =
                    !first.get().equals(second.get());

            System.out.println(
                    "Concurrent leases are distinct: " + distinctSessions);
        }
        finally {
            release.countDown();
            workers.shutdown();
        }
    }
}
~~~

Compile and run with Java 17 or later:

~~~bash
javac SessionResourceCacheDemo.java
java SessionResourceCacheDemo
~~~

Output:

~~~text
First lease: session-1, producer-1
Second lease: session-1, producer-1
Transacted lease: session-2, producer-2
Concurrent leases are distinct: true
~~~

Two sequential `AUTO_ACKNOWLEDGE` borrows reuse the same `Session` and `Producer`. The `TRANSACTED` `Session` lives in a different cache bucket. Two concurrent workers receive two distinct sessions even though the cache size is only `1`; this demonstrates that cache size is not a concurrency limit.

## 14. Deployment and Testing Procedure

When introducing `CachingConnectionFactory` into an application, follow this order:

1. Identify the target `ConnectionFactory` supplied by the provider.
2. Wrap the target factory with `CachingConnectionFactory` and use the caching bean as the primary `ConnectionFactory` for `JmsTemplate`.
3. Start with `cacheProducers=true`, `cacheConsumers=false`.
4. Choose `sessionCacheSize` based on actual concurrency and number of acknowledgement modes.
5. Verify that `Session` instances are not shared concurrently across threads.
6. Test transactions, acknowledgement, and reconnect against a real provider.
7. If using listener containers, check container cache levels before enabling additional consumer caching.
8. Measure throughput, latency, created `Session`/`Producer` counts, and open resource counts.
9. Test shutdown and reconnect to ensure resources are released according to lifecycle.

Important tests include concurrent sending from multiple threads, verifying messages arrive at the right destination, checking producer reuse, verifying `Session` isolation by acknowledgement mode, and checking behavior when the broker disconnects. If `Consumer` caching is enabled, separately test selectors, subscriptions, receive timeouts, and close/reconnect behavior.

`CachingConnectionFactory` helps reuse JMS resources and lowers `Session`/`Producer` creation overhead in applications that send and receive frequently. Understanding caching by acknowledgement mode, `Producer` caching inside `Session`, and that `Consumer` is not cached by default enables proper configuration. Cache size only controls how many idle resources are retained; each concurrent operation still needs its own `Session`. Combining `JmsTemplate` or listener containers with clear lifecycle management lets the application benefit from caching while preserving JMS semantics.