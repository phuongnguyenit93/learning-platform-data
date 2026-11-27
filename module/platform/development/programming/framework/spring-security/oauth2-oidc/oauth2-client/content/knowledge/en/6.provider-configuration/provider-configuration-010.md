# 6.10. Application Startup When Discovery or JWKS Is Unavailable

## 1. Practical Question: Can the Application Start When the Identity Provider Is Down?

In a Spring Security OAuth 2.0/OIDC Client application, we usually configure an external **OpenID Provider (OP)** or **Authorization Server** for user login. That provider may publish a **Discovery Document** (metadata about the issuer and endpoints) and **JWKS** (JSON Web Key Set, usually containing public keys to verify ID Token signatures).

What happens if the application is deployed while the login provider is unreachable, DNS fails, or the JWKS endpoint returns HTTP 503? The answer depends on **when Spring Security needs to access each endpoint** and **how `ClientRegistration` is created**.

Distinguish two types of dependencies:

1. **Discovery dependency:** the application needs to fetch metadata to build the OAuth2/OIDC Client configuration. With configuration based on <code>issuer-uri</code>, this step usually happens when initializing <code>ClientRegistrationRepository</code> during application startup.
2. **JWKS dependency:** the application needs keys to verify ID Token signatures. With standard OAuth2 Login/OIDC configuration, keys are usually fetched when verifying a token during an actual login, not necessarily at startup.

Therefore, **a discovery failure can prevent the application from starting**, whereas **a JWKS failure may only cause new OIDC logins to fail** while the HTTP server and other endpoints keep running. This is typical behavior, not a guarantee for every version or custom configuration.

> **Crux:** Determine *when* the application calls the Discovery Document and *when* it fetches JWKS. Do not lump both failures into a single conclusion that "if the IdP is down, the app won't start."

## 2. Roles of Discovery and JWKS in an OIDC Client

### 2.1. Discovery Document

OpenID Connect Discovery tells the Client the OP's metadata. For example, with issuer:

~~~text
https://login.example.org/realms/company
~~~

the OIDC Discovery Document is usually published at:

~~~text
https://login.example.org/realms/company/.well-known/openid-configuration
~~~

An abbreviated JSON response:

~~~json
{
  "issuer": "https://login.example.org/realms/company",
  "authorization_endpoint": "https://login.example.org/realms/company/protocol/openid-connect/auth",
  "token_endpoint": "https://login.example.org/realms/company/protocol/openid-connect/token",
  "jwks_uri": "https://login.example.org/realms/company/protocol/openid-connect/certs",
  "response_types_supported": ["code"],
  "subject_types_supported": ["public"],
  "id_token_signing_alg_values_supported": ["RS256"]
}
~~~

The address and metadata above are illustrative only. Discovery may also publish the UserInfo endpoint, logout endpoint, supported scopes, Client authentication methods, and other details.

Spring Security can read metadata to determine the exact authorization endpoint, token endpoint, JWKS URI, and issuer. Metadata must come from a trusted provider, and the <code>issuer</code> field in JSON must match the issuer expected by the application.

### 2.2. JWKS

JWKS is JSON containing one or more **JWKs (JSON Web Keys)**. For asymmetric signing algorithms such as <code>RS256</code>, JWKS supplies public keys so the Client can verify ID Token signatures:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "kid": "company-key-2026-01",
      "alg": "RS256",
      "n": "base64url-encoded-modulus-placeholder",
      "e": "AQAB"
    }
  ]
}
~~~

This is an **illustrative structure**, not a valid RSA key for verifying tokens. The private key that signs tokens stays on the OP; JWKS normally publishes the public key portion. The <code>kid</code> field helps the Client select the key matching the JWT header. Providers can rotate keys, so the set of public keys changes over time.

An ID Token can only be accepted after the Client verifies the signature, issuer, audience, validity window, and relevant OIDC conditions. Successfully downloading JWKS does not automatically guarantee every token is valid.

### 2.3. Same IdP, Two Different Access Times

