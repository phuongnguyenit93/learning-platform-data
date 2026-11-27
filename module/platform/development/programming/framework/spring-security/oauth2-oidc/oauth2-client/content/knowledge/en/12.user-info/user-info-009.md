# 12.9. Enriching Profile Data from an Internal User Service

## 1. Scenario: Logging In via OIDC While Business Profiles Live in a Separate System

In a Spring Security OAuth 2.0/OIDC Client application, users typically sign in through an **OpenID Provider (OP)** such as a corporate SSO system. After authentication, the Client receives an ID Token and can call the UserInfo Endpoint to fetch standard OIDC claims such as name, email, avatar, or locale.

However, the application needs more than just those details. For example, a rental management portal may need:

- An **internal** user ID to link contracts and transaction history.
- Normalized department, branch, business unit, and display name.
- Internal account status: active, locked, pending approval.
- Application roles: <code>EMPLOYEE</code>, <code>SUPPORT</code>, <code>BILLING_ADMIN</code>.
- Business attributes such as approval limits, data access tier, and owning unit.

This data is typically managed by an **internal user service**, not the OP. Therefore, the application needs to **enrich profile data** after OIDC authentication without losing the trusted attributes from the ID Token and UserInfo.

We call this process **profile enrichment**: using the OP-verified identity to look up an internal record, fetch business data validated by the internal service, and build the appropriate principal/authorization context.

> **Distinguish from the start:** the OP proves **which user logged in**; the internal user service tells you **which business account that person corresponds to and what they are allowed to do in the application**. Profile enrichment does not mean altering the OP's ID Token.

## 2. Data Sources and Trust Boundaries

A system typically has at least three data sources:

| Source | Common Data | Who Is Responsible? |
|---|---|---|
| **ID Token** | <code>iss</code>, <code>sub</code>, <code>aud</code>, <code>exp</code>, name/email if provided by OP | OpenID Provider; Spring Security verifies the token |
| **OIDC UserInfo** | Name, email, avatar, locale, and profile claims published by OP | OpenID Provider; Client queries using an appropriate access token |
| **Internal User Service** | Internal user ID, department, status, roles, unit, business permissions | Internal user/authorization service |

Example of what two sources might return:

**Verified OIDC ID Token:**

~~~json
{
  "iss": "https://idp.example.org/realms/workforce",
  "sub": "6d90a0c3-7d90-4b35-8be5-51a1c8e08f45",
  "aud": "rental-portal",
  "email": "alex@example.org",
  "email_verified": true
}
~~~

**Response from the internal user service:**

~~~json
{
  "id": "9f14ac31-1ce1-4ee5-9e30-d0e7a8f4341a",
  "displayName": "Alex Nguyen",
  "department": "Customer Operations",
  "active": true,
  "roles": ["EMPLOYEE", "SUPPORT"]
}
~~~

The IDs, domains, and profile details in the examples are all dummy data.

We must keep separate:

1. **Identity from the OP:** the <code>(issuer, subject)</code> pair, verified from the ID Token.
2. **Internal identity:** <code>internalUserId</code>, managed by the business system.
3. **Display information:** name, avatar, email; may have multiple sources and precedence rules.
4. **Permissions:** verified internal roles/permissions, never taken blindly from an arbitrary claim.

Never use <code>email</code> as the sole key to look up and link internal accounts simply because it is easy to read.

### 2.1. Why Must You Use the (iss, sub) Pair?

OIDC defines <code>sub</code> as the End-User identifier **within the scope of the issuer**. The same <code>sub</code> string coming from two different issuers does not automatically identify the same person.

Example:

~~~text
Issuer A: https://idp.example.org/realms/tenant-a
Subject:  12345

Issuer B: https://idp.example.org/realms/tenant-b
Subject:  12345
~~~

The two cases must be treated as **two distinct external identities**, unless there is a separately verified account-linking workflow.

Appropriate mapping key design:

~~~text
ExternalIdentity(issuer, subject)  →  InternalUserId
~~~

With a database, you can store a table:

~~~sql
CREATE TABLE external_identities (
    issuer           VARCHAR(512) NOT NULL,
    subject          VARCHAR(255) NOT NULL,
    internal_user_id UUID NOT NULL,
    created_at       TIMESTAMP NOT NULL,
    PRIMARY KEY (issuer, subject)
);
~~~

This is an illustrative schema. Choose column lengths, timestamp types, and indexes suited to your database, along with foreign-key constraints to the internal users table if the architecture permits.

**Do not auto-link by email**: email can change, be reused, or be unverified. Even <code>email_verified=true</code> does not prove two accounts from two issuers are the same business account permitted to be merged. Account linking must be a separate process with verification and controls.

## 3. Architecture for Profile Enrichment After OIDC Login

In Servlet OAuth2 Login, Spring Security provides the <code>OidcUserService</code> mechanism to fetch and construct <code>OidcUser</code> after the token exchange step.

We can **delegate** to the default <code>OidcUserService</code> to run standard OIDC/UserInfo logic first, then use the verified subject/issuer to query the internal service.

~~~mermaid
flowchart TD
    A["Browser starts OIDC Login"] --> B["Authorization Code Flow at OP"]
    B --> C["Spring Security exchanges token"]
    C --> D["Default OidcUserService"]
    D --> E["Processed ID Token / UserInfo"]
    E --> F["Extract trusted (iss, sub)"]
    F --> G["InternalProfileGateway"]
    G --> H["Internal User Service"]
    H --> I{"Internal user exists and active?"}
    I -->|No| X["Reject login or provision per policy"]
    I -->|Yes| J["Retrieve internal ID, display name, roles"]
    J --> K["Build enriched principal"]
    K --> L["SecurityContext / HTTP session"]
    L --> M["Controllers / Method Security"]
~~~

Detailed sequence:

1. Browser is redirected to the OP; user logs in.
2. OP returns an authorization code; Spring Security performs token exchange.
3. Spring Security's OIDC processor verifies the ID Token; <code>OidcUserService</code> may query UserInfo when provider/scope conditions match.
4. The application reads <code>iss</code> and <code>sub</code> from the verified OIDC data.
5. Client calls the **internal user service** over a system-managed secure channel.
6. The internal service looks up the record by <code>(iss, sub)</code> and returns the profile.
7. The application checks user status and maps permitted roles.
8. A custom <code>OidcUser</code> preserves original OIDC data while exposing <code>internalUserId</code> and internal metadata.
9. Subsequent requests use the principal and/or query the internal service per data-freshness policy.

### 3.1. Sequence Diagram

~~~mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant C as Spring Security Client
    participant OP as OpenID Provider
    participant U as Internal User Service
    B->>C: GET /oauth2/authorization/company
    C-->>B: 302 to OP, state/nonce/PKCE per flow
    B->>OP: Login
    OP-->>B: Callback with code and state
    B->>C: GET /login/oauth2/code/company?code=...&state=...
    C->>OP: Token request
    OP-->>C: ID Token / access token
    C->>C: Verify ID Token, build OidcUser
    opt When eligible for OIDC UserInfo
        C->>OP: GET UserInfo with OP's access token
        OP-->>C: UserInfo claims
    end
    C->>C: Extract issuer + subject from verified identity
    C->>U: Resolve external identity using service credential
    U-->>C: Internal user ID, active, department, roles
    C->>C: Map authorities + create enriched principal
    C-->>B: Login success / session
~~~

**Do not forward the access token issued for the OP/UserInfo to the internal user service by default.** Access tokens have specific audiences and scopes; an internal API should accept that token only if it is genuinely a resource server for which the token was issued and performs full validation. Normally, use a dedicated **service-to-service credential** for internal APIs.

## 4. Choosing the Right Extension Point in Spring Security

Spring Security offers several extension points:

| Extension Point | Used For | When to Choose |
|---|---|---|
| <code>OAuth2UserService&lt;OidcUserRequest, OidcUser&gt;</code> | **OIDC** user-loading process | Need to fetch UserInfo and enrich with internal user |
| <code>OidcUserService</code> | Standard OIDC user service implementation | Used as a delegate to keep standard OIDC behavior |
| <code>oauth2Login().userInfoEndpoint().oidcUserService(...)</code> | Wiring custom OIDC service into login flow | Primary integration approach in this lesson |
| <code>oauth2Login().userInfoEndpoint().userService(...)</code> | **Non-OIDC** OAuth 2.0 Login | Provider lacks <code>openid</code> scope / OIDC ID Token |
| <code>GrantedAuthoritiesMapper</code> | Mapping authorities after user is loaded | Only need to transform authorities without a custom principal |
| <code>AuthenticationSuccessHandler</code> | Routing and post-login tasks | Not ideal for replacing the entire OidcUser creation process |
| Domain service in controller/service | Looking up profile during app usage | Profile changes frequently or shouldn't live in session |

In this lesson, we choose a **custom OidcUserService with a delegate** because we need both internal data and authorities after OIDC verification.

> For pure OAuth2 Login, use <code>userService(...)</code> and <code>OAuth2User</code> rather than mechanically applying <code>OidcUserService</code>. The two flows are related but not identical.

### 4.1. Why Not Parse the ID Token Yourself?

An ID Token can be a JWT signed with the OP's key. Spring Security already provides logic to verify issuer, audience, signature, timestamps, and OIDC constraints when configured properly. Manually parsing the payload by splitting the JWT string and Base64URL-decoding only yields **untrusted self-asserted data**.

A custom user service must run **after** the framework's OIDC logic, not replace it. Never take <code>iss</code>/<code>sub</code> from the callback URL, browser-supplied query parameters, or an unverified JWT payload to call an internal API.

## 5. Designing the Internal Profile Data

Java 17 example with a record serving as a profile snapshot:

~~~java
package example.security.profile;

import java.io.Serializable;
import java.util.Set;
import java.util.UUID;

public record InternalUserProfile(
        UUID id,
        String displayName,
        String department,
        boolean active,
        Set<String> roles
) implements Serializable {
    private static final long serialVersionUID = 1L;
}
~~~

Fields:

- <code>id</code>: stable internal key for linking business data tables.
- <code>displayName</code>: display name managed by the business system.
- <code>department</code>: organizational info; not used as an access permission by default.
- <code>active</code>: status indicating whether use of the system is permitted.
- <code>roles</code>: internal roles following an application-controlled taxonomy.

This is only a snapshot for the lesson. A real user service may include version, updated timestamp, provisioning status, or tenant info. **Do not stuff unnecessary sensitive data** such as birth date, ID documents, or account numbers into the principal just to render a small screen.

Service query interface:

~~~java
package example.security.profile;

import java.util.Optional;

public interface InternalProfileGateway {

    Optional<InternalUserProfile> findByExternalIdentity(
            String issuer,
            String subject);
}
~~~

With this interface, <code>Optional.empty()</code> means **no user mapping was found**. It must not be used to lump together network errors, service authentication errors, or server failures.

Distinguishing statuses helps the application make the right decision:

| Outcome | Meaning | Typical Policy |
|---|---|---|
| User exists and <code>active=true</code> | Identity has an active internal account | Proceed to build principal/roles |
| User not found | Not yet linked/provisioned | Reject or run permitted JIT provisioning flow |
| User exists but <code>active=false</code> | User locked/no longer active internally | Disallow logging into the application |
| HTTP 401/403 calling internal API | Service credential/permission error | System error; do not treat as nonexistent user |
| Timeout/HTTP 5xx | Internal service temporarily unavailable | Fail closed for sensitive privileges; avoid fabricating users |
| Malformed payload schema | Internal API incompatible or corrupted data | Report integration error; do not invent default roles |

## 6. Building a Principal Carrying Both OIDC Identity and Internal Profile

