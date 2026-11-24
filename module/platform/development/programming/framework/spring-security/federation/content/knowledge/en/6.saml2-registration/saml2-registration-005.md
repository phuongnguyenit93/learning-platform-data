# Distinguishing registrationId, entityId, and Provider Display Name in SAML 2.0 Registration

## 1. The Problem to Solve

A Spring Boot application using **Spring Security SAML 2.0 Login** can let users log in through one or more Identity Providers (IdPs). When setting up each connection, development teams often encounter three values that look similar:

- **`registrationId`**: a **local Spring Security configuration key**, used to look up a `RelyingPartyRegistration`.
- **`entityId`**: a **SAML protocol identifier** of a Service Provider (SP) or IdP; participates in the trust contract and message validation.
- **Provider display name** (*display name*): a human-readable string in the UI, e.g., **"Sign in with corporate account"**.

Even though all three can look like a "provider name", they answer **three different questions**:

| Question | Answering Value |
| --- | --- |
| "Which connection configuration should Spring Security select?" | `registrationId` |
| "Which SP requested the message, which IdP issued it, and which SP is the assertion for?" | SP/IdP `entityId` |
| "On the login page, what text does this button show so users recognize it?" | Display name in the UI |

**Do not substitute one value arbitrarily for another.** In particular, changing a login button label is not a reason to change the SAML Entity ID; using the right Entity ID while selecting the wrong registration/certificate can still cause errors or violate trust boundaries.

This lesson belongs to the **SAML2 Registration** track. The focus is on naming, configuring, and operating the relationship among these three values, not replacing the entire SAML verification pipeline with a string comparison.

## 2. What Is RelyingPartyRegistration?

In Spring Security SAML 2.0:

- **Relying Party (RP)** is synonymous with **Service Provider (SP)**: the Spring Boot application serving users.
- **Asserting Party (AP)** is synonymous with **Identity Provider (IdP)**: the system authenticating users and issuing SAML Responses/Assertions.
- **`RelyingPartyRegistration`** describes **one RP–AP relationship**: both sides' identifiers, endpoints, certificates, message send/receive mechanics, and security options.
- **`RelyingPartyRegistrationRepository`** is where Spring Security looks up a registration when creating an AuthnRequest, processing a Response, or publishing metadata.

An organization can create multiple registrations for the same application:

```text
Spring Boot Application (Service Provider)
    |
    +-- registrationId = employee
    |     +-- SP entityId  = urn:example:portal:prod:sp
    |     +-- IdP entityId = https://sso.company.example.test/saml/idp
    |     +-- UI label     = Employee account
    |
    +-- registrationId = partner
          +-- SP entityId  = urn:example:portal:prod:sp
          +-- IdP entityId = https://login.partner.example.test/issuer
          +-- UI label     = Partner account
```

Two registrations can share the same **SP Entity ID** if both relationships are configured accordingly and the IdPs accept that SP identifier. They remain **two distinct configurations** because their IdPs, endpoints/certificates, or policies differ.

Other deployments assign a **separate SP Entity ID per registration or environment**. This depends on the contract registered with the IdP; there is no mandatory rule that all registrations must share one entity ID or that all registrations must have different entity IDs.

## 3. registrationId: Spring Security's Internal Lookup Key

`registrationId` is **an application-chosen string** to distinguish `RelyingPartyRegistration` entries in the repository. Examples:

```text
employee
partner
corp-adfs
customer-okta
```

Characteristics:

1. **Unique within the repository**: each registration needs its own lookup key in the active configuration set.
2. **Application-owned**: the name can be `employee` even if the IdP has a completely different commercial product name.
3. **Participates in default routing**: typically `/saml2/authenticate/{registrationId}`, `/login/saml2/sso/{registrationId}`, and `/saml2/metadata/{registrationId}`.
4. **Not a secret**: the value may appear in public paths; never use it as a password, token, or proof of authentication.
5. **Not implicitly an Entity ID**: `employee` is only a Spring key; it does not automatically become `<saml:Issuer>` or `<saml:Audience>`.

In Spring Security, the URL:

```text
GET /saml2/authenticate/employee
```

typically instructs the application to look up the registration with `registrationId=employee` and initiate an AuthnRequest to the IdP configured in that registration.

On the receiving side, the SAML Response can be POSTed to:

```text
POST /login/saml2/sso/employee
```

However, **Spring Security does not rely solely on the registrationId path in all cases**. When processing a Response, the framework may look up the registration via a stored request/correlated state or the Response issuer, depending on version and configuration. The registration identifier remains the key managing the RP–AP pair. Do not write a custom Response handler that trusts only the URL suffix.

### 3.1. Why Should registrationId Be Stable?

Suppose a login button links to `/saml2/authenticate/employee`. If you rename the key to `staff`, the old link can no longer locate the registration (unless the application adds an alias/redirect). Moreover, an ACS URL using `{registrationId}` will change:

```text
Before: https://portal.example.test/login/saml2/sso/employee
After:  https://portal.example.test/login/saml2/sso/staff
```

If the IdP still stores the old ACS, it may reject the AuthnRequest or send the Response to an unsuitable location. Metadata configs, allowlists, login links, and in-flight SAML flows must also be reviewed before renaming.

