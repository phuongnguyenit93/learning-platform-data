# Cost of Candidate Discovery, Metadata Reading, Condition Evaluation, and Bean Instantiation

> **Spring Boot Auto Configuration → Performance and AOT.** This lesson analyzes startup costs by phase: discovering auto-configuration candidates, reading metadata, evaluating conditions, registering bean definitions, and instantiating beans. We will use the metadata processor to early-filter unsuitable configurations, measure startup with ApplicationStartup/Actuator, and distinguish standard runtime optimizations from Spring AOT and GraalVM Native Image. Hands-on examples use Java 17+, Maven, and Spring Boot 3.3.13.

## 1. The Big Picture: Where Does Auto-Configuration Spend Time?

When an application calls `SpringApplication.run(...)`, Spring Boot prepares the Environment, creates the ApplicationContext, loads configurations, registers bean definitions, instantiates eager singletons, runs lifecycle callbacks, and finally invokes ApplicationRunner/CommandLineRunner. Auto-configuration participates in the configuration processing and bean definition registration parts of that process.

The auto-configuration-related portion can be divided into five phases:

~~~text
Classpath and Environment
        |
        v
1. Candidate discovery
   Read AutoConfiguration.imports from JARs
        |
        v
2. Filtering and reading metadata
   Exclusions, ordering, spring-autoconfigure-metadata
        |
        v
3. Condition evaluation
   Classpath, property, bean, resource, web application...
        |
        v
4. Bean definition registration
   Configuration classes, @Bean methods, imports
        |
        v
5. Bean instantiation
   Constructor/factory method, dependency graph,
   BeanPostProcessor, lifecycle, resource connections
        |
        v
ApplicationReadyEvent
~~~

This is an analytical model, not five fixed-duration steps or an absolute detailed order for every callback. Spring can process multiple configuration classes according to import relationships and ordering; beans are created according to the dependency graph.

| Phase | Work | Common Sources of Cost |
| --- | --- | --- |
| Candidate discovery | Find and read auto-configuration lists on the classpath | Number of JARs, number of imports resources, number of candidates |
| Reading/filtering metadata | Exclude candidates early when conditions can be checked from metadata | Reading resources, analyzing class metadata, filtering and sorting |
| Condition evaluation | Run conditions on classes and bean methods | Number of conditions, classpath lookup, property lookup, custom conditions |
| Bean definition registration | Parse configurations, import configurations, and create bean definitions | Number of configurations, number of bean definitions, component scan, post-processors |
| Bean instantiation | Create singletons, inject dependencies, run init callbacks | Heavy constructors, I/O, proxies, migrations, network calls, dependency cycles |

**Not every candidate creates a bean.** An auto-configuration can be discovered but excluded by a condition. A configuration can match, yet a bean method can still be blocked by ConditionalOnMissingBean. A bean definition is registered, yet it may only be instantiated when needed if it is lazy.

It is also necessary to distinguish Spring startup time from process/JVM startup time. Class loading, JIT, GC, logging, server startup, and external service calls made by the application itself can all take time outside auto-configuration.

## 2. Candidate Discovery: AutoConfiguration.imports

Spring Boot 3 uses the file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Each line contains the fully qualified name of an auto-configuration class. When an application enables auto-configuration, Boot finds these files on the classpath and merges the candidate list from the JARs.

Example for a library:

~~~text
com.acme.notice.autoconfigure.NoticeAutoConfiguration
com.acme.notice.autoconfigure.NoticeJdbcAutoConfiguration
com.acme.notice.autoconfigure.NoticeMetricsAutoConfiguration
~~~

Candidate discovery is a mechanism for importing published configurations. It is not a component scan across every package of every library. This is why libraries should register the exact necessary auto-configurations in the imports file and avoid using a broad ComponentScan to find additional configurations.

Costs in this phase depend on:
- Number of JARs and imports resources on the classpath.
- Number of declared candidates.
- Number of duplicate or excluded candidates.
- Number of before/after relationships to sort.
- Number of libraries bringing in auto-configurations that the application does not use.

A starter that pulls in many optional integrations can increase the classpath and the number of candidates that must be examined. If a user only needs the core, pulling in JDBC, Kafka, Elasticsearch, metrics, and web integrations can complicate startup work even though most beans end up not being created.

### 2.1. Do Not Confuse Imports with Component Scan

@SpringBootApplication typically includes @ComponentScan for the application package and its subpackages. Library auto-configurations are discovered via imports metadata.

Libraries should:
- Place auto-configurations in a dedicated package.
- Register classes using AutoConfiguration.imports.
- Use @Import to pull in specific internal configurations when needed.
- Avoid broad component scanning in libraries because it can discover unexpected components and increase the number of bean definitions.

Auto-configurations are ordered using before, after, beforeName, afterName, or corresponding ordering annotations. Ordering only determines bean definition order; it does not determine the creation order of every instance. Instantiation afterward still depends on the dependency graph and @DependsOn.

### 2.2. Optimizing the Candidate Set from the Dependency Graph

