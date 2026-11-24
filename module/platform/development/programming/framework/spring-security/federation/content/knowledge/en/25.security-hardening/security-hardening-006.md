# IdP, Issuer, or Tenant Confusion When Selecting Verification Configuration

**When Spring Security supports multiple Identity Providers (IdPs), issuers, or tenants, selecting the wrong verification configuration can become an account-takeover or cross-tenant privilege-escalation vulnerability.** A valid token signature is not enough: it must match the right **issuer**, the right **keys bound to that issuer**, the right **recipient/audience**, the right **login transaction**, the right **time**, the right **token type**, and the **tenant the user is actually authorized to access**.

**Example:** a company uses OIDC issuers Corp and Partner alongside SAML IdP Enterprise. User `alex` from Partner sends a token validly signed with Partner's key to an endpoint meant for Corp. If the backend looks up the user only by username, dynamically picks JWKS from an unverified `iss`, or maps Partner's `admins` group to Corp privileges, that is **issuer/IdP confusion** and can lead to **account takeover**. If the backend trusts browser-supplied `tenant=south` directly to determine permissions, that is **tenant confusion**.

**Overarching rule:** define a **server-managed set of trusted configurations**; `iss`, SAML `Issuer`, `kid`, registrationId/path, or tenant slug coming from a request **can only serve as a hint to pick a candidate within that set**, never as trusted proof. After selecting a candidate, run the **exact protocol- and registration-specific validator**; only after verification link the identity to a local account and evaluate tenant/resource permissions.

This article belongs to **Spring Security – federation → Security Hardening**, covering OIDC/OAuth mix-up, JWT issuer/key confusion, SAML IdP/ACS/audience confusion, Spring Security multi-issuer/multi-RelyingPartyRegistration setups, onboarding processes for new IdPs, testing techniques, and a standalone Java 17 program.

## 1. Why Is This a Real Security Vulnerability?

A SaaS application has two tenants and two identity sources:

~~~text
User/Browser
      |
      | Select login /t/north or /t/south
      v
  Spring Application
      |
      +---- OIDC Corp:    issuer = https://id.corp.test/realm/staff
      |
      +---- OIDC Partner: issuer = https://id.partner.test/realm/client
      |
      +---- SAML Enterprise:
             IdP entityID = urn:enterprise:idp
      |
      v
 Verified identity -> Local account -> Tenant membership
      |
      v
 Protected API and object-level authorization
~~~

Two IdPs can both issue `sub=123`, `email=alex@example.test`, or `groups=["admin"]`. They **do not automatically represent the same person**. Similarly, a token with issuer Corp but `aud=payroll-api` must not be accepted by Billing. A SAML Assertion signed by Enterprise whose `AudienceRestriction` targets another app must not be accepted at Portal.

Therefore you must guard **all three boundaries**: identity source (issuer/IdP), target receiver (SP/client/API audience), and permissions over the tenant/resource.

## 2. Concepts to Distinguish

| Term | Meaning | Must not be confused with |
| --- | --- | --- |
| **IdP** | System authenticating users and issuing evidence (e.g., SAML/OIDC) | Tenant or email domain |
| **OIDC issuer / OAuth AS issuer** | Issuer/Authorization Server URL identifier, used in `iss` | Gateway hostname |
| **SAML IdP entityID** | Asserting party identifier in trusted SAML metadata | Spring registrationId |
| **Spring ClientRegistration.registrationId** | Internal OAuth/OIDC client config key | Issuer or tenant ID |
| **RelyingPartyRegistration.registrationId** | Internal SAML RP↔IdP config key | IdP entityID |
| **SAML SP entityID** | Service Provider identifier receiving the Assertion | IdP entityID |
| **Tenant** | Organizational, data, and policy boundary of the app | Issuer or subdomain |
| **Subject** | OIDC `sub` or SAML NameID/stable attribute within an IdP scope | Global email/username |
| **Audience** | Intended recipient of the token/assertion | Logged-in user |
| **Key ID (kid)** | Hint selecting a key within an already trusted key set | Standalone trust anchor |
| **JWKS / certificate metadata** | Registered/governed verification keys | Arbitrary URL taken from a token |

Relationships are not always 1:1: one tenant can trust **multiple IdPs**; one issuer can serve **multiple tenants**; one IdP can have **multiple registrations** across applications. Never hardcode `issuer == tenant` across all scenarios.

## 3. Authentication, Verifier Selection, and Authorization Are Three Steps

**Routing/candidate selection:** the application needs to know which registration/decoder to use. Selecting a candidate **does not mean the token is already trusted**.

**Authentication/protocol verification:** use the candidate's verifier to check signature, issuer, audience, time, replay, nonce or InResponseTo, and recipient.

**Authorization:** decide whether the verified subject is permitted to enter this tenant/resource. A user may authenticate successfully at the IdP yet lack permission for the requested tenant.

~~~text
HTTP request / browser callback (UNTRUSTED)
      |
      v
Select only from trusted registrations
      | Unknown/ambiguous -> REJECT
      v
Exact protocol verifier
      | Signature + issuer + audience + time
      | State/nonce/recipient/InResponseTo + replay controls
      | Failure -> REJECT
      v
Verified (protocol, issuer/IdP, subject, actor)
      |
      v
Local account linking, account active state
      |
      v
Tenant membership + action/resource authorization
      |
      v
ALLOW or DENY
~~~

**Wrong:** pick keys using whatever `iss` the token self-declares, then check only the signature. **Right:** pick a candidate from a trusted allowlist and require the verified result to match the expected registration completely.

## 4. Typical Attack Classes and Misconfigurations

| Failure Type | How it happens | Consequence |
| --- | --- | --- |
| IdP confusion | Token/Assertion B is accepted on flow A | Wrong user/trust context accepted |
| OAuth AS mix-up | Callback does not know which Authorization Server owns the code | Authorization code/token leakage |
| Issuer confusion | JWT has wrong `iss` or arbitrary issuer auto-trusted | Attacker self-signed token accepted |
| Key confusion | Global `kid` map not bound to issuer | Key B used to accept claims from A |
| Algorithm confusion | Parser trusts token-chosen `alg` without policy check | Weak/bypassed signature validation |
| SAML registration confusion | Selecting RelyingPartyRegistration via XML Issuer and treating it as proof | Accepting Assertion for wrong recipient/tenant |
| Audience confusion | Validly signed token meant for another API | Confused deputy |
| Tenant confusion | Trusting tenant slug/header as membership | Cross-tenant data exposure |
| Principal collision | Unnamespaced email/sub/NameID | Account takeover |
| Role collision | Group admin from B becomes ROLE_ADMIN in A | Privilege escalation |
| Replay confusion | Not matching state/nonce/InResponseTo or assertion ID | Session fixation/replay |
| Stale trust | IdP revoked while decoder/session still accepts | Access persists outside policy |

