# 7.11. AuthenticationFailureHandler and User Consent Denial Experience

## 1. The Problem: User Clicks "Deny" on the Consent Screen

In a **Spring Security OAuth 2.0 OIDC Client** application using Servlet, logging in through an identity provider usually involves two visible steps: the user authenticates at the provider (*Identity Provider*, IdP), then approves or denies the permissions requested by the application. Some providers skip the consent screen if the user already agreed previously, yet the application must still handle unsuccessful authorization.

For example, an internal Spring Boot portal requests scopes `openid`, `profile`, and `email`. When the browser redirects to the IdP, the user clicks **Cancel / Deny**. Instead of returning an authorization code, the IdP may send the browser back to the application's callback with an error:

~~~http
HTTP/1.1 302 Found
Location: https://portal.example.com/login/oauth2/code/company?error=access_denied&state=STATE_VALUE
~~~

The application needs to respond clearly:

- Recognize this as an **unsuccessful login/authorization transaction**.
- Never create a new login session from a failed callback.
- Display a neutral message, such as "You cancelled or the permission request was not approved".
- Let the user choose to **try again**, **return to a public page**, or **contact support** when needed, without infinitely redirecting back to the IdP.
- Never render raw `error_description` or internal provider details in the UI.

In Spring Security Servlet, the appropriate extension point for **OAuth2/OIDC login failures that pass through the authentication filter** is `AuthenticationFailureHandler`, configured via `oauth2Login().failureHandler(...)`.

**Keep this distinction clear:** "user denied consent" is one possible failure reason; **not every OAuth2/OIDC login failure means the user denied consent**. Misconfigured redirect URIs, state errors, expired codes, network errors, or invalid tokens require different explanations.

## 2. Normal Flow vs. Denial Branch

### 2.1. Two outcomes from the authorization endpoint

In the Authorization Code flow, Spring Security initiates a request to the provider's authorization endpoint:

~~~http
GET /authorize?response_type=code
    &client_id=portal-client
    &redirect_uri=https%3A%2F%2Fportal.example.com%2Flogin%2Foauth2%2Fcode%2Fcompany
    &scope=openid%20profile%20email
    &state=RANDOM_STATE
    &code_challenge=PKCE_CHALLENGE
    &code_challenge_method=S256
Host: id.example.com
~~~

This request is wrapped across lines for readability; the actual URL must be properly encoded. The provider may approve or deny the transaction.

**Approval case:**

~~~text
/login/oauth2/code/company?code=AUTHORIZATION_CODE&state=RANDOM_STATE
~~~

Spring Security matches the transaction, exchanges the code at the token endpoint, and continues OIDC authentication. If valid, the application can establish a login session.

**Denial case:**

~~~text
/login/oauth2/code/company?error=access_denied&state=RANDOM_STATE
~~~

There is no valid authorization code to exchange for tokens; Spring Security processes the authentication failure. `AuthenticationFailureHandler` decides the final HTTP response for the browser, such as redirecting to an explanation page.

### 2.2. Flow diagram with failure handler

~~~mermaid
sequenceDiagram
    autonumber
    actor U as User / Browser
    participant C as Spring Boot Servlet Client
    participant P as OAuth2/OIDC Provider
    participant F as AuthenticationFailureHandler
    U->>C: GET /reports (requires login)
    C-->>U: Redirect to /oauth2/authorization/company
    U->>C: Start OAuth2 Authorization
    C-->>U: Redirect to authorization endpoint
    U->>P: Authenticate and view consent screen
    alt User approves
        P-->>U: Redirect callback with code + state
        U->>C: GET /login/oauth2/code/company?code=...
        C->>P: Exchange code for tokens
        P-->>C: Access Token and ID Token if OIDC
        C-->>U: Login succeeds, enter application
    else User denies / provider denies
        P-->>U: Redirect callback with error=access_denied + state
        U->>C: GET /login/oauth2/code/company?error=...
        C->>F: onAuthenticationFailure(request, response, exception)
        F-->>U: Redirect /auth/feedback?status=cancelled
        U->>C: GET /auth/feedback
        C-->>U: Explanation page and retry options
    end
