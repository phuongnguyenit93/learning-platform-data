# Setting Up `spring-security-saml2-service-provider` and OpenSAML Dependencies

## 1. Problem Statement: Adding SAML 2.0 Capability to a Spring Application

In a **SAML 2.0 federation** system, the Spring application acts as a **Service Provider (SP)**, which Spring Security also calls a **Relying Party (RP)**. An independent identity system (Identity Provider, IdP; also called an Asserting Party, AP, in Spring Security docs) authenticates users and sends a `SAMLResponse` back to the application. The SP must validate the SAML message against trust configuration before creating an `Authentication` and application session.

To enable this flow in a Spring Boot application, two distinct setup layers are needed:

1. **Libraries and build:** declare the `org.springframework.security:spring-security-saml2-service-provider` module, compatible OpenSAML dependency versions, and a repository that can resolve the artifacts.
2. **Federation configuration:** declare IdP metadata, SSO endpoints, signature verification certificates, SP identifier, ACS, and signing/decryption credentials if required by the IdP; configure an appropriate servlet security chain.

**Installing dependencies successfully does not mean SSO is already working.** A passing build only proves the JARs are present. Complete login also requires a real IdP, an established trust relationship, and a working callback route.

After this lesson, you will know how to add dependencies with Gradle/Maven, explain OpenSAML's role, inspect the dependency tree, configure the IdP, verify endpoints, and troubleshoot common errors. Examples target **Spring Boot 3.x / Spring Security 6.x, Java 17 or higher, Servlet/MVC**. If using a different Spring Boot/Spring Security version, check the matching version's documentation before copying configuration.

## 2. Placing the Right Modules into the Architecture

| Component | Role | Must Declare Manually? |
| --- | --- | --- |
| `spring-boot-starter-web` | Servlet/MVC application, HTTP endpoints, and servlet container | Yes in the web MVC example |
| `spring-boot-starter-security` | Spring Security and core filter chain components | Yes in the example |
| `spring-security-saml2-service-provider` | SAML 2.0 SP integration into Spring Security; request/response, provider, registration, and authentication | **Primary dependency to add** |
| OpenSAML (`org.opensaml:...`) | SAML/XML processing, SAML objects, serialization/parsing, signatures, and related standard functions | **Usually resolved transitively** from the SAML module |
| Shibboleth Releases Maven repository | Distribution source required for OpenSAML artifacts per Spring Security docs | Must be declared in repository management when artifacts cannot be fetched from existing sources |
| `RelyingPartyRegistrationRepository` | Holds SP–IdP configuration pairs | Spring Boot can auto-create from properties; can provide a custom bean |
| `SecurityFilterChain` | Defines which endpoints are protected and enables `saml2Login` | Spring Boot auto-configures when appropriate; can declare a custom bean |

`spring-security-saml2-service-provider` is a **Spring Security Servlet SP**, not a standalone library to turn an application into an IdP, nor an OAuth/OIDC protocol client. In a pure Reactive Spring WebFlux application, the Servlet filters/endpoints in this example do not apply out of the box.

### Conceptual Dependency Flow

~~~text
Spring Boot Servlet application
    +-- spring-boot-starter-web
    +-- spring-boot-starter-security
    +-- spring-security-saml2-service-provider
          +-- Spring Security SAML integration
          +-- OpenSAML modules (resolved transitively)
                +-- SAML/XML processing and crypto dependencies

Runtime:
Browser -> Spring SP -> IdP
Browser <- IdP -> POST SAMLResponse -> Spring SP
                                  -> verify -> Authentication
~~~

This is a conceptual diagram, **not a copy of an actual resolved dependency tree**; sub-modules and exact versions vary by release. Use `dependencies`/`dependency:tree` commands to inspect your project's real dependency graph.

## 3. Before Adding the Libraries

Identify four pieces of information:

- **Managed Spring Boot and Spring Security versions:** if the project uses Spring Boot dependency management/BOM, let the BOM determine the Spring Security version. Do not pin a different Spring Security version solely for the SAML module.
- **Build system:** Gradle Groovy DSL, Kotlin DSL, or Maven; repositories may be declared at the application level or settings/parent level.
- **Runtime environment:** JDK compatible with the Spring Boot line in use; this lesson uses Java 17+ and the Servlet stack.
- **IdP details:** XML metadata or trusted metadata URL, `entityID`, SSO binding/location, public signing certificate, `AuthnRequest` signing requirements, and the ACS URL registered at the IdP.

You can complete the **build** setup before receiving metadata, though you cannot yet confirm runtime SSO works. Use a consistent `registrationId` throughout the example; here we choose `corp`.

