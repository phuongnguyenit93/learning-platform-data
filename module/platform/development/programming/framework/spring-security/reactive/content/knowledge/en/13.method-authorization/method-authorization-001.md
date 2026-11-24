# Enable @EnableReactiveMethodSecurity and Choose AuthorizationManager Mechanism by Version

## 1. Objectives

In **reactive** Spring Security (Spring WebFlux), protecting URLs with `ServerHttpSecurity.authorizeExchange(...)` is an important layer of defense, but it does not replace checking permissions directly at the **service method**. A service may be called from a REST controller, GraphQL handler, message consumer, job, or another service. If permissions are only checked on one URL, calls coming through another path may not be subject to the same policy.

Spring Security provides `@EnableReactiveMethodSecurity` to enable method security integrated with **Reactor Context**, and starting from the 5.8 branch introduced a new model based on `ReactiveAuthorizationManager`. Which configuration to use must be based on the **actual Spring Security version**, not merely the Java version or a blog example.

After this lesson, you will be able to:

1. Enable reactive method security properly and distinguish it from Servlet's `@EnableMethodSecurity`.
2. Understand the history of `useAuthorizationManager` and choose the appropriate default for Spring Security 5.8, 6.x, and 7.x.
3. Explain the flow of `@PreAuthorize`, `@PostAuthorize`, AOP proxies, Reactor Context, and `ReactiveAuthorizationManager`.
4. Write Spring Boot WebFlux Java 17+ examples using `Mono`, `Flux`, and various roles and authorities.
5. Test with HTTP and `StepVerifier`, and identify errors caused by proxies, context, annotations, and version dependencies.

**Scope:** this lesson focuses on reactive method security in Spring Security, not `HttpSecurity`, `SecurityFilterChain`, `@EnableGlobalMethodSecurity`, or standard Servlet `MethodInterceptor` configuration.

## 2. Why is method security needed?

Suppose the API `GET /api/admin/report` is already controlled at the HTTP layer. However, `reportService.exportSensitiveReport()` is also called from another unprotected endpoint or from a non-HTTP processing flow. When adding:

~~~java
@PreAuthorize("hasRole('ADMIN')")
public Mono<String> exportSensitiveReport() {
    return Mono.just("SECRET_REPORT");
}
~~~

Spring Security places a **method-security interceptor** around the method on a Spring-managed bean. Before allowing the method to emit results, the interceptor uses the `Authentication` information and the expression `hasRole('ADMIN')` to decide authorization. If permissions are insufficient, the publisher terminates with an access error (typically `AccessDeniedException`/`AuthorizationDeniedException`, depending on the version) instead of returning data to the caller.

Method security is beneficial when:

- A business operation is shared across multiple entry points.
- Permissions depend on method parameters, resource owner, tenant, or authority.
- A controller accidentally omits an HTTP matcher, yet the service still has an independent layer of protection.
- There is a requirement to enforce control both **before execution** and **before returning results**.

However, method security **does not replace** HTTP security. HTTP filters also handle authentication, CSRF, CORS, URL routing, entry points, and HTTP 401/403. Good design uses both for *defense in depth*.

## 3. Where to enable @EnableReactiveMethodSecurity?

With Spring Boot WebFlux, you can place the annotation on a `@Configuration` class, or directly on the main application class annotated with `@SpringBootApplication`:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableReactiveMethodSecurity
class ReactiveMethodSecurityConfig {
}
~~~

This is a **configuration snippet**, requiring imports:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
~~~

If you place the annotation on the `@SpringBootApplication` class, you do not need to create a separate configuration class. Avoid declaring multiple method security configurations simultaneously without purpose; they can lead to duplicate advisors or conflicts.

**Key point:** merely adding `spring-boot-starter-security` does not automatically enable all service security annotations. You must declare `@EnableReactiveMethodSecurity` so Spring creates the necessary proxies/advisors.

### 3.1. Choosing the right annotation for the stack

| Platform | Annotation to use | Reason |
| --- | --- | --- |
| Spring WebFlux + `Mono`/`Flux` | `@EnableReactiveMethodSecurity` | Integrates Reactor Context and reactive method interceptors |
| Spring MVC/Servlet | `@EnableMethodSecurity` | Method security in Servlet / synchronous stack |
| Very old Servlet projects | `@EnableGlobalMethodSecurity` (legacy) | Not a choice for new code; do not copy to WebFlux |
| Separate HTTP configuration for WebFlux | `@EnableWebFluxSecurity` and `SecurityWebFilterChain` | Protects requests; does not automatically replace method security |

A codebase with both MVC and WebFlux dependencies needs to verify whether the application actually runs `REACTIVE` or `SERVLET`. Do not use `@EnableMethodSecurity` just because its name is shorter: it is a different annotation with different semantics and processing mechanisms.

## 4. Choosing useAuthorizationManager by version

This is the core of the lesson. The `useAuthorizationManager` attribute was added in Spring Security 5.8 to transition from the legacy method security pipeline to interceptors based on `ReactiveAuthorizationManager`.

### 4.1. Compatibility table

