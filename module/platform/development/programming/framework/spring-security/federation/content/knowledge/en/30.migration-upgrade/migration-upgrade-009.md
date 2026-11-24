# Running Old and New Providers in Parallel Without Mixing Keys or Permissions

## 1. Objectives and Migration Context

An application using **Spring Security - federation** may need to keep accepting logins from a legacy identity provider while rolling out a new provider. Transitions normally move through **pilot, dual run, canary, cutover, drain, and retirement**, rather than replacing the entire configuration overnight. Simply adding two login buttons is not safe enough: users may be misidentified, tokens from one issuer may be verified with another issuer's keys, or old and new permissions may accumulate.

This lesson belongs to **Migration and Upgrade**, focusing on boundaries that must be preserved:

1. **Each IdP / Authorization Server has its own issuer/EntityID, verification public keys, metadata/JWKS, and client/registration.**
2. **A SAML Response / OIDC ID Token / JWT must be verified using the trust configuration belonging to its own provider**, never by searching keys in a global pool across all IdPs.
3. **User identity must carry provenance:** `(issuer or registration, stable subject, tenant)`. Matching email, short username, or display name never proves two identities are the same person.
4. **Permissions are granted by application policy** after the identity is validly linked. Never grant `ROLE_ADMIN` solely because the new IdP emits an `admin` claim.
5. Callback `state`, OIDC `nonce`, SAML `InResponseTo`, `Recipient`, `Audience`, `Issuer`, signatures, and timestamps must never be dropped during migration.
6. Login sessions, authorized clients, refresh tokens, logout, and rollback must keep the exact provider context without mixing credentials.
7. When the new provider fails, fallback may only initiate a **fresh approved authentication flow**, never verifying an old token with another provider's key.

Illustrative environment: **Java 17, Spring Boot 3.3.5, Spring Security 6.3.x**. Applicable to SAML2-to-OIDC, SAML2-to-SAML2, or OIDC-to-OIDC migrations. Hosts under **`example.org`** and identifiers below are technical examples only.

### Two Hypothetical Providers

~~~text
Legacy Identity Provider:
  alias      = legacy
  issuer     = https://idp-old.example.org/realms/corp
  samlEntity = https://idp-old.example.org/saml
  keys       = LEGACY_VERIFICATION_KEYS

Next Identity Provider:
  alias      = next
  issuer     = https://idp-new.example.org/realms/corp
  samlEntity = https://idp-new.example.org/saml
  keys       = NEXT_VERIFICATION_KEYS

Application:
  public origin = https://app.example.org
  tenant        = corp
  resource aud  = api://orders
~~~

## 2. Three Isolation Layers: Trust, Identity, and Authorization

~~~text
                   Application / Login selector
                              |
                  +-----------+-----------+
                  |                       |
         Legacy registration       Next registration
                  |                       |
           Legacy metadata           Next metadata
           Legacy signing cert       Next signing cert
           Legacy JWKS               Next JWKS
           Legacy client secret      Next client secret
                  |                       |
            VERIFIED ISSUER / SUBJECT / TENANT
                  |                       |
                  +-----------+-----------+
                              |
                     Approved identity link
                              |
                        Local account ID
                              |
                      Local RBAC / ABAC policy
                              |
                       Business permissions
~~~

**Trust layer:** Public keys belong strictly to an approved issuer/registration. Another IdP's signing certificate, even if valid and CA-issued, **is insufficient** to verify a Response for an IdP that does not own that key.

**Identity layer:** Only after verifying the token/Assertion may you use the corresponding issuer's stable subject. In OIDC, the **`(iss, sub)`** pair carries identity meaning. In SAML, require **the exact asserting-party registration and a stable NameID or immutable attribute** per contract. Transient NameIDs are not durable.

**Authorization layer:** The application checks the local account/tenant and entitlement policy. A validly signed `roles=admins` claim only means the IdP genuinely sent that claim; **it does not automatically permit calling admin APIs**.

### Example Identity Links

| Verified Source | Stable Subject | Tenant | Approved Local Account |
| --- | --- | --- | --- |
| Legacy SAML, EntityID legacy | `employee-4821` | corp | `account-0042` |
| Next OIDC, issuer next | `7f2b9c` | corp | `account-0042` |
| Next OIDC, issuer next | `employee-4821` | corp | **Unlinked** |
| Next OIDC, issuer next | `7f2b9c` | partner | **Unlinked** |

The first two identities point to the same account **only after an approved linking process** (e.g., immutable HR ID, account-admin review, or verified dual-login linking). Never rely on matching email, `displayName`, or subject strings. Each link should carry status, evidence, approver, timestamps, revocation, and policy version.

**Note:** Legacy and next may use different user directories. Matching emails can belong to two distinct individuals, and emails can change or be reassigned. Never create a new user with an old user's permissions just by matching email.

## 3. Registry Table for Governing Multiple Providers

| Field | Legacy | Next |
| --- | --- | --- |
| Internal Provider ID | `legacy` | `next` |
| SAML `registrationId` | `legacy-saml` | `next-saml` |
| OIDC `registrationId` | `legacy-oidc` | `next-oidc` |
| OIDC issuer | Exact legacy issuer | Exact next issuer |
| SAML IdP EntityID | Legacy EntityID | Next EntityID |
| SAML verification keys | Legacy public certificates | Next public certificates |
| JWKS URL | Legacy trusted JWKS | Next trusted JWKS |
| Client ID/secret | Legacy confidential client | Next confidential client |
| SP EntityID / ACS | Legacy registration values | Next registration values |
| Policy assurance | Legacy MFA/ACR contract | Next MFA/ACR contract |
| Active cohorts | default | pilot |
| IAM owner | legacy team | migration team |
| Lifecycle | enabled, drain, retired | pilot, enabled |

There is no need to enable both protocols on both IdPs. If legacy is SAML and next is OIDC, create only the two registrations **matching the real protocols**, rather than configuring a non-existent IdP/OP.

The provider registry must be backed by change-approved config/secret store/DB. Never construct a JWKS URI by taking an untrusted `iss` and appending a path arbitrarily; that invites **SSRF** and token trust injection. Any dynamic tenant registration requires an allowlist or an approved identity source.

## 4. SAML2: Separate `RelyingPartyRegistration` Per IdP

Spring Security represents each **SP–IdP** pair as a `RelyingPartyRegistration`. With two IdPs, configure two registrations, each with its own **IdP EntityID / SSO endpoint / trusted signing certificates**. `registrationId` is only a routing key, never a substitute for cryptographic issuer validation.