~~~mermaid
flowchart TD
    A["Application starts up"] --> B{"ClientRegistration configuration"}
    B -->|issuer-uri / discovery| C["HTTP GET metadata from OP"]
    B -->|Configured static endpoints| D["Build ClientRegistration locally"]
    C --> E{"Discovery available and valid?"}
    E -->|No| F["May fail bean creation / startup"]
    E -->|Yes| D
    D --> G["Application ready to serve HTTP"]
    G --> H["User initiates OIDC Login"]
    H --> I["Authorization Code Flow"]
    I --> J["Receive ID Token"]
    J --> K{"Verification key already in cache?"}
    K -->|Yes| M["Verify token with cached key"]
    K -->|No / needs refresh| L["HTTP GET JWKS URI"]
    L --> N{"JWKS available and has matching key?"}
    N -->|Yes| M
    N -->|No| O["Login fails closed"]
~~~

The diagram depicts the typical case. Custom configurations might proactively fetch JWKS at startup or already hold cached keys beforehand. Network call timing depends on the Spring Security version and the JWT decoder in use.

## 3. Behavior Matrix When an Endpoint Is Unavailable

| Scenario | Can the app start? | Can users log in? | Reason |
|---|---|---|---|
| Discovery unreachable, registration built from <code>issuer-uri</code> at startup | **Likely no** | Does not reach login step | Cannot construct ClientRegistration |
| Discovery unreachable, yet registration built manually with fixed endpoints/issuer | **Usually yes** | Depends on authorization/token/JWKS endpoints | Does not need discovery to build registration |
| JWKS unreachable, registration built successfully | **Usually yes** | May fail when verifying ID Token | Decoder needs key but cannot fetch it |
| JWKS temporarily down, yet valid cached key exists for current <code>kid</code> | **Yes** | **May still succeed** | Does not necessarily need an immediate key fetch |
| JWKS temporarily down and OP just rotated to a new key not in cache | **Likely yes** | Likely fails | No public key matching new <code>kid</code> |
| Authorization endpoint unreachable | Usually yes | Cannot start or finish login | Browser cannot reach authentication page |
| Token endpoint unreachable | Usually yes | Cannot complete new logins | Cannot exchange authorization code for tokens |
| Custom code proactively fetches metadata or JWKS in <code>@Bean</code>/<code>@PostConstruct</code> | **Depends on code** | Undetermined | The application itself added a startup dependency |

The "usually" outcomes describe an **OAuth2 Login Client** with default mechanics. Do not apply this matrix verbatim to Resource Servers or custom decoders.

## 4. Case A: Using `issuer-uri` and Discovery Fails at Startup

### 4.1. Common Configuration

In Spring Boot 3 / Spring Security 6, `ClientRegistration` can be configured as follows:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: company-web-client
            client-secret: replace-with-secret
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          company:
            issuer-uri: https://login.example.org/realms/company
~~~

The client secret value in the example is a placeholder. In real deployments, inject secrets from a secure source; never store real values in repositories.

With <code>issuer-uri</code>, Spring Security/Boot may discover metadata while creating `ClientRegistration`. Information must be fetched over HTTP before finishing repository configuration.

If DNS cannot resolve the domain, the HTTP connection times out, the TLS certificate is invalid, metadata returns 404/503, the response is invalid, or <code>issuer</code> in JSON mismatches the configured issuer, bean creation can fail. As a result, the `ApplicationContext` fails to initialize and the application does not open its serving port normally.

An error chain you might see in logs:

~~~text
Application startup failed
BeanCreationException: Error creating bean 'clientRegistrationRepository'
  ...
  Unable to resolve the Configuration with the provided Issuer
  ...
  ResourceAccessException: I/O error on GET request
  ...
  Connect timed out
~~~

This is only an **illustrative error shape**. Exception classes, messages, and stack trace order depend on Spring Boot/Spring Security version, HTTP client, and network cause. Never rely on a single text phrase to identify the error.

### 4.2. Why Can the Same Configuration Work Yesterday and Fail Today?

An application already running yesterday had `ClientRegistration` created in memory. When deploying a new version or new pod, the bean is recreated and may have to call discovery. Consequently:

- An **already-running** instance can keep handling requests even if the metadata endpoint just lost connectivity.
- A **newly starting** instance can fail if it needs to call discovery right away.
- A rolling deployment can create new instances that never become Ready while old instances are still serving.
- Automatically restarting all instances at once during an IdP outage can widen the blast radius.

This is why you must distinguish a **startup dependency** from a **runtime dependency** and design rollouts accordingly.

### 4.3. How to Observe Discovery Dependencies

When inspecting startup logs, focus on:

1. Whether the <code>ClientRegistrationRepository</code> or <code>ClientRegistration</code> bean is currently being created.
2. Which URL/issuer is used for metadata discovery; whether it points to the right realm, tenant, and environment.
3. The actual error type: DNS, TCP timeout, TLS trust, HTTP status, JSON parsing, or issuer mismatch.
4. Whether proxies, firewalls, and network policies permit the application to reach the OP over HTTPS.
5. Whether any custom code calls <code>ClientRegistrations.fromIssuerLocation(...)</code> or fetches discovery manually at startup.

Keep logs detailed enough for diagnostics; never enable sensitive logging containing client secrets, authorization codes, or tokens in production.

## 5. Case B: JWKS Is Unavailable

### 5.1. When Does Spring Security Need JWKS?

In a typical OIDC Authorization Code Flow, the Client receives an **ID Token** after exchanging the code at the token endpoint. If the ID Token is signed with an asymmetric algorithm like RS256, the Client needs the matching public key to verify the signature. <code>jwks_uri</code> is obtained from metadata or provider configuration.

In Spring Security OAuth2 Login, decoder creation and JWKS access normally happen **when an ID Token needs to be decoded/verified**, i.e., during an actual login flow, rather than forcing all keys to load at startup. Customizations in the application can alter this behavior.

Example ID Token header:

~~~json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "company-key-2026-01"
}
~~~

The Client must find a valid public key matching <code>kid</code> in the JWKS of the **trusted issuer**. If no matching cached key exists and the JWKS endpoint fails, the Client cannot verify the signature and must **reject the login**.

### 5.2. How Do Uncached and Cached States Differ?

| State | JWKS endpoint is unreachable | Expected outcome |
|---|---|---|
| First ID Token verification, no cached keys yet | Cannot fetch key | Login fails |
| Matching key already in cache and still usable per decoder policy | Network request may not be needed | Login may succeed |
| OP signs with a new <code>kid</code> not yet in cache | Client needs to fetch/refresh JWKS | Login likely fails |
| Cached key expired or needs refresh | Decoder may need to fetch JWKS | Login depends on cache policy and connectivity |

Do not assume **JWKS caching always saves login**. Caches have TTLs, refresh policies, and limits of their own. If the OP rotates keys while JWKS is down, the cache will not hold the new key. If stale cache entries are unacceptable, the Client must fail closed.

### 5.3. When JWKS Is Broken, What Still Works?

- The application **can remain running** and respond to endpoints that do not require a fresh login.
- Previously authenticated user sessions can continue under the application's session mechanism, as long as the session remains valid and business operations do not need fresh token verification.
- Some downstream APIs may keep working with existing valid tokens, depending on how the application manages authorized clients and refresh tokens.
- New **OIDC Login** flows will fail at the ID Token verification step.

Do not equate "new logins are failing" with "every existing request is failing." At the same time, do not assume existing sessions work indefinitely: expiration, logout, token refresh, and system policies still apply.

## 6. Approach 1: Keep Dynamic Discovery and Handle the Startup Dependency

This option fits when a team always wants metadata fetched from the OP when creating registrations and accepts depending on OP availability during startup.

Important operational practices:

- Ensure the exact issuer, DNS/TLS, and egress to the discovery endpoint work in the deployment environment.
- Use **finite timeouts** so startup never hangs indefinitely. When customizing the HTTP client for discovery, choose sensible connection and read timeouts.
- If retrying, cap attempts, use appropriate backoff, and avoid all instances hammering at once. Infinite startup retries mask real configuration errors.
- In multi-instance rollouts, preserve serving capacity from running instances while new instances cannot start; design readiness probes and rolling updates properly.
- Monitor **IdP/metadata endpoint reachability** separately to catch issues before deploying.
- Only put startup beans in fail-fast mode if lacking provider configuration truly prevents the application from meeting its security goals.