**Threat modeling:** explicitly mark every input an attacker can modify: URL, query, Host, forwarded headers, `iss`, `kid`, `jku`, XML Issuer, email, tenant ID, group names, and callback parameters. Every one of them must sit behind a trust boundary.

## 5. An Unverified JWT Issuer Is Only a Hint

A JWT may contain:

~~~json
{
  "header": {
    "alg": "RS256",
    "kid": "key1",
    "jku": "https://untrusted.test/keys"
  },
  "payload": {
    "iss": "https://untrusted.test",
    "sub": "admin",
    "aud": ["billing-api"],
    "tenant": "north"
  }
}
~~~

This is an **illustration of two JWT parts**, not a valid compact JWT. Both `header` and `payload` are **unverified** data until the decoder verifies the signature.

**Do not do this:**

~~~java
// UNSAFE PSEUDOCODE; not runnable code.
String issuerFromUnverifiedJwt = parseWithoutVerifying(token).getIssuer();
JwtDecoder decoder = JwtDecoders.fromIssuerLocation(
        issuerFromUnverifiedJwt);
Jwt authentication = decoder.decode(token);
~~~

If the issuer URL is attacker-controlled, the decoder can fetch the attacker's JWKS, and a self-signed token will verify **against the attacker's key set**. That does not give the backend any basis to trust the attacker as an IdP.

**Instead:** map from exact trusted issuer strings to AuthenticationManagers or JwtDecoders approved by the security owner. Unverified `iss` only performs a lookup **within that set**; after verification, confirm the exact issuer.

## 6. Spring Security: Safe JwtIssuerAuthenticationManagerResolver

Spring Security documentation for multi-issuer Resource Servers provides `JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(...)`.

Example for **Spring Security Servlet in a Spring Boot project**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerAuthenticationManagerResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurity {

    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        JwtIssuerAuthenticationManagerResolver trustedIssuers =
            JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
                "https://id.corp.test/realm/staff",
                "https://id.partner.test/realm/client"
            );

        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth -> oauth
                .authenticationManagerResolver(trustedIssuers))
            .build();
    }
}
~~~

**Integration note:** this configuration belongs in a Spring Security/OAuth2 Resource Server project and **cannot be run with plain JDK `javac`**; it requires dependencies, Authorization Servers, trusted metadata/JWKS, endpoint policies, and other SecurityFilterChains. Spring may lazily build a provider for an approved issuer when that issuer first sends a request.

**Do not turn fromTrustedIssuers into accepting every issuer** by dynamically adding any `iss` found in a JWT to the trusted list. Dynamic tenant management must be a **trusted governance workflow**, not self-enrollment from user input.

## 7. A Valid Issuer Is Not Enough: Audience and Token Purpose

Suppose a token issued by Corp says:

~~~text
iss = https://id.corp.test/realm/staff
aud = payroll-api
sub = employee-82
scope = payroll.read
~~~

The Billing API also trusts the Corp issuer, yet **must not accept** this token because the audience does not include `billing-api`.

A Resource Server checks at minimum:

1. JWT signature and trusted algorithm/key.
2. Exact `iss`.
3. `aud` within the accepted resource IDs for this API.
4. `exp` and `nbf`, with profile-aligned clock skew.
5. Token **purpose/type**: access token rather than an ID Token or another internal JWT.
6. Client/actor identity if the API enforces client-specific policy.
7. Scope/permissions per app contract.
8. Tenant membership, active account, and resource ownership.

**Note:** `JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers` handles **issuer selection**; when assembling custom managers/decoders, **you must still configure audience and purpose validators for each issuer**. Do not assume single-issuer properties automatically apply to custom managers.

## 8. Audience Validator Example in Spring

A `JwtDecoder` should only be built from a trusted issuer source. Illustrative Java snippet **inside a @Configuration**, with matching Spring OAuth2 imports:

~~~java
// trustedIssuer is an approved literal/config, not taken
// directly from an unverified token or query parameter.
NimbusJwtDecoder decoder = JwtDecoders
        .fromIssuerLocation(trustedIssuer) instanceof NimbusJwtDecoder n
        ? n : null;

if (decoder == null) {
    throw new IllegalStateException("Unexpected JwtDecoder type");
}

OAuth2TokenValidator<Jwt> issuerAndDefaults =
        JwtValidators.createDefaultWithIssuer(trustedIssuer);

OAuth2TokenValidator<Jwt> requiredAudience = jwt ->
        jwt.getAudience().contains("billing-api")
        ? OAuth2TokenValidatorResult.success()
        : OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", "Wrong audience", null));

decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
            issuerAndDefaults, requiredAudience));
~~~

**This is a fragment**, not a standalone class. It is version-dependent; a simpler approach is constructing `JwtDecoder` from a configured trusted JWK URL and configuring explicit validators. The goal is **not losing default checks** when adding a custom check. When supporting multiple issuers with distinct AS key sets, build a per-issuer decoder from a trusted registry rather than pooling everything into one global key pool.

**Token type** (such as a JWT access token per RFC 9068) must also be checked per contract, not just issuer/audience.

## 9. kid and jku: Difference Between Key Hint and Trust Anchor

A JWT header can carry `kid` to select a key in a known JWKS. However:

- `kid` is **not globally unique**. IdP Corp and Partner may both use `kid=key1`.
- Token-supplied `jku` or `x5u` **must not be trusted** as a key-download source.
- The `alg` declared by the JWT header must **be in the approved algorithms**, never allowed to downgrade security.
- If the app looks up keys in a global `kid → public key` map, it can verify with the wrong issuer's key.
- If the app fetches arbitrary URLs, it faces **SSRF**, DNS rebinding, and key substitution risks.
- Metadata/JWKS may be cached, but the key cache must be scoped to issuer/registration/source trust context.

**Right pattern:** `(trusted_issuer, trusted_metadata_version, kid) → candidate public key`; verify signature and algorithm policy, then validate `iss/aud/exp/type` claims. Never open trust by downloading JWKS directly from a token-suggested URL.

