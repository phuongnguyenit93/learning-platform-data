# Signing, Signature Verification, and Destination Checking of SAML2 Logout Messages

In **SAML 2.0 Single Logout (SLO)**, clicking a "Log out" button is not merely deleting an application cookie. The Service Provider (SP, or Relying Party/RP) and Identity Provider (IdP, or Asserting Party/AP) can exchange **`LogoutRequest`** and **`LogoutResponse`** through the browser to signal and confirm termination of federated sessions. These messages must have their **origin authenticated**, **integrity protected**, and **intended recipient verified**. Without those checks, a spoofed party could force logouts, tamper with responses, or exploit the wrong endpoint to corrupt logout state.

This lesson focuses on three requirements of **SAML2 Logout**: (1) the SP/IdP **signs messages properly with its own private key**, (2) the recipient **verifies signatures using the partner's trusted public certificate**, and (3) the recipient **validates the message destination (`Destination`)** and other protocol constraints, notably `Issuer`, `InResponseTo`, `NameID`, `SessionIndex`, `StatusCode`, and anti-replay.

**Core principle throughout:** a cryptographically valid signature over SAML content is still **not enough** to decide logout: you also need the right issuer, right registration, right SLO endpoint, right transaction, and right session/user per the SP–IdP contract. Never use HTTP 200 or 302 as a substitute for protocol checks.

## 1. Distinguishing Local Logout and SAML Single Logout

| Activity | Local Logout | SAML2 Single Logout |
| --- | --- | --- |
| Goal | End one application's session | Coordinate ending federated sessions across SP, IdP, and possibly other SPs |
| Where initiated | User/SP application | SP (*RP-initiated*) or IdP (*AP-initiated*) |
| Has `LogoutRequest`? | Not required | Present in the protocol flow |
| Has `LogoutResponse`? | No | Typically used to report request processing outcome |
| SAML signing certificate | Not needed | Needed when SLO uses applicable bindings/signing policies |
| Success condition | Internal session/cookies revoked | SAML messages valid and partner outcomes verified |
| Guarantees all SPs logged out? | No | **Not absolute**: may return `PartialLogout` or encounter network errors |

For example, a user logs into Portal A via IdP B. If Portal A only deletes its own session, the session at IdP B may remain alive; the next time the user visits Portal A, the IdP may SSO them back without prompting for a password. With SLO, the SP signals logout to the IdP and the IdP may coordinate with other SPs, though completeness depends on the IdP, bindings, transaction state, and partners.

**Do not treat SLO as an absolute global revocation.** Applications must distinguish local logout having occurred from federated outcomes `Success`, `PartialLogout`, or failure, and never tell users "logged out of all systems" without evidence.

## 2. Role of LogoutRequest and LogoutResponse

`<samlp:LogoutRequest>` requests terminating one or more federated sessions. Key fields:

- `ID`: unique identifier of the request, used to correlate when receiving a response.
- `IssueInstant`: timestamp when the message was issued.
- `Destination`: where the message is sent; must match the agreed SLO receiving endpoint.
- `Issuer`: Entity ID of the sending party.
- `NameID`, `BaseID`, or `EncryptedID`: identifies the principal per SAML; not necessarily the SP's internal username.
- `SessionIndex`: helps identify which session to revoke when present; do not assume every SAML message includes this field.
- `NotOnOrAfter`: request time limit when provided.

`<samlp:LogoutResponse>` is the outcome of a LogoutRequest:

- `ID`: unique response identifier.
- `InResponseTo`: must link to the **corresponding LogoutRequest's ID** when there is a request-response transaction.
- `Issuer`: identifier of the party sending the response.
- `Destination`: SLO endpoint receiving the response per metadata/contract.
- `Status/StatusCode`: distinguishes `Success`, `PartialLogout`, errors, or other profile statuses.

**Do not confuse `Response@InResponseTo` with `Assertion@AudienceRestriction` from Web SSO login.** LogoutRequest/LogoutResponse are logout protocol messages, not authentication Assertions. Do not copy `SubjectConfirmationData@Recipient` rules from SAML login onto LogoutRequest structures: that `Recipient` field belongs to Assertion bearer subject confirmation, whereas the **logout target** is primarily represented by `Destination`, metadata SLO endpoints, and the specific binding.

## 3. Diagrams of Both Single Logout Flows

### 3.1. RP-Initiated: SP Emits LogoutRequest, IdP Sends LogoutResponse

~~~mermaid
sequenceDiagram
    participant U as Browser
    participant SP as Portal A (SP)
    participant IdP as Identity Provider B
    U->>SP: POST /logout (with appropriate CSRF token)
    SP->>SP: Perform local logout and save SLO correlation
    SP->>SP: Create and sign LogoutRequest with SP key
    SP-->>U: Redirect/POST SAMLRequest to IdP SLO
    U->>IdP: Send signed LogoutRequest
    IdP->>IdP: Verify SP signature, Issuer, Destination, NameID
    IdP->>IdP: Log out and coordinate related sessions
    IdP-->>U: LogoutResponse signed by IdP
    U->>SP: Send SAMLResponse to SP SLO endpoint
    SP->>SP: Verify IdP signature, Destination, InResponseTo, Status
    SP-->>U: Post-verification logout result
~~~

In this flow **the SP private key** signs LogoutRequest and **the SP public certificate** is used by the IdP to verify. When the IdP returns LogoutResponse, roles reverse: **the IdP private key** signs and **the IdP public certificate** is used by the SP to verify.

Spring Security describes `Saml2RelyingPartyInitiatedLogoutSuccessHandler` using `Saml2LogoutRequestResolver` to build/sign/serialize the request, and then `Saml2LogoutResponseFilter` using `Saml2LogoutResponseValidator` to validate the response. Spring stores the initial request in a repository to correlate `InResponseTo` and `RelayState`.

### 3.2. AP-Initiated: IdP Emits LogoutRequest, SP Sends LogoutResponse

~~~mermaid
sequenceDiagram
    participant U as Browser
    participant IdP as Identity Provider B
    participant SP as Portal A (SP)
    U->>IdP: Log out at IdP
    IdP->>IdP: Create and sign LogoutRequest with IdP key
    IdP-->>U: Forward SAMLRequest to SP SLO endpoint
    U->>SP: Send LogoutRequest to /logout/saml2/slo
    SP->>SP: Verify IdP signature, Issuer, Destination, principal/session
    SP->>SP: Revoke matching local session if valid
    SP->>SP: Create/sign LogoutResponse with SP key
    SP-->>U: Forward LogoutResponse to IdP endpoint
    U->>IdP: Receive LogoutResponse from SP
    IdP->>IdP: Verify SP signature, Destination, InResponseTo
~~~

In AP-initiated SLO, the SP must **verify the request before executing any session-destroying action based on an external request**. Spring Security uses `Saml2LogoutRequestFilter` and `Saml2LogoutRequestValidator` for inbound requests, then `Saml2LogoutResponseResolver` to build/sign the response. Cookies/sessions are revoked per policy; never destroy another account's session merely because of a browser-supplied NameID.

## 4. Who Signs, and Who Verifies?

| Exchange Direction | Message | Private Key Used to Sign | Public Certificate Used to Verify |
| --- | --- | --- | --- |
| SP → IdP (RP-initiated) | `LogoutRequest` | **SP private signing key** | **SP public certificate** trusted by IdP |
| IdP → SP (RP-initiated reply) | `LogoutResponse` | **IdP private signing key** | **IdP public certificate** trusted by SP |
| IdP → SP (AP-initiated) | `LogoutRequest` | **IdP private signing key** | **IdP public certificate** trusted by SP |
| SP → IdP (AP-initiated reply) | `LogoutResponse` | **SP private signing key** | **SP public certificate** trusted by IdP |

**Security rules on ownership:**

- The SP keeps the SP `private key` secret, publishing only the certificate/public key in **SP metadata** when needed.
- The IdP keeps the IdP `private key` secret, publishing the matching certificate in **IdP metadata**.
- The SP configures `RelyingPartyRegistration.signingX509Credentials` for SAML messages it signs.
- The SP configures/loads `AssertingPartyMetadata.verificationX509Credentials` from an **approved** IdP source to verify signatures arriving from the IdP.
- Never use the **IdP's verification certificate** as the SP's signing private key. Never put private keys in committed YAML, logs, or public SAML metadata.
- When the IdP rotates certificates, the SP must update trust anchors/metadata via process, with an overlap window if needed. Never extract an arbitrary certificate from a SAML message and trust it as IdP B.

TLS protects the HTTP channel, yet **does not replace** SAML message-layer signature checks when required by profile/binding. The browser is a transport, not a trust anchor.

## 5. Signature Differences Between HTTP-Redirect and HTTP-POST Bindings

SAML supports multiple bindings, though Spring Security SAML2 SLO on Servlet typically operates with **HTTP-Redirect** and **HTTP-POST**. Signing mechanisms differ:

### A. HTTP-Redirect Binding

`LogoutRequest` or `LogoutResponse` data is typically DEFLATE-compressed, Base64-encoded, and URL-encoded into the `SAMLRequest` or `SAMLResponse` query parameter. When signed per Redirect binding, the URL carries `SigAlg` and `Signature`; the signature covers a **canonicalized query parameter string defined by the binding**, not an arbitrarily signed raw XML string.

Illustrative format:

~~~text
GET https://idp.partner-b.example/saml/slo?
  SAMLRequest=<deflated-base64-url-encoded-message>
  &RelayState=<url-encoded-state>
  &SigAlg=<url-encoded-algorithm-uri>
  &Signature=<url-encoded-signature>

For LogoutResponse, use SAMLResponse instead of SAMLRequest.
~~~

**Risk:** reordering query parameters, inconsistent decode-encode, adding/removing RelayState, or verifying the signature over XML rather than the signed query string breaks verification. Never write a custom Redirect binding signer/verifier. Use Spring Security/OpenSAML and match `Saml2MessageBinding.REDIRECT` accurately with partner metadata.

### B. HTTP-POST Binding

The SAML message is usually Base64 XML in the HTTP POST body. Signing uses XML Digital Signature, typically `<ds:Signature>` on the appropriate element. XML signatures require verifying canonicalization, signed references, IDs, and preventing signature wrapping. You cannot simply Base64-decode and compare bytes or trust a certificate embedded inside the XML itself.

Illustrative format:

~~~text
POST /logout/saml2/slo
Content-Type: application/x-www-form-urlencoded

SAMLRequest=<base64-encoded-xml>
RelayState=<opaque-value-when-present>
~~~

**The signature may live inside the XML**, not necessarily as a `Signature` query parameter like Redirect binding. Both XML signatures and query-binding signatures have distinct verification rules. A request "having `ds:Signature` visible" does not mean the signature is valid; it must be verified with a trusted key and reference the exact message.

**Operational rule:** cross-check the binding at `SingleLogoutService/@Binding` in IdP/SP metadata. Use SHA-256/modern algorithms per policy; never arbitrarily permit SHA-1 or weak algorithms. If a message is signed in a manner mismatched with the binding, fail closed; never skip verification for "compatibility".

## 6. Checking Destination: "Validly Signed" Can Still Go to the Wrong Place

`Destination` is the address where the sender expects the message **to be received**. For SLO:

| Message | Direction | Expected Destination |
| --- | --- | --- |
| RP LogoutRequest | SP → IdP | **IdP SLO request endpoint** in IdP metadata |
| AP LogoutResponse | IdP → SP | **SP SLO response endpoint** published by SP |
| AP LogoutRequest | IdP → SP | **SP SLO request endpoint** published by SP |
| RP LogoutResponse | SP → IdP | **IdP SLO response endpoint** in IdP metadata; may differ from request URL |

For example, if the SP has public SLO address:

~~~text
https://portal.example.com/logout/saml2/slo
~~~

While IdP B has:

~~~text
IdP SLO request URL:
https://login.partner-b.example/saml2/slo/request

IdP SLO response URL:
https://login.partner-b.example/saml2/slo/response
~~~

Then requests from the SP to the IdP must target `.../request`, while responses from the SP to the IdP after AP-initiated logout may need `.../response`. Never assume request and response endpoints always share the same URL. `RelyingPartyRegistration` and `AssertingPartyMetadata` provide `singleLogoutServiceLocation` and `singleLogoutServiceResponseLocation` for each side.

**`Destination` rules in SAML Core depend on binding/profile.** In signed Web SLO environments, the app must define the exact permitted public receiving URL and validate the field when present/required per profile/policy. Never ignore a wrong Destination simply because the signature is valid. Never accept `http://localhost:8080` in place of `https://portal.example.com` in production.

### Do Not Confuse Destination, Recipient, and RelayState

- **`Destination`:** where the logout message is received.
- **`SubjectConfirmationData` `Recipient`:** field on a bearer Assertion during **login**, not a required attribute of LogoutRequest/LogoutResponse.
- **`RelayState`:** state parameter transported via browser; used to correlate transactions via repository/session and binding. It does not by itself prove the message came from the right IdP.
- **`InResponseTo`:** links LogoutResponse to a prior LogoutRequest; essential when verifying RP-initiated or AP-initiated outcomes.

If a custom validator checks only Destination while omitting issuer/signature, an attacker can still forge logout messages targeting the right URL. If it checks only the signature without Destination, a message signed for another endpoint could be wrongly processed by your app.

## 7. LogoutRequest and LogoutResponse Examples for Field Reading

### AP-Initiated LogoutRequest Sent to SP

~~~xml
<samlp:LogoutRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_req-123"
    Version="2.0"
    IssueInstant="2026-11-07T10:00:00Z"
    Destination="https://portal.example.com/logout/saml2/slo">
  <saml:Issuer>https://login.partner-b.example/idp</saml:Issuer>
  <saml:NameID>employee-123</saml:NameID>
  <samlp:SessionIndex>session-b-456</samlp:SessionIndex>
</samlp:LogoutRequest>
~~~

### RP LogoutResponse Returned to IdP

~~~xml
<samlp:LogoutResponse
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_resp-789"
    InResponseTo="_req-123"
    Version="2.0"
    IssueInstant="2026-11-07T10:00:01Z"
    Destination="https://login.partner-b.example/saml2/slo/response">
  <saml:Issuer>https://portal.example.com/sp/partner-b</saml:Issuer>
  <samlp:Status>
    <samlp:StatusCode
        Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
  </samlp:Status>
</samlp:LogoutResponse>
~~~

**Note:** both fragments only illustrate attribute placement. They **lack signatures**, example IDs may be reused, and they lack full trust context; **they are not valid messages for deployment**. With Redirect binding, the signature may be in query parameters rather than inside the XML. With POST XML signatures, a valid `ds:Signature` structure per OpenSAML is needed. Never copy these XML snippets and accept them in production.

Analysis:

1. SP sees `Issuer=https://login.partner-b.example/idp`: it must look up registered IdP B rather than trusting a self-declared issuer in XML.
2. SP verifies the request signature with the public certificate **already trusted for B**.
3. SP verifies `Destination` matches the public SLO endpoint receiving the request.
4. SP verifies `NameID` / `SessionIndex` matches an active session per profile.
5. SP revokes matching sessions only **after the request is accepted**.
6. SP returns a LogoutResponse with `InResponseTo="_req-123"` to IdP B's response endpoint, signed with the SP's private key.
7. IdP verifies issuer, signature, destination, correlation, and `StatusCode` before concluding completion.

## 8. Binding Issuer and Selected Key: Never Trust an Arbitrary Certificate

**`Issuer` is a self-reported value in the message, not cryptographic proof on its own.** Proper flow:

1. Determine `RelyingPartyRegistration` from state/session, resolver, or issuer info via a controlled lookup.
2. Obtain the **Asserting Party Entity ID** configured on that registration.
3. Obtain the exact `verificationX509Credentials` for that IdP.
4. Verify the signature over the **received message/binding**.
5. Verify the signed issuer matches the trusted Entity ID.
6. Verify message Destination, correlation, NameID/session, and applicable conditions.
7. Only then execute logout/session cleanup.

**Dangerous bug:** parsing XML to extract the certificate under `KeyInfo` (if present), verifying the signature with it, and assuming the IdP is authenticated. Any attacker can generate a public/private key pair and sign their own message. A signature only establishes **authentication** when the public key is bound to a **pre-approved** issuer.

With multiple IdPs (`corp`, `partner-b`, `partner-c`), each registration may have a different certificate. A valid signature from IdP C must never impersonate IdP B, even if `NameID` and `Destination` match. During rollover, old/new IdP keys may be trusted simultaneously for a window per verified metadata/policy, but there must be a cutover deadline and monitoring.

## 9. Checking InResponseTo, RelayState, and Preventing Spoofed Responses

In **RP-initiated SLO**, the SP emits LogoutRequest `ID=_sp-req-001`. Then the IdP returns a LogoutResponse containing:

~~~text
InResponseTo = _sp-req-001
Issuer       = Registered IdP B
Destination  = SP SLO response URL
Status       = Success or appropriate error code
~~~

The SP must correlate this against the previously stored request in `Saml2LogoutRequestRepository`. Spring Security provides `HttpSessionLogoutRequestRepository` to store requests in the session, allowing `RelayState` and `InResponseTo` verification when the response returns. If replacing the repository, ensure TTL, session/browser binding, anti-replay, and never allow another user's response to match the current request.

Scenarios that must be rejected:

- `InResponseTo` does not match the SP's request ID.
- No stored request exists, yet a response arrives claiming to be an RP-initiated outcome.
- A previously consumed response is replayed.
- Issuer differs from the IdP selected for the original request.
- `Destination` is another SP's SLO URL.
- Signature does not match the trusted IdP certificate.
- `StatusCode` reports failure/`PartialLogout` while the app claims all SPs completed.

