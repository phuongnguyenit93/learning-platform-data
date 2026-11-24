# Migrating from Legacy Spring Security SAML Extension to Modern SAML2 Support

## 1. Objectives, Scope, and Architectural Differences

Many enterprise Java applications previously used **Spring Security SAML Extension 1.x** to act as a **SAML 2.0 Service Provider (SP)**. These projects typically have a `spring-security-saml2-core` dependency, an XML configuration `securityContext.xml`, multiple manual filters (`SAMLEntryPoint`, `SAMLProcessingFilter`, `MetadataGeneratorFilter`, `SAMLLogoutFilter`), a `KeyManager` holding JKS, a `MetadataManager` managing IdPs, `ExtendedMetadata`, and mapping code in `SAMLAuthenticationProvider`/`SAMLUserDetailsService`.

Modern Spring Security integrates **SAML2 Login directly into Spring Security Servlet** via the `spring-security-saml2-service-provider` module, configuring `SecurityFilterChain`, `saml2Login()`, `RelyingPartyRegistration`, `RelyingPartyRegistrationRepository`, and an OpenSAML-based provider. Metadata publishing and SAML Single Logout (SLO) capabilities are configured via `saml2Metadata()` and `saml2Logout()` when supported by the version/scenario.

**The goal of upgrading is not just renaming classes until it compiles:** you must **migrate the entire trust model**, metadata, Endpoint URLs, signing/decryption keys, request correlation, sessions, identity/role mapping, SLO, and security checks. A single incorrect `EntityID` or Assertion Consumer Service (ACS) change can cause all partner IdPs to reject logins even when the Java code compiles cleanly.

This lesson belongs to the **Migration and Upgrade** group in the **Spring Security - federation** module. The content focuses on **migrating a SAML2 Service Provider (SP)**; it does **not** cover migrating a custom SAML Identity Provider written with the extension into a new IdP in Spring Security, because the RP/SP capabilities of the modern module are not equivalent to a full IdP server.

**Expected outcomes:**
1. Fully identify legacy components and the actual contract with the IdP.
2. Understand the functional mapping to modern Spring Security SAML2 and recognize that **there is no 1:1 equivalent**.
3. Set up a new SP using a supported Spring Security/Boot version, importing IdP metadata and keys with the proper roles.
4. Preserve or perform controlled migration of `EntityID`, ACS, SLO URLs, NameID, attributes, roles, and sessions.
5. Test security negative cases, interoperability, multi-IdP, reverse proxy, and rollover.
6. Release safely with canary, rollout, rollback, and trust-change auditing.

**Version boundaries:** Spring Security **6.x** documentation contains many `OpenSaml4AuthenticationProvider` examples; the current **7.x** line uses `OpenSaml5AuthenticationProvider` and changes principal/assertion APIs. You must rely on the **actual resolved versions of Spring Security, Spring Boot, and OpenSAML**; do not mix snippets across release lines.

## 2. How Does the Legacy Extension Differ from Modern Support?

| Aspect | Spring Security SAML Extension 1.x | Modern Spring Security SAML2 | Work Required During Migration |
| --- | --- | --- | --- |
| Dependency | `spring-security-saml2-core` and OpenSAML from the extension era | `spring-security-saml2-service-provider` | Replace dependency, manage BOM/transitives |
| Enabling SSO | Multiple filters and entry points added manually | `http.saml2Login(...)` in `SecurityFilterChain` | Clean up legacy filter chain, avoid 2 stacks handling the same callback |
| Start login | `SAMLEntryPoint`, commonly `/saml/login` | `Saml2WebSsoAuthenticationRequestFilter`; default `/saml2/authenticate/{registrationId}` | Migrate entry links and IdP picker |
| ACS | `SAMLProcessingFilter`, commonly `/saml/SSO` | `Saml2WebSsoAuthenticationFilter`; default `/login/saml2/sso/{registrationId}` | Synchronize IdP ACS, proxy, and metadata |
| SP metadata | `MetadataGeneratorFilter`, `MetadataDisplayFilter`, `MetadataGenerator` | `saml2Metadata()` from `RelyingPartyRegistration` | Compare output XML/EntityID/cert/ACS before updating IdP |
| IdP metadata | `MetadataManager`, `ExtendedMetadataDelegate`, file/HTTP providers | `RelyingPartyRegistrations.fromMetadataLocation`/repository | Recreate trust policy, refresh, expiry, and signing keys |
| Extended properties | `ExtendedMetadata`, manual beans | Properties/builders, protocol-specific customization | Reconcile each behavior, do not auto-copy XML |
| Keystore | `KeyManager`, JKS/JCEKS aliases | `Saml2X509Credential` sign/verify/decrypt | Migrate private keys securely, preserve key use |
| Authentication provider | `SAMLAuthenticationProvider` + `WebSSOProfileConsumer` | OpenSAML provider and converters | Preserve signature/audience/recipient/timestamp/replay checks |
| User mapping | `SAMLUserDetailsService`, `SAMLCredential`, custom principal | Verified authentication + attributes/authorities converter or local service | Design subject/tenant/role contract |
| Logout | `SAMLLogoutFilter`, `SAMLLogoutProcessingFilter` | `saml2Logout(...)`, request/response filters | Re-verify RP/AP-initiated SLO and endpoints |
| Multi-IdP | Metadata aliases/discovery and context provider | Multiple `RelyingPartyRegistration`s, custom resolver/picker | Maintain clear `registrationId`, issuer, and tenant mapping |
| Proxy/load balancer | `SAMLContextProviderLB` and server name overrides | `{baseUrl}`, forwarded headers/base URL, metadata config | Verify public Internet host/scheme/path are accurate |
| Binding/profiles | Extension 1.x may support many specialized profiles/bindings | Modern module focuses on SAML Web Browser SSO/SLO | Build a **feature-gap list**, test bindings beyond defaults |

**There is no official automated command like "convert XML config to RelyingPartyRegistration" to guarantee full equivalence.** Spring provides migration documentation describing **patterns**, not a find-and-replace table for all classes.

## 3. Distinguishing Extension 1.x, Spring Security 5/6, and 7

| Project Line | Notes |
| --- | --- |
| **Spring Security SAML Extension 1.x** | Historical extension project; typically XML beans, `org.springframework.security.saml.*`, `OpenSAML 2.x` in older releases |
| **Spring Security 5.x** | SAML SP support was brought into the Spring Security core ecosystem, e.g., `saml2Login` and `RelyingPartyRegistration` |
| **Spring Security 6.x** | Uses modern Servlet `SecurityFilterChain` APIs, Jakarta EE namespaces; some guides use `OpenSaml4AuthenticationProvider` |
| **Spring Security 7.x** | Documentation uses `OpenSaml5AuthenticationProvider`, `Saml2AssertionAuthentication`, and `Saml2ResponseAssertionAccessor`; some older APIs are deprecated |
| **Spring Boot 3/4** | Manages dependency versions and SAML2 auto-config per Boot line; use the Boot-managed BOM rather than assembling libraries manually |

**Verify specifically:** `java -version`, `mvn dependency:tree`/`gradle dependencies`, Spring Boot plugin version, Spring Security BOM, OpenSAML versions, and Java Servlet imports. Upgrading from Boot 2.x to Boot 3/4 also involves **`javax.servlet.*` → `jakarta.servlet.*`**, not just SAML. Avoid importing `javax` from the legacy extension into Spring 6/7.

Not every application should do a "big bang" upgrade of Boot, Java, SAML, DB, and reverse proxy on the same day. Separate changes, run canary deployments, and keep a safe fallback when business SLAs permit.

## 4. Step 0: Inventory All Legacy Behaviors Before Changing Code

An **inventory** should record, for each IdP partner:

