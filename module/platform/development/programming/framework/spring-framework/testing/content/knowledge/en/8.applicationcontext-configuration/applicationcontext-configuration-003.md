# Loading Groovy Scripts in Groovy-Configured Projects

Spring Framework allows declaring beans with Groovy scripts through a DSL for bean definitions. This configuration style can be loaded into an `ApplicationContext` just like XML or Java configuration. In a project using Groovy, you can place bean definitions in `.groovy` files, load them with `GenericGroovyApplicationContext` or `GroovyBeanDefinitionReader`, and then refresh the context so Spring creates and manages the beans.

Loading a Groovy script is part of building an `ApplicationContext`: the script is read and converted into `BeanDefinition` instances, those definitions are registered into the bean factory, and then the context is refreshed to complete initialization. Understanding these steps helps avoid errors such as missing beans, missing Groovy runtime, incorrect resource paths, or calling `refresh()` at the wrong time.

## 1. The Groovy Bean-Definition DSL in Spring

Spring supports a DSL written in Groovy for declaring beans. Instead of describing beans with XML or annotations, the script uses a `beans { ... }` block to register bean names, classes, properties, and dependency relationships.

Example file `src/main/resources/context/services.groovy`:

```groovy
import com.example.account.AccountRepository
import com.example.account.AccountRepositoryImpl
import com.example.account.AccountService

beans {
    accountRepository(AccountRepositoryImpl)

    accountService(AccountService) {
        repository = ref('accountRepository')
    }
}
```

In this example:

- `accountRepository` is the bean name registered in the container.
- `AccountRepositoryImpl` is the class Spring instantiates for that bean.
- `accountService` is another bean.
- `repository = ref('accountRepository')` creates a reference to the bean named `accountRepository` and assigns that dependency to the `repository` property of `AccountService`.

The illustrative Java classes can be written as follows:

```java
public interface AccountRepository {
    String findDisplayName(long id);
}

public class AccountRepositoryImpl implements AccountRepository {
    @Override
    public String findDisplayName(long id) {
        return "Account-" + id;
    }
}

public class AccountService {

    private AccountRepository repository;

    public void setRepository(AccountRepository repository) {
        this.repository = repository;
    }

    public String displayName(long id) {
        return repository.findDisplayName(id);
    }
}
```

The Groovy DSL uses property syntax to invoke the corresponding setter. In the example above, `repository = ref(...)` is equivalent to configuring the `repository` property of the bean definition; when the bean is instantiated, Spring calls the appropriate setter.

### 1.1. Declaring Multiple Beans and References Between Them

A script can contain multiple bean definitions. Declaration order does not have to match dependency order because Spring resolves bean references during bean instantiation.

```groovy
beans {
    notificationGateway(SmtpNotificationGateway) {
        host = 'localhost'
        port = 2525
    }

    registrationService(RegistrationService) {
        notificationGateway = ref('notificationGateway')
    }
}
```

`ref('notificationGateway')` represents a dependency on another bean in the same bean factory. It is a bean reference, not a name string assigned directly to the property. If you assign the string `'notificationGateway'`, Spring treats it as a String value and will not interpret it as a bean to inject.

The Groovy DSL also supports bean definition capabilities such as scope configuration, lazy initialization, constructor arguments, inner beans, and other metadata. When using advanced features, keep the configuration readable and verify the exact dependency types expected by the beans.

### 1.2. Bean Definitions vs. Object Instantiation

When a script is read, Spring primarily registers metadata in the form of `BeanDefinition` objects. Reading the script does not mean all singletons have been instantiated immediately.

Basic flow:

```text
Groovy script (.groovy)
        |
        v
GroovyBeanDefinitionReader
        |
        v
Register BeanDefinitions into BeanDefinitionRegistry
        |
        v
ApplicationContext.refresh()
        |
        v
Instantiate beans and handle lifecycle
        |
        v
ApplicationContext ready to serve getBean()
```

