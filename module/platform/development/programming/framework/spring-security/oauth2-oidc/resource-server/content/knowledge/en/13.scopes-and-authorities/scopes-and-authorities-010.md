# Permissions Snapshotted at Token Issuance and Subsequent Permission Changes

## 1. Why does a JWT still carry permissions after an administrator revokes a role?

In a **Spring Security OAuth 2.0/OIDC Resource Server** system, the Authorization Server (AS) may issue a JWT access token containing the permissions/scopes granted at issuance time. The Resource Server uses signatures and token validators to authenticate the token, then maps scopes into **GrantedAuthority** instances for the request.

Illustrative JWT payload:

~~~json
{
  "iss": "https://auth.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "client_id": "shop-web",
  "scope": "orders.read orders.write",
  "iat": 1910000000,
  "exp": 1910001200
}
~~~

At the moment the token was issued, the user had permission to edit orders. Later, an administrator revokes edit permission in the identity/authorization store. **The old JWT does not mutate on its own**, because its contents are already signed. If the API only checks signature, expiration, and scopes read from the token, this token can still be accepted for edit operations until it expires or is blocked by an additional revocation mechanism.

This is the difference between two points in time:

- **Issuance time:** the Authorization Server decides whether to issue a token and which claims to put inside it.
- **Request time:** the Resource Server validates the token and enforces resource access policies at the moment the client sends a request.

**Core principle:** a valid JWT signature proves the token matches a trusted issuer's key and its contents have not been altered since signing. It **does not prove** that permissions or memberships in systems external to the JWT have remained unchanged up to the present moment.

## 2. What is actually a snapshot?

When issuing a JWT, the Authorization Server may record data such as:

| Claim | Purpose | Automatically refreshes after issuance? |
|---|---|---|
| **iss** | Issuer identifier | No |
| **sub** | Subject identifier within the issuer's scope | No |
| **aud** | Intended recipient/resource | No |
| **scope** or **scp** | Permission ranges granted to the token | **No** |
| **roles** or **groups** | Roles or groups if the issuer uses custom claims | **No** |
| **permissions** | Fine-grained permissions if the issuer uses custom claims | **No** |
| **tenant_id** | Tenant context if included in the profile | No |
| **iat** | Timestamp when the token was issued | No |
| **exp** | Token expiration timestamp | No |
| **jti** | Token identifier, if present | No |

A signed JWT is immutable data to the client. To change the scopes in a token, the AS must **issue a new token**, or the API must enforce additional policies outside the token's contents.

Not every JWT access token contains **roles**, **groups**, or **permissions** claims. Those are typically custom claims. Scope has specific OAuth 2.0 semantics: it represents the permission range **granted to the access token/client** per the grant, not necessarily the full list of user roles in the database.

### Scope, role, and per-resource operational permission are not the same

For example, a user holds an order-management role in the internal system, while the client only obtained a read scope:

~~~text
Current user role:       ORDER_MANAGER
Allowed client grants:   orders.read, orders.write
Actual token scope:      orders.read
Specific order policy:   may only edit orders belonging to the user's tenant
~~~

The Resource Server must not treat role, grant, and scope as one and the same value. A token with only **orders.read** does not gain write access just because the database recently added a role; conversely, a token with **orders.write** should not bypass live membership checks if the system requires role revocation to take effect immediately.

## 3. Timeline when permissions are revoked after token issuance

Suppose a hypothetical timeline in UTC:

| Time | Event | Impact |
|---|---|---|
| 09:00 | AS issues access token with **orders.read**, **orders.write**, expiring at 09:20 | JWT carries a snapshot of the grant at 09:00 |
| 09:05 | Admin revokes the user's order-edit permission | Current permission store no longer has write access |
| 09:06 | Client sends old JWT to PUT /api/orders/42 | Token still contains write scope |
| 09:06 | API checking only JWT scope | May allow, while token remains valid |
| 09:06 | API also checking current membership/permissions | May deny the operation |
| 09:20 | JWT expires | Decoder rejects token based on expiration |
| After 09:20 | Client requests a new token | AS must re-evaluate permissions/grant per current policy |

~~~mermaid
sequenceDiagram
    participant Admin
    participant AS as Authorization Server
    participant Client
    participant RS as Resource Server
    participant DB as Current Permissions

    Client->>AS: Request access token
    AS->>DB: Read roles and grants
    DB-->>AS: orders.write granted
    AS-->>Client: JWT scope=orders.write, exp=T+20m
    Admin->>DB: Revoke orders.write permission
    Note over Client,RS: Old signed JWT still retains original scope
    Client->>RS: PUT /api/orders/42 with old JWT
    RS->>RS: Verify signature, iss, aud, exp
    RS->>RS: Create authority SCOPE_orders.write
    RS->>DB: Check current permissions if policy requires
    DB-->>RS: No longer has edit permission
    RS-->>Client: Deny per domain authorization
~~~

