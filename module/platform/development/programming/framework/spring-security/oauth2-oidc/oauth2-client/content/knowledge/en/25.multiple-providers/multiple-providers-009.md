# 25.9. Switching Providers or Logging In with Another Account

## 1. Context: One Application, Multiple Login Methods

A Spring Security OAuth 2.0/OIDC Client application can allow users to sign in with multiple OpenID Providers (OPs) or OAuth2 providers:

- **Company SSO** for employees.
- **Partner Identity Provider** for partners.
- A provider supporting multiple accounts signed in simultaneously in the browser.

Suppose a user signs into the portal with an employee account at Company SSO, and later wants to use a partner account; or the user is signed in as <code>alice@example.org</code> at the same provider and wants to switch to <code>bob@example.org</code>.

These two requests sound similar, yet differ in protocol and session behavior:

1. **Switching providers:** Selecting a different <code>ClientRegistration</code> and starting a new authorization flow at another OP.
2. **Switching accounts at the same provider:** Using the same <code>ClientRegistration</code> while asking the OP to authenticate a different identity instead of silently reusing the existing SSO session.

A multi-provider system must recognize that:

> **Switching providers does not automatically mean logging out of all OPs; clearing the application's session does not automatically clear the SSO cookie at the OP; receiving a new ID Token does not authorize merging two accounts into one.**

In Spring Security, provider selection happens at authorization initiation, while actual identity is determined only after callback and validation. The application must never trust a query parameter like <code>user=bob</code> to decide which principal gets logged in.

## 2. Lesson Objectives

After this lesson, you will:

1. Distinguish **provider switching**, **account switching within the same provider**, **local logout**, **RP-Initiated Logout**, and **account linking**.
2. Use <code>/oauth2/authorization/{registrationId}</code> properly to select a registered provider.
3. Understand why users may be logged back into the old account due to an OP SSO session.
4. Use OIDC parameters such as <code>prompt=select_account</code>, <code>prompt=login</code>, <code>max_age=0</code>, and <code>login_hint</code> for their intended purposes.
5. Design identity switching via **CSRF-protected POST**, invalidating the local session, and starting a new authorization request.
6. Handle <code>SecurityContext</code>, <code>OAuth2AuthorizedClient</code>, authorization request repositories, and session rotation properly.
7. Avoid identity confusion across providers, especially when two ID Tokens share an email yet have different <code>iss</code>/<code>sub</code>.
8. Configure the corresponding flow in **Servlet** and understand differences in **Reactive WebFlux**.
9. Build appropriate account linking, tenant isolation, step-up, redirect, and token cleanup policies.
10. Test multi-provider login, switch-account, SSO, callback errors, and multi-instance setups.

## 3. Distinguishing Concepts Before Coding

| Need | Primary action | Must end OP session? | Notes |
|---|---|---|---|
| Initial login via Company | Start OAuth2/OIDC authorization with registration <code>company</code> | No | Requires state/nonce/PKCE/ID Token validation per flow |
| Switch from Company to Partner | End or replace local authentication per policy, start registration <code>partner</code> | Not necessarily | Changes issuer, Client ID, scopes, and principal |
| Switch from Alice to Bob at Company | Re-login via Company, ask OP to show account selection | Not necessarily, OP-dependent | <code>prompt=select_account</code> is only a request to the OP |
| Force credential re-entry | Request fresh authentication at the OP | May not require full OP logout | <code>prompt=login</code> or <code>max_age=0</code> when supported by OP |
| Log out of the portal | Invalidate local session/SecurityContext | No | OP SSO session may remain |
| Log out of the OP | RP-Initiated Logout, if OP supports it | Yes | May affect SSO across other apps |
| Attach two logins to one app account | Account linking with ownership verification | No | Never auto-link solely on matching email |
| Switch tenant/organization within same account | Authorization/business context switching | Not necessarily | Never conflate tenant switch with OAuth provider switch |

For example, a user may keep Alice's account at Company SSO while also linking a Partner account to the internal profile. When switching providers, the product must decide whether that means **switching the active user** or **connecting an additional identity to the existing account**. The two operations carry different risk levels and verification flows.

## 4. Multi-Provider Structure in Spring Security

### 4.1. `ClientRegistration` is the provider selection point

In Spring Security OAuth2 Client, each registration has a <code>registrationId</code>, <code>clientId</code>, provider metadata, grant type, scopes, and callback template.

