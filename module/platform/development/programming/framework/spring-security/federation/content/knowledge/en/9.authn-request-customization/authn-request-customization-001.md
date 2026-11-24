# Saml2AuthenticationRequestResolver and Extension Points Across Spring Security Versions

In Spring Security SAML 2.0 Login, **`Saml2AuthenticationRequestResolver`** is the interface that defines how to turn an **`HttpServletRequest`** of the Service Provider (SP, also called the Relying Party) into a SAML 2.0 authentication request sent to the Identity Provider (IdP, also called the Asserting Party). It is a key extension point when you need to customize `AuthnRequest`: requiring the user to re-authenticate with **`ForceAuthn`**, suggesting a `RequestedAuthnContext`, changing the SSO initiation path, handling multiple IdPs, or adjusting request generation according to enterprise policy.

Three separate layers must be understood:

1. **`Saml2AuthenticationRequestResolver`** decides and builds the outgoing AuthnRequest information; it does not authenticate the user.
2. **`RelyingPartyRegistrationRepository` / `RelyingPartyRegistrationResolver`** provides the IdP configuration, SP entity ID, endpoints, and certificates for the active trust pair.
3. **`Saml2AuthenticationRequestRepository`** stores the **issued request** for correlation when the SAML Response returns; this is a different object from the *resolver*, despite the similar name.

**Version note:** the `Saml2AuthenticationRequestResolver` interface appeared in Spring Security **5.7**. Spring Security 6.x documentation uses `OpenSaml4AuthenticationRequestResolver` in versions/configurations based on OpenSAML 4, whereas Spring Security 7.x has official examples with `OpenSaml5AuthenticationRequestResolver`. Do not copy classes and imports from one documentation branch to a different dependency branch without checking the API of the version pinned in your project.

## 1. What is an AuthnRequest and why do you need a resolver?

In the **SP-initiated SAML Web Browser SSO** model, the user accesses the application; the SP issues an `AuthnRequest` to the IdP to request authentication. The IdP may require a password, MFA, or reuse an existing SSO session according to policy. The IdP then returns a **SAML Response** to the SP's Assertion Consumer Service (ACS).

~~~text
Browser              Spring Security SP/RP                    IdP
    |                           |                              |
    | GET /private              |                              |
    +-------------------------->|                              |
    |                           | Select registrationId        |
    |                           | -> RelyingPartyRegistration   |
    |                           | -> Saml2AuthenticationRequestResolver
    |                           | -> AuthnRequest               |
    |                           | -> save correlation request   |
    | <---- Redirect / Form POST|                              |
    |---------------- SAMLRequest ----------------------------->|
    |                           |                         Authenticate
    |<----------------------- SAMLResponse ---------------------|
    |---- POST ACS ----------->|                              |
    |                     Verify signature, InResponseTo,       |
    |                     audience, recipient, timestamps       |
    |                     -> Authentication -> session         |
~~~

By default configuration, **`Saml2WebSsoAuthenticationRequestFilter`** triggers the SSO initiation flow at endpoints such as:

- `/saml2/authenticate/{registrationId}`, for example `/saml2/authenticate/corp`;
- `/saml2/authenticate?registrationId={registrationId}` in Spring Security versions that support it.

The filter needs a resolver to build the request as a Spring Security `AbstractSaml2AuthenticationRequest`. Depending on the binding, the concrete result is `Saml2RedirectAuthenticationRequest` or `Saml2PostAuthenticationRequest`.

**Do not confuse this:** an AuthnRequest is only an *authentication request*, not proof that the IdP has authenticated the user successfully. User permissions are only evaluated after the SP verifies the returning SAML Response/Assertion.

## 2. The Saml2AuthenticationRequestResolver Interface

Package of the interface:

~~~java
org.springframework.security.saml2.provider.service.web.authentication
~~~

Key signature model:

~~~java
public interface Saml2AuthenticationRequestResolver {
    <T extends AbstractSaml2AuthenticationRequest> T resolve(
            HttpServletRequest request);
}
~~~

This is a **simplified signature for learning the concept**, not the complete interface definition code; nullability annotations and API constants may differ by version. In Spring Security 6+/7+, `HttpServletRequest` belongs to the `jakarta.servlet.http` package (older branches may use `javax.servlet`).

Explanation:

- **Input:** the incoming HTTP request to the SP, usually carrying a path or parameter identifying `registrationId`.
- **Output:** an `AbstractSaml2AuthenticationRequest` matching the configured binding, or **null** when the request does not match a case handled by the resolver.
- **Responsibility contract:** look up the registration, build the SAML AuthnRequest XML data, and package the request so the filter sends it to the right IdP/binding.
- **Not responsible for:** verifying the SAML Response, mapping the principal, authorizing APIs, or persisting the session long-term.

