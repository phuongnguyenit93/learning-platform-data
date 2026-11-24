# ForceAuthn, IsPassive, and IdP-Enforced Assurance Boundaries

## 1. Problem and Objectives

In the SAML 2.0 Web Browser SSO flow, a Spring Security application acts as the **Service Provider (SP, Relying Party)**. The SP builds an `AuthnRequest` message and sends the browser to the **Identity Provider (IdP, Asserting Party)**. The IdP decides how to authenticate the user, either reusing an existing SSO session or requiring a fresh verification step. Two attributes of `AuthnRequest` directly influence that decision:

- **`ForceAuthn`**: the SP asks the IdP to authenticate the user directly, rather than relying solely on a **previous security context**.
- **`IsPassive`**: the SP asks the IdP and user agent **not to visibly take control of the UI to interact with the user noticeably**.

They appear contradictory, yet enabling both is not always impossible: an IdP with a way to authenticate directly **without visible UI interaction** can satisfy both simultaneously, depending on policy and capability. Conversely, when `IsPassive` cannot be satisfied, the IdP must fail appropriately rather than displaying a login form during a passive transaction.

This lesson belongs to **Spring Security - federation → AuthnRequest Customization**. After this lesson, you will be able to:

1. Read the exact meaning of both flags per **SAML 2.0 Core**, distinguishing an omitted value from `false`.
2. Understand the combination matrix of the two flags, reauthentication scenarios, silent SSO, step-up, and the `NoPassive` error code.
3. Customize `AuthnRequest` in Spring Security Servlet using `OpenSaml4AuthenticationRequestResolver` or `OpenSaml5AuthenticationRequestResolver` depending on version.
4. Distinguish the **SP's intent**, **the specification's obligation on compliant IdPs**, and **actual verifiable IdP behavior**.
5. Design strong authentication requirements without confusing `ForceAuthn` with MFA, guaranteed freshness, or application authorization.
6. Test cases where the outgoing request XML is valid yet the IdP ignores it, returns an error, the browser session expires, or no request is generated.
7. Preserve SAML signature, issuer, audience, destination, time, and `InResponseTo` correlation checks.

Spring example scope: **Java 17+, Spring Boot 3.x, Spring Security 6.x on Servlet/MVC**, with Spring Security 7.x differences covered separately. Sample URLs and metadata are hypothetical and cannot log into a non-existent IdP.

## 2. Reading AuthnRequest Attributes Correctly

In XML, the two attributes sit **directly on the protocol element** `<samlp:AuthnRequest>`, not inside `RelayState` or a `RequestedAuthnContext` element:

~~~xml
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    ID="_request-demo-001"
    Version="2.0"
    IssueInstant="2026-11-07T00:00:00Z"
    Destination="https://idp.example.org/saml/sso"
    AssertionConsumerServiceURL="https://app.example.org/login/saml2/sso/corp"
    ForceAuthn="true"
    IsPassive="false">
  <saml:Issuer
      xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
      >https://app.example.org/saml/metadata</saml:Issuer>
</samlp:AuthnRequest>
~~~

**This XML illustrates structure only**, not a valid production request: ID, IssueInstant, Destination, issuer, ACS, signature, and metadata must be generated, matched, and protected by a real implementation.

Key syntax:

| Element | Definition | Do Not Confuse With |
| --- | --- | --- |
| `ForceAuthn="true"` | Boolean flag requesting direct fresh authentication per SAML | MFA policy, OTP requirement, or specific password rule |
| `IsPassive="true"` | Boolean flag prohibiting noticeable UI interaction during request processing | Guarantee that the browser performs no redirects or network requests |
| `ForceAuthn` omitted | Per spec, **defaults to false** | “IdP must reuse old session” |
| `IsPassive` omitted | Per spec, **defaults to false** | “IdP must display a login form” |
| `RequestedAuthnContext` | Policy constraint on authentication context/method | The ForceAuthn flag |
| `AuthnStatement@AuthnInstant` | Timestamp of the authentication event asserted by the IdP | Absolute proof that ForceAuthn was executed properly |
| `Response@InResponseTo` | Correlates response to the issued request | A field answering “ForceAuthn was performed” |

SAML Core section **3.4.1 Authentication Request** states: if `ForceAuthn=true`, the IdP **MUST** authenticate the presenter directly rather than rely on a previous security context. If `IsPassive=true`, the IdP and user agent **MUST NOT** visibly take control of the UI to interact noticeably with the presenter. When omitted, both flags default to **false**. That is the **normative protocol meaning**; actual enforcement by a specific IdP product must be verified via documentation and testing.

## 3. ForceAuthn: Requests Reauthentication, Not MFA by Default

An application has sensitive operations such as viewing legal records, changing payout account numbers, or approving transactions. The user previously logged into the IdP; the application wants the IdP to **directly re-authenticate** rather than rely solely on an existing SSO session. That is the use case for `ForceAuthn=true`.

### What ForceAuthn Means

- The SP issues a **new AuthnRequest** with `ForceAuthn="true"`.
- A SAML-compliant IdP handles the request to authenticate the user directly **without merely inferring from a previous security context**.
- The IdP may prompt for a password, passkey, certificate, interactive verification step, or another mechanism per its policy.
- If the IdP cannot satisfy the requirement, it may return a protocol error status; the SP must have a safe failure path.
- A successful authentication event can produce an `AuthnStatement` and `AuthnContext` in the assertion; the SP must verify them against business requirements.

### What ForceAuthn **Does Not Automatically Guarantee**

- It does not mean **re-entering a password**. SAML does not mandate a specific method for this attribute.
- It does not mean **enforcing MFA**. MFA/assurance requires IdP policy and typically appropriate `RequestedAuthnContext`, trust/contract, or claims/assertions.
- It does not define a **maximum authentication age** in seconds. Authentication timing must be evaluated separately via `AuthnInstant` and policy; do not conflate with OIDC's `max_age` parameter.
- It does not mean the browser will always see a login form. How an IdP authenticates directly varies across platforms.
- It does not invalidate or wipe the entire existing SSO session at the IdP, nor force logout from other applications.
- It does not make SP signature verification of the Response/Assertion “stronger”; protecting message authenticity remains a separate step.
- It does not guarantee desired phishing resistance or impersonation defense if IdP policy, authentication method, and user device fall short.