For simple configurations based on Boot properties, you do not necessarily need to write custom retries inside every bean. If specialized timeouts or retry strategies are needed, check the official customization APIs/mechanisms of your Spring Security/HTTP client version, since how discovery is performed can vary by version.

## 7. Approach 2: Build `ClientRegistration` from Static Endpoints to Avoid Startup Discovery

If the operational requirement is that **the application must start even when the Discovery Document is failing**, you can construct <code>ClientRegistration</code> from previously verified endpoints and issuer. Then the bean does not need to call discovery.

This comes with a trade-off: the team must **maintain endpoint/issuer configuration** when the OP changes and still handle JWKS at runtime. Never use manual metadata from an untrusted source.

### 7.1. Dedicated Properties for Static Configuration

Example <code>application.yml</code>:

~~~yaml
app:
  oidc:
    issuer-uri: https://login.example.org/realms/company
    authorization-uri: https://login.example.org/realms/company/protocol/openid-connect/auth
    token-uri: https://login.example.org/realms/company/protocol/openid-connect/token
    jwk-set-uri: https://login.example.org/realms/company/protocol/openid-connect/certs
    client-id: replace-with-client-id
    client-secret: replace-with-secret-from-secure-config
~~~

The <code>client-id</code> and <code>client-secret</code> values here are placeholders. In production, use a secret manager or environment variables and never commit real secrets. Endpoints must be official values verified from OP configuration.

### 7.2. Java Bean Without Calling Discovery

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

@Configuration
public class OAuth2ClientConfig {

    @Bean
    ClientRegistrationRepository clientRegistrationRepository(Environment env) {
        ClientRegistration company = ClientRegistration
            .withRegistrationId("company")
            .clientId(env.getRequiredProperty("app.oidc.client-id"))
            .clientSecret(env.getRequiredProperty("app.oidc.client-secret"))
            .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
            .scope("openid", "profile")
            .issuerUri(env.getRequiredProperty("app.oidc.issuer-uri"))
            .authorizationUri(env.getRequiredProperty("app.oidc.authorization-uri"))
            .tokenUri(env.getRequiredProperty("app.oidc.token-uri"))
            .jwkSetUri(env.getRequiredProperty("app.oidc.jwk-set-uri"))
            .clientName("Company SSO")
            .build();

        return new InMemoryClientRegistrationRepository(company);
    }
}
~~~

The crucial difference: the example uses <code>ClientRegistration.withRegistrationId(...)</code> and **does not** call <code>ClientRegistrations.fromIssuerLocation(...)</code>. Consequently, creating this bean does not access the Discovery Document.

<code>issuerUri(...)</code> is still set explicitly so the application has the issuer information needed for OIDC validation. Do not drop the issuer just to dodge network errors. The <code>jwks_uri</code> path still points to the real public key endpoint: when verifying an ID Token, the decoder may have to call that endpoint.

The builder APIs illustrate Spring Security 6; in real projects, use the APIs and OIDC configuration requirements of the deployed version.

### 7.3. Enabling OAuth2 Login

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Clients visit <code>/oauth2/authorization/company</code> to initiate the flow. When the OP is healthy and tokens can be verified, the default callback is <code>/login/oauth2/code/company</code>.

**No additional auto-configured <code>ClientRegistrationRepository</code> is needed** once the Java bean above serves as the official registration source. Spring Boot normally backs off in favor of an application-supplied bean.

### 7.4. Limitations of Static Configuration

Manual configuration removes the **discovery dependency when building `ClientRegistration`**, but does not guarantee login works when:

- The authorization endpoint is down: the browser cannot authenticate.
- The token endpoint is down: the Client cannot exchange the code for ID Token/access token.
- The JWKS endpoint is down without a valid cached key: the Client cannot verify ID Tokens.
- The OP changes endpoints, issuer, authentication methods, or rotates keys before Client configuration catches up.

