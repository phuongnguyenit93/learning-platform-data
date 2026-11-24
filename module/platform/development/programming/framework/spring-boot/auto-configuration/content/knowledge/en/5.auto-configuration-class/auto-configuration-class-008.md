# Designing Public @Bean Methods with Informative Return Types in Spring Boot

> **Topic:** Spring Boot — auto-configuration -> auto-configuration class. Focuses on designing `@Bean` methods whose declarations are **readable, usable from other libraries, and provide sufficiently specific return types** so Spring can determine bean definitions, inject dependencies, and evaluate `@ConditionalOnBean` / `@ConditionalOnMissingBean` before instances are created. Examples use Java 17, Maven, and Spring Boot 3.5.7.

## 1. Why Can Changing Only a `@Bean`'s Return Type Change Application Behavior?

Compare two ways of declaring a bean whose actual runtime instance is identical:

```java
@Bean
public Store store() {
    return new InMemoryStore();
}
```

```java
@Bean
public InMemoryStore store() {
    return new InMemoryStore();
}
```

The two snippets above are only **fragments**; definitions of `Store`, `InMemoryStore`, and a configuration class are required. When the bean is actually created, both return an `InMemoryStore` object. However, **at the moment Spring parses the bean definition prior to instantiating the instance**, the factory method's type metadata differs:

- In the first example, Spring has reliable signature information that the bean is a `Store`.
- In the second example, Spring knows the bean is an `InMemoryStore` and, via the Java type hierarchy, also knows it is assignable to `Store`.
- A `@ConditionalOnBean(InMemoryStore.class)` condition needs to recognize the concrete implementation type. With a signature declaring only `Store`, that information **may not yet be available when the condition is evaluated**.
- Once the instance is created, calling `bean.getClass()` can return `InMemoryStore.class` in both cases. Runtime observation **does not prove** that a condition at the bean-definition stage saw the same information.

Spring Boot documentation recommends: **declare as much useful type information as possible in the return type of `@Bean` methods**. When an implementation implements an interface, in many cases returning the concrete implementation type rather than solely the interface is better, because bean conditions rely on metadata from the method signature. This is especially important in auto-configuration.

**Note:** You are not always forced to expose the implementation type. Keeping an interface type in a public API has architectural benefits when intentionally hiding the implementation. In that case, design bean conditions, extension points, and dependency injection **to match the published abstraction**; do not simultaneously expect another condition to detect an undeclared concrete type.

## 2. Three Conceptual Layers to Distinguish

| Concept | Example | What it describes |
| --- | --- | --- |
| **Method's declared type** | `public InMemoryStore inMemoryStore()` | The type Spring can infer from the bean factory method's signature. |
| **Instance's runtime type** | `new InMemoryStore()` | The actual class of the object after the method executes. |
| **Contract type searched by conditions** | `@ConditionalOnMissingBean(Store.class)` | The bean type auto-configuration uses to decide whether to create a default or back off. |

The three types can coincide, though they do not have to. Good design usually answers two questions separately:

1. **What is this bean really?** If it is `InMemoryStore` and you want other auto-configurations to recognize that characteristic, return `InMemoryStore`.
2. **Which bean type must the default back off for?** If any user-provided `Store` is a valid replacement, write `@ConditionalOnMissingBean(Store.class)` rather than relying on the concrete return type.

Combining both decisions:

```java
@Bean
@ConditionalOnMissingBean(Store.class)
public InMemoryStore inMemoryStore() {
    return new InMemoryStore();
}
```

**Explanation:** The method declares `InMemoryStore` to preserve specific metadata. The condition intentionally looks for `Store` (the interface), because it expresses a broader back-off rule. That design usually suits starters/auto-configurations.

## 3. Why Is Type Metadata Needed **Before** Creating Instances?

During ApplicationContext startup, Spring builds a list of **bean definitions**. For `@Bean` methods, Spring inspects the configuration class and method signatures to determine which beans can be created. Actual singleton instantiation normally happens after registration and evaluation of various conditions.

You can visualize it as:

```text
Read @AutoConfiguration / @Configuration
              |
              v
Discover @Bean factory method
              |
              v
Record metadata from return type signature
              |
              +----> @ConditionalOnBean(X) or @ConditionalOnMissingBean(X)
              |      uses the type known when the condition runs
              v
Register bean definition if eligible
              |
              v
Create instance when Spring needs to instantiate the bean
              |
              v
getClass() reveals the actual class of the instance
```

