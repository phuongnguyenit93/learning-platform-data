# Login, Consent, and Approving or Denying a Device Request

> **Chapter:** Device Authorization  
> **Module:** `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER`  
> **Scope:** Learn how to design, configure, secure, test, and operate an OAuth 2.0/OpenID Connect Authorization Server with Spring Security and Spring Authorization Server in a Spring Boot application.  
> **Illustrated versions:** Spring Boot 3.x, Spring Security 6.x, Spring Authorization Server 1.x on the Servlet stack. In Spring Security 7.x, classes/configurers may change packages or integration styles: verify against the docs for your exact version instead of copying old major-version configurations verbatim.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain why **Device Authorization Grant** (RFC 8628) separates requesting access on an input-constrained device from login and consent on a secondary browser.
2. Distinguish `device_code`, `user_code`, `verification_uri`, `verification_uri_complete`, `expires_in`, and `interval`.
3. Describe the complete sequence: **user login → user code verification → device/client inspection → consent → approval or denial → device polling the token endpoint**.
4. Distinguish the responsibilities of `OAuth2DeviceAuthorizationEndpointConfigurer`, `OAuth2DeviceVerificationEndpointConfigurer`, and `OAuth2TokenEndpointConfigurer` in Spring Authorization Server.
5. Build a consent page for the device flow that submits the proper `user_code`, `client_id`, `state`, approved scopes, and CSRF token.
6. Design the denial path so it **genuinely transitions the grant into a denied state**, causing the token endpoint to return `access_denied`, rather than merely closing the browser.
7. Test unauthenticated access, invalid/expired codes, partial consent, denial, rapid polling, signing in to the wrong account, phishing, and race conditions.

**Guiding principle:** A device can initiate an access request, but **that request must never be treated as approved** merely because the user opened the verification page or signed in. **The approval/denial decision must bind to the exact device authorization session, verified user, client, and scope set.**

## 2. Real-World Problem: Signing In on TVs, Printers, and IoT Devices

Suppose a user wants to sign in to a hotel-booking app on a smart TV. The TV can display a short code, but typing a long password or completing MFA directly with a remote control is both difficult and unsafe.

Device Authorization Grant lets the TV:

1. Contact the Authorization Server (AS) to request a device authorization session.
2. Receive a `user_code` and `verification_uri` to display.
3. Let the user use a **trusted phone or computer** to open the verification URL, sign in to the AS, and decide whether to grant the TV access.
4. Meanwhile, the TV **polls** the token endpoint at the specified interval.
5. Only after the user **approves** does the AS issue an access token to the TV under the grant.

If the user **denies**, the TV must learn of that decision through a protocol error and stop polling. If the code expires, the TV must start a new session when explicitly prompted by the user. This is the classic RFC 8628 scenario. <https://www.rfc-editor.org/rfc/rfc8628>

### 2.1. Roles

| Component | Role | Do not confuse with |
| --- | --- | --- |
| **Resource Owner** | Person deciding whether to grant access, e.g. Lan | The device requesting access |
| **Device / OAuth2 Client** | TV running the `booking-tv` app | The phone browser used for login |
| **Secondary device / browser** | Phone visiting `verification_uri`, logging in, and consenting | Where the AS sends the TV's access token |
| **Authorization Server** | Creates device session, authenticates user, records decision, issues tokens | Business API (Resource Server) |
| **Resource Server** | Validates access token and enforces API policies | Device code verification page |

The TV **never receives Lan's password**. The phone **never passes the account's refresh token or access token to the TV via QR/URL**; the TV retrieves its own token from the AS once the grant is approved.

## 3. Distinguishing `device_code` and `user_code`

A successful Device Authorization Endpoint response typically looks like:

~~~json
{
  "device_code": "opaque-high-entropy-device-code",
  "user_code": "WDJB-MJHT",
  "verification_uri": "https://auth.example.test/oauth2/device_verification",
  "verification_uri_complete": "https://auth.example.test/oauth2/device_verification?user_code=WDJB-MJHT",
  "expires_in": 600,
  "interval": 5
}
~~~

This data is **illustrative**. Never use hardcoded static codes in a real system; the AS must generate random, unpredictable codes with bounded lifetimes and proper validation.

| Property | Primary user | Meaning and rules |
| --- | --- | --- |
| `device_code` | Device / token endpoint | Secret, high-entropy string; TV uses it for polling, **never displayed for the user to type** |
| `user_code` | User entering on secondary browser | Short, readable/typeable code used to locate the right request; not an access token |
| `verification_uri` | Secondary browser | Official URL for the user to visit and manually enter `user_code` |
| `verification_uri_complete` | Browser/QR/NFC, when provided by AS | URL pre-filled with `user_code` to reduce typing; still requires confirming the right device |
| `expires_in` | Device | Validity window of the device authorization session, in seconds |
| `interval` | Device | Minimum polling interval, in seconds; if omitted, RFC 8628 defaults to 5 seconds |

**Key point:** `user_code` has lower entropy than `device_code` because humans must be able to type it. Therefore, the AS must apply rate limiting, guessing defenses, short lifetimes, and phishing risk checks. **Never use `user_code` for the device to exchange for a token at `/oauth2/token`.** Only `device_code` serves that role under Device Grant.

### 3.1. Why Are There Two Codes?

~~~mermaid
flowchart LR
    D["TV / Device"]
    A["Authorization Server"]
    H["Phone / browser"]
    U["User"]
    T["Token endpoint"]

    D -->|"Request device authorization session"| A
    A -->|"device_code (kept internal)<br/>user_code + verification_uri (displayed)"| D
    U -->|"Enter user_code or scan QR"| H
    H -->|"Login, inspect, consent"| A
    D -->|"Poll with device_code"| T
    T -->|"Check grant state at AS"| A
~~~

The code shown to the user **only identifies the pending device authorization request**. The AS still has to verify that the Resource Owner is authenticated, the session has not expired, the client is valid, the scopes do not exceed allowed bounds, and the request is not replayed.

## 4. Overview of the Login, Consent, and Decision Sequence

