# Compatibility Between Legacy javax Libraries and jakarta Containers

When upgrading a Java EE application to Jakarta EE, a very common situation is that **the application or legacy libraries still reference `javax.*` types**, while the newer application server, servlet container, or framework already uses `jakarta.*` types. The project may compile successfully by bringing along the old API JAR, yet still fail during deployment, when the container scans servlets/filters/listeners, when loading JPA entities, or when initializing providers for Validation, JAX-RS, and other Java EE technologies.

The core reason is that **changing namespaces is not just renaming imports cosmetically**. To the JVM, `javax.servlet.Filter` and `jakarta.servlet.Filter` are two distinct types; method descriptors, interface contracts, annotations, and much related metadata must all be compatible with the running ecosystem. A container that moved to Jakarta Servlet does not automatically treat a `javax.servlet.Filter` implementation as a `jakarta.servlet.Filter` implementation.

This lesson focuses on how to detect, explain, and resolve the compatibility boundary between **legacy `javax` libraries** and **`jakarta`-based containers**, especially when moving from Java EE/Jakarta EE 8 to Jakarta EE 9+, Tomcat 9 to Tomcat 10+, or Spring Framework 5/Spring Boot 2 to Spring Framework 6/Spring Boot 3.

> Main principle: the **same API generation is required at contract points managed by the container/framework**. Adding both API JARs to the classpath does not turn the two type families into one.

## 1. Distinguishing Java EE, Jakarta EE, and Namespace Names

### 1.1. Java EE and Jakarta EE 8

Java EE uses many APIs under the `javax.*` namespace. When the platform was renamed to Jakarta EE, **Jakarta EE 8 still used `javax.*` packages** for APIs inherited from Java EE.

For example:

```java
import javax.servlet.Servlet;
import javax.servlet.Filter;
import javax.persistence.Entity;
import javax.ws.rs.GET;
import javax.validation.NotNull;
```

These imports do not automatically become `jakarta.*` merely because an artifact or document includes the word "Jakarta".

### 1.2. Jakarta EE 9 onward

Jakarta EE 9 made a major namespace change for core APIs within the Jakarta EE scope:

```java
import jakarta.servlet.Servlet;
import jakarta.servlet.Filter;
import jakarta.persistence.Entity;
import jakarta.ws.rs.GET;
import jakarta.validation.constraints.NotNull;
```

Some products support Jakarta EE 9.1, 10, 11, or other levels with their own Java and API version requirements. **The package change starts in Jakarta EE 9; choosing a specific container generation also depends on the product's API level and Java runtime.**

### 1.3. Not every `javax.*` becomes `jakarta.*`

This is a common mistake when migrating via bulk find-and-replace. Many `javax.*` packages belong to **Java SE**, not Java EE APIs changing namespaces.

| Group | Old Namespace | New Jakarta EE Namespace | Notes |
|---|---|---|---|
| Servlet | `javax.servlet.*` | `jakarta.servlet.*` | Changed in Jakarta Servlet 5.0 |
| Persistence/JPA | `javax.persistence.*` | `jakarta.persistence.*` | Jakarta Persistence 3.0 |
| JAX-RS | `javax.ws.rs.*` | `jakarta.ws.rs.*` | Jakarta RESTful Web Services 3.0 |
| Bean Validation | `javax.validation.*` | `jakarta.validation.*` | Jakarta Validation 3.0 |
| CDI | `javax.enterprise.*`, `javax.inject.*` | `jakarta.enterprise.*`, `jakarta.inject.*` | Must also check the DI implementation |
| JMS | `javax.jms.*` | `jakarta.jms.*` | Messaging client/provider must share generation |
| JAX-WS | `javax.xml.ws.*` | `jakarta.xml.ws.*` | SOAP stack must also match |
| JAXB | `javax.xml.bind.*` | `jakarta.xml.bind.*` | Note JAXB is no longer bundled in JDK 11 |
| Jakarta Annotations | Java EE portion of `javax.annotation.*` | `jakarta.annotation.*` | Do not mistakenly change `javax.annotation.processing.*` |
| Java SE JDBC | `javax.sql.*` | **Remains `javax.sql.*`** | Do not look for `jakarta.sql` |
| Java SE XML | `javax.xml.parsers.*`, `javax.xml.transform.*` | **Remains `javax.xml.*`** | Do not change Java SE XML APIs |
| Java SE crypto | `javax.crypto.*`, `javax.net.ssl.*` | **Remains `javax.*`** | Not part of the Jakarta EE change |
| Java SE JTA/XA | `javax.transaction.xa.*` | **Remains `javax.transaction.xa.*`** | Distinct from Jakarta Transactions API `jakarta.transaction.*` |

A `javax.crypto` or `javax.sql` library can run normally inside a Jakarta container because it uses Java SE APIs. Therefore, you must identify the **exact package and specification**, not simply search for the string `javax`.

## 2. Source Compatibility, Binary Compatibility, and Runtime Contract

### 2.1. The JVM treats `javax.servlet.Filter` and `jakarta.servlet.Filter` as two types

Old version:

```java
package com.example.web;

import javax.servlet.Filter;

public final class AuditFilter implements Filter {
    // Implement methods according to the javax Servlet API.
}
```

New version:

```java
package com.example.web;

import jakarta.servlet.Filter;

public final class AuditFilter implements Filter {
    // Implement methods according to the jakarta Servlet API.
}
```

Even though the application's class name is still `com.example.web.AuditFilter`, the interface list in bytecode differs. An object implementing `javax.servlet.Filter` **is not automatically** a `jakarta.servlet.Filter`.

Example by type logic:

```java
// The Jakarta container expects this type:
jakarta.servlet.Filter filter = ...;
```

An instance of the old class implementing only `javax.servlet.Filter` cannot be validly assigned to the variable above merely because both APIs have similar methods.

### 2.2. Method descriptor changes

Suppose a library defines an extension point:

```java
// Old API
void initialize(javax.servlet.ServletContext context);
```

After converting:

```java
// New API
void initialize(jakarta.servlet.ServletContext context);
```

At the JVM level, the descriptors differ:

```text
Old: (Ljavax/servlet/ServletContext;)V
New: (Ljakarta/servlet/ServletContext;)V
```

**Changing packages changes binary type identity and descriptors**, even when the method name, logical type, and source body look almost identical.

When a compiled binary looks for a method with the old descriptor while runtime only provides the new descriptor, `NoSuchMethodError` can occur. If runtime cannot find `javax/servlet/...`, `NoClassDefFoundError` can occur. The exact error depends on the class loading path and executed operation.

### 2.3. Compilation success does not guarantee deployment success

A module can declare both APIs:

```text
javax.servlet-api.jar
jakarta.servlet-api.jar
```

Because they have different FQCNs, the compiler may accept both type families in the same source tree. However, that **does not make the Jakarta container execute `javax.servlet.Filter` as a Jakarta Filter**.

This is an example of source compilation success yet runtime integration failure.

### 2.4. Container integration is a contract that must be honored

The container does not merely load `.class` files. It can:

- Search for implementations of `jakarta.servlet.Servlet`, `Filter`, and listener interfaces.
- Scan annotations such as `jakarta.servlet.annotation.WebServlet`.
- Load `jakarta.persistence.Entity` for the JPA provider.
- Discover CDI annotations, REST resources, and Validation constraints.
- Manage dependency injection, sessions, transactions, security, and lifecycle hooks.

Legacy libraries declaring annotations or interfaces in the `javax` family generally do not participate properly in this contract inside a pure Jakarta container.

## 3. Servlet Scenario: Tomcat 9 vs. Tomcat 10+

An easily observable example is the Tomcat ecosystem.

| Runtime Container | Typical Servlet API Generation | Namespace |
|---|---|---|
| Tomcat 9 | Servlet 4.0 | `javax.servlet.*` |
| Tomcat 10.0 | Jakarta Servlet 5.0 | `jakarta.servlet.*` |
| Tomcat 10.1 | Jakarta Servlet 6.0 | `jakarta.servlet.*` |
| Tomcat 11 | Jakarta Servlet 6.1 | `jakarta.servlet.*` |

**Tomcat 10+ is not a drop-in replacement upgrade for legacy `javax` Servlet applications.** You must migrate namespaces and verify related spec/container changes.

Some products like Jetty may provide multiple deployment environments for different EE levels within the same product line. That is a specific feature that must be configured and verified; do not infer that every "Jakarta container" supports `javax` directly.

### 3.1. Legacy Servlet

```java
package com.example.web;

import java.io.IOException;
import javax.servlet.ServletException;
import javax.servlet.http.HttpServlet;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

public final class HealthServlet extends HttpServlet {
    @Override
    protected void doGet(
            HttpServletRequest request,
            HttpServletResponse response)
            throws ServletException, IOException {
        response.setContentType("text/plain");
        response.getWriter().write("OK");
    }
}
```

This code belongs to the `javax.servlet.http.HttpServlet` contract. If deployed directly onto a runtime accepting only Jakarta Servlet APIs, the container cannot automatically turn that class into `jakarta.servlet.http.HttpServlet`.

### 3.2. Servlet migrated to Jakarta

```java
package com.example.web;

import java.io.IOException;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

public final class HealthServlet extends HttpServlet {
    @Override
    protected void doGet(
            HttpServletRequest request,
            HttpServletResponse response)
            throws ServletException, IOException {
        response.setContentType("text/plain");
        response.getWriter().write("OK");
    }
}
```

The logic is virtually unchanged, yet the type contract with the container genuinely changed.

If the application's class in the artifact still extends `javax.servlet.http.HttpServlet`, editing `web.xml` or adding `jakarta.servlet-api.jar` alone is not enough.

### 3.3. Filters must also follow the container's namespace

With Jakarta Servlet:

```java
package com.example.web;

import java.io.IOException;
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;

public final class AuditFilter implements Filter {
    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {
        // Record audit logging before or after invoking the filter chain.
        chain.doFilter(request, response);
    }
}
```

If a legacy security library only supplies a `javax.servlet.Filter`, a Jakarta container cannot treat it as a filter under the new API. You need a Jakarta-compatible library release, verified binary transformation, or an intentional adapter.

## 4. `provided`/`compileOnly` Dependencies: Right Role, Does Not Fix Namespace

In traditional WARs, the Servlet API is usually provided by the container. Therefore, when compiling a Jakarta Servlet application, the API dependency is usually `provided` in Maven or `compileOnly` in Gradle.

### 4.1. Maven for Jakarta Servlet

```xml
<dependencies>
    <dependency>
        <groupId>jakarta.servlet</groupId>
        <artifactId>jakarta.servlet-api</artifactId>
        <version>6.0.0</version>
        <scope>provided</scope>
    </dependency>
</dependencies>
```

The example version must match the Jakarta Servlet level supported by the target container. Do not copy version 6.0.0 to Tomcat 10.0, which belongs to the Servlet 5.0 generation, and assume full compatibility.

### 4.2. Gradle Groovy DSL

```groovy
plugins {
    id 'war'
}

dependencies {
    compileOnly 'jakarta.servlet:jakarta.servlet-api:6.0.0'
}
```

When using the WAR plugin, verify the exact configuration, packaging tasks, and how the container supplies APIs. With Spring Boot executable JARs using an embedded server, the runtime dependency mechanism differs from WARs deployed to an application server.

### 4.3. Why not stuff `javax.servlet-api` into a new WAR?

A common wrong fix:

```text
WEB-INF/lib/javax.servlet-api.jar
WEB-INF/lib/jakarta.servlet-api.jar
```

