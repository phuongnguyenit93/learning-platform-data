# Boundaries of HTTPS, Digital Signatures, and Message Encryption in Spring Security Federation

## 1. Why Does SSO Need Multiple Layers of Protection?

In Single Sign-On (SSO), an application (Relying Party – RP in OpenID Connect, or Service Provider – SP in SAML) receives an authentication result issued by another party (OpenID Provider – OP, or Identity Provider – IdP). The message may traverse browsers, reverse proxies, gateways, public networks, or other backend services before reaching the component that checks identity.

The problem is not merely "is the transport over HTTPS?", but also:

1. **Which connection is being protected, and who can see the data when that connection terminates?**
2. **Who issued the message, which exact content did they sign, and does the recipient trust the right signing key?**
3. **Who can read identity data or sensitive attributes inside the message?**
4. **Is a cryptographically valid message being used by the right application, at the right time, and in the right login session?**

Three mechanisms often conflated are **HTTPS/TLS**, **message-level digital signatures**, and **message encryption**. They protect different boundaries. A secure federation system must use and verify them in their exact roles while binding the result to protocol context.

**Objective:** accurately explain each trust boundary, compare OIDC and SAML 2.0, recognize limits at TLS termination, distinguish signed vs. encrypted tokens, apply them in Spring Security, and troubleshoot real configuration errors.

## 2. Three Boundaries: Transport Channel, Issuer Origin, and Reader

### 2.1. HTTPS/TLS: Protecting *Each Transport Connection*

TLS typically provides:

- **Confidentiality in transit:** eavesdroppers on the wire cannot easily read plaintext application data.
- **Integrity in transit:** an on-path attacker cannot arbitrarily modify TLS records without detection.
- **Peer authentication on the connection:** in standard HTTPS, the client verifies the server's certificate/identity against hostname and trust chain. Mutual TLS (*mTLS*) can additionally authenticate the client.

Critical limitation: TLS protects **the connection between two TLS endpoints**; once an endpoint decrypts, it sees plaintext. If a connection terminates at a CDN, API gateway, load balancer, or ingress, a **new trust boundary** begins behind it.

```text
Browser ── HTTPS #1 ──> Reverse proxy ── HTTPS #2 ──> Spring Boot RP
                               │
                         TLS terminates;
                         proxy sees HTTP plaintext
```

If the hop between the reverse proxy and the application is plain HTTP, only the first hop has TLS protection. Even when both hops use HTTPS, the intermediate proxy can still inspect data after decrypting the first hop. That can be a valid design when the proxy is trusted, but it is not equivalent to "end-to-end encryption all the way to the RP".

**Do not equate an HTTPS certificate with an identity issuer.** The TLS certificate of `login.example.org` authenticates the server hosting the connection; it does not by itself prove that every SAML assertion or JWT presented over that connection was signed by an IdP/OP trusted by the RP, let alone that the assertion was intended for the current RP.

### 2.2. Digital Signatures: Protecting *Signed Content* and Binding to a Signing Key

With asymmetric signatures, the issuer uses its **private signing key** to sign data; the recipient uses the **public verification key** bound to the trusted issuer to verify the signature.

When algorithms, keys, and verification procedures are used securely, a signature detects tampering with data **within the signed scope** and proves the message was signed by the holder of the corresponding key. A signature **does not make content secret**: a JWS-signed JWT typically still contains a Base64URL-decodable payload; an XML-signed SAML assertion remains readable.

```text
IdP signs message with private signing key
               │
               ▼
      [payload + signature]
               │
    travels via browser / proxy
               │
               ▼
RP verifies using configured trusted IdP public key
  ├─ Signed content modified → signature invalid → reject
  └─ Signature valid → continue checking issuer, audience,
                       timestamps, response binding, session, replay...
```

A valid signature only answers **integrity and signing key**, not "is this application authorized to accept this message?". Without checking `aud`/`iss`/`exp` or `InResponseTo`, a genuine signature can still accompany a token sent to the wrong recipient, an old token, or a replayed message.

