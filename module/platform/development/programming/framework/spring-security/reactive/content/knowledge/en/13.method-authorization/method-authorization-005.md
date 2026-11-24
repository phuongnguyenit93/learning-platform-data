# @PreFilter, @PostFilter, and Filtering Limitations by Return Type and Version

> **Context:** Spring Security in Spring WebFlux applications, Java 17+, Spring Boot 3.3.x / Spring Security 6.3.x; clearly contrasted with Servlet/imperative method security and points to verify when upgrading versions. The focus is **filtering input and output elements**, not confusing them with blocking the entire method or securing records at the repository.

## 1. The problem: controlling individual elements instead of the entire request

Suppose a service manages reports:

| ID | Owner | Title |
|---|---|---|
| R-1 | alice | Report A |
| R-2 | bob | Report B |
| R-3 | alice | Report C |

Alice is authenticated. When calling `GET /api/reports`, the application wants to return **R-1, R-3**, and not R-2. When Alice submits three reports in a test request, the system may want to process only the elements she owns.

Spring Security provides two annotations for that pattern:

- `@PreFilter`: filters **elements of an input parameter** before the method logic receives them.
- `@PostFilter`: filters **elements of a method's return value** after the method supplies the result, before the caller sees the filtered outcome.

These two annotations differ from:

- `@PreAuthorize`: decides **whether the method may be called at all**; usually denies with an access-denied error when permissions are lacking.
- `@PostAuthorize`: inspects the **method result** and can **deny the entire result**, rather than acting as a "remove individual elements" mechanism.
- `authorizeExchange`: authorizes at the HTTP layer by URL, HTTP method, and principal.
- `Flux.filter(...)`, `Flux.filterWhen(...)`, or repository queries `findAllByOwnerId(...)`: filtering in business/reactive code at the data layer without relying on SpEL annotations.

### Visual overview

```text
              @PreFilter                       @PostFilter
Input A,B,C -------> Input A,C ---> service ---> Result A,B,C -------> Result A,C
                     (filtered)                (method may have fetched all)

@PreAuthorize: denies method call if caller is not permitted
@PostAuthorize: denies result if return condition is not met
```

**Core security point:** `@PostFilter` is only a barrier after data has already been retrieved. If a service loads a million records before filtering permissions, risks of heavy load, broken pagination, and internal logic accidentally processing out-of-scope data still remain. Policies protecting sensitive data must start with repository queries and object-level permission checks.

## 2. Annotations and SpEL expressions

Both annotations reside in the package:

```java
import org.springframework.security.access.prepost.PreFilter;
import org.springframework.security.access.prepost.PostFilter;
```

Basic example on elements having an `owner` property:

```java
@PreFilter("filterObject.owner == authentication.name")
public Collection<Report> process(Collection<Report> reports) {
    // Only elements matching the expression are passed into the method.
    return reports;
}

@PostFilter("filterObject.owner == authentication.name")
public Collection<Report> listReports() {
    // Method may return all records.
    return repository.findAll();
}
```

**This is an illustrative snippet for imperative/collection-based method security, not standalone runnable WebFlux code.** Spring Security's servlet/imperative docs describe these collection-based signatures. For **reactive method security**, you must verify the exact interceptor and Publisher types per version; do not copy an imperative `Collection<Report>` signature into a bean with only `@EnableReactiveMethodSecurity` and assume it works like a reactive method.

In the expression:

- `filterObject` is the **element currently being evaluated**, not the entire result set.
- `authentication.name` reads the name from the `Authentication` established by Spring Security. In Basic demos it is usually the username; with JWT it may be another subject.
- `hasRole('ADMIN')` checks granted roles. Under the default prefix, the role corresponds to authority `ROLE_ADMIN`.
- `filterObject.owner == authentication.name or hasRole('ADMIN')` permits the owner or an admin.

**Java property note:** If using a JavaBean `getOwner()`, SpEL `filterObject.owner` can access that property. If using Java records, verify whether SpEL can access record components on your exact Spring Framework version; to avoid ambiguity, the runnable example below explicitly declares `getOwner()`.

### Filtering is not the same as denying

When `@PostFilter` encounters an element failing the condition, it removes that element from the stream/collection the caller sees; it does not emit a 403 per excluded element by default. If every element is excluded, the caller may receive an empty list or an empty completing publisher, depending on API type and version. If business rules require **an unauthorized record to return 403/404**, enforce **per-object authorization** (scoped query, suitable `@PostAuthorize`, or explicit denial) instead of relying on an empty list.

## 3. Method security stacks: Servlet and Reactive are not the same

In Spring Security 6, both mechanisms use Spring AOP around bean invocations, yet have separate interceptor branches.

| Aspect | Imperative/Servlet | Reactive/WebFlux |
|---|---|---|
| Enable method security | `@EnableMethodSecurity` | `@EnableReactiveMethodSecurity` |
| Principal context | Typically `SecurityContextHolder` with thread-bound strategy | `ReactiveSecurityContextHolder` in Reactor Context |
| Common method types | `Report`, `List<Report>`, `Collection<Report>`, `Stream<Report>` | `Mono<Report>`, `Flux<Report>`, supported publisher/reactive types |
| Pre-filter interceptor | `PreFilterAuthorizationMethodInterceptor` | `PreFilterAuthorizationReactiveMethodInterceptor` |
| Post-filter interceptor | `PostFilterAuthorizationMethodInterceptor` | `PostFilterAuthorizationReactiveMethodInterceptor` |
| Filter target | Method argument/filterable elements | Reactive argument/Publisher as supported by implementation |
| Filter result | Collection, array, map, method stream | Publisher handled by interceptor per version; must test wrappers/elements |
| Risks | In-memory scan, eager loading, proxy/self-invocation | Lost Reactor Context, wrapper types, deferred subscription, still risks scan/over-fetch |

