# Identifying javax to jakarta Changes in Legacy Code

> **Spring Boot Fundamentals · Versioning and Extension**  
> When reading an older Spring Boot project, you may encounter imports like `javax.servlet.*`, `javax.persistence.*`, or `javax.validation.*`. In newer projects, the corresponding APIs usually live under the `jakarta.*` namespace. This is the result of transitioning Java EE to Jakarta EE after platform stewardship moved to the Eclipse Foundation. **The namespace change is a compatibility change at the API and bytecode level**, not a simple package rename. To identify and handle legacy code properly, you must know which APIs moved, which remain in Java SE, which Spring Boot/container versions are in use, and which dependencies still rely on the old namespace.

## 1. Why do both javax and jakarta exist?

For many years, enterprise Java APIs were developed under Java Platform, Enterprise Edition (Java EE). Familiar APIs included Servlet, JPA, Bean Validation, JAX-RS, JMS, and many others. They used the `javax.*` namespace.

After Java EE was transferred to the Eclipse Foundation, the platform continued under the name **Jakarta EE**. Due to trademark and `javax` namespace usage constraints, Jakarta EE 9 performed a major change: APIs belonging to the Jakarta platform moved from `javax.*` to `jakarta.*`.

Examples:

- `javax.servlet.Filter` became `jakarta.servlet.Filter`.
- `javax.persistence.Entity` became `jakarta.persistence.Entity`.
- `javax.validation.Valid` became `jakarta.validation.Valid`.

This does not mean every package starting with `javax` changed. Many `javax` packages are Java SE APIs and still exist in the JDK.

### 1.1. Key transition milestones

| Generation | Common platform | Common enterprise namespace |
| --- | --- | --- |
| Java EE 8 | Java EE 8 APIs | `javax.*` |
| Jakarta EE 8 | Jakarta EE 8, Java EE 8 namespace-compatible | `javax.*` |
| Jakarta EE 9 | Namespace transition step | `jakarta.*` |
| Jakarta EE 10 | Newer Jakarta EE API versions | `jakarta.*` |
| Spring Framework 5 / Spring Boot 2 | Spring generation before the major migration | Primarily integrates Java EE/`javax` APIs |
| Spring Framework 6 / Spring Boot 3 | Spring generation migrated to Jakarta | `jakarta` APIs for corresponding enterprise integrations |

Jakarta EE 8 still uses `javax` for compatibility with Java EE 8. The package change started in Jakarta EE 9; seeing the word "Jakarta" in a platform name does not guarantee imports are already `jakarta`.

### 1.2. Why couldn't the old package name be kept for compatibility?

The namespace is part of the binary class name. The JVM does not treat:

```text
javax.servlet.Filter
jakarta.servlet.Filter
```

as the same type. Two classes have different binary names, different method signatures, and cannot directly substitute for each other.

A class compiled to implement `javax.servlet.Filter` does not automatically become an implementation of `jakarta.servlet.Filter` just because the two interfaces share method names.

### 1.3. This is a platform change, not just a Spring change

Spring Framework 6 moved its corresponding integrations to Jakarta APIs. Spring Boot 3 is based on Spring Framework 6 and requires Java 17 or higher. Consequently, upgrading an application from Boot 2 to Boot 3 typically entails upgrading dependencies, containers, ORM, validation providers, and related libraries.

Do not treat this as an isolated import fix.

## 2. Quickly identifying legacy code in a project

When opening code or reading a stack trace, identify the package before deciding what to change.

### 2.1. Common imports in legacy Java EE applications

```java
import javax.servlet.Filter;
import javax.servlet.http.HttpServletRequest;
import javax.persistence.Entity;
import javax.persistence.Id;
import javax.validation.Valid;
import javax.validation.constraints.NotBlank;
import javax.annotation.PostConstruct;
import javax.inject.Inject;
```

In Spring Boot 3 / Spring Framework 6 applications, the corresponding Jakarta APIs typically look like:

```java
import jakarta.servlet.Filter;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.annotation.PostConstruct;
import jakarta.inject.Inject;
```

Spring's own annotations remain in `org.springframework.*`, such as `@Autowired`, `@Component`, `@Service`, and `org.springframework.transaction.annotation.Transactional`. Do not change every annotation just because the project is upgrading to Boot 3.

### 2.2. Using source search to build an inventory

In a repository, you can locate legacy imports using ripgrep:

```bash
rg -n "import javax\\.(servlet|persistence|validation|annotation|inject|transaction|ws\\.rs|jms|mail|xml\\.bind)" .
```

The command above is an initial inventory step. It does not catch every case:

- Code may use fully qualified class names in annotations or strings.
- XML descriptors may declare legacy namespaces/schemas.
- `META-INF/services` files may contain legacy interface names.
- Generated sources may be regenerated from schemas.
- Dependency JARs may reference `javax` even when application source has zero `javax` imports.

You can search more broadly:

```bash
rg -n "javax\\." src pom.xml build.gradle build.gradle.kts
```

Broad search results must be categorized; **never bulk-replace all matches**.

### 2.3. Inspect the dependency graph, not just source

A project may not import `javax.servlet` directly while an older library still requires that API at runtime.

Maven:

```bash
./mvnw dependency:tree
```

Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

To locate a specific version:

```bash
./gradlew dependencyInsight --dependency servlet-api --configuration runtimeClasspath
```

Look for dependencies such as:

- Servlet API.
- JPA API and ORM provider.
- Bean Validation API/provider.
- JAXB/JAX-WS.
- JAX-RS implementation.
- JMS client.
- Security, SAML, SOAP, or container integration libraries.

A source file using `jakarta.persistence.Entity` can still fail if runtime contains an older-generation Hibernate or persistence API.

## 3. Not every javax moves to jakarta

This is the most important rule when updating legacy code: **only migrate APIs belonging to Java EE/Jakarta EE whose namespaces changed**.

Many APIs in the JDK keep the `javax` name.

### 3.1. Java SE packages that remain javax

| Package | Status |
| --- | --- |
| `javax.sql.DataSource` | Java SE/JDBC; remains `javax.sql` |
| `javax.crypto.*` | Java SE cryptography; remains `javax.crypto` |
| `javax.net.*` | Java SE networking; remains `javax.net` |
| `javax.naming.*` | Java Naming and Directory Interface; remains `javax.naming` |
| `javax.management.*` | Java Management Extensions; remains `javax.management` |
| `javax.security.auth.*` | Java SE security APIs; remains `javax.security.auth` |
| `javax.xml.parsers.*` | Java SE XML APIs; remains `javax.xml.parsers` |
| `javax.xml.transform.*` | Java SE XML transformation; remains `javax.xml.transform` |
| `javax.xml.validation.*` | Java SE XML validation; remains `javax.xml.validation` |
| `javax.xml.stream.*` | Java SE StAX; remains `javax.xml.stream` |
| `javax.annotation.processing.*` | Java compiler annotation processing API; remains `javax.annotation.processing` |
| `javax.lang.model.*` | Java compiler language model; remains `javax.lang.model` |
| `javax.transaction.xa.*` | XA APIs belonging to the Java SE module; remains `javax.transaction.xa` |

