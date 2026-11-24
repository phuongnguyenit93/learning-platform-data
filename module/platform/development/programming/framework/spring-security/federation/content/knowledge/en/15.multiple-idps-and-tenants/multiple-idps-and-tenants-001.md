# Registering Multiple IdPs and Choosing a Provider on the Login Page with Spring Security SAML2

A **Service Provider (SP/Relying Party)** application can allow users to log in with multiple **Identity Providers (IdP/Asserting Party)**: an internal employee IdP, a partner IdP, or per-tenant IdPs. In Spring Security SAML 2.0, each SP–IdP trust relationship is represented by a **`RelyingPartyRegistration`**, and multiple registrations are managed through a **`RelyingPartyRegistrationRepository`**. The login page can present IdP choices and then send users to **`/saml2/authenticate/{registrationId}`** to initiate SAML Web Browser SSO.

**Core principle:** the IdP picker page only decides **where to start authentication**; it does not authenticate the user itself, does not confirm tenant authorization, and must never accept an arbitrary IdP SSO URL supplied by the browser. After the IdP returns a SAMLResponse, Spring Security must still verify the exact registration, signature, issuer, audience, recipient, validity window, and AuthnRequest correlation; the application must check permissions/tenant membership independently.

This lesson belongs to **Spring Security – Federation → Multiple IdPs and Tenants**. It covers configuring multiple IdPs, default and custom picker pages, tenant discovery, metadata/registration management, multi-tenant security, a standalone Java 17 example, and an operations checklist.

## 1. How Does the Multi-IdP Problem Arise?

Suppose a Portal has three user groups:

| Group | Authenticating Organization | Purpose |
| --- | --- | --- |
| Employees | Enterprise IdP | Access internal systems |
| Supply partners | Partner IdP | Access the supplier portal |
| B2B customers | Dedicated IdP per tenant | Access data belonging only to the corresponding organization |

When accessing `https://portal.example.test/private`, an unauthenticated user must determine **which IdP performs authentication**. A picker page can be shown:

~~~text
                 PORTAL — SIGN IN
      +-----------------------------------+
      | Choose an organization or provider|
      |                                   |
      | [Employee Sign-In]                |
      | [Partner Sign-In]                 |
      |                                   |
      | For B2B customers:                |
      | enter the org code assigned to you|
      +-----------------------------------+
          |                      |
          v                      v
/saml2/authenticate/corp   /saml2/authenticate/partner
          |                      |
          v                      v
      Enterprise IdP         Partner IdP
          |                      |
          +-----------+----------+
                      |
               POST SAMLResponse
                      |
             Spring Security SP
                      |
        Verify + create Authentication
                      |
                 Check tenant
~~~

The picker page **does not necessarily list every IdP** in the system. With thousands of tenants, a public page listing every IdP is both hard to use and risks disclosing customer names. You can use an organization code, domain discovery, or pre-issued login links, while still mapping to **a server-configured and trusted registration**.

## 2. Identifier Types That Are Easily Confused

| Component | Example | Who Defines It? | Purpose |
| --- | --- | --- | --- |
| `registrationId` | `corp` | SP/Spring Security | Internal key to look up a registration |
| IdP `entityId` | `https://login.corp.example.test/idp` | IdP | Trusted protocol/issuer identifier |
| SP `entityId` | `https://portal.example.test/saml/sp` | SP | Service provider identifier trusted by the IdP |
| IdP SSO endpoint | `https://login.corp.example.test/sso` | IdP metadata | Destination to send AuthnRequest |
| SP ACS endpoint | `https://portal.example.test/login/saml2/sso/corp` | SP | Endpoint that receives SAMLResponse |
| Tenant ID | `org-blue` | Business application | Data scope and access permissions |
| Display name on page | `Company Employees` | UX/SP | Human-readable label, not a SAML identity |
| Subject/NameID | Value issued by the IdP in the assertion | IdP within the federation scope | Identifies the user after verification |

**The three values—`registrationId`, IdP entityID, and tenant ID—are not automatically identical.** One IdP can serve multiple tenants; one tenant can also have multiple IdPs (for example, a primary IdP and an approved backup IdP). Choosing an IdP is a step in the login flow and is not sufficient to determine tenant permissions.

**Example:** `registrationId=partner` only states that the application wants to start SSO using the `partner` configuration. It does not prove which partner tenant the user belongs to or whether they hold `ROLE_ADMIN`.

## 3. Standard Flow: From Login Page to SAMLResponse

~~~text
(1) Browser GET /private
            |
            v
(2) ExceptionTranslationFilter -> requires authentication
            |
            v
(3) IdP picker page (/login or /login/choose)
            |
    User chooses "corp"
            |
            v
(4) GET /saml2/authenticate/corp
            |
            v
(5) Saml2WebSsoAuthenticationRequestFilter
     -> RelyingPartyRegistrationRepository
     -> findByRegistrationId("corp")
     -> creates AuthnRequest with issuer/ACS/destination
     -> stores request correlation
            |
            v
(6) Browser goes to IdP corp via HTTP Redirect/POST
            |
            v
(7) IdP authenticates and returns SAMLResponse to SP ACS
            |
            v
(8) Saml2WebSsoAuthenticationFilter / OpenSAML
     -> resolves the matching registration
     -> verifies signature, issuer, audience, recipient,
        response/assertion time, and InResponseTo
            |
            v
(9) Creates Authentication and SP session
            |
            v
(10) Authorization: account/tenant/role/resource
~~~

Each step has a distinct responsibility:

- **Picker:** displays allowed choices and initiation links.
- **Repository:** stores trust configurations, not user accounts or passwords.
- **SAML AuthnRequest resolver/filter:** constructs the outbound message to the IdP.
- **Response provider/filter:** verifies the returned SAML message.
- **Application:** links the internal account, determines tenant membership, and enforces business permissions.

