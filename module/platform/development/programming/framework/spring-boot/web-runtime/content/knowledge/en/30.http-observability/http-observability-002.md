# Configuring Access Logs for Tomcat, Jetty, Undertow, or Reactor Netty in Spring Boot

## 1. What Is an Access Log and Why Configure It Per HTTP Server?

When an HTTP request passes through Spring Boot, a developer might see `log.info(...)` from a service, exception stack traces, Micrometer metrics, or access logs. These sources are **not the same**. An **HTTP access log** is a record at the HTTP server layer, typically describing method, URL, timestamp, client IP, status code, byte count, and request duration. It can appear even when the controller **never calls a logger itself**.

Example lines in Common Log Format, with **purely illustrative** numbers and timestamps:

~~~text
127.0.0.1 - - [08/Nov/2026:09:00:01 +0700] "GET /ping HTTP/1.1" 200 15
127.0.0.1 - - [08/Nov/2026:09:00:02 +0700] "GET /missing HTTP/1.1" 404 88
~~~

From these two lines you can observe that GET `/ping` succeeded and `/missing` returned 404. However, you cannot deduce the business cause of the 404, SQL query time, or MFA-verified identity from the access log alone.

Spring Boot supports several embedded web servers. **There is no single shared access log configuration namespace across all servers**:

| Embedded server | Typical Spring Boot web stack | How to enable access logs |
| --- | --- | --- |
| Tomcat | Default Spring MVC/Servlet | `server.tomcat.accesslog.enabled=true` |
| Jetty | Spring MVC/Servlet when dependency is swapped | `server.jetty.accesslog.enabled=true` |
| Undertow | Spring MVC/Servlet when dependency is swapped | `server.undertow.accesslog.enabled=true` |
| Reactor Netty | Default Spring WebFlux/reactive | **JVM** `-Dreactor.netty.http.server.accessLogEnabled=true` or `HttpServer.accessLog(true)` |

This lesson uses Spring Boot **3.3.x, Java 17+** as its version baseline. Property keys, behaviors, and library packages may change across major versions; always check documentation matching your project's version.

Goal: choose the right server, enable logs in the right place, understand format/latency units, know whether logs go to files or stderr, handle proxy/client IP and privacy, run real HTTP tests, and distinguish access logs from tracing, business audits, and debug wiretaps.

## 2. Observing an HTTP Request Across Multiple Layers

~~~text
Browser / Mobile / API client
      |
      v
CDN / Load balancer / API gateway / Reverse proxy
      |  Edge access log: external client IP, cache, WAF,
      |                   TLS, edge status, upstream latency
      v
Tomcat / Jetty / Undertow / Reactor Netty
      |  Server access log: method, path, status, bytes, time
      v
Spring MVC DispatcherServlet / WebFlux Handler
      |  Application logs: validation, errors, domain context
      v
Service / Database / Downstream APIs
      |  Micrometer metrics and distributed trace spans
      v
HTTP response
~~~

| Source | Best used to answer | Does not fully answer |
| --- | --- | --- |
| Proxy/CDN access log | Did the request reach the edge? Cache HIT/MISS? 502/504 from gateway? | Which business logic the Spring controller executed |
| Embedded server access log | Which requests reached the HTTP listener, status/size/duration | Which domain/DB step failed |
| Application logs | Exceptions, business events, validation | Every 404/static resource if code does not explicitly log it |
| Micrometer HTTP metrics | Throughput, duration percentiles, route/status aggregates | Full forensic details of individual requests |
| Distributed traces | Cross-service latency, trace/span correlation | Complete audit if sampled or missing instrumentation |
| Business/security audit | Actor, action, resource, permission, outcome | HTTP byte counts and transport behavior unless recorded |

**A request rejected by WAF will not necessarily appear in Spring logs.** Likewise, an HTTP 200 access line does not guarantee a business operation succeeded. Do not treat access log line counts as unique transaction or user counts because retries, redirects, browser assets, preflights, and proxy hops can generate multiple requests.

## 3. Identify the Actual Embedded Server Before Enabling Logs

### Spring MVC

The dependency:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-web'
~~~

brings **embedded Tomcat** by default in Boot 3.x. Adding `server.jetty.accesslog.enabled=true` while still using Tomcat will not control Tomcat.

To use **Jetty instead of Tomcat**, configure dependencies as:

~~~groovy
implementation('org.springframework.boot:spring-boot-starter-web') {
    exclude group: 'org.springframework.boot',
            module: 'spring-boot-starter-tomcat'
}
implementation 'org.springframework.boot:spring-boot-starter-jetty'
~~~

To use **Undertow instead of Tomcat**:

~~~groovy
implementation('org.springframework.boot:spring-boot-starter-web') {
    exclude group: 'org.springframework.boot',
            module: 'spring-boot-starter-tomcat'
}
implementation 'org.springframework.boot:spring-boot-starter-undertow'
~~~

**These two options are mutually exclusive; do not include both at once.** Keep Boot-managed versions for Jetty/Undertow rather than forcing older dependencies incompatible with Jakarta Servlet.

### Spring WebFlux

The dependency:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-webflux'
~~~

typically runs Spring WebFlux on **Reactor Netty**. If both `spring-boot-starter-web` and `spring-boot-starter-webflux` are present, Boot 3.x usually selects **Servlet MVC**. Therefore, adding WebFlux solely to use `WebClient` does **not** automatically switch the incoming HTTP server to Netty.

A single process can use Tomcat as its server and Reactor Netty as its HTTP client. Reactor Netty's HTTP server access log **does not automatically log outbound `WebClient` calls**. To observe outbound requests, use client observations/tracing or configure separate client logging.

How to verify the server: inspect the dependency tree, startup banner/messages, application context type, and HTTP integration tests—not just property names in `application.properties`.

## 4. Shared Sample Servlet Project to Test All Three Servers

Create a Spring Boot 3.3.13 / Java 17 project. HTTP source code stays the same when switching between Tomcat/Jetty/Undertow; only dependencies and server properties change.

### 4.1. File Tree

