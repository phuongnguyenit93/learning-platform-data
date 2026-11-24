# NameIDPolicy and Agreeing on Identifier Format with the IdP

> **Module:** Spring Security – federation. **Parent topic:** AuthnRequest Customization. This lesson focuses on the `<samlp:NameIDPolicy>` element in SAML 2.0, how to choose an identifier format between the Service Provider (SP) and Identity Provider (IdP), configure Spring Security, and verify actual SSO results.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **`NameIDPolicy` in the AuthnRequest** from **`NameID` in the Assertion/Subject** and from the application's internal account identifier key.
2. Understand the three attributes `Format`, `SPNameQualifier`, and `AllowCreate`, when to omit each attribute, and the constraints under SAML Core/Errata.
3. Compare `persistent`, `transient`, `emailAddress`, and `unspecified`, especially regarding stability, uniqueness, scope, and privacy.
4. Agree with the IdP on a testable “identity contract”: issuer, SP entity ID, NameID format, qualifiers, account mapping, lifecycle, migration, and error behavior.
5. Customize the AuthnRequest per registration using `OpenSaml4AuthenticationRequestResolver` on Spring Boot 3.3/Spring Security 6.3 while preserving SAML security checks.
6. Verify the **actual identifier issued by the IdP** after the Response/Assertion is verified, rather than treating the SP sending NameIDPolicy as sufficient.
7. Recognize interoperability errors with IdPs, cases where NameID cannot be used as a long-term account key, and how to handle them safely.

## 2. Typical Scenario

The **Partner Orders Portal** application uses SAML SSO. Employees of Partner A need to return to the same internal account even if their email changes. On the first login, the IdP issues:

~~~xml
<saml:NameID
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    Format="urn:oasis:names:tc:SAML:2.0:nameid-format:transient">
    _tmp_7a31
</saml:NameID>
~~~

On the next login, the IdP issues `_tmp_b22c`. Both Assertions may be valid; however, **the SP cannot stably recognize the same user via a transient NameID**. If that value is used as the account key, the application may create a new account on every SSO login or fail to find prior permissions.

Another approach is asking the IdP to issue a `persistent` NameID. However, simply sending `NameIDPolicy Format=persistent` does not make the IdP automatically commit to the change: the IdP might not support it, might require separate configuration, might return an error, or might implement its own interpretation. Therefore, three layers are needed:

1. **Prior agreement with the IdP:** format, value source, scope, stability, lifetime, and migration.
2. **Protocol request:** when appropriate, set `NameIDPolicy` in the AuthnRequest using standard Spring Security/OpenSAML APIs.
3. **Post-login verification:** process NameID **only within a verified Assertion**, validate format/scope, and link to a local user per policy.

**Core message:** `NameIDPolicy` is **what the SP asks the IdP to do**; `Subject/NameID` in a valid Assertion is **what the IdP actually asserted**; application authorization is **what the SP decides itself**.

## 3. Position of NameIDPolicy in SAML2 Web Browser SSO

~~~text
Browser                SP (Spring Security)              IdP
   |                           |                            |
   | GET /private              |                            |
   |-------------------------->|                            |
   |                           | Build AuthnRequest         |
   |                           | - Issuer = SP entity ID    |
   |                           | - NameIDPolicy             |
   |                           | - ACS + ID + timing        |
   |<------ Redirect/POST -----|                            |
   |--------------------- SAMLRequest --------------------->|
   |                           |                 Authenticate|
   |<-------------------- SAMLResponse ---------------------|
   | POST ACS                  |                            |
   |-------------------------->| Validate signature,        |
   |                           | issuer, time, audience,     |
   |                           | recipient, InResponseTo     |
   |                           | then Subject/NameID        |
   |                           | Link local user + authorize|
   |<------ SP session --------|                            |
~~~

SAML2 uses two XML namespaces:

| Element | Namespace | Meaning |
| --- | --- | --- |
| `<samlp:AuthnRequest>` | `urn:oasis:names:tc:SAML:2.0:protocol` | Authentication request message sent by the SP. |
| `<samlp:NameIDPolicy>` | `urn:oasis:names:tc:SAML:2.0:protocol` | Preference regarding identifier format/scope. |
| `<saml:Assertion>` | `urn:oasis:names:tc:SAML:2.0:assertion` | Assertion issued by the IdP. |
| `<saml:Subject>` | `urn:oasis:names:tc:SAML:2.0:assertion` | Subject of the assertion. |
| `<saml:NameID>` | `urn:oasis:names:tc:SAML:2.0:assertion` | Identifier actually issued by the IdP for the subject. |

`NameIDPolicy` is an **optional** element of AuthnRequest; it **does not reside in the Assertion**. If the SP omits it, the IdP usually uses its SAML application configuration or established contract to pick a format. Omitting NameIDPolicy does not mean the SP may skip checking NameID in the Assertion.

### Example AuthnRequest with NameIDPolicy

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_req-a42"
    Version="2.0"
    IssueInstant="2030-05-01T10:00:00Z"
    Destination="https://idp.partner.example/saml/sso"
    AssertionConsumerServiceURL="https://sp.example/login/saml2/sso/partner">
    <saml:Issuer>https://sp.example/saml2/sp/partner</saml:Issuer>
    <samlp:NameIDPolicy
        Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
        SPNameQualifier="https://sp.example/saml2/sp/partner"
        AllowCreate="true"/>