**Key trust boundary:** if the RP fetches a public key from a URL specified by an untrusted token or request itself, an attacker can supply their own key and self-sign tokens. Keys/metadata must come from a configured trusted issuer or IdP, with clear key-rotation and algorithm policies. The `kid` value only selects a key within an already-trusted key set; it never creates trust on its own.

### 2.3. Message Encryption: Limiting *Who Can Read the Payload*

Message-level encryption protects content even as the payload passes through intermediaries. Common forms in federation include:

- **SAML XML Encryption:** the IdP may encrypt an `Assertion` or sensitive element using a key for the SP; the SP uses its own **private decryption key** to decrypt.
- **JWE (JSON Web Encryption):** wraps encrypted payloads so only the party holding the matching decryption key can read them. An OIDC ID Token *may* be encrypted by client/OP agreement; do not assume every ID Token is a JWE.
- **Authenticated symmetric encryption (AEAD), such as AES-GCM:** protects confidentiality and detects tampering on ciphertext/associated data (*AAD*) when implemented properly with safe nonce/IV management.

**Encrypting for the SP to read does not by itself prove the IdP issued it.** With asymmetric encryption using the SP's public key, anyone possessing that public key can encrypt data for the SP. Therefore, signatures or an appropriate issuer-authentication mechanism are still required. Nor should you assume every "encryption" algorithm protects integrity automatically: use authenticated, tamper-resistant primitives and configurations.

## 3. Comparison Table for Choosing the Right Mechanism

| Security Question | HTTPS/TLS | Message Digital Signature | Message Encryption |
| --- | --- | --- | --- |
| Protected unit | One connection, one TLS hop | Exact bytes/structure within signed scope | Content encrypted for a set of recipients |
| Can an intermediary read plaintext? | At TLS endpoint: yes | Usually yes, since signing does not hide payload | No, without decryption key and sufficiently strong config |
| Detects tampering? | Yes within that TLS hop | Yes for the **signed** part | Yes if encryption mechanism is authenticated/integrity-checked |
| Proves who sent it? | Authenticates TLS peer, usually server; optional mTLS | Verifies control of signing key bound to trusted issuer | Does not by itself prove plaintext author |
| After TLS termination? | Old hop ends; new hop policy needed | Signature can still be verified at destination | Ciphertext can remain confidential to recipient |
| Prevents replay on its own? | Does not protect cross-session login logic | No | No |
| Replaces issuer/audience/time checks? | No | No | No |
| Typical cases | Browser ↔ IdP, RP ↔ OP Token Endpoint | OIDC signed ID Token, SAML signed Response/Assertion | SAML EncryptedAssertion, OIDC encrypted ID Token if required |

**Easy-to-remember example:** An HTTP response travels over HTTPS containing a signed and encrypted SAML assertion. HTTPS protects each connection, the signature lets the SP verify the issuer/signed content, and encryption hides attributes from the browser and proxies. Neither layer replaces `AudienceRestriction`, `Recipient`, expiration, or anti-replay checks.

## 4. Trust Boundaries When Messages Traverse the Browser

The browser is a user-routing component, yet the RP/SP never treats browser-submitted data as self-verifying proof of authentication.

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant RP as RP / SP
    participant IdP as OP / IdP
    B->>RP: Access login-protected resource
    RP-->>B: Redirect requesting authentication (HTTPS)
    B->>IdP: Visit login page (HTTPS)
    IdP-->>B: Auth result via redirect/form POST (HTTPS)
    B->>RP: Forward code or SAMLResponse (HTTPS)
    RP->>RP: Check state/correlation and protocol policy
    Note over RP,IdP: OIDC code flow adds back-channel HTTPS POST /token
    RP->>IdP: POST /token (OIDC code flow)
    IdP-->>RP: Token response
    RP->>RP: Verify token/signature/claims; create RP session
