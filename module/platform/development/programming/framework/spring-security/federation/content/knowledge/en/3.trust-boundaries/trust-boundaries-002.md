# Establishing Trust with Metadata, Keys, Certificates, and Partner Configuration

> **Scope:** Spring Security – federation / Trust Boundaries. This lesson guides how to establish and operate trust relationships between an application and an Identity Provider (IdP) when using **OpenID Connect (OIDC)** or **SAML 2.0**, including partner configuration, message verification, key/certificate governance, key rotation, and testing. Spring examples use a **Servlet/MVC** application, Java 17+, and Spring Security 6.x in Spring Boot 3.x. An illustrative configuration only works when the IdP and client/SP are actually registered properly.

## 1. Learning Objectives

After completing this lesson, you will be able to:

1. Identify **trust boundaries**: which party issues identity claims, which party verifies them, which party establishes the session, and which party makes access decisions.
2. Accurately read **OIDC Discovery metadata/JWKS** and **SAML IdP/SP metadata**; distinguish endpoint-descriptive data from cryptographic credentials.
3. Establish the **initial trust anchor** (trust bootstrap) and partner configuration using issuer/entity ID, client ID, redirect/ACS, keys/certificates, algorithms, and policies.
4. Distinguish between a **TLS certificate**, **SAML signing certificate**, **public key in JWKS**, **SP private key**, **client secret**, **ID Token**, and **access token**.
5. Configure a Spring Security application to accept OIDC or SAML sign-in without inadvertently trusting an issuer, key, certificate, or URL arbitrarily supplied by a user.
6. Design key lifecycles, certificate rotation, invalid-message verification, partner changes, and incident response procedures.

## 2. The Trust Model: Who Publishes, Who Verifies?

**Federation** allows an application to rely on authentication results issued by another system. With OIDC, the application is the **Relying Party (RP)**, and the IdP acts as the **OpenID Provider (OP)**. With SAML, the application is the **Service Provider (SP)**, and the authenticating system is the **IdP/Asserting Party**.

```text
               +---------------------------+
               | Trusted IdP/OP            |
               | Authenticates users       |
               | Holds signing PRIVATE key |
               +-------------+-------------+
                           |
          (1) metadata: issuer/entity ID, endpoints,
              PUBLIC key or certificate
                           |
                           v
 +------------------+   (2) trust config        +--------------------+
 | App owner /      | ------------------------> | Spring Security    |
 | partner admin    |                           | RP/SP              |
 +------------------+                           +---------+----------+
                                                          ^
               (3) signed authentication result           |
 IdP/OP ------------------------------------------------> RP/SP
                                                          |
                           (4) verify signature, issuer,  |
                               audience, timestamps,      |
                               transaction context        |
                                                          v
                                                Create Authentication
                                                + app session
                                                          |
                                               (5) check permissions
```

The most important point is that **metadata and keys only have meaning when the application knows why the source publishing them is trustworthy**. An XML file containing a certificate, or a JWKS containing a public key, **does not by itself turn the publishing party into an IdP permitted for sign-in**. An administrator must establish the partner over an authenticated channel, constrain valid issuers/entity IDs and endpoints, and only then does the application use metadata to verify messages.

**Four layers of trust to distinguish:**

| Layer | Question | Common Controls |
| --- | --- | --- |
| Partner relationship | Is this organization/tenant/IdP permitted to authenticate users for the application? | Approved partner allowlist, owners, contracts, tenants, and change process |
| Metadata and keys | Where does the application learn the issuer, endpoints, and public keys/certificates? | Fixed metadata URLs, HTTPS, authenticated distribution sources, policy-based certificate/metadata checks |
| Authentication transaction | Was the response/token/assertion truly issued by the right partner, intended for the right RP/SP, and still valid? | Signature, `iss`/`Issuer`, `aud`/`Audience`, `exp`, `state`, `nonce`, `InResponseTo`, replay protection |
| Permissions and lifecycle | What is that identity allowed to do, how long does the session stay valid, and when must it be revoked? | Account mapping, tenant, roles, session, provisioning/deprovisioning, logout, audit |

**Counterexample:** An attacker can craft a JWT, generate their own RSA keypair, publish the public key in their own JWKS, and validly sign the JWT with the corresponding private key. The signature may verify mathematically, yet the application **must reject it** if the issuer/key is not part of an approved partner relationship. **Verifying a signature is different from deciding to trust the signer.**

## 3. Accurately Distinguishing Metadata, Keys, and Certificates

