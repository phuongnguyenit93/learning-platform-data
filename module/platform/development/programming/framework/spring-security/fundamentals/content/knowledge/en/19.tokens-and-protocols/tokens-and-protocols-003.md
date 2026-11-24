# JWT Is a Token Format, Not an Entire Login Protocol

## 1. Understanding the Problem Correctly: JWT Answers a Data Question, Not the Entire Login Question

When developing with Spring Security, many tutorials illustrate login like this: the client sends a username/password, the server returns a string with three dot-separated parts, and the client keeps that string to send in the `Authorization` header. That string is usually a **JWT (JSON Web Token)**. From there, it is easy to jump to the false conclusion that **JWT itself is the login protocol**.

In reality, **JWT is a format for representing claims** (assertions about identity, permissions, timestamps, or context) in a compact form suitable for transport between parties. A JWT can be integrity-protected using **JWS** or encrypted using **JWE**. Choosing JWT does not by itself specify how users are authenticated, who issues tokens, which clients may receive tokens, how long tokens last, which APIs can be used, or how renewal, revocation, and logout work.

A secure system must separate at least four questions:

1. **Authentication:** By what method does the user/client prove identity? Password, passkey, MFA, session, client certificate, OAuth/OIDC redirect?
2. **Token issuance:** Which party is trusted to issue credentials and authorized to sign/encrypt tokens?
3. **Token presentation and validation:** Where does the client present the credential? How does the server verify signature, issuer, audience, expiration, intended purpose, and permissions?
4. **Authorization and lifecycle:** What can the authenticated principal do, how are credentials revoked or expired, and when is re-authentication required?

**JWT does not automatically accomplish those four steps.** JWT may appear in a protocol like OpenID Connect, be used as an access token in an OAuth 2.0 deployment, serve as an internal token, or not be used in a login system at all.

### Learning Objectives

After this lesson, you will be able to:
- Read JWT structure, understand JWS/JWE, and distinguish Base64url encoding from security.
- Explain the roles of **OAuth 2.0**, **OpenID Connect (OIDC)**, **Authorization Server**, **Resource Server**, and JWT.
- Distinguish **ID tokens, access tokens, refresh tokens, and session cookies**; avoid using them for the wrong purpose.
- Know the conditions required to verify a JWT before treating a request as authenticated.
- Configure Spring Boot 3.x / Spring Security 6.x as a **JWT Resource Server** based on a trusted issuer.
- Run a Java 17+ program demonstrating signatures and how modifying the payload invalidates the signature.
- Recognize mistakes such as trusting the payload after Base64 decoding, ignoring audience, or using an ID token instead of an access token.

Lesson scope: focuses on **tokens and protocols** fundamentals; does not build an Authorization Server or a complete login protocol from scratch.

## 2. Distinguishing Four Commonly Conflated Concepts

| Concept | Nature | Example | Not Synonymous With |
| --- | --- | --- | --- |
| **JWT** | Format for transmitting claims per RFC 7519 | A three-part compact JWS | Login, OAuth 2.0, OIDC, or authorization |
| **OAuth 2.0** | Authorization framework defining roles/flows for obtaining and using access tokens | Authorization Code + PKCE | Requiring JWT or directly providing user identity attestation to the client |
| **OpenID Connect (OIDC)** | **Identity authentication** layer built on top of OAuth 2.0 | OIDC login receiving an ID token | Every access token being an ID token |
| **HTTP session** | Server-side state that can persist across multiple requests | `HttpSession` tied to a `JSESSIONID` cookie | A JWT or a token signed by an authorization server |
| **Bearer access token** | Credential: whoever holds a valid token can present it to access resources within allowed scopes | `Authorization: Bearer ...` | Always being a JWT; a Bearer token can be opaque |
| **Spring SecurityContext** | Context holding `Authentication` for request processing and authorization | `SecurityContextHolder` during a request | Automatically being a JWT or an `HttpSession` |

Key point: **OAuth 2.0 can use opaque access tokens**, not only JWTs. An application **not using OAuth/OIDC** can still issue its own JWTs under a custom protocol, but then the developer must design many critical details around security, operations, and credential lifecycle. For standard login needs, prefer proven standard protocols and components.

### Two Systems Both Using JWT Can Be Completely Different

**System A:** An SPA redirects users to an Identity Provider using OIDC Authorization Code + PKCE. The Authorization Server performs authentication and returns an authorization code, and the client exchanges the code for tokens per the protocol. The API uses a verified JWT access token.

**System B:** A client POSTs `/api/login` with JSON username/password to a custom backend. The backend checks the password itself, signs a JWT itself, and returns it. There is no OAuth Authorization Code, no OIDC discovery, no ID token, and no independent Identity Provider.

**Both A and B can return a JWT**, yet their sequences, protocols, trust boundaries, attack mitigations, permissions, and engineering responsibilities are vastly different. Seeing three Base64url segments does not tell you whether a system is A or B.

## 3. What Structure Does a JWT Actually Have?

Under RFC 7519, a JWT contains a set of claims encapsulated in a **JWS** (JSON Web Signature) or **JWE** (JSON Web Encryption) structure. The most common case in REST APIs is **JWS compact serialization** with three parts:

~~~text
BASE64URL(Protected Header) . BASE64URL(Payload) . BASE64URL(Signature)
          part 1                   part 2                  part 3
~~~

A real token has parts consisting of Base64url character strings. Dots separate the parts. To illustrate the shape without showing a fake signature that could be mistaken for a valid token:

~~~text
<encoded-header>.<encoded-payload>.<encoded-signature>
~~~