### 3.1 Important changes across versions

- **Spring Security 5.8:** docs and Javadoc note dedicated reactive interceptors `PreFilterAuthorizationReactiveMethodInterceptor` and `PostFilterAuthorizationReactiveMethodInterceptor` (Since 5.8). `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` introduced the AuthorizationManager direction.
- **Spring Security 6.0 onward:** AuthorizationManager is the default for `@EnableReactiveMethodSecurity`; new projects can simply use `@EnableReactiveMethodSecurity`. When migrating from older releases, ensure legacy interceptors are not simultaneously enabled.
- **Spring Security 6.3/6.5:** reactive docs list `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, `@PostFilter`, and the reactive interceptors. The docs also state protected methods in reactive examples must return `org.reactivestreams.Publisher` (e.g., `Mono`, `Flux`) to integrate with Reactor Context. **The existence of annotations/interceptors does not automatically prove every argument type, wrapper, stream, or expression behaves identically to Servlet.**
- **Spring Security 7.x:** reactive method security docs and corresponding interceptors remain, yet APIs, return-type rules, SpEL config, and specialized behavior may change across patch releases. When upgrading, check **exact-version** docs and re-run tests instead of extrapolating from 6.3 examples.

Official sources to verify:

- Spring Security 6.3 Reactive Method Security: https://docs.spring.io/spring-security/reference/6.3/reactive/authorization/method.html
- Spring Security 6.5 Reactive Method Security: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html
- `PreFilterAuthorizationReactiveMethodInterceptor` 6.3.8 Javadoc: https://docs.spring.io/spring-security/site/docs/6.3.8/api/org/springframework/security/authorization/method/PreFilterAuthorizationReactiveMethodInterceptor.html
- `PostFilterAuthorizationReactiveMethodInterceptor` 6.3.x Javadoc: https://docs.spring.io/spring-security/site/docs/6.3.x/api/org/springframework/security/authorization/method/PostFilterAuthorizationReactiveMethodInterceptor.html
- Servlet docs for collection/map/stream types: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html

**Do not consult unversioned "current" docs blindly**: right now the default page may point to Spring Security 7.x, which does not match an app on Spring Boot 3.3.x.

### 3.2 Enabling the right annotations in reactive configuration

```java
@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
class SecurityConfiguration {
    // SecurityWebFilterChain and Authentication source here.
}
```

This snippet requires imports:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
```

Both request-level and method-level configuration are needed. `@EnableReactiveMethodSecurity` does not replace `SecurityWebFilterChain`; `@EnableWebFluxSecurity` alone does not enable method security annotations.

In a WebFlux system, **do not use Servlet's `@EnableMethodSecurity` expecting `Flux`/`Mono` methods to be handled via ReactiveSecurityContextHolder**. Proxies/interceptors and context types must align.

## 4. Parameter types for @PreFilter and common limitations

`@PreFilter` evaluates the expression on each element **before the method processes input**.

### 4.1 Collection/array/map/stream in imperative method security

According to Spring Security Servlet docs, the following are valid patterns when imperative method security is enabled:

```java
@PreFilter("filterObject.owner == authentication.name")
Collection<Report> update(Collection<Report> reports);

@PreFilter("filterObject.owner == authentication.name")
Collection<Report> update(Report[] reports);

@PreFilter("filterObject.value.owner == authentication.name")
Collection<Report> update(Map<String, Report> reports);

@PreFilter("filterObject.owner == authentication.name")
Collection<Report> update(Stream<Report> reports);
```

These are **illustrative signatures**, not runnable Java classes; the docs support `Stream` provided the stream has not been closed. For maps, `filterObject` is typically an **entry**, so use `filterObject.value.owner` instead of treating the entry itself as a report. When multiple filterable arguments exist, use `filterTarget` to name the target parameter (alongside compiler config allowing parameter name resolution).

```java
@PreFilter(
    value = "filterObject.owner == authentication.name",
    filterTarget = "reports")
Collection<Report> update(String tenantId, Collection<Report> reports);
```

In practice, when selecting by variable name, verify compiler parameter metadata or use a Spring Security-supported parameter naming mechanism. Do not turn source variable names into an implicit dependency and forget to test after builds.

### 4.2 Flux<T> is not List<T>

A `Flux<Report>` describes a **stream emitting Reports**, which may not have executed yet when the method builds the `Flux`. Spring Security 6.x has reactive interceptors for filter annotations, so you must test the reactive branch directly.

Target signature meaning "check each element when the Flux is subscribed":

```java
@PreFilter("filterObject.owner == authentication.name")
public Flux<Report> preview(Flux<Report> input) {
    return input;
}
```

This snippet requires a Spring-proxied bean, `@EnableReactiveMethodSecurity`, a Reactor Context with authentication, and **a Spring Security version supporting Flux argument filtering as expected**. Do not assume putting `@PreFilter` on `List<Report>` in the same reactive bean yields the same result; that boundary must be confirmed by version-specific integration tests.

If your version or special type does not behave as expected, the **explicit and predictable** alternative is writing the reactive pipeline yourself using a verified owner/tenant:

```java
Flux<Report> previewOwned(
        Flux<Report> input, String trustedUsername) {
    return input.filter(
        report -> trustedUsername.equals(report.getOwner()));
}
```