~~~mermaid
sequenceDiagram
    autonumber
    participant TV as TV / OAuth2 Client
    participant AS as Authorization Server
    participant DB as Authorization Store
    actor U as Resource Owner
    participant P as Phone Browser

    TV->>AS: POST /oauth2/device_authorization<br/>client_id + scope
    AS->>DB: Create PENDING device session
    AS-->>TV: device_code, user_code, verification_uri, interval, expires_in
    TV->>TV: Display URL and user_code
    TV->>AS: POST /oauth2/token<br/>grant_type=device_code + device_code + client_id
    AS-->>TV: authorization_pending
    U->>P: Open verification_uri / scan QR
    P->>AS: GET /oauth2/device_verification
    opt User not logged in
        AS-->>P: Redirect to /login
        U->>P: Sign in, MFA if required by policy
        P->>AS: Resume device verification
    end
    U->>P: Enter/confirm user_code
    P->>AS: Submit user_code
    AS->>DB: Look up session and requested client/scopes
    AS-->>P: Display app name, permissions, and code to match
    alt Approve
        U->>P: Approve scopes
        P->>AS: POST valid consent
        AS->>DB: Record APPROVED / authorized scopes
        AS-->>P: Approved, please return to TV
        TV->>AS: Next poll with device_code
        AS-->>TV: Access token (+ refresh token if policy allows)
    else Deny
        U->>P: Select Deny
        P->>AS: Submit valid denial decision
        AS->>DB: Record DENIED / invalidate token issuance
        AS-->>P: Request denied
        TV->>AS: Next poll with device_code
        AS-->>TV: access_denied
    end
~~~

This diagram is a **conceptual protocol and state model**. State names `PENDING`, `APPROVED`, and `DENIED` are illustrative; they are **not built-in mandatory enum constants** in every Spring Authorization Server version. If you build a custom denial path, make sure both the verification provider and the token endpoint agree on the denied state.

### 4.1. States to Distinguish

| Logical state | User/browser | Polling device |
| --- | --- | --- |
| **Pending** | Has not entered user code, logged in, or decided | `authorization_pending` |
| **Code invalid/expired** | Screen reports missing/expired code, offers retry | `expired_token` if device code expired |
| **Authenticated, not yet consented** | Signed in, must still review and decide scopes | Still `authorization_pending` |
| **Approved** | Shows completion, asks user to return to device | Next valid poll can receive token |
| **Denied** | Shows denied, does not auto-grant | `access_denied`; client must stop polling |
| **Rate limited / polled too fast** | Not directly visible to browser | `slow_down`; increase polling interval |

Successfully authenticating on the login page **is not enough** to transition the state to Approved.

## 5. Step 1 — Device Creates a Device Authorization Request

### 5.1. RegisteredClient Must Permit the Device Grant

In Spring Authorization Server 1.x, a public client for a TV can be registered with the `DEVICE_CODE` grant type.

~~~java
import java.time.Duration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;
import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;

public final class DeviceClientFactory {

    private DeviceClientFactory() {}

    public static RegisteredClient bookingTv() {
        return RegisteredClient.withId("booking-tv-registration-id")
            .clientId("booking-tv")
            .clientName("Booking TV")
            .clientAuthenticationMethod(ClientAuthenticationMethod.NONE)
            .authorizationGrantType(AuthorizationGrantType.DEVICE_CODE)
            .scope("booking.read")
            .scope("profile")
            .clientSettings(ClientSettings.builder()
                .requireAuthorizationConsent(true)
                .build())
            .tokenSettings(TokenSettings.builder()
                .accessTokenTimeToLive(Duration.ofMinutes(5))
                .build())
            .build();
    }
}
~~~

This is an **illustrative registration snippet**, not a complete AS. Persist the client via an appropriate `RegisteredClientRepository` and configure the remaining services. For a public client, `client_id` is a public identifier, **not proof of a physical TV's identity or trustworthiness**. Client secrets should never be embedded in unprotected firmware or apps.

Setting `requireAuthorizationConsent(true)` expresses the policy requiring user consent under the AS mechanism. However, to guarantee **every pairing for each individual device explicitly confirms the right device**, check how stored consent behaves alongside client policy and security requirements. **Previously saved consent for the same client/user does not necessarily prove the user recognizes the specific physical TV requesting access.**

### 5.2. Request to the Device Authorization Endpoint

~~~http
POST /oauth2/device_authorization HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded
Accept: application/json

client_id=booking-tv&scope=booking.read%20profile
~~~

For a public client, the AS identifies the client using `client_id` and registration rules. For a confidential client, client authentication must follow the registered method. The AS checks whether the client is permitted to use Device Authorization Grant and whether the scopes are valid, then creates a device session.

The Device Authorization Endpoint is **not** where the user enters a password or gives consent. From this initial request alone, the AS does not yet know which Resource Owner will approve the request.

### 5.3. What Should the Device Display?

A well-designed screen might read:

> On your phone or computer, visit **https://auth.example.test/oauth2/device_verification**.  
> Enter code: **WDJB-MJHT**.  
> Proceed only if you are signing in for this TV. This code expires in a few minutes.

The device screen can provide a QR code pointing to `verification_uri_complete`, yet **still show `user_code` in text** so the user can cross-check it in the browser. Never display `device_code`, since that is the polling credential. Never put `device_code` into a URL or QR code.

## 6. Step 2 — User Opens Verification URI and Logs In

The user switches to a phone and **directly opens the official AS URL** over HTTPS. If not already signed in, Spring Security prompts the Resource Owner to authenticate.

### 6.1. Role of the Login Entry Point

The Authorization Server can use two filter chains:

1. An OAuth2/OIDC chain dedicated to device authorization, device verification, and token endpoints.
2. An application chain managing form login, additional HTML pages, sessions, and browser authentication requirements.

Requests to `/oauth2/device_verification` require an authenticated **real user** before completing verification/consent. If Spring Security redirects to `/login`, ensure that:

- `GET /login` is accessible anonymously.
- `POST /login` validates username/password/MFA per policy.
- Form login CSRF protection is never arbitrarily disabled.
- `SecurityContext` and session are persisted so the browser returns to device verification.
- The code or request being verified is preserved/restored cleanly after login completes.
- If the user signed in with the wrong account, the UI shows the current account and lets them cancel or switch accounts appropriately.

**Never collect a password on the TV and forward it directly to the AS as "device consent."** The purpose of the device grant is to move user login onto a more trustworthy browser on another device.