The line above is a **diagram**, not a usable credential. Compact JWS JWTs typically have three parts; compact JWEs have **five parts** with a different encryption structure. Do not claim every JWT has three parts; also be aware of other JOSE serialization forms.

### 3.1. Header

The header describes cryptographic processing information, for example:

~~~json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "signing-key-2026"
}
~~~

- **alg**: integrity/signature protection algorithm; for example RS256, ES256, or HS256 depending on the system.
- **typ**: object type; can help distinguish JWT types in profiles that specify concrete types.
- **kid**: key ID hint so the verifier selects the matching public key from a **configured trusted key set**.

**The header is data supplied by the sender, not a list of trusted commands.** The Resource Server must enforce an explicit algorithm/key policy, never automatically accepting whatever algorithm the header requests, and never treating an arbitrary URL supplied in the header as a trusted key source.

### 3.2. Payload and Claims

Example claims of an access token under a specific profile:

~~~json
{
  "iss": "https://idp.example.org/realms/training",
  "sub": "user-123",
  "aud": "reports-api",
  "iat": 1793800000,
  "nbf": 1793800000,
  "exp": 1793800900,
  "scope": "reports.read reports.write"
}
~~~

The numeric timestamps only **illustrate Unix timestamps**, not a token currently valid at the time you read this. The `scope` field above represents a system permission convention; **scope** is not a mandatory registered claim of every JWT.

| Claim | Typical Meaning | Verification Concerns |
| --- | --- | --- |
| **iss** | Issuer: the issuing party | Must match a **system-trusted issuer** by exact identifier |
| **sub** | Subject: identity of the principal | Must be interpreted in the issuer's context; do not arbitrarily treat as a globally unique email |
| **aud** | Audience: intended recipient(s) | Must contain the API/client receiving the token as intended; reject tokens issued for other systems |
| **exp** | Expiration time | Reject expired tokens according to time rules and reasonable clock skew |
| **nbf** | Not before: do not use before this time | Reject tokens not yet active |
| **iat** | Issued at: issuance time | Can be used to enforce token age policies if required by profile |
| **jti** | JWT ID | Can support replay prevention or revocation lists if the system designs such mechanisms |
| **scope / scp** | Scopes granted per OAuth/token issuer profile | Map accurately to authorities and only permit operations within scope |
| **roles / permissions** | Custom business permissions | Not automatically interpreted as Spring `GrantedAuthority` without a suitable converter |

Not all claims above are mandatory under the JWT format; **each protocol profile and application policy** determines which claims must be present and how they are checked. For example, **`exp` is not automatically generated just because the payload is JSON**.

### 3.3. Base64url Is Not Secret Encryption

In a standard JWS, the header and payload are only **encoded for transport**, not hidden. Anyone holding the token can decode the first two parts and read the claims; no private key is needed.

Therefore:
- **Do not place passwords, OTPs, private keys, secrets, or unnecessary personal data** in a JWS payload.
- Do not treat users not knowing how to Base64url decode as a security barrier.
- **Do not treat successful decoding as proof that a token is valid.** A forged string can also be readable JSON.
- A valid signature guarantees **integrity/authenticity of the signing source** for an allowed key and algorithm; it **does not guarantee confidentiality**.
- If token contents need confidentiality in transit/storage, consider JWE or omit sensitive data from the token, while still using TLS.

### 3.4. JWS and JWE Differ

| Characteristic | JWS | JWE |
| --- | --- | --- |
| Primary goal | Integrity and authentication of signed/MACed content | Confidentiality via encryption |
| Common compact JWT | 3 parts | 5 parts |
| Payload readable on Base64url decode? | **Yes**, in the standard compact JWS case | **No**, ciphertext must be decrypted |
| Required processing | Verify signature/MAC per policy, then check claims | Decrypt with a trusted key, then check all claims and related protections |
| Combinable? | Yes: nested JWT per appropriate profile | Yes: encrypt a signed JWT and process in the prescribed order |

**JWT does not automatically mean a signed JWT.** Formats and profiles offer different options, including unsecured cases without integrity protection. A system using JWTs as security credentials must **reject tokens lacking appropriate protection or using algorithms outside an allowlist**.

## 4. Standalone Java 17+ Lab: Reading Payload vs. Verifying Signature

The following example runs with **JDK 17+**, without needing Spring Boot, Maven, or a JSON library. It creates a JWS with **HS256** using a lab-only secret, verifies the HMAC signature, and shows that changing the subject from `alice` to `admin` invalidates the signature.

This lab **does not create a login protocol**, **does not authenticate username/password**, and **is not a production JWT library**. Its sole goal is to observe structure, Base64url, and integrity. For real JWT usage, use standard libraries and policies validating claims, issuer, audience, token type, time, and key rotation.

### 4.1. Source Code

