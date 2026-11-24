# Connecting an OIDC Application to an Identity Broker Backed by a SAML IdP

**Module:** Spring Security – federation  
**Group:** Comprehensive Practice  
**Objective:** Build an end-to-end **Spring Boot OIDC client → identity broker → SAML Identity Provider** login flow, clearly demonstrating both trust boundaries, account mapping, session management, and failure-case testing.  
**Technology:** Java 17, Spring Boot 3.5.x / Spring Security 6.x, Keycloak 26.x as the identity broker, and a second Keycloak realm simulating the SAML IdP. `localhost` addresses are for lab use only; never expose `start-dev`, HTTP, or demo admin accounts in production.

## 1. Expected Learning Outcomes

After completing this exercise, you should be able to verify that:

1. A **Java application configured strictly for OIDC** lets end users log in via a **SAML IdP** sitting behind the broker.
2. The broker acts as a **SAML Service Provider (SP)** when talking to the IdP, and simultaneously as an **OpenID Provider (OP)** issuing OIDC tokens to Spring Boot.
3. The broker validates the SAML Response signature, Issuer, Audience, Recipient, and timestamps; Spring Security validates the OIDC ID Token's **broker issuer**, signature/JWKS, audience, and expiry/nonce per flow.
4. SAML **`NameID`/attributes** do not automatically equal OIDC **`sub`**, and `sub` does not automatically grant business permissions.
5. You can inspect the Authorization Code flow, callbacks, and protected resources **without** logging tokens, `SAMLResponse` payloads, cookies, or private keys.
6. You can separate failures at the IdP, broker, OIDC client, account linking, and local authorization layers.
7. You have a repeatable lab with positive and negative tests, knowing which lab settings to strip and what to change before real deployment.

**Key takeaway:** SAML and OIDC **do not need to run side-by-side inside the Spring app**. The broker translates **verified authentication outcomes**—it does not convert a `SAMLResponse` string into a JWT by manual re-encoding.

## 2. Architecture and Boundaries Diagram

~~~text
Browser                   Spring Boot:8081
   |  GET /api/me                 |
   +----------------------------> | Unauthenticated
   |                               |
   | 302 to /oauth2/authorization/broker
   |                               |
   |------------------------------>| OIDC Authorization Code + state/nonce/PKCE
   |                               |
   | 302 to Keycloak broker realm :8080
   v                               v
+---------------------------------------------------+
| Identity broker realm: broker-oidc                |
| Downstream role: OIDC OpenID Provider             |
| - receives /protocol/openid-connect/auth requests |
| - manages sessions and linked identities          |
| - issues authorization code after upstream login  |
+---------------------------------------------------+
   |
   | SAML AuthnRequest (configured binding)
   v
+---------------------------------------------------+
| SAML IdP realm: corp-saml                         |
| - authenticates user                              |
| - generates SAMLResponse / signed Assertion       |
+---------------------------------------------------+
   |
   | Browser POSTs SAMLResponse → broker SAML ACS
   v
+---------------------------------------------------+
| Broker SAML SP                                    |
| - verify IdP signing key/Issuer/Audience/ACS/time |
| - map upstream subject → broker user              |
+---------------------------------------------------+
   |
   | Browser redirect OIDC authorization code
   v
Spring Boot OIDC callback:
   /login/oauth2/code/broker
   |
   | Spring client exchanges code via backchannel token endpoint
   v
Broker OIDC ID Token: iss=broker, aud=client, sub=broker user
   |
   v
Spring Security OidcUser + local authorization
   |
   v
GET /api/me → 200; GET /api/admin → deny if role missing
~~~

### Three Roles to Remember

| Component | Protocol Role | Whom Must It Trust? |
| --- | --- | --- |
| **corp-saml** | **SAML IdP** | Broker's registered SAML SP metadata/ACS/EntityID |
| **broker-oidc** facing IdP | **SAML SP** | Onboarded IdP EntityID and **signing certificate** |
| **broker-oidc** facing Spring | **OIDC OP** | OIDC client registration, redirect URI, client authentication |
| **Spring Boot app** | **OIDC Relying Party** / OAuth2 Client | **Broker** issuer/JWKS, valid ID Token for the exact client |
| **Business database** | Authorization decision | Local account, tenant, and roles from approved sources |

A validly signed SAML Assertion is processed by the broker **only after verifying the exact signed element**; a validly signed OIDC ID Token only lets the app identify the broker user; `/admin` and owner/resource permissions are still decided by the application.

### Two Easily Confused URL Pairs

**Upstream SAML:**

- IdP EntityID: exact `EntityID` value from SAML IdP metadata.
- IdP SSO URL: where the broker sends `AuthnRequest`.
- Broker SAML SP EntityID: identifier inside broker SP metadata.
- Broker SAML ACS: where the IdP posts **`SAMLResponse`**, **not** the Spring app.

**Downstream OIDC:**

- Broker issuer: `issuer` value from OIDC Discovery JSON.
- Broker authorization/token/JWKS endpoints: advertised by Discovery.
- OIDC client ID: Spring app's client registered on the broker.
- Spring redirect URI: where the broker sends the **authorization code**, **not** a `SAMLResponse`.

**Never send a `SAMLResponse` to `/login/oauth2/code/broker`; never send an OIDC code to the broker SAML ACS.**

## 3. Preparing the Local Lab

The lab uses **one Keycloak server with two realms** to reproduce both protocols without needing an enterprise IdP account:

- **corp-saml** realm: simulates the corporate SAML IdP.
- **broker-oidc** realm: consumes upstream SAML and issues downstream OIDC.
- Spring Boot Java 17 app runs on the host at port **8081**.
- Keycloak runs on port **8080**; both browser and Spring host reach `http://localhost:8080`.

**Trust note:** two realms inside one process are a **functional/protocol simulation only**—they do not model network isolation, operations, CA separation, or attack surfaces of independent IdPs. Production must use distinct HTTPS endpoints/domains with certificates, key rotation, availability, and network policies.

### Prerequisites

- JDK 17, Maven, Docker or Podman, and a browser able to reach localhost.
- Ports 8080 and 8081 free.
- Permission to start containers and create two realms/clients in a **dedicated lab**.
- **Lab-only accounts**—never real users, production SAML metadata, or production secrets.
- Optional `curl` and `jq` for JSON inspection commands.

### Starting Keycloak

With Docker locally:

~~~bash
docker run --rm --name kc-broker-lab \
  -p 127.0.0.1:8080:8080 \
  -e KC_BOOTSTRAP_ADMIN_USERNAME=lab-admin \
  -e KC_BOOTSTRAP_ADMIN_PASSWORD=lab-only-change-this \
  quay.io/keycloak/keycloak:26.8.2 \
  start-dev --hostname=http://localhost:8080
