# Running Actuator on the Application Port or a Separate Management Port

Web applications commonly have two groups of requests: business requests from users and management requests from operational tools. Spring Boot Actuator provides the second group, such as reading application health or info.

You can serve both groups on the **same HTTP port**, or move Actuator endpoints to a **separate management port**. This choice affects access addresses, network configuration, health checks, and how the management infrastructure is organized.

This lesson uses **Spring Boot 3.3.x**; the hands-on project is pinned to **3.3.13, Java 21, Gradle 8.5, and Spring MVC**. The examples cover applications using an embedded web server, packaged as an executable JAR.

## 1. Two Port Layouts

### 1.1. Sharing the Application Port

For example, an application listening on port `8087`:

```text
Port 8087
├── /hello           → application path
└── /actuator/info   → management endpoint
```

Configuration:

```properties
server.port=8087
```

If `management.server.port` is not set, Actuator HTTP uses the same port as the application. Having the Actuator library does not automatically open an extra fixed management port.

In addition to the port, an endpoint must also be enabled, satisfy its auto-configuration conditions, and be selected for HTTP exposure. For example, `info` in this lesson is explicitly exposed with:

```properties
management.endpoint.info.enabled=true
management.endpoints.web.exposure.include=health,info
```

### 1.2. Using a Separate Management Port

```properties
server.port=8087
management.server.port=9087
```

Desired layout:

```text
Same Java process
├── Port 8087
│   └── /hello           → application path
└── Port 9087
    └── /actuator/info   → management endpoint
```

In the standard auto-configuration mechanism of the example, Actuator endpoints move to the management port; they are not automatically duplicated onto both ports.

The property to select the port is `management.server.port`. It is not `management.endpoints.web.port`. [Configuring the HTTP management port](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html)

## 2. Meaning of the Port Options

| Configuration | Expected Outcome |
| --- | --- |
| `management.server.port` not set | Actuator HTTP uses the application port |
| Set to the same value as the application port, e.g., both `8087` | Still shares the application port and context |
| Set to a different positive port, e.g., application `8087`, management `9087` | Creates a separate management layout with a management web server |
| Set `management.server.port=-1` | Stops serving management endpoints over HTTP |

Explicitly setting the same port number does not mean starting a second server competing for the same address. With the fixed ports in this lesson, Spring Boot distinguishes the same-port and different-port cases to choose the appropriate mechanism. [Management context auto-configuration API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/web/server/ManagementContextAutoConfiguration.html)

A value of `-1` does not shut down the business HTTP server. Nor does it mean disabling all forms of management such as JMX. Those channels have their own configuration. [Disabling HTTP management exposure](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html)

In testing, a random port can be used with appropriate configuration, but you must retrieve the **actual allocated port**. The number `0` is not a port address for monitoring tools to call directly. The experiments in this lesson use fixed ports for easy comparison.

## 3. How Does a Separate Port Work Within the Same Application?

When the management port matches the application port, Spring Boot uses the same `ApplicationContext`, meaning the context containing the application's beans.

When using a separate management port, Spring Boot creates a separate management context with the main application context as its parent. For servlet applications, the management auto-configuration provides the mechanism to create the child web context and corresponding web server. [Management auto-configuration for servlet applications](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/web/servlet/ServletManagementContextAutoConfiguration.java)

This separates the HTTP management entry point, yet both still reside in the same process:

- Share the same JVM and process memory.
- Equally affected if the process stops or runs out of resources.
- Do not create an independent service with a separate deployment lifecycle.
- Do not automatically copy all business controllers onto the management port.

Therefore, separating the port is a way to organize web and network infrastructure. You should not infer that it provides complete isolation of resources or failures.

### 3.1. Choosing a Different Port Does Not Automatically Enable More Endpoints

For example:

```properties
management.server.port=9087
management.endpoints.web.exposure.include=health
```

still selects only `health` for HTTP exposure. A separate port does not automatically make `env`, `beans`, or `info` appear.

You can read the decision layers in order of questions:

1. Is the endpoint enabled and eligible?
2. Is the endpoint exposed over HTTP?
3. Which port is the management HTTP server on?
4. Can the caller connect and do they have access permissions?