| Component/Value to Collect | Why Is It Important? |
| --- | --- |
| **SP EntityID** | Used by the IdP as audience/identifier; changing it may require reconfiguration on the partner side |
| **IdP EntityID/Issuer** | Selects the right trusted source; multiple partners may share the same usernames |
| **SSO endpoint URL, binding** | Browser redirect/POST must reach the right IdP |
| **ACS URL, binding, index** | The IdP POSTs SAMLResponse to the registered destination |
| **SingleLogoutService URLs and binding** | RP/AP-initiated logout, request/response handling |
| **Signing rules** | Whether the Response or Assertion is signed, and whether AuthnRequest must be signed |
| **IdP verification certificates** | Used to verify signatures; distinct from the SP signing private key |
| **SP encryption/decryption keys** | Enables EncryptedAssertion/EncryptedAttribute/EncryptedID |
| **NameIDFormat and subject identity key** | Defines local-account linking, not just displayName/email |
| **Attribute Name/NameFormat, cardinality** | Group/role/tenant/email mapping; values may be multi-valued |
| **RequestedAuthnContext/forceAuthn/passive/scoping** | IdP policy, MFA assurance, step-up behavior |
| **SP-initiated/IdP-initiated SSO** | Different correlation/InResponseTo/RelayState policies |
| **Session timeout/cookie/SameSite** | Cross-site POST to ACS can lose session state if cookie policy is wrong |
| **AuthnRequest repository/RelayState** | Needed to preserve request correlation across a cluster |
| **Metadata refresh/expiry and trust policy** | Rotation, issuer/cert trust, startup when IdP is offline |
| **Multi-IdP discovery/entityAlias** | Login URL and tenant selection/registration resolution |
| **Legacy Artifact/ECP/SOAP/PAOS support** | May lack a direct replacement; requires gap assessment |
| **Logging/audit/error handlers** | Do not lose authentication/authorization auditing when swapping filters |
| **Load balancer/proxy/forwarded headers** | Generates accurate public scheme/host in ACS/metadata |
| **Operations keys/secret management** | HSM/JKS, alias/password, key lifecycle, rotation, and read permissions |
| **Partner contact, approval, and rollback** | IdP must update metadata/certs in a controlled manner |

**Inventory sources** can include XML security context files, `web.xml`, current IdP/SP metadata, the IdP management UI, deployment secrets, and E2E traces using test identities. **Do not include production SAMLResponses, raw NameIDs, private keys, or keystore passwords in the inventory document**; record only fingerprints/versions and approved references.

### Example Legacy Extension Configuration to Identify

~~~xml
<!-- HISTORICAL structure, only for identifying in legacy projects. -->
<security:http entry-point-ref="samlEntryPoint">
  <security:custom-filter before="FIRST"
                          ref="metadataGeneratorFilter"/>
  <security:custom-filter after="BASIC_AUTH_FILTER"
                          ref="samlFilter"/>
</security:http>
~~~

The `samlFilter` bean often groups multiple servlet filters, and `samlEntryPoint` initiates SSO. **Do not place these legacy filters in the same new filter chain** with the same ACS to "run in parallel" on a single endpoint; the result can be double parsing, session state contention, and faulty authentication flows.

## 5. Designing the Target State

A modern Spring Security SAML2 RP/SP application typically consists of:

~~~mermaid
flowchart TD
    U[Browser] --> F[Spring SecurityFilterChain]
    F --> R[SSO request filter]
    R --> IDP[Trusted IdP]
    IDP --> ACS[SAML Response POST to ACS]
    ACS --> P[Saml2WebSsoAuthenticationFilter]
    P --> T[RelyingPartyRegistrationRepository]
    P --> A[OpenSAML authentication provider]
    A --> V[Signature / issuer / audience / time / recipient]
    V --> M[Verified NameID and attributes]
    M --> L[Local identity and authority mapper]
    L --> X[Spring SecurityContext / application session]
    X --> B[Business authorization and tenant policy]
~~~

Where:
- `SecurityFilterChain` defines endpoint authorization and enables SAML2.
- `RelyingPartyRegistration` represents **a single SP–IdP relationship**; an application can have multiple registrations.
- `RelyingPartyRegistrationRepository` looks up a registration by `registrationId` or a custom strategy.
- `Saml2X509Credential` represents certificates/keys by **key use** (signing, decryption, verification).
- The OpenSAML provider handles signature/decryption/protocol validation before creating an authenticated object.
- The application local mapper does not manually decode raw `SAMLResponse`s or bypass the provider.

**Note:** Multiple IdPs may represent organizations/tenants, but the business domain "tenant" still requires separate verification. Do not map an arbitrary browser-supplied `registrationId` into tenant access rights.

## 6. Dependencies: Remove the Extension, Add the Service Provider Module

### Maven with Spring Boot BOM

~~~xml
<!-- In pom.xml where Spring Boot/Spring Security version is already managed. -->
<dependency>
  <groupId>org.springframework.security</groupId>
  <artifactId>spring-security-saml2-service-provider</artifactId>
</dependency>
~~~

### Gradle

~~~groovy
repositories {
    mavenCentral()
    // OpenSAML artifacts may require adding the Shibboleth repository.
    maven {
        url = uri("https://build.shibboleth.net/maven/releases")
    }
}

dependencies {
    implementation("org.springframework.security:spring-security-saml2-service-provider")
}
~~~

If using Spring Boot with a BOM, **do not pin a SAML module version different from the resolved Security line**. Per Spring Boot docs, OpenSAML may require the **Shibboleth Maven Releases repository**; verify the actual required repository per version and organization, and do not enable arbitrary insecure repositories.

### Legacy Dependencies to Remove or Isolate

~~~text
org.springframework.security.extensions:spring-security-saml2-core
org.opensaml:*                         (versions from the legacy extension)
org.apache.xml.security:*              (incompatible overrides)
commons-logging / servlet javax.*      (depending on specific dependencies)
custom SAMLProcessingFilter and WebSSOProfileConsumer subclasses
~~~

The exact coordinates/versions of legacy artifacts depend on the system. **Do not blindly delete an XML security library still used by another module**; run the dependency tree and check for classpath clashes before removing.

Verification commands:

~~~bash
mvn dependency:tree
mvn -DskipTests=false test

# If using Gradle:
./gradlew dependencies --configuration runtimeClasspath
./gradlew test
~~~

If the Maven surefire plugin or Gradle build uses different logic, choose the corresponding commands; these examples are illustrative only. **Do not put production keystores/secrets into CI** just to "make tests pass."

## 7. Minimal Modern Spring Boot Configuration Using IdP Metadata

Spring Boot can auto-configure `RelyingPartyRegistrationRepository` from properties:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              metadata-uri: "https://idp.example/metadata"
~~~

This value is a **placeholder IdP metadata URL**; a real application requires the IdP to have provided metadata, proper HTTPS trust, and entity registration approved by the IdP. The name `assertingparty` is the schema in current Boot lines; if a project uses an older Boot line, you may see `identityprovider` in historical documentation. **Check the configuration metadata of your actual Boot version** before copying.

Spring Security Boot auto-config can generate the registration and filter chain when dependencies/properties are complete, but when you define your own `SecurityFilterChain`, you must **enable `saml2Login()` in the chain serving the callback**, rather than assuming auto-config still adds all filters.

**Startup metadata URL caveat:** If the builder/runtime fetches metadata from the IdP at startup and the IdP endpoint is offline, the app may fail to start. For systems requiring offline boot, consider an approved metadata file/config revision and a version-appropriate retry/cache/hot-reload strategy; do not disable TLS verification or accept unsigned metadata from untrusted URLs.

## 8. Modern JavaConfig: Single SP–IdP Relationship

Example **Spring Security project fragment** for an SP, using Java 17+ but **requiring Spring Security/Boot dependencies**; it does not run with plain `javac`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.registration
        .InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration
        .RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration
        .RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration
        .RelyingPartyRegistrations;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class Saml2SpSecurityConfiguration {

    @Bean
    RelyingPartyRegistrationRepository relyingParties() {
        RelyingPartyRegistration rp =
                RelyingPartyRegistrations
                    .fromMetadataLocation("https://idp.example/metadata")
                    .registrationId("corp")
                    .entityId("https://reports.example/saml2/sp/corp")
                    .assertionConsumerServiceLocation(
                        "https://reports.example/login/saml2/sso/corp")
                    .build();

        return new InMemoryRelyingPartyRegistrationRepository(rp);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                    .requestMatchers("/health").permitAll()
                    .anyRequest().authenticated())
                .saml2Login(Customizer.withDefaults())
                .saml2Metadata(Customizer.withDefaults())
                .build();
    }
}
~~~

