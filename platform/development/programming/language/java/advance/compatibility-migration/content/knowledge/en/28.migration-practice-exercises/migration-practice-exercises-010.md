# Migrating a javax Component to jakarta with Proper Scope

One of the common mistakes when upgrading Java EE applications is using a project-wide find-and-replace: changing every `javax.` string to `jakarta.`. Doing so can break APIs **that still belong to Java SE**, such as `javax.sql.DataSource`, `javax.crypto.Cipher`, `javax.naming.InitialContext`, `javax.net.ssl.SSLContext`, or `javax.tools.JavaCompiler`. Conversely, if you only update imports in one class without upgrading the API dependency, Servlet container, or execution library, the application may build yet fail immediately at startup with `NoClassDefFoundError`.

This lab guides migrating **exactly one component with a clear boundary**: `RequestIdFilter`, a Servlet filter attaching a request identifier to `/api/*` endpoints. The old version uses `javax.servlet.*`; the new version uses `jakarta.servlet.*`. We will lock down the scope, preserve the input/output contract, update the corresponding code and dependencies, write JUnit/Mockito tests, package a WAR, and verify on the target container. The pattern applies to many Java EE → Jakarta migrations, though **it does not mean every Java EE component must be upgraded simultaneously in the same way**.

## 1. Learning Objectives

After this lab, you can:

1. Determine whether a `javax.*` API belongs to the Java/Jakarta EE group requiring a namespace change.
2. Identify a component's boundaries and direct dependencies without editing unrelated areas.
3. Select appropriate Jakarta Servlet API, JDK, and Servlet container versions.
4. Migrate `Filter`, `ServletRequest`, `ServletResponse`, `FilterChain`, and `ServletException` signatures to the right namespace.
5. Preserve behavior: requests continue through the filter chain exactly once, with a consistent request ID and response header.
6. Write tests verifying both the success path and error paths.
7. Package properly with Maven `provided` scope for a WAR running on a container providing the Jakarta API.
8. Diagnose errors from mixing `javax.servlet`/`jakarta.servlet` or loading the wrong artifact.
9. Know when the entire runtime boundary must be upgraded and when to isolate a legacy component behind a protocol adapter.
10. Record evidence and an appropriate rollback plan before applying in a real system.

## 2. Lab Context

Suppose the system has a legacy WAR deployed on **Apache Tomcat 9**, using Java 8 or a JDK supported by Tomcat 9, with the Servlet API in the `javax.servlet.*` namespace. Inside the WAR is the filter:

```text
HTTP request
     |
     v
RequestIdFilter (javax.servlet.Filter)
     |
     v
Other filters / Servlet / Controller
     |
     v
HTTP response with X-Request-ID
```

The goal of this lab is to migrate the filter and the test WAR environment to:

| Component | Before | After |
|---|---|---|
| Build JDK | Java 8 in the initial scenario | Java 17 |
| API | Java EE Servlet, `javax.servlet.*` | Jakarta Servlet 6.0, `jakarta.servlet.*` |
| Container | Tomcat 9.x | Tomcat 10.1.x |
| Packaging | WAR | WAR |
| Business logic | Generate request ID and continue filter chain | Unchanged |
| Applied URL | `/api/*` | Unchanged within webapp scope |
| HTTP response | `X-Request-ID` | Unchanged |
| Java SE packages | Unchanged | Unchanged |

**Important:** Tomcat 10.1 supports Jakarta Servlet 6.0 and requires Java 11 or later; in this lesson we choose Java 17 to have a concrete baseline. Tomcat 10.0 belongs to the Servlet 5.0 generation, whereas Tomcat 9 uses the `javax.servlet.*` namespace. Do not choose API/container versions arbitrarily based on major numbers.

To make the workshop easy to reproduce, we create a **minimal test WAR** containing only the filter and a `/api/ping` servlet. `PingServlet` is merely a fixture verifying the HTTP path; **the primary component being migrated is `RequestIdFilter`**. In a real system, components residing on the same servlet runtime must also be Jakarta-compatible; the lesson does not recommend placing the new filter into a WAR running on Tomcat 9.

## 3. What Does "Proper Scope" Mean?

Three scopes must be separated:

- **Code modification scope:** one filter and its related imports/type signatures.
- **Mandatory synchronized runtime scope:** the Servlet API and the container/Jakarta-compatible framework into which the filter is deployed.
- **Out of scope:** other modules that do not depend on the filter, business domain, database schema, Java SE `javax.*` packages, and unrelated API clients.

A migration plan can confine code changes to a single class, yet **cannot** keep the `javax.servlet.Filter` container runtime and expect it to accept an object implementing `jakarta.servlet.Filter`: those are two different interfaces in terms of Java type identity.

### 3.1. Dependency boundary to draw

```text
                                Java SE API
                     java.util.UUID, java.io.IOException
                                  |
                                  v
                    +---------------------------+
HTTP /api/* ------> | RequestIdFilter           |
                    | jakarta.servlet.Filter    |
                    +---------------------------+
                         |                 |
                         v                 v
             jakarta.servlet-api      Servlet container
                   6.0.0               Tomcat 10.1.x
                         |
                         v
                  /api/ping fixture
```

The UUID generation logic in `java.util` needs no namespace migration. What needs changing are the Servlet-facing interface and type signatures, along with the execution API/container.

## 4. Classifying javax Imports Before Editing

A legacy set of imports might contain:

```java
import javax.servlet.Filter;
import javax.servlet.ServletException;
import javax.sql.DataSource;
import javax.crypto.Cipher;
import javax.naming.InitialContext;
import javax.net.ssl.SSLContext;
import javax.xml.parsers.DocumentBuilderFactory;
```

Do **not** replace all of them with `jakarta.*`. Classification:

| Old import | Decision | Reason |
|---|---|---|
| `javax.servlet.Filter` | Change to `jakarta.servlet.Filter` | Servlet is a Jakarta EE API after namespace migration. |
| `javax.servlet.FilterChain` | Change to `jakarta.servlet.FilterChain` | Must use the same Servlet API family. |
| `javax.servlet.ServletRequest` | Change to `jakarta.servlet.ServletRequest` | Type in the new Servlet filter signature. |
| `javax.servlet.ServletResponse` | Change to `jakarta.servlet.ServletResponse` | Type in the new filter signature. |
| `javax.servlet.ServletException` | Change to `jakarta.servlet.ServletException` | Corresponding exception API. |
| `javax.servlet.http.HttpServletResponse` | Change to `jakarta.servlet.http.HttpServletResponse` | New HTTP Servlet API. |
| `javax.annotation.PostConstruct` | Evaluate migrating to `jakarta.annotation.PostConstruct` if using Jakarta Annotations | Do not change if it is another API or out-of-scope code. |
| `javax.persistence.Entity` | Only change when upgrading the JPA/Jakarta Persistence layer | Not directly related to the filter. |
| `javax.validation.Valid` | Only change when upgrading the Bean Validation/Jakarta Validation stack | Does not belong to Java SE, yet must be decided per module. |
| `javax.sql.DataSource` | **Keep unchanged** | Java SE JDBC API. |
| `javax.crypto.Cipher` | **Keep unchanged** | Java SE cryptography API. |
| `javax.naming.InitialContext` | **Keep unchanged** | Java SE JNDI API. |
| `javax.net.ssl.SSLContext` | **Keep unchanged** | Java SE TLS API. |
| `javax.xml.parsers.DocumentBuilderFactory` | **Keep unchanged** | Java SE XML/JAXP API. |
| `javax.tools.JavaCompiler` | **Keep unchanged** | Java SE compiler API. |

This is the core of the "proper scope" requirement: only change APIs with a **confirmed owner and namespace version**, not based merely on the `javax` prefix.

