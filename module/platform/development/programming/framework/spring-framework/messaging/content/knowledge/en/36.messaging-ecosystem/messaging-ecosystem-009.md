# Boundaries Between Framework Knowledge and External Product Configuration

When learning Spring Messaging, it is easy to mix up three types of knowledge: APIs provided by Spring Framework, capabilities added by another Spring project, and configuration belonging to a broker or external product. They often appear together in one application, yet have different owners, version lifecycles, and testing approaches.

For example, an application might use Spring Messaging to build a message, Spring for Apache Kafka to send the message to Kafka, Spring Boot to auto-configure the producer, and the Kafka broker to store messages according to a retention policy. All four components participate in one processing flow, yet not every property or behavior in that flow can be treated as a Spring Framework feature.

This lesson helps define the right boundaries, choose the right documentation, and know which parts must be tested at the Framework, adapter, runtime, or external product level.

## 1. Four common layers of knowledge

A messaging application can generally be viewed across four layers:

1. **Spring Framework:** foundational abstractions and APIs such as Message, MessageHeaders, MessageChannel, MessageHandler, MessageConverter, WebSocket/STOMP, RSocket, and JMS integration.
2. **Extended Spring projects:** projects built on top of the Framework to provide integration flows, broker adapters, binders, or specialized capabilities.
3. **Spring Boot and application configuration:** auto-configuration, externalized configuration, property binding, starters, and dependency management.
4. **External products/runtimes:** Kafka, RabbitMQ, ActiveMQ, Artemis, cloud brokers, schema registries, proxies, load balancers, Kubernetes, and storage systems.

These layers cooperate with one another but do not replace one another. Spring Framework defines application-level APIs and integrations; extended Spring projects supply adapters or additional abstractions; Boot reduces configuration boilerplate; external products enforce semantics and manage their own resources.

## 2. What belongs to Spring Framework

Spring Framework provides shared messaging abstractions so applications do not have to redefine message structures and data conversion everywhere.

Key components include:

- **Message and MessageHeaders:** represent payload and metadata.
- **MessageBuilder:** builds messages and sets headers.
- **MessageChannel:** abstraction for sending messages to a channel.
- **MessageHandler:** abstraction for processing messages.
- **MessageConverter:** converts payloads between objects and suitable data formats.
- **MessageHeaderAccessor:** reads and manipulates headers through a controlled API.
- **Spring WebSocket/STOMP:** supports messaging over WebSocket, destination mapping, and broker integration.
- **RSocket integration:** supports requesters, responders, routes, and codec strategies.
- **JMS integration:** provides components such as JmsTemplate and listener containers via the Spring JMS module.

Example snippet using only Spring Messaging abstractions:

~~~java
Message<String> message = MessageBuilder
    .withPayload("order submitted")
    .setHeader("correlationId", "corr-100")
    .build();

MessageChannel channel = obtainChannel();
boolean accepted = channel.send(message);
~~~

This snippet illustrates the message contract and sending via a channel. It does not yet reveal whether the channel is wired to Kafka, RabbitMQ, JMS, an internal executor, or another adapter. The concrete implementation lives in the integration layer.

Spring Framework documentation is appropriate for answering questions such as:

- How do Message payload and headers work?
- Are headers immutable?
- What roles do MessageChannel and MessageHandler play?
- Where is MessageConverter invoked?
- How does Spring map STOMP destinations to handlers?
- How are RSocket routes declared and invoked?
- How are JmsTemplate and listener containers used?

Do not use Framework documentation to infer a configuration property specific to Kafka or RabbitMQ.

## 3. What belongs to extended Spring projects

Several common messaging capabilities live in separate Spring projects, even though they build on Spring Framework abstractions.

| Project | Primary scope | Knowledge examples |
|---|---|---|
| Spring Integration | Enterprise Integration Patterns and integration flows | channel adapters, routers, transformers, filters, aggregators |
| Spring for Apache Kafka | Integrating Spring applications with Apache Kafka | KafkaTemplate, listener containers, retry topics, transactions |
| Spring AMQP / Spring for RabbitMQ | Integrating Spring with AMQP and RabbitMQ | RabbitTemplate, listener containers, exchanges, bindings |
| Spring Cloud Stream | Abstraction for event-driven microservices via binders | function bindings, consumer groups, partitions, binders |
| Spring Batch | Batch processing and jobs | chunks, readers, writers, retry/skip in batch steps |