**Important note:** changing `registrationId` **does not necessarily change the SP Entity ID** if the SP Entity ID is fixed. Conversely, if the SP Entity ID uses the `{registrationId}` placeholder, changing the key can **change the expanded Entity ID as well**. Always inspect the **actual value in metadata** rather than inferring from YAML keys.

### 3.2. Reasonable Naming Conventions

Choose short, URL-friendly, stable, technically meaningful keys:

- `employee` for the employee IdP.
- `partner-acme` for an independently managed partner IdP.
- `corp-adfs-prod` when system/environment specificity is needed, though avoid embedding volatile details unnecessarily.

Avoid using long marketing names with accents, emails, full URLs, or display labels containing spaces as registration IDs. This is a **recommended operational convention**, not a SAML rule forcing all registration IDs into that exact format.

## 4. entityId: The SAML Identity of Both Sides

`entityId` is the **logical identifier of a SAML entity**. Each side's metadata publishes a value via `<md:EntityDescriptor entityID="...">`.

In one registration there are **two Entity IDs**:

1. **SP Entity ID / Relying Party Entity ID**: identifies the **Spring application** in the federation.
2. **IdP Entity ID / Asserting Party Entity ID**: identifies the **authentication server**.

Example:

```text
registrationId      = employee
SP entityId         = urn:example:portal:prod:sp
IdP entityId        = https://sso.company.example.test/saml/idp
Display name        = Sign in with employee account
```

The SP Entity ID can be a URI using `urn:` or `https:`. **It is not automatically a URL the browser needs to open**. The IdP Entity ID can also resemble a URL, without necessarily matching the IdP login address.

### 4.1. Entity ID Appears in SAML Messages

In **SP-initiated login**, the `<saml:Issuer>` element inside the `AuthnRequest` generated by the SP typically holds the **SP Entity ID**:

```xml
<samlp:AuthnRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_req_001"
    Version="2.0"
    IssueInstant="2026-01-01T10:00:00Z"
    Destination="https://sso.company.example.test/saml/sso">
    <saml:Issuer>urn:example:portal:prod:sp</saml:Issuer>
</samlp:AuthnRequest>
```

In the SAML Response/Assertion from the IdP, `Issuer` denotes the **IdP Entity ID** and `AudienceRestriction/Audience` typically denotes the **SP Entity ID**:

```xml
<saml:Issuer
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
    https://sso.company.example.test/saml/idp
</saml:Issuer>

<saml:AudienceRestriction
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
    <saml:Audience>urn:example:portal:prod:sp</saml:Audience>
</saml:AudienceRestriction>
```

These XML snippets **only illustrate the placement of the two identifiers**; they are not complete AuthnRequest/Response/Assertion documents, lack signatures, and **cannot be used as login proof**.

The Entity ID pair is part of the **SAML trust contract**, so:

- The IdP compares `AuthnRequest/Issuer` against the SP registered at the IdP.
- The SP compares the IdP issuer in the Response/Assertion against the trusted issuer.
- The SP verifies that the assertion audience matches its own **SP Entity ID**.
- The SP must also verify signatures with the right certificate, `Destination`, `Recipient`, time conditions, `InResponseTo`, SubjectConfirmation, and anti-replay per flow/profile.

**Never trust an assertion merely because the Entity ID strings match**: an attacker can craft XML with matching strings. Signatures and trust configuration are what verify the issuing source.

### 4.2. Entity ID Differs from Metadata URLs and Endpoints

| Concept | Example | Function |
| --- | --- | --- |
| SP Entity ID | `urn:example:portal:prod:sp` | Identifies the app in SAML; used in AuthnRequest Issuer/Audience |
| IdP Entity ID | `https://sso.company.example.test/saml/idp` | Identifies the assertion issuer |
| SP metadata URL | `https://portal.example.test/saml2/metadata/employee` | Where SP metadata is fetched |
| IdP metadata URL | `https://sso.company.example.test/saml/metadata` | Where IdP metadata is fetched |
| Assertion Consumer Service (ACS) | `https://portal.example.test/login/saml2/sso/employee` | SP endpoint receiving SAML Response |
| Single Sign-On (SSO) URL | `https://sso.company.example.test/saml/sso` | IdP endpoint receiving AuthnRequest |
| `registrationId` | `employee` | Registration lookup key inside Spring Security |
| UI display name | "Employee account" | Text displayed on login buttons or lists |
| `NameID` | `user-418` (hypothetical) | **User** identifier in the assertion, not the provider |

Metadata URL, ACS, and SSO URL can look similar to IdP/SP Entity IDs. Even on the same hostname, **they must not be swapped** when the IdP/SP have registered distinct values.

### 4.3. Two Entity IDs and Uniqueness Scope

- Different IdPs should be identified by **each party's exact Entity ID and trust credentials**.
- A commercial vendor can operate multiple tenants/realms with **different IdP Entity IDs**.
- Two local registrations can point to the same IdP Entity ID if there is a configuration reason, but choosing the right RP–AP still depends on each registration's constraints.
- An SP can keep the same Entity ID across multiple IdP registrations, or assign distinct Entity IDs per tenant/environment. Agree on this with the IdP in advance.

