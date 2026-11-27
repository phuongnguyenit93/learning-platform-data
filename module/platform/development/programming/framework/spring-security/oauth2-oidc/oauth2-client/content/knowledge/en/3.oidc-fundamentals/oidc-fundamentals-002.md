# 3.2. Scopes `openid`, `profile`, `email`, `address`, and `phone`

In **Spring Security OAuth 2.0/OIDC Client**, when a user logs in with an OpenID Provider (OP), the application typically requests **scopes** to indicate that it wants to perform an OIDC login and specify which groups of user information it needs. The five standard scopes commonly used are `openid`, `profile`, `email`, `address`, and `phone`.

The core question of this lesson is: **what does requesting a scope mean, which claims does that scope correspond to, and where does Spring Security read the granted information?** Answering this accurately helps avoid confusing *requesting access*, *obtaining user consent*, *actually receiving claims*, and *making authorization decisions in the application*.

## 1. Overview: How Do Scopes Differ from Claims?

In OAuth 2.0, `scope` is a list of strings requested by the Client in the authorization request. The Authorization Server decides which scopes to grant based on Client configuration, policy, user consent, and authentication context.

**OIDC** builds on OAuth 2.0 by defining the `openid` scope as the signal for an identity authentication request and adding scopes used to **request standard groups of claims**.

- **Scope** is the *name of a requested permission or information group*, such as `email`.
- **Claim** is a *named attribute and value about the user or authentication event*, such as `"email": "lan@example.test"`.
- **ID Token** is the signed/validated OIDC token used to confirm the user's identity and the login event.
- **UserInfo Endpoint** is an OIDC endpoint that the Client can call with an access token to retrieve a set of claims about the user.
- **Access token** is used to access authorized resources, such as the UserInfo Endpoint; it does not necessarily contain all claims requested by the Client itself.

For example, the Client requests `scope=openid%20profile%20email`. That does not mean the IdP is required to return every field of `profile`, nor does it guarantee `email_verified=true`. Claims in these groups may be missing because the data does not exist, the user did not consent, the Client was not granted permission, or IdP policy restricts disclosure.

### 1.1. Summary Table of the Five Standard Scopes

| Scope | Purpose | Standard Claims Requested |
|---|---|---|
| `openid` | Initiates an **OIDC authentication request**; distinguishes from plain OAuth 2.0 | Results in an ID Token; identifies the subject via `sub` (the ID Token also carries other required protocol claims) |
| `profile` | Requests basic profile information | `name`, `family_name`, `given_name`, `middle_name`, `nickname`, `preferred_username`, `profile`, `picture`, `website`, `gender`, `birthdate`, `zoneinfo`, `locale`, `updated_at` |
| `email` | Requests email address and email verification status | `email`, `email_verified` |
| `address` | Requests the user's contact address | `address` (an object with sub-fields) |
| `phone` | Requests phone number and phone verification status | `phone_number`, `phone_number_verified` |

The list in the table represents **the claims requested by each scope under OIDC**, not a guarantee that every claim will be present. An IdP may have additional scopes such as `roles`, `groups`, or custom API scopes; those **do not belong** to the five standard scopes covered here and require consulting the provider's documentation.

### 1.2. Why Must `openid` Be Present?

In an OAuth 2.0 request without `openid`, the Server is not instructed to process it as an OIDC request. When `openid` is present in the authorization request and the OIDC flow succeeds, the Client receives an **ID Token** to verify identity. The ID Token includes protocol claims such as `iss` (issuer), `sub` (subject), `aud` (audience), `exp`, and `iat`.

Keep these distinctions clear:

- `openid` is the **mandatory OIDC scope**.
- `profile`, `email`, `address`, and `phone` are **optional scopes** to request additional information.
- `sub` is the subject identifier issued by the issuer; it is not a name, email, or phone number.
- Receiving an ID Token **does not depend** on requesting `profile` or `email`.

A configuration with only `scope=openid` can still allow users to perform OIDC login if the IdP/Client supports the corresponding flow. If the UI needs a display name, the application can also request `profile`; if a feature needs an email contact address, it can consider `email`.

