# 3.9. Consent, prompt, max_age, login_hint, and Account Selection

## Lesson Objectives

In a Spring Security application acting as an **OpenID Connect Relying Party (RP)**, sending the user to an OpenID Provider (OP) to log in is only part of the authentication experience. The application also needs to control **when to ask the user to approve permissions**, **when to require re-authentication**, **when to let the user pick an account**, and **whether to suggest a login identity in advance**.

After this lesson, you will be able to:

- Distinguish **consent**, **user authentication**, and **account selection**.
- Explain the meaning of the OIDC `prompt` parameter values: `none`, `login`, `consent`, and `select_account`.
- Use `max_age` and the `auth_time` claim to express and enforce authentication freshness requirements.
- Understand how `login_hint` influences the login UI without becoming proof of identity.
- Customize the Authorization Request in **Spring Security OAuth 2.0 Client / OIDC Login** according to application policy.
- Recognize errors, limitations, and security considerations when the OP cannot satisfy a request.

## 1. Context: Logging In Involves More Than One Decision

Consider a **Customer Portal** application built with Spring Boot. The Portal uses an OpenID Connect–compatible OP to let customers log in.

When a customer visits the Portal, the application may need different experiences:

1. The customer already logged in at the OP earlier; the Portal wants to **reuse the SSO session** to avoid prompting for credentials again.
2. The customer wants to **switch to another account** existing at the OP, such as from a personal account to a work account.
3. The customer is about to change a payment method; the Portal requires a **sufficiently recent authentication**.
4. The Portal needs access to an additional data scope; the customer must have an opportunity to **approve consent** per OP policy.
5. The customer just entered an email on the Portal; the Portal wants to pass that email to the OP to **pre-fill the login box**.

These scenarios correspond to controls carried in the **OIDC Authorization Request** sent from the RP to the OP. They do not share the same meaning:

| Question | Typically Related Mechanism | Meaning |
|---|---|---|
| Does the user need to interact right now? | `prompt` | Controls how the OP handles user interaction |
| Should the consent screen be shown again? | `prompt=consent` | Requests that the OP re-prompt for approval |
| Is the last authentication too old? | `max_age`, `auth_time` | Sets and verifies authentication freshness |
| Should an account be suggested? | `login_hint` | Suggests an input identity to the OP |
| Should the user choose an account? | `prompt=select_account` | Asks the OP to present an account chooser |

**Core takeaway:** the login UI, the permission consent screen, and the re-authentication mechanism are distinct steps, even though an OP may combine them within a single journey.

## 2. What Is Consent in OpenID Connect?

### 2.1. Consent Is the Decision to Share Data or Grant Permissions

In OAuth 2.0 and OIDC, **consent** is typically an interaction at the Authorization Server/OP where the user approves a client receiving requested access rights or information.

For example, the Portal requests:

~~~text
scope=openid profile email
~~~

The OP may display a message along the lines of:

> Customer Portal wants to know your identity and read certain profile details, such as your name and email.

If the user approves, the OP continues the authorization flow per policy. If they decline, the OP may return an `access_denied` error to the client's redirect URI.

**Consent does not mean authentication:**

- **Authentication:** the OP determines who the user is, using a password, passkey, MFA, or another method.
- **Consent:** the user/OP decides which permissions or data the client may receive.
- **Authorization at the Resource Server:** the API checks the access token and actual permissions to allow or deny an operation.

Being logged in does not mean all scopes were approved; having consent also does not automatically mean the user is authorized to perform every business action on the Portal.

### 2.2. Why Is the Consent Screen Sometimes Not Shown?

Not every Authorization Request leads to a permission prompt. An OP may skip the consent UI because:

- The user already granted the same scopes to the client previously.
- The client is an internal application pre-approved by an administrator under OP policy.
- Provider policy allows handling certain scopes without prompting separately on that visit.
- The OP uses another established mechanism to record approval.

