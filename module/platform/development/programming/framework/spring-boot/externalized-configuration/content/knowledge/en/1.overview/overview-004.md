# Distinguishing Application Configuration, Bean Definitions, and Business Data

In Spring Boot, three concepts—**application configuration**, **bean definition**, and **business data**—often appear in the same processing flow. They can coexist in a single Java class, yet they have different origins, owners, lifecycles, and change mechanisms. Distinguishing them properly keeps an application easy to deploy across environments, easy to test, and prevents turning the Spring container into a store for business state.

## 1. Quick Overview of the Three Layers of Responsibility

| Aspect | Application Configuration | Bean Definition | Business Data |
| --- | --- | --- | --- |
| Question answered | **With what parameters** does the app run in this environment? | **Which objects, dependencies, and lifecycles** does Spring create? | **Which events, transactions, or entities** is the system processing? |
| Examples | External service URLs, timeouts, pool sizes, topic names, integration toggle flags | `@Component`, `@Service`, `@Configuration`, `@Bean`, auto-configuration | Orders, payment amounts, shipment statuses, customer information |
| Common sources | `application.yml`, environment variables, startup arguments, secret stores | Java code, annotations, configuration classes, framework auto-configuration | Databases, API requests, messages/events, user actions |
| Who typically changes it? | Operators or the development team per environment | Developers via code/version changes | Users, business workflows, and system processes |
| Typical lifecycle | Loaded/bound at startup; updatability depends on consumption mechanism | Registered, instantiated, and managed by Spring in `ApplicationContext` | Created, updated, read, and persisted along business flows |
| How to test | Override properties, test binding/validation | Test wiring, bean creation conditions, and dependency injection | Test business behavior, transactions, and input/output data |

**Key point:** the same value can pass through multiple layers, while its role changes depending on where it is used. A timeout value is *configuration*; the `GatewayClient` object Spring constructs using that timeout is a *bean*; an order passed into the client is *business data*.

## 2. Application Configuration: Values Controlling How the App Operates

Spring Boot supports **externalized configuration**: instead of hard-coding every per-environment value into source code, the application receives properties from sources such as configuration files, environment variables, or runtime arguments. Spring `Environment` provides the model for accessing properties; `@ConfigurationProperties` binds a group of properties into a strongly typed object.

Example in `application.yml`:

~~~yaml
shipping:
  gateway:
    base-url: https://shipping.example.invalid
    timeout: 3s
    enabled: true
~~~

These are **technical parameters for shipping integration**: the outbound endpoint, the timeout, and whether the integration component is enabled. Development, staging, and production environments can use different values without duplicating the `ShippingClient` class.

Characteristics that identify application configuration:

- Values describe the **environment or operational policy** of a deployment: host, port, timeout, retry level, connection limit, log level.
- Values usually have **defaults, validity constraints, and naming conventions**; they can be overridden from configuration sources with appropriate precedence.
- Values should be **validated early** to avoid starting the application with invalid settings. `@ConfigurationProperties` is well suited for grouping and type-safe binding.
- Secrets such as tokens, passwords, and API keys are still a form of configuration, but should come from a secret manager or environment security mechanism—never hard-coded in a repository or printed to logs.

Java example receiving the configuration group above:

~~~java
import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "shipping.gateway")
public record ShippingGatewayProperties(
        URI baseUrl,
        Duration timeout,
        boolean enabled
) {}
~~~

When the application enables `@ConfigurationPropertiesScan` or registers this type via `@EnableConfigurationProperties`, Spring Boot binds keys such as `base-url` and `timeout` into `ShippingGatewayProperties`. The string `3s` is converted into a `Duration`.

**Distinguish the configuration holder object from the configuration source:** `ShippingGatewayProperties` can be a Spring-managed bean; that does not turn `application.yml` into a bean definition. The YAML file supplies **values**, whereas registering the bean belongs to Spring's configuration mechanism.

### Profiles Are Not Business Data

Files such as `application-dev.yml` and `application-prod.yml` can represent per-environment values. Profiles help choose the appropriate configuration set or Spring components, but should not be used to represent the state of individual orders, customers, or specific transactions.

For example, "production calls the real endpoint" is a configuration decision; "order 123 has been shipped" is business state that must be persisted and audited.

## 3. Bean Definitions: How Application Components Are Assembled

A **bean definition** is metadata Spring uses to know how a component should be registered and created. A bean is an **instance managed by the Spring container**. Common declaration methods include:

- `@Component` and specializations such as `@Service` and `@Repository` to discover components via component scanning.
- `@Bean` methods inside `@Configuration` to define objects constructed in Java code, especially useful for third-party library classes.
- Spring Boot auto-configuration, typically conditional on the classpath, existing beans, or properties.
- Rules such as scope, qualifiers, primary markers, and activation conditions to decide which instances enter `ApplicationContext`.

Continuing the shipping example, suppose `ShippingClient` is a Java class accepting a URL and timeout via its constructor:

~~~java
import java.net.URI;
import java.time.Duration;

public final class ShippingClient {
    private final URI baseUrl;
    private final Duration timeout;

    public ShippingClient(URI baseUrl, Duration timeout) {
        this.baseUrl = baseUrl;
        this.timeout = timeout;
    }

    // Integration methods using baseUrl and timeout.
}
~~~

We define the corresponding bean:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class ShippingClientConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "shipping.gateway",
        name = "enabled",
        havingValue = "true"
    )
    ShippingClient shippingClient(ShippingGatewayProperties properties) {
        return new ShippingClient(
            properties.baseUrl(),
            properties.timeout()
        );
    }
}
~~~

The `@Bean` method describes **how to create and manage `ShippingClient`**; the `@ConditionalOnProperty` condition uses **a configuration value** to decide whether to register the bean. The property `shipping.gateway.enabled=true` by itself does not define the constructor, dependencies, or lifecycle of the bean.

If the condition does not match, Spring does not register this bean. Any component that obligatorily injects `ShippingClient` must also be structured appropriately when the integration is disabled; otherwise, the application can fail due to a missing dependency. This is a **wiring** issue, not an order data issue.

Keep in mind as well:

- The default scope of most application beans is **singleton per `ApplicationContext`**, which does not mean singleton across all processes or servers.
- The container creates and manages beans according to application structure; **it does not create a new singleton bean for every business request**.
- Changing a property does not automatically recreate a bean. Basic Spring Boot usually binds and constructs beans at startup; dynamic updates require explicitly designing a reload/refresh mechanism and handling state synchronization.
- Beans can be declared via annotations or Java configuration; the essence remains **registering components and dependencies**, not storing data tables.

## 4. Business Data: Facts the Application Processes and Stores

Business data represents the state or history of the application domain: which order was created, how much it costs, which customer owns it, which invoice has been paid, and what state a parcel is in. It flows through APIs, commands, events, services, repositories, and databases.

Example of a simplified order data object:

~~~java
import java.math.BigDecimal;
import java.util.UUID;

public record ShippingOrder(
        UUID id,
        UUID customerId,
        BigDecimal totalAmount,
        String deliveryAddress,
        String status
) {}
~~~

A use case can load `ShippingOrder` from a repository and call `ShippingClient` to send a request to the shipping system:

~~~java
public void requestShipment(UUID orderId) {
    ShippingOrder order = orderRepository.findById(orderId)
        .orElseThrow(() -> new OrderNotFoundException(orderId));

    shippingClient.createShipment(order);
}
~~~

The use case code above is illustrative: repositories, exceptions, and integration methods are defined in the actual business module. What matters is that **the `order` object comes from business data**, while `shippingClient` is a Spring-managed dependency that already received operational settings.

Characteristics of business data:

- Typically has **identity** (order ID, customer ID), state, timestamps, relationships, and integrity rules.
- Can change **continuously while the application is running** without restarting the server.
- Changes must go through validation, authorization, transactions, and the relevant business workflows.
- Requires storage, querying, access control, auditing, and traceability according to requirements; deployment configuration files should not be treated as the source of truth for transactions.

An example of crossing the wrong boundary is writing `order.status=SHIPPED` or `customer.42.creditLimit=...` inside `application.yml` for daily business updates. Those values require a proper data model and business management workflow.

## 5. Viewing the Full Data Flow

~~~text
application.yml / environment / secrets
                 |
                 | bind configuration
                 v
       ShippingGatewayProperties
                 |
                 | injection
                 v
@Configuration + @Bean ---> ShippingClient (Spring-managed)
                                 |
API / event --> OrderService ----+----> calls shipping system
                   |
                   v
            OrderRepository
                   |
                   v
            Order record
~~~

Read the diagram in sequence:

1. Externalized configuration sources provide the URL, timeout, and activation flag.
2. Spring binds the values into `ShippingGatewayProperties`.
3. The bean definition decides whether to create `ShippingClient` and how to supply its dependencies.
4. `OrderService` is the component executing the use case; it receives required dependencies via its constructor.
5. Requests and the database supply individual order data; the service executes business logic on that data and invokes the client.

You can view this as three distinct questions: **which values are used**, **which objects are created**, and **which business records those objects process**.

## 6. Commonly Confused Cases

### 6.1. Is `@ConfigurationProperties` a Bean Definition?

A class annotated with `@ConfigurationProperties` describes the **structure and binding rules for configuration values**. For Spring to manage an instance, a bean registration mechanism (scanning, enabling, or an appropriate `@Bean` method) is still required. Thus there are two sides:

- `shipping.gateway.timeout=3s` is a **configuration value**.
- Registering `ShippingGatewayProperties` into the container is **bean creation/definition behavior**.

Do not call all of `application.yml` "bean configuration" when it holds application properties.

### 6.2. When `@Value` Reads a Property, Does the Variable Become Business Data?

No. Injecting a property into a field or constructor is simply **consuming application configuration**. A value's role depends on its meaning. An HTTP client's `timeout` remains operational configuration even once the value is inside a Java object.

With multiple related properties, `@ConfigurationProperties` is usually easier to maintain than scattered `@Value` strings because it groups values under one prefix and enforces clear data types.

### 6.3. Which Layer Does a Feature Flag Belong To?

A flag such as `shipping.gateway.enabled` used to toggle an **integration component per environment** is usually application configuration. It can be used by `@ConditionalOnProperty` to decide a bean definition.

However, a flag chosen by operations staff for **individual customers**, specific experiments, or individual transactions—changing dynamically while the system runs—may be **business data/policy** stored in a database or a feature flag management service. You cannot classify something merely by the word "flag".

### 6.4. What About Tax Rates, Shipping Fees, Limits, and Discount Tiers?

These are often **business rules or business parameters**, which may be stored in properties or database tables depending on operational needs. To decide, ask: who is authorized to change them, do they vary by customer/order or by deployment, and do they require effective dates, auditing, or approval?

- A technical request limit, fixed across the entire environment, fits well as configuration.
- A regional shipping fee schedule with effective dates updated by business staff fits well as governed business data/policy.
- The fee calculation code and participating services are **logic and bean structure**, regardless of which of those two sources supplies the parameters.

**There is no rule saying "if it is in YAML, it must be technical configuration."** Business meaning and change lifecycle are the deciding criteria.

### 6.5. Can a Bean Hold Business Data?

Technically, a singleton service can have mutable fields, but **storing current order state in a singleton's field** commonly causes data cross-talk between requests, race conditions, and scaling issues across multiple instances. Business objects should travel via method arguments, transactions, or appropriate storage.

A bean may hold references to repositories, gateways, validators, immutable settings, or processing collaborators. A bean should not act as a shared temporary state bucket across all users without explicit synchronization and scoping.

### 6.6. Is Configuration Stored in a Database Still Configuration?

Possibly. **Storage location alone does not determine data type.** A table holding system-wide endpoints/timeouts can be a centralized configuration store. Conversely, a JSON file attached to a request containing an order is still business data. Consider ownership, scope of effect, update timing, and how the data is consumed.

## 7. Classifying with Four Questions

When encountering a variable, class, table, or code snippet whose role is unclear, ask:

1. **Does this value describe the environment or an entity/transaction?** For example, `http.client.timeout` describes how the app runs, whereas `order.paidAt` describes order state.
2. **Who is responsible for updating it?** Deployment pipelines/operations teams normally change configuration; developers change bean definitions; users and business workflows change order data.
3. **What must change to apply an update?** Change a property or restart the app; release new code to alter wiring; or execute a command/transaction to update business state?
4. **What is the scope of effect?** An application/environment; a Spring component; or a specific customer, order, or transaction session?

| Specific Case | Appropriate Classification | Why? |
| --- | --- | --- |
| `spring.datasource.url` | Application configuration | Determines which database to connect to per environment |
| `@Bean DataSource dataSource(...)` | Bean definition | Describes how Spring constructs and provides the object |
| `orders.status = "PAID"` | Business data | State of a specific order |
| `spring.jpa.show-sql` | Application configuration | Controls SQL logging behavior |
| `@Service OrderService` | Component/bean | Registers a class implementing use cases |
| Promo code entered by a user | Business input data | Tied to a transaction and requires validation |
| `shipping.gateway.timeout` | Application configuration | Technical constraint when calling an integration |
| `@ConditionalOnProperty` on a bean | Bean registration rule | Uses a property to decide bean existence |

