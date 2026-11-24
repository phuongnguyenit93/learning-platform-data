# Default and Custom Metadata URLs Across Spring Security Versions

**SAML 2.0 metadata** is an XML document describing parameters that help a Service Provider (SP) and Identity Provider (IdP) establish a trust relationship: Entity ID, endpoints, bindings, and public certificates. In Spring Security SAML2 Service Provider, the Spring application is the **SP/Relying Party**, which can publish **SP metadata** based on `RelyingPartyRegistration` and provide an HTTP URL for an IdP administrator to download the XML.

The question "which URL serves metadata?" only has an accurate answer once you know **the Spring Security version and how the application enabled the metadata feature**. Furthermore, **SP metadata URL, SP Entity ID, ACS URL, and IdP metadata URL are four distinct concepts**. Changing a metadata download URL does not automatically change the Entity ID or where SAML Responses are received. This lesson explains defaults across generations, safe customization approaches, and verification using real HTTP/XML.

## 1. Distinguishing Four Important Addresses

Suppose application `https://portal.example.com` integrates partner B's IdP using `registrationId = partner-b`.

| Type | Example | Function |
| --- | --- | --- |
| **SP metadata URL** | `https://portal.example.com/saml2/metadata/partner-b` | GET address returning the SP's XML to give to the IdP |
| **SP Entity ID** | `https://portal.example.com/saml2/service-provider-metadata/partner-b` | SAML identifier of the SP; used by the IdP as audience/trust target |
| **SP ACS URL** | `https://portal.example.com/login/saml2/sso/partner-b` | Where the browser sends the SAML Response to the SP, usually via HTTP POST |
| **IdP metadata URL** | `https://login.partner-b.example/idp/metadata` | IdP metadata source read by the SP to learn issuer, SSO endpoint, and certificates |

The `.example` domain is illustrative, not a real reachable host.

A common point of confusion: by default `RelyingPartyRegistration.entityId` in many Spring Security versions takes the form `{baseUrl}/saml2/service-provider-metadata/{registrationId}`. This string **resembles the historical metadata download path**, yet in essence it is a protocol identifier. An Entity ID **does not have to be** a URL that serves XML over HTTP.

**`registrationId` is also not the Entity ID.** It is an internal key helping `RelyingPartyRegistrationRepository` locate the SP–IdP configuration pair. You can name it `partner-b`, `corp`, or `vendor-01`, as long as it matches system configuration.

## 2. Version Milestones: What Changed in Spring Security?

| Generation | SP metadata publishing mechanism | Typical endpoint when configured | Limitations to remember |
| --- | --- | --- | --- |
| **Legacy Spring Security SAML Extension** | `MetadataGeneratorFilter` and `MetadataDisplayFilter` from the separate extension | `/saml/metadata` | Different stack from the modern SAML2 module |
| **Spring Security 5.2.x / early SAML2 era** | SAML2 SP did not yet have a built-in XML metadata endpoint like later versions | Often required supplying metadata manually | Do not treat a default SP Entity ID as proof an HTTP endpoint exists |
| **Spring Security 5.4–5.8** | `Saml2MetadataFilter` added manually to SecurityFilterChain | `/saml2/service-provider-metadata/{registrationId}` in guides from that era | Does not automatically expose a URL merely because the SAML2 dependency is present |
| **Spring Security 6.0** | Check exact patch filter APIs and configure manually | Path determined by actual filter/matcher | `HttpSecurity.saml2Metadata` was not yet an API in 6.0 |
| **Spring Security 6.1–6.5** | `http.saml2Metadata(...)` DSL; includes extended resolvers and filters | `/saml2/metadata`, `/saml2/metadata/{registrationId}`, plus legacy alias | The `saml2Metadata` DSL appeared in **6.1** |
| **Spring Security 7.x** | Continues `saml2Metadata(...)` and metadata response resolvers | Same modern routes, depending on custom config | Check API versions and Servlet stack before upgrading |

According to the Javadoc, `Saml2MetadataFilter` has existed since **5.4**. The `HttpSecurity.saml2Metadata` Javadoc (6.1, 6.5, and 7.1) documents the primary URL `/saml2/metadata`, per-registration URL `/saml2/metadata/{registrationId}`, and backward-compatibility support for `/saml2/service-provider-metadata/{registrationId}`. Spring Security 5.5 configuration samples used the filter and legacy path. Spring Security 5.x uses `javax.servlet`, whereas 6.x/7.x use `jakarta.servlet`.