~~~

In both branches, saving and verifying `state`, managing the callback, and exchanging tokens remain Spring Security's responsibility. The application should simply provide an appropriate failure UI after the framework processes the callback via standard mechanics.

## 3. How Does OAuth 2.0 Report Errors?

Under the OAuth 2.0 protocol, the authorization server can redirect back to the client with error query parameters. For example:

~~~http
GET /login/oauth2/code/company?error=access_denied
    &error_description=The%20request%20was%20not%20approved
    &state=RANDOM_STATE HTTP/1.1
Host: portal.example.com
~~~

Common fields:

| Parameter | Purpose | Should it be shown verbatim in UI? |
| --- | --- | --- |
| `error` | Machine-readable error code, e.g., `access_denied` | Map to an allowed UI status |
| `error_description` | Optional provider explanation | **Do not** display verbatim, as it is external input |
| `error_uri` | Optional error documentation URI | Never auto-link redirects to untrusted URIs |
| `state` | Value binding the response to the prior authorization request | Spring Security handles per transaction; do not display |

OAuth 2.0 error codes at the authorization endpoint can include:

| Error code | General meaning | UX handling suggestion |
| --- | --- | --- |
| `access_denied` | Resource owner or authorization server denied the request | Inform that permission was not granted; offer back and retry buttons |
| `invalid_request` | Request is missing/malformed or invalid | Inform login could not complete; ops team checks configuration |
| `unauthorized_client` | Client is not permitted to use this request method | Do not tell the user to keep retrying; check provider configuration |
| `unsupported_response_type` | Provider does not support requested response type | Integration/configuration error |
| `invalid_scope` | Requested scope is invalid, unknown, or disallowed | Scope/policy error; do not assume user clicked deny |
| `server_error` | Provider could not process the request | Show temporary error; allow deliberate retry |
| `temporarily_unavailable` | Provider temporarily out of service | Suggest retrying later; avoid automatic redirect loops |

Other errors can happen at the **token endpoint** or during OIDC verification, such as `invalid_client`, `invalid_grant`, wrong issuer, invalid ID Token signature, or state mismatch. Even though they also route through the failure handler, **they are not `access_denied`** and must be treated as distinct failures.

**Important detail:** `access_denied` does not prove for certain that the user actively clicked "Deny"; the authorization server may deny due to organizational policy, mandatory consent rules, or account restrictions. The UI should use neutral wording instead of blaming the user.

## 4. What Is AuthenticationFailureHandler?

`AuthenticationFailureHandler` is the Spring Security interface used to **determine the HTTP response when authentication fails** in Servlet authentication processing.

Method signature:

~~~java
import java.io.IOException;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.authentication.AuthenticationFailureHandler;

public interface AuthenticationFailureHandler {
    void onAuthenticationFailure(
        HttpServletRequest request,
        HttpServletResponse response,
        AuthenticationException exception
    ) throws IOException, ServletException;
}
~~~

This signature is an illustration of the interface. Examples for Spring Boot 3/Spring Security 6 and later use `jakarta.servlet.*`. Older Spring Boot 2 apps use a different Servlet namespace and may use different DSL syntax; do not mix APIs across the two generations.

When an authentication filter catches an `AuthenticationException`, Spring Security can invoke the handler to:

- Redirect the browser to a safe URL.
- Return an informational HTML page.
- Return structured JSON errors when the client is genuinely an API app.
- Log non-sensitive metadata about the failure event.
- Choose a support or retry path based on failure type.

The handler is **not responsible for issuing Access Tokens**, creating ID Tokens, fixing JWT signatures, or bypassing `state` validation. Nor is it `AccessDeniedHandler`, which handles authenticated users denied access to an application resource.

### 4.1. Distinguishing similarly named components

