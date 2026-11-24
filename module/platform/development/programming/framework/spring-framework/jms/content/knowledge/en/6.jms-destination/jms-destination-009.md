# Destination Creation Permissions Differ from Send/Receive Permissions in Spring JMS

## 1. Goal and real-world problem

An application may be allowed to **send messages to a Queue** without being allowed to **create a new Queue**. Similarly, a worker may **receive messages** yet not be permitted to **send messages**, delete queues, or change broker configuration.

This is the distinction between two groups of operations:

- **Provisioning / administration:** creating, deleting, and configuring physical destinations on the message broker, or managing related subscriptions/resources.
- **Messaging:** sending (`send`), receiving (`consume`), or non-destructively reading (`browse`) messages on a destination **that already exists and for which permission is granted**.

This distinction matters especially in Spring JMS because code like `jmsTemplate.convertAndSend("orders.commands", data)` and `@JmsListener(destination = "orders.commands")` typically declares only the **destination name**. Whether the real resource is pre-created, auto-created, or rejected is decided by the **JMS provider/broker**.

After this lesson, you should be able to:

1. Distinguish `Queue`/`Topic` as API objects from physical destinations on the broker.
2. Explain why `Session.createQueue()` does not equate to permission to create a queue on the server.
3. Separate create/delete, send, consume, browse, and admin permissions; apply **least privilege**.
4. Understand the effects of ActiveMQ Artemis's **auto-create** settings.
5. Configure a Spring Boot + Artemis test setup with separate sender and receiver accounts.
6. Diagnose when an application has the right queue name yet still cannot send/receive due to missing permissions or a non-existent destination.

## 2. Two layers to distinguish: API destination and broker resource

Jakarta Messaging (JMS) defines `jakarta.jms.Destination`, with two primary types: `Queue` (point-to-point) and `Topic` (publish/subscribe). A Java object named `orders.commands` **does not by itself guarantee** that the broker has a matching physical queue or topic.

~~~mermaid
flowchart LR
    A["Spring JMS application"] --> B["Named Queue/Topic object"]
    B --> C["Connect and perform send/consume"]
    C --> D{"Broker checks"}
    D --> E["Destination exists or valid auto-create?"]
    E --> F["Account has matching permissions?"]
    F --> G["Deliver or receive message"]
~~~

**Specifically:**

~~~java
// Fragment: Session session was already created from Connection.
jakarta.jms.Queue queue = session.createQueue("orders.commands");
~~~

`createQueue(String)` creates a **Queue object wrapping a provider-understood name**; according to the JMS specification, it is **not a command to create a physical queue**. Likewise, `session.createTopic("domain.events")` is not a command to create a physical topic. A provider may support auto-creating resources during send or consumer registration, yet that is a **provider-specific mechanism**.

With JNDI:

~~~java
// Fragment: context was already configured for the JMS provider.
jakarta.jms.Queue queue =
        (jakarta.jms.Queue) context.lookup("jms/queue/Orders");
~~~

`lookup` retrieves an **administered object** already configured in JNDI; lookup also does not grant `send`/`consume` permissions and does not equate to creating a physical queue. JNDI name syntax differs from physical broker names and depends on provider configuration.

**Exception to remember:** `Session.createTemporaryQueue()`/`createTemporaryTopic()` genuinely creates a **temporary destination** whose lifecycle is tied to the connection. Thus this operation may require corresponding resource-creation permissions on the broker. Temporary destinations are typically used for `JMSReplyTo` in request/reply and require separate permission policies; do not generalize from `createQueue(String)`.

### 2.1. Concrete example

Suppose a system has the physical resource `orders.commands`:

- The **Order API** service only sends the command `ORDER-101`.
- The **Order Worker** service only receives and processes commands.
- The operations team creates the queue, sets durability, DLQ, max-size, ACLs, and monitors backlog.

Order API **does not need queue create/delete permissions** just because it knows the name and can send. Order Worker **does not need queue create/delete permissions** just because it uses `@JmsListener`.

