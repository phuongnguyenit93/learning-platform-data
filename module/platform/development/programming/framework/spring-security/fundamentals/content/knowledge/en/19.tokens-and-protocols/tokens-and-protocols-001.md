# What Is a Token and How Bearer Tokens Differ from Password Credentials

When users sign in to a web application, they can use a **password** to prove control over an account. After authentication, another system can issue an **access token**, and the client uses that token to call APIs without resending the password on every request. The common usage is the HTTP header `Authorization: Bearer <access-token>`.

This distinction is critical for Spring Security. A password authentication filter must check one kind of credential; an OAuth2 Resource Server filter must check a different kind of credential. A password does not automatically become a Bearer token just because it is placed after the word `Bearer`. Conversely, a Bearer token is still a dangerous secret if leaked: anyone holding a valid token can exercise the permissions that the token still grants.

This lesson belongs to the **Tokens and Protocols** group of **Spring Security - Fundamentals**. We will explore the definition of a token, HTTP Basic versus Bearer, OAuth2 access tokens, JWT/opaque tokens, scope/issuer/audience, how Spring Security verifies tokens, and security practices. Examples use Java 17+, Spring Boot 3.3.x, and Spring Security 6.3.x with Spring MVC/Servlet.

## 1. What Is a Token?

In security, a **token** is a value representing authentication information, a session, access rights, or an event/authorization according to the issuing system's protocol. Not all tokens are the same:

- A **Session ID** typically helps the server look up stored session state, for example after form login.
- An **OAuth2 access token** is sent by the client to a Resource Server to call protected resources.
- A **Refresh token** is used with an Authorization Server to request a new access token.
- An **OpenID Connect ID token** conveys information about user authentication to an OIDC client.
- A **CSRF token** is used to protect state-changing requests in certain browser applications.

The word "token" by itself **does not** prove that the token is a JWT, does not prove it can log a user in, and does not prove it is allowed to access any arbitrary API.

In OAuth2, three roles are commonly seen:

~~~text
User / Resource Owner
             |
             | authenticates/authorizes via appropriate flow
             v
Authorization Server (token-issuing system)
             |
             | access token
             v
Client (application)
             |
             | Authorization: Bearer <access-token>
             v
Resource Server (API)
             |
             | validates token + checks permissions
             v
Protected Resource
~~~

The actual flow depends on the OAuth2 grant. With `client_credentials`, an access token can represent an application/service rather than an end user. A system using tokens also does not implicitly have to use passwords; it may use passkeys, federated login, or another form of authentication.

## 2. Differences Between a Password and a Bearer Access Token

| Criterion | User Password | Bearer Access Token |
| --- | --- | --- |
| Role | A secret used to prove identity during an authentication process | A credential used to call an API within the granted scope of permissions |
| Where typically processed | Login system / Identity Provider | Resource Server authorized to accept the token |
| Who can create it? | User / identity system following password-setup procedures | Authorization Server or a trusted token issuer |
| Lifecycle | Usually exists until changed/reset or disabled | Usually has a limited lifetime and may have a revocation mechanism |
| Permission scope | The password itself does not describe API scopes | The token or lookup result can attach scope, audience, resource |
| If compromised | Attackers may attempt to use it to log in wherever passwords are still accepted | Attackers may use the token within its still-valid permissions |
| Change/revocation | Password change, account lock, handling related sessions | Expiration, revocation, introspection, key rotation, or other policies |
| Verification in Spring Security | `PasswordEncoder` in the appropriate password mechanism | `JwtDecoder` or `OpaqueTokenIntrospector` in the Resource Server |

**Both passwords and Bearer tokens must be protected.** A Bearer token is a credential under the model *whoever holds the token can use the permissions attached to it*, without a mandatory step to prove possession of a cryptographic key like a *proof-of-possession* token. If the token is stolen, the server does not automatically know whether the request came from the original device/owner.

### Do Tokens Completely Replace Passwords?

Not necessarily. An application can use a password when logging in at an IdP, yet use an access token when calling APIs. Other applications do not require traditional passwords at all. What matters is the **protocol and endpoint**: the login system accepts credentials for authentication; the Resource Server API accepts access tokens according to its own contract.

### Is It Necessary to Send Username/Password on Every API Call?

No, not for an API designed around access tokens: the client uses a Bearer token on requests accessing the API. With HTTP Basic, username/password can be presented again on every request; that is a separate mechanism and requires HTTPS. Do not invent a custom "send password on every request and self-issue tokens" solution when standard authentication components and protocols already exist.

## 3. Authorization: Basic and Authorization: Bearer

The HTTP `Authorization` header contains an **authentication scheme** along with the credential. The same header with different prefixes leads to different decoding/verification behavior.

~~~http
GET /api/profile HTTP/1.1
Host: api.example.test
Authorization: Basic bGFuOmRlbW8xMjM=
~~~

With HTTP Basic, the string above is typically the Base64 encoding of `username:password`, here `lan:demo123`. **Base64 is not security encryption.** Anyone reading the header can decode it to recover the username and password.

~~~http
GET /api/profile HTTP/1.1
Host: api.example.test
Authorization: Bearer example-access-token
~~~

With Bearer, the string after the word `Bearer` is a token issued by an appropriate system. It does not implicitly contain a username/password and cannot be treated as valid by a Resource Server merely because it has the Bearer prefix.

| Header | Interpretation |
| --- | --- |
| `Authorization: Basic <base64(user:password)>` | HTTP Basic credential, must be verified by the Basic handler |
| `Authorization: Bearer <token>` | Bearer token verified by the Resource Server handler |
| No Authorization header | The request carries no credential in this header; it may be anonymous or use session/another mechanism |
| `Authorization: Bearer demo123` where `demo123` is a password | Not a valid access token if the token issuer did not actually issue that string |
| `Authorization: Basic ...` to a Bearer-only API | Not automatically converted to Bearer and typically fails authentication |

### Standalone Java 17+ Example: Base64 Is Not Encryption

