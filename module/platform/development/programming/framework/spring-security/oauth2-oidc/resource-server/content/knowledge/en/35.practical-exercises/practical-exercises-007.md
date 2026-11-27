# Supporting Two Approved Issuers and Testing Data Isolation

A Resource Server may need to accept JWT access tokens from two independent Authorization Servers (issuers). For example, an API serving both internal employees and enterprise partner customers, each with its own identity provider. Spring Security can select a decoder/authentication manager based on the JWT's `iss` claim, but supporting multiple issuers must be paired with an allowlist, separate validation policies, and data isolation aligned with each trust domain.

The key principle to uphold is that **allowing an issuer to authenticate tokens does not mean principals from that issuer may read data belonging to another issuer**. Two issuers might both emit the subject `alice`, both use the role `ADMIN`, or both use the same `kid`. Those values have no global meaning. Identity must be keyed at minimum by the `(issuer, subject)` pair, and the tenant/data partition must come from a trusted mapping.

This lesson builds a Resource Server that accepts exactly two approved issuers, uses dedicated JWKS per issuer, validates issuer/audience/time/signature, isolates authority mappings, enforces tenant context, and tests cross-issuer/cross-tenant scenarios.

## 1. The Multi-Issuer Problem

Suppose an Orders API needs to serve two groups:

| Attribute | Issuer A: Workforce | Issuer B: Partner |
|---|---|---|
| Issuer URI | `https://login.corp.example` | `https://identity.partner.example` |
| JWKS URI | `https://login.corp.example/oauth2/jwks` | `https://identity.partner.example/keys` |
| Audience | `workforce-orders-api` | `partner-orders-api` |
| Tenant mapping | `internal` | `partner` |
| Order read scope | `orders.read` | `partner.orders.read` |
| Subject namespace | Managed by Issuer A | Managed by Issuer B |

Both issuers can emit valid JWTs, yet tokens must be verified with the key set and policy corresponding to the issuer that issued them.

~~~text
                       Orders Resource Server
                                  |
                     Read untrusted JWT iss
                                  |
                    +-------------+-------------+
                    |                           |
             exact issuer A              exact issuer B
                    |                           |
                    v                           v
              Decoder A                    Decoder B
              JWKS A                       JWKS B
              Audience A                   Audience B
              Authorities A                Authorities B
                    |                           |
                    +-------------+-------------+
                                  |
                         Authenticated principal
                                  |
                       Trusted issuer-to-tenant
                              mapping
                                  |
                          Tenant-scoped service
                                  |
                    Repository query with tenant_id
~~~

### 1.1. Two Issuers Are Two Trust Domains

Each issuer has:

- Separate signing keys and JWKS.
- A separate issuer identifier.
- Separate audience/resource identifiers.
- Separate token issuance policies and claim conventions.
- A separate subject namespace.
- Separate rotation, incident response, and availability processes.

Never assume two issuers share keys, `kid`, `sub`, scope, or role semantics. Even when both use OpenID Connect, token profiles and claim mappings can still differ.

### 1.2. Authentication and Data Authorization Are Two Layers

Authentication answers: was this token signed by a trusted issuer, is it unexpired, and is it intended for this API?

Data authorization answers: is the authenticated principal permitted to access the record belonging to a specific tenant/organization/resource?

Successful authentication of a token from Issuer A does not mean the principal can access Issuer B's records. Maintain tenant boundaries in the service/repository layer, even when the controller is already protected by scopes.

## 2. Trust Model: Allowlist Issuers Before Creating a Decoder

The `iss` claim sits in the JWT payload and can be read before verifying the signature. Therefore, it can be used as a **selector** to pick a pre-provisioned authentication manager, but it cannot be treated as trusted proof until the decoder verifies the signature and the issuer claim.

Safe flow:

1. Read the issuer string from the token as untrusted data.
2. Look up the exact string in a system-managed allowlist/registry.
3. If no matching issuer exists, reject the token without making any network calls.
4. Select the decoder/authentication manager bound to that issuer.
5. Verify the signature using the issuer's trusted JWKS.
6. Validate `iss`, `aud`, `exp`, `nbf`, algorithm, and token profile.
7. Create `Authentication` and map the tenant from trusted configuration.

~~~text
JWT arrives
   |
   v
Read unverified iss (routing hint only)
   |
   v
Exact lookup in approved issuer registry
   |
   +-- not found --> reject; no discovery/network fetch
   |
   v
Select issuer-specific AuthenticationManager
   |
   v
Verify signature using issuer's configured JWKS
   |
   v
Validate issuer, audience, time, algorithm, token type
   |
   v
Authenticated principal
~~~

### 2.1. Do Not Automatically Trust the Issuer URL in the Token

A dangerous implementation reads `iss` and creates a decoder from that URL:

~~~java
// Do not do this:
String issuer = readUnverifiedIssuer(token);
JwtDecoder decoder = JwtDecoders.fromIssuerLocation(issuer);
~~~

An attacker can send a JWT with `iss` pointing to a server they control. The Resource Server can be tricked into fetching an external metadata/JWKS URL, causing SSRF, hitting internal endpoints, or trusting attacker-supplied keys.

Only create decoders for registered and approved issuers. Never let a token, request header, query parameter, or arbitrary tenant name control the JWKS URL.

### 2.2. Compare Issuers by Exact Identifier

An Issuer URI is an identifier, not a URL to normalize arbitrarily. Avoid operations such as:

- Stripping paths or queries and comparing hostnames.
- Accepting every subdomain of a domain.
- Implicitly upgrading HTTP to HTTPS.
- Stripping trailing path segments for "close enough" matching.
- Prefix matching.

For example, `https://login.example/tenant-a` and `https://login.example/tenant-b` can be two distinct issuers. Use the exact provisioned issuer string and the identifier published in the issuer's metadata.

### 2.3. Manage the Allowlist as Security Configuration

The issuer registry should be managed through deployment configuration or a control plane with explicit permissions. Adding an issuer requires approving the issuer URI, JWKS URI, audience, tenant mapping, and claim policy. Never auto-register a new issuer merely because a request carries an unfamiliar `iss`.