This does **not** prove the application isn't using OAuth 2.0/OIDC. Whether a consent screen appears is determined by the combination of client request, scopes, prior grant state, and OP policy.

### 2.3. Consent Relates to Scopes, Yet Scopes Are Not Business Permissions

OIDC defines several familiar scopes:

| Scope | Typical Purpose |
|---|---|
| `openid` | Indicates an OIDC request; required to receive an ID token in the appropriate flow |
| `profile` | Requests profile claims such as name, display name, etc., per OP policy |
| `email` | Requests email claims |
| `phone` | Requests phone number claims |
| `address` | Requests address claims |
| `offline_access` | Requests access when the user is not present, typically related to a refresh token, if permitted by the OP |

You cannot infer that a scope always returns every claim; some claims may be delivered via the **UserInfo Endpoint**, and the OP still applies release policies.

Provider-specific API scopes, such as `orders.read` or `payments.write`, do not automatically turn into Spring Security authorities inside the application. The Portal must still determine what the user is allowed to do with its own internal data.

### 2.4. Requesting Consent Again with `prompt=consent`

Example of an Authorization Request containing:

~~~text
prompt=consent
~~~

The `consent` value asks the OP to **prompt the user for consent** before returning an authorization result, even if a login session or prior grant already exists. Under OIDC, the OP should re-prompt; exact UI behavior still depends on OP capabilities and policy.

Appropriate scenarios:

- The application has just requested **additional scopes** not previously granted.
- A business workflow requires the user to review data-sharing permissions.
- Provider policy requires explicit confirmation for sensitive permissions.

Do not attach `prompt=consent` to every page load unnecessarily: users may face repetitive consent screens, causing friction or failing to complete flows when the OP does not support that experience.

With `offline_access`, the OP may require an appropriate consent flow or separate conditions to issue a refresh token. **Requesting `offline_access` or `prompt=consent` does not guarantee a refresh token will be issued**; the outcome depends on grant, client type, and OP policy.

## 3. The `prompt` Parameter: How the Application Asks the OP to Handle Interaction

`prompt` is a standard OIDC Authentication Request parameter. Its value is a set of **space-delimited** keywords. Basic values:

| Value | What the RP Asks the OP to Do | When Commonly Used |
|---|---|---|
| `none` | Display no interactive authentication/consent UI whatsoever; return an error if impossible | Testing silent SSO capability in an appropriate context |
| `login` | Require the user to re-authenticate | Accessing high-sensitivity actions, switching authentication sessions |
| `consent` | Ask the OP to prompt the user for permission consent | Requesting extra scopes or needing permission confirmation |
| `select_account` | Ask the OP to let the user choose an account | User wants to switch the logged-in account |

### 3.1. `prompt=none` — Disallowing Interaction

When receiving `prompt=none`, the OP **must not** display any interactive step to the user. If the OP cannot return a successful result without interaction, it returns an appropriate error.

Situations commonly leading to errors:

- No valid login session exists at the OP: `login_required`.
- User interaction is needed to satisfy the request: `interaction_required`.
- Required consent has not been granted: `consent_required`.
- The user needs to select an account: `account_selection_required`.

These error codes are defined by OIDC; an OP may return codes matching the situation and its support level.

**Never combine `none` with any other `prompt` value.** For example, `prompt=none%20login` is semantically invalid.

`prompt=none` does not mean "log in without security checks". It asks the OP to **succeed only when conditions already allow non-interactive processing**. Silent SSO mechanisms depend on sessions/cookies and browser capabilities; third-party cookie blocking or iframe restrictions can make iframe-based silent authentication unreliable. In modern web applications, provide a standard interactive login redirect fallback when needed.

### 3.2. `prompt=login` — Requesting Re-Authentication

`prompt=login` asks the OP to re-authenticate the user, even if the browser already holds an SSO session. "Re-authenticate" **does not necessarily mean re-entering a password**: the OP may use a passkey, MFA, or another mechanism.

