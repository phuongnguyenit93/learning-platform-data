# Destination Naming Conventions by Environment and Business Domain in Spring JMS

## 1. Goal

When a system has many Queues, Topics, services, and deployment environments, inconsistent destination naming causes hard-to-spot bugs: a `dev` application accidentally sends to a `prod` queue, two business domains reuse the same name, a listener registers the wrong destination type, or operations cannot tell who owns a destination. A good naming convention enables **accurate routing, environment separation, authorization, observability, and controlled contract evolution**.

After this lesson, you will be able to:
- Distinguish **logical names in the application**, **physical destination names** on the broker, and **subscription names**.
- Design names by environment (`dev`, `test`, `stg`, `prod`), business domain, subject, and message intent.
- Explain why naming conventions are an **architectural decision**, not a mandatory requirement of the Jakarta Messaging specification.
- Configure a publisher and `@JmsListener` to share the same name via Spring Boot externalized configuration.
- Establish naming principles for retry/DLQ, versioning, multi-tenancy, access permissions, and migration.
- Validate names using Java 17, and verify in practice with Spring JMS and a broker before release.

This lesson belongs to the **Destination** group. The focus is on naming and Queue/Topic management lifecycle, without diving deep into delivery tuning, transactions, or broker-specific cluster configuration.

## 2. Three naming layers to distinguish

~~~text
Spring Application                                   Broker
┌─────────────────────────────────────┐            ┌──────────────────────────────┐
│ Logical configuration key           │            │ Physical JMS destination     │
│ app.messaging.destinations.invoice-issue         │                              │
│              │                      │            │ dev.billing.invoice.issue.v1 │
│              ▼                      │            │    └─ Queue                  │
│           config value ───────────────────────────>│                              │
│              │                      │            │ prod.sales.order.created.v1  │
│  JmsTemplate / @JmsListener          │            │    └─ Topic                  │
└─────────────────────────────────────┘            └──────────────────────────────┘
~~~

1. **Logical name:** configuration key or internal application identifier, for example `app.messaging.destinations.invoice-issue`. This name reflects the code's responsibility and should remain stable across environments.
2. **Physical destination name:** the string that the JMS client passes to the provider when looking up/creating a Queue or Topic, for example `dev.billing.invoice.issue.v1`. The broker or administration layer maps this string to the real resource according to provider rules.
3. **Subscription name:** the identifier of a Topic subscription (especially durable/shared), for example `billing-reporting-v1`. This is a **different entity from the Topic name**; multiple independent subscriptions can read from the same Topic.

According to Jakarta Messaging, `Queue` and `Topic` are two types of `Destination`. Using names with dots, hyphens, environment prefixes, or version segments is a **convention chosen by the development team**, not mandatory JMS syntax. Calling `Session.createQueue(String)` or `Session.createTopic(String)` does not necessarily make the broker auto-create a physical resource: behavior depends on the provider, JNDI, auto-create settings, and permissions.

**Queue and Topic names do not replace the destination type.** In Spring JMS, publishers using `JmsTemplate` and listener containers must be configured with the right Queue or Topic mode (`pubSubDomain`), even if the physical names look similar.

## 3. Recommended standard, operations-friendly naming pattern

For organizations with multiple applications/environments sharing a broker, you can start from the pattern:

~~~text
environment.domain.subject.action.vMAJOR
~~~

Breakdown:

| Segment | Meaning | Examples |
|---|---|---|
| `environment` | Environment owning the message, not hostname or pod. | `dev`, `test`, `stg`, `prod` |
| `domain` | Business domain/bounded context responsible for the message. | `billing`, `sales`, `identity` |
| `subject` | Main business entity/concept. | `invoice`, `order`, `user` |
| `action` | Command to execute or event that occurred. | `issue`, `created`, `paid` |
| `vMAJOR` | Major routing contract version when incompatible streams genuinely need separation. | `v1`, `v2` |

**Concrete examples** (these are illustrative names, not destinations already existing on a broker):

| Type | Physical name | Purpose |
|---|---|---|
| Queue | `dev.billing.invoice.issue.v1` | Invoice issuance request in dev; one consumer in the group handles each job. |
| Queue | `prod.fulfillment.shipment.dispatch.v1` | Production shipment dispatch command. |
| Topic | `stg.sales.order.created.v1` | Broadcasts order-created events to multiple subscriber groups in staging. |
| Topic | `prod.billing.invoice.paid.v2` | Invoice-paid event, routing contract major version 2. |

