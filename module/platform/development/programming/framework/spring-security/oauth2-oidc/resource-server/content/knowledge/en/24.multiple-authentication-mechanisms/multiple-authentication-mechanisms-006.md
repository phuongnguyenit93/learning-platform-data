# Coordinating Multiple Providers and Avoiding Overlapping Scopes

In a **Spring Security OAuth 2.0/OIDC Resource Server** system, a single application may simultaneously host JWT-based APIs, partner APIs using opaque tokens, a website logging in via OpenID Connect, administrative endpoints, and some legacy systems using HTTP Basic. Simply adding **AuthenticationProvider** instances without clearly bounding their scope can let a token be accepted through a mechanism not intended for that endpoint.

Important questions include:

- Which **SecurityFilterChain** does an HTTP request enter?
- Which filter extracts the credential and builds the **Authentication request**?
- Which **AuthenticationManager** is invoked?
- Which **AuthenticationProvider** instances jointly support that request type?
- If one provider rejects a token, will a subsequent provider be tried?
- Can a token valid for issuer A be used at a resource meant for issuer B?
- Can a session cookie or Basic credentials accidentally access an API meant only for Bearer tokens?
- When the application adds a new controller, is there a fallback protecting unclassified URLs?

The goal of this lesson is to distinguish coordination layers, design trust boundaries, and verify them with negative tests. **Successful authentication is only one step; authorization by scope, audience, tenant, and resource remains mandatory.**

## 1. Which Component Is "Provider" Here?

| Concept | Example | Responsibility |
|---|---|---|
| **Authorization Server / Identity Provider** | OIDC issuer A, issuer B | Issues access tokens/ID Tokens per protocol |
| **AuthenticationProvider** | JwtAuthenticationProvider, OpaqueTokenAuthenticationProvider, DaoAuthenticationProvider | Verifies one kind of Authentication request |
| **AuthenticationManager** | ProviderManager | Coordinates AuthenticationProvider instances |
| **AuthenticationManagerResolver** | JwtIssuerAuthenticationManagerResolver | Selects the right manager per request/issuer |
| **SecurityFilterChain** | API chain, web-login chain, admin chain | Decides filters and authorization rules applied to an HTTP request |
| **Authentication mechanism** | Bearer, Basic, form login, OIDC login, mTLS | How the client presents authentication proof |

One application may have multiple issuers yet one SecurityFilterChain. Another application has multiple SecurityFilterChain beans, each using only one provider. **The counts of issuers, providers, managers, and chains are not identical.**

## 2. Two Separate Selection Levels

~~~mermaid
flowchart TD
    R[HTTP request] --> FC[FilterChainProxy]
    FC --> C{First matching SecurityFilterChain}
    C -->|JWT API| JF[BearerTokenAuthenticationFilter]
    C -->|Opaque API| OF[BearerTokenAuthenticationFilter]
    C -->|Web Login| LF[OAuth2Login and session filters]
    C -->|No match| U[Not protected by these security chains]
    JF --> JM[JWT AuthenticationManager]
    OF --> OM[Opaque AuthenticationManager]
    JM --> JP[JwtAuthenticationProvider]
    OM --> OP[OpaqueTokenAuthenticationProvider]
    LF --> WP[Web login authentication]
    JP --> A[Authentication succeeded]
    OP --> A
    WP --> A
    A --> Z[Authorization: scope, role, audience, tenant]
~~~

**Level 1: FilterChainProxy** picks a chain by HTTP request and matcher order. **Level 2: AuthenticationManager** processes the Authentication request created by a filter in that chain.

Registering a JwtAuthenticationProvider **does not automatically add BearerTokenAuthenticationFilter to every URL**. Likewise, declaring a securityMatcher does not automatically verify JWT signatures.

## 3. SecurityFilterChain: First Match Wins

In Servlet Spring Security, FilterChainProxy walks through SecurityFilterChain beans in order and picks **the first matching chain**.