**RelayState is neither a password nor a self-authenticating token:** an attacker can manipulate URLs/forms from the browser. Trust outcomes only after binding signature, request repository, and SAML validation succeed. Never use `RelayState` to dynamically pick an arbitrary IdP metadata URL.

## 10. Checking NameID, SessionIndex, and Session State

A LogoutRequest contains `NameID` or an equivalent identifier designating the subject; `SessionIndex` (when present) helps pinpoint the session to log out. Both fields have SAML semantics:

- IdP `NameID` may be persistent, transient, or another scoped identifier; **it does not necessarily match the SP's local username/email**.
- `SessionIndex` is tied by the IdP to an authentication session; **it is not the app's JSESSIONID** and not necessarily a Redis session ID.
- One user can have multiple distinct sessions; logging out one session does not automatically delete all sessions unless policy/protocol specifies so.
- `LogoutResponse` must never be used as an automatic command to log out an arbitrary user; it is a reply to a specific request.

When Spring Security 7 uses custom principal/authority mapping, preserve the SAML data still needed for SLO. `Saml2AssertionAuthentication` and `Saml2ResponseAssertionAccessor` help retain assertion/registration info needed for logout. If a converter produces a plain `UsernamePasswordAuthenticationToken` and drops NameID/SessionIndex/registration, a successful login can still lead to SLO failure.

**Security:** validate an AP-initiated LogoutRequest before revoking sessions; require exact issuer/NameID/session per trusted state. Never delete all sessions of a user based solely on a NameID taken from unverified XML.

## 11. Minimal Configuration Steps in Spring Boot

Spring Security SAML2 on Servlet uses the `spring-security-saml2-service-provider` dependency, `RelyingPartyRegistrationRepository`, IdP metadata, and version-appropriate credentials. Per official guidance, SLO needs:

1. IdP B genuinely supports Single Logout, typically publishing `<SingleLogoutService>` in metadata.
2. SP has a PKCS#8 **signing private key** and matching certificate to sign outbound messages.
3. SP knows **IdP B's verification public certificate** to verify inbound messages.
4. SP/IdP agree on SLO URLs, bindings, and signing policies.
5. `saml2Logout(...)` is enabled on `SecurityFilterChain`.

Example `application.yml` for Spring Boot versions supporting these properties:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-b:
            entity-id: "https://portal.example.com/sp/partner-b"
            signing:
              credentials:
                - private-key-location: "classpath:credentials/sp-signing-private.key"
                  certificate-location: "classpath:credentials/sp-signing-public.crt"
            singlelogout:
              url: "https://portal.example.com/logout/saml2/slo"
            assertingparty:
              metadata-uri: "https://login.partner-b.example/metadata"
~~~

This is an **illustrative configuration**, without real private keys/certs, and `.example` domains do not exist. In production, private keys must come from managed secret management/keystores, never committed to source. IdP metadata must be loaded from a trusted source and checked for issuer/certificates; explicit verification credentials may be needed if metadata is unavailable or enterprise policy requires them.

`singlelogout.url` is the **SP's published SLO endpoint**, not the **IdP SLO destination**. The IdP target is typically read from `<SingleLogoutService>` in IdP metadata or configured via `AssertingPartyMetadata.singleLogoutServiceLocation` and `singleLogoutServiceResponseLocation`.

When changing `singlelogout.url`, synchronize **SP metadata, IdP configuration, and the logout endpoint DSL**. A valid YAML snippet alone is insufficient if a proxy or the IdP still uses an old URL.

## 12. SecurityFilterChain Configuration and Default SLO Paths

