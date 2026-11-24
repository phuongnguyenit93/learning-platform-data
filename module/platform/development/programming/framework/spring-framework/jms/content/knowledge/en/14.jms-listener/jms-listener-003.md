# The Default Name jmsListenerContainerFactory

> **Topic:** `@JmsListener` in Spring Framework JMS. If a method is annotated with `@JmsListener` **without declaring `containerFactory`**, Spring's listener registration mechanism looks by default for **a Spring bean named exactly `jmsListenerContainerFactory`**. This is a *bean naming convention for selecting a factory*, not a queue name, not the name of a listener thread, and it does not mean plain Spring Framework always creates that bean automatically.

## 1. Core Answer

Example:

~~~java
@Component
public class OrderConsumer {

    @JmsListener(destination = "orders.inbox")
    public void onOrder(String body) {
        System.out.println(body);
    }
}
~~~

Here there is no `containerFactory = ...`. With standard `@EnableJms` infrastructure, Spring looks up the bean named:

~~~text
jmsListenerContainerFactory
~~~

That bean implements `org.springframework.jms.config.JmsListenerContainerFactory<?>`; a typical example is `org.springframework.jms.config.DefaultJmsListenerContainerFactory`. The factory creates **a message listener container for the endpoint**. The container manages the JMS connection/session/consumer and invokes the `onOrder` method when a message arrives.

**Distinguish three names:**

| Component | Example | Role |
| --- | --- | --- |
| **Factory bean name** | `jmsListenerContainerFactory` | Used by `@JmsListener` to create the container when no other name is specified |
| **Destination/queue name** | `orders.inbox` | Broker message address that the consumer listens to |
| **Listener endpoint ID** | `ordersListener` (if `id` is set) | Used with `JmsListenerEndpointRegistry` to look up/manage the endpoint's container |

A bean of the right type **with a different name**, such as `myJmsFactory`, does not automatically become the default factory for an annotation that omits `containerFactory` just because it is the only bean. In Spring JMS, the default lookup branch is **by name** unless you configure a custom default via `JmsListenerConfigurer`. This is also why `@Primary` or a `@Qualifier` used for ordinary field injection does not replace the default naming rule.

## 2. How Does the Factory Lookup Mechanism Work?

Spring enables annotation support via `@EnableJms` or Spring Boot's auto-configuration mechanism. Methods with `@JmsListener` are discovered and registered as JMS listener endpoints.

~~~text
Spring ApplicationContext
   |
   +-- Bean: connectionFactory
   |      -> Jakarta JMS ConnectionFactory, connects to the broker
   |
   +-- Bean: jmsListenerContainerFactory
   |      -> DefaultJmsListenerContainerFactory
   |      -> config: connectionFactory, concurrency,
   |                 transaction, converter, error handling...
   |
   +-- Bean: orderConsumer
          |
          +-- @JmsListener(destination="orders.inbox")
                       |
                       v
          Spring finds default factory by NAME:
          "jmsListenerContainerFactory"
                       |
                       v
          factory.createListenerContainer(endpoint)
                       |
                       v
          JmsListenerEndpointRegistry
             -> manages a listener container for the endpoint
                       |
                       v
          Broker -> consumer -> orderConsumer.onOrder(...)
~~~

**Common point of confusion:** `JmsListenerContainerFactory` is the **factory** that creates containers, not the running container itself. The `JmsListenerEndpointRegistry` bean holds the containers created for annotated endpoints; they do not necessarily appear as standalone Spring beans named after the listener ID.

At runtime, the actual processing path consists of:
1. Spring creates and configures the JMS provider's `ConnectionFactory`.
2. Spring detects the default factory bean or the specified factory.
3. The annotation infrastructure creates a listener endpoint from the `@JmsListener` method.
4. The factory creates a `MessageListenerContainer` for the endpoint.
5. The registry manages start/stop and lookup by listener `id`.
6. The container receives messages from the broker and dispatches them to the Java method.

`JmsListenerContainerFactory` is **unrelated** to `JmsTemplate.convertAndSend` in terms of selecting a producer: `JmsTemplate` uses `ConnectionFactory` to send, whereas `@JmsListener` uses a listener container factory to receive asynchronously.

## 3. Selection Rules: Three Paths

| Declaration | Which factory is chosen? | When to use |
| --- | --- | --- |
| `@JmsListener(destination = "orders.inbox")` | **Default** factory: usually bean `jmsListenerContainerFactory` | Most listeners share the same policy |
| `@JmsListener(destination = "orders.inbox", containerFactory = "criticalJmsFactory")` | Bean named **`criticalJmsFactory`** | Listener needs a different policy for concurrency, transactions, converter... |
| `JmsListenerConfigurer.configureJmsListeners(registrar)` + `registrar.setContainerFactoryBeanName("businessFactory")` | `businessFactory` becomes the default for endpoints that do not specify a factory, unless overridden by a specific factory | Want to change the app-wide default instead of naming the bean `jmsListenerContainerFactory` |