Save the file `Base64BasicDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public class Base64BasicDemo {
    public static void main(String[] args) {
        String demoCredentials = "lan:demo123";

        String encoded = Base64.getEncoder().encodeToString(
                demoCredentials.getBytes(StandardCharsets.UTF_8)
        );

        String decoded = new String(
                Base64.getDecoder().decode(encoded),
                StandardCharsets.UTF_8
        );

        System.out.println(encoded);
        System.out.println(decoded);
    }
}
~~~

Compile and run:

~~~bash
javac Base64BasicDemo.java
java Base64BasicDemo
~~~

Exact stdout of the sample program:

~~~text
bGFuOmRlbW8xMjM=
lan:demo123
~~~

This is a **dummy secret for learning**, not a real credential. Do not log credentials in production applications. The purpose of the example is to prove that Base64 is reversible, not to prove HTTP Basic is a safe way to store passwords. The protocol requires HTTPS and server-side password storage using a suitable hashing algorithm, such as BCrypt via `PasswordEncoder`.

## 4. "Bearer" Describes Usage, Not Token Format

According to RFC 6750, a Bearer token is used by presenting the token value to obtain access, **without requiring the presenter to prove possession of a corresponding cryptographic key**. Therefore, a leaked copy of a token can be replayed while it remains valid.

Three concepts that are often mixed up:

1. **Bearer**: a token usage model where whoever holds the token can use it according to its granted permissions.
2. **JWT**: a token format with a claims structure, usually digitally signed; not every JWT is an access token.
3. **Opaque token**: a token from which the Resource Server cannot derive trusted information simply by reading the string; it usually requires lookup/introspection.

A **signed JWT** can be sent as a Bearer token. An **opaque token** can also be sent as Bearer. In addition, there are key/device-bound token mechanisms (mTLS-bound, DPoP) designed to prevent replay by requiring additional proof of key possession; those are no longer pure Bearer tokens.

### Why Is HTTPS Still Necessary Even When a JWT Is Signed?

A JWT signature helps detect unauthorized tampering with the token; **the signature does not prevent an attacker from reusing the original token** if they have stolen it. TLS/HTTPS protects the transport channel; beyond TLS, you must also prevent leaks from logs, browser scripts, extensions, malware, and token storage locations.

## 5. Access Token, Refresh Token, and ID Token

| Token Type | Primary Consumer | Purpose |
| --- | --- | --- |
| **Access token** | Resource Server / API | Allows calling resources according to granted permissions/scopes |
| **Refresh token** | Authorization Server | Requests a new access token according to policy |
| **ID token** (OpenID Connect) | OIDC client | Contains information about the user authentication event |

**Do not send an ID token instead of an access token to call an API just because both are JWTs.** A JWT may have a valid signature and `sub`, yet be issued for a different audience/purpose. The Resource Server needs to verify that the token is intended for it and is permitted as a resource-access credential.

Refresh tokens are typically sensitive because they can be used to obtain new access tokens. They should not be placed in the Authorization header sent to ordinary resource APIs. An expired access token should also not be accepted just because the client holds a refresh token elsewhere; the client must go through a valid refresh flow.

### Is Using a Password to Obtain a Token the Standard Way for Every Application?

No. Modern flows such as **Authorization Code + PKCE** allow users to authenticate at the identity system without the client directly collecting the user's password. For service-to-service communication, `client_credentials` can be used. The Resource Owner Password Credentials flow, where the client collects a password and directly requests a token, is not recommended for new designs. Do not invent a custom password-to-token exchange protocol when an appropriate IdP and OAuth2/OIDC can be used.

## 6. How Are JWTs and Opaque Tokens Verified?

### 6.1. JWT

A compact JWS JWT typically has three parts:

~~~text
base64url(header).base64url(payload).base64url(signature)
~~~

Illustrative payload, **not an issued or signed token**:

~~~json
{
  "iss": "https://id.example.test/issuer",
  "sub": "lan",
  "aud": ["profile-api"],
  "scope": "profile.read",
  "iat": 1730000000,
  "exp": 1730003600
}
~~~

Meaning of common claims:

- `iss`: the issuing organization or server.
- `sub`: the subject the token refers to; not necessarily an end user by default.
- `aud`: the target system(s) the token was issued for.
- `exp`: expiration time.
- `nbf`: time before which the token must not be used.
- `iat`: time at which the token was issued.
- `scope`/`scp`: permission scopes, depending on how the Authorization Server represents them.

**Decoding a JWT into JSON does not mean the JWT is valid.** You must verify the signature with a trusted key/algorithm, and verify the claims and permissions. A standard digitally signed JWS JWT **does not encrypt the payload**: anyone holding the token string can usually read its contents after Base64URL decoding. Do not store secrets such as passwords, OTP codes, or API keys in a JWT payload.

### 6.2. Opaque Token

An opaque token can be a string without a public structure:

~~~text
T0k3n-opaque-random-example-12ab34
~~~

The Resource Server usually needs to call an **introspection endpoint** or a trusted service/store to learn whether the token is still active and what permissions it carries. Spring Security supports `OpaqueTokenIntrospector` for this approach.

| Criterion | Signed JWT | Opaque Token |
| --- | --- | --- |
| Typical shape | Structured payload and signature | String whose meaning is not directly inferable |
| Common verification | `JwtDecoder` verifies signature and claims | `OpaqueTokenIntrospector` performs lookup/introspection |
| Network call per request | May not be needed for signature verification if keys are already cached | May require introspection, depending on caching/infrastructure |
| Revocation before expiration | Requires a strategy beyond signature/`exp` if verified offline | Can be reflected via introspection according to policy |
| Can act as a Bearer token? | Yes | Yes |
| Must be kept secret? | Yes | Yes |

Neither type is automatically more secure solely by format. TTL, scope, audience, key strategy, verification infrastructure, and storage location determine much of the real-world risk.

## 7. Resource Server Token Authentication Differs from Password Mechanisms

Let's separate the two pipelines:

~~~text
PASSWORD LOGIN                         API CALL WITH BEARER
username/password                      Authorization: Bearer <access-token>
       |                                            |
       v                                            v
AuthenticationManager                   BearerTokenAuthenticationFilter
       |                                            |
Password-based AuthenticationProvider                v
       |                                JwtAuthenticationProvider
UserDetailsService + PasswordEncoder                 |
       |                                         JwtDecoder
       v                                            |
Authentication succeeded                            v
                                        JwtAuthenticationToken
                                                   |
                                                   v
                                           AuthorizationManager
                                                   |
                                           Check scope/permissions
~~~

With HTTP Basic or form login, the password provider typically loads account details and uses `PasswordEncoder` to match the password against the stored hash. A Resource Server API using Bearer tokens checks the token with `JwtDecoder` or introspection; it does not directly verify user passwords itself.

The steps Spring Security typically performs with a JWT Resource Server:

1. `BearerTokenAuthenticationFilter` extracts the token from the `Authorization` header.
2. The token is passed to the appropriate `AuthenticationManager` and `JwtAuthenticationProvider`.
3. `JwtDecoder` validates the token against the trust configuration, such as signature, expiration, and issuer.
4. `JwtAuthenticationConverter` maps claims such as `scope` into authorities, typically prefixed with `SCOPE_` by default.
5. `AuthorizationFilter` evaluates the path, HTTP method, authorities, and other policies.
6. The controller runs only if the request passes all required checks.

For example, a JWT carrying the scope `profile.read` typically produces the authority `SCOPE_profile.read`. The rule:

~~~java
.requestMatchers(HttpMethod.GET, "/api/profile")
    .hasAuthority("SCOPE_profile.read")
~~~

differs from the rule:

~~~java
.requestMatchers(HttpMethod.POST, "/api/profile")
    .hasAuthority("SCOPE_profile.write")
~~~

An authenticated token that only has the read scope is still not allowed to write. Even the same user having both read and write permissions is not automatically allowed to modify someone else's profile; resource-level authorization checks are required.

### A Valid Signature Is Not Enough

A JWT with a valid signature but an untrusted issuer, an expired timestamp, or an audience targeting a different API **should not be accepted**. Spring Security provides default checks on certain properties, but **do not assume audience is always validated merely because `issuer-uri` is configured**. Add an audience validator/configuration appropriate to your Spring Boot version and API requirements.

## 8. Spring Boot 3.3 Example: API Accepting Only Bearer JWT

The example consists of an application with `GET /api/profile` and `POST /api/profile`. The API uses Bearer tokens and does not enable HTTP Basic or form login. The Resource Server **only verifies tokens**; it does not issue access tokens or render a login page.

Structure:

~~~text
bearer-token-demo/
├── settings.gradle
├── build.gradle
├── src/main/resources/application.yml
├── src/main/java/example/bearer/
│   ├── BearerDemoApplication.java
│   ├── SecurityConfig.java
│   └── ProfileController.java
└── src/test/java/example/bearer/
    └── BearerSecurityTest.java
~~~

### 8.1. Gradle

File `settings.gradle`:

~~~groovy
rootProject.name = 'bearer-token-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot's OAuth2 Resource Server starter brings in properly managed dependencies for decoding and validating JWTs. Do not manually mix incompatible Spring Security versions into the project.

### 8.2. application.yml

File `src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/issuer
~~~

