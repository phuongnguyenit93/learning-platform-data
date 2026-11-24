# Diagnosing Invalid Signatures, Missing Keys, and Rotated Certificates

## 1. Problem to Solve

In a Spring Security – federation system, an SSO flow can run stably and then suddenly fail when the Identity Provider (IdP) or Authorization Server rotates its signing key. Common error messages include:

- SAML Response or Assertion: signature verification failed, cannot validate signature, no trusted signing credential.
- OIDC ID Token/JWT access token verification: no matching JWK, unknown kid, invalid signature, unsupported algorithm.
- Some pods log in successfully while others fail after a certificate rollover because metadata/caches are out of sync.
- The endpoint serving IdP metadata or JWKS hits HTTP 5xx, TLS errors, timeouts, or malformed XML/JSON.
- Someone sees an X.509 certificate past `NotAfter` and mistakenly concludes it is JWT `exp` or SAML `NotOnOrAfter`.
- SAML `EncryptedAssertion` fails to decrypt or the IdP rejects a signed `AuthnRequest`, yet every error is lumped together as a "signature error".

This article belongs to the Observability and debugging group. Its goal is accurate layer-by-layer diagnosis with verifiable evidence, safe key/certificate rotation handling, and never skipping signature verification or trusting a certificate carried inside the message itself. The primary scope is Spring Security 6.x with SAML2 Service Provider, OIDC login, and OAuth2 JWT Resource Server; configuration examples use Spring Boot 3.3.5 and Java 17. Hostnames like `example.org`, issuers, and key identifiers are simulated data.

After this lesson, the reader must be able to distinguish:

1. No trusted key found for verification.
2. Trusted key found, yet the signature fails to verify.
3. Valid signature, yet issuer, audience, recipient, time, or tenant is invalid.
4. Signing certificate has rotated or expired under policy.
5. Unable to fetch metadata/JWKS due to network, cache, or TLS.
6. SP fails to decrypt Assertion due to the wrong decryption key.
7. IdP fails to verify AuthnRequest due to the wrong SP signing key/cert.

Security principle: fail closed. Never turn an unverified SAMLResponse/JWT into an `Authentication`; never add an arbitrary public key to the trust set just to make login succeed.

## 2. Verification Step Map

### 2.1. SAML2 Flow at the Service Provider

~~~text
Browser -> SP: requests protected resource
SP -> IdP: AuthnRequest (may be signed by SP signing key)
IdP -> Browser: SAMLResponse with signed Response/Assertion per profile
Browser -> SP: POST SAMLResponse to ACS

Spring SAML2 authentication:
  1. Resolve RelyingPartyRegistration matching issuer/context
  2. Deserialize and check required XML signature
  3. Select trusted IdP verification credentials
  4. Decrypt EncryptedAssertion if present using SP decryption credentials
  5. Check Issuer, Destination, AudienceRestriction, Recipient
  6. Check Conditions/SubjectConfirmationData times, InResponseTo
  7. Extract principal from signed/validated Assertion
  8. Apply local account, groups, tenant, and resource authorization
~~~

The verify/decrypt order can differ depending on signed Response vs. signed Assertion structure and Spring/OpenSAML version. Never write a custom XML parser that bypasses signed-element/reference rules; use only the `Authentication` produced by a fully validating provider.

### 2.2. JWT Flow at the Relying Party/API

~~~text
JWT header: alg, kid, typ       -- untrusted data
JWT payload: iss, aud, exp...  -- untrusted data
JWT signature

Trusted issuer configured on server
  -> provider discovery / trusted jwks_uri
  -> fetch/cached JWKS public keys
  -> choose candidate by kid/kty/alg/use where appropriate
  -> verify JWS signature using trusted candidate
  -> verify iss/aud/exp/nbf, token type, nonce/state as relevant
  -> authenticated principal + app authorization
~~~

Merely Base64URL-decoding the payload does not mean the signature is valid. The JWT header `kid` is a key identifier, not proof of trust. Never accept a `jku`/`x5u` URL from an unverified token header to fetch an arbitrary JWK.

## 3. Key-Selection Errors vs. Signature-Verification Errors

| Error Category | Verification Question | Possible Causes |
| --- | --- | --- |
| KEY_NOT_FOUND | Is there a matching trusted public verification key? | Missing trusted metadata, new JWT `kid` not yet in JWKS cache, wrong issuer/registration, incompatible key type/alg. |
| SIGNATURE_INVALID | With the selected key, do the signed bytes verify? | Wrong key, signed data altered, broken SAML XML-DSig reference/canonicalization, forged JWT signature, `kid` reused with different key bytes. |
| ISSUER_MISMATCH | Which issuer actually issued the Assertion/Token and which registration is trusted? | Wrong tenant/realm, staging/prod mix-up, cross-IdP. |
| CLAIM_VALIDATION | Signature passes, yet are audience/recipient/time valid? | Assertion for another SP, API token for another resource, expired, wrong ACS. |
| METADATA_FETCH_FAILED | Can the public key source be fetched/parsed? | DNS, network, TLS trust, 404/500, timeout, malformed XML/JSON. |
| CERT_POLICY | Has the certificate rotated/passed `NotAfter`/been revoked per policy? | Rotation missing overlap, certificate inventory out of sync with metadata/trust policy. |
| DECRYPT_FAILED | Does the SP have the private decryption key matching the ciphertext? | IdP used old encryption cert, wrong SP private key, unsupported encryption. |
| AUTHNREQUEST_SIGNING | Does the IdP trust the SP's public signing certificate? | IdP has not updated SP cert or SP signed request with the wrong key. |

These failures may produce similar messages in the framework or IdP. Error text alone is not enough to conclude the root cause. You must inspect the issuer, expected registration, keyset version, signed element, algorithm, and rollout timestamp.

