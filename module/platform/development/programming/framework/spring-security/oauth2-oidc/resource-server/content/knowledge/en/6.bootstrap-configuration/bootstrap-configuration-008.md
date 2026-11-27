# Separating URLs, Audiences, and Credentials by Environment

When deploying a **Spring Security OAuth 2.0 / OIDC Resource Server**, an application typically runs across multiple environments such as **local**, **development (dev)**, **staging**, and **production (prod)**. All environments may run the exact same source code while connecting to different Authorization Servers, APIs, audiences, and secret stores. If these values are hardcoded or mixed up across environments, an API can end up rejecting every valid request or accepting tokens issued for the wrong target system.

Therefore, an essential bootstrap step is **separating environment-dependent values from security logic**:

- **URLs/URIs** specify which endpoints the application calls and where to fetch metadata or verification keys.
- **Issuer and audience** identify where a token came from and whether it is intended for this API.
- **Credentials/secrets** specify how a service proves its identity to another system and how those secrets are supplied, stored, and rotated.

These three configuration groups serve distinct purposes; you cannot replace an audience with an API URL or use a `client-secret` as a way to validate JWTs. This lesson uses **Orders API** as the Resource Server, **Shop Web** as the OAuth2 Client, and **Identity Server** as the Authorization Server.

## 1. Why Separate by Environment?

Suppose a system has three independent environments:

| Component / value | Dev | Staging | Production |
| --- | --- | --- | --- |
| Orders API base URL | `https://orders.dev.example.test` | `https://orders.staging.example.test` | `https://orders.example.com` |
| Trusted issuer | `https://id.dev.example.test/realms/shop` | `https://id.staging.example.test/realms/shop` | `https://login.example.com/realms/shop` |
| Audience required by Orders API | `orders-api-dev` | `orders-api-staging` | `orders-api` |
| JWKS endpoint | Dev issuer JWKS URL | Staging issuer JWKS URL | Production issuer JWKS URL |
| Client registration / credentials | Dedicated dev set | Dedicated staging set | Dedicated production set |
| Data and policies | Test data | Pre-production data | Real data |

The URLs above are **illustrative addresses**, not endpoints of any specific provider. Audience values are also illustrative contract identifiers: another Authorization Server might use a URI like `https://orders.example.com` instead of the string `orders-api`.

When separated this way, a dev access token will not be trusted by production simply because both environments use RS256 or share `scope = orders.read`. Production must validate its own **issuer, signature, audience, timestamps, and policies**.

### Three Classic Configuration Mistakes

1. **Dev API accidentally uses the production issuer:** Developers cannot call the API with dev tokens due to issuer mismatch; worse, dev could accidentally accept production tokens if trust config is wrong.
2. **Right issuer, audience copied from another environment:** Staging tokens are issued for `orders-api-staging`, yet the API expects `orders-api` and returns 401 despite valid signatures.
3. **Reusing client secrets across environments:** Production secrets leak into dev configs, logs, or personal laptops; the blast radius of a secret leak extends beyond testing.

These issues must never be fixed by skipping `iss`/`aud` checks or disabling token verification; fix **the configuration source** and token issuance contract.

## 2. Distinguishing Each Address and Identifier Type

Looking at an OAuth 2.0 application, many URIs look similar yet carry distinct responsibilities:

| Value | What is it for? | Who uses it? | Must it be secret? |
| --- | --- | --- | --- |
| **API base URL** | Address Clients call, e.g., `https://orders.example.com` | OAuth2 Client, gateway, callers | No |
| **Issuer URI** | Issuer identifier, matched against `iss` claim | Resource Server; OAuth2/OIDC Client per flow | No |
| **Authorization endpoint** | Where the Client sends users for authentication/consent | Interactive Client facing users | No |
| **Token endpoint** | Where the Client exchanges codes or uses grants for tokens | OAuth2 Client | No; though credentials sent here may be secret |
| **JWKS URI** | Where the Resource Server fetches public keys to verify JWS/JWT | Resource Server and signature verifiers | No; **public** keys are not private keys |
| **Introspection URI** | Where the API queries opaque token status | Resource Server using introspection | No; though credentials calling it are typically secret |
| **Audience (`aud`)** | Target recipient identifier for an access token | Issued by Authorization Server; validated by Resource Server; Clients may request target resource | No |
| **Client ID** | Client identifier registered with the Authorization Server | OAuth2 Client and Authorization Server | Typically no |
| **Client secret** | Confidential Client credential | Client authenticating to the Authorization Server | **Yes** |
| **Private signing key** | Private key for the Authorization Server to sign tokens | Authorization Server or authorized signing service | **Yes, highly sensitive** |

