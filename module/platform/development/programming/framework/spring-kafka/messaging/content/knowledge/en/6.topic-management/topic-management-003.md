# Topic Names and Naming Conventions

## Lesson Objectives

In the **Topic Management** chapter, this lesson defines how to choose clear, stable, and consistent Kafka topic names so producers, consumers, operations teams, and development teams share a common understanding of the messaging contract.

**SPRING_KAFKA_MESSAGING** focuses on building applications that send and receive Kafka events using Spring Kafka, `KafkaTemplate`, and `@KafkaListener`; while also helping learners understand topics, partitions, offsets, consumer groups, serialization, retries, dead-letter handling, transactions, exactly-once semantics, concurrency, and testing. A topic name is part of the contract between components in an event flow: a good name identifies the purpose of the data and reduces confusion as the system scales.

After this lesson, learners can:

- Understand the role of topic names in an event-driven architecture.
- Apply Kafka's character limits and topic naming rules.
- Establish naming conventions based on domain, entity, and event type.
- Distinguish topic names from consumer groups, partitions, schema versions, and environments.
- Identify anti-patterns such as overly generic names, database-table names, or names containing mutable implementation details.
- Integrate naming conventions into Spring Kafka configuration and topic governance workflows.

## 1. Why Do Topic Names Matter?

A topic is where Kafka stores records belonging to the same logical data stream. Producers write records to a topic; consumers belonging to consumer groups read records from the topic by partition and offset. A single topic can be consumed independently by multiple consumer groups.

Topic names commonly appear in:

- Producer and consumer source code.
- Topic creation, retention, partition, and replication configurations.
- ACLs and security policies.
- Dashboards, metrics, logs, and alerts.
- Event contract documentation and data catalogs.
- Operational, deployment, and dead-letter handling tools.

A name like **orders** may seem clear enough when the system is small. When more order streams appear—such as order created, paid, cancelled, shipped, and refunded—an overly generic name makes it hard for readers to know exactly what kind of data the topic holds.

By contrast, a name like **commerce.order.created** describes the business context, the entity, and the event. Development teams can identify the topic's purpose straight from its name without reading every producer's source code.

A topic name should be treated as part of the integration interface between systems. Renaming a topic can simultaneously impact producers, consumers, ACLs, dashboards, connectors, and operational procedures.

## 2. Technical Rules for Kafka Topic Names

Kafka enforces technical constraints on topic names. An organization's internal conventions must comply with these constraints before considering readability.

### 2.1. Allowed Characters

Kafka topic names use the following ASCII characters:

- Letters from **a** to **z** and **A** to **Z**.
- Digits from **0** to **9**.
- Dot **.**
- Underscore **_**.
- Hyphen **-**.

A topic name cannot be a single dot **.** or two dots **..**. The maximum length of a topic name is **249 characters**.

Valid examples:

~~~text
orders
orders.created
commerce.order.created
inventory-stock-reserved
payment_events
orders-v2
~~~

Invalid examples:

~~~text
order created
orders/created
orders:created
đơn-hàng-đã-tạo
.
..
~~~

