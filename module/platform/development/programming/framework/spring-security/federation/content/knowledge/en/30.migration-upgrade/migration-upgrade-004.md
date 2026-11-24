# Reviewing Custom Validators and Converters During Version Upgrades

> **Module:** Spring Security – federation. **Group:** Migration and Upgrade. This Knowledge article is a standalone guide to inventorying, upgrading, testing, and operating **custom validators, converters, mappers, authentication providers, and resolvers** in Spring Security, especially across SAML 2.0, OIDC/OAuth2 Login, JWT Resource Server, LDAP, Kerberos, and CAS. The focus is not just fixing compile-time API errors, but preserving security boundaries when the framework changes how it verifies, converts identities, manages sessions, and enforces authorization.

## 1. Learning Outcomes and Non-Negotiable Principles

After this lesson, you should be able to:
1. Distinguish validation from conversion, authentication, and authorization.
2. Locate all custom extension points across source code, config, and dependencies.
3. Compare **default behaviors of old and new versions** rather than just renaming classes.
4. Understand the risks of customizing the OpenSAML authentication provider, SAML Response/Assertion validators, and converters.
5. Understand Spring Security 6→7 differences: OpenSAML 5, NameID/validation order, principal/assertion accessor, missing RelyingPartyRegistration, and SAML logout.
6. Verify OIDC UserService/GrantedAuthoritiesMapper and JWT JwtDecoder/JwtAuthenticationConverter do not drop issuer, audience, lifetime, signature, or authority scope checks.
7. Design negative security fixtures to prove **forged inputs are still rejected** after the upgrade.
8. Detect regressions in tenant mapping, role prefixes, SecurityFilterChain, CSRF, sessions, cookies, and SSO callbacks.
9. Write Java 17 tests, measure observability, and prepare rollbacks and release gates.
10. Distinguish standalone example code from Spring framework fragments that require a project and dependencies.

**Core principle:** **Map principals and authorities only from an identity already proven by the framework using trusted credentials and the right protocol context.** If adding business validation, **preserve** mandatory built-in checks. Removing or replacing a validator is a security-model change requiring independent review.

## 2. Four Commonly Confused Layers of Responsibility

| Layer | Question | Typical Components |
|---|---|---|
| Parsing/decoding | Is HTTP/XML/JWT data read safely? | OpenSAML unmarshaller, JWT parser |
| Validation | Are signature, signer, issuer, audience, timestamps, and protocol context valid? | SAML validators, JwtDecoder, OAuth2TokenValidator |
| Conversion | How is verified data mapped to principal/authorities? | ResponseAuthenticationConverter, JwtAuthenticationConverter, GrantedAuthoritiesMapper |
| Authorization | Is the principal permitted to access this resource/action? | AuthorizationManager, @PreAuthorize, domain ACL |

JWT Resource Server example: `JwtDecoder` must verify token signature, issuer, and expiration; `JwtAuthenticationConverter` merely transforms verified claims into a `JwtAuthenticationToken` and authorities. The converter creating `ROLE_ADMIN` does not make the token come from a valid issuer.

SAML example: the OpenSAML provider verifies the Response/Assertion, trusted IdP certificate, and Conditions; the response converter creates principal/authorities. If the converter reads NameID from an unsigned XML element, the whole pipeline can become vulnerable to XML Signature Wrapping.

### 2.1. Trust Boundary Diagram

~~~text
Raw HTTP request / browser callback
       |
       v
Secure parser: SAML XML, OIDC code exchange, JWT bytes
       |
       v
Signing credential trust + cryptographic verification
       |
       v
Default protocol validators + approved custom validators
       |
       v
Validated identity and context
       |
       v
Custom converter / authorities mapper
       |
       v
Authentication (SecurityContext)
       |
       v
URL AuthorizationManager / method / tenant rules
       |
       v
Resource granted or denied
~~~

Replacing an entire AuthenticationProvider risks impacting both verification and conversion layers. Replacing only a GrantedAuthoritiesMapper usually scopes the impact to mapping, yet can still cause privilege escalation. **Know exactly whether a hook runs before or after validation in the target version**; never guess from API names.

## 3. Build an Inventory Before Upgrading

Record for every extension point:
- Module/protocol (SAML, OIDC, JWT, LDAP, CAS, Kerberos).
- Old dependency versions, target versions, BOM/JDK.
- Custom bean/class/filter chain/method.
- Input source: trusted result vs. raw untrusted request.
- Which default behavior was replaced vs. composed.
- Why the customization exists.
- Invariants that must hold.
- Acceptance/negative tests.
- Owner, review date, rollback, and audit impact.

Examples:

| Extension | Function | Common Regression |
|---|---|---|
| `ResponseValidator` | Validates SAML Response | Dropping Issuer, Destination, InResponseTo |
| `AssertionValidator` | Validates Conditions/Subject/Audience | Accepting expired/wrong-audience assertions |
| `ResponseAuthenticationConverter` | Creates SAML Authentication | Selecting wrong NameID, missing roles, breaking SLO support |
| `Saml2AuthenticationTokenConverter` | Resolves RelyingPartyRegistration | Selecting wrong IdP/tenant, missing registration loop |
| `OidcUserService` | Loads OIDC UserInfo and principal | Dropping delegate, wrong sub, losing validated claims |
| `GrantedAuthoritiesMapper` | Maps OIDC groups | Wrong role prefix, auto-granting Admin |
| `JwtDecoder` | Verifies JWT signature and claims | Dropping issuer/exp/nbf |
| `JwtGrantedAuthoritiesConverter` | Maps scopes/roles | Wrong claim name, delimiter, or prefix |
| `AuthorizationManager` | Enforces URL/method access | Filter ordering, tenant bypass |
| `UserDetailsService` | Local account mapping | Merging same email across IdPs |
| `SecurityContextRepository` | Session state | Callback succeeds yet subsequent requests are anonymous |

### 3.1. Finding Customizations in the Application Repo

These commands are guidance for developers to run on a checkout **of the exact project being upgraded**, not on other workspaces:

~~~bash
rg -n 'SecurityFilterChain|AuthenticationProvider|AuthenticationManager' src
rg -n 'OpenSaml4|OpenSaml5|ResponseValidator|AssertionValidator' src
rg -n 'ResponseAuthenticationConverter|Saml2AuthenticationTokenConverter' src
rg -n 'RelyingPartyRegistration|Saml2AuthenticatedPrincipal' src
rg -n 'JwtDecoder|JwtValidators|OAuth2TokenValidator' src
rg -n 'JwtAuthenticationConverter|JwtGrantedAuthoritiesConverter' src
rg -n 'OidcUserService|OAuth2UserService|GrantedAuthoritiesMapper' src
rg -n 'UserDetailsService|Kerberos|Cas|LdapAuthoritiesPopulator' src
rg -n 'requestMatchers|securityMatcher|PreAuthorize|AuthorizationManager' src
rg -n 'SecurityContextRepository|sessionManagement|requestCache|csrf' src
~~~

