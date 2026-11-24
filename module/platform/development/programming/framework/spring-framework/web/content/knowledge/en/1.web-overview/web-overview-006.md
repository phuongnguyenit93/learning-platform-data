# Spring Versions, Jakarta Servlet, and API Compatibility

## 1. Why check versions before writing a web application?

A **Spring Web MVC** application does not run independently of its underlying layers: Java code is compiled with a JDK, uses Spring Framework and Servlet APIs, and is served by a Servlet container such as Tomcat or Jetty. If you use Spring Boot, Boot selects and manages most dependency versions and typically starts an embedded container.

There are four separate questions:

1. **Which JDK?** For example, Java 8, 17, 21, or 25; the JVM must run the bytecode and meet the minimum requirements of Spring and the container.
2. **Which Spring Framework?** For example, 5.3, 6.2, or 7.0; each generation has its own minimum Java/Jakarta EE baseline and API changes.
3. **Which Servlet API?** For example, Servlet 4.0 (`javax.servlet.*`), Jakarta Servlet 5.0/6.0/6.1 (`jakarta.servlet.*`); this is the contract between web code and the container.
4. **Which container?** For example, Tomcat 9/10.1/11; the container *implements* a Servlet version, and simply adding a Servlet API JAR does not upgrade the container.

**Article scope:** Spring MVC's Servlet-based web stack (`spring-webmvc`). Spring WebFlux can run on Reactor Netty and does not necessarily use the Servlet API; therefore, do not mechanically apply the Servlet container compatibility table to every WebFlux application.

## 2. Compatibility map to remember

| Typical application generation | Minimum Java | Web API/namespace | Typical Servlet container | Key note |
| --- | --- | --- | --- | --- |
| Spring Framework **5.3** / Spring Boot **2.7** | Java 8 | Java EE 8, **Servlet 4.0**, `javax.servlet.*` | **Tomcat 9** | Older line prior to the namespace transition. |
| Spring Framework **6.0–6.2** / Spring Boot **3.x** | Java 17 | Jakarta EE 9+, **Servlet 5.0+**, `jakarta.servlet.*` | Boot 3.5 embeds **Tomcat 10.1 / Servlet 6.0** | Servlet 5.0 is the minimum API level for Spring 6; actual embedded versions may be higher. |
| Spring Framework **7.0** / Spring Boot **4.x** | Java 17 | Jakarta EE 11, **Servlet 6.1+**, `jakarta.servlet.*` | **Tomcat 11 / Servlet 6.1**, or Jetty 12.1 | Raises the Servlet baseline; cannot be assumed deployable to Tomcat 10.1. |

**How to read the table:** this shows relationships between *version lines*, not an assertion that every Spring Boot patch picks the exact same Spring Framework version. For instance, Boot 3.5 uses Framework 6.2; Boot 4.0/4.1 uses Framework 7.0. Check the dependency management/BOM of your exact Boot version for actual library versions.

Dedicated table for **Tomcat and Servlet**:

| Tomcat | Servlet specification | Namespace |
| --- | --- | --- |
| 9.0.x | 4.0 | `javax.servlet.*` |
| 10.0.x (end-of-life) | 5.0 | `jakarta.servlet.*` |
| 10.1.x | 6.0 | `jakarta.servlet.*` |
| 11.0.x | 6.1 | `jakarta.servlet.*` |

**Two easily confused points:**

- The name *Jakarta EE 8* appeared before the package rename; Jakarta EE 8/Servlet 4.0 APIs still use the `javax.*` namespace. **Jakarta EE 9/Servlet 5.0** was the milestone that switched to `jakarta.*`.
- The minimum Java levels in the table are those of *Spring Framework/the application generation*. A standalone container might require an older Java version, but the entire application must still satisfy the **highest minimum** among its components. For example, Tomcat 10.1 can run on Java 11, yet Spring Framework 6 still requires Java 17+.

## 3. Where does the Servlet API sit in Spring MVC?

Simplified processing flow:

```text
HTTP client
    |
    v
Servlet container (Tomcat/Jetty)
    |
    v
jakarta.servlet.Filter chain
    |
    v
Spring DispatcherServlet
    |
    v
HandlerMapping -> @Controller/@RestController -> HandlerAdapter
    |
    v
HttpMessageConverter / ViewResolver
    |
    v
HTTP response
```

`DispatcherServlet` is a Servlet provided by Spring MVC. Spring uses objects from the Servlet API such as `HttpServletRequest`, `HttpServletResponse`, `ServletContext`, `Filter`, and `ServletRegistration`. The container creates and manages the lifecycle of requests/responses, filters, and servlets; Spring handles routing, binding, invoking handlers, error handling, and producing responses.