Spring should not have to invoke every `@Bean` method just to discover implementation classes, because doing so could:

- Open network connections, databases, or thread pools too early.
- Trigger side effects before properties and `BeanPostProcessor`s finish.
- Corrupt dependency order or cause cycles when a condition needs to know bean types before creating beans.
- Increase startup time and turn configuration selection into a side-effecting process.

Information from the **method signature** therefore has distinct value. Spring may gather additional metadata from multiple sources depending on bean type, proxies, factory methods, and phases, yet **you should not rely on runtime implementation guessing** to make auto-configuration conditions work.

### Two Contrasting Scenarios

**Case A:**

```java
@Bean
public Object paymentClient() {
    return new PaymentClient();
}
```

At parse time, a method returning `Object` does not convey that it actually supplies `PaymentClient`. A consumer using `@ConditionalOnBean(PaymentClient.class)` may not see this bean during registration.

**Case B:**

```java
@Bean
public PaymentClient paymentClient() {
    return new PaymentClient();
}
```

The specific signature lets Spring recognize `PaymentClient` without instantiating it first. These are **two illustrative fragments**, omitting the `PaymentClient` definition and imports.

## 4. "Public" Here Has Two Different Meanings

### 4.1. `public` in Java

```java
@Bean
public InMemoryStore inMemoryStore() {
    return new InMemoryStore();
}
```

The `public` keyword makes the method callable under Java visibility rules whenever its enclosing class is accessible. For library configurations, `public` often improves clarity, supports tooling or intentional extension, and aligns with official Spring examples.

**However, `public` is not mandatory for every `@Bean` method.** Spring Framework can process package-private methods in many appropriate configurations. Do not conclude that changing a method from package-private to `public` will by itself fix `@ConditionalOnBean`: the metadata issue here lies in the **return type**, not visibility.

When designing an auto-configuration exposing public extension points, pick visibility consistent with your Java/module contract and team conventions. Avoid `private` on methods Spring must process in full `@Configuration` mode, and avoid letting the API accidentally depend on inaccessible implementations. With `@AutoConfiguration`, `proxyBeanMethods=false` is already fixed, so proxy interception semantics also differ from full mode.

### 4.2. "Sufficiently Informative" in Java Type Metadata

That means the type signature conveys what downstream dependencies truly need:

- Specific type (`PaymentClient`) rather than overly broad (`Object`).
- Clear hierarchy (`InMemoryStore implements Store`).
- For generic types, retain useful type arguments, such as `MessageHandler<Order>` rather than raw `MessageHandler` when the framework needs to distinguish them.
- For wrappers/factories/proxies, understand where Spring derives type metadata; if the actual object is built through a complex factory, type matching outcomes should be tested.
- The specific type must be **accessible** to consuming code if you want consumer libraries to reference it directly. You can keep implementations closed, but do not write external conditions based on that hidden implementation.

In short: `public` visibility and return-type specificity are **two distinct design dimensions**, even though they often appear side by side in `@Bean` examples.

## 5. Design Rules with @ConditionalOnMissingBean

The `@ConditionalOnMissingBean` annotation has two common usage styles.

### 5.1. Omitting the Type: Defaulting from the Return Type

```java
@Bean
@ConditionalOnMissingBean
public InMemoryStore inMemoryStore() {
    return new InMemoryStore();
}
```

When `@ConditionalOnMissingBean` sits on a `@Bean` method and you do not specify `value`/`type`/`name`, the check target defaults to the method's **declared return type**.

Here the target is effectively `InMemoryStore`. That **does not express** "any user-supplied implementation of `Store` makes me back off". If the user creates `RemoteStore implements Store`, both `RemoteStore` and `InMemoryStore` may end up registered.

### 5.2. Explicitly Specifying the Abstraction Type: Contract-Based Back-off

```java
@Bean
@ConditionalOnMissingBean(Store.class)
public InMemoryStore inMemoryStore() {
    return new InMemoryStore();
}
```

In this version:

- The method still advertises the specific type `InMemoryStore` to Spring and other auto-configurations.
- The condition treats any bean assignable to `Store` as a replacement candidate.
- A user's `RemoteStore`, `InMemoryStore`, or any matching `Store` implementation prevents the default bean from registering.

If the contract is genuinely **by bean name** (e.g., standardizing a bean name so extensions look it up by name), you can use `@ConditionalOnMissingBean(name="storeClient")`. If the contract is by type, prefer specifying the type explicitly. Name-conditions and type-conditions are not always equivalent, especially when an application has multiple beans sharing an interface.