For non-lazy singletons, Spring typically creates the beans during refresh. Lazy beans or beans with other scopes may only be created when requested. If a dependency cannot be resolved, the error usually surfaces during refresh or when the corresponding bean is instantiated.

## 2. Loading Scripts with GenericGroovyApplicationContext

`GenericGroovyApplicationContext` is an `ApplicationContext` implementation dedicated to loading bean definitions from Groovy scripts. It is a direct choice when a project wants to use Groovy as its primary configuration source.

Suppose the files have this structure:

```text
src/main/resources/
└── context/
    └── services.groovy
```

You can load the file from Java:

```java
import org.springframework.context.support.GenericGroovyApplicationContext;

public class Application {

    public static void main(String[] args) {
        try (var context = new GenericGroovyApplicationContext()) {
            context.load("classpath:context/services.groovy");
            context.refresh();

            AccountService service = context.getBean(AccountService.class);
            System.out.println(service.displayName(42L));
        }
    }
}
```

Each step has its own purpose:

1. Create `GenericGroovyApplicationContext` using the no-arg constructor.
2. Call `load(...)` to read one or more Groovy resources and register bean definitions.
3. Call `refresh()` to finish creating and configuring the context.
4. Call `getBean(...)` to retrieve the Spring-managed bean.
5. Close the context when the application or usage scope ends so Spring invokes bean destruction callbacks and releases resources.

Using the no-arg constructor and calling `load()`/`refresh()` explicitly makes the lifecycle clear. Do not call `refresh()` again after the context has already been refreshed successfully. For a context used as a standalone container, manage its lifecycle explicitly with `try-with-resources` or a corresponding shutdown mechanism.

### 2.1. Loading Multiple Groovy Resources

`load(...)` can accept multiple resource locations:

```java
try (var context = new GenericGroovyApplicationContext()) {
    context.load(
            "classpath:context/infrastructure.groovy",
            "classpath:context/services.groovy",
            "classpath:context/web-support.groovy");
    context.refresh();

    // Use the registered beans
}
```

You can split scripts by responsibility to keep configuration manageable: infrastructure, services, adapters, or supporting beans. When splitting files, avoid accidentally declaring duplicate bean names. If the same bean name is registered multiple times, the result depends on the bean definition overriding policy and container configuration; do not rely on implicit load order to replace beans.

### 2.2. Loading from Classpath and Filesystem

Spring's resource abstraction lets you load Groovy scripts from multiple sources.

| Resource location | Example | Purpose |
|---|---|---|
| Classpath | `classpath:context/services.groovy` | Script packaged with the application or placed on the classpath |
| File system | `file:/opt/myapp/config/services.groovy` | Configuration script located outside the artifact |
| Relative file path | `file:./config/services.groovy` | Script located relative to the process working directory |

Example:

```java
try (var context = new GenericGroovyApplicationContext()) {
    context.load("file:./config/application-context.groovy");
    context.refresh();
}
```

Relative paths are resolved against the process working directory, not necessarily the directory containing the JAR file. In deployment environments, use explicit configuration paths and verify file existence, read permissions, and packaging. Do not assume relative paths are identical across IDEs, Gradle/Maven, and containerized services.

### 2.3. Loading Scripts with a Resource Object

If the application already has a `Resource` or wants to decide how resources are resolved, you can pass the resource to the reader via `GenericGroovyApplicationContext` or `GroovyBeanDefinitionReader`.

Example with a classpath resource:

```java
import org.springframework.core.io.ClassPathResource;
import org.springframework.context.support.GenericGroovyApplicationContext;

try (var context = new GenericGroovyApplicationContext()) {
    context.load(new ClassPathResource("context/services.groovy"));
    context.refresh();
}
```

This approach is useful when the resource is created programmatically or passed in from another configuration component. `ClassPathResource` uses a path relative to the classpath; do not add the `classpath:` prefix when a concrete resource object has already been created.

## 3. Loading Scripts with GroovyBeanDefinitionReader