**Important notes:**
- `https://idp.example/metadata`, `https://reports.example/...`, and `corp` are **illustrative** values and must be replaced with parameters approved by the IdP.
- `entityId(...)` and `assertionConsumerServiceLocation(...)` are **set explicitly**. If you want to keep the legacy `EntityID`/ACS, use the verified legacy values, but **the legacy ACS differs from the default filter URL**; you must configure the corresponding callback resolver/filter (Section 10). Do not just change a single metadata line.
- `RelyingPartyRegistrations.fromMetadataLocation` parses **IdP metadata**; signature, issuer trust, HTTPS, expiry, and rollover require operational policies.
- `saml2Metadata()` publishes SP metadata from the registration; it **does not replace `saml2Login()`**.
- Do not enable `saml2Logout()` in the minimal example unless signing keys, SLO endpoints, and IdP support are provided and verified; Section 15 covers this separately.
- If the IdP requires signed AuthnRequests or encrypts Assertions, **you must add SP credentials** with the appropriate roles.
- If the app also has Basic/JWT/OIDC APIs, design multiple filter chains/request matchers so the SAML chain does not accidentally intercept the entire system.

This pattern avoids writing `MetadataGeneratorFilter` or `SAMLProcessingFilter` manually. Identity/role mapping configuration happens after provider validation; never construct an Authentication from unverified XML.

## 9. Legacy-to-New Endpoint Mapping

The paths below are **common patterns**; do not assume every extension app used the exact same URLs.

| Function | Typical Legacy URL | Spring Security SAML2 Default | Migration Requirement |
| --- | --- | --- | --- |
| Start SP-initiated login | `/saml/login` | `/saml2/authenticate/{registrationId}` | Update links/UI/entry point/IdP picker |
| ACS receiving SAMLResponse | `/saml/SSO` | `/login/saml2/sso/{registrationId}` | Update IdP ACS/metadata or add custom processing URL |
| SP metadata | `/saml/metadata` | `/saml2/metadata` and `/saml2/metadata/{registrationId}` | Re-register metadata URL/EntityID |
| SP metadata alias | URL depending on extension/alias | `/saml2/service-provider-metadata/{registrationId}` | Compare metadata payload, do not guess |
| Inbound/outbound SLO | `/saml/SingleLogout` or variant | `/logout/saml2/slo` | Configure logout request/response matchers and metadata |
| Local logout | App `/logout` per config | `POST /logout` per Spring config | Do not confuse local logout with global SLO |

**Common mistake:** The IdP keeps POSTing to `/saml/SSO` while Spring only listens on `/login/saml2/sso/corp`. HTTP 404/403 or a redirect loop can occur even when signature keys are correct. You must verify the **effective external URL** (scheme, host, port, context path, reverse-proxy rewrite) and the ACS value in the metadata that the IdP is **actually using**.

### Should You Keep the Legacy URLs?

There are two practical options:

**A. Switch to the new defaults:** Simpler and easier to maintain; requires the IdP to update metadata/ACS, updating bookmarks/SSO links, and testing alongside partner configuration changes.

**B. Keep legacy URLs temporarily:** Reduces IdP-side changes for a phase, but you must **align simultaneously**:
- `RelyingPartyRegistration.assertionConsumerServiceLocation`.
- `http.saml2Login(saml2 -> saml2.loginProcessingUrl(...))`.
- Logic to determine the right registration if the URL does not contain `{registrationId}`.
- Proxy routes/CSRF/Cookie/SameSite and actual SAML binding.
- IdP metadata and the exact registered ACS.

**Do not just edit the ACS in metadata** and expect the filter to automatically listen on that URL. Conversely, do not just change the filter path while forgetting the registered partner metadata.

## 10. Customizing ACS When Maintaining Legacy Paths

The Spring reference notes that you can change the URL where `Saml2WebSsoAuthenticationFilter` processes `SAMLResponse` using `saml2Login().loginProcessingUrl(...)`.

Example fragment:

~~~java
@Bean
SecurityFilterChain legacyAcsCompatibility(HttpSecurity http)
        throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .saml2Login(saml2 -> saml2
                .loginProcessingUrl("/saml/SSO"))
            .build();
}
~~~

**Illustrative configuration only:** When the ACS does not contain `{registrationId}` and there are multiple IdPs/tenants, ensure `RelyingPartyRegistration` is resolved from **a trusted source** via an `AuthenticationConverter`/resolver, validated correlation state, or issuer matching. Do not rely on a browser-appended `registrationId` to decide trust or automatically pick "the first IdP."

You must declare the same external ACS URL in the registration and on the IdP. Use staging tests with two IdPs to confirm it never selects the wrong signing key/audience.

### Do Not Arbitrarily Accept SAMLResponse via HTTP GET

Web Browser SSO SAMLResponse normally travels via **HTTP POST binding** to the ACS. Per Spring Security 7.x migration docs, converters are tightening how SAML Response GET requests are handled in subsequent versions. **Do not use a GET response payload as a legacy compatibility shortcut without an official standard/binding**, and do not disable signature/protocol checks to accept URL-based responses.

**RelayState** can carry opaque correlation state; never use raw RelayState as an open redirect or to hold sensitive tokens.

## 11. Metadata: From MetadataGenerator to saml2Metadata()

The legacy extension typically instantiated `MetadataGenerator`, `MetadataGeneratorFilter`, `MetadataDisplayFilter`, and managed `entityAlias`/keystore.

Modern Spring Security:

~~~java
http.saml2Login(Customizer.withDefaults());
http.saml2Metadata(Customizer.withDefaults());
~~~

Per current metadata documentation, endpoints typically include:

~~~text
GET /saml2/metadata
GET /saml2/metadata/{registrationId}
GET /saml2/service-provider-metadata/{registrationId}
~~~

**Important:** New metadata can differ from legacy metadata even with the same app name. Before handing it to the IdP:

- Compare `EntityDescriptor.entityID` **byte-for-byte/exact URI** against partner registration.
- Compare `SPSSODescriptor`, `AssertionConsumerService Location`, Binding, and index/default.
- Compare public signing/encryption certificates and `KeyDescriptor use`.
- Compare `SingleLogoutService Location` and supported bindings.
- Compare `NameIDFormat`, `AuthnRequestsSigned`, and `WantAssertionsSigned` against the contract.
- Compare hostname/port/scheme/path through the load balancer and `{baseUrl}`.
- Check IdP metadata cache: "new SP metadata is published" **does not mean the IdP has imported/applied it**.

**Do not copy legacy metadata XML to the new endpoint while ignoring `RelyingPartyRegistration`**: runtime checks/ACS/EntityID must remain consistent with published metadata. If the system uses signed metadata, determine how it is signed and where it is validated on both sides.

### New Metadata Does Not Need the Entire Legacy Management Suite

Do not put `MetadataGeneratorFilter`, `MetadataManager`, or `ExtendedMetadata` from the extension onto the classpath just to serve `/saml/metadata`. The modern release provides `saml2Metadata` and the repository; if custom metadata is needed, use the supported resolver/customization API for your version instead of mixing legacy filters into the new security chain.

## 12. Keys and X.509: KeyManager Cannot Be Ported "As-Is"

The legacy `KeyManager` could read JKS aliases containing SP private keys, SP signing certificates, and IdP verification material. Spring SAML2 uses **`Saml2X509Credential`** categorized by purpose:

| Purpose | Who Owns the Private Key? | How Do IdP/SP Use It? |
| --- | --- | --- |
| **IdP signing** | IdP | SP uses **public cert** with `Saml2X509Credential.verification(cert)` |
| **SP AuthnRequest signing** | SP | SP uses **private key** with `Saml2X509Credential.signing(privateKey,cert)`; IdP verifies public cert |
| **SP Assertion decryption** | SP | IdP encrypts with public SP cert; SP uses `Saml2X509Credential.decryption(privateKey,cert)` |
| **TLS certificate** | Respective server | Protects HTTPS; not by default the SAML XML signing key |
| **IdP metadata signature** | Metadata issuer/owner | Has its own trust policy/verification; not by default the same key as assertions |

