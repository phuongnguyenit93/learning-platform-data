# Distinguishing extending via public APIs from depending on internal framework classes

## 1. Why must we distinguish them?

Spring Framework and Spring Boot provide many extension points designed for applications to use: interfaces, annotations, callbacks, events, builders, customizers, and configuration registration mechanisms. Alongside them, the framework has classes for internal implementation such as parsers, resolvers, registries, selectors, caches, and proxy factories.

Both groups can reside under the `org.springframework` package. Some internal classes even carry the `public` modifier. Therefore, **being able to import a class does not prove it is a supported extension API**.

When code relies on implementation details, upgrading Spring Boot or Spring Framework can break the application even though public contracts continue working. The framework may change packages, constructors, fields, callback invocation order, `BeanDefinition` structures, or annotation processing algorithms. Those details do not have to maintain compatibility for external code.

The goal is to know how to choose documented extension points with the right lifecycle that can be tested independently of the framework's internal implementation.

## 2. API, SPI, and implementation detail

**API (Application Programming Interface)** is the surface an application calls or configures. Examples: `ApplicationContext.getBean(...)`, `RestClient.Builder`, and `@ConfigurationProperties`.

**SPI (Service Provider Interface)** is a contract implemented by an application or another library for the framework to call back into. Examples: `BeanPostProcessor`, `ApplicationContextInitializer`, and `RestClientCustomizer`.

The main difference lies in call direction:

- API: application code calls the framework.
- SPI: the framework calls the implementation supplied by the application.

**Implementation detail** is how the framework fulfills the contract internally. Examples: parsers analyzing annotations, registries storing bean definitions, comparators sorting order, caches holding metadata, or proxy factories generating wrapper objects. These classes can change when the framework refactors.

### 2.1. How to recognize supported APIs/SPIs

Before depending on a type, check:

1. **Reference documentation:** does the documentation guide applications to implement or use that type as an extension point?
2. **Javadoc:** are callbacks, lifecycle, ordering, scope, and registration method clearly described?
3. **Registration mechanism:** is there an official mechanism such as a bean in `ApplicationContext`, `AutoConfiguration.imports`, an event listener, or a builder customizer?
4. **Examples and tests:** do official documentation or tests use that contract in a way applications can replicate?
5. **Version information:** check `@since`, `@Deprecated`, `forRemoval`, release notes, and migration guides.
6. **Internal markers:** do the package or Javadoc explicitly state internal, implementation, do not use, or subclassing not supported?
7. **Reflection:** does the code have to access private fields, unpublished methods, internal bean names, or unguaranteed processing order?

An interface with documented callbacks and a clear registration path is a good sign of an SPI. An internal parser does not become an SPI merely because it can be imported.

### 2.2. The public modifier is not a compatibility promise

The `public` modifier only governs Java accessibility. It does not assert that a class is meant for application extension.

A public class may exist for the framework to share implementation across modules, for testing/debugging, or for internal integration. Look for documentation explicitly stating how applications should use that type. Do not draw conclusions solely from package names, modifiers, or IDE import suggestions.

## 3. Common public extension points

| Need | Contract to consider first | Lifecycle |
| --- | --- | --- |
| Initialize context before refresh | `ApplicationContextInitializer` | Before context refresh |
| Modify bean definitions/metadata | `BeanFactoryPostProcessor` or `BeanDefinitionRegistryPostProcessor` | After loading metadata, before creating most beans |
| Modify or wrap bean instances | `BeanPostProcessor` | During bean initialization |
| Listen for events | `ApplicationListener` or `@EventListener` | When events are published |
| Choose configurations to import | `ImportSelector` or `DeferredImportSelector` | While Spring processes configuration classes |
| Customize Boot builders | Boot-published Customizer SPIs | Inside component creation pipelines |
| Provide replaceable default beans | `@AutoConfiguration`, `@Bean`, `@ConditionalOnMissingBean` | When Boot registers auto-configuration |
| Publish library configuration | `@ConfigurationProperties` | During property binding |

