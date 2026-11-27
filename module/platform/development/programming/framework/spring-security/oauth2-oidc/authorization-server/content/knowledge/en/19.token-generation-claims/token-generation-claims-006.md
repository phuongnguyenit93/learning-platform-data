# Adding Roles, Authorities, or Business Data to Claims Under Control

## 1. Why Must Claims Be Controlled?

In an **OAuth 2.0/OpenID Connect Authorization Server** using **Spring Security, Spring Authorization Server, and Spring Boot**, access tokens often carry information so the Resource Server can decide whether a request is authorized. Beyond standard claims like iss, sub, aud, and exp, a token may need **roles**, **authorities**, **tenant**, **organization**, or selected business attributes.

For example, an order management API may need to know:

- Who the caller is (sub).
- Which Authorization Server issued the token (iss).
- Which API the token is meant for (aud).
- Which OAuth permissions the token was granted (scope).
- Which business roles the user holds, such as ORDER_MANAGER.
- Which tenant the user belongs to so the API never reads another tenant's data.

Putting information into tokens helps Resource Servers make authorization decisions without calling the Authorization Server on every request. However, the token also becomes **a point-in-time snapshot of privileges**. Including too much data, reading from the wrong source, or letting stale claims live too long can expose data or grant excessive privileges.

In the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, the goal is to learn how to **design, configure, secure, test, and operate an OAuth 2.0/OpenID Connect Authorization Server with Spring Security and Spring Authorization Server in a Spring Boot application**. This lesson belongs to the **Tokens and claims** chapter, focusing on principles for putting roles, authorities, and business information into tokens with **least privilege**, proper token types, proper audiences, and lifecycle control.

After this lesson, you will be able to:

1. Distinguish **OAuth scopes**, **Spring Security authorities**, **roles**, and **business claims**.
2. Choose necessary claims, trusted data sources, and appropriate audience boundaries.
3. Use OAuth2TokenCustomizer<JwtEncodingContext> to customize JWT access tokens in Spring Authorization Server.
4. Understand the differences between JWT and opaque/reference access tokens when adding claims.
5. Map claims to authorities at the Resource Server and enforce permissions at the API.
6. Test token claims, tenant isolation, old tokens after permission changes, and negative claim-issuance cases.

**Example scope:** API examples follow Spring Authorization Server 1.5.x and Spring Security 6.x on the Servlet stack. Some configurations may differ in Spring Security 7.x or newer versions; check Javadoc and documentation matching your project's dependencies.

## 2. Distinguishing Scopes, Authorities, Roles, and Business Claims

These concepts are related, yet cannot be substituted for one another arbitrarily.

| Concept | Meaning | Example | Typical source |
| --- | --- | --- | --- |
| **OAuth scope** | Range of access requested by a client and granted by the Authorization Server for an authorization | orders.read, orders.write | RegisteredClient, authorization request, consent, and grant policy |
| **Spring Security authority** | Permission used by Spring Security in authorization decisions | SCOPE_orders.read, ROLE_ORDER_MANAGER | GrantedAuthority on Authentication or Resource Server converter |
| **Role** | Broad business privilege group | ORDER_MANAGER, SUPPORT_AGENT | Identity/user directory or business RBAC system |
| **Permission/entitlement** | Fine-grained permission for an action or resource | invoice.approve, customer.export | Policy/entitlement service |
| **Business claim** | Attribute describing the subject or business context | tenant_id, organization_id, account_tier | Trusted business data, verified for access |

For instance, a user having the ORDER_MANAGER role does not mean every OAuth client is granted the orders.write scope. A scope is a privilege granted to **a specific client and authorization**; a role is a business privilege attribute of **the user**. The Authorization Server must govern their combination via policy.

### 2.1. Do Not Turn Every Authority into a Scope

An Authentication may contain:

```text
ROLE_ORDER_MANAGER
ROLE_SUPPORT_AGENT
SCOPE_orders.read
SCOPE_orders.write
MFA_AUTHENTICATED
IP_TRUSTED
```

Do not copy all of the above straight into the scope claim:

- ROLE_ORDER_MANAGER is a role, not an approved OAuth scope.
- MFA_AUTHENTICATED may be an authentication state, not an API call permission.
- IP_TRUSTED may only hold true for the current connection/time and should not become a long-lived privilege in a JWT.
- Scopes must obey the authorization grant, client policy, and consent; never escalate scopes just because the principal holds high roles.

Keep the scope claim aligned with OAuth semantics. If roles are needed, use a dedicated claim like roles; if fine-grained permissions are needed, use a dedicated claim with a clear schema.

### 2.2. Example Access Token for an Orders API

An illustrative JWT access token might contain:

```json
{
  "iss": "https://auth.example.com",
  "sub": "user-8f31",
  "aud": ["orders-api"],
  "iat": 1794820200,
  "exp": 1794820800,
  "scope": "orders.read",
  "roles": ["ORDER_MANAGER"],
  "https://claims.example.com/tenant_id": "tenant-42"
}
```

The values above are illustrative only. Scope indicates granted OAuth permissions; roles and tenant_id are custom claims per system policy. The API must still check issuer, audience, expiration, signature, and endpoint permissions. The tenant_id claim does not replace checking which tenant owns the queried data.

## 3. Selecting Claims by Least Privilege

Before adding a claim, answer four questions:

1. **Who needs to read this claim?** One Resource Server, multiple APIs, or the OAuth client?
2. **Which decision depends on this claim?** Authorization, tenant isolation, UI display, or merely telemetry?
3. **Is the claim sensitive or frequently changing?** Is it PII, contract data, account status, or internal metadata?
4. **How fresh must the claim be?** Is issuance-time data acceptable, or is real-time verification required?

A claim should only appear if it has an explicit consumer and purpose. Never dump the entire user profile into a JWT on the excuse that "we might need it later".

### 3.1. Data Selection Matrix

| Data | Should it go in the access token? | Conditions |
| --- | --- | --- |
| Stable sub | **Yes**, typically a standard claim | Use a subject without easily guessable personal data; consistent per issuer |
| scope | **Yes**, per granted authorization | Never auto-expand from roles or client registration |
| Business roles needed by API | **Maybe** | Use an allowlist, limit audience and TTL, plan for role changes |
| Fine-grained permissions | **Maybe** | Only when token size and freshness fit; avoid giant lists |
| tenant_id | **Maybe** | Taken from verified membership, bound to subject and client |
| organization_id | **Maybe** | Only if required by API; never trust client-supplied values |
| Email, phone number, address | **Usually avoid** | Include only if the API genuinely needs it after PII, consent, and retention review |
| Passwords, client secrets, refresh tokens, private keys | **Never** | These are credentials or secrets |
| Balances, limits, live order status | **Usually no** | Changes constantly; API should query the business source |
| Feature flags/UI preferences | **Usually unnecessary** | Do not use access tokens as UI configuration profiles |
| Sensitive health/financial data | **Avoid** | If mandatory, requires dedicated threat modeling, compliance controls, and encryption architecture |

### 3.2. A Signed JWT Does Not Mean an Encrypted Payload

A JWS-formatted JWT normally has the structure:

```text
base64url(header).base64url(payload).signature
```

The payload can be read by any party holding the token. A signature protects integrity and authenticates the issuer—it **does not conceal the contents**. Therefore:

- Never put passwords, secrets, private keys, or refresh tokens into claims.
- Minimize PII and unnecessary internal details.
- Never put data the client is not allowed to see just because the token is signed.
- If claims must stay confidential between the AS and Resource Server, consider opaque/reference tokens with introspection or an explicitly designed and supported encrypted token mechanism.

Opaque tokens are also bearer credentials; being opaque does not make transmitting or storing tokens harmless.

## 4. Selecting the Right Token Type

Not every token is meant for the same consumer.

