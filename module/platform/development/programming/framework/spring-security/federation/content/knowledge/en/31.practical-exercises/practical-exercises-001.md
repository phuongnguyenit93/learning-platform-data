# Building a SAML2 Service Provider with Metadata and a Test IdP

## 1. Practical Objectives and Acceptance Criteria

This exercise belongs to the **Comprehensive Practice** group in the **Spring Security - federation** module. Learners will build a **SAML 2.0 Service Provider (SP)** with Spring Boot/Spring Security, use **Keycloak** as a test **Identity Provider (IdP)**, exchange metadata in the right direction, run **SP-initiated SAML Web Browser SSO** login, inspect the session, and practice security failure scenarios. Spring acts as the SP/Relying Party; Keycloak issues Authentication Assertions under the SAML 2.0 protocol and handles user login.

Expected outcomes:

1. A Keycloak realm `saml-lab`, test user `alice`, and a registered SAML client.
2. A Java 17 Spring Boot application with `spring-security-saml2-service-provider`, `SecurityFilterChain.saml2Login()`, and `saml2Metadata()`.
3. Spring reads **IdP metadata** at `http://localhost:8081/realms/saml-lab/protocol/saml/descriptor`.
4. Keycloak uses the **SP EntityID** taken from **SP metadata** and the **ACS** with the exact HTTP-POST path.
5. Visiting `http://localhost:8080/me` in a browser with no session redirects to the IdP; after logging in, the SAMLResponse is verified by Spring, returning to `/me` with `authenticated=true`.
6. Understand why the IdP login screen appearing does **not** yet prove the SAMLResponse was verified by the SP.
7. Have a negative test checklist: invalid signature, issuer, audience, ACS, timestamp, request correlation, groups/roles, logout, and certificate rotation.
8. Have a standalone pure Java 17 example verifying the EntityID/ACS contract and allowlist-only group mapping.

**Version baseline used in this exercise:** Java 17; Maven 3.9+; Spring Boot **3.5.0** (Spring Security 6.x); Keycloak image **26.8.2**. This is a concrete version set for demonstrating the lab, **not a recommendation to keep old releases in production**. For real deployments, select an organization-approved patch release and re-test changed APIs. Spring Security 7 documentation introduces newer OpenSAML/principal APIs; do not arbitrarily mix and copy them into Boot 3.x.

> **Security scope:** the HTTP URLs, bootstrap `admin` account, and passwords in this exercise are **for localhost only**—never expose them to the Internet or use them as production configuration. Production environments require HTTPS, managed identities/secret stores, an IdP metadata trust policy, valid certificates, CSRF/session/replay protection, and audits that do not contain SAMLResponse or private keys.

## 2. Understanding the Components Before Setup

| Component | Role | Lab Parameter |
| --- | --- | --- |
| **Spring SP / Relying Party** | Generates AuthnRequest, receives and verifies SAMLResponse, and creates SecurityContext | `http://localhost:8080` |
| **Keycloak IdP / Asserting Party** | Authenticates the user, signs and issues SAMLResponse | `http://localhost:8081` |
| **SAML AuthnRequest** | SP asks the IdP to log the user in | Browser HTTP-Redirect to IdP |
| **SAMLResponse/Assertion** | IdP delivers authentication result, Subject, and attributes | Browser HTTP-POST to ACS |
| **IdP metadata** | IdP EntityID, SSO endpoint, public signing certificate | `/realms/saml-lab/protocol/saml/descriptor` |
| **SP metadata** | SP EntityID, ACS, supported bindings, signing/encryption descriptors if present | `/saml2/metadata/keycloak` |
| **RelyingPartyRegistration** | Spring-side SP–IdP relationship configuration | `registrationId=keycloak` |
| **Assertion Consumer Service (ACS)** | Spring endpoint receiving the POST SAMLResponse | `/login/saml2/sso/keycloak` |
| **SP EntityID** | Identifier used by the IdP as Client ID/Audience | `http://localhost:8080/saml2/service-provider-metadata/keycloak` |
| **Spring HTTP session** | Stores local authentication after SAML is validated | Cookie/session store, not the IdP session |

**A URL-shaped EntityID does not necessarily need to be opened by a browser as a web page.** EntityID is an identifier. The default SP EntityID may share the same form as the metadata-serving endpoint URL; when registering on the IdP, copy the exact `EntityDescriptor.entityID` rather than manually typing `keycloak`.

### Expected SSO Flow

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant SP as Spring SP :8080
    participant I as Keycloak IdP :8081
    B->>SP: GET /me (anonymous)
    SP-->>B: 302 /saml2/authenticate/keycloak
    B->>SP: GET /saml2/authenticate/keycloak
    SP-->>B: SAML AuthnRequest HTTP-Redirect
    B->>I: GET SAML SSO endpoint with SAMLRequest
    I->>I: Identify SAML Client + authenticate alice
    I-->>B: HTML form with signed SAMLResponse
    B->>SP: POST /login/saml2/sso/keycloak
    SP->>SP: Resolve registration + verify SAML signature/conditions
    SP->>SP: Establish authenticated SecurityContext/session
    SP-->>B: Redirect to saved /me
    B->>SP: GET /me using SP session cookie
    SP-->>B: JSON authenticated = true
~~~

**No step requires Spring to receive a Keycloak username/password through a custom API.** Spring trusts the result from the IdP **after** verifying the signature and SAML conditions, not merely because an HTTP POST contains a `SAMLResponse` parameter.

## 3. Environment Preparation

Install JDK 17, Maven 3.9+, Docker, and a browser with DevTools. Verify:

~~~bash
java -version
mvn -version
docker version
~~~

Keep host ports **8080** (Spring) and **8081** (Keycloak) free. On Windows PowerShell, `curl` may be an alias for `Invoke-WebRequest`; when standard curl flags are needed, invoke `curl.exe` or download the XML via browser.

Directory tree to build:

~~~text
saml-sp-lab/
  pom.xml
  src/main/java/com/example/samllab/
    SamlSpLabApplication.java
    SecurityConfig.java
    LabController.java
  src/main/resources/
    application.yml
