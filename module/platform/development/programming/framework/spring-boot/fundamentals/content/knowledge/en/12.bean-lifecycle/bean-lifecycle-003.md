# @PostConstruct and the jakarta.annotation Namespace Across Version Lines

In the lifecycle of a Spring bean, there are tasks that should only execute after Spring has created the object and injected the required dependencies. For example, a bean may need to validate bound configuration, build an internal data structure, or prepare initial state before being used. The `@PostConstruct` annotation provides a callback for this phase.

When working with Spring Boot, pay attention to the **annotation namespace changing across Spring Framework generations**:

- Spring Boot 2.x (Spring Framework 5.x) uses `javax.annotation.PostConstruct`.
- Spring Boot 3.x (Spring Framework 6.x) uses `jakarta.annotation.PostConstruct`.

This is an important change when upgrading applications. The two annotations have similar names and purposes, but belong to **two different packages**, so code importing the wrong namespace may fail to compile or the callback may not be processed by Spring as expected.

## 1. What Is @PostConstruct Used For?

`@PostConstruct` marks a method to be called after dependency injection and initial bean setup steps complete, before the bean is put into normal use.

Example with Spring Boot 3:

~~~java
package com.example.catalog.service;

import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Service;

@Service
public class CatalogCache {

    private final ProductRepository productRepository;

    private java.util.Map<Long, String> productNames;

    public CatalogCache(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    @PostConstruct
    void initialize() {
        this.productNames = productRepository.findAllNames();
    }

    public String findName(long productId) {
        return productNames.get(productId);
    }
}
~~~

When Spring creates `CatalogCache`:

1. Instantiates the class.
2. Injects `ProductRepository` via the constructor.
3. Processes dependency setup and related callbacks.
4. Calls the `initialize()` method annotated with `@PostConstruct`.
5. Completes the bean initialization phase and puts the bean into service.

When `initialize()` runs, the `productRepository` field has already been assigned. That is why this callback is suited for work that needs to use injected dependencies.

The example above assumes `ProductRepository.findAllNames()` is an application-defined API. Loading all data into memory is only appropriate when data size and cache refresh policies are controlled; do not treat `@PostConstruct` as a default place to load huge datasets or make unbounded calls to external services.

**Spring Framework executes this lifecycle callback.** Spring Boot provides the startup environment and application configuration; `@PostConstruct` itself belongs to the Jakarta/Java Common Annotations API (or the older Java EE namespace), not an annotation exclusive to Spring Boot.

## 2. How Do the javax and jakarta Namespaces Differ?

In older versions, the annotation was declared in the `javax.annotation` package:

~~~java
import javax.annotation.PostConstruct;
~~~

Starting with the Jakarta EE generation, Java EE APIs moved to the `jakarta.*` namespace:

~~~java
import jakarta.annotation.PostConstruct;
~~~

The short class name remains `PostConstruct`, but the fully qualified names differ:

| Generation | Fully qualified class name |
|---|---|
| Java EE / javax | `javax.annotation.PostConstruct` |
| Jakarta EE / jakarta | `jakarta.annotation.PostConstruct` |

In the JVM, these two fully qualified names are **two distinct types**. An annotation compiled with `javax.annotation.PostConstruct` is not the `jakarta.annotation.PostConstruct` annotation. Simply renaming a dependency or switching JDK versions does not make the two types automatically compatible.

## 3. Choosing Imports by Spring Boot Release Line

Key practical rule:

| Spring Boot | Underlying Spring Framework | Namespace used for @PostConstruct |
|---|---|---|
| Boot 2.x | Spring Framework 5.x | `javax.annotation.PostConstruct` |
| Boot 3.x | Spring Framework 6.x | `jakarta.annotation.PostConstruct` |

Boot 3 is the major transition milestone to Jakarta EE APIs. If a project is upgraded from Boot 2 to Boot 3, relevant Java EE imports must be migrated to their Jakarta counterparts, including `PostConstruct` and `PreDestroy`.

For newer Boot lines that continue to build on Spring Framework 6+ and Jakarta APIs, keep using the `jakarta.annotation` namespace. Do not determine the namespace based on the running JDK name or the simple annotation name alone; check the **Spring Framework version managed by your Spring Boot line**.

### 3.1. Example with Spring Boot 2.x

~~~java
package com.example.catalog;

import javax.annotation.PostConstruct;
import org.springframework.stereotype.Component;

@Component
public class StartupRegistry {

