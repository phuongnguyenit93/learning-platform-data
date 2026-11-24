# Converting XML Configuration to Java While Preserving Behavior — Spring Core Container

## 1. Goal: Preserve the Runtime Contract, Not Just Change Syntax

Spring Framework supports both XML bean definitions and Java-based configuration (`@Configuration`, `@Bean`, `@Import`). When migrating an application from XML to Java, replacing `<bean>` with `@Bean` is only the visible part. The hard part is **preserving container behavior**: which beans exist, what they are named, when they are created, what scope they have, which dependencies they receive, and how they are initialized and destroyed.

XML example:

```xml
<bean id="repository" class="demo.Repository"/>
<bean id="service" class="demo.Service">
    <constructor-arg ref="repository"/>
    <property name="prefix" value="INV:"/>
</bean>
```

JavaConfig can be written as:

```java
@Configuration(proxyBeanMethods = false)
class ApplicationConfig {
    @Bean("repository")
    Repository repository() {
        return new Repository();
    }

    @Bean("service")
    Service service(Repository repository) {
        Service service = new Service(repository);
        service.setPrefix("INV:");
        return service;
    }
}
```

These two examples are **illustrative code**, requiring domain classes and imports. They can build the same object graph, yet do not prove every contract is identical: legacy XML may also have aliases, profiles, `depends-on`, custom init/destroy callbacks, prototype scopes, namespace infrastructure, or properties resolved in a specific precedence order.

**A successful conversion** means that given the same inputs and environment, consumers observe the exact same behavior as before, aside from differences intentionally approved by the team.

This lesson focuses on:

- Taking a complete inventory of XML sources, bean definitions, and metadata.
- Mapping tables from XML → JavaConfig for dependency injection, bean names, aliases, scopes, laziness, profiles, ordering, and lifecycle.
- Cases without a 1:1 mapping such as `FactoryBean`, lookup-method injection, and custom namespaces.
- Temporary XML/Java coexistence using `@ImportResource` and strategies to avoid duplicate registrations.
- A Java 17+ Spring Framework 6.2 example with **two independent contexts** and assertions comparing output, identity, and lifecycle.
- Regression testing, rollout checklists, common pitfalls, and solved exercises.

## 2. What Is “Parity” and Where Should It Be Measured?

Comparing class names alone is not enough. Distinguish the following contracts:

| Contract group | What to preserve | Example migration bug |
| --- | --- | --- |
| Bean registration | Bean names/types present in the right context | Dropping an old bean or accidentally scanning an extra bean |
| Naming/alias | Bean `id`, aliases, and string lookups | `getBean("billingGateway")` stops working |
| Injection | Consumer receives the exact collaborator it had before | Switching `ref="safeStore"` to by-type injection and receiving `fastStore` |
| Scope | Singleton, prototype, or web/custom scope | Prototype turns into singleton |
| Lazy/eager | When the bean is instantiated | Lazy bean gets instantiated during refresh |
| Lifecycle | Init/destroy methods, callbacks, shutdown | Dropping `stop()` or calling `start()` twice |
| Ordering | `depends-on` and indirect dependencies | Infrastructure is unready when a service initializes |
| Config values | Literals, nulls, collections, property sources | Endpoint changes due to different property precedence |
| Conditions | Active profiles/conditional metadata | Production picks up a dev bean |
| Candidate rules | Primary/qualifier/autowire-candidate | Two implementations become ambiguous |
| Framework infrastructure | Transactions/AOP/cache/async/schedulers | Business logic runs yet transactions fail to roll back |
| Ownership | Parent/child `ApplicationContext`s, scope boundaries | Bean moves into a different context |
| External behavior | I/O, database, messaging, side effects | Job/listener runs twice after migration |

Not every **implementation detail** must remain identical. For example, `AnnotationConfigApplicationContext` may register different Spring infrastructure definitions than `ClassPathXmlApplicationContext`. Rather than demanding an exact match in `getBeanDefinitionCount()`, compare **bean contracts** and actual runtime outcomes.

### 2.1. Distinguishing Behavioral Parity from Structural Parity

Two configurations can differ structurally while behaving identically:

- XML `<constructor-arg ref=...>` becomes a factory-method parameter.
- XML `<property value=...>` becomes a setter call inside a `@Bean` method.
- XML `<import resource=...>` becomes `@Import(JavaConfig.class)` once that source is migrated.
- XML `name`/`alias` is preserved via `@Bean(name={"primary","alias"})`.

Conversely, keeping the same implementation class while changing scope, dropping an alias, or losing a lifecycle hook is **not equivalent**.

### 2.2. Defining Verification Boundaries

In an application with both root and servlet child contexts, two valid instances of the same type can coexist. Verify from **the same consumer perspective**: which context owns the bean, which name is looked up, and which proxy is handed to the service. Do not compare an XML singleton in a child context to a JavaConfig singleton in the root context and declare parity just because the class matches.

## 3. Before Writing Java: Inventory What XML Is Actually Loaded

A project may contain:

```text
config/
├── root.xml
├── persistence.xml
├── services.xml
├── integration/
│   ├── messaging.xml
│   └── transactions.xml
└── environments/
    ├── dev.xml
    └── prod.xml
```

The entry point might invoke:

```java
new ClassPathXmlApplicationContext(
        "config/root.xml",
        "config/services.xml");
```

or XML might contain transitive `<import resource="..."/>` elements. A library JAR may also supply XML imported by the application.

**Inventory checklist:**

1. Which XML resources are loaded at runtime, not just files named “applicationContext.”
2. Transitive `<import>` declarations and `<beans profile=...>` blocks.
3. Bean IDs, aliases, types, scopes, `lazy-init`, `depends-on`, init/destroy methods, `primary`, qualifiers.
4. Constructor/property values and explicit `ref` by name.
5. Property placeholders, bean factory post-processors, and property source precedence.
6. Namespace handlers such as `context`, `tx`, `aop`, `task`, or third-party libraries.
7. `FactoryBean`, `factory-bean`, `factory-method`, inner beans, `lookup-method`, bean definition inheritance.
8. Tests/integrations using `getBean("name")` or string-based SpEL bean references.
9. Beans registered via component scanning outside explicit XML definitions.
10. Parent-child contexts and beans with external side effects.

Example inventory table:

| Bean | Aliases | Scope | Dependencies | Init/Destroy | Notes |
| --- | --- | --- | --- | --- | --- |
| `catalogRepository` | — | singleton | — | — | Managed repository |
| `catalogService` | `publicCatalog` | singleton | `catalogRepository` | `start/stop` | `depends-on="startupMarker"` |
| `ticket` | — | prototype | — | — | Two lookups must return distinct instances |
| `lazyFormatter` | — | lazy singleton | — | — | Instantiated upon lookup |
| `startupMarker` | — | singleton | — | — | Initialization dependency |

The demo in Section 10 implements this entire table in both XML and JavaConfig, then verifies parity automatically.

## 4. XML → JavaConfig Mapping: Practical Lookup Table

| XML | JavaConfig | Check |
| --- | --- | --- |
| `<bean id="x" class="pkg.X"/>` | `@Bean("x") X x()` | Bean type and name |
| `<alias name="x" alias="publicX"/>` | `@Bean(name={"x","publicX"})` | Both names resolve to the same bean |
| `<constructor-arg ref="repo"/>` | Factory method accepts `Repo repo` | Exact bean instance |
| `<constructor-arg value="5"/>` | `new X(5)` or config value | Conversion/defaults |
| `<property name="enabled" value="true"/>` | `obj.setEnabled(true)` | Value and timing |
| `<property name="store" ref="store"/>` | Inject `Store` param then `setStore(store)` | Never instantiate raw dependency manually |
| `<list>/<map>/<props>` | Java collections/`Properties` | Content, mutability, order |
| `scope="singleton"` | `@Bean` default | Per-container singleton |
| `scope="prototype"` | `@Scope("prototype")` | Distinct lookup behavior |
| `lazy-init="true"` | `@Lazy` | Avoids pre-instantiation until needed |
| `depends-on="manager"` | `@DependsOn("manager")` | Startup/shutdown relationship |
| `init-method="start"` | `@Bean(initMethod="start")` | Single invocation callback |
| `destroy-method="stop"` | `@Bean(destroyMethod="stop")` | Callback on context close |
| `primary="true"` | `@Primary` | Single-candidate selection |
| `autowire-candidate="false"` | `@Bean(autowireCandidate=false)` | Type-based selection |
| `<beans profile="dev">` | `@Profile("dev")` | Profile-scoped bean group |
| XML `<import resource="x.xml"/>` | `@Import(XConfig.class)` after migrating | Correct sources |
| Keeping unmigrated XML | `@ImportResource("classpath:x.xml")` | No duplicate beans |
| `<context:component-scan>` | `@ComponentScan` | Packages and filters |
| `<tx:annotation-driven/>` | `@EnableTransactionManagement` where appropriate | Transaction manager/proxy behavior |

The Java snippets in this table are **illustrative syntax**. They require importing annotations from their respective Spring packages and valid class definitions.

### 4.1. Beware of XML Default Values

XML bean definitions default to singleton and normally eagerly initialize non-lazy singletons in `ApplicationContext`. `@Bean` also defaults to singleton, yet destroy inference and bean-candidate metadata can differ. Do not skip checking other defaults just because both default to singleton.

## 5. Bean Names and Aliases Are Part of the API

XML:

```xml
<bean id="paymentService" class="demo.PaymentService"/>
<alias name="paymentService" alias="billingGateway"/>
```

Nearly equivalent JavaConfig:

```java
@Bean(name = {"paymentService", "billingGateway"})
PaymentService paymentService() {
    return new PaymentService();
}
```

The first name in the array is the primary bean name; subsequent names are aliases. For singletons, lookups under either name return the same instance. Never create two factory methods just because XML defined an alias.

### 5.1. Specify `@Bean("oldName")` Explicitly

If you convert:

```xml
<bean id="accountDao" class="demo.AccountDao"/>
```

to:

```java
@Bean
AccountDao repository() {
    return new AccountDao();
}
```

the bean defaults to the name `repository` instead of `accountDao`. Type-based injection may keep working, yet `getBean("accountDao")` or XML `ref="accountDao"` in an unmigrated file will fail.

Keep the name with `@Bean("accountDao")` whenever legacy contracts depend on that name. Do not casually rename beans while migrating.

### 5.2. Verify Both By-Type and By-Name Lookups

If JavaConfig introduces a second implementation, by-name lookups may still pass while by-type injection becomes ambiguous. Audit names, aliases, and candidate counts per interface, especially when `@Primary` or `@Qualifier` is involved.

## 6. Migrating Dependency Injection Without Altering Collaborator Selection

### 6.1. Constructor Arguments

XML:

```xml
<bean id="repository" class="demo.SqlRepository"/>
<bean id="service" class="demo.OrderService">
    <constructor-arg ref="repository"/>
</bean>
```

JavaConfig:

```java
@Configuration(proxyBeanMethods = false)
class OrderConfiguration {

    @Bean("repository")
    SqlRepository repository() {
        return new SqlRepository();
    }

    @Bean("service")
    OrderService service(SqlRepository repository) {
        return new OrderService(repository);
    }
}
```

Method-parameter injection tells BeanFactory to resolve `repository` before invoking the `service` factory method. This is straightforward and avoids inter-bean self-invocation issues when `proxyBeanMethods=false`.

### 6.2. An XML `ref` May Mean **Selection by Name**

XML:

```xml
<bean id="service" class="demo.OrderService">
    <constructor-arg ref="safeRepository"/>
</bean>
```

If Java writes:

```java
@Bean("service")
OrderService service(Repository repository) {
    return new OrderService(repository);
}
```

and the container holds both `fastRepository` and `safeRepository`, Spring may choose a different candidate (via primary/qualifier/name resolution rules) or fail with no unique match. To preserve intent, use:

```java
@Bean("service")
OrderService service(
        @Qualifier("safeRepository") Repository repository) {
    return new OrderService(repository);
}
```

`@Qualifier` constrains candidate selection by name/metadata. For special scenarios requiring exact string lookup, a deliberate BeanFactory named lookup can be used. Do not turn business code into a service locator when factory-method parameters clearly express the dependency.

### 6.3. Setter Injection Preserves Property Population Timing

XML:

```xml
<bean id="client" class="demo.Client">
    <property name="timeoutMillis" value="5000"/>
    <property name="repository" ref="repository"/>
</bean>
```

JavaConfig:

```java
@Bean("client")
Client client(Repository repository) {
    Client client = new Client();
    client.setTimeoutMillis(5000);
    client.setRepository(repository);
    return client;
}
```

Preserve both literals and dependency references. Refactoring to constructor injection at the same time may produce the same end state yet change initialization sequencing or the class API; do that as a separate, tested refactoring step.

### 6.4. Avoid `new` on a Collaborator Instead of a Managed Bean

Wrong if old XML injected a singleton repository:

```java
@Bean
OrderService orderService() {
    return new OrderService(new SqlRepository());
}
```

`new SqlRepository()` creates a standalone object, not the Spring-managed `repository` bean, missing AOP proxies, injections, and init/destroy hooks.

Better:

```java
@Bean
OrderService orderService(SqlRepository repository) {
    return new OrderService(repository);
}
```

**Exception to inspect separately:** an XML inner bean intentionally created for a single consumer. There, creating the object directly inside the Java factory can match functionally, though inner-bean lifecycle/post-processing may differ — test before claiming parity.

### 6.5. Full `@Configuration` vs. Lite Mode

`@Configuration` defaults to `proxyBeanMethods=true`, enhancing the class with CGLIB so calls between `@Bean` methods route through the container. With `proxyBeanMethods=false`, calling `someBean()` in Java is a direct method invocation, potentially creating an extra raw instance.

For clear migrations, prefer:

```java
@Bean
Service service(Repository repository) {
    return new Service(repository);
}
```

over:

```java
@Bean
Service service() {
    return new Service(repository()); // Direct @Bean method call.
}
```

The first makes the dependency graph explicit in the method signature and does not depend on proxy mode.

## 7. Scalar Values, Nulls, Collections, and External Configuration

### 7.1. Literal Conversion

XML:

```xml
<property name="retries" value="3"/>
<property name="enabled" value="true"/>
<property name="label" value="Invoices"/>
```

In Java:

```java
service.setRetries(3);
service.setEnabled(true);
service.setLabel("Invoices");
```

Spring XML uses type-conversion infrastructure to parse text to the setter's type; the Java compiler checks argument types directly. With a custom `PropertyEditor` or `ConversionService`, a literal may convert into a specialized domain value. Preserve **the post-conversion semantics**, not just raw XML text.

### 7.2. Empty String Differs from Java `null`

XML `<property name="memo" value=""/>` specifies an empty string. XML:

```xml
<property name="memo">
    <null/>
</property>
```

specifies `null`. When migrating to Java, call `setMemo("")` or `setMemo(null)` faithfully per the old metadata. Distinguish the two if validation, serialization, or business logic depends on them.

### 7.3. Collection Mutability and Order

XML:

```xml
<property name="channels">
    <list>
        <value>email</value>
        <value>sms</value>
    </list>
</property>
```

Java:

```java
service.setChannels(List.of("email", "sms"));
```

These collections are equivalent if the service **only reads** content and order. However, `List.of(...)` is unmodifiable; if legacy code calls `channels.add("push")`, behavior breaks.

When mutability is part of the contract:

```java
service.setChannels(
        new ArrayList<>(List.of("email", "sms")));
```

For XML `<map>` vs. Java `Map.of(...)`, watch iteration order, null keys/values, duplicate keys, and mutability. When order matters, consider `LinkedHashMap`; when mutability is needed, construct a mutable copy and test it.

### 7.4. Placeholders and Property Source Precedence

XML may declare:

```xml
<context:property-placeholder
    location="classpath:legacy.properties"/>

<bean id="client" class="demo.Client">
    <property name="endpoint"
              value="${client.endpoint}"/>
</bean>
```

JavaConfig may use:

```java
@Configuration(proxyBeanMethods = false)
@PropertySource("classpath:legacy.properties")
class ClientConfiguration {

    @Bean
    Client client(@Value("${client.endpoint}") String endpoint) {
        Client client = new Client();
        client.setEndpoint(endpoint);
        return client;
    }
}
```

These are illustrative snippets; XML needs the `context` namespace, and Java needs imports and domain classes. Spring placeholder syntax is `${client.endpoint}` (without backslashes in real source). Placeholder resolution depends on property sources and active infrastructure.

Watch **sources and precedence**: properties from OS environment variables, JVM system properties, classpath files, Spring `Environment`, `PropertySourcesPlaceholderConfigurer`, or Boot config systems can resolve in different orders. Never alter property keys, default fallbacks, or override precedence just because the new syntax is shorter.

### 7.5. SpEL Expressions Are Not Unconditionally Equivalent to Java Expressions

XML `value="#{@settings.timeoutMillis}"` resolves SpEL through the container. A Java call `settings.timeoutMillis()` may differ regarding proxies, lazy/scoped references, and lifecycle. Keep `@Value("#{...}")` when warranted or replace via DI + tests, rather than blindly find-and-replacing expressions.

## 8. Bean Scope, Laziness, Ordering, and Lifecycle

### 8.1. Scope

XML:

```xml
<bean id="ticket" class="demo.Ticket"
      scope="prototype"/>
```

Java:

```java
@Bean("ticket")
@Scope("prototype")
Ticket ticket() {
    return new Ticket();
}
```

Two calls to `context.getBean("ticket")` must return two distinct objects per prototype semantics. Because `@Bean` defaults to singleton, forgetting `@Scope` is a regression.

If a singleton receives a prototype in its constructor, it normally retains that single prototype instance; to fetch a fresh instance per operation, you need `ObjectProvider<T>`, a factory, or method injection. Moving the scope flag alone is not enough if legacy XML used `<lookup-method>`.

### 8.2. Lazy Initialization

XML:

```xml
<bean id="lazyFormatter"
      class="demo.LazyFormatter"
      lazy-init="true"/>
```

Java:

```java
@Bean("lazyFormatter")
@Lazy
LazyFormatter lazyFormatter() {
    return new LazyFormatter();
}
```

A lazy bean may still be created at startup if an eager singleton depends on it. Test against the real bean graph instead of claiming a lazy bean is “never” instantiated during refresh.

### 8.3. `depends-on`

XML:

```xml
<bean id="service" class="demo.Service"
      depends-on="startupMarker"/>
```

Java:

```java
@Bean("service")
@DependsOn("startupMarker")
Service service(Repository repository) {
    return new Service(repository);
}
```

`@DependsOn` expresses an initialization ordering constraint by bean name. It does not inject `StartupMarker` into `service`. It also influences singleton destruction order. Do not remove it merely because `service`'s constructor does not take the marker.

### 8.4. Init/Destroy Callbacks

XML:

```xml
<bean id="service" class="demo.Service"
      init-method="start"
      destroy-method="stop"/>
```

Java:

```java
@Bean(name = "service",
      initMethod = "start",
      destroyMethod = "stop")
Service service(Repository repository) {
    return new Service(repository);
}
```

Do not call `service.start()` inside the factory method while also specifying `initMethod="start"`: the callback would run **twice**. Let the container invoke it at the proper lifecycle phase.

### 8.5. `@Bean` Destroy Inference Is a Trap

`@Bean` automatically infers public no-arg `close()` or `shutdown()` destroy methods. That can add behavior absent from legacy XML that declared no destroy callback.

To disable **inference** for a bean:

```java
@Bean(destroyMethod = "")
LegacyResource sharedResource() {
    return new LegacyResource();
}
```

An empty string only disables automatic inference; it does not disable `DisposableBean` or other lifecycle callbacks. When legacy XML explicitly had `destroy-method="close"`, declare `@Bean(destroyMethod="close")` explicitly to preserve behavior.

### 8.6. Prototype Destruction Differs from Singleton Destruction

Spring does not track all created prototype instances to invoke destroy callbacks upon context shutdown the way it does for singletons. If prototype resources require cleanup, the application must manage it explicitly. Do not rely on `@Bean(destroyMethod="...")` to clean up every prototype.

## 9. Profiles, Candidates, and Key Infrastructure

### 9.1. XML Profiles to `@Profile`

XML:

```xml
<beans profile="dev">
    <bean id="store" class="demo.InMemoryStore"/>
</beans>
```

Java:

```java
@Configuration(proxyBeanMethods = false)
@Profile("dev")
class DevConfiguration {
    @Bean("store")
    Store store() {
        return new InMemoryStore();
    }
}
```

Test `dev`, `prod`, no-profile, and multi-profile combinations when the app supports them. If an imported configuration carries `@Conditional` or `@Profile`, those conditions still apply; importing does not force registration.

### 9.2. Primary / Qualifier

XML `primary="true"` corresponds closely to Java `@Primary`. For consumers requiring a specific bean, `@Qualifier("safeStore")` or an explicit named lookup is safer than relying on default by-type injection.

XML `autowire-candidate="false"` mainly excludes a bean from type-based injection without deleting it or blocking explicit `ref`. In Spring 6.2, `@Bean(autowireCandidate=false)` preserves that candidate metadata.

### 9.3. Do Not Translate Infrastructure XML by Guessing Annotation Names

`<tx:annotation-driven/>` maps conceptually to `@EnableTransactionManagement`, yet you must verify proxy vs. AspectJ mode, transaction manager, advisor ordering, `proxyTargetClass`, and actual commit/rollback behavior.

`<aop:aspectj-autoproxy/>` has a Java counterpart in `@EnableAspectJAutoProxy`, though it does not turn every raw object into a proxy. Self-invocation under Spring AOP proxy mode normally bypasses the proxy.

`<context:component-scan>` translates to `@ComponentScan`, while preserving base packages, include/exclude filters, and bean naming. Overly broad scanning can register unwanted XML configs or implementations.

For custom namespaces from Spring Integration, Security, Batch, or vendor libraries, a 1:1 Java DSL/API is **not guaranteed** in every version. Keep an XML fragment via `@ImportResource` and migrate only once tested.

## 10. Java 17+ Demo: Same Application, Two Bean Registration Styles

The goal is comparing **an XML context** and **a JavaConfig context**, rather than mixing both into one registry. Both XML and JavaConfig define:

- `catalogRepository`: singleton repository.
- `catalogService`: singleton service with alias `publicCatalog`, taking repository, prefix, retries, and channels.
- `startupMarker`: linked to the service via `depends-on`.
- `ticket`: prototype.
- `lazyFormatter`: lazy singleton.
- Service lifecycle: `start` on initialization, `stop` on context close.

### 10.1. File Structure

```text
xml-to-java-parity/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── XmlJavaParityDemo.java
        └── resources/
            └── legacy-context.xml
```

`settings.gradle`:

```groovy
rootProject.name = 'xml-to-java-parity'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
}

application {
    mainClass = 'demo.XmlJavaParityDemo'
}
```

Use JDK 17+ and a compatible Gradle version. `spring-context` includes the Spring modules needed for both XML and JavaConfig; no Spring Boot is required.

### 10.2. Original XML File

`src/main/resources/legacy-context.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="startupMarker"
          class="demo.XmlJavaParityDemo$StartupMarker"/>

    <bean id="catalogRepository"
          class="demo.XmlJavaParityDemo$CatalogRepository"/>

    <bean id="catalogService"
          class="demo.XmlJavaParityDemo$CatalogService"
          depends-on="startupMarker"
          init-method="start"
          destroy-method="stop">
        <constructor-arg ref="catalogRepository"/>
        <property name="prefix" value="INV:"/>
        <property name="retries" value="2"/>
        <property name="channels">
            <list>
                <value>email</value>
                <value>sms</value>
            </list>
        </property>
    </bean>

    <alias name="catalogService" alias="publicCatalog"/>

    <bean id="ticket"
          class="demo.XmlJavaParityDemo$Ticket"
          scope="prototype"/>

    <bean id="lazyFormatter"
          class="demo.XmlJavaParityDemo$LazyFormatter"
          lazy-init="true"/>
</beans>
```

The `$` signs in `class` are **binary names of nested Java classes**. This is exact for the demo; if you extract domain classes to top-level files, update the XML class names.

### 10.3. Complete Java Code

`src/main/java/demo/XmlJavaParityDemo.java`:

```java
package demo;

import java.util.Arrays;
import java.util.List;
import java.util.Objects;

import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.DependsOn;
import org.springframework.context.annotation.Lazy;
import org.springframework.context.annotation.Scope;
import org.springframework.context.support.ClassPathXmlApplicationContext;

public class XmlJavaParityDemo {

    public static final class StartupMarker {
        public StartupMarker() {
        }
    }

    public static final class CatalogRepository {
        public CatalogRepository() {
        }

        public String find(String id) {
            return "sku-" + id;
        }
    }

    public static final class Ticket {
        public Ticket() {
        }
    }

    public static final class LazyFormatter {
        public LazyFormatter() {
        }
    }

    public static final class CatalogService {
        private final CatalogRepository repository;
        private String prefix = "";
        private int retries;
        private List<String> channels = List.of();
        private boolean started;
        private boolean stopped;

        public CatalogService(CatalogRepository repository) {
            this.repository = Objects.requireNonNull(repository);
        }

        public void setPrefix(String prefix) {
            this.prefix = Objects.requireNonNull(prefix);
        }

        public void setRetries(int retries) {
            this.retries = retries;
        }

        public void setChannels(List<String> channels) {
            this.channels = Objects.requireNonNull(channels);
        }

        public CatalogRepository getRepository() {
            return repository;
        }

        public void start() {
            started = true;
        }

        public void stop() {
            stopped = true;
        }

        public boolean isStarted() {
            return started;
        }

        public boolean isStopped() {
            return stopped;
        }

        public String report(String id) {
            return prefix + repository.find(id)
                    + " retries=" + retries
                    + " channels=" + channels;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class JavaConfig {

        @Bean("startupMarker")
        StartupMarker startupMarker() {
            return new StartupMarker();
        }

        @Bean("catalogRepository")
        CatalogRepository catalogRepository() {
            return new CatalogRepository();
        }

        @Bean(
            name = {"catalogService", "publicCatalog"},
            initMethod = "start",
            destroyMethod = "stop"
        )
        @DependsOn("startupMarker")
        CatalogService catalogService(
                CatalogRepository catalogRepository) {

            CatalogService service =
                    new CatalogService(catalogRepository);
            service.setPrefix("INV:");
            service.setRetries(2);
            service.setChannels(List.of("email", "sms"));
            return service;
        }

        @Bean("ticket")
        @Scope("prototype")
        Ticket ticket() {
            return new Ticket();
        }

        @Bean("lazyFormatter")
        @Lazy
        LazyFormatter lazyFormatter() {
            return new LazyFormatter();
        }
    }

    private static void inspect(
            String label,
            ConfigurableApplicationContext context) {

        CatalogService service;

        try (context) {
            boolean lazyBefore = context.getBeanFactory()
                    .containsSingleton("lazyFormatter");

            service = context.getBean(
                    "catalogService", CatalogService.class);

            CatalogRepository repository =
                    context.getBean(CatalogRepository.class);

            boolean aliasSame =
                    service == context.getBean("publicCatalog");
            boolean repositorySame =
                    service.getRepository() == repository;
            boolean prototypeDistinct =
                    context.getBean("ticket")
                    != context.getBean("ticket");
            boolean dependsOnCorrect = Arrays.equals(
                    context.getBeanFactory()
                            .getBeanDefinition("catalogService")
                            .getDependsOn(),
                    new String[] {"startupMarker"});

            context.getBean("lazyFormatter");
            boolean lazyAfter = context.getBeanFactory()
                    .containsSingleton("lazyFormatter");

            String expected =
                    "INV:sku-42 retries=2 channels=[email, sms]";

            if (!expected.equals(service.report("42"))
                    || !aliasSame || !repositorySame
                    || !prototypeDistinct || !dependsOnCorrect
                    || !service.isStarted()
                    || lazyBefore || !lazyAfter) {
                throw new AssertionError(
                        label + " parity failed");
            }

            System.out.println(label + " report=" +
                    service.report("42"));
            System.out.println(label + " aliasSame=" + aliasSame);
            System.out.println(label + " repositorySame=" +
                    repositorySame);
            System.out.println(label + " prototypeDistinct=" +
                    prototypeDistinct);
            System.out.println(label + " dependsOnCorrect=" +
                    dependsOnCorrect);
            System.out.println(label + " started=" +
                    service.isStarted());
            System.out.println(label + " lazyBefore=" + lazyBefore);
            System.out.println(label + " lazyAfter=" + lazyAfter);
        }

        if (!service.isStopped()) {
            throw new AssertionError(
                    label + " destroy callback not invoked");
        }
        System.out.println(label + " stopped=" +
                service.isStopped());
    }

    public static void main(String[] args) {
        inspect("XML", new ClassPathXmlApplicationContext(
                "legacy-context.xml"));
        inspect("JAVA", new AnnotationConfigApplicationContext(
                JavaConfig.class));
    }
}
```

This is a complete Java file with a single top-level public class. Domain types are static nested classes; factory methods in `JavaConfig` do not invoke each other directly. The `@Bean` method `catalogService(...)` receives the managed repository from BeanFactory instead of creating a second repository.

### 10.4. How to Run

From the project root:

```bash
gradle run --quiet
```

When using the Gradle Wrapper:

```bash
./gradlew run --quiet
```

In Windows PowerShell:

```powershell
.\gradlew.bat run --quiet
```

Program stdout:

```text
XML report=INV:sku-42 retries=2 channels=[email, sms]
XML aliasSame=true
XML repositorySame=true
XML prototypeDistinct=true
XML dependsOnCorrect=true
XML started=true
XML lazyBefore=false
XML lazyAfter=true
XML stopped=true
JAVA report=INV:sku-42 retries=2 channels=[email, sms]
JAVA aliasSame=true
JAVA repositorySame=true
JAVA prototypeDistinct=true
JAVA dependsOnCorrect=true
JAVA started=true
JAVA lazyBefore=false
JAVA lazyAfter=true
JAVA stopped=true
```

Build tool or logging messages outside these `System.out.println` lines may appear depending on the environment. Assertions throw `AssertionError` if any parity contract in the example fails.

### 10.5. Output Explanation

**`report`:** both contexts supply identical prefix, retries, and ordered channels. Repository behavior returns `sku-42`, so business output matches.

**`aliasSame=true`:** XML `<alias>` and Java `@Bean(name=...)` both preserve the `publicCatalog` alias for `catalogService`.

**`repositorySame=true`:** `CatalogService`'s constructor receives the exact managed `CatalogRepository` singleton. There is no `new CatalogRepository()` inside the service factory method.

**`prototypeDistinct=true`:** two lookups of `ticket` in the same context return two distinct objects.

**`dependsOnCorrect=true`:** both definitions carry `startupMarker` dependency metadata.

**`started=true`:** Spring invokes the init method on the singleton service; factory code does not call `start()` manually.

**`lazyBefore=false`/`lazyAfter=true`:** before lookup, the lazy bean has no singleton instance yet; after lookup, it has been created.

**`stopped=true`:** `try-with-resources` closes the context and triggers the destroy callback.

### 10.6. Limitations of the Demo

The demo verifies the **declared contracts**, not that the two Spring contexts share identical internal infrastructure beans/metadata. It does not exercise transactions, component scanning, `FactoryBean`, profiles, or web scopes. Java `List.of` is unmodifiable; because the demo does not mutate `channels`, parity is proven for contents and order, **not** mutability. In real systems, add assertions for any remaining business contracts.

## 11. Running XML and JavaConfig Side by Side with `@ImportResource`

You do not need to delete all XML in a single commit. In a Java-centric application, you can do:

```java
@Configuration(proxyBeanMethods = false)
@ImportResource("classpath:legacy-infrastructure.xml")
class ApplicationConfig {

    @Bean
    NewService newService(LegacyRepository repository) {
        return new NewService(repository);
    }
}
```

This is **illustrative code** requiring class/domain types and imports. `@ImportResource` loads XML bean definitions; it differs from Java `@Import(AnotherConfig.class)`.

### 11.1. Each Bean Must Have One Intentional Registration Source

When migrating a bean from XML to Java:
- Register the new bean in JavaConfig.
- Remove the corresponding bean definition from the loaded XML.
- Check whether scanners or auto-configuration register that type/name as well.
- Test named lookups, injection, scopes, callbacks, and side effects.

Do not leave two bean definitions with the same name hoping override ordering picks the right one. Bean definition overriding policies depend on context and framework settings and should never be a migration strategy.

### 11.2. XML-Centric Apps Can Still Load JavaConfig

In an app whose entry point is `ClassPathXmlApplicationContext`, Spring can process a `@Configuration` class registered as a bean or scanned from a package if configuration post-processing is enabled. Do not simply add a class to XML assuming all `@Bean` methods are automatically recognized in every legacy bootstrap setup.

Java-centric `AnnotationConfigApplicationContext` with `@ImportResource` is usually a cleaner starting point when JavaConfig is the target. Still, migration can proceed in either direction depending on current boundaries.

### 11.3. Migrate in Small Modules

A safe rollout path:

1. Keep legacy XML infrastructure running.
2. Migrate a small group of domain beans with minimal side effects.
3. Run context parity tests.
4. Switch the composition root to use the new Java beans.
5. Delete the XML definitions for that group.
6. Continue with the next group, leaving complex namespace infrastructure for last.

Do not bundle major Spring version upgrades, business logic changes, and property precedence changes into the same batch when you need to prove behavior was preserved.

## 12. Cases Without a One-to-One Mapping

### 12.1. `FactoryBean` and the `&` Prefix

XML can register an implementation of `FactoryBean<T>`. Calling `getBean("connection")` returns the product, whereas `getBean("&connection")` retrieves the factory bean itself. Converting this directly to `@Bean Connection connection()` can break the factory contract.

If consumers rely on `&name`, preserve `FactoryBean` semantics or migrate consumers intentionally. Do not equate `FactoryBean` with a plain Java factory method.

### 12.2. Lookup-Method Injection

XML `<lookup-method>` allows a singleton to obtain a fresh prototype on every method call. Putting Java `@Scope("prototype")` on the target bean alone does not cause a singleton holding it to swap dependencies per call. Consider `ObjectProvider<T>`, a factory abstraction, or `@Lookup` under appropriate constraints, and test across multiple lookups.

### 12.3. XML Bean Inheritance

XML child bean definitions can inherit and override metadata from `parent="..."`. Java class inheritance does not replicate every rule of bean definition inheritance, particularly collection merging or abstract parent templates. Helper methods or factory patterns can replace it, provided merged metadata is verified.

### 12.4. Custom XML Namespaces

Some XML namespaces are backed by a vendor `NamespaceHandler` registering multiple bean definitions and proxies. Migrate pieces only when the vendor offers a corresponding Java DSL/API for your exact version. Keep XML via `@ImportResource` when no safe equivalent exists; never write a single `@Bean` assuming it reproduces an entire namespace's semantics.

### 12.5. Post-Processors, Proxies, and Infrastructure

An XML bean might be wrapped in a proxy by a `BeanPostProcessor`; if changing context bootstrapping drops that post-processor, the returned type and transaction behavior will differ even with the same target class. Test through **managed bean references**, not by calling Java factory methods directly.

### 12.6. Less Common Metadata

`role`, `description`, abstract definitions, lookup/replaced methods, custom qualifiers, `primary`, `autowire-candidate`, and scope-specific proxies can carry contracts for libraries or tooling. Not every setting has a identically named annotation; when needed, use programmatic bean definition registration APIs or keep XML temporarily.