**Do not confuse the initiation endpoint `/saml2/authenticate/corp` with the ACS `/login/saml2/sso/corp`.** The browser calls the initiation endpoint to go to the IdP; the IdP sends the response to the ACS after authentication.

## 4. Core Spring Security APIs

| API/Class | Role |
| --- | --- |
| `RelyingPartyRegistration` | Describes an SP–IdP pair, endpoints, entity IDs, and credentials |
| `RelyingPartyRegistrationRepository` | Looks up a registration by `registrationId` |
| `InMemoryRelyingPartyRegistrationRepository` | Holds a set of registrations in memory; supports iteration |
| `IterableRelyingPartyRegistrationRepository` | Repository contract capable of iterating over all registrations |
| `RelyingPartyRegistrations` | Creates a builder from IdP metadata |
| `DefaultLoginPageGeneratingFilter` | Generates the default login page when configuration conditions permit |
| `Saml2WebSsoAuthenticationRequestFilter` | Handles the SSO initiation endpoint and creates AuthnRequest |
| `Saml2AuthenticationRequestResolver` | Decides how to create an AuthnRequest from an HTTP request |
| `Saml2WebSsoAuthenticationFilter` | Processes SAMLResponse at the ACS |
| `Saml2AuthenticationTokenConverter` | Reads SAMLResponse and resolves the matching registration |
| `Saml2AuthenticationRequestRepository` | Stores issued requests to correlate when the Response returns |

**In particular:** `InMemoryRelyingPartyRegistrationRepository` implements `IterableRelyingPartyRegistrationRepository`. When multiple registrations and the default login page are enabled, Spring Security can **enumerate the registrations to generate the SAML links**. A custom repository that only implements the basic lookup interface without being **`Iterable`** may not provide enough information for the default picker page.

Starting in Spring Security 6.4, the `IterableRelyingPartyRegistrationRepository` interface was standardized; `InMemoryRelyingPartyRegistrationRepository` still supports iteration. When upgrading from 5.x to 6.x/7.x, check the classes/imports and login page mechanism for your exact release.

## 5. Option 1 — Spring Boot Properties: Registering Multiple IdPs

If Spring Boot 3.x auto-configures SAML2 from properties, you can declare multiple entries below:

`src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              metadata-uri: "classpath:saml/corp-idp.xml"
          partner:
            assertingparty:
              metadata-uri: "classpath:saml/partner-idp.xml"
~~~

The two files `src/main/resources/saml/corp-idp.xml` and `partner-idp.xml` must be **real XML metadata from the two trusted IdPs**. Metadata typically contains the IdP entityID, SSO endpoint/binding, and public certificate used for signature verification. **This is an application configuration template; SSO cannot run without real metadata, real IdPs, and an SP registered at the IdPs.**

Logical result:

| URL Chosen by User | Registration Used | Target |
| --- | --- | --- |
| `/saml2/authenticate/corp` | `corp` | SSO endpoint belonging to the corp IdP |
| `/saml2/authenticate/partner` | `partner` | SSO endpoint belonging to the partner IdP |
| `/login/saml2/sso/corp` | ACS callback per the `corp` configuration | SP verifies the response |
| `/login/saml2/sso/partner` | ACS callback per the `partner` configuration | SP verifies the response |
| `/saml2/metadata/corp` | SP metadata for `corp` if metadata DSL is enabled | Used by the corp IdP to register the SP |
| `/saml2/metadata/partner` | SP metadata for `partner` if metadata DSL is enabled | Used by the partner IdP to register the SP |

When using the builder/metadata, Spring Security can resolve the SP `entityId` and `assertionConsumerServiceLocation` from URL templates. **Always compare the actual SP metadata against the IdP configuration.** If an organization requires a dedicated signing credential for AuthnRequest or a decryption credential for encrypted assertions, additional configuration is needed. Do not disable SAML signature validation during integration.

### Does Declaring metadata-uri Mean Automatic Refresh?

No. When Spring Boot creates an `InMemoryRelyingPartyRegistrationRepository`, metadata may be loaded and built into registrations at startup. If an IdP rotates its certificate or changes its SSO URL, the in-memory repository **does not automatically track every change**. You can use a metadata repository/refresh/cache mechanism by version, but you must define trust policy, TTL, `validUntil`, rollover, and behavior when the IdP metadata URL fails.

### Should You Also Create a Separate Java @Bean Repository at the Same Time?

Not by default. **Properties** and a **manual bean** are **two alternative configuration options**. When you declare your own `RelyingPartyRegistrationRepository` bean, Spring Boot typically backs off the corresponding auto-configuration; do not assume Boot will merge the two registration sets.

## 6. Option 2 — Creating an InMemory Repository with Multiple Registrations

When Java customization is needed, you can build each registration from verified IdP metadata and return an iterable repository.

File `src/main/java/com/example/security/MultiIdpSecurityConfig.java`:

~~~java
package com.example.security;

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
public class MultiIdpSecurityConfig {

    @Bean
    RelyingPartyRegistrationRepository relyingPartyRegistrationRepository() {
        RelyingPartyRegistration corp = RelyingPartyRegistrations
            .fromMetadataLocation("classpath:saml/corp-idp.xml")
            .registrationId("corp")
            .build();

        RelyingPartyRegistration partner = RelyingPartyRegistrations
            .fromMetadataLocation("classpath:saml/partner-idp.xml")
            .registrationId("partner")
            .build();

        return new InMemoryRelyingPartyRegistrationRepository(
                corp, partner);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/healthz").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

**Purpose:** ensures a single application holds **two distinct registration IDs** and enables SAML login. `fromMetadataLocation` loads each IdP's configuration rather than using an IdP URL sent by the browser.

**Prerequisites to run:** this is a **class inside a Spring Boot/Security project**, not a standalone program run with `javac`. It requires the `spring-security-saml2-service-provider` module, Servlet Web, real metadata from a trusted source, IdPs with the SP registered, and signing/decryption configuration if needed. There is no fixed stdout.

**If you want to use Option 1 with properties,** **do not add the repository bean from Option 2** without clearly defining which configuration source wins.

## 7. Spring Security's Default IdP Picker Page

When SAML2 Login is enabled and the application has not configured a custom login page, Spring Security can use `DefaultLoginPageGeneratingFilter` to render a `/login` page. When there are **multiple IdPs** and the repository supports iteration, this page can list the SAML options corresponding to the registrations.

Conditions to watch:

1. The security filter chain has `saml2Login`.
2. The repository contains the registrations and is iterable, for example `InMemoryRelyingPartyRegistrationRepository`.
3. The default login page is **not overridden** by a `loginPage(...)` configuration or another login mechanism with higher precedence.
4. SAML initiation URLs use matchers compatible with the Spring Security version in use.
5. The app may have other login methods (form/OAuth2); the default page may display multiple groups depending on the filter chain and configuration.

### Why Does a Single IdP Not Show the Picker Page?

If there is only one registration, Spring Security may redirect directly to the AuthnRequest initiation endpoint. The picker page is useful when there are **multiple choices**. Do not assume the picker page will appear in every configuration: test `GET /private` while unauthenticated and trace the redirects to `/login` or `/saml2/authenticate/{id}`.

### Why Doesn't a Custom Repository Show the List?

`RelyingPartyRegistrationRepository` only requires lookup by registrationId. For features that require enumeration (such as the default picker page or certain metadata endpoints), the repository must support **`Iterable` / `IterableRelyingPartyRegistrationRepository`** per the API version. Do not implement `iterator()` by returning an empty list while `findByRegistrationId` still finds IdP pairs—that causes the picker page not to reflect the active configuration.

**The default page** helps test federation quickly, but it does not replace enterprise requirements for UI, language, tenant-specific visibility, branding, or privacy.

## 8. Option 3 — Custom IdP Picker Page with Friendly Labels

Many applications need a login page that matches their design: buttons like "Employee Sign-In", "Partner Sign-In", and a help link. The safe approach is for the **SP to define the allowed registration IDs**, then render links **to the SP's own endpoints** rather than rendering SSO URLs supplied by the client.

### SecurityFilterChain for a Custom Picker

File `src/main/java/com/example/security/CustomPickerSecurityConfig.java`:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class CustomPickerSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/", "/healthz", "/login/choose", "/css/**")
                .permitAll()
                .anyRequest().authenticated())
            .saml2Login(saml -> saml
                .loginPage("/login/choose"))
            .build();
    }
}
~~~

This pattern is an **alternative to the SecurityFilterChain in Section 6**. If you already have a filter chain serving the same scope, **modify that filter chain** instead of declaring two overlapping beans with unclear ordering. `/login/choose` needs `permitAll` to avoid a redirect loop for unauthenticated users.

**Important:** `loginPage("/login/choose")` only tells Spring Security the **URL of the application-owned login page**. It does not auto-generate a controller/template for that URL, nor does it change the ACS endpoint.

### Controller Using Only an Approved Allowlist of Choices

File `src/main/java/com/example/web/IdpPickerController.java`:

~~~java
package com.example.web;

import java.util.Comparator;
import java.util.List;
import java.util.Map;

import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class IdpPickerController {

    private static final Map<String, String> LABELS = Map.of(
        "corp", "Employee Sign-In",
        "partner", "Partner Sign-In"
    );

    private final RelyingPartyRegistrationRepository repository;

    public IdpPickerController(RelyingPartyRegistrationRepository repository) {
        this.repository = repository;
    }

    public record Choice(String registrationId,
                         String label,
                         String path) {}

    @GetMapping("/login/choose")
    public String show(Model model) {
        List<Choice> choices = LABELS.entrySet().stream()
            .filter(e -> repository.findByRegistrationId(e.getKey()) != null)
            .map(e -> new Choice(
                e.getKey(),
                e.getValue(),
                "/saml2/authenticate/" + e.getKey()))
            .sorted(Comparator.comparing(Choice::label))
            .toList();

        model.addAttribute("choices", choices);
        return "login-choose";
    }
}
~~~

**Why check the repository?** A label should only be shown if the corresponding registration currently exists. **Why hard-code the labels map?** This is the application's UI allowlist; it does not take company names from query parameters/browser input or publicly expose every configured tenant.

This snippet belongs in a **Spring MVC project**, not standalone Java. It requires a view engine (e.g., Thymeleaf), the Spring MVC dependency, and the registrations from the earlier configuration.

### Thymeleaf Template

File `src/main/resources/templates/login-choose.html`:

~~~html
<!doctype html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Choose a sign-in method</title>
</head>
<body>
  <main>
    <h1>Sign In</h1>
    <p>Select the identity organization that matches your account.</p>
    <ul>
      <li th:each="choice : ${choices}">
        <a th:href="${choice.path}"
           th:text="${choice.label}">Sign In</a>
      </li>
    </ul>
    <p th:if="${#lists.isEmpty(choices)}">
      No sign-in providers are currently available.
    </p>
  </main>
</body>
</html>
~~~

Thymeleaf will render internal URLs such as `/saml2/authenticate/corp` and escape labels. The links use **HTTP GET** to initiate an AuthnRequest flow; this is not a password-collection form for the IdP and does not send a `SAMLResponse` to the picker page.

**Note when rendering links:** use `Choice` data from the allowlist and verified registrations; avoid directly outputting an unchecked `href` taken from `?redirect=` or `?idpUrl=`, as that can create open redirects or phishing risks.

### Integrating Dependencies

A Spring Boot project needs Spring Web MVC, Spring Security, `spring-security-saml2-service-provider`, and (if using the template above) **`spring-boot-starter-thymeleaf`**. Module versions are managed by the Spring Boot BOM; do not manually mix OpenSAML 4 and 5.

## 9. With Very Many Tenants: Use an Org Code Input Instead of Listing IdPs

A B2B system with thousands of organizations should not publicly expose every IdP name on one page. Instead, you can ask for an **organization code** or use links provided in invitations:

~~~text
GET /login/choose
        |
    User enters "north"
        |
        v
GET /sso/start?tenant=north
        |
        v
Tenant Discovery Service
  map "north" -> registration "corp-north"
        |
        v
Check registration exists / tenant enabled
        |
        v
Internal redirect:
 /saml2/authenticate/corp-north
~~~

**The tenant code at this stage is only a routing hint** and must not be trusted as proof of membership. After the callback, the application must verify that the user truly belongs to that tenant using account mapping, assertion policy, and domain authorization.

### Controller Example with a Fixed Tenant Allowlist

~~~java
package com.example.web;

import java.util.Map;

import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;

@Controller
public class TenantSsoStartController {

    private static final Map<String, String> TENANT_TO_IDP = Map.of(
        "north", "corp",
        "suppliers", "partner"
    );

    private final RelyingPartyRegistrationRepository registrations;

    public TenantSsoStartController(
            RelyingPartyRegistrationRepository registrations) {
        this.registrations = registrations;
    }

    @GetMapping("/sso/start")
    public String start(@RequestParam String tenant) {
        String registrationId = TENANT_TO_IDP.get(tenant);
        if (registrationId == null
                || registrations.findByRegistrationId(registrationId) == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        return "redirect:/saml2/authenticate/" + registrationId;
    }
}
~~~

**Usage condition:** if you enable the `/sso/start` route for unauthenticated users, you must grant `permitAll()` to that exact endpoint in `SecurityFilterChain`; otherwise, the request will trigger login again and may cause a redirect loop. The above is a **Spring project class**, not standalone Java.

**Do not infer tenant membership from `?tenant=north`.** After a verified SAML Response, compare the internal account, IdP issuer, subject/NameID, and membership before granting permissions for `north`. If the tenant is not supported, return a controlled error rather than redirecting to an arbitrary "default" IdP or a client-specified URL.

### Discovery by Email Domain

An application can accept an email address strictly to **suggest** an IdP, such as a corporate domain. However, an unauthenticated email is user-supplied input and does not prove ownership of that domain. You need:

- Domain mappings from approved administrative configuration.
- Never using user-entered domain strings to construct new metadata/SSO URLs.
- Considering limiting messages like "this email has an account" to prevent account enumeration.
- Avoiding reliable tenant inference from shared consumer domains such as Gmail.
- Clear user choice or another discovery policy when multiple IdPs share the same domain.
- Verifying the actual subject/issuer after the callback before granting permissions.

Do not turn email discovery into "select IdP via MX DNS record," "log in to any IdP serving metadata at that domain," or trusting that the email entered before login is the same email verified by the IdP.

## 10. Standalone Java 17: Fail-Closed IdP Selector

The JDK 17 example below simulates **routing policy** before initiating SSO. It does not contact an IdP or generate a SAMLResponse. Each tenant is mapped to a **server-managed** `registrationId`, and only IDs in the enabled set can be selected. Any parameter attempting to supply a direct IdP URL is rejected.

Create `TenantIdpSelectionDemo.java`:

~~~java
import java.util.Map;
import java.util.Set;

public class TenantIdpSelectionDemo {

    private static final Map<String, String> TENANT_IDP = Map.of(
            "north", "corp",
            "suppliers", "partner"
    );

    private static final Set<String> ENABLED = Set.of(
            "corp", "partner"
    );

    static String choose(String tenant, String directIdpUrl) {
        if (directIdpUrl != null) {
            return "REJECT: direct IdP URL not allowed";
        }

        String registrationId = TENANT_IDP.get(tenant);
        if (registrationId == null || !ENABLED.contains(registrationId)) {
            return "REJECT: no approved registration";
        }

        return "START: /saml2/authenticate/" + registrationId;
    }

    public static void main(String[] args) {
        System.out.println(choose("north", null));
        System.out.println(choose("suppliers", null));
        System.out.println(choose("unknown", null));
        System.out.println(choose(
                "north", "https://untrusted.example.test/sso"));
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac TenantIdpSelectionDemo.java
java TenantIdpSelectionDemo
~~~

**Exact stdout:**

~~~text
START: /saml2/authenticate/corp
START: /saml2/authenticate/partner
REJECT: no approved registration
REJECT: direct IdP URL not allowed
~~~

This is a **route-resolution simulation**; it does not verify signatures, check tenant membership, build a SAML AuthnRequest, or prove login. In production, the mapping data can live in a controlled database/configuration service instead of `Map.of`; mapping updates must have an owner, auditing, tenant isolation, and tests. Avoid trusting an `ENABLED` set sent by the browser.

## 11. Multi-IdP and Multi-Tenant Are Not Exactly the Same

**Multi-IdP:** one SP trusts multiple authentication systems.

**Multi-tenant:** one application serves multiple organizations whose data/entitlements must be isolated. Possible topologies include:

- **One tenant → one IdP:** for example, each B2B customer provides one IdP.
- **One tenant → multiple IdPs:** for example, separate employee and contractor IdPs, or two approved sources.
- **Multiple tenants → one IdP:** for example, a conglomerate using a single IdP while separating subsidiary data.
- **One SP → multiple registration configurations for the same IdP issuer:** possibly due to different SP entityIDs, ACS endpoints, tenants, or protocol partners.

Therefore:

| Value Received Right After Login | Does It Identify the Tenant? |
| --- | --- |
| `registrationId` | Not necessarily; it only identifies the registration |
| IdP `entityId` / Issuer | Not necessarily; one IdP can serve multiple tenants |
| User email domain | Insufficient to trust membership |
| SAML NameID | Meaningful only within the issuer/NameID format context |
| Tenant claim | Source, scope, and mapping policy must be verified |
| Tenant ID chosen by browser | Request data only; must be verified on the server |
| Internal account+tenant membership | Can serve as the authoritative source if managed and currently active |

**Correct design:** Create or look up the account using **trusted issuer + subject identifier + appropriate registration/tenant scope**, then check membership/roles in domain authorization. Never grant global permissions solely because the user clicked a button.

## 12. Preventing Tenant and IdP Leakage via the Picker Page

A public login page easily becomes a source of customer intelligence if not designed carefully:

- **Listing all IdPs:** discloses the list of enterprises using the Portal.
- **Responding "this organization exists but is suspended":** creates an enumeration channel.
- **Displaying arbitrary logos/names from unverified metadata:** can be abused for spoofed interfaces.
- **Accepting an arbitrary `next`/returnUrl:** creates an open redirect to a phishing website.
- **Noticeable timing differences:** can reveal which tenants have active configurations.
- **Fetching metadata from a user-entered domain:** causes SSRF and trust-injection risks.

How to prevent this:

1. For 2–5 publicly disclosed IdPs, you can list friendly labels via an allowlist.
2. For many confidential tenants, prefer discovery via pre-issued codes/links with rate limiting and generic error responses when invalid.
3. Render HTML with standard escaping, restricting scripts/CSP as needed for UX.
4. Only redirect to **fixed internal paths** `/saml2/authenticate/{approvedRegistrationId}`.
5. If you must store where the user wants to go after login, store only a validated internal resource path—never an arbitrary domain.
6. Monitor repeated tenant-probing attempts, while avoiding unnecessary logging of sensitive emails or tenant names.

**Avoid confusion:** "hiding an IdP from the picker" is only a UX/privacy measure; **it is not authorization**. The `/saml2/authenticate/{registrationId}` endpoint can still be accessed directly, so tenant permissions must be enforced server-side after Authentication is established.

## 13. Matching Registration and Response with Multiple IdPs

SAML 2.0 does not allow an SP to trust a Response merely because the browser clicked IdP A's link. The SP must verify the **actual message received**.

| Condition | Why It Matters |
| --- | --- |
| Registration resolved properly | Selects the right IdP and SP trust material |
| Valid Response/Assertion signature | Message is untampered and signed by an authorized key |
| Issuer matches asserting party metadata | Does not accept IdP B as IdP A |
| AudienceRestriction contains the right SP entityID | Rejects assertions intended for another SP |
| Recipient/Destination matches ACS | Rejects Responses sent to the wrong endpoint |
| InResponseTo correlates with AuthnRequest when applicable | Prevents response injection/replay/login CSRF |
| Valid SubjectConfirmation and Conditions | Validity window, recipient, and usage conditions |
| Replay protection | A Response/Assertion cannot be reused against policy |
| Tenant membership and app permissions | Prevents cross-tenant access even when IdP-authenticated |

**Mandatory test:** Log in via `/saml2/authenticate/corp`, then submit a Response validly signed by the partner IdP spliced into the corp context. The system must reject it, or at minimum never create a session with corp tenant permissions from the partner Response.

If an SP accepts IdP-initiated SSO without a stored AuthnRequest, registration selection requires a different policy; only use an unverified Issuer as a **candidate hint within the approved IdP set**, then verify that candidate's signature/issuer/recipient/audience. Never dynamically fetch metadata from a URL carried inside the Response.

## 14. Two IdPs Sharing the Same Issuer or Certificate

A tricky case: multiple registrations share the same IdP `entityId` but have different SP `entityId`s, ACS URLs, or tenants. If the resolver only inspects the Response's Issuer, **it may not uniquely identify the registration**. The `findUniqueByAssertingPartyEntityId` API is only appropriate when there is truly **one** unique registration for that issuer; if multiple pairs exist, you must use request state or a resolver bound to verified tenant/recipient data.

Shared certificates across tenants or IdPs also do not solve registration selection. A valid signature under a shared key does not tell you **which SP entityID/tenant** the message was meant for.

Principles:

- Bind the `registrationId` to the **stored AuthnRequest context**; never trust unverified cookies/query params from the browser.
- Match Audience/Recipient and SP entityID when processing the Response.
- Only allow one IdP to serve multiple tenants if there is an explicit identity- and tenant-mapping mechanism.
- Avoid "if lookup is non-unique, pick the first registration," because iteration order is not a trust boundary.
- If you need a custom `RelyingPartyRegistrationResolver` or `Saml2AuthenticationTokenConverter`, follow the exact API version and preserve the default SAML validators.

## 15. IdP Discovery and Browser Sessions

Some users click "Partner Sign-In" while their browser already holds an active corporate IdP session. IdPs are separate systems; the outcome depends on whether they hold existing sessions, share an upstream federation, and each party's policies.

**Scenarios:**

1. **Choosing corp when a corp IdP session already exists:** the IdP may silently authenticate via SSO.
2. **Choosing partner when only a corp session exists:** the Partner IdP may show its own login page; it does not automatically use the corp session to prove partner identity.
3. **Switching choices mid-flow:** an older AuthnRequest/RelayState may still exist; preserve correlation and avoid processing a Response belonging to a different flow.
4. **Local logout followed by logging back in:** the IdP session may persist, bringing the user back without prompting for a password.
5. **One person with accounts at two IdPs:** after login, identify by **issuer+subject**; do not merge accounts based solely on a matching email.
6. **Different MFA/assurance levels:** two IdPs may enforce different authentication policies; sensitive business permissions should inspect AuthnContext/AuthnInstant from the verified assertion if required.

The picker can show the choices again after logout, but **you must not infer that the user safely "switched organizations" merely by clicking a new link**. Switching tenants/accounts requires clearing relevant state and re-validating session/authentication.

## 16. Auto-Selecting an IdP Based on Subdomain or Path

Some systems implement:

~~~text
https://north.portal.example.test/login
https://supplier.portal.example.test/login
           |
           v
Server verifies configured host/route
           |
       allowlist mapping
           |
           v
       registrationId
           |
           v
/saml2/authenticate/{registrationId}
~~~

This design can reduce picker clicks, but note the following:

- **`Host` and `X-Forwarded-Host` headers are not inherently trustworthy.** Only trust managed proxies, configured forwarded headers, and a host allowlist.
- Wildcard subdomains must not dynamically construct IdP metadata URLs from client hostnames.
- Each registration may require its own SP entityID and ACS; the IdP must register those exact URLs.
- If using a reverse proxy and `{baseUrl}`, verify that the actual SP metadata contains the correct public HTTPS hostname.
- When a tenant is suspended, the endpoint must return a policy error; never fall back to a default registration.
- Write unit/integration tests for IDN/Unicode domains, case sensitivity, trailing dots, and unknown hosts; canonicalization must be consistent.

**Never concatenate raw `Host` into `/saml2/authenticate/` or an IdP SSO URL.** Every mapping must come from trusted server configuration.

## 17. SP Metadata with Multiple Registrations

For each SP–IdP pair, the IdP needs to know the **SP entityID, ACS URL, and signing/encryption certificates if applicable**. Spring Security supports publishing SP metadata when enabled:

~~~java
http
    .saml2Login(Customizer.withDefaults())
    .saml2Metadata(Customizer.withDefaults());
~~~

Typical endpoints:

| Path | Role |
| --- | --- |
| `/saml2/metadata` | Aggregated/enumerable SP metadata endpoint depending on repository and version |
| `/saml2/metadata/corp` | SP metadata for the `corp` registration |
| `/saml2/metadata/partner` | SP metadata for the `partner` registration |
| `/saml2/service-provider-metadata/corp` | Compatible metadata path by registration ID |

**IdP metadata is the input for the SP to trust the IdP; SP metadata is the output for the IdP to register the SP.** Do not load the SP metadata URL and use it as IdP metadata when configuring a registration.

When SP entityID/ACS values differ per registration, two IdPs may need two independently imported SP metadata files. When registrations share an SP entityID but have different partner policies, each connection and response binding must still be verified individually.

### Behind a Proxy

If the app runs internally over HTTP while external traffic is HTTPS, `{baseUrl}` can be wrong when forwarded headers/host validation are misconfigured. The symptom is metadata containing `http://internal-host:8080`, causing the IdP to send SAMLResponse to the wrong ACS or reject the request. Only allow forwarded headers from a trusted reverse proxy and verify against the actual public URL.

