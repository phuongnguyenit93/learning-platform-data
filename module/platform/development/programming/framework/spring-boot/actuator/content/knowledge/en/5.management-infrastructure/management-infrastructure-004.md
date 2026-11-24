# Identifying the Management Context and Separate Web Infrastructure When Separating Ports

When configuring Actuator on a different port from the application port, what changes is not just the number in the URL. Spring Boot also organizes a separate **management context** along with web infrastructure serving management.

To diagnose accurately, distinguish four entities: the Java process, the Spring context, the web server, and HTTP mappings. Two ports may use two web servers in two different contexts, yet still reside in one JVM and share certain beans.

This lesson uses **Spring Boot 3.3.13, Spring MVC, Java 21, and Gradle 8.5**, with an embedded web server. Conclusions and hands-on outputs are scoped to the standard auto-configuration mechanism of the sample project.

## 1. Four Concepts to Identify

| Concept | Role |
| --- | --- |
| Java/JVM process | Runs application code, manages process memory and resources |
| `ApplicationContext` | Spring context holding bean definitions, instances, and related services |
| `WebServer` | Object managing the embedded web server and listen port |
| HTTP mapping | Rule routing a request such as `GET /business` to a handler component |

The **management context** is the Spring context serving management configurations. It is not synonymous with an endpoint, a discovery page, or a second Java process.

In Spring Boot, `WebServerApplicationContext` is the interface for a context that manages an embedded web server. You can obtain the server via `getWebServer()` and identify context relationships via `getParent()`. [Web server application context API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/context/WebServerApplicationContext.html)

## 2. When Is a Context Shared, and When Is There a Child Context?

### 2.1. Shared Application and Management Port

Example:

```properties
server.port=8087
```

When no separate management port is set, Actuator HTTP uses the application port. Explicitly setting `management.server.port=8087` when the application port is also `8087` is still a shared layout.

Simplified model of the sample project:

```text
Single JVM
└── Main application context
    └── Web server: 8087
        ├── /business
        └── /actuator/info
```

There is no separate child web management context merely because the Actuator library was added.

### 2.2. Management Port Different From Application Port

```properties
server.port=8087
management.server.port=9087
```

In this layout, Spring Boot creates a separate management context with the main context as its parent:

```text
Single JVM
└── Main application context
    ├── Business beans and application infrastructure
    ├── Main web server: 8087
    │   └── /business
    └── Child management context
        └── Management web server: 9087
            └── /actuator/info
```

The child branch in the diagram represents the parent-child relationship between contexts. It does not mean the main web server forwards individual requests to the management server.

This contract is directly specified in `ManagementContextAutoConfiguration`: same port uses the same context; different port uses a separate context with the main application context as parent. [Management context auto-configuration API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/web/server/ManagementContextAutoConfiguration.html)

## 3. Parent-Child Relationship Determines Bean Lookup

### 3.1. The Child Context Can Look Up Beans in the Parent

If the management context does not have a bean named `sharedMarker` locally, `getBean("sharedMarker")` can walk up to the parent's bean factory.

For a singleton bean owned by the parent and not shadowed by a bean of the same name in the child, both lookups can return **the same instance**. Spring does not need to copy or recreate the bean just because a management context exists.

The usual lookup direction goes from child to parent. The parent context does not automatically search down into every child context to resolve a dependency. If the child has a bean with the same name, lookups from the child may pick the child's bean first. [`BeanFactory` lookup rules](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/beans/factory/BeanFactory.html)

### 3.2. "Found" Differs From "Locally Owned"

Two questions must be separated:

| Check | Question |
| --- | --- |
| `context.containsBean("sharedMarker")` | Can the context find the bean name through the lookup mechanism? |
| `context.containsLocalBean("sharedMarker")` | Does the bean belong to the bean factory of this specific context? |

In the port-separation experiment, the management context can find `sharedMarker`, but `containsLocalBean` returns `false` because the bean is registered in the parent.

Counting or listing beans also requires checking the API contract. Do not assume every listing method automatically includes beans from ancestor contexts. This lesson uses lookup by name and local bean checks to avoid conflating these two scopes.

### 3.3. A Singleton Does Not Mean One Instance Per Entire JVM

In Spring, singleton scope is tied to the bean factory that owns the bean. If you intentionally define a bean of the same type in both parent and child, there can be two distinct instances.

What makes the example share an instance is that **the bean is declared only in the parent and the child looks up to the parent**, not a rule that every bean of the same type in the JVM must share identity.

## 4. A Visible Bean Does Not Guarantee an HTTP Mapping on That Port

A controller may be a bean in the parent context. The child context can find this bean via the hierarchy, but serving `GET /business` also depends on the HTTP mapping and handling components of the management server.

Spring MVC has a mechanism to detect handler methods in a context. The `detectHandlerMethodsInAncestorContexts` flag on `AbstractHandlerMethodMapping` defaults to `false`: handler detection focuses on the current context. [Detecting handlers in ancestor contexts API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/servlet/handler/AbstractHandlerMethodMapping.html#setDetectHandlerMethodsInAncestorContexts(boolean))

Therefore, in the sample configuration:

- The main port serves the `/business` controller.
- The management port serves the Actuator endpoints selected for exposure.
- Being able to resolve the `businessController` bean from the management context does not automatically make `/business` appear on the management port.

This is an essential relationship to remember when reading `404` errors: bean existence and mapped paths are two different pieces of evidence.

Custom web configurations can alter behavior. When an application has custom filters, interceptors, servlets, or MVC configuration, verify the actual registration scope rather than assuming they apply identically to both sides.

## 5. What Is Separated and What Remains Shared

| Component | Interpretation in Standard Separate-Port Layout |
| --- | --- |
| Management context | Separate child context |
| Management web server instance | Different from the main web server instance |
| HTTP port and entry point | Separate according to configuration |
| Web processing components | Organized for the corresponding side's web infrastructure |
| Singleton bean in parent accessed by child via lookup | Can still be the same instance |
| Data pool managed by a bean in the parent | Not automatically duplicated just by separating ports |
| JVM, process memory, CPU, and process termination | Still the same process |

Separating HTTP ingress infrastructure gives management its own access point. It does not create two completely independent systems for failures or resources.

For example, the main server may have trouble accepting new connections while the management server still responds. Conversely, JVM memory exhaustion or process termination affects both. Do not use the word "isolation" without specifying whether you mean the network layer, web infrastructure, or the entire process.

## 6. Identifying the Right Server via Initialization Events

Spring Boot publishes `WebServerInitializedEvent` when a web server is ready. The event provides:

- The context that created the server: `event.getApplicationContext()`.
- The actual server and port: `event.getWebServer().getPort()`.

This is more direct evidence than just reading a port config string. [Web server initialized event API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/context/WebServerInitializedEvent.html)

An easy pitfall is that **events from a child context can propagate to listeners in ancestor contexts**. A listener in the main application can therefore see events belonging to the management server.

If you take the port from every event and overwrite a single `applicationPort` variable, you may mistakenly assign the management port as the main port. You must compare the event's context identity. [Events in a parent-child context hierarchy](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)

The example below stores **a set of observed context instances**, rather than counting listener invocations or relying on event order.

## 7. Complete Hands-On: Observing Contexts, Servers, and Beans

The sample project has one application controller, one shared marker bean, and an infrastructure observation snippet. The observation snippet does not create the management context itself; Spring Boot does that based on port configuration.

Requires JDK 21, Gradle 8.5, and internet connectivity to download dependencies the first time. Ports `8087` and `9087` must be free. The example adds no Spring Security, proxies, custom contexts, or other HTTP mappers.

The outputs stated are **expected results for this exact sample project**.

### 7.1. Project Structure

```text
management-context-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/
    │   ├── ManagementContextApplication.java
    │   └── BusinessController.java
    └── resources/application.properties
```

File `settings.gradle`:

```groovy
rootProject.name = 'management-context-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

### 7.2. Observation Code

File `src/main/java/example/ManagementContextApplication.java`:

```java
package example;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.context.WebServerApplicationContext;
import org.springframework.boot.web.context.WebServerInitializedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ManagementContextApplication {

    public static void main(String[] args) {
        Set<WebServerApplicationContext> observedContexts =
                ConcurrentHashMap.newKeySet();

        SpringApplication application =
                new SpringApplication(ManagementContextApplication.class);

        application.addListeners(
                (ApplicationListener<WebServerInitializedEvent>) event ->
                        observedContexts.add(event.getApplicationContext()));

        WebServerApplicationContext mainContext =
                (WebServerApplicationContext) application.run(args);

        WebServerApplicationContext managementContext = observedContexts.stream()
                .filter(context -> context != mainContext
                        && context.getParent() == mainContext)
                .findFirst()
                .orElse(mainContext);

        boolean separate = managementContext != mainContext;

        Object markerFromMain = mainContext.getBean("sharedMarker");
        Object markerFromManagement =
                managementContext.getBean("sharedMarker");

        System.out.println("WEB_CONTEXTS=" + observedContexts.size());
        System.out.println("SEPARATE_MANAGEMENT_CONTEXT=" + separate);
        System.out.println("MAIN_PORT="
                + mainContext.getWebServer().getPort());
        System.out.println("MANAGEMENT_PORT="
                + managementContext.getWebServer().getPort());
        System.out.println("SAME_WEB_SERVER_INSTANCE="
                + (mainContext.getWebServer()
                        == managementContext.getWebServer()));
        System.out.println("MANAGEMENT_PARENT_IS_MAIN="
                + (separate
                        && managementContext.getParent() == mainContext));
        System.out.println("MANAGEMENT_HAS_LOCAL_MARKER="
                + managementContext.containsLocalBean("sharedMarker"));
        System.out.println("SAME_MARKER_INSTANCE="
                + (markerFromMain == markerFromManagement));
        System.out.println("MANAGEMENT_CAN_RESOLVE_CONTROLLER="
                + managementContext.containsBean("businessController"));
    }

    @Bean
    SharedMarker sharedMarker() {
        return new SharedMarker("owned-by-main");
    }

    public record SharedMarker(String label) {
    }
}
```

How to read the code:

1. The listener is registered before running the application to observe server events.
2. The `observedContexts` set stores contexts by instance; multiple notifications related to the same context are not counted as multiple distinct contexts.
3. After `run` returns, the code knows the exact main context instance.
4. In the sample project there is only one child web context serving management, so it can be identified via `getParent() == mainContext`.
5. If no such child context exists, the observation uses the main context as the shared management side.
6. The code compares both server identity and bean identity, rather than inferring those two facts from port numbers.

This is an observation tool for the minimal layout of this lesson. Applications with multiple child web contexts need additional identification criteria; do not take "first child context" as a universal detector for every architecture.

### 7.3. Controller and Configuration

File `src/main/java/example/BusinessController.java`:

```java
package example;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class BusinessController {

    @GetMapping("/business")
    public String business() {
        return "BUSINESS_OK";
    }
}
```

File `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=8087
spring.jmx.enabled=false

management.endpoints.enabled-by-default=false
management.endpoint.health.enabled=true
management.endpoint.info.enabled=true
management.endpoints.web.exposure.include=health,info
management.endpoints.web.base-path=/actuator
```

Do not set a management port in the initial file so run A shares the context.

### 7.4. Run A: Shared Port and Context

In the project directory:

```powershell
gradle bootJar
java -jar build/libs/management-context-demo-1.0.0.jar
```

If Gradle Wrapper 8.5 is present, replace the first command with `.\gradlew.bat bootJar`. Gradle compiles with the Spring libraries and packages the JAR; do not use standalone `javac` for this example.

Aside from Spring Boot's startup logs, the lines printed by the program are:

```text
WEB_CONTEXTS=1
SEPARATE_MANAGEMENT_CONTEXT=false
MAIN_PORT=8087
MANAGEMENT_PORT=8087
SAME_WEB_SERVER_INSTANCE=true
MANAGEMENT_PARENT_IS_MAIN=false
MANAGEMENT_HAS_LOCAL_MARKER=true
SAME_MARKER_INSTANCE=true
MANAGEMENT_CAN_RESOLVE_CONTROLLER=true
```

`MANAGEMENT_PARENT_IS_MAIN=false` here is not an error: the management side is the main context itself, with no child context carrying that parent-child relationship.

Open a second PowerShell window:

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/business
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/actuator/info
```

Expected output:

```text
200
200
```

Both request groups go through the main web server.

### 7.5. Run B: Separate Port, Observing the Child Context

Stop run A with `Ctrl+C`, then run the same JAR again:

```powershell
java -jar build/libs/management-context-demo-1.0.0.jar --management.server.port=9087 --management.server.address=127.0.0.1
```

Expected observation lines:

```text
WEB_CONTEXTS=2
SEPARATE_MANAGEMENT_CONTEXT=true
MAIN_PORT=8087
MANAGEMENT_PORT=9087
SAME_WEB_SERVER_INSTANCE=false
MANAGEMENT_PARENT_IS_MAIN=true
MANAGEMENT_HAS_LOCAL_MARKER=false
SAME_MARKER_INSTANCE=true
MANAGEMENT_CAN_RESOLVE_CONTROLLER=true
```

Reading each group of evidence:

- `WEB_CONTEXTS=2` and `SEPARATE_MANAGEMENT_CONTEXT=true`: two web context instances are observed in the sample layout.
- `MANAGEMENT_PARENT_IS_MAIN=true`: the management context is identified as a child of the main context.
- `SAME_WEB_SERVER_INSTANCE=false`: the two contexts use two distinct web server instances.
- `MANAGEMENT_HAS_LOCAL_MARKER=false` yet `SAME_MARKER_INSTANCE=true`: the child context looks up to the parent and retrieves the same marker bean.
- `MANAGEMENT_CAN_RESOLVE_CONTROLLER=true`: the controller bean in the parent is still within lookup scope from the child.

You cannot use the last line to conclude that the controller is served on the management port. You must continue with HTTP verification.

### 7.6. Run B: Comparing HTTP Mapping Scopes

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/business
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/actuator/info
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:9087/actuator/info
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:9087/business
```

Expected output:

```text
200
404
200
404
```

Combined with stdout:

- The controller in the parent is resolvable from the child.
- Yet `/business` is not automatically exposed on the management port.
- Actuator `info` is served by the management web infrastructure on port `9087`.

These codes apply to the sample with no security or alternative mappings. In a real application, a filter may process the request before the handler-lookup step.

### 7.7. Run C: Explicitly Setting the Same Port Number

Stop run B, then run:

```powershell
java -jar build/libs/management-context-demo-1.0.0.jar --management.server.port=8087
```

The management address argument from run B does not automatically carry over to the new process.

Observations return to run A's shared layout: one web context observed, same server instance, and the marker bean belongs to the very context used for management.

This run distinguishes "having a `management.server.port` key declared" from "actually separating the port and context."

### 7.8. Comparison Table

| Evidence | Shared Port | Separate Port |
| --- | --- | --- |
| Number of web contexts observed in sample | 1 | 2 |
| Child management context | None | Present |
| Main and management web server instances | Same | Different |
| `sharedMarker` bean retrieved from both sides | Same instance | Still same instance |
| Management context owns the marker bean locally | Yes, because it is the main context | No, marker bean belongs to parent |
| Parent controller resolvable from management side | Yes | Yes via hierarchy |
| `/business` automatically served on separate management port | No separate port to consider | No in standard sample |

Do not take any single row as a substitute for the whole model. For example, shared beans do not contradict having two separate web servers; two separate web servers do not prove that data beans were duplicated.

## 8. Reading Infrastructure Signals Without Over-Inferring

### 8.1. Two Server Startup Log Lines Are a Clue, Not a Context Map

Logs may show web servers starting on two ports. This is useful evidence, but to tie each port to a context, compare runtime events or objects.

Do not use a context ID string containing a familiar word as the sole criterion. IDs, log formats, or implementation class names can change with configuration. Parent-child relationships and object identity are direct evidence in the example.

`WebServerApplicationContext` also provides a server namespace to distinguish servers within an application. When using this information in diagnostic tools, check runtime values and configuration contracts rather than guessing from display names.

### 8.2. Do Not Assume Every Web Customization Has the Same Effect

A filter or MVC configuration must be evaluated according to where it is registered and which server actually handles requests. That a bean can be looked up from the child does not replace verifying whether it is attached to the servlet processing chain.

Similarly, do not assume thread, connection, or TLS settings of the main server always apply verbatim to the management side. Read the configuration and customizer mechanisms in use, and verify requests on both ports.

This is also why you should not "quick-fix" by rescanning the entire business package in the management context: doing so can spawn unintended beans or mappings.

### 8.3. Paths Still Belong to the Corresponding Server's Scope

When separating ports, Actuator paths are calculated from `management.server.base-path` and `management.endpoints.web.base-path`. The main application's context path is not automatically prepended to management paths.

For example, with `management.server.base-path=/ops` and endpoint base `/actuator`, the `info` address on the management port is `/ops/actuator/info`. Reading the right context while calling the wrong prefix can still yield `404`. [Paths on the management server](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html)

## 9. Consequences for Monitoring, Security, and Lifecycle

### 9.1. Health Checks on the Management Port Do Not Cover All Main Web Handling

Separate management web infrastructure may still respond when the main application port has trouble accepting connections. Therefore, health responses on the management port must be interpreted according to the check's goal.

Spring Boot supports exposing liveness and readiness probe groups on the main port:

```properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true
```

When enabled and properly exposed, additional paths `/livez` and `/readyz` are added on the main port. This feature is not automatically enabled merely because a separate management context exists. [Probes when using a separate management context](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)

### 9.2. Context Relationship Does Not Replace Access Policy

Separating the management server creates a dedicated entry point for configuring bind addresses and network routes. Which endpoints are exposed, who may call them, and what data is returned still require corresponding policies.

When Spring Security or custom servlet configurations exist, verify on the exact port. Do not infer that a child context automatically creates a completely independent authentication boundary, nor that all parent rules are copied verbatim.

### 9.3. Lifecycle Remains Tied to One Application

This layout is managed by Spring Boot within a single process. There is no independent management service that keeps running once the main JVM has stopped.

When diagnosing startup, inspect the outcome of the whole application and both servers. A log line showing that the main server opened its port is not enough to conclude that the management context started successfully.

## 10. Self-Check With Specific Questions

1. Why can separating ports create two `WebServer` instances yet still retrieve the same `sharedMarker` bean?
2. How do `containsBean` and `containsLocalBean` answer two different questions?
3. Why does `MANAGEMENT_CAN_RESOLVE_CONTROLLER=true` still go with HTTP `404` when calling `9087/business`?
4. Why can a listener in the main application receive events from the management server?
5. If you record every port from events into the same variable without checking context, what could you misassign?
6. Which JVM limits do two separate web servers still share?
7. What does a successful health check on the management port still leave unproven about the main port?
8. If an application has multiple child web contexts, what needs to be added to the example's identification criteria?

To answer well, tie each conclusion to the right evidence: context from the event, relationship from `getParent()`, server from `getWebServer()`, bean from lookup, and mapping from HTTP requests. This distinction helps read management infrastructure accurately as the number of ports and contexts grows.
