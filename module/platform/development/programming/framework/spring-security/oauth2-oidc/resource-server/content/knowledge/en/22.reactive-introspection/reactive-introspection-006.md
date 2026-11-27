# Customizing the Introspector with Reactive Composition

## 1. Context: Why Customize Introspection in WebFlux?

In a **Spring Security OAuth 2.0/OIDC Resource Server** running **Spring WebFlux**, an API can validate a Bearer access token using **OAuth 2.0 Token Introspection** per RFC 7662. Instead of verifying a JWT signature locally with a public key, the Resource Server sends the token string to a trusted introspection endpoint and asks the Authorization Server (AS) whether the token is still recognized.

For example, a client sends:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer Aq6p7W...opaque-access-token...
```

The Resource Server sends to the AS:

```http
POST /oauth2/introspect HTTP/1.1
Host: login.example.test
Authorization: Basic <introspection-client-credential>
Content-Type: application/x-www-form-urlencoded

token=Aq6p7W...opaque-access-token...
```

The AS might return:

```json
{
  "active": true,
  "iss": "https://login.example.test",
  "sub": "user-123",
  "client_id": "orders-web",
  "aud": ["orders-api"],
  "scope": "orders:read orders:export",
  "tenant_id": "tenant-a",
  "exp": 1893456000
}
```

A common scenario: the AS returns `active=true` and valid scopes, yet the application also wants to:

1. Accept only tokens intended for **`orders-api`**, not `payments-api`.
2. Restrict trusted issuers and client registrations per the contract.
3. Normalize authorities from AS-verified metadata **without accidentally granting extra permissions**.
4. Add metrics, tracing, timeouts, or a safe bounded cache.
5. Keep processing **non-blocking**, never turning authentication failures into success.

The primary extension point in WebFlux is **`ReactiveOpaqueTokenIntrospector`**. An effective customization technique is **reactive composition**: wrap a trusted introspector, receive `Mono<OAuth2AuthenticatedPrincipal>`, use Reactor operators to validate/transform the result, and return a new `Mono`.

> **Principle:** **Compose additional guarantees** around the core introspection step; never replace it by inspecting raw tokens yourself, ignoring `active`, or creating a principal when the AS could not verify the token.

## 2. What Role Does the Introspector Play in the WebFlux Chain?

Conceptual processing path:

```mermaid
sequenceDiagram
    participant C as OAuth Client
    participant F as AuthenticationWebFilter
    participant M as OpaqueTokenReactiveAuthenticationManager
    participant D as Decorator Introspector
    participant R as Remote Reactive Introspector
    participant AS as Authorization Server
    participant A as AuthorizationWebFilter
    C->>F: Authorization: Bearer token
    F->>M: authenticate(BearerTokenAuthenticationToken)
    M->>D: introspect(rawToken)
    D->>R: delegate.introspect(rawToken)
    R->>AS: POST introspection + client auth
    AS-->>R: active + metadata
    alt Inactive token or introspection error
        R-->>D: Mono.error(...)
        D-->>M: Mono.error(...)
        M-->>F: Authentication failure
        F-->>C: 401 / appropriate error
    else Token confirmed by AS
        R-->>D: Mono<OAuth2AuthenticatedPrincipal>
        D->>D: Audience / issuer / attributes / authorities
        alt Local token contract fails
            D-->>M: Mono.error(...)
            M-->>F: Authentication failure
        else Local token contract passes
            D-->>M: Mono<OAuth2AuthenticatedPrincipal>
            M-->>F: BearerTokenAuthentication
            F->>A: Reactor SecurityContext
            A-->>C: 2xx or 403 per permissions
        end
    end
```

Key components to remember:

| Component | Role |
| --- | --- |
| `SecurityWebFilterChain` | Selects the reactive HTTP security pipeline. |
| `ServerHttpSecurity` | WebFlux Resource Server configuration DSL. |
| `AuthenticationWebFilter` | Converts the request into an unauthenticated Authentication token and calls the reactive manager. |
| `OpaqueTokenReactiveAuthenticationManager` | Invokes `ReactiveOpaqueTokenIntrospector` to verify the token. |
| `ReactiveOpaqueTokenIntrospector` | Introspection contract returning `Mono<OAuth2AuthenticatedPrincipal>`. |
| `SpringReactiveOpaqueTokenIntrospector` | Implementation using reactive HTTP to query the AS, depending on version. |
| `OAuth2AuthenticatedPrincipal` | Principal data, attributes, and granted authorities accepted by the introspector. |
| `BearerTokenAuthentication` | Authentication for a token verified by the manager via introspection. |
| `AuthorizationWebFilter` and reactive method security | Checks permissions based on the established authentication. |

**Do not confuse WebFlux with Servlet.** Servlet uses synchronous `OpaqueTokenIntrospector` returning `OAuth2AuthenticatedPrincipal` directly, whereas WebFlux uses `ReactiveOpaqueTokenIntrospector` returning `Mono`. Likewise, Servlet uses `HttpSecurity`/`SecurityFilterChain`; WebFlux uses `ServerHttpSecurity`/`SecurityWebFilterChain`.

### 2.1. Introspection Does Not Equal Full Authorization

The AS may return `active=true` for tokens belonging to its OAuth ecosystem. The API must still decide whether the token targets the right **resource**, carries the right **scope**, and whether the principal has rights on the **specific resource instance**.

For example, user A holding `SCOPE_orders:read` does not imply permission to read user B's orders. The introspector generally handles the **token contract**; owner/tenant access on `orderId` must be enforced at the service/repository/authorization layer.

## 3. The ReactiveOpaqueTokenIntrospector Contract

Primary interface:

```java
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import reactor.core.publisher.Mono;

@FunctionalInterface
public interface ReactiveOpaqueTokenIntrospector {
    Mono<OAuth2AuthenticatedPrincipal> introspect(String token);
}
```

The snippet shows the core signature; the real interface lives in package `org.springframework.security.oauth2.server.resource.introspection`.

For composition, you must understand the three `Mono` signals:

| Signal | Meaning | Security rule |
| --- | --- | --- |
| `onNext(principal)` then `onComplete()` | Introspection returned an accepted principal along the delegate path. | Continue validating additional policies before letting the manager build Authentication. |
| `onError(error)` | Token rejected or verification failed. | **Never create a principal**; propagate an appropriate error. |
| Only `onComplete()`, no principal | No introspection result. | **Fail-closed**; never treat empty as a valid token. |

A valid introspector must not return `Mono.just(...)` from an AS-unverified token string unless it is itself another **trusted implementation** that verified the token under an equivalent contract.

### 3.1. Lazy Execution of Mono

In the Reactor model, operators like `map`, `flatMap`, and `doOnError` only describe a pipeline; the network call executes upon subscription. Example:

```java
Mono<OAuth2AuthenticatedPrincipal> result =
        delegate.introspect(rawToken)
                .map(principal -> transform(principal));
```

In WebFlux, the framework subscribes to the HTTP processing chain. Never call `.block()` or manual `.subscribe()` on the authentication path just to grab a principal "immediately."

```java
// WRONG: blocks the reactive request thread.
OAuth2AuthenticatedPrincipal principal =
        delegate.introspect(rawToken).block();

// WRONG: self-subscribes and returns another principal before verification finishes.
delegate.introspect(rawToken).subscribe();
return Mono.just(makeDefaultPrincipal());
```

### 3.2. Common Exceptions

`BadOpaqueTokenException` represents an invalid or unacceptable opaque token. `OAuth2IntrospectionException` describes errors related to the introspection process. Exceptions must be handled in line with your Spring Security version and the system's error policy.

**An AS timeout or wrong introspection credentials** differs from **the AS returning `active=false`**. Both must fail closed, yet operational classification differs.

## 4. What Is Reactive Composition?

Instead of subclassing or modifying Spring Security's HTTP implementation, build a **decorator**:

```text
External Bearer token
       |
       v
ReactiveOpaqueTokenIntrospector (custom decorator)
       |
       +-- delegate.introspect(token)
       |      |
       |      +-- HTTP introspection via trusted endpoint
       |      +-- active=false -> error
       |      +-- active=true  -> OAuth2AuthenticatedPrincipal
       |
       +-- validate audience/issuer/client contract
       +-- map/limit authorities when needed
       +-- observe latency/error category safely
       |
       +-- return Mono<OAuth2AuthenticatedPrincipal>
```

Suitable Reactor operators:

| Operator | When to use | Warning |
| --- | --- | --- |
| `map` | Synchronously transform an existing principal, e.g., mapping authorities. | Never put blocking HTTP/JDBC inside `map`. |
| `flatMap` | Policy returns a `Mono`, e.g., async lookup or conditional `Mono.error`. | Never emit a principal if policy fails. |
| `filter` | Keep elements matching a predicate. | `filter` can produce **`Mono.empty()`**; for authentication, turn rejections into explicit errors. |
| `switchIfEmpty` | Handle the absent-principal case. | Should **fail closed**; never synthesize a fallback admin/user. |
| `doOnNext` / `doOnSuccess` | Record observability metrics/events. | Never log tokens, secrets, or attributes containing PII. |
| `doOnError` | Observe errors and classify internally. | Never swallow errors or dump raw exception messages carelessly. |
| `timeout` | Bound wait time for introspection. | Timeout must lead to denial/dependency error, never granting access. |
| `onErrorMap` | Translate exceptions into appropriate error categories. | Do not erase the distinction between inactive tokens and upstream outages in ops telemetry. |
| `retryWhen` | Bounded retries for certain transient network errors. | Never retry all errors or `active=false` tokens. |
| `defer` | Construct the pipeline at subscription time when needed. | Avoid accidentally triggering multiple introspection calls. |
| `contextWrite` / `deferContextual` | Read or enrich Reactor Context per policy. | Context is not a source of Bearer token authentication proof. |

### 4.1. Why a Decorator Usually Beats Rewriting a Remote Introspector

An HTTP introspection implementation already handles many subtleties:

- HTTP POST with `application/x-www-form-urlencoded`.
- Resource Server client authentication, such as Basic or another AS-supported scheme.
- Parsing `active`, response JSON, and converting metadata.
- Classifying HTTP errors, timeouts, and transport failures.
- Protecting credentials when calling the endpoint.

If you only need **an extra audience validator or authority restriction**, rewriting the entire HTTP client increases protocol risk. A decorator keeps a properly configured delegate intact and adds only the required steps.

## 5. Example 1: Fail-Closed Audience-Checking Decorator

Suppose the AS guarantees `aud` in the introspection response and the API accepts only tokens meant for `orders-api`.

A standalone implementation:

```java
import java.util.Collection;
import java.util.Objects;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;

public final class AudienceCheckingIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    private final ReactiveOpaqueTokenIntrospector delegate;
    private final String expectedAudience;

    public AudienceCheckingIntrospector(
            ReactiveOpaqueTokenIntrospector delegate,
            String expectedAudience) {
        this.delegate = Objects.requireNonNull(delegate);
        this.expectedAudience = Objects.requireNonNull(expectedAudience);
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
        return delegate.introspect(token)
                .switchIfEmpty(Mono.error(
                        new BadOpaqueTokenException(
                                "No principal from introspection")))
                .flatMap(principal -> {
                    Object aud = principal.getAttribute("aud");

                    boolean matches =
                            (aud instanceof String one
                                    && expectedAudience.equals(one))
                            || (aud instanceof Collection<?> many
                                    && many.contains(expectedAudience));

                    return matches
                            ? Mono.just(principal)
                            : Mono.error(new BadOpaqueTokenException(
                                    "Token is not intended for this API"));
                });
    }
}
```

**How it works:**

1. `delegate.introspect(token)` performs remote introspection and evaluates `active`.
2. If the delegate errors, `Mono.error` propagates; `flatMap` does not run.
3. If the delegate completes empty, `switchIfEmpty` turns it into an error—**never letting it pass**.
4. Once a principal arrives, policy verifies `aud` is an **exact string** or a collection containing that exact string.
5. If `aud` is missing, wrong type, or targets another resource, it emits `BadOpaqueTokenException`.
6. Only when every condition passes does it emit **the principal from the delegate**.

Suppose:

```json
{
  "active": true,
  "aud": ["payments-api"],
  "scope": "orders:read"
}
```

The token must still be rejected at `orders-api`, even though the AS returned `active=true` and the token carries `orders:read`.

### 5.1. Why Not Use `filter` Alone?

You could write:

```java
return delegate.introspect(token)
        .filter(principal -> hasAudience(principal, "orders-api"));
```

However, when audience mismatches, the result is **`Mono.empty()`**, not a clearly categorized failure. Depending on the manager/composition, empty may be interpreted as abstaining or cause confusing errors. For **authentication**, the safer and clearer choice is emitting `Mono.error(new BadOpaqueTokenException(...))`.

### 5.2. What If the AS Does Not Return `aud`?

RFC 7662 does not force every AS to return `aud` on every token. If API policy mandates resource binding, missing `aud` **cannot silently pass**.

There are two proper options:

- Require the AS to return `aud` per the **introspection contract**.
- Or document an equivalent mechanism: the AS only returns `active=true` for tokens targeting the Resource Server authenticated by that client registration/credential, backed by integration tests proving it.

Never assume **every** `active=true` token is meant for the current API.

## 6. Example 2: Verifying Issuer and Client per Contract

If the Resource Server accepts tokens from a specific issuer and the introspection response discloses `iss`, you can compose another check:

```java
private static Mono<OAuth2AuthenticatedPrincipal> requireIssuer(
        OAuth2AuthenticatedPrincipal principal,
        String trustedIssuer) {

    Object issuer = principal.getAttribute("iss");

    return trustedIssuer.equals(issuer)
            ? Mono.just(principal)
            : Mono.error(new BadOpaqueTokenException(
                    "Unexpected token issuer"));
}
```

Composing them:

```java
return delegate.introspect(token)
        .switchIfEmpty(Mono.error(
                new BadOpaqueTokenException("No introspection result")))
        .flatMap(principal -> requireIssuer(
                principal, "https://login.example.test"))
        .flatMap(principal -> requireAudience(
                principal, "orders-api"));
```

`requireAudience` in this example is a helper matching Section 5's policy, extracted into its own method to avoid duplication. This is an **illustrative pipeline**, not a complete copy-pasteable class.

### 6.1. Never Read the Issuer from an Unverified Token

Do not do:

```java
// WRONG: issuer/endpoint derived from client input.
String uri = request.getHeader("X-Introspection-URL");
ReactiveOpaqueTokenIntrospector delegate =
        buildIntrospector(uri, clientSecret);
```

The introspection endpoint and credentials must come from **trusted configuration**. Letting callers select the endpoint risks SSRF or leaking the Resource Server's Basic credentials.

### 6.2. `client_id` in the Response Is Not the Resource Server's `client_id`

In an introspection response:

```json
{
  "active": true,
  "client_id": "orders-mobile",
  "scope": "orders:read"
}
```

`client_id` usually identifies the **OAuth client issued the access token**. It can differ from the `client_id` the Resource Server uses **to authenticate when calling the introspection endpoint**.

The API can check an allowlist of OAuth client IDs if required by contract:

```java
Set<String> permittedClients =
        Set.of("orders-web", "orders-mobile");

Object clientId = principal.getAttribute("client_id");
boolean allowed =
        clientId instanceof String value
        && permittedClients.contains(value);
```

Yet this is an **additional token-profile policy**, not a substitute for scope/audience checks. Never use prefix or substring matching like `startsWith("orders")` when client IDs are exact identities.

## 7. Chaining Steps with a Reusable Policy Pipeline

When there are many conditions, stuffing everything into a single `flatMap` becomes hard to read. You can extract policies into functions sharing one contract:

```java
import java.util.List;
import java.util.Objects;
import java.util.function.Function;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;

public final class ComposedReactiveIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    private final ReactiveOpaqueTokenIntrospector delegate;
    private final List<Function<
            OAuth2AuthenticatedPrincipal,
            Mono<OAuth2AuthenticatedPrincipal>>> steps;

    public ComposedReactiveIntrospector(
            ReactiveOpaqueTokenIntrospector delegate,
            List<Function<
                    OAuth2AuthenticatedPrincipal,
                    Mono<OAuth2AuthenticatedPrincipal>>> steps) {
        this.delegate = Objects.requireNonNull(delegate);
        this.steps = List.copyOf(steps);
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
        Mono<OAuth2AuthenticatedPrincipal> result =
                delegate.introspect(token);

        for (var step : steps) {
            result = result.flatMap(step);
        }

        return result.switchIfEmpty(Mono.error(
                new BadOpaqueTokenException(
                        "Introspection policy did not produce a principal")));
    }
}
```

Assembling the steps:

```java
var composed = new ComposedReactiveIntrospector(
        remoteIntrospector,
        List.of(
                principal -> requireIssuer(
                        principal, "https://login.example.test"),
                principal -> requireAudience(
                        principal, "orders-api"),
                principal -> requireAllowedClient(
                        principal, permittedClients)));
