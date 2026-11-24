# Distinguishing Manual Framework Configuration from Spring Boot Auto-Configuration

When building a Spring application, we need to create objects, wire dependencies, and configure infrastructure so components can work together. Spring Framework provides the IoC container and configuration mechanisms for developers to declare those components. Spring Boot builds on top of Spring Framework, adding the auto-configuration mechanism to automatically set up many common components based on libraries on the classpath, existing beans, and external configuration.

The main difference lies in the level of configuration the application must declare. With manual configuration, the developer explicitly creates and wires beans. With Spring Boot, the framework automatically provides default configurations when the required conditions are satisfied; the application only adds business-specific beans or properties. Both approaches can coexist in the same application.

## 1. What Roles Do Spring Framework and Spring Boot Play?

### Spring Framework

Spring Framework provides the foundation for Java applications, including:

- **IoC container:** creates, manages the lifecycle of, and wires objects (beans).
- **Dependency Injection:** supplies dependencies to a bean via constructor, setter, or field.
- **Java configuration:** uses **@Configuration** and **@Bean** to declare beans.
- **Component scanning:** discovers classes annotated with **@Component**, **@Service**, **@Repository**, and **@Controller**.
- **Integration modules:** supports web, data, transactions, messaging, and many other capabilities.

Spring Framework does not automatically guess all the infrastructure an application needs. In an application using plain Framework, the developer must choose and register the necessary components, such as connection factories, templates, channels, adapters, or message listeners.

### Spring Boot

Spring Boot uses Spring Framework and adds utilities to initialize applications faster:

- **Auto-configuration:** automatically declares common beans when matching conditions are met.
- **Starter dependencies:** groups commonly used libraries to simplify dependency declarations.
- **Externalized configuration:** reads configuration from application.properties, application.yaml, environment variables, command-line arguments, and supported sources.
- **Embedded server and standalone runnable applications:** for web applications, can be packaged and launched with a single command.
- **Observability and diagnostics:** helps inspect application health and why a configuration was or was not applied.

Spring Boot does not replace Spring Framework's IoC container, beans, or Dependency Injection. Auto-configuration itself is implemented using Spring's own configuration and conditional mechanisms.

## 2. How Does Manual Framework Configuration Work?

With manual configuration, the developer explicitly defines which beans must exist and how they depend on one another. XML or Java configuration can be used. In modern Spring applications, Java configuration is typically expressed with **@Configuration** and **@Bean**.

For example, a Java configuration might declare a service and its dependency:

~~~java
@Configuration
public class ApplicationConfig {

    @Bean
    public OrderRepository orderRepository() {
        return new JdbcOrderRepository();
    }

    @Bean
    public OrderService orderService(OrderRepository repository) {
        return new OrderService(repository);
    }
}
~~~

Spring invokes the **@Bean** methods, registers the results in the ApplicationContext, and automatically injects the **OrderRepository** bean into **OrderService**. The developer decides which implementation is used, how objects are constructed, and which dependencies are needed.

The application can initialize a context from that configuration:

~~~java
try (var context =
        new AnnotationConfigApplicationContext(ApplicationConfig.class)) {
    OrderService service = context.getBean(OrderService.class);
    service.processPendingOrders();
}
~~~

This is an example of initializing a Spring Framework context using Java configuration. To run, the project must have Spring Context and the corresponding business classes. The example is not a complete Spring Boot application.

Manual configuration is useful when:

- You want explicit control over how each bean is created and configured.
- The application has specialized infrastructure or custom integration requirements.
- You need to replace default implementations with organization-specific implementations.
- You are building a library or module that requires explicit configuration behavior.
- You want to reduce reliance on conventions or auto-configuration of a specific Spring Boot version.

In return, the developer is responsible for more details: dependencies, beans, connections, timeouts, converters, listeners, retries, and resource lifecycles.

## 3. How Does Spring Boot Auto-Configuration Work?

Auto-configuration is the mechanism by which Spring Boot registers default beans when conditions defined in configuration libraries are satisfied. An auto-configuration typically checks the following factors:

- **Whether a class is on the classpath:** whether the application added the required library.
- **Whether a bean already exists:** whether the application has already declared an equivalent bean.
- **Whether a property enables the feature:** whether external configuration permits that capability.
- **Whether other dependencies are ready:** a configuration may only activate when related beans or modules already exist.