## 4. Determining the Correct Address, Port, and Path

A full URL requires a protocol, target host, port, and path segments. Changing the port does not replace determining the correct base path.

### 4.1. When Sharing a Port

Suppose the configuration is:

```properties
server.port=8087
server.servlet.context-path=/app
management.endpoints.web.base-path=/actuator
```

The address of `info`, when exposed, is:

```text
http://127.0.0.1:8087/app/actuator/info
```

With Spring MVC sharing a port, Actuator's base path is resolved relative to `server.servlet.context-path`.

### 4.2. When Using a Separate Port

Suppose:

```properties
server.port=8087
server.servlet.context-path=/app

management.server.port=9087
management.server.base-path=/ops
management.endpoints.web.base-path=/manage
```

The corresponding Actuator address is:

```text
http://127.0.0.1:9087/ops/manage/info
```

The `/app` prefix of the main application is not prepended to this management URL. With a separate management port, the endpoint base path is resolved relative to `management.server.base-path`.

Path composition table:

| Layout | Context Prefix | Endpoint Base | `info` Path |
| --- | --- | --- | --- |
| Shared port | `server.servlet.context-path=/app` | `/actuator` | `/app/actuator/info` |
| Separate port | `management.server.base-path=/ops` | `/manage` | `/ops/manage/info` |

These are two properties with different responsibilities: `management.server.base-path` is the root of the separate management server, whereas `management.endpoints.web.base-path` is the root of the web endpoint group. [Management property descriptions](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html)

### 4.3. Listen Address Also Matters

With a separate port, you can have the management server listen only on a local address:

```properties
server.port=8087
management.server.port=9087
management.server.address=127.0.0.1
```

`management.server.address` is used for layouts with a separate management port. When sharing a port, the shared server uses the application's address; you cannot create two independent listen addresses with this management property alone.

Listening on `127.0.0.1` means accepting connections from the same local network environment. If the monitoring tool is on another machine or network segment, you must choose an appropriate address and route instead of only changing the port number.

In a container, the loopback address belongs to the network namespace inside the container. Declaring an external port mapping does not automatically make a process listening only on loopback receive all forwarded connections.

## 5. When to Choose Same Port vs. Separate Port?

| Requirement | Shared Port | Separate Port |
| --- | --- | --- |
| Minimal local run configuration | Fewer configuration points | Requires an extra port to track |
| Infrastructure forwards only one HTTP port | Convenient if routing and security are path-based | Requires adding forwarding for the management port |
| Network policy separating management traffic | Requires path-based or intermediary-layer controls | Can apply rules by dedicated port and address |
| Operational tools use a separate management address | Requires clear path conventions | Has a dedicated access point to configure |
| Checking the main app's ability to accept HTTP | Uses the same web infrastructure | Requires considering an additional check on the main port |

Neither choice is always better in every environment. Start from how operational tools will connect and the actual access policy.

A separate port does not automatically add authentication or authorization. If Spring Security or a proxy protects management, verify that rules apply to the right access point. Exposure lists, invocation permissions, and network connectivity are separate control layers.

## 6. Complete Hands-On: Keep the Same JAR, Change the Port Layout

We create an application path `/hello` to observe the main server, while using the Actuator `info` endpoint to observe the management server. These two observations help distinguish "whether the app still accepts HTTP" from "which port Actuator is on."

The project does not add Spring Security, proxies, or other custom mappings. Ports `8087` and `9087` must be free; stop previous runs before changing configuration. The outputs below are **expected results for this exact sample project**.

### 6.1. Project Structure

```text
actuator-port-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/
    │   ├── PortDemoApplication.java
    │   └── BusinessProbeController.java
    └── resources/application.properties
```

File `settings.gradle`:

```groovy
rootProject.name = 'actuator-port-demo'
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

File `src/main/java/example/PortDemoApplication.java`:

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PortDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(PortDemoApplication.class, args);
    }
}
```

File `src/main/java/example/BusinessProbeController.java`:

```java
package example;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class BusinessProbeController {

    @GetMapping("/hello")
    public String hello() {
        return "APP_HTTP_OK";
    }
}
```

This path is an observation probe for the port experiment. It does not replace the health or readiness check mechanisms of a real system.

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