Adding the old API JAR may allow `javax.servlet.*` classes to be found, but it does not create a matching Javax Servlet runtime implementation inside a Jakarta container. Nor does it turn `javax.servlet.Filter` into `jakarta.servlet.Filter`, or make the container scan Javax annotations as Jakarta annotations.

This is the difference between:

1. **Does the class exist to be loaded?**
2. **Does the class implement/have the exact interface/annotation required by the container?**
3. **Does the container provide the corresponding implementation and lifecycle?**

Solving question 1 does not automatically solve questions 2 and 3.

### 4.4. Avoid mixing container APIs with app dependencies arbitrarily

Placing multiple copies of `jakarta.servlet-api` or servlet container implementation JARs into `WEB-INF/lib` can create classloader or version conflicts. Let the container own its API/provider according to its contract, unless a packaging mode (such as an embedded server) has specific rules.

## 5. When Can Pure-Java `javax` Libraries Still Be Used?

Not every older library mentioning `javax` is incompatible.

### 5.1. Libraries using stable Java SE APIs

For example, a library using:

```java
import javax.sql.DataSource;
import javax.crypto.Cipher;
import javax.net.ssl.SSLContext;
import javax.xml.parsers.DocumentBuilderFactory;
```

These packages belong to Java SE and do not change to Jakarta simply because the application server moved to Jakarta EE. Even if the library is old, it can continue running if its bytecode, JDK APIs, providers, and other dependencies are compatible.

### 5.2. Libraries not crossing container contracts

A pure Java processing library such as data structures, algorithms, or standalone HTTP connectivity may run inside a Jakarta container even if written in the Java EE era, provided it carries no runtime requirement on `javax.*` EE APIs.

If a library contains Javax APIs in an unused code branch, it may still run, yet carries risk of class loading via reflection, static initializers, service providers, or rare execution paths. Check dependencies and real integration behavior.

### 5.3. Libraries at boundaries decoupled from the application

A legacy Java EE service running independently can communicate with a new Jakarta application over compatible HTTP/JSON, SOAP contracts, or message protocols. When not directly exchanging Java objects implementing `javax.servlet.*`/`jakarta.servlet.*`, wire-protocol boundaries allow incremental system upgrades.

However, JSON, XML, WSDL, message schemas, authentication, and transaction boundaries must still be explicitly managed.

## 6. Seeing a `jakarta.*` Artifact Does Not Mean the Namespace Switched

An easily confusing point in dependency management: **artifact coordinates and Java packages are not the same thing**.

During the Jakarta EE 8 era, there were artifacts with `jakarta.*` group coordinates whose **classes still declared `javax.*`**. For example, the Jakarta Servlet 4.0 and Jakarta Persistence 2.2 lines remained tied to the `javax` generation.

| Prior-Generation API | `javax` Phase | `jakarta` Transition Phase |
|---|---|---|
| Servlet | Java EE 8 / Jakarta Servlet 4.0 | Jakarta Servlet 5.0+ |
| Persistence | JPA/Jakarta Persistence 2.2 | Jakarta Persistence 3.0+ |
| REST/JAX-RS | JAX-RS/Jakarta REST 2.1 | Jakarta REST 3.0+ |
| Bean Validation | Jakarta Bean Validation 2.0 | Jakarta Validation 3.0+ |
| CDI | CDI/Jakarta CDI 2.0 | Jakarta CDI 3.0+ |

Therefore, **do not determine the namespace by `groupId` or `artifactId`**. Inspect the spec version and actual class files inside the JAR.

Quick check:

```bash
jar tf jakarta.servlet-api-6.0.0.jar
```

Look for the path:

```text
jakarta/servlet/Filter.class
```

For legacy artifacts:

```text
javax/servlet/Filter.class
```

Conclude which namespace an artifact belongs to only after verifying the class paths inside the JAR.

## 7. Common Runtime Errors

### 7.1. `NoClassDefFoundError` for Javax types

For example:

```text
java.lang.NoClassDefFoundError:
  javax/servlet/Filter
```

Can happen when the application or a dependency still references Javax Servlet while the runtime only provides Jakarta Servlet. Find **which artifact contains that reference**, rather than merely adding the Javax API JAR to silence the error.

If you add the Javax JAR while the runtime lacks a contract-compliant implementation, the error may shift into another failure when the container instantiates or registers the filter.

### 7.2. `ClassCastException`

Logical example:

```text
Cannot cast com.example.LegacyFilter
to jakarta.servlet.Filter
```

If the old class only implements `javax.servlet.Filter`, casting to the Jakarta interface fails. This error reflects distinct type identities, not missing `doFilter` methods with similar names.

### 7.3. `NoSuchMethodError`

A method taking `javax.servlet.ServletContext` differs from a method taking `jakarta.servlet.ServletContext`, as seen in method descriptors. A library compiled against Javax APIs when runtime only has a Jakarta replacement library can hit a linkage error.

### 7.4. `AbstractMethodError`

Can appear when runtime invokes a method/interface contract that a compiled implementation does not provide with the exact descriptor and types. This is a form of binary incompatibility requiring analysis of class files and the dependency graph, not a simple source compilation issue.

### 7.5. `ClassNotFoundException` in reflection

Frameworks may look up class names via strings:

```java
Class.forName("javax.persistence.Entity");
```

If the Javax API does not exist, the lookup fails. Using binary transformation tools that rewrite class references without rewriting all configuration/reflection strings can leave this error behind.

### 7.6. CDI/annotations not recognized

A class with `javax.inject.Inject` or `javax.enterprise.context.ApplicationScoped` may not be recognized as the corresponding annotation by a Jakarta container without a specific compatibility mechanism.

The outcome may be missing injection, beans not being created, or deployment failure. Upgrade the entire DI integration/provider to match the container version.

### 7.7. Provider or `ServiceLoader` errors

A dependency has metadata:

```text
META-INF/services/javax.some.Service
```

while the new API searches for providers under:

```text
META-INF/services/jakarta.some.Service
```

No provider may be found, or the provider class may not implement the new interface properly. Replacing `.class` files may not suffice if service descriptors and metadata were not converted.

The names above only illustrate path structure; actual service names depend on the spec/provider.

## 8. JPA/Hibernate: Entity Annotations and Providers Must Share the Same Generation

JPA is a classic example where code can compile yet go unrecognized by the provider.

### 8.1. Javax Entity

```java
import javax.persistence.Entity;
import javax.persistence.Id;

@Entity
public class Customer {
    @Id
    private Long id;
}
```

### 8.2. Jakarta Entity

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
public class Customer {
    @Id
    private Long id;
}
```

A Jakarta Persistence provider expects Jakarta annotations. If an entity still carries Javax annotations, the provider may not treat the class as a managed entity and may raise mapping/runtime errors.

### 8.3. Not just changing annotations

JPA migration usually also includes:

- `EntityManager`, `EntityManagerFactory`, `Persistence`, `TypedQuery`, and API interfaces.
- `persistence.xml`, schema URI/namespace, version, and provider class.
- Properties prefixed with `javax.persistence.*` converted per the Jakarta spec where applicable.
- Hibernate/JPA provider, transaction integration, and bytecode enhancers.
- Entity listeners, converters, validation integration, and CDI injection.
- Criteria API, metamodel generators, annotation processors.
- Database driver/JDBC: `javax.sql.*` remains a Java SE API and does not change to a Jakarta namespace.

If using Hibernate, pick the exact version/variant supporting Jakarta Persistence; do not mechanically conclude that all Hibernate 5 releases support only Javax or all Hibernate 6 releases configure identically. Base choices on the concrete artifact and framework support matrix.

### 8.4. Do not package two JPA providers arbitrarily

Including both Javax/Jakarta JPA APIs and two providers can lead to classpath conflicts, persistence unit discovery errors, or transaction integration issues. A Jakarta container already provides certain services; applications should follow the container's or framework's provider management model rather than bundling every API and implementation themselves.

## 9. REST/JAX-RS: Resources and Providers Need APIs in the Same Namespace

Legacy REST endpoint:

```java
import javax.ws.rs.GET;
import javax.ws.rs.Path;
import javax.ws.rs.Produces;

@Path("/health")
public class HealthResource {
    @GET
    @Produces("text/plain")
    public String status() {
        return "OK";
    }
}
```

Jakarta REST:

```java
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;

@Path("/health")
public class HealthResource {
    @GET
    @Produces("text/plain")
    public String status() {
        return "OK";
    }
}
```

It is not only controllers/resources that must migrate. Providers such as `ContainerRequestFilter`, `MessageBodyReader`, `ExceptionMapper`, `Application`, and the JAX-RS runtime implementation also belong to the new contract.

An old JAX-RS provider JAR implementing only `javax.ws.rs.ext.MessageBodyReader` does not automatically become a `jakarta.ws.rs.ext.MessageBodyReader` provider, even if the JSON conversion logic is identical.

If an API client and server communicate over HTTP/JSON, a Javax client and a Jakarta server **can** interoperate at the wire protocol level if endpoints, authentication, media types, and payload contracts are compatible. However, if they share a binary Java extension interface directly, type namespaces must match.

## 10. Bean Validation: Constraint Annotations and Validators

A legacy model library has:

```java
import javax.validation.constraints.NotNull;

public class OrderInput {
    @NotNull
    private String customerId;
}
```

Model migrated to Jakarta:

```java
import jakarta.validation.constraints.NotNull;

public class OrderInput {
    @NotNull
    private String customerId;
}
```

A Jakarta validator engine looks for annotations, `ConstraintValidator`, and providers under the Jakarta Validation contract. Leaving Javax annotations on DTOs can cause validation to be skipped silently or cause integration errors depending on the framework.

Check as well:

- Custom constraint annotations.
- `ConstraintValidator` implementations.
- `Validation.buildDefaultValidatorFactory()` and bootstrap providers.
- Hibernate Validator or another implementation in its Jakarta version.
- CDI integration and JPA validation hooks.
- Method validation on controllers/services.
- Message bundles and XML validation mappings.

**Missing validation can cause silent business logic bugs**, unlike an immediate startup crash. That is why migration also needs negative tests (invalid inputs must be rejected).

## 11. Spring Framework and Spring Boot: Same Namespace Change, Broader Scope

Some representative milestones:

| Ecosystem | Generation Level | Servlet/EE Integration |
|---|---|---|
| Spring Framework 5.x | Prior generation | Primarily uses `javax` for Servlet and corresponding EE integrations |
| Spring Framework 6.x | New generation | Moved to Jakarta EE APIs |
| Spring Boot 2.x | Uses Spring Framework 5 | Primarily within the `javax` ecosystem |
| Spring Boot 3.x | Uses Spring Framework 6 | Requires the Jakarta ecosystem |

A Spring Boot 2 application cannot simply switch containers from Tomcat 9 to Tomcat 10 and expect all servlet filters and framework integrations to be compatible automatically.

Similarly, upgrading to Spring Boot 3 may require changing:

- Servlet API imports in controllers/filters/listeners.
- JPA/Validation annotations and providers.
- Servlet container/embedded server versions.
- Corresponding security frameworks/filter chains.
- OpenAPI/documentation libraries using Javax annotations.
- Monitoring, tracing, serialization, servlet adapters, and framework starters.
- Custom `HandlerInterceptor` or servlet-level integrations where type signatures are involved.

Do not arbitrarily pin Spring Framework core or Servlet API versions outside the Spring Boot BOM/starters without understanding the support matrix. Framework BOMs normally coordinate dependencies along one API generation.

## 12. Jakarta Transactions and the Java SE `javax.transaction.xa` Case

This transition has a trap:

- Many Jakarta Transactions APIs moved from `javax.transaction.*` to `jakarta.transaction.*`.
- However, `javax.transaction.xa.*` is part of Java SE and **does not move to `jakarta.transaction.xa.*`** under the same rule.

If a migration tool replaces every `javax.transaction` string with `jakarta.transaction` without distinguishing packages, source code can break immediately in XA interfaces.

This also affects transaction managers, JTA integration, JDBC resources, and container-managed transactions. When upgrading frameworks, verify drivers, XA providers, and transaction coordinators as well.

## 13. JAXB, JAX-WS, XML, and SOAP

Some legacy Java EE libraries use JAXB/JAX-WS:

```java
import javax.xml.bind.JAXBContext;
import javax.xml.ws.Service;
```

Corresponding Jakarta generation:

```java
import jakarta.xml.bind.JAXBContext;
import jakarta.xml.ws.Service;
```

However, **`javax.xml.parsers.DocumentBuilderFactory` and `javax.xml.transform.TransformerFactory` remain part of Java SE**. Do not bulk-replace `javax.xml.*` with `jakarta.xml.*`.

### 13.1. Upgrading the JDK and switching to Jakarta are two separate problems

JAXB and JAX-WS used to ship with the JDK in older releases but were removed from the JDK starting in Java 11. An application moving from Java 8 to Java 11 can hit missing JAXB/JAX-WS class errors **even when still running on a Javax container**.

The fix may be adding the exact dependencies matching the Javax or Jakarta generation the application is using. Do not equate "API removed from the JDK" with "API changed namespace".

### 13.2. XML/WSDL compatibility at the wire contract

A SOAP service implemented with a Javax stack and a client implemented with a Jakarta stack can interoperate if WSDL, XML schemas, bindings, WS-* policies, and security are compatible. However, generated Java stubs, provider internals, and JAXB annotations on each side must belong to their respective stack.

Regenerate client/server code from WSDL using tooling aligned with the runtime, rather than copying Javax generated classes into a Jakarta application unchecked.

## 14. How to Check Whether Legacy JARs Still Depend on `javax`

### 14.1. Listing classes with `jar`

```bash
jar tf legacy-library.jar
```

Look for signs of Javax classes if the artifact is an API JAR:

```bash
jar tf legacy-library.jar | grep '^javax/'
```

However, this only finds **classes packaged inside the JAR**. A library can reference `javax.servlet.Filter` without containing any Javax classes in that artifact itself.

### 14.2. Using `jdeps` to observe bytecode dependencies

For example:

```bash
jdeps --recursive \
  --class-path "lib/*" \
  legacy-library.jar
```

Output can show which classes/packages the library references. For missing dependencies, supply the appropriate analysis classpath to resolve references.

Limitation: `jdeps` analyzes static references and **cannot prove the absence** of string-based reflection, ServiceLoader, XML descriptors, or dynamically generated classes.

### 14.3. Using `javap` to inspect descriptors

Example with an extension class:

```bash
javap -classpath legacy-library.jar \
  -s com.example.integration.LegacyExtension
```

If you see:

```text
(Ljavax/servlet/ServletContext;)V
```

then the binary contract still references Javax Servlet, regardless of artifact filename or Maven group.

A proper Jakarta build will use the corresponding type:

```text
(Ljakarta/servlet/ServletContext;)V
```

### 14.4. Inspecting metadata outside class descriptors

Remaining traces may reside in:

- `META-INF/services/...` and service provider configurations.
- `web.xml`, `web-fragment.xml`, taglib descriptors.
- `persistence.xml`, `beans.xml`, `validation.xml`.
- JSP taglibs/JSTL imports and expression-language integrations.
- XML mapping/ORM descriptors or serializer configurations.
- String literals in code using `Class.forName("javax...")`.
- Annotation processors, generated sources, and codegen templates.
- OSGi bundle manifests, Automatic-Module-Name, or framework plugin metadata.

Therefore, changing imports and getting a passing build is only part of the migration process.

## 15. Maven: Checking Both Dependency Families

A Maven project can pull in both Javax and Jakarta versions simultaneously through transitive branches.

Inspect the dependency graph:

```bash
mvn dependency:tree
```

Narrow the search by artifact when needed:

```bash
mvn dependency:tree -Dincludes=javax.servlet:javax.servlet-api
mvn dependency:tree -Dincludes=jakarta.servlet:jakarta.servlet-api
```

Depending on the platform, also search for `javax.persistence`, `jakarta.persistence`, `javax.validation`, `jakarta.validation`, JAX-RS/REST, and corresponding runtime implementations.

### 15.1. Two API JARs do not necessarily collide on class names

Javax and Jakarta Servlet APIs sit under two different packages, so this is not strictly a duplicate FQCN in the traditional classpath sense. However, **it is a sign of mixing API generations at boundaries**.

Two different versions of the Jakarta Servlet API both providing `jakarta.servlet.Filter` can indeed be a duplicate FQCN or version collision. Classify the specific issue carefully.

### 15.2. When to use exclusions?

For example, if an old SDK pulls `javax.servlet-api` into a Jakarta WAR when that dependency is unneeded at runtime, you can consider excluding it on that branch. However, exclusion does not convert code inside the SDK from Javax to Jakarta.

If the SDK still has compiled references to `javax.servlet.Filter`, removing the API JAR can expose errors faster, helping pinpoint which dependency needs replacing or upgrading.

Do not blindly exclude all dependencies named `javax.*`; some are Java SE or are still needed by unmigrated parts of the system.

### 15.3. BOM/framework-managed versions

With Spring Boot 3 or Jakarta EE platforms, rely on the BOM or recommended dependency catalog of the framework/container whenever possible. Overriding a single provider back to the Javax generation can break integration between JPA, Validation, CDI, or Servlet even when the API JAR is Jakarta.

Align the API level, provider implementation, container, and Java runtime.

## 16. Gradle: Inspecting `compileClasspath` and `runtimeClasspath`

Gradle may resolve compilation and runtime differently.

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
```