## 5. Pre-Migration Inventory

In a real project, list:
- Which files actually import `javax.servlet.*`.
- Which classes `implements Filter`, `extends HttpServlet`, or implement `ServletRequestListener`.
- `web.xml` configuration, `@WebFilter`, `@WebServlet`, programmatic filter registrations.
- Which Tomcat version the WAR runs on.
- Which Maven/Gradle scope the Servlet API dependency is declared with.
- Third-party libraries using Servlet Filters such as security filters, tracing, compression, CORS.
- Filter order, URL mapping, async/dispatcher types.
- Client-visible behavior: response headers, error paths, encoding, status.
- Java SE `javax.*` imports that must be preserved.

Example string-search commands (illustrative for source code in a workspace):

```bash
grep -R "javax\.servlet" src/
grep -R "jakarta\.servlet" src/
grep -R "RequestIdFilter" src/
```

On PowerShell, you can use:

```powershell
Get-ChildItem -Recurse -File src |
  Select-String -Pattern 'javax\.servlet','jakarta\.servlet','RequestIdFilter'
```

Search results are not an automatic replacement list: you must read which type/annotation is being used and where it is loaded at runtime.

## 6. Confirming the Contract Before Editing

For `RequestIdFilter`, define the expected output:

| Condition | Behavior |
|---|---|
| Request matches `/api/*` | Filter is invoked exactly once per declared mapping/dispatch. |
| Request reaches filter | Generates a UUID string without relying on untrusted input. |
| In downstream code | Attribute `requestId` holds the same UUID. |
| HTTP response | Header `X-Request-ID` holds the same UUID. |
| Downstream succeeds | Filter invokes `chain.doFilter(...)` exactly once. |
| Downstream throws `ServletException` or `IOException` | Does not swallow the exception or alter status in violation of the contract. |
| URL outside `/api/*` | Filter must not inject the header unless another mapping exists. |
| Dispatcher type | Only REQUEST in the example; ERROR/FORWARD/ASYNC must be decided separately if required by the application. |

This contract is sufficient to catch migrations that alter behavior even when code compiles. If in a real project the request ID is taken from an upstream proxy, add a specific input validation/normalization policy instead of blindly accepting client-sent headers.

## 7. Pre-Migration Code: javax Servlet Filter

Legacy file `src/main/java/com/example/web/RequestIdFilter.java`:

```java
package com.example.web;

import java.io.IOException;
import java.util.UUID;

import javax.servlet.DispatcherType;
import javax.servlet.Filter;
import javax.servlet.FilterChain;
import javax.servlet.ServletException;
import javax.servlet.ServletRequest;
import javax.servlet.ServletResponse;
import javax.servlet.annotation.WebFilter;
import javax.servlet.http.HttpServletResponse;

@WebFilter(
    urlPatterns = "/api/*",
    dispatcherTypes = {DispatcherType.REQUEST}
)
public final class RequestIdFilter implements Filter {

    public static final String ATTRIBUTE = "requestId";
    public static final String HEADER = "X-Request-ID";

    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {

        String id = UUID.randomUUID().toString();
        request.setAttribute(ATTRIBUTE, id);

        if (response instanceof HttpServletResponse) {
            ((HttpServletResponse) response).setHeader(HEADER, id);
        }

        chain.doFilter(request, response);
    }
}
```

This is written in syntax compatible with Java 8. Logic:
1. Generate a UUID.
2. Store the request attribute.
3. Set the HTTP response header.
4. Invoke the chain once.
5. Let downstream exceptions propagate per contract.

A common mistake when upgrading: developers change the first few imports yet forget `ServletException`, `FilterChain`, or `@WebFilter` belonging to the same namespace. **Every Servlet API type** in the component must be changed, not just the `Filter` interface.

## 8. Preparing the Test Maven Project

Create a Maven WAR project with a minimal structure:

```text
request-id-demo/
├── pom.xml
├── src/
│   ├── main/
│   │   └── java/com/example/web/
│   │       ├── RequestIdFilter.java
│   │       └── PingServlet.java
│   └── test/
│       └── java/com/example/web/
│           └── RequestIdFilterTest.java
└── target/                 (generated by Maven)
```

**Do not place two versions of `RequestIdFilter` into the same source set.** The legacy version in the section above is only for comparison. Keep only the new Jakarta code in the target project.