| Component | OIDC/OAuth 2.0 | SAML 2.0 | What the Application Must Ensure |
| --- | --- | --- | --- |
| Issuer identity | `issuer` (URI, `iss` value) | IdP `entityID`, `Issuer` in assertion | Matches configured partner; avoid tenant confusion |
| Metadata | OpenID Provider Configuration JSON | XML `EntityDescriptor`/`IDPSSODescriptor` | Fetched from the right source, authenticated, and change-monitored |
| Endpoints | `authorization_endpoint`, `token_endpoint`, `jwks_uri`... | `SingleSignOnService`, optionally `SingleLogoutService` | Scheme, host, and path match the allowlist and deployment |
| Verification keys | JWKS, public keys described as JWK | X.509 certificate in `KeyDescriptor` or trust config | Only use keys belonging to an approved issuer/entity ID |
| IdP signing private key | Kept secret by IdP, signs ID Token/SAML Assertion | Kept secret by IdP, signs Assertion/Response | RP/SP does not need and must never demand the IdP's private signing key |
| Recipient registration | `client_id`, secret/client auth method, `redirect_uri`, scope | SP `entityID`, ACS URL, bindings, metadata, SP certificates | IdP must register the exact recipient |
| Login result | ID Token (JWT), optionally accompanied by UserInfo | `SAMLResponse`/`Assertion` | Verify semantics **after** verifying the origin and signature |
| Channel protection | HTTPS/TLS for discovery, token, callback | HTTPS/TLS for metadata, SSO, ACS | TLS protects transport; it does not replace message verification |
| Application secret material | Client secret/private key JWT/client credential per config | SP private key when signing requests or decrypting assertions | Store in a secret manager, restrict access, and plan rotation |

**Do not conflate terms:**

- **The TLS certificate of `https://idp.example.org`** serves server authentication and HTTPS channel encryption; it may be issued by a public CA.
- **JWK/JWKS** represents token signature verification keys (typically RSA/EC). A JWK may include `x5c`, though not every JWKS contains certificates. Trust typically comes from the configured issuer/discovery endpoint and TLS, not merely from the CA chain of `x5c`.
- **The X.509 certificate in SAML metadata** contains the public key used to verify SAML signatures. It may be self-signed; trusting it usually depends on specific IdP/metadata configuration, **not by default Web PKI validation like a TLS certificate**.
- **A private key** must stay in the system that owns it. An RP/SP only needs the IdP's public key to verify the IdP's signature; an SP may need **the SP's own** private key to sign `AuthnRequest` or decrypt Assertions.
- **The client secret** of an OAuth confidential client is the client's authentication credential at the token endpoint, not the key used to verify the ID Token signature.
- **Encryption** protects confidentiality; **digital signing** supports integrity and origin verification; **identity authentication** also requires checking issuer, audience, timestamps, and session context.

## 4. Trust Bootstrap: The Starting Point Must Be Controlled

A partner onboarding process should begin **outside the user's login flow**:

1. **Identify the principal party:** organization name, IdP owner, tenant/realm, system environment (test, staging, production), and authentication purpose.
2. **Exchange static identifiers:** OIDC issuer URL or SAML IdP `entityID`; RP `client_id` or SP `entityID`; restrict the set of allowed partners.
3. **Exchange metadata over a trusted channel:** authenticated admin portal, internal admin channel, approved HTTPS URL, or signed file verified per policy. Never ingest a metadata URL from a browser query parameter.
4. **Register return endpoints:** exact OIDC `redirect_uri`; compatible SAML ACS URL and bindings. Separate each environment and handle real proxies accurately.
5. **Define token/assertion policy:** approved algorithms, audience, lifetimes, clock skew, MFA/ACR if required, mandatory identity attributes, and role mapping.
6. **Set up accounts and testing:** test users, groups, unauthorized-access scenarios, logout, rotation, and IdP downtime. Enable production only after completing negative testing.
7. **Record an audit trail of changes:** date metadata was received, version/certificate, approver, expiration date, rotation schedule, and rollback procedure.

**Trust bootstrap differs from runtime trust:** The bootstrap step places the right partner and public key into configuration; the runtime step verifies each message against that configuration. A redirect sent to the application must never be allowed to dynamically expand the trust store.

### Sample Partner Profile (Business Documentation, Not Spring Boot Configuration)

```yaml
partner:
  id: corp-idp-prod
  owner: identity-platform-team
  environment: production
  protocol: oidc
  issuer: https://login.example.org/realms/employees
  relying-party:
    client-id: portal-web-prod
    redirect-uri: https://portal.example.org/login/oauth2/code/corporate
  accepted-signing-algorithms: [RS256]
  identity-key: [issuer, subject]
  account-mapping: internal-user-id
  change-process: security-approved
  rotation-contact: identity-platform-team
```

The data above only describes the **trust contract**. Values such as domain, client ID, and algorithm are examples; they must be obtained from the real partner. Never put client secrets/private keys into a widely shared profile. Do not treat `accepted-signing-algorithms` as a built-in Spring Boot property without implementing the corresponding validator/decoder.

## 5. OIDC: Metadata Discovery and Verifying the Right Issuer

With OIDC, the **OpenID Provider Configuration** is a JSON document that helps the RP discover the OP's endpoints and capabilities. When using a standard issuer `https://login.example.org/realms/employees`, the RP must perform discovery following OIDC rules and confirm that the `issuer` value in the returned document **matches the configured trusted issuer exactly**. Never infer the issuer from the callback hostname or the `iss` value of an unverified token.

Fields to recognize:

| Field | Purpose | Common Pitfalls |
| --- | --- | --- |
| `issuer` | Unique identifier of the OP; ID Token carries the matching `iss` | Confusing tenants, omitting path/realm or trailing slash |
| `authorization_endpoint` | Where the browser goes for authentication/consent | Redirecting to an unconfigured/unapproved endpoint |
| `token_endpoint` | Backend exchanges the authorization code for tokens | Leaking client secret, wrong client auth, or sending code to a rogue endpoint |
| `jwks_uri` | Address of the OP's public signing key set | Using a URL from the token's `jku` header instead of the trusted URL |
| `response_types_supported` | Response types supported by the OP | Using a flow unsuitable for a web app |
| `id_token_signing_alg_values_supported` | Algorithms the OP advertises it may use to sign ID Tokens | Permitting weak/out-of-policy algorithms just because metadata lists them |
| `end_session_endpoint` (if present) | Endpoint for logout per OP capabilities | Assuming RP logout always terminates the IdP session |

**Sample JSON snippet illustrating structure** (contains representative fields only, not complete metadata):

```json
{
  "issuer": "https://login.example.org/realms/employees",
  "authorization_endpoint": "https://login.example.org/realms/employees/protocol/openid-connect/auth",
  "token_endpoint": "https://login.example.org/realms/employees/protocol/openid-connect/token",
  "jwks_uri": "https://login.example.org/realms/employees/protocol/openid-connect/certs",
  "response_types_supported": ["code"],
  "id_token_signing_alg_values_supported": ["RS256"]
}
```

**Source verification:** HTTPS protects metadata and JWKS retrieval; the issuer URL must originate from an approved partner profile; discovery endpoints must remain within controllable boundaries. If an enterprise runs an IdP with custom paths or endpoints, configuration must reflect the exact published metadata rather than modifying `issuer` by guesswork.

### 5.1. JWKS Is Not an "Everyone Is Trusted" List

A **JSON Web Key Set (JWKS)** contains a set of public keys, each of which may have `kty`, `kid`, `use`, `alg`, `n`/`e` (RSA), or `crv`/`x`/`y` (EC). `kid` helps select a key from a key set **already bound to an issuer**; `kid` itself does not prove who the issuer is. Two different IdPs can share the same `kid`.

For a JWT-signed ID Token, a proper pipeline is:

1. Identify the **configured partner/registration** based on the initiated login flow.
2. Use **that issuer's** metadata/JWKS to locate candidate keys by `kid` and allowed algorithm.
3. Verify the signature and reject unapproved algorithms, `alg=none`, or attempts to use an HMAC key as an RSA public key.
4. Check `iss`, `aud`, `exp`, `iat`, and `nonce` when present; check `azp` per OIDC rules if the ID Token has multiple audiences; enforce `state` verification on the callback.
5. Build `Authentication` and establish the RP session **after** all checks pass; keep authority granting independent from the authentication conclusion.

**Never take untrusted `jku`, `x5u`, `kid`, or `iss` values from a JWT and automatically fetch keys from an arbitrary URL.** This is a common vector leading to key substitution, SSRF, or cross-tenant token acceptance. A Base64URL-decoded but unverified JWT **is not trustworthy data**.

### 5.2. ID Token Differs from Access Token; API Audience Differs from Client Audience

- **ID Token** is an identity assertion for the RP/client; `aud` must match `client_id` and OIDC constraints. It is **not** used as a Bearer credential to call APIs merely because it has a signature.
- **Access token** is issued by the Authorization Server for a Resource Server; the API must check the signature or introspection, issuer, **API**-appropriate audience, expiration, and scopes/authorities. An ID Token may share the same `iss` yet have a different audience.
- **Client authentication** when the RP exchanges the code may use `client_secret_basic`, `private_key_jwt`, or another IdP-permitted method; the client secret does not replace ID Token verification rules.
- **Authorization Code + PKCE** protects the code exchange transaction; `state` defends against login CSRF and binds the callback; `nonce` binds the ID Token to the transaction session when required by the flow. Even a valid trust configuration still requires these per-transaction controls.

## 6. Configuring an OIDC Relying Party in Spring Security

Minimal example for a **Spring Boot 3.5.0/Java 17** application. It uses the issuer's discovery endpoint, a registered callback, and `oauth2Login()`. The code contains no real secrets and does not assume you already have an IdP. This design illustrates **one** statically managed OIDC partner.

**File `pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>federation-trust</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
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
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**File `src/main/resources/application.yml`:**

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: corporate
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid, profile
        provider:
          corporate:
            issuer-uri: ${OIDC_ISSUER_URI}
```

**File `src/main/java/demo/FederationTrustApplication.java`:**

```java
package demo;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class FederationTrustApplication {
    public static void main(String[] args) {
        SpringApplication.run(FederationTrustApplication.class, args);
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .build();
    }

    @RestController
    static class DemoController {
        @GetMapping("/")
        String home() {
            return "Open /whoami to authenticate with the corporate IdP";
        }

        @GetMapping("/whoami")
        Map<String, String> whoami(@AuthenticationPrincipal OidcUser user) {
            return Map.of(
                    "issuer", user.getIdToken().getIssuer().toString(),
                    "subject", user.getIdToken().getSubject());
        }
    }
}
```