**Stale window** is the period after permissions change during which a system may still accept stale permission decisions. With scope-only JWTs, that window usually relates to **remaining token lifetime**, clock skew tolerances, and any supplementary revocation mechanisms.

Note: the AS itself may also cache old roles and keep issuing new tokens with old scopes. In that case, merely shortening access-token lifetime **is not enough**. The system must also ensure fresh issuances read current grant state.

## 4. What Spring Security actually does with JWT scopes

In a Servlet Resource Server, the typical steps are:

~~~text
HTTP Authorization: Bearer <JWT>
          |
          v
BearerTokenAuthenticationFilter
          |
          v
BearerTokenAuthenticationToken (unauthenticated)
          |
          v
JwtAuthenticationProvider
          |
          v
JwtDecoder: verify signature + JWT validators
          |
          v
JwtAuthenticationConverter
          |
          v
JwtAuthenticationToken (authenticated)
  GrantedAuthority: SCOPE_orders.read
  GrantedAuthority: SCOPE_orders.write
          |
          v
AuthorizationFilter / method security
~~~

By appropriate default, **JwtGrantedAuthoritiesConverter** maps scopes in claims like **scope** or **scp** to authorities prefixed with **SCOPE_**.

Example:

~~~json
{
  "scope": "orders.read orders.write"
}
~~~

typically corresponds to:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

With configuration:

~~~java
.requestMatchers(HttpMethod.PUT, "/api/orders/**")
    .hasAuthority("SCOPE_orders.write")
~~~

Spring Security checks authorities generated from **the request's verified JWT**. It **does not automatically call the Authorization Server, database, or role service** to ask whether write permission was just revoked.

A common misconception is thinking every request passing through JwtDecoder automatically synchronizes all live permissions. In reality, the decoder handles **credential validity** and configured validators; synchronizing current authorization requires its own design.

### The SCOPE_ convention differs from ROLE_

- **hasAuthority("SCOPE_orders.write")** checks an authority derived from an OAuth scope.
- **hasRole("ADMIN")** typically uses an authority prefixed with **ROLE_** per Spring Security convention.
- A custom claim **roles: ["ADMIN"]** is not automatically mapped to ROLE_ADMIN by the default scope converter.

If the provider has a custom role claim, you can customize **JwtAuthenticationConverter** to convert it into authorities after the token is verified. However, **mapping more roles from a JWT does not make the role snapshot update itself**.

## 5. Configuring the Resource Server to validate tokens before authorization

Spring Boot example:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/shop
~~~

Illustrative security chain:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrdersApiSecurity {

    @Bean
    SecurityFilterChain ordersApi(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.read")
                        .requestMatchers(HttpMethod.PUT, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.write")
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

This configuration represents **token-scope-based authorization**, not real-time entitlement lookup.

To accept access tokens safely, the Resource Server needs a clear contract:

1. Who is the trusted issuer?
2. Which JWS algorithm and key source verify the JWT?
3. Is the token unexpired and matching the API's **audience**?
4. Is it genuinely an **access token**, rather than an OIDC ID token or a JWT for another purpose?
5. Do the scopes/authorities match the endpoint?
6. Are **live permissions for the specific resource** required?

Setting only **issuer-uri** does not automatically fulfill all audience or token-purpose validations. Those rules can be configured in **JwtDecoder** and appropriate **OAuth2TokenValidator<Jwt>** implementations.

### Example adding an audience validator

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Bean
JwtDecoder jwtDecoder() {
    String issuer = "https://auth.example.com/realms/shop";

    NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withIssuerLocation(issuer).build();

    OAuth2TokenValidator<Jwt> defaults =
            JwtValidators.createDefaultWithIssuer(issuer);

    OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error(
                                "invalid_token",
                                "Incorrect audience",
                                null));

    decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                    defaults, audience));
    return decoder;
}
~~~

This example illustrates the **authentication/token validation** layer. When using **setJwtValidator**, retain issuer, timestamp, and required token-profile checks, because calling this replaces the decoder's validator set.

**Do not put all business authorization decisions inside the JWT decoder.** Order edit permissions depend on state and membership that can change per request; they usually fit better in method/domain authorization. Only place freshness/revocation checks in the decoder when that is an explicitly designed authentication policy backed by a trusted state source.

## 6. Approach 1: combine JWT scopes with live permissions at request time

A solution for systems sensitive to permission changes is to treat token scope as an **upper bound** on the grant while checking current permissions:

~~~text
allow =
    valid token for the right API
    AND token has required scope
    AND principal still holds live permission
    AND principal has permission on the specific resource
~~~

Example when a user's write role is revoked:

~~~text
Old JWT:
  scope = orders.read orders.write

Current role store:
  user no longer has EDIT_ORDER

HTTP:
  PUT /api/orders/42

Outcome:
  JWT signature may be valid
  Token still has SCOPE_orders.write
  Yet domain policy returns DENY
~~~

### Method security in Spring Security