</samlp:AuthnRequest>
~~~

This XML **only illustrates structure, is unsigned, and is not for real login**. A request using HTTP-Redirect Binding may be encoded via DEFLATE, Base64, and URL encoding; Redirect Binding signatures also have their own rules. When using Spring Security, let the resolver create and modify the OpenSAML object **before the serialization/signing step**, rather than manually editing the request XML string after signing.

### Three Distinct Constraint Levels

- **SP identity (`Issuer`):** which SP entity is requesting login.
- **`NameIDPolicy`:** which identifier format/context is desired.
- **Response conditions:** did the IdP actually return a valid, unexpired Assertion intended for this exact SP? The SP must check these **independently** of NameIDPolicy.

Do not confuse `NameIDPolicy` with `RequestedAuthnContext`: RequestedAuthnContext refers to **authentication context/method**, not identifier format.

## 4. The Three Attributes of NameIDPolicy

### 4.1. Format

`Format` is a URI describing the type of identifier the SP wants the IdP to use when representing the subject in the Assertion.

~~~xml
<samlp:NameIDPolicy
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"/>
~~~

Do not confuse `Format` with the `NameID` value itself: the `persistent` URI does not contain a username, while the actual NameID value might be a pseudonymous string like `p-6f91`.

When the IdP cannot fulfill it, it may return a Status code related to `InvalidNameIDPolicy` or another response depending on the product/profile. **There is no guarantee every IdP will automatically honor the request in every environment**. You must test interoperability with the exact IdP, tenant, and SAML application configuration.

### 4.2. SPNameQualifier

`SPNameQualifier` specifies the **SP or SP affiliation** context to which the desired identifier belongs. It is often especially important for persistent/pairwise identifiers in multi-party federations.

~~~xml
<samlp:NameIDPolicy
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
    SPNameQualifier="https://sp.example/saml2/sp/partner"/>
~~~

Keep in mind:

- Do not assume `SPNameQualifier` is the ACS endpoint. **ACS is the URL receiving the SAMLResponse**, whereas SPNameQualifier denotes identifier scope.
- It can be the SP entity ID or an affiliation ID **if and only if the IdP and SP agreed upon it**.
- Some IdPs do not support or do not require this field. For them, adding a qualifier can cause the request to be rejected.
- In the returned `<saml:NameID>`, `NameQualifier` generally relates to the identifier issuer (IdP) and `SPNameQualifier` relates to the SP/affiliation scope; attributes may be absent depending on format/profile. Do not guess missing values when security binding is required.
- Do not let the browser supply SPNameQualifier to “pick” another issuer/tenant/permission; derive it from a trusted registration.

### 4.3. AllowCreate

`AllowCreate` is a Boolean indicating whether the SP permits the IdP to create or associate an identifier for the relying party while fulfilling the request. **SAML 2.0 Approved Errata 05** clarified this meaning.

| Value | Meaning to Understand | Does Not Mean |
| --- | --- | --- |
| `true` | Allows the IdP to create/establish a new identifier association when needed, per policy and profile. | Create local user, auto JIT provision, or auto-grant permissions. |
| `false` | SP prefers the IdP to use only an already-established identifier/association, where applicable. | Guarantee the IdP never provisions an identifier in any scenario. |
| Attribute omitted | Per errata, defaults to `false`. | Every IdP follows the exact same implementation behavior. |

Per the errata, when **Format=transient**, **MUST NOT use `AllowCreate`**. Transient identifiers do not maintain persistent associations under this semantics. Example of an **invalid policy usage**:

~~~xml
<!-- INVALID: do not use AllowCreate with transient -->
<samlp:NameIDPolicy
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    Format="urn:oasis:names:tc:SAML:2.0:nameid-format:transient"
    AllowCreate="true"/>
~~~

**Beware of real-world implementations:** Microsoft Entra ID documents that `AllowCreate` is ignored in its SAML NameIDPolicy handling. This illustrates that **the protocol contract must be tested against the specific IdP**, not assumed merely because an attribute has a sensible name.

**AllowCreate and Just-in-Time provisioning are different.** Permitting the IdP to create an identifier grants no permission to create a local account in the SP database; user creation, tenant assignment, and privilege grants are separate workflows that the application must control.

## 5. Comparing NameID Formats

| Format | Exact Format URI | Characteristics | Long-Term Account Key? |
| --- | --- | --- | --- |
| **persistent** | `urn:oasis:names:tc:SAML:2.0:nameid-format:persistent` | Durable identifier scoped to an IdP–SP/affiliation relationship, usually pseudonymous. | **Possible**, when issuer/scope/lifecycle are guaranteed by the IdP. |
| **transient** | `urn:oasis:names:tc:SAML:2.0:nameid-format:transient` | Temporary identifier for a single SSO context, not guaranteed to repeat. | **No**, if relying solely on NameID. |
| **emailAddress** | `urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress` | Identifier formatted as an email address. | Not recommended by default; emails change or get recycled. |
| **unspecified** | `urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified` | Does not prescribe syntax/semantics in the URI. | Only when the contract explicitly defines durability/uniqueness. |
| **entity** | `urn:oasis:names:tc:SAML:2.0:nameid-format:entity` | Identifies a SAML entity, not a user by default. | Not a default choice for users. |
| **X509SubjectName** | `urn:oasis:names:tc:SAML:1.1:nameid-format:X509SubjectName` | Subject name in X.509 syntax. | Only in specialized profiles/applications. |

