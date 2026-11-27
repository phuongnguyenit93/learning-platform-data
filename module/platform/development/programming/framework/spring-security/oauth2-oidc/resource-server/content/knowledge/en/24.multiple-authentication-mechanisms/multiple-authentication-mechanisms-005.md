# A Failure in One Strategy Does Not Justify Trying Every Trust Source

## 1. The Problem: Multiple Authentication Methods Does Not Mean Trying Everything Until Something Passes

An API using **Spring Security OAuth 2.0/OIDC Resource Server** sometimes needs to support at the same time:

- JWT Bearer tokens from Authorization Server (AS) A.
- JWT Bearer tokens from AS B.
- Opaque Bearer tokens verified via token introspection.
- HTTP Basic on a restricted operational endpoint.
- OIDC Login + session cookies for a browser UI.
- mTLS, API keys, or identity from a trusted reverse proxy.
- Multiple `SecurityFilterChain` or `SecurityWebFilterChain` beans for different resource areas.

This variety **does not mean** that when a request fails authentication under strategy A, the Resource Server should automatically try B, C, and D until one succeeds.

Example of dangerous logic:

~~~text
Authorization: Bearer TOKEN_X
           |
           v
Verify JWT with trusted issuer A
  -> Signature invalid
           |
           v
Try JWT issuer B
  -> Issuer mismatch
           |
           v
Try introspection at AS C
  -> active=true
           |
           v
Create Authentication and let request proceed
~~~

If the endpoint only allows access tokens from issuer A, the request above **must be rejected**. The fact that AS C recognizes `TOKEN_X` does not qualify it to access issuer A's route.

Central principle:

> **An authentication failure in one strategy is not a signal to expand the trust set. Select an allowed strategy from security policy first, then verify the credential with that strategy; failure does not automatically permit switching strategies.**

This does not forbid supporting multiple methods. It requires that mechanism selection, trust boundaries, credential types, and authorization contracts be **explicitly defined upfront**.

## 2. Distinguishing Not-Applicable, Authentication Failure, Success, and Dependency Failure

Four states to keep separate:

| Logical state | Description | Safe reaction |
|---|---|---|
| **NOT_APPLICABLE** | A mechanism is not meant for this credential or route | Another mechanism may be used **if policy allows** |
| **AUTHENTICATION_FAILURE** | Credential belongs to the selected mechanism but fails verification | Reject; do not try other ASes/providers |
| **AUTHENTICATION_SUCCESS** | Credential passes all conditions of the chosen trust domain | Create Authentication and evaluate permissions |
| **DEPENDENCY_FAILURE** | JWKS, introspection endpoint, TLS, network, or internal credentials errored | Fail closed; never turn into success at another source |

Examples:

~~~text
Request 1:
  /api/orders
  Authorization: Bearer JWT_A
  Strategy contract: issuer A JWT
  Signature invalid
  -> AUTHENTICATION_FAILURE

Request 2:
  /api/legacy/orders
  Authorization: Bearer OPAQUE_B
  Strategy contract: AS B introspection
  active=true
  -> AUTHENTICATION_SUCCESS

Request 3:
  /api/orders
  No Authorization header
  -> No Bearer credential
  -> Protected endpoint typically 401

Request 4:
  /api/orders
  Authorization: Bearer JWT_A
  JWKS A timeout
  -> DEPENDENCY_FAILURE
  -> Do not query JWKS B to rescue the request
~~~

**`NOT_APPLICABLE` is not `AUTHENTICATION_FAILURE`.** Merging both into one fallback branch easily causes the system to accept credentials using an out-of-contract trust domain.

## 3. Trust Selection Must Happen Before Token Acceptance

Three architectural steps:

~~~text
HTTP Request
    |
    v
TRUST SELECTION
  - Route/security zone
  - Permitted credential scheme
  - Trusted issuer/tenant allow-list
  - Gateway-protected metadata if any
    |
    v
AUTHENTICATION
  - JWT: JWS, iss, aud, exp, nbf, typ
  - Opaque: trusted introspection + active + audience
  - Basic: password/credential verification
  - mTLS: trusted certificate chain
    |
    v
AUTHORIZATION
  - Scope/authority
  - Actor kind USER/CLIENT
  - Tenant membership
  - Ownership and business policy
~~~

A request rejected by JWT signature validation must not loop back to **TRUST SELECTION** to try another AS simply because it failed. Trust routing is **policy**, not an exception-guessing algorithm.

### Route and Issuer Have Different Roles

The path `/api/orders` can dictate that **the route trusts only issuer A**. The `iss` claim in a JWT can help route within the group of permitted issuers, yet it is still **unverified**. It must never add a new issuer to the trust list.

### Authentication Success Is Not Authorization Success

An AS may authenticate a valid user, yet the user does not belong to the order's tenant. Authentication produces a trusted principal; authorization can still return 403 or an appropriate domain response.

## 4. Why Is Arbitrary Fallback Dangerous?

Suppose code has this idea:

~~~java
// Pseudo-code of a wrong idea, not complete Java code.
try {
    return validateJwt(token);
}
catch (AuthenticationException ex) {
    return introspectAtAnotherIssuer(token);
}
~~~

Risks:

1. **Downgrade**: a strict JWT validator rejects it, yet another backend applies a looser contract.
2. **Token substitution**: a token issued for API B is accepted at API A.
3. **Issuer confusion**: multiple trusted issuers collapse into one namespace.
4. **Principal confusion**: a single raw credential could map to two different identities.
5. **Credential leakage**: the same token is sent to multiple introspection endpoints unauthorized to receive it.
6. **Network amplification**: an attacker sends invalid tokens causing the RS to call every backend.
7. **SSRF**: if key/metadata URIs come from an unverified JWT, requests can be directed to attacker-controlled addresses.
8. **Hard to audit**: unclear which policy accepted the request.
9. **Availability degradation**: one AS outage triggers cascading retries onto unrelated ASes.
10. **MFA/auth-factor downgrade**: a request fails a higher-factor mechanism and gets accepted by a weaker one.

**Having multiple trust sources does not mean every source is authorized to vouch for every action.**

## 5. Valid Routing Differs from Post-Error Fallback