## 2. Where Do Scopes Appear in the Login Flow?

In the Authorization Code Flow, Spring Security OAuth2 Login redirects the browser to the IdP's Authorization Endpoint. That URL includes the `scope` parameter, for example:

```http
GET /authorize?
    response_type=code&
    client_id=web-client&
    redirect_uri=https%3A%2F%2Fapp.example.test%2Flogin%2Foauth2%2Fcode%2Fcompany&
    scope=openid%20profile%20email%20address%20phone&
    state=RANDOM_STATE&
    code_challenge=RANDOM_CHALLENGE&
    code_challenge_method=S256 HTTP/1.1
Host: id.example.test
```

The example is wrapped across lines only for readability; an actual request must have a valid URL-encoded URI. This is the authorization request generated by Spring Security Client from `ClientRegistration` to send the browser to the provider. With OIDC, parameters such as `nonce` are also commonly included in the authentication request.

```mermaid
sequenceDiagram
    autonumber
    participant Browser as Browser
    participant Spring as Spring Security Client
    participant OP as OpenID Provider

    Browser->>Spring: GET /oauth2/authorization/company
    Spring-->>Browser: 302 to OP with scope=openid profile email...
    Browser->>OP: Authorization request
    OP->>OP: Login, evaluate policies and consent
    OP-->>Browser: Redirect URI with code, state
    Browser->>Spring: /login/oauth2/code/company?code=...&state=...
    Spring->>OP: POST Token Endpoint to exchange code
    OP-->>Spring: Access token, ID Token, ...
    opt UserInfo Endpoint exists and Client has access
        Spring->>OP: GET UserInfo with access token
        OP-->>Spring: Permitted claims
    end
    Spring->>Spring: Validate ID Token, create OidcUser
    Spring-->>Browser: Establish login session
```

In the diagram above, scopes are **requested at the Authorization Endpoint**; tokens and claims are received **after the flow succeeds**. Depending on provider configuration, claims may reside in the ID Token, the UserInfo response, or be aggregated from both sources. Do not assume that simply opening the ID Token payload will show all of `profile`, `email`, `address`, and `phone`.

### 2.1. Distinguishing Requested Scopes from Granted Scopes

Suppose the Client requests:

```text
openid profile email address phone
```

The provider may approve only a subset, or reject invalid scopes. The OAuth 2.0 token response may include a `scope` field describing the granted scopes:

```json
{
  "access_token": "example-access-token",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "openid profile email",
  "id_token": "example-id-token"
}
```

In this example, the application cannot assume it received `address` and `phone` just because it requested them. If `scope` is absent from the token response, apply OAuth 2.0 rules and provider configuration to determine granted scopes; never assume all desired fields are present.

**Even a granted scope does not guarantee the claim will be returned.** The safe design is to verify that a claim exists and has the expected data type before using it.

## 3. The `openid` Scope: Identity Authentication, Not Just Reading a Profile

`openid` turns the request into an OpenID Connect authentication request. With the Authorization Code Flow, after Spring successfully exchanges the authorization code, the OIDC token response includes an ID Token. Spring Security validates the ID Token using OIDC mechanisms, such as signature, issuer, audience, expiration, and correlation checks against the authorization request per the flow.

Example ID Token, showing the **decoded payload** for readability (not a real JWT token):

```json
{
  "iss": "https://id.example.test/realms/company",
  "sub": "u_314159",
  "aud": "spring-web-client",
  "exp": 1781111000,
  "iat": 1781107400,
  "auth_time": 1781107390
}
```

Only the claims relevant to the specific flow and scenario appear; `auth_time`, for instance, is not required in every ID Token. The timestamps and domain names in the example are illustrative.

### 3.1. `sub` Is the Key Identifier

An application often needs a stable key to link a user's account in its internal system. With OIDC, use the pair:

```text
(iss, sub)
```

For example:

```text
("https://id.example.test/realms/company", "u_314159")
```

