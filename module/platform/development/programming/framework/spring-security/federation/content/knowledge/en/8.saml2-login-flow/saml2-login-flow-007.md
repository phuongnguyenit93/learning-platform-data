# Saml2AuthenticationTokenConverter and Selecting the Matching Registration

## 1. Problem: One ACS, Multiple SAML Partners

In a **Spring Security Servlet** application using **SAML 2.0 Web Browser SSO**, a **Service Provider (SP/Relying Party)** may be configured with one or more **Identity Providers (IdP/Asserting Party)**. When the browser POSTs `SAMLResponse` to the **Assertion Consumer Service (ACS)**, Spring Security must know: **which partner configuration does this response belong to so it can use the right issuer, verification certificates, SP entityId, ACS, and validation rules?**

The centerpiece is **Saml2AuthenticationTokenConverter**. It is an **AuthenticationConverter** that transforms an **HttpServletRequest containing `SAMLResponse`** into an **unauthenticated `Saml2AuthenticationToken`**, while **selecting the matching `RelyingPartyRegistration`**. The result is passed to **AuthenticationManager / OpenSAML authentication provider** to validate the Response and Assertion. The converter is **not** the component that decides the user is logged in.

For example, an SP has two registrations:

| Property | Registration corp | Registration partner |
| --- | --- | --- |
| **registrationId** | corp | partner |
| **IdP entityID** | https://login.corp.example.org/saml | https://idp.partner.example.org/saml |
| **IdP SSO URL** | URL published by Corp IdP | URL published by Partner IdP |
| **IdP verification certificates** | Corp IdP signing key | Partner IdP signing key |
| **SP entityID** | Can be per-registration | Can be per-registration |
| **SP ACS** | /login/saml2/sso/corp | /login/saml2/sso/partner |

If a response from **Corp IdP** were verified with **Partner IdP**'s certificate, or if a response intended for **SP corp** were routed to **SP partner**, login must fail. The converter helps **identify the configuration to validate against**, whereas the authentication provider decides **whether the `SAMLResponse` is actually valid under that configuration**.

This lesson focuses on **the SAML2 login flow, Spring Boot 3.x/Spring Security 6.x, Java 17+**. Exact registration selection details and APIs may vary by version; practical examples use Spring Boot **3.3.5** for consistent syntax.

## 2. Objects with Easily Confused Names

| Object / Class | Meaning | Does It Authenticate the User? |
| --- | --- | --- |
| **RelyingPartyRegistration** | Configuration of the relationship between SP and one asserting party: entityId, ACS, IdP issuer/SSO URL, verification keys, signing/decryption keys. | No. |
| **RelyingPartyRegistrationRepository** | Store of permitted registrations, looked up by registrationId. | No. |
| **registrationId** | Technical key chosen by the app, like corp or partner, to identify a configuration. | No; not a SAML entityID. |
| **RelyingPartyRegistrationResolver** | Strategy for resolving a registration from an HTTP request and supplied registrationId. | No. |
| **DefaultRelyingPartyRegistrationResolver** | Built-in resolver that uses the repository to find registrations and resolve request-dependent URL placeholders. | No. |
| **Saml2AuthenticationTokenConverter** | Extracts `SAMLResponse`, selects registration, and builds an authentication request token. | **Does not verify** SAML Response/Assertion. |
| **Saml2AuthenticationToken** | **Unauthenticated** token carrying the Response, registration, and, when present, associated AuthnRequest. | Not yet. |
| **Saml2WebSsoAuthenticationFilter** | Receives ACS callbacks and delegates conversion/authentication to converter and `AuthenticationManager`. | Orchestrates. |
| **AuthenticationManager + OpenSAML provider** | Verifies signature, issuer, SAML conditions, correlation, decryption, and produces a valid Authentication. | **Yes, if all conditions pass.** |
| **Saml2Authentication** | User's Authentication result after SAML validation succeeds. | Authenticated; app permissions still checked separately. |

**`registrationId` is not a userId, NameID, IdP issuer, or SP entityID.** One IdP can have multiple registrations within the same SP app, e.g., for different tenants/SP entityIDs; and one registration points to one IdP with its own policy.

Example:

~~~text
registrationId: corp
IdP entityID:   https://login.corp.example.org/saml
SP entityID:    https://app.example.com/saml2/service-provider-metadata/corp
SP ACS:         https://app.example.com/login/saml2/sso/corp
~~~

These last three values need not be identical. The ID in the ACS URL helps select a registration, **yet does not by itself prove the identity of the IdP that sent the message**.

## 3. Where Does the Converter Sit in the Web Browser SSO Flow?

SP-initiated login diagram:

~~~text
Browser                  Spring Security SP                    Corp IdP
   |-- GET /private ------------>|                                |
   |<-- redirect /saml2/authenticate/corp ------------------------|
   |                             |-- builds AuthnRequest (ID=_r1)>|
   |                             |-- saves request + registrationId|
   |------------------------ AuthnRequest to IdP ----------------->|
   |<-------------------- SAMLResponse form after login -----------|
   |-- POST /login/saml2/sso/corp --> Saml2WebSsoAuthenticationFilter
   |                                  |
   |                                  v
   |                         Saml2AuthenticationTokenConverter
   |                                  |
   |                        selects RelyingPartyRegistration
   |                        + loads saved AuthnRequest if present
   |                        + builds Saml2AuthenticationToken
   |                                  |
   |                                  v
   |                       AuthenticationManager/OpenSAML provider
   |                        checks signature, issuer, audience,
   |                        destination, recipient, validity,
   |                        InResponseTo, and profile conditions
   |                                  |
   |                        valid: creates Saml2Authentication
   |<--------------- local session / resource access -------------|
