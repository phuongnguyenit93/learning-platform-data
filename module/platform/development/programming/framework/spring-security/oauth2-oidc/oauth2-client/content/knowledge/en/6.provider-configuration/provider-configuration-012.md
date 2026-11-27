# 6.12. Separating Secrets from Public Configuration Properties

## 1. Why Separate Configuration When Integrating OAuth 2.0/OIDC?

A Spring Boot application using **Spring Security OAuth 2.0 Client** usually has two groups of data when configuring an Identity Provider (**IdP**):

1. **Descriptive and routing information**: issuer URI, authorization endpoint, token endpoint, client ID, scopes, redirect URI, and other URIs. Many of these values can be public or shared among development, operations, and provider teams.
2. **Secrets or credentials**: confidential client's client secret, private key used to sign client assertions, keystore passwords, access tokens, refresh tokens, and other authentication material. These values must be protected with dedicated access controls and lifecycles.

For example, an **Employee Portal** uses OIDC to sign employees in at the corporate IdP, then uses an OAuth 2.0 access token to call an Orders API on behalf of the employee. The Portal needs to know the **issuer** and **client ID** to build authorization requests. If the Portal is a **confidential web client**, it must also safeguard the **client secret** used to authenticate with the token endpoint.

In practice, these two kinds of data easily get mixed into **application.yml**, causing secrets to be committed to Git or leak into build artifacts, container images, attachments, logging systems, or deployment docs. This lesson shows how to **classify**, **store**, **load into Spring Boot**, and **rotate** secrets while keeping provider configuration easy to understand.

> Primary scope: **Spring Boot 3 / Spring Security 6**, **server-side OAuth 2.0/OIDC Client** application using the Authorization Code Flow. The URLs, IDs, and example strings below do not represent a live IdP. Production configuration must match your provider's capabilities and policies.

## 2. "Public" Does Not Mean "Unimportant"

**Public** information is data that, if read by someone else, **does not by itself grant access**. Conversely, a **secret** can be used to authenticate, obtain tokens, or access resources if stolen.

However, public information still requires **integrity**: an issuer URI modified to point to a rogue IdP, a redirect URI swapped for an attacker's address, or a wrong audience can cause severe failures. Therefore:

- **Confidentiality** is a special requirement for secrets.
- **Integrity protection** must apply to **both secrets and public configuration**.
- **Operational access restrictions** remain helpful for certain internal URLs/IDs, even when they are not credentials.

A **client ID** is placed into authorization requests through the browser and is therefore **not a password**. A confidential client's **client secret** is the opposite: it must never appear in JavaScript, mobile apps distributed to users, or publicly readable files.

## 3. Classification Table of Common OAuth 2.0/OIDC Properties

