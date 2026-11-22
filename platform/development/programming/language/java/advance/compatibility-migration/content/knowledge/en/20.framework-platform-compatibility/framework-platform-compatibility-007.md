# Web Servers, Servlet Containers, and WAR Deployment Compatibility

In **Java Advance Compatibility Migration**, upgrading the JDK does not affect application code alone. A Java web service may build successfully on Java 17 and run fine when packaged as an executable JAR, yet fail when deploying a **WAR** file onto Tomcat, Jetty, or an external application server. The cause usually lies at the boundary among **JDK runtime, Servlet API, web container, dependency graph, class loader, and deployment configuration**.

A particularly important change is Java EE APIs moving from `javax.servlet.*` to `jakarta.servlet.*` in newer Jakarta EE generations. A WAR carrying servlets/filters compiled against javax is not automatically compatible with a container using jakarta, even when both run on a modern JDK. Likewise, if the container runs a JDK lower than what the application requires, class-file version errors can arise before the framework even initializes.

This lesson explains Java web deployment models, how to pick the right JDK–Servlet–container–framework combination, Spring Boot WAR configuration with Gradle/Maven, resolving class loader/JNDI/TLS/session conflicts, and building a verification workflow with rollback capability.

## 1. Distinguishing Web Servers, Servlet Containers, and Application Servers

| Component | Primary Function | Examples |
|---|---|---|
| HTTP web server/reverse proxy | Receives HTTP/TLS, reverse proxy, serves static files, routing | Nginx, Apache HTTP Server |
| Servlet container | Manages Servlet API, request/response, filters, listeners, webapp lifecycle | Tomcat, Jetty, Undertow in Servlet mode |
| Embedded Servlet container | Container loaded by the application as a dependency, sharing the app's JVM | Embedded Tomcat or Jetty in Spring Boot |
| Jakarta EE application server | Provides Servlet plus, depending on profile, other enterprise services | WildFly, Payara, Open Liberty |
| JVM/JDK | Runs container and application bytecode, provides platform APIs | JDK 17, JDK 21 |

Common architecture diagram:

~~~text
Client / browser
       |
       v
Reverse proxy / ingress (if present)
       |
       v
Servlet container JVM
       |
       +-- HTTP connector
       +-- Servlet context
       +-- Filter chain
       +-- DispatcherServlet / custom servlet
       |
       v
Application services / repositories / messaging
~~~

A reverse proxy does not automatically become a Servlet container. It can route to a Java process, but it does not implement `ServletContext` or load Java Servlet classes.

The container is responsible for implementing the Servlet contract parts such as request/response objects, filters, listeners, sessions, dispatch, servlet mappings, and webapp lifecycle. Other capabilities such as TLS connectors, JSP, WebSocket, clustered sessions, JNDI, or metrics also depend on the implementation and configuration.

**Do not assume every Servlet container is a full Jakarta EE application server.** For example, Tomcat does not automatically supply all enterprise technologies like a full Jakarta EE platform does. Applications must still manage appropriate JPA, transaction integration, or messaging providers.

## 2. Embedded Executable JAR vs. External WAR

### 2.1. Executable JAR

In the Spring Boot embedded server model, the application is packaged into a JAR containing business classes, the framework, and container libraries:

~~~bash
java -jar orders-service.jar
~~~

~~~text
orders-service.jar
    |
    +-- Spring application
    +-- Dependencies
    +-- Embedded container libraries
    |
    v
Dedicated JVM
    |
    v
HTTP connector
~~~

The typical advantage is that the application and container are versioned and deployed as a single unit; the service does not depend on a pre-installed Tomcat server. This fits many container/microservice deployments.

### 2.2. External WAR

With a WAR, a pre-existing Servlet container loads the web application:

~~~text
Tomcat / Jetty / application server
    |
    +-- JVM + container API implementation
    +-- HTTP connectors
    +-- Container-provided resources/libraries
    |
    v
orders.war
    |
    +-- WEB-INF/classes
    +-- WEB-INF/lib
    +-- Resources / descriptors
~~~

The external container manages the process, connector ports, context root, webapp classloader, and deployment lifecycle. The application must not assume it owns the entire JVM.

### 2.3. Executable WAR is a special case

Spring Boot can create an **executable WAR** with a launcher, runnable via `java -jar orders.war` or deployable onto an external Servlet container when configured properly. Container libraries marked provided may live in a special location such as `WEB-INF/lib-provided` for the launcher to use when running directly, without becoming external container libraries in the usual way.

This does not apply to every WAR. A plain Servlet WAR may lack a `Main-Class`/launcher for running via `java -jar`.

**Choosing between JAR and WAR deployment is an architectural decision**, not just changing the artifact's file extension. If choosing WAR, test against the exact container product and version planned for use.

## 3. Three Critical Compatibility Conditions

~~~text
Application / framework
  - Java baseline
  - Servlet API types
  - Dependencies and bytecode
              |
              v
Servlet container
  - javax or jakarta
  - Servlet specification level
  - Implementation / classloading
              |
              v
JDK of the container process
  - Runtime class-file support
  - Java SE APIs
  - TLS/security/provider policy
~~~

A valid deployment must satisfy **simultaneously**:

1. The JDK actually running the process can load the bytecode of the framework, application, and dependencies.
2. The Servlet specification implemented by the container is compatible with the application/framework.
3. Related libraries match the namespace and API contract.
4. Deployment settings such as context path, DataSource, proxy/TLS, and resource loading are correct.