```

`requireIssuer`, `requireAudience`, and `requireAllowedClient` are policy helpers returning `Mono.just(principal)` on pass and `Mono.error(...)` on failure. Using `List.copyOf` ensures the step list cannot be mutated externally after construction.

### 7.1. Order Can Affect Performance and Information Disclosure

Suppose one step merely checks the `aud` string, while a later step queries a reactive user registry to resolve the actor. Run **cheap, pure-data checks** first, before steps that incur I/O when the contract truly requires them.

Still, never rely on "error ordering" to leak the list of trusted issuers or audiences to callers. Public responses should remain minimal; detailed error categories belong strictly in redacted internal telemetry.

### 7.2. Not Every Policy Belongs in the Introspector

If a condition depends on the **request's `orderId`**, such as "does the user own this order?", `introspect(String token)` **has no `orderId` parameter**. Forcing the introspector to read external request context to check ownership creates coupling and breaks easily with Reactor Context/async boundaries.

Separate them:

- **Introspector**: token status, resource audience, issuer/client contract, principal metadata checks.
- **Method/domain authorization**: action scopes, user/tenant membership, resource ownership, order state.

## 8. Example 3: Mapping and Restricting Authorities per Contract

Spring Security typically maps scopes from the introspection response:

```json
{
  "active": true,
  "sub": "user-123",
  "scope": "orders:read orders:export"
}
```

to:

```text
SCOPE_orders:read
SCOPE_orders:export
```

However, an API may want to **keep only recognized authorities**. We can use `map` since this is pure in-memory processing:

```java
import java.util.List;
import java.util.Set;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;

private static OAuth2AuthenticatedPrincipal restrictAuthorities(
        OAuth2AuthenticatedPrincipal principal) {

    Set<String> accepted = Set.of(
            "SCOPE_orders:read",
            "SCOPE_orders:export");

    List<GrantedAuthority> filtered =
            principal.getAuthorities().stream()
                    .filter(authority ->
                            accepted.contains(authority.getAuthority()))
                    .toList();

    return new DefaultOAuth2AuthenticatedPrincipal(
            principal.getName(),
            principal.getAttributes(),
            filtered);
}
```

Composing after introspection and policy checks:

```java
return delegate.introspect(token)
        .switchIfEmpty(Mono.error(
                new BadOpaqueTokenException("Missing principal")))
        .flatMap(principal -> requireAudience(
                principal, "orders-api"))
        .map(MyAuthorityPolicy::restrictAuthorities);
```

In this example, `MyAuthorityPolicy` is an application-defined class housing `restrictAuthorities`. `getAttributes()` is preserved for downstream policies, while `getAuthorities()` drives Spring Security authorization.

### 8.1. Be Careful with Non-Scope Authorities

Some Spring Security versions add authorities representing **authentication factors** or authentication mechanism metadata, not just `SCOPE_...`. Stripping every authority outside a scope allowlist can alter policies that depend on those other authorities.

Therefore:

- Understand the **full authority contract** of your framework version.
- Restrict authorities strictly per an approved policy.
- Test both retained authorities and stripped authorities.
- Never inject `ROLE_ADMIN` or `SCOPE_orders:write` merely because `client_id` or email looks admin-like.

### 8.2. Do Not Use `map` to Fabricate Extra Privileges

Dangerous example:

```java
// WRONG: turns every active token into an admin.
List<GrantedAuthority> authorities =
        List.of(new SimpleGrantedAuthority("ROLE_ADMIN"));
```

Introspector composition is a sensitive extension point: any authority added here is seen by the authorization layer as belonging to the principal. Only add privileges when the AS verified the source data, mapping follows an allowlist, and tests verify privilege-escalation resistance.

### 8.3. Attributes and Authorities May Diverge in Representation

If you filter authorities while leaving raw `scope` in attributes, downstream code reading `scope` directly might interpret permissions differently from the filtered policy. Enforce a rule:

**Spring Security authorization relies on normalized `Authentication.getAuthorities()`**; business code must not parse raw `scope` on its own to grant access.

For auditing, raw claims can remain on the internal principal subject to access controls, but never send full attributes back to HTTP callers.

## 9. Use `map` for Synchronous Steps; Use `flatMap` for Asynchronous Steps

Example:

```java
return delegate.introspect(token)
        // Synchronous, no I/O.
        .map(MyAuthorityPolicy::restrictAuthorities)
        // Reactive policy returning a Mono.
        .flatMap(principal ->
                accountStatusPolicy.requireEligibleAccount(principal));
```

Assume `accountStatusPolicy.requireEligibleAccount` returns `Mono<OAuth2AuthenticatedPrincipal>` and never emits a principal when the account is ineligible.

**Do not do**:

```java
// WRONG: map produces Mono<Mono<Principal>> instead of Mono<Principal>.
return delegate.introspect(token)
        .map(principal ->
                accountStatusPolicy.requireEligibleAccount(principal));
```

With `flatMap`, Reactor awaits the async operation's outcome before continuing. Avoid forcing async data into a boolean via `.block()`.

### 9.1. Should Membership Be Queried Inside the Introspector?

If account status or tenant membership is **genuinely an API-wide token acceptance condition**, a reactive check per contract can be considered. However, doing so:

- Adds a database dependency to every authentication.
- Increases latency and introduces new failure modes.
- Causes account-check frequency to couple with any token caching.
- Still does not replace per-order object-level policies.

For most applications, it is cleaner to keep the introspector verifying the **access-token contract**, and use the **reactive authorization/service layer** for dynamic data permissions.

### 9.2. Synchronous Database Calls Inside `map` Are an Anti-Pattern

```java
// WRONG: JDBC can block the Netty event loop.
return delegate.introspect(token)
        .map(principal -> {
            jdbcTemplate.queryForObject(
                    "select active from accounts where id=?",
                    Boolean.class,
                    principal.getName());
            return principal;
        });
```

In WebFlux, use a reactive driver/repository or offload legacy blocking I/O onto bounded schedulers in a dedicated layer with capacity planning. Never use `Mono.just(jdbcCall())`, since the blocking call happens **before the Mono is even created**.

## 10. Example 4: Strictly Type-Checking Metadata

Introspection responses can return claims in various JSON types. Policies must not call `toString()` indiscriminately:

```json
{"active":true,"tenant_id":"tenant-a"}
```

differs from:

```json
{"active":true,"tenant_id":{"id":"tenant-a"}}
```

If the token contract requires `tenant_id` to be a syntax-constrained string:

```java
private static Mono<OAuth2AuthenticatedPrincipal> requireTenantClaim(
        OAuth2AuthenticatedPrincipal principal) {

    Object raw = principal.getAttribute("tenant_id");

    if (raw instanceof String tenant
            && tenant.matches("[a-zA-Z0-9_-]{1,64}")) {
        return Mono.just(principal);
    }

    return Mono.error(new BadOpaqueTokenException(
            "Tenant claim violates token contract"));
}
```

This checks **claim format**, not whether the user belongs to that tenant or can read its records. Those decisions require a trusted data source and domain policy.

### 10.1. Difference Between User Subjects and Client-Credentials Tokens

In a client-credentials grant, the token may represent a **service principal**, not a human user. `sub`, `client_id`, and service identity metadata must be interpreted according to the token profile.

Never use `email` or `preferred_username` as a stable identity key without a contract. For end-users, a common pattern binds **`(verified issuer, verified subject)`** to an internal user ID; for workloads, resolve a dedicated service identity.

## 11. Configuring Spring Boot WebFlux with Delegate and Decorator

Gradle Groovy DSL dependency example:

```gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-resource-server")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
    testImplementation("io.projectreactor:reactor-test")
}
```

A WebFlux API typically configures the introspection endpoint and client credentials via properties:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.test/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

**The client secret here belongs to the Resource Server calling the AS**, distinct from the caller's Bearer access token. Never commit production secrets to Git, and never expose secrets in logs or responses.

### 11.1. Creating a Custom `ReactiveOpaqueTokenIntrospector` Bean

Example using the builder on Spring Security versions that support this API:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.SpringReactiveOpaqueTokenIntrospector;

@Configuration
public class IntrospectionConfig {

    @Bean
    ReactiveOpaqueTokenIntrospector reactiveOpaqueTokenIntrospector(
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.introspection-uri}")
            String uri,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-id}")
            String clientId,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-secret}")
            String clientSecret) {

        ReactiveOpaqueTokenIntrospector remote =
                SpringReactiveOpaqueTokenIntrospector
                        .withIntrospectionUri(uri)
                        .clientId(clientId)
                        .clientSecret(clientSecret)
                        .build();

        return new AudienceCheckingIntrospector(
                remote, "orders-api");
    }
}
```

