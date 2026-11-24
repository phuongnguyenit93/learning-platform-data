# QueueBrowser: Inspecting Messages Without Consuming in Spring JMS

## 1. Problem and objectives

When operating a system backed by a Queue, you sometimes need to **inspect messages currently sitting in the queue** to verify their format, properties, correlation ID, or processing status. However, if you call `MessageConsumer.receive()` just to "peek," you can **remove the message from the queue**, trigger acknowledgement/transactions, compete with real workers, and alter system state.

Jakarta Messaging (JMS) provides **`jakarta.jms.QueueBrowser`** to **browse/peek messages on a Queue without consuming them**. Spring JMS wraps this capability with `JmsTemplate.browse(...)` and `browseSelected(...)`.

After this lesson, you will be able to:

1. Distinguish **browse** from **receive/consume** and understand the impact on acknowledgement.
2. Create a `QueueBrowser` via `Session.createBrowser` or `JMSContext.createBrowser`.
3. Iterate `java.util.Enumeration` to read headers, properties, and bodies when needed.
4. Use `JmsTemplate.browse`/`browseSelected` with `BrowserCallback<T>`.
5. Apply JMS message selectors to inspect only matching messages.
6. Understand why **browsing is not a consistent snapshot**, does not guarantee exact counts or freshness, and does not show messages before their `JMSDeliveryTime`.
7. Write and run a **Java 17+, Spring Boot 3.5.x, embedded ActiveMQ Artemis** demo proving browse does not lose messages.
8. Know how to use browsing safely in production: bounding resources, protecting data, access control, and choosing metrics for backlog measurement.

This lesson belongs to **Synchronous Receiving**. Although a browser helps observe a queue, it is **not a consumer receiving for processing**, nor a mechanism for replaying events in a Topic.

## 2. What is QueueBrowser?

Per Jakarta Messaging, a `QueueBrowser` lets an application **inspect messages in a Queue without removing them from the Queue**. Core API:

~~~java
// Abbreviated signature for learning, not an interface to define yourself.
jakarta.jms.QueueBrowser browser =
        session.createBrowser(queue);
java.util.Enumeration<?> messages = browser.getEnumeration();
~~~

`QueueBrowser` is an **AutoCloseable resource**. Key methods:

| API | Role |
| --- | --- |
| `Session.createBrowser(Queue)` | Creates a browser without a selector. |
| `Session.createBrowser(Queue, String)` | Creates a browser seeing only messages matching the selector. |
| `JMSContext.createBrowser(Queue)` | Equivalent in the simplified JMS API. |
| `JMSContext.createBrowser(Queue, String)` | Browser with a selector using `JMSContext`. |
| `QueueBrowser.getEnumeration()` | Obtains an `Enumeration` to iterate browsable messages. |
| `QueueBrowser.getQueue()` | Returns the queue the browser is attached to. |
| `QueueBrowser.getMessageSelector()` | Returns the selector expression (or null if none). |
| `QueueBrowser.close()` | Closes the browser and releases provider resources. |

`getEnumeration()` is not an endless stream. It provides a way to **iterate matching messages present during the browse pass**, according to provider semantics. Once finished, if you want to check again, open/iterate anew rather than keeping a browser open long-term like a listener.

### 2.1. Comparing browse, receive, and monitor

| Operation | Reads message content? | Consumes message? | Suitable for business processing? |
| --- | --- | --- | --- |
| `QueueBrowser.getEnumeration()` | Yes, per permissions and browsable messages. | **No** | No; its primary purpose is observation. |
| `MessageConsumer.receive(timeout)` | Yes. | **Yes**, per session ack/transaction. | Yes. |
| `JmsTemplate.receive(queue)` | Yes, returns raw `jakarta.jms.Message`. | **Yes** | Yes, in synchronous receive flows. |
| `JmsTemplate.receiveAndConvert(queue)` | Yes, returns converted body. | **Yes** | Yes, when converted data is needed. |
| `@JmsListener` | Yes, via listener container. | **Yes** per container configuration. | Yes, for asynchronous processing flows. |
| Queue metrics/management API | Typically statistics (count, depth, age, etc.). | No | Used for observability, not reading individual messages. |

**Browse ≠ receive without ACK**. Even if a consumer in `CLIENT_ACKNOWLEDGE` has not yet called `acknowledge()`, the message has already been **delivered/received** and may be in-flight. A browser **does not perform that consuming receive**. Therefore, do not use `receiveNoWait()` as a "safe" substitute for peeking.

## 3. Operational model

Suppose queue `orders.pending` holds three messages:

~~~text
orders.pending:
    M1: orderId=O-101, type=Created
    M2: orderId=O-102, type=Cancelled
    M3: orderId=O-103, type=Created
~~~

Browser traversing the queue:

~~~mermaid
flowchart TD
    Q[("orders.pending: M1, M2, M3")]
    Q --> B["QueueBrowser.getEnumeration()"]
    B --> D["Application reads headers/properties/body"]
    D --> X["No acknowledge, message not removed"]
    Q --> C["MessageConsumer.receive()"]
    C --> A["Process + ack/commit"]
    A --> R["Message processed per receive semantics"]
~~~

When **no other producer/consumer is concurrently modifying the queue** and no TTL/delay/selector blocks visibility, the browser can list M1–M3. After browsing, a real consumer **can still receive M1, M2, and M3**.

However, this is **not a transactional point-in-time snapshot of the entire queue**. If while browsing another worker consumes M2, a producer adds M4, or M3 expires, whether M2/M3/M4 appear in the enumeration **depends on the JMS provider**. Never treat a browse result as absolute proof that the queue held exactly N messages at a single instant.