```

The diagram merges both mechanisms to show the path; **standard SAML Web Browser SSO has no POST /token step**. Meanwhile, OIDC Authorization Code Flow passes a short-lived one-time **authorization code** over the front-channel without needing to expose the ID Token to the browser in a backend-backed app model.

### With OIDC

A signed ID Token is typically a three-part JWS `BASE64URL(header).BASE64URL(payload).BASE64URL(signature)`. Decoding the first two parts to inspect them **does not mean verified**. The RP must verify the signature against the right key from a trusted OP and check required claims—at minimum per flow: `iss`, `aud`, `exp`, `iat`, and `nonce` if sent; plus `azp`, authentication time limits, etc. when protocol conditions demand.

Back-channel HTTPS at the Token Endpoint protects tokens in transit and authenticates the endpoint; **it does not replace OIDC ID Token validation**. The RP must not infer "a token fetched over HTTPS is trustworthy" if the token has the wrong issuer, audience, signature, or token type.

`state` binds the browser response to the created request; PKCE uses `code_challenge` and `code_verifier` to bind authorization code exchange; `nonce` (when used) binds the ID Token to the authorization request. These are **protocol protections**, not variants of digital signatures or TLS.

### With SAML 2.0

Web Browser SSO typically uses Redirect binding to send `AuthnRequest` and HTTP-POST binding for the browser to deliver `SAMLResponse` to the **Assertion Consumer Service (ACS)**. The HTTP-POST payload is typically Base64-encoded. **Base64 is not security encryption.**

An SP may accept a signed Response or a signed Assertion **per its designed profile and policy**; it must verify that **the exact assertion used to establish identity** lies inside validly signed content. Verify `Issuer`, `Destination`, `Recipient`, `AudienceRestriction`, `NotBefore`/`NotOnOrAfter`, `InResponseTo` for SP-initiated flows, signature policy, and replay. Specifically prevent **XML Signature Wrapping**: verifying a signature on one XML node while reading login info from another unsigned node.

If `EncryptedAssertion` is present, the SP needs its decryption key and must continue verifying SAML signatures and conditions afterward using the proper library. Decryption key configuration serves a **different purpose** from the IdP's public certificate used to verify signatures.

## 5. Reverse Proxies: Per-Hop HTTPS Still Leaves Trust Gaps

Suppose a deployment is:

```text
Internet                 Proxy zone                  App zone
Browser ─HTTPS─> Ingress ─HTTP─> Spring Boot RP ─HTTPS─> Identity Provider
                     │                     │
           TLS decrypted at ingress   Calls Token Endpoint