| Spring Security | Recommended configuration | Explanation |
| --- | --- | --- |
| **5.7 and earlier** | `@EnableReactiveMethodSecurity` | `useAuthorizationManager` does not exist yet; do not add a non-existent attribute |
| **5.8.x** | `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` | **Must opt-in** to use reactive AuthorizationManager; 5.8 Javadoc states default is **false** |
| **6.0.x** | Prefer `@EnableReactiveMethodSecurity` on a patched release; check Javadoc/patch | The 6.0 migration guide switched default to true, but very early patch versions had discrepancies between docs and code; use a patched 6.0.x release |
| **6.1–6.5.x** | `@EnableReactiveMethodSecurity` | Default `useAuthorizationManager = true`; omit redundant attribute in new code |
| **7.0–7.1.x** | `@EnableReactiveMethodSecurity` | 7.1 Javadoc confirms default is true; AuthorizationManager-based approach is the default |
| **Later versions** | Check Javadoc of the **resolved** dependency | API may change; do not assume a permanent default |

The following two configurations are equivalent regarding manager selection on versions where **default is true**:

~~~java
@EnableReactiveMethodSecurity

// Explicit but unnecessary in Spring Security 6.5 / 7.1:
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
~~~

These are **two separate options** to place on a class, not two annotations to use together.

**Version evidence:** Spring Security 5.8.16 Javadoc states `useAuthorizationManager` defaults to `false`; Spring Security 7.1 Javadoc states `true`. The 6.5 migration documentation confirms the shift from explicit configuration to the shorthand annotation after the default changed in 6.0. When encountering a very old 6.0.0 application, verify the exact patch and prioritize upgrading rather than relying on assumptions.

### 4.2. Relation to Spring Boot

The Spring Boot BOM manages Spring Security versions when you use Boot's parent/BOM:

- **Spring Boot 3.5.x** pairs with the Spring Security **6.5.x** branch per the corresponding BOM patch; minimum Java 17.
- **Spring Boot 4.1.x** pairs with the Spring Security **7.1.x** branch per the corresponding BOM patch; minimum Java 17.
- Projects that override `spring-security-config`, `spring-security-core`, or `spring-security-web` may run a different version than the Boot documentation you are reading. Inspect the dependency graph.

On Maven:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework.security
./mvnw help:effective-pom
~~~

On Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-config \
  --configuration runtimeClasspath
~~~

On PowerShell/Windows, use `.\mvnw.cmd` or `.\gradlew.bat` respectively and put the command on a single line if the shell does not support Bash-style line continuation. Do not merely check the version of `spring-security-web` and assume all security modules share the same version; verify actual dependency resolution.

### 4.3. Should useAuthorizationManager=false be used?

**Do not use in new code.** Setting `false` selects the legacy method security mechanism; some newer versions require adding the `spring-security-access` module for legacy metadata/voter infrastructure. Only consider this when maintaining a legacy system for a clear reason, after reading the exact version's migration notes, and with a removal plan.

Do not use `false` to "fix" a 403 error without finding the root cause; it can inadvertently alter how permissions are evaluated across all services.

## 5. Differences between the new AuthorizationManager and the legacy pipeline

### 5.1. Legacy model

In the legacy architecture, the system could use:

- `MethodSecurityMetadataSource` to read metadata/annotations.
- `ConfigAttribute` to represent conditions.
- `AccessDecisionManager` and `AccessDecisionVoter` instances to vote.
- Legacy interceptors tightly coupled to the abstractions above.

This model was complex when customizing, testing, or integrating with Reactor.

### 5.2. ReactiveAuthorizationManager-based model

With `useAuthorizationManager = true`, reactive Spring Security creates advisors/interceptors corresponding to annotations such as:

| Annotation | Check point | Related component |
| --- | --- | --- |
| `@PreAuthorize` | Before the call / before the publisher is allowed to run | `AuthorizationManagerBeforeReactiveMethodInterceptor` |
| `@PostAuthorize` | After the reactive result is produced, before emitting to caller | `AuthorizationManagerAfterReactiveMethodInterceptor` |
| `@PreFilter` | Filters input parameter collections (when applicable) | `PreFilterAuthorizationReactiveMethodInterceptor` |
| `@PostFilter` | Filters result elements (when applicable) | `PostFilterAuthorizationReactiveMethodInterceptor` |

The manager interface in Spring Security 7.1 has the signature:

~~~java
public interface ReactiveAuthorizationManager<T> {
    Mono<AuthorizationResult> authorize(
            Mono<Authentication> authentication, T object);

    // verify(...) is the default method to check authorization.
}
~~~

This is an **abbreviated signature**, not the entire source. `AuthorizationResult.isGranted()` represents the outcome; some older APIs/snippets use `AuthorizationDecision` (a result implementation) or `check(...)` returning `AuthorizationDecision`. In newer versions, prefer `authorize(...)` and `AuthorizationResult` per the specific Javadoc.

For method security, the object `T` is typically `org.aopalliance.intercept.MethodInvocation`, which contains method, target, and arguments information. A custom manager can make decisions based on identity, authorities, parameters, or business domain policy. A manager returning `Mono.empty()` can mean abstain/no decision made; **do not treat empty as a deny-all mechanism** when you want to fail closed.

### 5.3. Before method and after method are not the same

Example:

~~~java
@PreAuthorize("hasRole('ADMIN')")
public Mono<String> createReport() {
    return Mono.just("REPORT_READY");
}