This is an illustrative method; **`trustedUsername` must come from a verified Authentication**, never from client-sent query params, bodies, or headers. Use `flatMap`/`filterWhen` when decisions require async permission lookups.

### 4.3 Mono<List<T>> differs from Flux<T>

`Mono<List<Report>>` emits **a single List object**, whereas `Flux<Report>` emits individual `Report` items. Having a container inside `Mono` does not make annotations automatically "descend" one level into the list:

```java
Mono<List<Report>> wrapped = repository.findAll().collectList();
// Publisher emits 1 List<Report> value.
// Not automatically equivalent to Flux<Report> or direct Collection<Report>.
```

Nor can you assume `@PreFilter` on `Mono<List<Report>>` filters each `Report` inside the List the same way as `Flux<Report>`. Depending on the version, the interceptor may treat the payload as a single object, reject the wrapper, or apply specialized handling; **test it, do not guess**.

When per-element processing is needed, prefer explicit pipelines:

```java
Flux<Report> items = inputMono
    .flatMapMany(Flux::fromIterable)
    .filter(report -> trustedUsername.equals(report.getOwner()));
```

You can also return `Mono<List<Report>>` after filtering:

```java
Mono<List<Report>> owned =
    inputMono.flatMapMany(Flux::fromIterable)
        .filter(r -> trustedUsername.equals(r.getOwner()))
        .collectList();
```

However, if the source already loaded all data before entering `inputMono`, the over-fetch cost remains. When a reactive repository is available, querying by owner/tenant upfront is far better.

### 4.4 Scalar parameters are not collections

`@PreFilter` filters **elements**; for scalar parameters like `Long orderId` or `String tenant`, do not use it to mean "deny if not owned by user". Use `@PreAuthorize(...)` or service/repository authorization checks instead.

### 4.5 Security considerations when filtering inputs

Silently dropping unauthorized elements from input can cause business bugs: a client submits 10 items, the server processes only 7 and returns success, causing confusion or enabling repeated batch probing. For **write** operations, it is usually safer and clearer to:

- Verify permissions for the entire batch before starting the transaction.
- If any item is out of scope: return an appropriate 403/422 error.
- If business rules intentionally allow partial success: return per-item results explicitly, with accurate auditing, idempotency, and transaction policies.

Do not use `@PreFilter` to silently strip out-of-scope items and return `200 OK` if the API contract requires all-or-nothing semantics.

## 5. Return types for @PostFilter: capabilities and pitfalls

### 5.1 Methods returning a Collection directly

In **imperative method security**, Spring Security 6.x supports filtering:

- `Collection<Report>` such as `List` or `Set`.
- `Report[]` arrays.
- `Map<K, Report>` with expressions targeting entries.
- `Stream<Report>` while the stream remains open.

```java
@PostFilter("filterObject.owner == authentication.name")
public List<Report> allReports() {
    return repository.findAll();
}
```

The example above is an **imperative method fragment**. If the repository returns 500,000 records and the annotation keeps 5, you still pay the cost of reading 500,000 records. Use owner/tenant-scoped queries in production.

### 5.2 Methods returning Flux<Report>

This is the natural shape in WebFlux: `Flux<Report>` emits multiple elements and can be filtered as the subscriber consumes data:

```java
@PostFilter(
    "filterObject.owner == authentication.name or hasRole('ADMIN')")
public Flux<Report> list() {
    return Flux.just(
        new Report("R-1", "alice", "Alpha"),
        new Report("R-2", "bob", "Beta"),
        new Report("R-3", "alice", "Gamma"));
}
```

This is an **illustrative method**, requiring a Spring bean, model, and proper annotation setup. Reactive interceptors exist in Spring Security 6.3 targeting publisher results, yet **exact behavior must be tested against your actual patch/dependency version**. Section 7 provides a similar runnable example and `WebTestClient` tests for owner/admin results.

If your chosen version does not filter `Flux<Report>` properly as expected, **do not ignore the failure and ship to production**; switch to explicit `Flux.filter/filterWhen` or principal-scoped repository queries.

### 5.3 Methods returning Mono<Report>

`Mono<Report>` emits at most one `Report`. Do not use `@PostFilter` to express "return 403 when owner mismatches" because the filter may yield **`Mono.empty()`** instead of emitting access-denied; a controller might turn empty into an unexpected response. For single records, define an explicit policy:

```java
public Mono<Report> readVisible(String id, String trustedUsername) {
    return repository.findByIdAndOwner(id, trustedUsername)
        .switchIfEmpty(Mono.error(
            new AccessDeniedException("Not allowed")));
}
```

This is illustrative Java pseudocode: requires a repository, `AccessDeniedException`, and `Mono` imports; 403/404 depends on API policy and exception handlers. If a record **does not exist**, do not blindly return 403 if that leaks existence; design anti-enumeration responses and data-level authorization.

### 5.4 Methods returning Mono<List<Report>>

Do not look at the type wrapped by `Mono` and assume the annotation automatically iterates through the entire List. In particular, do not **assert with certainty** that `@PostFilter("filterObject.owner...")` behaves like a directly returned `List<Report>`; that depends on reactive interceptors and version.

Clear, version-resilient pattern:

```java
public Mono<List<Report>> listVisible(String trustedUsername) {
    return repository.findAllByOwner(trustedUsername)
        .collectList();
}
```

With R2DBC databases, owner filtering should occur in the repository query; then the controller can choose to return `Flux<Report>` or `Mono<List<Report>>` per API contract.

### 5.5 Mono<Void>, void, Optional, and scalar DTOs

Practical analysis table:

| Return type | Does `@PostFilter` mean "remove individual records"? | Reliable alternative |
|---|---|---|
| `Flux<Report>` | Meaningful at the **emitted element** level when supported by the reactive interceptor | Write version-specific integration tests; prefer scoped queries |
| `Mono<Report>` | At most one element to keep/drop, not a default 403 policy | Confirmed `@PostAuthorize` or explicit access check |
| `Mono<List<Report>>` | Does not automatically unwrap List to filter each Report | `flatMapMany/filter/collectList` or repository query |
| `Mono<Map<String,Report>>` | Does not automatically treat map entries like direct Servlet `Map` | Convert explicitly to `Flux<Map.Entry<...>>` if needed and test |
| `Mono<Void>` | No data elements to filter | `@PreAuthorize` or service-level authorization |
| Direct `void` / `Report` | Does not match reactive method Publisher assumption | Use imperative method in right stack or adjust API |
| Direct `List<Report>` | Supported in **imperative**; do not assume reactive | `@EnableMethodSecurity` in proper stack or scoped queries |
| Direct `Stream<Report>` | Imperative filter while Stream is open | Avoid DB Streams outside transactions; in WebFlux use Flux |

### 5.6 Post-filtering can still leave data exposed elsewhere

`@PostFilter` does not reverse side effects that already happened inside the method: detailed metrics, caches, logs, callbacks, events, or external writes may already have processed items "removed from the response". It only governs **values the caller receives** at the interceptor boundary. Never use it as the sole data isolation boundary in multi-tenant systems.

## 6. Filtering data via Reactor operators: a stable alternative

In most WebFlux apps, owner/tenant filtering can be written directly in the repository or pipeline:

```java
public Flux<Report> reportsForCurrentUser() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .flatMapMany(auth ->
            reportRepository.findByOwner(auth.getName()));
}
```

This snippet requires real repositories, reactive `SecurityContext`, and identity mapping. `findByOwner` must query with the verified owner condition rather than accepting an owner from the request. With multi-issuer JWTs, `auth.getName()` might not be a stable user ID; map source identity → trusted internal ID.

Additional filtering with predicates:

```java
public Flux<Report> onlyOwned(
        Flux<Report> incoming, String trustedUsername) {
    return incoming.filter(
        report -> trustedUsername.equals(report.getOwner()));
}
```

When permissions require non-blocking DB lookups:

```java
public Flux<Report> allowed(
        Flux<Report> incoming, String trustedUserId) {
    return incoming.filterWhen(report ->
        permissions.canRead(trustedUserId, report.getId()));
}
```

Both methods above are **code fragments**; `permissions` is an application-defined reactive service. If `canRead` errors, propagate the error or handle it fail-closed; **never `onErrorReturn(true)`**. `filterWhen` can trigger many async checks; bound concurrency/buffering per Reactor API and real load.

### 6.1 When to prefer scoped queries over post-filtering?

| Case | Preference |
|---|---|
| Small dataset already loaded for another purpose, wanting defense-in-depth | Can add `@PostFilter`/`filter` if tested |
| Search with `page/size`, `sort`, `count` | Filter in repository before pagination; post-filtering breaks page metadata |
| Multi-tenant or private data | `WHERE tenant_id = ? AND owner_id = ?` / RLS / permission join |
| Flux involving heavy I/O or long streaming APIs | Filter as close to the source as possible; mind backpressure, cancellation, resources |
| Permissions depend on record and third-party services | Use reactive authorization service, timeouts, concurrency limits |
| Batch updates requiring all-or-nothing | Validate all items and transactions; never silently drop items |

`@PostFilter` is not a substitute for parameterized queries, database row-level security (RLS), or service-level authorization.

## 7. Runnable Spring Boot 3.3 + WebFlux example with tests

The demo focuses on filtering in a service bean and HTTP responses. To separate annotation behavior from business rules, the service provides **two endpoint groups**: endpoints with `@PostFilter`/`@PreFilter` to observe reactive interceptors; and an **explicit** filter endpoint as a stable baseline. Tests let you verify whether your version handles `Flux` properly; if not, treat it as a compatibility issue to resolve before considering the setup data-safe.

**Note:** usernames/passwords below are for tests/localhost only. Spring Boot 3.3.13 and corresponding Spring Security 6.3 are used as an **API learning baseline**, not a 2026 production deployment recommendation.

### 7.1 Structure

```text
webflux-filter-method-security/
  settings.gradle
  build.gradle
  src/main/java/example/filter/FilterApplication.java
  src/main/java/example/filter/SecurityConfiguration.java
  src/main/java/example/filter/Report.java
  src/main/java/example/filter/ReportService.java
  src/main/java/example/filter/ReportController.java
  src/test/java/example/filter/ReportMethodSecurityTest.java
```

**settings.gradle**

```groovy
rootProject.name = 'webflux-filter-method-security'
```

**build.gradle**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example.filter'
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
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-aop'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-aop` is declared explicitly to highlight method security's Spring AOP proxy mechanism. The application uses an in-memory user store with no external DB. Do not add the MVC starter.

### 7.2 Application

**src/main/java/example/filter/FilterApplication.java**

```java
package example.filter;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FilterApplication {
    public static void main(String[] args) {
        SpringApplication.run(FilterApplication.class, args);
    }
}
```

### 7.3 Authentication and enabling reactive method security

**src/main/java/example/filter/SecurityConfiguration.java**