~~~

Do not put keystores/passwords/real tokens into source code or spreadsheets. The initial version does not need SP signing/decryption private keys because the lab IdP is configured **not to require signed AuthnRequests and not to encrypt Assertions**. **The IdP must still sign the SAMLResponse or Assertion** for Spring to verify.

## 4. Step 1 — Run the Keycloak IdP on Localhost

Following Keycloak's official Docker guide, the image can run in development mode:

~~~bash
docker run --rm --name saml-idp-lab -p 127.0.0.1:8081:8080 -e KC_BOOTSTRAP_ADMIN_USERNAME=admin -e KC_BOOTSTRAP_ADMIN_PASSWORD=admin quay.io/keycloak/keycloak:26.8.2 start-dev
~~~

Explanation: container port 8080 is published as **localhost:8081** on the host, avoiding conflict with Spring port 8080; `127.0.0.1` prevents exposing the admin console to other networks. `start-dev`, easy-to-remember passwords, and `--rm` are **suitable for labs only**; the container loses data when removed without a volume. Do not use this configuration for the Internet or enterprise environments.

Open: `http://localhost:8081/admin`. Sign in with `admin`/`admin`. Once Keycloak is ready:
1. **Manage realms → Create realm**.
2. Name it `saml-lab`, create the realm, and select it as the current realm.
3. Do not use the `master` realm for demo users/apps; `master` is for Keycloak administration.

### Create User Alice

In the `saml-lab` realm:
- **Users → Create new user**; username `alice`, Enabled ON.
- Save, go to the **Credentials → Set password** tab.
- Set a lab-only password; set **Temporary OFF** so password change is not forced on first login.
- If the admin UI differs across 26.x versions, locate the equivalent field; do not relax security requirements.

### View IdP Metadata

Open directly:

~~~text
http://localhost:8081/realms/saml-lab/protocol/saml/descriptor
~~~

Or:

~~~bash
curl -fsS "http://localhost:8081/realms/saml-lab/protocol/saml/descriptor"
~~~

Expected XML metadata contains `EntityDescriptor`, `IDPSSODescriptor`, `SingleSignOnService`, and typically `KeyDescriptor` holding the public signing certificate. **Do not enter this exact URI into the Keycloak Client ID field**: this is the **input for Spring**, whereas the Keycloak Client ID must equal the SP EntityID exported by Spring. On 404, check the realm name, port, and Docker logs; if XML metadata is not yet returned, **do not start Spring with metadata-uri yet**.

## 5. Step 2 — Create the Spring Boot Maven Project

### Complete `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
          https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.0</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>saml-sp-lab</artifactId>
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
      <groupId>org.springframework.security</groupId>
      <artifactId>spring-security-saml2-service-provider</artifactId>
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

  <repositories>
    <repository>
      <id>shibboleth-releases</id>
      <name>Shibboleth Maven Releases</name>
      <url>https://build.shibboleth.net/maven/releases</url>
      <snapshots>
        <enabled>false</enabled>
      </snapshots>
    </repository>
  </repositories>

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

**Why each dependency is needed:**
- `spring-boot-starter-web`: Servlet web server and REST controller.
- `spring-boot-starter-security`: SecurityFilterChain, Authentication/Authorization.
- `spring-security-saml2-service-provider`: SAML RP/SP integration with OpenSAML.
- Test dependencies: for unit/MockMvc regression tests later.
- Shibboleth HTTPS Maven Releases repository: Spring Security docs specify this repository because some OpenSAML artifacts have their own release source. **Do not enable insecure repositories or trust-all TLS**.
- Spring Boot parent manages compatible versions. Avoid pinning incompatible transitive OpenSAML/Spring Security versions.

If the build fails due to the repository, check HTTPS, Maven proxy/corporate certificate trust, network, and the dependency tree; do **not** manually install the legacy `spring-security-saml2-core` extension to "rescue" a modern dependency.

### `SamlSpLabApplication.java`

~~~java
package com.example.samllab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SamlSpLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(SamlSpLabApplication.class, args);
    }
}
~~~

Java `@SpringBootApplication` creates the context and auto-configuration; `application.yml` in the proper resources path sets the HTTP port.

## 6. Step 3 — Use IdP Metadata to Create RelyingPartyRegistration

### `src/main/resources/application.yml`

~~~yaml
server:
  port: 8080

spring:
  security:
    saml2:
      relyingparty:
        registration:
          keycloak:
            assertingparty:
              metadata-uri: "http://localhost:8081/realms/saml-lab/protocol/saml/descriptor"
~~~

**Reading the configuration:**
- `registration.keycloak` is the internal **registrationId**, appearing in `/saml2/authenticate/keycloak` and `/login/saml2/sso/keycloak`.
- `assertingparty.metadata-uri` points to the **IdP metadata XML**. It is **not** OIDC `.well-known/openid-configuration`, not the `/admin` URL, and not SP metadata.
- Spring Boot can auto-create `RelyingPartyRegistrationRepository` from properties. Metadata supplies the IdP EntityID, SSO location, supported bindings, and public verification certs.
- If Keycloak is not running or the realm does not exist yet, the Java build may succeed, but **application startup will fail to load metadata**.
- Do not treat an HTTP source outside localhost as trustworthy. Production uses HTTPS/PKIX and metadata issuer/certificate review.
- This configuration is the **minimal lab** for unsigned AuthnRequest and signed SAML Response/Assertion. Without an SP private signing/decryption key, IdP policies requiring them are not yet supported.

Renaming registration `keycloak` changes the default login/ACS/metadata URLs. Update **the Keycloak SAML client, the IdP registered ACS, and all test links** if you rename it.

## 7. Step 4 — Enable the SAML2 Filter Chain and Export SP Metadata

### `SecurityConfig.java`

