# Restricting Service Account Permissions and Access Tokens in Spring Security WebFlux

## 1. Context, Objectives, and Target Outcomes

In **reactive** Spring Security (WebFlux) systems, many API calls originate not from browsers or end users, but from schedulers, workers, CI/CD pipelines, microservices, and background jobs. These components must have a **machine identity** (*service account/workload identity*) and **least privilege**. A service account should only be allowed to perform its assigned operation, in its assigned environment, on its assigned APIs and resources, using an access token with an appropriate lifetime.

Consistent examples throughout this lesson:

- `report-reader-prod` may only call `GET /api/reports/**` with scope `reports.read`.
- `job-runner-prod` may only call `POST /api/jobs` with scope `jobs.submit`.
- `billing-worker-prod` requires dedicated payment permissions and must not implicitly access report/job endpoints.
- Any caller presenting a validly signed token with the wrong `aud`, missing scope, wrong client identity, or cross-tenant target must be rejected at the appropriate enforcement layer.

Protection is designed in layers:

~~~text
Workload -> authenticates with Authorization Server / IdP
         -> receives access token scoped by issuer/audience/scope/expiry
         -> connects over TLS to Spring WebFlux API
         -> Resource Server validates the real token
         -> SecurityWebFilterChain checks route/method and authority
         -> policy verifies service identity
         -> service/domain checks tenant, object, and action
         -> executes business logic or returns appropriate 401/403
~~~

An access token with a valid signature **does not** automatically grant permission to perform every action. Every API can be called directly, bypassing UIs and self-imposed caller limits; the final decision must reside on the **server**.

## 2. Understanding Service Accounts, OAuth2 Clients, and Access Tokens

| Component | Meaning | Mistakes to Avoid |
| --- | --- | --- |
| Service account / workload identity | Identity of a process, workload, or service | Sharing one admin account across all services |
| OAuth2 client registration | `client_id`, client authentication mechanism, approved grants and scopes | Treating `client_id` as a secret or relying on a self-asserted client ID |
| Client credentials grant | Machine obtains an access token by authenticating with the Authorization Server, typically without user involvement | Using human user passwords or employee accounts for daemons |
| Access token | Bounded authorization at a resource server | Treating it as a "forever pass," or substituting an ID token for an access token |
| Scope | Permission range issued by the authorization server, e.g. `reports.read` | Treating scope as sufficient to skip tenant/resource checks |
| Role/authority | Permission model enforced by the resource server | Equating scopes directly with all internal roles |
| `iss`, `aud`, `exp`, `nbf` | Issuer, target API, expiration time, not-before timestamp | Base64-decoding a JWT without validating it |
| `client_id`, `azp`, `sub` | Client/subject claims depending on provider | Assuming claims always exist with identical semantics |

With **OAuth2 client credentials**, the machine authenticates directly with the IdP to receive an access token belonging to the client itself. The token is typically a bearer token: anyone who obtains the token can call the API while it remains valid, unless the system applies additional bindings such as mTLS/DPoP or revocation mechanisms. Therefore, **short TTL + narrow scope + narrow audience + protected secrets** form the baseline.

Each IdP has its own claim contract. Examples in this lesson use a JWT containing `client_id` signed by the issuer; if an IdP uses `azp`, `sub`, or another claim, confirm its semantics and how the issuer populates tokens before writing policies. Never rely on `X-Client-Id`, query parameters, JSON bodies, or claims decoded before signature verification as proof of caller authority.

An access token can be a **JWT** or an **opaque token**. JWTs require a trusted decoder, algorithms, and JWKS; opaque tokens require trusted introspection. Spring Security WebFlux supports both through the corresponding resource server configuration. Java examples below target JWTs.

## 3. Least-Privilege Matrix and Threat Model

Before creating a service account, list **principal – action – resource – environment – lifetime**. Every permission must have a business justification and a clear owner.

| Workload | Allowed API | Required Scope | Additional Conditions |
| --- | --- | --- | --- |
| `report-reader-prod` | GET `/api/reports/**` | `reports.read` | Permitted reports only, matching tenant |
| `job-runner-prod` | POST `/api/jobs` | `jobs.submit` | Granted job types and tenant only |
| `billing-worker-prod` | Approved payment APIs | `payments.process` | Restricted transaction types and accounts |
| `report-reader-staging` | Staging API | `reports.read` in staging | No prod access despite identical scope name |
| Undeclared workload | No endpoints | None | Denied by default |

