# Customizing the Login Start URL and Assertion Consumer Service in Spring Security SAML2

The **login start URL** and **Assertion Consumer Service (ACS)** are two endpoints on the Service Provider (SP) side, handling two different halves of SAML 2.0 Web Browser SSO. One endpoint **generates an AuthnRequest to send the user to the Identity Provider (IdP)**; the other **receives the SAMLResponse from the IdP via the browser for verification and Authentication creation**. Changing paths must be done properly across Spring Security, `RelyingPartyRegistration` details, SP metadata, and IdP configuration.

This lesson belongs to the **AuthnRequest Customization** group of Spring Security federation. It explains how to identify the default endpoints, customize both endpoints via the DSL, bind the ACS to the SAML protocol, test in a proxied environment, and handle errors. Addresses with `.example` domains are illustrative only, not real servers.

## 1. Seeing Each Address's Role Clearly

Suppose Portal A at `https://portal.example.com` trusts partner IdP B, with `registrationId = partner-b`.

| Component | Illustrative Address | Processing Party and Meaning |
| --- | --- | --- |
| **SP start/login initiation** | `https://portal.example.com/saml2/authenticate/partner-b` | SP: receives the command to start SSO, creates AuthnRequest |
| **IdP SingleSignOnService** | `https://login.partner-b.example/sso` | IdP: receives AuthnRequest from the SP |
| **SP Assertion Consumer Service** | `https://portal.example.com/login/saml2/sso/partner-b` | SP: receives SAMLResponse, verifies identity |
| **SP metadata HTTP endpoint** | `https://portal.example.com/saml2/metadata/partner-b` | Provides XML describing the SP to IdP administrators |
| **SP Entity ID** | `https://portal.example.com/sp/partner-b` | SAML identifier of the SP; used by the IdP to restrict audience |

These are **five distinct addresses/identifiers with different responsibilities**. The SP Entity ID is a protocol identifier string, not necessarily an HTTP endpoint. The IdP SSO URL is where the SP sends the AuthnRequest, **not** the URL where the browser sends the SAMLResponse back. The SP metadata GET endpoint is not the ACS POST endpoint.

**Spring Security uses two main filters:**

- `Saml2WebSsoAuthenticationRequestFilter`: generates, stores, and issues the SAML AuthnRequest at the start endpoint.
- `Saml2WebSsoAuthenticationFilter`: receives the SAMLResponse at the ACS, creates a `Saml2AuthenticationToken` via a converter, and passes it to an authentication provider for verification.

`registrationId` is the lookup key for the **SP–IdP pair** configuration in `RelyingPartyRegistrationRepository`; it is not an email, an IdP issuer, or a tenant permission.

## 2. Web Browser SSO Flow Before Customization

~~~mermaid
sequenceDiagram
    participant U as Browser
    participant SP as Portal A / Spring Security
    participant IdP as Identity Provider B
    U->>SP: GET /private
    SP-->>U: Redirect to start URL
    U->>SP: GET /saml2/authenticate/partner-b
    SP->>SP: Create AuthnRequest, save request ID and state
    SP-->>U: Redirect or form POST to IdP SSO URL
    U->>IdP: SAMLRequest + RelayState if present
    IdP->>IdP: Authenticate, validate SP parameters
    IdP-->>U: HTML form containing SAMLResponse
    U->>SP: POST /login/saml2/sso/partner-b
    SP->>SP: Verify Response/Assertion and permissions
    SP-->>U: Authenticated session or error
~~~

**Default routes worth remembering in modern Spring Security:**

~~~text
GET /saml2/authenticate/{registrationId}
GET /saml2/authenticate?registrationId={registrationId}
POST /login/saml2/sso/{registrationId}
POST /login/saml2/sso          (may be used in some flows/resolvers)
GET /saml2/metadata/{registrationId}   (when metadata is enabled)
~~~

The Start URL belongs to the **SP**, but it is the starting point that sends the browser **to the IdP**, not the destination for the SAMLResponse. The IdP typically returns the SAMLResponse via HTTP-POST binding to the ACS; the SP can send the AuthnRequest using HTTP-Redirect or HTTP-POST binding by agreement.