| Component | When used? | Example |
| --- | --- | --- |
| `AuthenticationFailureHandler` | Login/authentication failed | OAuth2 callback has `error=access_denied`; bad authorization code |
| `AuthenticationSuccessHandler` | Login succeeded | Redirect to saved page; send post-login response |
| `AuthenticationEntryPoint` | Unauthenticated access to a protected resource requiring login initiation | Redirect unauthenticated browser to login page |
| `AccessDeniedHandler` | An HTTP request is denied authorization by Spring Security | Logged-in user lacks permission to view admin page |
| `OAuth2UserService` / `OidcUserService` | Load/map user info after valid OAuth2/OIDC exchange | Fetch UserInfo and build principal |
| `OAuth2AuthorizationRequestRepository` | Store authorization request for callback verification | Manage `state` and original request |

One application might need all four of the error/entry components above. Never configure `AccessDeniedHandler` expecting it to catch an `error=access_denied` callback: those are two completely different contexts despite both names containing "denied".

### 4.2. Where is the failure handler called in OAuth2 Login?

Standard Spring Security Servlet flow:

~~~text
GET /oauth2/authorization/company
    -> OAuth2AuthorizationRequestRedirectFilter
    -> redirect to Authorization Server

GET /login/oauth2/code/company?... 
    -> OAuth2LoginAuthenticationFilter
    -> authentication manager/provider handles response
    -> success: AuthenticationSuccessHandler
    -> failure: AuthenticationFailureHandler
~~~

Errors **before the callback reaches the login filter**—such as failing to build an authorization request, connection errors fetching startup metadata, or exceptions in other filters—**do not necessarily pass through** `oauth2Login().failureHandler(...)`. For those cases, inspect the actual failure point and configure appropriate handling; do not rely on one handler to catch every protocol failure.

## 5. Complete Example for Spring Security Servlet

This section illustrates a Spring Boot app with an OIDC provider named `company`. When the user denies consent, the browser redirects to a friendly feedback page. For other errors, the app shows a generic technical notice while operations investigate via safe logs.

### 5.1. Dependencies and ClientRegistration

Example `build.gradle` for Spring Boot 3.x with Spring Boot plugin and dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
}
~~~

On Spring Boot 4.x, the corresponding starter names are `spring-boot-starter-webmvc` and `spring-boot-starter-security-oauth2-client`; pick per your project's actual BOM/version. Thymeleaf is only used to render the example page; replace with your preferred view engine or frontend.

`application.yml` configuration:

~~~yaml
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
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          company:
            issuer-uri: https://id.example.com/realms/company
~~~

Replace the illustrative issuer and client ID with verified provider details. The actual Redirect URI must match the URI registered at the IdP. Never commit client secrets, and use valid HTTPS in production.

### 5.2. Implementing the failure handler: classify only known errors

Placed at `src/main/java/com/example/security/OAuth2LoginFailureHandler.java`:

~~~java
package com.example.security;

import java.io.IOException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.web.authentication.AuthenticationFailureHandler;
import org.springframework.stereotype.Component;

@Component
public final class OAuth2LoginFailureHandler implements AuthenticationFailureHandler {

    @Override
    public void onAuthenticationFailure(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException exception) throws IOException {

        // Values exposed to the UI must come from a fixed allowlist.
        String status = "failed";

        if (exception instanceof OAuth2AuthenticationException oauth2Exception) {
            String errorCode = oauth2Exception.getError().getErrorCode();
            if ("access_denied".equals(errorCode)) {
                status = "cancelled";
            }
        }

        // Fixed internal redirect; never append error_description from the provider.
        String target = request.getContextPath() + "/auth/feedback?status=" + status;
        response.sendRedirect(target);
    }
}
~~~

Explanation of each choice:

1. `AuthenticationException` is the general exception; for OAuth2 errors, Spring Security can provide `OAuth2AuthenticationException` and `OAuth2Error` containing the error code.
2. Only `access_denied` maps to UI status `cancelled`. Other errors map to `failed`; do not label every error as "user denied".
3. `status` is chosen from **two fixed values**, so neither `error_description` nor arbitrary browser parameters enter the destination URL.
4. Redirect uses `request.getContextPath()` and an application-controlled internal path; it never accepts a target URL from query parameters or provider-supplied values.
5. The example code logs no sensitive data, does not mutate sessions/authorized clients manually, and does not interfere with Spring Security's state verification.