### 5.3. Be Careful with Bean Names and @Primary

`@Primary` only sets preference during autowiring when multiple matching beans exist; it **does not automatically cause** a default bean guarded by `@ConditionalOnMissingBean(InMemoryStore.class)` to back off when the user only supplies a `RemoteStore` bean.

If two beans share the same name, Spring Boot by default can fail because overriding is disabled. If two beans share an interface, autowiring by interface without a qualifier/primary can fail due to multiple candidates. Designing the condition right from the start is better than using `@Primary` to mask the issue.

## 6. Runnable Example: Public @Bean with Specific Return Type and Clear Back-off Contract

We create a small application with two auto-configurations:

- `StoreAutoConfiguration` supplies `InMemoryStore` when no user `Store` bean exists.
- `StoreDiagnosticsAutoConfiguration` creates `StoreDiagnostics` only when an `InMemoryStore` bean is known to exist.

The `InMemoryStore` class belongs to `dev.example.impl`; the application class resides in `dev.example.app`. Both auto-configurations belong to `dev.example.autoconfigure` **outside default component scan**, and are loaded via `AutoConfiguration.imports`.

### 6.1. Directory Structure

```text
bean-type-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/dev/example/
    │   │   ├── api/Store.java
    │   │   ├── impl/InMemoryStore.java
    │   │   ├── monitoring/StoreDiagnostics.java
    │   │   ├── autoconfigure/StoreAutoConfiguration.java
    │   │   ├── autoconfigure/StoreDiagnosticsAutoConfiguration.java
    │   │   └── app/
    │   │       ├── DemoApplication.java
    │   │       ├── CustomStore.java
    │   │       └── UserStoreConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/java/dev/example/testing/
        ├── StoreAutoConfigurationTest.java
        └── ApplicationWiringTest.java
```

**Note:** This layout is a single artifact for learning. In a real library, you normally package the `autoconfigure`, `api`, `impl` packages and imports resource into a separate library JAR, then let applications consume them via dependency.

### 6.2. Maven POM

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>dev.example</groupId>
    <artifactId>bean-type-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

No HTTP server, database, or starter beyond basic Spring Boot is needed.

### 6.3. Store Interface

`src/main/java/dev/example/api/Store.java`:

```java
package dev.example.api;

public interface Store {
    String read(String key);
}
```

### 6.4. Default Implementation

`src/main/java/dev/example/impl/InMemoryStore.java`:

```java
package dev.example.impl;

import dev.example.api.Store;

public final class InMemoryStore implements Store {
    @Override
    public String read(String key) {
        return "memory:" + key;
    }
}
```

This implementation is a `public` class, usable in `@Bean` signatures and conditions in other modules. It has no `@Component` because the bean will be created **via a `@Bean` method**, not via scanning.

### 6.5. Diagnostics Bean Depending on a Concrete Implementation

`src/main/java/dev/example/monitoring/StoreDiagnostics.java`:

```java
package dev.example.monitoring;

import dev.example.impl.InMemoryStore;

public final class StoreDiagnostics {
    private final InMemoryStore store;

    public StoreDiagnostics(InMemoryStore store) {
        this.store = store;
    }

    public String kind() {
        return store.getClass().getSimpleName();
    }
}
```

This is an optional component: diagnostics applies only to `InMemoryStore`; if the user replaces it with `CustomStore`, we intentionally do not create the `StoreDiagnostics` bean.

### 6.6. Auto-Configuration Creating the Default Bean

`src/main/java/dev/example/autoconfigure/StoreAutoConfiguration.java`:

```java
package dev.example.autoconfigure;

import dev.example.api.Store;
import dev.example.impl.InMemoryStore;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class StoreAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(Store.class)
    public InMemoryStore inMemoryStore() {
        return new InMemoryStore();
    }
}
```

**Two core lines:**

- `public InMemoryStore inMemoryStore()` provides the **implementation type** information right in the signature.
- `@ConditionalOnMissingBean(Store.class)` defines the **back-off policy**: any valid user bean of type `Store` makes the default configuration back off.

When Boot loads standard auto-configuration after user definitions, the condition inspects registered bean definitions. This layout clarifies intent instead of gambling on ordering or whether Spring has already instantiated objects.

### 6.7. Another Auto-Configuration Depending on the Concrete Bean

`src/main/java/dev/example/autoconfigure/StoreDiagnosticsAutoConfiguration.java`:

```java
package dev.example.autoconfigure;

import dev.example.impl.InMemoryStore;
import dev.example.monitoring.StoreDiagnostics;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(after = StoreAutoConfiguration.class)
@ConditionalOnBean(InMemoryStore.class)
public class StoreDiagnosticsAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(StoreDiagnostics.class)
    public StoreDiagnostics storeDiagnostics(InMemoryStore store) {
        return new StoreDiagnostics(store);
    }
}
```

Explanation:

1. `after = StoreAutoConfiguration.class` instructs Spring Boot to process this auto-configuration after the default provider, because conditional bean selection needs metadata from that source.
2. `@ConditionalOnBean(InMemoryStore.class)` does not need `InMemoryStore` instantiated beforehand; it relies on existing bean definitions and resolvable type metadata.
3. `@Bean public StoreDiagnostics storeDiagnostics(InMemoryStore store)` both advertises a specific type and uses method-parameter injection. Avoid calling `inMemoryStore()` directly because auto-configuration has `proxyBeanMethods=false`.
4. `@ConditionalOnMissingBean(StoreDiagnostics.class)` gives users the option to supply their own diagnostics bean if appropriate.

**Do not replace the method return type with an interface and then expect the second condition to always recognize the runtime implementation.**

### 6.8. Declaring the Imports File

Create resource `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`:

```text
dev.example.autoconfigure.StoreAutoConfiguration
dev.example.autoconfigure.StoreDiagnosticsAutoConfiguration
```

Spring Boot picks up both classes even though they sit outside the application's root package. Keep auto-configuration in a separate package, without adding that package to component scan.

### 6.9. User Supplying a Custom Store

`src/main/java/dev/example/app/CustomStore.java`:

```java
package dev.example.app;

import dev.example.api.Store;

public final class CustomStore implements Store {
    @Override
    public String read(String key) {
        return "custom:" + key;
    }
}
```

`src/main/java/dev/example/app/UserStoreConfiguration.java`:

```java
package dev.example.app;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("custom")
public class UserStoreConfiguration {

    @Bean
    public CustomStore customStore() {
        return new CustomStore();
    }
}
```

`UserStoreConfiguration` sits under the application root `dev.example.app`, so component scan inspects it. Only when the `custom` profile is enabled does the `CustomStore` bean appear and cause the auto-configuration's `@ConditionalOnMissingBean(Store.class)` **not to match**.

Note: The user method also declares the concrete type `CustomStore`, so Spring knows this bean is a `Store` via `implements Store`. Even without `@Primary`, the context has only one `Store` bean in each scenario.

### 6.10. Application Displaying the Results

`src/main/java/dev/example/app/DemoApplication.java`:

```java
package dev.example.app;

import dev.example.api.Store;
import dev.example.monitoring.StoreDiagnostics;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                 SpringApplication.run(DemoApplication.class, args)) {

            Store store = context.getBean(Store.class);
            StoreDiagnostics diagnostics =
                context.getBeanProvider(StoreDiagnostics.class).getIfAvailable();

            System.out.println(
                "store.class=" + store.getClass().getSimpleName()
            );
            System.out.println("store.read=" + store.read("sample"));
            System.out.println("diagnostics.present=" + (diagnostics != null));
            System.out.println(
                "diagnostics.kind=" +
                (diagnostics == null ? "none" : diagnostics.kind())
            );
        }
    }
}
```

Run from the directory containing `pom.xml`:

```bash
mvn -q spring-boot:run
```

Four lines printed by the application code (ignoring Spring Boot logs):

```text
store.class=InMemoryStore
store.read=memory:sample
diagnostics.present=true
diagnostics.kind=InMemoryStore
```

Spring Boot loads `StoreAutoConfiguration` via imports and registers `InMemoryStore`. Next, diagnostics' condition sees a bean of type `InMemoryStore` and creates `StoreDiagnostics`.

Enable user configuration:

```bash
mvn -q spring-boot:run -Dspring-boot.run.arguments=--spring.profiles.active=custom
```

Four lines printed by the application code:

```text
store.class=CustomStore
store.read=custom:sample
diagnostics.present=false
diagnostics.kind=none
```

In the custom branch, the `CustomStore` bean is a `Store`, so `StoreAutoConfiguration` backs off, and at the same time there is no `InMemoryStore` to trigger diagnostics. This is intentional back-off, not a missing component scan bug.

## 7. Testing: Concrete Metadata, Interface-Based Back-off, and Overly Broad Return Types