```java
package example.filter;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("dev-alice-only"))
            .roles("USER")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("dev-bob-only"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("dev-admin-only"))
            .roles("USER", "ADMIN")
            .build();

        return new MapReactiveUserDetailsService(alice, bob, admin);
    }

    @Bean
    SecurityWebFilterChain chain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public").permitAll()
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .csrf(Customizer.withDefaults())
            .build();
    }
}
```

Analysis:

- `@EnableReactiveMethodSecurity` registers Spring AOP mechanics for method annotations; methods must belong to Spring beans invoked through proxies.
- `anyExchange().authenticated()` at the HTTP layer requires an authenticated principal; method-level filtering further narrows the data visible to the caller.
- `httpBasic` uses in-memory usernames/passwords. Passwords are hashed with BCrypt; do not use demo users/passwords in production.
- `csrf(withDefaults())` keeps CSRF enabled. Browser POST/PUT/DELETE requests may require CSRF tokens; POST tests in section 7.7 attach tokens via Spring Security Test. Do not disable CSRF simply because you are learning prefiltering.

### 7.4 Model with JavaBean getters for SpEL

**src/main/java/example/filter/Report.java**

```java
package example.filter;

public record Report(String id, String owner, String title) {

    public String getOwner() {
        return owner;
    }

    public String getId() {
        return id;
    }
}
```

The record keeps JSON serialization concise. The two getters make SpEL usage of `owner` and `id` properties explicit. This is a demo DTO containing no sensitive data. In real projects, never let callers assign `owner` themselves and treat that field as verified.

### 7.5 Service: annotation filters and explicit baseline

**src/main/java/example/filter/ReportService.java**

```java
package example.filter;

import org.springframework.security.access.prepost.PostFilter;
import org.springframework.security.access.prepost.PreFilter;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;

@Service
public class ReportService {

    private Flux<Report> sample() {
        return Flux.just(
            new Report("R-1", "alice", "Alpha"),
            new Report("R-2", "bob", "Beta"),
            new Report("R-3", "alice", "Gamma"));
    }

    // Return value: filters each Report by owner or ADMIN role.
    @PreAuthorize("hasRole('USER')")
    @PostFilter(
        "filterObject.owner == authentication.name or hasRole('ADMIN')")
    public Flux<Report> visibleViaAnnotation() {
        return sample();
    }

    // Input argument: attempts to filter Flux<Report> before method processes it.
    @PreAuthorize("hasRole('USER')")
    @PreFilter(
        "filterObject.owner == authentication.name or hasRole('ADMIN')")
    public Flux<Report> previewViaAnnotation(Flux<Report> input) {
        return input;
    }

    // Baseline not relying on @PostFilter: filters by identity
    // read directly from Reactor Context populated by Spring Security.
    @PreAuthorize("hasRole('USER')")
    public Flux<Report> visibleExplicitly() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .flatMapMany(auth -> {
                boolean admin = auth.getAuthorities().stream()
                    .anyMatch(a ->
                        "ROLE_ADMIN".equals(a.getAuthority()));

                if (admin) {
                    return sample();
                }
                return sample().filter(
                    r -> auth.getName().equals(r.getOwner()));
            });
    }
}
```

**Design and testing notes:**

1. `visibleViaAnnotation()` and `previewViaAnnotation(...)` are two **target signatures to test reactive filter interceptors** in Spring Security 6.3.x. The tests below are the acceptance criteria; if they fail, fix the implementation or use explicit filtering — **never assume annotations protect data automatically**.
2. `sample()` creates an in-memory Flux solely to demonstrate filter conditions. With real DB/Redis stores, never return all records and rely purely on postfiltering.
3. `visibleExplicitly()` is the baseline authenticating via Reactor Context and filtering `Flux<Report>` explicitly, avoiding guesswork about wrapper-type support.
4. `@PreAuthorize` requires the USER role on all three methods. In the demo, `admin` also holds `ROLE_USER` so they can enter each method. If admins lack USER in your system, update the expression to match policy roles.
5. The service is a separate bean from the controller: calls from the controller pass **through the Spring AOP proxy**. Calling `this.visibleViaAnnotation()` inside `ReportService` itself can bypass method security interceptors.
6. Filtering by `owner` is for demonstration only; multi-tenant systems need full tenant/permission constraints in the DB and strict trust boundaries.

### 7.6 Controller

**src/main/java/example/filter/ReportController.java**

```java
package example.filter;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
public class ReportController {

    private final ReportService reports;

    public ReportController(ReportService reports) {
        this.reports = reports;
    }

    @GetMapping("/api/reports/annotation")
    public Flux<Report> annotation() {
        return reports.visibleViaAnnotation();
    }

    @GetMapping("/api/reports/explicit")
    public Flux<Report> explicit() {
        return reports.visibleExplicitly();
    }

    @PostMapping("/api/reports/preview")
    public Flux<Report> preview(@RequestBody Flux<Report> input) {
        return reports.previewViaAnnotation(input);
    }

    @GetMapping("/api/public")
    public Flux<String> publicEndpoint() {
        return Flux.just("public");
    }
}
```

The controller returns Publishers so WebFlux manages subscriptions; never call `.block()` or `.subscribe()` manually. The POST method is a **preview** without DB writes, yet it remains an unsafe HTTP method and CSRF stays enabled to reflect stateful API policy. When sending a JSON array body, WebFlux decodes elements using the appropriate `Flux<Report>` decoder; clients must send `Content-Type: application/json`.

### 7.7 Automated tests with WebTestClient

**src/test/java/example/filter/ReportMethodSecurityTest.java**

```java
package example.filter;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class ReportMethodSecurityTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointIsPublic() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectBodyList(String.class)
            .contains("public");
    }

    @Test
    void protectedEndpointRejectsAnonymous() {
        client.get().uri("/api/reports/annotation")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void annotationPostFilterForAlice() {
        client.get().uri("/api/reports/annotation")
            .headers(h -> h.setBasicAuth("alice", "dev-alice-only"))
            .exchange()
            .expectStatus().isOk()
            .expectBodyList(Report.class)
            .hasSize(2)
            .contains(
                new Report("R-1", "alice", "Alpha"),
                new Report("R-3", "alice", "Gamma"));
    }

    @Test
    void annotationPostFilterForAdmin() {
        client.get().uri("/api/reports/annotation")
            .headers(h -> h.setBasicAuth("admin", "dev-admin-only"))
            .exchange()
            .expectStatus().isOk()
            .expectBodyList(Report.class)
            .hasSize(3);
    }

    @Test
    void explicitFilteringIsEquivalentForAlice() {
        client.get().uri("/api/reports/explicit")
            .headers(h -> h.setBasicAuth("alice", "dev-alice-only"))
            .exchange()
            .expectStatus().isOk()
            .expectBodyList(Report.class)
            .hasSize(2);
    }

    @Test
    void preFilterDropsForeignInputForAlice() {
        List<Report> input = List.of(
            new Report("R-1", "alice", "Alpha"),
            new Report("R-2", "bob", "Beta"),
            new Report("R-3", "alice", "Gamma"));

        client.mutateWith(csrf()).post().uri("/api/reports/preview")
            .headers(h -> h.setBasicAuth("alice", "dev-alice-only"))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(input)
            .exchange()
            .expectStatus().isOk()
            .expectBodyList(Report.class)
            .hasSize(2);
    }

    @Test
    void preFilterKeepsAllForAdmin() {
        List<Report> input = List.of(
            new Report("R-1", "alice", "Alpha"),
            new Report("R-2", "bob", "Beta"));

        client.mutateWith(csrf()).post().uri("/api/reports/preview")
            .headers(h -> h.setBasicAuth("admin", "dev-admin-only"))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(input)
            .exchange()
            .expectStatus().isOk()
            .expectBodyList(Report.class)
            .hasSize(2);
    }

    @Test
    void postWithoutCsrfIsDenied() {
        client.post().uri("/api/reports/preview")
            .headers(h -> h.setBasicAuth("alice", "dev-alice-only"))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(List.of(
                new Report("R-1", "alice", "Alpha")))
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

Run:

```bash
gradle test
```

These are **8 test methods**. Expected outcome in an environment properly supporting reactive `Flux` filtering: all PASS. If **tests for `@PreFilter` or `@PostFilter` fail**, treat it as an important compatibility/implementation finding (especially on minor/patch releases or method parameter conversion), do not ignore it. The explicit filtering and 401/CSRF tests provide a baseline to isolate faults.

**Do not treat expectations as proof tests were already run:** the examples were authored and API-reviewed without running Gradle locally in this document. Before deploying, actually run `gradle test` with your **exact dependency lockfile**, inspect stack traces, and verify no out-of-scope users appear in JSON. If your chosen release does not support `Flux` filtering as intended, switch to `filter/filterWhen` or scoped queries and update tests accordingly.

### 7.8 Manual HTTP testing

```bash
gradle bootRun

# No login required:
curl -i http://localhost:8080/api/public

# Login required:
curl -i http://localhost:8080/api/reports/annotation

# Curl CLI will prompt for password; enter dev-alice-only
curl -i -u alice http://localhost:8080/api/reports/annotation