**At the IdP**, create a **web/confidential OIDC client** with the corresponding client ID/secret and register `http://localhost:8080/login/oauth2/code/corporate` exactly. `OIDC_ISSUER_URI` must be the exact issuer published by the OP, including path/realm/tenant. When running behind a reverse proxy or in production, use an HTTPS callback, the public host, and forwarded headers configured from a **trusted proxy**.

**Run on bash:**

```bash
export OIDC_ISSUER_URI='https://login.example.org/realms/employees'
export OIDC_CLIENT_ID='portal-demo'
export OIDC_CLIENT_SECRET='actual-secret-from-your-test-idp'
mvn spring-boot:run
```

**On PowerShell:** set `$env:OIDC_ISSUER_URI`, `$env:OIDC_CLIENT_ID`, and `$env:OIDC_CLIENT_SECRET` in turn with your test IdP values, then run `mvn spring-boot:run`. The values above are illustrative only: replace them with a real registration to actually run sign-in.

Visit `http://localhost:8080/` to see the fixed string **`Open /whoami to authenticate with the corporate IdP`**. Visiting `http://localhost:8080/whoami` will prompt for sign-in; after a valid callback, the endpoint returns JSON containing the `issuer` and `subject` provided by the IdP, so **there is no fixed hardcoded output**. The manual flow-initiation endpoint is `/oauth2/authorization/corporate`.

**Configuration lesson:** `issuer-uri` is the trust anchor at the OP-identifier level within an approved registration; Spring Security uses provider metadata and public keys to perform ID Token verification during OIDC login. Do not write your own JWT parser or decode tokens manually and trust their claims. `client-secret` must be supplied from a secret store/environment, access-restricted, never committed to Git, and never logged.

### When the Application Is an OAuth2 Resource Server, Configuration Differs

An **API** receiving Bearer access tokens should use the Resource Server model, typically in a **separate service**. For JWTs, an example configuration snippet for an API using Spring Boot 3.5.x:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.org/realms/employees
          audiences: api://orders
```

The `spring-boot-starter-oauth2-resource-server` dependency and a matching security filter chain are required—for example, using `oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))`. `audiences` is the **API's** audience per the token issuance contract, not the login page's client ID. The API also needs `hasAuthority(...)` rules or business authorization for each resource. If the AS issues opaque tokens, use introspection with appropriate credentials; do not treat an opaque token as a JWT.

**Valid alternative scenario:** Some Resource Servers need to start up even when the OP is temporarily not serving discovery; additionally configuring a fixed `jwk-set-uri` **alongside** the approved `issuer-uri` can avoid depending on a discovery call at startup while still preserving issuer validation. When using a static JWKS URL, the operator is responsible for verifying the URL, rotation, and audience; never disable issuer validation just to "make it run easily".

## 7. SAML 2.0: Metadata and Signing Certificates of Both Parties

In SAML Web Browser SSO, metadata is typically XML:

- **IdP `EntityDescriptor`** has `entityID`, `IDPSSODescriptor`, `SingleSignOnService` (binding and location), `KeyDescriptor` for signing/encryption if published, and optional logout.
- **SP `EntityDescriptor`** has `entityID`, `SPSSODescriptor`, `AssertionConsumerService` (ACS), optional SingleLogoutService, bindings, and SP certificates used to sign requests/decrypt when needed.
- The certificate in `KeyDescriptor use="signing"` is the public key to verify signatures. The `use="encryption"` certificate is for encryption/decryption according to role; **they are not interchangeable**.
- SAML XML metadata may be **signed at the metadata level**; this is distinct from the signature of the **SAML Response/Assertion**. If policy requires a metadata signature, a trusted key must be present to verify the metadata before updating configuration. Unsigned metadata should only be accepted from a protected, authenticated, and version-controlled exchange channel.

**Registration flow:**

```text
SP owner                                  IdP owner
  |  Provide SP entityID, ACS, bindings      |
  |----------------------------------------->|
  |     Receive IdP entityID, SSO URL, cert  |
  |<-----------------------------------------|
  |                                          |
  |  SP stores trust: IdP entityID + cert    |
  |  IdP stores reg: SP entityID + ACS       |
  |                                          |
  |  SP generates AuthnRequest ------------->|
  |<-- Signed SAMLResponse via browser ------|
  |  SP verifies before creating session     |
