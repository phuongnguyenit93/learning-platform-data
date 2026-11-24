# Roles and Dependencies of the messaging, jms, and websocket Modules

Spring Framework splits messaging functionality into multiple smaller modules. Three commonly used artifacts are spring-messaging, spring-jms, and spring-websocket. They can work together in the same application, but each module addresses a distinct layer: the message model, integration with a JMS provider, and WebSocket communication with clients.

When designing dependencies, distinguish between three types of components:

1. **Spring integration module:** Spring libraries that provide abstractions, templates, listeners, and configuration.
2. **Protocol API and runtime:** the standard API that the integration module calls, along with its corresponding implementation.
3. **External infrastructure:** brokers, servlet containers, WebSocket endpoints, or clients connecting to the application.

Adding a Spring module only puts integration code on the classpath. It does not automatically install or start every broker, server, or service that the application needs.

## 1. Role of Each Artifact

### 1.1. spring-messaging

Artifact: org.springframework:spring-messaging.

This is the foundational layer for messaging in Spring. The module defines the message model and contracts so components can exchange data without depending directly on a specific transport.

Key API types:

- Message<T>: a message with payload and headers.
- MessageHeaders: metadata attached to a message.
- MessageChannel: contract for sending messages.
- MessageHandler: contract for handling messages.
- SubscribableChannel and PollableChannel: two channel types with different ways of receiving messages.
- MessageBuilder: builds messages.
- MessageConverter: converts payloads between messages and Java types.
- MessageSendingOperations and MessageReceivingOperations: send/receive operation contracts.
- GenericMessagingTemplate: template working with a MessageChannel as the destination.
- Abstractions in the simp package: support for Simple Messaging Protocol, including STOMP.

spring-messaging does not require the application to connect to a JMS broker or open a WebSocket. You can use these abstractions to organize message flows inside the application. When integrating with a transport, a specialized module connects those abstractions to the corresponding protocol.

### 1.2. spring-jms

Artifact: org.springframework:spring-jms.

This module integrates a Spring application with Jakarta Messaging (JMS). JMS provides a standard API for message communication between an application and a JMS provider. Spring adds utilities to send, receive, convert messages, manage listener containers, and participate in transactions.

Representative APIs:

- JmsTemplate: sends and receives messages synchronously.
- JmsMessagingTemplate: adapter to use Spring Messaging abstractions when working with JMS.
- @JmsListener: declares a method that receives messages.
- @EnableJms: enables listener annotation processing in plain Spring Framework configuration.
- DefaultJmsListenerContainerFactory and SimpleJmsListenerContainerFactory: configures listener containers.
- JmsTransactionManager: local transaction manager for a JMS ConnectionFactory.
- MessageConverter: converts between JMS messages and Java objects.

spring-jms requires a real jakarta.jms.ConnectionFactory. This ConnectionFactory is usually created by the broker vendor's client library. Example providers you can use include ActiveMQ Artemis or a compatible ActiveMQ Classic version supporting Jakarta Messaging.

Spring is not a JMS provider. If you only add spring-jms without a suitable implementation and connection configuration, the application cannot yet send or receive messages through a broker.

### 1.3. spring-websocket

Artifact: org.springframework:spring-websocket.

This module provides server-side WebSocket support on the Servlet stack, including:

- APIs to handle WebSocket frames directly via WebSocketHandler.
- Endpoint and handshake configuration.
- SockJS fallback for environments that do not fully support WebSocket.
- STOMP messaging running over WebSocket.
- Components supporting sessions, transport, and broker connectivity.

When using raw WebSocket only, the application can handle frames with its own handler. When using STOMP, spring-websocket collaborates with spring-messaging to represent frames as Messages, route them through channels, and invoke annotated methods such as @MessageMapping.

spring-websocket does not replace the servlet container. The application still needs a server environment that supports WebSocket, such as embedded Tomcat or Jetty in a Spring Boot application, or a properly configured standalone container.

For reactive WebFlux applications, distinguish the reactive WebSocket APIs belonging to spring-webflux from the Servlet WebSocket APIs belonging to spring-websocket. Do not choose an artifact based solely on the protocol name.

## 2. Dependency Relationships Between Modules

Spring modules share foundations such as spring-core, spring-beans, and spring-context. Specifically, spring-context depends on spring-beans, and spring-beans depends on spring-core.

Part of the key dependency graph in Spring Framework 6.x can be depicted as follows:

~~~text
Application
├── spring-jms
│   ├── spring-messaging
│   ├── spring-tx
│   └── spring-beans / spring-core
│
├── spring-websocket
│   ├── spring-context
│   ├── spring-web
│   └── spring-messaging (optional; needed for STOMP)
│
└── spring-messaging
    ├── spring-beans
    └── spring-core

spring-context
└── spring-beans
    └── spring-core
~~~

This is a diagram of the primary edges relevant to the three modules, not an exhaustive list of every dependency in each version. Some dependencies are optional or only needed when enabling a specific capability. Check the POM and Gradle module metadata of the exact version when you need the exact classpath.

There are three points to understand:

1. **spring-jms depends on spring-messaging.** JmsMessagingTemplate uses Spring's messaging abstractions. Therefore, when adding spring-jms, spring-messaging usually appears in the dependency graph as a transitive dependency.
2. **spring-websocket can use spring-messaging.** STOMP messaging relies on spring-messaging. This dependency is optional in the module so that applications using raw WebSocket do not necessarily pull in all messaging abstractions.
3. **spring-messaging does not depend on JMS or WebSocket.** It is an abstraction layer that can be used standalone or used by other integration modules.

If application code directly imports classes from a module, declare a direct dependency on that module. Do not rely on another library accidentally pulling the required module onto the classpath, as the dependency graph may change on upgrades.

## 3. External Dependencies Needed Beyond Spring for Each Case

### 3.1. Using spring-messaging Standalone

If you only use Message, MessageChannel, MessageHandler, MessageBuilder, or GenericMessagingTemplate to organize message handling inside the application, the primary dependency is spring-messaging along with the foundational dependencies it declares.

No JMS provider, broker, or WebSocket server installation is needed for this case.

Example:

~~~groovy
dependencies {
    implementation("org.springframework:spring-messaging")
}
~~~

This snippet assumes the version is managed by a BOM or project-level dependency management.

### 3.2. Using spring-jms

A JMS application needs at least:

- spring-jms to use JmsTemplate, listener containers, and integration APIs.
- Jakarta Messaging API with the jakarta.jms package.
- A compatible JMS provider client to create a ConnectionFactory.
- A broker or JMS service that the provider client can connect to.
- spring-tx if the application needs transaction abstractions; spring-jms already declares a dependency on Spring's transaction module in the standard dependency graph.

Providers may be distributed across multiple artifacts. For example, a client library used to connect to a remote broker is different from a server library used to embed a broker in the same JVM. Do not add a server artifact to a production application just to resolve a missing ConnectionFactory error.

A JMS ConnectionFactory holds connection information and the capability to create connections to the provider. It can be created directly in code, configured as a Spring bean, or provided via application server JNDI.

### 3.3. Using Raw WebSocket

A Servlet application using raw WebSocket typically needs:

- spring-websocket.
- spring-web and spring-context per Spring's dependency graph.
- A Servlet container with a compatible WebSocket API implementation.
- Jakarta Servlet/WebSocket APIs provided by the container or build environment depending on the deployment configuration.

The application also needs an endpoint handler and handshake configuration. If running an embedded server, Spring Boot's starter dependencies usually help set up the runtime. If deploying a WAR to a standalone server, you must verify WebSocket support on the target container.

### 3.4. Using STOMP over WebSocket

To use @EnableWebSocketMessageBroker, @MessageMapping, SimpMessagingTemplate, and broker messaging, you need all of:

- spring-websocket.
- spring-messaging.
- A compatible Servlet/WebSocket runtime.

STOMP is a sub-protocol over WebSocket. Spring can use an internal simple broker for subscriptions and broadcasting, or configure a broker relay to an external STOMP broker.

The simple broker does not require installing an external broker. A broker relay requires a broker that supports STOMP and separate connection configuration. A JMS provider does not support STOMP by default; verify the product's protocol support and enable the corresponding plugin/module if sharing a broker.

SockJS also requires the corresponding JavaScript client in the browser when the application uses SockJS fallback. That is a frontend dependency, not a Java dependency replacing spring-websocket.

## 4. Choosing Dependencies by Use Case

| Use case | Spring artifact | Additional dependencies or infrastructure |
|---|---|---|
| Create internal Messages and channels | spring-messaging | Spring core dependencies |
| Send/receive JMS with JmsTemplate | spring-jms | Jakarta JMS API, provider client, ConnectionFactory |
| Receive JMS asynchronously with @JmsListener | spring-jms | Provider, listener container factory, broker |
| Raw WebSocket on Servlet stack | spring-websocket | Servlet container and WebSocket runtime |
| STOMP over WebSocket | spring-websocket + spring-messaging | WebSocket runtime; simple broker or STOMP broker relay |
| JMS receives events then broadcasts to WebSocket clients | spring-jms + spring-websocket + spring-messaging | JMS provider and WebSocket runtime; add STOMP broker if using relay |
| Kafka | Spring for Apache Kafka | Kafka client and Kafka broker |
| RabbitMQ via AMQP | Spring AMQP | AMQP client and RabbitMQ broker |