### 3.1. Two Easily Confused Situations

- A new key is already being used by the IdP while the SP has not loaded the new certificate: you may see "no verification credential", "no matching key", or "signature invalid" depending on the provider.
- JWKS has a `kid` matching the JWT header, yet the actual public key is the old key: the key selector finds a candidate, and the signature still fails; matching `kid` does not make a token trusted.

### 3.2. Things You Must Never Do

- Do not enable `trustAll` or `skipSignatureValidation`.
- Do not treat a `KeyInfo` certificate from `SAMLResponse` as a new trust anchor.
- Do not fetch JWKS from an attacker's JWT `jku`/`x5u`.
- Do not dump all issuers into one trust store and accept whichever key verifies.
- Do not disable `exp`/`nbf`/`audience`/`issuer` while tracking down a signature error.
- Do not accept raw `NameID`/email/`sub` as a user before the framework completes verification.

## 4. SAML2: Distinguishing Certificates and Private Keys

| Owner | Key Type | Purpose |
| --- | --- | --- |
| IdP | Signing private key | Signs Response/Assertion sent to the SP. |
| IdP | Signing public certificate | Used by SP to verify signatures; lives in trusted asserting-party metadata/credentials. |
| SP | Signing private key | Signs AuthnRequest if required by the IdP. |
| SP | Signing public certificate | Used by IdP to verify AuthnRequest. |
| SP | Decryption private key | SP decrypts `EncryptedAssertion`/`EncryptedAttribute`. |
| SP | Encryption public certificate | Used by IdP to encrypt Assertions for the SP. |
| TLS server | HTTPS certificate/private key | Protects transport/hostname; does not replace SAML verification keys. |

Example IdP metadata (XML fragment only; certificate bytes shown here are an illustrative placeholder, not a real cert):

~~~xml
<md:EntityDescriptor
  xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
  xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
  entityID="https://idp.example.org/saml">
  <md:IDPSSODescriptor
    protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:KeyDescriptor use="signing">
      <ds:KeyInfo>
        <ds:X509Data>
          <ds:X509Certificate>BASE64_PUBLIC_CERTIFICATE_ONLY</ds:X509Certificate>
        </ds:X509Data>
      </ds:KeyInfo>
    </md:KeyDescriptor>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
~~~

Real metadata can contain multiple `KeyDescriptor`s, with or without an explicit `use`. The provider/OpenSAML handles them per profile. Never mistakenly pick `KeyDescriptor use="encryption"` to verify a signature. Never assume the first certificate in the XML is the active key.

### 4.1. Trust Must Be Anchored at the Right IdP

`RelyingPartyRegistration` links SP metadata to asserting-party metadata: IdP EntityID, SingleSignOnService, public verification credentials, SP EntityID/ACS, and SP credentials. If an app has `corp`, `partner`, `staging`, and `production`, each registration must have its own trust/policy. Using a partner's certificate to trust a `corp` Response is a cross-tenant flaw.

`KeyInfo` inside an XML Signature may describe a candidate, yet that information is sender-supplied; verification must rely on trusted IdP credentials. A valid XML Signature against an arbitrary certificate does not prove the message came from the IdP.

### 4.2. Signed Response or Signed Assertion?

Depending on the federation profile, the IdP may sign the Response, the Assertion, or both. You must ensure the data used to grant a principal actually resides inside the signed/validated elements. Never verify a signed Assertion A and then read an unsigned Assertion B: that is an XML Signature Wrapping attack surface.

XML-DSig verification involves `SignedInfo`, `Reference` URI, canonicalization, transforms, and element IDs—not merely comparing a Base64 signature against a hand-built XML string. Use Spring Security/OpenSAML; never hand-roll SAML verification with a few lines of `java.security.Signature`.

### 4.3. Signing Certificate NotAfter Is Not Token Expiry

An X.509 certificate has `NotBefore`/`NotAfter`. An RSA/ECDSA signature can still verify mathematically even after the certificate passes `NotAfter`; whether it is rejected depends on trust configuration, PKIX/certificate validity policy, profile, and provider. Do not assume Spring SAML always automatically checks the CA chain/`NotAfter` of every certificate in metadata.

SAML Assertions also carry `Conditions.NotOnOrAfter` and `SubjectConfirmationData.NotOnOrAfter`; JWTs carry `exp`/`nbf`. These are credential/message lifetimes, independent of X.509 certificate dates. Never "fix" certificate rollover by disabling assertion time checks.

### 4.4. Signing, Encryption, and TLS Must Never Be Swapped

- SP decryption fails: investigate the SP private decryption key and the public encryption certificate configured at the IdP.
- IdP rejects SP AuthnRequest signature: investigate the SP signing private key and the SP public certificate trusted by the IdP.
- SP rejects incoming Response signature: investigate the IdP signing public certificate/trusted metadata.
- Metadata HTTPS TLS fails: investigate the TLS CA chain, hostname, and network; do not assume an XML signature failure.

## 5. Inspecting Public Certificates with OpenSSL/keytool

In an authorized operational environment, fetch metadata from a trusted IdP URL (hostname is illustrative only):

~~~bash
curl --fail --show-error --silent --max-time 15 https://idp.example.org/saml/metadata -o idp-metadata.xml
~~~

HTTP 200 + HTTPS alone does not prove metadata is safe; the IdP source must be governed, and any metadata signature must be verified using an independently provisioned metadata trust anchor. Never pull a metadata URL supplied by a browser or an unverified Assertion.

Extract the public `X509Certificate` from metadata using an XML-aware parser, wrap it with proper PEM BEGIN/END headers, and save as `idp-signing.pem`. No private key is needed. Check:

~~~bash
openssl x509 -in idp-signing.pem -noout -subject -issuer -serial -dates -fingerprint -sha256
openssl x509 -in idp-signing.pem -noout -text
openssl x509 -in idp-signing.pem -checkend 604800 -noout
keytool -printcert -file idp-signing.pem -v
~~~

The `checkend 604800` command exits nonzero if the certificate is expired or will expire within 7 days, with no fixed universal stdout across all certs. A SHA-256 fingerprint proves whether two certificate files have identical or different bytes, not trust by itself. Two different certificates can contain the same public key. When investigating rotation, compare both the cert fingerprint and the IdP-approved key material/public key ID.

Cross-check three sources:

1. Current trusted IdP metadata: EntityID, signing certificates, fingerprint, version/time.
2. Running SP configuration on each node: registration, IdP EntityID, loaded verification credentials, and metadata age.
3. Signed SAML fixture in sandbox: Issuer, SignedInfo/alg, signed element, signature result.

Never dump raw SAMLResponse/attributes/tokens/cookies into logs or issue trackers. If XML diagnosis is required, use synthetic fixtures, restricted access, and redaction.

## 6. OIDC/JWT: kid, JWKS, and Trusted Issuer

A JWS JWT has header `alg`/`kid`, payload `iss`/`aud`/`exp`, and a signature. Both header and payload fields are untrusted before verification.

- `issuer` identifies the trusted OpenID Provider/Authorization Server.
- `jwks_uri` comes from provider discovery or server-side configuration from a trusted source.
- JWKS contains public JWKs, usually with `kid`, `kty`, `alg`, `use`/`key_ops`, and sometimes `x5c`/`x5t`.
- `kid` is optional and not globally unique. It is a key selector, not a trust anchor.
- `kty`/`alg`/`use`/`key_ops` must match the token and the application's allowlist.
- Even after verifying the signature, you must still verify `iss`, `aud`, `exp`, `nbf`; OIDC login also requires `state`/`nonce` per flow.
- An ID Token's audience is the RP's `client_id`; an API access token's audience is the resource identifier, not `client_id` by default.

### 6.1. Checking Issuer and Public JWKS Endpoint

Obtain the actual `jwks_uri` from trusted issuer discovery. The illustrative URLs below vary by provider; never hardcode paths blindly:

~~~bash
curl --fail --show-error --silent --max-time 15 https://idp.example.org/realms/corp/.well-known/openid-configuration -o discovery.json
curl --fail --show-error --silent --max-time 15 https://idp.example.org/realms/corp/protocol/openid-connect/certs -o jwks.json
jq -r '.keys[] | [.kid // "-", .kty // "-", .alg // "-", .use // "-"] | @tsv' jwks.json
~~~

Always read the JWKS endpoint from the `jwks_uri` field of the trusted issuer's discovery document rather than guessing from an example URL. Never trust a `jku`/`x5u` URL from a JWT header. Never use `curl -k` to bypass TLS errors. JWKS holds public keys and must never contain private key parameters; if private components are exposed, treat it as a security incident.

### 6.2. Classifying JWK Errors

| Error | Hypothesis | Remediation |
| --- | --- | --- |
| Unknown `kid` | Issuer just rotated, key not yet published, or consumer cache is stale. | Check current trusted JWKS, cache TTL/refresh, and rollout. |
| `kid` matches yet signature fails | `kid` was reused with a different key, bytes were altered, or wrong signer. | Compare public key/fingerprint, issuer, token signer, and `alg`. |
| No compatible key | `kty`/`alg`/`use`/`key_ops` incompatible, unsupported key. | Check key metadata and algorithm policy. |
| JWKS 404/500/timeout | Wrong discovery path, outage, DNS/network issue. | Fix provider endpoints/retries/cache per policy. |
| HTTPS JWKS cert invalid | Wrong CA/hostname chain or expired TLS cert. | Fix TLS trust; never disable HTTPS verification. |
| Invalid issuer | Token from a different realm/tenant. | Select the right trusted issuer; do not merge trust pools. |
| Invalid audience | API received a web ID Token or a token for another API. | Issue an access token for the right API; keep the `aud` validator. |
| Expired/not yet valid | `exp`/`nbf` or wrong system clock. | NTP, token renewal, bounded clock skew; never drop timestamps. |

Spring Security Resource Server and Nimbus support refreshing the JWK Set when the issuer rotates keys, yet caching/refetch behavior upon unknown `kid` depends on version, custom cache config, network timeouts, and the key endpoint. Never assume every pod always refreshes instantaneously.

## 7. Rotation Plan with Overlap and Rollback Procedure

Example planned signing key rotation:

~~~text
T-7 days:
  IdP/AS publishes new public signing key/cert alongside old
  (right issuer, trusted metadata/JWKS).
  SP/API consumers refresh keyset and verify fingerprint/version.

T-1 day:
  Sandbox signed fixtures using old and new both pass when claims are valid.
  Negative fixtures with wrong key, tampered, wrong issuer all reject.
  Confirm every node/region/tenant has loaded the new key.

T0:
  IdP/AS switches to signing with new private key.
  Monitor SIGNATURE_INVALID and KEY_NOT_FOUND.
  Consumers continue trusting old during approved overlap window.

T + approved overlap:
  Only when old tokens/assertions have expired and caches stabilize,
  retire old verification key per approved schedule.

Emergency compromise:
  Old signing private key compromised => emergency trust revocation,
  do not keep overlap just to avoid login errors.
~~~

Distinguish replacing a certificate while reusing the same public key from changing the actual keypair. Rotating while some consumers still lack the new key causes intermittent login failures. Do not rush to rotate keys a second time when the root cause is a stale metadata snapshot.

### Static SAML RelyingPartyRegistration

