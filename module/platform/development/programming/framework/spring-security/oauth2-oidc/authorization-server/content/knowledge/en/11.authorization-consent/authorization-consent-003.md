# Building a Consent UI Displaying the Client and Requested Scopes

## 1. Objectives and Context

When building an **OAuth 2.0/OpenID Connect (OIDC) Authorization Server** with **Spring Security**, **Spring Authorization Server**, and **Spring Boot**, the **consent** page is where users see which application is requesting access and decide which **scopes** to approve. This is a critical step in the Authorization Code Flow: the user must understand what they are allowing the application to do, and the Authorization Server must validate that decision within the context of a valid authorization request.

For example, user Alice signs in to the Authorization Server at <code>https://auth.example.com</code>. The application <code>orders-web</code> requests <code>orders.read</code> and <code>orders.write</code> to call the Orders API. On the consent screen, Alice should see the registered application name, clear descriptions of each permission, any previously granted permissions if applicable, and two choices: **Approve** and **Deny**. Rendering the UI or submitting the form must never turn a browser-declared scope into a granted permission.

After this lesson, you will be able to:

1. Explain when the Authorization Server requires consent and what data must be displayed.
2. Use <code>OAuth2AuthorizationEndpointConfigurer.consentPage()</code> to specify a custom consent page.
3. Create a Spring MVC controller and Thymeleaf template displaying the client, requested scopes, and previously approved scopes.
4. Submit the decision via HTTP POST to the right Authorization Endpoint with <code>client_id</code>, <code>state</code>, and <code>scope</code> parameters.
5. Distinguish consent state, OAuth client state, and the HTTP form's CSRF token.
6. Prevent displaying misleading permissions, XSS, CSRF, client spoofing, scope tampering, and invalid consent.
7. Test the entire Authorization Code + PKCE/OIDC flow instead of testing only the template.

**Version Scope:** Examples use common APIs from Spring Authorization Server 1.x, including <code>OAuth2AuthorizationServerConfigurer.authorizationServer()</code>, <code>HttpSecurity.with(...)</code>, and <code>consentPage(...)</code>. Newer versions of Spring Security with integrated Authorization Server may change package names or configuration styles. The code blocks below are educational examples that intentionally omit imports and infrastructure beans not directly related to consent.

## 2. Consent Flow in the Authorization Code Flow

~~~mermaid
sequenceDiagram
    autonumber
    participant U as Alice (Browser)
    participant C as orders-web (OAuth Client)
    participant AS as Authorization Endpoint
    participant UI as Custom Consent UI
    participant R as RegisteredClientRepository
    participant CS as OAuth2AuthorizationConsentService
    C->>U: Redirect to request permissions
    U->>AS: GET /oauth2/authorize + client_id, scope, state, PKCE
    AS->>R: Validate client, grant, redirect_uri, and scopes
    AS-->>U: Require login if unauthenticated
    U->>AS: Resume authorization after login
    AS->>CS: Look up stored consent
    AS-->>U: 302 /oauth2/consent?client_id=...&scope=...&state=...
    U->>UI: GET /oauth2/consent
    UI->>R: Retrieve client name from trusted registration
    UI->>CS: Retrieve previously granted scopes
    UI-->>U: HTML with scopes and Approve/Deny options
    U->>AS: POST /oauth2/authorize with decision
    AS->>AS: Verify session, state, client, and valid permissions
    AS->>CS: Save/update consent if valid
    AS-->>U: Redirect back to client with code or error
~~~

Consent is a step **after End-User authentication** and authorization request validation. The system does not necessarily show this page every time: if sufficient consent already exists and policy permits reuse, the Authorization Server may skip it. If the user denies, the server must process a non-granted outcome according to the protocol rather than issuing a code as on approval.

### 2.1. Consent, Authentication, and Authorization Are Distinct Decisions

| Component | Question | Example |
| --- | --- | --- |
| User authentication | Who is signed in? | Alice has authenticated successfully. |
| Client registration | Which scopes is the client allowed to request? | <code>orders-web</code> has <code>orders.read</code>, <code>orders.write</code>. |
| Consent | Which scopes did Alice agree to for that client? | Alice selects <code>orders.read</code>. |
| Authorization policy | Is that permission currently allowed by policy? | Alice's account is not locked and may request read access. |
| Token issuance | Which token is issued, and with what scopes? | Access token contains only the valid granted scopes. |
| Resource authorization | Is Alice allowed to read a specific order? | Orders API checks permissions on order 123. |

Consent does not grant ownership over all resources, does not prove the client is properly registered, and does not itself create a login session. With **Client Credentials**, there is typically no End-User in front of a consent UI; service client permissions are managed through client registration and server policies.

### 2.2. When Should Consent Be Prompted?