```

- The browser sees the ingress's HTTPS certificate, not necessarily the JVM's certificate. The ingress can see cookies, SAMLResponse, or codes in plaintext while forwarding.
- The HTTP `Ingress → RP` hop must be evaluated against network protections and the threat model; if traversing an untrusted network, re-encrypt with HTTPS and consider appropriate service-to-service/mTLS authentication.
- The `RP → IdP` hop is a **separate** TLS connection with its own trust store, DNS, hostname, and certificate checks; a browser successfully logging into the IdP does not prove the RP can reach the Token Endpoint.
- For signed SAML/JWS, integrity of signed content can still be verified at the RP even though the proxy decrypted HTTPS. However, a proxy can **block, copy, replay, or substitute another validly signed message**; correlation, timestamps, audience, and replay checks are still mandatory.
- If an assertion is encrypted for the SP, a proxy holding only TLS keys cannot read inner attributes. Even so, the proxy still sees metadata outside the ciphertext (URL, size, timing, headers, cookies) and can drop or swap ciphertext.

**Critical forwarded-headers boundary:** Spring Boot behind an ingress may need to understand `Forwarded` or `X-Forwarded-Proto` to generate accurate HTTPS callbacks. Trust headers set only by **trusted proxies**; never let Internet clients craft them to alter computed callback URLs. `redirect_uri`, ACS URL, issuer, and entity ID values must remain consistent with OP/IdP configuration.

## 6. Which Key Is Used for What?

In a federation integration, several certificate/key types may coexist even if dashboards call all of them "certificates":

| Component | Key/Certificate | Private Key Owner | Purpose |
| --- | --- | --- | --- |
| IdP/OP HTTPS | TLS server certificate | IdP/OP TLS endpoint or its proxy | Authenticates hostname and establishes TLS connection |
| RP/SP HTTPS | TLS server certificate | RP/ingress TLS endpoint | Protects connection from browser to RP |
| OIDC signing | Signing key published by OP via trusted metadata/JWKS | OP | RP verifies OP's JWS/ID Token |
| SAML signing | IdP verification certificate trusted by RP | IdP | SP verifies XML Signature of Response/Assertion |
| SAML decryption | SP public encryption certificate and matching private key | SP | IdP encrypts assertion for SP; SP decrypts |
| SAML AuthnRequest signing (if enabled) | SP signing key and matching public certificate | SP | IdP verifies AuthnRequest came from SP |
| mTLS client | Client certificate and private key | TLS connection client | Peer server can authenticate client on the connection |

Never swap keys just because they are all `RSA` or `X.509`. Signing and encryption keys may relate in some deployments, but **separating keys by purpose** aids access control, limits key-compromise blast radius, and simplifies rotation. JWKS/certificate rotation plans must support an overlap phase with both old and new keys valid, then retire the old key once related content/sessions expire per policy.

**Impact of key compromise:** exposing an HTTPS endpoint's private key affects connections/sessions within its threat model; exposing the IdP's private signing key enables forging IdP-"signed" assertions/tokens; exposing the SP's private decryption key allows reading data encrypted for the SP (if ciphertext was captured). Never treat these three incidents as identical.

## 7. Java 17 Example: Clearly Seeing Distinct Roles of Signatures and Encryption

This standalone Java SE 17 program demonstrates **ECDSA** (signing, verification) and **AES-GCM** (authenticated encryption). The code generates fresh random keys on each run, does not emulate an OP or SP, and **does not replace** Spring Security's OIDC/SAML libraries.

Save as file `MessageBoundaryDemo.java`:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.security.Signature;
import java.security.spec.ECGenParameterSpec;
import java.util.Arrays;

import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class MessageBoundaryDemo {

    private static byte[] bytes(String value) {
        return value.getBytes(StandardCharsets.UTF_8);
    }

    private static boolean verify(
            PublicKey publicKey, byte[] data, byte[] signature)
            throws GeneralSecurityException {
        Signature verifier = Signature.getInstance("SHA256withECDSA");
        verifier.initVerify(publicKey);
        verifier.update(data);
        return verifier.verify(signature);
    }

    public static void main(String[] args) throws Exception {
        byte[] message = bytes("sub=alice;aud=service-a");

        // 1. Sign with private key; verify with public key.
        KeyPairGenerator keyGenerator = KeyPairGenerator.getInstance("EC");
        keyGenerator.initialize(new ECGenParameterSpec("secp256r1"));
        KeyPair pair = keyGenerator.generateKeyPair();

        Signature signer = Signature.getInstance("SHA256withECDSA");
        signer.initSign(pair.getPrivate());
        signer.update(message);
        byte[] signature = signer.sign();

        byte[] changed = message.clone();
        changed[0] ^= 1; // Attempt to modify content after signing.

        System.out.println("signatureValid="
                + verify(pair.getPublic(), message, signature));
        System.out.println("signatureValidAfterChange="
                + verify(pair.getPublic(), changed, signature));

        // 2. Authenticated encryption with AES-GCM.
        KeyGenerator aesGenerator = KeyGenerator.getInstance("AES");
        aesGenerator.init(128);
        SecretKey aesKey = aesGenerator.generateKey();

        byte[] iv = new byte[12]; // 96-bit GCM nonce, must be unique per key.
        new SecureRandom().nextBytes(iv);
        byte[] aad = bytes("recipient=service-a");

        Cipher encryptor = Cipher.getInstance("AES/GCM/NoPadding");
        encryptor.init(Cipher.ENCRYPT_MODE, aesKey,
                new GCMParameterSpec(128, iv));
        encryptor.updateAAD(aad);
        byte[] ciphertext = encryptor.doFinal(message);

        Cipher decryptor = Cipher.getInstance("AES/GCM/NoPadding");
        decryptor.init(Cipher.DECRYPT_MODE, aesKey,
                new GCMParameterSpec(128, iv));
        decryptor.updateAAD(aad);
        byte[] restored = decryptor.doFinal(ciphertext);
        System.out.println("plaintextRestored="
                + Arrays.equals(message, restored));

        // 3. Attempt to tamper with ciphertext: GCM checks the authentication tag.
        byte[] tampered = ciphertext.clone();
        tampered[tampered.length - 1] ^= 1;
        Cipher rejector = Cipher.getInstance("AES/GCM/NoPadding");
        rejector.init(Cipher.DECRYPT_MODE, aesKey,
                new GCMParameterSpec(128, iv));
        rejector.updateAAD(aad);
        boolean tamperRejected = false;
        try {
            rejector.doFinal(tampered);
        } catch (AEADBadTagException expected) {
            tamperRejected = true;
        }
        System.out.println("ciphertextTamperRejected=" + tamperRejected);
    }
}
```