The tests below use `ApplicationContextRunner` to create lightweight contexts without starting a web application. They are placed in package `dev.example.testing`, **outside the `dev.example.app` scan scope**, so test-only configuration classes are not accidentally scanned by the Spring Boot application.

### 7.1. Testing the Main Branches

File `src/test/java/dev/example/testing/StoreAutoConfigurationTest.java`:

```java
package dev.example.testing;

import dev.example.api.Store;
import dev.example.app.CustomStore;
import dev.example.autoconfigure.StoreAutoConfiguration;
import dev.example.autoconfigure.StoreDiagnosticsAutoConfiguration;
import dev.example.impl.InMemoryStore;
import dev.example.monitoring.StoreDiagnostics;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class StoreAutoConfigurationTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner().withConfiguration(
            AutoConfigurations.of(
                StoreAutoConfiguration.class,
                StoreDiagnosticsAutoConfiguration.class
            )
        );

    @Test
    void defaultStoreExposesConcreteMetadata() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(Store.class);
            assertThat(context).hasSingleBean(InMemoryStore.class);
            assertThat(context).hasSingleBean(StoreDiagnostics.class);
            assertThat(context.getBean(Store.class).read("sample"))
                .isEqualTo("memory:sample");
            assertThat(context.getBean(StoreDiagnostics.class).kind())
                .isEqualTo("InMemoryStore");
        });
    }

    @Test
    void anyUserStoreCanMakeDefaultBackOff() {
        runner.withUserConfiguration(UserStoreForTest.class)
            .run(context -> {
                assertThat(context).hasSingleBean(Store.class);
                assertThat(context).hasSingleBean(CustomStore.class);
                assertThat(context).doesNotHaveBean(InMemoryStore.class);
                assertThat(context).doesNotHaveBean(StoreDiagnostics.class);
                assertThat(context.getBean(Store.class).read("sample"))
                    .isEqualTo("custom:sample");
            });
    }

    @Test
    void broadDeclaredReturnTypeCanHideConcreteTypeFromCondition() {
        new ApplicationContextRunner()
            .withUserConfiguration(BroadReturnTypeConfiguration.class)
            .withConfiguration(
                AutoConfigurations.of(StoreDiagnosticsAutoConfiguration.class)
            )
            .run(context -> {
                assertThat(context).hasSingleBean(Store.class);
                assertThat(context.getBean(Store.class))
                    .isInstanceOf(InMemoryStore.class);
                assertThat(context).doesNotHaveBean(StoreDiagnostics.class);
            });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserStoreForTest {
        @Bean
        public CustomStore customStore() {
            return new CustomStore();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class BroadReturnTypeConfiguration {
        @Bean
        public Store broadStore() {
            return new InMemoryStore();
        }
    }
}
```

**Why is the third test important?**

- `BroadReturnTypeConfiguration.broadStore()` truly creates an `InMemoryStore` instance.
- Yet its signature declares `Store`; when `@ConditionalOnBean(InMemoryStore.class)` is evaluated on `StoreDiagnosticsAutoConfiguration`, the bean definition from that method does not promise that concrete type.
- Thus diagnostics is not registered in this test context, even though Spring later instantiates the bean and we confirm the instance is `InMemoryStore`.
- This test intentionally **does not** load `StoreAutoConfiguration` to prevent another concrete bean source from muddying the result. It isolates the difference between declared type and runtime type.

### 7.2. Integration Test Verifying the Imports File

File `src/test/java/dev/example/testing/ApplicationWiringTest.java`:

```java
package dev.example.testing;

import dev.example.api.Store;
import dev.example.app.DemoApplication;
import dev.example.impl.InMemoryStore;
import dev.example.monitoring.StoreDiagnostics;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(classes = DemoApplication.class)
class ApplicationWiringTest {

    @Autowired
    ApplicationContext context;

    @Test
    void discoversAutoConfigurationOutsideComponentScan() {
        assertThat(context.getBean(Store.class))
            .isInstanceOf(InMemoryStore.class);
        assertThat(context.containsBean("inMemoryStore")).isTrue();
        assertThat(context.getBean(StoreDiagnostics.class).kind())
            .isEqualTo("InMemoryStore");
    }
}
```

Run from the project directory:

```bash
mvn -q test
```

Expect **4 tests pass** (3 tests in `StoreAutoConfigurationTest` and 1 integration test). The integration test assumes the `custom` profile is **not activated** by the CI environment; if CI applies that profile, explicitly set the desired profile for the test before evaluating results.

The two testing approaches do not replace each other:

- `ApplicationContextRunner` tests conditions and bean definitions of the auto-configurations we select, **without checking that the imports file was packaged**.
- `@SpringBootTest` checks the entire application bootstrapping flow, helping catch misspelled class names or missing imports resources on the classpath.

## 8. How to Actively Verify Return Types

Do not just call `context.getBean(...).getClass()` and assume bean conditions will certainly recognize that type. Instead, tests should verify **conditions that actually consume metadata**.

### 8.1. Distinguishing Runtime from Registration-Time

Suppose:

```java
@Bean
public Store store() {
    return new InMemoryStore();
}
```

After initialization:

```java
Store store = context.getBean(Store.class);
System.out.println(store.getClass().getSimpleName());
```

May print:

```text
InMemoryStore
```

Yet that is a **runtime observation**. A condition on `InMemoryStore.class` evaluated before instantiation might not match. That is why the third test in section 7 directly observes the conditional registration outcome.

### 8.2. Using the Condition Evaluation Report

Run:

```bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
```

Spring Boot's condition report can reveal why an auto-configuration or `@Bean` method did not match a condition. When your bean appears at runtime yet `@ConditionalOnBean(ConcreteType.class)` fails to match, inspect the **declared return type**, not only the actual class.

With Actuator, the `conditions` endpoint can also provide this information if the dependency is added, the endpoint is properly exposed, and access is appropriately secured.

### 8.3. Checking Actual Bean Definitions

When deep debugging is needed, you can inspect `BeanDefinition`, `factoryMethodName`, `resolvableType`, or metadata from Spring configuration; however, not every bean definition carries identical metadata (for instance beans produced by `FactoryBean`, proxies, or complex factory methods). Verify **the type the condition actually requires**, rather than relying on a single inspection method.

## 9. Notes on Generic Types, Proxies, and Abstraction

### 9.1. Generic Types

Example in an event-processing system:

```java
@Bean
public MessageHandler<OrderEvent> orderHandler() {
    return new OrderHandler();
}
```

This is a **fragment** requiring declarations for `MessageHandler`, `OrderEvent`, and `OrderHandler`. The signature retains the `OrderEvent` type argument, unlike the raw type:

```java
@Bean
@SuppressWarnings("rawtypes")
public MessageHandler rawHandler() {
    return new OrderHandler();
}
```

Spring Framework can use generic type information to resolve dependencies in many contexts; keeping generic signatures explicit helps the framework and tooling avoid guessing. However, how `@ConditionalOnBean` specifically matches generics or proxies depends on the actual API and metadata; **test your specific case** rather than assuming every `ResolvableType` is handled identically across all conditions.

### 9.2. Proxies/AOP

When a bean has an AOP proxy applied, `bean.getClass()` may be a proxy class (JDK dynamic proxy or CGLIB). The observed runtime type is not necessarily the original implementation class. Do not rely on `getClass().getSimpleName()` in business logic to identify beans; the example in section 6 uses it only for illustration without AOP.

If a bean must be accessed through an interface at runtime (such as a JDK proxy), the public API can publish the interface and conditions must be designed accordingly. The "as specific as possible" rule is **guidance for metadata**, not a mandate to expose every internal implementation regardless of encapsulation and proxy semantics.

### 9.3. Optional Dependencies

If a `@Bean` method returns a type from an SDK that **may not exist** on the classpath, placing `@ConditionalOnClass` solely on the method may not be safe enough: the JVM may need to resolve the method signature before the condition runs.

A robust approach is to place the method inside a **nested configuration class** annotated with `@ConditionalOnClass` at the class level:

```java
@AutoConfiguration
class OptionalSdkAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.sdk.OptionalClient")
    static class OptionalClientConfiguration {

        @Bean
        OptionalClient optionalClient() {
            return new OptionalClient();
        }
    }
}
```

**This snippet only illustrates design, not standalone runnable code:** imports, the `OptionalClient` SDK class, and the corresponding imports resource are needed. In a real library JAR, the bytecode referencing the SDK is packaged, yet applications can run when the SDK is absent thanks to the condition on the nested configuration class. The nested condition protects class loading while the `@Bean` return type remains specific in the branch where the SDK exists.

## 10. @AutoConfiguration, Ordering, and Metadata-Driven Design

Auto-configuration is normally processed by Spring Boot **after user configuration definitions**, enabling `@ConditionalOnMissingBean(Store.class)` to back off. Within a group of multiple auto-configurations, ordering may need to be specified:

```java
@AutoConfiguration(after = StoreAutoConfiguration.class)
class StoreDiagnosticsAutoConfiguration {
    // ...
}
```