Note that **emailAddress** and **unspecified** still use the **SAML:1.1** namespace URI even when used in SAML 2.0. Do not “fix” them to `SAML:2.0` just because you are configuring SAML 2.0.

### 5.1. Persistent Does Not Mean Global

~~~text
IdP A + SP Orders:   subject persistent = "p-4af2"
IdP A + SP Payroll:  subject persistent = "p-729c"
IdP B + SP Orders:   subject persistent = "p-4af2"
~~~

The three strings above **do not by themselves prove any pair belongs to the same person**. One user at IdP A can have different pairwise identifiers across two SPs; two different IdPs can issue the same string for two completely different people.

The SP needs a **source + scope** key such as `IdP entity ID + NameID Format + qualifiers/SP scope + NameID value`, possibly paired with registration/tenant context per contract. Do not key solely on `NameID value` or email.

### 5.2. Transient and the Account Linking Problem

~~~text
Login #1: NameID transient = "T-089f"
Login #2: NameID transient = "T-5dc2"
~~~

Even when logging into the same IdP account, two NameIDs can differ. If the application needs to preserve shopping carts, orders, roles, or long-term history, use another **proven stable external identifier** or negotiate a persistent NameID. Do not silently merge two logins by email as a workaround.

### 5.3. EmailAddress Is Convenient but Not Immutable

A person changing company domain, email address, or department can receive a different email NameID than before. An old email address can also be reassigned to someone else. Thus `emailAddress` is useful for display/contact but is not a default choice for an identity key governing access to sensitive data.

If an IdP supports only emailAddress, you need a contract covering uniqueness, verification, reuse, value changes, notifications/deprovisioning, and migration procedures. Even when email is asserted by the IdP in a signed assertion, **the signature does not make an email an immutable ID**.

### 5.4. Unspecified Does Not Mean “No Identifier”

One IdP may emit `NameID Format=unspecified` containing a stable directory ID. Another IdP also uses unspecified, yet the value is a reusable username. The SP cannot infer semantics from this URI; there must be an **explicit commitment on content, scope, and lifecycle**.

### 5.5. Rules for Choosing a Format

1. Need a durable local user → prefer `persistent` or an immutable attribute with a full trust contract.
2. Need authentication only for a single session, without linking users across sessions via NameID → `transient` may fit.
3. Need email for display/notifications → receive via a separate Attribute; decouple from the external ID used for authorization.
4. IdP supports only `unspecified` → require written confirmation of its technical meaning and test across multiple logins.
5. Multi-tenant/multi-IdP → always record the issuer source and identifier scope to avoid conflating users.

## 6. Identity Agreement with the IdP

Do not treat NameIDPolicy as a “one-sided configuration.” The SP should align with the IdP admin team on testable points.

| Item | Question to Lock Down | Illustrative Example |
| --- | --- | --- |
| SP entity ID | Which URI does the IdP recognize the SP by? | `https://sp.example/saml2/sp/partner` |
| IdP entity ID | Trusted issuer authorized to issue assertions? | `https://idp.partner.example/saml` |
| SSO/ACS | Endpoints, bindings, signatures, redirects, context path? | `/login/saml2/sso/partner` |
| NameID Format | Standard URI or IdP policy? | `...:persistent` |
| NameID source | Object ID, pairwise pseudonym, email, username? | Stable directory subject scoped to the SP. |
| SPNameQualifier | Required or not? What value? | SP entity ID/affiliation per contract. |
| AllowCreate | Supported; what identifier effect does it have? | `true` if creation/association is allowed. |
| Uniqueness | Scope guaranteeing no collisions? | Issuer + SP scope. |
| Stability | Does changing email/name/department change NameID? | Unchanged on email rename. |
| Migration | How is mapping handled on tenant/IdP/directory changes? | Approved old→new mapping exists. |
| Deprovision | When an employee leaves or account is locked? | SP disables local link/permissions promptly. |
| Unsupported format | Does IdP return `InvalidNameIDPolicy` or fall back? | Documented and tested. |
| Privacy | Can NameID be logged/persisted? | Restricted access, retention, audit. |

### Illustrative Contract Document

~~~yaml
# Technical sign-off document; NOT a built-in Spring property
partner: partner-a
spEntityId: "https://sp.example/saml2/sp/partner-a"
idpEntityId: "https://idp.partner-a.example/saml"
nameId:
  expectedFormat: "urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
  spNameQualifier: "https://sp.example/saml2/sp/partner-a"
  allowCreate: true
  stableAcrossEmailRename: true
  uniquenessScope: "IdP-SP pair"
  migrationProcess: "admin-approved link update"
accountLink:
  automaticEmailMatch: false
  requireApprovedLocalMapping: true
~~~

This is an **implementation agreement**, not automatically processed by Spring Boot just by putting it in YAML. You must configure the IdP, SP code, and inspect actual responses accordingly.

### What to Do If the IdP Does Not Support Persistent?

- Determine which format/attribute the IdP **actually** emits and what stability guarantees exist.
- If the IdP uses `unspecified` with an immutable object ID value, document the semantics and scope explicitly.
- If it emits only `transient`, do not try to turn it into persistent by caching one result and reusing it out of context.
- If only emailAddress, assess email change/reuse risks; consider adding an approved account-linking workflow instead of automatic matching.
- If switching formats, **do not grant permissions to a “new user” unconditionally**; run an audited identity mapping migration.
- Every exception must have tenant, issuer, and permission boundaries and revocation capability.

