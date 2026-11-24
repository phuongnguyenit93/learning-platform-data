# `BeanFactory`, `ApplicationContext`, and Additional Services of Spring Core Container

## 1. The Big Picture: Who Creates and Wires Beans?

In a Spring application, the **IoC container** is responsible for instantiating, configuring, wiring, and managing objects registered as **Spring beans**. Business code typically declares dependencies through constructors rather than searching for or creating all collaborators itself.

Two key APIs in Spring Core Container:

- **`BeanFactory`** (`org.springframework.beans.factory.BeanFactory`): the foundational interface for retrieving beans by name or type and describing the container's dependency management capabilities.
- **`ApplicationContext`** (`org.springframework.context.ApplicationContext`): a higher-level interface **extending `BeanFactory`'s capabilities**, adding unified support for the environment, resources, internationalized messages, application events, and other startup/integration mechanisms.

An `ApplicationContext` can also be used as a `BeanFactory` to call `getBean(...)`, but **not every `BeanFactory` object is an `ApplicationContext`**.

~~~text
                  BeanFactory
        bean creation/lookup, dependencies, scopes
                       ^
                       | Extended API
                ApplicationContext
             /         |          \
       Environment  MessageSource  ResourceLoader
          profiles    i18n          Resource
                       |
              ApplicationEventPublisher
                    events
~~~

The diagram only shows major capabilities, not the entire interface inheritance hierarchy in the Spring library. Underneath, `ApplicationContext` still relies on bean factory components to instantiate and wire beans.

## 2. `BeanFactory`: Core Bean Management and Lookup Contract

`BeanFactory` defines familiar operations:

~~~java
Object bean = factory.getBean("orderService");
OrderService service = factory.getBean(OrderService.class);
boolean known = factory.containsBean("orderService");
boolean singleton = factory.isSingleton("orderService");
~~~

This is an **illustrative snippet**, assuming the `factory` variable and `OrderService` class already exist. Calling `getBean` may trigger bean creation depending on the container, scope, and current initialization state.

Responsibilities associated with a bean factory include:

1. Looking up beans by **name, type**, or a combination of name and type.
2. Applying bean creation configuration: constructors, factory methods, dependencies, and scopes.
3. Managing certain bean lifecycle aspects, such as initialization and destruction, when the container/bean factory is configured appropriately.
4. Reporting errors when a bean is missing, multiple matching beans exist, or dependency configuration cannot be resolved.

**Distinguishing interface and implementation class:** `BeanFactory` is an interface, not a constructor you call like `new BeanFactory()`. `DefaultListableBeanFactory` is a commonly used implementation when low-level operations are needed, such as manually registering a `BeanDefinition`.

A simple `BeanFactory` often creates a bean **when it is first requested**. However, this **does not mean every bean factory is always lazy**, nor does every `getBean` call create a new bean: that depends on scope.

Example:

~~~java
DefaultListableBeanFactory factory = new DefaultListableBeanFactory();
factory.registerBeanDefinition(
        "greeting", new RootBeanDefinition(Greeting.class));
Greeting greeting = factory.getBean(Greeting.class);
~~~

This snippet requires imports from `org.springframework.beans.factory.support` and a `Greeting` class with a suitable constructor. A full runnable example appears in section 6.

## 3. `ApplicationContext`: A Bean Factory in an Application Context

An `ApplicationContext` provides bean lookup like `BeanFactory` **plus** a set of services commonly needed in applications. Common implementations include:

| Context type | Typical use |
| --- | --- |
| `AnnotationConfigApplicationContext` | Initialized from `@Configuration` classes or registered component classes; suited for plain Java examples without web |
| `ClassPathXmlApplicationContext` | Reads XML configuration from the classpath when maintaining XML-based systems |
| `FileSystemXmlApplicationContext` | Reads XML configuration from a file-system style path per Spring rules |
| `GenericApplicationContext` | A context where bean definitions or customizers can be registered programmatically |
| `WebApplicationContext` | Variant for web application environments when Spring Web is present |

Spring Boot is not needed to create a context. **Spring Framework's `spring-context` already provides `ApplicationContext`**; Spring Boot adds higher-level auto-configuration and application startup.

Java configuration example:

~~~java
@Configuration
class AppConfig {
    @Bean
    Notifier notifier() {
        return new ConsoleNotifier();
    }

    @Bean
    OrderService orderService(Notifier notifier) {
        return new OrderService(notifier);
    }
}
~~~