**"Default" does not mean automatically enabled.** In 6.1+, you must configure `saml2Metadata` or an equivalent mechanism with a valid `RelyingPartyRegistrationRepository`. In 5.x using `Saml2MetadataFilter`, you must add the filter to the chain. If an application has multiple chains or custom routing, final behavior depends on which chain handles the request.

## 3. Three Default Addresses in Spring Security 6.1+ and 7.x

### `GET /saml2/metadata`

This is the general endpoint. When the repository **can iterate over registrations** (such as `InMemoryRelyingPartyRegistrationRepository`), the resolver can emit aggregated metadata under `<md:EntitiesDescriptor>`. When only one registration exists, the XML format may be a single `EntityDescriptor` depending on the resolver.

If you have partner IdPs B and C, consider whether to publish an aggregated document to each IdP. Not every partner needs to see all SP registrations in your system.

### `GET /saml2/metadata/{registrationId}`

This is the per-registration endpoint:

~~~text
https://portal.example.com/saml2/metadata/corp
https://portal.example.com/saml2/metadata/partner-b
~~~

The braced segment is a **path variable**. The live endpoint will contain `partner-b`, not the literal string `{registrationId}`. The repository must contain that registration; an unknown ID must never default to pointing at another IdP.

### `GET /saml2/service-provider-metadata/{registrationId}`

This is the **backward-compatibility** alias recognized in 6.1+/7.x documentation under default configuration:

~~~text
https://portal.example.com/saml2/service-provider-metadata/partner-b
~~~

Many older applications used this path to serve XML while also using that same URL format as the SP Entity ID. The two roles **remain distinct**: one URL is where metadata is downloaded, the other string is a SAML issuer/audience. When an application customizes `metadataUrl(...)` or request matchers, test via real HTTP to verify whether the old alias still works; do not assume every default alias remains active under custom configuration.

## 4. How Do Metadata and Login Flows Differ?

~~~mermaid
sequenceDiagram
    participant Admin as IdP Admin
    participant B as User Browser
    participant SP as Spring Security SP
    participant IdP as Identity Provider
    Admin->>SP: GET /saml2/metadata/partner-b
    SP-->>Admin: XML SPSSODescriptor, EntityID, ACS, certificate
    Admin->>IdP: Register SP
    B->>SP: GET /secure
    SP-->>B: AuthnRequest targeting IdP
    B->>IdP: Authenticate
    IdP-->>B: SAMLResponse
    B->>SP: POST /login/saml2/sso/partner-b
    SP->>SP: Verify signature, issuer, audience, recipient, permissions
~~~

The GET metadata endpoint **does not process SAML Responses**. The ACS processes SAML Responses; `/saml2/authenticate/{registrationId}` starts the SP-initiated flow; `/saml2/metadata/{registrationId}` only emits XML. Seeing HTTP 200 on the metadata route confirms only part of SP setup; full login testing is still required.

## 5. Enabling Metadata in Spring Security 6.1+ with JavaConfig

In a **Servlet** application with `spring-security-saml2-service-provider` and a valid `RelyingPartyRegistrationRepository`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlMetadataConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(Customizer.withDefaults());
        return http.build();
    }
}
~~~

This is a configuration file in a **Spring Boot/Spring Security project**, not a standalone Java program runnable with `javac`. `saml2Login` enables the SAML authentication flow; `saml2Metadata` configures the SP metadata publishing endpoint. The sample still lacks IdP trust config/keys so it cannot authenticate logins on its own.

A Spring Boot registration config in versions supporting `assertingparty.metadata-uri` might look like:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          partner-b:
            entity-id: "{baseUrl}/saml2/service-provider-metadata/{registrationId}"
            acs:
              location: "{baseUrl}/login/saml2/sso/{registrationId}"
            assertingparty:
              metadata-uri: "https://login.partner-b.example/idp/metadata"
~~~

`assertingparty.metadata-uri` specifies **where the SP reads IdP B's metadata**, not the URL of published SP metadata. IdP metadata must come from a trusted source, and additional certificate/signing/decryption settings must match the contract. Property names may differ in older Spring Boot/Spring Security versions; consult the docs for **the Boot version in use**.