Distinguishing several related types:

| Type | Function |
| --- | --- |
| `Saml2AuthenticationRequestResolver` | Generates an AuthnRequest for the current request |
| `RelyingPartyRegistrationResolver` | Finds and resolves the registration template based on the HTTP request |
| `DefaultRelyingPartyRegistrationResolver` | Common implementation of the registration resolver |
| `RelyingPartyRegistrationRepository` | Looks up a registration by registrationId |
| `Saml2AuthenticationRequestRepository` | Saves/reads/removes the issued SAML request to handle correlation with the Response |
| `Saml2AuthenticationTokenConverter` | Converts an incoming SAMLResponse into an unverified authentication token |
| `OpenSamlXAuthenticationProvider` | Verifies the Response/Assertion and creates an Authentication according to the OpenSAML version |

The resolver interface allows the filter/DSL layer to avoid depending directly on the details of how OpenSAML builds XML.

## 3. Main Elements in an AuthnRequest XML

Example **XML fragment** containing several commonly customized fields:

~~~xml
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_request-unique-id"
    Version="2.0"
    IssueInstant="2026-11-07T10:00:00Z"
    Destination="https://idp.example.test/sso"
    AssertionConsumerServiceURL="https://portal.example.test/login/saml2/sso/corp"
    ForceAuthn="true">
    <saml:Issuer>https://portal.example.test/saml/sp</saml:Issuer>
    <samlp:NameIDPolicy
        Format="urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified"
        AllowCreate="true"/>
    <samlp:RequestedAuthnContext Comparison="exact">
        <saml:AuthnContextClassRef>
            urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport
        </saml:AuthnContextClassRef>
    </samlp:RequestedAuthnContext>
</samlp:AuthnRequest>
~~~

This is an **illustrative XML snippet**, not a complete signed AuthnRequest. In practice, Spring Security generates a random ID, timestamp, encoding, binding, and signature according to the registration and policy. Do not use this static string itself as a real AuthnRequest.

Fields to understand:

| Attribute/Element | Meaning | Risk if modified incorrectly |
| --- | --- | --- |
| `ID` | Unique identifier of the AuthnRequest | Duplicate IDs break correlation and replay protection |
| `IssueInstant` | Time the SP issues the request | Incorrect time causes verification failures |
| `Destination` | IdP endpoint intended to receive the request | Wrong IdP/binding or open redirect |
| `Issuer` | SP entity ID | Mismatch with the SP registered at the IdP |
| `AssertionConsumerServiceURL` | Where the IdP sends the Response back | Wrong ACS/recipient or response sent to an untrusted location |
| `ProtocolBinding` | Desired binding for the IdP to return the Response, if specified | Mixing up the request-sending binding and response-returning binding |
| `ForceAuthn` | Requests the IdP to directly re-authenticate per SAML rules | Does not guarantee MFA |
| `IsPassive` | Requests the IdP not to interact directly with the user | May fail if no suitable SSO session exists |
| `NameIDPolicy` | Policy on how to represent the subject identifier | IdP does not support the format or invalid request |
| `RequestedAuthnContext` | Suggests the desired authentication context class | IdP may not support it; actual result must be verified |

The login initiation path **at the SP**, such as `/saml2/authenticate/corp`, is not `Destination` in the XML. `Destination` is the endpoint **at the IdP**. Similarly, the ACS callback receives the **SAMLResponse**, not where the browser asks the SP to start SSO.

## 4. RelyingPartyRegistrationResolver: Selecting the Right SP–IdP Before Creating an AuthnRequest

An AuthnRequest resolver typically relies on `RelyingPartyRegistrationResolver` to know which SP–IdP pair is in use. The configuration flow can look like this:

~~~text
RelyingPartyRegistrationRepository
    "corp"    -> SP Portal / Corporate IdP
    "partner" -> SP Portal / Partner IdP
             |
             v
DefaultRelyingPartyRegistrationResolver
             |
             v
OpenSaml4/5AuthenticationRequestResolver
             |
             v
AbstractSaml2AuthenticationRequest
             |
             v
Saml2WebSsoAuthenticationRequestFilter
~~~

A few common points of confusion:

- `registrationId` is an internal Spring Security key; it is **not required to equal** the SAML SP entityId or IdP entityId.
- `DefaultRelyingPartyRegistrationResolver` uses the repository and HTTP request context to select and resolve URI templates, such as `{baseUrl}`.
- If one SP connects to multiple IdPs, the registration must be selected by a rule-based mechanism; do not use an arbitrary user-supplied `idpUrl` parameter to issue an AuthnRequest to the Internet.
- `RelyingPartyRegistration` configuration must have the correct issuer, IdP SSO endpoint, signing credential, and ACS; a customizer cannot fix every registration error.
- When the application sits behind a reverse proxy, `{baseUrl}`/SP metadata must rely on a verified external URL, not blindly trust `X-Forwarded-Host` from the client.

## 5. Common Extension Point: Modifying OpenSAML AuthnRequest with a Customizer

This is the case developers need most often: creating an `AuthnRequest` using the standard configuration and then adjusting a few fields **before the encode/sign/send step**. Instead of building XML manually, use the official extension of the OpenSAML-based resolver.

### Spring Security 7.x + OpenSAML 5 Example

The following example uses Java 17+ and Servlet Spring Security 7.x, provided the project has the **`spring-security-saml2-service-provider`** module and an already valid `RelyingPartyRegistrationRepository` bean.

File `src/main/java/com/example/security/SamlAuthnRequestConfig.java`:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.web.DefaultRelyingPartyRegistrationResolver;
import org.springframework.security.saml2.provider.service.web.RelyingPartyRegistrationResolver;
import org.springframework.security.saml2.provider.service.web.authentication.OpenSaml5AuthenticationRequestResolver;
import org.springframework.security.saml2.provider.service.web.authentication.Saml2AuthenticationRequestResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlAuthnRequestConfig {

    @Bean
    Saml2AuthenticationRequestResolver authenticationRequestResolver(
            RelyingPartyRegistrationRepository registrations) {

        RelyingPartyRegistrationResolver registrationResolver =
                new DefaultRelyingPartyRegistrationResolver(registrations);

        OpenSaml5AuthenticationRequestResolver resolver =
                new OpenSaml5AuthenticationRequestResolver(
                        registrationResolver);

        resolver.setAuthnRequestCustomizer(context ->
                context.getAuthnRequest().setForceAuthn(true));

        return resolver;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            Saml2AuthenticationRequestResolver resolver) throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/healthz").permitAll()
                .anyRequest().authenticated())
            .saml2Login(saml -> saml
                .authenticationRequestResolver(resolver))
            .build();
    }
}
~~~

**Explanation:**

1. `DefaultRelyingPartyRegistrationResolver` looks up the configuration from the repository based on the login request information.
2. `OpenSaml5AuthenticationRequestResolver` builds the AuthnRequest using OpenSAML 5.
3. `setAuthnRequestCustomizer(...)` receives a context allowing modification of the **OpenSAML AuthnRequest object**; calling `setForceAuthn(true)` requests re-authentication.
4. `saml2Login(...authenticationRequestResolver(resolver))` passes the custom resolver directly to the Security DSL. This clarifies the connection point between the bean and the filter chain.
5. `securityFilterChain` serves only Servlet web; for SSO to work in practice you also need SP/IdP registrations, trust certificates, endpoints, user flow, and a running IdP.

**Warning:** the example sets `ForceAuthn=true` **for every request** created through this resolver. That can eliminate the benefit of SSO session reuse and force users to re-authenticate frequently. Apply it deliberately for operations requiring recent authentication or separate the flows clearly. **ForceAuthn does not guarantee MFA**; if MFA/assurance is needed, you must have IdP policy, an appropriate RequestedAuthnContext, and result verification.

This is a **Spring project configuration class**, not standalone Java run with a single `javac` then `java` command; there is no fixed stdout. Import names and APIs are based on Spring Security 7.x documentation with OpenSAML 5; **do not apply them verbatim to Spring Security 5.x or 6.x versions that do not yet support this class**.

### Example in a Branch Using OpenSAML 4

In some Spring Security **5.7/6.x** branches using OpenSAML 4, the idea is the same except the resolver is replaced:

~~~java
RelyingPartyRegistrationResolver registrationResolver =
        new DefaultRelyingPartyRegistrationResolver(registrations);

OpenSaml4AuthenticationRequestResolver resolver =
        new OpenSaml4AuthenticationRequestResolver(registrationResolver);

resolver.setAuthnRequestCustomizer(context ->
        context.getAuthnRequest().setForceAuthn(true));
~~~