## 18. Upgrading from Default Picker to Custom Picker: Safe Procedure

**Step 1 — test registrations:** verify that `/saml2/authenticate/{id}` works for every IdP. Do not change the UI while trust configuration is still broken.

**Step 2 — enable the default picker:** if there are multiple IdPs, verify that Spring displays the right choices and that the repository is `Iterable`.

**Step 3 — build the custom page:** add the `GET /login/choose` route and a template with friendly labels; pull IDs only from an allowlist.

**Step 4 — configure `loginPage`:** use `saml2Login(saml -> saml.loginPage("/login/choose"))` in the right `SecurityFilterChain`.

**Step 5 — `permitAll` for the UI:** make `/login/choose` and static assets public to avoid redirect loops.

**Step 6 — test every button:** each must lead to the right AuthnRequest endpoint, right IdP SSO location, and right issuer/ACS.

**Step 7 — test callbacks and state:** session/RelayState/InResponseTo preserve the right registration and reject Responses from other IdPs.

**Step 8 — check tenant authorization:** after login, pages and APIs must prevent a user in tenant A from viewing tenant B's data.

**Step 9 — observe and prepare rollback:** retain the ability to revert to the default picker without altering trust/metadata, keep sanitized logs, and handle errors cleanly.

**Step 10 — review privacy/UX:** do not leak the customer IdP list if policy prohibits it; display helpful messages when an IdP is unavailable without exposing sensitive details.

