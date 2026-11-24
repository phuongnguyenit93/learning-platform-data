# Saml2WebSsoAuthenticationRequestFilter and AuthnRequest Initiation

> **Module:** Spring Security – federation. **Group:** SAML2 login flow. This lesson explains the **SP-initiated SAML Web SSO** flow in Spring Security Servlet: from requesting a protected resource to `Saml2WebSsoAuthenticationRequestFilter`, how the resolver builds `AuthnRequest`, sends it via browser to the Identity Provider (IdP), stores context to correlate the response, and configuration, security, and testing choices. API examples focus on Spring Security 6.3.x / Spring Boot 3.x; when upgrading major versions, check the documentation for the running version.

## 1. What Is an AuthnRequest and What Does This Filter Do?

In SAML 2.0 Web SSO, the application acts as the **Service Provider (SP)** or **Relying Party**, while the **Identity Provider (IdP)**, also called the **Asserting Party**, is responsible for authenticating the user and issuing a SAML assertion/response. To initiate login from the SP, the application builds an XML `<samlp:AuthnRequest>` message asking the IdP to perform authentication. The browser transports the request to the IdP via the HTTP-Redirect or HTTP-POST binding.

**Saml2WebSsoAuthenticationRequestFilter** is Spring Security's entry point that **creates and sends the AuthnRequest** in the Servlet filter chain. It does not verify a `SAMLResponse` and has not yet granted any authority to the user. Receiving and validating `SAMLResponse` at the ACS belongs to **Saml2WebSsoAuthenticationFilter** together with the converter, authentication manager, and OpenSAML provider.

| Component | What Does It Receive? | What Does It Do? | Result |
| --- | --- | --- | --- |
| `Saml2WebSsoAuthenticationRequestFilter` | Initiation request, e.g., `GET /saml2/authenticate/corp` | Resolves configuration, prepares AuthnRequest, saves pending request, sends to IdP | Redirect/POST containing `SAMLRequest` |
| `Saml2WebSsoAuthenticationFilter` | `SAMLResponse` callback to SP ACS | Resolves registration, uses saved request, authenticates response/assertion | `Authentication` success or failure |
| `AuthorizationFilter` / `ExceptionTranslationFilter` / `AuthenticationEntryPoint` | Request to a protected page while unauthenticated | Initiates login flow/navigates to login page or AuthnRequest creation URL | Browser enters request filter |
| `RelyingPartyRegistrationRepository` | Configured SP/IdP registrations | Supplies issuer, ACS, SSO URL, binding, keys | Trust data for resolver to build request |

**Common pitfall:** AuthnRequest is only a **request to start authentication** from the SP; it is not an assertion signed by the IdP confirming the user. Never treat "the request filter ran" as the user being authenticated.

### Learning Outcomes

After this lesson, the reader will:

- Describe the SAML initiation URL and the chain of filters/entry points leading to it.
- Distinguish the request filter, resolver, registration repository, and request-state repository.
- Read an `AuthnRequest`: `ID`, `IssueInstant`, `Destination`, `Issuer`, `AssertionConsumerServiceURL`, and `ProtocolBinding`.
- Explain how Redirect and POST bindings encode requests, where signatures live, and when the SP must sign.
- Understand the boundary between a pending request in HttpSession, `RelayState`, `InResponseTo`, and the post-login session.
- Configure and customize Spring Security 6.3 APIs properly, testing both valid flows and negative cases.

## 2. Overall SP-initiated SAML Login Flow

Assume the following **mock** values:

```text
SP public origin:       https://portal.example.org
registrationId:         corp
SP entityId:            https://portal.example.org/saml/sp/corp
SP AuthnRequest path:   /saml2/authenticate/corp
IdP entityId:           https://login.example.org/idp
IdP SingleSignOnService https://login.example.org/saml/sso
SP ACS:                 https://portal.example.org/login/saml2/sso/corp
Request binding:        HTTP-Redirect
Response binding:       HTTP-POST
```

Processing sequence:

```text
Browser                    Spring Security SP                  IdP
   |                              |                             |
   | GET /private                 |                             |
   |----------------------------->|                             |
   | AuthorizationFilter: requires authentication               |
   | ExceptionTranslationFilter + AuthenticationEntryPoint      |
   |<-----------------------------| redirect login              |
   | GET /saml2/authenticate/corp |                             |
   |----------------------------->|                             |
   |  Saml2WebSsoAuthenticationRequestFilter                    |
   |     -> RequestResolver finds registration corp             |
   |     -> builds ID/Issuer/Destination/ACS and AuthnRequest   |
   |     -> signs/encodes per binding; generates RelayState     |
   |     -> saves pending request in repository                 |
   |<-----------------------------| 302 to IdP SSO + SAMLRequest
   | GET IdP /saml/sso?SAMLRequest=...                          |
   |----------------------------------------------------------->|
   |                              |       IdP verifies request  |
   |                              |       login/MFA user        |
   |<-----------------------------------------------------------|
   | HTML form POSTs SAMLResponse to SP ACS                     |
   | POST /login/saml2/sso/corp   |                             |
   |----------------------------->|                             |
   |   Saml2WebSsoAuthenticationFilter                          |
   |     -> finds pending request, checks InResponseTo          |
   |     -> validates trust/issuer/signature/audience/time      |
   |     -> Authentication, SecurityContext, session            |
   |<-----------------------------| redirect /private           |
```

