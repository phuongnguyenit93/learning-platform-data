# Reading SAML 2.0 Metadata from Classpath, Filesystem, and Trusted HTTPS Locations

## 1. Objective and Scope

When a Spring Security application participates in **SAML 2.0 federation**, a Service Provider (SP, also called Relying Party/RP) must know **which Identity Provider (IdP, also called Asserting Party/AP) is trusted**, which Single Sign-On (SSO) endpoint to call, which issuer to accept, and which public keys to use for verifying SAML signatures. This information is typically exchanged as **SAML metadata XML**.

This lesson directly answers the question: **how do you load IdP metadata XML into Spring Security when the source is the classpath, a file on the server, or a vetted HTTPS URL?** Reading metadata is only a configuration step; source authenticity, signatures, update policy, and SAML response testing still need to be handled separately.

After this lesson, you will be able to:

- Distinguish **inbound IdP metadata** from **outbound SP metadata**.
- Recognize `EntityDescriptor`, `EntitiesDescriptor`, `IDPSSODescriptor`, `KeyDescriptor`, `SingleSignOnService`, `entityID`, and `Binding`/`Location` attributes.
- Use `RelyingPartyRegistrations.fromMetadataLocation(...).registrationId(...).build()` with the three sources `classpath:`, `file:`, and `https:`.
- Integrate metadata sources into a Spring Boot Servlet application with Spring Security and configure them to avoid leaking secrets.
- Assess risks of metadata spoofing, signing certificate replacement, fake HTTPS, SSRF from arbitrary URLs, and metadata endpoint outages.
- Distinguish a snapshot loaded at startup from refreshing metadata via a repository/cache; test the path from build to login.
- Diagnose resource errors, XML errors, metadata mismatches, broken paths when packaging a JAR, and certificate errors.

**Technical assumptions:** **Spring Boot 3.x and Spring Security 6.x (Servlet/MVC), Java 17 or newer**. Certain advanced APIs for Spring Security 7.1+ are noted separately. The domains `idp.example.org` and `app.example.org` in this lesson are **illustrative examples**, not active IdP endpoints.

## 2. What Is IdP Metadata? Is It a SAML Response?

**Metadata** is a document describing federation configuration, not proof that a user has logged in. IdP metadata typically provides:

| XML Field | Meaning for a Spring Security SP |
| --- | --- |
| `EntityDescriptor@entityID` | Official identifier of the IdP; must be matched against the SAML Response issuer |
| `IDPSSODescriptor@protocolSupportEnumeration` | IdP role and supported SAML 2.0 protocol |
| `SingleSignOnService@Binding` | How the IdP **receives AuthnRequests**: Redirect/POST depending on configuration |
| `SingleSignOnService@Location` | The IdP's SSO address |
| `KeyDescriptor use="signing"` | Public certificate/key information used to verify signatures from the IdP |
| `SingleLogoutService` | Endpoint/binding for Single Logout if provided by the IdP |
| `validUntil`, `cacheDuration` | Metadata expiration/caching information per specification and relevant policy |
| `ds:Signature` (if present) | Signature protecting **the metadata document**; distinct from the Response/Assertion signature |

Example of a **minimal XML structure** for reading element names, insufficient for real login because it lacks certificates, signatures, and full configuration:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://idp.example.org/issuer">
  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp.example.org/saml/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
~~~

**Do not use the abridged document above as production metadata**: it lacks signature verification keys and many trust relationship details. Real metadata usually includes one or more X.509 certificates under `KeyDescriptor` and may wrap multiple entities in `EntitiesDescriptor`.

A SAML Response normally arrives via the browser at the Assertion Consumer Service (ACS) when a user logs in; Spring Security verifies the assertion/response signature using **the IdP's public key trusted from configuration**, and checks issuer, audience, destination, validity timestamps, and conditions. **Successfully reading metadata XML does not prove a SAML Response came from a valid IdP**.

### Boundary Between SP Metadata and IdP Metadata

- **Inbound IdP metadata:** loaded by the Spring SP to know which issuer the IdP uses, where to send requests, and which certificates sign responses.
- **Outbound SP metadata:** Spring can publish an `SPSSODescriptor` with the SP entity ID, ACS URL, and SP public certificate so the IdP can register the application. To enable the metadata publishing endpoint in Spring Security, configure `.saml2Metadata(... )` appropriately.
- **A metadata URL is not a login URL.** Do not replace `metadata-uri` with an HTML login page address, a SOAP resource URL, or a URL that merely returns 302 loops.

## 3. How Spring Security Represents Metadata

At the configuration layer, `RelyingPartyRegistration` describes **the relationship between one SP and one IdP**. It contains the SP side (entity ID, ACS, signing/decryption keys if needed) and the IdP side (entity ID, SSO location/binding, public verification credentials, etc.).

Commonly encountered components:

- `RelyingPartyRegistrations`: utility to build a registration from IdP metadata XML.
- `RelyingPartyRegistrationRepository`: contract to look up a registration by `registrationId`.
- `InMemoryRelyingPartyRegistrationRepository`: repository holding created registrations in memory; suited for startup configuration snapshots.
- `Saml2WebSsoAuthenticationRequestFilter`: initiates AuthnRequest based on the registration.
- `Saml2WebSsoAuthenticationFilter`: processes SAMLResponse at the ACS using the registration and verification provider.
- `OpenSAML`: SAML/XML processing library used by Spring Security at the implementation layer.

Common way to create a registration:

~~~java
RelyingPartyRegistration registration = RelyingPartyRegistrations
        .fromMetadataLocation("classpath:saml/corp-idp.xml")
        .registrationId("corp")
        .build();
~~~

