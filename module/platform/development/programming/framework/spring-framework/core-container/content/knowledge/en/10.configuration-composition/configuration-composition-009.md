# Avoiding Circular Dependencies Between Configuration Classes in Spring Core Container

## Lesson Objectives

As a Spring application grows, splitting Java configuration into multiple `@Configuration` classes helps organize beans by module: database, repositories, services, integrations, and entry points. However, if configuration classes **import each other**, **constructor-inject each other**, or **access beans they define themselves too early**, you can create a *circular dependency*.

A common mistake looks like:

```text
ServiceConfig  --->  RepositoryConfig
     ^                    |
     |                    |
     +--------------------+
```

Those arrows might represent `@Import`, constructor injection between two configuration classes, or a dependency between objects declared with `@Bean`. **These three cases are not identical**, and diagnosing and fixing them properly depends on which kind of edge forms the cycle.

This lesson focuses on **“Avoiding Circular Dependencies Between Configuration Classes”**, part of the *Configuration Composition* section of Spring Framework Core Container. After this lesson, you will:

1. Distinguish **configuration-class import cycles**, **configuration-bean creation cycles**, and **dependency cycles between application beans**.
2. Use `@Import` in a unidirectional structure rather than letting module configs know about and import one another.
3. Use **`@Bean` method parameters** to express dependencies between bean definitions across different configuration classes.
4. Understand why constructor injection on a `@Configuration` class itself can sometimes cause **early initialization / self-reference cycles**.
5. Avoid calling `@Bean` methods inside `@PostConstruct` on a configuration class.
6. Understand the difference between full `@Configuration` and `@Configuration(proxyBeanMethods=false)`, and know when direct method calls create unmanaged objects.
7. Read the true root cause of `BeanCurrentlyInCreationException`, `UnsatisfiedDependencyException`, and `@Import` cycles.
8. Evaluate the limits of `@Lazy`, `ObjectProvider`, `@DependsOn`, and the option to allow circular references.
9. Have a complete Java 17 + Spring Framework design example using root composition and type-based wiring with no cycles.
10. Write integration tests to detect cycles early and prevent regressions.

**Guiding principle:** A `@Configuration` class should **declare how beans are created**, not act as a service needing direct dependencies on other configuration classes. Let **business beans depend on appropriate abstractions**, while a **root configuration** composes modules unidirectionally.

## 1. Three Kinds of Cycles Often Conflated

Not every cycle in Spring lives at the same layer. Before editing code, draw the graph and identify what the **nodes** are.

### 1.1. Import Cycle: Configuration Class A Imports B, B Imports A

```java
// COUNTEREXAMPLE: Two configuration classes importing each other.
@Configuration
@Import(ConfigB.class)
class ConfigA {
}

@Configuration
@Import(ConfigA.class)
class ConfigB {
}
```

Graph:

```text
ConfigA --@Import--> ConfigB
ConfigB --@Import--> ConfigA
```

`@Import` tells Spring “also process this configuration class”, **not** “instantiate an object as a dependency for the other class”. When the import graph contains a cycle, Spring's configuration parser can detect and reject it, for example with messages related to `A circular @Import has been detected` or a configuration parsing failure.

The standard fix is **lifting coordination up to a root**:

```java
@Configuration(proxyBeanMethods = false)
@Import({ConfigA.class, ConfigB.class})
class RootConfig {
}

// ConfigA and ConfigB no longer @Import each other.
```

Organizationally, the root knows which modules need to be assembled into an application; modules do not need to know about each other's configurations.

### 1.2. Constructor Cycle Between `@Configuration` Beans Themselves

```java
// COUNTEREXAMPLE: Both configuration classes require an instance of the other.
@Configuration
class BillingConfig {
    BillingConfig(ShippingConfig shippingConfig) {
    }
}

@Configuration
class ShippingConfig {
    ShippingConfig(BillingConfig billingConfig) {
    }
}
```

Graph:

```text
BillingConfig instance --> ShippingConfig instance
ShippingConfig instance --> BillingConfig instance
```

Spring treats `@Configuration` classes as beans in the container. If `BillingConfig` must be created before `ShippingConfig`, yet `ShippingConfig` must be created before `BillingConfig`, constructor injection cannot complete.

Crucial point: this cycle occurs **between the configuration instances themselves**, not necessarily between `InvoiceService` and `ShippingService`. Usually the best fix is **not injecting configuration classes into configuration classes**; instead, declare dependencies by the **needed bean type** right on the `@Bean` method.

### 1.3. Constructor Cycle Between Beans Created by `@Bean`

```java
// COUNTEREXAMPLE: Two business types require each other right in their constructors.
@Configuration(proxyBeanMethods = false)
class BadBusinessConfig {

    @Bean
    ServiceA serviceA(ServiceB b) {
        return new ServiceA(b);
    }

    @Bean
    ServiceB serviceB(ServiceA a) {
        return new ServiceB(a);
    }
}
```

Here `ServiceA` and `ServiceB` are illustrative types whose constructors accept each other. The actual graph:

```text
bean "serviceA" --> bean "serviceB"
bean "serviceB" --> bean "serviceA"
```

When Spring creates bean A, it needs B; creating B needs A, which is currently in creation. Unresolvable constructor cycles typically result in `BeanCurrentlyInCreationException`, often nested inside an exception chain containing `UnsatisfiedDependencyException` or `BeanCreationException`.

**Essential distinction:** Moving those two `@Bean` methods into two separate `@Configuration` classes **does not make the bean cycle disappear**. You must fix **the dependency direction between application beans**, not merely where they are declared.

## 2. Why Can Multiple Configuration Classes Still Depend on Each Other's Beans?

Spring **does not require** a configuration class to create only beans it completely self-contains. A bean in the service module can freely depend on a repository bean declared by another module.

Example:

```java
@Configuration(proxyBeanMethods = false)
class RepositoryConfig {

    @Bean
    AccountRepository accountRepository() {
        return new InMemoryAccountRepository();
    }
}
```

```java
@Configuration(proxyBeanMethods = false)
class ServiceConfig {

    @Bean
    AccountService accountService(AccountRepository accountRepository) {
        return new AccountService(accountRepository);
    }
}
```

```java
@Configuration(proxyBeanMethods = false)
@Import({RepositoryConfig.class, ServiceConfig.class})
class ApplicationConfig {
}
```

This is an **illustrative pattern**, requiring `AccountRepository`, `InMemoryAccountRepository`, and `AccountService` types with matching constructors.

Import graph:

```text
             ApplicationConfig
                /       \
           @Import      @Import
              /           \
RepositoryConfig         ServiceConfig
```

Dependency graph **between beans**:

```text
accountService --> accountRepository
```

There is no cycle. `ServiceConfig` **does not need to import `RepositoryConfig`** just because `accountService(AccountRepository)` requires a repository bean. Once the root brings both configs into the same context, BeanFactory sees the definitions and resolves the parameter by type.

This is a key point in module design: **configuration classes can be independent at the source-reference level, while their beans are wired together through the IoC container**.

### Role of `@Import`

`@Import` belongs to:

```java
import org.springframework.context.annotation.Import;
```

It lets a root configuration gather appropriate configurations or components for Spring to process. Its arguments are **class references**, not bean instances. `@Import` does not inject one configuration instance into another configuration.

### Role of `@Bean` Parameters

```java
@Bean
AccountService accountService(AccountRepository repository) {
    return new AccountService(repository);
}
```

The `AccountRepository` parameter is a **dependency request** to BeanFactory, allowing Spring to resolve the bean by type, qualifier, primary status, generics, and scope. There is no reason to call `new RepositoryConfig().accountRepository()` or hold a `RepositoryConfig` field inside `ServiceConfig` to obtain the bean.

## 3. Unidirectional Design: Root Composition and Autonomous Modules

For a layered application, an easy-to-maintain architecture looks like:

```text
                     RootConfig
                   /     |      \
                  v      v       v
              Infra    Repo    Service
              Config   Config  Config

Bean dependencies:
CatalogService  ---> CatalogRepository
       |
       +-----------> Clock
       |
       v
CatalogFacade
```

**Configuration classes** are imported from the root. **Application beans** are wired via injection. There is no need for a `ServiceConfig -> RepositoryConfig` edge just so a service can use a repository bean.

### Setting Module Boundaries

- `InfrastructureConfig` is responsible for registering clock, data source, HTTP client, codecs, or shared infrastructure.
- `RepositoryConfig` is responsible for repository implementations.
- `ServiceConfig` is responsible for service beans.
- `RootConfig` decides which modules the application needs.
- No module needs to hold another module's configuration class instance.

This organization makes **dependency direction** explicit. You can organize packages by feature instead of by layer; the principle remains choosing a clear root composition with no cycles.

### What If One Module Truly Needs Another Module?

Separate two questions:

1. “Does the application need both configurations loaded?” — root `@Import` handles this.
2. “Does bean A need bean B?” — constructor or factory method parameter injection handles this.

Do not answer both with “config A imports config B and takes `BConfig` in its constructor”. That increases coupling and easily causes cycles later when module B needs to import A.

## 4. Anti-Pattern: Injecting Another Configuration Class to Call Its Factory Method

Hard-to-maintain example:

```java
@Configuration
class RepositoryConfig {

    @Bean
    CatalogRepository catalogRepository() {
        return new JdbcCatalogRepository();
    }
}

@Configuration
class ServiceConfig {

    private final RepositoryConfig repositoryConfig;

    ServiceConfig(RepositoryConfig repositoryConfig) {
        this.repositoryConfig = repositoryConfig;
    }

    @Bean
    CatalogService catalogService() {
        return new CatalogService(
                repositoryConfig.catalogRepository());
    }
}
```

This is a **counterexample** with hypothetical application classes. Even if full configuration proxying might intercept the call in some cases, it couples `ServiceConfig` to the repository module's **implementation/configuration class** instead of the `CatalogRepository` dependency contract.

Risks:

- Refactoring how the repository is registered forces `ServiceConfig` to change as well.
- If `RepositoryConfig` ever needs a dependency from the service module, a cycle between config instances easily forms.
- Easy to confuse a plain Java method call with retrieving a Spring-managed singleton, especially if switching to `proxyBeanMethods=false`.
- Unit tests of the factory method unnecessarily have to construct another configuration instance.
- Hard to move the bean to XML, a registrar, or component scan without editing wiring code.

### Fix Using Factory Method Parameters

```java
@Configuration(proxyBeanMethods = false)
class ServiceConfig {

    @Bean
    CatalogService catalogService(CatalogRepository repository) {
        return new CatalogService(repository);
    }
}
```

In the root:

```java
@Configuration(proxyBeanMethods = false)
@Import({RepositoryConfig.class, ServiceConfig.class})
class RootConfig {
}
```

Thus `ServiceConfig` does not need to know which class `RepositoryConfig` is. BeanFactory satisfies the dependency by contract.

## 5. Anti-Pattern: Configuration Class Injecting a Bean It Declares Itself

A subtler cycle happens when a configuration class demands **the result of its own instance method**.

```java
// COUNTEREXAMPLE: StorageConfig needs Storage to be constructed,
// yet Storage is created by an instance method on StorageConfig.
@Configuration
class StorageConfig {

    private final Storage storage;

    StorageConfig(Storage storage) {
        this.storage = storage;
    }

    @Bean
    Storage storage() {
        return new Storage();
    }
}
```

Graph:

```text
configuration bean "storageConfig"
           |
           | constructor requires Storage
           v
bean "storage"
           |
           | instance @Bean factory requires storageConfig instance
           v
configuration bean "storageConfig"
```

Spring must instantiate the configuration instance before invoking the non-static factory method `storage()` on that instance, yet the config constructor demands the bean produced by that very method. This is a **self-reference cycle** at bean creation time.

### Fix 1: Do Not Pass Storage into the Configuration Constructor

```java
@Configuration(proxyBeanMethods = false)
class StorageConfig {

    @Bean
    Storage storage() {
        return new Storage();
    }

    @Bean
    StorageConsumer storageConsumer(Storage storage) {
        return new StorageConsumer(storage);
    }
}
```

In this example, `StorageConsumer` has a constructor taking `Storage`. The config does not hold `Storage` in a field; Spring injects it directly into the factory method that needs it.

### Fix 2: Use an Independent Infrastructure Configuration

```java
@Configuration(proxyBeanMethods = false)
class InfrastructureConfig {

    @Bean
    Storage storage() {
        return new Storage();
    }
}

@Configuration(proxyBeanMethods = false)
class ConsumerConfig {

    @Bean
    StorageConsumer storageConsumer(Storage storage) {
        return new StorageConsumer(storage);
    }
}
```

One root imports both. Neither config injects a bean produced by its own instance factory method.

### Fix 3: `static @Bean` for Appropriate Infrastructure Types

Certain bean post-processors are declared with `static @Bean`, allowing BeanFactory to create them **without instantiating the configuration class prematurely**. However, that applies to infrastructure with special lifecycle requirements, not a general recipe to turn every bean static.

Example:

```java
// Illustrative snippet, not a recommendation for every @Bean.
@Configuration(proxyBeanMethods = false)
class InfrastructureConfig {
    @Bean
    static SomeBeanFactoryPostProcessor somePostProcessor() {
        return new SomeBeanFactoryPostProcessor();
    }
}
```

`SomeBeanFactoryPostProcessor` must be an appropriate implementation. Key takeaway: use `static` when the bean genuinely belongs to bootstrap post-processors, and understand how it differs from instance factory methods.

## 6. Do Not Call Configuration Beans Inside `@PostConstruct` on the `@Configuration` Itself

This is an explicit warning in Spring's documentation on composing Java configurations.

```java
// COUNTEREXAMPLE: Do not retrieve a bean defined by the config itself
// inside @PostConstruct of that same config class.
@Configuration
class RiskyConfig {

    @Bean
    DataClient dataClient() {
        return new DataClient();
    }

    @PostConstruct
    void init() {
        dataClient().connect();
    }
}
```

This snippet uses Jakarta Annotations' `@PostConstruct` and assumes `DataClient` has a `connect()` method. It only illustrates the risk, not a safe application.

Because `@Configuration` is itself a bean and instance `@Bean` methods need the config instance ready, trying to fetch a locally declared bean **while the config instance is still in initialization** can create a self-reference/circular creation problem. When circular references are disallowed, you can hit `BeanCurrentlyInCreationException`.

In addition:

- `@PostConstruct` runs during **the configuration bean's lifecycle**, not after the entire application has finished starting.
- Calling a factory method directly in lite mode creates a plain Java object **not managed by BeanFactory**.
- Opening network connections or running business logic in initialization callbacks can also slow startup, cause deadlocks, or leak resources.
- Adding `@Lazy` to a bean does not guarantee self-invocation inside `init` is safe.

### Fix: Bean-Local Initialization on the Managed Bean

If `DataClient` has a `connect()` method suitable for **its own** lifecycle:

```java
@Configuration(proxyBeanMethods = false)
class ClientConfig {

    @Bean(initMethod = "connect", destroyMethod = "close")
    DataClient dataClient() {
        return new DataClient();
    }
}
```

Spring calls `connect` on the **managed `DataClient` bean**, and `close` per singleton lifecycle when the context closes. There is no need to call `dataClient()` from `ClientConfig`'s `@PostConstruct`.

If the operation is business bootstrap coordinating multiple beans, use an appropriate dedicated coordinator/startup lifecycle hook rather than putting it inside config initialization.

## 7. Full and Lite `@Configuration` Do Not Eliminate Real Cycles

With full configuration:

```java
@Configuration
class FullConfig {
    @Bean
    X x() {
        return new X(y());
    }

    @Bean
    Y y() {
        return new Y();
    }
}
```

When `y()` is called on the Spring-managed enhanced configuration instance, Spring can intercept it to retrieve the `y` bean according to its scope. This preserves proper bean identity in an **acyclic** dependency graph.

With lite configuration:

```java
@Configuration(proxyBeanMethods = false)
class LiteConfig {
    @Bean
    X x() {
        return new X(y());
    }

    @Bean
    Y y() {
        return new Y();
    }
}
```

Calling `y()` inside `x()` is just a plain Java call; it can create a separate `Y` object rather than the managed `y` bean. That is an **identity/lifecycle bug**, not necessarily a circular dependency error; therefore lite mode is **not a “cycle cure”** and can hide other risks.

### Common Pattern for Both Full and Lite

```java
@Configuration(proxyBeanMethods = false)
class SafeConfig {
    @Bean
    X x(Y y) {
        return new X(y);
    }

    @Bean
    Y y() {
        return new Y();
    }
}
```

Spring resolves the factory method parameter so identity stays intact. If `Y` in turn depends on `X` via constructor, you still have a **real bean cycle** and must refactor the dependency direction.

**Remember:** Switching `proxyBeanMethods=true` to `false` does not eliminate import cycles or constructor cycles. It only changes how Java calls to bean methods are handled. Always inspect the **bean dependency graph**, not just the configuration enhancement flag.

## 8. Java 17 + Spring Framework Example: Cycle-Free Configuration Composition

The runnable example below demonstrates a small application with:

- `InfrastructureConfig` creating a fixed `Clock` for deterministic output.
- `RepositoryConfig` creating `CatalogRepository`.
- `ServiceConfig` creating `CatalogService` via **`@Bean` parameters** receiving both dependencies.
- `RootConfig` importing those three configurations via **unidirectional `@Import`** and creating `CatalogFacade`.
- No config injects another configuration class.
- Bean dependencies point unidirectionally and Spring manages singleton identity.

The project only requires Java 17+, Maven, and `spring-context`—no Spring Boot, web server, database, or external network.

### 8.1. Project Structure

```text
config-cycle-free/
├── pom.xml
└── src/main/java/
    └── demo/
        └── CycleFreeConfigDemo.java
```

### 8.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
             http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>config-cycle-free</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
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

### 8.3. Full Java Code

Create `src/main/java/demo/CycleFreeConfigDemo.java`:

```java
package demo;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.Arrays;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;

public class CycleFreeConfigDemo {

    public interface CatalogRepository {
        String labelFor(String sku);
    }

    public static final class InMemoryCatalogRepository
            implements CatalogRepository {

        @Override
        public String labelFor(String sku) {
            return switch (sku) {
                case "BK-7" -> "Java book";
                case "MUG-2" -> "Coffee mug";
                default -> "Unknown";
            };
        }
    }

    public static final class CatalogService {
        private final CatalogRepository repository;
        private final Clock clock;

        public CatalogService(CatalogRepository repository, Clock clock) {
            this.repository = repository;
            this.clock = clock;
        }

        public String describe(String sku) {
            return repository.labelFor(sku) + "@" +
                    LocalDate.now(clock);
        }

        public CatalogRepository repository() {
            return repository;
        }
    }

    public static final class CatalogFacade {
        private final CatalogService service;

        public CatalogFacade(CatalogService service) {
            this.service = service;
        }

        public String show(String sku) {
            return "facade:" + service.describe(sku);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class InfrastructureConfig {

        @Bean
        public Clock fixedClock() {
            return Clock.fixed(
                    Instant.parse("2024-01-01T00:00:00Z"),
                    ZoneOffset.UTC);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class RepositoryConfig {

        @Bean
        public CatalogRepository catalogRepository() {
            return new InMemoryCatalogRepository();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class ServiceConfig {

        @Bean
        public CatalogService catalogService(
                CatalogRepository repository, Clock clock) {
            return new CatalogService(repository, clock);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @Import({
        InfrastructureConfig.class,
        RepositoryConfig.class,
        ServiceConfig.class
    })
    public static class RootConfig {

        @Bean
        public CatalogFacade catalogFacade(CatalogService service) {
            return new CatalogFacade(service);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(RootConfig.class)) {

            CatalogRepository repository =
                    context.getBean(CatalogRepository.class);
            CatalogService service =
                    context.getBean(CatalogService.class);
            CatalogFacade facade =
                    context.getBean(CatalogFacade.class);

            System.out.println("repo=" + repository.labelFor("BK-7"));
            System.out.println("service=" + service.describe("BK-7"));
            System.out.println("facade=" + facade.show("MUG-2"));
            System.out.println("sameRepository=" +
                    (service.repository() == repository));

            String[] repositoryNames =
                    context.getBeanNamesForType(CatalogRepository.class);
            Arrays.sort(repositoryNames);
            System.out.println("repositoryBeans=" +
                    Arrays.toString(repositoryNames));
        }
    }
}
```

### 8.4. Run Command

Run from the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.CycleFreeConfigDemo
```

Lines **printed by the program itself**, excluding Maven logs or environment logging bindings:

```text
repo=Java book
service=Java book@2024-01-01
facade=facade:Coffee mug@2024-01-01
sameRepository=true
repositoryBeans=[catalogRepository]
```

### 8.5. Why Is the Output Accurate?

**`repo=Java book`:** Bean `catalogRepository` is declared by `RepositoryConfig`, returning `InMemoryCatalogRepository`. `labelFor("BK-7")` returns the fixed string `Java book`.

**`service=Java book@2024-01-01`:** `CatalogService` is created by Spring via factory method `catalogService(CatalogRepository, Clock)`. It receives the singleton repository and `Clock.fixed(...)` from `InfrastructureConfig`. `LocalDate.now(clock)` yields `2024-01-01`, independent of the host machine's clock.

**`facade=facade:Coffee mug@2024-01-01`:** Root creates `CatalogFacade` using the `CatalogService` parameter injected by Spring. The facade calls the service with `MUG-2`, the repository returns `Coffee mug`, and the facade prepends `facade:`.

**`sameRepository=true`:** `CatalogService` receives the **managed singleton repository** resolved by Spring by type. `getBean(CatalogRepository.class)` returns the same reference within the same context.

**`repositoryBeans=[catalogRepository]`:** Only one definition of type `CatalogRepository` exists; the default name of the `@Bean` factory method is `catalogRepository`. Every module shares one BeanFactory, with no extra repository instantiated via `new RepositoryConfig().catalogRepository()`.

### 8.6. Graphs in the Example

```text
RootConfig
  |--@Import--> InfrastructureConfig  --@Bean--> Clock
  |--@Import--> RepositoryConfig      --@Bean--> CatalogRepository
  |--@Import--> ServiceConfig         --@Bean--> CatalogService
  |
  +-------------- @Bean ---------------------> CatalogFacade

Bean dependencies (opposite to supply direction):
CatalogFacade ---> CatalogService ---> CatalogRepository
                         |
                         +-----------> Clock
```

There is no path from repository back to service or from infrastructure to facade. Both the import graph and the bean dependency graph are **cycle-free**.

### 8.7. Why Does RootConfig Only Import Without Instantiating Configs?

`@Import(RepositoryConfig.class)` tells Spring to process that configuration class. Writing:

```java
// COUNTEREXAMPLE: do not instantiate configuration classes manually.
RepositoryConfig repoConfig = new RepositoryConfig();
CatalogRepository repo = repoConfig.catalogRepository();
```

creates a repository object outside managed bean definitions, bypassing BeanFactory management. In lite configuration, direct calls can also create instances separate from the singleton. The right way is letting `@Import` bring bean definitions into the container and using `@Bean` parameter injection.

### 8.8. What If Another Module Is Added?

Suppose there is a `NotificationConfig` registering a `NotificationService` that depends on `CatalogService`. You can:

1. Create `NotificationConfig` with `@Bean NotificationService notificationService(CatalogService service)`.
2. Add `NotificationConfig.class` to **`RootConfig`**'s import array.
3. Do not make `ServiceConfig` import `NotificationConfig` just because another service uses the catalog.
4. Keep business dependencies unidirectional; if notification ever forces catalog service to depend back on notification, that signals a need to extract an abstraction or event.

The root can know all modules assembled to run the application, while individual modules do not need to know the entire map.

## 9. Reading Cycles in Stack Traces and Bean Graphs

When a context fails to initialize, the top-level exception might look like:

```text
BeanCreationException
  -> UnsatisfiedDependencyException
     -> BeanCurrentlyInCreationException
```

You will not always see this exact wrapper chain; exception types and wrapping depth depend on the failure stage and how beans are created. What matters is reading the **root cause** and lines stating “A depends on B, B depends on A”.

Illustrative trace:

```text
serviceA
   |
   v
serviceB
   |
   v
serviceA  (currently in creation)
```

If the cycle nodes are **beans**, look for constructors, factory-method parameters, or field injections causing bidirectional requirements. If the cycle nodes are **configuration classes** importing each other, the error may happen inside the configuration parser **before any bean instances exist**. If the nodes are **a configuration instance and a locally defined bean**, check config constructors, `@PostConstruct`, or early config injection.

### Quick Identification Table

| Clue | Where Might the Cycle Be? | Where to Inspect |
| --- | --- | --- |
| Message `A circular @Import has been detected` | Import graph | Direct/meta-present `@Import` annotations, import chains |
| `BeanCurrentlyInCreationException` naming two services | Constructor/factory dependency graph | Service constructors, `@Bean` parameters, hidden service locators |
| Exception naming a configuration bean and a locally defined bean | Config early creation/self-reference | Config constructor, `@Autowired` fields, `@PostConstruct` |
| Failure or duplicate objects after switching `proxyBeanMethods=false` | Direct `@Bean` calls in lite mode | Replace with factory method parameters |
| `BeanCreationException` on static post-processor `@Bean` | Infrastructure bootstrap/lifecycle | `static`/non-static declaration, constructor side effects |
| Error occurs only when enabling a specific profile | Conditional bean graph | `@Profile`, bean availability in that profile |
| Fails only in tests using a configuration subset | Missing definitions or cycle exposed by test config | Root imports, test slices, mock bean replacements |

**Do not diagnose solely by exception name.** `UnsatisfiedDependencyException` can also come from missing beans, multiple candidates, wrong qualifiers, or constructor errors; it does not prove a cycle without specific `currently in creation` evidence.

## 10. `@Import` and `@ComponentScan`: Boundaries to Understand

A configuration class can enter a context via:

- `AnnotationConfigApplicationContext(RootConfig.class)`.
- `@Import(SomeConfig.class)` from another config.
- Component scanning when a `@Configuration` class (meta-annotated with `@Component`) lies inside the scan root.
- Appropriate framework bootstrap/import selector mechanisms.

Multiple **registration paths** reaching the same configuration class do not necessarily create duplicate beans if Spring recognizes the same definition; however, never rely on duplicate imports to impose ordering or magically “break cycles”.

### Avoid Overly Broad Scanning in Complex Module Systems

```java
@ComponentScan(basePackages = "com.company")
```

can pull in multiple configuration classes that the application did not intend to run together. This sometimes activates new bean definitions, type ambiguity, or reverse-dependent configs that an explicit root import would have left out.

When strict module boundaries are needed, use explicit imports or feature-scoped component scanning. Still, do not say “component scan causes cycles” in every case: actual cycles come from the **dependency graph** after beans/configs are selected.

### An `@Import` Cycle Is Not Always a Bean Cycle

An acyclic import graph does not guarantee an acyclic bean graph. Conversely, two independent service beans can sit inside two config classes that accidentally import each other.

That is why QA should verify both **composition** and **dependency wiring**, not merely how `@Configuration` files are organized.

## 11. Business Service Cycles Must Be Broken at the Design Level

If:

```text
OrderService ---> PaymentService
PaymentService ---> OrderService
```

changing `@Import`, moving `@Bean` to another file, or toggling `proxyBeanMethods` will not remove the bidirectional requirement. Usually one of these directions is needed:

### 11.1. Extract Shared Responsibility into a Third Bean

Before:

```text
OrderService <----> PaymentService
```

After:

```text
OrderService ----> PaymentPolicy <---- PaymentService
```

Each service depends on a shared abstraction `PaymentPolicy`, without injecting the other service.

### 11.2. Extract a Higher-Level Coordinator / Use Case

```text
          CheckoutCoordinator
             /        \
            v          v
       OrderService  PaymentService
```

The coordinator invokes both services in use-case sequence, rather than each service requiring the other to be instantiated first. This fits especially well when the cycle stems from **orchestration** rather than true domain logic dependency.

### 11.3. Use Events to Notify Instead of Direct Reverse Calls

One service performs an action and publishes a domain/application event; another component reacts according to designed lifecycle, transaction, and idempotency rules. This can reduce coupling, though events do not exempt you from designing ordering, error handling, data consistency, and transaction boundaries.

### 11.4. Clarify Inward-Pointing Interfaces

If a repository needs to call a business service to decide logic, the data layer may be depending backward on the application layer. Move the policy/rule into an appropriate abstraction or pass values into repository methods rather than forcing the repository to inject the whole service.

**Important:** “Breaking a cycle” properly means ensuring the dependency graph **has no edge returning to an ancestor node on the path**, not merely delaying when Spring detects the error.

## 12. Does `@Lazy` Help?

`@Lazy` can defer resolution of a dependency injection point through a proxy in certain cases.

Illustrative example:

```java
class ServiceA {
    ServiceA(@Lazy ServiceB serviceB) {
        this.serviceB = serviceB;
    }
}

class ServiceB {
    ServiceB(ServiceA serviceA) {
        this.serviceA = serviceA;
    }
}
```

If Spring injects a proxy for `ServiceB` instead of eagerly instantiating bean B, it can avoid requiring B immediately while constructing A. However:

- It is still a **bidirectional logical dependency**.
- If the proxy is dereferenced too early or during init/construction, the cycle can reappear.
- Type/proxying constraints apply (for example final types or proxy semantics).
- Deferral does not fix coupling, state ownership, or business responsibility.
- It does not resolve `@Import` cycles between configuration classes.

**Recommendation:** `@Lazy` is a tool for choosing resolution timing when a dependency is genuinely meant to be lazy—**not a default band-aid to hide every circular reference**.

## 13. `ObjectProvider` and `Provider`: Conditional Deferred Lookup

If a service only needs a collaborator **at the time an operation executes**, you can inject:

```java
import org.springframework.beans.factory.ObjectProvider;

class DeferredClient {
    private final ObjectProvider<RemoteGateway> gatewayProvider;

    DeferredClient(ObjectProvider<RemoteGateway> gatewayProvider) {
        this.gatewayProvider = gatewayProvider;
    }