**Version note:** verify the `withIntrospectionUri` builder API against the Spring Security Javadoc for your project's version. Older lines may use constructors or different HTTP client configurations. The goal here is **passing a trusted implementation into the decorator**; keep business code decoupled from a specific constructor.

When Spring Boot would otherwise auto-configure a default introspector and the application **registers a bean of the same interface**, Boot backs off from creating the default bean. Therefore, the right pattern is **explicitly constructing the delegate** and wrapping it, or defining a named/qualified bean graph—never expect to auto-wire the same interface into the very bean being constructed, which creates a circular dependency.

### 11.2. Enabling the Resource Server in `SecurityWebFilterChain`

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class ApiSecurityConfig {

    @Bean
    SecurityWebFilterChain apiChain(
            ServerHttpSecurity http,
            ReactiveOpaqueTokenIntrospector introspector) {

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders:read")
                        .anyExchange().authenticated())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .opaqueToken(opaque ->
                                opaque.introspector(introspector)))
                .build();
    }
}
```

Meaning:

- `.opaqueToken(...)` selects **introspection-based authentication**.
- `.introspector(introspector)` ensures the chain uses the **configured decorator**.
- `hasAuthority("SCOPE_orders:read")` checks scope/authority after authentication.
- Requests without valid tokens still cannot pass authentication.

**Do not confuse** with Servlet `HttpSecurity` and synchronous `OpaqueTokenIntrospector`. In WebFlux, the manager, introspector, and filter chain all belong to the reactive stack.

### 11.3. When an Application Has Multiple `SecurityWebFilterChain` Beans

Each chain needs an appropriate matcher and order. A broad `/**` chain can match before a narrow chain if ordered carelessly. Test endpoints to confirm the right introspector runs; **having a bean in the context does not prove the intended chain uses it**.

If an endpoint accepts only JWTs, use the corresponding JWT manager/decoder. Do not expect Spring to inspect dots in the token string and switch between JWT and opaque automatically.

## 12. Execution Timing: `Mono.defer` and Lazy Composition

A decorator should ensure it does not accidentally introspect **twice**:

```java
// Can create two subscriptions and two HTTP calls:
Mono<OAuth2AuthenticatedPrincipal> source =
        delegate.introspect(token);

Mono<Boolean> hasAudience = source.map(this::matchesAudience);
Mono<String> name = source.map(OAuth2AuthenticatedPrincipal::getName);

return Mono.zip(hasAudience, name)
        .map(tuple -> buildPrincipal(tuple.getT2()));
```

This is a **conceptual example with hypothetical helpers** illustrating the risk: subscribing multiple times to a cold publisher can trigger multiple remote introspection calls. When the same principal needs several checks, it is usually simpler to write:

```java
return delegate.introspect(token)
        .flatMap(principal -> {
            // Same principal; no second subscription to the source.
            if (!matchesAudience(principal)
                    || !matchesIssuer(principal)) {
                return Mono.error(new BadOpaqueTokenException(
                        "Token contract rejected"));
            }
            return Mono.just(principal);
        });
```

### 12.1. When Is `Mono.defer` Useful?

When building the remote call or reading current credentials/config must happen at subscription time:

```java
return Mono.defer(() -> {
    ReactiveOpaqueTokenIntrospector activeDelegate =
            delegateProvider.currentTrustedDelegate();
    return activeDelegate.introspect(token);
});
```

`delegateProvider` is an application-defined abstraction responsible for returning a trusted delegate under a secret-rotation policy. **Never take URIs or credentials from HTTP requests or tokens** to build a delegate.

With a fixed delegate, writing `return delegate.introspect(token).flatMap(...)` directly is usually enough. Never use `defer` as a "fix" for blocking I/O in a synchronous HTTP client.

### 12.2. Avoid Manual `subscribe()`

`subscribe()` detaches work from the authentication pipeline managed by Spring Security. When that subscription fails, the filter may never notice, and you may already have returned authentication prematurely. Always **return the `Mono`** intact to the manager.

## 13. Observability with `doOn...` Without Leaking Credentials

A decorator can measure latency and count errors. A simple way is attaching side-effect operators:

```java
@Override
public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
    return delegate.introspect(token)
            .flatMap(principal ->
                    requireAudience(principal, "orders-api"))
            .doOnNext(principal ->
                    metrics.increment("introspection.accepted"))
            .doOnError(error ->
                    metrics.increment("introspection.rejected"));
}
```

`metrics` is an illustrative abstraction, not a Reactor API; applications can use Micrometer accordingly. This snippet does not classify specific errors—it only shows where to place instrumentation.

**Do not do**:

```java
.doOnError(error ->
        log.error("token={} introspection error={}",
                token, error.getMessage()))
```

Because:

- `token` is a Bearer credential.
- Exception messages can contain the introspection URI, response body, client registration, or other sensitive data.
- Metric labels using unverified tokens or subjects cause leaks and extreme cardinality.

### 13.1. Measuring Duration with Signal-Safe Logic

If latency measurement is needed:

```java
return Mono.defer(() -> {
    long started = System.nanoTime();

    return delegate.introspect(token)
            .flatMap(this::verifyContract)
            .doFinally(signal ->
                    metrics.recordNanos(
                            "introspection.duration",
                            System.nanoTime() - started));
});
```

`verifyContract` and `metrics.recordNanos` are application-implemented methods. `doFinally` runs on complete/error/cancel, making it suitable for duration tracking—just **never treat cancellation as equivalent to an invalid token**.

### 13.2. Reactor Context and Correlation IDs

In WebFlux, request metadata can flow via the **Reactor Context**, without relying on Servlet `ThreadLocal`.

```java
return Mono.deferContextual(context -> {
    String requestId = context.getOrDefault(
            "requestId", "unknown");

    return delegate.introspect(token)
            .doOnError(error ->
                    audit.recordFailure(
                            requestId,
                            "INTROSPECTION_FAILURE"));
});
```

Here `audit` is an application abstraction. If `requestId` originates from a client header, validate length and character set before logging it as an identifier. **Context is processing-flow metadata**, not proof the caller is authenticated.

## 14. Timeouts and Exception Mapping: Fail Closed

Remote introspection introduces a runtime dependency. A slow AS can slow down the API even when the domain service is fast.

Example wrapping a timeout:

```java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import org.springframework.security.oauth2.server.resource.introspection.OAuth2IntrospectionException;

return delegate.introspect(token)
        .timeout(Duration.ofSeconds(2))
        .onErrorMap(TimeoutException.class, error ->
                new OAuth2IntrospectionException(
                        "Introspection dependency timeout"));
```

This is an **error-classification pattern**, not a complete HTTP status policy. Before adopting it, ensure timeouts are also configured on the HTTP client/network, and distinguish:

1. Token confirmed `active=false` by the AS: authentication failure.
2. AS rejects **introspection client credentials**: configuration/secret-rotation incident.
3. AS/HTTP client timeout/TLS/DNS/5xx: dependency unavailable.
4. Active token missing `SCOPE_orders:read`: authorization failure.

In all cases **never fabricate an authenticated principal**. Operational telemetry must separate these causes so outages are not misdiagnosed as mass token revocations.

### 14.1. Fail-Open Anti-Patterns

```java
// DANGEROUS: every token is accepted when the AS fails.
return delegate.introspect(token)
        .onErrorResume(error ->
                Mono.just(createAdministratorPrincipal()));
```

When a dependency is unavailable, there is no proof the token is valid. This is **privilege escalation**.

Another dangerous fallback:

```java
// DANGEROUS: serves stale cached principals indefinitely.
return delegate.introspect(token)
        .onErrorResume(error ->
                cachedPrincipalWithoutExpiry(token));
```

Any cache must enforce an explicit TTL and revocation policy; never use it as a fail-open bypass for unverified or expired tokens.

### 14.2. HTTP Status Classification Does Not Belong Solely to the Introspector

In many Spring Security configurations, `BadOpaqueTokenException` leads to a Bearer authentication error such as **401 invalid_token**. AS unavailability errors propagate through the authentication chain and are handled per configuration.

If the API should return **503 Service Unavailable** on dependency outages, design appropriate exception translation / WebFlux entry points while preserving Bearer semantics and hiding endpoints/credentials. **Never assume `timeout()` produces 503 on its own.**

## 15. Retries in Introspection: Bounded and Only for Eligible Errors

Not every failure should be retried:

| Scenario | Retry within one request? | Reason |
| --- | --- | --- |
| `active=false` | **No** | AS already determined the token is rejected. |
| Audience/issuer mismatch | **No** | Token failed policy. |
| Missing scope | **No** | Retrying introspection will not grant missing scopes. |
| HTTP 401 due to bad introspection client secret | Usually **no** | Fix credentials/registration; retrying is futile. |
| HTTP 429 | Possibly, respecting `Retry-After` and tight limits | Avoid overloading the AS further. |
| Transient timeout/503 | Possibly, very bounded | SLA and endpoint idempotency must permit it. |
| TLS validation failure | **No** by default | Never bypass TLS; investigate trust/config. |

A rough sketch:

```java
return delegate.introspect(token)
        .retryWhen(Retry.backoff(
                2, Duration.ofMillis(100))
                .filter(this::isKnownTransientDependencyError));
```

`isKnownTransientDependencyError` is an application method that must **strictly allowlist retryable network/transient errors**—never something broad like `error instanceof RuntimeException`. Retries require an overall time budget, jitter/backoff, concurrency caps, and rate monitoring.

**Never retry by switching issuers or resource endpoints** just because a token was rejected at the configured endpoint.

## 16. Caching Introspection Results and Staleness Risk

Introspection lets the Resource Server ask the AS about the token's live status. Caching can improve latency, at the cost of accepting tokens after revocation or privilege changes.

### 16.1. Never Cache a Single Shared Mono Across All Tokens

Wrong example:

```java
// WRONG: shared publisher for token A reused for token B.
private Mono<OAuth2AuthenticatedPrincipal> sharedPrincipal =
        delegate.introspect("token-A").cache();

@Override
public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
    return sharedPrincipal;
}
```

Every caller would receive **token A's principal**. This is a critical security vulnerability.

Even when caching per token, ensure:

- Cache keys never expose raw tokens in logs or metrics.
- Keys isolate issuer, resource, introspection client registration, policy version, and tenant trust context.
- TTL never exceeds `exp`/lifetime or the revocation SLA.
- Explicit strategies exist for `active=false`, AS errors, and policy changes.
- Cache eviction, concurrency, and stampede protection are handled.
- Expired cached results are never used to fail open during outages.

### 16.2. Where in the Pipeline Should Caching Sit?

In principle:

```text
Raw token
   -> remote introspection -> active principal
   -> validate audience/issuer/token contract
   -> cache verified result with bounded TTL
   -> authorization checks on current request/resource
```

Caching **before** audience/issuer policies risks sharing principals across trust contexts without resource-specific validation. Caching **after** custom validation requires cache keys/TTLs to account for policy versions.

There is no single default TTL suitable for all systems. Sensitive APIs may forbid caching; APIs with flexible revocation SLAs may approve short-lived caches after review.

### 16.3. `Mono.cache(Duration)` Does Not Replace Token Cache Design

`Mono.cache(Duration)` caches signals **for one specific publisher instance**. Using it within a single request chain can prevent duplicate subscriptions to that publisher, but it does not build a safe cache keyed by token/issuer/resource. Furthermore, error caching and cancellation semantics must be well understood.

Never assume a class-field `cache()` is safe across multiple Bearer tokens.

## 17. Composition Must Preserve Access-Token Boundaries

In an OIDC ecosystem, there may be:

- **OIDC ID tokens** meant for client login.
- **OAuth 2.0 access tokens** meant for Resource Servers.
- **Refresh tokens** used by clients to obtain new access tokens.
- **Client assertions** used to authenticate an OAuth client to the AS.

The introspector should accept only the **token type agreed upon by the AS and Resource Server**. Never infer from `active=true` that every token type is a valid API access token.

If the AS returns claims distinguishing `token_type`, `aud`, `client_id`, or token profiles, the API may validate them in a decorator/contract. Exact claim names and values depend on the issuer; do not invent requirements the AS does not provide.

### 17.1. JWT-Formatted Tokens Can Still Be Introspected

An AS may issue JWS JWT access tokens while also providing introspection to enforce revocation. When a Resource Server configures `opaqueToken()`, it sends the **JWT string** to the AS for verification; this path does not invoke `ReactiveJwtDecoder` by default.

Never branch by token shape:

```java
// WRONG: token syntax does not prove trust contract.
if (token.split("\\.").length == 3) {
    return jwtDecoder.decode(token)
            .map(jwt -> createOpaquePrincipal(jwt));
}
```

If a system genuinely needs both local JWT validation and introspection, define ordering, issuers, audiences, failure semantics, and who authorizes tokens explicitly. Never skip introspection merely because a token "looks like a JWT."

## 18. Scope Authorization After the Introspector Accepts the Token

Suppose the AS returns:

```json
{
  "active": true,
  "sub": "user-123",
  "scope": "orders:read orders:export",
  "aud": ["orders-api"]
}
```

After mapping:

```text
Authentication: BearerTokenAuthentication
Authorities:    SCOPE_orders:read
                SCOPE_orders:export
```

With endpoint rules:

```java
.authorizeExchange(exchanges -> exchanges
        .pathMatchers(HttpMethod.GET, "/api/orders/**")
            .hasAuthority("SCOPE_orders:read")
        .pathMatchers(HttpMethod.POST, "/api/orders/**")
            .hasAuthority("SCOPE_orders:write")
        .anyExchange().authenticated())
```

GET requests with `SCOPE_orders:read` can proceed, while POST requests requiring `SCOPE_orders:write` are rejected.

**Never infer** that `orders:export` implies `orders:read`, or that any `orders:` prefix grants all actions. Permission relationships exist only if explicitly defined by the issuer/API contract.

### 18.1. 401 Differs from 403

| Scenario | Authentication | Authorization | Typical HTTP status |
| --- | --- | --- | --- |
| No Bearer token sent | No principal | Endpoint requires login/token | **401**. |
| AS returns `active=false` | Failed | Does not reach business layer | **401 invalid_token**. |
| Active token with wrong `aud` per decorator | Failed | Does not reach business layer | **401 invalid_token**. |
| Active token, right audience, missing `orders:write` | Succeeded | Insufficient authority | **403 Forbidden**. |
| Active token, valid scope, order belongs to another tenant | Succeeded | Domain policy denies | **403/404** per API contract. |
| AS timeout / bad credentials | Token unverified | No privileges granted | Fail-closed; handler/config determines 401/5xx. |

Status codes in the table are typical outcomes, not guaranteed identical responses across every gateway/handler.

## 19. Object-Level Authorization Belongs in the Business Layer

Reading an order by ID:

```java
@Service
public final class OrderService {

    private final ReactiveOrderRepository orders;
    private final ReactiveCurrentActor currentActor;

    public OrderService(
            ReactiveOrderRepository orders,
            ReactiveCurrentActor currentActor) {
        this.orders = orders;
        this.currentActor = currentActor;
    }

    @PreAuthorize("hasAuthority('SCOPE_orders:read')")
    public Mono<OrderDto> getOrder(UUID orderId) {
        return currentActor.getAuthorizedActor()
                .flatMap(actor -> orders
                        .findByIdAndOwnerIdAndTenantId(
                                orderId,
                                actor.userId(),
                                actor.tenantId()))
                .map(OrderDto::from);
    }
}
```

`ReactiveOrderRepository`, `ReactiveCurrentActor`, and `OrderDto` are **hypothetical domain types**. Method security in WebFlux requires `@EnableReactiveMethodSecurity` and invocation through a Spring proxy; the repository must enforce tenant/owner predicates per policy.

Here:

- **Introspector** confirms the access token is active, targets the right audience, and has valid principal metadata.
- **Method security** enforces `SCOPE_orders:read`.
- **Reactive repository** fetches only records belonging to the authenticated actor/tenant.

This keeps responsibilities cleanly separated without forcing the introspector to know every request's resource IDs.

## 20. Multi-Issuer and Multiple Introspection Delegates

An API may need to accept tokens issued by multiple Authorization Servers. Using a single introspection endpoint and secret across all issuers often breaks contracts.

Example:

```text
Trust domain A:
  issuer: https://idp-a.example.test/issuer
  introspection: https://idp-a.example.test/introspect
  client credentials: resource-A

Trust domain B:
  issuer: https://idp-b.example.test/issuer
  introspection: https://idp-b.example.test/introspect
  client credentials: resource-B
```

**Never let clients pick the delegate via arbitrary headers**:

```java
// WRONG: attacker redirects introspection credentials to an arbitrary endpoint.
String target = exchange.getRequest()
        .getHeaders().getFirst("X-Introspection-Uri");
return newRemoteIntrospector(target, resourceServerSecret);
```

In multi-issuer applications, choose based on **trusted configuration**, such as specific route/API contracts or managed registrations. If an unverified `iss` hint is ever inspected to pick a candidate, treat it purely as a **routing hint**, validate it against an allowlist, and confirm via trusted introspection.

### 20.1. Do Not Fall Back After an AS Rejects a Token

Dangerous example:

```java
return issuerA.introspect(token)
        .onErrorResume(error -> issuerB.introspect(token));
```

If issuer A rejected a token, trying issuer B with a different trust policy risks token confusion or creates a token-probing oracle across endpoints. If a migration genuinely requires multiple issuers, design routing contracts, client/resource isolation, and negative tests explicitly—never turn **every** authentication error into a fallback.

### 20.2. Use Separate `SecurityWebFilterChain` Beans When Appropriate

When there are two distinct API groups:

```text
/api/partner-a/** -> introspection credentials and policy A
/api/partner-b/** -> introspection credentials and policy B
```

you can define separate `SecurityWebFilterChain` beans with appropriate matchers/order and introspectors. Remaining routes should have a safe default policy. Test JWT/opaque/partner tokens against the wrong routes to ensure they are not accepted by a looser chain.

## 21. Protecting the Resource Server's Credentials

An introspection request contains **two sensitive credentials**:

1. The caller's access token sent in the `token=...` body.
2. The Resource Server's credential for calling the AS, such as Basic client secret, mTLS private key, or private-key JWT client assertion.

They have different lifecycles and owners:

| Credential | Held by | Purpose |
| --- | --- | --- |
| Bearer access token | OAuth client and Resource Server during request handling | Access the API with granted permissions. |
| Introspection client ID/secret | Resource Server / secret manager | Prove the Resource Server is permitted to query the AS. |
| mTLS client certificate/private key | Resource Server | Client authentication to the AS when required by registration. |
| AS JWT signing private key | Authorization Server | Sign JWTs; not a secret for calling introspection. |

**Never log** Bearer headers, Basic headers, raw `token` form values, private keys, or full introspection responses.

### 21.1. Secret Rotation and Decorators

When a client secret rotates in the secret manager, a delegate bean created from `@Value` at startup may **still hold the old secret**. A decorator does not automatically make the HTTP client reload credentials.

Options:

- Rolling redeploy/restart to instantiate a new delegate with the new credential.
- Swapping the delegate via a controlled reference once the new credential is verified.
- Having the AS allow two active secrets/registrations during an overlap window before revoking the old one.

If the AS allows only one active secret, a rolling update does not automatically guarantee zero downtime. Use blue-green client registrations or a coordinated cutover. Never leave a suspected-compromised secret active just to avoid introspection errors.

### 21.2. Never Hardcode Secrets or Unverified Endpoints

The introspection URL must remain pinned to trusted deployment configuration; TLS/mTLS must be strictly verified. Never pull endpoints from Bearer tokens, query strings, or unverified issuers.

## 22. Testing the Decorator with `StepVerifier`

Because `ReactiveOpaqueTokenIntrospector` returns `Mono`, **Reactor Test `StepVerifier`** is ideal for verifying exact success/error/empty paths without a real AS.

### 22.1. Setting Up Fake Principals and a Fake Delegate

```java
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class AudienceCheckingIntrospectorTest {

    private static OAuth2AuthenticatedPrincipal principal(String aud) {
        return new DefaultOAuth2AuthenticatedPrincipal(
                "user-123",
                Map.of(
                        "sub", "user-123",
                        "aud", List.of(aud),
                        "scope", "orders:read"),
                List.of(new SimpleGrantedAuthority(
                        "SCOPE_orders:read")));
    }

    @Test
    void acceptsMatchingAudience() {
        ReactiveOpaqueTokenIntrospector remote =
                token -> Mono.just(principal("orders-api"));

        ReactiveOpaqueTokenIntrospector decorated =
                new AudienceCheckingIntrospector(remote, "orders-api");

        StepVerifier.create(decorated.introspect("fake-token"))
                .expectNextMatches(p ->
                        "user-123".equals(p.getName())
                        && p.getAuthorities().stream().anyMatch(a ->
                                "SCOPE_orders:read"
                                        .equals(a.getAuthority())))
                .verifyComplete();
    }

    @Test
    void rejectsWrongAudience() {
        ReactiveOpaqueTokenIntrospector remote =
                token -> Mono.just(principal("payments-api"));

        ReactiveOpaqueTokenIntrospector decorated =
                new AudienceCheckingIntrospector(remote, "orders-api");

        StepVerifier.create(decorated.introspect("fake-token"))
                .expectError(BadOpaqueTokenException.class)
                .verify();
    }

    @Test
    void doesNotTurnRemoteFailureIntoSuccess() {
        ReactiveOpaqueTokenIntrospector remote =
                token -> Mono.error(
                        new BadOpaqueTokenException("inactive"));

        ReactiveOpaqueTokenIntrospector decorated =
                new AudienceCheckingIntrospector(remote, "orders-api");

        StepVerifier.create(decorated.introspect("fake-token"))
                .expectError(BadOpaqueTokenException.class)
                .verify();
    }

    @Test
    void emptyDelegateMustFailClosed() {
        ReactiveOpaqueTokenIntrospector remote =
                token -> Mono.empty();

        ReactiveOpaqueTokenIntrospector decorated =
                new AudienceCheckingIntrospector(remote, "orders-api");

        StepVerifier.create(decorated.introspect("fake-token"))
                .expectError(BadOpaqueTokenException.class)
                .verify();
    }
}
```

These tests verify **decorator logic**, not that the remote introspector sends an HTTP POST, authenticates Basic credentials, or parses `active=false`. `fake-token` is only a unit-test placeholder.

### 22.2. Verifying Introspection Invocation Count

A fake delegate using `Mono.defer`:

```java
AtomicInteger calls = new AtomicInteger();

ReactiveOpaqueTokenIntrospector remote = token ->
        Mono.defer(() -> {
            calls.incrementAndGet();
            return Mono.just(principal("orders-api"));
        });

ReactiveOpaqueTokenIntrospector decorated =
        new AudienceCheckingIntrospector(remote, "orders-api");

StepVerifier.create(decorated.introspect("test-token"))
        .expectNextCount(1)
        .verifyComplete();

assertEquals(1, calls.get());
```

`assertEquals` comes from JUnit Jupiter. This test verifies **one subscription** triggers one delegate invocation in the simple case. If subscriptions are intentionally repeated or retries occur, invocations may be higher; define the contract accordingly.

### 22.3. Verifying No Side Effects Before Subscription

Using the fake delegate above:

```java
Mono<OAuth2AuthenticatedPrincipal> publisher =
        decorated.introspect("test-token");

assertEquals(0, calls.get());

StepVerifier.create(publisher)
        .expectNextCount(1)
        .verifyComplete();

assertEquals(1, calls.get());
```

This is a standalone example assuming `calls` starts at 0 before the test. It demonstrates the **lazy** nature of `Mono.defer` and helps catch premature self-subscription in implementations.

## 23. Testing the Wire Protocol with a Mock Introspection Server

Unit tests with a fake `ReactiveOpaqueTokenIntrospector` do not verify the HTTP layer. If your project customizes client credentials, timeouts, or AS response mapping, add a test using a **mock HTTP server** like WireMock or MockWebServer:

1. Point the delegate to the trusted mock introspection URI.
2. Send a test token through `delegate.introspect(...)` or the WebFlux filter chain.
3. Assert a **POST** request with `Content-Type: application/x-www-form-urlencoded`.
4. Assert the form carries the expected `token` and HTTP client authentication matches the contract.
5. Mock `{"active":true,"aud":["orders-api"],"scope":"orders:read"}` → principal accepted by decorator.
6. Mock `{"active":true,"aud":["payments-api"]}` → decorator rejects.
7. Mock `{"active":false}` → delegate/introspector rejects; no principal created.
8. Mock HTTP 401 from AS due to bad introspection credentials → classify as **client authentication failure**, not inactive user token.
9. Mock timeout/503/malformed JSON → no authenticated principal created.
10. Assert logs, headers, and responses contain no test token or secret markers.

**Never use production access tokens or production client secrets.** Generate dedicated test credentials for the test environment.

### 23.1. Why Test Basic Auth Encoding?

Introspection client IDs/secrets can contain `+`, `:`, `%`, or `/`. If one layer percent-encodes credentials and the builder/HTTP client encodes them a second time, the AS can return HTTP 401 even though the secret is logically right.

Use the builder/HTTP client matching your **Spring Security version**, pass raw credentials where required by the API, and verify the wire format at the mock AS. Never log Basic Authorization headers just to debug encoding.

### 23.2. AS HTTP 401 Differs from API HTTP 401

```text
AS -> Resource Server: HTTP 401 (introspection client rejected by AS)
Resource Server -> OAuth client: HTTP 401/5xx per safe handler
```

These two HTTP statuses occur on **two different requests/hops**. If the AS returns 401 after secret rotation, do not record "all user tokens revoked" in audit logs. Investigate the Resource Server's credentials and registration.

## 24. WebTestClient Testing 401 and 403 Through the WebFlux Filter Chain

To test the entire HTTP flow, use **`WebTestClient`** with the real `SecurityWebFilterChain` and a controlled mock delegate or mock AS.

Sketch example:

```java
webTestClient.get()
        .uri("/api/orders")
        .header(HttpHeaders.AUTHORIZATION,
                "Bearer active-read-token")
        .exchange()
        .expectStatus().isOk();

webTestClient.get()
        .uri("/api/orders")
        .header(HttpHeaders.AUTHORIZATION,
                "Bearer active-no-scope-token")
        .exchange()
        .expectStatus().isForbidden();

webTestClient.get()
        .uri("/api/orders")
        .header(HttpHeaders.AUTHORIZATION,
                "Bearer inactive-token")
        .exchange()
        .expectStatus().isUnauthorized();
```

**Assuming** the test environment configured the introspector/mock AS to return those three cases and the endpoint returns 200 when authorized. This illustrates a test pattern, **not observed execution output**.

When using `WebTestClient.bindToApplicationContext(...)`, configure Spring Security Test integration properly, typically via the `springSecurity()` configurer. With a live `RANDOM_PORT` server, test mutators behave differently; pick the mode fitting your goal of testing the real filter.

### 24.1. `mockOpaqueToken()` Does Not Test Introspection

Spring Security Test for WebFlux provides `mockOpaqueToken()` to inject a simulated Authentication:

```java
webTestClient.mutateWith(
        mockOpaqueToken().authorities(
                new SimpleGrantedAuthority("SCOPE_orders:read")))
        .get()
        .uri("/api/orders")
        .exchange()
        .expectStatus()
        .isOk();
```

This is great for testing **authorization rules**, yet **does not prove** `ReactiveOpaqueTokenIntrospector` or your decorator ran. To genuinely test audience validation, send a Bearer header through the filter so the delegate/mock AS is actually invoked.

### 24.2. Integration Test Matrix

| Case | Remote introspection | Decorator | Expected HTTP |
| --- | --- | --- | --- |
| Missing token | AS not called | Does not run | 401 for protected APIs. |
| Active token, `aud=orders-api`, has read scope | Valid principal | Pass | 2xx if domain allows. |
| Active token, `aud=payments-api`, has read scope | Valid principal | Deny | 401 invalid_token per handler. |
| Active token missing required `aud` | Valid principal | Deny | 401. |
| Active token, right audience, missing read scope | Valid principal | Pass | 403 from authorization. |
| Active token, valid scope, wrong owner/tenant | Valid principal | Pass | 403/404 from domain policy. |
| Inactive token | `active=false` | Should not run policy on principal | 401. |
| Remote introspector returns `Mono.empty()` | Empty | Fail-closed | Authentication failure, never 2xx. |
| Remote introspection timeout | Error | No principal created | Safe error per handler, e.g. 5xx/503. |
| AS returns 401 due to bad introspection client secret | HTTP error | No principal created | Safe error, internal log classifies credential issue. |
| Claim `tenant_id` is an object instead of string | Valid principal | Deny per schema | 401 if checked during authentication. |
| Attempting to send JWT to opaque endpoint | AS decides per contract | No auto-switching | Rejected unless allowed by AS/token profile. |

## 25. Reactor Context, Cancellation, and Request Deadlines

In WebFlux, the security context typically propagates via the **Reactor Context**:

```java
Mono<Authentication> current =
        ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication);
```

During introspection, the filter is attempting to **establish Authentication**, so never assume a trusted principal already exists in `ReactiveSecurityContextHolder` for the same request before token verification completes.

### 25.1. Never Read the "User" from Context Before Authentication

A header like `X-User-ID`, query parameter `tenant`, or Reactor Context populated by custom middleware **does not prove identity** before the trust boundary verifies it.

When policy needs an actor, extract it from the `OAuth2AuthenticatedPrincipal` returned by introspection and validate external identity mapping per contract—never grant permissions from caller-supplied inputs.

### 25.2. Cancellation Does Not Mean an Invalid Token

A client may cancel a request mid-introspection. When the Reactor pipeline cancels, `doFinally` receives a cancel signal. Never audit "invalid token" or lock an account merely because a request was canceled.

HTTP clients and resources must handle cancellation, timeouts, and connection cleanup properly. Unbounded `retryWhen` or `cache` operators can keep network requests alive longer than needed.

## 26. Distinguishing an Introspector Decorator from an Authentication Converter

In Spring Security, there are two customization layers:

1. **Introspector decorator**: takes the raw token, calls the remote introspector, validates/transforms `OAuth2AuthenticatedPrincipal`.
2. **Authentication converter** on the manager (where supported by version): takes the introspected principal/metadata and builds an appropriate `Authentication`, potentially customizing authorities or principal representation.

The two layers are not complete substitutes for each other:

| Goal | Appropriate place |
| --- | --- |
| Enforce access-token issuer/audience/metadata | Introspector decorator (before creating Authentication). |
| Observe latency and remote introspection errors | Around the delegate, without logging tokens/secrets. |
| Restrict raw principal attributes per contract | Decorator with careful handling. |
| Formally map principal/authorities into a custom Authentication type | Authentication converter per supported contract. |
| Check owner/tenant of `orderId` | Method/domain authorization or repository query. |
| Verify a JWT signature locally | `ReactiveJwtDecoder`, **not** an opaque decorator. |

**Avoid configuring authority mapping in both layers** without clear precedence. One layer might filter privileges while the next layer re-adds them from raw `scope`, undermining the original policy.

## 27. Common Anti-Patterns

### 27.1. Writing a Fake Delegate That Always Returns a Principal

```java
ReactiveOpaqueTokenIntrospector insecure =
        token -> Mono.just(adminPrincipal);
```

Without a trusted token verification source, every string sent by a client becomes admin. Keep fakes strictly inside **dedicated test contexts**, never production.

### 27.2. Using `onErrorResume` to Accept Tokens on AS Timeout

```java
delegate.introspect(token)
        .onErrorResume(error -> Mono.just(lastKnownAdmin));
```

This is fail-open. Propagate the error or map it to a dependency error handled safely.

### 27.3. Using `filter` and Treating Empty as Authenticated

`filter` drops failing principals by turning them into empty. An authentication pipeline must represent rejection with **`Mono.error`** and test negative paths.

### 27.4. Self-Subscribing Inside `introspect()`

`subscribe()` breaks framework control over outcomes/errors and easily triggers redundant network calls. Return the `Mono` pipeline to the manager.

### 27.5. Blocking HTTP/JDBC Inside `map`

`map` does not make synchronous code non-blocking. Use reactive I/O or a bounded adapter for legacy blocking dependencies.

### 27.6. Selecting the Introspection URI from Untrusted Input

Creates SSRF risks or leaks the client secret to an attacker's host. Endpoints and credentials must come from trusted configuration.

### 27.7. Confirming `active=true` and Ignoring `aud`

An active token may belong to another resource. Enforce resource binding via the introspection contract, or rely on verified equivalent AS guarantees.

### 27.8. Granting Roles Based on Email or Display Name

Emails and names can change or collide. Never substitute them for contracted external identities; never grant `ROLE_ADMIN` by guessing from strings.

### 27.9. Caching One Shared `Mono` Across All Requests

Can give user B user A's principal. Caches require proper keys, trust-context isolation, TTL, and revocation analysis.

### 27.10. Retrying Inactive or Wrong-Audience Errors

The AS already rejected the token or local policy detected a mismatch. Retrying only adds load and risks bypasses if falling back to another issuer.

### 27.11. Testing Only with `mockOpaqueToken()`

Mock Authentication bypasses both the remote introspector and decorators. You need `StepVerifier` tests for decorators plus integration tests exercising the HTTP Bearer filter path.

### 27.12. Returning `exception.getMessage()` to Clients

Introspection errors can contain the AS URL or client registration details. Responses should use minimal RFC 6750 Bearer errors without leaking tokens, secrets, or stack traces.

## 28. Practical Scenarios

### Scenario A — Blocking Tokens Meant for Another API

The AS returns `active=true` for a token with `aud=["payments-api"]`. `AudienceCheckingIntrospector` emits `BadOpaqueTokenException`. The API creates no principal for `orders-api` even if the token shares similar scope names.

### Scenario B — Restricting Authorities

The AS returns `orders:read orders:export tenant:admin`, while the API permits only the first two scopes. A decorator can filter authorities via an allowlist. However, clarify how other role/factor authorities are mapped so intentional security policies are not lost.

### Scenario C — Identity Belonging to Another Tenant

The token is active with the right audience, yet the user does not belong to `orderId`'s tenant. The decorator passes the token contract; the **reactive order query** enforces tenant/ownership and never returns unauthorized records.

### Scenario D — AS Returns an Empty Publisher

A buggy custom delegate returns `Mono.empty()`. The decorator uses `switchIfEmpty(Mono.error(...))` so it never silently treats the token as verified.

### Scenario E — Introspection Secret Rotated

The AS rejects the old Basic credential with HTTP 401. The decorator creates no principal, and internal logs record `INTROSPECTION_CLIENT_AUTH_FAILURE`. Ops rotates the secret/delegate properly without falsely assuming every user's access token was revoked.

### Scenario F — Introspection Timeout

The HTTP call exceeds the SLA and `timeout` emits an error. The API fails closed, granting no "temporary" principal. Circuit breakers/retries may only be used if they preserve authentication semantics and stay within a time budget.

### Scenario G — Migrating Between Two Issuers

Two issuers have distinct credentials and audiences. Select the delegate via trusted route/client-registration configuration or an allowlist, then enforce the resource contract. Never switch delegates using unverified token payloads or fall back across all errors.

### Scenario H — Tests Pass, Production Lacks Authority

A `mockOpaqueToken()` test supplies `SCOPE_orders:read` and gets 200; production introspection returns `scope="profile"`, resulting in 403. Test real remote principal/authority mapping with a mock AS and verify scope policies.

## 29. Self-Check Questions

**1. What does `ReactiveOpaqueTokenIntrospector` return?** `Mono<OAuth2AuthenticatedPrincipal>`, not a synchronous principal.

**2. Why prefer a decorator over rewriting HTTP introspection?** It preserves protocol handling, client authentication, and `active` checks from a trusted implementation, adding only the needed policies.

**3. How do `map` and `flatMap` differ in composition?** `map` synchronously transforms an element; `flatMap` chains a step that returns a `Mono` publisher into the pipeline.

**4. When the AS returns `active=false`, should the decorator emit an empty principal to let the API continue?** No. Always fail closed.

**5. Is `Mono.empty()` a valid successful authentication result?** No. For token introspection, convert unexpected empty results into an explicit error.

**6. Why can `filter` on a principal be hard to diagnose?** Because a failing element becomes an empty publisher with no explicit failure category.

**7. Is an active token automatically valid for every API?** No. Enforce audience/resource binding or an equivalent AS guarantee.

**8. Does `scope` replace order ownership checks?** No. `SCOPE_orders:read` does not prove a user owns every order.

**9. Why not use email as a default identity key?** Emails can change or be reassigned; rely on a subject/issuer contract and internal identity mapping.

**10. Can you call `.block()` inside a WebFlux introspector?** No. It can block the event loop and break reactive execution.

**11. When introspection times out, may we fall back to an admin principal?** No. That is fail-open privilege escalation.

**12. What is the risk of caching a shared `Mono` in a field?** Subsequent tokens can receive a prior token's principal; caches must isolate keys, trust context, and TTL.

**13. Why is retrying `active=false` pointless?** The AS already determined the token is rejected; retrying will not make it valid under policy.

**14. Which cases should be tested with `StepVerifier`?** Matching/mismatched audience, delegate errors, empty publishers, signal propagation, and delegate invocation counts.

**15. Does `mockOpaqueToken()` prove HTTP introspection ran?** No. It creates a mock Authentication for authorization tests.

**16. How do an AS HTTP 401 and an API HTTP 401 differ?** An AS 401 may mean bad introspection client credentials; an API 401 usually means the caller's Bearer credential was rejected.

**17. Where should database lookups checking permissions on `orderId` live?** In reactive authorization/service/repository layers—not forced into the introspector.

**18. Why forbid callers from sending `X-Introspection-Uri`?** It is untrusted input that enables SSRF and leaks Resource Server credentials.

**19. When composing multiple policies, how do you ensure all are enforced?** Chain steps with `flatMap`, return the principal only after every step succeeds, and write negative tests for each condition.

**20. What is safe to log during composition?** Correlation IDs, result categories, latencies, and low-cardinality labels—never raw Bearer tokens, Basic secrets, or full introspection responses.

## 30. References

- **RFC 7662 — OAuth 2.0 Token Introspection**: `active` rules, response metadata, and protecting the introspection endpoint. https://www.rfc-editor.org/rfc/rfc7662
- **RFC 6750 — OAuth 2.0 Bearer Token Usage**: Bearer transport and `invalid_token`, `insufficient_scope` errors. https://www.rfc-editor.org/rfc/rfc6750
- **RFC 6749 — OAuth 2.0 Authorization Framework**: client authentication and scopes. https://www.rfc-editor.org/rfc/rfc6749
- **Spring Security Reference — Reactive OAuth2 Resource Server Opaque Token**: https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html
- **Spring Security API — ReactiveOpaqueTokenIntrospector**: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/ReactiveOpaqueTokenIntrospector.html
- **Spring Security API — SpringReactiveOpaqueTokenIntrospector**: consult the Javadoc matching your project's Spring Security dependency.
- **Spring Security API — OpaqueTokenReactiveAuthenticationManager**: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/OpaqueTokenReactiveAuthenticationManager.html
- **Spring Security Reference — WebFlux Security**: https://docs.spring.io/spring-security/reference/reactive/index.html
- **Spring Security Reference — WebFlux Testing**: https://docs.spring.io/spring-security/reference/reactive/test/index.html
- **Project Reactor Reference Guide**: `Mono`, `map`, `flatMap`, error handling, scheduling, context, and testing. https://projectreactor.io/docs/core/release/reference/
- **OWASP Logging Cheat Sheet**: reducing credential/PII exposure in logs and tracing. https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html

## 31. Summary

**Customizing an introspector via reactive composition** means keeping a trusted `ReactiveOpaqueTokenIntrospector` as the **delegate**, then using `map`, `flatMap`, `switchIfEmpty`, `doOnError`, `timeout`, and other Reactor operators to enforce additional policies per your **token contract**.

Core pattern:

```java
return delegate.introspect(token)
        .switchIfEmpty(Mono.error(
                new BadOpaqueTokenException(
                        "Introspection did not return a principal")))
        .flatMap(principal ->
                requireAudience(principal, expectedAudience))
        .flatMap(principal ->
                requireIssuer(principal, trustedIssuer))
        .map(MyAuthorityPolicy::restrictAuthorities);
```

This pipeline emits a principal only after **the delegate has accepted the token** and every additional step succeeds. An AS error, audience mismatch, or empty publisher can **never become a valid Authentication**.

When deploying to real WebFlux systems, maintain clear boundaries: **the AS verifies the token is active**, **the decorator enforces issuer/audience/metadata contracts**, **Spring Security checks authorities**, and **the domain layer checks per-resource permissions**. Avoid blocking, fail-open fallbacks, cross-token shared caching, and logging credentials. To safeguard the system, test with **`StepVerifier`**, a **mock introspection HTTP server**, and **`WebTestClient` exercising the real Bearer filter chain**—each tier verifying its own responsibility.