Run with Java 17+:

```bash
javac MessageBoundaryDemo.java
java MessageBoundaryDemo
```

Standard output result (independent of random keys, since it prints only `boolean`s):

```text
signatureValid=true
signatureValidAfterChange=false
plaintextRestored=true
ciphertextTamperRejected=true
```

**Read the output within proper scope:** flipping a byte in the message invalidates the signature; altering the ciphertext causes AES-GCM to reject decryption. However, the demo has no issuer/audience/expiration/nonce from a real protocol, nor does it establish HTTPS or key distribution. In a real system, key management, a unique IV for **every encryption under the same GCM key**, peer authentication, and binding tokens to the exact audience remain mandatory. Never reuse a nonce with the same key in AES-GCM.

## 8. Applying to Spring Security

### 8.1. OIDC: Trust Issuer, Verify ID Token, and Protect Back-Channel

With Spring Security 6.x / Spring Boot 3.x, the RP backend uses `spring-boot-starter-oauth2-client` and `oauth2Login`. Example declaration for a trusted OIDC issuer:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: YOUR_CLIENT_ID
            client-secret: YOUR_CLIENT_SECRET_FROM_SECRET_STORE
            authorization-grant-type: authorization_code
            scope: [openid, profile]
        provider:
          company:
            issuer-uri: https://idp.example.org/realms/company
```

The example is a **configuration template requiring value replacement**, usable only with a real OP supporting OIDC discovery at the registered issuer. Never commit real client secrets into YAML. Spring Security uses trusted provider details to perform OIDC login steps and token verification per framework mechanisms; the application must also properly configure the registered redirect URI, sessions, access permissions, and proxies.

A minimal `SecurityFilterChain` (snippet belonging to a Spring Boot application already having provider config/dependencies) illustrating where the mechanism is enabled:

```java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/").permitAll()
                    .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
}
```

Requires imports `org.springframework.context.annotation.Bean`, `org.springframework.security.config.annotation.web.builders.HttpSecurity`, `org.springframework.security.config.Customizer`, and `org.springframework.security.web.SecurityFilterChain`. This is an **illustrative bean method**, not a standalone Java program. Spring OAuth2 Login includes built-in protocol checks and is strongly preferred over manually parsing JWTs. In backend-backed applications, the `POST /token` exchange happens server-to-server; the browser typically sees only the redirect through the Authorization Endpoint and the callback containing the code.

When debugging, distinguish:
- **Token Endpoint TLS error:** certificate/hostname, proxy, DNS, or timeout error occurring before or while calling the endpoint; no token exists yet to verify.
- **ID Token signature/claims error:** TLS succeeded, yet issuer/audience/signature/nonce failed; never "skip verification" to bypass the error.
- **Authentication succeeded, insufficient permissions:** a valid session/identity does not mean the user can access every resource.

Never use an ID Token to call APIs in place of an Access Token; an Access Token meant for a Resource Server must be verified under its own contract (JWT or opaque token/introspection).

### 8.2. SAML: Separating Verification Credentials and Decryption Credentials

Spring Security provides `saml2Login` and `RelyingPartyRegistration`. At minimum, the SP needs IdP details/metadata and a **trusted verification certificate** to verify SAMLResponse/Assertion. When the IdP sends an `EncryptedAssertion`, the SP also needs a **decryption credential** (private key and corresponding certificate).

The API difference is illustrated by two credential-creation methods; this snippet belongs to Spring configuration, not standalone Java SE:

```java
Saml2X509Credential verifyIdpSignature =
        Saml2X509Credential.verification(idpSigningCertificate);