## 7. Spring Security 6.3: Customizing the AuthnRequest

In **Spring Boot 3.3.x / Spring Security 6.3.x**, use `OpenSaml4AuthenticationRequestResolver` with `setAuthnRequestCustomizer(...)` to modify the OpenSAML `AuthnRequest` before issuance. This is better than manually parsing/editing `SAMLRequest` XML.

The sample below is a Servlet/SP Java 17+ application configuring `partner-a` via IdP metadata. Being **buildable** does not mean login works without a real IdP, certificates, entity ID, and ACS.

### 7.1. Project Structure

~~~text
saml-nameid-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/nameiddemo/
    │   ├── NameIdDemoApplication.java
    │   ├── SecurityConfig.java
    │   └── IdentityController.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'saml-nameid-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
    // Some OpenSAML artifacts may be downloaded from Shibboleth.
    maven {
        url 'https://build.shibboleth.net/maven/releases/'
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-saml2-service-provider'
}
~~~

`spring-security-saml2-service-provider` is the SAML2 SP dependency; `spring-security-oauth2-client` serves OAuth2/OIDC and **does not replace** SAML2. Use Java, Gradle, and dependency versions compatible with Boot 3.3.

### 7.2. Application.java

`src/main/java/com/example/nameiddemo/NameIdDemoApplication.java`:

~~~java
package com.example.nameiddemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class NameIdDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(NameIdDemoApplication.class, args);
    }
}
~~~

### 7.3. application.yml

