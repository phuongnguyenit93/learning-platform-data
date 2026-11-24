# Diagnosing Missing WebServerFactory or Port Already in Use

## 1. Objectives and How to Read Startup Errors

Spring Boot can successfully initialize many application beans and still fail to open an HTTP server. Two common failure groups when running a web application are:

1. **Missing WebServerFactory**: the ApplicationContext needs to create an embedded HTTP server, but cannot find a factory bean capable of building a server matching the web application type.
2. **Port or address failed to bind**: the factory and embedded server were selected, yet the process cannot listen on the requested IP address or port.

Both errors can lead to `ApplicationContext startup failed`, yet their **root causes and fixes differ**. Do not draw conclusions solely from the last line such as `Application run failed`. Read the `Caused by` chain, identify whether it is the Servlet or Reactive stack, and then check dependencies and port status in order.

This lesson uses Spring Boot 3.3.x with Java 17+, focusing on embedded web servers in Spring MVC and Spring WebFlux applications. Gradle examples and run commands are standalone learning scenarios; adjust paths and ports if your project structure differs.

After this lesson, you will be able to:

- Distinguish a missing ServletWebServerFactory from a missing ReactiveWebServerFactory.
- Explain when Boot creates the factory and why excluding a dependency can prevent startup.
- Read the actual cause of a port-binding error instead of relying only on generic messages.
- Find the process listening on a port on Windows, Linux, and macOS.
- Fix configuration or dependencies, restart, and verify with a real HTTP request.
- Avoid false fixes such as accidentally disabling the web server or killing the wrong process.

## 2. Mental Model: From ApplicationContext to Listening Socket

When SpringApplication.run begins, Boot determines the web application type, processes configuration, creates the ApplicationContext, builds beans, and starts the server if the application type requires one.

Overview flow:

~~~mermaid
flowchart TD
    A["SpringApplication.run"] --> B{"WebApplicationType?"}
    B -->|SERVLET| C["Servlet web ApplicationContext"]
    B -->|REACTIVE| D["Reactive web ApplicationContext"]
    B -->|NONE| E["Non-web context; no HTTP server opened"]
    C --> F["Look up ServletWebServerFactory"]
    D --> G["Look up ReactiveWebServerFactory"]
    F --> H{"Matching factory found?"}
    G --> I{"Matching factory found?"}
    H -->|No| J["Missing WebServerFactory error"]
    I -->|No| J
    H -->|Yes| K["Create embedded server"]
    I -->|Yes| K
    K --> L{"Bind address and port succeed?"}
    L -->|No| M["BindException / Port already in use / address error"]
    L -->|Yes| N["Server listens and accepts HTTP requests"]
~~~

**WebServerFactory is a factory that creates an embedded web server, not a controller, service, or repository**. With the Servlet stack, Boot typically uses a ServletWebServerFactory to create a server like Tomcat. With the reactive stack, Boot needs a ReactiveWebServerFactory, such as the factory for Reactor Netty.

Related classes and beans:

| Application Type | Factory Boot Needs | Common Implementation Example | HTTP Pipeline |
| --- | --- | --- | --- |
| SERVLET / Spring MVC | org.springframework.boot.web.servlet.server.ServletWebServerFactory | TomcatServletWebServerFactory | Servlet container, Filter chain, DispatcherServlet |
| REACTIVE / WebFlux | org.springframework.boot.web.reactive.server.ReactiveWebServerFactory | NettyReactiveWebServerFactory | Reactive HTTP server, WebFilter, DispatcherHandler |
| NONE | No embedded web server factory required | Not applicable | Does not serve HTTP itself |

Having a factory still does not guarantee the port will open successfully: the operating system can reject binding after the server is created. Conversely, missing-factory errors occur **before** port binding, so changing server.port to 8081 does not fix a missing dependency.

## 3. Identifying the Two Error Groups from Messages

### 3.1 Missing WebServerFactory

A typical message in a Servlet application reads roughly like:

~~~text
Unable to start ServletWebServerApplicationContext due to missing ServletWebServerFactory bean.
~~~

For reactive applications, the corresponding message refers to ReactiveWebServerApplicationContext and ReactiveWebServerFactory.

This message means the context is starting under a web application type that requires an embedded server, but Spring has no suitable factory bean. Check:

- Is Boot running in SERVLET or REACTIVE mode?
- Is a starter/server dependency present on runtimeClasspath?
- Was the default embedded server excluded without adding another server?
- Is there an auto-configuration exclusion or special bean/condition?
- Is the application forcing a web application type incompatible with its classpath?

