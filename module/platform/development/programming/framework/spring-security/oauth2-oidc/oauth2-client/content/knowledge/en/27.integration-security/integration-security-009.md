# 27.9. Consent Management, Incremental Authorization, and Reauthentication

## 1. Why Manage Consent After a User Has Already Logged In?

In a **Spring Security OAuth 2.0/OIDC Client** application, a successful login does not mean the application is permitted to use every API of a provider, and an active login session is not necessarily fresh enough or strong enough for sensitive actions.

Example of a work portal:

```text
09:00 User logs in via OIDC
      scope: openid profile email
      -> views dashboard and profile

09:20 User clicks "Sync calendar"
      -> app requests additional calendar.readonly
      -> IdP displays consent if needed
      -> app receives new authorization

10:00 User clicks "Change payout details"
      -> app requires reauthentication
      -> verifies auth_time, assurance, and internal policy
      -> only then allows modifying data
```

There are three **distinct** decisions:

1. **Authentication:** Who is using the application? When were they authenticated and by what method?
2. **OAuth2 authorization/consent:** Which resources and scopes have the user and Authorization Server (AS) allowed the **OAuth2 client** to access?
3. **Business authorization:** Does the current internal account have permission to perform the business operation, such as viewing a calendar or editing payout details?

**Consent** does not replace authentication; **re-authentication** does not automatically grant new scopes; and an access token with the right scopes **does not replace business authorization** at the Resource Server.

### Learning Objectives

After this lesson, you will be able to:

- Distinguish consent screens, OAuth2 scopes, granted authorizations, roles, and application preferences.
- Design **incremental authorization**: requesting additional permissions only when the user invokes a feature requiring them.
- Understand that incremental authorization typically reuses the **Authorization Code Flow**, not a new OAuth2 grant type.
- Customize authorization requests in Spring Security via `OAuth2AuthorizationRequestResolver`.
- Use `prompt=consent`, `prompt=login`, `max_age`, `auth_time`, `acr_values`, and `amr` properly.
- Understand the differences among OIDC reauthentication, MFA/step-up, and refreshing a Spring Security session.
- Incorporate OAuth2 `state`, PKCE, OIDC `nonce`, CSRF, and account binding into privilege-elevation flows.
- Manage `OAuth2AuthorizedClient` and access/refresh tokens after scopes expand.
- Handle denied consent, partial scopes, `invalid_grant`, `insufficient_scope`, 401/403, and session expiration.
- Design a BFF without exposing raw tokens to the browser.
- Test both success scenarios and permission or identity-confusion failures.

All domains, client IDs, tokens, and scopes in examples are illustrative. Primary code snippets target **Spring Security OAuth2/OIDC Client on Servlet/MVC**; WebFlux has a dedicated section. API scope names are examples; verify against your real provider before implementation.

---

## 2. Four Permission Layers: Never Conflate Them

| Layer | Primary decision point | Example |
|---|---|---|
| **Authentication** | OIDC Provider/Spring Security | `sub=alice`, `auth_time=...` |
| **OAuth2 consent/authorization grant** | Authorization Server, user, and client policy | Client is allowed `calendar.readonly` |
| **Access token scopes/audience** | Issued by AS; verified by Resource Server | Token has `aud=calendar-api`, `scope=calendar.readonly` |
| **Business authorization** | Application/Resource Server | Alice can only view calendars in tenant A |

An access token with `calendar.readonly` does not prove Alice may view Bob's private calendar. Conversely, Alice having an admin role in the SaaS still cannot call a provider API if the client has not been issued a suitable access token by the AS.

### 2.1. Logging In Is Not Consenting to Every Resource

OIDC Login normally starts with:

```text
scope=openid profile email
```

These scopes cover authentication and profile claims. They do not automatically grant:

```text
calendar.readonly
drive.file
billing.write
```

API permissions must be requested via OAuth2 authorization for the **right provider, client, audience, and resource**.

### 2.2. Consent Differs from an "I Agree to Terms" Screen

Distinguish:

- **OAuth2 authorization consent:** User grants the client permission to access APIs/resources via the AS.
- **Terms of Service acceptance:** Accepting the application's terms.
- **Privacy preferences:** Configuring data-processing choices inside the application.
- **Business approval:** An administrator assigning a role or approving a transaction.
- **Step-up authentication:** User re-proving identity or assurance level before a sensitive action.

Never replace a provider's OAuth2 consent with an in-app checkbox and treat it as equivalent to holding an access token.

### 2.3. Consent Is Not Fully Captured by `Authentication`

An `OAuth2AuthenticationToken` indicates the user logged in, yet it does not guarantee the authorized client holds all needed scopes. Check the **actual access token** and authorization state.

---

## 3. Who Controls Consent?

An Authorization Server governs granting authorization based on:

```text
End-User
    +
OAuth2 client
    +
Requested scopes/resources
    +
AS policy, administrator policy, and consent history
```

The AS may:

- Show the consent screen on first use.
- Skip the screen if consent is already saved.
- Re-prompt for consent when new scopes are requested.
- Reject permissions blocked by organizational policy.
- Grant only a subset of requested permissions if the provider supports granular consent.
- Require admin consent or a verified application.
- Omit a refresh token even when the user consented.

**Spring Security cannot force the AS to grant permissions merely by adding scopes to a request.** The client can only **request**; the AS and user/policy decide what is granted.

### 3.1. What the Application Should Store

The application can store **business metadata** explaining state:

```text
internalUserId
providerRegistrationId
feature = CALENDAR_SYNC
consentFlowStatus = CONNECTED / NEEDS_CONSENT / REVOKED
lastSuccessfulAuthorizationAt
authorizedClientReference
```

However, a `CONNECTED` status in the DB is **not the absolute source of truth** on whether the token is still valid. Consent may have been revoked directly at the provider without the app being notified yet.

### 3.2. The Authorization Server Issues Tokens

You cannot fabricate:

```json
{
  "scope": "calendar.readonly"
}
```

inside an app JWT or session attribute and claim the API provider allowed it.

Tokens must be issued by the trusted AS with the right audience/scope/issuer and verified by the Resource Server.

---

## 4. What Is Incremental Authorization?

**Incremental authorization** is the strategy of **requesting additional permissions only when a specific feature requires them**, rather than asking for a broad set of scopes upfront at login.

Example:

```text
Step 1: User sign-in
    openid profile

Step 2: User clicks "Connect Calendar"
    calendar.readonly

Step 3: User clicks "Create Event"
    calendar.events.write
```

These three grants do not necessarily yield three coexisting access tokens. A provider may merge granted scopes into one authorization, issue a new token with combined scopes, or handle tokens/refresh tokens differently per its contract.

### 4.1. Why Is It Better Than Requesting Everything Upfront?

- Users see permission prompts **in the context of use**.
- Reduces unnecessary application privileges.
- Lowers onboarding friction.
- Supports the principle of least privilege.
- Makes it easy to explain impact when a user declines.
- Allows features not needing sensitive permissions to work normally.

### 4.2. Incremental Authorization Is Not a New Grant Type

OAuth2 has no:

```text
grant_type=incremental_authorization
```

for this common pattern.

Typically, the application **initiates a new Authorization Code Flow**, requesting new scopes or combining existing scopes, with provider-specific parameters if needed.

Illustrative authorization request:

```http
GET /authorize?
    response_type=code
    &client_id=portal-client
    &redirect_uri=https%3A%2F%2Fportal.example%2Flogin%2Foauth2%2Fcode%2Fcorporate
    &scope=openid%20profile%20calendar.readonly
    &state=RANDOM_STATE
    &code_challenge=RANDOM_PKCE_CHALLENGE
    &code_challenge_method=S256
```

Line breaks are for readability; the real URL must be properly URL-encoded and belong to an AS-approved client registration.

### 4.3. The OAuth2 Client Must Inspect Which Scopes Were Actually Granted

Never assume:

```text
I just requested calendar.readonly
    => The returned token definitely has calendar.readonly
```

The AS may return:

- All requested scopes.
- A subset.
- A different scope set per policy.
- `access_denied` or a policy error.

The client must inspect the **actual scope grant** and gate features accordingly.

---

## 5. End-to-End Example: Dashboard, Calendar, and Payments

Suppose `https://portal.example` uses an OIDC Provider:

```text
Issuer: https://login.example-idp.com
Client registration: corporate
Client ID: portal-bff
```

Features:

| Feature | OAuth2 permissions needed | Authentication requirement |
|---|---|---|
| View dashboard | `openid profile` | OIDC Login |
| View calendar | `calendar.readonly` | Consent on first use |
| Create event | `calendar.events.write` | Additional consent |
| View internal transactions | Local role and API policy | Valid session |
| Change payout bank account | Does not necessarily need new scopes | Fresh re-authentication, possibly MFA |
| Export private data | API scopes and local policy | May require both consent and step-up |

An operation can require **both**:

```text
Consent for calendar.write
    +
Reauthentication with stronger assurance
```

These are two independent checks. If reauthentication passes yet the AS denies `calendar.write`, do not call the API. If scopes exist yet the user fails the step-up policy, disallow the sensitive operation as well.

---

## 6. Flow for Requesting Additional Scopes

```mermaid
sequenceDiagram
    autonumber
    actor U as User / Browser
    participant BFF as Spring Boot OAuth2 Client
    participant S as Session + Pending Intent Store
    participant AS as Authorization Server
    participant API as Calendar API

    U->>BFF: POST /api/connections/calendar/authorize
    Note over BFF: Verify session, CSRF, current account, feature policy
    BFF->>S: Save pending consent intent for account U
    BFF-->>U: Return safe same-origin authorization start URL
    U->>BFF: GET /oauth2/authorization/corporate
    BFF->>S: Bind intent to OAuth2 state, registration, scopes
    BFF-->>U: 302 /authorize with additional calendar.readonly scope + PKCE
    U->>AS: Authenticate/consent as required
    AS-->>U: Redirect code + state, or error
    U->>BFF: GET /login/oauth2/code/corporate
    BFF->>S: Validate state, PKCE, pending consent intent
    BFF->>AS: POST /token with authorization_code
    AS-->>BFF: Access token with granted scopes; refresh token if issued
    BFF->>BFF: Validate same intended user and scope outcome
    BFF->>S: Store/reconcile OAuth2AuthorizedClient
    BFF-->>U: Redirect /settings/calendar?result=connected
    U->>BFF: GET /api/calendar
    BFF->>API: Bearer token for Calendar API
    API-->>BFF: Calendar data
    BFF-->>U: Business JSON, no raw OAuth tokens
```

### 6.1. Do Not Start with Arbitrary Frontend Redirects