Create file **JwtFormatLab.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.Base64;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public class JwtFormatLab {

    // For local experimentation only.
    // Do not hardcode signing secrets in production products.
    private static final byte[] LAB_KEY =
            "classroom-key-not-for-real-token-signing-2026"
                .getBytes(StandardCharsets.UTF_8);

    private static final String HEADER =
            "{\"alg\":\"HS256\",\"typ\":\"JWT\"}";

    private static String encode(String text) {
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(
                    text.getBytes(StandardCharsets.UTF_8));
    }

    private static String encodeBytes(byte[] bytes) {
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(bytes);
    }

    private static String decode(String encoded) {
        return new String(
            Base64.getUrlDecoder().decode(encoded),
            StandardCharsets.UTF_8);
    }

    private static byte[] sign(String signingInput) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(LAB_KEY, "HmacSHA256"));
        return mac.doFinal(
            signingInput.getBytes(StandardCharsets.UTF_8));
    }

    private static boolean hasValidSignature(String token)
            throws Exception {
        String[] parts = token.split("\\.", -1);
        if (parts.length != 3) {
            return false;
        }

        try {
            // Lab allows only a fixed protected header, preventing
            // algorithm selection driven by arbitrary input data.
            if (!HEADER.equals(decode(parts[0]))) {
                return false;
            }

            byte[] expected = sign(parts[0] + "." + parts[1]);
            byte[] received =
                    Base64.getUrlDecoder().decode(parts[2]);

            return MessageDigest.isEqual(expected, received);
        } catch (IllegalArgumentException ex) {
            return false;
        }
    }

    public static void main(String[] args) throws Exception {
        long expiresAt = Instant.now()
                .plusSeconds(60)
                .getEpochSecond();

        String claims =
            "{\"iss\":\"https://issuer.example\"," +
            "\"sub\":\"alice\"," +
            "\"aud\":\"reports-api\"," +
            "\"exp\":" + expiresAt + "}";

        String signingInput = encode(HEADER) + "." + encode(claims);
        String token = signingInput + "." +
                encodeBytes(sign(signingInput));

        String[] parts = token.split("\\.", -1);

        // Decoding only proves that the payload is readable.
        boolean payloadReadable = decode(parts[1])
                .contains("\"sub\":\"alice\"");

        // Change subject while keeping the old signature.
        String changedClaims = claims.replace(
                "\"sub\":\"alice\"", "\"sub\":\"admin\"");
        String modifiedToken = parts[0] + "." +
                encode(changedClaims) + "." + parts[2];

        System.out.println("segments=" + parts.length);
        System.out.println("payloadReadable=" + payloadReadable);
        System.out.println("signatureValid=" +
                hasValidSignature(token));
        System.out.println("modifiedSignatureValid=" +
                hasValidSignature(modifiedToken));
    }
}
~~~

Compile and run:

~~~bash
javac JwtFormatLab.java
java JwtFormatLab
~~~

**Exact expected stdout**:

~~~text
segments=3
payloadReadable=true
signatureValid=true
modifiedSignatureValid=false
~~~

Because `exp` is generated from the runtime clock, the compact token differs across runs, though the program does not print the token to stdout. The signature is checked using **`MessageDigest.isEqual`** to avoid ad-hoc byte comparison; JCA `Mac` computes HMAC SHA-256 with the lab secret.

### 4.2. Security Limitations of the Lab

**Especially important:** The **`hasValidSignature`** method only demonstrates an **HMAC check over the exact signing input** using the lab key. It **does not** check:
- Whether user authentication was actually performed.
- Whether the issuer is on a trusted list.
- Whether the audience matches the receiving API.
- Whether the token is expired, not yet active, revoked, or used for the wrong purpose.
- Granted permissions, data ownership, session, or MFA.
- Key rotation, per-issuer algorithms, nested JWTs, or all real-world JOSE variants.

A token with a valid signature **can still be rejected** if `exp` has passed, `aud` is wrong, or the issuer is not accepted. Therefore, **do not copy the custom JWT handling code above into production APIs**. Use Nimbus through Spring Security or a maintained library configured with an algorithm allowlist and appropriate validation profile.

**Lab conclusion:** A readable payload does not prove a token is valid; a valid signature proves integrity under the chosen key, yet **still does not constitute an entire login/authorization protocol**.

## 5. Where Do OAuth 2.0 and OpenID Connect Use JWT?

### 5.1. OAuth 2.0 Is an Authorization Framework

OAuth 2.0 defines key roles:

| Role | Real-World Responsibility |
| --- | --- |
| **Resource Owner** | Entity authorized to delegate access to a resource |
| **Client** | Application wanting to access resources |
| **Authorization Server** | System that authenticates/authorizes and issues tokens per grant |
| **Resource Server** | API holding resources, validating access tokens and enforcing permissions |

An OAuth 2.0 flow defines how a client is authorized to obtain an access token, the exchange steps with the authorization server, and how the token is used with APIs. **OAuth 2.0 does not require access tokens to be JWTs.** A server may issue opaque tokens with no meaningful structure to the client; the resource server uses introspection with the token-issuing system.

OAuth 2.0 is also not always "user login". The **Client Credentials Grant** can serve service-to-service communication without involving a user logging in via a browser UI.

### 5.2. OpenID Connect Adds a User Identity Layer

**OpenID Connect (OIDC)** builds on OAuth 2.0 to support **end-user identity authentication** for clients. It defines the **ID token**, identity claims, discovery, verification rules, and other protocol behaviors.

In a typical OIDC Authorization Code flow:

~~~text
Browser / User        Application Client          Identity Provider / AS
     |                        |                              |
     | Open application       |                              |
     |----------------------->|                              |
     |                        | Redirect to authorization    |
     |<-----------------------|                              |
     |------------------------------------------------------>|
     |                        |   Login / MFA / consent      |
     |<------------------------------------------------------|
     |                        |  Redirect to callback + code |
     |----------------------->|                              |
     |                        | POST token endpoint + code   |
     |                        | + PKCE verifier              |
     |                        |----------------------------->|
     |                        |<-----------------------------|
     |                        | ID token and/or access token |
     |                        | per standard response        |
     |                        |                              |
     |                        | Validate ID token, bind login|
     |<-----------------------|                              |
     | App grants UI access   |                              |
~~~

The diagram intentionally summarizes the steps. Real implementations also require `state`, `nonce` where applicable, redirect URI matching, PKCE S256, client authentication when appropriate, token endpoint security, cookies/sessions, and secure client credential storage. **JWT is merely a data structure appearing in certain steps of the flow; it does not replace the flow.**