For example, Boot 3 has a Java 17 baseline. A container capable of running on Java 11 will not let a Boot 3 WAR run when that container instance itself is running Java 11. The runtime must meet the minimum requirement of **every component**.

## 4. The javax.servlet and jakarta.servlet Boundary

This is a major API difference in web application migration.

Before, with Java EE 8 / Servlet 4:

~~~java
import javax.servlet.Filter;
import javax.servlet.http.HttpServletRequest;
~~~

After, with Jakarta Servlet 5 onward:

~~~java
import jakarta.servlet.Filter;
import jakarta.servlet.http.HttpServletRequest;
~~~

Although the short name `Filter` looks the same, they are two distinct types in Java. You cannot cast `javax.servlet.Filter` to `jakarta.servlet.Filter`. A Servlet container providing Jakarta Servlet will not automatically accept a Filter implementation compiled for javax.

| Generation | Servlet Specification | Namespace |
|---|---|---|
| Java EE 8 | Servlet 4.0 | `javax.servlet.*` |
| Jakarta EE 9 | Servlet 5.0 | `jakarta.servlet.*` |
| Jakarta EE 10 | Servlet 6.0 | `jakarta.servlet.*` |
| Jakarta EE 11 | Servlet 6.1 | `jakarta.servlet.*` |

### 4.1. Do not change every javax.* to jakarta.*

The following Java SE APIs continue using the `javax` namespace:

- `javax.net.ssl.*`.
- `javax.crypto.*`.
- `javax.sql.*`.
- `javax.naming.*`.
- `javax.management.*`.
- `javax.xml.parsers.*`.
- `javax.annotation.processing.*`.

Only migrate APIs that genuinely belong to Jakarta Enterprise and are used by the target framework. Running find-and-replace on all `javax.` occurrences can break valid Java SE source code.

### 4.2. Adding javax.servlet-api to a Jakarta WAR is not a fix

A Boot 3 application using Spring Framework 6 and Jakarta Servlet may include a legacy third-party filter compiled for javax. Adding the `javax.servlet-api` JAR might make some missing-class errors disappear, yet **it does not make that filter implement the Jakarta Servlet contract**. The solution is to upgrade/rebuild/replace the filter with a compatible version or execute a verified conversion plan.

## 5. Tomcat Major Versions and Servlet Specifications

Some reference milestones:

| Apache Tomcat | Servlet API | Namespace | Container Minimum Java |
|---|---|---|---|
| 9.0 | 4.0 | `javax.servlet` | Java 8 |
| 10.0 | 5.0 | `jakarta.servlet` | Java 8 |
| 10.1 | 6.0 | `jakarta.servlet` | Java 11 |
| 11.0 | 6.1 | `jakarta.servlet` | Java 17 |

These are the main characteristics of each Tomcat line; you must still verify **patch releases, security support, framework support matrices, and the actual deployment JDK runtime**.

For example:

~~~text
Spring Boot 2 / Spring Framework 5
    + javax.servlet integrations
    -> Tomcat 9 is a typical combination.

Spring Boot 3 / Spring Framework 6
    + jakarta.servlet integrations
    -> Tomcat 10.1 is a typical combination.

Spring Boot 3 WAR -> Tomcat 9:
    Incompatible namespace.
~~~

A newer Tomcat version does not automatically guarantee that every Spring Boot 3 minor branch has been verified compatible upstream. When selecting versions, inspect Servlet API levels, Java baselines, supported container versions, and the application framework's release notes.

### 5.1. Tomcat 10 is not "Tomcat 9 plus a few features"

The javax → jakarta change is a binary-level API rename. Legacy source code, annotations, integration libraries, web descriptors, and servlet filters may require migration. Do not treat it as a simple patch upgrade.

## 6. Jetty, Undertow, and Jakarta EE Application Servers

Jetty has releases/profiles supporting different Servlet generations; some newer lines use environment modules to choose the Jakarta/Servlet level. Do not assume "Jetty N always equals Tomcat N". Check the **release, environment profile, Java baseline, and Servlet specification**.

Undertow can serve as an embedded engine or part of an application server. When deploying a WAR onto WildFly or another runtime, the **application server's support matrix** matters more than Undertow's standalone name and version.

Application servers such as WildFly, Payara, and Open Liberty can additionally supply JNDI, JTA, CDI, Jakarta Persistence, and messaging services depending on product/profile. Those services affect dependency scopes and resource ownership.

Before deploying a WAR, answer:

- Is the server implementing the javax or jakarta Servlet API?
- Which JDKs has the server been verified with?
- Does the runtime support JSP/JSTL, WebSocket, or HTTP/2 as required?
- Does the container provide JPA/transaction/validation libraries or does the application bundle them itself?
- How do the server's classloading delegation and module isolation work?
- Are Spring/Servlet libraries allowed to be packaged inside the WAR?

## 7. Actual Java Runtime of the Container

A WAR with class-file major 61 needs a JVM supporting Java 17; major 65 needs a JVM supporting Java 21. Configuring only the compiler release in the source repository is not enough.

For example:

~~~text
Build JDK: Java 21
Compiler --release: 17
WAR class files: major 61
External container JVM: Java 11
=> Runtime does not satisfy the WAR's bytecode target.
~~~

### 7.1. Checking the process runtime

~~~bash
java -version
javac -version
~~~

These commands only reflect the current shell. The container/server may be launched by systemd, a Windows Service, or scripts using a different JAVA_HOME. With Tomcat, tools like `bin/version.sh` or startup logs can show the instance's Java Home, runtime version, and server version.

### 7.2. Class-file version

~~~bash
javap -verbose -classpath build/classes/java/main \
  com.example.orders.OrdersApplication