In SP-initiated SSO, the IdP may read `AssertionConsumerServiceURL` in the AuthnRequest or use the pre-registered ACS. Either way, the IdP must send the Response to an authorized ACS, not an arbitrary URL proposed externally.

## 3. Changing Start and Changing ACS Are Two Different Changes

Target state after customization:

~~~text
NEW START:
https://portal.example.com/federation/saml/start/partner-b

NEW ACS:
https://portal.example.com/federation/saml/acs/partner-b

SP ENTITY ID UNCHANGED:
https://portal.example.com/sp/partner-b

IdP SSO URL UNCHANGED:
https://login.partner-b.example/sso
~~~

| Configuration or Artifact | Change Start Only | Change ACS |
| --- | --- | --- |
| `saml2Login.authenticationRequestUriQuery(...)` | **Change** | Not required |
| Link on login page / redirect entry point | **Change** | Usually not required |
| `saml2Login.loginProcessingUrl(...)` | Keep unchanged | **Change** |
| `RelyingPartyRegistration.assertionConsumerServiceLocation` | Keep unchanged | **Change** |
| Spring Boot `acs.location` if using YAML | Keep unchanged | **Change** |
| SAML AuthnRequest ACS field if emitted | Keep unchanged | **Must reflect new ACS** |
| SP metadata `AssertionConsumerService Location` | Keep unchanged | **Must reflect new ACS** |
| ACS/Reply URL stored at IdP | Keep unchanged | **Must sync with IdP** |
| `RelyingPartyRegistration.entityId` | Keep unchanged unless changing SP identity | Do not change automatically |
| SAML E2E and negative tests | Needed | **Mandatory before rollout** |

Therefore, it is **not enough** to change only `loginProcessingUrl` while forgetting `acs.location` or the IdP Reply URL. In that case, the backend may be listening for POST at the new address while the IdP still sends to the old path. Conversely, if you change only the metadata ACS while the filter still listens on the old path, a browser POST to the new address will not be authenticated by the filter.

## 4. Step 1: Customize the SSO Start Endpoint

As of Spring Security 7.1, `Saml2WebSsoAuthenticationRequestFilter` by default accepts `/saml2/authenticate/{registrationId}` and `/saml2/authenticate?registrationId={registrationId}`.

The `Saml2LoginConfigurer.authenticationRequestUriQuery(String)` API, available since **Spring Security 6.0**, allows configuring the URI and query parameters of the AuthnRequest generation endpoint. With a path variable:

~~~java
.saml2Login(saml -> saml
    .authenticationRequestUriQuery(
        "/federation/saml/start/{registrationId}"))
~~~

When registration is `partner-b`:

~~~text
GET https://portal.example.com/federation/saml/start/partner-b
~~~

If the enterprise requires query form, you can configure per the API:

~~~java
.saml2Login(saml -> saml
    .authenticationRequestUriQuery(
        "/federation/saml/start?registrationId={registrationId}"))
~~~

If you change the parameter name or build a custom resolver, ensure the resolver actually understands it and **only selects a server-approved registration**. Do not let a user pass an arbitrary IdP metadata URL and treat it as a valid registration.

**Update the SSO initiation links.** An old UI has:

~~~html
<a href="/saml2/authenticate/partner-b">Sign in with B</a>
~~~

After the change, it needs:

~~~html
<a href="/federation/saml/start/partner-b">Sign in with B</a>
~~~

If `loginPage("/login")` is configured, verify that the page displays the updated link/IdP picker. `loginPage` specifies the **login selection page**, whereas `authenticationRequestUriQuery` sets the **AuthnRequest generation processing endpoint**. Changing the route without updating the login page, bookmarks, portal links, or redirect entry point will cause browsers to keep hitting the old path.

**Do not confuse URL with request contents.** If you need `ForceAuthn`, `NameIDPolicy`, `RequestedAuthnContext`, or a different signing algorithm, that is the job of customizing `Saml2AuthenticationRequestResolver`/OpenSAML, not the effect of `authenticationRequestUriQuery`.