~~~text
servlet-access-logging/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/http/ServletAccessApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/demo/http/ServletAccessTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'servlet-access-logging'
~~~

`build.gradle`, default Tomcat:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`src/main/java/demo/http/ServletAccessApplication.java` — **a single runnable Java file**:

~~~java
package demo.http;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ServletAccessApplication {
    public static void main(String[] args) {
        SpringApplication.run(ServletAccessApplication.class, args);
    }
}

@RestController
class ProbeController {

    @GetMapping("/ping")
    Map<String, String> ping() {
        return Map.of("status", "ok");
    }

    @GetMapping("/bad")
    ResponseEntity<Map<String, String>> bad() {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                .body(Map.of("error", "invalid-demo-request"));
    }

    @GetMapping("/slow")
    Map<String, String> slow() throws InterruptedException {
        // LAB ONLY: intentionally slows the request by 80 ms.
        // Do not use Thread.sleep on a request thread in production.
        Thread.sleep(80L);
        return Map.of("status", "slow-ok");
    }
}
~~~

One public class `ServletAccessApplication` and a package-private controller are valid in Java 17. `spring-boot-starter-web` includes Jackson to serialize `Map` to JSON. There is no authentication in the lab; production requires separate Spring Security/authorization.

### 4.2. Testing HTTP After Starting the Server

All server configurations in the following sections use:

~~~properties
server.port=8080
~~~

Run with the Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

If no wrapper exists yet, generate one from a compatible Gradle installation or use an installed `gradle bootRun`.

Call:

~~~bash
curl -i http://localhost:8080/ping
curl -i http://localhost:8080/bad
curl -i http://localhost:8080/missing
curl -i http://localhost:8080/slow
~~~

Expected statuses are **200, 400, 404, 200**, respectively. Logical body of `/ping`:

~~~json
{"status":"ok"}
~~~

And `/bad`:

~~~json
{"error":"invalid-demo-request"}
~~~

Response headers, 404 body, actual timings, and log fields depend on the server and OS. **The goal is to inspect access records across status types**, not to match an illustrative log line with a random timestamp verbatim.

## 5. Tomcat: AccessLogValve, Directory, and Pattern

Tomcat access logging is **off** by default. In `application.properties` of the **Servlet lab using Tomcat**, configure:

~~~properties
server.port=8080

server.tomcat.basedir=./runtime/tomcat
server.tomcat.accesslog.enabled=true
server.tomcat.accesslog.directory=logs
server.tomcat.accesslog.prefix=access_log
server.tomcat.accesslog.suffix=.log
server.tomcat.accesslog.rotate=true
server.tomcat.accesslog.max-days=14

# Method + path without query + protocol + status + bytes + duration
server.tomcat.accesslog.pattern=%t %a "%m %U %H" %s %b %D
~~~

**File location:** relative to the working directory, typically:

~~~text
runtime/tomcat/logs/access_log.<yyyy-MM-dd>.log
~~~

Because `server.tomcat.basedir=./runtime/tomcat` is set, Tomcat does not fall back to a temporary directory for its base. According to Boot documentation, without a fixed base dir or absolute directory, embedded Tomcat may place access logs in a **temp directory**, causing developers to miss them under `./logs`.

### 5.1. Key Tomcat Tokens

| Token | Meaning |
| --- | --- |
| `%t` | Request timestamp in common log format |
| `%a` | Remote address as seen by Tomcat |
| `%h` | Remote hostname/IP |
| `%m` | HTTP method |
| `%U` | URL **path**, excluding query |
| `%q` | Query string; may contain tokens/PII |
| `%r` | Request line (may contain full URL/query) |
| `%H` | HTTP protocol |
| `%s` | Response status |
| `%b` | Bytes sent; `-` if no bytes sent |
| `%B` | Bytes sent as a number |
| `%D` | Duration in **microseconds** on Tomcat 10.1 |
| `%T` | Duration in **seconds** |
| `%{ms}T` | Duration explicitly in **milliseconds** |
| `%{X-Request-ID}o` | Value of the `X-Request-ID` response header if emitted |

Illustrative example line:

~~~text
[08/Nov/2026:09:12:00 +0700] 127.0.0.1 "GET /slow HTTP/1.1" 200 20 85100
~~~

`85100` in the last column is **85,100 microseconds = 85.1 milliseconds**, not 85.1 seconds. The number is not fixed, as it includes HTTP processing overhead beyond the lab's `Thread.sleep(80L)`.

### 5.2. Buffered Output, Rotation, Retention

- `server.tomcat.accesslog.buffered` defaults to `true`: log lines may **not flush immediately** when cURL finishes.
- `file-date-format` adds the date to the filename by default; rotation and prefix/suffix are configured separately.
- `max-days=14` is an example retention setting; default `-1` imposes no day limit via this property.
- `check-exists` helps certain external log rotation/rename scenarios; pick a single rotation owner and test in practice.
- `logging.file.name` controls the regular logging framework and **does not change** where native Tomcat `AccessLogValve` writes its files.

### 5.3. Real Client IP Behind a Proxy

If Spring Boot sits behind NGINX or a load balancer, `%a` may be the proxy IP. Tomcat provides `RemoteIpValve` and properties:

~~~properties
# Use only alongside a verified trusted proxy configuration:
server.forward-headers-strategy=native
server.tomcat.accesslog.request-attributes-enabled=true
~~~

When proxies are properly trusted, `AccessLogValve` can use request attributes populated by `RemoteIpValve`. **Never accept arbitrary `X-Forwarded-For` headers sent by Internet clients** as the real address; the gateway must strip/overwrite untrusted forwarded headers, and Tomcat needs an accurate list of internal/trusted proxies.

### 5.4. Tomcat Troubleshooting

- `logging.level.org.apache.catalina=DEBUG` is set but there is no access log: enabling debug on app/container loggers **does not enable `AccessLogValve`**.
- No file under `./logs`: check `server.tomcat.basedir` and the relative directory.
- Logs do not appear immediately: check buffered flushing and file date rotation.
- Access duration looks huge on dashboards: Tomcat `%D` is in **microseconds** and must be converted to ms.
- Pattern `%r` leaks a query string containing a reset token: switch to `%m %U` and design routes without secrets.
- Running Jetty/Undertow with Tomcat properties configured: wrong namespace for the active server.

## 6. Jetty: RequestLog and System.err When Filename Is Unset

To test **Jetty**, replace the dependencies block in the Servlet lab's `build.gradle` with:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-tomcat'
    }

    implementation 'org.springframework.boot:spring-boot-starter-jetty'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Rebuild/run `bootRun` so Jetty is actually the embedded HTTP server.

### 6.1. Quick Enable to View on stderr

~~~properties
server.port=8080
server.jetty.accesslog.enabled=true
~~~

In Spring Boot 3.3, when `server.jetty.accesslog.filename` is **not configured**, access logs are sent to **`System.err`**—there is no default `logs/jetty-access.log` file to look for.

This is often convenient for Docker/Kubernetes console log collection. However, Jetty logging to `System.err` does not mean it is a Java exception or HTTP 500; that is simply the default output destination for Jetty's access log.

### 6.2. File Configuration and Custom Format

~~~properties
server.port=8080

server.jetty.accesslog.enabled=true
server.jetty.accesslog.filename=logs/jetty-access.log
server.jetty.accesslog.append=true
server.jetty.accesslog.retention-period=14

# Based on org.eclipse.jetty.server.CustomRequestLog
server.jetty.accesslog.custom-format=%{client}a %t "%m %U %H" %s %{ms}T
~~~

Ensure `logs/` is writable. Key Jetty Boot properties:

| Property | Meaning |
| --- | --- |
| `server.jetty.accesslog.enabled` | Enables request logging |
| `server.jetty.accesslog.filename` | File path; if unset → System.err |
| `server.jetty.accesslog.format` | Built-in format, defaults to `ncsa` |
| `server.jetty.accesslog.custom-format` | Jetty `CustomRequestLog` format, **overrides `format`** |
| `server.jetty.accesslog.append` | Appends to file |
| `server.jetty.accesslog.file-date-format` | Date suffix for log rotation |
| `server.jetty.accesslog.retention-period` | Retention in days |
| `server.jetty.accesslog.ignore-paths` | Ignores request paths per Jetty/Boot mechanism |

Jetty `CustomRequestLog` supports `%m`, `%U`, `%s`, `%D`, and `%{ms}T`; in Jetty, `%D` is **microseconds**, while `%{ms}T` outputs milliseconds. Even though many tokens look like Tomcat's, do not blindly copy all syntax or time/date escaping between Jetty and Tomcat without testing.

### 6.3. Embedded Jetty vs. Standalone Jetty

These `server.jetty.accesslog.*` settings apply to **Spring Boot-managed embedded Jetty**. Standalone Jetty uses its own modules/`JETTY_BASE` mechanism and property files. Do not assume enabling the `requestlog` module in a standalone Jetty distribution configures an embedded Boot app.

When `Jetty enabled=true` produces no file, check console stderr first, then verify `filename` and permissions. In containers, writing to a separate file requires a file collector or mounted volume.

## 7. Undertow: accesslog.dir and record-request-start-time

To test **Undertow**, replace the Servlet lab's dependencies block with:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-tomcat'
    }

    implementation 'org.springframework.boot:spring-boot-starter-undertow'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

### 7.1. Basic Access Log Setup

~~~properties
server.port=8080

server.undertow.accesslog.enabled=true
server.undertow.accesslog.dir=logs/undertow
server.undertow.accesslog.pattern=common
server.undertow.accesslog.rotate=true
~~~

In Spring Boot 3.3, Undertow writes files by default under `logs` **relative to the working directory**, unlike Tomcat's `basedir`. Properties include `enabled`, `dir`, `pattern` (defaults to `common`), `prefix` (defaults to `access_log.`), `suffix` (defaults to `log`), and `rotate` (defaults to `true`).

Tomcat `max-days` and Jetty `retention-period` **do not control** Undertow's native log rotation. Define retention policies via your host tooling and configure collectors/disks accordingly.

### 7.2. Proper Configuration When Duration Is Needed

Spring Boot documentation recommends:

~~~properties
server.undertow.accesslog.enabled=true
server.undertow.accesslog.pattern=%t %a %r %s (%D milliseconds)
server.undertow.options.server.record-request-start-time=true
~~~

**Reason:** to record elapsed time `%D`, Undertow needs to capture the **request start time**. Enabling `record-request-start-time=true` adds minor overhead but is required for meaningful durations in the access logger.

Note specifically:

| Column | Tomcat 10.1 | Jetty CustomRequestLog | Undertow (Boot example) |
| --- | --- | --- | --- |
| `%D` | **microseconds** | **microseconds** | **milliseconds** |
| Extra option required to measure %D? | No in example config | No in example config | **Yes: record-request-start-time** |
| Readable millisecond token | `%{ms}T` | `%{ms}T` | `%D` |

If you take `90000` from Tomcat and label it milliseconds, dashboards will misinterpret 90 ms as 90 seconds. Normalize units in your ingestion pipeline.

### 7.3. Example Line, Not Fixed Output

~~~text
[08/Nov/2026:09:30:00 +0700] 127.0.0.1 GET /slow HTTP/1.1 200 (90 milliseconds)
~~~

Actual output varies with request overhead, server formatting, timezone, and client. Patterns containing `%r` can log URL queries: when production URLs are sensitive, choose formatting/redaction suitable for your Undertow version or suppress raw URI logging in a controlled layer.

### 7.4. Undertow Troubleshooting

- `server.tomcat.accesslog.*` is configured while embedded server is Undertow → no effect.
- Forgot `record-request-start-time=true` → `%D` missing or unreliable.
- Relative `dir` resolved from a different working directory than expected in the IDE → looking in the wrong place.
- Read-only filesystem or unmounted volume → logs lost or cannot be written.
- Interpreting Undertow duration as Tomcat microseconds → wrong numbers.
- Pattern logs raw queries containing PII → update data retention and route/log patterns.

## 8. Reactor Netty: Access Logs for the Reactive HTTP Server

Reactor Netty does not use Servlet `AccessLogValve`, Jetty `RequestLog`, or Undertow `AccessLogHandler`. In Spring Boot 3.x using WebFlux with Reactor Netty, there are two ways to enable access logs:

1. **JVM system property**: `-Dreactor.netty.http.server.accessLogEnabled=true`.
2. **Programmatic**: `reactor.netty.http.server.HttpServer.accessLog(true)` via a `NettyReactiveWebServerFactory` customizer.

By default, Reactor Netty HTTP access logging is **off**.

### 8.1. The System Property Is a JVM Option, Not a Boot Application Property

Example after building the JAR:

~~~bash
java -Dreactor.netty.http.server.accessLogEnabled=true \
  -jar build/libs/reactive-access-logging-1.0.0.jar
~~~

`-D...=true` must appear **before `-jar`**. Placing it after the JAR makes it an application argument instead of a JVM system property.

**Do not confuse this with:**

~~~properties
# NOT a Boot 3.3 accesslog namespace property:
reactor.netty.http.server.accessLogEnabled=true
~~~

in `application.properties`. Setting `logging.level.reactor.netty.http.server.AccessLog=INFO` only lets the logger emit messages if the access logger is already enabled; it **does not activate the generator**. Setting `logging.level.reactor.netty=DEBUG` or enabling `wiretap` is also not equivalent to an access log; wiretap can expose sensitive headers and payloads.

### 8.2. Logger Name

Reactor Netty uses the logger:

~~~text
reactor.netty.http.server.AccessLog
~~~

to emit HTTP access entries through the logging framework (SLF4J/Logback typically bundled with Spring Boot). If the default appender writes to the console, you can see them directly; to write a separate file, configure a dedicated appender as shown in the next section. Do not set `server.tomcat.accesslog.directory` for Reactor Netty expecting it to do anything.

## 9. WebFlux Reactor Netty: Runnable Java 17+ Project

### 9.1. Structure

~~~text
reactive-access-logging/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/reactivelog/ReactiveAccessApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/demo/reactivelog/ReactiveAccessTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'reactive-access-logging'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}

tasks.named('bootRun') {
    // Dedicated JVM running the app receives this system property.
    systemProperty 'reactor.netty.http.server.accessLogEnabled', 'true'
}
~~~

`application.properties`:

~~~properties
server.port=8082
logging.level.reactor.netty.http.server.AccessLog=INFO
~~~

File `src/main/java/demo/reactivelog/ReactiveAccessApplication.java`:

~~~java
package demo.reactivelog;

import java.time.Duration;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class ReactiveAccessApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveAccessApplication.class, args);
    }
}

@RestController
class ReactiveProbeController {

    @GetMapping("/ping")
    Mono<Map<String, String>> ping() {
        return Mono.just(Map.of("status", "ok"));
    }

    @GetMapping("/bad")
    Mono<ResponseEntity<Map<String, String>>> bad() {
        return Mono.just(ResponseEntity.status(HttpStatus.BAD_REQUEST)
                .body(Map.of("error", "invalid-demo-request")));
    }

    @GetMapping("/slow")
    Mono<Map<String, String>> slow() {
        // Reactive timer: no Thread.sleep on the event loop.
        return Mono.delay(Duration.ofMillis(80))
                .map(ignored -> Map.of("status", "slow-ok"));
    }
}
~~~

**Single runnable Java file:** one public main class and one package-private controller. Only `spring-boot-starter-webflux` is present, so Boot 3.3 runs WebFlux on Reactor Netty. Do not add `starter-web` to this project if you want to be sure the server is Netty.

### 9.2. Running with bootRun

~~~bash
./gradlew bootRun
~~~

The `tasks.named('bootRun')` block sets the JVM system property. Hit the endpoints:

~~~bash
curl -i http://localhost:8082/ping
curl -i http://localhost:8082/bad
curl -i http://localhost:8082/missing
curl -i http://localhost:8082/slow
~~~

Expected statuses **200/400/404/200**. The Reactor Netty access logger will be active in the app JVM unless disabled/overridden by a customizer, provided the logging framework accepts the logger at INFO.

### 9.3. Running from an Executable JAR

~~~bash
./gradlew bootJar

java -Dreactor.netty.http.server.accessLogEnabled=true -jar build/libs/reactive-access-logging-1.0.0.jar
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootJar
java -Dreactor.netty.http.server.accessLogEnabled=true -jar .\build\libs\reactive-access-logging-1.0.0.jar
~~~

The JAR name is an example from Gradle's project name/version; if the build artifact is renamed, use the actual file in `build/libs`. Do not use `./gradlew bootRun --args=...` to pass a JVM system property because `--args` sets application arguments.

## 10. Reactor Netty: Logback File and Programmatic Configuration

### 10.1. Writing the Access Logger to a Separate File

If you do not want access records mixed into the application console, create `src/main/resources/logback-spring.xml` in the **WebFlux project**:

~~~xml
<configuration>
    <include resource="org/springframework/boot/logging/logback/defaults.xml"/>

    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ACCESS_FILE"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/reactor-access.log</file>
        <rollingPolicy class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>logs/reactor-access.%d{yyyy-MM-dd}.log</fileNamePattern>
            <maxHistory>7</maxHistory>
        </rollingPolicy>
        <encoder>
            <pattern>%msg%n</pattern>
        </encoder>
    </appender>

    <logger name="reactor.netty.http.server.AccessLog"
            level="INFO" additivity="false">
        <appender-ref ref="ACCESS_FILE"/>
    </logger>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Access log messages go to `logs/reactor-access.log` when enabled. Normal application logs continue going to the console. Requires write permission on `logs` and separate rotation/shipping. In containers with stdout/stderr collectors, a file appender is only appropriate if a volume/tailer exists; do not assume a file is automatically better than console output.

This XML file is an example for small apps; if your organization already maintains `logback-spring.xml`, structured JSON, or async appenders, **integrate only the AccessLog logger into your existing config** instead of replacing the entire file. Spring Boot's `logging.file.name` alone does not enable the Netty access logger.

### 10.2. Configuring via WebServerFactoryCustomizer