With an `InMemoryRelyingPartyRegistrationRepository` built from `RelyingPartyRegistrations.fromMetadataLocation` at startup, the repository may hold a snapshot of signing certificates from that moment. Changing the IdP metadata URL later does not guarantee the app automatically refreshes on every request. You need a controlled rebuild/refresh/redeployment per version and per-instance verification. Before the IdP activates a new signing key, all active SP nodes must trust the new public key.

### JWKS Cache on APIs

If an API cached the old keyset and a new JWT arrives, `unknown kid` is a key signal. Check the token issuer, trusted `jwks_uri`, actual public JWKS, cache age, keyset version, `alg` policy, and refetch outcome on every node. Never load keys from an arbitrary URL or temporarily skip signature checks.

### Emergency Incident Response Sequence

If a private key is compromised: notify the security owner, revoke/update trust per the incident process, issue new keys, invalidate affected sessions/tokens as supported by the system, assess replay and exposure window, redeploy, and run negative tests. Here security takes precedence over availability; never extend overlap indefinitely.

## 8. Using Spring Security 6.x: Keep Default Validators Intact

### 8.1. Minimal Spring Boot 3.3.5 SAML2 SP Sample

Test application Maven `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>signature-lab</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <properties><java.version>17</java.version></properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.security</groupId>
      <artifactId>spring-security-saml2-service-provider</artifactId>
    </dependency>
  </dependencies>
  <build><plugins><plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
  </plugin></plugins></build>
</project>
~~~

Metadata location must come from an approved IdP source. Depending on OpenSAML version and Maven mirrors, ensure dependency artifacts come from trusted repositories. Never downgrade to an obsolete version just because a dependency failed to resolve.

`application.yml`:

~~~yaml
server:
  port: 8080
  # Use only behind a trusted reverse proxy that strips user-supplied forwarded headers.
  forward-headers-strategy: framework

lab:
  saml:
    idp-metadata-uri: "https://idp.example.org/saml/metadata"
~~~

Main class in `src/main/java/com/example/signaturelab/SignatureLabApplication.java`:

~~~java
package com.example.signaturelab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SignatureLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(SignatureLabApplication.class, args);
    }
}
~~~

`SecurityConfig.java`:

~~~java
package com.example.signaturelab;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    private static final Logger LOG =
        LoggerFactory.getLogger(SecurityConfig.class);

    @Bean
    RelyingPartyRegistrationRepository relyingParties(Environment env) {
        String trustedMetadata = env.getRequiredProperty(
            "lab.saml.idp-metadata-uri");

        RelyingPartyRegistration corp = RelyingPartyRegistrations
            .fromMetadataLocation(trustedMetadata)
            .registrationId("corp")
            .entityId(
                "https://sp.example.org/saml2/service-provider-metadata/corp")
            .assertionConsumerServiceLocation(
                "https://sp.example.org/login/saml2/sso/corp")
            .build();

        return new InMemoryRelyingPartyRegistrationRepository(corp);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login-error").permitAll()
                .anyRequest().authenticated())
            .saml2Login(saml -> saml.failureHandler(
                (request, response, error) -> {
                    // Log exception type; do not log raw XML or user attributes.
                    LOG.warn("saml_login_denied causeType={}",
                        error.getClass().getSimpleName());
                    response.sendRedirect("/login-error");
                }))
            .saml2Metadata(Customizer.withDefaults());
        return http.build();
    }
}
~~~

`LabController.java`:

~~~java
package com.example.signaturelab;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class LabController {
    @GetMapping("/")
    public String home() {
        return "SAML2 validation lab";
    }

    @GetMapping("/login-error")
    public String loginError() {
        return "SSO authentication failed";
    }

    @GetMapping("/private")
    public String privatePage(Authentication auth) {
        return "Authenticated: " + auth.getName();
    }
}
~~~

`SecurityFilterChain` preserves Spring/OpenSAML signature and protocol validation. The failure handler logs only the exception class and redirects to a generic error page, never extracting `NameID` from a rejected XML to create a principal. Production should classify internal reason codes via controlled mapping and safe trace IDs.

End-to-end SAML cannot run against `example.org`; you need a real sandbox IdP, trusted metadata, exact EntityID/ACS, and signed fixtures. Spring Security 6.3 uses the `OpenSaml4AuthenticationProvider` family; newer Spring docs may reference `OpenSaml5AuthenticationProvider`, so never copy customizers for the wrong version.

### 8.2. Resource Server JWT: Composing Issuer/Time/Audience

An API application using `spring-boot-starter-oauth2-resource-server` can configure Boot YAML:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: "https://idp.example.org/realms/corp"
          jwk-set-uri: "https://idp.example.org/realms/corp/protocol/openid-connect/certs"
          audiences: "api://inventory"
~~~

The URLs in the example are not live; obtain the exact `jwks_uri` from trusted issuer discovery. Keep both issuer and audience because a valid signature on a token meant for another resource is not enough. Pinning the JWKS location in config can avoid startup discovery in some setups, yet `iss` validation must never be dropped.

If a custom `JwtDecoder` is needed, configure a separate Resource Server project:

~~~java
package com.example.api;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {
    @Bean
    JwtDecoder decoder(Environment env) {
        String issuer = env.getRequiredProperty("security.jwt.issuer");
        String jwks = env.getRequiredProperty("security.jwt.jwks");
        String audience = env.getRequiredProperty("security.jwt.audience");

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwks)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains(audience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error("invalid_token",
                        "Wrong audience", null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                audienceValidator));
        return decoder;
    }

    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()));
        return http.build();
    }
}
~~~

Alongside the Java bean above, add server-side YAML config:

~~~yaml
security:
  jwt:
    issuer: "https://idp.example.org/realms/corp"
    jwks: "https://idp.example.org/realms/corp/protocol/openid-connect/certs"
    audience: "api://inventory"
~~~

- Only `RS256` is allowed in the example; use an algorithm allowlist agreed upon by issuer and security policy, never trusting an arbitrary `alg` from the token.
- `DelegatingOAuth2TokenValidator` preserves `JwtValidators.createDefaultWithIssuer`, including issuer and timestamps, while adding audience.
- Never call `decoder.setJwtValidator(audienceValidator)` alone because that replaces the default validators.
- Never accept `jku`/`x5u` headers from tokens as trusted key endpoints.
- JWKS cache/auto-refresh depends on Nimbus, Spring version, and cache config; an unknown `kid` must fail closed until a trusted compatible key is present.
- An API access token differs from an OIDC ID Token: the ID Token's `aud` is `client_id`, not automatically the API resource identifier.

## 9. Standalone Java 17: Demonstrating Key Rotation and Failure Causes

`KeyRotationDiagnostics.java` uses real RSA SHA256 over the bytes of a claim model to show that an untrusted new key triggers `KEY_NOT_FOUND`; a known `keyId` with a wrong signature is still rejected; and issuer/audience/time are independent checks.

Mandatory limitations: this is NOT a SAML XML-DSig verifier, JOSE/JWS/JWT verifier, or X.509 PKIX validator. Pipe-joining strings is for teaching only, not safe canonicalization. `keyId` `v1`/`v2` are simulated labels for JWKS `kid`; do not assume SAML Responses always have a `kid`. Production must use OpenSAML, Spring/`NimbusJwtDecoder`, and trusted metadata/issuers.

`KeyRotationDiagnostics.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.time.Instant;
import java.util.Map;