This is an ordering **fragment**, not a standalone class. It controls **auto-configuration processing order**, not guaranteeing that instances of all beans from the earlier configuration are instantiated first.

Why does this relate to return types?

1. `StoreAutoConfiguration` registers the default bean definition from `public InMemoryStore inMemoryStore()`.
2. `StoreDiagnosticsAutoConfiguration` is processed afterwards and requires `@ConditionalOnBean(InMemoryStore.class)`.
3. The specific return type lets the second condition recognize the bean via metadata, **even before `InMemoryStore` is instantiated**.
4. If only `Store` were declared, the bean might still be `InMemoryStore` at runtime yet the condition would not necessarily recognize it.
5. If the source bean has not been processed beforehand, even a concrete signature may not make the condition match: **sufficiently specific return types and proper processing order are two independent requirements**.

Avoid calling `@Bean` methods from each other to "force Spring to create them first":

```java
@Bean
public StoreDiagnostics storeDiagnostics() {
    return new StoreDiagnostics(inMemoryStore());
}
```

The snippet above is a **pattern to avoid** when `@AutoConfiguration` uses `proxyBeanMethods=false`; the direct `inMemoryStore()` call is a plain Java call and can create an instance outside the container's managed lifecycle. The right pattern is receiving dependencies via parameters:

```java
@Bean
public StoreDiagnostics storeDiagnostics(InMemoryStore store) {
    return new StoreDiagnostics(store);
}
```

## 11. Intentional Design Choices

### Option A: Expose Concrete Implementation

```java
@Bean
public RedisBackedStore redisBackedStore() {
    return new RedisBackedStore();
}
```

**Fits when:** downstream auto-configurations/conditions genuinely need to know the implementation, or supporting beans work only with this class. Requires the implementation type to be part of the public API; refactoring the implementation can impact consumers.

### Option B: Expose Interface

```java
@Bean
public Store store() {
    return new RedisBackedStore();
}
```

**Fits when:** intentionally hiding the implementation, supporting diverse implementations, or limiting coupling. Conditions in other components should then rely on `Store.class` or a public marker contract, **not on Spring guessing `RedisBackedStore.class`**.

### Option C: Expose Concrete Type Yet Back Off by Interface

```java
@Bean
@ConditionalOnMissingBean(Store.class)
public RedisBackedStore redisBackedStore() {
    return new RedisBackedStore();
}
```

**Fits when:** you want a specific default, want to support implementation-specific downstream features, and still allow users to substitute any `Store`. This is the form shown in the runnable example in section 6.

All three snippets are fragments; `RedisBackedStore` is not defined in the demo project.

### Option D: Multiple Beans of the Same Interface by Intentional Design

If an application needs multiple distinct `Store` beans (primary/secondary, read/write, multi-tenancy), `@ConditionalOnMissingBean(Store.class)` can be too broad: any single `Store` bean disables the default. In that case, design explicitly by bean name, qualifier, or specific marker annotations; do not try to work around it by declaring a return type of `Object`.

Spring Boot provides parameters such as `name`, `annotation`, and `search` for conditions suited to each context. Choose conditions that reflect the **functional contract**, while return types reflect the **produced bean type**.

## 12. Common Mistakes and Fixes

| Mistake | Symptom | Fix |
| --- | --- | --- |
| Declaring `@Bean public Object service()` | Conditions or injection by `ServiceImpl` miss the desired type | Return `ServiceImpl` if that type is part of the contract to advertise. |
| Declaring `@Bean public Service service()` even though downstream needs `ServiceImpl` | Bean has the right instance after startup, yet `@ConditionalOnBean(ServiceImpl.class)` fails to match | Expose the specific type or switch the condition to the interface/contract. |
| Using bare `@ConditionalOnMissingBean` on a method returning a concrete type | User bean implementing the interface with a different concrete class fails to make the default back off | Write `@ConditionalOnMissingBean(Service.class)` if any implementation should replace the default. |
| Using `@ConditionalOnMissingBean(Service.class)` when multiple Services should coexist | Even one user `Service` bean makes the default disappear | Consider conditioning by bean name, marker annotation, or distinguishing roles. |
| Inspecting only `getBean(...).getClass()` | Runtime class is right yet the condition fails to match | Test condition/bean-definition outcomes; check the `@Bean` signature. |
| Creating dependencies by calling methods directly inside auto-configuration | May create extra instances because `proxyBeanMethods=false` | Inject dependencies as `@Bean` method parameters. |
| Method returns an optional SDK type when the SDK is absent | May fail class loading before method conditions get a chance to run | Guard with `@ConditionalOnClass` on a nested configuration class. |
| Confusing `public` with Spring needing to see concrete types | Changing visibility leaves the condition failure intact | Check the declared return type and condition target. |
| Forgetting ordering between auto-configurations | Condition using a bean from another config evaluates too early | Use `@AutoConfiguration(after=...)` when a dependency relationship exists. |
| Mixing auto-configuration packages into the application's component scan | Configuration may be loaded outside the intended flow/conditions | Register via `AutoConfiguration.imports` and keep packages separate. |
| Making the implementation type inaccessible while expecting public consumers to reference it | Other modules fail to compile signatures/conditions | Consider a public contract or intentionally public implementation. |