Do not assume the port is occupied: if the server could not even be created, the process never reached opening the port.

### 3.2 Port Already in Use or Bind Failure

Spring Boot may report:

~~~text
Web server failed to start. Port 8080 was already in use.
~~~

The underlying cause chain may include:

~~~text
java.net.BindException: Address already in use
~~~

Exact messages and exception wrapping depend on the server, operating system, and failure point. Some logs also show WebServerException, Unable to start embedded Tomcat, or failure starting the `webServerStartStop` bean; inspect the **deepest root cause** to tell whether it is genuinely a bind error.

Other causes that should not be lumped into "port already in use":

- Permission denied: the process lacks privileges to bind the address/port.
- Cannot assign requested address: server.address points to an IP not assigned to the machine or container environment.
- Invalid port or unparseable configuration: configuration error, not a process conflict.
- Network unreachable or connection refused on the client side: the server may not be running, may be bound to the wrong interface, or have a network issue; not sufficient proof that the port is occupied.

### 3.3 Quick Comparison Table

| Indicator | Missing Factory | Port Bind Failure |
| --- | --- | --- |
| When it occurs | When web context needs a bean to build the server | When server attempts to open the socket |
| Log keywords | missing ServletWebServerFactory / ReactiveWebServerFactory bean | Port ... already in use, BindException, failed to bind |
| Priority checks | WebApplicationType, runtimeClasspath, auto-configuration | server.port, server.address, LISTENING processes |
| Does changing port help? | No | Possibly, if the error is genuinely a port collision |
| Does adding a web server starter help? | Possibly, if server implementation is missing | Does not free an already occupied port |
| Goal after fix | Right factory exists for the stack | Bind succeeds and HTTP endpoints work |

## 4. First Step: Reading the Exception Chain Properly

A startup log can span hundreds of lines. Prioritize:

1. Note the Failure Analysis section or the line describing `Web server failed to start`, if present.
2. Find the deepest relevant `Caused by`, especially `BindException` or a missing factory error.
3. Identify the exact port, address, server type, and active web stack.
4. Check whether an earlier error prevented the factory bean from being initialized.
5. Only after classifying the error, adjust configuration or dependencies.

Two illustrative scenario descriptions:

~~~text
Scenario A:
ApplicationContext needs ServletWebServerFactory, yet no matching bean exists.
=> Check embedded Servlet server dependencies and auto-configuration.

Scenario B:
Tomcat/Netty is configured, yet cannot bind 0.0.0.0:8080.
=> Check processes LISTENING on port 8080 and server.address.
~~~

These are diagnostic interpretations, not two exact stack traces to match character-for-character. If the root exception differs from both scenarios above, address the actual root cause rather than forcing it into one of these two buckets.

## 5. Diagnosing a Missing ServletWebServerFactory

### 5.1 Normal Setup

For a simple Spring Boot Servlet application, dependencies typically include:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

`spring-boot-starter-web` normally pulls in Spring MVC and embedded Tomcat. Spring Boot uses `ServletWebServerFactoryAutoConfiguration` with matching conditions to configure a `ServletWebServerFactory`. If the application defines a supported custom factory itself, default auto-configuration can back off.

When Boot chooses SERVLET yet fails to create a factory, check whether the project excluded Tomcat, Jetty, or Undertow.

### 5.2 Example: Excluding Embedded Tomcat Without Adding Another Server

Illustrative configuration creating a missing-factory risk:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-tomcat'
    }
}
~~~

If no other embedded Servlet server is supplied, an application detected as SERVLET by Boot will lack a default factory to start an HTTP server. Excluding Tomcat is only appropriate when supplying an alternative server or packaging for deployment via a deliberately designed external mechanism.

Common fix: **remove the exclude** to use default Tomcat, or add an appropriate Servlet server starter. Example selecting Jetty:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-tomcat'
    }
    implementation 'org.springframework.boot:spring-boot-starter-jetty'
}
~~~

Do not add multiple embedded server starters just to "make sure there is one." When choosing an alternative to Tomcat, read the version and configuration requirements for your Spring Boot version.

### 5.3 Inspecting Actual Dependencies

In a Gradle project, inspect **runtimeClasspath**, because the web server must be present at runtime:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Focus on dependencies such as:

~~~text
spring-boot-starter-web
spring-boot-starter-tomcat
spring-boot-starter-jetty
spring-boot-starter-undertow
spring-webmvc
jakarta.servlet-api
~~~