Use **lowercase ASCII**, standardize on a single separator (`.`), and avoid spaces, Vietnamese diacritics, and special characters unless proven supported by the broker/client. For instance, `prod.sales.order.created.v1` is clearer than `ORDER_EVENT` or `orders`. Segments should be concise with clear nouns/semantics; do not alternate between singular/plural or `order-created` vs `order_created` without a policy.

Names should not contain IP addresses, hostnames, passwords, deploy IDs, timestamps, or pod IDs. Those values change with infrastructure and destabilize contracts. If you need to identify the sender, use message properties/headers, tracing, and appropriate metrics rather than creating a new destination per instance.

### Should `queue`/`topic` be included in the name?

You can use a style like `prod.queue.billing.invoice.issue.v1` to make it easier for humans to read, though no standard requires it. If the organization already tracks **destination type in a destination registry**, repeating `queue` or `topic` as a segment is unnecessary. Either way, reviews must explicitly record `kind=QUEUE` or `kind=TOPIC`: the broker may distinguish them by resource type, routing type, or separate context.

**A convention must be consistent end-to-end.** Do not apply a new pattern unilaterally to legacy Queues that have consumers, ACLs, or monitoring tied to old names without a transition plan.

## 4. Environment separation: name prefix or separate broker?

Both strategies are valid, depending on topology.

### Strategy A — Single broker/namespace shared across multiple environments

Physical names carry an environment prefix:

~~~text
dev.billing.invoice.issue.v1
stg.billing.invoice.issue.v1
prod.billing.invoice.issue.v1
~~~

Helpful when operations needs to tell streams apart by sight. However, prefixes are **not a security isolation mechanism**. A dev application with overly broad credentials could still send to `prod.billing.invoice.issue.v1`. You still need separate ACLs/service accounts, namespaces/virtual hosts if supported by the provider, resource policies, quotas, and deployment guardrails.

### Strategy B — Each environment has an independent broker/namespace

The same logical/physical name can be used in each broker:

~~~text
DEV Broker:  billing.invoice.issue.v1
STG Broker:  billing.invoice.issue.v1
PROD Broker: billing.invoice.issue.v1
~~~

Real isolation comes from endpoints, accounts, network infrastructure, and access permissions—not a `prod` prefix. This avoids repeating the environment in the name and makes it easy for apps to move across environments via configuration. The prerequisite is that pipelines and provisioning map to the right broker with no cross-environment network paths.

**There is no requirement to stuff the environment into the name if namespaces are already physically separated.** Pick one standard for all services in the system. If shared brokers and dedicated brokers coexist, document the per-environment mapping in the registry to prevent confusion.

## 5. Aligning names with business domain and ownership

The business domain should reflect the **person/team owning the contract** rather than where consumers are deployed. For example, `sales.order.created` is an event published by Sales; Billing and Notification are independent subscribers. Do not name it `billing.sales.order.created` just because Billing reads that Topic.

For command Queues like `billing.invoice.issue`, the name typically describes the **invoked capability** and the owner handling the command; the sender may be Order Service while Billing still owns the destination. This clarifies who has authority to create it, change the schema, configure DLQs, and purge the queue.

Maintain an auditable **destination registry**; each entry should minimally include:

| Field | Example value |
|---|---|
| Logical key | `invoice-issue` |
| Physical name | `prod.billing.invoice.issue.v1` |
| Kind | `QUEUE` |
| Owner | `billing` |
| Producer | `order-service` |
| Consumer group | `invoice-worker` |
| Environment / broker namespace | `prod / finance-mq` |
| Message contract | `InvoiceIssueCommand v1` |
| Retry/DLQ policy | `invoice-issue-dlq-policy` |
| Security | Producer send; worker consume; ops administer |
| Lifecycle | Active, replacement, cutover, retired |

The application, domain, and registry names in the table are illustrative only. The security fields here represent **roles to grant**; actual permissions are enforced by the broker. For Topics with multiple subscribers, also record subscription names, durable/shared mode, client identity if any, and retention policy.

### Do not let consumers dictate event source names

When multiple services care about `order.created`, the owning domain publishes one destination contract and consumers subscribe to that contract. If each consumer picks its own Topic name, the publisher must know every consumer and the decoupling benefits of pub/sub diminish significantly.

## 6. Queues, Topics, and subscriptions are named differently