~~~

**Explanation:**

- `start-dev` uses development defaults and must **never** go into production verbatim.
- Bind strictly to **127.0.0.1**, never exposing `0.0.0.0`.
- Example admin credentials are solely for entering the lab Admin Console; never reuse them on real servers.
- `--rm` discards container data on stop; to persist across runs, configure a persistent volume/DB per Keycloak docs.
- Run the Spring app on the **host**. If you run the app in another container, `localhost` inside that container points to itself rather than the broker; ensure consistent DNS/hostnames and routing so the issuer URL works for both browser and Spring.

Open the Keycloak Admin Console at `http://localhost:8080/admin/` and log in as **lab-admin**.

Keycloak 26.x may rearrange certain buttons; the key sections to locate are **Realms, Identity providers, Clients, Client authentication, Standard flow, Credentials, SAML Metadata/Endpoints, First broker login**.

## 4. Setting Up Realm `corp-saml` as the IdP

### Step 4.1. Create the Realm

In the Keycloak Admin Console, select **Create realm** and name it **corp-saml**. This realm acts as the **SAML Identity Provider**.

Once created, expected endpoints for the lab host are:

~~~text
IdP metadata/descriptor:
http://localhost:8080/realms/corp-saml/protocol/saml/descriptor

IdP SSO endpoint:
http://localhost:8080/realms/corp-saml/protocol/saml

Common IdP realm base / entity ID:
http://localhost:8080/realms/corp-saml
~~~

**Always read `EntityDescriptor entityID`, `SingleSignOnService` Binding/Location, and `X509Certificate` from actual metadata**, rather than trusting a guessed URI just because it looks plausible. Keycloak can change hostnames/context paths behind a reverse proxy.

### Step 4.2. Create a Test User

Under **corp-saml → Users → Add user**:

- Username: `alice.lab`
- Email: `alice@lab.invalid` (synthetic dummy data only)
- Enabled: ON
- Credentials: set a test password and toggle "Temporary" OFF so first login does not force a password change.
- Do not assign `ROLE_ADMIN`, and do not configure production MFA/secrets.
- Optionally create `bob.lab` for negative identity-linking tests.

**Do not manually pre-create a matching broker user yet** if you want to observe the first-broker-login flow. Production, by contrast, may mandate **pre-provisioned users / approved account linking**; see section 10.

### Step 4.3. Do Not Create the SAML Client Too Early

A SAML IdP needs the **broker's SP EntityID and ACS**. We will create the identity-provider entry on the broker first, obtain its official **SP Descriptor**, and then import it into `corp-saml`. That avoids EntityID/ACS typos compared to manual entry.

## 5. Setting Up `broker-oidc` as the Upstream SAML SP

### Step 5.1. Create Realm `broker-oidc`

Create a new realm named **broker-oidc**. This realm serves two roles:

1. **SAML v2.0 Identity Provider connection** to `corp-saml`.
2. **OIDC OP** serving the Spring Boot client.

One Keycloak realm can act as a broker and issue OIDC tokens to multiple clients. In the lab, both realms live on the same Keycloak instance yet maintain separate per-realm sessions, keys, and configs.

### Step 5.2. Register the SAML Identity Provider

In **broker-oidc → Identity providers → Add provider → SAML v2.0**, configure:

| Field | Lab Value / Policy |
| --- | --- |
| Alias | `corp-saml-upstream` |
| Enabled | ON |
| Service Provider Entity ID | Keep the broker-generated value or set an explicit URI, then **use the exact SP descriptor** |
| Identity Provider Entity ID | Read from `corp-saml` metadata; **never leave blank** |
| Single Sign-On Service URL | From IdP metadata, e.g., `http://localhost:8080/realms/corp-saml/protocol/saml` |
| NameID Policy Format | Persistent if supported by upstream, or an approved stable attribute |
| Principal Type | Verified Subject NameID or Attribute with appropriate stability |
| Want Assertions Signed | ON **when** the IdP is configured to sign Assertions |
| Validate Signature | ON; reject unsigned Assertions/Responses per trust policy |
| Signing certificate | Public verification cert of **corp-saml**, imported from trusted metadata |
| Trust Email | OFF for safe lab defaults, especially without an email-verification policy |
| Store Tokens | OFF unless required by use case with secured storage |
| First Login Flow | Default to observe lab behavior; production must review against account takeover |

**Two settings that must never be left blank in production:** `Identity Provider Entity ID` and **signature verification using a trusted signing key**. Keycloak docs note that leaving Identity Provider Entity ID blank can skip Issuer checks.

**Want Assertions Signed** must match how the IdP actually signs. When enabled, configure the IdP's SAML client to **sign assertions**, import the right cert, and test. If an IdP signs only the Response under a different contract, select a compatible profile/trust policy—**never turn off Validate Signature globally just to make it run**.

### Step 5.3. Retrieve the Broker SP Metadata and ACS

After saving the identity-provider alias, open the connection's **Endpoints → SAML 2.0 Service Provider Metadata** link (depending on UI version).

Keycloak's descriptor URL:

~~~text
http://localhost:8080/realms/broker-oidc/broker/corp-saml-upstream/endpoint/descriptor
~~~

The SAML ACS advertised in that metadata corresponds to:

~~~text
http://localhost:8080/realms/broker-oidc/broker/corp-saml-upstream/endpoint
~~~

**Cross-check the descriptor before registering:** `EntityDescriptor/@entityID` must match the broker's SP EntityID, and `AssertionConsumerService` Location/Binding must match IdP settings. SP metadata is the registration input for the upstream IdP; **it is neither OIDC Discovery nor the Spring redirect URI**.

On the host, you can inspect the lab metadata:

~~~bash
curl -fsS \
  http://localhost:8080/realms/broker-oidc/broker/corp-saml-upstream/endpoint/descriptor
~~~

Never paste internal metadata output onto public paste sites. In production, fetch metadata only from allowlisted sources and verify provenance/trust; HTTPS and key rotation must follow policy.

## 6. Registering the Broker SP as a SAML Client of `corp-saml`

Return to **corp-saml → Clients → Create client**.