Example:

```java
import javax.sql.DataSource;
import javax.crypto.Cipher;
import javax.naming.InitialContext;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.annotation.processing.Processor;
```

These imports do not change to `jakarta` when upgrading to Spring Boot 3.

### 3.2. Enterprise packages that changed namespace

| Legacy API | New Jakarta API |
| --- | --- |
| `javax.servlet.*` | `jakarta.servlet.*` |
| `javax.persistence.*` | `jakarta.persistence.*` |
| `javax.validation.*` | `jakarta.validation.*` |
| `javax.annotation.*` (Common Annotations) | `jakarta.annotation.*` |
| `javax.inject.*` | `jakarta.inject.*` |
| `javax.transaction.*` (JTA APIs) | `jakarta.transaction.*` |
| `javax.ws.rs.*` | `jakarta.ws.rs.*` |
| `javax.jms.*` | `jakarta.jms.*` |
| `javax.websocket.*` | `jakarta.websocket.*` |
| `javax.faces.*` | `jakarta.faces.*` |
| `javax.enterprise.*` | `jakarta.enterprise.*` |
| `javax.batch.*` | `jakarta.batch.*` |
| `javax.resource.*` | `jakarta.resource.*` |
| `javax.xml.bind.*` | `jakarta.xml.bind.*` |
| `javax.xml.soap.*` | `jakarta.xml.soap.*` |
| `javax.mail.*` | `jakarta.mail.*` |
| `javax.activation.*` | `jakarta.activation.*` |
| `javax.json.*` | `jakarta.json.*` |

This table helps identify common API families. When upgrading a specific library, still verify the version and artifact coordinates of that library.

### 3.3. Easy-to-confuse exception: javax.transaction vs. javax.transaction.xa

Legacy JTA APIs include types like `javax.transaction.UserTransaction` and `javax.transaction.TransactionManager`; in Jakarta they moved to `jakarta.transaction.*`.

However, `javax.transaction.xa.XAResource` is a Java SE API and keeps the `javax.transaction.xa` package.

Example of valid code in a Jakarta application:

```java
import jakarta.transaction.UserTransaction;
import javax.transaction.xa.XAResource;
```

Do not indiscriminately replace the prefix `javax.transaction` with `jakarta.transaction` via a blind text replacement.

### 3.4. Easy-to-confuse exception: javax.annotation vs. javax.annotation.processing

`javax.annotation.PostConstruct` belongs to legacy Common Annotations and is replaced by `jakarta.annotation.PostConstruct` in the Jakarta ecosystem.

However, `javax.annotation.processing.Processor` belongs to the Java compiler API and remains unchanged.

Example:

```java
import jakarta.annotation.PostConstruct;
import javax.annotation.processing.ProcessingEnvironment;
```

Both imports can appear together in a Boot 3 application without conflict.

### 3.5. Easy-to-confuse exception: javax.xml

Not all of `javax.xml` moved to Jakarta.

`javax.xml.parsers`, `javax.xml.transform`, and several Java SE XML APIs remain unchanged. Enterprise APIs like JAXB and SAAJ changed namespaces:

```java
import jakarta.xml.bind.JAXBContext;
import jakarta.xml.soap.SOAPMessage;
import javax.xml.parsers.DocumentBuilderFactory;
```

Additionally, since Java 11, certain Java EE modules like JAXB/JAX-WS are no longer bundled in the JDK as in older Java versions. Missing classes may be caused by an undeclared dependency even before namespace migration.

## 4. Map of Spring Boot APIs commonly affected

When upgrading Spring Boot 2.x to 3.x, certain API families appear most often.

### 4.1. Servlet API

Before:

```java
import javax.servlet.Filter;
import javax.servlet.FilterChain;
import javax.servlet.ServletException;
import javax.servlet.ServletRequest;
import javax.servlet.ServletResponse;
```

After:

```java
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
```

Filter example:

```java
@Component
public class RequestTraceFilter implements Filter {

    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {

        chain.doFilter(request, response);
    }
}
```

Updating imports updates the method signatures once compatible dependencies are in place. However, if a third-party library still returns `javax.servlet.Filter`, it cannot be registered as `jakarta.servlet.Filter`.

### 4.2. JPA / Persistence

Before:

```java
import javax.persistence.Entity;
import javax.persistence.Id;
import javax.persistence.Table;
import javax.persistence.ManyToOne;
```

After:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.ManyToOne;
```

Entity example:

```java
@Entity
@Table(name = "orders")
public class OrderEntity {

    @Id
    private Long id;

    // ...
}
```

Hibernate 6, used in the Spring Boot 3 line, is based on Jakarta Persistence. An entity still annotated with `javax.persistence.Entity` is not the Jakarta Persistence annotation that Hibernate 6 looks for.

This can cause entities not to be recognized or mapping metadata not to be created as expected.

### 4.3. Bean Validation

Before:

```java
import javax.validation.Valid;
import javax.validation.constraints.NotBlank;
import javax.validation.constraints.NotNull;
```

After:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
```

Example:

```java
public record CreateCustomerRequest(
        @NotBlank String name,
        @NotNull @Email String email) {
}
```

If API types and the validation provider do not share the same namespace/version, constraints may not be detected as expected or the application may lack an appropriate provider.

### 4.4. Common Annotations

Before:

```java
import javax.annotation.PostConstruct;
import javax.annotation.PreDestroy;
import javax.annotation.Resource;
```

After:

```java
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import jakarta.annotation.Resource;
```

Example:

```java
@Component
public class CacheWarmup {

    @PostConstruct
    void initialize() {
        // Prepare cache after dependencies are injected.
    }

    @PreDestroy
    void shutdown() {
        // Release resources.
    }
}
```

In Spring, `@PostConstruct`/`@PreDestroy` remain supported lifecycle annotations via the corresponding Jakarta API. Do not confuse them with Spring callbacks such as `InitializingBean` or `DisposableBean`.

### 4.5. Dependency Injection annotations

Before:

```java
import javax.inject.Inject;
import javax.inject.Named;
```

After:

```java
import jakarta.inject.Inject;
import jakarta.inject.Named;
```

Spring also has its own annotations:

```java
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;
```

`@Autowired` does not turn into `@Inject` or vice versa just because of migration. These are two annotation sets with different origins; use the API supported by your codebase and framework version.

### 4.6. JTA transaction annotation vs. Spring transaction annotation

JTA:

```java
import jakarta.transaction.Transactional;
```

Spring:

```java
import org.springframework.transaction.annotation.Transactional;
```

Both share the same simple annotation name but are two distinct types with their own semantics and integrations. Spring transaction management can support multiple transaction annotations depending on configuration, but do not swap imports based on the short name without verifying which transaction model the code intends to use.

## 5. How do Spring Boot 2 and Spring Boot 3 differ?

A strong indicator when inspecting a codebase is the Spring Boot major version.