### Is it necessary to add a Controller for `/saml2/metadata`?

No. The DSL uses Spring Security's official filter and metadata resolver. Adding a parallel `@GetMapping("/saml2/metadata")` can cause confusion over request handling or emit XML inconsistent with `RelyingPartyRegistration`. Only build a custom controller for specialized reasons after verifying SAML metadata and security responsibilities; normally prefer the DSL.

### Can metadata be served when no user is logged in?

Usually yes: metadata is downloaded by IdP admins to establish the SP–IdP relationship, so it does not depend on a user session. However, the actual endpoint still sits behind the security chain; if path/authorization rules do not permit it, requests may receive 302/401/403. Inspect the HTTP response rather than guessing from `authorizeHttpRequests`.

## 6. Changing the Endpoint in Spring Security 6.1–6.5 and 7.x

The direct approach is `Saml2MetadataConfigurer.metadataUrl(String)`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class CustomSamlMetadataConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Metadata(saml ->
                saml.metadataUrl("/federation/metadata/{registrationId}"));
        return http.build();
    }
}
~~~

If the repository contains `partner-b`, metadata will be requested at:

~~~text
GET https://portal.example.com/federation/metadata/partner-b
~~~

The `{registrationId}` template lets the resolver pick the exact configuration. To use a URL without an ID:

~~~java
.saml2Metadata(saml -> saml.metadataUrl("/federation/metadata"))
~~~

Per the Javadoc, with an **Iterable** repository, an ID-less endpoint can emit metadata for all registrations under one `EntitiesDescriptor`. For more complex registration lookup logic (approved host/domain/tenant, a fixed registration), use `metadataResponseResolver(...)` and build explicit mapping rules.

**Changing the XML publishing URL does not change:**

- `RelyingPartyRegistration.entityId`;
- `RelyingPartyRegistration.assertionConsumerServiceLocation`;
- IdP Entity ID or IdP metadata URL;
- Login initiation URL;
- Signing/decryption credentials or user roles.

When moving the metadata link, IdP operations must be given the new URL, especially if the IdP auto-refreshes from URL. However, **never change SP Entity ID/ACS without a coordinated two-party plan**.

## 7. Deep Customization with `Saml2MetadataResponseResolver`

When a URL pattern is not enough, modern Spring Security provides `Saml2MetadataResponseResolver` and resolvers based on request matchers/registration repositories. Valid use cases:

- Let IdP A fetch metadata from a fixed ID-less route, while IdP B uses a different route.
- Serve metadata by hostname/tenant **approved server-side**.
- Deliberately emit full `EntitiesDescriptor` or per-partner metadata.
- Customize the downloaded filename.
- Generate metadata from a repository with updated configs, keys, or certs following a rotation workflow.

Design-level resolver flow example:

~~~text
GET /partners/b/sp-metadata
  -> server rule: route B
  -> registrationId = partner-b
  -> RelyingPartyRegistrationRepository.findByRegistrationId("partner-b")
  -> metadata XML from partner-b registration

GET /partners/c/sp-metadata
  -> server rule: route C
  -> registrationId = partner-c
  -> metadata XML from partner-c registration

GET /partners/unknown/sp-metadata
  -> no valid registration -> reject
~~~

**Never trust arbitrary browser-supplied headers/queries** to select an unauthorized issuer or trust configuration. Especially in multi-tenant apps, public hostnames and tenant rules must be on a server-side allowlist.

From 6.1 onward, a response resolver can be configured via `saml2Metadata(meta -> meta.metadataResponseResolver(...))`. Constructor/package APIs of some implementations changed across major versions; for snippets copied from blogs, verify against the Javadoc for your **exact version**. Do not mix `RequestMatcherMetadataResponseResolver` from newer lines with older `OpenSamlMetadataResolver`/constructors without checking compatibility.

## 8. In Spring Security 5.4–5.8, Use `Saml2MetadataFilter`

5.x projects typically add an SP metadata filter into `SecurityFilterChain`. A configuration using the **Spring Security 5.8** API:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.metadata.OpenSamlMetadataResolver;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.web.DefaultRelyingPartyRegistrationResolver;
import org.springframework.security.saml2.provider.service.web.Saml2MetadataFilter;
import org.springframework.security.saml2.provider.service.web.Saml2WebSsoAuthenticationFilter;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;

