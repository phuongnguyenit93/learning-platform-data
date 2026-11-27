# Separating Environment Configuration with Profiles and Environment Variables

A Spring Cloud Stream application typically runs across multiple environments: a personal development machine, test environments, staging, and production. Each environment may use a different broker, connection address, destination names, consumer groups, and credentials. If these values are scattered through source code or hardcoded in a single configuration file, deployments can easily target the wrong environment, become hard to test, and risk leaking secrets.

Spring Boot supports externalized configuration: the application reads configuration from files, environment variables, command-line arguments, and external configuration sources. Spring Profiles allow selecting a configuration set for the active environment. Spring Cloud Stream uses those properties to configure functions, bindings, destinations, consumers, and binders. The goal is to keep event-processing logic stable while supplying the right configuration for each deployment.

## 1. Separating Shared Configuration from Environment-Specific Configuration

First, classify configuration into three groups:

| Group | Examples | How to manage |
|---|---|---|
| Shared configuration | Application name, function definition, binding names, default retry attempts | Place in **application.yml**. |
| Environment-dependent configuration | Destination, consumer group, broker address, port, security mode | Place in profiles or pass from the deployment environment. |
| Secrets | Broker password, tokens, private keys, credentials | Retrieve from a secret store or platform secret injection; never commit to Git. |

Not every value that differs across environments needs its own profile. A useful rule is to use profiles for choices representing the nature of the environment, and environment variables for deployment-specific values such as hostnames, topic names, or credentials. For example, the **prod** profile can enable production-oriented settings, while **KAFKA_BOOTSTRAP_SERVERS** supplies the actual cluster address.

## 2. How Do Spring Profiles Work?

A profile is a label used to activate a group of settings. Spring Boot automatically reads **application.yml** and matching profile files such as **application-local.yml**, **application-test.yml**, or **application-prod.yml**. Profile configuration is applied when that profile is active and can override shared values.

Example file structure:

~~~text
src/main/resources/
  application.yml
  application-local.yml
  application-test.yml
  application-prod.yml
~~~

Activate a profile via an environment variable:

~~~bash
SPRING_PROFILES_ACTIVE=local
~~~

Or pass an argument when running the application:

~~~bash
java -jar order-stream.jar --spring.profiles.active=prod
~~~

When running with the **prod** profile, Spring Boot loads the shared configuration and then applies the configuration for **prod**. If the same property appears in both places, the value from the higher-priority configuration source is used. Environment variables and command-line arguments are commonly used to override values in configuration files.

Do not place **spring.profiles.active** inside a profile-specific configuration file such as **application-prod.yml**. Activate the profile from the runtime environment, command-line arguments, or a profile-independent configuration source. This avoids the situation where the application has to read a profile to know which profile to activate.

### Example Splitting Configuration Across Multiple Files

The **application.yml** file holds the shared part:

~~~yaml
spring:
  application:
    name: order-stream
  cloud:
    function:
      definition: orderProcessor
    stream:
      bindings:
        orderProcessor-in-0:
          destination: ${APP_ORDERS_DESTINATION:orders}
          group: ${APP_CONSUMER_GROUP:billing}
          consumer:
            max-attempts: ${APP_CONSUMER_MAX_ATTEMPTS:3}
~~~

The selected function can be a standard `Consumer`:

~~~java
@Bean
Consumer<OrderCreated> orderProcessor(OrderService orderService) {
    return event -> orderService.process(event);
}
~~~

The input binding name **orderProcessor-in-0** is derived by Spring Cloud Stream from the function name **orderProcessor**. **destination** specifies the target receiving events; **group** specifies the consumer group. Placeholders **${VAR_NAME:default_value}** allow reading values from environment variables while providing a default when the variable is unset.

The **application-local.yml** file can configure the development environment:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderProcessor-in-0:
          destination: orders-local
          group: billing-local
      kafka:
        binder:
          brokers: localhost:9092
~~~