## 10. OAuth Authorization Server Mix-Up Occurs Before ID Token Validation

When an OAuth/OIDC client works with multiple Authorization Servers, the user might pick AS A while the callback is processed as if the code belonged to AS B. If the client **sends the authorization code to the wrong token endpoint**, secrets can leak **before ID Token validation ever happens**.

~~~text
Browser            OAuth Client             AS Legit          AS Malicious
   |                    |                       |                  |
   |--- choose A ------>|                       |                  |
   |                    |---- auth request A -->|                  |
   |<------------------- redirect code+state --|                  |
   |--- callback ------>|                       |                  |
   |                    |----- WRONG exchange -------------------->|
   |                    |                               code leaked
~~~

**RFC 9700 (OAuth 2.0 Security BCP)** requires clients supporting multiple ASes to defend against mix-up. **RFC 9207** defines `iss` in the authorization response so the client can compare it against the issuer stored at initiation.

**Do not assume using PKCE automatically waives all mix-up protections.** PKCE protects the authorization code under specific conditions, yet the client must still ensure it never sends codes/credentials to the wrong AS.

## 11. Binding the OAuth Callback with state and issuer

When initiating login, store the transaction **server-side** or in a secure request repository:

~~~text
transaction:
  registrationId         = corp-oidc
  expectedIssuer         = https://id.corp.test/realm/staff
  expectedClientId       = portal-corp
  expectedTokenEndpoint  = trusted AS token endpoint
  redirectUri            = exact callback URI
  state                  = random, one-time, session-bound
  pkceCodeVerifier       = secret for this request
  nonce                  = random when required by OIDC flow
  expiresAt              = short lifetime
~~~

On callback:

1. Confirm `state` exists, is single-use, and binds to the right browser context.
2. Confirm the callback route/registrationId matches the expected registration.
3. If the authorization response contains `iss` (RFC 9207), verify it matches the **expected issuer** before token exchange.
4. If using another RFC 9700 countermeasure, such as distinct redirect URIs, verify exact mapping per AS; never drop mix-up defenses.
5. Exchange the code **only at the registered token endpoint**, applying client authentication/PKCE per flow.
6. Verify the ID Token for the exact issuer/client: signature, `iss`, `aud`, `azp` when needed, `exp`, `nonce`/`auth_time` per profile.
7. Link the user by verified `(iss,sub)`, not by a user-supplied email at initiation.
8. Check tenant/resource authorization after authentication.

**Note:** `state`/`nonce`/PKCE serve distinct purposes; use your release's framework support instead of hand-rolling callbacks unnecessarily.

## 12. OIDC Issuer Must Match Exactly, Not Merely Share a Host

Examples:

~~~text
Expected: https://login.example.test/realm/north
Actual:   https://login.example.test/realm/south
=> REJECT

Expected: https://login.example.test/realm/north
Actual:   https://login.example.test
=> REJECT

Expected: https://login.example.test/realm/north
Actual:   https://evil-login.example.test/realm/north
=> REJECT
~~~

Never strip paths, take email domains, drop trailing slashes arbitrarily, or check `startsWith("https://login.example.test")`. The `iss` value must match the published issuer per OP profile/metadata and contract.

**A single issuer can serve multiple tenants**, so a valid issuer **does not prove the user belongs to the requested tenant**.

## 13. OIDC ID Token Differs from API Access Token

An OIDC **ID Token** is issued to inform the client/Relying Party that the user logged in; an OAuth2 **Access Token** is meant for Resource Servers. Both may be JWTs, yet they differ in audience, claims, and purpose.

| Property | ID Token | JWT Access Token |
| --- | --- | --- |
| Primary recipient | OIDC client, `aud=client_id` | Resource Server, `aud=api/resource` |
| Purpose | User authentication for RP | API access authorization |
| Issuer validation | Mandatory per OP registration | Mandatory per AS trust |
| Nonce | Checked per OIDC flow when required | Not a default for API Bearer |
| Scope | Do not turn ID Token into API privileges | Access-token scopes used with resource policy |
| Token type | ID Token | Access token profile/purpose |

**Do not accept an ID Token at an API** merely because it was signed by the same IdP. For RFC 9068 JWT access tokens, verify `typ`/token profile when provided.

## 14. SAML: Distinct Identifiers

In SAML2:

| Name | Meaning |
| --- | --- |
| **IdP entityID** | Trusted registered asserting party issuer |
| **SP entityID** | Relying Party targeted by the Assertion |
| **registrationId** | Spring Security internal key for a registration |
| **ACS endpoint** | Assertion Consumer Service receiving POST SAMLResponse |
| **Response/Assertion Issuer** | Claim of sender; must be verified against metadata |
| **AudienceRestriction** | SP entityID permitted to receive the Assertion |
| **Destination/Recipient** | Endpoint targeted by SAMLResponse or SubjectConfirmation |
| **InResponseTo** | Links back to SP-issued AuthnRequest |
| **NameID** | User identity in a specific format within IdP scope |
| **Signing credentials** | Trusted keys/certs of the exact IdP registration |

**A Spring registrationId is not an IdP entityID.** SAML configuration also includes verification certificates, entityID, ACS, metadata, decryption keys, and trust settings.

## 15. SAML Authentication and Selecting RelyingPartyRegistration

Spring Security SAML2 Login documentation describes `Saml2WebSsoAuthenticationFilter` building a `Saml2AuthenticationToken` via an AuthenticationConverter, passing the resolved `RelyingPartyRegistration` to the OpenSAML provider.

Candidate registration may be selected from:

- registrationId in the URL, e.g. `/login/saml2/sso/corp`;
- stored AuthnRequest in an SP-initiated flow;
- SAML Response `Issuer` when appropriate and used to look up a trusted registration.

**Important:** initial `Issuer` is untrusted XML; it may select a **candidate**, never **proof of a valid signature**. After picking the registration, the provider must verify signature, expected issuer, Destination, AudienceRestriction, Recipient, assertion Conditions, and corresponding checks.

~~~text
POST /login/saml2/sso/corp + SAMLResponse
          |
     Candidate registration "corp"
          |
     Verify against Corp IdP credentials only
          |
     Check Response/Assertion Issuer
     Check Destination/ACS and Recipient
     Check AudienceRestriction equals configured SP entityID
     Check time, conditions, subject confirmation
     Correlate InResponseTo to stored AuthnRequest
     Reject replayed assertion IDs
          |
     Verified (IdP entityID, subject)
          |
     Map local account + requested tenant