Some commonly used conditional annotations:

| Annotation | Meaning |
|---|---|
| **@ConditionalOnClass** | Apply configuration only when the specified class is on the classpath |
| **@ConditionalOnMissingBean** | Create a default bean only when no matching bean exists yet |
| **@ConditionalOnBean** | Apply only when a required bean already exists |
| **@ConditionalOnProperty** | Apply only when a property has a matching value or state |

Illustrative example of an auto-configuration:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(ReportClient.class)
public class ReportAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    public ReportClient reportClient() {
        return new DefaultReportClient();
    }
}
~~~

This is an illustrative example of writing an auto-configuration, not a built-in Spring Boot configuration. If **ReportClient** is on the classpath and the application has not provided a **ReportClient** bean, this configuration creates a default implementation. If the application has already declared a matching bean, the **@ConditionalOnMissingBean** condition is no longer true and the default bean will not be created.

In an application, **@SpringBootApplication** is typically placed on the startup class:

~~~java
@SpringBootApplication
public class MessagingApplication {

    public static void main(String[] args) {
        SpringApplication.run(MessagingApplication.class, args);
    }
}
~~~

**@SpringBootApplication** combines three main roles:

- **@SpringBootConfiguration:** marks the main configuration class of the application.
- **@EnableAutoConfiguration:** enables the auto-configuration mechanism.
- **@ComponentScan:** scans components in the startup class's package and its subpackages.

Component scanning and auto-configuration are two different mechanisms. Component scanning finds components declared by the application. Auto-configuration applies library configurations registered by Spring Boot when their corresponding conditions hold.

## 4. Comparison Through a Messaging Example with RabbitMQ

The **spring-messaging** module defines common abstractions such as **Message**, **MessageHeaders**, **MessageChannel**, **MessageHandler**, and **MessageBuilder**. These abstractions describe message structure and exchange within an application. They do not automatically create connections to RabbitMQ, Kafka, or another message broker.

To communicate with RabbitMQ, the application needs an integration library such as Spring AMQP. The example below uses RabbitMQ to show clearly which parts are configured by the developer and which parts Spring Boot can auto-configure.

### 4.1. Manual Configuration with Spring Framework

In an application without Spring Boot auto-configuration, we can explicitly declare the connection factory, template, admin, and broker topology.

Example Java configuration with Spring AMQP:

~~~java
@Configuration
public class RabbitManualConfiguration {

    @Bean
    public CachingConnectionFactory connectionFactory() {
        CachingConnectionFactory factory =
                new CachingConnectionFactory("localhost");
        factory.setUsername("guest");
        factory.setPassword("guest");
        return factory;
    }

    @Bean
    public RabbitTemplate rabbitTemplate(
            ConnectionFactory connectionFactory) {
        return new RabbitTemplate(connectionFactory);
    }

    @Bean
    public RabbitAdmin rabbitAdmin(
            ConnectionFactory connectionFactory) {
        return new RabbitAdmin(connectionFactory);
    }

    @Bean
    public Queue ordersQueue() {
        return new Queue("orders.created", true);
    }

    @Bean
    public DirectExchange ordersExchange() {
        return new DirectExchange("orders");
    }

    @Bean
    public Binding ordersBinding(
            Queue ordersQueue,
            DirectExchange ordersExchange) {
        return BindingBuilder.bind(ordersQueue)
                .to(ordersExchange)
                .with("order.created");
    }
}
~~~

The beans in the example have specific responsibilities:

- **CachingConnectionFactory** manages connections to RabbitMQ.
- **RabbitTemplate** provides APIs to send and receive messages in request/reply style or standard message sending.
- **RabbitAdmin** helps declare queues, exchanges, and bindings on the broker.
- **Queue**, **DirectExchange**, and **Binding** describe the topology the application needs.

The example uses guest/guest credentials for local RabbitMQ for learning purposes. Production environments should obtain credentials from environment variables or a secret store and configure proper security.

To use this configuration snippet, the project needs the corresponding Spring Context and Spring AMQP/RabbitMQ dependencies. This is an illustrative Spring Java configuration, not a standalone program that can be compiled with only the JDK.