Maintain a periodic process to cross-check official metadata and update configuration when the OP changes. Never accept arbitrary issuers or keys merely to "get the app up."

## 8. Can JWKS Be Cached or Distributed Differently?

**Yes**, though that is a dedicated architectural decision balancing availability against signature verification safety.

### 8.1. JWKS Caching in the Decoder

Modern JWT libraries usually cache keys/JWKS after a successful fetch to avoid calling the IdP on every token. Benefits:

- Reduces latency and request load on the JWKS endpoint.
- Allows verifications to keep working during brief JWKS outages if the needed key remains valid in cache.
- Supports key rotation when the library refreshes JWKS per its built-in rules.

However, do not assume every decoder shares the exact same TTL, cache strategy, or behavior when encountering a new <code>kid</code>. Check the specific Spring Security/Nimbus APIs and configuration in use. An in-memory cache in one instance is also not automatically shared with other instances.

### 8.2. Packaging Public Keys or an Internal JWKS Mirror

In certain isolated environments, operations teams may supply a managed set of public keys/JWKS or an internal JWKS mirror. This can reduce direct runtime network dependency on the IdP during verification, while introducing responsibilities:

1. Obtain keys from the official OP source and verify source integrity.
2. Update keys **before, during, and after** key rotation according to a process agreed with the OP.
3. Never accept arbitrary keys or JWKS from another issuer.
4. Bound how long old keys remain usable and handle key revocation.
5. Design alerts and recovery procedures if the internal keyset falls out of sync.

Never copy a single old public key and treat it as a permanent fix. If the OP switches to a new <code>kid</code>, new tokens cannot be verified until the local keyset is updated. If a key is compromised/revoked, using stale keys indefinitely weakens security.

### 8.3. Fallbacks That Must Never Be Used

- Disabling ID Token signature checks or accepting <code>alg=none</code> arbitrarily.
- Skipping <code>iss</code> or <code>aud</code> checks to accept tokens from another provider.
- Trusting a public key or JWKS URL self-declared inside an unverified JWT.
- Trying to use an access token as an ID Token instead of verifying OIDC identity.
- Creating a "temporary login mode" that accepts any user whenever the IdP is down.

When a token cannot be verified per policy, new logins must **fail closed**: reject the login and return an appropriate message, while keeping unrelated functionality available if the architecture allows.

## 9. Readiness, Liveness, and Operational Behavior on Kubernetes

A JWKS or OIDC Login failure does not necessarily mean the entire application is unfit to handle all requests. Therefore distinguish:

| Health check type | Question answered | Guidance |
|---|---|---|
| **Liveness** | Is the application process alive and able to keep running? | Avoid hard-coupling to external JWKS/Discovery status to prevent restart storms |
| **Readiness** | Is this instance eligible to receive traffic per service contract? | Depends on business requirements; do not auto-fail solely for an OP outage if other endpoints can still serve |
| **Dependency monitor** | Are OP discovery, authorization, token, and JWKS available? | Monitor/alert separately so operators see the exact failure |
| **Login synthetic check** | Does the login flow actually complete? | Run with safe test accounts/scenarios, rate-controlled and without exposing credentials |

For example, in an application with many endpoints that do not require login, marking liveness "down" whenever JWKS returns 503 causes Kubernetes to endlessly restart pods that could otherwise serve traffic. Conversely, for an application where every feature strictly requires new logins, readiness policy may need to be stricter. Decisions must follow **the service's availability contract**, not a one-size-fits-all default.

When deployments use discovery at initialization, account for new pods failing while old pods keep running:

~~~text
IdP experiences brief outage
    ├─ Old pod: already has ClientRegistration → can keep serving
    ├─ New pod: needs discovery at startup → may fail to initialize
    └─ Rollout: insufficient capacity if pods are replaced too quickly
~~~

Rolling updates should preserve enough serving instances, gate traffic with readiness on new instances, and never tear down existing capacity before verifying replacement instances are healthy. If metadata is unavailable at startup, log the error clearly and let the platform pace rollout retries under appropriate policy rather than hammering the OP endlessly.