Whether the screen appears can depend on <code>ClientSettings.requireAuthorizationConsent(true)</code>, prior consent, new scopes in the request, OIDC policies, and active extensions. Do not assume <code>requireAuthorizationConsent(true)</code> means “show the page on every request”; likewise, never allow a client to request an unregistered scope and display it as if it were valid.

## 3. Designing Information on the Consent Screen

The primary goal of the page is to help the user answer **“Which application is requesting which permissions?”**.

| Information | Appropriate Source | Presentation |
| --- | --- | --- |
| Application name | <code>RegisteredClient.getClientName()</code> | “Orders Portal”, HTML-escaped. |
| Application ID | <code>RegisteredClient.getClientId()</code> | <code>orders-web</code> to aid identification. |
| Signed-in user | Server-side <code>Principal</code>/<code>Authentication</code> at the Authorization Server | Currently active account, especially when multiple accounts exist. |
| Scopes to review | List of <code>scope</code> values forwarded by the Authorization Server to the custom consent page, after validation against client registration | Individual permission checkboxes with clear labels. |
| Scope descriptions | Server-managed description catalog | “View permitted orders”, not just <code>orders.read</code>. |
| Prior consent | <code>OAuth2AuthorizationConsentService</code> by client record ID and principal | “Previously granted permissions” section. |
| Decision | Approval and denial forms | Do not hide the deny option or pre-select all permissions. |

### 3.1. Writing Friendly Yet Honest Permission Names

| Technical Scope | Display Name | Interpretation |
| --- | --- | --- |
| <code>orders.read</code> | View orders | Read orders the user is permitted to access. |
| <code>orders.write</code> | Edit orders | Create or update orders within permitted scope. |
| <code>profile</code> | Basic profile | Request profile information that may be provided under OIDC. |
| <code>email</code> | Email address | Request email information when available and permitted. |
| <code>openid</code> | Sign in with this account | Request OIDC authentication, not an API write permission. |

Scope labels must reflect actual Resource Server permissions. Do not describe <code>orders.read</code> as “View all orders” when the API still restricts access by ownership/tenant. The OIDC <code>email</code> scope does not guarantee every token will include an email claim; OIDC scopes and actual issued claims still depend on policy and consent.

### 3.2. Client Name Does Not Prove Brand Identity

<code>getClientName()</code> is **metadata in RegisteredClient**, typically entered by an administrator or client manager. For third-party clients, do not display a logo/domain or a “Verified” badge based solely on the display name. If logos and websites are shown, they must be reviewed, hosted from approved sources, and URL-validated; avoid fetching external images specified directly by the client while rendering consent.

## 4. Configuring a Custom Consent Page with Java DSL

### 4.1. Registering a Client That Requires Consent

Example setup for a <code>RegisteredClient</code>:

~~~java
RegisteredClient ordersClient = RegisteredClient
    .withId("orders-web-record-001")
    .clientId("orders-web")
    // Configure authentication method, grants, and real redirect URIs.
    .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
    .scope(OidcScopes.OPENID)
    .scope(OidcScopes.PROFILE)
    .scope("orders.read")
    .scope("orders.write")
    .clientSettings(ClientSettings.builder()
        .requireProofKey(true)
        .requireAuthorizationConsent(true)
        .build())
    .build();
~~~

This is an **illustrative snippet**, not a complete runnable `RegisteredClient`. You must add valid redirect URIs, client authentication appropriate to the client type, and Authorization Server services/keys. For public clients, never embed secrets in browser/mobile apps. PKCE and consent protect two distinct aspects; PKCE does not replace consent.

### 4.2. Configuring SecurityFilterChain

~~~java
@Configuration
@EnableWebSecurity
class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerChain(HttpSecurity http)
            throws Exception {
        OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, server -> server
                .authorizationEndpoint(endpoint ->
                    endpoint.consentPage("/oauth2/consent"))
                .oidc(Customizer.withDefaults()))
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated())
            .exceptionHandling(exceptions -> exceptions
                .defaultAuthenticationEntryPointFor(
                    new LoginUrlAuthenticationEntryPoint("/login"),
                    new MediaTypeRequestMatcher(MediaType.TEXT_HTML)))
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()));

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/oauth2/consent")
                    .authenticated()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());
        return http.build();
    }
}
~~~

**Explanation:** <code>getEndpointsMatcher()</code> selects the protocol endpoints actually managed by the Authorization Server, including <code>/oauth2/authorize</code>. The custom controller <code>GET /oauth2/consent</code> is protected by the **web chain** and requires a signed-in user. Spring Authorization Server will redirect to the URI specified in <code>consentPage()</code> when needed, but **does not automatically generate the custom controller or template**.