public class KeyRotationDiagnostics {
    record Claim(String issuer, String audience, String subject,
                 Instant expiresAt, String keyId) {
        String forDemoOnly() {
            return String.join("|",
                issuer, audience, subject, expiresAt.toString(), keyId);
        }
    }

    record Evidence(Claim claim, byte[] signature) {}

    static Evidence issue(Claim c, PrivateKey key)
            throws GeneralSecurityException {
        Signature sig = Signature.getInstance("SHA256withRSA");
        sig.initSign(key);
        sig.update(c.forDemoOnly().getBytes(StandardCharsets.UTF_8));
        return new Evidence(c, sig.sign());
    }

    static String validate(Evidence e, Map<String, PublicKey> trust,
                           String issuer, String audience, Instant now)
            throws GeneralSecurityException {
        Claim c = e.claim();
        PublicKey key = trust.get(c.keyId());
        if (key == null) return "REJECT KEY_NOT_FOUND";

        Signature verifier = Signature.getInstance("SHA256withRSA");
        verifier.initVerify(key);
        verifier.update(c.forDemoOnly().getBytes(StandardCharsets.UTF_8));
        if (!verifier.verify(e.signature())) {
            return "REJECT SIGNATURE_INVALID";
        }
        if (!issuer.equals(c.issuer())) return "REJECT ISSUER";
        if (!audience.equals(c.audience())) return "REJECT AUDIENCE";
        if (!now.isBefore(c.expiresAt())) return "REJECT EXPIRED";
        return "ACCEPT";
    }

    static void show(String label, Evidence e,
                     Map<String, PublicKey> trusted,
                     String issuer, String audience, Instant now)
            throws GeneralSecurityException {
        System.out.println(label + ": " +
            validate(e, trusted, issuer, audience, now));
    }

    public static void main(String[] args)
            throws GeneralSecurityException {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair old = generator.generateKeyPair();
        KeyPair fresh = generator.generateKeyPair();

        String issuer = "https://idp.example.org/realms/corp";
        String audience = "api://inventory";
        Instant now = Instant.parse("2030-01-01T12:00:00Z");
        Instant later = Instant.parse("2030-01-01T12:05:00Z");
        Instant earlier = Instant.parse("2030-01-01T11:59:00Z");

        Claim v1 = new Claim(issuer, audience, "alice", later, "v1");
        Claim v2 = new Claim(issuer, audience, "alice", later, "v2");
        Evidence oldToken = issue(v1, old.getPrivate());
        Evidence newToken = issue(v2, fresh.getPrivate());

        Map<String, PublicKey> oldOnly =
            Map.of("v1", old.getPublic());
        Map<String, PublicKey> overlap = Map.of(
            "v1", old.getPublic(), "v2", fresh.getPublic());
        Map<String, PublicKey> newOnly =
            Map.of("v2", fresh.getPublic());

        show("old before rotation", oldToken, oldOnly,
            issuer, audience, now);
        show("new before publish", newToken, oldOnly,
            issuer, audience, now);
        show("new during overlap", newToken, overlap,
            issuer, audience, now);
        show("old during overlap", oldToken, overlap,
            issuer, audience, now);
        show("old after retire", oldToken, newOnly,
            issuer, audience, now);

        Claim tampered = new Claim(
            issuer, audience, "mallory", later, "v1");
        show("tampered", new Evidence(tampered, oldToken.signature()),
            overlap, issuer, audience, now);

        Claim wrongIssuer = new Claim(
            "https://other.example.org", audience,
            "alice", later, "v2");
        show("wrong issuer", issue(wrongIssuer, fresh.getPrivate()),
            overlap, issuer, audience, now);

        Claim wrongAudience = new Claim(
            issuer, "api://other", "alice", later, "v2");
        show("wrong audience", issue(wrongAudience, fresh.getPrivate()),
            overlap, issuer, audience, now);

        Claim expired = new Claim(
            issuer, audience, "alice", earlier, "v2");
        show("expired", issue(expired, fresh.getPrivate()),
            overlap, issuer, audience, now);

        // keyId v2 yet signed with old private key: invalid signature.
        show("wrong key with known kid", issue(v2, old.getPrivate()),
            overlap, issuer, audience, now);
    }
}
~~~

