# Testing Channels and Message Handlers in Spring Integration

An integration flow can look very simple: receive a <code>Message&lt;OrderCommand&gt;</code> from a channel, call a service activator, and push the result downstream. Yet when switching from <code>DirectChannel</code> to <code>ExecutorChannel</code>, using <code>QueueChannel</code> with a poller, or adding retry, transactions, and an error channel, runtime behavior changes significantly. A test that only verifies the service returns the right data is **not enough** to prove the flow does not lose messages, report success prematurely, or misroute errors.

The lesson **“Testing Channels and Message Handlers”** belongs to the **Testing runtime** chapter of **SPRING_INTEGRATION_RUNTIME**. Its focus is designing tests around the channel–endpoint–handler boundary using the Spring Integration Test Framework and JUnit 5, then extending to threading, timeouts, retries, message stores, correlation, transactions, and lifecycle. The examples target Java 17+ and Spring Integration 6.x; when copying into a project, align dependency versions and application configuration.

> **Principle:** <code>MessageChannel.send()</code> returning true does **not always** mean the handler and all downstream steps succeeded. Tests must observe the exact **completion boundary** of each channel type.

## 1. Decide what needs to be proven before writing a test

Tests can be divided into four levels, each with different confidence and cost:

| Testing level | Entry / observation point | What it proves | What it does not prove |
|---|---|---|---|
| **Service unit test** | Call Java method directly, mock repository | Business rules, validation, result/error cases | Routing, headers, advice, subscribers, polling, threading |
| **Channel test** | Manually instantiate <code>DirectChannel</code>, <code>QueueChannel</code>, or <code>ExecutorChannel</code> | Send/receive, capacity, dispatch, threading, and channel completion | Full wiring in the Spring context |
| **Flow integration test** | Send message to input bean, receive output or inspect side effects | Channel → endpoint → handler, payload/header propagation, error path, and lifecycle | Broker/database transactions if only mocked |
| **System/boundary test** | Real broker/database/adapter or Testcontainers | ACK, redelivery, commit/rollback, restart, multi-instance concurrency | Does not automatically prove scenarios outside what was simulated |

A good test clearly answers:

1. **Given:** what are the initial payload/headers, channel state, and service state?
2. **When:** which channel receives the message; which thread, poller, or adapter triggers execution?
3. **Then:** who completes, where does the output go, where do exceptions go, and how many times do side effects occur?
4. **Finally:** what state are resources/test doubles restored to so subsequent tests are unaffected?

~~~mermaid
flowchart LR
    T["JUnit test"] --> IN["Input channel"]
    IN --> EP["Consumer endpoint"]
    EP --> H["Message handler"]
    H --> OUT["Output channel"]
    OUT --> A["Assert payload, header, completion"]
    H -. "Exception" .-> E["Caller or error flow"]
    E --> B["Assert error / rollback / retry"]
~~~

For asynchronous flows, the return from <code>send()</code> back to the test may occur **before** the <code>MessageHandler</code> finishes running. Use output queues, latches, futures, or conditional assertions with timeouts.

## 2. Comparing the testable semantics of channels

| Channel type | How messages are dispatched / stored | What does <code>send()</code> usually indicate? | Reliable assertion point |
|---|---|---|---|
| <code>DirectChannel</code> | Subscriber runs synchronously on sender thread | Synchronous handler invocation completed or exception propagated | Result after <code>send()</code>, exception from the same call stack |
| <code>PublishSubscribeChannel</code> without executor | Calls subscribers synchronously via dispatcher | Send executed subscribers per policy, unless an error handler/subscriber alters flow | Side effects per subscriber; errors per configuration |
| <code>ExecutorChannel</code> | Submits task to executor; handler runs on worker | Task was accepted, not that all downstream processing finished | <code>CountDownLatch</code>, output channel, or worker state |
| <code>QueueChannel</code> | Enqueues message; consumer polls via <code>receive()</code> | Message was accepted by the queue, **not** yet processed | <code>receive(timeout)</code> and execution of the polling endpoint |
| <code>FluxMessageChannel</code> | Publisher/Reactive Streams | Depends on subscriber/demand and reactive boundary | Completion, <code>onError</code>, StepVerifier, backpressure |

<code>MessageChannel</code> provides <code>send(message)</code> and <code>send(message, timeout)</code>. Do not assume all errors return <code>false</code>: with a <code>DirectChannel</code> that has no subscriber or whose handler throws an exception, a <code>MessagingException</code> may propagate to the caller. With buffered channels, <code>false</code> typically indicates the message could not be enqueued within the timeout.