**Queue**: each message is typically delivered to one consumer in a competing group. The name should express a clear **task or command**, such as `prod.billing.invoice.issue.v1`. Consumers of the same Queue share the physical destination; if you add replicas to scale load, **do not create a new Queue per replica name**.

**Topic**: a message can reach multiple independent subscriptions. The name typically expresses an **event that occurred**, such as `prod.sales.order.created.v1`. A Topic does not represent a single specific consumer.

**Subscription**: when using durable/shared subscriptions, assign an identity tied to the **consumer group and purpose**, such as `billing-revenue-projection-v1` or `notification-order-email-v1`. In JMS, durable unshared identity also depends on `clientId` and `subscriptionName` per the API/provider. Renaming a subscription arbitrarily can cause the broker to treat it as a brand-new subscription, losing the link to the old backlog or leaving orphaned backlogs.

~~~text
Topic: prod.sales.order.created.v1
    ├── Subscription: billing-revenue-projection-v1
    │      └── Billing consumers
    └── Subscription: notification-order-email-v1
           └── Notification consumers
~~~

If Billing increases its replica count, check whether to use a **shared subscription** instead of giving every replica an independent subscription (which would make every replica receive the same event). Both the broker provider and JMS API must support the chosen subscription type.

## 7. Use configured names instead of hardcoding in Spring JMS

The most important practical rule: **Java code uses a stable logical key, while the physical name comes from configuration**.

Example using Spring Boot 3 + Java 17 with a **Queue** to execute an invoice-issuance command. In `application.yml`:

~~~yaml
app:
  messaging:
    destinations:
      invoice-issue: "${JMS_INVOICE_ISSUE_QUEUE:dev.billing.invoice.issue.v1}"
~~~

- If the environment variable `JMS_INVOICE_ISSUE_QUEUE` is unset, the name is `dev.billing.invoice.issue.v1`.
- In staging/production, the deployment pipeline supplies the registered name for that environment, such as `prod.billing.invoice.issue.v1` when using the prefix strategy.
- The key `app.messaging.destinations.invoice-issue` **stays constant in code**, while the physical value changes per deployment. Configuration keys and broker names are two separate layers.
- For strict production setups, you can **omit the dev default** so a missing environment variable fails fast; the dev default is only for lab convenience.

### Publisher: reading the physical name from the same property

`src/main/java/example/jms/InvoicePublisher.java`:

~~~java
package example.jms;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
public class InvoicePublisher {
    private final JmsTemplate jmsTemplate;
    private final String invoiceIssueDestination;

    public InvoicePublisher(
            JmsTemplate jmsTemplate,
            @Value("${app.messaging.destinations.invoice-issue}")
            String invoiceIssueDestination) {
        this.jmsTemplate = jmsTemplate;
        this.invoiceIssueDestination = invoiceIssueDestination;
    }

    public void issueInvoice(String invoiceId) {
        jmsTemplate.convertAndSend(invoiceIssueDestination, invoiceId);
    }
}
~~~

`JmsTemplate` defaults to the Queue model when `pubSubDomain=false`; here `invoiceIssueDestination` is the name of a **Queue**. Do not prepend `prod.` manually in Java, because the environment is already decided by configuration.

### Listener: referencing the same property

`src/main/java/example/jms/InvoiceListener.java`:

~~~java
package example.jms;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class InvoiceListener {
    @JmsListener(destination =
            "${app.messaging.destinations.invoice-issue}")
    public void handle(String invoiceId) {
        System.out.println("processed invoice=" + invoiceId);
    }
}
~~~

Spring resolves configuration placeholders in `@JmsListener`'s `destination` attribute when registering the listener endpoint. Publisher and listener thus share the same configuration source. When changing the name in a deployment environment, both point to the same Queue **when running with the same configuration**. When services are deployed independently, registry/provisioning must supply matching mappings for both producer and consumer.

**Do not turn a Queue name into a Topic merely by changing wording in docs.** For a Topic, you must configure `JmsTemplate#setPubSubDomain(true)` and listener container factory `setPubSubDomain(true)` (or pass an explicit `Topic` destination), and verify broker routing/subscriptions. A producer and consumer using mismatched destination types can "send successfully" without the intended listener receiving anything.

## 8. Runnable Spring Boot demo: one physical Queue for both send and receive