These projects may share Message, MessageChannel, or other abstractions, yet their APIs and configurations do not automatically become core Spring Framework APIs.

Examples:

- **KafkaTemplate** belongs to Spring for Apache Kafka.
- **RabbitTemplate** belongs to Spring AMQP.
- **IntegrationFlow** and the integration flow DSL belong to Spring Integration.
- **Function bindings** and binder configuration belong to Spring Cloud Stream.
- **JmsTemplate** belongs to the Spring JMS module of Spring Framework.

When looking up a class or property, verify the actual artifact and package. A name starting with Spring is not enough to conclude it belongs to Spring Framework core.

## 4. Distinguishing Spring Framework from Spring Boot

Spring Boot is the layer that helps build and run Spring applications. Boot provides auto-configuration, starters, externalized configuration, and property binding mechanisms.

For example, the following properties typically belong to Spring Boot auto-configuration when the matching starter is present:

~~~properties
spring.kafka.bootstrap-servers=localhost:9092
spring.kafka.consumer.group-id=orders-service
spring.rabbitmq.host=localhost
spring.rabbitmq.port=5672
~~~

These are not general configuration APIs of Spring Framework. If an application does not use Spring Boot, these properties have no automatic meaning; the application must declare beans and configure clients or adapters itself.

Several components to distinguish:

- **Spring Framework Environment:** abstraction for accessing property sources and profiles.
- **Spring Boot Config Data:** Boot's mechanism for loading configuration from application.properties, application.yaml, profiles, and other config sources.
- **Spring Boot auto-configuration:** automatically creates beans when dependencies and conditions match.
- **Starter:** a convenient dependency bundle, not a runtime broker.
- **Externalized configuration:** moving environment-specific config out of code; exact loading and binding depend on Framework, Boot, and integration libraries.

When writing documentation, specify which prefix a property belongs to and which dependency it requires. Do not call every property starting with `spring` a Spring Framework property.

## 5. Which parts belong to the external product?

The broker or external product determines many behaviors that the Framework only configures or invokes through a client.

For example, with Kafka:

- Topics, partitions, and replication factors.
- Retention time and retention size.
- Consumer group coordination.
- Broker-side quotas.
- Log compaction.
- Replication and leader election.
- ACLs and broker security mechanisms.
- Record sizes and broker request limits.

With RabbitMQ:

- Exchanges, queues, and bindings.
- Queue durability and message persistence.
- Prefetch/QoS and acknowledgements.
- Dead-letter exchanges.
- TTL, maximum queue length, and overflow behavior.
- Quorum queues or streams.
- Users, vhosts, permissions, and policies.

With other brokers, concepts and configuration names may differ. Do not copy a property name from one broker to another merely because both support messaging.

A Spring adapter can expose an API to configure or use a feature, yet final semantics are still governed by broker version, client library, protocol, and deployment configuration.

## 6. Example classifying a Kafka flow

Suppose a service receives an order creation command, executes business logic, and emits an OrderCreated event.

| Component | Owner | Responsibility |
|---|---|---|
| Message payload and headers | Spring Messaging / application | Represents data and metadata |
| KafkaTemplate | Spring for Apache Kafka | Sends records to Kafka |
| Kafka producer client | Apache Kafka client | Executes protocol communication with broker |
| Bootstrap servers | Application config / Boot | Points client to brokers to connect to |
| Topic and partitions | Kafka cluster | Stores and distributes records |
| Retention policy | Kafka broker | Decides how long or how much data to retain |
| Auto-configuration | Spring Boot | Creates beans based on dependencies and properties |
| Business event schema | Application / schema governance | Defines event structure and meaning |

Example code sending an event via Spring for Apache Kafka:

~~~java
@Service
class OrderEventPublisher {

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    OrderEventPublisher(
            KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    CompletableFuture<SendResult<String, OrderCreatedEvent>> publish(
            OrderCreatedEvent event) {
        return kafkaTemplate.send(
            "orders.created.v1",
            event.orderId(),
            event
        );
    }
}
~~~

This snippet uses the Spring for Apache Kafka API. It does not automatically create the topic, set the retention policy, or guarantee the schema is registered in a schema registry. Those parts must be managed at the proper layer.

If the application uses Spring Boot, Boot can auto-configure KafkaTemplate from properties and dependencies. If not using Boot, the application must configure the producer factory and template using Java config or an equivalent mechanism.

## 7. Example classifying a RabbitMQ flow

With RabbitMQ, an application can use Spring AMQP to send messages:

~~~java
@Service
class BillingPublisher {