Example:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company-op
            client-id: portal-company
            client-secret: ${COMPANY_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email

          partner:
            provider: partner-op
            client-id: portal-partner
            client-secret: ${PARTNER_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile

        provider:
          company-op:
            issuer-uri: https://idp.example.org/realms/company
          partner-op:
            issuer-uri: https://login.partner.example.org
~~~

Both issuers, Client IDs, scopes, and secrets are illustrative. Each provider must be configured using trusted metadata and accurately registered redirect URIs.

When using OIDC Discovery, <code>issuer-uri</code> lets Spring Boot/Spring Security load metadata such as authorization/token endpoints, JWK Set, and UserInfo endpoint if available. **The issuer must be verified accurately**, never guessed from an email domain.

### 4.2. Login initiation paths

Spring Security defaults to the authorization initiation URLs:

~~~text
/oauth2/authorization/company
/oauth2/authorization/partner
~~~

Correspondingly:

~~~text
GET /oauth2/authorization/company
    → Company OP's Authorization Endpoint

GET /oauth2/authorization/partner
    → Partner OP's Authorization Endpoint
~~~

The path only selects a **declared registration**. The browser must never be allowed to pass arbitrarily:

~~~text
/oauth2/authorization?issuer=https://unknown.example
~~~

causing the server to send authorization requests or credentials to an untrusted issuer.

### 4.3. Callback corresponding to the registration

Example:

~~~text
Company callback:
    /login/oauth2/code/company

Partner callback:
    /login/oauth2/code/partner
~~~

Spring Security must match the callback against the initial authorization request, registration, <code>state</code>, PKCE/nonce where applicable, and validate the ID Token against the **issuer/audience of the selected registration**.

Never handle callbacks like: "JWT has a company email, so switch to the `company` ClientRegistration." Callbacks must bind to the trusted request and issuer, not unverified claims or self-reported emails.

## 5. Safe Provider Switching Flow

Consider a user logged into Company who wants to switch to Partner:

~~~mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant B as Browser
    participant APP as Spring Security Portal
    participant C as Company OP
    participant P as Partner OP
    U->>B: Select "Switch to Partner"
    B->>APP: POST /account/switch (CSRF + provider=partner)
    APP->>APP: Check provider allowlist, end local session
    APP-->>B: Redirect /oauth2/authorization/partner
    B->>APP: GET /oauth2/authorization/partner
    APP->>APP: Generate state, nonce/PKCE as applicable
    APP-->>B: 302 to Partner Authorization Endpoint
    B->>P: Authorization request
    P->>U: Login or SSO per policy
    P-->>B: Redirect code + state
    B->>APP: GET /login/oauth2/code/partner
    APP->>P: Token exchange
    P-->>APP: Access token + ID Token
    APP->>APP: Validate ID Token, build Partner principal
    APP->>APP: Create new Authentication/session
    APP-->>B: Redirect to safe post-login page
~~~

Notes:

- You do not need to send a logout request to Company OP to start authorization with Partner OP. Logging out of Company OP is a **separate product decision**.
- Company's local session must be cleaned up per policy before treating Partner as the active principal.
- If the product supports multiple identities in one session, explicitly design "active identity" and permission boundaries. Never simply overwrite a <code>currentProvider</code> field in the session and end up using another person's tokens.
- The new request must generate a **fresh `state`** and use the registration with the matching issuer.
- After callback, the application must apply the Partner principal's authorization/tenant policies rather than inheriting roles from the Company principal.

### 5.1. Why start with a CSRF-protected POST?

A GET link to <code>/oauth2/authorization/partner</code> is the standard way to **initiate login**. However, when a user is already signed in and asks to **change the active identity**, we normally want an intentional action:

~~~http
POST /account/switch HTTP/1.1
Content-Type: application/x-www-form-urlencoded
Cookie: JSESSIONID=...

provider=partner&<CSRF_FORM_FIELD>=...
~~~

The application validates the request, checks CSRF and the provider allowlist, and only then ends the old session and redirects to the new flow.

This avoids turning an identity-switching URL into a side-effecting action that an external site can force the browser to trigger via an image/iframe/link.

**This does not mean banning GET authorization initiation.** Login initiation still uses the standard URL; POST is specifically for switching accounts while **already authenticated**.

### 5.2. Never construct redirect URLs from unvalidated input

Wrong:

~~~java
return "redirect:" + request.getParameter("nextUrl");
~~~

If <code>nextUrl</code> is browser-controlled, this can become an open redirect leading to phishing or OAuth flow confusion.

Properly, redirect only to an internal path resolved from an allowlist:

~~~text
/oauth2/authorization/company
/oauth2/authorization/partner
~~~

If <code>returnTo</code> is needed, use validated route IDs/relative paths, or store the internal selection in server-side state and check permissions after login. Never place an arbitrary URI into <code>redirect_uri</code> sent to the OP.

## 6. Account Switching Flow Within the Same OpenID Provider

Suppose the user is currently Alice at Company:

~~~text
Portal session: Alice
Company OP session: Alice
~~~

The user clicks "Sign in with another Company account." The application clears the portal session and redirects to:

~~~text
/oauth2/authorization/company
~~~

The browser still holds Company OP's SSO cookie. The OP may immediately issue a code for **Alice** without prompting to choose an account.

~~~mermaid
flowchart TD
    A["User Alice logged in at Portal"] --> B["Portal local logout"]
    B --> C["Authorization request to same OP"]
    C --> D{"OP SSO cookie still valid?"}
    D -->|Yes| E["OP may immediately SSO into Alice"]
    D -->|No / interaction needed| F["OP shows login/account chooser"]
    E --> G["Callback may still be Alice"]
    F --> H["User picks Alice or Bob"]
    H --> I["Callback with OP-authenticated identity"]
~~~

**Clearing the local session does not automatically control the provider's account-selection UI.**

To let the user pick a different account, a mechanism provided by the OP is required—typically via OIDC authorization request parameters.

## 7. OIDC Parameters Affecting Account Selection

### 7.1. `prompt=select_account`

In OIDC, the <code>prompt</code> parameter accepts <code>select_account</code> to ask the Authorization Server/OP to display an account chooser.

Conceptual example:

~~~http
GET /authorize?response_type=code&client_id=portal-company&scope=openid%20profile&state=RANDOM_STATE&redirect_uri=https%3A%2F%2Fportal.example.org%2Flogin%2Foauth2%2Fcode%2Fcompany&prompt=select_account HTTP/1.1
Host: idp.example.org
~~~

The OP may:

- Let the user pick among accounts with active SSO sessions.
- Display login UI to add another account.
- Not support this prompt value or implement custom behavior.

**There is no guarantee <code>select_account</code> shows an identical chooser on every provider.** Applications must test with the exact OP, tenant, browser, and policy.

### 7.2. `prompt=login`

<code>prompt=login</code> asks the OP to re-authenticate the End-User.

It does not mean "show a list of all accounts." An OP might ask Alice to re-enter her password while keeping the user as Alice.

Example:

~~~text
prompt=login
~~~

fits when **reauthentication** is needed, not necessarily account switching.

### 7.3. `max_age=0`

<code>max_age</code> is the maximum elapsed time since the last active authentication that the Client accepts. With:

~~~text
max_age=0
~~~

OIDC requires the OP to perform active reauthentication, and the ID Token needs <code>auth_time</code> so the Client can evaluate it.

Key points:

- <code>max_age=0</code> requests **authentication freshness**.
- It does not dictate that the identity must be Bob.
- For account switching, it can be combined with an account selection mechanism when supported by the OP, subject to provider policy.
- Never use the ID Token's <code>iat</code> instead of <code>auth_time</code> to conclude authentication happened recently.

### 7.4. `prompt=login select_account`

OIDC allows multiple space-separated prompt values:

~~~text
prompt=login select_account
~~~

This signals a request for the OP to perform both reauthentication and account selection. However, not all OPs support or treat both values identically.

Do not blindly append unrecognized parameters to every authorization request assuming login behavior will stay consistent.

### 7.5. `login_hint`

<code>login_hint</code> can suggest which account the OP should preselect, such as an email or another identifier:

~~~text
login_hint=bob@example.org
~~~

This is a **UI hint**, not proof that Bob has been authenticated.

Risks:

- A browser or bookmark may supply the wrong hint.
- Email is personal data; avoid placing it in unnecessary analytics/logs.
- The OP may ignore the hint.
- Using a hint does not replace callback state and ID Token verification.

### 7.6. `prompt=none`

<code>prompt=none</code> asks the OP not to show any UI; it can result in <code>login_required</code> or <code>interaction_required</code> errors if silent SSO is impossible.

**Never use <code>prompt=none</code> to ask the user to choose another account.** Its purpose is almost the exact opposite.

### 7.7. Quick selection table

| Goal | Parameter typically considered | Conclusion to avoid |
|---|---|---|
| Show account chooser | <code>prompt=select_account</code> | Does not guarantee the provider always shows a chooser |
| Force reauthentication | <code>prompt=login</code> | Does not automatically switch accounts |
| Limit auth session age | <code>max_age</code> | Does not replace account selection |
| Suggest an account | <code>login_hint</code> | A hint is not authentication |
| Silent UI-less SSO | <code>prompt=none</code> | Not for switching accounts |

## 8. Do Not Confuse Local Logout with OP Logout

In SSO applications, there are at least two sessions:

~~~text
Portal HTTP session             Company OP SSO session
    app-session-123                  op-session-456
          |                               |
  Spring Security                         Browser cookie
  SecurityContext                         at idp.example.org
~~~

Local logout in the portal typically invalidates <code>app-session-123</code>. It **cannot directly delete cookies belonging to the OP's domain**.

### 8.1. When is local logout alone sufficient?

For example, when a user wants to switch from Company to Partner:

- End Company's local `Authentication`.
- Do not force logging out of Company OP unless global SSO logout is required.
- Start authorization at Partner OP.

This approach minimizes disruption to other apps using Company SSO.

### 8.2. When to consider RP-Initiated Logout?

If the product requires "sign out completely from Company" or the OP lacks a suitable account chooser, **OIDC RP-Initiated Logout** can be used when supported by the provider.

Spring Security Servlet offers <code>OidcClientInitiatedLogoutSuccessHandler</code>; WebFlux offers <code>OidcClientInitiatedServerLogoutSuccessHandler</code> in corresponding versions.

However, OP logout can affect SSO for many other applications and sometimes multiple account sessions, depending on the provider.

Do not automatically trigger OP logout when the user only wants to view the provider list unless required by product design.

### 8.3. Back-Channel Logout is not an account chooser

OIDC Back-Channel Logout lets an OP send a Logout Token so RPs end local sessions. It solves **logout synchronization**, not choosing Bob instead of Alice in an Authorization Code Flow.

Never implement account switching by forging Logout Tokens or manually POSTing to the application's back-channel endpoint.

## 9. Servlet Implementation Example: Two OIDC Providers

Examples use Java 17, Spring Boot 3/Spring Security 6 with MVC/Servlet. Choose exact APIs according to your project version.

### 9.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

If using view templates, add the appropriate template engine. Examples below show security logic only, without mandating a specific UI framework.

### 9.2. `SecurityFilterChain` with a provider selection page

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/", "/login", "/error", "/assets/**")
                    .permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .loginPage("/login"));

        return http.build();
    }
}
~~~

Explanation:

- <code>/login</code> is a custom page where users choose a registration.
- <code>/oauth2/authorization/company</code> and <code>/oauth2/authorization/partner</code> are handled by Spring Security OAuth2 Login if the registrations exist.
- Spring Security builds the authorization request/state and callback according to the selected registration.
- The configuration **does not disable CSRF**; the subsequent POST route for account switching requires a valid CSRF token.

### 9.3. Provider selection login page

A conceptual HTML page:

~~~html
<h1>Choose sign-in method</h1>
<ul>
  <li><a href="/oauth2/authorization/company">
      Sign in with Company SSO
  </a></li>
  <li><a href="/oauth2/authorization/partner">
      Sign in with Partner ID
  </a></li>
</ul>
~~~

Controller if using an MVC template:

~~~java
package example.web;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class LoginPageController {

    @GetMapping("/login")
    String loginPage() {
        return "login";
    }
}
~~~

This example assumes a template named <code>login</code>. If not using a template engine, serve a static page/controller view per your application's setup.

### 9.4. Registered paths must be exact

Example Company callback:

~~~text
https://portal.example.org/login/oauth2/code/company
~~~

Partner callback:

~~~text
https://portal.example.org/login/oauth2/code/partner
~~~

Each provider must register the exact matching URI; a wrong scheme/host/path results in <code>redirect_uri_mismatch</code>.

With a reverse proxy, Spring Boot must compute the public host/HTTPS accurately and trust forwarded headers only from controlled proxies.

## 10. Servlet Implementation Example: POST to Switch Provider

A clean design uses a dedicated POST route while the user is authenticated:

~~~text
POST /account/switch
    provider=company | partner
    valid CSRF token
~~~

### 10.1. Controller validating provider then running local logout

~~~java
package example.web;

import java.util.Set;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.security.core.Authentication;
import org.springframework.security.web.authentication.logout.SecurityContextLogoutHandler;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;

@Controller
public class AccountSwitchController {

    private static final Set<String> ALLOWED =
        Set.of("company", "partner");

    @PostMapping("/account/switch")
    String switchProvider(
            @RequestParam("provider") String provider,
            Authentication authentication,
            HttpServletRequest request,
            HttpServletResponse response) {

        // Allow only configured registrationIds.
        if (!ALLOWED.contains(provider)) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid provider");
        }

        // Spring Security CSRF filter must check POST before controller.
        // End current Authentication + HttpSession.
        var localLogout = new SecurityContextLogoutHandler();
        localLogout.logout(request, response, authentication);

        // Spring will start a new authorization flow at the chosen provider.
        return "redirect:/oauth2/authorization/" + provider;
    }
}
~~~

Prerequisites for using this pattern:

1. <code>/account/switch</code> is protected by <code>authenticated()</code>.
2. CSRF protection is enabled for POST.
3. The form submits a valid CSRF token.
4. The provider is checked against a **server-side allowlist**.
5. Local logout executes before starting the new identity flow.
6. Separate authorized-client cleanup is evaluated in subsequent sections.

<code>SecurityContextLogoutHandler</code> can invalidate the HTTP session and clear `SecurityContext`; it **does not** automatically revoke OP access/refresh tokens or delete all token records in a persistent authorized-client service.

**This is an illustrative implementation**, not a mandatory product rule. If an application has internal accounts with multiple linked identities, distinguish "switch active identity" from "link identity" before clearing the active principal.

### 10.2. HTML form with CSRF token

Conceptual example using Thymeleaf:

~~~html
<form th:action="@{/account/switch}" method="post">
    <button type="submit" name="provider" value="company">
        Switch to Company
    </button>
    <button type="submit" name="provider" value="partner">
        Switch to Partner
    </button>
</form>
~~~

With properly configured Thymeleaf and Spring Security CSRF integration, the token can be injected into the form automatically. If using another template engine, retrieve the CSRF token from the framework and submit it as supported; never copy a tokenless form and disable CSRF to "fix" a 403 error.

### 10.3. Why not just change a field in the session?

Wrong:

~~~java
session.setAttribute("activeProvider", "partner");
~~~

After that line, <code>Authentication</code> may **still be the Company user**, while code fetches the Partner access token from another source. Without careful checks, a controller could display user A's data while exercising user B's API permissions.

Switching identities must consistently update:

- `Authentication`/`SecurityContext`.
- Principal and internal account context.
- Authorized-client selection.
- Tenant/roles/permissions.
- Saved requests and redirects.
- Token caching and request-scoped data.

Do not treat it like changing a theme or language preference.

## 11. Forcing the Account Chooser at the Same Provider

The POST pattern above handles **local logout and provider selection**. However, if the user picks Company again, the OP might immediately SSO back into Alice.

To ask the OP to show an account chooser, you can add:

~~~text
prompt=select_account
~~~

to the **authorization request generated by Spring Security**.

### 11.1. Never put `prompt` inside `redirect_uri`

Wrong:

~~~text
redirect_uri=https://portal.example.org/login/oauth2/code/company?prompt=select_account
~~~

<code>prompt</code> is an **Authorization Endpoint request parameter**, not a query parameter on the callback <code>redirect_uri</code>.

Altering the redirect URI can also cause registration mismatches and open the door to OAuth mix-up or open redirects if unchecked.

### 11.2. Using `OAuth2AuthorizationRequestResolver`

In Servlet, Spring Security provides <code>DefaultOAuth2AuthorizationRequestResolver</code> and the <code>OAuth2AuthorizationRequestResolver</code> interface. You can wrap the default resolver—preserving `state`, PKCE, nonce, and correlation attributes—and only append <code>prompt</code> to appropriate authorization requests.

Example class illustrating a <code>?choose=true</code> option:

~~~java
package example.security;

import java.util.Set;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestRedirectFilter;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;
import org.springframework.security.oauth2.core.endpoint.OAuth2ParameterNames;

public final class AccountChoiceAuthorizationRequestResolver
        implements OAuth2AuthorizationRequestResolver {

    private final DefaultOAuth2AuthorizationRequestResolver delegate;
    private final Set<String> oidcRegistrations;

    public AccountChoiceAuthorizationRequestResolver(
            ClientRegistrationRepository repository,
            Set<String> oidcRegistrations) {

        this.delegate = new DefaultOAuth2AuthorizationRequestResolver(
            repository,
            OAuth2AuthorizationRequestRedirectFilter
                .DEFAULT_AUTHORIZATION_REQUEST_BASE_URI);
        this.oidcRegistrations = Set.copyOf(oidcRegistrations);
    }

    @Override
    public OAuth2AuthorizationRequest resolve(
            HttpServletRequest request) {
        return applyChooser(delegate.resolve(request), request);
    }

    @Override
    public OAuth2AuthorizationRequest resolve(
            HttpServletRequest request,
            String clientRegistrationId) {
        return applyChooser(
            delegate.resolve(request, clientRegistrationId),
            request);
    }

    private OAuth2AuthorizationRequest applyChooser(
            OAuth2AuthorizationRequest original,
            HttpServletRequest request) {

        if (original == null
                || !"true".equals(request.getParameter("choose"))) {
            return original;
        }

        Object registrationId =
            original.getAttributes()
                .get(OAuth2ParameterNames.REGISTRATION_ID);

        if (!(registrationId instanceof String id)
                || !oidcRegistrations.contains(id)) {
            return original;
        }

        return OAuth2AuthorizationRequest.from(original)
            .additionalParameters(parameters ->
                parameters.put("prompt", "select_account"))
            .build();
    }
}
~~~

Purpose of the class above:

- **Delegates** request creation to the default resolver.
- Adds <code>prompt=select_account</code> only if the request has <code>choose=true</code>.
- Applies only to registration IDs of OIDC providers verified to support it.
- **Does not regenerate `state`, nonce, PKCE, or `redirect_uri`.**

If a specific Spring Security version stores registration ID under another attribute key or offers a different customization API, adapt to that version. What must never change is the **binding between original request, `ClientRegistration`, and callback state**.

### 11.3. Wiring the resolver into `SecurityFilterChain`

If using the resolver above, replace the <code>oauth2Login()</code> setup in section 9.2 with:

~~~java
@Bean
SecurityFilterChain securityFilterChain(
        HttpSecurity http,
        ClientRegistrationRepository registrations) throws Exception {

    var resolver = new AccountChoiceAuthorizationRequestResolver(
        registrations, Set.of("company", "partner"));

    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/", "/login", "/error", "/assets/**")
                .permitAll()
            .anyRequest().authenticated())
        .oauth2Login(oauth2 -> oauth2
            .loginPage("/login")
            .authorizationEndpoint(endpoint ->
                endpoint.authorizationRequestResolver(resolver)));

    return http.build();
}
~~~

Here:

~~~text
GET /oauth2/authorization/company
    → normal login

GET /oauth2/authorization/company?choose=true
    → authorization request with prompt=select_account
~~~

**The two `SecurityFilterChain` configs in sections 9.2 and 11.3 are alternatives**—never declare both beans simultaneously with identical matchers expecting Spring to merge them.

### 11.4. Combining account choice with POST switch

To request account selection at the OP, after local logout redirect to:

~~~text
/oauth2/authorization/company?choose=true
~~~

In the switch controller from section 10.1, under a safe product-approved mode, you can return:

~~~java
return "redirect:/oauth2/authorization/" + provider
    + "?choose=true";
~~~

Here <code>provider</code> has already passed the allowlist check. The <code>choose=true</code> flag only asks the OP to display UI; it **grants no new permissions** and must never be trusted as proof that the account actually changed.

In a system where some provider does not support <code>select_account</code>, only add the flag for compatible registrations rather than applying it by default to every provider.

### 11.5. Preventing abuse of custom query parameters

Never let the browser pass arbitrarily:

~~~text
prompt=none
redirect_uri=https://attacker.example
client_id=another-client
scope=admin
issuer=https://untrusted.example
~~~

and copy them blindly into the authorization request.

If the browser needs to choose between <code>login</code> and <code>select_account</code>, use an **allowlist of defined modes**, checking the registration and product policy. Redirect URI, Client ID, provider issuer, and scopes must come from trusted server config.

## 12. New Callbacks Must Create a New `Authentication`, Not "Rename" the Principal

After an authorization code callback:

~~~text
GET /login/oauth2/code/partner?code=...&state=...
~~~

Spring Security:

1. Loads the original authorization request.
2. Verifies state/registration/correlation.
3. Sends the code plus matching client authentication/PKCE verifier to the Token Endpoint.
4. Verifies the token response, ID Token, and OIDC claims for the chosen registration.
5. Loads UserInfo when applicable.
6. Creates a new <code>OAuth2AuthenticationToken</code> and principal.
7. Saves <code>SecurityContext</code> and authorized client per configured mechanism.

Never do:

~~~java
oldAuthentication.setName("bob@example.org");
~~~

<code>Authentication</code> must not be mutated to impersonate another identity. A new login must go through the standard authentication flow and bind to a verified issuer/subject.

### 12.1. Distinguishing `OAuth2User` and `OidcUser`

If a registration includes <code>openid</code> and the provider supports OIDC, the principal is usually <code>OidcUser</code>.

If a provider supports OAuth2 Login without OIDC, the principal may be <code>OAuth2User</code> with its own attribute structure.

Provider-switching code must check the principal type. Never force an OAuth2-only provider into an OIDC issuer by reading <code>email</code> from UserInfo and fabricating an ID Token.

### 12.2. Never use email as a global identity

OIDC identifies users by the pair:

~~~text
(issuer, subject)
~~~

Example:

~~~text
("https://idp.example.org/realms/company", "u-123")
("https://login.partner.example.org",     "u-123")
~~~

Despite having the same <code>sub=u-123</code>, these are **two distinct identities**.

Conversely:

~~~text
Company: alice@example.org
Partner: alice@example.org
~~~

Two providers may report the same email without proving it is the same person. Emails can change, be recycled, be unverified, or belong to different trust domains.

## 13. Reading the Current Provider from `Authentication`

In Spring Security Servlet, <code>OAuth2AuthenticationToken</code> holds the registration ID of the authorized client used for login:

~~~java
package example.web;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;

@RestController
public class CurrentIdentityController {

    @GetMapping("/account/current")
    Map<String, String> current(Authentication authentication) {

        if (!(authentication instanceof OAuth2AuthenticationToken token)) {
            throw new ResponseStatusException(
                HttpStatus.UNAUTHORIZED,
                "No OAuth2 login principal");
        }

        return Map.of(
            "registrationId", token.getAuthorizedClientRegistrationId(),
            "principalName", token.getName());
    }
}
~~~

Explanation:

- <code>getAuthorizedClientRegistrationId()</code> identifies the registration that produced the current OAuth2 login.
- <code>getName()</code> is the principal name determined by the framework/provider; do not assume it is an email.
- Never return access tokens, ID Tokens, refresh tokens, or full claims to the frontend.

If the application also supports form login, API keys, Resource Server JWTs, or WebFlux, handle the appropriate `Authentication` types. The example above intentionally covers OAuth2 Login only.

### 13.1. When OIDC issuer and subject are needed

~~~java
if (token.getPrincipal() instanceof OidcUser oidcUser) {
    String issuer = oidcUser.getIdToken()
        .getIssuer().toString();
    String subject = oidcUser.getSubject();
    // Use issuer + subject for internal identity mapping.
}
~~~

Import:

~~~java
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
~~~

Only use ID Token/claims after Spring Security's OIDC flow has validated them. Never perform identity mapping by Base64URL-decoding a JWT arbitrarily provided by the browser.

## 14. `SecurityContext`, Session, and Token State During a Switch

Switching accounts impacts at least three layers:

~~~mermaid
flowchart LR
    OLD["Active identity A"] --> LOGOUT["Local logout / identity switch"]
    LOGOUT --> SEC["SecurityContext / HTTP session"]
    LOGOUT --> AUTH["OAuth2 authorization request state"]
    LOGOUT --> TOK["OAuth2AuthorizedClient storage"]
    SEC --> NEW["New identity B"]
    AUTH --> NEW
    TOK --> POLICY["Cleanup per separate policy"]
~~~

### 14.1. Login session

If the application allows only **one active identity per session**, local logout normally invalidates the old HTTP session and clears `SecurityContext` before starting the new flow.

Session fixation protection/session ID rotation during authentication should be managed by Spring Security per configuration; never reassign the old session ID to the new account yourself.

### 14.2. Authorization request repository

Each authorization flow needs a fresh <code>state</code>, and possibly <code>nonce</code>/<code>PKCE</code>. Before starting a new flow, never reuse an old Company authorization request for Partner.

If the browser opens multiple tabs, two flows may contend on the same authorization request repository depending on implementation. Support concurrent flows or inform the user—never drop state validation.

### 14.3. Authorized-client store

<code>OAuth2AuthorizedClient</code> can live in:

- HTTP session via <code>HttpSessionOAuth2AuthorizedClientRepository</code>.
- An <code>OAuth2AuthorizedClientService</code> keyed by registration/principal.
- Redis/JDBC/custom token vault per design.

**Invalidating the HTTP session does not guarantee deleting authorized clients in a service-based store.**

Thus after switching:

~~~text
New SecurityContext = Partner Bob
Token store still has record = Company Alice
~~~

This can be valid if the product permits account linking/multi-connection with dedicated policies, yet poses a risk if code accidentally uses Alice's token while Bob is the active user.

### 14.4. When to remove the old authorized client?

There is no universal answer:

| Token storage policy | Considerations when switching identity |
|---|---|
| Per-session token | Invalidating the session typically clears session data if the repository is truly session-scoped |
| Per-principal shared token | Decide retain/delete by lifetime/consent; deleting may impact another browser session |
| Per-device/authorization | Delete only the matching grant/session by key |
| Multiple linked accounts | Can keep tokens of verified connections, while never mixing active principals |
| High-security logout | May require revocation at the OP and invalidating other sessions per policy |

Never call <code>removeAuthorizedClient(registrationId, principalName)</code> using an unverified or browser-sent username. If removing old tokens, read the identity/storage key from a trusted server-side context **before clearing the old authentication**.

### 14.5. Refresh tokens may remain valid after local logout

Local logout does not revoke refresh tokens at the OP by default. If the product requires the user to lose delegated authorization after switching, consider token revocation (RFC 7009) per provider capability.

Conversely, revoking every token when the user only wants to add/switch providers can break other integrations relying on a still-valid grant.

## 15. One User Linking Multiple Providers: Do Not Confuse Account Linking with Switching

A common pattern:

~~~text
InternalAccount #105
    ├── Linked identity:
    │     issuer=Company OP, sub=user-abc
    └── Linked identity:
          issuer=Partner OP, sub=partner-xyz
~~~

The application can allow the user to sign in via either identity and resolve to the same `InternalAccount #105`.

**Account linking is a sensitive privilege/identity action**, distinct from logging out user A and logging in user B.

### 15.1. Email-based account takeover risk

Wrong:

~~~text
Company user: email=alex@example.org
Partner user: email=alex@example.org

⇒ automatically merge into one internal account
~~~

Because:

- Email may be unverified or the provider may lack an <code>email_verified</code> claim.
- An untrusted provider may allow self-service setting of someone else's email.
- Emails can be recycled when users change organizations.
- Two trust domains may have different email ownership verification policies.
- Having <code>email_verified=true</code> at one provider does not automatically authorize linking with every other provider.

### 15.2. Intentional account linking flow

A secure design:

1. User is already logged into internal account A.
2. User chooses **Link provider B**, clearly separated from **Switch active account**.
3. For sensitive actions, require reauthentication/MFA if required by policy.
4. Start a new authorization flow to provider B with a dedicated **linking transaction/state**.
5. After callback, validate the entire OIDC response and extract <code>(iss, sub)</code> for identity B.
6. Verify identity B is not already linked to another internal account.
7. Require confirmation or apply policy proving ownership of both identities.
8. Record the link in a consistent transaction with a unique constraint on <code>(issuer, subject)</code>.
9. Log a safe security event and notify the account owner when appropriate.
10. Keep internal identity A as the principal or transition per **controlled** policy—never switch mid-flight silently.

### 15.3. An account linking diagram

~~~mermaid
sequenceDiagram
    autonumber
    participant U as User logged into Account A
    participant APP as Portal
    participant OP as Provider B
    participant DB as Identity Mapping DB
    U->>APP: POST /account/link/provider-b (CSRF)
    APP->>APP: Verify A, reauth/step-up if needed
    APP->>APP: Create linking transaction with fresh state
    APP-->>U: Redirect to Provider B
    U->>OP: Login/prove ownership of identity B
    OP-->>APP: Authorization response code + state
    APP->>APP: Validate callback + B's ID Token
    APP->>DB: Check (issuerB, subB) belongs to no other account
    DB-->>APP: Eligible to link
    APP->>DB: Commit link with internalAccountId=A
    APP-->>U: Confirm connection added
~~~

**Do not use simple account-switch session invalidation as an account linking flow**, because linking needs proof of authenticated user A to establish who requested attaching identity B.

### 15.4. Preventing races while linking

If two internal accounts simultaneously try to link the same <code>(issuer,sub)</code>, enforce a DB uniqueness constraint/transaction. Checking first with a `SELECT` and then `INSERT` without a constraint can create duplicate links under high concurrency.

## 16. Multiple Providers and OAuth2 Mix-Up Protection

When a Client communicates with multiple Authorization Servers, guard against **mix-up attacks**: provider A's response being mistakenly correlated with provider B's request or token endpoint.

Principles:

1. Authorization requests must bind to the selected registration/issuer and a reliably stored <code>state</code>.
2. Callbacks must exchange codes only at **the exact Token Endpoint** of the original request.
3. For OIDC, validate <code>iss</code>, <code>aud</code>, signature, expiration, and nonce where applicable.
4. Each registration's Redirect URI is registered and processed accurately.
5. Never rely on email or a new callback <code>provider=...</code> query parameter to switch registrations.
6. Consider issuer identification in authorization responses per RFC 9207 and appropriate mix-up mitigations supported by the framework/provider.
7. When sharing one callback path across multiple providers, prove the response is bound to the original issuer rather than merely reading the code.

### 16.1. Dangerous example

~~~text
User starts Company login.
Application saves provider=Company.
Callback arrives with ?provider=Partner&code=...
Application trusts the query parameter and sends the code to Partner Token Endpoint.
~~~

This handling is flawed. The authorization code flow's registration must come from the **protected authorization request correlated via `state`**, never from a fresh untrusted parameter.

### 16.2. Separating login callbacks by provider

Using:

~~~text
/login/oauth2/code/company
/login/oauth2/code/partner
~~~

is a clean way to configure redirect URIs. Yet separate paths **do not replace** state, issuer, and token validation.

## 17. `SavedRequest`, Redirects, and Data Between Two Sessions

After OIDC Login, Spring Security can redirect the user back to the URL they originally requested via the request cache/success handler.

When the user switches identities, the initial URL may have been saved from the old session:

~~~text
Alice opens /admin/reports/finance
Alice selects Switch to Bob
Bob logs in successfully
SavedRequest sends Bob to /admin/reports/finance
~~~

If Bob is not allowed access, the backend must return 403. Still, the UX can be confusing; worse, if code skips authorization to display content cached from Alice, that is a severe vulnerability.

### 17.1. Redirect rules after switching

- Prefer sending the user to a **safe neutral page**, such as <code>/home</code> or <code>/account/current</code>.
- Never retain business data from the old identity inside the new session.
- If keeping <code>returnTo</code>, validate internal routes and post-login authorization.
- Never let the browser put an arbitrary absolute URL into OAuth `state` and redirect unchecked.
- After switching, caches holding previous tenant/user data must be refreshed or partitioned by identity.

### 17.2. Browser with multiple tabs

Browsers typically share cookies across tabs:

~~~text
Tab A: viewing Company Alice's data
Tab B: switches to Partner Bob
Tab A: clicks a data-modifying action
~~~

New requests from Tab A may execute under Bob's session after the switch. If the frontend displays Alice's UI while sending requests under Bob's permissions, it is easy to act on the wrong object.

Mitigations:

- After switching, broadcast an event/poll an identity version so other tabs learn the account changed.
- Bind internal-account/tenant context into API authorization, re-checking every request.
- Never grant permissions based on stale UI.
- For sensitive operations, verify identity context and require confirmation/step-up when needed.

### 17.3. Account switch generation

In systems needing strict consistency, you can attach an <code>identityGeneration</code> or session generation:

~~~text
Old request: generation=17, identity=Alice
Switch:      generation=18, identity=Bob
~~~

Before committing a sensitive mutation, the backend compares the request's generation against the active identity. This is an **application-layer safeguard**, not a built-in OAuth2 feature.

## 18. Switching Providers in Reactive WebFlux

WebFlux uses the same OAuth2/OIDC protocols, but its HTTP and security abstractions differ from Servlet.

| Servlet | Reactive WebFlux |
|---|---|
| <code>HttpSecurity</code> | <code>ServerHttpSecurity</code> |
| <code>SecurityFilterChain</code> | <code>SecurityWebFilterChain</code> |
| <code>HttpSession</code> | <code>WebSession</code> |
| <code>SecurityContextHolder</code> via thread context | <code>ReactiveSecurityContextHolder</code> / Reactor Context |
| <code>OAuth2AuthorizationRequestResolver</code> | <code>ServerOAuth2AuthorizationRequestResolver</code> |
| <code>OAuth2AuthorizedClientRepository</code> | <code>ServerOAuth2AuthorizedClientRepository</code> |
| <code>OidcClientInitiatedLogoutSuccessHandler</code> | <code>OidcClientInitiatedServerLogoutSuccessHandler</code> |

### 18.1. Configuring Reactive login and provider selection page

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveLoginSecurityConfig {

    @Bean
    SecurityWebFilterChain webSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/", "/login", "/error").permitAll()
                .anyExchange().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .authenticationEntryPoint(
                    new org.springframework.security.web.server
                        .authentication.RedirectServerAuthenticationEntryPoint(
                            "/login")))
            .build();
    }
}
~~~

The snippet illustrates a reactive chain. Depending on your Spring Security version, configuring the authentication entry point, login page, or exception handling may vary; stick to **reactive components** and never copy <code>HttpSecurity</code> into WebFlux.

The <code>/login</code> page can still offer both links:

~~~text
/oauth2/authorization/company
/oauth2/authorization/partner
~~~

Spring Security Reactive resolves callbacks using WebFilters/`WebSession`, not Servlet filters.

### 18.2. Switching via logout then provider selection

A Reactivity-friendly approach:

1. Browser sends a **CSRF-protected POST** to the WebFlux app's logout endpoint.
2. Reactive logout handlers invalidate <code>WebSession</code>/`SecurityContext` per configuration.
3. Logout success handler redirects to <code>/login?choose=1</code>.
4. User picks a provider on the login page.
5. Starts a new <code>/oauth2/authorization/{registrationId}</code> flow.

Example post-logout redirect configuration:

~~~java
import java.net.URI;

import org.springframework.security.web.server.authentication.logout
    .RedirectServerLogoutSuccessHandler;

RedirectServerLogoutSuccessHandler redirect =
    new RedirectServerLogoutSuccessHandler();
redirect.setLogoutSuccessUrl(URI.create("/login?choose=1"));

http.logout(logout ->
    logout.logoutSuccessHandler(redirect));
~~~

This is an **additional configuration snippet** for a reactive chain, not a complete class. Users can choose a provider after logout. To redirect directly to a chosen provider, implement a custom success handler reading the validated choice via Reactive APIs—never track the current session in a mutable singleton.

### 18.3. Reactive custom authorization request resolver

With WebFlux, use **<code>ServerOAuth2AuthorizationRequestResolver</code>** and reactive `WebExchange`-based APIs. Never use Servlet's <code>DefaultOAuth2AuthorizationRequestResolver</code> in a reactive pipeline.

Similar concept:

~~~text
Reactive default resolver
    → builds standard OAuth2AuthorizationRequest
    → if request uses mode choose=true and registration is OIDC:
         append prompt=select_account
    → preserve state, nonce, PKCE, redirect URI, issuer binding
~~~

If a provider does not support <code>select_account</code>, use an appropriate flow/UX or intentional RP-Initiated Logout. Never call <code>.block()</code> in a reactive filter to read/write `WebSession`.

### 18.4. Reactor Context after switching principals

<code>ReactiveSecurityContextHolder</code> binds `Authentication` to the reactive subscription. Never store old `Authentication` objects in static fields or thread-local caches and reuse them after a switch.

Requests after logging in as B must read the new principal via WebFlux security context, and token lookups must use the matching registration/principal.

## 19. Multi-Instance and Distributed Sessions

In a load-balanced environment:

~~~text
Browser
   ↓
Load Balancer
   ├── Instance A
   └── Instance B
         ↓
    Shared session store
         ↓
    Authorized client store
~~~

A flow might:

1. POST switch on instance A; old session invalidated.
2. New authorization request created on A.
3. Provider B callback routed to instance B.
4. B must retrieve state/nonce/PKCE and session correlation from a shared session store or appropriate session affinity.
5. B writes the new `Authentication` and authorized client to the proper storage.

**Do not persist only `SecurityContext` while forgetting the authorization request repository.** State for the new authorization flow must remain accessible when the callback hits another node.

### 19.1. Risks

- In-memory session/authorization request state on A causes B to report <code>invalid_state</code>.
- Authorized client remains in the old node's <code>InMemoryOAuth2AuthorizedClientService</code>.
- User A and user B share the same <code>principalName</code> key if the app does not namespace by issuer/tenant.
- Concurrent requests still use old tokens during the switch.
- Token refresh races or failure handlers accidentally delete newly updated tokens.
- Session logout occurs on one node while the service token store is cluster-wide.

### 19.2. Risk mitigation mechanisms

- Spring Session Redis/JDBC matching Servlet/WebFlux to share HTTP/`WebSession`.
- Authorized-client storage partitioned accurately by registration and trusted principal key.
- Identity generation or session version for sensitive operations when required.
- Clear cleanup/revocation policies for the old identity's tokens.
- Never use a single in-memory registry/lock for cluster coordination.
- Verify session serialization compatibility during rolling deployments.

When using refresh token rotation across multiple replicas, sharing a token store alone does not stop two nodes from refreshing R0 concurrently. When needed, add single-flight coordination, re-read after locking, CAS/conditional updates, and stale-safe conditional deletes.

## 20. Authorization and Tenant Isolation After Switching

A successful login **does not mean all prior resources remain permitted**.

Example:

~~~text
Company Alice:
    role = FINANCE_ADMIN
    tenant = COMPANY_A

Partner Bob:
    role = PARTNER_VIEWER
    tenant = PARTNER_B
~~~

After switching to Bob:

- Never inherit <code>FINANCE_ADMIN</code>.
- Never read data from a cache key based solely on route like <code>/reports</code>.
- Never use Company's old access token to call Partner APIs.
- Never retain Company as the default tenant in the new request/session.
- Resource Server must independently verify audience, scopes, roles, and ownership.

### 20.1. Caches must be partitioned by identity

Wrong:

~~~text
cacheKey = "dashboard"
~~~

If the dashboard holds user/tenant data, another user can receive the wrong results.

Better:

~~~text
cacheKey = appId + internalAccountId + tenantId + dashboardVersion
~~~

Key components must come from trusted backend context, not browser-asserted query parameters. On account switch, invalidate user-specific caches if needed.

### 20.2. Permissions are re-evaluated at every endpoint

Even when the frontend knows the user is in Partner, the backend must still authorize every action under the current `Authentication`. Never trust:

~~~http
X-Active-Account: company-admin
~~~

as proof of authorization. Arbitrary headers from the browser can only act as validated request preferences, never identity proof.

### 20.3. Provider choice differs from consented scopes

A new account on the same provider may grant fewer scopes than the previous account. <code>ClientRegistration.getScopes()</code> is the requested list, not a guarantee that the Token Endpoint grants all of them.

After login, verify actually granted token scopes, Resource Server audience, and business permissions. Never repeatedly refresh a <code>403 insufficient_scope</code> token expecting privileges to escalate.

## 21. User Picks Another Account Yet OP Still Returns the Old Account

This is the most common issue when testing account switching.

### 21.1. Root-cause analysis

1. Was the local session actually cleared?
2. Does the browser still hold the OP SSO cookie?
3. Did the authorization request actually include <code>prompt=select_account</code>?
4. Does the provider support that parameter?
5. Does the provider enforce its own account-selection policy or tenant restrictions?
6. How many sessions are open at the OP in that browser?
7. Is a <code>login_hint</code> inadvertently forcing the UI back to Alice?
8. Which <code>iss/sub</code> did the validated token callback return?

### 21.2. Never override `subject` on the Client side

Wrong:

~~~text
OP returns ID Token: sub=alice
App wants Bob
⇒ force principalName=bob
~~~

Doing so creates an identity mismatched with authentication proof. The right way is to initiate another **authorization/authentication flow** so the OP genuinely authenticates Bob, or inform the user that switching is unsupported under the provider's current capabilities.

### 21.3. Can RP-Initiated Logout be used?

Yes, if the OP supports it and the user accepts the SSO impact. After OP logout, the browser can return to the provider selection page or re-login.

However, even RP-Initiated Logout does not guarantee which account chooser UI appears; final behavior depends on the OP, SSO federation, and browser cookies.

## 22. Using RP-Initiated Logout in Servlet

For an OIDC provider with <code>end_session_endpoint</code>, Spring Security can redirect the browser to OP logout.

Example:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.oidc.web.logout
    .OidcClientInitiatedLogoutSuccessHandler;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class GlobalOidcLogoutConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ClientRegistrationRepository registrations)
            throws Exception {

        var success =
            new OidcClientInitiatedLogoutSuccessHandler(
                registrations);
        success.setPostLogoutRedirectUri("{baseUrl}/login");

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutSuccessHandler(success));

        return http.build();
    }
}
~~~

**This is an alternative to the simpler `SecurityFilterChain` earlier**—do not combine bean chains with overlapping matchers.

When the user logs out:

1. Local session is handled by logout filters.
2. OIDC logout success handler resolves the relevant OP from the current authentication/OIDC client config per framework.
3. The handler redirects the browser to the OP logout endpoint.
4. The OP may end the SSO session and redirect back to <code>/login</code> if post-logout redirect is registered/allowed.

With multiple providers, verify that the logout success handler chooses the registration of the **current authentication**. Never send provider A's <code>id_token_hint</code> to provider B.

Do not trigger global OP logout for a "switch provider" action if the product only wants a local identity switch. Present the two UX behaviors clearly.

### 22.1. Post-logout redirect URI

<code>{baseUrl}/login</code> is an illustrative internal redirect. The OP may require exact registration of <code>post_logout_redirect_uri</code>.

Never let the browser pass an arbitrary URL into post-logout redirect, avoiding open redirects/phishing and token/hint leaks.

### 22.2. Non-OIDC providers

A provider supporting only OAuth2 Login does not necessarily have an OIDC <code>end_session_endpoint</code> or ID Token. The OIDC logout success handler may not perform OP logout in the same way.

For non-OIDC providers, review the provider-specific logout protocol and local session policy; never fabricate an ID Token to trigger OIDC logout.

## 23. Failure Handling in the Switch-Account Flow

After local logout and initiating a new login, several errors can occur:

| Error | Consequence | Handling |
|---|---|---|
| User cancels login at OP | No new `Authentication` | Return to provider selection page; never restore old session arbitrarily |
| OP returns <code>access_denied</code> | User declined consent or policy | Safe notice, allow choosing again |
| OP reports <code>login_required</code> | Silent login impossible | Use interactive flow if needed |
| OP ignores or rejects <code>prompt</code> | Request rejected or ignored | Check provider capability, fallback UX |
| <code>redirect_uri_mismatch</code> | Authorization start/callback fails | Fix registration/proxy/OP config |
| Callback <code>invalid_state</code> | Correlation fails | Check session/state repository; never drop state validation |
| Token Endpoint rejects code | No new principal created | Check code lifetime, PKCE, Client auth |
| ID Token wrong issuer/audience | Login rejected | Check registration and OP; never drop validation |
| Account B locked internally | OIDC auth may succeed while app denies access | Apply business account policy |
| Account B lacks role/tenant | App/API returns 403 | Never inherit A's permissions |
| OP SSO still picks A | Switch-account misses UX goal | Use account chooser/reauth per provider |
| Old token remains in service store | Risks stale token if app uses wrong principal | Check token cleanup/isolation |

### 23.1. Never auto-restore the old session when the new login fails

If the product chooses to **invalidate the session before switching**, a failed new login must not restore the old `Authentication` from a token cache without proving it is still valid.

If you want "switch account with option to cancel and go back" UX, design a dedicated switching transaction bound to session and TTL—never use a browser variable like <code>oldUser=alice</code> to restore access.

### 23.2. Distinguishing authentication errors from account-linking errors

Bob's OIDC Login might succeed while linking Bob to internal account Alice fails because Bob is already linked to another account.

That is an **account linking policy error**, not a token signature mismatch. Return a safe message without disclosing the other account's identity unless authorized.

## 24. Common Implementation Mistakes

| Mistake | Why it is problematic | Right approach |
|---|---|---|
| Switching provider with <code>session.setAttribute("provider")</code> | `SecurityContext` still holds old identity | Run a new OAuth2/OIDC login |
| Only clearing local session and assuming OP shows chooser | OP SSO cookie still exists | Use <code>prompt=select_account</code> if OP supports it |
| Using <code>prompt=login</code> to guarantee selecting Bob over Alice | Reauth may still authenticate Alice | Read <code>iss/sub</code> from validated ID Token |
| Treating <code>login_hint</code> as authentication | Hint is not proof of identity | Treat strictly as a UX hint |
| Trusting <code>provider</code> query at callback | Can cause mix-up | Bind to `state` and original `ClientRegistration` |
| Letting browser supply arbitrary issuer/token endpoint | SSRF/token leakage/mix-up | Allowlist registrations |
| Merging accounts by matching email | Account takeover risk | Verified linking using <code>(iss,sub)</code> |
| Keeping user A's authorized client token as default after switch | Leaks user A's permissions to B | Scope tokens by registration/principal |
| Picking registration by email domain | Does not guarantee trusted OP/tenant | Server-side provider selection |
| Not invalidating/rotating session on identity switch | Session fixation and stale session data | Use `SecurityContextLogoutHandler`/standard filters |
| Disabling CSRF so switch POST avoids 403 | Weakens browser routes | Submit valid CSRF tokens |
| Using OP logout for every provider switch | May log user out of other apps | Separate local switch and global logout |
| Dropping <code>state</code> when multi-tab callbacks fail | Opens OAuth login CSRF/mix-up | Support multi-flow repository or UX |
| Caching profile by route name | Cross-account data leakage | Partition caches by identity/tenant |
| Sending ID Token as API access token | Wrong token purpose/audience | Use access token matching Resource Server |
| Printing raw tokens in debug logs | Credential leakage | Log sanitized metadata |
| Ignoring multi-instance setups | Callback/token store loses state across replicas | Appropriate shared session/storage |

## 25. Systematic Diagnostic Process

If a user says "I picked Bob, yet the page still shows Alice":

~~~text
Did the user click switch-account?
    |
    v
Did POST /account/switch pass CSRF and allowlist?
    |
    v
Was the old local session terminated?
    |
    v
Did authorization initiation pick the right ClientRegistration?
    |
    v
Did authorization request include prompt/select_account if needed?
    |
    v
Does OP support prompt and present an account chooser UI?
    |
    v
Did callback pass state/nonce/PKCE?
    |
    v
Which (iss,sub) does the newly validated ID Token contain?
    |
    +-- Still Alice
    |      → OP SSO/chooser policy did not produce a different identity
    |
    +-- Bob
           |
           v
      Was SecurityContext saved with Bob?
           |
           v
      Does authorized client use Bob's token?
           |
           v
      Were internal account/tenant/caches updated?
           |
           v
      Does API authorization enforce Bob's permissions?
~~~

If the validated ID Token is Bob while the UI still shows Alice, the bug usually lies in **session/`SecurityContext`/caching or internal identity mapping**, not that the OP failed to authenticate Bob.

### 25.1. Logs for investigation

Helpful fields:

~~~text
requestId=...
switchMode=provider
previousRegistration=company
selectedRegistration=partner
oauth2CallbackStateValidation=success
oidcIssuerAlias=partner-idp
internalAccountMappingOutcome=found
newPrincipalKeyHash=...
sessionRotated=true
authorizedClientRegistration=partner
~~~

Never log:

~~~text
authorization_code
code_verifier
actual state / nonce
id_token JWT
access_token / refresh_token
client_secret
session cookie
~~~

If identity correlation analysis is needed, use hashed/correlated identifiers per policy and control retention/access. Never put raw emails in metric labels.

## 26. UX Design to Prevent User Confusion

An account page should distinguish three actions:

**Switch active account**

> Ends the current work session and signs in with another account. Unsaved changes may be lost.

**Switch sign-in method**

> Chooses another identity provider to sign into the application.

**Link another account**

> Keeps the current account, verifies an additional identity from another provider, and links them per policy.

If the UI only has an "Add account" button while code invalidates the session and replaces the active principal, users will misunderstand and lose work in progress.

### 26.1. Confirming before switching

If work is being edited:

- Warn about unsaved data.
- Let the user confirm switching identities.
- Land on a safe page after login.
- Notify other tabs of the new identity.
- Never automatically replay old write requests under the new user's permissions.

### 26.2. Separating scopes from permissions

After switching, the UI may reflect a different role/tenant. Yet UI is never an enforcement point: the backend and Resource Server must still check authorization.

## 27. Test Scenarios to Cover

| Scenario | Expectation |
|---|---|
| Unauthenticated user picks Company | Redirects to the right Company OP |
| Unauthenticated user picks Partner | Redirects to the right Partner OP |
| Company user POSTs switch to Partner with CSRF | Old session ends, new flow starts |
| Company user POSTs switch without CSRF | Request rejected |
| User sends provider outside allowlist | 400/validation failure, no redirect to unknown issuer |
| Company user switches back to Company without prompt | May SSO back to same account; UX communicates clearly |
| Company user switches back to Company with <code>select_account</code> | OP asked to let user pick account if supported |
| Company user switches to Bob | Callback yields Bob's verified <code>(iss,sub)</code> |
| OP returns <code>access_denied</code> | Does not create Bob's `Authentication` |
| Callback with wrong state | Does not create a new authenticated session |
| Company ID Token sent to Partner callback | Rejected by issuer/audience/correlation |
| Two providers share the same email | No automatic account linking |
| User B lacks A's permissions | API blocks per B, never inherits A's roles |
| Authorized-client store holds A and B tokens | B's request picks only the matching registration/principal |
| User logs out of another session of same principal | Token cleanup follows policy, never out-of-scope deletions |
| Two-tab switch | Never uses stale principal/data to modify resources |
| Callback lands on another instance | State/session/token storage works or fails safely |

## 28. Practice Exercises

### Exercise 1 — Switching providers

The app is authenticated with Company. The user picks Partner and successfully signs in through Partner.

**Question:** Which property must change so Spring Security starts the Partner authorization flow?

**Answer:** Use <code>registrationId=partner</code> at <code>/oauth2/authorization/partner</code> after applying local identity-switch policy. Never alter issuer/Client ID via browser query parameters.

### Exercise 2 — SSO automatically returns Alice

User performs local logout and requests <code>/oauth2/authorization/company</code>. The OP immediately returns a code for Alice.

**Question:** Is this a state validation bug?

**Answer:** Not necessarily. The OP still holds Alice's SSO session. Consider <code>prompt=select_account</code> or a provider-supported account-selection flow.

### Exercise 3 — `select_account` and `login`

**Question:** Does <code>prompt=login</code> always guarantee selecting Bob instead of Alice?

**Answer:** No. It requests reauthentication, not a command to pick a specific account. <code>prompt=select_account</code> is better suited for requesting an account chooser, though providers may have limitations.

### Exercise 4 — `max_age=0`

Provider requests reauthentication and the ID Token returns a fresh <code>iat</code> yet an old <code>auth_time</code>.

**Question:** Should you look only at <code>iat</code> to conclude the user just re-entered their password?

**Answer:** No. <code>iat</code> is when the ID Token was issued; <code>auth_time</code> reflects actual authentication time per OIDC. Proper <code>max_age</code> validation is needed.

### Exercise 5 — Matching email

Company and Partner both return <code>alice@example.org</code>, yet with different issuer/sub.

**Question:** Can the two accounts be auto-linked?

**Answer:** No. An intentional linking flow verifying ownership/consent per policy is required to prevent account takeover.

### Exercise 6 — POST without CSRF

An external website link calls GET <code>/account/switch?provider=partner</code>, causing the portal to invalidate the session.

**Question:** What is wrong?

**Answer:** Side-effecting action over GET that can be forced cross-site. Use POST with CSRF protection, validate the provider, and authenticate the current user.

### Exercise 7 — Invalid provider

Browser sends <code>provider=https://attacker.example</code>.

**Question:** Should the system dynamically create a <code>ClientRegistration</code> for that URL?

**Answer:** Not under this lesson's model. Use only server-managed allowlisted registrations/issuers; prevent SSRF, OAuth mix-up, and credential leakage.

### Exercise 8 — Stale token in JDBC

Alice's session is invalidated, yet <code>JdbcOAuth2AuthorizedClientService</code> still holds Alice's token.

**Question:** Is Spring Security's logout broken?

**Answer:** Not necessarily. Session invalidation and service-backed authorized-client cleanup are separate lifecycles. Define token retention/revocation policies and ensure Bob never uses Alice's token.

### Exercise 9 — Two tabs

Tab A displays Company data; Tab B switches to Partner. Tab A submits a mutating POST.

**Question:** Where is the protection?

**Answer:** The backend must authorize against the current `Authentication` and tenant; optionally add an identity/session generation to reject stale actions. Never trust stale UI.

### Exercise 10 — Account linking

Bob at Partner is already linked to `internalAccount #200`. Alice at Company wants to link Bob to `internalAccount #105`.

**Question:** Should the system automatically transfer the link?

**Answer:** No. Enforce a unique constraint and ownership policy; block it or use a separately authorized workflow rather than silently linking one identity to two accounts.

### Exercise 11 — Multi-instance callback

Partner login starts on node A; the load balancer sends the callback to B, reporting <code>invalid_state</code>.

**Question:** Can we disable state validation to solve it?

**Answer:** No. Use a shared session/authorization request repository or appropriate sticky routing, checking cookies and proxies.

### Exercise 12 — Wrong-issuer callback

User starts the Company flow; a Partner response is sent to Company's callback.

**Question:** What must the system do?

**Answer:** Reject when state/registration/issuer/audience or OIDC validation fails. Never pick another provider from email/query parameters to "rescue" the flow.

### Exercise 13 — Designing a switching flow

Build an application with:

1. Two OIDC `ClientRegistration` entries: <code>company</code> and <code>partner</code>.
2. A <code>/login</code> provider selection page.
3. A <code>SecurityFilterChain</code> with <code>oauth2Login()</code>.
4. POST <code>/account/switch</code> with CSRF and registration allowlist.
5. Local session logout followed by redirect to OAuth2 initiation.
6. Custom resolver adding <code>prompt=select_account</code> for the same provider when supported.
7. Callback/ID Token validation checking state, issuer, audience, and nonce.
8. Identity mapping by <code>(iss,sub)</code>.
9. Authorized client token isolation and cleanup per policy.
10. Post-switch redirect to a safe page without retaining stale user caches.
11. Tests covering multiple browser tabs and a two-instance cluster.
12. Safe metadata logging without tokens, codes, state, or session cookies.

Explain why **"switching providers" does not automatically perform "account linking"**, and why **"local logout" does not automatically force the OP to show an account chooser**.

## 29. Key Takeaways

- **Switching providers** starts an authorization flow using a different <code>ClientRegistration</code>; **switching accounts at the same provider** asks the OP to authenticate another identity using the same registration.
- <code>/oauth2/authorization/{registrationId}</code> selects a registered provider; never let the browser configure issuer/token endpoints dynamically.
- **Local logout only ends the Client's session.** The browser may still hold an OP SSO session and silently log back into the same account.
- In OIDC, <code>prompt=select_account</code> requests an account chooser; <code>prompt=login</code> requests reauthentication; <code>max_age=0</code> requests authentication freshness; <code>login_hint</code> is only a hint.
- No parameter lets the Client assert <code>sub=Bob</code> on its own. Identity must be authenticated by the OP and fully validated at callback.
- When changing the active identity, use a **CSRF-protected POST**, registration allowlist, invalidate/rotate the local session, and start a fresh flow with new state/nonce/PKCE.
- **`SecurityContext`, authorization request repository, and `OAuth2AuthorizedClient` storage are three distinct states.** Invalidating a session does not automatically delete tokens from a persistent service.
- Across multiple providers, OIDC identity must be keyed by **<code>(issuer, subject)</code>**, never auto-merged by email or issuerless <code>sub</code>.
- **Account switching differs from account linking.** Linking requires verifying both identities, ownership policy, unique constraints, and anti-takeover protections.
- Never let user A's tokens, roles, tenant, cached data, or saved requests leak to user B after switching.
- With multiple Authorization Servers, prevent mix-up via state/registration binding, exact callbacks, issuer/audience/nonce validation, and RFC 9207 mitigations where supported.
- In WebFlux, use reactive security/session/resolver APIs; in Servlet, use <code>HttpSecurity</code>, <code>SecurityFilterChain</code>, and Servlet request APIs. Never mix stacks.
- Across multiple instances, share session/correlation state and token storage properly; watch out for refresh concurrency and token cleanup.

### References

- **Spring Security Reference — OAuth2 Login (Servlet):** <code>oauth2Login()</code>, login page, authorization initiation, `ClientRegistration`, success/failure handling.
- **Spring Security Java API — DefaultOAuth2AuthorizationRequestResolver:** customizing authorization request parameters per registration and request context.
- **Spring Security Reference — OAuth2 Client:** <code>OAuth2AuthorizedClient</code>, repository/service, token lifecycle, and authorized client managers.
- **Spring Security Reference — Reactive OAuth2 Login:** <code>SecurityWebFilterChain</code>, `WebSession`, reactive authorization request resolvers.
- **Spring Security Reference — Servlet and Reactive Logout:** <code>SecurityContextLogoutHandler</code>, <code>OidcClientInitiatedLogoutSuccessHandler</code>, <code>OidcClientInitiatedServerLogoutSuccessHandler</code>.
- **OpenID Connect Core 1.0:** Authorization Code Flow, <code>prompt</code>, <code>login_hint</code>, <code>max_age</code>, <code>auth_time</code>, ID Token, <code>iss</code>/<code>sub</code>.
- **OpenID Connect RP-Initiated Logout 1.0:** <code>end_session_endpoint</code>, <code>id_token_hint</code>, post-logout redirect.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** Authorization Code, Token Endpoint, and <code>state</code>.
- **RFC 7636 — Proof Key for Code Exchange:** PKCE and authorization code binding.
- **RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification:** issuer identification and mix-up mitigation.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** authorization response protection, redirect URI, session/token security.
- **OWASP Authentication Cheat Sheet and Session Management Cheat Sheet:** session fixation, reauthentication, session lifecycle, and account security.
