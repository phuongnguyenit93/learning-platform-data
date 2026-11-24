# Avoiding Broad Package Scanning or Heavy Work in Configuration Classes

## 1. Goal

Spring Boot automatically discovers components and auto-configures much of the infrastructure. This mechanism reduces boilerplate, yet package scan scope and the contents of configuration classes directly affect the startup process.

Two sources of cost to control:

- **Overly broad package scanning:** Spring must inspect more classes than necessary, generate extra candidates, potentially register unintended beans, and make the context harder to understand.
- **Heavy work in configuration:** constructors, static initializers, factory methods, or initialization callbacks may make network calls, query databases, read many files, or run heavy computations. Those tasks prolong ApplicationContext refresh and make startup depend on external systems.

This lesson shows how to choose bounded package scans, organize auto-configurations using imports and @Import, keep factory methods lightweight, defer bean instantiation when appropriate, place work in the right lifecycle phase, and measure startup to confirm results.

Examples use **Spring Boot 3.5.16, Spring Framework 6.2, and Java 17+**.

## 2. Startup Consists of Multiple Phases

A Spring Boot startup typically performs the following work:

~~~text
SpringApplication.run(...)
          |
          v
Read Environment and Config Data
          |
          v
Parse configuration classes
          |
          v
Component scan and discover auto-configuration candidates
          |
          v
Evaluate conditions, create bean definitions
          |
          v
Instantiate singleton beans and dependency graph
          |
          v
Lifecycle callbacks
          |
          v
ApplicationRunner / CommandLineRunner
          |
          v
ApplicationReadyEvent and READY state
~~~

| Phase | Potential Costs | Control Direction |
| --- | --- | --- |
| Component scan | Reading metadata of many classes, processing many candidates | Narrow base packages and filters |
| Configuration parsing | Many configuration classes, nested imports, complex conditions | Split configurations by responsibility, explicit imports |
| Bean definition | Many beans, many conditions and dependencies | Register only genuinely needed beans |
| Bean instantiation | Constructors, factory methods, cascading dependency instantiation | Keep factory methods lightweight, use lazy/provider purposefully |
| Initialization callbacks | @PostConstruct, InitializingBean, SmartInitializingSingleton | Do not put I/O or long tasks inside callbacks |
| Runner | Initializing data, calling external services before READY | Set timeouts, control ordering and readiness |

Broad package scanning primarily increases candidate discovery and processing work. Heavy constructors or factory methods increase bean instantiation time. Both issues can occur together but must be addressed at the right phase.

Do not optimize by intuition. Record startup times, identify the slow phase, and measure again after changes.

## 3. Why Is Overly Broad Component Scanning Costly?

@SpringBootApplication combines application configuration, auto-configuration, and component scanning. If no package is specified, component scanning starts from the package containing the annotated class and descends into subpackages.

Example:

~~~text
com.example.orders
├── OrdersApplication.java
├── web
│   ├── OrderController.java
│   └── HealthController.java
├── service
│   └── OrderService.java
├── persistence
│   └── OrderRepository.java
├── integration
│   └── PaymentGateway.java
└── configuration
    └── OrdersConfiguration.java
~~~

If OrdersApplication sits in com.example.orders, the default scan scope typically fits the application's subpackages.

Conversely, placing the main class in a very high-level package such as com can expand the scan scope across more modules or libraries than necessary.

### 3.1. Avoid the Default Package

The default package is the package of a class without a package declaration.

Example to avoid:

~~~java
@SpringBootApplication
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Spring Boot warns that the default package can cause annotations such as @ComponentScan, @ConfigurationPropertiesScan, @EntityScan, and @SpringBootApplication to read classes from every JAR on the classpath.

Use a reverse-domain convention package, for example:

~~~java
package com.example.orders;
~~~

### 3.2. Place the Main Class in the Application Root Package

Common structure:

~~~text
com.example.orders
├── OrdersApplication.java
├── customer
│   ├── CustomerController.java
│   ├── CustomerService.java
│   └── CustomerRepository.java
└── order
    ├── OrderController.java
    ├── OrderService.java
    └── OrderRepository.java
