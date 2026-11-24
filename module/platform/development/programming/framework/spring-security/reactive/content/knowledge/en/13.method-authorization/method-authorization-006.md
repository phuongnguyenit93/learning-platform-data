# SpEL Expressions with authentication, principal, and Method Parameters

> **Topic:** Spring Security – reactive  
> **Group:** Method Authorization  
> **Objective:** Use Spring Expression Language (SpEL) in `@PreAuthorize` to bind the verified identity to method parameters; distinguish `authentication`, `principal`, `#owner`, `#p0`, and policy beans; practice with Spring WebFlux Java 17+, `WebTestClient`, and `StepVerifier`.

## 1. Practical scenario and desired outcome

Suppose user `alice` logs in successfully and calls `GET /api/invoice/bob/inv-42`. An HTTP rule requiring only `authenticated()` lets the request pass because Alice's password is valid. Yet business policy must also decide whether Alice **is allowed to view Bob's invoice**. This is why authorization belongs at the service/method layer instead of stopping at URL authorization.

A simple rule:

```java
@PreAuthorize("hasAuthority('invoice:read') and #owner == authentication.name")
public Mono<String> invoice(
        @P("owner") String owner, String invoiceId) {
    return Mono.just("invoice=" + invoiceId + ",owner=" + owner);
}
```

The snippet above **is not a standalone program**: it needs a Spring bean, `@EnableReactiveMethodSecurity`, imports, and a security context. Meaning: only someone holding `invoice:read` whose username matches the `owner` parameter is allowed to call the method.

- `authentication`: the `Authentication` object established by Spring Security;
- `authentication.name`: the result of `Authentication.getName()`;
- `#owner`: the SpEL variable mapped from the method parameter annotated with `@P("owner")`;
- `hasAuthority`: checks the exact `GrantedAuthority` string;
- `and`: both conditions must evaluate to true.

**IDOR/BOLA warning:** `owner` is a parameter a user can self-declare in the URL. If an attacker calls `/api/invoice/alice/inv-of-bob`, the expression may pass even though the invoice ID belongs to Bob. Therefore **comparing a method param against the principal is only one guard**; when reading real data, verify the owner and tenant from storage by resource ID. See section 12.

### What will you be able to do after this lesson?

1. Enable `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` properly for Spring WebFlux.
2. Explain the root object/properties `authentication`, `principal`, and methods `hasRole`, `hasAuthority`.
3. Reference method arguments by name `#owner`, by `@P("owner")`, or by position `#p0`/`#a0`.
4. Write expressions with `and`/`or`, distinguishing an `owner only` rule from `admin OR owner`.
5. Understand that `principal` may be `UserDetails`, `Jwt`, `String`, or a custom object.
6. Offload complex logic to a SpEL bean `@ownerPolicy.canView(...)` returning `Mono<Boolean>` instead of blocking.
7. Verify method security across Spring AOP proxies, Reactor Context, HTTP 401/403, and subscription tests.

## 2. Where does method security sit in a reactive application?

There are two common authorization layers:

| Layer | Configuration/API | Question |
| --- | --- | --- |
| HTTP WebFlux | `SecurityWebFilterChain`, `ServerHttpSecurity.authorizeExchange` | Does this URL require login, a role, or a scope? |
| Method/service | `@PreAuthorize("...")` and method-security interceptors | Is this user permitted to invoke **this business function with these specific arguments**? |

Method-level authorization is applied by Spring Security via **Spring AOP proxies**, not by Java executing annotations natively. The annotation holds a SpEL string parsed during security evaluation. Misspelling a variable or property is usually a **runtime error**, not a `javac` compile error.

```text
Browser / API client
  |
  v
HTTP WebFilter chain
  ├─ AuthenticationWebFilter: extracts/verifies credentials
  ├─ SecurityContext in Reactor Context
  └─ AuthorizationWebFilter: HTTP matcher
  |
  v
@RestController
  |
  v
Injected InvoiceService (Spring proxy)
  |
  v
Reactive method interceptor: @PreAuthorize
  ├─ DENY: emits AccessDeniedException -> HTTP usually 403
  └─ ALLOW: invokes business logic, continues Mono/Flux -> HTTP usually 200
```

This is a simplified diagram; real applications also include additional filters, entry points, CSRF, CORS, security context persistence, and exception translation. In this lesson's HTTP Basic tests, requests without credentials usually return 401; authenticated users failing SpEL usually return 403.

### 2.1. Enabling the right reactive annotation

```java
@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class SecurityConfiguration {
    // Define SecurityWebFilterChain and user store in the complete example.
}
```

Import `EnableReactiveMethodSecurity` from `org.springframework.security.config.annotation.method.configuration`. Depending on the Spring Security version, `useAuthorizationManager` may be the default; specifying it explicitly ensures the Spring Security 6.5 example uses the reactive AuthorizationManager model, including boolean expressions and beans returning `Mono<Boolean>`.

**Reactive return type:** protected methods should return a publisher such as `Mono<T>` or `Flux<T>` so the interceptor can interact with Reactor Context at subscription time. Do not use Servlet's `@EnableMethodSecurity` without `@EnableReactiveMethodSecurity` and expect the same behavior.

### 2.2. Proxies and self-invocation

If you instantiate `new InvoiceService()` instead of retrieving the bean from the Spring context, annotations will not run automatically. If `public Mono<?> outer()` calls `this.securedInner()` **within the same bean**, the internal call can bypass the proxy. Place checks on the entrypoint method actually called through a Spring bean, or extract secured services into separate beans.

`private` or `final` methods can also cause proxy issues depending on the proxy strategy. Good design: Spring service beans, proxyable methods, injected into controllers, with negative tests proving denial actually occurs.