This is a **replacement code snippet inside the bean**, assuming the `registrations` variable already exists and `OpenSaml4AuthenticationRequestResolver` is imported from package `org.springframework.security.saml2.provider.service.web.authentication`. Do not add both resolvers in parallel without a clear selection mechanism. Some classes/configurations are changed or removed across version upgrades; check which classes are actually on the classpath.

## 6. Map of Extension Points by Version

| Branch / API | Approach | Compatibility Notes |
| --- | --- | --- |
| **Spring Security 5.2–5.6** | Has SAML2 Login, but AuthnRequest customization capabilities differ from newer releases | Do not assume the `Saml2AuthenticationRequestResolver` interface exists before 5.7; read the docs for the exact release |
| **From 5.7** | Has `Saml2AuthenticationRequestResolver`, `authenticationRequestResolver(...)` method in DSL; OpenSAML-based resolver depending on version | Servlet API may be `javax.servlet` in older generations |
| **Spring Security 6.x** | Uses `jakarta.servlet`; docs for many 6.x branches show `OpenSaml4AuthenticationRequestResolver`, while OpenSAML 5 support depends on release/dependencies | Pin the exact dependency, check Javadoc/classpath and deprecation warnings |
| **Spring Security 7.x** | Official docs guide using `OpenSaml5AuthenticationRequestResolver` and `setAuthnRequestCustomizer` | Do not import OpenSAML 4 classes that are no longer present in the branch |
| **From Spring Security 6.0** | `authenticationRequestUriQuery(...)` can change the AuthnRequest initiation endpoint with query parameters | `authenticationRequestUri(...)` is deprecated; do not change the ACS callback URL with this method |
| **Many 6/7 branches** | Has `Saml2AuthenticationRequestRepository` for request correlation; default is typically an HttpSession repository | If using a distributed cache, bind the request–browser association carefully to prevent login CSRF/fixation |

Do not take a single version number in an article as proof that every patch release supports the exact same signature. Before implementing: check the Spring Boot/Security BOM, SAML service provider module, OpenSAML version, API imports, and migration notes. In particular, avoid mixing OpenSAML 4 and 5 dependencies manually to “fix” compile errors.

### Table for Choosing an Extension Mechanism by Need

| Goal | Suitable Tool | Should Not Use |
| --- | --- | --- |
| Change the URL users click to start SSO | `authenticationRequestUriQuery` / version-appropriate filter matcher | Manually editing the AuthnRequest Destination |
| Select an IdP by `registrationId` | `RelyingPartyRegistrationRepository`, `RelyingPartyRegistrationResolver` | Using an IdP URL passed freely from the browser |
| Add `ForceAuthn`, `IsPassive`, RequestedAuthnContext | OpenSAML AuthnRequest customizer of the appropriate resolver | Regex-editing signed XML |
| Change the IdP SSO endpoint or request-sending binding | `RelyingPartyRegistration` / asserting-party metadata | Rewriting the URL after signing |
| Change the ACS handling SAMLResponse | `loginProcessingUrl` and `assertionConsumerServiceLocation`, metadata, and IdP | Changing only the SSO initiation path |
| Store InResponseTo/RelayState safely | `Saml2AuthenticationRequestRepository` | Disabling correlation checks to “fix” login |
| Customize Response validation or principal | `Saml2AuthenticationTokenConverter`, version-appropriate authentication provider/validator | Putting assertion verification logic into the AuthnRequest resolver |

## 7. Changing the SSO Initiation Endpoint: authenticationRequestUriQuery

By default, users can start login at `/saml2/authenticate/corp`. If a custom URL is needed, such as `/auth/sso/start?registrationId=corp`, Spring Security 6.0+ allows configuring:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .saml2Login(saml -> saml
            .authenticationRequestUriQuery(
                "/auth/sso/start?registrationId={registrationId}"))
        .build();
}
~~~

This is an **alternative configuration example** for the `SecurityFilterChain` in section 5; do not define two beans with the same role simultaneously in one application. `{registrationId}` must identify a valid registration; test the actual URLs and redirects against your project's Spring Security branch.

**Changing only the initiation endpoint** does not change:

- the `SingleSignOnService` URL at the IdP to which the AuthnRequest is sent;
- the ACS `/login/saml2/sso/{registrationId}` to which the IdP POSTs the Response;
- the SP entity ID and IdP metadata.

If you define a custom resolver and matcher different from the default, you must align how the custom resolver recognizes the URL with the DSL. Do not assume `authenticationRequestUriQuery` will adjust a custom resolver's matcher as expected.

## 8. RequestedAuthnContext, ForceAuthn, IsPassive: Understanding the Semantics

### ForceAuthn

