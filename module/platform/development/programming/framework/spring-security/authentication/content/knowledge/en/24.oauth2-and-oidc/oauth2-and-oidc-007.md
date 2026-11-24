# Mapping Claims, Permissions, and External Identities to Internal Principals

## 1. Problem: Logging In via an IdP While the App Still Needs to Know “Who Is This Person?”

In enterprise systems, users may log in via Google Workspace, Microsoft Entra ID, Keycloak, or another OpenID Provider. The *Identity Provider* (IdP) authenticates the user and issues information such as `sub`, `email`, `name`, `groups`, and `roles`. Meanwhile, the Java application holds its own data: employee ID, internal account, accounting role, organizational unit scope, and whether the user is permitted to use the system.

Those two layers answer different questions:

- **IdP and OIDC:** who successfully signed in at the identity provider, and under what identifier?
- **Application:** which internal account corresponds to that external identity, is the account locked, and which data may it read or modify?
- **Spring Security:** represents the authentication result as an `Authentication`/principal and a list of `GrantedAuthority` instances so access rules apply consistently.

For example: a valid ID Token contains `iss=https://login.example-idp.test/realms/company` and `sub=00u8abc`. The application maps this pair to `user_id=usr_1042`, then loads the `APP_ORDER_READ` and `APP_ORDER_APPROVE` authorities from its authorization policy. Having `email=lan@company.example` or `name=Lan Nguyen` in the token is mainly for display, and should not be the key that determines permissions.

~~~text
Browser                    OpenID Provider (IdP)             Spring Boot
   |                                 |                            |
   |-- OIDC authorization request -->|                            |
   |<-- authorization code ----------|                            |
   |-- callback + code ------------------------------------------>|
   |                                 |<-- code exchange ---------|
   |                                 |--- ID Token -------------->|
   |                                 |                            |
   |                                 |    validate OIDC token     |
   |                                 |    extract (issuer, sub)   |
   |                                 |    resolve local user      |
   |                                 |    load active state/roles |
   |                                 |    create Authentication   |
   |<-- application session --------------------------------------|
   |-- /orders/approve ------------------------------------------>|
   |                                 |    authorize per resource  |
~~~

This is the **authorization code–based OIDC login** model, not an exhaustive description of every OAuth 2.0 variant. For APIs receiving bearer access tokens, the first step is the resource server validating the access token, followed by mapping identity and permissions.

## 2. Distinguishing Claim, Principal, Authority, Scope, and Role

| Term | Meaning | Can It Be Used Directly as a Permission? |
|---|---|---|
| **Claim** | An attribute inside an ID Token, JWT access token, or UserInfo, e.g., `iss`, `sub`, `email`, `groups`. | Not every claim is a permission; you must understand its source and semantics. |
| **External identity** | Identity verified by the IdP, typically keyed by `(issuer, subject)`. | Used to link accounts; not a business permission by itself. |
| **Internal principal** | Representation of the subject recognized by the app, e.g., `internalUserId=usr_1042`, `tenantId=t1`. | The subject on which permissions are evaluated; does not grant permissions itself. |
| **GrantedAuthority** | Permission checked by Spring Security such as `APP_ORDER_READ`, `ROLE_ADMIN`, `SCOPE_orders.read`. | Yes, when application policy accepts that authority. |
| **OAuth scope** | Scope delegated to an OAuth client with a resource server, such as `orders.read`. | Not automatically synonymous with “employee role”; may map to `SCOPE_orders.read` for checks. |
| **IdP group/role** | Group or role in the IdP's model, e.g., `engineering`, `erp-admins`. | Should grant permissions only after verification and mapping through policy. |
| **Business permission** | Permission to perform a specific action in the app, such as approving invoices. | Typically loaded from the app's policy system and scoped to data. |

In Spring Security, `Authentication.getPrincipal()` is the object describing the subject, `Authentication.getName()` is the identifier name used by `Principal`, and `Authentication.getAuthorities()` holds the `GrantedAuthority` instances. `hasRole("ADMIN")` typically checks for authority `ROLE_ADMIN`; `hasAuthority("APP_ORDER_APPROVE")` checks the exact defined string. Never assume a claim `"role": "ADMIN"` automatically carries the authority `ROLE_ADMIN`.