Depending on the scenario, an OAuth2 error might be wrapped in another `AuthenticationException` or occur in a different filter; the handler has a **safe fallback** of `failed`. For finer classification, test against your actual environment and observe framework/provider error codes.

### 5.3. Wiring the handler into `SecurityFilterChain`

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            OAuth2LoginFailureHandler loginFailureHandler) throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/", "/login", "/auth/feedback",
                    "/error", "/css/**", "/images/**"
                ).permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .failureHandler(loginFailureHandler))
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

Two essential decisions:

- `oauth2Login(...failureHandler(...))` attaches the handler to the **login flow** rather than registering a global `@ControllerAdvice` across the entire app.
- `/auth/feedback` is a **public page**. If the error page itself required login, the filter would trigger OAuth2 login again, trapping the user in a redirect loop right after denying consent.

With multiple `SecurityFilterChain` beans, attach `oauth2Login()` and the failure handler to the chain that actually handles the callback. Chain ordering and `securityMatcher` rules can cause another chain to intercept the request first.

### 5.4. Controller displaying the feedback page

Placed at `src/main/java/com/example/web/AuthFeedbackController.java`:

~~~java
package com.example.web;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@Controller
public class AuthFeedbackController {

    @GetMapping("/auth/feedback")
    public String feedback(
            @RequestParam(defaultValue = "failed") String status,
            Model model) {

        boolean cancelled = "cancelled".equals(status);
        if (cancelled) {
            model.addAttribute(
                "heading",
                "Sign-in was not completed");
            model.addAttribute(
                "message",
                "You cancelled or the requested permissions were not approved by the provider.");
        } else {
            model.addAttribute(
                "heading",
                "Unable to complete sign-in");
            model.addAttribute(
                "message",
                "An issue occurred during sign-in. You can try again or contact support.");
        }

        return "auth-feedback";
    }
}
~~~

Here the controller **never prints the raw `status` value into HTML**; it only uses the value to pick between two predefined message sets. This protects the UI if a user directly edits `?status=...` in the URL.

Create the Thymeleaf template at `src/main/resources/templates/auth-feedback.html`:

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Sign-in Notice</title>
</head>
<body>
<main>
    <h1 th:text="${heading}">Sign-in Notice</h1>
    <p th:text="${message}">Sign-in was not completed.</p>

    <p>
        <a th:href="@{/login}">Back to sign-in options</a>
    </p>
    <p>
        <a th:href="@{/}">Go to home page</a>
    </p>
</main>
</body>
</html>
~~~

In the template above, `th:text` renders content using Thymeleaf's HTML escaping. Links use application-controlled paths and support context paths. `/login` may be Spring Security's generated default login page or your custom login page; if using a custom login route, update the link accordingly.

**Never build a "Retry" button using JavaScript that auto-triggers repeatedly.** A link letting the user intentionally choose to retry is clearer and safer. If the app offers multiple providers, send them back to the provider chooser instead of assuming they always want to retry the same provider.

### 5.5. When to use a built-in handler instead of a custom class?

If every failure should redirect to the same page, Spring Security offers `SimpleUrlAuthenticationFailureHandler`:

~~~java
import org.springframework.security.web.authentication.SimpleUrlAuthenticationFailureHandler;

// Can be configured as:
SimpleUrlAuthenticationFailureHandler handler =
    new SimpleUrlAuthenticationFailureHandler("/auth/feedback?status=failed");
~~~

Attach via `oauth2Login(oauth2 -> oauth2.failureHandler(handler))`. This is simple, though it **does not distinguish** `access_denied` from configuration errors. When you want tailored UX for user consent denial, a custom `AuthenticationFailureHandler` like the example above is a better fit.

## 6. Designing the Experience When Users Deny Consent

A denial handling page should answer three questions: **What happened? Was access granted? What can the user do next?**

### 6.1. Appropriate messaging