This snippet is **code within a Java application using Spring Security SAML SP** and cannot be compiled with a bare JDK without dependencies. Spring Security documents `fromMetadataLocation` as supporting **classpath**, **file**, and **HTTPS**. Give `registrationId("corp")` a meaningful name, because the metadata source URL is rarely suitable as a registration ID.

### Three Sources Under One Contract

| Source | `metadataLocation` value | Where the data actually resides |
| --- | --- | --- |
| Classpath | `classpath:saml/corp-idp.xml` | `src/main/resources/saml/corp-idp.xml` packaged onto the classpath |
| File | `file:/etc/myapp/saml/corp-idp.xml` | File on the filesystem of the **application runtime environment** |
| Trusted HTTPS | `https://idp.example.org/saml/metadata` | Real metadata endpoint controlled by the IdP, over verified TLS |

**The location string is chosen and pre-trusted by the SP.** Never accept an arbitrary metadata URL submitted by an unauthenticated user or external request and use it to establish SAML trust: that can cause SSRF and trusting an unintended IdP.

## 4. Gradle/Spring Boot Foundation for Running Examples

The application must use **Servlet/MVC** and include the SAML 2.0 Service Provider module. If the Spring Boot project already manages dependency versions, the application module's `build.gradle` needs equivalent configuration:

~~~groovy
repositories {
    mavenCentral()
    maven {
        url = uri("https://build.shibboleth.net/maven/releases/")
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-saml2-service-provider'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

This is a **snippet placed into an existing project's Gradle build**, not a complete `build.gradle`. If your organization configures repositories in `settings.gradle`/`dependencyResolutionManagement` or an internal mirror, add Shibboleth releases through that mechanism; do not add repositories blocked by project policy. Spring Security dependencies should follow Boot's BOM to avoid mixing incompatible OpenSAML versions.

With Maven, add the `org.springframework.security:spring-security-saml2-service-provider` dependency to a POM with a compatible BOM and the Shibboleth releases repository when required. This lesson focuses on **metadata sources**, so it does not manually build a SAML provider from XML/HTTP.

For pure Reactive WebFlux applications, do not assume the Servlet filters and examples here apply.

## 5. A Single Java Configuration for All Three Source Types

In the Boot application module, create `src/main/java/com/example/federation/SamlMetadataConfiguration.java`:

~~~java
package com.example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.security.saml2.provider.service.registration
        .InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration
        .RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration
        .RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration
        .RelyingPartyRegistrations;

@Configuration
public class SamlMetadataConfiguration {

    @Bean
    RelyingPartyRegistrationRepository relyingPartyRegistrationRepository(
            Environment environment) {

        String metadataLocation =
                environment.getRequiredProperty("saml.idp.metadata-location");

        RelyingPartyRegistration registration = RelyingPartyRegistrations
                .fromMetadataLocation(metadataLocation)
                .registrationId("corp")
                .build();

        return new InMemoryRelyingPartyRegistrationRepository(registration);
    }
}
~~~

> **Example scope:** the class above is a Spring `@Configuration` inside a Boot project that already has `@SpringBootApplication`, complete SAML dependencies, real IdP metadata, and component scanning covering `com.example.federation`. It is **not** a standalone Java program runnable with `javac SamlMetadataConfiguration.java` on a bare JDK. There is no fixed stdout because behavior depends on the environment and metadata.

How it works:

1. `Environment.getRequiredProperty` requires the application to configure `saml.idp.metadata-location`. Missing configuration causes startup to fail clearly rather than falling back to an arbitrary IdP.
2. `fromMetadataLocation` loads and parses IdP metadata from the given location via Spring Security.
3. `registrationId("corp")` assigns a stable ID so clients/browsers use the corresponding Spring URLs.
4. `InMemoryRelyingPartyRegistrationRepository` holds the resulting registration; **it does not automatically become a continuous metadata refresh service**.
5. Spring Boot uses the repository bean you provide instead of the auto-configured bean; do not simultaneously declare a competing `spring.security.saml2.relyingparty.registration.corp` configuration with the same ID.

Create `src/main/resources/application.yml` for **one** of the following three options (pick one value for the same key; do not repeat YAML keys).

### Choosing the classpath source

~~~yaml
saml:
  idp:
    metadata-location: "classpath:saml/corp-idp.xml"
~~~

### Choosing the OS filesystem source

~~~yaml
saml:
  idp:
    metadata-location: "file:/etc/myapp/saml/corp-idp.xml"
~~~

### Choosing an approved HTTPS source

~~~yaml
saml:
  idp:
    metadata-location: "https://idp.example.org/saml/metadata"
~~~

Important point: `saml.idp.metadata-location` is an **example-specific property** read by the bean above. It is **not** Boot's SAML auto-configuration property. A project using Boot directly can use:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              metadata-uri: "classpath:saml/corp-idp.xml"
~~~

This configuration belongs to **the approach where Boot auto-creates `RelyingPartyRegistrationRepository`**; do not combine it with a manual repository bean for the same registration. The `assertingparty.metadata-uri` YAML structure is documented in corresponding Spring Boot/Spring Security versions; always verify against your application's version.

### SecurityFilterChain for Receiving SAML Logins

If the project needs a custom chain, file `src/main/java/com/example/federation/SamlSecurityConfiguration.java`:

~~~java
package com.example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/**").permitAll()
                        .anyRequest().authenticated())
                .saml2Login(Customizer.withDefaults())
                .saml2Metadata(Customizer.withDefaults())
                .build();
    }
}
~~~

- `saml2Login` sets up the Servlet SSO filters; common initiation endpoint `/saml2/authenticate/corp`, common ACS `/login/saml2/sso/corp`.
- `saml2Metadata` explicitly enables the **SP metadata publishing** endpoint such as `/saml2/metadata/corp` for the IdP to import SP metadata; it **does not read IdP metadata** on behalf of your bean.
- Endpoint names can be customized; do not alter defaults if the IdP/ACS is already registered without coordination.
- Both `SamlMetadataConfiguration.java` and `SamlSecurityConfiguration.java` are composable configurations within the same project; a main application class, dependencies, and valid metadata are required to run.

## 6. Reading Metadata from the Classpath

### How to place the file in the project

Minimal layout:

~~~text
src/
  main/
    java/
      com/example/federation/
        SamlMetadataConfiguration.java
        SamlSecurityConfiguration.java
    resources/
      application.yml
      saml/
        corp-idp.xml
~~~

The file `corp-idp.xml` is **real metadata provided by the IdP**, not a hand-written minimal XML. Before committing the file to the source repository, verify the metadata provider, entity ID, certificates, and expiration. Metadata normally contains only **public certificates**, not private keys; even so, follow internal information policies and review key changes.

Use:

~~~text
classpath:saml/corp-idp.xml
~~~

Spring resolves the resource via the **runtime classpath**, not the current working directory. With standard Gradle or Maven, the contents of `src/main/resources` are packaged onto the classpath; in an executable Spring Boot JAR the resource may reside at `BOOT-INF/classes/saml/corp-idp.xml`. Do not convert `classpath:` into a fake filesystem path like `src/main/resources/...` when running in production.

**Classpath advantages:**

- Metadata ships alongside the application version, making it easy to review, sign, and audit in the build pipeline.
- Does not depend on network availability of the IdP metadata endpoint at startup.
- Container/JAR builds are consistent once the artifact is verified.

**Trade-offs:**

- When the IdP rotates its signing certificate or changes its SSO URL, the bundled snapshot becomes outdated; you must update the file, rebuild, and redeploy (or use a separate mechanism).
- Risk of environment drift if local developers and production run different JAR builds.
- You should not overwrite a classpath file **inside a running executable JAR**; it is an immutable artifact.

### How to verify the file is actually packaged

In Gradle, when the module has `processResources` and `bootJar` tasks:

~~~bash
./gradlew processResources
./gradlew bootJar
~~~

Then list the JAR using `jar tf` (substitute the exact generated JAR name):

~~~bash
jar tf build/libs/my-application.jar
~~~

Look for `BOOT-INF/classes/saml/corp-idp.xml` in the file listing if it is a Boot executable JAR. There is no fixed universal stdout because artifact/task names depend on the project.

**Common error:** `FileNotFoundException: class path resource [saml/corp-idp.xml] cannot be opened`. Check the filename, case sensitivity (especially on Linux), relative path after `classpath:`, `src/main/resources` directory, and `processResources` configuration. Do not switch to an Internet URL just to "work around" a packaging mistake.

## 7. Reading Metadata from a Filesystem File

Use:

~~~text
file:/etc/myapp/saml/corp-idp.xml
~~~

This is a URL/resource location pointing to **the filesystem visible to the Java process at runtime**. In Docker/Kubernetes, that is usually **a path inside the container**, not the developer's host path.

### Appropriate use cases

- The metadata file is provisioned by configuration management, volume mounts, a Kubernetes ConfigMap, or a config delivery tool.
- The application can swap metadata between deployments without modifying the JAR.
- Operations wants to manage certificates/trust metadata under a separate lifecycle.

**Do not assume "local file" means inherently safe.** If an untrusted process or user can modify the file, they can alter the IdP issuer/endpoint/certificates. That changes the trust boundary, not just an ordinary setting.

### Practical file rules

1. Use an **absolute**, deterministic path, such as `file:/etc/myapp/saml/corp-idp.xml`. Avoid relative paths because the working directory varies across IDEs, services, and containers.
2. Ensure the XML file exists **before the repository bean is created**, is readable by the service account running the app, and is writable only by authorized configuration management processes.
3. In containers, verify mounts, namespaces, symlinks, and file permissions; a host path does not guarantee the container sees the same path.
4. If you want to swap the file without restarting the application, build an explicit reload/refresh mechanism; **modifying the file on disk does not cause the InMemory repository to rebuild itself**.
5. When updating the file, typically write to a temporary file and atomically rename within the same filesystem, verifying version and validity before activation; avoid letting the process read a half-written XML file.
6. Record metadata version/source/fingerprint in change management. Do not print entire certificates/metadata in logs unnecessarily.

**Windows:** File URIs use syntax distinct from raw Windows paths (for example `file:///C:/saml/corp-idp.xml`); use `Path.toUri()` when converting from a `Path` to avoid escaping mistakes or `\\` issues. Do not assume Linux paths work across all OSes.

### Kubernetes case

A ConfigMap can mount metadata at `/etc/myapp/saml/corp-idp.xml`; an operator updates the ConfigMap, yet the pod/service may keep the repository object built at boot. Choose a **rolling restart** or implement a tested refresh mechanism. Also ensure volume mounts and file permissions are consistent across replicas; if one pod uses the old key and another uses the new key, users will experience intermittent login failures.

## 8. Reading Metadata from Trusted HTTPS

Use:

~~~text
https://idp.example.org/saml/metadata
~~~

Spring Security can download and parse metadata XML from an HTTPS endpoint when `fromMetadataLocation` is called. **HTTPS protects the transport connection and validates the server certificate against the TLS truststore/hostname verification**, yet it **does not by itself guarantee** that the endpoint serves metadata for **the right federation partner**.

Before accepting HTTPS metadata into the SP's trust, verify:

- The URL was provided through an official communication channel with the IdP/security team, and **the host/path is allow-listed**; never take the URL from a form or HTTP parameter.
- The URL uses the `https` scheme and exact hostname; the TLS certificate chain validates against Java's truststore; hostname verification is not disabled.
- The response returns the expected metadata XML, not an HTML login page, a reverse-proxy error page, or a document from an endpoint redirected through an unapproved host.
- `EntityDescriptor@entityID` matches the entity ID verified out-of-band; `IDPSSODescriptor`, SSO binding/Location, and signing certificate match the expected IdP.
- If metadata **is signed and verification is required**, the trust anchor for the metadata signature must be supplied **independently** of the downloaded metadata content; never use an untrusted certificate inside the XML to self-verify that XML.
- Policies exist for network timeouts, HTTP status codes, oversized metadata XML, unexpected entity counts, expired metadata, HTTP redirects, and refresh schedules.
- Allow only required endpoints/hosts at the egress proxy/DNS/network layer; account for DNS rebinding/SSRF if metadata URLs can vary with input.

### Why not use user-supplied URLs?

If an application exposes a "register new IdP" API to anyone and immediately calls `fromMetadataLocation(url)` with that URL, an attacker can force the server to access:

- Internal cloud/cluster endpoints or a private network service (**SSRF**).
- A URL returning crafted metadata with an issuer, SSO URL, and certificate controlled by the attacker.
- A redirect chain leading from valid HTTPS to another disallowed source.
- Extremely large XML causing resource exhaustion or startup failures.

To support dynamic multi-tenant federation, you must have a **partner approval workflow, hostname/path allow-list, egress restrictions, metadata/issuer/signature verification, rate limiting, and auditing**. Simply checking "URL starts with https://" is insufficient.

### Distinguishing three trust layers

| Layer | What to verify | What cannot be inferred |
| --- | --- | --- |
| **Download source** | Approved host/path, valid HTTPS, response not redirected to an unknown source | HTTPS alone does not prove the entityID belongs to the right partner |
| **Metadata document** | XML, issuer, validity, signing key, and metadata signature per policy | Valid XML parsing does not mean the XML is trustworthy |
| **Runtime SAML Response** | Response/assertion signature, issuer, audience, destination, recipient, timestamps, replay/correlation | Trusted metadata does not mean every response is valid |

Never disable TLS certificate validation, skip metadata signature validation when required by policy, or disable SAML Response signature verification just to make an integration pass.

### Downloading a snapshot in a controlled manner

If an organization wants to **vet HTTPS metadata once and package it as a file**, an administrator can download from the official IdP URL using a tool such as:

~~~bash
curl --fail --show-error --silent \
  --proto '=https' --proto-redir '=https' \
  --max-time 20 \
  --output corp-idp.xml \
  'https://idp.example.org/saml/metadata'
~~~

This illustrative command only downloads the file; it **does not verify signature/issuer/certificate**. If the tool follows redirects, review redirect rules and the hostname allow-list before using the file. Verify the file through your partner review workflow before committing it to a repository/configuration management; do not run this command directly against the example endpoint.

Do not conflate SSL pinning, TLS CA trust, signed metadata, and signed assertions: they protect **different things**.

## 9. Checking Whether Metadata XML Matches the Right IdP

Once metadata is loaded, you must understand its structure and pick the right entity.

### Example EntityDescriptor form

~~~xml
<md:EntityDescriptor
    xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://idp.example.org/issuer">
  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp.example.org/saml/sso/redirect"/>
    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
        Location="https://idp.example.org/saml/sso/post"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
~~~

Both `SingleSignOnService` entries above only specify which bindings **the IdP accepts AuthnRequests over**. They do **not** mean the SP must receive SAMLResponses over both bindings; the SP's ACS and the IdP's response configuration are separate. This XML example still lacks a signing certificate; use it to inspect structure, not to log in.

### Metadata with multiple entities

A file may contain an `EntitiesDescriptor` with multiple `EntityDescriptor` elements. In that case you must choose **the exact entity ID** (do not arbitrarily pick the first entity). Spring Security provides `collectionFromMetadataLocation(... )` to read multiple registration builders, while mapping each builder to a stable `registrationId` is the application's responsibility.

Illustrative example:

~~~java
Collection<RelyingPartyRegistration.Builder> builders =
        RelyingPartyRegistrations.collectionFromMetadataLocation(
                "classpath:saml/partners.xml");
~~~

This is a **code snippet** requiring imports inside a Spring Security project. Use this approach when genuinely managing multiple partners; do not split a single-entity IdP into unnecessary registrations. When selecting, confirm the issuer, SSO Location, signing certificate, and tenant scope; do not generate random IDs on each startup if you want stable login URLs.

### Case where a file contains SPSSODescriptor

If you accidentally pass **SP metadata** (`SPSSODescriptor`) to `fromMetadataLocation` intended for **IdP metadata** (`IDPSSODescriptor`), the registration will lack SSO info and IdP certificates or fail. Fix the input source; do not invent an IdP URL from an SP ACS.

## 10. Metadata Signatures Differ from Assertion Signatures

There are two decisions to keep separate.

**Decision A — should the loaded IdP metadata document be trusted?** An XML file may come from a trusted source, supplied through review and version control; or carry an XML signature verified with an out-of-band trust anchor. Metadata may lack a signature; in that case there must be another channel and mechanism confirming its source and integrity. If the URL is replaced with an attacker's domain and you blindly trust the new certificate in the metadata, all SSO trust is compromised.

**Decision B — should the SAML Response/Assertion sent during this login be accepted?** Spring Security uses the IdP's public verification credential to verify the SAML signature, while also checking issuer, destination, audience, timestamps, SubjectConfirmation, and related conditions.

| Signing Party | Signed Object | Purpose |
| --- | --- | --- |
| Authorized metadata publisher | Metadata XML | Proves metadata comes from the right source and is unaltered per trust policy |
| IdP | SAML Response / Assertion | Lets SP verify integrity and issuing authority of authentication messages |
| SP if required by IdP | AuthnRequest | Lets IdP verify requests originating from the SP |
| Web server TLS | HTTPS connection | Lets client authenticate the TLS server and protect transport |

**Never take a SAML Response signing certificate from untrusted metadata to self-verify the trustworthiness of that metadata.** Bootstrap trust through a vetted process.

### Metadata Refresh/Verification APIs in Newer Spring Security

In Spring Security versions providing `AssertingPartyMetadataRepository` and `OpenSaml5AssertingPartyMetadataRepository` (documented in Spring Security 7.1), a dedicated IdP metadata repository can use OpenSAML's `MetadataResolver` mechanism to handle expiration/refresh.

The documentation distinguishes:

- `OpenSaml5AssertingPartyMetadataRepository.fromTrustedMetadataLocation("https://...").build()`: approach for metadata **considered already trusted via source/location per policy**; consult your version's docs for exact semantics.
- `OpenSaml5AssertingPartyMetadataRepository.withMetadataLocation("https://...").verificationCredentials(...).build()`: allows supplying **independent credentials to verify the metadata signature**.
- Per the documentation, **if verification credentials are not provided for this verification setup, the component does not perform signature validation**. Do not mistake the word "trusted" for automatic metadata signature verification with an out-of-band key you never configured.

These APIs are advanced options and are **not required** to understand or implement basic metadata loading in Spring Security 6.x. If you need them, match the supporting version, API signature, and lifecycle; never copy 7.1 APIs into 6.1 without verifying compatibility.

## 11. Metadata Expiration, Refresh, and Certificate Rollover

A configuration that reads cleanly today can break weeks later when the IdP changes its SSO URL or certificate. Metadata files commonly carry:

- `validUntil`: timestamp after which metadata should no longer be accepted; check the implementation's validation/expiry behavior.
- `cacheDuration`: suggested cache interval per the metadata profile; not a guarantee that Spring Boot periodically polls the URL.
- `KeyDescriptor` containing multiple signing certificates: the IdP may publish **both old and new keys** simultaneously during a rollover window.
- Signed metadata may rotate its metadata signing key under a separate procedure, not necessarily at the same time as the SAML Response signing key.

### Behavior of the three sources

| Source | Does changing IdP metadata update the app immediately? | Proper operational practice |
| --- | --- | --- |
| Classpath snapshot | **No**; contents are baked into the artifact | Review new file → build → deploy → test |
| Filesystem file + InMemory repository | **Does not auto-reload** merely because the file on disk changed | Replace file carefully → restart or trigger designed repository refresh |
| HTTPS + `fromMetadataLocation` + InMemory repository | Do not assume automatic refresh after bean creation | Explicit refresh/cache policy, or controlled restart |
| Dynamic metadata repository with expiry-aware resolver | Can refresh per resolver/cache implementation | Add trust/signature, expiry, timeout, failure policy, and operational testing |

**Operational timeline pattern when the IdP rotates certs:**

1. IdP publishes verified metadata containing **current and new** keys and announces the cutover time.
2. SP imports the new metadata into its trust config/refresh repository, retaining the old credential during the overlap window as policy allows.
3. Test SSO with assertions signed by each supported/trusted key; monitor verification logs.
4. Once the IdP retires the old key and published metadata stabilizes, remove the old key under change management.
5. Never "hotfix" by disabling signature verification or accepting any certificate sent with a response.

### CachingRelyingPartyRegistrationRepository

Spring Security also provides a way to build a repository from a **supplier** and a **cache**:

~~~java
Supplier<IterableRelyingPartyRegistrationRepository> delegate = () ->
        new InMemoryRelyingPartyRegistrationRepository(
                RelyingPartyRegistrations
                        .fromMetadataLocation("https://idp.example.org/saml/metadata")
                        .registrationId("corp")
                        .build());

CachingRelyingPartyRegistrationRepository registrations =
        new CachingRelyingPartyRegistrationRepository(delegate);

registrations.setCache(cacheManager.getCache("saml-registrations"));
~~~

This is a **specialized configuration snippet** referencing Spring Security documentation, requiring imports, a valid `CacheManager` bean, and project lifecycle handling. `CacheManager` must configure TTL/eviction; refresh depends on **when an entry is evicted from cache** and the supplier is invoked again, not a guarantee that the IdP is re-fetched on a fixed schedule. If the remote URL is down on a cache miss, errors can occur; define a verified policy for failures, retries, and security-bounded "last known good" (never accept expired metadata merely for operational convenience).

## 12. Using InputStream When Metadata Comes from Another Source

The three locations are the simplest approach, but when XML is retrieved via a controlled internal API, database, or artifact store, Spring Security also offers a builder accepting an `InputStream`. Example helper in a project with **already verified** XML sources:

~~~java
package com.example.federation;

import java.io.IOException;
import java.io.InputStream;

import org.springframework.core.io.ClassPathResource;
import org.springframework.security.saml2.provider.service.registration
        .RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration
        .RelyingPartyRegistrations;

public final class SamlMetadataLoader {

    private SamlMetadataLoader() {
    }

    public static RelyingPartyRegistration fromResource() throws IOException {
        ClassPathResource resource =
                new ClassPathResource("saml/corp-idp.xml");

        try (InputStream input = resource.getInputStream()) {
            return RelyingPartyRegistrations
                    .fromMetadata(input)
                    .registrationId("corp")
                    .build();
        }
    }
}
~~~

This is a **helper class requiring Spring Security/OpenSAML/Spring Resource on the classpath**. It cannot run directly via `java SamlMetadataLoader` since it has no `main()` and creates no real IdP. Importantly, `try-with-resources` closes the stream properly; metadata is parsed before the stream closes.

The `fromMetadata(InputStream)` API separates **fetching/vetting the XML source** from **Spring building the registration**. It is not an excuse to fetch XML from arbitrary client-supplied URLs. If using a database, you still need a trusted source, signature/trust checks, and a rollover policy.

## 13. Standalone Java 17: Checking Location Policy Before Loading

To show that locations can come from **three sources yet all require approval**, the Java 17 example below checks three permitted locations against a **fixed allow-list** and rejects other HTTPS hosts. It **makes no network requests**, **does not parse XML**, and **does not replace TLS, metadata signature, or SAML Response checks**.

File `MetadataLocationPolicyDemo.java`:

~~~java
import java.net.URI;
import java.util.Set;

public class MetadataLocationPolicyDemo {

    private static final Set<String> APPROVED_LOCAL = Set.of(
            "classpath:saml/corp-idp.xml",
            "file:/etc/myapp/saml/corp-idp.xml"
    );

    static void requireApproved(String location) {
        if (APPROVED_LOCAL.contains(location)) {
            return;
        }

        URI uri = URI.create(location);
        boolean approvedHttps =
                "https".equalsIgnoreCase(uri.getScheme()) &&
                "idp.example.org".equalsIgnoreCase(uri.getHost()) &&
                "/saml/metadata".equals(uri.getRawPath()) &&
                uri.getPort() == -1 &&
                uri.getRawUserInfo() == null &&
                uri.getRawQuery() == null &&
                uri.getRawFragment() == null;

        if (!approvedHttps) {
            throw new IllegalArgumentException("Unapproved metadata location");
        }
    }

    public static void main(String[] args) {
        for (String location : new String[] {
                "classpath:saml/corp-idp.xml",
                "file:/etc/myapp/saml/corp-idp.xml",
                "https://idp.example.org/saml/metadata",
                "https://unknown.example.org/saml/metadata"
        }) {
            try {
                requireApproved(location);
                System.out.println("APPROVED: " + location);
            } catch (IllegalArgumentException ex) {
                System.out.println("REJECTED: " + location);
            }
        }
    }
}
~~~

Run on JDK 17+:

~~~bash
javac MetadataLocationPolicyDemo.java
java MetadataLocationPolicyDemo
~~~

**Exact** stdout:

~~~text
APPROVED: classpath:saml/corp-idp.xml
APPROVED: file:/etc/myapp/saml/corp-idp.xml
APPROVED: https://idp.example.org/saml/metadata
REJECTED: https://unknown.example.org/saml/metadata
~~~

Lessons from the code:

- Accept only **exact approved configuration values**; checking `startsWith("https://")` is insufficient.
- Do not accept arbitrary file paths or wildcard hosts. When a product has multiple IdPs, manage approved lists per partner and deployment.
- This function checks only the **initial URL string**. If an HTTP client follows redirects, DNS is tampered with, or returned XML does not match the entity, you still need network, TLS, redirect, issuer, and signature controls.
- Printing `APPROVED` does not mean the server successfully fetched XML or verified metadata; this is merely a configuration pre-check exercise.

## 14. Verification Sequence for the Three Loading Paths

### A. Checking classpath

1. Place **real IdP metadata** at `src/main/resources/saml/corp-idp.xml`.
2. Confirm file bytes and entity ID from the vetted IdP; if your organization tracks fingerprints, compare against the fingerprint from a trusted source.
3. Configure `classpath:saml/corp-idp.xml`.
4. Build/package, verify the file exists on the runtime classpath/JAR, and then start the app.
5. Test GET `/saml2/authenticate/corp` via a browser or HTTP client in a test IdP environment; it should direct you to the right SSO URL from metadata.

### B. Checking filesystem file

1. Place/download the vetted XML onto the **target machine/container**.
2. Grant read permission to the Java process user; restrict write permission from other processes.
3. Configure `file:/etc/myapp/saml/corp-idp.xml`.
4. Verify mount/path/read permission and startup.
5. Update the file with backup/versioning, perform a verified restart or refresh, and test login afterward.

### C. Checking HTTPS

1. Obtain the metadata URL from the IdP via an official channel and add the host/path to the allow-list.
2. Check the endpoint from the Java runtime environment, not just your laptop: DNS, TLS truststore, firewall, proxy, redirects, HTTP status, and MIME/contents.
3. Cross-check issuer, SSO URL, certificate, and expiration against verified IdP parameters.
4. Configure `https://idp.example.org/saml/metadata` with Java/Spring.
5. Start the app, evaluate failure behavior when the URL is down/times out, and verify monitoring/refresh in production.
6. Test end-to-end SSO and the cert rotation workflow in a test environment.

**QA caveat:** a successful startup proves metadata was read/parsed and beans were created to some extent, **not** that every SAML assertion will verify. You need a successful login against a test IdP, and must ensure assertions with invalid signatures, issuers/audiences, or timestamps are rejected.

## 15. Observing the Right Logs and Endpoints

For SP registration `corp`, a typical request diagram:

~~~mermaid
sequenceDiagram
    participant D as Deployed Spring SP
    participant M as Metadata source
    participant B as Browser
    participant I as IdP
    D->>M: Load and parse IdP metadata (startup / refresh)
    M-->>D: IdP issuer, SSO endpoint, certificates
    B->>D: GET /private
    D-->>B: Redirect to /saml2/authenticate/corp
    B->>D: GET /saml2/authenticate/corp
    D-->>B: Redirect / form AuthnRequest to IdP
    B->>I: SAML AuthnRequest
    I-->>B: Login / existing IdP session
    B->>D: POST SAMLResponse to ACS
    D->>D: Verify with trusted IdP registration
    D-->>B: App session on success
~~~

The **SP → metadata source** path is a loading/configuration step; the metadata URL is not called on every browser login. The **browser ↔ IdP ↔ SP** path is front-channel Web Browser SSO. Do not look in the browser's Network tab for HTTP requests made by the Java backend to the metadata URL; check server logs, metrics, or server-side network traces.

When debugging, you may log **non-sensitive resource paths, registrationId, approved issuer, HTTP status, and timestamps**, but never log raw SAMLResponse, session cookies, private keys, or full assertions containing personal data. In multi-tenant setups, control logs so users cannot view partner lists not meant for them.

### Inspecting the published SP metadata

If `.saml2Metadata(Customizer.withDefaults())` is enabled, Spring Security can return SP metadata at:

~~~text
GET /saml2/metadata/corp
GET /saml2/service-provider-metadata/corp
~~~

This metadata tells the IdP the SP's entity ID/ACS. It is **different** from the `https://idp.example.org/saml/metadata` URL where the SP reads IdP metadata. Checking SP metadata is valuable because the public ACS URL, entity ID, and certificates must be registered accurately at the IdP.

## 16. Common Errors and Layer-Appropriate Fixes

| Symptom | Where to check | Resolution |
| --- | --- | --- |
| `ClassPathResource cannot be opened` | Classpath/JAR | Filename, case sensitivity, resource processing, and path after `classpath:` |
| File not found or Permission denied | Filesystem/container | Mount path and JVM user; absolute path, read permissions |
| `UnknownHostException`, connection timeout | HTTPS/network | DNS, firewall, egress, proxy, and approved IdP URL |
| `PKIX path building failed` | HTTPS/TLS | Truststore/CA/cert chain of the endpoint; **never disable TLS verification** |
| HTTP 301/302 to login page when fetching metadata | HTTPS endpoint/redirect | Confirm exact metadata URL; do not accept HTML/redirects to unknown hosts |
| HTTP 401/403 on metadata URL | IdP access policy | Coordinate with IdP on official endpoint and valid authentication method |
| Parse error, malformed XML | File/response content | Check well-formed XML, encoding, namespaces, and complete download |
| Missing `IDPSSODescriptor` | Wrong SP metadata or wrong entity | Switch to the correct IdP metadata source |
| `Multiple entity/registration ambiguous` | `EntitiesDescriptor` | Select approved entity ID with stable ID; avoid picking arbitrarily |
| Wrong issuer after SSO | IdP entity ID | Compare `Issuer` against confirmed entity ID; do not relax validation |
| Wrong SSO binding/URL | Metadata and IdP config | Match `SingleSignOnService@Binding/Location` with AuthnRequest |
| SAML assertion signature invalid | IdP signing credential | Check new/old cert, issuer, trusted metadata cert, and rollover mechanism |
| SP metadata/ACS points to localhost | Reverse proxy/forwarded headers | Use public scheme/host/port and trusted proxy configuration |
| Build passes yet login fails | Runtime federation | Check IdP registration, ACS, audience, timestamps, cookies, and signatures |
| XML updated yet app keeps old cert | Snapshot/repository lifecycle | Restart/redeploy or designed refresh; do not expect "magical" reload |
| Users forced to logout/login repeatedly | Cookie/SSO state | Inspect SP session, cross-site POST SameSite cookie, correlation; don't guess metadata |
| Metadata file writable by untrusted service | Local trust boundary | Restrict write permissions, ownership, versioning, audit; re-import verified snapshot |
| Metadata URI replaced with internal URL | Dynamic registration/SSRF | Allow-list host/path, restrict egress, vet partner before loading |

Classify errors by **stage**:

1. **Build dependency failure:** JAR/OpenSAML/repository issue, not yet related to metadata XML.
2. **Startup failure while loading metadata:** path, network, TLS, XML content, or entity/method issue.
3. **Redirect to IdP fails:** SSO URL/binding, SP entity ID, request signing, or reverse proxy issue.
4. **Response reaches ACS and is rejected:** issuer, signing credentials, audience, destination, time, correlation, cookies, or assertion policy issue.
5. **Failure after metadata update:** prioritize checking version/refresh and key rotation; do not default to blaming the browser.

## 17. Before–After Scenario: Deploying to Kubernetes

**Before:** a developer succeeds locally because `src/main/resources/saml/corp-idp.xml` exists, whereas CI builds a new image and production intends to use `file:/opt/metadata/corp.xml` without mounting a volume. The service fails at startup.

**Proper fix:**

1. Standardize the runtime source: use classpath if you want an immutable image; mount a verified volume/file if configuring per environment.
2. When choosing a file, ensure every pod has `/etc/myapp/saml/corp-idp.xml` with valid contents and read permission for the startup user; configure the exact URI `file:/etc/myapp/saml/corp-idp.xml`.
3. Update the metadata file via atomic publishing, audit versions, and roll out. Verify issuer/cert/SSO URL before routing traffic to new pods.
4. Test login from a browser through the public URL, verifying the ACS receives POST and an SP session is created.

**Technical conclusion:** `classpath:` vs `file:` is a **choice of where to store the snapshot**; it does not decide whether SAML is trustworthy. Metadata trust and lifecycle must be managed separately.

## 18. Before–After Scenario: IdP Rotates Signing Certificate

**Before:** the SP loads HTTPS metadata once at startup and holds it in `InMemoryRelyingPartyRegistrationRepository`. The IdP rotates its certificate after the app runs for several days, causing SAML Responses signed with the new key to be rejected.

**Analysis:**

- If HTTPS metadata changed yet the SP did not reload, the SP still holds the old public verification key.
- If metadata reloaded yet signatures still fail, inspect the issuer, actual signature, entity ID, and chain of trust. New metadata from an unexpected URL **is not automatically trusted**.
- If the IdP switched abruptly without overlap, coordinate issuing valid metadata/safe rollback; never disable signature validation.

**Remediation:** design **overlapping certificates**, verify new metadata via a trusted source, and update snapshots/refreshes per procedure. With a cached/dynamic repository, specify eviction, expiry, failure policy, and how to observe cert rollover. Only a successful SAML login confirms the integration works in practice.

## 19. Self-Check Exercises and Answers

**Exercise 1.** In a Boot project, you place `src/main/resources/saml/corp-idp.xml` and configure `file:src/main/resources/saml/corp-idp.xml`. It runs in the IDE yet fails in Docker. Why?

**Answer:** `file:` locations depend on the runtime working directory/filesystem. If targeting a packaged resource, use `classpath:saml/corp-idp.xml`; if targeting an external file outside the JAR, mount an absolute path inside the container and use `file:/...`.

**Exercise 2.** An HTTPS metadata URL returns 200 and parses as valid XML, yet the issuer does not match the registered partner. Can that metadata be used to configure login?

**Answer:** no. You must verify issuer/entity ID, SSO endpoint, certificates, and trusted source before accepting it. HTTPS only authenticates the connection to the target host; it does not prove it is the enterprise's intended IdP.

**Exercise 3.** A developer adds `RelyingPartyRegistrations.fromMetadataLocation("https://...")` with an InMemory repository. Two weeks later, the IdP rotates its signing certificate and the app does not auto-update. Is this a JDK bug?

**Answer:** there is no evidence of that. An InMemory repository holds the registration built at creation time; an explicit refresh/rebuild or redeploy workflow is required. Synchronize metadata/credentials per IdP announcements.

**Exercise 4.** Metadata XML has `SPSSODescriptor` without `IDPSSODescriptor`, and a developer uses it as IdP metadata. What is wrong?

**Answer:** that describes an SP, not an IdP; you cannot derive the IdP SSO service and IdP signing key from an SP's ACS. Import the proper IdP metadata.

**Exercise 5.** An admin downloads metadata from the right URL yet does not know which public certificate was used to sign the metadata XML. Can they take any certificate from that untrusted file and treat it as independent proof?

**Answer:** no. That is circular self-attested trust. You need a supplied trust anchor/certificate verified through an independent channel, or an approved artifact-sourcing workflow; apply metadata signature verification policy if required.

**Exercise 6.** Configuration uses `spring.security.saml2.relyingparty.registration.corp.assertingparty.metadata-uri` while also defining a custom repository bean pointing to a different IdP. Why is this risky?

**Answer:** Boot can back off auto-configuration when a custom repository bean is present; operators may think YAML controls the IdP while the custom bean is actually active. Pick one configuration source and verify issuer/endpoints after startup.

**Exercise 7.** The browser shows no GET request to the IdP metadata in the Network tab, even though login succeeds. Was the metadata step skipped?

**Answer:** no. The SP server likely loaded metadata at startup or via file/classpath. The browser is not responsible for fetching all metadata; front-channel login is separate from backend configuration loading.

**Exercise 8.** An SP just loaded a new metadata file after the IdP announced a cert rollover. What minimum checks are required?

**Answer:** source/issuer/SSO/cert metadata vetted; SP registration accurate; SP signing/ACS unaltered; login tests pass with valid SAMLResponses while invalid signatures/issuers are rejected; all pods/versions run the same snapshot.

## 20. Metadata Source Decision Checklist

- [ ] Verified the partner and exact **IdP** entity ID, not confusing it with SP metadata.
- [ ] Document contains required SSO endpoints/bindings and verification certificates, valid SAML 2.0.
- [ ] Process exists to verify source and metadata signature/trust anchor per policy.
- [ ] If classpath: XML resides in JAR/classpath with an auditable release/version.
- [ ] If file: absolute path, mounts/permissions, and update procedure tested in the runtime environment.
- [ ] If HTTPS: endpoint allow-listed, valid TLS, redirects/SSRF/network timeouts controlled.
- [ ] Arbitrary metadata URLs from unapproved clients are never used to establish trust.
- [ ] `registrationId` is fixed, not conflated with the IdP's `entityID`.
- [ ] Explicitly chose either **Boot property auto-configuration** or a **custom repository bean**.
- [ ] Plan exists for cache/expiry/reload and handling signing certificate rollover.
- [ ] Raw SAML assertions, cookies, private keys, or sensitive identity data are never logged.
- [ ] Tested build, startup, redirect to exact IdP, ACS callback, and signature/issuer/audience/timestamp checks.
- [ ] Rollback prepared in case new metadata fails or the IdP endpoint becomes unreachable.

## 21. Key Takeaways

**Classpath** is a metadata snapshot packaged with the application; **file** is a metadata snapshot on the runtime filesystem; **HTTPS** is metadata from an IdP endpoint that must be vetted and managed as a trust source. All three flow into the same Spring Security API:

~~~java
RelyingPartyRegistrations.fromMetadataLocation(location)
        .registrationId("corp")
        .build();
~~~

This configuration is meaningful only when the metadata belongs to **the right partner**, certificates are handled trustworthily, and lifecycle management prevents the app from retaining expired metadata. A user is considered logged in only after Spring Security successfully validates the **SAML Response/Assertion**, not merely because metadata loaded.

### References

- Spring Security — SAML 2.0 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security — SAML 2.0 Metadata, signature verification, and repository refresh: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Security API — `RelyingPartyRegistrations` (supports classpath/file/HTTPS): https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/registration/RelyingPartyRegistrations.html
- Spring Security — SAML 2.0 AuthnRequests and SSO metadata: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Boot — SAML 2.0 Single Logout configuration illustrating `assertingparty.metadata-uri`: https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html
- OASIS — SAML 2.0 Metadata for the OASIS Security Assertion Markup Language: https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf
