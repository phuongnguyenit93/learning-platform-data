# 13.2. OAuth2User, OidcUser, and Accessing Attributes or Claims

## 1. Context: Which Object Does Spring Security Provide After a User Logs In?

In a **Spring Security OAuth 2.0/OIDC Client** application, logging in through a provider such as Google, GitHub, or an enterprise SSO system is typically configured with `oauth2Login()`. Upon successful login, Spring Security creates an `Authentication` representing the current user. Inside the authentication sits the **principal**, an object holding the identity data processed by the login system.

Two key principal types:

- **`OAuth2User`:** represents a user logged in through OAuth2 Login. User data is usually fetched from a provider endpoint, such as a UserInfo endpoint or a proprietary API like GitHub's. The returned fields are called **attributes**; their structure can vary across providers.
- **`OidcUser`:** represents a user logged in via **OpenID Connect (OIDC)**, a standard layer extending OAuth 2.0 for identity authentication. In addition to attributes, this principal provides the **ID Token**, **OIDC claims**, and possibly **UserInfo**.

Because `OidcUser` **extends `OAuth2User`**, you can handle an `OidcUser` through the `OAuth2User` interface when you only need generic data. However, if you need `sub`, `iss`, the ID Token, and OIDC claims with standardized semantics, use the `OidcUser` API.

> **Key point:** `OAuth2User` and `OidcUser` are the **principal of the user logged into the application**; they are not synonymous with an access token, are not where you send a bearer token to call an API, and do not by themselves turn an application into a Resource Server.

### 1.1. Distinguishing Three Layers of Data That Appear After Login

| Data | Example | Meaning |
| --- | --- | --- |
| **Principal** | `OAuth2User` or `OidcUser` | Identity and attributes/claims that Spring Security places inside `Authentication` |
| **Authentication** | `OAuth2AuthenticationToken` | Holds the principal, authorities, and related OAuth2 client registration |
| **Authorized client** | `OAuth2AuthorizedClient` | Holds `ClientRegistration` and access token, plus refresh token if any |

A controller reading `OidcUser.getEmail()` **does not need** to read the access token. Conversely, for the backend to call another API on behalf of the user, the application needs to retrieve the **authorized client** and send the access token properly. Do not use the ID Token as a bearer token for APIs.

## 2. Path from the OIDC Provider to the Principal

For example, an employee logs into a portal through an OIDC Provider:

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Browser
    participant P as Spring Boot Portal
    participant I as OIDC Provider
    participant S as SecurityContext / Session

    U->>P: Open /oauth2/authorization/corporate
    P-->>U: Redirect authorization request
    U->>I: Login, MFA, consent (if needed)
    I-->>U: Authorization code callback
    U->>P: GET callback?code=...&state=...
    P->>I: Token Request
    I-->>P: ID Token + Access Token (+ other tokens if any)
    P->>P: Validate ID Token: signature, iss, aud, exp, nonce...
    opt UserInfo is used
        P->>I: GET UserInfo with access token
        I-->>P: UserInfo claims
    end
    P->>P: Create OidcUser and Authentication
    P->>S: Save SecurityContext per configuration
    P-->>U: Session cookie / application page
    U->>P: GET /me with session cookie
    P->>S: Load current Authentication
    S-->>P: Principal: OidcUser
    P-->>U: User information permitted for display
~~~

The flow above illustrates **OIDC Authorization Code** in a session-backed web application. For OAuth2 Login without OIDC, the principal may be an `OAuth2User` constructed from the provider's user API; there is no OIDC ID Token under the standard contract.

**Important:** Spring Security should only create a trusted OIDC principal after the appropriate authentication and token validation steps succeed. If you write custom code to Base64-decode a JWT payload and build a principal from unverified JSON without checking the signature, you bypass critical verification mechanisms.

## 3. Direct Comparison of `OAuth2User` and `OidcUser`

| Criterion | `OAuth2User` | `OidcUser` |
| --- | --- | --- |
| Purpose | User principal logged in via OAuth2 Login | User principal logged in via **OpenID Connect** |
| Type relationship | Base interface | **Extends `OAuth2User`** |
| User data | `getAttributes()`: provider-specific attribute map | `getAttributes()` and `getClaims()`: OIDC claim data |
| Principal name | `getName()` | `getName()`; can access `getSubject()` |
| Spring Security permissions | `getAuthorities()` | `getAuthorities()` |
| ID Token | Not guaranteed by interface | `getIdToken()` |
| Standard OIDC UserInfo | Not guaranteed | `getUserInfo()` if UserInfo data is present |
| Standard OIDC getters | Not built into the interface | `getEmail()`, `getFullName()`, `getSubject()`, etc. |
| User identifier | Provider-specific, depends on attribute name | `iss` + `sub` is the standard identifier pair for linking subjects |
| Common example | OAuth2 Login with GitHub provider | OIDC Login with Google or corporate OIDC Provider |
| Contains bearer token for calling APIs? | **No** | **No**; the ID Token in an OIDC principal serves a different purpose |

An `OidcUser` also has `getAttributes()` because it is an `OAuth2User`. However, prefer standard OIDC getters or reading claims from `getIdToken()`/`getUserInfo()` when business logic needs clarity on each claim's **origin** and **meaning**.

### 3.1. `OAuth2User` Does Not Automatically Normalize Every Attribute

For example, provider A returns:

~~~json
{
  "id": 4172,
  "login": "linhdev",
  "name": "Linh Nguyen",
  "avatar_url": "https://example.test/avatar/4172"
}
~~~

Provider B returns:

~~~json
{
  "user_id": "u-9001",
  "display_name": "Linh N.",
  "email_address": "linh@example.test"
}
~~~

These two payloads are merely illustrative provider attributes. Spring Security can place them into `OAuth2User.getAttributes()`, but **no universal OAuth 2.0 specification forces every provider to place the user ID in `id`, `user_id`, or `sub`**.

Therefore, you must use `ClientRegistration`/`registrationId` and **each provider's API contract** to know which attribute is the stable identifier. Never assume `getAttribute("email")` always has a value.

### 3.2. OIDC Standardizes Many Claims, but Some Fields Remain Optional

OIDC Core defines claims such as:

- `sub`: subject identifier at the issuer.
- `iss`: issuer that issued the ID Token.
- `aud`: audience the token was issued for, usually containing the client ID.
- `exp`, `iat`: expiration and issued-at timestamps.
- `nonce`: value binding the authentication request, if used.
- `name`, `given_name`, `family_name`, `preferred_username`: profile data depending on capability/scopes.
- `email`, `email_verified`: email address and verification status, when released by the provider.