This is an **SP-initiated** flow. If the IdP sends an **unsolicited/IdP-initiated SAMLResponse**, there may be no preceding AuthnRequest. That is a separate case requiring acceptance policies and defenses against login injection/replay. Do not infer from the diagram that every response may omit `InResponseTo`.

### 2.1. From Protected Page to Request Filter

If the browser calls `GET /private` while unauthenticated, `AuthorizationFilter` denies access. `ExceptionTranslationFilter` and `AuthenticationEntryPoint` direct the browser into the login flow. When only one registration exists and configuration allows, the entry point can redirect straight to the request creation URL. When multiple IdPs exist, the app may show an **identity provider selection page** first.

The browser can also visit `/saml2/authenticate/corp` directly via a "Sign in with corporate SSO" link. In that case the request filter is triggered without requiring a prior `/private` request.

Do not create your own REST controller at `/saml2/authenticate/corp` on the same URL if Spring Security already owns that endpoint. This endpoint is a protocol filter; a controller returning JSON will not safely replace creating, signing, and storing the AuthnRequest.

### 2.2. Three Addresses Frequently Confused

| Address | Whose Side? | Action |
| --- | --- | --- |
| `https://portal.example.org/saml2/authenticate/corp` | SP | Starts login and creates AuthnRequest |
| `https://login.example.org/saml/sso` | IdP | Receives AuthnRequest via `SingleSignOnService` |
| `https://portal.example.org/login/saml2/sso/corp` | SP | Receives SAMLResponse at `AssertionConsumerService` (ACS) |

`SP entityID` is the logical identifier of the SP placed in `Issuer`; it is **not required** to be a URL with an active endpoint. `registrationId=corp` is Spring Security's internal name to select the registration—**not** the IdP entityID or a username.

## 3. Saml2WebSsoAuthenticationRequestFilter and Its Collaborators

### 3.1. Request Endpoint and Request Matcher

Typical default URL:

```http
GET /saml2/authenticate/corp HTTP/1.1
Host: portal.example.org
```

Current Spring Security documentation describes both the path form `/saml2/authenticate/{registrationId}` and a query form `/saml2/authenticate?registrationId={registrationId}`; matching/customization support must be checked against the specific version. For Spring Security 6.3, the path form with registration ID is a safe, explicit way to explain default behavior.

Matching depends on the **active SecurityFilterChain**: when a project has one chain for REST APIs and another for SAML web, `/saml2/authenticate/**` must hit the chain with `saml2Login()`. If a resource server chain matches this URL first, the SAML request filter may never run.

### 3.2. Key Classes and Responsibilities

| Type | Role |
| --- | --- |
| `Saml2LoginConfigurer` | DSL that creates and configures SAML login filters when calling `http.saml2Login(...)` |
| `Saml2WebSsoAuthenticationRequestFilter` | Filter that dispatches a prepared SAML authentication request via Redirect/POST |
| `Saml2AuthenticationRequestResolver` | Interface resolving a request from `HttpServletRequest`, returning `AbstractSaml2AuthenticationRequest` or no match |
| `OpenSaml4AuthenticationRequestResolver` | OpenSAML 4 implementation in Spring Security 6.3, supporting customizers |
| `RelyingPartyRegistrationRepository` | Store of configured and approved registrations |
| `RelyingPartyRegistration` | Integration data for one SP–IdP pair: IDs, ACS, bindings, signing/verification keys |
| `Saml2AuthenticationRequestRepository` | Saves/loads/removes pending AuthnRequest for callback correlation |
| `HttpSessionSaml2AuthenticationRequestRepository` | Default implementation storing state in `HttpSession` |
| `AbstractSaml2AuthenticationRequest` | Common prepared request data type |
| `Saml2RedirectAuthenticationRequest` | Prepared request for HTTP-Redirect binding |
| `Saml2PostAuthenticationRequest` | Prepared request for HTTP-POST binding |
| `Saml2AuthenticationTokenConverter` | At callback, extracts SAMLResponse and resolves registration/request context |
| `Saml2WebSsoAuthenticationFilter` | ACS filter forwarding SAMLResponse to authentication manager/provider for verification |

**Version distinction:** Spring Security 6.3.x uses `OpenSaml4AuthenticationRequestResolver`. In newer versions, the underlying OpenSAML library and APIs may differ. When using a snippet across major versions, verify the actual javadoc, dependencies, and builder syntax.

### 3.3. Conceptual Logic When the Request Filter Runs