Why `iss` is required: two different IdPs may issue the same `sub` string to different users. Why not use `email` as the primary key: emails can change, be missing, or be recycled depending on provider policy. `preferred_username` and `name` can also change and are not guaranteed to be unique.

An IdP may use **pairwise subject identifiers**, meaning the same person can receive a different `sub` across different Clients/sectors. Therefore, never automatically merge accounts across multiple applications simply by comparing names or email addresses.

### 3.2. `openid` Does Not Equal Business API Access

OIDC login answers the question **"Who is the user according to the provider?"**. Deciding "is this person allowed to approve invoices or administer users?" is application **authorization**. The `openid` scope does not automatically grant an `ADMIN` role or access to any API.

If the application also calls protected APIs, check whether the access token has the appropriate audience, scopes, and policies for that API. OIDC scopes used to request claims and scopes granting API permissions serve related purposes but should not be conflated.

## 4. The `profile` Scope: Requesting Basic Profile Data

`profile` requests the group of claims describing a user's profile. The standard claims have the following meanings:

| Claim | Example | Meaning and Notes |
|---|---|---|
| `name` | `"Nguyễn Thị Lan"` | Full display name; not a unique identifier |
| `family_name` | `"Nguyễn"` | Surname or family name |
| `given_name` | `"Lan"` | Given name / first name |
| `middle_name` | `"Thị"` | Middle name |
| `nickname` | `"Lan"` | Nickname |
| `preferred_username` | `"lan.nguyen"` | Preferred username or login handle; may change and is not guaranteed unique |
| `profile` | `"https://id.example.test/users/u314159"` | URL of the user's profile page |
| `picture` | `"https://cdn.example.test/u314159.png"` | URL of the profile picture |
| `website` | `"https://example.test"` | URL of the user's website |
| `gender` | `"female"` | Gender information if provided by the user/provider |
| `birthdate` | `"1995-06-03"` | Birthdate in an OIDC-supported representation; sometimes only year or month/day |
| `zoneinfo` | `"Asia/Ho_Chi_Minh"` | Time zone from the timezone database |
| `locale` | `"vi-VN"` | Preferred language/region as a language tag |
| `updated_at` | `1781100000` | Time the user's information was last updated, as Unix seconds |

A minimal profile response might contain only:

```json
{
  "sub": "u_314159",
  "name": "Nguyễn Thị Lan",
  "preferred_username": "lan.nguyen",
  "picture": "https://cdn.example.test/avatars/u314159.png",
  "locale": "vi-VN"
}
```

Requesting `profile` **does not mean** the IdP is required to store all 14 claims or allow the Client to read all of them. Each provider decides what data is available and allowed to be disclosed.

### 4.1. How Should `name`, `picture`, and `locale` Be Used?

- Use `name` or `preferred_username` as an option for displaying a greeting, after checking for empty/null values.
- Use `picture` to display an avatar after safely handling the URL according to UI requirements.
- Use `locale` to suggest a UI language, while still respecting the user's actual language choice.

Do not use these values as a basis for security or authorization. Even the `updated_at` field only describes the profile update timestamp at the IdP; it does not guarantee the application holds real-time synchronized data.

## 5. The `email` Scope: Email and Verification Status

`email` requests two standard claims:

| Claim | Type | Example | Interpretation |
|---|---|---|---|
| `email` | String | `"lan@example.test"` | User's email address |
| `email_verified` | Boolean | `true` | Provider indicates it performed a verification step for control of the email address according to its mechanism |

Example:

```json
{
  "sub": "u_314159",
  "email": "lan@example.test",
  "email_verified": true
}
```

### 5.1. Three States to Distinguish

In a Java program, the `email_verified` claim can be:

1. Present with value `true`.
2. Present with value `false`.
3. **Absent**.

The third case must not be arbitrarily interpreted as the provider asserting the email is unverified; it represents a state of **no verification information available** in the data received by the Client. In sensitive features, only accept `Boolean.TRUE.equals(value)` if a verified email is required.