Do not declare `management.server.port` in the initial file. Thus, the first run uses a shared port.

### 6.2. Build and Run Case A: Same Port

In the project directory, using JDK 21 and Gradle 8.5:

```powershell
gradle bootJar
java -jar build/libs/actuator-port-demo-1.0.0.jar
```

If the project already has Gradle Wrapper 8.5, you can replace the first command with `.\gradlew.bat bootJar`. Gradle provides the Spring dependency classpath and produces an executable JAR; do not use standalone `javac` for this project.

Open a second PowerShell window:

```powershell
curl.exe -s http://127.0.0.1:8087/hello
```

Expected response body:

```text
APP_HTTP_OK
```

Check the HTTP status codes of both paths:

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/hello
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/actuator/info
```

Expected output:

```text
200
200
```

Both are served on port `8087`. Enabling Actuator does not create an extra port `9087` in this run.

### 6.3. Case B: Move Actuator to a Separate Port

Stop run A with `Ctrl+C`, then run **the same JAR** again:

```powershell
java -jar build/libs/actuator-port-demo-1.0.0.jar --management.server.port=9087 --management.server.address=127.0.0.1
```

On the new startup, wait for both the application and the management server to finish starting. Check four addresses:

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/hello
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/actuator/info
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:9087/actuator/info
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:9087/hello
```

Expected output in order:

```text
200
404
200
404
```

Explanation:

- The application controller is still served on main port `8087`.
- Actuator `info` is served on management port `9087`.
- The Actuator path is no longer mapped on the main port in the sample configuration.
- The `/hello` controller is not automatically copied onto the management server.

These `404` results belong to the sample project with no security filters or alternative mappings. In another application, you must consider the entire request processing chain before interpreting response codes.

### 6.4. Case C: Explicitly Set the Management Port Equal to the Application Port

Stop run B, then run:

```powershell
java -jar build/libs/actuator-port-demo-1.0.0.jar --management.server.port=8087
```

Each command launches a new process; the `management.server.address` argument from run B is not automatically retained.

Call again:

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/hello
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/actuator/info
```

Expected output:

```text
200
200
```

Spring Boot chooses the shared-port layout. There is no second management server competing to bind `127.0.0.1:8087`.

### 6.5. Case D: Stop Serving Actuator Over HTTP

Stop run C, then run:

```powershell
java -jar build/libs/actuator-port-demo-1.0.0.jar --management.server.port=-1
```

Verify:

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/hello
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/actuator/info
```

Expected output:

```text
200
404
```

The application still serves the main controller; Actuator HTTP has stopped being exposed. The sample configuration also disables JMX separately with `spring.jmx.enabled=false`; do not infer that JMX being disabled is an effect of the `-1` port value.

### 6.6. Case E: Verify Path Prefixes When Separating Ports

Stop run D, then run:

```powershell
java -jar build/libs/actuator-port-demo-1.0.0.jar --server.servlet.context-path=/app --management.server.port=9087 --management.server.address=127.0.0.1 --management.server.base-path=/ops --management.endpoints.web.base-path=/manage
```

Verify:

```powershell
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:8087/app/hello
curl.exe -s -o NUL -w "%{http_code}\n" http://127.0.0.1:9087/ops/manage/info
```

Expected output:

```text
200
200
```

If you mistakenly call `9087/app/actuator/info`, you are using the main application's prefix and the old base path. Changing to the right port with the wrong path still will not reach the desired endpoint.

### 6.7. Run Verification Table

| Run | Application Path | Actuator `info` Path |
| --- | --- | --- |
| A: management port unset | `8087/hello` → `200` | `8087/actuator/info` → `200` |
| B: management port `9087` | `8087/hello` → `200` | `9087/actuator/info` → `200` |
| C: management port set to `8087` | `8087/hello` → `200` | `8087/actuator/info` → `200` |
| D: management port `-1` | `8087/hello` → `200` | Not served over Actuator HTTP |
| E: separate port and custom prefixes | `8087/app/hello` → `200` | `9087/ops/manage/info` → `200` |

The shortened addresses in the table all use `http://127.0.0.1`. The table only describes the sample project and does not accumulate parameters across runs.