**Authorization Code + PKCE** is the common and recommended choice for applicable clients. RFC 9700 provides updated best practices on PKCE, redirect URIs, refresh tokens, sender-constrained tokens, and insecure flows to avoid.

### 5.3. Three Token Types Must Not Be Mixed Up

| Token | Purpose | Typical Receiver/Verifier | Must It Be a JWT? |
| --- | --- | --- | --- |
| **ID token** | Information about the end-user authentication event for the OIDC client | OIDC Client / Relying Party | **Yes**, per OIDC Core an ID token is a JWT |
| **Access token** | Credential for calling APIs/resource servers within granted scopes/permissions | Resource Server | **No**, can be JWT or opaque |
| **Refresh token** | Requests a new access token without repeating the full grant flow | Authorization Server / token endpoint | **No**, typically handled as an opaque credential with its own lifecycle |

**Do not use an ID token as a Bearer access token to call APIs** unless the API is explicitly and properly designed for that token type. An ID token typically has the **client application** as its audience, not a resource server API; accepting it at an API causes **token substitution / cross-JWT confusion**.

Similarly, do not send a refresh token to a resource server to call an API. Refresh tokens are used per protocol with the authorization server and typically have strict storage, binding, and rotation/revocation requirements.

### 5.4. A JWT Access Token Is Not an ID Token

Having claims `sub`, `iss`, `aud`, and `exp` is not enough to identify a token's type. You must check the **issuer profile, issued token type, audience, and validation requirements**. There are dedicated standards for JWT access token profiles; two JWTs from the same issuer can have completely different purposes.

Receivers need **mutually exclusive validation** rules when the system supports multiple JWT types. Do not allow a token issued for client login to slip into an admin API just because its signature is valid and both have `sub`.

## 6. Resource Server Receiving a JWT: From Byte String to Authentication

This is where JWT appears clearly in Spring Security:

~~~text
HTTP request: Authorization: Bearer <access-token>
                             |
                             v
                   BearerTokenAuthenticationFilter
                             |
                             v
                     JwtAuthenticationProvider
                             |
                             v
                          JwtDecoder
                             |
                +------------+--------------+
                |                           |
        Valid signature/key/alg?     Valid iss, exp, nbf, aud,
                |                    and token profile?
                +------------+--------------+
                             |
                       Token accepted
                             |
                             v
                  JwtAuthenticationConverter
                             |
                  Principal + GrantedAuthority
                             |
                             v
                   SecurityContext / authorization
                             |
            +----------------+----------------+
            |                                 |
        Allow API                        HTTP 401/403
~~~

**Explanation:**

1. Spring Security extracts the Bearer token from the `Authorization` header per Resource Server configuration.
2. **`JwtDecoder`** validates the token using keys/issuer/validators; without proof of validity, the payload is not treated as a trusted identity.
3. Upon successful authentication, Spring Security builds an **`Authentication`**. With default settings, the principal is typically a **`Jwt`**, and the Authentication name is usually derived from the `sub` claim.
4. Scopes in the common **`scope`/`scp`** claim are mapped to **`GrantedAuthority`** with the prefix **`SCOPE_`**; for example `reports.read` → `SCOPE_reports.read`.
5. **`SecurityFilterChain` / `AuthorizationManager`** decides whether the endpoint is permitted.

If the token is valid but lacks **`SCOPE_reports.read`**, an authenticated request can still receive **403 Forbidden**. If the token has an invalid signature, wrong issuer, is expired, or no Bearer token is provided on an authentication-required endpoint, the result is typically **401 Unauthorized** with an appropriate `WWW-Authenticate` header.

**A Resource Server is not an Authorization Server.** The fact that Spring Security can validate JWTs **does not mean it provides a login API, account registration, MFA, OAuth authorization endpoint, token issuance, or refresh tokens**.

## 7. Spring Boot 3.x: Configuring a Resource Server to Validate JWTs Against the Right Issuer

This section creates a Spring Boot Servlet application that genuinely accepts **JWT access tokens from an existing issuer** and authorizes by scope. It is a **resource server sample**, not a token-issuing system; you need to connect it to a **valid Authorization Server/Identity Provider in your environment** to test requests with tokens.

### 7.1. Project Setup

Use Spring Initializr:
- Java **17+**, Spring Boot **3.x**, Gradle.
- Group **`com.example`**, package **`com.example.demo`**.
- Dependencies: **Spring Web** and **OAuth2 Resource Server** (`spring-boot-starter-web`, `spring-boot-starter-oauth2-resource-server`).

Spring Boot's resource server starter pulls in the required integrations to verify JWT/JWS per supported configuration. Do not manually write an `AuthenticationFilter` that accepts any three-part string and marks it authenticated.

### 7.2. Complete Java Backend for the Resource Server

Create file **src/main/java/com/example/demo/JwtResourceServerApplication.java**:

~~~java
package com.example.demo;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class JwtResourceServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(JwtResourceServerApplication.class, args);
    }
}

@Configuration
class ResourceServerSecurityConfiguration {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                    .requestMatchers(HttpMethod.GET, "/api/public")
                        .permitAll()
                    .requestMatchers(HttpMethod.GET, "/api/me")
                        .authenticated()
                    .requestMatchers(HttpMethod.GET, "/api/reports")
                        .hasAuthority("SCOPE_reports.read")
                    .anyRequest().denyAll())
                .oauth2ResourceServer(oauth ->
                    oauth.jwt(Customizer.withDefaults()))
                .build();
    }
}

@RestController
class ApiController {

    @GetMapping("/api/public")
    String publicInfo() {
        return "public";
    }