~~~

Key steps:

1. **Saml2WebSsoAuthenticationRequestFilter** prepares an AuthnRequest for registration **corp** and sends the browser to the corresponding IdP.
2. A **Saml2AuthenticationRequestRepository** stores the pending AuthnRequest; the common default in Spring Security Servlet is **HttpSessionSaml2AuthenticationRequestRepository**.
3. The IdP authenticates the user and returns `SAMLResponse` via browser to the app's ACS.
4. **Saml2WebSsoAuthenticationFilter** triggers at the callback processing endpoint and invokes the AuthenticationConverter.
5. **Saml2AuthenticationTokenConverter** finds the matching registration using request/URL context or Response info when needed, then creates **Saml2AuthenticationToken**.
6. **AuthenticationManager** authenticates the token using the SAML provider of the running Spring Security/OpenSAML version.
7. Only after verification succeeds does Spring Security create an **authenticated `Authentication`**, update `SecurityContext`, and optionally persist an application session.

**Do not equate "converter selected a registration" with "user is authenticated".** Selecting a registration finds the configuration to validate against; signatures and full SAML conditions determine whether login is accepted.

## 4. Which Signals Does the Converter Use to Pick a Registration?

Per Spring Security documentation, the standard default mechanism can use the **saved AuthnRequest**, the **`registrationId` from the callback path**, and when neither is found, the **`Issuer` of `SAMLResponse`** to locate a registration. Exact precedence and fallback depend on version/implementation; never build your own clone assuming every Spring Security 6.x/7.x version uses the exact same internal algorithm.

### 4.1. Saved AuthnRequest Context

In an **SP-initiated flow**, Spring creates an AuthnRequest and stores transaction info, including the `registrationId` used when issuing the request. When the Response returns, the converter can look up the **AuthnRequest bound to the browser/session** and identify the original registration.

This is a strong **selection-context** signal because the SP knows which IdP it initiated login to. However, it is never a reason to skip verifying **Response.InResponseTo**, **SubjectConfirmationData.InResponseTo**, issuer, signature, audience, and destination.

Example:

~~~text
SP created AuthnRequest ID=_req_101 for registrationId=corp
IdP POSTs Response to ACS
Converter retrieves saved request -> sees registrationId=corp
Authentication provider checks whether Response actually matches _req_101,
corp IdP, SP entityID, ACS, signature, and validity period
~~~

If the Response instead carries **partner**'s issuer, the converter finding **corp** from the saved request **does not validate** the Response. The provider must reject due to trust-relationship mismatch or failing SAML conditions.

### 4.2. registrationId in the ACS Path

Common default endpoint:

~~~text
POST /login/saml2/sso/{registrationId}
~~~

Example:

~~~text
POST /login/saml2/sso/corp
POST /login/saml2/sso/partner
~~~

Spring can use the **registrationId** in the URL to query **RelyingPartyRegistrationRepository**. If the specified registrationId is not found, it must **reject the nonexistent configuration** via proper error handling; never auto-create a registration or accept arbitrary issuers.

**The URL is only a routing signal**, not proof of the IdP. Any client can POST to the ACS path; signature checks using the right IdP's verification credentials and full SAML conditions are still mandatory.

### 4.3. Response.Issuer When Request/registrationId Is Missing

With an ACS **lacking registrationId**, or when saved context cannot be found, Spring may attempt to infer the registration from **Issuer inside the SAML Response**.

Example:

~~~text
POST /saml/acs
  SAMLResponse has Response.Issuer = https://idp.partner.example.org/saml

Registration repository:
  corp    -> issuer https://login.corp.example.org/saml
  partner -> issuer https://idp.partner.example.org/saml

One registration matches issuer -> partner is candidate for verification.
~~~

**The Issuer read from the Response at this stage is untrusted data** because the message arrived from the browser. It is merely a **hint to select keys and configuration**; the **signature, issuer, destination, audience, certificate, and SAML conditions must still be verified** before confirming identity.

**Dangerous edge case:** Two registrations share the **same IdP entityID**, e.g., **corp-eu** and **corp-us**, yet have different SP entityIDs, ACS URLs, or tenants. Without a saved request and without `registrationId` in the URL, **relying solely on issuer is ambiguous**. Design separate ACS URLs, retain login context, or use a vetted resolver strategy; **never pick a registration arbitrarily**.

### 4.4. Practical Decision Table

| Saved AuthnRequest? | URL Has registrationId? | Response.Issuer | Handling |
| --- | --- | --- | --- |
| Yes, belongs to corp | Has corp | Corp IdP | Selects corp config as candidate; provider verifies all conditions. |
| Yes, belongs to corp | No ID on path | Corp IdP | Can resolve corp from saved request; still must correlate properly. |
| No | Has partner | Partner IdP | Finds partner from repository; must verify issuer, signature, ACS, audience, and unsolicited policy. |
| No | No | Issuer matches single registration | Can look up by `Response.Issuer`; verify full message. |
| No | No | Issuer matches multiple registrations | **Insufficient basis for unique selection**; requires context or appropriate resolver. |
| No | Has invalid-id | Any | Reject nonexistent registration; never auto-create partner. |
| Has corp | Has partner | Any | **Context conflict**; investigate callback/URL/registration—do not allow login just because one field matched. |
| Has corp | Has corp | Partner IdP | Message violates trust; provider must reject even though URL says corp. |
| No | No | Unregistered issuer | Reject untrusted partner. |