This section builds a small app with an HTTP endpoint to send a JMS message and verify the listener receives from the exact Queue. Uses Spring Boot 3.3.5, Java 17+, compatible Gradle 8.x, and embedded Artemis for **lab** purposes. If using an external broker, replace embedded Artemis with connection settings to the real broker; production should never rely on a demo to prove durability or HA.

Structure:

~~~text
destination-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/jms/
    │   ├── DestinationDemoApplication.java
    │   ├── InvoicePublisher.java
    │   ├── InvoiceListener.java
    │   └── InvoiceController.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'destination-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
    runtimeOnly 'org.apache.activemq:artemis-jakarta-server'
}
~~~

`src/main/resources/application.yml`:

~~~yaml
spring:
  artemis:
    mode: embedded
    embedded:
      queues: dev.billing.invoice.issue.v1
      persistent: false

app:
  messaging:
    destinations:
      invoice-issue: "${JMS_INVOICE_ISSUE_QUEUE:dev.billing.invoice.issue.v1}"
~~~

In the lab, the embedded broker creates queue `dev.billing.invoice.issue.v1`, matching the application default. If you change the environment variable `JMS_INVOICE_ISSUE_QUEUE`, you must **provision the corresponding queue on the broker**; do not only change the client property. With a remote broker, manage destinations via IaC/admin and restrict auto-create as appropriate.

`src/main/java/example/jms/DestinationDemoApplication.java`:

~~~java
package example.jms;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.jms.annotation.EnableJms;

@SpringBootApplication
@EnableJms
public class DestinationDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DestinationDemoApplication.class, args);
    }
}
~~~

Reuse `InvoicePublisher` and `InvoiceListener` from section 7 (saved in package `example.jms`). Add the controller:

`src/main/java/example/jms/InvoiceController.java`:

~~~java
package example.jms;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class InvoiceController {
    private final InvoicePublisher publisher;

    public InvoiceController(InvoicePublisher publisher) {
        this.publisher = publisher;
    }

    @PostMapping("/invoices/{id}/issue")
    public ResponseEntity<String> issue(@PathVariable String id) {
        publisher.issueInvoice(id);
        return ResponseEntity.accepted().body("queued invoice=" + id);
    }
}
~~~

Run from the `destination-demo` directory. If Gradle Wrapper is present:

~~~bash
./gradlew bootRun
~~~

On PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Or if no Wrapper is present, use a compatible installed Gradle:

~~~bash
gradle bootRun
~~~

Once the application and listener have started, send an HTTP request from another terminal:

~~~bash
curl -X POST http://localhost:8080/invoices/42/issue
~~~

HTTP response body:

~~~text
queued invoice=42
~~~

In the Spring Boot console appears:

~~~text
processed invoice=42
~~~

These are two separate observation points: HTTP returns once `convertAndSend` completes according to the provider, whereas the consumer processes asynchronously so the console line may appear **after** the response. Do not treat `202 Accepted` as proof that business invoice issuance has finished.

When changing the physical name via environment config, producer and listener use the same property; the broker must have that Queue. This test verifies naming and mapping in a lab environment; it does not verify TLS, failover, database transactions, persistence across broker restarts, or blocking a dev client from sending prod messages.

## 9. Standalone Java 17 rule validation

The validator below needs neither Spring nor a broker and **actually runs with `javac`/`java`**. It validates a **self-chosen convention**: environment must be in the allowed list, domain/subject/action segments use only lowercase ASCII with internal hyphens, and major version is at least 1. `Kind` is stored separately from the name; a name does not by itself prove Queue or Topic on the broker.

Create `DestinationConvention.java`:

~~~java
import java.util.Set;
import java.util.regex.Pattern;

public final class DestinationConvention {
    enum Kind { QUEUE, TOPIC }

    record Definition(Kind kind, String physicalName) {}

    private static final Set<String> ENVIRONMENTS =
            Set.of("dev", "test", "stg", "prod");
    private static final Pattern SEGMENT =
            Pattern.compile("[a-z][a-z0-9-]*");

    private DestinationConvention() {}

    static Definition define(
            Kind kind, String environment, String domain,
            String subject, String action, int majorVersion) {

        if (kind == null) {
            throw new IllegalArgumentException("kind is required");
        }
        if (!ENVIRONMENTS.contains(environment)) {
            throw new IllegalArgumentException(
                    "invalid environment: " + environment);
        }
        for (String segment : new String[] {domain, subject, action}) {
            if (segment == null || !SEGMENT.matcher(segment).matches()) {
                throw new IllegalArgumentException(
                        "invalid segment: " + segment);
            }
        }
        if (majorVersion < 1) {
            throw new IllegalArgumentException(
                    "major version must be positive");
        }

        String name = String.join(".", environment, domain,
                subject, action, "v" + majorVersion);
        return new Definition(kind, name);
    }

