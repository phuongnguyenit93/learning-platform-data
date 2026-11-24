# Tracing an example from dependency to created bean

Spring Boot auto-configuration enables applications to use many components simply by adding dependencies and declaring necessary configuration. When adding a starter such as web, JDBC, or an integration library built by a development team, Spring Boot can discover auto-configuration classes on the classpath, evaluate conditions, and register matching beans into the `ApplicationContext`.

However, this process consists of several distinct steps. **Adding a dependency does not directly create beans**: the dependency puts classes and metadata onto the classpath; auto-configuration is loaded by Spring Boot; conditions are checked; bean definitions are registered; and only then does the container instantiate objects and inject dependencies.

This lesson traces one end-to-end example: an application adds `acme-greeting-spring-boot-starter`, Spring Boot discovers the library's auto-configuration, registers `GreetingClient` if conditions match, and then injects that bean into an application service. Through this example, you will see the connections among build dependencies, metadata, condition evaluation, bean definitions, and bean lifecycle.

The examples target Spring Boot 3.x and Java 17/21. Package names and some internal details may vary across versions, yet the fundamental architectural path remains the same.

## 1. The big picture: from dependency to object

An application using an auto-configuration library goes through this high-level sequence:

~~~mermaid
flowchart TD
    A["Add starter to build"] --> B["Starter and dependencies are on the runtime classpath"]
    B --> C["SpringApplication starts"]
    C --> D["@SpringBootApplication enables auto-configuration"]
    D --> E["Read AutoConfiguration.imports from JARs"]
    E --> F["Filter candidates and evaluate conditions"]
    F --> G["Register matching BeanDefinitions"]
    G --> H["ApplicationContext refreshes"]
    H --> I["Create singleton beans and resolve dependencies"]
    I --> J["GreetingClient becomes a ready-to-use bean"]
    J --> K["Service / Controller receives bean via injection"]
~~~

There are three layers to distinguish:

1. **Build dependencies:** Gradle or Maven puts artifacts and transitive dependencies onto the classpath.
2. **Auto-configuration:** Spring Boot locates auto-configuration classes, evaluates conditions, and registers bean definitions.
3. **Bean lifecycle:** The Spring container creates instances, injects dependencies, invokes initialization callbacks, and manages the lifecycle.

Understanding these three layers lets you diagnose situations like "added the starter yet no bean appears", "bean appears only in this profile", or "default bean was not created because the application declared its own implementation" much more accurately.

## 2. Preparing the example: a Greeting library

Suppose a team develops a shared library for generating greetings. The library provides a plain Java class:

~~~java
package com.acme.greeting;

public class GreetingClient {
    private final String prefix;

    public GreetingClient(String prefix) {
        this.prefix = prefix;
    }

    public String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        return prefix + ", " + name + "!";
    }
}
~~~

This class has no `@Component` or `@Service`. It is just a Java class. When an application uses the library, we want Spring Boot to automatically register it as a bean with matching configuration.

The artifact structure can be split across modules:

~~~text
acme-greeting/
├── acme-greeting-core/
│   └── GreetingClient.java
├── acme-greeting-spring-boot-autoconfigure/
│   ├── GreetingProperties.java
│   ├── GreetingAutoConfiguration.java
│   └── META-INF/spring/
│       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
└── acme-greeting-spring-boot-starter/
    └── build.gradle
~~~

Roles:

- `acme-greeting-core` holds plain Java APIs/logic.
- `acme-greeting-spring-boot-autoconfigure` holds Spring Boot configuration and metadata to register that configuration.
- `acme-greeting-spring-boot-starter` is a convenient dependency that pulls the auto-configuration module and required libraries into the application.

Not every library must have all three modules. For small libraries, core and auto-configuration can be combined. Splitting out a separate starter is helpful when providing a single convenient dependency for library consumers.

## 3. Step 1 — Adding the dependency to the application

Suppose the application uses Gradle and the Spring Boot plugin/dependency management is already configured at the project level:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'com.acme:acme-greeting-spring-boot-starter:1.0.0'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Or if developing multi-project modules in the same repository:

~~~groovy
dependencies {
    implementation project(':acme-greeting-spring-boot-starter')
}
~~~

The starter can declare a dependency on the auto-configuration module:

~~~groovy
dependencies {
    api project(':acme-greeting-spring-boot-autoconfigure')
}
~~~

The auto-configuration module in turn depends on core and Spring Boot auto-configuration APIs:

~~~groovy
dependencies {
    implementation project(':acme-greeting-core')
    implementation 'org.springframework.boot:spring-boot-autoconfigure'
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

The build snippets above illustrate dependency relationships only. In a real project, Spring Boot versions, Java toolchain, plugins, and dependency management must be aligned according to repository configuration.

### 3.1. What does Gradle do when resolving dependencies?

When building or running the application, Gradle resolves the dependency graph:

~~~mermaid
flowchart TD
    APP["Demo application"] --> WEB["spring-boot-starter-web"]
    APP --> STARTER["acme-greeting-spring-boot-starter"]
    STARTER --> AUTO["acme-greeting-spring-boot-autoconfigure"]
    AUTO --> CORE["acme-greeting-core"]
    AUTO --> BOOTAUTO["spring-boot-autoconfigure"]
~~~

Gradle will:

- Locate artifacts by dependency coordinates.
- Resolve direct and transitive versions.
- Place required classes/resources onto the compile/runtime classpath.
- Ensure related modules are built according to the dependency graph.

After this step, the `GreetingAutoConfiguration` class and its metadata file can be present on the application's runtime classpath.

**What has NOT happened yet:** Gradle does not instantiate `GreetingClient` and does not register beans into the `ApplicationContext`. The build system only prepares artifacts so the application can use them when running.

### 3.2. How does a starter differ from an auto-configuration library?

| Component | Responsibility |
| --- | --- |
| Starter | Convenient dependency entry point aggregating required modules |
| Auto-configuration module | Provides automatic configuration classes and metadata |
| Core/library module | Provides classes and logic that beans will use |
| Consuming application | Provides properties, custom beans, and the runnable entry point |

A starter does not have to contain Java code. Many starters are simply an artifact declaring dependencies in build metadata.

## 4. Step 2 — The application enables auto-configuration

Main runnable class:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

`@SpringBootApplication` is a composite annotation, commonly understood through three main parts:

- `@SpringBootConfiguration`: marks the application's primary configuration source.
- `@EnableAutoConfiguration`: turns on Spring Boot's auto-configuration mechanism.
- `@ComponentScan`: scans components from the application class's package and subpackages by default configuration.

In this lesson, `@EnableAutoConfiguration` is the starting point for the path from dependency to bean.

### 4.1. What does @EnableAutoConfiguration do?

`@EnableAutoConfiguration` uses Spring's import mechanism to bring `AutoConfigurationImportSelector` into configuration processing.

Conceptually:

~~~java
@SpringBootApplication
public class DemoApplication {
}
~~~

is equivalent to the application having enabled a configuration carrying the semantics of `@EnableAutoConfiguration`. You do not need to write your own selector or read imports files manually in normal applications.

`AutoConfigurationImportSelector` is a Spring Boot infrastructure component. It finds auto-configuration candidates from metadata on the classpath, applies exclusions/filters, and returns selected configurations for Spring to process.

Do not confuse this with component scanning:

- Component scan discovers component classes such as `@Component`, `@Service`, `@Repository`, and `@Controller` within scanned packages.
- Auto-configuration import discovers configuration classes declared in metadata inside artifacts on the classpath.

An auto-configuration class can reside in a package outside the application's component scan region and still be imported thanks to metadata.

## 5. Step 3 — Registering auto-configuration in metadata

In Spring Boot 3, libraries register auto-configuration classes using the file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Place the file in the auto-configuration module at:

~~~text
acme-greeting-spring-boot-autoconfigure/
└── src/main/resources/
    └── META-INF/
        └── spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

File content:

~~~text
com.acme.greeting.autoconfigure.GreetingAutoConfiguration
~~~

Each line contains the fully qualified name of an auto-configuration class. When the JAR is placed on the runtime classpath, Spring Boot can read this list to discover candidates.

### 5.1. Why is the metadata file important?

Suppose the module has the class:

~~~java
package com.acme.greeting.autoconfigure;

@AutoConfiguration
public class GreetingAutoConfiguration {
}
~~~

Simply writing `@AutoConfiguration` does not automatically guarantee Spring Boot will discover the class from a library JAR. It still needs to be registered into the candidate import mechanism, typically via `AutoConfiguration.imports`.

This is the distinction from component scan: you do not need to put the auto-configuration class in a subpackage of `DemoApplication` when metadata is registered properly.

### 5.2. Boot 3 and spring.factories

In older Spring Boot versions, auto-configurations were usually registered in `META-INF/spring.factories` under the `EnableAutoConfiguration` key. Spring Boot 2.7 was a transition period, whereas for auto-configurations written for Boot 3, use `AutoConfiguration.imports`.

`spring.factories` is still used for some other extension points. Do not assume every capability previously registered in that file has disappeared; this change refers specifically to listing auto-configuration candidates.

## 6. Step 4 — Spring Boot reads candidates and evaluates conditions

Having an auto-configuration does not mean every bean inside it is always registered. Spring Boot uses conditions so configurations activate only when the environment fits.

Three very common conditions:

| Annotation | Question checked |
| --- | --- |
| `@ConditionalOnClass` | Is the required class on the classpath? |
| `@ConditionalOnProperty` | Does the property exist or have a matching value? |
| `@ConditionalOnMissingBean` | Has a bean already been provided by the application or another configuration? |

Other conditions include `@ConditionalOnBean`, `@ConditionalOnResource`, `@ConditionalOnWebApplication`, and `@ConditionalOnSingleCandidate`.

### 6.1. ConditionalOnClass

For example, an integration that only makes sense when an optional SDK is on the classpath:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.sdk.GreetingSdk")
public class VendorGreetingAutoConfiguration {
    // Configuration appropriate only when the SDK is present.
}
~~~

Using the `name` attribute lets you express the class name as a string, useful when the optional class is not present when compiling the configuration module.

If the auto-configuration directly references optional types in method signatures or fields, place that configuration appropriately so the JVM is not forced to load missing types before the condition excludes it. A common pattern is isolating optional configurations into static nested configurations marked with conditions.

### 6.2. ConditionalOnProperty

For example, enabling an integration only when configured by the user:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.greeting",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
public class GreetingAutoConfiguration {
}
~~~

Meaning:

- The full property is `acme.greeting.enabled`.
- If the value is `true`, the condition matches.
- If the property is not declared, `matchIfMissing = true` allows enabling by default.
- If the property is set to `false`, the condition does not match.

If you want the integration disabled by default, you can use `matchIfMissing = false` or require the property explicitly. Choose a clear default and document it in the starter's documentation.

### 6.3. ConditionalOnMissingBean

Auto-configuration typically supplies a default bean while letting the application replace it:

~~~java
@Bean
@ConditionalOnMissingBean(GreetingClient.class)
GreetingClient greetingClient(GreetingProperties properties) {
    return new GreetingClient(properties.getPrefix());
}
~~~

If the application has already registered a matching `GreetingClient` bean, this default bean is not registered. This is an important extension point: the library offers default behavior, while the application retains customization control.

`@ConditionalOnMissingBean` does not delete user beans and does not replace already-registered beans. It only decides whether the default bean method contributes a bean definition.

## 7. Step 5 — Writing the library's properties configuration

The library wants users to configure the prefix. Create the class:

~~~java
package com.acme.greeting.autoconfigure;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.greeting")
public class GreetingProperties {
    private String prefix = "Hello";

    public String getPrefix() {
        return prefix;
    }

    public void setPrefix(String prefix) {
        this.prefix = prefix;
    }
}
~~~

The class uses `@ConfigurationProperties` to bind the group of properties prefixed with `acme.greeting`.

Application configuration:

~~~yaml
acme:
  greeting:
    enabled: true
    prefix: Xin chào
~~~

Register the properties in auto-configuration using:

~~~java
@EnableConfigurationProperties(GreetingProperties.class)
~~~

When the configuration is processed, Spring Boot registers the properties bean and binds values from the `Environment` into that object.

`GreetingProperties` does not need `@Component` if it is already registered via `@EnableConfigurationProperties` or an appropriate configuration properties scanning mechanism. Avoid registering the same properties type twice through multiple mechanisms unintentionally.

## 8. Step 6 — Creating the auto-configuration class

Now write the auto-configuration class:

~~~java
package com.acme.greeting.autoconfigure;

import com.acme.greeting.GreetingClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@EnableConfigurationProperties(GreetingProperties.class)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "acme.greeting",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true
    )
    @ConditionalOnMissingBean(GreetingClient.class)
    public GreetingClient greetingClient(GreetingProperties properties) {
        return new GreetingClient(properties.getPrefix());
    }
}
~~~