### 4.2. Using Spring Boot Auto-Configuration

With Spring Boot, we add the **spring-boot-starter-amqp** dependency. The starter brings the required RabbitMQ integration libraries onto the classpath. Spring Boot can automatically configure common infrastructure beans such as the connection factory, RabbitTemplate, and AmqpAdmin when the corresponding conditions are met.

Declare connection settings in **application.yaml**:

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: guest
    password: guest
~~~

The startup class can declare the business topology:

~~~java
@SpringBootApplication
public class MessagingApplication {

    public static void main(String[] args) {
        SpringApplication.run(MessagingApplication.class, args);
    }

    @Bean
    public Queue ordersQueue() {
        return new Queue("orders.created", true);
    }

    @Bean
    public DirectExchange ordersExchange() {
        return new DirectExchange("orders");
    }

    @Bean
    public Binding ordersBinding(
            Queue ordersQueue,
            DirectExchange ordersExchange) {
        return BindingBuilder.bind(ordersQueue)
                .to(ordersExchange)
                .with("order.created");
    }
}
~~~

We still declare the queue, exchange, and binding because this is business-specific topology. Spring Boot assists with common connection infrastructure based on the provided dependencies and properties.

A service can send messages using the injected **RabbitTemplate**:

~~~java
@Service
public class OrderPublisher {

    private final RabbitTemplate rabbitTemplate;

    public OrderPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publishOrderCreated() {
        rabbitTemplate.convertAndSend(
                "orders",
                "order.created",
                "{"orderId":"ORD-42"}"
        );
    }
}
~~~

A consumer can receive messages from the queue:

~~~java
@Component
public class OrderListener {

    @RabbitListener(queues = "orders.created")
    public void handle(String payload) {
        System.out.println("Received: " + payload);
    }
}
~~~

For the send and receive examples to work, a running RabbitMQ instance and compatible Spring Boot/Spring AMQP dependencies are required. A String payload is used here to avoid having to configure an additional JSON message converter. In real applications, clearly define schemas, converters, and payload versions when exchanging business objects.

### 4.3. What Is Automated and What Still Must Be Configured?

| Component | Manual Spring Framework configuration | Spring Boot with auto-configuration |
|---|---|---|
| RabbitMQ dependencies | Manually add required libraries | Can use starter to group dependencies |
| ConnectionFactory | Manually declare and configure bean | Auto-configured per classpath and properties |
| RabbitTemplate | Manually declare bean and wire it | Provided by default when conditions are met |
| RabbitAdmin | Manually declare if needed | Can be auto-configured when appropriate |
| Queue/exchange/binding | Manually declare per business needs | Still typically declared by the application |
| Host, port, credentials | Manually read and assign to beans | Can be declared via spring.rabbitmq.* |
| Message payload and schema | Application designs itself | Application still designs itself |
| Message processing logic | Manually write handler/listener | Application still writes handler/listener |

This table describes typical setups. Whether a specific bean is created also depends on the Spring Boot version, dependencies, properties, and beans already supplied by the application.

## 5. Mechanism for Overriding Default Configuration (Back-Off)

An important principle of Spring Boot is that auto-configuration generally allows the application to replace default beans. When the application provides its own bean, certain auto-configurations may stop creating the corresponding default bean.

For example, if the application declares its own **RabbitTemplate**, the auto-configuration with a missing-bean condition for it will no longer create the default **RabbitTemplate**. Other automatic beans such as the connection factory can still be kept if their conditions remain true.

This is called **back-off**. Do not assume that creating one custom bean disables all auto-configuration. Each configuration and each bean has its own conditions.

Example of replacing the default template:

~~~java
@Configuration
public class CustomRabbitConfiguration {

    @Bean
    public RabbitTemplate rabbitTemplate(
            ConnectionFactory connectionFactory) {
        RabbitTemplate template =
                new RabbitTemplate(connectionFactory);
        template.setMandatory(true);
        return template;
    }
}
~~~

The application can customize the template for requirements such as message converters, confirms/callbacks, or routing behavior. You need to understand clearly which default bean will be replaced and which beans Boot still provides.