This table states **the secure decisions to achieve**, not a claim about exact internal statement ordering in every version. Specifically, when signals conflict, let the provider and validation policy reject; **never relax validation to accept mismatches**.

## 5. RelyingPartyRegistrationRepository and Resolvers

**RelyingPartyRegistrationRepository** is the configuration source of **permitted partners**. Registrations can be configured via Spring Boot YAML/properties, built manually from IdP metadata, or retrieved from an application-managed repository.

**RelyingPartyRegistration** holds two sides:

- **Relying party (SP)**: entityId, assertionConsumerServiceLocation, signingX509Credentials, decryptionX509Credentials, logout endpoints per config.
- **Asserting party (IdP)**: entityId/issuer, singleSignOnServiceLocation/binding, verificationX509Credentials, logout info, AuthnRequest signing policy.

**DefaultRelyingPartyRegistrationResolver** uses the repository to find configuration by request and registrationId, and resolves template placeholders in the request context. For instance, URLs using **{baseUrl}** must reflect the application's real public scheme/host/port.

Do not confuse:

~~~text
RelyingPartyRegistrationRepository       store of trusted registrations
DefaultRelyingPartyRegistrationResolver  selects/resolves registration from request
Saml2AuthenticationTokenConverter        creates input auth token bound to registration
OpenSAML provider                        decides if Response/Assertion is valid
~~~

Having only one registration does not mean the converter skips checks: even with a single IdP, **Response.Issuer must still match IdP entityID**, and signatures/SAML conditions must still be verified.

### When Should You Keep the Defaults?

Keep the default converter/resolver when:

- The ACS uses the framework's **{registrationId}** URL;
- SP-initiated flows retain AuthnRequests in the default repository;
- Each IdP has accurate metadata and verification certificates;
- No special multi-tenant routing or non-standard binding is needed;
- Standard **`saml2Login()`** config works with your sandbox IdP.

Do not add a custom converter merely because the system has two IdPs; multiple registrations are a standard capability of Spring Security SAML2 SP.

## 6. AuthnRequestRepository and Correlation/Session Issues

When the SP initiates SAML login, the IdP takes time to authenticate the user, run MFA, and return a Response. Spring must locate the original request to correlate the login:

~~~text
AuthnRequest.ID = _req_101
registrationId  = corp
saved request   = SAML context in session/repository
Response.InResponseTo = _req_101
SubjectConfirmationData.InResponseTo = _req_101
~~~

**HttpSessionSaml2AuthenticationRequestRepository** is the common default: it binds pending AuthnRequests to the **browser's `HttpSession`**. This brings a clear security benefit: if an attacker tries feeding an attacker-session Response into a victim's browser, the victim's browser lacks the matching AuthnRequest and is rejected by correlation policy.

Never treat finding a response via **RelayState** or **InResponseTo** alone as proof that the request belongs to **the browser currently logging in**. Using a distributed cache keyed solely by a browser-supplied ID can lose the **login CSRF/login fixation** protection provided when requests are tied to `HttpSession`. Design explicit browser/session binding and replay defenses.

Common causes of lost pending requests:

1. **Session cookie withheld** on the POST redirect from IdP due to SameSite, Secure, domain, proxy, or browser policies.
2. **Session timeout** while the user spends too long on MFA.
3. **Cluster** of multiple nodes not sharing `HttpSession`, or inconsistent routing.
4. **Multiple tabs** creating multiple AuthnRequests while a custom repository stores only one entry and overwrites the other.
5. **Mismatched registrationId/ACS** across outbound request, SP metadata, and returned Response.
6. **HTTP/HTTPS or hostname shift** between AuthnRequest and callback breaking cookies/sessions and template URLs.
7. **Already-consumed request** when the Response is submitted a second time.

Never fix these issues by disabling **InResponseTo** checks or allowing unsolicited logins by default. Fix cookies/sessions, repositories, expiry, proxies, and IdP configuration.

### Can a Single Shared ACS URL Be Used?

Design-wise, a **shared ACS** may be needed, such as:

~~~text
https://app.example.com/saml/acs
~~~

when IdP partners cannot accept callback paths containing `registrationId`. Yet if the shared URL lacks an ID, the system needs **another lookup signal** (saved AuthnRequest, unique issuer, or a sound resolver strategy). Also configure consistently:

- **Saml2LoginConfigurer.loginProcessingUrl** must accept POSTs at the new endpoint;
- **RelyingPartyRegistration.assertionConsumerServiceLocation** on every registration must match the ACS URL registered at the IdP;
- the converter and repository must resolve the right partner;
- **Response.Destination**, **SubjectConfirmationData.Recipient**, and **Audience** must still be verified by the provider.

Changing **loginProcessingUrl** alone without updating **ACS metadata/IdP registration** causes the IdP to send Responses to the old URL or triggers validation mismatches.