**Practical precedence order:** factory specified directly on the annotation → default explicitly configured on the registrar → `jmsListenerContainerFactory` bean name convention.

Example of two listeners in the same class:

~~~java
// Snippet: placed in a component-scanned Spring bean.
@JmsListener(destination = "orders.normal")
public void normal(String body) {
    // Uses default factory.
}

@JmsListener(
    destination = "orders.urgent",
    containerFactory = "criticalJmsFactory")
public void urgent(String body) {
    // Uses the bean named criticalJmsFactory.
}
~~~

This is an **illustrative snippet**, not a standalone Java class. An application with both listeners must have a valid default factory and an existing `criticalJmsFactory` bean. Changing `containerFactory` on the annotation **does not change the queue**; the destination name still comes from `destination`.

## 4. Plain Spring Framework vs. Spring Boot

### 4.1. Plain Spring Framework: The Naming Convention Does Not Create the Bean Automatically

When configuring a Spring Framework application without Spring Boot auto-configuration, you can use:

~~~java
package demo;

import jakarta.jms.ConnectionFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
public class JmsListenerConfiguration {

    @Bean("jmsListenerContainerFactory")
    public DefaultJmsListenerContainerFactory defaultFactory(
            ConnectionFactory connectionFactory) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setSessionTransacted(true);
        factory.setConcurrency("1-3");
        return factory;
    }
}
~~~

**Prerequisite:** `ConnectionFactory` must have its own bean provided by the application; this snippet does not configure the broker/credentials itself. The code illustrates the factory definition completely, but it is **not a standalone runnable application** without a JMS provider.

Here the Java method name is `defaultFactory`, **not `jmsListenerContainerFactory`**, yet thanks to `@Bean("jmsListenerContainerFactory")`, Spring creates the exact **bean name** the infrastructure looks for.

Equivalently, if you use:

~~~java
@Bean
public DefaultJmsListenerContainerFactory jmsListenerContainerFactory(
        ConnectionFactory connectionFactory) {
    DefaultJmsListenerContainerFactory factory =
            new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(connectionFactory);
    return factory;
}
~~~

then the default bean name is taken from the method name `jmsListenerContainerFactory`. This is also the pattern commonly seen in the Spring reference documentation.

**Common mistake:** writing:

~~~java
@Bean
public DefaultJmsListenerContainerFactory factory(
        ConnectionFactory connectionFactory) {
    DefaultJmsListenerContainerFactory result =
            new DefaultJmsListenerContainerFactory();
    result.setConnectionFactory(connectionFactory);
    return result;
}
~~~

This bean named `factory` **does not have the default name**. If a listener does not specify `containerFactory = "factory"` and no other default is configured, Spring may fail when registering endpoints. Do not try to fix this by adding `@Primary` and expecting default name-based lookup to change automatically.

### 4.2. Spring Boot: Usually Provides the Default Factory Automatically

With Spring Boot having a JMS starter/infrastructure and a valid `ConnectionFactory`, Boot can automatically create a default `DefaultJmsListenerContainerFactory` so that `@JmsListener` methods without `containerFactory` work without manually writing the bean.

Dependency example using Spring Boot 3.3.5 and Artemis:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
~~~

In an application with `@SpringBootApplication` and a listener bean:

~~~java
@Component
public class MyListener {
    @JmsListener(destination = "demo.default.queue")
    public void receive(String payload) {
        System.out.println(payload);
    }
}
~~~

Under matching auto-configuration conditions, Boot provides the `jmsListenerContainerFactory` bean. You then only need to configure the Artemis `ConnectionFactory` and the queue.

**Important limitation:** do not conclude that "Spring Boot **always** creates that bean". When the starter/JMS API/provider/ConnectionFactory is missing, auto-configuration is excluded, profiles do not match, or a custom `JmsListenerContainerFactory` causes the "missing bean" condition to no longer hold, the default bean may not appear. Spring Boot documentation states that **if no `JmsListenerContainerFactory` is defined, a default factory is auto-configured**; therefore, creating a differently named factory without checking auto-config conditions can break default listeners too.

When using Boot, custom factory configuration should be built using `DefaultJmsListenerContainerFactoryConfigurer` if you want to preserve the default behavior already applied by Boot (transaction/converter/resolver/recovery). Do not manually configure a new factory and **assume** it is 100% identical to the auto-configured factory.

### 4.3. Two Independent Configuration Groups

- **Producer:** `JmsTemplate` / `JmsMessagingTemplate` sends messages, configured via `ConnectionFactory` and the template's own settings.
- **Consumer:** `@JmsListener` / `DefaultMessageListenerContainer` receives messages, governed by `JmsListenerContainerFactory`.

