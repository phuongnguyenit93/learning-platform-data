# AuthorizationManagerFactory and Customization in Supported Versions

## 1. Purpose and Version Scope

In Spring Security, `AuthorizationManager<T>` is the component that decides **GRANT/DENY** for a protected action, such as an HTTP request or a Java method invocation. `AuthorizationManagerFactory<T>` is the abstraction that **creates common AuthorizationManagers** when the system builds policies: `hasRole("ADMIN")`, `hasAuthority("document:read")`, `authenticated()`, `permitAll()`, and their variants.

**Critical version requirement:** the `org.springframework.security.authorization.AuthorizationManagerFactory` API and its `DefaultAuthorizationManagerFactory` implementation were introduced in **Spring Security 7.0** (the Javadoc states `Since: 7.0`). Spring Security 6.x projects still have `AuthorizationManager` and many other extension points, yet do not include this factory; never copy 7.x examples into a 6.x branch expecting them to compile.

This content targets Spring Security 7.0+ applications using HTTP Servlet and method security, while also explaining how to handle unsupported branches. Objectives:

1. Distinguish the factory that **creates managers** from the manager that **evaluates permissions**.
2. Understand factory methods and the role of generic type `T`.
3. Customize role prefixes, role hierarchy, trust resolvers, and additional requirements.
4. Distinguish shared generic factories from factories typed specifically for web or method security.
5. Recognize the risks of broad policy changes and how to test them.
6. Know when to use custom managers, `.access(...)`, or policy beans instead of a factory.

## 2. Factories Create Policies; Managers Make Decisions

In modern Spring Security, `AuthorizationManager<T>` has the conceptual contract:

```java
AuthorizationResult authorize(
    Supplier<? extends Authentication> authentication,
    T securedObject
);
```

This is a simplified signature for explanation. The real API may carry additional wildcards and nullability annotations depending on the patch version. `authentication` supplies the caller when needed; `securedObject` describes the object under check. The manager returns an allow/deny decision, or may abstain by returning `null` per the API contract.

Conversely, the factory's purpose is:

```java
AuthorizationManager<T> hasRole(String role);
AuthorizationManager<T> authenticated();
AuthorizationManager<T> permitAll();
```

The methods above are examples from the `AuthorizationManagerFactory<T>` contract: each call **produces a manager** with the corresponding rule.

```text
Configuration phase:
  .requestMatchers("/reports/**").hasRole("READER")
                         |
                         v
         AuthorizationManagerFactory<T>
             .hasRole("READER")
                         |
                         v
            AuthorizationManager<T>

When a request arrives:
  Supplier<Authentication> + request context
                         |
                         v
         AuthorizationManager.authorize(...)
                         |
                         v
                    GRANT / DENY
```

This separates two phases. A factory does not log users in itself, verify passwords, act as an `AuthenticationManager`, or check document ownership on its own. Per-resource access still requires dedicated policies and trusted data.

## 3. Common Methods of AuthorizationManagerFactory

| Method | The created manager will require |
| --- | --- |
| `permitAll()` | Allow everyone, without needing to read Authentication |
| `denyAll()` | Deny everyone |
| `anonymous()` | Only anonymous callers |
| `authenticated()` | Caller is authenticated per trust resolver |
| `fullyAuthenticated()` | Fully authenticated, not merely remember-me |
| `rememberMe()` | Remember-me authentication state |
| `hasRole("USER")` | Role USER; by default checks authority `ROLE_USER` |
| `hasAnyRole("USER", "ADMIN")` | Has at least one listed role |
| `hasAllRoles("READER", "AUDITOR")` | Has all listed roles |
| `hasAuthority("document:read")` | Exact authority `document:read` |
| `hasAnyAuthority("x", "y")` | Has at least one authority |
| `hasAllAuthorities("x", "y")` | Has all authorities |