**The issuer is not necessarily the login page URL**, and `aud` is not necessarily a URL you can open in a browser. Each value must match the exact convention published/issued by the Authorization Server.

### 2.1. Issuer URI Matching the `iss` Claim

Illustrative JWT token:

~~~json
{
  "iss": "https://login.example.com/realms/shop",
  "sub": "user-481",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1893459600
}
~~~

Production Orders API must trust only the issuer configured by the organization. The `iss` value is an exact semantic identifier, not a "same domain is close enough" match.

In Spring Security, the usual property is:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
~~~

When using issuer discovery, the Resource Server locates metadata and the JWKS location via supported rules. The configured issuer must match the actual issuer; never arbitrarily alter the realm path, add/remove trailing segments, or rewrite the host through a proxy and assume it counts as the same issuer.

### 2.2. JWKS URI for Signature Verification

Example Identity Provider serving JWKS at:

~~~text
https://login.example.com/realms/shop/protocol/openid-connect/certs
~~~

This is **one illustrative path pattern**, not a universal URL across all Authorization Servers. Obtain the JWKS URI from your issuer's metadata or integration documentation.

The Resource Server uses the matching JWK to verify the JWS signature. The `kid` header parameter helps pick a public key from the trusted key set; the API must never fetch keys from an arbitrary URL supplied inside an unverified token and trust it.

If configuring **both** `issuer-uri` and `jwk-set-uri`, you explicitly specify JWKS to reduce startup reliance on metadata discovery while preserving issuer claim checks. Ensure both belong to the **same** trusted provider.

### 2.3. Audience Is a Logical Identifier Issued by the Issuer

Suppose two APIs share an Identity Server:

~~~text
Orders API: audience = orders-api
Billing API: audience = billing-api
~~~

An access token with `aud = billing-api` **must not** be accepted by Orders API, even from the same issuer and signing key pair. If the system uses resource URLs as audiences, the API must match the exact contracted URL rather than inferring it from incoming request hostnames.

In some systems, Clients request a target audience via a **resource indicator** or provider parameter. **The Client only requests**; the Authorization Server decides the audience written into the token, and the Resource Server enforces the actual value.

## 3. Designing Configuration: Same Codebase, Different Values

In Spring Boot, keep `SecurityFilterChain` and JWT validation logic in shared code while placing environment values into **externalized configuration**: environment variables, deployment config systems, Spring profiles, or secret managers.

Example minimal variable set for Orders API accepting JWTs:

| Environment variable | Role | Production example |
| --- | --- | --- |
| `SPRING_PROFILES_ACTIVE` | Selects Spring config profile | `prod` |
| `OAUTH_ISSUER_URI` | Trusted issuer for the API | `https://login.example.com/realms/shop` |
| `OAUTH_JWKS_URI` | JWKS used to verify signatures | `https://login.example.com/realms/shop/protocol/openid-connect/certs` |
| `OAUTH_API_AUDIENCE` | API audience | `orders-api` |
| `ORDERS_PUBLIC_BASE_URL` | Public base URL advertised to Clients, if needed | `https://orders.example.com` |

**There is no `OAUTH_CLIENT_SECRET` in this minimal list** because a JWT Resource Server verifies tokens using **public keys**. Secrets are needed for other roles, such as an OAuth2 Client or a Resource Server using opaque-token introspection.

### 3.1. Option A: Using Environment Variables for Every Variable Value

Create `src/main/resources/application.yml` with placeholders:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${OAUTH_ISSUER_URI}
          jwk-set-uri: ${OAUTH_JWKS_URI}

app:
  security:
    expected-audience: ${OAUTH_API_AUDIENCE}
  public-base-url: ${ORDERS_PUBLIC_BASE_URL}
~~~

Spring Boot resolves placeholders from environment variables. Placeholders **without defaults** are helpful for mandatory values: a deployment missing required info fails noticeably when the property is read rather than silently falling back to a localhost or production URL.

Three environments supply different values:

~~~text
# DEV
OAUTH_ISSUER_URI=https://id.dev.example.test/realms/shop
OAUTH_JWKS_URI=https://id.dev.example.test/realms/shop/protocol/openid-connect/certs
OAUTH_API_AUDIENCE=orders-api-dev
ORDERS_PUBLIC_BASE_URL=https://orders.dev.example.test

# STAGING
OAUTH_ISSUER_URI=https://id.staging.example.test/realms/shop
OAUTH_JWKS_URI=https://id.staging.example.test/realms/shop/protocol/openid-connect/certs
OAUTH_API_AUDIENCE=orders-api-staging
ORDERS_PUBLIC_BASE_URL=https://orders.staging.example.test

# PRODUCTION
OAUTH_ISSUER_URI=https://login.example.com/realms/shop
OAUTH_JWKS_URI=https://login.example.com/realms/shop/protocol/openid-connect/certs
OAUTH_API_AUDIENCE=orders-api
ORDERS_PUBLIC_BASE_URL=https://orders.example.com
~~~

This block is an **illustrative table of variable names and values**, not a single `.env` file to load verbatim into every environment. CI/CD or your runtime platform must inject **only** the value set belonging to the target environment.

Pros: identical build artifacts across environments, no rebuild needed just to change endpoints or audiences. Cons: the deployment platform must reliably distribute, govern, and validate configuration.

### 3.2. Option B: Spring Profiles for Public Settings

When URLs/issuers/audiences are stable per environment, **non-secret** values can live in profile-specific files:

`src/main/resources/application-dev.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.dev.example.test/realms/shop
          jwk-set-uri: https://id.dev.example.test/realms/shop/protocol/openid-connect/certs

app:
  security:
    expected-audience: orders-api-dev
~~~

`src/main/resources/application-prod.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          jwk-set-uri: https://login.example.com/realms/shop/protocol/openid-connect/certs

app:
  security:
    expected-audience: orders-api
~~~

When running production, the deployment platform sets:

~~~text
SPRING_PROFILES_ACTIVE=prod
~~~

Dev uses `SPRING_PROFILES_ACTIVE=dev`; staging has a matching `application-staging.yml`. Profile files here hold **public addresses and identifiers**, never client secrets or private signing keys. Secrets always come from the environment's secret management system.

**Selecting a profile does not automatically create a security boundary.** If production starts with the dev profile or a bad config override, the app can point to the wrong issuer. Deployments must control effective values, edit permissions, and startup assertions.

### 3.3. When to Prefer Which Approach?

| Criterion | Externalized environment variables | Spring profile files |
| --- | --- | --- |
| Identical artifact across environments | Straightforward | Possible if all profiles are packaged together |
| Change endpoint/audience without rebuild | Yes | Requires external override or rebuild if editing packaged files |
| Change review via code review | Config lives in deployment/IaC repo | Public values reviewed alongside source code |
| Secrets management | Pairs with secret manager/Kubernetes Secret/CI secrets | Still needs secret manager; **never commit secrets to profiles** |
| Main risk | Missing/wrong runtime variables | Selecting wrong profile or accidental override |

Both can be combined: keep property names and shared structure in code; store stable public URLs in profiles; allow deployment-time overrides via environment variables. What matters is having a **single controlled source of truth per environment**, with checks to catch unintended overrides.

## 4. Configuring a JWT Resource Server to Validate Environment-Specific Audiences

**Enabling Resource Server does not mean every access token from the same issuer has the right audience.** Explicitly define the audience Orders API accepts and enforce it during token verification.

Example using **Spring Boot 3 and Spring Security 6**, reading three values from `application.yml` as in section 3.1:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Example `JwtDecoder` with `NimbusJwtDecoder` and validators:

~~~java
import org.springframework.beans.factory.annotation.Value;
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
public class ApiJwtConfiguration {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${spring.security.oauth2.resourceserver.jwt.issuer-uri}")
            String issuer,
            @Value("${spring.security.oauth2.resourceserver.jwt.jwk-set-uri}")
            String jwksUri,
            @Value("${app.security.expected-audience}")
            String expectedAudience) {

        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withJwkSetUri(jwksUri).build();

        // Keep default checks for expiration, validity window, and issuer.
        OAuth2TokenValidator<Jwt> standard =
                JwtValidators.createDefaultWithIssuer(issuer);

        // Reject tokens issued by the right issuer for a different API.
        OAuth2TokenValidator<Jwt> audience = jwt ->
                jwt.getAudience().contains(expectedAudience)
                        ? OAuth2TokenValidatorResult.success()
                        : OAuth2TokenValidatorResult.failure(
                                new OAuth2Error(
                                        "invalid_token",
                                        "Access token has an unexpected audience",
                                        null));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        standard,
                        audience));

        return decoder;
    }
}
~~~