`GroovyBeanDefinitionReader` is a reader specialized in reading Groovy scripts and registering bean definitions into a `BeanDefinitionRegistry`. It is useful when you need to combine Groovy scripts with another configuration style in the same context.

Example:

```java
import org.springframework.beans.factory.groovy.GroovyBeanDefinitionReader;
import org.springframework.context.support.GenericApplicationContext;

GenericApplicationContext context = new GenericApplicationContext();
GroovyBeanDefinitionReader reader = new GroovyBeanDefinitionReader(context);

reader.loadBeanDefinitions("classpath:context/services.groovy");
context.refresh();

try {
    AccountService service = context.getBean(AccountService.class);
    System.out.println(service.displayName(42L));
} finally {
    context.close();
}
```

The reader does not replace `ApplicationContext`. It is only responsible for reading Groovy sources and registering definitions into the supplied registry. The context itself still manages lifecycle, dependency injection, events, resources, and bean destruction.

### 3.1. When to Choose GenericGroovyApplicationContext?

Use `GenericGroovyApplicationContext` when:

- Most or all bean definitions come from Groovy scripts.
- You want the `load()` API and context lifecycle encapsulated in a single object.
- You do not need to coordinate multiple reader types manually.

Use `GroovyBeanDefinitionReader` when:

- You already have a `GenericApplicationContext` and want to load additional Groovy bean definitions.
- You want to combine Java annotation configuration, XML, or other bean definition sources.
- You need explicit control over which reader registers beans into the registry.

Both approaches use Spring's bean definition mechanism. The difference lies mainly in how configuration loading is organized.

## 4. Combining Groovy Scripts with Java Configuration

A project is not forced to choose exclusively between Groovy or Java configuration. `GenericApplicationContext` can receive bean definitions from multiple readers before refresh.

Example Java configuration class:

```java
import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class InfrastructureConfig {

    @Bean
    public Clock applicationClock() {
        return Clock.systemUTC();
    }
}
```

A Groovy script can declare beans that use another dependency or reference a bean already registered by Java:

```groovy
import com.example.account.AccountService
import com.example.account.AccountRepositoryImpl

beans {
    accountRepository(AccountRepositoryImpl)

    accountService(AccountService) {
        repository = ref('accountRepository')
    }
}
```

Register both sources before refresh:

```java
import org.springframework.beans.factory.annotation.AnnotatedBeanDefinitionReader;
import org.springframework.beans.factory.groovy.GroovyBeanDefinitionReader;
import org.springframework.context.support.GenericApplicationContext;

try (var context = new GenericApplicationContext()) {
    var annotationReader = new AnnotatedBeanDefinitionReader(context);
    annotationReader.register(InfrastructureConfig.class);

    var groovyReader = new GroovyBeanDefinitionReader(context);
    groovyReader.loadBeanDefinitions("classpath:context/services.groovy");

    context.refresh();

    Clock clock = context.getBean(Clock.class);
    AccountService service = context.getBean(AccountService.class);
}
```

Both readers register bean definitions into the same registry. Consequently, beans declared in Java can be referenced from Groovy and vice versa, provided the bean names, dependency types, and registration order satisfy the configuration requirements. Registering all sources before `refresh()` ensures the context has complete information when instantiating singletons.

If you need to configure multiple sources with complex ordering, make that order explicit in the bootstrap code. Avoid calling `refresh()` partway through and then continuing to load more definitions into an already active context.

## 5. Groovy Runtime and Required Dependencies

Spring includes support for the Groovy bean-definition reader, but to execute Groovy scripts, the application needs a compatible Groovy runtime on the classpath. Having only `spring-context` without the Groovy runtime can cause script loading to fail when Spring needs to compile or evaluate the script.

Gradle example with Groovy 4:

```groovy
dependencies {
    implementation("org.springframework:spring-context")
    runtimeOnly("org.apache.groovy:groovy")
}
```

If Java code directly imports `GenericGroovyApplicationContext` or `GroovyBeanDefinitionReader`, the compiler also needs access to the related Groovy types referenced by those APIs. In that case, configure the Groovy dependency on the compile classpath rather than only the runtime classpath, depending on the Spring/Groovy versions and how dependencies are declared.

