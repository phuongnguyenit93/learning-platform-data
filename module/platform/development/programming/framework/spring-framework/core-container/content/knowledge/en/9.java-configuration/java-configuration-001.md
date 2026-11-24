# Role of @Configuration and @Bean Methods in the Spring Core Container

## 1. Objectives

**Java-based configuration** lets you describe a Spring IoC container in Java code instead of relying only on XML or letting component scanning discover every class. The two central annotations are:

- `@Configuration`: marks **a class as a source of bean definitions**. This class typically groups `@Bean` methods and can be loaded via `AnnotationConfigApplicationContext`, `@Import`, or configuration scanning.
- `@Bean`: marks **a factory method** that instantiates, configures, and returns an object for Spring to register and manage as a bean.

It is important to distinguish between **a Java method returning an object** and **a bean managed by the container**. Spring reads the configuration to build bean definitions, resolve dependencies, and apply scopes, lifecycles, bean post-processors, and other rules. When you call a factory method directly outside Spring's mechanism, the returned object does **not automatically** become a container-managed bean.

This lesson focuses on these two annotations in the **Spring Framework Core Container**, covering:

1. The distinct roles of `@Configuration` classes and `@Bean` methods.
2. When to use them instead of `@Component`/`@Service`.
3. Bean naming, dependency injection, scope, and lifecycle mechanisms.
4. The difference between **full `@Configuration`** and **lite `@Bean`**, especially `proxyBeanMethods`.
5. A standalone runnable Java 17 + Spring Framework example, with Maven commands and expected stdout.
6. Common design, configuration, and testing mistakes.

## 2. Placing the Two Annotations in the IoC Picture

Spring manages objects based on **bean definitions**. A bean definition can describe the bean's name, type, instantiation strategy, dependencies, scope, and lifecycle. Java configuration is a **metadata source** for the container to create those bean definitions.

Consider a short configuration:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class AppConfig {

    @Bean
    public MessageService messageService() {
        return new MessageService();
    }
}
```

This is an **illustrative snippet**: `MessageService` is an application-defined class, not a built-in Spring API; the full runnable example is in section 6.

`@Configuration` applies to `AppConfig`, expressing "this class defines configuration for the container". `@Bean` applies to `messageService()`, expressing "the return value of this factory method must be managed by Spring as a bean". When you register `AppConfig` properly with Spring, the container can provide the `messageService` bean to consumers that require the `MessageService` type.

Conceptual flow:

```text
AppConfig.class
      |
      | read @Configuration and @Bean methods
      v
Bean definitions in the IoC container
      |
      | resolve dependencies, scope, and lifecycle
      v
Object instance managed by Spring
      |
      | getBean / constructor injection
      v
Consumer uses the bean
```

Do not think of `@Bean` as a `new` call that happens automatically when the JVM reads the annotation. Instance creation is a container step and can vary depending on scope, lazy initialization, and dependency resolution timing.

### Compared to XML configuration

The configuration:

```java
@Configuration
class Config {
    @Bean
    public MessageService messageService() {
        return new MessageService();
    }
}
```

is similar in bean-registration purpose to the XML definition:

```xml
<bean id="messageService" class="demo.MessageService"/>
```

The XML above only illustrates the structure; `demo.MessageService` must actually exist if used. Java config adds the benefit of the compiler directly checking constructor calls and data types.

## 3. Role of @Configuration

`@Configuration` belongs to the package:

```java
import org.springframework.context.annotation.Configuration;
```

It marks a **class** as configuration. In terms of stereotypes, `@Configuration` is also meta-annotated with `@Component`, so it can be discovered during appropriate component scanning. However, if you simply instantiate a configuration class with `new AppConfig()`, Spring does **not** automatically load its bean definitions. The configuration class must be **registered** with the container.

### 3.1. Registering a configuration class

A basic approach:

```java
// Illustrative snippet, assuming AppConfig already exists.
try (var context =
        new AnnotationConfigApplicationContext(AppConfig.class)) {
    MessageService service = context.getBean(MessageService.class);
    service.send("Hello");
}
```

Import `org.springframework.context.annotation.AnnotationConfigApplicationContext`. The constructor accepting `AppConfig.class` registers the configuration with the ApplicationContext and refreshes the context. Beans can be looked up by type/name; upon exiting `try-with-resources`, the context is closed and appropriate lifecycle callbacks are invoked.

Other approaches:

- `@Import(OtherConfig.class)` so one configuration declaratively imports another configuration.
- Component scanning finding `@Configuration` classes within the scanned packages.
- Using `AnnotationConfigApplicationContext` and then calling `register(Config.class)` and `refresh()`.
- In Spring Boot applications, bootstrap mechanisms process configuration classes through Boot's annotations; however, you do not need Boot to understand `@Configuration` in the Core Container.

### 3.2. What can a configuration class contain?

A configuration class can contain:

- `@Bean` methods returning beans for the container to manage.
- `@Import` to modularize configuration.
- `@ComponentScan` to specify packages containing candidate components.
- `@PropertySource`, `@Profile`, `@Conditional`, or other annotations controlling registration as appropriate, when the application needs them.
- Constructors and dependencies of the configuration class itself, though initialization timing must be considered and circular dependencies avoided.

Not every configuration class needs to contain many `@Bean` methods. You can split files by feature such as `PersistenceConfig`, `WebConfig`, and `MessagingConfig` when they genuinely manage different groups of beans. Splitting by **configuration responsibility** is better than a single giant file containing every bean in the entire system.

### 3.3. @Configuration is metadata, not a business service

A `@Configuration` class should focus on **wiring**: selecting implementations, constructing objects, and declaring dependencies. Order processing logic, pricing calculations, and data persistence belong in services/repositories, not inside configuration methods.

Counter-example:

```java
@Configuration
class PoorDesignConfig {