If the queue has not been created yet while the broker has **auto-create** enabled, the first send/receive *may* trigger resource creation. Specific authorization policies and behavior are determined by the broker, version, security manager, and configuration; in tightly controlled environments, **pre-provision** and **lock down auto-create** for critical namespaces.

## 3. Authentication differs from authorization

Before discussing create/send/receive permissions, separate:

- **Authentication:** verifying connection identity, for example user `order-sender` successfully logging into Artemis.
- **Authorization:** deciding which operations that account may perform, and on **which addresses/queues**.

Successfully logging in does not mean the user can send to any Queue, read any Topic, or create arbitrary destinations. The same user may be allowed to `send` to `orders.commands` while being denied `consume` on that exact queue.

Example with four roles:

| Role | Purpose | Minimum permission on `orders.commands` |
| --- | --- | --- |
| `order-senders` | Producer sending commands | `send` |
| `order-workers` | Consumer processing commands | `consume` |
| `order-auditors` | Inspecting messages when authorized | `browse` |
| `broker-admins` | Controlled destination provisioning/deletion | `createAddress`, `createDurableQueue`, etc. |

These are **authorization examples**, not built-in JMS roles. Jakarta Messaging defines the API and send/receive semantics; permission names and role assignments are **provider-specific**.

For production applications, manage separate broker accounts per service rather than sharing one `admin` account across both producers and consumers. Splitting roles limits blast radius if a service's credentials leak or a service sends messages to the wrong address.

## 4. Permission groups in ActiveMQ Artemis

ActiveMQ Artemis provides a role-based security model applied primarily **at the address level** (and consume can be refined using fully qualified queue names in some cases). Common permissions:

| Artemis permission | Meaning | Examples of who needs it |
| --- | --- | --- |
| `createAddress` | Create an **address** matching `match`. | Provisioning systems, address auto-create operations. |
| `deleteAddress` | Delete a matching address. | Admin tools, maintenance operations. |
| `createDurableQueue` | Create a durable queue under a matching address. | Provisioning persistent work queues/subscriptions. |
| `deleteDurableQueue` | Delete a durable queue. | Operations after checking backlog and data. |
| `createNonDurableQueue` | Create a non-durable queue. | Certain subscriptions/temporary resources. |
| `deleteNonDurableQueue` | Delete a non-durable queue. | Cleaning up subscriptions/temporary resources per policy. |
| `send` | Send messages to a matching address. | Producers. |
| `consume` | Receive/consume messages from queues on a matching address. | Workers, `@JmsListener`. |
| `browse` | View messages in a queue **without consuming them**. | `QueueBrowser`, observers. |
| `manage` | Use management operations via the management address. | Broker administration per policy. |
| `view` / `edit` | Fine-grained read/write permissions for the management API if corresponding management features are enabled. | Console/JMX/management APIs. |

**No permission in the list automatically implies any other permission.** For instance, `send` does not imply `consume` or `deleteDurableQueue`. `browse` differs from `consume`: browsing does not remove messages from the queue; consuming can lead to acknowledgement and removing messages from the backlog per receive semantics.

However, **auto-create** and broker compatibility/plugin mechanisms can cause send/receive operations to create auxiliary resources. To verify least privilege, inspect **both auto-create settings and ACLs**, not just the permission table.

### 4.1. Artemis uses addresses and queues, not just JMS Queue names

In Artemis:

- **Address:** target receiving messages from producers, then routing according to rules.
- **Queue:** where messages are stored and consumers receive; one address can have one or more queues.
- **Anycast:** typically used for the JMS Queue model, distributing work across competing consumers on a single target queue.
- **Multicast:** typically used for the JMS Topic model, distributing to matching subscription queues.

For example, an address `orders.commands` contains a queue of the same name. The producer sends to the address; the worker consumes from the queue. The `send` permission is checked against the address; the `consume` permission applies when receiving from the queue bound to the address.

