
# Distinguishing APIs from Their Implementation Libraries

During a Java upgrade, a common dependency error is **having an API to compile against without an implementation library at runtime**, or conversely: packaging multiple implementations of the same API without knowing which implementation gets selected. Another case occurs when an API and implementation share similar names yet belong to incompatible generations, such as an API in the `javax.*` namespace paired with an implementation in the `jakarta.*` namespace.

This confusion can cause an application to:

- Compile successfully yet hit `ClassNotFoundException`, `NoClassDefFoundError`, or a provider-not-found error at startup.
- Encounter `NoSuchMethodError` or `AbstractMethodError` when the API and implementation are not binary compatible.
- Discover multiple providers, making the outcome depend on classpath, module order, or configuration.
- Redundantly package a container implementation, causing class loader conflicts when deploying a WAR.
- Run on a developer machine yet fail inside a Docker image, server, or newer JDK.
- Become implicitly coupled to a single implementation, making library replacement very difficult.

This lesson belongs to **Java Advance Compatibility Migration**, **Dependency Management** section, focusing on identifying and managing the boundary between **APIs (contracts)** and **implementation/provider libraries** across Java, Maven, Gradle, JPMS, and real deployment environments.

## 1. API and Implementation Have Two Distinct Roles

**An API** describes the types, contracts, and extension points on which application code relies. It may contain:

- Interfaces and abstract classes.
- Annotations, enums, and public data types.
- Method signatures, exception types, and constants.
- Factories, bootstrap APIs, or registries to locate an implementation.
- Service Provider Interfaces (SPIs), i.e., contracts that implementations must satisfy.
- Metadata for build tools or runtime environments.

**An implementation library** provides concrete behavior for that contract, such as:

- Actually connecting to a database.
- Rendering servlet requests/responses in a web container.
- Writing logs through a backend.
- Executing validation on an object.
- Managing JPA's persistence context, SQL, and transactions.
- Serializing objects using a JAXB engine.

A minimal Java example:

~~~java
package com.example.api;

public interface MessageSender {
    void send(String destination, String message);
}
~~~

Implementation:

~~~java
package com.example.impl;

import com.example.api.MessageSender;

public final class SmtpMessageSender implements MessageSender {
    @Override
    public void send(String destination, String message) {
        // Connect to SMTP, authenticate, and send data.
    }
}
~~~

A module consuming the API may only need to know `MessageSender`. At runtime, however, a concrete instance of `SmtpMessageSender` or an equivalent implementation must exist, supplied via dependency injection, a factory, or configuration.

### 1.1. Dependency Diagram

~~~mermaid
flowchart TD
    A["Application / Consumer"] --> B["API / Contract"]
    C["Implementation A"] --> B
    D["Implementation B"] --> B
    E["Runtime wiring / SPI / DI"] --> C
    E --> D
    A --> E
~~~

In practice, consumers may interact with a factory inside the API that connects to an implementation at runtime. What matters is **knowing who provides the contract, who provides the behavior, and who selects the provider**.

### 1.2. An API Artifact Does Not Necessarily Contain Only Interfaces

The name "API" does not mean the JAR contains only interfaces. It may include utility classes, default methods, factories, or basic implementations. Likewise, an "implementation" artifact may expose public types for configuration.

Distinguish based on **architectural role and release contract**, not solely by filenames like `*-api.jar` or `*-impl.jar`.

### 1.3. Java SE APIs Differ from Standalone Dependency APIs

Some APIs reside in the JDK, such as `java.sql` providing `Connection`, `DriverManager`, and `DataSource`. They do not require a separate Maven dependency when the JDK provides the corresponding module.

Other APIs are external dependencies outside the JDK, such as those in the Jakarta EE family. Some Java EE APIs formerly included in older JDKs were removed in JDK 11 as part of modularization. When migrating, correctly identify **which APIs belong to Java SE**, which must be declared externally, and which implementations the runtime or server supplies.

## 2. Dependency Scenarios to Distinguish

| Scenario | API present at compile time? | Implementation present at runtime? | Outcome |
|---|---|---|---|
| Matching contract, matching provider | Yes | Yes | Runs if versions/config are compatible |
| API only | Yes | No | Compilation usually succeeds; bootstrap or actual functionality fails |
| Implementation only | Maybe yes/no | Yes | Compilation may lack public API; depends on implementation packaging |
| Multiple providers | Yes | Multiple | May run, pick the wrong provider, or cause conflicts |
| API and provider from different generations | Yes | Yes, yet incompatible | Linkage/configuration/runtime errors |
| Container already supplies implementation, app bundles another | Yes | Duplicated or conflicting | Class loader, version, and service resolution may fail |

You cannot conclude "dependencies are complete" merely by seeing a JAR with the right name. Inspect **runtimeClasspath and packaged artifacts**, where loaders actually look for APIs and providers.

## 3. Common API — Implementation Pairs

The examples below illustrate **roles**. Exact versions and compatibility must be verified against each project's release documentation; do not infer that any similarly named artifacts can always be paired together.

| Need | API / Contract | Common Implementation or Runtime | Notes |
|---|---|---|---|
| Servlet | Jakarta Servlet API | Servlet container such as Tomcat, Jetty | Container typically provides API and engine when deploying a WAR |
| JPA | Jakarta Persistence API | Hibernate ORM, EclipseLink | Provider executes persistence/SQL |
| Bean Validation | Jakarta Validation API | Hibernate Validator | Provider executes constraint validation |
| CDI | Jakarta CDI API | Weld, OpenWebBeans | May be provided by the application server |
| JAXB | Jakarta XML Binding API | GlassFish JAXB runtime or compatible implementation | Namespace generation must match |
| Jakarta Mail | Jakarta Mail API | Suitable Jakarta Mail/Angus Mail implementation | Check provider and version |
| JAX-WS | Jakarta XML Web Services API | Metro or suitable runtime | Adding only the API is insufficient after JDK 11 |
| Logging facade | SLF4J API | Logback, appropriate SLF4J provider | Must match the SLF4J major line |
| JDBC | Java SE `java.sql` API | Database vendor's JDBC driver | Driver is usually discovered at runtime |
| JSON Processing (JSON-P) | Jakarta JSON Processing API | Suitable JSON-P provider | Distinct API from JSON-B |
| JSON Binding (JSON-B) | Jakarta JSON Binding API | Yasson or matching provider | May depend on a JSON-P implementation |
| Cryptography | JCA/JCE engine API in the JDK | Software security provider, HSM/PKCS#11 | Provider may come from the JDK or vendor |

This table **is not a dependency version list to copy into production**. Exact pairing also depends on Java baseline, framework, container, classpath/module path, and deployment configuration.

## 4. Example 1: Servlet API and Servlet Container

Suppose you write a servlet:

~~~java
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import java.io.IOException;

public class HealthServlet extends HttpServlet {
    @Override
    protected void doGet(
            HttpServletRequest request,
            HttpServletResponse response) throws IOException {
        response.setContentType("text/plain; charset=UTF-8");
        response.getWriter().write("OK");
    }
}
~~~