The **application-prod.yml** file can specify production destination and group names while requiring the broker address to be supplied by the environment:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderProcessor-in-0:
          destination: ${APP_ORDERS_DESTINATION:orders}
          group: ${APP_CONSUMER_GROUP:billing-v1}
      kafka:
        binder:
          brokers: ${KAFKA_BOOTSTRAP_SERVERS}
~~~

In this example, the Kafka binder configuration sits under **spring.cloud.stream.kafka.binder**. If the application uses RabbitMQ or Pulsar, use the corresponding binder's connection properties. Do not copy Kafka properties to another binder because property names and meanings differ.

If the production profile is active but **KAFKA_BOOTSTRAP_SERVERS** is not supplied, a placeholder without a default value causes the application to fail resolving the required configuration. This is a helpful way to catch missing configuration at startup rather than silently connecting to an unexpected default broker.

### Using a Single YAML File with Multiple Documents

When differences are small, you can use multiple YAML documents in the same **application.yml**, separated by **---**. The **spring.config.activate.on-profile** property specifies which document applies:

~~~yaml
spring:
  application:
    name: order-stream
  cloud:
    function:
      definition: orderProcessor
    stream:
      bindings:
        orderProcessor-in-0:
          destination: orders
          group: billing
---
spring:
  config:
    activate:
      on-profile: local
  cloud:
    stream:
      bindings:
        orderProcessor-in-0:
          destination: orders-local
          group: billing-local
---
spring:
  config:
    activate:
      on-profile: prod
  cloud:
    stream:
      bindings:
        orderProcessor-in-0:
          destination: orders
          group: billing-v1
~~~

This works well for small modules with few differences. When each environment has many distinct broker, security, and observability settings, separate **application-{profile}.yml** files are usually easier to read and maintain.

## 3. Passing Deployment Values via Environment Variables

Environment variables allow the same application artifact to run in multiple places without repackaging. Spring Boot supports relaxed binding: an environment variable name can represent a property name in uppercase, replacing dots with underscores and removing hyphens. For example:

| Spring property | Corresponding environment variable |
|---|---|
| **spring.profiles.active** | **SPRING_PROFILES_ACTIVE** |
| **spring.cloud.stream.kafka.binder.brokers** | **SPRING_CLOUD_STREAM_KAFKA_BINDER_BROKERS** |
| **spring.rabbitmq.host** | **SPRING_RABBITMQ_HOST** |
| **spring.rabbitmq.username** | **SPRING_RABBITMQ_USERNAME** |
| **spring.rabbitmq.password** | **SPRING_RABBITMQ_PASSWORD** |
| **spring.pulsar.client.service-url** | **SPRING_PULSAR_CLIENT_SERVICEURL** |

The properties in the table illustrate the name-mapping rules. The application only uses a given property when the starter, binder, and Spring Boot version in use support that setting. With Spring Cloud Stream, confirm the documentation for the chosen binder, especially when configuring multiple binders in the same application.

You can also use application-defined variable names in placeholders. For instance:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderProcessor-in-0:
          destination: ${APP_ORDERS_DESTINATION:orders}
          group: ${APP_CONSUMER_GROUP:billing}
      kafka:
        binder:
          brokers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}
~~~

In a production deployment, the platform might supply values such as:

~~~bash
SPRING_PROFILES_ACTIVE=prod
APP_ORDERS_DESTINATION=orders
APP_CONSUMER_GROUP=billing-v1
KAFKA_BOOTSTRAP_SERVERS=kafka-1.internal:9092,kafka-2.internal:9092
~~~

Set these variables in container configuration, deployment manifests, or the platform's configuration management system. Do not write internal addresses, production group names, or credentials into shared documentation examples if they are sensitive organizational details.

## 4. Understanding Precedence When Multiple Configuration Sources Exist

A property can appear simultaneously in a YAML file, an environment variable, and a command-line argument. Spring Boot applies a property source precedence order; higher-priority sources override lower-priority ones. In typical operation:

1. Defaults in code or shared configuration form the baseline.
2. Application configuration files and profile files supply environment-oriented values.
3. Environment variables and external configuration sources supply deployment-specific values.
4. Command-line arguments can override configuration for a specific run.

This is a high-level overview; the full precedence order also depends on which configuration sources are enabled, the Spring Boot version, and how the application is launched. When a value is unexpected, inspect the actual configuration source rather than guessing from the YAML file alone.

For example, if **application-prod.yml** sets **group: billing-v1**, while the deployment environment sets **APP_CONSUMER_GROUP=billing-canary** and the YAML uses the placeholder **${APP_CONSUMER_GROUP:billing-v1}**, the application receives **billing-canary**. If a property is declared directly across multiple property sources, a matching environment variable can also override the file value.

Avoid creating too many hard-to-trace override layers. Clearly define which source owns each type of configuration: application files hold structure, profiles select environment behavior, and the deployment platform supplies concrete runtime values.

## 5. Managing Secrets Safely

Kafka, RabbitMQ, and Pulsar passwords, tokens, and private keys should never reside in a committed **application.yml**. If a credential is saved in Git, removing that line in a new commit does not remove the secret from repository history. Rotate any exposed credential and scrub history according to your organization's security process.

Common ways to inject secrets:

- Organizational or cloud-platform secret manager.
- Kubernetes Secrets mounted or injected into containers as environment variables per operational policy.
- Configuration files mounted from a secret management system with read permissions restricted to the application process.
- Workload authentication or service identity mechanisms, if supported by the broker and platform.

For example, Spring Boot can read environment variables for RabbitMQ connection details:

~~~yaml
spring:
  rabbitmq:
    host: ${RABBITMQ_HOST}
    port: ${RABBITMQ_PORT:5672}
    username: ${RABBITMQ_USERNAME}
    password: ${RABBITMQ_PASSWORD}
~~~

Actual values are provided at runtime. Do not print passwords, tokens, or the entire resolved configuration to logs. Be careful with diagnostic endpoints such as Actuator **env** and **configprops**: even though Spring Boot masks some sensitive values, exposing these endpoints externally can still leak configuration details. Only enable and secure them according to operational policy.