Both can use the same `ConnectionFactory` from the JMS provider, but renaming `jmsListenerContainerFactory` will never make producers automatically use the listener factory.

## 5. Runnable Example: Proving the Default Name Directly in Spring Boot

This example uses **Java 17 + Spring Boot 3.3.5 + ActiveMQ Artemis**. We intentionally **do not define any `JmsListenerContainerFactory` bean** so Spring Boot can create the default factory. The program verifies the presence of a bean named `jmsListenerContainerFactory`, uses a `@JmsListener` without declaring `containerFactory`, and sends a String message to a test queue.

### 5.1. Prerequisites

- JDK 17+; Gradle installed or Gradle wrapper available.
- ActiveMQ Artemis broker at `tcp://localhost:61616` and account `demo/demo` for **an isolated learning environment**.
- **Anycast** queue `demo.default.factory` provisioned or test broker allows auto-creating queues. Do not use a production queue.
- Send and consume permissions for the demo user; ensure no other consumer competes for messages on the test queue.
- If running the broker via Docker, check that port 61616 is published and the broker is ready. Username/password `demo/demo` is a user-configured example, not the default of every image.

### 5.2. Directory Structure

~~~text
jms-default-factory/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/
    │   ├── DefaultFactoryApplication.java
    │   └── DemoListener.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-default-factory'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
~~~

`src/main/resources/application.yml`:

~~~yaml
spring:
  main:
    web-application-type: none
  artemis:
    mode: native
    broker-url: "tcp://localhost:61616"
    user: "demo"
    password: "demo"
~~~

`mode: native` prevents accidentally targeting an embedded broker. When using real credentials, supply them via `SPRING_ARTEMIS_USER`/`SPRING_ARTEMIS_PASSWORD` or secret management; do not commit secrets to the repo.

### 5.3. Application Sending a Message and Checking the Registry

`src/main/java/demo/DefaultFactoryApplication.java`:

~~~java
package demo;

import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.JmsListenerContainerFactory;
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
@EnableJms
public class DefaultFactoryApplication {

    private static final String QUEUE = "demo.default.factory";

    public static void main(String[] args) {
        SpringApplication.run(DefaultFactoryApplication.class, args);
    }

    @Bean
    ApplicationRunner demonstrate(
            ApplicationContext applicationContext,
            JmsTemplate jmsTemplate,
            JmsListenerEndpointRegistry registry,
            DemoListener demoListener) {

        return args -> {
            Object bean = applicationContext.getBean(
                    "jmsListenerContainerFactory");

            if (!(bean instanceof JmsListenerContainerFactory<?>)) {
                throw new IllegalStateException(
                        "Unexpected default factory bean type");
            }
            if (registry.getListenerContainer("default-demo-listener")
                    == null) {
                throw new IllegalStateException(
                        "Listener endpoint not registered");
            }

            String runId = UUID.randomUUID().toString();
            demoListener.expect(runId);

            jmsTemplate.convertAndSend(QUEUE, "probe:" + runId);

            if (!demoListener.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "No matching message received within 10s");
            }

            System.out.println(
                    "DEFAULT_FACTORY_BEAN=jmsListenerContainerFactory");
            System.out.println(
                    "LISTENER_ID=default-demo-listener");
            System.out.println("LISTENER_RECEIVED=true");
        };
    }
}
~~~

`src/main/java/demo/DemoListener.java`:

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class DemoListener {

    private final CountDownLatch received = new CountDownLatch(1);
    private volatile String expected;

    public void expect(String runId) {
        expected = "probe:" + runId;
    }

    @JmsListener(
            id = "default-demo-listener",
            destination = "demo.default.factory")
    public void onMessage(String body) {
        String expectedNow = expected;
        if (expectedNow != null && expectedNow.equals(body)) {
            received.countDown();
        }
    }

    public boolean await(long time, TimeUnit unit)
            throws InterruptedException {
        return received.await(time, unit);
    }
}
~~~

**Key points that make this test meaningful:**

1. The program **has no `@Bean jmsListenerContainerFactory`**; if Boot satisfies auto-configure conditions, that bean must exist.
2. `@EnableJms` is written explicitly to make enabling `@JmsListener` processing transparent, even though in a typical Boot setup it may already be auto-enabled.
3. `ApplicationRunner` runs only after the Spring context initializes. It checks the bean **by name**, then checks `JmsListenerEndpointRegistry` by the annotation's `id` — two distinct checks.
4. `DemoListener` does not set `containerFactory`. Thus it uses the verified default.
5. `runId` is generated per run, and the body `probe:<UUID>` ensures the listener only counts down when receiving the exact message from this test run.
6. `CountDownLatch` lets `ApplicationRunner` wait with a 10-second bound to observe the message reaching the callback; it is not a blocking `JmsTemplate.receive` call in HTTP.
7. `@JmsListener` uses a listener worker/background thread managed by the container. This is **asynchronous receiving** at the application code layer.
8. The test queue must be dedicated because old messages or other consumers can interfere with results. The demo listener uses no JMS selector, so it can consume old messages in the test queue without completing the latch.
9. There is no database or external business logic, so the output only proves bean/factory selection and that one message was processed in the demo, **not** end-to-end exactly-once semantics.
10. The UUID is not printed in standard output to keep result lines stable across runs.