For an address with multiple queues, Artemis can support **FQQN** syntax `address::queue` to reference a specific queue and scope `consume` more finely. However, **do not assume** a `send` ACL on an FQQN blocks messages sent to the shared address: messages sent to the address can still be routed to multiple queues. Read the security/FQQN documentation before configuring per-subscription authorization.

## 5. Why does creating a Queue object in code not require admin permissions?

Consider this Java JMS snippet:

~~~java
// Fragment: ConnectionFactory factory is present.
try (jakarta.jms.JMSContext context = factory.createContext()) {
    jakarta.jms.Queue queue = context.createQueue("orders.commands");
    context.createProducer().send(queue, "ORDER-101");
}
~~~

Here there are **two separate actions**:

1. `context.createQueue("orders.commands")` creates a **name-reference object**.
2. `createProducer().send(queue, ...)` asks the broker to **send the message** and may perform additional routing/resource checks.

If `orders.commands` is already provisioned and the account only has `send`, the send **can still succeed** even without `createAddress` or `createDurableQueue`. The conditions are valid login, a healthy broker, and no other policy blocking the send.

If the destination does not exist yet:

- With **auto-create disabled**, the broker does not auto-provision so send/receive may fail or go unrouted; exact symptoms depend on the provider and policy.
- With **auto-create enabled**, the broker may create the address/queue according to rules; creation may require create permissions or be handled by the security manager via its own mechanism.
- With the **wrong routing type** or address/queue name, sending still does not mean an expected consumer will receive the message.

Therefore **"an API containing the word create" does not mean "the application has permission to create broker resources."** Separate the Java object, side-effect behavior, and server-side permission checks.

## 6. Artemis configuration: provision first, send/receive after

The examples below assume an **initialized standalone ActiveMQ Artemis broker with security enabled**. The XML snippets are **configuration blocks belonging to `etc/broker.xml`**, inserted into the appropriate section of the existing file; they are not a complete standalone XML file. Account `sender` belongs to role `order-senders`, `worker` belongs to `order-workers`, and operations accounts belong to `broker-admins`; user creation and role assignment are done in the broker's active authentication mechanism.

### 6.1. Declaring a pre-existing address + Queue

~~~xml
<addresses>
    <address name="orders.commands">
        <anycast>
            <queue name="orders.commands">
                <durable>true</durable>
            </queue>
        </anycast>
    </address>
</addresses>
~~~

This is Artemis's **anycast** configuration pattern. It differs from calling `session.createQueue(...)`: the broker creates the resource from configuration at startup or via supported reload mechanisms.

### 6.2. Disabling auto-create in a critical namespace

~~~xml
<address-settings>
    <address-setting match="orders.#">
        <auto-create-addresses>false</auto-create-addresses>
        <auto-create-queues>false</auto-create-queues>
    </address-setting>
</address-settings>
~~~

`orders.#` in Artemis's default wildcard syntax matches addresses in the `orders` namespace. Purpose: services may only use pre-provisioned resources, never spawning extra queues due to typos. Do not define duplicate `address-setting` entries with the same `match` without understanding how the broker merges/evaluates them; merge these properties into existing blocks to keep policies like redelivery, paging, and DLQ intact.

**Caution:** disabling auto-create is intended for pre-provisioned application queues; certain Topic subscription types need to create queues representing subscriptions at runtime. Evaluate policies for Topic/temporary-destination namespaces separately rather than applying them mechanically across the entire broker.

### 6.3. Separating permissions by role

~~~xml
<security-settings>
    <security-setting match="orders.#">
        <permission type="send" roles="order-senders,broker-admins"/>
        <permission type="consume" roles="order-workers,broker-admins"/>
        <permission type="browse" roles="order-auditors,broker-admins"/>

        <permission type="createAddress" roles="broker-admins"/>
        <permission type="deleteAddress" roles="broker-admins"/>
        <permission type="createDurableQueue" roles="broker-admins"/>
        <permission type="deleteDurableQueue" roles="broker-admins"/>
        <permission type="createNonDurableQueue" roles="broker-admins"/>
        <permission type="deleteNonDurableQueue" roles="broker-admins"/>
    </security-setting>