## 3. authentication: identity verified by Spring Security

In method security SpEL, `authentication` represents `org.springframework.security.core.Authentication`.

```text
authentication.name          -> Authentication.getName()
authentication.principal     -> Authentication.getPrincipal()
authentication.authorities   -> Authentication.getAuthorities()
authentication.authenticated -> Authentication.isAuthenticated()
```

Example:

```java
@PreAuthorize("authentication.name == #owner")
```

`authentication.name` comes from the **current Authentication**, never from `X-User`, `?username=`, or self-declared form fields. A Basic, session, or JWT app may authenticate via different mechanisms, yet Spring Security ultimately supplies the corresponding `Authentication`.

Common conditions:

```java
@PreAuthorize("isAuthenticated() and #owner == authentication.name")
@PreAuthorize("hasRole('ADMIN')")
@PreAuthorize("hasAuthority('invoice:read')")
@PreAuthorize("hasRole('ADMIN') or #owner == authentication.name")
```

These are four separate examples; **do not** stack multiple `@PreAuthorize` annotations on the same method expecting them to combine. Each annotation represents a policy. `isAuthenticated()` excludes anonymous callers from the condition; `hasRole('ADMIN')` normally requires authority `ROLE_ADMIN`, whereas `hasAuthority('invoice:read')` requires the exact string `invoice:read`.

### 3.1. Authentication differs from ThreadLocal

Reactive Spring Security provides `SecurityContext` through the **subscription's Reactor Context**. Java service code reads it directly:

```java
ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName);
```

The snippet above returns `Mono<String>`, not a ready-made string. Never call `.block()` on the Netty event loop, and never use imperative `SecurityContextHolder.getContext()` assuming the same thread stays across the entire request. `publishOn` may switch threads, yet Reactor Context travels with the subscription across a valid Reactor chain.

`@PreAuthorize` is wired by reactive Spring Security to this Context; it does not need a static user variable. In non-HTTP tests, you can supply Authentication for a specific subscription using `ReactiveSecurityContextHolder.withAuthentication(auth)`.

### 3.2. Do not rely solely on authentication.authenticated

An `Authentication` representing an anonymous user may also exist in the chain depending on configuration. If you want a logged-in user, `isAuthenticated()` is an appropriate expression. Do not check only `authentication.name != null`: an `anonymousUser` placeholder name or fake principal does not prove a successful login.

Never use `authentication.credentials` in authorization expressions, logs, or responses: it may hold a password/token or have already been erased. Authorization decisions should rely on verified identity, authorities, and trusted resource state.

## 4. principal: object type depends on authentication mechanism

In SpEL:

```text
principal ≈ authentication.principal
```

However, **principal is not always `UserDetails`**.

| Authentication source | Typical principal | Is `principal.username` safe? |
| --- | --- | --- |
| HTTP Basic with `MapReactiveUserDetailsService` | Spring Security `UserDetails` | Yes, if the object has `getUsername()` |
| Form login with `UserDetailsService` | Usually `UserDetails` | Yes, for that implementation type |
| OAuth2 Resource Server JWT | `Jwt` or converter-supplied principal | **Do not assume** `username` exists |
| Custom service identity | `String` or custom class | Depends on the object's API |
| Anonymous | Anonymous placeholder principal | Should not be treated as a real user |

Compare:

```java
@PreAuthorize("principal.username == #owner")
```

is only valid if the principal has `getUsername()`. It works in the HTTP Basic/`UserDetails` example below. A less class-coupled approach is usually:

```java
@PreAuthorize("authentication.name == #owner")
```

Yet even `authentication.name` may be mapped from `sub`, `client_id`, or a custom principal depending on the authentication converter. Standardize the **identity key** and tenant policy rather than assuming the returned name is always an email.

### 4.1. How does SpEL read properties?

SpEL uses property syntax corresponding to getters:

```text
authentication.name       -> getName()
principal.username        -> getUsername(), if it exists
authentication.principal  -> getPrincipal()
```

If the principal is a `String` and an expression reads `principal.username`, evaluation may fail because the property does not exist. Null-safe `principal?.username` only guards against a null receiver; **it does not invent a missing getter**. Instead of long chains like `principal.profile.organization.id`, normalize claims into `Authentication` or move the check into a tested Java policy.

## 5. Method parameters: #owner, #p0, #a0

SpEL uses **`#`** to denote variables. When Spring Security evaluates `@PreAuthorize` on a method, Java arguments can be accessed by **name** or **position**.

```java
public Mono<String> read(String owner, String invoiceId)
```

Suppose `read("alice", "inv-42")` is called:

| Expression | Value | How it is resolved |
| --- | --- | --- |
| `#owner` | `alice` | Parameter name must be discovered or annotated |
| `#invoiceId` | `inv-42` | Name of the second argument |
| `#p0` | `alice` | Parameter at **index 0** |
| `#a0` | `alice` | Alias for index 0 |
| `#p1` | `inv-42` | Parameter at index 1 |
| `#root` | Root evaluation object | Not `owner` or `invoiceId` |

### 5.1. @P("owner") is an explicit choice

```java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import reactor.core.publisher.Mono;

@PreAuthorize("#owner == authentication.name")
public Mono<String> own(@P("owner") String owner) {
    return Mono.just("own:" + owner);
}
```

This is a **snippet inside a class/service**. `@P` requires importing **`org.springframework.security.access.method.P`** (do not invent `org.springframework.security.core.parameters.P`). Regardless of whether the Java compiler retains parameter names, `@P("owner")` tells method security the exact variable name to bind.

### 5.2. Using parameter name metadata

If a method is compiled with `-parameters`, Spring Security can discover `owner` for `#owner`. With Maven:

```xml
<properties>
    <maven.compiler.parameters>true</maven.compiler.parameters>
</properties>
```

However, do not assume every module/library is compiled identically. When using interfaces, proxies, bytecode stripped of parameter metadata, or different build pipelines, `#owner` may fail to bind properly. For critical permissions, prefer `@P` or test explicitly.

### 5.3. #p0 and #a0 rely on argument order

```java
@PreAuthorize("hasAuthority('invoice:read') and #p0 == authentication.name")
public Mono<String> position(String owner) {
    return Mono.just("position:" + owner);
}
```

`#p0` does not need the parameter name `owner`. Yet if you refactor `position(String owner)` to `position(String invoiceId, String owner)` and forget to update the expression, `#p0` will **compare `invoiceId` against username**, potentially causing an authorization bug. Named variables are usually clearer when there are multiple parameters.

### 5.4. Misspelled variable name or missing `#` symbol

```java
// Wrong if the method only has a parameter named owner:
@PreAuthorize("#user == authentication.name")
public Mono<String> own(String owner);
```

`#user` does not automatically point to `owner`. Similarly, `owner` without `#` may be interpreted by SpEL as a property on the expression root rather than a method variable. Write `#owner` or `#p0` explicitly and test denial cases.

## 6. AND, OR, role/authority, and beans in SpEL

SpEL supports `and`/`or` or `&&`/`||`:

```java
@PreAuthorize("hasRole('ADMIN') or #owner == principal.username")
```

Admin **or** owner is permitted. Using `and` requires both the role and ownership. Avoid flipping requirements from "admin OR owner" into "admin AND owner" in code.

Representative expressions:

| Expression | Condition | Notes |
| --- | --- | --- |
| `isAuthenticated()` | Caller is authenticated | Do not check only `name != null` |
| `hasRole('ADMIN')` | Usually requires `ROLE_ADMIN` | Default prefix `ROLE_` |
| `hasAuthority('invoice:read')` | Exact permission name | Does not prepend any prefix |
| `authentication.name == #owner` | Username matches owner param | Does not prove real invoice ownership |
| `principal.username == #owner` | Principal getter matches owner | Only when principal exposes getter |
| `#p0 == authentication.name` | Compares first argument | Can drift during refactors |
| `A and B` | Requires both A and B | Logical AND |
| `A or B` | Requires A or B | Logical OR |
| `@ownerPolicy.canView(authentication, #owner)` | Calls a Spring bean | Extracts policy from long strings |

### 6.1. When should you call a bean instead of stuffing a long expression?

If business policy involves multiple roles, database ownership, tenants, transaction history, or frequently changing rules, long SpEL strings become hard to audit. Spring Security supports `@beanName.method(...)`; `@ownerPolicy` refers to a Spring bean, distinct from method variable `#owner`.

```java
@PreAuthorize("@ownerPolicy.canView(authentication, #owner)")
public Mono<String> byPolicy(@P("owner") String owner) {
    return Mono.just("policy:" + owner);
}
```

With `@EnableReactiveMethodSecurity(useAuthorizationManager = true)`, a bean called in an expression can return **`Boolean` or `Mono<Boolean>`** reactively. Never call `repositoryCall.block()` inside an expression; let the policy return a publisher of the async result, accompanied by tests and appropriate timeouts.

## 7. Mind subscription, Reactor Context, and 401/403 errors

```text
Request Authorization: Basic valid for alice
  |
  v
Spring Security WebFlux -> Authentication(name=alice)
  |
  v
SecurityContext carried in Reactor Context
  |
  v
Controller calls InvoiceService via AOP proxy
  |
  v
@PreAuthorize("#owner == authentication.name")
  |
  +-- owner=alice  --> grant --> Business Publisher --> HTTP 200
  |
  +-- owner=bob    --> deny --> AccessDeniedException --> HTTP 403
```

**Note:** a reactive chain separates assembly and subscription; not everything runs synchronously when the method is called. The reactive method interceptor applies authorization along the pipeline, receiving the current subscription's security context. A service calling `subscribe()` manually inside a callback can detach from the context and lose error/cancellation propagation. Return `Mono`/`Flux` rather than calling `block()` or manual `subscribe()`.

HTTP `authenticated()` rejects anonymous requests before reaching the method: usually **401** with a Basic challenge. If credentials are valid yet `@PreAuthorize` denies access, the method-level error normally becomes **403**. Do not attribute every 403 to `@PreAuthorize`: CSRF, HTTP `denyAll`, or other policy gates can also produce 403.

## 8. Complete Java 17+ project with Spring Security WebFlux

This example pins **Spring Boot 3.5.16** for a released learning baseline; this is the final release of the 3.5 line whose OSS support has ended. For new deployments, choose a supported Spring Boot branch (4.x) and adapt dependencies and test APIs per the migration guide. The project below uses Java 17+ and Boot-managed Spring Security 6.x.

**Four demo accounts** (shared password `demo123`, for learning only):

| Username | GrantedAuthority | Purpose |
| --- | --- | --- |
| `alice` | `invoice:read` | Allowed to read her own invoices |
| `bob` | `invoice:read` | Allowed to read his own invoices |
| `admin` | `ROLE_ADMIN`, `invoice:read` | Has role-based override where declared |
| `visitor` | `ROLE_VIEWER` | Logged in, but lacks `invoice:read` |

HTTP security only requires `/api/**` to be `authenticated`. Fine-grained permissions live in `InvoiceService`, highlighting the separation between HTTP and methods. Endpoints are GET, so CSRF is not disabled.

### 8.1. Directory layout

```text
method-spel-webflux/
├── pom.xml
└── src/
    ├── main/java/demo/spel/
    │   ├── Application.java
    │   ├── SecurityConfiguration.java
    │   ├── OwnerPolicy.java
    │   ├── InvoiceService.java
    │   └── InvoiceController.java
    └── test/java/demo/spel/
        ├── ReactiveMethodSpelHttpTests.java
        └── ReactiveMethodSpelPublisherTests.java
```

### 8.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>method-spel-webflux</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
        <maven.compiler.parameters>true</maven.compiler.parameters>
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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
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
```

### 8.3. Application.java

```java
package demo.spel;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

### 8.4. SecurityConfiguration.java

```java
package demo.spel;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        // Demo: do not hardcode real secrets in source.
        String password = "demo123";

        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode(password))
            .authorities("invoice:read")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode(password))
            .authorities("invoice:read")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode(password))
            .authorities("ROLE_ADMIN", "invoice:read")
            .build();

        UserDetails visitor = User.withUsername("visitor")
            .password(encoder.encode(password))
            .authorities("ROLE_VIEWER")
            .build();

        return new MapReactiveUserDetailsService(
            alice, bob, admin, visitor);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/health").permitAll()
                .pathMatchers("/api/**").authenticated()
                .anyExchange().denyAll())
            .httpBasic(withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }
}
```

**Explanation:** `@EnableReactiveMethodSecurity` registers method interceptors, while `SecurityWebFilterChain` provides HTTP Basic and enforces URL login. `roles("ADMIN")` is equivalent to granting `ROLE_ADMIN`; the example uses `authorities` explicitly to test both roles and permissions easily. BCrypt stores hashes in the in-memory user store. Never use this password pattern outside localhost, and never disable HTTPS validation in real environments.

### 8.5. OwnerPolicy.java

```java
package demo.spel;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component("ownerPolicy")
public class OwnerPolicy {

    public Mono<Boolean> canView(
            Authentication authentication, String owner) {
        return Mono.fromSupplier(() -> {
            if (authentication == null
                    || !authentication.isAuthenticated()) {
                return false;
            }

            boolean admin = authentication.getAuthorities().stream()
                .anyMatch(a -> "ROLE_ADMIN".equals(a.getAuthority()));

            boolean read = authentication.getAuthorities().stream()
                .anyMatch(a -> "invoice:read".equals(a.getAuthority()));

            boolean sameOwner = authentication.getName().equals(owner);
            return admin || (read && sameOwner);
        });
    }
}
```

`@Component("ownerPolicy")` creates a bean whose name matches `@ownerPolicy` in the expression. `Mono.fromSupplier` is non-blocking and evaluates at subscription time. A real-world policy can use a reactive repository to look up the owner from `invoiceId`. Never turn `Mono<Boolean>` into a boolean by calling `block()`.

### 8.6. InvoiceService.java

```java
package demo.spel;

import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class InvoiceService {

    @PreAuthorize("isAuthenticated() and #owner == authentication.name")
    public Mono<String> own(@P("owner") String owner) {
        return Mono.just("own:" + owner);
    }

    // Demo Basic UserDetails has getter getUsername().
    @PreAuthorize("isAuthenticated() and principal.username == #owner")
    public Mono<String> byPrincipal(@P("owner") String owner) {
        return Mono.just("principal:" + owner);
    }

    @PreAuthorize("hasAuthority('invoice:read') and #p0 == authentication.name")
    public Mono<String> positional(String owner) {
        return Mono.just("position:" + owner);
    }

    @PreAuthorize("hasRole('ADMIN') or #owner == principal.username")
    public Mono<String> viewOrAdmin(@P("owner") String owner) {
        return Mono.just("view:" + owner);
    }

    @PreAuthorize("hasAuthority('invoice:read') and #owner == authentication.name")
    public Mono<String> invoice(
            @P("owner") String owner,
            @P("invoiceId") String invoiceId) {
        return Mono.just("invoice=" + invoiceId + ",owner=" + owner);
    }

    @PreAuthorize("@ownerPolicy.canView(authentication, #owner)")
    public Mono<String> byPolicy(@P("owner") String owner) {
        return Mono.just("policy:" + owner);
    }
}
```

Precise behavior of each method:

- `own`: only checks that the caller is logged in and `owner` matches `Authentication.getName()`.
- `byPrincipal`: checks the `username` property on the `UserDetails` principal.
- `positional`: first argument `#p0` matches name and caller holds `invoice:read`.
- `viewOrAdmin`: **OR** rule; admins can view other accounts, while regular users can view only their own.
- `invoice`: combines a permission with named parameters; does **not** query real DB ownership.
- `byPolicy`: delegates to a Java bean returning `Mono<Boolean>` per reactive method security.

### 8.7. InvoiceController.java

```java
package demo.spel;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class InvoiceController {
    private final InvoiceService service;

    public InvoiceController(InvoiceService service) {
        this.service = service;
    }

    @GetMapping("/health")
    public Mono<String> health() {
        return Mono.just("OK");
    }

    @GetMapping("/api/own/{owner}")
    public Mono<String> own(@PathVariable String owner) {
        return service.own(owner);
    }

    @GetMapping("/api/principal/{owner}")
    public Mono<String> principal(@PathVariable String owner) {
        return service.byPrincipal(owner);
    }

    @GetMapping("/api/position/{owner}")
    public Mono<String> position(@PathVariable String owner) {
        return service.positional(owner);
    }

    @GetMapping("/api/view/{owner}")
    public Mono<String> view(@PathVariable String owner) {
        return service.viewOrAdmin(owner);
    }

    @GetMapping("/api/invoice/{owner}/{invoiceId}")
    public Mono<String> invoice(
            @PathVariable String owner,
            @PathVariable String invoiceId) {
        return service.invoice(owner, invoiceId);
    }

    @GetMapping("/api/policy/{owner}")
    public Mono<String> policy(@PathVariable String owner) {
        return service.byPolicy(owner);
    }

    @GetMapping("/api/me")
    public Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(auth -> {
                Object principal = auth.getPrincipal();
                String principalName = principal instanceof UserDetails details
                    ? details.getUsername() : auth.getName();
                return "authentication=" + auth.getName()
                    + ";principal=" + principalName;
            });
    }
}
```