Analysis:

- `@AutoConfiguration` marks the class as a Spring Boot auto-configuration.
- `@EnableConfigurationProperties` registers and binds `GreetingProperties`.
- `@Bean` declares a factory method creating `GreetingClient`.
- `@ConditionalOnProperty` decides whether the bean is enabled per configuration.
- `@ConditionalOnMissingBean` lets the application provide its own bean.
- The `GreetingProperties` parameter is resolved by Spring from the context when calling the factory method.

Note: this example does not need `@ConditionalOnClass(GreetingClient.class)` because `GreetingClient` is a required part of the same core library that the auto-configuration depends on. In an optional integration, classpath conditions should check classes that genuinely come from the optional dependency, rather than adding ceremonial conditions that are always true.

### 8.1. Does an auto-configuration class create beans immediately upon import?

Not necessarily. An auto-configuration class is a configuration brought into bean definition processing. `@Bean` methods contribute bean definitions if their corresponding conditions match.

Definition registration is distinct from object creation. Only during refresh and pre-instantiation does the container create eager singletons as needed, resolve factory method parameters, and execute lifecycle steps.

### 8.2. Conditions on classes vs. conditions on bean methods

A condition placed on the class affects whether that configuration is processed at all. A condition placed on a bean method decides whether that specific bean definition is registered.