</security-settings>
~~~

**Interpretation:** accounts with role `order-senders` only receive matching `send` permission; `order-workers` only `consume`; `order-auditors` only `browse`; `broker-admins` hold the administrative permissions on this address/queue. If `manage` or `view`/`edit` via the management address is needed, those are **additional policies**, not automatically granted by `createAddress`.

This is an **illustrative example for one namespace**: ensure credentials, roles, default wildcards, and other security blocks are configured compatibly. In Artemis, if multiple security settings match an address, **the most specific match takes precedence and does not inherit permissions from broader matches**. For instance, a more specific `orders.commands` block can override every permission in `orders.#`. Inspect all matching blocks.

**Do not replace** the entire `broker.xml` with just the snippets above; the file also contains acceptors, connectors, journal, security manager, and other settings. In production, changes must be tested and deployed through operational procedures.

### 6.4. Expected state after configuration

| Account/role | Send to existing queue | Receive from existing queue | Create/delete destination | Browse |
| --- | --- | --- | --- | --- |
| `sender` / `order-senders` | Yes | No | No | No |
| `worker` / `order-workers` | No | Yes | No | No |
| `auditor` / `order-auditors` | No | No | No | Yes |
| `admin` / `broker-admins` | Yes | Yes | Yes per policy | Yes |

Note that send/receive success also depends on the **physical queue existing with the right routing**. If a user belongs to multiple roles, effective permissions may be the union of granted permissions per the broker. The table assumes each account holds only the stated role.

## 7. Spring Boot 3.5.x example running against an ACL-enabled broker

This example uses **Java 17+**, **Spring Boot 3.5.7**, connecting to a **standalone Artemis broker** at `localhost:61616`. Two profiles run the same codebase under two distinct identities:

- `producer` profile: Spring `JmsTemplate` sends `ORDER-101`.
- `consumer` profile: Spring `@JmsListener` receives `ORDER-101`.

**Prerequisites:** the broker is running, queue `orders.commands` is provisioned as in section 6, and accounts `sender`/`worker` exist with their respective roles. Passwords are configured on the broker; never store real passwords in the repository. Set `SPRING_ARTEMIS_USER` and `SPRING_ARTEMIS_PASSWORD` environment variables before starting each process.

Structure:

~~~text
jms-acl-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/jmsacl/
    │   ├── JmsAclApplication.java
    │   ├── ProducerConfiguration.java
    │   └── OrderReceiver.java
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
    <artifactId>jms-acl-demo</artifactId>
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

Do not add an embedded Artemis dependency: this example must connect to a standalone broker **with ACLs enabled** to observe the difference between sender and receiver roles. Substituting an embedded broker with different security settings may not yield equivalent results.

### 7.2. application.properties

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.jms.pub-sub-domain=false
spring.main.banner-mode=off
~~~

Spring Boot automatically reads `SPRING_ARTEMIS_USER` and `SPRING_ARTEMIS_PASSWORD` from the environment to bind `spring.artemis.user`/`spring.artemis.password`. Each process must supply its corresponding account.

`spring.jms.pub-sub-domain=false` configures Queue send/receive; it does not mean the queue is auto-created or broker permissions are bypassed.

### 7.3. JmsAclApplication.java

~~~java
package com.example.jmsacl;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.jms.annotation.EnableJms;

@SpringBootApplication
@EnableJms
public class JmsAclApplication {

    public static void main(String[] args) {
        SpringApplication.run(JmsAclApplication.class, args);
    }
}
~~~

### 7.4. ProducerConfiguration.java

~~~java
package com.example.jmsacl;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.jms.core.JmsTemplate;