**Important:** OAuth 2.0 is an authorization framework, whereas OpenID Connect (OIDC) adds the user authentication layer on top of OAuth 2.0. **ID Tokens** serve the OIDC client/Relying Party receiving login information; **access tokens** serve APIs/resource servers. An API must not accept an ID Token merely because it is a validly signed JWT. Tokens must match the right **type, issuer, audience, expiration, and intended use**.

## 3. Normalizing External Identity: Why `iss + sub`?

Per OpenID Connect Core, the claim pair **`iss` (issuer) and `sub` (subject)** is the standard-guaranteed user identifier within the scope of an issuer. Identical `sub` strings from two different IdPs **must never** be assumed to be the same person. An IdP may also use *pairwise subjects*, where different clients/sectors receive different `sub` values for the same user to limit cross-site tracking.

Example:

~~~json
{
  "iss": "https://idp.company.example/realms/staff",
  "sub": "9a2b-user-451",
  "aud": "portal-web",
  "email": "lan@company.example",
  "email_verified": true,
  "name": "Lan Nguyen",
  "preferred_username": "lan.nguyen"
}
~~~

In a valid OIDC ID Token, these are **claims issued by the IdP and verified by the client per OIDC**; the JSON snippet alone **is not proof of authentication**. You must verify signature/algorithm, issuer, audience/client ID, expiration, nonce if required by the flow, and other conditions before trusting the values.

Identity links should be stored following this model:

~~~text
internal_users
  id = usr_1042
  tenant_id = tenant_a
  status = ACTIVE
  display_name = Lan Nguyen

external_identity_links
  issuer = https://idp.company.example/realms/staff
  subject = 9a2b-user-451
  internal_user_id = usr_1042
  linked_at = ...
  link_status = ACTIVE
  last_verified_at = ...
~~~

One person may have **multiple external links** (e.g., employee IdP and contractor IdP), all established through an approved linking workflow. Enforce a **UNIQUE (issuer, subject)** constraint on active links and a foreign key to the internal account. In multi-tenant systems, bind tenant/IdP registration and trust policies into the data model rather than merely concatenating issuer-sub loosely.

### Claims Unsuitable as Unique Keys

- `email` can change, be reused, collide across IdPs, and is **not guaranteed unique by OIDC**. `email_verified=true` only states the IdP ran a verification step for email control at some point; it **does not** prove the email is a permanent identifier or that the holder is still permitted to use the system.
- `preferred_username`, `name`, and `given_name` are mainly descriptive metadata, mutable and non-unique.
- `groups`/`roles` are data for permission evaluation, often changing with org structure rather than acting as an identity key.
- `sub` alone is insufficient when multiple issuers exist. Changing IdP, issuer URL, or tenant requires a migration/linking strategy with clear proof.

### When Is Linking by Email Allowed?

Only inside a designed **account ownership proof workflow**: for example, a user already authenticated to an internal account in an active session initiates linking an additional IdP, or an approved administrative workflow with trusted identity cross-checks. Never automatically connect two accounts just because they share an email, even if both show `email_verified=true`. If no link is found, the state should be **unlinked/denied** or routed to explicit onboarding rather than arbitrarily reusing an existing account.

## 4. Trusted Input: Validate the Token First, Map Claims Afterward

A service receiving a JWT string in an HTTP header must never just Base64-decode it and read `sub` or `roles`. Data at that stage is still client-supplied, so it must pass through Spring Security's validation before determining identity.

### OIDC Login (Browser)

The OIDC client uses discovery/client registration and processes the authorization code. The ID Token must be validated per OIDC rules: signature, `iss`, `aud`, `exp`, nonce, and client/flow constraints. If calling the UserInfo Endpoint, ensure `sub` in UserInfo matches the ID Token's subject. Only after that step does `OidcUser`/`OidcIdToken` become the source of claims for account linking.

### OAuth2 Resource Server (API)

An API may receive a **JWT access token** or an **opaque token**. For JWTs, the resource server must verify the signature with a trusted key, algorithm, `iss`, `exp`, `nbf`, and **`aud` matching the API**, along with token-type policies if multiple token types exist. In Spring Security, configuring `issuer-uri` provides default issuer/JWK validation, yet **you must not assume API audience checking is enabled automatically across all versions/configs**; explicitly configure a validator or audience property suitable for your framework.

For opaque tokens, the resource server uses token introspection per the IdP contract to confirm the token is active and retrieve permitted attributes. Not every token is a JWT; never try to decode an opaque token as JSON.