- Choose **Client type: SAML**.
- **Import the SP descriptor** from the broker's URL or metadata file (per UI/import flow).
- Verify **Client ID / EntityID** equals `EntityDescriptor/@entityID`, not the OIDC client ID.
- Verify **Master SAML Processing URL** or ACS POST URL matches the metadata—the broker's SAML ACS.
- Select matching POST/Redirect bindings on both sides; SAML Responses typically use HTTP-POST.
- Under SAML signing settings, enable **sign assertions** (and/or sign documents) per the broker's policy; in this lab the target is a **signed Assertion** so Want Assertions Signed + Validate Signature on the broker are exercised meaningfully.
- Verify modern signature algorithms; avoid deprecated/discouraged SHA-1 algorithms.
- Do not enable encryption before configuring and testing broker decryption credentials, though production may require `EncryptedAssertion`.
- Permit only the registered broker SP; the IdP must never send Assertions to arbitrary request-supplied ACS URLs.

**Key debugging tip:** if the broker reports `invalid signature`, the cause is usually a mismatched key/cert, the IdP SAML client not signing the Assertion, or a profile signing only the Response. Never "fix" it by disabling signature checking. Cross-check signing certs and signed elements against **SAML metadata**.

### Enable the IdP Signing Key on the Broker

In the broker's SAML v2.0 connection:

1. Open the metadata URL of **corp-saml**.
2. Extract the **IdP signing public certificate** marked `use="signing"`.
3. Import the cert or enable metadata key refresh per version capabilities and **trust policy**.
4. Verify the SP stores the IdP's trusted key; `KeyInfo` inside `SAMLResponse` is only sender-provided data, **never a self-proving trust anchor**.
5. When rotating the IdP signing key, plan overlap and new-key approval; never blindly trust arbitrary certs embedded in XML.

**Expected:** `AuthnRequest` flows from broker to `corp-saml`, and the signed Response/Assertion returns from `corp-saml` to the **broker ACS**, never directly to Spring.

## 7. Creating the Downstream OIDC Client for Spring Boot

In **broker-oidc → Clients → Create client**:

| Setting | Value |
| --- | --- |
| Client type | OpenID Connect |
| Client ID | `spring-oidc-lab` |
| Client authentication | **ON** for server-side confidential client |
| Standard Flow | **ON** (Authorization Code) |
| Direct Access Grants | OFF |
| Implicit Flow | OFF |
| Service Account Roles | OFF if not using M2M |
| Valid redirect URIs | `http://localhost:8081/login/oauth2/code/broker` |
| Root/Home URL | `http://localhost:8081` (if prompted) |
| Web origins | `*` is unnecessary for server-side MVC login |
| PKCE method | `S256` when Spring client sends an `S256` `code_challenge` |
| Client secret | Copy from **Credentials**; pass to Spring host only via env/secret store |

In the Java example below, we **explicitly enable PKCE S256** via `DefaultOAuth2AuthorizationRequestResolver`, so the Keycloak client can enforce `S256`. Never add a custom redirect URI without updating both the OIDC client registration and Spring's callback filter together.

### URLs to Verify

~~~text
Broker issuer:
http://localhost:8080/realms/broker-oidc

OIDC Discovery:
http://localhost:8080/realms/broker-oidc/.well-known/openid-configuration

Typical authorization endpoint:
http://localhost:8080/realms/broker-oidc/protocol/openid-connect/auth

Typical token endpoint:
http://localhost:8080/realms/broker-oidc/protocol/openid-connect/token

Typical JWKS endpoint:
http://localhost:8080/realms/broker-oidc/protocol/openid-connect/certs

Spring login initiation:
http://localhost:8081/oauth2/authorization/broker

Spring callback:
http://localhost:8081/login/oauth2/code/broker
~~~

**Always read Discovery JSON** instead of assuming every Keycloak deployment uses identical hostnames/context paths:

~~~bash
curl -fsS \
  http://localhost:8080/realms/broker-oidc/.well-known/openid-configuration
~~~

With `jq`:

~~~bash
curl -fsS \
  http://localhost:8080/realms/broker-oidc/.well-known/openid-configuration \
  | jq '{issuer, authorization_endpoint, token_endpoint, jwks_uri}'
~~~

**Invariant:** Spring's `issuer-uri` must match the broker's published `issuer` and the ID Token's `iss` claim verbatim. `aud` must contain **`spring-oidc-lab`**, not the SAML SP EntityID.

### Broker Routing the User to the SAML IdP

On the broker login page, users can click the IdP alias button `corp-saml-upstream`, or an admin can set a **Default Identity Provider** in the authentication flow/broker settings. Some Keycloak flows accept `kc_idp_hint` to preselect a provider; that is a **routing hint**, not proof of authentication.

**In the lab, click the SAML IdP button manually** to observe every hop. Never let browser query parameters or headers select Spring's IdP trust, JWKS, or issuer; the issuer must be configured server-side.

## 8. Creating a Runnable Spring Boot 3.5 / Java 17 Project

This compact project uses **Spring MVC** and **Spring Security OAuth2 Client**; there is no need for the SAML2 Service Provider dependency in Spring because the broker handles SAML.

~~~text
saml-behind-broker-lab/
  pom.xml
  src/main/resources/application.yml
  src/main/java/com/example/brokerlab/
    BrokerLabApplication.java
    SecurityConfig.java
    DemoController.java
~~~

### 8.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>saml-behind-broker-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
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
~~~

**Version note:** Spring Boot 3.5.7 fits Java 17 and Spring Security 6.x for the lab. In production, use an **organization-supported BOM patch kept up-to-date with security fixes** rather than treating the lab version pin as a permanent recommendation.

### 8.2. `application.yml`

~~~yaml
server:
  port: 8081
  forward-headers-strategy: none
  servlet:
    session:
      cookie:
        http-only: true

spring:
  security:
    oauth2:
      client:
        registration:
          broker:
            provider: broker
            client-id: spring-oidc-lab
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid,profile,email
        provider:
          broker:
            issuer-uri: http://localhost:8080/realms/broker-oidc

logging:
  level:
    root: INFO
    org.springframework.security: WARN
    org.opensaml: WARN
~~~

- `client-id` must match Keycloak **broker-oidc OIDC client**, not the SAML SP EntityID.
- Secret comes from environment variable `OIDC_CLIENT_SECRET`, never committed to Git.
- `openid` activates Spring's **OIDC authentication** and `OidcUserService`.
- `provider.broker.issuer-uri` points to the **broker** (not the SAML IdP).
- `redirect-uri` uses the default template, resolving callback on port **8081**.
- `forward-headers-strategy: none` suits direct host lab execution only; production behind a reverse proxy requires trusted forwarded-header handling and a public HTTPS URL.
- In an HTTP-only lab, `Secure` cookies are omitted; production requires HTTPS and appropriate `Secure`/`SameSite`/CSRF policies.

### 8.3. Main Class