For example:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.greeting",
        name = "enabled",
        havingValue = "true"
)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingClient.class)
    GreetingClient greetingClient(GreetingProperties properties) {
        return new GreetingClient(properties.getPrefix());
    }
}
~~~

If the property does not match at the class level, this configuration contributes no bean methods. If the class-level condition matches while the application already has a `GreetingClient` bean, the method-level condition excludes the default bean.

## 9. Step 7 — Spring Boot registers the bean definition

Once an auto-configuration candidate is selected and its conditions match, Spring processes the configuration class as a configuration source.

At this stage, the container registers bean definitions—metadata describing how to create beans:

- What bean type or factory method return type it has.
- What the bean name is.
- Which scope is used.
- What dependencies the factory method has.
- Which initialization/destruction methods are configured.
- Which conditions allowed the bean to be registered.

Example method:

~~~java
@Bean
GreetingClient greetingClient(GreetingProperties properties) {
    return new GreetingClient(properties.getPrefix());
}
~~~

contributes a bean definition whose factory method is `greetingClient`. The default bean name is typically the method name, in this case `greetingClient`.

Distinguish:

| Stage | Result |
| --- | --- |
| Auto-configuration candidate imported | Spring processes configuration |
| Condition matches | Bean method is allowed to contribute a definition |
| Bean definition registered | Container knows how to create the bean |
| Bean instantiated | Actual Java object is created |
| Bean initialization complete | Object is ready for use |

Having a bean definition does not mean the object was created at that exact moment. For non-lazy singletons, Spring typically instantiates early during refresh. For lazy beans or beans requested only at runtime, instances may be created later.

## 10. Step 8 — ApplicationContext refresh and bean creation

After processing configurations, Spring refreshes the context. During this process, non-lazy singletons are pre-instantiated according to the dependency graph and lifecycle rules.

For `GreetingClient`, the factory method needs `GreetingProperties`:

~~~mermaid
flowchart TD
    A["Refresh ApplicationContext"] --> B["Find eager singletons to create"]
    B --> C["Request GreetingClient"]
    C --> D["Resolve GreetingProperties parameter"]
    D --> E["Obtain bound properties bean"]
    E --> F["Call @Bean method greetingClient(...)"]
    F --> G["new GreetingClient(prefix)"]
    G --> H["BeanPostProcessor / initialization"]
    H --> I["GreetingClient ready"]
~~~

Step by step:

1. The container needs to create `GreetingClient`.
2. Spring inspects the factory method and sees it needs `GreetingProperties`.
3. `GreetingProperties` was registered via `@EnableConfigurationProperties`.
4. Spring resolves the properties bean and ensures values are bound from configuration.
5. Spring invokes `greetingClient(properties)`.
6. The method returns the `GreetingClient` instance.
7. The instance passes through appropriate post-processing and lifecycle steps.
8. The bean is stored in the context's singleton registry for consumers to use.

### 10.1. Where does GreetingClient's constructor run?

In the example, the line:

~~~java
return new GreetingClient(properties.getPrefix());
~~~

is where the actual object is constructed. Yet that object is constructed inside a Spring-managed factory method, so the returned result is registered as a bean.

This is a key point: the `GreetingClient` class does not need a stereotype annotation to become a bean. It is managed by Spring because a `@Bean` method returns an instance of it.

### 10.2. BeanPostProcessor and initialization

After the instance is created and dependencies are supplied, Spring applies lifecycle steps such as aware callbacks, BeanPostProcessors, and initialization callbacks per container rules.

If `GreetingClient` had `@PostConstruct`, the callback would run during the appropriate initialization phase. If AOP or a post-processor created a proxy, the final reference exposed to consumers could be a proxy instead of the raw target instance.

This example needs no lifecycle callbacks or proxies, yet the bean management mechanism still applies.

## 11. Step 9 — Consumer receives the bean via constructor injection

In the demo application:

~~~java
package com.example.demo;

import com.acme.greeting.GreetingClient;
import org.springframework.stereotype.Service;