Enable method security:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Combine scope and policy bean:

~~~java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class OrderCommandService {

    @PreAuthorize(
        "hasAuthority('SCOPE_orders.write') " +
        "and @orderPermission.canEdit(authentication, #orderId)")
    public void updateOrder(
            @P("orderId") String orderId,
            OrderPatch patch) {

        // Perform update inside transaction/domain service.
        // OrderPatch is an application DTO type.
    }
}
~~~

Policy bean checking current entitlement:

~~~java
import java.net.URI;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Component;

@Component("orderPermission")
public class OrderPermission {

    private final MembershipService membershipService;

    public OrderPermission(MembershipService membershipService) {
        this.membershipService = membershipService;
    }

    public boolean canEdit(
            Authentication authentication,
            String orderId) {

        if (!(authentication instanceof JwtAuthenticationToken jwtAuth)) {
            return false;
        }

        Jwt jwt = jwtAuth.getToken();
        URI issuer = jwt.getIssuer();
        String subject = jwt.getSubject();

        if (issuer == null || subject == null || subject.isBlank()) {
            return false;
        }

        // MembershipService is an application-defined domain component.
        // Look up principal by (issuer, subject), checking exact order and tenant.
        return membershipService.hasCurrentEditPermission(
                issuer.toString(), subject, orderId);
    }
}
~~~

These two Java snippets only illustrate extension points: **OrderPatch**, **MembershipService**, repositories, and transactions must be implemented per the real domain.

Points to note:

- Authentication must be verified by the Resource Server; never extract **sub** from a merely Base64URL-decoded JWT.
- With multiple issuers, use **(iss, sub)** instead of username, email, or bare subject.
- Membership lookup must bind to the relevant **resource and tenant**, not just a generic role.
- **@PreAuthorize** works when method security is enabled and calls go through the Spring proxy. When referencing parameters in SpEL, ensure parameter names are accessible—for example via **@P("orderId")** above.
- Do not assume checking permissions before an update eliminates all races. Under concurrent data access, transactions, locking/versioning, or write-time enforcement are still required.
- If domain checks use a cache, revocation takes effect according to **cache freshness**, not necessarily the instant the database updates.

### What happens when new permissions are granted?

The old JWT lacks **orders.write**, even though the database just granted write permission. The **scope AND current policy** expression still rejects the old token due to the missing scope. The client needs a new access token issued with the appropriate grant. This is intentional behavior of the **token scope as upper bound** model: granting a new role does not silently elevate an already-issued bearer credential.

If the product requirement is "new permissions take effect immediately without a new token", design authorization around a different contract—for instance, tokens carrying identity and a very coarse scope while action decisions depend entirely on the live PDP. Never skip scope checks without considering the grant boundaries set by the Authorization Server.

## 7. Approach 2: short-lived JWT access tokens

A simple strategy is shortening the access token's lifetime:

~~~text
Token lifetime = 5 minutes
Admin revokes permission right after token was issued

If Resource Server uses only JWT scopes:
  the old permission may still be used
  for the remaining lifetime of the token
  (plus related clock-skew/tolerance effects)
~~~

**Short-lived JWTs bound the stale window rather than making permissions change instantaneously.**

Advantages:

- Resource Server can verify JWTs offline.
- Low latency, minimal network dependencies.
- Stolen tokens also have a shorter usable window.

Trade-offs:

- Clients must request new access tokens more frequently.
- Authorization Server carries higher refresh/token-issuance load.
- Immediate revocation of a permission is not guaranteed.
- If the AS reads stale roles from cache or keeps old grants during refresh, new tokens may still contain scopes that should not be granted.

### Refresh tokens do not automatically invalidate old access tokens

In OAuth 2.0, a **refresh token** is sent by the client to the AS to obtain a new access token; the Resource Server does not use refresh tokens to authenticate business requests.

When a role is revoked:

- The AS can re-evaluate scopes/grants when issuing a new access token.
- The AS can revoke or restrict the refresh grant.
- However, already-issued JWT access tokens can remain cryptographically valid until **exp** or until the Resource Server enforces an additional rejection mechanism.

In particular, **logout**, **revoking a refresh token**, and **revoking all issued access tokens** are not automatically synonymous.

## 8. Approach 3: opaque access tokens and introspection

Instead of self-contained JWT access tokens, the AS can issue **opaque tokens**. The Resource Server uses **RFC 7662 Token Introspection** to query a trusted endpoint for status and metadata:

~~~json
{
  "active": true,
  "sub": "user-42",
  "client_id": "shop-web",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "exp": 1910001200
}
~~~

An illustrative Spring Boot configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.com/oauth2/introspect
          client-id: orders-api
          client-secret: YOUR_SECRET_FROM_SECURE_CONFIGURATION
~~~

This configures an introspection connection: the Resource Server can query the AS about tokens over an authenticated channel. Still, distinguish three models the AS might implement:

| AS introspection policy | Outcome when a role is revoked |
|---|---|
| Returns scopes attached to the token at issuance time | Old scopes may still appear even with **active=true** |
| Marks related access tokens **active=false** | API rejects on the next introspection call |
| Recomputes permissions/metadata per current policy | API can receive up-to-date permissions per AS contract |

**Introspection does not automatically guarantee roles are recomputed.** That is part of the contract with the Authorization Server. If the response has **active=true**, the API must still check audience, token type/purpose, scope, and business permissions.

### Introspection caching can cause staleness

If the API caches an **active=true** response for 60 seconds, the AS may have revoked the token while the API still sees the stale result until cache expiry or invalidation. Therefore:

~~~text
Actual revocation delay
  = AS updates token state
    + API/proxy introspection cache staleness
    + event/replication delay (if any)
~~~

Specify maximum cache TTL, invalidation mechanisms, and behavior when the introspection endpoint is unavailable. Never write "immediate revocation" in system requirements when the actual policy tolerates 60 seconds of staleness.

## 9. Approach 4: access-token denylist by jti

A JWT can include **jti** to identify an individual token:

~~~json
{
  "iss": "https://auth.example.com/realms/shop",
  "sub": "user-42",
  "aud": "orders-api",
  "jti": "token-93a6",
  "scope": "orders.read orders.write",
  "exp": 1910001200
}
~~~

If a token must be revoked before expiration, the API can maintain a denylist:

~~~text
Key: (issuer, jti)
Value: revoked
Expiry: token exp + appropriate clock tolerance
~~~

When a request arrives:

~~~mermaid
flowchart TD
    A["Request with JWT"] --> B["Verify signature, issuer, audience, time"]
    B --> C{"Is JWT valid?"}
    C -- "No" --> X["Reject"]
    C -- "Yes" --> D["Check denylist (iss, jti)"]
    D --> E{"Is token revoked?"}
    E -- "Yes" --> X
    E -- "No" --> F["Evaluate scope + domain permissions"]
    F --> G{"Sufficient permissions?"}
    G -- "Yes" --> H["Allow"]
    G -- "No" --> Y["Reject authorization"]
~~~

Design considerations:

- Does the AS issue sufficiently unique **jti** values per issuer/token family?
- Does revocation target **one token**, **one session**, **one user**, or **an entire client**?
- Do all Resource Servers share denylist data or observe revocation events in time?
- When the denylist store is unavailable, are sensitive operations denied?
- Is there cleanup for entries after token expiration?
- Is storing raw access tokens in storage/logs avoided?

Denylisting a single **jti** does not automatically revoke all of a user's access tokens. If an admin only changes a role, decide which tokens are affected or use live permission checks instead of trying to enumerate every jti.

Trade-off: a denylist introduces a **stateful validation dependency** in the Resource Server, even though the JWT remains self-contained and signed.

## 10. Approach 5: authorization version and tokens-valid-after

One way to reduce the need to enumerate individual tokens is for the AS to record the version of the authorization policy/grant:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": "orders-api",
  "authz_version": 17,
  "scope": "orders.write",
  "exp": 1910001200
}
~~~

When an admin revokes permissions:

~~~text
authz_version in JWT = 17
current version in policy store = 18

=> old token no longer satisfies freshness policy.
~~~

**authz_version is a custom claim**, not a mandatory OAuth 2.0 or JWT field. It only has meaning if both the AS and the API commit to its semantics.

Pseudocode:

~~~java
// PSEUDOCODE: omits tenant/grant keys, null/type handling,
// caching, fail-closed, and race-condition policies.
boolean currentVersionAllows(Jwt jwt) {
    String issuer = jwt.getIssuer().toString();
    String subject = jwt.getSubject();
    Integer tokenVersion = jwt.getClaim("authz_version");
    Integer latest = versionStore.loadCurrent(issuer, subject);
    return tokenVersion != null && tokenVersion.equals(latest);
}
~~~

Scope the version by **(issuer, subject)**—or more narrowly by tenant/client/grant if targeted revocation is needed—and increment the version atomically whenever policy changes. The Resource Server must read the latest version or use a cache with bounded staleness.

Another variant compares **iat** against a trusted **permissionsChangedAt/tokensValidAfter** timestamp. This variant must handle clock skew, timestamp resolution, concurrent events, and replication. By itself, **iat** does not prove a token holds the latest permissions; only when compared against a live policy-change marker can it serve as a freshness check.

## 11. Approach 6: policy decision point at request time

If business rules involve complex **RBAC, ABAC**, tenants, ownership, approval workflows, or resource states, the Resource Server can query a **Policy Decision Point (PDP)** or domain authorization service.

Decision inputs can include:

~~~text
Authenticated principal = (issuer, subject)
Client ID = shop-web
Token scopes = orders.write
Action = EDIT_ORDER
Resource ID = order-42
Tenant = tenant-blue
Current resource state = DRAFT
Context = time, channel, risk signal, ...
~~~

