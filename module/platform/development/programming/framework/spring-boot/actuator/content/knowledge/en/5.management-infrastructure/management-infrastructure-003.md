# Coordinating Management Base Path with Servlet Context Path or WebFlux Base Path

## 1. Viewing the Management URL Layer by Layer

Suppose the `health` endpoint is enabled and exposed over HTTP. After moving the application from the root path to `/app`, continuing to call `/actuator/health` may return 404 even though Actuator is working normally. The reason is that the full path also depends on the application's prefix and where the management server is placed.

To determine the URL, answer in sequence:

1. Does the application run on Servlet or WebFlux?
2. Does Actuator share a port with the application or use a separate management port?
3. What is the prefix of the application or management server?
4. What are the endpoint group prefix and the individual endpoint path?

This article uses Spring Boot 3.3.x, default Servlet configuration, and requests sent directly to the server. Experimental examples were verified with Boot 3.3.0, Java 21, Servlet on Tomcat, and WebFlux on Reactor Netty.

## 2. Distinguishing Properties Containing "path"

| Property | Role | Scope to Remember |
| --- | --- | --- |
| `server.servlet.context-path` | Context path of a Servlet application, e.g., `/app` | Common prefix of the Servlet application; when sharing a port, Actuator paths sit under this prefix |
| `spring.webflux.base-path` | Base path of a WebFlux application, e.g., `/api` | Corresponding prefix for reactive applications when sharing a port |
| `management.endpoints.web.base-path` | Prefix of the Actuator endpoint group, default `/actuator` | E.g., changed to `/manage`; composed beneath the root appropriate for the port mode |
| `management.server.base-path` | Root path of the separate management server, e.g., `/ops` | Used when the management port is actually separated from the application port |
| `management.endpoints.web.path-mapping.health` | Changes the path segment of the endpoint with ID `health` | E.g., `ready`; does not change the endpoint ID in the exposure list |

Do not stack `server.servlet.context-path` and `spring.webflux.base-path` together as two mandatory layers. Choose the property matching the type of application actually running.

