# 10.6. Public Clients, the `none` Method, and Conditions for Use

> **Module:** Spring Security OAuth 2.0 OIDC Client  
> **Chapter:** 10. Token Endpoint  
> **Focus:** Distinguish public clients from confidential clients; understand `client-authentication-method: none` when exchanging an authorization code for tokens; combine PKCE, Spring Security configuration, and Authorization Server policy for secure deployment.

When a Spring Security OAuth 2.0 Client calls the **Token Endpoint**, the Authorization Server needs to know which Client is requesting tokens and whether that Client must be authenticated. For server-side applications capable of keeping secrets, the Client is typically registered as a **confidential client** and authenticated via `client_secret_basic`, `client_secret_post`, or a stronger mechanism. However, not every type of application can keep a client secret.

A single-page application (SPA) running JavaScript in the browser, a native mobile app, or a desktop application distributed to user machines is typically a **public client**. Application code, network traffic, and values packaged with the app can all be inspected by users or attackers. Any "client secret" embedded in such code is therefore not genuinely secret and cannot be used to prove Client identity.

OAuth 2.0 allows the **`none`** Client authentication method: the Client presents no secret or authentication signature at the Token Endpoint. That **does not** mean the Token Endpoint accepts arbitrary requests. The Authorization Server must still identify the client ID, verify the authorization code, redirect URI, PKCE code verifier, and grant conditions; the Client must also handle OIDC security, sessions, and tokens appropriately for its architecture.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **public clients** from **confidential clients** based on their ability to protect the Client's own credentials.
2. Explain what `none` means at the Token Endpoint and which checks remain mandatory.
3. Configure `client-authentication-method: none` for a Spring Security OAuth 2.0 Client registration.
4. Analyze Authorization Code + **PKCE S256** when a public client exchanges a code for tokens.
5. Identify why `client_id` is still used even without a client secret.
6. Choose an appropriate architecture for SPAs, native apps, desktop apps, server-side Spring MVC, and Backend for Frontend (BFF).
7. Distinguish a public client's token request from a token request using `client_secret_basic` or other confidential methods.
8. Recognize the prerequisites the Authorization Server must support before using `none`.
9. Diagnose errors such as `invalid_client`, `invalid_grant`, PKCE mismatches, or invalid redirect URIs.
10. Avoid using `none` as a way to "turn off security" to work around client secret errors.

## 2. What Are Public Clients and Confidential Clients?

In OAuth 2.0, Client classification is based on **the ability to keep the credentials used to authenticate the Client itself confidential**.

| Classification | Characteristics | Typical Examples |
|---|---|---|
| **Confidential client** | Can store Client credentials out of reach of end users | Spring Boot application running on an organization-managed backend |
| **Public client** | Cannot guarantee confidentiality of Client credentials against end users or anyone able to inspect code running on the device | JavaScript SPA, native mobile app, desktop app distributed to users |

**Do not classify by programming language.** A system "written in Java" could be either a backend that protects secrets or a desktop application that cannot. Likewise, a website having JavaScript does not automatically turn its Spring Boot **backend** into a public client.

### 2.1. Side-by-Side Scenarios

**Scenario A — Spring Boot MVC on a server:** Browser sends requests to the backend; the backend holds the client secret in a secret manager and performs token exchange over a server-to-server connection. This is typically a **confidential client** architecture.

**Scenario B — SPA running entirely in the browser:** JavaScript receives the authorization code at the application's redirect URI and calls the Token Endpoint directly. All code and configuration values are shipped to the browser. This is typically a **public client**.

**Scenario C — Mobile app:** Installed on a phone and uses the system browser for login. Any secret bundled inside the APK/IPA can be extracted. This is typically a **public client**.

**Scenario D — BFF (Backend for Frontend):** The browser holds only a backend session cookie; the BFF performs the OAuth token exchange and stores tokens server-side. The BFF can be registered as a **confidential client** if it manages Client credentials securely.

A provider issuing a string labeled "secret" to a mobile app does not make it a confidential client if that string must be distributed to every user device.

### 2.2. Classification Is a Property of the Registration and Environment

A system can have multiple OAuth 2.0 Client registrations:

- `web-server` registered as confidential for the backend.
- `mobile-app` registered as public for the mobile app.
- `browser-spa` registered as public for the SPA.

They may share the same Authorization Server and the same users, but **must not default to sharing a client secret or the same Client authentication policy**. Each registration requires its own Client type, redirect URI, grant types, scopes, and safeguards.

## 3. What Does the `none` Method Mean?

Spring Security models the Client authentication method via `ClientAuthenticationMethod`. Common values include:

| Method | Who Performs Client Authentication | Typical Representation at Token Endpoint |
|---|---|---|
| `client_secret_basic` | Confidential client | HTTP Basic Authentication with client ID and client secret |
| `client_secret_post` | Confidential client | Sends client ID and client secret in the form body per spec/AS contract |
| `private_key_jwt` | Confidential client with a private key | Signs a JWT client assertion and sends it to the Token Endpoint |
| `client_secret_jwt` | Confidential client with a secret | Signs a JWT client assertion using a shared secret |
| `none` | Public client | **Presents no credentials to authenticate the Client**; still sends required Client/grant identifiers |

The term "none" specifically means **no client authentication at the Token Endpoint**. It does not mean:

- The Client does not need to be registered with the Authorization Server.
- The Client does not need a `client_id`.
- The Authorization Server skips checking the authorization code.
- The Client can skip PKCE.
- The user does not need to authenticate at the Authorization Server.
- The redirect URI can be arbitrary.
- The access token can be used for any API.
- The Resource Server skips validating tokens.

