# @RecordApplicationEvents and ApplicationEvents

## 1. Purpose and Scope

When a Spring Boot service publishes an **application event**, what needs to be tested is not only whether “ApplicationEventPublisher.publishEvent(...) was called”, but also **which event was published, whether the payload has the right business fields, how many events were emitted in a scenario, whether any event is emitted on invalid input, and which listener actually handles it**. Under the **Events and Observability** group, Spring TestContext provides **@RecordApplicationEvents** together with **ApplicationEvents** to observe events **inside the ApplicationContext during the lifecycle of a single test method**.

This lesson uses **Java 17, Spring Boot 3.4.5, Spring Framework 6.2, JUnit Jupiter, and spring-boot-starter-test**. The example includes a PaymentService that publishes a **PaymentRecordedEvent** record payload, a synchronous listener that writes observation data to an in-memory projection, **@SpringBootTest + @RecordApplicationEvents** integration tests, and a set of Mockito unit tests without a context. We also distinguish **event publication** from **async listener completion**, **@TransactionalEventListener AFTER_COMMIT**, events emitted by Spring TestContext, and the limits of the event recorder when tests run across different threads or over HTTP.

**Key takeaway:** **@RecordApplicationEvents proves that an application event was published within the scope recorded by the TestContext recorder; it does not by itself prove that a broker received a message, a DB committed, an async listener completed, or the system has observability metrics/traces.** Those are separate contracts that must be tested independently.

The full source snippets below are designed to compile with Java 17 and Spring Boot 3.4.5. No actual Gradle execution output is assumed during authoring.

## 2. Why Use Events in Spring?

**ApplicationEventPublisher** allows a component to publish events to listeners within the same Spring ApplicationContext, reducing direct coupling between a business service and downstream behaviors. For example:

~~~text
HTTP/controller or command
       |
       v
 PaymentService.recordPayment(paymentId, amountMinor)
       |
       +--> validate input
       |
       +--> publisher.publishEvent(PaymentRecordedEvent)
                        |
                        v
           Spring ApplicationEventMulticaster
                        |
             +----------+-----------+
             |                      |
             v                      v
    PaymentAuditProjection    NotificationListener
      @EventListener          @EventListener/@Async
             |                      |
             v                      v
        in-memory view        notification action
~~~

An **event record** typically carries data representing a business fact that has occurred. This demo uses PaymentRecordedEvent(String paymentId, long amountMinor), not a Kafka record or JPA entity.

**Spring application events are an in-process mechanism.** If the JVM stops or the service runs across multiple replicas, events are not automatically persisted durably or sent to other replicas. For reliable cross-service messaging, an appropriate broker/outbox/integration test is needed; merely observing Spring events does not provide delivery guarantees.

### ApplicationEvent Subclass vs. POJO Payload Events

Spring supports two common ways to publish events:

1. **ApplicationEvent subclass:** create a class extending org.springframework.context.ApplicationEvent with a source and fields. When stream() returns ApplicationEvent objects, that subclass is the event object.
2. **POJO/record payload:** call publisher.publishEvent(new PaymentRecordedEvent(...)) with a Java record that does not extend ApplicationEvent. Spring can **wrap the payload in a PayloadApplicationEvent** during dispatch. **ApplicationEvents.stream(PaymentRecordedEvent.class)** retrieves the strongly typed payload, instead of casting a raw ApplicationEvent to the Java record.

In this lesson, we use a **Java record payload** because it expresses domain data cleanly and avoids coupling business events to the ApplicationEvent class. The custom ApplicationEvent subclass case is illustrated in a later section.

### Publishing Does Not Mean Delivery Has Completed

By default, Spring event listeners are invoked **synchronously on the publishing thread** when using the default multicaster without an async executor. However, if @Async or a custom ApplicationEventMulticaster uses a TaskExecutor, the listener may run on a different thread. And with **@TransactionalEventListener(phase=AFTER_COMMIT)**, the listener is deferred until transaction commit, rather than running at the moment of publication.

Therefore, a test must clarify whether it is verifying **publication**, **listener invocation**, **side effect**, **commit**, or **remote delivery**; do not conflate these distinct pieces of evidence into a single count assertion.

## 3. What Does @RecordApplicationEvents Do?

**org.springframework.test.context.event.RecordApplicationEvents** is an annotation **placed on a test class** (and can be used as a meta-annotation). It instructs the Spring TestContext Framework to record application events published in the ApplicationContext during the execution of a test method. Spring Framework provides **ApplicationEventsTestExecutionListener**, which is registered by default in TestContext's set of TestExecutionListeners.

Usage with JUnit Jupiter:

~~~java
@SpringBootTest
@RecordApplicationEvents
class PaymentEventsIntegrationTest {

    @Test
    void recordsPublishedPayment(
            ApplicationEvents events) {
        // events is the recorder scoped to the current test method.
    }
}
~~~

**Exact imports:**

~~~java
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.test.context.event.ApplicationEvents;
~~~

This annotation is **not** org.springframework.context.event.RecordApplicationEvents, nor is it a Micrometer annotation. This API lives in **spring-test**, which is brought into test scope via **spring-boot-starter-test**.

**Spring TestContext/JUnit Jupiter SpringExtension is required.** @SpringBootTest and @SpringJUnitConfig provide that integration. A plain JUnit test with MockitoExtension will not automatically create an ApplicationEvents recorder just because you add @RecordApplicationEvents without a Spring context.

### How to Obtain ApplicationEvents

**Prefer a method parameter** in @Test, @BeforeEach, or @AfterEach when using SpringExtension:

~~~java
@Test
void example(ApplicationEvents events) {
    events.clear();
    // ...
}
~~~

Or inject it as a field:

~~~java
@Autowired
private ApplicationEvents events;
~~~

**Do not inject ApplicationEvents into the constructor of a test class.** It is a dependency scoped to the **current test method lifecycle**, and is not yet available when the test constructor is invoked. With JUnit Jupiter, method parameter injection is the clearest choice.

**@RecordApplicationEvents does not automatically write a log file.** It provides an in-memory recorder to query and assert events in tests. It does not replace application logs, Micrometer Observation, tracing, or a durable audit log.

## 4. Which Methods Does ApplicationEvents Provide?

In Spring Framework 6.2, the **ApplicationEvents** interface has three main methods:

| API | Meaning | When to Use |
| --- | --- | --- |
| **stream()** | Streams the **ApplicationEvent** instances recorded during the test | Inspecting raw event wrappers/types or lifecycle events |
| **stream(Class<T> type)** | Streams events or **payloads** of the requested type | Most common for domain record events |
| **clear()** | Clears the events currently held in this recorder | Establishing a clean baseline before the action under test |

**There is no ApplicationEvents.count(), getEvents(), size(), or await() API** in the core Spring Framework 6.2 interface. To count:

~~~java
long count = events.stream(PaymentRecordedEvent.class).count();
~~~

To collect specific payloads:

~~~java
List<PaymentRecordedEvent> payments =
    events.stream(PaymentRecordedEvent.class).toList();
~~~

To filter by identity:

~~~java
List<PaymentRecordedEvent> matching =
    events.stream(PaymentRecordedEvent.class)
        .filter(event -> event.paymentId().equals(paymentId))
        .toList();
~~~

**Note:** stream(Class<T>) filters **both event instances and event payloads** matching the type. When publishing a Java record that does not extend ApplicationEvent, it is still found via **stream(PaymentRecordedEvent.class)**. With the raw **stream()**, the recorder provides a Stream<ApplicationEvent>, so POJO payloads typically appear via **PayloadApplicationEvent**.

### clear() Does Not Undo Already-Processed Events

**events.clear() only clears the test recorder's observed list.** It does not:
- Undo the business action;
- Clear the in-memory listener projection;
- Roll back a database transaction;
- Cancel @Async tasks or event delivery;
- Clear the Spring context cache;
- Prevent new events from appearing immediately afterward.

When a test needs an exact count of events emitted by **a single business action**, you can call events.clear() **at the start of the test method, right before the action**. Do not assume the raw stream is completely empty initially: Spring TestContext may publish lifecycle events during before-test phases, and @RecordApplicationEvents can record those events.

## 5. Levels of Evidence in Event Tests

| Question | Appropriate Test | What It Does Not Prove |
| --- | --- | --- |
| Did the service decide to publish the right payload? | Mockito unit test on ApplicationEventPublisher | Spring context/event multicaster |
| Was the event published in the Spring test context? | @RecordApplicationEvents + ApplicationEvents.stream(Type) | Async listener completion or DB commit |
| Did the synchronous listener execute its side effect? | @SpringBootTest + assert listener's observable state | Reliability if the JVM crashes |
| Is @EventListener registered and receiving the right payload? | Spring context integration | Broker delivery |
| Does the AFTER_COMMIT listener run after commit? | Transaction integration with real commit | Behavior on rollback or without a transaction |
| Has the @Async listener finished? | Await state/completion with bounded timeout | Recorder waiting for tasks on its own |
| Did Kafka/RabbitMQ receive the event? | Broker integration + consumer assertions | Spring ApplicationEvents alone |
| Is the business audit durable? | Database/outbox/transaction integration | In-memory projection test |
| Event metrics/trace? | Micrometer ObservationRegistry/trace assertions | ApplicationEvents is not ObservationRegistry |
| Cross-node event propagation? | Distributed/broker integration | ApplicationEventPublisher is local JVM only |

A green test only proves the assertions that the test actually observed. If a requirement states “send an invoice to the queue after DB commit”, asserting stream(OrderPaidEvent).count() == 1 alone is not enough; you must verify transaction/outbox/producer ack or consumer behavior at the appropriate level.

## 6. Runnable Java 17 / Spring Boot 3.4.5 Project

The project picks a small domain: **recording a payment** and emitting **PaymentRecordedEvent**. A synchronous listener updates an in-memory audit projection. No DB, Kafka, or HTTP is used because the main topic is the **ApplicationEvents recorder**.

### 6.1. File Tree

~~~text
settings.gradle
build.gradle
src/main/java/com/example/eventqa/EventQaApplication.java
src/main/java/com/example/eventqa/PaymentRecordedEvent.java
src/main/java/com/example/eventqa/PaymentService.java
src/main/java/com/example/eventqa/PaymentAuditProjection.java
src/test/java/com/example/eventqa/PaymentServiceUnitTest.java
src/test/java/com/example/eventqa/PaymentEventsIntegrationTest.java
~~~

### 6.2. settings.gradle

~~~groovy
rootProject.name = 'spring-application-events-testing'
~~~

### 6.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.4.5'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
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
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**spring-boot-starter** brings in Spring core/context, lifecycle, and logging. **spring-boot-starter-test** provides spring-test, JUnit Jupiter, Mockito, and test helpers. You do not need spring-boot-starter-web if there is no HTTP controller. Do not add Kafka/Testcontainers just to count a Spring application event.

Using **./gradlew** requires Gradle Wrapper scripts in the project; if not yet generated, use an installed Gradle or generate the Wrapper first. The code files are presented in full; do not assume the Gradle Wrapper already exists.

### 6.4. EventQaApplication.java

**src/main/java/com/example/eventqa/EventQaApplication.java**

~~~java
package com.example.eventqa;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class EventQaApplication {
    public static void main(String[] args) {
        SpringApplication.run(EventQaApplication.class, args);
    }
}
~~~

The Application class resides in the same root package so component scanning finds PaymentService and PaymentAuditProjection. @SpringBootTest can locate @SpringBootConfiguration from this class. There is no embedded web server because the project does not use starter-web.

### 6.5. PaymentRecordedEvent.java

**src/main/java/com/example/eventqa/PaymentRecordedEvent.java**

~~~java
package com.example.eventqa;

public record PaymentRecordedEvent(
        String paymentId,
        long amountMinor) {
}
~~~

This Java record **does not extend ApplicationEvent**. Spring will publish it as a **payload event**. Therefore, **events.stream(PaymentRecordedEvent.class)** is the right way to retrieve the payload in tests, while **events.stream()** iterates over Spring ApplicationEvent wrappers.

**paymentId** lets you filter the exact event under test even when multiple events of the same type exist in a single context. **amountMinor** is an integer value in the smallest currency unit defined by the application contract, avoiding double for money representation.

### 6.6. PaymentService.java

**src/main/java/com/example/eventqa/PaymentService.java**

~~~java
package com.example.eventqa;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {

    private final ApplicationEventPublisher publisher;

    public PaymentService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void recordPayment(String paymentId, long amountMinor) {
        if (paymentId == null || paymentId.isBlank()) {
            throw new IllegalArgumentException(
                    "paymentId must not be blank");
        }
        if (amountMinor <= 0) {
            throw new IllegalArgumentException(
                    "amountMinor must be positive");
        }

        publisher.publishEvent(
                new PaymentRecordedEvent(paymentId, amountMinor));
    }
}
~~~

**Service responsibility:** validate input and publish the event. There is no transaction, persistence, or deduplication in this example. **Two calls with the same paymentId produce two publications**; that is not a bug in ApplicationEvents, but an explicit limitation of the business implementation.