| Characteristic | Spring Boot 2.x | Spring Boot 3.x |
| --- | --- | --- |
| Spring Framework | 5.x | 6.x |
| Java baseline | 2.x line supports older Java baselines; depends on minor | Java 17 and above |
| Enterprise API namespace | Typically `javax` | Jakarta `jakarta` |
| Servlet ecosystem | Typically Servlet 4 / Tomcat 9 | Jakarta Servlet 6 / Tomcat 10.1 in matching default configurations |
| Persistence provider | Hibernate 5 line common | Hibernate 6 |
| Validation API | `javax.validation` | `jakarta.validation` |
| Migration effort | Legacy code can keep running in a compatible stack | Must align Jakarta APIs and libraries |

This table describes typical generations and does not replace the compatibility matrix of a specific minor release. Boot 2.x has many minor versions and may use individually upgraded dependencies; Boot 3.x also spans releases with varying server/provider versions.

### 5.1. Boot 2.7 is often the migration starting point

Many projects upgrading from Boot 2.5/2.6 to Boot 3 pass through Boot 2.7 first to address deprecations and prepare. This is not mandatory for every repository, but it is often a helpful strategy.

At the Boot 2.7 stage:

- Clean up deprecated Spring APIs.
- Update dependencies to supported versions.
- Remove legacy configurations that no longer apply.
- Verify the test suite and build reproducibility.
- Prepare Java 17 and compatible plugins/toolchains.

Only then perform the namespace migration and upgrade dependencies to the Jakarta generation.

### 5.2. Spring Framework 6 requires Java 17+

If source imports are switched to `jakarta` while CI still runs Java 11, the application will still fail before a Spring context is created. That is a runtime/compiler baseline error, not a namespace error.

Check:

```bash
java -version
./mvnw -version
./gradlew -version
```

Verify both the JDK running Maven/Gradle and the Java toolchain used for compiling and testing.

### 5.3. Embedded Tomcat must also be on the same generation

A Boot 3 application using Jakarta Servlet cannot be deployed directly onto Tomcat 9—which provides the `javax.servlet` Servlet API—as a Jakarta Servlet 6 application.

Common Tomcat generations:

| Tomcat | Servlet namespace/specification |
| --- | --- |
| Tomcat 9 | Java EE 8 / Servlet 4, `javax.servlet` |
| Tomcat 10.0 | Jakarta EE 9 / Servlet 5, `jakarta.servlet` |
| Tomcat 10.1 | Jakarta EE 10 / Servlet 6, `jakarta.servlet` |

Boot 3.x requires a container matching the Servlet generation supported by that release. For external WAR deployments, verify the actual server instead of relying only on the embedded server version in local builds.

## 6. Why are javax and jakarta binary incompatible?

The JVM uses binary names of classes/interfaces in descriptors, the constant pool, and method signatures.

Suppose a library was compiled with:

```java
public class LegacyFilter implements javax.servlet.Filter {
}
```

The new application expects:

```java
jakarta.servlet.Filter filter = obtainFilter();
```

There is no automatic conversion between the two interfaces. A class implementing `javax.servlet.Filter` does not implement `jakarta.servlet.Filter`.

### 6.1. Method signatures also change

Legacy Servlet filter:

```java
void doFilter(
        javax.servlet.ServletRequest request,
        javax.servlet.ServletResponse response,
        javax.servlet.FilterChain chain);
```

New Servlet filter:

```java
void doFilter(
        jakarta.servlet.ServletRequest request,
        jakarta.servlet.ServletResponse response,
        jakarta.servlet.FilterChain chain);
```

Although the method name and parameter count match, the descriptors differ because the parameter types differ.

### 6.2. Passing compilation does not prove runtime compatibility

A project may compile because both old and new API JARs exist on the compile classpath. However, the runtime container supplies only one namespace, causing linkage or cast errors.

Do not add both `javax.servlet-api` and `jakarta.servlet-api` to the same application and hope Spring picks the right one. Remove the old dependency or isolate the integration properly.

### 6.3. Legacy annotations are not recognized as new annotations

Example:

```java
@javax.persistence.Entity
public class CustomerEntity {
}
```

is not the same annotation as:

```java
@jakarta.persistence.Entity
public class CustomerEntity {
}
```

Hibernate 6 does not automatically interpret the old annotation as a Jakarta Persistence annotation. Having the same simple name `Entity` does not make them the same type.

### 6.4. Generic types, reflection, and service loading are also affected

Migration does not affect only imports in regular methods:

- Reflection code calling `getAnnotation` with the old type will not find the new annotation.
- Generic signatures and interface implementations may reference the old namespace.
- SPI service descriptors may declare old provider interface names.
- Proxies and generated bytecode may retain old method descriptors.
- XML mappings may point to old classes or schemas.

Therefore, migration must inspect source, generated artifacts, resources, and runtime dependencies.

## 7. Dependency coordinates: new imports need new API artifacts

A common mistake is updating source imports while leaving old-generation API dependency artifacts in place.

### 7.1. Servlet API example

Old:

```xml
<dependency>
    <groupId>javax.servlet</groupId>
    <artifactId>javax.servlet-api</artifactId>
    <scope>provided</scope>
</dependency>
```

New:

```xml
<dependency>
    <groupId>jakarta.servlet</groupId>
    <artifactId>jakarta.servlet-api</artifactId>
    <scope>provided</scope>
</dependency>
```

In a Spring Boot Web application, normally let Boot starters/BOM manage server APIs instead of manually declaring an arbitrary servlet-api version. This example illustrates the coordinate change.

### 7.2. Persistence API example

Old:

```xml
<dependency>
    <groupId>javax.persistence</groupId>
    <artifactId>javax.persistence-api</artifactId>
</dependency>
```

New:

```xml
<dependency>
    <groupId>jakarta.persistence</groupId>
    <artifactId>jakarta.persistence-api</artifactId>
</dependency>
```

When using the Spring Boot Data JPA starter, dependency management typically selects a compatible API/provider. Avoid declaring separate API versions without a clear reason.

### 7.3. Bean Validation API example

Old:

```xml
<dependency>
    <groupId>javax.validation</groupId>
    <artifactId>validation-api</artifactId>
</dependency>
```

New:

```xml
<dependency>
    <groupId>jakarta.validation</groupId>
    <artifactId>jakarta.validation-api</artifactId>
</dependency>
```

Having only the API does not guarantee having a provider. In Boot applications, the validation starter normally brings the matching implementation to runtime.

### 7.4. Not every dependency group renames by the same rule

Artifacts for Hibernate, Hibernate Validator, Jackson, JAXB implementations, and other libraries follow their own versioning and artifact naming. You cannot apply a blanket rule like "replace `javax` with `jakarta` in `groupId`" to every dependency.

Rely on:

- Spring Boot dependency management/BOM.
- Library release notes and migration guides.
- The actual dependency tree.
- Container/provider compatibility matrices.

### 7.5. Avoiding version drift

A risky example:

- Spring Boot 3.x.
- Hibernate 5.x pinned manually.
- New Jakarta Persistence API.
- A Hibernate extension supporting only Hibernate 5.
- New Jakarta Servlet API, while an old filter library still implements javax.

Each dependency might resolve individually, yet together they fail to form a compatible stack. During a major framework upgrade, prioritize aligning on the Boot-managed version set first and only override with explicit justification.