### 5.4. Running and Results

At the project root with the broker ready:

~~~bash
gradle bootRun
~~~

When conditions are met, the lines **printed by the application** will be:

~~~text
DEFAULT_FACTORY_BEAN=jmsListenerContainerFactory
LISTENER_ID=default-demo-listener
LISTENER_RECEIVED=true
~~~

Logs from Spring Boot, the broker, and the listener container may also appear, with no ordering requirement relative to system logs. If the default bean does not exist, the program fails at `getBean(...)` instead of printing PASS. If the broker or ACL is wrong, no message is received and the program fails with a timeout/JMS error. This sample **does not claim to have been executed** in any specific environment.

Because the listener container is a long-lived component, the application may keep the process running after the PASS lines appear; stop with `Ctrl+C` when ending the demo.

### 5.5. When Is the Listener ID Used?

In the code `@JmsListener(id = "default-demo-listener")`:
- `id` is the endpoint/container name in the registry;
- `destination` is the queue;
- `containerFactory`, if declared, is the **factory bean name**.

`registry.getListenerContainer("default-demo-listener")` looks up the container for the endpoint, **not** the `jmsListenerContainerFactory` bean. If `id` is omitted, Spring generates an ID automatically; when you want to start/stop a single listener or test the registry, assign a stable ID.

## 6. Manually Defining the Default Factory with the Exact Name

If you do not want to use the auto-configured factory, create the bean explicitly with the conventional name. In Spring Boot 3.x, use `DefaultJmsListenerContainerFactoryConfigurer` to inherit Boot's usual defaults, then override the needed parameters.

Example **alternative snippet**—do not add this at the same time to the section 5 demo if you are demonstrating Boot auto-creation:

~~~java
package demo;

import jakarta.jms.ConnectionFactory;

import org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer;
import org.springframework.boot.jms.ConnectionFactoryUnwrapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
public class FactoryConfiguration {

    @Bean("jmsListenerContainerFactory")
    DefaultJmsListenerContainerFactory createDefaultFactory(
            ConnectionFactory connectionFactory,
            DefaultJmsListenerContainerFactoryConfigurer configurer) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();

        configurer.configure(
                factory,
                ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory));

        factory.setConcurrency("1-3");
        return factory;
    }
}
~~~

The method name `createDefaultFactory` **differs** from the bean name, which is fine because `@Bean("jmsListenerContainerFactory")` sets the exact name. With Spring Boot 3.3, the configurer import is `org.springframework.boot.autoconfigure.jms.DefaultJmsListenerContainerFactoryConfigurer`. In Spring Boot 4, the auto-configuration package changed to `org.springframework.boot.jms.autoconfigure...`, so imports must be updated when upgrading major versions.

`ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory)` gives the listener the opportunity to use the native connection factory instead of a Boot-created cached wrapper; this aligns with how Boot auto-configures containers in versions that provide that helper. Do not unwrap arbitrary wrappers/pools blindly: check compatibility and the broker's transaction infrastructure.

**Benefit of the configurer:** it applies Spring Boot defaults aligned with `spring.jms.listener.*`, converters, transaction managers, and related JMS beans (when present and conditions match). If you call `factory.setConnectionFactory(...)` directly and skip the configurer, you can lose some of Boot's default behaviors.

Do not arbitrarily set concurrency to hundreds just to process faster: each consumer holds session/connection resources, and downstream databases have their own limits.

## 7. What If You Want Two Different Factories?

Suppose normal messages and high-priority messages need different listener configurations. We create **two beans with two explicit names**, and specify which bean each listener uses.

~~~java
// @Configuration snippet in Spring Boot 3.x.
// Requires importing ConnectionFactory, @Bean, @Configuration,
// DefaultJmsListenerContainerFactory, and Boot configurer/unwrapper.
@Configuration
public class MultiListenerFactoryConfig {

    @Bean("jmsListenerContainerFactory")
    DefaultJmsListenerContainerFactory defaultFactory(
            ConnectionFactory connectionFactory,
            DefaultJmsListenerContainerFactoryConfigurer configurer) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();
        configurer.configure(
                factory,
                ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory));
        factory.setConcurrency("1-2");
        return factory;
    }

    @Bean("criticalJmsFactory")
    DefaultJmsListenerContainerFactory criticalFactory(
            ConnectionFactory connectionFactory,
            DefaultJmsListenerContainerFactoryConfigurer configurer) {

        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();
        configurer.configure(
                factory,
                ConnectionFactoryUnwrapper.unwrapCaching(connectionFactory));
        factory.setConcurrency("2-4");
        return factory;
    }
}
~~~