~~~

Declaration:

~~~java
package com.example.orders;

@SpringBootApplication
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

This allows the default scan scope to cover the application package without listing every subpackage.

## 4. Limiting Component Scanning with Marker Classes

When an application has multiple modules and you only want to scan certain packages, use the scanBasePackageClasses attribute.

~~~java
package com.example.orders;

import com.example.orders.application.ApplicationComponents;
import com.example.orders.web.WebComponents;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(
        scanBasePackageClasses = {
                ApplicationComponents.class,
                WebComponents.class
        })
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Create a marker class in each package:

~~~java
package com.example.orders.application;

public final class ApplicationComponents {

    private ApplicationComponents() {
    }
}
~~~

~~~java
package com.example.orders.web;

public final class WebComponents {

    private WebComponents() {
    }
}
~~~

Spring scans the packages containing the marker classes and their subpackages.

Benefits:
- Type-safe: IDEs/compilers assist when refactoring packages.
- No need to write package names as strings.
- Easy to see which packages are scanned.
- Marker classes do not need to contain business logic.

### 4.1. scanBasePackageClasses Only Controls Component Scanning

scanBasePackageClasses is an alias for @ComponentScan base packages. It does not automatically control scanning for JPA entities or Spring Data repositories.

If entity and repository packages sit outside the default scope, configure them separately:

~~~java
@SpringBootApplication(
        scanBasePackageClasses = {
                ApplicationComponents.class,
                WebComponents.class
        })
@EntityScan(basePackageClasses = OrderEntityMarker.class)
@EnableJpaRepositories(basePackageClasses = OrderRepositoryMarker.class)
public class OrdersApplication {
}
~~~

| Annotation | Scope |
| --- | --- |
| @ComponentScan | Components such as @Component, @Service, @Controller, @Configuration |
| @EntityScan | JPA entity packages |
| @EnableJpaRepositories | Spring Data JPA repository packages |

Do not widen component scanning just to find entities or repositories. Use the dedicated mechanism for each type.

## 5. Auto-Configuration Does Not Need to Component-Scan Library Packages

Spring Boot auto-configurations are discovered through separate imports. In Spring Boot 3.x, libraries register auto-configurations in:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Example contents:

~~~text
com.example.catalog.autoconfigure.CatalogAutoConfiguration
~~~

There is no need to add @ComponentScan("com.example.catalog") just for Spring to find the library's configuration classes.

Use @Import for necessary configuration classes:

~~~java
@AutoConfiguration
@Import({
        CatalogClientConfiguration.class,
        CatalogMetricsConfiguration.class
})
public class CatalogAutoConfiguration {
}
~~~

Each configuration declares the beans within its responsibility:

~~~java
@Configuration(proxyBeanMethods = false)
class CatalogClientConfiguration {

    @Bean
    @ConditionalOnMissingBean
    CatalogClient catalogClient(CatalogProperties properties) {
        return new CatalogClient(properties.getEndpoint());
    }
}
~~~

Because @AutoConfiguration always uses proxyBeanMethods = false, do not call another @Bean method directly as a Java method to obtain a bean. Declare dependencies via method parameters:

~~~java
@Bean
CatalogService catalogService(CatalogClient catalogClient) {
    return new CatalogService(catalogClient);
}
~~~

### 5.1. Avoid Broad Component Scanning in Starters

Do not write:

~~~java
@AutoConfiguration
@ComponentScan("com.example")
public class ExampleAutoConfiguration {
}
~~~

This scope can scan components owned by the consuming application, creating duplicate beans or pulling unrelated configurations into the context.

If an auto-configuration needs a few internal configurations, use @Import. If an integration is only needed when the corresponding library is on the classpath, isolate it with a nested configuration and condition:

~~~java
@AutoConfiguration
public class ExampleAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(ExampleTransport.class)
    static class TransportConfiguration {

        @Bean
        @ConditionalOnMissingBean
        ExampleTransport exampleTransport() {
            return new ExampleTransport();
        }
    }
}
~~~