`src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-a:
            assertingparty:
              metadata-uri: ${PARTNER_A_IDP_METADATA_URI}
~~~

The environment variable `PARTNER_A_IDP_METADATA_URI` is the IdP's real, trusted metadata URL. The IdP must know the SP entity ID, ACS URL, and SP signing certificate if required. Metadata URI is **not** the NameID Format; request customization lives in Java configuration.

### 7.4. SecurityConfig.java

`src/main/java/com/example/nameiddemo/SecurityConfig.java`:

~~~java
package com.example.nameiddemo;

import org.opensaml.saml.saml2.core.AuthnRequest;
import org.opensaml.saml.saml2.core.NameIDPolicy;
import org.opensaml.saml.saml2.core.NameIDType;
import org.opensaml.saml.saml2.core.impl.NameIDPolicyBuilder;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.web.DefaultRelyingPartyRegistrationResolver;
import org.springframework.security.saml2.provider.service.web.RelyingPartyRegistrationResolver;
import org.springframework.security.saml2.provider.service.web.authentication.OpenSaml4AuthenticationRequestResolver;
import org.springframework.security.saml2.provider.service.web.authentication.Saml2AuthenticationRequestResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    Saml2AuthenticationRequestResolver authenticationRequestResolver(
            RelyingPartyRegistrationRepository repository) {

        RelyingPartyRegistrationResolver registrationResolver =
            new DefaultRelyingPartyRegistrationResolver(repository);

        OpenSaml4AuthenticationRequestResolver resolver =
            new OpenSaml4AuthenticationRequestResolver(registrationResolver);

        resolver.setAuthnRequestCustomizer(context -> {
            if (!"partner-a".equals(
                    context.getRelyingPartyRegistration().getRegistrationId())) {
                return; // Do not apply partner A's policy to other IdPs.
            }

            AuthnRequest request = context.getAuthnRequest();
            NameIDPolicy policy = request.getNameIDPolicy();
            if (policy == null) {
                policy = new NameIDPolicyBuilder().buildObject();
                request.setNameIDPolicy(policy);
            }

            policy.setFormat(NameIDType.PERSISTENT);
            policy.setAllowCreate(Boolean.TRUE);

            // If SPNameQualifier has been agreed upon with the IdP:
            // policy.setSPNameQualifier(
            //     context.getRelyingPartyRegistration().getEntityId());
        });

        return resolver;
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            Saml2AuthenticationRequestResolver requestResolver)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .saml2Login(saml -> saml
                .authenticationRequestResolver(requestResolver)
            )
            .saml2Metadata(Customizer.withDefaults())
            .build();
    }
}
~~~

**Step-by-step explanation:**

1. `RelyingPartyRegistrationRepository` supplies registered SP–IdP pairs. `DefaultRelyingPartyRegistrationResolver` picks the registration matching the path/flow.
2. `OpenSaml4AuthenticationRequestResolver` builds the AuthnRequest using OpenSAML 4 and protocol details from Spring Security. Class and method names are APIs available in Spring Security 6.3.
3. `setAuthnRequestCustomizer(...)` is invoked when the resolver builds the AuthnRequest; `context` provides access to AuthnRequest and RelyingPartyRegistration.
4. Check `registrationId` before applying policy; do not force `partner-b` to use `partner-a`'s format.
5. If the request does not yet have a `NameIDPolicy`, use `NameIDPolicyBuilder().buildObject()`; if present, modify the existing object. Do not assume library defaults are identical across all versions.
6. `NameIDType.PERSISTENT` is an OpenSAML URI constant, preventing format namespace mistakes.
7. `AllowCreate=true` is a **contract-based choice**. If the IdP does not support it or is not allowed to create/link identifiers, change the policy rather than enabling it by default for every partner.
8. `SPNameQualifier` should be enabled only if the IdP confirms a specific value is required; **do not send it arbitrarily** on every request.
9. Wire the resolver via `.saml2Login(...authenticationRequestResolver(...))` so the filter actually uses the custom configuration.
10. `.saml2Metadata(...)` publishes SP metadata; this step does not force the IdP to return a specific NameID type.

**What the example does not do:** it does not sign XML manually, replace trusted metadata/certificates, or bypass signature, issuer, audience, recipient, time, InResponseTo, or replay checks. NameIDPolicy is never a reason to disable these validators.

### 7.5. Controller to Inspect the Principal

`src/main/java/com/example/nameiddemo/IdentityController.java`:

~~~java
package com.example.nameiddemo;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/")
    public String home() {
        return "Open /me to start SAML login";
    }

    @GetMapping("/me")
    public Map<String, Object> me(
            @AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("nameIdValue", principal.getName());
        result.put("registrationId",
                   principal.getRelyingPartyRegistrationId());
        return result;
    }
}
~~~

`Saml2AuthenticatedPrincipal.getName()` typically holds the **NameID value**, yet **does not expose full Format/NameQualifier/SPNameQualifier through this string alone**. If the application must enforce format in the response, you need a validator/converter operating on the **provider-verified Assertion**; do not trust only the principal's value or manually parse raw browser XML.

### 7.6. Running

With a compatible Gradle Wrapper and Java 17+:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell you can run:

~~~powershell
.\gradlew.bat bootRun
~~~

Test IdP integration procedure:

1. Set `PARTNER_A_IDP_METADATA_URI` to a real metadata URL.
2. Start the application. If metadata fails to load, the registration may fail to build; that is a configuration error to fix.
3. Open `/saml2/metadata/partner-a` and verify SP entity ID/ACS against the IdP configuration.
4. Open `/saml2/authenticate/partner-a` to inspect the AuthnRequest and confirm NameIDPolicy persistent/AllowCreate matches the contract.
5. IdP completes SSO and sends a signed response to the ACS. Spring Security verifies the SAML response.
6. Open `/me` after authentication. The `nameIdValue` field depends on the user and IdP; **there is no fixed JSON** valid across all environments.
7. Run two SSO logins with the same user and confirm identifier stability **if the IdP committed to persistent**.

This is an SP project; **it does not create a fake IdP or automatic trusted certificates**. Do not POST the unsigned illustrative XML from section 3 and treat it as proof of a successful login.

## 8. Other Customization Cases

### 8.1. Transient

If the contract requires transient, edit inside the customizer:

~~~java
policy.setFormat(NameIDType.TRANSIENT);
policy.setAllowCreate(null); // Do not send the AllowCreate attribute.
~~~

This is a **code snippet inside the customizer**, not a standalone class. Call `setAllowCreate(null)` to omit the attribute; inspect emitted XML with your exact OpenSAML version. Do not use a transient NameID as a stable account key.

### 8.2. EmailAddress

~~~java
policy.setFormat(NameIDType.EMAIL);
policy.setAllowCreate(null);
~~~

`NameIDType.EMAIL` maps to URI `urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress`. Do not automatically match local users by email without a safe process.

### 8.3. Unspecified

~~~java
policy.setFormat(NameIDType.UNSPECIFIED);
policy.setAllowCreate(null);
~~~

This merely tells the SP not to specify a NameID syntax via format. The actual NameID content must still follow the IdP–SP contract; do not assume `unspecified` is a meaningless identifier or always durable.

### 8.4. Omitting NameIDPolicy

When the IdP has a default contract configuration and prefers not to receive NameIDPolicy, inside the customizer you can use:

~~~java
request.setNameIDPolicy(null);
~~~

If omitting this element completely, **do not skip checking the received Assertion/NameID**. The SP must still validate the result against the contract even when the request specifies no format.

### 8.5. Per Registration

~~~java
// Code snippet inside the customizer; substitute your own project logic.
String registrationId =
    context.getRelyingPartyRegistration().getRegistrationId();

switch (registrationId) {
    case "partner-a" -> {
        policy.setFormat(NameIDType.PERSISTENT);
        policy.setAllowCreate(Boolean.TRUE);
    }
    case "partner-b" -> {
        policy.setFormat(NameIDType.TRANSIENT);
        policy.setAllowCreate(null);
    }
    default -> throw new IllegalStateException(
        "No NameID contract for " + registrationId);
}
~~~

In production, ensure an identifier/issuer outside the trusted list is never applied. **Do not pick a format from a browser-sent query parameter** to bypass integration policy.

## 9. Verifying NameID in the Received Assertion

### 9.1. NameID Returned by the IdP

Example Subject inside an authenticated Assertion:

~~~xml
<saml:Subject
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
    <saml:NameID
        Format="urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"
        NameQualifier="https://idp.partner.example/saml"
        SPNameQualifier="https://sp.example/saml2/sp/partner">
        p-6f91
    </saml:NameID>
    <saml:SubjectConfirmation
        Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
        <!-- SubjectConfirmationData constrains Recipient/InResponseTo/NotOnOrAfter -->
    </saml:SubjectConfirmation>
</saml:Subject>
~~~

This is only an explanatory XML fragment, without a signature or outer response. **The SP must verify the full Response/Assertion properly before trusting NameID**: signature with the trusted IdP certificate, issuer, audience, ACS recipient, request correlation, timestamps, replay, and conditions.

### 9.2. Validation Checklist After the Provider Accepts the Assertion

| Factor | What to Check | Why? |
| --- | --- | --- |
| IdP Issuer | Matches the trusted registration/tenant. | Two IdPs can issue the exact same NameID string. |
| Format | Matches agreed contract; handle absent/unspecified intentionally. | Request Format does not guarantee response Format. |
| NameID value | Valid, non-empty, not violating contract pattern. | Do not create accounts from undefined IDs. |
| NameQualifier | Matches expected source/namespace if required by profile. | Establishes subject scope. |
| SPNameQualifier | Matches SP/affiliation if required. | Avoids mixing identifiers across SPs/tenants. |
| Stability | Repeated logins for the same person keep the committed ID. | Prevents “new user” per SSO. |
| Local link | Maps to an approved/provisioned local account per policy. | Do not grant permissions merely because SAML login succeeded. |
| Authorization | Local account is active and authorized for the specific resource/tenant. | Identity is not permission. |

### 9.3. Integration Point with Spring Security

The sample in section 7 only **modifies the AuthnRequest** and inspects the NameID string after login. It **does not yet** enforce that the IdP returns the right `Format` via a dedicated validator. If business rules strictly require a NameID format, add a check on the **verified OpenSAML Assertion** via the appropriate response validation/conversion extension point for your Spring Security version.

**Do not do this:** reading `SAMLResponse` from the HTTP request in a controller, Base64-decoding it, and running XPath `//NameID[1]` to authorize. Outside the provider, that technique can read **a different XML element than the one whose signature was verified**, creating an XML Signature Wrapping risk.