Profile claims **do not necessarily appear** merely because the application requested `profile` or `email` scopes. Consent policies, provider capabilities, claim release settings, and account data all affect the result.

## 4. Key Interfaces and Classes to Know

In Spring Security:

~~~java
// Generic OAuth2 Login principal
org.springframework.security.oauth2.core.user.OAuth2User

// OIDC principal
org.springframework.security.oauth2.core.oidc.user.OidcUser

// ID Token and UserInfo objects
org.springframework.security.oauth2.core.oidc.OidcIdToken
org.springframework.security.oauth2.core.oidc.OidcUserInfo

// Authentication after OAuth2 Login
org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken
~~~

Important methods:

~~~java
// OAuth2User
Map<String, Object> attributes = oauth2User.getAttributes();
Collection<? extends GrantedAuthority> authorities = oauth2User.getAuthorities();
String name = oauth2User.getName();
Object rawEmail = oauth2User.getAttributes().get("email");

// OidcUser
OidcIdToken idToken = oidcUser.getIdToken();
OidcUserInfo userInfo = oidcUser.getUserInfo();  // may be null
Map<String, Object> claims = oidcUser.getClaims();
String subject = oidcUser.getSubject();
String email = oidcUser.getEmail();              // may be null
~~~

The snippet illustrates `oauth2User` and `oidcUser` variables already obtained from a valid `Authentication`. With `OidcUser`, data is exposed through claim accessor APIs, reducing code coupling to raw key names for standard claims.

### 4.1. Default Implementations

- **`DefaultOAuth2User`:** implements `OAuth2User` with an attributes map, authorities, and the key used as the principal name.
- **`DefaultOidcUser`:** implements `OidcUser` with ID Token, UserInfo (when present), authorities, and principal name resolution.
- **`OAuth2UserAuthority`:** authority representing user attributes loaded via OAuth2 UserInfo/provider API.
- **`OidcUserAuthority`:** authority holding ID Token and UserInfo data to support authority mapping in the login flow.

These classes sit beneath Spring Security's configuration. In business code, prefer depending on the `OAuth2User`/`OidcUser` interfaces rather than casting to concrete implementations unless necessary.

## 5. Accessing `OAuth2User` in Spring MVC/Servlet

Suppose a web app uses OAuth2 Login with GitHub. After a successful login, a controller can receive the principal via annotation:

~~~java
@RestController
class ProfileController {

    @GetMapping("/api/me/oauth2")
    Map<String, Object> currentOAuth2User(
            @AuthenticationPrincipal OAuth2User user) {

        if (user == null) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }

        Map<String, Object> attributes = user.getAttributes();

        Object rawLogin = attributes.get("login");
        String login = rawLogin instanceof String value ? value : "";

        Object rawName = attributes.get("name");
        String displayName = rawName instanceof String value ? value : "";

        return Map.of(
            "principalName", user.getName(),
            "login", login,
            "displayName", displayName
        );
    }
}
~~~

Types are imported correspondingly from Spring Web, Spring Security, and Java. The example assumes the provider returns attributes with keys `login` and `name`, as in some GitHub configurations. For other providers, replace the keys according to the actual data contract.

**Why use `instanceof String`?** `getAttributes()` returns `Map<String, Object>`; values can be String, Number, Boolean, List, or Map. Casting `(String) attributes.get("id")` directly can cause `ClassCastException` if the provider returns IDs as numbers.

### 5.1. Reading Attributes Directly

`OAuth2User` supports key-based access:

~~~java
String displayName = user.getAttribute("name");
Object externalId = user.getAttribute("id");
~~~

`getAttribute(...)` is convenient when the exact data type is already known. In code requiring stability across multiple providers, you can read from the map and perform explicit type checks before mapping to a domain model.

If attributes have nested structures:

~~~json
{
  "profile": {
    "displayName": "Linh",
    "locale": "vi"
  }
}
~~~

access the nested structure properly or build a provider-specific adapter/DTO. Do not assume all claims are flat or Strings.

### 5.2. Reading the Principal via `Authentication`

A Servlet controller can also accept `Authentication`:

~~~java
@GetMapping("/api/me/authentication")
Map<String, Object> authenticationDetails(Authentication authentication) {

    Object principal = authentication.getPrincipal();

    if (!(principal instanceof OAuth2User oauth2User)) {
        throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
    }

    String registrationId = "unknown";
    if (authentication instanceof OAuth2AuthenticationToken oauth2) {
        registrationId = oauth2.getAuthorizedClientRegistrationId();
    }

    return Map.of(
        "registrationId", registrationId,
        "principalName", oauth2User.getName(),
        "attributeKeys", oauth2User.getAttributes().keySet()
    );
}
~~~

`OAuth2AuthenticationToken.getAuthorizedClientRegistrationId()` tells you which registration the user logged in with, such as `github`, `google`, or `corporate`. That value is useful when the application supports multiple providers and each provider identifies users differently.

**Do not use the registration ID as the user's ID:** `corporate` is an OAuth2 Client configuration key, and many users can log in through that same registration.

### 5.3. Using `SecurityContextHolder` in the Servlet Service Layer

In synchronous code, you can read the current authentication:

~~~java
@Service
class CurrentUserService {

    OAuth2User currentUser() {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null
                || !(authentication.getPrincipal() instanceof OAuth2User user)) {
            throw new IllegalStateException(
                "Current principal is not an OAuth2 user");
        }

        return user;
    }
}
~~~

A service layer should only use this pattern when it genuinely needs to couple to the request's security context. In decoupled architectures, passing a verified **internal account ID** into business services generally makes code easier to test and avoids framework coupling.

**Note on threads:** `SecurityContextHolder` in Servlet usually binds context to a thread according to the configured strategy. When handing off to asynchronous executors or other threads, never assume the context propagates automatically to every thread. Use a propagation mechanism supported by Spring Security or pass the minimal required data safely.

## 6. Accessing `OidcUser` and Standard Claims

Suppose an application uses an OIDC Provider with scope `openid profile email`. An illustrative ID Token:

~~~json
{
  "iss": "https://idp.example.com/realms/staff",
  "sub": "47db8e71-2f39-4a84-8112-6326290ad7f2",
  "aud": "employee-portal",
  "exp": 1920000300,
  "iat": 1920000000,
  "name": "Linh Nguyen",
  "preferred_username": "linh.nguyen",
  "email": "linh@example.test",
  "email_verified": true
}
~~~

The payload above only illustrates claims; it is not a complete, signed, or time-valid ID Token for actual use.