**Roles and authorities are not synonymous.** `hasRole("ADMIN")` defaults to requiring `ROLE_ADMIN`, whereas `hasAuthority("ADMIN")` requires the exact string `ADMIN`. Calling `setRolePrefix("APP_")` affects rules created by `hasRole`, without turning `hasAuthority("document:read")` into a role.

Starting in 7.0, the factory interface provides **default implementations** for its methods; custom factories can override just the specific behaviors needed. However, overriding one method does **not automatically apply the same extension to other methods**: to keep rules consistent, configure explicitly, use delegation or role hierarchy, and write tests.

## 4. Type T Defines the Authorization Context

`AuthorizationManagerFactory<T>` is generic over the checked target type:

- `AuthorizationManagerFactory<RequestAuthorizationContext>` targets managers deciding on Servlet web authorization requests.
- `AuthorizationManagerFactory<MethodInvocation>` targets Java method invocations intercepted by Spring AOP.
- A generic bean declared as `<T> AuthorizationManagerFactory<T>` can serve framework components supporting a shared factory.

`RequestAuthorizationContext` supplies the request and matcher variables; `MethodInvocation` supplies the method and arguments. The factory itself does not inspect them; it creates the appropriate `AuthorizationManager<T>`.

```java
AuthorizationManager<RequestAuthorizationContext> webRule =
    webFactory.hasRole("ADMIN");

AuthorizationManager<MethodInvocation> methodRule =
    methodFactory.hasRole("ADMIN");
```

These are **two illustrative application snippets** with `webFactory`/`methodFactory` already injected. Both rules share the same role name yet take different input types. Never force a `MethodInvocation` manager into an HTTP manager by casting; if you need shared business logic, share a policy bean that decides from `Authentication` and server data.

## 5. DefaultAuthorizationManagerFactory and Shared Configuration

Spring Security 7.x provides `DefaultAuthorizationManagerFactory<T>`. Main configuration hooks:

- `setRolePrefix(String)` — adjusts how roles are converted into authorities.
- `setRoleHierarchy(RoleHierarchy)` — applies role inheritance relationships.
- `setTrustResolver(AuthenticationTrustResolver)` — adjusts how anonymous, remember-me, and fully authenticated states are evaluated.
- `setAdditionalAuthorization(AuthorizationManager<T>)` — adds an extra authorization condition to certain rule types produced by the factory.

Example creating a shared factory with a non-default prefix:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationManagerFactory;
import org.springframework.security.authorization.DefaultAuthorizationManagerFactory;

@Configuration
public class AuthorizationFactoryConfiguration {

    @Bean
    public <T> AuthorizationManagerFactory<T> authorizationManagerFactory() {
        DefaultAuthorizationManagerFactory<T> factory =
            new DefaultAuthorizationManagerFactory<>();
        factory.setRolePrefix("APP_");
        return factory;
    }
}
```

This is **Spring Security 7.x configuration**, registered as a Spring bean. Suppose a principal has authority `APP_ADMIN`: a `hasRole("ADMIN")` rule going through this factory will allow it, while a principal with only `ROLE_ADMIN` will not match the `APP_` prefix.

**Do not change the prefix merely to silence an HTTP 403.** Inspect `GrantedAuthority` values from the authentication system, JWT converter/LDAP/database setup, role hierarchy, Spring Security expressions, and other factories. An application may use `GrantedAuthorityDefaults` or another role-prefix mechanism; keep authority mapping consistent.

### Configuring RoleHierarchy

If the project already exposes a `RoleHierarchy` bean, you can pass it into the default factory:

```java
@Bean
public <T> AuthorizationManagerFactory<T> authorizationManagerFactory(
        RoleHierarchy hierarchy) {
    DefaultAuthorizationManagerFactory<T> factory =
        new DefaultAuthorizationManagerFactory<>();
    factory.setRoleHierarchy(hierarchy);
    return factory;
}
```

This snippet **replaces** the previous example bean method; do not declare two generic beans with the same name simultaneously. Import `RoleHierarchy` from `org.springframework.security.access.hierarchicalroles.RoleHierarchy` and provide the project's actual hierarchy bean.

Example semantics of a role hierarchy:

```text
ROLE_ADMIN > ROLE_EDITOR
ROLE_EDITOR > ROLE_READER
```

ADMIN can inherit READER's permissions under a properly configured hierarchy. This ordering expresses role inheritance notation, not interceptor execution order. Test both transitive inheritance paths and individual role permissions; a role hierarchy never proves a user shares a tenant or owns a resource.

## 6. Specialized Factory for HTTP Requests

Suppose a system requires endpoints using `authenticated()` to **both be logged in and hold role USER**. A specialized factory for `RequestAuthorizationContext`:

```java
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationManagerFactory;
import org.springframework.security.authorization.AuthorizationManagers;
import org.springframework.security.authorization.DefaultAuthorizationManagerFactory;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
import org.springframework.stereotype.Component;