Some ways to reduce work right from the start:
- Create a core starter that only pulls in core dependencies.
- Split JDBC, Kafka, JSON, or metrics into separate integrations/starters when they are truly optional.
- Do not declare an auto-configuration for a feature that does not belong to that artifact.
- Avoid duplicate imports or legacy configuration classes still registered after being replaced.
- Exclude unneeded dependencies from the application instead of relying on conditions to eliminate all of their costs.

Splitting modules can reduce the number of candidates and dependencies to process, but you should not split modules just to shave off a few lines in imports. Base the decision on optionality, dependency contracts, and how consumers use the library.

## 3. Metadata: Early Filtering Candidates Before Full Evaluation

Spring Boot provides an annotation processor for auto-configuration. The processor collects certain conditions that can be inferred from class metadata and writes them to:

~~~text
META-INF/spring-autoconfigure-metadata.properties
~~~

When this file is present, Boot can early-filter unsuitable auto-configurations before having to fully process each candidate. This early filtering helps reduce startup time, especially when a library has many auto-configurations.

Three types of metadata are commonly confused:

| File | Role | Does it directly filter auto-configuration candidates? |
| --- | --- | --- |
| META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports | Declares the list of auto-configuration classes | Yes, this is the candidate source |
| META-INF/spring-autoconfigure-metadata.properties | Condition metadata for early filtering of some candidates | Yes, supports eager filtering |
| META-INF/spring-configuration-metadata.json | Describes configuration properties for IDEs, autocomplete, and documentation | No, mainly assists application configurators |

spring-autoconfigure-metadata.properties does not replace the imports file and does not replace full condition evaluation. It only helps Boot skip early those candidates for which metadata has enough information to conclude a non-match. Custom conditions or conditions depending on runtime state still need to be evaluated through the normal mechanism.

### 3.1. Enabling the Annotation Processor in Maven

In the module containing auto-configuration classes, configure spring-boot-autoconfigure-processor in the annotation processor path. Example with Spring Boot 3.3.13 and Maven Compiler Plugin 3.13.0:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <annotationProcessorPaths>
                    <path>
                        <groupId>org.springframework.boot</groupId>
                        <artifactId>spring-boot-autoconfigure-processor</artifactId>
                        <version>3.3.13</version>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

The processor runs at compile time. In a multi-module library, configure it in the module that owns the auto-configurations; there is no need to include the processor in consumers' runtime dependencies.

With Gradle, declare the processor in the annotationProcessor configuration:

~~~groovy
dependencies {
    annotationProcessor "org.springframework.boot:spring-boot-autoconfigure-processor"
}
~~~

### 3.2. Verifying Generated Metadata

After building the auto-configuration module:

~~~bash
mvn clean package
~~~

You can check the file in the output directory:

~~~text
target/classes/META-INF/spring-autoconfigure-metadata.properties
~~~

Or inspect the library JAR:

~~~bash
jar tf target/acme-autoconfigure-1.0.0.jar
~~~

On Windows, you can filter the output:

~~~powershell
jar tf target/acme-autoconfigure-1.0.0.jar | findstr /I spring-autoconfigure-metadata
~~~

On Bash:

~~~bash
jar tf target/acme-autoconfigure-1.0.0.jar | grep spring-autoconfigure-metadata
~~~

When packaged as an executable Boot JAR, application resources may live under BOOT-INF/classes/; whereas a regular library JAR has resources at the JAR root. Make sure to inspect the actual artifact being released.

Do not manually write or edit generated metadata to alter logic. If the file is not generated, check whether the annotation processor ran in the module containing the auto-configurations.

### 3.3. Which Conditions Can Be Early-Filtered?

The processor can collect conditions it recognizes from annotation metadata, such as certain classpath or property conditions. It cannot arbitrarily predict all Java logic inside a custom Condition.

Example:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.acme.optional.OptionalClient")
@ConditionalOnProperty(
        prefix = "acme.notice",
        name = "enabled",
        havingValue = "true"
)
public class NoticeAutoConfiguration {
}
~~~

Explicit annotations allow Boot and the processor to read the configuration intent. If a custom condition queries a database, reads arbitrary files, or makes network calls, the processor cannot turn all of that logic into static metadata.

### 3.4. Do Not Confuse Metadata with Actual Conditions

Metadata supports early filtering; runtime conditions remain the final source of truth. Therefore:
- Do not remove @ConditionalOnClass just because the processor is enabled.
- Do not assume a custom condition will be skipped entirely.
- Do not use metadata as a replacement for testing conditions.
- When upgrading Boot or changing annotations, rebuild and inspect the artifact.
- Do not conclude an application is optimized solely because the metadata file exists; measure startup before/after.

## 4. Cost of Condition Evaluation

After candidates are discovered and early-filtered, Spring Boot evaluates the remaining conditions.

Common conditions:
- @ConditionalOnClass / @ConditionalOnMissingClass: checks the classpath.
- @ConditionalOnProperty: checks the Environment.
- @ConditionalOnBean / @ConditionalOnMissingBean: checks bean definitions known at evaluation time.
- @ConditionalOnResource: checks resources.
- @ConditionalOnWebApplication: checks the application context type.
- Custom Condition: runs logic defined by the library.