## 19. Checking the Limits of the Default Login Page

The page auto-generated by Spring Security is mainly meant to **support a standard login setup**. Do not assume it is a full-featured discovery portal:

- It does not guarantee enterprise branding or custom business labels.
- It does not replace tenant lifecycle management or SSO enable/disable policies.
- It does not distinguish between an IdP under maintenance, expired metadata, missing certificates, or an un-onboarded account.
- It does not accept a user's email to look up an IdP.
- It does not protect tenant data from enumeration.
- It does not manage post-login account linking or roles.
- It does not fail over to a backup IdP when one IdP is down.
- It does not turn IdP selection into authorization.
- It does not guarantee a non-`Iterable` custom repository will be listed.
- It does not automatically sync new IdP keys/certificates when metadata changes.

**The decision to build a custom picker** should be driven by UX, privacy, IdP count, and tenant policies. If there are only two public internal IdPs, the default picker may suffice. If providing a multi-customer B2B service, you should usually build controlled custom discovery.

## 20. Security When Storing AuthnRequest, RelayState, and Post-Login Redirects

Spring Security uses `Saml2AuthenticationRequestRepository` to store AuthnRequest details when initiating SSO. According to the documentation, the default is typically `HttpSessionSaml2AuthenticationRequestRepository`, binding the request to the browser session.