    @Bean
    PaymentService paymentService() {
        // Do not compute the entire payment business logic here.
        // Only construct the object and its collaborators.
        return new PaymentService();
    }
}
```

This is a design sketch example, not a standalone application. The `paymentService()` method is a bean factory, not an endpoint called to pay individual orders.

## 4. Role of @Bean

`@Bean` belongs to the package:

```java
import org.springframework.context.annotation.Bean;
```

This annotation is placed on a **method**; Spring uses the method as a factory to create the bean object.

```java
@Configuration
class AppConfig {
    @Bean
    PaymentGateway paymentGateway() {
        return new InMemoryPaymentGateway();
    }
}
```

In this illustrative snippet, `PaymentGateway` is an application interface and `InMemoryPaymentGateway` is an implementation. Spring registers the bean using its **declared return type** and any metadata resolvable at runtime. When the container needs to create this bean, it invokes the factory method in the appropriate context and manages the returned instance.

### 4.1. Default bean name

Normally, the default bean name from a `@Bean` method is the **method name**:

```java
@Bean
PaymentGateway paymentGateway() {
    return new InMemoryPaymentGateway();
}
```

The bean name is `paymentGateway`. It can be looked up as:

```java
// Illustration once the context has been created.
PaymentGateway gateway =
        context.getBean("paymentGateway", PaymentGateway.class);
```

Besides by name, Spring still supports injecting beans **by type** when a single suitable candidate exists and selection rules are satisfied. The bean name and the Java variable name in the consumer do not need to match for constructor injection to work.

### 4.2. Explicit naming and aliases

`@Bean` supports `name` or its alias `value`:

```java
@Bean(name = {"defaultGateway", "primaryPaymentAdapter"})
PaymentGateway paymentGateway() {
    return new InMemoryPaymentGateway();
}
```

Here `defaultGateway` is the primary name; `primaryPaymentAdapter` is an **alias for the same bean**, not two separate instances. This is a container bean name alias, **different** from the `@AliasFor` annotation used to describe aliases between annotation attributes.

When there are multiple beans of the same interface:

```java
@Bean("fastGateway")
PaymentGateway fastGateway() {
    return new FastGateway();
}

@Bean("safeGateway")
PaymentGateway safeGateway() {
    return new SafeGateway();
}
```

A consumer receiving a single `PaymentGateway` may need `@Qualifier("safeGateway")` or `@Primary`/other candidate selection rules. `@Bean` does not automatically pick "the first bean" when a type has multiple implementations. The two methods above are illustrative examples requiring the corresponding classes.

### 4.3. Return type of a factory method

You can declare an interface type:

```java
@Bean
Storage storage() {
    return new FileStorage();
}
```

or a concrete class:

```java
@Bean
FileStorage fileStorage() {
    return new FileStorage();
}
```

Both are valid if the classes exist. However, **type metadata for Spring to predict the bean before instantiating it** is affected by the declared return type. If another place wants to inject by the `FileStorage` type while the factory only declares `Storage`, Spring may not yet see the implementation type at certain stages.

Guideline: declare a return type **specific enough for the required injection points**, without forcing the business layer to depend on an implementation unnecessarily. For interface-based APIs, `Storage` is usually the right contract; for specialized processing mechanisms that rely on the implementation, consider type metadata.

### 4.4. @Bean does not only create objects via new

A factory method can:

- Return an object built with a Java constructor.
- Call a library's builder/factory.
- Create an adapter wrapping an external resource.
- Register an object from a third-party library whose **source you do not own** to attach `@Component`.

```java
@Bean
ExternalClient externalClient(ClientProperties properties) {
    return ExternalClient.builder()
            .endpoint(properties.endpoint())
            .build();
}
```

This is an illustrative snippet; `ExternalClient` and `ClientProperties` are hypothetical application/library types. The benefit here is that you can manage beans of classes that contain no Spring stereotypes while still configuring collaborators, scope, and lifecycle.

## 5. Dependency Injection via @Bean Method Parameters

This is the preferred wiring style because it is explicit and works with both full and lite configuration.

```java
@Configuration(proxyBeanMethods = false)
class AppConfig {

    @Bean
    PaymentGateway paymentGateway() {
        return new InMemoryPaymentGateway();
    }

    @Bean
    CheckoutService checkoutService(PaymentGateway paymentGateway) {
        return new CheckoutService(paymentGateway);
    }
}
```

Spring resolves the `PaymentGateway paymentGateway` parameter similarly to constructor injection and passes the matching bean into `checkoutService(...)`. You **do not need to call** `paymentGateway()` manually inside `checkoutService()`.

Benefits:

1. Dependencies are declared **openly right in the method signature**.
2. The container decides candidates by type, qualifier, primary, and required metadata.
3. This style does not depend on whether `@Configuration` enables proxying of bean methods.
4. When a required bean is missing, Spring reports an error while creating the consumer instead of silently creating an object outside the container.
5. It is easy to split configuration into multiple classes using `@Import` or component scanning.

### 5.1. Depending on a bean in another configuration class

```java
@Configuration(proxyBeanMethods = false)
class RepositoryConfig {

    @Bean
    AccountRepository accountRepository() {
        return new InMemoryAccountRepository();
    }
}

@Configuration(proxyBeanMethods = false)
@Import(RepositoryConfig.class)
class ServiceConfig {

    @Bean
    AccountService accountService(AccountRepository repository) {
        return new AccountService(repository);
    }
}
```

This is a structural illustration; interfaces/implementations are provided by the application. `@Import` pulls in the configuration; `accountService` receives the dependency resolved by Spring. There is no need for `ServiceConfig` to instantiate `RepositoryConfig` with `new` and call its factory method.

### 5.2. Resolving multiple beans

If there are two `PaymentGateway` beans, a method accepting a single `PaymentGateway` cannot always determine a unique candidate. You can use:

```java
@Bean
CheckoutService checkoutService(
        @Qualifier("safeGateway") PaymentGateway gateway) {
    return new CheckoutService(gateway);
}
```

Remember to import `org.springframework.beans.factory.annotation.Qualifier`. If you truly want to receive all plugins, use `List<Plugin>`, `Map<String, Plugin>`, or `ObjectProvider<Plugin>` at the appropriate injection point. Do not use a collection merely to dodge an ambiguity error when the service actually needs a single bean.

### 5.3. Optional dependencies

A `@Bean` method can also declare `Optional<AuditSink>` when auditing is legitimately optional:

```java
@Bean
CheckoutService checkoutService(
        PaymentGateway gateway,
        java.util.Optional<AuditSink> auditSink) {
    return new CheckoutService(gateway, auditSink);
}
```

This is illustrative; `CheckoutService`'s constructor in the project must match. The core dependency `PaymentGateway` remains required; `AuditSink` is allowed to be absent. Do not turn every parameter into `Optional` or `ObjectProvider` just so the application starts when configuration is missing.

## 6. Standalone Runnable Java 17 + Spring Framework Example

The example uses **plain Spring Framework** (no Spring Boot required), Java 17, and Maven. It demonstrates:

- `@Configuration(proxyBeanMethods = false)` as the source of bean definitions.
- `@Bean` creating the gateway and service.
- The `checkoutService(PaymentGateway gateway)` method receiving its dependency injected by Spring.
- `@Bean(name = {"auditClient", "auditAlias"})` creating a primary name and an alias.
- `initMethod`/`destroyMethod` having Spring manage the object's lifecycle.
- Lookups by type and by name returning the same singleton within a context.

### 6.1. Structure

```text
java-config-demo/
├── pom.xml
└── src/main/java/demo/JavaConfigDemo.java
```

### 6.2. POM

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>java-config-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.18</version>
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
            </plugin>
        </plugins>
    </build>
</project>
```

### 6.3. Program

Create `src/main/java/demo/JavaConfigDemo.java`:

```java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class JavaConfigDemo {

    interface PaymentGateway {
        String charge(String orderId);
    }

    static final class DemoGateway implements PaymentGateway {
        @Override
        public String charge(String orderId) {
            return "receipt-" + orderId;
        }
    }

    static final class CheckoutService {
        private final PaymentGateway gateway;

        CheckoutService(PaymentGateway gateway) {
            this.gateway = gateway;
        }

        String checkout(String orderId) {
            return gateway.charge(orderId);
        }
    }

    static final class AuditClient {
        private boolean ready;

        void initialize() {
            ready = true;
            System.out.println("audit.init");
        }

        void shutdown() {
            ready = false;
            System.out.println("audit.shutdown");
        }

        boolean isReady() {
            return ready;
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class AppConfig {

        @Bean
        PaymentGateway paymentGateway() {
            return new DemoGateway();
        }

        @Bean
        CheckoutService checkoutService(PaymentGateway paymentGateway) {
            return new CheckoutService(paymentGateway);
        }

        @Bean(
                name = {"auditClient", "auditAlias"},
                initMethod = "initialize",
                destroyMethod = "shutdown"
        )
        AuditClient auditClient() {
            return new AuditClient();
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            CheckoutService first =
                    context.getBean(CheckoutService.class);
            CheckoutService second =
                    context.getBean("checkoutService", CheckoutService.class);

            System.out.println("receipt=" + first.checkout("42"));
            System.out.println("sameService=" + (first == second));
            System.out.println("alias=" +
                    (context.getBean("auditClient") ==
                     context.getBean("auditAlias")));
            System.out.println("auditReady=" +
                    context.getBean(AuditClient.class).isReady());
        }
    }
}
```