## 3. Dependencies and fixture organization rules

For a project managed by the Spring Boot BOM or compatible dependency management, tests typically need:

~~~kotlin
dependencies {
    implementation("org.springframework.integration:spring-integration-core")

    testImplementation("org.springframework.integration:spring-integration-test")
    testImplementation("org.springframework:spring-test")
    testImplementation("org.junit.jupiter:junit-jupiter")
}
~~~

This is an **illustrative** Gradle Kotlin DSL snippet, not a complete build file. <code>spring-integration-test</code> provides Spring Integration test support; pure test utilities also live in <code>spring-integration-test-support</code>. Those artifacts transitively depend on Spring Test/Mockito in supported setups, though declaring explicit dependencies as needed keeps tests easier to maintain. Use a single aligned set of Spring Framework, Spring Integration, Reactor, and JUnit versions; do not mix 5.x/6.x branches arbitrarily.

Test fixtures should have **stable** channel/endpoint names so they can be looked up via <code>@Qualifier</code>, mocked, and topology-verified. Do not reuse the same bean name across multiple flows in a single test <code>ApplicationContext</code>.

## 4. Testing DirectChannel without a Spring context

This is the smallest test to prove **synchronous** dispatch. <code>DirectChannel</code> is a <code>SubscribableChannel</code>, so a <code>MessageHandler</code> can be subscribed directly:

~~~java
@Test
void directChannelInvokesHandlerBeforeSendReturns() {
    DirectChannel channel = new DirectChannel();
    AtomicReference<Message<?>> observed = new AtomicReference<>();
    AtomicReference<String> handlerThread = new AtomicReference<>();
    String senderThread = Thread.currentThread().getName();

    channel.subscribe(message -> {
        observed.set(message);
        handlerThread.set(Thread.currentThread().getName());
    });

    Message<String> request = MessageBuilder.withPayload("ping")
        .setHeader("correlationId", "request-42")
        .build();

    assertTrue(channel.send(request));
    assertSame(request, observed.get());
    assertEquals(senderThread, handlerThread.get());
    assertEquals("request-42",
        observed.get().getHeaders().get("correlationId"));
}
~~~

Key types: <code>org.springframework.integration.channel.DirectChannel</code>, <code>org.springframework.messaging.Message</code>, <code>org.springframework.integration.support.MessageBuilder</code>, <code>java.util.concurrent.atomic.AtomicReference</code>. Assertions belong to JUnit 5.

### Testing synchronous handler exceptions

~~~java
@Test
void synchronousHandlerFailurePropagatesToSender() {
    DirectChannel channel = new DirectChannel();
    channel.subscribe(message -> {
        throw new IllegalStateException("Downstream failed");
    });

    Message<String> request =
        MessageBuilder.withPayload("will-fail").build();

    MessagingException failure = assertThrows(
        MessagingException.class,
        () -> channel.send(request));

    assertNotNull(failure.getCause());
}
~~~

When the dispatcher wraps a non-<code>MessagingException</code> into a messaging error, the wrapper type and cause can vary across framework boundaries and versions. Therefore, for **business** assertions, inspect the root cause type or appropriate message/cause; do not rely on a verbatim log string.

**Anti-pattern:** Testing with <code>DirectChannel</code> and assuming an <code>ExecutorChannel</code> in production will throw exceptions back to <code>send()</code> in the same way. The two channel types have different completion boundaries.

## 5. Testing QueueChannel: a message in the queue is not yet processed

<code>QueueChannel</code> is a <code>PollableChannel</code>. It fits well as an observable output in flow tests because the test thread actively pulls messages using <code>receive(timeout)</code>:

~~~java
@Test
void queueChannelStoresMessageUntilReceived() {
    QueueChannel queue = new QueueChannel(1);
    Message<String> first = MessageBuilder.withPayload("first").build();
    Message<String> second = MessageBuilder.withPayload("second").build();

    assertTrue(queue.send(first));
    assertFalse(queue.send(second, 0)); // Queue is full; do not wait.

    Message<?> taken = queue.receive(0);
    assertNotNull(taken);
    assertEquals("first", taken.getPayload());
    assertNull(queue.receive(0));
}
~~~

Key points:

- <code>receive(0)</code> is a non-blocking poll; <code>receive(5_000)</code> waits up to a finite bound.
- <code>send(second, 0)</code> can return <code>false</code> because the bounded queue is full; this result does not prove <code>second</code> had a payload error.
- Pulling a message from the queue does **not** mean a downstream service activator executed business logic. In the poller model, dequeuing and processing happen in a separate endpoint/polling task.
- An in-memory <code>QueueChannel</code> does not become a persistent queue just because a test uses it. With <code>JdbcChannelMessageStore</code>, transactions and redelivery must be tested separately.

When a test leaves an output message in a queue without draining it, the next test reusing the Spring context may receive a **message from the previous test**. Use isolated channels/fixtures, drain queues in <code>@BeforeEach</code>/<code>@AfterEach</code>, or mark the context dirty when truly necessary.

## 6. Testing PublishSubscribeChannel: fan-out and failure boundary

A <code>PublishSubscribeChannel</code> without an executor typically invokes subscribers **synchronously**. Minimal test:

~~~java
@Test
void pubSubDeliversToBothSynchronousSubscribers() {
    PublishSubscribeChannel channel = new PublishSubscribeChannel();
    List<String> seen = new CopyOnWriteArrayList<>();

    channel.subscribe(message ->
        seen.add("audit:" + message.getPayload()));
    channel.subscribe(message ->
        seen.add("notify:" + message.getPayload()));

    assertTrue(channel.send(
        MessageBuilder.withPayload("order-42").build()));

    assertEquals(2, seen.size());
    assertTrue(seen.contains("audit:order-42"));
    assertTrue(seen.contains("notify:order-42"));
}
~~~

The test above does **not** claim subscribers always execute in a fixed order. When adding an executor, error handler, <code>requireSubscribers</code>, or sequencing policy, write new tests reflecting that exact configuration; for example, whether one failing subscriber stops remaining subscribers from being called depends on the dispatcher/error handling.

Do not mock every subscriber if the goal is to verify **fan-out**; a fake consumer recording payloads/correlation is enough to prove both branches received the message.

## 7. Testing ExecutorChannel with latches, not sleep

<code>ExecutorChannel</code> hands processing off to a worker; a test must never assert immediately after <code>send()</code> that side effects completed. Use <code>CountDownLatch</code> to control the exact boundary:

~~~java
@Test
void executorChannelSendCanReturnBeforeHandlerCompletes()
        throws Exception {
    ExecutorService executor = Executors.newSingleThreadExecutor();
    CountDownLatch entered = new CountDownLatch(1);
    CountDownLatch release = new CountDownLatch(1);
    CountDownLatch finished = new CountDownLatch(1);
    AtomicBoolean handled = new AtomicBoolean(false);

    try {
        ExecutorChannel channel = new ExecutorChannel(executor);
        channel.subscribe(message -> {
            entered.countDown();
            try {
                if (!release.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Test release timeout");
                }
                handled.set(true);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(ex);
            } finally {
                finished.countDown();
            }
        });

        assertTrue(channel.send(
            MessageBuilder.withPayload("async").build()));
        assertTrue(entered.await(2, TimeUnit.SECONDS));
        assertFalse(handled.get()); // Worker is still waiting for release.

        release.countDown();
        assertTrue(finished.await(2, TimeUnit.SECONDS));
        assertTrue(handled.get());
    } finally {
        release.countDown();
        executor.shutdownNow();
    }
}
~~~

This experiment proves the difference between **task accepted** and **handler completion**, without needing <code>Thread.sleep()</code> to “hope” a race condition appears. If production uses <code>ThreadPoolTaskExecutor</code>, let Spring manage shutdown, or close the executor in <code>finally</code> when constructed directly in a test.

**Never assert on an <code>AtomicBoolean</code> without a synchronization boundary**: the example above uses <code>entered.await()</code>, <code>release</code>, and <code>finished.await()</code> so the test reaches provable states.

## 8. Spring Integration Java DSL fixture for endpoint–handler tests

We will build a simple order processing flow. <code>OrderService</code> has no dependency on messaging APIs; the <code>Service Activator</code> extracts the payload, invokes the service, and sends the result to the output channel.

**Step 1 — two data types and a service:**

~~~java
public record OrderCommand(String orderId, int quantity) {}
public record OrderResult(String orderId, String status) {}

public class OrderService {
    public OrderResult process(OrderCommand order) {
        if (order.quantity() <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        return new OrderResult(order.orderId(), "ACCEPTED");
    }
}
~~~

**Step 2 — dedicated test context configuration:**

~~~java
@Configuration
@EnableIntegration
public class OrderFlowTestConfig {