JavaConfig fragment to add SP credentials:

~~~java
import java.security.interfaces.RSAPrivateKey;
import java.security.cert.X509Certificate;
import org.springframework.security.saml2.core.Saml2X509Credential;
import org.springframework.security.saml2.provider.service.registration
        .RelyingPartyRegistration;

RelyingPartyRegistration withSpKeys(
        RelyingPartyRegistration.Builder builder,
        RSAPrivateKey signingKey,
        X509Certificate signingCert,
        RSAPrivateKey decryptionKey,
        X509Certificate encryptionCert) {

    Saml2X509Credential signing =
            Saml2X509Credential.signing(signingKey, signingCert);
    Saml2X509Credential decryption =
            Saml2X509Credential.decryption(decryptionKey, encryptionCert);

    return builder
            .signingX509Credentials(keys -> keys.add(signing))
            .decryptionX509Credentials(keys -> keys.add(decryption))
            .build();
}
~~~

**This is a fragment inside a project with dependencies**, not a standalone runnable program. `signingKey`, `decryptionKey`, and certificates come from a controlled secret manager/keystore loader; the code does not load PEM in the example. When migrating from JKS:
- Check which alias serves **SP signing** and which serves decryption.
- If converting key formats, verify **PKCS#8 private key**, algorithm, certificate chain, and keypair match.
- Keep private keys out of Git/container images/logs/test reports.
- Do not accidentally export an **IdP private signing key** to the SP (the IdP only provides its verification public cert).
- Review support for RSA/ECDSA algorithms, XML Signature/Encryption, and key transport against the IdP/OpenSAML baseline.
- Plan for old/new verification/decryption key **overlap** during rotation; do not remove keys while messages are still in flight.
- If the IdP mandates signed AuthnRequests, add SP signing credentials before rollout; do not weaken IdP signing requirements just to "get it working."

**Never use a trust-all certificate verifier** or skip XML signature checks when encountering compatibility errors.

## 13. IdP Metadata, Trust Anchors, and Rollover

A `RelyingPartyRegistration` contains **Asserting Party** information: entity ID, SSO/SLO URLs, verification credentials, and preferences. Loading metadata from a URL is not enough to establish a trust boundary without defining **who controls the URL, which certificates are trusted, how metadata is signed/verified, and when it is updated**.

Process:
1. The IAM team confirms the IdP EntityID and metadata endpoint through official channels.
2. Verify HTTPS/PKIX/hostname or metadata signature per policy.
3. Record the fingerprint/trust revision in approved configuration.
4. Import/test in staging before creating the production registration.
5. When the IdP publishes a new signing cert, compare old/new `KeyDescriptor`s and activation times.
6. Ensure all Spring nodes share the same approved trust set or follow a versioned rollout.
7. Audit `PARTNER_CONFIG_PROPOSED → APPROVED → ACTIVATED` and rollback if needed.
8. Test signed assertions with both old and new certs according to the overlap policy.
9. Do not rely on an `InMemoryRelyingPartyRegistrationRepository` created at startup if dynamic refresh is required; verify the cache/repository refresh mechanism per version.

**Difference from legacy:** Automatic metadata reloading from `FilesystemMetadataProvider`/`HTTPMetadataProvider`/`CachingMetadataManager` does not automatically appear when you call `fromMetadataLocation`. A repository initialized from metadata at startup may hold a snapshot; if hot refresh is required, you must proactively design the repository/caching/periodic reload along with concurrency and rollback handling.

## 14. Identity, NameID, and Authority Mapping During Upgrade

SAML Identity may be based on `NameID` with a format (persistent/transient/emailAddress), issuer, registration, or an attribute with a stable contract. Legacy code typically received `SAMLCredential` and invoked a `SAMLUserDetailsService`. Modern Spring SAML2 places provider results into `Authentication` along with attributes/authorities.

**Do not default to email as the local account key** when migrating: email can change or be reassigned; transient NameID formats change per login; multiple IdPs can emit identical string `NameID`s. Define a **stable identity key** based on trusted IdP/issuer + a sufficiently stable subject identifier, along with tenant/account-linking approval.

| Legacy Behavior | Target Behavior to Test |
| --- | --- |
| Reading `SAMLCredential.getNameID()` | Reading verified principal/subject from the version-appropriate SAML provider |
| `SAMLUserDetailsService.loadUserBySAML(...)` | Custom response converter/delegated account lookup or post-auth local mapping |
| `SAMLCredential.getAttributeAsString(...)` | Verified attribute contract from principal/assertion accessor, handling lists and types |
| Using roles from raw groups | Exact allowlist from trusted groups → app `GrantedAuthority` |
| Auto-assigning `ROLE_USER` or default admin | Distinguishing framework default authority from business authorization |
| Linking accounts by username/email | Linking by stable subject/issuer/registration and checking migration consistency |
| Attribute namespace/NameFormat | Testing the exact `Attribute Name`, not trusting arbitrary `FriendlyName` |

### SAML AttributeValue Can Be Multi-Valued

~~~xml
<saml:Attribute
  Name="urn:example:claims:groups"
  xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
  <saml:AttributeValue>APP_REPORT_VIEWERS</saml:AttributeValue>
  <saml:AttributeValue>FINANCE_EMPLOYEES</saml:AttributeValue>
</saml:Attribute>
~~~

An IdP can emit **0..N** `AttributeValue` elements and non-String data types. **Do not split on commas automatically** unless the IdP contract specifies a delimited value. Do not call `getFirstAttribute("groups")` if you need to evaluate all groups. A `Domain Admins` value from AD/IdP must not automatically become app `ROLE_ADMIN`.

### Differences in Spring Security 6/7 Principals

- In Spring 6 many applications use `Saml2AuthenticatedPrincipal` and `getFirstAttribute`/`getAttribute`.
- Spring 7 migration documentation marks `Saml2AuthenticatedPrincipal` deprecated, moving assertion details to `Saml2ResponseAssertionAccessor` attached to the credential in the default flow.
- Spring 7 has `Saml2AssertionAuthentication` and a response conversion API different from legacy `SAMLCredential`.
- Do not cast `Authentication.getPrincipal()` to old classes once upgraded to a new version or when the app uses multiple authentication mechanisms.
- When customizing a converter, **delegate default validation/results** and then enrich local user/authorities; do not manually parse raw SAMLResponses without verification.

**Migration goal:** Role/tenant/user linking should match the legacy business intent more securely, not necessarily match every Java class or `Authentication.toString()`.

## 15. Single Logout: Do Not Treat Local Logout as SLO

The legacy extension typically configured `SAMLLogoutFilter` and `SAMLLogoutProcessingFilter`. Modern Spring Security provides `saml2Logout()` and filters dedicated to `SAMLRequest`/`SAMLResponse`.

Per Spring documentation:
- **RP-initiated:** User POSTs to the logout endpoint; SP clears local session, sends a signed `LogoutRequest` to the IdP; the IdP may return a `LogoutResponse` for the SP to verify.
- **AP/IdP-initiated:** SP receives a `LogoutRequest` from the IdP, verifies signature/issuer/destination/subject/matching correlation, invalidates the session, and returns a `LogoutResponse`.
- Spring's default SLO endpoint is typically **`/logout/saml2/slo`**.
- Enabling `saml2Logout()` requires **IdP SLO support and matching SP signing key/cert** (per documentation configuration). Do not simply add the DSL and assume global logout works automatically.

### Optional JavaConfig Fragment When SLO Prerequisites Are Met

~~~java
// Inside the SecurityFilterChain bean once a registration exists with
// SP signing credentials and IdP SingleLogoutService metadata:
http
    .saml2Login(Customizer.withDefaults())
    .saml2Logout(Customizer.withDefaults());
~~~

To retain the legacy `/SLOService.saml2` endpoint, the documentation shows customization:

~~~java
http.saml2Logout(saml2 -> saml2
    .logoutRequest(request -> request
        .logoutUrl("/SLOService.saml2"))
    .logoutResponse(response -> response
        .logoutUrl("/SLOService.saml2"))
);
~~~

You must also update `singleLogoutServiceLocation` in the registration and partner metadata. **Writing filter matchers alone is not enough**.

### Local vs. SLO and Session Semantics

| Event | What Can Be Concluded |
| --- | --- |
| `POST /logout` performs local cleanup | Local session has been cleared per implementation |
| SP sent `LogoutRequest` | SLO was initiated; does not yet confirm IdP cleared its session |
| SP received signed/valid `LogoutResponse` | Response confirmed within protocol/scope |
| SP received valid IdP-initiated `LogoutRequest` | Matching local session can be invalidated per policy |
| Browser tab closed | No proof of server-side logout |
| Session expired | Not an active user-initiated logout |

During migration you must test **both RP-initiated and IdP-initiated**, session index/NameID matching, RelayState, InResponseTo, CSRF/cookie, and response status. Do not emit `GLOBAL_LOGOUT_COMPLETED` just because an HTTP 200 or redirect was observed.

## 16. SP-Initiated vs. IdP-Initiated SSO

Legacy apps may support both:
- **SP-initiated**: Spring issues an AuthnRequest, stores request/RelayState, and the IdP returns a matching `InResponseTo`.
- **IdP-initiated (unsolicited)**: IdP sends a SAMLResponse to the ACS without the SP having created an AuthnRequest; correlation does not exist as in the SP-initiated flow.

**Do not leave unsolicited SSO open by default just for compatibility** if the business does not require it. When it must be accepted, enforce specific policies for issuer, recipient, audience, signature, freshness, replay, local user linking, and login CSRF/session confusion. A different app may require disabling IdP-initiated SSO completely.

Test cases:
- Users starting from the legacy IdP portal; is an IdP-initiated path still required?
- IdP sends `RelayState` as an opaque state or a URL; is there an open redirect?
- IdP sends Response to the new ACS in staging and production; is destination validated properly?
- Can the Authentication Request repository in session store/read across pods when the callback lands on a different pod?
- Is `InResponseTo`/request-ID thoroughly checked in the SP-initiated case?
- Is the replay cache shared across multiple nodes or local to one JVM only?
- With multiple IdPs, which validation cert source is selected for an unsolicited response?

**A successful migration must never be traded for disabling signature, issuer, or audience checks.**

## 17. Extension Profiles/Bindings That May Lack Direct Equivalents

Historical extension 1.x documentation lists profiles such as:
- Web Browser SSO (SP-/IdP-initiated).
- Single Logout.
- HTTP-POST, HTTP-Redirect, Artifact, SOAP, PAOS/ECP, and Enhanced Client/Proxy variants within the extension's scope.
- Discovery/IdP selection, metadata interoperability, certain PKIX trust and holder-of-key cases.

The modern SAML2 module is described by Spring primarily as a **SAML Web Browser SSO Service Provider** and SLO. **Do not assume every extension 1.x binding/profile is identically supported**. Build a table:

| Legacy Feature | Handling Approach |
| --- | --- |
| HTTP-Redirect AuthnRequest + HTTP-POST SAMLResponse | Common capability, test by default |
| POST AuthnRequest if required by IdP | Check `Saml2AuthenticationRequestResolver`/OpenSAML factory customization |
| Artifact binding | Verify specific support; if absent, design alternative/gateway |
| SOAP/ECP/PAOS | May require a SAML gateway or another library per feature gap |
| Holder-of-key profiles | Do not replace implicitly with bearer web SSO |
| Custom discovery service | Implement an explicit picker page/registration resolution |
| Metadata reload without restart | Custom/caching repository and trust change process |
| Custom policy "sign Response or all Assertions" | Use version-appropriate provider validators, test negative cases |
| Custom request-scoping/RequestedAuthnContext | Configure strict customization, test with IdP |
| Custom logout/session index | Replicate exact SLO contract using supported APIs |

If a legacy profile is **mandatory for a partner**, deploying "Spring Security 7 + saml2Login()" alone may **not be enough**. Do not silently disable functionality or downgrade the profile; consider a dedicated SAML gateway/IdP broker or defer that piece separately with risk acceptance and a replacement plan.

## 18. Reverse Proxy, Context Path, and Forwarded Headers

Legacy `SAMLContextProviderLB` was commonly used to advertise the public server name/port/context path when running behind Nginx/ingress. In modern Spring, many URLs use `{baseUrl}` and `RelyingPartyRegistration`, which are affected by request/proxy metadata.

Example:

~~~text
External URL: https://portal.example/sso
Ingress -> internal http://app:8080

Expected public ACS:
  https://portal.example/login/saml2/sso/corp

Wrong inferred ACS if forwarded headers missing:
  http://app:8080/login/saml2/sso/corp
~~~

If the IdP sends Destination to the public URL while Spring validates against the internal URL, login fails. Steps:
1. Determine the canonical external public URL for the SP.
2. Check trusted proxy headers `Forwarded`/`X-Forwarded-Proto`/`X-Forwarded-Host`/`X-Forwarded-Port`/prefix.
3. Configure Boot `server.forward-headers-strategy` appropriate for the environment **or** ForwardedHeaderFilter/server native, avoiding two overlapping processing layers.
4. **Trust forwarded headers only when set/sanitized by trusted ingress**; never accept client-spoofed Internet headers to craft malicious ACS URLs.
5. Explicit `entityId`/ACS URLs can be used for stability if architecture requires, but filter matchers/IdP metadata must share the same contract.
6. Test HTTPS and path prefixes on production-like ingress, not just localhost.

**Do not fix Destination mismatches by removing DestinationValidator.** That degrades the ability to detect SAMLResponses intended for a different endpoint.

## 19. CSRF, Session Cookies, and AuthnRequest Correlation

Spring Security uses HTTP session/repository storage for authorization request state in many configurations. In SAML Web Browser SSO, the IdP sends a **cross-site HTTP POST** to the ACS; browser cookie policies (SameSite/third-party cookie restrictions) can drop the session cookie and break request correlation.

- `SameSite=Lax` generally supports top-level cross-site **GET**, but does not by default send cookies on cross-site POST.
- `SameSite=None; Secure` may be needed for some SAML POST ACS/session designs, while assessing CSRF risk.
- Spring's `HttpSessionSaml2AuthenticationRequestRepository`/request repository must match load balancing/session store setups.
- If the callback hits a different pod, Spring Session/Redis or sticky sessions may be used per risk/deployment model; ensure TTL and request correlation.
- Do not disable CSRF application-wide just to let the ACS POST through. Spring SAML filters have appropriate mechanisms; if using a custom URL, configure a minimal, justified exemption and test it.
- Verify `RelayState` and `InResponseTo` to guard against unsolicited/replay/login CSRF.
- Rotate session ID / apply fixation policy after login and do not retain raw SAMLResponses/tickets longer than needed.
- Test Safari/Firefox/Chrome under current cookie policies; do not claim Chrome blocks third-party cookies for all users.

**Do not treat "valid SAML signature" as sufficient if request/session correlation is bypassed.** Migration can weaken the login flow when trying to restore compatibility.

## 20. Authorization: Preserve Business Permissions, Not Legacy Security Smells

Legacy `SAMLUserDetailsService` could construct application `UserDetails` and authorities from `SAMLCredential`. In Spring Security SAML2, default framework authorities do not automatically represent business permissions.

**Typical policy:**
- Verified IdP + immutable subject → local user link; do not unconditionally use email as primary key.
- Attribute `groups` has 0..N values; map only **approved group IDs** to `ROLE_REPORT_VIEWER`/`ROLE_REPORT_EDITOR`.
- `tenant` is mandatory: exactly **one** value and verify local tenant membership.
- Missing group → authenticated but **no** app-specific role; protected endpoints return deny.
- AD `Domain Admins` does not automatically become portal `ROLE_ADMIN`.
- Disabled local account → deny even when the SAML Assertion is valid.
- Users from IdP A and IdP B with the same username/email → do not automatically account-link.

Example contract:

~~~text
idpEntityId: https://idp.example/entity
subject: persistent-opaque-user-id
tenant: reports
groups: [APP_REPORT_VIEWERS, OTHER_GROUP]

local user key:
  (trusted_idp_entity_id, stable_subject)
  -> local_user_041

approved mapping:
  APP_REPORT_VIEWERS -> ROLE_REPORT_VIEWER
  OTHER_GROUP        -> no application role
~~~

**Do not log raw Assertion XML, NameID, email, or group lists** during migration. Use synthetic identities, sanitized error codes, and internal correlation IDs.

## 21. Standalone Java 17: Verify Migration Contract Before Updating IdP

The following program uses **only Java 17** to check whether a target configuration preserves essential properties of the legacy SP: `EntityID`, ACS, issuer, AuthnRequest signing policy, NameID format, and group attribute. It also illustrates allowlist-based role mapping.

**This is a contract-check demo**; it does **not** parse/verify SAMLResponses, perform XML Signature/Encryption, or connect to an IdP. Production still requires Spring Security/OpenSAML provider and signed E2E fixtures.

Create file **`SamlExtensionMigrationDemo.java`**:

~~~java
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

public class SamlExtensionMigrationDemo {

    record SpContract(
            String spEntityId,
            String acsUrl,
            String idpEntityId,
            boolean signedAuthnRequestRequired,
            String nameIdFormat,
            String groupsAttribute) { }

    static Set<String> appRoles(List<String> incomingGroups) {
        Set<String> roles = new TreeSet<>();
        for (String group : incomingGroups) {
            if ("APP_REPORT_VIEWERS".equals(group)) {
                roles.add("ROLE_REPORT_VIEWER");
            }
            if ("APP_REPORT_EDITORS".equals(group)) {
                roles.add("ROLE_REPORT_EDITOR");
            }
        }
        return roles;
    }

    static boolean sameTrustContract(
            SpContract oldConfig,
            SpContract newConfig) {
        return oldConfig.spEntityId().equals(newConfig.spEntityId())
                && oldConfig.acsUrl().equals(newConfig.acsUrl())
                && oldConfig.idpEntityId().equals(newConfig.idpEntityId())
                && oldConfig.signedAuthnRequestRequired()
                     == newConfig.signedAuthnRequestRequired()
                && oldConfig.nameIdFormat().equals(newConfig.nameIdFormat())
                && oldConfig.groupsAttribute()
                     .equals(newConfig.groupsAttribute());
    }

    public static void main(String[] args) {
        String issuer = "https://idp.example/entity";
        String entity = "https://reports.example/legacy-sp";
        String acs = "https://reports.example/saml/SSO";
        String format =
                "urn:oasis:names:tc:SAML:2.0:nameid-format:persistent";
        String groups = "urn:example:claims:groups";

        SpContract legacy = new SpContract(
                entity, acs, issuer, true, format, groups);
        SpContract preserved = new SpContract(
                entity, acs, issuer, true, format, groups);
        SpContract changed = new SpContract(
                "https://reports.example/new-sp",
                "https://reports.example/login/saml2/sso/corp",
                issuer, false, format, groups);

        System.out.println("Preserved contract compatible: "
                + sameTrustContract(legacy, preserved));

        System.out.println("Changed defaults compatible: "
                + sameTrustContract(legacy, changed));

        System.out.println("SP EntityID preserved: "
                + legacy.spEntityId().equals(
                    preserved.spEntityId()));

        System.out.println("ACS preserved: "
                + legacy.acsUrl().equals(
                    preserved.acsUrl()));

        System.out.println("IdP issuer preserved: "
                + legacy.idpEntityId().equals(
                    preserved.idpEntityId()));

        System.out.println("Request signing policy preserved: "
                + (legacy.signedAuthnRequestRequired()
                   == preserved.signedAuthnRequestRequired()));

        System.out.println("Approved roles: "
                + appRoles(List.of(
                    "Domain Admins", "APP_REPORT_VIEWERS")));

        System.out.println("Unapproved admin becomes ROLE_ADMIN: "
                + appRoles(List.of("Domain Admins"))
                    .contains("ROLE_ADMIN"));

        System.out.println("Missing approved group grants role: "
                + !appRoles(List.of("OtherGroup")).isEmpty());

        System.out.println("New ACS needs partner update: "
                + !legacy.acsUrl().equals(changed.acsUrl()));
    }
}
~~~

Compile and run with **JDK 17+**:

~~~bash
javac SamlExtensionMigrationDemo.java
java SamlExtensionMigrationDemo
~~~

**Exact stdout:**

~~~text
Preserved contract compatible: true
Changed defaults compatible: false
SP EntityID preserved: true
ACS preserved: true
IdP issuer preserved: true
Request signing policy preserved: true
Approved roles: [ROLE_REPORT_VIEWER]
Unapproved admin becomes ROLE_ADMIN: false
Missing approved group grants role: false
New ACS needs partner update: true
~~~

**Explanation:**
- `preserved` keeps the example contract fields, so string checks return `true`.
- `changed` alters EntityID, ACS, and disables required signing, so it is **incompatible** with the old contract if the IdP has not been updated.
- `NameIDFormat` and group attribute URI are preserved, avoiding silent changes to local identity mapping.
- `Domain Admins` is not granted app `ROLE_ADMIN`.
- When no approved group is present, no application role is granted.
- Changing the ACS requires updating partner registration or implementing verified compatibility endpoints.

**Warning:** `sameTrustContract` only compares **6 illustrative fields** and does not check certificates, signatures, encryption, replay, metadata, SLO, cookies, tenants, profile/binding support, or actual signed assertions. In a real migration, **the contract in the Section 4 table is much broader** and requires E2E security testing. Do not use this function as SAML authorization/validation logic.

## 22. Phased Migration Plan

### Phase 0 — Discovery and Baseline

- Finalize the inventory of IdP/SP metadata, EntityID, ACS, SLO, certs, algorithms, subjects/attributes/groups/tenants.
- Capture **test-only** baseline behaviors from the legacy app: SP-initiated/IdP-initiated login, logout, role mapping, error behavior, multi-IdP, and proxy.
- Record dependency versions, vulnerability baseline, backend services, DNS, firewall, and IdP ownership.
- Mark mandatory vs. optional features, especially Artifact/ECP/SOAP and dynamic metadata reload.

### Phase 1 — Build the New SAML2 SP in an Isolated Environment

- Use an organization-supported Spring Boot/Security version and compatible JVM/Jakarta libraries.
- Add `spring-security-saml2-service-provider` and `saml2Login`; remove legacy extension/filter classes from the target app.
- Configure a `RelyingPartyRegistration` with IdP test metadata and a trusted verification certificate.
- Use a separate SP EntityID/ACS for staging to avoid colliding with production IdP registration.
- Allow only test identities/approved accounts in staging; never use production keys.
- Check HTTP response headers, no-store, TLS, CSRF, and default-deny routes.

### Phase 2 — Connect IdP, Authenticate, and Map

- Provide the new SP metadata to staging IdP; verify EntityID/ACS/signature requirements.
- Test HTTP-Redirect AuthnRequest, HTTP-POST response, request correlation, conditions, and response audience.
- If the IdP signs AuthnRequests or encrypts Assertions, add signing/decryption `Saml2X509Credential`s.
- Read verified NameID/attributes via the provider and map local user/authorities/tenant per contract.
- Test users missing optional fields, wrong tenant, disabled account, and duplicate emails/multi-IdP.

### Phase 3 — SLO and Advanced Requirements

- Enable `saml2Logout()` only after IdP/SP keys, endpoints, and bindings are verified.
- Test RP-initiated and AP-initiated SLO, invalid signatures, stale sessions, request replay, and missing correlation.
- Verify artifact/ECP/discovery/RequestedAuthnContext/metadata reload: every feature gap must have an explicit disposition.
- Test IdP signing certificate rotation and SP decryption key rotation.

### Phase 4 — Production-Like Staging