**If a synchronous listener throws an exception, publishEvent may propagate the error to the caller** depending on the multicaster/error handler. If the listener is async, the publisher may return before the listener runs, and an async exception will not automatically propagate to this call stack.

### 6.7. PaymentAuditProjection.java

**src/main/java/com/example/eventqa/PaymentAuditProjection.java**

~~~java
package com.example.eventqa;

import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class PaymentAuditProjection {

    private final ConcurrentHashMap<String, PaymentRecordedEvent> items =
            new ConcurrentHashMap<>();

    @EventListener
    public void onPaymentRecorded(PaymentRecordedEvent event) {
        items.put(event.paymentId(), event);
    }

    public Optional<PaymentRecordedEvent> find(String paymentId) {
        return Optional.ofNullable(items.get(paymentId));
    }
}
~~~

This is a **default synchronous** listener, with no @Async annotation and no custom multicaster. When PaymentService.publishEvent returns normally, the listener has been invoked by default, so the test can inspect the projection immediately after publication.

**This projection is not durable.** It stores the latest event per paymentId in a ConcurrentHashMap. If the same paymentId is published twice, the map still has one key, yet **the ApplicationEvents recorder can record two occurrences**. Do not treat the number of rows in the projection as the number of events published.

The paymentId value in each integration test is uniquely generated (UUID) to avoid depending on data from a previous method even when Spring TestContext caches the ApplicationContext and bean state.

## 7. Unit Test Without Spring Context: Mockito Publisher

**src/test/java/com/example/eventqa/PaymentServiceUnitTest.java**

~~~java
package com.example.eventqa;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.context.ApplicationEventPublisher;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

@ExtendWith(MockitoExtension.class)
class PaymentServiceUnitTest {

    @Mock
    private ApplicationEventPublisher publisher;

    private PaymentService service;

    @BeforeEach
    void setUp() {
        service = new PaymentService(publisher);
    }

    @Test
    void validPaymentPublishesExactPayload() {
        service.recordPayment("pay-101", 2500L);

        ArgumentCaptor<PaymentRecordedEvent> captor =
                ArgumentCaptor.forClass(PaymentRecordedEvent.class);

        verify(publisher).publishEvent(captor.capture());

        PaymentRecordedEvent event = captor.getValue();
        assertEquals("pay-101", event.paymentId());
        assertEquals(2500L, event.amountMinor());
    }

    @Test
    void invalidInputPublishesNothing() {
        assertThrows(IllegalArgumentException.class,
                () -> service.recordPayment(" ", 2500L));

        assertThrows(IllegalArgumentException.class,
                () -> service.recordPayment("pay-102", 0L));

        verifyNoInteractions(publisher);
    }

    @Test
    void synchronousPublisherFailurePropagates() {
        IllegalStateException cause =
                new IllegalStateException("listener rejected event");

        doThrow(cause).when(publisher)
                .publishEvent(any(PaymentRecordedEvent.class));

        IllegalStateException actual = assertThrows(
                IllegalStateException.class,
                () -> service.recordPayment("pay-103", 2500L));

        assertSame(cause, actual);
    }
}
~~~

**What this proves:** valid input emits a Java record with the exact paymentId/amountMinor; invalid input never calls the publisher; an error thrown from publishEvent via the mock propagates rather than being swallowed by the service.

**What this does not prove:** whether Spring actually dispatches to @EventListener, whether a PayloadApplicationEvent wrapper is created, whether the recorder works, or whether listener side effects succeed. Because the test does not start a Spring context, it only guards the business decision/boundary.

**Mockito overload note:** ApplicationEventPublisher has publishEvent(ApplicationEvent) and publishEvent(Object); **PaymentRecordedEvent is a POJO record**, so the compile-time call selects the Object overload. ArgumentCaptor<PaymentRecordedEvent> and any(PaymentRecordedEvent.class) allow Mockito to capture the right overload in tests.

## 8. Real Integration Test with @RecordApplicationEvents

**src/test/java/com/example/eventqa/PaymentEventsIntegrationTest.java**

~~~java
package com.example.eventqa;

import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.PayloadApplicationEvent;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@RecordApplicationEvents
class PaymentEventsIntegrationTest {

    @Autowired
    private PaymentService service;

    @Autowired
    private PaymentAuditProjection audit;

    @Test
    void recordsSingleEventWithExactPayload(
            ApplicationEvents events) {

        // Exclude framework/startup events recorded before the action.
        events.clear();

        String id = "pay-" + UUID.randomUUID();
        service.recordPayment(id, 4000L);

        List<PaymentRecordedEvent> recorded =
                events.stream(PaymentRecordedEvent.class)
                    .filter(event -> event.paymentId().equals(id))
                    .toList();

        assertEquals(1, recorded.size());
        assertEquals(id, recorded.get(0).paymentId());
        assertEquals(4000L, recorded.get(0).amountMinor());

        // Synchronous @EventListener has already updated the projection.
        PaymentRecordedEvent projected =
                audit.find(id).orElseThrow();
        assertEquals(4000L, projected.amountMinor());
    }

    @Test
    void invalidCommandProducesNoPaymentEvent(
            ApplicationEvents events) {

        events.clear();

        org.junit.jupiter.api.Assertions.assertThrows(
            IllegalArgumentException.class,
            () -> service.recordPayment(" ", -1L));

        assertEquals(0L,
            events.stream(PaymentRecordedEvent.class).count());
    }

    @Test
    void streamByPayloadTypeUnwrapsPojoEvent(
            ApplicationEvents events) {

        events.clear();

        String id = "pay-" + UUID.randomUUID();
        service.recordPayment(id, 10L);

        // Typed API returns the Java record payload.
        assertEquals(1L,
            events.stream(PaymentRecordedEvent.class)
                .filter(event -> event.paymentId().equals(id))
                .count());

        // Raw API returns the ApplicationEvent wrapper.
        assertEquals(1L,
            events.stream()
                .filter(event ->
                    event instanceof PayloadApplicationEvent<?> payload
                    && payload.getPayload()
                        instanceof PaymentRecordedEvent payment
                    && payment.paymentId().equals(id))
                .count());
    }

    @Test
    void recorderClearDoesNotUndoListenerSideEffect(
            ApplicationEvents events) {

        events.clear();

        String id = "pay-" + UUID.randomUUID();
        service.recordPayment(id, 50L);

        assertEquals(1L,
            events.stream(PaymentRecordedEvent.class)
                .filter(event -> event.paymentId().equals(id))
                .count());

        events.clear();

        // Recorder is empty, but listener state remains.
        assertEquals(0L,
            events.stream(PaymentRecordedEvent.class).count());
        assertTrue(audit.find(id).isPresent());
    }