## 13. Checklist When Reviewing a Starter's `@Bean` Method

1. **Bean name:** Is this bean identified primarily by name or by type? If multiple beans of the same type exist, do name and qualifier matter?
2. **Return type:** Is it returning `Object`, a raw type, an interface, or a concrete class? Which type do metadata readers need to resolve?
3. **Visibility:** Are the method and return type consistently accessible with the intended public API? Is `public` genuinely required by the library design?
4. **Back-off:** Does `@ConditionalOnMissingBean` explicitly state the contract users can replace?
5. **Downstream conditions:** Can `@ConditionalOnBean(ConcreteType.class)` see the type from the provider bean's signature without instantiating it?
6. **Ordering:** If the provider and consumer beans live in different auto-configurations, are appropriate `before/after` constraints set?
7. **Optional classpath:** Does the signature mention optional SDK classes; is a nested configuration with a class condition needed?
8. **Proxies:** Is the declared type compatible with actual proxy mechanisms and the abstraction other components should depend on?
9. **Generics:** Are important generic type arguments preserved in the signature?
10. **Testing:** Are there tests proving defaults, user overrides, concrete-type conditions, and overly broad return-type scenarios?
11. **Packaging:** Is the auto-configuration listed in the imports file without depending on the app's component scan?
12. **Observability:** When a condition fails, have you checked the Condition Evaluation Report and bean definitions instead of only checking instances after startup?

## 14. Self-Check Questions

1. Does `@Bean public Object storage() { return new DiskStorage(); }` guarantee `@ConditionalOnBean(DiskStorage.class)` matches before bean creation? **No**; the declared type only promises `Object`.
2. Why is `@Bean public InMemoryStore inMemoryStore()` helpful? **Because Spring knows the concrete type from the signature**, letting type-based conditions recognize it while processing definitions.
3. Should you write `@ConditionalOnMissingBean` with no arguments on a method returning `InMemoryStore` if users can replace it with `RemoteStore implements Store`? **Usually no**; use `@ConditionalOnMissingBean(Store.class)`.
4. Is `public` mandatory for every Spring `@Bean` method? **No**. Visibility and return-type metadata are two separate issues.
5. When the runtime instance is `InMemoryStore`, was an earlier concrete-type condition guaranteed to match? **No**; check evaluation timing and declared type.
6. Does `@ConditionalOnMissingBean(Store.class)` cause Spring to delete an already-created default bean? **No**; if the condition does not match, the default bean is never registered from that method.
7. Does `@AutoConfiguration(after=X.class)` guarantee X's `@Bean` methods have already been called to create instances? **No**; it only specifies configuration processing order.
8. If the goal is hiding the implementation and letting consumers use a contract, is returning an interface type reasonable? **Yes**, provided downstream components do not rely on concrete-type metadata.
9. When a `@Bean` method returns an optional SDK type, why use a nested `@Configuration` guarded by `@ConditionalOnClass`? **To avoid class loading of the method signature when the SDK is absent**.
10. Which test utility helps verify conditions without booting the whole application? **`ApplicationContextRunner`** with explicitly declared configurations and user beans.

## Official References

- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): explicit guidance on declaring as much type information as possible in `@Bean` return types and evaluating bean conditions.
- [Spring Boot 3.5 — ConditionalOnBean API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html): matching against bean definitions and information available at evaluation time.
- [Spring Boot 3.5 — ConditionalOnMissingBean API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html): default rules with `@Bean` methods and selection criteria.
- [Spring Framework 6.2 — Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/bean-annotation.html): `@Bean`, bean definition types, method parameters, and scope.
- [Spring Boot — Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html): back-off, exclusions, and the Condition Evaluation Report.