PDP returns:

~~~json
{
  "allow": false,
  "reason": "membership_revoked"
}
~~~

Conditions:

1. The JWT must be authenticated before sending principal/claims to the PDP.
2. The PDP must query a **trusted permission source** and service-to-service communication must be secured.
3. Decision cache keys must be specific enough across principal, action, resource, tenant, and critical policy factors.
4. Timeouts and failure modes must be defined (typically **fail-closed** for sensitive operations).
5. If **allow** responses are cached, permissions can still remain stale until TTL expires or the cache is invalidated.

In Spring Security, this can integrate at **AuthorizationManager**, method-security expressions, or service/domain policies. You do not need a custom JWT servlet filter running in parallel with Resource Server to do this.

## 12. Caching and permission revocation delay

Even when domain authorization queries live permissions, multiple layers can cache:

- Self-contained claims inside the access token.
- Cached introspection responses.
- Membership caches inside the Resource Server.
- JWT/session state at the gateway.
- Authorization policy decision caches.
- Caches at the identity broker/AS.
- Event-driven replicas of the permission store.

Example:

~~~text
09:05:00 Admin revokes role.
09:05:01 Primary DB updated.
09:05:03 Authorization event reaches replicas.
09:05:30 API allow-decision cache expires.
09:05:31 New requests begin being blocked.
~~~

The effective revocation delay in the example is **tens of seconds**, not instantaneous upon DB commit.

If the organization requires "revoked permissions take effect within 10 seconds maximum", define the mechanism guaranteeing that bound rather than merely stating "the API caches permissions".

### Properly scoped cache keys

Avoid caching:

~~~text
key = user-42
value = allow
~~~

when the decision actually depends on action, tenant, resource, client, or scope.

A better key may include:

~~~text
issuer + subject + tenant + action + resource + policy_version
~~~

However, more detailed keys consume more memory; balance this against risk policy and system scale. To avoid stale permissions, skip caching **allow** decisions for sensitive operations or use a very short TTL.

### Event-driven invalidation

An authorization store may emit events:

~~~json
{
  "type": "PermissionChanged",
  "issuer": "https://auth.example.com",
  "subject": "user-42",
  "tenant": "tenant-blue",
  "authzVersion": 18
}
~~~

APIs invalidate caches upon receiving the event. However, events can arrive late, be delivered twice, or arrive out of order. You need versions/sequences, reconciliation, and handling for missed events. Never treat publishing an event as synonymous with every API having stopped trusting old decisions.

## 13. New permissions granted after token issuance

Newly granted permissions are also affected by snapshotting.

~~~text
10:00 Token issued with scope = orders.read
10:05 Admin grants orders.write permission
10:06 Client calls PUT /api/orders/42 with old JWT
~~~

If the API requires **SCOPE_orders.write**, the old token still lacks this scope. The domain store may have granted the write role, yet the scope inside the token has not increased.

With the policy:

~~~text
allow = token_scope_has_write AND current_permission_has_write
~~~

the result is still **deny**. The client must obtain a **new access token** with the write grant allowed by the AS.

Still, "being granted a new role" does not mean the AS will automatically add the new scope: it also depends on **client permissions**, **user consent**, **grant policies**, **audience**, and whether the AS has received the role update yet.

Distinguish clearly:

- **Current role of the user/client.**
- **Scopes the client is allowed to request.**
- **Scopes granted by the AS to the specific access token.**
- **Action permissions at the Resource Server.**

If new permissions must take effect without issuing a new token, design a dedicated policy allowing dynamic decisions within grant boundaries; never arbitrarily ignore the scope granted to the token.

## 14. User tokens vs. client-credentials tokens

Access tokens do not always represent an end-user. With **client_credentials**, a token can represent a service:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "inventory-sync",
  "client_id": "inventory-sync",
  "aud": "orders-api",
  "scope": "orders.sync",
  "exp": 1910001200
}
~~~

When an admin revokes permissions for the **inventory-sync** service, old JWT tokens can still carry **orders.sync** until they are no longer accepted.

Decisions to make:

- Principal type: user, service, or delegation?
- Should live client status be checked?
- Does revoking a client secret/credential also render old access tokens inactive?
- Which endpoints may scopes in a service token call?
- If a service is disabled, is that checked via introspection/version/PDP or short TTL?

Never treat **sub** as a user ID by default; subjects must be interpreted according to the issuer and token profile.

**DPoP** or **mTLS sender-constrained tokens** help prevent token use by parties lacking the bound key. However, proof-of-possession **does not update role claims** after revocation.

## 15. Multi-tenant and object-level authorization

A JWT might state:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": "orders-api",
  "scope": "orders.read orders.write",
  "tenant_id": "tenant-blue",
  "roles": ["ORDER_MANAGER"]
}
~~~

If the user is removed from **tenant-blue** after the token was issued, the tenant/role claims can still hold old values.