### 3.1. What does "non-consuming" mean?

- The browser does not delete/ack messages merely because it read them.
- The browser does not turn observation into **business processing**.
- It does not replace a consumer in a transaction.
- Accessing properties/bodies for debugging is still **reading data** and is subject to security policies.
- Closing the browser frees resources for the browse pass; **no commit/rollback of consumed messages is created by the browser**.

If a message disappears by the next browse pass, **do not** assume the browser deleted it. Another worker may have consumed/committed it, the message may have expired, a broker policy may have moved it to an expiry queue, or a selector/delivery time excluded it from the browsable set.

## 4. Classic API: Session.createBrowser

The snippet below uses a configured `jakarta.jms.ConnectionFactory`, creates a `QueueBrowser`, and iterates messages.

~~~java
// Fragment: factory is a jakarta.jms.ConnectionFactory connected to a real broker.
try (jakarta.jms.Connection connection = factory.createConnection();
     jakarta.jms.Session session = connection.createSession(
             false, jakarta.jms.Session.AUTO_ACKNOWLEDGE)) {

    jakarta.jms.Queue queue = session.createQueue("orders.pending");
    connection.start();

    try (jakarta.jms.QueueBrowser browser =
                 session.createBrowser(queue)) {

        java.util.Enumeration<?> enumeration =
                browser.getEnumeration();

        while (enumeration.hasMoreElements()) {
            Object candidate = enumeration.nextElement();

            if (candidate instanceof jakarta.jms.Message message) {
                System.out.println(
                        "ID=" + message.getJMSMessageID()
                                + ", correlation="
                                + message.getJMSCorrelationID());
            }
        }
    }
}
~~~

**Line-by-line explanation:**

1. `Session.createQueue("orders.pending")` creates a **named Queue reference object**, not an admin request to create a physical queue. The broker must already have the destination or an auto-provisioning policy.
2. `Session.createBrowser(queue)` creates a browser for a **Queue**, not a Topic.
3. `connection.start()` in the example readies the connection for delivery; a browser is **not** a consumer calling `receive()`.
4. `getEnumeration()` returns an iterator-like enumeration over messages; `hasMoreElements()` and `nextElement()` belong to `java.util.Enumeration`, **not** `Iterator`.
5. Safely cast and call JMS getters.
6. `try-with-resources` closes the browser, session, and connection, preventing provider resource leaks.

This is a **fragment**, without a `main` method or `factory` configuration. It can throw `JMSException` on missing permissions, invalid destination, or broker errors. Do not fetch every message's body by default: payloads can be large or sensitive.

### 4.1. Browser with a message selector

~~~java
// Fragment: jakarta.jms.Session session and Queue queue already available.
try (jakarta.jms.QueueBrowser browser = session.createBrowser(
        queue, "eventType = 'OrderCreated' AND schemaVersion >= 2")) {

    java.util.Enumeration<?> e = browser.getEnumeration();

    while (e.hasMoreElements()) {
        jakarta.jms.Message m =
                (jakarta.jms.Message) e.nextElement();

        System.out.println(m.getJMSMessageID());
    }
}
~~~

Only messages whose JMS properties `eventType` and `schemaVersion` match the condition are returned by the browser. `schemaVersion` in this example should be set by the producer via `setIntProperty(..., 2)`; if sent as `String "2"`, numeric comparison may fail to match.

**Selectors evaluate headers/properties**, and do not parse JSON bodies. The JMS SQL-92 subset is not arbitrary SQL querying. `eventType` is case-sensitive; string literals use single quotes `'...'`.

### 4.2. Avoid mutating messages while browsing

A browser may return a `Message` whose headers/body can be read, yet **never modify that Message expecting to update the physical message in the queue**. Do not write:

~~~java
// ANTI-PATTERN: do not treat this as a way to update a message already in the queue.
m.setStringProperty("status", "fixed");
m.acknowledge(); // Browser is not a consume + ack method.
~~~

There is no portable JMS API to "browse and edit/delete that exact message in the queue." To handle bad messages, use a consumer with transactions/acknowledgement, or an authorized admin tool/broker API under safe operational procedures. Browsing **must not become ad-hoc read-modify-write**.

## 5. Simplified API: JMSContext.createBrowser

`JMSContext` (JMS 2.0+/Jakarta Messaging) provides methods to create a QueueBrowser directly:

~~~java
// Fragment: factory is a configured jakarta.jms.ConnectionFactory.
try (jakarta.jms.JMSContext context = factory.createContext()) {
    jakarta.jms.Queue queue = context.createQueue("orders.pending");

    try (jakarta.jms.QueueBrowser browser =
                 context.createBrowser(queue)) {

        java.util.Enumeration<?> enumeration =
                browser.getEnumeration();

        while (enumeration.hasMoreElements()) {
            jakarta.jms.Message message =
                    (jakarta.jms.Message) enumeration.nextElement();
            System.out.println(message.getJMSMessageID());
        }
    }
}
~~~

With a filter:

~~~java
// Fragment in the same JMSContext with Queue queue.
try (jakarta.jms.QueueBrowser browser = context.createBrowser(
        queue, "eventType = 'OrderCreated'")) {
    java.util.Enumeration<?> e = browser.getEnumeration();
    while (e.hasMoreElements()) {
        jakarta.jms.Message m =
                (jakarta.jms.Message) e.nextElement();
        System.out.println(m.getJMSType());
    }
}
~~~

`JMSContext` closes the associated session/connection upon exiting per API rules. Still close `QueueBrowser` explicitly when done so resources are released promptly.