### 5.2. "Email Verified" Does Not Replace Authorization

`email_verified=true` does not prove a user belongs to a specific department, is currently an employee of a company, or holds administrative rights. Nor does it guarantee the email address will never change or that control over the email cannot be lost later.

For example, if a SaaS application wants to restrict access to members of an organization:

- Simply checking whether the email ends with `@company.test` is insufficient for authorization.
- You need organization membership management, invitations, internal roles/permissions, or assertions from a trusted identity system.
- If email verification is needed before sending notifications, you can require `email_verified=true` per feature policy.

For account linking, use `(iss, sub)` and an appropriate internal account-ownership confirmation mechanism; never automatically merge two accounts solely because their current emails match.

## 6. The `address` Scope: Address Is a Structured Object

Unlike `email`, the `address` scope primarily requests **a single `address` claim formatted as a JSON object**. According to OIDC's standard Address Claim definition, the object has the following fields:

| Sub-field | Example | Meaning |
|---|---|---|
| `formatted` | `"12 Street A\nDistrict B\nHo Chi Minh City"` | Full formatted mailing address for display |
| `street_address` | `"12 Street A"` | Street, house number, detailed street line |
| `locality` | `"Ho Chi Minh City"` | City or locality |
| `region` | `"Ho Chi Minh"` | State, province, prefecture, or region |
| `postal_code` | `"700000"` | Postal code |
| `country` | `"VN"` | Country; exact representation depends on provider data |

Example response:

```json
{
  "sub": "u_314159",
  "address": {
    "formatted": "12 Street A\nWard B\nHo Chi Minh City",
    "street_address": "12 Street A",
    "locality": "Ho Chi Minh City",
    "region": "Ho Chi Minh",
    "postal_code": "700000",
    "country": "VN"
  }
}
```

### 6.1. Why Not Treat `address` as a String?

In JSON, `address` is an object; in Java, for instance, the data may be represented as a `Map<String, Object>`. Reading it as a `String` can cause cast exceptions or lose its structure.

In addition:

- `formatted` is a convenient presentation form; detailed sub-components may be missing or vary by country.
- A profile address is not automatically the **shipping address** or **billing address** chosen by the user for a transaction.
- The data may be outdated or only partially accurate. When handling shipping, invoicing, or residency checks, re-confirm it in the corresponding business workflow.
- `address` is contextually sensitive personal data; only request and store it when a feature genuinely needs it.

Not every IdP supports the `address` scope. In some enterprise login systems, address information may exist only in an internal directory or not be exposed via OIDC.

## 7. The `phone` Scope: Phone Number and Verification Status

`phone` requests two claims:

| Claim | Type | Example | Interpretation |
|---|---|---|---|
| `phone_number` | String | `"+84901234567"` | Phone number, recommended in E.164 international format when the provider can supply it |
| `phone_number_verified` | Boolean | `false` | Provider indicates verification status for control of the phone number under its mechanism |

Example:

```json
{
  "sub": "u_314159",
  "phone_number": "+84901234567",
  "phone_number_verified": true
}
```

### 7.1. Having a Phone Number Does Not Mean It Is Verified

Even when `phone_number` is present, `phone_number_verified` can still be `false` or omitted. An application that requires a verified phone number must explicitly check the verification status rather than merely checking `phone_number != null`.

Like `email_verified`, a provider having previously verified a phone number is not guaranteed proof that the number still belongs to the same person at all times. If a phone number is used to verify high-risk transactions, the application may need additional verification steps or security policies.

### 7.2. The `phone` Scope Does Not Grant Permission to Send SMS or Perform MFA

Receiving the `phone_number` claim only provides information if approved; it does **not** automatically grant consent for all communications, nor does it mean the provider performed SMS MFA during the login session. To determine which authentication method was used, rely on authentication metadata provided by the provider—such as the `amr` or `acr` claims when available and agreed upon—not on the fact that the `phone` scope was requested.

## 8. ID Token and UserInfo: Same Scope, Different Possible Locations for Claims