Do not guess an IdP Entity ID from the software vendor ("Okta", "ADFS"), hostname, or company name. **Take the value from verified IdP metadata or an approved configuration contract**.

## 5. Provider Display Name: UI Data

The display name is a **user-friendly label**. Examples:

```text
Employee account
Sign in via partner SSO
Vendor account
```

This name helps users select the right login system, especially when the application supports multiple IdPs. It **is not** a required component of a SAML AuthnRequest, Response, or AudienceRestriction.

A custom-designed login page might hold data like:

| registrationId | displayName | loginUrl |
| --- | --- | --- |
| `employee` | Sign in with employee account | `/saml2/authenticate/employee` |
| `partner` | Sign in with partner account | `/saml2/authenticate/partner` |

In this table, the application manages the `registrationId -> displayName` mapping. Distinguish **UI-driven display labels** from information that may exist in IdP-side metadata such as `OrganizationDisplayName` or `mdui:DisplayName` extensions. SAML metadata does not guarantee every IdP publishes consistent friendly names, nor does it guarantee Spring Security automatically maps that metadata into a standard display name property in the registration configuration.

**Recommendation:** if you need control over wording, localization, ordering, logos, and the IdP selection experience, build **the application's own IdP selection page** with a governed mapping. Spring Security's auto-generated login page and how it renders providers can change across versions/configs; do not treat default display text as a protocol contract.

### 5.1. What Does Changing the Display Name Affect?

If a button previously read "Corporate SSO" and now changes to "Employee account", with **the same registrationId and both Entity IDs**, then:

- Users see the new label.
- Login URLs, SP/IdP metadata, and trust relationships remain unchanged.
- SAML signatures and issuer/audience are unaffected.
- No IdP update is needed just because the button text changed (barring separate brand governance workflows).

Conversely, if a user clicks "Employee account" while the link points to `/saml2/authenticate/partner`, the system may start the flow at the **wrong IdP**. That is a UI-to-registration mapping bug, even though the displayName string itself holds no technical authority.

### 5.2. Never Use Display Name for Authorization

A label "Admin Login" does not grant admin privileges. Permissions derive from the verified identity, account mapping, membership, application policy, and contract-trusted SAML attributes. Never write security logic such as:

```text
if (providerDisplayName == "Admin SSO") allowAll()
```

This is an **unsafe pattern**: display name is purely UI text that can change by language or branding. Moreover, display name is not a user identifier; users are identified by verified NameID/attributes and a dedicated identity-linking policy.

## 6. Comparison Table of the Three Key Concepts

| Criterion | registrationId | entityId | Provider Display Name |
| --- | --- | --- | --- |
| Which layer? | Spring Security configuration | SAML/federation protocol | Application UI/UX |
| Chosen by whom? | App development/ops team | SP and IdP per contract, metadata | Product/UI/ops team |
| Scope | Application's registration repository | Each entity's SAML identifier space | UI/localization |
| Example | `employee` | `urn:example:portal:prod:sp`, `https://sso.company.example.test/saml/idp` | "Employee account" |
| Appears in URLs? | Usually yes, in default endpoints | Can be a URI but not necessarily a live endpoint | Not required |
| Appears in SAML metadata? | Not `entityID`; can be part of metadata URL | Yes: `EntityDescriptor/@entityID` | UI name extensions may exist, not an auth field |
| Appears in SAML Issuer/Audience? | Not the default trust comparison value | Yes, in the SP/IdP role | No |
| Changing value can break SSO? | Yes, when URLs/templates/correlation depend on it | Yes, alters the trust contract | Usually no, if only UI label changes |
| Used to look up internal users? | No | Not used alone as a user ID | No |
| Used to decide business permissions? | No | No | No |

**Note on dependency:** although conceptually distinct, some configs allow the SP `entityId` to include the `{registrationId}` placeholder. In that case, changing `registrationId` can **indirectly change the Entity ID**. That dependency arises from **the developer's chosen template**, not because the two fields are inherently identical.

## 7. Example: Configuring Two IdPs with Spring Boot

This example targets **Spring Boot 3.x / Spring Security 6.x**. Appropriate dependencies for Spring Web/Security and SAML 2.0 Service Provider are required; real IdPs must be registered and publish valid metadata/certificates.

File `src/main/resources/application.yml`:

```yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          employee:
            entity-id: "urn:example:portal:prod:sp"
            acs:
              location: "{baseUrl}/login/saml2/sso/{registrationId}"
            assertingparty:
              metadata-uri: "https://sso.company.example.test/saml/metadata"
          partner:
            entity-id: "urn:example:portal:prod:sp"
            acs:
              location: "{baseUrl}/login/saml2/sso/{registrationId}"
            assertingparty:
              metadata-uri: "https://login.partner.example.test/saml/metadata"

# Application-specific configuration, not a standard SAML property.
app:
  login-providers:
    employee: "Sign in with employee account"
    partner: "Sign in with partner account"
```

Reading the config:

1. `employee` and `partner` are **registrationIds**.
2. `entity-id` directly under each registration is the **SP Entity ID**. The example uses the same value for both assuming both IdPs registered that SP.
3. `assertingparty.metadata-uri` is the **URL to load IdP metadata**, **not the IdP Entity ID**. The IdP Entity ID resides inside each provider's XML metadata, e.g., `<EntityDescriptor entityID="...">`.
4. `acs.location` contains the `{registrationId}` placeholder; each registration's ACS URL will differ, even with a shared SP Entity ID.
5. `app.login-providers` is purely **application-defined UI label data**; it will not automatically render login buttons unless you write code to read and use it.