With Maven, the Groovy dependency can be declared as follows when the project uses Groovy 4:

```xml
<dependency>
    <groupId>org.apache.groovy</groupId>
    <artifactId>groovy</artifactId>
</dependency>
```

The Groovy version should be managed explicitly using dependency management or an appropriate BOM. Earlier Groovy lines may use a different group id; choose the artifact coordinates matching your project's Groovy version and Spring baseline. Do not arbitrarily mix different Groovy versions on the classpath.

If the application only uses Java configuration and does not load Groovy scripts, there is no need to add the Groovy runtime just because Spring supports the feature.

## 6. Resource Paths and Organizing Configuration Files

A common layout for an application using Groovy configuration:

```text
src/main/resources/
└── context/
    ├── infrastructure.groovy
    ├── persistence.groovy
    ├── services.groovy
    └── application.groovy
```

You can create an aggregate script or individual files to organize beans:

```groovy
beans {
    // Declare the beans belonging to this configuration.
}
```

In Java bootstrap code, load each resource location in an explicit order:

```java
context.load(
        "classpath:context/infrastructure.groovy",
        "classpath:context/persistence.groovy",
        "classpath:context/services.groovy");
context.refresh();
```

Load order can matter when multiple scripts declare the same bean name or when configuration relies on definition overriding. It is best to use unique bean names and make references explicit. Do not use the same bean name across multiple files expecting the later-loaded file to always replace the earlier one, because overriding behavior also depends on bean factory settings and framework version.

### 6.1. Loading Configuration Outside the Artifact

In some systems, Groovy files live outside the JAR/WAR so configuration can be adjusted per environment. In that case, pass the path via startup arguments or environment variables, then construct an appropriate `file:` resource location.

Illustrative example:

```java
String configPath = System.getProperty("app.context.script");
if (configPath == null || configPath.isBlank()) {
    throw new IllegalStateException("Missing app.context.script");
}

try (var context = new GenericGroovyApplicationContext()) {
    context.load("file:" + configPath);
    context.refresh();
    // Run the application with the context
}
```

In real applications, normalize the path into a valid URI rather than concatenating strings arbitrarily, especially when paths contain spaces or special characters. You can create a `FileSystemResource` from a `Path` if you want to avoid manually prepending the prefix.

A Groovy script is executable code when loaded. Therefore, only load scripts from configuration sources that the application trusts and controls. A tampered configuration file can execute arbitrary Groovy logic inside the application process; its security impact is greater than that of a plain data file.

## 7. ApplicationContext Lifecycle When Loading Groovy

The lifecycle must be managed in the right sequence.

### 7.1. Creating the Context

Instantiate the context to obtain a bean definition registry and bean factory. With `GenericGroovyApplicationContext`, the Groovy reader is built in for loading scripts.

### 7.2. Loading Bean Definitions

Call `load(...)` or use `GroovyBeanDefinitionReader` to read the script. During this phase, Spring parses the script and registers definitions. If the script has syntax errors, imported classes cannot be found, or bean declarations are invalid, errors occur during loading.

### 7.3. Refreshing the Context

`refresh()` triggers context finalization: preparing the bean factory, running bean factory post-processors, registering bean post-processors, instantiating eager singletons, handling lifecycle callbacks, and publishing the refresh event.

Some errors only surface at this stage, such as:

- A referenced bean is not found.
- No matching constructor or setter exists.
- Placeholders or dependencies cannot be resolved.
- A bean post-processor or factory method fails.
- Bean initialization throws an exception.

### 7.4. Using and Closing the Context

After a successful refresh, the application can retrieve beans, publish events, and use services in the context. When the application shuts down, close the context so Spring calls destroy callbacks and releases resources managed by beans.

Do not create and refresh a new `ApplicationContext` for every request. A context is normally created once for the application's lifetime or once per isolated test scope.

## 8. Testing Groovy Script Loading