@PostAuthorize("returnObject == authentication.name")
public Mono<String> readUsername(String selectedName) {
    return Mono.just(selectedName);
}
~~~

Both methods are snippets placed inside a Spring bean. With `@PreAuthorize`, authorization is determined before allowing the method to run. With `@PostAuthorize`, the value already computed/emitted in the internal stream can be checked afterward, before being passed to the external subscriber.

**Do not use `@PostAuthorize` to protect operations with side effects** such as transferring money, deleting records, or sending emails: the action may have already occurred before the post-check denies it. For state-changing operations, check beforehand and enforce business authorization at the transaction boundary.

## 6. Reactor Context: the source of Authentication

In Spring MVC/Servlet, code is often accustomed to `ThreadLocal`-based `SecurityContextHolder`. In WebFlux, a request may execute across multiple threads. Reactive method security retrieves information from the **Reactor Context**, provided by `ReactiveSecurityContextHolder`.

~~~text
HTTP request + credentials
         |
         v
SecurityWebFilterChain / AuthenticationWebFilter
         |
         v
SecurityContext is put into Reactor Context
         |
         v
Controller calls Spring-managed service proxy
         |
         v
Method interceptor reads Authentication in Reactor Context
         |
         +-- ALLOW -> subscription to method's Mono/Flux
         |
         +-- DENY  -> Publisher emits AccessDeniedException
         |
         v
ExceptionTranslationWebFilter / WebFlux error handling
         |
         v
HTTP 401 or 403 depending on status and mechanism
~~~

**Important condition:** the method should return `org.reactivestreams.Publisher` (typically `Mono<T>`, `Flux<T>`) so the security interceptor integrates with the context at subscription time. Coroutine applications on supported branches have their own rules, so consult the documentation for your exact Kotlin/Spring Security version.

Example of reading context in a pipeline:

~~~java
Mono<String> currentUserName = ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
~~~

This snippet requires importing `ReactiveSecurityContextHolder`, `SecurityContext`, `Authentication`, and `Mono`. When no corresponding context exists, the publisher can be empty; do not turn empty into a default "admin" account.

In unit tests without an HTTP request, you can attach context using:

~~~java
Authentication user = new TestingAuthenticationToken(
        "reader", "unused", "ROLE_USER");

Mono<String> result = securedService.profile()
        .contextWrite(ReactiveSecurityContextHolder.withAuthentication(user));
~~~

The snippet here assumes `securedService` is a Spring-proxied bean and `profile()` is annotated. Thorough testing requires subscribing (`StepVerifier`), not merely instantiating a `Mono`. Avoid using `ThreadLocal`-based `SecurityContextHolder.getContext()` to guess the active identity inside a reactive subscriber.

## 7. Complete project: enable reactive method security and observe results

To see both protection layers operating independently, let's build a Spring Boot WebFlux API with:

- HTTP Basic authenticating users from an in-memory store.
- `SecurityWebFilterChain` authenticating all `/api/**` URLs.
- Method security checking roles/authorities at the service layer.
- `@PreAuthorize` for services requiring `ROLE_USER`, `ROLE_ADMIN`, and `report:read`.
- `@PostAuthorize` for a method that may only return the caller's own name.
- GET endpoints, so there is no need to disable Spring Security's CSRF.

### 7.1. The pom.xml file

Create a project on [Spring Initializr](https://start.spring.io/) with Java 17+, Maven, Spring Boot 4.1.2, group `com.example`, artifact `reactive-method-demo`; select **Spring Reactive Web** and **Spring Security**. Complete `pom.xml` example:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>reactive-method-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
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

Do not declare individual versions for `spring-security-*` modules. Use the parent/BOM to avoid mixing incompatible Spring Framework, Security, and Reactor versions.

### 7.2. Standalone Java file

Create `src/main/java/com/example/methoddemo/ReactiveMethodDemoApplication.java`:

~~~java
package com.example.methoddemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
public class ReactiveMethodDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveMethodDemoApplication.class, args);
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails reader = User.withUsername("reader")
                .password("{noop}reader123")
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password("{noop}admin123")
                .roles("USER", "ADMIN")
                .build();

        UserDetails analyst = User.withUsername("analyst")
                .password("{noop}analyst123")
                .authorities("report:read")
                .build();

        return new MapReactiveUserDetailsService(reader, admin, analyst);
    }

    @Bean
    SecurityWebFilterChain webSecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/status").permitAll()
                        .pathMatchers("/api/**").authenticated()
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    @Service
    static class SecuredService {

        @PreAuthorize("hasRole('USER')")
        public Mono<String> profile() {
            return Mono.just("PROFILE_OK");
        }

        @PreAuthorize("hasRole('ADMIN')")
        public Mono<String> adminReport() {
            return Mono.just("ADMIN_REPORT_OK");
        }

        @PreAuthorize("hasAuthority('report:read')")
        public Flux<String> reports() {
            return Flux.just("R1", "R2");
        }

        @PreAuthorize("#owner == authentication.name")
        public Mono<String> byOwner(String owner) {
            return Mono.just("OWNER_OK:" + owner);
        }

        @PostAuthorize("returnObject == authentication.name")
        public Mono<String> checkedName(String name) {
            return Mono.just(name);
        }
    }

    @RestController
    static class DemoController {
        private final SecuredService service;

        DemoController(SecuredService service) {
            this.service = service;
        }

        @GetMapping("/status")
        Mono<String> status() {
            return Mono.just("UP");
        }

        @GetMapping("/api/profile")
        Mono<String> profile() {
            return service.profile();
        }

        @GetMapping("/api/admin")
        Mono<String> adminReport() {
            return service.adminReport();
        }

        @GetMapping("/api/reports")
        Flux<String> reports() {
            return service.reports();
        }

        @GetMapping("/api/owner/{owner}")
        Mono<String> byOwner(@PathVariable String owner) {
            return service.byOwner(owner);
        }

        @GetMapping("/api/checked/{name}")
        Mono<String> checkedName(@PathVariable String name) {
            return service.checkedName(name);
        }
    }
}
~~~