**`src/main/java/com/example/brokerlab/BrokerLabApplication.java`**

~~~java
package com.example.brokerlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BrokerLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(BrokerLabApplication.class, args);
    }
}
~~~

### 8.4. `SecurityConfig`: OIDC Login and PKCE S256

**`src/main/java/com/example/brokerlab/SecurityConfig.java`**

~~~java
package com.example.brokerlab;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestCustomizers;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ClientRegistrationRepository registrations)
            throws Exception {

        DefaultOAuth2AuthorizationRequestResolver resolver =
            new DefaultOAuth2AuthorizationRequestResolver(
                registrations, "/oauth2/authorization");

        resolver.setAuthorizationRequestCustomizer(
            OAuth2AuthorizationRequestCustomizers.withPkce());

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .anyRequest().authenticated())
            .oauth2Login(oauth -> oauth
                .authorizationEndpoint(endpoint -> endpoint
                    .authorizationRequestResolver(resolver)));

        return http.build();
    }
}
~~~

**Exact explanation:**

1. `DefaultOAuth2AuthorizationRequestResolver` handles `/oauth2/authorization/broker`.
2. `withPkce()` adds `code_challenge`/`code_challenge_method` and stores the verifier in `OAuth2AuthorizationRequest` for token exchange.
3. `oauth2Login()` configures Authorization Code authentication; `state`, OIDC `nonce`, and token validation run via Spring Security's flow.
4. There is no `.saml2Login()` in Spring; the SAML ACS lives on the **broker**.
5. Neither `csrf.disable()` nor `permitAll` on `/api/**` is enabled.
6. `/api/admin` requires `ROLE_ADMIN`; the lab never auto-assigns this role from SAML/Keycloak groups, so a valid login is still denied access to admin.
7. Spring Security sets up `HttpSession`/`SecurityContext` after login; this code never creates `Authentication` directly from the OIDC query `code`.

**No client secrets are hardcoded.** These files depend on Maven dependencies and a running broker; they form a **minimal complete integration project**, not plain Java runnable standalone with `javac`.

### 8.5. `DemoController`: Inspecting the OIDC Principal Without Dumping Tokens

**`src/main/java/com/example/brokerlab/DemoController.java`**

~~~java
package com.example.brokerlab;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    private static final String BROKER_ISSUER =
        "http://localhost:8080/realms/broker-oidc";

    @GetMapping("/")
    public String home() {
        return "Lab OIDC -> Broker -> SAML IdP";
    }

    @GetMapping("/api/me")
    public Map<String, Object> me(
            @AuthenticationPrincipal OidcUser oidcUser) {
        return Map.of(
            "authenticated", true,
            "oidcIssuerIsBroker",
                BROKER_ISSUER.equals(
                    oidcUser.getIdToken().getIssuer().toString()),
            "oidcSubjectPresent",
                !oidcUser.getSubject().isBlank(),
            "samlHandledAtBroker", true);
    }

    @GetMapping("/api/admin")
    public Map<String, String> admin() {
        return Map.of("result", "admin-only");
    }
}
~~~

`/api/me` **never prints raw ID Tokens, access tokens, `SAMLResponse`, emails, or `NameID`**. `samlHandledAtBroker=true` is merely **lab architecture metadata**, not technical proof of upstream SAML on a specific request: proving the upstream path requires inspecting sanitized events/traces **at the broker and IdP**. When an app supports non-SAML IdPs as well, never use this demo field in authorization decisions.

**Note:** Spring Security already validated the ID Token before creating `OidcUser`; the issuer comparison in the controller is illustrative and does not replace built-in validation. Never decode a JWT from a request parameter yourself to construct a principal.

### 8.6. Starting the Spring App

On the host, set the secret copied from the broker OIDC client's **Credentials** tab; never paste secrets into shared logs/history. Example in a test shell (depending on OS):

~~~bash
export OIDC_CLIENT_SECRET="the-lab-client-secret-from-keycloak"
mvn spring-boot:run
~~~

In PowerShell:

~~~powershell
$env:OIDC_CLIENT_SECRET = "the-lab-client-secret-from-keycloak"
mvn spring-boot:run
~~~

**The secret string is an instructional placeholder you must replace with your lab value**, not a real credential issued in this article. Use a secret store or uncommitted environment file in serious workflows.

Open in a browser:

~~~text
http://localhost:8081/
http://localhost:8081/api/me
http://localhost:8081/oauth2/authorization/broker
~~~

Visiting `/api/me` unauthenticated redirects the browser to OIDC login at the broker. On Keycloak broker, choose `corp-saml-upstream`, complete login as `alice.lab` in `corp-saml`, and step through the first-broker-login screen if shown. After callback, `/api/me` should return JSON like:

~~~json
{
  "authenticated": true,
  "oidcIssuerIsBroker": true,
  "oidcSubjectPresent": true,
  "samlHandledAtBroker": true
}
~~~

**This is expected output when the entire lab is properly configured**, not evidence of a live E2E run inside this document. Verify live status via browser/network tools and sanitized test logs.

Try `/api/admin`: even though OIDC login succeeded, lacking an app-granted `ROLE_ADMIN` must return **403 / deny per policy**, never auto-accepting simply because the SAML user or broker OIDC client held a group/role.

## 9. Tracing the Flow Across Every Hop

### Hop A – Spring App Initiates OIDC

With no authenticated `HttpSession`:

~~~text
GET /api/me
  -> 302 /oauth2/authorization/broker
  -> 302 http://localhost:8080/realms/broker-oidc/
          protocol/openid-connect/auth?client_id=...
                                   &response_type=code
                                   &scope=openid...
                                   &state=...
                                   &code_challenge=...
                                   &code_challenge_method=S256
~~~

**Never log full URLs containing `state`, `code`, cookies, or tokens.** Inspect them only inside test-environment browser DevTools, and discard HAR files containing credentials afterward.

### Hop B – Broker Delegates to the SAML IdP

When selecting `corp-saml-upstream`:

~~~text
Browser -> broker SAML IdP connection
Broker  -> SAML AuthnRequest sent to IdP SSO endpoint
Browser -> corp-saml login
IdP     -> signed SAMLResponse (HTTP POST)
Browser -> broker ACS /broker/corp-saml-upstream/endpoint
~~~

The broker checks:

- SAML IdP EntityID / Issuer matches configuration.
- XMLDSig signature/digest and IdP verification certificate are trusted.
- Audience = broker SP EntityID; Destination/Recipient = broker SAML ACS.
- Time Conditions, SubjectConfirmation, `InResponseTo`, and unique/replay IDs per profile.
- XML parser safety (no XXE, no unsigned sibling Assertions).
- Stable `NameID` / selected principal attribute before mapping to a broker account.