## 5. Step 2: Change the ACS Handled by `Saml2WebSsoAuthenticationFilter`

Spring Security SAML2 by default processes SAMLResponse at `/login/saml2/sso/{registrationId}`. To use a new path, configure `Saml2LoginConfigurer.loginProcessingUrl(String)`:

~~~java
.saml2Login(saml -> saml
    .loginProcessingUrl(
        "/federation/saml/acs/{registrationId}"))
~~~

The IdP must send an HTTP POST to:

~~~text
POST https://portal.example.com/federation/saml/acs/partner-b
Content-Type: application/x-www-form-urlencoded

SAMLResponse=<base64-encoded-saml-response>
~~~

The HTTP example above is **illustrative**, not a valid SAMLResponse, and real tokens/assertions should never be logged. When processing, the filter creates an authentication request, finds the matching `RelyingPartyRegistration`, validates the XML signature/conditions via the provider, and returns a session or error.

**Keeping `{registrationId}` in the ACS path is an easy-to-control choice** when there are multiple IdPs. The Javadoc warns that when changing `loginProcessingUrl`, consider `authenticationConverter(...)`, because the default converter relies on `{registrationId}` in the URL, the saved AuthnRequest, or the Response's issuer to identify the registration. Changing to a path without the ID may require a custom lookup strategy.

A shared ACS such as `/federation/saml/acs` is feasible in certain designs, but you must clearly decide how to select the IdP/registration, check `InResponseTo`, and enforce trust boundaries. Do not select an IdP based on an email or browser-supplied query parameter, nor treat an **unverified** issuer declared in XML as a trusted source.

**Do not write a controller that Base64-decodes manually** and creates a session. This is an authentication protocol ingestion point and requires a full SAML processor.

## 6. Step 3: Change `assertionConsumerServiceLocation` in the Registration

`loginProcessingUrl` is the HTTP listening endpoint of the filter. `RelyingPartyRegistration.assertionConsumerServiceLocation` is the **ACS address published by the SP in the protocol**, including metadata and the AuthnRequest when applicable.

If using Spring Boot with the `acs.location` property:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-b:
            entity-id: "https://portal.example.com/sp/partner-b"
            acs:
              location: "https://portal.example.com/federation/saml/acs/partner-b"
            assertingparty:
              metadata-uri: "classpath:saml/partner-b-idp-metadata.xml"
~~~

The IdP metadata file `saml/partner-b-idp-metadata.xml` must actually exist and be verified via a trusted channel. Certificates, signing credentials, encryption/decryption, and per-IdP signature requirements must be configured appropriately for the environment. Properties change across some Spring Boot lines; **check the Boot version in use** before copying.

Explanation:

- `entity-id` is the **SP Entity ID**; do not change it merely because the ACS changed.
- `acs.location` is the **URL to which the IdP must POST the Response**.
- `assertingparty.metadata-uri` is the **IdP metadata source** used by the SP, not the ACS or start endpoint address.

With a Java-constructed repository, you can set the ACS on the builder. **This fragment requires a Spring project and real metadata, not a standalone program**:

~~~java
RelyingPartyRegistration partnerB = RelyingPartyRegistrations
    .fromMetadataLocation("classpath:saml/partner-b-idp-metadata.xml")
    .registrationId("partner-b")
    .entityId("https://portal.example.com/sp/partner-b")
    .assertionConsumerServiceLocation(
        "https://portal.example.com/federation/saml/acs/partner-b")
    .build();
~~~

Keep public URLs consistent, especially behind a reverse proxy. Several URI fields support placeholders `{baseUrl}`, `{registrationId}`, `{baseScheme}`, `{baseHost}`, `{basePort}`:

~~~text
ACS template:
{baseUrl}/federation/saml/acs/{registrationId}

If baseUrl = https://portal.example.com,
registrationId = partner-b:

ACS =
https://portal.example.com/federation/saml/acs/partner-b
~~~