Per OIDC, the OP should perform re-authentication; if unable, it must return an appropriate error. However, relying solely on `prompt=login` appearing in the URL to conclude a fresh authentication actually occurred is insufficient for high-security operations.

For policies such as **"authenticated within the last N seconds"**, `max_age` combined with checking `auth_time` gives clearer evidence about authentication timing, covered in the next section.

### 3.3. `prompt=consent` — Requesting Re-Consent

`prompt=consent` pertains to permissions requested by the client and **does not force the user to re-enter a password**. The OP may already know who the user is yet still need them to confirm sharing permissions.

When combined:

~~~text
prompt=login consent
~~~

The RP asks for both re-authentication **and** showing consent. Words in the `prompt` value are separated by spaces; when placed in a URL, they must be URL-encoded:

~~~text
prompt=login%20consent
~~~

Do not use commas (`login,consent`) as the standard separator.

### 3.4. `prompt=select_account` — Requesting Account Selection

When a user has multiple accounts known to the OP, `select_account` asks the OP to offer account selection instead of defaulting to the current SSO account.

Example:

~~~text
prompt=select_account
~~~

Per OIDC, the OP should ask the user to choose an account. If unable, the OP may return `account_selection_required`. The actual UX depends on the OP: the provider may show an account list, a username input box, or another selection interface.

**The RP must not treat `prompt=select_account` as proof that the user picked a specific account.** After the callback, the RP must rely on a valid ID token and the `iss` + `sub` identifier to determine who just logged in.

### 3.5. Combining `prompt` Values

Several values can be combined, except `none` must stand alone:

| Requirement | Example |
|---|---|
| Re-authenticate and ask consent | `prompt=login consent` |
| Let user select account then ask consent | `prompt=select_account consent` |
| Let user select account and re-authenticate | `prompt=select_account login` |
| Handle non-interactively | `prompt=none` |

Some providers do not fully support every value or combination. The client must check OP documentation/metadata; error responses are protocol outcomes that must be handled rather than assuming every option is always honored.

## 4. `max_age`: Freshness of the Authentication Event

### 4.1. What Does `max_age` Measure?

`max_age` is an integer specifying the **maximum number of seconds that may elapse since the OP actively authenticated the user** up to the time of the OIDC request, as permitted by the RP.

Example:

~~~text
max_age=300
~~~

The Portal requires the authentication at the OP to be recent within a **5-minute** threshold. If the prior authentication exceeds that threshold, the OP needs to handle re-authentication to satisfy the request.

Some examples:

| Value | Meaning |
|---|---|
| `max_age=0` | Requires active re-authentication, even if the user already logged in earlier |
| `max_age=300` | Caps authentication age at around 5 minutes |
| `max_age=900` | Caps authentication age at around 15 minutes |

Key distinction: `max_age` concerns **authentication freshness**, not the HTTP session lifetime at the RP, and it does **not** directly alter the TTL of access tokens or ID tokens.

### 4.2. Mandatory Role of the `auth_time` Claim

When the Authentication Request contains `max_age`, **the returned ID token must include the `auth_time` claim** per OIDC Core. `auth_time` is the time at which the OP authenticated the user, represented in seconds since the Unix epoch.

Abbreviated example ID token payload:

~~~json
{
  "iss": "https://idp.example.com/realms/company",
  "sub": "user-9841",
  "aud": "portal-web",
  "iat": 1760000900,
  "exp": 1760004500,
  "auth_time": 1760000700
}
~~~

**`iat` does not replace `auth_time`.**

- `iat`: time **the ID token was issued**.
- `auth_time`: time **the user was actually authenticated** at the OP.

A user may have authenticated long ago yet just received a newly issued ID token; looking only at `iat` will not reveal whether the authentication event itself is too old.

For sensitive operations, the RP needs to validate the ID token and apply a freshness policy based on `auth_time`. If `auth_time` is missing even though the RP requested `max_age`, or fails the acceptance threshold, the application must not assume the fresh authentication requirement was met.