## 8. XML descriptors and resources are not fixed by import refactoring

Legacy code may have zero `javax` imports left yet still contain Java EE XML configurations.

### 8.1. web.xml

An old descriptor might begin with:

```xml
<web-app
    xmlns="http://xmlns.jcp.org/xml/ns/javaee"
    version="4.0">
    ...
</web-app>
```

Modern Jakarta Servlet uses the corresponding Jakarta EE XML namespace/schema; for example, a Servlet 6 descriptor uses a namespace like:

```xml
<web-app
    xmlns="https://jakarta.ee/xml/ns/jakartaee"
    version="6.0">
    ...
</web-app>
```

If the application relies on Spring Boot's Servlet initializer and does not need a custom descriptor, `web.xml` might not be needed at all. However, if filter/listener/servlet declarations, security constraints, or other metadata remain, migrate the descriptor to the schema supported by the target container.

### 8.2. persistence.xml

An old persistence descriptor may use JPA 2.x namespaces/schemas. Jakarta Persistence 3.x uses the corresponding Jakarta schema/namespace.

If the project uses a manually declared persistence unit, update:

- XML namespace and schema version.
- Provider class name.
- Persistence unit properties.
- Entity class references.
- Related mapping files.

Do not touch schemas if the application does not use `persistence.xml`; Spring Boot can configure persistence from properties and entity scanning.

### 8.3. beans.xml and validation mappings

CDI descriptors or validation mappings may also reference old schema namespaces and class names. Verify exact specification versions rather than rewriting all XML URLs with a generic pattern.

### 8.4. `META-INF/services`

Java SPI stores provider class names in resources such as:

```text
META-INF/services/javax.servlet.ServletContainerInitializer
```

If the SPI interface changed namespaces, the corresponding resource file must also use the new interface name:

```text
META-INF/services/jakarta.servlet.ServletContainerInitializer
```

This is a classic example showing why fixing Java imports alone is insufficient during migration.

## 9. Third-party libraries: where migration is often hardest

An application may update all of its own code yet still depend on an older library.

Examples:

- A filter library implementing only `javax.servlet.Filter`.
- A JPA integration plugin using `javax.persistence.EntityManager`.
- A validation extension referencing `javax.validation.ConstraintValidator`.
- An older SOAP/JAXB library using `javax.xml.bind`.
- A security adapter depending on the legacy Servlet API generation.

### 9.1. Classifying dependencies

| Library type | Question to check |
| --- | --- |
| Framework integration | Is there a release supporting Spring Framework 6/Boot 3? |
| Servlet filter/security | Does it implement `jakarta.servlet` or `javax.servlet`? |
| ORM extension | Does it support Hibernate 6/Jakarta Persistence? |
| Custom validation constraint | Does it implement the Jakarta Validation API? |
| Serialization/XML | Does it use Jakarta JAXB/SAAJ? |
| Generated SDK | Has the code generator emitted the new namespace? |
| Internal company library | Is source available to upgrade and republish? |
| Container plugin | Which external Tomcat/Jakarta Servlet version does it support? |

### 9.2. Prefer Jakarta-native releases

If the vendor provides a newer Jakarta-compatible version, prefer upgrading to that release. A similarly named library with a different major version may have changed both namespaces and behavior.

Read release notes, POM metadata, and source JARs when needed. Do not guess from artifact names alone.

### 9.3. If no replacement library exists

Options may include:

1. Finding another implementation that supports Jakarta.
2. Upgrading or forking an internal library to build against Jakarta APIs.
3. Replacing the integration with a small application adapter.
4. Using bytecode transformation as an interim step if supported and tested.
5. Separating the legacy application from the new Jakarta runtime into its own service/process communicating via HTTP/message contracts.

Never try to force a `javax` class into a `jakarta` interface via casts or reflection. They are distinct APIs.

## 10. Identifying errors when mixing javax and jakarta

### 10.1. Compile error: package does not exist

Example:

```text
package javax.persistence does not exist
```

The new Jakarta dependency may have been brought in while source still uses old imports, or the old API dependency was removed from the classpath.

Resolution steps:

- Confirm the target framework version.
- If the project uses Boot 3, switch Persistence imports to `jakarta.persistence`.
- Check starter/provider dependencies.
- Rebuild the failing module.

### 10.2. NoClassDefFoundError: javax/servlet/...

Example:

```text
java.lang.NoClassDefFoundError: javax/servlet/Filter
```

A runtime library or class still requires the legacy Servlet API. If the application runs on Boot 3/Tomcat 10.1, this usually indicates an unmigrated legacy dependency.

Use the dependency tree to locate the artifact referencing `javax.servlet` and upgrade or replace it.

### 10.3. ClassCastException between javax and jakarta

Example:

```text
SomeFilter cannot be cast to jakarta.servlet.Filter
```

If `SomeFilter` implements only `javax.servlet.Filter`, it cannot be registered as `jakarta.servlet.Filter`. Inspect the filter library, container integration, and mixed API JARs.

### 10.4. NoSuchMethodError or AbstractMethodError

A library was compiled against one API generation while runtime loaded the other. Method descriptors no longer match, or a new interface defines a different contract.

Inspect:

- Actual API version.
- Actual implementation version.
- Classpath ordering/shading.
- Dependency mediation.
- Old artifacts copied into server shared library directories.

### 10.5. JPA does not recognize entities

An entity carrying `javax.persistence.Entity` in an application using Hibernate 6/Jakarta Persistence will not be recognized as a Jakarta entity.

Symptoms include entity-not-found errors, mapping errors, or missing mapping metadata. Check annotation imports and provider/API versions before changing component scanning.

### 10.6. Bean Validation does not run

A constraint annotation from `javax.validation` may not be recognized by a Jakarta Validation provider as a Jakarta constraint. Inspect constraint imports, provider versions, and the dependency graph.

### 10.7. `@PostConstruct` is not invoked as expected

If source uses `javax.annotation.PostConstruct` while a Spring 6 runtime expects the corresponding Jakarta Common Annotations integration, the legacy lifecycle annotation may be ignored. Switch to `jakarta.annotation.PostConstruct` and ensure the API is on the classpath if needed.

### 10.8. Container errors when deploying a WAR

A WAR compiled against `jakarta.servlet` cannot run as a Servlet 4 application on Tomcat 9. Conversely, an old WAR using `javax.servlet` does not become a Jakarta Servlet app on Tomcat 10 simply by changing the server version.

Upgrade both the application and container to the same generation or use a controlled migration/transformation strategy.

## 11. Migration strategy from Spring Boot 2 to Spring Boot 3

Do not start with a repository-wide find-and-replace. A phased approach separates namespace errors from framework/provider upgrade errors.

### Step 1 — Capture the current baseline

Record:

- Spring Boot and Spring Framework versions.
- Java compile/runtime versions.
- Maven/Gradle and plugin versions.
- Servlet container version.
- Hibernate/JPA/Validation providers.
- Security, SOAP, messaging, and batch libraries.
- Pre-migration build/test status.
- Deployed WAR/JAR artifacts.