If you want to completely exclude a specific auto-configuration, you can use the **spring.autoconfigure.exclude** property or the **exclude** attribute on **@SpringBootApplication**. Only do this once you have identified the exact auto-configuration to exclude and have a plan to supply replacement components yourself.

## 6. Property Configuration and Precedence

Spring Boot allows externalizing configuration outside source code. With RabbitMQ, we can place host, port, username, and password in **application.yaml** or **application.properties**.

In deployment environments, sensitive information should be passed via environment variables or a secret store. Example YAML using default values for a local environment:

~~~yaml
spring:
  rabbitmq:
    host: localhost
    port: 5672
    username: guest
    password: guest
~~~

Spring Boot's external configuration sources have a precedence order. For example, environment variables or command-line arguments can override values in configuration files according to Boot's property source rules. Thus, the same application.yaml file can be used across multiple environments without modifying source code.

Distinguish Boot properties from manually configured beans. Properties only take effect when the corresponding configuration reads them. If we create a connection factory manually and do not bind it to the necessary properties, changing **spring.rabbitmq.host** may not affect the manual bean.

## 7. When to Choose Which Approach?

Manual configuration is suitable when:

- The application needs exact control over every bean and its lifecycle.
- You need to configure multiple brokers, multiple connection factories, or complex topology.
- There are special security, connection, or routing requirements.
- Integrating into a Spring Framework application that does not use Boot.
- You want minimal configuration, bringing in only the components actually needed.

Spring Boot auto-configuration is suitable when:

- Starting a new Spring Boot application.
- Using common integrations such as RabbitMQ, Kafka, JMS, or web.
- Wanting to reduce boilerplate and use defaults tested by the ecosystem.
- Needing different configurations across development, testing, and deployment environments.
- Wanting to add capabilities through dependencies and properties, then customizing only the necessary business parts.

In many applications, a reasonable approach is combining both: let Boot create the default infrastructure, while the application declares specific queues, exchanges, listeners, converters, or custom business beans.

## 8. How to Check Why Auto-Configuration Was Applied or Skipped

When an expected bean does not appear, check in order:

1. Is the dependency or starter actually on the classpath?
2. Does the property have the right name, right profile, and right value?
3. Is there any custom bean causing the **@ConditionalOnMissingBean** condition to no longer be satisfied?
4. Was the configuration excluded via **exclude** or **spring.autoconfigure.exclude**?
5. Does the package containing the application class cover the components to be scanned?
6. Is the broker running and are the connection details correct?

You can start the application with the **--debug** option to view the Condition Evaluation Report. This report shows which conditions many auto-configurations matched or failed to match. If Spring Boot Actuator is present and the endpoint is enabled, secured, and exposed appropriately, the **/actuator/conditions** endpoint also provides information about configuration conditions.

Some common mistakes:

- **Missing starter or client library:** the conditional class is not on the classpath, so auto-configuration does not run.
- **Wrong property:** Boot creates the bean, but connects to the broker with the wrong host, port, or credentials.
- **Creating duplicate or unintended replacement beans:** a custom bean prevents the default bean from being created.
- **Confusing component scan with auto-configuration:** a component is not found because its package lies outside the scan scope.
- **Expecting Boot to create business topology automatically:** the application still must define queues, topics, exchanges, bindings, or subscriptions as required.
- **Confusing abstractions with transport:** spring-messaging has Message and MessageChannel, but does not by itself provide a broker or guarantee durable message storage.

## 9. Takeaways When Designing Messaging Applications

When reading a Spring configuration, identify which beans come from the application, which are provided by integration libraries, and which are auto-configured by Boot. Then check the corresponding dependencies, properties, and bean creation conditions.

With messaging, clearly distinguish three layers:

1. **Abstraction:** Spring Messaging's Message, MessageHeaders, MessageChannel, and MessageHandler types.
2. **Transport/integration:** libraries connecting to RabbitMQ, Kafka, JMS, or other systems.
3. **Application behavior:** payload, schema, queue/topic, routing, listeners, and business logic.

Manual configuration gives you explicit control over every component. Spring Boot auto-configuration reduces the work of setting up common components by applying conditional configurations. Understanding the boundary between these three layers helps you know what to declare yourself, what to delegate to Boot, and how to customize without accidentally breaking default configurations.