The sample only shows the relationship among the three values; operating in production requires confirming signing/verification certificates, trusted IdP metadata, binding/ACS, HTTPS, logout if used, key rotation, and response issuance/acceptance policies. Different Spring Boot versions may change property names or capabilities; cross-check the configuration metadata of the exact version.

### 7.1. Where Does IdP entityId Come From?

Suppose `https://sso.company.example.test/saml/metadata` returns trusted metadata:

```xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://sso.company.example.test/saml/idp">
    <md:IDPSSODescriptor
        protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
        <md:SingleSignOnService
            Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
            Location="https://sso.company.example.test/saml/sso"/>
    </md:IDPSSODescriptor>
</md:EntityDescriptor>
```

From this snippet:

- Metadata download URL: `.../saml/metadata`.
- **IdP Entity ID**: `.../saml/idp`.
- IdP SSO endpoint: `.../saml/sso`.

The three addresses have distinct meanings. The XML is trimmed for explanation and omits verification certificates. In practice, the application must verify the IdP issuer and certificate from a trusted, managed metadata source; never trust arbitrary XML merely because the URL shares a domain name.

### 7.2. What Does SP Metadata Contain?

When Spring Security exports SP metadata for the `employee` registration, the conceptually important fields are:

```xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="urn:example:portal:prod:sp">
    <md:SPSSODescriptor
        protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
        <md:AssertionConsumerService
            index="0"
            Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
            Location="https://portal.example.test/login/saml2/sso/employee"/>
    </md:SPSSODescriptor>
</md:EntityDescriptor>
```

This is a **shortened structural illustration**; real metadata can include certificates/signatures and multiple endpoints. SP `entityID` is not `employee`, and `employee` appears only as part of the ACS URL per the template configuration.

When a new IdP registration is needed, use **the SP metadata exported by the application in the target environment** or provide the exact SP Entity ID, ACS, and certificates/bindings required by the IdP. Avoid typing an "Entity ID that looks like a login URL" by hand and letting both sides drift out of sync.

## 8. Spring Security Java Configuration for SAML Login

Example filter chain configuration for a Spring Boot Servlet application with Spring Security SAML 2.0 Service Provider and Boot-configured registrations.

File `src/main/java/com/example/portal/SecurityConfig.java`:

```java
package com.example.portal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/assets/**").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults());

        return http.build();
    }
}
```

Explanation:

- `saml2Login()` configures the SP SAML 2.0 login flow.
- `saml2Metadata()` enables publishing SP metadata for integration/testing; default URLs depend on version/configuration, though common patterns are `/saml2/metadata` and `/saml2/metadata/{registrationId}`.
- `RelyingPartyRegistrationRepository` is auto-configured by Spring Boot from YAML if sufficient metadata is present. Spring Security uses the repository to look up registrations and handle trust.
- This program **has no fixed "Employee account" button**. If you want exact display labels and custom layout, build a dedicated login UI.
- This is a class inside a **Spring Boot project with dependencies**, not a Java file compiled with plain JDK. Running it also requires a project build, valid IdP metadata, and trust configuration.

### 8.1. When Creating RelyingPartyRegistration in Java

In modern Spring Security, you can use `RelyingPartyRegistrations.fromMetadataLocation(...).registrationId(...).entityId(...).build()` to create an RP/AP pair. An illustrative snippet (inside a configuration class with a repository):

```java
RelyingPartyRegistration registration = RelyingPartyRegistrations
    .fromMetadataLocation(
        "https://sso.company.example.test/saml/metadata"
    )
    .registrationId("employee")
    .entityId("urn:example:portal:prod:sp")
    .build();
```

This is an **API snippet**, not a standalone class. Metadata access and builder APIs can vary across versions. Real deployments must consider SP credentials, signing policies/verification requirements, and trusted metadata sources.

**Important:** builder `.registrationId("employee")` does not determine `assertingParty.entityId`: IdP information comes from metadata or is configured separately. Using the name `employee` does not mean the IdP has issuer `employee`.

### 8.2. How to Read Back Configured Registrations

The getters below let you **inspect logical values** from a registration without replacing metadata/runtime checks:

```java
RelyingPartyRegistration r =
    repository.findByRegistrationId("employee");

String localRegistrationId = r.getRegistrationId();
String spEntityId = r.getEntityId();
String idpEntityId = r.getAssertingPartyMetadata().getEntityId();
String acsTemplate = r.getAssertionConsumerServiceLocation();
```

This is a snippet inside a method that has a `repository` variable, not a standalone program. Depending on context, some fields may still hold unexpanded placeholders or URLs dependent on the request's public base URL. Compare with metadata **actually exported by Spring at the real deployed address**.

Never log these fields in production alongside private keys, secrets, or unmasked SAMLResponses; identifier configuration may be logged at controlled levels for debugging.

## 9. Designing a Login Provider Selection Page

Suppose the application displays two buttons:

```text
+--------------------------------------+
|             Portal Login             |
|                                      |
|  [ Sign in with employee account ]   |
|  [ Sign in with partner account  ]   |
+--------------------------------------+
```

Each button must navigate to the **right registrationId**:

```html
<a href="/saml2/authenticate/employee">
  Sign in with employee account
</a>
<a href="/saml2/authenticate/partner">
  Sign in with partner account
</a>
```

This is illustrative HTML: ensure the login page is accessible while unauthenticated and links match `RelyingPartyRegistrationRepository`. With Spring MVC/Thymeleaf, you can build the list from application-owned configuration and render these links. By default `/saml2/authenticate/{registrationId}` is the AuthnRequest initiation endpoint, not the IdP Entity ID.

Never construct URLs from **uncontrolled display names**. UI labels must map to an allowed `registrationId`; users can choose from the list, but **must never be allowed to declare new IdP metadata, issuers, or certificates**.

### 9.1. Suggested UI Data Model

An application record can store:

```text
LoginProviderOption:
  registrationId = employee
  displayName    = Sign in with employee account
  enabled        = true
  sortOrder      = 10
```

`displayName` can be multilingual (`vi`, `en`), and include a logo and short description. This is product data and does not overwrite `EntityDescriptor/@entityID`.

If using IdP metadata to suggest UI names, verify metadata authenticity, brand consistency, and encoding/HTML escaping. Dynamic labels from external sources must never inject arbitrary HTML/scripts.

## 10. Plain Java 17 Example: Three Independent Fields

The following example compiles/runs with JDK 17 or later, **without Spring Security**. It models a registry showing that display name, registration key, and the two Entity IDs serve different purposes. The final check function only compares strings to teach the concept and **does not verify SAML signatures**.

File `SamlRegistrationNamesDemo.java`:

```java
import java.util.LinkedHashMap;
import java.util.Map;

public class SamlRegistrationNamesDemo {
    record Provider(
        String registrationId,
        String spEntityId,
        String idpEntityId,
        String displayName
    ) {
        String loginPath() {
            return "/saml2/authenticate/" + registrationId;
        }
    }

    static boolean matchesDeclaredIds(
            Provider provider,
            String responseIssuer,
            String audience) {
        return provider.idpEntityId().equals(responseIssuer)
            && provider.spEntityId().equals(audience);
    }

    public static void main(String[] args) {
        Map<String, Provider> registry = new LinkedHashMap<>();
        Provider employee = new Provider(
            "employee",
            "urn:example:portal:prod:sp",
            "https://sso.company.example.test/saml/idp",
            "Employee account"
        );
        Provider partner = new Provider(
            "partner",
            "urn:example:portal:prod:sp",
            "https://login.partner.example.test/issuer",
            "Partner account"
        );
        registry.put(employee.registrationId(), employee);
        registry.put(partner.registrationId(), partner);

        System.out.println("lookup=" + registry.get("employee").displayName());
        System.out.println("loginPath=" + employee.loginPath());
        System.out.println("spEntityId=" + employee.spEntityId());
        System.out.println("idpEntityId=" + employee.idpEntityId());

        Provider relabeled = new Provider(
            employee.registrationId(),
            employee.spEntityId(),
            employee.idpEntityId(),
            "Company SSO login"
        );
        System.out.println("sameRegistration="
            + employee.registrationId().equals(relabeled.registrationId()));
        System.out.println("sameSp="
            + employee.spEntityId().equals(relabeled.spEntityId()));
        System.out.println("labelChanged="
            + !employee.displayName().equals(relabeled.displayName()));

        System.out.println("issuerAndAudienceOk=" + matchesDeclaredIds(
            employee,
            "https://sso.company.example.test/saml/idp",
            "urn:example:portal:prod:sp"
        ));
        System.out.println("wrongIdpIssuer=" + matchesDeclaredIds(
            employee,
            partner.idpEntityId(),
            employee.spEntityId()
        ));
        System.out.println("wrongSpAudience=" + matchesDeclaredIds(
            employee,
            employee.idpEntityId(),
            "urn:example:other:sp"
        ));
    }
}
```

Run:

```bash
javac SamlRegistrationNamesDemo.java
java SamlRegistrationNamesDemo
```

Exact stdout:

```text
lookup=Employee account
loginPath=/saml2/authenticate/employee
spEntityId=urn:example:portal:prod:sp
idpEntityId=https://sso.company.example.test/saml/idp
sameRegistration=true
sameSp=true
labelChanged=true
issuerAndAudienceOk=true
wrongIdpIssuer=false
wrongSpAudience=false
```

Meaning:

1. `registry.get("employee")` uses **registrationId** to fetch the configuration record.
2. `loginPath()` builds the **SAML initiation path** using registrationId.
3. `spEntityId` and `idpEntityId` remain the URI identifiers of the two SAML entities.
4. Changing `displayName` changes neither registrationId nor SP Entity ID.
5. The **partner IdP**'s issuer is not accepted as the employee IdP's issuer.
6. Another SP's audience is not treated as the current application's audience.

`matchesDeclaredIds` **is not sufficient for a real SAML authentication system**. It does not check signatures, certificates, bindings, Recipient/Destination, SubjectConfirmation, time validity, `InResponseTo`, or anti-replay. Spring Security/OpenSAML must perform those checks after selecting the right registration.