Do not allow an optional class to be directly referenced in a configuration without a guarding condition if that dependency may be absent.

## 6. Configuration Classes Should Declare Configuration, Not Execute Business Logic

A configuration class's job is to describe bean definitions and dependencies. It is not the right place to:
- Call HTTP APIs or open sockets.
- Query a database to load initial data.
- Read and parse thousands of files.
- Scan directories or the classpath with custom logic.
- Run manual migrations outside dedicated mechanisms.
- Wait on external services with unbounded retry loops.
- Launch unmanaged threads.
- Perform heavy computations solely to decide how to create a bean.

Such tasks can slow down context refresh or cause it to fail due to external system outages.

### 6.1. Keep Constructors and Static Initializers Lightweight

Do not place I/O or heavy computation inside configuration class constructors or static initializers. Configuration classes can be loaded and processed during configuration parsing, before business beans are created.

Constructors should only store dependencies or establish necessary local state.

### 6.2. @Bean Methods Should Only Create and Wire Objects

Bad example:

~~~java
@Bean
CatalogClient catalogClient() throws Exception {
    CatalogClient client = new CatalogClient();

    // Connect to external service right during bean creation.
    client.connect();
    client.downloadAllCatalogItems();
    client.rebuildLocalIndex();

    return client;
}
~~~

If the remote API is slow, the database is under maintenance, or the data is huge, application startup will be prolonged.

Better example:

~~~java
@Bean
@ConditionalOnMissingBean
CatalogClient catalogClient(CatalogProperties properties) {
    return new CatalogClient(
            properties.getEndpoint(),
            properties.getTimeout());
}
~~~

The factory method only constructs the object from configuration. Making network calls, loading data, or executing queries happens when the application actually needs the client.

This does not mean every constructor is free. Check third-party libraries: a constructor may start a connection pool or perform discovery on its own. If so, consider appropriate factory/lifecycle APIs from that library.

## 7. Pass Dependencies via Parameters Instead of Calling @Bean Methods Directly

A configuration class can contain multiple bean methods:

~~~java
@Configuration(proxyBeanMethods = false)
class CatalogConfiguration {

    @Bean
    CatalogClient catalogClient(CatalogProperties properties) {
        return new CatalogClient(properties.getEndpoint());
    }

    @Bean
    CatalogService catalogService(CatalogClient catalogClient) {
        return new CatalogService(catalogClient);
    }
}
~~~

The dependency is expressed via the parameter of catalogService.

Do not write:

~~~java
@Bean
CatalogService catalogService() {
    return new CatalogService(catalogClient(new CatalogProperties()));
}
~~~

The code above invokes the factory method directly and creates a properties object itself. It bypasses dependency injection, can create unintended instances, and fails to respect bean lifecycle or replacement beans provided by the application.

In @Configuration(proxyBeanMethods = false) and @AutoConfiguration, direct calls between @Bean methods are not proxied to look up the bean in the container. Use method parameters or constructor injection.

## 8. Deferring Instantiation of Expensive Beans

If a bean is not needed immediately when the application starts, consider @Lazy and ObjectProvider.

### 8.1. Using @Lazy on a Specific Bean

~~~java
@Bean
@Lazy
@ConditionalOnMissingBean
CatalogClient catalogClient(CatalogProperties properties) {
    return new CatalogClient(properties.getEndpoint());
}
~~~

The bean is created upon access request rather than being instantiated immediately during the default singleton creation phase.

Suitable when the bean is only used in rare flows, is expensive to instantiate, and initialization errors occurring on first use are acceptable.

### 8.2. Using ObjectProvider to Express Conditional Access

~~~java
@Component
public class CatalogFacade {

    private final ObjectProvider<CatalogClient> catalogClients;

    public CatalogFacade(ObjectProvider<CatalogClient> catalogClients) {
        this.catalogClients = catalogClients;
    }

    public URI getEndpoint() {
        CatalogClient client = this.catalogClients.getObject();
        return client.getEndpoint();
    }
}
~~~