**Runnability notes:**

- The public class and package path match; the `@Service` and `@RestController` classes are **nested static classes** found by Spring component scanning. They are not `final` to avoid proxy issues.
- `SecuredService` is a separate Spring bean injected into the controller, so calls go **through the AOP proxy**, not `this.method()` calls within the same object.
- `@EnableReactiveMethodSecurity` uses Spring Security 7.1's default AuthorizationManager. When upgrading or testing on the 5.8 branch, adjust the annotation according to the version table.
- `MapReactiveUserDetailsService` uses three local users. `{noop}` does not hash passwords: **only for local machine demos**, never use plaintext/hardcoded credentials in production. Real applications need a password encoder, HTTPS, and an appropriate identity system.
- `roles("USER")` creates authority `ROLE_USER`, `roles("ADMIN")` creates `ROLE_ADMIN`; `hasRole("ADMIN")` uses the default `ROLE_` prefix. `authorities("report:read")` creates the literal authority string checked by `hasAuthority("report:read")`.
- `@PostAuthorize` inspects the **emitted value** from `Mono<String>` before the caller receives it. Because the method only returns the name, there is no data mutation upon denial.
- `SecurityWebFilterChain` protects requests at the HTTP layer; method security performs deeper checks when the service is invoked. Do not use HTTP matchers as a substitute for AOP proxies.

### 7.3. Running the project

In the directory containing `pom.xml`, run:

~~~bash
./mvnw clean package
./mvnw spring-boot:run
~~~

On Windows, use `.\mvnw.cmd clean package` and `.\mvnw.cmd spring-boot:run`. If the project lacks a wrapper, you can use installed Maven via `mvn clean package` and `mvn spring-boot:run`.

The application listens on `http://localhost:8080` by default. If packages/imports do not match your version, stop and inspect the Javadoc/dependency tree; do not "fix" it by removing `@EnableReactiveMethodSecurity` or adding unrelated Servlet dependencies.

### 7.4. Verifying with curl

Example commands:

~~~bash
curl -i http://localhost:8080/status
curl -i http://localhost:8080/api/profile
curl -i -u 'reader:reader123' http://localhost:8080/api/profile
curl -i -u 'reader:reader123' http://localhost:8080/api/admin
curl -i -u 'admin:admin123' http://localhost:8080/api/admin
curl -i -u 'analyst:analyst123' http://localhost:8080/api/reports
curl -i -u 'reader:reader123' http://localhost:8080/api/reports
curl -i -u 'reader:reader123' http://localhost:8080/api/owner/reader
curl -i -u 'reader:reader123' http://localhost:8080/api/owner/admin
curl -i -u 'reader:reader123' http://localhost:8080/api/checked/reader
curl -i -u 'reader:reader123' http://localhost:8080/api/checked/admin
~~~

Use `curl.exe` if PowerShell aliases `curl` to `Invoke-WebRequest`. Expected results (when the app runs with default Basic auth and no custom exception handler):

| Request | Status | Content or reason |
| --- | --- | --- |
| `GET /status` anonymous | **200** | `UP` |
| `GET /api/profile` anonymous | **401** | Blocked by HTTP `authenticated` rule |
| Reader → `/api/profile` | **200** | `PROFILE_OK` |
| Reader → `/api/admin` | **403** | HTTP auth succeeded, service lacks `ROLE_ADMIN` |
| Admin → `/api/admin` | **200** | `ADMIN_REPORT_OK` |
| Analyst → `/api/reports` | **200** | `R1` and `R2` content via `Flux` |
| Reader → `/api/reports` | **403** | Missing `report:read` authority |
| Reader → `/api/owner/reader` | **200** | `OWNER_OK:reader` |
| Reader → `/api/owner/admin` | **403** | `#owner` does not equal `authentication.name` |
| Reader → `/api/checked/reader` | **200** | `reader` |
| Reader → `/api/checked/admin` | **403** | `@PostAuthorize` rejects mismatched return value |

`Flux<String>` over WebFlux may be encoded/streamed depending on `Accept` and codecs; **do not hard-code the body format** of the two elements unless a fixed media type is configured on the controller. HTTP status and individual element contents are the primary signals.

If an anonymous caller invokes the service via HTTP in another configuration that permits the URL, a method security denial may still route to the authentication entry point/401. However, the final HTTP status depends on the authentication mechanism, entry point, and exception handling; do not claim that every non-HTTP service call translates to HTTP 403.

## 8. Testing method security without HTTP

A test using only `curl` does not prove method security is verified independently if the HTTP layer blocks requests beforehand. For a service with an AOP proxy, test the publisher directly and attach authentication to the Reactor Context.