These are documented contracts, which does not mean every one of them is the first choice for every problem. Choose the hook with the narrowest scope and the most appropriate phase.

### 3.1. Prefer high-level customizers when available

Spring Boot 3.5 publishes several specific callbacks:

- `org.springframework.boot.web.client.RestClientCustomizer` customizes `RestClient.Builder`.
- `org.springframework.boot.web.client.RestTemplateCustomizer` customizes `RestTemplate`.
- `org.springframework.boot.web.server.WebServerFactoryCustomizer` customizes web server factories before server startup.

Example:

```java
@Bean
RestClientCustomizer applicationHeader() {
    return builder -> builder.defaultHeader("X-Application", "catalog");
}
```

Customizers are only applied to builders that pass through the pipeline invoking them. If you call `RestClient.create()` directly, the application bypasses Boot's auto-configuration and customizers. `RestClient.Builder` is stateful, so mutating the builder affects clients subsequently built from that builder.

When a targeted high-level hook exists, using it is usually less risky than replacing entire beans or intervening in the container.

### 3.2. Auto-configuration is a public contract

When developing a starter, use the annotations and registration mechanisms published by Spring Boot:

```java
@AutoConfiguration
@ConditionalOnClass(ExternalClient.class)
public class ExternalClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(ExternalClient.class)
    ExternalClient externalClient(ExternalClientProperties properties) {
        return new ExternalClient(properties.getEndpoint());
    }
}
```

`ExternalClient` and `ExternalClientProperties` are hypothetical types from the example library.

In the starter JAR, register auto-configurations in:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Each line is the fully qualified name of an auto-configuration class. This is the registration mechanism documented by Spring Boot. If ordering is needed, use `before`/`after` on `@AutoConfiguration` or the corresponding ordering annotations. Do not rely on classpath scan order or class position in the JAR.

## 4. Understanding the lifecycle of foundational SPIs

### 4.1. BeanPostProcessor: processing bean instances

`BeanPostProcessor` receives callbacks when bean instances are created. It can inspect beans, add behavior, or return wrappers/proxies.

- `postProcessBeforeInitialization` runs before initialization callbacks such as `afterPropertiesSet()` or init methods.
- `postProcessAfterInitialization` runs after initialization callbacks.
- `ApplicationContext` automatically detects beans implementing BPP.
- BPPs belong to each container; a BPP in a parent context does not automatically process beans created in a child context.

BPPs are created very early in order to process other beans. When registering via `@Bean`, use a `static` method and avoid unnecessary dependencies. If a BPP triggers premature instantiation of other beans, those beans may miss full processing by all post-processors, such as AOP auto-proxying.

BPPs have broad scope because they are invoked for many beans. If you only want to configure a specific builder, a dedicated customizer is usually more appropriate.

### 4.2. BeanFactoryPostProcessor: processing bean definition metadata

`BeanFactoryPostProcessor` operates on bean configuration metadata such as `BeanDefinition` before most bean instances are created. Use it when you genuinely need to adjust container-level metadata or property values.

Do not call `beanFactory.getBean(...)` inside a BFPP to fetch instances and mutate objects. Doing so instantiates beans too early, can bypass normal post-processing, and causes lifecycle bugs.

`BeanDefinitionRegistryPostProcessor` is an extended SPI for registering or modifying bean definitions at the registry level. This is a low-level hook; use it only when annotations, auto-configuration, and `@Bean` factory methods cannot meet the requirement.

### 4.3. ApplicationContextInitializer: bootstrapping before refresh

`ApplicationContextInitializer` receives `ConfigurableApplicationContext` before the context is refreshed. Documented use cases include programmatically registering `PropertySource`s or activating profiles.

This is an early bootstrap hook. If you only need to configure values, `application.yml` or externalized configuration mechanisms are usually simpler. Avoid instantiating business beans in an initializer before the context finishes its lifecycle.

### 4.4. ApplicationListener and events