@Service
public class WelcomeService {
    private final GreetingClient greetingClient;

    public WelcomeService(GreetingClient greetingClient) {
        this.greetingClient = greetingClient;
    }

    public String welcome(String name) {
        return greetingClient.greet(name);
    }
}
~~~

`WelcomeService` is discovered by component scan because it resides in a subpackage of the application class. When Spring creates the service, it needs a `GreetingClient` bean.

That bean was registered by auto-configuration, so constructor injection succeeds.

It can be used in a controller:

~~~java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WelcomeController {
    private final WelcomeService service;

    public WelcomeController(WelcomeService service) {
        this.service = service;
    }

    @GetMapping("/welcome/{name}")
    public String welcome(@PathVariable String name) {
        return service.welcome(name);
    }
}
~~~

With configuration:

~~~yaml
acme:
  greeting:
    enabled: true
    prefix: Xin chào
~~~

the request:

~~~http
GET /welcome/Phuong
~~~

can return:

~~~text
Xin chào, Phuong!
~~~

The complete flow:

~~~mermaid
sequenceDiagram
    participant App as Spring Boot app
    participant Import as AutoConfigurationImportSelector
    participant Auto as GreetingAutoConfiguration
    participant Context as ApplicationContext
    participant Service as WelcomeService
    App->>Import: Start and enable auto-configuration
    Import->>Import: Read AutoConfiguration.imports
    Import->>Auto: Select candidate, evaluate conditions
    Auto->>Context: Register bean definitions
    Context->>Context: Bind GreetingProperties
    Context->>Context: Call greetingClient(properties)
    Context->>Context: Store GreetingClient singleton
    Context->>Service: Inject GreetingClient
    Service-->>App: WelcomeService ready
~~~

## 12. Step 10 — The application can override the default bean

Good auto-configuration supplies a default bean without locking the application into that implementation.

Suppose the application wants to replace `GreetingClient` with a custom implementation. Create the bean:

~~~java
package com.example.demo;

import com.acme.greeting.GreetingClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CustomGreetingConfiguration {

    @Bean
    GreetingClient greetingClient() {
        return new GreetingClient("Welcome");
    }
}
~~~

When Spring evaluates `@ConditionalOnMissingBean(GreetingClient.class)` in the auto-configuration, the application-provided bean takes precedence under normal configuration processing order. The library's default bean is not registered.

Result:

- The application has a customized `GreetingClient` bean.
- Auto-configuration can still be imported.
- The default bean method is skipped because the condition does not match.
- `WelcomeService` still injects by type `GreetingClient` without needing to know where the implementation came from.

This is a key contract of auto-configuration libraries: **provide sensible defaults while respecting the consuming application's configuration**.

### 12.1. @ConditionalOnMissingBean is not @Primary

The two mechanisms differ:

| Mechanism | Effect |
| --- | --- |
| `@ConditionalOnMissingBean` | Do not register default bean if a matching bean already exists |
| `@Primary` | Prefer one bean when multiple beans of the same type already exist |
| `@Qualifier` | Filter bean candidates by metadata at the injection point |

If the application wants to replace the default, `@ConditionalOnMissingBean` fits. If the application wants to keep multiple implementations and mark one as default, `@Primary` may fit. If a consumer needs a specific implementation by role, use a qualifier.

### 12.2. Why does configuration order matter again?

Auto-configuration is designed to be processed after user-declared configurations, allowing conditions like `@ConditionalOnMissingBean` to see bean definitions already contributed by the application.

If an auto-configuration depends on another configuration, `@AutoConfigureAfter`, `@AutoConfigureBefore`, or `@AutoConfigureOrder` can be used to control processing order among auto-configurations.

These annotations order **automatic configurations**, not object instantiation order across the entire container. Do not use `@DependsOn` or `@Order` as substitutes for auto-configuration ordering when the goal is configuration processing order.

## 13. What happens if a condition does not match?

Try setting:

~~~yaml
acme:
  greeting:
    enabled: false
~~~

With `@ConditionalOnProperty` in the example, the default `GreetingClient` bean is not registered.

If `WelcomeService` still requires `GreetingClient` via its constructor, the application may fail during context initialization due to the missing bean.

That does not mean the condition malfunctioned. It means configuration turned off the feature while a consumer still declared a mandatory dependency.

There are three design options depending on the feature's semantics:

1. **Mandatory feature:** do not allow disabling it if consumers require the bean; remove the enable property or validate configuration appropriately.
2. **Optional feature:** consumers must handle the absent-bean case, for example by injecting `ObjectProvider<GreetingClient>` or an optional abstraction.
3. **No-op default:** when the feature is disabled, auto-configuration still registers an implementation that performs no side effects while satisfying the contract.