## 11. What Must Be Updated When Changing Each Value?

| Change | Primary Impact | Where to Check/Update |
| --- | --- | --- |
| Change displayName | Button text, translations, logo | UI config/templates, copy, UI tests |
| Change registrationId | Repository lookup, login URLs, placeholder ACS/metadata URLs | Config sources, UI links, endpoints/routes, IdP ACS if URL changed, active SAML states |
| Change SP Entity ID | `AuthnRequest/Issuer`, SAML audience, SP metadata and IdP contract | SP config, IdP SP registration, metadata, issuer/audience tests |
| Change IdP Entity ID | Trusted issuer value, IdP metadata/trust | Asserting-party metadata, issuer/certificate checks, user linking keys if using IdP issuer |
| Change IdP SSO URL | Destination for AuthnRequest | IdP metadata/endpoints, bindings, network |
| Change SP ACS URL | Destination for SAML Response | SP routes/metadata, IdP ACS allowlist, Destination/Recipient |
| Rotate certificate | Keys used for signing/verification or encryption/decryption | SP/IdP trust credentials, overlapping keys, rotation policy; Entity ID usually stays unchanged |
| Switch commercial vendor | May affect IdP Entity ID, certificate, SSO URL, and subject | Full migration review, not just changing displayName |

### 11.1. Example: Label-Only Change

Before:

```text
registrationId = employee
spEntityId     = urn:example:portal:prod:sp
idpEntityId    = https://sso.company.example.test/saml/idp
displayName    = Corporate SSO
```

After:

```text
registrationId = employee
spEntityId     = urn:example:portal:prod:sp
idpEntityId    = https://sso.company.example.test/saml/idp
displayName    = Sign in with employee account
```

This is a **UI change**. It is not a new IdP/SP configuration; no certificate rotation or Entity ID re-registration is needed if all protocol parameters stay intact.

### 11.2. Example: Changing registrationId with a Fixed Entity ID

Before:

```text
registrationId = employee
spEntityId     = urn:example:portal:prod:sp
acs            = .../login/saml2/sso/employee
```

After:

```text
registrationId = staff
spEntityId     = urn:example:portal:prod:sp
acs            = .../login/saml2/sso/staff
```

SP Entity ID stays unchanged, yet ACS can change because the template contains registrationId. The IdP must accept the new ACS and the application must update login links. Never change only the YAML key while ignoring metadata.

### 11.3. Example: Changing registrationId Alters a Template-Based Entity ID

If the SP uses:

```text
entityId = {baseUrl}/saml2/service-provider-metadata/{registrationId}
```

then at `https://portal.example.test`:

```text
employee -> https://portal.example.test/saml2/service-provider-metadata/employee
staff    -> https://portal.example.test/saml2/service-provider-metadata/staff
```

In this case, changing registrationId **simultaneously produces a new SP Entity ID**, because the template itself binds the two fields. Re-coordinate the SP registration/Audience with the IdP. When the SP needs an unchanging Entity ID across local key renames, consider declaring a **fixed** Entity ID and managing ACS/metadata independently.

## 12. Multi-IdP and Multi-Environment Setups

### 12.1. Same IdP, Multiple SP Applications

Suppose the same corporate IdP serves Portal and Payroll:

```text
IdP entityId = https://sso.company.example.test/saml/idp

Portal SP entityId  = urn:example:portal:prod:sp
Payroll SP entityId = urn:example:payroll:prod:sp
```

Both applications can use the **same `registrationId=employee` in their own repositories** without conflict: registrationId is locally scoped. However, a SAML assertion issued for Portal must never be accepted by Payroll, because **AudienceRestriction and verification conditions** target the specific SP.

### 12.2. Same Application, Multiple IdPs

One application has two registrations:

```text
employee -> Corporate IdP, certificate A, displayName "Employee account"
partner  -> Partner IdP, certificate B, displayName "Partner account"
```

Each IdP has its own entityId and trusted metadata source. Never select an IdP by displayName from an unvalidated query string. Never pair certificate A with issuer B. Never fetch metadata from a caller-supplied URL and accept new signing keys without governance.

### 12.3. DEV, UAT, PROD

Environments can use the same registrationId, e.g., `employee`, if repositories are separate. SP Entity ID and ACS must match the environment contract:

```text
DEV:  SP entityId = urn:example:portal:dev:sp
UAT:  SP entityId = urn:example:portal:uat:sp
PROD: SP entityId = urn:example:portal:prod:sp
```

These are convention examples, not mandatory SAML syntax. Separate certificates, metadata/IdP registrations, domains, and callbacks by policy. An assertion issued for DEV must never be accepted in PROD simply because both environments share `registrationId=employee`.

Display names can be identical across environments if the UI clearly shows context, though users should be protected from confusing environments when performing sensitive actions.

## 13. Common Operational Mistakes

### 13.1. Using Display Name as registrationId

**Mistake:** the button reads `"Sign in with Employee SSO"` and the code calls:

```text
/saml2/authenticate/Sign in with Employee SSO
```

If the real registration is `employee`, the repository fails to find the config, or the URL gets encoded/routed incorrectly. **Fix:** separate `displayName` from `registrationId`, and build links only from registered keys.