    @GetMapping("/api/me")
    Map<String, String> currentUser(Authentication authentication) {
        return Map.of("subject", authentication.getName());
    }

    @GetMapping("/api/reports")
    String reports() {
        return "reports-ok";
    }
}
~~~

**This Java code has valid class structure**: only `JwtResourceServerApplication` is a `public class` matching the filename; the remaining classes in the same package are scanned by Spring. It builds a Spring Security filter chain and three GET endpoints; no `HttpSession` needs to be created to authenticate Bearer tokens in a typical resource server model.

### 7.3. Configuring Issuer and Audience

Create file **src/main/resources/application.yml**:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org/realms/training
          audiences: reports-api
~~~

**`https://idp.example.org/realms/training` is a hypothetical issuer solely to illustrate configuration.** To test real tokens, replace it with the exact issuer URL published by your Identity Provider; the IdP must expose metadata/JWK Set so Spring Security can locate the matching public key, and real tokens must carry the corresponding **`iss`** claim. The **`audiences`** property enforces checking the `aud` claim; in this example, tokens issued for another API are not accepted at `reports-api`.

Per Spring Security 6.5, minimal configuration via `issuer-uri` can use issuer discovery to find the JWK Set, verify signatures, **`iss`**, **`exp`**, and **`nbf`**, and map scopes to **`SCOPE_...`**. Audience is an additional constraint to configure per API; Spring Boot supports the **`audiences`** property as shown above.

**Do not arbitrarily fetch JWK URLs from an untrusted token's header.** The list of valid issuers, key sources, and algorithms must originate from trusted configuration. If supporting multiple issuers, design multi-tenant/multi-issuer handling with explicit trust boundaries rather than decoding the `iss` claim and blindly trusting it.

### 7.4. Running and Testing

In the Gradle directory:

~~~bash
./gradlew bootRun
~~~

On Windows use **`gradlew.bat bootRun`**. When running with the hypothetical issuer above, **there is no real token to authenticate with**. To test `/api/me` and `/api/reports` returning 200, you need a real IdP with the matching issuer, audience, and scope. Do not forge a token signed with a lab secret and expect a resource server using the IdP's public key to accept it.

Test commands:

~~~bash
# Public endpoint:
curl -i http://localhost:8080/api/public

# Protected endpoint, without token:
curl -i http://localhost:8080/api/me

# Once you have a valid access token from the configured IdP:
curl -i -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:8080/api/me

# Token also needs scope reports.read:
curl -i -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:8080/api/reports
~~~

Table of **policy-expected results**, not actual execution logs:

| Request / Token | Typical Status | Explanation |
| --- | --- | --- |
| GET /api/public, no token | **200** | `permitAll`, body `public` |
| GET /api/me, no token | **401** | Authentication required |
| GET /api/me, invalid signature token | **401** | `JwtDecoder` rejects token |
| GET /api/me, expired token (`exp` passed) | **401** | Token no longer valid |
| GET /api/me, wrong `iss`/`aud` token | **401** | Wrong trusted source/target |
| GET /api/me, valid access token | **200** | `Authentication` created from token |
| GET /api/reports, valid token without `reports.read` scope | **403** | Missing `SCOPE_reports.read` |
| GET /api/reports, valid token with `reports.read` scope | **200** | Body `reports-ok` |
| GET unpermitted endpoint | **403** if request is authenticated and matches `denyAll` | Final rule denies |

Actual status codes and error headers depend on Spring Security and configured filters/entry points. In particular, for an unauthenticated request hitting `denyAll`, the result may be **401**, not always 403. The API above only has GET; if adding POST/PUT/DELETE, design authorization and evaluate CSRF based on how clients send credentials rather than disabling CSRF globally out of habit.

**There is no `POST /login` in the example.** Spring Resource Server only verifies JWTs already issued by another party. To provide OIDC login, the client application must configure OAuth2 Client/OIDC, and the token issuer needs a suitable Authorization Server.

### 7.5. Permissions from Scope and Role Are Not Automatically Identical

A claim such as:

~~~json
{"scope": "reports.read reports.write"}
~~~

is mapped by the default converter rules into **`SCOPE_reports.read`**, **`SCOPE_reports.write`**. It **does not automatically create `ROLE_ADMIN`**. Conversely, a JWT from a provider with a custom `roles` claim may not automatically convert into Spring `GrantedAuthority` values.

For example:
- **`hasAuthority("SCOPE_reports.read")`** checks the scope above.
- **`hasRole("ADMIN")`** typically checks for `GrantedAuthority` **`ROLE_ADMIN`**.
- **`hasAuthority("reports.read")`** will not match **`SCOPE_reports.read`** unless a different converter is configured.

When custom claims must be mapped, write a tested **`JwtAuthenticationConverter` / `JwtGrantedAuthoritiesConverter`**, clearly specify the issuer profile, and map only trusted granted permissions. Never take a role list submitted by the client in request JSON to build authorities.

## 8. Issuing Tokens and Verifying Tokens Are Two Distinct Responsibilities

### 8.1. What Does an Authorization Server Need Beyond JWT?

For a system to genuinely provide login or protocol-based authorization, many components must be designed that the JWT structure does not cover:

- **Initial authentication method**: username/password with `PasswordEncoder`, passkeys, MFA, federation, or client authentication.
- **Client registration**: `client_id`, redirect URIs, public/confidential client type, allowed scopes, client authentication.
- **Grant flow**: authorization code, PKCE, consent, `state`/`nonce` when applicable.
- **Token endpoint**: issuing access tokens, refresh tokens, and ID tokens per profile; not all types are always issued.
- **Signing keys / JWK**: key generation, secure secret/private key storage, publishing public keys, key rotation, and key revocation.
- **Claims definition**: issuer/audience/subject, scopes and permissions, expiration, token type, version.
- **Token validation**: resource server checks key/alg, issuer/audience, timestamps, intended usage, permissions.
- **Lifecycle and revocation**: revoke, refresh token rotation, logout, expiration, password/permission changes.
- **Attacks and monitoring**: brute force, token replay, redirect attacks, token leakage, auditing, and rate limiting.

Rather than building all of this in a `@RestController` returning self-signed JWTs, applications can integrate an existing **OpenID Provider/Authorization Server** or use Spring Authorization Server under a complete security design. Spring Security Resource Server **does not** take on the issuance responsibilities above.

### 8.2. Authenticate Once, Authorize Many Times

An OIDC login may finish with a client session cookie to maintain the user interface. Meanwhile, APIs can require a separate Bearer access token. Both mechanisms **can coexist**:

~~~text
User logs in at Identity Provider
        |
        v
OIDC client authenticates successfully
        |
        +--> Web app creates session for browser
        |
        +--> OAuth client holds access token to call API
                 |
                 v
           Resource Server checks Bearer token
~~~

Seeing a browser with a session cookie does not tell you whether the API uses JWT or opaque tokens. Seeing an API accept JWTs also does not prove the browser uses JWT as its login session.

## 9. Mandatory JWT Verification Steps to Think Through

You should never design a **`decodeJwt()`** function that reads claims and returns `UserDetails` without complete verification steps.

### 9.1. Algorithm, Key, and Issuer Allowlist

- Allow **specific algorithms** via configuration; never pick a different algorithm merely because the token's **`alg`** field requests it.
- With **HS256**, the signer and verifier share the same secret; anyone with the secret can forge signatures. If multiple services hold the secret, the trust boundary widens.
- With **RS256/ES256**, the issuer typically holds the private key to sign; the resource server receives the public key to verify. The resource server does not need to hold the private signing key.
- Fetch keys only from a **configured trusted issuer/JWK Set URI**; resolve `kid` against that issuer's key set.
- Design key rotation, caching/JWKS refresh, and a plan to retire old keys; never embed keys/secrets directly in production source code.

### 9.2. Checking Claims by Resource and Token Type

| Step | What Can Happen If Skipped |
| --- | --- |
| Verify signature/MAC and valid algorithm | Attacker alters payload to admin permissions or spoofs issuer |
| Check **`iss`** | Accepts tokens issued by another party |
| Check **`aud`** | Uses token issued for a different API/client to access the wrong resource |
| Check **`exp`/`nbf`** | Expired or not-yet-active tokens still work |
| Check token type / profile | Misuses an ID token, refresh token, or another JWT type as an access token |
| Check scope/authority | Cryptographically valid token without sufficient permissions still reads/modifies data |
| Check resource ownership/tenant | Valid scope, yet user views another user's resources |
| Control replay/revocation when needed | Stolen token can be reused until expiration |
| Verify issuer/key trust boundary | Token from an unauthorized party gains trusted privileges |

**A valid signature is only a necessary condition in many cases, not sufficient for authorization to succeed.**

### 9.3. Key Confusion, Algorithm Confusion, and Cross-JWT Confusion

RFC 8725 highlights serious failure modes:
- **Algorithm confusion**: accepting an unintended algorithm or using the wrong key type.
- **Cross-JWT confusion**: accepting a JWT issued for a different purpose, such as an ID token at an API expecting an access token.
- **Weak key/secret management**: using guessable secrets, sharing them too broadly, or failing to rotate.
- **Not binding issuer/audience**: letting tokens from another context enter the resource server.
- **Looking up data from untrusted claims**: can lead to injection, SSRF, or cross-tenant resource access.

**`kid` is not a filesystem access command.** Never concatenate `kid` directly into a path to read a private key and never automatically fetch an arbitrary URL specified by a token. Only select keys from a registered trusted key set.

### 9.4. JWT Does Not Protect Itself Against Theft/Replay

A **Bearer** access token means anyone holding a valid token can present it within its scope, unless the token has a sender-binding mechanism. A valid signature does not stop someone else from using a stolen copy. Commonly considered countermeasures:
- Enforce **HTTPS**; never put tokens in URLs, browser history, or logs.
- Short-lived access tokens per threat model; managed signing key rotation.
- Protect tokens on the client; avoid exposing secrets to JavaScript when unnecessary.
- Sender-constrained access tokens such as **DPoP/mTLS** when high security is required.
- For public client refresh tokens, use **sender-constraining or refresh token rotation** per RFC 9700.
- Design permission/session revocation on password change, lost device, account lock, or breach detection.

If a JWT is self-verified and unexpired, "UI logout" alone does not guarantee the API immediately rejects copies of the token. Design TTLs and/or appropriate revocation/session/version checks.

## 10. Session, CSRF, CORS, and Cookies Still Matter Even with JWT

Several common false conclusions:

**False:** "Using JWT means no CSRF is needed."  
**True:** CSRF depends on how the browser automatically sends credentials. If a JWT is stored in a cookie and the browser attaches the cookie automatically to requests, CSRF must be evaluated just like a cookie-authentication system. If a bearer token is explicitly added by the client into the `Authorization` header, the threat model differs, though XSS/token theft defenses are still required.

**False:** "Using JWT means there are no sessions anywhere in the system."  
**True:** A resource server can authenticate JWTs per-request without using `HttpSession` to store `Authentication`, yet the browser client, Identity Provider, and Authorization Server can still use sessions; refresh tokens may also be tied to a server-side grant or session.