This is the difference between **client identification** and **client authentication**:

- `client_id` is a public identifier stating which registration the request refers to.
- Client authentication proves the sender possesses the Client's credentials; a public client using `none` **has no such secret proof**.
- PKCE binds the authorization code to the party that initiated the authorization request, yet **does not turn a public client into a confidential client**.

### 3.1. Client ID Is Not a Secret

In a SPA or mobile app, users can see `client_id` in code, configuration, or the authorization URL. That is normal: OAuth 2.0 does not treat client IDs as secret information.

Example:

```text
client_id=mobile-learning-app
client_authentication_method=none
```

The client ID must match a registration known to the Authorization Server, yet by itself it does not prove the caller is the genuine application. Never protect an API solely because a request claims a familiar client ID.

## 4. What Does the Token Endpoint Still Do for Public Clients?

For the Authorization Code grant, a properly configured Token Endpoint must enforce the **authorization grant** constraints before issuing tokens.

Important conditions include:

1. **The client registration exists and is allowed to use** the `authorization_code` grant.
2. **The authorization code is valid**, unexpired, unused, and issued to the matching Client.
3. **The Client ID matches** the code/client registration when a public client does not authenticate with credentials.
4. **The Redirect URI matches** the original authorization request and registration policy; when required by the protocol, the value in the token request must match identically.
5. **The PKCE code verifier matches** the code challenge stored from the authorization request; prefer `S256` and follow AS policy.
6. **Token issuance policies** are enforced, including scopes, audience/resource, consent, lifetimes, and other AS rules.
7. **Secure transport:** use TLS/HTTPS in real environments; never transmit codes, verifiers, or tokens over plain HTTP.
8. **Issue no tokens when checks fail**, returning the appropriate OAuth error instead.

Notably, a public client **can still receive an access token and an OIDC ID token** after a valid Authorization Code flow. `none` only describes how **the Client itself** authenticates at the Token Endpoint; it does not prevent the OP from authenticating the **user** and issuing OIDC responses.

## 5. Authorization Code + PKCE Is Essential

PKCE (Proof Key for Code Exchange, RFC 7636) is designed to reduce the risk of **an authorization code being intercepted or redeemed by another party**. PKCE is especially critical for public clients because they lack a protected client secret to authenticate at the Token Endpoint.

### 5.1. Two Values to Understand

- **`code_verifier`:** an unpredictable random string generated by the Client for **one authorization transaction**.
- **`code_challenge`:** a value derived from `code_verifier` and sent in the authorization request.

With the `S256` method:

```text
code_challenge = BASE64URL-ENCODE(
    SHA256(ASCII(code_verifier))
)
```

`code_challenge_method=S256` tells the Authorization Server how to verify it. When the Token Endpoint receives `code_verifier`, it computes the challenge itself and compares it against the value stored with the authorization code.

**Never send `code_verifier` in the authorization request via the browser.** The authorization request carries only `code_challenge`. The verifier is kept back until the token request; an attacker who intercepts the authorization code without knowing the verifier cannot exchange the code for tokens when the AS enforces PKCE properly.

### 5.2. Complete Flow

```mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant B as Browser / Native App
    participant C as Public Client
    participant AS as Authorization Server / OP
    U->>C: Initiate login
    C->>C: Generate per-transaction secret code_verifier
    C->>C: Compute code_challenge = BASE64URL(SHA256(verifier))
    C-->>B: Open authorization URL
    B->>AS: client_id, redirect_uri, state, code_challenge, method=S256
    AS->>U: Authenticate / consent if needed
    AS-->>B: Redirect back to client with code and state
    B->>C: Pass authorization code
    C->>AS: POST token: code, client_id, redirect_uri, code_verifier; no client secret
    AS->>AS: Validate code, Client, redirect URI, and PKCE
    AS-->>C: Access token and corresponding result if valid
    C->>C: If OIDC, verify ID token and establish appropriate session
```

### 5.3. PKCE Does Not Replace Other Protections

PKCE does not prove that the app running on a device is the "legitimate official app." Nor does it automatically replace:

- `state` / CSRF protections and callback correlation;
- redirect URI validation;
- OIDC `nonce` and ID token validation rules where applicable;
- scope restrictions and Resource Server authorization;
- protecting access/refresh tokens after issuance;
- defenses against redirect hijacking or deep-link interception on mobile.

A strong application uses **multiple layered checks**, rather than treating PKCE as a substitute for all of OAuth/OIDC security.

## 6. How Does a Public Client Send a Token Request?

After receiving a valid authorization code, the public client sends an `application/x-www-form-urlencoded` HTTP request to the Token Endpoint. Illustrative example:

```http
POST /realms/training/protocol/openid-connect/token HTTP/1.1
Host: id.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code
&client_id=mobile-learning-app
&code=<one-time-authorization-code>
&redirect_uri=com.example.learning%3A%2Foauth2redirect
&code_verifier=<per-request-secret-verifier>
```

In real HTTP traffic, form pairs are URL-encoded on a single body line; line breaks above are for readability. `com.example.learning:/oauth2redirect` is an illustrative redirect URI for a native application; actual supported schemes/URIs must match the AS registration and policy.

**Hallmarks of the `none` method:**

- No `Authorization: Basic ...` header carrying a client secret.
- No `client_secret` field in the body.
- No `client_assertion` used to authenticate the Client.
- `client_id` is present to identify the Client in the absence of client authentication.
- `code_verifier` is present if the prior authorization request used PKCE; for modern public clients, the AS should require and verify PKCE.