`ApplicationListener<E extends ApplicationEvent>` is the contract for receiving events; `@EventListener` allows declaring listeners as methods. Use them when reacting to events with documented public meaning in the lifecycle or domain.

Do not rely on internal events that merely happen to be published at startup if documentation does not commit to them as a contract. Even for a public event, read the documentation to understand timing, ordering, and publishing scope.

### 4.5. ImportSelector and DeferredImportSelector

These two SPIs let you choose configurations to import while Spring processes configuration classes. They suit libraries with dynamic import requirements more complex than standard annotation conditions.

For Spring Boot auto-configuration, start with `@AutoConfiguration`, `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnMissingBean`, and `AutoConfiguration.imports`. Only write a custom selector when truly required.

## 5. Internal classes and brittle dependencies

### 5.1. Common signs

Implementation details can appear in the following forms:

- Classes in `internal` packages or explicitly marked internal in Javadoc.
- Specific parsers, resolvers, registries, selectors, or processors used by the framework to execute annotations.
- Private/protected fields not published as extension contracts.
- Constructors intended solely for framework instantiation.
- Method call orders or bean names not guaranteed by documentation.
- Specific `BeanDefinition` structures that the framework happens to produce for an annotation.
- Proxy classes, CGLIB enhancers, bytecode, reflection, or internal caches.
- Logs/stack traces used as a control protocol.

For example, `ConfigurationClassParser` and `ConfigurationClassPostProcessor` are components in Spring's configuration-processing pipeline. They help the framework interpret `@Configuration`, but they are not the default choice for applications building auto-configuration extensions. Use `@AutoConfiguration`, `@Import`, selector SPIs, or appropriate public conditions.

Do not classify solely by package name. Some `support` packages contain documented APIs, while a public class can still be infrastructure. Evaluate each type by its contract and official guidance.

### 5.2. Example of internal dependency to avoid

```java
// Anti-pattern: depending on internal implementation
Class<?> parser = Class.forName(
    "org.springframework.context.annotation.ConfigurationClassParser"
);

// Then use reflection to read private fields or invoke internal methods.
```

There is no supported contract for applications to read parser state this way. Code can break when packages, fields, module access, or algorithms change.

Another form is subclassing an infrastructure class to override protected methods not documented as extension hooks. When the framework changes constructors or call flows, the subclass may stop working.

### 5.3. Why is reflection especially risky?

Reflection accesses members that normal Java code cannot call directly. Since Java 9, the module system can restrict deep access; flags like `--add-opens` make deployment additionally dependent on runtime configuration.

Even if reflection works today, it creates no compatibility promise for private fields or methods. Similarly, internal bean names can change when auto-configurations are refactored. If documentation provides a public interface, type, or qualifier, inject against that contract.

## 6. Runnable example: public BeanPostProcessor

This example uses **Java 17 and Spring Boot 3.5.0**. A bean implementing `GreetingService` is annotated with `@Traceable`. A public BPP inspects the annotation and wraps the bean in a JDK dynamic proxy. The test verifies the bean is wrapped and method calls still delegate to the implementation.

This is an example for learning the SPI. In real applications, if the goal is method tracing/metrics, evaluate Spring AOP or Micrometer Observation before writing custom proxies. BPPs operate at the container level, so understanding the lifecycle is necessary.

### Structure

```text
public-spi-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── example/
                └── PublicExtensionPointTest.java
```