### 6.4. Run and observe

From the directory containing `pom.xml`, install JDK 17+ and Maven and run:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.JavaConfigDemo
```

Lines **printed by the application** (excluding Maven or environment logs):

```text
audit.init
receipt=receipt-42
sameService=true
alias=true
auditReady=true
audit.shutdown
```

Why is this output reliable?

1. `AnnotationConfigApplicationContext(AppConfig.class)` creates/refreshes the context with three bean definitions from three `@Bean` methods. Regular singletons are instantiated during startup; `auditClient` has the `initialize()` callback so it prints `audit.init` before code in `main` prints the receipt.
2. `CheckoutService` receives the same `PaymentGateway` resolved by the container by type. The factory method does not manually call `paymentGateway()`.
3. `checkoutService` is a singleton by default: the two `getBean` calls by type and by name refer to the same instance, so `sameService=true`.
4. `auditClient` and `auditAlias` are **two names for the same bean**, not two separate beans, so `alias=true`.
5. `initMethod = "initialize"` is called before the bean is ready for consumers; `isReady()` returns `true`.
6. Upon exiting `try-with-resources`, the context closes and Spring invokes `shutdown()` on the `AuditClient` singleton, printing `audit.shutdown`.

**Conditions to keep in mind:** For non-lazy singletons, Spring's bean lifecycle executes at startup/close as in the example. For prototype or scoped beans, destruction lifecycle does not have the same guarantee as singletons; do not generalize this output to every scope. The program intentionally keeps classes simple and uses no logging framework.

### 6.5. Mini exercise

Replace:

```java
@Bean
CheckoutService checkoutService(PaymentGateway paymentGateway) {
    return new CheckoutService(paymentGateway);
}
```

with:

```java
@Bean("primaryCheckout")
CheckoutService checkoutService(PaymentGateway paymentGateway) {
    return new CheckoutService(paymentGateway);
}
```

Then the primary bean name changes from `checkoutService` to `primaryCheckout`. If `main` still calls `getBean("checkoutService", CheckoutService.class)`, it will no longer find the bean under the old name, unless there is an alias or another bean definition. Fetching by type `CheckoutService.class` can still work if there is only one matching bean.

## 7. Full `@Configuration` and the `proxyBeanMethods` Mechanism

`@Configuration` defaults to `proxyBeanMethods=true`: Spring enhances the configuration class with CGLIB so that eligible calls to **instance `@Bean` methods** on the container-managed configuration go through the `BeanFactory`. With `proxyBeanMethods=false`, direct Java calls retain standard Java semantics. **Both modes register bean definitions, support DI, and support lifecycle callbacks.**

### 7.1. Default full configuration

```java
@Configuration
class FullConfig {
    @Bean Repository repository() { return new Repository(); }
    @Bean Service service() { return new Service(repository()); }
}
```

This snippet illustrates two already-defined types `Repository` and `Service`. When the container invokes `service()` on the **enhanced `FullConfig`**, the `repository()` call can be intercepted to obtain the scoped bean. With the default singleton scope, `service` receives the same managed reference as `context.getBean(Repository.class)`. Calling `new FullConfig()` yourself outside the container has no interception.

### 7.2. Lite mode and the safe fix

If you change the annotation to `@Configuration(proxyBeanMethods=false)` while still calling `repository()` inside `service()`, Java executes the factory method directly and can create **a `Repository` outside the managed bean**. This is neither a `prototype` bean nor does it mean `@Bean` stopped working.

The preferred way in both modes:

```java
@Configuration(proxyBeanMethods = false)
class ParameterConfig {
    @Bean Repository repository() { return new Repository(); }
    @Bean Service service(Repository repository) {
        return new Service(repository);
    }
}
```

The `Repository` parameter is resolved by Spring from the BeanFactory by type/qualifier/scope, so there is no need to call another factory method to obtain the bean.

### 7.3. Comparison table

| Condition | Full (default) | Lite (`proxyBeanMethods=false`) |
| --- | --- | --- |
| Container registers and manages `@Bean` | Yes | Yes |
| Direct inter-bean instance call | Can be intercepted via enhanced config | Regular Java method call |
| Dependency via `@Bean` parameter | Yes | Yes |
| CGLIB subclass for method interception | Yes | Not needed |

Switch to lite only when there are no remaining inter-bean calls that require container semantics; inspect and replace them with dependency parameters where appropriate.

### 7.4. Subclassing limitations

Full configuration requires the class to be subclassable and instance `@Bean` methods to be overridable: `final` classes and `private`/`final` methods are unsuitable; `static @Bean` is supported, though static calls have no interception. The lesson on full mode and the lesson on `final`/`private`/`static` limitations will analyze the reasons in depth.

## 8. Can @Bean Live Inside @Component?

Yes. Spring allows `@Bean` methods inside a regular `@Component` class. However, that is **lite @Bean mode**, not full configuration processing simply because a bean method is present.

```java
@Component
class HelperFactory {