## 13. Regression Testing: Use Evidence Instead of Eyeballing

### 13.1. Golden-Master Baseline Before Migration

Against the old XML context, capture:

- `getBean("name")` and alias lookups.
- Types and identities of key managed dependencies.
- Business method outputs for stable inputs.
- Singleton vs. prototype distinctions.
- Lifecycle init/destroy, lazy/eager timing, and `depends-on`.
- Active profiles and property precedence across dev/test/prod.
- Transaction commit/rollback, caching, schedulers, or messaging side effects where applicable.
- Whether multiple candidates exist per interface.

Then run the exact same checks against the new JavaConfig **with the same framework version, inputs, and runtime dependencies**.

### 13.2. Differential Test Across Two Contexts

Snippet from the demo:

```java
try (var legacy = new ClassPathXmlApplicationContext(
        "legacy-context.xml");
     var modern = new AnnotationConfigApplicationContext(
        XmlJavaParityDemo.JavaConfig.class)) {

    String oldValue = legacy.getBean(
            XmlJavaParityDemo.CatalogService.class)
            .report("42");
    String newValue = modern.getBean(
            XmlJavaParityDemo.CatalogService.class)
            .report("42");

    if (!oldValue.equals(newValue)) {
        throw new AssertionError("Business output changed");
    }
}
```

This is a **test fragment** needing imports and an enclosing class when placed in a separate file. One business assertion is necessary but insufficient: Section 10 also checks aliases, scopes, `depends-on`, laziness, and destruction.

### 13.3. Testing Across a Profile/Property Matrix

| Scenario | Input environment | Expectation |
| --- | --- | --- |
| Local | `dev` | Dev provider; no production resources instantiated |
| CI | `test` | Deterministic fake/stub |
| Production | `prod` | Real provider and transaction infrastructure |
| Missing required property | No endpoint | Fails fast with same policy as XML |
| Multiple profiles | `dev,metrics` | Consistent candidate selection |

This table is a template; tailor it to real environments. Do not compare two contexts fed different property sources and blame JavaConfig for the difference.

### 13.4. Test Shutdown Too

Many regressions only appear when the context closes: lingering threads, unclosed connection pools, or shared resources closed unexpectedly by inferred destroy callbacks. Test opening and closing contexts repeatedly and assert cleanup.

### 13.5. Do Not Compare Raw Bean Definition Counts Mechanically

`@Configuration` processing introduces infrastructure bean definitions different from XML. Focus on comparing the set of **business bean names/types** and behavior. If there is a dependency on specific infrastructure, assert that infrastructure explicitly.

## 14. Typical Mistakes When Converting XML to Java