**Only after token validation** does mapping have a valid basis to process claims. If `iss` or `sub` is missing, audience is invalid, issuer is untrusted, or the token is expired, reject it at authentication/validation time. Never modify tokens or alter claim values to “bypass” checks.

### Recommended Flow

~~~text
HTTP request / OAuth2 callback
          │
          ▼
OAuth2 client / Resource Server authentication
  - verify cryptographic signature / introspection
  - validate issuer, audience, time, token purpose
          │
          ▼
Canonical external identity = (trusted issuer, subject)
          │
          ▼
Resolve local account link + tenant + status
          │
          ├── No link / locked / disabled → deny or explicit onboarding
          │
          ▼
Derive internal permissions from trusted policy
          │
          ▼
Create Spring Authentication / internal principal view
          │
          ▼
Enforce resource-level authorization
~~~

## 5. Permission Mapping Policies: Which Source Decides Which Permissions?

There are at least three valid strategies, depending on how much control the application requires:

| Strategy | Permission Source | When to Apply | Risks to Manage |
|---|---|---|---|
| **Internal permissions as source of truth** | App DB/policy service; IdP supplies identity only. | Critical business permissions requiring independent offboarding/approval. | Account status sync, per-request permission cache/lookup. |
| **IdP group/role mapping via allowlist** | Groups issued by a trusted issuer, translated through a finite mapping table. | Organizations with centralized group management and clear semantics. | Missing group claims, name collisions across tenants, nested groups, stale permissions. |
| **Hybrid** | IdP identity + group signal, while final decisions rely on internal policy/account. | Systems needing both RBAC/ABAC and central governance. | Must explicitly define precedence and conflict resolution. |

Example approved mapping table:

| Trusted IdP group | Additional Conditions | Internal Spring Authority |
|---|---|---|
| `finance-readers` | Account active; tenant = A | `APP_INVOICE_READ` |
| `finance-approvers` | Account active; belongs to right cost center | `APP_INVOICE_APPROVE` |
| `hr-admins` | Additional control by application | `APP_EMPLOYEE_ADMIN` |
| Claim `role=admin` not in policy | Does not match allowlist | Grant no special permissions |

Never promote arbitrary `groups` or `roles` values into `ROLE_...` without knowing the issuer, namespace, semantics, access boundaries, and lifecycle. An `admins` group in one tenant must never become admin in another tenant. Nor should OAuth scopes like `openid` or `profile` become a business permission to “view all records”.

Spring Security uses `GrantedAuthority` as the final request-level authority string, while object-level checks typically need extra business conditions: `APP_INVOICE_APPROVE` may require **the invoice belongs to an assigned department**, an approvable status, and the user's approval limit. Use method security or an authorization service instead of relying solely on URL-level `hasAuthority(...)`.

**Freshness principle:** claims in a token are a snapshot at issuance time. When a user is removed from a group or an account is locked, existing tokens/sessions may retain old info until expiry or reload. Define token TTLs, session expiry, revocation rights, internal account check frequency, and fallback behavior if the IdP/DB is temporarily unavailable.

## 6. Spring Security: Three Authentication Types to Distinguish

In **Servlet, Spring Security 6.x / Spring Boot 3.x** applications, common setups are:

1. **`oauth2Login()` with OIDC:** after browser login, `OAuth2AuthenticationToken` holds an `OidcUser`. `OidcUser.getIdToken()` and `getClaims()` expose the validated OIDC source; Spring Security can map authorities inside a user service or `GrantedAuthoritiesMapper`.
2. **`oauth2ResourceServer().jwt()`:** API validating JWT access tokens; by default `Authentication.getPrincipal()` is `Jwt` and `getName()` is usually `sub`. `JwtAuthenticationConverter` can change authorities and the `Authentication` name; if an internal principal object is needed, use a version-appropriate converter/wrapper or an internal identity view in the service layer.
3. **`oauth2ResourceServer().opaqueToken()`:** API introspecting opaque tokens. Subject info and authorities can be mapped via an introspector/converter depending on the integration, while preserving token validation and issuer/authorization-server checks.

The configurations above are **different extension points**. Configuration for OIDC login does not automatically run for bearer JWTs, and `JwtAuthenticationConverter` does not automatically affect `OidcUser` created by `oauth2Login()`. Never swap code from one flow into another simply because both involve a `sub` claim.

## 7. Example A: Mapping OIDC Login to an Internal Principal