    @Bean
    OrderService orderService() {
        return new OrderService();
    }

    @Bean(name = "orders.in")
    MessageChannel ordersIn() {
        return new DirectChannel();
    }

    @Bean(name = "orders.out")
    PollableChannel ordersOut() {
        return new QueueChannel(20);
    }

    @Bean
    IntegrationFlow orderFlow(OrderService service) {
        return IntegrationFlow.from("orders.in")
            .handle(service, "process",
                endpoint -> endpoint.id("orders.process.endpoint"))
            .channel("orders.out")
            .get();
    }
}
~~~

Key imports: <code>org.springframework.integration.dsl.IntegrationFlow</code>, <code>org.springframework.integration.config.EnableIntegration</code>, <code>org.springframework.integration.channel.DirectChannel</code>/<code>QueueChannel</code>, <code>org.springframework.messaging.MessageChannel</code>/<code>PollableChannel</code>, and <code>org.springframework.context.annotation.Configuration</code>/<code>Bean</code>.

<code>endpoint.id("orders.process.endpoint")</code> is the endpoint name used when mocking the handler, which does not have to match the service bean name <code>orderService</code>. This is critical when using <code>MockIntegrationContext.substituteMessageHandlerFor(...)</code>.

## 9. Flow integration test: payload, reply, and error

<code>@SpringJUnitConfig</code> initializes the Spring TestContext integrated with JUnit Jupiter; <code>@SpringIntegrationTest</code> adds Spring Integration-specific test utilities.

~~~java
@SpringJUnitConfig(OrderFlowTestConfig.class)
@SpringIntegrationTest
class OrderFlowIntegrationTest {

    @Autowired
    @Qualifier("orders.in")
    MessageChannel input;

    @Autowired
    @Qualifier("orders.out")
    PollableChannel output;

    @Test
    void validOrderProducesExpectedReplyAndCorrelation() {
        Message<OrderCommand> request = MessageBuilder
            .withPayload(new OrderCommand("O-301", 2))
            .setHeader("correlationId", "checkout-301")
            .build();

        assertTrue(input.send(request));

        Message<?> reply = output.receive(1_000);
        assertNotNull(reply);
        assertEquals(new OrderResult("O-301", "ACCEPTED"),
            reply.getPayload());
        assertEquals("checkout-301",
            reply.getHeaders().get("correlationId"));
        assertNull(output.receive(0));
    }

    @Test
    void invalidOrderPropagatesExceptionAndEmitsNoReply() {
        Message<OrderCommand> request = MessageBuilder
            .withPayload(new OrderCommand("O-302", 0))
            .build();

        assertThrows(MessagingException.class,
            () -> input.send(request));
        assertNull(output.receive(0));
    }
}
~~~

Annotations: <code>org.springframework.test.context.junit.jupiter.SpringJUnitConfig</code>, <code>org.springframework.integration.test.context.SpringIntegrationTest</code>, <code>org.springframework.beans.factory.annotation.Autowired</code>/<code>Qualifier</code>. <code>MessagingException</code> belongs to <code>org.springframework.messaging</code>.

**Why is this test valuable?** It verifies bean wiring, dispatch through <code>DirectChannel</code>, invoking the right method on the Service Activator, producing the reply, and preserving the correlation header when the framework builds the reply message. It does not verify database transactions or broker ACKs because the fixture contains neither.

For the error test, the framework may wrap the business error in a <code>MessagingException</code>; inspect the cause chain if you want to verify the <code>quantity</code> reason. Avoid coupling tests to stack trace text that can change across versions.

## 10. Substituting a handler with MockIntegrationContext

When you want to test **wiring and routing** without calling the real service (which may touch a DB or HTTP), Spring Integration provides <code>MockIntegrationContext</code> and <code>MockMessageHandler</code>.

<code>@SpringIntegrationTest</code> registers <code>MockIntegrationContext</code> in the test context. <code>substituteMessageHandlerFor(endpointId, mockHandler)</code> takes the **consumer endpoint ID**, not an arbitrary method name or <code>MessageChannel</code> name.

~~~java
@SpringJUnitConfig(OrderFlowTestConfig.class)
@SpringIntegrationTest
class MockedHandlerFlowTest {

    @Autowired
    MockIntegrationContext mockContext;

    @Autowired
    @Qualifier("orders.in")
    MessageChannel input;

    @Autowired
    @Qualifier("orders.out")
    PollableChannel output;