Example **test method snippet**, requiring Spring Test/`reactor-test`, with the service injected from the ApplicationContext:

~~~java
@Test
void readerCannotCallAdminService() {
    Authentication reader = new TestingAuthenticationToken(
            "reader", "unused", "ROLE_USER");

    Mono<String> invocation = service.adminReport()
            .contextWrite(
                    ReactiveSecurityContextHolder.withAuthentication(reader));

    StepVerifier.create(invocation)
            .expectError(AccessDeniedException.class)
            .verify();
}

@Test
void adminCanCallAdminService() {
    Authentication admin = new TestingAuthenticationToken(
            "admin", "unused", "ROLE_ADMIN");

    Mono<String> invocation = service.adminReport()
            .contextWrite(
                    ReactiveSecurityContextHolder.withAuthentication(admin));

    StepVerifier.create(invocation)
            .expectNext("ADMIN_REPORT_OK")
            .verifyComplete();
}
~~~

This is a **test snippet**, not a complete test class. It requires imports `org.junit.jupiter.api.Test`, `org.springframework.security.authentication.TestingAuthenticationToken`, `org.springframework.security.core.Authentication`, `org.springframework.security.core.context.ReactiveSecurityContextHolder`, `org.springframework.security.access.AccessDeniedException`, `reactor.core.publisher.Mono`, and `reactor.test.StepVerifier`. The `service` bean must be a **Spring proxy**; do not instantiate with `new SecuredService()` as that bypasses AOP. Some versions throw a subtype of `AccessDeniedException`; `expectError(AccessDeniedException.class)` works when the subtype inherits from that exception.

For a full test project, add testing dependencies managed by the Spring Boot BOM, such as the Spring Boot WebFlux test starter and Spring Security test matching your version. If using Spring Boot 4, test starters may be split by capability; verify the corresponding artifacts via Initializr rather than copying a full test dependency list from Boot 2.x.

**Why use `contextWrite` after the call?** A deferred publisher receives the Reactor Context at subscription time. If the service is a proxy, the method-security interceptor executes consistently with subscription; the context lets the manager see the test user.

If a test has no context, method security may emit an authentication error instead of succeeding; that is something to detect rather than simulating a ThreadLocal security context.

## 9. Annotations and expressions to remember

### 9.1. @PreAuthorize

~~~java
@PreAuthorize("hasRole('ADMIN')")
public Mono<String> adminOnly() {
    return Mono.just("OK");
}

@PreAuthorize("hasAuthority('invoice:read')")
public Flux<String> invoices() {
    return Flux.just("I-1", "I-2");
}

@PreAuthorize("#ownerId == authentication.name")
public Mono<String> owned(String ownerId) {
    return Mono.just(ownerId);
}
~~~

These are **method snippets placed in a Spring bean**, requiring imports for `@PreAuthorize`, `Mono`, and `Flux`. Expressions can read principal/roles/authorities/parameters. When Java compilation does not preserve parameter names as SpEL expects, you must enable parameter name metadata or use an appropriate annotation like `@P("ownerId")` depending on version; modern Spring Boot compiler plugins usually configure `-parameters`. If SpEL cannot resolve `#ownerId`, check parameter metadata before changing the policy.

### 9.2. @PostAuthorize

~~~java
@PostAuthorize("returnObject.owner == authentication.name")
public Mono<DocumentView> findDocument(String id) {
    return repository.findById(id);
}
~~~

**This is an illustrative non-standalone snippet**: `DocumentView` and `repository` are hypothetical, with `owner` as a property of the returned object. Reactive Spring Security can evaluate the value emitted from `Mono` before downstream consumes it. However, the query has already executed; do not treat this as a safeguard against side effects or unauthorized DB queries. For sensitive data, you may need to check the owner **before querying** or filter directly at the database by tenant/user id to prevent leaks via logs, timing, and caches.

### 9.3. @PreFilter and @PostFilter

Interceptors on the AuthorizationManager path support pre/post filtering of collections or publishers per the API contract. Because filtering may process individual elements or parameter collections, consider return types, lazy evaluation behavior, and publisher overhead. Do not use `@PostFilter` in place of `WHERE tenant_id = ...` in the database for large datasets or multi-tenant data.

### 9.4. hasRole and hasAuthority

| Expression | Common condition |
| --- | --- |
| `hasRole('ADMIN')` | Authentication has `ROLE_ADMIN` with the default role prefix |
| `hasAuthority('ROLE_ADMIN')` | Authentication has the exact authority string `ROLE_ADMIN` |
| `hasAuthority('report:read')` | Has the exact authority `report:read` |
| `isAuthenticated()` | Has an authentication considered validly logged in by Spring Security |
| `#owner == authentication.name` | Method argument `owner` matches principal name |

If the application uses `GrantedAuthorityDefaults` to change the role prefix, `hasRole` may be interpreted differently; inspect the bean/version configuration. Do not manually prepend `ROLE_` to every string when the API already does so.

### 9.5. SpEL must be non-blocking

Expressions and custom beans used in `@PreAuthorize` run on the reactive request path. A bean returning `Mono<Boolean>` can work reactively; if a bean returns `Boolean`, avoid calling blocking JDBC or blocking HTTP clients inside it.

