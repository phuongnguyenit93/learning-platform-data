# Evaluating Servlet or Reactive Support by Server and Version

## 1. Objectives and Scope

A Spring Boot project can serve HTTP using **Spring MVC (Servlet stack)** or **Spring WebFlux (reactive stack)**. Choosing a server is not merely picking Tomcat, Jetty, Undertow, or Netty: you must simultaneously check the Spring Boot version, server version, supported Jakarta Servlet level, processing model, and actual dependencies.

This lesson provides an evidence-based evaluation method, focusing on the representative lines **Spring Boot 2.7, 3.2, 3.5, and 4.0/4.1**, along with differences during upgrades. Server version numbers in the tables represent **the version lines integrated or supported by Spring Boot**, not a guarantee that every patch release in that line is compatible with every Spring Boot release. Always rely on the BOM/parent and documentation for the **exact Boot version you are running**.

Questions to answer when assessing a combination:

1. Does the server provide a **Servlet API** version sufficient for Spring MVC?
2. Can it run **Spring WebFlux** via non-blocking I/O or a corresponding adapter?
3. Does the Spring Boot version in use have an official **starter and auto-configuration** for that server?
4. Are Java, the **javax.servlet / jakarta.servlet** namespace, libraries, and the deployment environment aligned?
5. Does the actual server version resolved by Maven/Gradle match dependency management and security requirements?

## 2. Distinguishing HTTP Server, Servlet, and Reactive

### Servlet Stack: Spring MVC

In Spring MVC, HTTP requests pass through a **Servlet container**, a Filter chain, and DispatcherServlet. Controllers can interact with Servlet APIs when needed. Tomcat, Jetty, and (for Boot lines that still support it) Undertow are familiar embedded Servlet containers.

Servlet is an API specification, whereas Tomcat/Jetty/Undertow are concrete implementations. A server can support HTTP without being a Servlet container. Therefore, **Reactor Netty is not used to run Spring MVC under the Servlet stack**.

### Reactive Stack: Spring WebFlux

Spring WebFlux uses **Reactive Streams**, Publishers, and a non-blocking HTTP processing API. In Spring Boot, **Reactor Netty** is the default HTTP server for the WebFlux starter. WebFlux can also run on **Tomcat or Jetty** through a non-blocking Servlet I/O bridge. In Spring Boot 2.x/3.x, Undertow was also a supported option; this changes in Boot 4.x.

Key distinction: **Running WebFlux on Tomcat does not turn Tomcat into Reactor Netty**, nor does it mean the application uses Servlet MVC. WebFlux still uses the reactive programming model, with Tomcat serving as the underlying runtime.

**Being capable of non-blocking I/O** does not mean the entire application is non-blocking. A WebFlux controller that calls synchronous JDBC or blocks on the event loop can still cause stalls.

### Three Independent Compatibility Layers

| Layer | What to check | Example |
|---|---|---|
| Framework/Boot | Spring MVC or WebFlux; supported starter/auto-configuration | Boot 3.5 has the Undertow starter; Boot 4.x does not |
| Runtime | Tomcat, Jetty, Undertow, Reactor Netty and exact version | Tomcat 10.1 differs from Tomcat 11.0 |
| API/platform | Java, Servlet specification, javax/jakarta, and dependencies | Boot 4.x uses the Servlet 6.1 baseline |

If any of these three layers is version-mismatched, the server being able to open an HTTP port still does not guarantee the application will start or operate properly.

## 3. Embedded Server Matrix by Spring Boot Line

The table below is compiled from Spring Boot's **System Requirements** and **Embedded Web Servers** documentation. **Boot 3.0/3.1** had differences in early 3.x releases; do not extrapolate from the Boot 3.2/3.5 rows to draw conclusions for 3.0/3.1.