| Token type | Primary consumer | Appropriate claims | What to avoid |
| --- | --- | --- | --- |
| **Access token** | Resource Server/API | Scope, audience, subject, roles/permissions/tenant when API needs them | Stuffing full user profiles or permissions for other APIs |
| **ID token** | OIDC Client/Relying Party | User authentication claims per OIDC and client request | Using an ID token as an access token or stuffing API permissions into it |
| **Refresh token** | Token Endpoint | Usually an opaque/stateful credential, not a claim bundle for APIs | Putting business data into refresh tokens or sending them to Resource Servers |
| **Authorization code** | Token Endpoint | One-time credential tied to an authorization | Treating the code as an API access token |

In this lesson, primary examples focus on **JWT access tokens**. When customizing JWTs, always check the token type so you do not accidentally add roles, tenant_id, or API permissions to ID tokens.

## 5. Spring Authorization Server: Where to Customize JWT Access Tokens

### 5.1. Role of OAuth2TokenCustomizer<JwtEncodingContext>

Spring Authorization Server lets you customize claims/headers during JWT encoding via:

```java
OAuth2TokenCustomizer<JwtEncodingContext>
```

JwtEncodingContext provides the context of the token being created, including:

- getTokenType(): type of token being generated.
- getRegisteredClient(): client registration.
- getPrincipal(): authentication principal in the grant context.
- getAuthorizationGrantType(): grant type.
- getAuthorizedScopes(): scopes granted to the authorization.
- getAuthorization(): current authorization if present.
- getClaims(): builder to add/modify JWT claims.
- getJwsHeader(): builder for the JOSE header.

**Never add claims before checking token type.** A JWT customizer may run across different JWT flows depending on configuration/generators; add role/business claims only when generating access tokens per defined policy.

Authorization context and persistence must also be understood correctly:

- **RegisteredClientRepository** provides client settings such as grant types, scopes, redirect URIs, and token settings.
- **OAuth2AuthorizationService** saves/looks up authorizations and token state; OAuth2Authorization holds registered client ID, principal name, grant type, authorized scopes, attributes, and token metadata.
- **OAuth2TokenGenerator** generates tokens from the context built by the authentication provider; the customizer only supplements claims during encoding, not where consent is granted or scopes are elevated.

When placing roles in a JWT, take scopes from the authorization context and roles from a verified business authorization source. Do not use the client's registered scopes in place of the specific grant's authorized scopes.

### 5.2. Role Data Must Come from a Trusted Source

Create a dedicated service to retrieve verified roles:

```java
import java.util.Set;

public interface UserRoleClaimService {
    /**
     * Returns verified business roles for the subject.
     * Returned values do not include the Spring "ROLE_" prefix.
     */
    Set<String> rolesForSubject(String subject);
}
```

Implementations may read from a user/entitlement store, an invalidated cache, or a managed policy service. Never take roles from:

- Request parameters, query strings, or user-supplied headers.
- Authentication.getDetails() if that data can be controlled by the client.
- A client-supplied JWT without verifying its signature/issuer/audience.
- Client names or scopes by guessing the user holds corresponding roles.

### 5.3. Example Customizer Adding Roles Only to Access Tokens

The example below illustrates user authorization code and refresh grants. The service returns verified role names; the customizer applies an allowlist to avoid leaking internal authorities into the token:

```java
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.server.authorization.OAuth2TokenType;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenCustomizer;

@Configuration(proxyBeanMethods = false)
public class AccessTokenClaimsConfiguration {

    private static final Set<String> EXPOSED_ROLES =
            Set.of("ORDER_MANAGER", "SUPPORT_AGENT");

    @Bean
    OAuth2TokenCustomizer<JwtEncodingContext> accessTokenCustomizer(
            UserRoleClaimService roleClaimService) {

        return context -> {
            // Do not add these business claims to ID tokens.
            if (!OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
                return;
            }

            AuthorizationGrantType grantType =
                    context.getAuthorizationGrantType();
            boolean userGrant =
                    AuthorizationGrantType.AUTHORIZATION_CODE.equals(grantType)
                    || AuthorizationGrantType.REFRESH_TOKEN.equals(grantType);
            if (!userGrant) {
                return;
            }

            String subject = context.getPrincipal().getName();
            Set<String> roles = roleClaimService.rolesForSubject(subject).stream()
                    .filter(EXPOSED_ROLES::contains)
                    .collect(Collectors.toUnmodifiableSet());

            if (!roles.isEmpty()) {
                context.getClaims().claim("roles", roles);
            }
        };
    }
}
```