There are two common approaches:

1. Construct a new <code>DefaultOidcUser</code> with added authorities. This is simple if the application only needs roles and looks up the internal user ID via another service.
2. Create a **wrapper implementing <code>OidcUser</code>** holding the OIDC delegate and internal profile snapshot. This preserves the original OIDC claims intact while exposing <code>internalUserId</code> without spoofing claims signed by the OP.

When both profile display and internal ID are needed, a wrapper is a clean choice.

### 6.1. Custom OidcUser Wrapper

~~~java
package example.security.profile;

import java.io.Serial;
import java.io.Serializable;
import java.util.Collection;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.Map;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.OidcUserInfo;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

public final class EnrichedOidcUser implements OidcUser, Serializable {

    @Serial
    private static final long serialVersionUID = 1L;

    private final OidcUser delegate;
    private final InternalUserProfile internalProfile;
    private final Collection<? extends GrantedAuthority> authorities;

    public EnrichedOidcUser(
            OidcUser delegate,
            InternalUserProfile internalProfile,
            Collection<? extends GrantedAuthority> authorities) {
        this.delegate = delegate;
        this.internalProfile = internalProfile;
        this.authorities = Collections.unmodifiableSet(
            new LinkedHashSet<>(authorities));
    }

    public InternalUserProfile internalProfile() {
        return internalProfile;
    }

    @Override
    public Collection<? extends GrantedAuthority> getAuthorities() {
        return authorities;
    }

    @Override
    public String getName() {
        return delegate.getName();
    }

    @Override
    public Map<String, Object> getAttributes() {
        return delegate.getAttributes();
    }

    @Override
    public Map<String, Object> getClaims() {
        return delegate.getClaims();
    }

    @Override
    public OidcIdToken getIdToken() {
        return delegate.getIdToken();
    }

    @Override
    public OidcUserInfo getUserInfo() {
        return delegate.getUserInfo();
    }
}
~~~

The wrapper preserves:

- <code>getIdToken()</code>: the ID Token processed by the framework.
- <code>getUserInfo()</code>: UserInfo if provided by the OP and used by Spring Security.
- <code>getClaims()</code>, <code>getAttributes()</code>: OIDC data as in the original principal.
- <code>getName()</code>: the original OIDC principal's naming semantics, not swapped for the internal user ID.
- <code>getAuthorities()</code>: newly curated authorities selected by the application.
- <code>internalProfile()</code>: profile snapshot from the internal service.

**Why not mutate <code>id_token</code> or its claims?** The ID Token was issued and signed by the OP. If the application injects <code>department</code>, <code>internalUserId</code>, or internal roles into the claims map and still calls it the "verified ID Token", readers easily confuse trust origins. Separating <code>internalProfile</code> from OIDC claims is much clearer.

If using a distributed HTTP session (e.g., Spring Session storing principals), ensure every stored object has serialization compatible with the session store, version, and deployment model. Store only minimal data since roles/profiles can become stale.

## 7. Custom OidcUserService: Delegate First, Then Enrich

We build an <code>OAuth2UserService&lt;OidcUserRequest, OidcUser&gt;</code> using the default <code>OidcUserService</code> as a delegate.

### 7.1. Java Code

~~~java
package example.security.profile;

import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Set;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.core.user.OAuth2UserService;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClientException;

@Service
public class EnrichingOidcUserService
        implements OAuth2UserService<OidcUserRequest, OidcUser> {

    private static final Set<String> ALLOWED_ROLES = Set.of(
        "EMPLOYEE", "SUPPORT", "BILLING_ADMIN");

    private final OidcUserService delegate = new OidcUserService();
    private final InternalProfileGateway profileGateway;

    public EnrichingOidcUserService(InternalProfileGateway profileGateway) {
        this.profileGateway = profileGateway;
    }

    @Override
    public OidcUser loadUser(OidcUserRequest userRequest)
            throws OAuth2AuthenticationException {

        // Preserve Spring Security's default OIDC/UserInfo logic.
        OidcUser oidcUser = delegate.loadUser(userRequest);

        // Extract identity from the ID Token that already passed OIDC validation.
        String issuer = oidcUser.getIdToken().getClaimAsString("iss");
        String subject = oidcUser.getSubject();
        if (issuer == null || issuer.isBlank()
                || subject == null || subject.isBlank()) {
            throw rejected("invalid_external_identity");
        }

        final InternalUserProfile profile;
        try {
            profile = profileGateway.findByExternalIdentity(issuer, subject)
                .orElseThrow(() -> rejected("internal_account_not_found"));
        } catch (RestClientException ex) {
            // Do not convert infrastructure failures into "user not found".
            throw new OAuth2AuthenticationException(
                new OAuth2Error(
                    "internal_profile_unavailable",
                    "Internal profile service is unavailable",
                    null),
                ex);
        }

        if (!profile.active()) {
            throw rejected("internal_account_disabled");
        }

        Collection<GrantedAuthority> authorities =
            new LinkedHashSet<>(oidcUser.getAuthorities());

        if (profile.roles() != null) {
            profile.roles().stream()
                .filter(ALLOWED_ROLES::contains)
                .map(role -> new SimpleGrantedAuthority("ROLE_" + role))
                .forEach(authorities::add);
        }

        return new EnrichedOidcUser(oidcUser, profile, authorities);
    }

    private static OAuth2AuthenticationException rejected(String code) {
        return new OAuth2AuthenticationException(
            new OAuth2Error(code, "Unable to complete sign-in", null));
    }
}
~~~

In the code:

1. <code>delegate.loadUser(userRequest)</code> lets Spring Security build the OIDC principal per existing configuration.
2. <code>iss</code>/<code>sub</code> come from the OIDC principal's ID Token, **not from unverified request data**.
3. <code>profileGateway.findByExternalIdentity(...)</code> looks up the right profile by both keys.
4. Missing profile or <code>active=false</code> → **disallow application login** per the illustrative policy.
5. Internal API call errors are classified separately from "user not found".
6. Internal roles are **allowlisted**, converted to <code>ROLE_...</code> authorities per Spring Security convention.
7. The wrapper keeps original OIDC data, adding only what the application manages.