Run on Java 17:

~~~bash
javac KeyRotationDiagnostics.java
java KeyRotationDiagnostics
~~~

Exact stdout, even though RSA keypairs are randomly generated:

~~~text
old before rotation: ACCEPT
new before publish: REJECT KEY_NOT_FOUND
new during overlap: ACCEPT
old during overlap: ACCEPT
old after retire: REJECT KEY_NOT_FOUND
tampered: REJECT SIGNATURE_INVALID
wrong issuer: REJECT ISSUER
wrong audience: REJECT AUDIENCE
expired: REJECT EXPIRED
wrong key with known kid: REJECT SIGNATURE_INVALID
~~~

Meaning:

- `new before publish`: key `v2` is not yet in the trust pool, cannot verify.
- `new during overlap` and `old during overlap`: both public keys are trusted during the approved rotation window.
- `old after retire`: old key removed; tokens using the old key are rejected.
- `tampered`: subject contents changed while the old signature did not, so it is invalid.
- `wrong issuer/audience`: signed by a trusted key, yet claim validation still rejects.
- `expired`: valid signature yet expired token; do not confuse with certificate `NotAfter`.
- `wrong key with known kid`: key selector found `v2`, yet the signature was created by `v1`, so it is invalid.

Never use this program to create `Authentication`. Real SAML/JWT requires signed-element coverage, canonicalization/alg policy, trusted issuer/JWKS, replay/correlation, and framework authorization.

## 10. Observability Without Exposing Bearer Credentials

Log events after the provider returns an outcome instead of dumping unverified XML/tokens:

~~~text
event=sso.authentication.denied
trace_id=trace-7f20
protocol=SAML2
registration_alias=corp
stage=SIGNATURE_VERIFICATION
reason=KEY_NOT_FOUND
trusted_keyset_version=rot-2026-11-a
node=sp-prod-b
result=DENY
~~~

Reason codes like `KEY_NOT_FOUND`, `SIGNATURE_INVALID`, `ISSUER_MISMATCH`, `DECRYPT_FAILED`, `CERT_VALIDITY_POLICY` are a taxonomy defined by the operations team, not a default Spring API enum. Map exceptions/causes only after analyzing and sanitizing. Never log raw `error.getMessage()` when it may contain sensitive data.

Never log raw `SAMLResponse`, XML assertions, JWT/ID Token/access tokens, `Authorization` headers, cookies, private keys, full user/group attributes, or unverified JWT payloads. Full fingerprints and internal issuer endpoints may also require access restrictions per security policy.

Useful metrics and alerts:

| Signal | Low-Cardinality Labels | Meaning |
| --- | --- | --- |
| `sso_auth_attempts_total` | `protocol`, `registration_alias`, `result` | Success/error ratio. |
| `sso_auth_failures_total` | `protocol`, `stage`, `reason` | Signature/key errors after rotation. |
| `idp_metadata_age_seconds` | `idp_alias`, `node` | Does a node have stale metadata? |
| `idp_metadata_refresh_success` | `idp_alias`, `node` | Did fetch/parse/trust pass? |
| `jwks_refresh_failures_total` | `issuer_alias`, `env` | Key endpoint/network issues. |
| `jwks_keyset_age_seconds` | `issuer_alias`, `node` | Cache freshness per pod. |
| `signing_cert_days_remaining` | `idp_alias`, `cert_slot` | Planned expiry alert. |
| `sso_rotation_state` | `idp_alias`, `phase` | Publish, activate, overlap, retire. |

Never use arbitrary `kid`, user email, subject, trace ID, or raw URLs as Prometheus labels due to cardinality and privacy. Per-request details belong in sanitized audit logs.

Alert when (1) `SIGNATURE_INVALID`/`KEY_NOT_FOUND` spikes across the fleet; (2) only one node fails; (3) metadata/JWKS stops refreshing; (4) a signing cert approaches `NotAfter`; (5) actual key fingerprint differs from the approved change; (6) synthetic login fails after T0.

## 11. 12-Step Incident Resolution Runbook

1. Record UTC onset, protocol, IdP alias, registration, affected endpoints, deployment version, and sanitized trace IDs.
2. Determine scope: fleet-wide or one region/node/tenant? Only SAML login or also JWT APIs?
3. Classify the stage: metadata fetch, key selection, signature verification, decryption, issuer/audience/time, or local authorization.
4. Read the expected trusted issuer/registration and keyset version from the running app; never look at an unverified token to decide trust.
5. Fetch IdP metadata/JWKS from the approved origin and verify HTTPS/trust/integrity. Compare fingerprints/`kid`/`alg` against the change record.
6. Reconcile when the IdP published the new key and when it began signing with the new private key.
7. Inspect the SP static `RelyingPartyRegistration` snapshot or JWT JWKS cache/TTL/refetch on each node.
8. Distinguish encryption failures, IdP-rejected signed AuthnRequests, cert `NotAfter`, and signed assertion time expiry.
9. Fix the right config: import the approved new public verification key, refresh metadata/rebuild repository/reload cache, and keep the old key during the approved overlap.
10. Verify valid new-signed traffic passes while tampered, wrong issuer, wrong audience, retired key, and expired traffic still reject.
11. Roll out node/region by node/region, watch failure metrics, confirm no intermittent failures remain, and keep a rollback plan ready.
12. Close RCA: owner, certificate fingerprints, keyset versions, change ticket, postmortem, rotation calendar, and runbook updates.