This is one of the most commonly misunderstood points when working with Spring Security OIDC Client.

### 8.1. The ID Token Is Not a Complete Profile Record

The ID Token is meant to **verify the authentication session and identify the subject**. A provider may include `name`, `email`, or other claims in the ID Token, but requesting `profile email` from the Client does not guarantee those claims will appear there.

Example decoded ID Token:

```json
{
  "iss": "https://id.example.test",
  "sub": "user-782",
  "aud": "spring-web",
  "iat": 1781107200,
  "exp": 1781110800
}
```

The UserInfo response may be separate:

```json
{
  "sub": "user-782",
  "name": "Nguyễn Thị Lan",
  "email": "lan@example.test",
  "email_verified": true,
  "phone_number": "+84901234567",
  "phone_number_verified": false
}
```

The two examples represent **the same subject** with `sub="user-782"`. Per OIDC, `sub` in the UserInfo response must match `sub` in the ID Token; the Client must ensure data from two different users is never mixed up.

### 8.2. When Does the Client Call UserInfo?

A provider publishes `userinfo_endpoint` in its OIDC metadata if supported. The Client can use the access token received from the Token Endpoint to call this endpoint:

```http
GET /userinfo HTTP/1.1
Host: id.example.test
Authorization: Bearer ACCESS_TOKEN_EXAMPLE
Accept: application/json
```

Example response:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "sub": "user-782",
  "name": "Nguyễn Thị Lan",
  "email": "lan@example.test",
  "email_verified": true
}
```

Spring Security OAuth2 Login integrates reading OIDC information and building `OidcUser` based on provider configuration. Whether the UserInfo Endpoint is called and which claims are fetched depend on provider capabilities and Spring Security configuration; UserInfo should not be treated as a call that always happens unconditionally.

When UserInfo is present, applications commonly access data via `OidcUser#getClaims()`, and can also inspect `getIdToken()` and `getUserInfo()` separately to determine the source of a claim. Before processing `getUserInfo()`, account for the possibility that it may be absent.

### 8.3. Scope Granted Yet Claim Missing: Is This Normal?

Yes. Reasons include:

- The user never entered that information.
- The IdP does not store or expose that field.
- The user declined to share that field.
- The account or Client is restricted by policy.
- UserInfo was not called by the Client under the active configuration.
- The provider returns the claim in UserInfo, but the developer only inspected the ID Token.
- The scope was not granted or the IdP does not support the requested scope.

For this reason, the application should process data based on the **actual values received**, rather than inferring availability from the list of requested scopes.

### 8.4. What Is the Claims Parameter?

OIDC also defines the `claims` authorization request parameter so a Client can express more granular requests for claims in the ID Token or UserInfo response—for example, requesting a specific claim as essential. However, this is a separate mechanism and depends on provider support. Adding the `email` scope is **not equivalent** to a guarantee that `email` will be returned; even more detailed `claims` requests remain subject to IdP policy and user permissions.

## 9. Configuring the Five Scopes in Spring Boot

In a Spring Boot application using **Spring Security OAuth2 Client**, you can configure an OIDC registration in `application.yml` as follows:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            client-authentication-method: client_secret_basic
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
              - address
              - phone
        provider:
          company:
            issuer-uri: https://id.example.test/realms/company
```

This is an illustrative address; replace `issuer-uri` with the actual issuer published by your provider. For a provider supporting OIDC discovery, Spring can obtain the Authorization Endpoint, Token Endpoint, UserInfo Endpoint, and verification key information from metadata. Those endpoints are not scopes themselves.

Key configuration properties:

| Property | Meaning |
|---|---|
| `registration.company` | Client registration name in Spring; `company` is the `registrationId` |
| `client-id` | Client ID issued by the IdP |
| `client-secret` | Client secret when using a confidential client; store via secret manager or environment variable |
| `scope` | List of scopes requested when initiating the Authorization Code Flow |
| `redirect-uri` | Spring Client callback after the IdP completes the authorization request |
| `issuer-uri` | OIDC issuer address used to verify provider identity and discover metadata |

If you only need login and displaying name/email, many applications can start with:

```yaml
scope:
  - openid
  - profile
  - email