| Spring Boot line | Minimum Java | Tomcat for Servlet | Jetty for Servlet | Undertow for Servlet | Default WebFlux server |
|---|---:|---|---|---|---|
| **2.7.x** | 8 | **9.0**, Servlet **4.0** | **9.4**, Servlet **3.1**; or **10.0**, Servlet **4.0** | **2.0**, Servlet **4.0** | **Reactor Netty** |
| **3.2.x** | 17 | **10.1**, Servlet **6.0** | **12.0**, Servlet **6.0** | **2.3**, Servlet **6.0** | **Reactor Netty** |
| **3.5.x** | 17 | **10.1**, Servlet **6.0** | **12.0**, Servlet **6.0** | **2.3**, Servlet **6.0** | **Reactor Netty** |
| **4.0.x** | 17 | **11.0.x**, Servlet **6.1** | **12.1.x**, Servlet **6.1** | **No embedded support in Boot 4** | **Reactor Netty** |
| **4.1.x** | 17 | **11.0.x**, Servlet **6.1** | **12.1.x**, Servlet **6.1** | **No embedded support in Boot 4** | **Reactor Netty** |

**How to read the table properly:**

- The Servlet column shows the **Servlet specification version** associated with the server per Boot docs, not the Spring Framework version.
- Reactor Netty is a non-Servlet HTTP server, so that column has **no Servlet specification**.
- WebFlux is not restricted to Reactor Netty: it also runs on supported Tomcat and Jetty, and on Undertow in Boot lines where the Undertow starter still exists.
- For **Boot 2.7**, the application namespace is **javax.servlet**. From **Boot 3.x**, applications moved to **jakarta.servlet**. Changing only the server version while keeping old imports can cause class-loading or compilation errors.
- **Boot 4.x requires Servlet 6.1** for the servlet stack; Undertow does not meet that baseline within Boot 4's official support scope, so the Undertow starter and embedded Undertow support were removed.
- For **Boot 3.0/3.1**, read the exact system requirements, release notes, and dependency management for the deployed patch version; do not assume every 3.x release shares the same server matrix.

**Official version sources:**
- Boot 2.7.18: https://docs.spring.io/spring-boot/docs/2.7.x/reference/htmlsingle/
- Boot 3.2.x: https://docs.spring.io/spring-boot/docs/3.2.12/reference/htmlsingle/
- Boot 3.5.x: https://docs.spring.io/spring-boot/3.5/system-requirements.html
- Boot 4.0.x: https://docs.spring.io/spring-boot/4.0/system-requirements.html
- Boot 4.1.x: https://docs.spring.io/spring-boot/system-requirements.html

Branch-scoped links may update to newer patch versions; when you need to reproduce an environment precisely, refer to the documentation tied to your application's exact patch version.

## 4. Servlet vs. WebFlux Selection Matrix by Server

Legend in table: **Yes** = Boot provides corresponding server integration; **No** = wrong runtime kind or no longer officially supported by Boot. A **Yes** cell still requires using the exact server version managed by Boot.

| Server | Spring MVC / Servlet on Boot 2.7 | Spring WebFlux on Boot 2.7 | Spring MVC / Servlet on Boot 3.5 | Spring WebFlux on Boot 3.5 | Spring MVC / Servlet on Boot 4.x | Spring WebFlux on Boot 4.x |
|---|---|---|---|---|---|---|
| **Tomcat** | Yes | Yes via non-blocking Servlet adapter | Yes | Yes via adapter | Yes | Yes via adapter |
| **Jetty** | Yes | Yes via non-blocking Servlet adapter | Yes | Yes via adapter | Yes | Yes via adapter |
| **Undertow** | Yes | Yes via Spring reactive integration | Yes | Yes via Spring reactive integration | **No** | **No** |
| **Reactor Netty** | **No** | Yes, default | **No** | Yes, default | **No** | Yes, default |

From this table we can derive decision rules:

- **MVC + synchronous JDBC/JPA** apps: prefer default Tomcat; Jetty is a compatible alternative, Undertow only while Boot still supports it.
- **Non-blocking WebFlux** apps: Reactor Netty is the default choice; Tomcat/Jetty remain valid if infrastructure standardization is required.
- Apps currently using **Undertow** and planning to move to **Boot 4**: plan to switch the HTTP server prior to upgrading.
- **Netty itself** has its own event loop and I/O APIs; it does not implement the Servlet API to run DispatcherServlet under the Spring MVC model.