Ownership: IdP/AS admin manages signers and publishes keys; SP/API team manages registration/decoders/caches; Platform owns DNS/TLS/network/rollouts; Security/IAM approves trust anchors/compromise response; QA/SRE owns synthetic tests/metrics.

## 12. Signature, Key, and Rotation Test Matrix

To test audience independently, you must generate a validly signed message/token with the wrong audience. If you merely edit XML/JSON after signing, the signature fails first and does not prove the audience validator works.

| # | Scenario | Expectation |
| --- | --- | --- |
| 1 | SAML signed by trusted IdP, valid claims | Login passes after local authorization. |
| 2 | SAML signed by attacker private key | Reject signature/trust. |
| 3 | SAML `KeyInfo` contains attacker X.509 cert | Do not auto-trust. |
| 4 | SAML `NameID` altered after signing | Reject signature. |
| 5 | XML Signature Wrapping signed Alice + unsigned Mallory | Never grant Mallory principal. |
| 6 | Signed Response valid yet another Assertion outside coverage | Reject untrusted data. |
| 7 | IdP uses old key, SP trusts old | Passes during old valid period. |
| 8 | IdP signs new yet SP trusts only old | Fail closed. |
| 9 | SP trusts old+new, IdP signs new | Passes. |
| 10 | SP trusts old+new, unexpired old fixture | Passes during overlap. |
| 11 | Old key retired | Reject old-signed messages. |
| 12 | Wrong IdP EntityID/registration | Reject issuer/trust. |
| 13 | SAML wrong audience/recipient, valid signature | Reject protocol claims. |
| 14 | X.509 signing cert past `NotAfter`, signature math verifies | Evaluate cert policy separately; do not misclassify. |
| 15 | SAML assertion `NotOnOrAfter` expired | Reject time. |
| 16 | Metadata endpoint HTTPS CA invalid | Fail if no valid trusted snapshot per policy. |
| 17 | Static registration not yet updated with new cert | Fails; requires reload/rebuild. |
| 18 | Node A trusts new, B only old | Catch node inconsistency. |
| 19 | IdP rejects SP signed AuthnRequest | Check SP signing credentials. |
| 20 | `EncryptedAssertion` decryption failed | Check SP decryption keys. |
| 21 | IdP encryption certificate misused as signing verifier | Reject/config QA fail. |
| 22 | Metadata altered from untrusted origin | Do not load public keys. |
| 23 | JWT RS256 valid issuer/audience/key | API passes. |
| 24 | New JWT `kid`, cache holds only old | `KEY_NOT_FOUND`, refresh trusted JWKS. |
| 25 | JWT JWKS overlap old+new | Both new and unexpired old pass. |
| 26 | Right JWT `kid` yet signed by wrong private key | `SIGNATURE_INVALID`. |
| 27 | JWT `kid` reused with different key bytes | Reject; investigate issuer rotation. |
| 28 | JWT `alg=none` | Reject. |
| 29 | JWT `jku`/`x5u` points to attacker | Never fetch arbitrary key URLs. |
| 30 | JWK `use=enc` while token needs `sig` | Reject incompatible key. |
| 31 | Wrong JWT issuer, signature may verify | Reject issuer. |
| 32 | API receives web client's ID Token | Reject audience/token type. |
| 33 | Expired `exp` or future `nbf` | Reject time. |
| 34 | JWKS endpoint 404/timeout | Fail closed if no valid trusted key is available. |
| 35 | JWKS HTTPS certificate expired | Never disable TLS validation. |
| 36 | Custom cache fails to refresh on unknown `kid` | Diagnose stale keyset, fix cache. |
| 37 | Signing private key compromised | Emergency revoke; keep no overlap. |
| 38 | Token verified yet user disabled | Local authorization deny. |
| 39 | Cross-tenant wrong issuer/registration | Reject. |
| 40 | Debug log contains raw SAMLResponse/JWT/private key | Security QA fail. |
| 41 | Certificate inventory alerts before expiry | Schedule planned rotation change. |
| 42 | Roll back to old signer inside approved window | Accept old trusted key only when policy allows. |
| 43 | Same JWT `kid` yet incompatible `kty`/`alg` | Reject/no candidate. |
| 44 | Valid SAML signature yet user lacks role | 403/local deny. |
| 45 | Metadata 200 yet malformed/wrong issuer | Reject metadata. |

Best outcome: positive new-signed fixtures pass after rotation while tampered, wrong issuer/audience, retired old key, expired, and untrusted key fixtures are still rejected. Never delete negative tests just to turn CI green.

## 13. Common Anti-Patterns and Replacements

| Anti-Pattern | Replace With |
| --- | --- |
| Trust any certificate when the IdP rotates | Import approved IdP public verification keys from trusted metadata, with overlap. |
| Treat `KeyInfo` from Response as trust anchor | Pin verification credentials per registration. |
| Let users log in whenever JWT `kid` matches | Still verify trusted JWK, algorithm, signature, and claims. |
| Fetch JWKS from user token's `jku` | Server-configured trusted issuer discovery/JWKS URI. |
| Skip signature when no matching key exists | Fail closed and fix key publishing/refresh/reload. |
| Confuse X.509 `NotAfter` with JWT `exp` | Investigate cert policy and token lifetime separately. |
| Rotate IdP signing cert when decryption fails | Inspect SP decryption key and IdP encryption cert. |
| Change IdP response signer when IdP rejects AuthnRequest | Inspect SP signing key and IdP's SP trust config. |
| Trust whichever `alg` the JWT header requests | Enforce an `alg` allowlist matching the trusted issuer. |
| Drop old key immediately during planned rotation | Keep bounded overlap per TTL and policy. |
| Keep old verification keys indefinitely | Retirement deadline, metrics, and rotation controls. |
| Log raw SAML XML/JWTs in prod | Sanitized reason codes/trace IDs and limited lab debugging. |