This code highlights **reading audience from environment config** rather than hardcoding `orders-api` in Java. `JwtValidators.createDefaultWithIssuer(issuer)` preserves default timestamp checks and adds issuer verification. Signatures are verified against trusted JWKS before the JWT is accepted.

When declaring your own `JwtDecoder` bean, Spring Boot may stop creating the property-driven default decoder. Ensure **signature, algorithm, issuer, expiration, audience, and token profile rules** are all enforced. If a token profile imposes extra requirements on `typ`, Client, or subject resolution, configure matching validators.

### 4.1. Shared SecurityFilterChain Across All Environments

Endpoint authorization rules should not vary arbitrarily across dev/staging/prod:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

This example assumes `/api/**` is a **Bearer-token-only** REST API with no cookie authentication, hence disabling CSRF on this filter chain and enforcing stateless sessions. If the app also serves a web UI using session cookies or another auth mechanism, configure appropriate CSRF/filter chains.

Spring Security normally maps `scope` or `scp` claims into `SCOPE_`-prefixed authorities, e.g. `scope = "orders.read"` becomes `SCOPE_orders.read`. Enforcing permissions on **specific orders** (owner, tenant, status) still belongs in the business layer; having the right scope alone does not grant access to every record.

### 4.2. What Happens When Switching Environments?

With the exact same Java code:

- **Dev:** Reads dev issuer, dev JWKS, and `expected-audience = orders-api-dev`.
- **Staging:** Reads staging issuer, staging JWKS, and `expected-audience = orders-api-staging`.
- **Prod:** Reads production issuer, production JWKS, and `expected-audience = orders-api`.

If a dev token is sent to prod, the mismatched issuer and/or audience must cause rejection. If your organization uses **the same issuer** across environments, boundaries separating audiences, Client registrations, scopes, and policies must be designed even more carefully; sharing an issuer does not automatically isolate environments.

## 5. Distinguishing Secrets of OAuth2 Client, Resource Server, and Authorization Server

Not every OAuth 2.0 participant needs a `client-id` and `client-secret`.

### 5.1. Resource Server Verifying Signed JWTs

Orders API receives JWTs signed by Identity Server and typically uses **public keys** from JWKS to verify signatures. In this setup, the Resource Server **does not need a client secret just to verify tokens**.

~~~text
Identity Server:
  private signing key  -> signs JWT (keep secret)
  public key/JWKS      -> published for Resource Server

Orders API:
  issuer-uri           -> trusted issuer
  jwk-set-uri          -> public key source
  expected-audience    -> API identifier
~~~

Never copy the Authorization Server's **private signing key** into the API just to "verify JWTs." With asymmetric algorithms like RS256/ES256, the Resource Server only needs the public key plus issuer/algorithm policy constraints.

### 5.2. Resource Server Using Opaque Token Introspection

If the Authorization Server issues **opaque access tokens**, Orders API may need to call the introspection endpoint and authenticate itself when calling it.

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaque-token:
          introspection-uri: ${OAUTH_INTROSPECTION_URI}
          client-id: ${OAUTH_INTROSPECTION_CLIENT_ID}
          client-secret: ${OAUTH_INTROSPECTION_CLIENT_SECRET}
~~~

In Spring Security, the opaque-token security chain uses:

~~~java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults()))
~~~

**This is an alternative configuration to the JWT decoder in section 4**; do not accidentally configure both modes expecting Spring to auto-pick the right token mode per business need.

Here, `OAUTH_INTROSPECTION_CLIENT_SECRET` is the secret Orders API uses to authenticate to the Authorization Server to **verify tokens**, not a JWT signing key. Dev/staging/prod must each use dedicated credentials and introspection URIs with least privilege.

Introspection responses must be evaluated by the Resource Server per contract: `active`, audience or resource, scopes, Client/subject metadata, and related attributes. If audience is absent from the response, establish an equivalent contractual check confirming the token targets this API; never assume `active = true` suffices for every API.

### 5.3. App Acting as Both Resource Server and OAuth2 Client