This is an illustrative snippet; `Notifier`, `ConsoleNotifier`, and `OrderService` need to be defined. Spring sees the `Notifier notifier` parameter on `@Bean` and resolves the corresponding dependency bean. Concrete bean creation logic resides in the configuration class, kept separate from business code.

### Startup Lifecycle: Differences to Remember

Normally, when `refresh()` is called, `ApplicationContext` processes configuration, registers/installs relevant extensions, and **pre-instantiates singletons not marked lazy**. After `refresh()`, standard singleton beans are ready for use.

With a manually constructed `DefaultListableBeanFactory`, calling `getBean()` may be what instantiates a bean for the first time; processors/extensions must be registered or triggered appropriately. Therefore **do not conclude "`BeanFactory` lacks lifecycle, while `ApplicationContext` has lifecycle"**. Both have bean management mechanisms; the notable difference is **the degree of automatic setup and integration of application services**.

- `@Lazy` and scopes such as `prototype` can alter when a bean is created.
- `singleton` in Spring means **one instance per bean definition within each container**, not a JVM-wide singleton.
- Eager singleton initialization does not mean the application never creates objects later.
- An object created manually with `new` outside the container does not automatically become a Spring bean.

## 4. Key Additional Services

| Capability | Basic `BeanFactory` | `ApplicationContext` |
| --- | --- | --- |
| Bean lookup, DI, scopes | Yes | Yes |
| Bean definitions, instantiation, and lifecycle | Yes, via suitable implementation/config | Yes, plus automatic integration and discovery of many extension points on `refresh` |
| `Environment` / properties / profiles | Not a standard service on the `BeanFactory` interface | Yes, via `getEnvironment()` |
| `MessageSource` / i18n | Not a direct standard capability on the interface | Supported by context via `getMessage(...)` |
| `ResourceLoader` | Not a direct API on `BeanFactory` | `getResource(...)` |
| Publishing application events | Not a direct API on `BeanFactory` | `publishEvent(...)` |
| Context lifecycle management | Depends on implementation and usage | `refresh`, `close`, or `start`/`stop` depending on interface/implementation |
| Context hierarchy | Some bean factory mechanisms support a parent | Contexts can have a parent; name scope/visibility depends on configuration |

The table compares **API contracts and typical usage**, without claiming that similar capabilities cannot be integrated manually into a low-level `BeanFactory`.

### 4.1. `Environment`, Properties, and Profiles

`Environment` reads property sources such as system properties, environment variables, or `PropertySource`s added by the application. Contexts can use profiles to select beans suited to an environment:

~~~java
String appName = context.getEnvironment()
                        .getProperty("app.title", "Untitled");
~~~

This is an illustrative snippet with an already created `context`. If you want to configure profiles, you normally need to **set profiles before calling `refresh()`**. For example:

~~~java
context.getEnvironment().setActiveProfiles("dev");
context.register(AppConfig.class);
context.refresh();
~~~

A bean marked `@Profile("dev")` is registered only when the profile condition matches. **Profiles do not guarantee security**, are not a mechanism to automatically hide configuration secrets, and a profile name alone does not create a bean if no matching definition exists.

With multiple configuration sources, understand property source precedence. Duplicate keys can be overridden by higher-priority sources when queried.

### 4.2. `MessageSource`: Locale-Based Messages

`ApplicationContext` implements `MessageSource`, providing:

~~~java
String text = context.getMessage(
        "order.saved", new Object[]{"A01"}, Locale.US);
~~~

Used to look up text by key and arguments for a given locale. If no matching message code exists and no default is supplied, the API may throw `NoSuchMessageException`.

When configured as a bean, the special name **`messageSource`** is used by the context to identify the application's message source. You can use `ResourceBundleMessageSource` for properties files across multiple locales, or `StaticMessageSource` for examples/tests without external files.

`MessageSource` handles **display messages**; it does not replace `Environment` for arbitrary configuration properties.

### 4.3. `ResourceLoader`: Unified Resources

~~~java
Resource resource = context.getResource(
        "classpath:demo/SpringServicesDemo.class");
boolean exists = resource.exists();
~~~

This is an illustrative snippet; `Resource` is in `org.springframework.core.io`. Spring supports prefixes such as `classpath:` and `file:` per resource loader rules and the specified path. `Resource` does not mean every source can be converted to `java.io.File`:

- Resources inside a JAR can be read via a stream without necessarily having a regular OS file path.
- If you need to read contents, use `getInputStream()` and **close the stream** after use.
- `getResource` locates a single resource; finding multiple resources by pattern is an advanced capability of `ResourcePatternResolver`, and should not be assumed for arbitrary URLs.

### 4.4. `ApplicationEventPublisher`: In-Application Events