### Hop C – Broker Issues OIDC to Spring

Once upstream SAML is verified, Keycloak executes its first/post-broker-login flow, creates or links the broker user, and resumes **OIDC Authorization Code**.

Spring receives the callback:

~~~text
GET http://localhost:8081/login/oauth2/code/broker
     ?code=<one-time-opaque-code>&state=<bound-state>

Spring -> broker token endpoint (backchannel, client_secret_basic)
Broker -> ID Token/Access Token response
Spring -> validate broker ID Token, create OidcUser
Spring -> save SecurityContext/HttpSession
Browser -> /api/me returns authenticated JSON
~~~

**The ID Token should contain:**

| Claim | Expected | Control |
| --- | --- | --- |
| `iss` | `http://localhost:8080/realms/broker-oidc` | Spring issuer validation |
| `sub` | Broker-local stable subject | Not necessarily equal to SAML `NameID` |
| `aud` | Includes `spring-oidc-lab` | Exact OIDC client |
| `exp`, `iat` | Valid timestamps | Token lifetime |
| `nonce` | Matches request when used | OIDC login correlation |
| `azp` if present | Authorized client | Validated per OIDC semantics |
| `email`, `name` | Optional | Never use as global account ID |
| `groups`/`roles` | Optional broker mapping | Never auto-mint app permissions |

**Never send an ID Token to a backend API as an access token** simply because it is a JWT. If your app exposes resource-server endpoints accepting Bearer tokens, issue an access token with the proper `aud`/`scope`/`issuer` and validate it independently.

## 10. First Broker Login, Account Linking, and Authorization

When the SAML IdP returns `NameID`, the broker maps the upstream user to an account in the broker realm. The **default first-broker-login flow** may auto-create an account if none exists—useful in fresh lab realms to observe the end-to-end flow.

**Production cannot treat email auto-linking as safe by default.** Determine:

1. Which format is SAML `NameID`: persistent or transient? If transient, never use it as a persistent lookup key.
2. What is the broker's external user lookup key? Must be stable upstream `(source IdP alias, verified issuer, immutable subject)`.
3. Is the broker user ↔ upstream user link proven/approved? If emails collide across distinct issuers, require reauthentication/approval rather than auto-merging.
4. Does the Spring app maintain local business user IDs and tenants? Map `(broker iss, broker sub, tenant)` → approved `local user_id`.
5. Which permissions come from the local DB? Never auto-map `groups=admins` or a SAML Attribute to `ROLE_ADMIN` outside an allowlist/policy.
6. When a user is disabled at the IdP or local DB, are broker/app sessions revoked immediately or only at TTL?
7. Changing an IdP alias, SAML `NameID` format, or OIDC client/sector can alter `sub`/links; assess impact before deploying.

### Illustrative Mapping Schema

~~~sql
CREATE TABLE local_user (
  id BIGINT PRIMARY KEY,
  tenant_id VARCHAR(80) NOT NULL,
  enabled BOOLEAN NOT NULL
);

CREATE TABLE external_identity_link (
  id BIGINT PRIMARY KEY,
  local_user_id BIGINT NOT NULL REFERENCES local_user(id),
  issuer VARCHAR(500) NOT NULL,
  subject VARCHAR(500) NOT NULL,
  tenant_id VARCHAR(80) NOT NULL,
  approved BOOLEAN NOT NULL,
  UNIQUE (issuer, subject, tenant_id)
);
~~~

**In a real application**, look up links only after Spring validates the OIDC ID Token. Enforce tenant consistency, transactions, unique constraints, account-linking audits/approvals, and never auto-create admins on missing mappings.

An `email_verified=true` claim emitted by the broker may merely reflect upstream email-trust settings—it does **not** prove the same person across issuers. Review Keycloak's `Trust Email` and first-login flow before migrating.

### Role Mapping and Local Authorization

In the lab, `oauth2Login` creates an OIDC `Authentication`; since the app does not map DB roles yet, `/api/admin` must be denied. To enforce real authorization:

- In `OidcUserService` or a custom authentication success handler, extract the **validated** `oidcUser.getIdToken().getIssuer()` and `oidcUser.getSubject()`.
- Look up the user link/tenant, enabled/locked status, and allowed roles in the database.
- Convert policy results into `GrantedAuthority` values using deny-by-default and approved data sources.
- Never trust unverified usernames/emails or browser `X-Role` headers for permissions.
- Never mint a brand-new local user ID on every login if SAML `NameID` / broker `sub` rotates.
- If MFA is required, check `acr`/`amr`/`auth_time` mapped faithfully by the broker rather than assuming the SAML IdP performed step-up.

**The broker's OIDC `sub` must never be treated as the SAML `NameID`.** The broker is a distinct issuer with its own subject policy and may link multiple external identities under one broker account.

## 11. Standalone Java 17: Simulating Two Trust Layers and Identity Linking

To separate "SAML verified by broker" from "OIDC verified by Spring", we build a model **without network calls or XML/JWT parsing**. Two verification booleans represent real library outputs; **this is not a cryptographic validator**.

**File: `BrokerTrustChainDemo.java`**

~~~java
import java.util.Map;

public final class BrokerTrustChainDemo {

    private static final String SAML_ISSUER =
        "http://localhost:8080/realms/corp-saml";
    private static final String BROKER_ISSUER =
        "http://localhost:8080/realms/broker-oidc";
    private static final String OIDC_CLIENT = "spring-oidc-lab";

    record SamlEvidence(
        String issuer, boolean verifiedSignature,
        boolean validRecipient, String upstreamSubject) { }

    record OidcEvidence(
        String issuer, String audience, boolean verifiedSignature,
        boolean validNonce, String brokerSubject) { }

    private static final Map<String, String> APPROVED =
        Map.of("broker-sub-42", "LOCAL-USER-42");

    static String authenticate(SamlEvidence upstream,
            OidcEvidence downstream) {

        if (!SAML_ISSUER.equals(upstream.issuer())
                || !upstream.verifiedSignature()
                || !upstream.validRecipient()
                || !"saml-user-42".equals(upstream.upstreamSubject())) {
            return "DENY_UPSTREAM_SAML";
        }

        if (!BROKER_ISSUER.equals(downstream.issuer())
                || !OIDC_CLIENT.equals(downstream.audience())
                || !downstream.verifiedSignature()
                || !downstream.validNonce()) {
            return "DENY_DOWNSTREAM_OIDC";
        }

        return APPROVED.getOrDefault(downstream.brokerSubject(),
            "DENY_UNLINKED_USER");
    }