Below are the required restriction layers; no single layer replaces the others:

1. **Workload identity**: separate identity per application or function. When two functions have different sensitivity levels, split their identities/registrations. Never share a super-account.
2. **Environment**: prod, staging, and dev isolate accounts, issuer endpoints, audiences, secrets, and policies. Experimental CI must not receive prod secrets by default.
3. **Method and route**: distinguish GET/POST/PATCH/DELETE. A report-reading client neither needs nor should hold modify/delete rights.
4. **Business scope**: fine-grained scopes such as `reports.read` or `jobs.submit`; avoid `api.full_access`, `admin`, or `*` without real need and explicit approval.
5. **Audience**: an access token for Resource Server A must not work at Resource Server B. Validate `aud` even when JWTs are signed by a shared issuer.
6. **Data**: access to `tenant-A` does not grant access to `tenant-B`. Verify permissions on the specific object at the service/repository/policy-engine layer.
7. **Lifecycle**: short-lived tokens, revocation capability, credential rotation, account offboarding, and access auditing.

Suppose an attacker steals `report-reader-prod`'s access token: if the token only has read scope, the exact report API audience, a short TTL, and tenant-scoped permissions, blast radius is contained. If it is a shared token with `admin` rights across multiple APIs, one minor leak becomes a system-wide breach.

**Deny by default** is a core requirement: new endpoints, unapproved actions, or workloads outside the allowlist must be rejected; never flip `denyAll()` to `permitAll()` as a temporary workaround for a 403.

## 4. Validating Access Tokens: Authentication First, Authorization Second

Spring Resource Server should only build a trusted `Authentication` after verifying the access token. For JWTs, check:

- **Signature/algorithm**: accept only algorithms, keys, and JWKS from the trusted issuer. Never trust the token's `alg` or `jku` headers to dynamically switch key sources.
- **Issuer (`iss`)**: accept tokens only from the IdP configured for the current environment.
- **Audience (`aud`)**: the token must identify the exact protected API. This check is often missed when configuring only the issuer.
- **Timestamps (`exp`, `nbf`)**: the token is unexpired and active; define clock skew explicitly.
- **Scope/authorities**: the issuer granted the authorized scopes; the server maps scopes to authorities per contract (by default prefixed with `SCOPE_`).
- **Caller identity**: verified claims like `client_id` help bind a specific caller, strictly following the real issuer's semantics.
- **Business object**: server policy checks tenant/resource ownership; a JWT does not authorize an action merely by carrying a claim.
- **Token type**: OIDC ID tokens must not be used in place of API access tokens. Never send refresh tokens as HTTP Bearer tokens to a resource server.

When a Bearer token is missing or fails authentication, HTTP typically returns **401 Unauthorized** with a Bearer challenge. When authenticated but lacking permission, it typically returns **403 Forbidden**. Do not turn claim/issuer/signature errors into anonymous success or fall back to `permitAll`. For hidden resources, some APIs return 404 by contract to avoid leaking resource existence; enforce consistent policies and tests.

An already-issued JWT can remain valid until `exp` even if the client secret was just rotated or the account disabled, depending on how the IdP/resource server handles revocation. Choose an appropriate TTL, `jti` denylist, introspection, or token revocation model. Never assume "deleting the secret" automatically invalidates every issued JWT.

## 5. Resource Server Sample for Spring Security WebFlux

This example uses Java 17+, Spring Boot 3.3.x, and Spring Security 6.x. It simultaneously enforces **issuer + audience + scope + client identity + route/method**. Place it in `src/main/java/example/security/MachineApiSecurity.java` in an application with `spring-boot-starter-webflux`, `spring-boot-starter-security`, and `spring-boot-starter-oauth2-resource-server`.

~~~java
package example.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authorization.AuthorizationContext;

@Configuration
@EnableWebFluxSecurity
public class MachineApiSecurity {

