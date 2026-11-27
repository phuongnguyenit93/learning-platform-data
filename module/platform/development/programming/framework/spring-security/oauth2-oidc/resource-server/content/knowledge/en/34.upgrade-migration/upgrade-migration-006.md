# Migrating Servlet `javax` to `jakarta` with the Right Scope

## 1. Why Does This Migration Require Careful Scoping?

Starting with Jakarta EE 9, many Java EE APIs moved their namespace from `javax.*` to `jakarta.*`. For a Servlet application using Spring Security OAuth 2.0/OIDC Resource Server, the most visible change is:

```java
// Before: Servlet API under Java EE namespace
import javax.servlet.Filter;
import javax.servlet.ServletException;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

// After: Servlet API under Jakarta EE namespace
import jakarta.servlet.Filter;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
```

This is an API- and bytecode-level package change. A class compiled to implement `javax.servlet.Filter` does not automatically become an implementation of `jakarta.servlet.Filter`. Therefore, simply bumping the Spring Boot version or swapping the container is insufficient if source code, dependencies, or plugins still rely on the old Servlet API.

However, **not every package starting with `javax.` moves to `jakarta.`** Many Java SE packages retain their original namespace. Running a blind global find-and-replace on `javax` can break valid code for JDBC, cryptography, networking, XML processing, or Java annotation processing.

This lesson belongs to the **Upgrade and Migration** chapter of the **Spring Security OAuth 2.0 OIDC Resource Server** module. It focuses on the scope of Servlet API conversion, distinguishing Java SE from Jakarta EE packages, impacts on Spring Boot 3/Spring Framework 6/Spring Security 6, dependency and container compatibility, custom filters, OAuth2 Resource Server configuration, testing, and troubleshooting migration failures.

> **Core rule:** Move true Jakarta EE APIs to the `jakarta` namespace. Keep Java SE `javax` packages and Spring's own packages untouched. Verify both compile-time and runtime dependencies because bytecode in older libraries still references old class names.

---

## 2. Background: Java EE Becomes Jakarta EE

Java EE was transferred to the Eclipse Foundation and evolved under the name Jakarta EE. A defining change in Jakarta EE 9 was moving most enterprise APIs from `javax.*` to `jakarta.*`.

Examples:

| Pre-Migration API | Post-Migration API |
|---|---|
| `javax.servlet.*` | `jakarta.servlet.*` |
| `javax.validation.*` | `jakarta.validation.*` |
| `javax.persistence.*` | `jakarta.persistence.*` |
| `javax.ws.rs.*` | `jakarta.ws.rs.*` |
| `javax.websocket.*` | `jakarta.websocket.*` |
| `javax.enterprise.*` | `jakarta.enterprise.*` |
| `javax.inject.*` | `jakarta.inject.*` |
| `javax.annotation.*` (Jakarta Common Annotations) | `jakarta.annotation.*` |
| `javax.xml.bind.*` | `jakarta.xml.bind.*` |
| `javax.mail.*` | `jakarta.mail.*` |
| `javax.activation.*` | `jakarta.activation.*` |

These APIs did not merely rename imports in source code. Their fully qualified class names also changed in bytecode, method signatures, annotations, descriptors, and dependency metadata.

### 2.1. Why Is Binary Compatibility Affected?

Suppose an older library declares:

```java
public class LegacyAuthFilter implements javax.servlet.Filter {
    // ...
}
```

The new application runs on a Servlet container that provides only `jakarta.servlet.Filter`. The JVM treats two differently named interfaces as distinct types. The legacy class does not implement the interface the new container expects.

You may encounter errors such as:

```text
ClassNotFoundException: javax.servlet.Filter
NoClassDefFoundError: javax/servlet/Filter
ClassCastException: ... cannot be cast to jakarta.servlet.Filter
```

Even after updating application source imports, a pre-compiled dependency built against `javax.servlet` can still fail at runtime.

### 2.2. The Jakarta Namespace Is Not a Global Prefix Replacement

Migration must distinguish:

- Jakarta EE APIs: rename namespaces per the target release.
- Java SE APIs: preserve the namespace if the package still belongs to the JDK.
- Spring APIs: continue using `org.springframework.*` packages.
- Third-party APIs: follow the vendor's compatible release.
- Application-specific packages: change only if the application owns the namespace and has a clear reason.

---

## 3. Distinguishing `javax` Packages to Migrate vs. `javax` Packages to Keep

This is the most critical part of a properly scoped migration.

### 3.1. Jakarta EE Packages Typically Needing Migration

| Old Namespace | New Namespace | Where Encountered in Applications |
|---|---|---|
| `javax.servlet` | `jakarta.servlet` | Filters, servlets, listeners, request/response, ServletContext. |
| `javax.servlet.http` | `jakarta.servlet.http` | HttpServletRequest, HttpServletResponse, HttpSession. |
| `javax.servlet.annotation` | `jakarta.servlet.annotation` | @WebServlet, @WebFilter, @WebListener. |
| `javax.servlet.descriptor` | `jakarta.servlet.descriptor` | Deployment descriptor APIs. |
| `javax.validation` | `jakarta.validation` | Bean Validation constraints and Validator. |
| `javax.persistence` | `jakarta.persistence` | JPA entities, EntityManager, persistence annotations. |
| `javax.transaction` | `jakarta.transaction` | Jakarta Transactions API, e.g. UserTransaction. |
| `javax.annotation` | `jakarta.annotation` | PostConstruct, PreDestroy, Resource, RolesAllowed. |
| `javax.inject` | `jakarta.inject` | Inject, Named, Provider. |
| `javax.enterprise` | `jakarta.enterprise` | CDI annotations and APIs. |
| `javax.ws.rs` | `jakarta.ws.rs` | JAX-RS resources, providers, filters. |
| `javax.websocket` | `jakarta.websocket` | WebSocket endpoints. |
| `javax.xml.bind` | `jakarta.xml.bind` | JAXB marshalling/unmarshalling. |
| `javax.mail` | `jakarta.mail` | Jakarta Mail. |
| `javax.activation` | `jakarta.activation` | Jakarta Activation. |
| `javax.servlet.jsp` | `jakarta.servlet.jsp` | JSP APIs. |
| `javax.security.enterprise` | `jakarta.security.enterprise` | Jakarta Security APIs. |
| `javax.security.auth.message` | `jakarta.security.auth.message` | Jakarta Authentication/JASPIC APIs. |

