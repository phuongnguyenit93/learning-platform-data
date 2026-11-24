# Separating Connection Configuration from Business Logic in Spring Messaging

## 1. Goal of Separation

In a messaging application, business code needs to focus on the question: **what does the message mean and how should it be processed?** Information for connecting to infrastructure needs to be managed in a separate configuration layer.

For example, a handler that processes an order creation command needs to know how to call the order creation service and what result to emit. The handler should not need to know which hostname or port the broker is running on, which credentials are used, how TLS is enabled, or how long the connection should retry.

Separating these two groups of responsibilities makes it possible to:

- Switch between local, test, staging, and production environments without modifying business logic.
- Swap brokers or infrastructure endpoints with a smaller blast radius.
- Manage sensitive information through environment variables or a secret manager.
- Unit-test business logic without starting a real broker.
- Centralize timeouts, heartbeats, pools, concurrency, and security in one controllable place.
- Prevent each handler from creating its own connections with inconsistent configurations.

You need to draw clear boundaries between the **message contract**, **business logic**, **messaging configuration**, and **deployment environment**.

## 2. Separation of Responsibilities

A maintainable design typically has four parts:

| Part | Responsibility | Example |
|---|---|---|
| Message contract | Defines payload, headers, destinations, and data types | CreateOrder, OrderCreated, /topic/orders |
| Business processing | Validates and executes business rules | OrderApplicationService |
| Messaging configuration | Creates adapters, connection factories, listeners, channels, and broker relays | WebSocketMessagingConfiguration |
| Environment configuration | Provides host, port, credentials, TLS, and operational parameters | application.yml, environment variables, secret manager |

The **message contract** can contain destinations such as `/app/orders` or `/topic/orders` because those are part of how the application communicates. Host, port, username, password, virtual host, certificates, and broker connection details belong to infrastructure configuration.

**Business processing** receives data that has been decoded and converted according to the application contract. It does not open sockets itself, construct connection factories, or assemble broker URLs from hardcoded strings.

## 3. Externalizing Connection Parameters

Values that should generally be kept out of source code include:

- Broker address, hostname, port, and virtual host.
- Username, password, tokens, and other authentication details.
- TLS, truststore, keystore, and certificate verification options.
- Client ID, heartbeat, connection timeout, and reconnect policy.
- Pool size, consumer concurrency, prefetch, and resource limits.
- Retries, acknowledgements, and timeouts that may vary by environment.

Do not commit real passwords or tokens to Git, sample configuration files, logs, or error messages. You may commit environment variable names and safe default values for local environments; real credentials should be supplied by the deployment environment or a secret manager.

Spring Boot configuration example:

~~~yaml
app:
  messaging:
    stomp:
      relay-host: ${STOMP_RELAY_HOST:localhost}
      relay-port: ${STOMP_RELAY_PORT:61613}
      client-login: ${STOMP_CLIENT_LOGIN}
      client-passcode: ${STOMP_CLIENT_PASSCODE}
      system-login: ${STOMP_SYSTEM_LOGIN}
      system-passcode: ${STOMP_SYSTEM_PASSCODE}
~~~

Host and port have default values for local development. Credentials have no defaults; the runtime environment must supply them. If using a secret manager, the deployment platform can inject secrets into environment variables or integrate directly according to the platform's mechanism.

Do not use production credentials in local or test profiles. Each environment needs permissions and secrets scoped to its boundaries.

## 4. Binding Configuration into Typed Objects

With Spring Boot 3 and later, `@ConfigurationProperties` is the right way to group related properties into a typed object. Example using a Java record:

~~~java
package com.example.messaging.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.messaging.stomp")
public record StompRelayProperties(
        String relayHost,
        int relayPort,
        String clientLogin,
        String clientPasscode,
        String systemLogin,
        String systemPasscode
) {
}
~~~

The YAML properties are bound into the record:

- `relay-host` → `relayHost`
- `relay-port` → `relayPort`
- `client-login` → `clientLogin`
- `client-passcode` → `clientPasscode`
- `system-login` → `systemLogin`
- `system-passcode` → `systemPasscode`

Register the record with `@EnableConfigurationProperties(StompRelayProperties.class)` on a configuration class, or use `@ConfigurationPropertiesScan` on the application. This is a Spring Boot mechanism. If using plain Spring Framework without Boot, read values from `Environment` or an application-configured property source and pass them through constructors or factory methods; `@ConfigurationProperties` is not part of core Spring Framework.