    @Bean
    SecurityWebFilterChain securityFilterChain(ServerHttpSecurity http) {
        return http
            // Only disable CSRF when the entire API uses bearer headers,
            // with no browser cookie/session login.
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .authorizeExchange(ex -> ex
                .pathMatchers(HttpMethod.GET, "/api/reports/**")
                    .access(allowOnly("report-reader-prod", "reports.read"))
                .pathMatchers(HttpMethod.POST, "/api/jobs")
                    .access(allowOnly("job-runner-prod", "jobs.submit"))
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }

    private static ReactiveAuthorizationManager<AuthorizationContext>
        allowOnly(String expectedClientId, String requiredScope) {

        return (authentication, context) -> authentication
            .map(auth -> {
                if (!(auth instanceof JwtAuthenticationToken jwtAuth)
                        || !jwtAuth.isAuthenticated()) {
                    return new AuthorizationDecision(false);
                }

                Jwt jwt = jwtAuth.getToken();  // JWT already verified by the decoder
                boolean correctClient = expectedClientId.equals(
                    jwt.getClaimAsString("client_id"));
                String requiredAuthority = "SCOPE_" + requiredScope;
                boolean correctScope = jwtAuth.getAuthorities().stream()
                    .anyMatch(a -> requiredAuthority.equals(
                        a.getAuthority()));

                return new AuthorizationDecision(correctClient && correctScope);
            })
            .defaultIfEmpty(new AuthorizationDecision(false));
    }

    @Bean
    ReactiveJwtDecoder jwtDecoder(
            @Value("${app.security.issuer}") String issuer,
            @Value("${app.security.audience}") String audience) {

        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder.withIssuerLocation(issuer).build();

        OAuth2TokenValidator<Jwt> requiredAudience = jwt ->
            jwt.getAudience().contains(audience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error("invalid_token",
                        "Required audience is missing", null));

        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
            JwtValidators.createDefaultWithIssuer(issuer),
            requiredAudience));
        return decoder;
    }
}
~~~

Illustrative configuration:

~~~yaml
app:
  security:
    issuer: https://identity.example.test/issuer
    audience: reports-jobs-api
~~~

The domains/values above are samples only; in deployment, supply the real issuer, real audience, and appropriate TLS/JWK discovery configuration.

How to read the configuration:

- `GET /api/reports/**` accepts only JWTs from the declared issuer with the right audience, `client_id=report-reader-prod`, and authority `SCOPE_reports.read`.
- `POST /api/jobs` requires `client_id=job-runner-prod` and `SCOPE_jobs.submit`.
- `anyExchange().denyAll()` rejects any other method/route, including newly added endpoints. If a health endpoint is needed, declare an explicit exception matcher and limit exposed data.
- `allowOnly` checks `JwtAuthenticationToken`; apps using opaque tokens must apply an equivalent policy on the opaque token principal. Do not silently drop the `client_id` check if the IdP does not yet supply the claim.
- `JwtValidators.createDefaultWithIssuer` provides issuer and default checks, while the extra validator enforces the exact audience. Signature validity is verified by the decoder using the trusted key source.
- Scope `reports.read` normally translates to `SCOPE_reports.read` via the default converter. If the IdP uses a different claim or format, configure the converter per a verified and tested contract; do not assume every token carries `scope`.
- `csrf(...disable)` suits pure bearer APIs that do not use credentials automatically attached by browsers. For mixed browser/session apps, keep CSRF on cookie-backed sections and split `SecurityWebFilterChain` configs using appropriate matchers.

This `client_id` check exemplifies an IdP emitting that claim in the **access token**. On other providers, you may need a different claim, claim-to-authority mapping, or policy engine; never take the service name from request bodies/headers to make authorization decisions.

## 6. Outbound Client Credentials: Send Tokens Only to the Intended Target API

A microservice can act as both a Resource Server for inbound traffic and an OAuth2 Client when making outbound calls. **These are two distinct roles**: Resource Server validates incoming tokens; OAuth2 Client acquires tokens for an authorized destination.