<code>ALLOWED_ROLES</code> in the example represents **application** roles. In real projects, define a central authorization policy and keep permission names synchronized with the business backend. Never automatically convert every string returned by an internal API into an authority — misconfigured data could inadvertently grant admin rights.

### 7.2. When OIDC UserInfo Is Used

<code>OidcUserService</code> may call the UserInfo Endpoint depending on conditions such as scopes, endpoint configuration, and tokens provided by the OP. UserInfo contents come from the **OP**, not from the internal user service.

Do not manually call UserInfo with the user access token inside a custom service just to fetch claims the delegate already loaded. If you need to customize how UserInfo is loaded, Spring Security offers dedicated configuration/extension points on <code>OidcUserService</code> depending on version.

In all cases, UserInfo data has its own security requirement: the OP must return a <code>sub</code> claim matching the ID Token's subject per OIDC. Never fetch UserInfo from an arbitrary endpoint and assume it belongs to the same identity as the ID Token.

### 7.3. If Periodic Profile Synchronization Is Needed

A single internal API call at login creates only a **snapshot**. If a role changes while the user is logged in, the principal in the HTTP session does not change automatically.

Options:

- Accept the snapshot for low-sensitivity display data until the user logs in again.
- Use a TTL and session profile-refresh mechanism for appropriate pages or actions.
- For sensitive permissions, re-query the authority/entitlement source at the time an action is performed.
- Use user-locked/role-changed events to revoke sessions or refresh the context.

**Never treat a session snapshot as an eternal source of truth** for privileges that may need urgent revocation.

## 8. Wiring EnrichingOidcUserService into SecurityFilterChain

Spring Boot 3, Spring Security 6 running Servlet example:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

OIDC provider configuration:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: rental-web-client
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]
        provider:
          company:
            issuer-uri: https://idp.example.org/realms/workforce
~~~

In production, Client ID, secret, issuer, and redirect URI must match the registration on the OP. Never commit real secrets; environment variables in the example are placeholders.

Spring Security configuration:

~~~java
package example.security;