**This pattern must be adapted to your application's actual principals and policies.** Verify that the principal in authorization code and refresh grants is the user principal your service expects; never assume getPrincipal().getName() is always a user ID across all grants. For refresh tokens, check how your version constructs the token context and how to extract a stable subject from the authorization. If the principal does not represent a user, do not look up roles by client name and write them into roles.

This example intentionally does **not** add a scope claim: Spring Authorization Server already creates token claims from the authorization context. Never overwrite default scopes with a role list.

### 5.4. Do Not Put User Roles into `client_credentials` Tokens

With client_credentials, the principal represents the client/application, not an end user. Do not apply the user role lookup above. If the Resource Server needs machine-to-machine permissions, design a dedicated client claim such as client_permissions based on **the RegisteredClient's own policy** or an entitlement service:

```java
if (AuthorizationGrantType.CLIENT_CREDENTIALS.equals(
        context.getAuthorizationGrantType())) {
    // Read client permissions from a trusted source using RegisteredClient.id
    // or the authenticated client identity; do not attach a user's roles.
}
```

Never turn client_id into a user sub. Never grant ROLE_ADMIN to a service account merely because that service holds the orders.read scope.

### 5.5. Do Not Arbitrarily Call Slow Systems Inside a Customizer

Customizers execute on the token issuance hot path. If every token generation calls an external network API to fetch roles/tenants, the Token Endpoint can suffer high latency or fail when external systems degrade.

Recommendations:

- Use internal data sources with appropriate reliability and SLAs.
- Cache with short TTLs and clear invalidation; never let stale roles linger indefinitely.
- Handle entitlement errors fail-closed for sensitive permission claims.
- Avoid repeated redundant queries within a single token generation.
- Measure latency, errors, and token generation failure rates; never put sensitive claims into metrics.

## 6. Adding Business Claims Under Control

Roles are not the only business data. Multi-tenant APIs may need tenant_id, organization_id, or a region code. However, these claims must be bound to **subject, client, and authorization**.

### 6.1. Tenant Claims Must Be Verified

Suppose a browser sends:

```http
X-Tenant-Id: tenant-42
```

This header is only **client-supplied input**, not proof that the user belongs to that tenant. The Authorization Server must verify membership or tenant context using trusted data. A policy service might expose:

```java
import java.util.Optional;

public interface TenantClaimService {
    Optional<String> activeTenantFor(String subject, String clientId);
}
```

When creating a token, add the claim only if the service confirms the subject is permitted for that tenant:

```java
tenantClaimService.activeTenantFor(subject, context.getRegisteredClient().getClientId())
        .ifPresent(tenant ->
                context.getClaims().claim(
                        "https://claims.example.com/tenant_id", tenant));
```

The URI claim here is a namespaced custom claim name to minimize collisions with standard claims or claims defined by other libraries. In a real system, the namespace domain should be controlled by your organization.

### 6.2. Do Not Confuse a Tenant Claim with Tenant Authorization

A Resource Server can read tenant_id to know which tenant context a token was issued in, yet it must still:

1. Verify the token's signature/issuer/audience/expiry.
2. Read the tenant claim from the verified JWT, never from a substitute request header.
3. Scope all data queries to the tenant claim and check record-level permissions.
4. Prevent clients from picking tenant_id via query/body/header and bypassing membership.
5. Handle cases where a user is removed from a tenant or a tenant is locked.

A tenant claim is **not** permission to access every record in that tenant. It is merely an attribute of the token verified by the Authorization Server at issuance time.

### 6.3. Frequently Changing Business Claims

Do not pack minute-by-minute mutable state into long-lived access tokens:

- Current financial limits.
- Order status, account balances, or inventory counts.
- Constantly changing feature entitlements.
- Per-resource permission lists containing tens of thousands of entries.

A token is a snapshot. Once claims are signed into a JWT, an offline Resource Server does not automatically know source data changed. For data requiring high freshness, the API should query business services or use an authorization/introspection mechanism with defined TTL/cache policies.