The example below illustrates **the integration concept in a Spring Boot Servlet project with Spring Security OAuth2 Client**. Interfaces `AccountLinkRepository` and `LocalAccount` are contracts the application must implement itself. This is integration configuration code, **not a standalone `javac` program**.

Typical dependencies:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-client")
}
~~~

Issuer/client configuration via Spring Boot (illustrative values; load client secret from a secrets manager):

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: portal-web
            client-secret: "configured-outside-source"
            authorization-grant-type: authorization_code
            scope: openid, profile, email
        provider:
          company:
            issuer-uri: https://idp.company.example/realms/staff
~~~

### 7.1. Defining the Account Mapping Contract

~~~java
public record LocalAccount(
        String id,
        boolean active,
        java.util.Set<String> permissionCodes
) {}

public interface AccountLinkRepository {
    // Only return user when issuer+subject is uniquely linked to the right tenant
    java.util.Optional<LocalAccount> findByExternalIdentity(
            String issuer, String subject);
}
~~~

In real products, determine the tenant from a trusted registration/boundary and enforce mapping uniqueness. Never use email as the key for this method.

### 7.2. OIDC User Service and Internal Principal

~~~java
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.OidcUserInfo;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;

@Configuration
public class InternalOidcSecurityConfig {

    @Bean
    OAuth2UserService<OidcUserRequest, OidcUser> internalOidcUserService(
            AccountLinkRepository accounts) {
        var delegate = new OidcUserService();

        return request -> {
            // Spring Security OIDC client already validated the ID Token in the previous step
            OidcUser external = delegate.loadUser(request);
            String issuer = external.getIdToken().getClaimAsString("iss");
            String subject = external.getIdToken().getSubject();

            if (issuer == null || issuer.isBlank()
                    || subject == null || subject.isBlank()) {
                throw new OAuth2AuthenticationException(
                        new OAuth2Error("invalid_external_identity"));
            }

            LocalAccount local = accounts
                    .findByExternalIdentity(issuer, subject)
                    .filter(LocalAccount::active)
                    .orElseThrow(() -> new OAuth2AuthenticationException(
                            new OAuth2Error("account_not_linked_or_disabled")));

            var granted = new LinkedHashSet<GrantedAuthority>();
            // permissionCodes must be selected from an internal allowlist
            for (String permission : local.permissionCodes()) {
                granted.add(new SimpleGrantedAuthority(permission));
            }

            return new InternalOidcPrincipal(
                    external, local.id(), granted);
        };
    }