~~~

**Never try every certificate of every IdP in turn and accept whichever key verifies.** Even a shared signing key across two registrations does not permit waiving issuer/audience/tenant restrictions.

## 16. Multiple SAML Registrations Example in Spring Boot

This is a configuration example for a **Spring Boot application with the SAML2 Service Provider library**, not a standalone program:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              metadata-uri: "https://idp.corp.test/saml/metadata"
          partner:
            assertingparty:
              metadata-uri: "https://idp.partner.test/saml/metadata"
~~~

**Practical additions needed:** trusted IdP metadata endpoints, SP registration, entityID/ACS, SSO profiles, cert rotation, IdP allowlist, and reverse-proxy public origin. Spring Boot/Security versions differ in properties/APIs; test against your exact BOM.

**Never accept a browser-supplied metadata-uri and immediately enable a registration.** Adding an IdP must go through trust/configuration approval, SSRF defense, and identity-link collision checks.

## 17. SAML SP-Initiated Must Bind Request and Response

~~~text
1. Browser chooses Corp login.
2. SP stores expected RelyingPartyRegistration=corp.
3. SP sends AuthnRequest ID=REQ-42 to Corp IdP.
4. Corp authenticates user and posts SAMLResponse to ACS.
5. SP matches InResponseTo=REQ-42 against outbound request.
6. SP verifies signed Response/Assertion, Issuer, Audience, Recipient.
7. SP checks time/SubjectConfirmation and replay ID.
8. SP creates Authentication carrying verified IdP context.
~~~

If Partner's response arrives inside Corp's flow, never switch automatically to the Partner registration merely because the XML says `Issuer=Partner` while skipping request correlation.

**IdP-initiated/unsolicited SAML** lacks a prior AuthnRequest to correlate. If business requirements allow it, define a strict policy: exact IdP trust, audience/recipient, time, replay, login-CSRF protection, and tenant mapping. Never skip signature or destination checks because `InResponseTo` is absent.

## 18. Non-Negotiable SAML Checks

- **Signature:** use the exact trusted IdP verification credentials; distinguish Response vs Assertion signatures per profile.
- **Issuer:** Response/Assertion claims must match the exact asserting party registration.
- **Destination:** Response must target a URL accepted by the RP.
- **AudienceRestriction:** Assertion must target the configured SP entityID.
- **SubjectConfirmationData.Recipient:** must be the exact ACS, not just any URL on the same domain.
- **InResponseTo:** when SP-initiated, must match a stored AuthnRequest.
- **Conditions timestamps:** NotBefore/NotOnOrAfter, clock skew policy.
- **Replay:** never accept replayed Assertion IDs or response IDs outside policy.
- **Decryption:** if encrypted, decrypt with the right credential and continue full validation.
- **XML handling:** defend against signature wrapping, XXE, malicious XML, and oversized messages.

**Use the standard Spring/OpenSAML provider**, never parsing XML manually with regex or verifying one node while reading the principal from another. Spring Security 6.x and 7.x differ in OpenSAML/APIs, so follow your exact release.

## 19. Tenant in URL/Header Is Not Permission

Example URL:

~~~text
GET /t/south/api/invoices/inv-203
X-Tenant: south
Authorization: Bearer ACCESS_TOKEN
~~~

The user holds a token from a valid issuer but belongs only to tenant North. The `south` field in the path/header only identifies the **requested resource**, not membership.

**Domain authorization:**

~~~text
ALLOW
 IF token/assertion verified against trusted issuer/IdP
 AND local account active
 AND requested tenant exists and is permitted for this IdP/registration
 AND user is active member of requested tenant
 AND action permission granted in requested tenant
 AND invoice belongs to requested tenant
 ELSE DENY
~~~

If the app uses tenant subdomains, guard against Host/X-Forwarded-Host spoofing via trusted proxies and allowlists. **Never select an IdP/tenant from an untrusted Host header and allow login under broadened trust.**

## 20. Identity Linking: Same sub/email Can Still Be Different People

Two sources:

~~~text
Corp:
  issuer = https://id.corp.test/realm/staff
  sub    = 123
  email  = alex@example.test

Partner:
  issuer = https://id.partner.test/realm/client
  sub    = 123
  email  = alex@example.test
~~~

Despite matching `sub` and email, these are **two external identities**. A safe key is typically:

~~~text
(protocol, verified_issuer_or_saml_entityID, verified_subject)
    -> local_account_id

local_account_id + requested_tenant
    -> membership and entitlements
~~~

For SAML NameID, check the format (persistent/transient/email address) and contract; many NameIDs are unstable, and email must not be used as a UUID. When a tenant switches IdPs, account migration requires linking proof/approval and audit.

**Never auto-merge two local accounts solely by matching email**, especially if tenant admins can register IdPs themselves.

## 21. Group/Role Confusion and GrantedAuthority

Suppose Partner IdP emits group `FinanceAdmins` and Corp IdP also has a group with the same name. Never map both to `ROLE_ADMIN` across all tenants.

Enforce an explicit policy:

| Trusted source | Trusted group ID | Tenant | App permission |
| --- | --- | --- | --- |
| Corp issuer | `corp-billing-readers` | North | `ROLE_INVOICE_VIEWER` |
| Corp issuer | `corp-billing-approvers` | North | `ROLE_INVOICE_APPROVER` |
| Partner issuer | `partner-support-readers` | South | `ROLE_SUPPORT_VIEWER` |
| Unknown source | `ROLE_ADMIN` (raw string) | Any | **Do not grant** |

Map only after signature/token validation and account linking. **Roles are application-owned**, requiring an exact allowlist and tenant/resource checks. A verified user does not automatically get access to every endpoint.

## 22. Dynamic Issuer Onboarding Requires Governance

If a SaaS allows customers to register a new IdP:

1. Tenant owner submits an onboarding request; do not create a trusted profile immediately.
2. Verify the admin holds tenant administration and federation-trust change privileges.
3. Check issuer/entityID uniqueness, allowed tenant mappings, consent, and legal requirements.
4. Fetch metadata/JWKS only over HTTPS with egress controls against SSRF/private IPs/link-local.
5. Verify metadata issuer, algs, signing certificates/JWKS, endpoints, and redirects/ACS.
6. Run a canary login test verifying request correlation/audience/tenant.
7. Require security-owner approval before marking ACTIVE.
8. Version configurations and audit who changed issuer/keys/roles and when.
9. Configure key rotation and revocation/disable policies.
10. Never auto-trust an issuer merely because a JWT self-declares it.