A context can publish events:

~~~java
context.publishEvent(new OrderSavedEvent(source, "A01"));
~~~

A registered `ApplicationListener<OrderSavedEvent>` or `@EventListener` method can receive the notification. **By default, the standard multicaster invokes listeners synchronously** on the publishing thread. Custom executors/listener setups can alter how events are dispatched; do not assume Spring events are a durable message queue, distributed transaction, or guaranteed retry mechanism.

Events reduce direct coupling between components at the notification step, yet listeners still execute within the process/container according to configuration. Avoid using events to hide required dependencies or turn business control flow into a hard-to-trace chain of side effects.

## 5. When to Use `BeanFactory` vs. `ApplicationContext`?

For most Spring applications, **`ApplicationContext` is the standard choice** because it integrates DI, lifecycle, and additional services. Working directly with `BeanFactory`/`DefaultListableBeanFactory` is useful when:

- Studying bean definitions, bean creation, and extension points of Spring Core Container.
- Writing framework/infrastructure code that needs low-level bean factory control.
- Building a small example to see the difference between the core API and a context.

Do not pick `BeanFactory` merely because it sounds "lighter" if the application actually needs `Environment`, messages, event listeners, and automatic lifecycle: wiring those yourself creates extra work. Nor should you spin up an entire context for small objects that do not need Spring management.

In business code, prefer **constructor injection** into service classes instead of passing `ApplicationContext` into every class and calling `getBean(...)` freely. Querying beans everywhere resembles **Service Locator**, hiding dependencies and making unit tests harder.

## 6. Runnable Example with Spring Framework 6 and Java 17

This example runs with **Spring Framework 6.2.0** and Maven, **without Spring Boot**, and needs no server, database, or Internet when the program runs. The first Maven build downloads dependencies if not already cached. Messages and configuration sources are defined directly in code so output is easy to verify.

### 6.1. Project Structure and `pom.xml`

~~~text
spring-services/
├── pom.xml
└── src/main/java/demo/SpringServicesDemo.java
~~~