## 7. Port Separation and Health Checks

A monitoring system may see the health endpoint on the management port working while the main HTTP server cannot accept new requests. The reason is that when contexts are separated, the two sides do not share all web infrastructure.

Therefore, before choosing the check's port, determine what it needs to prove:

- Process status and health information reported by Actuator.
- Ability to accept HTTP on the user-facing port.
- Application readiness to receive traffic.

With Spring Boot's liveness and readiness probe groups, you can configure additional paths on the main port:

```properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true
```

When these groups are enabled and eligible for exposure, they add `/livez` and `/readyz` paths on the main application port. This is a feature you must actively consider in design; separating the port does not automatically add these paths in the sample project. [Health groups and probes on the main port](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)

Do not equate every `200` management response with all business features working properly. Conversely, a health indicator can cause `health` to return an error status even though the web server still accepts connections.

## 8. Infrastructure Considerations

### 8.1. Process Ports and External Ports Are Two Layers

Setting `management.server.port=9087` makes the application open the corresponding listener when the configuration is valid. It does not automatically modify:

- Container port mappings.
- Deployment environment Services or routing.
- Reverse proxies, firewalls, or allowed source lists.
- Target configurations of metrics scrapers and health checks.

If the infrastructure only forwards the application port, external tools may not reach the new management port. You must update the designed route properly; do not infer from the application starting up that the port is reachable from everywhere.

### 8.2. Separate Port and Security

Separating the port helps apply dedicated network rules. Permissions to read or modify management data still need proper control. Endpoints that expose data or management operations must be evaluated against authentication, authorization, and exposure policies.

If you want the management server to have its own TLS configuration, Spring Boot supports the `management.server.ssl.*` group when using a separate port. Choosing the port and configuring the protocol and certificates are related but distinct decisions; do not turn an HTTP URL into HTTPS merely by changing the port number.

### 8.3. Effective Values May Differ From the File Being Viewed

For example, if the file sets:

```properties
management.server.port=9087
```

but the process runs with:

```powershell
java -jar build/libs/actuator-port-demo-1.0.0.jar --management.server.port=8087
```

then under standard startup behavior, the command-line argument overrides the same key in the file. The corresponding environment variable is `MANAGEMENT_SERVER_PORT`.

When diagnosing, check profiles, environment variables, and startup arguments as well. Editing a file also does not automatically move the port of an already running process; you must restart according to the proper procedure. [Configuration sources and precedence](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)

## 9. Evidence-Based Diagnosis

| Symptom | Investigation Direction |
| --- | --- |
| Startup fails because port is already in use | Check both application and management ports; find conflicting processes or configurations |
| Calling the new port gives connection refused | Has the server started; is the bind address right; is there a network path to it |
| Connected but received `404` | Check port, context path, both base paths, and HTTP endpoint exposure set |
| Received `401` or `403` | Check security mechanisms instead of only changing ports |
| Works locally, unreachable from another machine | Check loopback, bind address, port mapping, and network policy |
| Actuator healthy but users cannot reach the app | Check main port and web infrastructure; review the health check's goal |
| Result matches the previous run | Verify the exact PID, JAR, arguments, and ensure no old process remains |

An HTTP response like `404` means a response was received from a server; inability to establish a connection lies at another layer. Do not use these two kinds of evidence interchangeably.

When the management server fails to start, do not treat the application as ready just because an earlier log line reported the main port starting. Check the overall application startup outcome and the actual state of both access points.

## 10. Self-Check

1. Why is it unnecessary to set `management.server.port` for Actuator to use the application port?
2. Does explicitly setting the management port equal to the application port create a second server?
3. When switching from `8087` to management port `9087`, what else besides the port number must be updated in the monitoring tool if the app also has base paths?
4. Why can `management.server.address=127.0.0.1` prevent a remote monitoring machine from connecting?
5. Why does `management.server.port=-1` still allow `/hello` to run in the example?
6. What evidence about the main application port is missing from a successful health check on a separate management port?
7. Does separating the port split the JVM, memory, and deployment lifecycle into two independent services?

You have mastered this lesson when you can accurately identify **which port serves which request**, **how the full URL is composed**, and **what port separation helps control along with which configuration layers still need review**.