```

Only add `address` and `phone` once you have clearly identified the features using them and confirmed the IdP actually supports them. With a provider that disallows a given scope, the authorization request may fail with `invalid_scope` or an equivalent error.

### 9.1. Enabling OAuth2 Login in SecurityFilterChain

Servlet configuration example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
```

With the default configuration, users can initiate login via:

```text
GET /oauth2/authorization/company
```

After the IdP finishes processing, the browser returns to the callback path:

```text
GET /login/oauth2/code/company?code=...&state=...
```

Spring Security will then exchange the code, validate the OIDC tokens, and create the authenticated principal. Spring uses the registered scopes when constructing the authorization request; the application **does not need to manually append** `scope=...` to the login URL.

## 10. Reading Claims from `OidcUser` in Spring Security

When OIDC login succeeds, the principal is typically an `OidcUser`. This object provides access to the ID Token, UserInfo, and the combined claim set.

### 10.1. Example of an Endpoint Returning Minimal Information

The example below illustrates selective data retrieval using `@AuthenticationPrincipal`. In a real system, return only the fields needed by the UI and only to the account owner or an authorized viewer.

```java
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class AccountController {

    @GetMapping("/me")
    public Map<String, Object> me(@AuthenticationPrincipal OidcUser user) {
        if (user == null) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }

        Map<String, Object> response = new LinkedHashMap<>();

        // Canonical identifiers for account mapping.
        response.put("subject", user.getSubject());
        response.put("issuer", user.getIdToken().getIssuer().toString());

        putIfPresent(response, "name", user.getClaim("name"));
        putIfPresent(response, "email", user.getClaim("email"));

        // Verification claim may be absent; do not default to true.
        Object emailVerified = user.getClaim("email_verified");
        if (emailVerified instanceof Boolean) {
            response.put("emailVerified", emailVerified);
        }

        return response;
    }

    private static void putIfPresent(
            Map<String, Object> target, String name, Object value) {
        if (value != null) {
            target.put(name, value);
        }
    }
}
```

An example response:

```json
{
  "subject": "u_314159",
  "issuer": "https://id.example.test/realms/company",
  "name": "Nguyễn Thị Lan",
  "email": "lan@example.test",
  "emailVerified": true
}
```

This example avoids returning the entire `user.getClaims()` map because that dataset may include birthdate, address, phone number, or other sensitive claims unrelated to the current feature.

### 10.2. Reading `address`, `phone`, and Verification Fields

If a business feature truly requires them, each claim can be read individually:

```java
import java.util.Map;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

// Inside a method that received OidcUser user from Spring:
String phoneNumber = user.getClaimAsString("phone_number");
Boolean phoneVerified = user.getClaimAsBoolean("phone_number_verified");

Map<String, Object> address = user.getClaim("address");

if (Boolean.TRUE.equals(phoneVerified) && phoneNumber != null) {
    // Proceed with business logic requiring an IdP-verified phone number.
}

if (address != null) {
    Object city = address.get("locality");
    Object street = address.get("street_address");
    // Read and use only the needed fields; verify data types.
}
```

Here `address` is a JSON object, shown in the example as a `Map<String, Object>` provided by the data mapping library. With custom providers or mappers, the application may need to verify types before use.

If you want to distinguish whether a claim appeared in the ID Token or in UserInfo:

```java
import org.springframework.security.oauth2.core.oidc.OidcUserInfo;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

// Inside a method that received OidcUser user from Spring:
Object emailFromIdToken = user.getIdToken().getClaim("email");

OidcUserInfo userInfo = user.getUserInfo();
Object emailFromUserInfo =
    userInfo == null ? null : userInfo.getClaim("email");
```

This snippet shows that **a missing `email` in the ID Token does not mean `email` is missing altogether**. When UserInfo is available, Spring can aggregate claims onto the `OidcUser` object; however, provider policy still determines what data is returned.