~~~java
package com.example.samllab;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/",
                    "/error",
                    "/saml2/metadata",
                    "/saml2/metadata/**",
                    "/saml2/service-provider-metadata/**")
                .permitAll()
                .requestMatchers("/me").authenticated()
                .anyRequest().denyAll())
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults())
            .logout(logout -> logout.logoutSuccessUrl("/"))
            .build();
    }
}
~~~

**Every line has a purpose:**
- `/` is public to verify the web server is running.
- `/saml2/metadata` and its variants are `permitAll` so partners can fetch **SP metadata** without a session; never place private information in metadata.
- `/me` requires an authenticated `SecurityContext`, triggering Web Browser SSO if the browser is not logged in.
- `saml2Login(...)` wires the filters and OpenSAML authentication provider; **never write custom controller code to parse Base64 XML**.
- `saml2Metadata(...)` enables the metadata endpoint based on registrations.
- `logout(...)` is **local logout**, not global SAML SLO.
- `anyRequest().denyAll()` locks down unknown endpoints; real projects need fine-grained rules per business authorization.

**Do not disable CSRF across the entire application.** The SAML POST ACS belongs to the framework authentication flow; state-changing business actions must still have CSRF protection or equivalent safeguards. If you customize the ACS/filter matcher, verify CSRF and state correlation separately instead of applying a broad exemption to all URLs.

### `LabController.java`

~~~java
package com.example.samllab;

import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class LabController {

    @GetMapping("/")
    public String home() {
        return "SAML2 SP lab running. Open /me to start login.";
    }

    @GetMapping("/me")
    public Map<String, Object> currentUser(
            Authentication authentication) {

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("authenticated", authentication.isAuthenticated());
        result.put("authenticationType",
                authentication.getClass().getSimpleName());
        result.put("principalAvailable",
                authentication.getName() != null
                        && !authentication.getName().isBlank());
        return result;
    }
}
~~~

In the lab, `/me` returns status without **exposing SAMLResponse, tokens, NameID, or email**. The `authenticationType` field may change across Spring Security versions; do not build tests depending on an exact type name. In production, remove/restrict this debug endpoint or replace it with an approved data API.

## 8. Step 5 — Start Spring and Check Metadata

From the root of `saml-sp-lab`:

~~~bash
mvn clean verify
mvn spring-boot:run
~~~

**Keycloak must already be running** for Spring to fetch IdP metadata. If you need to check connectivity via terminal:

~~~bash
curl -fsS "http://localhost:8081/realms/saml-lab/protocol/saml/descriptor"
~~~

Open the URL:

~~~text
http://localhost:8080/
~~~

Expected HTTP response body:

~~~text
SAML2 SP lab running. Open /me to start login.
~~~

This only proves the web server/controller is running; `/` is public and **does not prove SAML2 login**.

### Retrieve SP Metadata

~~~bash
curl -fsS "http://localhost:8080/saml2/metadata/keycloak"
~~~

Or open in a browser. The actual XML typically contains `EntityDescriptor`, `SPSSODescriptor`, and `AssertionConsumerService`. With the lab registration defaults, the two values to inspect are:

~~~text
SP EntityID:
  http://localhost:8080/saml2/service-provider-metadata/keycloak

SP ACS HTTP-POST:
  http://localhost:8080/login/saml2/sso/keycloak
~~~

**Do not hardcode conclusions if runtime metadata differs**: read `EntityDescriptor/@entityID` and `AssertionConsumerService/@Location` directly from the XML. With a custom entityId, reverse proxy, context path, or different Spring version, values may change.

The SP metadata endpoint also has variants in Spring Security:
- `/saml2/metadata`;
- `/saml2/metadata/{registrationId}`;
- `/saml2/service-provider-metadata/{registrationId}`.

**`/saml2/authenticate/keycloak` is NOT a metadata endpoint.** It is the endpoint that constructs an AuthnRequest and typically returns a redirect to the IdP.

### Comparing the Two Metadata Documents

| Field | Source | Where Is It Used for Configuration? |
| --- | --- | --- |
| IdP `EntityDescriptor.entityID` | Keycloak IdP metadata | Spring trusting/asserting-party issuer |
| IdP `SingleSignOnService.Location` | Keycloak IdP metadata | Spring AuthnRequest destination |
| IdP `KeyDescriptor use=signing` | Keycloak IdP metadata | Spring verifies IdP signature |
| SP `EntityDescriptor.entityID` | Spring SP metadata | Keycloak SAML Client ID |
| SP `AssertionConsumerService.Location` | Spring SP metadata | Keycloak Master SAML Processing URL |
| SP `AssertionConsumerService.Binding` | Spring SP metadata | Keycloak response binding |
| SP `KeyDescriptor use=signing/encryption` | SP metadata if keys are configured | Keycloak verifies request / encrypts Assertion |

**Never send the SP decryption private key to the IdP.** The IdP only needs the SP's public encryption certificate when encryption is required.

## 9. Step 6 — Register the SAML Client on Keycloak

After checking SP metadata:

1. In Keycloak select the `saml-lab` realm, go to **Clients → Create client**.
2. Choose **Client type = SAML**, **not** OpenID Connect.
3. **Client ID:** copy the **SP EntityID** from Spring metadata. The expected lab value is:

   `http://localhost:8080/saml2/service-provider-metadata/keycloak`

4. **Master SAML Processing URL:** enter the exact **ACS**:

   `http://localhost:8080/login/saml2/sso/keycloak`

5. **Valid Redirect URIs:** add the exact approved ACS URI. Do not use wildcard `*` or unintended domains.
6. **Name ID Format:** choose a format supported by the IdP for the demo user; if choosing persistent, determine Keycloak's identity stability mechanism. Do not infer from the field name that NameID cannot change.
7. Under **SAML capabilities**, require the IdP to **sign the SAML Response or Assertion** with the appropriate key; Keycloak typically offers **Sign Documents** and **Sign Assertions**. Do not disable both.
8. Because the lab SP does not yet have a signing credential, set **Client Signature Required = Off** so Keycloak permits unsigned AuthnRequests. This choice is **for the lab only**. When real policy requires signed AuthnRequests, add an SP signing private key/cert.
9. **Do not enable Encryption** for the Assertion initially if there is no SP decryption key/certificate yet.
10. Save and reopen the client to verify that the URIs/capabilities were saved properly.

