# PathPatternRequestMatcher, MvcRequestMatcher, and AntPathRequestMatcher Across Versions

> **Topic:** Spring Security - authorization  
> **Knowledge group:** RequestMatcher  
> **Goal:** Distinguish the three HTTP request matching strategies in Spring Security Servlet, understand why examples in versions 5.x, 6.x, and 7.x have different APIs, know how to choose the right matcher for Spring MVC or custom-servlet applications, and migrate from legacy matchers to `PathPatternRequestMatcher` **without accidentally leaving paths unprotected**.

## 1. The Real-World Problem: Same URL, Different Matchers Can Yield Different Results

Suppose an application has an HTTP endpoint:

```http
GET /portal/mvc/reports/42
Authorization: Bearer <token>
```

Suppose:
- `/portal` is the **context path** where the application is deployed.
- `/mvc` is the **servlet path** of `DispatcherServlet`.
- `/reports/42` is the path the controller receives.

The application wants to enforce `hasAuthority("reports:read")`. An older project might use `MvcRequestMatcher` with pattern `/reports/**` and servlet path `/mvc`; a Spring Security 7 project using `PathPatternRequestMatcher` needs to describe the URL **without the context path**, i.e., `/mvc/reports/**`, or use a builder with `basePath("/mvc")`.

If `/reports/**` is accidentally kept without configuring the servlet prefix, the rule may **fail to match**. With a fallback that only requires authentication, the request can pass HTTP authorization without needing `reports:read`. With multiple `SecurityFilterChain`s, even worse: selecting the wrong chain can cause the entire intended authentication/authorization filter set **not to participate**.

That is why this lesson treats matchers not as "wildcard syntax", but as **part of the security boundary**.

## 2. What Does RequestMatcher Do and Not Do?

In Spring Security Servlet, `org.springframework.security.web.util.matcher.RequestMatcher` is a strategy interface used to determine whether an `HttpServletRequest` matches a condition.

```java
// Minimal conceptual interface signature:
boolean matches(HttpServletRequest request);
```

Some implementations also support `matcher(request)` returning a `MatchResult` to pass variables extracted from the path. That information is usable during the authorization step, but should not be conflated with loading business entities from the database.

Two typical places that consume matchers:

1. **Selecting a filter chain:** `http.securityMatcher(...)` creates a matcher determining whether a request belongs to that `SecurityFilterChain`.
2. **Selecting an HTTP rule:** `authorizeHttpRequests(...requestMatchers(...))` uses a matcher to select an `AuthorizationManager` for the request inside the chosen chain.

```text
HTTP request
    |
    v
FilterChainProxy
    | selects the FIRST SecurityFilterChain matching securityMatcher
    v
SecurityFilterChain
    | authentication, CSRF, security filters ...
    v
AuthorizationFilter
    | selects the FIRST rule matching requestMatcher
    v
AuthorizationManager
    | role, authority, or other policy
    v
ALLOW / DENY
```

**Distinguish clearly:** the matcher answers "is this request in this set of paths/methods?", while the manager answers "does this identity have permission for that request?". A matching matcher does not mean ALLOW; a non-matching matcher does not mean DENY if another fallback rule exists.

The scope of this lesson is **Spring Security Servlet**, not WebFlux's `ServerWebExchangeMatcher`. Do not copy Servlet types into Reactive Security.

## 3. Comparison Table of the Three Matchers

| Aspect | `AntPathRequestMatcher` | `MvcRequestMatcher` | `PathPatternRequestMatcher` |
| --- | --- | --- | --- |
| Purpose | Ant-style URL matching | Matching aligned with how Spring MVC resolves controller mappings | Matching using `PathPattern`/`PathPatternParser` |
| Underlying engine | Ant path matching | Spring MVC's `HandlerMappingIntrospector` | `PathPatternParser` |
| Depends on MVC to work? | Not required | Yes, uses MVC infrastructure | Does not need `HandlerMappingIntrospector` for regular matching |
| Must know servlet path? | Depends on which URL the matcher reads and configuration | Must be configured when using a non-default servlet path | Uses full application path (excluding context root) or `Builder.basePath` |
| Supports HTTP method? | Yes | Yes | Yes |
| Supports path variables? | Yes via corresponding matcher/variable extraction utilities | Yes, per MVC mapping | Yes, via `PathPattern` and `MatchResult` |
| Status in 6.5 | Still present; deprecated for removal | Still present; deprecated for removal | Available, recommended migration target |
| Status in 7.x | No longer supported | No longer supported | Default path matcher and primary integration approach |
| When seen in code | Legacy compatibility, usually needs migration | Legacy MVC integration, must migrate | Modern choice in 6.5+ |

**Version accuracy matters more than memorizing class names.** A snippet using `AntPathRequestMatcher` may fit a Spring Security 5.x/6.4 branch, but should not be copied to 7.x. In 6.5, although legacy classes still appear in the API, they are marked for removal. This is not merely a style warning: a major upgrade can cause compile errors or broken rules if matchers are replaced with strings without checking real URLs.

## 4. Upgrade Timeline

| Version line | What to know about matchers | Appropriate action |
| --- | --- | --- |
| Spring Security 5.x and many 6.0–6.4 apps | Older docs and code commonly use `AntPathRequestMatcher`, `MvcRequestMatcher`, and DSL APIs that auto-select matchers based on MVC/classpath environment | When maintaining an older branch, check the exact version and actual matcher behavior; avoid guessing |
| Spring Security **6.5** | Adds `PathPatternRequestMatcher` (Javadoc notes `Since: 6.5`); `AntPathRequestMatcher` and `MvcRequestMatcher` are marked `@Deprecated(forRemoval = true)` | Start using `PathPatternRequestMatcher` explicitly, add tests for context/servlet paths |
| Spring Security **7.0+** | Legacy Ant/MVC matchers are no longer supported; `PathPatternRequestMatcher` is used by default for path matching in the Java DSL | Replace legacy APIs, convert patterns to absolute paths starting with `/` and **excluding context root**, accounting for servlet prefix |
| Upgrades between patch releases | May include bug fixes on how servlet path and matcher builder are resolved | Read release notes/security advisories, run regression tests on the target patch version |