This is a checklist of indicators; not every dependency needs to be present simultaneously.

To see where a dependency is pulled in from:

~~~bash
./gradlew dependencyInsight --dependency spring-boot-starter-tomcat --configuration runtimeClasspath
~~~

If a dependency only appears in `testImplementation` or `compileOnly`, it will not necessarily be on the application's runtime classpath. Also check project-level excludes, dependency management, convention plugins, and custom runtime configurations.

### 5.4 Reading the Condition Evaluation Report

When dependencies look right yet the factory is still missing, inspect auto-configuration conditions:

~~~bash
./gradlew bootRun --args='--debug'
~~~

Here `--debug` is passed **to the Spring Boot app** via `--args`, causing the app to print the Condition Evaluation Report at startup. Inspect sections related to:

- ServletWebServerFactoryAutoConfiguration
- Server-specific auto-configurations for Tomcat/Jetty/Undertow
- `@ConditionalOnClass`, `@ConditionalOnWebApplication`, `@ConditionalOnMissingBean`
- Any auto-configuration exclusions declared by the application

Do not manually define a `ServletWebServerFactory` bean before figuring out why auto-configuration skipped it. In most ordinary applications, fixing the dependency or web application type is cleaner and safer.

## 6. Diagnosing a Missing ReactiveWebServerFactory

For a reactive HTTP application, the typical configuration is:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

`spring-boot-starter-webflux` typically includes the Reactor Netty server. When Boot picks REACTIVE, the reactive web context needs an appropriate `ReactiveWebServerFactory`.

Example excluding the Reactor Netty starter:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-webflux') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-reactor-netty'
    }
}
~~~

If Boot runs in REACTIVE mode without another reactive-capable HTTP server implementation, the missing factory can cause startup to fail. Do not conclude WebFlux only needs `reactor-core`: reactive operators and the HTTP server runtime serve different roles.

To investigate:

~~~bash
./gradlew dependencyInsight --dependency spring-boot-starter-reactor-netty --configuration runtimeClasspath
~~~

Also check `ReactiveWebServerFactoryAutoConfiguration` in the Condition Evaluation Report and verify whether the application is being forced into REACTIVE mode.

## 7. Reviewing Servlet vs. Reactive When Both MVC and WebFlux Are Present

When both `spring-boot-starter-web` and `spring-boot-starter-webflux` are on the classpath, **Spring Boot defaults to preferring Spring MVC / SERVLET**. A common case is an MVC app needing `WebClient` without intending to switch its HTTP server stack.

Therefore:

- Having `WebClient` or `Mono`/`Flux` does not prove the app runs a reactive server.
- If both starters are present, verify whether Boot actually chooses SERVLET or REACTIVE.
- Use `spring.main.web-application-type=reactive` when you intentionally want a reactive app and have prepared the matching dependencies/server.
- Use `spring.main.web-application-type=none` only when the app truly needs no HTTP server; it is **not** a valid fix for a service supposed to serve REST APIs.

Example setting the web application type:

~~~properties
spring.main.web-application-type=reactive
~~~

If a project contains both MVC and WebFlux yet excludes a server improperly, a factory error can be an indirect consequence of the stack selection. Resolve both the **application context type** and the **server implementation** consistently.

## 8. Diagnosing Port Already in Use

### 8.1 Identify the Actual Port and Address

Spring Boot normally uses port 8080 unless configured otherwise. Values can come from `application.properties`/`application.yml`, environment variables, profiles, command-line arguments, or higher-precedence property sources.

Example:

~~~properties
server.port=8080
server.address=127.0.0.1
~~~

`server.address` is the interface address the web server attempts to bind. If unset, the server typically listens on the environment's default interfaces.

Before changing anything, check logs to confirm whether the failing port is actually 8080. Some applications run multiple contexts or an Actuator management server on another port; in that case check `management.server.port` and its endpoints as well.

### 8.2 Windows PowerShell

To find connections in the LISTEN state on port 8080:

~~~powershell
Get-NetTCPConnection -State Listen -LocalPort 8080 |
    Select-Object LocalAddress, LocalPort, State, OwningProcess
~~~

Once you have the PID, inspect the process:

~~~powershell
Get-Process -Id 12345
~~~

Replace 12345 with the actual `OwningProcess`. To inspect the full command line where permissions allow:

~~~powershell
Get-CimInstance Win32_Process -Filter "ProcessId = 12345" |
    Select-Object ProcessId, Name, CommandLine
~~~