`rg` is ripgrep; use IDE structural search if unavailable. Note that customizations may be configured via XML/YAML, Java, Kotlin, factory methods, or Spring auto-configuration, not just class names.

### 3.2. Checking the Dependency Tree

With Maven:
~~~bash
mvn dependency:tree
mvn dependency:tree -Dincludes=org.springframework.security
~~~

With Gradle:
~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency spring-security-saml2-service-provider \
  --configuration runtimeClasspath
~~~

Spring Boot/Framework/Security docs and vendor adapters determine compatibility. Never mix OpenSAML 4 and 5 or multiple major versions of Apache Santuario/XML security JARs just to "turn the build green." With a Spring Boot major upgrade, also check Java/Jakarta Servlet/Jackson namespace changes and how SecurityContext is serialized.

## 4. Define the Security Contract Before Editing Code

Invariants should be expressed as testable assertions:

~~~text
SAML:
- Trusted IdP signature on expected Response/Assertion
- Signed object is the consumed authentication assertion
- Registration issuer + key + audience + ACS remain consistent
- Destination/Recipient/InResponseTo/Conditions validated
- No replay or unsigned attribute escalation
- Principal and group mapping come from validated objects

OIDC:
- State and nonce (when applicable) verified
- ID Token signed by approved provider and iss/aud/time valid
- UserInfo subject consistent with verified ID Token
- Local identity link by approved issuer + stable subject
- Only approved group/entitlement to business role mapping

JWT API:
- Signed by trusted issuer's JWK, approved algorithm
- iss/exp/nbf and required aud checked
- Claims never promoted to ROLE_ADMIN without policy
- Access token not confused with ID Token
- Invalid token denied, not silently anonymous-authenticated

Application:
- SecurityFilterChain routes preserved
- CSRF/session/context/cookie rules preserved
- Tenant/resource/method authorization enforced
- No secrets or raw credentials in telemetry
~~~

If baseline tests lack negative cases, add them **before** upgrading to compare old vs. new behavior. A successful login test only confirms the happy path; it does not prove a validator wasn't disabled.

### 4.1. Defining Success Across 3 Layers

1. **API compatibility:** builds and starts without errors.
2. **Functional compatibility:** login, logout, callbacks, sessions, and user mapping work.
3. **Security-semantic compatibility:** signature/issuer/audience/time/recipient/replay checks and permission denials remain intact or are intentionally tightened.

The third point is the most critical release gate.

## 5. SAML2 Changes When Upgrading Spring Security 6 → 7

**Version note:** Changes below are interpreted from the Spring Security 7.0 migration guide and SAML authentication docs. During implementation, pin your actual target version and check its migration notes/Javadoc; never assume an API stays identical across every release.

### 5.1. OpenSAML 5 Becomes the Baseline

The migration guide explicitly notes OpenSAML 4 is no longer supported upstream, so Spring Security moves to OpenSAML 5 components in the target release. Audit:
- Code directly instantiating `OpenSaml4AuthenticationProvider` and OpenSAML 4 types.
- APIs on `OpenSaml5AuthenticationProvider`.
- SAML XML object model and signature/decryption strategy APIs.
- Apache Santuario and XML parser dependencies.
- Key/certificate loading and `RelyingPartyRegistration`.
- Integration tests with real signed SAMLResponses.

Do not mechanically swap class names and assume equivalent behavior. Some releases change constructors, type parameters, provider defaults, principal representation, and validator ordering.

### 5.2. Validation Order and NameID

Migration documentation explains the shift in SAML Response and Assertion validation order:
- The older pipeline ran Response validations before Assertion validation, plus a NameID/name check in the Response phase.
- The newer path may validate assertions first and then Response validations, and **`ResponseValidator` no longer checks NameID presence by default under the old assumption**.
- A custom `ResponseAuthenticationConverter` requiring NameID must **fail closed itself** if NameID is missing, blank, or not an approved identity.
- If the business uses a stable attribute other than NameID, that field must belong to an Assertion whose signature and conditions were verified; never fall back to a request parameter or email header.

**Regression:**
~~~text
Old custom converter:
  framework rejected missing NameID before converter
New converter path:
  converter receives a validated structure with NameID absent
  code accidentally falls back to "admin" or empty localUserId
Outcome:
  identity confusion or wrong account linking
~~~

Test missing NameID, wrong format, missing Subject, blank stable ID, duplicates, and multiple Assertions. If login is permitted without a NameID, there must be a documented alternative identity contract.

### 5.3. Principal and SAML Assertion Accessor

The Spring Security 7 migration guide describes separating Assertion information from the principal to support Single Logout, introducing `Saml2ResponseAssertionAccessor` and `Saml2AssertionAuthentication` in the new API/model, while noting `Saml2AuthenticatedPrincipal` usage may be deprecated.

Review:
- `@AuthenticationPrincipal Saml2AuthenticatedPrincipal` in controllers.
- Deep casts of `authentication.getPrincipal()` to old classes.
- Custom converters calling `new Saml2Authentication(...)` directly.
- SLO code looking for assertion details on the principal.
- Session serialization/Redis Jackson classes.
- Unit tests asserting exact Authentication types.
- Whether the `UserDetailsService` bridge still returns the right stable subject.

Keep the business layer depending on a stable domain interface/abstraction rather than framework-specific implementation classes wherever possible. **Never convert a verified SAML Assertion back into another raw DOM to construct Authentication** just to keep an old API.

### 5.4. Relying-Party Registration Not Found

The migration guide notes that `Saml2WebSsoAuthenticationFilter` behavior on a matching URL when no `RelyingPartyRegistration` is found may change: the filter continues the chain instead of immediately throwing an exception, triggering `AuthenticationEntryPoint` and sometimes a redirect loop.

Test:
- Non-existent `registrationId`.
- Unexpected SAML issuer and multiple IdPs.
- ACS callback with/without `registrationId`.
- Missing pending AuthnRequest.
- Unknown IdP cert/metadata.
- Failure handler and redirect chain.

**Mandatory condition:** No authenticated SecurityContext is created if the relying party/IdP is untrusted. An HTTP status change after an upgrade is not necessarily a security regression, but a redirect loop or erroneous default-registration fallback can be a serious bug.

### 5.5. SAML LogoutRequest/LogoutResponse Behavior

Spring Security 7 migration docs note that handling an invalid LogoutRequest may return an error SAML LogoutResponse instead of some legacy HTTP 401 responses. Check:
- Custom SAML SLO request validators.
- `LogoutResponseResolver`.
- IdP/SP issuers and signing keys.
- Logout status/error semantics.
- Session invalidation/CSRF.
- Older tests that asserted HTTP 401 too strictly without checking SAML protocol semantics.

Never weaken LogoutRequest signature or SLO correlation checks to keep an old HTTP status. Separate **protocol correctness** from **error presentation**.

### 5.6. Note on SAMLResponse Over GET

The migration docs also mention future converter configuration when encountering a GET containing a SAMLResponse; ignoring GET will become the default in the subsequent release described. Therefore:
- Read the exact target release/Javadoc regarding `setShouldConvertGetRequests`.
- Do not claim every version 7 release already rejects GET by default.
- Prefer SAML HTTP-POST binding per contract.
- Never send SAMLResponse in query URLs, browser history, or logs.
- Add negative tests ensuring GET payloads do not log users in when deployment policy forbids it.