Do not use spring-jms just because the problem domain mentions the word message. Kafka, AMQP, MQTT, and STOMP are different protocols or integrations. Use the specialized module for the protocol you need to connect to.

## 5. Configuring Dependencies with Gradle

### 5.1. Applications Using Spring Framework Directly

If the project does not use Spring Boot dependency management, you can import the Spring Framework BOM to synchronize versions:

~~~groovy
ext {
    springFrameworkVersion = "6.1.21"
}

dependencies {
    implementation(platform(
        "org.springframework:spring-framework-bom:${springFrameworkVersion}"
    ))

    implementation("org.springframework:spring-messaging")
    implementation("org.springframework:spring-jms")
    implementation("org.springframework:spring-websocket")
}
~~~

The example above fixes a BOM version for illustration. In a real project, pick a version matching Java, the Jakarta EE baseline, and related libraries. Do not specify three different versions for the three Spring Framework artifacts.

Declare only the modules actually used. For example:

- An application that only creates internal Messages: keep spring-messaging.
- An application that only receives JMS: add spring-jms and the provider client.
- An application that only uses raw WebSocket: add spring-websocket and the required runtime.
- An application using STOMP: declare both spring-websocket and spring-messaging to clearly reflect the APIs the code uses.

### 5.2. Applications Using Spring Boot

With Spring Boot, let the Spring Boot BOM manage Spring Framework versions. Starters bundle the appropriate dependencies and auto-configuration for the use case.

Example of a Servlet application using WebSocket and JMS via ActiveMQ Artemis:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-websocket")
    implementation("org.springframework.boot:spring-boot-starter-artemis")
}
~~~

If using ActiveMQ Classic, the corresponding starter is spring-boot-starter-activemq. JMS starters provide the required provider dependencies and Spring infrastructure for JMS integration. Choose the exact provider used by the deployment environment.

With STOMP, the WebSocket starter provides the WebSocket infrastructure for an MVC application; the messaging abstractions are used in the STOMP flow. If the code directly uses spring-messaging APIs, you can declare spring-messaging directly to make the source code's dependency explicit.

Do not manually add a different Spring Framework version to individual dependencies when Spring Boot already manages the BOM. If overriding is necessary, understand the impact on all Spring Framework modules and compatibility with the Spring Boot version in use.

### 5.3. Plain Maven Example