Once Spring Security verifies the ID Token and creates `OidcUser`, a controller can do:

~~~java
@RestController
class OidcProfileController {

    @GetMapping("/api/me/oidc")
    Map<String, Object> currentOidcUser(
            @AuthenticationPrincipal OidcUser user) {

        if (user == null) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }

        String email = user.getEmail();
        String fullName = user.getFullName();

        return Map.of(
            "subject", user.getSubject(),
            "name", fullName == null ? "" : fullName,
            "email", email == null ? "" : email,
            "emailVerified", Boolean.TRUE.equals(user.getEmailVerified())
        );
    }
}
~~~

The example uses standard OIDC getters. `getEmail()` and `getFullName()` can return `null` when the provider does not release those claims. Because `Map.of(...)` rejects null values, the code converts optional fields to empty strings before building the map.

**Business caveat:** `emailVerified=false` in the snippet above is also produced when the `email_verified` claim is **absent**. If you need to distinguish three states ("verified / unverified / not disclosed by provider"), keep a nullable `Boolean` or a separate status field instead of coercing `null` to `false`.

### 6.1. Standard Getters and the Claims Map

An `OidcUser` is commonly used in two ways:

~~~java
String subject = user.getSubject();
String preferredUsername = user.getPreferredUsername();
String email = user.getEmail();

Object department = user.getClaims().get("department");
Object assurance = user.getClaims().get("acr");
~~~

Getters like `getSubject()`, `getPreferredUsername()`, and `getEmail()` keep code readable for standard claims. For **custom claims** such as `department`, `tenant_id`, or `roles`, use the map and handle data types according to your IdP configuration.

Example of a list-shaped custom claim:

~~~json
{
  "department": "engineering",
  "roles": ["viewer", "editor"],
  "tenant_id": "tenant-a"
}
~~~

Safe way to read it:

~~~java
Object rawRoles = user.getClaims().get("roles");

List<String> roles = rawRoles instanceof List<?> list
    ? list.stream()
          .filter(String.class::isInstance)
          .map(String.class::cast)
          .toList()
    : List.of();
~~~

**Do not automatically treat `roles` as Spring Security authorities**. It is merely a claim the provider might issue. To use it in `hasRole(...)` or `@PreAuthorize(...)`, the application must **map it to `GrantedAuthority`** according to the system's trust policy.

### 6.2. Distinguishing `getClaims()`, `getAttributes()`, ID Token, and UserInfo

An `OidcUser` provides several views of the data:

~~~java
Map<String, Object> attributes = user.getAttributes();
Map<String, Object> principalClaims = user.getClaims();

OidcIdToken idToken = user.getIdToken();
Map<String, Object> idTokenClaims = idToken.getClaims();

OidcUserInfo userInfo = user.getUserInfo();
Map<String, Object> userInfoClaims =
    userInfo == null ? Map.of() : userInfo.getClaims();
~~~

Meaning:

- `getIdToken().getClaims()`: claims present in the **validated ID Token** from the OIDC flow.
- `getUserInfo().getClaims()`: claims from the **UserInfo Endpoint** if Spring Security called it and the provider returned matching data. `getUserInfo()` may be `null`.
- `getClaims()`/`getAttributes()` on the principal: the OIDC data view exposed by the implementation to the application; it may combine data from the ID Token and UserInfo as Spring Security builds the principal.

When business logic needs to know whether a claim **came from the ID Token or UserInfo**, read directly from `idTokenClaims` or `userInfoClaims`. Do not assume every provider returns the same fields in both places or treat their merge order as a business contract.

**UserInfo is not always called.** Some providers deliver all needed claims in the ID Token; some applications lack an appropriate access token or do not configure/use UserInfo. The absence of UserInfo does not mean the ID Token is invalid.

### 6.3. Why Must UserInfo Data Be Bound to the Right Subject?

UserInfo is an additional source of user attributes. That data must belong to **the exact user authenticated in the ID Token**, specifically the `sub` subject. Spring Security / the OIDC client must enforce the protocol binding before treating UserInfo as belonging to the same subject.

If you fetch UserInfo manually outside the framework, preserve subject, token, and provider binding; never call an arbitrary URL and let the returned JSON overwrite the authenticated identity.

## 7. `getName()`, `sub`, Email, and Durable Identifiers

This is the most critical section when mapping external logins to internal accounts.

### 7.1. `getName()` Is Not Always a Human-Readable Username

`OAuth2User.getName()` is the identifier name chosen by the principal implementation/configuration. For some providers it may come from `id`; for others from `login` or `sub` depending on configuration.

In OIDC, `OidcUser.getName()` usually relies on `sub` by default, though an application can configure a different **name attribute key**. Therefore, **never write domain logic assuming `getName()` is always an email or display-friendly value**.

Example:

~~~text
OAuth2User:
    getName()             = "4172"
    attributes["login"]    = "linhdev"

OidcUser:
    getName()             = "47db8e71-2f39-4a84-8112-6326290ad7f2"
    getSubject()          = "47db8e71-2f39-4a84-8112-6326290ad7f2"
    getFullName()         = "Linh Nguyen"
    getPreferredUsername()= "linh.nguyen"
~~~

Use `getFullName()` or a controlled display name for UI presentation. For account linking, use a **stable subject identifier** per the provider's contract.

### 7.2. For OIDC, Use the Issuer + Subject Pair

OIDC identifies a user by the `sub` claim **scoped to the issuer `iss`**. Two different providers can issue the same `sub` value for different people. Furthermore, a provider may implement **pairwise subject identifiers**, issuing different `sub` values to different clients/sectors.

Therefore, the safe logical pair for keying an internal account link table is:

~~~text
(issuer, subject)  →  internalUserId

("https://idp.example.com/realms/staff",
 "47db8e71-2f39-4a84-8112-6326290ad7f2")
    →  92041
~~~

Java example:

~~~java
record ExternalIdentity(String issuer, String subject) {}

ExternalIdentity externalIdentity(OidcUser user) {
    Object rawIssuer = user.getIdToken().getClaims().get("iss");

    if (!(rawIssuer instanceof String issuer)
            || issuer.isBlank()
            || user.getSubject() == null
            || user.getSubject().isBlank()) {
        throw new IllegalStateException("OIDC identity is incomplete");
    }

    return new ExternalIdentity(issuer, user.getSubject());
}
~~~

This code only constructs the linking key; it does not replace Spring Security's ID Token verification. Do not use it to accept a client-sent JWT whose signature and claims have not been verified.