### 4.1. Typical Endpoints

~~~text
GET  /saml2/authenticate/legacy-saml
GET  /saml2/authenticate/next-saml

POST /login/saml2/sso/legacy-saml
POST /login/saml2/sso/next-saml

GET  /saml2/metadata/legacy-saml
GET  /saml2/metadata/next-saml
~~~

Spring can support an ACS without `registrationId` via lookup from request state or response issuer. During migration, explicit `registrationId` paths aid tracing and correlation. Still, the URL path alone does not prove the issuer: the Response must be verified against the right IdP signing cert, Issuer, AudienceRestriction, Recipient/Destination, timestamps, and InResponseTo.

### 4.2. Exact Spring Boot 3.3.5 YAML for Two IdPs

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          legacy-saml:
            entity-id: "https://app.example.org/saml2/service-provider-metadata/legacy-saml"
            assertingparty:
              entity-id: "https://idp-old.example.org/saml"
              sso-url: "https://idp-old.example.org/saml/sso"
              verification:
                credentials:
                  - certificate-location: "classpath:trust/legacy-idp-signing.pem"

          next-saml:
            entity-id: "https://app.example.org/saml2/service-provider-metadata/next-saml"
            assertingparty:
              entity-id: "https://idp-new.example.org/saml"
              sso-url: "https://idp-new.example.org/saml/sso"
              verification:
                credentials:
                  - certificate-location: "classpath:trust/next-idp-signing.pem"
~~~

This is an example Boot configuration supporting multiple registrations. Public PEM certificates must come from **trusted IdP metadata / approved inventory** with IAM-verified fingerprints. Never put private keys on the classpath without secret lifecycle management; in production, prefer secret volumes or managed credentials with tight ACLs.

**Do not put a `verification.credentials` pool containing both IdPs' certificates into both registrations.** If trusting old and new signing certificates **while the legacy IdP rotates its own keys**, both certificates belong to **legacy** during an approved overlap—never add next's certificate as a candidate there.

Additional configuration required with two IdPs:
- Exact SP EntityID and ACS URL per registration; the IdP must issue Assertions for that exact SP/audience.
- Signed AuthnRequest if required by the IdP, using the SP signing private key matching the certificate registered at that IdP.
- EncryptedAssertion if used, with an SP decryption private key specific to that registration, distinct from IdP signing verification keys.
- Logout URLs/`SessionIndex`/issuer signed by the exact provider; never cross-route SLO between IdPs.
- Independent metadata refresh/repository caching per IdP, with audited key fingerprints/rotation.

### 4.3. `SecurityFilterChain` for Spring SAML Handling

This snippet is for a **SAML2-only app** that already has `spring-boot-starter-security` and `spring-security-saml2-service-provider` dependencies and matching YAML/certificates:

~~~java
package com.example.saml;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfig {
    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/choose-idp").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Boot builds `RelyingPartyRegistrationRepository` from YAML unless overridden by another bean. If implementing `InMemoryRelyingPartyRegistrationRepository` manually, include both `legacy` and `next` registrations. A static repository built from metadata at startup **does not automatically refresh** when an IdP rotates certificates; plan rebuild/cache refresh and verify across all nodes.

**Cross-provider SAML negative test:** send a `next`-signed Response to the `legacy` ACS; it must fail on issuer/trust/correlation. Send a Response with a valid signed Assertion targeting `legacy` SP audience to the `next` registration; it must fail. Never trust an untrusted `<ds:KeyInfo>` certificate carried inside the Response. Never parse XML manually to extract a principal from a different element than the signed one (XML Signature Wrapping).

### 4.4. SP-Initiated vs. IdP-Initiated

During parallel runs, prefer **SP-initiated login** so AuthnRequest/state and registration are explicit. IdP-initiated SSO lacks a matching AuthnRequest and has distinct profile and login-CSRF considerations; never relax `InResponseTo`/Issuer/Recipient checks just to make an unreviewed flow work. Even when IdP-initiated is allowed by contract, key isolation and SAML signatures remain mandatory.

## 5. OIDC: Two `ClientRegistration`s with Separate State/Nonce

### 5.1. OAuth2/OIDC Flow with Two Issuers

~~~text
User chooses legacy:
  /oauth2/authorization/legacy-oidc
  -> legacy authorization endpoint
  -> /login/oauth2/code/legacy-oidc
  -> token endpoint legacy
  -> ID Token verified with legacy issuer/JWKS and legacy client_id

User chooses next:
  /oauth2/authorization/next-oidc
  -> next authorization endpoint
  -> /login/oauth2/code/next-oidc
  -> token endpoint next
  -> ID Token verified with next issuer/JWKS and next client_id
~~~

Each flow has its own server-stored OAuth authorization request, **`state` against CSRF**, OIDC **`nonce` against token replay/mix-up** when used by the profile, PKCE per client/profile, registered redirect URI, and matching issuer/client ID. **Never decode a `next` ID Token with the `legacy` client registration** when a callback path is misrouted.

### 5.2. Spring Boot 3.3.5 YAML

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          legacy-oidc:
            provider: legacy-provider
            client-id: "legacy-web-client"
            client-secret: "${LEGACY_OIDC_CLIENT_SECRET}"
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]
          next-oidc:
            provider: next-provider
            client-id: "next-web-client"
            client-secret: "${NEXT_OIDC_CLIENT_SECRET}"
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]

        provider:
          legacy-provider:
            issuer-uri: "https://idp-old.example.org/realms/corp"
          next-provider:
            issuer-uri: "https://idp-new.example.org/realms/corp"
~~~

Each secret must belong to one client at the right OP, loaded from a managed secrets store/environment; never copy the legacy secret for next. The issuer URI must match trusted discovery exactly—never append client-supplied hostnames, query strings, or trailing slashes. URLs above are technical placeholders, not real endpoints.

### 5.3. OIDC Login `SecurityFilterChain`