    String sendLater(String message) {
        RemoteGateway gateway = gatewayProvider.getObject();
        return gateway.send(message);
    }
}
```

This illustration requires a `RemoteGateway` interface. `ObjectProvider` lets you fetch the bean when `sendLater` runs instead of forcing resolution inside the constructor.

However:

- If `getObject()` is called in the constructor or `@PostConstruct`, you can recreate the early creation cycle.
- If a cycle is only avoided because two methods do not run simultaneously, the architecture may remain fragile.
- `getIfAvailable()` and `getIfUnique()` fit **truly optional dependencies**; never use them to silently ignore mandatory dependencies just to make the context start.
- It does not replace root composition for the import graph.
- If the target bean is prototype/scoped, lookup timing carries lifecycle/identity implications that must be designed intentionally.

**Use providers only** when dynamic/lazy lookup is a real business or infrastructure requirement, not to silence a cycle error without fixing the design.

## 14. `@DependsOn` Is Not a Cycle-Breaking Tool

`@DependsOn` adds **bean initialization ordering constraints**. Example:

```java
@Bean
@DependsOn("schemaValidator")
ReportService reportService() {
    return new ReportService();
}
```

Meaning: bean `schemaValidator` must be initialized before Spring initializes `reportService`, alongside the report service's direct dependencies. It does not supply an instance to satisfy a constructor parameter, and it cannot make an A→B→A cycle instantiable.

If:

```text
A --dependsOn--> B
B --dependsOn--> A
```

then you have created an **ordering cycle**. Spring cannot initialize A before B and B before A simultaneously. Switching constructor injection to `@DependsOn` is not a solution when two beans genuinely hold references to one another.

Use `@DependsOn` for genuine ordering constraints, such as an infrastructure component requiring a validation step to complete first; do not use it for business orchestration or dependency inversion.

## 15. Should You Enable Allowing Circular References?

Spring Boot has the property:

```properties
spring.main.allow-circular-references=true
```

In modern Spring Boot versions, the default for this option is usually `false`. Still, this lesson clearly distinguishes **Spring Framework Core** from **Spring Boot**:

- `spring.main.allow-circular-references` is a **Spring Boot setting**, not a direct configuration syntax of `AnnotationConfigApplicationContext` in plain Spring Framework.
- Some circular dependencies via setter/field injection can be resolved by Spring BeanFactory using early references when the mechanism permits.
- **Constructor-to-constructor cycles** like A(B)→B(A) are still generally unresolvable, even with circular references enabled.
- Circular `@Import` in the configuration parser cannot be fixed by a bean factory flag.
- Early references can interact awkwardly with AOP proxies, init callbacks, and incomplete state.

**Conclusion:** Do not enable this flag as a default “fix”. It is a temporary compatibility measure during certain migrations, requiring tests and a refactoring plan. Long term, fixing **dependency direction** is far better.

### If Using Plain Spring Framework

`DefaultListableBeanFactory`/`AbstractAutowireCapableBeanFactory` exposes circular reference handling options at the bean factory level. That is an infrastructure configuration API, not the first step to fix a circular dependency design.

In section 8's runnable example, no circular-allowing mechanism is needed; the bean graph is already acyclic.

## 16. `@Configuration`-Specific Traps

### 16.1. Config Constructor Injection Pulling a Bean It Defines Itself

```java
@Configuration
class FeatureConfig {

    FeatureConfig(FeatureRegistry registry) {
        // ...
    }