    public static void main(String[] args) {

        SamlEvidence validSaml = new SamlEvidence(
            SAML_ISSUER, true, true, "saml-user-42");
        OidcEvidence validOidc = new OidcEvidence(
            BROKER_ISSUER, OIDC_CLIENT, true,
            true, "broker-sub-42");

        System.out.println("baseline=" +
            authenticate(validSaml, validOidc));

        System.out.println("badSamlSignature=" +
            authenticate(new SamlEvidence(
                SAML_ISSUER, false, true, "saml-user-42"),
                validOidc));

        System.out.println("wrongSamlIssuer=" +
            authenticate(new SamlEvidence(
                "https://other-idp.invalid", true, true, "saml-user-42"),
                validOidc));

        System.out.println("wrongBrokerIssuer=" +
            authenticate(validSaml, new OidcEvidence(
                "https://other-broker.invalid", OIDC_CLIENT,
                true, true, "broker-sub-42")));

        System.out.println("wrongOidcAudience=" +
            authenticate(validSaml, new OidcEvidence(
                BROKER_ISSUER, "other-client",
                true, true, "broker-sub-42")));

        System.out.println("badNonce=" +
            authenticate(validSaml, new OidcEvidence(
                BROKER_ISSUER, OIDC_CLIENT,
                true, false, "broker-sub-42")));

        System.out.println("unknownUser=" +
            authenticate(validSaml, new OidcEvidence(
                BROKER_ISSUER, OIDC_CLIENT,
                true, true, "unlinked-broker-sub")));
    }
}
~~~

Run with plain JDK 17:

~~~bash
javac BrokerTrustChainDemo.java
java BrokerTrustChainDemo
~~~

**Deterministic stdout from the code:**

~~~text
baseline=LOCAL-USER-42
badSamlSignature=DENY_UPSTREAM_SAML
wrongSamlIssuer=DENY_UPSTREAM_SAML
wrongBrokerIssuer=DENY_DOWNSTREAM_OIDC
wrongOidcAudience=DENY_DOWNSTREAM_OIDC
badNonce=DENY_DOWNSTREAM_OIDC
unknownUser=DENY_UNLINKED_USER
~~~

**Essential limitations:** `verifiedSignature` and `validNonce` are **mock evidence only**; in a real application they must come from the **broker's SAML validator** and **Spring Security's OIDC authentication pipeline**, never from query/header/body booleans sent by clients. The program checks no XMLDSig, JWKS/JWT signatures, TLS, audience/recipient timestamps, or replay; run separate E2E tests across IdP, broker, and app.

## 12. Integration Test Suite from Browser to IdP and Spring

### Mandatory Positive Control

1. Sign out of old sessions and use a clean browser profile.
2. Open `/api/me` on the Spring app; unauthenticated requests must redirect to the broker.
3. Choose `corp-saml-upstream`; browser navigates to `corp-saml`.
4. Log in as `alice.lab`; IdP signs Assertion/Response per contract and POSTs to the **broker ACS**.
5. Broker verifies SAML; first broker login links/creates a lab user.
6. Broker sends authorization code back to **Spring OIDC callback**.
7. Spring exchanges code and validates the broker's ID Token.
8. `/api/me` returns `authenticated=true`, `oidcIssuerIsBroker=true`, `oidcSubjectPresent=true`.
9. `/api/admin` remains denied due to lacking `ROLE_ADMIN` from local policy.
10. Inspect **sanitized** broker events/traces confirming source `corp-saml-upstream`; never rely on the controller's JSON field `samlHandledAtBroker=true` as proof.

### Negative Test Matrix

| # | Test | Layer That Must Block | Expected |
| --- | --- | --- | --- |
| 1 | Call `/api/me` unauthenticated | Spring auth entry point | Redirect/login, no private data |
| 2 | Validly signed SAML from IdP | Broker SAML validator | Positive SAML validation |
| 3 | Response with invalid signature | Broker | Rejected before creating broker identity |
| 4 | Wrong SAML issuer with valid signature | Broker | Reject issuer |
| 5 | Untrusted SAML signing key B | Broker | Reject key B, even if `KeyInfo` B is present |
| 6 | SAML Audience differs from broker SP EntityID | Broker | Reject |
| 7 | SAML Destination/Recipient differs from broker ACS | Broker | Reject |
| 8 | Expired Assertion / future `NotBefore` | Broker | Reject |
| 9 | `InResponseTo` mismatches request | Broker | Reject per SP-initiated contract |
| 10 | Replay used Response ID | Broker | Reject replay |
| 11 | XML Signature Wrapping / duplicate IDs | Broker | Never consume unsigned Assertion |
| 12 | Unapproved SAML signing key change in metadata | Broker | Never auto-trust new key |
| 13 | Unapproved broker user link | Broker/app policy | Review or deny |
| 14 | Email collides with another account | Broker first-login flow | Never blindly auto-link |
| 15 | Transient SAML `NameID` changes every login | Broker link policy | Prevent account takeover / policy-violating duplicates |
| 16 | Untrusted broker OP ID Token signing key B | Spring OIDC | Reject invalid/untrusted signature |
| 17 | ID Token issuer differs from broker | Spring OIDC | Reject |
| 18 | ID Token audience differs from `spring-oidc-lab` | Spring OIDC | Reject |
| 19 | Expired ID Token / invalid `nbf` | Spring OIDC | Reject |
| 20 | OIDC `nonce`/`state` mismatch | Spring OIDC | Reject callback, no authentication |
| 21 | Authorization code replay | Broker token endpoint | Reject reused code |
| 22 | Wrong PKCE verifier | Broker token endpoint | Reject |
| 23 | Wrong client secret | Broker token endpoint | Reject |
| 24 | Unregistered redirect URI | Broker authorization endpoint | Reject |
| 25 | Spoofed `X-Forwarded-Host` alters redirect | Trusted edge / Spring | No open redirect / callback poisoning |
| 26 | Send `SAMLResponse` to Spring OIDC callback | Spring/OIDC | Never parse SAML itself |
| 27 | Send OIDC code to SAML broker ACS | Broker/SAML | Never accept as `SAMLResponse` |
| 28 | Authenticated OIDC user calls `/api/admin` | Spring authorization | Deny if lacking app role |
| 29 | Disabled local user | Local policy | Deny even with valid broker ID Token |
| 30 | Cross-tenant object ID | App resource policy | Deny |
| 31 | SAML IdP fails to meet `AuthnContext`/MFA | Broker/step-up | Reject/reauth per policy |
| 32 | Logout on Spring app only | Session layer | Local session ends; never promise upstream SLO |
| 33 | Broker logout while IdP session stays alive | Broker/IdP | Re-login UX per contract |
| 34 | Broker/IdP outage | Spring/broker | Fail closed; never accept fake headers |
| 35 | SAML IdP signing cert rotated | Broker trust | Policy-compliant overlap, never fail-open |
| 36 | `SAMLResponse`/Authorization Code/ID Token in logs | Logging pipeline | No leaked secrets/PII |
| 37 | Replay old session after account disabled | App/session policy | Deny per revocation SLA |
| 38 | Browser blocks third-party cookies | Session/SSO UX | No login loop; debug cookie policy |
| 39 | Different OIDC client/sector/`sub` | Broker/app linking | Never auto-map by email |
| 40 | Broker identity changes while local `user_id` stays right | Local DB mapping | Retain roles/ownership when approved |