## 10. Designing Timeouts, Retries, and Error Handling in the Right Places

### 10.1. Finite Timeouts

All network requests to discovery, JWKS, and token endpoints need clear timeouts, especially in deployments with proxies or unstable links.

Distinguish:

- **Connection timeout:** unable to establish a connection to the OP.
- **Read/response timeout:** connection established, yet the OP responds too slowly.
- **TLS failure:** certificate or handshake error; retries normally cannot fix broken trust settings.
- **HTTP 4xx/5xx:** only some errors are transient; 404/401 and issuer mismatches are usually configuration issues.

Never put infinite retries inside startup beans, as that hangs startup, obscures observability, and makes multiple instances simultaneously flood a struggling endpoint.

### 10.2. Selective Retries

| Operation | Should you retry? | Notes |
|---|---|---|
| Fetching discovery metadata on network/5xx errors | Possible, strictly bounded | Use backoff and timeouts; do not mask issuer mismatch errors |
| Fetching JWKS on network/5xx errors | Possible per decoder policy | Never use keys from an untrusted issuer |
| Fetching JWKS when <code>kid</code> is missing | Possible refresh per library mechanics | Avoid infinite refreshes and check key rotation |
| Token request exchanging authorization code | **With extreme caution** | Codes are normally single-use; uncontrolled retries can cause errors or state confusion |
| User login in browser | Allowed to restart flow | Never reuse an expired or already-consumed authorization code |

When a code-exchange request was already processed by the OP yet the response was lost, the Client cannot easily tell if the code was consumed. Safe recovery usually means restarting the Authorization Code Flow for the user instead of replaying the same code repeatedly.

### 10.3. Returning Clear Errors to Users

When the OP or JWKS fails, the login page can show a neutral message:

> Unable to complete sign-in because the authentication service is temporarily unavailable. Please try again later.

Never expose stack traces, tokens, client secrets, internal hostnames, or sensitive configuration on error pages. Server-side logs should capture a correlation ID, error category, timestamp, and registration/provider name to aid investigation.

## 11. Distinguishing OAuth2 Client and Resource Server

This is a very common source of confusion in Spring Security.

**OAuth2/OIDC Client**:

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          company:
            issuer-uri: https://login.example.org/realms/company
~~~

This property lets **ClientRegistration** discover metadata for login/authorization flows. A discovery failure when building the registration can block startup.

**OAuth2 Resource Server**:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.org/realms/company
~~~

This property serves **verifying bearer JWTs on incoming API requests**. Depending on version and how <code>JwtDecoder</code> is created, Resource Server may discover metadata at initialization or support lazy initialization. Adding <code>jwk-set-uri</code> on Resource Server is commonly used to avoid startup discovery where supported by Spring Security, while still enforcing issuer validation when <code>issuer-uri</code> is present.

Do not infer OAuth2 Login Client behavior from Resource Server documentation or examples. The two roles use different configuration classes, lifecycles, and token-processing paths, even when both point to the same OP/JWKS.

An application having both <code>oauth2Login()</code> and JWT-protected APIs may have to manage **two** separate configurations. When diagnosing errors, identify which bean is initializing and which flow is verifying tokens.

## 12. Scenarios and Investigation Steps

### Scenario A — Startup Fails Because Discovery Document Returns 503

The application declares <code>spring.security.oauth2.client.provider.company.issuer-uri</code>, and during deployment the IdP returns HTTP 503 at the well-known endpoint. Startup halts while building `ClientRegistrationRepository`.

**Explanation:** The client needs metadata to create the registration, so it depends on discovery during startup.

**Options:** restore IdP connectivity/availability; improve timeouts and rollout strategy; or deliberately switch to a `ClientRegistration` built from verified static endpoints if business requirements demand starting independently of discovery. Never change the issuer arbitrarily to another realm just to get HTTP 200.

### Scenario B — App Starts, Yet OIDC Login Returns an Error