Keycloak versions may place fields in different tabs; match by function (**Client ID/ACS/redirect/signature requirements**) instead of looking for an identical UI from an older screenshot.

### Why Is Client ID Not the String `keycloak`?

`registrationId=keycloak` only distinguishes internal configurations **inside Spring**. In `samlp:AuthnRequest`, `saml:Issuer` is usually the **SP EntityID**; Keycloak relies on issuer/client ID to determine which client is requesting SSO. If Client ID is entered as `keycloak` while the SP sends the metadata URL as issuer, Keycloak may report **client not found/invalid client**.

### If Keycloak Supports Importing SP Metadata

You can pass the `/saml2/metadata/keycloak` URL or downloaded XML directly. **You must still verify** SP EntityID, ACS, bindings, signing requirements, and the redirect allowlist after import. Do not assume import automatically finalizes trust policy or signing rules.

## 10. Step 7 — Log In via Web Browser SSO

Open a private window or a browser profile with no existing Spring session:

~~~text
http://localhost:8080/me
~~~

Success journey:
1. Spring sees the resource requires authentication → starts SAML2 login.
2. Spring issues `AuthnRequest` and the browser navigates to Keycloak.
3. Keycloak identifies the SAML client by Issuer and prompts user `alice` for a password if no IdP session exists.
4. After user authentication, Keycloak generates a **signed SAMLResponse/Assertion**.
5. The browser performs an **HTTP POST** containing `SAMLResponse` to `/login/saml2/sso/keycloak`.
6. Spring `Saml2WebSsoAuthenticationFilter` and the OpenSAML provider verify signature, issuer, audience, Destination/Recipient, Conditions, SubjectConfirmationData, request correlation, and applicable constraints.
7. Spring creates an authenticated `Authentication` and stores it in `SecurityContext`/session.
8. The browser is redirected back to `/me` and receives JSON with `authenticated: true`.

**Illustrative** JSON example; class/type names may vary:

~~~json
{
  "authenticated": true,
  "authenticationType": "Saml2Authentication",
  "principalAvailable": true
}
~~~

Do not assume step 3 means completion: Keycloak showing the login page only proves the SP can initiate AuthnRequest; **it does not prove the SAMLResponse was verified by Spring**.

### Independent Verification Points

| Observation | Conclusion That Can Be Drawn |
| --- | --- |
| Root `/` returns 200 | Spring Boot is running |
| Browser is redirected to IdP | Basic AuthnRequest initiation works |
| User logs in successfully on Keycloak | IdP authenticates the user |
| Network shows POST `/login/saml2/sso/keycloak` | Response reached the ACS |
| Spring creates a session and `/me` returns `authenticated=true` | SP processed valid SAML under the deployed config |
| Resource requiring a business role denies a user lacking entitlement | Application authorization works |
| Invalid signature/issuer/audience is rejected | Negative security checks are active |

**Do not attach raw SAMLResponse payloads to public bug trackers.** In test environments, use test identities only, and protect HAR/logs because they may contain session cookies/AttributeValues.

## 11. Metadata XML: Reading Correctly Across Multiple Namespaces

IdP metadata skeleton:

~~~xml
<!-- Simplified illustration, NOT real importable metadata. -->
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="http://localhost:8081/realms/saml-lab">
  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:KeyDescriptor use="signing">
      <!-- public certificate of Keycloak -->
    </md:KeyDescriptor>
    <md:SingleSignOnService
      Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
      Location="http://localhost:8081/realms/saml-lab/protocol/saml"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
~~~

SP metadata skeleton:

~~~xml
<!-- Simplified illustration; get real values from the SP metadata endpoint. -->
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="http://localhost:8080/saml2/service-provider-metadata/keycloak">
  <md:SPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:AssertionConsumerService
      Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
      Location="http://localhost:8080/login/saml2/sso/keycloak"
      index="0"/>
  </md:SPSSODescriptor>
</md:EntityDescriptor>
~~~

**The two XML snippets above are skeletal diagrams with required elements omitted from full metadata**—never use them in place of actual IdP/SP XML during import. In practice, XML namespace prefixes, element ordering, certificate descriptors, ACS index, and signing flags may differ.

Extract fields using a namespace-aware XML parser or inspect real metadata. Specifically:
- `EntityDescriptor.entityID` is not automatically a login URL.
- `SPSSODescriptor` defines the SP; `IDPSSODescriptor` defines the IdP.
- `KeyDescriptor use=signing` normally holds the public key used by the partner to verify SAML messages.
- `KeyDescriptor use=encryption` normally holds the public key used to encrypt for the recipient.
- `AssertionConsumerService.Binding` must match the binding the IdP uses to send the response.
- `SingleLogoutService` is only relevant when configuring SLO.

## 12. How Does Spring Security Process SAMLResponse?

At runtime, the two endpoints serve distinct roles:

~~~text
/saml2/authenticate/{registrationId}
  -> Saml2WebSsoAuthenticationRequestFilter
  -> construct AuthnRequest and redirect to IdP

/login/saml2/sso/{registrationId}
  -> Saml2WebSsoAuthenticationFilter
  -> Saml2AuthenticationToken (untrusted before verification)
  -> AuthenticationManager / OpenSAML provider
  -> verify signature, issuer, audience, time, recipient, correlation
  -> Saml2Authentication and SecurityContext
~~~

The provider can also decrypt `EncryptedAssertion`/`EncryptedAttribute`/`EncryptedID` when SP decryption credentials are configured. **Do not and must not write a custom servlet controller `POST /login/saml2/sso/keycloak` to decode XML and grant `ROLE_USER` from the raw request**.

### Spring Security Versions