| Property / data | Usually treated as | Rationale and handling |
|---|---|---|
| **issuer-uri**, e.g. \`https://login.example.test/realms/company\` | Descriptive configuration | Used to identify the trusted IdP; must protect integrity |
| **authorization-uri** | Descriptive configuration | Endpoint where the browser is sent to authenticate/authorize |
| **token-uri** | Descriptive configuration | Server-to-server address to exchange codes/refresh tokens; connection must be secure |
| **jwk-set-uri** | Descriptive configuration | URI to fetch **public keys** for signature verification, contains no private keys |
| **user-info-uri** | Descriptive configuration | Endpoint URL to retrieve claims when allowed; returned data may be sensitive |
| **client-id** | Public identifier | Identifies the client registration; does not prove client authentication |
| **redirect-uri** | Descriptive configuration, integrity-sensitive | Must match registered URI; avoid wildcards and wrong scheme/host |
| **scope**, e.g. \`openid profile orders.read\` | Requested permissions description | Declaring a scope does not mean permission was granted |
| **client-authentication-method** | Descriptive configuration | Indicates client auth mechanism: \`client_secret_basic\`, \`private_key_jwt\`, ... |
| **client-secret** | **Secret** | Confidential client credential; must be protected at runtime |
| **private key** for \`private_key_jwt\` | **Secret** | Anyone holding the private key can sign assertions as the client |
| **keystore password**, TLS private key, mTLS client private key | **Secret** | Cryptographic credentials; need appropriate storage and access control |
| **access token** | **Sensitive authentication credential** | Bearer token can be replayed if leaked, whether JWT or opaque |
| **refresh token** | **High-value secret** | Can mint additional access tokens per IdP policy |
| **authorization code**, **PKCE code_verifier** | **Short-lived, sensitive transaction data** | Not static configuration; must be protected during authorization flow |
| **state**, **nonce** | Per-transaction security values | Must be generated/verified properly; never logged or fixed to a shared string |
| **ID Token** | Sensitive identity and authentication data | May contain personal data; used to verify OIDC login at the client |
| **user username/password** | **Secret** | Standard OIDC redirect apps must never collect IdP passwords themselves |
| **introspection client secret** | **Secret** | Resource Server credential when calling the introspection endpoint |

This list classifies by **intended usage**, not merely by name. For example:

- Public **JWKS** holds **public keys** for signature verification; the **private key** issuing signatures remains the Authorization Server's secret.
- A JWT access token having a readable payload does not make that token "public data." Every bearer token must be protected.
- **client_id** may be public, yet processes registering or modifying client_id and redirect URIs must be restricted to authorized personnel.

## 4. Confidential Clients vs. Public Clients Manage Secrets Differently

Not every OAuth Client has the same ability to keep a secret.

### 4.1. Confidential Web Client

Employee Portal runs on its own server and can hold a client secret or private key that browsers cannot read. The IdP can register it as a **confidential client** and require authentication at the token endpoint.

~~~mermaid
sequenceDiagram
    actor User as User
    participant Browser as Browser
    participant Portal as Spring Boot Portal
    participant IdP as OIDC Provider

    User->>Browser: Choose company sign-in
    Browser->>Portal: GET /oauth2/authorization/company
    Portal-->>Browser: Redirect to IdP
    Browser->>IdP: Authorization request (client_id, redirect_uri, scope...)
    IdP-->>Browser: Redirect callback with code
    Browser->>Portal: GET /login/oauth2/code/company?code=...
    Portal->>Portal: Retrieve client secret from secure runtime config
    Portal->>IdP: POST /token (code + confidential client auth)
    IdP-->>Portal: Token response
    Portal-->>Browser: Session cookie
~~~

In the example:

- **client_id** appears in the browser request redirected to the IdP.
- **client_secret** is used only by the server-side Portal to authenticate with the token endpoint; the browser **never needs to know it**.
- **access token/refresh token** are managed by the Portal after receipt, never automatically returned to the web UI.

### 4.2. Public Clients: SPAs or Mobile Applications

An SPA running in a browser and a mobile app distributed to user devices **cannot safely hold a static client secret**. Any secret bundled into JavaScript, an APK, or a client binary can be extracted; renaming variables or obfuscating code does not make it secret.

For public clients, the standard model is **Authorization Code Flow with PKCE**, paired with platform-appropriate redirect URI policies, CORS, and token protection; the client **does not rely on a client secret as trustworthy secret proof**. With a **Backend for Frontend** pattern, only the backend acts as the confidential client while the browser interacts with the backend via a session cookie.

**PKCE does not make a client secret redundant in every architecture.** PKCE protects the authorization code from being redeemed by another party; authenticating a confidential client via a secret or private key is a separate layer. Provider and client type dictate the exact setup.

## 5. Organizing Configuration Files in Spring Boot

The goal in this example is a **readable and committable** configuration in the repository, while real credentials are supplied only at runtime.

~~~text
employee-portal/
├── src/main/resources/
│   ├── application.yml
│   ├── application-local.yml
│   ├── application-staging.yml
│   └── application-prod.yml
├── .env.example                     # example variable names, no secret values
├── .gitignore
└── deployment/
    ├── README.md                    # documents runtime inputs
    └── ...                          # deployment definitions containing no real secrets

Runtime:
  ├── Environment variable          # e.g., injected from a secret manager
  └── /run/secrets/...               # secret file only present in container at runtime
~~~

It is **not mandatory** for every project to use both secret-loading approaches. Choose **environment variables** or **mounted files/config trees** depending on your platform. What matters is that secrets are never committed or baked into packaged artifacts.

### 5.1. `application.yml` Contains Only Shared Settings, Never Real Client Secrets

~~~yaml
# src/main/resources/application.yml (safe to commit)
spring:
  application:
    name: employee-portal

  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
              - orders.read
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}

app:
  orders:
    base-url: ${ORDERS_API_BASE_URL}
~~~

Notice: there is **no `client-secret` anywhere** in this YAML. Spring Boot can receive that value from a higher-precedence `PropertySource`, such as an environment variable named:

~~~text
SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_COMPANY_CLIENT_SECRET
~~~

Spring Boot uses relaxed property binding to map that environment variable to:

~~~text
spring.security.oauth2.client.registration.company.client-secret
~~~

With **client_secret_basic**, without the required credential, token exchange at the IdP fails; this is not yet a complete production configuration. We supply the secret at runtime in the following sections.

**Why put client ID and issuer into variables even when they are not secrets?** They typically differ across local, staging, and production. Using placeholders avoids duplicating source code. If their actual values are non-sensitive under organizational policy, they can also be written directly into profile files.

### 5.2. Splitting Profiles by Environment

~~~yaml
# application-local.yml
server:
  port: 8080

logging:
  level:
    root: INFO
    org.springframework.security: INFO
~~~

~~~yaml
# application-staging.yml
server:
  forward-headers-strategy: framework
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
~~~

~~~yaml
# application-prod.yml
server:
  forward-headers-strategy: framework
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax

management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Depending on the environment, issuer, redirect URI, hostname, and cookie policies may differ. Ensure the **active profile** is actually selected by the deployment, e.g., \`SPRING_PROFILES_ACTIVE=prod\`. Never put real secrets into a profile file just because that file is "only used in production."

Spring Boot's precedence order allows environment variables or command-line arguments to override YAML properties. When troubleshooting configuration, determine the **final winning source**, without printing secret values to logs for a "quick check."

## 6. Option A: Supplying the Client Secret via Environment Variables

### 6.1. Runtime Environment Configuration

Example variables the Portal needs at deployment:

~~~text
SPRING_PROFILES_ACTIVE=prod
OIDC_ISSUER_URI=https://login.example.test/realms/company
OIDC_CLIENT_ID=employee-portal-prod
ORDERS_API_BASE_URL=https://orders.example.test
SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_COMPANY_CLIENT_SECRET=<value-provided-by-secret-manager>
~~~

Here the first four values are operational configuration; the last variable is a **secret**. All can be injected into the Java process via platform mechanics, yet the secret must come from a separate source with restricted read permissions.

**Local PowerShell example (placeholder, not a real secret):**

~~~powershell
$env:SPRING_PROFILES_ACTIVE = 'local'
$env:OIDC_ISSUER_URI = 'https://login.dev.example.test/realms/company'
$env:OIDC_CLIENT_ID = 'employee-portal-local'
$env:ORDERS_API_BASE_URL = 'http://localhost:8081'

# Obtain the secret value through a tool approved by your organization.
$env:SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_COMPANY_CLIENT_SECRET = '<local-secret-placeholder>'

./gradlew.bat bootRun
~~~

In this example, the shell command contains a **placeholder**; never write real secrets directly into docs, CI output, or shared guides. In practice, manually typing secrets into commands can be saved in shell history or captured by monitoring tools; when the platform offers a secure secret-injection mechanism, prefer it.

Environment variables are **a channel to pass values into a process**, not inherently a secret vault: process diagnostics, host admin access, CI/CD configuration dumps, and crash dumps can still expose values. Therefore protect the **secret source**, **process access rights**, and **deployment pipeline**.

### 6.2. Kubernetes: `ConfigMap` for Non-Secret Data, `Secret` for Credentials

Illustrative example separating configuration injected into a container:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: employee-portal
spec:
  replicas: 2
  selector:
    matchLabels:
      app: employee-portal
  template:
    metadata:
      labels:
        app: employee-portal
    spec:
      containers:
        - name: portal
          image: registry.example.test/employee-portal:1.0.0
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: prod
            - name: OIDC_ISSUER_URI
              valueFrom:
                configMapKeyRef:
                  name: portal-public-config
                  key: oidcIssuerUri
            - name: OIDC_CLIENT_ID
              valueFrom:
                configMapKeyRef:
                  name: portal-public-config
                  key: oidcClientId
            - name: ORDERS_API_BASE_URL
              valueFrom:
                configMapKeyRef:
                  name: portal-public-config
                  key: ordersApiBaseUrl
            - name: SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_COMPANY_CLIENT_SECRET
              valueFrom:
                secretKeyRef:
                  name: portal-oidc-credential
                  key: client-secret
~~~

Here \`portal-public-config\` is a **ConfigMap**, while \`portal-oidc-credential\` is a **Kubernetes Secret** created and managed securely outside this manifest.

**A Kubernetes Secret is not automatically a complete vault.** Data in Secrets requires proper RBAC permissions, etcd encryption at rest where required by platform policy, restricting who can view pod descriptions/logs, and access auditing. Base64 encoding inside manifests is not secret encryption. Never commit a Secret manifest containing sensitive data in Base64 thinking it is protected.

When injecting via **environment variables**, updating a Kubernetes Secret usually **does not change values already injected into running processes**; use an appropriate rolling restart/redeploy strategy so new application instances pick up new credentials.

## 7. Option B: Mounted Secret Files and Spring Boot Config Tree

On platforms supporting mounted secret files, Spring Boot can read secrets from a **config tree**. The container receives the secret file at runtime; the file never sits in the repository or JAR.

Suppose infrastructure creates a file:

~~~text
/run/secrets/
└── spring.security.oauth2.client.registration.company.client-secret
~~~

The sole content of that file is **the client secret value**, not YAML and not including the property name. Set file permissions so only the application process and authorized operations components can read it.

In **application-prod.yml** you can declare:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/"
~~~

Spring Boot imports files under this directory as configuration properties. The filename becomes the corresponding property name, so the file in the example supplies the value for:

~~~text
spring.security.oauth2.client.registration.company.client-secret
~~~

**This is an alternative to injecting secrets via environment variables** from the previous section; choose one clearly managed source to avoid precedence ambiguity. With a mandatory import, the application should fail to start in production if the secret directory is not mounted.

In some environments, config trees also suit PEM/certificate data and passwords. However, check which APIs expect a **value** versus a **file path**; not every property reads file contents the same way.

**Protect files after mounting:** restrict filesystem permissions, never let a web server serve the secret directory, never copy files into build artifacts, and never back up or sync them to unauthorized locations. If a secret file is updated while the application is running, do not assume Spring Boot automatically refreshes every OAuth2 Client bean; reload/restart mechanics must be explicitly designed.

## 8. Provider Metadata Is Public, Yet Must Be Verified

OpenID Connect allows the Client to obtain provider configuration metadata via discovery. Example issuer:

~~~text
https://login.example.test/realms/company
~~~

Metadata may supply:

~~~json
{
  "issuer": "https://login.example.test/realms/company",
  "authorization_endpoint": "https://login.example.test/realms/company/protocol/openid-connect/auth",
  "token_endpoint": "https://login.example.test/realms/company/protocol/openid-connect/token",
  "jwks_uri": "https://login.example.test/realms/company/protocol/openid-connect/certs",
  "userinfo_endpoint": "https://login.example.test/realms/company/protocol/openid-connect/userinfo",
  "response_types_supported": ["code"],
  "subject_types_supported": ["public"]
}
~~~

The URLs in the example are descriptive configuration. They are **not credentials**, yet they must come from a trusted IdP accessed over TLS, with issuer verification per OIDC requirements.

In Spring Security, configuration can be concise:

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}
~~~

If the provider conforms to discovery, Spring can infer the required endpoints. Specifying \`issuer-uri\` **grants no permission** to any client and **contains no client secret**. Metadata discovery must never be used as a secret-delivery source.

If the provider does not support compatible discovery, configure \`authorization-uri\`, \`token-uri\`, \`jwk-set-uri\`, \`user-info-uri\`, and \`user-name-attribute\` individually as needed. Even when configured manually, endpoints remain **subject to integrity verification**; never take an arbitrary URL from a user request and treat it as a trusted IdP.

### Difference Between Public Keys and Private Keys

- **Public keys** in JWKS verify JWT signatures; public JWKS documents **do not reveal private keys**.
- **Private keys** used to sign tokens or client assertions must be protected via a secret manager, HSM, or properly access-controlled keystore.
- **kid** is an identifier for selecting a key from a trusted keyset; it does not by itself prove an untrusted key inside a token can be trusted.

## 9. Shared Spring Security Configuration Across Environments

The security layer should only define **application rules**, without embedding per-environment IdP endpoints and secrets directly.

~~~java
package com.example.portal.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/assets/**", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

With registration ID **company**, Spring Security provides by default:

~~~text
Login URL:     /oauth2/authorization/company
Callback URL:  /login/oauth2/code/company
~~~

The registration is loaded from property sources, so \`SecurityConfig\` does not need to know whether the client secret lives in an environment variable or a mounted file. Never write branches like "if local use hardcoded secret A, if production use hardcoded secret B" in Java.

When calling APIs, the Client uses **OAuth2AuthorizedClient** for the current principal rather than reading secrets to forge tokens or sending the client secret in requests to a Resource Server:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
class OrdersController {

    private final RestClient ordersApi =
        RestClient.create("https://orders.example.test");

    @GetMapping("/bff/orders")
    String orders(
        @RegisteredOAuth2AuthorizedClient("company")
        OAuth2AuthorizedClient authorizedClient
    ) {
        String accessToken = authorizedClient.getAccessToken().getTokenValue();
        return ordersApi.get()
            .uri("/api/orders")
            .headers(headers -> headers.setBearerAuth(accessToken))
            .retrieve()
            .body(String.class);
    }
}
~~~

To make the application fully environment-driven, the **orders.example.test** URL in this example should also be bound from a public property like \`app.orders.base-url\` instead of being fixed in Java. The token in the example is an **access token**, not a client secret; both are sensitive, yet serve **different purposes**.

## 10. Client Authentication Methods and Their Corresponding Secrets

Not every provider uses \`client_secret_basic\`. Examples:

| Method at token endpoint | Credential to protect on confidential client | Operational guidance |
|---|---|---|
| **client_secret_basic** | Client secret | Sent via HTTP Basic during token exchange over TLS |
| **client_secret_post** | Client secret | Credentials in POST body; use only when permitted by IdP policy |
| **client_secret_jwt** | Shared secret used to sign JWT assertion | Protect secret and ensure algorithm/timing match agreement |
| **private_key_jwt** | Private signing key | Protect private key; manage JWKS/public key and rotation |
| **tls_client_auth / self_signed_tls_client_auth** | Private key and matching certificate | Manage certificates, TLS binding, keystore, and rotation |
| **none** (public client) | No shared static client secret | Use public-client safeguards, typically Authorization Code + PKCE |

Spring Security configuration depends on the method and provider. Do not switch \`client-authentication-method\` to another value merely hoping to "hide the secret": for example, \`private_key_jwt\` requires real client assertion signing and private key management, not just changing one YAML line.

**A client secret is an application credential**, not a user password and not an OAuth access token. Using the wrong credential type can break the flow or widen exposure if leaked.

## 11. Separating Secrets from Data Generated During Login

In the OIDC Authorization Code Flow, several values do not exist in configuration files before a user logs in:

~~~mermaid
flowchart TD
    A["Static config from repository: issuer, client ID, redirect URI, scope"] --> C["Spring Security OAuth2 Client"]
    B["Runtime secret source: client secret / private key"] --> C
    C --> D["Authorization request: state, nonce, PKCE"]
    D --> E["Authorization Server"]
    E --> F["Short-lived authorization code"]
    F --> C
    C --> G["Token response: ID token, access token, refresh token if any"]
    G --> H["SecurityContext and OAuth2AuthorizedClient"]
    H --> I["Call Resource Server with access token"]
~~~

Classification by lifecycle:

- **Client secret or private key**: application registration credential, typically issued and rotated on its own schedule.
- **state, nonce, PKCE code_verifier**: values bound to a single authorization attempt; must be generated per transaction and verified properly, never hard-coded as a global string in YAML.
- **authorization code**: short-lived, single-use value in the token-exchange step.
- **access token, refresh token, and ID Token**: data issued after authorization/login, kept in secure storage tied to the session or authorized client; **never placed in `application.yml`**.

In an MVC/BFF application, the browser normally holds only the Portal's **session cookie**. Tokens are managed on the server side. When running multiple replicas, the system needs an appropriate session/authorized-client store; keeping the client secret in a vault does not by itself solve protecting refresh tokens or sessions.

## 12. Keeping Secrets Out of Git, Artifacts, Container Images, and Documentation

### 12.1. `.env.example` Template

A template file should document **variable names** without real credentials:

~~~dotenv
SPRING_PROFILES_ACTIVE=local
OIDC_ISSUER_URI=https://login.dev.example.test/realms/company
OIDC_CLIENT_ID=employee-portal-local
ORDERS_API_BASE_URL=http://localhost:8081
SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_COMPANY_CLIENT_SECRET=REPLACE_WITH_LOCAL_SECRET
~~~

\`.env.example\` can be committed, while files holding real secrets like \`.env\` and \`.env.local\` must be ignored or managed outside the repository per policy.

~~~gitignore
.env
.env.*
!.env.example
*.p12
*.pfx
*.key
~~~

This is an example to tailor to actual project files; broadly ignoring **.key** extensions may be unsuitable if the repository legitimately holds public keys or approved test fixtures. **.gitignore does not delete secrets already committed** and does not protect secrets in commit history.

### 12.2. Spring Boot Does Not Automatically Read `.env`

Having \`.env.local\` in the project directory **does not mean Spring Boot will load it automatically**. An IDE, shell script, container runtime, or environment-loading tool must be explicitly configured. Do not rely on assuming a \`.env\` file is silently picked up by the framework.

### 12.3. Container Images Must Be Generic Artifacts

A container image should hold **application code and non-secret configuration**, while secrets are injected at deploy time:

~~~text
Build:
    source code + application.yml
       -> JAR / container image

Deploy:
    image + profile + provider metadata + secure secret source
       -> Spring Boot process
~~~

Never use Dockerfile \`ENV CLIENT_SECRET=...\`, build arguments containing secrets, or \`COPY .env\` with secrets into the image. Those values can leak via layer history, registries, image scanners, or image copies. If a build requires its own credentials, use a scoped, short-lived build-secret mechanism; runtime OAuth Client credentials never belong in the build stage.

## 13. Logs, Actuator, and Channels That Accidentally Leak Secrets

Even when secrets never enter Git, the following channels can expose credentials:

- HTTP request/response logs containing **Authorization** headers, cookies, authorization codes, or token endpoint responses.
- **Spring Boot Actuator**, configuration dumps, error pages, heap dumps, or diagnostic endpoints left overly permissive.
- Traces/APM, reverse proxy access logs, CI/CD job logs, command-line history, and troubleshooting screenshots.
- Browser developer tools or frontend telemetry if the backend returns tokens to JavaScript.
- Error messages including secrets or sensitive headers.

Example production configuration restricting Actuator endpoints exposed over the web:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info

logging:
  level:
    root: INFO
    org.springframework.security: INFO
~~~

Reducing exposed endpoints **does not replace** authentication/authorization and network controls for Actuator. If an organization needs **/actuator/env** or **/actuator/configprops** for operations, restrict access and configure **sanitization/show-values** appropriate for your Spring Boot version; never treat the framework's default name-based masking as your sole security barrier.

When confirming Spring received the right values:

**Do:** log active profile name, approved issuer/host, registration ID, a "credential configured" boolean status, and redacted connection outcomes.

**Do not:** log \`clientSecret\`, \`OAuth2AccessToken.getTokenValue()\`, refresh tokens, token endpoint responses, Authorization headers, or the full \`Environment\` object.

Note that even though an issuer URI is usually public configuration, it can still reveal internal system topology. Log only what operations require and follow organizational policy.

## 14. Protecting Redirect URIs, Proxies, and Public-Considered Values

A **redirect-uri** or **issuer-uri** config is not a secret, yet tampering with it can break the trust chain of the login flow.

Example:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
~~~

When the Portal deploys behind a proxy:

~~~text
Browser
  -> https://portal.example.test
  -> Trusted TLS reverse proxy
  -> http://portal-service:8080
  -> Spring Boot
~~~

The Portal must generate the public callback:

~~~text
https://portal.example.test/login/oauth2/code/company
~~~

Not the internal callback:

~~~text
http://portal-service:8080/login/oauth2/code/company
~~~

To handle this properly, configure proxy/forwarded headers and register the exact redirect URI at the IdP. **Only trust `X-Forwarded-*` or `Forwarded` headers from proxies that filter and strip headers sent by external clients.** Never use wildcard redirect URIs or redirect values taken arbitrarily from query parameters.

Similarly, **issuer-uri** must specify a trusted IdP, never chosen arbitrarily from the request sender. If the application supports multiple issuers/tenants, enforce an explicit mapping and verification mechanism.

## 15. Secret Rotation: Changing Credentials Without Modifying Source Code

Separating secrets from YAML brings a major benefit: credentials can be rotated independently of business logic changes.

Suppose the current client secret is **S1** and must be replaced with **S2**. Typical workflow:

1. **Prepare at the IdP**: verify whether the provider supports overlapping validity of two secrets, credential versioning, or requires immediate cutover. Provision the new client secret via IdP-approved procedures.
2. **Store S2 in the secret manager**: restrict read/write access; never paste S2 into tickets, chat, Git, or pipeline output.
3. **Update deployment**: new app instances receive S2 via environment injection or mounted secret; perform a rolling restart if needed. Keep a rollback plan matching provider capabilities and security policy.
4. **Observe results**: verify authorization code exchanges, refresh tokens, and watch for **invalid_client** errors; log status only, never credentials.
5. **Revoke S1**: once required instances have switched to S2 and operational checks pass, invalidate the old credential.
6. **Record operations**: rotation date, affected systems, owner, and verification result; never store secret values in the record.

Some Authorization Servers **do not allow two client secrets to be active simultaneously**. In that case, rotation requires coordinated deployment planning and may involve a brief interruption. Do not assume a new secret is automatically reloaded into running Spring Security beans without a restart or explicitly supported config refresh.

If using **private_key_jwt**, rotation shifts to managing keypairs and corresponding public keys/JWKS. If using mTLS client authentication, rotation involves certificates and private keys. Changing an environment variable alone is not enough if the IdP does not yet trust the new credential.

## 16. What to Do If a Secret Has Already Leaked?

When discovering that a client secret or private key appeared in a commit, log, artifact, ticket, or unauthorized location, never just delete that line from the current file and consider the incident closed.

Technical steps in coordination with the IdP owner and operations:

1. **Identify the exposed credential and affected environments**; stop further copying or propagation of the secret value.
2. **Revoke/rotate the credential at the provider** and update secrets on legitimate instances.
3. **Audit exposure locations** such as Git history, image registries, CI logs, and artifacts; remediate/purge per organizational policy. Shared Git history requires a coordinated procedure to avoid data loss or further spread.
4. **Assess impact**: anomalous token exchanges, authorization sessions, still-valid tokens, permissions, and client scopes.
5. **Improve preventive controls**: secret scanning, access controls, isolated environments, log redaction, and rotation processes.

**Masking a secret in a newer file does not invalidate the leaked value.** Remediation must occur at the authority that issues and accepts credentials—namely the IdP or corresponding authentication component.

## 17. Testing and Development Configuration While Upholding Principles

When writing tests for OAuth2 Client, use **test client registrations**, a mock IdP, or test utilities supporting \`oidcLogin()\`. You never need a production confidential client secret for tests.

Example **application-test.yml**:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: portal-test
            client-secret: test-only-placeholder
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]
        provider:
          company:
            authorization-uri: http://localhost:9999/authorize
            token-uri: http://localhost:9999/token
            jwk-set-uri: http://localhost:9999/jwks
            user-info-uri: http://localhost:9999/userinfo
            user-name-attribute: sub
~~~

In this example, **test-only-placeholder** is not a real IdP credential; it only serves a test-controlled mock provider. Never use plain HTTP for a token endpoint outside isolated tests. If using an actual **issuer-uri**, discovery may require the mock server to be running when the Spring context starts.

Test suites can use **Spring Security Test** to mock an OIDC principal without logging in against a real IdP. End-to-end tests should still run with dedicated client registrations and credentials provisioned by the test environment.

A secure development workflow distinguishes:

- **Test fixtures with no real authentication value** may be committed if they contain no sensitive data.
- **Real secrets used for development** must still be protected and remain revocable/rotatable.
- **Never use production client secrets** for testing or debugging on a laptop.

## 18. Deployment Checklist for Provider Configuration

Before promoting Employee Portal to staging/production, application, security, and operations teams can review this table together:

| Question | Expected condition |
|---|---|
| Does the repo contain any real **client-secret** or private key? | No; only property names/placeholders or dummy fixtures |
| Does the provider distinguish client ID and secret? | Yes; client ID identifies, secret authenticates confidential clients |
| How does the secret enter runtime? | Secret manager, variable injection, or mounted file with proper permissions |
| Does each environment have its own client credentials? | Recommended to isolate permissions, callbacks, and rotation |
| Do issuer, endpoints, and redirect URI match the environment? | Match trusted IdP and real callback |
| Is the client authentication method configured accurately? | Matches provider policy and client type |
| Could secrets leak through builds, images, CI, logs, or Actuator? | Observability and configuration channels controlled |
| Are sessions/tokens and client secrets stored separately by lifecycle? | Yes, since authorized clients/tokens are runtime-generated data |
| When a secret rotates, how are old instances handled? | Plan exists for deploy, rollback, revocation, and verification |
| If a credential leaks, where is remediation performed? | Revoke/rotate at IdP, audit impact and leak source |

This is a **deployment operational checklist**, not a replacement for application tests or organizational security policies.

## 19. Practice Scenario

A developer prepares a Portal configuration:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            client-id: employee-portal-prod
            client-secret: s3cr3t-production-value
            authorization-grant-type: authorization_code
            scope: [openid, profile]
        provider:
          company:
            issuer-uri: https://login.example.test/realms/company
~~~

Identify what must change before committing:

1. Is **client-id** a secret? If not, why must editing its value still be controlled?
2. Is **issuer-uri** a secret? What happens if it is changed to another issuer?
3. Which configuration source should **client-secret** be moved to?
4. If **s3cr3t-production-value** already appeared in Git history, is replacing it with a placeholder enough?
5. When running on Kubernetes, how should `ConfigMap` and `Secret` be separated by responsibility?

One way to fix the committed configuration:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            client-id: ${OIDC_CLIENT_ID}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            scope: [openid, profile]
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}
~~~

Then deployment supplies **SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_COMPANY_CLIENT_SECRET** from a secret store. **If the example secret was ever a real credential and got committed, rotating/revoking it according to impact scope is mandatory**; removing it from the newer file only prevents repeating the same leak.

## 20. Practical Conclusion

In **Spring Security OAuth 2.0/OIDC Client**, provider configuration typically contains public values such as **issuer URI, endpoints, client ID, redirect URI, and scopes**, alongside **secret credentials** such as **client secrets or private keys**. They serve different functions and must follow separate management lifecycles.

The recommended design is: **source code and YAML contain only structure, property names, and non-sensitive configuration; secrets are managed outside the repository and injected into the Spring Boot process via a controlled runtime channel.** Meanwhile, **access tokens, refresh tokens, ID Tokens, and `state`/`nonce`/PKCE values** are managed per session or transaction rather than becoming static configuration.

Finally, classifying something as "public" does not mean trusting it blindly. **Issuer, redirect URI, JWKS source, audience, and client authentication method** must be configured and verified consistently with the IdP. When keeping credentials confidential while preserving provider configuration integrity, the application can deploy across environments without code edits to change secrets and maintains clear rotation and incident-response processes.