~~~text
@Order(1) /api/admin/**  -> JWT admin
@Order(2) /api/**        -> JWT general
@Order(3) broad matcher  -> fallback
~~~

**GET /api/admin/reports** matches both of the first two patterns, yet only **chain 1** runs. Chain 2's rules are not additive.

### 3.1. securityMatcher Differs from requestMatchers

~~~java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/api/orders/**")
            .hasAuthority("SCOPE_orders.read")
        .anyRequest().authenticated()
    );
~~~

- **securityMatcher("/api/**")** decides whether the chain is selected.
- **requestMatchers(...)** decides authorization rules once the request enters the chain.
- **anyRequest()** covers only requests belonging to that chain.

**GET /internal/export** does not belong to the /api/** chain, so anyRequest in that chain does not protect this URL.

### 3.2. Putting a Catch-All Chain First Is a Critical Bug

~~~text
@Order(1) /**               -> permitAll
@Order(2) /api/admin/**     -> hasRole ADMIN
~~~

Admin requests are matched by chain 1 first, so chain 2 never runs.

Conversely, a catch-all denyAll placed first will block every specialized chain. **Put specialized chains first, and a strict fallback last.**

## 4. AuthenticationProvider and supports()

Abbreviated Servlet interface:

~~~java
public interface AuthenticationProvider {
    Authentication authenticate(Authentication request)
        throws AuthenticationException;

    boolean supports(Class<?> requestType);
}
~~~

**supports(...)** only confirms whether the provider can handle the Authentication request class. It does not inspect token values, passwords, signatures, or issuers.

**authenticate(...)** is what verifies the credential and returns a successful Authentication or throws an error.

| Authentication request | Commonly used provider |
|---|---|
| UsernamePasswordAuthenticationToken | DaoAuthenticationProvider |
| BearerTokenAuthenticationToken with JWT | JwtAuthenticationProvider |
| BearerTokenAuthenticationToken with opaque token | OpaqueTokenAuthenticationProvider |
| PreAuthenticatedAuthenticationToken | PreAuthenticatedAuthenticationProvider |
| RememberMeAuthenticationToken | RememberMeAuthenticationProvider |

**JwtAuthenticationProvider and OpaqueTokenAuthenticationProvider both commonly support BearerTokenAuthenticationToken.** This is a major source of JWT/opaque overlap.

HTTP Basic and form login also both typically create UsernamePasswordAuthenticationToken; therefore supports() must not be treated as a tool to separate HTTP Basic from form login.

## 5. ProviderManager Does Not Work Like FilterChainProxy

Per ProviderManager's JavaDoc:

1. Providers are tried in order.
2. A provider that does not support the request type is skipped.
3. A supporting provider returning **null** may defer to the next provider.
4. When a provider returns a **non-null successful Authentication**, the manager stops and does not try later providers.
5. An **AuthenticationException** from an earlier provider can be overridden by success from a later provider.
6. If no provider handles it, ProviderNotFoundException or an appropriate authentication error may be raised.
7. **AccountStatusException** is a special case causing the manager to stop without trying later providers.
8. A parent AuthenticationManager may be consulted per configuration and ProviderManager semantics.

**Do not say "the first supporting provider is the only one executed"** and do not say "the manager always tries every provider". Behavior depends on results and exceptions.

### 5.1. ProviderManager Does Not Accumulate Authorities

Suppose provider A returns **SCOPE_orders.read** and provider B could return **ROLE_ADMIN**. ProviderManager **does not automatically run both and merge authorities**.

To require multiple authentication factors simultaneously—such as **mTLS AND JWT** or **password AND OTP**—you must design factor bindings and a separate AND policy. Simply adding two providers usually lets either mechanism pass, rather than guaranteeing both ran.

### 5.2. A Parent Manager Is Another Boundary

ProviderManager can have a parent. If local providers cannot handle the request, the parent may be invoked per implementation. Do not attach an overly broad parent and assume a Bearer-only endpoint cannot be authenticated by another mechanism.

Prefer narrowly scoped managers for each authentication strategy, especially when issuer/audience policies differ.

## 6. JWT and Opaque Tokens Both Use the Bearer Scheme

HTTP does not tag a token as JWT or opaque with a different authentication scheme:

~~~http
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
~~~

~~~http
Authorization: Bearer opaque-value-example
~~~

Both are typically turned into **BearerTokenAuthenticationToken** by BearerTokenAuthenticationFilter.

If you manually build:

~~~java
AuthenticationManager manager = new ProviderManager(
    new JwtAuthenticationProvider(jwtDecoder),
    new OpaqueTokenAuthenticationProvider(opaqueTokenIntrospector)
);
~~~

both providers support the same request type. When the JWT decoder rejects a token, ProviderManager **may** try the opaque provider depending on the error type. If another Authorization Server's introspection accepts the token, authentication can succeed even though the JWT policy rejected it.

This creates a **cross-strategy fallback/trust downgrade** risk.

### 6.1. Do Not Try Every Provider Until One Succeeds

~~~text
JWT verification fails due to wrong issuer/audience/signature
    -> switches to opaque introspection
         -> another AS returns active=true
              -> grants access
~~~

A success under a different contract can inadvertently bypass a JWT trust policy rejection.

**Select the right manager based on established routing/policy before validating the token, rather than trying every mechanism.**

### 6.2. Token Appearance Is Not a Trust Source

Counting dots to tell JWT and opaque tokens apart is an insufficiently safe heuristic. An opaque token can contain dots; a JWT-formatted access token may still require introspection for revocation.

Never use unverified token values such as **iss**, **alg**, **jku**, **jwk**, or URLs inside the token to construct trust sources outside an allowlist.

## 7. Separating SecurityFilterChains When URLs Have Clear Boundaries

Example design:

~~~text
/api/admin/**      -> JWT access token from internal issuer
/api/partners/**   -> opaque access token from partner AS
/web/**            -> OIDC Login and session cookie
all other routes   -> fallback denyAll
~~~

### 7.1. Servlet Configuration

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class MultiMechanismSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain adminApi(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/admin/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(csrf -> csrf.disable())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/admin/reports/**")
                    .hasAuthority("SCOPE_admin.read")
                .anyRequest().hasAuthority("SCOPE_admin.manage")
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()));
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain partnerApi(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/partners/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(csrf -> csrf.disable())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/partners/**")
                    .hasAuthority("SCOPE_partner.read")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(Customizer.withDefaults()));
        return http.build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain webLogin(HttpSecurity http) throws Exception {
        http
            .securityMatcher(
                "/web/**", "/login/**", "/oauth2/**", "/logout")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login/**", "/oauth2/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .csrf(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    @Order(4)
    SecurityFilterChain fallback(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll());
        return http.build();
    }
}
~~~

**This sample illustrates scope separation, not a complete production config.** You still need appropriate issuer/JWKS/JwtDecoder, introspection endpoint/credentials, OIDC client registrations, callback/logout routes, CORS, error dispatch, and Actuator policies.

Disabling CSRF in the API chains is **valid only when they truly accept only actively attached Bearer headers**, never session cookies, JWT cookies, or browser-managed Basic credentials.

### 7.2. Expected Routing Outcomes

| Request | Chain | Mechanism | Policy |
|---|---|---|---|
| GET /api/admin/reports/month | adminApi | JWT | SCOPE_admin.read |
| POST /api/admin/jobs | adminApi | JWT | SCOPE_admin.manage |
| GET /api/partners/orders | partnerApi | Opaque | SCOPE_partner.read |
| POST /api/partners/orders | partnerApi | Opaque | denyAll |
| GET /web/profile | webLogin | OIDC/session | authenticated |
| GET /internal/export | fallback | Deny | denyAll |

A JWT sent to the partner API does not redirect the request to the admin chain; an opaque token sent to the admin API is not introspected by the partner provider.

### 7.3. Why Is a Fallback Necessary?

When an application declares custom SecurityFilterChain beans, do not assume Spring Boot adds a catch-all chain automatically.

If a new controller **/internal/export** falls outside every chain, Spring Security filters from the declared chains might not protect the request. A trailing fallback denyAll helps enforce fail-closed behavior.