| Scenario | Right or wrong? | Explanation |
|---|---|---|
| `/api/v2/**` selects JWT upfront | Right | Clear route contract |
| `/api/legacy/**` selects opaque upfront | Right | Clear route contract |
| JWT invalid signature then tries introspection | Wrong unless explicitly permitted by policy | Credential was already rejected by the required strategy |
| Unknown JWT `iss` then creates decoder from that issuer URL | Wrong | Opens caller-controlled trust source |
| JWT issuer A invalid signature then tries issuer B | Wrong | Must not probe keys of another issuer |
| Invalid User Bearer yet session cookie is active | Wrong if route is Bearer-only | Session must not rescue Bearer |
| AS A returns `active=false` then queries all other ASes | Wrong | Hunting for an authority that will accept |
| JWKS A cache holds both old and new keys during rotation | Can be right | Same trust domain, issuer unchanged |
| Using cached JWKS from issuer A while A is temporarily unavailable | Can be right | Trusted key cache still within policy |
| Failover to a replica of the same AS with equivalent TLS and policy | Can be right | Resilience, same authority |
| HTTP Basic for `/ops/**` and JWT for `/api/**` | Right when boundaries are separated | Two mechanisms on distinct routes |
| Endpoint genuinely allows both session and Bearer | Needs explicit design | Must define precedence, CSRF, collision policy |

Not everything containing the word **fallback** is wrong. Distinguish **infrastructure failover within the same trust domain** from **switching to another authority to change the authentication outcome**.

## 6. A Safe Strategy-Selection Step

~~~mermaid
flowchart TD
    A["Request arrives at API"] --> B{"Which trust zone does route belong to?"}
    B -->|"/api/v2/*"| J["JWT issuer A policy"]
    B -->|"/api/legacy/*"| O["Opaque AS B policy"]
    B -->|"/ops/*"| H["Ops Basic/mTLS policy"]
    B -->|"No match"| D["Deny"]
    J --> VJ{"JWT verified?"}
    O --> VO{"Introspection active & valid?"}
    H --> VH{"Ops credential valid?"}
    VJ -->|"No"| F["Reject, no cross-strategy fallback"]
    VO -->|"No"| F
    VH -->|"No"| F
    VJ -->|"Yes"| Z["Scope / domain authorization"]
    VO -->|"Yes"| Z
    VH -->|"Yes"| Z
~~~

This is a **policy diagram**, not a claim that every filter chain runs nodes in the exact same order. Actual APIs/handlers depend on Servlet vs. WebFlux, framework version, and security configuration.

### Routing Signals That Can Be Suitable

- Server-side configured path or security zone.
- Ingress/virtual host routed and verified at a trusted gateway.
- HTTP authentication scheme intentionally accepted by the route.
- Issuer inside a preconfigured allow-list.
- Tenant context verified through a trusted source and cross-checked after authentication.

### Signals Insufficient as Proof of Trust

- Unverified JWT `iss` field.
- `jku`/`x5u` headers containing a caller-supplied JWKS URL.
- Query parameter `provider=...`.
- A JWT token having two dots.
- `X-User`/`X-Role`/`X-Tenant` headers from the Internet bypassing a trusted gateway.
- Payload `scope=admin` before signature verification.

These signals can sometimes serve as **routing hints**, but never as **proof of identity**.

## 7. Spring Security `ProviderManager` May Try the Next Provider

In **Servlet Spring Security**, `ProviderManager` iterates through a list of `AuthenticationProvider` instances to authenticate an `Authentication` request.

Per the API contract:

- `ProviderManager` checks providers that support the `Authentication` type.
- A provider can return an authenticated `Authentication`, return `null`, or throw `AuthenticationException`.
- When a provider succeeds, the Manager normally stops.
- If a provider returns `null`, subsequent providers may be tried.
- **Some `AuthenticationException`s do not stop `ProviderManager` from trying the next provider**; if a later provider succeeds, the earlier provider's error may be ignored.
- For exceptions such as **`AccountStatusException`**, `ProviderManager` stops early.
- If no provider supports it, `ProviderNotFoundException` may occur.
- A parent `AuthenticationManager` may participate per contract when configured.

Therefore, **you cannot assume every `AuthenticationException` always stops `ProviderManager` immediately**.

Common example structure:

~~~java
AuthenticationManager manager =
        new ProviderManager(List.of(
                new JwtAuthenticationProvider(jwtDecoderA),
                new OpaqueTokenAuthenticationProvider(introspectorB)));
~~~

Both providers can support **`BearerTokenAuthenticationToken`**. If the JWT provider fails to authenticate, **do not assume the opaque provider will never be called**. Exact behavior depends on the exception and `ProviderManager` behavior in your version.

### `supports(Class)` Is Not an Issuer Policy

`AuthenticationProvider.supports` states that a provider can handle **an `Authentication` class**, not which issuer or tenant a request is meant for.

Two providers both supporting `BearerTokenAuthenticationToken.class` do not automatically distinguish:

~~~text
Bearer JWT issuer A
Bearer JWT issuer B
Bearer opaque AS C
~~~

If you need **issuer A failure is final**, use a dedicated manager or a resolver selecting one manager, rather than relying on `supports` or provider ordering to enforce security policy.

## 8. Do Not Abuse `null` or Exceptions to "Route"

A custom provider might be written as:

~~~java
@Override
public Authentication authenticate(Authentication authentication) {
    if (isNotMine(authentication)) {
        return null;
    }
    return doAuthenticate(authentication);
}
~~~

If `isNotMine` is determined by a deterministic, permitted routing policy, `null` can indicate the provider does not handle that credential type per contract.

However, if a token was selected for provider A and has an **invalid signature**, never write:

~~~java
catch (BadCredentialsException ex) {
    return null; // Let provider B keep trying.
}
~~~

Doing that turns an authentication failure into **not applicable**, giving `ProviderManager` an opportunity to let another backend accept it.

Nor should you throw a **fake `AccountStatusException`** to force `ProviderManager` to stop: misleading exception semantics make auditing and behavior hard to reason about. Change **composition/routing** instead of using exceptions as a security-policy switch.

## 9. Servlet: `SecurityFilterChain` Separating API and Ops Boundaries