~~~

Look for `major version`. However, a WAR can contain multiple dependency JARs with differing bytecode targets. Inspect the artifacts actually packaged and loaded, rather than extrapolating from one representative class.

### 7.3. Compiler target is not a runtime upgrade

Gradle `options.release = 17` or Maven `maven.compiler.release=17` restricts syntax, bytecode, and Java SE APIs for the compiled module's source. It does not automatically upgrade the external Tomcat's JDK and does not force external dependencies onto the same target.

## 8. WAR Packaging: Structure and Classpath

A WAR typically has:

~~~text
orders.war
├── META-INF/
├── assets/
└── WEB-INF/
    ├── classes/
    │   └── com/example/orders/...
    ├── lib/
    │   ├── spring-*.jar
    │   └── application-libraries.jar
    └── web.xml  (optional)
~~~

`WEB-INF/classes` holds compiled application classes, while `WEB-INF/lib` holds application libraries. The external container provides the Servlet implementation and services specified by deployment policy.

Errors commonly arise when:

- Packaging the Servlet API or embedded container in conflict with the server.
- Marking an essential library as provided when the server does not actually supply it.
- Embedded/external dependencies appearing in two versions simultaneously.
- Code generation/resource loading placing outputs in the wrong location.
- The WAR lacking initializers or configs required to bootstrap the application.
- Dependencies present on test/IDE classpath missing from the WAR.

Use `jar tf` to inspect contents:

~~~bash
jar tf target/orders.war
~~~

Or:

~~~bash
jar tf build/libs/orders.war
~~~

Do not inspect only Maven/Gradle dependency declarations; inspect both the released artifact and server-level libraries.

## 9. Spring Boot WAR: Entrypoint and Initializer