## 8. Common Mistakes and How to Fix Them

**Mistake 1 — Hard-coding environment configuration inside `@Bean`.**

~~~java
@Bean
ShippingClient shippingClient() {
    return new ShippingClient(
        URI.create("https://production.example.invalid"),
        Duration.ofSeconds(3)
    );
}
~~~

This code couples the production endpoint directly into bean construction. Switching environments requires editing code or adding conditional branches. Move the endpoint and timeout to externalized configuration, bind them to strong types, and inject them into the bean factory as shown in section 3.

**Mistake 2 — Storing per-request data in a singleton service.**

~~~java
@Service
class CheckoutService {
    private String currentOrderId; // Incorrect when shared across requests
}
~~~

A shared field can be overwritten by another request. Pass the order ID as a method argument and load data from the repository within an appropriate use-case/transaction scope.

**Mistake 3 — Using properties to represent transaction state.**

Changing `order.123.status` via YAML deployment bypasses APIs, authorization, transactions, and auditing. Use a domain model and business data source with proper update commands.

**Mistake 4 — Assuming editing a YAML file updates running beans automatically.**

Spring Boot normally creates and binds configuration at startup. Updating without a restart requires designing a configuration reload mechanism and a way for components to pick up changes; many beans created from old values retain those values until an appropriate recreation/replacement mechanism runs.

**Mistake 5 — Confusing bean selection with per-transaction behavior selection.**

`@Profile` or `@ConditionalOnProperty` works well for deciding component types at startup. If an algorithm must vary per customer or per order at runtime, design a strategy/dispatcher driven by business data; do not create/destroy Spring beans per request.

**Mistake 6 — Storing secrets as public properties.**

Passwords and tokens can be bound through the same configuration mechanism, yet require access control, masking, rotation, and keeping them out of commits. Never use real values in documentation, test snapshots, or logs.

## 9. Designing and Testing Along Clear Boundaries

A maintainable design typically keeps these boundaries:

- **Settings classes** group properties by functional area and represent them with proper types (`URI`, `Duration`, integers, booleans). Constraints such as positive timeouts and valid URLs can be checked at startup.
- **Configuration/bean factory classes** wire dependencies, pick appropriate implementations, and configure clients; avoid putting complex business algorithms there.
- **Business services** receive dependencies via constructors, read/write domain data via repositories, and execute use cases; avoid reading environment variables directly or instantiating clients across methods.
- **Domain model and persistence** manage identity, state, rules, and data lifecycle; transaction handling sits at the appropriate business boundary.

Corresponding testing strategy:

1. **Configuration binding tests:** supply test-specific property values, assert `baseUrl` and `timeout` bind to the right types, and confirm missing/invalid values fail if validation is configured.
2. **Bean wiring tests:** build a Spring context with enabled/disabled configuration to verify `ShippingClient` is registered or omitted as intended; verify required dependents have alternative setups when integration is disabled.
3. **Business tests:** pass a concrete `ShippingOrder` into the use case, stub gateways/repositories as needed, and assert outcomes, state transitions, integrity, or business exceptions. You do not need to edit YAML for each test order.

For instance, changing a timeout in a test cannot replace testing "a canceled order must not be shipped." Similarly, mocking a `ShippingClient` does not verify binding of `shipping.gateway.timeout`. Each test should verify the exact layer of responsibility it targets.

## 10. Remembering Through a Scenario

Suppose the system sends orders through a shipping gateway:

- Operations increases the gateway call timeout from 3 to 5 seconds: **changing application configuration**.
- A developer swaps the HTTP client for another implementation and registers it with `@Bean`: **changing bean definition/wiring**.
- A customer edits the delivery address before the order is dispatched: **changing business data**.
- An administrator updates a regional fee schedule with an effective date: **changing business policy/data**, even if the table name includes the word "config".
- A property determines whether `ShippingClient` is created at startup: **configuration controlling a bean registration condition**, the intersection between the first two layers.

Keep three separate questions in mind when reading Spring Boot code: **where does the app get its values; which definitions does Spring use to create components; and which business data do those components process**. Answering all three makes it clear where properties, beans, and domain objects belong.