This Boot 3.5/Security 6.x article has different APIs/Authentication types from the current Spring Security 7 line. Spring 7 docs use `OpenSaml5AuthenticationProvider` and `Saml2ResponseAssertionAccessor`; much Spring 6 code uses `Saml2AuthenticatedPrincipal`. When upgrading versions, verify actual dependencies, public APIs, and integration tests; the `SecurityConfig` above does not depend on principal implementations.

### Issuer and Trust

The IdP signs the SAMLResponse with the **IdP's private signing key**; the SP verifies it using the approved **IdP public certificate**. If the IdP rotates its cert, the application needs a metadata/trust refresh policy rather than blindly accepting any certificate. Even a signed SAML Assertion with the right issuer must pass **AudienceRestriction, Recipient, NotBefore/NotOnOrAfter, InResponseTo, and replay safeguards**.

## 13. Distinguishing Login from Business Authorization

`/me` uses `authenticated()` to test SAML login, **requiring no business role**. In real systems:
- Link users by trusted IdP issuer + stable subject identifier (and tenant namespace if required), not by email alone.
- IdP attributes are structured data; one `Attribute` may carry **0..N `AttributeValue` elements**.
- Multi-valued `groups` must be iterated completely; do not just call `getFirstAttribute("groups")`.
- Map only approved groups such as `APP_REPORT_VIEWERS` → `ROLE_REPORT_VIEWER`.
- An AD `Domain Admins` group does not automatically grant application `ROLE_ADMIN`.
- Missing required `tenant` should deny access; missing optional email does not necessarily fail authentication.
- A disabled local user must be denied even if the Assertion signature is valid.
- An authenticated SAML session does not mean the user is allowed to view every resource in the API.

### Role Exercise After Smoke Testing

1. Create Keycloak group `APP_REPORT_VIEWERS` and assign it to `alice`.
2. Configure a SAML client group mapper emitting an Attribute Name agreed upon by both sides, e.g., `urn:example:claims:groups`.
3. Verify the XML assertion **in a safe lab environment** or inspect the verified attribute accessor after the Spring provider.
4. Map values in the list to app authorities via an exact allowlist.
5. Create endpoint `/reports` guarded by `hasAuthority("ROLE_REPORT_VIEWER")`.
6. Use a user without the group to test 403; use a user with the group to test 200.
7. Try adding `Domain Admins` and confirm **no ROLE_ADMIN is granted**.
8. Do not send raw group lists/NameID/PII into logs or external analytics.

## 14. Standalone Java 17: Checking the EntityID, ACS, and Role-Mapping Contract

A pure Java 17 program can catch confusion between `registrationId`, `SP EntityID`, and `ACS` before sending metadata to Keycloak. **The program below does not parse SAML XML, verify signatures, or act as an IdP or SP**. It only illustrates federation contract strings and safe group mapping. Spring/OpenSAML must still handle all cryptographic/protocol verification in a real system.

Create **`SamlSpMetadataContractDemo.java`**:

~~~java
import java.net.URI;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

public class SamlSpMetadataContractDemo {

    record SpContract(
            String registrationId,
            URI entityId,
            URI acs,
            URI idpMetadata) {}

    static boolean sameContract(
            SpContract expected, SpContract actual) {
        return expected.equals(actual);
    }

    static boolean validAcs(URI registered, URI candidate) {
        return registered.getScheme().equals(candidate.getScheme())
                && registered.getHost().equalsIgnoreCase(
                        candidate.getHost())
                && registered.getPort() == candidate.getPort()
                && registered.getRawPath().equals(
                        candidate.getRawPath())
                && candidate.getRawQuery() == null
                && candidate.getRawFragment() == null;
    }

    static Set<String> appRoles(List<String> groups) {
        Set<String> result = new TreeSet<>();
        for (String group : groups) {
            if ("APP_REPORT_VIEWERS".equals(group)) {
                result.add("ROLE_REPORT_VIEWER");
            }
            if ("APP_REPORT_EDITORS".equals(group)) {
                result.add("ROLE_REPORT_EDITOR");
            }
        }
        return result;
    }