**Important reason:** If you arbitrarily look up an AuthnRequest solely by `RelayState` or `InResponseTo` without binding it to the browser/session, an attacker could attempt to feed their own SAMLResponse to another user's browser (login CSRF/fixation). This is a specific risk to address if replacing the request repository with a distributed cache.

When using multiple IdPs:

1. Store the request ID and registration context from the initiated flow.
2. When the Response returns, retrieve the exact context and verify signature/issuer/recipient.
3. Bind relay/correlation state to a browser/session or a carefully designed anti-forgery token.
4. Set a TTL and enforce one-time consumption to prevent replay.
5. Post-login redirects must only go to approved internal paths/URLs; never redirect to an arbitrary domain from a query parameter.
6. With multiple concurrent requests across tabs, test state handling and how the repository handles prior requests.

**Never allow a client to pass a `registrationId` at the ACS and override the registration verified from the AuthnRequest.** Registration selection upon receiving a Response may depend on prior state, issuer, and converter depending on the version; policy must ensure no cross-IdP login is possible.

## 21. Configuring When an IdP Requires Signed AuthnRequests or Encrypted Assertions

Each IdP may have different requirements:

| Parameter | Corp | Partner |
| --- | --- | --- |
| IdP SSO binding | Redirect | POST |
| Signed AuthnRequest required? | Yes | No |
| Sends encrypted assertions? | Possibly | Possibly |
| Verification certificate | Corp cert | Partner cert |
| SP signing credential | Required per corp policy | Possibly not needed |
| SP decryption credential | Required if assertion is encrypted | Required if assertion is encrypted |
| SP entityID/ACS | Per corp registration | Per partner registration |