### `pom.xml` file

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>public-spi-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>

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
</project>
```

### `src/test/java/example/PublicExtensionPointTest.java` file

```java
package example;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.config.BeanPostProcessor;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class PublicExtensionPointTest {

    @Target(ElementType.TYPE)
    @Retention(RetentionPolicy.RUNTIME)
    @interface Traceable {}

    interface GreetingService {
        String greet(String name);
    }

    @Traceable
    static class DefaultGreetingService implements GreetingService {
        @Override
        public String greet(String name) {
            return "Hello, " + name;
        }
    }

    static class TraceableBeanPostProcessor implements BeanPostProcessor {

        @Override
        public Object postProcessAfterInitialization(
                Object bean, String beanName) {

            if (!(bean instanceof GreetingService)
                    || !bean.getClass().isAnnotationPresent(Traceable.class)) {
                return bean;
            }

            return Proxy.newProxyInstance(
                bean.getClass().getClassLoader(),
                new Class<?>[] { GreetingService.class },
                (proxy, method, args) -> {
                    try {
                        return method.invoke(bean, args);
                    }
                    catch (InvocationTargetException exception) {
                        throw exception.getCause();
                    }
                }
            );
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class SampleConfiguration {

        // BPP is discovered early: static factory, no dependencies.
        @Bean
        static BeanPostProcessor traceableBeanPostProcessor() {
            return new TraceableBeanPostProcessor();
        }

        @Bean
        GreetingService greetingService() {
            return new DefaultGreetingService();
        }
    }

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(SampleConfiguration.class);

    @Test
    void publicBeanPostProcessorWrapsTheSelectedBean() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(GreetingService.class);

            GreetingService service = context.getBean(GreetingService.class);

            assertThat(Proxy.isProxyClass(service.getClass())).isTrue();
            assertThat(service.greet("Mai")).isEqualTo("Hello, Mai");
        });
    }
}
```

### Running and results

In the directory containing `pom.xml`, using JDK 17+ and Maven:

```bash
java -version
mvn test
```

**Expected result:** one JUnit test passes and Maven finishes with `BUILD SUCCESS` if dependencies download successfully. The code does not call `System.out.println`, so there is no fixed business stdout.

Why this is extending via a contract:

- The code implements `BeanPostProcessor`, a Spring Framework published and documented interface.
- The context automatically detects the BPP through the standard mechanism; it does not read internal registries.
- The BPP relies only on the `GreetingService` interface and `Traceable` annotation owned by the application.
- `postProcessAfterInitialization` is a public callback; there is no need to access private fields or subclass parsers.
- The proxy implements `GreetingService`, so consumers should inject the interface rather than the concrete class `DefaultGreetingService`.
- The BPP registration method is `static` with no dependencies to avoid prematurely initializing unrelated beans.

The example uses a JDK proxy, so the proxy only exposes the `GreetingService` interface. Consumers injecting by concrete class may be incompatible with the proxy. This is a limitation of the wrapping approach, not a Spring bug.

## 7. Auto-configuration example using public APIs

Suppose a library provides `CatalogClient`. Users wishing to replace the default implementation use public auto-configuration and conditions:

```java
@AutoConfiguration
@ConditionalOnClass(CatalogClient.class)
public class CatalogAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CatalogClient.class)
    CatalogClient catalogClient(CatalogProperties properties) {
        return new DefaultCatalogClient(properties.getBaseUri());
    }
}
```

This is an illustrative snippet; `CatalogClient` and `CatalogProperties` belong to the example library.

Register in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`:

```text
com.example.catalog.autoconfigure.CatalogAutoConfiguration
```

Test using `ApplicationContextRunner`, add user configuration, and verify the default bean backs off. You do not need to subclass `AutoConfigurationImportSelector` or manipulate internal parsers to add a new auto-configuration.

## 8. Choosing an SPI by lifecycle

| Question | Appropriate choice | Avoid |
| --- | --- | --- |
| Want to change a component's configuration properties? | `@ConfigurationProperties` or public customizers/builders | Reflecting into bean fields after creation |
| Want to modify a bean instance after creation? | `BeanPostProcessor` for container-level handling; AOP if the goal is method interception | Mutating instances in `BeanFactoryPostProcessor` by calling `getBean` |
| Want to adjust metadata before beans are created? | `BeanFactoryPostProcessor` or `BeanDefinitionRegistryPostProcessor` | Accessing private parsers |
| Want to configure the context before refresh? | `ApplicationContextInitializer` | Calling internal refresh or initializing beans too early |
| Want to react to events? | `ApplicationListener` / `@EventListener` and public events | Watching logs or undocumented internal events |
| Want to add auto-configuration? | `@AutoConfiguration` + `AutoConfiguration.imports` | Replacing internal selectors |
| Want to add options to a Boot builder? | Corresponding Customizer SPI | Wrapping unrelated infrastructure beans |
| Want to replace a default bean? | `@ConditionalOnMissingBean` + user bean | Renaming internal beans or enabling overriding arbitrarily |