    @Bean
    FeatureRegistry registry() {
        return new FeatureRegistry();
    }
}
```

Unless another eligible `FeatureRegistry` bean exists, the config constructor demands a bean that requires the config itself to finish constructing first. That is a classic self-reference cycle. Do not move the injection to an `@Autowired` field thinking it is safely fixed: field injection can still trigger early initialization and incomplete state.

### 16.2. `@PostConstruct` on a Configuration Class Calling `@Bean`

As noted in section 6, Spring docs explicitly warn that accessing locally defined beans in `@PostConstruct` on the same configuration class can trigger circular references. Move state preparation into the target bean's lifecycle or a separate startup coordinator.

### 16.3. `BeanFactoryPostProcessor` and `BeanPostProcessor`

These post-processors run **very early** during container bootstrap. If declared with **non-static `@Bean`**, creating them can force Spring to instantiate the configuration class prematurely, before `@Autowired`/`@Value` on the configuration class itself are processed as expected.

Such post-processor beans should usually use **`static @Bean`** so the config instance does not need early creation. Only do this when defining that kind of infrastructure bean, not on ordinary services.

### 16.4. `@Configuration(proxyBeanMethods=false)` Does Not Fix Import Cycles

This flag disables CGLIB interception of `@Bean` methods; it does not fix `ConfigA` importing `ConfigB` while `ConfigB` imports `ConfigA`. You must fix the **composition graph** itself.

### 16.5. `@ImportResource` Does Not Make Cycles Disappear Either

If XML bean definitions create bean A depending on B while B depends on A via constructors, importing the XML via `@ImportResource` into a Java context still produces a **bean dependency cycle**. Moving metadata from XML to Java or vice versa does not alter the demand graph between instances.

## 17. Debugging Cycles in Large Applications

When encountering a circular dependency message, follow a finite procedure:

1. **Identify the failure phase:** configuration parsing or bean instantiation?
2. **Record node names:** config class names, bean names, and factory methods listed in the exception.
3. **Map dependency edges:** `@Import`; config constructor; `@Bean` method parameter; service constructor; `@DependsOn`; lookup during init.
4. **Classify the cycle:** import graph, config instance graph, or application bean graph.
5. **Find the structural root cause:** modules knowing each other, unextracted shared responsibility, bean depending on its own factory config, or premature invocation.
6. **Pick the smallest meaningful refactor:** root composition, parameterized `@Bean` methods, extracted interface/coordinator, moving startup work out of config init.
7. **Run a context test:** build `AnnotationConfigApplicationContext` with the real root, rather than relying on unit tests that only call `new`.
8. **Verify identity:** the instance held by a consumer must match the managed singleton if scope requires it.
9. **Test profile variants:** a graph might only cycle under a specific profile.
10. **Consider lazy/provider workarounds only** if the dependency has genuine lazy semantics and risks are understood.

### Do Not Just Delete One Edge to Make Startup Pass

For instance, removing a constructor dependency and switching to `ApplicationContext.getBean` inside an init method may merely postpone the failure. The code becomes harder to test while the logical cycle stays intact.

A proper refactor lets readers look at constructors/factory methods and see **a directed graph that never loops back on itself**, or an explicit abstraction/coordinator explaining why no bidirectional dependency is needed.

## 18. Regression-Prevention Testing

A small integration test can boot the root configuration and retrieve beans:

```java
// Illustrative snippet, not a standalone test file.
try (var context =
        new AnnotationConfigApplicationContext(RootConfig.class)) {
    CatalogRepository repository =
            context.getBean(CatalogRepository.class);
    CatalogService service =
            context.getBean(CatalogService.class);

    if (service.repository() != repository) {
        throw new AssertionError(
                "Service must use the managed repository singleton");
    }
}
```

In the sample project, the classes are nested inside `CycleFreeConfigDemo`, so in a separate test file you must import `demo.CycleFreeConfigDemo.RootConfig` and the relevant nested types.

### Verify Only Expected Modules Were Loaded

In a real application, build the context from **the single root configuration** and check bean name counts for key interfaces. If a config class accidentally pulls in an extra module, the test catches the changed candidate count or broken bean graph.

### Test Different Profiles

If modules use `@Profile("dev")` or `@Profile("prod")`, each profile can yield a different bean set. Write separate context tests for risky configurations to verify full dependencies, zero cycles, and no duplicate application modules.

### Intentionally Reproduce Errors in Tests

Never put circular counterexamples into the production root. You can create dedicated configuration classes inside tests to assert that the context **fails fast** on constructor cycles or circular imports. When asserting errors, avoid coupling too tightly to the entire stack trace string, as wrapper messages may change across Spring versions.

### Verify Init Callbacks

If a config previously had a self-reference in `@PostConstruct`, regression tests should confirm initialization moved to the managed bean or coordinator without forcing premature context bean creation.

### Verify Fail-Fast Behavior on Mandatory Dependencies

A missing repository in a test config should cause service bean creation to fail clearly. Do not turn mandatory dependencies into `Optional`/`ObjectProvider.getIfAvailable()` and silently skip them just to turn a test “green”.

## 19. Frequently Asked Questions

### Must Every Module Have Only One Configuration Class?

No. A module can have several configurations aligned with different responsibilities. What matters is **clear import/ownership direction**, not absolute class count.

### Do Two Mutually Importing Configs Always Create a Bean Constructor Cycle?

No. The import graph governs metadata processing, while the bean dependency graph governs instance creation. A circular import can fail in the configuration parser even when bean constructors do not depend on each other.

### If Root Imports Multiple Configs, Does That Create Multiple BeanFactories?

No. When an `AnnotationConfigApplicationContext` processes `RootConfig` and its `@Import`s, all bean definitions live in **the same container** unless code intentionally creates separate contexts.

### If ServiceConfig Uses a Repository Bean, Must It Import RepositoryConfig Directly?

No, if a root already imports both. A `@Bean service(Repository repository)` parameter lets Spring inject the bean from the same context by type.

### Is Calling Another Bean Method in Full `@Configuration` Wrong?

Not inherently wrong. Full configuration supports inter-bean references through CGLIB enhancement when invoked on the managed config instance. However, **method parameter injection** remains easier to read, less coupled, and safe if you later switch to lite mode.

### Is `@DependsOn` Needed to Force Repo Creation Before Service?

When a service factory method takes a mandatory `Repository`, Spring already knows the dependency and creates/resolves it when needed. Do not add `@DependsOn` just to repeat an existing dependency relationship.

### Does Enabling `allow-circular-references` Fix Constructors A(B), B(A)?

Do not count on it. Constructor cycles require each instance before the other can finish; this is normally unresolvable even though some setter/field cycles can be handled via early references.

### Should You Inject `ApplicationContext` into a Config to Look Up Beans Manually?

Usually no. It hides dependencies in code and makes testing harder. On factory methods, request beans via parameters. If dynamic lookup is genuinely needed, use `ObjectProvider<T>` in the bean owning that runtime responsibility, not in config init.

### What If a Config Is `@Import`ed from Two Branches?

Spring has mechanisms to handle configuration classes and imported definitions, yet you should not rely on duplicate import paths to control ordering or duplicate instances. Test with the real root context and keep ownership clear. A root directly importing the module list is usually easier to audit.

### Why Might a Cycle Appear Only in Production?

Differences in profiles, conditional beans, component scan roots, auto-configuration, config properties, or an implementation with reverse dependencies can form a different dependency graph. Integration tests should cover key configuration variants.

## 20. Exercises with Answers

### Exercise 1 — Identifying an Import Cycle

Two classes:

```java
@Configuration
@Import(BConfig.class)
class AConfig {}

@Configuration
@Import(AConfig.class)
class BConfig {}
```

What kind of cycle is this? How do you fix it so both modules load?

**Answer:** An **import graph** cycle. Remove bidirectional imports, create `RootConfig` with `@Import({AConfig.class, BConfig.class})`, or pick one proper direction if a genuine hierarchy exists. No config instance injection is needed.

### Exercise 2 — Identifying a Config Constructor Cycle

```java
@Configuration
class AConfig {
    AConfig(BConfig b) {}
}

@Configuration
class BConfig {
    BConfig(AConfig a) {}
}
```

Why can't Spring instantiate these two config instances?

**Answer:** Each constructor requires the other class's instance to already exist; BeanFactory has no starting point to complete construction. Refactor so configs do not inject each other, using bean method parameters for business dependencies.

### Exercise 3 — Service Module Using a Repository Bean

You have `RepositoryConfig` creating `AccountRepository` and `ServiceConfig` creating `AccountService`. How do you avoid keeping a `RepositoryConfig` field on `ServiceConfig`?

**Answer:**

```java
@Configuration(proxyBeanMethods = false)
class ServiceConfig {
    @Bean
    AccountService accountService(AccountRepository repository) {
        return new AccountService(repository);
    }
}
```

Root imports both config classes. Spring injects the repository bean via the factory method parameter.

### Exercise 4 — `@PostConstruct` on a Config

A `@Configuration` calls `dataSource()` inside `@PostConstruct`, where `dataSource()` is also a non-static `@Bean` method on itself. Why is that risky?

**Answer:** The config instance is still initializing; the bean produced by its method may require the config instance itself to be finished/constructed, leading to self-reference/early initialization and `BeanCurrentlyInCreationException`. Use bean-local `initMethod`/`@PostConstruct` on the target bean or a startup coordinator instead.

### Exercise 5 — Using `@Lazy` to “Fix a Cycle”

Service A needs B in its constructor, and B needs A in its constructor. Does placing `@Lazy` on injection point B fix the dependency design?

**Answer:** No. It may defer resolution via a proxy in some cases, yet the bidirectional relationship remains and can still fail if dereferenced early. Extracting an abstraction or coordinator is better.

### Exercise 6 — `@DependsOn`

`A` has `@DependsOn("b")` and `B` has `@DependsOn("a")`. What happens to ordering logic?

**Answer:** No initialization order satisfies both constraints. This is an ordering cycle; remove the wrong edge or model the dependency relationship in its real direction.

### Exercise 7 — Lite Config

```java
@Configuration(proxyBeanMethods = false)
class Config {
    @Bean
    Repo repo() { return new Repo(); }