Injecting ObjectProvider<CatalogClient> does not force Spring to create CatalogClient immediately. The bean is requested when code calls getObject().

| Method | Behavior |
| --- | --- |
| getObject() | Retrieves the bean; throws an exception if not found or ambiguous |
| getIfAvailable() | Returns the bean if present, otherwise returns null |
| getIfUnique() | Returns the bean if only one matching candidate exists |
| orderedStream() | Retrieves matching beans in Spring order |

Do not call getObject() inside the component's constructor if the goal is to defer bean creation.

### 8.3. Application-Wide Lazy Initialization

Spring Boot supports:

~~~properties
spring.main.lazy-initialization=true
~~~

When enabled, beans are created on demand instead of all during startup. This can reduce startup time, but carries trade-offs:
- Configuration errors may only appear on the first request or task.
- The first access may be slower.
- Memory must still be sufficient for all beans once they are instantiated.
- Critical beans may go unverified until traffic arrives.

Prefer deferring specific beans with clear justification. Enable application-wide lazy initialization only after measuring startup and testing initialization failures.

## 9. Placing Heavy Work in the Right Lifecycle Phase

There are tasks that must run when the application starts, such as schema checks, validating required configuration, or initializing essential local data.

If work must finish before the application serves traffic, you can use ApplicationRunner or CommandLineRunner:

~~~java
@Component
public class CatalogStartupCheck implements ApplicationRunner {

    private final CatalogHealthClient healthClient;

    public CatalogStartupCheck(CatalogHealthClient healthClient) {
        this.healthClient = healthClient;
    }

    @Override
    public void run(ApplicationArguments args) {
        this.healthClient.verifyWithTimeout(Duration.ofSeconds(3));
    }
}
~~~

This is an illustrative example; verifyWithTimeout must be implemented with a finite timeout and proper error handling.

Runners are invoked after SpringApplication has started the context but before SpringApplication.run(...) completes. Thus they fit tasks that must run before traffic, though their execution time still affects when the application becomes READY.

If multiple runners require ordering, use Ordered or @Order. Do not rely on source file declaration order.

### 9.1. Work Not Required Before Traffic

If cache loading or data synchronization can run after the application is ready:
- Use a Spring-managed TaskExecutor.
- Set timeouts and retry limits.
- Include logging, metrics, and completion status.
- Handle task failure or re-execution cases.
- Manage shutdown so resources are not left dangling.
- If traffic depends on warm-up results, represent that dependency through readiness.

Do not spawn threads manually with new Thread() inside a @Bean method and leave them unmanaged. Threads need lifecycle, exception handling, resource limits, and a shutdown mechanism.

### 9.2. Do Not Use @PostConstruct for Long Tasks

@PostConstruct, InitializingBean.afterPropertiesSet(), and initialization callbacks run during bean creation. Putting HTTP calls, database scans, or large processing here still blocks startup.

Use initialization callbacks for short local state checks. Move business tasks with significant runtime to runners or appropriate background workflows.

## 10. Runnable Example: Bounded Package Scan and Lazy-Initialized Client

The following example is a minimal Spring Boot application:
- Main application limits component scanning with a marker class.
- Auto-configuration is discovered from AutoConfiguration.imports.
- Properties are explicitly registered.
- The default client is marked lazy.
- Component receives only ObjectProvider and does not create the client in its constructor.
- Runner prints a line confirming the client has not been requested yet.

### 10.1. Project Structure

~~~text
scan-and-startup-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/demo/
        │   ├── DemoApplication.java
        │   ├── components/
        │   │   ├── ComponentsPackage.java
        │   │   ├── CatalogFacade.java
        │   │   └── StartupReporter.java
        │   ├── catalog/
        │   │   ├── CatalogClient.java
        │   │   └── CatalogProperties.java
        │   └── autoconfigure/
        │       └── CatalogAutoConfiguration.java
        └── resources/
            ├── application.properties
            └── META-INF/spring/
                └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

### 10.2. Maven Configuration