The `pom.xml` file illustrates Jakarta Servlet 6.0, Java 17, and JUnit 5/Mockito versions. The plugin/test dependency versions are a reproducible example set when resolved from an appropriate repository, **not to be treated as a recommendation for the latest versions at all times**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>request-id-demo</artifactId>
    <version>1.0.0</version>
    <packaging>war</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <junit.version>5.11.4</junit.version>
        <mockito.version>5.15.2</mockito.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>jakarta.servlet</groupId>
            <artifactId>jakarta.servlet-api</artifactId>
            <version>6.0.0</version>
            <scope>provided</scope>
        </dependency>

        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.version}</version>
            <scope>test</scope>
        </dependency>

        <dependency>
            <groupId>org.mockito</groupId>
            <artifactId>mockito-core</artifactId>
            <version>${mockito.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-war-plugin</artifactId>
                <version>3.4.0</version>
                <configuration>
                    <failOnMissingWebXml>false</failOnMissingWebXml>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Why `provided`?

- Maven uses the Jakarta Servlet API to **compile** and **run unit tests**.
- Tomcat 10.1 provides the Servlet implementation/API at runtime.
- A WAR should not package another copy of the Servlet API into `WEB-INF/lib/` when the container is the provider.

In an **embedded server** application or executable JAR, dependency management may differ; in this lesson we intentionally choose an external container WAR to illustrate clearly.

## 9. Checking the JDK Maven Actually Uses

Before compiling in the learning environment:

```bash
java -version
javac -version
mvn -version
```

Expectation: Maven runs on a JDK matching the Java 17 toolchain. When multiple installations exist on a machine, `mvn -version` may differ from `java -version` in the shell. If the project uses Maven Toolchains, check the configuration selecting the actual compiler.

Do not try to use `-source 8 -target 8` with code leveraging Java 17 syntax. In the target example, `maven.compiler.release=17` specifies the target source, bytecode, and Java SE API level for the compiler in use.

When working in a real system, a lower release may be chosen if the framework/container supports it and business requires it. Java 17 is an illustrative baseline, not a fixed requirement for every Jakarta Servlet application.

## 10. Post-Migration Code: jakarta Servlet Filter

Replace `src/main/java/com/example/web/RequestIdFilter.java` with:

```java
package com.example.web;

import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.DispatcherType;
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.annotation.WebFilter;
import jakarta.servlet.http.HttpServletResponse;

@WebFilter(
    urlPatterns = "/api/*",
    dispatcherTypes = {DispatcherType.REQUEST}
)
public final class RequestIdFilter implements Filter {

    public static final String ATTRIBUTE = "requestId";
    public static final String HEADER = "X-Request-ID";

    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {

        String id = UUID.randomUUID().toString();
        request.setAttribute(ATTRIBUTE, id);

        if (response instanceof HttpServletResponse httpResponse) {
            httpResponse.setHeader(HEADER, id);
        }

        chain.doFilter(request, response);
    }
}
```

Key changes:
- `javax.servlet.*` → `jakarta.servlet.*`.
- `javax.servlet.annotation.WebFilter` → `jakarta.servlet.annotation.WebFilter`.
- `javax.servlet.http.HttpServletResponse` → `jakarta.servlet.http.HttpServletResponse`.
- Kept `java.io.IOException` and `java.util.UUID` unchanged.
- The `instanceof` part uses pattern matching valid in Java 17, though you can keep the old cast style if you want to minimize syntax changes.

**Regarding behavior:** response header, request attribute, URL mapping, and downstream forwarding mechanism remain unchanged. This is a migration of **type namespace and runtime contract**, not a business logic change.

## 11. Fixture Endpoint to Test Real Requests

Add `src/main/java/com/example/web/PingServlet.java`:

```java
package com.example.web;

import java.io.IOException;

import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

@WebServlet("/api/ping")
public final class PingServlet extends HttpServlet {

    @Override
    protected void doGet(
            HttpServletRequest request,
            HttpServletResponse response)
            throws IOException {

        Object requestId =
                request.getAttribute(RequestIdFilter.ATTRIBUTE);

        response.setContentType("text/plain");
        response.setCharacterEncoding("UTF-8");

        response.getWriter().println(
                "pong; requestId=" + requestId);
    }
}
```

`PingServlet` only acts as an HTTP test fixture and does not represent having to migrate all controllers in a real project. Because the fixture runs **in the same Jakarta Servlet container**, it must also use `jakarta.servlet.http.*`. This illustrates the difference between **the scope of code intentionally edited** (the filter) and **the runtime boundary types** that must align for testing to be meaningful.

Expected response:

```text
HTTP/1.1 200
X-Request-ID: 0b7f... (UUID)

pong; requestId=0b7f... (same value)
```

The UUID is only illustrative and changes per request.

## 12. Why Are Annotations and URL Mappings Also Within Scope?

A Servlet component is not just a Java interface. The container may look for:
- `@WebFilter`.
- `web.xml` filter/filter-mapping.
- Programmatic `ServletContext.addFilter`.
- Framework-specific filter registration.
- `@WebListener` or ServletContainerInitializer in certain architectures.

If you change the implementation to `jakarta.servlet.Filter` yet leave `javax.servlet.annotation.WebFilter` metadata in an old artifact, the Jakarta container might not register the filter as expected. If both annotation and web.xml register it, the filter risks being invoked multiple times or in a different order.

In this lesson, use **only `@WebFilter`** and do not declare a duplicate filter in `web.xml`. In a real application, check ordering, dispatcher types, async support, and the existing registration method; do not arbitrarily convert to annotations if preserving a specific order is needed.

### 12.1. Context path is not inside the filter URL pattern

Suppose the WAR is deployed to context:

```text
/request-id-demo
```

HTTP URL:

```text
http://localhost:8080/request-id-demo/api/ping
```

`@WebFilter(urlPatterns = "/api/*")` is declared **within the webapp scope**, not `/request-id-demo/api/*`. Confusing context path with servlet mapping can prevent the filter from running as expected.
## 13. JUnit/Mockito Unit Tests: Preserving the Contract

In this lab, the most important goal is not seeing the word `jakarta` in imports, but confirming the filter still functions properly. Therefore, tests use the **Jakarta Servlet interfaces** themselves on the test classpath.

File `src/test/java/com/example/web/RequestIdFilterTest.java`:

```java
package com.example.web;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;

import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

class RequestIdFilterTest {

    @Test
    void shouldSetRequestIdAndContinueOnce() throws Exception {
        HttpServletRequest request =
                mock(HttpServletRequest.class);
        HttpServletResponse response =
                mock(HttpServletResponse.class);
        FilterChain chain = mock(FilterChain.class);

        RequestIdFilter filter = new RequestIdFilter();
        filter.doFilter(request, response, chain);

        ArgumentCaptor<String> idCaptor =
                ArgumentCaptor.forClass(String.class);

        verify(request).setAttribute(
                eq(RequestIdFilter.ATTRIBUTE),
                idCaptor.capture());

        String id = idCaptor.getValue();
        assertDoesNotThrow(() -> UUID.fromString(id));

        verify(response).setHeader(
                RequestIdFilter.HEADER, id);

        verify(chain, times(1)).doFilter(request, response);
    }

    @Test
    void shouldPropagateServletException() throws Exception {
        ServletRequest request = mock(ServletRequest.class);
        ServletResponse response = mock(ServletResponse.class);
        FilterChain chain = mock(FilterChain.class);

        ServletException failure =
                new ServletException("downstream failed");

        doThrow(failure).when(chain)
                .doFilter(request, response);

        ServletException actual = assertThrows(
                ServletException.class,
                () -> new RequestIdFilter().doFilter(
                        request, response, chain));

        assertEquals("downstream failed", actual.getMessage());
        verify(chain, times(1)).doFilter(request, response);
    }

    @Test
    void shouldPropagateIOException() throws Exception {
        ServletRequest request = mock(ServletRequest.class);
        HttpServletResponse response =
                mock(HttpServletResponse.class);
        FilterChain chain = mock(FilterChain.class);

        doThrow(new IOException("output failed")).when(chain)
                .doFilter(request, response);

        IOException actual = assertThrows(
                IOException.class,
                () -> new RequestIdFilter().doFilter(
                        request, response, chain));

        assertEquals("output failed", actual.getMessage());
        verify(chain, times(1)).doFilter(request, response);
    }

    @Test
    void shouldHandleNonHttpServletResponse() throws Exception {
        ServletRequest request = mock(ServletRequest.class);
        ServletResponse response = mock(ServletResponse.class);
        FilterChain chain = mock(FilterChain.class);

        new RequestIdFilter().doFilter(request, response, chain);

        verify(chain, times(1)).doFilter(request, response);
    }
}
```

### 13.1. What these tests verify

- **Compile-time type compatibility:** both tests and filter use `jakarta.servlet.*`.
- **Matching attribute and header:** the request ID generated by the filter is a parseable UUID, with the exact same value passed downstream and in the HTTP header.
- **Filter does not block requests:** `chain.doFilter` is invoked exactly once.
- **Exception propagation:** does not swallow downstream `ServletException` or `IOException`.
- **Non-HTTP response:** the filter does not blindly cast `ServletResponse` to an HTTP response.

Note that Mockito is a mocking library; unit tests **do not prove** the container actually discovers annotations, maps `/api/*`, orders filters, or resolves the API/runtime classloader. That is why deploying the WAR on a real container is necessary.

### 13.2. Why is testing "same value" more important than testing isolated calls?

A buggy implementation could generate two UUIDs:

```java
request.setAttribute("requestId",
        UUID.randomUUID().toString());

httpResponse.setHeader("X-Request-ID",
        UUID.randomUUID().toString());
```

Then an isolated test checking "was header set" still passes, yet the request attribute and header do not match, making tracing useless. Testing uses `ArgumentCaptor` to verify **a single value preserved across the boundary**, fulfilling the contract goal.

## 14. Explicitly Testing Type Identity

A small test can be added:

```java
package com.example.web;

import static org.junit.jupiter.api.Assertions.assertTrue;
import jakarta.servlet.Filter;
import org.junit.jupiter.api.Test;

class ServletNamespaceTest {

    @Test
    void filterImplementsJakartaContract() {
        assertTrue(Filter.class.isAssignableFrom(
                RequestIdFilter.class));
    }
}
```

This test proves the implementation class is compatible with `jakarta.servlet.Filter` **on the selected test classpath**. It does not replace checking the server runtime: the Jakarta API class could still be absent in a Tomcat 9 container or loaded from an inappropriate classloader.

### 14.1. No automatic cast adapter between the two Filters

Even though both interfaces have very similar methods:

```text
javax.servlet.Filter
        ≠
jakarta.servlet.Filter
```

An object implementing `javax.servlet.Filter` cannot simply be cast to `jakarta.servlet.Filter`. Do not write:

```java
jakarta.servlet.Filter newFilter =
        (jakarta.servlet.Filter) oldJavaxFilter;
```

If `oldJavaxFilter` does not actually implement Jakarta Filter, the cast does not become valid by adding both API JARs. For legacy binaries that cannot be recompiled, consider a supported transformation tool or isolate an adapter at **another boundary**, rather than using an incompatible cast.

## 15. Compiling, Running Unit Tests, and Building the WAR

Inside `request-id-demo/`, on a machine with Maven and an appropriate JDK:

```bash
mvn clean test
mvn package
```

Or run the target full lifecycle:

```bash
mvn clean verify
```

These are **commands learners can execute in the practice project**; the lesson content does not claim these commands have already been run.

With the POM in section 8, the expected output file:

```text
target/request-id-demo-1.0.0.war
```

Reading the build output:
- Java sources compile with no remaining dependency on `javax.servlet.*`.
- Unit tests run with `jakarta.servlet-api` on the test/compile classpath.
- Build produces a WAR, not just an ordinary JAR.
- If the build runs with a JDK that does not support `--release 17`, adjust the toolchain properly rather than changing APIs arbitrarily.
- A warning from another plugin must be classified, not papered over by adding an old JAR like `javax.servlet-api`.

## 16. Inspecting Contents Inside the WAR

Use:

```bash
jar tf target/request-id-demo-1.0.0.war
```

Typical entries include:

```text
META-INF/
WEB-INF/
WEB-INF/classes/
WEB-INF/classes/com/example/web/RequestIdFilter.class
WEB-INF/classes/com/example/web/PingServlet.class
...
```

You should not see `WEB-INF/lib/jakarta.servlet-api-6.0.0.jar` inside the WAR with the `provided` dependency in this POM, because the container provides the API. However, the WAR plugin may include test/other dependencies with wrong scopes if project configuration differs; inspect the actual artifact.

If `javax.servlet-api` is packaged inside `WEB-INF/lib/`, do not conclude that deleting the JAR is enough. Investigate which dependency pulled it in, and which application class or framework still requires the old namespace.

### 16.1. Inspecting bytecode signature when needed

Example:

```bash
javap -classpath target/classes \
  com.example.web.RequestIdFilter
```

Conceptual output:

```text
public final class com.example.web.RequestIdFilter
    implements jakarta.servlet.Filter {
  ...
}
```

If the output still shows `javax.servlet.Filter`, you may be inspecting an old artifact or old source still being compiled. Run a clean build, check commit/hash, and verify artifact paths.

`javap` shows the bytecode signature yet does not guarantee the right generation of container is deployed. Both factors must be verified separately.

## 17. Deploying on an Appropriate Tomcat

For the target example, use **Tomcat 10.1.x** with a Java runtime meeting requirements and a properly maintained/security-patched version. Note that `10.1.x` denotes the container branch; pick a specific currently supported patch release rather than merely writing "Tomcat 10".

A manual procedure:
1. Start Tomcat 10.1 with the chosen JDK 17.
2. Copy `request-id-demo-1.0.0.war` into Tomcat's deploy directory per the deployment environment.
3. Ensure annotation scanning is enabled within the webapp scope.
4. Verify the WAR deploys successfully without `ClassNotFoundException`/`NoClassDefFoundError`.
5. Call the `/request-id-demo/api/ping` endpoint on the configured port.

Example:

```bash
curl -i http://localhost:8080/request-id-demo/api/ping
```

Illustrative response:

```text
HTTP/1.1 200
Content-Type: text/plain;charset=UTF-8
X-Request-ID: 1e57197c-ef33-41c1-91b3-0c4c3a141800

pong; requestId=1e57197c-ef33-41c1-91b3-0c4c3a141800
```

The UUID value is an example. HTTP header names are case-insensitive. If the context path in Tomcat differs from the WAR name, adjust the URL; do not hardcode `/request-id-demo` in the filter source.

### 17.1. Checking the filter does not accidentally apply out of scope

Try a path outside `/api/*`, for example:

```bash
curl -i http://localhost:8080/request-id-demo/not-api
```

In the minimal WAR, this endpoint may return HTTP 404. `RequestIdFilter` must not be invoked merely because a request arrived at the same webapp. However, **other** filters or reverse proxies might still add a request ID header, so merely seeing the header in a production environment does not prove this specific filter ran.

In real integration tests, use a controlled filter invocation counter or fixture endpoint to verify mapping clearly; do not infer from a single header if multiple sources add that same header.

## 18. How Does WAR Deployment Differ with Spring Boot?

If a project uses Spring Boot 3.x on the Servlet stack, Spring Framework 6 and Jakarta Servlet APIs already belong to the same ecosystem. However, configuration differs from a plain WAR:

- There may be an embedded Tomcat or external Servlet container.
- Filter registration may occur via `FilterRegistrationBean`, `@Component`, or Servlet annotation scanning depending on configuration.
- Spring Security has its own `SecurityFilterChain`; custom servlet filters must be registered for the right purpose and order.
- A filter bean registered by both container auto-registration and the Security chain may run twice.

Minimal Spring configuration example (only illustrative when using Servlet-based Spring Boot):

```java
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class FilterConfig {

    @Bean
    FilterRegistrationBean<RequestIdFilter> requestIdRegistration() {
        FilterRegistrationBean<RequestIdFilter> registration =
                new FilterRegistrationBean<>();

        registration.setFilter(new RequestIdFilter());
        registration.addUrlPatterns("/api/*");
        registration.setName("requestIdFilter");
        return registration;
    }
}
```

If using this registration approach, **do not simultaneously keep an equivalent automatic registration via `@WebFilter`** in an environment with annotation scanning unless you thoroughly understand how the framework/container coordinates and have verified no duplicate execution. With modern Spring Boot, check the Boot/Spring version to use the exact package and configuration API.

In the main lesson, we use a plain WAR with `@WebFilter`. This Spring snippet only helps identify how to migrate the same component when the target is a different framework; **do not apply it simultaneously to the sample WAR project**.

## 19. What Happens When the Runtime Uses Tomcat 9?

A WAR with `RequestIdFilter implements jakarta.servlet.Filter` deployed onto Tomcat 9, which uses `javax.servlet.Filter`, **is incompatible as expected**.

Possible outcomes:
- The container does not recognize the class as a valid Servlet Filter.
- Error loading `jakarta.servlet.Filter` or its corresponding annotation class.
- `NoClassDefFoundError: jakarta/servlet/Filter`.
- The class is present thanks to an added API JAR, yet is not treated by Tomcat 9 as a filter of the right type.
- Deployment fails or the filter is skipped, breaking the contract even if other endpoints still return responses.

Do not fix this by placing both `javax.servlet-api` and `jakarta.servlet-api` into `WEB-INF/lib`. Doing so **does not convert** the type identity of the interfaces and can introduce additional loader conflicts.

A runtime boundary usually must be upgraded **together as a group**: Servlet container, Spring/Jakarta framework integration, filters/listeners/servlets, and API dependency. That is the mandatory part for a small code change to actually run properly.

## 20. Common Errors During Half-Way Namespace Migration

| Symptom | Possible cause | Remediation |
|---|---|---|
| `package jakarta.servlet does not exist` | Missing Jakarta API on compile classpath. | Declare proper Jakarta Servlet API version/scope. |
| `RequestIdFilter is not abstract and does not override ...` | Interface and method signatures come from two different namespaces. | Change all Servlet type imports/signatures. |
| `NoClassDefFoundError: jakarta/servlet/Filter` | Runtime container/JAR lacks Jakarta API. | Choose the corresponding target Servlet container. |
| `NoClassDefFoundError: javax/servlet/Filter` | Old library still links against javax API. | Upgrade/replace library, do not merely add Jakarta JAR. |
| `ClassCastException` between javax/jakarta Filter | The two interfaces are distinct types. | Recompile/migrate component or isolate boundary. |
| Filter does not run while endpoint returns 200 | Wrong annotation/config registration, metadata scanning disabled. | Check filter mapping, registration, and container logs. |
| Filter runs twice | Two registration mechanisms, or multiple filter instances. | Keep only one intentional registration path. |
| Endpoints outside `/api/*` also have header | Another filter/proxy or broad mapping. | Trace header source, check mappings/order. |
| POST/async/error behave differently | Dispatcher types/async support not preserved. | Preserve original config and test dispatch paths. |
| Passes in test but fails on server | Test classpath differs from runtime/container. | Deploy WAR onto actual target container. |
| `javax.sql.DataSource` changed to `jakarta.sql` | Out-of-scope bulk replace. | Keep Java SE import unchanged. |

Note that `NoClassDefFoundError` and `ClassNotFoundException` can be **symptoms** of mixing Servlet generations or wrong packages, not proof that random JARs should be added.

## 21. Before/After Test Matrix Must Reflect the Contract

| Test | Before (Tomcat 9 + javax) | After (Tomcat 10.1 + jakarta) |
|---|---|---|
| `GET /api/ping` | HTTP 200 | HTTP 200 |
| `X-Request-ID` | Contains UUID | Contains UUID |
| Request attribute | Matches header | Matches header |
| Chain execution | Exactly once | Exactly once |
| `/not-api` | Filter not applied | Filter not applied |
| Downstream `ServletException` | Not swallowed | Not swallowed |
| Downstream `IOException` | Not swallowed | Not swallowed |
| Dispatcher REQUEST | Matches | Matches |
| Dispatcher ERROR/ASYNC | Per legacy config | Not accidentally changed |
| JVM/container startup | No linkage errors | No linkage errors |
| WAR API dependency | Container provides right javax API | Container provides right Jakarta API |
| Java SE `javax.*` | Unchanged | Unchanged |

In practice, not every old test has to run verbatim against both containers if test dependencies differ. What must be preserved is the **contract output**, not trying to mix Java types of both generations in the same test classpath.

## 22. Migration Order When the Project Has Many Web Libraries

Migrating a standalone filter is the simplest situation. A real WAR may depend on:
- Servlet container.
- Spring MVC/Security.
- REST/JAX-RS implementation.
- CDI/Bean Validation.
- Logging/metrics filters.
- CORS/authentication filters.
- Third-party agents/interceptors.
- Internally written libraries implementing `javax.servlet.Filter`.

If a filter is upgraded to Jakarta while keeping an old framework using `javax.servlet.*`, build or runtime may fail. In that case, "proper scope" **does not mean forcing the whole system to fix every import in one commit**, rather identifying the tightly coupled group that must transition together at the runtime boundary.

Strategy:

```text
Inventory API/container dependencies
              |
              v
Choose compatible target runtime group
              |
              v
Migrate small component in isolated branch
              |
              v
Test with target API + target container
              |
              v
Migrate surrounding tightly coupled components
              |
              v
Deploy group at coherent boundary
```

Business modules that do not use Servlet types can be left untouched. In a modularized monolith, the domain layer does not need to import Jakarta merely because the web layer is upgraded.
## 23. If the Application Uses web.xml Instead of Annotations

Some legacy WARs register filters only via `WEB-INF/web.xml`. Do not delete an existing registration mechanism to use `@WebFilter` just for fewer lines of code, especially when filter order involves security.

Target Jakarta Servlet 6.0 declaration sample:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<web-app
    xmlns="https://jakarta.ee/xml/ns/jakartaee"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
        https://jakarta.ee/xml/ns/jakartaee
        https://jakarta.ee/xml/ns/jakartaee/web-app_6_0.xsd"
    version="6.0">

    <filter>
        <filter-name>requestIdFilter</filter-name>
        <filter-class>
            com.example.web.RequestIdFilter
        </filter-class>
    </filter>

    <filter-mapping>
        <filter-name>requestIdFilter</filter-name>
        <url-pattern>/api/*</url-pattern>
        <dispatcher>REQUEST</dispatcher>
    </filter-mapping>
</web-app>
```

If using `web.xml`:
- Check XML namespace/schema version compatibility with the Servlet container.
- Specify the right `filter-class` and mapping.
- Keep `dispatcher`/async-supported/initialization parameters per original requirements.
- **Remove `@WebFilter` from the class** in this variant to avoid creating two registration paths with the same target.
- Verify `filter-mapping` ordering in the descriptor per actual application configuration.
- Deploy the WAR to the target container and execute integration tests.

With the sample WAR project in previous sections, **choose one approach**: annotation *or* descriptor. Using annotations is sufficient; there is no need to add the file above for the sample to run.

## 24. Gradle Is an Alternative to Maven, Not Added Alongside

If a real project uses Gradle, `build.gradle.kts` can be chosen instead of `pom.xml`. A separate example for the same WAR and Jakarta Servlet:

```kotlin
plugins {
    java
    war
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    compileOnly("jakarta.servlet:jakarta.servlet-api:6.0.0")

    testImplementation("jakarta.servlet:jakarta.servlet-api:6.0.0")
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
    testImplementation("org.mockito:mockito-core:5.15.2")

    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
}
```

In this example:
- `compileOnly` allows compilation without putting the Servlet API into the runtime WAR as an application library.
- `testImplementation` for the Jakarta Servlet API ensures mock-based unit tests have the interfaces at test runtime.
- The target container supplies the Servlet API when deploying the WAR.
- The `war` plugin creates an artifact suitable for an external servlet container.
- Java 17 toolchain must exist/be able to be provisioned by Gradle per environment configuration.

The Gradle version must support the target JDK/toolchain. This is an **alternative option**; there is no need to keep both Maven and Gradle in the same workshop. Run `./gradlew clean test war` once the Gradle project is configured; do not assume this command works for every multi-module project.

## 25. Testing Servlet API with the Right Scope

Question: if the WAR does not contain `jakarta.servlet-api`, why do unit tests still run?

Answer:
- Maven's `provided` dependency is present during compile and test, yet is not placed on the WAR's runtime classpath due to the container's role.
- Gradle separates `compileOnly` and `testImplementation` as in the example to provide the API to tests.
- Tomcat 10.1 provides the Servlet implementation/API in the deployment runtime.

A diagram:

```text
Developer compile/tests
      |
      +--> RequestIdFilter.class
      +--> jakarta.servlet-api (compile/test only)
      +--> JUnit + Mockito (test only)
      |
      v
WAR artifact
      |
      +--> WEB-INF/classes/RequestIdFilter.class
      +--> WEB-INF/classes/PingServlet.class
      |
      v
Tomcat 10.1 runtime
      |
      +--> Jakarta Servlet API/implementation
      +--> WAR classes + application dependencies
```

The mistake of "trying to add the Servlet API JAR to the WAR to see if errors disappear" can hide choosing the wrong container or create classloader fragmentation. Before changing scope, identify the deployment type: standalone container, embedded server, or application server; each type has a different dependency contract.

## 26. Auditing Source with Clear Boundaries

In real migration, instead of running across the whole repository:

```text
Find:    javax.
Replace: jakarta.
```

set an **allowlist** of namespaces belonging to the component:

```text
javax.servlet.Filter
javax.servlet.FilterChain
javax.servlet.ServletRequest
javax.servlet.ServletResponse
javax.servlet.ServletException
javax.servlet.DispatcherType
javax.servlet.annotation.WebFilter
javax.servlet.http.HttpServletResponse
```

Then edit only the exact source files and related metadata. Leave other Java SE classes unchanged.

Compilation, IDE find-usages, and bytecode inspection can be used to detect remaining `javax.servlet` references in built artifacts. However:
- Source search misses binary-only dependencies.
- A third-party JAR may contain `javax.servlet` references even when application code is clean.
- Generated code may regenerate legacy imports after build.
- Service metadata, web descriptors, or JSP/taglibs may still use the old types.

Therefore, inventory areas actually using the Servlet API, yet **do not convert unrelated modules merely because they have `javax.*` in package names**.

## 27. Inspecting the Dependency Graph When Errors Arise

With Maven:

```bash
mvn dependency:tree
mvn help:effective-pom
```

With Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency servlet \
  --configuration compileClasspath
```

Check:
1. Which API family is selected: `javax.servlet-api` or `jakarta.servlet-api`?
2. Does the API version match the container?
3. Does a third-party library/plugin require the old namespace?
4. Are there duplicate Servlet API JARs in the WAR or on the server classpath?
5. Is a dependency marked `provided` yet not actually provided by the runtime?
6. Is an old artifact shaded/relocated or isolated by a classloader?

Error example:

```text
java.lang.NoClassDefFoundError:
    jakarta/servlet/Filter
```

may mean the container does not provide the new API. Another example:

```text
java.lang.NoClassDefFoundError:
    javax/servlet/Filter
```

in a Jakarta runtime may be a third-party filter library still compiled for Java EE. Compile errors can also be conflicting interfaces/method signatures if imports are mixed.

Read the **entire Caused by chain** instead of just adding the first JAR the message suggests.

## 28. Using jdeps in Its Proper Role

On JDK 17, `jdeps` can help locate class-level references in bytecode:

```bash
jdeps --ignore-missing-deps \
  --verbose:class \
  target/classes
```

For a WAR, `WEB-INF/classes` and JARs may need separate analysis depending on how the tool accepts paths. `jdeps` analyzes **static dependencies** and cannot guarantee finding every class loaded via reflection, ServiceLoader, or XML metadata.

When reading output, the goal is to determine:
- Which classes still depend on `javax.servlet.*`.
- Which classes already depend on `jakarta.servlet.*`.
- Whether other libraries require a different container API.
- Whether any dependency is missing or the module graph is incomplete.

Note that `--ignore-missing-deps` can suppress missing-dependency error reports to allow inspecting remaining references; **no error from this command** must not be treated as proof that every class dependency is present. Also use runtime integration tests.

## 29. When a Third-Party Library Has No Jakarta Version Yet

Suppose a legacy monitoring filter is distributed as a binary JAR:

```java
public final class LegacyMonitorFilter
        implements javax.servlet.Filter {
    // ...
}
```

The new application uses `jakarta.servlet.Filter`. There are three main options:

1. **Upgrade the library** to an official Jakarta version from the vendor.
2. **Replace the library** with a Jakarta-compatible component with an equivalent contract.
3. **Isolate** the legacy feature in an old application/runtime and communicate with the new application across a neutral boundary such as HTTP/queue, if business requirements allow.

Some bytecode/archive migration tools can rewrite namespace references in binaries, yet support level, licensing, runtime integration, resources/metadata, and full testing must be evaluated. **Do not assume "transforming" every old library is safe or always succeeds.**

If the application must maintain both generations during a transition phase:
- You can run **two separate applications**, one on Tomcat 9 and one on Tomcat 10.1.
- Use a neutral API/protocol between them.
- Keep DTOs/shared domain free from exposing `javax` or `jakarta` Servlet types across the boundary.
- Use contract tests for HTTP/events.
- End the legacy support phase once evidence is established.

Do not attempt to deploy the same Servlet Filter binary as an instance compatible with both interfaces via casting.

## 30. Bounding Scope with Interfaces at the Domain Layer

To avoid "leaking" Servlet types down into the domain layer, separate contracts:

```text
                 Web Adapter (Jakarta Servlet)
                           |
                           v
               Application Service Interface
                           |
                           v
                        Domain
```

Example of a domain/app service using Java SE types, needing no change when the web layer upgrades:

```java
package com.example.domain;

public interface RequestAudit {
    void record(String requestId, String path);
}
```

A Jakarta adapter can extract data from `HttpServletRequest` and call `record(...)`. The legacy Java EE version can also invoke this same interface from a `javax.servlet.*` adapter in a **separate** deployment.

Advantages:
- Domain contract stays intact.
- Domain tests do not require container APIs.
- Migrating the Servlet adapter is small and isolated.
- Reduces the chance that a namespace change drags in many modules.
- Rollback can preserve business logic while swapping the adapter/runtime.

**This is a design strategy**, and does not mean rewriting the domain layer for the `RequestIdFilter` workshop. For a simple filter, keeping UUID generation logic in the filter is also reasonable.

## 31. Security Implications of a Filter During Migration

The filter in this lesson only generates a request ID and does not authenticate users. Yet in real systems, the filter chain may contain authentication, authorization, CSRF, CORS, logging, request wrapping, and exception handling.

When changing the Servlet namespace, check:
- Filter order relative to security filters.
- Which URLs are bypassed/matched.
- Dispatcher types REQUEST/FORWARD/ERROR/ASYNC.
- Async context propagation and thread-local cleanup.
- Whether any filter is registered twice.
- Whether response commitment behavior changed.
- Whether exceptions are swallowed before Spring Security or the container handles them.
- Whether sensitive information is logged or placed into headers.

**`X-Request-ID` is not proof of authentication.** A request ID is log correlation data and should not be used for authorization or to trust that a client providing a matching ID is authorized. If accepting an inbound X-Request-ID from a proxy or client, enforce policies on length, format, trusted source, and log-injection protection; this lesson **generates its own UUID** to keep the example safe and easy to test.

## 32. Deployment Metadata Changes Can Expand Scope Unintentionally

Changes to review:
- Descriptor namespace/schema version.
- `@WebFilter` vs `web.xml`.
- URL pattern `/api/*` vs `/*`.
- Filter name and mapping order.
- `asyncSupported` and dispatcher types.
- Static resource handling.
- Error/forward mapping.
- Context path.
- Multiple servlet registrations.
- Reverse proxy/ingress path rewrite.

An example mistake:

```java
@WebFilter("/*")
```

when previously the filter only applied to `/api/*`, can alter behavior for login, static content, file upload, or error pages. Do not broaden mappings "just to be sure" during migration.

Another mistake is omitting dispatcher types from the old contract. In the main lesson, we use:

```java
dispatcherTypes = { DispatcherType.REQUEST }
```

If the real system previously handled ASYNC or ERROR as well, the exact committed behavior must be migrated and tested separately.

## 33. Canary and Rollback at the Runtime Group Level

A practical point: you cannot "roll back a single Filter class" if the new WAR already uses Jakarta Servlet and the runtime moved from Tomcat 9 to 10.1.

Deployment can proceed by group:

```text
        Load Balancer / Gateway
                |
       +--------+--------+
       |                 |
       v                 v
Legacy WAR +         Jakarta WAR +
Tomcat 9             Tomcat 10.1
       |                 |
       +--------+--------+
                |
            Shared DB/API
```

During the canary phase, the two runtimes run separately. Conditions:
- API returns identical contract behavior on equivalent endpoints.
- Data/DB/messaging are mutually compatible across both sides.
- Session/cookies/authentication flow is designed for rollout.
- Load balancer routing and header forwarding are accurate.
- Metrics distinguish legacy/new versions.
- There is a way to shift traffic back to legacy **if data and security policy allow**.

If the migration also alters the database schema, rollback is not merely switching routes back to Tomcat 9. With a stateless component like a request ID filter, data risk scope is smaller, yet the runtime/framework group still must align when rolling back.

Do not keep an old Java EE runtime long-term if it is out of support/security patches; the canary window must have an end date and a decommissioning roadmap.

## 34. Measurable Acceptance Criteria

| Gate | Condition | Evidence |
|---|---|---|
| Scope | Only necessary Servlet-facing imports changed, Java SE `javax.*` intact. | Diff, dependency inventory. |
| Build | Compiles with Java 17, Jakarta Servlet 6 API. | Maven/Gradle build output. |
| Unit | Header/attribute/chain/exception tests pass. | JUnit report. |
| Artifact | WAR contains target classes, no wrong Servlet API bundled. | `jar tf`, dependency report. |
| Runtime | Deploys on Tomcat 10.1. | Container logs, deploy status. |
| URL mapping | `/api/*` matches, out-of-scope paths are not processed by filter. | HTTP integration tests. |
| No regressions | Same response contract and error propagation. | Before/after contract matrix. |
| Namespace | No `javax.servlet` references in migrated component. | Source/bytecode inspection. |
| Container family | No Jakarta WAR mistakenly deployed to javax container. | Deployment config and inventory. |
| Security | Filter order/security boundaries not unintentionally changed. | Security regression tests if applicable. |
| Operations | Rollback/canary route defined. | Release runbook. |

The results here are **sample acceptance criteria for learners to execute**, not a report already run on a real project.

## 35. Advanced Exercise 1: Adding Dispatcher Types Cases

Requirements:
- Keep `RequestIdFilter` running only for `DispatcherType.REQUEST` as in the example.
- Create an endpoint that throws an error and let the container dispatch to an error page.
- Verify the filter does not automatically re-run due to `ERROR` dispatch if the mapping does not select that type.
- If the project wants the filter on `ERROR`, intentionally update the mapping and add a test for trace ID across dispatches.

Questions:
1. Should a different request ID automatically be set during an error dispatch?
2. Can an already-committed header be modified afterward?
3. If async is used, is the request attribute propagated as the framework expects?

Hint: for tracing, the same correlation ID is needed across processing; however, policy depends on request lifecycle and filter registration. Test against a real container instead of guessing from annotations.

## 36. Advanced Exercise 2: Identifying javax Packages That Must Not Be Changed

Given the list:

```text
javax.servlet.http.HttpServletRequest
javax.sql.DataSource
javax.crypto.Mac
javax.validation.constraints.NotNull
javax.net.ssl.HttpsURLConnection
javax.persistence.Entity
javax.xml.parsers.SAXParserFactory
javax.naming.Context
javax.annotation.PostConstruct
javax.tools.ToolProvider
```

Divide into three groups:

- **Group A:** migrated during Servlet API migration.
- **Group B:** consider migrating only when simultaneously upgrading other Jakarta EE groups such as Persistence/Validation/Annotations.
- **Group C:** keep unchanged because they belong to Java SE.

Suggested answer:

| Name | Group |
|---|---|
| `javax.servlet.http.HttpServletRequest` | A → `jakarta.servlet.http.HttpServletRequest`. |
| `javax.sql.DataSource` | C. |
| `javax.crypto.Mac` | C. |
| `javax.validation.constraints.NotNull` | B → corresponding Jakarta Validation when upgrading the validation stack. |
| `javax.net.ssl.HttpsURLConnection` | C. |
| `javax.persistence.Entity` | B → Jakarta Persistence when upgrading the JPA stack. |
| `javax.xml.parsers.SAXParserFactory` | C. |
| `javax.naming.Context` | C. |
| `javax.annotation.PostConstruct` | B → Jakarta Annotations when upgrading related API/frameworks. |
| `javax.tools.ToolProvider` | C. |

This exercise prevents a very common error: treating the `javax` prefix as proof a class must be changed, instead of identifying **the API specification the class belongs to**.
## 37. Advanced Exercise 3: Do Not Turn Tracing Into a Vulnerability

Suppose a new requirement is to preserve `X-Request-ID` from the API gateway to correlate logs across multiple services. A naive approach:

```java
String id = httpRequest.getHeader("X-Request-ID");
response.setHeader("X-Request-ID", id);
```

carries risks:
- The header may be absent or empty.
- An external client can spoof another request's ID.
- Overly long values or unwanted characters cause log/metric issues.
- Relying on the request ID as an access token creates an authorization vulnerability.
- When a proxy forwards multiple copies with the same name, which value gets picked is ambiguous.

Requirements for the advanced exercise:
1. Only trust inbound IDs if the request arrives from a **trusted gateway** per a designed boundary.
2. Validate format and enforce length limits.
3. For invalid IDs, generate a new UUID.
4. Do not place credentials, session IDs, or raw PII into the correlation header.
5. Keep the ID consistent across request attribute, response header, and log context.
6. If using MDC/thread-local, clean up in `finally` and test async/error dispatches.

This is a **separate business/observability change** and should not be mixed into the `javax` → `jakarta` migration commit if the current goal is solely preserving the contract. The risk-reducing approach is to complete the namespace migration first, then open a separate change request for the new header logic.

## 38. A Practical Low-Risk PR Sequence

In a large project, work can be split into pull requests along boundaries:

### PR A — Prepare testability

- Capture baseline behavior of the current filter.
- Record URL mappings, ordering, and dispatcher types.
- Create contract tests or fixtures that can run on the old environment.
- Inventory `javax.servlet` dependencies and Java SE imports to keep.

This PR does not need to change the runtime immediately.

### PR B — Synchronize runtime family

- Lock down target Java runtime, Servlet API, Tomcat/Spring versions.
- Upgrade related frameworks/dependencies in compatible groups.
- Prepare pipeline or new deployment supporting Jakarta.
- Ensure other web components in the same WAR have a synchronized upgrade plan.

This may be a larger PR than the filter itself, because Servlet-facing interfaces belong to a **unified runtime boundary**.

### PR C — Migrate component and tests

- Switch `RequestIdFilter` to Jakarta imports.
- Preserve method behavior and URL mapping.
- Migrate test mocks to Jakarta interfaces.
- Use exact API dependency scopes.
- Build/package WAR and test on Tomcat 10.1.

### PR D — Rollout and cleanup

- Canary traffic through the new runtime.
- Compare headers, errors, access logs, and latency.
- Verify no unexpected `javax.servlet` links remain in the migrated WAR.
- Decommission legacy deployment after the rollback window.
- Remove temporary bridges/intentional dependency overrides.
- Update runbooks, compatibility matrices, alerting, and documentation.

The breakdown may vary depending on the monolith, yet avoid **mixing namespace edits with large business refactors** in the same hard-to-verify commit.

## 39. Signs That "Proper Scope" Failed

A code review should demand explanation when seeing:
- Hundreds of `javax.sql`, `javax.crypto` imports replaced without reason.
- Business domain starts accepting `jakarta.servlet.http.HttpServletRequest` as a parameter.
- A `Filter` switches namespaces while Tomcat remains 9.x.
- New WAR bundles both `javax.servlet-api` and `jakarta.servlet-api`.
- Filter mapping changes from `/api/*` to `/*` without a contract change.
- The author simultaneously changes authentication/tracing logic without tests.
- Unit tests mock Jakarta while production still runs a Java EE container.
- A bytecode transformer is applied across all JARs without scope or exclusion lists.
- A transitive dependency pulls in an incompatible web stack.
- Generated sources still import legacy Servlet types even though main sources were updated.

Do not fix outward symptoms by stuffing in extra libraries or suppressing exceptions. Locate which part of **class identity/runtime contract** is out of sync.

## 40. Summary Step-by-Step Procedure

1. **Select component:** `RequestIdFilter` and its direct Servlet types.
2. **Mark unchanged:** `java.util.UUID`, `java.io.IOException`, other Java SE `javax.*`.
3. **Lock target:** JDK 17, Jakarta Servlet 6.0, Tomcat 10.1 for the test WAR.
4. **Record contract:** `/api/*` path, header, request attribute, chain/error behavior.
5. **Create baseline:** inspect current javax behavior on the older container if available.
6. **Update all imports and signatures:** all Servlet types under Jakarta.
7. **Update dependency:** use Jakarta Servlet API `provided` for the WAR.
8. **Migrate tests:** Mock Jakarta ServletRequest/Response/FilterChain.
9. **Build and inspect:** confirm the class implements `jakarta.servlet.Filter` and the WAR does not bundle the wrong API.
10. **Deploy to the right container:** Tomcat 10.1, not Tomcat 9.
11. **Integration test:** `GET /api/ping`, header/attribute, out-of-scope mapping, exception flow.
12. **Check related libraries:** no unresolved `javax.servlet` references in the same upgraded runtime group.
13. **Canary and rollback:** by runtime group, without assuming a single class can be swapped on an old server.
14. **Clean up temporary config:** after passing gates and ending the support/rollback window.
15. **Record evidence:** code diff, versions, test reports, WAR checksum, container runtime, and reviewer.

**Sequencing note:** if the runtime cannot transition yet, only prepare code/adapters on another branch; do not deploy Jakarta binaries onto a WAR/container still requiring javax.

## 41. Self-Check Questions

**Question 1:** Why is `javax.sql.DataSource` not changed to `jakarta.sql.DataSource` in this lab?

Because `javax.sql` belongs to Java SE, not a Servlet/Jakarta EE API undergoing namespace migration within this scope.

**Question 2:** Can `RequestIdFilter implements jakarta.servlet.Filter` be deployed on Tomcat 9 if `jakarta.servlet-api.jar` is added to the WAR?

That cannot be considered a proper solution. Tomcat 9 uses the `javax.servlet.Filter` contract; a Jakarta class does not become a Javax Filter by adding a JAR. You must use a Jakarta-compatible container/framework or keep the Javax version in the old deployment.

**Question 3:** Why is `provided` scope appropriate for `jakarta.servlet-api` in an external Tomcat WAR?

Because the API is needed for compile/test, while the Servlet API/implementation is provided by Tomcat at deployment. The WAR should not package another API version contradicting the container's contract.

**Question 4:** Do green unit tests prove `@WebFilter` is discovered by the container?

Not yet. Unit tests only invoke the Java method directly; an integration test deploying the WAR on the target container and sending real HTTP requests is required.

**Question 5:** If intending to use `web.xml`, should `@WebFilter` be kept with the same registration logic?

Do not arbitrarily leave two registration paths for the same filter. Choose one clear mechanism, preserve mapping/order/dispatch behavior, and test against the real container.

**Question 6:** When replacing Jakarta imports, does `java.util.UUID` need to change to a new package?

No. `java.util.UUID` belongs to Java SE and is completely outside the Java EE namespace transition.

**Question 7:** Why should the request ID generation algorithm not be changed simultaneously in the same PR?

Because it would be difficult to distinguish namespace/runtime failures from logic-change failures, and it destabilizes the baseline contract.

**Question 8:** Does a dependency using `javax.servlet.Filter` packaged alongside a Jakarta filter become compatible automatically?

No. The two interfaces have different type identities; the library needs a Jakarta-compatible version or a migration/adapter designed along a compatible boundary.

## 42. Checklist Before Considering the Lab Complete

- [ ] Identified the component to migrate and allowed source modification scope.
- [ ] Listed Java SE `javax.*` packages that must **not** be changed.
- [ ] Selected the right Servlet API version and compatible container.
- [ ] Verified Java version/toolchain used for build.
- [ ] `RequestIdFilter` implements `jakarta.servlet.Filter`.
- [ ] `FilterChain`, `ServletException`, `ServletRequest`, `ServletResponse`, and annotations belong to the Jakarta namespace.
- [ ] `java.io.IOException` and `java.util.UUID` kept unchanged.
- [ ] `/api/*` and dispatcher type were not unintentionally altered.
- [ ] Request attribute and header hold the same request ID.
- [ ] Filter invokes `chain.doFilter` exactly once.
- [ ] `ServletException` and `IOException` propagate properly for downstream error handling.
- [ ] Unit tests cover both happy paths and error paths.
- [ ] WAR build output contains the expected implementation class.
- [ ] Servlet API dependency is not packaged with the wrong scope.
- [ ] No unplanned `javax.servlet.*` references remain in the upgraded runtime group.
- [ ] WAR deployed on Tomcat 10.1 or a compatible Jakarta Servlet 6 container.
- [ ] HTTP integration test verifies actual route/filter mapping.
- [ ] No duplicate filter registration across annotations, XML, and frameworks.
- [ ] Security filter ordering/authorization was not altered out of scope.
- [ ] Confirmed tightly coupled dependencies are also Jakarta-compatible.
- [ ] Canary/rollback plan exists at the runtime group level.
- [ ] Diff/test evidence, artifact version, and container runtime recorded.

## 43. References

- [Jakarta Servlet 6.0 Specification](https://jakarta.ee/specifications/servlet/6.0/): specification of the Servlet API, lifecycle, filters, and deployment.
- [Apache Tomcat — Which Version?](https://tomcat.apache.org/whichversion.html): comparison table of Tomcat, Jakarta Servlet, and Java baseline.
- [Apache Tomcat — Migration Guide Tomcat 10](https://tomcat.apache.org/migration-10.html): Java EE `javax.*` → Jakarta EE `jakarta.*` changes when upgrading Tomcat 9 → 10.
- [Apache Tomcat — Migration Guide Tomcat 10.1](https://tomcat.apache.org/migration-10.1.html): changes in Tomcat 10.1/Jakarta Servlet 6.0.
- [Apache Tomcat — Jakarta EE Migration Tool](https://tomcat.apache.org/download-migration.cgi): tool for converting certain legacy applications/binary archives, with scope and limitations needing evaluation.
- [Jakarta EE Specifications](https://jakarta.ee/specifications/): distinguishing Servlet, Persistence, Validation, Annotations, and other Jakarta APIs.
- [Maven Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): compile/runtime/provided/test scopes.
- [Maven WAR Plugin](https://maven.apache.org/plugins/maven-war-plugin/): packaging web applications.
- [Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/): running unit tests.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): building tests.
- [Mockito Documentation](https://site.mockito.org/): mocking ServletRequest/ServletResponse/FilterChain.
- [Gradle WAR Plugin](https://docs.gradle.org/current/userguide/war_plugin.html): packaging WARs in Gradle.
- [Spring Boot Reference](https://docs.spring.io/spring-boot/reference/): Servlet container integration and filter registration for Spring Boot projects.
- [Spring Security Reference](https://docs.spring.io/spring-security/reference/): configuring the filter chain and security boundary if the filter resides in a Spring Security application.

## Conclusion

Migrating a component from **`javax.servlet.*` to `jakarta.servlet.*` with proper scope** is not a repository-wide string replacement operation. With `RequestIdFilter`, you must first identify the Servlet API owner, keep Java SE APIs and the business contract intact, update all relevant Java types/annotations, and then align the Maven/Gradle dependency and Servlet container to avoid mixing two generations of class identity.

The lab is technically complete when unit tests preserve the header, request attribute, and chain behavior; the WAR contains the Jakarta class in the right scope; Tomcat 10.1 actually picks up the filter and handles requests; and the team has evidence of zero impact on Java SE `javax.*` packages or out-of-scope modules. The broader lesson is **limiting code changes without overlooking the runtime boundary**: even a small modification still requires a consistent dependency/container stack. That is how Jakarta upgrades are testable, explainable, and rollback-ready in Java compatibility migration programs.