Do not arbitrarily use <code>securityMatcher("/oauth2/**")</code> instead of <code>getEndpointsMatcher()</code>: doing so can mistakenly intercept the consent page URL or miss OIDC endpoints on other paths. Use <code>@Order</code> to place the specific endpoint chain before the fallback chain.

In this example, <code>oauth2ResourceServer().jwt()</code> serves OIDC endpoints that require JWT/Bearer when the corresponding features are enabled; it requires an appropriate <code>JwtDecoder</code>. Beans for <code>RegisteredClientRepository</code>, authorization/consent services, user authentication, JWK, and OIDC infrastructure must be configured separately.

### 4.3. Display Path and Decision Submission Path

| Step | Method/Path | Handler |
| --- | --- | --- |
| Initiate permission request | <code>GET /oauth2/authorize</code> | Spring Authorization Server's Authorization Endpoint. |
| Render form | <code>GET /oauth2/consent</code> | Application-authored Spring MVC controller and Thymeleaf template. |
| Submit consent decision | <code>POST /oauth2/authorize</code> | Spring Authorization Server's Authorization Endpoint. |

**Note:** <code>/oauth2/authorize</code> is the default path. If changed via <code>AuthorizationServerSettings</code>, the form must POST to the actual **<code>getAuthorizationEndpoint()</code>**; do not hard-code the old path.

## 5. The Three Parameters of the Consent URL

According to the <code>OAuth2AuthorizationEndpointConfigurer.consentPage()</code> API, the Authorization Server redirects to the consent page with the parameters <code>client_id</code>, <code>scope</code>, and <code>state</code>. Example:

~~~http
HTTP/1.1 302 Found
Location: /oauth2/consent?client_id=orders-web&scope=orders.read%20orders.write&state=opaque-consent-state
~~~

| Parameter | Meaning |
| --- | --- |
| <code>client_id</code> | Protocol-level client ID, used to look up the RegisteredClient. |
| <code>scope</code> | Space-delimited list of scopes for the consent context. |
| <code>state</code> | Correlation/anti-forgery token for the **consent step** passed by the Authorization Server; must be submitted back verbatim. |

Because these values are placed in the URL, **do not trust them blindly**. Users can edit the query string. The controller uses them for display, but on POST, the Authorization Server must re-bind them to the pending authorization request, the user session, and stored policies.

### 5.1. Three Values Frequently Confused

1. **OAuth client state**: generated by the client in the initial <code>/oauth2/authorize</code> request; the client compares it against the state in the final callback redirect.
2. **Consent state**: forwarded by the Authorization Server to <code>/oauth2/consent</code>, used to link the user's decision to the pending authorization; **must never be replaced with the OAuth client state**.
3. **Servlet CSRF token**: typically exposed by Spring Security under the <code>_csrf</code> attribute, protecting POST forms at URLs covered by the CSRF filter.

The consent state and the Servlet CSRF token **are not the same value**, even though the API documentation describes consent state as a CSRF protection mechanism for the consent flow itself. If the form requires a Servlet CSRF token, pass both according to their respective roles.

### 5.2. Do Not Display All Registered Scopes as If Requested

<code>RegisteredClient.getScopes()</code> returns every scope the client is allowed to request. The current request may ask for only a subset. For example, if a client is registered with <code>orders.read</code>, <code>orders.write</code>, and <code>reports.export</code>, but the redirect only includes <code>orders.read</code>, the UI should only present checkboxes for the scopes actually in the consent context, without adding <code>reports.export</code>.

## 6. Spring MVC Controller Retrieving Client Info and Scopes

The controller below only **prepares display data**; when the user submits, it **does not** directly call <code>OAuth2AuthorizationConsentService.save()</code> and **does not** issue an authorization code itself. Inputs and scopes are re-validated when the Authorization Endpoint receives the POST.

~~~java
@Controller
public class ConsentPageController {

    private static final Map<String, String> TITLES = Map.of(
        "openid", "Sign in with this account",
        "profile", "Basic profile",
        "email", "Email address",
        "orders.read", "View orders",
        "orders.write", "Edit orders"
    );

    private static final Map<String, String> DESCRIPTIONS = Map.of(
        "openid", "Authenticate using OpenID Connect.",
        "profile", "Request permitted profile information.",
        "email", "Request email information per policy.",
        "orders.read", "Read orders you are permitted to view.",
        "orders.write", "Update orders you are permitted to edit."
    );

    private final RegisteredClientRepository clients;
    private final OAuth2AuthorizationConsentService consentService;

    public ConsentPageController(
            RegisteredClientRepository clients,
            OAuth2AuthorizationConsentService consentService) {
        this.clients = clients;
        this.consentService = consentService;
    }