```text
HTTP request arrives at SP
  -> matcher selects URL /saml2/authenticate/{registrationId}
  -> resolver determines RelyingPartyRegistration
  -> uses SP/IdP config to build OpenSAML AuthnRequest
  -> determines RelayState, binding, signature per policy
  -> prepares AbstractSaml2AuthenticationRequest
  -> repository.saveAuthenticationRequest(...)
  -> if Redirect: returns 302/Location to IdP
     if POST: returns auto-submit HTML form to IdP
```

This is **pseudocode explaining responsibilities**, not a verbatim excerpt from a release's source code. Details of serialize/sign ordering, object constructors, and handling when the resolver does not match vary by version. Key takeaway: the filter does not pick an IdP from browser-supplied XML; it relies on **existing registrations** and the resolver strategy.

### 3.4. Request Filter vs. Response Filter

`Saml2WebSsoAuthenticationFilter` receives the browser's `POST` of `SAMLResponse` at the ACS, using the converter and provider to handle authentication. The Response/Assertion signature is verified with a trusted **IdP public signing certificate**. Do not use `Saml2WebSsoAuthenticationRequestFilter` or add callback-parsing logic to it.

After the request filter sends the request to the IdP, there is **no authenticated principal yet** from SAML login. `SecurityContext` is established once a valid callback is processed and authentication succeeds.

## 4. Registration Data Shapes AuthnRequest

`RelyingPartyRegistration` holds two-way configuration:

| Property | Side | Where Used? |
| --- | --- | --- |
| `registrationId` | SP | Selects the right IdP/SP integration when browser starts login |
| SP `entityId` | SP | `Issuer` value in AuthnRequest |
| `assertionConsumerServiceLocation` | SP | ACS address, may go into `AssertionConsumerServiceURL` |
| `assertionConsumerServiceBinding` | SP | Binding IdP uses to return response; may go into `ProtocolBinding` |
| `signingX509Credentials` | SP | Private signing key/certificate used to sign SP-issued messages |
| IdP `entityId` | IdP | IdP identifier to establish trust and verify callbacks |
| `singleSignOnServiceLocation` | IdP | `Destination`, URL where IdP receives requests |
| `singleSignOnServiceBinding` | IdP | HTTP-Redirect or HTTP-POST for SP-sent requests |
| `wantAuthnRequestsSigned` | IdP | IdP policy expecting SP to sign authentication requests |
| `verificationX509Credentials` | IdP | IdP public cert for SP to verify responses/assertions |

**Common mistakes:** putting the IdP entityID into AuthnRequest `Issuer`; putting the SP ACS into `Destination`; using the IdP verification certificate as the SP signing key; treating `acs.binding` as the request binding. These cause requests to be rejected or create broken trust boundaries.

### 4.1. Illustrative AuthnRequest XML

```xml
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_req_31f0a"
    Version="2.0"
    IssueInstant="2026-11-07T03:20:00Z"
    Destination="https://login.example.org/saml/sso"
    AssertionConsumerServiceURL="https://portal.example.org/login/saml2/sso/corp"
    ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST">
    <saml:Issuer>https://portal.example.org/saml/sp/corp</saml:Issuer>
    <samlp:NameIDPolicy
        Format="urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified"
        AllowCreate="true"/>
</samlp:AuthnRequest>
```

This is an **educational XML excerpt**, unsigned and not a complete message for a real IdP. Each field means:

- `ID`: request identifier, unique per transaction; the IdP can return a matching `InResponseTo`.
- `IssueInstant`: timestamp when the request was issued; the IdP may enforce a time window.
- `Destination`: **IdP SSO endpoint**.
- `Issuer`: **SP entityID**.
- `AssertionConsumerServiceURL`: **SP ACS URL** to which the IdP is permitted to return the response.
- `ProtocolBinding`: **binding expected for receiving SAMLResponse**, not the binding used to send AuthnRequest.
- `NameIDPolicy`: requested NameID format matching the contract with the IdP.
- `ForceAuthn` (optional): requests re-authentication; depends on IdP policy.

`RelayState` typically travels as a query parameter/form field per the HTTP binding, **not inside the AuthnRequest XML**. It must be generated/validated per login transaction and the application's redirect policy.

### 4.2. Starting Login Does Not Mean the IdP Has Authenticated

At the moment the ID is created, the SP only holds a "pending" state. The user does not yet have an IdP-confirmed `Saml2AuthenticatedPrincipal`/authenticated session. If the user closes the browser, cancels login, or the IdP does not respond, the pending state expires/is cleaned up per repository design; never treat an issued request as proof of success.

## 5. HTTP-Redirect and HTTP-POST Bindings

### 5.1. Redirect Binding

With Redirect, the XML request is raw-DEFLATEd, Base64-encoded, URL-encoded, and sent via the `SAMLRequest` query parameter to the IdP SingleSignOnService. If the request is signed, the signature usually resides in the **query** as `SigAlg` and `Signature`.

```text
XML AuthnRequest
  -> raw DEFLATE
  -> Base64
  -> URL-encoded SAMLRequest
  -> RelayState (if used)
  -> SigAlg + Signature (if signed)
  -> HTTP 302 Location: IdP SSO
```