## 6. Custom ResponseValidator Must Preserve Default Checks

In SAML, a validly signed Response or Assertion alone is not sufficient to log in. Required profile properties include:
- Signature / trusted IdP signing key.
- Response Issuer and Assertion Issuer.
- Destination / ACS Location.
- AudienceRestriction = SP entityID.
- SubjectConfirmationData.Recipient / NotOnOrAfter.
- Conditions.NotBefore / NotOnOrAfter.
- InResponseTo for SP-initiated SSO.
- Status, AuthnStatement, and other profile requirements.
- Unique XML IDs and signed Reference target.
- Replay / correlation policy.
- Local tenant and account rules.

A custom validator checking only a business attribute cannot replace all the checks above.

### 6.1. Extension Pattern Instead of Full Replacement

The Spring Security SAML2 reference shows this pattern:
~~~java
// Spring fragment: actual interface and imports depend on target release.
ResponseValidator combined =
        ResponseValidator.withDefaults(myCustomValidator);
provider.setResponseValidator(combined);
~~~

The snippet above is **not standalone**; `myCustomValidator` and `provider` must be declared using the right OpenSAML5/Spring APIs. Meaning: add a policy check while keeping the default `ResponseValidator` checks. Apply the same principle to `AssertionValidator`, checking the builder/extension API of your target version.

**Mistake:** code calling `provider.setResponseValidator(customBusinessOnlyValidator)` without checking whether the setter replaces or composes. If default checks are replaced, a wrong Destination/Issuer could be accepted even with a valid XML signature.

### 6.2. InResponseTo Must Never Be Arbitrarily Dropped

In SP-initiated SSO:
- The SP issues an AuthnRequest ID and stores the request context.
- The IdP Response `InResponseTo` points to that exact request.
- `SubjectConfirmationData.InResponseTo` per profile must also correlate.
- A custom validator must never drop correlation because a test IdP sends the wrong request ID.

IdP-initiated/unsolicited flow, if permitted by the organization, is a separate mode without a pending AuthnRequest. It demands stringent issuer/signature/audience/recipient/replay/login-CSRF policies, not a reason to disable validation for SP-initiated flows.

### 6.3. Time/Skew During Upgrades

Spring providers expose APIs to configure `AssertionValidator` clock skew. Verify:
- Future `NotBefore` beyond skew → reject.
- Expired `NotOnOrAfter` → reject.
- Separate `SubjectConfirmationData` expiry.
- Request/Assertion `IssueInstant` consistency per policy.
- Replay of the same signed assertion while its signature is still valid.
- NTP synchronization between IdP and SP nodes.

Never set an enormous clock skew just so static test fixtures never expire.

### 6.4. XML Signature Wrapping

XSW occurs when the verifier validates signed object A while the converter extracts NameID/attributes from an unsigned object B. Regression tests:
- Signed Assertion A, unsigned Assertion B.
- Duplicate XML IDs.
- Unexpected nested Assertion.
- Signature Reference URI pointing to an object other than the consumed assertion.
- Multiple Assertions mixing signed/unsigned.
- Wrong KeyInfo trust.
- XML schema/namespace/DTD/XXE violations.

If the Response signature truly covers the Assertion subtree, modifying child content normally breaks the digest. Do not describe it as if an attacker can edit any signed XML while keeping the signature valid; XSW is **signed scope and selection confusion**. Use the OpenSAML validated object graph; never hunt for `NameID` using a global XPath.

## 7. Custom ResponseAuthenticationConverter: Source of Identity

A valid SAML converter may:
- Use persistent NameID or an approved stable attribute.
- Map verified attributes to a domain user.
- Call `UserDetailsService` to link a local account.
- Assign `GrantedAuthority` via an allowlist.
- Preserve the SAML assertion accessor needed for SLO.

But it must never:
- Read a raw `SAMLResponse` different from the verified object.
- Take user/role from a request header or query parameter.
- Assign default admin when NameID is null.
- Merge two IdPs on matching email.
- Use signed Assertion A to legitimize attributes from unsigned B.
- Skip local user active/tenant checks.
- Construct an authenticated token before provider verification.
- Drop default authentication factors/metadata required by the target version.

### 7.1. Converter Flow with Delegation

~~~text
Validated ResponseToken in trusted OpenSAML provider
            |
            v
Built-in ResponseAuthenticationConverter
            |
            v
Verified Authentication + attributes
            |
            v
Approved issuer/subject -> localUserId lookup
            |
            v
Approved group/entitlement -> app authorities
            |
            v
Authentication with preserved SAML protocol context
~~~

The conversion hook may be invoked at different stages across releases. Therefore, never assert "if the converter receives a Response, every property has already been checked" without reading the target version's source/API. Always keep the default converter and add business mapping in the official hook; never replace it with a custom parser.

### 7.2. Creating a Stable Domain Principal Contract

Conceptual model example:

~~~text
FederatedIdentity:
  protocol         = "SAML2" | "OIDC" | "KERBEROS" | "CAS"
  trustedIssuer    = canonical issuer / realm
  stableSubject    = verified subject identifier
  localUserId      = approved local identity link
  tenantId         = approved membership
  authorities      = allowlisted entitlements
~~~

This is a design schema, not a pre-compiled Java class. Goal: controllers/services do not cast directly to `Saml2AuthenticatedPrincipal` or an internal OpenSAML implementation just to fetch a user ID. Nor should all identities be flattened to email; stable subject and issuer scoping matter greatly.

## 8. OIDC/OAuth2 Login: UserService and GrantedAuthoritiesMapper

Extension points:
- `OAuth2AuthorizationRequestResolver`/Repository.
- `ClientRegistration`.
- Access token response client.
- `OidcUserService`, `OAuth2UserService`.
- `GrantedAuthoritiesMapper`.
- `AuthenticationSuccessHandler`/`FailureHandler`.
- Session/cookie/RequestCache.
- Logout endpoints.

When upgrading, avoid rewriting the entire AuthenticationProvider just to assign app roles.

### 8.1. Delegating OidcUserService

The Spring reference presents this pattern:
~~~java
// Spring framework fragment; requires appropriate imports and configuration.
OidcUserService delegate = new OidcUserService();

OAuth2UserService<OidcUserRequest, OidcUser> service = request -> {
    OidcUser oidcUser = delegate.loadUser(request);

    // Add approved local identity link / entitlement lookup here.
    // Preserve the verified ID Token and identity contract.
    return oidcUser;
};
~~~

This is a **fragment**, not a standalone JDK class. It preserves default OIDC processing instead of manually parsing JSON from the browser. Specifically check that UserInfo `sub` matches ID Token `sub` per the OIDC contract and that account linking does not rely solely on email.

### 8.2. GrantedAuthoritiesMapper and Role Prefixes