    private final RabbitTemplate rabbitTemplate;

    BillingPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    void publish(PaymentCaptured event) {
        rabbitTemplate.convertAndSend(
            "billing.events",
            "payment.captured",
            event
        );
    }
}
~~~

In this example:

- RabbitTemplate belongs to Spring AMQP.
- Exchange and routing key are used in the AMQP model.
- Exchanges, queues, and bindings must exist or be declared through an appropriate provisioning mechanism.
- Durability, acknowledgements, dead-lettering, and TTL depend on queue, broker, and listener configuration.
- The event object is converted by the configured message converter.

You cannot infer from calling convertAndSend that the message was successfully processed by a consumer. Sending, broker acknowledgement, consumer receipt, and business commit are distinct milestones. Tests and metrics must distinguish those milestones.

## 8. Example classifying STOMP and RSocket in Spring Framework

STOMP and RSocket are two integrations included in Spring Framework, yet their semantics and configuration differ.

### STOMP over WebSocket

Spring WebSocket supports application destination prefixes and broker destination prefixes:

~~~java
@Configuration
@EnableWebSocketMessageBroker
class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

The application prefix routes messages to controllers; the broker prefix routes messages to the configured broker. If using the simple broker, its capabilities differ from a dedicated broker or broker relay.

Configuring STOMP destination mappings belongs to Spring Framework WebSocket support. However, external broker setup, access permissions, queue policies, persistence, or cluster topology belong to the corresponding broker product.

### RSocket

Spring Framework provides requester and responder APIs:

~~~java
@Controller
class StatusController {