@Configuration
@Profile("producer")
public class ProducerConfiguration {

    @Bean
    ApplicationRunner sendOrder(JmsTemplate jmsTemplate) {
        return args -> {
            jmsTemplate.convertAndSend("orders.commands", "ORDER-101");
            System.out.println("SENT ORDER-101");
        };
    }
}
~~~

With the `producer` profile, `JmsTemplate` resolves the destination name and calls the send API under the process's credentials. `SENT ORDER-101` is printed only after `convertAndSend` returns successfully; it does not mean the consumer has finished processing.

### 7.5. OrderReceiver.java

~~~java
package com.example.jmsacl;

import org.springframework.context.annotation.Profile;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
@Profile("consumer")
public class OrderReceiver {

    @JmsListener(destination = "orders.commands")
    public void receive(String body) {
        System.out.println("RECEIVED " + body);
    }
}
~~~

With the `consumer` profile, Spring creates a listener container using the configured account to connect and **consume** from the Queue. If permissions are missing, the container may log errors and attempt restarts/reconnects; it is not guaranteed that the error will immediately terminate the process.

### 7.6. Starting and observing results

In **terminal A**, set `SPRING_ARTEMIS_USER=worker` and the worker account's password (via your environment's secret mechanism), then run:

~~~bash
mvn spring-boot:run -Dspring-boot.run.profiles=consumer
~~~

In **terminal B**, set `SPRING_ARTEMIS_USER=sender` and the sender account's password, then run:

~~~bash
mvn spring-boot:run -Dspring-boot.run.profiles=producer
~~~

When the broker, queue, roles, and credentials are all valid, the expected application lines (aside from Spring/Artemis logs) are:

~~~text
SENT ORDER-101
RECEIVED ORDER-101
~~~

These are **two lines coming from two processes**, not a single fixed combined stdout. `SENT` does not confirm `RECEIVED` has appeared yet: sending and receiving can be separated in time. If you run the sender while the consumer is down, the message may remain on the queue waiting for the worker depending on delivery mode, persistence, TTL, broker policy, and transactions.

To inspect actual roles yourself, use your organization's authorized broker admin tools; **do not grant admin permissions to the application just to check**.

## 8. Verifying each permission individually

Do not verify ACLs using only a single "send then receive succeeds" flow. That only proves the **two processes combined** can transfer a message, not that services lack excessive privileges.

Test suite following **positive + negative** principles:

| Case | Identity used | Action | Expectation |
| --- | --- | --- | --- |
| 1 | `sender` | `convertAndSend` to `orders.commands` | Succeeds when queue exists and broker is healthy. |
| 2 | `worker` | `@JmsListener` on `orders.commands` | Receives valid message. |
| 3 | `sender` | Start consumer on same queue | Denied `consume`, receives no messages. |
| 4 | `worker` | Attempt `convertAndSend` | Denied `send`. |
| 5 | `sender` or `worker` | Use broker management API to create/delete queue | Lacks admin create/delete permission; verify admin policy separately. |
| 6 | `auditor` | Browse via `QueueBrowser` | Reads non-destructively if `browse` is granted, lacks `consume`. |

Negative tests must run in a **test environment** or against authorized test resources so they do not disrupt queues serving live business traffic. Avoid deleting queues just to prove delete restrictions; test the API permissions or dedicated test resources with isolated lifecycles.

Example fragment attempting to create a consumer under a send-only identity:

~~~java
// Fragment: factory is a ConnectionFactory authenticated as "sender".
// Queue already exists, yet sender is not granted consume.
try (jakarta.jms.JMSContext context = factory.createContext()) {
    jakarta.jms.Queue queue = context.createQueue("orders.commands");
    try (jakarta.jms.JMSConsumer ignored =
                 context.createConsumer(queue)) {
        // If the broker allows it, re-check the security config.
    }
}
~~~