For example, the following signatures directly depend on the Servlet API namespace:

```java
// Spring Framework 5.3 / Spring Boot 2.x
import javax.servlet.http.HttpServletRequest;

// Spring Framework 6+ / Spring Boot 3+
import jakarta.servlet.http.HttpServletRequest;
```

These are **two distinct Java types** with different fully qualified names; they are not interchangeable just because both end in `HttpServletRequest`. Likewise, `javax.servlet.Filter` differs from `jakarta.servlet.Filter`.

## 4. The major break: Java EE → Jakarta EE

When enterprise specifications moved to Jakarta EE, affected APIs changed namespaces. For web applications, common examples include:

| Before (Java EE 8) | After (Jakarta EE 9+) | Role |
| --- | --- | --- |
| `javax.servlet.http.HttpServletRequest` | `jakarta.servlet.http.HttpServletRequest` | HTTP request |
| `javax.servlet.http.HttpServletResponse` | `jakarta.servlet.http.HttpServletResponse` | HTTP response |
| `javax.servlet.Filter` | `jakarta.servlet.Filter` | Filter |
| `javax.servlet.annotation.WebFilter` | `jakarta.servlet.annotation.WebFilter` | Filter registration |
| `javax.validation.Valid` | `jakarta.validation.Valid` | Bean Validation |
| `javax.persistence.Entity` | `jakarta.persistence.Entity` | JPA |
| `javax.annotation.PostConstruct` | `jakarta.annotation.PostConstruct` | Lifecycle annotation |

**Do not blindly replace every `javax.` with `jakarta.`.** Java SE APIs such as `javax.crypto`, `javax.net`, `javax.xml`, and `javax.management` did not undergo this conversion. Only update APIs that actually moved to Jakarta EE, guided by the library versions in use.

The change has three consequences:

- **Source compatibility:** importing `javax.servlet.*` will not compile in a project that only has `jakarta.servlet-api`; source code and related types must be updated.
- **Binary compatibility:** a JAR compiled against `javax` Servlet still has bytecode references to `javax/servlet/...`; changing imports only in the *application* does not make that library compatible. You need a version of the library built for Jakarta or a verified artifact transformation.
- **Runtime compatibility:** Jakarta-based containers do not supply `javax`-typed Servlets for newer Spring MVC apps; you may encounter `ClassNotFoundException`, `NoClassDefFoundError`, Servlet/filter initialization failures, or WAR deployment failures.

Tomcat's migration tool can help transform namespaces in legacy artifacts in some cases, but it does not replace checking for removed APIs, behavioral changes, third-party libraries, deployment config, and integration tests.

## 5. Runnable practical example: Spring Boot 3.5 and Jakarta Servlet

The following example uses **Java 17+, Spring Boot 3.5.16**, Maven, and `spring-boot-starter-web`. Boot manages Spring Framework along with a compatible embedded Tomcat; you do not manually add an arbitrary `servlet-api` version. The app returns the Servlet version reported by the container.

**Project structure:**

```text
servlet-compat/
├── pom.xml
└── src/main/java/demo/
    ├── WebApplication.java
    └── ServletInfoController.java
```

**`pom.xml`:**

```xml
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
    <groupId>demo</groupId>
    <artifactId>servlet-compat</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
```

**`src/main/java/demo/WebApplication.java`:**

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebApplication.class, args);
    }
}
```

**`src/main/java/demo/ServletInfoController.java`:**

```java
package demo;