This is an illustrative snippet; if creating a real file, add the corresponding imports as in section 6. In the example, both factories are explicitly named so you do not depend on whether Spring Boot continues to auto-configure the default when a custom factory is present.

Listeners:

~~~java
// Snippet inside a Spring-discovered @Component.
@JmsListener(destination = "orders.normal")
public void normal(String body) {
    // Bean jmsListenerContainerFactory.
}

@JmsListener(
        destination = "orders.critical",
        containerFactory = "criticalJmsFactory")
public void critical(String body) {
    // Bean criticalJmsFactory.
}
~~~

**Conclusion:** `containerFactory = "criticalJmsFactory"` is the **String bean name** of the factory, not a class name. It also does not change the nature of the destination: if you need a separate queue, declare a separate `destination`. One factory can be used to create **multiple containers** for multiple listener methods.

**Resource note:** concurrency `"2-4"` is a configuration bound for listener containers to support scaling; it does not guarantee the broker always has four active consumers, does not guarantee message ordering, and is not an SLA. Benchmark and check JMS prefetch, transactions, and DB load.

## 8. Changing the Default Factory with `JmsListenerConfigurer`

If you want `@JmsListener` methods that **omit `containerFactory`** to default to a bean with a different name like `businessFactory`, Spring provides `org.springframework.jms.annotation.JmsListenerConfigurer`. It lets you customize `JmsListenerEndpointRegistrar`:

~~~java
package demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListenerConfigurer;
import org.springframework.jms.config.JmsListenerEndpointRegistrar;

@Configuration
@EnableJms
public class ListenerDefaultSelection
        implements JmsListenerConfigurer {

    @Override
    public void configureJmsListeners(
            JmsListenerEndpointRegistrar registrar) {

        registrar.setContainerFactoryBeanName("businessFactory");
    }
}
~~~

**Requirement:** a `JmsListenerContainerFactory<?>` bean named `businessFactory` **must exist** and already be configured with `ConnectionFactory`, transactions, converter, and appropriate policies. Otherwise, Spring cannot create containers for endpoints without an explicit factory.

You can also call `registrar.setContainerFactory(instance)` to set the factory directly. Specifying `@JmsListener(containerFactory = "otherFactory")` on a method still lets you choose a separate factory for that method.

**When should you use `JmsListenerConfigurer`?** When building an internal integration framework in your app, wanting to change the default under a unified policy, or registering endpoints programmatically. For simple apps, the default bean name `jmsListenerContainerFactory` is usually easier to understand, debug, and requires less configuration.

## 9. Common Configuration Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Startup reports `jmsListenerContainerFactory` not found | No bean with that name, listener omits `containerFactory`, and no other registrar default | Create `@Bean("jmsListenerContainerFactory")` or specify the factory explicitly |
| Bean `myFactory` exists but default `@JmsListener` fails | Different bean name; Boot may not create default because a factory exists | Rename the bean or write `containerFactory = "myFactory"` |
| Marked `@Primary` yet default still not found | Default lookup is by name, not primary bean selection | Use the exact bean name or `JmsListenerConfigurer` |
| `@JmsListener(containerFactory = "criticalFactory")` fails | Bean `criticalFactory` missing or not a `JmsListenerContainerFactory<?>` | Check exact bean name and type |
| `jmsListenerContainerFactory` exists but no messages arrive | Broker/destination/ACL/selector/autoStartup/transaction issue, not necessarily the bean name | Verify queue, permissions, registry, broker logs |
| Only added `spring-jms` and listener is not detected | Annotation infrastructure not enabled (`@EnableJms` or Boot auto setup) or class is not a Spring bean | Enable annotation support and component scan |
| Manually created factory lost transaction behavior | Did not use Boot configurer, did not configure transacted session | Use `DefaultJmsListenerContainerFactoryConfigurer` or configure explicitly |
| Listener bean exists but container has not started | `autoStartup=false`, registry stopped, context shutting down | Check `JmsListenerEndpointRegistry`, startup policy |
| Renamed `@Bean` method thinking it had no effect | Default bean name comes from the method name when name is omitted | Use `@Bean("jmsListenerContainerFactory")` for stability |
| Factory bean named properly yet only another listener runs | Some endpoints set another `containerFactory`; different selectors/concurrency | Inspect each annotation and its corresponding factory |
| Payload deserialization error after receiving | Factory uses a converter incompatible with the DTO body | Configure MessageConverter and dedicated schema |
| Upgrading Boot 3 to Boot 4 breaks configurer import | Boot 4 auto-config package changed | Update imports, dependency BOM, and retest |
| `registry.getListenerContainer("x")` returns null | Wrong `id` or endpoint was not registered | Set `@JmsListener(id="x", ...)` and check annotation scan |