## 5. Individual Server Assessments

### 5.1. Apache Tomcat

**Spring MVC:** Tomcat is the default embedded server of **spring-boot-starter-web** in Boot 2.x/3.x; Boot 4.x lines have their own web MVC starter and continue using Tomcat by default.

**Spring WebFlux:** Tomcat can be used via Spring WebFlux's non-blocking adapter, provided you exclude the default Reactor Netty server from the reactive application's dependencies and add the Tomcat starter.

**Key compatibility milestones:**

- Boot 2.7: Tomcat 9.0, Servlet 4.0, javax.servlet.
- Boot 3.2/3.5: Tomcat 10.1, Servlet 6.0, jakarta.servlet.
- Boot 4.0/4.1: Tomcat 11.0.x, Servlet 6.1.

**Assessment:** strong default choice for Servlet; straightforward to operate when applications depend on Filters, Servlet listeners, HTTP sessions, and Jakarta Servlet libraries. When running WebFlux on Tomcat, do not assume code relying on Servlet requests/sessions can be used as in MVC.

### 5.2. Eclipse Jetty

**Spring MVC:** Jetty is an alternative Servlet container to Tomcat, with an official Spring Boot starter in all lines under review.

**Spring WebFlux:** supported via the non-blocking Servlet adapter. Jetty also provides its own HTTP client, though selecting Jetty as the server **does not automatically select** WebClient's HTTP client implementation.

**Compatibility milestones:**

- Boot 2.7: Jetty 9.4 with Servlet 3.1 or Jetty 10.0 with Servlet 4.0.
- Boot 3.2/3.5: Jetty 12.0 with Servlet 6.0.
- Boot 4.0/4.1: Jetty 12.1.x with Servlet 6.1.

**Assessment:** suitable when the organization already uses Jetty or needs Jetty-specific features/operational traits. When upgrading Jetty 12, pay attention to corresponding modules, APIs, and Jakarta EE environments; **Jetty 12.0 and 12.1 are not automatically interchangeable between Boot 3.5 and 4.x**.

### 5.3. Undertow

**Spring MVC:** Boot 2.7 and matching Boot 3.x lines provided **spring-boot-starter-undertow**. Undertow acts as both an HTTP server and a Servlet container.

**Spring WebFlux:** in Boot 2.x/3.x, Spring Boot provided a way to use Undertow instead of Reactor Netty at the HTTP server layer via Spring WebFlux's compatibility integration.

**Compatibility milestones:**

- Boot 2.7: Undertow 2.0, Servlet 4.0.
- Boot 3.2/3.5: Undertow 2.3, Servlet 6.0.
- Boot 4.x: no officially supported embedded Undertow integration.

**Assessment:** Undertow can be a valid choice in Boot 3.5 projects. However, before adopting it in long-term architecture, factor in the Boot 4 upgrade plan. Spring Boot 4 dropped Undertow support due to the Servlet 6.1 requirement; trying to carry over the old starter from Boot 3.x is not a supported upgrade path.

### 5.4. Reactor Netty

**Spring MVC:** not a Servlet container; do not use it as an embedded server for Spring MVC.

**Spring WebFlux:** the default HTTP runtime of **spring-boot-starter-webflux**. It uses Netty event loops and APIs, needing no Servlet bridge to process HTTP.

**Versions:** Boot manages Reactor Netty and Netty versions via the Boot branch's own BOM; do not use the Servlet table above to pick them. Avoid overriding the Netty version independently without checking Reactor, Spring Framework, and Boot compatibility.

**Assessment:** common choice for reactive applications with asynchronous HTTP clients, R2DBC, or streaming. Non-blocking benefits are only realized if critical I/O steps do not block the event loop; replacing Tomcat with Reactor Netty does not cure slow JDBC queries or blocking logic.