    @AfterEach
    void resetMocks() {
        mockContext.resetBeans();
    }

    @Test
    void canSubstituteConsumerHandlerWithoutCallingRealService() {
        ArgumentCaptor<Message<?>> captured =
            MockIntegration.messageArgumentCaptor();

        MockMessageHandler fake = MockIntegration
            .mockMessageHandler(captured)
            .handleNextAndReply(message -> {
                OrderCommand order =
                    (OrderCommand) message.getPayload();
                return new OrderResult(order.orderId(), "MOCKED");
            });

        mockContext.substituteMessageHandlerFor(
            "orders.process.endpoint", fake);

        Message<OrderCommand> request = MessageBuilder
            .withPayload(new OrderCommand("O-303", 1))
            .build();

        assertTrue(input.send(request));
        Message<?> reply = output.receive(1_000);

        assertNotNull(reply);
        assertEquals(new OrderResult("O-303", "MOCKED"),
            reply.getPayload());
        assertSame(request, captured.getValue());
    }
}
~~~

Types belong to <code>org.springframework.integration.test.context.MockIntegrationContext</code>, <code>org.springframework.integration.test.mock.MockIntegration</code>/<code>MockMessageHandler</code>, <code>org.mockito.ArgumentCaptor</code>, and JUnit 5 <code>@AfterEach</code>.

<code>handleNextAndReply(...)</code> simulates request–reply; for one-way consumers use <code>handleNext(...)</code>. Callbacks apply to subsequent messages in the declared order, and the last callback can be reused for remaining messages. If the test needs to check invocation count, use <code>ArgumentCaptor.getAllValues()</code> or appropriate interaction assertions.

**Why must you call <code>resetBeans()</code>?** Spring TestContext can reuse an <code>ApplicationContext</code> across tests. Skipping reset leaves the next test running the fake handler instead of the real one, creating order-dependent test failures. <code>resetBeans()</code> restores the original configuration of replaced endpoints.

### When to mock and when not to mock a handler

| Goal | Should mock? | Reason |
|---|---|---|
| Verify a router sends messages to the right endpoint | Yes | Block real side effects and confirm message arrival |
| Verify service validation and mapping | Do not mock the service under test itself | Otherwise you only test fake behavior |
| Verify error channel when downstream throws | Possible | Fake handler intentionally throws; must check the right thread boundary |
| Verify real transaction + DB rollback | Insufficient | Mocks do not prove database transactions |
| Verify retry advice around handler | Possible, with a mock failing n times | Controls attempt count, but requires separate integration tests for side effects |

## 11. Preventing real inbound adapters from starting in tests

A context containing Kafka/JMS/JDBC inbound adapters or schedulers may connect to external systems **as soon as the test starts**. To test channels/handlers, you do not need to start all real sources.

~~~java
@SpringJUnitConfig(ProductionLikeFlowConfig.class)
@SpringIntegrationTest(
    noAutoStartup = { "externalInboundAdapter", "*PollingSource*" })
class IsolatedFlowTest {

    @Autowired
    MockIntegrationContext mocks;