import jakarta.servlet.ServletContext;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ServletInfoController {
    @GetMapping("/api/servlet")
    public String servletVersion(HttpServletRequest request) {
        ServletContext context = request.getServletContext();
        return "Servlet " + context.getMajorVersion()
                + "." + context.getMinorVersion();
    }
}
```

**Run with JDK 17+ and Maven installed:**

```bash
mvn spring-boot:run
```

In another terminal:

```bash
curl -s http://localhost:8080/api/servlet
```

HTTP body result with **Boot 3.5's default embedded Tomcat 10.1**:

```text
Servlet 6.0
```

On Windows PowerShell you can use `curl.exe` instead of `curl`. The output reflects the **container's Servlet specification**, not the Spring Framework version string or JDK version. If you switch to a different container, the response may differ.

**Intentional error test:** change the import line in the controller to `import javax.servlet.http.HttpServletRequest;` while keeping the Boot 3.5 dependencies above. The project lacks that type on the compile classpath and reports a compilation error involving package `javax.servlet.http`. The fix is to use `jakarta.servlet.http.HttpServletRequest` as shown in the example, not adding a `javax.servlet-api` JAR to mask the error.

## 6. Spring Framework, Spring Boot, and the Servlet container do not share one version

- **Spring Framework** provides `spring-web`, `spring-webmvc`, IoC, transactions, etc. The framework does not itself dictate a project's embedded Tomcat version.
- **Spring Boot** is the configuration, dependency management, starters, auto-configuration, and packaging layer. Boot's BOM determines the Spring and embedded container versions tested together.
- **Servlet API** consists of the standard interfaces/classes that application code compiles against.
- **Servlet container** provides the runtime implementation, owning the lifecycle of requests/responses, servlets, and filters.

In a **Boot executable JAR**, `spring-boot-starter-web` pulls in a managed embedded container (usually Tomcat by default). For a **WAR deployed to an external container**, the target container must meet the Servlet level required by the Spring generation, and packaging must avoid bundling conflicting container classes/implementations.

Do not conclude "I am using Java 21, so Tomcat 9 can run Spring 6." A sufficiently new Java version only satisfies one condition; Tomcat 9 still provides `javax.servlet`/Servlet 4.0 and therefore does not satisfy Spring 6's Jakarta Servlet requirement.

## 7. Choosing versions when starting and upgrading

### Scenario A: existing Spring Boot 2.7 + Tomcat 9 application

This set belongs to the `javax.servlet.*` generation. When migrating to Boot 3.x, you must **simultaneously** raise the JDK requirement to 17+, migrate relevant Java EE APIs to `jakarta.*`, choose Jakarta-compatible libraries, and check the container. Upgrading only Tomcat from 9 to 10.1 while keeping an old `javax` WAR is not a complete compatible upgrade.

### Scenario B: Boot 3.5 + Tomcat 10.1 application

This is a valid combination: Spring 6.2 + Java 17+ + Jakarta Servlet 6.0 (Spring 6's minimum is Servlet 5.0). When deploying an external WAR, check the target container version and actual dependencies rather than relying on local compilation succeeding.

### Scenario C: wanting to upgrade from Boot 3.x to Boot 4.x

Boot 4.x moves to Spring 7, using Jakarta EE 11/Servlet **6.1+**. If previously running Tomcat 10.1 (Servlet 6.0), you must choose a container meeting Servlet 6.1, such as Tomcat 11, while auditing Spring/Boot changes and related libraries. The namespace remains `jakarta.*`, yet **sharing the same namespace does not guarantee the same API version**.

### Scenario D: an internal web library still imports `javax.servlet.Filter`

For Spring 6+/Boot 3+, upgrade or rebuild the library against the appropriate Jakarta API. When publishing a library, specify clearly whether a variant supports `javax` or `jakarta`, declare the proper API dependency, and test with the target container. A library targeting both generations may need two artifacts/modules or an explicit adapter layer; Java does not treat the two interfaces as the same type.

## 8. Practical compatibility verification workflow

1. **Record the current version set:** `java -version`; Boot/Framework version in `pom.xml` or `build.gradle`; JAR/WAR packaging type; actual container version.
2. **Verify the dependency tree:** with Maven you can run `mvn dependency:tree` to inspect Spring, Tomcat, and Servlet JARs; with Gradle use `./gradlew dependencies --configuration runtimeClasspath`, or `dependencyInsight` for a specific dependency.
3. **Check namespaces in code and dependencies:** search for `javax.servlet`, `javax.validation`, `javax.persistence`, `Filter`/`Servlet` implementations, listeners, JSP/tag libraries, integrated frameworks, and legacy annotations. Only migrate packages that have an actual mapping.
4. **Read the baseline from documentation for the exact Spring/Boot line:** Java, Servlet, Jakarta EE levels, and supported container list. Do not randomly pair a new Spring version with an old Boot BOM.
5. **Clean build and run tests:** test compilation, context startup, HTTP endpoints, filters/security, serialization, validation, and error handling; if deploying a WAR, test on the **exact target server**.
6. **Verify HTTP contracts after migration:** paths, methods, status codes, headers, JSON, CORS, and authentication. Client-facing contracts can remain intact even when changing the internal Servlet foundation, but this must be proven through testing.

Example diagnostic commands (in the Maven project from section 5):

```bash
java -version
mvn dependency:tree -Dincludes=org.springframework:spring-webmvc
mvn dependency:tree -Dincludes=org.apache.tomcat.embed:tomcat-embed-core
mvn dependency:tree -Dincludes=jakarta.servlet:jakarta.servlet-api
```

```bash
# Gradle: run in a project that has the Gradle wrapper
./gradlew dependencyInsight --dependency spring-webmvc --configuration runtimeClasspath
./gradlew dependencyInsight --dependency tomcat-embed-core --configuration runtimeClasspath
```

`jakarta.servlet-api` does not always appear as a direct dependency in the runtime tree: the Servlet implementation may be provided by the container, and scopes/classpaths differ across compile, runtime, and WAR deployment. Always inspect the full dependency configuration and runtime environment.

## 9. Common errors and troubleshooting

| Symptom | Possible cause | How to check and fix |
| --- | --- | --- |
| `package javax.servlet.http does not exist` on Boot 3 | Code still uses pre-Jakarta EE 9 namespace | Switch the relevant APIs to `jakarta.servlet.http` and update related libraries. |
| `NoClassDefFoundError: javax/servlet/Filter` | An old JAR compiled for `javax.servlet` | Identify the JAR via stack trace/dependency tree and upgrade to a Jakarta-compatible version. |
| Deploying a Spring 6 WAR to Tomcat 9 fails | Container only has Servlet 4.0/`javax` | Pick a Jakarta Servlet-compatible container and verify WAR configuration. |
| Deploying Spring 7 on Tomcat 10.1 fails | Tomcat 10.1 implements Servlet 6.0, below baseline 6.1 | Choose a Servlet 6.1+ container such as Tomcat 11. |
| `UnsupportedClassVersionError` | Runtime JVM is older than the Java bytecode target used to build | Check **runtime** `java -version`, compiler target, and framework Java baseline. |
| `NoSuchMethodError` or `AbstractMethodError` | Mismatched API/implementation or library versions | Analyze classpath, BOM, and dependency overrides; align to a supported version set. |
| Code compiles, but requests behave wrongly after upgrade | Changes in routing/filter/converter/default behavior | Use integration tests and compare status/headers/body across versions. |

**Rule to avoid errors:** do not arbitrarily add both `javax.servlet-api` and `jakarta.servlet-api` to "support everything." The two type hierarchies do not convert into each other; having both on the classpath may simply mask library incompatibilities.

## 10. Distinguishing types of compatibility

**Source compatibility** refers to whether Java code still compiles against a new API version. **Binary compatibility** refers to whether already-built bytecode/JARs can still link classes and methods at runtime. **Runtime/platform compatibility** covers the JVM, Servlet container, and actual implementations. **HTTP/API contract compatibility** is the commitment to clients via URLs, statuses, headers, and bodies; it does not force the backend to keep the same Servlet namespace.

For example, upgrading from Boot 2.7 to 3.5 may require updating Java imports and replacing `javax` libraries to build and run, yet the `GET /api/users` endpoint can still return the exact same JSON and status to clients. On the other hand, a successful build after switching namespaces does not yet prove that filters, security, serialization, or HTTP error responses preserve identical behavior.

## 11. Self-check for comprehension

- Can a Spring Framework 6.2 project compiled with Java 21 be deployed to Tomcat 9? **No**: Tomcat 9 is Servlet 4.0/`javax`, incompatible with the Jakarta Servlet 5.0+ required by Spring 6.
- Why can Boot 3.5 return `Servlet 6.0` even though the table states Spring 6 requires Servlet 5.0+? Because **5.0+ is the minimum**, whereas embedded Tomcat 10.1 implements Servlet 6.0.
- Once `javax.servlet` is changed to `jakarta.servlet`, can all old JARs be kept? **No**: compiled JARs reference specific class and method names; dependencies must be checked and upgraded.
- Do Spring 7 and Spring 6, which both use `jakarta.*`, both run on Tomcat 10.1? **You cannot assume that**: Spring 7 has a Servlet 6.1 baseline, whereas Tomcat 10.1 is 6.0.
- Should `javax.crypto.Cipher` be changed to `jakarta.crypto.Cipher`? **No**: `javax.crypto` belongs to Java SE and was not part of the Servlet/Jakarta EE namespace move.

## 12. Official documentation sources and how to use them

The baseline tables and examples are based on current release documentation at the time of writing. When upgrading to a new patch or milestone, prioritize the documentation for the **exact version** you are deploying:

- [Spring Framework Versions — JDK/Jakarta EE baselines](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-Versions).
- [Spring Framework Overview — moving from Java EE to Jakarta EE](https://docs.spring.io/spring-framework/reference/overview.html).
- [Spring Web MVC and DispatcherServlet](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet.html).
- [Spring Boot 3.5 System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html).
- [Spring Boot 4.1 System Requirements](https://docs.spring.io/spring-boot/system-requirements.html).
- [Apache Tomcat: Which Version Do I Want?](https://tomcat.apache.org/whichversion.html).
- [Jakarta Servlet 6.1 specification](https://jakarta.ee/specifications/servlet/6.1/).

**Selection principle:** always verify **JDK + Spring Framework/Boot + Servlet specification + container + application dependencies** as one unified compatibility set.