    @PostConstruct
    public void initialize() {
        // Prepare state after dependencies have been injected.
    }
}
~~~

This is the appropriate import for applications based on Spring Framework 5.x, commonly seen in Spring Boot 2.x.

### 3.2. Example with Spring Boot 3.x

~~~java
package com.example.catalog;

import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Component;

@Component
public class StartupRegistry {

    @PostConstruct
    public void initialize() {
        // Prepare state after dependencies have been injected.
    }
}
~~~

The class body stays unchanged; the difference appears in the package import. With Spring Framework 6, the callback is detected via the Jakarta annotation.

## 4. Why Might Java 11+ Require Declaring the Annotation API Dependency?

A common misconception is thinking `javax.annotation.PostConstruct` is always built into the JDK because people saw code run on Java 8 without adding extra libraries.

The relevant Java EE APIs used to be present in older Java SE environments through Java EE/CORBA modules that were removed from the JDK. Starting with **JDK 11**, `javax.annotation` is no longer provided out of the box the way it used to be. Similarly, `jakarta.annotation` is an API external to the JDK, not a package included in Java SE by default.

Therefore, the application must have the matching annotation API on the compile/runtime classpath.

### 4.1. Spring Boot 2.x on modern JDKs

For Boot 2.x projects using JDK 11 or higher, if the dependency tree does not yet include the old API, you can declare:

~~~groovy
dependencies {
    implementation 'javax.annotation:javax.annotation-api'
}
~~~

If the project uses Spring Boot dependency management/BOM, a compatible version can be managed centrally. If not using a BOM, declare a suitable API version rather than leaving the dependency versionless.

### 4.2. Spring Boot 3.x

For Boot 3.x projects, declare the Jakarta API if it is not already on the classpath:

~~~groovy
dependencies {
    implementation 'jakarta.annotation:jakarta.annotation-api'
}
~~~

Spring Boot dependency management handles the right version when the project uses the BOM or corresponding dependency management plugin. Do not pick an arbitrary Jakarta API version when Spring Boot already provides version alignment.

### 4.3. Maven example

If using Maven with the Spring Boot parent/BOM:

~~~xml
<dependency>
    <groupId>jakarta.annotation</groupId>
    <artifactId>jakarta.annotation-api</artifactId>
</dependency>
~~~

For Boot 2.x, the corresponding artifact coordinates are:

~~~xml
<dependency>
    <groupId>javax.annotation</groupId>
    <artifactId>javax.annotation-api</artifactId>
</dependency>
~~~

Only add the dependency belonging to the namespace matching your application's Spring Framework generation. If a starter or another dependency already brings the right API onto the classpath, there is no need to declare it redundantly.

## 5. How Does Spring Detect and Invoke @PostConstruct?

In an application context based on annotation configuration, Spring registers a `BeanPostProcessor` responsible for processing lifecycle annotations such as `@PostConstruct` and `@PreDestroy`. This mechanism is normally handled by `CommonAnnotationBeanPostProcessor`, built on the `InitDestroyAnnotationBeanPostProcessor` infrastructure.

High-level initialization flow:

~~~text
Spring needs to create a bean
       |
       v
Instantiate object
       |
       v
Constructor injection / populate properties
       |
       v
Aware callbacks (if any)
       |
       v
BeanPostProcessor before initialization
       |
       v
@PostConstruct callback
       |
       v
InitializingBean.afterPropertiesSet()
       |
       v
Custom init method (if any)
       |
       v
BeanPostProcessor after initialization
       |
       v
Bean ready for other beans to use
~~~

This is the common lifecycle order of a Spring bean. Exact steps also depend on bean type, processors, and application configuration.

### Order among initialization callbacks

If a bean simultaneously uses multiple init mechanisms, the typical order is:

1. `@PostConstruct` method.
2. `InitializingBean.afterPropertiesSet()`.
3. Custom init method declared via `@Bean(initMethod = "...")` or equivalent configuration.

Example:

~~~java
import jakarta.annotation.PostConstruct;
import org.springframework.beans.factory.InitializingBean;

public class SearchIndex implements InitializingBean {

    @PostConstruct
    void postConstruct() {
        System.out.println("1. PostConstruct");
    }