Application HTTP endpoints still respond. Users are sent to the IdP, sign in, the callback receives code and tokens, and then Spring Security fails with an error about being unable to fetch JWKS.

**Explanation:** Startup completed, yet ID Token signature verification requires a public key that the decoder does not have yet. Validation cannot be skipped.

**What to check:** official JWKS URI, DNS/TLS/HTTP status, <code>kid</code> in the token header, signing algorithm, and key rotation status. Without a valid key, fail the login and track the incident.

### Scenario C — Only New Pods Fail After Restart

IdP discovery is disrupted. Older running pods continue serving requests that do not need new logins, while new pods fail bean creation.

**Explanation:** Old instances already hold `ClientRegistration` in memory; new instances must run discovery again. Readiness/rollout policies must keep old pods running until replacement instances are ready.

### Scenario D — JWKS Cache Holds Old Key While IdP Just Rotated Keys

New ID Tokens have a <code>kid</code> not yet in cache. The JWKS endpoint also happens to be down.

**Explanation:** There is no public key to verify the new token. "Allowing the old key to verify the new token's signature" is wrong. Wait for JWKS recovery/valid keyset sync; never disable verification.

### Scenario E — Set `jwk-set-uri`, Yet Startup Still Fails

The application configures both <code>issuer-uri</code> and <code>jwk-set-uri</code> under **OAuth2 Client provider properties** expecting no startup discovery, yet still sees a `ClientRegistration` error.

**Explanation:** Having a JWKS URI does not necessarily cause Spring Boot to skip discovery when building a registration via issuer. This is a common mix-up with certain Resource Server settings.

**How to handle:** inspect the component creating registrations; if startup without discovery is required, build `ClientRegistration` in Java from all verified endpoints and issuer as in Section 7, or use an equivalent verified manual configuration mechanism.

## 13. Stage-by-Stage Diagnostic Flowchart

~~~mermaid
flowchart TD
    A["Application encounters IdP-related error"] --> B{"At which stage did the error occur?"}
    B -->|Before HTTP app is ready| C["Check ClientRegistrationRepository creation"]
    C --> D{"Does it call issuer discovery?"}
    D -->|Yes| E["Check DNS/TLS/HTTP, JSON, and issuer match"]
    D -->|No| F["Check custom beans, properties, and static endpoints"]
    B -->|When clicking login| G["Check authorization endpoint and browser redirect"]
    B -->|On callback / code exchange| H["Check token endpoint, client auth, PKCE, and state"]
    B -->|When verifying ID Token| I["Check JWKS, kid, alg, iss, aud, exp"]
    E --> J["Fix dependency/config and observe restart"]
    F --> J
    G --> K["Restore standard OAuth/OIDC flow"]
    H --> K
    I --> K
~~~

For each incident, record:

1. **Failure stage:** startup, login initiation, token exchange, or ID Token validation.
2. **Responsible bean or class:** `ClientRegistrationRepository`, authorization request resolver, token client, or JWT decoder.
3. **Exact provider:** registration ID, issuer, and environment. Never accidentally use a staging issuer in production.
4. **Network path:** DNS, proxy, firewall/egress, TLS, HTTP status, and timeouts.
5. **Cache/state:** whether metadata was fetched; whether JWKS keys are available; whether <code>kid</code> changed.
6. **Blast radius:** complete startup failure or only new login failures; number of affected instances; existing sessions.

Structured diagnostics separate real connectivity outages from misconfigured issuers, redirect URIs, or client authentication.

## 14. Practice in a Development Environment

### Exercise 1 — Starting Up When Discovery Is Unreachable

**Preparation:** a test OIDC IdP with a reachable issuer, a Spring Boot OAuth2 Login application, and an environment capable of simulating network failures.

1. Start from the <code>issuer-uri</code> configuration in Section 4; run the app while the IdP is healthy.
2. In the test environment, block connectivity to the Discovery Document or return HTTP 503 from a mock endpoint before starting a new app instance.
3. Observe the `ClientRegistration` creation error and record the network cause (without logging credentials).
4. Switch to the manual Java configuration in Section 7 using exact verified endpoints.
5. Try restarting while the Discovery Document is still failing.
6. Distinguish startup outcomes from login outcomes as other endpoints remain up or go down.