A Servlet-based Spring Boot application deployed as a WAR on an external container can extend `SpringBootServletInitializer`:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class OrdersApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder application) {
        return application.sources(OrdersApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

`configure` allows the external Servlet container to bootstrap the Spring application. `main` continues serving executable deployments when packaged appropriately.

This example is for **Servlet-based Spring Boot**. Do not assume a reactive-only WebFlux application can be switched to WAR deployment like a Spring MVC application. Check deployment-specific rules of your target framework/Boot release.

### 9.1. Component scan and duplicate bootstrapping

If `OrdersApplication` sits in the wrong package or the project has multiple `WebApplicationInitializer`/`web.xml` entries and Spring Boot initializers active at once, the application context may miss beans or bootstrap twice. Identify a single bootstrap point and clear package scanning boundaries.

## 10. Gradle Creating a Spring Boot WAR

Example of a Spring Boot Servlet application using Java 17:

~~~groovy
plugins {
    id 'java'
    id 'war'
    id 'org.springframework.boot' version 'REPLACE_WITH_VERIFIED_BOOT_VERSION'
    id 'io.spring.dependency-management' version 'REPLACE_WITH_COMPATIBLE_PLUGIN_VERSION'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    // External container will provide the Servlet engine.
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Both versions are **placeholders**. Choose real Boot 3, Gradle wrapper, and plugin versions aligned with your support policy; do not copy placeholders into a production build.

### 10.1. providedRuntime

`providedRuntime` is used by the Spring Boot Gradle WAR workflow to indicate container dependencies supplied by the external runtime. This configuration behaves differently from placing the Tomcat starter in normal `implementation`.

For a Boot executable WAR, the plugin can place provided runtime libraries in `WEB-INF/lib-provided` to avoid conflicts when the WAR deploys to an external container.

### 10.2. Building the WAR

~~~bash
./gradlew clean bootWar
~~~

Tasks and output paths must be verified for your plugin version/project. `bootWar` is a common task provided by the Spring Boot Gradle plugin when configured for WAR packaging, though not every Gradle project has this task by default.

### 10.3. If using Jetty or Undertow

Do not replace the Tomcat starter with an arbitrary artifact yourself. Use a starter/container combination supported by the target Boot release and review the corresponding provided runtime configuration.

## 11. Maven Creating a WAR

Concise yet structurally complete POM example:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>REPLACE_WITH_VERIFIED_BOOT_VERSION</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>orders-service</artifactId>
    <version>1.0.0</version>
    <packaging>war</packaging>

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
            <artifactId>spring-boot-starter-tomcat</artifactId>
            <scope>provided</scope>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

This example is for the Boot parent model, not the full dependency set of every application. If the project uses a corporate parent or imports BOMs differently, configure compiler/plugin management accordingly.

### 11.1. The provided scope

`provided` means the library is not treated as an ordinary application runtime library packaged for an external container. With embedded Tomcat in the Spring Boot WAR workflow, Maven packaging has specific handling for executable WARs.

Do not arbitrarily mark drivers or ORM libraries as provided. If the server does not actually supply the exact compatible version, runtime may throw `ClassNotFoundException` or `NoClassDefFoundError`.

### 11.2. Build

~~~bash
mvn clean package
~~~

Inspect the artifact under `target`, the WAR manifest, and actual libraries after plugin processing.

## 12. web.xml, Servlet Registration, and Jakarta Descriptors

Servlet 3.0 onward supports registration mechanisms that do not strictly require `WEB-INF/web.xml`. Spring Boot WARs typically rely on initializers to bootstrap the application context.

If a legacy application has `web.xml`, inspect:

- Descriptor schema and namespace.
- Servlet/filter/listener class names.
- Mappings and filter ordering.
- Session configuration and security constraints.
- Context parameters.
- Error pages and welcome files.
- Container-specific descriptors.

Descriptor example for Jakarta Servlet 6.0:

~~~xml
<web-app xmlns="https://jakarta.ee/xml/ns/jakartaee"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="https://jakarta.ee/xml/ns/jakartaee
                             https://jakarta.ee/xml/ns/jakartaee/web-app_6_0.xsd"
         version="6.0">

    <display-name>Orders Application</display-name>

</web-app>
~~~

Do not automatically add this file to every Boot WAR. It only illustrates the descriptor structure if the application genuinely needs it.

### 12.1. Duplicate registration

A WAR might simultaneously use annotations, `ServletContainerInitializer`, `WebApplicationInitializer`, `web.xml`, and Spring-managed registration beans. During migration, overlapping configs can cause Servlets/Filters to run twice or create multiple contexts. Identify the owner of each registration.

## 13. Class Loaders of an External Container

An external container may use multiple class loader layers:

~~~text
JDK bootstrap / platform
       |
       v
Container common / shared classes
       |
       v
Web application class loader
       |
       +-- WEB-INF/classes
       +-- WEB-INF/lib/*.jar
~~~

The diagram is conceptual. Actual delegation order depends on the container, parent-first/child-first settings, and exceptions for platform/Servlet APIs.

Common issues:

- A class appears in both container libraries and WAR libraries at two versions.
- Types with the same name are defined by two different class loaders.
- The Servlet API is included in the WAR and conflicts with the server-provided implementation.
- Thread context class loader (TCCL) cannot see providers/resources.
- The application server uses separate module layers to isolate libraries.
- Background threads retain the old WAR's class loader after undeploy.

**Java type identity is not only the fully qualified name, but also involves the defining class loader.** Two classes with the same name loaded by two different loaders can be incompatible.

### 13.1. Example of a suspicious error

~~~text
ClassCastException:
com.example.Plugin cannot be cast to com.example.Plugin
~~~

This case can occur when `com.example.Plugin` exists under two defining class loaders. Inspect JAR origins, classloader hierarchy, and container modules instead of only editing Java inheritance.

## 14. Duplicate Servlet APIs and Version Conflicts

Suppose external Tomcat 10.1 provides Jakarta Servlet 6.0 yet the WAR packages an older API JAR or legacy `javax.servlet-api`.

Having both libraries present can cause:

- Unintended class resolution.
- `LinkageError`, `NoSuchMethodError`, or `AbstractMethodError`.
- Filters/Servlets not implementing the right interface.
- Mismatched reflection lookups.
- Delayed failures when requests hit a specific code path.

Some containers implement class-loading protection for API packages, but **do not rely on implicit protection** as a version management strategy.

### 14.1. Do not copy JARs into server-wide lib arbitrarily

Putting JARs into Tomcat/application server shared classpaths can impact every deployed WAR, including unrelated applications. Container-owned libraries need clear version policies, owners, and compatibility tests.

### 14.2. Inspecting the resolved graph

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jakarta.servlet \
  --configuration runtimeClasspath
~~~

Maven:

~~~bash
mvn dependency:tree
~~~

Cross-check the dependency graph against `WEB-INF/lib` and libraries outside the WAR. Looking only at source imports is not enough.

## 15. JNDI DataSource and Server-Managed Resource Configuration

In an embedded Boot JAR, Spring usually creates the DataSource from properties. When using an external container, teams can choose a container-provided DataSource via JNDI.

Boot property example:

~~~properties
spring.datasource.jndi-name=java:comp/env/jdbc/OrdersDB
~~~

The container must declare the corresponding resource, provide the driver/connection pool, and configure required permissions.

| Model | Responsibility | Risks |
|---|---|---|
| Spring-managed DataSource | Application carries driver and manages pool | Must version driver/pool inside the WAR |
| Container-managed JNDI DataSource | Container/platform manages the resource | Requires config name, driver placement, credentials, pool policy |
| Full application server resource | Server may add transaction manager and other services | Framework integration and server module conflicts |

`javax.naming.*` remains a Java SE API and does not switch to `jakarta.naming.*`. Do not alter the wrong imports when changing Servlet APIs.

### 15.1. Common errors

~~~text
javax.naming.NameNotFoundException:
Name [jdbc/OrdersDB] is not bound in this Context
~~~

Inspect resource declarations and naming contexts **inside the container**, rather than only changing Maven dependencies.

### 15.2. Transaction management

A Tomcat Servlet container does not by default provide all JTA capabilities of a full application server. If the application needs distributed transactions, inspect the transaction manager and corresponding Jakarta EE resources separately.

## 16. Context Root, Connector Ports, and URL Paths

In embedded Boot mode, you can use:

~~~properties
server.port=8080
server.servlet.context-path=/orders
~~~

In an external WAR, the connector port and context root are usually managed by **container deployment configuration**. Context root may come from the WAR filename or a context descriptor.

For example:

~~~text
Embedded JAR:
  http://host:8080/orders/api/items

External WAR orders.war:
  http://host:8080/orders/api/items
~~~

The two URLs may look identical while being created by different configuration layers. Do not edit `server.port` expecting it to change the port of an external Tomcat.

Factors to review:

- WAR context root.
- Servlet mapping.
- Spring MVC paths.
- Spring Security matchers.
- Reverse proxy path prefixes/rewrites.
- Actuator endpoint base path.
- Cookie paths and redirect targets.

### 16.1. Forwarded headers

If TLS terminates at an ingress or reverse proxy, the application may need to know the original URL via `Forwarded`/`X-Forwarded-*` headers or container proxy settings. Trust forwarded headers only from controlled proxies; do not allow arbitrary clients to declare host/protocol headers freely.

## 17. TLS and HTTP Connector Compatibility

When changing deployment models, where TLS terminates may change:

~~~text
Client
  |
  | TLS #1
  v
Ingress / reverse proxy
  |
  | HTTP or TLS #2
  v
Servlet container
  |
  v
Application
~~~

Separate:

- **Inbound TLS** at the proxy or container.
- **Proxy-to-backend TLS** if applicable.
- **Outbound TLS** from the Java application to APIs/databases/brokers.

Each connection has its own certificates, truststore/keystore, and security policy.

When upgrading containers/JDKs, verify TLS versions, cipher suites, certificate chains, hostname verification, mTLS, ALPN/HTTP2, connection timeouts, header limits, keep-alive, multipart/body limits, and logging.

If the application runs as a WAR on a container yet hits HTTP 400/431 before a Spring controller receives the request, the cause may be a new HTTP parser/connector policy rather than controller code.

## 18. Custom Servlet Filters on Jakarta

Example of a Filter using Jakarta Servlet:

~~~java
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import java.io.IOException;

public final class RequestAuditFilter implements Filter {

    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {

        // Perform audit/correlation per the application contract.
        chain.doFilter(request, response);
    }
}
~~~

If the application still imports `javax.servlet.Filter`, it cannot function as a compliant Jakarta Filter.

Registration forms can include `web.xml`, servlet annotations, Spring `FilterRegistrationBean`, or container-specific mechanisms. When migrating an embedded JAR to a WAR, verify:

- The Filter is registered exactly once.
- Ordering among CORS, auth, logging, tracing, and compression is appropriate.
- Request/response wrapper types belong to the right namespace.
- Whether the Filter runs on error endpoints or async dispatches.
- Proper unregistration/cleanup on undeploy.

## 19. Spring Security When Deploying a WAR

Spring Security typically operates via the servlet filter chain. When moving from Boot 2/Security 5 to Boot 3/Security 6 and an external container, update namespaces, configuration, and security policy tests together.

Security 6 example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated()
        );
        http.httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

This is only a structural example and does not describe authentication/CSRF/CORS for a real system.

Deployment risks:

- Security Filter is unregistered or registered twice.
- Request matchers no longer match context path/proxy mappings.
- Cookie/session behavior changes.
- Redirect URLs have wrong scheme/host.
- OAuth/SSO adapters support only `javax.servlet`.
- Tests verify only the happy path without verifying forbidden endpoints.

**Do not remove the filter chain or permit-all to "fix" WAR startup failures.** Fix dependencies/registration and preserve authorization principles.

## 20. Sessions, Cookies, and Session Replication

A WAR can be restarted/redeployed independently or run across multiple nodes in an external container cluster. Factors to verify:

- `HttpSession` lifecycle and expiration.
- Session cookie name/domain/path.
- Secure, HttpOnly, SameSite.
- Sticky sessions / load balancer routing.
- External session stores.
- Session replication format.
- Session ID rotation after login.
- In-memory sessions during rolling deployments.
- Changes to serialized object classes between versions.

### 20.1. Do not assume old session data remains readable

When upgrading frameworks, Servlet namespaces, or containers, serialized session attributes may become incompatible. For example, an old class containing `javax.servlet.*` references or structural changes after Boot 3 upgrades can break session deserialization.

Decide upfront: drain sessions, accept re-logins, use an external session store supporting both versions, or provide data migration mechanisms with clear tests.

### 20.2. Login/cookie regressions

A deployment might return HTTP 200 for APIs yet break login redirects or cookie Paths due to context root/proxy mismatches. Test browser flows through a production-like ingress.

## 21. JSP, JSTL, and Views

Legacy WAR applications may use JSP/JSTL:

- The JSP engine must be compatible with the container and Servlet/Jakarta release.
- JSTL libraries/tag handlers may need moving to Jakarta equivalents.
- Custom JSP tags using `javax.servlet.jsp.*` may no longer match a Jakarta runtime.
- View resolvers and resource paths may differ from embedded deployments.
- JSP has differing packaging limitations between executable JARs and WARs in some framework releases.

Do not blame every HTTP 404/JSP 500 on javax/jakarta; check JSP compiler logs, view resolvers, and WAR resource layout.

If a project moves from an external WAR to an executable JAR, verify whether the framework supports JSP in that packaging mode instead of treating the two formats as fully interchangeable.

## 22. WebSocket, Async Servlet, and Streaming

Beyond synchronous REST, verify:

- Jakarta WebSocket API level.
- HTTP Upgrade handshake through proxies.
- Idle timeouts and heartbeats.
- Servlet `AsyncContext` lifecycle.
- Server-Sent Events and streaming.
- HTTP2/ALPN.
- Request buffering and backpressure.
- Load balancer sticky routing if the service holds connection state.

A WebSocket integration compiled for javax may be incompatible with a Jakarta container. Do not use ordinary HTTP GET tests to conclude realtime endpoints are safe.

## 23. Thread Pools and Classloader Leaks on Redeploy

External containers often run multiple web applications inside one JVM. If a WAR creates background threads, scheduled executors, or caches retaining references to the old classloader, a redeploy can create a memory leak.

Symptoms:

- Threads from previous versions keep running.
- JDBC drivers or connection pools are not cleaned up.
- `ThreadLocal` retains objects from the old webapp.
- JMX MBean registrations are not unregistered.
- Timers/schedulers keep holding the classloader.
- Static references from container-level libraries point to webapp classes.

Lifecycle bean example:

~~~java
import jakarta.annotation.PreDestroy;
import java.util.concurrent.ExecutorService;

public final class BackgroundJobOwner {

    private final ExecutorService executor;

    public BackgroundJobOwner(ExecutorService executor) {
        this.executor = executor;
    }

    @PreDestroy
    public void stop() {
        executor.shutdown();
    }
}
~~~

This snippet assumes the bean owns the executor. Do not shut down a shared/container-managed thread pool if it is outside the bean's ownership.

Test **deploy → undeploy → redeploy** multiple times in test environments if the system uses hot deployment, rather than verifying only initial startup.

## 24. Third-Party Dependencies Easily Overlooked

A WAR can contain:

- Servlet filters and SSO adapters.
- Spring MVC extensions.
- OpenAPI/Swagger UI integrations.
- Multipart/upload parsers.
- JSP/JSTL tags.
- WebSocket libraries.
- JPA/validation providers.
- Logging/tracing/metrics Servlet instrumentations.
- Application server vendor extensions.
- Java agents loaded via startup options.
- Native/JNI libraries.
- Internal shared libraries compiled against javax.

A library stating "supports Java 17" does not necessarily support Jakarta Servlet. Check **Java baseline + Servlet namespace/version + Spring/framework major version** separately.

When legacy libraries lack a Jakarta release, consider upgrading/replacing the library first. Some migration transformers can rewrite references, yet should not be expected to fix semantics, reflection strings, serialization, proprietary APIs, and special configurations. If using a transformer, control provenance, licensing, test evidence, and a retirement plan.

## 25. Classloader and Dependency Triage

When encountering:

~~~text
java.lang.NoClassDefFoundError: javax/servlet/Filter
  at com.vendor.legacy.SecurityFilter...
~~~

in a Boot 3 WAR on Tomcat 10.1, investigation steps:

1. Identify the JAR containing `com.vendor.legacy.SecurityFilter`.
2. Confirm it was compiled for `javax.servlet.Filter`.
3. Look up a vendor release supporting Jakarta Servlet/Spring Boot 3.
4. Replace or update the library.
5. Remove unneeded legacy API JARs.
6. Rebuild the WAR and inspect `WEB-INF/lib`.
7. Deploy onto the right container/JDK.
8. Test auth/authorization behavior, not only startup.

If the error is `NoSuchMethodError` on servlet/classloaders, inspect which API version is actually loaded. If the error is `UnsupportedClassVersionError`, inspect the JVM running the container instead of adding module exports.

## 26. WAR Build and Verification Pipeline

A recommended workflow:

~~~text
Source + pinned dependency graph
             |
             v
Build tool + compiler JDK
             |
             v
Compile, tests, static analysis
             |
             v
Build WAR
             |
             v
Inspect WAR + checksum
             |
             v
Deploy WAR to staging container/JDK
             |
             v
Startup, security, data, session tests
             |
             v
Production rollout + monitoring
~~~

When the external container is managed by a platform team, also version:

- The WAR artifact.
- Container release/patch.
- JDK vendor/runtime version.
- Common libraries.
- TLS proxy configuration.
- JNDI resources, credentials, and pool settings.
- Context root/connector policies.
- Deployment options and environment secrets.

If you only store the WAR checksum without knowing Tomcat/JDK/common-lib versions, reproducing production errors can become very difficult.

### 26.1. Stale exploded WAR

Some containers unpack WARs into an application directory. Under specific deployment setups, stale exploded directories or cached resources can leave the application running code from an earlier version. Cross-check artifacts, deployment logs, and directory/timestamps according to container guidelines.

## 27. Embedded Tests Do Not Replace External WAR Integration Tests

A `@SpringBootTest` with an embedded server or MockMvc is valuable for business/web contracts, yet **does not prove** the WAR works inside the classloaders and connectors of external Tomcat/Jetty.

| Test | Primary Evidence |
|---|---|
| Unit tests | Business logic |
| `@WebMvcTest` / MockMvc | MVC route/filter behavior in test context |
| `@SpringBootTest` with random port | Integration with embedded server |
| External WAR staging deploy | Servlet container lifecycle, classloading, resources |
| End-to-end through ingress/proxy | TLS, redirects, cookies, routing |
| Redeploy/restart tests | Cleanup, session/state recovery |
| Performance/failover tests | Resource limits and operations |

Use **the exact WAR artifact intended for release** to test external deployment, avoiding building a different WAR after verification.

## 28. Post-Deployment Verification Suite

A production-like test suite should cover:

1. **Startup:** server and application context initialize without errors.
2. **Deployment:** exact WAR version/checksum and context root.
3. **Health:** readiness/liveness reflects dependency state.
4. **Routing:** paths, trailing slashes, query parameters, and HTTP methods.
5. **Serialization:** JSON/XML/dates/numbers, error response contracts.
6. **Validation:** invalid inputs are handled properly.
7. **Security:** public/private paths, login, permissions, CSRF/CORS, token validation.
8. **Sessions:** cookie attributes, login, logout, restart, failover.
9. **Persistence:** JNDI/DB/pool, transactions, and query correctness.
10. **Static/JSP:** resources, templates, and tag libraries if used.
11. **WebSocket/async:** upgrade, disconnect/reconnect, and timeouts.
12. **Proxy/TLS:** forwarded host/scheme, certificates/HTTP2 if used.
13. **Resource limits:** large headers/bodies, multipart uploads, and timeouts.
14. **Metrics:** access logs, tracing, alerts, and actuator/management endpoints.
15. **Redeploy:** no leftover background threads/classloader leaks.
16. **Performance:** startup, throughput, p95/p99, heap, GC.
17. **Rollback:** old artifact works with planned state/schema.

Do not use an HTTP 200 health endpoint as the sole criterion to conclude the application is compatible.

## 29. Rolling Deployment, Data, and Rollback

During a rolling update, both can coexist simultaneously:

~~~text
Load balancer
  |         |
  v         v
Node A    Node B
WAR N     WAR N+1
~~~

Items to check:

- Are API clients compatible with both server versions?
- Can the database schema serve both old and new versions?
- Is session replication/deserialization compatible?
- Do message payloads/cache keys require versioning?
- Do old/new nodes have differing JDKs/containers?
- Can metrics/logs distinguish failing nodes/versions?
- On rollback, can data written by the new version still be read?

**Rollback is not simply copying the old WAR back.** If migration changed database schemas, session formats, or shared state, the old runtime may be unable to recover the new data.

### 29.1. Session draining

For applications relying on in-memory sessions, a rollout may require sticky sessions, load balancer draining, or accepting that users must log in again. This is an operational decision that must be communicated, rather than assuming the container handles it automatically.

## 30. Security Hardening When Upgrading Web Containers

A safe migration should maintain or raise the security posture:

- Container/JDK security patches.
- HTTPS/TLS certificate chains and cipher policies.
- HTTP request parser constraints.
- Header/body size limits.
- Timeouts and DoS protections.
- Secure, HttpOnly, and SameSite cookie policies.
- Session fixation protection.
- Spring Security authorization.
- Management/JMX/admin console access controls.
- Directory listing and default applications.
- Java serialization and deserialization trust boundaries.
- Shared libraries and native dependencies.
- Audit logs and secrets handling.

An older container lacking security fixes is a risk even if the current WAR still runs. Do not disable TLS checks, open all requests, or weaken HTTP validation merely to achieve compatibility.

## 31. HTTP Status Codes After Changing Containers

| Symptom | Layer Potentially Causing Error |
|---|---|
| 400 Bad Request | HTTP parser, invalid header/path, proxy/container constraints |
| 401 Unauthorized | Authentication filter, session/token |
| 403 Forbidden | Authorization, CSRF, CORS policy |
| 404 Not Found | Context root, servlet mapping, proxy rewrite, resources |
| 413 Payload Too Large | Proxy/container request size limit |
| 431 Request Header Fields Too Large | Header size limits |
| 500 Internal Server Error | App exception, JSP, JNDI, classloading |
| 502 Bad Gateway | Proxy cannot reach backend |
| 503 Service Unavailable | App/container not ready, ingress routing |
| 504 Gateway Timeout | Proxy/backend timeout, slow request |

These are investigation directions, not absolute rules. Always check logs from **the proxy, container, and Spring application** to see which layer rejected a request.

A request absent from application access logs may have been blocked at the ingress or connector, so editing controller code will not fix it.

## 32. Platform Selection Matrix Template

| Criterion | Question to Answer |
|---|---|
| JDK | Which Java runtime runs the server process? |
| Framework | Which Spring Boot/Spring Framework release is in use? |
| Servlet API | Which version and `javax`/`jakarta` namespace? |
| Container | Which Tomcat/Jetty/Undertow/application server release and patch? |
| Packaging | Embedded JAR, plain WAR, or executable WAR? |
| Provided libs | Which exact libraries does the container supply? |
| Servlet initialization | How do `SpringBootServletInitializer`, descriptors, and registrations work? |
| Classloading | Parent/child loading, common libs, isolation policies? |
| Context root | Who controls root paths and rewrites? |
| JNDI/resources | Who owns DataSources, transactions, and secrets? |
| TLS/network | Proxy, SNI, certificates, HTTP2, forwarded headers? |
| State | Session/cookies, serialized attributes, clustering? |
| Security | Filter chain, authn/authz, CSRF/CORS, management exposure? |
| Operations | Logs, tracing, metrics, readiness, redeploy, rollback? |

Do not identify only a combination that runs technically; also evaluate vendor support, patching, security lifecycle, and long-term operational capability.

## 33. Phased WAR Migration Workflow

### Phase A — Capture baseline

Record JDK, container, framework, WAR checksum, dependency graph, context root, JNDI, proxy/TLS, sessions, servlet filters, security rules, metrics, and test results.

### Phase B — Select a target with compatibility evidence

Choose the target JDK, Servlet generation, container branch, and supported framework release. Specifically identify the javax → jakarta boundary and third-party libraries that must be replaced.

### Phase C — Update source code and build

Upgrade toolchains, servlet imports, dependencies, generated code, configurations, and WAR packaging. With Boot, declare `SpringBootServletInitializer` and `provided/providedRuntime` according to the instructions of the version in use.

### Phase D — Inspect the artifact

Inspect `WEB-INF/lib`, duplicate dependencies, class-file major versions, web descriptors, and resources. Verify that no secrets or out-of-scope container implementations are embedded.

### Phase E — Stage on the exact container

Deploy the WAR onto the same JDK/container image and approximate network topology as production. Verify startup, JNDI, HTTP, security, persistence, sessions, JSP/WebSocket, and tracing.

### Phase F — Stress, restart, and rollback

Test redeploy, restart, load balancer failover, session behavior, long-lived connections, and performance. Design data and schema rollback before production deployment.

### Phase G — Rollout

Use canary/rolling rollout where appropriate. Watch error rates, authentication failures, database pools, classloader warnings, CPU/heap, and SLOs.

### Phase H — Clean up technical debt

Remove unneeded javax API dependencies, duplicate JARs, legacy server configs, and temporary compatibility workarounds. Update runbooks/ownership.

## 34. Checklist Before Concluding a WAR Is Compatible

- [ ] Container process JDK satisfies the framework and bytecode Java baseline.
- [ ] Servlet API specification/namespace matches both container and application.
- [ ] Container branch/patch still receives security support.
- [ ] No mixing of javax and jakarta Servlet types in integration paths.
- [ ] Build tools/Java compiler release and Java agents have been verified.
- [ ] WAR contains the right `WEB-INF/classes`, `WEB-INF/lib`, and resources.
- [ ] Container implementations are appropriately marked provided.
- [ ] Spring Boot WAR initializer/deployment descriptors are properly configured.
- [ ] Container shared libraries and classloader model have been inventoried.
- [ ] Context path, proxy rewrites, forwarded scheme/host, and redirects are correct.
- [ ] TLS/HTTP connectors, header/body limits, and timeouts have been tested.
- [ ] JNDI DataSources and resource ownership are correct.
- [ ] Servlet filters and the Security filter chain are neither missing nor registered twice.
- [ ] Login/session/cookies/CSRF/CORS and authorization have been tested.
- [ ] JSP/JSTL/WebSocket/async flows have been tested if used by the project.
- [ ] Integration tests run on the real WAR inside an external container.
- [ ] Undeploy/redeploy and resource cleanup have been tested.
- [ ] Metrics, tracing, logs, and alerts work.
- [ ] Performance and startup readiness have been compared against baseline.
- [ ] Plans exist for rolling upgrades, schema/session compatibility, and rollback.

The checklist is a technical guidance tool, **not QA test results of a specific system**.

## 35. Migration Report Template

~~~yaml
warMigration:
  application: orders-service
  from:
    java: "11"
    framework: "Spring Boot 2.x"
    servletApi: "javax.servlet"
    container: "Tomcat 9.x"
  target:
    java: "17"
    framework: "Spring Boot 3.x"
    servletApi: "jakarta.servlet"
    container: "Tomcat 10.1.x"
  packaging:
    mode: war
    initializerReviewed: false
    dependenciesReviewed: false
    jarOriginsReviewed: false
  platform:
    jndiReviewed: false
    contextPathVerified: false
    proxyTlsVerified: false
    classloaderReviewed: false
  tests:
    startupPassed: false
    httpContractPassed: false
    securityPassed: false
    sessionPassed: false
    persistencePassed: false
    redeployPassed: false
    observabilityPassed: false
  rollout:
    canaryPlanned: false
    rollbackPlanned: false
  owner: platform-team
  status: under-review
~~~

Versions and statuses are illustrative only. In a real project, record exact release/patch versions, JDK images, artifact checksums, logs, and actual test results before marking complete.

## 36. Common Pitfalls

**"Running the WAR on Java 17 is enough."** Insufficient: the Servlet API and container must match the framework. Boot 3 is not directly compatible with a javax Servlet container just because the JDK is newer.

**"Tomcat 10 is just a newer Tomcat 9."** Incorrect: the namespace moved from javax to jakarta in the Tomcat 10 generation.

**"Add javax.servlet-api.jar to fix Jakarta incompatibility."** Does not turn a legacy Filter into a Jakarta Filter. You must change the library/API contract.

**"Embedded JAR tests passing mean the external WAR passes."** An external container has different classloaders, connectors, and resources; deploy the actual WAR to test.

**"server.port in application.yml decides the external Tomcat port."** The HTTP connector belongs to the container in the external WAR model.

**"provided means every dependency is already on the server."** Use only when the runtime genuinely supplies that dependency and the team has verified its version.

**"Every WAR is executable via java -jar."** Only WARs with the proper launcher and packaging support that.

**"Startup succeeding means features work fine."** Many JNDI, repository, security matcher, JSP, and WebSocket failures only appear when those features are invoked.

**"Rollback is just copying back the old WAR."** Session data, database schemas, and message formats may have changed; you need a state rollback plan.

## 37. Summary Principles

- **Web servers, Servlet containers, application servers, and the JDK are distinct layers**, each with versions and contracts to verify.
- **WAR deployment must match JDK + Servlet namespace/version + container + framework + dependencies.**
- **`javax.servlet` and `jakarta.servlet` are not binary compatible**; adding API JARs does not replace code/library migration.
- **Tomcat 9 and 10.x belong to two different namespace generations.** Do not treat a major version change as a patch.
- **An application's Java baseline may be higher than the container's minimum Java**; the runtime must satisfy all of them.
- **Executable JARs and external WARs differ in classloading/configuration/lifecycles**; test them separately.
- **WAR packaging and dependency scopes must separate application-owned and container-owned libraries** to prevent conflicts.
- **JNDI, context roots, TLS, HTTP connectors, and session behavior may be managed by the external container or proxy**.
- **Filter registration, Spring Security, JSP, WebSocket, and Javax/Jakarta integrations** are key areas requiring behavioral testing.
- **Redeploy, rolling upgrades, and stateful rollback** are essential parts of WAR operability.
- **Verification must run on the exact WAR, exact JDK/container image, and network topology**, rather than looking only at a passing build.

In Java Advance Compatibility Migration, safe WAR deployment requires more than compiling Java code with a new JDK. Teams must ensure **the application, Servlet API, Servlet container, and JVM form a compatible combination**, control libraries by classloader/runtime ownership, and verify HTTP, data, security, and lifecycle contracts in real environments. When these boundaries are clearly designed, web platform upgrades become far easier to troubleshoot, deploy, and roll back.