## 7. IdP-initiated SSO and the Issuer Fallback Problem

**SP-initiated SSO**: browser starts at the SP; SP builds AuthnRequest, saves registrationId and request ID, and sends to IdP. This is the cleanest model for tying responses to sessions.

**IdP-initiated SSO** (unsolicited): user clicks an app tile in the IdP portal; IdP sends Response to SP **without the SP having sent an AuthnRequest**. With no pending request, the converter may have to rely on URL/issuer to locate the registration.

In unsolicited flows:

- There is no **AuthnRequest.ID** to correlate with `Response.InResponseTo` as in SP-initiated.
- There must be an explicit policy allowing or denying unsolicited logins per partner.
- Signature, IdP issuer, recipient, destination, audience, assertion expiration, anti-replay, and login CSRF defenses remain critical.
- A SAML Response's issuer is **untrusted input** until signature and conditions are verified.
- One IdP may share an issuer across multiple SP registrations, so issuer alone may be insufficient.

Spring Security can accept SAML responses from IdP-initiated flows depending on configuration and version, yet **never assume every unsolicited mode satisfies your organization's policy by default**. If business workflows do not need IdP-initiated, enforce a rejection policy and test it; if needed, design login CSRF and replay defenses with your IdP admin.

## 8. Spring Boot 3.3.5 / Java 17 Example with Two IdPs

The following example has **one Spring SP** with two registrations: **corp** and **partner**. Each registration uses independent IdP metadata. The framework selects the right configuration on callback and verifies Responses per partner; the app never reads `NameID` directly from an unverified `SAMLResponse`.

**Prerequisites:**

- Java 17+, Maven able to resolve dependencies;
- Two real IdPs or two sandbox IdP configs with valid metadata;
- IdPs registered with matching **SP entityID + ACS URL** per registration;
- SP signing/decryption private keys added if partners require them;
- Localhost is for learning only; production uses public HTTPS URLs and secure proxy configuration.

### 8.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>saml-registration-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <repositories>
        <repository>
            <id>shibboleth-releases</id>
            <url>https://build.shibboleth.net/maven/releases/</url>
            <snapshots>
                <enabled>false</enabled>
            </snapshots>
        </repository>
    </repositories>

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

This is a Spring Security **Service Provider**, not a SAML IdP. The Shibboleth repository may be needed for OpenSAML; follow your organization's approved repository and dependency management policies.

### 8.2. application.yml

**src/main/resources/application.yml**

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              metadata-uri: ${CORP_IDP_METADATA_URI}
          partner:
            assertingparty:
              metadata-uri: ${PARTNER_IDP_METADATA_URI}

server:
  port: 8080
  servlet:
    session:
      timeout: 30m
~~~

**CORP_IDP_METADATA_URI** and **PARTNER_IDP_METADATA_URI** are two environment variables holding **real IdP metadata URLs**. Replace with addresses confirmed by each partner's IdP administrator; `example.org` domains in this lesson are illustrative only. Never use unverified URLs as trust sources.

Boot creates a **RelyingPartyRegistrationRepository** containing registrationIds **corp** and **partner**. Each entry populates issuer/SSO URL/certificates from its metadata, while SP entityID and ACS use defaults or overrides matching what is registered at each IdP.

### 8.3. Application

**src/main/java/com/example/samlregistration/SamlRegistrationApplication.java**

~~~java
package com.example.samlregistration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SamlRegistrationApplication {
    public static void main(String[] args) {
        SpringApplication.run(SamlRegistrationApplication.class, args);
    }
}
~~~

### 8.4. SecurityConfig Using the Default Converter

**src/main/java/com/example/samlregistration/SecurityConfig.java**

~~~java
package com.example.samlregistration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error",
                    "/saml2/metadata", "/saml2/metadata/**",
                    "/saml2/service-provider-metadata/**").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults());

        return http.build();
    }
}
~~~

**Important:** Even though **Saml2AuthenticationTokenConverter** is not named explicitly in `SecurityConfig`, Spring Security configures the default converter for SAML login. That is the right choice when using standard ACS URLs and the normal request repository.

### 8.5. Controller Using Only the Authenticated Principal

**src/main/java/com/example/samlregistration/DemoController.java**

~~~java
package com.example.samlregistration;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/")
    public String home() {
        return "SAML registration demo";
    }

    @GetMapping("/me")
    public String me(@AuthenticationPrincipal Saml2AuthenticatedPrincipal user) {
        return "NameID=" + user.getName();
    }
}
~~~

The controller never touches **SAMLResponse**; users reach **/me** only after Spring Security/OpenSAML finishes verification and establishes `Authentication`.

### 8.6. Running and Observing

Set the real metadata URI environment variables for your OS and run inside the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Behaviors to verify:

1. **GET http://localhost:8080/** returns the exact body **SAML registration demo** once the app starts cleanly.
2. **GET http://localhost:8080/saml2/authenticate/corp** initiates login to **Corp IdP**; Spring saves the AuthnRequest bound to registration `corp`.
3. **GET http://localhost:8080/saml2/authenticate/partner** initiates login to **Partner IdP**.
4. **POST http://localhost:8080/login/saml2/sso/corp** is the default ACS callback for `corp`, receiving `SAMLResponse` from the IdP. **Never** POST fake data to bypass signatures.
5. **GET http://localhost:8080/saml2/metadata/corp** outputs **corp SP metadata**, helping inspect entityID/ACS; likewise for `partner`.
6. **GET http://localhost:8080/me** while unauthenticated triggers login (with multiple IdPs, an IdP selection page may appear), and upon receiving a valid SAML Response returns **NameID=<value issued by IdP>**. There is no fixed stdout for NameID since it depends on the IdP account.