OIDC/OAuth2 login may produce `OIDC_USER`/`OAUTH2_USER` and `SCOPE_*`; these authorities are not business roles. The app can map group IDs from verified claims into `ROLE_REPORT_VIEW`, provided:
- Only approved IdP issuers/client registrations are trusted.
- Only exact group IDs are allowlisted.
- Arbitrary text `admin` never turns into `ROLE_ADMIN`.
- Default authorities important to the target version are preserved if required by adapters.
- Claim lists/strings/nulls/casing/duplicates are handled per policy.
- Tests cover removed groups, missing groups, and disabled accounts.
- Changes in factor authorities between versions are evaluated against the contract—avoid brittle assertions on exact full raw sets while still asserting no privilege escalation.

### 8.3. OIDC State/Nonce/PKCE

If a custom `AuthorizationRequestRepository` or redirect resolver changes:
- `state` may be lost between request and callback.
- `nonce` may not be validated properly.
- PKCE challenge/verifier mismatch.
- Callback URI mismatch with the IdP's registered redirect.
- Cookie `SameSite`/`Secure` or forwarded Host/Proto prevents session persistence.
- Multi-IdP client registration selected erroneously.

**Never disable state or nonce to fix 302/401 callbacks.** Separate session/proxy issues from token validation and test end-to-end.

## 9. JWT Resource Server: Keep JwtDecoder Defaults

`oauth2ResourceServer().jwt()` separates layers:
- `JwtDecoder` decodes, verifies signature/trusted issuer/algorithms, and validates claims.
- `JwtAuthenticationConverter` maps validated claims to `Authentication`.
- `JwtGrantedAuthoritiesConverter` maps scopes, usually defaulting to the `SCOPE_` prefix.
- `AuthorizationManager` decides API permissions, not the decoder.

### 9.1. Common Custom Decoder/Validator Mistakes

- Manually instantiating `NimbusJwtDecoder` and forgetting `JwtValidators.createDefaultWithIssuer`.
- Custom `setJwtValidator(audienceOnly)` replacing defaults instead of composing.
- Omitting the required audience validator for an API with an audience contract.
- Using JWT `kid`/`jku` to fetch arbitrary client-specified public keys.
- Trusting an issuer named in a query param/header without an approved issuer allowlist.
- Accepting `alg=none` or weak algorithms outside policy.
- Treating an API access token as an OIDC ID Token or vice versa.
- Mapping a raw `roles` claim to `ROLE_ADMIN` without group/tenant policy.

### 9.2. Spring Example: Composing Issuer/Time and Audience

File `JwtValidationConfiguration.java` inside a Spring Boot project:

~~~java
package com.example.security;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwtValidationConfiguration {

    private static final String ISSUER =
            "https://idp.example.org/issuer";
    private static final String AUDIENCE = "reporting-api";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withIssuerLocation(ISSUER).build();

        OAuth2TokenValidator<Jwt> audValidator = jwt -> {
            List<String> audiences = jwt.getAudience();
            if (audiences != null && audiences.contains(AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                            "invalid_token",
                            "Required audience is missing",
                            null));
        };

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        JwtValidators.createDefaultWithIssuer(ISSUER),
                        audValidator));
        return decoder;
    }
}
~~~

**Explanation:**
- This is Spring configuration, not a standalone `javac` file. It requires compatible OAuth2 Resource Server + JOSE modules and trusted issuer metadata/JWKS.
- The decoder handles signature/JWK trust, while `JwtValidators.createDefaultWithIssuer` preserves expected issuer and time checks per framework version; custom audience is **added**.
- Different config APIs may apply in your target release; this demonstrates the composition principle.
- With multiple JWT issuers, never infer trusted JWKS from an arbitrary token claim and fetch it; allowlist issuers and use the matching decoder.
- Test all groups: valid, expired, wrong issuer, wrong audience, invalid signature.

### 9.3. Custom JWT Authority Converter

~~~java
@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtGrantedAuthoritiesConverter granted =
            new JwtGrantedAuthoritiesConverter();

    granted.setAuthoritiesClaimName("scope");
    granted.setAuthorityPrefix("SCOPE_");

    JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();
    converter.setJwtGrantedAuthoritiesConverter(granted);
    return converter;
}
~~~

This is a **bean fragment** requiring imports and resource server configuration. If the real issuer sends `scp` as a list, `scope` as a space-separated string, or a custom `roles` claim, the converter must match the real contract rather than guessing from fake unit tests.

**Changing the prefix from `SCOPE_` to `ROLE_` can cause major authorization shifts.** Audit authorization policies before modifying it. A token with scope `profile` must never become `ROLE_ADMIN` through ambiguous logic.

## 10. Custom AuthenticationProvider or Manager Is a High-Risk Point

Replacing `AuthenticationProvider` can accidentally drop:
1. XMLDSig/JWT signature verification.
2. IdP trusted key/issuer checks.
3. SAML Audience/Recipient/Destination/Conditions.
4. OIDC nonce/state/PKCE.
5. InResponseTo/correlation.
6. Profile-specific replay prevention.
7. Session fixation/cookie policies.
8. Authentication failure handling.
9. Local disabled-account checks.
10. Extra factor/authority metadata in the new version.

**Rule:** If you only need business group mapping, use a converter/mapper. If you only need an extra condition, compose a validator. Replace Provider/Manager only with a clear protocol-level justification and strong integration tests.

### 10.1. Never Fall Back to an Old Authentication on Error

An anti-pattern:
~~~java
// Anti-pattern fragment: never use in production.
try {
    return customProvider.authenticate(request);
}
catch (Exception ignored) {
    return previousSessionAuthentication;
}
~~~

This illustrative snippet does not compile standalone due to missing context/types. It is dangerous because an invalid signature/issuer or expired ticket error could cause an old trusted Authentication to be reused for the current request. **Fail closed** if credential/protocol validation fails; exception handlers must never grant identity.

## 11. Multi-IdP and Tenant Mapping

An application with two identity sources:
~~~text
registrationId=staff
issuer=urn:example:saml:staff-idp
trusted public signing certs=STAFF
tenant=employees

registrationId=partners
issuer=urn:example:saml:partners-idp
trusted public signing certs=PARTNERS
tenant=partners
~~~

A custom `RelyingPartyRegistrationRepository`/resolver must accurately map:
- SAML Request context and SP entityID.
- Approved IdP issuer/signing keys.
- ACS/Recipient/Destination.
- Audience, Conditions, and signature scope.
- Local subject link and tenant/role membership.

Never select a registration solely from raw `X-Forwarded-Host` or user email. When ingress uses dynamic tenant routing, public hostnames are allowlisted/normalized by the proxy, yet IdP key trust must still be governed by server-side registration.

In OIDC, `iss+sub` forms the identity namespace. In SAML, IdP issuer + stable NameID/qualifiers or an approved persistent attribute. In Kerberos, realm + full principal. Two users with the same email from two issuers are not automatically one local user.

## 12. LDAP, Kerberos, CAS, and Legacy Adapters