~~~java
package com.example.oidc;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OidcSecurityConfig {
    @Bean
    SecurityFilterChain chain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/choose-idp").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

For an application needing **both SAML2 login and OAuth2 login simultaneously**, do not copy two catch-all `SecurityFilterChain`s with overlapping matchers and hope Spring picks the right one. Either use a single chain configuring both `.saml2Login(...)` and `.oauth2Login(...)`, or multiple chains with explicit `@Order`/`securityMatcher`. Test callbacks blocked by another chain, session cookies, and CSRF.

### 5.4. Provenance After OIDC Authentication

In Spring Security 6.3, **`OAuth2AuthenticationToken.getAuthorizedClientRegistrationId()`** reports which client registration was used. For a verified OIDC user, also extract the ID Token's issuer and stable subject, then look up the local identity link. Never take `provider` from a query parameter or an unverified attribute to place in `SecurityContext`.

Conceptual example:

~~~text
protocol             = OIDC
registration         = next-oidc
verified_issuer      = https://idp-new.example.org/realms/corp
verified_sub         = 7f2b9c
tenant               = corp
local_account_id     = account-0042
effective_permissions= ORDERS_READ
~~~

The fields above are an **internal model**, not claims Spring logs automatically. All are derived after signature/issuer/audience/state/nonce validation. The OIDC ID Token audience must be the **web `client_id`**, not the business API's `api://orders`.

## 6. API JWT: Issuer-Specific Keysets, Never One Global JWKS

During a migration, an API may temporarily accept access tokens from two Authorization Servers. Accepting two issuers **does not mean** accepting tokens signed by any public key from either side.

~~~text
Incoming Bearer JWT
     |
Parse unverified iss for exact allowlist lookup ONLY
     |
     +-- old issuer -> OLD decoder -> OLD JWKS, old alg policy
     |
     +-- new issuer -> NEW decoder -> NEW JWKS, new alg policy
     |
Verify signature WITH SELECTED ISSUER KEYSET
Check iss exactly, aud=api://orders, exp/nbf, token type
     |
Verified (issuer, sub, tenant) -> approved link -> local roles
     |
Resource authorization
~~~

`kid` values can collide across two issuers. Never build a global `Map<String kid, PublicKey>`; key selection must reside inside an **issuer-scoped trusted decoder**. Token-supplied JWT headers `jku`/`x5u` must never be used to download arbitrary key URLs. If a JWT claims `iss=old` yet is signed with next's private key, the old decoder must reject it.

### 6.1. Simple Configuration from Spring Security 6.3

~~~java
JwtIssuerAuthenticationManagerResolver resolver =
    JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
        "https://idp-old.example.org/realms/corp",
        "https://idp-new.example.org/realms/corp");

http.oauth2ResourceServer(oauth2 ->
    oauth2.authenticationManagerResolver(resolver));
~~~

This snippet is a **fragment**, not a full app. The resolver only treats the two issuers as trusted; reading unverified `iss` is strictly for **allowlist routing**, after which that issuer's decoder verifies signature/issuer/time. You still must validate **API audience**, token type, and authorization. For dynamic tenant registration, add issuers only after admin approval—never auto-create decoders from token input.

### 6.2. Full Per-Issuer Spring Resource Server Java Config

A dedicated API application has Maven dependencies:
- `spring-boot-starter-web`
- `spring-boot-starter-security`
- `spring-boot-starter-oauth2-resource-server`

The configuration below uses **two separate known JWKS URIs and two separate decoders**, accepting **RS256** by illustration. Replace URLs with real `jwks_uri` values from trusted discovery and tune algorithms per approved policy. Never use this code as an endpoint receiving web ID Tokens.

**`MultiIssuerApiSecurity.java`**:

~~~java
package com.example.api;

import java.util.Collection;
import java.util.List;
import java.util.Map;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationProvider;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerAuthenticationManagerResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MultiIssuerApiSecurity {
    private static final String OLD =
        "https://idp-old.example.org/realms/corp";
    private static final String NEXT =
        "https://idp-new.example.org/realms/corp";
    private static final String AUD = "api://orders";

    @Bean
    AuthenticationManagerResolver<HttpServletRequest> resolver() {
        Map<String, AuthenticationManager> approved = Map.of(
            OLD, newManager(OLD,
                "https://idp-old.example.org/realms/corp/keys"),
            NEXT, newManager(NEXT,
                "https://idp-new.example.org/realms/corp/keys"));
        return new JwtIssuerAuthenticationManagerResolver(approved::get);
    }

    private static AuthenticationManager newManager(
            String issuer, String trustedJwksUri) {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(trustedJwksUri)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains(AUD)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error("invalid_token",
                        "Wrong audience", null));

        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
            JwtValidators.createDefaultWithIssuer(issuer), audience));

        JwtAuthenticationConverter authorityConverter =
            new JwtAuthenticationConverter();
        authorityConverter.setJwtGrantedAuthoritiesConverter(
            jwt -> localAuthorities(jwt));

        JwtAuthenticationProvider provider =
            new JwtAuthenticationProvider(decoder);
        provider.setJwtAuthenticationConverter(authorityConverter);
        return provider::authenticate;
    }

    private static Collection<GrantedAuthority> localAuthorities(
            Jwt verifiedJwt) {
        String issuer = verifiedJwt.getIssuer().toString();
        String sub = verifiedJwt.getSubject();

        // Demo only: approved links for both identities.
        boolean linked =
            (OLD.equals(issuer) && "old-user-17".equals(sub))
            || (NEXT.equals(issuer) && "new-sub-98".equals(sub));

        if (!linked) return List.of();
        return List.of(new SimpleGrantedAuthority("ORDERS_READ"));
    }

    @Bean
    SecurityFilterChain api(
            HttpSecurity http,
            AuthenticationManagerResolver<HttpServletRequest> resolver)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/orders").hasAuthority("ORDERS_READ")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .authenticationManagerResolver(resolver));
        return http.build();
    }
}
~~~

**Limitations of the sample code:**

- `/keys` JWKS URLs are **examples**; different OP products expose different endpoints. Use only real URIs from issuer discovery or approved configuration.
- `JwtValidators.createDefaultWithIssuer` retains `iss` and `exp`/`nbf` checks; the custom `aud` validator is added without replacing default validators.
- If the new issuer emits an `admin` role in a signed JWT, the converter still grants only `ORDERS_READ` per the approved local link. Production replaces the hardcoded map with an identity-link DB and permission service including tenants, role revocation, step-up, and auditing.
- Unknown subjects may still authenticate at the framework level if signature/claims are valid, yet hold zero local business permissions; `/api/orders` denies them. If policy requires rejecting all unlinked accounts at the authentication layer, add explicit rejection logic.
- This snippet is a full Spring bean config **for an API app**; never combine it with web SAML/OIDC catch-all chains without designing `securityMatcher`.
- JWKS fetching/caching must stay isolated per issuer; never fall back to another keyset on error.
- Unverified header/claim `iss`/`kid` are used only for key selection within a known registry; final signature and claim validation govern `Authentication`.
- Implement explicit token-type checks to prevent **JWT access token vs. OIDC ID Token confusion**. Audience validation alone may not prove token purpose if issuer/token formats do not sufficiently distinguish them.