Example of an ownership-checking bean using Reactor Context:

~~~java
@Component("ownerPolicy")
class OwnerPolicy {

    public Mono<Boolean> canRead(String owner) {
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(authentication ->
                        authentication.getName().equals(owner)
                        || authentication.getAuthorities().stream().anyMatch(
                            a -> "ROLE_ADMIN".equals(a.getAuthority())))
                .defaultIfEmpty(false);
    }
}

// In Spring-managed service:
@PreAuthorize("@ownerPolicy.canRead(#owner)")
public Mono<String> readFor(String owner) {
    return Mono.just("OK");
}
~~~

This is a **two-class/method snippet**, not a standalone file: the annotated method must be placed in a service and import `@Component`, `ReactiveSecurityContextHolder`, `SecurityContext`, and `Mono`. According to AuthorizationManager method-security documentation, custom beans in SpEL can return `Boolean` or `Mono<Boolean>`. `defaultIfEmpty(false)` ensures a missing context results in an explicit denial.

A production owner policy should rely on durable IDs and check tenant/resource ownership, not just compare path/username strings. If resource lookup is needed, prefer reactive repositories and control data-access errors.

## 10. Customizing ReactiveAuthorizationManager at the interceptor level

### 10.1. When is it needed?

`@PreAuthorize` expressions are usually sufficient. When authorization logic requires deep testing, multiple context sources, or reusable policies, you can write a `ReactiveAuthorizationManager<MethodInvocation>` and attach it to an advisor. **Merely creating a manager bean does not automatically make `@PreAuthorize` use that manager**; you must register the appropriate interceptor/pointcut.

Example of a simple manager checking `ROLE_AUDITOR` (**illustrative** code snippet, not a complete configuration):

~~~java
final class AuditorAuthorizationManager
        implements ReactiveAuthorizationManager<MethodInvocation> {

    @Override
    public Mono<AuthorizationResult> authorize(
            Mono<Authentication> authentication,
            MethodInvocation invocation) {

        return authentication
                .map(user -> user.getAuthorities().stream()
                        .anyMatch(a -> "ROLE_AUDITOR".equals(a.getAuthority())))
                .map(granted ->
                        (AuthorizationResult) new AuthorizationDecision(granted))
                .defaultIfEmpty(new AuthorizationDecision(false));
    }
}
~~~

Required imports:

~~~java
import org.aopalliance.intercept.MethodInvocation;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.core.Authentication;
import reactor.core.publisher.Mono;
~~~

In Spring Security 7.1, `ReactiveAuthorizationManager.authorize(Mono<Authentication>, T)` returns `Mono<AuthorizationResult>`, not a synchronous boolean. `AuthorizationDecision` is an implementation of `AuthorizationResult`. In some older documentation, you may see `check(...)` or signatures taking `Supplier<Authentication>`; **check the Javadoc for your exact resolved version** rather than mixing APIs.

### 10.2. How to attach to a method interceptor

The API provides a factory:

~~~java
AuthorizationManagerBeforeReactiveMethodInterceptor.preAuthorize(manager);
~~~

This is an **illustrative line**, with `manager` of type `ReactiveAuthorizationManager<MethodInvocation>`. To use it, you need to publish an `Advisor` / infrastructure bean with a pointcut for the target annotation. If `@EnableReactiveMethodSecurity` is already enabled causing Spring to register default advisors, adding a new advisor without disabling/customizing the default can cause **both rules to apply** or create conflicts.

Therefore, in most projects, the safer approach is:

1. Keep `@EnableReactiveMethodSecurity` with the default interceptors.
2. Put logic into a bean for SpEL to call, or into an independently tested authorization service.
3. Only replace internal advisors when truly necessary, after understanding `AuthorizationInterceptorsOrder`, pointcuts, AOP, and dependencies.
4. Write integration tests proving annotations are neither skipped nor executed twice.

**Do not use the factory snippet alone and claim you have "replaced the entire AuthorizationManager".** If you must customize infrastructure, consult the corresponding Spring Security method-security docs, because interceptor counts and registration points vary across versions.

## 11. AOP proxy: pitfalls that prevent method security from running

### 11.1. Internal calls (self-invocation)

Suppose:

~~~java
@Service
class ReportService {

    public Mono<String> unsafeFacade() {
        return adminOnly(); // this.adminOnly(): bypasses Spring AOP proxy
    }

    @PreAuthorize("hasRole('ADMIN')")
    public Mono<String> adminOnly() {
        return Mono.just("SECRET");
    }
}
~~~

This is a **snippet illustrating a hazard**: if `unsafeFacade()` is called from another bean, the internal call to `adminOnly()` is still `this.adminOnly()`, bypassing that method's proxy. Therefore, the annotation may not be checked as intended.

**Solution:** move the protected business method to a separate bean and inject it into the calling bean; or redesign the flow so calls always go through a Spring-managed proxy. Do not treat annotations on private methods or methods called on `new`-instantiated objects as effective protection.

### 11.2. Final/private methods and Kotlin

Spring AOP proxies have limitations for non-overridable methods and internal invocations. For classes without interfaces, Spring typically uses class-based proxies; `final` classes or methods can prevent the proxy from working as expected. In Kotlin, classes are `final` by default, requiring compatible plugins/proxy patterns. Do not merely see an annotation in source code and conclude the interceptor ran.