Having a baseline tells you which errors appeared at each step.

### Step 2 — Choose target compatibility

Identify the target Spring Boot 3 release, Java 17+, servlet container, and compatible library versions.

Do not upgrade Boot before confirming critical dependencies have Jakarta-compatible releases.

### Step 3 — Upgrade the Java toolchain

Maven example:

```xml
<properties>
    <java.version>17</java.version>
</properties>
```

Gradle:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

Align CI, developer JDKs, and runtime images. Verify annotation processors, compiler plugins, and test runners support the target JDK.

### Step 4 — Upgrade framework and dependency management

Upgrade the Spring Boot parent/plugin/BOM to the chosen release. Avoid keeping Spring Framework 5 or Hibernate 5 via manual pinning if the target Boot 3 requires the newer generation.

Run the dependency tree to confirm no legacy APIs/providers remain pulled in.

### Step 5 — Convert imports by specific API

Update moved namespace families: Servlet, Persistence, Validation, Common Annotations, JAX-RS, JMS, JAXB, etc.

Preserve Java SE packages such as `javax.sql`, `javax.crypto`, `javax.naming`, and `javax.xml.parsers`.

### Step 6 — Update descriptors and SPI resources

Inspect `web.xml`, `persistence.xml`, `beans.xml`, validation mappings, `META-INF/services`, and XML schemas.

If files are generated, update the source schemas/generator templates instead of editing only generated output.

### Step 7 — Upgrade third-party libraries

Verify library integrations for Jakarta support. Pay special attention to security filters, servlet extensions, ORM types, validation constraints, and SOAP clients.

### Step 8 — Build module by module

Build core modules first, then adapters and applications. Early compile errors pinpoint unaligned sources/imports/APIs. Do not skip rarely used modules, as they may fail only during full-project packaging.

### Step 9 — Run layered tests

- Unit tests for pure logic.
- Persistence tests for JPA/provider behavior.
- MVC/Servlet tests for filters/controllers.
- Context startup tests.
- Integration tests with databases/message brokers.
- Smoke tests on the packaged artifact.
- External container deployment tests if building a WAR.

### Step 10 — Run in the target runtime

Do not run only from the IDE. Use the exact built JAR/WAR artifact and deployment Java/container runtime. Verify logging, ports, security, migrations, shutdown, and health checks.

### Step 11 — Remove legacy dependencies and re-verify

Use dependency analysis and source/resource scanning to find remaining references. Distinguish valid Java SE references from legacy enterprise APIs. Finish with a clean build in CI.

## 12. Automated tools: when helpful, when dangerous?

### 12.1. Find-and-replace

Replacing all `javax.` with `jakarta.` is dangerous because it breaks Java SE packages that must remain untouched.

Examples that must NOT be changed:

```java
import javax.sql.DataSource;
import javax.crypto.Cipher;
import javax.naming.InitialContext;
import javax.xml.parsers.DocumentBuilderFactory;
```

A blind replacement turns valid imports into nonexistent packages.

If using IDE replace, restrict it to a verified package list, review the diff, and compile immediately after each group.

### 12.2. OpenRewrite

OpenRewrite provides recipes for upgrading Spring Boot and migrating Java EE namespaces to Jakarta in supported cases.

A recipe can update:

- Java imports.
- Some dependency coordinates.
- Some configurations.
- Some API usages according to defined rules.

However, a tool cannot automatically know whether every internal custom library has a Jakarta-compatible release, nor decide how business behavior should change.

Always:

1. Choose the appropriate recipe/version.
2. Run on a migration branch.
3. Review the diff.
4. Check XML/resources/generated sources.
5. Build and test all modules.
6. Verify the dependency graph and runtime behavior.

### 12.3. Eclipse Transformer and Tomcat Migration Tool

Tools exist to transform artifacts/bytecode from Java EE namespaces to Jakarta, such as Eclipse Transformer or the Apache Tomcat Jakarta EE Migration Tool.

They can help handle legacy applications or dependencies without immediate source migration. However:

- Not every library can be safely transformed.
- Reflection strings, serialization metadata, XML, service descriptors, and bytecode may require corresponding handling.
- Runtime behavior must still be compatible with target Jakarta APIs.
- A transformed artifact does not mean vendor support.
- Tools do not replace upgrading frameworks/containers/providers.

Treat transformation as a tested part of a migration plan, not an automatic compatibility guarantee.

### 12.4. Generated code

If sources are generated from WSDL, XSD, OpenAPI, or annotation processors, old imports can reappear on the next generation run.

Check:

- Generator version.
- Plugin configuration.
- Templates.
- Annotation processor dependencies.
- Generated source directories.
- CI code generation tasks.

Editing generated output without updating the generator produces only a temporary fix.

## 13. Servlet container compatibility when upgrading a WAR

For traditional WAR deployments, namespace migration must align with the external container.

### 13.1. Tomcat 9 vs. Tomcat 10+

Tomcat 9 provides the `javax.servlet` Servlet API generation. Tomcat 10 switched to `jakarta.servlet`. Tomcat 10.1 supports Jakarta Servlet 6.0.

A Boot 3/Spring 6 WAR using Jakarta Servlet requires a compatible container. Deploying to Tomcat 9 is not a valid test for a Jakarta Servlet application.

### 13.2. Do not copy legacy Servlet API JARs into a WAR as a workaround

If the container provides the Servlet API, dependency scopes must reflect runtime ownership. Dropping `javax.servlet-api` into `WEB-INF/lib` of a Jakarta WAR does not make an old adapter compatible; it just introduces an incompatible type set onto the classpath.

### 13.3. Tomcat migration tool can help transition legacy WARs

Tomcat provides a migration tool to transform certain Java EE 8 applications into Jakarta EE suitable for Tomcat 10. This is a useful transitional utility for legacy deployments, yet you must still test:

- Servlet filters/listeners.
- JSP/tag libraries if any.
- XML descriptors.
- Third-party libraries.
- Security integration.
- JPA/validation APIs beyond Servlet scope.
- Application-specific reflection/serialization.

Do not assume transforming the Servlet namespace means the entire enterprise stack has been migrated.

## 14. Which Spring-specific APIs do NOT change?

When upgrading to Spring Boot 3, many Spring classes retain their packages and names.

Example:

```java
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.annotation.Transactional;
```

These annotations still belong to Spring Framework. Do not change them to a `jakarta` package because no equivalent Jakarta API plays the same role.

Some Spring APIs may have changed behavior or been deprecated across major versions, but that is a separate migration topic rather than namespace conversion.

### 14.1. `@Transactional` is easy to confuse

Spring:

```java
import org.springframework.transaction.annotation.Transactional;
```

Legacy JTA:

```java
import javax.transaction.Transactional;
```

New JTA:

```java
import jakarta.transaction.Transactional;
```

If source uses the Spring annotation, the import remains `org.springframework.transaction.annotation.Transactional` in Boot 3. Do not switch it to `jakarta.transaction.Transactional` merely upon seeing the word transaction.

### 14.2. `@Autowired` does not become `@Inject`

Spring:

```java
import org.springframework.beans.factory.annotation.Autowired;
```