According to Boot 3.3 documentation, when sharing a port, the management endpoint base path sits under the Servlet context path or WebFlux base path; when separating ports, it sits under the management server base path. [Relationship between HTTP management paths](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html#actuator.monitoring.customizing-management-endpoint-paths).

## 3. Servlet Sharing the Port

Configuration:

```properties
server.port=8080
server.servlet.context-path=/app
management.endpoints.web.base-path=/manage
management.endpoints.web.exposure.include=health
```

No separate management port is set. The `health` path is composed as follows:

```text
/app/manage/health
= /app/manage/health
```

Full URL:

```text
http://127.0.0.1:8080/app/manage/health
```

If a business controller has mapping `@GetMapping("/ping")`, its URL is:

```text
http://127.0.0.1:8080/app/ping
```

The `/manage` prefix is placed only before Actuator endpoints; it does not automatically turn the `/ping` controller into `/app/manage/ping`.

| Test URL in Unsecured Sample App | Expected Result |
| --- | --- |
| `http://127.0.0.1:8080/app/manage/health` | Finds the health endpoint |
| `http://127.0.0.1:8080/manage/health` | Missing context path `/app` |
| `http://127.0.0.1:8080/app/actuator/health` | Still uses the old Actuator prefix |

### 3.1. When Keeping Actuator's Default Prefix

If you omit `management.endpoints.web.base-path=/manage`, the default Actuator prefix is `/actuator`. With context path `/app`, the URL becomes:

```text
http://127.0.0.1:8080/app/actuator/health
```

Changing the context path does not automatically remove the `/actuator` prefix.

## 4. WebFlux Sharing the Port

Corresponding configuration:

```properties
server.port=8080
spring.webflux.base-path=/api
management.endpoints.web.base-path=/manage
management.endpoints.web.exposure.include=health
```

`health` path:

```text
/api/manage/health
= /api/manage/health
```

Full URL:

```text
http://127.0.0.1:8080/api/manage/health
```

A controller mapped to `/ping` is called at:

```text
http://127.0.0.1:8080/api/ping
```

In this case, do not use `server.servlet.context-path` as a substitute for `spring.webflux.base-path`. A WebFlux application does not become a Servlet application just because a property name starting with `server` is added to the configuration.

If the result still behaves like Servlet when intending to run WebFlux, check the application type selected by Boot and the starters on the classpath. The demo project below selects one web starter per build, helping distinguish the two cases.

## 5. When the Management Port Is Actually Separate

Suppose the application port is 8080 and the management port is 8081:

```properties
server.port=8080
management.server.port=8081
management.server.base-path=/ops
management.endpoints.web.base-path=/manage
management.endpoints.web.exposure.include=health
```

On the management server, the path composition is:

```text
/ops/manage/health
= /ops/manage/health
```

Management URL:

```text
http://127.0.0.1:8081/ops/manage/health
```

This path does not prepend the application server's context/base path. Two concrete cases:

| Application Type | `/ping` Controller Path on Port 8080 | Health Path on Port 8081 |
| --- | --- | --- |
| Servlet with `server.servlet.context-path=/app` | `/app/ping` | `/ops/manage/health` |
| WebFlux with `spring.webflux.base-path=/api` | `/api/ping` | `/ops/manage/health` |

Do not compose `/app/ops/manage/health` or `/api/ops/manage/health` on the management port. Nor should you keep probing `/app/manage/health` or `/api/manage/health` on the business port as if Actuator had not moved ports.

Separating the port configures a dedicated management server. [Configuring the management port in Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html#actuator.monitoring.customizing-management-server-port).

### 5.1. If management.server.base-path Is Not Added

With a separate port 8081 but no additional management server prefix, `management.endpoints.web.base-path=/manage` produces the URL:

```text
http://127.0.0.1:8081/manage/health
```

It does not automatically inherit `/app` or `/api` to become a path on the management port.

### 5.2. Declaring the Same Port Number Still Means Sharing a Port

Example:

```properties
server.port=8080
management.server.port=8080
server.servlet.context-path=/app
management.endpoints.web.base-path=/manage
```

Here the management port is not different from the application port. With this Servlet configuration, `health` remains at `/app/manage/health` on port 8080.

The deciding factor is having an **actually separate management port**, not merely whether a line named `management.server.port` exists in the file. In typical examples, leaving this property blank also means using the application port. [Management server properties and using the application port](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/web/server/ManagementServerProperties.html).

## 6. Formula and Quick Reference Table

Let:

- `A` be the effective application prefix: Servlet context path or WebFlux base path.
- `M` be the management server base path when there is a separate management server.
- `E` be the management endpoint base path, defaulting to `/actuator`.
- `S` be the endpoint operation's path, such as `/health`.

Then, with the typical path configurations in this article:

```text
Shared port:   URL = application server address + A + E + S
Separate port: URL = management server address + M + E + S
```

This represents joining path segments, not mechanically concatenating strings while keeping every `/` verbatim. A root segment `/` is not inserted as two consecutive slashes.

| Mode | A | M | E | Health Path on Target Port |
| --- | --- | --- | --- | --- |
| Servlet, shared port | `/app` | Not used as separate management root | `/manage` | `/app/manage/health` on application port |
| WebFlux, shared port | `/api` | Not used as separate management root | `/manage` | `/api/manage/health` on application port |
| Servlet or WebFlux, separate port | Business application prefix | `/ops` | `/manage` | `/ops/manage/health` on management port |
| Separate port, without M | Business application prefix | No additional prefix | `/manage` | `/manage/health` on management port |
| Servlet, shared port, E is root | `/app` | Not used as separate management root | `/` | `/app/health` on application port |
| WebFlux, shared port, E is root | `/api` | Not used as separate management root | `/` | `/api/health` on application port |

### 6.1. Setting Endpoint Base Path to / Does Not Remove Outer Context/Base Path

Servlet example:

```properties
server.servlet.context-path=/app
management.endpoints.web.base-path=/
```

`health` is located at `/app/health`, not `/health`. Similarly, WebFlux with base path `/api` will use `/api/health`.

### 6.2. Changing the Individual Path of Health

```properties
server.servlet.context-path=/app
management.endpoints.web.base-path=/manage
management.endpoints.web.path-mapping.health=ready
management.endpoints.web.exposure.include=health
```

The URL becomes:

```text
http://127.0.0.1:8080/app/manage/ready
```

The ID in include remains `health`; `ready` is only the mapped path. Nor is this an operation that creates a readiness health group: the example only renames the path of the health endpoint.

## 7. Experiment With the Same Java Code for Servlet and WebFlux

The small project below uses Java 21, Gradle 8.5, and Boot 3.3.0. Ports 8080/8081 must be available for the corresponding runs; if changing ports, update the test URLs following the same rule.

The application has a `/ping` controller to distinguish the business prefix from the Actuator prefix. It adds no Spring Security and listens only on loopback. The first build needs to download plugins and libraries.

### 7.1. Create the Files

```text
actuator-path-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/lab/paths/
    │   ├── PathApplication.java
    │   └── PingController.java
    └── resources/application.properties
```

File `settings.gradle`:

```groovy
rootProject.name = 'actuator-path-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

def webStack = providers.gradleProperty('webStack').getOrElse('servlet')
if (!(webStack in ['servlet', 'reactive'])) {
    throw new GradleException('webStack must be servlet or reactive')
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    if (webStack == 'reactive') {
        implementation 'org.springframework.boot:spring-boot-starter-webflux'
    } else {
        implementation 'org.springframework.boot:spring-boot-starter-web'
    }
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}

tasks.named('bootJar') {
    archiveFileName = "actuator-path-demo-${webStack}.jar"
}
```

The Gradle property `webStack` in this project selects one web starter: `servlet` uses Spring MVC, `reactive` uses WebFlux. The two JAR files have distinct names so the run command clearly shows which application type was built.

File `src/main/java/lab/paths/PathApplication.java`:

```java
package lab.paths;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PathApplication {
    public static void main(String[] args) {
        SpringApplication.run(PathApplication.class, args);
    }
}
```

File `src/main/java/lab/paths/PingController.java`:

```java
package lab.paths;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {
    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }
}
```

The controller declares only `/ping`; it does not copy `/app`, `/api`, or `/manage` into the annotation. The outer prefixes are determined by environment configuration.

File `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=8080
management.endpoints.web.exposure.include=health
management.endpoints.web.base-path=/manage
```

### 7.2. Run Servlet, Shared Port

```shell
gradle bootJar -PwebStack=servlet
java -jar build/libs/actuator-path-demo-servlet.jar --server.servlet.context-path=/app
```

In another command-line window:

```shell
curl -i http://127.0.0.1:8080/app/ping
curl -i http://127.0.0.1:8080/app/manage/health
curl -i http://127.0.0.1:8080/manage/health
```

On Windows PowerShell, use `curl.exe` if `curl` is an alias.

Main results: `/app/ping` returns 200 with body `pong`; `/app/manage/health` returns 200 in the healthy sample app; `/manage/health` returns 404 due to the missing context path.

### 7.3. Separate Management Port for Servlet

Stop the previous Servlet process with Ctrl+C, then run:

```shell
java -jar build/libs/actuator-path-demo-servlet.jar --server.servlet.context-path=/app --management.server.port=8081 --management.server.address=127.0.0.1 --management.server.base-path=/ops
```

Test:

```shell
curl -i http://127.0.0.1:8080/app/ping
curl -i http://127.0.0.1:8081/ops/manage/health
curl -i http://127.0.0.1:8080/app/manage/health
curl -i http://127.0.0.1:8081/app/ops/manage/health
```

The first two requests return 200 in the sample app. The last two return 404: one still looks for Actuator on the business port, and the other prepends an extra context path.

`management.server.address=127.0.0.1` in this example sets the address for the separate management server; it does not determine path segments.

### 7.4. Run WebFlux, Shared Port

Stop the previous process, build reactive mode, then run:

```shell
gradle bootJar -PwebStack=reactive
java -jar build/libs/actuator-path-demo-reactive.jar --spring.webflux.base-path=/api
```

Test:

```shell
curl -i http://127.0.0.1:8080/api/ping
curl -i http://127.0.0.1:8080/api/manage/health
curl -i http://127.0.0.1:8080/manage/health
```

The two requests with `/api` return 200 in the sample app; the last request lacks the WebFlux base path and thus returns 404.

### 7.5. Separate Management Port for WebFlux

Stop the previous reactive process, then run:

```shell
java -jar build/libs/actuator-path-demo-reactive.jar --spring.webflux.base-path=/api --management.server.port=8081 --management.server.address=127.0.0.1 --management.server.base-path=/ops
```

Test:

```shell
curl -i http://127.0.0.1:8080/api/ping
curl -i http://127.0.0.1:8081/ops/manage/health
curl -i http://127.0.0.1:8081/api/ops/manage/health
```

The first two requests return 200 in the sample app. The last request returns 404 because it prepends `/api` from the business application onto the separate management server.

When modifying packaged configuration files, you must rebuild the JAR and restart. When changing only command-line arguments as in this lesson, stopping and rerunning the right JAR is sufficient for that test run.

## 8. Public Paths Behind a Reverse Proxy May Differ

The formula above determines the URL that the application handles directly. A reverse proxy can add or strip a prefix before forwarding the request to the application.

For example, a proxy receives `/platform/ops/manage/health`, strips `/platform`, and forwards `/ops/manage/health` to the management port. In that case, the public URL includes `/platform`, while the management server configuration does not necessarily contain this prefix.

Distinguish between:

```text
External path sent by the caller
    → proxy rules for keeping/stripping/rewriting the prefix
    → internal path received by the application
```

If a prefix is already configured in the application, do not add it a second time merely based on the public URL. Conversely, a proxy keeping a prefix that the application does not have can also produce a 404.

Changing the base path does not automatically expose additional endpoints and does not grant access permissions. After changing the management URL, update the exact address in probes, metrics scraping configs, or path-based access rules.

## 9. Evidence-Based Diagnosis

When a management URL does not work, check:

1. **Right process and web type:** is a Servlet or WebFlux JAR running; which arguments are in effect?
2. **Right port:** does management have its own server; is the request hitting the application port or the management port?
3. **Right outer prefix:** use the application's context/base path when sharing a port, and the management server base path when separating ports.
4. **Right endpoint prefix:** is it still `/actuator`, changed to `/manage`, or set to `/`?
5. **Right final segment:** does the endpoint have a custom path mapping; is the ID in include still right?
6. **Right exposure and access conditions:** is the endpoint enabled, selected for HTTP, and authorized for the caller?
7. **Right route through the proxy:** which path does the application actually receive after proxy forwarding?

In the unsecured sample project, mismatched paths return 404. In real systems, 401/403 can come from access control; 503 on a health response can relate to application health status. Do not change path configuration based solely on an error code without inspecting the response body and where it originated.

## 10. Common Mistakes

| Confusion | Fix |
| --- | --- |
| Sharing a port but omitting `/app` or `/api` | Prepend the application prefix before the management endpoint base path |
| Separating ports but still adding `/app` or `/api` to the management URL | Use the separate server's management server base path |
| Setting `/manage` and continuing to call `/actuator` | Check the effective endpoint base path value |
| Assuming `management.endpoints.web.base-path=/` removes all prefixes | Keep the appropriate outer context/base path layer |
| Stacking both Servlet context path and WebFlux base path | Identify the running application type and choose the right property |
| Declaring two equal ports but calculating URLs as two servers | Apply the shared-port rules |
| Remapping health path to ready and then writing `include=ready` | Keep ID `health` in include; only the path changes |
| Hardcoding `/app` in the controller while also setting context path `/app` | Let the controller describe internal paths to avoid duplicating configured prefixes |
| Editing config but still running an old process or JAR | Check the startup command and rebuild when necessary |

## 11. Self-Check

**Question 1.** Servlet has context path `/orders`, endpoint base path `/manage`, sharing port 8080. Where is health?

**Answer:** `http://127.0.0.1:8080/orders/manage/health`.

**Question 2.** WebFlux has base path `/api`, endpoint base path still defaults to `/actuator`, sharing a port. What is the health path?

**Answer:** `/api/actuator/health`.

**Question 3.** The app has prefix `/api`, separate management port 8081, management server base path `/ops`, endpoint base path `/manage`. Do you prepend `/api` to the management URL?

**Answer:** No. The direct management URL is `http://127.0.0.1:8081/ops/manage/health`.

**Question 4.** Servlet has context path `/app`, shares a port, and sets endpoint base path to `/`. Is health at `/health`?

**Answer:** No. It is at `/app/health`.

**Question 5.** Do two port properties both equal to 8080 create a separate management server?

**Answer:** Not in this fixed-port case. You must apply the path composition of shared-port mode.

**Question 6.** Does mapping health's path to `ready` change the endpoint ID to `ready`?

**Answer:** No. The ID remains `health`; the final path segment changes to `/ready`.