### 10.3. Reading `openid` from Client Configuration Is Not How You Check Authentication

Do not write logic like this:

```java
// Do not use the configured scope list as proof of login:
boolean loggedIn = configuredScopes.contains("openid");
```

The scope list only indicates what the Client *intends to request*. Login state must be based on the `Authentication` verified and placed in `SecurityContext` by Spring Security. Likewise, never use the presence of `email` or `phone_number` as proof that the user holds a business role.

## 11. Scopes and Authorization Decisions Are Two Separate Layers

A common design mistake is equating the IdP returning `email` or `profile` with the application permitting business actions.

Consider these needs:

| Feature | OIDC Data Potentially Needed | Additional Business Conditions |
|---|---|---|
| Show greeting on dashboard | `openid profile`, read `name` if present | User is logged in |
| Send notification email | `openid email`, read `email` and consider `email_verified` | Notification consent, valid address, communication policy |
| Ship an order to an address | `openid address` if supported by provider | User confirms shipping address; data handling rules |
| Contact via phone number | `openid phone` | Valid number, appropriate usage purpose, and required contact permission |
| Access administrative features | `openid` may suffice to verify identity | System roles/permissions or a trusted authority source |

If a provider also returns a `groups` or `roles` claim, the Client must still clearly determine what mechanism produced that claim, how trustworthy it is, and how to map it to `GrantedAuthority`. The five standard OIDC scopes in this lesson do not automatically solve fine-grained authorization.

## 12. Data Minimization and Privacy Protection Principles

Scopes are not just technical parameters; they determine which categories of personal data the application requests access to. Good practices include:

1. **Only request scopes needed by features.** For instance, an app displaying only name/email does not need to request `address` and `phone` by default.
2. **Clearly explain usage purposes.** Consent prompts and permission descriptions must match actual product behavior.
3. **Only store the claims you need to store.** Do not copy the entire OIDC profile into your database "just in case".
4. **Never log tokens or full profiles.** Avoid logging ID Tokens, access tokens, refresh tokens, phone numbers, and street addresses.
5. **Handle missing or changed claims.** Never assume a claim will always exist or remain unchanged.
6. **Authorize personal data access by owner.** Endpoints returning personal claims must be protected and must not allow users to guess URLs to view someone else's data.
7. **Consider update lifecycles.** Information fetched at login time may become stale; if a business flow needs up-to-date data, establish an appropriate refresh mechanism.

In particular, `address` and `phone_number` are generally more sensitive than a display name. Avoid returning them in frontend responses if the UI does not need them.

## 13. Troubleshooting When Requesting Scopes Yields No Data

You may encounter the following situations when integrating a real provider.

| Symptom | Possible Cause | What to Check |
|---|---|---|
| Login succeeds but `email` is missing | Missing `email` scope, account has no email, or IdP does not share email | Check scopes in the authorization request and claims in UserInfo/ID Token |
| `email` is present but `email_verified` is missing | Provider does not return the verification claim | Handle unknown state; consult IdP documentation/policy |
| `profile` is present but `given_name` is missing | User has no value set or provider does not expose that claim | Use an appropriate display fallback; never assume all profile fields exist |
| `address` returns as an object instead of a string | This is the standard data type of the address claim | Read as an object/map; inspect sub-fields |
| Requested `phone` but `phone_number` is missing | Scope not granted, provider unsupported, or data missing | Check granted scopes and UserInfo mapping |
| Provider returns `invalid_scope` | Scope unsupported or Client not permitted to request it | Verify scope list/consent configured at the IdP |
| ID Token has no profile information | Provider delivers data via UserInfo or omits optional claims | Check UserInfo and OIDC Client configuration |
| Have `email` but failed to create internal user | Account lookup logic based on email causes conflicts | Link identity using `(iss, sub)` |
| Client manually appends `scope` to URL with no effect | Modifying the wrong URL or Spring uses a separate registration | Check `spring.security.oauth2.client.registration.<id>.scope` and the final request |
| `phone_number_verified=false` despite a number being present | IdP has not verified the number under its policy | Do not treat the phone number as verified; handle per business rules |