A background job using the `client_credentials` grant and registration `reports-reader` requests only `reports.read`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          corporate-idp:
            token-uri: https://identity.example.test/oauth2/token
        registration:
          reports-reader:
            provider: corporate-idp
            authorization-grant-type: client_credentials
            client-id: ${REPORTS_CLIENT_ID}
            client-secret: ${REPORTS_CLIENT_SECRET}
            scope: reports.read
~~~

Environment variables are a configuration pattern. In real deployments, load secrets from a secret manager or platform- and IdP-supported workload identity/federation; avoid committing secrets to Git, baking them into container images, or printing secret configs to logs. The Authorization Server must cap the maximum scopes a client can request: `scope=*` in an attacker's request must never self-escalate privileges.

For applications **without a browser session** (cron/worker), use `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`. File `src/main/java/example/security/OutboundMachineClient.java` below requires `spring-boot-starter-oauth2-client`:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class OutboundMachineClient {

    @Bean
    ReactiveOAuth2AuthorizedClientManager machineAuthorizedClientManager(
            ReactiveClientRegistrationRepository registrations,
            ReactiveOAuth2AuthorizedClientService clients) {
        var manager =
            new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                registrations, clients);
        manager.setAuthorizedClientProvider(
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build());
        return manager;
    }

    @Bean
    WebClient reportsWebClient(
            ReactiveOAuth2AuthorizedClientManager machineAuthorizedClientManager) {
        var oauth =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                machineAuthorizedClientManager);
        return WebClient.builder()
            .baseUrl("https://reports-api.example.test")
            .filter(oauth)
            .build();
    }
}
~~~

To use a specific registration **only when needed**, call it from a service injected with `WebClient`:

~~~java
// Method snippet in a service having the WebClient reportsWebClient field.
// Import reactor.core.publisher.Mono and WebClient in the class containing the method.
public Mono<String> readDailyReport(WebClient reportsWebClient) {
    return reportsWebClient.get()
        .uri("/api/reports/daily")
        .attributes(
            org.springframework.security.oauth2.client.web.reactive
                .function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction
                .clientRegistrationId("reports-reader"))
        .retrieve()
        .bodyToMono(String.class);
}
~~~

The last snippet is **an illustrative method**, not a standalone Java file. In real code you can statically import `clientRegistrationId` to avoid the long qualification. A `WebClient` configured with an authorization filter does not mean every URL should receive a token; pin the target destination and prevent callers from controlling absolute URIs or redirects that leak headers. Do not configure a broad-privilege default registration on a `WebClient` shared across arbitrary destinations. Define a separate registration/API client when downstreams need different scopes or audiences.

Avoid blindly forwarding inbound Bearer tokens outbound. A user's or service A's token may carry the wrong audience for service B. If you genuinely must propagate authority "on behalf of" a user, use token exchange or a formal delegation mechanism from the IdP to obtain a new token scoped to the target subject/audience/scopes; never assume pure token relay is safe.

## 7. Data-Level Authorization and Reactor Context

WebFlux Security makes decisions at the HTTP layer, but business logic must also enforce **resource ownership**. For example:

~~~text
POST /api/jobs
Body: { "tenantId": "tenant-B", "type": "EXPORT" }

Verified JWT:
  client_id = job-runner-prod
  scope     = jobs.submit
  tenant    = tenant-A
  aud       = reports-jobs-api

HTTP-level: caller is authorized to POST /api/jobs
Domain-level: denied because caller lacks permission on tenant-B
~~~

Do not trust `tenantId` from the request body as proof of permission. The service layer must match verified claims against a server-controlled tenant/ACL/policy store, while also constraining job types, data granularity, and side effects. Place checks close to data reads/writes to prevent **IDOR / broken object-level authorization**. For multi-step operations, guard against races between authorization checks and writes if state can change.

In reactive processing, the principal/security context flows through the **Reactor Context**. Do not mistakenly read ThreadLocal-based `SecurityContextHolder` expecting the identity to survive across `flatMap`, `publishOn`, or async tasks. Use `ReactiveSecurityContextHolder` or Spring Security argument injection in appropriate scopes; check cases where a `Publisher` subscribes outside the request scope. When using `@EnableReactiveMethodSecurity` and `@PreAuthorize`, test expressions and returned `Mono`/`Flux` types thoroughly, and avoid equating method-level security with full tenant/resource validation.