@Configuration
public class MetadataFilterConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            RelyingPartyRegistrationRepository registrations) throws Exception {
        var resolver = new DefaultRelyingPartyRegistrationResolver(registrations);
        var metadataFilter = new Saml2MetadataFilter(
                resolver, new OpenSamlMetadataResolver());

        metadataFilter.setRequestMatcher(
                new AntPathRequestMatcher(
                    "/legacy/saml-metadata/{registrationId}", "GET"));

        http.authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults());
        http.addFilterBefore(
                metadataFilter, Saml2WebSsoAuthenticationFilter.class);
        return http.build();
    }
}
~~~

In the snippet, `/legacy/saml-metadata/{registrationId}` is an **application-chosen route**, not the default across all 5.x releases. Without customizing the filter per historical Spring Security 5.5 examples, docs commonly used `/saml2/service-provider-metadata/{registrationId}`.

**API differences:**

- `Saml2MetadataFilter` has existed since 5.4.
- `setRequestMatcher(...)` sets the path to handle.
- `setMetadataFilename(...)` customizes the metadata filename (e.g. `saml-{registrationId}-metadata.xml`).
- Some older constructors accepting `Converter<HttpServletRequest, RelyingPartyRegistration>` were deprecated in 5.8; the code above uses `RelyingPartyRegistrationResolver`.
- Spring Security 5.8 uses `javax.servlet.*`; 6.x/7.x use `jakarta.servlet.*`.

**Do not copy this 5.8 config verbatim into 6.1+/7.x** where the DSL exists. Adding both the legacy filter and enabling `saml2Metadata(...)` risks two filters/paths competing or generating inconsistent metadata.

### Note on Spring Security 6.0

The Javadoc notes `HttpSecurity.saml2Metadata(...)` exists since **6.1**. Projects on 6.0 must not assume that method exists; check the `Saml2MetadataFilter` API for that exact version and configure manually, or upgrade the full dependency set via a tested BOM. Avoid "fixing" it by overriding only `spring-security-config` to 6.1 while keeping other modules at 6.0.

## 9. Why Does Legacy Spring Security SAML Extension Use `/saml/metadata`?

Before the modern `spring-security-saml2-service-provider` module, there was a separate **Spring Security SAML Extension**. Older configurations used `MetadataGeneratorFilter` and `MetadataDisplayFilter`, commonly serving metadata at `/saml/metadata`.

That is a different stack. When migrating an app to the modern Spring Security SAML2 module, the `/saml/metadata` route **does not appear automatically**. To keep supporting the old URL for already-registered IdPs, explicitly configure:

~~~java
.saml2Metadata(saml -> saml.metadataUrl("/saml/metadata"))
~~~

This configuration requires a Spring Security release with the 6.1+ DSL; choose an appropriate repository/resolver if multiple registrations exist. Preserving the old route **does not automatically mean old metadata XML can be reused wholesale**: you must cross-check SP Entity ID, ACS, signing certificates, bindings, and logout endpoints.

Identifying the stack from the codebase:

| Symbol | Belongs to branch |
| --- | --- |
| `MetadataGeneratorFilter`, `MetadataDisplayFilter`, `ExtendedMetadata` | Legacy Spring Security SAML Extension |
| `Saml2MetadataFilter` and `OpenSamlMetadataResolver` | Spring Security SAML2, especially 5.4–6.0 configuration style |
| `saml2Metadata(...)`, `metadataUrl(...)` | Spring Security 6.1 and newer |
| `RelyingPartyRegistration` | SP–IdP configuration model of modern SAML2 Service Provider |

## 10. Changing Metadata URL While Preserving Entity ID and ACS

Suppose before migration:

~~~text
SP metadata GET:
https://portal.example.com/saml2/service-provider-metadata/partner-b

SP Entity ID:
https://portal.example.com/saml2/service-provider-metadata/partner-b

SP ACS:
https://portal.example.com/login/saml2/sso/partner-b
~~~

After changing how XML is published:

~~~text
SP metadata GET:
https://portal.example.com/federation/metadata/partner-b

SP Entity ID:
https://portal.example.com/saml2/service-provider-metadata/partner-b