    @Test
    void twoPublicationsAppearAsTwoOccurrences(
            ApplicationEvents events) {

        events.clear();

        String id = "pay-" + UUID.randomUUID();

        service.recordPayment(id, 100L);
        service.recordPayment(id, 100L);

        assertEquals(2L,
            events.stream(PaymentRecordedEvent.class)
                .filter(event -> event.paymentId().equals(id))
                .count());

        // Projection map only retains the latest value for the key.
        assertTrue(audit.find(id).isPresent());
    }

    @Test
    void typedStreamCanFilterDifferentBusinessIds(
            ApplicationEvents events) {

        events.clear();

        String first = "pay-" + UUID.randomUUID();
        String second = "pay-" + UUID.randomUUID();

        service.recordPayment(first, 1000L);
        service.recordPayment(second, 2000L);

        List<PaymentRecordedEvent> result =
                events.stream(PaymentRecordedEvent.class)
                    .filter(event -> event.paymentId().equals(second))
                    .toList();

        assertEquals(1, result.size());
        assertEquals(2000L, result.get(0).amountMinor());
    }
}
~~~

### Reading the Assertions Precisely

**recordsSingleEventWithExactPayload:** events.stream(PaymentRecordedEvent.class) returns exactly one event for the paymentId under test. Assert the fields, not just the count. Then inspect the listener projection to prove the **synchronous @EventListener** executed its side effect.

**invalidCommandProducesNoPaymentEvent:** service validation throws an exception before publishing. Assert **0 domain events of the expected type**. Do not assert that stream() has 0 raw events because Spring TestContext can emit lifecycle events of other types.

**streamByPayloadTypeUnwrapsPojoEvent:** proves the typed stream returns the record payload; raw stream() includes **PayloadApplicationEvent**. Do not cast directly to the Java record from stream() without unwrapping.

**recorderClearDoesNotUndoListenerSideEffect:** clear() only empties the recorder, while the audit map still holds the entry; this marks a clear boundary between **observing publication** and **mutating state**.

**twoPublicationsAppearAsTwoOccurrences:** if the service publishes twice with the same paymentId, the recorder counts 2. Do not infer from the Map projection holding only 1 key that the business logic deduplicates duplicate events. Production requires idempotent processing if the requirement demands it.

**typedStreamCanFilterDifferentBusinessIds:** a single context can hold multiple events; filtering by type and identity keeps tests accurate without relying on the Nth element index in raw global events.

### Why Call events.clear() at the Start of Each Test Method?

The recorder captures events across the test lifecycle; TestContext can emit lifecycle events such as BeforeTestMethodEvent/BeforeTestExecutionEvent, or other components might publish events before the business action. **events.clear() establishes a baseline right inside the test method**, close to the action being observed. When you want to verify a setup event, do not clear that event before the assertion; instead filter by type/correlation ID.

**Independent test methods:** each method generates its own UUID, avoids @TestMethodOrder, and does not rely on the audit projection containing data from a previous test. The context may be cached by Spring and the projection is a singleton, but the tests do not count the entire map and do not use fixed keys, so they have no ordering dependencies.

## 9. ApplicationEvent Subclass Events

When an event extends ApplicationEvent, no PayloadApplicationEvent wrapper is needed to represent the payload. Below is a **standalone illustrative example, not part of the runnable tree**:

~~~java
public final class PaymentSettledEvent
        extends org.springframework.context.ApplicationEvent {

    private final String paymentId;

    public PaymentSettledEvent(
            Object source, String paymentId) {
        super(source);
        this.paymentId = paymentId;
    }

    public String getPaymentId() {
        return paymentId;
    }
}
~~~

In a Spring-managed component:

~~~java
publisher.publishEvent(
    new PaymentSettledEvent(this, "pay-200"));
~~~

The test can use:

~~~java
assertEquals(1L,
    events.stream(PaymentSettledEvent.class)
        .filter(event -> event.getPaymentId().equals("pay-200"))
        .count());
~~~

These are **illustrative snippets**, without complete imports/test classes, and do not need to be added to the main project. They help distinguish the two styles:

| Event Form | Object Passed to publishEvent | Typed Stream Result | Raw Stream |
| --- | --- | --- | --- |
| Java record/POJO | new PaymentRecordedEvent(...) | PaymentRecordedEvent payload | Typically PayloadApplicationEvent |
| ApplicationEvent subclass | new PaymentSettledEvent(source,...) | PaymentSettledEvent instance | ApplicationEvent subclass |
| Framework lifecycle event | ApplicationReadyEvent or TestContext event | Corresponding event type | ApplicationEvent subclass |

**Do not confuse PayloadApplicationEvent with the business event type.** Using stream(PaymentRecordedEvent.class), the Spring Test API already gives access to the strongly typed payload, keeping test code cleaner.

## 10. What Scope Does @RecordApplicationEvents Record?

According to the TestContext Framework, the recorder is **test-method scoped** and tied to a thread-local/inheritable context for the test. It targets events emitted by the **test thread or its descendant threads** during the test lifecycle.

This has important consequences:

1. **@RecordApplicationEvents is required on the class/meta-annotation** for TestContext to enable recording.
2. **ApplicationEventsTestExecutionListener must be present.** It is registered by default; a custom @TestExecutionListeners that replaces defaults can accidentally drop this listener.
3. **Events published before the recorder starts** (for example, many application startup events when the context is cached/initialized before the test) should not be assumed to appear reliably.
4. **Events published after the test finishes** are outside the lifecycle for asserting via that method's recorder.
5. **Pre-existing thread pools** and servlet container threads are not necessarily descendants of the test thread, so events published there **might not be recorded in the test recorder**.
6. **Parallel tests sharing an ApplicationContext** can observe events from other tests in certain scenarios; avoid counting global events and sharing mutable state.
7. **@TestInstance(PER_CLASS) combined with @RecordApplicationEvents and parallel test methods** is not supported in Spring TestContext versions; prefer the default PER_METHOD, @Execution(SAME_THREAD) when needed, or disable parallel execution.

**Do not use ApplicationEvents as a global event bus hook to monitor every thread of a running application.** It is a scoped testing utility. If an integration test sends an HTTP request to a **RANDOM_PORT** server thread, events may fall outside the recorder scope; instead, assert durable state, use a thread-safe test listener/queue, or test a message broker with a completion signal.

### Custom @TestExecutionListeners

By default, TestContext registers ApplicationEventsTestExecutionListener. If a test class declares custom listeners and accidentally replaces all defaults, the recorder may stop working. Preserve defaults using merge mode when appropriate:

~~~java
@TestExecutionListeners(
    listeners = CustomListener.class,
    mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS)
~~~

This is a **snippet**, requiring a real CustomListener class and imports; it is not part of the runnable sample. Another option is to register the required listeners explicitly, though merging defaults is usually less error-prone. Avoid removing other TestExecutionListeners just to add logging.

## 11. @BeforeEach, @AfterEach, Field Injection, and Constructor Scope

In JUnit Jupiter + SpringExtension, ApplicationEvents can be injected into methods:

~~~java
@BeforeEach
void before(ApplicationEvents events) {
    events.clear();
}

@Test
void test(ApplicationEvents events) {
    // Call service then assert stream(...)
}

@AfterEach
void after(ApplicationEvents events) {
    // Can inspect recorded events at the end of the lifecycle.
}
~~~

**Timing note:** if @BeforeEach clears the recorder, events emitted by Spring TestContext after @BeforeEach (for example, before-test-execution) can still enter the raw stream. Thus, when a requirement needs to count raw events caused by a single action, call **events.clear() right before the action inside the @Test method** or filter by business event type/identity.

Field injection is also supported:

~~~java
@Autowired
private ApplicationEvents recordedEvents;
~~~

However, **ApplicationEvents as a test constructor parameter is not guaranteed** because the recorder is only active during the current test method lifecycle. Method parameter injection makes the scoping explicit and avoids holding long-lived references under @TestInstance(PER_CLASS) or nested/parallel tests.

**@AfterEach** can verify events published during the test, but should not assume an async listener has finished before @AfterEach. Separate completion signals/timeouts or durable state are needed to verify asynchronous behavior.

## 12. Synchronous @EventListener vs. Asynchronous Listeners

By default, Spring's ApplicationEventMulticaster invokes listeners **synchronously** on the publishing thread. In the sample project, PaymentAuditProjection.onPaymentRecorded runs before PaymentService.recordPayment(...) returns (unless a custom async multicaster is configured).

Therefore, after:

~~~java
service.recordPayment(id, 4000L);
assertEquals(1L,
    events.stream(PaymentRecordedEvent.class)
        .filter(e -> e.paymentId().equals(id))
        .count());
assertTrue(audit.find(id).isPresent());
~~~

the two assertions represent different pieces of evidence:
- the recorder has the event: **publication**;
- the audit map has the entry: **the listener executed its synchronous side effect**.

### If a Listener Has @Async

A listener like:

~~~java
@Async
@EventListener
public void sendNotification(PaymentRecordedEvent event) {
    // External notification or CPU work.
}
~~~

is an **illustrative snippet**, requiring @EnableAsync/TaskExecutor and a real implementation to run. @Async moves work onto an executor thread, so:
- publishEvent may return before the listener completes;
- exceptions in an async listener do not automatically propagate to the publisher thread;
- the event recorder is not a latch/await utility;
- tests must observe **observable completion** using CompletableFuture, CountDownLatch, Awaitility, or durable state with a bounded timeout;
- when a reused executor thread is not a true descendant of the test thread, the scoped ApplicationEvents recorder may miss events published inside the async listener;
- MDC/trace context does not propagate automatically across arbitrary thread boundaries; use proper context propagation if observability is required.

**Do not use Thread.sleep(300) and then assert count**: tests become flaky under machine load. If you need to test an async listener, use a test-controlled executor, a bounded wait, and assertions on the downstream side effect. Keep a separate recorder test for publication on the caller thread.

### Async Multicaster vs. @Async Listener

A **SimpleApplicationEventMulticaster** configured with a TaskExecutor can dispatch multiple listeners asynchronously. @Async on a method is a separate mechanism. If a project configures a global multicaster, even plain listeners can run on another thread; never assume an immediate audit map assertion is always valid. Know the app's actual scheduler/executor before writing tests.

## 13. @TransactionalEventListener: Event Published Before Commit Happens

**@TransactionalEventListener** runs by default in the **AFTER_COMMIT** phase when an event is published inside an active transaction. It differs from a regular @EventListener.

~~~java
@Component
class ReceiptSender {

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT)
    public void afterPaymentCommitted(
            PaymentRecordedEvent event) {
        // Call an appropriate service/send adapter.
    }
}
~~~

This is an **architectural snippet**, not part of the runnable project because the demo does not create a transaction manager or database. It requires imports org.springframework.transaction.event.TransactionalEventListener and org.springframework.transaction.event.TransactionPhase.

**Key points:**
- **events.stream(PaymentRecordedEvent.class)** may already see the event as soon as the service calls publishEvent **before commit**.
- **@TransactionalEventListener(AFTER_COMMIT)** only executes after the transaction actually commits successfully, and does not run on rollback.
- If published **without an active transaction**, the listener **does not run** by default unless **fallbackExecution=true** is set.
- **@TransactionalEventListener(BEFORE_COMMIT)**, **AFTER_ROLLBACK**, and **AFTER_COMPLETION** have different semantics and need dedicated tests when used.
- For reactive transactions, the transaction context lives in the Reactor Context rather than a ThreadLocal by default; in Spring Framework 6.1+, use appropriate mechanisms to publish/propagate transaction context rather than blindly applying thread-bound assumptions.
- After AFTER_COMMIT/AFTER_COMPLETION, transactional resources may still be accessible, yet commit has already completed; if the listener needs to perform new DB writes, it typically needs **REQUIRES_NEW** or a proper outbox/separate transaction matching the contract.

### The @Transactional Pitfall on Tests

Spring TestContext by default **rolls back the test-managed transaction** of a @Transactional test after the method completes. If you publish an event inside that transaction and assertions run **before rollback**, the recorder may still see the event, yet the **AFTER_COMMIT listener will not run**. Do not treat stream count=1 as proof that an after-commit notification was sent.

To test AFTER_COMMIT:
1. Use a real database and transaction manager, or a test-specific fixture.
2. Execute the business operation **inside a transaction that actually commits**, such as TransactionTemplate.executeWithoutResult, ending the transaction before asserting listener side effects.
3. Ensure the test is not wrapped by an outer @Transactional test transaction that rolls back; otherwise, TransactionTemplate by default may join the outer transaction that has not yet committed.
4. Assert the listener's side effect, not just the ApplicationEvents stream.
5. Clean up durable data against a test-only DB; never point to a shared production database.

An intentional sketch:

~~~java
transactionTemplate.executeWithoutResult(status -> {
    paymentService.recordPayment(id, 1000L);
});

// Once the transaction has committed, check the AFTER_COMMIT listener.
assertTrue(receiptStore.existsForPayment(id));
~~~