**False:** "Allowing CORS makes the API secure."  
**True:** CORS is a browser mechanism controlling cross-origin sharing; the server must still authenticate tokens and check permissions. Non-browser clients are not bound by browser CORS rules.

**False:** "The payload only has `sub` and `role`, so re-signing and sending it logs you in."  
**True:** A token is accepted only if the signature is created with a trusted issuer's key, uses an allowed algorithm, and satisfies `iss`/`aud`/type/time/permission conditions. Clients have no right to propose roles and force the server to trust them.

### Frontend Token Storage Locations

- **Memory:** limits certain long-term storage risks, though refreshes or page reloads require a strategy to re-obtain the token.
- **LocalStorage/SessionStorage:** accessible to same-origin JavaScript, making XSS a particularly critical risk.
- **HttpOnly cookie:** JavaScript cannot read the cookie directly if `HttpOnly` is set; however, cookies are sent automatically, requiring `SameSite`/`Secure`/CSRF policies and an understanding of browser sessions.
- **Backend-for-Frontend (BFF):** keeps tokens on the backend and uses a session cookie for the browser; reduces exposing access tokens to JavaScript, though session/cookie and CSRF protections are still required.

There is no single storage choice that is universally safe for every application; evaluate client type, origin architecture, CSRF, XSS, and revocability.

## 11. Testing JWTs and Protocols Must Separate Two Layers

### 11.1. Testing the Resource Server

Build a minimum test matrix:

| Input | Expected Outcome to Verify |
| --- | --- |
| Call protected endpoint without Bearer token | 401 |
| Malformed token / invalid signature / invalid algorithm | 401 |
| Unknown issuer token | 401 |
| Token audience is not this API | 401 |
| Expired or not-yet-valid token | 401 |
| Valid token missing required scope | 403 |
| Valid token with scope and matching resource policy | 200 |
| Token with scope belonging to another tenant | Denied per data policy |
| ID token sent in place of access token | Denied per validation profile |
| Revoked token / locked credential | Denied if system requires immediate revocation |
| Unusual `alg` or `kid` header | Must not select keys/algorithms without control |

### 11.2. Distinguishing Mock JWT Tests from Cryptographic Tests

In Spring Security Test, the **`jwt()`** helper can construct an `Authentication` for MockMvc to test authorization rules without **performing full cryptographic validation of a JWT**. This test example is an illustrative fragment inside a `@SpringBootTest` / `@AutoConfigureMockMvc` test, requiring the `spring-security-test` dependency:

~~~java
mvc.perform(get("/api/reports")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_reports.read"))))
    .andExpect(status().isOk());

mvc.perform(get("/api/reports")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_profile"))))
    .andExpect(status().isForbidden());
~~~

Static imports in the test: **`MockMvcRequestBuilders.get`**, **`MockMvcResultMatchers.status`**, **`SecurityMockMvcRequestPostProcessors.jwt`**; the `GrantedAuthority` implementation can use **`SimpleGrantedAuthority`**. This is **not** a standalone test class to run with `javac`.

**The two tests above prove how endpoints evaluate authorities when the context already has a JWT `Authentication`**, but they do not prove `JwtDecoder` rejects invalid signatures, wrong `aud`, or fake issuers. To verify the real system, write integration tests using **real/signed fixture tokens** and a **configured `JwtDecoder`**, or a controlled test issuer/JWKS environment. Never claim security is complete solely because all MockMvc tests using `jwt()` pass.

### 11.3. Testing OIDC Client Login Differs from Testing APIs

For an OIDC client, verify:
- Correct Authorization Code flow and PKCE, preventing code injection.
- `state`/`nonce` when needed, redirect URI matching, and client authentication.
- ID token validation for issuer/audience/nonce per profile.
- Not using the ID token as an API Bearer access token.
- Login session/cookies, logout, refresh, and provider errors.
- Tokens not leaked in URLs/logs or reused outside their intended purpose.

An API resource server does not prove OIDC client login works; conversely, successful login does not prove the API validates access tokens properly.

## 12. Diagnosing Common Misconceptions

| Symptom / Claim | Root Cause | Resolution |
| --- | --- | --- |
| "A three-part token must be valid" | Checking format only, not verifying signature and claims | Use full `JwtDecoder`/validators |
| "Base64 decode shows role ADMIN so grant access" | Trusting unverified payload | Verify signature, issuer, audience, token type, and authority |
| "JWT is OAuth" | Confusing token format with authorization framework | Separate token serialization from grant/authorization |
| "OAuth 2.0 always returns JWTs" | OAuth does not mandate access token encoding | Support JWT or opaque per issuer |
| "Got an ID token so use it to call APIs" | Wrong audience/token purpose | APIs accept only access tokens per profile |
| "JWT is encryption" | Standard JWS is only Base64url + signature | Do not store secrets in payload; use JWE when needed |
| "Valid signature means every API must accept it" | Missing issuer/`aud` and scope constraints | Check resource-specific claims/policy |
| "Bearer tokens protect themselves from replay" | Token is a copyable credential | TLS, TTL, secure storage, DPoP/mTLS when appropriate |
| "Spring Resource Server provides login endpoints automatically" | Only configured to validate incoming tokens | Use appropriate OAuth/OIDC client and Authorization Server |
| "Disabling CSRF is mandatory with JWT" | Confusing token format with browser credential transport | Evaluate CSRF based on how browsers send credentials |
| "`JwtDecoder` automatically understands custom `roles` claims" | Default converter focuses on `scope`/`scp` | Configure a tested `JwtAuthenticationConverter` |
| "Token without `JSESSIONID` lacks a `SecurityContext`" | Per-request `SecurityContext` still exists | Understand stateless per-request authentication |
| "Logout immediately removes JWT from the server" | Self-contained JWTs may remain valid | TTL, revocation/introspection/token version per requirements |
| "`kid` can point to any key URL" | Trusting unverified token headers | Select keys only from trusted JWKS/issuer |
| "MockMvc `jwt()` tests signatures" | Helper usually mocks `Authentication` | Add decoder/issuer/JWKS integration tests |

### How to Debug in Spring Security

1. Check whether the request has a proper **`Authorization: Bearer`** header and a token intended for this API.
2. Check `issuer-uri`/JWK Set URI, key rotation, and algorithm whitelist.
3. Check **`iss`, `aud`, `exp`, `nbf`**, and token profile/type.
4. Once the token is valid, inspect **`Authentication.getAuthorities()`**, scope mapping, and request matchers.
5. Distinguish **401** (unauthenticated) from **403** (authenticated but lacking permissions or blocked by another layer).
6. Review session/cookies if the browser also uses an OIDC login or BFF step.
7. Never log raw JWTs, refresh tokens, `Authorization` headers, or private signing keys.

Use `DEBUG` level in development if needed, but configure logging to avoid collecting credentials.

## 13. Real-World Scenario: Reports Management API

Suppose the application consists of:

~~~text
Browser (OIDC Client)
        |
        | Authorization Code + PKCE
        v
Identity Provider / Authorization Server
        |
        | issues JWT access token with:
        | iss = trusted issuer
        | aud = reports-api
        | scope = reports.read
        v
Backend (Spring Security Resource Server)
        |
        | JwtDecoder verifies token
        | JwtAuthenticationConverter creates SCOPE_reports.read
        v
GET /api/reports -> allowed if policy matches
~~~

Suppose an attacker edits the JWT payload from **`reports.read`** to **`reports.write`** without the private signing key. The signature will fail validation, and the request is rejected. If the attacker substitutes another validly signed JWT with **`aud = billing-api`**, the reports API must also reject it due to the wrong audience. If a user has the `reports.read` scope yet requests someone else's report, the application must still check **ownership/tenant**.

Security comes from the **chain of trust decisions and controls**, not from the two dots in a JWT.

### When Should Opaque Tokens Be Used?

Opaque tokens are suitable when the Resource Server needs to check status and permissions at a central system via **introspection** or when you do not want to expose claim contents to the client. They should not automatically be considered better or worse than JWTs in all circumstances: factor in latency, availability, revocation, caching, trust boundaries, and system scale.

Spring Security supports **OAuth2 Resource Server Opaque Token** alongside JWT. Choosing JWT or opaque is a **token representation/validation choice**, independent of which OAuth/OIDC flow the application uses to grant access.

## 14. Self-Assessment Questions

1. What **format** does JWT describe, and why does it not by itself define a login endpoint?
2. Why can a client read a JWS payload without the private key?
3. How many parts does a typical compact JWS have? How many parts does a compact JWE have? What properties do they protect?
4. Should a JWT with a valid signature whose **`aud`** is another API be accepted? Why?
5. Does OAuth 2.0 require access tokens to be JWTs? Does Client Credentials require a user login?
6. What does OIDC add on top of OAuth 2.0? What purpose does the ID token serve?
7. Why should you not send an **ID token** to call an API that requires an **access token**?
8. Distinguish **`iss`**, **`sub`**, **`aud`**, **`exp`**, and **`scope`**.
9. In Spring Security, how do **`JwtDecoder`** and **`JwtAuthenticationConverter`** differ in responsibility?
10. What default authority does a token with scope `reports.read` map to? Does **`hasRole("ADMIN")`** match automatically?
11. Why is MockMvc using the **`jwt()`** helper insufficient to prove the decoder verifies signatures properly?
12. Does logout immediately invalidate all unexpired JWTs? What strategies are needed if immediate revocation is required?
13. Does storing a JWT in an `HttpOnly` cookie automatically eliminate CSRF risk? Explain based on how credentials are transmitted.
14. When are key rotation, revocation, and sender-constrained tokens needed?
15. If building OIDC login for an SPA, why can't JWT replace Authorization Code + PKCE, `state`, and related verification steps?

**Lesson takeaway:** **JWT = claims/token format.** **OAuth 2.0 = authorization framework.** **OIDC = identity/authentication layer built on OAuth 2.0.** **Spring Security Resource Server = component that receives and verifies access tokens to protect APIs**, not by default a token-issuing component. To build a proper login system, you must thoroughly design **authentication, token issuance, token validation, authorization, renewal, revocation, and credential protection**.

## Official References

- RFC 7519 — JSON Web Token (JWT): https://www.rfc-editor.org/rfc/rfc7519
- RFC 7515 — JSON Web Signature (JWS): https://www.rfc-editor.org/rfc/rfc7515
- RFC 7516 — JSON Web Encryption (JWE): https://www.rfc-editor.org/rfc/rfc7516
- RFC 8725 — JSON Web Token Best Current Practices: https://www.rfc-editor.org/rfc/rfc8725
- RFC 6749 — OAuth 2.0 Authorization Framework: https://www.rfc-editor.org/rfc/rfc6749
- RFC 9700 — Best Current Practice for OAuth 2.0 Security: https://www.rfc-editor.org/rfc/rfc9700
- OpenID Connect Core 1.0: https://openid.net/specs/openid-connect-core-1_0.html
- Spring Security 6.5 — OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html
- Spring Security 6.5 — OAuth2 Resource Server opaque tokens: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html
- Spring Security 6.5 — OAuth2 Login: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/core.html