A token validated when opening an SSE/long-lived stream is **not** automatically re-checked on every emitted item. If policy requires immediate revocation or real-time permission checks, design an explicit recheck mechanism or bounded stream duration; a short TTL alone does not necessarily close already-open connections.

## 8. Testing Permission Policies with `WebTestClient` and Real Tokens

Two separate test layers are needed:

1. **Policy tests** using Spring Security Test's `mockJwt()` to simulate a trusted principal and prove routes/scopes/client IDs are denied or allowed. This tool **bypasses JWT signature/expiry/issuer/audience validation**.
2. **Decoder/integration tests** using real JWTs signed by a test key with matching issuer/audience, verifying expired tokens, wrong issuer/audience, invalid signatures, and rejected algorithms/JWKs. Use a fixed clock or tokens well outside clock-skew bounds to avoid flaky tests.

Example `src/test/java/example/security/MachineApiSecurityTest.java` in a Spring Boot 3.3 app with `spring-boot-starter-test` and `spring-security-test`:

~~~java
package example.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;

@WebFluxTest(
    controllers = MachineApiSecurityTest.Api.class,
    properties = {
        "app.security.issuer=https://identity.example.test/issuer",
        "app.security.audience=reports-jobs-api"
    })
@Import(MachineApiSecurity.class)
class MachineApiSecurityTest {

    @Autowired
    WebTestClient client;

    @MockBean
    ReactiveJwtDecoder decoder;