Therefore, **do not blindly copy all properties from the `corp` registration to `partner`**. With manual builders, define the exact `assertingPartyMetadata` for each IdP—SSO location, bindings, verification credentials—and SP signing/decryption credentials as needed.

**Do not confuse:** The certificate used to verify an IdP Response is the **IdP's public certificate**. The SP's private keys for signing AuthnRequests and decrypting assertions serve two different roles; never expose private keys on the picker page, in public metadata, or in logs.

During key rotation, an IdP may hold multiple verification credentials for the same issuer; that never permits using the partner IdP's certificate to verify a corp Response.

## 22. Handling IdP Unavailability on the Picker Page

An IdP button can lead to an error due to an SSO endpoint outage, expired metadata, rotated certificates, or callback configuration mismatches. Distinguish among:

- **Metadata retrieval failure:** the SP cannot load or refresh a trusted registration.
- **SSO endpoint outage:** new IdP logins fail even though metadata is still valid.
- **Signature validation error:** certificate/issuer mismatch; never bypass verification to proceed.
- **ACS mismatch:** the IdP does not send the Response to the right URL.
- **Authorization 403:** SAML authentication succeeded, but the account lacks tenant permissions.
- **Tenant disabled:** the SP is not permitted to initiate or accept sessions for a suspended tenant.

The UI should display **"Unable to sign in with this provider right now"** and allow returning to the picker without leaking raw SAML assertions, certificates, NameIDs, or stack traces. If a backup IdP exists, display it only when the trust relationship, account mapping, and identity assurance policy have been approved; **never automatically fail over from `corp` to `partner`**.

Alert when a registration has broken metadata, signature failures spike, tenant mappings are missing, or repeated requests hit invalid IDs. Rate-limit discovery routes to prevent tenant-list enumeration.

## 23. Multi-IdP and Tenant Testing Matrix

| Test | Action | Expected Result |
| --- | --- | --- |
| 01 | Only corp registration configured | Corp AuthnRequest runs; picker may not appear |
| 02 | Corp and partner configured, repository `Iterable` | Default page can list both options |
| 03 | Choose corp | Redirect/POST to corp IdP per registration |
| 04 | Choose partner | Redirect/POST to partner IdP per registration |
| 05 | Switch to custom `loginPage` | Renders new route/view instead of the generated page per config |
| 06 | Open `/login/choose` while unauthenticated | No redirect loop/403 from missing `permitAll` |
| 07 | Request `/sso/start?tenant=north` | Routes to corp registration via server allowlist |
| 08 | Non-existent tenant | Does not pick an arbitrary default IdP; controlled error |
| 09 | Query contains `idpUrl` outside allowlist | Does not use that URL as destination |
| 10 | External `returnUrl` | Does not redirect to an untrusted domain |
| 11 | Response signed by IdP B after starting corp | Rejected or never grants corp permissions |
| 12 | Valid Issuer but wrong Audience | Rejected |
| 13 | Mismatched `InResponseTo` | Rejected in SP-initiated flow |
| 14 | Two registrations with the same IdP issuer | Resolver does not pick arbitrarily by order |
| 15 | One user has matching email at two IdPs | Does not wrongly merge accounts without a linking policy |
| 16 | Account in tenant `north` chooses `suppliers` | Does not grant `suppliers` permissions without membership |
| 17 | One IdP rotates certificate | Only the matching registration receives approved new keys |
| 18 | Corp IdP down, partner healthy | Only corp fails; never auto-routes account to partner |
| 19 | Behind reverse proxy | ACS/Entity ID uses correct external HTTPS origin |
| 20 | Page has many confidential tenants | Does not leak IdP list if privacy policy forbids it |
| 21 | User opens two login flows in two tabs | Request correlation does not cross or corrupt sessions |
| 22 | After login, call another tenant's API | Domain authorization denies access |
| 23 | IdP-initiated Response without request state | Accepted only with explicit policy and full validation |
| 24 | Non-`Iterable` custom repository | Verify custom picker/listing does not rely on missing enumeration |
| 25 | Corp and partner SP metadata | Each IdP has registered the exact Entity ID/ACS/certificate |