**Proper QA grading:** "HTTP 302/403" alone does not prove signatures or issuers were checked. Build a **valid positive baseline** first; for wrong SAML issuer, the document must be **re-signed with a trusted key** to isolate issuer validation. For untrusted keys, sign validly with another key while the broker trustset still holds only the approved key. Likewise for OIDC, expired/wrong-audience tests must not accidentally fail due to `invalid_state`.

### E2E and MockMvc Are Not Equivalent

- **MockMvc** can inject a synthetic `OidcUser` to test business authorization in the app, yet it bypasses Keycloak/SAML IdP, SAML signatures, OIDC JWKS, and real browser cookies.
- **Browser-based E2E** against a test IdP, broker, and HTTPS-like environment verifies end-to-end protocol routing, form POSTs, callbacks, cookies, and sessions.
- Separate **network tests** must verify TLS, DNS, proxy Host/Proto, egress/IdP metadata URLs, and callback allowlists.
- **Lab environments** may use localhost HTTP, whereas production mandates HTTPS, trusted proxies, and rotation/availability controls.

## 13. Sessions and Logout Across Three Layers

After login, three sessions may exist:

~~~text
Session A: Spring HttpSession/SecurityContext
Session B: Keycloak broker OP browser session
Session C: corp-saml IdP browser session
~~~

`session.invalidate()` in Spring guarantees ending only **A**. Broker RP-initiated logout can end **B** if properly configured, while **C** is not automatically cleared in every scenario. The broker may support upstream SAML Single Logout per policy, yet never promise 100% SLO if the IdP lacks support or compatible bindings.

**Testing:**

1. Log in and verify `/api/me` returns authenticated.
2. POST logout per Spring Security CSRF policy → app session A is invalidated.
3. Log in again: an active broker B or IdP C session may trigger rapid SSO without prompting for a password.
4. To log out of the broker too, configure `OidcClientInitiatedLogoutSuccessHandler` with `ClientRegistrationRepository` and the broker OP's `end_session_endpoint`, plus a trusted `post_logout_redirect_uri`.
5. Test logout propagation / SCIM session revocation separately if production requires "sign out everywhere".
6. Configure idle/absolute session timeouts, token TTLs, disabled-user revocation, and step-up MFA per policy.
7. Never write session cookies, logout tokens, or ID Token hints into logs.

**OIDC ID Token differs from an access token:** the ID Token serves client authentication in Spring; APIs using Bearer flows need a Resource Server and access tokens with the right audience/scope. Never treat OIDC login as authorization for every object.

## 14. Debugging by Where Errors Occur

| Symptom | Checkpoints and Common Causes | Remediation |
| --- | --- | --- |
| Spring startup fails loading issuer | OIDC Discovery URL unreachable, issuer mismatch | Check `.well-known/openid-configuration`, DNS/port |
| Browser loops back to broker login | Wrong redirect URI, `HttpSession`, cookie/domain/`SameSite` | Compare registered URI/callback, state/session |
| Broker lacks `corp-saml-upstream` button | IdP disabled / Hide on Login Page / default flow | Check identity provider alias/config |
| Broker reports `invalid requester` | Wrong SP EntityID/ACS on `corp-saml` client | Import descriptor from broker; match entityID |
| IdP did not sign Assertion | `Want Assertions Signed` vs. `Sign Assertions` mismatch | Enable signing on the right node; check cert |
| Broker rejects SAML signature | Wrong IdP cert / key rotation / algorithm / canonicalization | Import trusted signing cert; test signed fixture |
| Broker rejects Issuer | `Identity Provider Entity ID` wrong or blank | Set exact entityID from metadata; never skip check |
| Broker reports Audience/Recipient mismatch | IdP SAML client ACS differs from descriptor | Compare SP descriptor/binding/URL |
| Broker fails to link user | Transient `NameID`, attribute mismatch, first-login flow | Stable ID, approved linking |
| "Account already exists" after SAML login | Email/username collision in broker | Explicit proof/link approval; never enable Trust Email blindly |
| Wrong broker OIDC code callback | Wrong client redirect URI / `registrationId` | Exact `/login/oauth2/code/broker` |
| Token exchange `invalid_client` | Client secret / client auth method mismatch | Align secret/basic/credentials |
| PKCE error | Client requires `S256` while request lacks challenge/verifier | Verify `withPkce` and `S256` setting |
| Spring ID Token issuer invalid | Pointed to `corp-saml` IdP instead of broker | `issuer-uri` must be the **broker** |
| Spring audience invalid | Wrong OIDC client ID | `spring-oidc-lab` in `aud` |
| Spring `/api/me` 200, `/api/admin` 403 | OIDC login succeeded yet lacks business role | **Expected in lab**; check local policy |
| Logout still silently re-logs in via SSO | Broker/IdP session not logged out | Design layered logout |
| Docker localhost fails to connect | App/container resolve `localhost` differently | Fix host/DNS + canonical issuer |
| Logs contain XML/tokens | DEBUG/custom request logger dumps credentials | Audit redaction; disable raw logs |

### Observing Without Leaking Secrets

Log safely:

~~~text
event=SSO_AUTH_STARTED  client=broker        route=/api/me
event=BROKER_SAML_ACCEPTED provider=corp-saml-upstream
event=OIDC_LOGIN_SUCCESS issuerAlias=broker-oidc
event=AUTHZ_DENIED       route=/api/admin   reason=ROLE_MISSING
~~~

This is an **example custom event format**, not default Keycloak or Spring output. Never log raw `SAMLResponse`, `NameID`, `KeyInfo`, authorization codes, ID Tokens, client secrets, `Cookie`/`JSESSIONID`, or `RelayState`.