    @Test
    void missingBearerTokenReturns401() {
        client.get().uri("/api/reports/daily")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void wrongClientCannotSubmitWithCorrectScope() {
        client.mutateWith(mockJwt()
                .jwt(jwt -> jwt.claim("client_id", "unknown-service"))
                .authorities(new SimpleGrantedAuthority("SCOPE_jobs.submit")))
            .post().uri("/api/jobs")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void correctClientCannotReadWithoutReportsPermission() {
        client.mutateWith(mockJwt()
                .jwt(jwt -> jwt.claim("client_id", "job-runner-prod"))
                .authorities(new SimpleGrantedAuthority("SCOPE_jobs.submit")))
            .get().uri("/api/reports/daily")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void jobRunnerWithCorrectPermissionCanSubmit() {
        client.mutateWith(mockJwt()
                .jwt(jwt -> jwt.claim("client_id", "job-runner-prod"))
                .authorities(new SimpleGrantedAuthority("SCOPE_jobs.submit")))
            .post().uri("/api/jobs")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("queued");
    }

    @RestController
    static class Api {
        @GetMapping("/api/reports/daily")
        Mono<String> report() {
            return Mono.just("daily");
        }

        @PostMapping("/api/jobs")
        Mono<String> submit() {
            return Mono.just("queued");
        }
    }
}
~~~

The test above uses `@MockBean`, fitting Boot 3.3; when upgrading Boot, use the mock API supported in the target version. It tests **authorization**, not cryptographic validity or `exp`. Add cases for: right client missing scope; right scope with wrong client identity; staging token sent to prod; JWT `aud` for another API; expired token; wrong issuer; future `nbf`; new routes/DELETE methods; another workload's tenant; and endpoints exposed via another filter chain matcher.

A practical regression matrix:

| Case | Expectation |
| --- | --- |
| No Bearer token | 401 |
| Expired token, invalid signature, or wrong issuer | 401, handler does not run |
| Valid issuer but wrong audience | 401 |
| Valid token lacking required scope | 403 |
| Valid scope, ungranted client ID | 403 |
| Valid client/scope using POST on a GET-only endpoint | 403 |
| Valid client/scope for another tenant/resource | 403 or 404 per public policy |
| Staging client calling prod API | Blocked by issuer/audience/environment policy |
| All conditions satisfied | 2xx with expected body/side effect |
| Replaying old token after credential revocation | Depends on TTL/denylist/introspection; must be tested as designed |
| JWKS or IdP unreachable | Never falls back to default allow |

For tenant-level permission tests, use at least two tenants with independent resources. A test proving only tenant A succeeds is not enough to conclude tenant B is protected. When testing the decoder, do not confuse `@WithMockUser`, `mockJwt()`, or a mocked `ReactiveJwtDecoder` with real JWT signature verification tests.

## 9. Operating Service Accounts, Access Tokens, and Secrets Safely

A sound authorization policy in code can still fail in deployment if credentials live too long or leak. Apply the following process.

**Creation/provisioning:** every account has an owner, environment, client ID, job scope, audience, allowed scopes, and review date. The IdP must enforce scope ceilings per client registration; callers must not gain higher privileges simply by requesting `scope=*`. Use strong client credentials supported by the IdP: protected client secrets, `private_key_jwt`, mTLS, or workload identity federation when feasible.

**Storage/usage:** prefer a secret manager, secret volume/mount, or short-lived platform-issued identity tokens. Never commit secrets, access tokens, refresh tokens, or private keys into Git, Dockerfiles, images, test fixtures, console logs, or URL paths. Send Bearer tokens only over TLS to controlled hosts. Avoid logging full request headers or bodies containing tokens. When acquiring tokens for `WebClient`, avoid exposing tokens in exceptions or tracing spans.

**Rotation:** schedule secret and signing-key rotation with overlap per system contract; JWKS rotation must preserve verification of still-living valid tokens if policy requires. Test rotation before enabling in production. Never assume rotating a client secret immediately revokes already-issued JWTs.

**Revocation/offboarding:** when a workload is decommissioned or suspected compromised, revoke registration/secret, strip scopes, remove deployment bindings, and investigate logs. Determine whether self-contained tokens expire immediately; use short TTLs, introspection, or a denylist if immediate effect is required.

**Audit/monitoring:** log timestamp, route, 401/403/2xx decision, verified service identity, valid issuer, audience, tenant, and correlation ID with safe data levels. Never log raw tokens for "debugging convenience"; avoid putting unnecessary PII/secret claims in JWTs. Monitor spikes in 403s, new callers using high scopes, staging tokens hitting prod, permission changes, and unusual token issuances.

**Periodic review:** compare granted scopes against active functionality, remove unused permissions, split accounts if a workload expands in scope, and update owners and emergency recovery procedures. Service account permissions should be reviewed alongside code reviews and deployment workflows.

Common mistakes to avoid: enabling `anyExchange().permitAll()` in production; relying solely on a gateway while skipping server-side checks; using decoded unverified JWTs; trusting caller-sent `client_id` headers; sharing one system-wide Bearer token; using overly broad audiences; copying inbound tokens outbound unrestrictedly; giving workers admin rights to silence 403s; logging full `Authorization` headers; and assuming a deleted key/secret immediately invalidates every issued JWT.

## 10. Checklist and Acceptance Criteria

- [ ] Accounts/service identities are separated by function and environment; no shared super-account.
- [ ] An approved principal–method–route–scope–audience–tenant/resource matrix exists.
- [ ] Resource Server validates signature or introspection, issuer, audience, expiry, and not-before.
- [ ] `client_id`/identity claims follow the IdP's contract, never self-asserted by callers.
- [ ] HTTP authorization defaults to deny; policy constrains both service ID and authority.
- [ ] Scopes are not confused with authorization across all tenants or resources.
- [ ] OAuth2 Client requests only needed scopes and attaches tokens only to APIs with matching audience.
- [ ] Secrets/tokens are protected by TLS and appropriate credential management, TTLs, rotation, and revocation.
- [ ] Logs and telemetry are redacted; unusual callers/permissions are monitored.
- [ ] Tests cover 401, 403, cross-service, cross-tenant, wrong audience, expired tokens, and new endpoints.
- [ ] Spring `mockJwt()` tests are separated from real JWT decoder tests.
- [ ] CSRF protection is not dropped on browser cookie sections when an application has multiple security chains.

**Key lesson:** a service account can perform only its assigned work when **identity is verified**, **tokens are bound to the right issuer/audience/time window**, **scopes are sufficient without overreach**, **HTTP routes are conditionally allowed**, and **the data layer blocks wrong-owner/cross-tenant access**. WebFlux must enforce these checks inside the server's reactive processing pipeline rather than relying on clients or a generic "valid" token.