File pom.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>scan-and-startup-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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
~~~

### 10.3. Main Application and Marker Package

File DemoApplication.java:

~~~java
package com.example.demo;

import com.example.demo.components.ComponentsPackage;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;

@SpringBootApplication(scanBasePackageClasses = ComponentsPackage.class)
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(DemoApplication.class);

        application.setApplicationStartup(
                new BufferingApplicationStartup(2048));

        application.run(args);
    }
}
~~~

File components/ComponentsPackage.java:

~~~java
package com.example.demo.components;

public final class ComponentsPackage {

    private ComponentsPackage() {
    }
}
~~~

Component scanning targets only package com.example.demo.components and its subpackages. The main class remains the application's primary source; auto-configuration is handled through a separate mechanism.

### 10.4. Properties Class

File catalog/CatalogProperties.java:

~~~java
package com.example.demo.catalog;

import java.net.URI;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo.catalog")
public class CatalogProperties {

    private URI endpoint = URI.create("https://catalog.example.test");

    public URI getEndpoint() {
        return this.endpoint;
    }

    public void setEndpoint(URI endpoint) {
        this.endpoint = endpoint;
    }
}
~~~

### 10.5. Client with Lightweight Constructor

File catalog/CatalogClient.java:

~~~java
package com.example.demo.catalog;

import java.net.URI;

public final class CatalogClient {

    private final URI endpoint;

    public CatalogClient(URI endpoint) {
        this.endpoint = endpoint;
    }

    public URI getEndpoint() {
        return this.endpoint;
    }
}
~~~

The client only holds the configured endpoint. The constructor makes no network calls, opens no databases, and loads no catalogs.

In a real application, the methods that perform HTTP requests or read data are where I/O happens, with proper timeouts and error handling.

### 10.6. Auto-Configuration Registering a Lazy Bean

File autoconfigure/CatalogAutoConfiguration.java:

~~~java
package com.example.demo.autoconfigure;

import com.example.demo.catalog.CatalogClient;
import com.example.demo.catalog.CatalogProperties;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Lazy;

@AutoConfiguration
@EnableConfigurationProperties(CatalogProperties.class)
public class CatalogAutoConfiguration {

    @Bean
    @Lazy
    @ConditionalOnMissingBean(CatalogClient.class)
    CatalogClient catalogClient(CatalogProperties properties) {
        return new CatalogClient(properties.getEndpoint());
    }
}
~~~

File src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports:

~~~text
com.example.demo.autoconfigure.CatalogAutoConfiguration
~~~

Auto-configuration does not need component scanning. Spring Boot discovers it via the imports file.

### 10.7. Component Accepting ObjectProvider

File components/CatalogFacade.java:

~~~java
package com.example.demo.components;

import java.net.URI;

import com.example.demo.catalog.CatalogClient;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Component;

@Component
public class CatalogFacade {

    private final ObjectProvider<CatalogClient> catalogClients;

    public CatalogFacade(ObjectProvider<CatalogClient> catalogClients) {
        this.catalogClients = catalogClients;
    }

    public URI getEndpoint() {
        CatalogClient client = this.catalogClients.getObject();
        return client.getEndpoint();
    }
}
~~~

When CatalogFacade is created, Spring only injects ObjectProvider. The client has not been requested yet. When a business flow calls getEndpoint(), getObject() requests the bean.

### 10.8. Runner That Does Not Request the Client

File components/StartupReporter.java:

~~~java
package com.example.demo.components;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class StartupReporter implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(
                "ApplicationRunner ran; CatalogClient has not been requested.");
    }
}
~~~

File application.properties may contain:

~~~properties
demo.catalog.endpoint=https://catalog.internal.example
~~~

### 10.9. Running the Application

~~~bash
mvn spring-boot:run
~~~

Output line printed by the application itself:

~~~text
ApplicationRunner ran; CatalogClient has not been requested.
~~~

Other Spring Boot startup logs still appear. In this example, StartupReporter does not call CatalogFacade.getEndpoint(), so the lazy CatalogClient has not been requested yet.