    @Bean
    Worker worker() {
        return new Worker();
    }
}
```

This is an illustrative snippet (requiring `Worker` and `@Component` imports). If `HelperFactory` is discovered by Spring, `worker()` can contribute a bean definition. However, calling `worker()` directly from another method on `HelperFactory` is **not** intercepted by Spring the way full `@Configuration` is.

Distinguish between:

- **Component scanning:** finding `@Component` classes or classes with meta-present stereotypes.
- **Bean definition configuration:** recognizing `@Bean` methods to register factory definitions.
- **Full configuration enhancement:** proxied method-call behavior only when full configuration meets its conditions.

Because a class whose purpose is defining multiple beans communicates intent more clearly with `@Configuration` than `@Component`, `@Configuration` is usually better. If interception is not needed, `@Configuration(proxyBeanMethods=false)` is a transparent declaration.

## 9. Bean Scope and Instantiation Timing

`@Bean` by default creates a **singleton per Spring IoC container**, unless another scope is declared.

```java
@Bean
CacheClient cacheClient() {
    return new CacheClient();
}
```

Fetching the `cacheClient` bean multiple times from a single ApplicationContext normally returns **the same instance**, though each independent ApplicationContext has its own singleton.

### Prototype scope

```java
@Bean
@Scope("prototype")
TaskWorker taskWorker() {
    return new TaskWorker();
}
```

This illustrative snippet requires the corresponding classes/imports. Spring returns a new instance per prototype bean resolution request. However, if a prototype `TaskWorker` is **injected directly once** into the constructor of a singleton, that singleton normally retains the instance it received; calling a method on the singleton does not automatically make Spring inject a new prototype.

When a singleton needs **to obtain a fresh prototype per task**, you can use `ObjectProvider<TaskWorker>` or a dedicated factory; do not change the scope or misuse direct calls to `taskWorker()` under `proxyBeanMethods=false`.

### Lazy beans

```java
@Bean
@Lazy
LargeClient largeClient() {
    return new LargeClient();
}
```

`@Lazy` alters instantiation timing under eligible conditions; it does not mean the bean is excluded from the container or can be missing. For non-lazy singletons, Spring typically instantiates them during context refresh. For lazy beans, creation can be deferred until requested; if another eager singleton needs it right away, that dependency can still trigger early creation.

**Do not confuse `@Bean` with `@Scope`:** The factory method defines the bean; scope defines the policy managing instance count and lifetime.

## 10. Bean Lifecycle and @Bean(initMethod, destroyMethod)

Because `@Bean` returns an object managed by Spring, Spring can apply:

- Dependency injection and lifecycle callbacks.
- BeanPostProcessors and auxiliary/proxy mechanisms enabled in the context.
- `@PostConstruct` and `@PreDestroy` if the relevant annotations and support are present.
- `InitializingBean` / `DisposableBean`.
- `initMethod` / `destroyMethod` declared directly on `@Bean`.

Example:

```java
@Bean(initMethod = "connect", destroyMethod = "close")
ConnectionClient connectionClient() {
    return new ConnectionClient();
}
```

This illustrative example requires `ConnectionClient.connect()` and `ConnectionClient.close()`. Spring invokes the init callback according to the lifecycle after creating and populating the bean; the destroy callback runs when the container closes for eligible singletons.

### When a bean has a close/shutdown method

Spring has a **destruction callback inference** mechanism for certain methods like `close` or `shutdown` on eligible objects. If a resource **does not belong to the context's lifecycle ownership** (for example, a JNDI/managed resource managed by external infrastructure), you may need:

```java
@Bean(destroyMethod = "")
ExternalManagedResource externalResource() {
    return lookupExternalResource();
}
```

This is illustrative; `ExternalManagedResource` and `lookupExternalResource` must be defined in the application. Use `destroyMethod=""` to disable the inferred destroy callback when Spring should not automatically close an external resource.

Do not manually close a Spring-managed resource in multiple places and still expect the destroy callback not to run again, unless the implementation is truly idempotent and the lifecycle is intentionally designed that way.

### Prototype destruction

Spring handles **initializing** prototypes, but normally does not manage **prototype destruction** the way it does for singletons after handing the object to the client. If a prototype bean holds a connection/file/resource, the caller must have an appropriate cleanup policy. Do not treat the singleton `AuditClient` example in section 6 as a guarantee that every prototype will automatically invoke `destroyMethod` when the context closes.

## 11. Loading and Composing Java Configuration

In multi-module applications, configuration can be split:

```java
@Configuration(proxyBeanMethods = false)
class AdapterConfig {

    @Bean
    Adapter adapter() {
        return new Adapter();
    }
}

@Configuration(proxyBeanMethods = false)
@Import(AdapterConfig.class)
class BusinessConfig {