    @GetMapping("/oauth2/consent")
    public String consentPage(
            Principal principal,
            @RequestParam("client_id") String clientId,
            @RequestParam("scope") String scopeParameter,
            @RequestParam("state") String consentState,
            Model model,
            HttpServletResponse response) {

        // The web chain already requires Authentication; defensive check.
        if (principal == null) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED);
        }

        RegisteredClient client = clients.findByClientId(clientId);
        if (client == null || !StringUtils.hasText(consentState)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST);
        }

        Set<String> requestedScopes = Arrays.stream(
                scopeParameter.split("\\s+"))
            .filter(StringUtils::hasText)
            .collect(Collectors.toCollection(LinkedHashSet::new));

        // Validation for rendering only; the AS must independently validate POST.
        if (!client.getScopes().containsAll(requestedScopes)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST);
        }

        OAuth2AuthorizationConsent previous = consentService.findById(
            client.getId(), principal.getName());

        Set<String> approved = previous == null
            ? Set.of()
            : previous.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .filter(authority -> authority.startsWith("SCOPE_"))
                .map(authority -> authority.substring("SCOPE_".length()))
                .filter(client.getScopes()::contains)
                .collect(Collectors.toSet());

        List<ScopeItem> newScopes = requestedScopes.stream()
            .filter(scope -> !approved.contains(scope))
            .map(ConsentPageController::scopeItem)
            .toList();

        List<ScopeItem> previousScopes = approved.stream()
            .sorted()
            .map(ConsentPageController::scopeItem)
            .toList();

        response.setHeader(HttpHeaders.CACHE_CONTROL, "no-store");
        response.setHeader(HttpHeaders.PRAGMA, "no-cache");

        model.addAttribute("clientName", client.getClientName());
        model.addAttribute("clientId", client.getClientId());
        model.addAttribute("consentState", consentState);
        model.addAttribute("userName", principal.getName());
        model.addAttribute("newScopes", newScopes);
        model.addAttribute("previousScopes", previousScopes);

        return "oauth2-consent";
    }

    private static ScopeItem scopeItem(String scope) {
        return new ScopeItem(
            scope,
            TITLES.getOrDefault(scope, "Scope: " + scope),
            DESCRIPTIONS.getOrDefault(
                scope, "Technical permission requiring description and review.")
        );
    }

    public record ScopeItem(
        String value, String title, String description) {}
}
~~~

Imports are omitted to keep the focus on the logic. <code>ScopeItem</code> is a Java record for Java 17+. <code>newScopes</code> includes only current scopes not yet present in stored consent; <code>previousScopes</code> separately displays previously approved permissions. Grouping UI data this way **does not** replace the Authorization Server's semantics for combining prior consent with new decisions.

A few notes on the controller:

- <code>clients.findByClientId(clientId)</code> looks up the client by **OAuth client ID**, whereas <code>consentService.findById(client.getId(), principal.getName())</code> must use the **registered client record ID**.
- <code>Principal</code> must come from server-verified <code>Authentication</code>; never take a username from the query string to look up someone else's consent.
- If a scope is unrecognized in the description catalog, production systems should reject registering unapproved scopes rather than letting users guess their meaning.
- <code>Cache-Control: no-store</code> prevents caching sensitive consent details in browsers/proxies; also configure CSP, Referrer-Policy, and framing controls.
- In multi-tenant systems, the principal name must follow a stable, collision-free ID convention across tenants. Two users named <code>alice</code> in two organizations must never share consent.

**Important Limitation:** The controller cannot verify on its own that the state belongs to the exact pending authorization request; the framework verifies this during the POST step. Data in GET is strictly for rendering. Do not use this controller to allow a client to request all registered scopes by editing the URL.

## 7. Thymeleaf Template for the Consent Page

Place the template inside the Spring Boot application, for example at <code>src/main/resources/templates/oauth2-consent.html</code>. For this lesson, the template contents are presented inline within Markdown; no separate source file is created.

~~~html
<!DOCTYPE html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="referrer" content="no-referrer">
    <title>Authorization Consent</title>
</head>
<body>
<main>
    <header>
        <h1>Review Permissions</h1>
        <p>
            Application
            <strong th:text="${clientName}">Orders Portal</strong>
            (<code th:text="${clientId}">orders-web</code>)
            is requesting access.
        </p>
        <p>
            You are signed in as
            <strong th:text="${userName}">alice</strong>.
        </p>
    </header>

    <!-- APPROVAL FORM: POSTs to the default Authorization Endpoint. -->
    <form method="post" th:action="@{/oauth2/authorize}">
        <input type="hidden" name="client_id" th:value="${clientId}">
        <input type="hidden" name="state" th:value="${consentState}">

        <!-- Included if the Servlet CSRF filter applies.
             Do not confuse _csrf with consent state. -->
        <input th:if="${_csrf != null}"
               type="hidden"
               th:name="${_csrf.parameterName}"
               th:value="${_csrf.token}">

        <fieldset>
            <legend>Permissions to review</legend>
            <p th:if="${#lists.isEmpty(newScopes)}">
                There are no new permissions in this list.
            </p>
            <div th:each="item : ${newScopes}">
                <label>
                    <input type="checkbox" name="scope"
                           th:value="${item.value()}">
                    <strong th:text="${item.title()}">View orders</strong>
                </label>
                <p th:text="${item.description()}">
                    Read orders you are permitted to view.
                </p>
            </div>
        </fieldset>

        <section th:if="${!#lists.isEmpty(previousScopes)}">
            <h2>Previously granted permissions</h2>
            <ul>
                <li th:each="item : ${previousScopes}"
                    th:text="${item.title()}">View orders</li>
            </ul>
        </section>

        <button type="submit"
                th:disabled="${#lists.isEmpty(newScopes)}">
            Approve selected permissions
        </button>
    </form>

    <!-- DENIAL FORM: submits without any scope parameters. -->
    <form method="post" th:action="@{/oauth2/authorize}">
        <input type="hidden" name="client_id" th:value="${clientId}">
        <input type="hidden" name="state" th:value="${consentState}">
        <input th:if="${_csrf != null}"
               type="hidden"
               th:name="${_csrf.parameterName}"
               th:value="${_csrf.token}">
        <button type="submit">Deny</button>
    </form>
</main>
</body>
</html>
~~~

### 7.1. Verifying Exact POST Fields

| Field | Required by Flow | Meaning |
| --- | --- | --- |
| <code>method="post"</code> | Yes | Sends the consent decision to the Authorization Endpoint via POST. |
| <code>action="/oauth2/authorize"</code> | Yes, update per settings if endpoint path changes | POSTs to the protocol endpoint handled by the AS. |
| <code>client_id</code> | Yes | Client requesting permissions; re-verified by the AS. |
| <code>state</code> | Yes | Consent state value from the redirect; matched by the AS against the pending authorization. |
| <code>scope</code> | Yes when approving scopes | One value per checked box; parameter name may repeat. |
| <code>_csrf</code> | Per actual CSRF config | Form anti-forgery token when required by the Servlet CSRF filter. |

Example when the user selects two checkboxes:

~~~http
POST /oauth2/authorize HTTP/1.1
Content-Type: application/x-www-form-urlencoded

client_id=orders-web&state=opaque-consent-state&
scope=orders.read&scope=orders.write
~~~

This abbreviated request omits the CSRF token in configurations that require one. The browser sends data as URL-encoded form parameters; the two <code>scope</code> entries are **two values under the same parameter name**, not a custom comma-separated string.

### 7.2. The Deny Form

The deny form submits only <code>client_id</code>, <code>state</code>, and the CSRF token if applicable, **with no `scope` parameter**. With Spring Authorization Server's standard consent handling, this indicates the user did not approve new permissions and can lead to `access_denied` in the authorization response. Test the behavior of your actual version and customizations, especially when the request already has prior consent.

Never build a custom POST handler that issues tokens itself, never pre-populate <code>scope=orders.write</code> via a hidden input to “make the form always valid”, and never treat clicking approve as a reason to skip state verification.

### 7.3. Notes on CSRF and Thymeleaf

In Thymeleaf/Spring Security setups, <code>th:action</code> can integrate with <code>RequestDataValueProcessor</code> to automatically inject a hidden CSRF input. The template example renders the token when the <code>_csrf</code> attribute is present for clarity; in real integration, inspect the rendered HTML and **use only one consistent token-injection mechanism**, avoiding unnecessary duplicate inputs.

Some Authorization Server endpoints are excluded from the CSRF matcher managed by the protocol configurer. That **does not make consent state optional**. Do not disable CSRF across the entire web/login app just because the consent form returned 403; identify the right filter chain, matcher, and handling endpoint.

### 7.4. Displaying OIDC Scopes

The <code>openid</code>, <code>profile</code>, and <code>email</code> scopes have different semantics from API permission scopes. Do not assume you must render an <code>openid</code> checkbox on every consent page: the framework may treat it as a protocol condition and omit it from the scopes requiring review. Rely strictly on the scope set passed by the Authorization Server along with the policies for those scopes; never inject a hidden <code>openid</code> input into POST if the AS did not include it in the consent context.

## 8. Ensuring Granted Permissions Never Exceed What Was Requested

For a consent UI, a core invariant is:

~~~text
Actually granted scopes
  ⊆ Scopes in the pending authorization request
  ∩ Scopes the client is allowed to register
  ∩ User and system authorization policy
  ∩ Valid consent decision