In multi-tenant applications, you may also need to bind **tenant or ClientRegistration** according to internal linking policies, especially when a provider issues pairwise subjects or multiple tenants use different IdP configurations.

### 7.3. Email Is Not an Immutable Identifier

An email can be renamed, revoked and reassigned, left unverified by the provider, omitted, or duplicated across multiple identity sources.

Therefore:

- **Do not use `email` as the default primary key** to link an OIDC principal to an internal account.
- If using email for features requiring a verified address, check `email_verified` (if supplied by the provider), trustworthiness, and provider policy.
- Never automatically merge two accounts just because they share the same email without a secure account-linking workflow.
- If updating the internal account's email, check update permissions independently of a token merely containing a new claim.

For **non-OIDC** OAuth2 Login, the application should choose a stable provider-specific ID combined with the registration/provider identifier, such as `(registrationId, providerUserId)`, and understand the provider's lifecycle policy for that ID.

### 7.4. Separating Display Name and Identity

A simple domain model:

~~~java
record CurrentUserProfile(
    String internalUserId,
    String displayName,
    String email
) {}
~~~

A service maps `ExternalIdentity` to `internalUserId` and fetches the profile from the internal database. The UI displays `displayName` and policy-approved `email`, while authorization relies on the **internal account ID and system-granted permissions**.

Never use `name` or `preferred_username` directly in sensitive authorization checks, such as "anyone with name == admin is an admin".

## 8. Spring Boot: Coexistence of OAuth2 Login and OIDC Login

### 8.1. Common Dependencies

In a Spring MVC/Servlet application:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

### 8.2. Registering an OAuth2 Provider and an OIDC Provider