- Route through **the same ingress/CDN/WAF/LB, HTTPS scheme, and context path** as production.
- Test multi-pod sessions/shared request repository/cache, SameSite cookies, and browser flows.
- Run regressions against the real Java/Spring dependency versions.
- Verify audits, SIEM, and telemetry contain no raw SAMLResponses/NameIDs/keys.
- Load-test IdP metadata retrieval/startup behavior, key rollover, and disaster recovery.

### Phase 5 — Canary and Rollout

- Coordinate with IAM/IdP admins to update metadata/ACS/certs during an approved change window.
- A **separate SP registration** (different EntityID/ACS) can be used for canary if the IdP supports it; never let two SPs sharing an EntityID receive arbitrary responses.
- Route a group of test users/partner traffic to the new SP using verified configuration while maintaining session isolation.
- Compare login success/failure rates, SAML validation reasons, role mappings, and logout outcomes.
- Do not split a single ACS URL across two stacks via round-robin when request correlation/stores are incompatible.
- Gradually expand traffic only after acceptance criteria are met and monitoring is stable.

### Phase 6 — Cutover, Rollback, and Legacy Cleanup

- Switch partner metadata/redirect/ACS/SLO to the approved target and confirm the IdP's effective state.
- Remove `spring-security-saml2-core`, legacy XML beans/filters, and OpenSAML transitive overrides from the new app.
- Revoke/rotate legacy credentials per policy once overlap ends; do not delete them too early.
- Update runbooks, dashboards, dependency governance, and secure cookie settings.
- Rollback must restore **both the SP deployment + IdP metadata/ACS/cert trust + session assumptions**; do not just redeploy an old JAR and expect the IdP to revert itself.
- Audit old/new revision/actor/approver, which nodes were deployed, and rollback reason.

## 23. Proper "Parallel" Strategies: Do Not Create Two Authenticating Principals for One Callback

Selectable architectures:

| Strategy | Strengths | Risks / Checks Needed |
| --- | --- | --- |
| **Migrate in-place within a change window** | Fewer IdP registrations, operationally simple | Downtime/rollback depends on partner update |
| **Parallel staging with new SP EntityID** | Independent testing, avoids prod impact | IdP must support another app registration and test users |
| **Canary with separate ACS/EntityID** | Clear gradual traffic shift | Selecting right IdP registrations, session isolation |
| **SAML gateway/broker preserving external contract** | Can reduce IdP changes across many apps | Adds a trust boundary/ops/latency; must audit broker |
| **Dual-stack in same app, different ACS** | Can support per-route migration | Filter order, shared session, complex keys/correlation; not recommended without thorough testing |

**Do not send the same signed SAMLResponse to two SPs for shadow verification**: Assertions typically contain Audience/Recipient/One-time replay conditions; a Response issued for SP A is not automatically valid for SP B. For dual-run testing, the IdP must issue distinct responses per registration rather than "cloning packets" to test.

## 24. Security and Compatibility Test Matrix

| ID | Scenario | PASS Criteria |
| --- | --- | --- |
| M01 | SP-initiated login with staging IdP | Redirect/AuthnRequest/POST ACS/authenticated properly |
| M02 | Legacy EntityID preserved | IdP Audience matches, no unexpected entity switch |
| M03 | New default ACS while IdP still uses legacy URL | Mismatch detected, no silent fallback |
| M04 | Custom legacy ACS enabled | Filter/registration/IdP/proxy all share the exact URL |
| M05 | IdP-initiated SSO | Accepted only if policy approved; replay/issuer validated |
| M06 | Wrong InResponseTo | Reject SP-initiated response |
| M07 | Signed Assertion with trusted cert | Accepted when all other conditions pass |
| M08 | Assertion signed with unknown cert | Rejected, no trust-all |
| M09 | Unsigned Response, unsigned Assertion | Rejected |
| M10 | Expired Assertion / future NotBefore | Rejected within approved small clock skew |
| M11 | Wrong Audience, Recipient, or Destination | Rejected, validators not disabled |
| M12 | SAMLResponse replay with same Assertion ID | Rejected per replay/correlation policy |
| M13 | EncryptedAssertion with correct SP decrypt key | Decrypted + verified, then authenticated |
| M14 | EncryptedAssertion with wrong SP key | Rejected, no plaintext fallback |
| M15 | EncryptedAttribute/EncryptedID | Decrypted in proper order after relevant checks |
| M16 | Signed AuthnRequest required but SP does not sign | Fails clearly; add signing credential |
| M17 | IdP signing rollover A→B | Old/new trust overlap works within window |
| M18 | SP decryption key rollover A→B | Pods share the same allowed keysets |
| M19 | Missing optional displayName/email | No NPE thrown and no wrong account-link |
| M20 | Missing required tenant | Deny authorization/login per contract |
| M21 | Multi-value groups | Full list evaluated, exact allowlist enforced |
| M22 | AD Domain Admins without app group | ROLE_ADMIN not granted |
| M23 | Two IdPs sharing same email/username | Users/tenants not merged erroneously |
| M24 | IdP metadata unavailable at startup | Fails/recovers per explicit design, no silent trust bypass |
| M25 | IdP metadata signature/PKIX invalid | Rejected per trust policy |
| M26 | Proxy Forwarded spoofing | No ACS/EntityID derived from untrusted headers |
| M27 | Browser cross-site POST and SameSite | Request correlation stable, no CSRF downgrade |
| M28 | Callback hits a different pod | Shared request repository/session works properly |
| M29 | Login fails then retries | No stale AuthnRequest/RelayState confusion |
| M30 | RP-initiated SLO | Signed LogoutRequest, valid response/correlation |
| M31 | AP-initiated SLO invalid signature | Rejected, no arbitrary logout |
| M32 | Local logout only | Does not report global SLO completed |
| M33 | Custom legacy SLO URL | Matches filter, registration, metadata/IdP |
| M34 | XML Signature Wrapping/XXE/oversized XML | Provider/parser rejects per security policy |
| M35 | Legacy Artifact/ECP/PAOS use case | Gap tested/resolved, not silently dropped |
| M36 | Browser history/ingress logs | No raw SAMLResponse/keys/PII in logs |
| M37 | Role mapping in Spring 6/7 | Compatibility with principal accessor verified |
| M38 | SAML config revision changed mid-rollout | Per-node drift/audit detected |
| M39 | Switchback/rollback test | IdP+SP metadata/trust restored with evidence |
| M40 | OIDC/API sharing the same app | SecurityFilterChains do not intercept wrong routes |
| M41 | New metadata endpoint | EntityID, ACS, key descriptors published accurately |
| M42 | Auth failure due to cert vs. missing permission | Logs distinguish protocol failure from local authorization |
| M43 | CAS/OIDC coexistence (if present) | Correct authentication manager selected, no filter conflicts |
| M44 | Negative HTTP GET SAMLResponse | Does not bypass intended HTTP POST binding/security checks |
| M45 | Post-upgrade session/logout | No arbitrary legacy session retention or fixation |

**Fixture requirement:** To test time/audience/signature, you must create a **valid signed SAMLResponse** from a test IdP or OpenSAML signer lab and modify conditions before signing; editing XML after signing only invalidates the signature and fails to test other validators. Never put production signing keys/credentials into CI.

## 25. Common Migration Errors and How to Fix Them