The controller receives `InvoiceService` via constructor injection, so calls pass through the Spring proxy. It does not call `subscribe()`/`block()` itself; this is a core WebFlux requirement. The `/api/me` endpoint is solely for inspecting Authentication and principal in the demo; avoid exposing full security context details in production.

## 9. WebTestClient test suite using real HTTP Basic

This suite verifies login and method security through the entire WebFlux stack. Using `bindToApplicationContext(...).apply(springSecurity())` runs the filter chain in tests; requests send real `Authorization: Basic ...` headers via `HttpHeaders.setBasicAuth`. Do not use `mockUser` and claim password verification was tested.

### 9.1. ReactiveMethodSpelHttpTests.java

```java
package demo.spel;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class ReactiveMethodSpelHttpTests {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    private WebTestClient.ResponseSpec getAs(String username, String path) {
        return client.get().uri(path)
            .headers(h -> h.setBasicAuth(username, "demo123"))
            .exchange();
    }

    @Test
    void publicHealthDoesNotNeedAuthentication() {
        client.get().uri("/health")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("OK");
    }

    @Test
    void missingCredentialsReturn401BeforeMethodAuthorization() {
        client.get().uri("/api/own/alice")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().exists(HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void incorrectBasicPasswordReturns401() {
        client.get().uri("/api/own/alice")
            .headers(h -> h.setBasicAuth("alice", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void matchingAuthenticationNameAndOwnerAreAllowed() {
        getAs("alice", "/api/own/alice")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("own:alice");
    }

    @Test
    void differentMethodOwnerIsDenied() {
        getAs("alice", "/api/own/bob")
            .expectStatus().isForbidden();
    }

    @Test
    void anotherUserCanAccessTheirOwnOwnerMethod() {
        getAs("bob", "/api/own/bob")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("own:bob");
    }

    @Test
    void ownerOnlyCheckDoesNotRequireInvoiceReadAuthority() {
        getAs("visitor", "/api/own/visitor")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("own:visitor");
    }

    @Test
    void principalUsernameWorksForUserDetailsPrincipal() {
        getAs("alice", "/api/principal/alice")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("principal:alice");
    }

    @Test
    void principalUsernameRejectsOtherOwner() {
        getAs("bob", "/api/principal/alice")
            .expectStatus().isForbidden();
    }

    @Test
    void positionalParameterP0AllowsSameOwner() {
        getAs("alice", "/api/position/alice")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("position:alice");
    }

    @Test
    void positionalParameterP0RejectsDifferentOwner() {
        getAs("alice", "/api/position/bob")
            .expectStatus().isForbidden();
    }

    @Test
    void positionalParameterAlsoRequiresInvoiceRead() {
        getAs("visitor", "/api/position/visitor")
            .expectStatus().isForbidden();
    }

    @Test
    void ownerCanViewOwnResource() {
        getAs("alice", "/api/view/alice")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("view:alice");
    }

    @Test
    void ordinaryUserCannotViewAnotherOwner() {
        getAs("alice", "/api/view/bob")
            .expectStatus().isForbidden();
    }

    @Test
    void adminCanViewAnotherOwnerUsingRoleExpression() {
        getAs("admin", "/api/view/alice")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("view:alice");
    }

    @Test
    void adminDoesNotAutomaticallyBypassStrictOwnerOnlyRule() {
        getAs("admin", "/api/own/alice")
            .expectStatus().isForbidden();
    }

    @Test
    void namedOwnerAndInvoiceIdArgumentsBindCorrectly() {
        getAs("alice", "/api/invoice/alice/inv-42")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("invoice=inv-42,owner=alice");
    }

    @Test
    void invoiceRequiresOwnerMatch() {
        getAs("alice", "/api/invoice/bob/inv-42")
            .expectStatus().isForbidden();
    }

    @Test
    void invoiceAlsoRequiresReadAuthority() {
        getAs("visitor", "/api/invoice/visitor/inv-42")
            .expectStatus().isForbidden();
    }

    @Test
    void reactiveBeanPolicyAllowsOwnerWithPermission() {
        getAs("alice", "/api/policy/alice")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("policy:alice");
    }

    @Test
    void reactiveBeanPolicyRejectsAnotherOwner() {
        getAs("alice", "/api/policy/bob")
            .expectStatus().isForbidden();
    }

    @Test
    void reactiveBeanPolicyAllowsAdmin() {
        getAs("admin", "/api/policy/bob")
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("policy:bob");
    }

    @Test
    void reactiveBeanPolicyRejectsVisitorWithoutReadAuthority() {
        getAs("visitor", "/api/policy/visitor")
            .expectStatus().isForbidden();
    }

    @Test
    void securityContextContainsExpectedPrincipal() {
        getAs("alice", "/api/me")
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("authentication=alice;principal=alice");
    }
}
```

There are **24 `@Test` methods**. Each test's outcome is independent: missing or wrong HTTP Basic => 401; valid login failing SpEL => 403; matching username/authority => 200. The `principal.username` condition is proven specifically for this project's `UserDetails` principal.

### 9.2. Key behavior matrix