If using mounted secret files, Spring Boot supports config trees via **spring.config.import**, for example **optional:configtree:/run/secrets/**. Each file in the directory can supply one configuration property. Verify file naming conventions, permissions, and the platform's mount path before adopting it.

## 6. Separating Binder Configuration by Environment

Spring Cloud Stream bindings describe how functions connect to destinations. The binder is responsible for communicating with a specific messaging system. Therefore, when moving from local to production, check both layers:

- **Binding:** function definition, destination, group, consumer concurrency, partitioning, and retries.
- **Binder:** broker type, cluster addresses, credentials, TLS, authentication mechanisms, and broker-specific options.

For example, with Kafka, **spring.cloud.stream.kafka.binder.brokers** specifies broker addresses for the Kafka binder. With RabbitMQ, applications typically use RabbitMQ connection properties such as host, port, username, and password. With Pulsar, you need to configure the service URL and corresponding client/binder options. Exact property names depend on the starter and version in use.

If an application connects to multiple binders, name the binders explicitly and configure each separately according to the Spring Cloud Stream documentation for your project's version. Avoid letting a profile accidentally pick the wrong binder or point to a cluster shared between test and production.

In particular, `destination` and `group` are data-impacting settings. If two environments unintentionally share a destination and group, a test consumer can compete for messages with a production consumer. If a group changes in production, the broker may establish new consumption progress and replay events according to its policy. Treat changes to these values as operational changes that require testing.

## 7. Running and Testing per Environment

For a local environment, you can activate the profile and provide the broker address on the development machine:

~~~bash
SPRING_PROFILES_ACTIVE=local
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
~~~

On Windows PowerShell, the syntax to set variables for the current session is:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "local"
$env:KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
java -jar ./target/order-stream.jar
~~~

In a container, declare the same variables in the **environment** section or through the platform's secret/config mechanism. Do not bake production values into the image because the same image should be promoted consistently across deployment stages.

Profile testing can be performed with a Spring Boot test:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class OrderProcessorConfigurationTest {

    @Test
    void loadsTestProfile() {
        // Verify the test configuration and required bindings.
    }
}
~~~

Configuration tests should confirm at least:

1. The intended profile is actually active.
2. The function definition points to the right processing function.
3. The input binding has the expected destination and group.
4. The active binder matches the broker type provided by the environment.
5. Required values such as broker addresses and credentials are fully supplied.
6. Test configuration cannot accidentally point to a production destination or group.

For integration tests, use a dedicated test broker or appropriate service container. Do not only verify that the application starts successfully: send a sample message and confirm the consumer receives the right event from the right destination. When testing configuration failures, intentionally omit a required variable to ensure the application stops with a clear error message.

## 8. Common Configuration Mistakes

| Symptom | Possible cause | How to resolve |
|---|---|---|
| Application always uses local config | Profile is not activated or **SPRING_PROFILES_ACTIVE** was not passed to the process. | Inspect variables inside the actual container/process and the active profiles logged at startup. |
| Destination does not change | Wrong binding name, profile not loaded, or placeholder variable does not exist. | Cross-check function and binding names, active profiles, and variable names. |
| Consumer receives no events | Wrong broker, destination, group, permissions, or binder configuration. | Check created bindings, connection logs, and actual resources on the broker. |
| Test consumer receives production messages | Two environments share a destination or group. | Separate destinations/groups and verify effective configuration before running. |
| Application starts but uses an unintended default value | Placeholder has a fallback unsuitable for the deployment environment. | Remove fallbacks for mandatory production values or validate configuration at startup. |
| Credentials are not picked up | Wrong variable name, wrong secret mount, or insufficient read permissions. | Check property names, process environment, and permissions; do not log secret values. |
| Switching profiles causes events to be reprocessed | Group or subscription changed, creating new consumption progress. | Evaluate offset/cursor positions and replay policy before deploying. |

A subtle mistake is naming an environment variable close to—but not quite matching—the mapping rules. For deeply structured Spring properties or keys containing hyphens, follow the relaxed binding rules carefully or use placeholders with simple application-controlled variable names. Do not assume every YAML key can be converted to an environment variable simply by replacing dots arbitrarily.

## 9. Recommended Pre-Deployment Workflow

1. Identify the profile to activate and specify it explicitly in deployment configuration.
2. Put shared properties in **application.yml**; place only true differences in profile files.
3. Move broker addresses, environment-varying destinations, and credentials to environment variables or a secret store.
4. Verify function, binding, destination, and group names in each environment.
5. Confirm the binder and target broker match the environment.
6. Run configuration tests and integration tests against a test broker.
7. Check startup logs, permissions, and connection metrics before scaling up consumer instances.
8. Treat group, destination, or security policy changes as operational changes with a rollback plan.

Short checklist:

- [ ] **SPRING_PROFILES_ACTIVE** is explicitly set at deployment time.
- [ ] Profile files contain only necessary environment differences.
- [ ] No passwords, tokens, or private keys exist in the repository.
- [ ] Mandatory placeholders do not silently fall back to defaults in production.
- [ ] Each binding points to the environment's intended destination and group.
- [ ] The binder connects to the right cluster and uses appropriate security mechanisms.
- [ ] The test profile cannot receive production events.
- [ ] Group/destination changes have been evaluated for impact on consumption progress and replay.
- [ ] Logs and management endpoints do not leak secrets.

Separating configuration by profiles and environment variables enables the same Spring Cloud Stream application to run consistently across environments. Profiles select settings by deployment purpose, environment variables provide per-run values, and secret stores protect credentials. When both bindings and binders are verified, the development team can deploy the same artifact with the appropriate destinations, consumer groups, and brokers without modifying event-processing logic.