**Do not diagnose by guessing a fixed exception class.** Spring Framework/Boot can report errors during endpoint configuration or context refresh with wrapped exceptions. Look for "bean name", "container factory", and "listener endpoint" in the cause chain rather than attributing every startup error to the broker.

## 10. Specific Debugging in ApplicationContext

When suspecting a missing factory, inspect both **name and type** for the bean:

~~~java
// Snippet: ApplicationContext injected into a Spring bean.
boolean exists =
        applicationContext.containsBean(
                "jmsListenerContainerFactory");

String[] factoryNames =
        applicationContext.getBeanNamesForType(
                JmsListenerContainerFactory.class);

System.out.println("DEFAULT_EXISTS=" + exists);
System.out.println("FACTORY_NAMES="
        + java.util.Arrays.toString(factoryNames));
~~~

Requires imports `org.springframework.context.ApplicationContext`, `org.springframework.jms.config.JmsListenerContainerFactory`, and `java.util.Arrays` (or fully qualified as above). This is a **snippet**, not a standalone Java file.

**How to interpret the results:**

| `DEFAULT_EXISTS` | `FACTORY_NAMES` list | Interpretation |
| --- | --- | --- |
| `true` | Contains `jmsListenerContainerFactory` | Default bean exists, but still verify config/registry next |
| `false` | Contains only `myFactory` | Custom factory exists, default-named bean is missing; update mapping |
| `false` | Empty | No factory bean yet; likely missing JMS auto-configuration/dependency |
| `true` | Multiple factories | Listeners without a factory usually use default; listeners with `containerFactory` use the named one |

**Note:** `containsBean` only verifies that a bean with that name exists; to verify the type, use `getBean(name, JmsListenerContainerFactory.class)` or check `instanceof`. Having a bean of the wrong type with the same name also causes errors.

### 10.1. Verifying the Listener Endpoint Was Created

~~~java
// Snippet: registry is an injected JmsListenerEndpointRegistry.
// Method annotation should specify id="ordersListener".
var container = registry.getListenerContainer("ordersListener");

if (container == null) {
    throw new IllegalStateException("Listener is not registered");
}
System.out.println("LISTENER_RUNNING=" + container.isRunning());
~~~

Requires the `JmsListenerEndpointRegistry` bean from JMS annotation infrastructure. `container.isRunning()` reports lifecycle status; it does **not** confirm the broker is delivering messages or that the handler succeeded in business processing. To inspect the number of containers, use `registry.getListenerContainers()` or `getListenerContainerIds()` depending on the Spring version.

### 10.2. Checking Boot Auto-Configuration

When a Boot app does not create the bean as expected:
1. Check actual dependencies to ensure `spring-jms` and a client/broker starter are present.
2. Verify the `ConnectionFactory` bean was created from the right broker configuration.
3. Check whether `@EnableJms` or JMS annotation infrastructure has been enabled.
4. Check for any custom `JmsListenerContainerFactory` across the entire application context: **a bean of that type with a different name can cause Boot to back off**.
5. Check `@Profile`, `@ConditionalOn...`, component scan, exclusions, and application configuration.
6. Use the Spring Boot condition evaluation report (e.g., run with `--debug`) to see which auto-configurations matched/did not match.
7. Check the registry to see if the endpoint is registered and the container is running.

Do not "fix" Spring's default by naming a bean `jmsListenerContainerFactory` while omitting `setConnectionFactory` or skipping the configurer: having the right name is only **one condition**; the factory still must be configured properly.

## 11. Prefer Using the Spring Boot Configurer for Custom Factories

For Spring Boot 3.x, `DefaultJmsListenerContainerFactoryConfigurer` helps a custom factory use the settings Boot can apply automatically:

- `ConnectionFactory` (usually the native underlying connection factory for listeners);
- `DestinationResolver` if provided;
- `MessageConverter` if a matching bean exists;
- `ExceptionListener` or related error/recovery settings when supported by Boot;
- `spring.jms.listener.*` settings and transaction strategy per Boot version;
- Afterward, you can fine-tune concurrency, receive timeout, backoff, or a custom error handler.

**Do not infer** that a bean with the default name is always transacted; that still depends on how the factory was created and configured. A manually created factory that skips the configurer and only calls `setConnectionFactory` will have Spring Framework defaults, which can differ from Spring Boot's transactional defaults.

When using local JMS transactions (e.g., `sessionTransacted=true`), a listener throwing an exception can trigger rollback/redelivery per policy. It **does not automatically create a distributed transaction with the database**. Critical business handlers need idempotency and dedicated retry/DLQ strategies.