## 7. Scopes, Roles, and Permissions in the Resource Server

### 7.1. Spring Security Default Scopes

Spring Security Resource Server maps scopes in a JWT (typically the scope or scp claim, depending on converter/configuration) into authorities prefixed with SCOPE_. For example:

```text
scope: "orders.read orders.write"

Authorities:
SCOPE_orders.read
SCOPE_orders.write
```

Thus you can use:

```java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public List<Order> readOrders() { ... }
```

### 7.2. Role Claims Do Not Automatically Map to `ROLE_`

If an access token contains:

```json
{
  "roles": ["ORDER_MANAGER"]
}
```

Spring Security **does not automatically treat** the string ORDER_MANAGER as ROLE_ORDER_MANAGER in default configurations. You must configure a converter to translate the roles claim into GrantedAuthority instances.

Example converter combining default scopes and roles:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Set;

import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

public final class ApiJwtAuthenticationConverters {
    private ApiJwtAuthenticationConverters() {}

    public static JwtAuthenticationConverter withRoles() {
        JwtGrantedAuthoritiesConverter scopes =
                new JwtGrantedAuthoritiesConverter();
        Set<String> allowedRoles =
                Set.of("ORDER_MANAGER", "SUPPORT_AGENT");

        Converter<Jwt, Collection<GrantedAuthority>> combined = jwt -> {
            List<GrantedAuthority> authorities =
                    new ArrayList<>(scopes.convert(jwt));

            List<String> roles = jwt.getClaimAsStringList("roles");
            if (roles != null) {
                roles.stream()
                        .filter(allowedRoles::contains)
                        .map(role -> new SimpleGrantedAuthority("ROLE_" + role))
                        .forEach(authorities::add);
            }
            return authorities;
        };

        JwtAuthenticationConverter converter = new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(combined);
        return converter;
    }
}
```

This converter preserves the default scope converter and adds roles. An allowlist restricts recognized role names; real Resource Servers need an allowlist of understood roles to prevent arbitrary claims from becoming powerful authorities. Never accept roles from a token whose signature/issuer/audience have not been verified.

### 7.3. Using Scopes and Roles for Different Purposes

Example Resource Server configuration:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrdersApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            JwtAuthenticationConverter jwtAuthenticationConverter)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .requestMatchers("/management/**")
                    .hasRole("ORDER_MANAGER")
                .anyRequest().authenticated())
            .oauth2ResourceServer(resourceServer -> resourceServer
                .jwt(jwt -> jwt.jwtAuthenticationConverter(
                        jwtAuthenticationConverter)));

        return http.build();
    }
}
```

In a real application, you must also configure a valid JwtDecoder/issuer or JWK Set and protect remaining endpoints per policy. hasRole("ORDER_MANAGER") checks for authority ROLE_ORDER_MANAGER; hasAuthority("SCOPE_orders.write") checks the scope. **Do not replace all scopes with roles**, and do not let high-level roles bypass tenant/resource ownership checks.

## 8. JWT Access Tokens vs. Opaque/Reference Tokens

Spring Authorization Server can issue access tokens in the appropriate format:

| Characteristic | JWT/self-contained | Opaque/reference |
| --- | --- | --- |
| Claim storage | Lives in the JWT payload, readable if unencrypted | Claims are not directly visible in the token value |
| Resource Server verification | Can verify signature and claims offline | Typically uses introspection to query status/token metadata |
| Freshness of roles/tenant | Snapshot at issuance time; offline JWTs do not auto-update | Can receive fresher data via introspection, depending on cache and implementation |
| API request overhead | Lower, since introspection is not needed per request | Network/cache overhead for introspection |
| Immediate revocation | Harder if Resource Servers only verify JWTs offline | Can reflect revocation faster if not cached too long |
| Specific risks | Claims exposed to token holders; stale permissions | Introspection endpoint and cache become critical components |