Example verbal policy:

> Only allow changing the payment method when `auth_time` is within the last 5 minutes, accounting for allowed clock skew and token validation rules.

Typically, the RP must also ensure a mechanism to re-trigger the OIDC Authentication Request when the threshold is not met; simply having a Spring Security session at the Portal **does not automatically make the browser start a new authentication flow** whenever the user opens a sensitive screen.

### 4.3. How Are `max_age=0` and `prompt=login` Similar and Different?

Both can cause the OP to require re-authentication, but they differ in the verifiable information produced:

- `prompt=login` expresses an **interactive behavior** request: please re-authenticate.
- `max_age=0` sets a strict freshness threshold, triggering re-authentication and obligating `auth_time` in the ID token.
- `max_age=300` allows using a sufficiently recent authentication result without forcing the user back through credential entry.

In systems that must prove authentication freshness, design around `max_age` + `auth_time`, alongside proper token validation. You can combine `prompt=login` for the desired UX, yet it does not replace freshness verification.

### 4.4. `max_age` Does Not Equal SSO Session Expiration

Suppose the OP has an SSO session lasting several hours. The Portal requests `max_age=300`:

- If the OP authenticated the user 2 minutes ago, the current session can be used.
- If the OP authenticated the user 20 minutes ago, the OP must re-authenticate per the request.
- After logging into the Portal, the Portal's HTTP session may have a different lifetime than the OP's SSO session.

Each layer has its own clock and rules: **OP authentication**, **RP session**, **ID token**, **access token**, **refresh token**. Never use a token's expiration time as a proxy for when the user last authenticated.

## 5. `login_hint`: Suggesting an Account, Not Asserting Identity

`login_hint` is a string sent by the RP to the OP to **suggest which account the user might want to log in with**.

Example:

~~~text
login_hint=alice%40example.com
~~~

The OP may use this hint to pre-fill the email, pre-select an account, or skip entering a username. However:

- This is only a **hint**, not a requirement forcing the OP to use it.
- The OP may ignore, transform, or handle it in its own way.
- The RP **must not** treat `login_hint` as proof that the user actually authenticated under that identity.
- After the callback, trusted identity must come from the **validated ID token**, typically the `iss` + `sub` pair.

### 5.1. Appropriate Usage Scenario

For example, the Portal has an email entry step to look up enterprise login options. The user enters `alice@example.com`; the Portal redirects to the OP with `login_hint`. The OP may pre-display that address, while the user still completes authentication under the OP's flow.

`login_hint` **improves UX**; it does not replace verifying email ownership or validating the ID token.

### 5.2. Security and Privacy Notes

An email or identifier in `login_hint` can appear in redirect URLs and may be recorded in browser history, proxies, or logs if systems are not configured carefully. Therefore:

- Send only necessary data supplied by the user or a valid workflow.
- Never put passwords, access tokens, OTP codes, or other secrets into `login_hint`.
- URL-encode the value properly using a URI handling library.
- Never automatically trust a browser-passed `login_hint` to link or switch internal accounts.
- Avoid logging full Authorization Requests containing sensitive data in application logs.

### 5.3. `login_hint` vs. `id_token_hint`

OIDC also defines the `id_token_hint` parameter to hint about **an authentication session / End-User previously known via an ID token**. This differs from the user-entered account string in `login_hint`.

| Parameter | Typical Data | Purpose |
|---|---|---|
| `login_hint` | Email, username, or identifier understood by the OP | Suggests an account for the authentication UI |
| `id_token_hint` | A previously issued ID token | Hints to the OP about the related End-User/session in an OIDC context |

Do not confuse `id_token_hint` with an access token; when using it, follow OP requirements and avoid leaking tokens. Neither parameter **allows the RP to skip validating the new callback result**.

## 6. Account Selection in SSO Applications