### 5.1. Do not confuse QueueBrowser with JMSConsumer

`context.createConsumer(queue)` produces a `JMSConsumer`, which uses `receive()`, `receiveNoWait()`, or `setMessageListener()`. **That is a real consumer**, which acknowledges and alters remaining messages.

`context.createBrowser(queue)` produces a **QueueBrowser**, which uses `getEnumeration()` and **does not consume**. Both can inspect messages, yet their purposes and effects differ.

## 6. Spring JMS: JmsTemplate.browse and BrowserCallback

When an application already uses Spring, you rarely need to manually open `Connection`, `Session`, or `QueueBrowser` for a short inspection task. `org.springframework.jms.core.JmsTemplate` provides these overloads:

~~~java
// Summarized API signatures:
<T> T browse(
        String queueName,
        org.springframework.jms.core.BrowserCallback<T> action);

<T> T browseSelected(
        String queueName,
        String messageSelector,
        org.springframework.jms.core.BrowserCallback<T> action);
~~~

Other overloads accept a `jakarta.jms.Queue` object or use the default queue. `JmsTemplate` prepares the session/browser, invokes the callback, **closes resources at the right lifecycle point**, and translates checked `JMSException` into unchecked `JmsException`.

### 6.1. BrowserCallback<T> contract

~~~java
// Reference API signature; do not define this interface in your application.
T doInJms(
        jakarta.jms.Session session,
        jakarta.jms.QueueBrowser browser)
        throws jakarta.jms.JMSException;
~~~

`BrowserCallback<T>` is a functional interface. The callback receives **two parameters** `(session, browser)`, not `Message` directly; you call `browser.getEnumeration()` yourself.

**Lifecycle rule:** iterate and extract data **inside the callback**, returning a value independent of the session/browser (e.g., a List of IDs or a small summary Map). Never return `QueueBrowser`, `Enumeration`, or an object tied to closed resources.

### 6.2. Browsing into a list of IDs

~~~java
// Fragment in a service that already has JmsTemplate jmsTemplate.
java.util.List<String> ids = jmsTemplate.browse(
        "orders.pending",
        (session, browser) -> {
            java.util.List<String> result =
                    new java.util.ArrayList<>();

            java.util.Enumeration<?> e =
                    browser.getEnumeration();

            while (e.hasMoreElements()) {
                jakarta.jms.Message m =
                        (jakarta.jms.Message) e.nextElement();
                result.add(m.getJMSMessageID());
            }
            return result;
        });

System.out.println("IDs seen: " + ids.size());
~~~

This is a fragment inside a Spring service with an existing Queue. **The list is not necessarily the entire queue at a single instant**; it only reflects messages the browser observed during its pass. Cap the element count and avoid logging sensitive data on large queues.

### 6.3. BrowseSelected by property

~~~java
// Fragment in a Spring bean that already has JmsTemplate jmsTemplate.
java.util.List<String> ids = jmsTemplate.browseSelected(
        "orders.pending",
        "eventType = 'OrderCreated'",
        (session, browser) -> {
            java.util.List<String> result =
                    new java.util.ArrayList<>();

            java.util.Enumeration<?> e =
                    browser.getEnumeration();

            while (e.hasMoreElements()) {
                jakarta.jms.Message m =
                        (jakarta.jms.Message) e.nextElement();
                result.add(m.getStringProperty("eventId"));
            }
            return result;
        });
~~~

`browseSelected` attaches the selector to **`QueueBrowser`**, consuming neither filtered nor unfiltered messages. Contrast this with `JmsTemplate.receiveSelected`: **`receiveSelected` is still a receive**, which removes messages and participates in acknowledgement/transactions.

### 6.4. Do not use receiveAndConvert to debug without knowing its impact

~~~java
// This CONSUMES, it is NOT a "peek":
Object payload = jmsTemplate.receiveAndConvert("orders.pending");
~~~

Some developers assume merely reading a Java object leaves the Queue untouched. Yet `receiveAndConvert` calls receive before converting to a Java object; the message has already been delivered to a consumer. Even if the application subsequently throws an error, ack/rollback depends on transaction/session configuration; **never use this just to inspect**.

## 7. Complete demo: Java 17 + Spring Boot + ActiveMQ Artemis

The following demo proves three things:

1. `JmsTemplate.browse` sees the sent messages.
2. `JmsTemplate.browseSelected` lists only messages with matching properties.
3. After **two browse passes**, `JmsTemplate.receive` still retrieves **all** original messages, meaning browse is **non-consuming**.

**Prerequisites:** JDK 17+, Maven 3.6.3+, and Maven Central access for dependencies. Uses **Spring Boot 3.5.7** with an **embedded Artemis broker** so no external broker startup is needed. The demo queue is accessed by a single `ApplicationRunner`, avoiding concurrent consumers in the lesson.

Directory structure:

~~~text
jms-browser-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/jmsbrowser/
    │   └── JmsBrowserDemoApplication.java
    └── resources/
        └── application.properties
~~~

### 7.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>jms-browser-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
        </dependency>

        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>artemis-jakarta-server</artifactId>
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

The starter adds Spring JMS and the Artemis client, while `artemis-jakarta-server` enables Boot to start an embedded broker. Dependency versions are managed by the Boot parent.

### 7.2. application.properties

~~~properties
spring.artemis.mode=embedded
spring.artemis.embedded.queues=demo.browser
spring.artemis.embedded.persistent=false
spring.jms.pub-sub-domain=false
spring.jms.template.receive-timeout=5s
spring.main.banner-mode=off
~~~