Validation criteria can be expressed in pseudocode:

~~~text
verifiedAssertion = assertion verified by Spring Security/OpenSAML
subjectNameID = verifiedAssertion.Subject.NameID

REQUIRE verifiedAssertion.issuer == configuredIdP.issuer
REQUIRE subjectNameID != null
REQUIRE subjectNameID.format == configuredContract.expectedFormat
REQUIRE scope/qualifiers satisfy configuredContract
localUser = lookupTrustedIdentityLink(issuer, format, qualifiers, value)
REQUIRE localUser.status == ACTIVE

# Afterward, still enforce permission/tenant checks per business request.
~~~

This is a **design algorithm**, not Java API guaranteed to compile. Method names and hook locations for validated Assertions depend on the Spring Security/OpenSAML version; consult the documentation for your exact version.

### 9.4. Designing the Identity Link Key

Reference data structure:

~~~text
external_identity
-------------------------------------------------------------------
idp_entity_id     format       sp_scope     name_id_value   local_user
IdP-A             persistent   SP-Orders    p-6f91          user_104
IdP-B             persistent   SP-Orders    p-6f91          user_999

local_user
-------------------------------------------------------------------
id        tenant_id       status        permissions
user_104  partner_A       ACTIVE        ORDER_READ
user_999  partner_B       ACTIVE        ORDER_READ
~~~

These two users **must not be merged** because their issuers differ, even though the NameID value is identical. The actual unique key must reflect **issuer + format + qualifier/SP scope + value**, plus tenant/registration when required by contract. The SP may normalize absent qualifiers if proven safe, without assigning arbitrary scopes.

**Do not auto-match by email:** emails can change or be reused, and the same email appearing from two different IdPs does not prove it is the same user. On first provisioning, you can create a `PENDING` state awaiting approval; never grant admin authority by default.

### 9.5. Changing Formats in a Live System

Moving from `emailAddress` to `persistent` can make every account look different. A safe migration usually requires:

1. Freeze the current contract and export the user link list in a controlled manner; restrict PII access.
2. Receive an **old ID → new persistent ID** mapping from the IdP via a verified and approved source.
3. Test with a non-sensitive set of accounts; verify no person collisions or tenant mixing.
4. Support a schema allowing multiple effective external identities/links during a migration window if policy allows.
5. Update links transactionally, audit who approved, detect ambiguous mappings, and keep rollback capability.
6. Remove email-based fallback after cutover; prevent attackers from exploiting both formats to hijack another account.
7. Verify permission revocation, existing sessions, and old identifier retention per policy.

Never change NameIDPolicy unilaterally on the SP and automatically “link” new accounts to old accounts based solely on display name or email.