"Version-dependent" here does not mean every project on the same major version has the exact same default matcher. In 6.x, DSL overloads, an application-registered `PathPatternRequestMatcher.Builder` bean, the MVC classpath, and configuration choices all affect which implementation is created. **To avoid surprises, pass an explicit `RequestMatcher` when path behavior is a critical security boundary.**

Key reference sources:
- Official guide **Spring Security 6.5 → 7, Web Migrations**: `https://docs.spring.io/spring-security/reference/6.5/migration-7/web.html`.
- Javadoc `PathPatternRequestMatcher` 6.5/7.0: `https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/web/servlet/util/matcher/PathPatternRequestMatcher.html`.
- Javadoc for legacy matchers in the 6.5 branch to cross-check deprecation.

## 5. AntPathRequestMatcher: Ant-Style URL Matching in Legacy Code

A legacy configuration might write:

```java
import static org.springframework.security.web.util.matcher
    .AntPathRequestMatcher.antMatcher;

// Snippet for Spring Security 6.x branches that still have this class;
// DO NOT use for Spring Security 7.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(antMatcher("/api/admin/**")).hasRole("ADMIN")
    .requestMatchers(antMatcher("/api/reports/**")).hasAuthority("reports:read")
    .anyRequest().denyAll()
);
```

In Java, a static import should be written on a single line in a real file:

```java
import static org.springframework.security.web.util.matcher.AntPathRequestMatcher.antMatcher;
```

**Mechanism:** `AntPathRequestMatcher` matches Ant-style patterns against the URL based on `servletPath + pathInfo` (or a configured path helper). The query string is not part of the matched path. It can restrict the HTTP method; a `/**` pattern can act as a universal match.

Conceptual examples of Ant patterns:
- `/admin/**`: admin subtree.
- `/api/users/*`: single child segment under Ant wildcards.
- `/assets/*.css`: pattern for CSS files; verify actual paths and configuration.
- `/api/users/{name}`: a single segment variable, when the matcher supports extracting variables.
- Some mid-path `**` patterns may have been accepted by Ant, but **that does not mean** they can be copied verbatim to `PathPatternParser` across all versions.

Older documentation may contain:

```java
// Restrict GET method on legacy matcher.
new AntPathRequestMatcher("/api/reports/**", "GET");
```

**Key point:** when migrating to PathPattern, do not merely swap the class name and keep every pattern assumption. With Ant, many wildcards/details split on the path string; with PathPattern, paths are parsed structurally by segment and the parser has its own rules.

### Can AntPathRequestMatcher Still Be Used in 6.5?

Yes, in the 6.5 branch the API still exists, but it is marked deprecated for removal with a recommendation to migrate to `PathPatternRequestMatcher`. Therefore:
- Maintaining a 6.5 branch short-term may continue running legacy code if thoroughly tested.
- Do not design new code depending on an API scheduled for removal if you are preparing to upgrade to 7.x.
- Do not enable "suppress deprecation warnings" and treat migration as done.
- If third-party libraries create Ant matchers internally, check library versions and compatibility with Security 7.

## 6. MvcRequestMatcher: Using Spring MVC HandlerMappingIntrospector

A legacy Spring MVC snippet:

```java
import org.springframework.web.servlet.handler.HandlerMappingIntrospector;
import org.springframework.security.web.servlet.util.matcher.MvcRequestMatcher;

// Illustrative only for 6.x branches that still provide MvcRequestMatcher.
MvcRequestMatcher.Builder mvc =
    new MvcRequestMatcher.Builder(handlerMappingIntrospector);

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(mvc.pattern("/reports/**"))
        .hasAuthority("reports:read")
    .anyRequest().denyAll()
);
```

`handlerMappingIntrospector` is Spring MVC's `HandlerMappingIntrospector` bean that the configuration needs. A common pattern is injecting this bean into the `SecurityFilterChain` bean method. The snippet lacks full classes/imports/wiring so it is **not a standalone program**.

Why was the MVC matcher useful?

- It used Spring MVC's controller mapping resolution to make decisions, rather than matching paths with a starkly different mechanism.
- For MVC applications, it helped prevent the controller and security filter from interpreting wildcards in incompatible ways.
- It could extract path variables, supporting conditional expression checks.
- MVC paths are interpreted relative to the servlet path. If `DispatcherServlet` is mapped under `/mvc`, the matcher needed to know this to align with the controller.

In legacy configuration for a custom servlet path:

```java
MvcRequestMatcher.Builder mvc =
    new MvcRequestMatcher.Builder(handlerMappingIntrospector)
        .servletPath("/mvc");

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(mvc.pattern("/reports/**"))
        .hasAuthority("reports:read")
    .anyRequest().denyAll()
);
```

For request `/portal/mvc/reports/42`:
- Context root is `/portal`.
- Servlet path is `/mvc`.
- MVC controller mapping is `/reports/42`.
- Pattern `/reports/**` can match properly when the builder is configured with the matching servlet path.

**Do not assume `MvcRequestMatcher` is always equivalent to `PathPatternRequestMatcher` if you simply keep the same pattern string.** Spring Security 7 removes this servlet-prefix inference mechanism; URLs in matchers must be expressed relative to the application root, excluding the context root.

In 6.5, `MvcRequestMatcher` remains in the API but is deprecated for removal, with guidance to migrate to `PathPatternRequestMatcher`.

## 7. PathPatternRequestMatcher: The New Strategy Since 6.5

Import:

```java
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;
```

Create matchers using the builder:

```java
PathPatternRequestMatcher.Builder paths =
    PathPatternRequestMatcher.withDefaults();

RequestMatcher readReport =
    paths.matcher(HttpMethod.GET, "/api/reports/{reportId}");

RequestMatcher manageReports =
    paths.matcher("/api/reports/admin/**");
```

This is an API snippet; you need to import `org.springframework.http.HttpMethod` and `org.springframework.security.web.util.matcher.RequestMatcher`. `PathPatternRequestMatcher.withDefaults()` uses `PathPatternParser.defaultInstance`; the builder has an overload accepting `HttpMethod` to restrict the method.

When used in `authorizeHttpRequests`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;