The Resource Server needs to verify:

1. Token is valid and intended for **orders-api**.
2. Has **orders.write** for edit endpoints.
3. Which local principal does **(iss, sub)** map to?
4. Does the principal still hold active membership in the tenant?
5. Which tenant does the order actually belong to, who is the owner, and does its state permit editing?
6. Are the permission check and write operation inside a boundary guaranteeing appropriate consistency?

Never look solely at **tenant_id** in the JWT to infer the user may edit every order in that tenant. Tenant claims and permissions may reflect state at issuance time, while the resource changed afterward.

## 16. Logout, account lock, and password change

Many administrative events are related, yet affect access tokens differently:

| Event | Direct effect | Do issued JWT access tokens automatically become invalid? |
|---|---|---|
| User logs out of browser/app | Session/client state changes | **No by default** |
| Refresh token is revoked | Prevents or restricts requesting new access tokens | **No by default** |
| User is disabled | Account status changes | No, if the API only verifies JWTs offline |
| User changes password | Login credentials change | No by default |
| Admin revokes role | Authorization store changes | No by default |
| Access token expires per **exp** | JWT is no longer time-valid | Yes, when the decoder checks expiration |
| Token **jti** is placed on denylist | API has an additional rejection policy | Yes, if the check is enforced consistently |
| Introspection returns **active=false** | AS considers token no longer active | Yes, when the API uses fresh results and ignores stale cache |
| Current permission is revoked | Domain policy returns deny | Denies operation per dynamic policy |

Therefore, if a requirement states "locking an account immediately blocks all administrative operations", explicitly design **account-state checks**, **revocation**, or **version freshness**—never just emit a logout event and wait for access tokens to change themselves.

### Key rotation is not a way to revoke a role

Rotating signing keys or removing a public JWK from JWKS can break **large numbers of tokens** sharing that key. This is not an appropriate mechanism to revoke one role from a normal user.

**Key rotation** belongs to the cryptographic key lifecycle. **Token revocation/current entitlement** belongs to the permission and session/grant lifecycle. Keep the two problems separate. Compromised private signing keys require their own emergency response.

## 17. Authentication failure or authorization failure?

When a token is no longer accepted, the Resource Server response is typically an **authentication** error; when a token is valid yet lacks permissions, it is typically an **authorization** error:

| Scenario | Rejection point | Typical HTTP status |
|---|---|---|
| Missing Bearer credential on an authenticated endpoint | Authentication entry point | 401 |
| Expired JWT or invalid signature | JwtDecoder | 401, typically **invalid_token** |
| JWT has wrong issuer/audience/token purpose | Jwt validators | 401 |
| JWT is on denylist, treated as revoked token | Token acceptance policy | Typically 401 |
| Valid JWT missing **orders.write** | Authorization | Typically 403, possibly **insufficient_scope** |
| JWT has scope, but tenant membership is gone | Domain authorization | Typically 403, per policy |
| User disabled, checked at authentication | Token/account policy | Typically 401 |
| User disabled, checked at domain authorization | Domain policy | Typically 403 |

Examples:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

and:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

Exact responses depend on **BearerTokenAuthenticationEntryPoint**, **BearerTokenAccessDeniedHandler**, and handlers configured by the application. Never return JWT contents, raw Authorization headers, or sensitive role-database details in error bodies.

## 18. Choosing a solution by permission-freshness requirements

| Design | Stale permission window | Cost / dependencies | When it may fit |
|---|---|---|---|
| JWT scope + relatively long TTL | Up to expiration | Low, offline verification | Rarely changing permissions, low impact |
| Short JWT TTL + AS recomputes permissions on refresh | Bounded by TTL, clock skew, and AS freshness | More frequent token requests | Bounding staleness without querying DB per request |
| JWT scope + live domain authorization | Follows permission store/cache freshness | DB/PDP lookup | Tenant, ownership, and roles change frequently |
| JWT + denylist **(iss, jti)** | Follows denylist write/read latency | Shared store and invalidation | Revoking specific access tokens |
| JWT + authorization version | Follows version lookup freshness | Shared version store | Invalidating groups of tokens by subject/grant/tenant |
| Opaque + introspection | Follows AS semantics and cache TTL | Network/cache dependent on AS | Centralized token status needed |
| Policy Decision Point at request time | Follows store/decision cache freshness | Depends on PDP | Complex authorization needing fast effect |

Example choices by business sensitivity:

- **Reading product catalog:** JWT scope and token lifetime may suffice.
- **Reading order data:** add ownership/tenant checks.
- **Editing orders:** add current membership and order state checks.
- **Approving critical transactions:** may require live authorization, token freshness, and additional context checks.
- **Emergency account lockout:** requires an explicit revocation SLA, never just waiting for JWT expiration.

There is no single optimal lifetime or TTL for every application; choose based on risk model, revocation SLA, and infrastructure capabilities.

## 19. Test design: distinguishing token snapshots from live permissions