This list covers common groups, not a rule to replace every similarly named package. Check the API documentation and dependency version for each library.

### 3.2. Java SE Packages That Must Usually Stay `javax`

| Package to Keep | Reason |
|---|---|
| `javax.crypto` | Java SE Cryptography APIs. |
| `javax.net` and `javax.net.ssl` | Java SE Networking and TLS APIs. |
| `javax.sql` | Java SE JDBC extensions/DataSource APIs. |
| `javax.naming` | Java SE JNDI APIs. |
| `javax.management` | Java SE JMX APIs. |
| `javax.xml.parsers` | Java SE XML parser APIs. |
| `javax.xml.transform` | Java SE XML transformation APIs. |
| `javax.xml.namespace` | Java SE XML namespace APIs. |
| `javax.xml.stream` | Java SE StAX APIs. |
| `javax.xml.validation` | Java SE XML Schema validation APIs; do not confuse with Bean Validation. |
| `javax.security.auth` | Java SE Java Authentication and Authorization Service (JAAS) APIs. |
| `javax.security.auth.callback` | Java SE callback APIs. |
| `javax.security.auth.login` | Java SE login APIs. |
| `javax.annotation.processing` | Java compiler annotation-processing APIs. |
| `javax.lang.model` | Java compiler language model APIs. |
| `javax.transaction.xa` | XA transaction interfaces belonging to the Java SE module. |

Example inside a Resource Server application:

```java
import javax.crypto.SecretKey;
import javax.net.ssl.SSLContext;
import javax.sql.DataSource;
import javax.naming.InitialContext;
import javax.xml.parsers.DocumentBuilderFactory;

import jakarta.servlet.http.HttpServletRequest;
```

The leading `javax` imports remain valid on the JDK. Only the Servlet import moves to `jakarta`.

### 3.3. Similar-Looking Names Belonging to Different APIs

Do not confuse:

- `javax.validation` (legacy Bean Validation API) with `javax.xml.validation` (Java SE XML validation).
- `javax.annotation` (pre-migration Jakarta Common Annotations) with `javax.annotation.processing` (Java compiler API).
- `javax.transaction` (pre-migration Jakarta Transactions API) with `javax.transaction.xa` (Java SE XA API).
- `javax.security.enterprise` or `javax.security.auth.message` (pre-migration Jakarta EE APIs) with `javax.security.auth` (Java SE JAAS).

Never decide based on prefix alone. Check the specific package, owning module, and API version.

---

## 4. Scope Across Spring Boot, Spring Framework, and Spring Security

Servlet namespace migration typically occurs when upgrading an application from Spring Boot 2.x to Spring Boot 3.x.

Related changes:

| Component | Typical Pre-Migration | Typical Post-Migration |
|---|---|---|
| Spring Boot | 2.x | 3.x |
| Spring Framework | 5.x | 6.x |
| Spring Security | 5.x | 6.x |
| Java baseline | Java 8/11 depending on Boot 2 minor | Java 17 or higher for Spring Boot 3 |
| Servlet API | Java EE `javax.servlet` | Jakarta `jakarta.servlet` |
| Embedded Tomcat | Tomcat 9 | Tomcat 10.1 in common Boot 3 lines |
| Servlet container | Servlet 4.0 in common Boot 2 setups | Jakarta Servlet 6.0 in common Boot 3/Tomcat 10.1 setups |

Always check the compatibility matrix of the exact Spring Boot minor release and deployed container. Do not assume every Boot 3 version uses the same minor Servlet API or embedded container.

### 4.1. Spring Security Packages Do Not Move to `jakarta`

The following classes remain in the Spring namespace:

```java
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationFilter;
```

Do not change them to `jakarta.security.*` or any invented package. The Jakarta namespace migration applies only to Jakarta EE APIs.

### 4.2. Spring Boot Starter Coordinates Normally Stay the Same

Dependency declarations still use Spring artifacts:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
```

You do not change `groupId` to `jakarta` for these starters. The Spring Boot BOM manages compatible versions across Spring Framework, Spring Security, and supported dependencies.

### 4.3. The Java Baseline Is Part of the Migration

Spring Boot 3 requires Java 17 or newer. Before switching namespaces:

- Verify build and runtime JDKs.
- Update Maven/Gradle toolchains.
- Verify CI images and production base images.
- Update compiler release/target settings.
- Verify annotation processors and code generators.
- Confirm third-party libraries support Java 17 and Jakarta APIs.

If you build with JDK 17 while production runs an older JDK, migration may compile cleanly yet fail to deploy.

---

## 5. Servlet API Migration: Primary Types

Servlet types commonly appear in custom filters, interceptors, listeners, and authentication handlers.

| Before | After |
|---|---|
| `javax.servlet.Filter` | `jakarta.servlet.Filter` |
| `javax.servlet.FilterChain` | `jakarta.servlet.FilterChain` |
| `javax.servlet.ServletRequest` | `jakarta.servlet.ServletRequest` |
| `javax.servlet.ServletResponse` | `jakarta.servlet.ServletResponse` |
| `javax.servlet.ServletException` | `jakarta.servlet.ServletException` |
| `javax.servlet.ServletContext` | `jakarta.servlet.ServletContext` |
| `javax.servlet.ServletConfig` | `jakarta.servlet.ServletConfig` |
| `javax.servlet.http.HttpServlet` | `jakarta.servlet.http.HttpServlet` |
| `javax.servlet.http.HttpServletRequest` | `jakarta.servlet.http.HttpServletRequest` |
| `javax.servlet.http.HttpServletResponse` | `jakarta.servlet.http.HttpServletResponse` |
| `javax.servlet.http.HttpSession` | `jakarta.servlet.http.HttpSession` |
| `javax.servlet.http.Cookie` | `jakarta.servlet.http.Cookie` |
| `javax.servlet.http.HttpServletRequestWrapper` | `jakarta.servlet.http.HttpServletRequestWrapper` |
| `javax.servlet.http.HttpServletResponseWrapper` | `jakarta.servlet.http.HttpServletResponseWrapper` |
| `javax.servlet.annotation.WebFilter` | `jakarta.servlet.annotation.WebFilter` |
| `javax.servlet.annotation.WebListener` | `jakarta.servlet.annotation.WebListener` |

### 5.1. Custom Filter

Before migration:

```java
import javax.servlet.FilterChain;
import javax.servlet.ServletException;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