@Configuration
class ReportHttpSecurity {
    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        var paths = PathPatternRequestMatcher.withDefaults();

        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(
                paths.matcher(HttpMethod.GET, "/api/public/**")
            ).permitAll()
            .requestMatchers(
                paths.matcher("/api/admin/**")
            ).hasRole("ADMIN")
            .requestMatchers(
                paths.matcher(HttpMethod.GET, "/api/reports/{id}")
            ).hasAuthority("reports:read")
            .anyRequest().denyAll()
        );

        return http.build();
    }
}
```

This is a **partial configuration**: it does not yet declare authentication (form, JWT, session, HTTP Basic...), CSRF, the MVC app, or per-report policies. In a real project, creating the security chain bean must match the runtime in use.

Key points:
- `paths.matcher(HttpMethod.GET, "/api/reports/{id}")` matches only GET and a single ID segment.
- The `id` variable can be present in `RequestMatcher.MatchResult` to serve an `AuthorizationManager` that needs extracted variables.
- `paths.matcher("/api/admin/**")` does not restrict the HTTP method, applying to all methods in the admin area.
- `anyRequest().denyAll()` closes remaining URLs **within the selected filter chain**.
- Ordering is still **first-match**, not automatically choosing the "longest pattern."

For applications with a custom `PathPatternParser`, the matcher and MVC controller must understand the same pattern rules. The Javadoc notes that `HandlerMapping` containing related URI mappings should use `PathPatternParser.defaultInstance` when using `withDefaults()`; if the project configures a different parser, supply a compatible parser to the matcher and write tests.

## 8. Do Not Include Context Path in PathPattern Patterns

An important migration rule: `PathPatternRequestMatcher` accepts URI paths **relative to the context path**, meaning **without** the context root.

Suppose:

```text
External URL: https://example.com/portal/api/reports/42
contextPath: /portal
servletPath: (default servlet mapping)
application path: /api/reports/42
```

The usually correct matcher is:

```java
PathPatternRequestMatcher.withDefaults()
    .matcher(HttpMethod.GET, "/api/reports/{id}");
```

Matcher that **does not match intent**:

```java
PathPatternRequestMatcher.withDefaults()
    .matcher(HttpMethod.GET, "/portal/api/reports/{id}");
```

The pattern above risks failing to match real requests because `/portal` is the context path stripped before path matching. Do not include `/portal` in every rule just because the external URL starts with `/portal`.

Also note that a reverse proxy may rewrite URLs. The browser seeing `https://site.example/gateway/api/...` does not guarantee the Servlet container sees the `/gateway` prefix. Measure actual `request.getContextPath()`, `request.getServletPath()`, and `request.getPathInfo()` in a safe test environment and determine the application path after proxy processing.

## 9. Custom Servlet Path: Use Builder.basePath

If `DispatcherServlet` runs at `/mvc`:

```text
External URL       /portal/mvc/reports/42
Context path       /portal
Servlet path       /mvc
MVC mapping        /reports/42
Pattern to match   /mvc/reports/{id}
```

You can write the full application path:

```java
var paths = PathPatternRequestMatcher.withDefaults();

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(
        paths.matcher(HttpMethod.GET, "/mvc/reports/{id}")
    ).hasAuthority("reports:read")
    .anyRequest().denyAll()
);
```

Or use a builder attached to the servlet prefix to avoid repetition:

```java
var mvc = PathPatternRequestMatcher.withDefaults()
    .basePath("/mvc");

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(
        mvc.matcher(HttpMethod.GET, "/reports/{id}")
    ).hasAuthority("reports:read")
    .requestMatchers(
        mvc.matcher("/admin/**")
    ).hasRole("ADMIN")
    .anyRequest().denyAll()
);
```

`basePath("/mvc")` is how you declare the **servlet prefix** so the builder constructs the corresponding full application path. Sub-patterns like `/reports/{id}` **must still start with `/`**. When there are multiple servlets, create builders with different base paths or specify matchers per servlet; do not rely on "MVC will guess the URL."

**Do not configure both basePath("/mvc") and matcher("/mvc/reports/**")** if the intent is only a single `/mvc` prefix; understand how the builder joins paths before using it. If `contextPath` is `/portal`, also do not write `basePath("/portal/mvc")` because the context path is not a servlet prefix.

## 10. Example: Migrating the Same Rules Across Three Generations

Suppose the application has:
- `GET /api/public/info` for guests.
- `GET /api/documents/{id}` for users with `document:read`.
- `DELETE /api/documents/{id}` for users with `document:delete`.
- `/api/admin/**` only for `ROLE_ADMIN`.

### A. Legacy Ant Pattern (Only Branches Retaining the Class)

```java
import static org.springframework.security.web.util.matcher.AntPathRequestMatcher.antMatcher;

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(antMatcher("/api/public/**")).permitAll()
    .requestMatchers(antMatcher("/api/admin/**")).hasRole("ADMIN")
    .requestMatchers(
        new AntPathRequestMatcher("/api/documents/**", "DELETE")
    ).hasAuthority("document:delete")
    .requestMatchers(
        new AntPathRequestMatcher("/api/documents/**", "GET")
    ).hasAuthority("document:read")
    .anyRequest().denyAll()
);
```

Requires importing `AntPathRequestMatcher`. Because `antMatcher("/api/public/**")` does not restrict HTTP method, **do not use this exact snippet for a GET-only public endpoint without changing it to a GET-specific matcher**. This illustrates migration from legacy code, not a security policy recommendation.

### B. Legacy MVC Pattern (Only Branches Retaining the Class)

```java
MvcRequestMatcher.Builder mvc =
    new MvcRequestMatcher.Builder(introspector);

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(mvc.pattern(HttpMethod.GET, "/api/public/**"))
        .permitAll()
    .requestMatchers(mvc.pattern("/api/admin/**"))
        .hasRole("ADMIN")
    .requestMatchers(mvc.pattern(HttpMethod.DELETE, "/api/documents/{id}"))
        .hasAuthority("document:delete")
    .requestMatchers(mvc.pattern(HttpMethod.GET, "/api/documents/{id}"))
        .hasAuthority("document:read")
    .anyRequest().denyAll()
);
```