For critical configuration, validate values at application startup. You can use Bean Validation with `@Validated`, `@NotBlank`, `@Min`, and `@Max` to reject empty hosts, missing credentials, or out-of-range ports. This approach requires the corresponding validation dependency. Make sure secrets are provided before starting the application.

## 5. Centralizing the STOMP Connection in a Configuration Class

The following example configures Spring WebSocket messaging with a STOMP broker relay. Connection details appear only in the configuration class.

~~~java
package com.example.messaging.config;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration(proxyBeanMethods = false)
@EnableWebSocketMessageBroker
@EnableConfigurationProperties(StompRelayProperties.class)
public class WebSocketMessagingConfiguration
        implements WebSocketMessageBrokerConfigurer {

    private final StompRelayProperties properties;

    public WebSocketMessagingConfiguration(
            StompRelayProperties properties) {
        this.properties = properties;
    }

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");

        registry.enableStompBrokerRelay("/topic", "/queue")
                .setRelayHost(properties.relayHost())
                .setRelayPort(properties.relayPort())
                .setClientLogin(properties.clientLogin())
                .setClientPasscode(properties.clientPasscode())
                .setSystemLogin(properties.systemLogin())
                .setSystemPasscode(properties.systemPasscode());
    }
}
~~~

Main parts:

- `@EnableWebSocketMessageBroker` enables WebSocket messaging infrastructure.
- `registerStompEndpoints` registers the WebSocket endpoint that clients use to connect.
- `setApplicationDestinationPrefixes("/app")` declares the prefix for messages routed to application handler methods.
- `enableStompBrokerRelay("/topic", "/queue")` configures the relay to forward messages to an external STOMP broker.
- `setRelayHost` and `setRelayPort` obtain the connection address from properties.
- Client credentials and system credentials are supplied separately per the relay configuration.

In a STOMP broker relay, the connection serving client sessions and the relay's system connection have different roles. Grant appropriate broker permissions to each account type. Do not use a single account with broad administrative privileges for all application connections.

This example uses a broker relay, so it requires a running and reachable external STOMP broker. For simple testing environments, Spring supports an in-memory simple broker via `enableSimpleBroker`; that option does not have the same operational, persistence, or scaling capabilities as an external broker. Choose based on deployment requirements, and do not treat the two options as having identical guarantees.

## 6. Keeping Handlers Focused on Business Logic

Once connection infrastructure is configured separately, the controller or handler only needs to receive data according to the message contract and call the business service.

~~~java
package com.example.messaging.orders;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Controller;

@Controller
public class OrderMessagingController {

    private final OrderApplicationService orderService;