This does not mean "omitting the Authorization header is always valid"; the Authorization Server still enforces every authorization code constraint.

### 6.1. Comparison with a Confidential Client

Example of a confidential client using HTTP Basic:

```http
POST /realms/training/protocol/openid-connect/token HTTP/1.1
Host: id.example.test
Authorization: Basic <redacted-client-credentials>
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code
&code=<one-time-authorization-code>
&redirect_uri=https%3A%2F%2Fapp.example.test%2Flogin%2Foauth2%2Fcode%2Fweb
```

With a public client, the request sends `client_id` and no client secret; with a confidential client, the Authorization Server may require the registered client authentication mechanism. Both can use PKCE; **confidential clients are also recommended to use PKCE** in modern Authorization Code designs.

### 6.2. Why Is `client_id` Still Needed in the Token Request?

An authorization code must be bound to the Client it was issued to. Without client authentication credentials, the Token Endpoint needs to know **which client registration** is asking to exchange the code. `client_id` lets the AS look up the registration and match the code. This is **identification**, not proof of Client ownership.

A flawed system might accept any code alongside a Client ID supplied by anyone while skipping PKCE checks; a proper system enforces all grant conditions to prevent code interception.

### 6.3. Do Not Arbitrarily Log In Using the Returned Access Token

If an OIDC request includes the `openid` scope, the OP returns an ID token per the OIDC Code flow. The Client uses the verified ID token to establish user identity. The access token is meant for calling Resource Servers; never decode an access token and treat it as an ID token.

The `none` method only affects **client authentication** at the Token Endpoint. It does not alter the separation between user authentication, API authorization, and session management.

## 7. Generating `code_verifier` and `code_challenge`

In practice, let a well-maintained OAuth 2.0 library generate and manage PKCE. To understand the algorithm, inspect this standalone Java example:

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;

public final class PkceExample {

    public static void main(String[] args) throws Exception {
        byte[] randomBytes = new byte[32];
        new SecureRandom().nextBytes(randomBytes);

        String codeVerifier = Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(randomBytes);

        byte[] digest = MessageDigest.getInstance("SHA-256")
            .digest(codeVerifier.getBytes(StandardCharsets.US_ASCII));

        String codeChallenge = Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(digest);

        System.out.println("challenge method: S256");
        System.out.println("challenge length: " + codeChallenge.length());

        // Do not print codeVerifier in a real application:
        // this value must stay secret for one specific transaction.
    }
}
```

32 random bytes encoded with unpadded Base64url produce a 43-character verifier string, fitting RFC 7636 length bounds. The verifier is neither a user password nor a long-lived client secret; it is a secret value **specific to a single authorization transaction**.

When designing a custom implementation:

1. Use a cryptographic random source such as `SecureRandom`.
2. Generate a fresh verifier for each authorization attempt.
3. Use `S256` rather than relying on `plain`, unless there is a carefully evaluated compatibility reason.
4. Bind the verifier to the exact authorization transaction and prevent cross-talk between concurrent callbacks.
5. Never place the verifier in the authorization URL or logs.
6. Clear/discard the verifier upon completion or failure according to policy.

A common bug is regenerating the verifier when the callback arrives. That value will **not match** the challenge from the initial request, causing token exchange to fail. The framework must persist the verifier from creating the authorization request until receiving the code and calling the Token Endpoint.

## 8. Authorization Server Prerequisites Before Using `none`

Client configuration is only half the contract. The Authorization Server must know the registration is a public client and permit the `none` method.

| Prerequisite | Reason |
|---|---|
| Client registered as **public** or token endpoint auth method `none` | The AS must know the Client does not authenticate with credentials |
| Dedicated client ID | The AS identifies the registration, scopes, and policies for the Client |
| Authorization Code flow enabled | The Client needs a valid grant to exchange the code |
| PKCE S256 enabled and enforced | Mitigates code interception when no client secret exists |
| Exact Redirect URIs registered | Prevents redirecting codes to uncontrolled addresses |
| Restricted scopes/resources | Tokens must not grant permissions beyond policy |
| Short lifetime / single-use enforcement on authorization codes | Reduces replay risk |
| TLS and appropriate token policies | Protects codes, verifiers, and tokens in transit |
| Refresh token policy for public clients evaluated | Limits refresh token theft and replay exposure |

You **cannot** convert a Client registered as confidential into `none` merely by deleting `client-secret` in Spring Boot. If the Authorization Server expects client authentication, a token request without credentials will be rejected.

### 8.1. Token Endpoint Supporting `none` Does Not Mean Every Client Can Use `none`

An Authorization Server can support multiple Client authentication methods simultaneously, yet **each registration** has its own permitted mechanism. For example, an AS might serve both a public mobile app and a confidential backend.

If token endpoint metadata advertises `token_endpoint_auth_methods_supported`, that reflects the OP's global capabilities, **not a substitute for per-Client configuration**. Just because `none` appears in the list does not mean a Client registered with a secret can arbitrarily drop its secret.

### 8.2. Client Authentication Must Stay Separate from User Authentication

Users may still have to sign in, pass MFA, approve scopes, and undergo policy checks at the OP during the authorization flow. `none` does not skip any of those steps.

For example, a mobile client might use `none` while the Authorization Server requires MFA for employee login. After authentication, it can still issue an ID token representing the user's OIDC authentication event. The two questions—"Who is the user?" and "Does the Client authenticate itself with a secret?"—are handled independently.

## 9. Configuring a Public Client in Spring Boot / Spring Security

Consider a Spring Boot MVC lab app registered with the Authorization Server as a public client. Even though a backend **can** protect a client secret, this example deliberately uses a secretless registration to demonstrate Token Endpoint behavior. In production systems, choose public vs. confidential based on architecture and actual ability to protect secrets—never pick `none` just to shorten configuration.

### 9.1. Dependencies

A Servlet web application uses the appropriate starters:

```xml
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
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-client</artifactId>
    </dependency>