    public static void main(String[] args) {
        Definition command = define(
                Kind.QUEUE, "dev", "billing", "invoice", "issue", 1);
        Definition event = define(
                Kind.TOPIC, "prod", "sales", "order", "created", 2);

        System.out.println(command.kind() + " " + command.physicalName());
        System.out.println(event.kind() + " " + event.physicalName());

        try {
            define(Kind.QUEUE, "production", "billing",
                    "invoice", "issue", 1);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected: " + ex.getMessage());
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 DestinationConvention.java
java DestinationConvention
~~~

**Deterministic exact output:**

~~~text
QUEUE dev.billing.invoice.issue.v1
TOPIC prod.sales.order.created.v2
rejected: invalid environment: production
~~~

This validator is useful in unit tests or pipelines when generating names consistently. Even so, a regex is only an application-level policy; **it does not guarantee every broker vendor accepts that name**. In particular, length limits, reserved names, and provider separators need separate checks. Being able to render a `TOPIC` name does not provision a Topic on the broker.

## 10. Naming constraints depending on the JMS provider

Examples like `dev.billing.invoice.issue.v1` were chosen under relatively safe principles, yet actual validity depends on the provider:

| Provider | Naming notes |
|---|---|
| **Apache ActiveMQ Artemis** | Distinguishes address/queue and `anycast` routing (usually corresponding to Queue) / `multicast` (usually corresponding to Topic). Some scenarios use fully-qualified queue names with `address::queue` syntax; avoid `::` in regular names. |
| **IBM MQ** | Local queue names are limited to **48 characters**; `SYSTEM.` is a reserved prefix for queue manager resources. Separators do not automatically create ACL hierarchies; check IBM documentation for your specific platform and object type. |
| **ActiveMQ Classic** | Supports hierarchical destination conventions; wildcards/composite destinations and destination creation rules are **broker-specific features**, not universal JMS rules. |
| **Providers using JNDI** | JNDI lookup names can **differ from physical names** on the broker. The registry must document both the JNDI name and the mapped broker target. |

With IBM MQ, `prod.fulfillment.shipment.dispatch.v1` still fits the length limit, but very long multi-segment names can exceed it. Do not take an Artemis Topic or Queue name and assume it works verbatim on IBM MQ. Dots in some products are simply valid naming characters and **do not automatically enforce permissions or create folders**.

### Specifically for Artemis

In Artemis, an address and a queue can be two separate entities. A physical name that works when sending to a JMS Queue does not guarantee that the address has routing type `anycast` or that the queue was created as expected. For Topics, check `multicast` and subscription queues. Names containing `::` have FQQN semantics in supported contexts; **do not use it as a domain separator**, as that blurs application conventions with provider syntax.

## 11. Versioning: when to rename a destination?

Do not change the physical name on every minor payload edit. Distinguish:

- **Payload/schema version**: changes to fields, data types, and message compatibility rules.
- **Destination contract version**: changes where old consumers can no longer keep processing, or semantics/routing paths change.

For backward-compatible changes, typically keep `prod.sales.order.created.v1` and evolve the schema in a controlled way; schemas can carry their own version in headers/payload. For breaking changes, evaluate running `prod.sales.order.created.v2` in parallel with a cutover procedure.

Example of a controlled migration:

1. Register the new destination (Topic `v2`) along with its owner/ACL/retention in the registry.
2. Deploy consumers that understand the new contract; create durable subscriptions before publishing if backlog capture is needed.
3. Temporarily dual-publish or bridge `v1` to `v2` **only when a deduplication strategy is in place** and the source of truth is clearly defined.
4. Monitor consumer lag, backlog, error messages, and processing success rate.
5. Switch publishers and consumers on schedule; verify no consumers still depend on `v1`.
6. Retire/delete the old destination only after verifying backlogs and retention are handled, with owner approval and archival policy compliance.

**Renaming directly** in `@JmsListener` or environment variables does not automatically move messages sitting in the old Queue. With durable Topic subscriptions, changing Topic/subscription names can create a separate backlog stream. Treat migration as a contract change, not just a string refactor.

## 12. Retry, DLQ, delayed messages, and temporary destinations

Primary destination names should be clearly separated from operational destinations when required by the provider or architecture:

~~~text
prod.billing.invoice.issue.v1          (Main processing queue)
prod.billing.invoice.issue.v1.retry    (Retry queue, if design uses a separate queue)
prod.billing.invoice.issue.v1.dlq      (Dead-letter queue, if used)
~~~

This is **one naming convention option**, not a claim that the broker automatically creates `.retry` or `.dlq` from the main name. Many brokers use dead-letter addresses, redelivery delays, or a shared DLQ; names and mappings must match actual policy. On a broker with a 48-character name limit, check the longest name after appending suffixes; shorten in a controlled way and record aliases in the registry.

Do not create a separate Queue per retry count or per attempt when the broker already supports backoff/delivery counts. Bounding retry attempts, designing poison-message handling, and monitoring DLQs usually matter more than suffix style.

**TemporaryQueue/TemporaryTopic** are created dynamically for short-lived request/reply, with lifecycles tied to a connection. Do not mechanically apply long-term physical naming conventions to this destination type; log logical request IDs and traces instead of assuming temporary names are stable.

## 13. Multi-tenancy, data regions, and security policies

There are two options for tenant separation:

- **Dedicated destination per tenant**, e.g. `prod.eu.sales.order.created.v1` when each region/tenant has independent policies. This increases resource counts, ACLs, and quotas, and is only appropriate when genuine isolation is required.
- **Shared destination** with tenant ID in message properties/payload, enforcing authorization/isolation at the appropriate layers. In that case, users must not arbitrarily pick a Topic/Queue name purely from a tenant ID.

Do not embed tenant IDs, customer IDs, or personal data directly into physical names unless necessary, because names easily appear in metrics, logs, dashboards, and admin tools. Parameterizing destination names from API inputs requires allowlists/authorization; otherwise clients could create destinations outside allowed regions or send data to sensitive targets (depending on broker ACLs).

In a shared broker, environment/domain prefixes should be paired with **dedicated send/consume/manage permissions**. For instance, `billing-worker` may only consume `prod.billing.invoice.issue.v1`, `order-service` may only send, and `dev` services have no permissions on `prod` destinations. Enforce ACLs on the broker; never rely on name regexes as the sole security barrier.

## 14. Provisioning, testing, and observability

A destination contract should live in a configuration repository or IaC platform and be reviewed alongside code. Required broker resources can be provisioned before deploying a new application version. In tightly governed environments, consider disabling or restricting `auto-create` on the broker so a typo cannot silently spawn an "orphan" Queue.

Useful testing layers:

| Test | What to verify |
|---|---|
| **Naming and logic** | Regex/allowed environments, domain owner, version, length, and provider reserved names. |
| **Configuration** | Logical key values and broker endpoints match `dev`/`stg`/`prod`; missing critical config fails fast. |
| **Provisioning** | Physical Queue/Topic and routing type exist properly; subscription/DLQ/retention counts are accurate. |
| **Round-trip** | Publisher sends to the right destination, listener receives with proper Queue/Topic semantics. |
| **Isolation** | Dev credentials cannot send/consume from prod; tenant/region policies cannot be bypassed. |
| **Migration** | No messages stranded in old destination; duplicate deliveries handled safely. |
| **Monitoring** | Metrics by environment/domain/physical destination, backlog, redelivery, DLQ, subscription lag, and owner. |

For logs/tracing, record the **logical destination key**, physical name, broker alias, message ID/correlation ID, owning domain, and processing outcome where appropriate. Do not log credentials or full sensitive payloads. In metrics, watch label cardinality: if destination names contain ever-changing user IDs or pod IDs, monitoring systems can easily overload.

### Pre-deployment review checklist

- [ ] Name reflects **business meaning**, with Queue/Topic and owner clear.
- [ ] An environment isolation strategy is chosen: prefix, separate broker, or explicit namespace.
- [ ] Logical key, physical name, and subscription identity are clearly distinguished.
- [ ] Producer and consumer read the same contract from config/registry, without ad-hoc prefix concatenation.
- [ ] Character limits, reserved names, and provider routing rules are verified.
- [ ] Destinations and ACLs are provisioned in the right environment.
- [ ] Retry/DLQ/retention policies and auxiliary names (if used) are in place.
- [ ] Round-trip, authorization failure, migration, and rollback plan have been tested.
- [ ] Contract name changes have owner approval and a retirement schedule for the old destination.

## 15. Common mistakes

| Mistake | Consequences and fix |
|---|---|
| Using the name `orders` across all environments | Easy misrouting or hard authorization; separate namespaces, brokers, or environment prefixes. |
| Every service creates its own `order-created` Topic | Publisher becomes coupled to consumers; standardize event contracts under the domain owner. |
| Naming by pod, instance, or hostname | Creates unstable Queues/Topics and fragments backlogs/monitoring; name by business meaning, put instance in metrics/tags. |
| Hardcoding `prod...` directly in Java | Easy to run against the wrong environment; externalize physical names. |
| Assuming adding `.dlq` makes the broker auto-retry | Not guaranteed; must configure actual dead-letter/routing policies. |
| Changing `v1` to `v2` without migrating backlog | Old consumers miss draining messages; plan a cutover and monitor backlog. |
| Using the same physical string for Queue and Topic assuming equivalence | JMS destination types and routing differ; configure Queue/Topic explicitly. |
| Treating environment prefixes as an ACL mechanism | Credentials can still be over-privileged; verify broker authorization. |
| Creating names too long or with characters disallowed by provider | Provisioning/runtime failures; validate provider constraints early in CI. |
| Applying durable naming policies to TemporaryQueue | Wrong lifecycle; use request/reply dynamic destinations via the proper API. |

## 16. Self-check exercises

**Exercise 1.** The Sales team publishes an "order created" event. Both Billing and Notification need to receive it, and each team may scale replicas independently. Choose the destination type, name, and subscription naming approach.

**Suggested answer:** Use Topic `prod.sales.order.created.v1`; Billing and Notification each have **independent subscriptions** named by group/purpose, and each group can use a shared subscription so replicas split messages within the group. Do not create a separate Topic per replica.

**Exercise 2.** Dev and Prod share a broker. Dev accidentally sends to `prod.billing.invoice.issue.v1` despite code having prefix conventions. Why?

**Suggested answer:** A prefix is just a name; the app can still be misconfigured or have overly broad credentials. You need strict environment bindings, ACLs blocking dev from prod, deployment checks, and alerts on cross-environment routing.

**Exercise 3.** You change `app.messaging.destinations.invoice-issue` from `prod.billing.invoice.issue.v1` to `prod.billing.invoice.issue.v2`. What happens to messages remaining in Queue `v1`?

**Suggested answer:** They do not move automatically. They remain in Queue `v1` unless the broker has an explicit forwarding rule. You need a drain/bridge/cutover strategy, backlog monitoring, and keeping old consumers running long enough.

**Exercise 4.** A team creates `prod.billing.invoice.issue.v1.dlq`, yet after listener errors the DLQ stays empty. What does this prove?

**Suggested answer:** Having a name alone provides no routing/retry policy. Check transactions/acknowledgements, redelivery counts, dead-letter address settings, Queue bindings, and broker permissions.

**Exercise 5.** Why can a destination named `prod.sales.order.created.v1` still malfunction if sender code uses Queue while receiver code uses Topic?

**Suggested answer:** A name is just a string, whereas Queue/Topic defines routing semantics. Spring `pubSubDomain` and provider routing types must match; identical strings do not guarantee the same physical destination or consumer set.

## 17. Official references

- [Jakarta Messaging specification — Destinations, Queue, Topic, and subscriptions](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1).
- [Spring Framework — Using JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html).
- [Spring Framework — Annotation-driven JMS listeners](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html).
- [Spring Boot — Externalized Configuration and property placeholders](https://docs.spring.io/spring-boot/reference/features/external-config.html).
- [Spring Boot — JMS Artemis and ActiveMQ Classic](https://docs.spring.io/spring-boot/3.3/reference/messaging/jms.html).
- [Apache ActiveMQ Artemis — Address model, anycast/multicast, and FQQN](https://activemq.apache.org/components/artemis/documentation/latest/address-model.html).
- [IBM MQ — Naming restrictions for queues](https://www.ibm.com/docs/en/ibm-mq/9.4.x?topic=reference-naming-restrictions-queues).
- [IBM MQ — Rules for naming MQ objects](https://www.ibm.com/docs/en/ibm-mq/9.4.x?topic=objects-rules-naming-mq).