`HttpServlet`, `HttpServletRequest`, and `HttpServletResponse` belong to the **Servlet API**. Yet the API itself does not open an HTTP port, dispatch requests, manage the servlet lifecycle, or handle connectors. That is the job of the **Servlet container**.

### 4.1. Deploying a WAR to an External Container

When deploying a WAR into a compatible Tomcat/Jetty instance, the container provides both the Servlet API and its implementation. Therefore, the Servlet API dependency is commonly marked **provided** or **compileOnly** in build configuration to avoid bundling a duplicate/incompatible API copy in `WEB-INF/lib`.

Illustrative Maven example:

~~~xml
<dependency>
    <groupId>jakarta.servlet</groupId>
    <artifactId>jakarta.servlet-api</artifactId>
    <version>VERSION_MATCHING_CONTAINER</version>
    <scope>provided</scope>
</dependency>
~~~

`VERSION_MATCHING_CONTAINER` is merely a placeholder indicating the requirement to choose a compatible version, not a real version for Maven resolution.

If another implementation/container is mistakenly packaged into the WAR, a container may experience:

- Duplicate API classes across class loaders.
- Servlet API version mismatch with the container.
- `ClassCastException` even though class names match, because they come from different loaders.
- Linkage or service initialization errors.
- Conflicts with server-managed libraries.

### 4.2. Executable JAR with an Embedded Server

For an application using embedded Tomcat/Jetty, runtime dependencies differ: the application normally **packages the server implementation** so it can start up and accept HTTP requests on its own.

Do not mechanically set all servlet-related dependencies to `provided` in a standalone application. Ask:

1. Is the runtime an external container or an embedded container?
2. Who owns the servlet engine?
3. Which dependencies are packaged into the JAR/WAR?
4. Which Servlet API version does the engine support?
5. Is there class loader separation or a module path?

A configuration valid for a traditional WAR can be completely wrong when moving to an executable JAR.

### 4.3. javax.servlet and jakarta.servlet Are Not Equivalent

Older Servlet generations use the `javax.servlet.*` package; newer Jakarta APIs use `jakarta.servlet.*`. These are two **distinct type names at the bytecode level**.

You cannot expect an implementation for `jakarta.servlet.*` to automatically handle an application compiled against `javax.servlet.*` merely because both are called "Servlet API." During migration, align source/imports, API artifacts, implementation/container, and matching frameworks together.

## 5. Example 2: Jakarta Persistence API and JPA Provider

An entity can be declared using JPA annotations:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
public class Customer {
    @Id
    private Long id;

    private String name;

    protected Customer() {
    }
}
~~~

Annotations such as `@Entity` and `@Id` belong to the **Jakarta Persistence API**. They define metadata, yet do not execute SQL, dirty checking, caching, or transaction handling themselves.

A provider such as Hibernate ORM or EclipseLink handles those responsibilities.

### 5.1. The API Alone Suffices Only for Compilation

Example:

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.Persistence;

EntityManager em =
        Persistence.createEntityManagerFactory("orders")
                .createEntityManager();
~~~

The call compiles when the API is present. At runtime, if a compatible provider or required `persistence.xml`/container integration configuration is missing, bootstrapping will fail.

Possible causes include:

- No runtime provider is present.
- The provider is unregistered or cannot be discovered.
- A provider exists yet mismatches the API generation.
- DataSource/driver is missing.
- `persistence.xml` configuration is incorrect or missing from the artifact.
- The provider is present yet does not support the newer Java/class-file version.
- Module access for entity reflection is misconfigured.

To fix this, do not blindly add a random `*-impl` JAR. Inspect the **provider resolution path**, dependency graph, and actual runtime environment.

### 5.2. Framework Starters May Already Bundle the Provider

A framework starter/platform may transitively pull in the API, implementation, and related dependencies. In that case, directly adding an API or provider with the wrong version can conflict with the framework's dependency management.

Inspect:

- Which versions the BOM/platform manages.
- Which provider actually resolves.
- Whether the starter excludes another provider.
- Whether multiple JPA providers coexist.
- Whether an application server already supplies the runtime.

**Do not treat an undeclared transitive dependency as nonexistent.** Transitive dependencies remain on the classpath unless excluded.

## 6. Example 3: Jakarta Validation API and Validation Provider

A DTO with annotations:

~~~java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

public record CreateUser(
        @NotBlank String name,
        @Email String email) {
}
~~~

`@NotBlank` and `@Email` are constraint APIs/metadata. Having annotations alone does not mean validation runs automatically.

Runtime example:

~~~java
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;

public class ValidateExample {
    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();

            var violations = validator.validate(
                    new CreateUser("", "bad-email"));

            System.out.println(violations.size());
        }
    }
}
~~~

Usage model:

1. The API allows importing annotations and calling `Validation`.
2. The runtime provider enforces constraints.
3. A bootstrap mechanism locates the provider.
4. Frameworks like Spring can integrate a validator and manage its lifecycle automatically.

Without a provider, the DTO code may still compile, yet bootstrapping can throw `ValidationException`, depending on the specific environment.

### 6.1. When Is a Direct Implementation Needed?

- If a standalone application calls `Validation.buildDefaultValidatorFactory()`, a suitable runtime provider is needed.
- If an application server already supplies Bean Validation, check classloading and dependency scope.
- If a framework starter already brings a provider, do not add a second implementation merely because you see an API dependency.

### 6.2. Annotations Have No Effect Without an Engine

Placing `@Email` on a field does not automatically cause a setter or constructor call to reject input. Validation only occurs when an engine/framework is configured to run it.

Test an **actually violated constraint**, rather than only testing that annotations can be read via reflection.

## 7. Example 4: SLF4J API and Logging Implementation

SLF4J is a clear example of the facade-and-provider pattern.

Application code:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class OrderService {
    private static final Logger log =
            LoggerFactory.getLogger(OrderService.class);

    public void process(long orderId) {
        log.info("Processing order {}", orderId);
    }
}
~~~

The application calls the **SLF4J API**, while writing logs to the console, files, JSON sinks, or monitoring systems depends on the **logging provider/backend**.

A common setup uses Logback; another project uses Log4j 2 via a compatible binding/provider.

### 7.1. Missing Provider

Having only `slf4j-api` allows code to compile and run, yet logs may not be processed by a real backend as expected, or the runtime may emit warnings and fall back to a no-op logging implementation.

Exact behavior depends on the SLF4J line:

- SLF4J 1.7 uses its own binding mechanism.
- SLF4J 2.x uses the service provider mechanism.
- A binding/provider from an incompatible generation may not be recognized.

Therefore, **do not arbitrarily mix SLF4J 1.7 bindings with an SLF4J 2.x runtime** and expect them to be selected.

### 7.2. Multiple Providers Present

When multiple SLF4J providers are available, the runtime may log a warning and pick one provider; runtime behavior becomes unpredictable if left to classpath ordering.

The solution is:

1. Decide which logging backend the system uses.
2. Keep only the required provider/binding.
3. Exclude unwanted providers pulled in via transitive dependencies.
4. Verify logs are actually written and delivered to the expected destination.
5. Check logging configuration in the final packaged artifact.

### 7.3. Bridges and Forwarding Loops

Some libraries use Java Util Logging (JUL), Log4j API, or SLF4J. Bridges forward events from one logging framework to another.

If you configure a circular bridge—for example A to B and B back to A—it can cause recursion, duplicated logs, or severe failures. Therefore, never add every bridge "just in case."

Map out the logging flow direction and distinguish:

- The API called by source code.
- The backend that actually writes logs.
- Bridges adapting other APIs.
- The provider/binding communicating with the backend.

## 8. Example 5: JDBC API and Driver Implementation

In Java SE, `java.sql` provides interfaces:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;

Connection connection =
        DriverManager.getConnection(
                "jdbc:vendor://db.example:5432/app",
                "username",
                "password");
~~~

The **JDBC API** defines `Connection`, `PreparedStatement`, `ResultSet`, and other contracts. The database vendor's **JDBC driver** implements how to communicate with the database.

An application compiles with just the JDK, yet `DriverManager.getConnection(...)` will not succeed without an appropriate driver and valid URL/configuration.

### 8.1. Driver Discovery

Modern JDBC discovers drivers via service provider registration in the driver JAR. Thus, with compliant drivers, applications do not necessarily need to call manually:

~~~java
Class.forName("com.vendor.jdbc.Driver");
~~~

Nevertheless, actual driver loading still depends on the classpath, module path, and environment class loaders. Some frameworks or application servers also manage data sources in their own ways.

### 8.2. Drivers Can Be Runtime-Only

If source code uses only standard JDBC APIs, vendor driver classes might not need to be imported at compile time. In that case, the driver JAR can be declared as a runtime-only dependency, depending on your build tool and framework.

Gradle example:

~~~groovy
dependencies {
    runtimeOnly("com.vendor:jdbc-driver:VERSION")
}
~~~

`com.vendor:jdbc-driver:VERSION` is only a placeholder. A real driver must be chosen for compatibility with your database, Java baseline, license, and version.

If source code imports vendor-specific types, the driver may be required on the compile classpath; however, that also couples the application to implementation-specific APIs.

### 8.3. Having the Right Driver Does Not Guarantee Database Connectivity

Different failure modes:

- `No suitable driver`: driver not found or does not accept the URL.
- Authentication failure: driver present, yet credentials/policy are wrong.
- TLS handshake error: driver present, yet certificate/protocol configuration is incompatible.
- `NoSuchMethodError`: driver or transitive dependency version mismatch.
- Unsupported class file: driver compiled for a newer JDK than the runtime.

Do not lump every JDBC error together as "missing JDBC API."

## 9. Example 6: JAXB and APIs No Longer Bundled in Newer JDKs

In some older JDKs, Java EE-related modules such as JAXB/JAX-WS were supplied by the JDK. In JDK 11, the Java EE and CORBA modules were removed (JEP 320).

Consequence: code that compiled/ran on an older JDK may fail to find JAXB types or runtime bootstrap providers when moving to JDK 11+.

JAXB consumer example:

~~~java
import jakarta.xml.bind.JAXBContext;
import jakarta.xml.bind.Marshaller;

JAXBContext context =
        JAXBContext.newInstance(Customer.class);

Marshaller marshaller =
        context.createMarshaller();

marshaller.marshal(customer, System.out);
~~~

When using the Jakarta generation, you need both **the API in the matching namespace** and **a compatible implementation**. Adding only the API artifact may let code compile while `JAXBContext.newInstance(...)` fails due to a missing runtime provider.

### 9.1. Two Independent Issues When Migrating JAXB

**Issue A — library no longer provided by the JDK:** you must declare external dependencies instead of relying on removed JDK modules.

**Issue B — namespace/generation:** many older APIs live in `javax.xml.bind.*`, whereas the newer Jakarta generation uses `jakarta.xml.bind.*`. Migrating namespaces requires reviewing source code, annotations, providers, and frameworks—not merely changing a dependency's groupId.

Do not mix:

- Source importing `javax.xml.bind.*`.
- The `jakarta.xml.bind.*` API.
- A runtime implementation from a different generation.

Many failures can appear as missing classes or missing providers even when a "JAXB" JAR is present.

### 9.2. API and Runtime Can Be Separate Artifacts

Illustrative Maven example:

~~~xml
<dependency>
    <groupId>jakarta.xml.bind</groupId>
    <artifactId>jakarta.xml.bind-api</artifactId>
    <version>COMPATIBLE_API_VERSION</version>
</dependency>

<dependency>
    <groupId>org.glassfish.jaxb</groupId>
    <artifactId>jaxb-runtime</artifactId>
    <version>COMPATIBLE_RUNTIME_VERSION</version>
    <scope>runtime</scope>
</dependency>
~~~

The `COMPATIBLE_*` values are placeholders, not literals to build directly. Pick versions from the compatibility matrix of your target runtime/framework/JDK.

If source code or annotation processors reference implementation-specific types, runtime-only scope may be insufficient; identify actual code boundaries rather than copying templates mechanically.

## 10. JAX-WS, Jakarta Mail, CDI, and JSON Providers

To avoid similar issues, apply the same set of questions across multiple Java specifications:

### 10.1. JAX-WS

The SOAP-based web services API defines annotations and contracts. The corresponding runtime needs an implementation stack, such as Metro in systems using that stack.

Once Java EE modules are no longer bundled in JDK 11, merely adding the API and expecting a SOAP server to work is usually not enough. Check:

- Runtime creating and processing SOAP messages.
- HTTP transport integration.
- XML binding.
- Provider registration.
- Matching package namespace.

### 10.2. Jakarta Mail

APIs such as `jakarta.mail.*` define messages, sessions, transports, and related concepts. The matching implementation must provide SMTP/IMAP/POP3 protocol providers when used by the application.

When errors happen, distinguish:

- Missing API.
- Missing implementation/provider.
- Provider present yet protocol/TLS/authentication configuration is wrong.
- Generation mismatch between `javax.mail` and `jakarta.mail`.

### 10.3. CDI

The CDI API defines dependency injection contracts and annotations; a CDI runtime such as Weld or OpenWebBeans is integrated according to your deployment architecture.

A plain Java application launching directly via `main` with CDI annotations does not gain container-managed injection unless you bootstrap a CDI runtime or a supporting framework. Conversely, an application server may already supply CDI, so bundling an extra standalone runtime can be wrong.

### 10.4. JSON-P and JSON-B

JSON-P and JSON-B are two distinct APIs with different responsibilities:

- JSON-P focuses on parsing/generation and JSON models.
- JSON-B defines how to bind JSON to Java objects.

A JSON-B runtime may require a compatible JSON-P implementation. Do not see the word "JSON" and assume a single dependency satisfies every API.

Check each pair's engine/factory, provider discovery, and specific transitive dependencies.