**Takeaway:** building static configuration removes the discovery dependency at startup; it does not make login completely independent of the IdP.

### Exercise 2 — When JWKS Is Unavailable

1. Start the application while metadata is valid.
2. In the test environment, block or simulate failure only on the JWKS endpoint while keeping authorization/token endpoints operational.
3. Perform a new login requiring ID Token verification.
4. Observe both cached and uncached cases. If the library skips calling JWKS due to cache, use a fresh instance or isolated test environment to observe the initial key fetch.
5. Restore the endpoint and start a **new login flow**; never reuse an already-used or expired authorization code.

**Takeaway:** ID Token signatures must still be verified; a JWKS failure is a runtime login error, not necessarily a startup error.

### Exercise 3 — Analyzing Architectural Trade-Offs

An internal application serves a logged-in dashboard and several public APIs. The SSO provider has occasional brief downtime, yet the company requires the dashboard to keep serving already-authenticated sessions while the login system is temporarily down.

Compare:

| Option | Advantages | Cost/responsibility |
|---|---|---|
| Startup issuer discovery | Minimal hard-coded endpoints; fetches metadata from OP | New instances depend on discovery availability |
| Verified static ClientRegistration | Can start when discovery is down | Must keep endpoints, issuer, and auth method updated |
| Library-level JWKS caching | Reduces JWKS dependency per login | Cache misses or key rotation still require fetching keys |
| Internal JWKS mirror/keyset | Can reduce direct IdP dependency during verification | Must manage integrity, cache, key rotation, and key revocation |
| Separate IdP monitoring and rollout design | Keeps impact clear; avoids restart storms | Requires metrics, alerts, and operational runbooks |

**Hint:** first clarify the exact availability goal: must the app **start**, **serve already-logged-in users**, or **allow new logins** while the IdP is unreachable? Those three goals differ and require different solutions.

## 15. Knowledge Summary

- **Discovery Document** helps build `ClientRegistration` from an issuer. With the common <code>issuer-uri</code> configuration in Spring Security OAuth2 Client, if discovery is unavailable when initializing the repository, **startup can fail**.
- **JWKS** is used to verify ID Token signatures. In normal OIDC Login, key fetching usually occurs when verifying tokens, so **JWKS failures normally affect new logins** rather than blocking startup.
- If startup must succeed while discovery is down, you can **build `ClientRegistration` manually** from trusted issuer/authorization/token/JWKS endpoints. This still depends on the OP during actual logins.
- **JWKS caching** can bridge short outages when a matching key is cached, yet does not guarantee working with new keys or expired caches. Never accept unverified tokens to increase availability.
- Clearly distinguish **startup, login, token exchange, and ID Token validation** as four separate stages when debugging. Readiness, liveness, rollouts, and dependency monitoring must reflect each failure's real impact.
- **OAuth2 Client and Resource Server** have different configurations, discovery timing, and decoder lifecycles; never blindly apply Resource Server advice to an OIDC Login Client.

### Standards and APIs to Reference

- **OpenID Connect Discovery 1.0**: issuer, Provider Configuration, and metadata details.
- **OpenID Connect Core 1.0**: ID Token, signatures, issuer, audience, and validation steps.
- **RFC 7517 — JSON Web Key (JWK)**: structure of public keys in JWKS.
- **RFC 8414 — OAuth 2.0 Authorization Server Metadata**: metadata endpoints and issuer in OAuth 2.0.
- **Spring Security Reference — OAuth2 Login, OAuth2 Client, JWT Resource Server**: configuring `ClientRegistration`, issuer, JWKS, and decoders.
- **Spring Security API — `ClientRegistration`, `ClientRegistrations`, `OidcIdTokenDecoderFactory`, `NimbusJwtDecoder`**: extension points for creating registrations and verifying JWTs.
- **Spring Boot Reference — OAuth2 Client auto-configuration and Actuator health probes**: how Boot builds Client configuration and readiness/liveness concepts.