Focus on a single API:

```bash
./gradlew dependencyInsight \
  --dependency jakarta.servlet-api \
  --configuration runtimeClasspath
```

In a WAR deployed into a container, the Servlet API is usually needed only on the compile classpath:

```groovy
dependencies {
    compileOnly 'jakarta.servlet:jakarta.servlet-api:6.0.0'
}
```

If using a Spring Boot embedded container, follow Boot starter dependency conventions; do not apply `compileOnly` mechanically because the servlet implementation must be present at runtime in a standalone application.

### 16.1. A resolved dependency is not necessarily what gets deployed

A WAR may receive extra JARs from a custom packaging task. A Docker image may contain an application server with bundled APIs of another version, or carry legacy libraries in a shared directory.

Therefore, inspect **both the resolved graph and the contents of the final WAR/JAR/runtime image**. The build tool does not control the application server's entire classloader unless deployment packaging is explicitly designed for it.

### 16.2. Compiler targets do not resolve namespaces

`sourceCompatibility`, `targetCompatibility`, or `options.release` only govern Java source/bytecode/Java SE API levels. They do not turn `javax.servlet.Filter` into `jakarta.servlet.Filter`.

You can compile a Javax library with JDK 17 and it remains a Javax library. Conversely, a Javax-supporting container can run on a newer JDK; **JDK version and Jakarta API generation are two independent axes of choice**.

## 17. Three Main Migration Strategies

### 17.1. Strategy A: Upgrade the library to an official Jakarta release

**Top priority** when the publisher provides a Jakarta-supported release.

Workflow:

1. Identify which classes of the SDK/library reference Javax EE APIs.
2. Find the official Jakarta version/variant.
3. Review JDK, framework/container, and API level requirements of the new library.
4. Upgrade accompanying dependencies (JPA provider, validation engine, REST implementation, servlet integration).
5. Update imports/descriptors/annotations in the application.
6. Build and deploy using the target Jakarta container.
7. Run integration tests on real endpoints, transactions, validation, and lifecycles.

Advantage: vendor-maintained, low reliance on bytecode transformation, less self-maintenance overhead. However, a major version upgrade may bring non-namespace API/semantic breaking changes, requiring migration guides and testing.

### 17.2. Strategy B: Migrate source and recompile

If you own the library's source:

1. Choose the target Jakarta API level/container.
2. Controlledly convert relevant Java EE imports from `javax.*` to `jakarta.*`.
3. Keep `javax.*` belonging to Java SE unchanged.
4. Update API and implementation dependencies.
5. Update XML descriptors, annotations, provider metadata, and reflection strings.
6. Recompile, run tests, and release a new artifact version.

For example:

```diff
-import javax.servlet.Filter;
-import javax.servlet.ServletRequest;
-import javax.servlet.ServletResponse;
+import jakarta.servlet.Filter;
+import jakarta.servlet.ServletRequest;
+import jakarta.servlet.ServletResponse;
```

At the same time, update method signatures using these types in public APIs.

This is usually a more sustainable solution for internal libraries because the source can be reviewed, fixed semantically, and maintained.

### 17.3. Strategy C: Bytecode/namespace transformation as a bridge

When source is unavailable or the publisher has not yet provided a Jakarta release, you can evaluate artifact conversion tools such as:

- **Apache Tomcat Jakarta EE Migration Tool**: helps convert certain Java EE 8 applications from the Javax namespace to Jakarta for appropriate environments.
- **Eclipse Transformer**: converts namespaces and metadata according to configured rules/tool versions.

Transformer tools can rewrite class references and some resources/metadata, but you must verify **the exact conversion scope**. Not every framework extension, native component, dynamic reflection string, or serialization file can be fully transformed.

Do not invoke a bytecode transformer once and assume the binary is compatible: inspect the output and run full integration tests.

## 18. Limitations of Bytecode Transformation

### 18.1. Reflection and string-based class names

For example:

```java
Class<?> type = Class.forName("javax.servlet.http.HttpServlet");
```

If the transformer does not rewrite the relevant string, runtime still requests the Javax class. Some transformers have rules for strings/resources, though specific capabilities must be verified for the exact configuration and tool version.

### 18.2. Serialized data and external contracts

If the system stores data using Javax class names or generated proxies inside serialized payloads, changing the binary namespace can break reading legacy data.

Do not apply transformers onto production data formats without designing data versioning and migration.

### 18.3. SPI/service descriptors

A provider may declare a service file under the Javax interface name. Rewriting class bytecode without updating `META-INF/services` leaves `ServiceLoader` unable to discover the provider as expected.

### 18.4. Annotations and XML descriptors

Frameworks can read annotations, XML namespaces, deployment descriptors, or generated proxies. Verify packages/namespaces in:

```text
WEB-INF/web.xml
META-INF/persistence.xml
META-INF/beans.xml
META-INF/services/*
WEB-INF/*.tld
```

Do not mechanically alter XML namespace URIs without knowing the container's specifications/schemas.

### 18.5. JAR signing and supply-chain security

Transforming bytecode/resources alters JAR contents and can invalidate existing digital signatures. The new artifact requires new provenance, checksums, signing, and verification workflows.

Do not put transformed JARs from unverified sources into production merely because they start up.

### 18.6. Remaining dependencies still on Javax

A transformer applied to one JAR does not convert other JARs automatically. If library A is converted to Jakarta while library B still accepts `javax.servlet.ServletRequest` in its public API, calls between A and B still mismatch.

Handle **the entire dependency graph of the affected application area** or place clear adapter boundaries.

## 19. Why Cannot an Adapter Just Be a Cast?

A common mistake is trying to cast:

```java
// No direct subtype relationship between the two interfaces:
jakarta.servlet.Filter f =
        (jakarta.servlet.Filter) legacyJavaxFilter;
```

Casting does not create a new `implements` relationship. If the object only implements the Javax interface, the cast can fail with `ClassCastException`.