When choosing opaque tokens, Spring Authorization Server can customize claims via OAuth2TokenCustomizer<OAuth2TokenClaimsContext> for opaque access tokens. **OAuth2TokenCustomizer<JwtEncodingContext> only customizes the JWT encoding context**; do not assume it modifies claims across all token formats.

Example configuring reference tokens on TokenSettings:

```java
import org.springframework.security.oauth2.server.authorization.settings.OAuth2TokenFormat;
import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;

TokenSettings tokenSettings = TokenSettings.builder()
        .accessTokenFormat(OAuth2TokenFormat.REFERENCE)
        .build();
```

This is part of the RegisteredClient configuration; switching formats requires the Resource Server to have an introspection client/credentials and matching configuration. Never just flip an enum and assume every API will keep reading JWT claims as before.

## 9. Claims Have Lifetimes and Can Become Stale

Suppose a user is issued a JWT at 09:00 with:

```json
{
  "roles": ["ORDER_MANAGER"],
  "https://claims.example.com/tenant_id": "tenant-42",
  "exp": 1794820800
}
```

At 09:02, an administrator removes the ORDER_MANAGER role. If the Resource Server only verifies JWTs offline, the signed token may still carry the old role until expiration.

Mitigation strategies:

1. **Short access token TTLs:** limit how long a privilege snapshot remains valid.
2. **Opaque tokens + introspection:** API checks live token status; design cache TTL accordingly.
3. **Revocation/state checks:** add denylists, authorization versions, or session/account status checks when SLAs require it.
4. **Resource-level authorization:** always verify ownership/tenant/data state in the API.
5. **Revoke refresh/authorization:** prevent issuing new tokens from an old grant once privileges are withdrawn.

No single solution fits every system automatically. Define your SLA: "when a role is revoked, every API must reject within 30 seconds" is completely different from "new tokens will omit that role on the next refresh".

### 9.1. Refresh Tokens and Custom Claims

During a refresh, a new access token can be regenerated from the current authorization context. If the customizer re-queries roles/tenants from the data source, the new token can reflect **the latest state observed by the service**. However:

- Never expand OAuth scopes beyond the original grant's authorizedScopes just because new roles were added.
- If the user lost access, do not keep issuing old role claims just because an old authorization exists; enforce dedicated revocation/downscoping policies.
- If the role service fails, never fall back to granting a broad default privilege set.
- Refresh token rotation does not automatically update or revoke previously issued JWT access tokens.

Role claims and OAuth scopes must follow **two independent decisions**: scopes follow the grant; roles/entitlements follow user/client/business policy.

## 10. Designing a Stable Claims Schema

### 10.1. Naming and Data Types

| Claim | Recommended type | Rules |
| --- | --- | --- |
| roles | String array | Allowlisted role names, omitting ROLE_ if the converter adds the prefix |
| permissions | String array | Use only when fine-grained permissions are needed; bound count and schema |
| tenant_id (or namespaced claim) | String | Single verified tenant, never taken directly from requests |
| organization_id | String | Stable ID, bound to subject/client |
| authz_version | Integer/string version | Use only if Resource Servers check the version |
| scope | OAuth scope string in active format | Never replace with a role list |
| aud | String array | Target API audience; never issue a single wildcard token to all services unnecessarily |

### 10.2. Avoiding Claim Name Collisions

Standard claims like iss, sub, aud, exp, nbf, iat, and jti have fixed semantics. Do not reuse those names for arbitrary business data. For custom claims, you can use an organization-controlled URI namespace:

```json
{
  "https://claims.example.com/tenant_id": "tenant-42",
  "https://claims.example.com/organization_id": "org-19"
}
```

Claim names are part of the contract between the Authorization Server and Resource Server. Changing names or data types requires versioning/migration and compatibility testing.

### 10.3. Keeping Tokens Small

Oversized JWTs increase:

- HTTP header sizes and the risk of hitting proxy/server limits.
- Bandwidth, latency, and per-request transmission overhead.
- Data exposure surface when tokens end up in logs/debug tools.
- Schema update and multi-Resource-Server synchronization complexity.

Do not put lists of thousands of permissions, full user profiles, or deeply nested JSON into access tokens. When large amounts of data are needed, use business APIs or an entitlement service.