Saml2X509Credential decryptForSp =
        Saml2X509Credential.decryption(
                spDecryptionPrivateKey,
                spDecryptionCertificate);
```

Here `idpSigningCertificate` is a trusted `X509Certificate` received via the IdP configuration channel, `spDecryptionPrivateKey` is an `RSAPrivateKey` managed as a secret, and `spDecryptionCertificate` is the SP's certificate. Requires importing `org.springframework.security.saml2.core.Saml2X509Credential`; the example assumes the three key objects were securely loaded from a key store.

In `RelyingPartyRegistration`, verification credentials belong to the **asserting party** configuration; decryption credentials belong to the **relying party**. Spring Security/OpenSAML is responsible for decryption, signature verification, and SAML condition checks when configured properly. Manually "grabbing the first XML node with NameID" or checking a signature without verifying which element was signed opens the door to XML Signature Wrapping.

**Never use the IdP's TLS certificate as the SAML verification certificate** unless the partner explicitly confirms they are the same key and distributes it over a trusted channel; the keys have different responsibilities. Likewise, an encryption certificate intended for the SP must never be treated as the IdP's signing certificate.

## 9. Common Cases: Cryptographically Protected Yet Still Insecure

### Case A – Valid HTTPS Yet Wrong User/App Accepted

An RP receives an ID Token over a properly secured HTTPS connection. The token may be signed by the real OP yet carry an `aud` targeting another client. If the RP sees a valid signature and immediately creates a session, it has breached the recipient boundary.

**Mitigation:** check issuer, audience, client correlation, token type, expiration, and nonce per OIDC; trust only configured providers/JWKS. HTTPS does not decide audience.

### Case B – Valid SAML Signature Yet Selected Assertion Is Unprotected

In a malicious XML document, one validly signed assertion sits alongside another unsigned assertion. If the program checks the signature on the valid node while extracting identity from the other node, spoofing remains possible.

**Mitigation:** use OpenSAML/Spring Security to verify the exact element consumed, enforce signature policies, schema validation/hardened XML parsers, and prevent signature wrapping. Never write a manual XML signature validator just to shorten implementation.

### Case C – Signed Without Encrypting User Attributes

A signed `SAMLResponse` travels in an HTML form POST over HTTPS. The browser can still inspect the form's payload once content reaches the browser; Base64 decodes the attributes.

**Mitigation:** when the threat model requires hiding assertions from browsers/intermediaries, negotiate `EncryptedAssertion` for the SP and protect the decryption key. Signatures do not replace content confidentiality.

### Case D – Encrypted Without Verifying the Issuing Source

The SP successfully decrypts a payload encrypted with the SP's public key. Because public keys are not secret, successful decryption does not by itself prove the IdP issued the data.

**Mitigation:** after decryption, verify the signature from a trusted issuer and federation conditions. If using AEAD between two parties sharing a secret, the authentication tag proves the creator knew the secret, yet still does not by itself establish user identity or token permissions.

### Case E – Genuine Signed Token Gets Replayed

An attacker copies a still-valid message and resends it in another callback. The signature remains valid; encryption still decrypts.

**Mitigation:** bind the response to the original request/session, `state`, `nonce`, `InResponseTo`, check expiration, and maintain a replay cache/ID store per protocol requirements. Replay defense is also needed at the application layer.

### Case F – Untrusted Key Rotation

A JWT carries an unknown `kid` or a header containing a key URL. If the RP automatically downloads keys from a URL embedded inside an unverified token, an attacker can issue self-signed tokens and trick the RP into accepting them.

**Mitigation:** restrict keys and algorithms to trusted issuers; refresh JWKS only at controlled config/discovery endpoints, govern key rotation, and block SSRF.

## 10. Checklist for Auditing a Federation Flow

When designing or reviewing an integration, check in order:

1. **Hop map:** browser → OP/IdP, browser → RP/SP, proxy → app, app → token/metadata/JWKS endpoints. For each hop, who is the TLS endpoint, who sees plaintext, and is mTLS required?
2. **Signatures:** which messages must be signed; `Response` vs. `Assertion` in SAML; JWS of ID Token in OIDC; which keys are trusted, which algorithms are accepted, and which exact bytes are verified?
3. **Encryption:** is there sensitive data that must stay hidden from browsers, proxies, or intermediate services? Which recipient holds the private decryption key? Do both sides support JWE/EncryptedAssertion?
4. **Protocol semantics:** `iss`/`aud`/`exp`/`nonce`/`state`/PKCE or `Issuer`/`AudienceRestriction`/`Recipient`/`InResponseTo`; anti-replay and clock skew.
5. **Key lifecycle:** provisioned via trusted channel, secrets stored securely, access restricted, rotation, revocation, ensuring configs reject out-of-policy keys/algorithms.
6. **Operations:** RP cookies, redirect URI/ACS, proxy headers, actual backend HTTPS, token/secret-redacted logs, connection timeouts, and error observability without leaking data.

For real-world failures, **separate by layer**: TLS handshake/hostname failure is a connection issue; signature verification failure is a signed-content/key-trust issue; decryption failure is an encryption key/algorithm issue; a verified token rejected for audience, nonce, or replay is a **federation-context** issue. Never weaken verification to "fix" an error in another layer.

## 11. Self-Check

**Question 1.** A browser accesses the IdP over HTTPS and delivers a signed `SAMLResponse` to the SP. A proxy in front of the SP terminates TLS. Can the proxy see the assertion?  
**Answer:** Yes, if the assertion is only signed and not message-level encrypted; after TLS termination the proxy sees HTTP plaintext. To hide attributes from the proxy, encrypt the assertion for the SP by design.

**Question 2.** Is a valid ID Token signature enough to create a session for any application?  
**Answer:** No; the application must also check issuer, audience, expiration, nonce when required, exact transaction binding, and other OIDC conditions.

**Question 3.** Once the SP successfully decrypts an `EncryptedAssertion`, does it already know who issued the assertion?  
**Answer:** No; it must still verify the signature and SAML conditions using a trusted IdP signing key.

**Question 4.** Does a backend call to the Token Endpoint over HTTPS mean the token response needs no claim verification?  
**Answer:** No; TLS protects transport, while accepting an ID Token must follow OIDC rules.

**Question 5.** Can `kid` in a JWS be used to fetch any public key from a URL inside the token?  
**Answer:** No; `kid` is only used to select from a key set already bound to a trusted issuer.

## 12. References

- [OWASP – SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet): TLS, signatures, encryption, XML Signature Wrapping, and replay.
- [Spring Security – SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): authentication flow, verification, and decryption credentials.
- [Spring Security – Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): SAML verification and decryption steps.
- [Spring Security – OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html): OIDC/OAuth2 integration in Servlet.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token validation, claims, and Authorization Code flow.
- [RFC 7515 – JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515.html) and [RFC 7516 – JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516.html): formats for message-level integrity and confidentiality.
- [RFC 9700 – OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700.html): security considerations for authorization codes, PKCE, redirects, and tokens.