**Practical rule:** pick the highest-level API that meets the requirement. Low-level SPIs such as BPP/BFPP have broader blast radius, more complex lifecycles, and require more thorough testing.

## 9. Checking stability across version upgrades

### 9.1. Inspect Javadoc and release notes

Before using a class:

- Open the Javadoc matching the application's exact dependency version.
- Read the class/interface, method, callback, and `@since` descriptions.
- Check deprecation annotations, the version deprecation began, and `forRemoval`.
- Read migration guides between major versions.
- Check whether documentation instructs implementing the interface or registering a bean.
- If an API was renamed or moved to another package, prefer the replacement API indicated in the Javadoc.

Do not read `current` Javadoc and assume a Boot 3.5 project has the identical API. Open versioned Javadoc matching your actual dependencies.

### 9.2. Declare dependencies explicitly

If library code invokes a type from Spring Boot, declare the required dependency explicitly. Do not rely on another dependency accidentally pulling that class onto the transitive classpath. For starters, distinguish compile/runtime dependencies from test-only dependencies.

Do not copy internal classes from framework source into application code. Copying code does not turn an implementation detail into a contract and creates a burden to sync bug/security fixes.

### 9.3. Write tests against public behavior

- Test which beans exist, which beans back off, and which properties bind.
- Test that callbacks are actually invoked through the supported registration path.
- Test that the context starts and closes cleanly according to lifecycle.
- If supporting multiple Spring Boot versions, run the corresponding compatibility test matrix.
- Do not assert proxy class names, private fields, internal bean numbers, or undocumented log output.

`ApplicationContextRunner` is useful for testing auto-configurations across combinations of properties, user beans, and classpath states. For web contexts, use `WebApplicationContextRunner` or `ReactiveWebApplicationContextRunner`.

### 9.4. Monitor deprecations

When encountering `@Deprecated(since = "x", forRemoval = true)`, do not just suppress warnings. Read the Javadoc and migration guide to learn the replacement API. When upgrading major versions, audit imports from Spring Framework/Boot, especially extension hooks, customizers, and SPIs registered via resource files.

## 10. Common design mistakes

1. **Relying on the `public` modifier:** an importable class does not prove it is an application-facing API. Look up extension contract documentation.
2. **Using reflection to read private fields:** replace with properties, accessors, events, or published SPIs. Reflection can break due to module access or refactoring.
3. **Subclassing infrastructure classes:** only subclass when documentation states the class is designed for extension and documents which methods to override. Otherwise, use interfaces/callbacks.
4. **Relying on accidental bean registration order:** use `@Order`/`Ordered` when supported by the contract and understand the semantics. Do not rely on classpath order.
5. **Relying on unpublished bean names:** inject by interface/type or application qualifier; only use names when explicitly part of the contract.
6. **Using BFPP to mutate object instances:** BFPP works with metadata; BPP works with instances.
7. **Registering BPPs with heavy dependencies:** BPPs are created very early; their dependencies may not be fully post-processed. Use static factory methods with minimal dependencies.
8. **Wrapping every bean when only a narrow hook is needed:** BPPs apply across many beans. Use specialized customizers if available.
9. **Relying on Boot internal classes to modify auto-configuration:** use `@AutoConfiguration`, conditions, and `AutoConfiguration.imports`.
10. **Testing implementation instead of contract:** verify the behavior the application needs, rather than locking tests to proxy class names or internal bean definition structures.
11. **Ignoring deprecations:** code still compiles in the current version but may be removed in the next release.
12. **Classifying solely by package name:** do not assume everything in `support` packages is internal or everything in `autoconfigure` is public API. Inspect each type and its documented purpose.