Illustrative protocol format **for demonstration, not a valid payload**:

```http
HTTP/1.1 302 Found
Location: https://login.example.org/saml/sso?SAMLRequest=ENCODED_TEST_DATA&RelayState=opaqueState7&SigAlg=SIGNATURE_ALGORITHM_URI&Signature=ENCODED_SIGNATURE
```

To verify a Redirect signature, the IdP uses the **SP's** public signing certificate and the URL-encoded parameter string in exact order:

```text
SAMLRequest=<url-encoded-value>&RelayState=<url-encoded-value>&SigAlg=<url-encoded-value>
```

If there is no RelayState, omit the `RelayState=...` pair and its corresponding separator. `Signature` is the signing output, not part of the signed input string. With Redirect, the inflated XML may **have no `<ds:Signature>`**, yet the request is still validly signed via query parameters. Do not confuse the two signature forms.

### 5.2. POST Binding

If the IdP supports/requires POST, the request is Base64-encoded (without applying raw DEFLATE as in Redirect) and placed in a hidden field of an HTML form pointing to the IdP:

```html
<form action="https://login.example.org/saml/sso/post" method="post">
  <input type="hidden" name="SAMLRequest" value="BASE64_TEST_DATA"/>
  <input type="hidden" name="RelayState" value="opaqueState7"/>
  <button type="submit">Continue SSO</button>
</form>
```

This is **illustrative HTML**, not a replacement for Spring Security filters, signing, or nonce/state management. A signed POST AuthnRequest typically uses an **XML Digital Signature** directly inside the XML before Base64 encoding, rather than Redirect's `SigAlg` and `Signature` query parameters.

| Criterion | Redirect Request | POST Request |
| --- | --- | --- |
| Browser → IdP | GET | POST |
| `SAMLRequest` | Query parameter | HTML form field |
| Encoding | Raw DEFLATE + Base64 + URL encoding | Base64 XML |
| Typical signature location | Query `SigAlg`/`Signature` | XML `ds:Signature` |
| Target URL | IdP SingleSignOnService Redirect Location | IdP SingleSignOnService POST Location |
| Relation to ACS binding | Independent | Independent |

**Important:** the SP can send a **Redirect** AuthnRequest while setting `ProtocolBinding` in the XML to **HTTP-POST**: that field asks the IdP to return the **SAMLResponse** via POST to the ACS.

## 6. Storing Pending AuthnRequest and Callback Correlation

`Saml2AuthenticationRequestRepository` is the bridge between the initiation filter and the response-handling filter. It stores prepared request data so the callback can identify the IdP/registration, request ID, and trust context.

### 6.1. Default Uses HttpSession

`HttpSessionSaml2AuthenticationRequestRepository` is the common default in Spring Security 6.x. It saves the `AbstractSaml2AuthenticationRequest` object in the SP's browser HTTP session. When the response reaches the ACS, Spring Security retrieves the waiting request, checks `InResponseTo`, and verifies registration context.

Before login, this session is a **pending login session**, not an authenticated principal. After a successful callback, Spring Security can save the login `SecurityContext`/session. Assertion lifetime is distinct from HttpSession lifetime.

### 6.2. Distinct from RequestCache and SavedRequest

| Store | What Does It Store? | What Is It Used For? |
| --- | --- | --- |
| `RequestCache` | Request to internal page (e.g., `/private`) before login | Navigating back to that page after login |
| `Saml2AuthenticationRequestRepository` | Sent prepared AuthnRequest, RelayState/SAML context | Correlation when receiving SAMLResponse |
| `SecurityContextRepository` | Authenticated `Authentication` details | Preserving identity across subsequent requests |

Do not use `RequestCache` to replace `InResponseTo`/pending SAML request storage. The two kinds of "saved requests" solve different problems.

### 6.3. Session Cookies, SameSite, and Cross-Site POST

In the common flow, the request filter starts login at the SP, and later the browser POSTs `SAMLResponse` **from the IdP origin to the SP origin**. If the SP session cookie uses `SameSite=Lax` or `Strict`, the browser may withhold the cookie on the cross-site POST. Then the response filter cannot find the pending request in `HttpSession` even though `SAMLResponse` is valid.

Remediation steps:

1. In a real browser, inspect `Set-Cookie` at initiation and the `Cookie` header on the ACS POST.
2. Check `SameSite`, `Secure`, HTTPS public origin, and trusted reverse proxies.
3. If cookies must ride on cross-site POSTs, consider a `SameSite=None; Secure` strategy with proper CSRF defenses, or a controlled alternative state/correlation design.
4. For multi-node SPs, use session replication or a compatible shared session store when callbacks hit another pod.
5. Never disable `InResponseTo` or accept all unsolicited responses to mask session-loss symptoms.

### 6.4. Moving to an External Cache Must Preserve Browser Binding