| Scenario | Recommended message | Appropriate action |
| --- | --- | --- |
| User denies consent or provider denies `access_denied` | "The sign-in or permission request was not approved. No account connection was made this time." | Go back, retry when ready |
| User declines a sensitive scope | "To use this feature, the app needs the described permission. You may go back if you prefer not to grant it." | Explain scope purpose, stop or pick another feature |
| Provider temporarily unavailable | "Unable to connect to the sign-in provider right now. Please try again later." | Intentional retry button, support link |
| Client misconfigured or invalid token | "Unable to complete sign-in. Please contact support if this persists." | Provide support code / correlation ID if available |
| User declines while linking an additional external account | "Account was not linked. You may continue working in the app if your current session is valid." | Return to linked accounts page, preserve work data |

Avoid messages like "You made a mistake", "Security system failed", or "Unauthorized to use system" when all you know is `access_denied`. A user might deliberately withhold consent for privacy reasons; UX should not pressure them into repeating consent.

### 6.2. Principle of clarifying requested scopes

Before redirecting to the provider, explain why permissions are needed: `openid` for OIDC login, `profile` for name/avatar if available, `email` to read email when permitted, and business scopes like `calendar.read` or `files.read` for specific features.

Never display "The app needs full access" if it only reads a specific piece of data. If features can work with fewer permissions, consider **minimum scopes** and request extra scopes only when needed (*incremental authorization*) if supported by the provider. When a user denies optional permissions, an auxiliary feature can degrade gracefully without breaking everything else.

### 6.3. Avoiding redirect loops

The following design can cause a loop:

~~~text
User denies at IdP
    -> failure handler redirects to /private-page
    -> /private-page requires login
    -> Spring Security redirects back to IdP
    -> user denies again
    -> back to /private-page ...
~~~

To avoid this:

1. Ensure the feedback page is public and does not automatically start OAuth2 login.
2. Provide a **user-initiated retry** button/link.
3. When using pre-login saved requests, never automatically replay the saved request after a failed login transaction, which would bounce the browser straight back to the protected URL in a loop.
4. Provide a way back to a public home page or support contact.

In SSO systems with multiple login methods, let the user choose another provider if allowed by the product; never silently switch providers or merge accounts without user action.

### 6.4. Do not conflate authentication failure with missing business authorization

For instance, a user completes OIDC login successfully yet is denied access to the app's admin page. That is normally a `403 Forbidden` handled by `AccessDeniedHandler` or application policy. Conversely, clicking "Cancel" at the IdP **before granting login permission** is an OAuth2/OIDC authentication failure routed through the login failure handler.

| Event | Handling layer | What user should see |
| --- | --- | --- |
| Clicked "Deny" on OAuth consent | OAuth2 login failure handler | Login/authorization transaction was not completed |
| Invalid state on OAuth callback | OAuth2 login failure handler during callback, if caught by filter | Sign-in did not complete; may try again |
| Logged in, yet accesses admin page without role | Authorization / `AccessDeniedHandler` | Insufficient permissions for this feature |
| Downstream API returns `403` due to missing scope | HTTP client / API error handling | Feature lacks required API permission |
| Provider unreachable during startup discovery | Application config / startup handling | Integration/ops incident; does not necessarily hit login failure handler |

## 7. Security and Privacy of the Failure Handler

### 7.1. Never trust callback query parameters directly

An OAuth2 callback may contain `error`, `error_description`, and `state`. These arrive via the browser and must only be processed inside a valid authorization transaction context. **Never write a public controller accepting `error=access_denied` and treating every hit as "user denied"** or updating security state from it.

Spring Security stores the authorization request to bind the callback to a transaction, validate `state`, and run protocol checks. The failure handler receives `AuthenticationException` after the authentication filter's processing; it **does not replace** transaction verification.

If callback query params are forged or lack a matching authorization request, the framework may raise an error other than `access_denied`. In those cases, the handler should fall back to a generic error branch rather than asserting the user declined consent.

### 7.2. Never reflect `error_description` to the browser

Suppose a provider sends:

~~~text
error=access_denied
error_description=<untrusted text or HTML>
~~~

Taking `error_description` and placing it straight into HTML risks **cross-site scripting (XSS)** or leaking provider configuration details. Even when the framework or template engine escapes HTML, provider descriptions can still reveal details meant to stay internal.