</dependencies>
```

### 9.2. `application.yml`

Suppose a test OP exposes issuer `http://localhost:9000/realms/training` and the registration has client ID `learning-public`:

```yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      client:
        registration:
          learning-public:
            provider: training
            client-id: learning-public
            client-authentication-method: none
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          training:
            issuer-uri: http://localhost:9000/realms/training
```

**Key details to recognize:**

- `client-authentication-method: none` states that the Client uses no client authentication credentials at the Token Endpoint.
- There is **no** `client-secret` on this registration.
- `client-id: learning-public` must still match the Client registered at the OP.
- `authorization-grant-type: authorization_code` uses Authorization Code, not password or implicit grant.
- `scope: openid` requests OIDC Login; Spring Security processes the ID token when supported by the provider.
- `redirect-uri` must match the URI registered at the OP, e.g., `http://localhost:8080/login/oauth2/code/learning-public`.
- `issuer-uri` must match the actual issuer published by the OP.

Localhost HTTP in a lab is purely illustrative; production environments require HTTPS and proper TLS. Do not copy URLs from a specific realm/OP if your project does not actually use it.

### 9.3. `SecurityFilterChain` Configuration

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SecurityConfig {

    @Bean
    SecurityFilterChain webSecurityChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
```

With registration `learning-public`, users can start at:

```text
http://localhost:8080/oauth2/authorization/learning-public
```

`oauth2Login()` enables the Authorization Code/OIDC flow for the Servlet Client; declaring `client-authentication-method: none` in YAML alone is not enough if you define HTTP Security yourself and forget `oauth2Login()`.

### 9.4. Spring Security and PKCE

`DefaultOAuth2AuthorizationRequestResolver` includes PKCE support for the Authorization Code flow; in common Spring Security 6.x releases, it automatically applies PKCE when the client authentication method is `none`. Therefore, when using the standard defaults, you typically **do not need to generate `code_verifier` or append `code_challenge` to the URL manually**.

However, understand the exact boundaries:

- The Client generates the challenge and stores the verifier.
- The Authorization Server must **enforce** PKCE per public client policy and validate the verifier properly.
- If you swap in a custom `OAuth2AuthorizationRequestResolver` or token response client, you must preserve the PKCE mechanism.
- When upgrading framework versions, check PKCE behavior in the specific Spring Security branch you use.
- The browser redirect only sees `code_challenge`, while the verifier is used when calling the Token Endpoint.

The Spring MVC code above demonstrates a **server-side OAuth2 Client** using `none`; it does not automatically turn the browser into a direct-to-token SPA. In this app, token exchange still happens on the Spring Boot side.

## 10. Public Client in Java Configuration

When an app does not use properties to create registrations, you can build `ClientRegistration` via the Java API. Example using metadata from an OP with OIDC discovery:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.ClientRegistrations;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

@Configuration
class ClientRegistrationConfig {

    @Bean
    ClientRegistrationRepository clientRegistrationRepository() {
        ClientRegistration publicClient = ClientRegistrations
            .fromIssuerLocation("http://localhost:9000/realms/training")
            .registrationId("learning-public")
            .clientId("learning-public")
            .clientAuthenticationMethod(ClientAuthenticationMethod.NONE)
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
            .scope("openid", "profile")
            .build();

        return new InMemoryClientRegistrationRepository(publicClient);
    }
}
```

This example illustrates only one registration; it requires a live OP with valid OIDC metadata and a matching public client registration. `ClientRegistrations.fromIssuerLocation(...)` uses discovery to resolve endpoints and may require the OP to be reachable when creating the bean.

**Note when defining a custom repository:** if the app provides its own `ClientRegistrationRepository` bean, Spring Boot backs off creating one from `application.yml`. Make sure every registration your app needs is included in the repository you manage—do not define a single public registration and accidentally lose other Clients.

## 11. Comparing Public and Confidential Using Two Registrations

To observe Token Endpoint behavior clearly, configure two Client registrations pointing to the same issuer with different Client authentication methods.

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          demo-public:
            provider: training
            client-id: learning-public
            client-authentication-method: none
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]

          demo-server:
            provider: training
            client-id: learning-confidential
            client-secret: ${DEMO_SERVER_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]

        provider:
          training:
            issuer-uri: http://localhost:9000/realms/training