Scenarios to state clearly when building policies (these are **not executed test results**):

| Input / action | Expectation using only JWT scope | Expectation when adding live permissions |
|---|---|---|
| Unexpired JWT with write, membership still has write | May allow | Allows if resource matches |
| Unexpired JWT with write, membership was just revoked | **May still allow** | Denies |
| Unexpired JWT with only read, user was just granted write | Rejects PUT | Still rejects if token is required to have write scope |
| Expired JWT while membership still has write | Rejects | Rejects |
| JWT with wrong audience yet valid role | Must reject with audience validation | Must reject |
| ID token from same issuer with admin role | Must not be accepted as access token | Must not be accepted |
| JWT has write, order transitions to LOCKED state | May not know if checking scope alone | Denies per domain rule |
| JWT has write, jti was just revoked | Needs additional revocation check | Denies if token policy has denylist |
| Opaque active=true while role was revoked | Depends on AS introspection contract | Denies if live policy blocks |
| Two tenants with identical subject string across two issuers | Collision risk if looking up bare sub | Distinguish principals by (iss, sub) |
| Multiple API instances caching permissions differently | May show inconsistent behavior | Needs bounded staleness/invalidation |

When designing integration tests, distinguish **mocked authorization** tests from real **JWT decoder and Resource Server filter** tests. Spring Security Test has a post-processor that builds a fake JWT authentication to test permissions, but that does not prove issuer, signature, or audience validation works in production.

In STEP 4, this section only describes scenarios and responsibilities; it does not execute a test suite or evaluate runtime results.

## 20. Diagnosing "permission was revoked, yet the API still allows it"

An investigation flow:

~~~text
[1] Was the JWT issued before or after revocation?
            |
            v
[2] Is the JWT still unexpired, and which scopes does it carry?
            |
            v
[3] Does the API actually check audience, issuer, and token type?
            |
            v
[4] Which authorities does JwtAuthenticationToken hold?
            |
            v
[5] Does the endpoint use only hasAuthority, or also a domain policy?
            |
            v
[6] Which source does the domain policy query for permissions?
            |
            v
[7] Are there caches / stale replicas / event delivery delays?
            |
            v
[8] If newly issued tokens still hold old permissions, which grant is the AS using?
            |
            v
[9] Are revocation/denylist/version checks being executed?
~~~

Common symptoms:

| Symptom | Likely cause |
|---|---|
| Old access token still has **SCOPE_orders.write** | Scope snapshot in JWT |
| New token is still issued write scope after role revocation | AS keeps old grant, caches old role, or policy is out of sync |
| API A denies, API B still allows | Differing authorization contracts or caches |
| Introspection returns inactive, yet API still allows | Caching or request path bypasses introspection |
| Domain policy is written, yet edits still succeed | Method security did not run, self-invocation, wrong resource/tenant, race |
| Newly added role still yields 403 on old JWT | Token lacks the new scope |
| Role revocation takes effect only after 30 seconds | Cache TTL, replicas, or event delay |
| Old access token still works after logout | No access-token revocation policy |

Log **request ID, error code, configured issuer, policy name, and normalized decision reason**. Never log raw Bearer tokens, JWT signatures, Authorization headers, refresh tokens, or introspection secrets.

## 21. Misconceptions and anti-patterns to avoid

| Misconception / wrong approach | Problem | Design direction |
|---|---|---|
| "As long as the JWT is unexpired, the role is still valid." | JWT has no live link to the role store | TTL/revocation/live policy |
| "JwtDecoder automatically refreshes permissions from the AS." | Default decoder verifies tokens/validators | Build a dedicated live entitlement policy |
| "hasAuthority is a live role lookup." | It reads authorities from Authentication | Add method/domain authorization if needed |
| "Revoking the refresh token is enough to block old access tokens." | Old JWT access tokens can remain valid | Define an access-token revocation policy |
| "Opaque introspection always returns updated scopes." | Depends on AS semantics/caching | Clear AS contract and bounded cache |
| "When a new role is granted, the old token automatically gains the new scope." | Signed tokens do not mutate scopes | Request a new token or design dynamic policy |
| "Having tenant_id in the JWT means access to all orders in the tenant." | Membership/resource state may differ | Object-level authorization |
| "A disabled user means an invalid JWT signature." | Signature and account state are separate issues | Token/account freshness checks |
| "Rotate the signing key to revoke a role." | Affects unrelated users/tokens | Denylist/version/permission policy |
| "Use a separate JWT filter to load roles on every request." | Overlaps Resource Server authentication | Keep standard JWT auth; check dynamic authz at the right layer |
| "One user-keyed allow cache is enough." | Permission outcomes depend on action/resource/tenant | Key caches by policy context |
| "If the permission DB errors out, allow by default." | Turns outages into authorization bypasses | Fail-closed for sensitive operations |
| "DPoP fixes stale scopes." | Sender binding does not refresh permissions | Combine with revocation/live authorization |
| "Check sub only; issuer is unnecessary." | Subjects are scoped to an issuer | Use verified (iss, sub) |