## 11. Testing Claims from Authorization Server to API

### 11.1. Unit Testing Role Selection Policy

Policy must ensure only permitted roles appear:

```java
import java.util.Set;
import java.util.stream.Collectors;

public final class RoleClaimPolicy {
    private static final Set<String> ALLOWED =
            Set.of("ORDER_MANAGER", "SUPPORT_AGENT");

    private RoleClaimPolicy() {}

    public static Set<String> exposedRoles(Set<String> trustedRoles) {
        return trustedRoles.stream()
                .filter(ALLOWED::contains)
                .collect(Collectors.toUnmodifiableSet());
    }
}
```

Example JUnit 5 test:

```java
import java.util.Set;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class RoleClaimPolicyTest {
    @Test
    void onlyApprovedBusinessRolesAreExposed() {
        Set<String> result = RoleClaimPolicy.exposedRoles(Set.of(
                "ORDER_MANAGER",
                "SUPPORT_AGENT",
                "ROLE_SYSTEM_INTERNAL",
                "DBA"));

        assertThat(result)
                .containsExactlyInAnyOrder("ORDER_MANAGER", "SUPPORT_AGENT");
    }

    @Test
    void unknownRolesDoNotBecomeTokenClaims() {
        assertThat(RoleClaimPolicy.exposedRoles(Set.of("ROOT", "DEBUG")))
                .isEmpty();
    }
}
```

This is a unit test for the allowlist and does not replace token-generation integration tests. When integrating, verify that the customizer runs only for access tokens and that the Resource Server interprets the claims correctly.

### 11.2. Integration Test Matrix

| ID | Scenario | Expected result |
| --- | --- | --- |
| C01 | Authorization Code user with ORDER_MANAGER | Access token includes allowlisted role |
| C02 | User with internal authority ROLE_SYSTEM_INTERNAL | Does not appear in roles claim |
| C03 | User with no matching roles | Roles claim absent or empty per schema |
| C04 | client_credentials | End-user roles are not placed in client token |
| C05 | ID token generated in OIDC flow | Does not receive API role claims if policy is access-token-only |
| C06 | Refresh token after role removal | New token reflects designed revocation/downscoping policy |
| C07 | User switches tenant or loses membership | Old tenant claim is not issued from request data |
| C08 | Request sends a different X-Tenant-Id | Cannot pick a tenant outside verified membership |
| C09 | Client granted only orders.read scope | Token lacks orders.write even if user is manager |
| C10 | Token audience is orders-api | Other APIs reject the wrong-audience token |
| C11 | Resource Server receives roles claim | Converter produces accurate ROLE_* authorities |
| C12 | Resource Server receives scope | Scopes map to SCOPE_* and endpoints enforce them |
| C13 | JWT missing mandatory tenant claim | API rejects or applies safe fail-closed policy |
| C14 | Claim with disallowed PII | Absent from JWT |
| C15 | Token format switched to opaque | Custom claims tested via introspection, not assumed JWT |
| C16 | Role service timeout/error | Broad default role claims are not issued; defined fail-closed behavior |
| C17 | Old JWT after role revocation | Actual behavior stays within committed SLA |
| C18 | Token exceeds size limit | Caught by tests pre-production; schema trimmed |
| C19 | Two users with same display name, different subjects | Claims queried by stable subject without mix-ups |
| C20 | Different clients for same user | Claims constrained by audience/client policy if required |

### 11.3. Inspecting JWTs Without Leaking Tokens

In test environments, you can decode payloads to inspect claims, but:

- Use only test/fixture tokens.
- Never paste production JWTs into public online decode websites.
- Never dump full payloads into CI logs if they contain sensitive PII/tenant/role data.
- Verify signature, issuer, audience, and expiration with a Resource Server decoder; Base64 decoding is **not** token verification.
- Test both the Token Endpoint response and real enforcement at the API.