```

**What must be verified on a SAML Response/Assertion?**

1. **Valid XML signature** on the element protected by the profile and configuration (Response or Assertion as appropriate), using the trusted IdP certificate; do not take a certificate embedded in the message as a new trust anchor.
2. **`Issuer`** must be the configured IdP/entity ID; exact Response **`Destination`** and SubjectConfirmationData **`Recipient`** matching the actual deployment.
3. **`AudienceRestriction`** must pinpoint the exact SP entity ID; an Assertion sent for SP A must not be accepted at SP B.
4. **`NotBefore`, `NotOnOrAfter`**, plus any additional time conditions, checked with synchronized clocks and very tight clock skew.
5. **`InResponseTo`** must match a pending AuthnRequest when using the SP-initiated flow. Correlation must be handled for the corresponding session/browser, not merely checking that the XML "has a signature".
6. **Replay protection:** use the Response/Assertion ID and transaction state to prevent reuse within the validity window; never implement XML verification using string comparison or regex.
7. **NameID/attributes:** accept only after the message passes verification; map tenant/user and authorities according to internal policy. Never automatically grant `ROLE_ADMIN` based on an unagreed attribute.

**Important distinction:** A SAML IdP certificate may be self-signed and outside Web PKI. Its trustworthiness lies in the application having received/approved the right partner's certificate via metadata/onboarding. Still, certificate validity periods, rotation schedules, algorithms, and organizational validation policies must be monitored. A syntactically valid `X509Certificate` does not ensure an assertion is trustworthy if the **entity ID or audience is wrong**.

### 7.1. Configuring an SP with Metadata in Spring Security

When using SAML 2.0 on Servlet, the typical dependency is `org.springframework.security:spring-security-saml2-service-provider`. The **integration configuration snippet** below assumes the project already has Spring Security, Spring Web, and an approved IdP metadata URL. This is an **alternative pattern to the OIDC configuration** in Section 6 if the application chooses SAML; do not combine both into a single `SecurityFilterChain` and treat them as independent flows.

**File `SamlSecurityConfiguration.java`** (excerpt of configuration class, placed in an application package):

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfiguration {

    @Bean
    RelyingPartyRegistrationRepository relyingPartyRegistrations() {
        RelyingPartyRegistration corporate =
                RelyingPartyRegistrations
                        .fromMetadataLocation("https://sso.example.org/metadata")
                        .registrationId("corporate-saml")
                        .entityId("{baseUrl}/saml2/service-provider-metadata/{registrationId}")
                        .assertionConsumerServiceLocation(
                                "{baseUrl}/login/saml2/sso/{registrationId}")
                        .build();

        return new InMemoryRelyingPartyRegistrationRepository(corporate);
    }

    @Bean
    SecurityFilterChain samlSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/error").permitAll()
                        .anyRequest().authenticated())
                .saml2Login(Customizer.withDefaults())
                .saml2Metadata(Customizer.withDefaults())
                .build();
    }
}
```

**Explanation of limitations:** The metadata path is an illustrative URL and must be replaced with a real IdP. `fromMetadataLocation(...)` creates a registration from the provided metadata; **only do this with an approved source**. If the IdP requires signed `AuthnRequest`s or encrypted Assertions, add the SP's credentials to `RelyingPartyRegistration` and register the SP's public certificate at the IdP. The example does not yet configure an SP private key, logout, role mapping, clustered replay storage, or enterprise policies.

The default sign-in path typically starts with `/saml2/authenticate/corporate-saml`, and the ACS is `/login/saml2/sso/corporate-saml`. With `saml2Metadata()`, the application can publish metadata for the IdP to register the SP; the actual URL depends on `registrationId`, base URL, and version. Cross-check the **metadata generated by the application** against the configuration at the IdP instead of retyping endpoints from memory.

**Do not assume the library handles all operations automatically:** depending on the version and how `RelyingPartyRegistration` is provided, metadata/JWKS may be loaded or cached at different times; in particular, if a SAML registration is built once at startup, updating the metadata file at the source **does not guarantee** the signing certificate updates automatically in the running process. You must test rotation scenarios and proper reload/restart procedures.

## 8. Metadata Is a Technical Contract, Not a Substitute for Trust Policy

Both OIDC and SAML can advertise many endpoints and attributes. Do not blindly ingest every field into the application:

- **Trust only approved partners**: `registrationId` is an internal code; OIDC `issuer` and SAML `entityID` are protocol identifiers; they must be bound 1-to-1 via explicit configuration or controlled multi-tenant rules.
- **Do not treat matching hostnames as the same identity**: `https://idp.example.org/realm/a` differs from `https://idp.example.org/realm/b`; a different `client_id` can also have a different policy.
- **Do not use discovery as an open proxy**: a URL supplied via a `?issuer=...` request parameter or user-uploaded XML metadata must be vetted. If the app fetches untrusted documents, there are risks of SSRF, internal address access, endpoint replacement, and key substitution.
- **Restrict `alg`**: only accept signature algorithms safely supported by policy and the library. Never force the library to accept `none` or mix RSA/HMAC. Even when metadata advertises multiple algorithms, actual selection remains constrained by RP/SP policy.
- **Restrict redirect/ACS**: callbacks must match registered URLs and a properly configured reverse proxy. Do not use broad wildcards, open redirects, staging domains in production, or arbitrary URLs from untrusted headers.
- **Manage changes**: when receiving new metadata, know what changed (issuer/entity ID, endpoints, cert/key, alg), obtain approval, and test; do not assume every change from a remote host is business-authorized.
- **Synchronize time**: short-lived tokens/assertions are affected by clock skew; NTP and monitoring are part of trust operations.
- **Manage identities**: map users by a stable key, such as the `(issuer, sub)` pair in OIDC; SAML depends on the agreed NameID/attribute. Email is rarely a permanent identifier key.
- **Separate authentication/authorization**: the IdP authenticates the user; the RP/API still decides internal permissions and tenant independently. If receiving roles/groups from an IdP, mapping rules are needed, especially for attributes sharing the same name across partners.

### Multi-Tenant Partners