Safe approach: classify known error codes and show application-managed messages. The UI can display a random support code / correlation ID while server logs store minimal matching technical info.

### 7.3. Never redirect to user- or provider-controlled URLs

Example to avoid:

~~~java
// Anti-pattern - do not use in applications:
String target = request.getParameter("returnUrl");
response.sendRedirect(target);
~~~

Without strict allowlisting/validation, this creates an **open redirect**. OAuth logins are especially sensitive to redirecting off-domain, particularly when URLs carry session state or related codes.

Use fixed internal routes for error states. If the product needs to return to an earlier screen, save a safe application-validated navigation intent beforehand rather than accepting arbitrary destination URLs from the callback.

### 7.4. How to log safely

Record operationally helpful metadata such as:

~~~text
event=oauth2_login_failed
registration=company
outcome=consent_not_granted
correlation_id=7c9b... 
http_route=/login/oauth2/code/company
~~~

This is an illustrative log format; do not log fields lacking verified data. If the framework could not verify the transaction, do not confidently attribute the failure to a specific account or registration based solely on untrusted query parameters.

Never log:

- `authorization_code` or full callback URLs containing `code` and `state`.
- Access Tokens, ID Tokens, Refresh Tokens, or client secrets.
- Raw `error_description` when it may contain sensitive data or externally controlled strings.
- Full email addresses or usernames unless justified by business needs with matching retention and access controls.

For troubleshooting, use safe error enums and correlation IDs, restricting log read permissions, retention periods, and log volume to guard against log flooding from spoofed callbacks.

### 7.5. Handling sessions and authorized clients after failure

Never assume an `access_denied` callback produces a new `OAuth2AuthorizedClient` or new tokens: when an Authorization Code flow is denied, there is normally **no code to exchange for tokens**.

However, if a user **is already logged in** and attempting to link an additional provider, existing session/authorized client state needs careful design. `AbstractAuthenticationProcessingFilter` and failure paths can affect `SecurityContext` in the request; do not assume every prior session is always preserved or always destroyed.

If the feature is "connect an external service account" within an active session, intentionally design the linking flow, preserve work data, and verify `Authentication` persistence; you may need a dedicated flow instead of treating every new OAuth2 callback as a replacement login.

## 8. Login Failure vs. "External Service Connection" Failure

Two screens might both use the OAuth Authorization Code flow while having different business goals:

| Use case | If user denies | Desired response |
| --- | --- | --- |
| **Primary portal login** via IdP | New identity not authenticated | Create no new login; show public feedback page with retry option |
| **Linking Google Drive/Calendar** to existing logged-in account | External API permission not granted | Keep integration management screen if session remains valid; mark link incomplete |
| **Requesting extra scope for an optional feature** | Optional feature not authorized | Explain minimum permissions needed; let user return to working parts |
| **Switching login provider** | Transaction with new provider incomplete | Keep existing login/identity policy; do not auto-merge accounts |

For example, a user logged into the portal with a company account wants the portal to read their calendar, then denies the `calendar.read` scope. That **does not mean the user lost permission to log into the portal**; it only means the token/delegation for the calendar feature was not granted. Integration flows may require separate authorized-client handling and failure UI rather than reusing primary OIDC login logic as "connect account".

When linking accounts across providers, avoid updating internal account links until required tokens are received and subject/consent checks pass. Never mark an integration as connected just because the browser returned to a callback.

## 9. Scaling the Failure Handler for Multiple Providers

Suppose the portal supports logging in with `company` and `partner`. When a transaction fails, UX can direct users back to the **provider selection page** to try again. Never read `registrationId` from an arbitrary query param to redirect straight to a domain or create a login loop.

A clean design uses fixed UI statuses:

~~~text
/auth/feedback?status=cancelled
    -> "You cancelled or the request was not approved."
    -> /login button to pick a provider

/auth/feedback?status=failed
    -> "Unable to complete sign-in."
    -> /login button, home page, support
~~~

If displaying the provider name is genuinely needed, map from a **configured, trusted list of registrations** to a display label like "Company Account", rather than showing issuer URLs or callback values. With multiple login options, a shared feedback page prevents users from getting stuck on one provider.