    public OrderMessagingController(OrderApplicationService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("/orders")
    @SendTo("/topic/orders")
    public OrderStatus create(@Payload CreateOrderCommand command) {
        return orderService.create(command);
    }
}
~~~

`OrderApplicationService`, `CreateOrderCommand`, and `OrderStatus` are application types that must be defined according to the project's domain model.

With the `/app` prefix in the configuration, clients send messages to destination `/app/orders`. Spring routes them to the `create` method. The return value is sent to destination `/topic/orders` per `@SendTo`.

The controller does not know where the broker lives, which port it uses, or what credentials it logs in with. When switching the broker from a local machine to production, the configuration layer and property sources change; the order creation rules stay in the business service.

Distinguish destinations from connection addresses. `/app/orders` and `/topic/orders` are destinations in the application's messaging contract, not hostnames or broker URLs. If a destination must vary by environment, you can place it in a dedicated configuration group, but avoid scattering arbitrary routing strings across handlers.

## 7. Applying the Principle to Other Brokers

Each technology has its own APIs and semantics. Connection configuration should still live in the infrastructure layer, while listeners or publishers only pass data to business services.

| Integration | Common Spring Boot properties | Common application APIs |
|---|---|---|
| ActiveMQ Classic via JMS | `spring.activemq.broker-url`, `spring.activemq.user`, `spring.activemq.password` | `JmsTemplate`, `@JmsListener` |
| ActiveMQ Artemis via JMS | `spring.artemis.broker-url` and corresponding authentication properties | `JmsTemplate`, `@JmsListener` |
| RabbitMQ via AMQP | `spring.rabbitmq.host`, `spring.rabbitmq.port`, `spring.rabbitmq.username`, `spring.rabbitmq.password` | `RabbitTemplate`, `@RabbitListener` |
| Apache Kafka | `spring.kafka.bootstrap-servers` and producer/consumer properties | `KafkaTemplate`, `@KafkaListener` |

The prefixes above are Spring Boot auto-configuration properties and may differ by provider, version, or configuration style. In a plain Spring Framework application, you must declare the connection factory, client, or adapter yourself with the appropriate beans.

Example division of responsibilities:

- The configuration layer creates and configures the connection factory, template, listener container, or adapter.
- Publishers use the injected template to send messages.
- Listeners receive messages, validate the input contract, and invoke the business service.
- Business services do not read hostnames or passwords or create broker connections themselves.

With Spring Integration, apply the same boundary: configure channels, inbound/outbound adapters, connection factories, and endpoints in the integration layer; service activators call business logic. In-memory channels and broker-connecting adapters have different semantics, so read carefully about the exact endpoint type in use.

## 8. Managing Environments and Secrets

### 8.1 Separating Configuration by Environment

Spring Boot supports profiles to set different values for local, test, staging, and production:

~~~text
application.yml
application-local.yml
application-test.yml
application-prod.yml
~~~

The local profile can point to a broker running on the developer's machine. The test profile can use a dedicated broker or one launched by Testcontainers. Production obtains addresses and secrets from the deployment system.

You do not need to duplicate the entire configuration file for every profile. Keep shared values in the base file and override only the values that actually differ.

### 8.2 Secret Management

- Do not store real credentials in the repository.
- Do not write passwords, tokens, or connection strings containing secrets to logs.
- Grant least-privilege permissions to the application's broker account.
- Use separate secrets for the client connection, system connection, and each environment when required by the architecture.
- Have a process to rotate credentials and update secrets without modifying business code.
- Do not include secrets in exception messages, metric labels, or trace attributes.

Environment variables are a common way to supply configuration, though production systems may use a secret manager or platform workload identity/credential mechanisms. Choose an approach suited to the infrastructure in operation and protect read access to secrets.

## 9. Testing When Configuration and Business Logic Are Separated

Clear boundaries let you divide tests by purpose:

1. **Business unit tests:** invoke services or handlers directly with input data; use mocks/fakes for needed dependencies. No real broker is needed to test order creation rules.
2. **Configuration binding tests:** verify properties bind to the right types, required values are validated, and invalid configuration is caught at startup.
3. **Messaging configuration tests:** initialize the application context to verify beans, endpoints, and adapters are registered properly.
4. **Integration tests:** use a test broker or Testcontainers to verify connectivity, sending/receiving, routing, acknowledgements, and real error handling.
5. **Environment-specific verification:** verify production configuration receives the right host, TLS, secrets, and access permissions without printing secrets to logs.

Do not use business unit tests to check broker hostnames. Conversely, testing broker connectivity does not replace testing business rules. Each type of test should verify the exact responsibility of its corresponding layer.

## 10. Common Mistakes

- **Hardcoding host and port inside handlers:** changing environments forces modifying processing logic or rebuilding the application.
- **Creating a connection on every message handled:** wastes resources, increases latency, and makes connection lifecycles hard to control.
- **Reading environment directly across multiple business layers:** scatters configuration and makes testing harder.
- **Leaving credentials in committed YAML files:** secrets can leak through Git history and build artifacts.
- **Lumping all configuration into an unstructured object:** properties across multiple brokers become easy to mix up and hard to validate.
- **Sharing an overly privileged credential:** increases blast radius if a service or secret is compromised.
- **Confusing the simple broker with a production broker:** the in-memory simple broker does not provide persistence or distributed scalability on its own.
- **Putting every destination into connection configuration:** destinations are part of the application's routing contract; externalize them only when there is a reason for them to vary by environment.
- **Skipping startup configuration validation:** the application may only discover an invalid host, port, or credentials when the first message arrives.
- **Having no integration tests:** valid property binding does not prove the broker is reachable or publish/subscribe permissions are valid.

## 11. Design Checklist

Before putting a messaging integration into production, check:

- Do handlers only process payloads and call business services?
- Are host, port, credentials, TLS, and timeouts in the configuration layer?
- Are connection properties bound into strongly typed objects or clear configuration beans?
- Does each environment have its own appropriate endpoints and secrets?
- Are secrets managed outside the repository and logs?
- Are the lifecycles of connection factories, templates, listeners, and adapters managed by the container?
- Are destinations defined as a consistent routing contract?
- Is invalid configuration detected at application startup?
- Do business unit tests run without a broker?
- Do integration tests verify connectivity and delivery with a real broker?

When these answers are clear, the application can change its connection infrastructure with minimal scope, while handlers and services continue to accurately reflect business logic.