A simple approach uses two routes with distinct authentication contracts:

- **`/api/**`** accepts only Bearer JWTs.
- **`/ops/**`** uses HTTP Basic for the operations zone, as an illustrative example.
- Undeclared paths are denied by default.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SegmentedSecurity {

    @Bean
    @Order(1)
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .csrf(AbstractHttpConfigurer::disable)
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.read")
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain ops(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/ops/**")
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().hasRole("OPS"))
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain remaining(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .anyRequest().denyAll())
                .build();
    }
}
~~~

This is an **example of mechanism selection**, not a complete production config. HTTP Basic must run over TLS with a proper user/password store; ops areas should have network isolation and preferably use SSO/mTLS. CSRF is disabled only in the **purely stateless Bearer** `/api/**` example—never copy that blindly to browser cookie/session endpoints.

### Expected Behavior

~~~text
GET /api/orders
   -> JWT Resource Server policy
   -> JWT invalid: reject
   -> Does not try Basic from /ops

GET /ops/health
   -> Ops Basic policy
   -> Basic invalid: reject
   -> Does not try JWT issuer from /api
~~~

`FilterChainProxy` selects the matching chain by matcher/order; **it does not run chain B when chain A fails**. Also ensure no path is left unprotected due to a wrong matcher.

## 10. Servlet: `AuthenticationManagerResolver` Selecting JWT or Opaque by Route

If an API needs both JWT and opaque Bearer tokens, the Spring Security Reference illustrates `AuthenticationManagerResolver<HttpServletRequest>`.

A resolver with an explicit route policy:

~~~java
import jakarta.servlet.http.HttpServletRequest;

import org.springframework.context.annotation.Bean;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationProvider;
import org.springframework.security.oauth2.server.resource.authentication.OpaqueTokenAuthenticationProvider;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

@Bean
AuthenticationManagerResolver<HttpServletRequest> resourceManagers(
        JwtDecoder jwtDecoder,
        OpaqueTokenIntrospector introspector) {

    AuthenticationManager jwt =
            new ProviderManager(new JwtAuthenticationProvider(jwtDecoder));

    AuthenticationManager opaque =
            new ProviderManager(
                    new OpaqueTokenAuthenticationProvider(introspector));

    AuthenticationManager rejectUnknown = auth -> {
        throw new BadCredentialsException(
                "No allowed strategy for this route");
    };

    return request -> {
        String path = request.getServletPath();

        if (path.startsWith("/api/v2/")) {
            return jwt;
        }
        if (path.startsWith("/api/legacy/")) {
            return opaque;
        }
        return rejectUnknown;
    };
}
~~~

Wire the resolver:

~~~java
@Bean
SecurityFilterChain resourceApi(
        HttpSecurity http,
        AuthenticationManagerResolver<HttpServletRequest> resourceManagers)
        throws Exception {
    return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth ->
                    auth.anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                    oauth2.authenticationManagerResolver(resourceManagers))
            .build();
}
~~~

**Key point:** the resolver selects a manager **before** token validation runs.

- **`/api/v2/`**: if JWT fails, **never** try opaque.
- **`/api/legacy/`**: if opaque fails, **never** try JWT.
- Unknown route: the manager rejects rather than defaulting to the easiest backend.

This is only an example of the trust-routing pattern. With servlet context paths, reverse proxy rewrites, and URL encoding, align route extraction between `securityMatcher` and the resolver. The JWT decoder must verify signature, `iss`, `aud`, time, and token purpose; the opaque introspector must verify `active`, audience/resource contract, and issuer when applicable.

## 11. Invalid JWT Signature Is No Reason to Query Introspection

An anti-pattern:

~~~text
tryJwtDecode(token)
  |
  +-- SUCCESS -> Authenticate
  |
  +-- JwtException -> tryOpaqueIntrospection(token)
                        |
                        +-- active=true -> Authenticate
~~~

If the API requires a JWT validator for that route, the branch above can let a token with an invalid signature/issuer/audience pass via another backend. That **changes the security contract**.

### Is Introspection for JWTs Ever Valid?

Yes. Spring Security opaque-token support can introspect any token string, including JWTs, if the AS supports it. A Resource Server can **deliberately choose introspection upfront** so the AS decides active/revoked status.

Different policies:

~~~text
Policy 1:
  JWT-only validation:
    accepted = signature AND issuer AND audience AND time

Policy 2:
  Introspection-only:
    accepted = trusted introspection says active
               AND resource/token contract

Policy 3:
  JWT verification + revocation check:
    accepted = valid JWT AND positive introspection
~~~

**Policy 2 or 3 is not an automatic fallback when Policy 1 fails.** Choose the policy intentionally. If Policy 3 requires both, use logical **AND**, never OR to rescue an invalid JWT.

### AS Introspection `active=true` Still Needs Resource Contract Checks

An AS may know a token is active, yet the API must verify the token is intended for the current audience/resource if the AS does not perform that check on its behalf. A token active for `billing-api` must not call `orders-api`.

## 12. Multi-Issuer JWT: Trust Only Issuers in the Allow-List

Suppose the Resource Server accepts:

~~~text
Issuer A: https://auth-a.example.com/
Issuer B: https://auth-b.example.com/
~~~

Caller's JWT claims:

~~~json
{
  "iss": "https://attacker.example.net/",
  "sub": "admin",
  "aud": ["orders-api"]
}
~~~

Reading an unverified `iss` and dynamically building a JWT decoder from it is dangerous: an attacker can run their own AS, sign tokens with their key, and make the API trust their JWKS.

Correct design:

~~~text
Unverified iss claim
  is only a routing hint
          |
          v
Configured trusted issuer allow-list
          |
       +--+--+
       |     |
       v     v
     Iss A  Iss B
       |     |
       v     v
   Decoder A Decoder B
       |     |
       v     v
   Verify JWS signature for selected issuer
          |
          v
    Exact iss + aud + exp/nbf + type validation
          |
          v
     Authenticated principal
~~~

A JWT claiming `iss=A` whose signature fails against A's trusted key **must not try B to find a matching key**.

## 13. `JwtIssuerAuthenticationManagerResolver` in Servlet

Spring Security provides **`JwtIssuerAuthenticationManagerResolver`** to select a manager by issuer from a **trusted issuer allow-list**.

~~~java
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerAuthenticationManagerResolver;

JwtIssuerAuthenticationManagerResolver resolver =
        JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
                "https://auth-a.example.com/",
                "https://auth-b.example.com/");
~~~

Apply it:

~~~java
http.oauth2ResourceServer(oauth2 ->
        oauth2.authenticationManagerResolver(resolver));
~~~

This is **selecting an issuer from a trusted set**, not trying A and then B after A fails.

Notes:

- `iss` read from the JWT before verification is only a routing hint.
- Only issuers in the allow-list get a manager/decoder.
- Each decoder must verify the signature and **that exact `iss`**.
- Audience and access-token profile need appropriate validators.
- The Resource Server must not link subjects just because `sub` values match.
- `fromTrustedIssuers` is supported in applicable Spring Security versions; check the API if using an older release.

### Do Not Merge `kid` Across Issuers

Two issuers can share `kid=signing-2026` with different public keys. `kid` has meaning only inside the selected issuer's trusted JWKS. Never use `kid` as the key of an un-namespaced global cache.

## 14. WebFlux: `JwtIssuerReactiveAuthenticationManagerResolver`

In **Spring Security WebFlux**, use the reactive resolver, not the `HttpServletRequest`-based API.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerReactiveAuthenticationManagerResolver;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveTrustedIssuers {

    @Bean
    SecurityWebFilterChain resourceApi(ServerHttpSecurity http) {
        JwtIssuerReactiveAuthenticationManagerResolver resolver =
                JwtIssuerReactiveAuthenticationManagerResolver
                        .fromTrustedIssuers(
                                "https://auth-a.example.com/",
                                "https://auth-b.example.com/");

        return http
                .authorizeExchange(auth ->
                        auth.anyExchange().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.authenticationManagerResolver(resolver))
                .build();
    }
}
~~~

The WebFlux resolver uses a trusted issuer allow-list. An unknown issuer will not open a new JWKS URL.

### Why Distinguish `Mono.empty` and `Mono.error`?

In the reactive API:

- **`Mono.empty()`** can express no result / not-applicable per a specific contract.
- **`Mono.error(AuthenticationException)`** is a failure.
- **`Mono.just(Authentication)`** is success.

A custom reactive manager must never do:

~~~java
return jwtManager.authenticate(authentication)
        .onErrorResume(ex ->
                opaqueManager.authenticate(authentication));
~~~

**Catch-all `onErrorResume` does not understand security semantics.** It can catch invalid JWTs, JWKS timeouts, config errors, and issuer mismatches and silently switch trust sources. Never use it to build a "try another backend on any error" mechanism.

## 15. WebFlux: Splitting `SecurityWebFilterChain` by Route

Example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

@Configuration
@EnableWebFluxSecurity
public class ReactiveSegmentedSecurity {

    @Bean
    @Order(1)
    SecurityWebFilterChain jwtApi(ServerHttpSecurity http) {
        return http
                .securityMatcher(
                        ServerWebExchangeMatchers.pathMatchers("/api/v2/**"))
                .authorizeExchange(auth ->
                        auth.anyExchange().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain opaqueApi(ServerHttpSecurity http) {
        return http
                .securityMatcher(
                        ServerWebExchangeMatchers.pathMatchers("/api/legacy/**"))
                .authorizeExchange(auth ->
                        auth.anyExchange().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.opaqueToken(Customizer.withDefaults()))
                .build();
    }

    @Bean
    @Order(3)
    SecurityWebFilterChain denyRemaining(ServerHttpSecurity http) {
        return http
                .authorizeExchange(auth ->
                        auth.anyExchange().denyAll())
                .build();
    }
}
~~~

This is an architectural example; configure reactive JWT decoders, opaque introspectors, CORS/CSRF, token profiles, and error handling appropriately.

- JWT route fails: **never switch to the opaque chain**.
- Opaque route fails: **never switch to the JWT chain**.
- Unmatched route: **deny**, never leave open.

**Never use Servlet `HttpSecurity` inside pure WebFlux.** Likewise, a custom `WebFilter` that attaches `Authentication` without verifying credentials can break the security pipeline boundary.

## 16. Opaque `active=false` Must Not Query Every AS to Find `active=true`

RFC 7662 allows an introspection endpoint to return:

~~~json
{
  "active": false
}
~~~

This means the chosen AS **does not confirm the token is active**. It is not an invitation to poll other ASes.

An anti-pattern:

~~~text
AS A introspection:
  active=false
         |
         v
AS B introspection:
  active=false
         |
         v
AS C introspection:
  active=true
         |
         v
Authenticate as principal from AS C
~~~

This can leak Bearer tokens to multiple providers and cause the API to accept credentials from an issuer not allowed for that route.

### Distinguishing Inactive Tokens from Upstream Errors

| AS result | Meaning | Safe action |
|---|---|---|
| 200 + `active=true` | Token active per AS | Proceed to resource/authorization checks |
| 200 + `active=false` | Inactive token | Reject; do not scan other ASes |
| 401 `invalid_client` | RS introspection credentials problem | Fail closed; fix secret |
| 403 | RS not authorized to introspect | Fail closed |
| 429 | AS throttling | Backoff/rate-limit per policy |
| 5xx | AS unavailable | Fail closed |
| DNS/TLS/timeout | Network/trust dependency error | Fail closed |
| 200 malformed JSON | Protocol failure | Fail closed |

An HTTP 401 from the AS on the **Resource Server -> AS hop** does not mean the caller's token on the **Client -> Resource Server hop** expired. Separate the two error sources.

## 17. Fail Closed Does Not Mean Every Error Is 401

**Fail closed** means a protected operation must not execute without valid authentication and authorization.

| Cause | Typical HTTP | Did authentication succeed? |
|---|---|---|
| Protected route missing Bearer | 401 challenge | No |
| Wrong JWT signature/issuer/audience | 401 `invalid_token` | No |
| Expired JWT | 401 `invalid_token` | No |
| Opaque introspection `active=false` | 401 `invalid_token` | No |
| Malformed Bearer transport | 400/401 depending on resolver error | No |
| Valid token missing scope | 403 `insufficient_scope` when appropriate | Yes |
| Valid token but wrong tenant | 403 or other domain policy | Yes |
| JWKS outage | Dependency failure, possibly 503 per contract | No |
| Introspection timeout | Dependency failure, possibly 503 per contract | No |
| CSRF/CORS/gateway denial | Possibly 403 | Not necessarily |

Do not claim Spring Security always defaults to 503 when an AS is unavailable; behavior depends on exceptions, handlers, and version.

The invariant: **Never return success or mint a fake authenticated principal just because the real authentication mechanism errored.**

## 18. Audience and Token Purpose Prevent Token Substitution

A JWT:

~~~json
{
  "iss": "https://auth.example.com/",
  "sub": "user-42",
  "aud": ["billing-api"],
  "scope": "orders.read",
  "exp": 1794731400
}
~~~

Even with a valid signature, the token must not be used at `orders-api` if `aud` does not contain `orders-api`. Do not route it to another backend with weaker audience checking to let it pass.

**OAuth scopes do not replace audience**, and **`client_id` does not replace `aud`**.

### OIDC ID Tokens Are Not Access Tokens

An OIDC ID token is meant for an OIDC Client / Relying Party. It may share the same issuer/JWKS as an access token while having a different audience and token purpose. A Resource Server must not accept an ID token just because a fallback introspector returns `active=true` when the route requires an OAuth access token.

Token profiles to keep separate:

- OAuth access token, possibly using RFC 9068 `typ=at+jwt`.
- OIDC ID token.
- Refresh token.
- OAuth client assertion.
- Logout token.
- Bearer token intended for another API.

**A wrong-purpose token must not be "rescued" by another authentication strategy.**

## 19. User Identity and Machine Identity Are Not Interchangeable

Two tokens from the same AS:

~~~text
User-delegated token:
  iss = auth.shop
  sub = user-42
  client_id = shop-web
  scope = orders.read

Client-credentials token:
  iss = auth.shop
  client_id = billing-worker
  scope = orders.sync
~~~

With `client_credentials`, a token may lack a human `sub`. If a user endpoint requires `sub` and the token lacks it, do not switch to machine-identity mapping and grant access to user resources.

A separated design:

~~~text
USER actor:
  key = issuer + subject
  delegated client
  tenant/ownership permissions

CLIENT actor:
  key = issuer + client_id
  service permissions
  no implicit human ownership
~~~

**Matching principal names do not merge two trust domains or actor kinds into one.**

## 20. Session Cookies Must Not Silently Rescue Invalid Bearer Tokens

A browser request may simultaneously carry:

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer EXPIRED_TOKEN
Cookie: SESSION=VALID_BROWSER_SESSION
X-Api-Key: PARTNER_KEY
~~~

If `/api/orders` requires Bearer-only, the expired token must be rejected. Neither the session cookie nor the API key is an automatic substitute.

If a route **genuinely** accepts both session and Bearer, the application needs an explicit policy:

1. When Bearer is absent but session exists, is it allowed?
2. When Bearer is invalid and session is valid, reject or pick session?
3. When Bearer user Alice differs from session user Bob, who wins?
4. Must CSRF protection run for cookie-based credentials?
5. Do API responses/`WWW-Authenticate` reflect the right required scheme?
6. Which principal drives authorization?
7. Do cookies/sessions have proper session-fixation and CSRF protections?

Never disable CSRF just because an endpoint can use Bearer if it still accepts ambient browser cookies. Cookie fallback shifts the API's threat model from **explicit Bearer credentials** to **ambient browser credentials**.

## 21. Gateway mTLS and Private Headers Are Not Arbitrary Fallback Sources

A gateway can verify an mTLS client and attach a private identity header for the backend. That is safe only when:

- Internet clients cannot call the backend directly.
- The gateway strips client-sent private headers.
- The gateway sets the header strictly from verified authentication.
- The gateway -> backend connection has a clear trust boundary.
- The backend accepts gateway identity only on defined routes.

Wrong:

~~~text
JWT validation failed
  -> sees X-Verified-User: admin
  -> accepts.
~~~

If the caller sent the header, that is identity spoofing. Even if the header genuinely came from a trusted gateway, it cannot substitute for a user Bearer token on a route requiring user delegation.

Changing credential sources is not just swapping a header name; it changes the **security authority** and **principal semantics**.

## 22. Multiple Credentials in One Request Need a Collision Policy

When a request carries Bearer, Basic, API key, session cookie, or Bearer header + query:

- Credentials may point to **different principals**.
- One security mechanism may run before another.
- One filter may ignore credentials outside its scheme.
- A custom authentication manager may pick a credential after an earlier one fails.

Without explicit API design, a request can be accepted under a different principal than the client expected.

A sound policy:

~~~text
/api/**:
  bearer-only
  invalid Bearer -> reject
  cookie/api-key must not rescue

/browser/**:
  OIDC session
  CSRF and session protections
  Bearer not accepted automatically

/integrations/**:
  mTLS/API key per partner contract
  separate client type/tenant/resource binding
~~~

If a route must support multiple schemes, define precedence, error responses, duplicate handling, and tests for conflicts.

### Duplicate Bearer Token Sources

RFC 6750 recommends not sending a Bearer token via multiple methods in the same request. If the `Authorization` header, `access_token` query parameter, and form field contain different tokens, do not run a "whichever token passes wins" contest. Define a clear resolver/transport policy, typically rejecting credential collisions.

## 23. Selecting by Token Format: Hints Allowed, Never Trusted as Proof

A simple heuristic:

~~~text
Token contains two dots:
  pick JWT verifier.

Token has no dots:
  pick opaque introspection.
~~~

Drawbacks:

- Opaque tokens can contain dots.
- Attackers can craft JWT-shaped strings.
- Does not identify issuer/audience.
- Token shape does not guarantee token type/purpose.
- Format migrations make policy inconsistent.

If the AS issues unambiguous token prefixes by contract, a prefix may be used as a controlled routing hint. **After routing, still verify the entire credential**; a routing hint is not proof of identity.

Without a firm contract, prefer request routes, a trusted issuer allow-list, or metadata verified by a trusted gateway.

## 24. Multi-Tenant: Unverified `iss` and `tenant` Do Not Add Trust Domains

A self-asserted token:

~~~json
{
  "iss": "https://attacker.example.net/",
  "sub": "user-42",
  "tenant_id": "tenant-blue",
  "scope": "orders.admin"
}
~~~

If the API creates decoders dynamically from an arbitrary `iss` or `tenant_id`, attackers can point the API to JWKS they control or inject invalid admin roles.

Proper trust selection:

~~~text
Trusted tenant/route mapping
       |
       v
Issuer allow-list for this tenant
       |
       v
Select issuer-specific verifier
       |
       v
Verify JWS signature + exact iss + aud + time/profile
       |
       v
Map (issuer, sub) to local identity
       |
       v
Verify current tenant membership/resource ownership
~~~

If the organization supports dynamic tenant onboarding, the issuer list must be updated through a **trusted administrative workflow**, never because a request asserted an unknown issuer.

## 25. Migrating from Opaque to JWT Without Error-Based Fallbacks

Suppose clients need to migrate:

~~~text
Phase 1:
  /api/legacy/** uses AS opaque introspection.
  /api/v2/** uses JWT issuer A.

Phase 2:
  Clients migrate to /api/v2 and request audience-matched JWTs.

Phase 3:
  Monitor usage, stop issuing legacy tokens, and retire legacy routes.
~~~

Advantages:

- Each route has a clear authentication contract.
- No "if JWT fails, try opaque" needed.
- You can test the exact backend invoked.
- Clear migration metrics and sunset policies.
- Lower risk of authentication downgrades.

If the same endpoint must accept multiple token formats, use a deterministic resolver with a trusted allow-list/format contract and reject ambiguous cases. Never turn an exception chain into a token-recognition algorithm.

### When Both JWT and Introspection Are Needed

If policy requires JWT signature validation **and** an online revocation check, design:

~~~text
accepted =
  JWT signature/iss/aud/time valid
  AND introspection says active
~~~

Very different from:

~~~text
accepted =
  JWT validation valid
  OR introspection says active
~~~

The OR expression is a downgrade if the organization actually requires both.

## 26. HA Failover Within the Same Trust Domain Can Be Valid

Not every failover is dangerous. An AS may provide two endpoints serving the same token registry:

~~~text
https://introspect-a.auth.example.com/
https://introspect-b.auth.example.com/
~~~

If they are genuinely replicas of the same trust authority with equivalent active policies, client authentication, and resource binding, preconfigured within a trusted network, switching replicas on network failure can be a valid availability strategy.

Conditions:

1. No change of issuer/token authority.
2. Both endpoints have verified TLS trust.
3. Same credentials/policy/audience contract.
4. Bounded timeouts/retries to prevent request storms.
5. `inactive` remains `inactive`—never switch authorities looking for success.
6. Any public-key/token-state caches obey expiration/revocation policies.

**Failover for an AS replica outage differs from querying an independent AS after the first AS rejects a token.**

## 27. Invalid Signature, Issuer, Audience, and Lifetime Never Permit Strategy Hopping

| JWT failure | Meaning | Must not do |
|---|---|---|
| Malformed JWT | Invalid token format | Try Basic/session |
| Signature invalid | Could not verify with trusted key | Try every JWKS issuer |
| Disallowed `alg` | Algorithm policy not met | Enable `HS256`/`none` to fix error |
| `kid` not found | No trusted candidate key | Fetch arbitrary key URL from header |
| Wrong `iss` | Wrong issuer | Try arbitrary issuers |
| Wrong `aud` | Token meant for another API | Try looser introspection |
| Expired `exp` | Expired credential | Rescue request with admin cookie |
| Future `nbf` | Credential not yet active | Inflate clock skew excessively or switch provider |
| Wrong `typ`/token purpose | Not an access token matching profile | Treat ID token as API token |
| Missing scope | Authenticated, insufficient privileges | Look for another provider's account |

These errors must be handled strictly **within the selected strategy**. Even if another backend could decode or recognize the string, it does not necessarily have authority over the endpoint.

## 28. Three Security Zones Scenario

Suppose the architecture is:

~~~text
/api/orders/**
  JWT issuer Shop
  aud=orders-api
  scopes orders.read/orders.write

/api/partner/**
  Opaque introspection of Partner AS
  aud=partner-orders-api
  scope partner.orders.read

/admin/**
  OIDC Login + session cookie
  CSRF protection
~~~

**Scenario A:** Expired Shop JWT calls `/api/orders`. Result is authentication failure; must not try partner AS or admin session.

**Scenario B:** Partner opaque token is mistakenly sent to `/api/orders`. Route still requires Shop JWT; never switch backends automatically.

**Scenario C:** Partner opaque token hits `/api/partner`. Introspection `active=true` but lacks `partner.orders.read`: authentication succeeds, authorization may return 403.

**Scenario D:** Valid OIDC admin session with invalid CSRF on `POST /admin`. CSRF policy rejects; must not try Bearer/API key.

**Scenario E:** Partner introspection times out. Fail closed; do not query Shop AS.

**Scenario F:** Shop AS rotates its signing key. Resource Server refreshes trusted Shop JWKS and verifies the new key. This stays within the same trust domain, not a fallback to Partner.

**Scenario G:** Shop and Partner issuers share `sub=user-42`. The two principals are not automatically the same person; local identity mapping requires `issuer + sub` or trusted account linking.

**Scenario H:** Shop JWT verifies, but tenant membership was revoked. Domain authorization denies; do not search for another credential to elevate privileges.

## 29. Integration Tests Must Prove Unselected Backends Were Not Called

Do not test only the happy path. Negative tests must confirm **other authentication paths did not execute**.

| Test | Expectation |
|---|---|
| `/api/v2` valid JWT | JWT manager used |
| `/api/v2` invalid JWT signature | 401; opaque introspector not called |
| `/api/v2` wrong JWT issuer | 401; unknown issuer JWKS not fetched |
| `/api/v2` wrong JWT `aud` | 401; opaque not tried |
| `/api/v2` expired JWT | 401; session cookie does not rescue |
| `/api/legacy` opaque `active=true` | Opaque introspector used |
| `/api/legacy` opaque `active=false` | 401; JWT decoder not called |
| `/api/legacy` AS timeout | Fail closed; no fallback to JWT |
| Multi-issuer unknown `iss` | Reject; unknown issuer metadata not fetched |
| `iss=A` but JWT signed with key B | Reject; B not tried to rescue A |
| Invalid Bearer + valid cookie | Reject on Bearer-only route |
| Invalid Bearer + valid API key | Reject on Bearer-only route |
| Invalid Basic at `/ops` | Reject; `/api` Bearer not tried |
| Valid JWT, missing scope | 403; account from another provider not used |
| Valid JWT, wrong tenant | Domain denial |
| AS introspection HTTP 401 `invalid_client` | Fail closed, categorized as upstream config error |
| JWKS timeout | Never trust unknown keys |
| Key rotation inside trusted JWKS | Verifies with new trusted key |
| Conflicting multiple credentials | Per collision policy, typically reject |

### Verifying Interactions with Mocks

After an integration test through the filter chain, you can assert:

~~~java
verify(jwtDecoder).decode(anyString());
verifyNoInteractions(opaqueIntrospector);
~~~

With reactive WebFlux, let `WebTestClient` complete the response before verifying interactions. Post-processors like `mockJwt()` build mock `Authentication` without running the real decoder; do not rely on them alone to prove the security pipeline does not fall back.

Tests should cover HTTP status, `WWW-Authenticate`, `Authentication` principal, zero raw token leaks, and backend invocation counts.

## 30. Unit Testing `ProviderManager` Behavior to Avoid Misunderstanding the Framework

A dedicated test can set up two `AuthenticationProvider` fixtures both supporting `BearerTokenAuthenticationToken`:

~~~text
Provider A:
  supports = true
  authenticate -> BadCredentialsException

Provider B:
  supports = true
  authenticate -> authenticated result
~~~

If the framework tries B and the final result succeeds, the test demonstrates that a provider list **is not automatically deny-on-first-error**.

Test these cases separately:

- Provider A returns `null`.
- Provider A throws `BadCredentialsException`.
- Provider A throws `AccountStatusException`.
- Provider A succeeds.
- Parent `AuthenticationManager` is configured.
- Providers both `supports` the same `Authentication` type.

**Never throw a fake `AccountStatusException` to force stopping.** If policy requires a single strategy, use a resolver or chain separation instead of hacking exception classes.

## 31. Reactive Tests: Do Not Confuse `Mono.empty` with `Mono.error`

For a reactive manager:

~~~text
Mono.just(authentication):
  success

Mono.error(authenticationException):
  failure

Mono.empty():
  no result / not-applicable per specific contract
~~~

An anti-pattern:

~~~java
return jwtManager.authenticate(authentication)
        .switchIfEmpty(opaqueManager.authenticate(authentication));
~~~

This can only be valid if **empty genuinely means not-applicable**, and the opaque strategy is permitted by policy on that exact request. If the JWT manager uses empty to hide an invalid credential, this composition is wrong.

Even more dangerous:

~~~java
return jwtManager.authenticate(authentication)
        .onErrorResume(anyError ->
                opaqueManager.authenticate(authentication));
~~~

It can swallow signature errors, issuer mismatches, JWKS outages, and client config errors and switch to another backend. **Catch-all `onErrorResume` does not understand authentication trust boundaries.**

## 32. Auditing the Selected Strategy Without Logging Credentials

Log fields like:

~~~text
requestId = req-472
securityZone = api_v2
selectedAuthStrategy = jwt_issuer_shop
authenticationOutcome = failure
failureCategory = invalid_signature
crossStrategyFallbackCount = 0
status = 401
~~~

Or:

~~~text
requestId = req-473
securityZone = api_legacy
selectedAuthStrategy = opaque_partner
authenticationOutcome = dependency_error
failureCategory = introspection_timeout
crossStrategyFallbackCount = 0
~~~

Never log:

- Raw JWT/Bearer access tokens.
- HTTP `Authorization` headers.
- Introspection client secrets, API keys, or Basic passwords.
- Full token payloads containing PII.
- Raw `iss`/`kid` from unverified tokens as trusted identities.
- Unbounded strings from JWTs as metric labels causing high cardinality.

Use **preconfigured strategy IDs** so metrics keep bounded cardinality.

### Signs of Dangerous Fallback

- JWT signature error yet final status is HTTP 200.
- One request calls multiple independent introspection endpoints.
- Principal ID changes when provider order is flipped.
- Partner token accepted on an admin route.
- API key or session cookie rescues an expired Bearer token.
- During an AS outage, successes through a weaker mechanism spike abnormally.
- Invalid tokens generate outbound load across multiple ASes.
- Logs cannot tell which strategy produced the final `Authentication`.

## 33. Questions to Ask Before Adding a New Mechanism

1. Which route/security zone is allowed to accept this credential?
2. Is the credential read from `Authorization`, cookie, custom header, mTLS, or form/query?
3. Which issuer/AS/certificate authority/API-key registry is trusted?
4. If a request carries multiple credentials, what precedence/collision policy applies?
5. When a credential is absent, which routes may pick another strategy?
6. When a credential is rejected, is execution guaranteed to stop?
7. When JWKS/introspection is unavailable, does it fail closed?
8. Is audience/resource binding mandatory?
9. Are token purpose/profile and lifetime validated?
10. Is the principal kind a human user or a machine client?
11. Is the subject namespace qualified by issuer?
12. Are scope/role mappings identical across issuers?
13. Should a principal from provider B have access to A's resources?
14. Can tests prove unselected backends **were not called**?
15. Does dynamic issuer onboarding come from a trusted workflow or self-asserted requests?
16. Do HA replicas share the same trust domain and policy?
17. How does the CORS/CSRF/cookie threat model change?
18. Do logs include the strategy ID without leaking credentials?
19. Do legacy mechanisms have a sunset date and monitoring for removal?
20. Are there negative tests for invalid signature/issuer/audience/token type?

These are **design questions** before implementation, not a Content QA checklist for this article.

## 34. Anti-Patterns and Fixes

| Anti-pattern | Risk | Fix |
|---|---|---|
| JWT fails then introspect | Downgrade | Select strategy before validation |
| Issuer A fails then try issuer B | Cross-issuer trust confusion | Trusted issuer resolver |
| Build JWKS URL from unverified `iss`/`jku` | SSRF/key substitution | Preconfigured allow-list |
| Multiple providers `supports` without understanding `ProviderManager` | Silent success after failure | Separate managers by policy |
| Provider returns `null` on invalid credentials | Turns failure into not-applicable | `AuthenticationException` with proper semantics |
| Reactive catch-all `onErrorResume` to another backend | Authentication bypass | Propagate failure, fail closed |
| AS `active=false` then poll next AS | Token probing/leakage | Reject per chosen AS |
| JWKS outage disables signature check | Accepts unverified tokens | Fail closed or trusted cache policy |
| Invalid Bearer falls back to session | Principal confusion/CSRF | Bearer-only route or explicit policy |
| API key rescues expired user token | Escalation/actor mismatch | Actor-specific routes |
| Trust `X-User` header from Internet | Spoofing | Trusted gateway strip/rewrite |
| Use `client_id` as `sub` for all users | Identity confusion | Separate `USER`/`CLIENT` contracts |
| Scope from issuer B becomes admin for issuer A | Privilege escalation | Issuer-specific authority mapping |
| ID token accepted on API | Cross-JWT confusion | Audience/token purpose checks |
| Routing solely by token dot count | Type spoofing | Trusted routing contract |
| Retry to independent AS on timeout | Crosses trust boundary | Only HA replicas of same authority |
| Test only success cases | Misses fallback bugs | Negative interaction tests |
| Log raw credentials | Secret leakage | Redacted metrics and logs |

## 35. Summary

~~~text
                       HTTP REQUEST
                            |
                            v
                Choose allowed trust strategy
                  from explicit policy
                            |
                            v
                  Verify the credential
               against that strategy only
                            |
               +------------+------------+
               |                         |
               v                         v
            SUCCESS                   FAILURE
               |                         |
               v                         v
       Authenticated principal      Reject / fail closed
               |                    No unrelated fallback
               v
       Authorization:
       scope + issuer + tenant + domain policy
               |
               v
       Protected operation
~~~

Key principles:

1. **Multiple authentication mechanisms do not mean trying everything until one succeeds.**
2. **Choose the strategy from trust policy first**, never from a failed strategy's exception.
3. **`NOT_APPLICABLE` differs from `AUTHENTICATION_FAILURE`**, and both differ from dependency failure.
4. **`ProviderManager` can try later providers in some situations**, so provider order alone does not guarantee fail-on-first-error.
5. **`AuthenticationManagerResolver`/`SecurityFilterChain`** separate trust policies in Servlet.
6. **Reactive resolvers/`SecurityWebFilterChain`** fulfill the equivalent role in WebFlux.
7. **JWTs with invalid signature, issuer, audience, time, or purpose must be rejected**; never rescue them with opaque/session/Basic/API key.
8. **Opaque `active=false` or an AS outage does not justify polling all introspection endpoints.**
9. **An unverified issuer claim is only a routing hint**, not permission to choose arbitrary ASes/JWKS.
10. **Failover within the same trust authority can be valid**, but another authority must never override an authentication outcome.
11. **An accepted credential must still pass authorization**, within the right scope, tenant, and actor type.
12. **Negative tests must verify unselected backends were not called**, not just check the final HTTP status.

**Conclusion:** A multi-strategy authentication architecture is safe only when each request has a clearly bounded trust path. A failure in the selected strategy must be treated as a failure, not the start of a search for another authority that will accept the credential.

## 36. References

- **Spring Security — OAuth 2.0 Resource Server Multi-tenancy (Servlet):** JWT and opaque via `AuthenticationManagerResolver`, trusted issuer selection. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html
- **Spring Security — OAuth 2.0 Resource Server Multi-tenancy (Reactive):** `JwtIssuerReactiveAuthenticationManagerResolver` and trusted issuers. https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/multitenancy.html
- **Spring Security API — ProviderManager:** provider iteration, `AuthenticationException`, and `AccountStatusException`. https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ProviderManager.html
- **Spring Security — Servlet Authentication Architecture:** `AuthenticationManager`, `AuthenticationProvider`, `ProviderManager`. https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- **Spring Security API — JwtIssuerAuthenticationManagerResolver:** JWT trusted issuer routing. https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerAuthenticationManagerResolver.html
- **Spring Security API — JwtIssuerReactiveAuthenticationManagerResolver:** WebFlux trusted issuer routing. https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerReactiveAuthenticationManagerResolver.html
- **Spring Security — Servlet JWT Resource Server:** JWS validation, issuer, audience, and timestamps. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- **Spring Security — Reactive JWT Resource Server:** `ReactiveJwtDecoder`, trusted keys, and validators. https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html
- **Spring Security — Servlet Opaque Token Resource Server:** introspection, opaque and JWT token introspection. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html
- **Spring Security — Reactive Opaque Token Resource Server:** `ReactiveOpaqueTokenIntrospector`. https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html
- **Spring Security — Servlet Java Configuration:** multiple `SecurityFilterChain` beans and `securityMatcher`. https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- **Spring Security — WebFlux Security:** `ServerHttpSecurity`/`SecurityWebFilterChain`. https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** Bearer credentials, `WWW-Authenticate`, and error semantics. https://www.rfc-editor.org/rfc/rfc6750
- **RFC 7662 — OAuth 2.0 Token Introspection:** active responses and AS trust. https://www.rfc-editor.org/rfc/rfc7662
- **RFC 7519 — JSON Web Token:** `iss`, `sub`, `aud`, `exp`, and claims. https://www.rfc-editor.org/rfc/rfc7519
- **RFC 8725 — JWT Best Current Practices:** algorithms, issuer/audience, and token confusion. https://www.rfc-editor.org/rfc/rfc8725
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** access-token audience/type/profile. https://www.rfc-editor.org/rfc/rfc9068
- **RFC 9110 — HTTP Semantics:** authentication and 400/401/403. https://www.rfc-editor.org/rfc/rfc9110