## 22. Coordination contract between Authorization Server and Resource Server

A trustworthy design must align on **permission semantics**, not just a field named **scope**.

**The Authorization Server must publish/specify:**

1. Which roles/grants determine scope issuance?
2. Does it issue JWT or opaque access tokens?
3. Token lifetimes and clock-skew contracts?
4. When permissions change, are old access tokens revoked/inactivated or left valid?
5. Are grants refreshed when issuing tokens via refresh?
6. Does it support **jti**, token revocation, version claims, or introspection?
7. Do introspection **active** and scope reflect issuance-time state or live permissions?
8. Is there a committed maximum cache/replication delay?

**The Resource Server must specify:**

1. Which issuers/JWKS/introspection endpoints are trusted?
2. Which audiences, algorithms, and access-token profiles are accepted?
3. How are scopes converted into authorities?
4. Which endpoints may rely on the token scope snapshot?
5. Which endpoints must check live membership/resource permissions?
6. What are the revocation SLA and cache TTLs?
7. How should unavailability of revocation/PDP/DB be handled?
8. How do authentication errors differ from authorization errors?
9. Do audit logs protect identifying/token data?
10. Is behavior aligned when **granting additional** permissions after token issuance?

**Clear SLAs** guide architecture choices: "a revoked role must block order-editing operations within at most 15 seconds" is an implementable and testable engineering requirement; saying "permissions will update themselves" is not concrete enough.

## 23. Principles to remember

~~~text
T_issue:
  Authorization Server issues JWT
  Scope/roles recorded in JWT = data at issuance time

T_request:
  Resource Server receives JWT
  Scope/roles in JWT do not update automatically

Snapshot-only policy:
  allow = valid_token
          AND token_scope
          AND endpoint_rule

Hybrid current-state policy:
  allow = valid_token
          AND token_scope
          AND current_entitlement
          AND resource_policy
~~~

Core principles:

1. **Permissions/scopes in a JWT are a snapshot from token issuance.** Role databases can change afterward.
2. **Revoked permissions do not vanish from old JWTs.** Tokens must expire or be rejected by an additional mechanism.
3. **JwtAuthenticationConverter does not look up new permissions.** It converts verified claims into request authorities.
4. **Granting new permissions does not add scopes to old JWTs.** A new token must be issued with the right grant, or the system needs a different dynamic-authorization contract.
5. **Short JWT lifetimes shrink the stale window**, yet do not guarantee instant revocation and cannot fix an AS that keeps issuing stale tokens.
6. **Opaque introspection, denylists, versioning, and domain/PDP lookups** each carry trade-offs; document semantics and caching explicitly.
7. **Authentication and authorization are separate decisions.** A validly signed, unexpired token can still be denied due to current permissions.
8. **Principal, tenant, and object ownership must be checked within proper boundaries**; never rely solely on sub/role claims.
9. **Revocation SLAs** must be built with measurable mechanisms, not by expecting tokens to sync themselves.
10. **Keep Resource Server as the primary authentication path**, placing dynamic permission policies at proper extension points instead of writing a parallel JWT filter.

**Conclusion:** if a product accepts stale permissions remaining active for a bounded window, JWT scopes + an appropriate lifetime can be an effective choice. If role revocation must take effect immediately or nearly immediately, the Resource Server must have a trusted live state source at request time or a mechanism to revoke issued tokens. A JWT itself cannot reflect a permission change that happened **after the moment it was signed**.

## 24. References

- **RFC 6749 — The OAuth 2.0 Authorization Framework:** access tokens, scopes, refresh tokens, and grants. https://www.rfc-editor.org/rfc/rfc6749
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** Bearer token usage, invalid_token, and insufficient_scope. https://www.rfc-editor.org/rfc/rfc6750
- **RFC 7519 — JSON Web Token:** iat, exp, iss, sub, and jti claims. https://www.rfc-editor.org/rfc/rfc7519
- **RFC 7662 — OAuth 2.0 Token Introspection:** active status and access token metadata. https://www.rfc-editor.org/rfc/rfc7662
- **RFC 7009 — OAuth 2.0 Token Revocation:** protocol-level token revocation mechanism. https://www.rfc-editor.org/rfc/rfc7009
- **RFC 8725 — JWT Best Current Practices:** validating issuer, audience, and preventing token-type confusion. https://www.rfc-editor.org/rfc/rfc8725
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** requirements for JWT access tokens. https://www.rfc-editor.org/rfc/rfc9068
- **Spring Security — OAuth 2.0 Resource Server JWT:** signature, issuer, and mapping scopes to authorities. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- **Spring Security — Opaque Token Resource Server:** introspection and authenticating opaque access tokens. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html
- **Spring Security — Method Security:** EnableMethodSecurity and PreAuthorize. https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