To isolate the issue, trace in order: **Which scopes did the Client request → did the IdP grant them → which claims are in the ID Token → was UserInfo called and which claims did it return → did the application read the exact claim name/type**.

### 13.1. Practical Scenario: A User Profile Page

A student management application logs in via OIDC and wants to display:

- Name and photo: request `profile`.
- Email for result notifications: request `email`.
- Phone number for contact support: request `phone` only if the feature genuinely uses that number.
- Mailing address for paper certificates: request `address` only if the product mails physical certificates; always let the user review and confirm the address.

The scope set can start with:

```text
openid profile email
```

When a user chooses a feature requiring an address or phone number, depending on IdP capabilities and product architecture, the application may need to expand permission requests, run an incremental consent flow, or collect the data directly according to policy. Do not request all personal data up front on the initial login screen by default.

## 14. Misconceptions to Avoid

**"Adding `scope=profile` guarantees the ID Token contains `name`."** False. A scope requests a group of claims; actual claims depend on the provider and may reside in UserInfo or be omitted altogether.

**"`email_verified=true` means the user is allowed to log into every system with that email domain."** False. An email verification signal does not replace internal access control decisions.

**"The `phone` scope means OTP/MFA was completed."** False. The scope requests phone number information, whereas authentication method information belongs to a separate domain.

**"`address` is an address string."** Incorrect under the standard OIDC model; it is an object containing fields such as `formatted`, `street_address`, and `locality`.

**"If a user has an email, we can use email instead of `sub`."** Not recommended. Email addresses can change; the pair `(iss, sub)` is the proper OIDC identifier for linking accounts per issuer.

**"Spring must manually call UserInfo with RestTemplate/WebClient on every login."** Not necessarily. `oauth2Login` has built-in OIDC UserInfo support within Spring Security. Provider configuration and user-service handling determine how claims are fetched.

**"Adding `address` and `phone` in YAML forces the IdP to return the data."** False. The provider may not support the scope, may require consent approval, or may have no data for that account.

## 15. Summary of Key Takeaways

- `openid` is the core scope to initiate **OIDC authentication** and receive an ID Token under the appropriate flow.
- `profile` requests profile claims such as `name`, `picture`, and `locale`; `email` requests `email` and `email_verified`.
- `address` requests an object-typed `address` claim; `phone` requests `phone_number` and `phone_number_verified`.
- **Requesting a scope ≠ being granted a scope ≠ guaranteed receipt of claims**. Applications must handle missing or invalid claims.
- Profile claims may live in the **ID Token, UserInfo, or both**. In Spring Security, `OidcUser` provides access to these data sources.
- Use `(iss, sub)` for OIDC identification, not display name, email, or phone number as the identity key.
- Standard scopes do not replace **application authorization**, business-level data validation, or personal data privacy policies.
- In Spring Boot, configure scopes under `spring.security.oauth2.client.registration.<registrationId>.scope` and enable `oauth2Login` so Spring executes the login flow.

## 16. References

- [OpenID Connect Core 1.0 — Standard Claims and Requesting Claims using Scope Values](https://openid.net/specs/openid-connect-core-1_0.html#ScopeClaims): standard claim list, `openid`, `profile`, `email`, `address`, `phone`, and rules for requesting claims.
- [OpenID Connect Core 1.0 — ID Token](https://openid.net/specs/openid-connect-core-1_0.html#IDToken): protocol claims and ID Token validation requirements.
- [OpenID Connect Core 1.0 — UserInfo Endpoint](https://openid.net/specs/openid-connect-core-1_0.html#UserInfo): using an access token to request user information.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): the `scope` concept, authorization requests, token responses, and granted scopes.
- [Spring Security Reference — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): `ClientRegistration`, `oauth2Login`, and OpenID Connect integration in Servlet applications.
- [Spring Security API — OidcUser](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/core/oidc/user/OidcUser.html): accessing the ID Token, UserInfo, and claims in an OIDC principal.