### 6.2. Spring Security Configuration Example for User Interaction

Example for Spring Authorization Server 1.x focusing on device endpoints and form login:

~~~java
@Configuration
public class DeviceFlowSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurity(HttpSecurity http)
            throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, server -> server
                .deviceAuthorizationEndpoint(Customizer.withDefaults())
                .deviceVerificationEndpoint(verification -> verification
                    .consentPage("/device/consent"))
            )
            .authorizeHttpRequests(authorize -> authorize
                .anyRequest().authenticated())
            .exceptionHandling(exceptions -> exceptions
                .defaultAuthenticationEntryPointFor(
                    new LoginUrlAuthenticationEntryPoint("/login"),
                    new MediaTypeRequestMatcher(MediaType.TEXT_HTML)));

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurity(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/assets/**").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
~~~

Typical imports:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.LoginUrlAuthenticationEntryPoint;
import org.springframework.security.web.util.matcher.MediaTypeRequestMatcher;
~~~

**Important boundary:** this is a **configuration fragment** for an application that already provides `RegisteredClientRepository`, `OAuth2AuthorizationService`, keys, and required AS, user authentication, and session beans. `consentPage("/device/consent")` **only points to a UI created by your application**; it does not automatically supply a controller or template.

Default device paths from `AuthorizationServerSettings` are typically:

~~~text
POST /oauth2/device_authorization    - device requests codes
GET/POST /oauth2/device_verification - user code verification / consent per flow
POST /oauth2/token                   - device polls to exchange device code
~~~

If the application uses custom settings, read the actual path from `AuthorizationServerSettings` rather than hardcoding `/oauth2/device_verification` in UI templates. **Never change the URL displayed on the TV without updating `verification_uri` and the endpoint matcher.**

Different major lines/versions configure device endpoints with different default enabled states; start the app and verify live endpoint behavior rather than guessing from method names. Paths and behavior above align with Spring Authorization Server documentation. <https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html>

## 7. Step 3 — Entering or Confirming user_code

### 7.1. User Opens the Verification Page

When the browser opens `verification_uri`, the AS must provide a way to identify the device session. For manual entry, the user enters `user_code`. With `verification_uri_complete` or QR, the code may be pre-filled, yet **the UI should still display the code and ask the user to match it against the TV**.

Goals of this step:

1. Locate the initialized pending device authorization session.
2. Verify the session has not expired and has not already been completed or denied.
3. Associate the pending session with the authenticated Resource Owner.
4. Retrieve the client registration and requested scopes to render the consent screen.
5. **Do not issue any token** merely because the user entered a code.

### 7.2. Invalid, Expired, or Already-Processed Codes

For a non-existent, expired, or already-used `user_code`:

- Show an error that leaks no information about other accounts.
- Let the user recheck the code on the TV or restart from the device.
- Never proceed to consent for an unidentified session.
- Never log `user_code` in plaintext in logs or traces unless strictly required.
- Apply rate limiting, CAPTCHA, or risk-based controls to stop brute-forcing short codes.
- Never allow re-approving an already-completed session.

### 7.3. A Code Does Not Prove the User Holds the TV

This is a vital security point: a short `user_code` can be sent by an attacker via email or chat. A victim may enter a code belonging to **an attacker-controlled device** while thinking they are signing in to their own TV.

Thus, a valid user code alone is not enough. The consent screen must make clear:

- Which application or client is requesting access.
- The exact permissions requested.
- That the code must **match the code displayed on the device the user actually owns or is setting up**.
- That the user should approve only if **they themselves just initiated** the pairing.
- A prominent **Deny** option if they do not recognize the device.

For devices/mechanisms supporting verifiable identity, AS-verified device information may be displayed. **Never trust an arbitrary `"My TV"` string sent by the client as verified hardware identity.**

## 8. Step 4 — Displaying Consent and Scopes for the Right Client

Consent answers the question: **Which permissions does the Resource Owner allow this client to exercise?**

Suppose `booking-tv` requests:

~~~text
client_id: booking-tv
client_name: Booking TV
requested_scopes:
  - booking.read
  - profile
user_code: WDJB-MJHT
~~~

The consent page should present permissions in user-friendly language:

| Technical scope | Displayable description |
| --- | --- |
| `booking.read` | View bookings accessible to your account |
| `profile` | View basic profile details per policy |
| `booking.write` | Create or modify bookings — **must not appear if not requested/permitted for the client** |

**Consent does not replace business authorization.** Even if Lan approves `booking.read`, the Resource Server must still check permissions per booking/tenant. Never infer from an approved scope that the TV can read every booking across all accounts.

### 8.1. Trusted Data Sources for the Consent Screen

A consent page **must not blindly trust** `client_id`, `scope`, and `user_code` arriving in browser query strings. The safe procedure is:

1. Look up `RegisteredClient` from the repository; never take arbitrary app names from query params.
2. Identify the pending device session by code, status, and matching user session.
3. Intersect requested scopes with registered scopes and the authorization state stored by the AS.
4. Render only approvable scopes and server-controlled descriptions.
5. On consent POST, **the AS provider re-validates server-side**; hidden HTML fields are not a security boundary.

The objects involved are `OAuth2Authorization`, `OAuth2AuthorizationConsent`, and their backing services; `SecurityContextHolder` alone cannot substitute for device session state.

### 8.2. Consent May Be Full or Partial

Under OAuth2, the AS may let the Resource Owner approve a **subset** of requested scopes. If a client requests `booking.read profile` and the user only approves `booking.read`, the issued token must not include `profile` against the user's wishes. However, partial consent support and required scopes depend on provider/client/version policy; test actual behavior.

**Do not assume leaving all checkboxes unchecked is universally treated as denying the entire grant across every version.** For a reliably testable "Deny" action, design a dedicated protocol-compliant denial path as shown in section 10.

## 9. Custom Consent Page with Spring Authorization Server

### 9.1. Configurers Dedicated to Device Verification

Spring Authorization Server separates these configurers:

| Configurer | Endpoint | Role |
| --- | --- | --- |
| `OAuth2DeviceAuthorizationEndpointConfigurer` | `/oauth2/device_authorization` | Accepts device requests, issues `device_code`/`user_code`, sets `verification_uri` |
| `OAuth2DeviceVerificationEndpointConfigurer` | `/oauth2/device_verification` | Verifies user code, handles consent and browser interaction |
| `OAuth2TokenEndpointConfigurer` | `/oauth2/token` | Handles device code polling and returns tokens/errors |

For device verification, Spring Authorization Server exposes extension points such as:

- `deviceVerificationRequestConverter(...)` / `deviceVerificationRequestConverters(...)`.
- `authenticationProvider(...)` / `authenticationProviders(...)`.
- `deviceVerificationResponseHandler(...)`.
- `errorResponseHandler(...)`.
- `consentPage(...)`.

Default providers in SAS 1.x include `OAuth2DeviceVerificationAuthenticationProvider` and `OAuth2DeviceAuthorizationConsentAuthenticationProvider`. Adding custom providers must preserve standard checks on user code, client, user authentication, scopes, consent state, and code lifetime.

### 9.2. Parameters Passed to a Custom Consent Page

Per the `OAuth2DeviceVerificationEndpointConfigurer.consentPage(...)` API, when redirecting to a custom consent page, the key parameters include:

- `client_id` — client identifier.
- `scope` — space-delimited scope list.
- `state` — correlation/anti-CSRF token for the **device consent flow**.
- `user_code` — user code tied to the device session.

The consent form must **POST to `AuthorizationServerSettings.getDeviceVerificationEndpoint()`** with `client_id`, `state`, `user_code`, and the approved `scope` values. This is a notable difference from standard Authorization Code Grant consent forms, which POST to the authorization endpoint. <https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OAuth2DeviceVerificationEndpointConfigurer.html>

### 9.3. Example Consent Display Controller

Assuming Spring MVC and Thymeleaf, the custom path `/device/consent` is served under the application/login chain, while the POST goes to the AS device verification endpoint:

~~~java
@Controller
public class DeviceConsentPageController {

    private final RegisteredClientRepository clients;

    public DeviceConsentPageController(RegisteredClientRepository clients) {
        this.clients = clients;
    }

    @GetMapping("/device/consent")
    String showConsent(
            @RequestParam("client_id") String clientId,
            @RequestParam("scope") String scope,
            @RequestParam("state") String state,
            @RequestParam("user_code") String userCode,
            Model model,
            Authentication authentication) {

        if (authentication == null
                || authentication instanceof AnonymousAuthenticationToken) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }

        RegisteredClient client = clients.findByClientId(clientId);
        if (client == null) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST);
        }

        Set<String> requestedScopes = Arrays.stream(scope.split(" "))
            .filter(value -> !value.isBlank())
            .collect(Collectors.toCollection(LinkedHashSet::new));

        if (!client.getScopes().containsAll(requestedScopes)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST);
        }

        model.addAttribute("clientId", client.getClientId());
        model.addAttribute("clientName", client.getClientName());
        model.addAttribute("state", state);
        model.addAttribute("userCode", userCode);
        model.addAttribute("scopes", requestedScopes);
        return "device-consent";
    }
}
~~~

Required Java/Spring imports include `Arrays`, `Set`, `LinkedHashSet`, `Collectors`, `Model`, `RegisteredClientRepository`, `RegisteredClient`, `Authentication`, `AnonymousAuthenticationToken`, `ResponseStatusException`, `HttpStatus`, and the MVC annotations.

**Limitation:** this snippet is strictly the **UI rendering layer**. Checking client and scopes from query params alone does not prove `user_code` and `state` match a **pending authorization in the store**. Let the AS default provider validate the POST or add a safe service that verifies the pending session before displaying sensitive details. Never turn the UI controller into a substitute for the token-issuing provider.

In production, verify that `user_code` belongs to an unexpired, incomplete session bound to the right client, verified device info if available, and the currently logged-in account. Checking `AnonymousAuthenticationToken` in the example is only a coarse guard; standard authentication rules should be enforced by the filter chain.

### 9.4. Example Thymeleaf Template for the "Approve" Button

~~~html
<h1>Allow device access?</h1>

<p>
  Application: <strong th:text="${clientName}">Booking TV</strong>
</p>

<p>
  Device code: <strong th:text="${userCode}">WDJB-MJHT</strong>
</p>

<p>Proceed only if this code matches the code on the TV you are setting up.</p>

<form method="post" th:action="@{/oauth2/device_verification}">
  <input type="hidden" name="client_id" th:value="${clientId}">
  <input type="hidden" name="state" th:value="${state}">
  <input type="hidden" name="user_code" th:value="${userCode}">

  <div th:each="scopeValue : ${scopes}">
    <label>
      <input type="checkbox" name="scope" th:value="${scopeValue}">
      <span th:text="${scopeValue}">Access permission</span>
    </label>
  </div>

  <input type="hidden"
         th:name="${_csrf.parameterName}"
         th:value="${_csrf.token}">

  <button type="submit">Approve selected permissions</button>
</form>
~~~

**Template assumption:** `AuthorizationServerSettings.getDeviceVerificationEndpoint()` uses the default `/oauth2/device_verification`. If you customize the endpoint, pass the configured URI from trusted settings into the model rather than hardcoding the form action. Output-escape all request values; the template engine automatically escapes `th:text`/`th:value`.

In some UIs, "no scopes selected" may signal denial or trigger an error depending on provider/version. Never rely on that behavior as a security contract without verifying it. Build an **explicit deny button** and test the outcome as covered in section 10.

### 9.5. Consent `state` vs. Easily Confused Values

| Value | What is it used for? |
| --- | --- |
| `user_code` | Identifies the pending device session for the user during verification |
| `device_code` | Device polling at token endpoint; **never included in the HTML consent form** |
| Device consent `state` | AS-managed correlation/CSRF protection for the consent interaction |
| Spring Security `_csrf` | Protects HTTP form POST per configured CSRF mechanism |
| Authorization Code Grant `state` | Client correlates callback with a normal authorization request |

Never generate a new `state` value while rendering consent. Never substitute `user_code` or `_csrf` for `state`. Each value has its own source and purpose.

## 10. Approval and Denial: Both Decisions Must Produce Protocol Outcomes

### 10.1. When the User Approves

On consent POST, the AS must verify:

1. The browser has an authenticated Resource Owner, plus re-authentication/MFA if required by policy.
2. `state` and `user_code` match the pending device session and have not already been used.
3. The session has not expired and the form's client ID matches the pending authorization.
4. Approved scopes lie within the requested scopes, registration, and client policy.
5. The user has not been disabled or become ineligible to grant permissions under current policy.
6. Approval state is persisted durably so the same request cannot be processed as new again.

After approval, the browser displays a message like:

> **Device approved.** Return to your TV to finish signing in. If this is not your device, revoke access in device management.

The TV **never receives the token through the browser**. It obtains the token on its next valid poll to `/oauth2/token` once the AS sees the approved session.

### 10.2. When the User Denies

A genuine denial action must:

1. Verify **who** is denying and **which request** is being denied.
2. Identify the corresponding `user_code`, client, state, and pending authorization.
3. Record the denial or invalidate the session per the AS model so **the token endpoint can never issue a token** for that `device_code`.
4. Inform the browser that the request was denied.
5. When the device polls, return `access_denied` per RFC 8628 if the implementation stores denial state that way.
6. Require the device to stop polling and prompt the user to start a new request if desired.

**Closing the browser, clicking Back, or leaving checkboxes unchecked does not guarantee the token endpoint will recognize a "denial."** If the user takes no action, the request usually stays pending until it expires—a different state from explicit denial.

### 10.3. Do Not Fake DENIED by Arbitrarily Deleting Records

Conceptual handling pattern:

~~~text
POST /device/deny   (custom endpoint, not a standard RFC 8628 endpoint)
  1. Verify user authentication, CSRF, and browser authorization.
  2. Look up the exact pending device session via server-side state + user_code.
  3. Validate client, scopes, expiration, and decision authority.
  4. Atomically record DENIED; revoke/invalidate grant per AS model.
  5. Ensure the device-code token provider returns access_denied on poll.
  6. Render a safe denial confirmation page.
~~~

This is a **design contract**, not runnable copy-paste code. Spring Authorization Server 1.x provides providers/handlers for device verification and consent, but **you must not assume a `/device/deny` endpoint exists out of the box or that deleting `OAuth2Authorization` will make polling return `access_denied`**. Deleting the record can cause the token endpoint to treat the code as missing or expired and return a different error.

The team should choose one of two verified approaches on their exact version:

- Use the **framework-supported denial path** for your version's behavior and confirm via integration tests that polling returns `access_denied`.
- Or add a provider/handler paired with a denied-state model in the authorization store so the token endpoint understands `DENIED` without bypassing default validations.

When adding custom handlers, prefer keeping default providers intact and extending selectively rather than replacing the entire token endpoint. Never allow a user to submit another device's code to deny or approve on the owner's behalf.

### 10.4. The Denial UI Should Be Clear

A "Deny" button should appear alongside consent and require user action, without **submitting the same approval form along with selected scopes**. If the app implements a dedicated denial endpoint, use a separate POST form with CSRF, user code, and AS-verified correlation state. Never use `GET /device/deny?user_code=...` to mutate state.

After denial, the AS issues no codes or tokens; the device can display:

> The sign-in request on this device was denied. You can try again with a new code if you initiated this connection.

Do not expose the denying user's name, email, or grant details to the TV unnecessarily, as the TV or client could be controlled by someone else.

## 11. How Does Token Endpoint Polling Reflect the Decision?

The device calls:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Adevice_code&device_code=DEVICE_CODE_FROM_RESPONSE&client_id=booking-tv
~~~

For confidential clients, include client authentication per registration. A public client's `client_id` is not a secret; the token endpoint must verify `device_code` is bound to that client and inspect authorization state.

### 11.1. Standard RFC 8628 Responses

| Token endpoint response | Meaning | What the device must do |
| --- | --- | --- |
| `authorization_pending` | User has not completed interaction | Keep polling after at least `interval` |
| `slow_down` | Polling too fast | **Increase polling interval by 5 seconds** for all future polls |
| `access_denied` | Resource Owner denied the request | **Stop polling** and inform the user |
| `expired_token` | Device authorization session expired | **Stop polling**; start a new session only on user intent |
| HTTP success with `access_token` | AS confirmed grant conditions are met | Store token securely; call RS per scope/audience |
| `invalid_client` or other unrecoverable error | Invalid client or request | Stop, fix configuration error, do not spam AS |

If the initial response omits `interval`, the device waits **5 seconds** by default between polls. On `slow_down`, it must add 5 seconds for subsequent polls. On connection timeouts, RFC recommends backoff to reduce load on the AS. Any error other than those permitting continued polling must stop polling per the protocol. <https://www.rfc-editor.org/rfc/rfc8628#section-3.5>

### 11.2. Example Response Before User Decision

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "error": "authorization_pending"
}
~~~

Do not treat this HTTP 400 as "permanent device login failure." It is the normal Device Grant signal before the user approves or denies.

### 11.3. Example Response After Explicit Denial

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "error": "access_denied"
}
~~~

After this response, the client must stop polling the old code. Hiding the waiting spinner while still sending background requests violates protocol semantics and creates unnecessary load.

### 11.4. Difference Between Denied and Expired

- **Denied:** the user actively chose deny, and the AS recorded that state.
- **Expired:** `expires_in` elapsed without a valid decision, or the session closed under expiration policy.
- **Invalid code:** the request used a wrong code or one belonging to another client; exact responses depend on provider/RFC and code state.

Never record `access_denied` just because a browser session closed without choosing anything. Never issue a token from an expired code even if the user happened to click approve afterward.

## 12. Specific Security Risks: Remote Phishing and Device Ownership Verification

Device flow has a different risk surface from Authorization Code + PKCE: the user approves on **a different device** from the one requesting the token. Signals from the phone used for approval do not automatically prove the real TV is sitting next to the user.

### 12.1. Remote Phishing Attack Example

An attacker runs a client/device they control, obtains a `user_code`, and messages a victim:

> "Your account requires verification. Go to auth.example.test/device and enter code ABCD-EFGH."

If the victim complies and approves, tokens can be issued **to the attacker's device**, not the user's TV. This can succeed even when the verification URL is the genuine AS domain.

**Core defense:** The UI must remind users: "Approve only if you are actively signing in on a device right in front of you." Show the user code, application/client name, and scope set, plus verified device info if available. Provide a prominent deny button.

### 12.2. QR Codes Do Not Automatically Make the Flow Safer

`verification_uri_complete`/QR reduces typing, yet **skipping manual `user_code` entry** can raise the chance a user approves an attacker-supplied QR code. Therefore, the AS should still show the code and ask the user to compare it against the code displayed on the device.

Never auto-approve immediately on QR scan or deep-link open. Users must have a chance to read and make a deliberate choice.

### 12.3. Rate Limiting and Anti-Guessing for user_code

Because user codes are short for convenience, the AS must:

- Generate codes with sufficient entropy relative to expected attempt volume.
- Rate-limit attempts by account, IP, session, code, and appropriate risk signals.
- Keep TTLs short yet long enough for the user to open a browser, finish login/MFA, and decide.
- Never reveal user identity or sensitive client details on invalid codes.
- Throttle/lock repeated guessing sessions without causing mass user DoS.
- Avoid reusing completed codes within windows that could cause confusion, per AS safety policy.

`device_code` needs very high entropy because it acts as a credential at the token endpoint. `user_code` requires combining entropy, time limits, and rate limits. RFC 8628 covers these risks in its Security Considerations section. <https://www.rfc-editor.org/rfc/rfc8628#section-5>

### 12.4. Step-Up / MFA for Sensitive Devices

If the TV can view sensitive data or a device accesses internal documents, the AS may require MFA or additional verification **before approval**. Store and evaluate assurance context per policy and never let the consent endpoint bypass this step.

An "authenticated" flag from an old session does not prove the user just satisfied the assurance level required for a new device.

## 13. Sessions, CSRF, and the Authorization Store

### 13.1. Browser Login Requires Proper Session/CSRF Handling

On the secondary device:

- Form login and consent POSTs can rely on sessions/cookies.
- CSRF protection must be properly configured for state-changing requests.
- The session must retain the principal across login/verification/consent redirects.
- Switching accounts or logging out mid-flow must invalidate approval under the stale session.
- Cookies need proper `Secure`, `HttpOnly`, and `SameSite` policies over HTTPS.
- The request cache/success handler must resume the exact pending verification once the user logs in.

**Never disable CSRF across the whole Authorization Server** just because the consent POST returned 403. Instead, inspect the form token, session, matchers, callbacks, and endpoint policies.

### 13.2. Authorization Store Must Be Durable Across Multiple AS Instances

~~~mermaid
flowchart TD
    TV["TV requests codes / polls"]
    A["AS instance A"]
    B["AS instance B"]
    PHONE["Browser approves"]
    STORE[("Authorization / Consent Store<br/>consistent shared storage")]

    TV --> A
    TV --> B
    PHONE --> B
    A <--> STORE
    B <--> STORE
~~~

This can happen:

1. The device receives its device code from AS instance A.
2. The phone browser opens the verification URI and hits instance B.
3. The browser approves on B.
4. The TV polls instance A.

If instances only keep separate `InMemoryOAuth2AuthorizationService` instances, A may not see the decision recorded on B. You need durable, consistent shared storage—such as JDBC per Spring Authorization Server docs—and multi-instance/rolling-deployment tests.

### 13.3. Concurrent Approval and Polling

When the user clicks Approve at the exact moment the TV polls:

- The polling provider may return `authorization_pending` if the approval transaction has not committed yet.
- The next poll succeeds once state is committed.
- No token may be issued if the consent transaction fails or rolls back.
- If a denial and an approval arrive concurrently, enforce a **single final decision** rule; both must never take effect.
- Even after a token is issued, have policies for re-checking permissions or revoking if the user denied almost concurrently.

Production systems need real concurrency and transaction/locking tests against the actual authorization store, not just single-threaded MockMvc tests.

## 14. Testing Login, Consent, Approve, and Deny

### 14.1. Test Matrix

| Test case | Setup | What to verify |
| --- | --- | --- |
| Valid device request | Client `booking-tv` with `DEVICE_CODE` grant | AS issues both codes, verification URI, and lifetime |
| Unauthenticated browser | Open verification URI | AS redirects to login per policy |
| Login with wrong password | Attempt authentication | Cannot approve device session |
| Successful login | User authenticated | Resumes the right verification session |
| Wrong user code | Enter non-existent code | Does not open consent for another grant |
| Expired user code | Exceed `expires_in` | Cannot approve; device poll gets no token |
| Already-processed user code | Resubmit | Does not grant authorization a second time |
| QR complete URI | Browser already has user code | Still shows info to match code on TV |
| Full scope consent | User approves valid scopes | AS records approved scopes and token endpoint can issue token |
| Partial consent | Only `booking.read` selected | Token omits unapproved scopes |
| Tampered scope in form | Submit unregistered/unrequested scope | AS rejects; no privilege escalation |
| Tampered Client ID | Hidden field differs from registration | AS rejects; does not approve wrong client |
| Tampered `state` | POST with wrong state | AS rejects; no approval recorded |
| Missing CSRF | Consent POST | Blocked per policy |
| Click Deny | Valid denial per implementation | Browser reports denied; polling returns `access_denied` |
| Click Back / close browser | Submit no decision | Stays pending until timeout; never auto-approved |
| Poll before decision | Valid device code | `authorization_pending` |
| Poll too fast | Violate `interval` | `slow_down` per RFC/policy |
| Poll after expiration | Expired device code | `expired_token` |
| Device code with wrong client | Different public client ID or wrong client auth | Rejected; no token issued |
| Logged in to wrong account | User session differs from intended account | UI clarifies account and does not auto-approve |
| Two overlapping device sessions | Two pending user codes | Does not approve the wrong code |
| Concurrent approve/deny | Race condition | One final decision; no erroneous token issued |
| Two AS instances | Request/consent/poll hit two AS instances | Decision shared properly |
| User locked before approval | User status changes | Security policy enforced; no unauthorized grant |

### 14.2. Testing Browser Login

Use `spring-security-test` and MockMvc to verify the verification page requires a logged-in user. Skeleton example:

~~~java
@Test
void deviceVerificationRequiresAuthenticatedResourceOwner()
        throws Exception {
    mockMvc.perform(get("/oauth2/device_verification")
            .accept(MediaType.TEXT_HTML))
        .andExpect(status().is3xxRedirection())
        .andExpect(header().string(
            "Location", containsString("/login")));
}
~~~

Adapt this example to the GET endpoint and default verification page policy of **your exact version**. If the user-code entry page allows anonymous GET and requires login on POST, tests must reflect that design; the mandatory invariant is **never completing verification/consent while unauthenticated**.

### 14.3. Testing Custom Consent

For a custom consent page, include tests verifying:

1. Authenticated browser + valid pending `user_code` → renders right client name and scopes.
2. Page uses only registration/server state for names and permission descriptions; never echoes HTML/JavaScript from query params.
3. Form POST sends exact `client_id`, `state`, `user_code`, chosen scopes, and CSRF token when required.
4. POSTing a scope outside the grant → rejected.
5. POSTing for an expired user code → rejected.
6. POSTing from an ineligible user/account → rejected.
7. Successful approval → updates state; device poll gets token with matching client/scopes.
8. Successful denial → updates state; device poll gets `access_denied` and stops.
9. Two concurrent state-mutating requests cannot both succeed.

`@WithMockUser` helps test some authorization rules, yet **does not prove** login, session storage, consent providers, or device token polling actually work. End-to-end tests must run through the real filter chain and a real/reliable authorization store fixture.

### 14.4. Polling Tests Must Follow RFC 8628

A compliant device should:

~~~text
Initialize interval = response.interval if present, else 5 seconds
Loop until success, denial, expiration, or terminal error:
  - Wait at least interval before the next attempt
  - authorization_pending -> keep interval and retry
  - slow_down -> increase interval by 5 seconds, then retry
  - timeout -> back off; do not spam AS
  - access_denied / expired_token -> stop
  - success -> stop, store access token securely
  - other terminal error -> stop and report
~~~

This is pseudocode for **client** behavior, not a Java bean inside the AS. Client-side tests should simulate clocks, timeouts, retry/backoff, and flow cancellation when the user exits the pairing screen.

## 15. Operations and Diagnostics

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| TV has code but verification URL gives 404 | Endpoint disabled, wrong settings/matcher | Check `AuthorizationServerSettings` and device verification configurer |
| Browser enters code and hits login redirect loop | Login/verification in wrong chain or session not saved | Check `@Order`, security matcher, login entry point, session cookie |
| User code lost after login | Request cache/redirect drops correlation | Preserve verification context server-side; test across login redirect |
| Consent shows wrong client name | UI trusts `client_id`/name from query | Query `RegisteredClientRepository` and check pending state |
| Consent POST returns 403 | Missing CSRF, expired session, wrong state | Check form, CSRF/session; never disable CSRF globally |
| Approved, yet TV stays pending | Unshared authorization store or uncommitted transaction | Test multi-instance/persistence; monitor authorization updates |
| Clicked Deny, yet TV stays pending | UI only closed page without saving denial state | Implement/test explicit denial per contract |
| Clicked Deny, yet TV gets `expired_token` instead of `access_denied` | Record deleted/expired instead of recording denial | Check how provider/token endpoint interprets state |
| TV polls very rapidly | Ignores `interval` or `slow_down` | Fix client/backoff and rate-limit |
| Frequent code-guessing attempts | Weak entropy/rate limiting | Throttle and add security monitoring |
| Signs of remote phishing | Victim tricked into entering attacker's device code | Warn users, revoke tokens, strengthen device ownership confirmation |
| User approved, yet API returns 403 | Mismatched scope/audience or data permissions | Inspect token and RS policy independently |

### 15.1. What to Log Safely

Include request ID, correlation ID, trusted client ID, endpoint type, creation/expiration timestamps, logical state and policy outcome, approve/deny events, and polling latency.

Never log raw `device_code`, full `user_code`, session cookies, access tokens, refresh tokens, client secrets, or unnecessary personal data. When correlating events across a session, use an internal audit ID or protected token identifier under a retention policy.

### 15.2. Useful Metrics to Monitor

- Ratio of device sessions moving from pending to approved/denied/expired.
- P50/P95 duration from device request to user completion.
- Invalid user-code entry rates and rate-limit hit counts.
- Polling requests per device session and `slow_down` rate.
- Token issuance failure rate after approval.
- State discrepancies across AS instances.
- Suspected remote phishing events, revocations, and session compromises.

Never increase log verbosity by printing full raw codes just to make metrics easier to compute.

## 16. Illustrative Scenario: Pairing Booking TV

A user opens the Booking app on a TV and selects "Link Account." The TV requests `device_code` and `user_code`, displaying code `WDJB-MJHT` alongside the AS URL. Lan visits the URL on her phone and signs in. The AS locates the pending device session and shows that **Booking TV** is requesting permission to read bookings and profile info.

**If it really is Lan's TV**, she matches the code and approves `booking.read` while optionally withholding `profile` if policy allows partial consent. The AS records the outcome, and the TV receives an access token on its next valid poll. The Booking API still verifies token expiration, issuer, audience, scopes, and allowed data records.

**If Lan never touched the TV**, she clicks **Deny**. The AS records the denial, and the waiting TV/device receives `access_denied`. No token is issued merely because Lan signed in on her phone.

**If Lan closes the browser without choosing**, the device stays pending until expiration. That outcome differs from explicit denial; UI and logs must distinguish both cases.

## 17. Mistakes to Avoid

| Mistake | Consequence | Fix principle |
| --- | --- | --- |
| Treating user login as approval | Issues token without user agreement | Require verification + valid consent/decision |
| Displaying `device_code` to the user | Exposes token endpoint credential | Display only `user_code` |
| Using `user_code` to exchange for token | Breaks protocol, widens attack surface | Token endpoint expects `device_code` |
| Issuing token when user opens verification URI | Bypasses user decision | Require authentication, code comparison, and approval |
| Trusting all consent page query parameters | Approves wrong client/scopes | Load registration and pending server state; revalidate on POST |
| Auto-approving on QR scan | Easy target for remote phishing | Show code, client, scopes, and explicit decision buttons |
| "Deny" only closes the page | TV stays pending with no decision | Persist denial and ensure polling receives error |
| Deleting authorization and assuming `access_denied` | May return expired/invalid token instead of denial | Design consistent denial state/provider |
| Confusing `state` with `_csrf` | CSRF/correlation flaws, may permit forged POSTs | Enforce both mechanisms properly |
| Consent from anonymous browser | Strangers can approve | Require Resource Owner authentication |
| Disabling CSRF globally | Weakens login and consent forms | Protect POSTs per matcher/policy |
| Not throttling user codes | Brute-forcing short user codes | Entropy, TTL, rate limits |
| Ignoring polling interval | Overloads AS and violates RFC | Respect `interval`/`slow_down` |
| Running multiple AS instances with separate in-memory stores | Device polls miss approvals | Shared authorization store |
| Treating TV-supplied display name as trusted device | Device spoofing | Separate registration metadata from hardware attestation |
| Skipping scope checks at RS | TV reads beyond granted permissions | RS checks audience/scopes/object-level permissions |

## 18. Self-Check Questions

**Question 1.** Why is opening `verification_uri` and logging in not enough for the device to receive an access token?

**Answer:** Login only authenticates the Resource Owner. The AS must also verify the matching user code/device session, check client/scopes, obtain consent, and record a valid approval decision.

**Question 2.** How do `device_code` and `user_code` differ?

**Answer:** `device_code` is a high-entropy credential for the device to poll the token endpoint; `user_code` is a short code for the user to enter/match in the verification browser. Never swap their roles.

**Question 3.** When scanning a QR code with `verification_uri_complete`, can the user skip checking the code on the TV?

**Answer:** No. The AS should still let the user match the code and confirm the device actually being paired to mitigate remote phishing.

**Question 4.** Can `OAuth2AuthorizationEndpointConfigurer.consentPage(...)` be used to customize the device flow consent page?

**Answer:** That is not the right configuration point. Device flow uses `OAuth2DeviceVerificationEndpointConfigurer.consentPage(...)`, and the form POSTs to the device verification endpoint.

**Question 5.** What parameters does a device flow consent form need?

**Answer:** Under the SAS 1.x API, at minimum `client_id`, `state`, `user_code`, and the approved `scope` values, plus a CSRF token if required by security policy. POST to `AuthorizationServerSettings.getDeviceVerificationEndpoint()`.

**Question 6.** A user clicks "Deny," and the backend simply redirects to "Denied" without updating the authorization. Is that sufficient?

**Answer:** No. Device polling may stay pending until expiration. You need an AS-recorded denial decision that blocks token issuance and returns an appropriate token endpoint outcome such as `access_denied`.

**Question 7.** Should the TV handle `authorization_pending` and `slow_down` identically?

**Answer:** Not quite. Both allow polling to continue, but `slow_down` requires adding 5 seconds to the wait interval for all subsequent polls.

**Question 8.** If the user's browser and polling requests hit two different AS instances, what is the main issue?

**Answer:** Both must observe the same device authorization state and consent decision. Isolated in-memory stores can cause inconsistent state.

**Question 9.** After approval, can the TV access every booking?

**Answer:** No. The access token only carries permissions granted under policy; the Resource Server must check the token, scopes, audience, and per-object permissions.

## 19. Pre-Production Checklist

- [ ] Client/device is registered with the right `DEVICE_CODE` grant and allowed scopes.
- [ ] Device Authorization/Verification/Token Endpoints are enabled and use URLs from proper settings/metadata.
- [ ] `device_code` has high entropy, is never shown to users, and is never logged.
- [ ] `user_code` has sufficient entropy and is protected by TTL/rate limits/brute-force controls.
- [ ] Device displays the official AS URL and user code; QR is only an input convenience.
- [ ] Browser verification requires user authentication and MFA/step-up per policy.
- [ ] Consent displays exact client, scopes, and code matching the device.
- [ ] Approval form uses exact `client_id`, `state`, `user_code`, scopes, CSRF token, and POST endpoint.
- [ ] Custom consent does not bypass Spring Authorization Server's default providers/validators.
- [ ] "Deny" button genuinely prevents token issuance and polling returns the tested error contract.
- [ ] Denied, pending, expired, and invalid states are distinct across UI, API, and audit logs.
- [ ] Device client honors `interval`, `slow_down`, timeout/backoff, and stops polling on terminal errors.
- [ ] Phone browser session is never treated as the TV's token.
- [ ] Authorization/consent store is shared and consistent across multiple AS instances.
- [ ] Tests cover wrong user code, tampered scope/state, anonymous access, expiration, approve/deny, and race conditions.
- [ ] Controls mitigate remote phishing, code guessing, and session compromise.
- [ ] Policies exist for revocation and handling access tokens after a device is lost or revoked.

## 20. References and Standards

Verify against your exact running Spring version:

- [RFC 8628 — OAuth 2.0 Device Authorization Grant](https://www.rfc-editor.org/rfc/rfc8628)
- [RFC 8628, Section 3.3 — User Interaction](https://www.rfc-editor.org/rfc/rfc8628#section-3.3)
- [RFC 8628, Section 3.5 — Token Endpoint Responses](https://www.rfc-editor.org/rfc/rfc8628#section-3.5)
- [RFC 8628, Section 5 — Security Considerations](https://www.rfc-editor.org/rfc/rfc8628#section-5)
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server — OAuth2DeviceVerificationEndpointConfigurer API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OAuth2DeviceVerificationEndpointConfigurer.html)
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html)
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)

## 21. Conclusion

In Device Authorization Grant, **the TV initiates the request**, while **the user decides** whether to grant access by signing in and completing consent on a secondary browser. `user_code` identifies the pending session; `device_code` is the device's credential at the token endpoint. Signing in does not mean consent has been granted.

To implement this properly on Spring Authorization Server, connect **Device Authorization Endpoint → Device Verification Endpoint → user login/consent → approval/denial state in the authorization store → Device Code Grant at the Token Endpoint** cleanly. The approval branch must grant only the consented scopes; the denial branch must genuinely block token issuance and signal the protocol outcome rather than merely changing the UI. Combined with defenses against phishing, CSRF, code guessing, rapid polling, multi-instance state drift, and concurrency bugs, your system can let users pair input-constrained devices safely and reliably in production.