## 12. Practical Question: Does Renaming a Factory Change Message Behavior?

Example:

~~~java
// Option 1: @Bean("jmsListenerContainerFactory")
DefaultJmsListenerContainerFactory createFactory(...) { ... }

// Option 2: @Bean("myFactory")
DefaultJmsListenerContainerFactory createFactory(...) { ... }
~~~

The two factories may have the exact same Java class and configuration, yet **an annotation without a specified factory only automatically discovers Option 1** by the naming convention. If a method has `containerFactory = "myFactory"`, it selects Option 2.

The bean name is only the **mechanism for selecting container configuration**; it does not determine:
- Whether messages reach the right queue (determined by destination/broker routing).
- Whether the user has permission to consume (determined by JMS provider authorization).
- Whether the payload converts to the right DTO (determined by MessageConverter/config).
- Whether the message is processed exactly once in the database (determined by transactions/idempotency).
- Whether a consumer processes multiple messages concurrently (determined by concurrency and broker/runtime).

Therefore, when encountering "listener does not run", separate two steps: **was the factory found and the container created?** Only then check **did the container start, connect to the broker, and receive messages from the right destination?**

## 13. Recommended Test Scenarios

| Test | Configuration | Expected Result |
| --- | --- | --- |
| Default bean created by Boot | Boot JMS starter + ConnectionFactory, no manual factory | `ApplicationContext` contains `jmsListenerContainerFactory` when auto-config conditions hold |
| Listener omits `containerFactory` | Default bean with standard name exists | Endpoint registers and receives messages on test queue |
| Differently named bean while listener omits factory | Only `myFactory` exists, no other default | Missing default; startup/registration may fail |
| Listener specifies `containerFactory = "myFactory"` | Bean `myFactory` exists | Endpoint uses the exact named factory |
| Factory bean has wrong type | Named `jmsListenerContainerFactory` but class does not implement factory interface | Configuration error, not silently accepted |
| Factory lacks `ConnectionFactory` | Right bean name but missing connection config | Container fails to initialize/operate normally |
| Two factories exist | Default and critical with different names | Endpoints choose per annotation or default |
| Using `JmsListenerConfigurer` | Registrar selects `businessFactory` as default | Endpoints omitting factory use the new default |
| Listener `autoStartup=false` | Factory exists, endpoint registered | Registry sees container but `isRunning()` is false |
| Wrong destination / ACL | Factory exists, container exists | Receives nothing or broker error; do not blame bean name |
| Retry/error handling | Listener throws exception, proper transacted/recovery policy | Observe rollback/redelivery per provider and config |
| Boot upgrade | Change Boot major version, keep bean name contract | Recompile imports, retest auto-config and listener registration |

### 13.1. Why Unit Tests Checking Only Type Are Not Enough

A passing `context.getBean(DefaultJmsListenerContainerFactory.class)` test does not prove the bean has the right name. To verify the default rule, assert:

~~~java
// Snippet in an integration test using Spring context.
assert context.containsBean("jmsListenerContainerFactory");
assert context.getBean("jmsListenerContainerFactory")
        instanceof JmsListenerContainerFactory;
~~~

This is illustrative syntax for checking the context; use `Assertions.assertTrue(...)`/AssertJ depending on your test framework. Then check that `JmsListenerEndpointRegistry` has the listener ID and send a test message through an isolated broker to verify the runtime path. **Do not** call the `@JmsListener`-annotated method directly to "prove" `containerFactory` works: calling the Java method bypasses the entire JMS infrastructure.

### 13.2. Do Not Touch Production Queues Just to Test Bean Names

To verify bean selection, you do not need to consume real messages. Use a test queue, dummy data, and a dedicated ID. If a listener points to a production queue, starting the Spring context just for a test can cause it to receive/ACK real messages. Use a test profile and disable autoStartup in context-inspection-only environments if needed, or isolate test config from business endpoints.

## 14. Common Questions in Interviews or Code Reviews

**Q: What is the default name?** — `jmsListenerContainerFactory`, matching exact camelCase as the bean name.

**Q: Is this a class or a bean?** — It is a **bean name**; the commonly used class is `DefaultJmsListenerContainerFactory` and the interface is `JmsListenerContainerFactory`.

**Q: What happens if this bean is not defined?** — Plain Spring Framework does not guarantee the bean exists. Spring Boot can auto-configure it when conditions are met; if missing, listeners that do not specify a factory may fail to register.

**Q: Can a different name be used?** — Yes. Use `@JmsListener(containerFactory = "otherFactory")` or configure the registrar default via `JmsListenerConfigurer`.

**Q: Why isn't `@Primary` enough?** — Default lookup relies on the **bean name**, not selecting a primary bean in type-based autowiring.