JavaConfig example in a Spring Security Servlet project with a valid registration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSingleLogoutSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Logout(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**Precondition:** this is a class inside a Spring application and cannot compile standalone with `javac` without dependencies. `saml2Logout` enables SAML2 SLO on the app; each registration still needs an SLO location and signing credentials per Spring docs. `saml2Metadata` publishes SP metadata so partners can read SLO parameters.

In current Spring Security SLO docs, common endpoints include:

| Endpoint | Purpose |
| --- | --- |
| `POST /logout` | User at SP initiates RP-initiated logout, subject to CSRF/LogoutFilter policy |
| `POST /logout/saml2/slo` with `SAMLRequest` | Receives IdP-initiated LogoutRequest |
| `POST /logout/saml2/slo` with `SAMLResponse` | Receives LogoutResponse returned to SP |
| `GET /saml2/metadata/{registrationId}` when metadata enabled | Exposes SP metadata, including SLO service if configured |

**Version note:** overview/docs pages may vary on SLO aliases or GET/POST/binding methods. Use your **resolved Spring Security version**, Javadoc, and actual metadata XML/HTTP requests as the authority for implementation; never hardcode another alias from a random tutorial. `/logout/saml2/slo` in the table is the URL documented in Spring Security's SLO guide, not a guarantee that every custom filter or reverse proxy uses the exact same route.

### Changing the URL Receiving LogoutRequest and LogoutResponse

For example, to use `/federation/saml/slo`:

~~~java
http.saml2Logout(saml -> saml
        .logoutRequest(request ->
                request.logoutUrl("/federation/saml/slo"))
        .logoutResponse(response ->
                response.logoutUrl("/federation/saml/slo")));
~~~

**Update both places** if request and response share the new URL. Also update `RelyingPartyRegistration.singleLogoutServiceLocation`, SP metadata, and the IdP application. In the example, `logoutRequest(...).logoutUrl(...)` receives **IdP→SP LogoutRequest**, while `logoutResponse(...).logoutUrl(...)` receives **IdP→SP LogoutResponse**; do not confuse these with `saml2Logout(saml -> saml.logoutUrl("/saml2/logout"))`, which is the **SP-initiated logout trigger URL**.

A misconfigured custom route can cause signed responses to arrive at the right public URL yet miss the filter, returning 404 or redirecting to login. Never disable signature validation to work around endpoint mismatches.

## 13. Building SLO Configuration with RelyingPartyRegistration.Builder

Beyond YAML, JavaConfig can load approved IdP metadata and declare SP-side SLO:

~~~java
Saml2X509Credential signingCredential =
        Saml2X509Credential.signing(spPrivateKey, spCertificate);

RelyingPartyRegistration registration = RelyingPartyRegistrations
        .fromMetadataLocation(trustedIdpMetadataUrl)
        .registrationId("partner-b")
        .entityId("https://portal.example.com/sp/partner-b")
        .singleLogoutServiceLocation(
                "https://portal.example.com/logout/saml2/slo")
        .signingX509Credentials(credentials ->
                credentials.add(signingCredential))
        .build();
~~~

This is a **Spring project Java fragment** requiring safely loaded/verified `spPrivateKey`, `spCertificate`, `trustedIdpMetadataUrl`, imports, and a repository bean. `Saml2X509Credential.signing` takes the SP's private key + certificate to sign outbound messages. `fromMetadataLocation` must only accept admin-configured metadata URLs/files, **never** browser-supplied URLs, to prevent SSRF/IdP spoofing.

If IdP metadata lists different `SingleLogoutService` entries for requests vs. responses, the builder or `AssertingPartyMetadata.Builder` can configure `singleLogoutServiceLocation`, `singleLogoutServiceResponseLocation`, and bindings per your running Spring Security version.

**Distinction:** `RelyingPartyRegistration.Builder.singleLogoutServiceLocation` describes the **SP's** SLO endpoint, whereas `AssertingPartyMetadata.Builder.singleLogoutServiceLocation` describes the **IdP's** SLO endpoint. Never mix up the two URLs.

## 14. Verify Signatures with Official Validators—Never Write Manual XML Parsers

Spring Security provides:

- `Saml2LogoutRequestFilter` to receive IdP LogoutRequests.
- `Saml2LogoutResponseFilter` to receive IdP LogoutResponses.
- `Saml2LogoutRequestValidator` and `Saml2LogoutResponseValidator` to evaluate messages.
- In Spring Security 7/OpenSAML 5, `OpenSaml5LogoutRequestValidator` and `OpenSaml5LogoutResponseValidator` validate signatures, issuer, destination, and message-specific constraints.
- `Saml2LogoutRequestResolver` / `Saml2LogoutResponseResolver` to create, sign, and serialize outbound SP messages.
- `Saml2LogoutRequestRepository` to store request state while awaiting responses.

Spring docs advise using default validators and adding custom policies only when genuinely required:

~~~java
http.saml2Logout(saml -> saml
        .logoutRequest(request ->
                request.logoutRequestValidator(myRequestValidator))
        .logoutResponse(response ->
                response.logoutResponseValidator(myResponseValidator)));
~~~

This is a **customization fragment**: `myRequestValidator` and `myResponseValidator` must be real implementations; they are not included in the snippet. Without non-default requirements, **you do not need to configure them**. Custom validators should **delegate to the standard validator first**, **reject if it returns errors**, and only then run additional business rules. Never replace the validator with an always-success stub, as that drops signature, issuer, and destination checks.

### What Extra Checks Might Be Needed?

A B2B application may require:

- Only IdP B may control sessions for tenant B.
- `NameID`/`SessionIndex` must correspond to an existing SAML-authenticated session.
- Stale requests or expired `NotOnOrAfter` must be rejected per policy/binding.
- `LogoutResponse@InResponseTo` must match the stored request along with issuer/registration.
- Only a specific set of `StatusCode` values may report "completed"; `PartialLogout` must render differently.
- Metadata/certificate rotation state must never accept unknown issuers.
- Replayed message IDs must be rejected per policy.

These checks are **additive**; they do not replace the library's signature and Destination verification. If writing any custom XML parser, you would have to guard against DTD/external entities, canonicalization flaws, and signature wrapping; best practice is **not writing your own** and relying on OpenSAML APIs.

## 15. Why Looking Only at StatusCode Success Is Insufficient

A `LogoutResponse` containing:

~~~xml
<samlp:Status xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol">
  <samlp:StatusCode
      Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
</samlp:Status>
~~~

declares `Success`, yet any untrusted sender can craft XML that looks like this. To trust that this is IdP B's reply to SP A's request, you must verify:

1. Signature matches trusted IdP B/certificate.
2. `Issuer` matches IdP B.
3. `Destination` matches the SP's SLO response URL.
4. `InResponseTo` matches the LogoutRequest ID saved in the pending transaction.
5. `RelayState`/browser session matches, if used.
6. Status is parsed per standard and fits context.
7. Message is not replayed and timestamps/system state are normal.

Never conclude "full logout succeeded" from `HTTP 302`, an unverified `StatusCode=Success`, or merely because the SP session was invalidated. When the IdP returns `PartialLogout`, distinguish "logged out of current application" from "logged out across all services".

## 16. Reverse Proxies and Hostnames: Common Cause of Destination Mismatches

Suppose the Java service runs internally at:

~~~text
http://sp-backend:8080
~~~

While the IdP knows the public URL:

~~~text
https://portal.example.com/logout/saml2/slo
~~~

If the app generates `Destination` or metadata from internal `{baseUrl}`, the IdP may reject requests targeting the wrong address. Conversely, if the IdP sends a LogoutRequest with the public Destination while the backend compares against an internal Host header, errors occur unless proxy forwarding is configured properly.

How to handle:

1. Lock down the public SLO scheme/host/port/path on both SP and IdP.
2. Set `singleLogoutServiceLocation`/`ResponseLocation` to fixed public URLs or verified placeholders.
3. Accept `Forwarded`/`X-Forwarded-*` only from **trusted reverse proxies**, stripping client-supplied headers from the Internet to prevent host-header injection.
4. Ensure proxies forward HTTP POST/Redirect bindings intact without stripping `SAMLRequest`, `SAMLResponse`, `RelayState`, `SigAlg`, or `Signature`.
5. For HTTP-Redirect signatures, avoid any rewrite that alters query encoding relative to the signed string.
6. Inspect SP metadata at the public URL, cross-checking `<SingleLogoutService>` with the IdP registration.
7. Test both RP-initiated and AP-initiated flows after deployment, not just HTTP 200 on endpoints.

**Never disable Destination validation to "fix" proxy errors.** Fix metadata, public URLs, and proxy forwarding/trust headers properly.

## 17. Certificates, Signing Algorithms, and Key Rotation

A production deployment needs procedures for:

- **Key generation:** SP generates its private signing key in a proper HSM/keystore/vault; the public certificate is provided to the IdP.
- **IdP trust:** SP obtains the IdP's public signing certificates from verified metadata or an official channel.
- **Key rotation:** support old/new keys during a bounded transition window when partners permit; assign an owner, schedule, and rollback plan.
- **Algorithm policy:** prefer modern algorithms compatible with Spring/OpenSAML and the IdP; never indiscriminately enable SigAlg/SHA-1 just to bypass an error.
- **Certificate expiration:** monitor certificate expiry and trust chains per policy, distinguishing signature errors from certificate expiration errors.
- **Secret handling:** never log private keys, commit them to repos, or expose them in a public metadata endpoint.
- **Multiple IdPs:** each registration uses the exact approved issuer certificate.
- **Deployment consistency:** all SP nodes must share the same trust/key configuration, avoiding node A signing with a new key not yet trusted by the IdP or node B using stale metadata.

An IdP certificate merely appearing in HTTP metadata is not automatically trustworthy: verify endpoint/metadata signatures/trust channels. If an IdP's signing cert changes unexpectedly, never auto-import and trust the new certificate from a Response.

## 18. Standalone Java 17: Understanding Sign–Verify and Destination

The following program uses the **Java Cryptography Architecture (JCA)** to demonstrate: sender signs a string with a private key; receiver verifies with a pre-selected public key; altering content, swapping the public key, or using the wrong destination changes the verification outcome.

**Important:** this is an *educational demo on byte strings*, **not SAML XML Signature or HTTP-Redirect binding signature**. The code does not parse SAML XML, does not process DEFLATE/Base64/RelayState, does not validate SignedInfo/references/canonicalization, and is not an SLO implementation. In real products, you must use Spring Security/OpenSAML validators.

Create file `SamlLogoutSignatureDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.util.Objects;

public class SamlLogoutSignatureDemo {

    static byte[] sign(String payload, PrivateKey privateKey)
            throws GeneralSecurityException {
        Signature signature = Signature.getInstance("SHA256withRSA");
        signature.initSign(privateKey);
        signature.update(payload.getBytes(StandardCharsets.UTF_8));
        return signature.sign();
    }

    static boolean verify(
            String payload, byte[] signed, PublicKey publicKey)
            throws GeneralSecurityException {
        Signature signature = Signature.getInstance("SHA256withRSA");
        signature.initVerify(publicKey);
        signature.update(payload.getBytes(StandardCharsets.UTF_8));
        return signature.verify(signed);
    }

    static boolean correctDestination(
            String actual, String expectedPublicEndpoint) {
        return expectedPublicEndpoint.equals(actual);
    }

    static boolean correlates(
            String inResponseTo, String storedRequestId) {
        return storedRequestId != null
                && Objects.equals(inResponseTo, storedRequestId);
    }

    public static void main(String[] args)
            throws GeneralSecurityException {

        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);

        KeyPair trustedIdp = generator.generateKeyPair();
        KeyPair unrelatedParty = generator.generateKeyPair();

        String destination =
                "https://portal.example.com/logout/saml2/slo";
        String logoutRequest = "LogoutRequest|ID=_idp-req-1"
                + "|Issuer=https://idp.partner-b.example"
                + "|Destination=" + destination;

        byte[] signed = sign(logoutRequest, trustedIdp.getPrivate());

        System.out.println("Trusted signature: " + verify(
                logoutRequest, signed, trustedIdp.getPublic()));

        System.out.println("Tampered message accepted: " + verify(
                logoutRequest + "|NameID=another-user",
                signed,
                trustedIdp.getPublic()));

        System.out.println("Wrong key accepted: " + verify(
                logoutRequest, signed, unrelatedParty.getPublic()));

        System.out.println("Expected destination: "
                + correctDestination(destination, destination));

        System.out.println("Wrong destination accepted: "
                + correctDestination(
                    "https://other-sp.example.com/logout/saml2/slo",
                    destination));

        System.out.println("Matching InResponseTo: "
                + correlates("_sp-req-100", "_sp-req-100"));

        System.out.println("Wrong InResponseTo accepted: "
                + correlates("_sp-req-999", "_sp-req-100"));
    }
}
~~~

Use JDK 17 or later:

~~~bash
javac SamlLogoutSignatureDemo.java
java SamlLogoutSignatureDemo
~~~

**Exact stdout** (RSA keys differ each run, though Boolean outputs are identical):

~~~text
Trusted signature: true
Tampered message accepted: false
Wrong key accepted: false
Expected destination: true
Wrong destination accepted: false
Matching InResponseTo: true
Wrong InResponseTo accepted: false
~~~

Explanation:

- `Trusted signature: true`: signature matches the **exact public key** corresponding to the signing private key.
- `Tampered message accepted: false`: modifying signed content causes signature verification to fail.
- `Wrong key accepted: false`: a public key not belonging to the signer is rejected.
- `Expected destination: true`: matches the configured public SLO URL.
- `Wrong destination accepted: false`: another SP's destination must be rejected per policy.
- `Matching InResponseTo: true`: the reply matches only the stored request.
- `Wrong InResponseTo accepted: false`: a response referencing another request is invalid.

**Never take `correctDestination` and `verify` from this demo and apply them directly to production SAML.** URL canonicalization/forwarded headers, binding signatures, XML ID/reference validation, issuer, timestamps, replay, and sessions are handled by the SAML library. The program generates ephemeral RSA keys for demonstration without writing private keys to disk.

## 19. Integration Testing to Actually Prove Safe SLO

A test suite should cover **both RP-initiated/AP-initiated directions** plus numerous negative tests:

| Test | Input | Expected Outcome |
| --- | --- | --- |
| RP-initiated happy path | SAML-logged-in user, POST logout with CSRF | SP signs LogoutRequest, IdP verifies, returns valid LogoutResponse |
| AP-initiated happy path | IdP signs LogoutRequest with right issuer/target | SP verifies then logs out right session, signs LogoutResponse |
| Bad IdP signature | Tampered SAMLRequest or signed with unknown key | Rejected; does not execute logout on forged request |
| Bad SP signature | IdP receives request/response not matching SP cert | IdP rejects, alerts on key configuration |
| Redirect query modified | Altered `RelayState` or `SigAlg` in signed message | Binding signature invalid; rejected |
| POST XML signature wrapping | Message payload referencing wrong signed element | Forged/spoofed content rejected |
| Unknown issuer | IdP C signs but routed/registered as B | SP does not accept as IdP B |
| Wrong Destination | Signed request from B sent to SP C | SP A rejects |
| Wrong proxy URL | Destination `http://internal:8080` vs. public HTTPS | Test fails; fix public metadata/forwarding |
| Wrong response correlation | `InResponseTo` differs from stored request ID | Do not treat this transaction's logout as succeeded |
| RelayState from another session | Response sent to another browser | Do not cross-match transactions |
| Replayed message | Reuse LogoutRequest/Response ID | Rejected per anti-replay policy |
| Wrong NameID/SessionIndex | IdP B asks to log out session not belonging to principal | Do not delete wrong session/account |
| Status `PartialLogout` | Another SP fails to complete | Distinguish incomplete from global success |
| Expired request | Past `NotOnOrAfter` if used | Rejected per profile/policy |
| IdP certificate rotation | Switch approved cert | Only keys in trust set are accepted |
| SP signing rotation | IdP updates SP public cert | Request/response verify cleanly after cutover |
| POST/Redirect binding | Each binding supported by partner | Verify exact signature type and endpoint |
| New SLO endpoint | DSL + metadata + IdP share URL | Requests/responses reach the right filter |
| Logout without SAML session | Local-login/anonymous user | Do not emit inappropriate LogoutRequest |
| Local session already destroyed | IdP SLO failure/network timeout | App handles and reports distinct from global SLO outcome |
| Multiple IdPs | User B/IdP C shares same NameID | Never log out or reply to the wrong partner |

**Testing only "signed requests" is not enough.** Create SAML messages signed with a valid cert yet sent with **wrong destination**, **wrong InResponseTo**, or **wrong NameID**; only then do you prove validators check everything beyond signatures.

### Verification Steps in Staging

1. Open SP metadata `/saml2/metadata/partner-b` if enabled; check `SPSSODescriptor/SingleLogoutService` binding and location.
2. Verify IdP metadata has `IDPSSODescriptor/SingleLogoutService` and valid certificates.
3. Log in to SP via the test IdP to establish a real SAML session.
4. POST logout with a valid CSRF token; use controlled developer/test proxy tools to inspect the redirect/form flow.
5. Verify `SAMLRequest` goes to the right IdP SLO request endpoint.
6. IdP verifies signature and returns `SAMLResponse` with matching `InResponseTo`.
7. SP verifies using `Saml2LogoutResponseValidator`, handles status, and redirects the application.
8. Repeat with IdP-initiated, bad signature, wrong destination, and response replay.
9. Verify the app session is genuinely invalidated and other linked services report accurate state.
10. Verify logs record only safe error codes and correlation IDs, with no raw SAML messages containing user data.

All HTTP commands require real endpoints and certificates. `curl -i https://portal.example.com/saml2/metadata/partner-b` is only an example for reading metadata; there is no fixed XML stdout to copy from this lesson.

## 20. Distinguishing CSRF from SAML Signature

There are **two distinct layers of protection**:

- Application **CSRF tokens** protect internal logout commands like `POST /logout` from another website forcing a user to submit the request.
- **SAML signatures** protect SLO messages traveling via the browser between SP and IdP, proving the signer is authorized and contents were not altered per profile.

When the IdP sends `SAMLRequest` or `SAMLResponse` to the SP SLO endpoint, it is a cross-site POST per the protocol. Spring Security includes SAML logout handling logic; if customizing endpoints/CSRF policies, apply a narrow exception accordingly and **never disable CSRF application-wide** just to avoid 403 errors.

An attacker sending a forged `POST /logout/saml2/slo` is not permitted merely because CSRF tokens are absent: that endpoint must **verify SAML signature, issuer, and destination** per policy. Conversely, a `POST /logout` with valid CSRF does not by itself prove IdP SLO completed.

## 21. Common Errors and Remediation

| Symptom | Common Cause | Right Remediation |
| --- | --- | --- |
| IdP does not support SLO | Metadata lacks `SingleLogoutService` | Verify capabilities; do not promise global logout |
| No LogoutRequest sent to IdP | `saml2Logout` not enabled, registration lacks SLO, principal lacks context | Check filter chain, metadata, and SAML Authentication |
| "Signature invalid" at IdP | SP used wrong/rotated key or wrong binding signature | Synchronize SP public certificate and signing configuration |
| "Signature invalid" at SP | IdP cert mismatch or unscheduled rotation | Update verification creds from trusted metadata |
| Redirect signed query error | Proxy rewrote/re-encoded signed parameters | Preserve binding canonical input; inspect wire request |
| XML signed with right key but rejected | Wrong Issuer, Destination, correlation, or status | Check corresponding rule; do not disable signature validation |
| Invalid Destination | Public URL and metadata/proxy mismatch | Synchronize SLO public host/path/binding |
| LogoutResponse fails verification | Lost request repository/session/RelayState or wrong InResponseTo | Check request correlation and browser session |
| Logged out wrong user | Failed to check NameID/SessionIndex or tenant | Bind strictly to verified session |
| Local logout succeeds but IdP keeps session | SLO disabled or network/IdP error | Distinguish local/global, handle fallback, report honestly |
| `PartialLogout` reported as success | Checked only HTTP status or matched a single string | Evaluate verified StatusCode per policy |
| Logout endpoint 404/405 | SLO URL out of sync across DSL, metadata, and IdP | Update all three; test POST/Redirect |
| SLO works on node A, fails on node B | Out-of-sync key/trust metadata or session repo | Check deployment/keystore/session sharing |
| SAMLResponse exposes sensitive data in logs | Debug logging raw payload | Redact logs, audit, and protect data |
| User completed local logout yet got SSO again | IdP session remains alive | Check RP-initiated SLO; do not assume logout everywhere |

Do not fix incidents by dropping signature verification or allowing any Destination. Identify **which step** failed: registration lookup, signature verification, issuer/destination, request correlation, session mapping, or IdP SLO support.

## 22. Safe Deployment Runbook

1. **Lock down SP–IdP contract:** Entity IDs, SLO request/response URLs, bindings, signing algorithms, and trusted certificates.
2. **Verify metadata:** IdP has SingleLogoutService; SP metadata publishes exact SP endpoint.
3. **Manage secrets:** SP PKCS#8 private key has access/rotation procedures; only the public cert is shared with partners.
4. **Enable SLO for your Spring version:** SAML2 SP dependency, `RelyingPartyRegistrationRepository`, and `saml2Logout`.
5. **Preserve SAML principal context:** keep NameID/SessionIndex/accessor when customizing login mapping.
6. **Test RP-initiated:** POST logout with CSRF; SP signs Request; IdP returns Response; SP verifies/correlates/checks status.
7. **Test AP-initiated:** IdP signs Request; SP verifies before logout; SP signs Response back to the right IdP.
8. **Negative tests:** bad signature/key/issuer/destination/response request ID/session/replay/algorithms.
9. **Check reverse proxy:** public HTTPS URL, trusted forwarded headers, query string preservation.
10. **Monitor:** counts of SLO success/failure/partial, signature and destination errors, IdP timeouts.
11. **Rollback:** keep old config/certs for an approved overlap window and a procedure to switch endpoints.
12. **Report outcomes accurately:** local logout differs from network-wide SLO; never claim unconfirmed sessions ended.

## 23. Most Common Misconceptions — Quick Q&A

**Q:** Is a validly signed LogoutRequest enough for the SP to log a user out?

**A:** No. You also need a trusted issuer, matching Destination, right NameID/session, lifetime/replay policy, and profile conditions. A signature does not by itself choose which user gets logged out.

**Q:** Must the SP use the IdP's certificate to sign LogoutResponse?

**A:** No. The SP uses the **SP private key** to sign; the IdP uses the **SP public certificate** to verify. The IdP certificate is used by the SP to verify messages sent by the IdP.

**Q:** Why is a LogoutRequest with `Destination=https://other-sp.example.com/slo` rejected even when IdP B's signature is valid?

**A:** The message was signed **for another destination**. SP A must not execute it as an instruction meant for itself.

**Q:** Can the certificate from the LogoutRequest XML itself be used to verify the signature?

**A:** That certificate cannot automatically serve as a trust anchor. It must match the pre-registered IdP verification credentials.

**Q:** Does `Recipient` appear in every LogoutRequest?

**A:** No. `Recipient` typically appears on bearer `SubjectConfirmationData` of a login Assertion. For logout, check `Destination` and matching SLO metadata/endpoints.

**Q:** Does LogoutResponse `StatusCode=Success` prove global SLO finished?

**A:** Only after verifying signature, issuer, destination, correlation, and understanding response scope. Even when the IdP reports success, the app must report per contract and never assume every out-of-scope system ended its session.

**Q:** Should we build XML Digital Signatures manually to "stay in control"?

**A:** No. XML signatures and Redirect signatures have complex rules that easily lead to signature wrapping or canonicalization bugs. Prefer Spring Security/OpenSAML.

## 24. Official References

1. [Spring Security — Performing Single Logout](https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html): minimal configuration, RP/AP-initiated, request/response filters/resolvers/validators, endpoints, and request repository.
2. [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): authentication chain, registration, and SSO/SLO distinction; verify URLs against your version.
3. [Spring Security API — Saml2LogoutRequestFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/authentication/logout/Saml2LogoutRequestFilter.html): filter receiving IdP-initiated requests.
4. [Spring Security API — Saml2LogoutRequestRepository](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/authentication/logout/Saml2LogoutRequestRepository.html): storing and retrieving LogoutRequests for correlation.
5. [Spring Security API — Saml2LogoutRequestResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/authentication/logout/Saml2LogoutRequestResolver.html): creating, signing, and serializing requests sent to the IdP.
6. [Spring Security API — RelyingPartyRegistration.Builder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/registration/RelyingPartyRegistration.Builder.html): SP SLO service locations/bindings and signing credentials.
7. [Spring Security API — AssertingPartyMetadata.Builder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/registration/AssertingPartyMetadata.Builder.html): IdP SLO request/response locations, bindings, and verification certificates.
8. [OASIS — SAML 2.0 Technical Overview](https://docs.oasis-open.org/security/saml/Post2.0/sstc-saml-tech-overview-2.0.html): Single Logout flow and roles of signing, NameID, and SessionIndex.
9. [OASIS — SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): LogoutRequest/LogoutResponse, `Destination`, `InResponseTo`, `StatusCode`, and request lifetimes.
10. [OASIS — SAML 2.0 Bindings](https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf): HTTP-Redirect signatures (`SigAlg`, `Signature`) and POST XML Signatures.

**Final takeaway:** **signing** protects integrity and proves the sender holds the private key; **verifying with a trusted certificate** binds the message to the exact SP/IdP; **checking Destination** and `InResponseTo` ensures the message targets the right endpoint and transaction. In SAML2 SLO, these three layers must work alongside issuer, NameID/SessionIndex, timestamps/replay, and logout status; never drop one layer to work around an integration error.