Loading Groovy configuration should be verified with a small test using dedicated test resources. The test can verify that the script is found, beans are registered, dependencies are injected, and bean behavior matches configuration.

### 8.1. Creating a Groovy Script in Test Resources

Example file `src/test/resources/context/test-services.groovy`:

```groovy
import com.example.greeting.GreetingService

beans {
    greetingService(GreetingService) {
        prefix = 'Hello'
    }
}
```

Java class:

```java
package com.example.greeting;

public class GreetingService {

    private String prefix;

    public void setPrefix(String prefix) {
        this.prefix = prefix;
    }

    public String greet(String name) {
        return prefix + ", " + name;
    }
}
```

### 8.2. JUnit Test Loading the Context

```java
import org.junit.jupiter.api.Test;
import org.springframework.context.support.GenericGroovyApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class GroovyApplicationContextTest {

    @Test
    void loadsBeanDefinitionsFromGroovyScript() {
        try (var context = new GenericGroovyApplicationContext()) {
            context.load("classpath:context/test-services.groovy");
            context.refresh();

            GreetingService service = context.getBean(GreetingService.class);

            assertNotNull(service);
            assertEquals("Hello, Spring", service.greet("Spring"));
        }
    }
}
```

This test checks resource lookup, DSL parsing, bean definition registration, bean instantiation, and property injection. Using `try-with-resources` guarantees the context is closed even if an assertion fails.

### 8.3. Testing Bean References Between Definitions

A test script can declare two beans referencing each other:

```groovy
beans {
    greetingFormatter(GreetingFormatter) {
        prefix = 'Welcome'
    }

    greetingService(GreetingService) {
        formatter = ref('greetingFormatter')
    }
}
```

The test should retrieve `GreetingService`, invoke its public behavior, and verify the result uses the formatter. If you need to verify dependency identity, you can check that the injected bean is the same instance as the bean named `greetingFormatter`, though behavioral assertions are preferable when identity is not part of the application contract.

### 8.4. Testing Script Loading Errors

Useful error cases to verify at the configuration level:

- Resource location does not exist.
- Script has Groovy syntax errors.
- Bean class is not on the classpath.
- Bean reference points to a nonexistent name.
- Property cannot be assigned or constructor is incompatible.
- Dependency cycle cannot be resolved under the current container configuration.

Depending on the error, exceptions may be thrown during `load()` or `refresh()`. Tests should assert the exception type at an appropriate level and key cause details, avoiding tight coupling to entire internal error messages that may change across Spring/Groovy versions.

## 9. Using Groovy Scripts in Spring TestContext Testing

Spring TestContext can load Groovy bean-definition scripts through `@ContextConfiguration`. When the Groovy runtime is on the classpath and the specified resource is a `.groovy` file, Spring TestContext's default loader can select the appropriate Groovy reader mechanism.

Example:

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;

@ExtendWith(SpringExtension.class)
@ContextConfiguration(locations = "classpath:context/test-services.groovy")
class GreetingServiceGroovyContextTest {

    @Autowired
    private GreetingService greetingService;