Maintain a **server-side feature-to-scope policy**:

```text
CALENDAR_READ -> calendar.readonly
CALENDAR_WRITE -> calendar.events.write
```

The frontend may select a feature:

```json
{"feature":"CALENDAR_READ"}
```

but **must never supply arbitrary scopes**, issuer URIs, or redirect URIs for the BFF to pass straight to the Authorization Server.

### 6.2. Consent Requests Must Have Explicit Intent

The server-side pending intent should store:

```text
intentId: opaque, random
internalUserId: stable local account ID
tenantId: validated tenant
registrationId: corporate
feature: CALENDAR_READ
approvedScopes: [calendar.readonly]
createdAt: ...
expiresAt: ...
consumed: false
expectedExternalIdentity: verified issuer+subject, if already known
oauthStateBinding: set during authorization request
```

Never let `intent` live forever. On callback, validate, consume atomically, and handle cases where the user logged out, the session changed, or another tab started a flow.

### 6.3. Login Callback and Consent Callback Can Share the Same URL

Spring Security OAuth2 Login typically handles:

```text
/login/oauth2/code/{registrationId}
```

for both initial sign-in and interactive reauthorization if the app uses the same `oauth2Login()` pipeline.

Therefore, callback handling must distinguish:

- **Initial login**.
- **Additional-scope consent** for an already logged-in user.
- **Reauthentication/step-up**.
- **Account linking** if also supported by the app.

Never infer this from a query parameter like `?action=consent` without server-side state/session binding.

---

## 7. How Does `prompt=consent` Differ from Additional `scope`?

In OIDC, the parameter:

```text
prompt=consent
```

asks the OpenID Provider to display an interaction so the user grants consent per its protocol and policy.

Yet to ask for new API permissions, the core requirement remains the **requested scopes**:

```text
scope=openid profile calendar.readonly
```

These parameters serve different purposes:

| Element | Purpose |
|---|---|
| `scope` | Expresses which permissions/claims/resources the client requests |
| `prompt=consent` | Asks the provider to interact with the user to confirm consent |
| `prompt=login` | Forces End-User reauthentication |
| `prompt=select_account` | Asks the user to choose a provider account |
| `prompt=none` | Show no UI; if interaction is needed, provider returns an error |
| `max_age` | Caps authentication age at the OP |
| `acr_values` | Communicates requested authentication context classes per OP contract |

**Never send `prompt=consent` on every API call.** It is an authorization endpoint parameter on an interactive authorization request, not a Resource Server header.

### 7.1. Does `prompt=consent` Always Display a Screen?

OIDC defines `prompt` semantics, yet actual behavior depends on the provider, policy, and interaction capabilities. Some providers display a screen, some return errors, and some enforce admin-consent policies.

Never build business logic assuming "the user definitely saw the exact dialog" without provider support and matching authorization results.

### 7.2. `prompt=consent` Does Not Override Policy

The AS may still deny `calendar.events.write` if the client is unauthorized to request it or a tenant admin blocked it. Forcing a consent prompt does not bypass AS policy.

---

## 8. Google-Specific Example: `include_granted_scopes`

Per Google OAuth2 documentation, an authorization request can pass:

```text
include_granted_scopes=true
```

to support Google's **incremental authorization**.

Conceptual example:

```text
GET https://accounts.google.com/o/oauth2/v2/auth
  ?client_id=...
  &response_type=code
  &scope=openid%20profile%20https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fcalendar.readonly
  &include_granted_scopes=true
  &state=...
  &redirect_uri=...
  &code_challenge=...
  &code_challenge_method=S256
```

Google can combine previously granted scopes with newly requested scopes per Google policy.

### 8.1. Do Not Apply Google Parameters to Every OIDC Provider

`include_granted_scopes` is **not a mandatory standard parameter across all OpenID Providers**. An enterprise provider may ignore it or reject the request with `invalid_request`.

Use a per-registration strategy:

```text
registration google:
    include_granted_scopes=true

registration corporate:
    send only parameters allowed by OIDC/RFC/provider docs
```

### 8.2. Never Assume Google Always Returns a New Refresh Token

During additional consent/reauthorization, Google does not guarantee every code exchange returns a new refresh token. Keep/rotate tokens per provider contract and do not wipe an existing valid refresh token solely because the new response omits that field, unless policy/SDK dictates otherwise.

### 8.3. `access_type=offline` Is Also Provider-Specific

In Google's OAuth2 web-server flow, `access_type=offline` relates to requesting refresh tokens. It is not a universal parameter understood by every Authorization Server.

Never write a global customizer that injects `access_type=offline` into every registration.

---

## 9. What Spring Security Manages vs. What the App Must Write

Spring Security OAuth2 Client can:

- Build authorization requests from `ClientRegistration`.
- Generate and verify `state`.
- Add PKCE via appropriate configuration/customizers.
- Handle redirects and authorization codes.
- Call the Token Endpoint.
- Validate OIDC ID Tokens per configuration.
- Create `OAuth2AuthenticationToken`/`OidcUser`.
- Persist `OAuth2AuthorizedClient` via repository/service.
- Refresh access tokens when allowed by provider/manager.
- Integrate tokens with `RestClient`/`WebClient`.

However, the application itself must decide:

- Which feature needs which scopes.
- Whether the user **intentionally** initiated additional consent.
- Which account/tenant owns the consent intent.
- Whether the post-callback ID Token matches the same user.
- Which scopes were actually granted and whether they suffice for the feature.
- How many minutes old reauthentication may be.
- Which MFA/ACR level fits business risk.
- How logout/disconnect/revocation and consent state are surfaced.
- Whether multiple distinct authorized clients/registrations must be persisted.

**There is no universal `incrementalAuthorization()` toggle** that handles all of those rules automatically.

---

## 10. Basic OIDC Login Configuration in Spring Boot

Spring Boot 3.x / Spring Security Servlet example:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
```

`application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: corporate-idp
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          corporate-idp:
            issuer-uri: https://login.example-idp.com
```

Initial scoping covers only login/profile. An API requiring `calendar.readonly` triggers a separate **interactive consent request** later if the user enables that feature.

**Do not dump every sensitive scope into the login registration just to avoid designing incremental authorization.**

### 10.1. Redirect URI Must Belong to the BFF or Client per Architecture

In a BFF:

```text
https://portal.example/login/oauth2/code/corporate
```

is the **Spring Security backend** callback, not an arbitrary frontend route or user-supplied host.

### 10.2. Keep Client Secrets on the Backend

Never embed `client-secret`, access tokens, or refresh tokens in JavaScript bundles, HTML bootstrap payloads, or browser storage.

---

## 11. `DefaultOAuth2AuthorizationRequestResolver`

Spring Security Servlet provides:

```java
org.springframework.security.oauth2.client.web
    .DefaultOAuth2AuthorizationRequestResolver
```

implementing:

```java
OAuth2AuthorizationRequestResolver
```

It constructs `OAuth2AuthorizationRequest` from the HTTP request and client registration. You can attach a customizer:

```java
setAuthorizationRequestCustomizer(
    Consumer<OAuth2AuthorizationRequest.Builder>
)
```

### 11.1. Illustrative Example Only: Always Adding `prompt=consent`

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestResolver;

@Bean
OAuth2AuthorizationRequestResolver authorizationRequestResolver(
        ClientRegistrationRepository registrations) {

    DefaultOAuth2AuthorizationRequestResolver resolver =
        new DefaultOAuth2AuthorizationRequestResolver(
            registrations,
            "/oauth2/authorization"
        );

    resolver.setAuthorizationRequestCustomizer(
        builder -> builder.additionalParameters(
            params -> params.put("prompt", "consent")
        )
    );

    return resolver;
}
```

This illustrates **how to add an OIDC parameter**. **Do not enforce `prompt=consent` globally in production** without an explicit requirement, as it causes consent fatigue and repeatedly interrupts logins with UI prompts.

### 11.2. Wiring the Resolver into OAuth2 Login

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestResolver;