## 7. Runnable Java 17: Simulating Key Isolation and Local Privileges

The following program uses **real RSA SHA-256 signatures** for two keypairs, yet **is not a SAML/JWT verifier**. It signs a demonstration structure joined with `|` without JOSE standards or canonicalization; **never use this serialization in production**. Its job is to show that the verifier must select keys by issuer, still verify aud/time/tenant, and use only **approved local identity links** to grant permissions.

**`ParallelProviderLab.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.util.Map;
import java.util.Set;

public class ParallelProviderLab {
    static final String OLD =
        "https://idp-old.example.org/realms/corp";
    static final String NEXT =
        "https://idp-new.example.org/realms/corp";
    static final String AUDIENCE = "api://orders";
    static final long NOW = 2_000_000_000L;

    record Provider(String code, PublicKey key, String tenant) {}
    record Account(String id, Set<String> permissions) {}
    record Message(String issuer, String audience, String subject,
                   String tenant, String claimedRole, long expiresAt,
                   byte[] signature) {
        String dataForDemo() {
            return String.join("|", issuer, audience, subject,
                tenant, claimedRole, Long.toString(expiresAt));
        }
    }

    static Message signed(String issuer, String audience, String subject,
            String tenant, String claimedRole, long expires,
            PrivateKey key) throws GeneralSecurityException {
        Message unsigned = new Message(issuer, audience, subject,
            tenant, claimedRole, expires, new byte[0]);

        Signature sig = Signature.getInstance("SHA256withRSA");
        sig.initSign(key);
        sig.update(
            unsigned.dataForDemo().getBytes(StandardCharsets.UTF_8));
        return new Message(issuer, audience, subject, tenant,
            claimedRole, expires, sig.sign());
    }

    static String validate(Message m, Map<String, Provider> providers,
            Map<String, Account> links, String permission)
            throws GeneralSecurityException {
        Provider p = providers.get(m.issuer());
        if (p == null) return "REJECT UNKNOWN_ISSUER";

        Signature signature = Signature.getInstance("SHA256withRSA");
        signature.initVerify(p.key());
        signature.update(
            m.dataForDemo().getBytes(StandardCharsets.UTF_8));
        if (!signature.verify(m.signature())) {
            return "REJECT WRONG_PROVIDER_KEY";
        }

        if (!AUDIENCE.equals(m.audience()))
            return "REJECT AUDIENCE";
        if (NOW >= m.expiresAt())
            return "REJECT EXPIRED";
        if (!p.tenant().equals(m.tenant()))
            return "REJECT TENANT";

        String identity = p.code() + "|" + m.subject()
            + "|" + m.tenant();
        Account a = links.get(identity);
        if (a == null) return "REJECT UNLINKED_SUBJECT";

        // A role in the token does not automatically become an application role.
        if (!a.permissions().contains(permission))
            return "DENY LOCAL_PRIVILEGE";
        return "ALLOW " + a.id() + " " + permission;
    }

    static void show(String label, Message m,
            Map<String, Provider> trust, Map<String, Account> links,
            String permission) throws GeneralSecurityException {
        System.out.println(label + ": " +
            validate(m, trust, links, permission));
    }

    public static void main(String[] args)
            throws GeneralSecurityException {
        KeyPairGenerator g = KeyPairGenerator.getInstance("RSA");
        g.initialize(2048);
        KeyPair oldKey = g.generateKeyPair();
        KeyPair nextKey = g.generateKeyPair();

        Map<String, Provider> trust = Map.of(
            OLD, new Provider("old", oldKey.getPublic(), "corp"),
            NEXT, new Provider("next", nextKey.getPublic(), "corp"));

        Account employee = new Account(
            "account-0042", Set.of("ORDERS_READ"));
        Map<String, Account> links = Map.of(
            "old|old-user-17|corp", employee,
            "next|new-sub-98|corp", employee);

        Message oldOk = signed(
            OLD, AUDIENCE, "old-user-17", "corp", "reader",
            NOW + 300, oldKey.getPrivate());
        Message nextOk = signed(
            NEXT, AUDIENCE, "new-sub-98", "corp", "reader",
            NOW + 300, nextKey.getPrivate());
        Message claimsAdmin = signed(
            NEXT, AUDIENCE, "new-sub-98", "corp", "ADMIN",
            NOW + 300, nextKey.getPrivate());

        show("old valid", oldOk, trust, links, "ORDERS_READ");
        show("next linked", nextOk, trust, links, "ORDERS_READ");
        show("new claims admin", claimsAdmin, trust, links,
            "ORDERS_READ");
        show("admin endpoint", claimsAdmin, trust, links, "ADMIN");

        Message unknown = signed(
            "https://evil.example.org", AUDIENCE, "old-user-17",
            "corp", "reader", NOW + 300, oldKey.getPrivate());
        show("unknown issuer", unknown, trust, links, "ORDERS_READ");

        Message crossKey = signed(
            OLD, AUDIENCE, "old-user-17", "corp", "reader",
            NOW + 300, nextKey.getPrivate());
        show("cross provider key", crossKey, trust, links, "ORDERS_READ");

        Message sameName = signed(
            NEXT, AUDIENCE, "old-user-17", "corp", "reader",
            NOW + 300, nextKey.getPrivate());
        show("same subject unlinked", sameName, trust, links,
            "ORDERS_READ");

        Message modified = new Message(
            NEXT, AUDIENCE, "new-sub-98", "corp", "ADMIN",
            NOW + 300, nextOk.signature());
        show("tampered role", modified, trust, links, "ORDERS_READ");

        Message wrongAud = signed(
            OLD, "api://other", "old-user-17", "corp", "reader",
            NOW + 300, oldKey.getPrivate());
        show("wrong audience", wrongAud, trust, links, "ORDERS_READ");

        Message wrongTenant = signed(
            NEXT, AUDIENCE, "new-sub-98", "partner", "reader",
            NOW + 300, nextKey.getPrivate());
        show("wrong tenant", wrongTenant, trust, links, "ORDERS_READ");

        Message expired = signed(
            NEXT, AUDIENCE, "new-sub-98", "corp", "reader",
            NOW - 1, nextKey.getPrivate());
        show("expired", expired, trust, links, "ORDERS_READ");
    }
}
~~~

Run standalone on Java 17:

~~~bash
javac ParallelProviderLab.java
java ParallelProviderLab
~~~

**Exact stdout** when run on standard JDK 17; RSA keypairs are randomly generated yet results are always consistent:

~~~text
old valid: ALLOW account-0042 ORDERS_READ
next linked: ALLOW account-0042 ORDERS_READ
new claims admin: ALLOW account-0042 ORDERS_READ
admin endpoint: DENY LOCAL_PRIVILEGE
unknown issuer: REJECT UNKNOWN_ISSUER
cross provider key: REJECT WRONG_PROVIDER_KEY
same subject unlinked: REJECT UNLINKED_SUBJECT
tampered role: REJECT WRONG_PROVIDER_KEY
wrong audience: REJECT AUDIENCE
wrong tenant: REJECT TENANT
expired: REJECT EXPIRED
~~~

**Interpreting the negative cases:**

- A token claiming `issuer=old` yet signed with `next`'s private key is rejected because the public key is fetched from the `old` registry.
- Subject `old-user-17` under issuer `next` does not automatically have an account link even though the subject string matches `old`.
- `next`'s signer validly signs the `ADMIN` claim, yet local policy allows only `ORDERS_READ`, so the admin endpoint denies access.
- A signed token with wrong audience/tenant/time is still rejected after signature verification passes.
- Altering the role after signing invalidates the signature.
- This code clarifies the trust and policy model only; it does not replace SAML XML-DSig, JWT/JWS parsers, PKIX, nonces, `InResponseTo`, scopes, cookie sessions, or IdP SSO integration.

## 8. Role Mapping and Privilege Isolation

Every user migrating from `legacy` to `next` needs an **approved effective authority mapping**, not just a login-success check.

| Verified Issuer | External Group/Claim | Suggested Local Permission | Conditions |
| --- | --- | --- | --- |
| Legacy | `groups=CN=OrdersRead` | `ORDERS_READ` | Linked active account, tenant `corp`. |
| Next | `roles=orders-reader` | `ORDERS_READ` | IAM migration mapping approved. |
| Legacy | `groups=CN=OrdersAdmin` | `ORDERS_ADMIN` | Privileged review, MFA/step-up. |
| Next | `roles=admins` | **Do not auto-map** | Review group semantics/approval separately. |
| Next | `email=alice@example.org` | **Grant no permissions** | Email is not an entitlement. |

An IdP may attest attributes yet has no inherent authority to grant application permissions. When groups are permitted as an entitlement source, mappings must specify **provider issuer, claim namespace/value, tenant, application, permission, approval, and expiry**. Sensitive privileges should come from local IAM/IGA or a controlled policy engine.

**Never union authorities across sessions:** A user logs in via the old IdP with admin rights under legacy policy, then switches to `next` as a reader; the app must recompute effective permissions from the local account and current policy. Never retain `ROLE_ADMIN` in `SecurityContext` simply because it appeared in an earlier session.

Account linking must resist takeover: accounts disabled in `legacy` or `next` must never be revived via matching email; password resets at the new IdP do not prove ownership of a legacy account; privileged linking requires re-verification.

## 9. Routing Migration and Mix-Up Prevention

### 9.1. Pilot / Canary Feature Flags

A server-side cohort selector can be used:

~~~text
tenant=corp, cohort=default -> legacy
tenant=corp, cohort=pilot   -> next
tenant=corp, approvedUserChoice=true -> one of allowlisted providers
~~~

A `provider=next` query parameter is only a **request to start a flow via a known registration**, never a command to alter JWKS URIs, EntityIDs, or permissions. Before redirecting, bind the original registration and `state`/nonce or SAML AuthnRequest ID/correlation to the session/TTL. On callback, verify that exact original registration **even if a feature flag flipped in between**.

If tenant routing uses subdomains or proxy headers, trust `Host`/`Forwarded` headers only after the reverse proxy strips user-supplied headers and the app checks an approved hostname allowlist. After authentication, still check the local account's tenant; host headers do not grant permissions.

### 9.2. Login Failure Does Not Mean Retrying the Other Provider with the Same Token

When a `next` token fails signature verification or `state` mismatches, **never** run the `old` decoder "just to try." If policy permits fallback, send the user back to the login chooser and start a **fresh flow** with its own AuthnRequest/state/code. Never reuse a `SAMLResponse`, OAuth authorization code, single-use CAS ticket, or access token under another provider.

### 9.3. OIDC Issuer Mix-Up

When two OPs serve one RP, bind the callback endpoint receiving the authorization response to the **issuer and client registration selected before redirect**, then validate the code/ID Token against that exact OP. Even with `state` checked, mitigate issuer mix-up per OAuth/OIDC profiles and provider support. Never construct redirect URIs dynamically from untrusted input or exchange callback codes at a different token endpoint.

### 9.4. MFA/Assurance

Legacy may use phishing-resistant MFA while next uses passwords only; never assume account migration preserves assurance automatically. Tie sensitive local operations to approved MFA/ACR/AMR policies and verified provider claims. If `next` lacks sufficient assurance, allow low-risk logins if policy permits while denying privileged actions.

## 10. Sessions, Tokens, and Logout While Both IdPs Are Active

Distinguish three session layers:

~~~text
Legacy IdP SSO session          Next IdP SSO session
          \                              /
           \                            /
                  Application HttpSession
                   Spring SecurityContext

OAuth2 authorized clients:
  legacy-oidc client -> legacy access/refresh tokens
  next-oidc client   -> next access/refresh tokens
~~~

**Local logout** invalidates the Spring `HttpSession` yet does not automatically log out either IdP browser session. OIDC RP-initiated logout must use the exact issuer's `end_session_endpoint`/ID Token hint/redirect contract; SAML Single Logout requires the exact registration, signed request/response, and `SessionIndex`. Never send a `next` refresh token to the `legacy` token endpoint.

Operational rules:

1. Store verified authentication provenance in the server-side session: protocol, provider alias, issuer, local account link, tenant, and policy version.
2. When switching providers, never add old permissions onto new permissions; rebuild `Authentication` and rotate session IDs for session fixation protection.
3. Store/load OAuth2 authorized clients keyed to their exact client registration. On unlinking/revoking a provider, clean up associated tokens/cookies per policy.
4. Any `remember-me` or persistent login must be audited; never re-create privileged accounts from a retired provider.
5. `Secure`, `HttpOnly`, `SameSite`/CSRF state, HTTPS proxies, and callback paths must be right. Never skip CSRF just because the IdP signed the assertion.
6. For active `old` sessions prior to cutover, decide explicitly whether to **let them finish TTL or revoke and force re-login**; never assume disabling the login route revokes active sessions.
7. Across multiple nodes, ensure uniform session stores, observable metadata/JWKS cache versions, and zero stale authorization policies.
8. Global logout must be supported by the respective OP/IdP; the app must never claim the workstation or IdP is fully logged out on its own.
9. Separate token types: OIDC ID Tokens are for the RP; JWT access tokens are for APIs with distinct `aud`/resource policies.
10. If an issuer's private signing key is compromised, evaluate revoking related sessions/tokens rather than retaining shared authorities indefinitely.

## 11. Key Rotation Within One IdP vs. Migrating Between Two IdPs

Distinguish:

~~~text
Planned rollover belonging to legacy issuer:
  legacy -> [legacy-sign-v1, legacy-sign-v2]

Planned rollover belonging to next issuer:
  next   -> [next-sign-v1, next-sign-v2]

Wrong:
  legacy -> [legacy-sign-v1, next-sign-v1]
  next   -> [legacy-sign-v1, next-sign-v1]
~~~

An IdP may publish old+new public keys during an approved overlap window before rotating its signing private key. **That overlap belongs strictly inside the same trusted issuer/registration.** Never pull keys from `next` to verify a Response/token claiming issuer `old`.

Never share a private signing key between two IdPs without security architecture approval: it widens compromise blast radius and breaks crypto isolation. Even with matching `kid`s, two JWK Sets must stay in separate issuer namespaces. If one node caches old metadata while another has new metadata, roll out refreshes systematically rather than widening trust to all keys across providers.

## 12. Migration Phases and Quality Gates

### Phase 0 — Inventory

Record owners, SAML EntityIDs/metadata, OIDC issuers/client IDs, signing cert fingerprints, JWKS URIs, SP EntityID/ACS, redirect URIs, logout, service accounts, API audiences, group mappings, local account stores, session TTLs, MFA, and clients not yet supporting the new OP. Never export private keys or secrets into the inventory sheet.

### Phase 1 — Shadow Provisioning / Testing

Create the `next` client/registration on the new IdP, import approved public verification credentials, and test signed fixtures. Build the identity-link table and local authority policy, especially for privileged users. Keep all tests in a sandbox with separate keypairs.

### Phase 2 — Pilot

Direct an authorized cohort to `next` while keeping `legacy` as default. Compare local account IDs/permissions for the same linked user, not just username/email. Test callback loops, browser policies, session handling, and MFA assurance.

### Phase 3 — Canary Ramp

Increase traffic for new logins in waves (e.g., 1% → 5% → 25% → 50% → 100%; **no mandatory fixed percentages**). Expand each wave only if:
- Login success rates and latency meet SLOs.
- **Cross-provider token acceptance equals 0.**
- **Unlinked subjects holding business permissions equals 0.**
- Privileged role drift shows zero unapproved escalations.
- `state`/`nonce`/`InResponseTo`/audience/issuer negative tests still reject.
- Safe rollback routes and alerts are active.

### Phase 4 — Default Cutover

Switch the default for **new logins** to `next` without altering registrations of pending callbacks. Keep `legacy` for approved cohorts if migrating service accounts, older browser integrations, admin workflows, or session drains is still underway.

### Phase 5 — Drain/Retire Legacy

Set deadlines for legacy logins, JWT issuance, and app sessions/tokens. Align TTL/revocation behavior. Once all clients have migrated, remove the legacy issuer from the API trust allowlist, remove legacy SAML registrations/metadata/keys, and revoke client secrets and IdP integrations via change approval. Never leave trust/key/privilege fallbacks active indefinitely.

## 13. Rollback Does Not Mean Mixing Keys

When the `next` IdP suffers an outage, safe rollback switches **new login routing** back to `legacy` per approval—never letting the `legacy` verifier accept `next`-signed tokens. Runbook:

1. Freeze rollout; identify timestamps, cohorts, error codes, and affected nodes/regions.
2. Categorize failure: trust/key mismatch, redirect/state, identity link, role mapping, or IdP availability.
3. Restore the default login route to `legacy` if `legacy` remains trusted/operational and policy allows.
4. Pending callbacks must still check their original registration/state; never force them through the new provider via flags.
5. Handle active `next` sessions per risk: invalidate/re-authenticate, or let them finish TTL if policy allows.
6. Never merge audiences, keys, issuer allowlists, or privileged roles.
7. Run smoke + negative tests and verify business permissions.
8. Record audit trail, RCA, corrective actions, and criteria to resume canary.

If rolling back due to a **private signing key compromise** at `next`, revoke trust/keys per incident policy and terminate impacted sessions; never cite availability to retain a compromised issuer or key.

## 14. Test Matrix for SAML, OIDC, JWT, and Permissions

Use **synthetic signed fixtures**: to test issuer/audience validators independently, build a validly signed message/token with an intentionally wrong issuer or audience. Modifying the payload after signing makes the signature fail first and leaves claim validators untested.

| # | Scenario | Secure Outcome |
| --- | --- | --- |
| 1 | Legacy SAML validly signed with right issuer/ACS/conditions | Passes if local policy permits. |
| 2 | Next SAML validly signed with right issuer/ACS/conditions | Passes. |
| 3 | Next `SAMLResponse` sent to legacy ACS | Reject cross-provider. |
| 4 | Legacy `SAMLResponse` sent to next ACS | Reject cross-provider. |
| 5 | Validly signed SAML with wrong `AudienceRestriction` | Reject. |
| 6 | Wrong SAML Recipient/Destination | Reject. |
| 7 | SAML `InResponseTo` mismatches AuthnRequest | Reject. |
| 8 | SAML Assertion replay | Reject. |
| 9 | SAML NameID altered after signing | Reject signature. |
| 10 | XML Signature Wrapping: signed Alice, unsigned Mallory | Never grants Mallory principal. |
| 11 | Attacker X.509 cert inside SAML `KeyInfo` | Never auto-trusted. |
| 12 | Legacy signed with approved legacy rollover key | Passes during overlap. |
| 13 | Next public key mistakenly added to legacy trust | Security QA FAIL. |
| 14 | Unapproved IdP-initiated SAML | Rejected/unavailable; checks never dropped. |
| 15 | Legacy OIDC login with right issuer/`client_id`/nonce | Passes. |
| 16 | Next OIDC login with right issuer/`client_id`/nonce | Passes. |
| 17 | Legacy callback carrying next `state` | Reject. |
| 18 | Next callback carrying legacy authorization code | Reject. |
| 19 | OIDC ID Token with right issuer yet another client's `aud` | Reject. |
| 20 | Mismatched OIDC `nonce` | Reject. |
| 21 | Client-supplied provider URL outside allowlist | Reject routing. |
| 22 | Feature flag flips between redirect and callback | Retains original registration/correlation. |
| 23 | Legacy JWT signed with old key, old `iss`, right API `aud` | Passes if local entitlement permits. |
| 24 | Next JWT signed with new key, new `iss`, right API `aud` | Passes if local entitlement permits. |
| 25 | JWT with `iss=old` signed by next private key | Reject. |
| 26 | JWT with `iss=next` signed by old private key | Reject. |
| 27 | Non-allowlisted JWT issuer | Reject; never build arbitrary decoder. |
| 28 | Same `kid` in old and next | Select key strictly from allowlisted issuer. |
| 29 | JWT `jku` pointing to attacker host | Never fetch arbitrary JWKS. |
| 30 | JWT `alg=none` or disallowed algorithm | Reject. |
| 31 | JWT `aud` for a different API | Reject even with valid signature. |
| 32 | Expired JWT `exp` or future `nbf` | Reject time. |
| 33 | New issuer JWKS times out | Never fall back to old signing keys. |
| 34 | Two IdPs share same email without link | Never auto-merge accounts. |
| 35 | Two issuers share same short subject | Never treat as one identity. |
| 36 | Approved old/new links to one local account | Permissions stay consistent per local policy. |
| 37 | New provider sends `Admin` role | Never auto-grants `ROLE_ADMIN`. |
| 38 | Legacy admin logs in, then next reader logs in | Never union old+new authorities. |
| 39 | Verified next subject yet unlinked | Never receives `ORDERS_READ`. |
| 40 | Tenant `corp` identity accesses `partner` resource | Deny tenant. |
| 41 | Old refresh token sent to next token endpoint | Reject. |
| 42 | OAuth authorized clients store old/new tokens | Scoped to registration; never cross-reused. |
| 43 | Legacy SAML SLO affects next session | Cross-provider requests never trusted. |
| 44 | App logout while IdP sessions stay active | Never claim global logout. |
| 45 | Next outage, approved fallback to legacy | Fresh flow, fresh state/nonce. |
| 46 | Default route rollback | Key/issuer isolation remains intact. |
| 47 | Legacy JWT after issuer retired from API trust | Reject. |
| 48 | Next private signing key compromised | Revoke that issuer, review sessions. |
| 49 | Pod A and B hold different metadata/JWKS versions | Detect and fix cache parity. |
| 50 | Raw `SAMLResponse`/JWT/secret appears in logs | Security QA FAIL. |
| 51 | Local account disabled despite valid identity | Deny. |
| 52 | Verified identity lacking local business role | 403/deny. |
| 53 | Spoofed `Host`/`Forwarded` headers trying to switch tenant | Blocked by trusted routing + post-auth tenant checks. |
| 54 | Replayed callback/auth code | Reject. |
| 55 | New issuer MFA weaker than admin requirement | Step-up/deny privileged action. |

**Acceptance must rely on negative cases as well**, not just login success. Cross-issuer acceptance and privilege escalation are immediate rollout stoppers.

## 15. Troubleshooting

| Symptom | Investigation Path |
| --- | --- |
| Next SAML invalid signature | Next EntityID, trusted signing public cert, metadata refresh; never pull legacy cert. |
| `SAMLResponse` hits wrong ACS | IdP callback registration, SP EntityID, reverse proxy, correlation. |
| OIDC callback invalid state | Session cookie, state repository, wrong registration, feature flag changed mid-flow. |
| OIDC ID Token `aud` mismatch | Mixed up client ID/registration. |
| Unknown JWT issuer | Exact allowlist; never use arbitrary JWT claims as issuer config. |
| Invalid JWT signature despite matching `kid` | Check issuer-specific JWKS, key bytes/rotation/cache. |
| Valid JWT yet API 403 | Approved account link/entitlements/tenant; never open wildcard roles. |
| Same email logs into wrong account | No email auto-linking; verify immutable IDs and approved links. |
| Admin role appears after migration | Role converter, group mapping namespace, stale `SecurityContext`. |
| Old session stays alive after next login | Session lifecycle and authority unioning; invalidate/reauth. |
| Only one node fails next login | Cache/metadata/keyset parity, SSL trust, deployment. |
| Logging out of next doesn't log out of legacy | Two independent IdP sessions; separate SLO contracts. |
| Rollback causes login loop | Pending state/nonce, cookie `SameSite`, right issuer callback. |

## 16. Observability and Auditing

Log **after authentication is verified**, never logging raw assertions or tokens:

~~~text
event=federation.authentication.completed
trace_id=trace-demo-a91
protocol=OIDC
provider_alias=next-oidc
issuer_alias=next
client_registration=next-oidc
tenant=corp
local_account_id=account-0042
identity_link_version=v3
entitlement_policy_version=policy-2026-11
result=SUCCESS
~~~

Values are illustrative only, not Spring auto-logs. Never log raw `SAMLResponse`s, ID Tokens, JWT access tokens, refresh tokens, cookies, private keys, full group attributes, DNs, or unnecessary PII.

Useful metrics:
- `federation_logins_total` by provider alias/protocol/result.
- `federation_auth_failures_total` by provider/reason (signature, wrong issuer, audience, state, nonce).
- `federation_identity_link_failures_total` by cohort/provider.
- `federation_permissions_changed_total` to catch privilege drift.
- `federation_jwks_metadata_age_seconds` by issuer alias/node.
- `federation_sessions_active` by provider/cohort.
- `federation_rollback_events_total` by migration phase.

Never use email, subject, token, arbitrary `kid`, user-supplied issuer URL, or high-cardinality trace ID as metric labels. Audit logs may record trace IDs at event level in protected logs. Alert on elevated provider failures, nodes missing keys, rising identity-link failures, rising signature/issuer rejections, or any unauthorized privilege grant.

## 17. Acceptance Checklist and Anti-Patterns

**Trust & protocol**
- [ ] Legacy/next SAML EntityIDs or OIDC issuers are distinct and exact.
- [ ] Each registration has its own trusted verification certificates/JWKS.
- [ ] JWT decoders, issuer allowlists, `aud`, time, and algorithms are isolated per issuer.
- [ ] SAML Issuer/Audience/Recipient/Destination/`InResponseTo`/signature/time checks remain active.
- [ ] OIDC `client_id`/secret/`redirect_uri`/state/nonce/ID Token issuer/`aud` are accurate.
- [ ] Never fetch keys from arbitrary `jku`/`x5u` or verify against a global union pool.
- [ ] Old+new key rotation happens strictly within the same approved issuer.

**Identity & authorization**
- [ ] Links bind issuer/provider + stable subject + tenant + local account.
- [ ] Matching email/username never auto-merges accounts.
- [ ] Group/role claims map strictly via approved local entitlement policies.
- [ ] Privileged roles have security approvals and MFA assurance policies.
- [ ] Switching sessions never unions authorities; token stores never cross-reuse refresh tokens across issuers.
- [ ] Disabled/unlinked accounts receive zero business permissions.

**Operations**
- [ ] Pilot/canary/cutover/drain/retire have clear owners and gates.
- [ ] Callbacks stay bound to the flow's starting registration even if flags flip.
- [ ] Rollback runbook exists without mixing issuers or keys.
- [ ] Session TTL/revocation policy for retiring issuers is explicit.
- [ ] Positive + negative fixtures, audit logs, and alerts are in place.
- [ ] Zero bearer tokens, assertions, or secrets exposed.

**Typical anti-patterns:**
- Merging `legacy` and `next` keys into one issuer-agnostic verifier.
- Automatically mapping `roles=admin` to `ROLE_ADMIN` across every provider.
- Treating matching email as an approved identity link.
- Using `JwtIssuerAuthenticationManagerResolver` for arbitrary token-supplied issuers.
- Disabling audience/nonce/state checks because the callback "reached the right URL."
- Sending an old refresh token to the new token endpoint.
- Keeping admin permissions from a legacy session after a new login.
- Borrowing old metadata/keys when next's JWKS times out.
- Rolling back by letting the old verifier accept new signed tokens.
- Keeping legacy trust open indefinitely after retirement.

## 18. Self-Check Questions

**1. Why must verification keys be separated by issuer?**  
So one IdP cannot sign tokens or assertions that an API treats as issued by another IdP. Key selection comes strictly from the selected issuer's trust set.

**2. Can an unverified JWT `iss` be read?**  
Yes, strictly to look up an exact server allowlist, followed by signature verification and `iss`/`aud`/time validation via an issuer-bound decoder. Never construct a JWKS URL from an arbitrary `iss`.

**3. Can `kid` collide between two issuers?**  
Yes. `kid` is only a selector inside an issuer's JWKS, not an identity or global trust anchor.

**4. Can two providers sharing an email auto-link an account?**  
No. You need an issuer-qualified immutable subject, tenant, and verified migration approval.

**5. Is a validly signed `Admin` role claim enough for `ROLE_ADMIN`?**  
No. You also need trusted authority mapping and a local business authorization policy.

**6. Can a `next` SAML Response arriving at the `legacy` ACS temporarily use `next`'s certificate?**  
No. Registration/IdP EntityID, signing key, SP audience, and correlation must all belong to the legacy flow; never mix keysets.

**7. Does a `next` OIDC callback prove the ID Token belongs to `next`?**  
No. You must verify `state`/nonce, issuer, signature, `client_id` audience, and the verified client registration.

**8. When switching providers, should permissions from both sessions be combined?**  
No. Recompute from the current verified identity / local IAM policy and manage session lifecycles.

**9. During legacy's planned key rollover, can two legacy signing keys be temporarily trusted?**  
Yes, within the approved overlap of **the same legacy issuer**, never using `next`'s key.

**10. How can you fall back during a `next` IdP outage?**  
If policy permits, start a fresh authentication flow through `legacy`; never reuse a `next` token/Assertion or swap issuers mid-callback.

**11. Does an API still need an audience validator when signature and issuer are right?**  
Yes. The same issuer can sign tokens for many different APIs and clients.

**12. Once default switches to `next`, are legacy sessions automatically invalidated?**  
No. You need a dedicated session TTL, revocation, and drain plan.

**13. After retiring the `legacy` issuer from API trust, what happens to still-unexpired legacy tokens?**  
The API rejects them, so clients must migrate and validity/retirement windows must be managed.

**14. What if an identity is verified yet the local account is disabled?**  
Deny access. Login proof never overrides entitlements or authorization.

## 19. References

1. [Spring Boot 3.3 SAML2 Multiple Relying Parties](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html): multiple SAML registrations and IdP certificates.
2. [Spring Security SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): `RelyingPartyRegistration`, `registrationId`, ACS, and signature checks.
3. [Spring Security Authenticating SAML2 Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): authentication converters and registration resolution.
4. [Spring Security OAuth2 Login Core](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): `ClientRegistration` and callbacks.
5. [Spring Security 6.3 OAuth2AuthenticationToken API](https://docs.spring.io/spring-security/site/docs/6.3.5/api/org/springframework/security/oauth2/client/authentication/OAuth2AuthenticationToken.html): authorized client registration ID.
6. [Spring Security Multi-tenancy](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/multitenancy.html): `JwtIssuerAuthenticationManagerResolver`/trusted issuers.
7. [Spring Security JWT Resource Server](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html): signature/issuer/timestamp/JWKS.
8. [OASIS SAML2 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): Response/Assertion, Issuer, Conditions.
9. [OASIS SAML2 Metadata](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf): EntityDescriptor, KeyDescriptor.
10. [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token issuer/subject/audience/nonce.
11. [RFC 6749 OAuth2](https://www.rfc-editor.org/rfc/rfc6749): redirect URI, authorization code/state.
12. [RFC 7636 PKCE](https://www.rfc-editor.org/rfc/rfc7636): authorization code hardening.
13. [RFC 7517 JWK](https://www.rfc-editor.org/rfc/rfc7517): JWKS/kid/key usage.
14. [RFC 7519 JWT](https://www.rfc-editor.org/rfc/rfc7519): `iss`/`aud`/`sub`/`exp`/`nbf`.
15. [RFC 8725 JWT Best Practices](https://www.rfc-editor.org/rfc/rfc8725): alg/key/issuer/audience confusion.
16. [OWASP SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html): signature wrapping/trust.
17. [OWASP OAuth2 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): CSRF/state, issuer mix-up, redirect.
18. [Spring Security Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): session lifecycle/fixation.

**Conclusion:** Running old and new IdPs in parallel means two independent trust zones serving one application. Always chain **registration/issuer → trusted keys → validated subject → approved identity link → local permissions**, protect callbacks and sessions, and plan rollback, cutover, and retirement. Never accept a token using another issuer's key or turn raw claims into admin privileges just to cut down errors during migration.