When deep debugging is required, use synthetic users and narrow lab-only loggers on a time-bound window; never leave OpenSAML TRACE or XML dumps enabled in production.

## 15. Production Hardening Compared to the Lab

| Area | In the Lab | In Production |
| --- | --- | --- |
| Transport | Localhost HTTP | HTTPS/TLS, trusted proxy chain, origin allowlist |
| Keycloak | `start-dev`, one instance / two realms | HA, persistent DB, backup/restore, hardening |
| Credentials | Lab admin, client secret env var | Secrets manager/rotation, admin MFA |
| SAML certificates | Test IdP signer | Trusted metadata onboarding, key rotation, cert expiry |
| SAML XML processing | Broker built-in | Patch OpenSAML/Keycloak; XXE/signature-wrapping tests |
| OIDC client | Confidential app, Code+PKCE | Strict redirect URIs, issuer/JWKS/`aud`/`nonce`/token TTL |
| Browser sessions | Local cookies | `Secure`/`HttpOnly`/`SameSite`/CSRF, session fixation protection |
| Identity link | First broker login creates lab user | Preapproved issuer+subject mapping, account-takeover prevention |
| Role policy | Admin denied by default | DB/tenant/object authorization, least privilege |
| Audit | Manual browser tests | Centralized safe events, anomaly detection, retention |
| Logout | Local session proof | RP-Initiated/Front/Back-channel/Upstream SLO contract |
| Resilience | Single local Keycloak server | DR, availability, fail closed, circuit breakers |
| Monitoring | Browser, stdout | Trace IDs, per-hop metrics, no raw credentials |
| API tokens | Unused in demo | Resource server access tokens with exact issuer/audience |

**Never lower trust just to "make the demo work":** if signature checks fail, fix metadata/certs/client settings instead of turning off Validate Signature or accepting unsigned `SAMLResponse`s. If an ID Token fails validation, never fall back to Base64-decoding JWT claims to build `Authentication`.

## 16. Exercise Completion Checklist

- [ ] Lab Keycloak 26.x runs on localhost and Admin Console is accessible.
- [ ] `corp-saml` realm exists with a lab-only test user.
- [ ] `broker-oidc` realm exists with SAML IdP alias `corp-saml-upstream`.
- [ ] Retrieved **broker SP descriptor** and registered it as a SAML client in `corp-saml`.
- [ ] IdP SAML EntityID/SSO URL and broker SP EntityID/ACS match actual metadata.
- [ ] Broker has a **non-empty Identity Provider Entity ID**, Validate Signature enabled, and trusted IdP signing certificate.
- [ ] IdP SAML client signs Assertions per profile (or follows an approved signing policy, never unsigned).
- [ ] Broker First Broker Login does not auto-link existing users by unverified email.
- [ ] OIDC client `spring-oidc-lab` on the broker permits Authorization Code, confidential auth, and exact registered redirect URI.
- [ ] Spring `issuer-uri` points to **broker-oidc**, not `corp-saml`.
- [ ] Spring OIDC client ID/secret/redirect URI match broker registration, and PKCE `S256` works.
- [ ] Spring Security uses `oauth2Login` without custom `SAMLResponse` parsing or disabled state/nonce checks.
- [ ] Browser traverses the SAML IdP → broker ACS → Spring OIDC callback.
- [ ] `/api/me` confirms the OIDC issuer is the broker and subject is present.
- [ ] `/api/admin` is not granted solely because OIDC login succeeded.
- [ ] Local account linking by approved broker `(iss, sub)` and tenant is designed.
- [ ] Negative tests cover SAML signature/issuer/audience/time and OIDC issuer/audience/state/PKCE.
- [ ] MockMvc authorization tests are clearly separated from real browser E2E federation tests.
- [ ] Logout across app/broker/IdP has an explicit contract without overpromising unsupported sync.
- [ ] Logs/proxies/APM store no raw tokens, `SAMLResponse`, `NameID`, cookies, or client secrets.
- [ ] Never carry `start-dev`, localhost HTTP, lab admin credentials, or unreviewed first-login policies into production.
- [ ] When finished, stop containers and delete lab secrets/files safely without impacting real systems.

**Conclusion:** In this architecture, **SAML terminates at the broker**, while Spring **speaks only OIDC with the broker**. Success is proven not merely by a browser showing a logged-in page, but by the full verification chain: valid upstream SAML signature/issuer/audience → broker creates/resolves the properly linked user → valid OIDC Authorization Code/PKCE and ID Token for the broker issuer/client audience → Spring creates `Authentication` → application authorization still blocks ungranted privileges. Two protocols, two trust pairs, and three session layers must each be tested independently.

## 17. Official References

- [Keycloak Docker Getting Started](https://www.keycloak.org/getting-started/getting-started-docker): containers, `KC_BOOTSTRAP_ADMIN_USERNAME`/`PASSWORD`, and `start-dev`.
- [Keycloak Server Administration – Identity Brokering](https://www.keycloak.org/docs/latest/server_admin/): SAML Identity Provider, broker alias, first login flow, token mapping, and account-linking security.
- [Keycloak SAML SP Metadata/Descriptor](https://www.keycloak.org/docs/latest/server_admin/#_identity_broker_saml): browser SAML broker endpoint and SAML SP descriptor.
- [Spring Security – OAuth2 Login Core Configuration](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/core.html): client registration, `issuer-uri`, redirect URI, and OAuth2 Login.
- [Spring Security – OAuth2 Login Advanced](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/advanced.html): authorization endpoint customization, `OidcUserService`, role mapping.
- [Spring Security – `OAuth2AuthorizationRequestCustomizers.withPkce`](https://docs.spring.io/spring-security/site/docs/6.4.12/api/org/springframework/security/oauth2/client/web/OAuth2AuthorizationRequestCustomizers.html): PKCE `S256` customizer.
- [Spring Boot – OAuth2 Client Configuration](https://docs.spring.io/spring-boot/reference/security/oauth2.html): `ClientRegistration` properties and security auto-configuration.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token issuer, subject, audience, nonce.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): issuer, authorization/token/JWKS endpoint metadata.
- [OASIS SAML 2.0 Specifications](https://docs.oasis-open.org/security/saml/v2.0/): `AuthnRequest`, Response/Assertion, XMLDSig, `NameID`, bindings.
- [RFC 7636 – Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636): `code_challenge`/`code_verifier` and `S256`.
- [RFC 9700 – OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): redirect, PKCE, and token security considerations.
- [OWASP SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html): signature, trust, audience, replay, and wrapping.
- [OWASP OAuth2 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): issuer/JWKS, state, redirect, and code-flow safety.