`https://id.example.test/issuer` is an **illustrative placeholder**, not a real IdP. In deployment, replace it with the issuer URI published by your token-issuing system with suitable metadata and a JWK endpoint. You cannot call the API successfully with a real JWT if the application cannot verify its signature with trusted keys.

### 8.3. BearerDemoApplication.java

~~~java
package example.bearer;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BearerDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(BearerDemoApplication.class, args);
    }
}
~~~

Save at `src/main/java/example/bearer/BearerDemoApplication.java`. Place the subsequent classes in the same package.

### 8.4. SecurityConfig.java

~~~java
package example.bearer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/profile")
                    .hasAuthority("SCOPE_profile.read")
                .requestMatchers(HttpMethod.POST, "/api/profile")
                    .hasAuthority("SCOPE_profile.write")
                .anyRequest().denyAll()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(csrf -> csrf.disable())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

Careful explanation:

- `oauth2ResourceServer(...jwt(...))` configures Spring Security to accept Bearer JWTs. It **does not issue tokens** and **does not extract passwords from the Authorization header**.
- `STATELESS` means HTTP sessions are not used to store the `SecurityContext` for API requests; the client presents the token on every request.
- `csrf.disable()` in this **pure Bearer-header API example without session cookies** is chosen because cross-site browser requests do not automatically include a Bearer token in the header. **Do not apply this line to applications with form login, session cookies, or credentials automatically sent by the browser** without evaluating CSRF risk.
- `hasAuthority("SCOPE_profile.read")` and `SCOPE_profile.write` distinguish read and write access.
- `anyRequest().denyAll()` denies every other request, even with a valid token.