No-op example:

~~~java
public class DisabledGreetingClient extends GreetingClient {
    public DisabledGreetingClient() {
        super("");
    }

    @Override
    public String greet(String name) {
        return name;
    }
}
~~~

This is only an illustration of a default behavior; in real applications, design an appropriate interface/contract rather than subclassing a concrete class just to work around configuration. The key is that conditions and consumers must share a consistent contract.

## 14. Tracing a built-in Spring Boot auto-configuration

The Greeting example above was a custom library built to show every piece clearly. In real applications, the exact same mechanism powers built-in infrastructure beans.

For example, with JDBC:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.mysql:mysql-connector-j'
}
~~~

The application configures the datasource:

~~~yaml
spring:
  datasource:
    url: jdbc:mysql://localhost:3306/shop
    username: app_user
    password: change-me
~~~

Conceptually:

1. The JDBC starter puts Spring JDBC, an appropriate default connection pool, and related dependencies onto the classpath.
2. The MySQL driver is added to the runtime classpath.
3. `@SpringBootApplication` enables auto-configuration.
4. Spring Boot discovers JDBC/DataSource-related auto-configurations from Spring Boot's metadata.
5. Conditions check JDBC classes, connection factory, datasource type, available pool, and application-provided beans.
6. Matching datasource configuration can register a `DataSource` bean and bind properties from `spring.datasource`.
7. Other auto-configurations such as JDBC template can use the existing `DataSource` bean to provide `JdbcTemplate`.
8. Services can inject `JdbcTemplate` or corresponding repositories.

This describes the architectural path, not an exhaustive list of every condition or implementation branch of a specific Spring Boot version. Exact pool and bean choices depend on dependencies, versions, classpath, and application configuration.

Example service using JDBC:

~~~java
@Repository
public class ProductQuery {
    private final JdbcTemplate jdbcTemplate;

    public ProductQuery(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public int countProducts() {
        return jdbcTemplate.queryForObject(
                "select count(*) from product",
                Integer.class
        );
    }
}
~~~

`JdbcTemplate` does not need to be created manually in the service. When auto-configuration conditions match, Spring Boot can register the bean for the application to inject.

To check the exact auto-configurations of the version in use, inspect the condition report or API documentation for that exact version; do not rely on internal class names from one Boot version as immutable across all versions.

## 15. Diagnosing: why was the bean not created?

When a starter is added yet a bean cannot be injected, check along the path from outside in.

| Symptom | Layer to inspect | Question |
| --- | --- | --- |
| Cannot compile library classes | Build dependencies | Is the artifact on the compile classpath? |
| Compiles yet auto-configuration is unseen | Runtime dependencies/metadata | Is the JAR present at runtime? Is the imports file packaged? |
| Auto-configuration does not appear in report | Candidate discovery/filter/exclusion | Is the class name in imports? Is it excluded or filtered? |
| Auto-configuration found yet does not match | Conditions | Which classpath, property, bean, or web condition failed? |
| Auto-configuration matches yet bean is missing | Bean method conditions | Is another condition excluding the bean method? |
| Default bean does not appear, yet app runs | User override | Did the application already provide a matching bean so missing-bean backed off? |
| Multiple beans of the same type | Dependency resolution | Is a qualifier or primary needed? |
| Bean appears yet dependencies still fail | Bean graph | Is a deeper dependency unregistered? |
| Fails only in one profile | Property/profile sources | What are the effective config values and active profiles? |

### 15.1. Enabling the debug condition report

You can run the application with:

~~~bash
java -jar app.jar --debug
~~~

Or configure debug logging appropriately during development. Spring Boot prints the condition report showing which auto-configurations matched and did not match.

In the report, pay attention to the groups:

- Positive matches: configurations/conditions satisfied.
- Negative matches: configurations excluded and reasons.
- Exclusions: explicitly excluded configurations.
- Unconditional classes: configurations without ordinary conditions.

This is one of the most useful ways to understand why a starter did not create a bean as expected.

### 15.2. Actuator conditions endpoint

If the application has Spring Boot Actuator and the appropriate endpoint is enabled/exposed, `/actuator/conditions` can display the condition evaluation report.

Expose diagnostic endpoints only according to the environment's governance and security policy. Do not expose management endpoints to public networks just for quick debugging.

### 15.3. Checking artifacts and metadata

If auto-configuration is not discovered, inspect the library module's JAR to ensure it contains the resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

and that the class name line has the exact package/casing. The file must sit in the main resource source set to be packaged into the artifact. If it exists only in a test directory or is excluded by the build, consuming applications will not be able to read it.

## 16. Testing auto-configuration with ApplicationContextRunner

Auto-configuration libraries should test conditions with a small context, without starting an entire web application.

Spring Boot provides `ApplicationContextRunner` in test support. For example:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import com.acme.greeting.GreetingClient;
import com.acme.greeting.autoconfigure.GreetingAutoConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class GreetingAutoConfigurationTest {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(GreetingAutoConfiguration.class)
                    );