End-to-end tests must run against **test or real IdPs** with trusted certificates/metadata. Unit tests for picker/mapping logic only prove routing logic, not that Spring validates SAMLResponses properly.

## 24. Troubleshooting Common Errors

| Symptom | Possible Cause | Remediation |
| --- | --- | --- |
| Login page lists no IdPs | Non-`Iterable` repository, single registration, or custom login page enabled | Check enumeration contract configuration and login URL |
| Clicking corp button gives 404 | Wrong `registrationId` or altered initiation route | Check `/saml2/authenticate/corp` URL and matchers |
| Login returns 500 when initializing registration | Broken IdP metadata or unreachable source | Verify source/validity; never trust spoofed metadata |
| Browser loops on `/login/choose` | Picker route lacks `permitAll` | Permit the exact GET picker route and assets per policy |
| User picked the right IdP but Response signature invalid | Wrong IdP key or un-synced rotation | Verify certificate for that specific IdP only |
| IdP reports unknown SP | SP Entity ID not registered or mismatched | Compare SP metadata with IdP configuration |
| IdP redirects to wrong ACS | Proxy/ACS URL or registration out of sync | Align external origin, metadata, and `loginProcessingUrl` |
| Chose tenant A but reached tenant B's data | Domain authorization relied on hint instead of membership | Enforce tenant and resource scope server-side |
| User has no matching option | Tenant's IdP not onboarded or disabled | Handle status explicitly; never auto-provision IdPs |
| Shared issuer confuses registration resolution | Multiple SP–IdP pairs share the same Issuer | Use trusted request state/recipient/audience |
| Fast SSO without password prompt after re-selecting | IdP session already exists | Explain SSO reuse; require fresh auth when policy mandates |
| User logs in successfully but gets 403 | Missing business permissions | Check roles, tenant membership, and account status |
| Picker page leaks customer names | Lists all dynamic registrations | Switch to controlled discovery and conduct privacy review |
| Passing IdP URL in query causes strange redirect | Open redirect or trust injection | Replace with server-side `registrationId` allowlist |

**Avoid fixing errors by** disabling SAML signatures, skipping issuer/audience/recipient checks, picking the first registration when uncertain, or granting tenant permissions just because the user clicked the right button.

## 25. Pre-Production Checklist

- [ ] Maintain an admin-approved list of IdPs, with each SP–IdP pair having a unique, stable `registrationId`.
- [ ] Each registration uses the exact IdP metadata, entityID, SSO endpoint, verification credentials, and bindings for that partner.
- [ ] SP signing/decryption credentials are configured where required by the protocol or IdP.
- [ ] Clearly distinguish `registrationId`, IdP entityID, SP entityID, and tenant ID.
- [ ] Repository supports `Iterable` when the default picker or aggregated metadata is needed.
- [ ] Custom picker uses a display-name allowlist and points only to approved SP initiation paths.
- [ ] Custom `loginPage` has a controller/view, `permitAll`, and no conflicting filter chains.
- [ ] If tenant/email/subdomain discovery is used, mappings originate from trusted server configuration.
- [ ] Never fetch metadata or construct SSO URLs from unverified browser/query/`Host` header inputs.
- [ ] Exact SP metadata Entity ID/ACS/certificate are registered at every IdP.
- [ ] AuthnRequest/Response, signature, issuer, audience, recipient, `InResponseTo`, and replay protection are tested for every IdP.
- [ ] Post-authentication, verify account linking via issuer+subject and tenant membership via authoritative data.
- [ ] Domain authorization enforces role/tenant/resource policies independently of the picker.
- [ ] Do not expose confidential IdP/tenant lists or enable user enumeration.
- [ ] Handle IdP downtime, metadata expiration, key rotation, and disabled tenants cleanly.
- [ ] Test multi-tab/concurrent login flows, reverse-proxy public URLs, and session state.
- [ ] Identify Spring Security 6.x/7.x upgrade impacts related to login pages, resolvers, and metadata.
- [ ] Maintain sanitized logs and audit changes to registrations, tenant mappings, and access permissions.

## 26. Conclusion

**Registering multiple IdPs in Spring Security means configuring multiple `RelyingPartyRegistration` instances in a repository and letting users initiate an AuthnRequest for the appropriate `registrationId`.** For a small number of IdPs, `InMemoryRelyingPartyRegistrationRepository` combined with the default login page can be a simple solution. When branding, privacy, or tenant-based discovery is needed, build a **custom picker** with **server-side allowlist mapping**.

Regardless of which IdP the user selects, the SP must only create a session after the SAML Response has been verified against the **exact issuer, keys, and recipient/audience**, and then verify the internal account, tenant membership, and business permissions. **A login button is not a security boundary**: all IdP selection, state/correlation, account linking, and authorization must be enforced on the server.

### Official References

- Spring Security — SAML 2.0 Login Overview, multi-IdP configuration and login picker: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security — SAML2 Authentication Requests: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Security — Authenticating SAML Responses: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security — SAML2 Metadata: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Security Javadoc — InMemoryRelyingPartyRegistrationRepository: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/registration/InMemoryRelyingPartyRegistrationRepository.html
- Spring Security Javadoc — IterableRelyingPartyRegistrationRepository: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/registration/IterableRelyingPartyRegistrationRepository.html
- Spring Security Javadoc — Saml2LoginConfigurer: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/configurers/saml2/Saml2LoginConfigurer.html
- OASIS — SAML 2.0 Profiles (Web Browser SSO): https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