## 3. Configuring Two Issuers in Spring Security Servlet

Spring Security provides `JwtIssuerAuthenticationManagerResolver` to select an `AuthenticationManager` from the JWT's issuer. For a static list of issuers, the `fromTrustedIssuers` factory is concise.

### 3.1. Configuring Trusted Issuers

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerAuthenticationManagerResolver;
import org.springframework.security.web.SecurityFilterChain;

import jakarta.servlet.http.HttpServletRequest;

@Configuration
class MultiIssuerSecurityConfiguration {

    static final String WORKFORCE_ISSUER =
        "https://login.corp.example";
    static final String PARTNER_ISSUER =
        "https://identity.partner.example";

    @Bean
    AuthenticationManagerResolver<HttpServletRequest>
    authenticationManagerResolver() {
        return JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
            WORKFORCE_ISSUER,
            PARTNER_ISSUER
        );
    }

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            AuthenticationManagerResolver<HttpServletRequest> resolver)
            throws Exception {

        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/health").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .authenticationManagerResolver(resolver)
            )
            .build();
    }
}
~~~

The resolver accepts only the two issuers in the list. Each issuer is used to construct its corresponding authentication manager and decoder. The API never needs private keys; each decoder fetches public keys from its issuer's JWKS endpoint.

### 3.2. When Is a Custom Resolver Needed?

`fromTrustedIssuers` works well when both issuers share similar validation policies and need default issuer validation. In practice, Issuer A and Issuer B may have different audiences, different algorithms, or separate claim/authority mappings. In that case, build one `AuthenticationManager` per issuer and look them up from a static map.

### 3.3. Dedicated `AuthenticationManager` per Issuer

The following example creates decoders with separate JWKS URIs, algorithms, and audiences:

~~~java
import java.util.Map;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationProvider;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerAuthenticationManagerResolver;

import jakarta.servlet.http.HttpServletRequest;

@Configuration
class IssuerSpecificManagers {

    static final String ISSUER_A = "https://login.corp.example";
    static final String ISSUER_B = "https://identity.partner.example";

    @Bean
    AuthenticationManagerResolver<HttpServletRequest> issuerResolver() {
        Map<String, AuthenticationManager> managers = Map.of(
            ISSUER_A, manager(
                ISSUER_A,
                "https://login.corp.example/oauth2/jwks",
                "workforce-orders-api"),
            ISSUER_B, manager(
                ISSUER_B,
                "https://identity.partner.example/keys",
                "partner-orders-api")
        );

        AuthenticationManagerResolver<String> trustedLookup =
            managers::get;

        return new JwtIssuerAuthenticationManagerResolver(trustedLookup);
    }

    private AuthenticationManager manager(
            String issuer,
            String jwkSetUri,
            String audience) {

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwkSetUri)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains(audience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Audience is not accepted by this API",
                        null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                issuerAndTime,
                audienceValidator));

        JwtAuthenticationProvider provider =
            new JwtAuthenticationProvider(decoder);
        provider.setJwtAuthenticationConverter(
            new JwtAuthenticationConverter());

        return provider::authenticate;
    }
}
~~~

`JwtIssuerAuthenticationManagerResolver` uses the issuer string to look up the manager. `managers::get` returns a manager only when the issuer matches a registered key exactly; any other issuer gets `null` and is rejected. Do not replace this map with logic that builds decoders from arbitrary URLs.

The snippet above uses RS256 for both issuers for illustration. If an issuer uses a different algorithm, configure a dedicated allowlist on that manager. The audience validator is also per issuer; a token from A carrying audience B must not be accepted merely because its signature is valid.

### 3.4. Dedicated Authority Converter per Issuer

Two issuers may use different scope claims. If Issuer A uses a space-delimited `scope` string while Issuer B uses a `permissions` array, do not force one shared converter to interpret both under the same convention.

You can configure a dedicated converter on each `JwtAuthenticationProvider` before placing the provider in the map. With the default converter, Spring Security typically maps `scope`/`scp` to authorities with the `SCOPE_` prefix. For custom claims, write an explicit converter and test positive/negative mappings.

Do not map a `roles=["ADMIN"]` claim from Issuer B to an internal admin permission merely because the role name matches. Authority namespaces should reflect the trust domain, such as `WORKFORCE_ADMIN` and `PARTNER_ORDER_READER`, or map through a controlled policy service.

## 4. Configuring Two Issuers in Spring Security WebFlux

WebFlux provides `JwtIssuerReactiveAuthenticationManagerResolver` and reactive authentication managers. Never use a Servlet resolver or blocking decoder in a reactive filter chain.

### 4.1. Trusted Issuer List

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ReactiveAuthenticationManagerResolver;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerReactiveAuthenticationManagerResolver;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.server.ServerWebExchange;

@Configuration
class MultiIssuerReactiveSecurityConfiguration {

    @Bean
    ReactiveAuthenticationManagerResolver<ServerWebExchange>
    reactiveIssuerResolver() {
        return JwtIssuerReactiveAuthenticationManagerResolver
            .fromTrustedIssuers(
                "https://login.corp.example",
                "https://identity.partner.example"
            );
    }

    @Bean
    SecurityWebFilterChain apiSecurity(
            ServerHttpSecurity http,
            ReactiveAuthenticationManagerResolver<ServerWebExchange> resolver) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/health").permitAll()
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .authenticationManagerResolver(resolver)
            )
            .build();
    }
}
~~~

### 4.2. Dedicated Reactive Manager per Issuer

When audiences or decoder configurations differ, build a map from issuer to `ReactiveAuthenticationManager`:

~~~java
import java.util.Map;

import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.ReactiveAuthenticationManagerResolver;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtReactiveAuthenticationManager;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerReactiveAuthenticationManagerResolver;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@Configuration
class IssuerSpecificReactiveManagers {

    private static final String ISSUER_A = "https://login.corp.example";
    private static final String ISSUER_B = "https://identity.partner.example";