    @Test
    void createsDefaultClientWhenEnabled() {
        contextRunner
                .withPropertyValues(
                        "acme.greeting.enabled=true",
                        "acme.greeting.prefix=Hello"
                )
                .run(context -> {
                    assertThat(context).hasSingleBean(GreetingClient.class);
                    assertThat(context.getBean(GreetingClient.class).greet("Sam"))
                            .isEqualTo("Hello, Sam!");
                });
    }

    @Test
    void doesNotCreateClientWhenDisabled() {
        contextRunner
                .withPropertyValues("acme.greeting.enabled=false")
                .run(context ->
                        assertThat(context).doesNotHaveBean(GreetingClient.class)
                );
    }
}
~~~

This test loads the auto-configuration class directly via `AutoConfigurations.of`. It verifies conditions and bean factory methods, yet **does not verify that the `AutoConfiguration.imports` file is properly packaged and auto-discovered**.

You can add an integration test using a starter-consuming application or a context booting with real auto-configuration discovery to confirm metadata registration.

### 16.1. Checking that applications can override the bean

Add a user configuration in the test:

~~~java
@Configuration(proxyBeanMethods = false)
static class UserGreetingConfiguration {
    @Bean
    GreetingClient greetingClient() {
        return new GreetingClient("Welcome");
    }
}
~~~

Then load the user configuration alongside the auto-configuration and verify the context contains only the customized bean. This tests `@ConditionalOnMissingBean` behavior.

### 16.2. Checking default properties

Since the example sets `matchIfMissing = true`, also test the case where `acme.greeting.enabled` is not declared. If default behavior changes in the future, this test catches the contract change.

## 17. Auto-configuration ordering and dependency ordering

Some auto-configurations depend on beans or configurations supplied by another auto-configuration. Spring Boot provides annotations:

- `@AutoConfigureBefore`
- `@AutoConfigureAfter`
- `@AutoConfigureOrder`

For example:

~~~java
@AutoConfiguration
@AutoConfigureAfter(DataSourceAutoConfiguration.class)
public class ReportingAutoConfiguration {
    // Configuration processed after DataSourceAutoConfiguration.
}
~~~

They control candidate auto-configuration processing order, helping conditions see bean definitions from related configurations as desired.

Do not confuse with:

- `@DependsOn`: initialization relationships between specific beans.
- `@Order`: priority order within certain collections/extension points.
- `@Primary`: preferring one bean when resolving a single dependency.
- Constructor injection: expressing actual object dependencies.

Use the right mechanism for each kind of relationship. Auto-configuration ordering does not guarantee all singletons are instantiated in a global linear order.

## 18. Component scan and auto-configuration can coexist

In the same application, Spring can find beans through multiple paths:

~~~mermaid
flowchart TD
    A["ApplicationContext"] --> B["Component scanning"]
    A --> C["Auto-configuration imports"]
    A --> D["Java configuration / @Import"]
    B --> E["@Component / @Service / @Repository"]
    C --> F["@AutoConfiguration + @Bean"]
    D --> G["@Configuration + @Bean"]
    E --> H["Bean definitions"]
    F --> H
    G --> H
~~~

For example:

- `WelcomeService` is discovered via component scan.
- `GreetingClient` is registered via auto-configuration.
- A custom `Clock` can be registered from an application configuration class.
- Dependencies are then resolved within the same context.

This is why an auto-configuration class does not have to live in a package scanned by the application's component scan. It is discovered from dedicated metadata.

## 19. Common mistakes when writing starters

### 19.1. Thinking adding a starter scans every class in the JAR

A starter only adds artifacts to the classpath. Auto-configurations must be registered via metadata and conditions must match. A `@Component` class inside a JAR outside scanned packages does not automatically become a bean.

### 19.2. Forgetting the AutoConfiguration.imports file

Having an `@AutoConfiguration` class without metadata prevents Boot from discovering the class from the library via imports. Inspect resources inside the built artifact.

### 19.3. Creating default beans without allowing overrides