import org.springframework.web.filter.OncePerRequestFilter;

public class RequestAuditFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        filterChain.doFilter(request, response);
    }
}
```

After migration:

```java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.filter.OncePerRequestFilter;

public class RequestAuditFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        filterChain.doFilter(request, response);
    }
}
```

The `OncePerRequestFilter` class remains a Spring class. The Servlet types in the method signature move to Jakarta. When compiling against Spring Framework 6, the overridden method must match the Jakarta types exactly.

### 5.2. Custom Servlet

```java
import jakarta.servlet.ServletException;
import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

@WebServlet("/legacy-status")
public class StatusServlet extends HttpServlet {

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

Applications using Spring MVC controllers normally do not write raw Servlets. However, legacy servlets, vendor integrations, and servlet registrations must still use Jakarta types when running on a Jakarta container.

### 5.3. Servlet Listener

```java
import jakarta.servlet.ServletContextEvent;
import jakarta.servlet.ServletContextListener;
import jakarta.servlet.annotation.WebListener;

@WebListener
public class StartupListener implements ServletContextListener {

    @Override
    public void contextInitialized(ServletContextEvent event) {
        // Initialize application resources.
    }

    @Override
    public void contextDestroyed(ServletContextEvent event) {
        // Release application resources.
    }
}
```

Verify listener registrations both in code and in deployment descriptors. A legacy listener may compile if the old API remains on the classpath, yet the new container will not recognize it as a Jakarta listener.

---

## 6. OAuth2 Resource Server: What Changes and What Stays the Same?

Spring Security Resource Server uses Spring's own packages. JWT/opaque token configuration normally does not require renaming Spring Security packages merely because the Servlet API changed namespaces.

`SecurityFilterChain` example:

```java
@Configuration
@EnableWebSecurity
public class ResourceServerSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/orders/**")
                    .hasAuthority("SCOPE_orders:read")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

Key imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;
```

Do not change `org.springframework.security` to `jakarta.security`.

### 6.1. `BearerTokenAuthenticationFilter` and Servlet Requests

Spring Security 6 uses the Jakarta Servlet API in its filter chain implementation. If an application defines custom filters, resolvers, or authentication handlers working with requests/responses, their method signatures must accept Jakarta types.

Custom authentication entry point example:

```java
@Component
public class ApiAuthenticationEntryPoint
        implements AuthenticationEntryPoint {

    @Override
    public void commence(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException exception)
            throws IOException {

        response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
        response.setContentType("application/json");
        response.getWriter().write(
            "{\"error\":\"unauthorized\"}"
        );
    }
}
```

Servlet imports move to `jakarta.servlet.http.*`; `AuthenticationEntryPoint` and `AuthenticationException` remain in `org.springframework.security.*`.

### 6.2. Custom `BearerTokenResolver`

```java
public final class HeaderOnlyBearerTokenResolver
        implements BearerTokenResolver {

    private final DefaultBearerTokenResolver delegate =
        new DefaultBearerTokenResolver();

    @Override
    public String resolve(HttpServletRequest request) {
        return delegate.resolve(request);
    }
}
```

Here `HttpServletRequest` must be `jakarta.servlet.http.HttpServletRequest`. `BearerTokenResolver` and `DefaultBearerTokenResolver` remain in Spring Security.

### 6.3. JWT and Opaque Token APIs Keep Their Namespaces

The following APIs remain Spring Security types:

- `JwtDecoder`
- `Jwt`
- `JwtAuthenticationConverter`
- `OAuth2TokenValidator<Jwt>`
- `OpaqueTokenIntrospector`
- `OAuth2AuthenticatedPrincipal`
- `BearerTokenAuthentication`
- `BearerTokenAuthenticationFilter`

If code interacts only with these types without referencing Servlet APIs directly, no package imports need to change solely for the Servlet migration.

### 6.4. `SecurityFilterChain` Is Spring Configuration, Not a Servlet API

`SecurityFilterChain` is still declared with Spring Security. However, the chain attaches to the Servlet container through Spring Security's filter infrastructure. Therefore, Spring Framework/Security dependencies must be compatible with the Jakarta Servlet API.

---

## 7. Spring Security 6 Has API Changes Beyond Namespaces

Upgrading Spring Boot 2 to 3 usually brings Spring Security 5 to 6. Several Spring Security APIs changed independently of `javax.servlet` moving to `jakarta.servlet`.

| Common Legacy Configuration | New Configuration Approach |
|---|---|
| `WebSecurityConfigurerAdapter` | Declare `SecurityFilterChain` and `WebSecurityCustomizer` beans as needed. |
| `antMatchers(...)` | `requestMatchers(...)`. |
| `mvcMatchers(...)` | `requestMatchers(...)` with the appropriate matcher. |
| `@EnableGlobalMethodSecurity` | `@EnableMethodSecurity`. |
| Overriding `configure(HttpSecurity)` | Configure using the lambda DSL in a `SecurityFilterChain` bean. |

Legacy example:

```java
@Override
protected void configure(HttpSecurity http) throws Exception {
    http
        .authorizeRequests()
        .antMatchers("/api/orders/**")
        .hasAuthority("SCOPE_orders:read");
}
```

New example:

```java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders:read")
            .anyRequest().denyAll())
        .oauth2ResourceServer(oauth ->
            oauth.jwt(Customizer.withDefaults()))
        .build();
}
```

Do not lump both categories of changes together. If the compiler reports missing `javax.servlet`, address namespace/dependencies. If the compiler reports missing `WebSecurityConfigurerAdapter` or `antMatchers`, that is Spring Security API migration.

---

## 8. Dependency Management: Choosing the Right Jakarta APIs

### 8.1. Use Spring Boot Dependency Management

With Spring Boot, prefer starters and the BOM from the same release line.

Maven:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>BOOT_VERSION</version>
    <relativePath/>
</parent>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

This example uses a placeholder version to illustrate BOM management; projects should select an organization-supported Spring Boot release and keep plugins/dependencies on the same release line.

### 8.2. Do Not Manually Add Servlet APIs If Starters Provide Them

For a Spring Boot web application running an embedded container, `spring-boot-starter-web` brings in the matching stack. Do not add an older Servlet API to the classpath.

When building a WAR for an external container, the Servlet API dependency can be declared with `provided` scope according to packaging requirements. In that case, use the Jakarta Servlet API version compatible with the target container.

Maven example when explicit API declaration is required:

```xml
<dependency>
    <groupId>jakarta.servlet</groupId>
    <artifactId>jakarta.servlet-api</artifactId>
    <scope>provided</scope>
</dependency>
```

Do not pin versions arbitrarily if the Spring Boot BOM already manages a compatible version.

### 8.3. Bean Validation Dependencies

If the application uses Bean Validation, update both the API and provider together:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
```

Spring Boot 3 typically uses a Hibernate Validator version compatible with Jakarta Validation. Do not swap annotation imports alone while leaving an older provider compiled against `javax.validation`.

### 8.4. Persistence Dependencies

If the application uses JPA:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.EntityManager;
```

Choose a Hibernate/JPA provider supporting Jakarta Persistence. An entity compiled against `javax.persistence.Entity` is not a Jakarta entity merely because the annotation name looks similar.

### 8.5. Avoid Mixing Old and New APIs

Do not put both `javax.servlet-api` and `jakarta.servlet-api` in the application to "make both work." They are two distinct APIs. A legacy library needs a proper Jakarta release or needs to be replaced/transformed.

---

## 9. Inspecting the Dependency Tree and Transitive Libraries

Updating imports in source code does not resolve transitive dependencies.

### 9.1. Maven

Inspect the dependency tree:

```bash
mvn dependency:tree
```

Filter relevant APIs:

```bash
mvn dependency:tree -Dincludes=javax.servlet:*,jakarta.servlet:*
```

Check dependency convergence and exclude old artifacts when evidence shows a newer dependency substitutes cleanly:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>legacy-integration</artifactId>
    <version>LIBRARY_VERSION</version>
    <exclusions>
        <exclusion>
            <groupId>javax.servlet</groupId>
            <artifactId>javax.servlet-api</artifactId>
        </exclusion>
    </exclusions>
</dependency>
```

Exclude only when the library no longer requires the old API or a compatible Jakarta artifact is present. An exclusion alone does not convert legacy bytecode to Jakarta.

### 9.2. Gradle

Inspect the dependency graph:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Locate legacy dependencies:

```bash
./gradlew dependencyInsight --dependency javax.servlet --configuration runtimeClasspath
```

When multiple configurations exist, check compile, runtime, test, and annotation processor configurations.

### 9.3. Inspecting Library Bytecode

A dependency may not declare `javax.servlet-api` directly yet still reference `javax/servlet/...` in its bytecode. Use `jdeps`, `jar tf`, and bytecode/dependency analysis tools to inspect class references inside JARs.

Example:

```bash
jdeps --recursive --multi-release 17 path/to/legacy-library.jar
```

`jdeps` helps identify package dependencies but does not replace runtime tests. Reflection, service loading, string-based class names, XML descriptors, and generated metadata may not show up clearly in static dependency graphs.

### 9.4. Classifying Each Dependency

For each library:

- Is there an official Jakarta-compatible version?
- Does the vendor publish a separate Jakarta artifact?
- Does the library use only Java SE, or does it directly reference Servlet/JPA/Validation?
- Does it ship with plugins, annotation processors, or generated sources?
- Is it still maintained?
- Can it be replaced with a Spring-native API?
- If temporarily transforming bytecode, are tests and a support policy in place?

Prefer upgrading to an official release or replacing unmaintained dependencies.

---

## 10. Embedded Containers and External Containers

The Servlet namespace must match the runtime container.

| Container Family | Servlet Namespace | Notes |
|---|---|---|
| Tomcat 9 | `javax.servlet` | Java EE Servlet 4.0 line. |
| Tomcat 10.0 | `jakarta.servlet` | Jakarta EE 9 namespace; the 10.0 branch is end-of-life. |
| Tomcat 10.1 | `jakarta.servlet` | Used in many Spring Boot 3.x setups; check matching Servlet API version. |
| Jetty 9/10 | Primarily Java EE namespace in older setups | Check exact distribution/module and version. |
| Jetty 11 | `jakarta.servlet` | Jakarta EE 9 era. |
| Jetty 12 | Supports multiple EE environments by module | Select the matching EE environment and compatible version. |
| Undertow | Depends on major/version and integration | Verify a Jakarta-compatible release. |

Do not stick with an older container just because the application compiles. External containers must provide the Servlet API required by the application and Spring Framework.

### 10.1. Embedded Deployment

When running a Spring Boot executable JAR, Boot manages the embedded container via the dependency graph. Upgrading the Boot release line normally brings in a compatible container.

### 10.2. WAR Deployment

When deploying a WAR:

- Confirm the external container supports the exact Jakarta Servlet API version.
- Put the container API in an appropriate scope, typically `provided`.
- Do not package an old Servlet API inside the WAR.
- Check container libraries for duplicate/legacy servlet classes.
- Check server startup logs and classloader behavior.
- Test deployment on the exact container version used in production.

### 10.3. You Cannot Fix a Legacy Library Just by Changing Server Versions

If a third-party JAR still implements `javax.servlet.Filter`, Tomcat 10.1 cannot automatically treat it as `jakarta.servlet.Filter`. You need a Jakarta release of the library, a source rebuild, or controlled transformation.

---

## 11. Migrating Deployment Descriptors and Annotations

### 11.1. `web.xml`

Applications using a Servlet deployment descriptor must check the version and schema namespace against the target Jakarta EE/Servlet level.

Jakarta Servlet 6.0 descriptor example:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<web-app
    xmlns="https://jakarta.ee/xml/ns/jakartaee"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
      https://jakarta.ee/xml/ns/jakartaee
      https://jakarta.ee/xml/ns/jakartaee/web-app_6_0.xsd"
    version="6.0">

    <display-name>orders-api</display-name>
</web-app>
```

Use a descriptor version compatible with the actual Servlet container. If the application does not need `web.xml`, do not introduce one just for migration.

### 11.2. Servlet Annotations

Update:

```java
import jakarta.servlet.annotation.WebFilter;
import jakarta.servlet.annotation.WebListener;
import jakarta.servlet.annotation.WebServlet;
```

Spring annotations such as `@RestController`, `@RequestMapping`, `@Component`, and `@Configuration` remain in Spring packages.

### 11.3. Lifecycle and Injection Annotations

Examples:

```java
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import jakarta.annotation.Resource;
```

`@PostConstruct` and `@PreDestroy` belong to Jakarta Common Annotations. If using `javax.annotation.processing.*` inside an annotation processor, keep it untouched because it is a Java compiler API.

### 11.4. JSP, JSTL, and Tag Libraries

If the application uses JSP, check both the Servlet JSP API and a Jakarta-compatible JSTL version. Some tag library URIs/versions changed under Jakarta Tags. Do not update only Java imports while overlooking JSP pages, TLD files, and taglib dependencies.

---

## 12. Custom Spring Filters and Filter Registration

### 12.1. Filters Extending Spring `OncePerRequestFilter`

`OncePerRequestFilter` remains a Spring class. Only the Servlet types in the overridden method signature move to Jakarta.

```java
@Component
public class CorrelationIdFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        String correlationId =
            request.getHeader("X-Correlation-Id");

        if (correlationId == null || correlationId.isBlank()) {
            correlationId = UUID.randomUUID().toString();
        }

        response.setHeader("X-Correlation-Id", correlationId);
        chain.doFilter(request, response);
    }
}
```

Required imports:

```java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.filter.OncePerRequestFilter;
```

### 12.2. `FilterRegistrationBean`

`FilterRegistrationBean` remains part of Spring Boot:

```java
@Bean
FilterRegistrationBean<CorrelationIdFilter> correlationFilter(
        CorrelationIdFilter filter) {
    FilterRegistrationBean<CorrelationIdFilter> registration =
        new FilterRegistrationBean<>();
    registration.setFilter(filter);
    registration.addUrlPatterns("/api/*");
    registration.setOrder(10);
    return registration;
}
```

The generic type must be a Jakarta-compatible `Filter` implementation. Verify the same filter is not registered twice: once via Servlet container registration and once inside the Spring Security chain.

### 12.3. Filters Inside `SecurityFilterChain`

If a filter performs security duties, usually register it within the Spring Security chain using the appropriate mechanism:

```java
http.addFilterBefore(
    correlationIdFilter,
    BearerTokenAuthenticationFilter.class
);
```

Filter order matters. Do not arbitrarily place a custom authentication/authorization filter before or after the Bearer filter without understanding exception handling, `SecurityContext` lifecycle, and async dispatch behavior.

### 12.4. Async and Error Dispatches

After migration, test all of:

- Normal request dispatches.
- Async dispatches if the filter supports them.
- Error dispatches.
- Request/response wrappers.
- Filter ordering and dispatcher types.
- `SecurityContext` propagation.

These issues are not strictly namespace bugs, yet they often surface when custom filters are recompiled.

---

## 13. Authentication Handlers, Resolvers, and Servlet Adapters

Spring Security classes can accept Servlet types in method signatures.

Example:

```java
public class JsonBearerEntryPoint
        implements AuthenticationEntryPoint {

    @Override
    public void commence(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException authException)
            throws IOException {

        response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
        response.setContentType("application/json");
        response.getWriter().write(
            "{\"error\":\"invalid_token\"}"
        );
    }
}
```

Imports:

```java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.AuthenticationEntryPoint;
```

Similarly, check extension points:

- `AuthenticationEntryPoint`
- `AccessDeniedHandler`
- `BearerTokenResolver`
- `AuthenticationFailureHandler`
- `AuthenticationSuccessHandler`
- `RequestMatcher`
- `SecurityContextRepository`
- Custom `Filter` or `HandlerInterceptor`
- Custom servlet request/response wrappers

Spring interfaces retain their Spring namespaces. Only the Servlet parameter types change.

---

## 14. Spring MVC, WebFlux, and Migration Boundaries

Not every Spring application uses the Servlet API.

### 14.1. Spring MVC

Spring MVC runs on the Servlet stack. Controllers rarely import Servlet types directly, though custom filters, servlet listeners, request wrappers, and security adapters may require updates.

### 14.2. Spring WebFlux

WebFlux uses reactive HTTP abstractions such as `ServerWebExchange` and does not rely on the Servlet API in its primary execution model. Imports from `org.springframework.web.server`, `org.springframework.http.server.reactive`, and Spring Security reactive APIs do not change to Jakarta Servlet types.

If an application includes both MVC and WebFlux dependencies, identify which stack the application actually runs. Do not add Servlet APIs solely because Spring Security OAuth2 Resource Server is present.

### 14.3. Reactive Resource Server

Reactive security configuration typically uses `SecurityWebFilterChain` and `ServerHttpSecurity`:

```java
@Bean
SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
    return http
        .authorizeExchange(auth -> auth
            .pathMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders:read")
            .anyExchange().denyAll())
        .oauth2ResourceServer(oauth ->
            oauth.jwt(Customizer.withDefaults()))
        .build();
}
```

These are Spring WebFlux APIs and do not migrate to Jakarta Servlet APIs. If reactive code relies on a Servlet-based integration library, evaluate that dependency's migration scope separately.

---

## 15. Spring Security Test and MockMvc After Migration

Spring Test and Spring Security Test packages remain in Spring namespaces:

```java
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors;
```

MockMvc did not change namespaces. However, Spring Framework 6 and Spring Security 6 use the Jakarta Servlet API underneath.

### 15.1. MockMvc with Bearer Tokens

Filter-flow test example:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ResourceServerMigrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void protectedEndpointRejectsMissingBearerToken()
            throws Exception {
        mvc.perform(get("/api/orders/42"))
            .andExpect(status().isUnauthorized());
    }
}
```

### 15.2. Authorization-Only Tests

Spring Security Test post-processors such as `jwt()` still belong to Spring Security Test:

```java
mvc.perform(get("/api/orders/42")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders:read"))))
    .andExpect(status().isOk());
```

This test is useful for authorization rules. It does not prove that the JWT decoder or Servlet Bearer filter verified a real compact token.

### 15.3. Filter-Flow Tests

To test the Resource Server filter chain, send a Bearer header using a real decoder or a targeted mock decoder:

```java
mvc.perform(get("/api/orders/42")
        .header(
            HttpHeaders.AUTHORIZATION,
            "Bearer " + signedTestToken))
    .andExpect(status().isOk());
```

For migration tests, confirm custom filters and servlet integrations run on Jakarta types. Keep signature/issuer/audience tests separate from namespace compatibility tests so failures are easy to diagnose.

### 15.4. Testing Servlet Mocks

If tests directly reference Servlet APIs, check imports:

```java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.mock.web.MockHttpServletRequest;
```

`MockHttpServletRequest` is a Spring mock class; its instances implement Jakarta Servlet contracts in Spring Framework 6. Do not use a mock/request from an older test library implementing `javax` contracts.

---

## 16. Third-Party Libraries and Frequently Overlooked Migration Points

An application can compile cleanly yet still load legacy libraries at runtime.

| Category | Examples to Check |
|---|---|
| Security integrations | SAML adapters, custom authentication filters, identity provider SDKs. |
| Servlet filters | WAF agents, tracing agents, compression, session, audit filters. |
| Persistence | JPA providers, entity listeners, custom Hibernate types. |
| Validation | Bean Validation providers and custom constraints. |
| JSON/XML | JAXB, XML bind adapters, SOAP/JAX-WS dependencies. |
| REST clients/servers | JAX-RS implementations, providers, servlet bridges. |
| Messaging | Jakarta Mail, JMS, messaging adapters. |
| CDI/injection | CDI extensions, `javax.inject` consumers. |
| Observability | APM Java agents, servlet instrumentation, tracing libraries. |
| Code generation | OpenAPI generators, annotation processors, generated stubs. |
| Testing | Mock servlet libraries, embedded containers, test fixtures. |
| Build plugins | Packaging, bytecode weaving, shading, enhancement plugins. |

### 16.1. APM Agents and Java Agents

An agent may instrument Servlet API method signatures. If an older agent recognizes only `javax.servlet`, it may fail to instrument Jakarta requests or cause linkage errors.

Check the agent version, bytecode transformers, and startup flags. Never assume an agent is compatible merely because the application compiles.

### 16.2. Generated Source

Code generated from OpenAPI, WSDL, JAXB, or annotation processors may still emit `javax.*` imports. Upgrade the generator/plugin and regenerate sources. Do not manually edit generated files if the next build overwrites them.

### 16.3. Shaded/Fat JAR Dependencies

A library may bundle API classes or relocate packages. Inspect JAR contents, service provider files, and manifests. Do not stuff the old API into a fat JAR to mask classloading errors.

---

## 17. Handling Libraries Available Only in `javax`

Prioritize in this order:

1. Upgrade to an official version supporting Jakarta.
2. Use a Jakarta-variant artifact if the vendor publishes one.
3. Replace the library with a maintained implementation.
4. If source is available, fork/rebuild and validate the full API surface.
5. Use bytecode transformation only as a controlled last resort when no viable alternative exists.

### 17.1. Why Simply Excluding the Old Dependency Fails

If a pre-compiled library exposes a method:

```java
public void register(javax.servlet.Filter filter)
```

excluding `javax.servlet-api` from the dependency tree causes missing classes at runtime. Adding `jakarta.servlet-api` does not rewrite the method signature.

### 17.2. Transformation Tools

Tools exist to transform Java EE namespaces to Jakarta, such as Eclipse Transformer or the Apache Tomcat Jakarta EE Migration Tool. They can help bridge a legacy application/library during migration.

However, transformation has limits:

- It does not replace upgrading to a vendor-supported release.
- Reflection or class names stored as strings may require inspection.
- Serialized data, service descriptors, and XML resources require verification.
- Not every third-party integration can be transformed safely.
- Licensing/support and reproducible artifact builds must be verified.
- It must be tested on the exact runtime container.

Do not turn a transformed JAR into a permanent production dependency without an owner, a reproducible build, and a replacement plan.

---

## 18. Step-by-Step Migration Strategy

A safe migration should be broken into controllable changes.

### Step 1: Capture the Current Baseline

Record:

- Java version.
- Spring Boot/Framework/Security versions.
- Servlet container and version.
- Build tool and dependency tree.
- Custom filters, listeners, and servlets.
- Integration libraries.
- Test baseline and deployment target.
- OAuth2 Resource Server configuration.

Keep the baseline to separate pre-existing issues from migration regressions.

### Step 2: Check the Compatibility Matrix

Verify:

- The Spring Boot release supports the current Java runtime.
- Spring Framework/Security versions are managed by Boot.
- The Servlet container supports the required Jakarta API.
- OAuth2/JWT/JWK/introspection libraries are compatible.
- Vendor libraries and agents have Jakarta releases.

Do not upgrade a single Spring Security JAR outside the BOM without a clear compatibility rationale.

### Step 3: Inventory Namespace Imports

Search for imports likely needing conversion:

```bash
rg -n "javax\.(servlet|validation|persistence|annotation|inject|ws\.rs|websocket|enterprise|transaction|xml\.bind|mail|activation)" src
```

Then classify each result. Never run a global replace across all `javax`.

Search for Servlet references in generated sources and test sources, not just the `main` directory.

### Step 4: Upgrade Frameworks and Dependencies Together

- Move to the target Spring Boot release line.
- Let the BOM/parent manage versions.
- Upgrade Spring Security along the same release line.
- Upgrade Jakarta-compatible providers and integrations.
- Remove legacy `javax` API dependencies only after all consumers are updated.
- Switch the JDK toolchain and CI runtime.

### Step 5: Update Source Code by Specific Package

Update Servlet imports and required Jakarta EE imports. Keep Java SE `javax` imports. Update custom filters, servlet adapters, listeners, validation/persistence annotations, and generated sources.

### Step 6: Update Containers/Descriptors

- Select a Jakarta-compatible embedded/external container.
- Update `web.xml` if present.
- Check servlet registrations and listener declarations.
- Check WAR packaging scopes.
- Check APM/agent support.

### Step 7: Compile and Inspect the Dependency Graph

Run main and test compilation and inspect the dependency tree. Address every library still referencing legacy `javax` APIs. Never mask errors by putting both Servlet APIs on the classpath.

### Step 8: Run Layered Tests

- Unit tests for custom filters/resolvers.
- Spring Security MockMvc tests.
- Signed JWT filter-flow tests.
- Opaque introspection tests.
- Integration tests with the target container.
- End-to-end tests through the gateway if applicable.

### Step 9: Deploy to Staging and Observe

Verify startup logs, classloading, filter registration, endpoint health, JWT validation, 401/403 behavior, downstream calls, metrics, and traces.

### Step 10: Controlled Rollout

Retain rollback artifacts and matching configuration. Monitor error rates, classloading exceptions, auth failures, latency, and container restarts. Remove compatibility workarounds only after every runtime has migrated.

---

## 19. Common Failures and How to Diagnose Them

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `ClassNotFoundException: javax.servlet.Filter` | Legacy dependency references old Servlet API | Upgrade/rebuild the library or replace the dependency. |
| `NoClassDefFoundError: javax/servlet/...` | Legacy bytecode or agent requires `javax` class | Inspect stack trace and dependency origin; do not blindly add the old API. |
| `ClassCastException` between `javax` and `jakarta` Filter | Two incompatible interfaces | Use a Jakarta-compatible implementation. |
| `method does not override or implement a method` | Custom filter override still uses `javax` parameter types | Switch the relevant Servlet imports to `jakarta`. |
| Spring context fails to build `SecurityFilterChain` | Spring Security API/config migration or dependency mismatch | Check version/BOM, DSL, and bean configuration. |
| Protected endpoints suddenly return widespread 401s | Filter chain, decoder, issuer/JWKS, or deployment config changed | Check startup logs, token validation, and chain matchers. |
| Custom filter does not execute | Wrong type, ordering, or double registration | Check bean/Servlet registration and `SecurityFilterChain` order. |
| WAR works locally but fails on server | External container still uses `javax` or wrong Servlet level | Pick a Jakarta-compatible container. |
| Build passes but production fails | Runtime dependency/agent/container incompatible | Check `runtimeClasspath` and the actual deployment artifact. |
| Annotation validation stops working | `javax` and `jakarta` validation API/providers mixed | Upgrade provider and annotations together. |
| JPA entities are not detected | Entities still use `javax.persistence` | Move to `jakarta.persistence` and upgrade the provider. |
| Generated source re-emits `javax` imports | Older generator/plugin version | Upgrade generator, configure namespace, and regenerate. |
| Tests compile but servlet mocks fail | Legacy test library or mock implements `javax` contracts | Upgrade Spring Test/security-test and mock dependencies. |
| TLS/crypto code fails after replacement | Java SE `javax` packages were accidentally renamed | Restore `javax.crypto`/`javax.net` imports. |

### 19.1. Reading Stack Traces by Classloader Origin

When encountering a linkage error:

1. Find the first frame belonging to application code or a third-party library.
2. Determine whether the class references `javax/...` or `jakarta/...`.
3. Identify the JAR containing that class via the dependency tree or archive inspection.
4. Identify which dependency brings the old API into runtime.
5. Check which API the classloader/container supplies.
6. Fix the dependency source or replace the artifact.
7. Re-test on the actual target container, not just embedded tests.

Do not work around it by dropping a random Servlet API JAR into `lib`. That can introduce classloader conflicts and will not turn a legacy `Filter` into a Jakarta `Filter`.

### 19.2. Distinguishing Namespace Errors from Security API Errors

Examples:

- Missing `jakarta.servlet.Filter`: Jakarta Servlet dependency/container issue.
- Missing `WebSecurityConfigurerAdapter`: Spring Security 6 API change.
- Missing `javax.crypto.SecretKey`: Java SE/runtime/module issue or accidental rename.
- Missing `JwtDecoder` in context: OAuth2 Resource Server configuration/dependency issue, not a Servlet namespace issue.

---

## 20. Migration Checklist for OAuth2/OIDC Resource Server

| Area | What to Confirm |
|---|---|
| **Java runtime** | Build and production use JDK 17+ when moving to Spring Boot 3. |
| **Spring Boot** | Selected version manages matching Spring Framework/Security versions. |
| **Servlet namespace** | Custom filters, handlers, and listeners use `jakarta.servlet`. |
| **Java SE namespace** | `javax.crypto`, `javax.net`, `javax.sql`, `javax.naming`, `javax.xml.parsers` remain intact. |
| **Spring imports** | `org.springframework.*` was not changed to `jakarta.*`. |
| **JWT API** | `JwtDecoder`, `Jwt`, and validators still use Spring Security packages. |
| **Opaque token** | `OpaqueTokenIntrospector` and dependencies are compatible. |
| **Custom filter** | Method signatures use Jakarta request/response/filter chain types. |
| **Filter registration** | No double registration; ordering is accurate. |
| **Security configuration** | Uses `SecurityFilterChain` and Spring Security 6-compatible APIs. |
| **Audience/issuer** | Validators preserve the trust policy after changing decoder/config. |
| **Servlet container** | Embedded/external container supports the required Jakarta Servlet version. |
| **WAR packaging** | Does not bundle the wrong Servlet API version; `provided` scope is correct. |
| **Transitive dependencies** | No remaining legacy library requires the `javax` Servlet API at runtime. |
| **Generated code** | Generators/plugins emit Jakarta imports. |
| **Annotations** | Common Annotations, Validation, and Persistence use the new APIs; compiler APIs stay unchanged. |
| **Descriptors** | `web.xml`/JSP/tag libraries match the target container. |
| **Tests** | MockMvc and Spring Security Test are upgraded compatibly. |
| **Filter flow** | Bearer headers pass through the real filter chain. |
| **Runtime** | Runs on the real target container or matching major/version. |
| **Observability** | Logs/traces never expose tokens; auth failures and classloading are monitored. |
| **Rollback** | Previous artifacts and configs remain rollback-ready during the rollout window. |

---

## 21. End-to-End Example: Servlet Resource Server After Migration

Overall configuration example:

```java
@Configuration
@EnableWebSecurity
public class ResourceServerConfiguration {

    @Bean
    SecurityFilterChain apiFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .securityMatcher("/api/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders:read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders:write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

If a custom filter is present:

```java
@Component
public class SecurityAuditFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        try {
            chain.doFilter(request, response);
        } finally {
            // Record a redacted event. Never record the raw token.
        }
    }
}
```

Related imports:

```java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.filter.OncePerRequestFilter;
```

In this migration:

- Servlet method parameters move to Jakarta.
- The Spring filter base class remains Spring.
- Security configuration remains Spring Security.
- JWT decoder and authorities continue using Spring Security types.
- Java cryptography/TLS imports stay in the Java SE namespace.
- OAuth issuer, audience, scope, and token validation policies remain unchanged per security design.

That is the goal of a properly scoped migration: changing the platform API boundary without unintentionally altering authorization semantics.

---

## 22. Verifying Behavior Before and After Migration

Namespace migration can prevent an application from starting, or it can alter security behavior if configuration is adjusted at the same time. Keep a before/after behavior test suite for comparison.

| Scenario | Expected Outcome |
|---|---|
| Public endpoint request | Matches existing public policy. |
| Protected endpoint without token | 401 or current entry point contract. |
| JWT with invalid signature | 401. |
| JWT with wrong issuer/audience | 401. |
| Expired JWT / invalid not-before | 401. |
| Valid JWT missing scope | 403. |
| Valid JWT with required scope | Allowed if object policy also permits. |
| Inactive opaque token | Authentication rejected. |
| Cross-tenant request | Rejected per object/tenant policy. |
| Custom Servlet filter | Executes once per dispatcher policy. |
| Custom authentication entry point | Response status/content type/body match contract. |
| Async/error dispatch | Does not lose security context or bypass filter policy. |

### 22.1. Do Not Use Migration to Change Policies Unintentionally

If an endpoint required `SCOPE_orders:write` before migration, do not accidentally relax it to `authenticated()` after migration just to make tests pass.

When an authorization policy change is needed, document and test it separately. That keeps regressions caused by namespaces, framework APIs, and security design clearly separable.

---

## 23. Rollback and Post-Migration Operations

### 23.1. Artifacts and Runtime Must Roll Back Together

Do not roll back only the application while keeping the new Jakarta container if the older artifact supports only `javax`. Conversely, do not deploy a Jakarta artifact onto a legacy Java EE container.

A rollback unit should include:

- Application artifact.
- Runtime/container version.
- JDK version.
- Relevant configuration.
- Secret/issuer/JWKS settings if altered.
- Database/schema changes if another migration ran alongside it.

### 23.2. Canary and Telemetry

Monitor:

- Application startup/restart rates.
- `ClassNotFound`/`NoClassDef`/`LinkageError`.
- HTTP 401/403 distribution.
- JWT decoder/JWKS failures.
- Introspection latency/errors.
- Request latency and throughput.
- Custom filter invocations.
- Downstream failure rates.
- Servlet container thread/connection pools.

A spike in 401s after migration may stem from issuer/audience config, filter chains, decoder beans, or clock/identity dependencies. Do not assume every 401 is a namespace failure.

### 23.3. Cleaning Up Legacy Compatibility

Once all services have fully migrated:

- Remove unused `javax` API dependencies.
- Remove temporary exclusions/workarounds.
- Remove transformed artifacts once replaced by vendor releases.
- Update build/deployment documentation.
- Record the container/JDK baseline.
- Retain dependency graph and runtime behavior tests.

---

## 24. Misconceptions to Avoid

| Misconception | Reality |
|---|---|
| Every `javax.*` package moves to `jakarta.*`. | Java SE packages like crypto, net, sql, naming, and many XML APIs remain unchanged. |
| Just search-and-replace `javax` with `jakarta`. | Can break Java SE imports, strings, generated code, and unrelated packages. |
| Spring Security packages also move to `jakarta.security`. | Spring APIs remain under `org.springframework.security.*`. |
| Adding `jakarta.servlet-api` makes `javax` libraries run. | The two interfaces are distinct; legacy bytecode must be upgraded or transformed. |
| Tomcat 10 automatically runs every Tomcat 9 application. | The Servlet namespace changed; legacy applications require migration. |
| Only source imports need updating. | Transitive JARs, agents, descriptors, generated code, and test mocks must also be compatible. |
| JWT/OIDC protocols change because of the Servlet namespace. | OAuth2/OIDC protocol semantics do not change merely because the Servlet API package changed. |
| 401s after migration are always a broken decoder. | They can stem from the filter chain, issuer/audience, wrong container, dependencies, or token config. |
| `javax.transaction.xa` must change along with `javax.transaction`. | The XA API belongs to Java SE and keeps `javax.transaction.xa`. |
| `javax.xml.validation` changes along with `javax.validation`. | XML validation belongs to Java SE; only the legacy Bean Validation API changed namespaces. |

---

## 25. Technical References

- [Spring Boot 3.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide): Java 17 requirement, Jakarta EE migration, and platform changes.
- [Spring Framework 6.0 Overview](https://docs.spring.io/spring-framework/reference/overview.html): Java baseline and Jakarta EE support.
- [Spring Security 6 Migration Guide](https://docs.spring.io/spring-security/reference/6.0/migration/index.html): API and configuration changes when upgrading Spring Security.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT Resource Server on the Servlet stack.
- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): opaque token introspection.
- [Jakarta EE 9 Platform](https://jakarta.ee/specifications/platform/9/): namespace transition and platform specifications.
- [Jakarta Servlet Specification](https://jakarta.ee/specifications/servlet/): Servlet API and compatibility.
- [Apache Tomcat Migration Guide — Tomcat 9 to 10](https://tomcat.apache.org/migration-10.html): namespace differences moving from Tomcat 9 to Tomcat 10.
- [Apache Tomcat Jakarta EE Migration Tool](https://github.com/apache/tomcat-jakartaee-migration): tool for transforming legacy applications during migration.
- [Eclipse Transformer](https://github.com/eclipse-transformer/transformer): tool for converting Jakarta namespaces in artifacts.
- [Java SE API Documentation](https://docs.oracle.com/en/java/javase/): distinguishing Java SE packages that remain in the `javax` namespace.
- [Maven Dependency Plugin](https://maven.apache.org/plugins/maven-dependency-plugin/): analyzing the dependency tree.
- [Gradle Dependency Insight](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): tracing legacy dependency sources in the dependency graph.

**Conclusion:** Migrating Servlet from `javax` to Jakarta is an API- and bytecode-level namespace migration, typically accompanying Spring Boot 3, Spring Framework 6, and Spring Security 6. Convert Jakarta EE packages while leaving packages like `javax.crypto`, `javax.net`, `javax.sql`, `javax.naming`, `javax.xml.parsers`, and `javax.transaction.xa` untouched. These Java SE packages keep their namespace; only `javax.servlet` and the corresponding Jakarta EE APIs move to `jakarta`. Spring Security packages remain in `org.springframework.security`. Verify transitive dependencies, generated code, filters, descriptors, tests, and the runtime container to ensure the entire application speaks the same Servlet contract. Migration is complete only when the API boots and OAuth2 authentication/authorization behavior remains accurate on the target Jakarta runtime.