A single simple condition is usually very cheap. However, a large number of conditions, complex custom logic, or a very broad classpath can add up to significant cost.

### 4.1. Prefer Fast and Deterministic Conditions

Prefer:
- Checking classes with @ConditionalOnClass.
- Checking feature flags with @ConditionalOnProperty.
- Checking beans with @ConditionalOnBean when needed.
- Separating integrations into nested configurations so conditions exclude the right group of beans.
- Using a custom condition only when standard annotations cannot express the rule.

Avoid custom conditions that do the following:
- Scan thousands of classes or packages on every evaluation.
- Read and parse large files when only a single property is needed.
- Open database or HTTP connections.
- Wait for network responses.
- Create a secondary ApplicationContext.
- Call getBean() to instantiate an object solely to decide whether to register a bean.
- Repeat the same expensive computation across multiple configurations without reason.

A condition should answer questions about configuration and environment quickly, repeatably, and without side effects.

### 4.2. Place Conditions at the Appropriate Scope

If a whole group of beans needs the same dependency, place the condition on a nested configuration:

~~~java
@AutoConfiguration
public class NoticeAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.acme.jdbc.NoticeJdbcAdapter")
    static class JdbcConfiguration {

        @Bean
        @ConditionalOnMissingBean
        NoticeHistoryWriter noticeHistoryWriter() {
            return new NoticeHistoryWriter();
        }
    }
}
~~~

If only a single bean needs its own condition, place the condition on the factory method. Avoid overly broad conditions that cause an optional integration to accidentally block other independent beans.

### 4.3. Be Careful with SpEL Conditions Referencing Beans

@ConditionalOnExpression is useful for simple expressions, but referencing a bean inside the expression can cause that bean to be instantiated very early during refresh. At that point, the bean may not yet have been fully processed by BeanPostProcessors, such as configuration properties binding or proxies.

If you only need to check a property, use @ConditionalOnProperty. If you need a bean dependency, use @ConditionalOnBean or @ConditionalOnMissingBean at the right stage. Do not use SpEL to invoke a bean solely to compute a configuration condition.

### 4.4. Bean Conditions Depend on Definition Order

@ConditionalOnBean and @ConditionalOnMissingBean evaluate bean definitions processed up to that point. Therefore:
- Auto-configuration should be loaded after user-declared bean definitions.
- Use @AutoConfiguration(after = ...) when an auto-configuration depends on bean definitions from another configuration.
- Place the condition on the bean method if only that factory method needs the dependency.
- Declare the @Bean return type as specifically as possible so conditions see the exact bean type.

Auto-configuration ordering controls bean definition registration order. It does not guarantee that beans are instantiated in the same order.

## 5. Bean Definition Registration and Bean Instantiation Are Two Different Costs

When a configuration class is processed, Spring registers bean definitions. A bean definition describes:
- Bean class or factory method.
- Scope.
- Constructor/factory method arguments.
- Dependencies.
- Lazy/eager behavior.
- Init and destroy callbacks.
- Metadata for injection and post-processing.

Registering a definition does not equate to creating an instance. A context can have hundreds of bean definitions while only a subset are instantiated if they are lazy or not yet requested.

By default, non-lazy singletons are typically instantiated during refresh. When instantiating a bean, Spring may have to:
1. Create the bean's dependencies.
2. Select a constructor or factory method.
3. Perform dependency injection.
4. Apply BeanPostProcessors.
5. Create proxies if needed.
6. Invoke initialization callbacks such as @PostConstruct or InitializingBean.
7. Execute application-written initialization work.

This is where a small constructor can lead to a large startup time if it opens connections, runs migrations, downloads schemas, makes HTTP calls, or waits for an external service.

### 5.1. Keep Constructors and Factory Methods Lightweight

Example of what not to do:

~~~java
@Bean
RemoteCatalog remoteCatalog() {
    RemoteCatalog catalog = new RemoteCatalog();
    catalog.connectToRemoteServer();
    catalog.downloadAllSchemas();
    catalog.warmUpEveryCache();
    return catalog;
}
~~~

On every context refresh, these operations can prolong startup and tie the application directly to external service latency.

Better design:
- Constructors should only assign required dependencies and state.
- Use explicit timeouts for I/O.
- Load the minimal data needed for readiness.
- Separate optional warm-up from bean creation.
- Use caches or pre-prepared resources where appropriate.
- If initializing asynchronously, only mark the application ready after required capabilities are ready.

Do not offload all work to the background just to shrink the startup number. If the application receives traffic before a required dependency is ready, failures will shift from startup to the first request.

### 5.2. Lazy Initialization Only Defers Instance Creation

You can mark a bean lazy:

~~~java
@Bean
@Lazy
ExpensiveReportClient expensiveReportClient() {
    return new ExpensiveReportClient();
}
~~~

Or enable lazy initialization application-wide:

~~~properties
spring.main.lazy-initialization=true
~~~

Lazy can reduce refresh time because unrequested beans will not be created yet. However, it does not eliminate:
- Candidate discovery.
- Reading imports metadata.
- Condition evaluation.
- Bean definition registration.
- The cost when the bean is used for the first time.