`ForceAuthn="true"` in a SAML AuthnRequest asks the IdP to directly re-authenticate the subject instead of relying solely on a prior session context. This is the way to express a *fresh authentication* requirement.

However:

- It is not synonymous with **MFA** or phishing-resistant authentication.
- It does not automatically elevate the user to a specific assurance level.
- It does not guarantee the IdP enforces the policy properly if integrated systems are incompatible.
- The SP must check `AuthnInstant` and `AuthnContext` from the **verified assertion** when a transaction requires a specific level of assurance.

### RequestedAuthnContext

`RequestedAuthnContext` can request one or more authentication context classes via **`AuthnContextClassRef`**, such as a class agreed upon with the IdP, and a `Comparison` option like `exact` per SAML.

~~~xml
<samlp:RequestedAuthnContext
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    Comparison="exact">
    <saml:AuthnContextClassRef>
        urn:oasis:names:tc:SAML:2.0:ac:classes:SmartcardPKI
    </saml:AuthnContextClassRef>
</samlp:RequestedAuthnContext>
~~~

The snippet above expresses only a **request** in the AuthnRequest, not an `AuthnStatement` asserting what the IdP actually did. If the IdP does not support the requested class, authentication may fail with an error such as `NoAuthnContext`. Even if the IdP returns a successful response, the RP must still verify the actual `AuthnContext` information when business logic requires assurance.

**Do not label a password-only URI as “MFA”.** If an organization uses custom assurance URIs, you must define the contract with the IdP and test actual behavior.

### IsPassive

`IsPassive="true"` requests that the IdP avoid interacting directly with the user. If authentication cannot succeed with the existing context, the IdP may return `NoPassive`. Do not simultaneously use `IsPassive=true` and expect an interactive login screen in all cases; the goals of the two options generally conflict.

### NameIDPolicy

`NameIDPolicy` allows the SP to request how the subject identifier is represented, such as persistent or transient if the IdP supports it. Which type to choose is a federation/account linking decision and should not be changed arbitrarily once users have linked accounts.

### Customizing OpenSAML Objects

When more than `setForceAuthn` is needed, you can use the context and the version's OpenSAML XML object API to modify elements. **There is no single snippet that “works for all OpenSAML versions”**: builders/factories and model classes depend on the version. Construct objects using the OpenSAML API of the branch in use and run integration tests against the specific IdP; do not build XML via string concatenation.

## 9. Per-Request Customization: Normal Login vs. Step-Up

A practical scenario:

- Viewing the dashboard: allow reusing the SSO session according to policy.
- Approving a payment: must have fresh authentication within 10 minutes and belong to an approved assurance class.

A common mistake is setting `ForceAuthn=true` for the **entire** SSO flow. That forces re-authentication on every login and still fails to prove sufficient MFA conditions.

A controlled design:

~~~text
Application receives business request
            |
       Check permissions
            |
      Needs fresh auth?
       |          |
      No         Yes
       |          |
   Normal login  Create server-side step-up intent
       |          |
       |         AuthnRequest:
       |         ForceAuthn=true
       |         RequestedAuthnContext per policy
       |          |
       +-----> IdP returns verified Response
                  |
             Verify AuthnInstant + AuthnContext
                  |
             Check business permissions again
                  |
             Allow or deny action
~~~

**Do not rely solely on a client-supplied `?force=true` query parameter to conclude that a user needs step-up or has completed step-up.** The step-up trigger should come from server-side business requirements, store state with a TTL, bind to the session/browser, and correlate with the AuthnRequest ID. After the callback, the resulting AuthnInstant/AuthnContext must be verified independently of request parameters.

A custom resolver can classify the route or read the intent from a trusted state source and then set the corresponding attributes before encoding/signing. When implementing dynamic policy, design an independent decision class for unit testing and a separate version-specific OpenSAML adapter. If state linkage between request and response cannot be guaranteed, deny rather than allow through.

## 10. RelayState and AuthenticationRequestRepository Are Not the Resolver

Two concepts with easily confused names:

| Component | Timing | Role |
| --- | --- | --- |
| `Saml2AuthenticationRequestResolver` | Before sending to the IdP | Builds the AuthnRequest and binding information |
| `Saml2AuthenticationRequestRepository` | When sending and when receiving the Response | Saves, loads, and removes the issued request for correlation and login CSRF/replay protection |

Spring Security by default typically uses **`HttpSessionSaml2AuthenticationRequestRepository`**. Because the HttpSession is bound to the browser, an attacker cannot simply take their own request ID and force a victim's browser to accept a response for a different session.