When a business component calls:

~~~java
URI endpoint = catalogFacade.getEndpoint();
~~~

only then does Spring create CatalogClient if it does not already exist.

This example illustrates deferring bean instantiation. It does not substitute for deferring network connections: if a real client constructor actually opens a socket or initializes a pool, that cost occurs when the bean is first created. Good design still requires keeping constructors lightweight and performing I/O only on explicit usage operations.

## 11. Spring AOT and Native Image Compatibility

Spring AOT inspects the ApplicationContext at build time to generate the necessary initialization code, bytecode, and runtime hints. The goal is to shift part of configuration discovery and processing work from runtime to build time.

This helps startup and GraalVM native images, while also imposing constraints.

### 11.1. The Bean Graph Must Be Determinable at Build Time

With AOT/native image:
- The classpath is fixed and determined at build time.
- The bean graph cannot change arbitrarily at runtime.
- Profiles and properties affecting whether a bean is created must be selected appropriately at build time.
- Conditions such as @ConditionalOnProperty cannot be used to change the bean graph arbitrarily after AOT has generated code.
- Some dynamic bean registration patterns using instance suppliers or direct singleton registration cannot be AOT-transformed like standard bean definitions.

Prefer:
- Explicit @Configuration and @AutoConfiguration.
- @Bean methods with exact return types.
- @Import for known configurations.
- Conditions with clear contracts.
- Bean definitions declared via standard Spring mechanisms.

Avoid using BeanFactory.registerSingleton(...) at runtime to add beans that AOT cannot know ahead of time.

### 11.2. RuntimeHints for Reflection and Resources

Native image needs to know in advance about dynamic activities such as reflection, reading resources by runtime-constructed names, serialization, and creating JDK proxies.

Spring infers many hints from code and annotations, but libraries may still need to supplement them.

Example of a library reading schemas from the classpath by pattern:

~~~java
package com.example.demo.autoconfigure;

import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class CatalogRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.resources().registerPattern("catalog/schemas/*.json");
    }
}
~~~

Register hints near the component that needs them:

~~~java
@AutoConfiguration
@ImportRuntimeHints(CatalogRuntimeHints.class)
public class CatalogAutoConfiguration {
}
~~~

Declare a resource pattern only when code actually needs to load those files at runtime. Do not register blanket resource or reflection hints unnecessarily.

You can test hints with RuntimeHintsPredicates to confirm required resources, reflection, or proxies are declared.

### 11.3. Avoid Dynamic Scanning and Runtime Bean-Graph-Changing Conditions

An application relying on a fixed package scan can still participate in AOT. The key is that scan scope should be stable and tailored to the application.

Avoid:
- Building package names dynamically from environment and scanning arbitrarily.
- Discovering arbitrary classes on the classpath and manually registering beans at runtime.
- Registering singletons directly into the bean factory after the context is created.
- Using property conditions expecting a native image to alter its bean graph after build.
- Declaring beans with overly generic types preventing AOT from determining the actual type.

AOT does not forbid all reflection or component scanning. Use supported Spring APIs, declare hints for dynamic behavior the framework cannot infer, and test AOT/native artifacts with appropriate tests.

## 12. Measuring and Analyzing Startup

Spring Boot provides ApplicationStartup to record startup steps. Example:

~~~java
SpringApplication application =
        new SpringApplication(DemoApplication.class);

application.setApplicationStartup(
        new BufferingApplicationStartup(2048));

application.run(args);
~~~

If the application has Actuator, you can configure the startup endpoint to view recorded steps. The endpoint must be exposed according to the application's governance policy.

Another option is Java Flight Recorder:

~~~bash
java -XX:StartFlightRecording:filename=startup.jfr,duration=30s -jar target/my-app.jar
~~~

JFR helps observe class loading, thread activity, CPU hot spots, allocation, and garbage collection.

### 12.1. Verified Optimization Process