Trade-offs:
- Startup may be faster.
- The first request using the bean may be slower.
- Configuration or connection errors may only surface when the bean is called.
- A bean thought to be unused at startup may be required immediately on the first request.

Use lazy for rarely used beans or optional work. Keep components eager when early validation is needed for readiness to be meaningful.

### 5.3. Do Not Confuse Lazy with Ordering

@AutoConfigureBefore and @AutoConfigureAfter order the bean definition phase of auto-configurations. @DependsOn affects initialization order between beans. @Lazy defers instance creation.

These three mechanisms solve three different problems. Do not use ordering to hide a missing dependency, do not use @DependsOn for every bean, and do not use lazy to mask a required initialization failure.

## 6. Optimization Strategies by Phase

| Phase | What to Do | What to Avoid |
| --- | --- | --- |
| Candidate discovery | Minimal starters, split optional integrations, accurate imports | Pulling every integration into every application |
| Metadata | Enable spring-boot-autoconfigure-processor in auto-config modules | Assuming every custom condition is early-filtered |
| Condition | Standard, fast conditions placed at the right scope | I/O, broad classpath scanning, or instantiating beans inside conditions |
| Bean definitions | Small configurations, specific @Import, exact return types | Broad component scanning and duplicate definitions |
| Bean creation | Lightweight constructors, timeouts, selective lazy, reduced I/O | Network calls without timeouts, uncontrolled migrations/warm-up |
| Measurement | ApplicationStartup, Actuator startup, JFR | Optimizing based on intuition or a single measurement |

The sensible sequence is to measure first, identify the phase taking the most time, fix the biggest cause, and then measure again under the same conditions. Do not optimize candidate count if most of the time is spent in a database migration or a bean making an HTTP call that takes several seconds.

## 7. Measuring Startup with ApplicationStartup and Actuator

Spring Framework provides ApplicationStartup and StartupStep to record steps in the Spring lifecycle. Spring Boot provides BufferingApplicationStartup, which retains steps along with timestamps and durations in a bounded buffer.

To enable recording, create a SpringApplication instead of calling static run(...) directly:

~~~java
package demo.app;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;

@SpringBootApplication
public class StartupDemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(StartupDemoApplication.class);

        application.setApplicationStartup(
                new BufferingApplicationStartup(2048)
        );

        application.run(args);
    }
}
~~~

Capacity 2048 is the limit on buffered steps in this example. If the application produces more steps, new steps may not be recorded once the buffer is full. You can adjust the capacity or filter/drain steps depending on observation goals.

### 7.1. Exposing the Startup Endpoint

Add Actuator and configure:

~~~properties
management.endpoints.web.exposure.include=health,startup
~~~

When SpringApplication uses BufferingApplicationStartup, the startup endpoint can provide JSON data about startup steps.

Fetch a snapshot:

~~~bash
curl http://localhost:8080/actuator/startup
~~~

The endpoint also supports POST to drain recorded steps:

~~~bash
curl -X POST http://localhost:8080/actuator/startup
~~~

The response contains fields such as:
- springBootVersion.
- timeline.startTime.
- timeline.events.
- timeline.events[].duration.
- timeline.events[].startupStep.name.
- timeline.events[].startupStep.tags.

A step may report a name such as spring.beans.instantiate and a beanName tag to identify the bean being created. Step names and counts depend on the Boot version, context type, and application.

**Secure the startup endpoint.** Do not expose this management information publicly if unnecessary. Startup data can reveal bean names, packages, libraries, and internal structure.

### 7.2. Reading the Startup Timeline by Questions

When inspecting the timeline, look for:
- Which step has the longest duration?
- Are many beans of the same type initializing repeatedly?
- Which bean is waiting on I/O or dependencies?
- Is the time spent in Spring context refresh or in application-written runners?
- Is a bean initializing very early when it is not actually needed for readiness?

A long step is not necessarily an auto-configuration bug. For example, spring.beans.instantiate can be long because a bean constructor calls a database. Combine steps with logs, code, and profiling to find the root cause.

### 7.3. Using Java Flight Recorder When JVM-Level Detail Is Needed

BufferingApplicationStartup records Spring steps. It does not replace a profiler for CPU, allocation, GC, class loading, or thread blocking.

You can use JFR when running the application:

~~~bash
java -XX:StartFlightRecording:filename=startup.jfr,duration=10s -jar target/acme-startup-demo-1.0.0.jar
~~~

JFR is useful to:
- Find CPU-consuming methods.
- Inspect class loading.
- Observe GC and allocations.
- Detect blocked threads.
- Correlate JVM events with when Spring creates beans.

Do not draw conclusions from a single measurement. Compare multiple runs under the same JDK, JVM flags, classpath, configuration, hardware, and external dependency state. Record whether it is a cold start or warm start; do not compare two runs with different caches or databases.

## 8. Complete Hands-On Example: Measuring Startup of an Auto-Configuration

