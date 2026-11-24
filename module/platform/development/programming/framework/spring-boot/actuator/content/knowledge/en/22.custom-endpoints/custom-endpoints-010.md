# Customizing Endpoints with @EndpointWebExtension or @EndpointJmxExtension

## 1. Shared Endpoints and Channel-Specific Representations

An Actuator endpoint can serve two groups of tools: HTTP clients and JVM management tools via JMX. The underlying management data may be the same, while the representation and accompanying metadata differ. HTTP has status codes and JSON bodies; JMX works with MBeans and management operations.

For example, a queue that has paused accepting jobs still needs to return the pending job count. An HTTP monitoring tool wants JSON accompanied by status `503`; an operator in JConsole wants to read a short string. If you put HTTP status-code decisions into the shared endpoint, the JMX consumer becomes coupled to HTTP concepts.

In Actuator, **an extension is a class that provides additional or replacement operations for an existing endpoint for a specific access technology**:

- `@EndpointWebExtension` applies to HTTP.
- `@EndpointJmxExtension` applies to JMX.
- `endpoint = YourEndpointClass.class` specifies the endpoint class being extended.

These annotations attach to an endpoint; they do not create a new management ID. The meaning of the `endpoint` attribute is described in [Spring Boot 3.3's EndpointWebExtension API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/web/annotation/EndpointWebExtension.html).

In this lesson, we use Spring Boot **3.3.13** and Java **17+** source code. The program and tests below have been run on Java 21.

## 2. Choosing the Right Extension Point

| Need | Appropriate Component |
| --- | --- |
| Create a management endpoint with a common model across channels | `@Endpoint` |
| Create a new endpoint serving HTTP only | `@WebEndpoint` |
| Create a new endpoint serving JMX only | `@JmxEndpoint` |
| Customize how an existing endpoint serves HTTP | `@EndpointWebExtension` |
| Customize how an existing endpoint serves JMX | `@EndpointJmxExtension` |

For example, if `workqueue` already holds shared queue data and only needs HTTP status codes added, choose a web extension. If you want an independent management feature with a different ID, design a new endpoint. The [Implementing Custom Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom) documentation presents technology-specific endpoints and extensions.

Before writing an extension, also check whether the endpoint in use already has configuration properties or specialized extension points. For instance, adding a health check usually fits `HealthIndicator` better than writing a custom web extension for `health`.

## 3. Discovery and Operation Replacement Mechanism

### 3.1. The Class Must Actually Be a Spring Bean

The extension annotation describes the role of the class. The class must still be registered as a bean via `@Bean` or via an appropriate stereotype like `@Component` within the scan scope.

The flow can be pictured as follows:

1. Spring has the base endpoint bean and the extension bean.
2. Actuator discovers methods annotated with `@ReadOperation`, `@WriteOperation`, or `@DeleteOperation`.
3. The HTTP discoverer picks up web extensions; the JMX discoverer picks up JMX extensions.
4. Actuator combines base operations with extension operations, replacing operations that share the same identifying key.
5. Operations are exposed to management channels per exposure configuration.

An extension typically receives the base endpoint via constructor to reuse data and logic. Actuator does not invoke the base endpoint automatically before or after the extension. If base behavior must be preserved, the extension must call it explicitly.

### 3.2. HTTP and JMX Have Different Identifying Keys

**For HTTP**, the key is built from the request predicate, consisting of path, HTTP method, and content-type predicates. Java method names do not determine the URL.

For example, the lesson has two methods:

- Base endpoint: `@ReadOperation Snapshot snapshot()`.
- Web extension: `@ReadOperation WebEndpointResponse<Map<String, Object>> overview()`.

Both map to the read operation at the root of `workqueue`, with identical default content-type predicates. Therefore, the web extension replaces the HTTP operation even though `overview` differs from `snapshot`. How keys are constructed can be seen in [WebEndpointDiscoverer 3.3.13](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/endpoint/web/annotation/WebEndpointDiscoverer.java).

If adding `@Selector` changes the path or changing `produces` alters predicates, re-evaluate the entire predicate. Having two methods both annotated with `@ReadOperation` is not enough to conclude one replaces the other. Adding query parameters is also not a way to split two HTTP operations that share the same predicate.

**For JMX in Spring Boot 3.3.13**, the operation key is the JMX operation name. In the example, the extension keeps the name `snapshot` to replace that operation. Renaming it to `summary` adds a new operation name; the original `snapshot` remains. Do not infer Java overloading by parameter type lists to design JMX operations with duplicate names.

Combination rules and JMX keys can be verified in [EndpointDiscoverer](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/endpoint/annotation/EndpointDiscoverer.java) and [JmxEndpointDiscoverer](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/endpoint/jmx/annotation/JmxEndpointDiscoverer.java) of this version.

### 3.3. Scope of Replacement

A web extension modifies only operations exposed over HTTP; a JMX extension modifies only operations exposed over JMX. Base operations with other keys are preserved.

Direct Java calls such as `endpoint.snapshot()` still call the method on the base endpoint instance. An extension is not `extends`, does not need `@Override`, and does not turn the base endpoint into a different object.

In Spring Boot 3.3.13, at most one extension per endpoint can be selected by each technology discoverer. You can simultaneously have one web extension and one JMX extension. Multiple web extension beans for the same endpoint are not chained like ordered filters; merge their responsibilities or use conditional configuration so only one matching bean exists.

## 4. Complete Example: One Queue, Two Ways to Observe

We build a `workqueue` endpoint with the following data:

- `accepting`: whether the queue is accepting new jobs, initially `false`.
- `pending`: pending job count, fixed at `7` to focus on the extension mechanism.
- `setAccepting`: management operation that toggles the accepting flag.

This is a minimal model for experimentation; no real queue or job processor is implemented. The flag uses `AtomicBoolean` so HTTP/JMX calls can observe shared state changes.

Standalone project structure:

```text
endpoint-extension-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/demo/DemoApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/demo/ExtensionTest.java
```

### 4.1. Declaring Libraries

Create `pom.xml`:

```xml
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
    <groupId>com.example</groupId>
    <artifactId>endpoint-extension-demo</artifactId>
    <version>1.0.0</version>
    <properties><java.version>17</java.version></properties>
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
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build><plugins><plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
    </plugin></plugins></build>
</project>
```

`spring-boot-starter-web` provides Spring MVC and an embedded server; `spring-boot-starter-actuator` provides endpoints and extensions; `spring-boot-starter-test` supports testing. The project inherits Spring Boot's compiler configuration, including retaining parameter names so Actuator binds the `accepting` input.

### 4.2. Base Endpoint and Two Extensions

Create `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.boot.actuate.endpoint.annotation.WriteOperation;
import org.springframework.boot.actuate.endpoint.jmx.annotation.EndpointJmxExtension;
import org.springframework.boot.actuate.endpoint.web.WebEndpointResponse;
import org.springframework.boot.actuate.endpoint.web.annotation.EndpointWebExtension;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    WorkQueueEndpoint workQueueEndpoint() {
        return new WorkQueueEndpoint();
    }

    @Bean
    WorkQueueWebExtension workQueueWebExtension(WorkQueueEndpoint endpoint) {
        return new WorkQueueWebExtension(endpoint);
    }

    @Bean
    WorkQueueJmxExtension workQueueJmxExtension(WorkQueueEndpoint endpoint) {
        return new WorkQueueJmxExtension(endpoint);
    }

    public record Snapshot(boolean accepting, int pending) { }

    @Endpoint(id = "workqueue")
    public static class WorkQueueEndpoint {
        private final AtomicBoolean accepting = new AtomicBoolean(false);

        @ReadOperation
        public Snapshot snapshot() {
            return new Snapshot(accepting.get(), 7);
        }

        @WriteOperation
        public void setAccepting(boolean accepting) {
            this.accepting.set(accepting);
        }
    }

    @EndpointWebExtension(endpoint = WorkQueueEndpoint.class)
    public static class WorkQueueWebExtension {
        private final WorkQueueEndpoint endpoint;

        public WorkQueueWebExtension(WorkQueueEndpoint endpoint) {
            this.endpoint = endpoint;
        }

        @ReadOperation
        public WebEndpointResponse<Map<String, Object>> overview() {
            Snapshot snapshot = endpoint.snapshot();
            Map<String, Object> body = new LinkedHashMap<>();
            body.put("accepting", snapshot.accepting());
            body.put("pending", snapshot.pending());
            int status = snapshot.accepting()
                    ? WebEndpointResponse.STATUS_OK
                    : WebEndpointResponse.STATUS_SERVICE_UNAVAILABLE;
            return new WebEndpointResponse<>(body, status);
        }
    }

    @EndpointJmxExtension(endpoint = WorkQueueEndpoint.class)
    public static class WorkQueueJmxExtension {
        private final WorkQueueEndpoint endpoint;

        public WorkQueueJmxExtension(WorkQueueEndpoint endpoint) {
            this.endpoint = endpoint;
        }

        @ReadOperation
        public String snapshot() {
            Snapshot snapshot = endpoint.snapshot();
            return "accepting=" + snapshot.accepting()
                    + ",pending=" + snapshot.pending();
        }
    }
}
```

Three `@Bean` methods explicitly register the endpoint and both extensions. Classes are nested in one file for easy execution; in larger applications they can be split into separate files while keeping constructor-based wiring.

**The base endpoint** knows only `Snapshot` and the state-changing operation. It returns neither HTTP codes nor JMX formatting strings.

**The web extension** calls `endpoint.snapshot()`, builds the JSON body, and picks the response status. `WebEndpointResponse` lets you supply a body together with an HTTP status code; this is the purpose described in the [WebEndpointResponse API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/web/WebEndpointResponse.html). Pick the right `(body, status)` constructor; the constructor taking only `body` defaults to status `200`.

**The JMX extension** takes the same `Snapshot` and formats it into a `String`, so operators read both fields in one call. Do not put `WebEndpointResponse` in JMX because it carries HTTP response semantics.

Both extensions declare only a read operation. The base endpoint's write operation `setAccepting` remains present on both HTTP and JMX. Calling back into the base endpoint lets both channels share the same state.

### 4.3. HTTP and JMX Configuration

Create `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
spring.jmx.enabled=true
management.endpoints.web.exposure.include=health,workqueue
management.endpoints.jmx.exposure.include=workqueue
```

In this experiment:

- HTTP listens on the machine's loopback address.
- `workqueue` is added to the HTTP exposure list.
- `spring.jmx.enabled=true` enables Spring's JMX integration.
- The JMX exposure list includes `workqueue`.

When configuring endpoint enablement/exposure, lists use the base endpoint's ID `workqueue`. Do not use the bean name or extension class name.

Spring Boot's JMX is disabled by default; MBean naming rules and configuration are presented in [Monitoring and Management over JMX](https://docs.spring.io/spring-boot/3.3/reference/actuator/jmx.html). Enabling `spring.jmx.enabled` does not mean opening a remote JMX port. This lesson uses only the in-JVM MBeanServer and local JConsole connections.

The sample project omits Spring Security. When adding state-changing management operations to a real application, enforce appropriate access controls for each channel. Protecting HTTP with `SecurityFilterChain` does not automatically protect a remote JMX connection.

## 5. Running and Observing

### 5.1. Compiling and Starting

In the directory containing `pom.xml`, run:

```shell
mvn package
java -jar target/endpoint-extension-demo-1.0.0.jar
```

Maven compiles Java code together with required libraries; `java -jar` then runs the application. Dependencies are downloaded on the first run. Default HTTP port is `8080`; if already in use, change `server.port` and adjust URLs in commands accordingly.

### 5.2. Initial HTTP: Status 503 with Data Present

In another terminal window:

```shell
curl -i -H 'Accept: application/json' http://127.0.0.1:8080/actuator/workqueue
```

Two details to observe in the response are status code **503** and JSON body:

```json
{"accepting":false,"pending":7}
```

Remaining HTTP headers may vary by environment. The JSON above is the body, not the complete output of `curl -i`.

With only the base read operation returning `Snapshot`, having a result object would not automatically infer `503` from `accepting=false`. That decision lives in the web extension.

Status `503` here is purely a convention of the `workqueue` endpoint. It does not automatically change `health` results, readiness state, or load balancer health checks.

### 5.3. Calling the Write Operation Preserved from the Base Endpoint

In a shell supporting single quotes like Bash:

```shell
curl -i -X POST -H 'Content-Type: application/json' -d '{"accepting":true}' http://127.0.0.1:8080/actuator/workqueue
```

In PowerShell, you can use this equivalent command to avoid quoting differences when passing arguments to native programs:

```powershell
Invoke-WebRequest -Method Post -Uri 'http://127.0.0.1:8080/actuator/workqueue' -ContentType 'application/json' -Body '{"accepting":true}'
```

The POST result is **204 No Content**. The write method returns `void`, so there is no result body. The extension declares no write operation, yet Actuator retains `setAccepting` from the base endpoint.

Call GET again:

```shell
curl -i -H 'Accept: application/json' http://127.0.0.1:8080/actuator/workqueue
```

Now the status code is **200** and the body is:

```json
{"accepting":true,"pending":7}
```

HTTP paths do not include the names `overview` or `setAccepting`. Under this configuration, GET and POST share `/actuator/workqueue`; the operation type determines the HTTP method.

### 5.4. Observing the Same State with JConsole

With the application still running:

1. Launch `jconsole` from a JDK that includes it, under an account permitted to attach to the running JVM.
2. Select the `DemoApplication` process in the local processes list.
3. Open the **MBeans** tab and locate the `org.springframework.boot` domain.
4. Find the MBean with ObjectName `org.springframework.boot:type=Endpoint,name=Workqueue`.
5. Open **Operations** and invoke `snapshot`.

If you performed the POST above, the returned value is:

```text
accepting=true,pending=7
```

The name `Workqueue` in ObjectName is derived from the ID `workqueue` under the experiment's default configuration; it is not `WorkQueueWebExtension`. If you change the domain or enable unique names in an application with multiple contexts, select the actual ObjectName.

Invoke `setAccepting` with boolean `false` on the same MBean. Invoke `snapshot` again:

```text
accepting=false,pending=7
```

Afterward, GET over HTTP returns **503** again. This shows the two representations share the same endpoint and state rather than creating two separate management copies.

To see the initial state again, restart the application. The flag is held in memory and reinitialized to `false`.

## 6. Testing Both Exposure Channels

Calling `new WorkQueueWebExtension(...).overview()` directly does not test whether Actuator discovered the beans, replaced the right operation, or kept the base operation. We need to test both Actuator's HTTP mappings and the registered MBean.

Create `src/test/java/com/example/demo/ExtensionTest.java`:

```java
package com.example.demo;

import javax.management.MBeanServer;
import javax.management.ObjectName;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = "spring.jmx.enabled=true")
@AutoConfigureMockMvc
class ExtensionTest {
    @Autowired MockMvc http;
    @Autowired MBeanServer mbeans;
    @Autowired DemoApplication.WorkQueueEndpoint endpoint;

    @Test
    void webAndJmxUseDifferentExtensionsAndRetainTheWriteOperation() throws Exception {
        ObjectName name = new ObjectName("org.springframework.boot:type=Endpoint,name=Workqueue");
        endpoint.setAccepting(false);
        assertThat(endpoint.snapshot()).isEqualTo(new DemoApplication.Snapshot(false, 7));
        http.perform(get("/actuator/workqueue"))
                .andExpect(status().isServiceUnavailable())
                .andExpect(content().json("{\"accepting\":false,\"pending\":7}", true));
        assertThat(mbeans.invoke(name, "snapshot", new Object[0], new String[0]))
                .isEqualTo("accepting=false,pending=7");

        http.perform(post("/actuator/workqueue")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"accepting\":true}"))
                .andExpect(status().isNoContent());
        http.perform(get("/actuator/workqueue"))
                .andExpect(status().isOk())
                .andExpect(content().json("{\"accepting\":true,\"pending\":7}", true));
        assertThat(mbeans.invoke(name, "snapshot", new Object[0], new String[0]))
                .isEqualTo("accepting=true,pending=7");

        mbeans.invoke(name, "setAccepting", new Object[]{false}, new String[]{"boolean"});
        http.perform(get("/actuator/workqueue"))
                .andExpect(status().isServiceUnavailable());
    }
}
```

Run:

```shell
mvn test
```

The successful test summary includes:

```text
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Startup log lines, runtime, and JVM warnings may differ.

This test uses **MockMvc**, going through the application's in-memory HTTP mapping and handling; it does not open a TCP port. The JMX part calls the real MBeanServer in the same JVM without creating a remote JMX connection.

`@SpringBootTest(properties = "spring.jmx.enabled=true")` explicitly enables JMX for the test run. Spring Boot disables JMX by default in `@SpringBootTest` contexts, so do not rely solely on normal runtime configuration.

Conditions verified:

| Call Path | Confirmed Result |
| --- | --- |
| Direct Java call `endpoint.snapshot()` | Still receives `Snapshot(false, 7)` from the base endpoint |
| GET when not accepting | Web extension returns 503 and the exact two JSON fields |
| JMX `snapshot` | JMX extension returns the string for the same state |
| POST `accepting=true` | Base write operation remains available, returns 204 |
| GET after POST | Returns 200 and `accepting=true` |
| JMX after POST | Sees state `true` |
| JMX `setAccepting(false)` then GET | Base write operation mutates shared state; HTTP returns 503 again |

This result simultaneously verifies per-channel read operation replacement and preservation of the write operation.

## 7. Common Errors and How to Identify Causes

### Annotated Extension Is Not Used

Check whether the bean is registered, whether the `@Bean`-declaring class is loaded, and whether `endpoint = ...class` points to the right base endpoint class. Placing the annotation on a class outside configuration scope does not create a bean.

If the base endpoint is conditionally created, ensure the extension is only created when the corresponding endpoint exists. An extension cannot act as a data source for an unregistered base endpoint.

### HTTP Still Returns Base Result or Has Conflicting Mappings

Compare the predicates of both operations: HTTP method, path derived from ID/`@Selector`, consumes, and produces predicates. Having the same Java method name does not guarantee the same HTTP mapping.

Conversely, two read operations in the same class with the same predicate can conflict even with different Java names. Design clear paths and operation types, then test through HTTP mapping.

### JMX Shows Both Old and New Operations

Check the operation name. In the version used in this lesson, `summary` is a different key from `snapshot`. If the goal is to replace `snapshot`, the extension must supply that exact name.

### Endpoint Is Unreachable

Distinguish three verification layers: bean/operations discovered; endpoint permitted for exposure on the channel in use; call allowed by the security layer.

In this experiment, verify the exact ID in `management.endpoints.web.exposure.include` or `management.endpoints.jmx.exposure.include`. When `exclude` is configured, it takes precedence over `include`. When integrating into another application, also check enablement, base path, and management port settings.

### HTTP Returns 401 or 403

This can be the result of authentication, authorization, or CSRF when the application uses Spring Security. Do not conclude the extension was not discovered from these codes alone. The standalone sample has no Security library; real applications may have different configurations.

### POST Reports Input Error

JSON must contain an `accepting` property matching the parameter name. Source code must be compiled with parameter name metadata, such as via the Spring Boot parent configuration in `pom.xml` above. Check both the boolean type and `Content-Type`.

### Multiple Extensions of the Same Technology for One Endpoint

Avoid registering two web extensions for `workqueue` at the same time. Adding `@Order` does not turn them into sequential filters. If multiple configurations contribute beans, clarify conditions to select one extension.

For built-in endpoints like `health`, first identify the extensions or specialized components Boot already provides; do not assume you can add a second web extension to automatically layer behavior.

### Management Data Is Stale

If the application configures `management.endpoint.workqueue.cache.time-to-live` greater than 0, parameterless read operations can be cached. When testing immediate updates as in this lesson, keep TTL at 0 so cached data is not mistaken for an extension failure. The sample project configures no positive TTL.

## 8. Practice with Reference Outcomes

1. **Unregister the web extension while keeping the base endpoint and JMX extension.** After restarting with state `false`, HTTP uses the base read operation and no longer returns 503 from `overview`. JMX still returns the string from its extension.
2. **Unregister the JMX extension while keeping the web extension.** HTTP continues using `overview`; JMX uses the base operation. Observe how the base type is rendered in the JMX tool rather than assuming it matches the extension's string.
3. **Rename the web extension method from `overview` to `inspect`.** Keep the operation annotation and mapping predicates; the GET URL remains `/actuator/workqueue`.
4. **In the JMX extension, rename `snapshot` to `summary`.** Inspect the Operations list to see the new operation added while the base `snapshot` is no longer replaced.
5. **Expose `workqueue` only over HTTP.** Verify that HTTP working does not cause the `workqueue` MBean to be exported over JMX.

After each change, restart the application and verify both channels. For changes that intentionally alter the contract, update test expectations accordingly before evaluating results.

When designing an extension for another endpoint, clearly establish: where shared data lives, which channel needs a distinct representation, which operations are replaced, which operations must remain, and what conditions permit exposing management data.