With two IdPs, **each registration must be tested separately** from redirect, issuer, and SSO endpoint to ACS, certificates, assertion audience, and final access rights.

## 9. When Should You Configure the Converter Explicitly?

In most applications, **you do not need to instantiate `Saml2AuthenticationTokenConverter` yourself**. However, if you need a different resolver or want to change callback handling, Spring Security exposes **`saml2Login.authenticationConverter(AuthenticationConverter)`**.

The example **replaces the previous `SecurityConfig` completely with this version**. It explicitly builds the converter with **DefaultRelyingPartyRegistrationResolver** without replacing validators or authenticating Assertions itself.

**src/main/java/com/example/samlregistration/SecurityConfig.java – replacement version**

~~~java
package com.example.samlregistration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.web.DefaultRelyingPartyRegistrationResolver;
import org.springframework.security.saml2.provider.service.web.Saml2AuthenticationTokenConverter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            RelyingPartyRegistrationRepository registrations) throws Exception {

        var resolver = new DefaultRelyingPartyRegistrationResolver(registrations);
        var converter = new Saml2AuthenticationTokenConverter(resolver);

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error",
                    "/saml2/metadata", "/saml2/metadata/**",
                    "/saml2/service-provider-metadata/**").permitAll()
                .anyRequest().authenticated())
            .saml2Login(saml2 -> saml2.authenticationConverter(converter))
            .saml2Metadata(metadata -> {});

        return http.build();
    }
}
~~~

In this configuration:

- The resolver looks up **RelyingPartyRegistration** from the repository based on request signals; the converter uses the resolver to build **Saml2AuthenticationToken**.
- **Saml2AuthenticationTokenConverter** can retrieve the saved AuthnRequest via **Saml2AuthenticationRequestRepository**. When customizing the request repository, ensure **the AuthnRequest-creating filter, converter, and ACS callback filter share the exact same repository/state store**; avoid saving requests in one place while callbacks query another.
- **saml2Login.authenticationConverter(...)** swaps the strategy turning HTTP requests into tokens. It **cannot** bypass OpenSAML signature/issuer/audience checks.
- Using the default resolver here demonstrates API boundaries; in practice, configure explicitly only when justified. **Never declare two `SecurityConfig` beans simultaneously**.
- If using a custom **RelyingPartyRegistrationResolver**, define clearly how partners are chosen and keep full SAML verification in the provider afterward.

### Updating ACS URL in Three Places Together

Suppose business needs require endpoint **/custom/saml/acs**. Changing the DSL alone is not enough:

~~~java
// Illustrative configuration snippet inserted into saml2Login in SecurityFilterChain:
.saml2Login(saml2 -> saml2.loginProcessingUrl("/custom/saml/acs"))
~~~

This snippet **cannot run standalone**; you must set **assertionConsumerServiceLocation** on `RelyingPartyRegistration` to match and configure the IdP's **Reply URL/ACS** to **https://public-host/custom/saml/acs**. When the endpoint omits **{registrationId}**, verify carefully that the converter resolves the registration unambiguously from the saved request or issuer lookup; you may need a custom converter depending on version.

Omitting any of these steps typically causes callback **404, registration not found, invalid Destination/Recipient, or ACS mismatch**. Never fix it by allowing any issuer/ACS.

## 10. Registration Selection for Multiple Tenants

One **IdP** may issue SAML for **multiple tenants**, or one SP may use a **shared ACS** across multiple partners. Distinguish at least these pieces of data:

| Property | Role | Trusted Immediately on HTTP Request? |
| --- | --- | --- |
| **registrationId** from URL | Hint to pick an entry in the repository. | **Not** proof of the IdP. |
| **Response.Issuer** | Hint of which IdP issued the Response. | **Untrusted** before signature verification. |
| **AuthnRequest saved in session** | Transaction context created by SP. | SP-managed data, yet still requires Response matching and security checks. |
| **HTTP Host / X-Forwarded-Host** | Can assist tenant/ACS routing. | Use only with trusted proxies and strict host allowlists. |
| **NameID / Attributes** | Identity/attributes claimed by Assertion. | **Trusted only after provider verifies Assertion**. |
| **Tenant query parameter** | Browser-supplied input. | Never use for uncontrolled trust/certificate selection. |

**Especially dangerous:** taking a request parameter like **?tenant=arbitrary** and fetching metadata/certificates from a browser-supplied URL. That lets an unauthenticated client control trust anchors and can cause **SSRF, confused-deputy attacks, or cross-tenant login**.

A secure multi-tenant system typically:

1. Maintains an **allowlist** of approved registrationIds, IdP entityIDs, SP entityIDs, and ACS URLs.
2. In **SP-initiated flows**, correlates browser session, `AuthnRequest.ID`, and chosen registration.
3. If using a shared URL, builds an unambiguous **deterministic lookup** or requires `registrationId` in a controlled route/host.
4. Never uses an unverified issuer as an authorization grant; issuer only selects configuration for **verification**.
5. After authentication, maps the principal to an **internal tenant** and enforces authorization in the business layer rather than relying solely on the ACS path.
6. Includes negative tests: wrong issuer, wrong cert, wrong audience, cross-tenant, missing/expired request ID, response replay, and spoofed Host headers.