Beyond web federation protocols, applications may integrate:
- **LDAP/AD:** `LdapBindAuthenticationManagerFactory`, LDAPS/StartTLS, user/group search, nested roles, DN/filter escaping.
- **Kerberos/SPNEGO:** GSS tokens, keytabs, service principal `HTTP/host@REALM`, enctypes/JDK, group mapping.
- **CAS:** service ticket validation, server/service URLs, login/logout callbacks, authorities.
- **X.509 preauth:** client cert trust, TLS termination, mapping validated subjects.
- **Custom enterprise token adapters:** proprietary claims mapped to Authentication.

When upgrading:
- Check vendor adapter versions supporting the target Spring API/JDK.
- Never use a realm-less/issuer-less username as a unique account ID.
- Never trust arbitrary HTTP `X-Forwarded-User`/`X-Remote-User` headers.
- Never drop LDAPS trust certificate validation when a CA changes.
- Never grant roles solely from a valid Kerberos ticket if the local user is disabled.
- CAS ticket/service bindings must remain verified.
- Test missing service principal, invalid ticket, wrong realm, expired ticket, and missing groups.

**A directory lookup returning a user entry does not mean the user is authenticated.** Conversion should consume a validated identity result, never treating an LDAP query as login.

## 13. Checking Filter Chains and Callback Routing

An upgrade can cause a custom validator to **never be invoked** because requests enter a different chain. Review:
- `SecurityFilterChain` order.
- `securityMatcher` and `requestMatchers`.
- SAML ACS `/login/saml2/sso/{registrationId}`.
- OIDC callback `/login/oauth2/code/{registrationId}`.
- API JWT resource server paths.
- Properly scoped CSRF exemptions for callbacks.
- `SessionCreationPolicy` and `SecurityContextRepository`.
- `RequestCache`, SavedRequest, and success/failure handlers.
- Proxy forwarded headers and external public origin.
- SAML SLO, OIDC logout, and session invalidation.