Check separate management ports/contexts, reverse proxy rewrites, servlet paths/context paths, HTTP methods, and dispatcher types. A 404 from an unmapped route **does not prove security worked**.

## 8. Basic and Bearer in the Same Chain: When Does It Make Sense?

A legacy endpoint may **intentionally** accept:

~~~text
/integration/**:
  HTTP Basic username/password
  or
  OAuth2 Bearer JWT
~~~

Example:

~~~java
@Bean
SecurityFilterChain mixedApi(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/integration/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults()));

    return http.build();
}
~~~

BasicAuthenticationFilter typically builds UsernamePasswordAuthenticationToken; BearerTokenAuthenticationFilter builds BearerTokenAuthenticationToken. If providers handle exact types, there is separation at the Authentication request level.

Yet supporting Basic OR Bearer requires evaluating:

- Do Basic users hold privileges equivalent to access token scopes?
- Does Basic bypass token audience/issuer or MFA policies?
- Will browsers cache/auto-send Basic credentials, creating CSRF risk?
- When a request lacks credentials, does the entry point send a Basic or Bearer challenge?
- If a request contains multiple credentials, is there a consistent rule?
- Does the API need to restrict each mechanism by HTTP method or route?

Without genuine legacy compatibility needs, **splitting paths/chains** is easier to control.

### 8.1. Overly Broad supports() in a Custom Provider Is Dangerous

~~~java
@Override
public boolean supports(Class<?> type) {
    return Authentication.class.isAssignableFrom(type);
}
~~~

This pattern feeds unexpected Authentication request types into the provider. If authenticate() accidentally returns success for an unverified credential, security can be bypassed.

Support only the designed types and return successful Authentication only from a trusted source.

## 9. AuthenticationManagerResolver: Picking the Right Manager per Request

Spring Security Servlet provides:

~~~java
AuthenticationManagerResolver<HttpServletRequest>
~~~

If a single chain truly must serve both JWT and opaque tokens, a resolver can pick a manager at request time.

### 9.1. Example JWT/Opaque Route Boundary

~~~text
/api/jwt/**       -> JwtAuthenticationProvider
/api/opaque/**    -> OpaqueTokenAuthenticationProvider
outside both      -> no allowed strategy
~~~

Java:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationProvider;
import org.springframework.security.oauth2.server.resource.authentication.OpaqueTokenAuthenticationProvider;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.security.web.SecurityFilterChain;

@Bean
AuthenticationManagerResolver<HttpServletRequest> bearerResolver(
        JwtDecoder jwtDecoder,
        OpaqueTokenIntrospector opaqueTokenIntrospector) {

    AuthenticationManager jwt =
        new ProviderManager(new JwtAuthenticationProvider(jwtDecoder));

    AuthenticationManager opaque =
        new ProviderManager(
            new OpaqueTokenAuthenticationProvider(opaqueTokenIntrospector));

    AuthenticationManager reject = authentication -> {
        throw new BadCredentialsException(
            "No approved Bearer strategy for this route");
    };

    return request -> {
        String servletPath = request.getServletPath();
        if (servletPath.startsWith("/api/jwt/")) {
            return jwt;
        }
        if (servletPath.startsWith("/api/opaque/")) {
            return opaque;
        }
        return reject;
    };
}

@Bean
SecurityFilterChain routedApi(
        HttpSecurity http,
        AuthenticationManagerResolver<HttpServletRequest> bearerResolver)
        throws Exception {

    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/jwt/**")
                .hasAuthority("SCOPE_orders.read")
            .requestMatchers(HttpMethod.GET, "/api/opaque/**")
                .hasAuthority("SCOPE_partner.read")
            .anyRequest().denyAll()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .authenticationManagerResolver(bearerResolver));

    return http.build();
}
~~~

This example assumes standard DispatcherServlet mapping. **getServletPath() may not match routes as expected** when contextPath, custom servlet mappings, proxy rewrites, or path normalization are involved. Production code should use request matchers suited to the deployment and test path variants rather than relying on startsWith alone.

For routes separated as above, two dedicated SecurityFilterChain beans are usually clearer; a resolver is truly needed only when policy must select managers **inside one shared chain**.

### 9.2. A Resolver Is Not a Decoder

It only specifies **which manager will authenticate**. The JWT manager still must verify signature, issuer, algorithms, exp/nbf, audience, and token profile. The opaque manager still must call a trusted introspection endpoint and verify active status, audience/scope/tenant per contract.

Never select another manager after the decoder rejects. If a token fails the trust policy of the routed manager, the request must fail.

## 10. Multiple JWT Issuers: Managing the Trust Allowlist

A Resource Server may trust two issuers:

~~~text
https://identity-a.example.com/realms/shop
https://identity-b.example.com/realms/partners
~~~

Spring Security supports **JwtIssuerAuthenticationManagerResolver**:

~~~java
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerAuthenticationManagerResolver;

JwtIssuerAuthenticationManagerResolver resolver =
    JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
        "https://identity-a.example.com/realms/shop",
        "https://identity-b.example.com/realms/partners"
    );

http
    .authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated())
    .oauth2ResourceServer(oauth2 -> oauth2
        .authenticationManagerResolver(resolver));
~~~

The resolver can read the unverified **iss** claim to pick a candidate manager from the trusted issuers set. **Afterward, JwtDecoder must verify the signature and claims.**

### 10.1. Unverified iss Is Only a Routing Hint

An attacker can craft a JWT payload:

~~~json
{
  "iss": "https://identity-a.example.com/realms/shop",
  "sub": "admin",
  "scope": "all"
}
~~~

These values are untrusted prior to signature and validators. The issuer claim must only route to an **allowlisted** key source/decoder, never automatically open trust.

Anti-pattern:

~~~text
Read arbitrary iss from unverified JWT
    -> create decoder to any issuer URL
    -> fetch metadata/JWKS specified by attacker
    -> accept attacker self-signed JWT
~~~

This risks SSRF or trust-boundary expansion. Never auto-register new issuers from incoming tokens.

### 10.2. A Trusted Issuer Does Not Replace Audience Validation

A token from issuer A with **aud=billing-api** must not be accepted by **orders-api**, even if signature and issuer are valid. Verify audience, token type/profile, and resource binding for every manager.

### 10.3. Identity Is Issuer + Subject

**sub=user-123** in issuer A is not by default the same identity as **sub=user-123** in issuer B. Use issuer+sub or trusted domain identity mapping; never merge accounts solely by unverified email.

### 10.4. Dynamic Tenant Management

You can use an issuer-to-manager repository to add/remove tenants, provided:

- Issuers are added only via governed administrative workflows.
- JWKS endpoints and TLS are verified.
- Audience/scopes are bound per issuer.
- Caching/lazy initialization and manager eviction are verified.
- Unknown tokens never instantiate decoders/managers on their own.
- Trust registry changes are audited.

## 11. Identical Scope Names Across Issuers Do Not Guarantee Identical Meaning

Suppose issuers A and B both issue:

~~~text
orders.read
~~~

An active token from issuer B does not necessarily carry the same privileges as one from issuer A.

| Factor | Question to answer |
|---|---|
| **Issuer** | Which source issued the token? |
| **Signature/active** | Has it been verified by a trusted source? |
| **Audience** | Which Resource Server is it intended for? |
| **Client** | Is the issued client type appropriate for this purpose? |
| **Scope** | Does orders.read share the same contract across issuers? |
| **Role** | Is this issuer authorized to grant ROLE_ADMIN? |
| **Tenant** | Which organization owns the data? |
| **Ownership** | Is the principal allowed to read this specific record? |

Do not blindly map every claim like:

~~~json
{
  "roles": ["ADMIN"]
}
~~~

from any issuer into **ROLE_INTERNAL_ADMIN**. Map authorities strictly per the verified issuer's trust contract.

## 12. OAuth2/OIDC Login Differs from Resource Server Bearer

| Aspect | OAuth2/OIDC Login | OAuth2 Resource Server |
|---|---|---|
| Goal | Log in browser user | Validate API access token |
| Mechanism | Authorization Code/OIDC callback | Authorization Bearer |
| Key token | ID Token and session/client context | Access token meant for API |
| State | Usually uses session cookie | Can be stateless |
| Spring DSL | oauth2Login | oauth2ResourceServer |
| CSRF | Consider session/browser | Consider how credentials are sent |

**An ID Token is not an access token** for an API. An ID Token with a valid signature whose audience is the OAuth client_id is not sufficient for a Resource Server.

An application using OAuth2AuthorizedClientManager to acquire access tokens when calling another service acts as an **OAuth2 Client**, and does not give inbound requests a valid Authentication.

### 12.1. Session Cookies Must Not Open Bearer-Only APIs

A browser sends:

~~~http
POST /api/admin/jobs HTTP/1.1
Cookie: JSESSIONID=session-value
~~~

If the endpoint accepts only Bearer access tokens, cookie-only requests must be rejected. When an API accidentally accepts sessions or browser-managed Basic auth, the policy has changed and CSRF risk can emerge.

**STATELESS does not automatically prevent CSRF** if a custom filter still reads a JWT from a cookie. Check the real credential ingestion mechanism, not just one property.

## 13. WebFlux: Same Principles, Different APIs

| Servlet | WebFlux |
|---|---|
| SecurityFilterChain | SecurityWebFilterChain |
| HttpSecurity | ServerHttpSecurity |
| AuthenticationManager | ReactiveAuthenticationManager |
| AuthenticationManagerResolver<HttpServletRequest> | ReactiveAuthenticationManagerResolver<ServerWebExchange> |
| JwtAuthenticationProvider | JwtReactiveAuthenticationManager |
| OpaqueTokenAuthenticationProvider | OpaqueTokenReactiveAuthenticationManager |
| JwtIssuerAuthenticationManagerResolver | JwtIssuerReactiveAuthenticationManagerResolver |
| SecurityContextHolder | ReactiveSecurityContextHolder |

Never call blocking Servlet authentication providers on the Reactor event loop. Use reactive decoders/introspectors/managers.

### 13.1. WebFlux Separating JWT and Opaque by URL

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

@Configuration
@EnableWebFluxSecurity
class ReactiveSecurityConfig {

    @Bean
    @Order(1)
    SecurityWebFilterChain admin(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                ServerWebExchangeMatchers.pathMatchers("/api/admin/**"))
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/admin/**")
                    .hasAuthority("SCOPE_admin.read")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain partner(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                ServerWebExchangeMatchers.pathMatchers("/api/partners/**"))
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/partners/**")
                    .hasAuthority("SCOPE_partner.read")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(Customizer.withDefaults()))
            .build();
    }

    @Bean
    @Order(3)
    SecurityWebFilterChain fallback(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth.anyExchange().denyAll())
            .build();
    }
}
~~~

Decoders/introspectors/validators must be configured separately, and CSRF/CORS policies must fit browser/client usage.

### 13.2. Multi-Issuer WebFlux

~~~java
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerReactiveAuthenticationManagerResolver;

JwtIssuerReactiveAuthenticationManagerResolver resolver =
    JwtIssuerReactiveAuthenticationManagerResolver.fromTrustedIssuers(
        "https://identity-a.example.com/realms/shop",
        "https://identity-b.example.com/realms/partners"
    );

http.oauth2ResourceServer(oauth2 -> oauth2
    .authenticationManagerResolver(resolver));
~~~

Issuers must belong to the governed set, and tokens still require signature/audience/expiration verification. Never treat an arbitrary URL in an unverified iss as a trust source.

## 14. OR, AND, SELECT-ONE: Which Choice Is Required?

### 14.1. OR

~~~text
Legacy endpoint:
  Valid Basic -> allowed
  Valid Bearer -> allowed
  Both invalid -> denied
~~~

You must define authority mappings, HTTP challenges, and security requirements for both.

### 14.2. AND

~~~text
Valid mTLS certificate
AND JWT access token bound to right client
AND SCOPE_orders.write
~~~

Default ProviderManager does not implement this combination automatically. You need a policy combining factors, verifying bindings between them, and tests proving missing any factor fails.

### 14.3. SELECT-ONE

~~~text
/api/admin/** -> JWT manager
/api/partners/** -> opaque manager
JWT issuer A -> decoder A
JWT issuer B -> decoder B
~~~

This is usually the clearest strategy when trust sources differ.

**Never use "try all providers until one succeeds" as a substitute for an explicit selection policy.**

## 15. Authorization Must Still Be Correct After Authentication

A rule like:

~~~java
.authorizeHttpRequests(auth -> auth
    .anyRequest().authenticated()
)
~~~

only requires an established Authentication. It does not require **SCOPE_orders.write** for POST, an ADMIN role, or record-level rights.

When multiple providers can produce a principal, an overly broad rule lets a token from a low-privilege mechanism slip through.

Check:

- Scopes per HTTP method/path.
- Issuer and audience/token purpose.
- Roles/permissions from authorized sources.
- Tenant/organization.
- Resource ownership and business state.
- Client identity and delegation.
- Domain policies independent of HTTP authentication.

Never merge permissions across two different principals or build a new principal from raw unverified tokens.

## 16. WWW-Authenticate When Multiple Mechanisms Exist

| Request | Typical outcome |
|---|---|
| Protected Bearer API, no token | 401 + WWW-Authenticate: Bearer |
| Invalid Bearer token | 401, possibly error=invalid_token |
| Valid token missing scope | 403, possibly error=insufficient_scope |
| Wrong Basic credentials | 401 + Basic challenge |
| Unauthenticated Web OIDC user | Login redirect if web flow uses interactive login |

If a single chain supports both Basic and Bearer, the entry point may need to pick a challenge per request or advertise multiple schemes per HTTP semantics. **Provider order does not automatically decide valid challenges**.

Machine clients need clear API status/challenges, not default HTML redirects.

## 17. Testing Overlap with a Credential Matrix

Example desired policy:

| Endpoint | JWT admin | Opaque partner | Basic | OIDC cookie | No credential |
|---|---|---|---|---|---|
| GET /api/admin/reports | Allow if sufficient scope | Deny | Deny | Deny | 401 |
| POST /api/admin/jobs | Allow if sufficient scope | Deny | Deny | Deny | 401 |
| GET /api/partners/orders | Deny | Allow if sufficient scope | Deny | Deny | 401 |
| POST /api/partners/orders | Deny | Deny | Deny | Deny | Deny |
| GET /web/profile | Per web policy | Per web policy | Per web policy | Valid session | Web challenge |
| GET /internal/export | Fallback deny | Fallback | Fallback | Fallback | Fallback |

This is a **requirements matrix**, not behavior Spring Security provides out of the box.

### 17.1. Mandatory Negative Tests

1. Forged JWT signature on admin API → must not be authenticated by opaque manager instead.
2. Valid JWT signature with wrong issuer → deny.
3. Valid JWT issuer with wrong audience → deny.
4. Issuer A JWT on endpoint trusting only issuer B → deny.
5. Unknown issuer in JWT → resolver does not create a decoder trusting that URL.
6. Partner AS opaque token with active=true sent to admin API → deny.
7. Basic credential sent to Bearer-only API → do not authenticate.
8. Only JSESSIONID sent to Bearer-only API → do not authenticate.
9. Both Bearer and cookie present → explicit policy behavior, no merged principals.
10. Valid token missing scope → deny.
11. Token with scope but wrong tenant/ownership → deny.
12. POST/DELETE not accidentally permitted by read-only rules.
13. New route outside specialized chains → fallback deny.
14. OIDC ID Token not accepted as an access token at Resource Server.
15. Path variants, context path, proxy rewrites, and management port verified.

### 17.2. MockMvc .with(jwt()) Does Not Prove the Decoder Works

Example:

~~~java
mockMvc.perform(get("/api/admin/reports").with(jwt()))
    .andExpect(status().isOk());
~~~

Typically Spring Security Test's **jwt()** creates a simulated Authentication; it does not prove JWT signatures were verified.

To test the real path, use a JWT signed with a test private key, a decoder trusting the test public key, and send **Authorization: Bearer** through the filters. For opaque tokens, use an HTTP introspection stub returning active=true/false.

**MockMvc must run the real Spring Security filters**. Do not rely on standaloneSetup or addFilters=false as security proof. A 404 from a route without a controller also does not prove the chain protected the endpoint.

### 17.3. Unit Testing ProviderManager

Create test doubles:

- Provider A supports request but returns null; B succeeds.
- A succeeds; B is not called.
- A throws authentication error; B may succeed per semantics.
- A throws AccountStatusException; B is not tried.
- No provider supports; authentication fails.

These tests verify **technical orchestration**, not that falling back from JWT to opaque is a safe design.

## 18. Reverse Proxies, URL Matchers, and Coverage

A request's public URL:

~~~text
Public:  https://api.example.com/v1/admin/reports
Backend: /api/admin/reports
~~~

If a proxy rewrites the path, Spring Security usually evaluates the path that reached the backend, not the external URL.

Verify:

- Servlet context path and servlet mapping.
- HTTP methods, path variants, and trailing slashes.
- Encoded paths/normalization and alias routes.
- Ingress/gateway rewrites.
- Actuator on a separate management port.
- Dispatcher types, e.g., ERROR/FORWARD where appropriate.
- Fallbacks not exposing unintended routes.
- Filter registration actually taking effect.

**Route coverage and provider coverage are two different problems**. Having the right provider still leaves a vulnerability if the request misses the chain.

## 19. Logging and Observing Orchestration

When investigating 401/403, you need to know:

- Which chain matched?
- Which filter/scheme received the credential?
- Which logical manager/provider name was selected?
- Which issuer was verified, not just raw unverified iss?
- Was the error signature, audience, inactive token, scope, or upstream timeout?
- Which rule/domain policy denied it?
- Was the HTTP challenge Bearer, Basic, or web login?

Log only **sanitized logical names, request correlation IDs, route templates, and error classes**. Never log raw Authorization headers, JWT/opaque tokens, Basic credentials, client secrets, or session cookies.

### 19.1. ProviderManager and Credential Erasure

Per ProviderManager JavaDoc, after successful Authentication, credentials on the result can be erased if Authentication implements **CredentialsContainer**, controlled by the eraseCredentialsAfterAuthentication property.

This does not automatically erase credentials already written to logs, request bodies, or custom properties. Never disable credential erasure just to debug.

### 19.2. Authentication Events

ProviderManager supports **AuthenticationEventPublisher**. When configuring custom managers, ensure the publisher is wired as needed. When a parent manager exists, avoid duplicate events from parent and child. Never put credentials into events.

## 20. Common Anti-Patterns

**Adding JWT and opaque providers both supporting Bearer and falling back on authentication error.** Can cause cross-strategy policy downgrades.

**supports(Authentication.class) on a custom provider.** Accepts more request types than it can verify.

**Treating ProviderManager as AND.** Multiple providers do not automatically create MFA.

**Placing a broad permitAll chain before specialized chains.** Shadows critical chains.

**Having no fallback.** New endpoints may bypass Spring Security.

**Creating a decoder from unverified iss/jku of arbitrary tokens.** Opens trust boundaries/SSRF.

**Treating identical scope strings across multiple issuers as identical rights.** Can confuse tenants/resources.

**Using an OIDC ID Token as a Bearer access token.** Wrong token purpose.

**Letting session cookies or Basic reach Bearer-only APIs.** Breaks credential boundaries and increases CSRF risk.

**Requiring only authenticated for administrative operations.** Lacks scope/role/domain authorization.

**Disabling CSRF application-wide because JWTs are used.** Wrong when browser sessions/cookies still exist.

**Letting JWKS/introspection timeouts pass with a mock principal.** Without reliable authentication, you must fail closed.

**Using mockJwt() or jwt() post-processors and assuming signatures were tested.** Only simulates Authentication.

## 21. An Applicable Implementation Workflow

**Step 1 — Inventory endpoints:** HTTP methods, public/backend paths, servlet context, management port, handlers, and expected access.

**Step 2 — Document accepted credentials per route:** Bearer JWT, opaque, Basic, session, or OIDC Login.

**Step 3 — Define trust contracts:** issuer/JWKS/algorithm/audience or introspection URI/client authentication/active, scopes, and tenants.

**Step 4 — Pick orchestration mechanism:** separate chains by path, issuer resolver for multiple JWT issuers, manager resolver when a single chain genuinely has multiple strategies, and a dedicated multi-factor policy if AND is needed.

**Step 5 — Design ordering/matchers:** specialized chains first, fallback denyAll last, avoiding unclear overlaps.

**Step 6 — Check supports and results:** custom providers accept only exact types and never return success from unverified credentials.

**Step 7 — Check authorization:** method-specific scopes, roles, audience, tenant, ownership; authenticated alone is insufficient for sensitive endpoints.

**Step 8 — Write negative integration tests:** cross-issuer, cross-token-format, Basic/session into Bearer-only, missing/invalid tokens, wrong scope/audience, unknown routes, path variants.

**Step 9 — Verify responses:** 401 Bearer challenge for APIs, 403 for missing permissions, interactive login handling for websites, CSRF policy matching ambient credentials.

**Step 10 — Re-review when adding an issuer/provider/route:** a new mechanism can inadvertently make previously rejected requests succeed.

## 22. Self-Check Questions

**1. If two SecurityFilterChains match the same request, do both run?**

No. The first matching chain is selected.

**2. If two AuthenticationProviders both support BearerTokenAuthenticationToken, can the second provider be tried when the first errors?**

Possibly, depending on the exception and ProviderManager semantics. Therefore avoid fallbacks lacking a trust policy.

**3. Does supports() prove a JWT token is valid?**

No. It only checks the Authentication request class.

**4. Can a validly signed JWT with audience billing-api be used at orders-api?**

No, if audience policy requires orders-api.

**5. Should a decoder be created for any arbitrary issuer claimed by an unverified JWT?**

No. Only issuers inside a governed allowlist/trust store.

**6. Are adding an mTLS provider and a JWT provider enough to require both factors?**

No. An AND policy and appropriate binding are required.

**7. Should an OIDC session cookie automatically authenticate a Bearer-only API?**

No, if API policy accepts only Bearer tokens.

**8. Does configuring anyRequest().authenticated() inside the /api/** chain protect /internal/export?**

No. Another chain or fallback is needed.

**9. Does a .with(jwt()) test returning 200 prove JwtDecoder verified the signature?**

No. You must test real Authorization headers with signed JWTs and test keys.

**10. After authentication completes, do we still need to check tenant and ownership?**

Yes. Authentication does not grant access to every resource.

## Conclusion

**Coordinating multiple AuthenticationProviders** requires separating three tasks:

1. **SecurityFilterChain** selects the HTTP request scope, first-match in order.
2. **AuthenticationManager/ProviderManager** verifies credentials through providers; the same Authentication request type can be supported by multiple providers, and an error in an earlier provider can be replaced by success from a later provider.
3. **Authorization** checks scopes, roles, issuer/audience, tenant, and resource permissions after Authentication succeeds.

For JWT/opaque Bearer tokens, **do not default to trying both providers until one accepts**. Use **route-separated SecurityFilterChain beans** or a policy-designed **AuthenticationManagerResolver**, combined with a trusted-issuer allowlist, fail-closed fallbacks, and negative tests across every authentication mechanism.

### References

- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Multiple HttpSecurity Instances](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html#_multiple_httpsecurity_instances)
- [Spring Security API — ProviderManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ProviderManager.html)
- [Spring Security API — AuthenticationProvider](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationProvider.html)
- [Spring Security — Servlet Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html)
- [Spring Security — Reactive Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/multitenancy.html)
- [Spring Security API — JwtIssuerAuthenticationManagerResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerAuthenticationManagerResolver.html)
- [Spring Security API — JwtIssuerReactiveAuthenticationManagerResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerReactiveAuthenticationManagerResolver.html)
- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Opaque Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