import example.security.profile.EnrichingOidcUserService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.SimpleUrlAuthenticationFailureHandler;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain webSecurity(
            HttpSecurity http,
            EnrichingOidcUserService enrichingOidcUserService)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error", "/assets/**").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(login -> login
                .userInfoEndpoint(userInfo -> userInfo
                    .oidcUserService(enrichingOidcUserService))
                .failureHandler(
                    new SimpleUrlAuthenticationFailureHandler("/login?error")));

        return http.build();
    }
}
~~~

Here:

- <code>userInfoEndpoint().oidcUserService(...)</code> is where the custom OIDC user service hooks into the login flow.
- Spring Security still handles the Authorization Code Flow, callback, ID Token, and authentication mechanics.
- When <code>EnrichingOidcUserService.loadUser(...)</code> throws <code>OAuth2AuthenticationException</code>, login is treated as **failed**, never creating a successful session.
- The failure handler redirects to the login page with a generic notice; never place raw internal API errors, tokens, or sensitive details in URLs.

This pattern assumes the internal profile service has an explicit policy: if a user is missing or locked, disallow login. Applications with a policy of "restricted login when profile service is temporarily down" must define a separate **restricted role** and ensure no unintended privileges are opened.

**Multiple filter chains:** if the web chain has a <code>securityMatcher</code> restricted to <code>/app/**</code>, include the default endpoints <code>/oauth2/authorization/**</code> and <code>/login/oauth2/code/**</code> as well. If the callback is matched first by an API chain, the custom OIDC service may never run.

## 9. Connecting to the Internal User Service via RestClient

The custom OIDC service above depends on <code>InternalProfileGateway</code>. Below is an illustrative HTTP adapter using Spring Framework 6.1+ <code>RestClient</code>, suitable for Spring Boot 3.2+.

Suppose the internal API has the contract:

~~~http
POST /internal/users/resolve HTTP/1.1
Content-Type: application/json
Authorization: Bearer SERVICE_ACCESS_TOKEN

{
  "issuer": "https://idp.example.org/realms/workforce",
  "subject": "6d90a0c3-7d90-4b35-8be5-51a1c8e08f45"
}
~~~

Success response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "9f14ac31-1ce1-4ee5-9e30-d0e7a8f4341a",
  "displayName": "Alex Nguyen",
  "department": "Customer Operations",
  "active": true,
  "roles": ["EMPLOYEE", "SUPPORT"]
}
~~~

The API returns HTTP 404 when no mapping exists, HTTP 401/403 when service credentials are invalid, and HTTP 5xx on server error. This is an **illustrative contract**, not a default endpoint provided by Spring Security or OIDC.

### 9.1. Providing a Dedicated Service Token

To avoid accidentally forwarding a user's access token to another API, define a dependency that supplies tokens for the internal service:

~~~java
package example.security.profile;

public interface InternalServiceTokenProvider {
    String getAccessTokenForProfileApi();
}
~~~

A real application must supply an implementation using **OAuth 2.0 client credentials**, mTLS, or an appropriate service authentication mechanism. If using OAuth2 client credentials, the token needs the audience/scopes permitted by the internal API and must be cached/refreshed according to actual expiration.

This interface intentionally **does not return the user access token** from OIDC Login. Nor should the application hardcode a static bearer token string directly in source code.

### 9.2. Illustrative HTTP Adapter

~~~java
package example.security.profile;

import java.time.Duration;
import java.util.Optional;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;

@Component
public final class RestInternalProfileGateway
        implements InternalProfileGateway {

    private final RestClient restClient;

    public RestInternalProfileGateway(
            RestClient.Builder restClientBuilder,
            @Value("${app.internal-profile.base-url}") String baseUrl,
            InternalServiceTokenProvider tokenProvider) {

        var requestFactory = new SimpleClientHttpRequestFactory();
        requestFactory.setConnectTimeout(Duration.ofSeconds(2));
        requestFactory.setReadTimeout(Duration.ofSeconds(3));

        this.restClient = restClientBuilder
            .baseUrl(baseUrl)
            .requestFactory(requestFactory)
            .requestInterceptor((request, body, execution) -> {
                request.getHeaders().setBearerAuth(
                    tokenProvider.getAccessTokenForProfileApi());
                return execution.execute(request, body);
            })
            .build();
    }

    @Override
    public Optional<InternalUserProfile> findByExternalIdentity(
            String issuer,
            String subject) {
        try {
            InternalUserProfile profile = restClient
                .post()
                .uri("/internal/users/resolve")
                .contentType(MediaType.APPLICATION_JSON)
                .body(new ExternalIdentityLookup(issuer, subject))
                .retrieve()
                .body(InternalUserProfile.class);

            if (profile == null) {
                throw new IllegalStateException(
                    "Internal profile response body is empty");
            }

            return Optional.of(profile);
        } catch (HttpClientErrorException.NotFound ex) {
            // API contract: 404 genuinely means no mapping exists yet.
            return Optional.empty();
        }
    }

    private record ExternalIdentityLookup(
            String issuer,
            String subject) {
    }
}
~~~

Configuration property:

~~~yaml
app:
  internal-profile:
    base-url: https://users.internal.example.org
~~~

**To complete before deploying:** implement the <code>InternalServiceTokenProvider</code> bean with valid service authentication, configure TLS trust, connection limits, and error observability. Without a token provider, the Spring context cannot instantiate the adapter; that is an intentional dependency, not a token auto-issued by Spring.

Additionally:

- Only use the base URL from trusted configuration; never accept user-supplied URLs to prevent SSRF.
- Connect over HTTPS with certificate verification; never disable TLS validation.
- The internal API must authenticate the service and verify authorization; being on an internal network **does not mean trustworthy**.
- Limit response sizes and set connect/read timeouts; use an HTTP client suited to production needs.
- Distinguish **404** from **401/403/5xx**; never catch all exceptions and return <code>Optional.empty()</code>.
- Never log raw tokens, <code>Authorization</code> headers, OIDC cookies, or responses containing PII.

In the example, <code>HttpClientErrorException.NotFound</code> is translated to "account does not exist". Other errors (timeouts, HTTP 5xx, JSON errors, service authentication) continue throwing exceptions. The custom user service should classify and surface errors safely. For malformed payload errors outside <code>RestClientException</code> or null data, provide dedicated handling per your project's integration error policy; never treat them as "user has no mapping".

### 9.3. Do Not Forward the OIDC Access Token to Internal APIs by Default

Distinguish the two HTTP channels:

~~~text
Spring OIDC Client ---- user access token ----> OP UserInfo Endpoint

Spring OIDC Client ---- service access token ---> Internal User Service
~~~

An access token issued by the OP for UserInfo or another API has a specific **audience**, scope, and subject. Sending that token to an internal service can not only fail due to audience mismatch, but also risks **token leakage** and blurring authorization boundaries.

If an internal API needs to act **on behalf of the user**, design a token exchange/on-behalf-of flow per the IdP and Resource Server contracts. That is a dedicated flow requiring audience, scope, delegation, and consent checks, never replaced by blindly forwarding the user access token.

## 10. Accessing the Internal Profile from Controllers and Method Security

With <code>EnrichedOidcUser</code> as the Authentication principal, controllers can read needed fields without re-parsing tokens.

~~~java
package example.web;

import example.security.profile.EnrichedOidcUser;
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MeController {

    @GetMapping("/me")
    public Map<String, String> me(
            @AuthenticationPrincipal EnrichedOidcUser principal) {
        var profile = principal.internalProfile();

        return Map.of(
            "internalUserId", profile.id().toString(),
            "displayName", profile.displayName(),
            "department", profile.department()
        );
    }
}
~~~

This example assumes <code>displayName</code> and <code>department</code> are non-null. In real APIs, use a dedicated DTO and handle null/optional values so <code>Map.of</code> does not throw exceptions.

**Never send the entire <code>OidcUser</code>, <code>OidcIdToken</code>, access token, or internal profile containing unnecessary PII to the frontend.** Return only fields the UI is permitted to receive.

### 10.1. Internal Roles as GrantedAuthority

Inside <code>EnrichingOidcUserService</code>:

~~~java
new SimpleGrantedAuthority("ROLE_BILLING_ADMIN")
~~~

Then, on an endpoint:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class BillingController {

    @PostMapping("/billing/close-period")
    @PreAuthorize("hasRole('BILLING_ADMIN')")
    public String closePeriod() {
        return "Period closure requested";
    }
}
~~~

Enabling method security:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

<code>hasRole("BILLING_ADMIN")</code> matches authority <code>ROLE_BILLING_ADMIN</code> with Spring Security's default role prefix. The application must establish a trusted role source, govern role changes, and verify permissions before executing real actions.

The sample controller only illustrates authorization; an actual accounting period close also needs transaction control, auditing, CSRF protection for browser sessions, input validation, and a domain service.

### 10.2. Do Not Automatically Treat Every Claim as a Permission

For example, the ID Token has:

~~~json
{
  "preferred_username": "alex",
  "groups": ["admins"]
}
~~~

That **does not automatically** prove the application must grant <code>ROLE_BILLING_ADMIN</code>. The <code>groups</code> claim may have meaning at the OP without necessarily mapping accurately to the application's business roles. Map only when there is an explicit policy recognizing the issuer/claim, or rely on roles provided by an authoritative internal service.

## 11. Strategies When a User Does Not Yet Exist in the Internal System

When OIDC succeeds yet <code>(iss, sub)</code> is not found, several policies are possible.

### 11.1. Allow Login Only for Pre-Authorized Users

Suitable for internal portals or sensitive-data systems:

~~~text
Valid OIDC identity
    -> InternalProfileGateway: 404 / no mapping
    -> OAuth2AuthenticationException("internal_account_not_found")
    -> Login failed with generic message
~~~

This prevents automatically creating accounts for any valid OP identity. Administrators must approve and create the mapping beforehand.

### 11.2. Just-in-Time Provisioning (JIT)

Some applications allow creating an internal profile the first time a user logs in. If using JIT:

1. Allow only trusted configured issuers/clients/tenants.
2. Fully verify the ID Token before creating the user.
3. Use <code>(iss, sub)</code> as the external identity; enforce a unique constraint to prevent duplicates during concurrent requests.
4. Create the user with **least privilege**, optionally pending approval; never take privileged roles from self-asserted fields.
5. Clearly set status, creation source, audit trail, and account deletion/lock policies.
6. Avoid auto-linking to existing accounts based solely on matching email.

JIT provisioning should live in a **transactional, idempotent domain service**, rather than arbitrary database inserts directly inside a controller callback.

### 11.3. Linking an Existing Account

If a user wants to link a new OIDC identity to an older internal account, use a dedicated guarded workflow: the user proves ownership of both the existing identity and the new identity, meets assurance/reauthentication requirements if needed, and records the mapping with auditing.

Never auto-merge accounts merely because <code>email</code>, <code>name</code>, <code>preferred_username</code>, or phone number match.

## 12. Risk of Stale Data in Sessions and How to Handle It

For example, a user logs in at 09:00 and the service returns:

~~~json
{
  "active": true,
  "roles": ["BILLING_ADMIN"]
}
~~~

At 10:00, an administrator revokes <code>BILLING_ADMIN</code> in the internal service. If the application keeps authorities solely in the HTTP session, the user's <code>SecurityContext</code> may retain the old permission until the session is updated, expires, or the user re-logs in.

Therefore, choose consistently:

| Data Category | Typically Suitable Strategy |
|---|---|
| Display name, photo, locale | Short cache or until next login if stale data is acceptable |
| Department, branch | TTL and refresh as needed if changes affect data authorization |
| General business roles | Versioned/TTL cache and invalidation mechanism if required |
| Financial approval, bulk export, account locking | Check near action time, revocation, or session invalidation |
| Locked/terminated status | Fast detection mechanism; do not wait for long session expiry |

**The session is an authentication cache/frame from login time**, not a real-time permission synchronization mechanism. If immediate revocation is needed, add a complementary strategy.

### 12.1. Refreshing Permissions Across Multiple Instances

When running multiple nodes:

- HTTP sessions may live on specific nodes or in Spring Session/Redis.
- Nodes must share the same interpretation of authorities and internal user IDs.
- Serialized principal data must stay version-compatible; avoid holding heavy domain objects and non-serializable references.
- When roles change, use events/invalidation or check permissions directly in the domain service so nodes do not hold divergent snapshots.
- If the internal service is temporarily down, never swap current roles for broader privileges.

### 12.2. Should You Call the Internal Service on Every Request?

Not always necessary. Calling an internal API on every request can cause:

- Increased latency, especially when the UI fires many requests.
- Load pressure on the internal service and risk of cascading failures.
- Harder control over timeouts/circuit breakers and rate limits.
- Risk of information exposure across excessive network calls/logs.

Typically, balance with time-bounded caches, re-reading on business changes, checking permissions in domain services, or event-driven invalidation. For highly sensitive actions, however, a fresh current-permission check can be worth more than relying on an old snapshot.

## 13. Resilience When the Profile Service Fails

Enriching profiles during OIDC Login introduces a new dependency: the OP may be healthy while the internal user service fails temporarily. Classify failures and set explicit policies.

| Situation | What Not to Do | Appropriate Behavior |
|---|---|---|
| Timeout from internal service | Assume user doesn't exist or create a new user | Report system error, controlled retry at the right layer |
| HTTP 401/403 from internal service | Try forwarding the OP user access token as credentials | Fix service authentication/audience/permissions |
| HTTP 404 | Treat as outage or retry infinitely | Apply unprovisioned-user policy |
| HTTP 503 | Grant every user <code>ROLE_EMPLOYEE</code> by default | Fail closed or explicitly designed restricted mode |
| Response missing <code>id</code> or <code>active</code> | Substitute dummy values to let login succeed | Treat as invalid data and reject/investigate |
| User <code>active=false</code> | Grant privileged session because ID Token is valid | Block access per internal policy |

### 13.1. Timeouts, Circuit Breakers, and Retries

Internal connections must have sensible timeouts so login requests never hang indefinitely. In multi-user systems, use circuit breakers/bulkheads to contain outages.

If retrying, retry only semantically safe cases such as transient network errors or HTTP 503 with **bounded attempts/backoff**. Never retry HTTP 404 or 403 endlessly. Identity lookup APIs should have idempotent semantics per contract; if using POST for lookup, verify the server processes queries without side effects before enabling retries.

### 13.2. Fail-Closed Policy and Restricted Mode

For applications holding sensitive data, if the internal user or permissions cannot be verified, **granting no business permissions** is the safe default.

Some public-facing applications may allow OIDC users to log in under an "incomplete profile" mode, provided they:

- Use a distinct principal/state for restricted mode.
- Allow only public endpoints and defined onboarding-completion steps.
- Never use a default role to access business data.
- Never equate a 5xx outage with a new unprovisioned user.

This is a product/security decision, not default behavior of <code>OidcUserService</code>.

## 14. Distinguishing Identity Resolution from Profile Synchronization

Two actions easily get conflated:

**Identity resolution:** determining which internal user an OIDC identity points to:

~~~text
(iss, sub) -> internalUserId
~~~

**Profile synchronization:** updating name, email, photo, locale, or OP-permitted fields in the internal profile.

If every OIDC field is overwritten into the database on every login, the application might overwrite values managed by HR/customer support. Define a **source of truth** per field:

| Field | Illustrative Primary Source | Behavior |
|---|---|---|
| External issuer/subject | Verified ID Token | Used solely as linking key; never user-editable |
| Internal user ID | Internal user service/database | Never accepted from arbitrary claims |
| Contact email | Internal profile or OIDC per policy | Reconcile rules and check <code>email_verified</code> where appropriate |
| Display name | Internal profile or OP | Do not overwrite if users are permitted to edit it |
| Department | Internal HR/user service | Do not blindly trust self-asserted profile claims |
| Roles/permissions | Internal authorization service | Enforce grant and revocation policies |
| Profile photo | Possibly OP/UserInfo | Control URLs, image sources, and privacy |

**Profile enrichment does not mean writing data back to the OP or database by default.** If two-way sync is desired, design a separate workflow with conflict rules, auditing, edit permissions, and personal-data protection.

## 15. Important Security Considerations

### 15.1. Trust OIDC Data from the Right Source

- Take issuer/subject only from an ID Token verified against a trusted OP configuration.
- For UserInfo, ensure UserInfo's subject matches the ID Token's subject per OIDC; let the framework enforce the protocol.
- Never use unverified claim data from the frontend as an internal user lookup key.
- With multiple issuers, map by the <code>(iss, sub)</code> pair and enforce an allowed-issuers policy.

### 15.2. Service Authentication and Token Audience

- The Internal User Service must authenticate its callers (mTLS, service token, or equivalent).
- If using OAuth2 client credentials, the token must carry the audience and scopes intended for the internal API.
- Never forward the ID Token as a bearer token to internal APIs by default: the ID Token proves authentication to the Client, not access to a resource server.
- Never grab an access token meant for UserInfo or another API and misuse it against an internal API.
- Never expose service credentials to the browser, JSON responses, or logs.

### 15.3. Internal Permissions and Data

- Define a role allowlist, permission hierarchy, and authority-granting policy.
- Internal APIs must verify the caller is authorized to read only permitted data; never skip authorization just because it is "internal".
- Lookup requests by issuer/subject should have auditing and appropriate rate limits to curb enumeration.
- Never store entire personal profiles in the HTTP session merely for convenience.
- Never auto-link accounts based on email or phone number.

### 15.4. Data Minimization Principle

Internal profiles may contain PII or sensitive details. Request only fields needed for the use case. For instance, a welcome page may need only `displayName`, while permission checks need roles. Never log or return the entire profile object when only an <code>active</code> boolean is needed.

Users may visit <code>/me</code> to view permitted data, yet the API response should not return credentials, unnecessary raw permission lists, or infrastructure metadata. Apply access controls and retention per organizational data policy.

## 16. Error Handling and Common Symptoms

| Symptom | Possible Cause | Resolution |
|---|---|---|
| OP login succeeds yet app redirects to <code>/login?error</code> | Internal profile missing, locked, or internal API failed | Distinguish error codes in telemetry; check mapping/status and service health |
| <code>ClassCastException</code> casting principal to <code>EnrichedOidcUser</code> | Custom user service not wired into chain, or endpoint served an OAuth-only principal | Check <code>userInfoEndpoint().oidcUserService(...)</code> and matched chain |
| User gets the wrong internal record | Mapped by email or omitted issuer from key | Use <code>(iss, sub)</code> pair; check unique constraints/account linking |
| Locked user can still access | Session holds stale profile or status only checked at login | Revoke sessions and check status at protected actions |
| Role changed yet <code>hasRole</code> not updated | Authority snapshot in session | Refresh/invalidate session or check permissions directly |
| UserInfo lacks email claim | Scope not granted, OP withholds email, or UserInfo not called | Do not depend on email for identity lookup; inspect UserInfo flow |
| Internal API returns 401 | Service token invalid/expired or wrong audience | Check client credentials and internal resource server config |
| Internal API returns 403 | Service lacks permission to call lookup endpoint | Check service-to-service scopes/authorization |
| Internal API returns 404 | No external identity mapping | Provision or block login per policy |
| Internal API returns 502/503 | Network, DNS, gateway, or overloaded backend | Timeouts/circuit breaker, telemetry, and fail-closed policy |
| Slow login | Internal service calls too many APIs sequentially | Consolidate lookups, use sensible caching, limit payload |
| User from another tenant mapped to same account | Matched bare <code>sub</code> or skipped issuer verification | Verify issuer and tenant boundaries |
| Spring Session fails to serialize principal | Custom wrapper holds non-serializable objects or version mismatch | Keep snapshot DTO small, serializable, with compatibility strategy |
| Callback 404 / custom service never called | OAuth2 Login filter/chain did not receive callback | Check redirect URI, <code>securityMatcher</code>, and chain order |

### 16.1. Layered Diagnostic Flow

~~~text
Did the browser callback reach the application?
    |
    v
Did Spring Security select the right OAuth2 Login chain?
    |
    v
Were ID Token/nonce/state/issuer processed validly?
    |
    v
Did the default OidcUserService load the user successfully?
    |
    v
Was the custom OidcUserService invoked?
    |
    v
Was (iss, sub) mapped accurately?
    |
    v
Did the Internal Service return 200/404/401/403/5xx?
    |
    v
Are active/roles/profile valid per policy?
    |
    v
Were Principal + SecurityContext stored and used properly?
~~~

Do not blame everything on the OP or the internal service. If the callback never hits the right chain, the custom user service **never ran at all**. If the ID Token has the wrong issuer/audience, **never call the internal API with that identity**.

Logs should use registration ID, lookup outcome, HTTP status, internal correlation ID, and a bounded error code. Never log ID Tokens, access tokens, service tokens, authorization codes, PKCE verifiers, or full profile responses containing PII.

## 17. Practice Exercises

### Exercise 1 — Designing a Mapping Key

Two OPs return verified ID Tokens:

~~~text
Token A: iss=https://idp.example.org/tenant/a, sub=12345
Token B: iss=https://idp.example.org/tenant/b, sub=12345
~~~

**Question:** Should you use <code>sub=12345</code> alone to look up the internal user?

**Answer:** No. Use the <code>(iss, sub)</code> pair. Two different issuers do not automatically share the same identity namespace. A dedicated account-linking policy is required if business logic genuinely wants to merge them.

### Exercise 2 — Distinguishing Three Data Categories

An application needs to:

1. Confirm who the logged-in user is.
2. Know their display name, email, and locale.
3. Know whether they are allowed to approve invoices.

**Suggested answer:** (1) use verified ID Token/OIDC authentication; (2) use UserInfo and/or internal profile per source-of-truth policy; (3) use roles/entitlements from an authoritative internal service and enforce them on the backend. Never infer permissions from email or display name.

### Exercise 3 — Safe Role Mapping

Internal API returns:

~~~json
{
  "roles": ["EMPLOYEE", "BILLING_ADMIN", "SUPER_ROOT"]
}
~~~

The application only supports <code>EMPLOYEE</code>, <code>SUPPORT</code>, and <code>BILLING_ADMIN</code>.

**Question:** Which authorities should be created?

**Answer:** Only <code>ROLE_EMPLOYEE</code> and <code>ROLE_BILLING_ADMIN</code> (besides any original OIDC authorities policy decides to keep). Never auto-create <code>ROLE_SUPER_ROOT</code> if the application does not permit that role.

### Exercise 4 — Internal Service Failure

A user authenticated validly with OIDC, yet the internal API returns HTTP 503.

**Question:** Should you create a new profile with <code>active=true</code> and <code>roles=["EMPLOYEE"]</code> to avoid blocking the user?

**Answer:** No. HTTP 503 is a service failure, not proof of a new user or granted permissions. Under a policy requiring an internal profile, report incomplete login and log the infrastructure error safely; only allow a restricted mode if the architecture defines explicit rules and grants zero business permissions.

### Exercise 5 — Permission Revoked While Session Is Active

A user logged in and holds <code>ROLE_BILLING_ADMIN</code> on the principal. Later the internal service revokes the permission, while the user has not logged out.

**Question:** Why might method security still see the old permission?

**Answer:** Authentication's <code>GrantedAuthority</code> is typically a login-time snapshot. Without refreshing/revoking the session or checking entitlements at action time, the stale permission persists. Design refresh/invalidation or direct authorization checks for sensitive actions.

### Exercise 6 — Integrating in a Test Application

1. Create an OIDC ClientRegistration with the test OP's issuer, Client ID, and redirect URI.
2. Enable <code>oauth2Login()</code> and verify receiving <code>OidcUser</code> from the delegate.
3. Create a fake <code>InternalProfileGateway</code> for the test environment mapping by <code>(iss, sub)</code>.
4. Wire <code>EnrichingOidcUserService</code> into the <code>oidcUserService(...)</code> DSL.
5. Create <code>/me</code> returning only <code>internalUserId</code>, display name, and permitted fields.
6. Create an endpoint protected with <code>@PreAuthorize("hasRole('BILLING_ADMIN')")</code>.
7. Test cases: active user, locked user, missing mapping, internal service failure, different issuer with same subject, role outside allowlist.
8. Inspect post-login data and ensure no tokens/secrets are logged.

This exercise focuses on **how to design and write the integration**; test execution, evaluation, and content QA are performed in the project's separate testing phase.

## 18. Key Takeaways

- **Profile enrichment** is the step of augmenting business data from an internal user service after the OIDC identity has been verified by the OP and processed by Spring Security.
- The trusted mapping key is **<code>(iss, sub)</code>**, not email or bare <code>sub</code> when multiple issuers exist.
- In Spring Security Servlet OIDC Login, you can implement <code>OAuth2UserService&lt;OidcUserRequest, OidcUser&gt;</code> by **delegating to the default <code>OidcUserService</code>**, querying the internal API, and building a richer principal.
- Use <code>oauth2Login().userInfoEndpoint().oidcUserService(...)</code> to wire the custom service; do not confuse it with <code>userService(...)</code> for standard OAuth2 Login.
- Keep **ID Token/UserInfo claims** separate from **internal profiles and authorities**. Never mutate signed ID Token contents or turn arbitrary roles into permissions.
- Call the internal API with **service authentication dedicated to that API**, never blindly forwarding ID Tokens or UserInfo access tokens.
- Distinguish **missing user**, **locked user**, and **unavailable service**; fail closed for sensitive permissions.
- Profiles/roles in an HTTP session are normally a **snapshot**; adopt permission refresh/revocation policies commensurate with business risk.

### References

- **OpenID Connect Core 1.0:** ID Token, UserInfo Endpoint, subject identifier, and <code>sub</code> validation rules.
- **OpenID Connect Discovery 1.0:** OpenID Provider issuer and metadata.
- **Spring Security Reference — OAuth2 Login (Servlet):** customizing OIDC UserInfo, <code>OidcUserService</code>, and <code>userInfoEndpoint()</code>.
- **Spring Security Java API:** <code>OidcUserRequest</code>, <code>OidcUserService</code>, <code>OAuth2UserService</code>, <code>OidcUser</code>, <code>DefaultOidcUser</code>.
- **Spring Security Reference — Authorization / Method Security:** <code>GrantedAuthority</code>, <code>SimpleGrantedAuthority</code>, <code>hasRole</code>, and <code>@PreAuthorize</code>.
- **Spring Framework Reference — REST Clients:** <code>RestClient</code>, HTTP request/response, timeouts, and error handling.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** distinguishing Client, Authorization Server, Resource Server, access token, and client credentials.