```

Register **two Clients** at the OP:

| Attribute | `demo-public` | `demo-server` |
|---|---|---|
| Client type at OP | Public | Confidential |
| Client ID | `learning-public` | `learning-confidential` |
| Client secret in Spring | None | Yes, via secret store |
| `client-authentication-method` | `none` | `client_secret_basic` |
| PKCE | Must be enabled/enforced | Recommended per modern practice |
| Redirect URI | `/login/oauth2/code/demo-public` | `/login/oauth2/code/demo-server` |
| Browser login URL | `/oauth2/authorization/demo-public` | `/oauth2/authorization/demo-server` |
| Token Endpoint | Presents no Client secret | Sends configured client authentication |

Sharing the same OP does not mean the two Clients share tokens, permissions, or authentication policies. Registration ID also determines the callback URL and how `OAuth2AuthorizedClient` is keyed in Spring Security.

### 11.1. Comparison at the Token Endpoint

For `demo-public`:

- The token request relies on the authorization code and PKCE verifier.
- No Client secret or Basic credentials are sent.
- The Authorization Server validates client ID, code, redirect, and PKCE.

For `demo-server`:

- The Client presents the required Client authentication credentials, such as HTTP Basic.
- The token request still requires a valid authorization code and matching redirect.
- PKCE can still be used to protect the code.

**Do not** conclude "confidential clients don't need PKCE" or "a public client using PKCE is authenticated like a confidential client." They are two distinct mechanisms with different goals.

## 12. Spring MVC Web App vs. SPA: Same OAuth 2.0, Different Token Storage

A common design mistake is configuring a Spring Boot backend with `none` and calling that architecture an "SPA public client" even though the browser does not run an OAuth Client directly.

### 12.1. Traditional Spring MVC Model

```text
Browser
  |
  | session cookie
  v
Spring Boot MVC (OAuth2 Client)
  |                       ^
  | authorization code     | tokens
  v                       |
Authorization Server / OP
```

In this model:

- Spring Boot initiates the authorization request and handles the callback.
- Spring Boot calls the Token Endpoint over a server-to-server connection.
- The browser typically holds only the application's session cookie.
- If the backend can keep a secret safe, it normally uses a confidential client.
- If the AS allows a public registration and Spring Boot uses `none`, token exchange still happens server-side, just without client authentication.

### 12.2. Browser-Based Public Client Model

```text
Browser SPA
  |  \
  |   \ direct token request with code_verifier
  |    \
  v     v
Authorization Endpoint / Token Endpoint
  |
  v