    @Bean
    ReactiveAuthenticationManagerResolver<ServerWebExchange> resolver() {
        Map<String, ReactiveAuthenticationManager> managers = Map.of(
            ISSUER_A, manager(
                ISSUER_A,
                "https://login.corp.example/oauth2/jwks",
                "workforce-orders-api"),
            ISSUER_B, manager(
                ISSUER_B,
                "https://identity.partner.example/keys",
                "partner-orders-api")
        );

        ReactiveAuthenticationManagerResolver<String> trustedLookup =
            issuer -> Mono.justOrEmpty(managers.get(issuer));

        return new JwtIssuerReactiveAuthenticationManagerResolver(
            trustedLookup);
    }

    private ReactiveAuthenticationManager manager(
            String issuer,
            String jwkSetUri,
            String audience) {

        NimbusReactiveJwtDecoder decoder = NimbusReactiveJwtDecoder
            .withJwkSetUri(jwkSetUri)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains(audience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Audience is not accepted by this API",
                        null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                audienceValidator));

        return new JwtReactiveAuthenticationManager(decoder);
    }
}
~~~

The resolver only looks up inside the configured issuer map. The reactive decoder performs JWKS retrieval via reactive infrastructure. If a custom authority converter is needed, configure it on each `JwtReactiveAuthenticationManager`; never block to invoke a Servlet converter or synchronous network client on the event loop.

### 4.3. Version Compatibility

Package names and resolver overloads can vary across Spring Security major/minor versions. Use the API of your project's version and verify the corresponding Javadoc. The principles never change: issuers must be allowlisted, managers must be bound to specific issuers, and decoders must enforce issuer/audience/key policies.

## 5. Mapping Issuer to Tenant Identity

Once the decoder validates the token, the application needs to build tenant context from verified data and trusted configuration. For the example with two issuers corresponding to two tenant partitions:

~~~java
import java.util.Map;

import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Component;

record TenantIdentity(
    String issuer,
    String subject,
    String tenantId
) {}

@Component
class TenantIdentityResolver {

    private static final Map<String, String> TENANT_BY_ISSUER = Map.of(
        "https://login.corp.example", "internal",
        "https://identity.partner.example", "partner"
    );

    TenantIdentity resolve(JwtAuthenticationToken authentication) {
        Jwt jwt = authentication.getToken();
        String issuer = jwt.getClaimAsString("iss");
        String tenantId = TENANT_BY_ISSUER.get(issuer);

        if (tenantId == null) {
            throw new IllegalStateException(
                "Authenticated issuer has no tenant mapping");
        }

        String subject = jwt.getSubject();
        if (subject == null || subject.isBlank()) {
            throw new IllegalStateException(
                "Authenticated token has no subject");
        }

        return new TenantIdentity(issuer, subject, tenantId);
    }
}
~~~

This is a static mapping by issuer. Because the decoder already validated the issuer claim, the application can use that claim to look up the tenant. Never take a tenant ID from `X-Tenant-ID`, a query parameter, or a request body and treat it as the tenant identity.

### 5.1. Subject Must Be Paired with Issuer

Both issuers may issue `sub=alice`. These are two distinct identities:

~~~text
("https://login.corp.example", "alice")
    -> internal user 1042

("https://identity.partner.example", "alice")
    -> partner user 8891
~~~

If the database has a user identity table, use a composite key or unique constraint on `(issuer, subject)`. Never use `sub` alone as a global user ID.

Example schema:

~~~sql
CREATE TABLE external_identity (
    id BIGINT PRIMARY KEY,
    issuer VARCHAR(500) NOT NULL,
    subject VARCHAR(255) NOT NULL,
    tenant_id VARCHAR(100) NOT NULL,
    local_user_id BIGINT NOT NULL,
    UNIQUE (issuer, subject)
);
~~~

The issuer must be stored using the exact verified identifier. Constrain column lengths and validate input before persisting to prevent malformed data.

### 5.2. When One Issuer Represents Multiple Tenants

You cannot always map one issuer to exactly one tenant. For instance, Issuer B may issue tokens for many partner organizations. In that case, the token may carry a `tenant_id` or `organization` claim signed by the issuer.

Tenant claims must still be checked against policy:

- Is Issuer B authorized to issue tokens for that tenant?
- Does the subject/client hold membership in that tenant?
- Is the tenant active and permitted to use the API?
- Does the token's audience match the resource?
- Should the tenant claim be cross-checked against an internal registry?

If the request includes `X-Tenant-ID`, the header can serve as a selector to pick one tenant from the principal's verified membership set. The header must never expand the set of tenants the principal can access.

### 5.3. Do Not Trust a Tenant Claim Merely Because the JWT Is Signed

A signature proves the issuer emitted the claim. It does not prove the application understands the claim's semantics correctly. Agree with the issuer on claim name, data type, namespace, membership update timing, and handling of users belonging to multiple organizations.

Never allow Issuer A to issue a tenant ID belonging to a namespace reserved for Issuer B unless an explicit mapping/delegation is designed.

## 6. Enforcing Tenant Boundaries in Service and Repository Layers

Authentication in the filter chain is only the starting point. Every data query must be bound to the verified tenant identity.

### 6.1. Always Include Tenant ID in Repository Queries

Example with a Spring Data repository:

~~~java
import java.util.List;
import java.util.Optional;
import org.springframework.data.repository.Repository;

interface OrderRepository extends Repository<OrderEntity, Long> {

    List<OrderEntity> findAllByTenantId(String tenantId);

    Optional<OrderEntity> findByIdAndTenantId(
        Long id,
        String tenantId);
}
~~~

The service uses the resolved tenant identity:

~~~java
import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class TenantOrdersService {

    private final OrderRepository repository;

    TenantOrdersService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    List<OrderEntity> list(TenantIdentity identity) {
        return repository.findAllByTenantId(identity.tenantId());
    }

    @Transactional(readOnly = true)
    Optional<OrderEntity> get(Long orderId, TenantIdentity identity) {
        return repository.findByIdAndTenantId(
            orderId,
            identity.tenantId());
    }
}
~~~