## 11. Maven Dependency Scopes: Where Do APIs and Runtimes Live?

A Maven project can use the following scopes:

| Scope | Primary role | Notes for API/implementation |
|---|---|---|
| `compile` | Available at compile time and normally on runtime/test classpaths | Default; propagates transitively to consumers |
| `provided` | Available for compile/test, yet expected from runtime/container | Suitable when the server already manages the API/implementation |
| `runtime` | Needed at runtime/test, not needed to compile source | Suitable for drivers/providers not directly imported by source |
| `test` | For tests only | Test implementations do not enter production artifacts automatically |
| `system` | Dependency via local path, poorly portable | Usually avoided in favor of standard artifact management |
| `import` | Imports a BOM inside `dependencyManagement` | Manages versions; does not add JARs to runtime itself |

Example when deploying a WAR onto a compatible Servlet container:

~~~xml
<dependency>
    <groupId>jakarta.servlet</groupId>
    <artifactId>jakarta.servlet-api</artifactId>
    <version>COMPATIBLE_VERSION</version>
    <scope>provided</scope>
</dependency>
~~~

Example runtime provider for a standalone application:

~~~xml
<dependency>
    <groupId>example.group</groupId>
    <artifactId>example-implementation</artifactId>
    <version>COMPATIBLE_VERSION</version>
    <scope>runtime</scope>
</dependency>
~~~

`example.*` and `COMPATIBLE_VERSION` are placeholders.

### 11.1. provided Does Not Mean "Not Needed at Runtime"

A dangerous mistake is interpreting `provided` as "no longer needed." In fact, it tells the build tool that **an external runtime environment will supply** that component. If the environment does not provide it, the application compiles and then fails at runtime.

Examples:

- WAR: Servlet container provides the Servlet API.
- Standalone JAR: without an embedded server, `provided` scope alone can omit required runtime pieces.
- App server: may supply JPA/CDI/Validation; check actual server versions.
- Test container: may emulate the environment, yet local tests do not fully represent production.

### 11.2. A BOM Is Not an Implementation

A BOM in `dependencyManagement` specifies versions or constraints; it does not automatically pull every platform module into runtime.

Example:

~~~xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>example.platform</groupId>
      <artifactId>example-bom</artifactId>
      <version>PLATFORM_VERSION</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>
~~~

After importing a BOM, the project still must declare the required dependencies. Do not treat "BOM imported" as proof that a provider is present.

### 11.3. Evaluating Transitive Dependencies

A runtime implementation often brings its API and helper libraries along in the dependency graph. In some cases, adding only the implementation suffices for compile and runtime because the API comes transitively. However, for a **public library API**, declare the dependency contract explicitly rather than leaving API availability to transitive implementation dependencies.

If you author `my-validation-extension` with a public method accepting `jakarta.validation.Validator`, that type is part of your library's public API; its transitive scope to consumers must be designed so consumers can compile against it.

## 12. Gradle: api, implementation, compileOnly, and runtimeOnly

In Gradle with the `java-library` plugin, configurations carry distinct meanings:

| Configuration | Current module compiler | Consumer compiler | Runtime |
|---|---|---|---|
| `api` | Yes | Yes via API dependency | Typically yes |
| `implementation` | Yes | Not exported as compile API to consumers | Yes |
| `compileOnly` | Yes | Not propagated to consumers at runtime | Not by default |
| `runtimeOnly` | No | No | Yes |
| `testImplementation` | Yes for tests | No | Tests |
| `testRuntimeOnly` | Not for test compilation | No | Test runtime |

Example of a library using a public API and an internal provider:

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    api("com.example:service-api:API_VERSION")
    implementation("com.example:service-helper:HELPER_VERSION")
    runtimeOnly("com.example:service-provider:PROVIDER_VERSION")
}
~~~

This is merely illustrative syntax using placeholder coordinates.

### 12.1. When to Use api?

If a library's public method signatures, superclasses, or public annotations expose types from a dependency, consumers may need those types on their compile classpath.

~~~java
package com.example.library;

import com.example.contract.Task;

public interface TaskExecutor {
    void execute(Task task);
}
~~~

If `Task` comes from `service-api`, the dependency containing that type must be exposed appropriately to consumers. In Gradle's `java-library`, `api(...)` is usually the right choice.

### 12.2. When to Use implementation?

If a dependency serves only internal code and is never exposed in the public contract:

~~~java
public final class TaskExecutorImpl {
    private final InternalCodec codec = new InternalCodec();
}
~~~

then `implementation(...)` prevents leaking the dependency as part of consumers' compile-time API. The dependency can still be present at runtime.

### 12.3. When to Use compileOnly?

Use `compileOnly` when a module needs types to compile yet **must not bundle that JAR into runtime itself**. Typical case: an API supplied by an application server/container.

Do not choose `compileOnly` merely because an artifact is named "API." If the runtime does not supply that artifact through another mechanism, consumers can fail when loading classes, annotations, or interfaces.

### 12.4. When to Use runtimeOnly?

`runtimeOnly` fits when source code does not directly need implementation classes to compile, yet runtime needs a provider or driver—for example, a JDBC driver when code uses only `java.sql`.

If source code imports implementation-specific types or directly instantiates provider classes with `new`, a compile dependency is needed; leaving it `runtimeOnly` will cause compile errors.

### 12.5. Published Java Library Metadata

Gradle publishes metadata under `apiElements` and `runtimeElements` variants. When publishing, declaring `api` and `implementation` accurately ensures consumers receive the right compile and runtime dependencies.

Do not verify a public library solely by running tests within the same repository. Test with an independent consumer using the published artifact or a snapshot build to confirm dependency metadata propagates to consumers as expected.

## 13. SPI: The Mechanism Connecting APIs and Providers

A **Service Provider Interface (SPI)** is a contract enabling implementations to register themselves and be discovered by consumers without consumers directly importing implementation classes.

In Java SE, `java.util.ServiceLoader` is the standard mechanism.

### 13.1. Defining the Service Interface

~~~java
package com.example.spi;

public interface TextEncoder {
    String encode(String input);
}
~~~

### 13.2. Creating an Implementation

~~~java
package com.example.impl;

import com.example.spi.TextEncoder;

public final class UppercaseEncoder implements TextEncoder {
    @Override
    public String encode(String input) {
        return input.toUpperCase(java.util.Locale.ROOT);
    }
}
~~~

### 13.3. Registering on the Classpath

The implementation JAR can contain:

~~~text
META-INF/services/com.example.spi.TextEncoder
~~~

File contents:

~~~text
com.example.impl.UppercaseEncoder
~~~

Consumer:

~~~java
import com.example.spi.TextEncoder;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        for (TextEncoder encoder :
                ServiceLoader.load(TextEncoder.class)) {
            System.out.println(encoder.encode("hello"));
        }
    }
}
~~~

The consumer compiles against the API, while runtime requires the implementation JAR and service descriptor. If the service file is missing, the provider may **exist inside the JAR yet never be discovered**.