The following example creates a small Spring Boot application:
- Auto-configuration is loaded via AutoConfiguration.imports.
- Bean AcmeClient is created when acme.enabled=true.
- The application uses BufferingApplicationStartup.
- Actuator provides the /actuator/startup endpoint.

### 8.1. Directory Structure

~~~text
acme-startup-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   ├── demo/app/
        │   │   ├── StartupDemoApplication.java
        │   │   └── AcmeController.java
        │   └── demo/acme/
        │       ├── AcmeClient.java
        │       └── autoconfigure/
        │           └── AcmeAutoConfiguration.java
        └── resources/
            ├── application.properties
            └── META-INF/spring/
                └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Package demo.acme.autoconfigure sits outside the demo.app scan package. Therefore, the bean from the library is registered via imports metadata, not by component scan accidentally finding the configuration.

### 8.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>demo.acme</groupId>
    <artifactId>acme-startup-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <annotationProcessorPaths>
                        <path>
                            <groupId>org.springframework.boot</groupId>
                            <artifactId>spring-boot-autoconfigure-processor</artifactId>
                            <version>3.3.13</version>
                        </path>
                    </annotationProcessorPaths>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

In a multi-module library project, configure the annotation processor in the autoconfigure module. In this single-module lab, the plugin is configured directly in the project to generate spring-autoconfigure-metadata.properties.

### 8.3. AcmeClient.java

File src/main/java/demo/acme/AcmeClient.java:

~~~java
package demo.acme;

public record AcmeClient(String state) {

    public String status() {
        return "acme:" + state;
    }
}
~~~

The client only holds state so output is predictable. It makes no network calls, so the lab's startup time is not dominated by external services.

### 8.4. AcmeAutoConfiguration.java

File src/main/java/demo/acme/autoconfigure/AcmeAutoConfiguration.java:

~~~java
package demo.acme.autoconfigure;

import demo.acme.AcmeClient;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
public class AcmeAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    AcmeClient acmeClient() {
        return new AcmeClient("ready");
    }
}
~~~

The class-level property condition allows the processor to record an early-filterable condition. ConditionalOnMissingBean preserves the application's ability to replace the default client. AutoConfiguration uses proxyBeanMethods=false by default, suitable for auto-configurations that do not need cross-@Bean method calls through a proxy.

### 8.5. Registering Imports Metadata

File src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports has contents:

~~~text
demo.acme.autoconfigure.AcmeAutoConfiguration
~~~

This is the resource that lets Boot discover the class. spring-autoconfigure-metadata.properties is generated separately by the processor to support early condition filtering.

### 8.6. StartupDemoApplication.java

File src/main/java/demo/app/StartupDemoApplication.java:

~~~java
package demo.app;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;

@SpringBootApplication(scanBasePackages = "demo.app")
public class StartupDemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(StartupDemoApplication.class);

        application.setApplicationStartup(
                new BufferingApplicationStartup(2048)
        );

        application.run(args);
    }
}
~~~

scanBasePackages restricts component scanning to the application package. Because the auto-configuration lies outside this package, it must be loaded via the imports file.

### 8.7. AcmeController.java

File src/main/java/demo/app/AcmeController.java:

~~~java
package demo.app;

import demo.acme.AcmeClient;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AcmeController {

    private final ObjectProvider<AcmeClient> clients;

    public AcmeController(ObjectProvider<AcmeClient> clients) {
        this.clients = clients;
    }

    @GetMapping("/demo")
    public String demo() {
        AcmeClient client =
                clients.getIfAvailable(() -> new AcmeClient("disabled"));

        return client.status();
    }
}
~~~

ObjectProvider allows the endpoint to return a result even when a property disables the auto-configuration. When the feature is enabled by default, the bean from auto-configuration returns acme:ready.

### 8.8. application.properties

File src/main/resources/application.properties:

~~~properties
acme.enabled=true
management.endpoints.web.exposure.include=health,startup
~~~

The startup endpoint requires BufferingApplicationStartup; merely adding the Actuator dependency without configuring an appropriate ApplicationStartup will not produce the expected timeline.

### 8.9. Build and Run

From the directory containing pom.xml:

~~~bash
mvn clean package
java -jar target/acme-startup-demo-1.0.0.jar
~~~

Call the application endpoint:

~~~bash
curl http://localhost:8080/demo
~~~

Response body:

~~~text
acme:ready
~~~

Fetch the startup timeline:

~~~bash
curl http://localhost:8080/actuator/startup
~~~

The response is JSON containing springBootVersion, timeline.startTime, and timeline.events. Duration, event count, and tags depend on the machine, JDK, classpath, and application contents; there is no fixed timing number to copy into a README.

Try disabling the auto-configuration via command line:

~~~bash
java -jar target/acme-startup-demo-1.0.0.jar --acme.enabled=false
~~~

Then call /demo; expected response body:

~~~text
acme:disabled
~~~

This test illustrates that the bean condition responds to the property. It does not prove how much performance improved; to measure, compare the startup timeline in the same environment before and after the change.

## 9. Spring AOT: Shifting Part of the Work to Build Time

Spring AOT (Ahead-of-Time) analyzes the ApplicationContext during the build to produce assets that help runtime start up with pre-processed configuration.