# Curl CLI will prompt for password; enter dev-admin-only
curl -i -u admin http://localhost:8080/api/reports/annotation
```

On PowerShell, if `curl` is an alias, use `curl.exe`. Never record passwords in command-line arguments in production docs. To test POST with CSRF from a real HTTP client, obtain a CSRF token per policy and submit it via the valid header/field; `mutateWith(csrf())` is for tests only.

## 8. Reactive method security works via AOP and Reactor Context

Even when annotations sit on methods, Spring Security uses Spring AOP to "wrap" bean methods. Key conditions:

1. **Method belongs to a Spring-managed bean.** An object created with `new ReportService()` outside the ApplicationContext is not handled by a Spring proxy.
2. **Calls must go through the proxy.** `this.someAnnotatedMethod()` (self-invocation) inside the same class may skip interceptors.
3. **Method/reactive type must be compatible.** For example, `Flux<T>` runs deferred; Spring Security retrieves Authentication from the subscription's Reactor Context rather than reading ThreadLocal as in Servlet apps.
4. **Authentication must be populated.** WebFlux Security normally injects context into the request pipeline; calling services from non-HTTP jobs/tests requires attaching authentication properly during testing.
5. **Interceptor order matters when combined.** `@PreAuthorize`, `@PreFilter`, `@PostAuthorize`, and `@PostFilter` belong to distinct advisors. Do not assume they act as a single unified check; test ordering/errors when both filtering and denying.
6. **Do not subscribe manually inside services.** Return Publishers for the framework to manage, and never call `.block()` on the event loop.

Example of reading the trusted Principal in a pipeline:

```java
Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
}
```

This is an illustrative method. If there is no security context, the Mono can be empty. Do not use ThreadLocal-based `SecurityContextHolder.getContext()` as the default identity source in WebFlux services.

## 9. Return-type and version testing matrix

Safety cannot be verified solely because "code compiles". Since annotations rely on AOP and behave differently across runtimes/interceptors, behavioral tests are required.

| Case | Test to write | Bug to catch |
|---|---|---|
| `@PreFilter` on `Flux<Report>` | Alice's input includes Bob's record; output/side effects contain only Alice's | Interceptor disabled, publisher unfiltered, wrong SpEL |
| `@PostFilter` on `Flux<Report>` | Source contains Alice/Bob; Alice sees only Alice's | Filter only touches wrapper or never runs |
| `@PostFilter` on `Mono<Report>` | One record owned by someone else; verify exact empty/deny behavior of version | Confusing empty response with 403 |
| `@PostFilter` on `Mono<List<Report>>` | List with two owners; observe whether annotation unwraps or fails | Assuming element filtering works when it doesn't |
| `@PreFilter` with two filterable inputs | Use `filterTarget`, verify right parameter is filtered | Filtering wrong argument |
| `@PreFilter` on scalar | Confirm appropriate config reaction or switch to `@PreAuthorize` | Misusing annotation purpose |
| `@PostFilter` on `Map`/`Stream` | Only in documented imperative configurations/APIs | Mixing Servlet branch with Reactive |
| No authentication | Protected endpoint/method rejects as intended | Exposing data via anonymous/empty |
| ADMIN vs USER | ADMIN gets full policy, USER gets filtered | Wrong role prefix/authorities |
| Calling method from same bean | Test self-invocation bypass potential | Annotations declared yet never enforced |
| Large datasets, pagination | Check `count`, `hasNext`, sort after policy | Filtering too late, missing/wrong pages |
| Upgrading Spring Security 6.3 → 6.5/7.x | Re-run full integration suite | Changes in signatures or type handling |

**Test behavior must be "pinned" to the deployed version**, not just log output. In particular, an annotation can **exist and compile** yet fail to protect the return/wrapper type you expected.

### Verification steps when upgrading

1. Record exact versions of **Spring Boot**, **Spring Security**, **Spring Framework**, **Reactor**, JDK, and runtime.
2. Inspect the dependency graph/lockfile to spot mismatched Spring Security module versions.
3. Read reference docs/Javadoc for the corresponding version branch covering reactive interceptors.
4. Test data fixtures containing both permitted and forbidden records, including empty/error cases.
5. Test HTTP JSON **and** direct bean invocation through Spring ApplicationContext (so serializers do not mask issues).
6. Test permissions across multiple tenants, disabled users, missing roles, forged tokens, missing context, and reactive scheduler boundaries.
7. Measure performance: both DB rows returned and filtered rows, memory/CPU latency under large streams.
8. Only after protection behavior is proven by tests should you treat annotations as a reliable guardrail for that configuration.

## 10. Real protection: DB constraints and data-level authorization

In production, taking `authentication.name` and comparing it to `filterObject.owner` is insufficient for every system:

- Usernames can change and are not durable internal user IDs.
- With JWT/OIDC, `Authentication.getName()` may map from `sub`; with multiple issuers, `sub` must be bound to issuer and tenant.
- Records may be shared via ACLs/groups/organizations rather than simple username ownership.
- A record filtered from the HTTP response may still have been read/written to caches, telemetry, or internal events.
- Post-filter pagination can produce empty pages or inaccurate totals.
- Silently dropping elements in batch writes can violate transactional semantics.

Example repository query for R2DBC:

```java
public interface ReportRepository
        extends ReactiveCrudRepository<ReportEntity, String> {

    Flux<ReportEntity> findAllByTenantIdAndOwnerId(
        String tenantId, String ownerId);
}
```

This is an **interface fragment** requiring proper entity/R2DBC mapping, Spring Data dependencies, and trusted IDs; it does not run standalone in the in-memory demo. Key point: **bind tenant/owner directly in the query**. For complex permissions, use a security policy/permission service and proper auditing; for sync JPA/JDBC, isolate blocking boundaries when calling from WebFlux.

A pre-access authorization pattern:

```java
Mono<ReportDto> loadVisible(
        String reportId, String trustedTenant, String trustedUser) {
    return repository.findByIdAndTenantAndOwner(
            reportId, trustedTenant, trustedUser)
        .map(this::toSafeDto);
}
```

This is merely **Java pseudocode**; 403/404 policies for missing records, identity mapping, and repository methods depend on the application. It illustrates that the safest filter avoids loading unauthorized records into memory at all.

## 11. Diagnosing @PreFilter / @PostFilter issues

### Nothing appears to be filtered

- Check that `@EnableReactiveMethodSecurity` is enabled on the right context's configuration.
- Is the method invoked through a **Spring bean proxy**, rather than `this.method()` or `new`?
- Is the annotation placed on the method/implementation visible to the proxy? For interfaces/classes, inspect advisors and method placement.
- Can the expression `filterObject.owner` resolve the property?
- Is the `Authentication` in Reactor Context the expected user? Is Basic/JWT valid?
- Is the return type `Flux<Report>` or `Mono<List<Report>>`? Do not confuse them.
- Do all Spring Security modules match in version and support the Publisher/argument types in use?
- Does the test include records for both matching and mismatching owners? If only matching records exist, bypassed filtering still passes tests.

### SpEL errors or runtime exceptions

- For `Map`, expressions typically require `filterObject.value.owner`.
- For Java record properties, use explicit getters or expressions verified by tests.
- When using `filterTarget`, confirm the parameter name exists in metadata.
- If a reactive expression queries a DB, never call blocking repositories from SpEL on the event loop; use proper reactive authorization or service-layer logic.
- If annotations were copied from Servlet examples, check `PreFilterAuthorizationReactiveMethodInterceptor`/`PostFilterAuthorizationReactiveMethodInterceptor` Javadoc.
- Never catch all errors and call `onErrorReturn(true)` or return unfiltered data to clients.

### Filtering works yet the API behaves wrongly

- `@PostFilter` can produce abnormally short lists compared to pagination metadata.
- If a batch processes only part of input, the response must report partial success or reject the batch per policy.
- If the service performed side effects before filtering, dropping elements from the response does not undo those side effects.
- On large streams, authorization errors late in the stream may occur after the client already received part of the body; never place critical checks at the end of a pipeline.
- If a client requests a single resource, returning empty is not always equivalent to 403/404; design explicit authorization.

## 12. Practical implementation checklist

1. Confirm the app uses WebFlux/reactive rather than confusing Servlet configuration.
2. Enable `@EnableReactiveMethodSecurity`, with a request-level Security chain and proper authentication.
3. Annotate only methods on Spring beans invoked through proxies.
4. Read Javadoc/reference docs for your exact Spring Security version, especially typed support for reactive pre/post filters.
5. For `Flux<T>`, write tests **containing both valid and invalid elements**. For `Mono<List<T>>`, do not extrapolate from `Flux<T>`.
6. For single-resource `Mono<T>`, define clear unauthorized status codes; never treat filter empty as denial automatically.
7. For `@PreFilter` on write batches, define all-or-nothing vs. partial success, auditing, and transaction semantics.
8. Protect data directly in repositories/queries; use annotations as defense-in-depth where suitable, never as a substitute for tenant isolation.
9. Test CSRF for browsers/cookies, handle credentials/roles properly, and never disable security because tests fail.
10. Investigate root causes when migrations alter interceptor configs, classloaders, versions, or target methods.
11. For async jobs, queues, and scheduled tasks, define how Reactor Context/Authentication is propagated.
12. Monitor latency, DB rows scanned, filtered record counts, cache/log leaks, and security exceptions.
13. Never return raw `Authentication`, password hashes, access tokens, or tenant secrets in data or filter logs.
14. Roll out only after integration tests prove the server **never returns out-of-scope records** to restricted callers.

## 13. Practice exercises

1. Write `@PreFilter("filterObject.owner == authentication.name")` on an input collection in **imperative** Spring Security, then write tests distinguishing input filtering from whole-method denial.
2. Write `@PostFilter` for `Flux<Report>` in WebFlux (Spring Security 6.3), test Alice/Bob/Admin, and compare against a `Flux.filter(...)` baseline.
3. Change the return signature to `Mono<List<Report>>` while keeping the annotation. What happens in your version? Do not guess; prove it with tests.
4. For a `Mono<Report>` method, design returning 403/404 for IDs not owned by the caller using repository/service checks instead of relying solely on `@PostFilter`.
5. With `Map<String,Report>` in an imperative method, explain why `filterObject.value.owner` differs from `filterObject.owner`.
6. Create a self-invocation test: method A calls `this.annotatedMethod()`. Observe how it can bypass the proxy, then extract into another bean.
7. Write an R2DBC query with `tenant_id` and `owner_id` to paginate after permission filtering; compare with `findAll().filter(...)`.
8. Design a batch write API where one record does not belong to the user. Choose **fail entire batch** or **partial success** and define response, audit, and transaction behavior.
9. Run the same test suite on Spring Security 6.3 and 6.5/7.x; document behavioral changes rather than merely checking compilation.
10. Use `Flux.filterWhen(...)` with per-record async permission checks, bounding concurrency and failing closed on repository errors.

## Summary

- **`@PreFilter`** filters **input** elements before the method processes them; **`@PostFilter`** filters **output** elements after the method provides results.
- These two annotations are **not equivalent to `@PreAuthorize`/`@PostAuthorize`**: filtering usually keeps/drops elements, whereas authorize decides whether to grant/deny access.
- For Spring Security **Servlet**, collections, arrays, maps, and streams are documented as supported; for **Reactive/WebFlux**, reactive filter interceptors exist since Spring Security 5.8, yet **exact Publisher types, wrappers, and version behavior must be verified via integration tests**.
- `Flux<T>`, `Mono<T>`, and `Mono<List<T>>` are **not the same data type**. Do not assume annotations automatically deep-filter elements inside wrappers.
- For sensitive data, tenants, and batch writes, **repository filtering + explicit authorization + negative tests** always matter more than relying on a post-filter layer.

## Official references

1. Spring Security 6.3 — Reactive Method Security: https://docs.spring.io/spring-security/reference/6.3/reactive/authorization/method.html
2. Spring Security 6.5 — Reactive Method Security: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html
3. Spring Security 7.0 — Reactive Method Security (for upgrade comparison): https://docs.spring.io/spring-security/reference/7.0/reactive/authorization/method.html
4. Spring Security 6.3 — PreFilterAuthorizationReactiveMethodInterceptor Javadoc: https://docs.spring.io/spring-security/site/docs/6.3.8/api/org/springframework/security/authorization/method/PreFilterAuthorizationReactiveMethodInterceptor.html
5. Spring Security 6.3 — PostFilterAuthorizationReactiveMethodInterceptor Javadoc: https://docs.spring.io/spring-security/site/docs/6.3.x/api/org/springframework/security/authorization/method/PostFilterAuthorizationReactiveMethodInterceptor.html
6. Spring Security 6.5 — Servlet Method Security, Collection/array/Map/Stream support: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
7. Spring Security 6.5 — Reactive Test Support: https://docs.spring.io/spring-security/reference/6.5/reactive/test/index.html
8. Spring Framework — Spring AOP proxies and self-invocation: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