    @MessageMapping("system.status")
    Mono<ServerStatus> status() {
        return Mono.just(new ServerStatus("UP"));
    }
}
~~~

The `system.status` route is handled by the responder. RSocket has interaction models such as Request-Response, Request-Stream, Fire-and-Forget, and Channel. Codecs, data MIME types, and metadata MIME types are also important parts of the contract.

If an RSocket server runs behind a load balancer, proxy, or service mesh, infrastructure settings for TLS, idle timeouts, connection draining, and routing can affect connections. Those parameters are not automatically properties of @MessageMapping or RSocketRequester.

## 9. Asking the right questions to find the right docs

When encountering a messaging issue, first identify which layer owns the behavior you are looking for.

| Question | Where to look first |
|---|---|
| Are MessageHeaders immutable? | Spring Framework API |
| What does MessageChannel.send return? | Spring Framework API |
| How is a STOMP handler mapped from a destination? | Spring Framework WebSocket/STOMP |
| How does RSocketRequester establish a connection? | Spring Framework RSocket and RSocket Java |
| How does KafkaTemplate send a record? | Spring for Apache Kafka |
| How are spring.kafka.consumer.* properties bound? | Spring Boot Kafka auto-configuration |
| How does consumer group rebalancing work? | Apache Kafka documentation |
| How do Rabbit queues handle TTL and dead-lettering? | RabbitMQ documentation and Spring AMQP adapter |
| Which broker is a function bound to? | Spring Cloud Stream documentation |
| How are pods scaled and secrets mounted? | Kubernetes or deployment platform |

If the answer spans multiple layers, read documentation for each layer and state the boundaries explicitly. For instance, Spring Kafka shows how to declare a listener, while Kafka documentation is the authoritative source for the consumer group protocol and broker configuration.

## 10. Classifying configuration by ownership

Every configuration setting should be documented with its owner, scope, and where it takes effect.

| Config group | Example | Primary owner |
|---|---|---|
| Messaging abstraction | Message headers, channels, converters | Spring Framework |
| Transport integration | STOMP endpoints, RSocket routes, JMS listeners | Spring Framework or matching adapter |
| Adapter/client | KafkaTemplate, RabbitTemplate, listener factories | Extended Spring integration project |
| Application binding | spring.kafka.*, spring.rabbitmq.* | Spring Boot when using auto-configuration |
| Client runtime | Kafka producer acks, client retries, serializers | Client library and application config |
| Broker runtime | Kafka retention, Rabbit queue policies | Broker product |
| Deployment | DNS, ports, TLS secrets, replicas, resource limits | Deployment platform |
| Business contract | Event names, schemas, compatibility rules | Application and governance process |

Do not place secrets, passwords, or tokens into public documentation or examples committed to repositories. Describe environment variable names or secret references and specify how they are provisioned at runtime.

A property may be declared in the application yet interpreted by the client library. Another value may be stored in the broker and enforced by the broker. Documentation should state clearly where the value is read and where the behavior is actually enforced.

## 11. Version management and compatibility

A messaging application typically involves multiple independent versions:

- Spring Framework.
- Spring Boot.
- Integration projects such as Spring Kafka or Spring AMQP.
- Kafka client or RabbitMQ Java client.
- Broker server.
- Protocols or serializers.
- Schema registry and schema formats.

Do not upgrade one component without checking compatibility with the remaining components. Spring Boot manages dependency versions through dependency management/BOM when used properly; if overriding dependencies, check compatibility matrices and release notes.

When writing deployment documentation, record:

1. Java version.
2. Spring Boot version if applicable.
3. Actual Spring Framework version.
4. Spring integration project version.
5. Client library version.
6. Broker server version.
7. Protocol or schema format version when relevant.

Do not label an example as "current API" without specifying the version. Builder APIs, packages, converter names, and properties can change across releases.

For message schemas, versioning must be managed independently of framework versions. Upgrading Spring does not necessarily change business schemas; conversely, a schema may need a new version even when the framework does not change.

## 12. Testing by layer

A test covering only one layer does not prove the entire messaging flow works. Split tests by scope and the question they answer.

### Unit tests for logic and abstractions

Use unit tests to verify:

- Building messages with payloads and headers.
- Mapping domain objects to event DTOs.
- Message validation.
- Idempotency handling logic.
- Route or destination naming rules.
- Publisher-level error handling and retry policies.

You do not need a real broker to test a pure DTO mapping function or a naming policy.

### Spring context tests for wiring

Use context tests to verify:

- Required beans are created.
- Message converters are properly configured.
- Handler mappings are registered.
- Properties bind properly to beans.
- Conditional auto-configuration activates as expected.

If a test uses Spring Boot, explicitly state it is a Boot context test. Do not conclude that a Boot property is a Spring Framework feature merely because the test context starts successfully.

### Adapter integration tests

Test adapters with their corresponding dependencies:

- Spring Kafka with a Kafka broker.
- Spring AMQP with RabbitMQ.
- Spring JMS with a JMS provider.
- Spring Integration with the adapters/transports in use.
- Spring STOMP with the simple broker or an external broker relay.
- RSocket requester/responder over a real transport.

These tests verify mapping, serialization, acknowledgements, routing, and lifecycles across the integration boundary.

### Broker and deployment tests

A production-like environment is needed to test:

- Partitioning/replication or queue durability.
- Broker restarts and failover.
- Authentication, TLS, and ACLs.
- Consumer group rebalancing.
- Prefetch, retries, and dead-letter policies.
- Network timeouts, proxies, and connection draining.
- Load, throughput, and resource limits.

Testcontainers can launch real products in automated tests when suitable modules exist. However, a single broker container does not fully simulate clusters, replication, cloud IAM, or production network topologies.

## 13. Testing configuration without testing another product

Configuration should be verified where it is consumed:

- Boot property binding: check beans after binding.
- Kafka client properties: check producer/consumer factory configuration and broker integration.
- Kafka broker properties: check the cluster or broker environment, not just the Spring ApplicationContext.
- Rabbit queue arguments: check RabbitMQ declarations and runtime behavior.
- Kubernetes resource limits: check manifests or the cluster, not just Java unit tests.
- Secrets: verify secret injection in a safe test environment without hardcoding real values.

Example context test verifying Boot binds the consumer group:

~~~java
@SpringBootTest(properties = {
    "spring.kafka.consumer.group-id=orders-test"
})
class KafkaPropertiesTest {

    @Autowired
    KafkaProperties properties;