Jakarta Inject:

```java
import jakarta.inject.Inject;
```

Both can express dependency injection in the right environment, but they are not the same type. Migration does not require replacing `@Autowired` with `@Inject`.

### 14.3. `@Component` does not become `@Named`

Spring:

```java
import org.springframework.stereotype.Component;
```

Jakarta Inject:

```java
import jakarta.inject.Named;
```

These annotations belong to different ecosystems. Choose by framework contract rather than swapping names as synonyms.

## 15. APIs that left the JDK and separate dependency issues

Some enterprise `javax` packages used to be bundled in older JDKs but were removed from the JDK in Java 11 under the module removal plan. JAXB and JAX-WS are prominent examples.

This creates two distinct classes of errors:

1. Source still uses the old API while the dependency is no longer bundled in the JDK.
2. The application migrated to Jakarta yet has not declared the corresponding API/implementation dependencies.

### 15.1. JAXB

Legacy code:

```java
import javax.xml.bind.JAXBContext;
```

Jakarta code:

```java
import jakarta.xml.bind.JAXBContext;
```

Beyond the namespace, compatible JAXB API and implementation artifacts must exist in the dependency graph. Importing the new package without runtime dependencies is still insufficient.

### 15.2. JAX-WS

Legacy JAX-WS APIs use `javax.xml.ws`; Jakarta versions use `jakarta.xml.ws`. Tooling such as `wsimport`, generated clients, and runtime implementations must align with the target namespace.

If WSDL client code was generated by an older tool, source may continue containing `javax.xml.ws` even after the project upgrades to Boot 3.

### 15.3. Distinguish Java 11 errors from Jakarta migration errors

An application running Java 8 could pull JAXB classes from the JDK. Moving to Java 17 may trigger `ClassNotFoundException` even while still using the old namespace.

That is a JDK packaging change. Migrating to Jakarta is a namespace/API generation change. Both issues can appear together, yet each must be diagnosed separately.

## 16. Common upgrade errors and how to investigate them

| Symptom | Possible cause | Investigation direction |
| --- | --- | --- |
| `package javax.persistence does not exist` | Old source with new dependency or missing old API | Switch to Jakarta if targeting Boot 3; check JPA starter |
| `NoClassDefFoundError: javax/servlet/Filter` | Legacy library requires javax Servlet | Locate dependency and upgrade to Jakarta release |
| `NoClassDefFoundError: jakarta/servlet/Servlet` | Runtime/container does not provide Jakarta Servlet | Check Tomcat/Jetty and deployment mode |
| `ClassCastException` registering Filter | Filter implements javax while container expects jakarta | Upgrade filter library or replace adapter |
| Hibernate ignores Entity | Entity annotation belongs to javax Persistence | Update import and use Jakarta Hibernate/JPA |
| Validation does not run | Constraint/provider on mismatched namespaces | Check Jakarta Validation API/provider |
| `NoSuchMethodError` | Incompatible API/provider/library versions | Dependency tree, BOM, runtime classpath |
| Boot 2 WAR fails on Tomcat 10 | WAR still uses javax Servlet | Migrate source/dependencies or transform in a controlled way |
| Boot 3 WAR fails on Tomcat 9 | Container supports only javax Servlet | Upgrade external container |
| `javax.annotation.PostConstruct` does not run | Legacy lifecycle annotation | Use `jakarta.annotation.PostConstruct` |
| XML deployment descriptor rejected | Legacy namespace/schema version | Update descriptor for target container |
| SPI provider not found | `META-INF/services` still uses old interface name | Update service descriptor and provider |
| JAXB class missing on Java 17 | JAXB no longer bundled in JDK | Add compatible Jakarta JAXB API/implementation |
| Generated source reintroduces javax | Old generator/plugin | Upgrade generator and templates |
| Fails only in CI | CI JDK/container/dependencies differ from local | Compare toolchain, runtime image, resolved graph |
| Source is clean yet runtime still fails | Third-party bytecode contains javax references | Scan dependency JARs/upgrade library |
| Both javax and jakarta APIs appear | Dependency tree mixes generations | Identify dependency pulling old API and exclude/upgrade |

### 16.1. Read the full exception chain

Example:

```text
Caused by: java.lang.NoClassDefFoundError:
    javax/servlet/ServletRequest

    at com.vendor.legacy.LegacyFilter.initialize(...)
    ...

Caused by: java.lang.ClassNotFoundException:
    javax.servlet.ServletRequest
```

The frame `com.vendor.legacy.LegacyFilter` shows the vendor library is what still references the old API. Editing imports in your application controllers will not solve it.

### 16.2. Find the dependency owning the legacy class

Maven:

```bash
./mvnw dependency:tree -Dverbose
```

Gradle:

```bash
./gradlew dependencyInsight --dependency javax.servlet --configuration runtimeClasspath
```

Module names might not match packages exactly. If `dependencyInsight` does not find it because an API was shaded/relocated inside another JAR, inspect archive contents or scan bytecode.

### 16.3. Compare local and CI

Check:

- Actual JDK.
- Spring Boot plugin/BOM version.
- Dependency lockfiles.
- Container base image.
- Deployed WAR/JAR artifact.
- Shared libraries in external Tomcat.
- Environment variables and build profiles.

A local IDE may accidentally include an old API from another module on the classpath while the packaged artifact omits it—or vice versa.

## 17. Workflow to inspect source, resources, and bytecode

A reliable migration should include multiple verification layers.

### 17.1. Scan source imports

```bash
rg -n "import javax\\.(servlet|persistence|validation|annotation|inject|ws\\.rs|jms|mail|xml\\.bind)" src
```

This filter targets API groups commonly needing migration. Verify whether each match belongs to a moved package or Java SE.

### 17.2. Scan resources

Check inside:

- `src/main/resources`.
- `src/test/resources`.
- `META-INF/services`.
- XML descriptors.
- WSDL/XSD/generated files.
- Templates containing fully qualified class names.

Example:

```bash
rg -n "javax\\.(servlet|persistence|validation|xml\\.bind)" src/main/resources src/test/resources
```

### 17.3. Inspect built archives

For JAR:

```bash
jar tf target/application.jar
```

For WAR:

```bash
jar tf target/application.war
```

Inspect packaged dependency JARs and resource descriptors. Updating source imports does not guarantee the deployed artifact was rebuilt from updated sources.

### 17.4. Scan bytecode when necessary

Compiled classes may retain symbolic references to legacy namespaces. Tools like `jdeps`, `javap`, or bytecode analyzers help uncover dependency references.

Example inspecting a class:

```bash
javap -classpath path/to/library.jar -verbose com.vendor.LegacyFilter
```

Search constant pool entries or method descriptors containing `javax/servlet`. Select the exact classpath and class name for the JAR; for nested JARs inside executable Boot archives, extract the artifact first if needed.

### 17.5. Dependency graphs are evidence, not the whole evidence

Dependency trees show artifact coordinates and versions, but do not always reveal packages shaded into a JAR or classes generated at build time. Combine source search, resource search, dependency analysis, and runtime stack traces.

## 18. Cross-module compatibility in large systems

In multi-module or multi-service systems, migration may progress at different paces.

### 18.1. Do not share a Servlet interface across two generations

A legacy module implementing `javax.servlet.Filter` cannot be registered directly into a Spring Boot 3 application expecting `jakarta.servlet.Filter`.

If the legacy module must remain temporarily, separate it from the Jakarta application boundary via process/API/messaging boundaries or write a new adapter based on a neutral contract.

### 18.2. Split at service boundaries instead of mixing APIs

Example:

```text
Legacy service (Boot 2 / javax)
        |
        | HTTP/JSON or message contract
        v
New service (Boot 3 / jakarta)
```

HTTP/JSON contracts do not carry Java class identities of Servlet/JPA types. Two services can use different namespaces as long as shared schemas/protocols are versioned and tested.

### 18.3. Shared libraries should avoid Servlet dependencies when unnecessary

If a library contains only shared domain types or DTOs, do not pull Servlet APIs into its dependencies. Doing so makes the library hard to reuse across old and new web stacks.

Keeping shared contracts plain Java or schema-based messages reduces coupling. If Servlet integration is truly needed, split dedicated adapter modules per API generation when parallel migration is required.

### 18.4. Do not let javax and jakarta define the same contract in one module

Two identically named interfaces in different packages have distinct type identities. If temporary compatibility is required, write explicit adapters at boundaries and keep legacy types from leaking into core code.

Never build a common API using casts or raw reflection to bypass type differences.

## 19. A complete Servlet Filter migration example

### 19.1. Legacy code

```java
package com.example.legacy;

import javax.servlet.Filter;
import javax.servlet.FilterChain;
import javax.servlet.ServletException;
import javax.servlet.ServletRequest;
import javax.servlet.ServletResponse;

import java.io.IOException;

public class LegacyTraceFilter implements Filter {

    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {

        chain.doFilter(request, response);
    }
}
```

### 19.2. Jakarta code

```java
package com.example.web;

import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;

import java.io.IOException;

public class TraceFilter implements Filter {

    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {

        chain.doFilter(request, response);
    }
}
```

### 19.3. Registering in Spring

```java
@Configuration(proxyBeanMethods = false)
public class WebConfiguration {

    @Bean
    FilterRegistrationBean<TraceFilter> traceFilter() {
        FilterRegistrationBean<TraceFilter> registration =
                new FilterRegistrationBean<>();

        registration.setFilter(new TraceFilter());
        registration.addUrlPatterns("/*");
        registration.setOrder(10);

        return registration;
    }
}
```

`FilterRegistrationBean` is a Spring Boot servlet integration API. In a Boot 3 application, the filter generic type and imports must be Jakarta Servlet-compatible.

If a vendor library provides only `LegacyTraceFilter` implementing javax, that object cannot be passed into a Jakarta registration bean. Upgrade the library or write a new filter adapter with the Jakarta API.

### 19.4. Testing the filter

Use MockMvc with a full application context to verify the filter is registered and applied. If the filter relies on specific container behavior, supplement with HTTP tests using `RANDOM_PORT` or tests on a matching external container.

## 20. A JPA and Validation migration example

### 20.1. Legacy entity

```java
import javax.persistence.Entity;
import javax.persistence.Id;
import javax.persistence.Column;

@Entity
public class CustomerEntity {

    @Id
    private Long id;

    @Column(nullable = false)
    private String name;
}
```

### 20.2. Jakarta entity

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Column;

@Entity
public class CustomerEntity {

    @Id
    private Long id;

    @Column(nullable = false)
    private String name;
}
```

When using Hibernate 6, ensure both entities and provider use Jakarta Persistence. Hibernate configurations may have additional breaking changes beyond namespaces, so read the migration guide for the Hibernate version being adopted.

### 20.3. Legacy request validation

```java
import javax.validation.Valid;
import javax.validation.constraints.NotBlank;

public record CustomerRequest(
        @NotBlank String name) {
}
```

### 20.4. Jakarta request validation

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

public record CustomerRequest(
        @NotBlank String name) {
}
```

The `@Valid` annotation on controller parameters retains its cascading validation role, but imports must be Jakarta Validation types on the Boot 3 stack.

If a custom validator implements `ConstraintValidator`, that interface and its related annotations must also move to `jakarta.validation.*`.

## 21. Testing migration after changing namespaces

Do not stop migration once sources compile. Verify runtime integration.

### 21.1. Clean build

Maven:

```bash
./mvnw clean verify
```

Gradle:

```bash
./gradlew clean test
```

A clean build clears stale outputs from before migration. In multi-module builds, confirm all modules build against the same target generation.

### 21.2. Context startup test

```java
@SpringBootTest
class ApplicationMigrationTest {

    @Test
    void contextLoads() {
    }
}
```

This test catches missing beans, API incompatibilities, invalid configurations, and provider initialization errors.

### 21.3. Servlet integration test

Use MockMvc or `RANDOM_PORT` to verify:

- Filter registration.
- Request/response handling.
- Exception handlers.
- Security chain.
- JSON conversion.
- Servlet API integration.

If targeting an external WAR, test deploying on the target container generation; embedded tests do not replace external deployment tests.

### 21.4. Persistence test

Verify:

- Entity scanning.
- Hibernate startup.
- Schema validation/migration.
- Repository save/load.
- JPQL/native queries.
- Custom type converters.
- Transaction behavior.

Do not check only application context startup when entity mappings might not be exercised during tests.

### 21.5. Validation test

Verify constraint annotations are detected by the provider and return the expected errors. An endpoint returning 200 on invalid input may indicate old validation annotations are ignored by the new provider.

### 21.6. Smoke test the packaged artifact

Run the actual built JAR/WAR, not just inside the IDE. For a WAR, deploy onto the target external container if that matches production.

## 22. Diagnostic checklist when encountering legacy javax code

When spotting a `javax` import or stack trace, follow this order:

1. **Identify the full package.** Do not look only at the `javax` prefix.
2. **Determine whether the API belongs to Java SE or Java EE/Jakarta EE.**
3. **Identify the Spring Boot/Spring Framework version.**
4. **Identify the target container/provider version.**
5. **Verify dependency coordinates and resolved versions.**
6. **Inspect source, resources, XML, and service descriptors.**
7. **Check whether third-party libraries reference the old namespace.**
8. **Run a clean build to uncover compile/linkage errors.**
9. **Run appropriate context, persistence, web, and validation tests.**
10. **Deploy the actual artifact on the target runtime.**
11. **Use bytecode transformers only with defined scope and proving tests.**
12. **Preserve Java SE `javax` packages unaffected by migration.**

### 22.1. Decision questions

| Question | If the answer is... | Action |
| --- | --- | --- |
| Does the package belong to Java SE? | Yes | Keep `javax` |
| Does the package belong to a moved Jakarta API? | Yes | Use `jakarta` for the target Jakarta stack |
| Does the project run Boot 2/Spring 5? | Yes | Verify Java EE/Jakarta EE 8 compatibility before changing |
| Does the project run Boot 3/Spring 6? | Yes | Upgrade APIs/providers/libraries to Jakarta-compatible versions |
| Does a third-party library have only a javax release? | Yes | Upgrade/replace/fork/transform in a controlled manner or isolate the service |
| Running a WAR on Tomcat 9? | Yes | That is the javax Servlet generation; not directly compatible with Boot 3 Jakarta Servlet |
| Source is clean yet runtime fails? | Yes | Inspect bytecode, dependencies, generated code, and container shared libs |
| Error occurs only on Java 17? | Yes | Separate JDK module removals from namespace migration |