Instead of a system property, you can enable it using Spring Boot 3.3 Java config. File `src/main/java/demo/reactivelog/NettyAccessConfig.java`:

~~~java
package demo.reactivelog;

import org.springframework.boot.web.embedded.netty.NettyReactiveWebServerFactory;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class NettyAccessConfig {

    @Bean
    WebServerFactoryCustomizer<NettyReactiveWebServerFactory>
            nettyAccessLogCustomizer() {

        return factory -> factory.addServerCustomizers(
                server -> server.accessLog(true));
    }
}
~~~

`NettyReactiveWebServerFactory.addServerCustomizers` lets you customize the `reactor.netty.http.server.HttpServer` builder. `accessLog(true)` enables the generator; **programmatic config takes precedence over the system property**. Do not expect both sources to emit two independent log copies.

When using this Java config, you can remove `bootRun.systemProperty` for access logging so the policy is managed in code.

### 10.3. Custom Format and Stripping Query from URI

A sample **replacing the customizer's return expression**, requiring import `reactor.netty.http.server.logging.AccessLog`:

~~~java
return factory -> factory.addServerCustomizers(server ->
        server.accessLog(true, args -> {
            String uri = String.valueOf(args.uri());
            int q = uri.indexOf('?');
            String path = q < 0 ? uri : uri.substring(0, q);

            return AccessLog.create(
                    "method={} path={} status={}",
                    args.method(), path, args.status());
        }));
~~~

This uses `HttpServer.accessLog(boolean, AccessLogFactory)`. It does not use Tomcat/Jetty format tokens. Stripping the query lowers the risk of logging reset tokens, emails, or secrets in query strings, **but paths can still contain personal data** (`/users/alice@example.test`). Production needs route template allowlisting/normalization, not merely stripping after `?`.

`AccessLogFactory.createFilter(...)` also supports skipping certain health-check paths to reduce volume, though do not filter out all 401/403/5xx entries just to "reduce logs". When skipping health events, keep corresponding metrics and ensure the filter cannot be fooled by spoofed health-like URLs.

## 11. Key Comparison Table

| Item | Tomcat | Jetty | Undertow | Reactor Netty |
| --- | --- | --- | --- | --- |
| Enable | `server.tomcat.accesslog.enabled` | `server.jetty.accesslog.enabled` | `server.undertow.accesslog.enabled` | JVM `reactor.netty.http.server.accessLogEnabled` |
| Default enabled | false | false | false | false |
| Layer | Tomcat AccessLogValve | Jetty RequestLog/CustomRequestLog | Undertow access handler | Reactor Netty HttpServer accessLog |
| Default output when enabled | File under Tomcat basedir/logs | **System.err** if filename empty | Files under working-dir/logs | SLF4J logger AccessLog |
| Change file | directory/prefix/suffix | filename | dir/prefix/suffix | Logback/Log4j2 appender |
| Customize format | accesslog.pattern | custom-format | accesslog.pattern | AccessLogFactory |
| Duration | `%D` microseconds | `%D` microseconds, `%{ms}T` milliseconds | `%D` milliseconds when start-time enabled | Netty's formatter/metrics |
| Rotation/retention | rotate/max-days | filename/date/retention-period | rotate and ops policy | logging appender/collector |
| Common pitfall | basedir may be a temp dir | no file when filename unset | requires record-request-start-time for `%D` | lacks Servlet-style Boot accesslog.* namespace |

Do not put raw latency numbers from these four log formats onto a shared `duration_ms` dashboard before verifying and normalizing units. Nor does an app access log measure the exact same interval as gateway upstream time or browser performance timing.

## 12. Avoiding Credentials and Personal Data in Access Logs

Some common/combined log patterns include `%r` (request line) or `%q` (query string), and queries can carry sensitive data:

~~~http
GET /reset-password?token=example-secret HTTP/1.1
Authorization: Bearer example-token
Cookie: SESSION=example-session
~~~

Do not log these values in real logs. Avoid:
- Raw `Authorization`, `Cookie`, and `Set-Cookie`.
- Reset tokens, OTPs, API keys, and access tokens in queries/paths.
- Request/response bodies containing private data, passwords, or payment cards.
- Session IDs (such as Tomcat `%S`) without business/policy justification.
- Uncontrolled full User-Agent/Referer/X-Forwarded-* headers without a clear purpose.
- Log injection through unescaped client-controlled values.

Tomcat can log path-only using `%m %U %H` instead of `%r`. Jetty supports `%U`. Undertow and Reactor Netty require checking formatters/sanitization per version; Reactor Netty supports a custom `AccessLogFactory`. **Stripping queries is not enough if paths contain PII or tokens.** Designing secret-free URLs is the first step.

### Log Privacy and Retention

- Define who can view logs and why IPs/paths are needed.
- Enforce retention limits, volume permissions, encryption at rest, and central logging controls.
- Never paste raw bearer/session tokens into issue trackers.
- If logs already accidentally captured secrets, fixing the pattern for new logs does not erase old ones; execute incident/credential rotation and retention cleanup as needed.
- Do not assume `no-store` HTTP `Cache-Control` protects access logs: HTTP caching and log persistence are two separate mechanisms.

## 13. Reverse Proxies, Client IP, and Forwarded Headers

~~~text
Client 203.0.113.50
       |
       v
Reverse proxy 10.0.0.20
       |
       v
Spring Boot 10.0.0.30
~~~

The Spring origin may record `10.0.0.20` because that is the TCP peer, not the browser. A proxy can pass `Forwarded`/`X-Forwarded-For`, yet those headers **can be spoofed** if the server blindly trusts Internet input.

Security requirements:

1. The edge reverse proxy must strip/overwrite forwarded headers sent by untrusted clients.
2. Configure trusted proxies/CIDR ranges/`RemoteIpValve` matching actual topology.
3. Tomcat `server.tomcat.accesslog.request-attributes-enabled=true` lets the access valve read attributes set by a trust-aware `RemoteIpValve`.
4. Choose `server.forward-headers-strategy=native` or `framework` based on your server and infrastructure, never by guesswork.
5. Across multiple hops, client IP selection needs a clear policy rather than blindly grabbing the first IP in `X-Forwarded-For`.
6. Keep edge access logs and origin access logs distinct via `layer`, `service`, `instance`, and correlation IDs.
7. IP addresses may be personal data; evaluate retention/permissions and privacy requirements.