SP ACS:
https://portal.example.com/login/saml2/sso/partner-b
~~~

This makes complete sense: Entity ID and ACS **remain stable**, while only the XML download path changes. IdP admins need to update the metadata URL if their IdP refreshes by URL, yet **no audience/recipient change is needed** if the SP contract itself didn't change.

Conversely, changing SP Entity ID/ACS without coordinating with the IdP causes errors: IdP does not recognize the SP, old `AudienceRestriction` differs from the new Entity ID, `Destination`/`Recipient` mismatch, or SAML Responses go to the wrong ACS. Never disable validation to mask configuration errors.

## 11. Reverse Proxies and Base URLs Easily Break Metadata

A Spring application runs inside a container at:

~~~text
http://app:8080
~~~

Yet users and the IdP see:

~~~text
https://sso.example.com/portal
~~~

If `{baseUrl}` is constructed from the internal request or untrusted forwarded headers, XML may emit an incorrect Entity ID/ACS. Procedure:

1. Determine the true **public URL** (HTTPS, hostname, port, context path).
2. Verify `RelyingPartyRegistration.entityId` and `assertionConsumerServiceLocation`, declaring them explicitly if proxying is complex.
3. Process `Forwarded`/`X-Forwarded-*` only from managed ingress/reverse proxies; never accept spontaneous headers from clients.
4. Fetch metadata via the **public hostname** and check `EntityDescriptor/@entityID` and `AssertionConsumerService/@Location`.
5. Confirm the IdP has registered those exact values.
6. Test SP-initiated SSO, not just GET metadata.
7. Maintain NTP/clock sync, TLS, and valid certificates.

**Never use arbitrary `Host`/`X-Forwarded-Host` as the Entity ID or ACS**, because an attacker could influence generated metadata if proxy trust is misconfigured.

## 12. How to Verify Published Metadata XML

An SP metadata document might contain the following elements (**abridged** example, not guaranteed output for every version):

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://portal.example.com/saml2/service-provider-metadata/partner-b">
    <md:SPSSODescriptor
        protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
        <md:AssertionConsumerService
            Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
            Location="https://portal.example.com/login/saml2/sso/partner-b"
            index="1" />
    </md:SPSSODescriptor>
</md:EntityDescriptor>
~~~

Real metadata may include `KeyDescriptor` (public signing/encryption certificates), `SingleLogoutService`, metadata XML signature, or multiple bindings. With multiple registrations, the root may be `<md:EntitiesDescriptor>` containing multiple EntityDescriptors.

**Verify these points:**

| Field | Question |
| --- | --- |
| HTTP status/Content-Type | Does it return **metadata XML**, or redirect to login/return HTML? |
| `EntityDescriptor/@entityID` | Does it match the Entity ID the IdP uses to identify the SP? |
| `SPSSODescriptor` | Does it genuinely describe an SP, not accidentally IdP metadata? |
| `AssertionConsumerService/@Location` | Does it match the public URL registered at the IdP? |
| `AssertionConsumerService/@Binding` | Does it match how the IdP sends SAML Responses? |
| `KeyDescriptor` | Are public certificates the right type and valid under the rotation plan? |
| Metadata signature (if present) | Can the consumer verify it under its trust policy? |
| `EntitiesDescriptor` | Does it unintentionally expose multiple registrations? |

Metadata contains **public certificates**, never the SP's private signing key/decryption key. IdP metadata may be signed: if the app uses IdP metadata as a trust source, obtain it from a trusted source and verify its signature per policy. Never blindly accept arbitrary certificates embedded inside a Response.

## 13. Verifying Endpoints with Real HTTP Requests

Once the application runs behind a valid public URL:

~~~bash
curl -i https://portal.example.com/saml2/metadata/partner-b
curl -i https://portal.example.com/saml2/metadata
curl -i https://portal.example.com/saml2/service-provider-metadata/partner-b
~~~

If using a custom path:

~~~bash
curl -i https://portal.example.com/federation/metadata/partner-b
~~~

These commands have no fixed stdout because each application returns different XML. Evaluate by outcome:

| Result | Investigation direction |
| --- | --- |
| `404` | Wrong path/context path, DSL/filter not enabled, wrong version, or chain mismatch |
| `302` to login | Request routed to entry point/login instead of metadata filter |
| `401/403` | Rule or security chain denies access per its configuration |
| `500` | Repository, metadata resolver, or registration/certificate error |
| `200` yet HTML | Response may be another page, proxy error, or wrong controller |
| `200` with SAML XML | Inspect XML fields and test real login |
| Unknown ID returns another partner's metadata | Resolver picked the wrong registration: fix immediately |

Test **both old and new** URLs when upgrading versions. After editing `metadataUrl`, do not assume legacy aliases still work. If both routes must stay up during migration, design explicit routing rules and test both.

## 14. Standalone Java 17 Program to Distinguish Paths

The code below does not run Spring Security and does not parse metadata XML. It models the version-based URL table and illustrates that two distinct strings can simultaneously represent the Entity ID and the XML download path.

Create `SamlMetadataRoutesDemo.java`:

~~~java
public class SamlMetadataRoutesDemo {
    static String resolve(String pattern, String registrationId) {
        return pattern.replace("{registrationId}", registrationId);
    }

    public static void main(String[] args) {
        String legacy = resolve(
                "/saml2/service-provider-metadata/{registrationId}",
                "partner-b");
        String current = resolve(
                "/saml2/metadata/{registrationId}",
                "partner-b");

        String entityId = "https://portal.example.com" + legacy;
        String customMetadataUrl = "https://portal.example.com"
                + "/federation/metadata/partner-b";

        System.out.println("5.8 filter route: " + legacy);
        System.out.println("6.1+ metadata route: " + current);
        System.out.println("Entity ID remains: "
                + entityId.endsWith("/partner-b"));
        System.out.println("Different URL: "
                + !entityId.equals(customMetadataUrl));
    }
}
~~~

Command to run on JDK 17 or newer:

~~~bash
javac SamlMetadataRoutesDemo.java
java SamlMetadataRoutesDemo
~~~

Exact stdout:

~~~text
5.8 filter route: /saml2/service-provider-metadata/partner-b
6.1+ metadata route: /saml2/metadata/partner-b
Entity ID remains: true
Different URL: true
~~~

This is a **string-processing** example; it does not serve metadata, verify SAML signatures, or validate actual Spring dependencies. Which routes are active in the app must still be tested against the filter/DSL and real HTTP requests.

## 15. Safe Endpoint Migration Across Versions

A practical plan when upgrading from 5.8 to 6.5/7.x or changing URLs:

1. **Inventory current config:** Spring Boot/Security versions, registrationId, metadata URL, Entity ID, ACS, certificates, and active bindings.
2. **Verify resolved artifacts** via Gradle/Maven. Do not rely solely on versions in `pom.xml` if a BOM overrides them.
3. **Classify the change:** XML download URL only, or also Entity ID/ACS/keys?
4. **Pick the right mechanism:** 5.8 uses filter/matcher; 6.1+ uses `saml2Metadata()/metadataUrl()` DSL or a resolver.
5. **Avoid duplicate filters** between old and new configs unless intentional.
6. **Verify in staging:** GET XML via public URL, compare Entity ID, ACS, certificates, and bindings against pre-deploy baseline.
7. **Coordinate with IdP admins:** update the metadata import URL, check whether the IdP auto-refreshes or stores a snapshot.
8. **Test SP-initiated login**: AuthnRequest/Response, signature, audience, recipient, InResponseTo, timestamps, and replay.
9. **Test negative cases:** unknown registration, foreign issuer, wrong audience, wrong ACS, expired certificate, revoked account.
10. **Monitor and prepare rollback:** keep the old route if needed until IdPs finish updating, with alerts on 404/SSO failures.

Changing the metadata URL should be treated as an onboarding/operations change. Changing Entity ID/ACS is a protocol contract change requiring IdP approval.