    @Override
    public void afterPropertiesSet() {
        System.out.println("2. afterPropertiesSet");
    }

    public void initializeIndex() {
        System.out.println("3. custom init method");
    }
}
~~~

To run all three callbacks in the example, a custom init method must be declared for the bean, for instance:

~~~java
@Bean(initMethod = "initializeIndex")
SearchIndex searchIndex() {
    return new SearchIndex();
}
~~~

Do not simultaneously register `SearchIndex` via component scanning and another `@Bean` method unless intentional, as that can create two separate bean definitions. The two snippets above illustrate a single bean definition configured with all callbacks, not two independent registrations to combine arbitrarily.

## 6. Rules for Writing @PostConstruct Methods

To keep callbacks readable and compliant with the lifecycle annotation contract, follow these rules:

- The method takes no parameters.
- The method is not `static`.
- The method returns `void`.
- The method is usually given a clear name such as `initialize()`, `loadMetadata()`, or `prepareCache()`.
- Keep one primary callback per class so initialization order and responsibilities are predictable.
- Do not call constructors directly or instantiate the object yourself with `new` if you expect Spring to invoke callbacks for that object.

Good example:

~~~java
@PostConstruct
void initialize() {
    // Initialize internal state.
}
~~~

Spring permits method visibility compatible with the framework's annotation processing rules; callbacks are not required to be `public`. However, use `public` or package-private/protected consistently with project style and avoid making the method overly complex.

Do not write:

~~~java
@PostConstruct
static void initialize() {
}
~~~

~~~java
@PostConstruct
void initialize(String mode) {
}
~~~

These forms are unsuitable for a standard lifecycle callback because static methods or methods with parameters do not satisfy the callback invocation contract.

## 7. Is @PostConstruct Called for Every Scope?

`@PostConstruct` is tied to **the initialization phase of a Spring-managed instance**, not exclusively to singletons.

| Scope | Callback timing |
|---|---|
| Singleton | When the singleton instance is created and initialized |
| Prototype | Every time the container creates a prototype instance |
| Request | When the request-scoped instance is created within a request context |
| Session | When the session-scoped instance is created |

For non-lazy singletons, the callback typically runs during context startup. For lazy singletons or prototypes, the callback may only run when the bean is actually requested.

Prototype example:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
class TemporaryReport {

    @PostConstruct
    void prepare() {
        System.out.println("Prepare a new report instance");
    }
}
~~~

Each time Spring resolves `TemporaryReport` and creates a new instance, the callback is invoked for that instance. If a singleton injects a prototype directly, the prototype is only created when the singleton is initialized; the callback does not automatically re-run on each method call on the singleton.

## 8. What Happens If @PostConstruct Throws an Exception?

The callback is part of bean initialization. If it throws an unhandled exception, Spring considers bean initialization to have failed. For an eager singleton created during startup, that error typically causes application context creation to fail and prevents the application from starting up completely.

Example:

~~~java
@Component
class RequiredConfiguration {

    @PostConstruct
    void validate() {
        if (!configurationIsValid()) {
            throw new IllegalStateException(
                    "Required configuration is invalid");
        }
    }

    private boolean configurationIsValid() {
        return false;
    }
}
~~~

This is a useful way to fail fast when a required invariant is not satisfied. However, distinguish real configuration errors from temporary external service failures.

A few caveats:

- If the callback performs network connections, relies on DNS, or calls external services, the application may fail to start when that system is temporarily unavailable.
- If the callback loads very large amounts of data, startup time can increase significantly.
- If the callback runs on a prototype, the exception fails that instance creation; it does not mean every other prototype bean cannot be created.
- Do not swallow exceptions and leave the bean in a half-initialized state if subsequent methods assume data is ready.

## 9. @PostConstruct and Spring AOP/Proxies

A subtle point: the `@PostConstruct` callback is typically invoked during the BeanPostProcessor phase **before the bean is wrapped in a proxy during the post-initialization phase**. Therefore, do not call a method on the same bean inside `@PostConstruct` expecting AOP interceptors like `@Transactional` or `@Async` to already work as they do when called through a proxy.

Example you should not rely on:

~~~java
@Service
class AccountService {

    @PostConstruct
    void initialize() {
        refreshAccounts();
    }