### Two Registrations Pointing to the Same IdP Issuer

Suppose **corp-vn** and **corp-sg** both use **IdP entityID=https://login.corp.example.org/saml**, yet have different SP entityIds/ACS URLs. **Issuer fallback cannot distinguish the two registrations without additional information.**

A reliable design retains **registrationId from the saved AuthnRequest**, uses **separate ACS URLs**, or applies a resolver with approved routing rules. Never use an **unverified IdP user email/NameID** to select a tenant.

## 11. Standalone Java 17 Example: Simulating Registration Selection Principles

This is a **standalone Java 17 program** illustrating **partner-selection signals** and ambiguity cases. It **does not mirror internal Spring Security branches**, **does not parse `SAMLResponse`**, and **cannot authenticate**. The simulation intentionally applies a **conflict-rejection policy** when request/route differ, since real integrations should investigate mismatches rather than logging in.

**RegistrationChoiceDemo.java**

~~~java
import java.util.List;
import java.util.Map;
import java.util.Set;

public class RegistrationChoiceDemo {

    static String choose(
            String savedRegistrationId,
            String routeRegistrationId,
            String responseIssuer,
            Set<String> allowed,
            Map<String, List<String>> byIssuer) {

        if (savedRegistrationId != null) {
            if (!allowed.contains(savedRegistrationId)) {
                return "UNRESOLVED";
            }
            if (routeRegistrationId != null
                    && !savedRegistrationId.equals(routeRegistrationId)) {
                return "CONFLICT";
            }
            return savedRegistrationId;
        }

        if (routeRegistrationId != null) {
            return allowed.contains(routeRegistrationId)
                    ? routeRegistrationId : "UNRESOLVED";
        }

        List<String> candidates = byIssuer.getOrDefault(responseIssuer, List.of());
        if (candidates.size() != 1) {
            return "UNRESOLVED";
        }

        String only = candidates.get(0);
        return allowed.contains(only) ? only : "UNRESOLVED";
    }