**Dynamic trusted configuration ≠ dynamic trust from unverified input.** When a tenant closes or an IdP is compromised, disable the registration and handle issued sessions.

## 23. Key Rotation, Metadata Cache, and Failure Modes

Issuers rotate JWKs; SAML IdPs rotate signing certificates. You must:

- Scope key caches by **exact issuer/registration**, never by global `kid`.
- Trust only approved metadata/JWKS endpoints; verify TLS certificates and redirects.
- Enforce algorithms and key types per policy; never downgrade to weak algorithms to fix an outage.
- Provide managed key overlap windows during rotation.
- Configure timeouts, caching, bounded retries, and metrics.
- If a new `kid` is missing, refresh only that trusted issuer's JWKS under rate limits; never fall back to another issuer.
- When an issuer is revoked, halt new authentications and handle cached managers/sessions per SLA.
- Never accept an expired or untrusted certificate just because the name matches.
- Check multi-node impact and stale caches after deployment.
- Maintain a rollback plan that **never broadens trust**.

**IdP A's key set cannot compensate for IdP B's misconfiguration.** “Try finding another issuer that verifies it” is a design bug.

## 24. Standalone Java 17: Simulating Verifier and Tenant Selection

The following program uses a **simulated policy**. It **does not actually verify JWT/SAML signatures**; the booleans `signatureVerified` and `flowCorrelated` represent outputs **after a trusted protocol library has processed the message**, never values read from an HTTP request.

Create file **IssuerTenantSelectionDemo.java**:

~~~java
import java.util.Map;
import java.util.Set;

public class IssuerTenantSelectionDemo {

    record Profile(String issuer, String audience,
                   String tenant, Set<String> keyIds) {}

    record Evidence(String issuer, String audience,
                    String tenant, String keyId,
                    boolean signatureVerified,
                    boolean flowCorrelated,
                    boolean freshAndNotReplayed) {}

    private static final Map<String, Profile> TRUST = Map.of(
        "corp", new Profile(
            "https://id.corp.test/realm/staff",
            "portal-corp", "north", Set.of("corp-key")),
        "partner", new Profile(
            "https://id.partner.test/realm/client",
            "portal-partner", "south", Set.of("partner-key"))
    );

    static String verify(String trustedRegistration,
                         Evidence evidence,
                         String resourceTenant) {
        Profile profile = TRUST.get(trustedRegistration);

        if (profile == null) {
            return "DENY_UNKNOWN_REGISTRATION";
        }
        if (!profile.issuer().equals(evidence.issuer())) {
            return "DENY_ISSUER";
        }
        if (!profile.audience().equals(evidence.audience())) {
            return "DENY_AUDIENCE";
        }
        if (!profile.keyIds().contains(evidence.keyId())) {
            return "DENY_KEY";
        }
        if (!evidence.signatureVerified()) {
            return "DENY_SIGNATURE";
        }
        if (!evidence.flowCorrelated()) {
            return "DENY_FLOW";
        }
        if (!evidence.freshAndNotReplayed()) {
            return "DENY_REPLAY";
        }
        if (!profile.tenant().equals(evidence.tenant())) {
            return "DENY_TENANT_CLAIM";
        }
        if (!profile.tenant().equals(resourceTenant)) {
            return "DENY_RESOURCE_TENANT";
        }
        return "ALLOW " + trustedRegistration;
    }

    static Evidence evidence(String issuer, String audience,
                             String tenant, String keyId,
                             boolean signature,
                             boolean flow,
                             boolean fresh) {
        return new Evidence(issuer, audience, tenant, keyId,
                            signature, flow, fresh);
    }

    public static void main(String[] args) {
        Evidence corp = evidence(
            "https://id.corp.test/realm/staff",
            "portal-corp", "north", "corp-key",
            true, true, true);

        System.out.println("Valid: "
            + verify("corp", corp, "north"));
        System.out.println("Unknown registration: "
            + verify("attacker", corp, "north"));
        System.out.println("Wrong issuer: "
            + verify("partner", corp, "south"));
        System.out.println("Wrong audience: "
            + verify("corp", evidence(
                "https://id.corp.test/realm/staff",
                "other-api", "north", "corp-key",
                true, true, true), "north"));
        System.out.println("Wrong key scope: "
            + verify("corp", evidence(
                "https://id.corp.test/realm/staff",
                "portal-corp", "north", "partner-key",
                true, true, true), "north"));
        System.out.println("Bad signature: "
            + verify("corp", evidence(
                "https://id.corp.test/realm/staff",
                "portal-corp", "north", "corp-key",
                false, true, true), "north"));
        System.out.println("No state binding: "
            + verify("corp", evidence(
                "https://id.corp.test/realm/staff",
                "portal-corp", "north", "corp-key",
                true, false, true), "north"));
        System.out.println("Replay: "
            + verify("corp", evidence(
                "https://id.corp.test/realm/staff",
                "portal-corp", "north", "corp-key",
                true, true, false), "north"));
        System.out.println("Wrong tenant: "
            + verify("corp", evidence(
                "https://id.corp.test/realm/staff",
                "portal-corp", "south", "corp-key",
                true, true, true), "north"));
        System.out.println("Resource from South: "
            + verify("corp", corp, "south"));
    }
}
~~~

Run with JDK 17+:

~~~bash
javac IssuerTenantSelectionDemo.java
java IssuerTenantSelectionDemo
~~~

**Exact stdout:**

~~~text
Valid: ALLOW corp
Unknown registration: DENY_UNKNOWN_REGISTRATION
Wrong issuer: DENY_ISSUER
Wrong audience: DENY_AUDIENCE
Wrong key scope: DENY_KEY
Bad signature: DENY_SIGNATURE
No state binding: DENY_FLOW
Replay: DENY_REPLAY
Wrong tenant: DENY_TENANT_CLAIM
Resource from South: DENY_RESOURCE_TENANT
~~~

**Explanation:** `trustedRegistration` is assumed to come from a **server-side saved login transaction/approved route**, not arbitrarily from a query param; `keyId` is a hint verified by the validator within the right trusted issuer keyset; tenant checking in the demo is 1:1 for illustration. Production may allow one issuer for multiple tenants while still checking membership. **Never use this demo as a production JwtDecoder, AuthenticationProvider, or SAML verifier.**