### 9.1. Using error codes in business metrics

Measuring real failures helps improve onboarding:

| Metric | Interpretation |
| --- | --- |
| Number of OAuth2 logins started | Total authorization transactions initiated |
| Share of callbacks with `access_denied` | Transactions denied per provider code; not necessarily all user-initiated |
| Protocol/token error rate | Potential configuration, environment, or provider issues |
| User manual retry rate | Effectiveness of the feedback page |
| Hits to feedback page without a valid transaction | Do not count automatically as login failures since the feedback URL is public |

Metrics should focus on **aggregate counts** and safe error codes. Never store full consent responses or user profiles just to analyze denial rates.

## 10. Controlled Scenario Testing

When developing with a test OIDC provider, verify the UX across these scenarios. These are **expected behaviors for learning**, not test execution results:

| Scenario | Trigger | Expected outcome |
| --- | --- | --- |
| User approves scopes | Login succeeds, provider returns `code` | Spring Security processes tokens and navigates per success handler |
| User clicks deny | Provider returns `error=access_denied` at callback | Failure handler selects `cancelled` and redirects to feedback page |
| Temporary provider error | Provider returns `server_error` or `temporarily_unavailable` | Generic error notice; does not blame the user |
| User opens `/auth/feedback` directly | No login session | Public page renders safely without auto-redirecting to IdP |
| Feedback URL contains `status=<script>...` | User edits query string | Controller takes `failed` branch; never reflects arbitrary strings into HTML |
| Callback state mismatch | Invalid OAuth2 transaction | No new `Authentication` issued; generic error shown per filter mechanics |
| Provider returns `invalid_scope` | Client requested wrong scope | Error displayed; dev team inspects registration |
| User retries manually | Clicks link on feedback page | Starts a fresh login transaction without reusing old code/state |
| Logged-in user denies extra scope | Linking / incremental scope flow | Depends on integration design; does not fail unrelated user work |
| Business API returns `403` after login | Access Token lacks scope | Handle API permission error downstream; do not classify as consent login failure |

Example when the application receives a forged callback:

~~~text
GET /login/oauth2/code/company?error=access_denied&state=FAKE_STATE
~~~

The application must rely on the framework to verify the callback matches a valid authorization request. **Never create an `Authentication` by reading `error` or `state` in a controller.** Real testing requires a test provider or integration environment able to return distinct OAuth responses.

## 11. Common Implementation Mistakes

### Mistake 1: Treating every OAuth2AuthenticationException as user denial

**Consequence:** configuration, token endpoint, or ID Token signature errors get reported as "You declined permission". Users have no recourse and ops struggle to spot real outages.

**Fix:** map only `access_denied` to the consent-not-granted message; route all other codes to a generic error branch or controlled classification.

### Mistake 2: Redirecting to a page that requires login

**Consequence:** the error page is guarded by `anyRequest().authenticated()`, causing an infinite redirect loop.

**Fix:** add `/auth/feedback` to `permitAll()`, and make retrying a user-triggered action.

### Mistake 3: Displaying raw `error_description`

**Consequence:** leaks provider internals and risks rendering malicious HTML or strings.

**Fix:** display application-defined messages; never reflect external input.

### Mistake 4: Using `AccessDeniedHandler` for `access_denied` callbacks

**Consequence:** fails to catch OAuth2 login failures because OAuth authorization denial and application authorization denial sit at different layers.

**Fix:** use `oauth2Login().failureHandler(...)` for callback failures; use `AccessDeniedHandler` for in-app 403 errors.

### Mistake 5: Logging tokens and callback URLs

**Consequence:** exposes codes, states, or tokens if logs are accessed. Overly verbose logs also prolong sensitive data retention.

**Fix:** log categorized error codes, static routes, and correlation IDs; never log credential values.

### Mistake 6: Modifying `state` manually to bypass callback errors

**Consequence:** breaks CSRF binding between authorization request and response.

**Fix:** let Spring Security manage `state`/authorization requests; investigate lost sessions, `SameSite` cookies, proxies, redirect URIs, or browser cookie blocking.