    @Bean
    BusinessService businessService(Adapter adapter) {
        return new BusinessService(adapter);
    }
}
```

These are illustrative classes requiring imports for `Configuration`, `Bean`, `Import`, and application classes. Registering `BusinessConfig` in the context pulls in `AdapterConfig`, and `BusinessService` receives the `Adapter` resolved by Spring. There is no need to call `new AdapterConfig().adapter()` directly.

If you want to combine with component scanning:

```java
@Configuration(proxyBeanMethods = false)
@ComponentScan(basePackages = "com.example.application")
class ApplicationConfig {
}
```

Classes carrying stereotypes in `com.example.application` and its subpackages can be scanned. At the same time, `@Bean` methods inside `ApplicationConfig` also register factory bean definitions. Both approaches **complement each other**; you do not necessarily have to choose only one.

### Registering configuration via context

You can use:

```java
var context = new AnnotationConfigApplicationContext();
context.register(BusinessConfig.class);
context.refresh();
try {
    // retrieve beans and execute tasks
} finally {
    context.close();
}
```

This is an illustrative snippet requiring a valid `BusinessConfig`. You must call `refresh()` after `register()` when using the empty constructor to complete context initialization. When using the constructor that takes configuration classes as in section 6, Spring performs the refresh inside the constructor.

## 12. @Configuration and @Bean vs. @Component / @Service

| Criterion | `@Component` / `@Service` | `@Configuration` + `@Bean` |
| --- | --- | --- |
| Primary annotation placement | On the candidate class | `@Configuration` on the config class, `@Bean` on the factory method |
| Where the bean comes from | Scanner discovers stereotype class and container manages instantiation | Container invokes the declared factory method |
| Best suited for | Application classes whose source you control, dependencies via constructor | Third-party clients, adapters needing complex builders/config, wiring groups |
| Requires component scan? | Usually yes, or registered via another mechanism | Not mandatory if the config is registered directly |
| Bean naming | Usually based on class name or stereotype value | Usually factory method name; `@Bean(name=...)` can be used |
| Lifecycle handling | Standard managed bean | Standard managed bean |
| Needs proxied method calls? | Not the goal of stereotypes | Only with full `@Configuration` when calling other bean methods |

Having `@Bean` does not make Spring create a "superior" object compared to `@Component`. **Once inside the container, both are beans** and are subject to the applicable scope/lifecycle rules. The main difference is **how the factory is declared and how much control you have over instantiation**.

### When should you use @Bean?

- You need to register a bean from a third-party library and cannot edit its source to add `@Component`.
- You need to pass config values into a builder/constructor with many options.
- You want to provide multiple beans of the same class with different configurations.
- You want to explicitly define aliases, scope, and init/destroy callbacks at the factory boundary.
- You want to modularize wiring and swap implementations per environment.

### When should you use @Component/@Service?

- The class belongs to the application and has clear constructor dependencies.
- Complex factory logic is not needed.
- Component scanning is intentionally configured.
- You want less boilerplate and to avoid listing hundreds of trivial factory methods.

Avoid unconsciously both annotating an implementation with `@Component` and declaring a `@Bean` that creates the same implementation. That can create **two different beans of the same type**, leading to ambiguity when injecting a single dependency. If you genuinely need multiple differently configured instances, use clear names/qualifiers and test the candidate count explicitly.

## 13. Common Misconceptions

### "With @Configuration, every method inside automatically becomes a bean"

**False.** Only methods recognized by Spring as `@Bean` (or other registration mechanisms) contribute bean definitions. An ordinary helper method does not automatically become a factory bean.

```java
@Configuration
class Config {
    @Bean
    Client client() {
        return createClient();
    }

    private Client createClient() {
        return new Client();
    }
}
```

This is illustrative; `Client` is an application class. `createClient()` is merely a helper and does not register a separate bean; it is called inside `client()` to construct the `client` bean.

### "Calling appConfig.beanMethod() always retrieves a Spring bean"

**False without context.** On a configuration class created via `new` outside a context, it is just an ordinary Java call. On a full `@Configuration` object enhanced by Spring, inter-bean calls have interception. In lite mode, direct calls still behave normally. To be sure you receive a managed bean, inject dependencies via method parameters or look them up from the context in wiring/test layers when needed.

### "Changing to @Configuration(proxyBeanMethods=false) is only an optimization and never changes behavior"

**Not always true.** If the existing configuration directly calls one `@Bean` method from another `@Bean` method, disabling proxying removes Spring interception; this can create extra objects outside the expected bean identity/scope. Replace those calls with parameter-based dependency injection before turning off proxying.

### "@Bean always creates a new singleton every time it is called"

**False.** Singleton/prototype is the **scope of bean resolution in the container**. A factory method may be invoked once when the container creates a singleton, or each time Spring resolves a prototype. However, a direct Java call on a lite config is a different matter and does not guarantee the same instance as the bean.

### "With @Bean, there is no need to add the config to the context"

**False.** The configuration class must be registered/imported/scanned via a valid Spring mechanism. A Java file with annotations that is not in the ApplicationContext does not create bean definitions on its own.

### "Any library bean should be annotated with @Component by editing its source"

**Unnecessary.** `@Bean` lets you create and manage library instances without modifying that class. This is a prime use case for Java config.

### "@Bean(name = {a, b}) creates two singletons"

**False.** The name array of a single bean definition specifies the primary name and aliases, not two separate bean instances. If you need two instances, write two factory methods or register two separate bean definitions, with qualifiers if needed.

### "@Bean is used like a business endpoint"

**False.** A factory method is for **defining/creating a bean**, not for being called every time a payment request needs processing or a job needs to run. Business logic belongs in methods of the created bean, not in the `@Bean` method itself.

## 14. Advanced Technical Points to Know

### 14.1. @Bean and BeanFactoryPostProcessor

Some infrastructure beans such as `BeanFactoryPostProcessor` or `BeanPostProcessor` participate at **very early** stages of the container. Spring documentation recommends that `@Bean` methods for certain post-processors like `BeanFactoryPostProcessor` usually be `static` to avoid instantiating the configuration class too early, which could affect injections/callbacks on the configuration class itself.

```java
@Configuration
class InfrastructureConfig {