AOT can generate:
- Java source code for restoring bean definitions.
- Bytecode, for example for dynamic proxies.
- RuntimeHints for reflection, resource loading, serialization, and JDK proxies.
- ApplicationContextInitializer to load pre-processed configuration.

During AOT processing, Spring prepares the BeanFactory and processes bean definitions without instantiating all bean instances as in a normal application run. Configuration decisions can be encoded into generated code.

### 9.1. How Does AOT Differ from the Metadata Processor?

| Mechanism | Timing | Target Processed | Effect |
| --- | --- | --- | --- |
| spring-boot-autoconfigure-processor | Library module compile time | Condition annotations on auto-configuration classes | Generates metadata to early-filter unsuitable candidates |
| Spring AOT process-aot | Application build time | ApplicationContext of a specific application | Generates code and hints for the application's bean configuration |
| GraalVM Native Image | Native executable build time | Bytecode and AOT assets | Produces a native executable that can start fast and typically uses less memory than the JVM |

The library processor helps many consumers filter candidates better when running on the JVM. AOT, by contrast, analyzes a specific application with a known classpath and Environment. Native Image is the step that compiles an executable from an application already prepared appropriately for AOT.

AOT is not another name for spring-autoconfigure-metadata.properties; the two mechanisms differ in scope and timing.

### 9.2. Configuring process-aot with Maven

You can add the process-aot execution to the Spring Boot Maven Plugin:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <id>process-aot</id>
            <goals>
                <goal>process-aot</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

During the build, the plugin prepares the ApplicationContext, evaluates conditions in the build environment, and writes generated sources/classes/resources to target/spring-aot/.

With a Maven project using spring-boot-starter-parent, the native profile can help configure AOT/native build steps. GraalVM or appropriate Buildpacks/Native Build Tools are required to create a native image.

Example activating the native profile:

~~~bash
mvn -Pnative package
~~~

Once the JAR contains AOT generated assets, you can run on the JVM with AOT initialization to test the generated code:

~~~bash
java -Dspring.aot.enabled=true -jar target/acme-startup-demo-1.0.0.jar
~~~

The JVM AOT command is only meaningful when the artifact was built with AOT assets. If the JAR has no generated code, enabling the system property will not generate code at runtime.

### 9.3. Conditions Are Evaluated at Build Time

This is the most important limitation when enabling AOT.

Example:

~~~java
@ConditionalOnProperty(
        prefix = "acme",
        name = "enabled",
        havingValue = "true"
)
@Bean
AcmeClient acmeClient() {
    return new AcmeClient("ready");
}
~~~

When process-aot runs, Boot evaluates the condition against the Environment at build time. If acme.enabled=true at build time, the bean is included in the generated configuration. When running AOT, you cannot expect to flip the property to false to remove that bean from the generated configuration.

Key limitations:
- The classpath must be fully determined at build time.
- Profiles affecting bean definitions must be selected at build time.
- Properties affecting bean existence via @Conditional are evaluated at build time.
- Bean definitions should not change arbitrarily at runtime.
- Dynamic singleton registration mechanisms or custom instance suppliers may not be transformed by AOT.
- Bean types should be declared as specifically as possible so AOT knows full metadata.

If two environments require different sets of beans, you can produce two artifacts/builds with the corresponding Environments. Do not build one AOT artifact and expect every bean toggle condition to change freely at runtime.

Properties that only change configuration values on an already-determined bean must be distinguished from properties that determine whether a bean exists or not. AOT limitations focus on decisions affecting bean definitions.

### 9.4. RuntimeHints for Native Image

Native image needs to know in advance about dynamic operations such as reflection, resource reading, serialization, and JDK proxy creation. Spring can infer many cases automatically, but libraries may still need to supply hints.

Example registering resources and reflection:

~~~java
package demo.acme.autoconfigure;

import demo.acme.AcmePayload;

import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class AcmeRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.resources().registerPattern("acme/templates/*.txt");

        hints.reflection().registerType(
                AcmePayload.class,
                MemberCategory.INVOKE_DECLARED_CONSTRUCTORS,
                MemberCategory.INVOKE_PUBLIC_METHODS
        );
    }
}
~~~

Enable the registrar with @ImportRuntimeHints on a configuration:

~~~java
package demo.acme.autoconfigure;

import org.springframework.context.annotation.Configuration;
import org.springframework.aot.hint.annotation.ImportRuntimeHints;

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(AcmeRuntimeHints.class)
class AcmeNativeHintsConfiguration {
}
~~~

This is an illustrative example; AcmePayload must exist in the project if you want to compile the code. Register only the exact members actually invoked via reflection. Excessive hints can bloat the native image and mask unnecessary dynamic design.

You can test hints using RuntimeHintsPredicates rather than waiting until native compilation to discover missing resource or reflection entries.

### 9.5. AOT Does Not Eliminate Bean Creation Cost

Even when using AOT:
- Bean instances still have to be created at runtime.
- Constructors and init callbacks still run.
- Database connections and network calls still incur cost.
- The server still needs to start.
- Caches still need warm-up if required by the application.
- Business code still executes normally.