    // The test will explicitly send messages to the input channel in the context.
}
~~~

<code>noAutoStartup</code> uses simple pattern matching on endpoint IDs: <code>xxx*</code>, <code>xxx</code>, <code>*xxx</code>, <code>xxx*yyy</code>. It prevents matching endpoints from auto-starting during the test lifecycle; it does not disable other handlers/channels outside the pattern.

When you want to substitute a scheduled polling source, you can use:

~~~java
mocks.substituteMessageSourceFor(
    "externalInboundAdapter",
    MockIntegration.mockMessageSource("test-payload"));
~~~

This snippet belongs in a test that **already has** a <code>SourcePollingChannelAdapter</code> with bean ID <code>externalInboundAdapter</code>, not an API to create a new endpoint. After replacing the source, you must explicitly start the endpoint or let the scheduler run per test setup, and reset beans afterward. Since Spring Integration **6.3**, <code>MockIntegrationContext.substituteTriggerFor(...)</code> also lets you replace a real polling trigger with a test trigger.

**Never write a test that runs a poller every few seconds and calls <code>Thread.sleep(10_000)</code> to wait.** You can trigger a single poll, test the polling source directly, or use a latch/queue with a timeout. This keeps tests fast, deterministic, and free of wasted waits.

## 12. ChannelInterceptor to observe without replacing the handler

When testing header enrichment or channel send properties, you can register a <code>ChannelInterceptor</code> on the channel:

~~~java
@Test
void channelInterceptorSeesMessageAtSendBoundary() {
    DirectChannel channel = new DirectChannel();
    AtomicReference<Message<?>> intercepted = new AtomicReference<>();
    AtomicReference<Message<?>> delivered = new AtomicReference<>();

    channel.addInterceptor(new ChannelInterceptor() {
        @Override
        public Message<?> preSend(Message<?> message, MessageChannel ch) {
            intercepted.set(message);
            return message;
        }
    });

    channel.subscribe(delivered::set);

    Message<String> request = MessageBuilder.withPayload("data")
        .setHeader("correlationId", "corr-77")
        .build();

    channel.send(request);

    assertSame(request, intercepted.get());
    assertSame(request, delivered.get());
}
~~~

<code>ChannelInterceptor</code> belongs to <code>org.springframework.messaging.support</code>. The test checks the channel boundary, though it cannot tell whether another outbound adapter actually ACKed the data.

If you want to verify that an interceptor **mutates the message** (e.g., adds a header), assert on the message **actually received by the subscriber**, not just the message the interceptor observed in <code>preSend()</code>.

## 13. Testing errors: synchronous and asynchronous are two different contracts

### 13.1. DirectChannel: the caller sees the exception

In the fixture from section 9, the input is a <code>DirectChannel</code>. The test can call <code>assertThrows(MessagingException.class, ...)</code> when the service activator throws a runtime error. This proves the exception unwinds the synchronous call stack, not that the global <code>errorChannel</code> received an error.

### 13.2. ExecutorChannel/poller: errors may occur on the worker

If the handler runs on an executor, the sender may have already received <code>send() == true</code> before the error occurs. You must test the **configured error-reporting mechanism**, such as Spring Integration's error handler/error channel or the container/adapter error flow:

~~~text
Sender ──send() accepted──> ExecutorChannel
                               │
                               ▼
                          Worker thread
                               │
                          handler fails
                               │
                               ▼
                     Error handler / ErrorMessage
                               │
                               ▼
                        test error sink
~~~

To test this, replace the handler with a fake that throws an exception, configure the error channel at the right boundary, and use a <code>QueueChannel</code> as the error sink. Assert that the <code>ErrorMessage</code> contains the <code>Throwable</code> along with original/failed message info if supplied by the producer. **Do not assume** every <code>ExecutorChannel</code> automatically publishes errors to an arbitrarily named queue without configuration.

| Failure | What to verify |
|---|---|
| Conversion/transformer error before handler | Handler is not called; error appears at the proper upstream boundary |
| Handler throws synchronously | Caller or gateway receives error per <code>DirectChannel</code> semantics |
| Handler fails after async handoff | Error flow or worker logging receives error; sender is not mis-asserted |
| Retries exhausted | Attempt count is exact; final error is propagated/recovered per policy |
| Recovery swallows exception | Accepted intentionally, not mistaken for successful business processing |
| Error flow also throws | Secondary failure is observed without hanging the test forever |

A published <code>ErrorMessage</code> **does not prove** the source message rolled back, was not ACKed, or will be redelivered. To confirm those, you must test the message source/adapter itself and its transaction.

## 14. Testing retry and transactions around handlers

Suppose a service can encounter transient errors. <code>RequestHandlerRetryAdvice</code> wraps the handler invocation; you need to test both attempt counts and post-retry outcomes.

### Successful retry scenario

1. Create a fake service or handler that fails with a transient error on the first two attempts.
2. Configure a retry policy with up to three attempts; set test backoff to 0 or very short so the suite is not slowed down.
3. Send one message to the endpoint carrying the advice.
4. Verify the service was called **three times** and output contains only one valid result.
5. Verify no duplicate side effects occurred if a prior attempt wrote partial data.

### Exhausted retry scenario

1. The fake always throws a transient error.
2. Verify it stops at the exact attempt count; no infinite retries.
3. For synchronous flows, assert the exception; for async, assert the error sink/recovery.
4. Check that message/correlation IDs remain identifiable through the error.

**Key point:** If a test only verifies mock call counts, it does not prove **a fresh transaction is created per retry**. One outer transaction spanning multiple attempts may already be marked rollback-only after the first attempt. To prove rollback, use a real database or Testcontainers with a real transaction manager and read data **after the transaction ends**.

| Boundary to test | Testing approach to choose |
|---|---|
| Handler validation, Java result | Direct unit test |
| Retry advice + dispatch + attempt count | Flow test, fake handler/repository |
| JDBC commit/rollback when downstream throws | Integration test with real DB and transaction manager |
| Message receive rollback in a transactional queue | Test persistent channel/store and poller transaction |
| ACK/requeue/DLQ in Kafka/JMS/AMQP | Test with the appropriate adapter/container/broker |
| Idempotency after redelivery | Produce duplicates with the same business event ID, assert only one side effect |

**Avoid putting <code>@Transactional</code> on the test itself** if your goal is to verify transactions committed by a production facade/poller. An outer test transaction can roll back data after the test and mask the flow's real commit/rollback boundary.

## 15. Testing correlation, message headers, and group stores

Even when focusing on channels and handlers, a message can carry headers that control the flow:

| Header/identifier | Test goal | Common mistake |
|---|---|---|
| <code>MessageHeaders.ID</code> | Each message has a valid ID | Comparing absolute IDs across rebuilt messages |
| <code>MessageHeaders.TIMESTAMP</code> | Timestamp is present where supported | Asserting exact millisecond equality |
| <code>correlationId</code> | Header passes through transformer/handler per contract | Treating correlation ID as a transaction ID |
| <code>replyChannel</code> | Gateway or handler sends reply to the right destination | Forgetting reply configuration in request–reply tests |
| <code>errorChannel</code> | Error path routes to the right boundary | Assuming the header turns every exception into an ErrorMessage automatically |
| Business event ID | Idempotency across retry/redelivery | Using a newly generated message ID as the idempotency key |

For an aggregator, you can send fragments **with the same correlation key**, verify no output exists while incomplete, then send the final fragment and assert **one** group is released. Tests should also check late messages, group timeouts, and store cleanup. Using <code>SimpleMessageStore</code> in tests does not prove behavior across restarts; with <code>JdbcMessageStore</code>, test multiple application contexts sharing the same backend and data.

**Do not assert a specific header passes through every adapter unless a contract exists.** Some transformers/service activators construct new messages, and some transport mappers filter headers by policy. Tests must set the header at input and verify the receiver gets the required fields.

## 16. Testing pollers and lifecycle without arbitrary waits

A polling consumer starts via a task scheduler or trigger. If a test just waits with <code>Thread.sleep(500)</code> and then checks for a message, it easily fails on slow CI or loaded machines.

More stable design patterns:

- Use <code>@SpringIntegrationTest(noAutoStartup = ...)</code> so real adapters do not start during fixture initialization.
- Substitute <code>MessageSource</code> with <code>MockIntegration.mockMessageSource(...)</code> or a custom <code>MessageSource</code> that counts polls.
- Tune triggers for testing; since Spring Integration 6.3, <code>substituteTriggerFor(...)</code> is available on <code>MockIntegrationContext</code>.
- Set explicit <code>maxMessagesPerPoll</code> and output queues; assert received message counts and that no unexpected extra polls occurred.
- Test start/stop via endpoint <code>SmartLifecycle</code> or flow registration; assert <code>isRunning()</code> and no **new polls** after stop, while handling in-flight tasks per policy.

Lifecycle tests should recognize that <code>stop()</code> does not necessarily wait for all already-submitted executor tasks to finish. Never assert a queue is immediately empty just because the endpoint reports <code>isRunning() == false</code>.

## 17. TestUtils and inspecting internal configuration

<code>spring-integration-test-support</code> provides <code>TestUtils</code>. When you need to inspect dispatcher configuration or bean internals that lack public getters:

~~~java
LoadBalancingStrategy strategy = TestUtils.getPropertyValue(
    directChannel,
    "dispatcher.loadBalancingStrategy",
    LoadBalancingStrategy.class);

assertNotNull(strategy);
~~~

<code>TestUtils</code> belongs to <code>org.springframework.integration.test.util</code>; <code>LoadBalancingStrategy</code> belongs to <code>org.springframework.integration.dispatcher</code>. <code>getPropertyValue()</code> uses <code>DirectFieldAccessor</code> and supports nested field paths.

**Warning:** This checks an implementation detail. Across framework upgrades, internal field or dispatcher names may change even when external behavior does not. Prefer behavioral tests via messages/callbacks first, and reserve <code>TestUtils</code> for properties that genuinely need configuration-level verification.

## 18. Reasons channel/handler tests become flaky

| Symptom | Common cause | Mitigation |
|---|---|---|
| Passes alone, fails in full suite | Cached Spring context, unreset mock handler, leftover queue messages | <code>resetBeans()</code>, isolated fixtures, and queue draining in cleanup |
| <code>assertThrows()</code> sees no error | Handler runs asynchronously or has recovery advice | Check thread boundary, error sink, and recovery policy |
| <code>receive()</code> returns <code>null</code> | Endpoint not started, message routed elsewhere, worker has not run, or no output | Check topology/endpoint lifecycle; conditional wait with timeout |
| Test hangs forever | <code>receive()</code> without timeout, deadlock, poller waiting on source | Use explicit deadlines and log state on expiration |
| First message in next test has previous test's data | Shared <code>QueueChannel</code> not drained | Use unique correlation, drain/reset fixture |
| Mock verification fails on invocation count | Retries, subscriber fan-out, repeated polling | Distinguish logical message from attempt count |
| Unexpected correlation ID | Transformer rebuilds message, adapter header mapper strips header | Check per-step contract and header propagation |
| Throughput test fluctuates wildly | Relies on <code>Thread.sleep</code> or real scheduler | <code>CountDownLatch</code>, controlled triggers, virtual time when applicable |
| DB test sees data “disappear” | Outer test transaction rolled back | Read state after production commit boundary; avoid accidental nested test transactions |
| Test with fakes still connects to broker | Inbound adapter auto-started before mocking | <code>noAutoStartup</code>, fixture context, or test profile |

### Procedure to debug a failing test

1. Verify the input channel in the test is the **exact bean** the endpoint subscribes to.
2. Check endpoint ID, running status, subscriber count, and routing configuration.
3. Determine whether it is a <code>DirectChannel</code> or an async/pollable boundary; check if <code>send()</code> can finish early.
4. Inspect messages on the output sink including payload, headers, message ID, and correlation.
5. If there is no output, inspect the error sink, exception cause, retry count, and poller scheduler.
6. Check whether mocks/queues/contexts retain state from an earlier test.
7. If transactions or a broker are involved, look for real commit/ACK/redelivery evidence rather than inferring from handler logs.

## 19. Checklist for a reliable test suite

- [ ] Every test states its completion boundary: accepted send, handler completion, reply present, or transaction commit.
- [ ] <code>DirectChannel</code> tests prove synchronous dispatch and exception propagation.
- [ ] <code>QueueChannel</code> tests prove capacity/send/receive; never treat enqueuing as business processing.
- [ ] <code>ExecutorChannel</code> tests use latches/futures and finite timeouts instead of arbitrary sleeps.
- [ ] Flow tests via Spring context verify handler wiring, payload, headers, and output/error channels.
- [ ] When mocking endpoints, use the exact endpoint ID and restore with <code>MockIntegrationContext.resetBeans()</code>.
- [ ] Real inbound adapters are isolated with <code>noAutoStartup</code> or test profiles when external infrastructure is unnecessary.
- [ ] Retries and transactions have dedicated tests for attempt counts, duplicate side effects, rollback, and final exceptions.
- [ ] Message stores, pollers, broker ACK/requeue, and multi-threading are tested at the appropriate integration layer.
- [ ] Tests clean up channel state, contexts, executors, schedulers, and mocks after every case.
- [ ] Logs/traces expose correlation and endpoint/thread info; tests never depend on random message IDs or timestamps.
- [ ] Asynchronous assertions use conditional waits with deadlines and emit useful diagnostics on expiration.

**Conclusion:** Testing Spring Integration at runtime means testing the **contracts of channels and endpoints**, not just business methods. <code>DirectChannel</code> provides a synchronous boundary that is easy to assert; <code>QueueChannel</code> helps observe queued messages; <code>ExecutorChannel</code> forces tests to separate sending from completion. By combining <code>@SpringIntegrationTest</code>, <code>MockIntegrationContext</code>, fake handlers/sources, and dedicated transaction–retry–correlation tests, you can catch threading, error-routing, and lifecycle bugs before deploying real message flows.

## References

- [Spring Integration Reference — Testing Support](https://docs.spring.io/spring-integration/reference/testing.html)
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html)
- [Spring Integration Reference — Message Endpoints](https://docs.spring.io/spring-integration/reference/endpoint.html)
- [Spring Integration 6.5 Javadoc — MockIntegrationContext](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/test/context/MockIntegrationContext.html)
- [Spring Integration 6.5 Javadoc — MockIntegration](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/test/mock/MockIntegration.html)
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