    @Test
    void shouldBindConsumerGroup() {
        assertEquals(
            "orders-test",
            properties.getConsumer().getGroupId()
        );
    }
}
~~~

This test verifies the property binds into Boot configuration. It does not prove the broker has the topic, the consumer group joined successfully, or ACL permissions are correct. Those require integration tests or deployment environment checks.

## 14. How to write documentation without mixing layers

A good README or runbook should separate content by scope:

1. **Framework concepts:** explain stable abstractions and APIs.
2. **Spring project integration:** list modules/dependencies and adapter APIs.
3. **Boot setup:** list starters, property prefixes, and auto-configuration conditions.
4. **External product setup:** record broker versions, topics/queues, policies, security, and runtime configuration.
5. **Deployment:** record networking, secrets, resources, replicas, and health checks.
6. **Testing:** state which tests verify each layer and which require real environments.

Every configuration example should note:

- Does the property belong to Spring Boot or the client library?
- Is the value read at startup or runtime?
- Does it configure the application, client, or broker?
- Is an application or broker restart required to apply it?
- Does it change message semantics or only resources?
- Which version was verified?

When a feature is exposed by an adapter yet enforced by the broker, describe both sides. For example, Spring AMQP can declare queue arguments, while TTL and dead-letter behavior are enforced by RabbitMQ.

## 15. Common classification mistakes

| Confusion | Why it is wrong | Correct classification |
|---|---|---|
| Calling KafkaTemplate a core Spring Framework API | The class belongs to Spring for Apache Kafka | State the project and dependency explicitly |
| Calling spring.kafka.* a Framework property | The prefix belongs to Boot auto-configuration | State the Spring Boot requirement explicitly |
| Assuming Spring Messaging provides a broker itself | Framework provides abstractions and integrations | Specify the actual broker or transport |
| Assuming `/topic` in the simple broker is a durable queue | Prefixes do not create dedicated broker semantics | Inspect the broker and configuration |
| Assuming sending a message means the consumer committed | Send, broker ack, and business commit are separate milestones | Test each milestone |
| Using a context test to prove Kafka retention | Retention is managed by the broker | Test the broker or cluster |
| Using one config for every broker | Properties and semantics are not uniform | Consult product-specific documentation |
| Upgrading Spring while ignoring client/broker compatibility | Components have independent versions | Check BOM and compatibility matrices |
| Putting secrets into sample application.yaml | Risks credential leaks | Use secret references or environment variables |
| Calling everything starting with Spring "Framework core" | The ecosystem contains many independent projects | Check packages, artifacts, and documentation |

## 16. Pre-publication or pre-deployment checklist

- [ ] Identified whether APIs belong to Spring Framework or an extended Spring project.
- [ ] Explicitly stated whether Spring Boot is used.
- [ ] Every property has a clearly identified owner and enforcement point.
- [ ] Distinguished application, client, broker, and deployment configuration.
- [ ] Broker/product versions are recorded alongside related configuration.
- [ ] Not treating one broker's properties as universal across all brokers.
- [ ] APIs and code examples match dependency versions.
- [ ] Business schemas are managed independently of framework versions.
- [ ] Unit tests, context tests, adapter integration tests, and broker tests have clear scopes.
- [ ] No claims about broker behavior based solely on Spring context startup succeeding.
- [ ] Secrets and credentials are not written into source or logs.
- [ ] Release notes and compatibility matrices are documented for coordinated components.

## 17. References

- [Spring Framework Reference](https://docs.spring.io/spring-framework/reference/) — official abstractions and integrations of Spring Framework.
- [Spring Messaging](https://docs.spring.io/spring-framework/reference/integration.html) — messaging abstractions and integrations inside the Framework.
- [Spring Boot Reference](https://docs.spring.io/spring-boot/reference/) — auto-configuration, externalized configuration, properties, and starters.
- [Spring Integration Reference](https://docs.spring.io/spring-integration/reference/) — integration flows, channel adapters, and Enterprise Integration Patterns.
- [Spring for Apache Kafka Reference](https://docs.spring.io/spring-kafka/reference/) — KafkaTemplate, listener containers, producers/consumers, and transactions.
- [Spring AMQP Reference](https://docs.spring.io/spring-amqp/reference/) — RabbitTemplate, listener containers, and AMQP integration.
- [Spring Cloud Stream Reference](https://docs.spring.io/spring-cloud-stream/reference/) — function bindings, binders, and event-driven applications.
- [Apache Kafka Documentation](https://kafka.apache.org/documentation/) — topics, partitions, retention, consumer groups, and broker configuration.
- [RabbitMQ Documentation](https://www.rabbitmq.com/docs) — exchanges, queues, bindings, acknowledgements, TTL, and dead-letter policies.