On Windows systems lacking the `Get-NetTCPConnection` cmdlet, you can use:

~~~powershell
netstat -ano -p tcp | findstr :8080
~~~

When reading `netstat`, look for the `LISTENING` line and its PID; `ESTABLISHED` or `TIME_WAIT` connections do not by themselves prove a process is listening on that port. If you lack permissions to inspect another user's process, consult an administrator instead of guessing the owner.

### 8.3 Linux

Use `ss` to inspect listening sockets:

~~~bash
ss -ltnp 'sport = :8080'
~~~

Elevated privileges may be required to see PIDs/processes belonging to other users. Alternative command:

~~~bash
lsof -nP -iTCP:8080 -sTCP:LISTEN
~~~

If no process appears listening on 8080 yet the app still reports bind failed, check `server.address`, namespaces/containers, IPv4/IPv6, and the root exception message.

### 8.4 macOS

~~~bash
lsof -nP -iTCP:8080 -sTCP:LISTEN
~~~

Output shows the PID and process name if system permissions allow. Do not use outbound client connection lists to claim a local port is occupied by another server.

### 8.5 Verify Before Stopping a Process

If the PID is another Java application, it may be a running instance of the service or an earlier run started by an IDE or Gradle. Check the process name, command line, and purpose before stopping it.

For an app launched by an IDE, use the IDE's Stop button or lifecycle controls. For a Gradle terminal or `java -jar`, stop the running process cleanly—for example, with Ctrl+C in that terminal. Avoid killing random PIDs or stopping someone else's service just to free a port.

## 9. Three Ways to Resolve a Port Conflict

### Option A: Stop the Right Stale Process

Appropriate when that process is a leftover test instance of your application. After stopping it, verify the port is free and restart.

### Option B: Move the Application to Another Port

In `application.properties`:

~~~properties
server.port=8081
~~~

Or pass an argument at runtime:

~~~bash
./gradlew bootRun --args='--server.port=8081'
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun --args="--server.port=8081"
~~~

Update client URLs, reverse proxies, health checks, or service discovery configuration if the environment requires a fixed port.

### Option C: Use a Dynamic Port for Testing/Local Runs

~~~properties
server.port=0
~~~

The operating system then allocates an available port. This is helpful for tests or running multiple local instances, provided clients know the **actual port** chosen by the server. You can no longer assume `localhost:8080`. In Spring Boot integration tests, use `RANDOM_PORT` and read `@LocalServerPort`.

Switching to 8081 or 0 only solves port collisions when the bind address and privileges are valid. If the error is `Cannot assign requested address` or `Permission denied`, resolve the address/permission cause first.

## 10. Runnable Example: Reproducing a Port Error and Fixing It

The example creates a small Spring Boot MVC application returning the string `READY` at `/healthz`. Java 17+; Gradle compatible with Spring Boot 3.3.x.

Structure:

~~~text
boot-server-diagnostics/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/demo/BootServerDiagnosticsApplication.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'boot-server-diagnostics'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

File `src/main/java/com/example/demo/BootServerDiagnosticsApplication.java`:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class BootServerDiagnosticsApplication {

    public static void main(String[] args) {
        SpringApplication.run(BootServerDiagnosticsApplication.class, args);
    }
}

@RestController
class HealthController {

    @GetMapping(value = "/healthz", produces = MediaType.TEXT_PLAIN_VALUE)
    public String healthz() {
        return "READY";
    }
}
~~~

Both classes are in the same package, so Spring Boot component scanning detects the controller. `build.gradle` already includes embedded Tomcat via `starter-web`. This is a standalone application example; no database or Actuator is required.

### 10.1 Build and Run the First Instance

In the project directory:

~~~bash
gradle bootJar
~~~

Run instance A:

~~~bash
java -jar build/libs/boot-server-diagnostics-0.0.1-SNAPSHOT.jar --server.port=8080
~~~

Keep this terminal running. In a second terminal:

~~~bash
curl -s http://127.0.0.1:8080/healthz
~~~

Expected body:

~~~text
READY
~~~

### 10.2 Reproduce a Port Collision

Keep A listening on 8080. Open a third terminal and run **the same JAR** on the same port:

~~~bash
java -jar build/libs/boot-server-diagnostics-0.0.1-SNAPSHOT.jar --server.port=8080
~~~

Instance B cannot bind a second listening socket like instance A on the same address/port, so Boot typically reports `port 8080 already in use` or an equivalent bind error. This is the expected outcome of the experiment; exact log wording depends on the OS and server.