    @Bean
    SecurityFilterChain webSecurity(
            HttpSecurity http,
            OAuth2UserService<OidcUserRequest, OidcUser> internalOidcUserService)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/admin/**").hasAuthority("APP_ADMIN")
                .anyRequest().authenticated());

        http.oauth2Login(login -> login
                .userInfoEndpoint(userInfo ->
                        userInfo.oidcUserService(internalOidcUserService)));

        return http.build();
    }

    public record InternalOidcPrincipal(
            OidcUser external,
            String internalUserId,
            Collection<? extends GrantedAuthority> authorities
    ) implements OidcUser {

        @Override
        public String getName() {
            return internalUserId;
        }

        @Override
        public Collection<? extends GrantedAuthority> getAuthorities() {
            return authorities;
        }

        @Override
        public Map<String, Object> getAttributes() {
            return external.getAttributes();
        }

        @Override
        public Map<String, Object> getClaims() {
            return external.getClaims();
        }

        @Override
        public OidcIdToken getIdToken() {
            return external.getIdToken();
        }

        @Override
        public OidcUserInfo getUserInfo() {
            return external.getUserInfo();
        }
    }
}
~~~

**Explanation:** the user service invokes the standard `OidcUserService` to load the OIDC user, reads `iss` and `sub` from the **framework-validated ID Token**, looks up the internal account, checks `active`, and builds an internal principal whose `getName()` is `usr_...` instead of the IdP name. The `OidcUser` wrapper retains the ID Token/UserInfo so other OIDC components can access them when needed. The example requires `LocalAccount.java` and `AccountLinkRepository.java` from section 7.1 plus a repository implementation; public Java classes must be organized in the matching package/file names.

**Additional production requirements:** validate IdP/registration tenant matching, map permission codes from a trusted source, handle account lookup timeouts, define status/session re-check policies, add unit/integration tests, and display safe login errors. `account_not_linked_or_disabled` should be mapped to a generic user-facing message that does not reveal specific account status. Never let the repository return admin permissions based on a request parameter or an unapproved claim.

### 7.3. Accessing the Principal in a Controller

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MeController {
    @GetMapping("/me")
    public String me(
            @AuthenticationPrincipal
            InternalOidcSecurityConfig.InternalOidcPrincipal principal) {
        return principal.internalUserId();
    }
}
~~~

When the external link resolves to `usr_1042`, `GET /me` returns the string `usr_1042`. This is a conditional illustrative response; there is no live token/login in the snippet. Avoid returning raw `external.getClaims()` to the frontend unnecessarily: tokens may contain personal data and internal metadata.

### 7.4. When Only Authorities Need Changing Without Changing the Principal

If the requirement is merely mapping an IdP group to `GrantedAuthority` values, `GrantedAuthoritiesMapper` is a leaner extension point. The mapper receives `OidcUserAuthority` (including ID Token/UserInfo) or `OAuth2UserAuthority` along with `SCOPE_...` authorities, returning the mapped authority set. However, the mapper **does not change the identity in `OidcUser.getName()`** and cannot easily call additional external resources without an access token in context. When you must look up an internal account and build a custom principal, use the `OAuth2UserService<OidcUserRequest, OidcUser>` strategy shown above.

## 8. Example B: Resource Server JWT Building Authentication with Internal User ID

An API can validate access tokens and use `JwtAuthenticationConverter` to assign `GrantedAuthority` instances. If you want `Authentication.getName()` to be the internal user ID, you can supply a custom converter returning `JwtAuthenticationToken` with the `name` argument; **the principal object remains `Jwt`**, unless a deeper converter/principal wrapper is implemented.

Integration example with Spring Security Resource Server, in another API application or a separate `SecurityFilterChain`:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-resource-server")
}
~~~

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.company.example/realms/staff
~~~

This configures basic issuer discovery/JWT validation in Spring Security. You must also add audience validation matching the `orders-api` API, algorithm checks, and business claims per system policy. **Do not treat the example YAML as a complete production security configuration.**

~~~java
import java.util.LinkedHashSet;
import java.util.Objects;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiJwtSecurityConfig {

    @Bean
    Converter<Jwt, ? extends AbstractAuthenticationToken> internalJwtConverter(
            AccountLinkRepository accounts) {
        return jwt -> {
            // Only invoked after JwtDecoder has validated the token.
            String issuer = jwt.getClaimAsString("iss");
            String subject = jwt.getSubject();

            if (issuer == null || subject == null) {
                throw new org.springframework.security.oauth2.core.OAuth2AuthenticationException(
                    new org.springframework.security.oauth2.core.OAuth2Error(
                        "invalid_external_identity"));
            }

            LocalAccount local = accounts
                    .findByExternalIdentity(issuer, subject)
                    .filter(LocalAccount::active)
                    .orElseThrow(() ->
                        new org.springframework.security.oauth2.core.OAuth2AuthenticationException(
                            new org.springframework.security.oauth2.core.OAuth2Error(
                                "account_not_linked_or_disabled")));

            var authorities = new LinkedHashSet<GrantedAuthority>();
            for (String permission : local.permissionCodes()) {
                authorities.add(new SimpleGrantedAuthority(permission));
            }

            // In the API: Authentication.getName() is the internal ID.
            // Authentication.getPrincipal() remains Jwt here.
            return new JwtAuthenticationToken(jwt, authorities, local.id());
        };
    }

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            Converter<Jwt, ? extends AbstractAuthenticationToken> internalJwtConverter)
            throws Exception {

        http.securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/orders/read")
                    .hasAuthority("APP_ORDER_READ")
                .requestMatchers("/api/orders/approve")
                    .hasAuthority("APP_ORDER_APPROVE")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth ->
                oauth.jwt(jwt ->
                    jwt.jwtAuthenticationConverter(internalJwtConverter)));

        return http.build();
    }
}
~~~

The example above reuses `LocalAccount` and `AccountLinkRepository` from the previous section; this is a **Servlet** configuration requiring a real IdP/JWKS + DB environment to run end-to-end. In production, ensure the JWT `aud` targets the receiving API, ID Tokens are not accepted instead of access tokens, and the issuer belongs to the trusted provider set; use a `JwtDecoder` validator or corresponding version config. All permission logic must come from a valid source; never use a user ID from the request as `name`.

### Distinguishing Changing the Name vs. Changing the Principal Object

- `JwtAuthenticationConverter.setPrincipalClaimName(...)` only changes the **claim used to name** the Authentication; it does not look up an internal user. Never point it at an `internal_user_id` claim without a trusted contract and blindly trust the value.
- The constructor `new JwtAuthenticationToken(jwt, authorities, local.id())` changes `Authentication.getName()` to the internal ID, while `getPrincipal()` remains `Jwt` in this usage.
- If business code wants an `InternalPrincipal` object holding tenant/status/permissions, it can provide a request-scoped abstraction built from trusted mapping, or a custom converter/principal appropriate for your Spring Security version. Do not force API and OIDC login to share the exact same Java principal type if the two flows have different security models and lifecycles.

## 9. Standalone Java 17 Example: Demonstrating Why Not to Link by Email

The snippet below **runs on plain JDK 17** without Spring or an IdP. It only illustrates the linking algorithm by issuer/subject pair and permissions from the internal account; **it does not validate token signatures or expiration**. Input to this function must come from a verified authentication layer in real applications.

~~~java
import java.util.Map;
import java.util.Set;

public class ExternalIdentityMappingDemo {
    record ExternalIdentity(String issuer, String subject, String email) {}
    record LocalUser(String id, boolean active, Set<String> permissions) {}

    public static void main(String[] args) {
        Map<String, LocalUser> links = Map.of(
            "https://idp-a.example|user-17",
            new LocalUser("usr_1042", true, Set.of("APP_ORDER_READ")),

            "https://idp-b.example|user-17",
            new LocalUser("usr_2099", true, Set.of("APP_ORDER_APPROVE"))
        );

        ExternalIdentity a = new ExternalIdentity(
            "https://idp-a.example", "user-17", "lan@example.test");
        ExternalIdentity b = new ExternalIdentity(
            "https://idp-b.example", "user-17", "lan@example.test");

        for (ExternalIdentity external : new ExternalIdentity[] {a, b}) {
            LocalUser local = links.get(
                external.issuer() + "|" + external.subject());
            if (local == null || !local.active()) {
                throw new SecurityException("account denied");
            }
            System.out.println(local.id() + " -> "
                + local.permissions().stream().sorted().toList());
        }
    }
}
~~~

Save as `ExternalIdentityMappingDemo.java` and run:

~~~bash
javac ExternalIdentityMappingDemo.java
java ExternalIdentityMappingDemo
~~~

Exact stdout:

~~~text
usr_1042 -> [APP_ORDER_READ]
usr_2099 -> [APP_ORDER_APPROVE]
~~~

Both identities share `sub=user-17` and `email=lan@example.test`, yet differ in issuer and therefore link to **two separate accounts**. Using only email or only subject as the key would mistakenly merge the two identities. In real systems, store the key as separate DB columns and normalize the issuer per client registration, rather than concatenating with `|` as a production key.

## 10. Practice: Separating OAuth Scopes, IdP Groups, and Business Permissions

Suppose a company has three APIs: reading orders, approving orders, and managing users. The IdP issues an access token with the following data:

~~~json
{
  "iss": "https://idp.company.example/realms/staff",
  "sub": "external-778",
  "aud": ["orders-api"],
  "scope": "openid profile orders.read",
  "groups": ["sales-team", "approvers"]
}
~~~

An appropriate evaluation flow:

1. The resource server validates the JWT, checking `iss`, `aud=orders-api`, expiration, and token conditions. `openid`/`profile` are **not** permissions to view orders.
2. Read `(iss,sub)` to locate `usr_1042` and its corresponding tenant, verifying `active`.
3. If `orders.read` is a scope trusted by the API from this issuer for this client, it may become `SCOPE_orders.read`; verify semantics to avoid turning scopes into unrelated permissions.
4. The `approvers` group is only supplemental input. Granting `APP_ORDER_APPROVE` must follow an allowlist keyed by tenant, app, and permitted group, or an internal table. Never “sum up every group” into admin.
5. For approval commands, also check whether the order falls under the user's scope and is in an approvable state.

In Spring Security resource server JWT, the default converts `scope`/`scp` into `SCOPE_...`. If the issuer uses an `authorities` or `roles` claim or a nested structure, you can use `JwtGrantedAuthoritiesConverter` (configuring claim name/prefix) or a custom converter. However, **this configuration must express an approved mapping**; never blindly read any claim named `roles` and assign `ROLE_ADMIN` without checking issuer/tenant.

~~~java
// Example when the "roles" claim only contains ALLOWED role codes
var roles = new org.springframework.security.oauth2.server.resource
    .authentication.JwtGrantedAuthoritiesConverter();
roles.setAuthoritiesClaimName("roles");
roles.setAuthorityPrefix("ROLE_");
~~~

This snippet **does not run standalone** and merely illustrates the converter API; with multiple IdPs, enforce claim values by policy and grant only approved permissions. In architectures using an internal principal, the converter in section 8 can load permissions exclusively from the local account, avoiding confusion with external permissions.

## 11. Handling Account Lifecycle, Provisioning, and Multi-IdP Linking

### 11.1. User Signs In for the First Time Without a Local Account

Choose one consistent policy:

- **Pre-invite / pre-provision:** administrators create the account and link `(iss,sub)` before the user signs in; unlinked logins are rejected or guided to onboarding.
- **JIT provisioning:** create a new account only when issuer/tenant/group satisfy allowlist criteria and the identity has been validated; grant minimal default permissions and never search existing accounts by email to merge.
- **SCIM / HRIS sync:** an HR system or provisioning service creates/locks accounts over their lifecycle; login only authenticates and links to an existing record.

Every policy must prevent duplicates on concurrent logins, enforce DB unique constraints, ensure idempotency, record audits, and provide a mechanism to fix mistaken links.

### 11.2. User Changes Email, Name, or Switches IdP

Changing email or name is a profile update, **not a change to the internal account key** as long as `(iss,sub)` remains unchanged. When changing issuer, realm, tenant, or subject strategy (e.g., pairwise), perform an evidenced and confirmed migration/linking flow; never auto-merge accounts by matching email. Multiple external identity links may be stored for one internal user if policy allows.

### 11.3. User Is Locked or Permissions Are Revoked

When a local account switches to `DISABLED`, mapping must block creating new sessions. For existing sessions/tokens, define a strategy for revalidation, session revocation, token TTL, and cache invalidation; changing an IdP group does not guarantee all old sessions update immediately. APIs with strict revocation requirements should check the internal authorization source at sensitive operations, balanced with performance and availability.

### 11.4. When the IdP Does Not Return a Group Claim

Some IdPs cap token size or expose groups through a separate API. A missing group claim must never turn into high default privileges. Design a clear policy: if the required permission source is absent, deny or grant only verified internal permissions; if calling a group API is required, use appropriate tokens/scopes, timeouts, bounded caching, and verify tenant/issuer.

## 12. Threat Model: Common Identity and Permission Mapping Bugs

| Scenario | Design Flaw | Consequence | Mitigation |
|---|---|---|---|
| Users A and B share an email over time | Linking accounts by `email` | The new holder receives the previous holder's data | Link by `iss+sub` and an approved transfer workflow. |
| Two IdPs share identical `sub` | Using `sub` alone | Cross-IdP account collision | Key by verified issuer + subject. |
| API accepts ID Token instead of access token | Checking only JWT signature | Wrong-audience/purpose token accepted at API | Enforce token type, `aud`, issuer, and validator. |
| App accepts arbitrary `roles=["ADMIN"]` | Directly mapping role claim | Privilege escalation | Allowlist issuer/tenant/group/policy; prefer internal permission source. |
| Group changes yet session stays valid long-term | Granting permissions from old snapshot | Revoked permissions persist | TTL, refresh/recheck, session invalidation. |
| IdP temporarily unavailable | “Temporarily grant admin to avoid disruption” | Uncontrolled privilege expansion | Fail closed, use bounded cache TTL and explicit policy. |
| `email_verified=true` | Treated as sufficient proof to merge accounts | Account takeover upon email reuse | Verify local account ownership before linking. |
| Multiple tenants have an `admins` group | Ignoring issuer tenant | Cross-tenant privilege escalation | Bind issuer/tenant/registration into mapping and policy. |
| Client sends claims via HTTP header | Bypassing token validation | Identity spoofing | Accept claims only from verified tokens/assertions. |
| Token has a different audience | Checking only issuer | Token issued for API A used on API B | Validate audience and token purpose at every API. |
| Local account is disabled | Trusting `sub` in token alone | Disabled account still accesses data | Check account status during authentication + policy cache. |

An ID Token with `email_verified=true`, or a JWT decodable on a public website, **is not** proof that it is valid for **the current application and intended token recipient**.

## 13. Testing Checklist for Identity, Claims, and Permissions

Tests should isolate each boundary, covering both “happy paths” and “deny paths”:

| Test Case | Expected Result |
|---|---|
| Valid `iss/sub`, account linked and active | Authentication succeeds; internal principal has right `user_id`; authorities match policy. |
| Same `sub` across two approved issuers | Maps to two distinct identities; no user collision. |
| Same email but different `iss/sub` | Does not auto-merge accounts; requires explicit linking. |
| Email changed while `iss/sub` unchanged | Internal user preserved; profile updated per policy. |
| Account linked yet disabled | Authentication fails or is blocked before business data. |
| No link found | Fails closed or enters designed onboarding; no admin fallback. |
| Claim `roles=ADMIN` from unapproved source | Does not grant `ROLE_ADMIN`. |
| Missing group claim; account has independent internal permissions | Applies defined permission source policy; grants no speculative permissions. |
| Expired JWT, invalid signature, or different `iss` | Rejected at token validation, before the mapper. |
| Valid JWT whose `aud` is not this API | Rejected; wrong-audience token never becomes a principal. |
| OAuth2 login succeeds yet permissions are insufficient | User is authenticated, but API/method returns 403 per policy. |
| Group removed in IdP while old session persists | Permissions expire per defined TTL/revalidation; not retained indefinitely. |
| Two concurrent creations of the same external link | Unique constraint and transaction ensure no two users share one link. |
| Multi-tenant with identically named roles | Grants roles only for the right tenant. |
| Nested claims / unexpected data types | Mapper rejects or chooses safe default policy; does not throw token-leaking errors. |

With Spring Security, MockMvc/Spring Security Test can verify authorization conditions without an IdP per test; alongside that, run real integration tests with a mock IdP/JWKS/redirects, repository, and session lifecycle to be certain `iss+sub` links as expected. Do not merely test that `hasRole("ADMIN")` works while neglecting to test **the data source that produces `ROLE_ADMIN`**.

## 14. Operations and Observability

Emit audit events correlated to requests/sessions, such as timestamp, trusted issuer ID/registration, normalized subject (optionally pseudonymized in logs), internal user ID, tenant, mapping outcome, and denial reason at a level that does not leak sensitive data. Avoid logging raw ID Tokens, access tokens, refresh tokens, or full profile claims.

Monitor login success rate, `account_not_linked`, audience mismatches, abnormal group/authority changes, repository/IdP errors, timeouts, cache hits, and sessions remaining active after offboarding. If synchronizing across multiple systems is needed, manage sessions/revocation via an explicit mechanism instead of expecting token claims to reflect real-time state.

When debugging, follow this order: **was the token/response actually validated → were issuer/subject extracted accurately → is there a unique linked internal user → is the account active → where do permissions come from → does the resource policy allow it**. Avoid returning differentiating messages like “email exists” vs. “account awaiting link” to unauthenticated users if that enables identity enumeration.

## 15. Architectural Conclusion

- **The IdP** is responsible for proving external identity and issuing validated claims under a trust contract.
- **Identity mapping** binds the external key `(iss,sub)` to an **immutable internal user ID** through a link table with clear ownership and lifecycle.
- **Authorization** relies on application-recognized authorities/policies while considering tenant, account status, and specific resources.
- **Spring Security** is the framework connecting these layers; `oauth2Login` and `oauth2ResourceServer` expose different extension points and must be configured appropriately for each flow.

With clear boundaries, the application can switch IdPs, change emails, add login providers, or revise group policies while keeping `usr_1042` as the consistent identity for business data and access control.

## References

1. [OpenID Connect Core 1.0 – Subject Identifier and Claim Stability](https://openid.net/specs/openid-connect-core-1_0-final.html): `iss/sub` identifiers, ID Token, `email_verified` claim, and pairwise subjects.
2. [Spring Security – OAuth2 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): `GrantedAuthoritiesMapper`, `OidcUserService`, and delegation-based mapping.
3. [Spring Security – OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JwtDecoder, `JwtAuthenticationConverter`, `JwtGrantedAuthoritiesConverter`, scopes/authorities, and token validation.
4. [Spring Security – Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `hasRole`, `hasAuthority`, HTTP request authorization.
5. [RFC 9068 – JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token claims profile, audience requirements, and API purpose.