A 502/504 or 429 may be generated by the gateway before Spring, resulting in **no origin access log**. Do not assume Spring's log writer is broken if the request never reached the origin.

## 14. Correlation ID: Linking Access Logs with Application Logs

Typically the access log records "GET /orders/42 → 500", while the Spring application log holds the stack trace. To join both records, you need a controlled, propagated request ID or trace ID.

~~~text
Gateway generates trusted request ID
          |
          v
Spring filters / WebFlux context
          |
          +-> app logs, traces, response header
          +-> access log if its formatter includes the ID
          +-> downstream correlation
~~~

An `X-Request-ID` sent by an arbitrary client is **not trustworthy by default**. Validate length/charset/allowlist at the gateway or generate a fresh ID.

### Demo Servlet Filter Generating a New UUID

In the Servlet lab, add `src/main/java/demo/http/RequestIdFilter.java`:

~~~java
package demo.http;

import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class RequestIdFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        String id = UUID.randomUUID().toString();
        response.setHeader("X-Request-ID", id);

        MDC.put("requestId", id);
        try {
            chain.doFilter(request, response);
        } finally {
            MDC.remove("requestId");
        }
    }
}
~~~

This is a runnable Java class when added to package `demo.http` with `spring-boot-starter-web`. The lab **generates a new UUID at the origin** rather than trusting client headers. Tomcat access logs can record the ID from the response header:

~~~properties
server.tomcat.accesslog.pattern=%t "%m %U" %s %{X-Request-ID}o
~~~

Jetty `CustomRequestLog` also supports response header format `%{X-Request-ID}o`; test against your Jetty version. For Undertow, check its corresponding exchange attribute syntax instead of assuming Tomcat tokens apply.

**MDC in a Servlet filter does not automatically propagate across all async workers**; Reactor Context/Micrometer Tracing use different mechanisms in WebFlux. Nor does a response header automatically become a trace ID in an APM without instrumentation. Standardized tracing such as W3C Trace Context complements request IDs.

## 15. Duration and Size: Do Not Over-Interpret

### 15.1. Timing

If column `%D` equals 100000:

- Tomcat 10.1: **100000 µs = 100 ms**.
- Jetty: `%D` is defined in microseconds.
- Undertow (pattern in Boot docs): **100000 ms**, if `record-request-start-time` is enabled.
- Reactor Netty: uses its own logger/custom factory/metrics, without a shared Tomcat `%D` grammar.

Server access duration does not necessarily include browser DNS/TLS, edge queues, CDN cache waits, client rendering, or every individual downstream service. It can also include response write time depending on implementation. To pinpoint real bottlenecks, combine edge timings, server metrics, and distributed trace spans.

### 15.2. Bytes

Tomcat's `%b` is bytes sent, not UTF-16 characters or Java String lengths. With gzip, HTTP/2, chunked transfer, or aborted responses, verify byte semantics and measurement points per server/version. Never treat access-log byte counts as business record counts.

### 15.3. Long-Lived Streaming

SSE, streaming downloads, and HTTP long-polling hold responses open for long durations. Access logs are normally written **when the response completes**, not one line per `Flux` element or SSE event. Thus, not seeing an access log immediately does not mean the server never received the request. Track active connections/streams metrics as well.

HTTP WebSocket upgrades have their own lifecycle; status 101 or log timing varies by server/handshake. Never assume HTTP access logs observe individual WebSocket messages.

## 16. HTTP Integration Testing with TestRestTemplate (Servlet)

Create `src/test/java/demo/http/ServletAccessTest.java`:

~~~java
package demo.http;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class ServletAccessTest {
    @Autowired
    TestRestTemplate rest;

    @Test
    void pingIs200() {
        ResponseEntity<String> r =
                rest.getForEntity("/ping", String.class);
        assertThat(r.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(r.getBody()).contains("ok");
    }

    @Test
    void badIs400() {
        ResponseEntity<String> r =
                rest.getForEntity("/bad", String.class);
        assertThat(r.getStatusCode())
                .isEqualTo(HttpStatus.BAD_REQUEST);
    }

    @Test
    void missingIs404() {
        ResponseEntity<String> r =
                rest.getForEntity("/missing", String.class);
        assertThat(r.getStatusCode())
                .isEqualTo(HttpStatus.NOT_FOUND);
    }
}
~~~

Run with the Tomcat dependency, or swap to Jetty/Undertow **one server at a time**:

~~~bash
./gradlew test --tests demo.http.ServletAccessTest
~~~

The test uses an embedded web server on a random HTTP port and checks real statuses. **It does not yet prove the access log file/stderr received a record**, since it does not inspect log files and buffered writers may not have flushed. To verify access logging, run the app with the relevant config and inspect the log destination after cURL, using appropriate polling/waiting for async flushes.

## 17. Testing WebFlux with WebTestClient

In the WebFlux project, create `src/test/java/demo/reactivelog/ReactiveAccessTest.java`:

~~~java
package demo.reactivelog;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveAccessTest {
    @Autowired
    WebTestClient client;

    @Test
    void pingIs200WithJson() {
        client.get().uri("/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.status").isEqualTo("ok");
    }

    @Test
    void missingIs404() {
        client.get().uri("/missing")
                .exchange()
                .expectStatus().isNotFound();
    }
}
~~~

Run:

~~~bash
./gradlew test --tests demo.reactivelog.ReactiveAccessTest
~~~

**Note:** the `bootRun.systemProperty` block applies only to the `bootRun` task. Gradle tests run in a separate JVM, so passing HTTP tests do not mean the access logger was enabled in the test JVM. To test access-log emission, run the app/bootJar with the `-D` JVM flag or configure the system property on the test task as needed and inspect the logger output.

## 18. Log Verification Workflow on Hosts and Containers

### 18.1. Verifying at the Origin

1. Confirm the embedded server, build artifact, and dependency tree.
2. Enable the right namespace/system property; ensure the output destination is writable.
3. Restart the process. Do not rely on source hot-reload when a setting requires server re-initialization.
4. Use `curl -i` to call `/ping`, `/bad`, `/missing`, and `/slow`.
5. Look for logs in the **right place** for that server; do not look for a Jetty file when Jetty writes to stderr.
6. Verify status codes and duration units, then compare sample lines against the active pattern.
7. Check whether queries/secrets are logged using **dummy data**; never put real credentials into test logs.
8. When behind a proxy, compare direct origin calls against calls through the public hostname.
9. Test rotation, permissions, disk-full handling, and log shipping across restarts and rolling deploys.

Linux/macOS examples for the lab setup:

~~~bash
# Tomcat
find runtime/tomcat/logs -type f -name 'access_log*.log'
tail -f runtime/tomcat/logs/access_log*.log

# Jetty if filename is set
tail -f logs/jetty-access.log

# Undertow
find logs/undertow -type f

# Reactor Netty with the created logback-spring.xml
tail -f logs/reactor-access.log
~~~

Windows PowerShell:

~~~powershell
Get-ChildItem .\runtime\tomcat\logs\access_log*.log
Get-Content .\logs\reactor-access.log -Tail 20 -Wait
~~~

Relative paths resolve from the **process working directory**, not necessarily the source directory. IDEs, Gradle, Windows services, systemd, and Docker each have different working directories.

### 18.2. Containers/Kubernetes

- Jetty enabled without a filename writes to `System.err`, which container log collectors pick up.
- Reactor Netty with an SLF4J console appender is picked up by collectors; a file appender requires a volume/tailer.
- Tomcat/Undertow native access logs usually write to files and **do not appear automatically in `kubectl logs`**.
- Pod filesystems are ephemeral: files disappear when pods are replaced; ship logs or mount volumes properly.
- Both edge logs and origin logs are useful, but require a `layer` field to avoid counting one HTTP call multiple times.
- Estimate ingestion/indexing capacity, set sensible retention, and restrict unauthorized access to logs.

**Hypothetical capacity math:** 1,000 req/s × 200 bytes/log ≈ 200,000 bytes/s ≈ 17.28 GB/day raw data (decimal), before indexing or replicas. Real traffic and log sizes vary and must be measured.

## 19. Troubleshooting by Server and Symptom

| Symptom | Common cause | Check |
| --- | --- | --- |
| Tomcat access log enabled, file not found | Temp basedir, wrong directory, buffered writer | basedir/directory, working directory, flush |
| Jetty enabled, no file | filename unset so logging goes to System.err | Check stderr or configure a writable filename |
| Undertow not writing | App still running Tomcat or dir lacks permissions | Dependency exclusion, server runtime, dir |
| Undertow %D missing/invalid | Start-time recording disabled | `record-request-start-time=true` |
| Netty has no access records | Property placed in application.properties instead of JVM -D; logger filtered | System property before -jar, logger/appender |
| Heavy console DEBUG output, no access log | Debug/wiretap is not the HTTP access logger | Enable the actual access log generator |
| Jetty writes file but lacks latency | Default NCSA omits duration | custom-format with `%{ms}T` |
| Dashboard duration off by 1000x | Mixing microseconds and milliseconds | Normalize per server/pattern |
| 404 missing from origin log | Gateway blocked request or filtered path | Compare edge vs. origin |
| `Client IP` is the load balancer | Missing trusted forwarded config | Trusted proxies, RemoteIpValve |
| Client IP can be spoofed | Trusting raw X-Forwarded-For from Internet | Strip/overwrite headers at gateway |
| Just ran cURL, no line visible yet | Buffered/async file writer | Wait for flush and check file date |
| HTTP 504 at edge, nothing at origin | Proxy timeout/error before origin | Gateway error/access logs |
| Access log contains reset token | `%r`/`%q` or full URI logged | Remove query/route secrets, incident cleanup |
| Outbound WebClient missing | Server access log is not client log | Client metrics/tracing |
| SSE has no access line yet | Stream has not ended | Active stream metrics and completion |
| App includes 2 server starters | Boot selected a different server than expected | Verify actual runtime/dependencies |
| File logging disappears after deploy | Ephemeral filesystem, no log shipper | Mount/collector/retention |

Never "fix" missing access logs by enabling payload wiretaps in production: that creates high privacy risk. Instead, verify the proper logger and output destination.

## 20. Logging Overhead, Retention, and High-Traffic Operation

Access loggers consume resources formatting metadata, writing to files/stderr, flushing, rotating, and shipping. Long-lived streams may only log on completion. Under high traffic:

- Keep fields minimal; never log raw bodies or headers containing secrets.
- Monitor appenders/queues/collectors; async logging risks dropping logs when queues fill or processes crash.
- Rotation and retention belong to the **exact server/logging framework** in use. Tomcat native rotation is not Logback; Netty Logback files are not Undertow rotation.
- Monitor file descriptors, disk usage, shipper backlog, dropped logs, and I/O latency.
- Keep 401/403/5xx logs because they are vital for security—do not drop all errors merely to cut costs.
- Optionally filter out health checks while keeping metrics, and ensure filters do not accidentally ignore attack traffic disguised as health paths.
- When shipping logs through a collector, standardize fields like `timestamp`, `service`, `instance`, `layer`, `method`, `route/path`, `status`, `duration_ms`, `trace_id` with redaction.
- Benchmark throughput and p95/p99 latency with logging enabled vs. disabled under realistic load; test rolling restarts and disk-full behavior.

### Access Logs Are Not Security Audits

An HTTP server log showing `GET /orders/42 200` does not prove "the authorized user read that order". Business audits require a trusted authenticated actor, action, resource, outcome, retention, and tamper resistance per policy. You can link both via trace/request IDs, but never log bearer or session tokens.

## 21. Pre-Release Checklist

1. Which server is actually running: Tomcat, Jetty, Undertow, or Reactor Netty?
2. Does the configuration match the active dependency and namespace/system property?
3. Do you know whether logs land in Tomcat basedir files, Jetty stderr/files, Undertow dir, or the Netty logger?
4. Does the format include useful method/path/status/duration fields with accurate units?
5. Are queries, cookies, Authorization, PII/tokens, or request bodies excluded?
6. Do client IP and Forwarded headers enforce trust boundaries and prevent spoofing?
7. Are rotation, retention, writable directories, permissions, log shipping, and disk limits configured?
8. Have you observed 200/400/404, proxy errors, and streaming/long-lived requests?
9. Are edge and origin records distinguished for the same request to avoid double counting?
10. Are app logs, tracing, and Micrometer configured alongside access logs to diagnose root causes?
11. Did you test with real HTTP requests rather than controller unit tests alone?
12. Are operators documented on where to find logs, how to adjust formats, roll back, and handle PII incidents?
13. When using a Reactor Netty customizer, is there a single clear enablement source without conflicting JVM properties and code?
14. For Undertow `%D`, is `server.undertow.options.server.record-request-start-time` enabled?
15. Are you referencing the matching version's docs rather than applying Tomcat 9/Boot 2 syntax to Boot 3.3?

## 22. Self-Check Questions

**1.** An app has `spring-boot-starter-web` and `server.jetty.accesslog.enabled=true`, yet logs nothing. Why?

**Answer:** `starter-web` runs Tomcat by default. Either use the Tomcat namespace or swap dependencies to Jetty and exclude `starter-tomcat`.

**2.** Tomcat access logging is enabled, but `./logs/access_log` does not exist. Where should you look?

**Answer:** Check `server.tomcat.basedir` and `server.tomcat.accesslog.directory`; Tomcat's base dir may be a temporary directory.

**3.** Where does Jetty write when enabled without configuring `filename`?

**Answer:** `System.err` in Spring Boot 3.3. It does not automatically create `logs/jetty-access.log`.

**4.** Which property is needed for Undertow to log duration `%D`?

**Answer:** `server.undertow.options.server.record-request-start-time=true`.

**5.** Are `%D` in Tomcat and Undertow both milliseconds?

**Answer:** No. Tomcat 10.1 uses microseconds, whereas Undertow in the Boot example uses milliseconds. Jetty supports `%D` in microseconds and `%{ms}T` in milliseconds.

**6.** Is setting `logging.level.reactor.netty=DEBUG` enough to turn on Netty server access logs?

**Answer:** No. Enable JVM `-Dreactor.netty.http.server.accessLogEnabled=true` or `HttpServer.accessLog(true)`, and ensure the logging framework accepts the logger.

**7.** Can you enable Netty access logs via `application.properties` using the same JVM option name?

**Answer:** Not by default. `reactor.netty.http.server.accessLogEnabled` is a JVM system property, not a Boot 3.3 bound server accesslog property.

**8.** Why does Spring have no access log line for a 504 response seen in the browser?

**Answer:** The gateway may have generated the 504 before the origin responded; inspect edge logs and request paths.

**9.** Is setting Tomcat pattern `%r` safe for a password-reset API that passes a token in the query string?

**Answer:** High risk, because the request line normally includes the query string. Avoid tokens in URLs, use path-only fields, or apply proper redaction.

**10.** An SSE stream has been open for 5 minutes with no access log line yet—does that mean the server didn't receive the request?

**Answer:** No. Access log records are typically emitted when the response completes; use active stream metrics as well.

**11.** Does Reactor Netty's HTTP server access log track all outbound `WebClient` requests?

**Answer:** No; HTTP server logs are separate from client-side observability.

**12.** Is `X-Forwarded-For` from an Internet client trustworthy enough to record as the "real IP"?

**Answer:** No. Trust only controlled proxies; the gateway must strip/overwrite headers and the server must handle trusted proxy ranges.

## 23. Official Reference Documentation

- [Spring Boot 3.3 – Configure Access Logging](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): guides for Tomcat, Jetty, Undertow, log locations, and Undertow timing.
- [Spring Boot 3.3 – Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): native access logging properties for the three Servlet servers, logging, and forwarded headers.
- [Apache Tomcat 10.1 – AccessLogValve](https://tomcat.apache.org/tomcat-10.1-doc/config/valve.html): `%m/%U/%r/%q/%s/%D` tokens, units, `RemoteIpValve`, and request attributes.
- [Jetty 12 – CustomRequestLog API](https://jetty-project.github.io/javadoc.jetty.org/jetty-12/org/eclipse/jetty/server/CustomRequestLog.html): custom patterns, latency, and response header fields.
- [Jetty 12 – Request Logging Module](https://jetty.org/docs/jetty/12/operations-guide/modules/standard.html): NCSA request logs and file handling.
- [Undertow – UndertowOptions source](https://github.com/undertow-io/undertow/blob/main/core/src/main/java/io/undertow/UndertowOptions.java): `RECORD_REQUEST_START_TIME` option.
- [Reactor Netty 1.1 – HTTP Access Log Reference](https://docs.spring.io/projectreactor/reactor-netty/docs/1.1.15/reference/html/): system property, logger, file appender, and programmatic `accessLog`.
- [Spring Boot 3.3 – NettyReactiveWebServerFactory API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/embedded/netty/NettyReactiveWebServerFactory.html): `addServerCustomizers`.
- [Reactor Netty – AccessLogFactory API](https://docs.spring.io/projectreactor/reactor-netty/docs/1.1.4/api/reactor/netty/http/server/logging/AccessLogFactory.html): custom formatting and filters.
- [Spring Boot – Logging Features](https://docs.spring.io/spring-boot/3.3/reference/features/logging.html): app console/file logs vs. native access logs.
- [Micrometer Tracing](https://docs.micrometer.io/tracing/reference/): correlation and distributed spans.

**Conclusion:** access logs belong to the **actual running HTTP server**, not to individual controllers. Tomcat, Jetty, and Undertow use three distinct `server.*.accesslog.*` namespaces; Reactor Netty uses a JVM system property or `HttpServer.accessLog(...)` plus the logging framework. Proper configuration must cover **output destination, privacy/redaction, trusted proxies, duration units, retention, and verification via real HTTP requests**.