| User | URL | Highlighted SpEL | Expected status |
| --- | --- | --- | --- |
| Anonymous | `/api/own/alice` | HTTP authenticated | **401** |
| Alice, wrong password | `/api/own/alice` | Authentication failed | **401** |
| Alice | `/api/own/alice` | `#owner == authentication.name` | **200** |
| Alice | `/api/own/bob` | Owner mismatch | **403** |
| Visitor | `/api/own/visitor` | Owner-only, no invoice permission needed | **200** |
| Visitor | `/api/position/visitor` | Lacks `invoice:read` | **403** |
| Alice | `/api/principal/alice` | `principal.username` | **200** |
| Alice | `/api/position/bob` | `#p0` mismatch | **403** |
| Alice | `/api/view/bob` | Neither admin nor owner | **403** |
| Admin | `/api/view/alice` | `hasRole('ADMIN')` | **200** |
| Admin | `/api/own/alice` | Owner-only rule | **403** |
| Alice | `/api/invoice/alice/inv-42` | Has authority, owner matches | **200** |
| Alice | `/api/policy/bob` | `Mono<Boolean>` bean returns false | **403** |
| Admin | `/api/policy/bob` | Bean has admin branch | **200** |

**Do not assert fixed 401/403 error bodies** without customizing entry points and access-denied handlers. Secondary bodies/headers can vary across Spring Boot, servers, and content negotiation.

## 10. Testing publishers directly with StepVerifier

These tests use the Spring-context service bean **without launching an HTTP request**. Instead, they supply `Authentication` to the subscription via `ReactiveSecurityContextHolder.withAuthentication`.

### ReactiveMethodSpelPublisherTests.java

```java
package demo.spel;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@SpringBootTest
class ReactiveMethodSpelPublisherTests {

    @Autowired
    InvoiceService service;

    private static Authentication auth(String username, String... authorities) {
        return new TestingAuthenticationToken(username, "unused", authorities);
    }

    @Test
    void publisherAllowsMatchingNameAndAuthority() {
        Mono<String> source = service.positional("alice")
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                    auth("alice", "invoice:read")));

        StepVerifier.create(source)
            .expectNext("position:alice")
            .verifyComplete();
    }

    @Test
    void publisherDeniesDifferentName() {
        Mono<String> source = service.positional("bob")
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                    auth("alice", "invoice:read")));

        StepVerifier.create(source)
            .expectError(AccessDeniedException.class)
            .verify();
    }

    @Test
    void publisherDeniesMissingAuthority() {
        Mono<String> source = service.positional("alice")
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                    auth("alice", "ROLE_VIEWER")));

        StepVerifier.create(source)
            .expectError(AccessDeniedException.class)
            .verify();
    }

    @Test
    void publisherUsesIndependentContextPerSubscription() {
        Mono<String> source = service.own("bob");

        StepVerifier.create(source.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                    auth("bob", "invoice:read"))))
            .expectNext("own:bob")
            .verifyComplete();

        StepVerifier.create(source.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                    auth("alice", "invoice:read"))))
            .expectError(AccessDeniedException.class)
            .verify();
    }
}
```

There are **4 StepVerifier tests**, bringing the project total to **28 tests**. `TestingAuthenticationToken` is a **mock test token**; `withAuthentication` focuses on verifying method security rules, yet **does not verify real passwords**. To test HTTP Basic/passwords, the `WebTestClient` tests with real credentials in section 9 remain necessary.

Each `contextWrite` applies only to its upstream subscription; having two subscribers for `bob` and `alice` does not leak identity across them. This is crucial in applications serving many concurrent requests across a pool of event-loop threads.

## 11. Running Maven, checking output, and testing with curl

From the directory containing `pom.xml`, with Java 17+ and compatible Maven:

```bash
java -version
mvn -version
mvn clean test
```

Expected result from the listed code: **28 test methods**, comprising 24 `WebTestClient` tests and 4 `StepVerifier` tests. Maven Surefire reports `Tests run: 28, Failures: 0, Errors: 0` and `BUILD SUCCESS` when environment/dependencies match and no unexpected failures occur. **This is the lesson's expected result, not a claim that it ran on your machine.** Inspect `target/surefire-reports` to investigate if results differ.

Start the WebFlux server:

```bash
mvn spring-boot:run
```

Try with demo accounts on localhost:

```bash
# Public health
curl -i http://localhost:8080/health

# Missing credentials: 401
curl -i http://localhost:8080/api/own/alice

# Valid caller: 200
curl -i -u alice:demo123 http://localhost:8080/api/own/alice

# Caller alice, owner bob: 403
curl -i -u alice:demo123 http://localhost:8080/api/own/bob

# UserDetails principal matches username: 200
curl -i -u alice:demo123 http://localhost:8080/api/principal/alice

# Positional variable #p0: 200
curl -i -u alice:demo123 http://localhost:8080/api/position/alice

# ADMIN via OR branch: 200
curl -i -u admin:demo123 http://localhost:8080/api/view/bob

# Admin cannot bypass owner-only rule: 403
curl -i -u admin:demo123 http://localhost:8080/api/own/alice

# Reactive SpEL bean returning Mono<Boolean>
curl -i -u alice:demo123 http://localhost:8080/api/policy/alice
curl -i -u alice:demo123 http://localhost:8080/api/policy/bob
```

PowerShell may require `curl.exe` instead of `curl`. **Never use real credentials on the command line** in production environments because shell history/process inspection can expose passwords. Use HTTPS/TLS outside localhost, strong password hashing, and secret management.

A successful response from `/api/own/alice`:

```http
HTTP/1.1 200 OK
Content-Type: text/plain;charset=UTF-8

own:alice
```

A response denied by method security:

```http
HTTP/1.1 403 Forbidden
```

A response missing HTTP Basic authentication:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Realm"
```

The `realm` header and secondary headers are not fixed unless explicitly configured. Tests in section 9 only assert the challenge exists rather than hardcoding the exact realm.

## 12. Security boundary: account owner is not resource owner

The SpEL expression:

```java
@PreAuthorize("#owner == authentication.name")
```

**does not by itself prevent IDOR/BOLA**. If `owner` is sent by the client, attacker Alice can construct URL `/api/invoice/alice/invoice-owned-by-bob`: `owner == authentication.name` passes, yet the actual invoice does not belong to Alice. Therefore, never let a method rely on a self-declared `owner` parameter to decide whether a resource belongs to the caller.

Better design:

```text
1. Obtain trusted identity + tenantId from verified Authentication/claims.
2. Look up the real invoice by invoiceId within the tenant scope.
3. Read the actual ownerId from the stored invoice.
4. Compare ownerId against Authentication's subjectId, or check admin
   permission granted for that tenant/resource.
5. Only when permitted, emit content or perform the mutation.
```

Reactive repository pseudocode example:

```java
// API illustration; define InvoiceRepository, Invoice, and auth context yourself.
return repository.findByIdAndTenantId(invoiceId, trustedTenantId)
    .filter(invoice ->
        invoice.ownerId().equals(trustedSubjectId) || mayAdminRead)
    .switchIfEmpty(Mono.error(new AccessDeniedException("denied")));
```

This is a **non-standalone architectural snippet** illustrating how to query by real tenant/resource. In a complete application, distinguish genuinely missing resources from existing forbidden ones, prevent user enumeration, guard against race/TOCTOU issues, and enforce checks before side effects.

In multi-tenant systems, the same username `alice` in tenant A and tenant B is not the same principal. Use subject ID + tenant scope from a trusted source, not bare username strings. When policies need DB access, a SpEL bean returning `Mono<Boolean>` can delegate checks to a reactive repository instead of trying to call a blocking repository in the annotation.

## 13. Method security is not guaranteed to run if the proxy is bypassed

An anti-pattern:

```java
// Illustration, imports/package omitted.
@Service
public class UnsafeService {
    public Mono<String> outer(String owner) {
        return inner(owner); // self-invocation within the same instance
    }

    @PreAuthorize("#owner == authentication.name")
    public Mono<String> inner(@P("owner") String owner) {
        return Mono.just("sensitive");
    }
}
```

`outer` calling `this.inner` can bypass the Spring AOP proxy, leaving the annotation on `inner` unenforced. Fix using one of these approaches:

- Attach authorization directly to entrypoint method `outer` if that is the proper boundary.
- Move `inner` into another Spring bean and inject it so calls traverse the proxy.
- Extract Java policy logic and invoke it explicitly before sensitive operations if enforcement independent of AOP is needed.
- Write **negative tests**: unauthorized users must receive errors rather than only testing happy paths.

Never instantiate an annotated service with `new` and expect AOP to work. For reactive method security, check both the return type and the bean invocation path.

## 14. Common SpEL mistakes and fixes

| Symptom | Cause | Fix |
| --- | --- | --- |
| `#owner` does not receive value | Parameter name not exposed or typo | Use `@P("owner")`, `-parameters`, tests |
| Using `#user` in method with `owner` | Wrong variable name | Align annotation and parameter names |
| Using `#p0` after reordering args | Points to wrong argument | Use `@P` or update positional expression |
| `principal.username` fails with JWT | Principal lacks `getUsername()` | Use `authentication.name` or custom converter/policy |
| `authentication.name` differs from email | Name may come from JWT `sub`/ID | Standardize trusted subject key |
| `hasRole('ADMIN')` denies `ADMIN` authority | Expects `ROLE_ADMIN` by default | Grant proper prefix or use `hasAuthority('ADMIN')` |
| Admin still denied on owner-only | Rule has no role override | Check requirements; add OR branch only if intended |
| HTTP authenticated yet method returns 403 | HTTP only authenticates; method checks owner/permission | Distinguish the two layers |
| Method never denies | Method security not enabled or self-invocation | Enable config, call Spring proxy, write deny tests |
| Testing with `new InvoiceService()` | No AOP proxy | Use `@SpringBootTest` injected service |
| Imperative `SecurityContextHolder` in WebFlux | Context binds to subscriber, not fixed thread | Use `ReactiveSecurityContextHolder` |
| `@ownerPolicy` fails to resolve | Wrong bean name or component scan | Set `@Component("ownerPolicy")`, test |
| Bean returning `Mono<Boolean>` mishandled | Using legacy/unsupported method security mode | `useAuthorizationManager=true`, test exact version |
| SpEL calls `.block()` | Blocks event loop | Compose reactive pipeline |
| 403 on POST despite valid permissions | Likely CSRF | Test CSRF token and HTTP method |
| Comparing input `owner` to username still allows IDOR | Real owner of invoice ID unchecked | Query/authorize by resource and tenant |
| Using `@PostAuthorize` after side effects | Check runs after operation | Check permissions before reads/writes |
| Authentication leaked in logs | May contain credentials/tokens | Log only necessary signals; redact secrets |

### Recommended debugging sequence

1. Check which HTTP `SecurityWebFilterChain` matched; are credentials valid?
2. Verify `@EnableReactiveMethodSecurity(useAuthorizationManager = true)`.
3. Verify the method is called on a Spring bean through its proxy, not via self-invocation.
4. Confirm `Authentication.getName()` and actual principal type in a safe test environment.
5. Inspect expected method arguments in tests without printing raw passwords/tokens.
6. Check `@P` names, `#owner`, `#p0`, and parameter ordering.
7. Check actual authorities after converters/mappers, `ROLE_` prefixes, and scopes.
8. If needed, extract a policy bean and unit test owner/tenant/resource logic.
9. Inspect error signals with `StepVerifier` before blaming HTTP exception handlers.
10. Add negative tests to catch bypasses, especially self-invocation and manipulated owner URLs.