## 25. Multi-Tenant and Multi-Issuer Are Two Different Problems

**Multi-issuer:** the API accepts access tokens from multiple Authorization Servers. Each token must be verified with the **exact right issuer/keyset**.

**Multi-tenant:** the app serves multiple organizations, each with its own data, memberships, and entitlements. **Authorization isolation** is required.

Topologies:

| Relationship | Example | Handling |
| --- | --- | --- |
| 1 issuer : 1 tenant | Corp → North | Trusted issuer map + domain membership |
| 1 issuer : many tenants | Shared enterprise OP → North/South | One verifier may suffice; separate tenant checks |
| Many issuers : 1 tenant | Corp + Partner → North | Allow multiple IdPs, separate identity links |
| Many tenants : Many IdPs | SaaS marketplace | Trusted registry (issuer, tenant, registration), local authorization |
| 1 tenant with OIDC + SAML | Migration system | Protocol-specific validators, unified account link |
| User belongs to multiple tenants | Consultant | Grant privileges only for selected tenant and real resource |

**Do not force a 1:1 architecture when reality is 1:n/n:1.** At the same time, never loosen policy so one issuer is trusted by every tenant automatically.

## 26. Home Realm Discovery Is Not Proof

A login page may ask for email and suggest a matching IdP:

~~~text
alice@corp.test
  -> hint: log in with Corp IdP
  -> server selects ClientRegistration corp (trusted)
  -> create state/nonce/PKCE transaction
  -> validate callback and token with Corp config
~~~

**User-entered email does not prove the user belongs to Corp.** Use email domains solely for UX discovery and always recheck identity after login. Never auto-create local accounts/tenant memberships from email.

If using subdomains to pick tenant/IdP, protect Host, Forwarded, and X-Forwarded-* headers as well as aliases/misrouting. Never let `tenant=corp` in a URL grant permission to create a trust registration.

## 27. Sessions, Logout, and Reauthentication

What can happen:

~~~text
09:00 Corp user logs in -> Spring session account A/North
09:30 Admin revokes A's privileges or changes IdP trust
09:40 Old session still holds SecurityContext/GrantedAuthorities
10:00 Browser starts Partner user B login
10:01 Callback/tenant mismatch or principal change
~~~

If the session retains A after B's callback, or A's roles fail to refresh after privilege changes, the wrong identity/entitlement may be used.

**Countermeasures:**
- Session principal change detection, session fixation protection.
- Logout flow per exact source; OIDC logout/SAML SLO if supported, never assuming all IdPs sync automatically.
- Cap maximum session/Authentication snapshot age.
- Re-check active account, trusted issuer/profile, and tenant membership on sensitive permissions.
- Revoke sessions/tokens when an issuer is disabled/compromised per SLA.
- When a user switches tenants, enforce authorization/step-up per policy.
- Coordinate multi-node session/replay caches.
- Do not wait solely for JWT expiration when immediate revocation is needed.

**One successful authentication is not a permanent guarantee of authorization.**

## 28. API, Browser, and SAML Do Not Share the Same Filter Assumptions

A system may have SecurityFilterChains:

~~~text
/login/oauth2/**           -> Spring OAuth2/OIDC login
/oauth2/authorization/**   -> Spring OAuth2 authorization request
/login/saml2/sso/**        -> Spring SAML2 response validation
/saml2/authenticate/**     -> Spring SAML2 AuthnRequest
/api/**                    -> OAuth2 Resource Server access tokens
/admin/**                  -> Elevated authorization policy
~~~

This is a **logical diagram**, not path configuration to copy verbatim; default/framework endpoints can vary by app, and filter order/matchers require real testing.

**Do not:**
- Accept a JWT ID Token at a Bearer API.
- Feed a SAML Assertion to a JWT decoder.
- Use an `X-User` header as a fallback after signature failure.
- Write a custom parser that picks whichever verifier succeeds first.
- Leave an unauthenticated entrypoint routing requests to a looser registration.
- Enable wildcard issuer/certificate trust to temporarily work around a production error.

## 29. Error-Handling Principles

| Error | Handling |
| --- | --- |
| Unknown issuer/JWK source | Reject, do not auto-enroll |
| Invalid signature | Reject, do not fall back to another issuer |
| Wrong JWT audience | API returns 401 |
| OIDC callback issuer/state mismatch | Abort flow, do not send code to wrong token endpoint |
| SAML Issuer/cert/Audience/Recipient mismatch | Authentication failure |
| Expired/replayed Assertion/ID Token | Reject |
| Right issuer user lacking tenant membership | Authorization 403 |
| Member user lacking object permission | Authorization 403 |
| Metadata/JWKS outage | Do not skip validation; handle unavailable per policy |
| Untrusted tenant Host/header | Do not use as trust context |
| Same sub from two IdPs | Keep distinct identities or require linking proof |
| User suspended after login | Revoke/deny per application policy |

**Never log raw JWTs, authorization codes, SAMLResponse, certificate private keys, session cookies, or full NameIDs to public logs.** Use correlation IDs and categorized error codes.

## 30. End-to-End Security Test Matrix

| # | Scenario | Required Outcome |
| --- | --- | --- |
| 01 | Corp issuer, Corp key, right audience | Valid Authentication |
| 02 | Self-signed token from attacker issuer | Unknown issuer, 401 |
| 03 | Partner JWT sent to Corp-only flow | Reject |
| 04 | Corp token meant for Payroll sent to Billing | 401 wrong audience |
| 05 | OIDC ID Token sent to resource server API | Reject token type/audience |
| 06 | Same JWT kid across two issuers | Never use wrong key |
| 07 | JWT with jku pointing to attacker.test | Do not fetch/trust arbitrary URL |
| 08 | JWT alg outside allowlist | Reject |
| 09 | Valid iss with invalid signature | Reject |
| 10 | Expired JWT or not-yet-valid nbf | Reject |
| 11 | One issuer serving North and South | Separate tenant authorization |
| 12 | Corp user without North membership | 403 |
| 13 | Duplicate username/sub across two IdPs | Do not merge accounts |
| 14 | Duplicate email across two tenants | Do not auto-link |
| 15 | Authorization code A, state B | Abort |
| 16 | OAuth callback iss mismatches expected issuer | Abort before token exchange |
| 17 | Expired/reused OAuth state | Reject |
| 18 | Redirect URI mismatches registration | Reject |
| 19 | OIDC nonce mismatch | Reject |
| 20 | Invalid OIDC aud/azp | Reject |
| 21 | SAML Response from IdP B posted to registration A ACS | Reject |
| 22 | Cert B used to sign assertion claiming A | Reject |
| 23 | SAML AudienceRestriction wrong SP entityID | Reject |
| 24 | Wrong SAML Recipient/Destination | Reject |
| 25 | Missing SAML InResponseTo | Reject SP-initiated response |
| 26 | Expired SAML NotOnOrAfter | Reject |
| 27 | SAML assertion ID replay | Reject |
| 28 | XML Signature Wrapping | Never use unsigned identity |
| 29 | Unsolicited SAML when policy forbids | Reject |
| 30 | User modifies metadata URI | Does not alter trusted registration |
| 31 | Dynamic issuer auto-added from JWT iss | Forbidden |
| 32 | Browser alters tenant slug North→South | Membership/object rules return 403 |
| 33 | Group ROLE_ADMIN emitted by Partner | Does not grant Corp admin |
| 34 | Issuer revoked while session active | Sessions/tokens handled per SLA |
| 35 | Key rotation new kid in valid trust set | Accepted per policy |
| 36 | Key rotation unexpected key | Reject |
| 37 | JWKS fetch timeout | Never fall back to another issuer/cert |
| 38 | Tenant admin adds IdP pending approval | Profile pending, not trusted |
| 39 | One tenant has two approved IdPs | Both identity namespaces stay separate |
| 40 | Valid SAML issuer but bad signature | Reject |
| 41 | Valid SAML signature but wrong recipient | Reject |
| 42 | Valid token aud but unauthorized client/actor | Deny per policy |
| 43 | Host/X-Forwarded-Host spoof | Never alters trusted tenant/issuer |
| 44 | Callback carries conflicting issuer identifiers | Reject |
| 45 | Disabled user with unexpired token | Backend denies per SLA |
| 46 | API route matched by wrong SecurityFilterChain | Test catches configuration mismatch |
| 47 | Session user A switched to B | Never reuse stale SecurityContext A |
| 48 | Canaries detect out-of-policy cross-tenant success | Safe rollback and incident handling |

**E2E tests must prove the verifier came from a trusted registration, not merely mock `Authentication.isAuthenticated()==true`.** Test cross-issuer/cross-tenant paths with real tokens/assertions in a controlled test environment.

## 31. Deployment Runbook

### Phase A — Inventory trust configuration

1. Enumerate OIDC/OAuth issuers, SAML IdP entityIDs, and tenant↔registration mappings.
2. Document metadata/JWKS URLs, certs, algorithms, ACS/redirects, client IDs/SP entityIDs, and audiences.
3. Define the stable identity per issuer and local account-linking method.
4. Audit who has permission to add/edit issuers/certs/tenant mappings.
5. Inventory dynamic issuer resolution and any paths opening trust from unverified inputs.
6. Define session/replay/cache lifetimes and revocation SLAs.

### Phase B — Hardening

1. Enforce issuer allowlists and the right Spring multi-issuer resolver.
2. Bind the exact JWKS/certificates/algorithms to each matching issuer.
3. Add JWT audience/token purpose validators per issuer.
4. OAuth multi-AS clients bind state + expected issuer per RFC 9207/9700.
5. OIDC validates iss/aud/nonce/azp and user account linking.
6. SAML validates registration, signature, issuer, recipient, destination, audience, InResponseTo, and replay.
7. Defend against Host/Forwarded spoofing and metadata-fetch SSRF.
8. Map groups through a tenant-specific allowlist.
9. Enforce domain authorization by user account + tenant + resource.

### Phase C — Canary

1. Canaries for Corp/Partner, tenants, and cross-scope tokens.
2. Test authorization-server mix-up with conflicting callback state/issuers.
3. Test SAML XML issuer/cert mismatches and ACS/audience mismatches.
4. Test JWT kid collisions, jku injection, wrong audience, and expired tokens.
5. Test IdP outages, JWKS rotation, certificate rollover, and session revocation.
6. Monitor 401/403/mismatch/replay counters with correlation IDs, without leaking tokens.
7. Sign off on security test results before ramping traffic.

### Phase D — Operations

1. Govern the issuer/cert trust registry with clear owners and audit trails.
2. On compromise: disable issuer/registration and evict sessions/tokens per policy.
3. Never fix outages with wildcard issuers or by dropping signatures.
4. Monitor metadata freshness and fail-closed behavior.
5. Manage migrations between IdPs with linking proofs, never by merging emails.
6. Periodically test cross-tenant access, refresh roles, and review trust drift.

## 32. Monitoring and Audit

These are suggested metrics instrumented by the application, not all emitted out of the box by Spring Security:

| Metric | Meaning |
| --- | --- |
| `federation_unknown_issuer_total` | Untrusted issuer |
| `federation_issuer_mismatch_total` | Token/assertion issuer differs from expected |
| `oauth_mixup_prevented_total` | Callback AS mismatch/state errors |
| `jwt_wrong_audience_total` | Token meant for another API |
| `jwt_invalid_signature_total` | Verification failed |
| `jwks_untrusted_url_rejected_total` | Blocked dynamic key URL |
| `saml_registration_mismatch_total` | Wrong RelyingPartyRegistration |
| `saml_replay_blocked_total` | Assertion replay blocked |
| `tenant_authorization_denied_total` | User not in tenant/resource |
| `identity_link_collision_total` | Colliding user IDs across different issuers |
| `trust_profile_changes_total` | Trust config changed |
| `stale_session_denied_total` | Revoked session/token |

Never put `sub`, email, tokens, raw SAML XML, or user-controlled raw `kid` in metric labels. Record trusted registrationId, policy version, pseudonymous user ID, operation, correlation ID, and decision category.

**High-severity alerts:** sudden spike in unknown issuers; self-signed JWT still getting 200; a Partner-verified user accessing Corp resources without membership; callbacks without state/issuer succeeding; a revoked IdP still minting new sessions.

## 33. Self-Assessment Questions

**1. Is a JWT signature valid against JWKS from a URL declared by the JWT itself trustworthy?**  
No. Issuer and JWKS URI must come from approved trust configuration; a signature consistent with an attacker's key is not authentication.

**2. Can you read an unverified `iss` to select a decoder?**  
Yes, but only as a **candidate hint within a trusted allowlist**, followed by verifying the signature and exact issuer/audience/time/type.

**3. Is `kid` globally unique across the Internet?**  
No; key lookups must be scoped by issuer/registration.

**4. How does OAuth mix-up differ from an ID Token issuer mismatch?**  
Mix-up can cause the client to send the authorization code to the wrong token endpoint **before an ID Token exists**; expected issuer must bind to the transaction and callback.

**5. What parameter does RFC 9207 introduce?**  
`iss` in the authorization response so the client can compare against the expected AS issuer.

**6. What does Spring's `JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers` do?**  
Enables issuer selection across a trusted set; it does not replace audience/type/tenant authorization validators.

**7. Can SAML Response Issuer be used to select RelyingPartyRegistration?**  
It may act as a hint per Spring/flow, but full SAML signature/protocol verification is required before trusting it.

**8. Is a SAML registrationId the same as IdP entityID?**  
No. registrationId is Spring's internal key; IdP entityID is the SAML protocol identifier.

**9. Why validate Recipient and AudienceRestriction?**  
To ensure the assertion is meant for the exact ACS and SP, rejecting assertions issued for other services.

**10. Does a tenant ID in a verified token automatically grant membership?**  
Not by default. The backend must verify server-side tenant membership and resource-level authorization per contract.

**11. Is email enough to link users from two IdPs?**  
No. Verified issuer+subject and linking proof are required.

**12. When Corp's JWKS has an outage, is falling back to Partner's keys reasonable?**  
No. Fail closed; never switch trust contexts.

**13. When one issuer serves two tenants, are two separate JWT validators always needed?**  
Not necessarily; one issuer verifier may suffice, while tenant authorization must stay isolated.

**14. What if IdP-initiated SAML has no InResponseTo?**  
Accept only when policy permits unsolicited login and enforce strict signature/issuer/audience/recipient/replay/login-CSRF protections.

**15. Can an IdP be auto-added to the trust list when a user supplies a metadata URL?**  
No. Owner approval and verification are required.

## 34. Production Checklist

- [ ] Maintain a versioned trusted registry for OIDC issuers and SAML IdP entityIDs.
- [ ] Unknown issuers/IdPs fail closed; no auto-discovery from JWTs.
- [ ] Pre-verification issuer claims or SAML Issuers serve only as candidate hints.
- [ ] Each issuer binds to exact JWKS/signing certs and allowed algorithms.
- [ ] Never trust arbitrary `jku`/`x5u` or use a global `kid` map.
- [ ] JWT APIs validate signature, `iss`, `aud`, `exp`/`nbf`, token purpose, and scopes.
- [ ] OAuth multi-AS login includes RFC 9700/RFC 9207 mix-up defenses or equivalent.
- [ ] OAuth callbacks bind state, expected registration, issuer, PKCE, and redirectUri.
- [ ] OIDC ID Tokens validate `iss`/`aud`/`azp`/`nonce` per flow.
- [ ] Spring `JwtIssuerAuthenticationManagerResolver` uses trusted issuers.
- [ ] SAML RelyingPartyRegistration resolver selects the right registration and trusted signing credentials.
- [ ] SAML Response/Assertion validate Issuer, Destination/Recipient, Audience, Conditions, and signature.
- [ ] SP-initiated SAML verifies AuthnRequest InResponseTo and replay.
- [ ] Unsolicited SAML is not accepted without explicit policy.
- [ ] Local identity links are namespaced by issuer/IdP, not email/username alone.
- [ ] Tenant in URL/header does not grant permission; check membership/resource.
- [ ] Group mapping uses an issuer+tenant allowlist; no automatic ROLE_ADMIN.
- [ ] Client credentials/service identities are separate from user identities; never mix token types.
- [ ] Session logout/revocation policy triggers when IdP/tenant config changes.
- [ ] Tests cover cross-issuer, cross-tenant, kid collision, wrong aud, mix-up, and SAML ACS mismatch.
- [ ] Host/Forwarded spoofing, metadata SSRF, and key rotation are tested.
- [ ] Never log raw tokens, SAML assertions, private keys, or unnecessary PII.
- [ ] During outages, never weaken trust via accept-any-issuer/key/metadata.
- [ ] Canaries, incident runbooks, and fast issuer-disable procedures are in place.

## 35. Conclusion

**IdP, issuer, or tenant confusion is a trust failure, not merely a config naming mix-up.** A validly signed JWT from IdP B must not be accepted under A's trust profile; a validly signed SAML assertion for the wrong SP/ACS must not be used; a verified identity does not automatically have permissions on a caller-chosen tenant.

The safe pipeline is **trusted registration and initiated transaction → candidate selection from allowlist → exact key/issuer/recipient/audience verifier → full protocol validation and replay protection → verified subject within issuer namespace → local account/tenant/resource authorization**.

With Spring Security, leverage **`JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(...)`** for multi-issuer APIs and **`RelyingPartyRegistrationRepository`/Resolver with the OpenSAML provider** for SAML. For OAuth/OIDC clients supporting multiple Authorization Servers, enforce mix-up defenses **before token exchange**, per RFC 9207 and RFC 9700. Tenant authorization is always the backend's responsibility, never a self-granting claim.

### Official References

- Spring Security — Multi-tenancy of OAuth2 Resource Servers: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html
- Spring Security — JWT Resource Server validation: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security — OAuth2 Login: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
- Spring Security — SAML2 Login Overview, registration resolution and OpenSAML validation: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification: https://www.rfc-editor.org/rfc/rfc9207
- RFC 9700 — OAuth 2.0 Security Best Current Practice: https://www.rfc-editor.org/rfc/rfc9700
- RFC 8414 — OAuth 2.0 Authorization Server Metadata: https://www.rfc-editor.org/rfc/rfc8414
- RFC 9068 — JWT Profile for OAuth2 Access Tokens: https://www.rfc-editor.org/rfc/rfc9068
- RFC 7519 — JSON Web Token: https://www.rfc-editor.org/rfc/rfc7519
- OpenID Connect Core 1.0 — Issuer/ID Token Validation: https://openid.net/specs/openid-connect-core-1_0.html
- OASIS SAML 2.0 Core/Profiles/Metadata: https://www.oasis-open.org/standard/saml/