This is **not standalone runnable code**: it requires a TransactionTemplate/transaction manager, receiptStore, and separate database schema. It illustrates **the commit boundary before the assertion**; the main project above has no transactions and does not pretend to be an executed AFTER_COMMIT test.

### Publication vs. Persistence and Durable Messaging

ApplicationEventPublisher emits within the same JVM; transaction-bound listeners tie behavior to commit, but **do not guarantee exactly-once delivery to Kafka/email if the process crashes right after DB commit**. If DB + external event consistency is required, consider a **transactional outbox** and idempotent consumers. The test recorder is only one layer of evidence for publication, not a replacement for outbox/broker integration tests.

## 14. Framework Lifecycle Events and Why Not to Count the Raw Stream Blindly

In a Spring Boot application context and test lifecycle, there are many non-business events, such as:
- ContextRefreshedEvent, ContextClosedEvent;
- Spring Boot ApplicationStartedEvent, ApplicationReadyEvent (depending on phase/context lifecycle);
- Spring TestContext test execution events such as BeforeTestMethodEvent, BeforeTestExecutionEvent, AfterTestExecutionEvent, AfterTestMethodEvent;
- Events from other components in the application.

**Do not assume events.stream().count() == 1** just because the service published one PaymentRecordedEvent. The recorder may hold unrelated events from the same test, and even their timing differs.

Better:

~~~java
long count = events.stream(PaymentRecordedEvent.class)
    .filter(event -> event.paymentId().equals(id))
    .count();

assertEquals(1L, count);
~~~

Count **by exact type and identity** rather than the raw global list. If you want to check that a context refresh event occurred, you must understand when the recorder becomes active; startup events can occur before the current test method scope, so the TestContext recorder is not a reliable mechanism to capture **every** application-startup event.

**Per-method event recording** differs from Spring TestContext ApplicationContext caching. A singleton context can stay alive across tests; the recorder is created/scoped per test method, whereas listener state is not automatically reset. That is why the project uses UUIDs in business events and does not assert the total size of the projection map.

## 15. ApplicationEvents and Observability: Related, Not Synonymous

An application may need:
- **Application events**: business facts or technical signals published in-process.
- **Audit log**: a durable record of who did what and when, tamper-resistant, with retention.
- **Micrometer Observation**: duration, spans, metrics/traces, and context propagation.
- **Structured logging**: correlation IDs, requestId, paymentId, severity, and error reasons.
- **Message broker**: durable/remote event transport, ack, retry, DLT.
- **Domain event store/outbox**: transactionally persisted intent/events to recover after crashes.

**@RecordApplicationEvents only observes Spring events**. It does not automatically produce counters, spans, trace IDs, or audit records. If a requirement says “metric increments by one after payment”, test with an appropriate **MeterRegistry/ObservationRegistry**; if it says “PaymentRecordedEvent was published with the right amountMinor”, use ApplicationEvents. If it says “email sent after commit”, test the listener side effect/external adapter at a different layer.

### Avoid Exposing Sensitive Data via Application Events

Events can contain payment IDs, emails, user IDs, or sensitive data. Do not attach raw passwords, tokens, or card numbers to event payloads or automatically log event.toString() in production. Test fixtures should use synthetic IDs rather than copying real customer data. When forwarding to observability/telemetry, consider cardinality and redaction policies appropriately.

## 16. Multiple Publications, Duplicates, and Ordering Scenarios

Suppose a service calls:

~~~java
publisher.publishEvent(
    new PaymentRecordedEvent("pay-A", 100L));
publisher.publishEvent(
    new PaymentRecordedEvent("pay-B", 200L));
~~~

On the same publishing thread, with a synchronous multicaster and no listeners publishing nested events, the recorder can observe order A then B. However, **do not treat global ordering of the raw ApplicationEvents stream as a business invariant** when:
- listeners publish nested events;
- a custom async multicaster is used;
- multiple threads/HTTP requests publish concurrently;
- parallel tests share a context;
- @TransactionalEventListener defers handling to another phase;
- other events are interleaved by Spring/TestContext.

Prefer asserting the exact **count by type/paymentId** and fields, or write an ordering integration test matching the real contract when ordering is required.

**Duplicate business effects:** If the same paymentId is published twice, the recorder counts two events. In this lesson, the audit projection uses a map and keeps only the latest entry; that does **not** prove consumer idempotency in real life. To achieve “exactly one business action” semantics, you need unique constraints/transactions/outbox and tests for retry/concurrency scenarios.

### Event Publication During Rollback

Even if an event is named “PaymentConfirmed”, publishing inside a transaction that later rolls back can still leave the event visible in the recorder even though the payment did not commit. If an event truly must reflect durable success, consider publishing at the right boundary, using @TransactionalEventListener, or an outbox. Name events responsibly; do not create a mismatch between application events and actual database truth.

## 17. Choosing the Test Layer by Purpose

| Test Intent | Tool | Example Assertion |
| --- | --- | --- |
| Decision logic to emit an event | Mockito ApplicationEventPublisher | verify publishEvent exact event |
| Correct DTO payload | Mockito captor or ApplicationEvents typed stream | paymentId/amountMinor |
| Spring actually dispatches the event | @SpringBootTest + @RecordApplicationEvents | typed stream count |
| Synchronous listener was invoked | Spring context + listener state | audit.find(id) present |
| No event on invalid input | Unit + integration test | verifyNoInteractions / count0 |
| Raw POJO event wrapper | ApplicationEvents.stream() | PayloadApplicationEvent type |
| Recorder clear scope | ApplicationEvents.clear() | stream empty while projection unchanged |
| @TransactionalEventListener AFTER_COMMIT | TransactionTemplate + real commit | downstream side effect after commit |
| Async event handling | Completion signal/await | eventual side effect, timeout |
| HTTP-triggered event on real server thread | RANDOM_PORT integration + shared state/queue | response + side effect, not relying on recorder |
| Kafka downstream publication | EmbeddedKafka/Testcontainers/real broker | consumer receives record |
| Observability metrics/traces | MeterRegistry/ObservationRegistry | counter/timer/span assertions |

**Do not spin up a full @SpringBootTest for pure domain logic that only needs to verify a publisher call**. Conversely, **do not mock the entire ApplicationEventPublisher when the goal is Spring dispatch/registration**, because that bypasses the ApplicationContext behavior under test.

## 18. @SpringJUnitConfig and Narrow Contexts Instead of @SpringBootTest When Appropriate

A full Spring Boot context is useful for proving component scanning and auto-configuration. If you only want to test the Spring event bus with a few beans, you can use **@SpringJUnitConfig** with specific @Import/context classes:

~~~java
@SpringJUnitConfig(classes = {
    PaymentService.class,
    PaymentAuditProjection.class
})
@RecordApplicationEvents
class MinimalEventContextExample {

    @Autowired
    PaymentService service;

    @Test
    void records(ApplicationEvents events) {
        events.clear();
        service.recordPayment("pay-min", 100L);
        assertEquals(1L,
            events.stream(PaymentRecordedEvent.class).count());
    }
}
~~~

This is an **illustrative snippet** without imports in a runnable project file, though PaymentService and PaymentAuditProjection already exist in the source tree. SpringJUnitConfig combines SpringExtension with context configuration. It can avoid pulling in the full Boot context when testing simple event multicaster and listener registration.

**Do not force the Spring Boot test runner for every event check.** Weigh context cost against required evidence. When you want to prove real auto-configuration/context integration, @SpringBootTest still holds its distinct value.

## 19. Testing Nested Events and Listener Return Values

Spring's @EventListener can use a return value to publish a new event during synchronous processing under framework rules. However, async listeners cannot rely on return values to publish follow-up events with the same semantics; they must inject ApplicationEventPublisher explicitly.

A sample synchronous listener could transform PaymentRecordedEvent into PaymentAuditedEvent, causing the recorder to capture **two business event types**: PaymentRecordedEvent and PaymentAuditedEvent. In tests, do not assert raw stream count1; assert count1 for each type with the matching paymentId.

**Avoid infinite loops:** a listener receiving type A and publishing A again without a stop condition can cause recursion/stack overflow. Type-specific event contracts help tests avoid accidentally picking up unrelated events.

If a listener emits events via an async executor, tracking follow-up events with the test-scoped recorder may be unreliable due to thread boundaries. Assert a durable side effect or use a test-controlled event collector with explicit synchronization.

## 20. Common Pitfalls and How to Fix Them

| Symptom | Likely Cause | Resolution |
| --- | --- | --- |
| Cannot inject ApplicationEvents | Missing @RecordApplicationEvents/SpringExtension or default listeners replaced | Annotate test class, keep TestContext listeners |
| ApplicationEvents unavailable in test constructor | Test-method scope not yet active | Use @Test/@BeforeEach parameter or @Autowired field |
| stream(PaymentRecordedEvent.class) returns 0 | Mocked publisher, wrong ApplicationContext, different thread, action didn't publish | Check context/thread/real publisher |
| stream() returns PayloadApplicationEvent instead of record | POJO is wrapped | Use typed stream or getPayload() |
| Whole stream count is greater than 1 | Framework/test lifecycle events present | Filter by type/paymentId, clear before action |
| After events.clear(), audit still has the record | clear only empties the recorder | Verify side effect separately |
| @TransactionalEventListener does not run | Test rolled back or published without a transaction | Test with real commit, check fallback policy |
| Event recorded but email not sent | Async or after-commit listener | Await downstream completion/commit; do not treat publish as delivery |
| MockMvc sees event but RANDOM_PORT recorder misses it | Server thread is outside recorder scope | Assert state/queue via HTTP integration |
| @Async listener fails but publishEvent does not throw | Async exception does not propagate | AsyncUncaughtExceptionHandler/completion monitoring |
| Raw event ordering test is flaky | Concurrent publishers/listeners | Filter by identity, test ordering at the right layer |
| Parallel PER_CLASS tests fail or are unreliable | @RecordApplicationEvents per-method ThreadLocal scope | Use PER_METHOD/SAME_THREAD or disable parallel |
| @DirtiesContext added to “clear the recorder” | Confusing context cache with test recorder | Use ApplicationEvents.clear() and unique IDs |
| Custom @TestExecutionListeners drops defaults | Replaced instead of merged | Use MERGE_WITH_DEFAULTS |
| Test expects startup event but misses it | Recorder starts with test method lifecycle | Test startup events via dedicated listener/instrumentation |
| Assert count1 then claim Kafka delivered | Spring event is not a broker | Broker integration |
| Assert event count1 then claim DB committed | Publication happens before commit/rollback | Transaction integration |
| Listener projection uses static mutable list across tests | State leakage/test order dependency | Unique IDs, fresh fixtures, or scoped cleanup |
| ApplicationEvents called outside test lifecycle | Recorder no longer active | Use only within test/lifecycle methods |
| Event contains secrets leaking into logs | Unredacted payload | Use appropriate IDs/metadata only |
| Unit test mocks publisher and claims listener wiring works | Mock bypasses Spring multicaster | Add @RecordApplicationEvents context test |

## 21. Running Tests and Expected Results

With JDK 17 and a compatible Gradle Wrapper:

~~~bash
./gradlew clean test
./gradlew test --tests com.example.eventqa.PaymentServiceUnitTest
./gradlew test --tests com.example.eventqa.PaymentEventsIntegrationTest
./gradlew test --tests com.example.eventqa.PaymentEventsIntegrationTest.recordsSingleEventWithExactPayload
~~~

On Windows, use **gradlew.bat** with the corresponding arguments. The main app can start without a server or database; the demo creates no payments at startup.

The following outcomes are **expectations from the assertions**, not an actual test run log:

| Test | Expected Observable Result |
| --- | --- |
| validPaymentPublishesExactPayload | Captor: pay-101, amountMinor=2500 |
| invalidInputPublishesNothing | IllegalArgumentException, publisher zero interactions |
| synchronousPublisherFailurePropagates | Original exception not swallowed |
| recordsSingleEventWithExactPayload | 1 PaymentRecordedEvent for UUID, audit projection holds amount=4000 |
| invalidCommandProducesNoPaymentEvent | 0 PaymentRecordedEvent |
| streamByPayloadTypeUnwrapsPojoEvent | Typed stream 1 record; raw stream has 1 matching PayloadApplicationEvent |
| recorderClearDoesNotUndoListenerSideEffect | Recorder count=0 after clear; audit still holds payment |
| twoPublicationsAppearAsTwoOccurrences | 2 recorded events with same ID |
| typedStreamCanFilterDifferentBusinessIds | Second event filtered out, amount=2000 |

### What to Check If a Test Fails

- **UnsatisfiedDependencyException when injecting ApplicationEvents**: does the test have @RecordApplicationEvents and the default TestContext listener? Did you try injecting into the constructor?
- **Recorded count=0 while unit captor passes**: are you using the real publisher in the Spring context, or did @MockitoBean replace it? Was the event published from the test thread?
- **Payload class cast fails**: the raw stream contains ApplicationEvent wrappers; use stream(PayloadType.class) or unwrap.
- **Listener projection does not update immediately**: does the listener have @Async/custom multicaster or is it transaction-bound? Is it running inside a rolled-back transaction?
- **Intermittent pass/fail when tests run in parallel**: check JUnit lifecycle mode, static state, context cache, executor threads, and test identity.
- **Event count inflated by setup/framework events**: clear right before the action and filter by type/ID; do not naively assert total raw stream length.