1. Record baseline startup time in the same environment.
2. Enable BufferingApplicationStartup or JFR.
3. Identify the slow phase: scan, configuration parsing, bean creation, or runner.
4. Check package scans and bean candidate counts.
5. Find constructors, @Bean methods, @PostConstruct, and runners with I/O or long processing.
6. Change only one group of causes per iteration.
7. Re-run with the same profile, classpath, JVM options, and data.
8. Compare startup time, readiness time, and first-access latency.
9. Check for deferred configuration errors when using lazy initialization.
10. Run AOT/native builds and smoke tests if the application targets those deployment formats.

Do not measure only time to the Started log. For traffic-serving systems, also observe readiness time and first-request response time.

## 13. Solution Selection Table

| Issue | Preferred Solution | Things to Note |
| --- | --- | --- |
| Main class in too high a package | Move to root package or limit scan with marker classes | Check entity/repository scans separately |
| Auto-configuration scans library packages | Use @Import and imports file | Do not scan consuming application packages |
| Properties classes scanned too broadly | Use @EnableConfigurationProperties or limit @ConfigurationPropertiesScan | Register the exact properties types needed |
| @Bean method calls external API | Move I/O to usage operations or explicit lifecycle | Include timeouts and error handling |
| Bean used only in certain flows | @Lazy and/or ObjectProvider | Test failures on first access |
| Many unnecessary beans created at startup | Consider lazy initialization | Re-measure memory and first-request latency |
| Tasks required before traffic | ApplicationRunner or CommandLineRunner | Runners extend time to READY |
| Warm-up not required before traffic | Managed executor/lifecycle | Include readiness, logging, metrics, and shutdown |
| Native image missing resources/reflection | RuntimeHintsRegistrar and @ImportRuntimeHints | Register only genuinely needed hints |

## 14. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Placing main class in the default package | Scan may read classes from every JAR | Use a reverse-domain package |
| Placing main class in com or overly high vendor package | Scans many modules outside application scope | Choose the application's root package |
| Using @ComponentScan("com") | Overly broad scan scope and easy unintended beans | Use marker classes or specific packages |
| Using scanBasePackageClasses to find JPA entities | Entity scanning is not controlled by this attribute | Use @EntityScan |
| Using component scan in a starter to find auto-configurations | Scans consuming application packages too | Register via AutoConfiguration.imports |
| Making HTTP calls in configuration constructor | Context startup depends on external network | Separate I/O from configuration |
| Querying DB in @Bean method | Slow startup or failure when DB is not ready | Use lightweight beans and proper lifecycle |
| Putting heavy work in @PostConstruct | Bean creation is blocked | Use runners or background workflows |
| Enabling global lazy initialization without testing | Init errors appear late, first request is slow | Prefer lazy on specific beans |
| Directly injecting a heavy bean even though used occasionally | Dependency may be created as soon as the component is created | Use ObjectProvider |
| Using proxyBeanMethods=false but calling @Bean method directly | Can create new instances outside the container | Inject dependencies via parameters |
| Creating threads with new Thread() in configuration | Hard to manage errors and shutdown | Use Spring-managed executor/lifecycle |
| Dynamically registering beans with registerSingleton when using AOT | Bean graph is hard to process at build time | Declare standard bean definitions |
| Omitting runtime hints for dynamic resources/reflection | Native image may lack needed resources or accessible members | Register hints and test |
| Measuring only time to Started log | Misses runners and first-request latency | Measure both READY and first request |

## 15. Checklist Before Finalizing an Auto-Configuration

### Packages and Scanning

- [ ] Main application sits in a reverse-domain package in a reasonable location.
- [ ] No classes live in the default package.
- [ ] Component scan has a well-bounded scope.
- [ ] Marker classes are used when clear scan boundaries are needed.
- [ ] Entities and repositories have separate scan configurations when needed.
- [ ] Auto-configurations are registered via the imports file.
- [ ] No broad @ComponentScan in starters.

### Configuration and Lifecycle