## 16. Common Errors and Fixes

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `/saml/metadata` 404 after upgrade | Legacy SAML Extension path does not exist automatically in the new SAML2 module | Configure route via appropriate DSL/resolver |
| `/saml2/metadata` 404 on Security 5.8 | Using older filter with a different route, or filter not added | Check `Saml2MetadataFilter`/`setRequestMatcher` |
| `saml2Metadata(...)` fails to compile | Version below 6.1 | Check dependency graph; use version-appropriate filter or upgrade BOM |
| `javax.servlet`/`jakarta.servlet` errors | Mixing libraries across different major versions | Align Spring Boot/Security/Servlet API |
| Aggregate URL fails | Repository not Iterable or custom resolver lacks support | Use per-ID route or explicit resolver |
| GET metadata returns HTML | Login redirect, gateway rewrite, or another controller | Check HTTP status, Content-Type, filter ordering |
| Metadata contains `http://localhost:8080` | Wrong public base URL/forwarded headers | Configure proxy, public Entity ID, and ACS |
| Invalid Audience after changing link | Entity ID was inadvertently altered | Compare old/new contract with the IdP |
| Invalid Recipient/Destination | ACS differs from registered URL | Fix ACS/IdP; never disable validation |
| Cert mismatch after rotation | IdP/SP certificates out of sync | Update trust/metadata following procedure |
| Login succeeds yet page access fails | Missing role or tenant authorization | Check user/role mapping; do not blame metadata |

Some operations teams mistake a `302` from the metadata URL for "metadata is reachable because the login page opens". That outcome **does not** confirm SAML metadata is being served. Actual XML of the right type is required.

## 17. QA Checklist Before Publishing SP Metadata

- [ ] Confirmed Spring Security runtime version and matching filter/DSL mechanism.
- [ ] Valid `RelyingPartyRegistrationRepository` with required `registrationId`.
- [ ] GET on published URL returns valid SP metadata XML.
- [ ] Reconciled SP `entityID`, ACS, and bindings with the IdP.
- [ ] Public hostname/HTTPS/context path stable behind reverse proxy.
- [ ] Public certificates accurate; private keys never leaked in metadata/logs.
- [ ] Both new URL and legacy alias tested per migration policy.
- [ ] With multiple registrations, no unintended exposure of other partners' metadata.
- [ ] IdP imported metadata, verified trust/credentials, and accepted the SP.
- [ ] SP-initiated login succeeds for test user; invalid signature/issuer/audience/recipient all rejected.
- [ ] Tenant/object authorization operates independently after authentication.
- [ ] Documented metadata owner, rotation schedule, error monitoring, and rollback.

## 18. Official References

Select documentation matching **your exact Spring Security line**:

1. [Current Spring Security — SAML 2.0 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html): default URLs, `saml2Metadata` DSL, `metadataUrl`, and resolvers.
2. [Spring Security 7.1 Javadoc — HttpSecurity](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/builders/HttpSecurity.html): `saml2Metadata` introduced in 6.1, backward-compatible alias.
3. [Javadoc — Saml2MetadataConfigurer](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/configurers/saml2/Saml2MetadataConfigurer.html): route behavior with or without `{registrationId}`.
4. [Spring Security 5.8 Javadoc — Saml2MetadataFilter](https://docs.spring.io/spring-security/site/docs/5.8.0/api/org/springframework/security/saml2/provider/service/web/Saml2MetadataFilter.html): filter, `setRequestMatcher`, legacy Servlet version.
5. [Spring Security 5.5.6 Reference](https://docs.spring.io/spring-security/site/docs/5.5.6/reference/html5/): generating SP metadata via filter and legacy URL.
6. [Spring Security 5.2.1 Reference](https://docs.spring.io/spring-security/site/docs/5.2.1.RELEASE/reference/html/saml2.html): era prior to built-in metadata endpoint.
7. [Legacy Spring Security SAML Extension — Metadata](https://docs.spring.io/spring-security-saml/docs/current/reference/html/configuration-metadata.html): `/saml/metadata` path from the separate extension.
8. [Current Spring Security — SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): relationship between Entity ID, ACS, and related URLs.
9. [Spring Boot 3.4 — SAML2 Relying Party](https://docs.spring.io/spring-boot/3.4/reference/web/spring-security.html): properties and repository auto-configuration.

**Key takeaway:** for **Spring Security 6.1+/7.x**, the primary endpoints are `/saml2/metadata` and `/saml2/metadata/{registrationId}`, with the alias `/saml2/service-provider-metadata/{registrationId}` under default config. **5.4–5.8** use `Saml2MetadataFilter`; the legacy **Spring Security SAML Extension** uses `/saml/metadata`. In every generation, keep **XML download URL**, **SP Entity ID**, and **ACS** distinct, and verify both the XML response and real SAML flow.