When multiple partners sign in to the same product, each partner has a separate trust profile and keys. For example:

```text
registration: company-a -> OIDC issuer https://idp-a.example/realms/work
registration: company-b -> OIDC issuer https://idp-b.example/tenant/b

company-a public keys MUST NOT verify company-b tokens
company-b subject "123" is NOT the same person as company-a subject "123"
```

If routing partners by email domain, subdomain, or tenant parameter, check the tenant mapping on the backend and select only an **existing, permitted registration**. Do not dynamically create new registrations/issuers from unauthenticated input. For SAML, bind `RelyingPartyRegistration`, IdP entity ID, ACS, and user tenant; prevent partner A's Assertion from being processed in B's context.

## 9. Policy for Storing Keys and Secret Material

| Material | Where It Lives | Who Needs What Access? | Operational Rules |
| --- | --- | --- | --- |
| OIDC signing **private key** | IdP/OP system | Signing service and IdP security team only | Never export private key to RP; manage in HSM/KMS where appropriate |
| OIDC signing **public key/JWKS** | Public endpoint managed by OP | RP/RS downloads to verify | Bind to issuer, cache, monitor `kid`/alg/rotation |
| OAuth **client secret** | RP backend/secret manager and IdP | Code-exchange system and authorized personnel only | Do not commit, do not log, do not send to frontend |
| SAML IdP **signing private key** | IdP | IdP only | Protect strictly; publish verification cert via metadata |
| SAML IdP **signing certificate** | Metadata/trust config at SP | SP needs public cert | Verify origin, track expiration, accept planned key rollover |
| SAML SP **signing/decryption private key** | SP/secret manager | Only SP needing sign/decrypt operations | Do not send private key to IdP; IdP receives the corresponding public certificate |
| HTTPS **server private key** | TLS endpoint/reverse proxy | TLS-terminating component only | Manage per PKI/TLS; do not use as a substitute for federation verification logic |

**When importing a SAML certificate**, you can use `keytool -printcert -file idp-signing.cer` to inspect Subject, Issuer, validity dates, and fingerprints; this helps **cross-check** the certificate against a trusted source, not automatically approve it.

### Java 17 Example to Inspect a Received X.509 Certificate

This is a utility to **read a public certificate and print inventory details**, not code to verify SAML Responses/Assertions. Java 17 includes `CertificateFactory`, `MessageDigest`, and `HexFormat` out of the box.

**File `InspectCertificate.java`:**

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.util.HexFormat;