~~~

This is a logical representation; OIDC or extensions may introduce additional rules. The key point is that **HTML forms are not a trusted source**. If someone modifies a checkbox in DevTools and submits <code>scope=admin.full_access</code>, the Authorization Server must reject or refuse to grant that permission based on the pending request, registered client, and policy, even if the GET controller rendered valid data.

### 8.1. Preventing XSS, Client Identity Spoofing, and Phishing

- Render client name, principal, scopes, and descriptions with escaping via <code>th:text</code>/<code>th:value</code>; never use <code>th:utext</code> for untrusted content.
- Do not load logos from an arbitrary URL supplied by the client inside the authorization request; use vetted metadata.
- Set <code>Content-Security-Policy</code>, restrict <code>frame-ancestors</code>, <code>Referrer-Policy: no-referrer</code>, HTTPS/HSTS, and <code>Cache-Control: no-store</code>.
- Avoid logging full consent URLs since they contain state and request details; never log tokens, secrets, or cookies.
- Provide a support and permission-revocation path for connected applications, but never create a misleading “Revoke all tokens” button that only deletes the consent record.

### 8.2. Binding State, Session, and Principal

The GET controller only reads data for display. When receiving the POST, the Authorization Endpoint must verify that the consent state exists, correlates to the appropriate authorization request, matches the right client ID, matches the right user session, and includes only valid scopes. Reject POSTs when the user has logged out, the state has already been consumed or no longer exists, or the client ID was altered.

For multi-tenant systems, the <code>registeredClientId</code> and <code>principalName</code> pair must uniquely distinguish entities; never share a consent record between two people with the same username across two tenants.

### 8.3. Never Save Consent on GET

<code>OAuth2AuthorizationConsent</code> represents authorities already granted by a user to a registered client. While rendering the consent page, the controller should only call <code>OAuth2AuthorizationConsentService.findById()</code> to inspect prior status; <code>save()</code> belongs to the Authorization Server's pipeline after validating a consent decision. Writing <code>SCOPE_orders.write</code> into the record merely because the request contained that value would constitute **auto-granting permissions before the user agrees**.

## 9. Prior Permissions, New Scopes, and State Changes

### 9.1. User Already Consented to <code>orders.read</code>

Example prior consent:

~~~text
registeredClientId = orders-web-record-001
principalName      = user-42
authorities        = {SCOPE_orders.read}
~~~

When the client additionally requests <code>orders.write</code>, the UI can group them:

~~~text
Orders Portal (orders-web) wants access:

New permissions:
  [ ] Edit orders
      Can update orders you are permitted to edit.

Previously granted:
  ✓ View orders

[Approve selected permissions]    [Deny]
~~~

Previously granted permissions can be reused per policy and should not be treated as permissions being requested for the first time. However, do not assume unchecking a prior permission on this screen **revokes that permission**; a “Manage connected apps” feature requires its own authenticated revocation flow.

### 9.2. No New Scopes Yet the AS Still Shows the Page

If the page receives a valid state but the list of new permissions is empty, check OIDC rules, re-consent requirements, previously granted permissions, and version-specific framework behavior. Do not automatically complete authorization inside the controller to “skip the screen”; handle it according to policy or refine the display logic clearly.

### 9.3. Modifying or Revoking Consent

If the user deletes stored consent, a new request may need to prompt again. However, deleting consent does not automatically expire existing JWT access tokens; if the goal is immediate disconnection, you must implement a strategy to revoke refresh tokens, active authorizations, and/or access tokens according to token format and Resource Server capabilities.

## 10. Common Errors and Troubleshooting

| Symptom | Common Cause | How to Check |
| --- | --- | --- |
| GET consent returns 404 | <code>consentPage()</code> configured without MVC controller or template. | Check <code>@GetMapping</code>, view name, and Thymeleaf resolver. |
| Consent page loops back to login | Session not preserved, cookie blocked, wrong web chain, or context path/proxy mismatch. | Check chains, session, forwarded headers, and SameSite/Secure flags. |
| POST returns 404 | Form action does not match the Authorization Endpoint. | Compare against <code>AuthorizationServerSettings.getAuthorizationEndpoint()</code>. |
| POST returns 403 | CSRF token does not match the active filter chain. | Check CSRF matcher and hidden input; keep form-login protection intact. |
| Infinite consent loop | Form missing or using wrong consent state, session changed, or POST lacks valid scopes. | Compare consent redirect state against submitted state. |
| Form displays unrequested scopes | Rendering all of <code>client.getScopes()</code>. | Read the scope list from the consent redirect and authorization request. |
| Form does not grant selected scopes | Using an input name other than <code>scope</code> or wrong action. | Inspect POST body and endpoint response. |
| User denies yet still receives a code | Unwanted hidden scope input or custom handler bypassing consent. | Inspect form payload and test denial path. |
| Consent prompted every time | In-memory state lost on restart, unstable principal/client record ID, or multiple nodes with separate stores. | Inspect <code>OAuth2AuthorizationConsentService</code>. |
| Unexpected client name displayed | Reading `client_name` from query or unvetted data. | Always fetch from trusted <code>RegisteredClient</code>. |
| Page vulnerable to XSS | Unescaped client/scope rendering. | Use <code>th:text</code>/<code>th:value</code>, CSP, and test special characters. |