## 15. Self-check questions

**Question 1.** What does `authentication.name == #owner` compare?  
**Answer:** It compares the caller's name from the verified Authentication against the **method parameter value** exposed via `#owner`.

**Question 2.** Does `principal.username` work unchanged when switching from HTTP Basic UserDetails to JWT?  
**Answer:** Not necessarily. A JWT principal may lack `username`; check your converter or use `authentication.name` per identity policy.

**Question 3.** Why can `#owner` be null/unresolved even though the method declares `String owner`?  
**Answer:** Parameter names may not be discoverable from bytecode. Use `@P("owner")` or enable `-parameters`, and test on a real build.

**Question 4.** How does `#p0` differ from `#owner`?  
**Answer:** `#p0` uses the first parameter's position; `#owner` uses the name. Refactoring argument order can silently break `#p0`.

**Question 5.** Does `hasRole('ADMIN') or #owner == authentication.name` require an admin to also be the owner?  
**Answer:** No. OR allows either admin or owner. To require both, use AND if business rules demand it.

**Question 6.** If Alice calls `invoice("alice","id-of-bob")`, is comparing `owner` with username enough to prevent IDOR?  
**Answer:** No. The true owner of the invoice must be checked from the database by ID and tenant, never trusting client-supplied `owner`.

**Question 7.** What is required for `@PreAuthorize` to work on a WebFlux service?  
**Answer:** Reactive method security enabled, reactive method return type, Spring AOP-proxied bean, and invocation through the proxy within a subscription carrying valid Authentication.

**Question 8.** Why is `@WithMockUser` insufficient to verify HTTP Basic passwords?  
**Answer:** Mock users inject a pre-built Authentication, bypassing converters and password verifiers. Real Basic headers via `WebTestClient` are needed.

**Question 9.** Can `@ownerPolicy.canView(authentication,#owner)` return `Mono<Boolean>`?  
**Answer:** Yes, in AuthorizationManager-based reactive method security on supported versions; do not call `block()`.

**Question 10.** Why is the method not denied when calling `this.securedMethod()`?  
**Answer:** Self-invocation can bypass the Spring AOP proxy; protect the entrypoint or extract into another bean.

**Question 11.** Which package contains `@P`?  
**Answer:** `org.springframework.security.access.method.P`.

**Question 12.** Why can a valid login still receive HTTP 403?  
**Answer:** HTTP authentication succeeded, yet method or HTTP authorization denied access due to owner, authority, CSRF, or another policy.

**Question 13.** Should you call `SecurityContextHolder.getContext()` in a WebFlux request and store it in ThreadLocal?  
**Answer:** No. Reactive security uses Reactor Context and `ReactiveSecurityContextHolder` tied to the subscription.

**Question 14.** Does `@PostAuthorize` replace all pre-mutation authorization checks?  
**Answer:** No. For side effects, post-method checks happen too late; gate before writing data or calling external services.

## 16. Checklist and further reading

- [ ] Enabled `@EnableReactiveMethodSecurity` with the proper AuthorizationManager mechanism.
- [ ] Methods return `Mono`/`Flux` and are invoked through Spring beans/proxies.
- [ ] No ThreadLocal/imperative `SecurityContextHolder` used to infer reactive identity.
- [ ] Chose `authentication.name`/trusted identity key rather than assuming every principal has `username`.
- [ ] Used `@P` or `-parameters` for named expressions; tested positional `#p0`.
- [ ] Reviewed AND/OR rules against business requirements; `ROLE_` and authorities mapped cleanly.
- [ ] Added negative tests for owner mismatch, missing authority, and admin blocked from owner-only rules.
- [ ] For SpEL beans, avoided blocking I/O and tested policies independently.
- [ ] Invoice owner/tenant verified from storage by ID, not from self-declared path params.
- [ ] HTTP 401 and method 403 tested separately with `WebTestClient`.
- [ ] `StepVerifier` confirms isolated Context across subscriptions.
- [ ] No self-invocation or `new` constructors bypassing AOP.
- [ ] Accounted for CSRF on browser POSTs and enforced authorization before side effects.
- [ ] Never log credentials, JWTs, raw SecurityContext, or sensitive data.

**Summary:** In reactive Spring Security, `authentication` is the framework-provided identity; `principal` is the object inside Authentication whose type depends on the authentication mechanism; `#owner`/`#p0` are merely **method parameter values**. `@PreAuthorize` lets you combine these into clear policies, yet **does not by itself prove real resource ownership**. Safety requires method security, proper Reactor Context, proxies, negative tests, and trusted owner/tenant queries.

**Official documentation:**

- Spring Security 6.5 – EnableReactiveMethodSecurity: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html
- Spring Security 6.5 – Reactive Web Security: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security 6.5 – Method Security Expressions and Parameters: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 6.5 – `@PreAuthorize`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/prepost/PreAuthorize.html
- Spring Security 6.5 – `@P` annotation: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/method/P.html
- Spring Security 6.5 – ReactiveSecurityContextHolder: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html
- Spring Security 6.5 – Testing reactive method security: https://docs.spring.io/spring-security/reference/6.5/reactive/test/method.html
- Spring Security 6.5 – WebTestClient test setup: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html
- OWASP API Security – Broken Object Level Authorization: https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/
- Spring Boot 3.5.16 release and end of OSS support: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/