## 10. Common Errors and How to Handle Them

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| IdP returns `InvalidNameIDPolicy`. | Format/qualifier/AllowCreate not supported. | Check exact URI, contract, and IdP configuration. |
| SP requests persistent but receives transient. | IdP does not honor request or uses default. | Inspect outbound request and real assertion; fix IdP or contract. |
| Every login creates a new local account. | Using transient NameID as a long-term key. | Use persistent or another mapped immutable subject. |
| After email change, user loses permissions. | Keying identity by email. | Decouple email from immutable subject and migrate safely. |
| `AllowCreate=true`, yet SP has no new user. | Confusing IdP identifier creation with SP provisioning. | Design separate JIT/local account provisioning. |
| Sending `AllowCreate` with transient. | Violates SAML Errata 05 rule. | Omit the attribute in the customizer. |
| Adding SPNameQualifier breaks login. | IdP does not support it or value violates contract. | Agree on exact value or omit field when appropriate. |
| One NameID matched the wrong user at IdP B. | Stored only NameID string without issuer. | Include issuer/format/scope in the unique link. |
| Request lacks NameIDPolicy despite written bean. | Filter does not use new resolver, or flow is not SP-initiated. | Wire resolver into `saml2Login`, check endpoint/IdP-initiated. |
| Changing NameIDPolicy breaks AuthnRequest signature. | Manually edited XML/binding after signing. | Edit OpenSAML AuthnRequest in customizer before signing. |
| SP-initiated login works, but IdP-initiated has different format. | No SP AuthnRequest in unsolicited flow. | Configure IdP + validate Assertion; do not rely solely on customizer. |
| Login succeeds, yet API returns 403. | Missing permission/tenant or inactive local account. | Handle authorization separately; do not drop SAML signature checks. |
| `OpenSaml4AuthenticationRequestResolver` fails to compile in newer version. | Different Spring Security/OpenSAML major version. | Check Javadoc of resolved version and migration guide. |
| `unspecified` value changes after migration. | Contract did not define durability. | Clarify ID source and subject change procedure. |

### Do Not Confuse AuthnRequest Attributes

- `ForceAuthn` asks the IdP to re-authenticate rather than rely on an old session.
- `IsPassive` instructs the IdP to avoid user interaction per profile.
- `RequestedAuthnContext` describes the desired authentication context/method.
- `AssertionConsumerServiceURL` is the SP's ACS receiving the response.
- `NameIDPolicy` requests **identifier format/scope**.
- `RelayState` maintains state correlation across the binding, **not** user identity.

Changing `NameIDPolicy` alone does not cause the IdP to grant admin permissions, does not imply MFA, does not alter Assertion expiration, and does not handle SLO.

## 11. Across Spring Security Versions

**Spring Security 6.3 / Spring Boot 3.3**:

- Has `Saml2AuthenticationRequestResolver` and `OpenSaml4AuthenticationRequestResolver` to customize AuthnRequests.
- `setAuthnRequestCustomizer` uses an `AuthnRequestContext` object providing AuthnRequest/registration.
- OpenSAML 4 uses `org.opensaml.saml.saml2.core.NameIDPolicy` and `NameIDType` as in the example.
- API 6.3 is the baseline for the runnable example in section 7.

**Spring Security 6.4/6.5**:

- Has OpenSAML 4/5 compatibility changes depending on managed dependencies; look up the exact resolver class in the actual version.
- Do not just rename the class in source while skipping build and tests: OpenSAML major versions can affect APIs.

**Spring Security 7.x**:

- Current docs illustrate `OpenSaml5AuthenticationRequestResolver`; verify migration, Java baseline, classpath, and available methods.
- Do not treat the legacy `spring-security-saml` extension as an equivalent API for modern Servlet SAML2 Login.

Inspect resolved dependencies:

~~~bash
./gradlew dependencyInsight --dependency spring-security-saml2-service-provider --configuration runtimeClasspath
./gradlew dependencyInsight --dependency opensaml-saml-api --configuration runtimeClasspath
~~~

In PowerShell, use `.\gradlew.bat`. If the BOM has been overridden, the Boot version number alone **is insufficient** to confirm which resolver class runtime uses.

## 12. Test Suite and Exercises

| ID | Scenario | Expectation |
| --- | --- | --- |
| N01 | SP issues AuthnRequest for partner-a. | NameIDPolicy.Format=persistent, AllowCreate matches contract. |
| N02 | SP issues AuthnRequest for partner-b. | Does not apply partner-a policy to another registration. |
| N03 | IdP returns persistent NameID; issuer/qualifier/subject valid. | Accepted after valid SAML signature/conditions and local link. |
| N04 | IdP returns transient when contract mandates persistent. | Rejects mapping or authentication per policy; does not treat transient as persistent. |
| N05 | IdP supports only emailAddress. | Does not auto-create local admin accounts by email. |
| N06 | IdP does not support SP's requested format. | Explicit error/documented fallback; does not skip validation. |
| N07 | SP sends transient with AllowCreate. | Outbound test fails; fix by omitting AllowCreate. |
| N08 | SPNameQualifier mismatches agreed scope. | Rejected or flagged as config error; no wrong-tenant mapping. |
| N09 | Two IdPs emit the same NameID value. | Two distinct external identities. |
| N10 | Same user logs in across two persistent sessions. | Maps to same local account under scoped key. |
| N11 | Raw AuthnRequest altered after signing. | Signature/verification is no longer valid. |
| N12 | IdP-initiated login without AuthnRequest. | Still validates actual NameID; does not assume customizer ran. |
| N13 | Valid subject, yet local account disabled. | Business permissions denied. |
| N14 | Assertion has wrong issuer/audience/recipient/time/signature. | Authentication rejected before account linking. |
| N15 | IdP changes format after migration. | Verified old→new mapping workflow with audit and rollback. |

**Clear boundary:** the runnable example in section 7 proves **outbound NameIDPolicy** and basic principal after login. Tests N04, N08, N12, and N15 require inspecting the actual NameID and dedicated local identity workflows; they cannot be considered satisfied by the customizer alone.

### 12.1. Inspecting the Outbound Request