### 19.1. A proper adapter is a separate implementation

In principle, an adapter must **implement the Jakarta interface** and use actual Jakarta APIs/objects on the container side:

```java
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import java.io.IOException;

public final class ModernFilterAdapter implements Filter {
    private final LegacyAuditLogic delegate;

    public ModernFilterAdapter(LegacyAuditLogic delegate) {
        this.delegate = delegate;
    }

    @Override
    public void doFilter(
            ServletRequest req,
            ServletResponse res,
            FilterChain chain)
            throws IOException, ServletException {
        delegate.recordRequest(req.getRemoteAddr());
        chain.doFilter(req, res);
    }
}
```

Here, `LegacyAuditLogic` is **business logic independent of Servlet APIs** owned by the application; the adapter passes the required data into a model independent of `javax` or `jakarta`. This is the right approach when you have control over the architecture.

### 19.2. A full bridge between old and new Servlet APIs is very complex

If a legacy library requires a full `javax.servlet.ServletRequest` object, building an adapter from `jakarta.servlet.ServletRequest` is not just writing a single method. It drags in many interfaces/methods, session/context semantics, async processing, lifecycles, request/response wrappers, listeners, and potential API spec changes.

Therefore, **do not write a full Servlet API bridge yourself when only one business capability is needed**. It is better to upgrade the SDK, migrate source, or decouple logic from the Servlet boundary.

### 19.3. Boundaries over HTTP or messages are another option

If a Javax library cannot be migrated immediately, you can temporarily keep it in **a separate service/container supporting Javax**, and communicate with the Jakarta application over HTTP or neutral message schemas.

This supports incremental migration, yet adds deployment overhead, latency, security, observability, and wire-protocol compatibility costs. Do not treat it as a free solution.

## 20. Can Classloader Isolation Solve This?

Classloader isolation can allow two libraries with separate dependencies to coexist in one process, but it **does not automatically turn a Javax type into a Jakarta type**.

For example:

```text
Parent/container classloader:
  jakarta.servlet.*

Plugin classloader:
  javax.servlet.*
  legacy-plugin.jar
```

A plugin can load its own Javax classes, yet for the container to invoke it as a `jakarta.servlet.Filter`, an adapter implementing the Jakarta contract is still required.

Having the same package names in two classloaders also risks class identity/cast conflicts. For containers capable of running multiple EE environments side by side, follow the product's official **deployment environment and classloading contract**.

Do not change classpath order or enable parent-last classloading merely to "force" a Jakarta container to use a Javax Filter; this is a type contract issue, not simply search order.

## 21. Practical Options When a Library Has No Jakarta Version Yet

| Situation | Preferred Direction | Limitations to Note |
|---|---|---|
| SDK has an official Jakarta release | Upgrade to vendor-supported version/variant | May include non-namespace breaking changes |
| Internal library with available source | Migrate source, update API/imports/metadata, recompile | Needs contract and integration tests |
| Small library holding mostly business logic | Decouple Java SE logic from servlet/JPA boundaries, write new adapter | Requires changing entrypoints and lifecycles |
| Third-party JAR without source | Try a transformer with controlled rules | Reflection, resources, serialization, and signing may break |
| Legacy product cannot upgrade right away | Keep in a separate Javax container, integrate over HTTP/messaging | Increases operations and cross-service API management |
| Container supports multiple EE environments | Use the deployment environment of the right generation | Depends on specific product/config; never assume by default |
| App still on Javax without Jakarta requirement | Temporarily keep on a security-supported Javax container | Requires evaluating support lifecycle and operational risk |

Choosing a migration direction must be based on official library/container support and security requirements, not solely on compilation.

## 22. Investigation Workflow in a Real WAR/JAR

### Step 1 — Explicitly record 4 versions

Identify:

1. JDK/runtime version.
2. Servlet/Jakarta EE API generation.
3. Container/server version.
4. Framework and key integration libraries.

**Do not collapse this into a single sentence "we use Java 17".** Java 17 can run a Javax application on a Javax container, or a Jakarta application on a Jakarta container, depending on the support matrix.

### Step 2 — Identify the failing contract

Based on the exception:

```text
javax/servlet/Filter
jakarta/servlet/Filter
javax/persistence/Entity
jakarta/persistence/Entity
```

See which class requests the Javax type and which classes are supplied by the Jakarta container.

### Step 3 — Inspect the dependency graph

Maven:

```bash
mvn dependency:tree
```

Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Check both API JARs and implementations/providers; do not search for only a single package string.

### Step 4 — Inspect the deployed artifact

WAR example:

```bash
jar tf build/libs/app.war
```

Observe:

```text
WEB-INF/classes/
WEB-INF/lib/
WEB-INF/web.xml
```

Check whether old API JARs are packaged into the WAR. Check which SDKs still reference Javax EE. If using a Spring Boot executable JAR, inspect nested dependency JARs and embedded container versions instead of rigidly applying WAR rules.

### Step 5 — Analyze binary references

Use `jdeps` and `javap` with the appropriate classpath, searching for descriptors containing `Ljavax/...` or `Ljakarta/...`.

### Step 6 — Choose a migration path

Prefer official vendor Jakarta releases, followed by source migration, adapters, or controlled transformers; if impossible, isolate into a separate legacy service.

### Step 7 — Test every extension point

Do not merely load an HTML page. Test:

- Servlet/filter/listener lifecycles.
- REST endpoints and exception mappers.
- JPA entity scanning, CRUD, and transactions.
- Validation with invalid inputs.
- CDI dependency injection.
- Authentication/authorization/sessions.
- Messaging/JMS and SOAP if used.
- Reflection, service providers, and generated code.

### Step 8 — Deploy the artifact into the target container

Run smoke/integration tests on the exact container version, runtime image, classloaders, and packaging mode as production.

### Step 9 — Pin dependencies and record evidence