When debugging, inspect all three segments: **AS redirect to GET consent**, **MVC form rendering**, and **POST back to AS**. An HTTP 200 on the HTML page does not prove the Authorization Endpoint verified the state and issued a valid token.

### 10.1. PAR/JAR and Advanced Authorization Requests

With Pushed Authorization Requests (PAR), JWT-Secured Authorization Requests (JAR), or profiles using request objects, do not reconstruct the scope list solely from raw browser query parameters. Use the Authorization Server's built-in mechanism and test the consent redirect data on the exact version being deployed. Some versions have reported issues where scopes do not appear properly in custom consent when combined with PAR; this is why integration tests are essential rather than injecting hidden permissions into forms.

## 11. Testing the UI and Consent Decisions

### 11.1. Unit/MVC Tests for the Screen

Assuming Spring MVC tests have configured a test principal, client <code>orders-web</code>, and repositories:

~~~java
@Test
void consentPageShowsTrustedClientAndRequestedScopes() throws Exception {
    mockMvc.perform(get("/oauth2/consent")
            .param("client_id", "orders-web")
            .param("scope", "orders.read")
            .param("state", "example-consent-state")
            .with(user("alice")))
        .andExpect(status().isOk())
        .andExpect(view().name("oauth2-consent"))
        .andExpect(model().attribute("clientId", "orders-web"))
        .andExpect(model().attributeExists("newScopes"));
}

@Test
void consentPageRejectsScopeNotRegisteredForClient() throws Exception {
    mockMvc.perform(get("/oauth2/consent")
            .param("client_id", "orders-web")
            .param("scope", "admin.full_access")
            .param("state", "example-consent-state")
            .with(user("alice")))
        .andExpect(status().isBadRequest());
}
~~~

These are **UI rendering tests** and do not verify that real consent state exists in the authorization store. To prove security, you must test an actual POST through the Authorization Endpoint while preserving the session and server-issued consent state. For HTML templates, add tests with a client name containing <code>&lt;script&gt;</code> to verify escaping and ensure no checkboxes appear for unrequested scopes.

### 11.2. Integration Test Matrix

| Case | Expected Result |
| --- | --- |
| Unauthenticated user opens consent page | Must log in or be rejected; never leaks another user's consent. |
| Non-existent client ID | Never renders a fake client; fails safely. |
| Client requests one scope out of multiple registered scopes | UI displays only permissions in the consent context. |
| Client metadata contains HTML characters | Output is escaped; no script execution. |
| Alice already has <code>orders.read</code> in prior consent | Distinguishes previously granted permissions from new ones. |
| Approve a valid scope | AS stores/reads consent accurately and grants only valid permissions. |
| Tamper with POST to send unrequested scope | AS rejects or refuses to grant beyond policy. |
| Deny without selecting any scope | Does not issue an authorization code as on approval. |
| Missing/invalid consent state | Does not continue authorization. |
| Another user's state or replayed form | Does not accept an authorization that is no longer valid. |
| Missing/invalid servlet CSRF token when filter requires it | Rejected by the CSRF filter. |
| Change client ID between GET and POST | Does not grant permissions to a different client. |
| Session expires between viewing and submitting form | Forces re-login/re-initiates flow per policy. |
| Custom context path / reverse proxy | Form action and redirects generate accurate public URLs. |
| Multiple instances | Session, authorization state, and consent storage remain consistent. |
| PAR/JAR if enabled | Scopes and state are delivered properly to the UI on the deployed version. |

### 11.3. Repeatable End-to-End Procedure

1. Register a test client with <code>requireAuthorizationConsent(true)</code>, valid redirect URI, and scopes; create a test user.
2. Send <code>GET /oauth2/authorize</code> with <code>response_type=code</code>, <code>client_id</code>, scopes, client state, and valid PKCE.
3. Log in through the web chain, retaining the session/cookie.
4. Verify the Authorization Server redirects to <code>/oauth2/consent</code> with <code>client_id</code>, <code>scope</code>, and **AS-generated consent state**.
5. Render the UI and verify the client name, scope descriptions, checkboxes, and previously granted permissions if any.
6. POST to <code>/oauth2/authorize</code> with the exact consent state, client ID, and selected scopes, plus CSRF token if required.
7. Verify the redirect goes to the **registered redirect URI** with an authorization code and the original OAuth client state. Exchange the code with PKCE and verify the access token contains no extra scopes.
8. Repeat for denial, scope tampering, client ID tampering, state replay, session switching, and invalid CSRF token scenarios.