    @Transactional
    public void refreshAccounts() {
        // Update data.
    }
}
~~~

The `refreshAccounts()` call here is a self-invocation on the initializing instance; it does not go through a Spring proxy the way a call from another bean does. Therefore, the transaction annotation on the method is not activated solely by this call.

If you need transactional or AOP behavior, move the logic to another bean and invoke that bean after the context is ready, or use an appropriate lifecycle event/runner:

~~~java
@Component
class StartupTask {
    private final AccountInitializer initializer;

    StartupTask(AccountInitializer initializer) {
        this.initializer = initializer;
    }

    @EventListener(ApplicationReadyEvent.class)
    void afterApplicationReady() {
        initializer.refresh();
    }
}
~~~

~~~java
@Service
class AccountInitializer {
    @Transactional
    public void refresh() {
        // Transaction is invoked through the bean proxy when AOP is properly configured.
    }
}
~~~

This snippet uses `ApplicationReadyEvent` to demonstrate an operation at the stage when the application is ready, not as a mandatory replacement for `@PostConstruct`. Calling through another bean allows the transactional call to pass through `AccountInitializer`'s proxy.

## 10. Do Not Use @PostConstruct for Every Startup Task

`@PostConstruct` is suited for **internal initialization of a single bean** after dependencies are injected. Other tasks should use specialized callbacks/events:

| Need | Typically appropriate mechanism |
|---|---|
| Validate internal state after dependency injection | `@PostConstruct` |
| Configure a named init step on a factory-method bean | `@Bean(initMethod = "...")` |
| Participate in Spring's lifecycle interface | `InitializingBean` |
| Run logic after the context has refreshed | `ContextRefreshedEvent` |
| Run logic after the Boot application is ready | `ApplicationReadyEvent` |
| Run ordered/argument-aware startup tasks in Boot | `ApplicationRunner` or `CommandLineRunner` |

Not all callbacks/events occur at the same time. For instance, `@PostConstruct` runs as **each individual bean** initializes; `ApplicationReadyEvent` is published after the Boot application finishes its startup sequence and is ready to serve. Choose the right lifecycle point to avoid depending on other beans that are not yet ready.

### Distinguishing @PostConstruct from ApplicationRunner

~~~java
@Component
class ReferenceDataInitializer implements ApplicationRunner {
    @Override
    public void run(ApplicationArguments args) {
        // Application-level startup work.
    }
}
~~~

`ApplicationRunner` fits logic that needs to execute once the Boot application has built its context. It does not replace setting up simple state inside a single bean. Conversely, if a bean needs internal data before other beans use it, `@PostConstruct` can be the more natural choice.

## 11. Migrating Namespaces When Upgrading Spring Boot 2 to 3

Spring Boot 3 moves the foundation to Spring Framework 6 and Jakarta EE APIs. During an upgrade, not only `PostConstruct` but many other Java EE/Jakarta packages change as well:

| Common API | Spring Boot 2 / Spring 5 | Spring Boot 3 / Spring 6 |
|---|---|---|
| Post construct | `javax.annotation.PostConstruct` | `jakarta.annotation.PostConstruct` |
| Pre destroy | `javax.annotation.PreDestroy` | `jakarta.annotation.PreDestroy` |
| Servlet | `javax.servlet.*` | `jakarta.servlet.*` |
| Persistence | `javax.persistence.*` | `jakarta.persistence.*` |
| Validation | `javax.validation.*` | `jakarta.validation.*` |

Not every package starting with `javax` changes to `jakarta`. For example, `javax.sql`, `javax.crypto`, and `javax.net` are Java SE APIs that remain in the JDK. Only migrate APIs belonging to the Java EE/Jakarta ecosystem per framework and library migration guides.

### 11.1. Update imports in source code

Boot 2:

~~~java
import javax.annotation.PostConstruct;
import javax.annotation.PreDestroy;
~~~

Boot 3:

~~~java
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
~~~

Updating imports is necessary but insufficient if the project still has old dependencies or third-party libraries using legacy Java EE APIs.

### 11.2. Update dependencies

Remove old API dependencies if no library needs them anymore; add the matching Jakarta API when it is not yet on the classpath. Check both direct and transitive dependencies to avoid keeping both namespaces just because an older module has not been upgraded.

### 11.3. Upgrade integrated libraries

A library compiled against `javax.annotation.PostConstruct` does not automatically become compatible with Spring Framework 6 just because the application adds `jakarta.annotation-api`. That library needs a Jakarta-supporting version or must be replaced/upgraded. The two annotations are two different types.

### 11.4. Verify at runtime

After migration:

- Check imports and the dependency tree.
- Start the context to verify the lifecycle processor finds the annotation.
- Verify the callback runs once as expected for singleton instances.
- Verify callbacks on prototypes if the project uses prototypes.
- Inspect startup logs and class-loading errors, especially `ClassNotFoundException` or `NoClassDefFoundError` related to namespaces.

## 12. Testing the @PostConstruct Callback

You can test the callback with a bean that has initialized state:

~~~java
import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Component;

@Component
class StartupState {
    private boolean initialized;