Resource API (accepts access token per policy)
```

In this model:

- JavaScript running in the browser acts as the OAuth Client.
- A client secret cannot be protected like a server-side secret.
- Authorization Code + PKCE is far preferable to the implicit flow.
- The OP must support browser requirements, including **CORS on the Token Endpoint** when the SPA calls it directly from another origin.
- The application must defend tokens against XSS and choose an appropriate storage/session strategy.

**Setting `client-authentication-method: none` in a Spring MVC backend does not automatically enable CORS on the OP's Token Endpoint**, nor does it turn Spring Security Servlet login into a JavaScript OAuth SDK.

### 12.3. When Should You Consider a BFF?

When a product has a trusted backend, a BFF lets the browser rely solely on a session cookie while the backend holds tokens and makes OAuth 2.0/Resource Server calls as needed. Because the BFF can store credentials safely, a confidential registration is the natural fit.

A BFF still needs cookie protection, CSRF defenses, session fixation prevention, logout handling, authorization rules, and XSS protection. A public client is not inherently insecure in every situation; what matters is **matching the threat model and token policies**.

## 13. Application Types and Conditions for Using `none`

| Model | Ability to Protect Client Credentials | Can Use `none`? | What Must Be Prepared |
|---|---|---|---|
| Pure JavaScript SPA | Untrusted | Usually yes | Authorization Code + PKCE, OP CORS/token endpoint support for SPA, exact redirect, token & XSS protection |
| Native iOS/Android | Cannot protect secrets bundled in app | Usually yes | External/system browser, PKCE, RFC 8252 redirects, deep-link validation |
| Desktop app distributed to users | Untrusted | Usually yes | PKCE, loopback/URI redirect per policy, local token protection |
| Public CLI using browser/device flow | Cannot keep a shared secret | Possible | AS-supported grant, PKCE with authorization code or device grant rules |
| Spring Boot MVC backend | Usually can keep secrets | Technically possible if AS registers it public, though confidential is usually preferred | Clear reason for using `none`; PKCE, session/cookie security, aligned AS policy |
| BFF with server-side token storage | Usually can keep secrets | Usually unnecessary | Confidential client auth, cookie/session security, API proxy |
| Service-to-service daemon | Usually has server identity | Not a typical choice for `client_credentials` | Appropriate confidential client authentication |

Being a public client does not mean "the application is untrusted in every respect": users can still trust the app and the OP still performs login. It simply means **the Client cannot prove its own identity using a closely held static secret**.

### 13.1. Native Apps and Redirect URIs

Native applications commonly use:

- A custom URI scheme;
- An app-claimed HTTPS redirect URI (universal/app link);
- A loopback redirect to localhost on the device, depending on app style.

Choose the redirect style based on OS, SDK, and Authorization Server policy, referring to RFC 8252. Custom URI schemes can be claimed by competing apps; PKCE reduces the impact of code interception but does not eliminate all risks. Prefer the system browser/external user agent over an embedded WebView for login unless a specific supported requirement dictates otherwise.

### 13.2. Device Authorization Grant

A device without a convenient browser can use the OAuth 2.0 Device Authorization Grant if supported by the AS. A public client still usually lacks a client secret, yet **the device flow's token request has its own parameters and mechanics**, rather than Authorization Code + PKCE as in the main example. Do not copy `grant_type=authorization_code` into a device grant.

## 14. `none` and Other Grant Types

### 14.1. Authorization Code

This is the primary case. Public clients use `none` with Authorization Code + PKCE when permitted by the Authorization Server.

### 14.2. Client Credentials

The `client_credentials` grant is intended for Clients authenticating their own identity to the Authorization Server. **`none` should not** be treated as a standard way to use `client_credentials`, since a public client lacks trustworthy Client authentication proof.

If service-to-service authentication is needed, use proper confidential client authentication such as a securely managed secret, private key JWT, or mutual TLS per AS policy.

### 14.3. Refresh Token

A public client can be issued a refresh token if the AS permits it; `none` **does not inherently forbid** refresh tokens. However, because a public client has no client secret, the AS must mitigate the risk of refresh token theft and replay.

Per OAuth 2.0 Security Best Current Practice (RFC 9700), when issuing refresh tokens to public clients, the AS needs **sender-constraining** or **refresh token rotation** to detect/prevent replay as specified. Refresh tokens should also be scoped/resource-bounded with appropriate lifetimes and revocation rules.

On the Client side:

- Never put refresh tokens in URLs or logs.
- Avoid persisting tokens where malicious JavaScript can read them if your architecture allows safer options.
- On native apps, use platform-supported secure storage without treating it as a silver bullet against all attacks.
- Handle `invalid_grant` when a refresh token expires, is revoked, or is rotated.
- Do not assume a refresh token is guaranteed just by requesting `offline_access`; actual policies and parameters depend on the OP.

### 14.4. OIDC and `offline_access`

In OIDC, `offline_access` has defined semantics for requesting offline access, yet whether the OP issues a refresh token still depends on consent, grant, Client type, and provider policy. Using client authentication method `none` guarantees neither the presence nor the absence of a refresh token.

### 14.5. Implicit Grant and Resource Owner Password Credentials

Do not pick the implicit flow just to avoid the Token Endpoint, and do not use Resource Owner Password Credentials to funnel user passwords into a public client. For modern applications needing interactive login, prefer Authorization Code + PKCE and current security recommendations. The fact that a provider still supports a legacy grant does not make it right for new designs.

## 15. Token Endpoint Errors: Understanding the Real Cause

Two systems may return different error codes for the same situation depending on configuration. In practice, separate **Client authentication errors** from **grant/PKCE errors**.

| Symptom | Possible Cause | Where to Check |
|---|---|---|
| `invalid_client` | AS requires confidential client auth, yet request used `none` | Registration type at AS, `client-authentication-method` in Spring |
| `invalid_grant` | Authorization code expired, already used, wrong Client, wrong redirect URI, or wrong PKCE verifier | Entire grant binding and PKCE transaction |
| `invalid_request` | Missing parameter, duplicate parameter, wrong data type | Form body, `grant_type`, `client_id`, `code_verifier` |
| `unauthorized_client` | Client is not allowed to use this grant | Grant policy on the AS registration |
| `unsupported_grant_type` | AS does not support the requested grant | Check grant type and Token Endpoint |
| Redirect rejected by OP before callback | Authorization request used an unregistered redirect URI | Scheme/host/port/path and AS policy |
| Callback fails due to `state` | Request and callback do not match | Session, authorization request storage, multiple tabs, CSRF/correlation |
| Token request missing `code_verifier` | PKCE was not applied/persisted properly or a custom resolver dropped attributes | Did the authorization request have a challenge? Does token exchange have a verifier? |
| Token response lacks `id_token` when OIDC requested | OP did not complete OIDC Code flow or misconfiguration | `openid` scope, provider capability, and token response contract |
| API returns 401 after login | Wrong/expired access token or wrong audience for API | Resource Server verifier; separate from Client auth method at Token Endpoint |

PKCE-related `invalid_grant` errors typically avoid disclosing whether the code or the verifier failed, to limit information leakage. Focus on checking both Client and Authorization Server configurations alongside a sanitized request trace.

### 15.1. Never "Fix" `invalid_client` by Turning Off Checks

If a backend is registered as confidential and the Token Endpoint rejects it for a bad secret, switching to:

```yaml
client-authentication-method: none
```

is not a valid fix. First verify the credentials, `client_secret_basic`/`client_secret_post` delivery, or the registered method. Switch to `none` only after **redesigning the Client** and registering it appropriately at the AS with the required protections.

### 15.2. Do Not Confuse Token Endpoint Authentication with User Login

An `invalid_client` error indicates a Client/registration authentication problem; it does not mean the user typed the wrong password. An `invalid_grant` error can be a code replay, verifier mismatch, or wrong redirect URI even though the user signed in successfully at the OP.

Separating the steps clarifies diagnosis:

```text
Browser authorization request
    |
    v
OP authenticates user and issues code
    |
    v
Client sends code + code_verifier to Token Endpoint
    |
    +--> AS checks Client registration/auth method
    +--> AS checks code, redirect URI, PKCE
    |
    v
Token response
    |
    v
OIDC ID token validation / user principal / session
```

## 16. Observing Requests Without Exposing Secrets

Because the Token Endpoint handles credentials, codes, verifiers, and tokens, logging must be strictly restricted.

**Safe to record in sanitized lab notes:**

- registration ID and client authentication method;
- grant type name;
- presence/absence of HTTP Basic authentication;
- presence/absence of `client_id`, `code_verifier`, `redirect_uri`;
- code challenge method `S256`;
- HTTP status or summarized OAuth error code;
- OP's public issuer URI and demo endpoint URLs where appropriate.

**Never record verbatim:**

- authorization code;
- code verifier;
- client secret or Basic Authorization header;
- access token, refresh token, ID token;
- session cookies, actual `state`, and other transaction-binding data;
- user login credentials.

In Spring Security, you can enable DEBUG in development to observe filters and flow execution, but never log HTTP request/response bodies or token-bearing headers in environments with real data. Some HTTP client loggers/interceptors record full form bodies; audit them whenever working with the Token Endpoint.

## 17. Lab A — Public Client and PKCE S256

**Goal:** observe a `none` registration executing Authorization Code + PKCE.

**Preparation:**

1. A lab OP/AS supporting Authorization Code + PKCE S256.
2. Client registered as public with client ID `learning-public`.
3. Callback registered accurately for the Spring Boot MVC app at `http://localhost:8080`.
4. `application.yml` configuration from section 9.
5. A test user account containing no sensitive data.