### 11.3. Spring-managed beans

If you instantiate an object via `new SecuredService()` in a controller or test, it is not a Spring proxy bean; annotations may not be enforced. Use dependency injection from the ApplicationContext, and write failing tests to verify security advice is genuinely registered.

### 11.4. Unsubscribed Mono

A reactive publisher only describes work. If you call a method returning `Mono` without returning or subscribing to it, the absence of an error cannot be taken as proof that access was granted. In WebFlux, controllers should **return the publisher** to the framework. In tests, use `StepVerifier` to trigger execution and assert `onNext`/`onError`.

## 12. Distinguishing method security errors from HTTP errors

| Scenario | At method layer | Typical HTTP with Basic |
| --- | --- | --- |
| Request has no user and HTTP requires `authenticated` | Does not enter method | **401** |
| Authenticated user lacks `ROLE_ADMIN` | Method security denies | **403** |
| Valid user with required role | Publisher allowed to emit result | **200** if handler succeeds |
| Method denied outside HTTP (job/service test) | Publisher errors with `AccessDeniedException` | **No HTTP response** to auto-convert |
| Missing CSRF token on POST | May be blocked by `CsrfWebFilter` before method | **403** but not a role denial |
| HTTP 404 non-existent route | Service is not called | **404** if HTTP rules let route lookup proceed |

`ExceptionTranslationWebFilter` can translate access-denied errors raised during a reactive request flow into an entry point or access-denied response. However, you cannot say every `AccessDeniedException` in a background task automatically turns into HTTP 403. For non-HTTP callers, handle exceptions at business boundaries and log appropriate audits.

## 13. Safe migration strategy

If a codebase currently uses Spring Security 5.8 with:

~~~java
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
~~~

when upgrading to 6.5/7.1 it can become:

~~~java
@EnableReactiveMethodSecurity
~~~

Follow this sequence:

1. **Inventory resolved versions** of `spring-security-config`, `spring-security-core`, `spring-security-web`; confirm the Boot BOM.
2. Check `@EnableReactiveMethodSecurity` in the Javadoc **of the exact version in use**, especially when coming from 5.8 or old 6.0.0 patches.
3. Test all `@PreAuthorize`, `@PostAuthorize`, custom SpEL beans, custom interceptors, role prefixes, and return types.
4. If you have custom `AccessDecisionVoter`/metadata sources, plan to replace them with `ReactiveAuthorizationManager` or bean logic in SpEL. Do not assume old custom extensions automatically work in the new architecture.
5. Do not carry over `@EnableMethodSecurity(prePostEnabled = false)` from Servlet guides to the reactive annotation: `@EnableReactiveMethodSecurity` has a different set of attributes (`proxyTargetClass`, `mode`, `order`, `useAuthorizationManager`). Configure reactive infrastructure per its own Javadoc.
6. If placing annotations on interfaces, classes, or inherited methods, check AOP pointcuts and conflicting annotations; the AuthorizationManager path includes detection for some ambiguous configurations.
7. Re-run integration tests against the new Spring Boot patch, especially policies using `Mono<Boolean>` in SpEL, `@PostAuthorize`, and Reactor Context.
8. After migration, logs/metrics should monitor denied method invocations without exposing principal secrets or sensitive data.

### Quick selection matrix

| Where are you? | What to do? |
| --- | --- |
| New Boot 4.1 / Security 7.1 project | `@EnableReactiveMethodSecurity` |
| Boot 3.5 / Security 6.5 project | `@EnableReactiveMethodSecurity` |
| Legacy Security 5.8, needing AuthorizationManager | `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` |
| Project on 5.7 or earlier | Do not add unsupported attributes; plan an upgrade |
| Codebase has `useAuthorizationManager = false` | Audit legacy dependencies and migration needs; do not copy to new projects |
| Method annotation not running | Check enable annotation, proxy, self-invocation, Publisher, and context before changing policy |
| Complex logic needed | Prefer reactive custom SpEL beans; replace advisors only after understanding infrastructure |

## 14. Common mistakes

**"I added `@PreAuthorize` but users can still get in."** You might be missing `@EnableReactiveMethodSecurity`, the service is not a Spring bean, there is self-invocation, the method is final/private, the annotation is misplaced, or the test did not subscribe. Do not solve this by adding random HTTP matchers and assuming method security is active.

**"I have `@EnableMethodSecurity` yet Mono cannot get the user."** You may be using Servlet configuration instead of reactive. Switch to `@EnableReactiveMethodSecurity` and verify Reactor Context.

**"I removed `useAuthorizationManager = true` on Security 5.8 and policies changed behavior."** In 5.8, the default is `false`. Keep opt-in `true` until you upgrade to a version with a confirmed `true` default.

**"I wrote `@PreAuthorize("hasRole('ROLE_ADMIN')")`."** `hasRole` usually prepends `ROLE_` automatically. In demos use `hasRole('ADMIN')`; if you need an exact string match, use `hasAuthority('ROLE_ADMIN')`.

**"I put the JWT principal in ThreadLocal and the method still doesn't see it."** Reactive flows propagate context via Reactor; use Spring Security's authentication/WebFilter mechanisms or `contextWrite(ReactiveSecurityContextHolder.withAuthentication(...))` in tests, not ThreadLocal.