### 6.1. Why Is "Select Account" a Separate Problem?

A browser may remember multiple accounts at the OP. If the Portal only starts the default OIDC flow, the OP may immediately reuse the current SSO session.

That is convenient when the user wants to continue with the previous account, yet confusing when they want to open the Portal with a different account. `prompt=select_account` asks the OP to let them choose.

Example:

- The OP holds accounts `alice@company.example` and `alice.personal@example.com`.
- The user wants to open the Portal with their work account.
- The Portal initiates an OIDC Authorization Request with `prompt=select_account`.
- The OP handles account selection according to its capabilities.
- The Portal receives the callback, validates the ID token, and creates a local session keyed on **`iss` + `sub` of the actual account**.

Separate **display labels** from **identity keys**. An email can change or remain unverified by the OP; `sub` scoped to the issuer is appropriate for identifying the logged-in account.

### 6.2. Switching Accounts at the OP and Portal Do Not Sync Automatically

At least two kinds of state exist:

1. **Login session at the Portal (RP):** typically holds `SecurityContext` and servlet session state.
2. **SSO session at the OP:** managed by the OP, able to exist independently of the Portal session.

If the user clicks "Switch account":

- The Portal must decide how to terminate or replace the current local session to avoid mistakenly retaining data from the previous user.
- Start a new OIDC login request with `prompt=select_account` if supported by the OP.
- When the callback succeeds, verify the received identity and establish application state for the new account.
- Clarify how `OAuth2AuthorizedClient` / tokens are keyed by principal so tokens from account A are never sent after switching to B.
- Handle user cancellation or OP error responses without accidentally bridging data between two accounts.

**Do not assume** that calling the Portal's logout endpoint logs out all accounts at the OP. If business rules require logging out at the OP, use an OP-supported OIDC logout mechanism and manage session policies explicitly.

### 6.3. Passing `login_hint` Alone Is Not an Account-Switching Mechanism

Suppose the Portal sends:

~~~text
login_hint=bob%40example.com
~~~

Yet the OP currently holds an SSO session for Alice. The OP may ignore the hint and return Alice if policy allows. Thus, when the goal is **letting the user choose an account**, use `prompt=select_account` when appropriate and **verify the actual principal after callback**; never use `login_hint` as a command forcing a switch to Bob.

## 7. Complete Authorization Request

An example OIDC Authorization Code Request with account selection, freshness limit, and email hint:

~~~http
GET /authorize?response_type=code&client_id=portal-web&redirect_uri=https%3A%2F%2Fportal.example.com%2Flogin%2Foauth2%2Fcode%2Fcorp&scope=openid%20profile%20email&state=RANDOM_STATE&nonce=RANDOM_NONCE&prompt=select_account&max_age=300&login_hint=alice%40example.com&code_challenge=RANDOM_CHALLENGE&code_challenge_method=S256 HTTP/1.1
Host: idp.example.com
~~~

Main components:

| Parameter | Role |
|---|---|
| `response_type=code` | Selects the Authorization Code flow |
| `client_id` | Identifies the registered RP / OAuth client |
| `redirect_uri` | Callback registered at the OP |
| `scope=openid ...` | Requests OIDC and additional scopes |
| `state` | Binds request and callback; helps prevent CSRF |
| `nonce` | Binds the ID token to the authentication request per OIDC |
| `code_challenge` / `code_challenge_method` | PKCE parameters protecting the authorization code exchange |
| `prompt` | User interaction requirement |
| `max_age` | Upper bound on authentication age at the OP |
| `login_hint` | Login account suggestion |

`RANDOM_STATE`, `RANDOM_NONCE`, and `RANDOM_CHALLENGE` are illustrative placeholders only. In a real application, let Spring Security generate and manage these security values following the standard flow; never use fixed strings or build unvalidated custom callbacks.

### 7.1. What Is Handled at the OP vs. the RP