1. Use a controlled test IdP environment; open `/saml2/authenticate/partner-a`.
2. Capture `SAMLRequest` with a trusted SAML tracer in the test environment only.
3. For **HTTP-Redirect**, decode URL encoding, Base64, and DEFLATE per binding; for POST binding, Base64-decode per rules.
4. Parse XML and locate `samlp:AuthnRequest/samlp:NameIDPolicy`. Compare Format/AllowCreate/SPNameQualifier against the agreement.
5. Verify SP Issuer/ACS and request signature if required by the IdP; do not alter bytes after signing.
6. Have the IdP issue a real, validly signed Assertion and compare actual NameID/qualifiers against the contract.
7. Test multiple logins, different users, and different tenants to confirm stability and uniqueness.
8. Delete traces/raw SAMLResponses when finished; never upload identity data to public debugging tools.

### 12.2. Self-Assessment Questions

**Question 1.** Why does `NameIDPolicy` not prove identity?  
**Answer:** Because it is sent by the SP, not a verified Assertion from the IdP.

**Question 2.** Does the persistent format guarantee a user has the same NameID across every SP?  
**Answer:** No; scope can be per IdP–SP/affiliation.

**Question 3.** Does `AllowCreate=true` automatically create a user in the SP database?  
**Answer:** No; it relates to creating/associating an identifier at the IdP per policy.

**Question 4.** Should AllowCreate be sent with transient?  
**Answer:** No; Errata 05 requires not using it.

**Question 5.** Why should external identity not be keyed on emailAddress?  
**Answer:** Emails can change or be recycled; an Assertion signature does not make an email immutable.

**Question 6.** Is SPNameQualifier the ACS URL?  
**Answer:** No; it specifies the SP/affiliation scope for the identifier.

**Question 7.** When the IdP returns unspecified, what must you do?  
**Answer:** Explicitly agree on what the NameID value is, its stability, and scope; do not guess.

**Question 8.** Why is checking only `principal.getName()` insufficient?  
**Answer:** It is usually just the NameID value without full Format/qualifiers; a validated Assertion is needed when policy requires it.

**Question 9.** If one IdP emits the same NameID as another IdP, can the users be merged?  
**Answer:** No; the issuer is a trust-boundary component of the link key.

**Question 10.** Does IdP-initiated SSO pass through the AuthnRequest customizer?  
**Answer:** There is no SP-generated request in that flow, so format must be controlled at the IdP and in response validation.

## 13. Implementation Checklist

- [ ] Locked down the standard format URI with the IdP; distinguished `persistent`, `transient`, `emailAddress`, and `unspecified`.
- [ ] If using persistent, confirmed scope, uniqueness, lifecycle, and ID change procedures.
- [ ] `SPNameQualifier` appears only when specifically agreed upon; never copy ACS into this field.
- [ ] `AllowCreate` matches the contract; **never appears when transient**.
- [ ] Configured Spring Security with the exact version-appropriate resolver; wired customizer into the filter.
- [ ] Policy is scoped by `registrationId`; never accept format from untrusted requests.
- [ ] Trusted IdP metadata/certificates present; never skip signature/issuer/audience/recipient/time/correlation/replay checks.
- [ ] Verified both outbound AuthnRequest and inbound NameID on a valid Assertion.
- [ ] Identity link stores issuer + scope + format + value per contract; never match users solely by email.
- [ ] Have workflows for new users, deprovisioning, account locking, and identifier migration.
- [ ] Test IdP-initiated SSO separately if permitted.
- [ ] Sensitive SAML contents are not logged publicly or sent to third-party debug services.
- [ ] Executed tests N01–N15 or an equivalent suite.
- [ ] Enforced business permissions at the SP after SAML authentication succeeds.

**Remember:** `NameIDPolicy` is a format request from the SP. `NameID` inside a verified Assertion is the IdP's identity claim. Safe account linking requires a **durable identity contract, scoped accurately to issuer/SP, tested, and backed by an identifier migration process**. AuthnRequest customization never replaces response verification or internal authorization.

### Official Documentation

- [OASIS — SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): `NameIDPolicy`, `NameID`, NameID formats, and AuthnRequest/Assertion conditions.
- [OASIS — Approved SAML 2.0 Errata 05](https://docs.oasis-open.org/security/saml/v2.0/errata05/os/saml-v2.0-errata05-os.html): `AllowCreate` and the rule against using it with transient.
- [Spring Security — Producing SAML2 AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html): resolver, customizer, request binding, and signing.
- [Spring Security 6.3.5 — OpenSaml4AuthenticationRequestResolver Javadoc](https://docs.spring.io/spring-security/site/docs/6.3.5/api/org/springframework/security/saml2/provider/service/web/authentication/OpenSaml4AuthenticationRequestResolver.html): API matching the Boot 3.3 example.
- [Spring Security — SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): filters, registration, metadata, and ACS.
- [Spring Security — Authenticating SAML2 Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): principal, assertion, and response validation.
- [OpenSAML 4 — NameIDType](https://javadoc.io/static/org.opensaml/opensaml-saml-api/4.0.1/org/opensaml/saml/saml2/core/NameIDType.html): URI constants `PERSISTENT`, `TRANSIENT`, `EMAIL`, `UNSPECIFIED`.
- [Microsoft Entra — SAML SSO protocol](https://learn.microsoft.com/azure/active-directory/develop/single-sign-on-saml-protocol): real-world example of NameIDPolicy and how an IdP implementation may ignore AllowCreate.