**Crucial distinction:** the spec places a **MUST** obligation on compliant IdPs, yet **the SP cannot deduce the IdP enforced it properly just because the flag appeared in XML**. For critical actions, testing/configuration/IdP audits and assertion/policy evidence are required to assess real assurance.

## 4. IsPassive: Requesting Authentication Without UI Interaction

With `IsPassive=true`, the SP asks that processing **not cause the IdP or user agent to take over the requester's UI to communicate noticeably with the user**. This can fit a workflow probing whether the user already meets authentication conditions.

For example: an application opens an SSO check window/flow and wants to see whether the IdP can recognize the user in the current context **without showing an interactive login form**. If yes, the IdP returns a valid response; if not, the IdP rejects with a status such as `NoPassive`.

### Distinctions to Make

- **Passive does not mean the IdP performs zero authentication.** The IdP may use a prior security context when `ForceAuthn=false`, or a mechanism satisfying passive constraints to freshly authenticate if required.
- **Passive does not mean the browser makes no redirects.** Front-channel SAML can still pass through the browser. What the spec restricts is noticeable UI interaction.
- **Passive is not “login bypass”.** The SP still needs a validly signed response with matching issuer/audience/recipient/time, and the user remains unauthenticated if the IdP returns an error.
- **Passive is not guaranteed to work inside an iframe.** Third-party cookies, tracking prevention, Content Security Policy, SameSite, and browser policies can prevent the IdP from seeing a session in an embedded context.
- **Passive is not inherently equivalent to a refresh token or background API call.** It remains Web Browser SSO using an AuthnRequest.
- An IdP may **not support or may restrict IsPassive**. If passive authentication is unavailable under the contract, the SP must have a policy fallback rather than silently switching to interactive without notice/permission.

### The NoPassive Status

SAML Core defines the status URI:

~~~text
urn:oasis:names:tc:SAML:2.0:status:NoPassive
~~~

It indicates the IdP **could not authenticate the user passively as requested**. In many profiles, it appears as a subordinate status under `Responder`; actual implementations must inspect the full response/status. It **does not mean**:
- Wrong username/password;
- The IdP is under attack;
- The SP should treat the user as anonymously logged in;
- The SP may strip passive mode and perform interactive auth by automatically reusing the old request.

Safe UX direction: notify that silent login is unavailable and let the user actively choose **interactive login** if policy allows; initiate a **new SAML transaction** without `IsPassive=true`. Never “bend” an error Response into a successful Response.

## 5. Four ForceAuthn/IsPassive Combinations and Expected Outcomes

| ForceAuthn | IsPassive | SP Intent | Expected Behavior from a Compliant IdP |
| --- | --- | --- | --- |
| **false** | **false** | Standard SSO login | May reuse existing security context or interact per policy |
| **true** | **false** | Request fresh direct authentication | Do not rely solely on prior security context; may display authentication interaction |
| **false** | **true** | Attempt authentication without noticeable UI | May use existing conditions/session if suitable; otherwise return error like `NoPassive` |
| **true** | **true** | Want direct authentication **and** no noticeable UI | Succeeds only if IdP can **freshly authenticate** while still obeying IsPassive; otherwise must not perform fresh auth by violating passive constraint |

The `true/true` case **is not always invalid XML**. SAML Core explicitly specifies: when both flags are true, the IdP **MUST NOT freshly authenticate** unless it can satisfy the IsPassive constraint. In a product that only supports reauthentication via an interactive form, this combination will fail and should lead to an error; in a product with a non-interactive direct mechanism, valid cases may exist.

### Scenario-Based Examples

1. **Opening a normal dashboard when the user already has an IdP session:** `false,false` usually suffices; the IdP can reuse SSO.
2. **Approving a sensitive action:** consider `true,false` if fresh auth is genuinely needed; simultaneously configure assurance/MFA per IdP contract.
3. **Checking “is non-interactive SSO available?”:** `false,true`; if `NoPassive`, let the user choose interactive login via UX.
4. **Requiring fresh authentication with strictly zero UI:** `true,true` fits only if the IdP has a verified silent fresh-authentication mechanism; it should not be a default choice.

## 6. Where Do They Live in the HTTP/SAML Flow?

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant SP as Spring Security SP
    participant IDP as SAML IdP
    B->>SP: GET /saml2/authenticate/corp
    SP->>SP: Create AuthnRequest: ForceAuthn/IsPassive
    SP-->>B: 302 to IdP SSO with SAMLRequest
    B->>IDP: GET SSO endpoint
    alt Flags and policy can be satisfied
        IDP-->>B: Successful SAMLResponse via form POST
        B->>SP: POST SAMLResponse to ACS
        SP->>SP: Verify signature, issuer, audience, time, InResponseTo
        SP-->>B: Create SP session and redirect to resource
    else Cannot satisfy passive/policy
        IDP-->>B: Error SAML Response, e.g. NoPassive
        B->>SP: POST to ACS if IdP uses Web SSO POST
        SP->>SP: Handle failure; do not create authenticated principal
        SP-->>B: Error page or new interactive login option
    end
~~~

In **HTTP-Redirect** binding, SAML XML is typically raw DEFLATEd, Base64-encoded, and URL-encoded under the `SAMLRequest` parameter. The flags reside **inside the XML** once decoded, not as `&ForceAuthn=true` or `&IsPassive=true` in the URL query under the standard mechanism. In **HTTP-POST AuthnRequest** binding, the browser POSTs a `SAMLRequest` form field containing Base64 XML; the flags remain XML attributes.

To debug, locate the `SAMLRequest`, decode it **safely in a test environment** or via dedicated diagnostic logging/tools, and inspect whether the XML contains both attributes. Do not edit the query after the request is signed and assume the signature remains valid.

Note on separation: **the SP generates the request, the browser transports it, and the IdP decides authentication**. A successful response does not itself prove how the IdP authenticated unless corresponding fields and policies provide trusted evidence.

## 7. Where Does Spring Security Process AuthnRequest?

In `spring-security-saml2-service-provider` on the Servlet stack:

- `Saml2WebSsoAuthenticationRequestFilter` handles SSO initiation, defaulting to `/saml2/authenticate/{registrationId}` or framework-supported query variants.
- `Saml2AuthenticationRequestResolver` decides how to build the AuthnRequest from `HttpServletRequest` and the registration. An OpenSAML implementation supports a customizer on the `AuthnRequest` object before the message is serialized/sent.
- `RelyingPartyRegistrationRepository` holds IdP/ACS/entityId/certificate configuration for each registration.
- `Saml2AuthenticationRequestRepository` stores issued requests to correlate responses. Default on Servlet is typically `HttpSessionSaml2AuthenticationRequestRepository`.
- `Saml2WebSsoAuthenticationFilter` processes SAMLResponse at the ACS, typically `POST /login/saml2/sso/{registrationId}`, authenticating via the provider.
- The IdP enforces or declines ForceAuthn/IsPassive according to its capabilities and policy; Spring Security SP **cannot control screens, cookies, MFA engines, or session policies inside the IdP**.

By default, Spring Security sets `ForceAuthn=false` in official examples. To adjust it, use the **`setAuthnRequestCustomizer`** extension point rather than writing a controller that builds XML strings or mutating `SAMLRequest` after framework signing.

## 8. Static Customization on Spring Security 6.x

With **Spring Security 6.x featuring `OpenSaml4AuthenticationRequestResolver`** and compatible OpenSAML 4, register a request resolver bean recognized by Spring Security.

File `src/main/java/com/example/federation/SamlAuthnRequestConfig.java`:

~~~java
package com.example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.web.DefaultRelyingPartyRegistrationResolver;
import org.springframework.security.saml2.provider.service.web.RelyingPartyRegistrationResolver;
import org.springframework.security.saml2.provider.service.web.authentication.OpenSaml4AuthenticationRequestResolver;
import org.springframework.security.saml2.provider.service.web.authentication.Saml2AuthenticationRequestResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlAuthnRequestConfig {

    @Bean
    Saml2AuthenticationRequestResolver authenticationRequestResolver(
            RelyingPartyRegistrationRepository registrations) {

        RelyingPartyRegistrationResolver resolver =
                new DefaultRelyingPartyRegistrationResolver(registrations);

        OpenSaml4AuthenticationRequestResolver samlResolver =
                new OpenSaml4AuthenticationRequestResolver(resolver);

        samlResolver.setAuthnRequestCustomizer(context -> {
            context.getAuthnRequest().setForceAuthn(Boolean.TRUE);
            context.getAuthnRequest().setIsPassive(Boolean.FALSE);
        });

        return samlResolver;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/**", "/error").permitAll()
                        .anyRequest().authenticated())
                .saml2Login(Customizer.withDefaults())
                .build();
    }
}
~~~

**Run conditions:** this is a Spring configuration class inside a Boot Servlet project that already has `@SpringBootApplication`, suitable SAML Service Provider/OpenSAML dependencies, and valid IdP registrations. It is **not a standalone Java main** to run via `javac SamlAuthnRequestConfig.java` with a bare JDK. There is no fixed stdout; what to observe is **actual AuthnRequest XML having `ForceAuthn="true"`** and IdP behavior.

Key points:
1. Spring Security picks up the custom `Saml2AuthenticationRequestResolver` bean from the context per version-supported mechanisms.
2. `DefaultRelyingPartyRegistrationResolver` looks up the registration by request/path.
3. `setAuthnRequestCustomizer` modifies the OpenSAML object **before serialization/signing**.
4. The configuration above sets **ForceAuthn=true for every AuthnRequest initiated through this resolver**; that is an aggressive policy that can make everyday logins inconvenient. Use deliberately.
5. `setIsPassive(false)` is included to illustrate both attributes. Since the spec default is already false, you can set only ForceAuthn if unneeded.

### Import and Version Notes

- Spring Security 6.x based on OpenSAML 4 has `OpenSaml4AuthenticationRequestResolver`. Some 6.x releases optionally support OpenSAML 5; if you moved stacks, use the resolver 5 class and matching dependency guide.
- In Spring Security 7.x, current guides use **`OpenSaml5AuthenticationRequestResolver`**. Update **both the class name and imports** after upgrading; do not change only the class name if dependencies remain OpenSAML 4.
- Keep Spring Security/OpenSAML versions aligned with the BOM/compatibility matrix. Names like `OpenSamlXAuthenticationProvider` in documentation are generic placeholders, not importable class names.
- If a project already defines a request resolver bean for another partner, integrate logic into that existing bean; do not silently create two competing beans.

## 9. OpenSAML 5 / Spring Security 7.x Version

The idea is identical; the resolver 5 class provides the corresponding customizer API:

~~~java
package com.example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.web.DefaultRelyingPartyRegistrationResolver;
import org.springframework.security.saml2.provider.service.web.RelyingPartyRegistrationResolver;
import org.springframework.security.saml2.provider.service.web.authentication.OpenSaml5AuthenticationRequestResolver;
import org.springframework.security.saml2.provider.service.web.authentication.Saml2AuthenticationRequestResolver;

@Configuration
public class SamlAuthnRequestResolverConfig {

    @Bean
    Saml2AuthenticationRequestResolver authenticationRequestResolver(
            RelyingPartyRegistrationRepository registrations) {

        RelyingPartyRegistrationResolver registrationResolver =
                new DefaultRelyingPartyRegistrationResolver(registrations);

        OpenSaml5AuthenticationRequestResolver resolver =
                new OpenSaml5AuthenticationRequestResolver(registrationResolver);

        resolver.setAuthnRequestCustomizer(context -> {
            context.getAuthnRequest().setForceAuthn(true);
            context.getAuthnRequest().setIsPassive(false);
        });
        return resolver;
    }
}
~~~

This example is an **alternative option** to the OpenSAML 4 example; do not define both beans in the same app. To handle login, the project still needs `.saml2Login(...)`, IdP registrations, and a filter chain in its security layer. Official Spring Security 7.0/7.1 docs illustrate the `setForceAuthn(true)` customizer on the OpenSAML 5 resolver.

If the project is still on 6.x, verify the **active version** before picking APIs; do not apply 7.x classes just from reading a newer doc URL.

## 10. Trying Passive Mode with the Request Resolver

When the goal is **attempting silent login**, change the customizer to:

~~~java
resolver.setAuthnRequestCustomizer(context -> {
    context.getAuthnRequest().setForceAuthn(false);
    context.getAuthnRequest().setIsPassive(true);
});
~~~

This is a **code snippet** placed on the active resolver object (`OpenSaml4...` or `OpenSaml5...`) inside the same bean; **not a standalone Java program**. This tells the IdP: if you can authenticate the user without noticeable UI interaction, do so; otherwise respond with an error per profile. It does not guarantee silent browser behavior across all cookie policies.

### Why Not Enable Passive for All Logins?

- New users without an eligible IdP session will typically be unable to log in if the IdP requires an interactive form.
- The system can fall into a “silent check → NoPassive → silent check” loop if the failure handler simply retries the same request.
- Browsers blocking third-party cookies can prevent the IdP from seeing its session inside an iframe; `IsPassive=true` cannot override browser policy.
- If the SP already has an authenticated session and the user visits a public route, **the filter chain may not emit a new AuthnRequest**, so the customizer never runs. To test the flag, actively start an eligible SAML login flow.
- Silent authentication from the IdP does not guarantee the user meets the assurance level needed for sensitive actions.

Applications commonly use a two-phase strategy: try passive in a **controlled probing flow**, and upon receiving `NoPassive`, show an invitation for the user to initiate **a new non-passive request**. Fallback handling must inspect real error responses and avoid infinite loops.

## 11. Scenario-Based Policy: Avoid Enabling ForceAuthn App-Wide

In real products, distinguish between:

- **Default login:** user enters the dashboard, signing in again via a valid IdP session.
- **Reauthentication:** user needs to re-confirm identity before a sensitive operation; the app proactively opens a new flow with ForceAuthn true.
- **Passive probing:** a screen wants to check silent SSO; the app opens a separate IsPassive true flow.
- **Step-up MFA:** requirements for stronger authentication methods handled by the IdP; never guaranteed by ForceAuthn alone.

A clear policy table:

| Business Scenario | Expected Flags | Additional Requirements |
| --- | --- | --- |
| Accessing normal learning/portal pages | false / false | Normal session, authorization |
| Changing payout details | true / false | IdP policy, assurance/MFA if needed, verify fresh event |
| Checking non-interactive SSO | false / true | Handle NoPassive error safely, fallback |
| Requiring fresh authentication without UI | true / true, only if tested with IdP | Satisfy both conditions simultaneously; otherwise must fail |
| User requires mandatory MFA | No single flag pair guarantees this | RequestedAuthnContext / IdP policy / assertion validation |

### Do Not Take Flags Directly from Browser-Sent Queries

Unsafe example:

~~~text
GET /saml2/authenticate/corp?forceAuthn=false
~~~

If the server turns this query into `ForceAuthn=false` even during a mandatory reauthentication flow, a user/attacker can downgrade the security requirement. Conversely, if a user sets `isPassive=true` on a flow that must display MFA, the experience can fail. **Policy decisions must reside on the server** and bind to the action/trusted request source/state.

Viable design:

1. When the user starts an operation needing step-up, the server creates an **authentication transaction with a TTL and session binding**.
2. The server stores the reason/destination/required assurance and issues a short opaque handle.
3. Only the server resolves that handle into ForceAuthn/IsPassive policy inside the customizer.
4. After the response, look up that exact transaction and verify the actual outcome before permitting the action.
5. A consumed transaction cannot be replayed; on failure, present recovery options without allowing the sensitive action.

This is an **architectural pattern**, not full out-of-the-box Spring Security default behavior. For apps without dynamic policies, the static customizer in sections 8/10 suffices.

## 12. If the SP Already Has a Session, Is ForceAuthn Sent?

A very common misconception: “Setting ForceAuthn in config means every time a user visits `/transfer`, the IdP prompts them to log in again.”

In reality, ForceAuthn appears only in a **new AuthnRequest**. If the user already holds a valid `SecurityContext` at the SP and controller/authorization permits the request, Spring Security does not necessarily trigger SAML login. Hence:

- The ForceAuthn flag in the resolver **takes effect only when the resolver actually builds an AuthnRequest**.
- A sensitive endpoint cannot treat static flag config as sufficient for step-up.
- The application must track security level/authentication age per policy and **proactively initiate a new SAML transaction** when stronger authentication is needed.
- The SP must avoid infinite loops: after a successful response, mark server-side that step-up just completed **based on verified evidence**, valid only within the policy's time/scope window.
- Never treat “returned to the success URL” as fresh authentication; the assertion/assurance verification step is what must be evaluated.

Direct access to **`/saml2/authenticate/corp`** typically initiates the flow for that registration; however, check that your application's filter chain/routes/security matchers permit the SAML start request. Do not build a new GET controller solely to emit a URL with ForceAuthn.

## 13. ForceAuthn Differs from RequestedAuthnContext and AuthnInstant

These three serve distinct requirements:

| Business Requirement | Related SAML Construct | What Can Be Verified |
| --- | --- | --- |
| Do not rely solely on prior IdP security context | `AuthnRequest@ForceAuthn` | Request actually carries flag; IdP enforces per policy |
| Specific authentication method/level | `<RequestedAuthnContext>` (ClassRef/DeclRef, comparison) | Assertion `AuthnContext` reflects matching context if emitted by IdP and checked by SP |
| Authentication is not too old | `AuthnStatement@AuthnInstant` and SP policy | Timestamp in verified assertion compared against server clock / allowed window |
| Authentication without displaying UI | `AuthnRequest@IsPassive` | Observe IdP behavior and NoPassive status when impossible |
| Who may access a feature | Application authorization post-login | Roles/permissions per policy, never inferred from ForceAuthn |

For example, wanting **MFA for approval**: setting ForceAuthn=true can ask for fresh authentication, yet you still need the IdP to support MFA with the matching context and the SP **not to grant access if the assertion lacks the expected assurance evidence**. An IdP might re-authenticate with a single factor; thus ForceAuthn was satisfied while the product's MFA goal was not met.

Conversely, `RequestedAuthnContext` does not prove the user authenticated just now. You may need context requirements, freshness, and IdP policy alignment together.

**Do not treat `AuthnInstant` as standalone signed proof.** It is trustworthy only within an assertion fully verified by the SP (issuer, signature, conditions, subject confirmation, audience, replay).

## 14. When Both Flags Are True: Special Rule in the Specification

SAML Core has a specific rule for:

~~~xml
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    ID="_demo-combined"
    Version="2.0"
    IssueInstant="2026-11-07T00:00:00Z"
    ForceAuthn="true"
    IsPassive="true"/>
~~~

This illustrates **two attributes**, not a complete SSO request; do not send it in place of valid metadata/issuer/signature.

Per the specification:

1. ForceAuthn requests direct authentication rather than relying solely on an old security context.
2. IsPassive prohibits noticeable UI interaction.
3. If both are true, the IdP **must not perform fresh authentication** when it cannot satisfy the IsPassive constraint.
4. If both cannot be satisfied, it must fail per protocol/policy. Do not treat this as a pure XML syntax error.
5. If the IdP truly has a direct authentication mechanism without UI interaction and handles it per spec, the flow can succeed.

**Do not infer:** ForceAuthn true + IsPassive true = “prioritize ForceAuthn and show a popup”; that violates the IsPassive constraint. Likewise, do not conclude “both flags together are always invalid”; the spec states a condition rather than banning the combination outright.

## 15. How the IdP Enforces It and Assurance Limits on the SP

This is the core of the topic. Even after the SP sends a request with the right flags, many variables lie outside its control:

| IdP / System Variable | What the SP Cannot Control Directly | What the SP Can Do |
| --- | --- | --- |
| IdP implementation quality | Whether the IdP honors ForceAuthn/IsPassive across each binding | Check vendor docs, contract, integration tests, and audits |
| IdP session | Cookies, lifetime, session policy, primary login mechanisms | Test expectations with and without an existing IdP session |
| Reauthentication mechanism | Password, passkey, certificate, MFA, device token, proxy | Require assurance policy/level and verify matching evidence |
| Browser / third-party cookies | Cookie isolation, iframes, tracking prevention, SameSite | Test in real browsers and top-level redirects |
| Path through an IdP proxy | Whether it truly authenticates directly or relies on upstream IdP | Agree on how the IdP handles proxying/force auth and audit it |
| Response fidelity | Whether the IdP returns accurate AuthnContext/AuthnInstant | Trust only data inside verified assertions and policy |
| Failure status | Whether the IdP returns `NoPassive`, `AuthnFailed`, or vendor error | Classify errors, create no Authentication, provide safe fallback UX |
| AuthnRequest signature | Whether the IdP verifies request signature when required by policy | Configure SP signing credentials, align with IdP metadata, check test logs |

**Operational conclusion:** from the SP's perspective, setting `ForceAuthn=true` is **a protocol request**, not a button that directly forces the IdP to open MFA. Under the spec, a compliant IdP handles the corresponding obligation, yet the SP should rely on **IdP contract + testing + assertion evidence + local policy** to decide whether entry into a sensitive feature is warranted.

With independently configurable IdPs, policies may always enforce MFA for certain apps, disallow silent auth, enforce session-level “prompt login,” or ignore certain flags. Do not assume specific product behaviors without verifying the vendor's API/version.

## 16. Cases Where the IdP Ignores ForceAuthn

Suppose the SP sends:

~~~xml
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    ID="_request-stepup"
    Version="2.0"
    IssueInstant="2026-11-07T00:00:00Z"
    ForceAuthn="true"/>
~~~

Yet the IdP returns a successful SAMLResponse without prompting for any fresh authentication, relying only on an old session. This may be an IdP implementation/policy gap, or a mismatch in how “fresh authentication” is interpreted. The SP must handle this in two layers:

**Protocol layer:** check Response/Assertion signatures, issuer, audience, destination, recipient, validity window, `InResponseTo`, and replay protection. If invalid, reject authentication.

**Business assurance layer:** if the feature mandates strong reauthentication/MFA/freshness, check the verified assertion against requirements (e.g., `AuthnInstant`, `AuthnContext`, assurance fields per IdP contract). If evidence is missing or policy is unmet, **do not perform the sensitive action**; provide a suitable path such as an error notice or initiating a policy-compliant flow.

Do not “work around” this by:
- Skipping assertion checks to “get a success result.”
- Measuring only the `/saml2/authenticate` redirect timestamp and treating it as authentication time.
- Accepting a browser-sent `force=true` query parameter as proof.
- Inferring “IdP returned success, so ForceAuthn must have been enforced” without verification evidence.

## 17. Protecting AuthnRequest and Avoiding Flag Tampering After Signing

Flags live inside the AuthnRequest; the request is observable via the browser. More dangerously, it can be **tampered with** across the front-channel:

- With SAML **HTTP-Redirect binding**, the message is usually XML → raw DEFLATE → Base64 → URL-encoded. For signed requests, the binding signature validates the encoded parameters per spec.
- With **HTTP-POST AuthnRequest**, signatures when present are usually XML Signatures inside the message before Base64/form submission.
- An attacker could try changing `ForceAuthn=true` to false to downgrade security requirements; if the IdP does not verify request signatures per policy, a browser-carried flag cannot be trusted across a strict trust boundary.
- AuthnRequest signing configuration, SP signing certificate, and IdP trust must match; never disable signature verification as a quick fix for integration errors.

**Important:** whether Spring Security signs the request depends on IdP/relying party configuration. If the IdP **does not require signature verification**, the SP cannot rely solely on “the request was generated on the backend” to prove flags were not altered in transit.

For example, IdP metadata may include `WantAuthnRequestsSigned`; the application must heed this and supply SP signing credentials when required. SAML Response/Assertion still has its own signing/verification step; a signed request never replaces response verification.

## 18. How Must Success or Error Responses Be Handled?

**On a successful response:**
1. Spring Security receives `SAMLResponse` at the ACS.
2. Validate session/registration and the issued request per correlation policy; never accept an attacker's unsolicited response as a request created by this browser.
3. Verify signature, issuer, audience, destination/recipient, validity window, and subject confirmation.
4. Extract authentication context/instant data when required by assurance policy.
5. Create Authentication only after protocol checks pass; sensitive route authorization still requires strong policy.

**On passive failure (`NoPassive`):**
1. Do not treat it as user authentication.
2. Read the error code/status safely after processing; never log raw assertions.
3. Display an option to continue with **interactive login** if the product permits.
4. If retrying, initiate a **new** AuthnRequest with `IsPassive=false` and fresh correlation/RelayState.
5. Limit retries and avoid infinite 302 loops.

**If the IdP returns success despite no visible UI interaction:** do not rush to conclude the IdP ignored ForceAuthn. A silent direct authentication mechanism may exist. Inspect the assertion, IdP audit logs, policy, and real evidence before concluding.

## 19. When Does “Step-Up” Need More Than ForceAuthn?

**Step-up authentication** is the process of reaching a higher assurance level for a specific action or context, such as moving from single-factor to phishing-resistant MFA or device binding. It **is not identical** to the “reauthentication” addressed by ForceAuthn:

| Goal | ForceAuthn | What Else Is Needed |
| --- | --- | --- |
| Force IdP to re-authenticate directly | Can be used | IdP support, request integrity, result verification |
| Mandatory MFA | Insufficient alone | IdP MFA policy, matching assertion/authn context, audit |
| Authentication within the last 5 minutes | Insufficient alone | AuthnInstant/timestamp check and policy |
| Phishing-resistant method | Insufficient alone | AuthnContext/IdP assurance contract, verified evidence |
| Non-interactive authentication | Not the right flag alone | IsPassive true and handling NoPassive |
| Allow user to approve a transaction | Does not authorize by itself | Transaction authorization, CSRF, permissions, anti-replay, audit |
| Force all applications to log out together | No | Dedicated SAML SLO/IdP session policy |

When designing strong authentication, explicitly define:
- How many minutes of **freshness** are required?
- Are one or multiple factors required, and which types?
- Does the IdP provide a verifiable authentication context?
- When evidence is missing, does the SP block the action or allow a fallback?
- Does the IdP have bypass mechanisms for internal devices or recovery, and does that policy meet requirements?
- Do the browser and SP session allow the user to safely re-initiate an AuthnRequest?

## 20. Standalone Java 17: Decision Table Simulation Without Spoofing an IdP

The program below **runs on JDK 17 without Spring**. It illustrates flag combinations logically and identifies cases where an IdP can or cannot authenticate directly while remaining passive.

**It is not a SAML processor.** The model is a simplified educational simulation **without** XML signatures, sessions, browsers, or real IdP assurance guarantees.

File `AuthnFlagDecisionDemo.java`:

~~~java
public final class AuthnFlagDecisionDemo {

    static String describe(
            boolean forceAuthn,
            boolean isPassive,
            boolean hasPreviousSession,
            boolean canFreshlyAuthenticatePassively) {

        if (forceAuthn && isPassive) {
            return canFreshlyAuthenticatePassively
                    ? "Fresh and passive can both be satisfied"
                    : "NoPassive: fresh silent auth is unavailable";
        }

        if (forceAuthn) {
            return "Fresh direct authentication requested";
        }

        if (isPassive) {
            return hasPreviousSession
                    ? "Passive may use existing IdP session"
                    : "NoPassive: interactive login is forbidden";
        }

        return hasPreviousSession
                ? "Normal SSO: IdP may reuse session"
                : "Normal SSO: interaction may be required";
    }

    public static void main(String[] args) {
        System.out.println(describe(false, false, true, false));
        System.out.println(describe(true, false, true, false));
        System.out.println(describe(false, true, false, false));
        System.out.println(describe(true, true, true, false));
        System.out.println(describe(true, true, true, true));
    }
}
~~~

Compile/run:

~~~bash
javac AuthnFlagDecisionDemo.java
java AuthnFlagDecisionDemo
~~~

**Exact** stdout:

~~~text
Normal SSO: IdP may reuse session
Fresh direct authentication requested
NoPassive: interactive login is forbidden
NoPassive: fresh silent auth is unavailable
Fresh and passive can both be satisfied
~~~

**Explanation:**
- `hasPreviousSession` is only a variable simulating IdP state.
- `canFreshlyAuthenticatePassively` models an IdP capability assumption; in real deployments, the SP does not “enable” this capability in Java code.
- The model does not map every IdP failure to `NoPassive`; this represents only missing passive capability.
- With `true,true`, the added condition is **having the ability to authenticate directly without UI interaction**. Otherwise, fresh authentication must not occur in a way that breaks IsPassive.
- The code does not generate a real `AuthnRequest`. Use the Spring customizer in sections 8/9 to build XML in real applications.

## 21. Practical Testing with a Test IdP

### Preparation

- Spring Security Servlet SP with a valid `RelyingPartyRegistration` and public SP entity ID/ACS registered on the IdP.
- SP signing key/certificate if the IdP requires signed requests; trusted IdP public verification cert to validate responses.
- An authorized test account on the IdP and a browser with DevTools/Network.
- Scenarios with an IdP session and without an IdP session, and with/without silent direct authentication methods.
- IdP logs showing authentication method/event per policy if authorized; avoid copying credentials, raw assertions, or cookies.

### Test 1 — Default false/false

1. Log into the IdP beforehand in the test browser.
2. Start SAML login from the SP.
3. Verify the AuthnRequest has `ForceAuthn=false` or attribute omitted, and `IsPassive=false` or omitted.
4. Observe whether the IdP reuses the session and returns a valid response.
5. The SP must still verify the assertion and access permissions; do not assume false flags automatically permit SSO.

### Test 2 — ForceAuthn true, IsPassive false

1. Establish an IdP session beforehand.
2. Start a **new AuthnRequest** in the SP with ForceAuthn true.
3. Capture decoded outbound XML using test methods, confirming ForceAuthn is right and request signature is valid if used.
4. Observe whether the IdP performs a fresh direct authentication event per policy, rather than merely fast-redirecting to the ACS.
5. Inspect `AuthnInstant/AuthnContext` in the **verified** assertion and IdP-side audit logs when needed for evidence.
6. If the IdP ignores the flag while the SP completes login, do not conclude reauthentication succeeded; file an integration/policy defect.

### Test 3 — IsPassive true, No IdP Session

1. Clear the IdP session in the test browser (without altering out-of-scope sessions/credentials).
2. Send an AuthnRequest with `IsPassive=true`, `ForceAuthn=false`.
3. If the IdP has no passive method, expect an error like `NoPassive` instead of interactive login.
4. The SP must not create a new authenticated session from the error response.
5. The UI may let the user click login in a new interactive flow.

### Test 4 — Both Flags True

1. IdP does not support fresh silent authentication: expect failure, with no interactive form violating IsPassive.
2. If the IdP supports a silent direct mechanism per contract: may succeed, requiring suitable authentication evidence.
3. Even if successful, do not infer MFA or authentication age solely from the flag pair.
4. Do not strip IsPassive “transparently” on the server while still claiming the transaction is passive.

### Test 5 — Security Testing

- Someone attempts to alter ForceAuthn in a signed SAMLRequest: the IdP must reject on signature mismatch if policy requires signing and checks properly.
- Callback containing a SAMLResponse with invalid signature, issuer, audience, destination/time, or InResponseTo: the SP must reject and create no Authentication.
- User visits a route while the SP already has a session: verify **whether the resolver actually runs**; if not, the flag cannot trigger step-up on its own.
- IdP returns `NoPassive`: the error handler must not create a redirect loop or silently downgrade policy.
- Multiple tabs/sessions: requests must bind to the exact browser/session to prevent login fixation.
- RelayState/post-login redirect URL must not become an open redirect.

## 22. Reading Real Requests in Developer Tools

1. In the test browser, enable **Network → Preserve log**.
2. Open `GET /saml2/authenticate/corp` (or configured AuthnRequest endpoint) when permitted.
3. Confirm the SP response redirects to the IdP SSO endpoint; if using Redirect binding, the URL carries `SAMLRequest`.
4. Use a safe SAML/DevTools utility or dedicated test debug logging to decode the request: URL decode → Base64 decode → raw DEFLATE inflate. **Never write a servlet endpoint accepting production data just for debugging**.
5. Inspect `<samlp:AuthnRequest>` for `ForceAuthn="true"`, `IsPassive="true/false"` per scenario.
6. Verify the request has the right issuer/entity ID, Destination, ACS, binding, signature, RelayState, and request ID.
7. Observe what follows: whether the IdP interacts via UI or emits a success/error SAMLResponse, and which status code.
8. Inspect ACS, cookies/session, and correlation; check verified `AuthnInstant/AuthnContext` if policy requires.
9. Record **redacted data**: flags, timestamps, status, matching issuer, and test scenario; never post raw SAML assertions, session cookies, private keys, or personal data into public issues.

**Note:** browser requests to the IdP may use POST AuthnRequest in another config; in that case `SAMLRequest` sits in a Base64 HTML form field without Redirect's DEFLATE step. The flags still live inside the XML.

## 23. Common Errors and Diagnostics

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Wrote customizer, yet AuthnRequest lacks the flag | Resolver bean not wired, request not initiated, another bean overriding | Check registered beans, filter chain, exact endpoint/version; decode actual XML |
| `ClassNotFoundException: OpenSaml5...` | Used 7.x API docs on older 6.x dependencies | Check Spring Security/OpenSAML version; pick compatible resolver |
| ForceAuthn is true, yet no password re-entry screen appears | IdP used another mechanism, ignored flag, or has a fresh passive method | Check IdP policy/audit and assertion AuthnInstant/Context; do not infer from UI alone |
| Users are prompted to log in on every app visit | ForceAuthn true for all AuthnRequests | Review policy: apply only to deliberate reauthentication flows |
| Sensitive route still accessible without reauth | SP session already exists; no new AuthnRequest created | Design a step-up flow and track trusted freshness state at SP |
| IsPassive true, yet IdP displays a form | IdP does not support/honor it or misconfigured | Inspect request XML and IdP behavior, report contract bug; do not claim passive succeeded |
| IsPassive true always returns NoPassive | No eligible IdP session or cookies blocked | Test top-level/iframe, cookie policy, and IdP capability |
| ForceAuthn + IsPassive true fails | IdP cannot freshly authenticate while remaining passive | May be spec-compliant behavior; adjust business/UX requirements |
| IdP returns request signature error | Wrong signing key/algorithm/query signature | Check IdP metadata, SP key, and Redirect/POST binding |
| IdP returns AuthnFailed | User could not authenticate per policy | Handle as login failure; create no Authentication |
| SP returns 403 at ACS | CSRF/filter chain or SAML validation error | Classify server error and request method; do not disable CSRF globally |
| Error handler loops after NoPassive | Auto-retrying the same IsPassive request | Stop retrying; offer an explicit interactive choice |
| Valid assertion, yet freshness fails | IdP assertion/contract does not satisfy policy | Block sensitive task; require compliant IdP/assurance |
| InResponseTo mismatch | Lost AuthnRequest/session cookie or wrong request | Check session repository and SameSite on cross-site POST |
| Proxy breaks ACS/issuer | Mismatched public base URL/forwarded headers | Configure trusted proxy, metadata, and entity ID |
| Team assumes ForceAuthn equals MFA | Misunderstood protocol semantics | Separate reauthentication, assurance, MFA, and business authorization |

## 24. Real-World Scenario: Payment Approval

Suppose a user is logged in and viewing a screen for **approving a 100 million VND payment**.

**Product requirement:** before confirming the order, the user must have completed an authentication method of an approved assurance level recently. Simply enabling `ForceAuthn=true` on all SAML logins is insufficient because:
1. When the user is already authenticated at the SP, `POST /payments/approve` can execute without issuing a new AuthnRequest.
2. ForceAuthn does not specify an MFA level.
3. An IdP may not provide sufficiently detailed assurance/freshness evidence.
4. The SP session may outlive when the prior verification expires under business policy.

**Sound design:**
- SP blocks approval if step-up policy is not yet satisfied.
- SP creates a server-side step-up transaction and redirects to initiate an AuthnRequest with ForceAuthn true (and IsPassive false if interaction is needed).
- IdP enforces fresh authentication and the agreed assurance level.
- SP verifies the assertion, identifies the user, checks `AuthnInstant`/`AuthnContext` per policy, and binds to the exact transaction.
- If satisfied, SP marks **step-up verified** bound to user/session/transaction with a short TTL. If unsatisfied or the IdP ignored the requirement, **block approval**.
- When the user confirms the final action, application authorization/CSRF/transaction integrity are still verified.
- Audit logs record timestamp/assurance and authorization decision without storing raw assertions or private keys.

This is a policy design example; never treat RelayState or ForceAuthn as a “transaction signature” by itself.

## 25. Self-Check Exercises with Answers

**Exercise 1.** A user is already logged into the IdP and the SP wants the IdP **not to rely solely on the old session**, allowing interaction. Which flag pair fits?

**Answer:** `ForceAuthn=true, IsPassive=false`. Still requires IdP support and testing; does not mean enforcing MFA.

**Exercise 2.** The SP wants to check whether the IdP can authenticate silently, with no IdP session and no silent authentication support at the IdP. With `IsPassive=true`, what is the expected behavior?

**Answer:** no interactive form displayed contrary to the request; the IdP should return an error such as `NoPassive`. The SP creates no new session from the error and may invite the user to initiate interactive login.

**Exercise 3.** Does setting both ForceAuthn and IsPassive to true make the request invalid from XML creation?

**Answer:** no. Under SAML Core, fresh direct authentication is permitted only if passive constraints remain satisfied; otherwise, the IdP must not violate IsPassive and must fail appropriately.

**Exercise 4.** An application sets ForceAuthn=true in the customizer, yet a user with an SP session enters a protected page immediately. Did the IdP ignore ForceAuthn?

**Answer:** not necessarily; the SP may **not have created a new AuthnRequest**. Determine whether a SAML request was actually issued before evaluating the IdP.

**Exercise 5.** The IdP returns a successful Response; the dev team concludes MFA occurred because the request had ForceAuthn=true. Where is the flaw?

**Answer:** ForceAuthn is a direct-authentication request, **not a declaration of factor count or method**. You need IdP assurance policy and matching evidence inside a verified assertion.

**Exercise 6.** The IdP returns a response with `NoPassive`. Should you ignore the error and keep a newly authenticated session?

**Answer:** no. That is a passive authentication failure; preserve the trust boundary and use a user-initiated interactive fallback if allowed.

**Exercise 7.** ForceAuthn=true, yet an attacker flips the flag to false in the URL. What protects against this?

**Answer:** sign the `AuthnRequest` per binding and require the IdP to verify signature/SP identity; keep policy server-side and verify the result. HTTPS alone does not guarantee integrity of data modifiable in the browser.

**Exercise 8.** With IsPassive=true, the browser still shows a 302 through the IdP. Does this prove the IdP violated the spec?

**Answer:** no. Front-channel redirects and “noticeable UI interaction” are different concepts. Observe IdP/UX and profile behavior.

**Exercise 9.** Point to the exact place to change flags in Spring Security 6.x Servlet.

**Answer:** customize the OpenSAML `AuthnRequest` via `OpenSaml4AuthenticationRequestResolver#setAuthnRequestCustomizer` on the `Saml2AuthenticationRequestResolver` bean (or resolver 5 if the stack/version supports it).

**Exercise 10.** The IdP says it does not support ForceAuthn; the SP still requires strong reauthentication. What is the responsible choice?

**Answer:** update the IdP contract/capabilities, use another supported and verified mechanism/endpoint/policy, or block the assurance-requiring feature. Never “pretend success” just because a valid SAMLResponse arrived.

## 26. Implementation Checklist

- [ ] Clarified the use case: normal login, reauthentication, passive probing, or step-up assurance.
- [ ] Know that ForceAuthn and IsPassive are **attributes on AuthnRequest**, each defaulting to false when omitted.
- [ ] Have a clear policy for all four combinations, especially ForceAuthn=true + IsPassive=true.
- [ ] Spring Security resolver matching the OpenSAML version is registered without conflicting beans.
- [ ] Decoded a test AuthnRequest and confirmed the flags actually go out on the wire.
- [ ] SP signing key/valid request signature configured if required by IdP or when integrity is mandatory.
- [ ] IdP has documented support for flags, bindings, interaction methods, and NoPassive handling.
- [ ] Do not take ForceAuthn/IsPassive policy from user-modifiable query parameters.
- [ ] If MFA is required, have RequestedAuthnContext/IdP policy and verify trusted AuthnContext.
- [ ] If freshness is required, have AuthnInstant/TTL criteria and evaluate the verified assertion.
- [ ] If using step-up, the SP **proactively issues a new AuthnRequest** when needed; do not rely on an existing session to trigger it.
- [ ] Callback/ACS preserves signature, issuer, audience, destination, timestamps, InResponseTo, and replay protection.
- [ ] NoPassive/AuthnFailed are classified without redirect loops or policy bypasses.
- [ ] Tested with IdP session, without session, restricted browser cookies, multiple tabs, proxies, and signed/unsigned requests.
- [ ] Never record raw SAMLResponse, cookies, real RelayState, private keys, or sensitive data in logs/HAR files.

## 27. Technical Summary

**ForceAuthn is a request for the IdP to authenticate directly instead of relying solely on a prior security context; IsPassive is a request for no noticeable UI interaction.** When both are true, the IdP may perform fresh authentication only if it still satisfies passive constraints. The SP builds the right XML via `Saml2AuthenticationRequestResolver`, while the IdP is responsible for processing per spec/policy. For high-risk requirements, never look only at two Booleans to conclude MFA occurred, authentication is fresh enough, or the user is authorized to execute a transaction.

### Authoritative Reference Documentation

- OASIS — *Assertions and Protocols for the OASIS Security Assertion Markup Language (SAML) V2.0*, section 3.4.1 (ForceAuthn, IsPassive) and StatusCode: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- Spring Security 6.5 — Producing AuthnRequests, OpenSaml4AuthenticationRequestResolver customizer: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/login/authentication-requests.html
- Spring Security 7.0 — Producing AuthnRequests, OpenSaml5AuthenticationRequestResolver customizer: https://docs.spring.io/spring-security/reference/7.0/servlet/saml2/login/authentication-requests.html
- Spring Security — Authenticating SAML Responses (Servlet): https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security — SAML 2.0 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Microsoft Entra ID — SAML SSO protocol, ForceAuthn and IsPassive behavior on one vendor: https://learn.microsoft.com/azure/active-directory/develop/single-sign-on-saml-protocol