@Bean
SecurityFilterChain securityFilterChain(
        HttpSecurity http,
        OAuth2AuthorizationRequestResolver resolver)
        throws Exception {

    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/", "/assets/**", "/error").permitAll()
            .anyRequest().authenticated()
        )
        .oauth2Login(oauth2 -> oauth2
            .authorizationEndpoint(endpoint -> endpoint
                .authorizationRequestResolver(resolver)
            )
        )
        .oauth2Client(Customizer.withDefaults());

    // CSRF protection remains enabled.
    return http.build();
}
```

Here `resolver` is the bean from Section 11.1, or replaced with an **intent-driven** custom resolver in the next section.

### 11.3. Never Modify Authorization URIs by Arbitrary String Concatenation

Avoid:

```java
authorizationUri + "?scope=calendar.readonly&state=abc"
```

as it easily:

- Overwrites the Spring Security-generated `state`.
- Drops PKCE/`nonce`.
- Breaks URL encoding.
- Sends unapproved scopes/redirect URIs.
- Breaks callback validation.

Use `OAuth2AuthorizationRequest.Builder`/resolvers so the framework keeps handling the protocol.

---

## 12. Changing Scopes per Feature: A Controlled Custom Resolver

A `DefaultOAuth2AuthorizationRequestResolver` can be **wrapped** to add scopes only within a backend-approved flow.

### 12.1. Intent Data Model

Example **application-owned** interfaces (not Spring Security):

```java
public interface ConsentIntentService {

    ConsentIntent findApprovedForCurrentRequest(
        HttpServletRequest request,
        String registrationId
    );

    void bindOauthState(
        ConsentIntent intent,
        String oauthState
    );
}
```

`ConsentIntent` needs at least:

```java
public record ConsentIntent(
    String id,
    String internalUserId,
    String registrationId,
    Set<String> approvedScopes,
    String feature,
    Instant expiresAt
) {}
```

`HttpServletRequest`, `Set`, and `Instant` have standard imports. **This service must be genuinely implemented** with session, CSRF, account binding, TTL, and transaction handling. Never deserialize a `ConsentIntent` from browser JSON and trust it as approved.

### 12.2. Illustrative Resolver Wrapper

```java
import java.util.LinkedHashSet;
import java.util.Set;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;

public final class IncrementalConsentRequestResolver
        implements OAuth2AuthorizationRequestResolver {

    private final OAuth2AuthorizationRequestResolver delegate;
    private final ConsentIntentService intents;

    public IncrementalConsentRequestResolver(
            ClientRegistrationRepository registrations,
            ConsentIntentService intents) {

        this.delegate =
            new DefaultOAuth2AuthorizationRequestResolver(
                registrations, "/oauth2/authorization"
            );

        this.intents = intents;
    }

    @Override
    public OAuth2AuthorizationRequest resolve(HttpServletRequest request) {
        OAuth2AuthorizationRequest original = delegate.resolve(request);
        return customize(request, original);
    }

    @Override
    public OAuth2AuthorizationRequest resolve(
            HttpServletRequest request,
            String registrationId) {

        OAuth2AuthorizationRequest original =
            delegate.resolve(request, registrationId);
        return customize(request, original);
    }

    private OAuth2AuthorizationRequest customize(
            HttpServletRequest request,
            OAuth2AuthorizationRequest original) {

        if (original == null) {
            return null;
        }

        // Custom service must bind intent to this session, user,
        // registration, and request. Never just read a query param.
        ConsentIntent intent = intents.findApprovedForCurrentRequest(
            request,
            requiredRegistrationId(original)
        );

        if (intent == null) {
            return original; // Normal login.
        }

        Set<String> scopes = new LinkedHashSet<>(
            original.getScopes()
        );
        scopes.addAll(intent.approvedScopes());

        OAuth2AuthorizationRequest modified =
            OAuth2AuthorizationRequest.from(original)
                .scopes(scopes)
                .additionalParameters(params -> {
                    if ("google".equals(intent.registrationId())) {
                        params.put(
                            "include_granted_scopes", "true"
                        );
                    }
                })
                .build();

        // Keep Spring's generated OAuth2 state; the service
        // binds the pending intent rather than replacing state.
        intents.bindOauthState(intent, modified.getState());

        return modified;
    }

    private String requiredRegistrationId(
            OAuth2AuthorizationRequest request) {
        // Extract registration ID from trusted authorization request
        // attributes/app routing. NEVER infer from scope or free browser query.
        throw new UnsupportedOperationException(
            "Implement trusted registration resolution"
        );
    }
}
```

**This is an extension-point skeleton**, not copy-paste production code: `requiredRegistrationId` needs an implementation reading trusted app registration routing/attributes. Never deploy an `UnsupportedOperationException` stub as a live endpoint.

Goals of this code:

1. Preserve the framework-built authorization request.
2. Add policy-approved scopes, never user-supplied scopes.
3. Preserve `state`/PKCE/`nonce` and required attributes.
4. Add Google-specific parameters only for the Google registration.
5. Bind the pending intent to `state` for callback validation.

### 12.3. Avoid One Shared Session Variable Across Tabs

Wrong:

```text
session.pendingScope = "calendar.readonly"
```

When two tabs request permissions for two features simultaneously, the value gets overwritten.

Better:

```text
intentId -> user/session/registration/feature/expiry
OAuth2 state -> intentId
```

with single-use semantics, expiration, and proper transactions/checks.

### 12.4. Do Not Accidentally Drop the `openid` Scope

If the app uses OIDC Login, replacing the scope set with only:

```text
calendar.readonly
```

may stop the authorization request from behaving as OIDC Login.

When reauthorizing within the same OIDC registration, retain foundational scopes (`openid` and actually required scopes) per provider contract. With Google incremental authorization, grant-merging semantics are governed by the provider; still verify actual responses.

---

## 13. Policy for Starting Consent: POST First, Redirect Second

A cookie-session BFF should expose an endpoint to initiate the flow, e.g.:

```http
POST /api/features/calendar/connect
Cookie: SESSION=...
X-CSRF-TOKEN: ...
Content-Type: application/json

{"feature":"CALENDAR_READ"}
```

Backend performs:

1. Verify Spring Security Authentication.
2. Identify the trusted internal account/tenant.
3. Verify the feature is enabled for this tenant.
4. Map `CALENDAR_READ` to scopes via a server-side allowlist.
5. Confirm the user lacks the required permission or needs reauthorization.
6. Create the pending intent on the backend.
7. Return a **same-origin authorization start URL**, never an access token.
8. Frontend performs a top-level navigation to that URL.

Example response:

```json
{
  "authorizationStartUrl": "/oauth2/authorization/corporate"
}
```

### 13.1. Why Protect This POST with CSRF?

An external website must never be able to trigger a consent workflow or alter connection state for a BFF-authenticated user without explicit user action.

OAuth2 `state` correlates the callback with the authorization request, yet it **does not replace CSRF tokens on admin/account-settings POSTs**.

### 13.2. Never Let the Browser Pick Arbitrary Scopes

Anti-pattern:

```http
POST /api/authorize
{"scopes":["admin.write","billing.export","*"]}
```

with the backend forwarding them verbatim into the authorization request.

Right:

```text
Frontend feature = CALENDAR_READ
  |
  v
Backend policy -> allowed scopes for tenant/provider/feature
  |
  v
Authorization request with allowlisted scopes
```

### 13.3. Navigation Differs from XHR

OAuth2 authorization redirects require browser interaction with the IdP. Never initiate them with `fetch()` expecting `XMLHttpRequest` to render login/consent screens properly.

Typically:

```javascript
window.location.assign(
  "/oauth2/authorization/corporate"
);
```

after the backend confirms intent.

---

## 14. Post-Callback: Verify the Exact User and Granted Scopes

Additional consent usually begins when a user **already has a local session**. When the OAuth2 Login callback returns, Spring Security may construct a new `OAuth2AuthenticationToken`.

Danger point: the user may pick **a different IdP account** on the consent screen.

Example:

```text
Local session:
    internalAccount U = Alice

Intent:
    Alice wants to grant calendar.readonly

Provider account chooser:
    User accidentally selects Bob

Callback:
    OIDC identity = Bob
```

If the backend only checks "code exchange succeeded" and saves Bob's token under Alice's account, that is a **cross-account token binding** bug.

### 14.1. Must Enforce Identity Binding

With OIDC:

```text
expected (iss,sub) from previously linked identity
    ==
verified (iss,sub) from new ID Token
```

If they differ:

- Reject elevating permissions for Alice.
- Never auto-link Bob to Alice.
- Never silently switch the browser's local account.
- Never save Bob's `OAuth2AuthorizedClient` under Alice's `principalName`.
- Audit the event and display an error without leaking secrets.

If the provider is non-OIDC, use a stable provider user ID fetched from a trusted user endpoint, namespaced per provider instance.

### 14.2. The Callback Must Also Verify

- Valid OAuth2 `state` matching the pending intent.
- PKCE, client registration, and redirect URI per framework.
- OIDC ID Token issuer, audience, signature, expiry, and `nonce` per config.
- Pending intent is unexpired and unconsumed.
- Local account/tenant remains active.
- Granted scopes suffice for the feature.
- Provider remains permitted.
- No concurrent account switch/logout rendered the intent stale.

### 14.3. Never Use Email for Identity Binding

Emails can change, be unverified, or be recycled. OIDC `(iss,sub)` is a far stronger identity key; for pure OAuth2 providers, use a stable provider-namespaced user ID.

### 14.4. Do Not Switch the Authenticated Session to the Wrong Person

Interactive reauthorization occurs inside an existing session. Spring Security's OAuth2 login success flow may establish a new `Authentication`. Design your success handler/identity mapping so the post-callback local account remains the **exact account that started** the workflow.

Never read the current `Authentication` in a success handler assuming it is still the original internal account; it may already be the newly authenticated provider principal.

---

## 15. Granted Scopes: Requesting Does Not Guarantee Granting

Suppose the app requests:

```text
requestedScopes:
    openid
    profile
    calendar.readonly
    calendar.events.write
```

The AS may grant only:

```text
grantedScopes:
    openid
    profile
    calendar.readonly
```

Depending on the provider, this appears via token response `scope`, token metadata, or effective token permissions.

### 15.1. Reading Access Token Scopes in Spring Security

`OAuth2AuthorizedClient` exposes:

```java
OAuth2AccessToken token =
    authorizedClient.getAccessToken();

Set<String> scopes = token.getScopes();
```

Example check:

```java
import java.util.Set;

import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;

public boolean hasCalendarRead(
        OAuth2AuthorizedClient authorizedClient) {

    return authorizedClient != null
        && authorizedClient.getAccessToken() != null
        && authorizedClient.getAccessToken()
            .getScopes()
            .contains("calendar.readonly");
}
```

`OAuth2AccessToken#getScopes()` reflects the scopes Spring Security recorded from the token response/authorization. For providers with different semantics or resource-specific permissions, check against the exact provider contract.

### 15.2. `scope` in the Token Response May Be Omitted When Unchanged

OAuth2 token responses may omit `scope` if granted scopes equal requested scopes, depending on spec/implementation. Never write custom JSON parsing assuming the `scope` field is always present.

Spring Security's token response client and provider-specific converters handle responses per contract.

### 15.3. Feature-Enablement Rule

```text
if token has required scope
   and authorized client belongs to correct user/provider
   and token valid for target audience
   and local business policy allows:
       enable feature
else:
       show limited state or request consent
```

Never rely on a session boolean `consented=true` to bypass token checks.

---

## 16. `OAuth2AuthorizedClient` and Storage Issues After Consent

Spring Security provides:

```java
OAuth2AuthorizedClientRepository
OAuth2AuthorizedClientService
OAuth2AuthorizedClientManager
```

An authorized client is normally keyed by:

```text
(clientRegistrationId, principalName)
```

Example:

```text
("corporate", "alice-901")
    -> access token with scopes openid profile

After incremental authorization:
("corporate", "alice-901")
    -> access token with scopes openid profile calendar.readonly
```

However, whether to **replace, merge, or keep the old token** depends on the provider and how your repository/service behaves.

### 16.1. Never Manually Merge Raw Tokens

You cannot stitch two access tokens into one:

```text
Token A (profile)
+
Token B (calendar.readonly)
=
Token C (profile + calendar.readonly) // does not exist
```

Only the Authorization Server can mint that token. When a provider supports combined authorizations, **the AS** issues a token covering the granted scopes.

### 16.2. One Registration Usually Holds One Authorized Client per Principal

The default `OAuth2AuthorizedClientService` key `(registrationId,principalName)` may **overwrite** the previous token when a new authorization is saved under the same key.

If you need:

```text
profile access token for API A
calendar access token for API B
```

with differing audiences, expiries, or ownership, you may need **separate registrations** or custom token storage keyed by audience/resource/authorization ID.

### 16.3. Refresh Tokens May Rotate or Be Omitted

The AS may:

- Issue a new refresh token.
- Keep the existing refresh token.
- Omit a refresh token on scope-upgrade responses.
- Invalidate prior refresh tokens upon reauthorization.
- Require re-consent when permissions change.

There is no single universal policy. When a response lacks a refresh token, whether to retain or clear the old one depends on the **provider contract and authorization bindings**; never reuse an old refresh token for a different authorization if invalid.

### 16.4. Feature Token Caches Must Stay Synchronized

A UI showing `CALENDAR_READ` enabled while the backend holds a stale authorized client missing the scope causes consent loops or API 403s.

Ensure:

- New authorized clients save to the authoritative store.
- Caches evict/invalidate per registration/principal.
- Pod B never serves a stale authorized client from Pod A.
- Refresh token updates are atomic.
- Callbacks from old tabs never overwrite newer, broader-scoped tokens with older ones.

---

## 17. Never Use Refresh Tokens to Arbitrarily "Request Extra Scopes"

In OAuth2, the Refresh Token Grant may request a scope set equal to or narrower than the existing authorization per AS policy. **It is not a way to expand permissions never granted.**

Example:

```text
Current grant:
    openid profile

Client sends refresh token and requests:
    calendar.events.write
```

If the AS never granted that permission, refreshing cannot bypass consent.

**The standard path to new permissions** is a new interactive authorization request or another consent/authorization mechanism published by the provider.

### 17.1. `AuthorizedClientManager` Does Not Automatically Open Browser Consent

`OAuth2AuthorizedClientManager` handles loading existing authorizations, refreshing tokens, client credentials, or configured grants.

When an API returns:

```http
403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

the manager **does not automatically open a consent page in the browser**. Your app needs an explicit UX workflow:

```text
API insufficient_scope
  -> feature shows "Connect Calendar"
  -> user explicitly initiates consent
  -> Authorization Code Flow
```

Never turn every 403 into a reauthorization redirect, because 403 can also be a business authorization denial.

### 17.2. Bound Consent Retries

If the user denies permission, never enter a loop:

```text
consent denied -> redirect consent -> denied -> redirect ...
```

Re-prompt only when the user intentionally uses the feature requiring that permission, with clear messaging and anti-consent-fatigue rules.

---

## 18. Consent Denial and Partial Grants Are Normal Outcomes

Users may decline allowing an app to read their calendar or private data. This is not an error forcing retries.

UI example:

```text
"You can keep using the dashboard.
Calendar sync is disabled because calendar read access was not granted."
```

### 18.1. Cases to Handle

| Outcome | Appropriate behavior |
|---|---|
| User grants all scopes | Save authorization, enable feature if local policy allows |
| User grants partial scopes | Enable compatible parts; lock actions needing missing scopes |
| User denies completely | Keep core features working, allow retry when user chooses |
| Admin consent required | Inform user that admin approval is needed per provider workflow |
| Unverified client | Show proper guidance; never tell users to ignore security warnings |
| Provider returns interaction error | Explain clearly and offer controlled retry |
| User picks a different provider account | Reject binding; ask user to pick the right account |
| Token response omits refresh token | Handle online-only/reconnect per policy |
| Previously granted scope revoked | Clear connected status or ask for reauthorization |

### 18.2. Never Silently Fall Back to a Stronger Token

If the user denies `calendar.events.write`, never grab a service-admin token or another account's token to perform the action on their behalf.

That is a privilege escalation / confused-deputy vulnerability.

### 18.3. Never Treat Denied Consent as a Login Failure

If the user is already logged in with `openid profile`, declining an optional scope **must not destroy their entire local session**.

Separate the **authentication session** from **feature permission connection status**.

---

## 19. Reauthentication: Re-Verifying Identity Differs from Consent

**Reauthentication** requires the user to re-verify their identity with the OpenID Provider or application before a sensitive action.

Example:

```text
Alice logged in at 09:00
Alice requests to change payout bank account at 16:00

Policy:
    must have authenticated within 5 minutes
    MFA or trusted authentication context required
```

A session valid until 18:00 **does not mean** the latest IdP authentication is fresh enough for changing payout details.

### 19.1. `prompt=login`

OIDC allows:

```text
prompt=login
```

asking the OP to **reauthenticate** the End-User, even if an OP session exists.

This is not an OAuth2 `scope` and does not automatically grant API permissions.

### 19.2. `max_age`

OIDC:

```text
max_age=300
```

requires authentication at the OP to be no older than **300 seconds** per standard semantics. If older, the OP must attempt to reauthenticate the user.

Specifically:

```text
max_age=0
```

is semantically equivalent to `prompt=login` for reauthentication per OpenID Connect Core.

### 19.3. `auth_time`

When `max_age` is sent, the returned ID Token **must include the `auth_time` claim** per OIDC Core.

Example:

```json
{
  "iss": "https://login.example-idp.com",
  "sub": "alice-901",
  "aud": "portal-bff",
  "auth_time": 1979997600,
  "iat": 1979997900,
  "exp": 1980001500
}
```

`auth_time` is when the user was **last actively authenticated by the OP**, not when the new token was issued.

### 19.4. `iat` Does Not Replace `auth_time`

A newly issued ID Token with:

```text
iat = 16:00
```

does not prove the user entered a password/MFA at 16:00. The OP could have minted a new token from an SSO session authenticated at 09:00.

Check `auth_time` whenever policy requires freshness.

---

## 20. `prompt=consent` and `prompt=login` Are Not Equivalent

| Request parameter | Security question |
|---|---|
| `prompt=consent` | Is the user being asked to approve client access permissions? |
| `prompt=login` | Must the user reauthenticate with the OP? |
| `max_age=300` | Is authentication fresh within 300 seconds? |
| `acr_values=...` | Does the user need a specific authentication context? |
| `scope=calendar.readonly` | Is the client requesting calendar read permission? |

Examples:

```text
User has an active valid SSO session.
User requests additional calendar.readonly.
    -> May consent without logging in again.

User wants to change payout bank details.
    -> May re-log in without requesting new scopes.

User wants to export special data.
    -> May need both API scope consent and step-up.
```

### 20.1. Can Both Prompts Be Sent Together?

OIDC `prompt` is a space-delimited list, e.g.:

```text
prompt=login consent
```

if supported by the provider and policy genuinely requires both authentication and consent.

`prompt=none` **must never be combined with other prompt values**. Never send `none login` or `none consent`.

### 20.2. "Showed Login Screen" Does Not Prove MFA

`prompt=login` asks the OP to reauthenticate, yet that could use password, passwordless, or another method per OP policy.

If business risk demands MFA/phishing-resistant authentication, you also need an assurance contract, not just `prompt`.

---

## 21. Step-Up Authentication and Authentication Assurance

**Step-up authentication** raises confidence in identity/possession prior to a sensitive operation.

Example:

```text
Initial login:
    password + SSO session

High-risk action:
    passkey or MFA per corporate policy
```

Relevant OIDC claims/parameters:

| Element | Role |
|---|---|
| `acr` | Authentication Context Class Reference asserted by OP |
| `amr` | Authentication Methods References used during authentication |
| `acr_values` | List of authentication context classes requested by client |
| `auth_time` | Timestamp when OP authenticated the user |
| `max_age` | Freshness constraint |
| `prompt=login` | Reauthentication request |

### 21.1. `acr_values` Is a Request, Not Proof

Example:

```text
acr_values=urn:example:loa:high
```

is meaningful only if the OP/tenant publishes, supports, and assigns trustworthy semantics to `urn:example:loa:high`.

Never treat that string as a universal MFA standard level.

### 21.2. Must Verify Returned Claims

If the app sends:

```text
acr_values=urn:example:loa:high
```

yet the ID Token lacks the matching `acr` or the OP does not enforce the requirement, **do not elevate privileges**.

Depending on the use case, OIDC `claims` requests can mark `acr`/`auth_time` as essential, though provider support and enforcement must be tested.

### 21.3. `amr` Values Can Differ Across IdPs

`amr` values depend on specs and implementations. Never write:

```java
if (amr.contains("mfa")) {
    allowEverySensitiveAction();
}
```

without an agreed mapping/assurance policy per issuer and tenant.

### 21.4. Different Providers Can Offer Different Assurance Levels

If an internal account links Google and Workforce identities:

```text
OIDC Google login -> local account Alice
OIDC Workforce login -> local account Alice
```

both identities resolving to Alice **does not mean** both sessions carry equal authentication assurance.

High-risk operations may require reauthenticating via the Workforce provider or app-managed MFA per policy.

---

## 22. Verifying `auth_time` After Reauthentication

Suppose the backend requires:

```text
stepUpIntent:
    internalUserId = Alice
    requiredMaxAgeSeconds = 300
    requiredAcr = high, if supported by provider
    initiatedAt = server timestamp
    expiresAt = server timestamp
```

On callback, Spring Security verifies the ID Token per OIDC. The **application** must still enforce claim policy.

### 22.1. Conceptual Logic

```text
1. Verify callback matches the pending step-up intent.
2. New ID Token passed issuer/client validation.
3. (iss,sub) matches identity linked to internal account U.
4. auth_time is present per max_age requirement.
5. auth_time is sufficiently recent per freshness and clock skew policy.
6. acr/amr satisfy assurance policy if applicable.
7. Tenant/local account remains active.
8. Mark step-up satisfied solely for the required scope/session/transaction.
9. Consume pending intent to prevent replay.
```

### 22.2. Java Example Checking Freshness

```java
import java.time.Duration;
import java.time.Instant;

import org.springframework.security.oauth2.core.oidc.user.OidcUser;

public final class OidcFreshnessPolicy {

    public static boolean authenticatedRecently(
            OidcUser user,
            Instant now,
            Duration maxAge,
            Duration allowedClockSkew) {

        Instant authTime = user.getIdToken()
            .getClaimAsInstant("auth_time");

        if (authTime == null) {
            return false;
        }

        // Reject future timestamps beyond allowed clock skew.
        if (authTime.isAfter(now.plus(allowedClockSkew))) {
            return false;
        }

        Duration age = Duration.between(authTime, now);

        return !age.minus(allowedClockSkew).isNegative()
                ? age.compareTo(maxAge.plus(allowedClockSkew)) <= 0
                : true;
    }
}
```

This snippet **illustrates freshness only**; production needs a trusted clock source, skew policy, account/issuer binding, ACR/AMR checks, and full callback validation. If authentication must occur **after a specific initiation time**, also verify `auth_time` relative to the initiation/challenge timestamp per policy rather than only a broad max age.

### 22.3. `auth_time` Must Come from a Verified ID Token

Never accept:

```json
{"auth_time":"now"}
```

from browser JSON as MFA proof. Use only claims from framework- and policy-verified ID Tokens/OP responses.

### 22.4. Local Session Freshness Differs from OP Freshness

A local Spring session might be newly created after a silent login while the OP authenticated the user hours ago.

Conversely, an OP session might have a fresh authentication while the local app session belongs to a different internal account.

Verify **both account binding and auth freshness**.

---

## 23. Example `max_age` and `prompt=login` Request

An Authorization Request for OIDC step-up:

```http
GET https://login.example-idp.com/authorize?
  response_type=code
  &client_id=portal-bff
  &scope=openid%20profile
  &redirect_uri=https%3A%2F%2Fportal.example%2Flogin%2Foauth2%2Fcode%2Fcorporate
  &state=RANDOM_STATE
  &code_challenge=RANDOM_CHALLENGE
  &code_challenge_method=S256
  &prompt=login
  &max_age=0
```

In practice, `max_age=0` or `prompt=login` alone may suffice per OIDC semantics; sending both illustrates when policy/provider permits it. With `max_age`, the ID Token must include `auth_time`.

### 23.1. Request-Level Customization

If an app always requires reauthentication for a **specific registration**, configure the resolver/customizer for that registration.

However, **never apply `max_age=0` to every login request** if it forces constant reauthentication, destroying SSO value and hurting UX.

### 23.2. Never Take `max_age` from Browser URLs

An endpoint like:

```text
/step-up?max_age=9999999
```

must never let the user weaken policy.

The backend must map feature/transaction risk to trusted max-age and assurance requirements.

### 23.3. `login_hint` Is Only a UI Hint

You may send `login_hint` to help the OP pre-select the right account, yet it is **no proof** that the callback will return the right external identity.

Verify `(iss,sub)` after callback regardless.

---

## 24. `prompt=none` and Silent Authorization

OIDC allows:

```text
prompt=none
```

instructing the OP **to show no UI**. If authentication/consent cannot be satisfied silently, the OP returns an error.

Possible errors:

```text
login_required
consent_required
interaction_required
account_selection_required
```

Exact values can vary by provider and situation.

### 24.1. Silent Check Is Not Consent Bypass

If the user has not granted `calendar.readonly`, `prompt=none` cannot be used to bypass user interaction. The OP must enforce consent policy and may return `consent_required`.

### 24.2. Third-Party Cookie Restrictions

Silent sign-in techniques relying on hidden iframes and OP browser cookies can fail due to third-party cookie restrictions or browser privacy features.

A BFF server-side session does not guarantee OP SSO silent authorization succeeds; always have an interactive fallback.

### 24.3. Never Loop Infinitely

```text
prompt=none -> interaction_required
    -> fallback to explicit user action
```

Never resend silent requests indefinitely or auto-redirect to a consent prompt without user intent.

---

## 25. Reauthentication at a BFF Does Not Always Have to Go Through the OIDC Provider

An app can implement step-up via:

- OIDC reauthentication with `max_age`/`acr`.
- App-local passkey/MFA challenge.
- Password confirmation per policy.
- Transaction-specific confirmation.
- Out-of-band approval for ultra-sensitive operations.

Distinguish:

**Local step-up:** the app controls the extra verification itself and records the outcome server-side.

**OIDC step-up:** the app asks the OP for fresh authentication evidence, then validates ID Token claims.

Both can be appropriate depending on product/security policy.

### 25.1. Never Store an Unbounded `isAdmin=true` Boolean After Step-Up

If step-up was completed for `PAYMENT_CHANGE #834`, bind the result to:

```text
internalAccountId
sessionId or session epoch
transactionId
requiredAssurance
verifiedAt
expiresAt
usedOnce
```

A session attribute `stepUpPassed=true` lacking timeout/transaction binding turns a one-time check into long-lived privilege.

### 25.2. Session Fixation and Login Callbacks

Spring Security enforces session fixation protection per config. A reauthentication callback can alter `SecurityContext`/session attributes.

Design step-up to remain compatible with session migration and never take raw session IDs from URLs. If the callback replaces `Authentication`, preserve the right internal account and never turn reauthentication into an account switch.

### 25.3. Step-Up Does Not Replace Business Approval

A user who reauthenticates with MFA still cannot modify another tenant's data or promote their own account role.

---

## 26. BFF: The Browser Never Needs to Know OAuth2 Tokens

In the **Backend for Frontend** pattern, the browser holds:

```text
Cookie: SESSION=<opaque-session-id>
```

The backend holds:

```text
OAuth2AuthorizedClient
    accessToken
    refreshToken, if present
    clientRegistrationId
    principalName
```

### 26.1. Consent UI Simply Steers the Browser Through Redirects

```text
Browser:
    POST start-consent + CSRF
    top-level redirect to OP
    redirect back to BFF
    receive business UI response
```

Never return:

```json
{
  "access_token": "...",
  "refresh_token": "...",
  "id_token": "..."
}
```

to the frontend after incremental authorization.

### 26.2. Maintain CSRF Protection

Because the browser automatically sends the session cookie, endpoints initiating consent or step-up must be CSRF-protected whenever they mutate server-side pending intents or account authorization state.

`HttpOnly` does not stop same-origin scripts from calling APIs; you still need XSS defenses, CSP, trusted script handling, backend authorization, and step-up policies.

### 26.3. Cookie `SameSite` and OIDC Callbacks

When the OP redirects back to the BFF via top-level GET, `SameSite=Lax` is normally suitable. With `form_post` callbacks, cross-site POSTs may omit `Lax` cookies; design compatible cookie/response-mode handling.

Never disable `state` validation to work around lost callback sessions.

---

## 27. Separating API Consent from Identity Linking

A user may have:

```text
Internal Account U
    linked with Google identity G
    linked with Workforce identity W
```

**Linking** G/W for login does not mean permission to read Google Drive, Calendar, or Microsoft Graph.

Independent workflows:

| Workflow | Purpose |
|---|---|
| Link Google identity | Allow logging into internal account U via G |
| Consent `calendar.readonly` | Allow client to read G's calendar resources |
| Re-authenticate with Workforce | Prove W still controls identity and is fresh |
| Change local role | Business authorization per policy |
| Disconnect calendar integration | Remove/revoke OAuth2 authorized client |
| Unlink Google identity | Remove one login method from internal account U |

### 27.1. One Account with Multiple Google Identities

If one internal account U links two Google accounts, the default authorized client store keyed by `(registrationId,principalName)` cannot represent two concurrent authorized clients for the same registration.

Enforce one provider identity per registration or build a **custom store keyed by external identity/resource**.

### 27.2. Never Switch Accounts When Consent Picks a Different Provider Identity

If Alice is logged in as U yet the authorization dialog selects Bob, the app must reject it or require a separate explicit account-linking workflow with proof-of-control—never silently store Bob's tokens under Alice.

---

## 28. Multi-Tenant: Scopes and Consent Must Be Permitted per Tenant

Example:

```text
Tenant Alpha:
    Calendar sync permitted
    allowedScope = calendar.readonly

Tenant Beta:
    Calendar sync blocked by organization
```

Even if the AS grants `calendar.readonly` for a Tenant Beta identity, the app must never bypass **tenant business policy**.

### 28.1. Registration Must Match the Tenant

Never let a user pick:

```text
registrationId = tenant-beta-admin-client
```

inside a Tenant Alpha request, as that could cause the BFF to use another tenant's client credentials or scopes.

### 28.2. Consent State Must Be Tenant-Bound

Pending intent requires:

```text
tenantId
internalAccountId
registrationId
expectedIdentity
feature
approvedScopes
oauthStateBinding
```

Never infer tenant solely from email domain or bare `sub`.

### 28.3. Never Trust Dynamic Issuers Entered by the Browser

OIDC discovery from arbitrary issuer URLs risks SSRF and IdP mix-up. For consent/reauth, use only pre-onboarded and approved provider registrations.

---

## 29. Token Audience and Scope Are Not the Same Thing

An access token:

```json
{
  "iss": "https://login.example-idp.com",
  "sub": "alice-901",
  "aud": "calendar-api",
  "scope": "calendar.readonly"
}
```

differs from:

```json
{
  "iss": "https://login.example-idp.com",
  "sub": "alice-901",
  "aud": "billing-api",
  "scope": "billing.read"
}
```

Having the same scope name or the same End-User does not mean a token can be used against a different API.

### 29.1. May Require a Resource Indicator or Another Registration

A provider may require:

```text
resource=https://calendar-api.example
```

per RFC 8707 or a dedicated audience parameter.

Do not merely add a new scope and send the same token to every Resource Server.

### 29.2. Incremental Authorization Can Change Token Authorization Context

If new permissions belong to a different resource, the provider may not return one combined token covering both APIs. Design storage/registrations for **target audiences**, not just a single `Set<String> scopes`.

---

## 30. When an Access Token Lacks Scope: Handling Resource Server Responses

An API may return:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="calendar.readonly"
```

Per RFC 6750, `insufficient_scope` indicates the token lacks the required permission.

### 30.1. Never Blindly Trust Scope Headers from Upstreams

The BFF must never take an arbitrary string from `WWW-Authenticate` and pass it unchecked into an authorization request.

Map upstream errors to the backend's **feature-to-scope allowlist**.

### 30.2. Distinguish 401 and 403

| Outcome | Likely cause | Handling |
|---|---|---|
| 401 `invalid_token` | Token expired/revoked/invalid | Bounded refresh/reauthorization per provider policy |
| 403 `insufficient_scope` | Token lacks OAuth2 permission for API | Show consent CTA if feature is allowed |
| 403 business permission | User lacks access to resource | Do not request futile scopes to bypass |
| 403 tenant restriction | Organization disables feature | Do not allow re-consent to evade policy |
| 429 | API rate limited | Backoff/rate policy; do not trigger login flow |
| 5xx | Provider/resource unavailable | Bounded retry; do not loop consent |

### 30.3. Never Infinitely Auto-Retry the API After Consent

After new authorization:

1. Verify the access token carries the right scope/audience.
2. Confirm the authorized client was saved under the right principal.
3. Retry the API **with bounds** if the request is still valid.
4. Never blindly retry non-idempotent state-changing requests.
5. Return a clear error if the target API still rejects it.

---

## 31. Consent Management UI: Displaying True Permissions

A "Connected Apps" screen may display:

```text
Google Calendar
    Status: Connected
    Permissions: Read calendar
    Account: alice@example.com
    Last authorized: ...
    Actions: Reconnect | Disconnect
```

Display only data from **trusted local state reconciled with token/provider state**, without exposing raw tokens or excessive personal claims.

### 31.1. Never Claim "User Consented Forever"

Consent can be revoked at the IdP. Access tokens expire; refresh tokens can rotate/revoke or tenant policies can change.

Better:

```text
Connection status = Active / Needs consent / Needs reconnect / Revoked / Error
```

and re-verify when calling the API.

### 31.2. Least Privilege

A calendar-reading feature must not request edit or delete permissions on calendar events. If the user needs write access later, request it in a separate workflow.

### 31.3. Explain Before Redirecting

Example:

> "To show your calendar on the dashboard, the app needs read access to events. You can continue using other features if you decline."

Never mislead users into thinking unrelated permissions are mandatory for basic functionality.

---

## 32. Revoking Consent and Disconnecting

A user can disconnect inside the SaaS or revoke access at the provider.

### 32.1. Disconnecting in the Application

Flow:

```text
POST /api/connections/calendar/disconnect + CSRF
    |
    +-- Authorization check for account/tenant
    +-- Mark connection as disconnecting
    +-- Block new usage
    +-- Remove authorized client / token records per policy
    +-- Call AS revocation endpoint if supported/permitted
    +-- Stop background sync jobs
    +-- Audit and notify
```

Deleting local records **does not automatically** revoke tokens at the AS. RFC 7009 describes token revocation when supported by the AS.

### 32.2. Revocation at the Provider

Users may revoke app access in the provider's account portal. The SaaS does not necessarily receive instant notification. Subsequent usage may encounter `invalid_grant` or `invalid_token`.

The application must handle this by:

- Stopping use of known-invalid credentials.
- Removing/marking the authorized client disconnected.
- Avoiding infinite refresh loops.
- Prompting user re-consent only when they want the feature.
- Ensuring background jobs stop spamming the API.

### 32.3. Logout Is Not Consent Revocation

- **BFF Logout:** ends the local session.
- **OIDC RP-Initiated Logout:** may end the OP session.
- **OAuth2 token revocation:** revokes access/refresh tokens if AS supports it.
- **Disconnect integration:** stops using permissions and clears local authorization.

These operations can be coordinated, yet they are not a single command.

---

## 33. Privacy and Data Minimization After Consent

Even after the AS grants a scope, the app must still:

- Fetch only required fields.
- Limit retention of provider-sourced data.
- Enforce backend user/tenant ownership checks.
- Never repurpose data beyond features the user understands.
- Enforce authorization on background syncing.
- Support disconnecting/deleting data per product policy and applicable law.
- Never log raw API responses containing private data.

Consent is one prerequisite for OAuth2 authorization, **not an unlimited license** for arbitrary data processing.

### 33.1. New Data Uses May Require New Consent UX

If `calendar.readonly` was granted solely to display a user's schedule, and later the app wants to analyze calendars for org-wide reports, re-evaluate privacy/purpose and user notice/consent per policy. Never assume an unexpired scope automatically authorizes any new purpose.

---

## 34. `SecurityContext` and Local Session After Step-Up

An OIDC step-up callback can succeed, yet the app must distinguish:

```text
OIDC Authentication from provider
    ->
Already-authenticated local account U
    ->
Step-up satisfied for operation O
```

If Spring Security processes the OIDC provider callback like a fresh login, `Authentication` may be replaced by a new provider principal. Remap cleanly to the **exact local account** so the session never accidentally switches users.

### 34.1. Never Assume the Session Holds the Same User After Redirect

Before redirect:

```text
Spring session -> Alice internal account U
```

After callback:

```text
OIDC principal -> may differ if account chooser picked Bob
```

Verify `(iss,sub)` and pending transaction binding before marking step-up satisfied.

### 34.2. Never Let Step-Up Become a New Admin Role

Never write:

```java
session.setAttribute("ROLE_ADMIN", true);
```

simply because MFA succeeded.

Step-up proves freshness/assurance; it does not grant business roles. Resource operations must still check roles/ownership.

### 34.3. Tokens Do Not Necessarily Need to Change During Step-Up

For an internal check before modifying payout details, the app may only need proof-of-fresh-auth without requesting new access token scopes. This avoids unnecessary authorization requests.

---

## 35. Reauth and Consent in Multi-Provider Systems

Providers differ in capabilities:

| Capability | Standard OIDC Provider | Pure OAuth2 | Vendor-Specific |
|---|---|---|---|
| `prompt=login` | Defined by OIDC | Not universal OAuth2 | Per docs |
| `max_age` / `auth_time` | Defined by OIDC | No standard ID Token | Per docs |
| `acr_values` | Defined by OIDC | Not universal | Per config/assurance policy |
| `prompt=consent` | Defined by OIDC | Not universal | May be custom |
| Incremental scopes | Uses authorization request/scopes | AS-dependent | May have extensions |
| `include_granted_scopes` | Not universal OIDC | Not universal | Supported by Google |
| Refresh token rotation | Per AS policy | Per AS policy | Needs testing |
| Admin consent | Per provider/organization | Per provider | May be mandatory |
| Partial consent | Provider-dependent | Provider-dependent | Needs testing |

### 35.1. Never Build One Universal `ProviderAuthorizationCustomizer` for All Providers

Unsafe example:

```text
Every provider:
    prompt=consent
    include_granted_scopes=true
    access_type=offline
    acr_values=mfa
```

Some providers reject unknown parameters, some interpret them differently, and some silently ignore them. Use registration-specific configuration and **contract tests**.

### 35.2. Tenant Policy Can Block Scopes

A provider allowing a client to ask for a scope does not mean the SaaS lets that tenant use the feature. Tenant authorization may forbid calendar integration, payment exports, or offline access.

Enforce this before initiating consent and before every downstream API call.

---

## 36. Securing Redirects, Scopes, and Prompt Customization

An attacker may try:

```text
GET /oauth2/authorization/corporate?scope=admin.write
GET /reauth?max_age=100000
GET /oauth2/authorization/corporate?redirect_uri=https://evil.example
```

If a custom resolver trusts those parameters, the BFF could:

- Request out-of-policy scopes.
- Weaken reauthentication freshness requirements.
- Send authorization codes to an attacker's redirect URI.
- Suffer login CSRF / authorization flow confusion.
- Send credentials to the wrong provider.
- Induce consent fatigue to social-engineer users.

### 36.1. Minimum Safeguards

1. Select registrations from an allowlist/trusted tenant context.
2. Select scopes from server-side feature policy.
3. Select `prompt`/`max_age`/`acr` from risk policy.
4. Preserve framework-managed `state`/PKCE/`nonce`.
5. Redirect only to registered callback URIs.
6. Bind pending intents to session/account, `state`, registration, and TTL.
7. Verify the same external identity after callback.
8. Verify granted scopes/`auth_time`/assurance, not just HTTP success.
9. Store tokens backend-only.
10. Audit and rate-limit repeated consent/reauth attempts.

### 36.2. Prevent Open Redirects

Never pass:

```text
return_to=https://attacker.example
```

and redirect post-callback without validation.

Allow only **same-origin relative paths** from an allowlist or server-side continuation IDs. Authorization response codes, `state`, and tokens must never leak via redirects/`Referer` logs.

### 36.3. Prevent Login CSRF and Mix-Up

With multiple issuers/`ClientRegistration`s, verify the callback matches the exact registration/issuer and initiated authorization request. An ID Token from issuer B must never be accepted as issuer A merely because subject or email matches.

---

## 37. Concurrent Refresh Token Rotation and Consent Scope Updates

Suppose a dashboard triggers concurrent requests:

```text
Existing authorized client:
    AT1 scopes: openid profile
    RT1

Request A:
    refresh RT1 -> AT2 / RT2

Request B:
    interactive consent -> AT3 scopes: openid profile calendar.readonly
    possibly RT3

Request C:
    load cached authorized client -> AT1
```

Without coordination, a late `saveAuthorizedClient` from Request A can **overwrite the newly saved authorized client from B** and wipe out the new scope.

### 37.1. Do Not Assume Storage Updates Are Atomic wrt Authorization Semantics

A store keyed by `(registrationId,principalName)` may be last-write-wins, unaware which response represents a newer authorization with expanded scopes.

### 37.2. Mitigation Approaches

- Version authorized clients / track authorization epochs if needed.
- Re-read current authorized client before conditional writes.
- Distinguish refreshing an older authorization from a new interactive authorization.
- Serialize refresh token rotation via per-client concurrency control.
- Never manually union scopes while keeping an old token if the AS didn't mint a matching token.
- If the new token belongs to another resource/audience, consider a distinct registration/storage key.
- When a user disconnects, prevent in-flight refreshes from writing tokens back.

### 37.3. Never Downgrade Authorizations via Stale Callbacks

An older open tab might finish consent for narrower scopes **after** another tab granted broader scopes.

The backend needs ordering/epoch policies for token storage so stale callbacks cannot overwrite newer authorizations unchecked.

---

## 38. OAuth2/OIDC Errors and UX Responses

| Error/symptom | Likely cause | Handling |
|---|---|---|
| `access_denied` | User declined consent or AS policy forbade it | Keep core session; report feature not connected |
| `consent_required` | Silent request lacked consent | Let user explicitly initiate interactive consent |
| `interaction_required` | OP requires interaction | Controlled top-level browser redirect |
| `login_required` | OP requires login/re-login | Start interactive login/reauth flow |
| `account_selection_required` | OP could not pick an account | Account chooser followed by identity-binding check |
| `invalid_scope` | Scope unsupported by provider/client | Fix config/policy; do not retry infinitely |
| `invalid_request` | Bad or unsupported customizer parameters | Check `prompt`/`max_age`/`acr`/provider docs |
| `invalid_grant` | Code/refresh token expired/replayed/revoked | Cleanup/reconnect, investigate rotation race |
| `invalid_client` | Client authentication failure | Alert backend, secret rotation/config |
| OIDC `auth_time` missing | `max_age` not sent/enforced, non-compliant OP | Do not mark step-up satisfied |
| OIDC `acr` insufficient | OP did not satisfy assurance policy | Reject sensitive action, guide proper reauth |
| Consent succeeds yet API 403 | Wrong scope/audience/ownership | Check token and Resource Server policy |
| Consent succeeds yet account changed | IdP account chooser selected different identity | Reject binding and keep right local account |
| CSRF 403 at start-consent | Missing/invalid CSRF token | Fix frontend CSRF flow; never disable CSRF |
| Callback `invalid_state` | Lost session, stale tab, state mismatch | Reject callback, restart with fresh intent |
| OAuth2 callback changes auth session | Login pipeline creates new authentication | Local principal mapping & pending flow |
| No new refresh token | Provider doesn't issue one on every consent | Follow contract; never assume |
| Consent loops | Stale token store, scope ungranted, AS policy | Inspect persisted authorized client & scopes |
| API returns 401 after reauth | Wrong token audience/expiry | Don't confuse reauth with API authorization |

### 38.1. Avoid Redirect Loops

If the user repeatedly declines a scope:

```text
Dashboard -> consent -> denied -> dashboard -> consent -> ...
```

the frontend should maintain `NEEDS_CONSENT` or `DECLINED` state and re-initiate only when the user explicitly clicks the feature.

### 38.2. API 403 Is Not Always Missing Scope

Orders API may return 403 because Alice does not own the order; requesting new scopes won't fix that. Distinguish OAuth2 Bearer errors from application-specific business denials.

---

## 39. Testing Custom Authorization Requests

Tests should verify:

- Normal login does not automatically add `calendar.readonly`.
- Valid `CALENDAR_READ` intent adds the exact approved scope.
- Other client registrations do not receive Google-specific parameters.
- OAuth2 `state` preserves correlation.
- PKCE and required OIDC attributes are preserved.
- Arbitrary scopes in query/JSON are rejected.
- Expired pending intents do not produce consent requests.
- User B cannot use User A's intent.
- Two tabs do not overwrite each other's state.
- Disabled tenants cannot proceed.
- Callbacks from the wrong issuer or wrong subject are rejected.

### 39.1. Builder Test Preserving `state`

JUnit 5 example:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.LinkedHashSet;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;

class IncrementalRequestTest {

    @Test
    void addsScopeWithoutReplacingState() {
        OAuth2AuthorizationRequest original =
            OAuth2AuthorizationRequest.authorizationCode()
                .authorizationUri("https://id.example/authorize")
                .clientId("portal-client")
                .redirectUri("https://portal.example/callback")
                .scopes(Set.of("openid", "profile"))
                .state("random-state-for-test")
                .build();

        Set<String> scopes = new LinkedHashSet<>(
            original.getScopes()
        );
        scopes.add("calendar.readonly");

        OAuth2AuthorizationRequest modified =
            OAuth2AuthorizationRequest.from(original)
                .scopes(scopes)
                .additionalParameters(params ->
                    params.put(
                        "include_granted_scopes", "true"
                    )
                )
                .build();

        assertThat(modified.getState())
            .isEqualTo(original.getState());

        assertThat(modified.getScopes())
            .contains("openid", "profile", "calendar.readonly");
    }
}
```

This tests request-builder behavior. It **does not** prove the OP agrees to grant the scope, does not test callback state validation, and does not verify actual granted scopes.

### 39.2. Integration Tests with an Authorization Server

Use a real test provider or high-fidelity contract mock to verify:

1. Successful consent request.
2. AS refuses out-of-policy scopes for the client.
3. User denial.
4. Partial scopes if supported by provider.
5. Wrong account picked in OP account chooser.
6. Refresh token responses and reuse/rotation.
7. Token audience/scopes accepted by Resource Server.
8. Admin-consent tenant restrictions.
9. Re-consent after revocation.
10. Stale callback initiated on an old tab.

Never mock `OAuth2AuthorizedClientManager` to always return a fake token and claim "incremental authorization is tested."

---

## 40. Testing Reauthentication and Step-Up

Cases to cover:

| Case | Expected |
|---|---|
| `max_age=300`, `auth_time` 1 minute old | Passes freshness if other checks pass |
| `max_age=300`, `auth_time` 2 hours old | Fails |
| `max_age=0`, ID Token lacks `auth_time` | Fails |
| `auth_time` in future beyond clock skew | Rejected |
| `acr` lower than required | Fails step-up |
| User logs into a different provider account | Fails |
| Tenant disabled between redirect/callback | Fails |
| `state` mismatch | Rejected |
| Pending intent already consumed | Replay rejected |
| Step-up issued for operation A, used on B | Rejected |
| Step-up expired | Rejected |
| Local account disabled after callback | Rejected |
| OP returns interaction error | Never marked verified |
| Has consent scope yet failed step-up | Sensitive action blocked |
| Passed step-up yet lacks API scope | Scope-requiring API not called |

### 40.1. `MockMvc` and Spring Security Test

Spring Security Test can simulate OIDC login:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
```

Conceptual example:

```java
mockMvc.perform(
    post("/api/features/calendar/connect")
        .with(oidcLogin())
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"feature\":\"CALENDAR_READ\"}")
).andExpect(status().is2xxSuccessful());
```

Prepare MockMvc, security filter chain, approved feature policy, and intent storage for complete tests. `oidcLogin()` only **mocks `Authentication`**—it does not execute browser redirects/code exchanges or validate real OIDC signatures, `state`, `nonce`, and `auth_time` from an AS.

### 40.2. CSRF Negative Test

The same POST without `.with(csrf())` must be rejected when the security chain uses default cookie-session CSRF policy. Never disable CSRF just to make tests pass.

---

## 41. WebFlux/Reactive: Same Policy, Different APIs

In Spring WebFlux, the architecture is identical:

```text
Browser -> WebFlux BFF -> Authorization Server -> Resource Server
```

Yet the stack classes differ:

| Servlet/MVC | WebFlux |
|---|---|
| `HttpSecurity` | `ServerHttpSecurity` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `ClientRegistrationRepository` | `ReactiveClientRegistrationRepository` |
| `DefaultOAuth2AuthorizationRequestResolver` | `DefaultServerOAuth2AuthorizationRequestResolver` |
| `OAuth2AuthorizationRequestResolver` | `ServerOAuth2AuthorizationRequestResolver` |
| `OAuth2AuthorizedClientManager` | `ReactiveOAuth2AuthorizedClientManager` |
| `OAuth2AuthorizedClientRepository` | `ServerOAuth2AuthorizedClientRepository` |
| `OAuth2AuthorizedClientService` | `ReactiveOAuth2AuthorizedClientService` |
| `SecurityContextHolder` | `ReactiveSecurityContextHolder` |

### 41.1. Reactive Authorization Request Customization

WebFlux has corresponding resolvers operating on `ServerWebExchange` and returning publishers. Customize additional parameters/scopes from **trusted server-side intent** without blocking the Reactor event loop.

Never copy a Servlet resolver reading `HttpServletRequest` into WebFlux or call `.block()` to load consent state.

### 41.2. Reactor Context Is Not a Consent Store

`ReactiveSecurityContextHolder` lets you read `Authentication` in a subscription, yet it:

- Does not persist OAuth2 consent history.
- Does not replace `ServerOAuth2AuthorizedClientRepository`.
- Does not manage refresh token rotation.
- Does not prove the user just passed MFA.

Consent/step-up policies and token storage still require explicit implementation.

---

## 42. Consent, Reauth, and Session Lifecycle

A user session has multiple independent clocks:

```text
BFF session:
    30-minute idle timeout

Access token:
    10-minute expires_in

Refresh token:
    AS policy

OIDC authentication:
    auth_time 45 minutes ago

Step-up intent:
    5-minute TTL

Step-up proof:
    valid for one action or short-lived
```

**These do not share the same lifetime.**

### 42.1. Refreshing an Access Token Is Not Reauthentication

The AS can mint a new access token via a refresh token **without user interaction**. That does not update `auth_time` in the sense of the user actively reauthenticating.

### 42.2. Browser Reload Is Not Reauthentication

An SPA reloading the page and firing new network requests does not prove the user re-entered credentials.

### 42.3. Session ID Rotation Is Not MFA

Spring Security's session fixation protection may rotate the session ID after login, yet a fresh session ID does not prove higher authentication assurance.

### 42.4. New Consent Does Not Automatically Refresh `auth_time`

A user can grant an additional scope under an existing authenticated OP session without logging in again.

---

## 43. Anti-Patterns to Avoid

### Anti-Pattern 1: Requesting All Scopes at Login

```text
openid profile email calendar.write drive.full_access billing.admin ...
```

when the user only wants to view the dashboard. Use feature-level incremental authorization.

### Anti-Pattern 2: Equating Consent with Roles

```text
User consented -> ROLE_ADMIN
```

Wrong security boundary. Consent is an AS-granted API permission; roles are business authorization.

### Anti-Pattern 3: `prompt=consent` on Every Request

Causes consent fatigue and neither expands scopes nor guarantees refresh tokens.

### Anti-Pattern 4: Treating `prompt=login` as MFA

Re-logging in may not satisfy required assurance/ACR policies.

### Anti-Pattern 5: Using `iat` Instead of `auth_time`

A freshly minted token does not prove the user freshly authenticated.

### Anti-Pattern 6: Adding Scopes from Arbitrary Frontend Input

Expands privileges outside policy and enables consent phishing.

### Anti-Pattern 7: Skipping Identity Checks After Callback

Users can pick another provider account and cause the backend to bind tokens to the wrong internal account.

### Anti-Pattern 8: Overwriting OAuth2 `state`

Using predictable `state` or breaking redirect URI/PKCE/`nonce` corrupts flow security.

### Anti-Pattern 9: Using Refresh Grants to Request Ungranted Scopes

Refreshing cannot bypass consent or AS policy.

### Anti-Pattern 10: Returning Tokens to JavaScript in a BFF

Breaks the backend-only token storage boundary.

### Anti-Pattern 11: Logging Out the Whole App When Consent Is Denied

Declining a single feature does not invalidate local login.

### Anti-Pattern 12: Automatically Redirecting to Consent on Every API 403

403 may be resource ownership or tenant policy. Never auto-loop grant flows.

### Anti-Pattern 13: Reusing One Reauth Forever for All Future Actions

Step-up proofs need TTLs, session/account bindings, and often transaction bindings.

### Anti-Pattern 14: Assuming Every OIDC Provider Understands `include_granted_scopes`

That parameter is specific to Google and providers supporting that extension.

### Anti-Pattern 15: Assuming Requested Scopes Equal Granted Scopes

Always inspect the actual authorization/token response.

### Anti-Pattern 16: Deleting an Old Authorization Without Considering Refresh-Token Rotation

Can drop valid grants or trigger race conditions/`invalid_grant`.

### Anti-Pattern 17: Using Provider Account B's Token for Internal Account A

Enforce `(iss,sub)`/stable provider ID checks and authorized client ownership.

### Anti-Pattern 18: Disabling CSRF to Make `POST start-consent` Work

Cookie-session BFFs still need CSRF protection; OAuth2 `state` does not replace API CSRF tokens.

---

## 44. Applied Scenarios

### Scenario A — User Only Wants to View the Dashboard

**Right behavior:** log in with minimal scopes without asking for calendar/drive permissions yet.

### Scenario B — User Enables Calendar Sync for the First Time

**Behavior:** app explains permissions, creates pending intent, redirects to IdP for additional calendar scope, and saves tokens only on valid grant.

### Scenario C — User Declines Calendar Sync

**Behavior:** keep dashboard working; do not force logout or spam consent screens.

### Scenario D — Google Returns Token with Combined Scopes

**Behavior:** per provider contract (`include_granted_scopes=true` when appropriate), verify actually granted scopes and store the authorized client safely.

### Scenario E — Provider Omits Refresh Token After Re-Consent

**Behavior:** do not assume a refresh token will appear; retain or update the token record per contract and authorization semantics.

### Scenario F — API Returns 403 Because Alice Doesn't Own the Resource

**Behavior:** deny the business operation; never ask for new scopes to bypass permissions.

### Scenario G — User Picks Bob in the Google Account Chooser

**Behavior:** detect `(iss,sub)` mismatch; refuse to store Bob's token under Alice's session.

### Scenario H — Changing Payout Bank Account After 8 Hours

**Behavior:** require OIDC reauthentication/step-up per policy, verifying `auth_time` and ACR/MFA if required.

### Scenario I — OP Returns ID Token with Fresh `iat` Yet Stale `auth_time`

**Behavior:** do not treat as fresh login; token issuance time does not replace authentication event time.

### Scenario J — Provider Does Not Support `acr_values=...`

**Behavior:** use an assurance mechanism confirmed by the provider or app-local step-up; never mark MFA as passed.

### Scenario K — `prompt=none` Returns `interaction_required`

**Behavior:** do not bypass consent; show a button for user-initiated interactive authorization.

### Scenario L — Tenant Blocks `billing.write` Scope

**Behavior:** SaaS policy blocks the flow even if the provider could grant the scope.

### Scenario M — Two Tabs Request Different Scopes Simultaneously

**Behavior:** intents keyed by OAuth `state`, and token storage prevents stale overwrites.

### Scenario N — Logout After Consent

**Behavior:** local session ends; authorized client/token revocation follows separate policy.

### Scenario O — User Revokes App at Provider

**Behavior:** handle API/refresh failures, mark disconnected, and prompt re-consent only when user wants it.

### Scenario P — Concurrent Refresh During Consent Callback

**Behavior:** ensure newly granted callback tokens are not overwritten by older refresh responses.

### Scenario Q — Step-Up for a Single Transaction

**Behavior:** pending proof bound to transaction ID, short TTL, single-use consumption.

### Scenario R — SPA Attempts to Read Refresh Tokens from Backend

**Behavior:** no endpoint exposes raw tokens; the BFF proxies business calls keeping credentials server-side.

### Scenario S — Enterprise Admin Granted Consent for Users

**Behavior:** follow provider/admin-consent policy without assuming every end-user personally consented to every scope.

### Scenario T — Token Has Right Scope Yet Wrong Audience

**Behavior:** never call the API with a wrong-audience token; obtain authorization for the right resource/client.

---

## 45. Self-Check Questions

**1. Are consent and authentication the same?**  
No. Consent lets an OAuth2 client exercise API permissions; authentication establishes who is logged in.

**2. Is incremental authorization a new grant type?**  
No. It usually reuses a new Authorization Code Flow with additional scopes.

**3. Why not request every scope at initial login?**  
Least privilege, contextual permissions, and avoiding consent fatigue.

**4. What does `prompt=consent` do?**  
Requests consent interaction at the OP per spec/provider policy; it does not grant extra permissions by itself.

**5. How does `prompt=login` differ from `prompt=consent`?**  
The first requests reauthentication; the second requests consent.

**6. What does `max_age=0` mean?**  
Per OIDC Core, it requires active reauthentication, semantically equivalent to `prompt=login`.

**7. When using `max_age`, which claim must the ID Token contain?**  
`auth_time`.

**8. Why doesn't `iat` replace `auth_time`?**  
`iat` is when the token was issued, not when the user authenticated at the OP.

**9. Does `acr_values` guarantee MFA by itself?**  
No. You need a provider contract and verification of returned `acr`/assurance claims.

**10. Can the browser freely choose `scope=admin.write`?**  
No. Use a server-side feature-to-scope allowlist and business authorization.

**11. Does `include_granted_scopes=true` work with every provider?**  
No. It is a Google-supported feature; other providers have different semantics.

**12. What must a consent callback verify besides `state`?**  
PKCE/`nonce`, registration/issuer, intent, session/account/tenant binding, granted scopes, and identity.

**13. Why check `(iss,sub)` after callback?**  
Users might choose a different provider account, causing tokens to bind to the wrong internal user.

**14. Are requested scopes guaranteed to be granted?**  
No. AS/user/policy determine the actually granted scopes.

**15. What is `OAuth2AuthorizedClient` for?**  
Stores client registration and access/refresh tokens per principal for API calls.

**16. Can a refresh token request unconsented scopes?**  
Not under OAuth2 authorization rules; interactive authorization or a provider-specific contract is required.

**17. Should every API 403 trigger re-consent?**  
No. Distinguish `insufficient_scope` from business authorization denials.

**18. Does logout automatically revoke all provider tokens?**  
Not by default. Local session logout and token revocation are distinct.

**19. Does a BFF completely eliminate XSS?**  
No. A BFF reduces raw token exposure, yet XSS can still call APIs via the session.

**20. Why must step-up have TTL/transaction binding?**  
To keep a one-time check from turning into long-lived privilege across all actions.

**21. Does `prompt=none` allow skipping consent?**  
No. The OP returns an error if it cannot satisfy the request silently.

**22. Do multiple providers linked to one account share the same assurance?**  
No. Each provider/method has its own authentication provenance and trust policy.

**23. Can a consent callback alter the local `Authentication`?**  
Yes. OAuth2 Login callbacks can set a new `Authentication`; the app must preserve proper account binding.

**24. Who decides business roles after consent?**  
Application/Resource Server authorization policy, not the consent screen alone.

**25. What are the most critical tests?**  
Requested scopes/params, `state`/PKCE, identity binding, granted scopes, reauth `auth_time`/`acr`, denied consent, token lifecycle, and tenant isolation.

---

## 46. Core Takeaways

| Concept | Meaning |
|---|---|
| OAuth2 consent | User/AS allows client to exercise API permissions |
| Scope | Requested/granted permission range, not a local role |
| Incremental authorization | Requesting permissions at the moment a feature needs them |
| Authorization Code Flow | Flow typically reused for additional scopes |
| `prompt=consent` | Requests consent interaction at the OP |
| `include_granted_scopes=true` | Google-specific cumulative scopes support |
| `prompt=login` | Requests OP reauthentication of End-User |
| `max_age` | Caps age of active OP authentication |
| `max_age=0` | Requests active reauthentication |
| `auth_time` | Timestamp when OP authenticated End-User |
| `acr` | Authentication context class |
| `amr` | Authentication methods references |
| `acr_values` | Requested context classes; requires provider contract |
| `prompt=none` | Non-interactive; errors if interaction is required |
| `OAuth2AuthorizationRequestResolver` | Extension point creating authorization requests |
| `DefaultOAuth2AuthorizationRequestResolver` | Standard Servlet resolver with customizer support |
| `OAuth2AuthorizationRequest.from(...)` | Clones and modifies scopes/additional parameters |
| `state` | Protects authorization response correlation |
| PKCE | Binds authorization code to verifier |
| OIDC `nonce` | Binds ID Token to authentication request |
| CSRF token | Protects POSTs creating intents or changing settings |
| Pending consent intent | Server-side state binding account/tenant/feature/OAuth state |
| `OAuth2AuthorizedClient` | Access/refresh tokens plus registration/principal |
| `OAuth2AuthorizedClientManager` | Authorizes/refreshes per configured providers |
| Granted scopes | Permissions actually granted by AS; must be checked |
| Audience | Target resource for an access token |
| Reauthentication | Re-verifies identity; does not grant scopes |
| Step-up | Raises freshness/assurance for sensitive actions |
| BFF | Browser holds session cookie; tokens stay on backend |
| Token revocation | Separate AS operation when supported |
| Tenant policy | Governs scopes, registrations, and business permissions |
| `insufficient_scope` | Bearer token lacks required API permission |
| `login_required` | OP requires user authentication |
| `consent_required` | OP requires interactive consent |
| `interaction_required` | OP cannot fulfill silent request |
| Provider contract | Defines exact semantics and extension parameters |

### Conclusion

**Consent**, **incremental authorization**, and **reauthentication** are three complementary yet non-interchangeable processes in a Spring Security OAuth 2.0/OIDC Client:

1. **Consent:** AS and user grant the OAuth2 client access to resources with specific scopes.
2. **Incremental authorization:** the app requests new scopes only when the user actually needs a feature, typically using a new Authorization Code Flow and provider-specific parameters.
3. **Reauthentication/step-up:** the app requires the user to re-prove identity and sufficiently fresh assurance before sensitive actions, typically via `prompt=login`, `max_age`, `auth_time`, and `acr`/`amr` per OIDC contract.

A secure design must **initiate flows from verified user intent**, protect `state`/PKCE/`nonce` and CSRF, **verify the same provider identity after callback**, save tokens under the right authorized client owner, check **granted scopes** rather than requested scopes, and enforce local business authorization at the Resource Server.

**Never treat a dismissed consent screen as proof the user holds API permissions, and never treat a newly minted ID Token as proof MFA just occurred.** Only permissions and authentication evidence verified under the exact provider contract are sufficient for security decisions.

## Official References

- [Spring Security — Authorization Grant Support: Customizing the Authorization Request](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html) — `OAuth2AuthorizationRequestResolver`, `prompt`, and authorization request customization.
- [Spring Security — Advanced OAuth2 Login Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html) — OAuth2 Login callbacks, authorization requests, user services, and handlers.
- [Spring Security — OAuth2 Client Authorized Clients](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html) — managers, repositories, token lifecycle.
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html) — CSRF with browser sessions.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html) — sessions and reauthentication lifecycle.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html) — `prompt`, `max_age`, `auth_time`, `acr`, `amr`, OIDC authentication.
- [Google — OAuth 2.0 for Web Server Applications](https://developers.google.com/identity/protocols/oauth2/web-server) — incremental authorization and `include_granted_scopes`.
- [Google — OAuth2 Best Practices](https://developers.google.com/identity/protocols/oauth2/resources/best-practices) — contextual consent and handling partial grants.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749) — scopes, authorization code, token responses, and errors.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750) — `insufficient_scope` and Bearer errors.
- [RFC 7636 — PKCE](https://www.rfc-editor.org/rfc/rfc7636) — code interception protection.
- [RFC 8707 — OAuth 2.0 Resource Indicators](https://www.rfc-editor.org/rfc/rfc8707) — target resource/audience restriction.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009) — token revocation when supported by AS.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700) — OAuth2 security considerations.
- [OpenID Connect RP-Initiated Logout](https://openid.net/specs/openid-connect-rpinitiated-1_0.html) — OP logout and differences from token revocation.