Failure may occur at `createConsumer`, when the broker begins delivery, or inside the listener container. The exact exception class and message depend on the provider, version, call path, and security manager. You may encounter `JMSSecurityException`, an equivalent JMS exception, or a provider error translated by Spring into `JmsException`; inspect the **cause chain** and broker logs rather than relying on a single fixed error message string.

## 9. Auto-create: side effects that cause misunderstandings

Artemis supports configuring:

- `auto-create-addresses`
- `auto-create-queues`
- `auto-delete-addresses`
- `auto-delete-queues`

When auto-create is enabled, depending on the protocol and provider policy, **sending to a non-existent address or opening a consumer on a non-existent queue** can make the broker automatically create the resource. Some plugins/compatibility modes may handle auto-create permissions differently from direct admin grants; always verify on your exact version and security manager.

### 9.1. Misleading scenario

The application calls:

~~~java
jmsTemplate.convertAndSend("orders.commmands", "ORDER-101");
~~~

The name with **three `m`s** is a typo for `orders.commands`. If the broker allows auto-create, the wrong address can be created or the message routed somewhere with no worker, silently accumulating an unexpected backlog. If auto-create is disabled and broker config checks destination existence, the mistake usually surfaces earlier.

**Do not treat a successful send return as proof that the intended consumer received the message.** Observe queue depth, consumer count, routing, and acknowledgement/transactions. Even when sending succeeds to an existing address, messages may not route to the expected queue if routing rules are misconfigured.

### 9.2. Distinguishing "allowed to auto-create" from "allowed to administer"

A broker may apply different behaviors:

1. Require `createAddress`/`createDurableQueue` to auto-create resources for clients.
2. Have an auto-creation grant policy tied to `send`/compatibility roles.
3. Pre-create certain auxiliary resources for Topics/subscriptions per protocol.
4. Disable auto-create across an entire namespace to enforce pre-provisioning.

Thus the safe statement is: **destination creation permissions and send/receive permissions are conceptually distinct actions; actual policies and side effects are decided by the broker**. Avoid claiming `send` can always or never create resources across all brokers.

## 10. Topic subscriptions, TemporaryQueue, and request/reply

### 10.1. Topics often need dedicated subscription resources

With a JMS Topic, a `@JmsListener` does not merely need read access to the `events` address; the broker may create a **queue representing the subscription**, especially for durable subscriptions. Consequently, a Topic consumer may need permissions to create non-durable/durable subscription queues in some deployments even though the source code contains no `createQueue` call.

Illustrative example (listener configuration fragment, **not a standalone application**):

~~~java
@JmsListener(
        destination = "domain.events",
        subscription = "billing",
        containerFactory = "topicListenerFactory")
public void onEvent(String event) {
    // Handle business event; factory configures pubSubDomain=true.
}
~~~

`topicListenerFactory` must be a bean defined by the application; when using durable subscriptions you must also configure `subscriptionDurable`, client ID, and matching JMS settings. **Do not blindly grant create-any-queue permission to every worker** just because one Topic app needs subscriptions; scope permissions to the necessary address, queue type, and lifecycle.

### 10.2. Temporary destinations are a clear exception

`Session.createTemporaryQueue()` and `JMSContext.createTemporaryQueue()` **genuinely request creation of a temporary destination**, commonly used as `JMSReplyTo` for request/reply. Creating and deleting temporary resources may require `createAddress`, `createNonDurableQueue`, or equivalent provider permissions.

A Temporary Queue typically allows only **the connection that created it** to create consumers, while other connections may send replies per provider rules. Permission design must account for temporary address names, auto-delete policies, and reply send permissions; **do not grant `create*` across the entire business namespace** just to make request/reply work.

### 10.3. Browse is not consume

`QueueBrowser` (JMS) allows viewing messages in a queue **without removing them from the queue**. However, a browse snapshot is not guaranteed stable while producers/consumers operate concurrently, and viewing message bodies can expose sensitive data. Therefore the `order-auditors` role must be governed as a data-read permission, not treated as automatically safe just because it does not delete messages.