A backend may both accept Bearer tokens on Orders API and call Reporting API outbound. On outbound calls, the backend acts as an **OAuth2 Client** and may need its own client secret to request access tokens:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reporting:
            provider: company-identity
            client-id: ${REPORTING_CLIENT_ID}
            client-secret: ${REPORTING_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope: reports.read
        provider:
          company-identity:
            token-uri: ${REPORTING_TOKEN_URI}
~~~

This is **OAuth2 Client configuration for outbound calls**, not a substitute for Resource Server configuration protecting inbound requests. Nor can an access token received from an inbound caller **automatically** be forwarded to Reporting API, because the two APIs may have different audiences.

If a web app uses `oauth2Login()` for OIDC login, Client registration and Client credentials for the login flow are also separate settings. An **ID token** is for the OIDC Client, whereas Orders API expects an **access token** with the right audience and permissions.

### 5.4. Classifying Secrets to Avoid Misplacement

| Item | Secret? | Typical management approach |
| --- | --- | --- |
| `issuer-uri`, `jwk-set-uri`, `audience` | No | Public config files or configuration distribution |
| `client-id` | Typically no | Environment-specific configuration |
| `client-secret` | **Yes** | Secret manager, Kubernetes Secret, CI/CD secret injection |
| Private signing/decryption key | **Yes, highly sensitive** | HSM/KMS or role-restricted key vault |
| Bearer access token, refresh token | **Credential-sensitive** | Secure memory/token store; keep out of logs, URLs, shell history, and commits |
| Public JWK/JWKS | No | Published via trusted HTTPS endpoint with proper key/algorithm policy |
| Service account password | **Yes** | Per-environment secret store |

Prefix variable names with their **role** to avoid mix-ups: `OAUTH_INTROSPECTION_CLIENT_SECRET` is distinct from `REPORTING_CLIENT_SECRET`; avoid creating one generic `OAUTH_SECRET` shared across unrelated components.

## 6. Delivering Configuration and Secrets via Deployment Infrastructure

Environment separation does not stop at `application.yml`. Deployment infrastructure must deliver the right settings to the right app, restrict read/write permissions, and support safe secret rotation.

### 6.1. Kubernetes Example: ConfigMap for Public Values

A ConfigMap dedicated to production:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: orders-api-oauth-config
  namespace: shop-prod
data:
  OAUTH_ISSUER_URI: "https://login.example.com/realms/shop"
  OAUTH_JWKS_URI: "https://login.example.com/realms/shop/protocol/openid-connect/certs"
  OAUTH_API_AUDIENCE: "orders-api"
  ORDERS_PUBLIC_BASE_URL: "https://orders.example.com"
~~~

In a Deployment, values are injected into the container:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: shop-prod
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      containers:
        - name: orders-api
          image: example-registry.invalid/shop/orders-api:1.0.0
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: prod
          envFrom:
            - configMapRef:
                name: orders-api-oauth-config
~~~

This Deployment snippet only illustrates **passing configuration**; it omits ports, health checks, network policies, service accounts, and other operational settings required in real deployments.

Kubernetes **Secret** for sensitive credentials if the Resource Server uses introspection:

~~~yaml
# Partial container configuration when choosing opaque introspection:
env:
  - name: OAUTH_INTROSPECTION_CLIENT_SECRET
    valueFrom:
      secretKeyRef:
        name: orders-api-introspection-credentials
        key: client-secret
~~~

This is an **excerpt referencing an already-provisioned Secret**, not creating a Secret with literal credentials. Manage Secrets per environment, restrict RBAC access, control distribution, and establish rotation procedures. Do not assume default Kubernetes Secrets are end-to-end encrypted at every layer without verifying platform secret-storage protections.

### 6.2. CI/CD Must Supply the Right Configuration Set

A production pipeline might reference:

~~~text
environment = production
config-set  = orders-api/prod
secret-set  = orders-api/prod
image       = orders-api:<immutable-version>
~~~

This is an illustrative model; exact syntax varies by CI/CD tool. Key rules:

1. **Never commit secrets** into `application-prod.yml`, source code, Dockerfiles, scripts, or docs.
2. **Each environment has its own credentials**, least privilege, and independent revocation.
3. **Build one artifact and promote** across environments where appropriate; environment values are injected at deploy time.
4. **Restrict who can edit prod configuration**, especially issuer/JWKS/audience or authentication-related endpoints.
5. **Never print secrets/access tokens in logs** when debugging, inspecting pipelines, or generating error reports.

For local runs, obtain secrets from your team's secret manager or temporary environment variables, never hardcoded strings pushed to the repository. A dev environment with a mock issuer/authorization server must still validate tokens per the policy designed for dev.

## 7. Avoiding Hardcoding and Unsafe Fallbacks

### 7.1. Do Not Embed Issuer/Audience in Java

Pattern that invites environment bugs:

~~~java
// Unsuitable for code shared across multiple environments:
private static final String ISSUER =
        "https://login.example.com/realms/shop";
private static final String AUDIENCE = "orders-api";
~~~

If this runs in dev, the API may trust production tokens or force developers to test with production tokens. Moving values into environment properties keeps security code focused on **rules** (validate issuer/audience), while concrete values belong to deployment.

### 7.2. Beware of Defaults in Placeholders

This configuration can mask missing variables in production:

~~~yaml
# Example to avoid for mandatory security settings:
app:
  security:
    expected-audience: ${OAUTH_API_AUDIENCE:orders-api-dev}
~~~

If `OAUTH_API_AUDIENCE` is omitted, the app silently uses the dev audience. For mandatory security settings, use **no fallback values**, or permit explicit fallbacks only inside a tightly controlled local-only profile.

### 7.3. Never Use Request Host as Audience

Behind reverse proxies, requests may carry host `orders.example.com`, internal host `orders-api.shop-prod.svc.cluster.local`, or multiple public domains. Never infer valid `aud` values from the request hostname, as Host headers can change across proxies/gateways or be spoofed if uncontrolled.

Audience is a **Resource Server identifier contracted with the Authorization Server**, configured independently. The API URL serves routing; the audience serves token validation.

### 7.4. Never Relax Security by Profile

A bad shortcut when dev cannot reach JWKS is disabling JWT verification altogether or dropping scope checks. That makes dev behave differently from production, hides integration bugs, and risks leaking into deployments.

Instead, use a **real dev issuer or a mock issuer with deterministic signing keys**, configure JWKS properly, issue dev tokens with dev audiences/scopes, and keep verification rules identical. If unit tests need mocked Authentication, confine mocking strictly to tests, never in runtime API config.

## 8. Verifying Configuration at Startup

An app may boot cleanly yet accept tokens from the wrong issuer, or accept the right issuer with the wrong audience. Define **minimum configuration invariants** at startup.

### 8.1. Require Mandatory Values

These variables normally must exist and be non-empty:

~~~text
OAUTH_ISSUER_URI
OAUTH_JWKS_URI
OAUTH_API_AUDIENCE
~~~

If using introspection:

~~~text
OAUTH_INTROSPECTION_URI
OAUTH_INTROSPECTION_CLIENT_ID
OAUTH_INTROSPECTION_CLIENT_SECRET
~~~

If the app is also an OAuth2 Client, add the corresponding credentials/endpoints **for that Client**, e.g. `REPORTING_CLIENT_ID`, `REPORTING_CLIENT_SECRET`, `REPORTING_TOKEN_URI`.

Placeholders without defaults catch many missing values when Spring binds or reads properties. For critical security settings, you can define `@ConfigurationProperties` with validation to **fail fast** cleanly on blank or invalid values instead of waiting for the first request.

### 8.2. Check Consistency Between Issuer and JWKS

`OAUTH_ISSUER_URI` and `OAUTH_JWKS_URI` must belong to the same environment's trusted set. Cross-check against Authorization Server metadata:

~~~text
Issuer metadata:
  issuer = https://login.example.com/realms/shop
  jwks_uri = https://login.example.com/realms/shop/protocol/openid-connect/certs
~~~

Discovery paths depend on the provider and supported protocols. Do not construct endpoints by hardcoded string concatenation if the provider publishes a different URI. Use HTTPS and appropriate TLS certificate trust policies.

### 8.3. Verify the Actual Audience Issued by the Token Issuer

Example:

~~~json
{
  "iss": "https://login.example.com/realms/shop",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "sub": "user-481"
}
~~~

This is an **illustrative payload**. During real integration, inspect claims from a test token in a controlled environment to confirm the AS issues the expected audience. Decoding a payload only reads data—**it does not verify a token**; the API must use an official decoder/validator. Never upload real access tokens to public JWT decoder websites or log them.

## 9. Diagnosing 401 and 403 Across Environment Mismatches

Common issues look similar externally yet have distinct root causes:

| Symptom | Possible cause | What to check |
| --- | --- | --- |
| API returns **401**, dev token rejected by prod | Mismatched issuer or audience | Check AS-issued `iss`/`aud` vs. prod config |
| API returns **401** right after changing Identity Server endpoint | API still points to old/wrong JWKS/issuer | Check metadata, `jwks_uri`, realm changes, key rotation, decoder logs |
| API returns **401** even though token "decodes fine" | Bad signature, expired, wrong issuer, wrong audience, or wrong token type | Verify with JWT library; raw decoding proves nothing |
| API returns **401** in one environment but passes in another | Wrong ConfigMap/profile/env var or clock skew | Compare sanitized effective config; check system clocks |
| API returns **403** with valid token | Missing `SCOPE_orders.read` or object-level permission | Check actual scopes, converters, tenant/owner policy |
| API errors fetching JWKS | Network/DNS/TLS or bad JWKS URI | Check connectivity, metadata, certificates, keys/`kid` |
| Introspection returns inactive/auth error | Bad URI, client credentials, expired/revoked token | Verify environment's introspection endpoint and credential permissions |
| OAuth2 Client fails to fetch token | Wrong token endpoint, Client registration, grant, or secret | Check **Client config**; distinct from API JWT verification |

Never fix an audience mismatch by removing the audience validator. Never fix a key mismatch by accepting any signature. When permissions are missing, fix the **issued scopes/roles/policies** through proper channels instead of reading `ROLE_ADMIN` from request headers.

### 9.1. HTTP Status Codes Do Not Tell the Whole Story

With Bearer authentication, APIs typically return:

- **401 Unauthorized:** missing token or unauthenticated token, including bad issuer, audience, signature, or expiration.
- **403 Forbidden:** valid token lacking required scope/permission or record-level access.
- **404 Not Found:** sometimes used by policy to avoid disclosing the existence of an unauthorized resource.

Clients should handle 401 and 403 per the API's security semantics. Do not infinitely retry tokens from the wrong environment; fix Client registration, target audience, and granted permissions.

## 10. OIDC Scenario: Login Provider Config Differs from API Config

In OIDC, the **login Client** uses the issuer to discover endpoints, verify ID tokens, and establish a user session. The **Resource Server** uses issuer and audience to verify **access tokens** protecting APIs.

For example, the Shop Web app (OAuth2/OIDC Client) might use:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          shop-login:
            provider: shop-id
            client-id: ${SHOP_WEB_CLIENT_ID}
            client-secret: ${SHOP_WEB_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          shop-id:
            issuer-uri: ${SHOP_IDP_ISSUER_URI}
~~~

This assumes Shop Web is a **confidential web client** with a `client-secret`; public clients follow a different model, typically using PKCE without embedding long-lived secrets in client code. `SHOP_IDP_ISSUER_URI` may match the Resource Server's trusted issuer when using the same Identity Server, yet **Client ID/secret, redirect URI, requested scopes, and API audience remain distinct values**.

Specifically:

| ID token | Access token |
| --- | --- |
| Intended for the OIDC Client and typically has `aud` = `client_id` | Intended for the Resource Server; `aud` must match the API |
| Confirms user login outcome per OIDC | Used as Bearer credential calling APIs |
| Client validates per OIDC rules | API validates issuer, signature, lifetime, audience, and permissions |

Never configure Orders API to check only the issuer and accept ID tokens just because ID tokens are also JWTs. The Resource Server must enforce token type and intended audience per the integration contract.

## 11. When Environments Share One Authorization Server

Dev, staging, and production do not always have three physically separate issuers. An organization might use:

- A single Identity Provider with separate **realms/tenants** per environment.
- One shared issuer with distinct **Client registrations** and **audiences**.
- One shared issuer with the same audience across environments (this case warrants careful security review).

The priority is **isolating trust contracts and permissions across environments**. When APIs share an issuer, at minimum restrict accepted tokens by audience and other verified claims. If both issuer and audience are shared, environments may struggle to distinguish tokens; add appropriate boundaries (such as resource/client binding or independent issuance and verification policies) instead of assuming "same issuer means safe."

Ask the abuse question: if a dev token leaks, could it be presented to the production API and pass every validation check? The answer must be governed by **issuer, audience, trust, and policy design**, not merely profile names.

## 12. Recommended Per-Environment Rollout Workflow

### Step 1 — Define Each Environment's Token Contract

Document per environment:

~~~yaml
# Illustrative integration contract doc, not a schema read by Spring.
environment: prod
resource_server: orders-api
issuer: https://login.example.com/realms/shop
jwks_uri: https://login.example.com/realms/shop/protocol/openid-connect/certs
expected_audience: orders-api
required_scopes:
  GET /api/orders/{id}: orders.read
  POST /api/orders: orders.write
token_usage: oauth2_access_token
~~~

This is a **contract document**, not an automatic replacement for `application.yml`. It aligns the Client team, Identity team, and API team on exact values before writing real configs.

### Step 2 — Prepare Deployment Configuration

Attach each environment's configuration set to its release or workload: issuer/JWKS/audience in a ConfigMap or configuration service; introspection/OAuth2 Client credentials in a separate secret manager.

### Step 3 — Ensure the API Enforces What Was Agreed

The Resource Server must verify signatures with trusted keys, `iss`, `aud`, `exp`/`nbf`, token type, and scopes/authorities. Then the business layer must check owner, tenant, permissions, and domain rules.

### Step 4 — Verify Environment Match and Mismatch Behavior

| Scenario | Expectation |
| --- | --- |
| Prod API + valid prod access token, right audience and scope | Proceeds to data-level policy |
| Prod API + dev access token | **401** if it fails prod's issuer/audience/trust contract |
| Prod API + same-issuer token with `aud = billing-api` | **401** |
| Prod API + expired token with right audience | **401** |
| Prod API + valid issuer/audience token lacking endpoint scope | **403** |
| Prod API + sufficient scope lacking data permission | **403** or **404**, per policy |
| API starts missing mandatory issuer/audience | Deployment must catch config error rather than silently using unsafe defaults |

Observe outcomes from both Authentication and the business layer. Never log Bearer tokens or secrets for troubleshooting; log request IDs, environment, error codes, and public config identifiers per observability policy.

### Step 5 — Manage Changes and Secret Rotation

When updating issuers, JWKS endpoints, audiences, or client secrets, identify value ownership, affected environments, Client/AS/API rollout order, and token transition windows. Signing key rotation must account for JWKS caching and remaining token lifetimes. Client secret rotation must update consuming services cleanly without leaking old or new secrets through pipelines.

## 13. Pitfalls to Avoid

**"API base URL and audience are always identical."** False. Audience is an identifier defined by the issuer contract. It may be a URI, yet need not match the hostname Clients call.

**"As long as the issuer matches, any API can use the token."** False. A token may be issued for another API. Resource Servers must validate audience and permissions intended for themselves.

**"Verifying JWTs requires the issuer's client secret."** For asymmetrically signed JWTs, APIs normally verify using public keys from JWKS; an OAuth2 Client secret is a completely different concept.

**"JWKS is a secret and must not be published."** Verification JWKS normally holds **public** keys. Private signing keys stay secret on the signing side; never confuse the two.

**"Issuer URI is just an HTTP endpoint; changing domains has no impact."** `iss` is part of the verification contract. When an issuer changes, Clients, APIs, and token issuance policies may need coordinated updates.

**"Setting profile = prod secures production."** Profiles only select configuration. Security comes from deployment governance, accurate issuer/audience, isolated credentials, token validation, and authorization.

**"Every Resource Server needs a client-id/client-secret."** False. A Resource Server verifying signed JWTs typically needs no client secret; Resource Servers using introspection or apps also acting as OAuth2 Clients may need credentials.

**"Since dev and prod share code, they should share one secret for convenience."** Each environment needs independent credentials to limit blast radius upon leak or revocation.

**"A token that decodes and shows scopes is valid."** Base64URL decoding only reads payload data without verifying signature, issuer, audience, expiration, or token type.

---

**Remember:** To configure a Spring Security OAuth 2.0/OIDC Resource Server safely across environments, keep **verification logic in shared code**, externalize **issuer URI, JWKS URI, and audience** per environment, and deliver **client secrets/credentials** via secret management strictly to the roles that genuinely need them. Each Resource Server trusts only tokens issued by its agreed issuer, intended for that exact API, and satisfying access policies; moving between dev, staging, and production changes configuration values, never security principles.