| Symptom | Cause | Fix |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` by name | `@Bean` method changed the bean name | Specify `@Bean("oldName")` and aliases |
| Type injection becomes ambiguous | XML explicit `ref` → Java by-type parameter | Use qualifiers or named injection |
| Prototype becomes singleton | Forgot `@Scope("prototype")` | Restore scope and test identities |
| Lazy bean created immediately | Forgot `@Lazy` or an eager consumer injects it | Check metadata and dependency graph |
| Setter property missing | Factory method skipped calling setter | Inventory XML `<property>` tags |
| Wrong endpoint | Property source precedence shifted | Compare sources, order, and defaults |
| Init runs twice | Manual call + `initMethod` | Let container call it once |
| Destroy never runs | Forgot `destroyMethod` | Specify explicit callback and test `close()` |
| Destroy runs unexpectedly | `@Bean` inferred `close`/`shutdown` | Check `destroyMethod=""` |
| Service constructs dependency outside Spring | Factory called `new Dependency()` | Inject managed bean via parameter |
| Duplicate bean name | XML still imported alongside Java | Assign one owner per definition |
| Scope changed via context shift | Bean moved from child to root context | Keep context boundaries or refactor with tests |
| Transactions stop working | Lost `tx`/AOP infrastructure | Register Java equivalent and test rollback |
| Scan registers extra beans | Overly broad `@ComponentScan` | Tighten packages and filters |
| `FactoryBean` contract broken | Replaced factory with raw product | Preserve factory/product semantics |
| List becomes unmodifiable | Used `List.of` instead of mutable XML list | Use a mutable collection when needed |
| Prototype “never changes” per call | Singleton holds one injected prototype | Use a provider or lookup abstraction |
| Wrong profile | Converted XML profile block to mis-scoped `@Profile` | Test all profile combinations |
| Custom namespace loses behavior | Namespace handler not replaced | Keep XML or use matching vendor API |

## 15. Practical Rollout Roadmap

**Phase 1 — Capture baseline.** Record the Spring version, context hierarchy, XML files, property sources, profiles, bean contracts, integration tests, and startup/shutdown behavior. Avoid unrelated changes.

**Phase 2 — Build JavaConfig alongside in tests.** Write Java definitions **without registering them together with production XML**. Compare outputs across two test contexts.

**Phase 3 — Audit metadata.** Check aliases, scopes, laziness, lifecycles, explicit `depends-on`, candidates, and nontrivial namespace infrastructure.

**Phase 4 — Switch one module.** Update the root import to use JavaConfig for the tested bean group; remove that group's XML definitions from the active load path.

**Phase 5 — Observe.** Monitor startup, duplicate-bean issues, transactions, worker threads, shutdown, memory/CPU, logs, and metrics.

**Phase 6 — Roll back if needed.** Be able to flip the config source back without enabling XML and Java simultaneously. Only once stable should you remove obsolete XML and update ownership docs.

## 16. Exercises with Solutions

### Exercise 1 — Bean Name

XML `id="accountDao"` is converted to `@Bean AccountDao repository()`. Is `getBean("accountDao")` guaranteed to work?

**Answer:** No. The default name becomes `repository`. Keep `@Bean("accountDao")`.

### Exercise 2 — Alias

XML `<alias name="service" alias="publicService"/>`. What is a convenient Java equivalent?

**Answer:** `@Bean(name={"service","publicService"})` on a single factory method. Do not create two beans when XML only had an alias.

### Exercise 3 — Wrong Candidate

XML had `ref="safeStore"`. Java changes to injecting `Store store`, and the context has `@Primary` on `fastStore`. Is the collaborator preserved?

**Answer:** Not guaranteed. `@Primary` may cause `fastStore` to be injected. Use qualifiers or named wiring and test.

### Exercise 4 — Prototype

XML had `scope="prototype"`, and Java only writes `@Bean Ticket ticket()`. What is wrong?

**Answer:** Missing `@Scope("prototype")`; Java `@Bean` defaults to singleton.

### Exercise 5 — Lazy

XML had `lazy-init="true"`, and Java has `@Lazy`. However, an eager service injects that bean. Is the lazy bean guaranteed not to be created during refresh?

**Answer:** No; a required dependency from an eager bean triggers early creation.

### Exercise 6 — Init

A Java factory calls `start()` and declares `@Bean(initMethod="start")`. What happens?

**Answer:** The callback can run twice; keep a single source of lifecycle invocation.

### Exercise 7 — Destroy Inference

A bean has `public void close()`, old XML declared no custom destroy method, and Java converts it to `@Bean`. What must be checked?

**Answer:** `@Bean`'s inferred destroy callback. If legacy behavior requires not closing automatically, check `destroyMethod=""` and related lifecycle interfaces.

### Exercise 8 — `depends-on`

An XML service does not inject `marker`, yet specifies `depends-on="marker"`. Java deletes this ordering because “there is no constructor dependency.” Is that safe?

**Answer:** No; initialization and shutdown order may change. Keep `@DependsOn("marker")` for parity.

### Exercise 9 — `null` Property

XML uses nested `<null/>` for `memo`. Java calls `setMemo("")`. Are they equivalent?

**Answer:** No, if consumers distinguish `null` from empty string.

### Exercise 10 — Collection Mutability

XML list was mutable, Java uses `List.of(...)`, and business code adds an element. What happens?

**Answer:** The Java list is unmodifiable; behavior diverges. Choose an appropriate mutable collection and test.

### Exercise 11 — `@ImportResource`

An unmigrated repository remains in `legacy.xml`, while JavaConfig already migrated the service. Which mechanism bridges them?

**Answer:** `@ImportResource("classpath:legacy.xml")`, while ensuring the service is not registered twice across both sources.

### Exercise 12 — XML Infrastructure Namespaces

Legacy config used `<tx:annotation-driven/>`. JavaConfig only declares `@Bean` methods for services. Are transactions guaranteed to still work?

**Answer:** No. Matching transaction configuration, proxies, and a transaction manager are required, along with commit/rollback integration tests.

### Exercise 13 — `FactoryBean`

A consumer calls `getBean("&factory")`, and Java replaces the `FactoryBean` with a raw product factory method. Is parity preserved?

**Answer:** No, if the consumer depends on the factory object itself; preserve the contract or migrate consumers intentionally.

### Exercise 14 — Parent Context

The old bean lived in the servlet child context, while the new bean lives in the root context; name and class match. Are they automatically equivalent?

**Answer:** No; visibility, identity, and lifecycle boundaries can differ.

### Exercise 15 — Total Bean Definition Count

The XML context has fewer definitions than the JavaConfig context due to infrastructure beans. Can you conclude the migration is broken?

**Answer:** No. Compare business contracts and critical infrastructure rather than raw definition counts out of context.

### Exercise 16 — Runtime Properties

Legacy config reads from one properties file while Java reads from a different environment variable, and local defaults happen to match. Is parity proven?

**Answer:** Not yet. Test sources and precedence in environments where values differ from defaults.

## 17. Pre-Removal Checklist Before Deleting XML

- Have you located all XML files actually loaded in every environment?
- Are bean names, aliases, and string lookups preserved?
- Does dependency injection pick the exact same providers, especially with multiple candidates?
- Are scopes, laziness, `depends-on`, and init/destroy lifecycles accurate?
- Do property literals, type conversions, `null`/empty values, and collections preserve semantics?
- Did JavaConfig introduce any unintended inferred destroy callbacks?
- Was XML namespace infrastructure migrated and tested, or kept via `@ImportResource`?
- Do auto-scanned components create duplicate beans?
- Is there any bean name registered simultaneously by both XML and Java in the same context?
- Were tests run with the same Spring version, profiles, inputs, and property precedence?
- Do assertions cover behavior, identity, prototypes, and shutdown?
- Is there a rollback plan that never enables both bean definition sources at once?
- Are config classes organized along clear module boundaries?
- Is any retained XML documented with reason and owner?

## 18. Conclusion

Converting Spring XML to JavaConfig changes **how the bean graph is described**. To preserve behavior, you must preserve bean names and aliases, candidate selection, scopes, laziness, lifecycles, ordering, profiles, property precedence, and Spring infrastructure contracts. Many constructs map directly to `@Bean`/`@Scope`/`@Lazy`/`@DependsOn`/`@Profile`, whereas custom namespaces, `FactoryBean`s, lookup-method injection, and bean inheritance require dedicated design.

Do not treat a green context startup as sufficient proof. Spin up **two separate contexts**, feed identical inputs, and compare business output alongside key metadata, identity, and lifecycle callbacks. For incremental migrations, `@ImportResource` lets legacy XML coexist while you prevent duplicate definitions. Only after parity tests pass and production runs stably should you delete the replaced XML.

### Official Spring Documentation

- [Spring Framework 6.2 — Composing Java-based Configurations and XML](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/composing-configuration-classes.html).
- [Spring Framework 6.2 — Using `@Bean`](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/bean-annotation.html).
- [Spring Framework 6.2 — Basic Concepts: `@Bean` and `@Configuration`](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/basic-concepts.html).
- [Spring Framework 6.2 — Lazy-initialized Beans](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-lazy-init.html).
- [Spring Framework 6.2 — Using `depends-on`](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-dependson.html).
- [Spring Framework 6.2 — Bean Lifecycle](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html).
- [Spring Framework 6.2 — `Bean` Javadoc, names/aliases and destroy inference](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/annotation/Bean.html).