## 6. Dependency Configuration Examples on Spring Boot 3.5

The following examples target **Maven + Spring Boot 3.5.x**. Each block describes dependencies inside the POM's dependencies section; **do not combine all server configurations into the same application**.

### 6.1. MVC + Default Tomcat

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

This is the simplest setup. The web starter brings in Tomcat; the application uses Spring MVC unless the application type is changed via special configuration.

### 6.2. MVC + Jetty

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
    <exclusions>
        <exclusion>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-tomcat</artifactId>
        </exclusion>
    </exclusions>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jetty</artifactId>
</dependency>
~~~

Tomcat is excluded and Jetty is added. Let Boot dependency management pick compatible Jetty 12.0; do not force versions manually without a tested reason.

### 6.3. MVC + Undertow (Only on Supported Boot Versions)

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
    <exclusions>
        <exclusion>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-tomcat</artifactId>
        </exclusion>
    </exclusions>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-undertow</artifactId>
</dependency>
~~~

Valid example in Boot 3.5. **Do not apply when upgrading to Boot 4.x.**

### 6.4. WebFlux + Default Reactor Netty

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

The WebFlux starter brings Reactor Netty onto the classpath by default. No Tomcat, Jetty, or Undertow is needed to run a basic reactive HTTP server.

### 6.5. WebFlux + Tomcat

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
    <exclusions>
        <exclusion>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-reactor-netty</artifactId>
        </exclusion>
    </exclusions>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-tomcat</artifactId>
</dependency>
~~~

The intent is to select Tomcat as **WebFlux's HTTP server**. If the application also uses WebClient with the Reactor Netty HTTP client, you must keep the appropriate client dependency or configure a different HTTP client connector; switching the server does not require switching the client.

**Note for Boot 4.x:** Spring Boot reorganized its starters and modules (such as a dedicated web MVC starter). Pull exact starter names and dependency examples from Boot 4.x documentation, and verify that Undertow has been removed. Do not copy a Boot 3.x POM verbatim and only bump the version property.

## 7. Runnable Example: Verifying Spring MVC with Tomcat

This is a Java 17 and Maven application using Boot 3.5.16 to demonstrate a Servlet server running successfully. Version 3.5.16 is a patch release in the Boot 3.5 branch referenced by documentation; in real projects pick a patch release approved and maintained by your organization.

### Structure

~~~text
runtime-check/
├── pom.xml
└── src/main/java/com/example/runtime/
    ├── RuntimeCheckApplication.java
    └── RuntimeController.java
~~~

### File pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>runtime-check</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

### File RuntimeCheckApplication.java

~~~java
package com.example.runtime;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RuntimeCheckApplication {
    public static void main(String[] args) {
        SpringApplication.run(RuntimeCheckApplication.class, args);
    }
}
~~~

### File RuntimeController.java

~~~java
package com.example.runtime;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RuntimeController {
    @GetMapping("/runtime")
    public Result runtime() {
        return new Result("servlet", "ok");
    }

    public record Result(String stack, String status) {}
}
~~~

Launch with JDK 17+ and Maven:

~~~bash
mvn spring-boot:run
~~~

In another terminal:

~~~bash
curl -s http://localhost:8080/runtime
~~~

Expected response body:

~~~json
{"stack":"servlet","status":"ok"}
~~~

This example only proves the Spring MVC endpoint runs and returns JSON. To verify **Tomcat specifically**, inspect startup logs and the dependency tree. If you swap dependencies to Jetty per section 6.2, keep the Java code unchanged and re-run to prove the controller still works on another Servlet container.

### Verifying the Actual Server in the Dependency Tree

~~~bash
mvn dependency:tree
~~~

In the output, look for the present groups: **org.apache.tomcat.embed** for Tomcat; **org.eclipse.jetty** for Jetty; **io.undertow** for Undertow; **io.projectreactor.netty** for Reactor Netty. A leftover dependency name does not always prove it is the **started server**: a library may only be used on the HTTP client side. Cross-check with startup logs and actual web server beans.