AOT primarily moves discovery, configuration analysis, and part of the initialization code generation from runtime to build time. It does not turn a 3-second constructor into a zero-cost constructor.

### 9.6. Native Image and JVM AOT Have Different Trade-Offs

Native image typically offers faster startup and a smaller memory footprint than the corresponding JVM, but:
- Building a native image takes more time and resources.
- Reflection/resources/proxies require appropriate hints.
- Some libraries or dynamic patterns are not yet fully compatible.
- Debugging and profiling differ from the JVM.
- You need to test the actual native executable, not only on the JVM.

JVM AOT still runs on the JVM and keeps the JVM ecosystem, while using generated initialization code. Native image compiles into a standalone executable. Measure on real workloads and deployment environments before choosing.

## 10. Reading Results and Choosing the Right Tool

| Symptom | Tool to Use | What to Look For |
| --- | --- | --- |
| Many auto-configuration candidates | Inspect imports and dependency tree | Which JAR contributes unnecessary candidates |
| Candidates evaluated repeatedly | spring-autoconfigure-metadata.properties | Whether the processor generated metadata and can early-filter |
| Slow custom condition | Condition report, logs, and profiler | Which condition performs I/O, scanning, or heavy computation |
| Many bean definitions | Actuator /beans, startup steps | Which configuration or component scan registers too many beans |
| A bean takes long to instantiate | /actuator/startup, JFR | Constructor, init callback, dependencies, or network calls |
| JVM startup still heavy on parse/configuration | AOT processing and AOT JVM run | Whether generated initialization code reduces runtime steps |
| Native image missing class/resource | Native build log, RuntimeHints tests, tracing agent | Undeclared reflection, resources, serialization, or proxies |

Condition Evaluation Report answers why a condition matched or did not match. The startup endpoint answers which step takes time. JFR shows what the JVM is doing at the CPU, allocation, class loading, and GC levels. Do not use a single tool to answer every question.

## 11. A Repeatable Startup Optimization Process

1. Record a baseline using the same JDK, JVM flags, classpath, profile, and deployment configuration.
2. Use BufferingApplicationStartup to collect the timeline.
3. Determine whether time is spent in candidates/conditions, bean creation, server startup, or application runners.
4. Inspect imports and the dependency tree to find unnecessary starters/integrations.
5. Enable the annotation processor in auto-configuration modules.
6. Check which conditions have expensive custom logic or overly broad scope.
7. Identify slow-initializing beans using the timeline and JFR.
8. Make constructors/init callbacks lightweight, add timeouts, and separate optional warm-up.
9. Use lazy only when accepting that cost shifts to first use.
10. Measure again in the same environment and compare step durations.
11. If appropriate for the deployment target, build AOT and run an AOT-processed JVM.
12. If choosing native image, add RuntimeHints and test the native executable.
13. Repeat after each major change to dependencies, Boot version, or integration modules.

When benchmarking, record both total startup and important steps. Do not compare only a single total number; if the total drops while the first request spikes sharply due to lazy initialization, decide based on actual latency goals.

## 12. Common Mistakes When Optimizing Auto-Configuration

1. **Thinking every candidate creates a bean.** A candidate can be excluded by metadata or conditions.
2. **Confusing the imports file with autoconfigure metadata.** One declares candidates; the other supports early condition filtering.
3. **Confusing configuration metadata with autoconfigure metadata.** spring-configuration-metadata.json primarily serves IDEs and property documentation.
4. **Not enabling the annotation processor.** A library may lack early-filter metadata.
5. **Putting the processor in runtime dependencies.** The processor is a compile-time tool, not a runtime application dependency.
6. **Assuming the processor handles every custom condition.** Only conditions the processor can collect from metadata are early-filtered.
7. **Using broad component scans in a library.** It can register unexpected components and increase bean definition count.
8. **Writing custom conditions with I/O.** A condition waiting on a database or HTTP makes configuration slow and hard to reproduce.
9. **Referencing beans in @ConditionalOnExpression.** The bean may be instantiated too early before being fully post-processed.
10. **Using ordering to control instance creation.** Auto-configuration ordering only affects bean definition order.
11. **Putting heavy work in constructors.** Every bean instantiation can prolong refresh.
12. **Making every bean lazy without measuring.** Costs and failures may shift to the first request.
13. **Confusing bean definitions with bean instances.** Having a definition does not mean an instance has been created.
14. **Not measuring runners and startup callbacks.** ApplicationRunner/CommandLineRunner can also extend time before readiness.
15. **Ignoring external I/O.** Database migrations, remote calls, or cache warm-up can dwarf auto-configuration costs.
16. **Measuring only once.** JIT, file cache, database state, and machine load cause measurements to fluctuate.
17. **Comparing two different environments.** Different JDKs, memory, profiles, or dependencies make comparisons unfair.
18. **Assuming AOT still evaluates property conditions at runtime.** Bean-presence conditions are evaluated during AOT build.
19. **Assuming AOT automatically resolves all reflection.** Some dynamic access and resources still require RuntimeHints.
20. **Assuming native image is always suitable.** Build cost, compatibility, and operational workflows must also be weighed.
21. **Not testing the native executable.** JVM tests do not prove a native image has sufficient hints.
22. **Exposing the startup endpoint publicly.** Internal data about beans and startup steps must be protected.
23. **Looking only at total startup.** Inspect steps to know whether time lies in parsing, bean creation, or I/O.
24. **Optimizing without a baseline.** You may complicate code without improving the actual bottleneck.