## 23. Practical exercise: identifying and migrating a legacy module

### Objective

Start with a hypothetical Spring Boot 2.x module containing a Servlet filter, a JPA entity, a Bean Validation DTO, and an external dependency. Upgrade it to a Spring Boot 3.x/Jakarta-compatible target while preserving business behavior.

### Step 1 — Inventory

Locate and record:

- Boot/Spring version.
- Java toolchain.
- Servlet/JPA/Validation API dependencies.
- Tomcat/Jetty.
- Hibernate/Validation provider.
- `javax` imports.
- XML descriptors.
- Service descriptors.
- Generated code.
- Third-party libraries.

Do not edit source in this step.

### Step 2 — Classify imports

Create three groups:

1. Enterprise APIs to move to Jakarta.
2. Java SE `javax` packages to keep unchanged.
3. Third-party packages requiring vendor version upgrades.

Example:

| Import | Decision |
| --- | --- |
| `javax.servlet.Filter` | Move to `jakarta.servlet.Filter` |
| `javax.persistence.Entity` | Move to `jakarta.persistence.Entity` |
| `javax.validation.Valid` | Move to `jakarta.validation.Valid` |
| `javax.annotation.PostConstruct` | Move to `jakarta.annotation.PostConstruct` |
| `javax.sql.DataSource` | Keep unchanged |
| `javax.crypto.Cipher` | Keep unchanged |
| `javax.xml.parsers.DocumentBuilderFactory` | Keep unchanged |
| `javax.annotation.processing.Processor` | Keep unchanged |
| `javax.transaction.xa.XAResource` | Keep unchanged |

### Step 3 — Upgrade target runtime

Select Java 17+ and an appropriate Spring Boot 3 release. Select container/provider versions supporting the corresponding Jakarta APIs.

### Step 4 — Upgrade dependencies

Use the Boot BOM and Jakarta-compatible releases. Remove legacy APIs/providers pulled in by transitive dependencies. Document the reason for every dependency override.

### Step 5 — Migrate source

Convert enterprise imports by API group. Compile after each major group to pinpoint errors easily. Do not replace all `javax.`.

### Step 6 — Migrate resources

Update descriptors/schemas/SPI and code generators. Regenerate sources if WSDL/XSD/annotation processing is used.

### Step 7 — Upgrade third-party integrations

Upgrade servlet filters, security adapters, ORM extensions, custom validators, and SOAP/JMS libraries. If no Jakarta release exists, evaluate replacement or isolation.

### Step 8 — Build and scan

Run a clean build, dependency tree, and source/resource searches. Verify no enterprise javax dependencies remain aside from intentionally isolated legacy parts.

### Step 9 — Test

Run unit, context startup, MVC, JPA, validation, and integration tests. Compare behavior before/after migration for critical use cases.

### Step 10 — Deploy smoke test

Run the executable JAR or deploy the WAR to the exact target container. Inspect startup logs and verify endpoints, persistence, security, and shutdown.

### Step 11 — Record migration decisions

Create internal documentation listing:

- Which namespaces migrated.
- Which Java SE packages remain `javax`.
- Upgraded third-party library versions.
- Minimum container version.
- Remaining legacy integrations.
- Tests proving compatibility.

### Self-check questions

1. Why did Java EE transition to Jakarta EE?
2. Does Jakarta EE 8 use the `javax` or `jakarta` namespace?
3. Which Jakarta EE version officially started the namespace change?
4. Why can't `javax.servlet.Filter` and `jakarta.servlet.Filter` substitute directly?
5. Which Java SE APIs retain the `javax` prefix?
6. Why does `javax.annotation.PostConstruct` move while `javax.annotation.processing.Processor` stays?
7. Why is `javax.transaction.xa.XAResource` an exception?
8. What Java baseline does Spring Boot 3 require?
9. Why does Hibernate 6 require Jakarta Persistence annotations?
10. How does Tomcat 9 differ from Tomcat 10.1 in Servlet namespace/specification?
11. Why can runtime still fail after source imports are changed?
12. How does Spring's `@Transactional` differ from `jakarta.transaction.Transactional`?
13. Why must `META-INF/services` be checked during migration?
14. Why can generated sources bring back `javax` imports?
15. When should OpenRewrite or Eclipse Transformer be used?
16. Why should you not replace every `javax.` occurrence?
17. How do you find a library still referencing `javax.servlet`?
18. Why does successful compilation not prove a WAR can deploy?
19. When should a legacy service be isolated instead of mixing two namespaces?
20. Which integration tests should run after migration?

## 24. Quick reference summary

| Topic | Key takeaway |
| --- | --- |
| Java EE | Previous-generation enterprise API ecosystem |
| Jakarta EE 8 | Still uses the `javax` namespace |
| Jakarta EE 9 | Moves enterprise APIs to `jakarta` |
| Spring Boot 2 / Framework 5 | Generation commonly using `javax` integrations |
| Spring Boot 3 / Framework 6 | Jakarta APIs, Java 17+ |
| Servlet | `javax.servlet` → `jakarta.servlet` |
| JPA | `javax.persistence` → `jakarta.persistence` |
| Bean Validation | `javax.validation` → `jakarta.validation` |
| Common Annotations | `javax.annotation` → `jakarta.annotation` |
| Inject | `javax.inject` → `jakarta.inject` |
| JTA | `javax.transaction` → `jakarta.transaction` |
| XA | `javax.transaction.xa` remains Java SE |
| JDBC | `javax.sql` remains Java SE |
| Crypto | `javax.crypto` remains Java SE |
| XML parser | `javax.xml.parsers` remains Java SE |
| JAXB | `javax.xml.bind` → `jakarta.xml.bind` |
| JAX-RS | `javax.ws.rs` → `jakarta.ws.rs` |
| Spring annotations | `org.springframework.*` do not become Jakarta |
| Dependency graph | APIs, providers, and implementations must align |
| Third-party libraries | Need Jakarta-compatible releases |
| XML/SPI resources | May need migration outside Java source |
| Tomcat 9 | `javax` Servlet generation |
| Tomcat 10.1 | Jakarta Servlet 6 generation |
| Migration tools | Assist transformation but do not replace compatibility testing |
| Full validation | Clean build + context + web + persistence + runtime smoke tests |

**Core point:** When encountering legacy code, do not apply a rule like "see `javax`, change to `jakarta`." Determine **whether the package belongs to Java SE or Jakarta EE**, then check **Spring Boot/Spring Framework, API, provider, third-party library, and container versions**. Migration succeeds when all source, dependency graphs, descriptors, generated code, and runtime share one compatible API generation, while valid Java SE `javax` packages remain intact.