## 12. Common Design Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Copying all GrantedAuthorities into claims | Exposes internal authorities or over-privileges tokens | Allowlist and separate user vs. client authorities |
| Using roles instead of scopes | Bypasses consent/grants or client boundaries | Keep OAuth scopes independent from roles |
| Taking business claims from request headers | Users pick arbitrary tenants/organizations | Resolve from trusted membership/policy services |
| Adding roles to every JWT | ID tokens/other clients receive unnecessary data | Check token type and audience |
| Treating claims as real-time data | Old tokens retain changed state | TTLs, introspection/state checks, or API lookups |
| Putting PII/secrets into JWTs | Data readable whenever token leaks | Data minimization, opaque tokens, or API lookups |
| Using one shared audience for all APIs | Tokens replayed across APIs | Audience restriction and validation |
| Overwriting scope with roles | Breaks OAuth semantics | Let the provider manage scopes from the authorization |
| Unbounded role-service queries in customizer | Slow Token Endpoint / external failure coupling | Local source/invalidated cache, timeouts/fail-closed |
| Resource Server does not map role claim | hasRole always fails or permissions mismatch | Configure JwtAuthenticationConverter |
| Converter trusts every role string | Arbitrary claims become authorities | Allowlist/schema validation at AS and RS |
| Thinking signed JWT means secret payload | Claims exposed to token holders | Never put secrets in JWS payloads |
| Thinking revoking refresh token revokes old JWTs immediately | Offline APIs accept old tokens until exp | Design access token revocation/freshness separately |

## 13. Production Checklist

**Claim Design**

- [ ] Every claim has a documented consumer, purpose, owner, and schema.
- [ ] OAuth scopes, roles, authorities, and permissions are clearly separated.
- [ ] Claims contain only the minimum data needed by the Resource Server.
- [ ] Roles/tenants/organizations come from trusted sources verified against subject and client context.
- [ ] Claims contain no passwords, secrets, refresh tokens, private keys, or unnecessary PII.
- [ ] Claim names do not collide with registered JWT claims; namespaced/versioned as needed.
- [ ] Tokens carry appropriate audiences, minimal TTLs, and least-privilege scopes.

**Spring Authorization Server**

- [ ] JWT customizer checks OAuth2TokenType.ACCESS_TOKEN before adding API claims.
- [ ] The client_credentials grant is handled separately without fetching user roles.
- [ ] Granted scopes are never overwritten with role lists.
- [ ] Role/entitlement service failures never default to adding privileges.
- [ ] Opaque tokens use the appropriate customizer/context and are tested separately.
- [ ] ID tokens contain only claims needed by the OIDC client.

**Resource Server and Operations**

- [ ] JWT decoder verifies signature, issuer, audience, and expiration.
- [ ] Scopes map to SCOPE_*; roles map to ROLE_* via an allowlist.
- [ ] APIs verify tenant/resource ownership in addition to reading the tenant claim.
- [ ] Old tokens after privilege revocation, refresh flows, and multi-node behavior are tested.
- [ ] Claim/token size, logging, tracing, and PII exposure are controlled.
- [ ] A schema migration strategy exists for renaming claims or changing types.

## 14. References

- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): RegisteredClient, OAuth2Authorization, tokens, and authorization services.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): Token Endpoint, authentication providers, and customization points.
- [Spring Authorization Server — How-to: Customize JWT Claims](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-custom-claims-authorities.html): examples using OAuth2TokenCustomizer<JwtEncodingContext> to add claims/authorities.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): verifying JWTs and mapping claims to authorities.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): PreAuthorize, roles, and authorities in method authorization.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token profile, claims, and validation.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): registered claims, public/private claim names, and JWT semantics.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): least privilege, token leakage, and protecting access/refresh tokens.

**Conclusion:** Claims are part of the **security contract between the Authorization Server and Resource Server**. Keep scopes tied to granted OAuth permissions, place roles/permissions in separate claims only when needed by APIs, source business claims from verified origins, and constrain them by subject/client/audience. In Spring Authorization Server, customize JWTs via OAuth2TokenCustomizer<JwtEncodingContext> with token-type guards; on the Resource Server, verify tokens and then map claims cleanly to authorities. Tokens are time-bounded snapshots, so changing privileges, revocation, and tenant isolation always require an end-to-end strategy.