- `demo.browser` is the demo queue created at broker startup.
- `persistent=false` is for demos only; it does not simulate message recovery across broker restarts.
- `receive-timeout=5s` protects receive calls from waiting indefinitely.
- `pub-sub-domain=false` makes default destination names resolve as Queues.

### 7.3. JmsBrowserDemoApplication.java

Create `src/main/java/com/example/jmsbrowser/JmsBrowserDemoApplication.java`:

~~~java
package com.example.jmsbrowser;

import java.util.ArrayList;
import java.util.Enumeration;
import java.util.List;
import java.util.TreeSet;

import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.QueueBrowser;
import jakarta.jms.TextMessage;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class JmsBrowserDemoApplication {

    private static final String QUEUE = "demo.browser";

    public static void main(String[] args) {
        SpringApplication.run(JmsBrowserDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner demo(JmsTemplate template) {
        return args -> {
            template.convertAndSend(QUEUE, "ORDER-101", message -> {
                message.setStringProperty("eventId", "E-101");
                message.setStringProperty("eventType", "OrderCreated");
                return message;
            });
            template.convertAndSend(QUEUE, "ORDER-102", message -> {
                message.setStringProperty("eventId", "E-102");
                message.setStringProperty("eventType", "OrderCancelled");
                return message;
            });
            template.convertAndSend(QUEUE, "ORDER-103", message -> {
                message.setStringProperty("eventId", "E-103");
                message.setStringProperty("eventType", "OrderCreated");
                return message;
            });

            List<String> allIds = template.browse(
                    QUEUE, (session, browser) -> collectIds(browser));

            List<String> createdIds = template.browseSelected(
                    QUEUE,
                    "eventType = 'OrderCreated'",
                    (session, browser) -> collectIds(browser));

            List<String> receivedBodies = new ArrayList<>();
            for (int i = 0; i < 3; i++) {
                Message message = template.receive(QUEUE);

                if (!(message instanceof TextMessage text)) {
                    throw new IllegalStateException(
                            "Did not receive TextMessage in time");
                }
                receivedBodies.add(text.getText());
            }

            int remaining = template.browse(
                    QUEUE, (session, browser) -> collectIds(browser).size());

            System.out.println("BROWSED_IDS="
                    + new TreeSet<>(allIds));
            System.out.println("SELECTED_IDS="
                    + new TreeSet<>(createdIds));
            System.out.println("RECEIVED_BODIES="
                    + new TreeSet<>(receivedBodies));
            System.out.println("AFTER_CONSUME_COUNT=" + remaining);
            System.out.println("BROWSE_PRESERVED_ALL="
                    + (allIds.size() == 3 && receivedBodies.size() == 3));
        };
    }

    private static List<String> collectIds(QueueBrowser browser)
            throws JMSException {

        List<String> ids = new ArrayList<>();
        Enumeration<?> enumeration = browser.getEnumeration();

        while (enumeration.hasMoreElements()) {
            Object element = enumeration.nextElement();
            if (!(element instanceof Message message)) {
                throw new IllegalStateException(
                        "Browser returned a non-JMS Message");
            }
            ids.add(message.getStringProperty("eventId"));
        }
        return ids;
    }
}
~~~

**Explanation:**

1. `ApplicationRunner` runs after Spring Boot initializes the JMS connection factory and embedded broker.
2. Three `TextMessage`s are sent with `eventId` and `eventType` as JMS properties.
3. `template.browse(QUEUE,...)` invokes the callback, iterates the enumeration, and returns a `List<String>` of IDs. The list is independent of the browser once the callback finishes.
4. `template.browseSelected` uses a selector to find the two `OrderCreated` messages; the `OrderCancelled` message is not deleted.
5. **After browsing**, `template.receive(QUEUE)` is called three times. With no other consumers, TTL expiry, or delay, all three messages are still receivable.
6. The final browse checks the demo queue after all three messages have been received. Using the template's default session/ack, completing the receives consumes the messages per JMS semantics.
7. Printing `TreeSet` displays a stable sorted set without **relying on enumeration order**. Do not interpret `TreeSet` order as the broker's actual ordering.

Run inside `jms-browser-demo`:

~~~bash
mvn spring-boot:run
~~~

Program output lines, ignoring Maven/Spring/Artemis logs:

~~~text
BROWSED_IDS=[E-101, E-102, E-103]
SELECTED_IDS=[E-101, E-103]
RECEIVED_BODIES=[ORDER-101, ORDER-102, ORDER-103]
AFTER_CONSUME_COUNT=0
BROWSE_PRESERVED_ALL=true
~~~

**This is expected output** on a fresh embedded broker with no concurrent consumers, non-expiring messages, and all three sends succeeding. If tested against a shared broker with preexisting data in the queue, results may differ. This lesson **does not claim to have compiled/executed Maven**; in practice, run a similar integration test.

### 7.4. Test variations

- Comment out the entire `receive` step and browse again: all three messages should remain.
- Keep only `browseSelected` with `eventType='OrderCreated'`: two messages match, and the third remains in the Queue.
- Change selector to `eventType='OrderShipped'`: matches zero messages; **deletes no messages**.
- Run a real consumer concurrently: the count seen by the browser may change; do not assert a fixed snapshot.
- Set a delivery delay on the producer and browse immediately: messages **must not appear before `JMSDeliveryTime`** per specification.
- Use a short message TTL: messages may expire mid-browse; do not treat one enumeration as a fixed sample.

## 8. Important: QueueBrowser does not guarantee a snapshot

This is a standard Jakarta Messaging rule: **an Enumeration is not required to be a static snapshot of the Queue**. While you iterate, new messages may arrive, old messages may expire, and other consumers may consume them.

Example timeline:

~~~text
12:00:00.000  Queue has M1, M2, M3.
12:00:00.010  Browser begins enumerating.
12:00:00.015  Consumer A receives M2.
12:00:00.020  Producer B sends M4.
12:00:00.025  M3 expires via TTL.
12:00:00.030  Browser finishes.
~~~

Depending on the provider, the browser may see M1/M2/M3 or a different subset, and may or may not see M4. **Do not treat this result as a consistent read transaction**. A `QueueBrowser` offers no "lock the whole Queue" or `SELECT ... FOR UPDATE` primitive.

### 8.1. Implications for message counts

A seemingly accurate count:

~~~java
// Fragment: JmsTemplate template already available.
int count = template.browse("orders.pending", (session, browser) -> {
    int n = 0;
    java.util.Enumeration<?> e = browser.getEnumeration();
    while (e.hasMoreElements()) {
        e.nextElement();
        n++;
    }
    return n;
});
~~~

`count` is **the number of messages returned by the enumeration during that browse pass**, not necessarily the **exact queue depth at a single instant**. On a large Queue, iterating the entire queue just to count also causes unnecessary load.

**Right tool for the job:** to measure backlog, queue depth, messages added/acked, expiries, and consumer count, prefer the provider's **broker management metrics / JMX / Prometheus exporter**. Document the semantics of each metric: ready vs. delivering/in-flight vs. scheduled vs. expired may be defined differently across brokers. Do not equate `browseCount` with all metrics.

### 8.2. Implications for ordering

The Javadoc states the enumeration is in the order messages **would be received**, yet that is not an absolute ordering guarantee when:

- Concurrent producers/consumers exist.
- Messages differ in `JMSPriority`, delivery time, selector, transactions, or expiry.
- The broker applies message grouping or custom dispatch policies.

When business order matters, use consumers, business keys/idempotency, and proper sequencing design; **never use browse order to drive transactional decisions**.

### 8.3. Bounding results and lifecycle

When a Queue holds millions of messages, `getEnumeration()` can strain broker/network/JVM resources. A loop can stop after N items:

~~~java
// Fragment inside JmsTemplate.browse callback:
java.util.List<String> ids = new java.util.ArrayList<>();
java.util.Enumeration<?> e = browser.getEnumeration();

while (e.hasMoreElements() && ids.size() < 100) {
    jakarta.jms.Message m = (jakarta.jms.Message) e.nextElement();
    ids.add(m.getJMSMessageID());
}
return ids;
~~~

**Capping at 100 only limits how many elements the app stores/reads in the callback**; it does not guarantee the broker only produces or transfers 100 elements, as providers may prefetch/buffer ahead. JMS `QueueBrowser` defines no stable paging/offset protocol. If you need to paginate a large Queue, check the broker's own management API with pagination; still remember Queue contents can change between pages.

Do not keep a browser open for minutes to "monitor in real time." Use metrics for dashboards; for inspecting a few messages, browse briefly and close resources early.

## 9. Delivery delay and JMSDeliveryTime

An easily overlooked rule: **JMS requires QueueBrowser not to return a message before its `JMSDeliveryTime` has arrived**.

Suppose:

~~~text
10:00:00 Producer sends M1, delivery delay 5 minutes
M1's JMSDeliveryTime ≈ 10:05:00

10:02:00 Browser inspects Queue
          -> must not return M1 before 10:05

10:05:00+ Browser may now see M1,
           if M1 has not been consumed, expired, or otherwise handled.
~~~

This matters when the broker supports **scheduled/delayed delivery**. Broker queue metrics may report a scheduled message present, while `QueueBrowser` does not see it until it becomes eligible. **Do not conclude a message is lost** just because browse does not return a message still inside its delay window.

Distinguish:

- `JMSDeliveryTime`: **earliest time delivery is allowed**.
- `JMSExpiration`: **expiration timestamp** per TTL (0 means no JMS TTL expiration).
- `JMSTimestamp`: time recorded by the provider on send (may be 0 if timestamps are disabled).
- `receivedAt` measured by the app: time the consumer actually receives the message.

`QueueBrowser` does not promise to capture scheduled messages the broker is not yet allowed to deliver. To inspect scheduled messages at the broker level, use a **dedicated management API** instead of expecting `QueueBrowser` to act outside the specification.

## 10. Browsing with selectors: mechanics and limits

Both `Session.createBrowser(queue, selector)` and `JmsTemplate.browseSelected` use **JMS message selectors**.

Common cases:

| Selector | Meaning |
| --- | --- |
| `eventType = 'OrderCreated'` | Selects messages with `eventType` matching the exact String value. |
| `schemaVersion >= 2` | Selects messages with a matching numeric property. |
| `JMSCorrelationID = 'corr-123'` | Selects messages with the given correlation ID. |
| `eventType = 'OrderCreated' AND schemaVersion >= 2` | Both conditions simultaneously. |
| `JMSPriority >= 7` | Selects by JMS priority header, if applied by provider/selector. |
| `tenantId IS NOT NULL` | Selects messages whose property is non-null per selector rules. |

In JMS, selectors evaluate data types and logical expressions roughly as a SQL-92 subset. Arbitrary deep reading into JSON bodies is not supported; if you must filter by `orderId` inside JSON, consider adding a validated property at the producer, using a specialized broker/search tool, or reading via consumers when processing is truly required.

**Do not use selectors to replace authorization.** An account permitted to browse a queue can access whatever messages the browser/broker permits, whereas a selector is a client-side logical filter. Multi-tenant data protection requires ACLs, queue segmentation, and independent identity controls.

### 10.1. When the selector does not match

The browser can return an empty enumeration even while the queue holds many messages:

~~~text
Queue: eventType = "OrderCancelled" for all messages
Selector: eventType = 'OrderCreated'
Browse result: 0
Queue still contains messages; none are deleted.
~~~

If a property is absent, expressions generally do not evaluate to true. Do not assume NULL/unknown equals an empty String. Verify the producer uses the right property setter and type: `setIntProperty` rather than `setStringProperty` for numeric versions.

## 11. QueueBrowser is not for Topics

Jakarta Messaging defines `QueueBrowser` for browsing a **Queue**. There is no equivalent standard JMS API to directly browse "an entire Topic" like a Queue.

| Destination | Behavior |
| --- | --- |
| **Queue** | Browser inspects eligible available messages **without consuming**. |
| **Topic** | Subscribers have subscriptions; published messages are normally distributed per subscription. |
| **Durable Topic subscription** | The broker can retain messages for a subscription while the consumer is offline, yet JMS **defines no standard API to browse Topics**. |
| **Broker-specific queue backing a subscription** | The provider may allow inspection via management APIs or underlying queues, but this is non-portable. |

To inspect a durable subscription, use supported broker tools/management APIs with appropriate permissions; never assume `Session.createBrowser((Queue) topic)` is valid.

In ActiveMQ Artemis, Topics are typically implemented using multicast addresses and subscription queues. That is a broker-specific model; it does not turn `QueueBrowser` into a standard JMS Topic browser.

## 12. Transactions, acknowledgement, and redelivery

To avoid confusing browsing with receive modes:

### 12.1. AUTO_ACKNOWLEDGE

A consumer using `AUTO_ACKNOWLEDGE` causes messages to be acknowledged automatically after receive or listener completion per JMS rules. `QueueBrowser` only observes and **creates no consumer ACK step**.

### 12.2. CLIENT_ACKNOWLEDGE

A consumer using `CLIENT_ACKNOWLEDGE` receives a message and can later call `message.acknowledge()`. That is still a **receive**, and the message may be unacknowledged/in-flight. A browser is not "`CLIENT_ACKNOWLEDGE` without calling ACK"; it is a **different API**.

### 12.3. Transacted sessions

With a transacted session, a consumer receives messages and calls `commit()`/`rollback()`; rollback typically makes messages eligible for redelivery. A browser **does not need a commit for browsed messages to remain processed/unprocessed**, nor should `session.rollback()` be called to "undo a browse."

Messages sent by a producer in an **uncommitted** transaction are not normally visible to other consumers or browsers yet. Only after commit can they appear, subject to delivery time and other policies. Do not rely on a browser to inspect uncommitted transactional state.

### 12.4. Does browsing increment delivery count?

`JMSXDeliveryCount` and `JMSRedelivered` apply to **message delivery to a consumer**. Browsing **is not equivalent to delivery to a consumer executing business logic**, so do not use it to trigger retries or count a processing attempt. What the provider exposes on a message **seen by a browser** may depend on message/broker state; do not treat a browse pass as evidence of receive/ack events.

To inspect actual retries, check event logs, consumer transactions, and broker redelivery/DLQ metrics. Never modify `JMSRedelivered` or `JMSXDeliveryCount` on a browsed message.

## 13. Browse permission is a data-access permission

`QueueBrowser` is a **data-reading** tool; therefore browse permission must be controlled. In **Apache ActiveMQ Artemis**, ACLs define **`send`**, **`consume`**, **`browse`**, and separate management permissions.

| Artemis permission | Role | Does it imply browse? |
| --- | --- | --- |
| `send` | Producer sends messages to an address. | Not automatically. |
| `consume` | Worker receives messages from a Queue. | Not automatically. |
| `browse` | Permits viewing messages in the corresponding Queue. | Yes, per ACL/configuration. |
| `manage`, `view`, `edit` | Administrative / management API operations. | Different permission model; do not equate with JMS QueueBrowser. |
| `create*`/`delete*` | Provisioning and deleting Queues/Addresses. | Does not imply browse. |

Example **fragment** in Artemis's `broker.xml`, which must be integrated into an existing broker configuration:

~~~xml
<security-settings>
    <security-setting match="orders.#">
        <permission type="send" roles="order-producers"/>
        <permission type="consume" roles="order-workers"/>
        <permission type="browse" roles="order-auditors"/>
    </security-setting>
</security-settings>
~~~

Key points:

- This is not a complete `broker.xml` file; user/role mappings must be configured in the security manager.
- A more specific `security-setting` can **override** permissions from a broader rule in Artemis; always verify the **effective rule**.
- Some operations that create destinations or temporary queues also require separate `create*` permissions.
- Do not grant `consume` just so operations staff can inspect messages; grant scoped `browse` instead.
- Do not grant `browse` on `#` broadly; Queues can contain customer payloads, orders, and internal tokens.

**Production caution:** anyone with browse permission can still read message contents. If a Queue carries sensitive information, consider metadata-only logging, redaction, strict permission scoping, and access auditing. Secrets must not be logged in full payloads merely for debugging.

## 14. When to use and when not to use QueueBrowser

### 14.1. When to use it

- Diagnosing which event types or `schemaVersion`s are currently sitting in a Queue.
- Quickly checking a few `JMSMessageID`, `JMSCorrelationID`, `eventId`, `eventType`, or producer-set properties.
- Inspecting a message **non-destructively** before deciding on an authorized operational tool.
- Testing that messages remain in a Queue after browsing.
- Sampling a small number of messages matching a selector to investigate migration/format issues.

### 14.2. When not to use it

- **Business message processing**: requires a consumer and ack/transactions.
- **Accurate/reliable backlog counting** on large Queues: use broker metrics.
- **Continuous real-time monitoring** via rapid polling: use monitoring metrics; a browser is not a streaming subscription.
- **Paginating millions of messages** with fixed offsets: JMS has no universal immutable paging cursor.
- **Inspecting a Topic globally**: the JMS `QueueBrowser` API does not support it.
- **Editing/deleting/republishing messages** in a Queue: no portable browser API supports that; use a consumer or controlled management API.
- **Reading delayed messages before delivery time**: forbidden by the JMS specification.
- **Managing Queues in multi-tenant environments without authorization**: browsing can leak data.

### 14.3. Comparison with Artemis Console

Artemis Console provides screens to list Queues, browse messages, and paginate via management APIs. That is a **broker-specific interface**, not standard `QueueBrowser` that Java code can universally rely upon. Some console screens also allow **delete/move/copy/resend** when the account has permissions; those are **no longer "read-only browse" operations**.

If operations tooling is needed, grant console permissions to human operators separately; do not give application producers/workers admin credentials just to call `JmsTemplate.browse`.

## 15. Performance, memory, and deployment notes

### 15.1. Bounded browse

Always enforce limits on:

- Maximum messages inspected per pass, e.g. 20–100 IDs.
- Maximum body size logged; prefer metadata.
- Time allowed for the browse operation; enforce timeouts/request deadlines at the appropriate management layer.
- Execution frequency. An automated browse running every 100 ms on a large Queue can create heavy overhead.
- Access control and auditing; log when users inspect sensitive messages if policy requires.

Reading only 100 items from `Enumeration` **does not guarantee the provider only prefetched 100 items**. If strict page sizing is needed, use the broker's own management/paging API.

### 15.2. Do not retain JMS Messages after closing the browser for deferred processing

Although most Message getters work after receipt, some providers use lazy body streams/resources tied to the session. For browse logic, **extract small fields into a dedicated DTO/snapshot inside the callback**. Never return `Enumeration` or `QueueBrowser` from the callback.

Example observation DTO:

~~~java
// Java 17 record declared in an appropriate application:
public record MessageInfo(
        String jmsId,
        String eventType,
        String correlationId) {}
~~~

Inside the browser callback, you can extract:

~~~java
// Fragment: jakarta.jms.Message m from Enumeration.
MessageInfo info = new MessageInfo(
        m.getJMSMessageID(),
        m.getStringProperty("eventType"),
        m.getJMSCorrelationID());
~~~

Avoid loading huge `BytesMessage` payloads to return to a UI screen. If a body must be displayed, sanitize and truncate it to avoid inadvertently dumping payloads into logs.

### 15.3. Do not lock the Queue or race consumers to force a "snapshot"

There is no portable JMS way to "lock a queue while browsing." Pausing workers, pausing brokers, or freezing management queues can disrupt production traffic; do so only after risk assessment under formal operational procedures.

For lightweight diagnostics, approximate results usually suffice. For compliance/legal audits requiring immutable records, design an **outbox, audit log, event store, or CDC** from the start. `QueueBrowser` is not a historical archive.

## 16. Common issues and diagnosis

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| Browser returns 0 yet Queue metrics show many | Delayed messages before `JMSDeliveryTime`, non-matching selector, in-flight, expiry, or broker semantics. | Check delivery times, selector, ready/scheduled/dispatching metrics. |
| Browser sees messages yet worker does not receive | Worker not started, missing `consume`, different selector, broker routing/transaction. | Consumer count, application logs, queue configuration. |
| Browse counts 12 yet metrics report 10 | Queue changed during enumeration; provider buffering. | Use metrics for backlog, not browse as an exact count. |
| `JMSException` or Spring `JmsException` on browse | Missing `browse` permission, wrong Queue, connection error, internal provider issue. | Inspect cause chain and broker security logs. |
| Browse sees a message yet receive gets a different one | Concurrent consumers/producers, priority/selector. | Check concurrent flows; do not assume snapshot/strict order. |
| Browser closed, continuing to use Enumeration fails | Resources were released. | Finish iterating inside the callback/try block. |
| Body unreadable via `TextMessage.getText()` | Actual message is `BytesMessage`/`MapMessage`/... | Check `instanceof` or use appropriate converter. |
| Using `receiveNoWait()` to peek makes messages vanish | That is a consuming receive, not browse. | Use `QueueBrowser` or `JmsTemplate.browse`. |
| Cannot browse a Topic | Standard API provides `QueueBrowser` only for Queues. | Use provider-specific management/subscription diagnostics. |
| App runs out of memory browsing a large Queue | Iterating/loading too many bodies, provider prefetch. | Bound results, extract metadata only, use broker monitoring/paging. |
| Read-only user access denied | Role has `send`/`consume` but lacks `browse`. | Grant appropriate `browse` permission rather than elevating to admin. |

**Recommended debugging sequence:**

1. Confirm the Queue actually exists with the exact name/routing.
2. Check the JMS `ConnectionFactory` principal and `browse` permission.
3. Try without a selector on a test Queue; then verify type/name of each property.
4. Check TTL, `JMSDeliveryTime`, active transactions, and running consumers.
5. Compare broker metrics with browse output, keeping in mind the two sources have different semantics.
6. Ensure browsers are closed, with no infinite loops or unbounded body logging.
7. Retest on an isolated broker and isolated queue to eliminate concurrent contention.

## 17. Testing "non-consuming" behavior

### 17.1. Unit testing BrowserCallback

With mocked `QueueBrowser` and `Enumeration<Message>`, verify:

- The callback calls `getEnumeration()` and collects IDs/properties correctly.
- It never creates a `MessageConsumer` or calls `acknowledge()`.
- It returns a `List` containing Strings/DTOs, not `QueueBrowser`.
- It respects configured element limits.
- It handles `JMSException`/unexpected message types per policy.

Mocks only verify callback logic, **not that the broker avoids consuming**, so integration tests are needed.

### 17.2. Integration tests with a real broker

On an isolated queue with no other consumers:

1. Send M1/M2/M3 with distinct `eventId`s and `JMSDeliveryTime` already reached.
2. Browse without a selector to obtain ID set A.
3. Browse again to obtain ID set B; on an unchanged queue, expect A = B.
4. Run `browseSelected` for matching messages only, leaving A/B unaffected.
5. Call consumer `receive` three times and verify all of M1/M2/M3 are received.
6. Browse after receives have acked/committed; result is empty.
7. Test edge cases—non-matching selector, TTL, delay, and concurrent consumers—**separately**, without mixing them into the stable demo assertions.

This verifies **non-consuming behavior**, rather than asserting "browse returned N" and merely assuming the queue is unchanged without testing a consumer afterward.

### 17.3. Worthwhile negative tests

- Browse with an account lacking `browse` permission: must be rejected per policy.
- Receive with an account having only `browse`: `consume` must be denied.
- Wrong Queue name: reports an error or sees no messages per broker policy; do not enable auto-create in production.
- Browse a message before its delivery time: that message must not be returned.
- Browser finishes while queue mutates: test accepts provider-dependent outcomes rather than asserting a strict snapshot.
- Try `browseSelected` with wrong property name/type: matches nothing as expected, without losing messages.

## 18. Review questions

1. **Does QueueBrowser consume messages?** No; it iterates messages on a Queue without removing them from the Queue.
2. **What is the API for iterating?** `QueueBrowser.getEnumeration()`, returning `java.util.Enumeration`.
3. **Why shouldn't `receiveNoWait()` be used to peek?** Because it is a consuming receive that can affect ack/transactions.
4. **What parameters does `JmsTemplate.browse`'s callback receive?** `Session` and `QueueBrowser` via `BrowserCallback<T>`.
5. **How does `browseSelected` differ from `receiveSelected`?** Browse only inspects; receive removes messages for processing.
6. **Does QueueBrowser guarantee a static snapshot?** No. Messages can arrive, expire, or be taken by other consumers during iteration.
7. **Can it see messages with a future `JMSDeliveryTime`?** No; they must not be returned before delivery time.
8. **Is there a standard browser for Topics?** No; JMS `QueueBrowser` is for Queues only.
9. **Is using QueueBrowser to count production queue depth strictly accurate?** No; use broker metrics.
10. **Is `browse` permission separate from `consume` in Artemis?** Yes; they are two distinct permissions.
11. **Is reading message bodies with a browser automatically data-safe?** No; payloads may be sensitive, requiring ACLs and logging limits.
12. **Does closing a browser lose messages?** No; closing releases resources without consuming messages.
13. **Can selectors filter on JSON body fields?** No; JMS selectors evaluate headers/properties.
14. **If another consumer receives a message between two browse calls, can results differ?** Yes, depending on the broker and concurrent activity.
15. **Can QueueBrowser edit or delete messages?** No portable API exists for that; use a consumer or controlled management API.
16. **Why shouldn't `Enumeration` be returned from a `JmsTemplate.browse` callback?** The browser/session may already be closed afterward, so extract needed data inside the callback.

## 19. Official documentation

- [Jakarta Messaging 3.1 Specification — QueueBrowser](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html), section **4.1.6 QueueBrowser**: non-consuming browse, enumeration not required to be a snapshot, no messages returned before delivery time.
- [Jakarta Messaging 3.1 — QueueBrowser API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/queuebrowser): `getEnumeration`, `getQueue`, `getMessageSelector`, `close`.
- [Jakarta Messaging — Session API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/session): `createBrowser(Queue)` and selector overloads.
- [Jakarta Messaging — JMSContext API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/jmscontext): simplified API `createBrowser`.
- [Spring Framework 6.2 — JmsTemplate API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/core/JmsTemplate.html): `browse` and `browseSelected`.
- [Spring Framework 6.2 — BrowserCallback API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jms/core/BrowserCallback.html): `doInJms(Session, QueueBrowser)`.
- [Spring Boot 3.5 — JMS with Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html): embedded broker configuration and `JmsTemplate`.
- [Apache ActiveMQ Artemis — Authentication & Authorization](https://artemis.apache.org/components/artemis/documentation/latest/security.html): `browse`, `consume`, and `send` permissions.
- [Apache ActiveMQ Artemis Console](https://artemis.apache.org/components/artemis-console/documentation/latest/): queue administration, browsing, and provider pagination.

**Remember:** `QueueBrowser` is a tool for **inspecting messages on a Queue without consuming them** via `Enumeration`; in Spring JMS, use `JmsTemplate.browse/browseSelected`. It **does not guarantee a snapshot**, does not replace consumers/ACK/transactions, does not browse Topics standardly, and **must not return delayed messages before `JMSDeliveryTime`**. In production, use metrics for backlog counts; when inspecting content, protect `browse` permissions, bound scope, and close resources.