public class InspectCertificate {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Usage: java InspectCertificate <certificate-file>");
            System.exit(2);
        }

        try (InputStream input = Files.newInputStream(Path.of(args[0]))) {
            CertificateFactory factory = CertificateFactory.getInstance("X.509");
            X509Certificate cert =
                    (X509Certificate) factory.generateCertificate(input);
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(cert.getEncoded());

            System.out.println("Subject: " + cert.getSubjectX500Principal());
            System.out.println("Issuer: " + cert.getIssuerX500Principal());
            System.out.println("Not before: " + cert.getNotBefore());
            System.out.println("Not after: " + cert.getNotAfter());
            System.out.println("SHA-256: " +
                    HexFormat.ofDelimiter(":").withUpperCase().formatHex(digest));
        }
    }
}
```

**Compile/run:**

```bash
javac InspectCertificate.java
java InspectCertificate idp-signing.cer
```

The file `idp-signing.cer` must be a valid DER or PEM X.509 certificate. The program prints Subject, Issuer, validity dates, and the SHA-256 fingerprint **depending on the actual certificate**, so no fixed stdout can be given. If the file is corrupt or not a certificate, a `CertificateException` is thrown and the program prints no fake information. When importing a cert, compare the fingerprint with the partner over an **independent authenticated channel**; do not accept a fingerprint merely because it matches the certificate inside the untrusted file itself.

**Avoid confusion:** A SHA-256 fingerprint hash identifies the certificate's bytes; **it does not prove** the IdP owns the domain, holds the corresponding private key, or has authority to assert users in the tenant. SAML message verification must be delegated to properly configured Spring Security/OpenSAML protocol validators.

## 10. Key and Certificate Lifecycle: Rotation Planning

An initially valid configuration becomes stale without a key-replacement policy. Common reasons: certificate expiration, suspected private key exposure, IdP migration, algorithm upgrades, HSM/KMS migration, or new cryptographic policies.

**Safe signing-key rotation procedure (when no key compromise has occurred):**

1. **Prepare:** partner generates a new signing keypair and stores the private key in a protected store; determine time `T0` and the list of affected SPs/RPs.
2. **Publish the new public key/certificate first:** for OIDC, add the new JWK to JWKS; for SAML, add the new certificate to recipient metadata/config as supported by the library; do not stop verifying signatures with the old key yet.
3. **Refresh/update recipients:** confirm RPs/APIs can select the new key. For JWKS caches, understand the refresh policy; for static SAML registrations, a configuration update and application rollout may be needed.
4. **Switch the signer at the IdP:** start signing new messages with the new private key. The `kid` (OIDC) or signing cert (SAML) must already be known and trusted by recipients.
5. **Observe:** monitor login success/failure, `unknown kid` errors, signature validation, SAML signatures, per tenant, and per instance; ensure clocks stay synchronized.
6. **Maintain a reasonable overlap:** the old key may still be needed to verify unexpired valid tokens/assertions and handle lagging systems; duration depends on token TTL, caches, delays, and protocol profile.
7. **Retire the old key:** after the required period, remove it from trusted keys/certs, revoke private key usage permissions, update documentation, and record completion evidence.

**If private key compromise is suspected**, the emergency procedure differs from normal rotation: stop trusting the compromised key as soon as possible, analyze issued tokens/assertions, proactively revoke sessions/credentials where possible, communicate the incident, and switch to a clean key. Never keep an overlap out of habit if the old key was compromised.

**Certificate lifetime differs from token lifetime:** a SAML certificate can expire even for a newly signed short-lived Assertion; an ID Token can expire even while its JWK remains published. Check certificate validation policy, JWT TTL, session TTL, and the IdP's rotation schedule separately.

## 11. Testing Trust: Negative Scenarios Are Mandatory

| Test | Expected Behavior | Significance |
| --- | --- | --- |
| Valid OIDC issuer + valid ID Token | RP signs in successfully | Trust path works |
| JWT validly signed by a key of an **unapproved** issuer | Rejected | Never trust an arbitrary signer |
| ID Token with valid signature but `aud` for wrong client | Rejected | Prevents token substitution |
| API X's access token used at API Y | API Y rejects | Right audience per resource |
| JWT `alg=none` or alg outside allowlist | Rejected | Algorithms must be restricted |
| Token `kid` missing from trusted JWKS | Rejected; refresh per policy if appropriate | Never fetch keys from a token-supplied URL |
| Expired ID Token or wrong nonce/callback state | Rejected | Proper context and timing |
| SAML Response signed by an unknown IdP cert | Rejected | Certificate must belong to partner |
| SAML Assertion with wrong `AudienceRestriction`/ACS recipient | Rejected | Do not accept assertions for wrong recipient |
| SAML `InResponseTo` mismatch, message replay | Rejected | Prevents callback forgery/replay |
| Metadata spontaneously changes SSO URL to unknown domain | Detected, blocked/not applied before approval | Endpoint changes must be governed |
| OIDC JWKS adds valid key then signer switches key | Sign-in continues succeeding during rollout | Rotation with proper overlap |
| Old key removed after safe window | New tokens still pass; old expired tokens rejected | Do not depend on old key forever |
| Admin permission absent from user mapping | User can sign in but admin endpoint returns 403 | Separates authentication from authorization |
| User `sub=123` at issuer A and `sub=123` at issuer B | Two independent principals | Prevents cross-tenant account merging |
| IdP unreachable or cert expired | Controlled error, never bypass validation | Fail closed |

To run negative tests, use an IdP and client **in a test environment**; do not tamper with tokens/signatures to attack production. Collect HTTP status, session, registration ID, and sanitized error codes; never log raw ID Tokens, access tokens, secrets, raw SAML Assertions, or session cookies to public dashboards/logs.

### Symptom Troubleshooting Table

| Symptom | Common Cause | How to Diagnose |
| --- | --- | --- |
| OIDC discovery fails to initialize | Wrong issuer URL, DNS/TLS error, proxy block, missing metadata fields | Access configured URL from backend; verify hostname and `issuer` value |
| `invalid_issuer` / token rejected | Wrong realm/tenant/issuer in ID Token | Compare `iss` with approved config; keep verification intact |
| `invalid_signature` / unknown `kid` | Stale JWKS cache, signed with unpublished new key, key from wrong issuer | Check JWKS changes and rotation schedule, perform controlled refresh |
| `invalid_client` during code exchange | Wrong/rotated client secret, mismatched client auth method | Check client config at IdP and secret store |
| `redirect_uri_mismatch` | Scheme/host/port/path, unregistered callback, wrong proxy config | Inspect actual authorization request and registered URI |
| SAML `invalid_signature` | Signing cert changed, wrong metadata, signed element differs from expectation | Check trusted certificate, signature, and configuration version |
| SAML `invalid_destination` or audience | ACS/entity ID differs from IdP config, load balancer alters host | Compare SP metadata, Assertion/Response, and actual URL |
| SAML `InResponseTo` error | Lost session, request state, out-of-policy IdP-initiated response | Check correlation/cluster session, distinguish flows |
| Can sign in but cannot view resource | Role/authority mapping or tenant policy denies | Check why app returns 403, do not relax authentication rules |
| Some instances fail after rotation | Rolling deployment using inconsistent trust config | Verify every instance has the right registration/cert/JWKS cache |

**Fixing principle:** Never disable signature, issuer, audience, expiration, or HTTPS verification just to get login flowing. Fix the **metadata source**, registration, secret, cert, proxy, and mapping to match the contract.

## 12. Process for Onboarding a New Partner into the System

An onboarding process suitable for a runbook:

**Step A – Contract and boundaries.** Record partner, tenant, protocol (OIDC/SAML), user population, owner, environment, granted permissions, and rotation responsibilities. Define who the partner is allowed to assert identities for.

**Step B – Metadata bootstrap.** Ingest issuer/entity ID and metadata via an authenticated channel. Check HTTPS, metadata signature if required, unexpected endpoints, certificates/public keys, and expiration; establish a baseline and fingerprint.

**Step C – Mutual registration.** OIDC: register `client_id`, auth method, redirect URI, scopes, issuer. SAML: exchange IdP/SP metadata, entity IDs, ACS URL, bindings, signing/encryption certificates. Never share client secrets or SP private keys between production and test environments unless explicitly permitted by policy.

**Step D – Spring configuration.** Use `ClientRegistration`/OIDC `oauth2Login()` or `RelyingPartyRegistration`/SAML `saml2Login()`; ensure each registration binds to the right partner. APIs use Resource Server with dedicated audience/scope when accepting tokens.

**Step E – Test both directions.** Run happy-path sign-in, wrong issuer, wrong audience, signature, expiration, replay, missing permissions, wrong redirect/ACS, key change, and IdP unavailable cases. Inspect logs with secrets redacted.

**Step F – Approval and operations.** Enable the partner in production, enable login failure/rotation metrics, assign alert recipients, rollback plan, certificate expiry check schedule, permission review cadence, and incident response SLAs.

**Step G – Offboarding.** When ending collaboration or when an IdP changes ownership: disable registration/tenant routing, revoke account/token/credential links per policy, terminate active sessions appropriately, remove certs/public keys, clean up role mappings, and audit.

### One-Page Implementer Checklist

- [ ] **Issuer/entity ID comes from an approved partner**, never from a user request.
- [ ] Metadata/JWKS/SSO URLs are source-authenticated and monitored for changes.
- [ ] **Client ID/redirect URI** (OIDC) or **SP entity ID/ACS** (SAML) are configured on both sides.
- [ ] Public signing keys/certificates, TLS certs, client secrets, and SP private keys are clearly distinguished.
- [ ] Validation enforces issuer, audience, signature/alg, expiration, and `state`/`nonce`/`InResponseTo` transactions.
- [ ] Identity/tenant/authority mapping never treats untrusted emails/groups as admin rights.
- [ ] A rotation plan, expiry calendar, cache/reload testing, and rollback exist.
- [ ] Negative tests, secret-free logging, and appropriate monitoring are in place.

## 13. Hands-On Exercises

**Exercise 1 – Design analysis:** Given an employee portal using OIDC and a legacy accounting app using SAML, draw two independent trust paths specifying: signer, where public keys/certs are stored, issuer/entity ID identity, redirect URI or ACS, where sessions are issued, and where authorization is enforced.

**Exercise 2 – Contract check:** A partner publishes a JWKS with two keys `kid=k1` and `kid=k2`, then switches the signer from `k1` to `k2`. Describe the minimum deployment sequence so the RP experiences zero downtime. Explain why merely renaming `kid` in configuration is insufficient and why keys from an arbitrary `jku` must not be allowed.

**Exercise 3 – OIDC implementation:** Use the Section 6 project with a test IdP. Confirm the issuer from discovery metadata matches `OIDC_ISSUER_URI`, callback matches registration, and `/whoami` returns the identity only after login. Try changing `OIDC_ISSUER_URI` to another realm and observe a controlled failure; do not edit code to bypass issuer validation.

**Exercise 4 – SAML implementation:** Obtain IdP metadata from an approved channel; inspect entity ID, SingleSignOnService, and signing cert. Configure SP `entityID` and ACS to match the IdP registration. Test with a test user, then test a response with wrong audience or wrong signing cert in a test environment to confirm the application rejects it.

**Exercise 5 – Incident analysis:** Two IdPs issue the same subject `"a123"`. The dev team used `sub` alone as the account table key. Describe how to fix the identity model, a migration to avoid merging accounts, and how to prove the new mapping isolates users across the two IdPs.

**Passing criteria:** The learner can explain **initial trust anchor → metadata → keys/certificates → per-message verification → identity/tenant mapping → authorization → rotation/offboarding lifecycle**; operate at least one RP/SP with a test IdP; and demonstrate that tokens/assertions with the wrong issuer or audience are rejected.

## 14. Primary References

- Spring Security – OAuth 2.0 Login (Servlet): https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
- Spring Security – OAuth 2.0 Resource Server JWT: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security – SAML 2.0 Login: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security – SAML 2.0 Metadata: https://docs.spring.io/spring-security/reference/servlet/saml2/login/metadata.html
- OpenID Connect Core 1.0: https://openid.net/specs/openid-connect-core-1_0.html
- OpenID Connect Discovery 1.0: https://openid.net/specs/openid-connect-discovery-1_0.html
- RFC 7517 – JSON Web Key: https://www.rfc-editor.org/rfc/rfc7517
- RFC 7519 – JSON Web Token: https://www.rfc-editor.org/rfc/rfc7519
- RFC 8725 – JWT Best Current Practices: https://www.rfc-editor.org/rfc/rfc8725
- OASIS SAML 2.0 Technical Overview: https://docs.oasis-open.org/security/saml/Post2.0/sstc-saml-tech-overview-2.0.html