- [ ] Constructors and static initializers perform no I/O or heavy processing.
- [ ] @Bean methods primarily create objects and wire dependencies.
- [ ] Dependencies are passed via constructors or method parameters.
- [ ] No direct calls to @Bean methods when configuration uses proxyBeanMethods=false.
- [ ] Tasks required before traffic have timeouts and clear ordering.
- [ ] Background tasks use managed executors/lifecycles.
- [ ] Lazy initialization is enabled only with justification and has been tested.

### AOT and Startup Measurement

- [ ] Bean graph can be determined at build time.
- [ ] No dynamic singleton registrations that AOT cannot process.
- [ ] Return types of @Bean methods are sufficiently specific.
- [ ] Runtime hints are declared for needed reflection/resources/proxies.
- [ ] Startup baseline and post-optimization measurements exist.
- [ ] Readiness time and first-request latency have been checked.
- [ ] Native image or AOT artifact has been smoke-tested if it is a deployment target.

## 16. Self-Check Questions

**Question 1.** Why can the default package cause Spring Boot to scan too broadly?

**Answer:** Because scan annotations may have to read classes from every JAR on the classpath when there is no root package bounding the scope.

**Question 2.** How does scanBasePackageClasses differ from scanBasePackages?

**Answer:** Both specify packages for component scanning. scanBasePackageClasses uses marker classes, making it more type-safe than package name strings.

**Question 3.** Does scanBasePackageClasses control JPA entity and repository scanning?

**Answer:** No. Use @EntityScan and @EnableJpaRepositories for those scopes.

**Question 4.** Why should a starter's auto-configuration use @Import instead of broad component scanning?

**Answer:** @Import brings the exact needed configuration classes into the context, avoiding scanning components of the consuming application or unrelated packages.

**Question 5.** Why should you avoid making HTTP calls in a @Bean method?

**Answer:** Factory methods run during bean creation; network I/O can prolong or fail context startup when external services are unavailable.

**Question 6.** How does ObjectProvider<T> help defer instantiation?

**Answer:** A component can accept the provider without yet requesting bean T. The bean is only retrieved when code calls getObject().

**Question 7.** Does ApplicationRunner run after the application is completely READY?

**Answer:** No. Runners are invoked before SpringApplication.run(...) completes and can affect when the application becomes ready to receive traffic.

**Question 8.** Why can lazy initialization cause errors to surface late?

**Answer:** Beans are not created during startup. If bean configuration is invalid, errors only appear when the bean is first accessed.

**Question 9.** What does AOT require regarding bean creation conditions?

**Answer:** The bean graph must be determinable at build time. Profiles and properties affecting bean existence must match the configuration used for AOT processing.

**Question 10.** When are RuntimeHints needed?

**Answer:** When an application or library has dynamic behavior that the framework cannot infer, such as reflection, pattern-based resource loading, serialization, or JDK proxies.

## 17. Official References

- Spring Boot 3.5 — Structuring Your Code: https://docs.spring.io/spring-boot/3.5/reference/using/structuring-your-code.html
- Spring Boot 3.5 API — SpringBootApplication: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/SpringBootApplication.html
- Spring Boot 3.5 API — AutoConfiguration: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html
- Spring Boot 3.5 Reference — SpringApplication, lazy initialization, runners, and startup tracking: https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html
- Spring Boot 3.5 Reference — Configuration Classes: https://docs.spring.io/spring-boot/3.5/reference/using/configuration-classes.html
- Spring Framework 6.2 — Using the Configuration annotation: https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/configuration-annotation.html
- Spring Framework 6.2 — Composing Java-based Configurations: https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/composing-configuration-classes.html
- Spring Boot 3.5 — Ahead-of-Time Processing With the JVM: https://docs.spring.io/spring-boot/3.5/reference/packaging/aot.html
- Spring Boot 3.5 — Introducing GraalVM Native Images and Spring AOT: https://docs.spring.io/spring-boot/3.5/reference/packaging/native-image/introducing-graalvm-native-images.html
- Spring Boot 3.5 — Advanced Native Images Topics and Runtime Hints: https://docs.spring.io/spring-boot/3.5/reference/packaging/native-image/advanced-topics.html