## 22. QA Checklist Before Finalizing

- Does the test class have **@RecordApplicationEvents** and SpringExtension/@SpringBootTest?
- Is **ApplicationEvents** imported from the right package org.springframework.test.context.event?
- Does the test receive ApplicationEvents via method parameter/field rather than constructor injection?
- Do you distinguish **stream()** from **stream(MyPayload.class)**?
- For POJO/record events, do you account for the **PayloadApplicationEvent** wrapper?
- Do assertions check **payload fields** and correlation IDs, not just count?
- Does invalid input have a test proving **no event is emitted**?
- Is events.clear() placed **before the action** when a clean baseline is needed?
- Are you avoiding clear() as a way to roll back or wipe listener state?
- Are Spring TestContext lifecycle events distinguished from business events?
- Are test records per-method and independent of previous method data?
- Have you avoided @TestInstance(PER_CLASS) running in parallel with @RecordApplicationEvents?
- Have you avoided counting the global raw stream in shared-context parallel tests?
- Is synchronous vs. async listener behavior identified before asserting side effects?
- For @Async/custom multicasters, do you have bounded waits and thread-safe observable state?
- For @TransactionalEventListener, have you verified **real commit** and transaction phase?
- Are @Transactional rollback tests kept from being mistaken for AFTER_COMMIT listener success?
- For HTTP RANDOM_PORT, are you avoiding assuming the recorder sees events from server threads?
- Is it clear that event publication **does not** prove Kafka delivery, durable audit, or exactly-once?
- Are Spring events separated from Micrometer Observation/metrics/tracing?
- If using custom @TestExecutionListeners, is ApplicationEventsTestExecutionListener preserved?
- Is context wiring tested separately from pure Mockito publisher unit tests?
- Are test payloads free of sensitive info, credentials, or real customer data?
- Do source files and imports match Spring Boot 3.4/Spring Framework 6.2?
- Are you avoiding fabricating BUILD SUCCESSFUL, offsets, or logs from unexecuted runs?

## 23. Self-Check Questions

**1.** Where is @RecordApplicationEvents placed? **On the test class** or as a meta-annotation, not on a business service.

**2.** What is ApplicationEvents used for? **Querying Spring application events recorded during a test method lifecycle**.

**3.** Does ApplicationEvents have its own count() method? **No**; use events.stream(Type.class).count().

**4.** Does events.clear() delete data from a listener projection? **No**, it only clears the recorder buffer.

**5.** Can a Java record that does not extend ApplicationEvent be published? **Yes**, via publishEvent(Object).

**6.** Why does the raw stream contain PayloadApplicationEvent? Spring wraps POJO payloads to dispatch them as ApplicationEvent instances.

**7.** How do you retrieve PaymentRecordedEvent directly? **events.stream(PaymentRecordedEvent.class)**.

**8.** Why does a Mockito unit test not prove listener wiring? Because the publisher is mocked, so the Spring multicaster never runs.

**9.** Why does a context test need @RecordApplicationEvents? So TestContext creates a recorder scoped to the test.

**10.** Should ApplicationEvents be injected into a test constructor? **No**, prefer @Test/@BeforeEach/@AfterEach method parameters.

**11.** Which thread does @EventListener run on by default? Typically the **publishing thread** with the default synchronous multicaster.

**12.** Does an @Async listener make the publisher wait until completion? **Not by default**.

**13.** Should you use Thread.sleep to wait for an @Async listener? **No**, use observable completion and bounded waits.

**14.** What is the default phase of @TransactionalEventListener? **AFTER_COMMIT**.

**15.** If an event is recorded but the transaction rolls back, does the AFTER_COMMIT listener run? **No**, even though the recorder may contain the event.

**16.** When published outside a transaction, does a transaction-bound listener run by default? **No**, unless fallbackExecution=true.

**17.** Why do @Transactional tests often cause misunderstandings with AFTER_COMMIT? Because tests normally roll back after the method instead of committing.

**18.** Does a Spring event automatically go to a Kafka broker? **No**, it is an in-process mechanism.

**19.** Does @RecordApplicationEvents automatically generate metrics/traces? **No**, use dedicated Micrometer/Observation tools.

**20.** Why shouldn't you assert events.stream().count()==1? Framework events and other event types are also present.

**21.** Will an event emitted on a RANDOM_PORT server thread always be captured by the recorder? **Not guaranteed**, due to thread/lifecycle scope.

**22.** Is @TestInstance(PER_CLASS) with parallel @RecordApplicationEvents safe? **Not recommended / this combination is unsupported**; use PER_METHOD/SAME_THREAD.

**23.** When custom @TestExecutionListeners drops the default recorder listener, how do you fix it? **MERGE_WITH_DEFAULTS** or register the required listener explicitly.

**24.** Does recording two events with the same paymentId automatically mean duplicates are a bug? **No**, you must check the business idempotency contract; the recorder merely reflects publication occurrences.

**25.** When you need to prove an after-commit notification was sent, what should you assert? **Real commit and the listener's downstream side effect**, not just the ApplicationEvents stream.

**Conclusion:** **@RecordApplicationEvents + ApplicationEvents** is the Spring TestContext tool dedicated to observing and asserting application events published within a test method. Use the typed stream to count and filter the right domain event payloads; use clear() to isolate actions; combine Mockito unit tests and Spring context tests to separate business decisions from event dispatch; and verify listener side effects separately when needed. Most importantly, never equate **event recorded** with **async listener finished**, **transaction committed**, **broker received message**, or **complete observability**.

## Official References

- Spring Framework 6.2 — Application Events in TestContext: https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/application-events.html
- Spring Framework 6.2 — @RecordApplicationEvents: https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-recordapplicationevents.html
- Spring Framework 6.2 — ApplicationEvents Javadoc (stream/stream(Class)/clear): https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/test/context/event/ApplicationEvents.html
- Spring Framework 6.2 — RecordApplicationEvents Javadoc: https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/test/context/event/RecordApplicationEvents.html
- Spring Framework 6.2 — ApplicationContext events and @EventListener: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework 6.2 — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Spring Framework 6.2 — Observability support: https://docs.spring.io/spring-framework/reference/6.2/integration/observability.html
- Spring Boot 3.4 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.4/reference/testing/spring-boot-applications.html