@Component
public class WebAuthorizationManagerFactory
        implements AuthorizationManagerFactory<RequestAuthorizationContext> {

    private final AuthorizationManagerFactory<RequestAuthorizationContext>
        delegate = new DefaultAuthorizationManagerFactory<>();

    @Override
    public AuthorizationManager<RequestAuthorizationContext> authenticated() {
        return AuthorizationManagers.allOf(
            this.delegate.authenticated(),
            this.delegate.hasRole("USER")
        );
    }
}
```

`AuthorizationManagers.allOf(...)` requires all components to allow. An authenticated user holding only `ROLE_GUEST` will be denied by managers created from `authenticated()`. A user holding role USER without being authenticated also fails to satisfy both.

HTTP configuration using standard rules:

```java
@Bean
SecurityFilterChain web(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/public/**").permitAll()
        .requestMatchers("/reports/**").authenticated()
        .anyRequest().denyAll()
    );
    return http.build();
}
```

This is only a **configuration fragment**, requiring imports for `HttpSecurity`, `SecurityFilterChain`, `Bean`, and proper authentication setup. When Spring Security 7.x uses the typed factory above, `authenticated()` for `/reports/**` includes the additional USER condition.

**Override scope must be read accurately:**

- `permitAll()` is not turned into "must have USER."
- `hasRole("ADMIN")` on another route is unaffected by overriding `authenticated()`.
- `.access(customManager)` takes an existing manager, not necessarily produced by the factory.
- Multiple `SecurityFilterChain`s have separate matching rules; verify which chain actually runs.
- A `hasAuthority("document:read")` rule does not automatically require USER if only `authenticated()` was overridden.

If only one URL requires both `ROLE_USER` and authentication, putting that condition on that route alone is simpler and less impactful than altering `authenticated()` everywhere.

## 7. Specialized Factory for Method Security

When using `@EnableMethodSecurity`, Spring Security 7.x can use a typed `AuthorizationManagerFactory<MethodInvocation>` to construct managers for method annotation expressions.

Suppose you want `ROLE_ADMIN` to **substitute for any ordinary role** when methods use `hasRole` or `hasAnyRole`:

```java
import org.aopalliance.intercept.MethodInvocation;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationManagerFactory;
import org.springframework.security.authorization.AuthorizationManagers;
import org.springframework.security.authorization.DefaultAuthorizationManagerFactory;
import org.springframework.stereotype.Component;

@Component
public class MethodAuthorizationManagerFactory
        implements AuthorizationManagerFactory<MethodInvocation> {

    private final AuthorizationManagerFactory<MethodInvocation> delegate =
        new DefaultAuthorizationManagerFactory<>();

    @Override
    public AuthorizationManager<MethodInvocation> hasRole(String role) {
        return AuthorizationManagers.anyOf(
            this.delegate.hasRole(role),
            this.delegate.hasRole("ADMIN")
        );
    }

    @Override
    public AuthorizationManager<MethodInvocation>
            hasAnyRole(String... roles) {
        return AuthorizationManagers.anyOf(
            this.delegate.hasAnyRole(roles),
            this.delegate.hasRole("ADMIN")
        );
    }
}
```

`AuthorizationManagers.anyOf(...)` allows if **at least one** branch allows. With managers created by this factory from `hasRole("READER")`, a principal with `ROLE_ADMIN` is permitted even without `ROLE_READER`.

Illustrative service:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    @PreAuthorize("hasRole('READER')")
    public String listReports() {
        return "reports";
    }
}
```

Enable method security in Spring configuration:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
```

All of these are **application components**. Calling `listReports()` must go through a Spring proxy for method security advice to run in proxy mode. Calling `new ReportService()` directly in a unit test does not test the factory's real effect.

**Limitation:** the example overrides `hasRole` and `hasAnyRole`, without automatically overriding `hasAllRoles`, `hasAuthority`, `hasAnyAuthority`, or other rules. If the goal is consistent role inheritance for ADMIN, consider `RoleHierarchy`. Never assume a factory lets ADMIN bypass all owner, tenant, or ACL constraints; per-resource permissions must still be verified separately.

## 8. Generic vs. Typed Configuration: Which Path to Choose?

| Option | Meaning | When it fits |
| --- | --- | --- |
| `@Bean <T> AuthorizationManagerFactory<T>` | Publishes one shared factory for supporting integrations | Changing global conventions such as prefix/hierarchy |
| `AuthorizationManagerFactory<RequestAuthorizationContext>` | Bound to Servlet web request authorization | Overriding rules produced by `authorizeHttpRequests` |
| `AuthorizationManagerFactory<MethodInvocation>` | Bound to method security | Overriding manager creation for method annotations |
| `AuthorizationManager<RequestAuthorizationContext>` passed to `.access(...)` | Selects a specific policy at one request matcher | Requires URL, HTTP method, path variables, or resources |
| `@PreAuthorize("@policy.canRead(authentication, #id)")` | Java policy for a service method | Per-user, tenant, document, or ACL permissions |
| `RoleHierarchy` | Role inheritance model | More consistent role inheritance than scattered OR branches |

When both typed and generic beans exist, verify **which factory Spring Security actually picks** at each site. Spring bean resolution can depend on generic declarations, target type, and version; never rely solely on bean names. Having a custom factory in the context does not prove every manager uses it.

Never use a factory solely to inject a request's owner ID or tenant into decisions. HTTP paths and method arguments are **forgeable data**. Policies must read owner/tenant/ACL from verified server sources and constrain data queries properly.

## 9. setAdditionalAuthorization and Additional Authentication Requirements

Starting in 7.x, `DefaultAuthorizationManagerFactory.setAdditionalAuthorization(AuthorizationManager<T>)` can append an authorization requirement to managers created by:

- `hasRole`, `hasAnyRole`, `hasAllRoles`;
- `hasAuthority`, `hasAnyAuthority`, `hasAllAuthorities`;
- `authenticated`, `fullyAuthenticated`, `rememberMe`.

The additional condition is required **alongside** the base rule. For example, a manager from `hasRole("READER")` can also require passing a trusted MFA check.

**Important API exception:** per the default factory's Javadoc, `setAdditionalAuthorization` **does not apply** to `anonymous()`, `permitAll()`, or `denyAll()`. Never claim "enabling additional authorization means every endpoint requires MFA." Audit login, enrollment, recovery, and anonymous routes carefully.

Illustration attaching an existing manager:

```java
DefaultAuthorizationManagerFactory<RequestAuthorizationContext> factory =
    new DefaultAuthorizationManagerFactory<>();

AuthorizationManager<RequestAuthorizationContext> mfaManager =
    /* MFA policy already verified by the system from Authentication */;

factory.setAdditionalAuthorization(mfaManager);
```

This is **Java pseudocode showing how to wire it**; `mfaManager` must be supplied by the application—never copy the comment verbatim as an initializer. On Spring Security versions with built-in MFA support, read the docs on `AuthorizationManagerFactories.multiFactor()` and `FactorGrantedAuthority` before implementing. Never accept a self-asserted "MFA complete" header as proof.

When **only one endpoint** needs MFA, create a dedicated manager for that endpoint instead of applying an additional manager across the entire shared factory.

## 10. AuthenticationTrustResolver and Authentication States

`setTrustResolver(...)` adjusts how managers created by the factory interpret anonymous, remember-me, and full authentication. These states govern `authenticated()`, `fullyAuthenticated()`, `rememberMe()`, and `anonymous()`.

Never use `authentication.isAuthenticated()` alone to replace the entire trust resolver. An anonymous token in Spring Security can report `isAuthenticated() == true` in the core API, yet the trust resolver recognizes it as anonymous rather than a fully logged-in user.

If replacing the trust resolver with a custom one, test:

- Anonymous requests.
- Normal session logins.
- Remember-me sessions.
- Authenticated JWT/OAuth2 requests, if used by the application.
- Application-specific auth tokens.

Unless there is a specialized need, keeping the default trust resolver reduces the risk of altering familiar rule semantics.

## 11. Standalone Java 17 Demo: A Rule Factory

The following program is a **plain Java model** requiring no Spring Security. It shows a standard role-rule factory and a custom factory adding an ADMIN branch.

Create `AuthorizationManagerFactoryDemo.java`:

```java
import java.util.Set;

public class AuthorizationManagerFactoryDemo {
    record Actor(String username, Set<String> authorities) {}

    @FunctionalInterface
    interface Rule {
        boolean allows(Actor actor);
    }

    interface RuleFactory {
        Rule hasRole(String role);
    }

    static final class DefaultFactory implements RuleFactory {
        private final String prefix;

        DefaultFactory(String prefix) {
            this.prefix = prefix;
        }

        @Override
        public Rule hasRole(String role) {
            String required = this.prefix + role;
            return actor -> actor != null
                && actor.authorities().contains(required);
        }
    }

    static final class AdminAwareFactory implements RuleFactory {
        private final RuleFactory delegate;

        AdminAwareFactory(RuleFactory delegate) {
            this.delegate = delegate;
        }

        @Override
        public Rule hasRole(String role) {
            Rule base = this.delegate.hasRole(role);
            Rule admin = this.delegate.hasRole("ADMIN");
            return actor -> base.allows(actor) || admin.allows(actor);
        }
    }

    public static void main(String[] args) {
        RuleFactory standard = new DefaultFactory("ROLE_");
        RuleFactory extended = new AdminAwareFactory(standard);

        Rule normalReader = standard.hasRole("READER");
        Rule readerOrAdmin = extended.hasRole("READER");

        Actor reader = new Actor("reader", Set.of("ROLE_READER"));
        Actor admin = new Actor("admin", Set.of("ROLE_ADMIN"));
        Actor guest = new Actor("guest", Set.of());

        System.out.println("Reader default: "
            + normalReader.allows(reader));
        System.out.println("Admin default: "
            + normalReader.allows(admin));
        System.out.println("Admin custom: "
            + readerOrAdmin.allows(admin));
        System.out.println("Guest custom: "
            + readerOrAdmin.allows(guest));
        System.out.println("No identity: "
            + readerOrAdmin.allows(null));
    }
}
```

Compile and run on JDK 17+:

```bash
javac AuthorizationManagerFactoryDemo.java
java AuthorizationManagerFactoryDemo
```

Exact stdout:

```text
Reader default: true
Admin default: false
Admin custom: true
Guest custom: false
No identity: false
```

The factory builds a `Rule` once, then the same rule evaluates multiple Actors. For ADMIN, the default READER rule returns false, whereas the custom rule adding the ADMIN branch returns true. This example only models **the separation between policy creation and policy evaluation**; it does not run SpEL, Spring AOP, HTTP, or Spring Security's real anonymous handling.

## 12. Version Boundaries and Compatibility Paths

| Spring Security line | `AuthorizationManagerFactory` status | How to proceed |
| --- | --- | --- |
| 6.x | API not provided (`Since: 7.0`) | Use `AuthorizationManager<T>`, `.access(...)`, `@PreAuthorize`, policy beans, role hierarchy, and 6.x extension points |
| 7.0 and later | Factory and default factory available | Can register generic or typed factories; verify API per patch |
| Newer 7.x releases | May add helpers or refine integrations | Check Javadoc/changelog and run integration tests before upgrading |

Determine the **actually resolved version**, not merely the Spring Security version guessed from Spring Boot. With Maven, run `mvn dependency:tree` and inspect `spring-security-core` and `spring-security-config`; with Gradle, run `./gradlew dependencyInsight` or `dependencies` on the runtime configuration. When using the Spring Boot BOM, keep all Spring Security modules aligned.

When code reports `AuthorizationManagerFactory` cannot be found:

1. Check whether the resolved dependency is Spring Security 6.x or 7.x.
2. If 6.x, never create a fake class inside a Spring package to mimic the new API.
3. Use custom `AuthorizationManager`s at existing extension points, or plan a coordinated upgrade following the migration guide.
4. Never mix a lone Security 7.x artifact into a 6.x dependency graph.

### Alternative in 6.x: Custom Manager at the Right Point

If you only need an admin check on a group of URLs, built-in policies are usually enough:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
);
```

For complex logic, use `.access(...)` with a concrete `AuthorizationManager<RequestAuthorizationContext>` or `@PreAuthorize("@policy.canRead(authentication, #id)")` on services. Both approaches remain useful in 7.x; a custom factory is not required in every case.

## 13. Testing Semantics and Blast Radius

A factory can compile cleanly yet **not be picked by the framework**, or alter the meaning of far more rules than intended. Test at two levels.

### Factory Unit Tests

On 7.x, invoke the factory methods and pass test `Authentication` objects to the returned managers. At minimum:

1. `hasRole("READER")` with `ROLE_READER` → allow.
2. `hasRole("READER")` with `ROLE_ADMIN` → allow only in the custom factory that added the ADMIN branch.
3. Missing both READER and ADMIN → deny.
4. Anonymous or missing Authentication → never self-elevate.
5. `hasAuthority("report:read")` unaffected by role-only overrides.
6. Does `hasAllRoles(...)` preserve requiring all roles?
7. Does an `APP_` prefix match actually granted authorities?
8. Does `setAdditionalAuthorization` apply to the Javadoc-listed methods and **not** to `permitAll`/`denyAll`/`anonymous`?

In tests, use Spring Security test-supported `Authentication`/authority constructs rather than mocking every auth state with a plain boolean.

### HTTP Integration Tests

Use `MockMvc` or real servlet tests to verify routes and chains actually match.

| Principal / URL | Rule | Expected with example web factory |
| --- | --- | --- |
| Anonymous /public/info | `permitAll()` | Allow |
| Logged in with `ROLE_USER` /reports | `authenticated()` augmented with USER | Allow |
| Logged in with only `ROLE_GUEST` /reports | `authenticated()` augmented with USER | Deny |
| Logged in with only `ROLE_ADMIN` /reports | Lacks USER; example does not auto-relax roles | Deny |
| Anyone /unknown | `denyAll()` | Deny |

HTTP 401 vs. 403 depends on the application's authentication entry point and exception handling; verify both response status and that unauthorized business methods are never invoked.

### Method Integration Tests

Enable `@EnableMethodSecurity`, register the typed factory, obtain `ReportService` from the Spring context, and call `listReports()`. With `@WithMockUser(roles = "ADMIN")`, the example custom method factory must allow `@PreAuthorize("hasRole('READER')")`; users lacking both roles must be denied.

Tests must go through a **Spring proxy**; calling `this.listReports()` inside the same bean can bypass interceptors in proxy mode. If the service has `@Transactional`, test transactions and side effects separately; a factory does not resolve advice ordering on its own.

When using both generic and typed factories, test web and method boundaries independently. Inspect bean wiring to confirm which factory the framework actually uses rather than testing direct factory calls alone.

## 14. Common Mistakes and How to Fix Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Copying 7.x factory APIs into a 6.x app | Missing classes/methods | Check version and use supported APIs |
| Confusing a factory with a per-request manager | Runtime/DB logic placed in the wrong component | Factory builds managers; managers authorize requests/methods |
| Overriding `authenticated()` expecting all rules to add USER | Only one rule subset changes | Identify exact factory methods being overridden |
| Overriding `hasRole` while skipping `hasAnyRole`/`hasAllRoles` | Inconsistent role policy | Use `RoleHierarchy` or override and test all needed branches |
| Changing role prefix inconsistently with Authentication data | Unexpected access denials | Align authority mapping and write negative tests |
| Assuming ADMIN automatically bypasses tenant/owner checks | Cross-tenant data leaks | Keep separate owner/tenant/ACL checks backed by trusted server data |
| Registering a web factory expecting method security to change | Wrong generic context | Register the right typed factory and test each integration |
| Assuming `setAdditionalAuthorization` affects `permitAll` | Flawed MFA assumptions, possible gaps | Read the API exception list and test authentication flows |
| Using `.access(customManager)` expecting the factory to alter it | Rule bypasses the factory | Build/compose the manager directly at `.access(...)` |
| Using a request parameter to let clients pick the required role | Broken authorization logic even without SpEL injection | Fix policies server-side; only take resource IDs as inputs |
| Unit-testing only the factory without testing SecurityFilterChain/AOP | Bean unused or proxy bypassed | Write integration tests over real call paths |
| Registering overlapping factory beans without checking | Unclear which factory is selected | Keep configuration deliberate; verify bean selection and final outcomes |

## 15. Pre-Adoption Checklist

- **API version:** is Spring Security 7.0+ actually resolved, with all Security dependencies aligned?
- **Goal:** do you need a convention for creating standard rules, or just a custom manager for one route/method?
- **Context:** generic factory, `RequestAuthorizationContext`, or `MethodInvocation`?
- **Override scope:** exact methods (`authenticated`, `hasRole`, `hasAnyRole`, etc.)?
- **Authority source:** are role prefixes and role hierarchies consistent with Authentication?
- **Exceptions:** have `permitAll`, `denyAll`, `anonymous`, and `.access(...)` been tested separately?
- **MFA:** where does additional authorization apply, and does it break enrollment/recovery?
- **Resources:** are owner/tenant/ACL verified from database/trusted services instead of client inputs?
- **Side effects:** do transactions, caching, async, or self-invocation affect the check path?
- **Proof:** do both unit and integration tests prove the factory is used and decides accurately on both GRANT and DENY?

**Key takeaway:** `AuthorizationManagerFactory<T>` is available starting in Spring Security **7.0+** and lets you standardize how **AuthorizationManagers are created**; it does not replace a business authorization policy. Customizing a factory can have broad blast radius. Keep scope controlled, rely on trusted authorization data, and test real rules after configuration.

## Official References

- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): factory concepts and shared configuration beans.
- [Javadoc — AuthorizationManagerFactory](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/AuthorizationManagerFactory.html): contract and `Since: 7.0`.
- [Javadoc — DefaultAuthorizationManagerFactory](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/DefaultAuthorizationManagerFactory.html): configuring role prefix/hierarchy/trust resolver/additional authorization.
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): custom factory example for request authorization.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): custom factory example for `MethodInvocation`.
- [Spring Security — Multi-Factor Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/mfa.html): additional authentication factors and MFA factories.