## 11. Extension point review checklist

Before merging Spring integration code, answer:

- [ ] Have we checked official documentation/Javadoc for the exact version?
- [ ] Is this an API called by the application or an SPI called back by the framework?
- [ ] When does the lifecycle callback happen: before or after refresh/initialization?
- [ ] Is there an official registration path and proper resource file/bean method?
- [ ] Is the scope of impact one builder, one bean, all beans, or the entire `ApplicationContext`?
- [ ] Does it depend on packages/classes/fields/methods marked internal?
- [ ] Does it use reflection, `setAccessible`, `--add-opens`, unpublished bean names, or unguaranteed ordering?
- [ ] Is there a higher-level, narrower API that satisfies the requirement?
- [ ] Are there tests with `ApplicationContextRunner` or a real context verifying the contract?
- [ ] Have `@since`, deprecations, migration guides, and supported versions been reviewed?

If contract questions remain unanswered, verify before depending on that class.

## 12. Self-check questions

**Question 1.** A class has the `public` modifier in a Spring package. Does that prove it is a supported extension API?  
**Answer:** No. `public` only allows access from other code; check documentation, intent, and the extension contract.

**Question 2.** Which SPI should you use to intercept a bean instance after initialization?  
**Answer:** `BeanPostProcessor`, or AOP/customizers if a higher-level hook fits better.

**Question 3.** Should `BeanFactoryPostProcessor` be used to call `getBean()` and mutate objects?  
**Answer:** No. It modifies bean definition metadata before beans are created. Use `BeanPostProcessor` when processing instances.

**Question 4.** Why should a BPP be registered via a `static` `@Bean` method with minimal dependencies?  
**Answer:** BPPs are created very early to process other beans; unnecessary dependencies could be instantiated before all post-processors are registered.

**Question 5.** When adding auto-configuration in a Boot 3.x starter, should you subclass internal parsers?  
**Answer:** No. Use `@AutoConfiguration`, public conditions, and `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.

**Question 6.** To add a header to a Boot-managed `RestClient.Builder`, what is the first choice?  
**Answer:** Spring Boot 3.5's `RestClientCustomizer`, if the builder is created through the auto-configuration/customizer pipeline. `RestClient.create()` bypasses that pipeline.

**Question 7.** If an API is marked deprecated with `forRemoval=true`, can you just suppress the warning?  
**Answer:** You should not. Read the Javadoc and migration guide to migrate to the replacement API.

**Question 8.** Should tests assert the proxy class name generated by Spring?  
**Answer:** Usually no. Assert interfaces, behavior, and contracts needed by the application; proxy class names are an implementation detail.

## Official references

- Spring Framework Reference — Container Extension Points: https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html
- Spring Framework Javadoc 6.2 — `BeanPostProcessor`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/config/BeanPostProcessor.html
- Spring Framework Javadoc 6.2 — `BeanFactoryPostProcessor`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/config/BeanFactoryPostProcessor.html
- Spring Framework Javadoc 6.2 — `ApplicationContextInitializer`: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/ApplicationContextInitializer.html
- Spring Boot 3.5 Reference — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
- Spring Boot 3.5 API — `RestClientCustomizer`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/client/RestClientCustomizer.html
- Spring Boot 3.5 API — `WebServerFactoryCustomizer`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/server/WebServerFactoryCustomizer.html
- Spring Boot Reference — Calling REST Services and `RestClientCustomizer`: https://docs.spring.io/spring-boot/reference/io/rest-client.html

**Takeaway:** Extend Spring through **documented contracts**: interfaces, annotations, callbacks, events, builders, and official registration mechanisms. A class can be accessible while still being purely an internal framework implementation. Testing public behavior and upgrading with migration guides reduces dependence on fragile details.