**`CacheSaml2AuthenticationRequestRepository`** can be used in supported versions to store requests in a distributed cache, for example in multi-instance architectures or applications needing a non-default session design. However, storing by `RelayState` or `InResponseTo` **without safely binding to the session/browsing context** can create login injection/fixation risks. You need a random nonce, short TTL, one-time retrieval, correlation, and deliberately designed session protections.

`RelayState` is a mechanism for carrying state back across the SAML binding; do not automatically trust it just because the IdP returned it. Do not allow `RelayState` to contain an arbitrary URL and redirect to it after login; prevent open redirects, limit size, and store mappings to validated internal URLs.

Replacing the request repository is **not** the same as replacing the AuthnRequest resolver. The two components can be configured separately, but they must agree on how IDs are issued, RelayState is handled, requests are stored, and Responses are verified.

## 11. Choosing Binding, Request Signing, and the Right Configuration Source

Sending an AuthnRequest via **HTTP-Redirect** or **HTTP-POST** and signing usually relate to **`RelyingPartyRegistration` / IdP metadata**, not necessarily requiring a customizer that modifies XML.

| Scenario | Primary Configuration Approach |
| --- | --- |
| IdP receives AuthnRequest at a different SSO URL | Update the registration's asserting-party metadata after verifying the source |
| IdP requires HTTP-POST | Configure `singleSignOnServiceBinding(Saml2MessageBinding.POST)` accordingly |
| IdP requires signed AuthnRequest | Provide SP signing private key/certificate, sign according to IdP policy |
| IdP does not require signed AuthnRequest | Adjust the `wantAuthnRequestsSigned` policy if genuinely appropriate |
| IdP requires a specific signing algorithm | Use metadata or `signingAlgorithms` per the API and allowed algorithm list |
| SP wants to modify `ForceAuthn` | OpenSAML authentication-request resolver customizer |
| SP needs to change the ACS callback | `assertionConsumerServiceLocation` + `loginProcessingUrl` + IdP registration |

**Do not modify the SAMLRequest after it has been signed**, and do not convert a Redirect-bound request to POST merely by changing the HTTP method. Each binding has its own encoding/signature rules; let the library handle them.

### Encoding and Generated Data

`AbstractSaml2AuthenticationRequest` holds the information prepared for the SAML binding. With Redirect binding, the payload typically undergoes DEFLATE and Base64; with POST binding, Base64 is used per the profile. URL encoding/form escaping must be done properly at the sending layer; do not Base64-encode `getSamlRequest()` a second time.

If you only need to inspect AuthnRequest fields when debugging, use a test harness or logs with **sensitive data masked** in test environments—do not write full SAMLRequest/XML into production logs. Do not manually “decode/edit/re-encode” as an official customization technique.

## 12. Extension Points That Should Not Be Misused

Certain requirements **are not the responsibility** of the AuthnRequest resolver:

- **Customizing ACS / Response handling:** use `Saml2WebSsoAuthenticationFilter`, `loginProcessingUrl`, `Saml2AuthenticationTokenConverter`, and the appropriate authentication provider.
- **Adding signature/clock skew/assertion checks:** use `OpenSamlXAuthenticationProvider` or an extension validator in the active branch.
- **Renaming the principal or mapping roles:** perform at the conversion/authorization layer after verifying the assertion.
- **Refreshing IdP metadata/certificates:** use a registration/metadata repository or a secure refresh mechanism.
- **OAuth 2.0 access tokens for APIs:** use OAuth2 Client/Resource Server; a SAML `AuthnRequest` does not issue OAuth tokens by itself.
- **Single Logout:** use dedicated SAML logout components; do not use the AuthnRequest resolver to build a LogoutRequest.

If the need is only to **change the login URL**, you do not need to write an entire custom XML factory. If the need is to change the **authentication assurance level**, modifying the AuthnRequest alone is not enough; you must verify the actual Response against policy.

## 13. Standalone Java 17 Example: Deciding When to Require ForceAuthn

To decouple **application policy** from **version-dependent OpenSAML code**, you can decide based on the server-side action and the previously verified authentication timestamp. The following Java 17 example runs standalone; it **does not verify SAML itself**, does not create tokens, and must not be used with `AuthnInstant` data from an untrusted source.

Create file `AuthnRequestPolicyDemo.java`:

~~~java
import java.time.Duration;
import java.time.Instant;

public class AuthnRequestPolicyDemo {