The repository can be replaced with a distributed-cache implementation to solve replication/SameSite. However, **looking up `RelayState` or `InResponseTo` in a cache does not by itself prove the browser receiving the response initiated that request**. An attacker could try to create a login transaction and cause **login injection/login fixation** if correlation is weak.

Minimum requirements: high-entropy state, short TTL, single use, concurrent request limits, binding to registration/tenant, protection against log leakage, atomic failure/replay handling, and policies ensuring browser/transaction binding. SAML signature/trust/audience/time validation remain mandatory. Test across multiple tabs and multiple SP replicas.

## 7. Spring Boot 3.x / Spring Security 6.x Configuration

### 7.1. SecurityFilterChain

Create `SamlSecurityConfiguration.java` in a Spring Boot project with the SAML2 service provider dependency:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults());

        return http.build();
    }
}
```

This is a **Spring Boot configuration class**, not a standalone Java program runnable directly with `java`. `saml2Login()` configures the SAML request + response filters. A `RelyingPartyRegistrationRepository` bean or Boot configuration to create one must be supplied; the code above does not include an IdP on its own.

If you use the `saml2Login()` DSL, do not manually instantiate `new Saml2WebSsoAuthenticationRequestFilter(...)` and add the filter a second time. Manually registering two filters risks double registration, wrong matchers, or state drift.

### 7.2. Mock application.yml

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            entity-id: "{baseUrl}/saml/sp/{registrationId}"
            acs:
              location: "{baseUrl}/login/saml2/sso/{registrationId}"
              binding: POST
            signing:
              credentials:
                - private-key-location: "file:/run/secrets/sp-signing.key"
                  certificate-location: "file:/run/config/sp-signing.crt"
            assertingparty:
              entity-id: "https://login.example.org/idp"
              singlesignon:
                url: "https://login.example.org/saml/sso"
                binding: REDIRECT
                sign-request: true
              verification:
                credentials:
                  - certificate-location: "file:/run/config/idp-signing.crt"
```

This example **will not work without actual key/certificate files, trust, and a real IdP registration**. `{baseUrl}`/`{registrationId}` are Spring Security URI placeholders resolved from the request/deployment configuration.

- `entity-id` is the SP entityID, placed in the request `Issuer`.
- `acs.location` is the SP callback, not the URL for sending AuthnRequests.
- `acs.binding` is the response binding, which can be POST.
- `assertingparty.singlesignon.url` is the IdP SSO endpoint receiving AuthnRequests.
- `assertingparty.singlesignon.binding` determines Redirect vs. POST for requests.
- `assertingparty.singlesignon.sign-request` configures the request signing policy.
- `signing.credentials` requires **SP private key + SP public certificate**.
- `assertingparty.verification.credentials` is the **IdP public signing certificate** to verify SAMLResponse/assertions.

**Do not use an IdP certificate as the SP private signing key.** If the IdP requires signed AuthnRequests, the SP needs the private key matching the cert registered at the IdP for verification.

### 7.3. Trigger Request and Network Path

Open:

```text
https://portal.example.org/saml2/authenticate/corp
```

If IdP SSO uses Redirect and policy requires signing, the browser typically receives a 302/303 to `https://login.example.org/saml/sso` with `SAMLRequest`, `SigAlg`, and `Signature`. If POST binding, the browser receives an auto-submit HTML form. If the endpoint returns 404, check the filter chain/matcher/registration; there is **no basis yet to say the IdP rejected login**.

### 7.4. Reverse Proxy and Public URLs

Suppose the SP runs internally at `http://10.0.0.5:8080`, while the public origin is `https://portal.example.org`. If `{baseUrl}` is computed from the internal origin, AuthnRequest may emit:

```text
AssertionConsumerServiceURL =
  http://10.0.0.5:8080/login/saml2/sso/corp
```

The IdP may reject it because it does not match the registered ACS. Configure proxy forwarded headers **from trusted ingress** and accurate public URLs, then check both SP metadata and actual requests. Do not disable Recipient/Destination validation to work around a mismatch.

## 8. Customizing AuthnRequest in the Right Place

### 8.1. When a Custom Resolver Is Needed

Common needs include changing `ForceAuthn`, `NameIDPolicy`, `RequestedAuthnContext`, or `RelayState`. For endpoints, bindings, signing, and certificates, prefer changing **RelyingPartyRegistration/metadata** before writing code. Those parameters are part of the SP–IdP contract, not controller business logic.

### 8.2. Spring Security 6.3 Example: ForceAuthn Customizer