If a starter unconditionally registers a bean without `@ConditionalOnMissingBean` while the application needs to swap implementations, multiple beans of the same type and injection ambiguity can result. For library default beans, consider intentional extension points.

### 19.4. Placing conditions at the wrong scope

Placing a condition on the entire auto-configuration class can exclude every bean in the class. Placing a condition on a bean method affects only that bean. Choose the scope fitting the feature.

### 19.5. Using @ConditionalOnMissingBean arbitrarily in regular configurations

This condition works reliably in auto-configuration because application configurations are usually processed before auto-configurations. Scattering it across normal configurations can lead to results depending on confusing processing order.

### 19.6. Using broad component scanning to fix missing beans

Scanning an entire dependency package can pull many unintended components into the context. For libraries designed to integrate with Spring Boot, providing explicit auto-configuration usually gives better control.

### 19.7. Not testing default properties

`matchIfMissing` values, defaults in properties classes, and enable/disable conditions form the contract with starter users. Write tests for both defaults and explicit property branches.

### 19.8. Assuming auto-configuration always runs

Auto-configurations can be excluded with `exclude` on `@EnableAutoConfiguration`/`@SpringBootApplication`, via exclude configuration properties, or eliminated by conditions/filters. If a bean does not appear, read the condition report before editing code.

## 20. Workflow to trace any bean yourself

When you want to understand which starter a bean comes from and how it was created, trace in order:

1. Find where the application declares the direct or transitive dependency.
2. Identify which JAR contains the bean class or auto-configuration class.
3. Inspect the `AutoConfiguration.imports` resource inside the JAR.
4. Locate the registered auto-configuration class.
5. Read conditional annotations on the class and bean methods.
6. Check properties, profiles, classpath, and existing bean definitions.
7. Locate the `@Bean` method creating the object or registered component.
8. Identify dependencies of the factory method/constructor.
9. Inspect the bean definition and lifecycle after context refresh.
10. Use the condition report or context tests to confirm the actual branch taken.

One way to search in a codebase is by the bean type name, then tracing backward from the `@Bean` method or stereotype to the configuration class, metadata, and dependencies. Do not just look for annotations on the class and conclude that is the bean's source; the bean might be returned from a factory method in another module.

## 21. Practice exercises

### Exercise 1 — Tracing the starter

Create three modules: `demo-app`, `demo-greeting-autoconfigure`, and `demo-greeting-starter`. Declare dependencies from app to starter, and from starter to auto-configuration. Verify that the app sees classes from the core module on the runtime classpath.

### Exercise 2 — Registering auto-configuration metadata

Create `GreetingAutoConfiguration` and the `AutoConfiguration.imports` file. Run the application with `@SpringBootApplication` without adding `@Import(GreetingAutoConfiguration.class)`. Confirm the bean is still discovered thanks to metadata.

### Exercise 3 — Observing conditions

Add `@ConditionalOnProperty` for `demo.greeting.enabled`. Run twice with true and false, observing whether the bean appears in the context. Use `--debug` to read the condition report.

### Exercise 4 — Allowing application override

Add `@ConditionalOnMissingBean(GreetingClient.class)`. Create a `GreetingClient` bean from the application's configuration. Confirm that auto-configuration does not register the default bean.

### Exercise 5 — Distinguishing definitions and instances

Log inside the factory method and constructor of `GreetingClient`. Observe when they execute during context refresh. Try marking the bean lazy or requesting the bean only at runtime, and compare with an eager singleton.

### Exercise 6 — Testing with ApplicationContextRunner

Write tests for: default property, disabled property, user-defined bean override, and missing classpath dependency. Confirm each condition creates or omits the bean according to the contract.

## 22. Key takeaways

The path from dependency to bean can be summarized into steps with clear boundaries: Gradle/Maven puts starters and transitive dependencies onto the classpath; `@SpringBootApplication` enables auto-configuration; `AutoConfigurationImportSelector` reads candidates from `AutoConfiguration.imports`; Spring Boot filters and evaluates conditions; matching configurations contribute bean definitions; on context refresh, Spring instantiates objects and resolves dependencies; consumers receive beans via constructor injection.

Starters do not create objects themselves, and component scan is not the only way beans arise. Auto-configuration provides a way to register default beans based on classpath, properties, and existing beans. With `@ConditionalOnMissingBean`, applications can swap default implementations without editing the library. With `@ConditionalOnProperty`, features can be toggled via configuration.

When a bean does not appear, trace build dependencies, metadata, the condition report, bean definitions, and lifecycle in order. Reasoning this way helps you understand not only which bean was created, but why Spring Boot decided to create it in a particular environment.