    @Bean
    static MyBeanFactoryPostProcessor myPostProcessor() {
        return new MyBeanFactoryPostProcessor();
    }
}
```

This is illustrative; `MyBeanFactoryPostProcessor` is an implementation that must be defined separately. Do not mechanically convert every `@Bean` into `static`: base the choice on the bean's role and lifecycle requirements.

### 14.2. @Bean methods with scope-dependent parameters

If a singleton factory method receives a prototype dependency via a parameter, the prototype may be created **when the singleton is constructed**. Afterward, the singleton retains that reference and does not automatically fetch a new prototype on every method invocation. For per-call lookup, use a dedicated provider/factory and understand the scopes involved.

### 14.3. Beware circular dependencies and @PostConstruct on config

A configuration class is itself a special bean and is processed early. Do not call `@Bean` methods inside `@PostConstruct` of the configuration class itself to "force" creation of other beans. This can cause early initialization or complex circular references. Place dependencies in method parameters and let Spring manage the bean creation order.

### 14.4. Return type and bean prediction

Spring must infer substantial information about candidates before creating beans. If a method returns a broad interface, Spring may not know every actual interface/concrete type of the object during bean type matching. For injection points that require an implementation-specific type, declare a sufficiently specific return type or update the injection point to depend on a stable interface.

### 14.5. Duplicate bean names and overriding

Two methods or two configuration classes registering the same bean name can lead to an error or override a definition depending on container settings and framework policy. **Do not assume** Spring will always pick the method declared later. Choose clear bean names, minimize duplicate registrations, and test the outcome in the exact ApplicationContext/Boot configuration of your application.

## 15. Symptom-Based Troubleshooting

| Symptom | Common Cause | Fix |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` when fetching a bean | Config class not registered/imported, factory method missing `@Bean`, qualifier/type mismatch | Check metadata, config scope, and bean name/type |
| `UnsatisfiedDependencyException` | Factory method or constructor parameter missing a required bean | Read which dependency is missing and register/qualify the right implementation |
| `NoUniqueBeanDefinitionException` | Multiple beans of the same type, cannot pick a unique one | Use `@Qualifier`, `@Primary`, or design a collection if genuinely needed |
| `BeanCreationException` inside factory method | Library constructor/builder threw an exception; invalid config | Read the root cause in the stack trace; fix factory/config values |
| Two instances despite singleton definition | Direct call to `@Bean` method in lite config; calling `new AppConfig()` yourself | Inject beans via factory method parameters; let Spring manage them |
| Failure to enhance `@Configuration` | Full config or bean methods are `final`/`private` improperly | Switch to lite mode with proper wiring or remove `final`/`private` where interception is needed |
| Bean name differs from expected | Used `@Bean(name=...)` or a custom naming strategy | Check declared names and look up by type when appropriate |
| `destroyMethod` does not run for prototype | Prototypes are not automatically destroyed by the container like singletons | Design cleanup owned by the consumer |
| `initMethod` does not run as expected | Object created with `new` outside context or callback applied to another instance | Confirm you are using the Spring-managed bean |
| Bean created early despite a provider | Non-lazy singleton was pre-instantiated | Check bean scope and lazy configuration |
| Adding both `@Component` and `@Bean` for the same class causes ambiguity | Two bean definitions with overlapping types | Pick one registration approach or add explicit qualifiers |
| Called `register()` but still cannot retrieve bean | Context created with empty constructor has not called `refresh()` | Call `refresh()` then look up; remember to close context |

Debugging workflow:

1. Ensure the configuration class is in the ApplicationContext (passed to constructor, `register`, `@Import`, or scanned).
2. Ensure the factory method has `@Bean` and a valid return type.
3. Check whether the default bean name changed due to `name`/`value`.
4. Check how many candidates exist for each `@Bean` parameter and which qualifiers apply.
5. Inspect scope/lazy/lifecycle; distinguish container-created objects from objects created directly with `new`.
6. If `@Bean` methods call one another, inspect `proxyBeanMethods`.
7. Read the root-cause exception, not only the outermost wrapper exception.

## 16. Exercises and Guided Answers

### Exercise 1 — Roles of the two annotations