    @PostConstruct
    void initialize() {
        initialized = true;
    }

    boolean isInitialized() {
        return initialized;
    }
}
~~~

A Spring context test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class StartupStateTest {

    @Autowired
    StartupState startupState;

    @Test
    void postConstructRunsBeforeBeanIsUsed() {
        assertThat(startupState.isInitialized()).isTrue();
    }
}
~~~

This test assumes the Boot 3 project has the Jakarta Annotation API on the classpath. If running with Boot 2, change the import to `javax.annotation.PostConstruct` and use the matching API dependency when needed.

For plain unit tests that do not start a Spring context, the annotation does not run automatically:

~~~java
StartupState state = new StartupState();
~~~

`new StartupState()` only calls the Java constructor. It does not pass through Spring's BeanPostProcessor, so `@PostConstruct` is not executed. If you need to test the callback, initialize the bean through a Spring context or expose initialization logic via a separate API that can be unit tested directly.

## 13. Common Errors and How to Troubleshoot Them

| Symptom | Possible cause | What to check |
|---|---|---|
| `package jakarta.annotation does not exist` | Jakarta Annotation API not on compile classpath | Check `jakarta.annotation-api` dependency and dependency management |
| `package javax.annotation does not exist` | Boot 2 project on a JDK that no longer bundles the old API, or missing dependency | Check `javax.annotation-api` in runtime/compile classpath |
| Import compiles, but callback does not run | Wrong namespace for the Spring Framework version, object not managed by Spring, or annotation processor not registered | Check Boot/Spring version, bean registration, and context configuration |
| Callback runs, but dependency is null | Object created via `new`, field injection hasn't happened, or dependency was not injected properly | Ensure object is created by the container and use constructor injection |
| Context fails to start | Callback throws an exception or init operation fails | Read the root cause in logs and verify initialization conditions |
| Transaction does not take effect inside callback | Calling a transactional method on the same object before AOP proxy is ready | Move the operation to another bean or an appropriate lifecycle point |
| `ClassNotFoundException` with javax/jakarta | Library and application are using incompatible namespaces | Align framework, API, and integrated library versions |

A common upgrade mistake is changing the dependency to Jakarta while forgetting to update imports, or updating imports while still pulling in an old library that depends on the `javax` namespace. Inspect the actual classpath rather than looking only at the build file.

## 14. Guidelines for Using @PostConstruct in Spring Boot Applications

1. Use the callback for **preparing the bean's own state** after dependencies have been injected.
2. Choose the import by platform: `javax.annotation.PostConstruct` for Boot 2/Spring 5; `jakarta.annotation.PostConstruct` for Boot 3/Spring 6.
3. On JDK 11 and above, do not assume the old annotation API is still inside the JDK; verify and declare the appropriate dependency.
4. Keep the callback method simple, parameterless, non-static, and returning void.
5. Avoid calling methods on the same bean that require AOP such as `@Transactional` from the callback before the proxy is ready.
6. Do not perform overly heavy startup work or uncontrolled calls to external services; choose events/runners if the logic belongs to the application-ready stage.
7. Test with a Spring context when you want to verify that the lifecycle processor actually invokes the callback.

`@PostConstruct` is a small yet important hook in the bean lifecycle: it runs after Spring sets up dependencies and before the bean enters normal use. When upgrading between Spring Boot 2 and 3, pay close attention to migrating the namespace from `javax.annotation` to `jakarta.annotation`, because two annotations with the same short name are not the same type. Choosing the right API, dependency, and lifecycle timing keeps the callback predictable across version lines.