Now run B on a different port:

~~~bash
java -jar build/libs/boot-server-diagnostics-0.0.1-SNAPSHOT.jar --server.port=8081
~~~

Verify:

~~~bash
curl -s http://127.0.0.1:8081/healthz
~~~

Expected body:

~~~text
READY
~~~

Once both instances are running and each binds a distinct port, you have verified that changing the port resolves the port-collision category.

### 10.3 Reproduce the Missing-Factory Risk

Temporarily change the `starter-web` dependency in the example to:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-tomcat'
    }
}
~~~

Do not declare a replacement server. Build and run the application again. If the classpath still causes Boot to choose SERVLET without an embedded Servlet server implementation, you may encounter a missing `ServletWebServerFactory` error. Behavior from IDEs, tests, or custom configurations may differ depending on the classpath; never assume a fixed exception before inspecting the logs.

Fix it by **restoring the original `starter-web` dependency**, or adding an appropriate alternative embedded Servlet server starter. On restart, calling `/healthz` should return `READY`.

**Experiment boundary**: Never alter dependencies in a production app just to provoke an error. The goal is to distinguish server-creation errors from port-binding errors.

## 11. When Changing the Port Still Fails

If changing 8080 to 8081 still fails, check further:

- **Non-existent IP address**: `server.address` may point to an address not assigned to the host/container. List available interfaces and bind to a valid address.
- **Port occupied on another address or IPv6/IPv4**: a process listening on `0.0.0.0` or `::` can interact with interface-specific binds depending on the OS and configuration. Check the exact `LocalAddress` in socket listing commands.
- **Bind permission denied**: certain ports or OS security policies restrict the process. Do not solve this by elevating privileges if a normal unprivileged port like 8080 works.
- **Argument overridden**: `--server.port=8081` was passed, yet a higher-precedence config source or another process still uses 8081; check the final resolved configuration the app receives.
- **Multiple servers starting in one process**: inspect parent/child contexts, management server, or configs creating multiple listeners.
- **Parallel test runs**: integration tests binding the same fixed port can collide. Prefer `RANDOM_PORT` or isolate test resources.
- **Error is not port-related**: bean creation may be failing before binding. Re-read `Caused by`.

Calling `curl` on a nonexistent endpoint may return HTTP 404. That is not proof the server failed to start; on the contrary, an HTTP 404 from the right process shows the HTTP server received the request but has no mapping for that URL. Checking the right `/healthz` endpoint makes this clearer.

## 12. Containers, Docker, and Host Ports

In containers, at least two addresses/ports must be distinguished:

- **Container port**: what the Java application actually binds inside the container's network namespace, e.g. 8080.
- **Host port**: the port Docker publishes on the host machine, e.g. 18080 when using `-p 18080:8080`.

If one container already publishes host port 8080, Docker can refuse to start another container on the same host port even though the two apps inside use separate container ports. That is a Docker host publish/bind error, not necessarily an application `BeanFactory` exception.

Example using a different host port:

~~~bash
docker run --rm -p 18080:8080 my-boot-image
~~~

Precondition: the `my-boot-image` image exists and the app listens on port 8080 on an interface reachable from the container network. If the app binds only `127.0.0.1` inside the container, Docker port publishing may not be reachable from the host as expected.

To inspect running containers and port mappings:

~~~bash
docker ps
~~~

If an error originates from a proxy, orchestration platform, or port-publishing layer, inspect that component's logs, not only Spring Boot logs.

## 13. Checking Integration Tests and Development Environments

### 13.1 SpringBootTest Using RANDOM_PORT

A web integration test can pick a dynamic port to avoid port contention:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.web.client.RestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class HealthControllerTest {

    @LocalServerPort
    private int port;

    @Test
    void shouldRespondFromStartedServer() {
        String body = RestClient.create()
                .get()
                .uri("http://127.0.0.1:" + port + "/healthz")
                .retrieve()
                .body(String.class);

        assertThat(body).isEqualTo("READY");
    }
}
~~~

Add the matching test dependencies:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

This test uses the REST client in Spring Framework 6.1 (included in Spring Boot 3.3.x) and requires the example application from section 10. It is a complete test verifying that the HTTP server opened a dynamic port and the endpoint returns the expected body; there is no need to assume port 8080 is free.

### 13.2 Some Tests Should Not Start a Server

If only testing service logic, use a unit test without starting a Spring context. If only testing a web controller slice, use web slice tests when appropriate. Do not start an embedded server solely to test a plain Java method.