**Q: Does `@JmsListener(id = "foo")` change the factory?** — No. `id` identifies the endpoint container for registry/management.

**Q: Can `@JmsListener(destination = "foo")` and `containerFactory = "foo"` use the same String?** — They can happen to share the same string, but they have **two different meanings**: one is the JMS destination, and the other is the Spring factory bean name.

**Q: Is `@EnableJms` needed?** — In plain Spring Framework, it is the standard way to enable annotation processing. Spring Boot can auto-configure listener infrastructure; placing `@EnableJms` explicitly is still useful in demos to show intent. Inspect the actual context instead of guessing.

**Q: Is the factory a consumer thread?** — No. The factory creates the listener container; the container manages threads, connections, sessions, and polling/dispatch depending on the implementation.

**Q: Should you create multiple factories?** — When there is a genuine need for different policy configurations, such as destinations, concurrency, converters, or transactions/recovery. If all listeners are equivalent, a single default factory keeps things simple.

## 15. Checklist When Using `@JmsListener` in a Project

- [ ] Compatible JMS dependency for the Spring Framework/Boot version in use; Spring 6/Boot 3 uses `jakarta.jms`.
- [ ] Working `ConnectionFactory` with the right broker and credentials.
- [ ] Listener class is component-scanned/registered as a Spring bean.
- [ ] JMS annotation infrastructure enabled via `@EnableJms` or appropriate Boot auto-configuration.
- [ ] If omitting `containerFactory`, default bean `jmsListenerContainerFactory` exists or another registrar default is explicitly configured.
- [ ] If declaring `containerFactory = "name"`, exact bean name and type `JmsListenerContainerFactory<?>` match.
- [ ] When creating a manual factory in Boot, consider `DefaultJmsListenerContainerFactoryConfigurer`.
- [ ] Factory has appropriate connection factory, transaction policy, converter, and concurrency/recovery settings.
- [ ] `destination` is an actual queue/topic name; correct consume permissions, routing type, and selector.
- [ ] Listener has a stable `id` if managed through the registry.
- [ ] Verified container is registered, `isRunning()` is appropriate, and the broker actually delivers messages.
- [ ] Integration tests exist on a dedicated queue without ACKing production messages.
- [ ] Retry/DLQ/idempotency exist if message processing touches business data.
- [ ] Bean name is not confused with a JMS queue or `ConnectionFactory` name.

### Self-Check Questions

1. For `@JmsListener(destination = "orders")`, what default factory name does Spring look for?
2. Why might `@Bean public DefaultJmsListenerContainerFactory myFactory(...)` fail to serve a listener that omits `containerFactory`?
3. How do you set the default bean name even if the Java method is named `createDefaultFactory`?
4. What is the difference between `@JmsListener(id = "ordersListener")`, `destination = "orders"`, and `containerFactory = "factoryA"`?
5. Under what conditions can Spring Boot 3 auto-create the default bean? If you define a custom factory with another name, what should you check?
6. When should you use `JmsListenerConfigurer` instead of `@Bean("jmsListenerContainerFactory")`?
7. If the factory is found properly yet messages do not arrive, which layers should you check next?
8. Why does `registry.getListenerContainer("ordersListener")` not mean you are accessing a Spring bean named `ordersListener`?
9. Why does adding `@Primary` not change the default lookup name?
10. If a separate factory is needed for a queue with different transaction rules, how should the annotation and bean be declared?

**Remember:** **`jmsListenerContainerFactory` is the default bean name that `@JmsListener` uses when no factory is specified**. In plain Spring Framework, you need to provide/configure the factory; Spring Boot can auto-configure it when conditions are met. Renaming the bean must go together with updating `containerFactory` on the annotation or configuring the registrar default. Using the right name helps the listener **find the factory**, but successfully receiving messages also requires the right broker, destination, permissions, lifecycle, converter, and transactions.

## References

1. Spring Framework — Annotation-driven Listener Endpoints: https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html
2. Spring Framework 6.1 — `@JmsListener` API (containerFactory default): https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/jms/annotation/JmsListener.html
3. Spring Framework 6.1 — `JmsListenerEndpointRegistrar` API: https://docs.spring.io/spring-framework/docs/6.1.2/javadoc-api/org/springframework/jms/config/JmsListenerEndpointRegistrar.html
4. Spring Framework — Using Spring JMS (listener containers, transactions): https://docs.spring.io/spring-framework/reference/integration/jms/using.html
5. Spring Boot 3.x — JMS integration and listener factory auto-configuration: https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html
6. Spring Boot 3.x — `DefaultJmsListenerContainerFactoryConfigurer`: https://docs.spring.io/spring-boot/docs/3.0.8/api/org/springframework/boot/autoconfigure/jms/DefaultJmsListenerContainerFactoryConfigurer.html
7. Jakarta Messaging 3.1 Specification — JMS messaging and consumers: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