    @Test
    void loadsBeanFromGroovyContextConfiguration() {
        assertEquals("Hello, Spring", greetingService.greet("Spring"));
    }
}
```

Here Spring TestContext manages context caching and lifecycle for the test class. The script must be on the test classpath, and the Groovy runtime must be present for Spring to read the script. You can use `@SpringJUnitConfig` when you want to combine `SpringExtension` registration with context configuration in a shorthand form; `@ContextConfiguration` remains where resource locations are specified.

When you need to load scripts programmatically, control the order of multiple readers, or test the bootstrap process itself in isolation, use `GenericGroovyApplicationContext` inside the test as in the earlier example. When you want to leverage TestContext caching, dependency injection into the test instance, and Spring Test listeners/callbacks, declaring the Groovy resource via `@ContextConfiguration` is the right approach.

Do not confuse `@TestPropertySource` with Groovy bean-definition scripts. `@TestPropertySource` supplies property values to the Environment; it does not read a Groovy `beans {}` script to register bean definitions.

## 10. Comparing Groovy Configuration with XML and Java Configuration

| Configuration Style | Characteristics | Best Fit |
|---|---|---|
| XML | Declares beans with XML elements and attributes; familiar in legacy systems | Applications with existing XML configuration or legacy compatibility needs |
| Java configuration | Uses `@Configuration`, `@Bean`, component scanning, and type-safe Java | Modern Java applications needing compiler checks and safe refactoring |
| Groovy bean DSL | Uses Groovy scripts and `beans {}` to declare beans | Projects with Groovy runtime needing flexible configuration or already using Groovy DSL |

The Groovy DSL is concise and expresses configurations with many properties/references cleanly. However, scripts are still executable code and do not offer the same level of static type checking as Java configuration in all cases. Consider maintainability, debugging, the Groovy runtime dependency, and team familiarity.

The Groovy bean DSL is also not the same as writing a Groovy class annotated with `@Configuration`. An annotated Groovy class can be processed via Java annotation configuration; whereas a `beans {}` script is read by `GroovyBeanDefinitionReader`. Both can coexist, but they are two distinct forms of configuration.

## 11. Common Mistakes When Loading Groovy Scripts

**Missing Groovy runtime.** Spring finds the reader class but cannot execute the script because the Groovy runtime is missing from the classpath or incompatible. Check the dependency tree and Groovy version.

**Wrong resource path.** The script sits in `src/main/resources` but the path does not match the classpath after building. Use `classpath:context/services.groovy` and verify the file is packaged into output resources.

**Forgetting to call `refresh()`.** Bean definitions are registered, but the context has not been activated yet. Call `refresh()` after loading all configuration sources.

**Calling `refresh()` too early.** If refreshed before loading all scripts or Java configurations, eager beans may be created while the registry is still incomplete. Load all sources first and then refresh.

**Using a string instead of a bean reference.** `repository = 'accountRepository'` assigns a String; use `repository = ref('accountRepository')` to reference a bean.

**Declaring duplicate bean names.** Multiple scripts registering the same bean name cause conflicts or depend on overriding policies. Use clear names and control load order.

**Class not found in script.** Classes to be imported must be on the classpath when the Groovy script is compiled/executed. Check packages, class names, and dependencies.

**Not closing the context properly.** Failing to close the context can leave threads, connection pools, or bean resources open. Use `close()` or `try-with-resources` in code that owns the context.

**Assuming Groovy scripts are safe data files.** Scripts are executed inside the process. Only load files from trusted sources with controlled write permissions.

## 12. Workflow for Loading Groovy Scripts in an Application

When setting up an `ApplicationContext` that uses Groovy bean definitions, you can follow this sequence:

1. Determine whether Groovy scripts are the primary configuration source or a supplement.
2. Place scripts in classpath resources or explicitly choose a filesystem resource location.
3. Ensure a compatible Groovy runtime is on the compile/runtime classpath for the APIs being used.
4. Declare beans inside `beans {}` with clear names, classes, properties, and bean references.
5. Create a `GenericGroovyApplicationContext` or an appropriate `GenericApplicationContext`.
6. Load all Groovy resources before refreshing; if mixing Java configuration, register all readers into the same registry.
7. Call `refresh()` exactly once after finishing definition registration.
8. Retrieve beans via `getBean()` and use public interfaces/behaviors.
9. Close the context according to its lifecycle to destroy beans and release resources.
10. Write tests loading scripts from `src/test/resources` to protect resource paths, bean definitions, and dependency wiring.

When these steps are properly organized, Groovy scripts become a fully managed source of bean definitions in Spring. `GenericGroovyApplicationContext` is a convenient choice for applications using Groovy configuration; `GroovyBeanDefinitionReader` fits when combining Groovy with other configuration sources. Both feed bean definitions into the same `ApplicationContext` lifecycle, so resource loading, refreshing, and closing the context must be managed as part of application bootstrap.