How do `@Configuration` and `@Bean` differ?

**Answer:** `@Configuration` marks a configuration class as a source of bean definitions; `@Bean` marks a factory method that contributes a bean definition and returns an object managed by the container. Not every method on a `@Configuration` class automatically becomes a bean.

### Exercise 2 — Fetching a bean by name

With `@Bean CheckoutService checkoutService(...)`, what is the default bean name? If you use `@Bean(name={"checkoutA","checkoutAlias"})`, how many beans are defined?

**Answer:** By default the name is `checkoutService`. The name array creates **one bean definition** with primary name `checkoutA` and alias `checkoutAlias`.

### Exercise 3 — Full and lite

Given the following snippet:

```java
@Configuration(proxyBeanMethods = false)
class Config {
    @Bean
    Repository repository() { return new Repository(); }

    @Bean
    Service service() { return new Service(repository()); }
}
```

If `service()` calls `repository()` directly, is `Service` guaranteed to receive the singleton `repository` bean managed by the container?

**Answer:** No. In lite mode, `repository()` is a regular Java call and can create a separate instance. Change it to `Service service(Repository repository)` so Spring injects the dependency.

### Exercise 4 — Library bean

You need to register `HttpClient` from the JDK or a client from a third-party library, but you cannot edit that class's source. Should you choose component scanning directly on the client class or `@Bean`?

**Answer:** `@Bean` is appropriate. The factory method can construct the client using its builder/constructor and place the instance in the container. If the client holds resources, consider lifecycle/ownership.

### Exercise 5 — Two implementations

There are two `MailSender` beans of the same type. One service must use the exact sender for transactions. If the `MailSender mailSender` parameter is ambiguous, what should you do?

**Answer:** Use `@Qualifier` on the parameter or `@Primary` when one default candidate is right. Do not rely on registration order and do not replace everything with a collection if the business logic needs one specific sender.

### Exercise 6 — Lifecycle

A `@Bean(initMethod="start", destroyMethod="stop")` is a singleton. When can the callbacks run?

**Answer:** `start` runs during lifecycle initialization when the bean is created/processed; `stop` normally runs when the singleton is destroyed by the container or when the context closes. For prototypes, Spring does not automatically guarantee destroy callbacks on context close the way it does for singletons.

### Exercise 7 — Writing clean configuration

Given `Repository` and `ReportService` whose constructor takes `Repository`, write two `@Bean` methods in a `@Configuration(proxyBeanMethods=false)` so that `ReportService` uses the `Repository` bean managed by Spring.

**Guided answer:**

```java
@Configuration(proxyBeanMethods = false)
class ReportConfig {
    @Bean
    Repository repository() {
        return new Repository();
    }

    @Bean
    ReportService reportService(Repository repository) {
        return new ReportService(repository);
    }
}
```

This is a configuration template; the corresponding `Repository` and `ReportService` classes need to be added. The key point is that `Repository` is passed as a **factory method parameter**, rather than calling `repository()` directly.

## 17. Project Adoption Checklist

Before concluding that Java configuration works properly, check:

- `@Configuration` has been added to the right ApplicationContext.
- Every bean intended to be registered by a factory method has `@Bean`.
- `@Bean` methods return types useful for injection points.
- Bean names/aliases do not accidentally collide.
- Required dependencies are clearly declared via constructor or method parameters.
- If `proxyBeanMethods` is disabled, inter-bean direct calls are not relied upon to obtain container-managed instances.
- Scope/lazy semantics match the usage of singletons, prototypes, or external resources.
- Init/destroy callbacks match the bean's lifecycle owner.
- The same implementation is not accidentally registered twice between component scanning and `@Bean`.
- There is a smoke test using `AnnotationConfigApplicationContext` or an integration test confirming bean presence, identity, and lifecycle.

## Summary

**`@Configuration` describes where configuration lives; `@Bean` describes the method that creates a bean.** Spring uses them to build bean definitions and manage dependencies, scopes, lifecycles, callbacks, and other container mechanisms. When writing new Java config, **injecting dependencies via `@Bean` method parameters** is usually clearer and safe in both full and lite modes.

Rely on calls between `@Bean` methods only if you understand full `@Configuration` and `proxyBeanMethods=true`. With `proxyBeanMethods=false`, those calls are ordinary Java calls and can create objects outside the managed singleton identity. When you want to express wiring without editing library source code, `@Bean` is the natural tool; when application classes simply need to be discovered by a scanner, `@Component`/`@Service` can be simpler.

## Official Spring Documentation

- [Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java.html) — overview of Java configuration.
- [Basic Concepts: @Bean and @Configuration](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/basic-concepts.html) — definition of both annotations and full/lite mode.
- [Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/bean-annotation.html) — bean names, method parameters, lifecycle, and return types.
- [Using the @Configuration Annotation](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/configuration-annotation.html) — inter-bean dependencies and enhancement.
- [Composing Java-based Configurations](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/composing-configuration-classes.html) — `@Import` and wiring across configuration classes.
- [Bean Scopes](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-scopes.html) — singleton, prototype, and scope semantics.