**"I used `Mono.just(blockingRepository.findById(...))` in an authorization expression."** The blocking call still executes before creating the Mono. Use reactive repositories/HTTP clients; if unavoidable, design bounded schedulers and timeouts.

**"I put `@PostAuthorize` to protect money transfers."** Post-authorization can run after side effects. For state-mutating operations, check authorization before the transaction and at the point of sensitive data access.

**"Creating a custom ReactiveAuthorizationManager bean automatically applies it to annotations."** No. The manager must be wired into the proper advisor/pointcut or invoked by a SpEL component. Replacing default advisors carelessly can cause duplicate enforcement.

**"An endpoint returning 403 proves the annotation is running."** Not necessarily: 403 can come from HTTP authorization, CSRF, method roles, or a custom exception handler. Verify with tests calling the Spring-managed service proxy directly with different principals.

## 15. Production readiness checklist

1. Running the proper WebFlux/reactive ApplicationContext without mixing Servlet method security.
2. Resolved Spring Security BOM/version verified; `useAuthorizationManager` attribute matches the branch.
3. `@EnableReactiveMethodSecurity` is present in configuration and Spring creates the expected reactive interceptors.
4. Every protected method is on a Spring-managed bean called via proxy and returns an appropriate Publisher.
5. Authentication is present in the Reactor Context when the method is called.
6. Role prefixes, authorities, and parameter metadata in SpEL are explicitly tested.
7. Methods requiring ownership/tenant checks have policies based on trusted data, not just client-supplied arguments.
8. No blocking I/O inside managers, policy beans, or paths executing on the event loop.
9. Never rely on post-authorization to prevent side effects.
10. Tests cover anonymous, regular user, admin, wrong role, wrong owner, non-HTTP producer/consumer callers, and self-invocation.
11. HTTP security still enforces strict rules, CSRF/CORS/session/token matching the threat model.
12. Authorization errors are logged safely without leaking business data or credentials.

## 16. Self-assessment questions

**Question 1.** In Spring Security 5.8, what annotation should be used to enable AuthorizationManager-based method security?

**Answer:** `@EnableReactiveMethodSecurity(useAuthorizationManager = true)`, because 5.8 Javadoc documents the default as false.

**Question 2.** In Spring Security 6.5 or 7.1, do you always need to write `useAuthorizationManager = true`?

**Answer:** No. `@EnableReactiveMethodSecurity` enables AuthorizationManager by default. Keep code concise and verify the exact resolved version.

**Question 3.** Why is `@PreAuthorize` on `Mono<String> sensitive()` bypassed when called from another method in the same class?

**Answer:** Internal calls via `this` bypass the Spring AOP proxy; move the protected method to a separate Spring bean and inject it so calls go through the proxy.

**Question 4.** What is the difference between `@PreAuthorize` and `@PostAuthorize`?

**Answer:** Pre checks before calling/allowing the publisher to execute; Post checks the result after data is produced and before downstream receives it, so it does not guarantee preventing side effects that already occurred.

**Question 5.** Why use `ReactiveSecurityContextHolder` instead of ThreadLocal `SecurityContextHolder`?

**Answer:** Reactive streams can switch threads; Reactor Context travels with the subscriber and is where Spring Security integrates Authentication.

**Question 6.** Why does `hasRole('ADMIN')` in the demo match the `ROLE_ADMIN` authority?

**Answer:** Spring Security uses the `ROLE_` prefix by default for role checks; `roles("ADMIN")` generates the corresponding authority.

**Question 7.** Why does user `reader` receive 403 when calling `/api/admin` even though the HTTP layer allows logged-in users into `/api/**`?

**Answer:** HTTP only requires `authenticated`; the service method also has `@PreAuthorize("hasRole('ADMIN')")`, and `reader` lacks the role so the method-security interceptor denies access.

**Question 8.** When a custom manager returns `Mono.empty()`, is that a definitive deny decision?

**Answer:** No; per the `ReactiveAuthorizationManager` contract, empty can represent abstaining/not making a decision. If you need to fail closed, return an explicit deny result and ensure proper policy composition.

## 17. Official documentation and version verification

- [Spring Security 7.1 — EnableReactiveMethodSecurity and AuthorizationManager](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Javadoc — EnableReactiveMethodSecurity (current, default true)](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/method/configuration/EnableReactiveMethodSecurity.html)
- [Javadoc — EnableReactiveMethodSecurity 5.8.16 (default false)](https://docs.spring.io/spring-security/site/docs/5.8.16/api/org/springframework/security/config/annotation/method/configuration/EnableReactiveMethodSecurity.html)
- [Spring Security 6.5 Migration — Reactive / AuthorizationManager](https://docs.spring.io/spring-security/reference/6.5/migration/reactive.html)
- [Javadoc — ReactiveAuthorizationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/ReactiveAuthorizationManager.html)
- [Javadoc — AuthorizationManagerBeforeReactiveMethodInterceptor](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/method/AuthorizationManagerBeforeReactiveMethodInterceptor.html)
- [Javadoc — PreAuthorizeReactiveAuthorizationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/method/PreAuthorizeReactiveAuthorizationManager.html)
- [Spring Security — Reactive WebFlux Configuration](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security — Authorize ServerHttpRequest](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html)
- [Project Reactor — Reactor Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