**Steps:**

1. Start the OP and then start Spring Boot.
2. Open a private browser window and visit `/oauth2/authorization/learning-public`.
3. Observe the redirect to the authorization endpoint and note the **presence** of `code_challenge` and `code_challenge_method=S256`; do not copy actual values.
4. Complete sign-in at the OP.
5. Observe the callback and Token Endpoint request using safe lab tracing, recording only `grant_type`, `client_id`, `redirect_uri`, that `code_verifier` is present, and that no Client secret is sent.
6. Verify the app completes OIDC login and populates the principal.
7. Navigate to a post-login page and confirm normal operations use the application session without exchanging an authorization code again on every HTTP request.

**Expected result:** The Authorization Server accepts a token request without a client secret when the Client is registered as public and the authorization code/PKCE are valid. When using OIDC, the Client proceeds to verify the ID token before establishing user identity.

**Question:** Why is `client_id` not treated as a secret? Which value lets the Token Endpoint verify that the party exchanging the code knows the original transaction's verifier?

## 18. Lab B — Comparing `none` and `client_secret_basic`

**Goal:** understand how public and confidential clients differ at the Client authentication step without confusing it with user sign-in.

**Preparation:** two registrations `demo-public` and `demo-server` on the same OP, as in section 11.

**Steps:**

1. Sign in via `/oauth2/authorization/demo-public` and record what Client authentication data is sent at the Token Endpoint.
2. Open a new private browser window and sign in via `/oauth2/authorization/demo-server`.
3. Record that the second token request uses the `client_secret_basic` Client authentication method.
4. Compare scopes and ID tokens between the two flows at a safe public-claim level if both use OIDC.
5. Verify each registration has its own callback and Client ID; do not share tokens across them.
6. Never store real credentials in notes.

**Expected result:** both can sign in the same user at the OP, yet how the Client proves (or does not prove) its Client identity at the Token Endpoint differs. In both cases, the authorization code must be valid and bound to the right registration.

## 19. Lab C — PKCE Verifier Mismatch

**Goal:** see that the Token Endpoint still rejects a `none` request that lacks the right verifier.

**Preparation:** a test Authorization Server allowing sanitized request/response inspection or a controlled OAuth2 mock tool; use only dummy or lab-issued codes/tokens.

**Steps:**

1. Create a valid authorization attempt with PKCE S256 and note that the AS stored the challenge.
2. In the mock/lab environment, send a token request carrying a verifier **different** from the original verifier.
3. Observe the token endpoint rejecting it with the appropriate grant/PKCE error, typically `invalid_grant`.
4. Test omitting the verifier when a challenge was registered; observe the AS rejecting it.
5. Run a fresh complete flow with the matching verifier via the framework for comparison.
6. Never send raw verifiers or authorization codes to shared logs.

**Expected result:** the AS refuses to issue tokens for a code presented with a mismatched verifier. Having the right `client_id` alone is not enough to bypass PKCE.

**Question:** Why is an intercepted code insufficient on its own to obtain tokens when PKCE is enforced? Why must a new verifier be generated for every authorization attempt?

## 20. Lab D — Public Client Registered as the Wrong Type

**Goal:** diagnose a contract mismatch between Client and Authorization Server.

**Steps:**

1. Register a confidential lab Client requiring `client_secret_basic`.
2. Configure the Spring registration for that confidential setup and verify a successful baseline run.
3. Temporarily change **only the Spring side** to `client-authentication-method: none` and remove the secret.
4. Start a new login; observe the Token Endpoint rejecting it per AS policy.
5. Restore the original confidential configuration.
6. Create a **new public registration** on the AS; configure Spring with `none` and PKCE, then run a valid flow.

**Expected result:** changing a property in Spring does not change the Client type registered on the AS. The Client authentication method must match on both sides.

## 21. Lab E — Architectural Design

**Goal:** decide how to use `none` based on real-world application types.

Analyze these four scenarios:

| Problem | Option to Consider | Rationale |
|---|---|---|
| Mobile app for employee sign-in | Public Client + Authorization Code + PKCE | Secrets distributed inside the app cannot be trusted |
| Website with only a Spring MVC backend and server-side sessions | Confidential Client + Authorization Code, with PKCE recommended | Backend can protect credentials and tokens |
| SPA exchanging codes directly at the Token Endpoint | Public Client + PKCE, proper CORS/XSS defenses | Browser cannot protect secrets; direct token exchange requires OP support |
| Backend scheduler calling APIs with no user | Confidential client with matching grant and client authentication, e.g., `client_credentials` | Not an interactive user login |

**Analysis questions:**

1. Where are codes and tokens held?
2. Can Client secrets be kept out of end users' reach?
3. Which registration types and grants does the Authorization Server support?
4. Which component generates, stores, transmits, and verifies PKCE?
5. Does the browser call the Token Endpoint directly or go through a backend?
6. Where are tokens stored, are refresh tokens needed, and what replay protections apply?
7. Where are cookie/session, CSRF, XSS, and CORS protections required?

Never choose `none` merely because it has "fewer configuration fields"; choose it when the architecture calls for it and the Authorization Server enforces the corresponding safeguards.