### Minimal WebFlux Example (Separate Illustrative Code)

The following controller belongs to a **separate WebFlux project with a Spring Boot main class and starter-webflux**; do not drop it directly in place of an MVC controller while the web MVC starter is still present:

~~~java
package com.example.runtime;

import reactor.core.publisher.Mono;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReactiveController {
    @GetMapping("/reactive")
    public Mono<String> reactive() {
        return Mono.just("ok");
    }
}
~~~

With the WebFlux application running on port 8080, calling **GET /reactive** returns the body **ok**. A Mono return value shows the API returns a Publisher, but does not prove the entire I/O path is non-blocking; inspect the dependencies called inside the pipeline.

## 8. Version-by-Version Compatibility Evaluation Process

Repeat this exact process whenever changing Boot, server, or Java:

1. **Pin the exact Boot version:** e.g., 3.5.16 or a 4.1.x patch release. Use documentation matching that exact release.
2. **Choose the web stack:** Servlet MVC or WebFlux. Do not infer the stack from the server name.
3. **Read System Requirements:** note minimum Java, Servlet baseline, and supported Tomcat/Jetty/Undertow lines.
4. **Read Embedded Web Servers:** identify official starters and how to exclude the default server to substitute a new one.
5. **Let the BOM manage dependencies:** verify resolved artifacts via Maven dependency tree or Gradle dependencies; avoid bringing in multiple servers unintentionally.
6. **Start the real app:** check logs for the actual server, port, servlet/reactive application context, exceptions, and health.
7. **HTTP smoke test:** send GET, POST with JSON, and error cases; verify status, content type, body, encoding, and routing.
8. **Run advanced compatibility tests if applicable:** Filters/Servlet API/sessions/WebSocket for MVC, or streaming/backpressure/timeouts for WebFlux.
9. **Evaluate operations:** TLS, proxies, keep-alive, graceful shutdown, metrics, threads or event loop, and performance under realistic load.
10. **Record evidence:** Boot version, Java, server, Servlet API, dependency tree, startup logs, and test results so others can reproduce.

You can use the commands below to confirm the dependency versions resolved by Maven:

~~~bash
mvn dependency:tree
mvn help:effective-pom
~~~

Run these in the Maven project directory with a valid pom.xml; initial execution may require access to the dependency repository.

## 9. Common Version-Evaluation Mistakes

| Claim or mistake | Why it is wrong | How to fix |
|---|---|---|
| "Tomcat supports reactive so every Tomcat app is reactive" | Tomcat can run both MVC and WebFlux; the framework and dependencies decide the stack | Check starters, ApplicationContext, and controller APIs |
| "Reactor Netty replaces Tomcat for Servlet MVC" | Netty does not implement a Servlet container | Use compatible Tomcat/Jetty/Undertow or migrate fully to WebFlux |
| "All Spring Boot 3.x releases use the same Jetty/Servlet" | The dependency matrix varies by minor and patch release, especially early Boot 3 | Read System Requirements for the exact version |
| "Undertow 2.3 works with Boot 3.5 so Boot 4 supports it too" | Boot 4 raised the Servlet baseline to 6.1 and dropped Undertow support | Choose Tomcat 11 or Jetty 12.1 when moving to Boot 4 |
| "Just bumping Tomcat 9 to 10/11 finishes the upgrade" | Switches from javax.servlet to jakarta.servlet and changes Servlet/Jakarta EE levels | Upgrade code, libraries, and Boot together |
| "Returning Mono/Flux means I/O is non-blocking" | Controllers may still call blocking libraries | Measure event-loop blocking and audit JDBC/HTTP clients |
| "Adding the webflux starter always turns an MVC app reactive" | When both MVC and WebFlux exist, Boot usually auto-selects MVC | Declare the stack explicitly; use consistent starters/application type |
| "Seeing Netty in the dependency tree means a Netty server is running" | Reactor Netty may be used solely as an HTTP client | Check startup logs and web server configuration |
| "Servlet 6.1 works on any Jetty 12" | Jetty 12.0 and 12.1 have different baselines in Boot's matrix | Choose the Jetty line compatible with your Boot version |
| "You can force the newest server version independently" | The newer server may mismatch auto-configuration modules or Jakarta APIs | Prefer the Boot BOM, override only when tested |