A test configured to force `spring.main.web-application-type=servlet` or `reactive` while excluding the matching server dependencies can hit a factory error. Cross-check test annotations, properties, and the actual classpath before blaming production code.

## 14. Logging and Observation for Root-Cause Analysis

Keep enough diagnostic context on hand:

- Expected web application type (SERVLET or REACTIVE).
- Name of the selected embedded server if determined.
- Expected port and address; active profiles and relevant configuration.
- Root cause line from the exception chain, not just `Application run failed`.
- Runtime dependencies for the server implementation.
- LISTENING port status and owning PID in the target environment.
- HTTP request result after applying the fix.

You can enable Spring Boot's condition evaluation report when running in a test environment:

~~~bash
./gradlew bootRun --args='--debug'
~~~

The `--debug` flag can produce verbose output; when sharing logs, strip tokens, passwords, credentials, connection strings, or sensitive data. Note: Spring Boot Actuator is only available if the project adds its dependency and configuration; Actuator is not required to verify the server via `/healthz` in this example.

## 15. Step-by-Step Troubleshooting Workflow

~~~mermaid
flowchart TD
    A["Application run failed"] --> B["Read root cause"]
    B --> C{"Missing WebServerFactory?"}
    C -->|Yes| D["Determine SERVLET vs REACTIVE"]
    D --> E["Inspect runtimeClasspath and excludes"]
    E --> F["Inspect auto-configuration conditions"]
    F --> G["Add/fix server dependency or web type"]
    C -->|No| H{"BindException / Port in use?"}
    H -->|Yes| I["Check server.port and server.address"]
    I --> J["List LISTEN sockets / PIDs"]
    J --> K["Stop stale instance or change port/address"]
    H -->|No| L["Analyze other cause in stack trace"]
    G --> M["Restart"]
    K --> M
    L --> M
    M --> N{"HTTP response from expected endpoint?"}
    N -->|Yes| O["Verify issue resolved"]
    N -->|No| B
~~~

Follow this workflow during a real incident:

1. Read the logs and **classify**: missing factory, port bind failure, or another error.
2. If factory is missing, verify the web application type and dependencies/auto-configuration. Do not change ports blindly.
3. If binding fails, verify port + address and inspect listening processes in the **exact environment** running the app.
4. Make one intentional change: fix dependencies, fix web type, stop the right stale instance, or change port/address.
5. Restart only the single instance under test.
6. Send an HTTP request to a known endpoint, checking status, body, and actual port.
7. Document the root cause and prevention steps, especially dependency exclusions and fixed ports in tests.

## 16. Common Pitfalls

- **Changing `server.port` to fix a missing factory**: ineffective because the error happens before socket binding.
- **Adding a Servlet web starter to an app that must run reactively**: can cause Boot to select SERVLET when both starters are present; explicitly set the web application type.
- **Using `spring.main.web-application-type=none` just to "make it start"**: this disables the web server; unsuitable if an API must serve requests.
- **Assuming Tomcat in the dependency tree guarantees Boot is using Tomcat**: check the runtime classpath, auto-configuration, and actual server used.
- **Assuming port 8080 fails in every environment**: each host/container network namespace has its own port space.
- **Killing the first PID seen in netstat**: that PID may belong to an important service or another user.
- **Treating 404 as a server startup failure**: 404 can be a normal response when the server is running yet no route matches.
- **Treating every connection refused as port already in use**: refused usually indicates no listener is available at the target address/port.
- **Forgetting fixed ports in tests**: parallel integration tests collide easily; use `RANDOM_PORT` unless a specific port is required.
- **Reading only the last line of the stack trace**: a deeper `Caused by` line distinguishes bean errors from network errors.

## 17. Summary

**Missing WebServerFactory** means Spring Boot lacks the embedded server factory matching the Servlet or Reactive web context. Inspect web application type, dependencies on `runtimeClasspath`, exclusions, and auto-configuration; restore or supply an appropriate server starter.

**Port already in use / bind failed** means the server attempted to listen on an unusable address or port. Identify the port, address, and actual listener; stop the right stale process or pick a valid port, then re-verify.

In both cases, the final proof is not merely a "Started ..." log line: call the right HTTP endpoint and confirm the status/body over the port the process is actually listening on.

## 18. References

- Spring Boot 3.3 — Embedded Web Servers: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
- Spring Boot 3.3 — Servlet Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Spring Boot 3.3 — Reactive Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
- Spring Boot 3.3 — Externalized Configuration: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html