Example `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          github:
            client-id: ${GITHUB_CLIENT_ID}
            client-secret: ${GITHUB_CLIENT_SECRET}
            scope:
              - read:user
              - user:email

          corporate:
            provider: company-oidc
            client-id: ${CORPORATE_CLIENT_ID}
            client-secret: ${CORPORATE_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email

        provider:
          company-oidc:
            issuer-uri: https://idp.example.com/realms/staff
~~~

When running the application:

- `/oauth2/authorization/github` initiates login via GitHub with provider-specific attribute payloads.
- `/oauth2/authorization/corporate` initiates OIDC login via the enterprise provider, requesting the `openid` scope and producing an OIDC principal if the flow succeeds.
- Spring Security OAuth2 Login's default callback is typically `/login/oauth2/code/{registrationId}`; register the matching redirect URI with each provider.
- Client secrets are loaded from environment configuration or a secret manager; never commit real values to Git.

Example `SecurityFilterChain`:

~~~java
@Configuration
class LoginSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/css/**", "/js/**").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
~~~

The same `oauth2Login()` configuration can support both OAuth2 Login and OIDC Login depending on the registration/provider. **The final principal type depends on the protocol and provider data**, not just the `/login` endpoint name.

## 9. One Controller Handling Both `OAuth2User` and `OidcUser`

When an application supports multiple providers, you can use `OAuth2User` as the common type and then branch for OIDC:

~~~java
@RestController
class UnifiedProfileController {

    @GetMapping("/api/me")
    Map<String, Object> me(Authentication authentication) {

        if (authentication == null
                || !(authentication.getPrincipal() instanceof OAuth2User user)) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }

        String registrationId = authentication instanceof OAuth2AuthenticationToken token
            ? token.getAuthorizedClientRegistrationId()
            : "unknown";

        if (user instanceof OidcUser oidc) {
            String subject = oidc.getSubject();
            String email = oidc.getEmail();

            return Map.of(
                "kind", "oidc",
                "registrationId", registrationId,
                "subject", subject,
                "email", email == null ? "" : email
            );
        }

        Object rawProviderId = user.getAttributes().get("id");

        return Map.of(
            "kind", "oauth2",
            "registrationId", registrationId,
            "providerId", rawProviderId == null ? "" : rawProviderId.toString(),
            "principalName", user.getName()
        );
    }
}
~~~

This is an example of **principal type branching**, not a complete adapter for every OAuth2 provider. GitHub may provide `id`; another provider might lack that field. In production code, build an **adapter keyed by `registrationId`** and map to a consistent internal identifier.

### 9.1. When to Use `instanceof OidcUser`?

Useful when:

- An application accepts both GitHub OAuth2 Login and corporate OIDC Login.
- One endpoint returns a shared UI profile while adding standard OIDC info when available.
- The business layer handles issuer + subject separately for OIDC and provider-specific user IDs for non-OIDC sources.
- You need to access the ID Token or UserInfo to inspect a claim absent from the generic principal.

If an endpoint **only serves OIDC**, injecting `@AuthenticationPrincipal OidcUser user` directly is usually cleaner.

### 9.2. Avoid Unchecked Casts

Do not write:

~~~java
OidcUser user = (OidcUser) authentication.getPrincipal();
~~~

if the same application supports both OAuth2 and OIDC providers. A principal of type `DefaultOAuth2User` cannot be cast to `OidcUser`.

Use:

~~~java
Object principal = authentication.getPrincipal();

if (principal instanceof OidcUser oidcUser) {
    // Handle OIDC claims only here.
}
~~~

Or enforce an OIDC-only endpoint via clear configuration/contracts to prevent type errors when login providers change.

## 10. Accessing the Principal with `@AuthenticationPrincipal`

The annotation `org.springframework.security.core.annotation.AuthenticationPrincipal` lets Spring inject the authenticated principal into a handler:

~~~java
@GetMapping("/me/name")
String currentName(@AuthenticationPrincipal OAuth2User user) {
    return user.getName();
}
~~~

In an application using OIDC:

~~~java
@GetMapping("/me/subject")
String currentSubject(@AuthenticationPrincipal OidcUser user) {
    return user.getSubject();
}
~~~

Note:

- The annotation extracts the principal from the security context; **it does not trigger an OAuth2 authorization flow by itself**.
- If the user is not logged in or the principal is of the wrong type, the parameter may be `null` depending on how the argument resolver runs, so the endpoint must be protected and/or check explicitly.
- `@AuthenticationPrincipal(errorOnInvalidType = true)` can help surface errors when the principal does not match the expected type, though you should still design the endpoint around permitted authentication types.
- Avoid pulling sensitive fields from the principal and returning them verbatim from a public API.

### 10.1. Using SpEL to Extract an Attribute

Spring Security supports expressions on `@AuthenticationPrincipal`:

~~~java
@GetMapping("/me/email")
String email(
        @AuthenticationPrincipal(expression = "attributes['email']")
        String email) {

    return email == null ? "" : email;
}
~~~

This expression reads the `email` key from `getAttributes()` on the current principal. It is convenient for very simple handlers but has drawbacks:

- The field may be missing or not a String.
- Providers can change schemas while expressions remain scattered as strings across controllers.
- If you need to distinguish whether a claim came from the ID Token or UserInfo, access `OidcUser` explicitly.
- If the value affects security logic, route it through an identity adapter/domain service rather than handling everything inside an annotation expression.

### 10.2. Java `Principal` Is Not `OAuth2User`

A method can accept `java.security.Principal` or `Authentication`. `Principal.getName()` only supplies a name. `Authentication` also lets you inspect `getAuthorities()`, `getPrincipal()`, and the current authentication type.

To read specialized claims, retrieve the principal with the proper type or use `@AuthenticationPrincipal`. Never cast `Principal` directly to `OidcUser` without knowing what object it actually is.

## 11. Accessing the Principal in Spring WebFlux

WebFlux stores the security context in the **reactive context**. The `OAuth2User`/`OidcUser` concepts remain the same, but reading authentication in asynchronous code must fit Reactor.

### 11.1. Reactive OAuth2 Login Configuration

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

~~~java
@Configuration
@EnableWebFluxSecurity
class WebFluxLoginSecurity {

    @Bean
    SecurityWebFilterChain webSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/", "/assets/**").permitAll()
                .anyExchange().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

### 11.2. Using `@AuthenticationPrincipal` in a WebFlux Handler

~~~java
@RestController
class ReactiveProfileController {

    @GetMapping("/api/me/oidc")
    Mono<Map<String, String>> me(@AuthenticationPrincipal OidcUser user) {

        if (user == null) {
            return Mono.error(
                new ResponseStatusException(HttpStatus.UNAUTHORIZED));
        }

        return Mono.just(Map.of(
            "subject", user.getSubject(),
            "email", user.getEmail() == null ? "" : user.getEmail()
        ));
    }
}
~~~

The annotation extracts the principal as WebFlux processes the authenticated request. Because reading a few claims from an existing object is lightweight, the example uses `Mono.just(...)` without performing I/O.

If you need to query a database or external API to resolve an internal account, use a **reactive repository/WebClient** and compose with `flatMap`/`map`, avoiding `.block()` on the event loop.

### 11.3. Using `ReactiveSecurityContextHolder` in a Reactive Service

If you need to access the context inside a reactive pipeline:

~~~java
@Service
class ReactiveCurrentUserService {

    Mono<String> currentOidcSubject() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getPrincipal)
            .ofType(OidcUser.class)
            .map(OidcUser::getSubject);
    }
}
~~~

If there is no valid OIDC authentication, the pipeline may complete empty. The HTTP layer or business service must decide to return `401`, use another identity flow, or respond appropriately.

**Never call `SecurityContextHolder.getContext()` in WebFlux assuming the reactive request's principal is always in the current `ThreadLocal`.** Reactor switches threads and uses its own Context; use `ReactiveSecurityContextHolder` or WebFlux parameter injection.

## 12. Attributes, Claims, and Data Models: Type-Safe Handling

Providers can return JSON with diverse data types:

~~~json
{
  "sub": "u-123",
  "email": "linh@example.test",
  "email_verified": true,
  "age": 27,
  "roles": ["viewer", "editor"],
  "address": {
    "country": "VN"
  }
}
~~~

After parsing, `getAttributes()`/`getClaims()` may contain:

- `String` for subject/email.
- `Boolean` for `email_verified`.
- `Number` for numeric fields.
- `Collection` for lists.
- `Map` for nested objects.

Certain standard claims have accessor APIs converted/normalized by Spring Security. For custom claims, **do not assume everything is always a String**.

Example helper for reading a string:

~~~java
static Optional<String> stringClaim(
        Map<String, Object> claims, String name) {

    Object value = claims.get(name);
    return value instanceof String text && !text.isBlank()
        ? Optional.of(text)
        : Optional.empty();
}
~~~

Example helper for reading a list of strings:

~~~java
static List<String> stringListClaim(
        Map<String, Object> claims, String name) {

    Object value = claims.get(name);

    if (!(value instanceof Collection<?> values)) {
        return List.of();
    }

    return values.stream()
        .filter(String.class::isInstance)
        .map(String.class::cast)
        .toList();
}
~~~

These helpers demonstrate flexible data extraction, **not that every mistyped claim should be silently ignored**. When a claim is required for a security decision, missing or mistyped data must fail safely or be handled by an explicit policy.

### 12.1. Normalizing Data at the System Boundary

Instead of letting every controller read GitHub, Google, or corporate IdP keys directly, define an internal model:

~~~java
record LoginIdentity(
    String provider,
    String issuer,
    String externalSubject,
    String displayName,
    String email,
    boolean emailVerified
) {}
~~~

Then implement an adapter per registration:

~~~text
OAuth2User (GitHub attributes)
          \
           --> Provider identity adapter --> LoginIdentity
          /
OidcUser (OIDC claims)
~~~

The adapter is responsible for:

1. Identifying the provider via the configured `registrationId`/issuer.
2. Selecting the right field as the external user ID.
3. Validating required claims and data types.
4. Applying email verification / account linking policies.
5. Mapping to an internal account.
6. Exposing only the fields needed by the UI and business services.

Normalizing at the boundary avoids duplicating provider-specific logic across controllers and reduces errors when changing providers.

## 13. Principal and Authorization: Do Attributes/Claims Automatically Become Roles?

**No.** `OAuth2User.getAuthorities()` and `OidcUser.getAuthorities()` return the **`GrantedAuthority` objects that Spring Security attached to `Authentication`**. They do not necessarily match a `roles` field inside claims.

After OAuth2 Login, Spring Security typically includes authorities representing the user profile, such as `OAuth2UserAuthority` or `OidcUserAuthority`; depending on grants/scopes/configuration, `SCOPE_...` authorities may also be present. Yet an endpoint requiring:

~~~java
@PreAuthorize("hasRole('ADMIN')")
public void deleteReport(Long id) {
    // ...
}
~~~

only works when authentication contains the corresponding authority such as `ROLE_ADMIN` by convention, and when **method security** is enabled. `email`, `preferred_username`, or an arbitrary `roles` claim **does not automatically** become `ROLE_ADMIN`.

### 13.1. Inspecting Current Authorities

~~~java
@GetMapping("/api/me/authorities")
List<String> authorities(Authentication authentication) {

    return authentication.getAuthorities().stream()
        .map(GrantedAuthority::getAuthority)
        .toList();
}
~~~

This endpoint should only serve purposes aligned with access rights; **do not return all sensitive claims/attributes** just for debugging. Permissions granted to an internal account may come from a database or enterprise policy and not appear in provider claims at all.

### 13.2. Mapping Authorities from Provider Claims When Permitted

Spring Security supports `GrantedAuthoritiesMapper` during OAuth2 Login to translate principal authorities into application authorities. Suppose a **system-trusted** OIDC Provider's ID Token contains a custom `roles` claim:

~~~java
@Configuration
class OAuth2AuthorityMapping {

    @Bean
    GrantedAuthoritiesMapper userAuthoritiesMapper() {
        return existingAuthorities -> {
            Set<GrantedAuthority> mapped =
                new HashSet<>(existingAuthorities);

            for (GrantedAuthority authority : existingAuthorities) {
                if (authority instanceof OidcUserAuthority oidcAuthority) {
                    Object rawRoles =
                        oidcAuthority.getIdToken().getClaims().get("roles");

                    if (rawRoles instanceof Collection<?> roles
                            && roles.contains("report-reader")) {
                        mapped.add(new SimpleGrantedAuthority(
                            "ROLE_REPORT_READER"));
                    }
                }
            }

            return mapped;
        };
    }
}
~~~

This example assumes the provider issues a `roles` claim in the **ID Token**, and the `report-reader` value is controlled by the organization. The referenced classes include `GrantedAuthoritiesMapper`, `GrantedAuthority`, `SimpleGrantedAuthority`, and `OidcUserAuthority` from Spring Security. `import` statements are omitted.

**Important limitations:**

- `roles` **is not a mandatory standard claim** in ID Tokens. A provider might place it in UserInfo or another custom claim; verify the actual schema.
- Never use `email` or display name to infer admin privileges.
- Only trust claims issued by the **right issuer**, intended for the right client, and verified through validation.
- Critical business permissions may require querying an internal database to enforce immediate revocation rather than relying solely on claims inside an ID Token.
- If authorities are updated during a login session, **cached permissions may become stale** until the authentication/session is refreshed. Ensure an appropriate synchronization or reauthorization policy.
- If using `@PreAuthorize`, enable method security, such as `@EnableMethodSecurity` in a Servlet application.

### 13.3. Distinguishing Scope and Role

| Concept | Meaning | Example |
| --- | --- | --- |
| **OAuth2 scope** | Permission range a client requests/receives for APIs or data | `profile`, `email`, `reports.read` |
| **OIDC claim** | Information about the user/authentication in ID Token/UserInfo | `sub`, `email_verified`, `department` |
| **Spring Security authority** | Authority evaluated by the application's authorization engine | `ROLE_ADMIN`, `SCOPE_reports.read` |
| **Domain role** | Business permission managed by the internal system | `report_manager`, `billing_approver` |

These layers may be mapped to one another by policy, but **must never be treated as equivalent by default**. An `openid` scope does not grant application admin rights; a verified email does not grant access to confidential records.

## 14. When to Read ID Token, When to Read UserInfo, and When to Call Another API?

An `OidcUser` may already provide the claims needed to display login details. If you need data outside the OIDC profile scope (such as order counts or work schedules), you may need to call another **Resource Server** with a suitable access token.

| Need | Appropriate Source | Notes |
| --- | --- | --- |
| Identify the logged-in subject | OIDC `iss` + `sub` from verified ID Token | Stable identifier per issuer |
| Display user name/email | `OidcUser` claims or UserInfo when available | May be absent; follow privacy policy |
| Read non-OIDC OAuth2 provider account ID | `OAuth2User` attributes per provider | Provider-specific mapping |
| Fetch the user's project list | Business API / Resource Server | Use access token with proper audience/scopes |
| Retrieve internal application permissions | Domain authorization service/database or policy mapping | Do not rely on arbitrary email/claims by default |
| Verify a token calling your own REST API | OAuth2 Resource Server | Different from reading an OIDC principal in web login |

When the backend needs to call an API on behalf of the user, obtain `OAuth2AuthorizedClient` via Spring Security OAuth2 Client components. **Do not send `OidcUser.getIdToken().getTokenValue()` as an access token** to an API; the ID Token's audience is the client, and it serves client-side identity authentication.

### 14.1. Why Not Return Raw `getAttributes()` from a REST API?

Some providers include attributes not meant for public UI exposure: internal IDs, groups, flags, phone numbers, identity metadata, locale, or account settings. Returning the raw map:

~~~java
return user.getAttributes();
~~~

can leak data the frontend does not need. It is better to return a **whitelisted DTO/record** containing `displayName`, `avatarUrl`, or only fields the application is permitted to display.

Likewise, do not log or serialize full ID Token and UserInfo claims indiscriminately. For auditing, select specific fields, apply retention policies, and restrict access.

## 15. Customizing the Principal: Username Attribute, User Service, and Role Mapping

### 15.1. `user-name-attribute` for Non-OIDC OAuth2 Providers

A provider may return the user ID under `id` or `user_id`. In provider configuration, Spring Boot/Spring Security lets you declare which key serves as the principal name in that case, for example:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          partner:
            provider: partner-auth
            client-id: ${PARTNER_CLIENT_ID}
            client-secret: ${PARTNER_CLIENT_SECRET}
            scope: profile.read
        provider:
          partner-auth:
            authorization-uri: https://auth.partner.example/authorize
            token-uri: https://auth.partner.example/token
            user-info-uri: https://api.partner.example/me
            user-name-attribute: account_id
~~~

The configuration above illustrates an OAuth2 provider whose API returns `account_id`. Endpoints and scopes must be replaced with the provider's actual contract. `user-name-attribute` tells Spring what value `getName()` returns; **it does not turn `account_id` into an OIDC subject** or guarantee the claim is always present.

### 15.2. Customizing `OAuth2UserService`

If a provider requires special processing when loading attributes, Spring Security offers an extension point:

~~~java
OAuth2UserService<OAuth2UserRequest, OAuth2User>
~~~

In a Servlet application, you can plug a custom user service into:

~~~java
http.oauth2Login(oauth2 -> oauth2
    .userInfoEndpoint(userInfo -> userInfo
        .userService(customOAuth2UserService)
    )
);
~~~

This example assumes `customOAuth2UserService` is an existing bean. The user service should delegate to the standard implementation or process responses per the provider's contract, preserving token bindings and never trusting unverified data sources.

For OIDC there are dedicated interfaces and implementations, such as `OAuth2UserService<OidcUserRequest, OidcUser>` and `OidcUserService`, configured via `oidcUserService(...)` in corresponding Spring Security versions:

~~~java
http.oauth2Login(oauth2 -> oauth2
    .userInfoEndpoint(userInfo -> userInfo
        .oidcUserService(customOidcUserService)
    )
);
~~~

When customizing, be careful:

- Never bypass ID Token validation, nonce checks, or UserInfo subject binding.
- Keep username/subject policies consistent.
- Do not change the principal name to email purely for UI convenience if the system uses that name as an identity key.
- Separate domain user mapping logic from unnecessary external I/O requests.
- Handle IdP/UserInfo failures properly rather than accepting untrusted data.

### 15.3. `DefaultOidcUser` and Principal Name Options

`DefaultOidcUser` provides constructors letting you specify which key acts as the principal name when needed. If you change the default name attribute to `preferred_username` or another field, make sure the field actually exists and understand the impact on account linkage, session mapping, and auditing.

A safe approach in many applications is to **keep `sub` as the stable domain identifier** while having a separate `displayName` for display. Do not alter the principal name merely because an OIDC ID looks unreadable.

## 16. Principal in Session and Mutable Data

In a session-based web app using OAuth2 Login:

1. Spring Security authenticates the user and creates an `Authentication` containing the principal.
2. The application stores the context according to its session policy.
3. Subsequent requests may read the **stored principal**, even if the user's profile was just edited at the IdP.

This affects:

- **Name/email:** changing an email at the IdP does not guarantee `OidcUser.getEmail()` in the current session updates immediately.
- **Groups/roles:** revoking a user's privilege at the IdP does not guarantee authorities cached in the session change immediately.
- **Avatar/display name:** a profile refresh or re-login mechanism may be needed depending on requirements.
- **Account disabled:** if the system must disable an account immediately, enforce internal policies, session invalidation, or appropriate revalidation.

**Never treat a claim captured at login time as immutable evidence** for sensitive decisions later on. Consider querying internal permissions at request time when rapid revocation is required.

### 16.1. Users Logging In Across Multiple Providers

One person may link both a corporate OIDC account and a GitHub OAuth2 account to the same internal user. This requires an account-linking workflow:

~~~text
corporate (issuer + sub) ─┐
                          ├── internalUserId = 92041
github (provider + id) ───┘
~~~

Never merge two external identities automatically just because they display the same email. GitHub/OIDC accounts must be **verified** and linked through an authorized workflow. Each identity provider has its own ID rules and may differ in trust level.

## 17. Common Errors and Diagnostics

| Symptom | Common Cause | What to Check |
| --- | --- | --- |
| `@AuthenticationPrincipal OidcUser` is `null` | Unauthenticated user, non-OIDC OAuth2 login, or different authentication type | Check security chain, provider, `openid` scope, and actual principal |
| `ClassCastException: DefaultOAuth2User ... OidcUser` | Casting every principal to OIDC | Use `instanceof` or segregate endpoints |
| `getAttribute("email")` returns `null` | Provider does not release email, missing consent/scope, or different key | Check provider payload and claims configuration |
| `getEmail()` returns `null` despite OIDC login | Email is an optional claim; IdP did not release it | Check ID Token/UserInfo and IdP policy |
| `getName()` is a number/UUID instead of username | Default name attribute key is provider ID or `sub` | Use a separate displayName; check `user-name-attribute` |
| `getUserInfo()` is `null` | UserInfo was not called or provider did not supply it | Check provider, scopes, and OIDC user service |
| `roles` claim exists but `hasRole('ADMIN')` is denied | Claim not mapped to `GrantedAuthority` or role name differs | Check actual authorities and mapping policy |
| `ROLE_ADMIN` remains after admin rights were revoked | Stale session/authentication not updated | Check refresh/revalidation/session invalidation |
| Account mislinked after email change | Used email as the external identity key | Use OIDC issuer+subject or a stable provider ID |
| UserInfo and ID Token have different `sub` | Identity source mismatch/error, broken custom fetch | Halt processing; enforce OIDC subject binding check |
| WebFlux service reads principal incorrectly | Used `ThreadLocal` context inside reactive chain | Use `ReactiveSecurityContextHolder` or proper injection |
| API requires bearer token but app only has OIDC principal | Confused login principal with authorized client | Obtain access token from OAuth2 authorized client with right audience |
| `Map.of(...)` throws `NullPointerException` | Optional field like email/name is null | Handle absent fields before building the Map |
| `ClassCastException` when reading `id` | Provider returns number, code casts to String | Check types inside attributes map |
| Login does not produce `OidcUser` | Provider does not actually support OIDC or request lacks `openid` scope | Check discovery, grant, and OIDC configuration |

### 17.1. Controlled Principal Inspection

In development, inspect the **principal class name**, registration ID, and the list of attribute **keys** (not values):

~~~java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

if (authentication != null
        && authentication.getPrincipal() instanceof OAuth2User user) {

    String principalType = user.getClass().getSimpleName();
    Set<String> attributeKeys = user.getAttributes().keySet();

    // Use a debugger or controlled logging per environment policy.
}
~~~

Inspecting keys is generally less sensitive than logging all attributes, though telemetry policies, limits, and data minimization still apply. In particular, **never log raw ID Tokens, access tokens, refresh tokens, email/phone without reason, session cookies, or client secrets**.

### 17.2. Distinguishing Authentication and Authorization Failures

- **401 Unauthorized** typically occurs when unauthenticated or when a token/credential is rejected.
- **403 Forbidden** typically occurs when authenticated but lacking sufficient authorities/permissions.
- A user holding a valid `OidcUser` **does not mean** they are allowed to call every endpoint.
- An API Resource Server rejecting an access token is a different problem from `OidcUser.getClaims()` inside a portal.

If `@PreAuthorize("hasRole('ADMIN')")` denies access, inspect the authorities attached to Authentication, the role mapping policy, and internal user status. Do not add `ROLE_ADMIN` to every user just to make an endpoint work.

## 18. Practice Scenarios

### Scenario A — Logging In with Google OIDC and Displaying Email

**Problem:** A profile page wants to display the user's email after login.

**Approach:** Inject `OidcUser` and call `getEmail()`, handle null, and display only per data protection policies. If business logic requires a verified email, check the `email_verified` claim from a trusted IdP.

**Avoid:** using email as the sole primary key of an internal account or automatically treating email as admin privileges.

### Scenario B — Logging In with GitHub OAuth2, `OidcUser` Is Not Injected

**Problem:** The controller initially used `@AuthenticationPrincipal OidcUser`, but on GitHub login the principal is not of that type.

**Approach:** Use `OAuth2User`, read GitHub attributes, identify the stable provider ID, and build an appropriate adapter. If the app supports multiple providers, use `instanceof OidcUser` for the OIDC branch.

**Avoid:** casting `DefaultOAuth2User` to `OidcUser` or treating a plain OAuth2 provider as OIDC when the OIDC protocol is not used.

### Scenario C — Corporate IdP Adds a `department` Claim

**Problem:** The UI needs to display the department name from the token/UserInfo.

**Approach:** Read `user.getClaims().get("department")`, verify the type, and handle missing values. If you must know whether the claim came from the ID Token or UserInfo, read each source individually. Map to an internal DTO.

**Avoid:** treating `department="security"` as admin rights without an authorization policy.

### Scenario D — Privileges Revoked, but Session Still Has Access

**Problem:** The IdP removes a user from the admin group, yet `authentication.getAuthorities()` still retains `ROLE_ADMIN`.

**Approach:** Check when the user logged in, the authority mapping mechanism, and the session lifecycle. If immediate revocation is required, implement revalidation/internal permission lookup or invalidation; do not rely on claims captured at login.

### Scenario E — One Employee Has Multiple SSO Accounts with the Same Email

**Problem:** Two issuers return the same email, but different `sub` values.

**Approach:** Key external identities by **issuer + subject**, and only merge into an internal user through an authorized account-linking workflow. Email may serve as a hint, not proof that two identities are the same person.

### Scenario F — Backend Needs to Call Orders API After Login

**Problem:** Having an `OidcUser`, a developer wants to send `user.getIdToken().getTokenValue()` as a bearer token to the Orders API.

**Approach:** Obtain an access token issued for the Orders API via `OAuth2AuthorizedClient`/manager and an OAuth2 HTTP client, letting the Orders API as a Resource Server validate audience, scope, and signature/introspection. The ID Token serves client identity authentication, not as a default API credential.

### Scenario G — WebFlux Request Uses `SecurityContextHolder` and Gets a Null Principal

**Problem:** A reactive service accesses the context on another thread after `flatMap`.

**Approach:** Use `ReactiveSecurityContextHolder.getContext()` or pass identity down the reactive chain from the controller; do not assume context exists on every `ThreadLocal` when Reactor switches schedulers.

## 19. Review Questions

**Question 1. Is `OidcUser` a kind of `OAuth2User`?**

Yes. `OidcUser` extends `OAuth2User` and adds OIDC APIs such as `getIdToken()`, `getUserInfo()`, and claim accessors.

**Question 2. With GitHub OAuth2 Login, can you always inject `OidcUser`?**

No. An OAuth2 provider not using OIDC may return an `OAuth2User`/`DefaultOAuth2User` principal. Use the right interface and check types.

**Question 3. How do `getAttributes()` and `getClaims()` differ?**

`getAttributes()` is `OAuth2User`'s generic data map; `OidcUser` also has OIDC claims and standard getters. When you need the source, read `getIdToken().getClaims()` or `getUserInfo().getClaims()` if UserInfo exists.

**Question 4. Should email be used as the sole key to link an OIDC identity to an internal user?**

It should not. Emails can change or be reassigned. The **issuer + subject** pair from a verified ID Token is typically the standard basis for identification.

**Question 5. Does the `email_verified=true` claim automatically grant `ROLE_USER` or `ROLE_ADMIN`?**

No. Email verification and authorization are separate concerns; authority mapping requires an explicit policy.

**Question 6. Does an ID Token with syntactically valid `sub` and `iss` prove identity by itself?**

No. The token must be verified by Spring Security / the OIDC client for signature, issuer, audience, expiration, nonce if applicable, and related constraints.

**Question 7. Is `OidcUser.getUserInfo()` always non-null?**

No. It depends on the provider, scopes, configuration, and whether UserInfo is used. The application must handle missing UserInfo.

**Question 8. Does `getName()` always return a readable email?**

No. It depends on the name attribute key/implementation. With OIDC it may be `sub`, while display name is another field.

**Question 9. In WebFlux, what should you use to retrieve the security context inside a reactive service?**

Use `ReactiveSecurityContextHolder` or reactive framework injection/parameters. Avoid relying on `ThreadLocal` context when Reactor switches threads.

**Question 10. Does the access token live on `OidcUser` or `OAuth2AuthorizedClient`?**

The access token belongs to **`OAuth2AuthorizedClient`**; `OidcUser` represents the user and exposes APIs to read the ID Token/claims.

**Question 11. Why should `/api/me` not return raw `getAttributes()`?**

Because it may contain sensitive user data/metadata or fields unnecessary for the frontend. Return a DTO with explicitly allowed fields.

**Question 12. Does a `roles=["editor"]` claim in an ID Token automatically make `hasRole("EDITOR")` evaluate to true?**

No. The application must configure a `GrantedAuthoritiesMapper` or internal role-mapping mechanism, ensuring trusted issuers/claims and proper authority conventions.

## 20. Official References

- [Spring Security Reference — OAuth 2.0 Login (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)
- [Spring Security Reference — Advanced OAuth 2.0 Login Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html)
- [Spring Security Reference — OAuth 2.0 Login (Reactive)](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html)
- [Spring Security API — OAuth2User](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/core/user/OAuth2User.html)
- [Spring Security API — OidcUser](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/core/oidc/user/OidcUser.html)
- [Spring Security API — DefaultOAuth2User](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/core/user/DefaultOAuth2User.html)
- [Spring Security API — DefaultOidcUser](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/core/oidc/user/DefaultOidcUser.html)
- [Spring Security API — OAuth2AuthenticationToken](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/client/authentication/OAuth2AuthenticationToken.html)
- [Spring Security API — OidcUserAuthority](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/core/oidc/user/OidcUserAuthority.html)
- [OpenID Connect Core 1.0 — ID Token and Standard Claims](https://openid.net/specs/openid-connect-core-1_0.html)
- [OpenID Connect Core 1.0 — Subject Identifier Types](https://openid.net/specs/openid-connect-core-1_0.html#SubjectIDTypes)

**Takeaway:** `OAuth2User` supplies provider-specific **attributes**; `OidcUser` extends it with **ID Token and OIDC claims**. Use `@AuthenticationPrincipal` or `Authentication` to read the principal, handling optional fields and data types safely. For OIDC, link internal identities using **issuer + subject**, use claims for profile data per policy, and **map authorities explicitly** when authorization is needed. The logged-in principal, the access token for calling APIs, and business roles are distinct responsibilities.