    public static void main(String[] args) {
        Set<String> allowed = Set.of("corp-vn", "corp-sg", "partner");

        Map<String, List<String>> byIssuer = Map.of(
                "https://login.corp.example.org/saml",
                List.of("corp-vn", "corp-sg"),
                "https://idp.partner.example.org/saml",
                List.of("partner"));

        String corpIssuer = "https://login.corp.example.org/saml";
        String partnerIssuer = "https://idp.partner.example.org/saml";

        System.out.println("saved request: "
                + choose("corp-vn", "corp-vn", corpIssuer, allowed, byIssuer));
        System.out.println("route: "
                + choose(null, "partner", partnerIssuer, allowed, byIssuer));
        System.out.println("issuer unique: "
                + choose(null, null, partnerIssuer, allowed, byIssuer));
        System.out.println("issuer ambiguous: "
                + choose(null, null, corpIssuer, allowed, byIssuer));
        System.out.println("conflict: "
                + choose("corp-vn", "corp-sg", corpIssuer, allowed, byIssuer));
        System.out.println("unknown route: "
                + choose(null, "unknown", partnerIssuer, allowed, byIssuer));
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac RegistrationChoiceDemo.java
java RegistrationChoiceDemo
~~~

**Exact stdout:**

~~~text
saved request: corp-vn
route: partner
issuer unique: partner
issuer ambiguous: UNRESOLVED
conflict: CONFLICT
unknown route: UNRESOLVED
~~~

Explanation:

- **saved request** illustrates known SP-initiated context with a consistent route.
- **route** illustrates `registrationId` present in the ACS path.
- **issuer unique** illustrates a single allowlisted partner matching the issuer.
- **issuer ambiguous** illustrates the same IdP issuer mapped to multiple registrations; never pick arbitrarily.
- **conflict** is a **conflict-rejection policy of this simulation program**, not a claim about a specific exception or branch in Spring's default converter.
- **unknown route** rejects an unregistered ID without fetching new metadata dynamically.

**Never use `choose()` on production `SAMLResponse`s to mint `Authentication`.** A selection only leads to a valid login after Spring Security/OpenSAML **verifies the full Response/Assertion, signature, issuer, audience, recipient, destination, timestamps, correlation, and replay policy**.

## 12. Limits of Resolving Registration by Issuer

**Where is `Response.Issuer`?** It is an element in the **SAML protocol Response**, not a callback URL attribute. The converter may read it to locate a candidate for verification; however, before signatures and trust are proven, an attacker can POST arbitrary XML/Base64 to the ACS.

**Why not use issuer as proof?** If an attacker sets Issuer to IdP X, that does not give the attacker IdP X's signing key. When the converter selects configuration X, the provider verifies the signature with X's certificate and rejects on mismatch. If an application blindly trusts the issuer and marks Authentication valid, it eliminates the most critical security boundary.

**What if two IdPs share an issuer?** Federation-wise, `entityID` should uniquely identify a partner; if two configurations share an issuer, ambiguity must be resolved. Never rely on repository iteration order to pick a registration; require reliable context such as `registrationId`/ACS and request correlation.

**What if IdP metadata changes its issuer?** Never auto-accept a new issuer from a Response; verify the change through IdP onboarding/rotation procedures, update the registration, and test.

**What if `Response.Issuer` and `Assertion.Issuer` differ?** The provider must check issuer at all profile-required locations. Never allow one layer to use issuer A while another uses issuer B to slip past validation.

**What if a Response is signed with a key not in the chosen registration?** Reject per trust policy. Never sequentially try every certificate from every tenant and conclude "whichever key verifies identifies the right tenant" without a routing contract and security policy.

## 13. Test Matrix for Converter and Partner Selection

In test environments, build **valid `SAMLResponse`s signed with test keys** to isolate one condition at a time. If you simply edit already-signed XML, the signature will fail before reaching the check you wanted to test; do not infer root causes from generic failures.

| # | Scenario | Expectation |
| --- | --- | --- |
| 1 | SP sends AuthnRequest for corp, Corp IdP returns valid Response to corp ACS | Converter picks right candidate; provider verifies and allows login. |
| 2 | SP sends AuthnRequest for partner, Partner IdP returns valid Response to partner ACS | Same, for partner registration. |
| 3 | ACS URL specifies corp yet registration is absent from repository | Cannot resolve registration; authentication rejected. |
| 4 | ACS picks corp, Response has partner issuer and valid partner signature | **Rejected** for violating corp trust/profile. |
| 5 | ACS has corp yet Response is signed with a cert untrusted by corp | **Rejected** on signature/trust. |
| 6 | AuthnRequest saved for corp, `Response.InResponseTo` has different request ID | **Rejected** on correlation. |
| 7 | ACS URL matches yet `SubjectConfirmationData.Recipient` names another ACS | **Rejected** on bearer confirmation. |
| 8 | `Response.Destination` mismatches public ACS URL | **Rejected** on destination/profile validation. |
| 9 | `AudienceRestriction` lacks SP entityID of selected registration | **Rejected** on audience. |
| 10 | Session holding pending request lost on callback | Never bypass `InResponseTo`; inspect cookies/repository. |
| 11 | IdP-initiated unsolicited Response sent to a registered ACS | Accepted only if **policy allows unsolicited**, and all validation/replay/login CSRF checks pass. |
| 12 | IdP-initiated Response has unregistered issuer | Reject unknown IdP. |
| 13 | Shared URL without ID, one IdP issuer maps to two registrations | Resolver must handle ambiguity; never pick arbitrarily. |
| 14 | Response past `NotOnOrAfter` or `Conditions` expired | **Rejected**, even if issuer/registrationId match. |
| 15 | IdP rotated cert unannounced and SP still has old trust | **Rejected** on signature; execute proper rotation process. |
| 16 | Response replayed after AuthnRequest was consumed | **Rejected** per one-time/correlation/replay controls. |
| 17 | App runs behind HTTPS proxy while ACS metadata shows internal HTTP | Fix base URL/forwarded headers; never disable recipient/destination validation. |
| 18 | Two concurrent login tabs to two IdPs while custom store holds one entry | Check store/correlation; never match a Response to another request. |
| 19 | Message lacks `SAMLResponse` or has corrupt Base64/XML | No Authentication created; return error rather than treating as logged-in anonymous. |
| 20 | Custom converter returns `Saml2AuthenticationToken` without validating signature | `AuthenticationManager` must run validation; custom converter **must never set `authenticated=true`**. |

A negative test case passes only when the SP **properly rejects the invalid response**. Never aim for "everything passes" by weakening validation.

## 14. Troubleshooting Common Errors

| Symptom | Check First | Fix |
| --- | --- | --- |
| **Relying party registration not found** | `registrationId` in ACS, YAML, and repository. | Fix ID/path or add approved registration. |
| **Registration not found on shared ACS URL** | Is there a saved AuthnRequest? Does Response issuer resolve uniquely? | Use ID-containing URL, retain request correlation, or design explicit resolver. |
| **Issuer mismatch** | IdP `Response.Issuer`, `assertingParty.entityId` of chosen registration. | Fix partner/config; never drop issuer check. |
| **Invalid signature** | IdP verification certificates, key rotation, signed Response/Assertion policy. | Update metadata/certs via trusted channel. |
| **InResponseTo mismatch** | Saved AuthnRequest ID, HttpSession, repository, and callback. | Fix session/cookie/TTL/cluster; never drop correlation. |
| **Recipient/Destination mismatch** | Registration ACS, public URL, reverse proxy, and metadata. | Align HTTPS host/path/port at both SP and IdP. |
| **Login works in one tab, fails in another** | Concurrent AuthnRequests and how they are saved/read. | Design request store for concurrency or enforce appropriate UX. |
| **IdP portal SSO fails while SP-initiated works** | Unsolicited policy, ACS, issuer fallback, RelayState, and login CSRF. | Design/test IdP-initiated explicitly if required. |
| **Response matches issuer yet wrong audience** | SP entityId and Assertion's `AudienceRestriction`. | Fix IdP application registration and metadata. |
| **URL shifts across proxy between GET login and POST callback** | Forwarded host/scheme, `SameSite`/`Secure` cookies, and LB. | Align public baseUrl and trusted proxy config. |
| **Right user logs in yet gets wrong tenant permissions** | Post-validation mapping of principal to tenant/authorities. | Separate authorization; never pull tenant from unverified fields. |

### Essential Yet Safe Logging

In sandbox/debug environments, log **registrationId**, ACS path (without payload), internal correlation ID, validation error type, and lookup method used. Log issuer/host only normalized per policy; never dump raw `SAMLResponse`, Assertions, signatures, sensitive NameIDs, session cookies, authorization credentials, or private keys. Partner selection needs enough trace to tell where a request was routed, yet **logs must never introduce new vulnerabilities**.

## 15. Important Misconceptions

1. **"Saml2AuthenticationTokenConverter authenticates the user."** False: it **prepares the input token** and selects a registration; the provider verifies.
2. **"registrationId is the IdP entityID."** False: `registrationId` is a technical key in the repository; IdP issuer is a separate SAML value.
3. **"The path `/login/saml2/sso/corp` proves the Response came from Corp IdP."** False: any client can POST that URL; signature/issuer/profile prove authentic origin.
4. **"With a single IdP, RelyingPartyRegistration isn't needed."** False: the app still needs trust/SP/IdP config for verification.
5. **"Response.Issuer alone suffices for multi-tenant."** False: one issuer can map to multiple registrations, and pre-validation Responses are untrusted.
6. **"If the converter found a request in HttpSession, skip InResponseTo validation."** False: the saved request provides the reference to **verify correlation**, not replace it.
7. **"Just change loginProcessingUrl without updating ACS metadata."** False: the IdP must send Responses to the right URL and the SP must validate recipient/destination.
8. **"To make every IdP work, try all certs until one verifies."** False: risks cross-tenant trust confusion; enforce registration policy and verify against the right partner.
9. **"A custom converter can return an authenticated Authentication."** False: converters must never mark unvalidated Responses as authenticated.
10. **"IdP-initiated always has InResponseTo."** False: there is no originating AuthnRequest; requires dedicated policy and login CSRF/replay defenses.
11. **"Every Spring Security version shares the same classes/providers."** False: APIs, OpenSAML packages, and customization hooks change between 6.x and 7.x; check javadoc for your exact dependency.
12. **"Fix missing registration by disabling signature validation."** False: breaks security; fix routing, repository, correlation, or config instead.

## 16. Review Questions

**1. Why must the converter select `RelyingPartyRegistration` before verifying the Response?**  
Because the provider needs the **expected IdP issuer, verification certificates, SP entityId, ACS, and policies** to verify the Response against the right partner.

**2. Once the converter builds `Saml2AuthenticationToken`, is the user considered logged in?**  
**No.** That token is unauthenticated; `AuthenticationManager`/OpenSAML provider must validate `SAMLResponse`/Assertion before producing a valid `Saml2Authentication`.

**3. A Response arrives at `/login/saml2/sso/corp` with Issuer belonging to partner. Should login succeed because the route is valid?**  
**No.** The route only selects configuration; issuer/signature/audience/destination must match the trusted registration.

**4. Two registrations share the same IdP issuer, the callback lacks registrationId, and there is no saved AuthnRequest. Is issuer fallback sufficient?**  
**No.** A unique selection context or secure resolver is required; never pick arbitrarily.

**5. Losing HttpSession after MFA prevents the SP from finding AuthnRequest. What is the right action?**  
Inspect **SameSite, Secure, domain, timeout, proxy, session cluster, and request repository**. Never disable `InResponseTo` validation.

**6. Should you write a custom AuthenticationConverter when two registrations differ and default URLs already work?**  
Usually **no**. The default converter handles multiple registrations with standard URLs and request context; customize only for unsupported requirements.

**7. What does an IdP-initiated unsolicited Response need beyond mapping the issuer?**  
An **explicit allow policy** plus full verification of signature, issuer, recipient, audience, validity period, and anti-replay/login CSRF defenses; without a saved request, address its distinct risks explicitly.

## 17. Official References

1. [Spring Security – SAML 2.0 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): SAML Web Browser SSO, `Saml2WebSsoAuthenticationFilter`, converter, and authentication provider.
2. [Spring Security – Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): customizing ACS, `RelyingPartyRegistration` lookup, `AuthenticationConverter`, validation, and principal mapping.
3. [Spring Security – Producing AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html): `Saml2AuthenticationRequestRepository`, `HttpSession`, `RelayState`, and risks of caching requests.
4. [Spring Security Javadoc – Saml2AuthenticationTokenConverter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/Saml2AuthenticationTokenConverter.html): constructor with `RelyingPartyRegistrationResolver`, `convert`, and authentication request repository. **Check the 6.x version when deploying Boot 3.x.**
5. [Spring Security Javadoc – DefaultRelyingPartyRegistrationResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/web/DefaultRelyingPartyRegistrationResolver.html): resolving registrations from requests, `registrationId`, and template URLs.
6. [OASIS SAML 2.0 Profiles](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf): AuthnRequest/Response correlation and issuer/audience/destination/recipient requirements in Web Browser SSO.

**Key takeaway:** **`Saml2AuthenticationTokenConverter` selects the partner configuration and builds an unauthenticated token; `AuthenticationManager`/OpenSAML provider verifies `SAMLResponse` against that exact configuration.** In multi-IdP/multi-tenant systems, **saved AuthnRequests, `registrationId` at ACS, and `Response.Issuer`** are signals with distinct purposes; never turn any unverified signal into proof of identity.