    @Bean
    Service service() { return new Service(repo()); }
}
```

What is the risk and how do you fix it?

**Answer:** Calling `repo()` directly is a Java factory call, which can create a `Repo` outside managed bean identity. Change it to `Service service(Repo repo) { return new Service(repo); }`. This fix preserves DI semantics, though if `Repo` also depends back on `Service` you still must break the real bean cycle.

### Exercise 8 — Reading a Diagram

```text
RootConfig -> InfraConfig
RootConfig -> RepositoryConfig
RootConfig -> ServiceConfig

Bean graph:
Facade -> Service -> Repository
                  -> Clock
```

Is there any cycle?

**Answer:** No, in the described edges. Root imports unidirectionally, and the bean graph never loops back to an earlier node.

### Exercise 9 — Spring Boot

A Spring Boot application sets `spring.main.allow-circular-references=true` to silence an error between two mutually constructor-injecting services. Should this be treated as a durable fix?

**Answer:** No. Some constructor cycles remain unresolvable; the flag only affects how certain circular bean references are handled and does not fix import graphs or architecture. Dependencies must be refactored.

### Exercise 10 — Proper Design for Import Composition

A system has `DbConfig`, `MessagingConfig`, and `OrdersConfig`; `OrdersService` needs `DataSource` and `MessagePublisher`. Propose a clean structure.

**Guided answer:**

```java
@Configuration(proxyBeanMethods = false)
@Import({
    DbConfig.class,
    MessagingConfig.class,
    OrdersConfig.class
})
class RootConfig {
}

@Configuration(proxyBeanMethods = false)
class OrdersConfig {
    @Bean
    OrdersService ordersService(
            DataSource dataSource,
            MessagePublisher publisher) {
        return new OrdersService(dataSource, publisher);
    }
}
```

This pattern requires the types to be defined separately. `OrdersConfig` does not back-import Db/Messaging configs just to obtain instances. Dependencies are resolved from the shared BeanFactory via parameters. If `DbConfig` or `MessagingConfig` depends back on `OrdersService`, that signals a need to adjust responsibilities/abstractions.

### Exercise 11 — Bean Creation Order

If `@Bean Service service(Repository repo)` is called by Spring, do you need `@DependsOn("repo")` so the repo exists first?

**Answer:** No, when `Repository` is injected as a mandatory parameter; BeanFactory resolves the repository before it can invoke the factory method creating `Service`.

### Exercise 12 — Testing the Graph

You are tasked with refactoring three configs to remove a cycle. What minimum checks should tests cover?

**Answer:** Build the context from the new root; retrieve the core bean types; assert dependency identity for singletons; check total bean name counts and service behavior; test relevant profile/conditional variants; and confirm neither `allow-circular-references` nor providers are needed to mask missing dependencies.

## 21. Review Checklist Before Composing Configurations

- [ ] There is one or a few clear **entry-point/root configs**, with no accidental reverse imports.
- [ ] Each module config primarily declares bean definitions belonging to its own responsibility.
- [ ] `RepositoryConfig` is not injected into `ServiceConfig` just to call `@Bean` methods.
- [ ] When a service bean needs a repository, constructor or **factory-method parameter injection** is used.
- [ ] No bean is injected into a config's constructor if that same config must produce that bean.
- [ ] Locally defined beans are never called from `@PostConstruct` on the config class.
- [ ] Early-created `BeanFactoryPostProcessor`/`BeanPostProcessor` beans consider `static @Bean` where appropriate.
- [ ] Full/lite configuration semantics are understood; no direct `@Bean` calls in lite mode expecting managed objects.
- [ ] `@DependsOn` is not used to mask real dependency cycles.
- [ ] `@Lazy`/`ObjectProvider` appear only for genuine lazy/dynamic lookup needs, not to hide architectural issues.
- [ ] `spring.main.allow-circular-references` is not relied upon as a default fix.
- [ ] Context startup tests verify no `BeanCurrentlyInCreationException` occurs.
- [ ] Dependency graphs across important profile/conditional configs have been verified.
- [ ] No secondary ApplicationContexts or `new` configuration instances are created inside `@Bean`.
- [ ] Every resource has a clear lifecycle and is not initialized twice via direct method calls.
- [ ] Bean definitions do not collide in name/type due to unintended imports or scans.
- [ ] Integration tests verify bean identity and main use-case paths after refactoring.

## Conclusion

**Avoiding circular dependencies between configuration classes** does not mean stuffing every configuration into one class. What is needed is **separating configuration composition structure from bean dependency structure**:

- `@Import` enables **root composition** to bring multiple configurations into the same context in one clear direction.
- `@Bean` method parameters allow beans in one module to receive beans from another module **without configuration classes injecting each other**.
- Constructors/`@PostConstruct` on `@Configuration` must avoid premature references to beans produced by that same config instance.
- Constructor cycles between application beans must be fixed at **the service/abstraction/coordinator design level**, not merely by moving config files.
- `@Lazy`, `ObjectProvider`, `@DependsOn`, and circular-reference flags have narrow roles; they do not substitute for a sound dependency graph.

**Pattern worth remembering:** the root imports the modules; each module declares factory methods; dependencies between beans are resolved by Spring through parameters; no module config ever calls back into another config instance just to fetch an object.

## Official References

- [Spring Framework 6.2 — Composing Java-based Configurations](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/composing-configuration-classes.html): `@Import`, dependencies between imported configurations, early config initialization warnings, and `@PostConstruct`.
- [Spring Framework 6.2 — Dependency Injection and Circular Dependencies](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-collaborators.html): constructor cycles, bean creation, and meaning of early references.
- [Spring Framework 6.2 — Basic Concepts: @Bean and @Configuration](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/basic-concepts.html): full/lite configuration modes.
- [Spring Framework 6.2 — Using the @Configuration Annotation](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/configuration-annotation.html): inter-bean method references and CGLIB enhancement.
- [Spring Framework 6.2 — Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/bean-annotation.html): factory method parameters, type metadata, and lifecycle.
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/): `spring.main.allow-circular-references` belongs to Boot, not Spring Core configuration annotations.