### 13.2. Setting registrationId to the IdP Entity ID

**Mistake:** using `https://idp.example.test/saml/idp` verbatim as `registrationId` and putting it in a URL path. Conceptually these identifiers serve different purposes; in URLs it also introduces characters requiring encoding. **Fix:** pick a clean registration key like `employee`, and keep the IdP Entity ID in asserting-party metadata/trust.

### 13.3. Assuming registrationId Is the SAML Issuer

**Mistake:** the IdP registers SP Entity ID as `employee`, while the real `AuthnRequest/Issuer` is `urn:example:portal:prod:sp`. The IdP may report unknown SP/invalid issuer. **Fix:** take the **actual SP Entity ID from SP metadata** and provide it to the IdP.

### 13.4. Assuming Metadata URL Is the IdP Entity ID

**Mistake:** IdP metadata is downloaded from `https://sso.example.test/metadata`, yet the XML declares `entityID="https://sso.example.test/issuer"`. If the SP expects `/metadata` as the issuer, the Response may be rejected. **Fix:** check `EntityDescriptor/@entityID`; never infer it from the metadata download URL.

### 13.5. Changing Logo/Brand and Changing Entity ID Along with It

**Mistake:** a provider is renamed in the UI and an engineer simultaneously changes `entity-id` in Spring. SAML audience or issuer stops matching. **Fix:** branding/UI changes are displayName changes; alter Entity ID only when the IdP/SP contract actually changes.

### 13.6. Changing registrationId Without Updating ACS

**Mistake:** renaming `employee` to `staff` in YAML; the IdP keeps POSTing to `.../employee` or rejects the new ACS. **Fix:** cross-check `acs.location`, metadata, and the IdP allowlist; test both SP-initiated and IdP-initiated flows if supported.

### 13.7. Metadata Emits Internal Host Behind a Reverse Proxy

If `{baseUrl}` emits `http://service:8080` instead of `https://portal.example.test`, template-based ACS/Entity ID values can be wrong. **Fix:** configure public base URL/forwarded headers from trusted proxies, inspect exported metadata at the public URL, and prevent external clients from spoofing proxy headers.

### 13.8. Confusing Login with Authorization

An "Admin SSO" button does not make the user an admin; a valid SAML Response still needs principal-to-local-account mapping and data authorization checks. **Fix:** authorize based on verified identity, membership, application policy, and object permissions; never use labels as a permission source.

### 13.9. Accepting a Response Just Because the URL Has the Right registrationId

An attacker can POST a crafted SAMLResponse to `/login/saml2/sso/employee`. **Fix:** rely on Spring Security/OpenSAML's full validation: the right IdP's verification key, issuer, audience, destination/recipient, time window, correlation, and anti-replay.

## 14. Verification Procedure in a Real Integration

Perform with one registration, e.g., `employee`:

1. **Inspect local config**: confirm key `registrationId=employee` in `spring.security.saml2.relyingparty.registration` or custom repository.
2. **Inspect IdP metadata from an approved source**: note `EntityDescriptor/@entityID`, SSO URL, binding, and certificate.
3. **Inspect SP metadata exported by the app**: note `EntityDescriptor/@entityID`, ACS URL, and certificate/binding. With `saml2Metadata()`, `/saml2/metadata/employee` can be used if supported by version/config.
4. **Inspect application config at the IdP**: SP Entity ID and ACS allowlist must match SP metadata; request signing policy must be compatible.
5. **Inspect the link the user clicks**: the "Employee account" button must point to `/saml2/authenticate/employee`.
6. **Inspect AuthnRequest** with a controlled SAML analyzer: Issuer is SP Entity ID, Destination is IdP SSO endpoint; never confuse `employee` with issuer.
7. **Inspect SAML Response** via framework validation: issuer is IdP Entity ID, audience is SP Entity ID, plus signature, destination/recipient, correlation, validity window, and replay checks.
8. **Inspect user mapping**: once authenticated, `NameID`/attributes identify the right user without auto-merging different users solely on email match.
9. **Test controlled changes**: changing displayName without changing registration/Entity ID must preserve the flow; changing registrationId or Entity ID in a test environment must show the expected impact on links/metadata.
10. **Verify safe logging**: log registration key and validation error codes per policy, never full SAMLResponses, assertions with sensitive data, private keys, or secrets.

### 14.1. Test Matrix

| Case | Setup / Action | Expectation |
| --- | --- | --- |
| Select right provider | Click employee label mapped to `employee` | Starts AuthnRequest using the employee registration |
| Wrong link | Employee label points to `partner` | UI test fails; fix label–registration mapping |
| Change label | `displayName` changes, all IDs stay the same | Login URL/trust unchanged |
| Non-existent registrationId | Visit `/saml2/authenticate/unknown` | Does not initiate federation with any unconfigured IdP |
| Wrong SP Entity ID | AuthnRequest Issuer mismatches SP registered at IdP | Rejected by IdP per policy |
| Wrong IdP Entity ID | Response/Assertion from untrusted issuer | Rejected by Spring Security/SP |
| Wrong Audience | Assertion intended for another SP | Rejected by SP |
| Invalid signature | Issuer/audience look right but signature fails | Rejected by SP |
| Change registration key, fixed Entity ID | `employee` -> `staff` | SAML trust ID stays unchanged; must update placeholder URLs |
| Change registration key, template Entity ID | ID contains `{registrationId}` | Expanded SP Entity ID changes; must update IdP |
| Reverse proxy | Internal base URL differs from public URL | Final metadata/ACS use trusted public URL |
| Two IdPs | `employee` and `partner` have different issuers/certs | Response from A is never accepted under B's trust |
| Two apps with same registrationId | Separate repositories; different SP IDs | No local collision; audience still distinguishes them |
| IdP-initiated SSO | IdP sends Response not initiated by SP | Supported only when profile/policy is designed with proper validation |