`introspector` must be provided by the application; the signature `MvcRequestMatcher.Builder.pattern(HttpMethod, String)` belongs to compatibility branches and should not be copied to Spring Security 7.

### C. 6.5+/7.x Pattern Using PathPattern

```java
var paths = PathPatternRequestMatcher.withDefaults();

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(paths.matcher(
        HttpMethod.GET, "/api/public/**"
    )).permitAll()
    .requestMatchers(paths.matcher(
        "/api/admin/**"
    )).hasRole("ADMIN")
    .requestMatchers(paths.matcher(
        HttpMethod.DELETE, "/api/documents/{id}"
    )).hasAuthority("document:delete")
    .requestMatchers(paths.matcher(
        HttpMethod.GET, "/api/documents/{id}"
    )).hasAuthority("document:read")
    .anyRequest().denyAll()
);
```

In approach C, the request method/path intent is preserved while replacing the matcher with a supported type. Migrating from A/B to C must **be tested on real URLs**, especially:
- Root path vs sub-paths.
- Non-default servlet paths.
- Legacy wildcards and `{id}` variables.
- HTTP methods GET/HEAD/POST/PATCH/DELETE.
- Paths with trailing slashes or rewritten by a proxy.

**Do not merely fix imports to silence warnings.** Verify the set of URLs matched by each rule before and after migration.

## 11. What Is requestMatchers(String)? Why Shouldn't You Guess the Matcher Type?

In the common DSL, developers often write:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
);
```

This is an overload taking **strings**, not a direct constructor call to `AntPathRequestMatcher`, `MvcRequestMatcher`, or `PathPatternRequestMatcher`. Spring Security **constructs the RequestMatcher based on the version and configuration environment**.

Points to remember:

- In older branches, Spring Security could choose MVC style if Spring MVC was present, or Ant matchers in other contexts. XML namespaces also had `mvc`/`ant`/`regex` options depending on version.
- In 6.5, an application can configure a builder so the DSL chooses `PathPatternRequestMatcher`. The migration guide introduces `PathPatternRequestMatcherBuilderFactoryBean` as a way to prepare for 7.
- In 7.x, the default path matcher used by the DSL is `PathPatternRequestMatcher`, requiring path patterns to follow the new rules.
- If you pass **an explicit RequestMatcher object** to the matcher overload, you define exactly which matcher implementation is used, without depending on DSL inference.

Therefore, when auditing critical routes, write or inspect the explicit implementation rather than arguing that "`requestMatchers("/api/**")` is definitely Ant" across all versions.

## 12. Early Opt-In While Still on Spring Security 6.5

The Spring Security 6.5 → 7 migration guide mentions registering a bean:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.PathPatternRequestMatcherBuilderFactoryBean;

@Configuration
class MatcherMigrationConfiguration {

    @Bean
    PathPatternRequestMatcherBuilderFactoryBean requestMatcherBuilder() {
        return new PathPatternRequestMatcherBuilderFactoryBean();
    }
}
```

This bean directs the DSL to create path matchers via `PathPatternRequestMatcher`, helping catch incompatible rules before a major upgrade. This is a **Spring 6.5 migration snippet**; it is not mandatory configuration for all Spring Security 7.0 applications, and you must verify methods/packages in the actual dependency version in use.

When opting in:
- Do not just check that the app boots without error; execute **positive and negative security tests** for every path.
- If the app has custom servlet mappings, review servlet paths; the goal is explicit application paths.
- Matchers instantiated internally by third-party filters may not honor this builder bean; audit their configuration too.
- Cross-check matchers in both `securityMatcher` and `requestMatchers`, not only controller annotations.

**Note:** even without using the opt-in bean, you can still pass `PathPatternRequestMatcher.withDefaults().matcher(...)` directly to critical rules in the 6.5 branch.

## 13. Pattern Language Differences to Consider During Migration

### Literal Paths, Wildcards, and Path Variables

| Pattern | Common intent | What to test |
| --- | --- | --- |
| `/api/health` | Only one specific path | Does it match a trailing slash? |
| `/api/users/*` | One child segment | URLs with multiple segments, slashes, and encoded characters |
| `/api/users/{id}` | One named segment | Does it extract `id` properly and match the controller route? |
| `/api/files/**` | Resource subtree | Does the root `/api/files` match? |
| `/api/files/{*rest}` | Capture remaining path with `PathPattern` in supported versions | Real mapping, extracted variable, root case |
| `/**/admin/**` | Mid-path wildcard | **Do not assume portability** between Ant, Framework 6, and Framework 7 |

`PathPatternParser` is a parser with version-specific syntax and details. In Spring Framework 6, `**` and `{*var}` are generally restricted to the end of a pattern to reduce ambiguity; Spring Framework 7 introduced improvements for matching multiple segments before a literal. Do not declare a pattern "always invalid" or "always equivalent" across all versions. If using complex patterns, **verify against the parser and tests of the exact version running**.

Ant style may accept special patterns that PathPattern rejects or interprets differently. Patterns containing mid-path wildcards, dots, non-standard URL separators, encoded slashes, or semicolons should be audited case by case. Avoid vague security matchers like `/**/admin/**` just to catch a few endpoints; it is usually easier to review when sensitive routes share a clear prefix.

### Case Sensitivity

`AntPathRequestMatcher` has a case-sensitivity option in its constructor. `PathPatternParser` also has corresponding configuration. Do not assume URLs `/Admin` and `/admin` are always identical or always distinct without verifying that the MVC router, reverse proxy, servlet container, and matcher handle them identically.

### URL Encoding and Path Normalization

Because implementations do not always handle paths identically, test:
- `/api/users/42` and `/api/users/42/`.
- `/api/users/%34%32` (URL-encoded segment).
- `/api/files/a%2Fb` or encoded separators, if the container/proxy accepts them.
- `;` and matrix variables, if the application uses them.
- Strings containing `..` or confusing normalization forms.
- Case, duplicate slashes, context root, servlet prefix.

Do not ship an ambiguous pattern to production based on a single manual test.

## 14. Path Variables: Matching Does Not Mean the Resource Is Allowed

Example:

```java
var paths = PathPatternRequestMatcher.withDefaults();

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(
        paths.matcher(HttpMethod.GET, "/api/documents/{id}")
    ).hasAuthority("document:read")
    .anyRequest().denyAll()
);
```

A `GET /api/documents/42` request can match and a user with `document:read` passes HTTP authorization. **However, request ID 42 is still chosen by the client.** The URL matcher does not look up `Document#ownerId` or the tenant in the database.

In the service:

```java
// Integration snippet: repository, Actor, and DocumentPolicy are application-defined.
@PreAuthorize("hasAuthority('document:read')")
public DocumentDto readDocument(long id) {
    Actor actor = actorResolver.requireActorFromAuthentication();

    Document entity = repository
        .findByIdAndTenantId(id, actor.tenantId())
        .orElseThrow(DocumentNotFoundException::new);

    if (!policy.canRead(actor, entity)) {
        throw new AccessDeniedException("Not allowed");
    }
    return mapper.toDto(entity);
}
```

This is **not a standalone program**; real domain types/beans, transactions, annotation imports, and exceptions must be declared in the project. HTTP matching and domain permissions are two separate layers. A system can still suffer from IDOR/BOLA even when URL authorization matchers are right.

If using `RequestMatcher.MatchResult` to extract `id` for a custom `AuthorizationManager`, you must still validate the ID type, tenant, and actual object instead of trusting a path variable as an authenticated resource.

## 15. Selecting a SecurityFilterChain: Bigger Impact Than a Single Misaligned Rule

An application may have two chains:

```java
@Bean
@Order(1)
SecurityFilterChain adminApi(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/admin/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().hasRole("ADMIN")
        );
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain regularApi(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        );
    return http.build();
}
```

Snippets may require specific authentication configuration; `@Bean`/`@Order` and `SecurityFilterChain` need imports. What to learn:

1. `FilterChainProxy` selects the **first** chain whose `securityMatcher` matches.
2. Only after the chain is selected does `authorizeHttpRequests` inside it evaluate `requestMatchers`.
3. If the admin matcher fails to match due to a wrong servlet path or migration pattern, the request may fall into the regular chain and require only login.
4. If the regular chain also fails to match, the request may go unprotected by Spring Security if no suitable fallback chain exists.
5. `anyRequest().denyAll()` **inside one chain** does not protect requests **outside that chain**.

A matcher misconfiguration at `securityMatcher` is often more dangerous than a single functional rule bug, because it can drop all intended authentication, CSRF, and authorization filters for the request.

When upgrading from 6.5 to 7, inspect **every string-based `securityMatcher`** and custom builder, not only matchers inside `authorizeHttpRequests`.

## 16. A Very Specific Version-Scoped Security Advisory: Spring Security 7.0.0–7.0.4

In 2026, Spring published **CVE-2026-22753** regarding servlet paths not being included properly in matching under a specific configuration of `HttpSecurity#securityMatchers(String)`.

Relevant conditions per the official advisory:
- The application uses `securityMatchers(String)` for chain selection;
- Concurrently, a `PathPatternRequestMatcher.Builder` bean is used to prepend a servlet path;
- Chain selection may fail to match intended requests, causing the chain's security filters **not to run on those requests**.

Affected versions: **Spring Security 7.0.0 through 7.0.4**. Fixed version in the 7.0 line: **7.0.5**. The advisory explicitly states that Spring Security 6.x and earlier are not affected by this specific interaction.

Actions:
1. Upgrade affected versions to the patched release or newer in the corresponding branch.
2. If unable to upgrade immediately, consult the official mitigation to specify the servlet prefix explicitly in the matcher pattern.
3. Test `securityMatcher` to ensure the intended chain is selected when requests have a custom servlet path.
4. See [Spring advisory CVE-2026-22753](https://spring.io/security/cve-2026-22753/) to verify real-world applicability.

Do not overgeneralize as "all PathPattern usage is buggy" or "every 7.0 app is affected": the advisory describes **a specific combination** of string-based chain matchers and builders. Upgrading and testing chain selection are the key fixes.

## 17. When Should You Use Which Matcher?

### New Projects, Spring Security 7.x

Choose `PathPatternRequestMatcher` or the DSL string matchers supported by version 7. With a custom servlet path:
- Declare the full application path (excluding context root), or use a builder with `basePath`.
- Verify Spring MVC uses a compatible `PathPatternParser`.
- Do not use old `AntPathRequestMatcher`/`MvcRequestMatcher` imports that are no longer supported.
- Test positive/negative cases, public routes, admin, POST/PATCH, and fallback chains.

### 6.5 Projects Upgrading

Migrating early to `PathPatternRequestMatcher` is recommended; you can opt in the DSL via the official migration bean. Keep legacy classes short-term only if needed for compatibility and well tested. Standardize servlet paths and URL normalization before upgrading to 7.

### 6.4 or Older Branches Not Yet Upgrading

You can continue using matchers supported in that version. However:
- Do not apply code from Spring Security 7 docs to older branches if the new classes do not exist yet.
- Document the concrete matcher the DSL is creating (MVC/Ant).
- Never upgrade a major version by merely bumping dependencies without running security tests.
- Plan migration, especially for custom servlet mappings and complex wildcards.

### Non-Spring-MVC Systems

You can use `PathPatternRequestMatcher` for Servlet endpoints when aligned with application paths, or `RegexRequestMatcher`/custom matchers if other expressions are genuinely required. Do not force `MvcRequestMatcher` into an environment without MVC's `HandlerMappingIntrospector`. Any custom matcher must be reviewed as security code and tested against actual `HttpServletRequest` instances.

## 18. RegexRequestMatcher and Custom Matchers: Alternatives When Patterns Are Insufficient

All three matchers in this lesson belong to the path-matcher group. However, you may encounter URLs poorly expressed by `PathPattern`, such as certain endpoints of another servlet with special patterns.

In that case, Spring Security provides `RegexRequestMatcher`, using an appropriate regex. Depending on version, a factory can be used:

```java
import static org.springframework.security.web.util.matcher.RegexRequestMatcher.regexMatcher;

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(regexMatcher("^/legacy/.*\\.jsp$"))
        .hasAuthority("legacy:read")
    .anyRequest().denyAll()
);
```

Illustrative snippet; verify the exact path/method and regex at runtime. Regexes are easy to write too broadly (e.g., missing `^`/`$` anchors) or bypass via URL decoding, so use them only when needed and test thoroughly. A custom `RequestMatcher` may inspect headers, queries, or other conditions, but **must never trust client-supplied data as proof of authorization**.

The 6.5 → 7 migration guide also notes patterns without a general PathPattern replacement, such as certain servlet/JSP matching styles; those cases may require a dedicated regex. Do not try to replace every legacy matcher with a broader PathPattern wildcard just to make it build.

## 19. First-Match Still Holds Regardless of Which Matcher Is Used

Switching `AntPathRequestMatcher` to `PathPatternRequestMatcher` **does not turn DSL logic into a combination of all matching rules**.

Wrong example:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").authenticated()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
);
```

`/api/admin/users` matches the first matcher and requires only authentication; the later admin matcher does not add an admin requirement. Intentional version:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
);
```

**This is an ordering rule**, not an Ant-specific or PathPattern-specific issue. If migration changes the set of paths a matcher matches, which rule **gets evaluated first** can change as well. Therefore, security regression tests must examine all four:
- **Path semantics** (which matcher matches the URL).
- **Rule order** (which rule is selected).
- **Authority** (who the rule permits).
- **Resource policy** (whether the record belongs to the caller).

## 20. Standalone Java 17+ Program: Servlet Path Trap During Migration

The demo below avoids Spring to make learning and output verification straightforward. It **only simulates prefix matching for `/prefix/**` patterns** and does not recreate the parsers of `AntPathRequestMatcher`, `MvcRequestMatcher`, or `PathPatternRequestMatcher`. Its goal is to show why choosing **which part of the URL to compare** matters.

Save as `MatcherPathDemo.java`:

```java
public class MatcherPathDemo {

    record Request(
        String contextPath,
        String servletPath,
        String pathInfo,
        String method
    ) {
        String applicationPath() {
            return servletPath + pathInfo;
        }

        String legacyMvcPath() {
            return pathInfo;
        }
    }

    // Simple matcher ONLY for patterns ending with "/**".
    static boolean subtreeMatch(String actualPath, String pattern) {
        if (!pattern.endsWith("/**")) {
            throw new IllegalArgumentException("Expected /** pattern");
        }
        String root = pattern.substring(0, pattern.length() - 3);
        return actualPath.equals(root)
            || actualPath.startsWith(root + "/");
    }

    public static void main(String[] args) {
        Request request = new Request(
            "/portal", "/mvc", "/reports/42", "GET"
        );

        // Legacy model: pattern sits under the servlet path.
        boolean oldMvc = subtreeMatch(
            request.legacyMvcPath(), "/reports/**"
        );

        // New model: pattern must include servlet prefix, excluding context.
        boolean newWithoutPrefix = subtreeMatch(
            request.applicationPath(), "/reports/**"
        );
        boolean newWithPrefix = subtreeMatch(
            request.applicationPath(), "/mvc/reports/**"
        );

        // Bug: including context root /portal in the pattern.
        boolean newWithContext = subtreeMatch(
            request.applicationPath(), "/portal/mvc/reports/**"
        );

        // Example of method restriction independent of path.
        boolean getOnly = request.method().equals("GET")
            && newWithPrefix;
        boolean postOnly = request.method().equals("POST")
            && newWithPrefix;

        System.out.println("Application path: "
            + request.applicationPath());
        System.out.println("Legacy MVC relative: " + oldMvc);
        System.out.println("New without servlet prefix: "
            + newWithoutPrefix);
        System.out.println("New with servlet prefix: "
            + newWithPrefix);
        System.out.println("New with context prefix: "
            + newWithContext);
        System.out.println("GET rule matches: " + getOnly);
        System.out.println("POST rule matches: " + postOnly);
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac MatcherPathDemo.java
java MatcherPathDemo
```

Expected output:

```text
Application path: /mvc/reports/42
Legacy MVC relative: true
New without servlet prefix: false
New with servlet prefix: true
New with context prefix: false
GET rule matches: true
POST rule matches: false
```

Explanation:

1. The browser requests a URL containing `/portal`, but after removing the context root, the application path has the `/mvc` servlet prefix.
2. The legacy MVC example processes `/reports/42` relative to the servlet, so the relative pattern `/reports/**` matches.
3. A new PathPattern missing the servlet prefix fails to match `/mvc/reports/42`.
4. A PathPattern containing the context root `/portal` also fails to match.
5. Specifying the servlet prefix once makes the pattern align with the exact path.
6. HTTP method restriction is an independent condition; the same path can match GET without matching POST.

**Mandatory limitation to remember:** the demo works on author-supplied strings, non-null `pathInfo`, and subtree-only patterns. Real `HttpServletRequest`s, URL decoding, path variables, reverse proxies, Spring MVC, `PathPatternParser`, and Servlet mappings behave more complexly. Never use `subtreeMatch` as a production security filter.

## 21. Testing a Real RequestMatcher with MockHttpServletRequest

With Spring Security 6.5+/7 dependencies, you can construct matchers and mock requests in Spring tests; the example below is an **integration snippet**, not standalone `javac`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;
import static org.assertj.core.api.Assertions.assertThat;

class ReportMatcherTest {