### 13.4. Named Modules Using provides/uses

Under the Java Platform Module System, a named implementation module can declare:

~~~java
module com.example.encoder.impl {
    requires com.example.encoder.api;
    provides com.example.spi.TextEncoder
        with com.example.impl.UppercaseEncoder;
}
~~~

A consumer module can declare:

~~~java
module com.example.application {
    requires com.example.encoder.api;
    uses com.example.spi.TextEncoder;
}
~~~

The API module must export the package containing `TextEncoder` for other modules to use it. Execution also depends on the module path, resolution, and module layers in use.

Do not assume a `META-INF/services` file alone suffices in every JPMS setup, or conversely assume `provides` solves classpath packaging. Test the exact execution mode of the artifact.

### 13.5. Common ServiceLoader Failures

- `ServiceConfigurationError`: malformed provider metadata, class fails to load, or provider requirements are unmet.
- No provider found: implementation absent at runtime, descriptor missing, or module not resolved.
- Multiple providers: consumer needs a policy to select one provider or allow multiple.
- Incompatible provider: old interface implementation hits linkage/runtime errors upon loading or invocation.

Service discovery is a **runtime contract**, not just a dependency entry in a POM.

## 14. Factories and Dependency Injection Are Wiring Mechanisms Distinct from SPI

An API may declare a factory or interface:

~~~java
public interface Storage {
    void save(String key, byte[] value);
}
~~~

An application can construct an instance directly:

~~~java
Storage storage = new FileStorage(rootDirectory);
~~~

Or inject it:

~~~java
public final class BackupService {
    private final Storage storage;

    public BackupService(Storage storage) {
        this.storage = storage;
    }
}
~~~

In the second example, a DI container or bootstrap code is responsible for supplying `Storage`.

If only the API is present without registering a bean/implementation, startup may fail or the component may fail to wire. Do not look for `META-INF/services` if the framework actually uses DI bean registration; similarly, do not look for DI registrations if an API bootstraps through `ServiceLoader`.

### 14.1. Common Wiring Mechanisms

| Approach | Who chooses the implementation? | What to inspect? |
|---|---|---|
| Direct instantiation | Application code | Compile dependency and constructor |
| Factory/Bootstrap | API or runtime config | Provider implementation and factory resolution |
| ServiceLoader/SPI | Service discovery | Service files, module declarations, runtime path |
| Dependency injection | Container/framework | Bean definitions, component scanning, scopes, runtime |
| Application server | Server platform | API/provider versions and deployment isolation |

Many frameworks combine mechanisms. For example, a DI container may use `ServiceLoader` during bootstrap and then expose beans to the application.

## 15. Java Module System and Classpath / Module Path

On modern JVMs, the same dependency may run on the **classpath** or **module path**. Access rules and service discovery behave differently.

### 15.1. API Module and Implementation Module

Architectural example:

~~~text
com.example.contract
  exports com.example.contract

com.example.provider
  requires com.example.contract
  provides com.example.contract.Codec
      with com.example.provider.DefaultCodec

com.example.app
  requires com.example.contract
  uses com.example.contract.Codec
~~~

The consumer may require only the API module. At runtime, however, the implementation module must be **resolved**, and service binding must be configured appropriately.

If building a custom runtime with `jlink`, adding only the API module to the image may omit the implementation. Depending on how the image is built, you may need to specify provider modules or supported service-binding options.

### 15.2. Automatic Modules Do Not Replace SPI Verification

A JAR placed on the module path without `module-info.class` becomes an automatic module. Module names and module-path semantics do not automatically guarantee every service provider is selected or compatible.

Verify:

- Actual module names.
- `requires`, `exports`, and `opens`.
- `uses` and `provides` where applicable.
- Resolved dependencies/modules.
- Classpath/module path and corresponding class loaders.
- Reflection access if needed by implementations/frameworks.

### 15.3. Split Packages and Duplicate API Classes

If two JARs contain the same package or same class, behavior can differ between the classpath and module path. On the module path, split-package conflicts can fail module resolution. On the classpath, which class loads can depend on loader/path order.

This is why you should never package multiple "same API, different versions" artifacts into one runtime and hope the classloader picks the right one.

## 16. javax.* and jakarta.* Namespaces: Watch Standard Generations

One of the major enterprise Java migrations is the shift of many APIs from the `javax.*` namespace to `jakarta.*` across corresponding Jakarta EE generations.

Example:

~~~java
// Old generation
import javax.persistence.Entity;
~~~

versus:

~~~java
// New Jakarta generation
import jakarta.persistence.Entity;
~~~

This is not merely an alternate spelling of the same class. In bytecode, the two names are completely separate types. A Jakarta API with matching functional names does not replace binary references to legacy `javax` APIs.

### 16.1. Upgrade the Entire Connected Stack Together

If code has moved to `jakarta.persistence.*` while the provider only understands `javax.persistence.*`, bootstrapping or mapping will fail.

If the servlet container runs modern Jakarta Servlet while a legacy web framework was compiled against `javax.servlet.*`, adding both API JARs typically does not create a valid adapter.

Therefore, align:

1. Source imports/annotations.
2. API artifact generation.
3. Implementation generation.
4. Framework/starter version.
5. Application server/container version.
6. Transitive dependencies.
7. Compiled consumer tests and integration workflows.

### 16.2. Do Not "Fix" by Indiscriminately Adding Both Namespaces

Having two API JARs does not mean a compatibility bridge exists. Specialized bytecode migration tools or adapters may exist for specific scenarios, yet you must verify supported scope and inspect output artifacts rather than guessing from package names.

## 17. API/Implementation Compatibility Has Multiple Dimensions

Two artifacts that appear to form the right pair can still fail to run due to version skew.

### 17.1. Source Compatibility

A newer implementation may require newer source or annotations. For example, a new method added to an API interface may require recompiling and updating application code.

### 17.2. Binary Compatibility

An implementation compiled against a newer API may invoke methods missing from an older API version at runtime:

~~~text
java.lang.NoSuchMethodError
~~~

An older implementation may fail to implement a newly added abstract method expected by the consumer/runtime:

~~~text
java.lang.AbstractMethodError
~~~

Do not treat those two errors as the sole evidence of a mismatch; they are common symptoms requiring inspection of the loaded classes.

### 17.3. Semantic/Behavioral Compatibility

A method may still exist while behavior changes:

- Stricter new validation constraints.
- Changed default formatting in a serializer.
- Changed transaction handling or exception propagation in a provider.
- Changed formatting or routing in a logging backend.
- Changed TLS defaults or data type mapping in a driver.

### 17.4. Java Baseline Compatibility

The API and implementation can be built for two different JDKs. If the implementation requires a class file major version newer than the runtime:

~~~text
java.lang.UnsupportedClassVersionError
~~~

Compiling application source with `--release 17` does not automatically downgrade an external implementation to Java 17.

### 17.5. Container and Runtime Compatibility

An implementation may require:

- Java modules omitted from a custom runtime image.
- Native libraries matching the CPU architecture.
- Reflection/module `opens` permissions.
- Service descriptor files and resources.
- Database drivers/connections.
- Specific server lifecycle or class loader behavior.

Compatibility evaluation must cover the actual **runtime topology**, not merely artifact coordinates.

## 18. Diagnosing Errors: Missing API or Missing Implementation?

| Symptom | Likely Cause | First Check |
|---|---|---|
| `package ... does not exist` at compile time | API absent from compile classpath or wrong namespace | Compiler classpath, imports, and dependency version |
| `cannot find symbol` | API type/method missing in the version used | API artifact and source |
| `ClassNotFoundException` | Class absent from runtime loader | Runtime classpath/module path, packaging |
| `NoClassDefFoundError` | Referenced class could not resolve/initialize | Nested cause, classpath, and initialization |
| `NoSuchMethodError` | Binary API/implementation skew or dependency version conflict | Method descriptor and JAR containing class |
| `AbstractMethodError` | Implementation lacks method expected by runtime | Interface/implementation versions |
| `ServiceConfigurationError` | Service provider metadata or type/load error | `META-INF/services`, module `provides` |
| Provider not found | API only, or broken provider discovery | Provider JAR, service descriptor, and config |
| `No suitable driver` | JDBC driver not found/does not accept URL | Driver artifact and JDBC URL |
| No logs or provider warnings | SLF4J backend/provider missing or wrong generation | SLF4J API version and provider |
| `ClassCastException` between "same-named" types | Two class loaders / duplicate API class | Class loader identity, WAR server libs |
| `UnsupportedClassVersionError` | Implementation requires newer JDK | Class file major version |
| `InaccessibleObjectException` | Module reflection access | JDK/JPMS and framework config |

One exception can have multiple root causes. For example, `NoClassDefFoundError` can be caused by failed class initialization rather than a missing JAR. Read the **caused by** chain and classloader context.

### 18.1. Using API Class Names to Locate the Right Dependency

When seeing:

~~~text
java.lang.NoClassDefFoundError:
  jakarta/validation/Validation
~~~

this indicates the API class may be missing, rather than directly proving the provider implementation is missing.

If `Validation` is present yet bootstrapping reports no provider found, that is a different class of error.

Read the exact class name, stack trace, and failure phase:

- Compile: missing API.
- Class load: missing API or dependency.
- Bootstrap: implementation/discovery/configuration.
- Invocation: version mismatch or business error.

### 18.2. Identifying Which JAR Loaded a Class

On modern JDKs, enable class-loading logs in test environments:

~~~bash
java -Xlog:class+load=info -jar app.jar
~~~

Logs can reveal the source from which the JVM loads classes. With nested JARs, custom framework class loaders, or containers, use the corresponding diagnostic mechanism.

In Java, when classloader/security policy permits, inspect a class's code source location:

~~~java
Class<?> type = jakarta.validation.Validation.class;

var codeSource = type.getProtectionDomain().getCodeSource();

System.out.println(
        codeSource == null
                ? "No code source available"
                : codeSource.getLocation());
~~~

Do not print full paths or configurations containing sensitive data in public logs. Verifying from the classloader prevents misdiagnosis when an old JAR lingers inside a server runtime.

## 19. Dependency Management Tools and Actual Artifact Inspection

### 19.1. Maven Dependency Tree

~~~bash
mvn dependency:tree
~~~

To focus on runtime dependencies, select options/scopes fitting your Maven plugin version. During investigation, understand dependency mediation and versions omitted due to conflict.

Hypothetical example:

~~~text
app
+- example:validation-api:2.x
\- example:validator-provider:3.x
   \- example:validation-api:3.x (omitted for conflict)
~~~

If runtime selects API 2.x while provider 3.x expects API 3.x, binary or bootstrap errors can happen. This is a dependency version mismatch and cannot be "fixed" with an import statement.

### 19.2. Gradle Dependency Graph

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
~~~

Investigating a specific dependency:

~~~bash
./gradlew dependencyInsight \
    --dependency example-validation \
    --configuration runtimeClasspath
~~~

Compare:

- Does the API on `compileClasspath` differ from `runtimeClasspath`?
- Which provider is added transitively?
- Are there multiple logging bindings/providers?
- Which dependency constraints or platforms determine versions?
- Did an exclude/force strip a required API from an implementation?
- Does the test runtime differ from the production runtime?

### 19.3. JAR Contents and Service Metadata

~~~bash
jar tf library.jar
~~~

Look for:

~~~text
META-INF/services/
module-info.class
META-INF/MANIFEST.MF
~~~

An implementation may need classes/service resources absent from consumer source code. When shading, minimizing, or building fat JARs, ensure service descriptors are neither lost nor overwritten erroneously.

### 19.4. jdeps and Static Dependency Analysis

~~~bash
jdeps --recursive --class-path "lib/*" app.jar
~~~

`jdeps` reveals bytecode- and module-level dependencies, yet cannot prove providers discovered via reflection or SPI. Dynamically loaded implementations may not appear in static call graphs.

Combine `jdeps` with:

- Dependency graphs.
- JAR content inspection.
- ServiceLoader/provider diagnostics.
- Runtime integration tests.
- Class-loading logs.

### 19.5. Analyze the Exact Released Artifact

An application may work in an IDE because the IDE puts both APIs and providers onto the classpath, while the released JAR fails to package them properly. Conversely, a WAR may run inside a container yet fail standalone.

Therefore, test against the exact:

- Packaged JAR/WAR/ZIP.
- Runtime dependency set.
- Container/server image.
- JDK distribution and version.
- Service/metadata files after packaging.

## 20. Shading, Fat JARs, and ServiceLoader

Packaging dependencies into a fat JAR can alter how providers are discovered.

Suppose two dependencies contain:

~~~text
META-INF/services/com.example.spi.Codec
~~~

If the assembly step keeps only one file instead of properly merging provider declarations, both implementations remain in the JAR yet `ServiceLoader` sees only one provider—or none.

Other risks:

- Relocation renames the provider class while the service descriptor keeps the old name.
- Minimizers strip implementations only referenced via SPI.
- Duplicate resources overwrite each other.
- JAR signatures or signature metadata become invalid after repackaging.
- Module descriptors no longer match the classpath layout.
- Container and fat JAR carry two versions of the same API.

Use appropriate transformers/merge rules in your build plugin and verify with `jar tf`, reading service descriptors, and running SPI discovery tests against the final artifact.

Never conclude that because a dependency is "in the POM", its implementation survives shading intact.

## 21. Designing Public Library APIs Without Leaking Implementations

If you develop a library for others, separating API from implementation improves upgradeability.

### 21.1. Avoid Exposing Implementation Classes in Method Signatures

Avoid designing a public API like:

~~~java
public VendorSpecificSession openSession();
~~~

if callers only need a generic contract. Design like:

~~~java
public Session openSession();
~~~

so implementations can be swapped without forcing every consumer to import vendor types.