Create `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>spring-services</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.SpringServicesDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 6.2. File `SpringServicesDemo.java`

~~~java
package demo;

import java.util.Locale;
import java.util.Map;

import org.springframework.beans.factory.support.DefaultListableBeanFactory;
import org.springframework.beans.factory.support.RootBeanDefinition;
import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ApplicationListener;
import org.springframework.context.MessageSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.support.StaticMessageSource;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.io.Resource;

public class SpringServicesDemo {

    // Simple object to try out low-level BeanFactory.
    public static final class Greeting {
        public String text() {
            return "hello";
        }
    }

    // ApplicationEvent subclass; plain event objects can also be used.
    public static final class OrderSavedEvent extends ApplicationEvent {
        private final String orderId;

        public OrderSavedEvent(Object source, String orderId) {
            super(source);
            this.orderId = orderId;
        }

        public String getOrderId() {
            return orderId;
        }
    }

    public static final class OrderListener
            implements ApplicationListener<OrderSavedEvent> {
        @Override
        public void onApplicationEvent(OrderSavedEvent event) {
            System.out.println("EVENT " + event.getOrderId());
        }
    }

    public static final class OrderService {
        private final ApplicationEventPublisher publisher;

        public OrderService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        public void place(String orderId) {
            System.out.println("ORDER " + orderId);
            publisher.publishEvent(new OrderSavedEvent(this, orderId));
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        // The bean name messageSource has special meaning in ApplicationContext.
        @Bean("messageSource")
        public MessageSource messageSource() {
            StaticMessageSource messages = new StaticMessageSource();
            messages.addMessage("order.saved", Locale.US,
                    "Saved order {0}");
            return messages;
        }

        @Bean
        public OrderListener orderListener() {
            return new OrderListener();
        }

        // Spring supplies ApplicationEventPublisher when creating the bean.
        @Bean
        public OrderService orderService(ApplicationEventPublisher publisher) {
            return new OrderService(publisher);
        }
    }

    public static void main(String[] args) {
        // Direct BeanFactory: register a bean definition manually.
        DefaultListableBeanFactory factory =
                new DefaultListableBeanFactory();
        factory.registerBeanDefinition(
                "greeting", new RootBeanDefinition(Greeting.class));
        System.out.println(
                "BeanFactory: " + factory.getBean(Greeting.class).text());

        // ApplicationContext: application-level configuration and services.
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {
            context.getEnvironment().getPropertySources().addFirst(
                    new MapPropertySource("demo",
                            Map.of("app.title", "OrdersDemo")));

            context.register(AppConfig.class);
            context.refresh();

            System.out.println("Environment: "
                    + context.getEnvironment().getProperty("app.title"));
            System.out.println("MessageSource: "
                    + context.getMessage("order.saved",
                            new Object[]{"A01"}, Locale.US));

            Resource resource = context.getResource(
                    "classpath:demo/SpringServicesDemo.class");
            System.out.println("Resource exists: " + resource.exists());

            context.getBean(OrderService.class).place("A01");
        }
    }
}
~~~

From the directory containing `pom.xml`, using **JDK 17+** and Maven:

~~~bash
mvn -version
mvn -q compile exec:java
~~~

The first line checks Maven/JDK; the second compiles and runs. **Stdout lines printed by the application, in order:**

~~~text
BeanFactory: hello
Environment: OrdersDemo
MessageSource: Saved order A01
Resource exists: true
ORDER A01
EVENT A01
~~~

Maven, logging, or the build environment may print their own messages; these are the **stdout lines explicitly printed by the example code**, without guaranteeing a terminal transcript is always limited to six lines.

### 6.3. Why Does This Output Occur?

1. `DefaultListableBeanFactory` registers `Greeting` using `RootBeanDefinition`; calling `getBean(Greeting.class)` requests an instance and prints `hello`.
2. `AnnotationConfigApplicationContext` creates a context without refreshing yet. We add a `MapPropertySource` to `Environment`, then register `AppConfig` and call `refresh()`.
3. `getEnvironment().getProperty("app.title")` looks up the key just added and returns `OrdersDemo`.
4. The special `messageSource` bean provides the template `Saved order {0}` for `Locale.US`; `getMessage` substitutes `A01` into position 0.
5. `classpath:demo/SpringServicesDemo.class` exists because Maven compiled the file onto the classpath; `Resource.exists()` returns `true`.
6. Spring creates `OrderService` with the `ApplicationEventPublisher` supplied by the context. `place("A01")` prints `ORDER A01` and publishes the event.
7. `OrderListener` is a bean implementing `ApplicationListener<OrderSavedEvent>`, so it receives the event and prints `EVENT A01` via the default synchronous multicast mechanism.
8. `try-with-resources` closes the context after the block. If beans have properly configured destruction callbacks, the container runs them according to their lifecycle.

The example intentionally uses **two separate containers**: `factory` to illustrate low-level `BeanFactory`; `context` to illustrate service integration. The `greeting` bean exists only in `factory`; it **does not automatically appear** in `context`.

## 7. Reading Design and Avoiding Misconceptions

### 7.1. `getBean` Does Not Replace Constructor Injection in Business Code

~~~java
// Avoid doing this pervasively in domain/service classes:
OrderService service = context.getBean(OrderService.class);
~~~

Calling this at **a bootstrap/demo boundary** is reasonable to retrieve an entry point. However, if every service holds an `ApplicationContext` and repeatedly calls `getBean`, the dependency graph becomes obscured.

A more stable pattern is declaring:

~~~java
public OrderService(Notifier notifier, OrderRepository repository) {
    this.notifier = notifier;
    this.repository = repository;
}
~~~

This is illustrative syntax; `Notifier` and `OrderRepository` must be defined. The bean factory/context can supply both dependencies through the constructor without business code needing to know about the context.

### 7.2. Metadata and Instances from an API Perspective

`BeanFactory` stores bean definitions and provides bean objects via `getBean(...)`; `ApplicationContext` uses that same foundation while preparing services such as environment, messages, resources, and events. A bean definition can exist before a bean instance, and `@Component`/`@Bean` only take effect when the relevant configuration is registered or scanned into the context. The lesson on *bean definitions and instances* covers scopes, aliases, and proxies in detail.

### 7.3. Differences in Creation Timing

| Scenario | Behavior to understand |
| --- | --- |
| `DefaultListableBeanFactory` just registered a bean definition, not yet `getBean` | Normally the instance does not need to be created yet |
| `ApplicationContext.refresh()` with non-lazy singletons | Typically pre-instantiates singletons during refresh |
| `@Lazy` | May defer creation depending on how the bean is requested and depended upon |
| `prototype` | Context/bean factory typically creates a new instance per request, without managing full destruction like singletons |
| Two separate `ApplicationContext`s with the same config | Do not necessarily share singleton instances across contexts |

If a bean has side effects during initialization, starting the context may trigger those side effects before code ever calls `getBean()`. Therefore, avoid performing hard-to-control I/O or unnecessarily long work inside constructors.

## 8. Common Errors When Using `ApplicationContext`

| Symptom / misconception | Cause to check and how to resolve |
| --- | --- |
| `NoSuchBeanDefinitionException` | Bean not registered, package not scanned, profile mismatch, or wrong name/type |
| `NoUniqueBeanDefinitionException` | Multiple candidate beans of the same type; distinguish with `@Qualifier`, `@Primary`, or valid configuration |
| `UnsatisfiedDependencyException` | Required dependency cannot be resolved; inspect root cause in the stack trace |
| `BeanCreationException` | Constructor, factory method, injection, or initialization threw an error |
| `NoSuchMessageException` | Missing key/locale in `MessageSource`; declare the message or an appropriate default |
| Resource does not exist | Wrong `classpath:`/`file:` prefix or wrong classpath/path |
| Event not received | Listener is not a bean, wrong event type, context not ready, or event published to a different context |
| Assuming `publishEvent` is always async | Standard multicaster is synchronous by default; async requires deliberate configuration |
| `@Profile` not taking effect | Profile not active before `refresh`, or component scan config excludes the class |
| Singleton bean has concurrency bugs | Singleton only governs instance count per container; thread safety must be designed explicitly |
| Closing context too early | Do not use context-managed beans/resources after lifecycle ends |
| Creating an object with `new` and expecting Spring annotations to work | Objects outside the container are not processed as managed beans |

Be sure to distinguish **bean configuration errors** from business API errors. For example, a missing `OrderService` bean causes a startup/lookup failure; an empty `orderId` argument is a validation error in business code, not something `ApplicationContext` guesses on its own.

## 9. Self-Check Knowledge Questions

**Question 1. Does `ApplicationContext` completely replace `BeanFactory`?**

Not in the sense of invalidating `BeanFactory`. `ApplicationContext` **inherits bean lookup capabilities** and adds application-level services. It uses the bean factory mechanism to execute bean management.

**Question 2. Why do Spring users usually work with `ApplicationContext`?**

Because besides DI/lookup, the context integrates environment configuration, i18n message lookup, resource access, application events, and bean startup/shutdown lifecycles.

**Question 3. "`BeanFactory` only supports lazy beans and does not support lifecycle" — true or false?**

False. That is an oversimplification that leads to errors. Lazy vs. eager depends on the implementation/configuration and initialization process; lifecycle management exists at the bean factory layer, while `ApplicationContext` integrates and automates many steps.

**Question 4. If you want to change the message "Saved order A01" to another language, what do you use?**

Define the message for the corresponding locale in an appropriate `MessageSource` and call `getMessage` with the desired locale. For larger apps, `messages_*.properties` files via `ResourceBundleMessageSource` are usually easier to maintain than defining every message in code.

**Question 5. Why shouldn't a `Resource` always be coerced into a `File`?**

Because a resource may live inside a JAR or another source without a direct physical filesystem path; read the stream via `Resource.getInputStream()` when appropriate.

**Question 6. Is an `ApplicationListener` automatically a durable queue system?**

No. Internal Spring context events are delivered synchronously by default. If you need durable queues, retries, or cross-process message delivery guarantees, use an appropriate external solution outside these internal events.

**Question 7. Should `ApplicationContext` be injected into every service so it can call `getBean` itself?**

Normally no. Constructor injection keeps dependencies explicit and easy to unit test; `ApplicationContext` belongs at the bootstrap boundary or inside infrastructure components that genuinely need context services.

## 10. Project Application Checklist

1. Identify classes that genuinely need to be Spring-managed beans.
2. Choose `@Configuration` + `@Bean` or component scanning deliberately.
3. For required dependencies, prefer constructor injection.
4. Register beans with scopes matching their lifecycle; do not assume singletons are thread-safe.
5. If configuration varies by environment, use `Environment`/properties/profiles properly instead of hard-coding across files.
6. If internationalization is needed, use `MessageSource` instead of embedding display text directly in every service.
7. When loading resources, choose explicit prefixes/paths and handle streams with proper lifecycle cleanup.
8. If publishing events, identify listeners, sync/async behavior, and error-handling policy.
9. Use the context at the integration boundary; avoid pervasive Service Locator calls in business logic.
10. Verify missing beans, duplicate beans, circular dependencies, and bean lifecycle timing in tests.

**Conclusion:** `BeanFactory` provides the foundational contract for managing and retrieving beans. `ApplicationContext` builds on that foundation and integrates application services such as `Environment`, `MessageSource`, `ResourceLoader`, and application events. Understanding this boundary helps you pick the right API, configure Spring intentionally, and keep business classes dependent on explicitly declared collaborators rather than implicitly coupled to the container.