    @Test
    void shouldMatchOnlyGetReportsUnderMvcServlet() {
        var paths = PathPatternRequestMatcher.withDefaults()
            .basePath("/mvc");
        var matcher = paths.matcher(
            HttpMethod.GET, "/reports/{id}"
        );

        MockHttpServletRequest get =
            new MockHttpServletRequest("GET", "/portal/mvc/reports/42");
        get.setContextPath("/portal");
        get.setServletPath("/mvc");
        get.setPathInfo("/reports/42");

        MockHttpServletRequest post =
            new MockHttpServletRequest("POST", "/portal/mvc/reports/42");
        post.setContextPath("/portal");
        post.setServletPath("/mvc");
        post.setPathInfo("/reports/42");

        assertThat(matcher.matches(get)).isTrue();
        assertThat(matcher.matches(post)).isFalse();
    }
}
```

**Verify this snippet against your specific Spring Test/Security version**: how `MockHttpServletRequest` represents paths in `ServletRequestPathUtils` and caches parsed request paths may differ from tests running through a real Servlet pipeline. If standalone matcher tests do not accurately simulate the parser/filter chain, test further with `MockMvc` or an embedded servlet container instead of assuming the matcher has a bug.

Your test suite must verify context path, servlet path, `pathInfo`, `requestURI`, and MVC configuration together. A matcher returning true in a direct unit test is not enough to prove the **SecurityFilterChain** containing that matcher is chosen at runtime if `@Order`/`securityMatcher` has issues.

## 22. Test Full HTTP Authorization, Not Just matches()

Suppose the configuration restricts:
- `GET /api/public/**` for anonymous.
- `GET /api/reports/{id}` requiring `reports:read`.
- `/api/admin/**` requiring `ROLE_ADMIN`.
- All remaining routes denied.

Minimum test matrix:

| Request | Identity | Expectation |
| --- | --- | --- |
| `GET /api/public/info` | Anonymous | Passes HTTP authorization step |
| `POST /api/public/info` | Anonymous | DENY if POST is not public |
| `GET /api/reports/42` | User with `reports:read` | ALLOW HTTP |
| `GET /api/reports/42` | User with only `ROLE_USER` | DENY HTTP |
| `POST /api/reports/42` | User with `reports:read` | DENY if no rule exists |
| `GET /api/admin/users` | User with only `reports:read` | DENY |
| `GET /api/admin/users` | User with `ROLE_ADMIN` | ALLOW HTTP |
| `GET /api/reports/42/` | User with `reports:read` | Verify per version/trailing-slash policy |
| `GET /portal/mvc/reports/42` | User with `reports:read`, context+servlet path | Matches right chain/rule after migration |
| `GET /api/unknown` | Authenticated user | DENY if default deny |
| `GET /api/reports/999` | User with `reports:read` but different tenant | DENY in domain policy |

**Do not just test "admin can access admin."** A more important test is that a normal user **cannot** enter admin after migration. Overly broad path matchers causing bypasses are usually discovered only by negative tests.

### MockMvc Snippet

```java
// JUnit + Spring Security Test snippet; requires real MockMvc, controller, and chain.
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@Test
void readerCannotEnterAdmin() throws Exception {
    mvc.perform(get("/api/admin/users")
            .with(user("alice").authorities(
                new SimpleGrantedAuthority("reports:read")
            )))
       .andExpect(status().isForbidden());
}

@Test
void readerCanReadReport() throws Exception {
    mvc.perform(get("/api/reports/42")
            .with(user("alice").authorities(
                new SimpleGrantedAuthority("reports:read")
            )))
       .andExpect(status().isOk());
}
```

You must supply `SimpleGrantedAuthority` and proper imports, a real endpoint handler returning 200 on success, and no other business policy denying access. If the endpoint does not exist, 404/405 does not prove the matcher works. When testing POST/PATCH with CSRF enabled, provide a valid CSRF token to avoid a 403 from `CsrfFilter` masking authorization errors.

### Testing SecurityFilterChain Directly

With multiple filter chains, add an integration test proving the chain with admin rules is actually **selected** on URLs with a servlet prefix. You can observe chain behavior or perform appropriate inspection via `FilterChainProxy`, not just check status codes. Inspect request paths after the container applies context/servlet mapping; a `securityMatcher`-level error can skip the entire chain.

## 23. Security Issues When Context Path / Servlet Path Are Inconsistent

Several ways applications get misconfigured during migration:

**Scenario 1 — duplicated context path**

```text
Public URL = /portal/api/admin/users
Context root = /portal
Wrong matcher = /portal/api/admin/**
Right matcher = /api/admin/**
```

**Scenario 2 — missing servlet path**

```text
URL = /portal/mvc/api/admin/users
contextPath = /portal
servletPath = /mvc
Legacy MVC pattern = /api/admin/**
PathPattern must include servlet = /mvc/api/admin/**
or basePath("/mvc") + matcher("/api/admin/**")
```

**Scenario 3 — missing fallback chain**

```text
Chain A: securityMatcher("/mvc/api/admin/**")
Chain B: securityMatcher("/mvc/api/**")
Request: /portal/other/path
=> If no chain matches, neither chain's filters apply.
```

**Scenario 4 — incompatible legacy wildcard**

```text
Legacy Ant matcher has a complex pattern with mid-path /**/.
New PathPattern version interprets it differently or parser throws an error.
=> Do not fix with /**.permitAll() or /api/**.authenticated()
   just "to make it run"; rewrite narrow patterns and test against real paths.
```

**Scenario 5 — proxy path rewrite**

```text
Browser GET /gateway/api/admin/users
Proxy rewrite -> Servlet receives /api/admin/users
Security matcher must match the request the Servlet sees,
not just the external URL.
```

These mistakes can drop sensitive routes into general rules or outside all filter chains. Always combine **matcher audit + negative authorization tests + runtime path inspection**.

## 24. Should You Choose an Explicit Matcher or a String Overload?

| Scenario | Practical choice | Reason |
| --- | --- | --- |
| Spring Security 7, default servlet, simple paths | `requestMatchers("/api/**")` in DSL 7 or explicit matcher | DSL 7 uses PathPattern; explicit aids clear review |
| Spring Security 6.5 preparing for 7 | `PathPatternRequestMatcher.withDefaults()` or opt-in builder | Verify parser behavior before major upgrade |
| Custom servlet path `/mvc` | `withDefaults().basePath("/mvc")` | Avoid dropping servlet prefix when matching |
| Protect GET only | `matcher(HttpMethod.GET, "/path")` | Avoid accidentally opening POST/DELETE |
| Legacy MVC system with legacy code | Temporary `MvcRequestMatcher` if version still supports it | Suits older branch; requires migration plan |
| Legacy non-MVC Servlet app | Temporary `AntPathRequestMatcher` if version still supports it | Suits legacy branch; do not use in 7 |
| Special regex or non-PathPattern routing | `RegexRequestMatcher`/custom matcher | When PathPattern cannot express it accurately; test tightly |
| Per-record owner/tenant permissions | Domain policy or `AuthorizationManager` querying trusted data | RequestMatcher does not replace object authorization |

Many systems using string matchers continue working after upgrade because requests sit under the default servlet path. However, applications using **non-default servlet mappings**, multiple chains, or complex wildcards require much more careful testing.

## 25. Migration Checklist from Ant/MVC Matchers to PathPattern

Before changing versions or APIs, follow these steps:

1. **Record exact dependencies:** Which versions of `spring-security-web`, `spring-security-config`, and Spring Framework MVC are running?
2. **List every matcher creation site:** `http.securityMatcher(s)`, `requestMatchers`, filter processing URLs, logout/switch-user, CORS, web ignoring, and matchers created by custom libraries.
3. **Document intended policy:** Which permission does each HTTP method/path require, which endpoints are public, admin, or fallback deny?
4. **Inspect servlet setup:** context root, servlet path, MVC controller mappings, and reverse-proxy rewrites.
5. **Identify the actual matcher in the old version:** Ant, MVC, custom, or DSL auto-selected?
6. **Write explicit PathPatterns:** paths start with `/`, omit context root, include servlet prefix or `basePath`.
7. **Check pattern syntax:** wildcards, path variables, complex patterns, slashes, encoding, and parser config.
8. **Preserve HTTP methods:** a public GET must not become all methods public.
9. **Preserve rule order:** specific request matchers precede general rules whenever two path sets overlap.
10. **Preserve chain order:** with multiple chains, narrow chains have the right `@Order`; include a fallback chain when needed.
11. **Run positive and negative tests:** anonymous/user/admin/reader; both allowed and denied routes.
12. **Run tests on real paths:** non-default context + servlet paths, reverse proxy/staging, URL edge cases.
13. **Check advisories:** especially Spring Security 7.0 patches related to servlet paths.
14. **Do not forget domain policy:** same authority but different owner/tenant must still be denied.
15. **Monitor and prepare rollback:** have safe logging/auditing for chain/rule denials, and test baselines before and after migration.

### Self-Check Questions

**Question 1.** Which new path matcher did Spring Security 6.5 introduce, and which two legacy classes does it recommend migrating away from?  
→ `PathPatternRequestMatcher`; the two legacy classes are `AntPathRequestMatcher` and `MvcRequestMatcher`, which are deprecated for removal.

**Question 2.** A project upgrades to Spring Security 7; can it keep importing `MvcRequestMatcher` to avoid changing configuration?  
→ **No**. Spring Security 7 no longer supports it; you must adopt the new matcher and test behavior.

**Question 3.** App deployed at `/portal`, Servlet at `/mvc`, controller `/orders/42`. Which prefix must PathPattern see?  
→ Match `/mvc/orders/42` (excluding context root `/portal`), or use builder `basePath("/mvc")` + `matcher("/orders/{id}")`.

**Question 4.** `requestMatchers("/api/**").authenticated()` appears before `requestMatchers("/api/admin/**").hasRole("ADMIN")`. Does switching to PathPattern fix the ordering automatically?  
→ **No**. First-match rule order still applies. The admin matcher must come before the general API rule.

**Question 5.** A test confirms the matcher matches `GET /api/documents/42` and the user has `document:read`. Is this enough to protect tenants?  
→ **No**. You must check the actual resource, tenant, owner/ACL, and status per policy.

**Question 6.** In 6.5 using `MvcRequestMatcher` on servlet `/mvc`, after switching to PathPattern with string `/reports/**` without adding the servlet prefix, what is the risk?  
→ The matcher may fail to match; the URL may fall through to another rule/chain. You must add the full application path or `basePath("/mvc")` and test.

**Question 7.** A project uses `securityMatchers(String)` and `PathPatternRequestMatcher.Builder` to prepend the servlet path on Security 7.0.3. What should be done?  
→ Check CVE-2026-22753, upgrade to the patched release (7.0.5 or higher in the 7.0 line), test chain selection, and apply the official mitigation if needed.

**Question 8.** A library needs to match an endpoint that cannot be described by PathPattern. Should `/**.permitAll()` replace the legacy matcher?  
→ **No**. Design a properly scoped `RegexRequestMatcher`/custom matcher, test thoroughly, and keep fallback deny.

## Conclusion

`AntPathRequestMatcher` and `MvcRequestMatcher` explain many examples in older Spring Security applications; `PathPatternRequestMatcher` was introduced in **6.5** and is the path-matching mechanism going into **7.x**. During migration, the crux is not merely the class name, but **which URLs are matched**, **paths relative to context/servlet**, **HTTP methods**, **rule order**, and **which SecurityFilterChain is selected**. Treat matcher migration as a security policy change requiring unit/integration tests, not just a syntax refactor.

## Official References

1. [Spring Security 6.5 — Web Migrations to 7](https://docs.spring.io/spring-security/reference/6.5/migration-7/web.html) — replacing `AntPathRequestMatcher`/`MvcRequestMatcher` and handling servlet prefixes.
2. [Spring Security 6.5 — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html) — `securityMatcher`, `requestMatchers`, servlet-path examples.
3. [Spring Security 7.0 — PathPatternRequestMatcher Javadoc](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/web/servlet/util/matcher/PathPatternRequestMatcher.html) — `withDefaults`, `PathPatternParser`, context path.
4. [Spring Security 6.5 — AntPathRequestMatcher Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/util/matcher/AntPathRequestMatcher.html) — legacy semantics and deprecation.
5. [Spring Security 6.5 — MvcRequestMatcher Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/servlet/util/matcher/MvcRequestMatcher.html) — `HandlerMappingIntrospector`/servlet path.
6. [Spring Security 7.0 — PathPatternRequestMatcher.Builder](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/web/servlet/util/matcher/PathPatternRequestMatcher.Builder.html) — `basePath` and method-specific matchers.
7. [Spring Security Advisory — CVE-2026-22753](https://spring.io/security/cve-2026-22753/) — affected versions and patch for servlet path matchers.
8. [Spring Security — Testing MockMvc](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/index.html) — integration tests for authorization.