However, you do not always need extra interfaces everywhere. The goal is **never accidentally turning internal details into a public contract**. If implementation-specific types are intentionally part of a public feature, version and manage their compatibility accordingly.

### 21.2. Factories and Provider Configuration

A good factory API generally allows:

- Selecting an implementation explicitly or via SPI.
- Reporting missing providers with helpful error messages.
- Avoiding hidden reliance on classpath order.
- Distinguishing "no provider" from "provider present yet misconfigured."
- Binding providers to an appropriate context/lifecycle.
- Identifying the active provider for diagnostics.

Avoid silently picking a different implementation if doing so breaks security, transaction, or data guarantees.

### 21.3. Do Not Expose Implementation Classes as Public Data Transfer Types

Exposing `HibernateProxy`, internal serializer classes, or vendor JDBC types in an API locks consumers to that implementation. Switching providers later is no longer a simple runtime dependency swap.

Prefer standard interfaces, DTOs, and intentional contracts at module boundaries.

## 22. Version Alignment and Dependency Governance

Managing API/provider alignment recurs across every Java and library upgrade.

### 22.1. Use a Compatibility Matrix Instead of Guessing from Version Numbers

Two artifacts with the same major version are not guaranteed compatible, and two artifacts with different major versions are not necessarily incompatible. Each project has its own versioning policy.

Read:

- Release notes and compatibility guides.
- JDK baseline requirements.
- API specification generations.
- Framework/application server compatibility.
- Provider dependency requirements.
- Namespace migration notes.
- Security fixes and end-of-support policies.

### 22.2. Classifying Roles in the Dependency Inventory

A useful table:

| Artifact | Role | Compile? | Runtime? | Who owns the version? |
|---|---|---|---|---|
| Servlet API | Contract | Yes | Container supplies in WAR model | Container/platform |
| Embedded server | Implementation/runtime | Depends on code | Yes | Application/framework |
| Persistence API | Contract | Yes | Usually needed for provider/runtime | Framework/platform |
| ORM provider | Implementation | Depends on code | Yes | Framework/BOM |
| Logging API | Facade | Yes | Yes | Platform/library |
| Logging backend | Provider | Not necessarily | Yes | Application |
| JDBC driver | Database implementation | No if using JDBC only | Yes | Application/platform |
| Test engine | Test implementation | Test | Test | Build/test platform |

Do not force one table onto every deployment model. For instance, an application server may manage the persistence API and provider, whereas a microservice manages both itself.

### 22.3. Dependency Locking and Reproducible Builds

If an application uses dynamic versions or unlocked transitive dependencies, the same source commit can resolve different providers at different times.

Useful controls:

- Dependency locking.
- Unified BOM/platform.
- Dependency constraints.
- Reviewed version catalogs or dependency management.
- SBOMs for released artifacts.
- Testing against actually resolved runtime dependencies.

Locking aids reproducibility, yet you still must actively apply security patches and verify compatibility.

### 22.4. Avoid Fixing Errors by Adding Multiple Implementations

The idea of "adding Hibernate, EclipseLink, every logging provider, and every JAXB runtime so something works" inflates artifact size, creates service ambiguity, and widens maintenance surface.

The right approach:

1. Identify the required API contract.
2. Choose the single provider fitting the architecture.
3. Check versions and Java baseline.
4. Exclude unwanted providers.
5. Test bootstrap and actual functionality.
6. Document how the provider is selected.

## 23. Matrix Testing API–Implementation Compatibility

A thorough test covers both compile and runtime.

| Test | API | Implementation | Verification Goal |
|---|---|---|---|
| Compile consumer | Published version | May not need loading | Public types/methods valid |
| Runtime bootstrap | Published version | Selected provider | Provider found and initialized |
| Core operation | Matching-generation API | Real implementation | Runtime behavior succeeds |
| Old consumer on new runtime | Precompiled API | New implementation | Binary compatibility |
| Recompile consumer | New API | New provider | Source compatibility |
| Packaged artifact | Final JAR/WAR | Target runtime/container | No missing resources/metadata |
| Minimum JDK | Compatible API | Compatible provider bytecode | Does not exceed class file/JDK baseline |
| Negative test without provider | API present | Absent | Clear error, no wrong fallback |
| Multiple providers test | API present | Multiple | Clear selection policy |
| Dependency upgrade | New API/provider generation | New version | No transitive version skew |

### 23.1. An API-Only Test Is Not Enough

Running only:

~~~java
assertNotNull(jakarta.validation.constraints.NotNull.class);
~~~

only proves the API class loads. It does not prove the validator works.

Exercise a real operation:

~~~java
ValidatorFactory factory =
        jakarta.validation.Validation
                .buildDefaultValidatorFactory();

try (factory) {
    var validator = factory.getValidator();
    // Test invalid constraints and check violations.
}
~~~

### 23.2. Testing from an Independent Consumer

To protect a public library:

1. Build or publish the API/library artifact.
2. Create an independent sample consumer.
3. Compile the consumer against the published version.
4. Package the consumer and runtime dependencies.
5. Run on the minimum supported JDK.
6. Verify the real provider and execute a functional operation.
7. Test an older consumer binary against the new library/provider if binary compatibility is promised.

An independent consumer catches cases where tests inside a multi-module build accidentally see an implementation on the compile path that real users lack.

## 24. Step-by-Step Migration Process

~~~mermaid
flowchart TD
    A["Inventory APIs, providers, and runtime"] --> B["Identify generation/version and owner"]
    B --> C["Classify compile/runtime/container"]
    C --> D["Upgrade API, implementation, and framework in sync"]
    D --> E["Analyze dependency graph and packaging"]
    E --> F["Test bootstrap on target JDK"]
    F --> G["Test functionality and old/new consumers"]
    G --> H{"Pass on the final artifact?"}
    H -->|Yes| I["Release with evidence and SBOM"]
    H -->|No| J["Inspect errors, fix classpath/provider/version"]
    J --> E
~~~

### Step 1. Inventory APIs and Implementations

Record for each pair:

- API/specification name.
- Package namespace.
- API artifact coordinates and version.
- Implementation/provider coordinates and version.
- Runtime owner: application, container, or server.
- Bootstrap mechanism: direct, factory, SPI, DI.
- JDK baseline and related modules.
- Tests proving the provider works.
- Owner and upgrade plan.

### Step 2. Find Conflicting Dependencies

Compare compile and runtime dependency graphs; inspect duplicate API JARs, unwanted providers, and versions selected by mediation/BOMs.

### Step 3. Select a Compatible Stack

Choose API, provider, framework, and container from the same generation. Check `javax`/`jakarta` namespaces, class file versions, and Java baseline policy.

### Step 4. Configure Scopes by Deployment Model

Decide which dependencies are:

- Public APIs exported to consumers.
- Internal library implementations.
- Runtime-only providers.
- APIs/implementations provided by an external container.
- Test-only dependencies.

Never copy `provided` or `compileOnly` without understanding the operating environment.

### Step 5. Verify Service Registration

For SPI:

- Correct provider JAR is present.
- `META-INF/services` or `provides` is correct.
- Provider classes are loadable.
- Resources are not stripped during shading.
- No unexpected third-party provider gets picked instead.

### Step 6. Test Real Functionality

Test the corresponding HTTP request, database query, constraint validation, XML serialization, logging delivery, or crypto operation. Merely loading a class or printing a provider list is not enough.

### Step 7. Verify the Artifact and Roll Out

Run the exact final artifact on the target JDK/container/server; record checksums, dependency graphs, and bootstrap logs. If changing API namespaces or serialization contracts, prepare corresponding consumer upgrade and data migration plans.

## 25. Combined Scenario: Upgrading a Project from an Old JDK to a New JDK

A legacy system has:

- A web module using Servlet API from the container.
- A persistence module using JPA and an ORM provider.
- XML integration using JAXB formerly supplied by the JDK.
- Validation annotations on DTOs.
- Logging through SLF4J.
- A database-specific JDBC driver.

After upgrading the JDK and framework, the team encounters:

1. JAXB classes not found.
2. Web app conflicts between `javax.servlet` and `jakarta.servlet`.
3. Validation bootstrap finds no provider.
4. Logger prints provider warnings.
5. JPA provider fails with missing-method errors at startup.
6. Production driver missing from the executable artifact.

If handled by "seeing a missing class and adding any JAR with a similar name," the classpath quickly becomes unmanageable.

Structured approach:

| Symptom | Classification | Right Fix |
|---|---|---|
| Missing JAXB classes | API removed from JDK or different namespace | Add matching-generation API and corresponding runtime |
| Servlet conflict | Container/API/framework generation mismatch | Align entire stack and provided/embedded scope |
| Validation provider not found | API present, implementation/bootstrap missing | Choose compatible provider and check SPI |
| SLF4J warning | Facade missing/wrong backend provider | Keep a single provider of matching generation |
| JPA linkage error | API/provider/transitive version skew | Align versions via BOM and runtime graph |
| JDBC missing in packaged JAR | Runtime dependency/packaging error | Ensure driver enters the runtime artifact |

After fixing, the team not only runs compilation, yet also boots the artifact, calls APIs, connects to the DB, validates input, serializes XML, and confirms log output on the target JDK/container.

## 26. Common Mistakes

### 26.1. "Having the API Means Having the Implementation"

False. Interfaces/annotations/factories do not necessarily carry a runtime engine. A provider or container capable of executing the operation is required.

### 26.2. "Having the Implementation Means API Version Does Not Matter"

False. Providers are compiled and tested against a specific API generation. Wrong namespaces or mismatched method descriptors cause linkage errors.

### 26.3. "If Imports Compile, Runtime Will Work"

False. `compileClasspath` differs from `runtimeClasspath`; service metadata or providers may be absent from the packaged artifact.

### 26.4. "Setting provided Is Safe for Every Application"

False. `provided` makes sense only when the runtime/container truly supplies that component. Standalone applications normally must bundle implementations or matching dependencies.

### 26.5. "Just Add Both javax and jakarta JARs"

False. Package names differ; having both does not create a valid bridge between framework and provider.

### 26.6. "A BOM Provides Every Necessary Library"

False. A BOM manages versions/constraints; it does not automatically add every implementation to runtime.

### 26.7. "Having Two Providers Coexist Is Even Better"

Not necessarily. It can cause nondeterministic selection, warnings, bridge recursion, or configuration conflicts.

### 26.8. "ServiceLoader Will Always Discover Every Implementation"

False. Service descriptors, module `provides`, classloader context, and artifact packaging can all prevent discovery.

### 26.9. "If a Provider Is Found, Operations Will Definitely Work"

False. A provider may bootstrap yet fail to support a database URL, TLS config, key type, method/algorithm, or expected feature.

### 26.10. "Every Library Named impl Should Be runtimeOnly"

False. If source imports concrete implementation classes, compilation needs the dependency too. Architectural goals may aim to reduce such imports, yet dependency declarations must reflect actual current code.

### 26.11. "Inspecting Only the Test Dependency Tree Is Enough"

False. Test environments may have test-only providers, mocks, embedded DBs, or a broader classpath than production. Always test the deployment artifact.

### 26.12. "Upgrading the JDK Means Java SE Still Supplies Old APIs"

False. Legacy Java EE/CORBA modules formerly bundled in older JDKs were removed in JDK 11; related APIs and implementations must be managed explicitly per actual runtime and version.

## 27. Dependency Review Checklist

### Contracts

- [ ] Identified which artifacts are APIs/specifications and which are implementations.
- [ ] Identified whether each API belongs to Java SE, Jakarta EE, or a third-party specification.
- [ ] Recorded exact `javax.*` or `jakarta.*` namespace.
- [ ] Distinguished public API dependencies from implementation details.
- [ ] Identified what selects the implementation: application, SPI, DI, or container.

### Build and Versions

- [ ] Compared `compileClasspath` and `runtimeClasspath`.
- [ ] Verified Maven scopes/Gradle configurations match deployment.
- [ ] Confirmed BOMs/platforms are not mistaken for implementations.
- [ ] Checked transitive dependencies, conflicts, excludes, and forced versions.
- [ ] Verified API/provider share the same generation and JDK baseline.
- [ ] Checked for duplicate classes and multiple providers.

### Runtime and Packaging

- [ ] Confirmed providers exist at runtime or are supplied by the server.
- [ ] Checked `META-INF/services`, `module-info.class`, and provider discovery.
- [ ] Verified shading/minimization does not strip metadata or providers.
- [ ] Confirmed classes load from the right JAR and class loader.
- [ ] Tested minimum supported runtime and custom JRE/JDK images.
- [ ] Executed real operations rather than checking class existence alone.
- [ ] Tested with an independent consumer and the packaged artifact.
- [ ] Recorded dependency graphs, runtime versions, checksums, and related errors.

### Migration

- [ ] Read compatibility guides for APIs, providers, frameworks, and containers.
- [ ] Prepared a namespace migration plan when needed.
- [ ] Tested backward/binary compatibility for older consumers.
- [ ] Planned rollout and rollback matching the runtime topology.
- [ ] Removed obsolete/redundant providers and updated the dependency inventory.
- [ ] Documented the chosen provider to ease future diagnostics.

## Conclusion

**An API** defines the contract used by consumers; **an implementation library** supplies the actual behavior for that contract. Between those two layers sits a provider-selection mechanism such as a factory, `ServiceLoader`, dependency injection, or container. In Java, dependency declarations must accurately reflect **compile classpath, runtime classpath, version generation, modules/class loaders, and deployment model**.

When upgrading the JDK or dependencies, do not stop once classes resolve and builds succeed. Determine which APIs are in use, which provider executes them, who manages versions, how providers are discovered, and whether real functionality works in the released artifact. Separating APIs cleanly from implementations prevents missing runtimes, duplicate providers, `javax`/`jakarta` mismatches, and hard-to-diagnose compatibility bugs.