When multiple proxies or context paths are involved, an explicit public URL is often easier to verify than letting runtime guess `{baseUrl}` from potentially inaccurate headers.

## 7. JavaConfig Example Combining Start and ACS (Spring Security 6.1+/7.x)

Assuming the Spring Boot project already includes `spring-security-saml2-service-provider` and has a valid `RelyingPartyRegistrationRepository`, create `SamlEndpointsSecurityConfiguration.java`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlEndpointsSecurityConfiguration {

    @Bean
    SecurityFilterChain samlSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .saml2Login(saml -> saml
                .authenticationRequestUriQuery(
                    "/federation/saml/start/{registrationId}")
                .loginProcessingUrl(
                    "/federation/saml/acs/{registrationId}"))
            .saml2Metadata(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**Version scope of the example:** `authenticationRequestUriQuery` has existed since Spring Security 6.0; `saml2Metadata(...)` has existed since 6.1. Thus, this combined code targets Spring Security **6.1+ and 7.x** when modules are managed compatibly by the BOM. It requires a Spring project, OpenSAML, a real/test IdP, certificates, and registrations. The configuration file cannot be run standalone with `javac`.

Expected outcome at the **routing** level:

~~~text
GET  /federation/saml/start/partner-b
   -> Saml2WebSsoAuthenticationRequestFilter
   -> AuthnRequest sent to IdP B

POST /federation/saml/acs/partner-b
   -> Saml2WebSsoAuthenticationFilter
   -> Verify SAMLResponse

GET  /saml2/metadata/partner-b
   -> SP metadata published when DSL metadata is enabled
~~~

If the application has multiple `SecurityFilterChain` beans using `securityMatcher`, both start and ACS must fall under the chain with SAML enabled. Another chain capturing the path will produce 404, 302, or 403 even if the configuration above looks right.

**Do not mark complete just because it compiles**: you still need to update `acs.location`, the IdP Reply/ACS URL, and test the real browser flow.

## 8. AuthnRequest and SAMLResponse Must Be Consistent

An illustrative `AuthnRequest` after changing the ACS:

~~~xml
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_request-example"
    Version="2.0"
    IssueInstant="2026-11-07T03:00:00Z"
    Destination="https://login.partner-b.example/sso"
    AssertionConsumerServiceURL="https://portal.example.com/federation/saml/acs/partner-b"
    ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST">
    <saml:Issuer>https://portal.example.com/sp/partner-b</saml:Issuer>
</samlp:AuthnRequest>
~~~

This is **learning XML**, without a valid signature, and cannot be sent as a production message. Each field shows a role:

- `Destination` is the **IdP SSO URL**.
- `AssertionConsumerServiceURL` is the **SP ACS**; distinct from the start endpoint.
- `Issuer` is the **SP Entity ID**.
- `ID` helps correlate `InResponseTo` when the IdP returns the Response.
- `ProtocolBinding` describes the binding on which the SP expects the Response, in this example HTTP-POST.

Do not assume every version/IdP includes all illustrated attributes in the request. Some systems only use the ACS registered in IdP metadata or use an ACS index; verify in practice.

Upon receiving the Response, Spring must verify:

1. **Issuer:** IdP Entity ID matches the trusted registration.
2. **Signature:** matches the IdP certificate and the XML element has a valid signature.
3. **Audience:** assertion is intended for the **SP Entity ID**, not the start URL.
4. **Destination/Recipient:** the message and subject confirmation target the **current ACS**.
5. **InResponseTo:** matches an SP-issued request under SP-initiated login policy.
6. **Conditions/time:** `NotBefore`, `NotOnOrAfter`, clock skew, and replay.
7. **Subject/identity mapping:** principal is mapped to the right local user.
8. **Authorization:** tenant, object, and business permissions are checked separately.

**Do not disable Destination/Recipient/Audience validation just to bypass URL change errors.** Those errors usually indicate out-of-sync configuration between the two parties or a proxy generating the wrong public URL.

## 9. Step 4: Update SP Metadata and IdP Configuration

When `saml2Metadata(...)` is enabled, fetch SP metadata from the actual public domain:

~~~bash
curl -i "https://portal.example.com/saml2/metadata/partner-b"
~~~

In the XML, inspect `EntityDescriptor/@entityID`, `AssertionConsumerService/@Location`, binding, and certificate, for example this illustrative fragment:

~~~xml
<md:AssertionConsumerService
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
    Location="https://portal.example.com/federation/saml/acs/partner-b"
    index="1" />
~~~

At the IdP, administrators may call this field **ACS URL**, **Reply URL**, **Assertion Consumer URL**, or assertion receiving endpoint. Register the new URL with the exact scheme, host, path, port, trailing slash, and binding.

**Do not change the SP Entity ID unless you genuinely intend to change the SP identity.** An Entity ID change can force the IdP to update audience and break remaining trust contracts. When moving only the ACS, keep the Entity ID/certificates stable if policy allows.

If the IdP polls SP metadata from a URL periodically, know its cache/refresh interval. Some IdPs keep a static snapshot until an administrator updates it. Thus, updating SP metadata **does not guarantee** the IdP automatically accepts the new ACS immediately.

If the IdP requires signed AuthnRequests, the SP must have the corresponding signing key. Changing the ACS does not remove signing requirements. Do not include the private key in SP metadata: metadata only publishes the public certificate.

## 10. Different Configurations with Multiple IdPs or Multiple Tenants

One portal may have registrations:

~~~text
corp      -> Internal IdP
partner-b -> Company B's IdP
partner-c -> Company C's IdP

START:
  /federation/saml/start/corp
  /federation/saml/start/partner-b
  /federation/saml/start/partner-c

ACS:
  /federation/saml/acs/corp
  /federation/saml/acs/partner-b
  /federation/saml/acs/partner-c
~~~

**This helps with routing, not automatic tenant isolation.** The server must verify the signer/issuer matches the registration, map the internal user per IdP and durable identifier, and then enforce data authorization per tenant. If B and C both use `alice` or identical emails, do not merge accounts automatically.

When choosing an ACS **without registrationId**:

~~~text
POST /federation/saml/acs
~~~

the framework can look up the registration via the saved AuthnRequest or the issuer in the Response. However, with multi-IdP, IdP-initiated flows, and custom resolvers, you must carefully evaluate trust policy, anti-replay, and security context. Unless specifically needed, **keeping `{registrationId}`** makes inspection, error tracing, and coordination with each IdP easier.

## 11. Session, RelayState, and Request Correlation Must Not Be Bypassed

`Saml2WebSsoAuthenticationRequestFilter` saves the `AuthnRequest` via `Saml2AuthenticationRequestRepository`; by default on modern releases this may use `HttpSessionSaml2AuthenticationRequestRepository`.

When the browser posts the SAMLResponse back to the ACS, `Saml2WebSsoAuthenticationFilter` and `Saml2AuthenticationTokenConverter` can use the saved request to resolve registration/correlation. When changing start/ACS:

- Ensure the request ID and state are saved before going to the IdP.
- The browser needs to retain the session/cookie across redirects and POSTs from the IdP domain.
- `InResponseTo` must satisfy the correlation policy for SP-initiated flows.
- `RelayState` must not be used as standalone proof of identity/tenant.
- Do not let the browser supply an arbitrary issuer URL and select a registration outside an allowlist.
- Do not fix lost-session errors by defaulting to accepting all unsolicited SAMLResponses.
- If using Redis/distributed cache for the request repository, bind the request to the right session/browser, TTL, and anti-replay.

Spring Security documentation warns that looking up an AuthnRequest solely by `InResponseTo` or `RelayState` in a shared cache can lose the login fixation protection inherent in session binding. Do not pick a cache solution solely for routing convenience.

## 12. CSRF and ACS POST from the IdP

A SAML Response to the ACS is typically a **cross-site POST** because the browser arrives from the IdP's domain. Spring Security has built-in handling for the SAML Web SSO flow, but when changing `loginProcessingUrl` you must verify the matcher/filter/CSRF exemption against the running version.

**Do not fix a 403 at the ACS by disabling CSRF application-wide:**

~~~java
// This is not a default fix for ACS change errors
http.csrf(csrf -> csrf.disable());
~~~

Safer approach:

1. Ensure `POST /federation/saml/acs/{registrationId}` actually enters the SAML filter.
2. Verify the CSRF exemption for the ACS in the current SAML configuration.
3. If manual CSRF configuration is needed, restrict it **strictly to the ACS path/method**.
4. Keep CSRF protection for business forms/POSTs that still require it.
5. Check `SameSite` and `Secure` cookie attributes so the session can return after the IdP.
6. Distinguish 403 caused by CSRF from 403 caused by authorization, or SAML validation errors.

Maintain HTTPS/TLS and do not write raw SAMLResponse, cookies, or private keys to production debug logs.

## 13. Reverse Proxy, Public URL, and Context Path

An application may run at `http://saml-service:8080`, while users/IdP see `https://portal.example.com/app`. If Spring computes `{baseUrl}` from the internal host, the AuthnRequest or metadata may advertise ACS `http://saml-service:8080/...` and be rejected by the IdP.

Procedure:

1. Establish the real **public base URL**: scheme, hostname, port, and context path.
2. Use an explicit public ACS URL when proxies are complex.
3. Verify rewrite paths from public `/app/federation/saml/acs/...` to the corresponding internal Spring handler.
4. Accept `Forwarded`/`X-Forwarded-*` only from managed proxies; do not trust forged client headers.
5. Ensure the proxy forwards the **HTTP POST and SAMLResponse body**, without rewriting to GET.
6. Verify cookies/sessions remain intact when requests go through the IdP and return.
7. Fetch SP metadata via the public URL and compare with the Reply URL at the IdP.
8. Test login on the public hostname, not just `localhost`.

A start URL change does not require changing the public ACS if the old ACS was already right. Conversely, changing the ACS requires re-checking the entire public path to the backend.

## 14. Standalone Java 17: Checking the Endpoint Contract

The following program illustrates **URL mapping logic**, does not issue AuthnRequests, does not verify signatures, has no Spring Security, and does not prove login succeeds. Use it to practice distinguishing start from ACS and checking whether both sides agree on the ACS.

Create file `SamlEndpointContractDemo.java`:

~~~java
import java.util.Map;

public class SamlEndpointContractDemo {
    record Paths(String start, String acs) {
        String startUrl(String base, String id) {
            return base + start.replace("{registrationId}", id);
        }
        String acsUrl(String base, String id) {
            return base + acs.replace("{registrationId}", id);
        }
    }

    public static void main(String[] args) {
        String base = "https://portal.example.com";
        String id = "partner-b";
        Paths paths = new Paths(
                "/federation/saml/start/{registrationId}",
                "/federation/saml/acs/{registrationId}");

        Map<String, String> registeredAtIdP = Map.of(
                id, "https://portal.example.com/federation/saml/acs/partner-b");

        String start = paths.startUrl(base, id);
        String acs = paths.acsUrl(base, id);
        String oldAcs = base + "/login/saml2/sso/" + id;

        System.out.println("Start: " + start);
        System.out.println("ACS: " + acs);
        System.out.println("IdP agrees: "
                + acs.equals(registeredAtIdP.get(id)));
        System.out.println("Old ACS agrees: "
                + oldAcs.equals(registeredAtIdP.get(id)));
        System.out.println("Unknown registration: "
                + registeredAtIdP.containsKey("partner-c"));
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac SamlEndpointContractDemo.java
java SamlEndpointContractDemo
~~~

Exact stdout:

~~~text
Start: https://portal.example.com/federation/saml/start/partner-b
ACS: https://portal.example.com/federation/saml/acs/partner-b
IdP agrees: true
Old ACS agrees: false
Unknown registration: false
~~~

Meaning:

- **Start** is the URL the browser visits to ask the SP to generate an AuthnRequest.
- **ACS** is where the IdP needs to send the Response.
- **IdP agrees: true** means the address in the example matches as a **string**.
- **Old ACS agrees: false** simulates the old URL not matching the new configuration.
- **Unknown registration: false** shows an undeclared partner is not in the list.

This is only a **pre-integration URL contract check**; it does not test SAML metadata, trust anchors, certificates, HTTP, sessions, or authorization policies.

## 15. End-to-End Integration Test Suite

| Scenario | Input / Action | Expectation |
| --- | --- | --- |
| New start | GET `/federation/saml/start/partner-b` | Generates AuthnRequest for the right IdP |
| Old start | GET `/saml2/authenticate/partner-b` | Behavior matches migration policy |
| Unknown registration | GET `/federation/saml/start/unknown` | Does not automatically fall back to another IdP |
| SSO Destination | Inspect AuthnRequest in test lab | Points to IdP SSO URL, not ACS |
| ACS in AuthnRequest | Check `AssertionConsumerServiceURL` if emitted | Matches new ACS accepted by IdP |
| SP metadata | GET metadata by ID | New ACS, stable Entity ID, right cert |
| IdP config | Check B's Reply/ACS URL | Matches new public ACS |
| Browser SSO | Log in test account via IdP B | Browser POSTs to new ACS, valid session |
| Wrong issuer | Response from IdP C at B's route | Rejected |
| Wrong destination | SAMLResponse targeting old ACS or elsewhere | Rejected |
| Wrong recipient | Subject confirmation targeting another endpoint | Rejected |
| Wrong audience | Assertion intended for another SP | Rejected |
| Expired assertion | `NotOnOrAfter` has passed | Rejected |
| Request correlation | Wrong `InResponseTo`, or lost session | Rejected per policy |
| Replay | Resubmit already-used assertion | Does not create unauthorized session |
| IdP-initiated | No prior AuthnRequest | Accepted only under dedicated policy |
| CSRF | ACS POST and business POST | ACS works; other forms remain protected |
| Authorization | User B tries to view C's data | 403 even after successful login |
| Proxy rewrite | Public URL has context prefix | Filter/ACS/metadata align |
| Multi-node | Return hits a different node | Request repository/session behaves as designed |

Manual checks in staging (where example URLs have been replaced with real URLs):

~~~bash
curl -i "https://portal.example.com/federation/saml/start/partner-b"
curl -i "https://portal.example.com/saml2/metadata/partner-b"
~~~

Start may return 302 to the IdP or an HTML form if using POST binding; metadata returns XML when properly enabled. **There is no fixed stdout** for these commands. Do not use `.example` URLs as production URLs. Use a test IdP and a real browser session to verify the full response.

**PASS only when all three aspects align:** Spring handles start and ACS properly; the SAML protocol has valid issuer/audience/recipient/correlation; the application enforces tenant permissions properly.

## 16. Common Errors Table

| Symptom | Common Reason | Resolution |
| --- | --- | --- |
| Clicking login still hits old path | Link on loginPage/entry point not updated | Update links and test in browser |
| New start returns 404 | Wrong matcher/filter chain or `authenticationRequestUriQuery` not configured | Check SecurityFilterChain and URL |
| Browser does not reach IdP | Wrong SSO URL, IdP signing/binding, or request resolver | Check `RelyingPartyRegistration` and AuthnRequest |
| IdP reports unregistered ACS | New ACS not yet in IdP config | Update Reply URL/metadata |
| IdP still POSTs to old ACS | Stale metadata/config snapshot cache | Sync IdP and cutover plan |
| POST to new ACS returns 404/405 | Filter does not match path/method, bad proxy rewrite | Check `loginProcessingUrl` and POST routing |
| POST to ACS returns 403 | CSRF rule, session, or other authentication/authorization | Trace exact filter and policy; do not disable CSRF globally |
| Invalid Destination/Recipient | Public ACS does not match verified endpoint | Fix ACS/IdP/proxy; do not disable validation |
| Invalid Audience | SP Entity ID changed or IdP issued for another SP | Keep/sync the right Entity ID |
| Unknown registration | ID missing from repository or converter lookup failed | Check repository/resolver and saved request |
| InResponseTo unknown | Request not saved or session/cookie lost | Check request repo, SameSite, multi-node |
| Signature mismatch | Wrong cert/rotation/signing policy | Sync trust anchors; do not skip verification |
| Login succeeds but 403 on resource | Missing role/membership/object authorization | Fix business policy, not an ACS bug |

Diagnostics should log sanitized error codes, verified registrationId, and necessary operational context. Do not log raw SAML assertions or private keys.

## 17. Differences Across Spring Security Versions

| Version Line | Notes When Customizing |
| --- | --- |
| **Spring Security 5.2–5.6** | SAML2 login exists, but setting custom AuthnRequest endpoints requires version-appropriate filter/resolver APIs; do not copy modern DSL code |
| **Spring Security 5.7–5.8** | Has `authenticationRequestResolver` and customization APIs; uses Servlet `javax.servlet` on 5.x |
| **Spring Security 6.0** | `authenticationRequestUriQuery` introduced in 6.0; migrated to `jakarta.servlet` |
| **Spring Security 6.1–6.5** | Has `saml2Metadata(...)` to publish SP metadata; `SecurityFilterChain` is the standard configuration style |
| **Spring Security 7.x** | Continues `authenticationRequestUriQuery` and `loginProcessingUrl`; OpenSAML provider in newer branches differs from old examples |

When upgrading versions, do not look only at what `pom.xml` declares—inspect actual **resolved dependencies**. For example:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-security-saml2-service-provider
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-security-config
~~~

Or Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.security
~~~

A successful build **does not prove SSO works**. Always run integration tests with a real IdP and public URL.

## 18. Pre-Production Deployment Checklist

- [ ] Identify both start and ACS endpoints correctly, along with approved public URLs.
- [ ] Select an existing `registrationId`; do not dynamically construct IdPs from external parameters.
- [ ] Update `authenticationRequestUriQuery` and login page/entry points when changing start.
- [ ] Update `loginProcessingUrl` and `assertionConsumerServiceLocation` when changing ACS.
- [ ] Verify `RelyingPartyRegistration.entityId` was not unintentionally changed.
- [ ] Update SP metadata and register the new ACS with the IdP.
- [ ] Verify signing/verification certificates, bindings, and SSO endpoints.
- [ ] Run within the same browser session, verifying AuthnRequest ID, RelayState, and `InResponseTo`.
- [ ] Negative tests for wrong issuer/audience/recipient/destination/expiration are all rejected.
- [ ] CSRF protects business forms; ACS POST works properly without disabling CSRF globally.
- [ ] Reverse proxy, HTTPS, context path, forwarded headers, and session cookies are configured securely.
- [ ] Even after valid login, enforce tenant, role, and object permissions.
- [ ] Have an IdP cutover plan, error monitoring, key rotation, and rollback plan.

## 19. Reference Documentation

- [Spring Security — Producing AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html): start endpoint, `authenticationRequestUriQuery`, request repository, and resolver.
- [Spring Security — Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): `loginProcessingUrl`, ACS, and authentication converter.
- [Spring Security — SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): Web Browser SSO model and URI patterns.
- [Javadoc — Saml2LoginConfigurer](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/configurers/saml2/Saml2LoginConfigurer.html): definitions of URL-changing APIs.
- [Javadoc — Saml2WebSsoAuthenticationFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/authentication/Saml2WebSsoAuthenticationFilter.html): SAMLResponse processing point.
- [Javadoc — RelyingPartyRegistration.Builder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/registration/RelyingPartyRegistration.Builder.html): `assertionConsumerServiceLocation`.
- [Spring Security — SAML2 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html): exporting SP metadata for import at the IdP.

**Conclusion:** changing the **start URL** changes where the user triggers the SP to create an AuthnRequest; changing the **ACS** changes where the IdP sends the SAMLResponse, so you must synchronize the **processing filter, RelyingPartyRegistration, SP metadata, and the IdP**. A system is only truly correct when the entire flow is tested and all checks for signature, issuer, audience, recipient, timestamps, session, and resource authorization remain intact.