| Symptom | Likely Cause | Resolution |
| --- | --- | --- |
| 404 at `/saml/SSO` | Legacy ACS still on IdP, new filter listens only on default URL | Update IdP ACS or custom filter + registration |
| `AudienceRestriction` mismatch | New default SP EntityID differs from legacy | Align EntityID/IdP registration |
| `Destination` mismatch | Reverse proxy HTTPS/host/path misconfigured | Fix trusted forwarded headers/public ACS |
| `Signature validation failed` | Wrong IdP verification cert, metadata rollover | Check trusted signing cert, do not disable signature |
| `Could not decrypt` | Missing/wrong SP private decryption credential | Add correct keypair and encryption cert |
| `No matching AuthnRequest` | Session lost, RelayState/ACS mismatch, load balancing | Check request repository/cookie/session |
| CSRF 403 on ACS | Custom matcher/CSRF/cross-site POST cookie issue | Test filter chain and proper exception scope |
| 302 login loop | RegistrationId, saved request, cookies/IdP metadata issue | Trace flow by stage, do not log raw response |
| Login succeeded but user anonymous in controller | Wrong filter chain order/SecurityContext/session policy | Ensure saml2Login is in the right chain |
| Principal cast exception | `Saml2AuthenticatedPrincipal`/7 accessor mismatch | Refactor to actual resolved API |
| Groups receives only one value | Misuse of `getFirstAttribute` | Use list + cardinality/allowlist |
| Legacy user gets a new local account created | NameID format/EntityID link key changed | Explicit account migration/link audit |
| SLO clears local session only | SLO and signing key not enabled/configured | Add SLO tests per profile |
| IdP-initiated login fails | Unsolicited response not trusted/handled | Decide policy, do not drop replay/audience |
| One pod works, another pod fails | Inconsistent keys/registration/session store | Align deployment snapshots and secrets |
| Metadata refresh does not happen | Repo reads metadata only at startup | Build refresh strategy/version audit |
| Boot startup fails because IdP is offline | Metadata URI unavailable | Approved static metadata/caching/retries |
| Java `ClassNotFoundException` | Extension/OpenSAML javax/jakarta conflict | Fix BOM/transitive dependency tree |
| Legacy Artifact/ECP does not run | Feature parity unverified | Gateway/alternative/profile migration |
| SAMLResponse appears in logs | Debug filter/ingress body capture | Redact/stop capture; incident response if real |
| Private key leaked in test artifacts | Improper secrets handling | Revoke/rotate, purge, and secure key storage |

**Never relax signature, audience, recipient, time, or replay checks just to get past a migration error.** A migration is truly complete only when **the minimum security posture is no weaker than the legacy system** and business behaviors are verified by both the IdP and the application.

## 26. Acceptance Criteria Before Cutover

**Protocol & trust:**
- New SP metadata is approved and properly imported by the IdP.
- EntityID/ACS/binding are accurate; AuthnRequest signing requirements and verification/decryption keys are correct.
- Signature/issuer/audience/recipient/NotBefore/NotOnOrAfter/InResponseTo/replay tests PASS.
- Trusted certificate rotation and metadata refresh strategy have clear ownership.

**Identity & permissions:**
- Stable identity linking works for each IdP/tenant; no account collisions.
- Disabled/revoked local users are denied per policy.
- Missing/empty/multi-valued SAML attributes are handled properly.
- Admin roles are not auto-granted from raw IdP groups; authorization negative tests PASS.

**Operations & SLO:**
- Login and logout have telemetry/auditing without leaking credentials.
- SLO is tested with the IdP if required; local vs. remote completion is distinguished.
- Cluster/session/cookie/reverse-proxy/SameSite tested on real browsers.
- An executable rollback exists, covering IdP metadata/registered ACS/keys and app deployment.
- Dependency tree has no remaining extension/OpenSAML collisions; security scanning has been run.
- Feature-gap inventory has dispositions for Artifact/ECP/SOAP and custom behaviors.
- Partner change management has approval/change ticket, canary, monitoring, and post-cutover review.

Do not mark **"migration done"** simply because the IdP login screen appears; that proves at most that **AuthnRequest initiation** worked, not that the Response is verified, the local user is right, permissions are right, and logout is secure.

## 27. Practical Step-by-Step Checklist

1. Confirm the app is an **SP**; if the project implements its own IdP or ECP/Artifact, handle the feature gap separately.
2. Read legacy XML/metadata/keystore configs and capture the exact external SAML contract.
3. Lock Java, Spring Boot/Security, and OpenSAML dependency versions to a supported BOM.
4. Remove the legacy extension and filters **from the target runtime**; never listen on the same ACS simultaneously.
5. Add `spring-security-saml2-service-provider`; configure `SecurityFilterChain.saml2Login`.
6. Create `RelyingPartyRegistration` from approved IdP metadata and entity IDs.
7. Generate/verify SP metadata via `saml2Metadata`; compare EntityID, ACS, certs, and bindings against legacy.
8. Supply SP signing/decryption credentials when IdP policy requires them, managing secrets properly.
9. Decide whether to keep or change URLs; update **filter + registration + IdP + proxy** consistently.
10. Replicate request correlation, state, session timeout, cookie SameSite, and proxy URLs.
11. Migrate user details/role mapping to verified attributes and strict tenant/identity policy.
12. Test SP-initiated login, IdP-initiated when approved, and RP/AP SLO when supported.
13. Check legacy profiles/bindings beyond browser SSO; do not silently drop critical features.
14. Execute negative tests for signature, audience, recipient, replay, time, decryption, and spoofed headers.
15. Test multi-node, metadata refresh/key rotation, WAF/APM/log redaction.
16. Canary with IdP test users/approved partner changes; measure errors by reason/registration/node.
17. Cut over production with approval, config revision auditing, and an IdP+SP rollback plan.
18. Retire legacy dependencies and old credentials after a safe overlap; update runbooks.

## 28. Official Reference Documentation

1. [Spring Security SAML Extension 1.x — Reference Documentation](https://docs.spring.io/spring-security-saml/docs/current/reference/htmlsingle/): `SAMLEntryPoint`, `SAMLProcessingFilter`, `MetadataGeneratorFilter`, `MetadataManager`, `KeyManager`, SLO, and supported extension profiles and bindings.
2. [Spring Security Wiki — SAML 2.0 Migration Guide (Extension → Spring Security 5.7)](https://github.com/spring-projects/spring-security/wiki/SAML-2.0-Migration-Guide): migration patterns guide, history, and core differences.
3. [Spring Security — SAML2 Login](https://docs.spring.io/spring-security/reference/servlet/saml2/login/): modern Spring RP/SP module.
4. [Spring Security — SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): `SecurityFilterChain`, `Saml2WebSsoAuthenticationRequestFilter`, `Saml2WebSsoAuthenticationFilter`, `RelyingPartyRegistration`.
5. [Spring Security — Producing SAML AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html): `/saml2/authenticate/{registrationId}`, signing, request repository, and customization.
6. [Spring Security — Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): ACS, OpenSAML provider, validators, decryption, NameID, and authority mapping.
7. [Spring Security — SAML2 Metadata](https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html): `saml2Metadata`, endpoints, and response resolver.
8. [Spring Security — SAML Single Logout](https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html): RP/AP SLO, signing credentials, and default endpoint.
9. [Spring Security — SAML2 Migrations (Spring 7)](https://docs.spring.io/spring-security/reference/migration/servlet/saml2.html): `Saml2ResponseAssertionAccessor`, `Saml2AssertionAuthentication`, logout behavior, and GET response handling changes.
10. [Spring Boot — SAML 2.0](https://docs.spring.io/spring-boot/reference/security/saml2.html): `spring.security.saml2.relyingparty.registration`, credential properties, and build repository.
11. [OASIS SAML 2.0 Core](https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf): Assertions, Issuer, Conditions, SubjectConfirmation, and attributes.
12. [OASIS SAML 2.0 Profiles](https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf): Browser SSO/SLO obligations.
13. [OASIS SAML 2.0 Metadata](https://docs.oasis-open.org/security/saml/v2.0/saml-metadata-2.0-os.pdf): EntityID, KeyDescriptor, AssertionConsumerService, and SLO metadata.
14. [OWASP — SAML Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html): signature validation, replay, XML signature wrapping, and trust.
15. [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): HTTP sessions, cookies, and logout.
16. [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): sensitive data in audits/logs.
17. [Spring Security — Servlet Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html): testing filter chains, authentication, and authorization.

**Remember:** Spring Security SAML Extension 1.x and modern Spring Security SAML2 share the **SAML 2.0 protocol**, but **do not share configuration models or APIs**. Start by inventorying the **trust contract (EntityID, ACS, issuer, certificates, conditions, subject, roles, SLO)**, build `RelyingPartyRegistration`/`saml2Login`, publish standard metadata, and test with the IdP before cutover. In particular, verify **endpoint + metadata + filter mapping**, **signing/decryption keys**, **authentication vs. authorization**, **SLO vs. local logout**, and **binding/profile gaps** together; mark success only when both positive and negative E2E tests along with rollback have been proven.