    static boolean needsFreshLogin(String action, Instant lastAuthn,
                                   Instant now) {
        if (!"APPROVE_PAYMENT".equals(action)) {
            return false;
        }
        if (lastAuthn == null || lastAuthn.isAfter(now)) {
            return true;
        }
        Duration age = Duration.between(lastAuthn, now);
        return age.compareTo(Duration.ofMinutes(10)) > 0;
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-07T10:00:00Z");
        Instant recent = Instant.parse("2026-11-07T09:55:00Z");
        Instant old = Instant.parse("2026-11-07T09:20:00Z");

        System.out.println(needsFreshLogin("VIEW_DASHBOARD", old, now));
        System.out.println(needsFreshLogin("APPROVE_PAYMENT", recent, now));
        System.out.println(needsFreshLogin("APPROVE_PAYMENT", old, now));
        System.out.println(needsFreshLogin("APPROVE_PAYMENT", null, now));
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac AuthnRequestPolicyDemo.java
java AuthnRequestPolicyDemo
~~~

**Exact** stdout:

~~~text
false
false
true
true
~~~

Explanation:

1. Viewing the dashboard does not require reauthentication under the demo policy.
2. Approving a payment when the most recent authentication was 5 minutes ago does not require a new login.
3. Approving a payment when the authentication was 40 minutes ago requires a new login.
4. Missing verified AuthnInstant information requires a new login.

**Security note:** the function above only makes a decision **before creating the AuthnRequest**; it does not prove the user satisfied MFA and does not replace assertion validation/authorization. The `action` input must come from a verified server operation, not arbitrarily from a query string. Production requires clock skew policy, session/intent TTL, context checking mechanisms, and post-callback step-up rules.

## 14. Layered Testing of the Resolver

### Unit Tests (No IdP Needed)

- On non-SSO initiation paths, the resolver returns null or is not selected by the filter.
- With a valid `registrationId`, it resolves a request bound to the matching registration.
- `ForceAuthn` and customizer fields apply the policy correctly.
- Disallowed routes/intents do not generate requests to arbitrary IdPs.
- State/RelayState or destination URLs are never written from unvalidated data.
- With multiple IdPs, the same `registrationId` always maps to the configured metadata and certificates.

### Integration Tests with a Test IdP

- Requests initiated at `/saml2/authenticate/corp` actually redirect the browser to the right SSO URL.
- Decode the SAMLRequest per the binding and verify `ForceAuthn`, `Issuer`, `Destination`, `NameIDPolicy`, and RequestedAuthnContext match configuration.
- Valid AuthnRequest signature if required by the IdP, using the registered SP certificate.
- SAMLResponse returns to the right ACS; `InResponseTo` and `RelayState` correlate per rules.
- IdP returns an error when unable to satisfy RequestedAuthnContext or IsPassive; the application rejects safely.
- When requesting step-up, the verified Response has a sufficiently fresh `AuthnInstant` and policy-compliant `AuthnContext` before sensitive operations.
- Test behind a reverse proxy: `{baseUrl}`, Issuer, and ACS use the correct public HTTPS host.

### Regression Tests When Upgrading Spring Security

1. Check the **exact dependency version** and switch `OpenSaml4...` ↔ `OpenSaml5...` where supported by the library.
2. Run compile/build and integration tests, and do not ignore deprecation warnings.
3. Compare AuthnRequest XML/binding in the same scenarios before and after the version upgrade.
4. Check the SSO endpoint matcher, ACS response handling, session/cache request storage, and signing keys.
5. Test multi-IdP logout/login, SSO session reuse, and policy-based step-up.

## 15. Common Errors and Troubleshooting Guide

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Cannot import `OpenSaml4AuthenticationRequestResolver` after upgrade | Class is absent in a branch that moved to OpenSAML 5 | Check version-specific Javadoc, migrate to OpenSaml5 API instead of mixing JARs |
| Cannot import `OpenSaml5AuthenticationRequestResolver` | Project is on a branch without that resolver or missing SAML provider | Align Spring Security BOM/modules, choose the version-appropriate class |
| `Saml2AuthenticationRequestResolver` ignores HTTP request | SSO initiation matcher/URL does not match | Check `authenticationRequestUriQuery` and the resolver's request matcher |
| AuthnRequest sent, but IdP reports unknown SP | Incompatible SP entityId or IdP registration | Compare SP/IdP metadata and entity IDs |
| IdP reports Request signature invalid | SP signing credential, binding, algorithm, or XML modified incorrectly | Configure signing properly; do not modify payload after signing |
| IdP returns `NoAuthnContext` | RequestedAuthnContext is not supported by the IdP | Agree on assurance classes, test mapping and policy |
| Enabling ForceAuthn causes constant re-login prompts | Customizer applied globally to all logins | Apply only under controlled step-up policy |
| Response reports `InResponseTo` mismatch | Request not saved, HttpSession/SameSite, or cache correlation error | Check `Saml2AuthenticationRequestRepository` and session binding |
| Response sent to the wrong URL | ACS or reverse proxy public URL misconfigured | Align `assertionConsumerServiceLocation`, IdP, and loginProcessingUrl |
| Multiple IdPs but routed to the wrong tenant | Wrong registrationId/issuer resolution | Bind registration to trusted request state |
| IdP does not support `IsPassive` when user has no session | Cannot authenticate silently | Handle `NoPassive`, do not allow through automatically |
| Login succeeds, but step-up action lacks sufficient assurance | Relied only on ForceAuthn without checking the response | Verify AuthnInstant/AuthnContext and business authorization |
| Replaced request repository with cache, causing login injection | Looking up request by RelayState without browser/session binding | Design one-time nonce, TTL, session binding, and safe correlation |

**Do not fix errors by** disabling SAML signature verification, bypassing `InResponseTo`/replay checks, accepting any IdP, or letting users pick arbitrary callback URLs.

## 16. Implementation Checklist

- [ ] Know the Spring Security version, OpenSAML version, and Servlet package in use; do not mix example classes across branches.
- [ ] `RelyingPartyRegistrationRepository` has complete registrations with valid IdP metadata/certificates/ACS/entityId.
- [ ] Choose `Saml2AuthenticationRequestResolver` according to needs and version: OpenSaml4 or OpenSaml5.
- [ ] Customize XML via `setAuthnRequestCustomizer` before the library signs/encodes; do not manually assemble signed XML.
- [ ] Verify `ForceAuthn`, `IsPassive`, RequestedAuthnContext, and `NameIDPolicy` only when supported by the IdP.
- [ ] Use `authenticationRequestUriQuery` for its intended purpose of changing the login initiation path, not confusing it with ACS.
- [ ] Route `registrationId` safely; avoid client-controlled IdP URLs or RelayState.
- [ ] Maintain request correlation via `Saml2AuthenticationRequestRepository`, verifying `InResponseTo`/RelayState and replay.
- [ ] Configure Redirect/POST binding, SP signing credential, and signing algorithm matching IdP metadata.
- [ ] For step-up, verify the signed Response, AuthnInstant/Context, and authorization before sensitive operations.
- [ ] Test login behind a reverse proxy, with multiple IdPs, SSO sessions, and failure cases.
- [ ] When upgrading Spring Security, run compilation and end-to-end tests for all extension points.

## 17. Conclusion

**`Saml2AuthenticationRequestResolver` is the extension point for creating a SAML2 AuthnRequest from an HTTP request in Spring Security.** It links HTTP initiation with a trusted `RelyingPartyRegistration` and prepares the AuthnRequest for the filter to send over the configured SAML binding. **`Saml2AuthenticationRequestRepository` is a separate component**, used to store issued requests for correlation when the SAML Response returns.

When you need to change `ForceAuthn`, RequestedAuthnContext, or SAML attributes, prefer the customizer of the **version-appropriate `OpenSaml4AuthenticationRequestResolver` or `OpenSaml5AuthenticationRequestResolver`**. When only changing the URL or binding, use the corresponding DSL and registration. When requiring stronger/fresh authentication, **do not stop at sending the AuthnRequest**: verify the response and application policy. Separating protocol, state, metadata, and authorization keeps a federation system secure and maintainable across Spring Security version changes.

### Official Documentation

- Spring Security 7.0 — Producing AuthnRequests: https://docs.spring.io/spring-security/reference/7.0/servlet/saml2/login/authentication-requests.html
- Spring Security 6.5 — Producing AuthnRequests: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/authentication-requests.html
- Spring Security — SAML 2.0 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security — Authenticating SAML Responses: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Javadoc — Saml2AuthenticationRequestResolver: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/authentication/Saml2AuthenticationRequestResolver.html
- Javadoc — Saml2LoginConfigurer: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/configurers/saml2/Saml2LoginConfigurer.html
- Javadoc (Spring Security 6.0) — OpenSaml4AuthenticationRequestResolver: https://docs.spring.io/spring-security/site/docs/6.0.x/api/org/springframework/security/saml2/provider/service/web/authentication/OpenSaml4AuthenticationRequestResolver.html
- OASIS SAML 2.0 Core (AuthnRequest): https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