Do not fetch an order by ID first and only check the tenant in the controller after returning the entity. Queries must restrict by tenant right at the data access boundary.

### 6.2. Controllers Must Not Accept Client-Asserted Tenant Identity

Example:

~~~java
import java.util.List;
import org.springframework.http.ResponseEntity;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrdersController {

    private final TenantIdentityResolver tenantResolver;
    private final TenantOrdersService orders;

    OrdersController(
            TenantIdentityResolver tenantResolver,
            TenantOrdersService orders) {
        this.tenantResolver = tenantResolver;
        this.orders = orders;
    }

    @GetMapping("/api/orders")
    List<OrderEntity> list(JwtAuthenticationToken authentication) {
        TenantIdentity identity = tenantResolver.resolve(authentication);
        return orders.list(identity);
    }

    @GetMapping("/api/orders/{id}")
    ResponseEntity<OrderEntity> get(
            @PathVariable Long id,
            JwtAuthenticationToken authentication) {
        TenantIdentity identity = tenantResolver.resolve(authentication);
        return orders.get(id, identity)
            .map(ResponseEntity::ok)
            .orElseGet(() -> ResponseEntity.notFound().build());
    }
}
~~~

In Spring MVC, controllers can receive `JwtAuthenticationToken` via method argument resolution or extract the principal from `Authentication`. If using `@AuthenticationPrincipal Jwt`, you can pass the verified JWT directly to the resolver. Never accept another tenant ID from the client to determine data scope.

### 6.3. Protect Updates and Deletes Too

Tenant filters must be present in every operation:

~~~sql
UPDATE orders
SET status = :new_status
WHERE id = :order_id
  AND tenant_id = :authenticated_tenant_id;
~~~

~~~sql
DELETE FROM orders
WHERE id = :order_id
  AND tenant_id = :authenticated_tenant_id;
~~~

If updates/deletes omit the tenant check, an attacker can modify or delete another tenant's record by changing the ID even when `GET` lists are isolated.

### 6.4. Database-Level Tenant Isolation

With PostgreSQL, Row-Level Security (RLS) can provide an additional layer of defense. Example policy:

~~~sql
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders FORCE ROW LEVEL SECURITY;

CREATE POLICY orders_tenant_isolation
ON orders
USING (
    tenant_id = current_setting('app.tenant_id', true)
)
WITH CHECK (
    tenant_id = current_setting('app.tenant_id', true)
);
~~~

The application must set `app.tenant_id` in the active transaction/connection prior to querying. Use transaction-local settings (such as `SET LOCAL`) so context cannot leak across the connection pool to another request. The application's database user must not be a superuser or hold a role that bypasses RLS.

RLS does not replace application-layer authorization; it serves as defense-in-depth. Test reads, inserts, updates, and deletes, including connection reuse and rollbacks.

## 7. Isolating Authorities and Policies Between Two Issuers

Scope and role names from two issuers are not automatically equivalent. If both issue `ADMIN`, a shared converter could accidentally grant internal administrative privileges to a partner user.

### 7.1. Namespacing Authorities by Issuer

Example mapping policy:

| Issuer | Token claim | Internal authority |
|---|---|---|
| Workforce | `scope=orders.read` | `WORKFORCE_ORDERS_READ` |
| Workforce | `roles=[ADMIN]` | `WORKFORCE_ADMIN` |
| Partner | `permissions=[orders:view]` | `PARTNER_ORDERS_READ` |
| Partner | `roles=[ADMIN]` | `PARTNER_ADMIN` |

Endpoint policies can use namespaced authorities:

~~~java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/api/internal/**")
        .hasAuthority("WORKFORCE_ADMIN")
    .requestMatchers("/api/partner/**")
        .hasAuthority("PARTNER_ORDERS_READ")
    .anyRequest().authenticated()
);
~~~

Shared endpoints can accept multiple explicit authorities:

~~~java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/api/orders/**")
        .hasAnyAuthority(
            "WORKFORCE_ORDERS_READ",
            "PARTNER_ORDERS_READ")
    .anyRequest().authenticated()
);
~~~

### 7.2. Do Not Rely on Generic Role Names

Avoid policies that only check for `ADMIN` if `ADMIN` is issued by multiple issuers with different meanings. If the application genuinely has a platform-wide administrator, that privilege should come from a dedicated trusted policy source with approval/auditing, never inferred from colliding role strings.

### 7.3. Issuer-Issued Permissions Do Not Replace Tenant Membership

Even `PARTNER_ORDERS_READ` only indicates the token has permission to read that resource type. It does not automatically identify which partner. The service must still constrain by tenant ID or check membership on the specific resource.

## 8. Tenant Isolation in WebFlux

WebFlux executes on a reactive pipeline. Never store tenant identity in a `ThreadLocal` or static mutable field assuming the next step will run on the same thread. Requests from two issuers can interleave on the same event loop.

### 8.1. Passing Tenant Identity Explicitly

A resolver can accept the verified `Jwt`:

~~~java
import java.util.Map;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Component;

@Component
class ReactiveTenantIdentityResolver {

    private final Map<String, String> tenantByIssuer = Map.of(
        "https://login.corp.example", "internal",
        "https://identity.partner.example", "partner"
    );

    TenantIdentity resolve(Jwt jwt) {
        String issuer = jwt.getClaimAsString("iss");
        String tenantId = tenantByIssuer.get(issuer);
        if (tenantId == null) {
            throw new IllegalStateException("No tenant mapping for issuer");
        }
        return new TenantIdentity(issuer, jwt.getSubject(), tenantId);
    }
}
~~~

Reactive controllers/services pass `TenantIdentity` across methods:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
class ReactiveOrdersController {

    private final ReactiveTenantIdentityResolver tenantResolver;
    private final ReactiveTenantOrdersService orders;

    ReactiveOrdersController(
            ReactiveTenantIdentityResolver tenantResolver,
            ReactiveTenantOrdersService orders) {
        this.tenantResolver = tenantResolver;
        this.orders = orders;
    }

    @GetMapping("/api/orders")
    Flux<OrderEntity> list(@AuthenticationPrincipal Jwt jwt) {
        TenantIdentity identity = tenantResolver.resolve(jwt);
        return orders.list(identity);
    }
}
~~~

Reactive service:

~~~java
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
class ReactiveTenantOrdersService {

    private final ReactiveOrderRepository repository;

    ReactiveTenantOrdersService(ReactiveOrderRepository repository) {
        this.repository = repository;
    }

    Flux<OrderEntity> list(TenantIdentity identity) {
        return repository.findAllByTenantId(identity.tenantId());
    }
}
~~~

The example uses explicit parameters so the tenant boundary is clear and easy to test. If the application uses Reactor Context for cross-cutting metadata, ensure the context is attached to the right subscription and avoid mutable singleton state.

### 8.2. Avoid `ThreadLocal` Tenant Context

Do not do:

~~~java
static final ThreadLocal<String> CURRENT_TENANT = new ThreadLocal<>();
~~~

`ThreadLocal` breaks when a reactive pipeline switches threads, and data can leak across requests if not cleared properly. Use explicit parameters, Reactor Context, or configured and tested framework context propagation.

### 8.3. Reactive Repositories Always Filter by Tenant

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

interface ReactiveOrderRepository
        extends ReactiveCrudRepository<OrderEntity, Long> {

    Flux<OrderEntity> findAllByTenantId(String tenantId);

    Mono<OrderEntity> findByIdAndTenantId(
        Long id,
        String tenantId);
}
~~~

Never fetch a record by global ID and return it before verifying the tenant. Use queries with a tenant predicate at the repository.

## 9. Isolating Data Outside the Database

Tenant isolation often fails outside the primary relational tables. Every cache, object storage bucket, search index, message queue, and background job must preserve tenant boundaries.

### 9.1. Cache Keys

Do not cache an order solely by order ID if IDs can collide across tenants or if authorization results depend on tenant. Cache keys should include the tenant namespace:

~~~text
orders:{tenantId}:{orderId}
profile:{issuerAlias}:{subject}
permissions:{issuerAlias}:{subject}:{tenantId}
~~~

For identity caches, use the issuer/subject pair. For resource caches, use the tenant/resource key. Never include raw access tokens in cache keys.

### 9.2. Object Storage

Prefix object keys with the tenant:

~~~text
tenant/internal/orders/1001/invoice.pdf
tenant/partner/orders/1001/invoice.pdf
~~~

Never let clients supply arbitrary storage paths. The service must construct paths from the verified tenant identity and check ownership before issuing pre-signed URLs.

### 9.3. Search Indexes

Search queries must filter by tenant ID on the server side. Never rely on the frontend sending the filter. If using a shared index, every query and aggregation requires the tenant predicate; if using separate per-tenant indexes, the resolver must select the index from a trusted tenant mapping.

### 9.4. Message Queues and Event Consumers

Domain events should carry explicit tenant identity:

~~~json
{
  "eventId": "evt-10001",
  "tenantId": "partner",
  "issuer": "https://identity.partner.example",
  "subject": "alice",
  "orderId": "1001",
  "eventType": "OrderCreated"
}
~~~

Consumers must not trust the tenant ID in an event if the producer is unauthenticated. Validate the event source, schema, tenant membership, and access rights before processing. Avoid global caches or consumer state that could mix events from two tenants.

### 9.5. Background Jobs and Scheduled Tasks

Jobs running outside HTTP requests have no bearer token to derive tenant context. When enqueuing a job, store the verified tenant ID and resource ownership in the job payload; the worker must validate the tenant/resource mapping before processing. Never rely on a leftover `ThreadLocal` from the request that spawned the job.

## 10. Caches and Identity Mappings Must Be Isolated by Issuer

Even when two issuers share a subject and a `kid`, caches must never mix results:

| Cache concern | Recommended namespace |
|---|---|
| Principal/user lookup | Issuer + subject |
| JWK/key selection | Issuer/JWKS source + `kid` |
| Authorization/permission snapshot | Issuer + subject + tenant + policy version |
| Tenant data | Tenant ID + resource key |
| Session/linking state | Issuer + subject + client/session context |

### 10.1. `kid` Is Not a Global Key Identifier

Issuer A and Issuer B can both use `kid` equal to `signing-2026-01` while holding different public keys. Never use a single global map keyed only by `kid`. Key selection must happen inside the decoder/JWK source of the matching issuer.

### 10.2. Never Use `sub` as the Sole Cache Key

If Issuer A and Issuer B both have `sub=alice`, a `user:alice` cache key could return the first issuer's profile, permissions, or tenant to the second issuer. Use an issuer alias or issuer URI together with subject.

### 10.3. Invalidate Within the Right Namespace

When a user is disabled or a tenant is offboarded, purge entries belonging to the exact issuer/tenant. Ensure invalidation does not miss cluster nodes or accidentally wipe another issuer's policy sharing the same subject/`kid`.

## 11. Testing Two Issuers and Data Isolation

A multi-issuer test suite must verify both token validation and tenant boundaries. Testing only a valid JWT from Issuer A does not prove Issuer B is configured properly; testing only a controller with a mock principal does not prove the issuer resolver/JWKS works.

### 11.1. Minimum Test Matrix

| Case | Token/request | Expected outcome |
|---|---|---|
| Valid Workforce token | Issuer A, key A, audience A | Authenticated, tenant `internal` |
| Valid Partner token | Issuer B, key B, audience B | Authenticated, tenant `partner` |
| Unapproved issuer | Issuer C | Rejected, no metadata/JWKS fetch |
| Token A with audience B | Issuer A, signature A, audience B | Rejected |
| Token B with audience A | Issuer B, signature B, audience A | Rejected |
| Issuer A signed with key B | Issuer A, private key B | Rejected |
| Issuer B signed with key A | Issuer B, private key A | Rejected |
| Expired token | Valid issuer/key/audience, past `exp` | Rejected |
| Same `sub` across two issuers | A/`sub=alice` and B/`sub=alice` | Two separate identities/tenants |
| Same `kid` across two issuers | Same `kid`, different key material | Each token verifies only with its own key set |
| Tampered tenant header | Token A, `X-Tenant-ID=partner` | Cannot access partner data |
| Other tenant's record ID | Token A requests partner's order | Does not return that record's data |
| `ADMIN` role from partner | Token B has role `ADMIN` | Does not gain `WORKFORCE_ADMIN` |

### 11.2. Using Real Signed JWTs to Test the Resolver

To test the real execution path:

1. Generate separate test key pairs A and B.
2. Stand up local JWKS endpoints A and B.
3. Configure the allowlist/manager map with the two local JWKS URIs.
4. Sign token A with private key A, setting issuer/audience A.
5. Sign token B with private key B, setting issuer/audience B.
6. Send tokens via the `Authorization: Bearer` header to real endpoints in the test context.
7. Assert HTTP status, tenant-specific responses, and repository calls.

Do not call production issuers in tests and never use production private keys. Local JWKS mock servers must be bound to localhost/test networks.

### 11.3. Narrow Scope of Mock JWTs

Spring Security Test can fabricate a mock `Authentication` with `mockJwt` to quickly test controllers/services and authority rules. However, this helper normally bypasses the issuer resolver, JWKS retrieval, and signature verification. Therefore:

- Use mock JWTs to test downstream mapping when targeting controllers/services.
- Use signed JWTs via the Bearer header to test multi-issuer routing and decoders.
- Never treat a mock JWT test as proof that the issuer allowlist or JWKS isolation is working.

### 11.4. Testing Two Identical Subjects

Create two tokens:

~~~text
Token A:
    iss = https://login.corp.example
    sub = alice
    aud = workforce-orders-api

Token B:
    iss = https://identity.partner.example
    sub = alice
    aud = partner-orders-api
~~~

Assert:

- The resolver returns tenant `internal` for Token A.
- The resolver returns tenant `partner` for Token B.
- User lookups use the `(issuer, subject)` pair.
- No profile, permissions, or orders are shared merely because `sub` is identical.

### 11.5. Testing Tenant Header Tampering

Send Token A with header:

~~~http
Authorization: Bearer <SIGNED_TOKEN_A>
X-Tenant-ID: partner
~~~

The response must remain scoped to tenant `internal` or reject the invalid header. It must never switch to tenant `partner` merely because the request included that header.

### 11.6. Testing Repository Queries with Tenant Predicates

With Token A, call an endpoint with an order ID belonging to tenant B. The result can be `404` to hide record existence, or `403` per API policy; what matters is that the response contains no tenant B data and the query always enforces the tenant constraint.

You can verify the repository was invoked with the tenant ID derived from the verified identity. In database integration tests, seed two rows with the same business identifier in different tenants and verify each token only sees the row belonging to its tenant.

### 11.7. Testing Multi-Issuer Cache Isolation

Create two tokens with the same subject and same `kid` but different keys/issuers. After Token A is authenticated and its principal cached:

- Token B must still go through Decoder B.
- Never return Principal A for Token B.
- Cache keys must be namespaced by issuer/JWKS source.
- Invalidating User A must not accidentally delete or overwrite User B's state.

## 12. Linking Accounts Across Two Issuers

Two issuers may represent the same human user, yet the Resource Server should never automatically merge accounts solely because email or subject matches.

### 12.1. Do Not Auto-Link Solely by Email

An email address may be:

- Unverified at one issuer.
- Changed or reassigned to someone else.
- Shared across a group mailbox.
- Governed by different semantics between workforce and partner directories.

If account linking is required, use an explicit verification workflow with appropriate consent/approval and auditing. Store external identities separately and link them to a local account via a controlled record.

### 12.2. External Identity and Local Account

Data model:

~~~text
LocalAccount
    id = 5001
    status = ACTIVE

ExternalIdentity
    issuer = https://login.corp.example
    subject = alice
    localAccountId = 5001

ExternalIdentity
    issuer = https://identity.partner.example
    subject = alice-partner-9
    localAccountId = 5001
~~~

Two external identities point to the same local account only after the linking workflow is verified and approved. Never infer linking automatically from matching `sub` or email.

### 12.3. Permissions Do Not Merge Automatically on Account Link

Linking identities does not mean combining all authorities from both issuers. Each request must still retain its issuer context and corresponding policy. If business logic requires a unified permission, the policy service must grant it explicitly and log an audit record.

## 13. Security Pitfalls in Multi-Issuer Deployments

### 13.1. Expanding the Issuer Allowlist from Untrusted Input

Never create decoders or register tenants based on an issuer URL supplied by a token/request. Provision issuers through a trusted admin/control plane.

### 13.2. Sharing JWKS or Un-Namespaced Key Caches

Two issuers can share a `kid`. Each issuer must have its own JWK source/decoder or a cache namespace including the issuer/JWKS source.

### 13.3. Checking Signature Without Audience

A token signed by a valid issuer but intended for another API must not be accepted. Each manager needs an appropriate audience validator.

### 13.4. Checking Issuer Without Verifying Signature

The issuer claim can be forged if signatures are not verified. The resolver uses the unverified claim to pick a manager; the decoder must validate the signature and issuer before `Authentication` is trusted.

### 13.5. Using Shared Authorities for Both Issuers

Identical role names do not mean equivalent permissions. Namespace or use per-issuer converters so partner roles never turn into workforce privileges.

### 13.6. Taking Tenant ID from the Request

Header/path/query tenant IDs are untrusted input. Tenant context must be bound to verified identity and membership policy.

### 13.7. Filtering Tenants in Only a Few Repository Endpoints

Having a filter on `GET` while export, search, update, delete, or background jobs lack filters still leaks data. Tenant predicates must span every data access path.

### 13.8. Using `ThreadLocal` in WebFlux

Reactive requests are not guaranteed to stay on a single thread. `ThreadLocal` can lose context or leak tenants between requests. Use explicit context or Reactor Context.

### 13.9. Trusting Email to Merge Identities

Matching emails do not prove two issuers represent the same principal. Account linking requires a dedicated workflow.

### 13.10. Neglecting Offboarding Checks

When an issuer or tenant is offboarded, remove/disable the resolver mapping, tenant mapping, cache entries, client permissions, and related background jobs. Do not merely remove the issuer from config while leaving data/caches reachable through other paths.

## 14. Distinguishing OIDC ID Tokens from OAuth 2.0 Access Tokens

An OIDC issuer typically issues both ID Tokens and Access Tokens, yet Resource Server APIs require access tokens. Never accept an ID Token merely because it is a validly signed JWT from the same issuer.

| Attribute | ID Token | Access Token |
|---|---|---|
| Audience | OIDC client receiving login | Resource/API being called |
| Purpose | Confirms authentication event to the client | Grants permission to access resources |
| Where used | OIDC client/Relying Party | OAuth 2.0 Resource Server |
| Scope/authority | Not a default source of API authorization | Carries scopes/permissions for the API |

If the API audience is the orders API, a token whose audience is a browser client must be rejected, even with the same issuer and a valid signature.

### 14.1. Align Token Profiles Between Both Issuers

Issuer A and Issuer B may use different access token profiles. Clarify:

- Token type/`typ` header if required by the profile.
- Audience claim format and expected resource identifier.
- Scope/permissions claim name and data type.
- Subject semantics and stability.
- Issuer and timestamp claims.
- Required client identifier claim if policy requires it.

If using RFC 9068 JWT Profile for OAuth 2.0 Access Tokens, check the profile's requirements and configure validators accordingly. Never infer a token is an access token merely because it parses as a JWT.

### 14.2. Distinct Audiences Are a Critical Boundary

For example:

~~~text
Issuer A access token:
    iss = https://login.corp.example
    aud = workforce-orders-api

Issuer B access token:
    iss = https://identity.partner.example
    aud = partner-orders-api
~~~

A token from Issuer A must not be accepted merely because Issuer A is allowlisted if its audience is not intended for the API. Likewise, audience B must not be accepted in Decoder A.

## 15. Issuer Lifecycle and Configuration Changes

The list of two approved issuers is part of the security boundary. Changing issuers, JWKS URIs, audiences, or tenant mappings requires governance and controlled rollout.

### 15.1. Onboarding a New Issuer

Before adding an issuer:

1. Verify ownership and exact issuer URI.
2. Obtain metadata/JWKS URI from official documentation or a verified control plane.
3. Verify TLS, DNS, network reachability, and JWKS public keys.
4. Define audience, token profile, and allowed algorithms.
5. Define tenant mapping and authority converter.
6. Add the issuer to the allowlist and decoder manager map.
7. Test with real tokens using a test key/issuer environment.
8. Deploy via canary and monitor authentication failures.

Never grant a new issuer production access merely because its metadata endpoint returns valid JSON.

### 15.2. Changing a JWKS URI

The JWKS URI is trust-sensitive configuration. When migrating endpoints:

- Publish the same public key set at the new endpoint first.
- Verify the TLS certificate and issuer metadata.
- Update manager configuration.
- Confirm nodes can fetch the new JWKS.
- Keep the old endpoint during an overlap window if needed.
- Retire the old endpoint after propagation completes.

Changing an issuer URI can constitute a new trust domain identity; do not simply edit the issuer string and treat old tokens as equivalent without a migration policy.

### 15.3. Offboarding an Issuer

When an issuer is no longer permitted:

- Remove the issuer from the trusted resolver/manager registry.
- Reject new tokens from that issuer.
- Purge decoder/cache entries by namespace.
- Revoke or terminate sessions/token families per issuer capabilities.
- Confirm tenant data is exported/retained per policy.
- Stop background consumers and scheduled jobs for that tenant.
- Retain audit records long enough per retention policy.

Do not delete tenant data simply because an issuer is offboarded; data retention/deletion is a separate decision.

### 15.4. Rotating Keys Independently per Issuer

Issuer A and Issuer B may have different key rotation schedules. Each decoder/JWK source must refresh its own issuer's endpoint. When A rotates, never drop B's public keys or accidentally overwrite B's JWKS cache.

An unusual spike in unknown `kid` for one issuer should be investigated per issuer alias. Avoid aggregating metrics in ways that let Issuer B's traffic mask an outage on Issuer A.

## 16. Observability and Auditing for Multi-Issuer

With two trust domains, logs and metrics must distinguish issuers without exposing tokens or excessive personal data.

### 16.1. Recommended Metrics

| Metric | Bounded labels |
|---|---|
| JWT authentication attempts | issuer alias, outcome |
| JWT signature failures | issuer alias, failure category |
| Unknown issuer attempts | environment, outcome |
| JWKS fetch latency/errors | issuer alias |
| Audience validation failures | issuer alias, API alias |
| Tenant authorization denials | tenant alias, operation |
| Cross-tenant access denials | tenant alias, resource type |
| Repository queries by tenant | tenant alias, operation |
| Tenant cache hits/misses | tenant alias, cache type |

Never use raw JWTs, access tokens, subjects, emails, or token IDs as metric labels. Those values have high cardinality and may contain sensitive information.

### 16.2. Structured Authentication Logs

Example:

~~~text
event=jwt_authentication issuer=workforce outcome=success
event=jwt_authentication issuer=partner outcome=success
event=jwt_authentication issuer=unknown outcome=rejected
event=jwt_validation issuer=partner outcome=invalid_audience
event=tenant_authorization tenant=internal outcome=denied resource=order
event=tenant_authorization tenant=partner outcome=allowed resource=order
~~~

The issuer alias is an internal operational label mapped to a configured issuer URI. Never log full JWTs or `Authorization` headers.

### 16.3. Auditing Principal Identity

Audit records should identify the principal by issuer and subject or resolved local identity ID:

~~~json
{
  "actor": {
    "issuerAlias": "partner",
    "subject": "alice",
    "localUserId": 8891,
    "tenantId": "partner"
  },
  "action": "ORDER_READ",
  "resourceId": "1001",
  "outcome": "ALLOWED"
}
~~~

If `subject` is considered personal data under organizational policy, use a local ID or pseudonymous identifier in everyday logs; keep the detailed mapping only in a controlled-access system.

## 17. Cross-Tenant Access Incident Runbook

When a principal from Issuer A is found reading Tenant B's data:

1. Identify the request, issuer alias, subject/local identity, and resolved tenant.
2. Check the JWT audience and authorities verified by the decoder.
3. Check the issuer-to-tenant mapping and tenant claim policy.
4. Check whether controllers/services accepted a tenant ID from headers/paths/bodies.
5. Check whether repository queries include tenant predicates on read/update/delete/export/search.
6. Check whether cache keys are namespaced by tenant/issuer.
7. Check object storage paths, search indexes, and background jobs.
8. Check whether identity linking auto-linked on email/`sub`.
9. Temporarily disable affected endpoints or tenant paths if needed.
10. Collect audit evidence, identify accessed records, and follow the incident response process.

### 17.1. Distinguishing Authentication vs. Data Isolation Bugs

| Symptom | Layer to inspect |
|---|---|
| Token from unknown issuer accepted | Trusted issuer resolver/allowlist |
| Token A verified with key B | Decoder/JWKS namespace |
| Token A with audience B accepted | Audience validator |
| Partner role granted workforce privileges | Authority converter/policy |
| Colliding subject leaked profile | Identity key `(issuer, subject)` |
| Tenant header changed returned data | Tenant context resolver |
| `GET` is safe but export leaked | Export/search repository path |
| Request isolation is right but cache returned wrong data | Cache key/invalidation |
| WebFlux request received another request's tenant | `ThreadLocal`/context propagation |

### 17.2. Mitigation Actions

Depending on severity:

- Remove the issuer or tenant from the trusted registry if trust is compromised.
- Disable overly broad authority mappings.
- Enforce tenant predicates in repositories/services.
- Purge cache entries for affected namespaces.
- Revoke sessions/tokens or client credentials per issuer policy.
- Disable faulty account links and audit local identity mappings.
- Review audit logs to determine the scope of exposed data.

## 18. Two-Issuer Implementation Checklist

### 18.1. Trust and Token Validation

- [ ] Only the two approved issuers are in the allowlist.
- [ ] Issuers are compared by exact identifier.
- [ ] Unverified issuer is used only as a routing selector.
- [ ] Each issuer has its own decoder/JWKS source.
- [ ] Each issuer has its own audience validator.
- [ ] Signature, issuer, `exp`, `nbf`, and algorithm are verified.
- [ ] Only the access token profile is accepted by the API.
- [ ] Never fetch arbitrary metadata/JWKS URLs from tokens/requests.
- [ ] Unknown issuers are rejected before any outbound network call.

### 18.2. Identity and Tenant

- [ ] User identity is keyed by `issuer + subject`.
- [ ] Tenant mapping comes from a trusted registry or a policy-validated claim.
- [ ] Header/path/query tenant values do not self-grant tenant access.
- [ ] Account linking has a verified, audited workflow.
- [ ] Authorities are namespaced/mapped per issuer.
- [ ] Tenant membership is verified when required by the resource.

### 18.3. Data Access and Context

- [ ] Every repository query includes a tenant predicate.
- [ ] Read, insert, update, delete, export, and search are all isolated.
- [ ] Cache keys include the appropriate issuer/tenant/resource context.
- [ ] Object storage paths are constructed from trusted tenant identity.
- [ ] Search indexes and message consumers enforce tenant filters.
- [ ] Background jobs carry verified tenant context.
- [ ] WebFlux does not use `ThreadLocal` for tenant context.
- [ ] RLS (if used) is tested with connection pooling and transactions.

### 18.4. Testing and Operations

- [ ] Signed-token integration tests cover both issuers.
- [ ] Tests cover unknown issuer, wrong key, wrong audience, and expired tokens.
- [ ] Tests cover same-subject/same-`kid` collisions across both issuers.
- [ ] Tests cover tenant header tampering and cross-tenant record access.
- [ ] Tests cover authority collisions and account-linking behavior.
- [ ] Tests cover cache/search/storage/event tenant isolation.
- [ ] Metrics/logs distinguish issuers using bounded aliases.
- [ ] Runbooks exist for onboarding/offboarding and cross-tenant incidents.

## 19. Conclusion

Spring Security can support multiple issuers by selecting an `AuthenticationManager` based on the JWT's issuer. For two static issuers, a trusted issuer resolver is a clean starting point; when audiences, algorithms, or authority mappings differ, build dedicated managers/decoders per issuer and look them up from a static allowlist.

The unverified issuer claim is strictly a routing hint. The decoder must still verify signatures with the issuer's JWKS and validate issuer, audience, timestamps, algorithm, and access token profile. Never dynamically fetch metadata/JWKS from a token-supplied URL.

Data isolation begins after authentication: key principals by issuer plus subject, map tenants from trusted policy, namespace authorities by issuer, and add tenant predicates to every data access path. Caches, object storage, search, events, and background jobs must enforce the same tenant boundaries. In WebFlux, pass tenant identity explicitly or use configured Reactor Context; never use `ThreadLocal`.

**Allowing two issuers to call the same API does not mean the two issuers may see the same data.** Testing signed JWTs from both issuers alongside colliding subjects/`kid`s, wrong audiences, and tenant tampering is how you prove trust routing and data isolation operate independently.

## References

- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Multi-Tenancy](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html)
- [Spring Security — Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive Multi-Tenancy](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/multitenancy.html)
- [Spring Security — JwtIssuerAuthenticationManagerResolver Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerAuthenticationManagerResolver.html)
- [Spring Security — JwtIssuerReactiveAuthenticationManagerResolver Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerReactiveAuthenticationManagerResolver.html)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