## 11. Why does Spring JMS not "grant permissions on your behalf"?

Spring manages lifecycle and API translation, yet never replaces broker authorization:

- `JmsTemplate` uses `DestinationResolver`. By default `DynamicDestinationResolver` resolves names to JMS Queue/Topic objects; this **does not grant permission to create physical destinations**.
- `JndiDestinationResolver` looks up administered destinations if JNDI is configured; lookup does not attest to send/consume permissions.
- `@JmsListener(destination="orders.commands")` registers a listener under the `ConnectionFactory`'s credentials; the broker can still reject it.
- `@EnableJms` activates listener infrastructure; it **does not create broker accounts or bypass ACLs**.
- `spring.jms.pub-sub-domain=true/false` picks the default Topic/Queue interpretation; it **does not unlock permissions**.

Thus if a Spring application starts normally yet the listener reports authorization failure, look at **broker users/roles, destinations, security matches, auto-create, and subscription queues**, instead of adding a `Queue` bean or granting admin rights to the service.

**Do not confuse with Spring Security.** Spring Security controls HTTP/method authorization within the application; broker ACLs control JMS connections and message operations at the broker. An authorized HTTP endpoint does not imply the application's JMS credentials have `send`.

## 12. Diagnosing specific errors

| Symptom | Causes to check | How to verify |
| --- | --- | --- |
| `createQueue("name")` returns object yet `send` fails | No real queue, wrong address, missing `send`, broker disallows auto-create | Check broker `addresses/queues`, username, roles, and security logs. |
| Producer sends successfully yet listener receives nothing | Consumer lacks `consume`, wrong selector, missing queue binding, listener stopped | Check consumer roles, queue depth, consumer count, destination name. |
| Listener reports subscription creation error | Topic subscription needs auxiliary queue, lacks `createDurableQueue`/`createNonDurableQueue` per provider | Check durable/shared settings, client ID, subscription name, and Topic address ACLs. |
| Queue appears automatically when app runs | `auto-create-queues`/`auto-create-addresses` enabled or provider auto-provisions | Check address settings, security manager, protocol, and audit events. |
| Sender has `send` yet cannot create a new queue via console | `send` differs from `create*` or `manage` | Check effective matching security setting and role mapping. |
| Consumer can receive yet cannot browse | `consume` and `browse` are separate permissions | Test `QueueBrowser` with a dedicated test account. |
| Role granted yet permission still denied | More specific security match overrides broader match, roles unsynced, auth cache, wrong credentials | Read effective security settings and broker logs. |
| Added `createDurableQueue` yet still cannot create | Missing `createAddress`, different namespace, or management API needs its own permission | Check resource type, address, and API path. |
| App runs as admin yet fails as service user | Service user lacks ACL or auto-create enabled only for admin | Pre-provision, grant least privilege, never use admin as a permanent fix. |

Follow an ordered diagnostic workflow:

1. **Authentication:** are username/password/client certificate valid? Did the connection succeed?
2. **Destination:** Queue or Topic type, address/queue name, routing type, and physical existence?
3. **Effective ACLs:** which roles does the account have, and which **most specific** security-setting matches?
4. **Operation:** did the failure happen on `send`, `consume`, `browse`, queue auto-create, or management?
5. **Provider behavior:** are auto-create, subscription queues, FQQN, or security plugins introducing extra permission requirements?
6. **Observability:** check server logs, application exception cause chains, queue depth, and consumer counts.

Avoid "fixing" errors by turning off `security-enabled` or granting every permission on `#` in real environments. That hides misconfigurations and expands access unintentionally.

## 13. Principles for safe, maintainable deployment

**Provision destinations before deploying services:** use broker configuration, infrastructure-as-code, or an operations-controlled provisioning step. Include address/queue name, routing type, persistence, TTL, DLQ, size limits, retry policies, and permissions.