### 8.5. ProfileController.java

~~~java
package example.bearer;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/profile")
public class ProfileController {

    @GetMapping
    public String read(Authentication auth) {
        return "profile:" + auth.getName();
    }

    @PostMapping
    public ResponseEntity<String> update() {
        return ResponseEntity.status(HttpStatus.ACCEPTED).body("updated");
    }
}
~~~

The controller is a sample and does not persist real data. With a JWT having claim `sub=lan` and the default converter, the authentication name is typically `lan`.

### 8.6. Calling the API

Once you have a real access token issued by your system's IdP:

~~~bash
curl -i -H "Authorization: Bearer ACCESS_TOKEN_FROM_IDP" \
  http://localhost:8080/api/profile
~~~

`ACCESS_TOKEN_FROM_IDP` is a placeholder, not a signed token. In production, do not paste tokens into chats, public documentation, shell history, or logs. The example only runs against a suitable IdP/key/token; the next testing section **mocks the decoder** so no real IdP is needed to test the filter path and authorization rules.

## 9. Testing HTTP Bearer and Scopes with MockMvc

File `src/test/java/example/bearer/BearerSecurityTest.java`. The example uses `@MockBean`, available in Spring Boot 3.3.x, to replace the real decoder with a mock decoder, allowing focus on testing `Authorization: Bearer` and authorization rules.