Spring Security 6.3 uses `OpenSaml4AuthenticationRequestResolver`. The `setAuthnRequestCustomizer` API takes a callback providing `getAuthnRequest()`. Example class replacing the default configuration class above:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.web.authentication.OpenSaml4AuthenticationRequestResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ReauthenticationSamlConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            RelyingPartyRegistrationRepository registrations) throws Exception {

        OpenSaml4AuthenticationRequestResolver resolver =
                new OpenSaml4AuthenticationRequestResolver(registrations);

        resolver.setAuthnRequestCustomizer(context ->
                context.getAuthnRequest().setForceAuthn(Boolean.TRUE));

        http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .saml2Login(saml -> saml
                .authenticationRequestResolver(resolver));

        return http.build();
    }
}
```

**Technical note:** this is a Spring configuration class requiring matching dependencies/versions, not plain Java. `ForceAuthn=true` tells the IdP to re-authenticate, which can trigger repeated login/MFA prompts; **do not enable it globally** if normal SSO is desired. Depending on policy, enable it only where re-authentication is required. When upgrading Spring Security major versions, check the resolver/OpenSAML classes rather than copying 6.3 APIs blindly.

### 8.3. Custom authentication-request URI

Spring Security allows changing the initiation URL via `Saml2LoginConfigurer` configuration (`authenticationRequestUri` or `authenticationRequestUriQuery` API depending on version). When changing the path:

1. The resolver/matcher must match the new pattern.
2. The login page and `AuthenticationEntryPoint` must point to the new pattern.
3. The security filter chain must cover the new URL.
4. Select `registrationId` safely; never build an IdP from an arbitrary request.
5. **The ACS remains a separate endpoint**; it does not change automatically with the request URI.

Specifically, since version 6.3 differs from 7.x documentation, check the javadoc of the running version before using a specific method name.

### 8.4. RelayState Resolver

In Spring Security 6.3, `OpenSaml4AuthenticationRequestResolver` has `setRelayStateResolver(...)`. If customizing `RelayState`, ensure opaque values and policies defining length, TTL, allowed data, state/session binding, one-time use, and a redirect allowlist. A query like `returnUrl=https://attacker.example` must never become a post-SSO redirect target without validation.

## 9. Diagnosing Errors by Exact Filter Step

| Symptom | Most Likely Position | How to Handle |
| --- | --- | --- |
| `GET /saml2/authenticate/corp` returns 404 | URL/`SecurityFilterChain`/request matcher | Check chain matching and registration; IdP never received request |
| No redirect/form to IdP | Request resolver or registration | Check `RelyingPartyRegistrationRepository` and safe logs |
| Wrong IdP chosen in multi-tenant | Registration mapping | Bind tenant/issuer to trusted registrations |
| IdP returns "unknown SP" | `Issuer`/SP entityID | Cross-check IdP registration, metadata |
| IdP returns "destination invalid" | `Destination`/SSO URL | Cross-check SingleSignOnService Location per binding |
| IdP requires signed request | SP signing policy/key | Configure SP private key and register cert at IdP |
| Redirect XML lacks `ds:Signature` | Misunderstood binding | Inspect `SigAlg`/`Signature` query parameters |
| POST request rejected by IdP | Binding/endpoint/XML signature | Use correct POST SSO Location and key, validate XML sig |
| ACS URL in XML is internal HTTP | Forwarded headers/public baseUrl | Fix reverse proxy trust and ACS metadata |
| Callback cannot find pending request | HttpSession/cookie/SameSite/TTL | Check POST cookie/session/shared state |
| Wrong `InResponseTo` | Pending request differs from callback | Reject; investigate multiple tabs, session, RelayState |
| Response signature valid yet still fails | `Issuer`, audience, recipient, time, request binding | Investigate response filter/provider |
| Login loop | Session/ACS/request correlation/validation | Inspect full HTTP redirects and rejection reason logs |
| `RequestCache` returns to wrong URL | SavedRequest/success handling | Separate navigation inspection from AuthnRequest repository |
| Login succeeds but lacks permissions | Authorization mapping | Fix policy/domain roles; never alter request filter to grant permissions |

Do not assume 401/403/404 all share one cause: `SecurityFilterChain`, the IdP server, and the callback handler return codes differently. Combine HTTP traces, event details, and authentication configuration to isolate the cause.

### 9.1. Special Case: Session State Lost at Callback

Start by confirming **the request was actually created and saved** at the SP; next inspect cookies sent by the browser on the IdP POST to ACS, session ID/TTL, proxies, and multi-node environments. If the SP tries looking up the request in an empty session, never fix it by disabling `InResponseTo` or SAML signature verification.

### 9.2. Special Case: Signing Keys and Algorithms

A signed Redirect AuthnRequest needs properly encoded query signatures and the SP signing private key; a signed POST typically needs an XML Signature. The default/negotiated algorithm depends on IdP metadata and library version; RSA-SHA256 is common—avoid downgrading to SHA-1 just to "make it work". Certificate rollover requires the IdP to accept the new SP public key before the SP starts signing with the new key.

## 10. Security Boundaries That Must Not Be Bypassed