## 13. Performance and AOT Acceptance Checklist

- [ ] Identified which imports files candidates come from.
- [ ] Imports contain only auto-configurations actually belonging to the artifact.
- [ ] Starter does not pull in unnecessary optional integrations.
- [ ] No broad component scanning is used in the auto-configuration library.
- [ ] spring-boot-autoconfigure-processor is configured in the module containing auto-config.
- [ ] Verified META-INF/spring-autoconfigure-metadata.properties after build.
- [ ] Did not confuse the auto-config metadata file with configuration metadata JSON.
- [ ] Custom conditions do not perform I/O or instantiate beans.
- [ ] Conditions are placed at the right scope: class/nested configuration/bean method.
- [ ] Bean definitions are not registered redundantly.
- [ ] Constructors and init callbacks have no unnecessary heavy work.
- [ ] I/O has timeouts and a clear readiness strategy.
- [ ] Lazy initialization is used selectively and first-use latency has been measured.
- [ ] Startup timeline is recorded using BufferingApplicationStartup.
- [ ] Startup endpoint is exposed only within a secured administrative scope.
- [ ] JFR is used when needing visibility into CPU, allocation, GC, or class loading.
- [ ] Baseline and post-optimization results are measured in the same environment.
- [ ] AOT build uses the correct profile and Environment.
- [ ] Properties/profiles affecting bean presence are fixed at AOT build time.
- [ ] RuntimeHints cover necessary reflection/resources/serialization/proxies.
- [ ] Ran AOT-processed JVM if using AOT.
- [ ] Tested the native executable if deploying Native Image.

## 14. Self-Check Questions

**Question 1.** What is AutoConfiguration.imports used for?  
**Answer:** Declaring the list of auto-configuration classes that Spring Boot can discover from JARs on the classpath.

**Question 2.** How does spring-autoconfigure-metadata.properties differ from the imports file?  
**Answer:** Imports declare candidates; autoconfigure metadata supports early filtering of certain candidates based on conditions collected by the processor.

**Question 3.** Does spring-configuration-metadata.json filter auto-configurations?  
**Answer:** No. It primarily provides metadata for IDEs, autocomplete, and configuration properties documentation.

**Question 4.** Why should you use spring-boot-autoconfigure-processor?  
**Answer:** The processor collects condition metadata at compile time so Boot can eager-filter non-matching auto-configurations, reducing work at startup.

**Question 5.** Does a discovered candidate mean a bean has been created?  
**Answer:** Not yet. A candidate can be excluded by conditions; a configuration can register definitions, while bean instances are only created according to scope, lazy settings, and dependencies.

**Question 6.** Does lazy initialization eliminate condition evaluation?  
**Answer:** No. It defers instance creation; candidate discovery, condition evaluation, and bean-definition registration still occur.

**Question 7.** Which tool is used to view the duration of each Spring startup step?  
**Answer:** Configure BufferingApplicationStartup and read Actuator /actuator/startup; use JFR for deeper JVM-level profiling.

**Question 8.** When does AOT evaluate @ConditionalOnProperty?  
**Answer:** During the AOT build, against the build's Environment. Conditions affecting bean presence cannot be expected to toggle freely at runtime on an AOT artifact.

**Question 9.** Does AOT make heavy constructors free?  
**Answer:** No. Bean instances are still created at runtime; constructors, I/O, and init callbacks still take time.

**Question 10.** What is RuntimeHints used for?  
**Answer:** Providing information to native image about reflection, resource loading, serialization, and JDK proxies that Spring/GraalVM cannot fully infer.

## 15. Official References

- [Spring Boot 3.3.13 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html).
- [Spring Boot 3.3.13 — Ahead-of-Time Processing Maven Plugin](https://docs.spring.io/spring-boot/3.3/maven-plugin/aot.html).
- [Spring Boot 3.3.13 — Application Startup Actuator Endpoint](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/startup.html).
- [Spring Boot 3.3.13 — BufferingApplicationStartup API](https://docs.spring.io/spring-boot/3.3/api/kotlin/spring-boot-project/spring-boot/org.springframework.boot.context.metrics.buffering/-buffering-application-startup/index.html).
- [Spring Boot 3.3.13 — Advanced Native Images Topics and RuntimeHints](https://docs.spring.io/spring-boot/3.3/reference/packaging/native-image/advanced-topics.html).
- [Spring Boot 3.3.13 — GraalVM Native Images](https://docs.spring.io/spring-boot/3.3/reference/packaging/native-image/index.html).
- [Spring Framework — Ahead-of-Time Optimizations](https://docs.spring.io/spring-framework/reference/core/aot.html).