## 4. Gradle Groovy DSL: Adding Dependencies Properly

In a Spring Boot 3.x project **that already has the Spring Boot plugin and compatible dependency management**, add to `build.gradle`:

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

This is a **configuration snippet inside an existing Boot Gradle build**, not a complete standalone `build.gradle`. Plugins, project group, version, and other repository settings stay per your project.

Explanation:

- `implementation` makes the library available at compile and runtime. Placing the SAML module in `testImplementation` or `compileOnly` will fail to support login at runtime.
- Do not write a `version` right after `spring-security-saml2-service-provider` when the Spring Boot BOM already manages versions. If using Gradle **without a BOM/management plugin**, declare compatible versions under a unified plan instead of copying arbitrary version numbers.
- OpenSAML is usually pulled in transitively by the primary dependency. **Do not manually declare every `org.opensaml` module and version without a clear reason**; doing so easily creates conflicting versions.
- Repository `https://build.shibboleth.net/maven/releases/` is the Shibboleth releases URL documented by Spring Security for Maven. Some older Gradle pages/examples use URLs like `/nexus/content/repositories/releases/`; verify the URL approved by your organization and matching documentation version rather than adding unverified repositories in bulk.

### When the Project Manages Repositories Centrally in `settings.gradle`

Many multi-module Gradle projects place repositories in `dependencyResolutionManagement` and enforce `RepositoriesMode.FAIL_ON_PROJECT_REPOS`. In that case, place the repository in **settings**, not in individual `build.gradle` files:

~~~groovy
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        mavenCentral()
        maven {
            url = uri("https://build.shibboleth.net/maven/releases/")
        }
    }
}
~~~

This snippet is an illustrative addition to an existing `settings.gradle`. Preserve your organization's repository policies, especially when using mirrors/Nexus/Artifactory. In multi-module Gradle builds, add the dependency **to the SP application module that needs it**, not necessarily to the root or every sub-library.

### Kotlin DSL (`build.gradle.kts`)

If the project uses Kotlin DSL, the equivalent form is:

~~~kotlin
repositories {
    mavenCentral()
    maven {
        url = uri("https://build.shibboleth.net/maven/releases/")
    }
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.security:spring-security-saml2-service-provider")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Do not mix Groovy syntax `implementation '...'` into `.kts`. When repositories are already managed in settings, only add dependencies in the module; do not create duplicate repository declarations.

## 5. Maven: Dependencies and Artifact Sources

For a Maven project using the Spring Boot parent or importing a compatible BOM, the required section in `pom.xml` looks like:

~~~xml
<repositories>
    <repository>
        <id>shibboleth-releases</id>
        <url>https://build.shibboleth.net/maven/releases/</url>
        <releases>
            <enabled>true</enabled>
        </releases>
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
~~~

This is an **XML snippet to insert inside the `<project>` element of a valid POM**; it is not a full POM. If the parent `pom.xml` already manages Spring Security, child POMs only declare `artifactId` without pinning a separate version. If your organization uses mirrors, repository access policies, or dependency allow-lists, follow your corporate Maven `settings.xml` configuration.

Do not confuse two artifacts:
- **Correct for modern Spring Security:** `org.springframework.security:spring-security-saml2-service-provider`.
- **Legacy Spring Security SAML Extension:** `org.springframework.security.extensions:spring-security-saml2-core`. That is the old generation with different APIs/configuration; do not use it as a substitute for the modern module.

## 6. Where Does OpenSAML Come From and What Does It Do?

OpenSAML is the underlying SAML/XML technical implementation library used by Spring Security. At the application programming level, you typically work with Spring Security APIs such as `RelyingPartyRegistration`, `Saml2Authentication`, `Saml2AuthenticatedPrincipal`, and `Saml2X509Credential`; Spring Security bridges them to the OpenSAML-based implementation.

OpenSAML's technical responsibilities include:

1. Building, marshalling, and unmarshalling XML objects following the SAML model.
2. Reading `AuthnRequest`, `Response`, `Assertion`, and metadata; handling bindings/encodings within integration components.
3. Supporting XML Signature, XML Encryption, and validating SAML structure/conditions per provider logic.
4. Coordinating with Spring Security to verify responses and produce authentication results.

Why is the Shibboleth repository needed? Not all OpenSAML artifacts required by a Spring Security version can be resolved solely from Maven Central. Spring Security documentation requires adding the Shibboleth releases repository for SAML 2.0 SP. **The repository is a JAR download source, not a login IdP**; at runtime, users are never redirected to this repository.

Some OpenSAML artifacts visible in the dependency graph include `opensaml-saml-api`, `opensaml-saml-impl`, `opensaml-core` or `opensaml-core-api`/`opensaml-core-impl` modules, along with supporting XML security libraries. The exact list depends on the OpenSAML generation and dependency management in use.

### OpenSAML 4 vs OpenSAML 5: Do Not Guess Compatibility

Spring Security 6.x includes implementations named `OpenSaml4...` or `OpenSaml5...` in releases that support both, while newer releases may change the default and drop older ones. Notably, OpenSAML 5 splits certain modules that OpenSAML 4 packaged together (e.g., `opensaml-core` vs `opensaml-core-api` and `opensaml-core-impl`).

| Rule | Action |
| --- | --- |
| Standard app with Boot BOM | Keep the BOM and the default transitive dependencies of SAML SP |
| Want to opt into OpenSAML 5 in a Spring Security version that supports choosing | Follow the exact **OpenSAML Support** guide for your Spring Security version, including exclusions and extra modules |
| Upgrading Spring Security 6 to 7 | Review SAML release notes/migration, check the OpenSAML provider, Java baseline, and dependency graph before upgrading |
| Encountering `NoClassDefFoundError` or `NoSuchMethodError` | Inspect OpenSAML, XML security versions, and the entire dependency graph; suspect conflicts/incompatible versions before editing business logic |
| Project has overridden OpenSAML | Document the rationale, supporting docs, and integration tests; never just change one version string and call it done |

Never add "the latest OpenSAML version" directly to patch resolution errors when Spring Security is managed by a BOM: newer versions can change APIs or module layouts. Also never exclude signature verification libraries just to make the build pass.

## 7. Verifying the Dependency Tree Before Testing Login

In a Gradle project directory with wrapper:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-saml2-service-provider --configuration runtimeClasspath
./gradlew dependencyInsight --dependency opensaml-saml-impl --configuration runtimeClasspath
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency opensaml-saml-impl --configuration runtimeClasspath
~~~

In Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.security
mvn dependency:tree -Dincludes=org.opensaml
~~~

Meaning of these commands:

- `dependencies` displays the resolved graph of the **runtime configuration** (where SAML libraries must be present).
- `dependencyInsight` shows the selected module/version, selection reason, and dependency paths in Gradle. The `--dependency` flag is a filter, not an automatic version fix.
- `dependency:tree` is Maven's equivalent view; `-Dincludes` filtering requires a sufficiently recent dependency plugin for your build environment.
- Look for a consistent Spring Security line and resolved OpenSAML JARs; **there is no single fixed stdout** because Gradle, Maven, OS, BOM, repositories, and project dependencies vary.
- If the build succeeds yet the dependency tree contains multiple incompatible OpenSAML versions, a passing build is insufficient to conclude SAML runtime is safe or working.

When scaling to projects with custom build plugins, some dependencies may be injected via convention plugins/capabilities; inspect the resolved graph of the **actual runtime module**, not just declarations at the root.

## 8. Minimal IdP Metadata Configuration in Spring Boot

Once dependencies resolve, the RP/SP needs to know **which IdP to trust**. The cleanest way is pulling XML metadata from a URL provided by the IdP or from a verified metadata file. Example in `src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              metadata-uri: "https://login.example.org/saml/metadata"
~~~

All `.example.org` hostnames in this lesson are **illustrative addresses**; replace with your real IdP metadata URL upon deployment. This is the ideal setup when IdP metadata includes the issuer, SSO service, and trusted signing certificates needed for integration.

- `corp` is an **application-chosen registrationId** to distinguish the IdP/partner. It appears in initiation and callback URLs.
- `assertingparty.metadata-uri` points to the **IdP's (AP's) metadata**, not the SP metadata published by the application itself.
- Metadata XML typically contains `EntityDescriptor entityID`, `IDPSSODescriptor`, `SingleSignOnService`, and `KeyDescriptor`. Never swap IdP metadata with SP metadata XML.
- Being able to download metadata does not prove it is trustworthy. Source, TLS, metadata signing/distribution, certificates, and governance must be verified per the established relationship with the IdP.
- Never "guess" a `/metadata` URL by appending to a domain: every IdP has its own endpoint structure, and a URL returning an HTML login page is not valid XML metadata.

**Local metadata file option** when you want to control the source and lifecycle:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              metadata-uri: "classpath:saml/corp-idp-metadata.xml"
~~~

Place the corresponding file at `src/main/resources/saml/corp-idp-metadata.xml`. This must be XML metadata **received and verified** from the IdP; never fabricate content without verification. If using a static file, maintain an update procedure when the IdP rotates signing certificates/SSO endpoints; if loading metadata from a URL, understand the exact refresh/caching behavior of your configuration/version.

### When No Metadata URI Is Available

You can supply IdP fields manually (for example when the IdP provides the issuer, SSO URL, and certificate separately):

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              entity-id: "https://login.example.org/saml/issuer"
              singlesignon:
                url: "https://login.example.org/saml/sso"
                binding: "REDIRECT"
                sign-request: false
              verification:
                credentials:
                  - certificate-location: "classpath:saml/idp-signing.crt"
~~~

The snippet above assumes **the IdP accepts unsigned AuthnRequests** to illustrate configuration with a verification certificate; **only use `sign-request: false` when IdP policy/metadata permits it**. The `entity-id` field must match the `Issuer` in responses from the IdP. `certificate-location` holds the **IdP's public X.509 certificate**, used to verify signatures, never a private key. The `REDIRECT` binding and URL must also match the real IdP; an IdP may use POST binding instead. If the IdP requires signed requests, add SP signing credentials instead of disabling checks on the IdP side.

Do not deploy both sample approaches together as two repeated `spring:` YAML blocks that accidentally overwrite each other. Choose either **metadata URI** or **manual metadata** based on your scenario.

## 9. Keys, Certificates, and Credential Types

In federation, each party holds keys and certificates for distinct roles:

| Credential | Who Owns It? | Purpose |
| --- | --- | --- |
| IdP signing certificate, public | Provided by IdP; stored as trusted by SP | SP verifies the signature of SAML Responses/Assertions per profile/policy |
| SP signing private key + X.509 certificate | SP keeps private key, may publish cert | SP signs `AuthnRequest`/messages as required by the IdP |
| SP decryption private key + X.509 certificate | SP keeps private key | SP decrypts assertions/attributes encrypted by the IdP for the SP |
| IdP encryption public certificate, if any | Provided by IdP | SP uses it when sending messages requiring encryption to the IdP |

**Do not conflate** IdP and SP certificates; a "certificate" is generally public, whereas a **private key is secret**. Multiple certificates may exist for key rotation (rollover). Never hardcode private keys in Java code, paste them into a Google Sheet, or commit production secret files to Git.

Example when the IdP requires the SP to sign `AuthnRequest`, added to registration `corp`:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            signing:
              credentials:
                - private-key-location: "file:/run/secrets/saml/rp-signing.key"
                  certificate-location: "file:/run/secrets/saml/rp-signing.crt"
            assertingparty:
              metadata-uri: "https://login.example.org/saml/metadata"
~~~

This is **a complete standalone registration for the signing case**, not a block to concatenate with the other examples. The two `file:/run/secrets/...` paths merely illustrate secrets mounted from the runtime environment; you must supply real files, proper read permissions for the process, and matching key/cert pairs. The private key format usually requires **PKCS#8** readable by Spring Security. If the IdP encrypts assertions for the SP, add **decryption credentials** with the proper key/certificate per separate policy; never automatically reuse the signing key for every purpose.

On the SP side, enforce issuer, audience, recipient/destination, time bounds, replay protection, and response/assertion signatures. Never accept XML merely because it contains an email/name or because Base64 decoding succeeded.

## 10. Writing a `SecurityFilterChain` When Customization Is Needed

Spring Boot can auto-configure SAML beans when dependencies and properties align. If you need to explicitly declare application policy, use a `SecurityFilterChain` for Servlet.

File `src/main/java/com/example/saml/SecurityConfig.java`:

~~~java
package com.example.saml;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .saml2Login(Customizer.withDefaults())
                .saml2Metadata(Customizer.withDefaults())
                .build();
    }
}
~~~

Explanation:

1. `@Configuration` registers configuration; `@Bean SecurityFilterChain` replaces certain security defaults auto-configured by Boot. Do not use `WebSecurityConfigurerAdapter`, as it is a legacy API removed in Spring Security 6.
2. `authorizeHttpRequests` permits the root path and `/error`; remaining resources require authentication.
3. `saml2Login` wires SAML authentication requests, response filters, and providers; registrations from `spring.security.saml2.relyingparty.registration.*` can still be supplied by Boot.
4. `saml2Metadata` **explicitly enables the SP metadata endpoint**; this is useful to supply the SP entity ID/ACS/certificate to the IdP. Do not assume the dependency alone exposes a metadata URL.
5. This class **is not a standalone Java application**: it must reside in a Spring Boot project that is component-scanned, with dependencies, Java 17+, and a valid IdP registration. Do not run `javac SecurityConfig.java` on its own without Spring JARs.

When adding multiple `SecurityFilterChain` beans, understand `securityMatcher` and chain ordering: if the chain handling ACS or AuthnRequest lacks `saml2Login`, login will fail even though the dependency is present. The sample above illustrates a single simple chain for an MVC application.

### Default Endpoints to Recognize

| URL | Method/Role | Related Mechanism |
| --- | --- | --- |
| `/saml2/authenticate/corp` | GET initiating SP-initiated SSO | `Saml2WebSsoAuthenticationRequestFilter` generates `AuthnRequest` |
| `/login/saml2/sso/corp` | POST receiving `SAMLResponse` under common binding | `Saml2WebSsoAuthenticationFilter` delegates to the authentication provider |
| `/saml2/metadata/corp` | GET SP metadata when `saml2Metadata` is enabled | `Saml2MetadataFilter` generates metadata from the registration |
| `/saml2/service-provider-metadata/corp` | SP metadata alias endpoint per supported config | Used for exchanging metadata with the IdP |

Endpoint paths can be customized; `/login/saml2/sso` without `registrationId` may also be supported by the framework via registration lookup mechanisms. Rely on your exact Spring Security version and actual registration. The ACS must be a **public address reachable by the user's browser**, not an internal container hostname.

## 11. An Endpoint to Inspect the Principal After Authentication

To distinguish **a successful login** from **an application that only redirects properly**, you can inspect the principal created by Spring Security. File `src/main/java/com/example/saml/CurrentUserController.java`:

~~~java
package com.example.saml;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.saml2.provider.service.authentication.Saml2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CurrentUserController {

    @GetMapping("/me")
    public String me(@AuthenticationPrincipal Saml2AuthenticatedPrincipal principal) {
        return principal.getName();
    }
}
~~~

In a Boot project with `@SpringBootApplication` in a parent package `com.example` (or `com.example.saml`), this bean is scanned. Accessing `/me` while unauthenticated triggers login via the security chain; **only after SAML Response verification succeeds** does the endpoint receive the principal and return the name. There is no fixed stdout because the name and response values depend on the IdP. In production, return only attributes permitted for display; avoid dumping raw SAML assertions/attributes into HTTP responses or logs.

From `Saml2AuthenticatedPrincipal`, you can read attributes using Spring Security APIs when mapping business permissions. **Attributes issued by an IdP do not automatically equate to `ROLE_ADMIN`**: role mapping/authorization requires explicit policy.

## 12. When You Need to Configure Registration in Java

If metadata does not fit `application.yml` declarations, you can replace it with a `RelyingPartyRegistrationRepository` bean. This is an **alternative to Boot properties**, so you do not need to declare two sources for the same registration simultaneously.

Java example (within a project that already has the related beans and dependencies):

~~~java
package com.example.saml;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;

@Configuration
public class SamlRegistrationConfig {

    @Bean
    RelyingPartyRegistrationRepository relyingPartyRegistrationRepository() {
        RelyingPartyRegistration corp = RelyingPartyRegistrations
                .fromMetadataLocation("classpath:saml/corp-idp-metadata.xml")
                .registrationId("corp")
                .build();

        return new InMemoryRelyingPartyRegistrationRepository(corp);
    }
}
~~~

Prerequisites to run: a valid SAML metadata file must exist at `src/main/resources/saml/corp-idp-metadata.xml`; Spring Boot must load the bean, and the IdP must know the matching SP configuration. This is not a complete program with `main`. `InMemoryRelyingPartyRegistrationRepository` suits a registration set initialized at startup; if you need dynamic configuration, metadata updates, or complex multi-partner management, design an appropriate repository/refresh mechanism and address key rotation.

`RelyingPartyRegistration` contains both **SP-side metadata** (entityId, ACS, signing/decryption credentials) and **IdP-side metadata** (issuer, SSO endpoint, verification certificates). Do not confuse it with OAuth 2.0's Java `ClientRegistration`.

## 13. Exchanging SP–IdP Metadata Before Testing

A minimal configuration only works when both sides hold reciprocal details. Practical sequence:

1. Obtain trusted IdP metadata: issuer/entity ID, SSO URL, binding, and certificates. Verify the exchanged metadata endpoint belongs to the right provider.
2. Configure `registrationId=corp`, dependencies, and metadata for the Spring SP.
3. Determine the **SP entity ID** and **ACS URL** that Spring will generate in the runtime environment. By Spring Security convention, the SP entity ID typically uses `{baseUrl}/saml2/service-provider-metadata/{registrationId}`; the ACS is typically `{baseUrl}/login/saml2/sso/{registrationId}`, where `{baseUrl}` is the real public scheme/host/port. Both can be customized.
4. Register the **exact** SP entity ID and ACS URL at the IdP. Provide SP metadata (if the IdP supports import) and the SP signing certificate when the IdP requires signed AuthnRequests.
5. Verify the IdP allows the right binding/Response Destination/Audience. System clocks must be NTP-synchronized within allowed tolerance.
6. Only then attempt a real login.

For example, if the public system is `https://app.example.org` with registration `corp`, the SP parameter set might look like:

~~~text
SP Entity ID:
https://app.example.org/saml2/service-provider-metadata/corp

SP Assertion Consumer Service (ACS):
https://app.example.org/login/saml2/sso/corp

SP-initiated SSO entry:
https://app.example.org/saml2/authenticate/corp

SP metadata endpoint (if enabled):
https://app.example.org/saml2/metadata/corp
~~~

**Hypothetical addresses are solely to illustrate URL relationships.** In a deployment with a reverse proxy or load balancer, if Spring sees backend `http://localhost:8080` instead of public `https://app.example.org`, metadata/ACS/redirects can break. Configure the proxy, trusted forwarded headers, and canonical URLs per infrastructure; never broadly trust `X-Forwarded-*` from untrusted sources.

## 14. Verifying Setup Layer by Layer

### Layer A — Build Dependencies

Gradle:

~~~bash
./gradlew compileJava
./gradlew dependencyInsight --dependency spring-security-saml2-service-provider --configuration runtimeClasspath
./gradlew dependencyInsight --dependency opensaml-saml-impl --configuration runtimeClasspath
~~~

Maven:

~~~bash
mvn test
mvn dependency:tree -Dincludes=org.opensaml
~~~

If it fails right at `Could not resolve org.opensaml:...`, focus on checking repositories, SSL proxy, mirrors, VPN/corporate policy, artifact coordinates, and versions. Do not tweak IdP settings to fix a build dependency resolution error.

### Layer B — Application Startup

In a Boot project with a valid entrypoint and `application.yml`:

~~~bash
./gradlew bootRun
~~~

Or use your project's standard startup command. If IdP metadata is fetched at startup, the environment must be able to reach that URL and the document must be valid XML. **A successful startup only confirms the app can instantiate beans and initialize config**, not that SAML responses have been validated successfully.

### Layer C — AuthnRequest/Metadata Endpoints

With a local app running on port 8080 and a valid IdP registration:

~~~bash
curl -i "http://localhost:8080/saml2/authenticate/corp"
curl -i "http://localhost:8080/saml2/metadata/corp"
~~~

On the first command, in a normal SP-initiated setup, expect a redirect to the IdP with `SAMLRequest` (and possibly `RelayState`) in `Location`. The second command only applies if you enabled `saml2Metadata`, expecting SP metadata XML; HTTP status codes can differ if routes/security/environment were altered. `curl` will not complete authentication because it holds no IdP session and will not submit a valid `SAMLResponse` on its own.

### Layer D — End-to-End Browser Login

Open a browser in the integration environment, navigate to `/me` or a protected page, and turn on Developer Tools → Network → Preserve log. Observe:

1. The application redirects to the IdP from `/saml2/authenticate/corp`.
2. The IdP authenticates or reuses an existing IdP session.
3. The browser receives a SAML form and **POSTs `SAMLResponse` to the SP's ACS**.
4. Spring Security processes the response with the OpenSAML-based provider and creates the principal; the browser receives an application session.
5. Navigating to `/me` returns the expected principal name.

Also test failure paths: responses with wrong issuer/audience/signature or uncorrelated to a request must be rejected. **You do not need and should not craft fake unsigned SAMLResponses just to force login to succeed**.

## 15. Build, Configuration, and Runtime Errors: Identifying the Right Layer

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `Could not find org.opensaml:...` / `Could not resolve` | Missing Shibboleth releases repository, mirror lacks artifact, network blocked | Verify repository URL, centralized repositories config, proxy policy, and dependency graph |
| `PKIX path building failed` downloading artifacts/metadata | Java does not trust the TLS chain or corporate TLS interception | Check CA truststore/infrastructure; **never disable TLS verification** |
| `NoClassDefFoundError`, `NoSuchMethodError` related to OpenSAML | Mixing OpenSAML 4/5, missing implementation module, XML security/JAR conflict | Run `dependencyInsight`/`dependency:tree`, match versions per Spring Security compatibility |
| Boot does not create SP registration | Wrong YAML key, wrong indentation, missing metadata, or overridden bean | Check `spring.security.saml2.relyingparty.registration.corp.assertingparty` and bean config |
| Startup fails on metadata | URL does not return XML, IdP offline, TLS/redirect issue, incomplete metadata | Verify trusted metadata and reachability at startup; use a verified file when needed |
| `/saml2/authenticate/corp` does not generate request | Wrong registrationId, chain lacks SAML enabled, or custom route conflict | Compare `corp` config, `saml2Login`, servlet chain matcher, and path |
| IdP reports unknown service provider | SP entity ID is unregistered or mismatched | Match exact SP entity ID against IdP configuration |
| IdP reports invalid ACS/Destination/Recipient | ACS/callback differs from declared URL | Check public URL, proxy, HTTPS, port, hostname, path |
| IdP requires signed `AuthnRequest` | SP lacks signing private key/certificate or key mismatch | Configure signing credentials and verify IdP trusts the certificate |
| POST to ACS gets 403 | Mis-scoped filter chain/CSRF config or invalid route | Review SAML endpoints and CSRF config; do not disable CSRF app-wide |
| Missing state/mismatched `InResponseTo` | Lost SP session, cookie blocked on cross-site POST, wrong request repository | Check cookie SameSite/Secure, session, and correlation, especially on POST callbacks |
| `invalid signature` or untrusted cert | Stale IdP cert, wrong metadata, response missing signature per policy | Check XML signing/verified metadata, cert rollover plan; never skip verification |
| `expired`/NotBefore/NotOnOrAfter | Clock skew, expired response, replay | Synchronize clocks, issue fresh request, do not open tolerance infinitely |
| Login succeeds yet `/me` returns 403 | Authorization/authority mapping rules differ from authentication | Inspect `SecurityContext`, principal, and role-mapping policy |
| Library installed yet still sees default login form | Missing IdP registration or misconfigured chain | Review Boot properties/beans and SAML filters before writing manual redirects |

**Quick diagnosis:** if an error happens during dependency resolution, fix **build/repositories/versions**; if startup fails, check **metadata/beans/keys**; if redirect fails, inspect **registration/URLs/chains**; if the browser already POSTed the response and it was rejected, check **signature/issuer/audience/time/correlation/cookies**.

## 16. Distinguishing Four Operations Commonly Conflated

**Adding dependencies** only lets SAML classes compile/load. **Creating a registration** tells the SP which IdP to trust and where to send/receive messages. **Registering the SP on the IdP** establishes reciprocal trust. **Verifying the SAML Response** is the actual moment the application concludes the user is authenticated.

Do not build a custom `@RestController` to accept `SAMLResponse`, Base64-decode the XML, and create a session manually: that bypasses filters/providers, XML signature handling, SAML conditions, and replay checks. Spring Security already has a dedicated pipeline.

Conceptual illustration of components when POSTing to the ACS:

~~~mermaid
flowchart LR
    B[Browser POST SAMLResponse] --> F[Saml2WebSsoAuthenticationFilter]
    F --> R[RelyingPartyRegistration]
    F --> P[OpenSAML authentication provider]
    R --> P
    P --> V[Verify SAML response and assertions]
    V --> A[Authentication + SecurityContext]
    A --> S[Application session / protected endpoint]
~~~

The diagram only outlines major steps; it does not mean every check runs in a single method or every deployment stores sessions identically.

## 17. Security Constraints for Setting Up a SAML SP

- **TLS transport:** production metadata URLs, login, and callback/ACS require HTTPS with trusted certificates; never disable hostname validation.
- **Signatures and trust:** IdP signing certificates must be managed through a trust relationship. Allow multiple certificates during key rollover and remove old certificates on schedule.
- **Private keys:** store in a secret manager or secure mount; grant minimal read permissions. Never expose keys in logs, unit test output, or public files.
- **Replay prevention:** enforce `InResponseTo`, audience restriction, recipient/destination, time bounds, and response ID tracking per provider/config capabilities.
- **Session cookies on cross-site POST:** browsers may withhold `SameSite=Lax` cookies when the IdP POSTs SAMLResponse to the ACS. Choose an appropriate cookie/session and correlation strategy rather than disabling `InResponseTo` verification.
- **CSRF:** the SAML ACS must integrate properly with security filters and scoped CSRF exceptions. Never use `csrf.disable()` globally as a default workaround.
- **Authorization:** identity claims/attributes must be mapped into authorities per policy; successful authentication does not automatically grant admin privileges.
- **Published metadata:** entity ID, ACS, and public certificates may need to be reachable by the IdP; avoid embedding internal data/secrets into SP metadata.
- **Log limits:** never log raw `SAMLResponse`, private keys, or assertions containing personal data; redact before sharing logs/HAR files.
- **Security updates:** follow tested BOMs and Spring Security/OpenSAML update schedules; monitor CVEs and migration steps when changing major versions.

## 18. Practice Exercises with Verification

**Exercise A — diagnosing a dependency error:** a project declares `implementation 'org.springframework.security:spring-security-saml2-service-provider'`, yet Gradle reports it cannot download an `org.opensaml` module. What should be checked first?  
**Answer:** check the module's effective repositories, whether Shibboleth releases (or a mirror carrying the artifacts) is present, whether the URL is reachable, and TLS trust; check dependency versions and the BOM. Do not tweak ACS or IdP settings when the failure occurs at build time.

**Exercise B — distinguishing build from login:** `compileJava` passes and the app starts via `bootRun`, yet the IdP reports "unknown SP". What does this prove and what is missing?  
**Answer:** it proves compilation and startup work; the missing piece is a missing/mismatched SP entity ID or SP configuration on the IdP side. Compare SP metadata, entity ID, and ACS against the IdP-side registration.

**Exercise C — choosing OpenSAML version:** you see `org.opensaml:opensaml-saml-impl` pulled in transitively. Should you add the latest OpenSAML version into `dependencies`?  
**Answer:** do not upgrade it in isolation; check the Spring Security/BOM version and OpenSAML support docs. If migration is needed, apply exclusions, modules, and integration tests per the guide for that exact version.

**Exercise D — reading HTTP traces:** the browser GETs `/saml2/authenticate/corp`, receives a 302 to the IdP, then POSTs `SAMLResponse` to `/login/saml2/sso/corp`; the server returns 401/403. Can you conclude OpenSAML is missing?  
**Answer:** not yet. Because the application already handled the request flow, inspect signature, issuer, audience, destination, expiry, correlation, cookies/session, and the filter chain. A `NoClassDefFoundError` in logs would be concrete evidence of a missing/incompatible library.

**Exercise E — registering parameters:** the IdP asks for the SP entity ID and ACS. For registration `corp` at `https://app.example.org`, determine the values following common convention.  
**Answer:** entity ID is typically `https://app.example.org/saml2/service-provider-metadata/corp`; ACS is typically `https://app.example.org/login/saml2/sso/corp`; verify against actual metadata/config and ensure the reverse proxy produces the right public URL.

## 19. Setup Completion Checklist

- [ ] The application is Spring MVC/Servlet and uses a Spring Boot/Spring Security version compatible with the JDK.
- [ ] The `spring-security-saml2-service-provider` module is declared in the SP app with proper runtime scope.
- [ ] The Shibboleth releases repository or an approved mirror contains the required OpenSAML artifacts.
- [ ] The dependency graph resolves compatible OpenSAML versions without arbitrary overrides.
- [ ] IdP metadata/issuer/SSO URL/verification certificate are verified and configured in the registration.
- [ ] SP signing/decryption credentials are configured if required by protocol/IdP policy, with private keys protected.
- [ ] `SecurityFilterChain` enables `saml2Login`, and the metadata endpoint is enabled if SP metadata must be supplied to the IdP.
- [ ] SP entity ID and public ACS URL match the IdP registration and reverse proxy configuration exactly.
- [ ] Dependency build + app startup + AuthnRequest redirect + SAMLResponse POST + verified principal have all been tested.
- [ ] Cookies, CSRF, session correlation, XML signatures, timestamps, audience, replay, and certificate rotation plan have been evaluated.

## 20. Reference Documentation

The links below are reference resources; when implementing, prioritize the **exact version** matching Spring Security/Spring Boot in your project:

- Spring Security — SAML 2.0 Login Overview, dependencies, registration, default endpoints: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security 6.5 — OpenSAML Support and choosing OpenSAML 4/5: https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/opensaml.html
- Spring Security — SAML 2.0 Metadata: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Security — Producing SAML AuthnRequests: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Boot — Spring Security / SAML 2.0 Relying Party: https://docs.spring.io/spring-boot/reference/web/spring-security.html
- Gradle — Inspecting Dependencies: https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html
- Maven Dependency Plugin — dependency:tree: https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html

**Key takeaway:** `spring-security-saml2-service-provider` is the Spring Security integration point; OpenSAML is the underlying SAML/XML implementation layer; dependency management determines compatible versions; metadata and the IdP–SP trust relationship determine whether real login works.