1. **Metadata and IdP trust:** the browser may only select from preconfigured registrations. Never fetch metadata from an attacker-supplied URL and automatically trust that signing key.
2. **Request signing:** sign AuthnRequests when IdP policy requires, using the SP private key; never use the IdP certificate as a signing credential.
3. **Response validation:** verify the IdP signing key, issuer, audience, recipient, destination, time conditions, and request correlation; the request filter does not do this.
4. **Replay/one-time:** the pending request is tied to the login transaction; response/assertion anti-replay is a separate validation layer and is not guaranteed just because an HTTP session exists.
5. **RelayState:** a state/navigation hint, not a trust anchor. Block login injection and open redirects.
6. **Session:** `Secure`/`HttpOnly` cookies, `SameSite` compatible with cross-site POST, rotate session ID after login, and invalidate on server-side logout.
7. **Multi-IdP/multi-tenant:** isolate registrations, trust keys, account mapping, and permissions by issuer/tenant; never merge users solely by email while ignoring issuer.
8. **Logging:** never log raw `SAMLResponse`/assertions, cookies, private signing keys, or sensitive state; use correlation IDs and error codes.
9. **Authorization:** a valid `Saml2Authentication` still requires checking permissions per endpoint/resource/tenant before accessing data.

## 11. Java 17+ Practice: Simulating Pending Request and InResponseTo

This plain Java example illustrates why **state must be retained after issuing an AuthnRequest**. It models string matching only—it **does not build/parse XML, sign, or validate real SAML Responses or authentication**.

Save as `AuthnRequestCorrelationDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;

public class AuthnRequestCorrelationDemo {

    record PendingRequest(String id, String registrationId,
                          String trustedIdpIssuer) {}

    record ResponseInfo(String inResponseTo,
                        String registrationId, String idpIssuer) {}

    static boolean consumeIfMatched(
            ResponseInfo response, Map<String, PendingRequest> pending) {
        PendingRequest request = pending.get(response.inResponseTo());
        if (request == null) {
            return false;
        }
        if (!request.registrationId().equals(response.registrationId())) {
            return false;
        }
        if (!request.trustedIdpIssuer().equals(response.idpIssuer())) {
            return false;
        }
        pending.remove(request.id());
        return true;
    }

    public static void main(String[] args) {
        Map<String, PendingRequest> pending = new HashMap<>();
        pending.put("_req_42", new PendingRequest(
                "_req_42", "corp", "https://login.example.org/idp"));

        ResponseInfo wrongTenant = new ResponseInfo(
                "_req_42", "partner", "https://login.example.org/idp");
        ResponseInfo correct = new ResponseInfo(
                "_req_42", "corp", "https://login.example.org/idp");

        System.out.println("initial pending: " + pending.size());
        System.out.println("wrong registration: "
                + consumeIfMatched(wrongTenant, pending));
        System.out.println("correct response: "
                + consumeIfMatched(correct, pending));
        System.out.println("replayed response: "
                + consumeIfMatched(correct, pending));
        System.out.println("remaining pending: " + pending.size());
    }
}
```

Run with JDK 17+:

```bash
javac AuthnRequestCorrelationDemo.java
java AuthnRequestCorrelationDemo
```

Exact stdout:

```text
initial pending: 1
wrong registration: false
correct response: true
replayed response: false
remaining pending: 0
```

**Analysis:** Request `_req_42` is bound to `corp` and the expected issuer. A response with the wrong registration leaves the pending state untouched, a matching response consumes the ID, and a subsequent replay is rejected. However, an attacker could craft a `ResponseInfo` object with forged data: **the `true` result reflects only the example logic**, not a real issuer or valid signature. Production systems must use Spring Security/OpenSAML to verify signature, issuer, audience, recipient, time, subject confirmation, binding, and replay before creating `Authentication`. `HashMap` also lacks atomic consume and cross-node storage; do not copy this snippet into production.

## 12. Integration Test Scenarios

| Test | Secure Expectation |
| --- | --- |
| Access protected URL while unauthenticated | Entry point sends browser into SAML login |
| Call `/saml2/authenticate/corp` | Selects registration `corp` and creates AuthnRequest |
| Call nonexistent registration | Does not create a request for an arbitrary IdP |
| Redirect binding | 302 with `SAMLRequest`, targeting exact IdP SSO URL |
| Signed Redirect request | Query includes `SigAlg`/`Signature`; test IdP verifies it |
| POST binding | HTML form `SAMLRequest` POSTs to IdP POST SSO |
| Response uses POST while request used Redirect | Valid if ACS/IdP agreed |
| SP signing key missing when signing required | Does not emit a request treated as validly signed |
| Wrong SP entityID | IdP rejects or reports unknown issuer |
| Wrong public ACS URL behind proxy | Detected; do not disable Recipient validation |
| `InResponseTo` mismatches pending request | Rejected |
| Lost session cookie at callback | Safely rejected and SameSite/session investigated |
| RelayState points outside allowlist domain | No open redirect |
| Two tabs logging in with different registrations | No mixing of state/issuer/tenant |
| Callback routed to another pod | Uses compatible session/store or fails safely |
| Invalid SAMLResponse signature | SP rejects authentication |
| Validly signed SAMLResponse with wrong audience | SP rejects |
| Replay same response/assertion | Does not issue another login session |
| Successful login then open `/private` | Authenticated session + authorization work |
| User lacks permissions on `/admin` | 403/denied per policy despite SAML login |