Save the BOM/platform, dependency tree, artifact checksums, vendor/runtime versions, and test results. This helps catch regressions if a transitive dependency slips back to Javax.

## 23. Comprehensive Example: Javax WAR to Tomcat 10.1

Suppose a legacy Java EE application runs on Tomcat 9:

```text
inventory.war
  WEB-INF/classes/com/example/web/InventoryServlet.class
  WEB-INF/lib/legacy-auth-filter.jar
```

Where:

- `InventoryServlet` extends `javax.servlet.http.HttpServlet`.
- `legacy-auth-filter.jar` implements `javax.servlet.Filter`.
- Several validation annotations use `javax.validation.*`.

When moving the WAR as-is to Tomcat 10.1:

1. The container provides Jakarta Servlet 6.0.
2. The old Servlet/Filter still references Javax types.
3. Adding `jakarta.servlet-api.jar` to the WAR does not turn them into Jakarta types.
4. Deployment may fail on class loading/type contracts, or the application fails to register the filter as expected.
5. Validation may stop executing if only part of the stack migrated.

**Preferred plan:**

1. Upgrade `legacy-auth-filter` to a Jakarta Servlet release if available.
2. Migrate Servlet source and internal listeners/filters to `jakarta.servlet.*`.
3. Migrate Validation annotations and providers to the corresponding Jakarta ones.
4. Update `web.xml`, taglibs/JSP metadata, and related resources.
5. Select the Servlet API version matching Tomcat 10.1, provided by the container.
6. Build a new WAR and inspect the JARs inside `WEB-INF/lib`.
7. Deploy on Tomcat 10.1 and test endpoints/authorization/validation/sessions.

If `legacy-auth-filter` has no Jakarta version and cannot be migrated, consider a business adapter or tested transformation tooling; if that falls short, keep the Javax component isolated on a compatible runtime during a transition period.

## 24. Common Misconceptions

### "Jakarta EE 8 already moved everything to `jakarta.*`"

**False.** Jakarta EE 8 still uses the Javax namespace for the corresponding core APIs. The major shift to the Jakarta namespace occurred in Jakarta EE 9.

### "Just replace `javax` with `jakarta` in imports and you are done"

**Insufficient.** You must inspect dependencies, providers, XML/metadata, annotation processors, resource files, reflection, compiled JARs, and API signatures.

### "Adding both API JARs makes the application compatible with both"

**False for container contracts.** The two type families are independent; a Jakarta container requires implementations of Jakarta interfaces.

### "Maven group `jakarta.*` guarantees `jakarta.*` inside"

**Inaccurate.** Jakarta EE 8-era artifacts can have Jakarta coordinates while their classes still live under `javax.*`.

### "Upgrading to JDK 17 automatically switches a Javax app to Jakarta"

**False.** JDK version and EE namespace are two independent axes; `--release` does not rewrite dependency packages either.

### "Every `javax.*` must change"

**False.** Many Java SE APIs such as `javax.sql`, `javax.crypto`, and `javax.xml.parsers` stay unchanged.

### "Bytecode transformers always handle everything"

**False.** Reflection strings, metadata, JSP/TLD, service files, serialization, provider compatibility, and JAR signatures may need additional handling.

### "Isolating classloaders lets you cast a Javax Filter to a Jakarta Filter"

**False.** Classloader isolation does not establish a subtype relationship between two differently named interfaces.

### "Tomcat 10 and Tomcat 9 differ only in version numbers"

**False.** Tomcat 10 belongs to the Jakarta Servlet generation with namespace changes, aside from other spec/Java version changes.

## 25. Checklist Before Confirming Compatibility

- [ ] Distinguished Jakarta EE 8 (`javax`) and Jakarta EE 9+ (`jakarta`).
- [ ] Identified runtime JDK, container, Servlet API level, and framework version.
- [ ] Inventoried which libraries still reference Javax EE APIs.
- [ ] Kept `javax` packages belonging to Java SE untouched.
- [ ] Inspected actual JARs rather than relying on Maven group names.
- [ ] Checked bytecode descriptors with `javap` or equivalent analysis.
- [ ] Inspected the Maven/Gradle dependency graph under the exact runtime configuration.
- [ ] Removed inappropriate API JARs from the WAR when the container provides the corresponding API.
- [ ] Migrated Servlets/filters/listeners and other extension points to the new API generation.
- [ ] Updated JPA entities, persistence providers, and configurations where relevant.
- [ ] Updated REST resources/providers and Validation annotations/engines.
- [ ] Checked CDI/JMS/SOAP/JAXB/Jakarta Transactions if the application uses them.
- [ ] Checked metadata, service files, XML descriptors, and reflection strings.
- [ ] Verified transformers/adapters, if any, with integration tests.
- [ ] Tested the actual deployed WAR/JAR on the target container.
- [ ] Defined a dedicated roadmap for Javax libraries lacking a Jakarta release yet.
- [ ] Saved dependency graphs, container versions, artifacts, and regression test results.

## 26. Conclusion

Compatibility between legacy Javax libraries and Jakarta containers cannot be evaluated merely by whether source code compiles. Starting in Jakarta EE 9, APIs included in the namespace transition carry **new type identity**: `javax.servlet.Filter` is not `jakarta.servlet.Filter`, Javax annotations are not automatically equivalent to Jakarta annotations, and JVM method descriptors change with the package. A Jakarta container does not automatically provide a bridge for every legacy Javax library.

A sustainable migration approach is to **inventory APIs accurately by generation, preserve Java SE `javax.*` packages, upgrade libraries/providers to supported Jakarta releases, migrate source and metadata, and then test the real artifact on the target container**. For libraries that cannot upgrade right away, business adapters, verified transformers, or isolated legacy runtimes are transition options requiring control. The ultimate goal is not merely avoiding `ClassNotFoundException`, but ensuring the entire servlet, persistence, validation, injection, and integration lifecycle operates properly within one consistent API ecosystem.