    public static void main(String[] args) {
        SpContract expected = new SpContract(
                "keycloak",
                URI.create("http://localhost:8080"
                        + "/saml2/service-provider-metadata/keycloak"),
                URI.create("http://localhost:8080"
                        + "/login/saml2/sso/keycloak"),
                URI.create("http://localhost:8081"
                        + "/realms/saml-lab/protocol/saml/descriptor"));

        SpContract actual = new SpContract(
                expected.registrationId(),
                expected.entityId(),
                expected.acs(),
                expected.idpMetadata());

        SpContract wrongAcs = new SpContract(
                "keycloak", expected.entityId(),
                URI.create("http://localhost:8080"
                        + "/login/saml2/sso/other"),
                expected.idpMetadata());

        System.out.println("SP contract matches: "
                + sameContract(expected, actual));

        System.out.println("Wrong ACS detected: "
                + !sameContract(expected, wrongAcs));

        System.out.println("Registered ACS allowed: "
                + validAcs(expected.acs(), actual.acs()));

        System.out.println("Unregistered redirect rejected: "
                + !validAcs(expected.acs(),
                  URI.create("http://evil.example/login/saml2/sso/keycloak")));

        System.out.println("ACS with query rejected: "
                + !validAcs(expected.acs(),
                  URI.create(expected.acs() + "?ticket=FAKE")));

        System.out.println("Registration ID: "
                + expected.registrationId());

        System.out.println("Approved roles: "
                + appRoles(List.of(
                  "Domain Admins", "APP_REPORT_VIEWERS")));

        System.out.println("External admin becomes app admin: "
                + appRoles(List.of("Domain Admins"))
                  .contains("ROLE_ADMIN"));

        System.out.println("No app groups grants no role: "
                + appRoles(List.of("OTHER_TEAM")).isEmpty());
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac SamlSpMetadataContractDemo.java
java SamlSpMetadataContractDemo
~~~

**Exact stdout:**

~~~text
SP contract matches: true
Wrong ACS detected: true
Registered ACS allowed: true
Unregistered redirect rejected: true
ACS with query rejected: true
Registration ID: keycloak
Approved roles: [ROLE_REPORT_VIEWER]
External admin becomes app admin: false
No app groups grants no role: true
~~~

**Explanation:**
- `sameContract` uses record equality to compare the four fields; a different ACS is a contract change and must not be applied before the IdP updates its registered URI.
- `validAcs` illustrates exact scheme/host/port/path matching with no query/fragment; **it does not replace the Spring/OpenSAML Destination/Recipient validator**.
- `appRoles` uses an allowlist so an infrastructure group never becomes an application admin.
- The output does not prove certificates, XML Signature, SAML Conditions, replay, InResponseTo, or request correlation actually PASS.
- In production, consume trusted metadata/certificates and never allow users to supply arbitrary URIs as a trust authority.

## 15. Extension 1 — Enabling Signed AuthnRequests

The initial sample sets **Keycloak Client Signature Required = Off** because the Spring SP has no private signing key yet. A real application needs a unified policy:

1. Generate an **SP** private key + X.509 certificate pair for the lab using algorithms meeting the crypto baseline.
2. Store the private signing key in a secret store/file with minimal ACLs; never commit it to Git.
3. Add the SP **public signing certificate** to metadata/Keycloak SAML client.
4. Configure Spring `Saml2X509Credential.signing(...)` or Boot signing credentials.
5. Enable Keycloak **Client Signature Required**.
6. Verify Spring actually signs AuthnRequest for the proper binding and Keycloak accepts it.
7. Verify altered requests/unknown certificates are rejected by the IdP.

YAML fragment (placed **under `registration.keycloak`**, not a standalone YAML file):

~~~yaml
signing:
  credentials:
    - private-key-location: "file:/run/secrets/saml/sp-signing.key"
      certificate-location: "file:/etc/saml/sp-signing.crt"
~~~

File paths are illustrative only; provide a real keypair **in an appropriately protected lab environment**. If the IdP requires signing and the SP does not support it yet, **do not work around it by disabling SAMLResponse signature verification on the SP**. The two signature directions are distinct: the SP signs requests for the IdP, and the IdP signs responses/assertions for the SP.

## 16. Extension 2 — EncryptedAssertion and SP Decryption Key

To try encryption:
1. The SP generates or receives a valid **private decryption key + certificate**.
2. The SP publishes its **public encryption certificate** in metadata for Keycloak.
3. Keycloak encrypts the Assertion using the SP public certificate; the browser delivers the **EncryptedAssertion** to the SP.
4. Spring decrypts using the **SP private key** before/after signature checks per the Spring/OpenSAML provider workflow.
5. The SP continues verifying issuer, audience, recipient, signature, Conditions, subject confirmation, and replay.
6. Wrong-key/decryption-failure tests must **FAIL CLOSED**; never fall back to reading unverified plaintext.

Boot YAML fragment placed under `registration.keycloak`:

~~~yaml
decryption:
  credentials:
    - private-key-location: "file:/run/secrets/saml/sp-decrypt.key"
      certificate-location: "file:/etc/saml/sp-decrypt.crt"
~~~

**Distinction:** `EncryptedAssertion` encrypts the entire Assertion, `EncryptedAttribute` encrypts a single Attribute, and `EncryptedID` encrypts the identifier. XML Signature protects integrity/authenticity whereas XML Encryption protects confidentiality; **encryption does not replace signatures**. Use lab keys and regenerate signed/encrypted fixtures rather than mutating raw signed XML to build other tests.

## 17. Extension 3 — Local Logout and SAML Single Logout

In the initial lab, `POST /logout` performs **local session logout** via Spring Security. The browser may be redirected to `/`; **the Keycloak IdP SSO session may still be alive**, so the next visit to `/me` may log back in without prompting for a password. This is not evidence that local logout failed.

Separate **SAML Single Logout (SLO)** requires:
- IdP metadata containing `SingleLogoutService` and a supported binding.
- An SP signing credential when the IdP/protocol requires signed LogoutRequest/LogoutResponse messages.
- Agreed RP-initiated and IdP-initiated logout endpoints, such as `/logout/saml2/slo` in Spring.
- Enabling `saml2Logout(Customizer.withDefaults())` **after** prerequisites are complete.
- Testing LogoutRequest/LogoutResponse signature/issuer/destination/correlation and session index/nameID matching.
- Auditing `LOGOUT_REQUESTED`, `LOGOUT_LOCAL_COMPLETED`, `LOGOUT_SLO_DISPATCHED`, and `LOGOUT_SLO_CONFIRMED` separately according to evidenced scope.

**Do not label global logout as successful solely from seeing HTTP 302 or one invalidated Spring session.** If the IdP SSO session remains alive, a fresh visit may trigger SSO as usual.

## 18. Extension 4 — HTTPS Reverse Proxy and Session Cookies

In production, the public URL may be `https://portal.example.com` while the internal app runs at `http://spring:8080`. If SP metadata derives its URLs from the internal host, the IdP sends `Destination`/`Recipient` different from the expected ACS, causing login to fail.

Requirements:
- Choose canonical public SP EntityID and ACS; apply them to `RelyingPartyRegistration`/metadata and the IdP registration simultaneously.
- Use trusted `Forwarded`/`X-Forwarded-Proto`/`X-Forwarded-Host`/`X-Forwarded-Port` or the appropriate Boot `server.forward-headers-strategy`.
- **Never trust forwarded headers supplied directly by Internet clients**; ingress must sanitize them.
- Enforce HTTPS + PKIX/hostname verification, policy-compliant HSTS, and appropriate `Secure`/`HttpOnly`/`SameSite` cookie attributes.
- For cross-site SAML HTTP-POST ACS, `SameSite=Lax` can prevent session cookies from being sent; some architectures require `SameSite=None; Secure` alongside CSRF/correlation controls.
- Multi-pod setups require a shared session/request repository across nodes or consistent routing; verify `InResponseTo`/`RelayState`.
- Never put session IDs or raw SAMLResponse payloads into URLs, logs, or client storage.

**Interesting detail:** `localhost:8080` and `localhost:8081` are **different origins yet potentially same-site** because ports do not create a site boundary under browser site semantics. Therefore, success on localhost **does not prove** cookie behavior will hold across two cross-site production domains. End-to-end testing on representative HTTPS domains is mandatory.

## 19. Common Errors and Quick Diagnosis

| Symptom | Possible Cause | Check / Fix |
| --- | --- | --- |
| App fails to start | IdP metadata URI 404/connection refused | Start realm/Keycloak before Spring |
| Maven cannot find OpenSAML | Missing Shibboleth Releases/HTTPS proxy | Fix build repository, do not use trust-all |
| SP metadata returns 404 | `saml2Metadata` not enabled or wrong registrationId | Check SecurityFilterChain/repository |
| Keycloak "client not found" | Client ID does not match SP AuthnRequest Issuer/EntityID | Copy exact SP metadata entityID |
| Invalid redirect URI | ACS not registered | Register exact ACS |
| Keycloak demands signed request | Client Signature Required ON while SP has no signing key | Add SP key/cert or change lab-only policy |
| IdP login succeeds but browser gets 404 at SP | Wrong Master SAML Processing URL | Compare ACS against SP metadata |
| Signature validation failed | IdP signing disabled / wrong public cert / trust mismatch | Sign IdP response/assertion and verify metadata |
| SAML issuer mismatch | IdP metadata/Issuer differs from registration | Use the right realm EntityID and signing keys |
| Audience mismatch | SP EntityID does not match IdP Client ID/Audience | Fix approved partner contract |
| Destination/Recipient mismatch | Wrong ACS, reverse proxy scheme/host | Fix public ACS and proxy headers |
| InResponseTo mismatch | Lost AuthnRequest state/cookie/cluster mismatch | Check session repository, RelayState |
| Assertion expired/not yet valid | IdP/SP clock skew, login took too long | Sync NTP, keep justified small tolerance |
| Cannot decrypt | IdP encrypts but SP lacks/has wrong private key | Configure decryption credential |
| Login loop | Cookie SameSite/missing session/IdP config | Inspect DevTools Network and cookies |
| Authenticated but API returns 403 | Missing local group/tenant authorization | Add proper mapping and test deny |
| Login passes on only one pod | Metadata/keyset/session store drift | Check configs, replication, and sticky routing |
| New metadata cert unused by Spring | Stale registration snapshot/cache | Refresh/rollback per trust change policy |
| SP logs full of SAML XML | Debug body capture enabled | Disable raw SAMLResponse capture, handle exposed data |

**Runbook order:** network/metadata → SP EntityID/client → ACS/redirect → IdP signing cert → SAML provider validation → Spring session/cookie → local business authorization. Never relax signature/audience/replay checks to bypass a configuration error.

### Safe DevTools Inspection

Use a test user in the lab:
1. Observe `GET /me` redirecting to login start.
2. Observe `SAMLRequest` redirecting to the right realm on port 8081.
3. Observe Keycloak authenticating `alice`.
4. Observe the browser POSTing to `/login/saml2/sso/keycloak`.
5. Observe the ACS response redirecting back to `/me`.
6. Observe the session cookie and `authenticated=true`.

Never copy raw `SAMLResponse`, session cookies, or full HAR files into public documentation. SAMLResponse payloads may carry PII/AttributeValues; `no-store` and redacted logs matter even in test environments.

## 20. Integration and Security Test Matrix

| ID | Test Case | Expected Result |
| --- | --- | --- |
| L01 | Realm/user/keycloak SAML client exist | IdP metadata is readable |
| L02 | Spring reads IdP metadata | Boot starts, repository creates registration |
| L03 | Anonymous `GET /` | HTTP 200 lab body |
| L04 | `GET /saml2/metadata/keycloak` | SP metadata XML with EntityID/ACS |
| L05 | Client ID equals SP EntityID | AuthnRequest reaches the right client |
| L06 | Registered ACS matches | SAMLResponse POSTs to Spring |
| L07 | SAMLResponse/Assertion signed with valid key | Provider authenticates |
| L08 | User `alice` valid password | `/me` returns `authenticated=true` |
| L09 | Wrong password | No authenticated session created |
| L10 | User with no Spring session | Starts SP-initiated SSO |
| L11 | Wrong Client ID | IdP rejects / client not found |
| L12 | ACS not in redirect allowlist | IdP rejects per policy |
| L13 | Unsigned SAML Assertion and Response | Spring rejects |
| L14 | Signature from unknown cert | Spring rejects |
| L15 | Audience is another SP | Spring rejects |
| L16 | Recipient or Destination differs from ACS | Spring rejects |
| L17 | InResponseTo mismatches request | Rejected in SP-initiated flow |
| L18 | NotBefore in the future | Rejected outside approved skew |
| L19 | NotOnOrAfter expired | Rejected outside approved skew |
| L20 | Replay of same Response/Assertion ID | Rejected per replay/correlation controls |
| L21 | XML Signature Wrapping/XXE | Parser/provider rejects |
| L22 | EncryptedAssertion with valid SP key | Decrypted and fully verified |
| L23 | EncryptedAssertion with wrong SP key | Rejected, no fallback |
| L24 | Optional email missing | Identity/authorization policy handles properly |
| L25 | Required tenant missing | Business access denied |
| L26 | Multi-valued group AttributeValue | Exact allowlist mapping, not first value only |
| L27 | User belongs to Domain Admins | Does not auto-grant app ROLE_ADMIN |
| L28 | Disabled local user | Denied per local account policy |
| L29 | Local POST logout | Local session invalidated |
| L30 | IdP session alive after local logout | Silent re-login may occur, properly explained |
| L31 | SLO when enabled, RP-initiated | Signed request/response and correlation |
| L32 | Invalid IdP-initiated SLO | Does not arbitrarily terminate sessions |
| L33 | Third-party cookie/cross-site POST | Request correlation and CSRF remain valid |
| L34 | Callback hits another pod | Session/repository state remains consistent |
| L35 | IdP signing key rollover | Approved certificate rotation |
| L36 | SP decryption key rollover | Old/new key overlap per policy |
| L37 | Metadata refresh while IdP offline | Clear fail/retry/cache policy |
| L38 | HTTPS reverse proxy | Public EntityID/ACS match metadata |
| L39 | Spoofed Forwarded headers | Does not produce malicious external ACS |
| L40 | Logs/APM/HAR | Contain no raw SAMLResponse/keys/PII |
| L41 | SAML login present but missing app group | Business endpoint denied |
| L42 | Two IdPs share same email | No accidental account linking |
| L43 | Spring Security upgrade | API/build/protocol regressions tested |
| L44 | Unsupported binding/profile | Detected, never silently downgraded |
| L45 | Backup/restore of IdP+SP config | EntityID/ACS/cert revisions restored |

**Do not mark all tests PASS merely because the article includes a matrix.** Smoke tests L01–L10 can be run manually in the lab; many negative tests require **signed fixtures generated by a test IdP**. Mutating XML bytes after signing usually just causes signature failure and **does not** prove dedicated audience/expiration validators work.

## 21. Choosing the Right Test Tools and Avoiding Misconceptions

**Browser E2E + Keycloak:** verifies full redirects/POSTs, login/session/cookies. Essential to validate a real IdP and ACS.

**Spring MockMvc/unit tests:** verify `/me` requires authentication, `denyAll` rules, and local role mapping. Mocking `Authentication` alone does not prove IdP signature trust or metadata exchange.

**OpenSAML signed fixtures:** use a test IdP or OpenSAML test signer to build validly signed Assertions/Responses with **lab keys**; vary issuer/audience/time **before signing** and run through the real Spring provider. Never use production private keys.

**Metadata comparisons:** parse XML namespace-aware and compare EntityID/ACS, signing keys, bindings, and SLO. Do not compare XML byte-for-byte when ordering/namespaces do not affect semantics; **compare exact URI identifiers**.

**Security scanning:** check dependency vulnerabilities and Keycloak/Spring patch versions, ensure no secrets in Git/CI, and disable HTTP request-body logging.

## 22. Acceptance and Handover Checklist

- [ ] Docker Keycloak bound to localhost only; `saml-lab` realm has user `alice`.
- [ ] IdP metadata descriptor returns XML; Spring reads it via `metadata-uri`.
- [ ] Java 17 Maven project includes `spring-security-saml2-service-provider` with compatible Spring Security/Boot BOM.
- [ ] `SecurityFilterChain` enables `saml2Login` and `saml2Metadata`.
- [ ] Public root/metadata accessible; protected `/me` requires SAML login.
- [ ] SP metadata returns `EntityDescriptor`, ACS, and the right SP EntityID.
- [ ] Keycloak SAML Client ID **exactly equals SP EntityID**, not registrationId.
- [ ] Master SAML Processing URL/Valid Redirect URIs **match exact ACS**.
- [ ] Keycloak signs SAMLResponse or Assertion; Spring verifies with IdP trust cert.
- [ ] Unsigned SP AuthnRequest is accepted only when permitted by lab policy.
- [ ] End-to-end browser AuthnRequest redirect / SAMLResponse POST succeeds.
- [ ] Spring `/me` returns `authenticated=true` after login.
- [ ] App rejects unsigned/bad issuer/bad audience/expired/replayed responses.
- [ ] Local login user linking and role/tenant policy do not over-privilege.
- [ ] No raw SAML XML/NameID/tokens/keys logged.
- [ ] Session cookies and cross-site POST tested in production-like browsers.
- [ ] HTTPS, forwarded headers, and actual public EntityID/ACS tested behind ingress.
- [ ] Certificate/metadata refresh/rotation and approval policy exist.
- [ ] Local logout differs from SLO; do not claim all IdP sessions are destroyed.
- [ ] Negative E2E tests, audit, rollback, and partner permissions ready for real deployment.

## 23. Official References

1. [Spring Security — SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): AuthnRequest/Response flow, filters, RelyingPartyRegistration, and OpenSAML.
2. [Spring Security — SAML2 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html): `saml2Metadata` and SP metadata endpoints.
3. [Spring Security — Authentication Requests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html): request resolver, signing, and AuthnRequest repository.
4. [Spring Security — Authenticating SAML2 Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): validation, decryption, principal/authorities.
5. [Spring Security — SAML2 Single Logout](https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html): RP/AP-initiated logout, signing, and SLO endpoints.
6. [Spring Boot 3.5 — Spring Security / SAML2](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html): Boot properties, OpenSAML Maven repository, and auto-config.
7. [Keycloak — Getting Started on Docker](https://www.keycloak.org/getting-started/getting-started-docker): starting the image, realm, user.
8. [Keycloak — Server Administration Guide](https://www.keycloak.org/docs/latest/server_admin/): SAML clients, Client ID, Master SAML Processing URL, Redirect URIs, signing settings.
9. [OASIS SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): assertion, Conditions, and protocol.
10. [OASIS SAML 2.0 Profiles](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf): Web Browser SSO/SLO profiles.
11. [OASIS SAML 2.0 Metadata](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf): EntityID, KeyDescriptor, ACS, SingleSignOnService.
12. [OWASP — SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html): signature, issuer, audience, replay, and XML security.
13. [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): cookies, session rotation, local logout.
14. [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): avoiding logging credentials and PII.
15. [Spring Security — Servlet Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html): MockMvc/security integration.

**Conclusion:** A complete SAML2 SP is not merely an application displaying the Keycloak screen. It requires **IdP metadata properly imported into Spring**, **SP metadata exposing the right EntityID and ACS**, **a Keycloak SAML client configured with the exact EntityID/ACS and response signing**, and the browser completing **AuthnRequest → IdP authentication → SAMLResponse POST → OpenSAML signature/issuer/audience/recipient/time/correlation validation → Spring authenticated session**. Once the smoke test succeeds, continue with negative tests, business groups/roles, HTTPS/session/cookie/proxy, SLO, and certificate rotation before considering the system production-ready.