## 22. Common Misconceptions

| Misconception | Correct Understanding |
|---|---|
| "`none` means no security." | It only means no **Client credential authentication** at the Token Endpoint; grant, PKCE, redirect, scopes, and token validation still apply. |
| "Having `client_id` authenticates the Client." | Client ID is a public identifier, not proof of possessing a secret. |
| "PKCE turns a public client into a confidential one." | PKCE protects the authorization code exchange; it does not make distributed code capable of keeping a client secret. |
| "Public clients can never have refresh tokens." | They may be issued per AS policy, with appropriate anti-replay protections. |
| "Spring Boot sets `none`, so the token endpoint won't require PKCE." | PKCE must be used by both sides and enforced by the AS; `none` does not replace PKCE. |
| "A Spring Boot backend must always use `none` if the frontend SPA uses JavaScript." | If the backend acts as the OAuth Client and protects secrets, it can be confidential; it depends on where token exchange runs. |
| "A client secret embedded in a mobile app is safe because it's obfuscated." | Static secrets shipped to devices can be extracted; obfuscation does not turn public into confidential. |
| "A Token Endpoint receiving a code doesn't need redirect URI or Client ID." | Client, redirect, and grant bindings must all be checked per protocol. |
| "`none` works for standard `client_credentials`." | Machine-to-machine grants require authenticating the Client identity per policy; `none` is not the default choice. |
| "No Basic Authorization header means the token request is broken." | For a public client registered with `none`, omitting Basic credentials is expected. |
| "CORS replaces PKCE." | CORS is a browser cross-origin policy; PKCE protects the authorization code exchange. |
| "ID tokens and access tokens are interchangeable." | An ID token confirms identity to the Client; an access token authorizes access to a Resource Server. |

## 23. Self-Check Questions

**Question 1.** Why isn't an APK containing a client secret considered a confidential client just because the secret is encrypted or obfuscated?

*Hint:* anyone installing the app can inspect the binary and extract data shipped with the application.

**Question 2.** With `client-authentication-method: none`, does the Token Endpoint ignore `client_id`?

*Hint:* no; the AS needs to identify the Client registration and confirm the authorization code was issued to that Client.

**Question 3.** Does PKCE send `code_challenge` or `code_verifier` in the authorization request?

*Hint:* only the challenge travels through the browser; the verifier is sent in the token request.

**Question 4.** Why must `code_verifier` be tied to each individual authorization transaction?

*Hint:* the Token Endpoint must match it against the challenge for that exact code; reusing or regenerating it creates risks or mismatches.

**Question 5.** A Spring Boot backend can hold a Client secret in a secret manager. Should you immediately switch to `none` just because the Token Endpoint returns `invalid_client`?

*Hint:* no; verify the registration and Client authentication setup first, and only move to public when the architecture and AS policy warrant it.

**Question 6.** When a SPA calls the Token Endpoint directly, what browser requirements apply beyond OAuth PKCE?

*Hint:* the OP must support the required CORS headers; the app must minimize XSS/token exposure and manage redirects/origins safely.

**Question 7.** Are refresh tokens completely forbidden for public clients?

*Hint:* no; however, the AS must apply replay mitigations such as rotation or sender-constraining per current standards/recommendations.

**Question 8.** Does `none` at the Token Endpoint mean users don't have to log in at the OP?

*Hint:* no; client authentication and user authentication are two separate steps.

**Question 9.** An app uses `openid` and `none`. After token exchange, what must it do with the ID token?

*Hint:* verify issuer, audience, signature, expiration, and required OIDC claims before establishing identity.

**Question 10.** Is a public client using the `client_credentials` grant without presenting credentials a typical machine-to-machine architecture?

*Hint:* no; service-to-service designs require authenticating the Client via a mechanism trusted by the AS.

## 24. References

- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): Client classification, Authorization Code Grant, Token Endpoint, and meaning of client authentication.
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636): generating `code_verifier`, `code_challenge`, and verifying PKCE.
- [RFC 8252 — OAuth 2.0 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252): public native clients, redirect URIs, and recommending external browsers.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): protecting authorization codes, PKCE, refresh tokens, and anti-replay defenses.
- [OAuth 2.0 for Browser-Based Applications](https://datatracker.ietf.org/doc/draft-ietf-oauth-browser-based-apps/): SPA and BFF architecture guidance; check the current status of the specification version in use.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): OIDC Authorization Code flow, ID tokens, and client authentication considerations.
- [Spring Security — OAuth 2.0 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): `ClientRegistration` and OAuth 2.0 Client mechanics on Servlet.
- [Spring Security — OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html): redirects, callbacks, and OIDC login.
- [Spring Security — Advanced OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): authorization endpoint, token endpoint, and PKCE customization.
- [Spring Security API — ClientAuthenticationMethod](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/ClientAuthenticationMethod.html): method values, including `NONE`.
- [Spring Security API — DefaultOAuth2AuthorizationRequestResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/DefaultOAuth2AuthorizationRequestResolver.html): default resolver building authorization requests and PKCE.

**Key takeaway:** public clients use `client-authentication-method: none` because they cannot protect a shared Client credential. The Authorization Server must still identify the Client and strictly validate the authorization code, redirect URI, and PKCE. With Spring Security, configuring `none` must pair with a matching public registration at the OP and a protected Authorization Code + PKCE flow. Whenever the backend can safely keep a Client secret, prefer a confidential client aligned with your real architecture; never use `none` as a shortcut around Client authentication errors.