~~~java
package example.bearer;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BearerSecurityTest {

    @Autowired
    MockMvc mvc;

    @MockBean
    JwtDecoder decoder;

    private Jwt token(String value, String subject, String scope) {
        return Jwt.withTokenValue(value)
                .header("alg", "RS256")
                .claim("sub", subject)
                .claim("scope", scope)
                .build();
    }

    @BeforeEach
    void prepare() {
        when(decoder.decode("read-token"))
                .thenReturn(token("read-token", "lan", "profile.read"));
        when(decoder.decode("write-token"))
                .thenReturn(token("write-token", "lan", "profile.write"));
        when(decoder.decode("invalid-token"))
                .thenThrow(new BadJwtException("Invalid token"));
        when(decoder.decode("demo123"))
                .thenThrow(new BadJwtException("Password is not an access token"));
    }

    @Test
    void missingBearerReturns401() throws Exception {
        mvc.perform(get("/api/profile"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void readTokenCanRead() throws Exception {
        mvc.perform(get("/api/profile")
                .header(HttpHeaders.AUTHORIZATION, "Bearer read-token"))
                .andExpect(status().isOk())
                .andExpect(content().string("profile:lan"));
    }

    @Test
    void readTokenCannotWrite() throws Exception {
        mvc.perform(post("/api/profile")
                .header(HttpHeaders.AUTHORIZATION, "Bearer read-token"))
                .andExpect(status().isForbidden());
    }

    @Test
    void writeTokenCanWrite() throws Exception {
        mvc.perform(post("/api/profile")
                .header(HttpHeaders.AUTHORIZATION, "Bearer write-token"))
                .andExpect(status().isAccepted())
                .andExpect(content().string("updated"));
    }

    @Test
    void writeTokenCannotReadWithoutReadScope() throws Exception {
        mvc.perform(get("/api/profile")
                .header(HttpHeaders.AUTHORIZATION, "Bearer write-token"))
                .andExpect(status().isForbidden());
    }

    @Test
    void invalidTokenReturns401() throws Exception {
        mvc.perform(get("/api/profile")
                .header(HttpHeaders.AUTHORIZATION, "Bearer invalid-token"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void passwordAfterBearerKeywordIsNotAutomaticallyValid()
            throws Exception {
        mvc.perform(get("/api/profile")
                .header(HttpHeaders.AUTHORIZATION, "Bearer demo123"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void basicCredentialsDoNotAuthenticateWithBearerOnlyConfig()
            throws Exception {
        mvc.perform(get("/api/profile")
                .header(HttpHeaders.AUTHORIZATION,
                        "Basic bGFuOmRlbW8xMjM="))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void validTokenDoesNotPermitUnlistedPath() throws Exception {
        mvc.perform(get("/api/unknown")
                .header(HttpHeaders.AUTHORIZATION, "Bearer read-token"))
                .andExpect(status().isForbidden());
    }
}
~~~

Run:

~~~bash
./gradlew test --tests '*BearerSecurityTest'
~~~

On Windows:

~~~powershell
.\gradlew.bat test --tests "*BearerSecurityTest"
~~~

**Expected result:** 9 tests complete successfully given compatible dependencies and versions. This is an **expectation from the code**, not a record of an actual test run. Important limitation: `@MockBean JwtDecoder` does not verify real RS256 signatures, expiration, or issuer/audience. It stubs the decoder result to test filters and permissions. To test cryptography, add tests with genuinely signed JWTs, appropriate keys, and invalid signature/claims cases.

In newer Spring Boot versions, the replacement API for `@MockBean` may differ; check your actual dependencies before migrating the example.

## 10. A Valid Token Does Not Mean Authorized

Two steps must be separated:

1. **Authentication**: the token is accepted by the Resource Server and mapped to a valid `Authentication` object.
2. **Authorization**: the user/client/token has the authority, scope, and per-record permissions appropriate for the request.

| Request | Credential | Condition | Typical Result |
| --- | --- | --- | --- |
| GET /api/profile | No token | Login required | 401 |
| GET /api/profile | Wrong/expired token | Fails authentication | 401 |
| GET /api/profile | Token with `profile.read` | Has `SCOPE_profile.read` | 200 if controller succeeds |
| POST /api/profile | Token with `profile.read` | Missing `SCOPE_profile.write` | 403 |
| POST /api/profile | Token with `profile.write` | Has `SCOPE_profile.write` | 202 per sample Controller |
| GET /api/unknown | Valid `profile.read` token | `denyAll` | 403 |

Bearer responses may often include `WWW-Authenticate`:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

If the token is valid but lacks a scope, it can be 403 with `error="insufficient_scope"`. Specific headers depend on the Spring Security configuration, error type, and policy. Do not hardcode every event to a single HTTP status code.

When testing status codes, verify whether the request was blocked by the **authentication**, **authorization**, **CSRF**, **CORS**, or Controller layer. In the bearer-only example above, CSRF was intentionally disabled for the stateless API; cookie-based cases will differ.

## 11. Signing Keys, Issuer, Audience, exp, and Revocation

A valid JWT is not merely a decoded three-part string:

- **Signature** must be verified using a trusted key and allowed algorithm.
- **Issuer** (`iss`) must be an issuer the API trusts.
- **Audience** (`aud`) must match the API receiving the token; tokens intended for another service should not be accepted.
- **Timestamps** such as `exp` and `nbf` must be valid within the allowed clock skew.
- **Scope** must be converted into authorities appropriate for each endpoint.
- **Subject/resource** may require additional checks, such as which user owns a given order ID.
- **Key rotation and revocation** must follow organizational policy.

Changing a password **does not by default immediately invalidate all issued JWTs** if the Resource Server only checks signature/`exp` without looking up account state. To revoke before expiration, you need a strategy: short-lived tokens, blocklists, token versions, introspection, refresh token revocation, or an equivalent mechanism. A JWT does not automatically know the user just changed their password.

With opaque tokens, introspection can reflect revocation status from the Authorization Server; effectiveness still depends on caching and operations. Do not say "JWTs cannot be revoked" in an absolute sense; they **require additional design** if they must be invalidated before expiration.

## 12. Protecting Tokens in Real Systems

### 12.1. Always Use HTTPS and Protect Certificates

TLS protects the channel when transmitting passwords/Bearer tokens. Do not send Bearer tokens in URL query parameters such as:

~~~http
GET /api/profile?access_token=SECRET_TOKEN HTTP/1.1
~~~

URLs can appear in browser history, access logs, proxy logs, or Referrer headers. Prefer the `Authorization: Bearer` header over HTTPS. Avoid logging Authorization headers, cookies, refresh tokens, or passwords in logs or error-tracking tools.

### 12.2. Leaked Tokens Are Typically Replayable

Bearer tokens are not inherently bound to a browser/device. An attacker who obtains a token can call the API within its still-valid scope. Mitigate with short-lived tokens, narrow scopes, narrow audiences, secure transport channels, never exposing tokens, revocation controls, and anomaly detection.

### 12.3. Storing Tokens in the Browser

There is no "always right" solution for every application:

- Tokens in JavaScript memory usually disappear on page reload, but malicious code running in the same origin (XSS) can still access them.
- `localStorage`/`sessionStorage` carry risk when XSS or same-origin scripts have read access.
- `HttpOnly` cookies reduce JavaScript's ability to directly read the cookie, but browsers send cookies automatically, so CSRF and appropriate `SameSite`/`Secure` flags must be handled.
- The Backend for Frontend (BFF) pattern can keep access/refresh tokens server-side and use only an appropriate session cookie in the browser.

**Do not conclude that HttpOnly cookies eliminate all XSS/CSRF risks.** Base your decision on the authentication architecture and actual threat model.

### 12.4. Protecting Refresh Tokens and Logout

Refresh tokens can obtain new access tokens and therefore must be strictly protected. Clients should not send refresh tokens to a Resource Server as if they were access tokens. Logging out on the UI only removes the token from the client; whether the API continues accepting an unexpired access token depends on server-side revocation policy.

## 13. Common Mistakes to Avoid

1. **Confusing a Bearer token with an encrypted password.** A Bearer token is an issued credential, not a Base64-wrapped `password`.
2. **Confusing JWT with Bearer.** JWT is a format; Bearer is a usage model; an opaque token can also be Bearer.
3. **Believing Basic Base64 is encryption.** It is trivially decoded; HTTPS must be used.
4. **Only decoding a JWT and allowing the request.** You must verify the signature and claims.
5. **Only verifying the signature while ignoring audience.** The token may belong to a different API.
6. **Treating a valid token as having ADMIN permissions.** Scopes/authorities and resource permissions are still required.
7. **Using an ID token to call an API instead of an access token.** They serve two different purposes.
8. **Sending a refresh token to a resource API.** Refresh tokens belong to the token-issuing system per protocol contract.
9. **Changing a password and assuming all JWTs vanish.** A revocation policy is required.
10. **Putting tokens in query strings/logs/screenshots.** This creates replay risk for leaked tokens.
11. **Hardcoding tokens or passwords in source code.** Credentials must be managed as secrets.
12. **Disabling CSRF unconditionally.** Decide based on how the browser/client actually transmits credentials.
13. **Confusing a mock decoder test with cryptographic verification.** Mocks only test flow and authorization rules.
14. **Believing Bearer tokens are device-bound.** Pure Bearer tokens carry no proof of key possession.
15. **Assuming every token is a user token.** Client credentials can represent a service.
16. **Trusting claims from a token with the wrong issuer.** The API must enforce a clear trust policy.

## 14. Self-Check Questions

**1.** Is the HTTP header `Authorization: Basic bGFuOmRlbW8xMjM=` a Bearer token?

**Answer:** No. It is Base64-encoded HTTP Basic credentials corresponding to `lan:demo123`. Base64 does not protect the string if read.

**2.** An API is configured only for Bearer JWT, and a client sends `Authorization: Bearer demo123` where `demo123` is a password. Can it log in?

**Answer:** No, unless a system actually issued that exact string as a valid token under the contract; the Bearer prefix does not turn a password into an access token.

**3.** A JWT payload can be decoded without a key. Is the token valid yet?

**Answer:** Not yet. You must verify the signature, issuer, audience, timestamps, and permissions.

**4.** What happens when a token with scope `profile.read` calls `POST /api/profile` requiring `profile.write`?

**Answer:** It is rejected by policy for missing `SCOPE_profile.write`, typically returning 403 if the token was authenticated.

**5.** A token is validly signed by the IdP, but `aud` is intended for `billing-api`. How should `profile-api` handle it?

**Answer:** Do not accept it as an access token intended for itself; audience validation is required.

**6.** A user changes their password while a JWT still has 10 minutes of validity left. Is it automatically invalidated immediately?

**Answer:** Not by default. It depends on the revocation/state-checking mechanism.

**7.** Should `Authorization: Bearer ...` be written to logs for debugging?

**Answer:** Do not log raw credentials. Log only error types, request IDs, and safely designed metadata.

**8.** Does `@MockBean JwtDecoder` in a test prove that a real token's RS256 signature is checked?

**Answer:** No. It stubs the verification result to test filters/policies; signature and claim verification must be tested separately with a real decoder.

## 15. Spring Security Application Checklist

- Have you clearly separated **password login** endpoints from APIs that **accept access tokens**?
- Have you chosen the right HTTP scheme (Basic/Bearer or another mechanism) and determined which filter chain applies?
- Have you configured trusted issuer, keys, algorithms, `exp`, `nbf`, and audience for JWTs?
- Do you understand the `scope` to `SCOPE_...` mapping and endpoint-level permission checks?
- Do you check that resources belong to the appropriate user/organization in addition to scopes?
- Have you avoided using ID tokens/refresh tokens in the wrong places?
- Do you have policies for expiration, revocation, key rotation, refresh tokens, and password changes?
- Do you enforce HTTPS, avoid logging tokens in URLs/logs, and store tokens securely?
- If using browser cookies, have you evaluated CSRF/XSS and cookie flags?
- Have you tested missing/invalid tokens, missing scopes, wrong audience, invalid signatures, and expired tokens with a real decoder?
- Have you confirmed that `oauth2ResourceServer` only validates access tokens and does not itself issue tokens or perform password logins?

**Principle to remember:** A **password** is typically used to authenticate an account at a login system; a **Bearer access token** is a credential for accessing resources according to issued permissions. **JWT/opaque** are token formats; **Bearer** is how they are presented and used. Spring Security must authenticate tokens by issuer/key/time/audience, then verify scopes, authorities, and resource ownership for each request.

## Reference Documentation

- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://datatracker.ietf.org/doc/html/rfc6750): defines Bearer and protecting tokens in HTTP transport.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://datatracker.ietf.org/doc/html/rfc9700): recommendations on modern OAuth2 threats.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): `JwtDecoder`, issuer URI, and scope mapping.
- [Spring Security — OAuth2 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection.
- [Spring Security — Bearer Token Usage](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html): how Bearer tokens are extracted from requests.
- [Spring Security — HTTP Basic](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html): username/password and Basic authentication.
- [Spring Security — OAuth2 MockMvc Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): mock decoder and scope testing.