When testing in a browser, observe HTTP requests in sequence, but **never share raw SAMLResponses or session cookies in issues/traces**. Log `registrationId`, event, request correlation ID, rejection reason, and timestamp after sanitizing sensitive data.

### 12.1. Minimal Diagnostic Procedure

1. Verify the filter chain matches `/saml2/authenticate/{registrationId}`; did the request reach the request filter?
2. Verify the repository contains the needed registration; SP entityID, IdP SSO Location/Binding, and SP ACS are accurate.
3. Inspect the actual Redirect/POST emitted per binding—is the request signature formatted correctly and is the SP cert trusted?
4. Verify the browser sent `SAMLRequest` to the right IdP, and the IdP accepted it and returned `SAMLResponse`.
5. Verify the ACS received the POST and found the right pending request/state/session; check `SameSite`.
6. Verify SAMLResponse signature/issuer/audience/recipient/time and `InResponseTo` were checked; only then should `Authentication` exist.
7. Check success handler, `SavedRequest`, and authorization when the user returns to the app.

## 13. Review Questions

**1. Does `Saml2WebSsoAuthenticationRequestFilter` create the user principal?**  
No. The filter creates the **AuthnRequest**. The principal is created when the SAMLResponse callback is successfully authenticated by the response filter/provider.

**2. Using `/saml2/authenticate/corp`; is `corp` the IdP entityID?**  
No. It is Spring's internal **registrationId**, selecting the defined SP/IdP configuration.

**3. Where do `AuthnRequest.Destination` and `AssertionConsumerServiceURL` point?**  
`Destination` points to the **IdP SSO endpoint**; `AssertionConsumerServiceURL` points to the **SP ACS endpoint**.

**4. Why doesn't `ProtocolBinding=HTTP-POST` force AuthnRequest to be sent via POST?**  
Because the `ProtocolBinding` field in AuthnRequest specifies the **SAMLResponse binding** the SP wishes to receive, not the transport for the request to the IdP.

**5. A request is signed, yet the Redirect XML has no `ds:Signature`; is that wrong?**  
No. With **HTTP-Redirect binding**, the signature can reside in the `SigAlg`/`Signature` query parameters.

**6. What does `HttpSessionSaml2AuthenticationRequestRepository` do?**  
It stores the **pending AuthnRequest** and context to coordinate callbacks, not user roles or a `SavedRequest` for the original page.

**7. Why can callbacks lose state when `SameSite=Lax`?**  
Because `SAMLResponse` is usually sent via a **cross-site POST**; the browser may withhold the SP session cookie, making the pending request unfindable.

**8. Is an external cache keyed by `RelayState` automatically secure?**  
No. You must bind login to the browser/transaction, enforce TTL, one-time semantics, anti-replay, and full SAML validation to prevent login fixation/injection.

**9. Is `OpenSaml4AuthenticationRequestResolver` used in every Spring Security version?**  
No. That is an API of the OpenSAML 4 generation such as Spring Security 6.3; other major versions may change the resolver and builder APIs.

**10. Why does a response with a valid signature still need `InResponseTo` checked?**  
The signature proves the source/signed data integrity; `InResponseTo` binds the response to the **login transaction the SP initiated**, preventing request mix-ups and certain forms of login injection/replay.

## References

- [Spring Security – SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html) – entrypoint, request filter, and response filter.
- [Spring Security – Producing AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html) – request endpoint, repository, cache, binding, and signing.
- [Spring Security 6.3 API – OpenSaml4AuthenticationRequestResolver](https://docs.spring.io/spring-security/site/docs/6.3.5/api/org/springframework/security/saml2/provider/service/web/authentication/OpenSaml4AuthenticationRequestResolver.html) – customization hooks.
- [Spring Security 6.3 API – AuthnRequestContext](https://docs.spring.io/spring-security/site/docs/6.3.5/api/org/springframework/security/saml2/provider/service/web/authentication/OpenSaml4AuthenticationRequestResolver.AuthnRequestContext.html) – accessing AuthnRequest and registration inside customizers.
- [Spring Security – Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html) – authenticating `SAMLResponse` on the ACS side.
- [OASIS SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf) – AuthnRequest structure, `Issuer`, `InResponseTo`, and conditions.
- [OASIS SAML 2.0 Bindings](https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf) – Redirect, POST, encoding, signatures, and RelayState.
- [OASIS SAML 2.0 Metadata](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf) – SP/IdP endpoints, bindings, certificates.
- [OWASP SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet) – signature validation, trust boundaries, and replay.

**Key takeaway:** `Saml2WebSsoAuthenticationRequestFilter` is the starting point of a **SAML authentication transaction**, not a response validator. It relies on the registration and request resolver to create `AuthnRequest`, send it to the IdP per binding/signing policy, save pending login context, and coordinate with the callback. Only after `Saml2WebSsoAuthenticationFilter`/provider verifies a valid `SAMLResponse` can Spring Security grant `Authentication` to the user and enforce authorization.