Do not use spaces, **/**, **:**, accented Vietnamese characters, or characters outside the allowed set. Stick to ASCII names to avoid errors across shells, configuration files, monitoring tools, and integration systems.

### 2.2. Case Sensitivity

Topic names are case-sensitive. Therefore, **Orders.Created** and **orders.created** are two different names.

Even though Kafka allows uppercase letters, standardize on lowercase to reduce typos and prevent teams from accidentally creating two topics with the same meaning but different casing.

### 2.3. Avoid Mixing Dots and Underscores

Kafka allows both **.** and **_**, but topic names containing both separators can collide in certain JMX metric names because they are mapped to similar metric name forms.

For example, names like:

~~~text
orders.created
orders_created
~~~

can be difficult to distinguish in some metric systems. Therefore, choose a consistent separator convention. This lesson uses dots to separate business components and hyphens when multiple words need to be joined within a single component.

### 2.4. Avoid Prefixes Reserved for Internal Topics

Kafka uses internal topics whose names start with a double underscore, such as **__consumer_offsets** and **__transaction_state**.

Business applications should avoid the **__** prefix so they are not confused with Kafka-managed topics. You can enforce a rule forbidding names starting with **__** in your organization's topic creation tooling.

## 3. Recommended Naming Pattern

An extensible pattern for topics containing business events is:

~~~text
<domain>.<entity>.<event>
~~~

Where:

| Component | Meaning | Examples |
|---|---|---|
| domain | Bounded context or business domain owning the data | commerce, inventory, identity |
| entity | The entity or aggregate described by the event | order, payment, stock |
| event | The business event that occurred | created, authorized, reserved |

Examples:

~~~text
commerce.order.created
commerce.order.cancelled
commerce.payment.authorized
commerce.payment.refunded
inventory.stock.reserved
identity.customer.registered
~~~

This pattern is not a mandatory Kafka requirement. It is an architectural convention that helps topic names express business semantics and supports scaling across multiple development teams.

### 3.1. Naming by Domain

The domain should reflect the business domain or bounded context responsible for the event. Use short, stable terms agreed upon across the organization.

Examples:

- **commerce**: orders, payments, and commercial transactions.
- **inventory**: inventory stock and reservations.
- **shipping**: shipping and delivery.
- **identity**: accounts, identity, and authentication.

Avoid using department names or team names because organizational structures can change while event contracts need to endure long-term.

If an event is emitted by a technical service but belongs to another domain, name it according to the event's business semantics. For example, **order-service** emits **commerce.order.created**, rather than creating a name like **order-service-created**.

### 3.2. Naming by Entity or Aggregate

The entity tells readers which object the event describes. Prefer singular nouns when an event pertains to a single entity:

~~~text
commerce.order.created
commerce.payment.authorized
inventory.product.updated
~~~

Do not mix singular and plural arbitrarily. If an organization chooses plural nouns, apply it consistently across all domains. In the examples of this lesson, entities use the singular form.

Each database table does not necessarily correspond to one entity topic. An aggregate may emit multiple events; conversely, a single event may reflect a business change spanning multiple tables.

### 3.3. Naming by Event

The event should express something that has already happened, typically using past tense or a past participle in English:

- **created**
- **approved**
- **cancelled**
- **paid**
- **shipped**
- **reserved**
- **refunded**

Examples:

~~~text
commerce.order.created
commerce.order.approved
commerce.order.cancelled
commerce.payment.refunded
~~~

Event names should reflect meaningful business occurrences. Avoid overly technical names like **row-inserted**, **column-updated**, or **save-success** when consumers need to understand business state rather than database details.

### 3.4. Distinguishing Events from Commands

An event describes something that has happened; a command expresses a request for a component to perform an action.

| Meaning | Example Name | Interpretation |
|---|---|---|
| Event | commerce.order.created | An order has been created |
| Event | commerce.payment.authorized | A payment has been authorized |
| Command | commerce.order.create | Request to create an order |
| Command | commerce.payment.authorize | Request to authorize a payment |

Do not mix commands and events into the same topic if the two message types have different semantics, processing permissions, or retry policies. If the system uses Kafka for commands, define explicit naming and separate contracts for command streams.

## 4. Choosing the Level of Name Granularity

Topic names should be specific enough to distinguish data streams, yet you should not create a new topic for every minor variant that has no contractual or operational difference.

### 4.1. Avoid Overly Generic Names

| Unclear Name | Problem | More Specific Name |
|---|---|---|
| data | Unknown which domain the data belongs to | commerce.order.created |
| events | Mixes many different event types | inventory.stock.reserved |
| updates | Unclear which entity and what changed | identity.customer.updated |
| messages | Describes only the transport medium | shipping.delivery.dispatched |
| orders | May contain every order state | commerce.order.created or commerce.order.cancelled |

### 4.2. Avoid Overly Implementation-Specific Names

Do not embed details that easily change with source code or infrastructure into topic names:

~~~text
order-service-v2-instance-03-created
mysql-orders-table-cdc-prod
billing-worker-thread-4
~~~

Details such as instance names, threads, hosts, physical databases, or deployment names belong in metadata, configuration, or observability systems.

If a topic is genuinely a CDC stream, you can use a dedicated convention showing the data source and table, while clearly distinguishing CDC topics from business events. Example:

~~~text
cdc.sales.orders
~~~

Do not name a CDC stream as if it were a standardized business event when the payload merely mirrors database row changes.

### 4.3. Do Not Create Topics per Record or per User

Do not generate dynamic topic names based on order ID, customer ID, tenant ID, or timestamp:

~~~text
order-10001
order-10002
customer-9382-events
events-2026-11-17
~~~

This pattern causes uncontrolled growth in topic counts, putting pressure on metadata, the controller, ACLs, monitoring, and operations.

Instead, define one stable topic and use record keys, headers, or payload fields to distinguish individual entities:

~~~text
Topic: commerce.order.created
Key:   order-10001
Value: {"orderId":"order-10001","status":"CREATED"}
~~~

If data needs to be segmented by tenant, evaluate keys, partitioning, authorization, and isolation policies. Do not use a separate topic per tenant unless there is a genuine isolation or operational requirement.

## 5. Topic Names and Concepts Not to Confuse Them With

A topic name only identifies a logical data stream. It does not replace other Kafka configurations and identifiers.

| Concept | Role | Example |
|---|---|---|
| Topic | Data stream stored in Kafka | commerce.order.created |
| Record key | Routes and identifies groups of related records | order-10001 |
| Partition | Unit of storage and parallelism within a topic | Partition 0, 1, 2 |
| Consumer group | Group of consumers sharing reading of a topic | billing-service |
| Offset | Position of a record within a partition | Offset 125 |
| Schema version | Version of the data structure contract | Schema version 3 |
| Environment | Deployment environment | dev, staging, prod |
| Replication factor | Number of replicas of each partition | 3 |

For example, **commerce.order.created** is the topic name; **order-10001** may be the record key; **billing-service** is a consumer group. Do not concatenate all of this information into a single topic name.

### 5.1. Topic Names Do Not Determine Partitions

A topic name does not dictate the partition count or how keys are distributed. Those attributes are configured when creating the topic and when producers send records.

Example:

~~~text
Topic: commerce.order.created
Partitions: 6
Key strategy: orderId
Replication factor: 3
~~~

The topic name remains stable even when the partition count changes under a scaling plan. However, increasing partitions can affect key-to-partition mapping and ordering among records with the same key when the default partitioner is used. That is an operational decision requiring separate evaluation.

### 5.2. Topic Names Do Not Replace Consumer Groups

A single topic can be read independently by multiple consumer groups:

~~~text
Topic: commerce.order.created

Consumer groups:
- billing-service
- analytics-service
- notification-service
~~~

Do not create topics like **commerce.order.created.billing** or **commerce.order.created.analytics** just so each application has its own reading stream. Consumer groups already solve independent consumption in the standard Kafka model.

### 5.3. Topic Names Do Not Replace Schema Versions

Schema versions normally belong in a schema registry, headers, or data contract metadata. Do not append a version number to every topic name when structural changes remain compatible.

Only consider a new versioned topic when an incompatible semantic or contract change requires producers and consumers to use a separate stream during a transition period.

## 6. Environment and Deployment Region Conventions

There are two common ways to organize environments.

### 6.1. Separate Cluster per Environment

If development, staging, and production run on independent Kafka clusters, you can keep the exact same topic names across all environments:

~~~text
dev cluster:     commerce.order.created
staging cluster: commerce.order.created
production:      commerce.order.created
~~~

This approach avoids changing topic names in application code and documentation per environment. Bootstrap servers and secrets are configured per deployment.

### 6.2. Multiple Environments Sharing One Cluster

If an organization must share a single cluster, you can add an environment prefix:

~~~text
dev.commerce.order.created
staging.commerce.order.created
prod.commerce.order.created
~~~

When choosing this approach, apply it consistently to all related topics, including retry, DLT, and integration topics. ACLs and topic creation workflows must validate prefixes so applications in one environment do not accidentally access another environment's data.

Do not add environment prefixes merely out of habit if clusters are already isolated. Redundant prefixes lengthen names and tie logical contracts to deployment topology.

### 6.3. Region or Data Zone

Only include a region in the topic name when a single cluster genuinely holds multiple regional data streams and consumers must distinguish them by topic. If region is merely deployment metadata, keep it in configuration or headers/metadata.

Potential examples:

~~~text
apac.commerce.order.created
eu.commerce.order.created
~~~

This decision must align with data residency policies, cross-region replication, and access permissions. Do not add a region if it carries no meaning in the data contract.

## 7. Versioning and Changing Topic Names

Topic names are often referenced across source code and configurations of multiple services. Kafka does not provide a direct topic-rename operation like renaming a file. When you need to change a name or split a contract, the safe approach is typically to create a new topic and perform a controlled migration.

### 7.1. When a New Topic Version Is Not Needed

If payload changes remain compatible with existing consumers, prefer schema evolution:

- Add optional fields with appropriate defaults.
- Preserve the meaning of existing fields.
- Do not change field data types in ways that break old consumers.
- Check schema registry compatibility rules if one is in use.

For example, adding **currency** to an event can remain compatible if older consumers ignore unknown fields and the contract clearly specifies a default value.

### 7.2. When to Create a New Topic

Consider a new topic when:

- The meaning of the event changes significantly.
- The new payload is incompatible with existing consumers.
- You need to transition to different partitioning or retention that cannot be safely changed in place.
- You want to separate streams with different access permissions or data lifecycles.
- You need a phased migration so multiple consumers can switch independently.

Example:

~~~text
commerce.order.created
commerce.order.created.v2
~~~

Only use a version suffix when there is a contractual reason. Do not bump the version just because a new version of the application is released.

### 7.3. Topic Migration Procedure

A migration procedure can include:

1. Identify differences between the old topic and the new topic.
2. Declare the event contract, owner, key, schema, and storage policy for the new topic.
3. Create the new topic with appropriate partitions, replication, and retention.
4. Update producers to emit events according to the chosen transition strategy.
5. Update consumers, test data handling, and verify no unexpected drops or duplicate processing.
6. Monitor lag, errors, and consumption rates on the new topic.
7. Move all consumers over to the new topic.
8. Stop the old producer flow, wait for retention expiration, and handle any replay requirements.
9. Decommission the old topic according to governance policies and agreed timelines.

During dual-publish phases, both topics may contain the same event. Consumers need idempotency or deduplication mechanisms if they might read from both streams.

## 8. Conventions for Retry Topics and Dead-Letter Topics

Retry and dead-letter topics are normally tied to an original business topic. Name them so operators can immediately recognize the source topic and processing purpose.

Some patterns you can choose:

~~~text
commerce.order.created.retry
commerce.order.created.dlt
~~~

Or if there are multiple retry tiers:

~~~text
commerce.order.created.retry.1
commerce.order.created.retry.2
commerce.order.created.dlt
~~~

These are example conventions; Spring Kafka may generate retry topics according to the selected configuration and naming strategy. Verify the actual names the application creates, especially when using `@RetryableTopic`.

Guidelines:

- Keep the original topic name inside retry/DLT names for traceability.
- Use the same suffix and component ordering across the entire system.
- Do not confuse retry topics with new business events.
- Set retention and access permissions appropriate for error data.
- Monitor the number of records entering the DLT and identify the owner responsible for recovery.
- Avoid generating retry topics by repeatedly appending suffixes across retry attempts.

Kafka-managed internal topics such as **__consumer_offsets** are not application DLTs and should not be treated as business topics.

## 9. Naming Conventions in Spring Kafka Source Code

To reduce typos in topic names, applications should centralize topic names in a controlled location, such as configuration properties or a constants class.

### 9.1. Using Constants in the Application

~~~java
public final class KafkaTopics {

    private KafkaTopics() {
    }

    public static final String ORDER_CREATED =
        "commerce.order.created";

    public static final String PAYMENT_AUTHORIZED =
        "commerce.payment.authorized";
}
~~~

Producer:

~~~java
@Service
public class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderEventPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(OrderCreated event) {
        kafkaTemplate.send(
            KafkaTopics.ORDER_CREATED,
            event.orderId(),
            event
        );
    }
}
~~~

Consumer:

~~~java
@Service
public class OrderEventListener {

    @KafkaListener(
        topics = KafkaTopics.ORDER_CREATED,
        groupId = "billing-service"
    )
    public void receive(OrderCreated event) {
        // Process order event.
    }
}
~~~

Constants prevent producers and consumers within the same application from using two different strings. Across multiple independent applications, maintain contracts via documentation, a schema registry, or versioned shared artifacts; avoid forcing every service to import the same Java class.

### 9.2. Using Externalized Configuration

If topic names vary by environment or deployment, place them in configuration:

~~~yaml
app:
  kafka:
    topics:
      order-created: commerce.order.created
      payment-authorized: commerce.payment.authorized
~~~

Inject the value into the listener:

~~~java
@KafkaListener(
    topics = "${app.kafka.topics.order-created}",
    groupId = "billing-service"
)
public void receive(OrderCreated event) {
    // Process event.
}
~~~

Externalized configuration is useful when environment prefixes are needed or endpoints vary by deployment. Verify the resolved value on application startup and confirm the topic exists according to your topic creation policy.

### 9.3. Declaring Topics with NewTopic

Applications can declare topics to create via `KafkaAdmin` and `NewTopic` beans:

~~~java
@Configuration
public class TopicConfiguration {

    @Bean
    public NewTopic orderCreatedTopic() {
        return TopicBuilder.name(KafkaTopics.ORDER_CREATED)
            .partitions(6)
            .replicas(3)
            .build();
    }
}
~~~

This example assumes the cluster has enough brokers to place three replicas. In a single-broker development environment, use a replication factor of 1.

The topic name in the bean must follow the same naming convention as producers, consumers, and contract documentation. If the topic already exists, declaring the bean does not mean all existing attributes will automatically be updated as desired; changing partitions or topic configs must follow governance policies and Kafka's capabilities.

## 10. Complete Convention Example for a Domain

Suppose an e-commerce system has the bounded contexts Commerce, Inventory, Payment, and Shipping.

| Domain | Topic | Meaning |
|---|---|---|
| Commerce | commerce.order.created | Order created |
| Commerce | commerce.order.cancelled | Order cancelled |
| Commerce | commerce.order.completed | Order completed |
| Commerce | commerce.payment.authorized | Payment authorized |
| Commerce | commerce.payment.captured | Payment captured |
| Commerce | commerce.payment.refunded | Amount refunded |
| Inventory | inventory.stock.reserved | Stock reserved |
| Inventory | inventory.stock.released | Stock released |
| Shipping | shipping.delivery.dispatched | Delivery handed over for shipping |
| Shipping | shipping.delivery.delivered | Goods delivered |

Several consumer groups can consume these topics:

| Consumer group | Topics of Interest | Purpose |
|---|---|---|
| billing-service | commerce.order.created, commerce.payment.captured | Generate and reconcile invoices |
| inventory-service | commerce.order.created, commerce.order.cancelled | Reserve or release stock |
| notification-service | Order, payment, and delivery topics | Send notifications |
| analytics-service | Multiple business topics | Aggregate analytical data |

Topics reflect event types; consumer groups reflect groups of applications sharing consumption progress. By separating these two concepts, a single event can serve many needs without producers creating separate topics per consumer.

## 11. Anti-Patterns to Avoid

| Anti-pattern | Example | Issue |
|---|---|---|
| Overly generic name | data, events, messages | Does not express domain or event |
| Named after service | order-service-events | Couples contract to deployment service name |
| Named after database | orders_table_changes | Confuses CDC with business events |
| Dynamic name per entity ID | order-10001 | Creates too many topics |
| Inconsistent environment naming | dev.orders, orders.prod, staging-orders | Hard to automate and govern |
| Mixing separators | commerce_order.created | Prone to confusion and metric collisions |
| Arbitrary uppercase | Commerce.Order.Created | Easy to create duplicate topics differing only by case |
| Versioning without reason | order.v3, order.v4, order.v5 | Increases migration and consumer management cost |
| Command name used for event | create-order | Does not express an event that already happened |
| Using internal prefix | __commerce.order.created | Easily confused with Kafka internal topics |

## 12. Governing and Enforcing Naming Conventions

A convention is only useful when applied consistently. An organization should maintain a topic catalog and an approval workflow for creating topics.

Each topic should have minimum governance metadata:

| Metadata | Content |
|---|---|
| Topic name | Official topic name |
| Domain owner | Team responsible for the event |
| Purpose | Short description of purpose and semantics |
| Producer | Applications authorized to publish |
| Consumer groups | Groups currently consuming |
| Key strategy | Rule for selecting the record key |
| Partition count | Planned number of partitions |
| Replication factor | Number of replicas |
| Retention | Retention duration or storage size |
| Schema/contract | Location and version of the data contract |
| Data classification | Data sensitivity level |
| Retry/DLT | Related topics and error handling workflow |
| Lifecycle | Status: active, deprecated, or retired |

### 12.1. New Topic Creation Workflow

Before creating a topic:

1. Identify the domain owner and producer responsible for emitting the event.
2. Write a description of the event, when it is emitted, and the payload meaning.
3. Choose a name following the agreed pattern.
4. Check character limits and duplicate-meaning names in the catalog.
5. Define key, partitions, retention, and replication.
6. Define schema compatibility and data classification.
7. Identify expected consumer groups, retry, and DLT if needed.
8. Register the topic in the catalog and apply ACLs.
9. Create the topic via the agreed governance or deployment workflow.

### 12.2. Automated Name Validation

Validation rules can be built into CI or topic creation tools:

- Name does not exceed 249 characters.
- Contains only ASCII letters, digits, dots, underscores, or hyphens.
- Not equal to **.** or **..**.
- Does not start with **__**.
- Uses lowercase per convention.
- Does not mix dots and underscores.
- Contains all required domain, entity, and event segments.
- Does not duplicate an already registered name or an equivalent name.

Regex can assist with syntax checking, but cannot validate domain semantics. Catalog review still requires business owners or an architecture group.

A preliminary validation expression for a lowercase, dot-separated convention:

~~~regex
^[a-z0-9-]+(\.[a-z0-9-]+)+$
~~~

This regex is an illustrative internal rule, not a complete regex describing all valid Kafka topic names. After regex validation, you still need to check length, special names, internal prefixes, and the catalog.

## 13. Topic Naming Checklist

Before creating a topic, ask yourself:

- [ ] Does the name accurately express the domain or bounded context?
- [ ] Are entity and event clearly separated?
- [ ] Does the event name express something that already happened rather than a technical operation?
- [ ] Does the name use only Kafka-allowed characters and stay within 249 characters?
- [ ] Does the name use lowercase and a consistent separator?
- [ ] Does the name avoid the **__** prefix reserved for Kafka internal topics?
- [ ] Does the name avoid order IDs, tenant IDs, timestamps, or instance IDs?
- [ ] Is the name independent of service names, database tables, and frameworks?
- [ ] Is an environment prefix actually needed, or are clusters already separated?
- [ ] Is there a clear reason if a version is included in the name?
- [ ] Are the topic's owner, purpose, key, retention, and schema documented?
- [ ] Do retry and DLT topics follow a consistent convention with the source topic?
- [ ] Do producers, consumers, ACLs, and the catalog use the exact same name?

## Conclusion

A topic name is part of the integration contract among producers, consumers, and operations systems. A good convention typically expresses domain, entity, and event; uses valid characters, lowercase, and a consistent separator; and avoids dynamic names, overly generic names, implementation details, and prefixes reserved for internal topics.

By combining naming conventions with a catalog, owners, schemas, partitions, retention, and ACLs, an organization can manage event streams more clearly as the number of topics and consumer groups grows. Spring Kafka uses these topic names across `KafkaTemplate`, `@KafkaListener`, and topic management configurations; agreeing on names upfront helps components communicate reliably and operate smoothly.