~~~mermaid
sequenceDiagram
    autonumber
    actor User as User
    participant Browser as Browser
    participant RP as Spring Boot RP
    participant OP as OpenID Provider
    User->>Browser: Choose login / switch account
    Browser->>RP: GET /oauth2/authorization/corp
    RP-->>Browser: Redirect Authorization Request (prompt, max_age, login_hint...)
    Browser->>OP: OIDC authentication request
    OP->>User: Authenticate, consent, select account if needed
    OP-->>Browser: Redirect with code and state or error
    Browser->>RP: Callback at /login/oauth2/code/corp
    RP->>OP: Exchange code for tokens
    OP-->>RP: ID token and other tokens per flow
    Note over RP: Validate ID token, auth_time if needed, identity iss + sub
    RP-->>Browser: Establish session and return Portal content
~~~

`prompt`, `max_age`, and `login_hint` are parameters sent **during the authorization step**. They are not headers sent on every API call, nor values the RP can modify after receiving an ID token expecting the OP to apply them retroactively.

## 8. Integration in Spring Security OAuth 2.0 OIDC Client

### 8.1. Configuring Client Registration

Add the OAuth 2.0 Client dependency to your Spring Boot application:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

Example `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          corp:
            issuer-uri: https://idp.example.com/realms/company
~~~

This is an example of a **confidential web client** keeping its secret server-side. `issuer-uri` lets Spring Security use the discovery metadata of a compatible OP; URIs and client details must be properly configured at the provider.

Login for registration `corp` is typically initiated via:

~~~text
/oauth2/authorization/corp
~~~

Default callback for the example configuration:

~~~text
/login/oauth2/code/corp
~~~

### 8.2. Adding `prompt` and `max_age` with an Authorization Request Resolver

Spring Security provides `DefaultOAuth2AuthorizationRequestResolver` to construct Authorization Requests. You can wrap the default resolver to add OIDC parameters while preserving framework-generated fields such as `state`, `redirect_uri`, `nonce`, and PKCE (when configured/used).

Example **policy applied across all OIDC logins of the illustrative application**: prompt account selection and require authentication within the last 5 minutes.

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestRedirectFilter;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OidcLoginSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ClientRegistrationRepository clientRegistrations) throws Exception {

        DefaultOAuth2AuthorizationRequestResolver delegate =
                new DefaultOAuth2AuthorizationRequestResolver(
                        clientRegistrations,
                        OAuth2AuthorizationRequestRedirectFilter
                                .DEFAULT_AUTHORIZATION_REQUEST_BASE_URI);

        OAuth2AuthorizationRequestResolver resolver =
                new OAuth2AuthorizationRequestResolver() {

                    @Override
                    public OAuth2AuthorizationRequest resolve(HttpServletRequest request) {
                        return customize(delegate.resolve(request));
                    }

                    @Override
                    public OAuth2AuthorizationRequest resolve(
                            HttpServletRequest request, String registrationId) {
                        return customize(delegate.resolve(request, registrationId));
                    }
                };

        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(login -> login
                        .authorizationEndpoint(endpoint -> endpoint
                                .authorizationRequestResolver(resolver)))
                .build();
    }

    private static OAuth2AuthorizationRequest customize(
            OAuth2AuthorizationRequest original) {

        if (original == null || !original.getScopes().contains("openid")) {
            return original;
        }

        return OAuth2AuthorizationRequest.from(original)
                .additionalParameters(parameters -> {
                    parameters.put("prompt", "select_account");
                    parameters.put("max_age", "300");
                })
                .build();
    }
}
~~~

Explanation:

1. `delegate.resolve(...)` preserves how Spring Security determines client registration, redirect URI, scopes, and flow-protection parameters.
2. `OAuth2AuthorizationRequest.from(original)` creates a builder from the constructed request so only the needed parameters are added.
3. `additionalParameters(...)` adds `prompt` and `max_age` to the Authorization Request sent to the OP.
4. Checking the `openid` scope limits customization to OIDC requests.
5. On callback, Spring Security still handles Authorization Code / OIDC Login using the framework's standard mechanisms.

This snippet uses Spring Security 6 servlet APIs and Java running on `jakarta.servlet`. In environments with multiple providers or multiple flow types, apply policies per **registrationId / business workflow** rather than unconditionally setting `select_account` on every login.

### 8.3. Varying Policy by User Journey

Not every action needs the same set of parameters:

| Journey | Intent | Example Parameters |
|---|---|---|
| Normal login | Reuse SSO if valid | No need to force `prompt` |
| User clicks "Switch account" | Let user pick identity | `prompt=select_account` |
| Changing sensitive data | Require sufficiently fresh auth | `max_age=300`, paired with checking `auth_time` |
| Requesting new permission scopes | Prompt for consent | `prompt=consent` with appropriate scopes |
| Suggesting an entered email | Reduce typing | `login_hint=...` |
| Attempting non-interactive flow | Succeed only if no UI needed | `prompt=none` with proper error handling |

For multiple workflows, you can write a custom `OAuth2AuthorizationRequestResolver` driven by controlled routes or trusted session state. **Never forward arbitrary query parameters sent by the user in the browser verbatim** into `prompt`, `max_age`, or `login_hint` without allowlisting, value validation, and policy checks.

For instance, appending `?prompt=none` to a Portal URL **does not mean** Spring Security will automatically forward that value unchanged to the OP. Only when the application deliberately constructs or modifies the Authorization Request are those parameters sent.

### 8.4. Reading `auth_time` After Login

In Spring Security, the OIDC principal can be accessed as `OidcUser`. Example endpoint to **inspect** the authentication timestamp placed by the OP into the ID token:

~~~java
import java.time.Instant;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SessionInfoController {

    @GetMapping("/session-info")
    SessionInfo sessionInfo(@AuthenticationPrincipal OidcUser user) {
        return new SessionInfo(
                user.getIdToken().getIssuer().toString(),
                user.getIdToken().getSubject(),
                user.getIdToken().getAuthenticationTime());
    }

    record SessionInfo(String issuer, String subject, Instant authTime) {}
}
~~~

`authTime` may be `null` if the OIDC request did not ask for that claim. When policy requires `max_age`, the RP must ensure a valid `auth_time` is present and verify the threshold when a sensitive operation runs; **merely displaying this information is not an authorization mechanism**.

Depending on version and integration, the framework handles many core ID token checks, yet the application must still implement **re-triggering login flows and enforcing business freshness policies**. Never assume an active HTTP session means `auth_time` is still fresh enough.

## 9. Error Handling and Edge Cases

### 9.1. User Declines Consent

The OP may return:

~~~text
error=access_denied
~~~

The Portal must display an appropriate message and not treat the permission request as successful. If the new scope was optional, the application can continue with limited functionality; if mandatory, explain that the action cannot be performed.

### 9.2. `prompt=none` Cannot Be Satisfied

Examples:

~~~text
error=login_required
~~~

or:

~~~text
error=consent_required
~~~

This can be a **normal outcome of a silent SSO check**. The application must not infinitely retry the same `prompt=none` request. If the user wants to proceed, trigger an appropriate interactive login flow.

### 9.3. User Picks a Different Account from the Hint

If the Portal passes `login_hint=alice@example.com` yet the OP authenticates Bob, the Portal must handle **Bob's identity per the valid ID token**, never using Alice's hint to look up Alice's data or tokens. If the application requires a specific account, apply trusted identity-matching rules and reject or guide the user when they do not match.

### 9.4. OP Does Not Support the Requested Interaction

Some providers support only a subset of `prompt` values, or behave differently depending on client type, tenant configuration, and login policies. The RP needs to:

- Check capabilities published in OP documentation and metadata when available.
- Handle error callbacks through Spring Security's mechanisms; do not treat every error as invalid credentials.
- Avoid building a "switch account" flow on the assumption that the OP is guaranteed to show an account chooser.

### 9.5. Continuous Fresh-Authentication Prompts

If the Portal always sends `max_age=0` on every visit or triggers fresh authentication whenever a page reloads, users may get stuck in repeated redirects and logins. Apply the policy only to operations requiring protection and start a new interactive flow only when genuinely needed.

## 10. Applied Scenarios

### Scenario A: Switching the Active Account

A user is logged into the Portal with a work account and wants to switch to a personal account.

**Design:** The Portal offers a "Switch account" action, prepares to replace the local login state per policy, and starts OIDC Login with `prompt=select_account`. After the callback, the Portal uses `iss` + `sub` from the valid ID token to establish the actual account.

**Avoid:** sending a different `login_hint` and switching the internal user without validating the callback.

### Scenario B: Re-Verifying Before Changing Password or Payment Method

The Portal requires the user to have authenticated within the last **5 minutes**.

**Design:** When needed, start a new OIDC request with `max_age=300`. Once the OP returns, validate the ID token and check `auth_time` against system timing rules before permitting the action. Prevent an old HTTP session from bypassing the freshness policy.

**Avoid:** using `iat` of a new ID token in place of `auth_time`, or assuming `prompt=login` alone proves a 5-minute policy.

### Scenario C: Requesting Additional Profile Read Permissions

The Portal already has a login session but needs a new scope.

**Design:** Build an Authorization Request with the required scopes and ask for consent if OP/app policy requires it, such as `prompt=consent`. Handle user decline gracefully. Only call APIs using an access token with the proper permissions.

**Avoid:** treating an ID token or the presence of a consent screen as proof of API access rights.

### Scenario D: Passing an Entered Email to the OP

The user enters an email before clicking the login button.

**Design:** Validate input format appropriately, encode properly when building the URL, and send `login_hint`. After callback, the Portal must determine identity from the verified token.

**Avoid:** using the email in `login_hint` as the user-identification key even when ID token claims indicate a different subject.

## 11. Self-Check Quiz

**Question 1.** The Portal wants to display no interactive steps at all and accept an error if the OP cannot handle it silently. What should it request?

**Answer:** `prompt=none`. Errors like `login_required` or `consent_required` must be handled, with a fallback to interactive login when appropriate.

**Question 2.** The Portal requires the user to have authenticated recently; why not use only the ID token's issued-at timestamp?

**Answer:** `iat` is only when the token was issued, whereas `auth_time` is when the OP authenticated the user. Use `max_age` and verify `auth_time` for freshness policies.

**Question 3.** Can you send `prompt=none login` so the OP silently tries SSO and shows login if that fails?

**Answer:** No. `none` must not be combined with any other `prompt` value. The two experiences must be orchestrated via separate requests based on the OP's response.

**Question 4.** The Portal sends `login_hint=alice@example.com` yet a valid ID token returns Bob's `sub`. Who just logged in?

**Answer:** Identity is determined by `iss` and `sub` in the verified ID token. `login_hint` is only a suggestion and does not prove Alice logged in.

**Question 5.** The user is already logged in, but the application wants them to approve an additional scope. Which parameter is appropriate?

**Answer:** You can request `prompt=consent` along with the desired scope. The OP decides how to present consent per policy; the application must handle decline.

## Takeaways

- **Consent** is approval of permission/data scopes; it differs from identity authentication.
- **`prompt`** guides interaction at the OP: `none`, `login`, `consent`, and `select_account`. `none` must stand alone.
- **`max_age`** requests authentication freshness in seconds; **`auth_time`** in the ID token lets the RP check the actual time the OP authenticated the user.
- **`login_hint`** only provides an input suggestion and never replaces identity verified through **`iss` + `sub`**.
- In **Spring Security**, you can add these parameters via `OAuth2AuthorizationRequestResolver`, while preserving the standard OIDC Authorization Code flow and applying policies per business journey.