Never use a single controller unit test or a mocked `Authentication` test to claim the OAuth2/OIDC flow is fully protected. The Authorization Endpoint, consent provider, and token issuance together are what require integration testing.

## 12. Operating Consent UI in Production

Before releasing the screen to real users, ensure:

- **Metadata and scope catalog:** application name, logo, domain, and permission descriptions are governed and reviewed; never let clients inject arbitrary HTML.
- **UI consistency:** clear labels, keyboard/screen-reader accessibility, sufficient contrast, responsive layout, and an always-visible Deny button.
- **HTTP security:** HTTPS/HSTS, appropriate cookie attributes, CSP restricting scripts and framing, Referrer-Policy, `Cache-Control: no-store`, and XSS/CSRF protection.
- **Session and authorization state:** consistent across multiple instances; use durable storage where required and enforce timeouts.
- **Consent persistence:** if decisions must survive restarts, use JDBC or an appropriate durable store; in-memory is only for demos/tests.
- **Audit:** record principal ID, registered client record ID, selected scopes, timestamp, and outcome; never log credentials, tokens, or raw state values.
- **Distinguish revocation:** deleting consent does not automatically invalidate active access/refresh tokens; a disconnect feature needs its own token revocation policy.
- **Monitoring:** approval/denial rates, state errors, CSRF failures, scope mismatches, callback errors, and proxy issues.

A polished screen can make users trust a risky application more than it deserves. Therefore, **client verification workflows and honest permission descriptions** are direct security controls of the consent UI.

## 13. Practical Exercise

An Authorization Server serves three clients:

- <code>customer-portal</code> uses OIDC and scopes <code>openid profile orders.read</code>.
- <code>partner-integration</code> is registered with <code>orders.read orders.write</code>, but typically requests only read access.
- <code>billing-dashboard</code> requests <code>invoices.read</code> and <code>invoices.export</code>.

Complete the following:

1. Design a consent page mockup showing the client name/ID, active account, new scopes, previously granted permissions, and two action choices.
2. Create an English scope catalog, distinguishing <code>openid</code>/<code>profile</code> from business permissions.
3. Configure <code>consentPage("/oauth2/consent")</code>, the AS chain, and a separate web chain, explaining why the AS matcher should use <code>getEndpointsMatcher()</code>.
4. Write an MVC controller that loads trusted data from <code>RegisteredClientRepository</code> and prior consent from <code>OAuth2AuthorizationConsentService</code>.
5. Write a Thymeleaf form that POSTs to the Authorization Endpoint with the exact <code>client_id</code>, <code>state</code>, <code>scope</code>, and CSRF token where applicable; the deny form must not inject scopes.
6. Prove via tests that registering many scopes on a client does not cause the UI to display all scopes on every request.
7. Use DevTools to tamper with the form by trying <code>admin.full_access</code>, swapping in another user's state, changing the client ID, and double-submitting.
8. Test Alice already having <code>orders.read</code> while requesting <code>orders.write</code>; only valid permissions are reviewed and saved.
9. Define how to operate the consent store, client metadata, multi-tenancy, and token revocation when a “Disconnect” button is provided.

A passing design must demonstrate that **the UI shows the right client and scopes for review**, **the user has a genuine choice**, and **the Authorization Server validates independently before issuing any code or token**.

## 14. References

- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): configuring the Authorization Endpoint and custom consent page.
- [OAuth2AuthorizationEndpointConfigurer API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OAuth2AuthorizationEndpointConfigurer.html): redirect parameters and POST requirements when using <code>consentPage()</code>.
- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): <code>RegisteredClient</code>, <code>OAuth2AuthorizationConsent</code>, and <code>OAuth2AuthorizationConsentService</code>.
- [Spring Authorization Server — Getting Started](https://docs.spring.io/spring-authorization-server/reference/getting-started.html): client configuration, security filter chain, and authorization flow.
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): consent route authorization policy.
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF filter and form tokens.
- [Thymeleaf + Spring Tutorial](https://www.thymeleaf.org/doc/tutorials/3.1/thymeleafspring.html): forms, <code>th:text</code>, <code>th:value</code> expressions, and escaping.
- [RFC 6749, §4.1 — Authorization Code Grant](https://www.rfc-editor.org/rfc/rfc6749#section-4.1): authorization request, state, and scope.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): OIDC scopes and consent.