**Separate identities by service and environment:** `order-sender` has `send` to `orders.commands`; `order-worker` has `consume` from this queue. Staging accounts should not share secrets with production.

**Scope namespaces narrowly:** `orders.#` is narrower than `#`. Yet wildcards alone do not protect you once you add a more specific rule; specific rules can replace permissions from broader rules. Review both security-settings and address-settings.

**Treat `browse` as a data-read permission:** message payloads may contain customer IDs, emails, and order details. Manage observer roles, retention windows, and auditing.

**Monitor create/delete operations:** enable appropriate logging/auditing for provisioning, inspect unexpected queues, and alert when unexpected new destinations or subscription queues appear.

**Design legitimate exceptions explicitly:** request/reply needs temporary destinations; Topics need subscription queues; scope these privileges to dedicated namespaces and policies rather than promoting the whole application to broker admin.

**Automate ACL tests in appropriate environments:** combine positive and negative tests. `sender` succeeding on send **does not prove** it cannot consume or create queues; include at least one controlled negative assertion.

## 14. Self-check questions

1. **Does `session.createQueue("orders.commands")` actually create a physical queue?** No. It creates a name-reference object; creating real resources belongs to the provider/administration.
2. **Does a producer need `createDurableQueue` permission to send to an existing queue?** Conceptually no; it needs `send` and matching broker conditions. Other auto-create/ACL policies may add requirements in specific deployments.
3. **What permission should a worker that only processes messages be granted?** `consume` on the required queue; do not grant send, browse, create, or delete by default.
4. **Why should a sender not be granted `browse`?** Browse allows inspecting queued message payloads, which is a separate data-read privilege.
5. **If auto-create is enabled, what harm can a misspelled queue name cause?** The broker may create an unintended queue or accept messages with no matching consumer; monitor and consider disabling auto-create.
6. **Does `JndiDestinationResolver` allow creating real queues or granting send permissions?** No. It resolves objects from JNDI; the broker still governs operations.
7. **Why might a Topic subscriber need queue-creation permission?** The broker may create a queue to back the subscription; permissions depend on durable/non-durable settings and broker config.
8. **Does `createTemporaryQueue()` have the same meaning as `createQueue("x")`?** No. A TemporaryQueue is a real temporary resource tied to the connection.
9. **You already have the `send` role, yet the management API denies creating a queue—is that a contradiction?** No. Creating/managing is a different permission from sending.
10. **Why must you check the most specific security-setting?** Artemis does not automatically inherit permissions from a broader rule when a more specific rule matches; effective ACLs may differ from expectations.

## 15. References

- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html), sections on **Destination**, **Queue management**, **temporary destinations**, and **administered objects**.
- [Jakarta Messaging — Session API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/session), `createQueue`, `createTopic`, and `createTemporaryQueue`.
- [Spring Framework — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html), `JmsTemplate`, `DynamicDestinationResolver`, `JndiDestinationResolver`.
- [Spring Boot — JMS / Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html), native broker settings and connection auto-configuration.
- [Apache ActiveMQ Artemis — Authentication & Authorization](https://artemis.apache.org/components/artemis/documentation/latest/security.html), roles `create*`, `send`, `consume`, `browse`, `manage`, and security-setting precedence.
- [Apache ActiveMQ Artemis — Address Model](https://artemis.apache.org/components/artemis/documentation/latest/address-model.html), addresses, queues, anycast/multicast, and provisioning.
- [Apache ActiveMQ Artemis — Address Settings](https://artemis.apache.org/components/artemis/documentation/latest/address-settings.html), `auto-create-addresses`/`auto-create-queues` and auto-delete policies.

**Key takeaway:** an application knowing a destination name or calling `createQueue(String)` **is not permission to create real resources on the broker**. `send`, `consume`, `browse`, and `create/delete/manage` permissions serve distinct purposes. Spring JMS makes API calls convenient, while the broker enforces authorization; to separate permissions reliably, pre-provision, control auto-create, and test ACLs per role.