A test **checking only whether the login button works** is insufficient: negative tests are needed for issuer, audience, signature, ACS, time validity, and user-linking outcomes.

## 15. Checklist for Choosing Values Upfront

- [ ] Each registration in a repository has a unique, readable, stable, URL-safe `registrationId`.
- [ ] **SP Entity ID** and **IdP Entity ID** are documented separately in integration specs.
- [ ] SP Entity ID is verified against metadata actually emitted by the app; IdP Entity ID comes from trusted IdP metadata/contract.
- [ ] Metadata URL, SSO URL, ACS URL, and NameID are never confused with Entity ID.
- [ ] Confirmed whether `entityId` contains `{registrationId}`, to understand the impact of renaming the registration key.
- [ ] Login button labels are separate UI data mapped to permitted registration keys.
- [ ] Each IdP button leads to the exact endpoint and cert/trust of its corresponding registration.
- [ ] Proxy/public URLs, ACS, and IdP allowlists are aligned for the target environment.
- [ ] Metadata/certificate update procedures exist for issuer/entity ID/endpoint or certificate changes.
- [ ] Defenses against forged responses/assertions, replay, wrong issuer/audience, and missing business permissions remain active.
- [ ] Automated tests cover UI labels, links, registration lookup, metadata values, and SAML negative cases.
- [ ] Never use registrationId or display name as a user account key or authorization source.

## 16. Knowledge Self-Check

**Q1.** An app has `registrationId=corp` and SP `entityId=urn:example:app:sp`. Which SP identifier must the IdP register?

**Answer:** `urn:example:app:sp`, per the SP contract/metadata; `corp` is Spring's key and usually appears only in registration lookup URLs.

**Q2.** Users click a button labeled "Company SSO", while YAML declares `registrationId=employee`. Which value should the default initiation path use?

**Answer:** `/saml2/authenticate/employee`; the button label is `Company SSO` and does not need to appear in the URL.

**Q3.** Does changing the display name from "Company SSO" to "Employee account" make SAML Responses invalid?

**Answer:** Usually no if only UI text changes; Entity ID, endpoints, trust config, and mapping are unchanged.

**Q4.** Does changing `registrationId` always change the SP Entity ID?

**Answer:** No. Only indirectly when the SP entity ID template depends on `{registrationId}`; even when entity ID does not change, placeholder URLs may change.

**Q5.** If IdP metadata is downloaded at `/metadata`, is `/metadata` the IdP entityId?

**Answer:** Cannot be concluded. Read `EntityDescriptor/@entityID` inside trusted metadata.

**Q6.** Can Portal and Payroll share `registrationId=employee`?

**Answer:** Yes, if each app has its own repository. SP Entity ID and assertion audience must still distinguish the served application.

**Q7.** If a SAML Response declares the right IdP Entity ID but has an invalid signature, can login succeed?

**Answer:** No. Entity ID is only one part of trust verification; signature verification and other SAML checks remain mandatory.

**Q8.** Why is "Admin Login" not proof that a user holds admin rights?

**Answer:** It is merely a display name. Permissions derive from the authenticated user and business authorization checks, not login button text.

**Q9.** How many entityIds matter in one registration?

**Answer:** At minimum, distinguish the **SP Entity ID** and **IdP Entity ID** of the RP–AP pair. Spring Boot's `registration.<id>.entity-id` specifies the SP, while the IdP issuer lives in asserting-party metadata/config.

**Q10.** When migrating an environment to a new hostname, what is the priority check?

**Answer:** Compare actual SP metadata and `{baseUrl}`/`{registrationId}` templates against SP Entity ID, ACS, and IdP configuration; avoid internal URLs caused by a reverse proxy.

## Technical References

- Spring Security, **SAML 2.0 Login Overview** — `RelyingPartyRegistration`, `registrationId`, URI patterns: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security, **SAML 2.0 Metadata** — importing IdP metadata, exporting SP metadata: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Security, **Producing AuthnRequests** — endpoints and securing the initiation flow: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Security, **Authenticating Responses** — processing and selecting registration when receiving Responses: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security, **RelyingPartyRegistration API**: https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/saml2/provider/service/registration/RelyingPartyRegistration.html
- OASIS, **SAML 2.0 Metadata** — `EntityDescriptor/@entityID`, role descriptors, and endpoints: https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf

**Remember:** `registrationId` is Spring Security's configuration lookup key; **SP/IdP Entity ID** is the protocol identifier used to establish and verify trust relationships; **displayName** is the label shown by the app to users. Recording all three accurately, knowing when they depend on URL templates, and testing metadata/endpoint alignment prevents most SAML2 registration issues.