Import the BOM inside dependencyManagement:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-framework-bom</artifactId>
            <version>${spring-framework.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Then declare the modules:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-messaging</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-jms</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-websocket</artifactId>
    </dependency>
</dependencies>
~~~

In this example, the spring-framework.version property must be defined in the project's properties or profile section. If using Spring Boot parent or BOM, follow Boot's version management mechanism instead of importing another standalone BOM that could cause conflicts.

## 6. Spring Boot Configuration Examples for JMS and WebSocket

### 6.1. JMS with ActiveMQ Artemis

With the Artemis starter, Spring Boot can auto-configure a ConnectionFactory and JMS beans when the provider dependency is on the classpath.

Example configuration for connecting to a remote broker:

~~~yaml
spring:
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: ${ARTEMIS_USER}
    password: ${ARTEMIS_PASSWORD}
~~~

The values above are illustrative configuration for a local environment only. Production needs a secret manager or securely managed environment variables; do not commit credentials to source control.

Once the JMS infrastructure is configured, the application can inject JmsTemplate to send messages or use @JmsListener to receive messages. Spring Boot usually auto-configures a default listener container factory and detects listener annotations when JMS infrastructure is present.

### 6.2. WebSocket with STOMP

A typical STOMP configuration:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

This configuration uses the internal simple broker. When an external broker is needed, replace enabling the simple broker with enableStompBrokerRelay and provide connection details, authentication, heartbeats, and operational limits.

### 6.3. A Coordinated JMS → WebSocket Flow

Example of a service receiving events from JMS and broadcasting them to WebSocket subscribers:

~~~java
@Component
public class OrderEventBridge {

    private final SimpMessagingTemplate messagingTemplate;

    public OrderEventBridge(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    @JmsListener(destination = "orders.events")
    public void onOrderEvent(OrderEvent event) {
        messagingTemplate.convertAndSend("/topic/orders", event);
    }
}
~~~

In this flow, the two integration modules still operate over two separate protocols:

1. The JMS provider delivers the event to the listener container.
2. The listener receives the Java payload via spring-jms.
3. SimpMessagingTemplate sends the message into Spring's broker channel.
4. The STOMP broker routes the message to matching subscriptions.
5. The WebSocket transport delivers the frame to the browser.

This bridge is created by the application. Spring does not automatically map every JMS queue to a STOMP destination. Nor is there an atomic transaction spanning both JMS acknowledgement and frame delivery to every WebSocket client. If the data has business significance, persist the state durably and let clients re-read it upon reconnect.

## 7. Jakarta Namespace and Version Compatibility

Spring Framework 6.x uses the Jakarta EE 9+ namespace. This directly affects JMS and WebSocket dependencies.

For example:

| Legacy API | API used in Spring Framework 6.x |
|---|---|
| javax.jms.ConnectionFactory | jakarta.jms.ConnectionFactory |
| javax.servlet.Servlet | jakarta.servlet.Servlet |
| javax.websocket.Session | jakarta.websocket.Session |

You cannot just change imports in code if the provider client or application server still provides legacy javax.* APIs. Components within the same application must be compatible with the Jakarta namespace required by the Spring Framework version.

Principles when upgrading:

- Check the Java baseline of the Spring Framework version.
- Check the Jakarta Messaging API and provider client.
- Check the Servlet container and WebSocket implementation.
- Check the Spring Boot version corresponding to Spring Framework.
- Inspect the dependency graph to avoid having both javax and jakarta APIs for one protocol simultaneously.
- Read Spring's upgrade guide when changing major/minor versions.

Spring Framework 6.x requires Java 17 or higher and switches to the Jakarta namespace. An older provider that only implements javax.jms can cause compile or runtime errors even when spring-jms is on the classpath.

## 8. Inspecting the Dependency Graph When Errors Occur

When the application cannot find classes, throws NoClassDefFoundError, ClassNotFoundException, NoSuchMethodError, or fails to initialize a ConnectionFactory, inspect the dependency graph before adding libraries randomly.

### 8.1. Gradle

View all runtime dependencies:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Find a specific dependency and why a version was selected:

~~~bash
./gradlew dependencyInsight --dependency spring-messaging --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-jms --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-websocket --configuration runtimeClasspath
~~~

These commands help detect:
- modules not included on the classpath;
- multiple versions of Spring Framework appearing together;
- excluded dependencies;
- undeclared provider clients;
- versions selected due to conflict resolution or constraints.

### 8.2. Maven

View the dependency tree:

~~~bash
mvn dependency:tree -Dincludes=org.springframework
~~~

You can filter by the provider's groupId or artifactId to check the version and scope being used.

### 8.3. Distinguishing Missing Class Errors from Connection Errors

| Symptom | Category of cause to check |
|---|---|
| ClassNotFoundException for jakarta.jms.* | Missing Jakarta Messaging API or compatible provider client |
| ClassNotFoundException for org.springframework.messaging.* | Missing spring-messaging or excluded dependency |
| Failed to create ConnectionFactory | Provider dependency, URL configuration, credentials, or unsuitable factory class |
| Connection refused / timeout | Broker not running, wrong host/port, firewall, or TLS |
| Failed to upgrade WebSocket | Container, reverse proxy, endpoint, or handshake |
| STOMP CONNECT succeeds but SEND does not reach handler | Destination prefix, @MessageMapping, channel, or broker configuration |
| NoSuchMethodError inside Spring | Spring modules have mismatched versions or incompatible libraries |

Classpath errors and network errors require two different lines of troubleshooting. Adding a broker dependency will not fix a wrong URL; fixing the URL will not resolve a Jakarta namespace mismatch.

## 9. Dependency Mistakes and How to Avoid Them

### 9.1. Mixing Spring Module Versions

For example, spring-core at one version while spring-messaging or spring-websocket is at another version can lead to NoSuchMethodError or bean initialization errors.

The way to avoid this is to use the Spring Framework BOM or Spring Boot BOM and run dependencyInsight whenever a version conflict occurs.

### 9.2. Relying on Transitive Dependencies

One module may pull spring-messaging onto the classpath. However, if source code directly uses Message, GenericMessagingTemplate, or SimpMessagingTemplate, declare spring-messaging directly.

This makes the module's actual dependencies explicit and prevents code from accidentally relying on an implementation detail of another starter or integration module.

### 9.3. Missing Provider or Wrong Provider

spring-jms provides the integration layer, while the provider client creates the ConnectionFactory and communicates with the broker. Choose the right client artifact and API namespace for the provider. Do not mix client libraries from multiple brokers just to see which class initializes.

### 9.4. Using the Wrong Module for the Protocol

- RabbitMQ AMQP typically uses Spring AMQP.
- Kafka uses Spring for Apache Kafka.
- JMS uses spring-jms.
- STOMP over WebSocket uses spring-websocket and spring-messaging.

Multiple protocols can coexist in one system, but that does not mean they share the same dependency or the same kind of destination.

### 9.5. Forgetting Infrastructure When Deploying

An application that runs in the IDE does not necessarily have all required infrastructure once packaged:

- The JMS broker may not be provisioned or may not be reachable from the runtime.
- The Servlet container may not have WebSocket support enabled.
- The reverse proxy may not forward HTTP Upgrade requests.
- The STOMP broker relay may fail to open a TCP connection to the broker.
- The container image may be missing the provider client due to an incorrect dependency scope.

Check the runtimeClasspath, deployment configuration, and connectivity in a production-like environment.

## 10. Testing Strategy by Module

### 10.1. spring-messaging

You can test MessageBuilder, headers, channels, and handlers without an external broker. These are fast unit tests to verify contracts and internal routing logic.

### 10.2. spring-jms

Unit tests can mock abstractions or services calling JmsTemplate. However, behaviors such as acknowledgement, redelivery, selectors, and transactions should be tested against a real JMS provider or a suitable test broker.

Test scenarios including successful listener processing, listener throwing an exception, message redelivery, provider connection loss, and transaction rollback.

### 10.3. spring-websocket

Test handlers and message mappings separately. With STOMP, write integration tests verifying handshake, CONNECT, SUBSCRIBE, SEND, message routing, and session closing.

Also test reconnect, destination-based authorization, invalid payloads, and timeouts. If deploying behind a reverse proxy, run a test in the exact deployment topology because unit tests cannot confirm whether the proxy forwards WebSocket Upgrades.

### 10.4. Testing the JMS and WebSocket Bridge

Integration tests for the flow should verify:

1. The JMS event is received.
2. The payload is converted properly.
3. The message is published to the STOMP destination.
4. Subscribers receive the message.
5. Failures at any step are logged and handled according to policy.
6. Offline clients can re-read business state if data loss is unacceptable.

Do not treat the listener method being invoked as proof that the entire bridge has successfully delivered the message to clients.

## 11. Workflow for Choosing and Adding Dependencies

When starting a messaging feature, follow this order:

1. Identify the transport/protocol: internal, JMS, WebSocket/STOMP, Kafka, or AMQP.
2. Identify the Spring APIs that the source code will import.
3. Choose the corresponding Spring artifact(s).
4. Identify any external providers or runtimes needed beyond Spring.
5. Use a BOM to synchronize versions.
6. Inspect the dependency graph and runtime classpath.
7. Configure connections, destinations, transactions, security, and timeouts.
8. Write unit tests for contracts and integration tests for transports.
9. Verify behavior in an actual deployment environment.

This approach ensures dependencies accurately reflect the architecture. An application may only need one of the three modules; combine them only when multiple communication types are required.

## 12. References

- [Spring Framework Artifacts](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-Artifacts) — artifact list, dependency management, and BOM.
- [Spring Framework Reference — Messaging](https://docs.spring.io/spring-framework/reference/integration.html) — messaging abstractions and APIs.
- [Spring Framework Reference — JMS](https://docs.spring.io/spring-framework/reference/integration/jms.html) — JmsTemplate, listener containers, and transactions.
- [Spring Framework Reference — WebSocket](https://docs.spring.io/spring-framework/reference/web/websocket.html) — raw WebSocket and SockJS.
- [Spring Framework Reference — STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp.html) — message flow, simple broker, and broker relay.
- [Spring Boot Reference — JMS](https://docs.spring.io/spring-boot/reference/messaging/jms.html) — ActiveMQ, Artemis, and ConnectionFactory auto-configuration.
- [Spring Boot Reference — WebSockets](https://docs.spring.io/spring-boot/reference/messaging/websockets.html) — WebSocket starter and runtime.
- [Spring Framework 6.1 Javadoc — org.springframework.messaging](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/package-summary.html)
- [Spring Framework 6.1 Javadoc — org.springframework.jms](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jms/package-summary.html)

When looking up dependencies, always cross-check the exact Spring Framework and Spring Boot versions of the project. Artifact names may stay the same across versions, while the dependency graph, Jakarta baseline, and auto-configuration can change.