## 14. Acceptance Checklist

### SAML2

- [ ] IdP EntityID and `RelyingPartyRegistration` match the right environment/tenant.
- [ ] Right IdP public verification key used; not confused with SP signing/decryption or HTTPS TLS certs.
- [ ] Metadata trust/integrity, key fingerprints, and certificate dates inventoried.
- [ ] Spring/OpenSAML verifies signatures/coverage and prevents XML Signature Wrapping.
- [ ] Issuer, audience, recipient/destination, `NotBefore`/`NotOnOrAfter`, and `InResponseTo` remain active.
- [ ] Static metadata snapshots have a refresh/redeploy plan and node parity.
- [ ] Planned old+new overlap or compromised-key revocation policy is explicit.

### OIDC/JWT

- [ ] Trusted issuer/JWKS URI pinned/configured server-side.
- [ ] `kid`/`kty`/`alg`/`use`/`key_ops` checked per policy; arbitrary header URLs never trusted.
- [ ] `JwtDecoder` verifies signature, issuer, `exp`/`nbf`, and API audience.
- [ ] ID Token uses `client_id` as `aud`; API access token uses resource `aud`.
- [ ] Cache refresh and unknown `kid` behavior tested on the actual version.
- [ ] Key rotation tests cover publisher/consumer timing.

### Observability and Incident Handling

- [ ] Error metrics by protocol/registration/stage/reason have low cardinality.
- [ ] Alerts exist for JWKS/metadata fetch errors, keyset age, and signing cert `NotAfter`.
- [ ] Logs never expose raw tokens, keys, cookies, or full user attributes.
- [ ] Golden signed old/new fixtures and negative tests for tampering/unknown keys exist.
- [ ] Key fingerprints confirmed against approved change records.
- [ ] Incident closed only when fail-closed signature verification remains active.

## 15. Review Questions

1. How do invalid signature and key not found differ? Key not found means no trusted candidate exists, whereas signature invalid means a candidate was tried yet failed verification.
2. Can an `X509Certificate` inside SAML `KeyInfo` be trusted directly? No, it must be anchored to trusted IdP verification credentials.
3. Are TLS certificates and SAML signing certificates interchangeable? No, they protect transport and signed messages at different layers.
4. If an X.509 certificate is past `NotAfter`, will signature bytes always fail math verification? No, mathematical signature verification and certificate validity/trust policy are two separate checks.
5. Why must a new public key be published before signing with the new private key? Consumers need to load the new key before encountering new-signed traffic.
6. When should an old key be retired immediately without overlap? Upon key compromise or when emergency security policy demands it.
7. Is a JWT `kid` a trust anchor? No; it is an untrusted selector and must verify using a key from a trusted issuer.
8. Why can configuring only `jwk-set-uri` without checking issuer be dangerous? It lacks an exact `iss` binding from the API trust contract.
9. Which keys must be checked when SAML encrypted assertion decryption fails? The SP private decryption key and the IdP's SP encryption public cert.
10. Which keys must be checked when the IdP fails to verify a signed AuthnRequest? The SP signing private key/cert registered at the IdP.
11. Does `InMemoryRelyingPartyRegistrationRepository` automatically reload signing certs on every request? Never assume so; snapshots normally require rebuild/reload.
12. Why might errors appear on only one pod after rotation? Metadata/JWKS cache/config versions may differ across pods.
13. Once a signature is valid, can audience/time checks be skipped? No, trust, audience, and time are independent constraints.
14. Should raw JWT/SAMLResponse be logged for easier debugging? No; use sanitized reasons, trace IDs, and controlled sandbox environments.

## 16. Authoritative Documentation

1. [Spring Security SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): `RelyingPartyRegistration`, IdP verification credentials, and SAML login.
2. [Spring Security Authenticating SAML2 Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): signature/decryption/claims validation; check API version as newer docs use OpenSAML5.
3. [Spring Security SAML2 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html): asserting-party metadata, trust, and metadata signatures.
4. [Spring Security 6.3 OpenSaml4AuthenticationProvider API](https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/saml2/provider/service/authentication/OpenSaml4AuthenticationProvider.html): provider family matching Spring Security 6.3.
5. [Spring Security OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html): issuer/JWKS/rotation/default validators.
6. [Spring Boot 3.3 Spring Security](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html): SAML/Boot security integration.
7. [OASIS SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): Assertion/conditions/signature semantics.
8. [OASIS SAML 2.0 Metadata](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf): `KeyDescriptor`, `EntityDescriptor`.
9. [W3C XML Signature 1.1](https://www.w3.org/TR/xmldsig-core1/): Reference/canonicalization/KeyInfo.
10. [RFC 7517 JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517): JWKS/`kid`/`kty`/`use`.
11. [RFC 7515 JSON Web Signature](https://www.rfc-editor.org/rfc/rfc7515): JWS `alg`/signature.
12. [RFC 7519 JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): `iss`/`aud`/`exp`/`nbf`.
13. [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token validation.
14. [RFC 8414 OAuth2 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): issuer metadata/JWKS discovery.
15. [OWASP SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html): signature wrapping and trust.
16. [OWASP JWT Cheat Sheet for Java](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html): secure JWT verification.
17. [OpenSSL x509 manual](https://docs.openssl.org/3.0/man1/openssl-x509/): fingerprint/dates/checkend.

Conclusion: When encountering invalid signatures, missing keys, or rotated signing certificates, trace from protocol and the right trusted issuer/registration to metadata/JWKS, verify public keys/fingerprints and cache state, and separate signature, cert policy, and token validity. Fix configuration and planned rotation properly; never disable signature verification or trust a key supplied by an unverified message.