### Mistake 7: Treating the feedback URL's `cancelled` status as proof of consent

**Consequence:** anyone can visit `/auth/feedback?status=cancelled`; that query parameter does not prove they started or denied a real transaction.

**Fix:** the feedback page is purely UI. Never use it to update security state or mandatory audit logs; base audits on trusted framework/server events.

### Mistake 8: Wiping all business data when a user cancels connecting a provider

**Consequence:** an active user loses drafts or their session simply because they declined an optional integration scope.

**Fix:** separate primary login from external account/API linking flows; design sessions and work state accordingly.

## 12. Real-World Scenarios and Decision Making

### Scenario A: First-time OIDC login is denied

The user has no session and clicks "Decline" at the IdP. The provider returns `access_denied`. Spring Security has no new tokens to complete login.

**Application action:** show the public feedback page with a clear message and a link back to `/login`. Never render admin pages or auto-retry.

### Scenario B: Provider blocks consent due to organizational policy

The user clicks "Allow", yet the provider still returns `access_denied` because of an admin policy. Writing "You declined" in the UI is inaccurate.

**Application action:** display "The request was not approved" with instructions to contact an administrator if needed; log safe metadata so ops can distinguish the cause.

### Scenario C: Wrong `redirect_uri` after deployment

The provider rejects the request because the callback URL has a mismatched hostname or port. Some errors happen before the callback, so the failure handler is never called.

**Application action:** fix the client registration, trusted proxy config, and registered URI list at the IdP. Do not try to handle this by changing the `access_denied` message.

### Scenario D: User denies calendar read access

The user is logged into the portal. When opening calendar sync, the app requests extra API permissions and the user clicks deny.

**Application action:** do not mark the calendar integration as connected. While the portal session remains valid, let the user continue other tasks; use a separate integration flow to avoid disrupting primary authentication.

### Scenario E: Access Token works for UserInfo, yet API returns 403

OIDC login succeeded; a business API rejects the Access Token's permissions.

**Application action:** check audience, scopes, resource indicators, and API policy. This is a **post-login** error, not a consent denial on the OAuth authorization screen.

### Scenario F: Browser sends callback with `error=access_denied` but no state

The callback cannot be matched to an authorization request; the framework may raise a state/authorization request error before or during processing.

**Application action:** never skip `state` validation just to show a prettier "cancelled" page; show a safe error-appropriate message while preserving protocol CSRF checks.

## 13. References

- Spring Security — Servlet OAuth2 Login: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html
- Spring Security — OAuth2 Login Advanced Configuration: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html
- Spring Security Javadoc — AuthenticationFailureHandler: https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/web/authentication/AuthenticationFailureHandler.html
- Spring Security Javadoc — SimpleUrlAuthenticationFailureHandler: https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/web/authentication/SimpleUrlAuthenticationFailureHandler.html
- OAuth 2.0 Authorization Framework — Authorization Response Error (RFC 6749, Section 4.1.2.1): https://www.rfc-editor.org/rfc/rfc6749#section-4.1.2.1
- OpenID Connect Core 1.0 — Authentication Error Response: https://openid.net/specs/openid-connect-core-1_0.html

## 14. Practical Conclusion

In Spring Security Servlet OAuth2/OIDC Login, handling **user consent denial** should follow this path:

~~~text
User denies or provider refuses permission
  -> OAuth authorization response: error=access_denied
  -> Spring Security processes callback and transaction context
  -> OAuth2 login AuthenticationException
  -> AuthenticationFailureHandler
  -> Internal redirect to /auth/feedback?status=cancelled
  -> Public page explains situation with an option to retry

Other errors like invalid_client, invalid_grant, state mismatch, network...
  -> Appropriate handling or generic error message
  -> Do not describe as "user denied"
~~~

**`AuthenticationFailureHandler` turns a failed login event into an intentional user response; it does not replace OAuth2/OIDC protocol verification.** Classify only reliable errors, never reflect provider strings, protect `state` and sessions, prevent redirect loops, and let users decide whether to retry login or consent.