### What Else to Evaluate When Choosing WebFlux?

Servlet MVC can be very efficient with thread pools and synchronous I/O; do not choose WebFlux merely for the word "reactive". WebFlux typically pays off when the entire critical I/O path is non-blocking and high concurrency or streaming is required. Database queries, HTTP clients, transactions, SDK libraries, and timeout strategies must all fit that model.

On Tomcat/Jetty, WebFlux uses Servlet non-blocking I/O through an adapter; do not directly use Servlet Filters or servlet request/session APIs as in an MVC app to drive the WebFlux pipeline.

## 10. Scenario-Based Selection Guide

**Scenario A – CRUD app using JPA and Spring MVC on Boot 3.5.** The low-maintenance choice is default Tomcat 10.1. Switch to Jetty 12.0 or Undertow 2.3 when there is an operational reason and compatibility has been tested.

**Scenario B – WebFlux streaming API on Boot 3.5.** Start with default Reactor Netty, then measure latency, throughput, event loop, and dependency performance. Only switch to Tomcat/Jetty if infrastructure standards demand it or measurements support it.

**Scenario C – Upgrading an Undertow app from Boot 3.5 to Boot 4.** This is a server architecture change: remove the Undertow starter, choose Tomcat 11 or Jetty 12.1, update to Servlet 6.1/Jakarta EE 11, and re-run real tests.

**Scenario D – Legacy Boot 2.7 app using javax Servlet Filters.** Do not merely swap the server to Tomcat 10.1: upgrade Boot and related libraries, migrate code to the Jakarta namespace, and test Filters, listeners, and Servlet APIs. Boot 2.7 and Boot 3/4 do not share the same baseline.

## 11. Support Sign-Off Checklist

- [ ] Know the **exact** Spring Boot, Java, and embedded server versions.
- [ ] Identify Spring MVC/Servlet vs. Spring WebFlux/reactive.
- [ ] Match the Servlet API matrix against the server and javax/jakarta namespace.
- [ ] Pick a server officially supported by Boot **for that exact version**.
- [ ] Use official starters; exclude the default server starter when swapping.
- [ ] Do not confuse HTTP client libraries with the running HTTP server.
- [ ] Use dependency management and inspect resolved versions.
- [ ] Start up, inspect logs, smoke test endpoints, and evaluate operations.
- [ ] Record the compatibility matrix and evidence for future upgrades.

## 12. Official References

1. Spring Boot 2.7.18 Reference – System Requirements: https://docs.spring.io/spring-boot/docs/2.7.x/reference/htmlsingle/
2. Spring Boot 3.2.12 Reference – System Requirements: https://docs.spring.io/spring-boot/docs/3.2.12/reference/htmlsingle/
3. Spring Boot 3.5 – System Requirements: https://docs.spring.io/spring-boot/3.5/system-requirements.html
4. Spring Boot 3.5 – Embedded Web Servers: https://docs.spring.io/spring-boot/3.5/how-to/webserver.html
5. Spring Boot 4.0 – System Requirements: https://docs.spring.io/spring-boot/4.0/system-requirements.html
6. Spring Boot 4.x – Embedded Web Servers: https://docs.spring.io/spring-boot/4.0/how-to/webserver.html
7. Spring Boot 4.0 Migration Guide – Undertow removal: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide
8. Spring Framework – WebFlux overview and supported servers: https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html

**Conclusion:** Servlet or reactive support is a relationship among **web stack, server, Boot version, and required API level**. Tomcat/Jetty support both MVC and WebFlux with the right integration; Reactor Netty is built for WebFlux; Undertow fits supported Boot 2.x/3.x lines but was removed in Boot 4.x. Always verify against the exact version, dependency tree, and actual running application.