### 13.1. Spring Security Servlet Baseline

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfiguration {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

**This is a Spring configuration class**, requiring dependencies and a trusted `RelyingPartyRegistration`. On an integration branch, you can compare this default path against a custom provider to locate the extension causing a regression. Never use baseline `anyRequest().authenticated()` in place of real production domain authorization.

### 13.2. Session Cookies and CSRF

SAML POST callbacks / OIDC redirects can break after a Spring version change due to:
- Cookie `Secure`/`SameSite`/`Domain`/`Path`.
- HTTP vs. HTTPS public origin.
- Unsanitized proxy forward headers.
- Session state not persisting after authentication.
- CSRF filter chain path mismatch.
- IdP-initiated vs. SP-initiated correlation.
- Multi-node session store and stale serialized principals.

Never disable CSRF system-wide to make login tests pass; configure exemptions scoped strictly to protocol callbacks per Spring configuration and test browser E2E.

## 14. Standalone Java 17: Simulating Composition of Default and Custom Validators

This program runs on JDK 17+ without any framework. **Goal:** understand why a custom-only validator might accept a token signed by an untrusted key, while a default-only validator fails to block a newly required wrong Audience.

File `ValidatorCompositionDemo.java`:

~~~java
import java.time.Instant;
import java.util.List;
import java.util.function.Predicate;

public class ValidatorCompositionDemo {

    record Token(
            String issuer,
            String audience,
            Instant expiresAt,
            String subject,
            boolean trustedSignature) {
    }

    static boolean allPass(
            Token token,
            List<Predicate<Token>> validators) {

        return validators.stream().allMatch(v -> v.test(token));
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-06-01T12:00:00Z");

        Predicate<Token> issuer =
                t -> "https://idp.example.org".equals(t.issuer());
        Predicate<Token> notExpired =
                t -> now.isBefore(t.expiresAt());
        Predicate<Token> trustedSigner =
                Token::trustedSignature;
        Predicate<Token> approvedAudience =
                t -> "reporting-api".equals(t.audience());

        List<Predicate<Token>> defaults =
                List.of(issuer, notExpired, trustedSigner);
        List<Predicate<Token>> composed =
                List.of(issuer, notExpired, trustedSigner, approvedAudience);

        Token valid = new Token(
                "https://idp.example.org", "reporting-api",
                now.plusSeconds(300), "synthetic-user-001", true);
        Token wrongKey = new Token(
                "https://idp.example.org", "reporting-api",
                now.plusSeconds(300), "synthetic-user-002", false);
        Token wrongAudience = new Token(
                "https://idp.example.org", "other-api",
                now.plusSeconds(300), "synthetic-user-003", true);

        System.out.println("valid=" + allPass(valid, composed));
        System.out.println("wrong-key-custom-only=" +
                allPass(wrongKey, List.of(approvedAudience)));
        System.out.println("wrong-key-composed=" +
                allPass(wrongKey, composed));
        System.out.println("wrong-audience-default-only=" +
                allPass(wrongAudience, defaults));
        System.out.println("wrong-audience-composed=" +
                allPass(wrongAudience, composed));
    }
}
~~~

Run:
~~~bash
javac ValidatorCompositionDemo.java
java ValidatorCompositionDemo
~~~

**Exact stdout:**
~~~text
valid=true
wrong-key-custom-only=true
wrong-key-composed=false
wrong-audience-default-only=true
wrong-audience-composed=false
~~~

**Limitations:** `trustedSignature` in the demo is merely a hypothetical boolean. Production must never trust a `signatureValid=true` flag from a browser; it must use OpenSAML/`JwtDecoder` to verify real signatures, IdP/JWK trust, time, issuer, audience, correlation, and replay. The code only illustrates **losing default validators**.

## 15. Standalone Java 17: Role Conversion by Issuer and Tenant

The second program illustrates allowlisted group mapping. The `Identity` in the record **assumes upstream authentication has already passed**; the code does not replace SAML/OIDC/Kerberos token validators.

File `FederatedAuthorityPolicyDemo.java`:

~~~java
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class FederatedAuthorityPolicyDemo {

    record Identity(
            String issuer,
            String subject,
            String tenant,
            List<String> groups,
            boolean previouslyVerified) {
    }

    static Set<String> authorities(Identity user) {
        if (!user.previouslyVerified()) {
            return Set.of();
        }
        if (!"urn:example:idp:staff".equals(user.issuer())) {
            return Set.of();
        }
        if (!"tenant-a".equals(user.tenant())) {
            return Set.of();
        }
        if (user.subject() == null
                || user.subject().isBlank()) {
            return Set.of();
        }

        Set<String> result = new HashSet<>();
        result.add("ROLE_USER");
        if (user.groups().contains("ReportReaders")) {
            result.add("ROLE_REPORT_VIEW");
        }
        return Set.copyOf(result);
    }

    static String display(Set<String> roles) {
        return roles.stream().sorted().toList().toString();
    }

    public static void main(String[] args) {
        Identity alice = new Identity(
                "urn:example:idp:staff", "u-1001", "tenant-a",
                List.of("ReportReaders", "Admin"), true);
        Identity unsigned = new Identity(
                "urn:example:idp:staff", "u-1001", "tenant-a",
                List.of("ReportReaders"), false);
        Identity otherIdp = new Identity(
                "urn:example:idp:partner", "u-1001", "tenant-a",
                List.of("ReportReaders"), true);
        Identity otherTenant = new Identity(
                "urn:example:idp:staff", "u-1001", "tenant-b",
                List.of("ReportReaders"), true);

        System.out.println("alice=" +
                display(authorities(alice)));
        System.out.println("unsigned=" +
                display(authorities(unsigned)));
        System.out.println("other-idp=" +
                display(authorities(otherIdp)));
        System.out.println("other-tenant=" +
                display(authorities(otherTenant)));
    }
}
~~~

Run:
~~~bash
javac FederatedAuthorityPolicyDemo.java
java FederatedAuthorityPolicyDemo
~~~

**Exact stdout:**
~~~text
alice=[ROLE_REPORT_VIEW, ROLE_USER]
unsigned=[]
other-idp=[]
other-tenant=[]
~~~

**Explanation:** The group claim `Admin` appears in Alice's list, yet the app does not grant `ROLE_ADMIN` because it is not on the allowlist; tokens/identities from a different IdP or tenant are rejected. A mapper returning empty does not automatically deny an HTTP request—`AuthorizationManager` must still enforce endpoint/resource access.

**Limitations:** `previouslyVerified` is an internal simulated signal, not proof of trust. Never copy this record as a production security model without signature verification, identity linking, active-account checks, and the SAML/OIDC protocol.

## 16. Regression Test Matrix for SAML/OIDC/JWT

| Test | Input / Condition | Expected |
|---|---|---|
| S01 | SAML Response validly signed by trusted IdP | Authentication succeeds if conditions pass |
| S02 | SAML Assertion validly signed by trusted IdP | Authentication succeeds if conditions pass |
| S03 | Unsigned Response and unsigned Assertion | Reject |
| S04 | Signature bytes/digest modified after signing | Reject signature |
| S05 | IdP signing key not in registration trust | Reject |
| S06 | Valid signature but wrong Audience | Reject Audience |
| S07 | Valid signature but wrong Destination | Reject |
| S08 | Valid signature but wrong Recipient | Reject |
| S09 | Valid signature but wrong InResponseTo | Reject SP-initiated |
| S10 | Future NotBefore or expired NotOnOrAfter | Reject time |
| S11 | Missing NameID when converter requires it | Reject, no user fallback |
| S12 | Approved and protected stable alternate subject | Accept only per policy |
| S13 | Signed Assertion A and unsigned B selected by app | Reject XSW |
| S14 | Duplicate XML IDs / unsupported multiple Assertions | Reject |
| S15 | Valid EncryptedAssertion, right SP private key | Decrypt/validate properly |
| S16 | EncryptedAssertion with wrong decryption key | Reject |
| S17 | Unknown registrationId/issuer | No authenticated session / no loop |
| S18 | SAML HTTP GET Response disallowed by policy | No login from GET |
| S19 | Invalid SAML LogoutRequest | Proper error per target version |
| S20 | New principal/accessor implementation | Stable user mapping and SLO |
| O01 | OIDC Authorization Code + valid ID Token | Login with right iss+sub |
| O02 | Wrong ID Token signature/issuer/audience | Reject |
| O03 | Mismatched state/nonce/PKCE | Reject |
| O04 | UserInfo sub differs from ID Token sub | Reject per OIDC policy |
| O05 | Same email across two issuers | Do not merge local accounts |
| O06 | Approved verified group | Maps right `ROLE_REPORT_VIEW` |
| O07 | Unapproved Admin group | No elevated authority |
| O08 | UserInfo timeout | Fail closed or explicit limited policy |
| O09 | OIDC callback succeeds, session cookie lost | Detect persistence regression |
| J01 | Signed JWT with right issuer/aud/time | API authenticated |
| J02 | Wrong JWT signature/alg | Reject |
| J03 | Wrong JWT issuer | Reject |
| J04 | Missing/wrong required audience | Reject |
| J05 | Expired JWT | Reject |
| J06 | Future nbf outside skew | Reject |
| J07 | Valid token lacks required scope | Authorization deny, usually 403 |
| J08 | Untrusted custom roles claim | No privilege escalation |
| J09 | Unknown kid / arbitrary JWK URL | No untrusted signer accepted |
| A01 | URL matcher requires absent role | 403 |
| A02 | `@PreAuthorize` tenant/owner mismatch | Deny |
| A03 | Missing CSRF token on protected POST | Reject |
| A04 | Multiple filter chains | Correct callback and API chain selection |
| A05 | Browser session serialized across versions | Defined behavior, no wrong principal |
| A06 | Unknown login path after upgrade | No permissive fallback |
| A07 | Resource server enabled alongside browser OAuth2 session | Accurate 401/302 semantics |
| A08 | Logout/SP-initiated session revocation | Works under protocol policy |

**Distinguish 3 negative types:** "tamper-after-sign" must fail at signature; "wrong signing key" must fail at trust; "wrong Audience **validly signed after setting the wrong value**" must fail at protocol validation. If you edit Audience after signing, you haven't tested `AudienceValidator`—only XMLDSig.

## 17. Testing Layers and Confidence Levels

### 17.1. Unit Tests

Use JUnit 5 or standalone Java 17:
- Claim parsing/mapping.
- Null NameID/subject.
- Group allowlist/casing.
- Role prefixes.
- Issuer+subject/tenant linking.
- Default+custom validator composition.
- Error mapping/diagnostic categories.

Unit tests mocking `Jwt` or `Saml2AuthenticatedPrincipal` **do not prove real signatures**.

### 17.2. Provider-Level Integration Tests

- Stand up a separate test IdP keypair/metadata; Spring SP trusts only the public cert.
- Generate real signed SAMLResponse/Assertion via OpenSAML/test IdP.
- Test signatures, issuer, audience, recipient, destination, timestamps, and InResponseTo.
- Run XML Signature Wrapping / duplicate ID tests.
- Use a test JWT issuer/JWKS with real signing; test wrong signer/issuer/aud/time.
- Assert no authenticated SecurityContext is created from invalid input.
- Assert principal/authorities are built from verified content.

**Never bring production private keys into tests.** Use synthetic subjects and an isolated test network.

### 17.3. HTTP/Browser E2E

1. Browser GETs a protected URL.
2. Spring creates a SAML AuthnRequest or OIDC AuthorizationRequest.
3. Test IdP receives the request and emits a signed response.
4. Browser callback hits the exact ACS/redirect URI.
5. Spring verifies and stores SecurityContext/session.
6. Subsequent requests are properly authenticated and authorized.
7. Requests lacking role/tenant are denied.
8. Logout/SLO and session cleanup work.
9. Failure paths do not cause redirect loops.
10. Origin/forwarded headers, cookie SameSite/Secure, and CSRF are verified.

Stateless REST Resource Servers should send a Bearer JWT on every request rather than relying on an OIDC browser session as automatic proof.

## 18. MockMvc and Test Policy

Spring Security test helpers can simulate an authenticated user to test HTTP/method authorization. Example:

~~~java
// JUnit/MockMvc fragment inside a configured Spring Boot test.
mvc.perform(get("/reports/view/demo")
        .with(user("synthetic-user")
            .authorities(() -> "ROLE_REPORT_VIEW")))
    .andExpect(status().isOk());

mvc.perform(get("/reports/approve/demo")
        .with(user("synthetic-user")
            .authorities(() -> "ROLE_REPORT_VIEW")))
    .andExpect(status().isForbidden());
~~~

This fragment requires imports/static imports and existing endpoints; it **is not a standalone Java file**. `user()` bypasses real token validation, so never label this test "SAML signature verified."

When testing POST role-denials, supply a valid CSRF token if CSRF is enabled; otherwise 403 may come from `CsrfFilter` before the role validator runs.

## 19. Controlled Step-by-Step Migration Process

### 19.1. Baseline

1. Record versions and dependency tree.
2. Capture the inventory of custom hooks.
3. Save the security config/RP/client registration contract.
4. Run positive + negative tests on the old version.
5. Establish sanitized baseline authn/authz metrics.
6. Define a canary rollback plan.
7. Check existing SAML/XMLDSig/JWT signing algorithms.
8. Confirm vendor adapters have releases supporting the target.

### 19.2. Upgrade Incrementally

1. Select exact new versions; use Spring Boot dependency management.
2. Address deprecated APIs per the migration guide.
3. Run the app with framework defaults on a test branch for comparison.
4. Re-add each custom validator via composition.
5. Re-add converters/mappers against the verified identity contract.
6. Run the negative security suite after **each hook**.
7. Test sessions/rolling restarts, logout/SLO, and multi-IdP.
8. Test browser/public URLs/callbacks through a real proxy.
9. Review source diffs across impacted trust boundaries.
10. Approve release only with zero security regressions.

### 19.3. Every Extension Change Needs Justification

Record a brief Architecture Decision Record:
- Old hook / new hook.
- Why custom behavior is needed.
- Default validators preserved.
- Whether input is already verified.
- Relevant invariants.
- Unit/integration test IDs.
- Failure semantics.
- Security reviewer/owner.
- Rollback approach.

Never ship a "catch all, return true" exception handler to production just to turn the migration green.

## 20. Post-Upgrade Observability and Diagnostics

Distinguish:
- `authentication_failure`: invalid token/assertion/credential.
- `authentication_success`: trusted identity established.
- `authorization_denied`: user authenticated but lacks business role/tenant.
- `registration_not_found`: routing/IdP resolution issue.
- `state_or_correlation_invalid`: OIDC state / SAML InResponseTo mismatch.
- `session_not_persisted`: cookie/repository/rolling upgrade issue.
- `saml_logout_error`: SLO protocol failure.
- `authority_mapping_changed`: role mapping drift.

Spring Security logging/debug and Micrometer Observations can help, though event names/enablement depend on version/config. Never assume every `AuthenticationSuccessEvent` is emitted in every SSO flow.

### 20.1. Sample Metrics (Suggested, Not Default)

~~~text
security_authn_success_total{protocol,registration}
security_authn_failure_total{protocol,failure_category}
security_authz_denied_total{policy_category}
saml_signature_failure_total{registration}
saml_unknown_registration_total{registration_category}
oidc_callback_state_error_total{client_category}
jwt_audience_mismatch_total{issuer_category}
role_mapping_rejected_total{policy_category}
slo_error_total{registration}
~~~

Never use raw NameID, `sub`, email, JWT, dynamic URI, token, IP address, or arbitrary tenant ID as metric labels. They cause high cardinality and can leak personal data.

### 20.2. Never Log Sensitive Information

Forbidden in logs/tickets:
- Raw SAMLResponse/Assertion XML/Base64.
- ID Token, access token, refresh token, Authorization Code.
- Session cookies, Kerberos Negotiate tickets.
- IdP/SP private signing/decryption keys.
- LDAP passwords/bind credentials.
- Claims containing sensitive PII.
- JWT HMAC/shared secrets.

Use trace IDs, approved issuer/registration categories, error types, and anonymized user references where policy permits.

## 21. Troubleshooting Matrix

| Post-Upgrade Symptom | Likely Cause | Check Step |
|---|---|---|
| Null SAML NameID causes NPE | NameID presence assumption changed | Validate required subject in converter |
| Continuous SAML callback redirects | No-registration/entrypoint behavior | RelyingPartyRegistration resolver |
| Invalid SAML XML signature | OpenSAML5/algorithm/metadata mismatch | Real signed fixture + cert |
| Wrong SAML Audience accepted | Custom validator lost defaults | Compose + negative test |
| Signed SAML Response yet wrong user | Custom converter picked unsigned object | XSW/provenance test |
| SAML logout now returns error Response | SLO behavior changed | Verify protocol/handler |
| SAML principal ClassCastException | New Authentication representation | Stable principal adapter |
| OIDC login succeeds with empty roles | Claim/mapper format changed | Trusted claims + authorities |
| OIDC state/nonce fails | Cookie/AuthorizationRequestRepository | Browser callback trace |
| Widespread 401 on JWT API tokens | Decoder issuer/JWKS/expiry policy | `JwtDecoder` configuration |
| Valid JWT signature yet 403 | `SCOPE_`/`ROLE_` mismatch | Converter and URL policy |
| Wrong-audience JWT accepted | Missing custom audience validator | Signed-invalid-aud test |
| Unknown JWT issuer accepted | Overbroad dynamic issuer resolver | Strict allowlist |
| Same email mapped to wrong tenant | Subject linked solely by email | Issuer + stable subject |
| 403 after login callback | Method/tenant/CSRF | Authn vs. authz distinction |
| User logged in on node A, anonymous on node B | Session serialization/store drift | Cross-version rolling tests |
| IdP key rotation fails | Approved metadata/key overlap mismatch | Credential trust set |
| Kerberos wrong SPN after JVM update | GSS/keytab/enctype compatibility | Validate service tickets |
| CAS service ticket loop | Service URL/redirect changes | CAS validator and proxy origin |
| Tests pass with unsigned SAMLResponse | Mocked provider/permitAll path | Real provider E2E and negative suite |

### 21.1. Debugging in Order

1. Identify whether the request failure is authn, session, or authorization.
2. Verify the right `SecurityFilterChain`.
3. Verify IdP/client registration and trusted credentials.
4. Verify signature/issuer/audience/time/correlation validators.
5. Verify the converter builds the right principal + authorities.
6. Verify local identity link, tenant, and `@PreAuthorize`.
7. Verify callback public origin/redirect/session cookies.
8. Compare observed target-release behavior against migration notes.
9. Add a regression test isolating the root cause.
10. Never disable controls to mask a symptom.

## 22. Rollout, Canary, Rollback, and Session Compatibility

A SAML/OIDC upgrade can change `Authentication`/`Principal` classes. If sessions are stored in Redis/Java serialization or a custom session codec, rolling deployment can prevent new nodes from reading a `SecurityContext` written by old nodes.

How to prepare:
- Verify serializability/session storage format.
- Test cross-version read/write if zero-downtime is required.
- When not guaranteed, consider session invalidation and requiring users to re-SSO.
- Test logout/SLO before and after rollback.
- Never deserialize untrusted bytes into arbitrary principals via insecure polymorphic mapping.
- Monitor callback failures, session loops, and unexpected elevated authorities.
- Canary on approved IdPs/tenants; never experiment on sensitive production accounts.
- Rollback code must not re-enable trust for deprecated algorithms/issuers.
- Prepare documented user communication if re-login is needed after upgrade.

**Important:** Rollback does not mean "toggling a property to accept all legacy tokens." Keep signature/issuer/time validation intact and invalidate incompatible sessions per policy.

## 23. Pre-Release Review Checklist

- [ ] Recorded exact old/target Spring Security, Boot, OpenSAML/JDK versions.
- [ ] Audited every AuthenticationProvider, validator, converter, mapper, and resolver.
- [ ] Read the migration guide for the exact major/minor release.
- [ ] No custom parser reads raw SAMLResponse to construct a principal.
- [ ] SAML signature/trusted IdP signing credentials remain verified.
- [ ] Consumed assertion lies within trusted signed coverage.
- [ ] `ResponseValidator`/`AssertionValidator` keep mandatory checks.
- [ ] Missing NameID / alternate stable ID policy has negative tests.
- [ ] Issuer/Audience/Destination/Recipient/Conditions/InResponseTo are verified.
- [ ] Unknown `registrationId` neither creates a login nor causes a redirect loop.
- [ ] SLO/LogoutResponse behavior matches the target release.
- [ ] Authentication/principal/accessor changes do not corrupt account mapping.
- [ ] OIDC ID Token issuer/audience/time and state/nonce/PKCE are verified.
- [ ] UserInfo subject binding and approved identity link remain intact.
- [ ] JWT Decoder verifies signature, issuer, expiry, nbf, and required audience.
- [ ] JWT authority prefix/claim conversion matches contract.
- [ ] No arbitrary `ROLE_ADMIN` from untrusted claims.
- [ ] Multi-IdP tenant routing and `localUserId` mapping are isolated.
- [ ] Kerberos/CAS/LDAP adapters match supported versions.
- [ ] `SecurityFilterChain` and `MethodSecurity` policies remain enforced.
- [ ] CSRF/session/cookie/`redirect_uri`/SAML ACS settings are accurate.
- [ ] Java 17 unit tests exist for mapping/composition.
- [ ] Real signed SAML + JWT integration security tests exist.
- [ ] Negative tests exist for XSW, replay, wrong key, missing signature, wrong audience.
- [ ] No tokens/keys/PII are logged.
- [ ] Release gates, metrics, canary, rollback, and session handling plans are ready.
- [ ] All validator/decoder errors fail closed; no permissive fallback.

## 24. Review Questions

1. **How does a validator differ from a converter?** One verifies data; the other maps verified data.
2. **Why does a passing build not prove the upgrade is safe?** Default checks may have been dropped while the app still runs.
3. **What does `ResponseValidator.withDefaults` signify?** Keeping built-in Response validation when adding a custom rule.
4. **Why does OpenSAML 5 matter?** Provider model, XMLDSig/decryption, APIs, and behavior must be re-verified.
5. **What does Spring Security 7 change regarding NameID?** Custom converters must enforce policy explicitly as presence validation order/defaults shift.
6. **Why is `Saml2ResponseAssertionAccessor` notable?** Assertion data is separated from the principal for workflows like logout.
7. **What can an unknown `RelyingPartyRegistration` cause after upgrade?** Redirect loops or different handler behavior; it must never grant Authentication.
8. **What can an invalid SAML LogoutRequest return?** An error SAML LogoutResponse per target protocol behavior.
9. **How should GET SAMLResponse be handled?** Strictly per binding/profile and policy; never allow arbitrary login.
10. **Valid signature but wrong Audience?** Reject.
11. **Is a browser-supplied `KeyInfo` a trust anchor?** No.
12. **Can attributes from unsigned assertion B be used when signed A is valid?** No.
13. **Does `OIDC_USER` mean `ROLE_ADMIN`?** No.
14. **What is the critical identity key pair in OIDC?** Approved issuer + stable subject.
15. **Does `JwtAuthenticationConverter` verify the JWT itself?** No; the decoder is responsible.
16. **When adding Audience validation, how do you avoid losing defaults?** Compose issuer/time validators with the audience rule.
17. **Are `SCOPE_profile` and `ROLE_ADMIN` equivalent?** No.
18. **What if a custom group converter encounters a null claim?** Never grant permissions beyond policy.
19. **Should state/nonce be dropped to fix callback failures?** No.
20. **What if a local user is disabled while SAML is valid?** The app must deny business access.
21. **Does a MockMvc `user()` test verify real signatures?** No.
22. **For a wrong-audience negative test, sign before or after setting the wrong audience?** Set the wrong value first, then sign.
23. **When session serialization changes, what must be done?** Test rolling deployment or invalidate sessions in a controlled manner.
24. **When multiple IdPs share the same email, auto-merge local users?** No.
25. **Can `X-Forwarded-User` be trusted directly?** No.
26. **If a token with the wrong issuer is accepted?** Release blocker due to validation regression.
27. **Why test HTTP, method, and domain authorization?** Valid login does not automatically grant access to every resource.
28. **Most important review when upgrading?** Preserving default cryptographic/protocol validators and trusted identity provenance.
29. **Can raw SAMLResponses be logged for debugging?** No; they contain sensitive information.
30. **Signs of a completed migration?** Positive paths pass, negative inputs are still rejected, roles are accurate, and operations/canary/rollback are verified.

## 25. References

- Spring Security – Migrating to 7: https://docs.spring.io/spring-security/reference/migration/
- Spring Security – Servlet SAML2 Migrations: https://docs.spring.io/spring-security/reference/7.0/migration/servlet/saml2.html
- Spring Security – SAML2 Authenticating Responses: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security – SAML2 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security – Relying Party Configuration: https://docs.spring.io/spring-security/reference/servlet/saml2/login/relying-party.html
- Spring Security – OAuth2 Login Advanced, UserService and GrantedAuthoritiesMapper: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html
- Spring Security – OAuth2 Login Core: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
- Spring Security – OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security – HTTP Authorization: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security – Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security – MockMvc Testing: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/
- Spring Boot – Dependency Management: https://docs.spring.io/spring-boot/reference/using/build-systems.html
- OWASP – SAML Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html
- OWASP – JSON Web Token for Java Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html
- OWASP – Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- OASIS – SAML Core 2.0: https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf
- OASIS – SAML Web Browser SSO Profiles: https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf

**Summary:** Reviewing custom validators and converters is a security task, not just an API fix when upgrading Spring Security federation. Every upgrade must preserve or intentionally strengthen the controls **trusted signature → issuer → audience/recipient/destination → lifetime/correlation → validated subject → approved roles → resource authorization**. Especially when moving from Spring Security 6→7, verify differences in OpenSAML 5, NameID/principal, missing registration, and SLO. Release only after negative security fixtures prove forged inputs remain rejected, no identity/tenant/role escalation occurs, and observability/rollback are prepared.
