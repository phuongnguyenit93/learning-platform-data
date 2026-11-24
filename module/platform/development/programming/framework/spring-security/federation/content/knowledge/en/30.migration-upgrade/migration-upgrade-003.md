# Choosing OpenSAML 4 or OpenSAML 5 by Spring Security Version

## 1. Lesson Objectives

In **Spring Security - federation**, under **Migration and Upgrade**, choosing **OpenSAML 4** or **OpenSAML 5** is not an arbitrary preference of the development team. It is a compatibility decision across the **Spring Security version**, the SAML components provided by Spring, the actual Maven/Gradle **dependency graph**, the Java runtime, Jakarta/Servlet APIs, and custom code used by the application.

A misconfiguration can cause:
- Build failures because `OpenSaml4AuthenticationProvider` no longer exists in Spring Security 7.
- Startup errors such as `NoClassDefFoundError`, `NoSuchMethodError`, `ClassNotFoundException`, or `ServiceConfigurationError` caused by **mixing OpenSAML 4 and 5** or misaligned dependencies.
- SAML login failures during parsing, building AuthnRequests, signature validation, decrypting EncryptedAssertions, metadata, or Single Logout.
- An upgrade that "compiles and runs" yet accidentally drops critical checks like `InResponseTo`, `AudienceRestriction`, `Recipient`, signatures, or replay.
- Security risk from continuing to run an OpenSAML major version that is **end of life** without security fixes.

**Target outcome:** after this lesson, you can inspect the actual Spring Security version, determine the appropriate OpenSAML major, configure the build for that branch, verify the runtime classpath, migrate custom APIs from `OpenSaml4XXX` to `OpenSaml5XXX`, run regression tests, and decide whether it is safe to promote the upgrade to production.

> **Quick rule:** **Spring Security 6.5** supports choosing OpenSAML 4 (default) or OpenSAML 5 (opt-in); **Spring Security 7.x removed OpenSAML 4 support and requires OpenSAML 5**. Other Spring Security versions must be checked against the documentation for that exact version; do not assume every 6.x branch shares the same selection mechanism.

## 2. Version-Based Decision Matrix — Foundation for Every Choice

| Spring Security in Application | OpenSAML to Consider | Default Mechanism / Limits | Recommendation |
| --- | --- | --- | --- |
| **6.5.x** | **OpenSAML 4.x** or **5.x** | 6.5 docs state the default transitive dependency is OpenSAML 4; `spring-security-config` selects the matching implementation based on the library version found. | Existing projects may temporarily keep 4 to lower migration risk; **prioritize testing opt-in 5** before moving to Spring Security 7 because 4 is EOL. |
| **7.0.x / 7.1.x** | **OpenSAML 5.x** | Spring Security 7 **removed OpenSAML 4 support**; the default flow uses `OpenSaml5AuthenticationProvider`. | Use OpenSAML 5 via supported dependency management; remove custom `OpenSaml4XXX`, never try to force provider 4 to run. |
| **6.4.x and earlier** | Depends on the **exact patch/docs** | Do not apply 6.5/7 rules automatically; APIs, BOM, transitive dependencies, and major support may differ. | Confirm the documentation/Javadoc for that exact release, then plan an upgrade through 6.5 or a supported upgrade path. |
| **Spring Security 5.x or legacy Spring Security SAML Extension** | Separate legacy lineage | Differs in namespaces, dependencies, metadata, APIs, and Servlet stack; swapping the OpenSAML jar alone is not a complete migration. | First upgrade the stack systematically, port to `spring-security-saml2-service-provider`, and verify Jakarta/Java/IdP compatibility. |

**Official sources:** the [Spring Security 6.5 OpenSAML Support](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/opensaml.html) page confirms support for both majors, defaulting to 4 and how to opt into 5. [What's New in Spring Security 7.0](https://docs.spring.io/spring-security/reference/7.0/whats-new.html) confirms the **removal of OpenSAML 4**. [Migrating SAML 2.0 to Security 7](https://docs.spring.io/spring-security/reference/6.5/migration-7/saml2.html) guides dependency changes and custom APIs.

### 2.1. A Valid Answer Must Specify Exact Versions

Asking "Can Spring Boot 3 use OpenSAML 5?" **lacks sufficient information**. You must ask specifically:
1. Which Spring Boot version and BOM/parent manages `spring-security-*`?
2. What is the **final Spring Security artifact version** on the runtime classpath?
3. Which Java 17/21/25 runtime is running, and how does it differ from the build JDK?
4. Which **`org.opensaml` modules and versions** are Maven/Gradle actually resolving?
5. Do any custom classes directly instantiate `OpenSaml4AuthenticationProvider`, `OpenSaml4AuthenticationRequestFactory`, or OpenSAML XML objects?
6. To what extent does the app use login, SLO, metadata, XML signing/decryption, dynamic registrations, and custom validators?
7. Do other libraries such as Apache WSS4J/Shibboleth pull in a different OpenSAML major?

**Do not judge by a single Maven artifact name.** For example, `opensaml-saml-api` exists in both 4 and 5; you must verify the **resolved version**, legacy `opensaml-core` vs. new `opensaml-core-api`/`opensaml-core-impl` modules, and bytecode/API compatibility.

## 3. What Do OpenSAML and Spring Security Each Do?

**OpenSAML** is the XML/SAML library provided by the Shibboleth ecosystem: SAML protocol/data objects, XML marshalling/unmarshalling, signatures, encryption, metadata, and related utilities. It is **not a complete Identity Provider or Service Provider**.

**Spring Security SAML 2.0 Service Provider** provides:
- `Saml2WebSsoAuthenticationRequestFilter`: creates/dispatches AuthnRequests to the IdP.
- `Saml2WebSsoAuthenticationFilter`: receives browser-POSTed SAMLResponses.
- `Saml2AuthenticationTokenConverter`: pairs the response with the relying-party context.
- `RelyingPartyRegistration` and repository: issuer/SP entityID, ACS, IdP SSO URL, keys, and metadata.
- `OpenSamlXAuthenticationProvider` and request/metadata helpers: bridge Spring Security to the corresponding OpenSAML major API.
- SLO/metadata/session management components depending on configuration.

The minimal dependency configuration for **SAML SP** is the official dependency:

```xml
<dependency>
  <groupId>org.springframework.security</groupId>
  <artifactId>spring-security-saml2-service-provider</artifactId>
</dependency>
```

The exact artifact name is **`spring-security-saml2-service-provider`**. Do not copy/paste from an old description naming `spring-security-saml` if it does not match the dependency XML in the reference docs. Never pin a separate Spring Security version when the Spring Boot BOM/parent already manages the entire suite, unless executing a controlled upgrade plan.

### 3.1. The SAML2 Processing Pipeline Does Not Change Just Because the OpenSAML Major Changes

```text
Browser --GET /saml2/authenticate/{registrationId}-->
  Spring SAML AuthnRequest filter
    -> load approved RelyingPartyRegistration
    -> create/sign/encode AuthnRequest
    -> redirect browser to IdP
IdP authenticates user and returns browser POST:
  POST /login/saml2/sso/{registrationId}
    -> Spring SAML response filter
    -> token converter resolves registration
    -> OpenSAML-specific provider validates signed/encrypted SAML
    -> SAML principal + local authorization mapping
    -> Spring Authentication/session
```

**Different OpenSAML majors mainly affect the implementation/API/dependencies in the middle of the flow**, and never permit skipping AuthnRequest correlation, destination, issuer, audience, conditions, signature, or replay validation.

## 4. Why Do the `OpenSaml4XXX` and `OpenSaml5XXX` Class Names Matter?

In Spring Security 6.5, the documentation states the convention:
- `OpenSamlXXX`: class name or abstraction applicable across the majors supported by that Spring version.
- `OpenSaml4XXX`: Spring implementation depending on OpenSAML 4 APIs.
- `OpenSaml5XXX`: Spring implementation depending on OpenSAML 5 APIs.

Examples:
- `OpenSaml4AuthenticationProvider` is used on the 4 branch while that Spring Security version still supports it.
- `OpenSaml5AuthenticationProvider` is the implementation for the 5 branch.
- Depending on the version, there are also `OpenSaml4...`/`OpenSaml5...` factories, metadata repositories, and helpers.

**Picking the right JAR is not enough if custom code still instantiates classes from the other major.**

### 4.1. Spring Security 6.5: Automatic Class Selection Mechanism

The 6.5 documentation notes that `spring-security-config` selects the implementation corresponding to the OpenSAML major present. This is **auto-selection for default configuration**, not a promise that every `new OpenSaml4AuthenticationProvider()` magically turns into OpenSAML 5 or that every extension point ports itself.

When instantiating a custom `AuthenticationProvider`, `Saml2AuthenticationRequestFactory`, decrypter, signature validator, marshaller, or metadata parser, you are responsible for:
- Updating class/constructor names to match the chosen major's API.
- Updating type signatures for callbacks, converters, and token wrappers that changed.
- Checking validation/decryption ordering.
- Preserving default core SAML validators when extending.

### 4.2. Spring Security 7: No Longer "Choose 4 or 5"

In Spring Security 7, the choice table narrows: **5.x** is the supported OpenSAML branch. If code/binaries/libraries depend on Spring's `OpenSaml4...`, the application **cannot be fixed by adding OpenSAML 4 jars** because those Spring classes may have been removed.

You must **port custom code** or temporarily stay on supported Spring Security 6.5 under a time-boxed upgrade plan. Never deploy 7 + 4 as an official configuration or use package/classloader tricks to mask errors.

## 5. Inventory Versions Before Editing Build Files

Before modifying dependencies, build an environment table:

| Information | How to Obtain | Value to Record in Change Request |
| --- | --- | --- |
| Spring Boot version | Parent POM/BOM, Gradle plugins | Exact version, not just "Boot 3." |
| Spring Security version | Runtime dependency tree | Versions of `spring-security-config`, `spring-security-web`, `spring-security-saml2-service-provider`. |
| OpenSAML modules | Runtime dependency tree | Major/patch of `opensaml-saml-api`, `opensaml-saml-impl`, core, and supporting modules. |
| Java build and runtime | `java -version`, `mvn -version` / Gradle toolchain | Both the build JVM and the image/container runtime. |
| Servlet/Jakarta dependencies | Dependency tree and container | Do not mix `javax.servlet` and `jakarta.servlet` incompatibly. |
| XML Security libraries | Dependency tree | Apache Santuario, xmltooling, Shibboleth utilities. |
| Custom SAML API usage | Code search in permitted project | `OpenSaml4...` classes, XMLObject builders, custom decrypters. |
| Authentication flows | Integration test inventory | SP-initiated, policy-approved IdP-initiated, multi-IdP, signed requests, encrypted assertions, SLO. |
| IdP registrations | Approved metadata/config | EntityID, ACS, signature cert, algorithms, NameID/attributes mapping. |

**Maven commands**, run from the application directory when permitted:

```bash
mvn -version
mvn dependency:tree -Dincludes=org.springframework.security
mvn dependency:tree -Dincludes=org.opensaml
mvn dependency:tree -Dincludes=net.shibboleth
mvn dependency:tree -Dverbose
mvn help:effective-pom
```

Some plugins/versions handle `-Dincludes` syntax differently; if filtering misses entries, run full `mvn dependency:tree` and search the groups. You must inspect **runtime artifact versions**, not just declared dependencies.

**Gradle commands**:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency opensaml-saml-api --configuration runtimeClasspath
./gradlew dependencyInsight --dependency opensaml-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-saml2-service-provider --configuration runtimeClasspath
```

On Windows use `gradlew.bat`, PowerShell, or the appropriate shell. `dependencyInsight` helps explain version conflicts, constraints, and which dependency pulled an unexpected major.

## 6. Java 17 and Jakarta: Do Not Confuse "Upgrading OpenSAML" with "Upgrading the JDK"

OpenSAML 5 belongs to the **Shibboleth Java 17 platform**, requiring **Java 17 or later**. OpenSAML 4 belonged to the older Java 11 line and is end of life. Spring Boot 3.x and 4.x also use Java 17 or later as their baseline (exact version/runtime and servlet API details depend on the specific branch).

**Common mistakes:**
- Running Maven on JDK 21 while the production container runs Java 11: the build succeeds, and the runtime cannot load the class files.
- Changing only `sourceCompatibility` or `--release` without changing the actual JVM in the app image.
- Seeing `javax.servlet.ServletOutputStream` missing in a Jakarta runtime and concluding "Java 21 does not support OpenSAML."
- Keeping an old pre-Jakarta integration library in a Boot 3/4 app using `jakarta.servlet`, causing `NoClassDefFoundError`.
- Switching OpenSAML 4→5 while keeping a library integration/WSS4J version compatible only with 4.

### 6.1. Distinguishing Namespaces

| API Ecosystem | Indicator | Required Action |
| --- | --- | --- |
| Java EE / pre-Jakarta | `javax.servlet.*` | Do not assume it runs with `jakarta.servlet.*` without a compatibility migration step. |
| Jakarta EE | `jakarta.servlet.*` | Align Spring Framework/Boot/Security and the container. |
| OpenSAML Java platform 4 | Java 11 platform, legacy support | May exist in legacy apps, but not a target platform for upgrading to 7. |
| OpenSAML Java platform 5 | Java 17 platform | Fits Spring Security 7 target; verify dependencies share the same major. |

**Never recommend "downgrading Java to 11 to keep OpenSAML 4"** in a modern Spring Security 6/7 app: that breaks the platform baseline and ignores end-of-life exposure.

## 7. Shibboleth Maven Repository and Supply-Chain Controls

The Spring Security SAML2 SP dependency brings in OpenSAML/Shibboleth artifacts. Spring Security docs note that adding the **Shibboleth Releases Repository** is often necessary to resolve dependencies.

Maven:

```xml
<repositories>
  <repository>
    <id>shibboleth-releases</id>
    <name>Shibboleth Releases Repository</name>
    <url>https://build.shibboleth.net/maven/releases/</url>
    <releases><enabled>true</enabled></releases>
    <snapshots><enabled>false</enabled></snapshots>
  </repository>
</repositories>
```

Gradle Kotlin DSL:

```kotlin
repositories {
    mavenCentral()
    maven {
        url = uri("https://build.shibboleth.net/maven/releases/")
        mavenContent { releasesOnly() }
    }
}
```

**The URLs above are public artifact repositories referenced by Spring docs, not IdP metadata endpoints.** In enterprises with internal Artifactory/Nexus, prefer approved mirrors and verify source/provenance, TLS, artifact signatures/checksums, repository allowlists, and dependency locks.

**Never enable snapshot repos in production** to fix "Could not find OpenSAML," never add an arbitrary repository suggested by a dependency, and never use `LATEST`, `+`, or snapshot versions for release builds. If a build only succeeds by adding an unfamiliar repository, require a security review first.

## 8. Option A: Spring Security 6.5 Keeping Default OpenSAML 4

In the **6.5** branch, official docs state OpenSAML 4 is the default. If the app has no custom overrides or conflicting dependencies, only the SAML SP dependency is needed:

```xml
<dependencies>
  <dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-saml2-service-provider</artifactId>
  </dependency>
</dependencies>
```

Conditions:
- The BOM/parent already manages the corresponding **Spring Security 6.5 patch**.
- The runtime dependency graph genuinely contains only OpenSAML 4 artifacts valid for Spring 6.5, with no 5.x mixed in.
- Every custom provider/factory uses 4 APIs compatible with that exact patch.
- Java/Servlet stack and IdP integration tests pass.
- A migration plan exists because **OpenSAML 4 is no longer supported by Shibboleth**; do not treat this as a permanent state.

**When to keep temporarily?** If the enterprise is stable on 6.5, some custom OpenSAML 4 code is not yet ported, or IdP integration requires lengthy testing. Keeping it temporarily requires **risk acceptance and a migration deadline**, without skipping Spring Security advisories/patches during the transition.

**Never apply this keep-4 approach to Spring Security 7.x.**

## 9. Option B: Spring Security 6.5 Opting Into OpenSAML 5 Before Upgrading to 7

A strong strategy for projects preparing for Spring Security 7 is to **upgrade the OpenSAML major first**, reducing simultaneous changes. Spring Security 6.5 can select `OpenSaml5XXX` implementations when the dependency graph contains only valid OpenSAML 5 artifacts.

Spring Security 6.5 documentation instructs excluding transitive `org.opensaml` major 4 artifacts and declaring **OpenSAML 5 API and implementation**. The example below illustrates pinning **OpenSAML 5.2.3** — a release version recorded in the Shibboleth Maven repository in 2026 — instead of copying old docs examples using 5.1.2. **Re-check advisories and test compatibility of your specific combination before release**; the version here is an illustrative build pin, not a guarantee every project works by pasting alone.

### 9.1. Controlled Maven Override

```xml
<properties>
  <opensaml.version>5.2.3</opensaml.version>
</properties>

<dependencies>
  <dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-saml2-service-provider</artifactId>
    <exclusions>
      <exclusion>
        <groupId>org.opensaml</groupId>
        <artifactId>*</artifactId>
      </exclusion>
    </exclusions>
  </dependency>
  <dependency>
    <groupId>org.opensaml</groupId>
    <artifactId>opensaml-saml-api</artifactId>
    <version>${opensaml.version}</version>
  </dependency>
  <dependency>
    <groupId>org.opensaml</groupId>
    <artifactId>opensaml-saml-impl</artifactId>
    <version>${opensaml.version}</version>
  </dependency>
</dependencies>
```

**Must be placed in an application POM that already has parent/BOM, Java, and repositories**, not as a standalone complete POM. If a corporate BOM or transitive modules still force other `org.opensaml` libraries to 4.x, adjust dependency management/constraints in the appropriate scope and **verify the entire runtime tree**. Do not inspect only the two direct dependencies.

In Maven, `<artifactId>*</artifactId>` in the documentation's exclusion excludes `org.opensaml` dependencies pulled transitively by the Spring SAML module; it **does not remove all OpenSAML in the project if another library pulls them from a different branch**. If the build still has 4 and 5 simultaneously, trace the dependency tree and fix at the root source; do not apply global exclusions blindly without understanding their impact.

### 9.2. Why Must Legacy `opensaml-core` Be Excluded?

A structural change in OpenSAML 5 is that 4.x's **`opensaml-core` module was split into `opensaml-core-api` and `opensaml-core-impl`**. Spring Security 6.5 docs require updating the dependency graph when opting into 5 due to this change.

With 5.x, expect a consistent graph containing:
- `org.opensaml:opensaml-saml-api:5.x`
- `org.opensaml:opensaml-saml-impl:5.x`
- `org.opensaml:opensaml-core-api:5.x`
- `org.opensaml:opensaml-core-impl:5.x`
- Supporting modules and compatible XML Security/Shibboleth dependencies managed by BOM/metadata.

**Suspicious symptom:** `opensaml-saml-api:5.2.3` sitting next to `opensaml-core:4.x` or `opensaml-saml-impl:4.x`. The build may compile code that does not touch conflicting APIs, yet runtime SAML login fails when the classloader hits a method with a changed signature.

### 9.3. Do Not Confuse Spring Security Auto-Selection with Automatic Code Porting

After swapping JARs:
- Spring 6.5 config can select `OpenSaml5` components **if dependencies are right**.
- Custom beans instantiated by the application still must be migrated to 5.
- A Spring dependency patch may introduce specific API/support changes; run tests and inspect runtime logs.
- If package names match while class ABI changed, **compiling now does not guarantee old artifacts in the image were replaced**.
- Specifically verify CI caches, fat JAR packaging, Docker multi-stage images, runtime mounts, and BOM overrides.

## 10. Gradle: Selecting OpenSAML 5 with Explicit Constraints and Exclusions

With Gradle Kotlin DSL in an app using **Spring Security 6.5**, you can express the same goal:

```kotlin
repositories {
    mavenCentral()
    maven {
        url = uri("https://build.shibboleth.net/maven/releases/")
        mavenContent { releasesOnly() }
    }
}

dependencies {
    implementation("org.springframework.security:spring-security-saml2-service-provider") {
        exclude(group = "org.opensaml", module = "opensaml-core")
    }

    constraints {
        implementation("org.opensaml:opensaml-core-api:5.2.3")
        implementation("org.opensaml:opensaml-core-impl:5.2.3")
        implementation("org.opensaml:opensaml-saml-api:5.2.3")
        implementation("org.opensaml:opensaml-saml-impl:5.2.3")
    }

    implementation("org.opensaml:opensaml-saml-api:5.2.3")
    implementation("org.opensaml:opensaml-saml-impl:5.2.3")
}
```

**This is a directional example following the Gradle structure in Spring docs; review resolved dependencies**—if another library forces OpenSAML 4, excluding only `opensaml-core` on the dependency above is not enough. `constraints` can influence version selection, but do not replace checking the graph. With a corporate platform/BOM, prefer a single central place managing the OpenSAML version.

Post-upgrade commands:

```bash
./gradlew clean test
./gradlew dependencyInsight --dependency opensaml-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency opensaml-saml-api --configuration runtimeClasspath
./gradlew dependencyInsight --dependency opensaml-saml-impl --configuration runtimeClasspath
./gradlew dependencies --configuration runtimeClasspath
```

If the runtime graph still contains core 4, saml 4, or incompatible XML/Santuario, **the migration cannot be considered successful**. Never use `configurations.all { exclude group="org.opensaml" }` indiscriminately, as it can strip the OpenSAML 5 you need.

## 11. Option C: Spring Security 7.x Using OpenSAML 5

For **Spring Security 7**, the right choice is **OpenSAML 5**. Spring Security 7.0 What's New explicitly states it **removed OpenSAML 4 support**; the SAML2 Login reference describes `OpenSaml5AuthenticationProvider` as the default provider.

Normally prefer a **Spring Boot compatible BOM** and standard dependency, without copying over the 6.5 opt-in 5 exclusions verbatim:

```xml
<dependencies>
  <dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-saml2-service-provider</artifactId>
  </dependency>
</dependencies>
```

Do not add an `OpenSaml4AuthenticationProvider` bean to "preserve old logic." If you copied `org.opensaml` overrides from the 6.5 branch, **evaluate removing unnecessary overrides** and let the Boot/Spring platform select its tested dependency set; pin a specific OpenSAML 5 patch only when needed for an advisory fix and compatibility is verified.

### 11.1. Spring Boot 4 / Spring Security 7 Is Not Just a POM Change

The upgrade path from Boot 3 + Security 6 to Boot 4 + Security 7 also involves:
- Java 17 baseline; new Jakarta Servlet/EE platform versions.
- Spring Framework 7.x and configuration/lifecycle changes.
- Removed/deprecated Spring Security 7 APIs, e.g., `AssertingPartyDetails` → `AssertingPartyMetadata`.
- Changes in URI matching, response validation, principal/attributes, and SLO depending on customizations.
- Module splits and transitive dependency changes in Spring Boot 4.
- Customizations using OpenSAML 4 classes needing porting.

**Do not run Spring Security 7 on an incompatible Spring Framework/Boot version just because a few classes compile.** Per [migrating to 7](https://docs.spring.io/spring-security/reference/migration/), prefer stepping through 6.5 and updating maintenance releases of Boot 4/Security 7 on the supported migration path.

## 12. Migrating Custom Providers: From OpenSaml4... to OpenSaml5...

In projects with a custom SAML provider, you will commonly find imports like:

```java
import org.springframework.security.saml2.provider.service.authentication.OpenSaml4AuthenticationProvider;
```

In Spring Security 7, this import **is no longer valid**, and code must migrate to the 5 API:

```java
import org.springframework.security.saml2.provider.service.authentication.OpenSaml5AuthenticationProvider;
```

**Do not stop at renaming the import.** Converter, validator, and decrypter callbacks may have changed token types/method signatures. Examples in 6.5 docs or Javadoc of one patch may not compile verbatim on 7.1.

### 12.1. Provider Configuration Fragment in Spring Security with OpenSAML 5

The following example is a **Spring Boot/Spring Security Servlet fragment**, not runnable standalone Java SE; it requires `RelyingPartyRegistration` and the matching Spring Security version:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.authentication.OpenSaml5AuthenticationProvider;
import org.springframework.security.web.SecurityFilterChain;

public class SamlSecurityConfiguration {

    @Bean
    SecurityFilterChain samlSecurity(HttpSecurity http) throws Exception {
        OpenSaml5AuthenticationProvider provider =
            new OpenSaml5AuthenticationProvider();

        http.authorizeHttpRequests(auth ->
                auth.anyRequest().authenticated())
            .saml2Login(saml2 ->
                saml2.authenticationManager(new ProviderManager(provider)));

        return http.build();
    }
}
```

**When no customization is needed, use `saml2Login(Customizer.withDefaults())` and let Spring configure the default provider.** The snippet above is useful to show `OpenSaml5AuthenticationProvider` explicitly, but does not add `RelyingPartyRegistrationRepository`, IdP certificates, secrets, claims mapping, or SLO. Do not instantiate a new provider solely to force a version when Spring's auto-config already works properly.

### 12.2. OpenSAML Initialization

In custom components that invoke OpenSAML objects directly, Spring docs recommend using:

```java
static {
    OpenSamlInitializationService.initialize();
}
```

This snippet uses a class from **Spring Security SAML support** with the proper import, not a standalone Java SE demo. It differs from arbitrarily calling `org.opensaml.core.config.InitializationService.initialize()` multiple times or touching `XMLObjectProviderFactory` before initialization.

**Important:** proper initialization does not fix incompatibilities from mixed major JARs. `OpenSamlInitializationService` succeeding does not prove signature validators/cipher suites work in the end-to-end flow.

## 13. Customizations to Review When Moving to OpenSAML 5

Not every system needs only the default SSO flow. Projects frequently customize:

| Layer | What to Verify | Proof Test |
| --- | --- | --- |
| AuthnRequest factory | XML Object builders, NameIDPolicy, ForceAuthn, signing, RelayState. | Valid request matches IdP/ACS/algorithm. |
| SAML response provider | `OpenSaml4AuthenticationProvider` → `OpenSaml5AuthenticationProvider`. | Signed response passes, modified response fails. |
| Response validators | Issuer, Destination, InResponseTo, Status, NameID requirements. | Wrong Issuer/ACS/InResponseTo rejected. |
| Assertion validators | Conditions, audience, recipient, SubjectConfirmationData, clock skew. | Expired/wrong audience/replay fails. |
| Encryption/decryption | EncryptedAssertion, EncryptedAttribute, EncryptedID, decrypter strategies. | Sign-then-encrypt combinations work properly. |
| Principal conversion | NameID, attributes, local account mapping, authorities. | Principal/roles unchanged or intentionally updated. |
| RelyingPartyRegistration | `AssertingPartyDetails` API and new metadata API. | Multi-IdP resolution, correct verification cert. |
| SAML metadata parsing | XML schema, certificates, algorithm/endpoint bindings. | Trusted metadata only; reject unsigned tampering. |
| SAML Single Logout | LogoutRequest/Response signing, SessionIndex, session correlation. | Valid SLO completes, forged logout rejected. |
| XML ParserPool | Entity limits, XXE, encoding, request size constraints. | Oversized/XML abuse safely rejected. |
| Test fixtures | XML generated from OpenSAML 4 objects incompatible with 5 API. | Tests compile cleanly with major 5 and expected XML. |
| Build/test tooling | Classpath, Gradle/Maven plugins, test harness classloaders. | CI, fat JAR, and runtime image all consistent. |

**A custom `Saml2ResponseValidator` or `Saml2AuthenticationConverter` must never accidentally drop default validators.** Check the code and Javadoc of your running release; **chaining additional validation** is usually safer than replacing the whole validator unless a clear specification/threat model demands otherwise.

### 13.1. NameID Check and Validation Order Changes in Spring Security 7

The Spring Security 6.5 migration guide describes changing the response processing order in preparation for 7:
1. Verify the Response signature if present.
2. Decrypt the Response.
3. Validate assertions (verify signature, decrypt, conditions).
4. Validate Response fields like Destination/Issuer after processing assertions.

In some cases Spring Security 6 validated Response fields before assertion fields; Spring Security 7 reverses that order and removes certain NameID-related checks from the default step that custom response converters previously assumed.

**If a custom principal converter does not require NameID**, the new behavior can be helpful. However, if business identity mapping **requires NameID**, your custom converter/validator must explicitly verify its presence and valid value instead of assuming the earlier step enforced it.

The Spring Security 6.5 migration guide provides an option to preview 7 behavior early:

```java
OpenSaml5AuthenticationProvider provider =
    new OpenSaml5AuthenticationProvider();
provider.setValidateResponseAfterAssertions(true);
```

This snippet **is a migration-preparation API in Security 6.5 per documentation**; **do not assume the method still exists or needs to be called in every 7.x release**. On Spring Security 7, check Javadoc/current API and test behavioral expectations.

### 13.2. Decryption Order Is a Security Boundary

OpenSAML/Spring must accurately handle cases such as:
- Signed Response containing an encrypted assertion.
- Signed Assertion containing an encrypted attribute.
- Assertion encrypted and signed in combinations supported by the IdP.

`OpenSaml5AuthenticationProvider` has two decryption strategies:
- **Response elements decrypter**: for encrypted elements at the Response level, e.g., EncryptedAssertion.
- **Assertion elements decrypter**: for encrypted elements inside an Assertion, e.g., EncryptedAttribute/EncryptedID.

**Never decrypt parts of a signed Assertion before verifying the signature in the order required by the provider**, as that can alter XML/canonicalization and invalidate signatures, or worse, blur trust boundaries. [Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html) shows examples of customizing the two decrypters separately.

### 13.3. SLO and Request Bindings

When changing majors, test:
- Signed AuthnRequest HTTP-Redirect/POST, signature algorithms, canonicalization.
- IdP SSO Binding URL and RelayState encoding.
- ACS HTTP POST, `InResponseTo`, and request repository.
- LogoutRequest/LogoutResponse XML signing/verification, SLO correlation, and local sessions.
- SAML metadata generation, signed metadata trust, certificate rotation.
- IdP-initiated if policy permits; never enable unsolicited SSO just for migration.

**A happy-path SAML login does not prove SLO or encrypted assertions still work.**

## 14. Real Dependency Conflicts: Look at Artifact Groups, Not Just the Last Error

### 14.1. Conflict Type 1: Both OpenSAML 4 and 5 Present

```text
spring-security-saml2-service-provider:6.5.x
  -> opensaml-saml-api:4.x

application
  -> opensaml-saml-impl:5.x
  -> opensaml-core-impl:5.x

RESULT: mixed major / incompatible API risk
```

Maven/Gradle may pick one version for matching coordinates yet leave modules from a different major on the same runtime. **The classloader succeeding on one class does not mean all OpenSAML APIs are compatible.**

**Fix:** inspect `dependency:tree`/`dependencyInsight`, exclude transitive 4 properly, bring in the full 5 dependency set on the same version, and run a clean full build + SAML integration tests.

### 14.2. Conflict Type 2: Third-Party Library Pulls Old OpenSAML

A WS-Security library might use OpenSAML 4 to verify SAML assertions in SOAP while the Spring SAML login app uses 5. For instance, Apache WSS4J 3.x has an OpenSAML 4 lineage, whereas WSS4J 4.x moves to OpenSAML 5/Java 17.

**Do not force the entire project into a mixed graph.** Choose compatible integration library versions, split modules/processes if needed, or defer upgrading to Spring 7 in a controlled manner. An exclusion on the Spring SAML module will not resolve dependencies pulled in elsewhere by WSS4J.

### 14.3. Conflict Type 3: Deployed Fat JAR Differs from Checked Runtime Tree

- CI build has OpenSAML 5, yet the container image retains an old artifact from cache.
- `BOOT-INF/lib/` contains both 4 and 5 jars or mismatched patch jars.
- Application server shared classloader loads OpenSAML 4 ahead of the app classpath.
- IDE runs with a classpath different from Maven tests.
- A dependency shades/relocates classes unseen in the SBOM.
- Partial rolling upgrade leaves pods on different Spring Security/OpenSAML majors during SSO callbacks.

**Mitigation:** inspect resolved dependencies, inspect the packaged artifact, build reproducible images, verify SBOM, compare build hashes/dependency graphs, and test startup on the exact production container image.

### 14.4. Conflict Type 4: JAXB/Jakarta and XML Security

A missing `javax.servlet.*` or `jakarta.*` mismatch error usually comes from the **Servlet stack**, not "OpenSAML doesn't run on new JDKs." Errors in `org.apache.xml.security` can come from mismatched XML Security libraries. Trace **class name, declaring artifact, dependency edge, and deployed classpath**.

**Never "fix" it by dropping random JARs from the Internet into `lib/`** until startup stops failing; that can leave multiple XML signature implementations and parser vulnerabilities active.

## 15. Security: EOL and Advisories Must Drive Decisions

Shibboleth states OpenSAML 5 is the current Java major based on Java 17; prior majors are **end of life**. The goal of migration is not merely API compatibility, but **continuing to receive security fixes**.

Required assessments:
- Are there advisories affecting the parser, XML signature, encryption/decryption, SAML inflate, resource exhaustion, or unsafe deserialization?
- Does the running Spring Security patch version include the corresponding security fixes?
- Is the pinned OpenSAML 5 patch within a supported/actively updated version?
- Are the Shibboleth artifact repository and Spring Security version approved in the enterprise?
- Do JDK XML parser properties and request-body limits protect against DoS?
- Are `SubjectConfirmation`, Audience, Recipient, Destination, replay, signature policy, and certificate trust verified post-upgrade?

**A concrete milestone:** the [May 13, 2026 OpenSAML security advisory](https://shibboleth.net/pipermail/announce/2026-May/000384.html) notes OpenSAML **5.2.2** adds default parser limits against a DoS vector. Therefore, older 6.5 docs examples using **5.1.2** must not be copied as "a recommended secure version for 2026." The 5.2.3 example above is a verified release in the Shibboleth repository; always evaluate newer security advisories and compatibility before release.

[Spring Security Releases 2026-06-09](https://spring.io/blog/2026/06/09/spring-security-releases-2026-06/) also published CVEs related to SAML inflation/decryption and other Security areas. **Never equate an OpenSAML fix with a Spring Security fix**: both layers must be updated per advisories and dependency policy.

### 15.1. Release-Day Library Verification Checklist

```text
[ ] Spring Security selected supported maintenance line
[ ] OpenSAML major matches Spring Security line
[ ] OpenSAML minor/patch reviewed against Shibboleth advisories
[ ] Spring Security patch reviewed against Spring advisories
[ ] Java and servlet/Jakarta platforms compatible
[ ] No mixed OpenSAML 4/5 modules in runtime
[ ] Signature, encryption, replay and XML parsing tests pass
[ ] SBOM, artifact provenance and checksum verified
[ ] Staged canary and emergency rollback strategy approved
```

**Safe rollback** is different from "rolling back to a critically vulnerable library." If only a known-vulnerable old image exists, evaluate containment/temporarily disabling SAML login rather than automatically re-enabling exposure.

## 16. Two-Phase Upgrade Roadmap to Reduce Risk

### Phase A: Prepare on Spring Security 6.5

1. Lock an approved Boot/Spring Security **6.5 maintenance patch**.
2. Run all existing SAML integration tests with OpenSAML 4 to create a baseline.
3. Audit custom imports of `OpenSaml4`, OpenSAML XML builders, validators, decryptors, and metadata utilities.
4. Update dependencies to OpenSAML 5 per 6.5 guidance and pin a compatible patch.
5. Port custom code to `OpenSaml5` APIs while preserving validation semantics.
6. Verify classpath/repository/fat jar/Java 17 runtime.
7. Test SSO/SLO/encryption/metadata, multi-IdP, tampered assertions, wrong audience, and replay.
8. Canary with the test IdP, measuring login success/rejection reason codes; avoid changing IdP config and SAML library simultaneously unless necessary.
9. Record evidence: dependency tree, artifacts, tests, security sign-off.

**Phase A Gate:** Spring Security 6.5 + OpenSAML 5 runs in the same environment with accurate negative tests. This separates **OpenSAML major upgrade** issues from **Spring Security major upgrade** issues.

### Phase B: Move to Spring Security 7

1. Check the official migration guide for the exact Spring Security 7 patch and compatible Boot line.
2. Upgrade Spring Boot/Framework/Security per the supported matrix; never upgrade the Security module in isolation.
3. Remove remaining Java/OpenSAML 4 customizations and check removed/deprecated classes.
4. Evaluate `AssertingPartyDetails` → `AssertingPartyMetadata` changes.
5. Evaluate response validation order and custom NameID/Principal mapping.
6. Evaluate `Saml2WebSsoAuthenticationFilter` behavior when no `RelyingPartyRegistration` matches, avoiding redirect loops.
7. Re-run unit/integration/contract tests, SAML SLO, metadata, and cache/data migrations.
8. Test rollout across pods/instances and rollback of configs/IdP registrations.
9. Update dashboards, SBOM, change control, and incident response.
10. Promote once all canary/negative tests pass.

**Avoid bundling simultaneously:** OpenSAML major, Boot major, IdP certificate rotation, IdP metadata refresh algorithm, and tenant role mapping in a single change whenever avoidable. A step crossing many boundaries makes root-cause analysis very hard when login fails.

## 17. Runnable Java 17: OpenSAML Selection Policy Checker

The following example **runs standalone on Java 17**, without real Spring/OpenSAML. It models the rules confirmed above and classifies a dependency version inventory. The booleans represent **results inspected from the Maven/Gradle runtime graph**, not data read dynamically from the classpath. This model **does not replace** a dependency audit or integration test.

Create file **`OpenSamlCompatibilityAdvisor.java`**:

```java
public final class OpenSamlCompatibilityAdvisor {

    record Stack(
        int springMajor,
        int springMinor,
        int javaVersion,
        boolean hasOpenSaml4,
        boolean hasOpenSaml5,
        boolean legacyCore4,
        boolean customOpenSaml4Code) {}

    static String decide(Stack s) {
        if (s.javaVersion() < 17) {
            return "BLOCK_JAVA_BELOW_17";
        }
        if ((s.hasOpenSaml4() && s.hasOpenSaml5())
                || (s.legacyCore4() && s.hasOpenSaml5())) {
            return "BLOCK_MIXED_OPEN_SAML";
        }
        if (s.springMajor() >= 7) {
            if (s.hasOpenSaml4()) {
                return "BLOCK_OPEN_SAML_4_REMOVED";
            }
            if (!s.hasOpenSaml5()) {
                return "BLOCK_OPEN_SAML_5_MISSING";
            }
            if (s.customOpenSaml4Code()) {
                return "BLOCK_CUSTOM_OPEN_SAML_4_CODE";
            }
            return "READY_SPRING_7_OPEN_SAML_5";
        }
        if (s.springMajor() == 6 && s.springMinor() == 5) {
            if (s.hasOpenSaml5()) {
                if (s.customOpenSaml4Code()) {
                    return "BLOCK_CUSTOM_OPEN_SAML_4_CODE";
                }
                return "READY_6_5_OPEN_SAML_5_OPT_IN";
            }
            if (s.hasOpenSaml4()) {
                return "LEGACY_6_5_OPEN_SAML_4_DEFAULT";
            }
            return "BLOCK_OPEN_SAML_MISSING";
        }
        return "VERIFY_PINNED_SPRING_DOCUMENTATION";
    }

    static void show(String label, Stack stack) {
        System.out.println(label + "=" + decide(stack));
    }

    public static void main(String[] args) {
        show("S65_DEFAULT",
             new Stack(6, 5, 17, true, false, true, false));
        show("S65_OPT_IN",
             new Stack(6, 5, 17, false, true, false, false));
        show("S71_NORMAL",
             new Stack(7, 1, 17, false, true, false, false));
        show("S71_WITH_4",
             new Stack(7, 1, 17, true, false, true, false));
        show("MIXED_MAJORS",
             new Stack(7, 1, 17, true, true, true, false));
        show("LEGACY_CORE_4",
             new Stack(6, 5, 17, false, true, true, false));
        show("CUSTOM_PROVIDER_4",
             new Stack(6, 5, 17, false, true, false, true));
        show("JAVA_11",
             new Stack(7, 1, 11, false, true, false, false));
        show("MISSING_5",
             new Stack(7, 0, 17, false, false, false, false));
        show("OTHER_SPRING",
             new Stack(6, 4, 17, true, false, true, false));
    }
}
```

Compile and run:

```bash
javac OpenSamlCompatibilityAdvisor.java
java OpenSamlCompatibilityAdvisor
```

**Exact stdout:**

```text
S65_DEFAULT=LEGACY_6_5_OPEN_SAML_4_DEFAULT
S65_OPT_IN=READY_6_5_OPEN_SAML_5_OPT_IN
S71_NORMAL=READY_SPRING_7_OPEN_SAML_5
S71_WITH_4=BLOCK_OPEN_SAML_4_REMOVED
MIXED_MAJORS=BLOCK_MIXED_OPEN_SAML
LEGACY_CORE_4=BLOCK_MIXED_OPEN_SAML
CUSTOM_PROVIDER_4=BLOCK_CUSTOM_OPEN_SAML_4_CODE
JAVA_11=BLOCK_JAVA_BELOW_17
MISSING_5=BLOCK_OPEN_SAML_5_MISSING
OTHER_SPRING=VERIFY_PINNED_SPRING_DOCUMENTATION
```

### 17.1. Output Analysis

- `S65_DEFAULT`: matches default 6.5 behavior, but EOL risk requires a migration plan.
- `S65_OPT_IN`: 6.5 can use 5 if the graph and custom code are aligned.
- `S71_NORMAL`: 7.x using OpenSAML 5 is the valid major choice.
- `S71_WITH_4`: 7.x + 4 is unsupported.
- `MIXED_MAJORS`: app has both 4 and 5; rollout should be blocked.
- `LEGACY_CORE_4`: core 4 remains alongside 5 even though the main dependency changed.
- `CUSTOM_PROVIDER_4`: custom code/bytecode still references Spring `OpenSaml4...`.
- `JAVA_11`: Java 11 fails the baseline.
- `MISSING_5`: Spring 7 has no OpenSAML 5 on the classpath.
- `OTHER_SPRING`: open the docs for that exact branch; do not extrapolate the 6.5 matrix.

**Important limitation:** "READY" only indicates **preliminary major-selection eligibility**; it **does not prove CVE-free status**, valid signatures, library ABI compatibility, established IdP trust, or that every supporting module shares the same patch. The booleans are not read from HTTP input and the program cannot scan a Maven project. This is a decision-logic exercise, not a deployable security tool.

## 18. Testing After Switching Majors — Beyond a Green Build

| Test Group | Positive Case | Negative / Regression Case |
| --- | --- | --- |
| Build/dependency | Clean Maven/Gradle build, single OpenSAML major at runtime. | Inject OpenSAML 4/5 conflict and verify gate blocks it. |
| Startup | Spring Boot context starts, SAML provider and registrations initialize. | Missing XML core/helper or classloader mismatch must fail clearly. |
| AuthnRequest | SP builds request for right IdP/ACS, signed per policy. | Invalid IdP/registration or malformed request rejected. |
| SAMLResponse POST | Trusted IdP returns valid response; login creates Authentication. | Modified XML/signature rejected. |
| Issuer | Expected IdP issuer matches. | Wrong issuer/unknown IdP never auto-trusted. |
| Audience | Assertion targets exact SP EntityID. | Audience for another service rejected. |
| Destination/Recipient | Public ACS URL matches. | Wrong scheme/host/path rejected. |
| InResponseTo | Response ties to matching request/session. | Mismatch/no pending AuthnRequest rejected per SP-initiated policy. |
| Replay | Single-use assertion. | Re-POSTing same assertion/response blocked across multi-node. |
| Conditions | Valid NotBefore/NotOnOrAfter. | Expired/future assertion fails per clock skew. |
| XML parsing | Valid signed SAML XML parses normally. | XXE, oversized XML, dangerous compression constrained. |
| EncryptedAssertion | Valid SP decryption private key, valid signed response. | Wrong key/ciphertext rejected, no plaintext fallback. |
| EncryptedAttribute | Decrypted in proper order relative to signature validation. | Pre-signature decryption breaks validation or gets rejected. |
| NameID/principal | Expected NameID/attributes mapped accurately. | Missing NameID handled per business security policy, no NPE. |
| Authorities | Verified groups/tenant map to right roles. | Admin role never granted from untrusted attribute. |
| SP metadata | EntityID/ACS/signing and encryption certs match contract. | Private key never exposed; unexpected metadata cert not auto-trusted. |
| SLO | Signed LogoutRequest/Response and SessionIndex accurate. | Forged logout or wrong SessionIndex rejected. |
| Multi-IdP | Each registration uses its right trusted cert/issuer. | Cert/Issuer from IdP A never accepted for IdP B. |
| Session/cookie | Browser POST SAMLResponse preserves proper state. | SameSite, multi-tab, pod failover never allow bypass. |
| Rollout | Canary containers run same version, metrics stable. | Old/new pod state mismatch detected; rollback policy safe. |

**A validly signed SAMLResponse is not enough to create a local admin user.** After cryptographic validation come local account status, tenant mapping, RBAC, and session fixation protection.

### 18.1. Key Upgrade Metrics

```text
saml_login_success_total{registration,build}
saml_login_failure_total{registration,reason,build}
saml_signature_rejected_total{registration}
saml_audience_rejected_total{registration}
saml_in_response_to_mismatch_total{registration}
saml_assertion_decrypt_failed_total{registration}
saml_assertion_replay_rejected_total{registration}
saml_metadata_refresh_failed_total{registration}
saml_slo_error_total{registration}
```

Never record raw `SAMLResponse`, `SAMLRequest`, private keys, NameID, Session ID, RelayState, or user identifiers as metric labels. Attach **build version, OpenSAML major, and config version** in cardinality-controlled labels to pinpoint post-rollout errors.

## 19. Diagnosing Runtime Incompatibility Errors

| Symptom | Cause Category | Verification and Fix |
| --- | --- | --- |
| `ClassNotFoundException: OpenSaml4AuthenticationProvider` | Spring Security 7 removed API 4. | Find custom imports/beans and port to OpenSaml5. |
| `NoClassDefFoundError: org/opensaml/core/...` | Missing OpenSAML 5 core API/impl or mixed classpath. | Dependency tree, fat jar, version alignment. |
| `NoSuchMethodError` in OpenSAML classes | API/binary incompatible versions. | Check declaring artifact + resolved/runtime jar; never drop in random JARs. |
| `ClassNotFoundException: javax.servlet...` | Legacy servlet dependency in Jakarta runtime. | Switch to compatible library/Servlet namespace; do not downgrade Java. |
| Cannot resolve `opensaml-saml-impl` | Repository/build dependency issue. | Add Shibboleth releases or approved corporate mirror; never arbitrary snapshots. |
| App still uses OpenSaml4 bean on 6.5 opt-in 5 | Custom code not auto-migrated. | Update bean/import/callback API, compile and run tests. |
| SAMLResponse fails signature | Verification cert/IdP config, algorithm, or parsing difference. | Compare issuer/trust cert, signed XML, version; never disable signature. |
| EncryptedAssertion fails decryption | Wrong SP key/algorithm/decrypter order. | Test response-level vs. assertion-level decrypter. |
| NameID test fails after upgrading to 7 | Response validation/converter behavior changed. | Review custom NameID policy and response authentication converter. |
| SAML ACS 302 loop | Missing-registration/entry-point behavior in 7. | Inspect filter chain and no-registration fallback; preserve deny policy. |
| SLO fails while login succeeds | LogoutMessage validator/metadata/binding differs. | Test SLO separately: signing/cert/session index. |
| Parser rejects large assertion | XML parser size/depth limits and request body limits. | Verify actual legitimate size; never disable security limits blindly. |
| Security scanner detects OpenSAML 4 | Transitive WSS4J/legacy jars or stale fat JAR. | Dependency graph, cache, artifact inventory; never suppress with fake exclusions. |
| Failure appears only after deploy, not in IDE | Runtime classloader, image, shared libs differ. | Inspect packaged JAR/SBOM/image and JVM versions. |
| OpenSAML 5 works in 6.5 but fails in 7 | Spring Security major migration APIs/behavior. | Check 7 migration guide, response order, `AssertingPartyMetadata`, filter matchers. |

### 19.1. Separating Build Errors from Protocol Errors

- **Build failure**: removed import/class → fix source/dependency.
- **Runtime linkage failure**: `NoSuchMethodError`/`NoClassDefFoundError` → fix resolved JAR/ABI.
- **Startup configuration failure**: missing repository/registration/cert → fix Spring bean/config.
- **SAML protocol failure**: invalid signature, issuer, audience, recipient, replay → fix trust/protocol.
- **Local authorization failure**: account disabled, missing tenant/role → unrelated to OpenSAML major.
- **Browser/session failure**: SameSite, ACS, RelayState, multi-tab → diagnose SSO state and proxies.

Never lump everything together as "OpenSAML 5 bug." An `invalid SAMLResponse` error may mean validators are **rightfully rejecting** an invalid assertion.

## 20. Common Anti-Patterns

1. **"Spring Security 7 + OpenSAML 4 still works via POM overrides."** False: support for 4 classes was removed.
2. **"Every Spring Security 6.x auto-selects OpenSAML 5."** Do not assume; check docs for your exact version.
3. **"Changing only `opensaml-saml-api` version is enough."** False: core, impl, and supporting modules also matter.
4. **"Having OpenSAML 4 + 5 on the classpath helps backward compatibility."** Usually creates ABI/classpath conflict risk.
5. **"One Maven exclusion removes all transitive 4 libraries."** False if another library still pulls 4.
6. **"Custom OpenSaml4 provider renames itself on Boot upgrade."** False: custom code must be ported.
7. **"Java 11 runtime works because Maven compiled on 17."** False for OpenSAML 5/Boot 3/4.
8. **"Missing javax.servlet means Java 21 doesn't support OpenSAML."** Usually caused by Jakarta namespace mismatch.
9. **"Copying 5.1.2 from 6.5 docs as a secure 2026 version."** Must check recent security advisories/patches.
10. **"Disable XML parser size limits to bypass errors."** Can open DoS exposure.
11. **"Replace signature validator with no-op to make login pass."** Destroys trust boundary.
12. **"Metadata fetched over HTTPS automatically establishes cert trust."** Requires metadata signature/approved trust bootstrap.
13. **"Valid response signature means audience doesn't matter."** False.
14. **"SAML login works so SLO works automatically."** False; test separately.
15. **"Green unit tests alone suffice without IdP E2E."** False; signed/encrypted/bindings require real testing.
16. **"Presence of one `OpenSaml5AuthenticationProvider` class means the classpath is clean."** False; supporting libs still matter.
17. **"Legacy `spring-security-saml` can replace the SAML2 SP module."** Not the current official artifact.
18. **"Downgrade Spring Security patch to stay compatible with broken XML."** Increases exposure if the patch contains security fixes.
19. **"Copy custom XML signature classes from OpenSAML 4 to 5 without review."** APIs and validation order may differ.
20. **"Rolling back to an old image is easier than a security review."** Unacceptable if the image is known vulnerable.
21. **"Upgrade OpenSAML at the same time as rotating IdP cert/ACS/roles."** Makes root-cause isolation hard and raises risk.
22. **"Working SAML signing means decryption and metadata don't need testing."** False.
23. **"Boot BOM auto-resolves everything despite ad-hoc dependency overrides."** Overrides can break the graph; verify actual resolution.
24. **"Snapshots are newest so they are safer."** No production support or security guarantees.
25. **"Test in CI using raw production assertions."** Risks exposing bearer tokens and PII.

## 21. QA Checklist Before Production Upgrade

1. Identify exact current Boot, Spring Security, Java, and Servlet/Jakarta versions.
2. Reconcile the 6.5 vs. 7.x matrix against docs for the exact release.
3. Never use OpenSAML 4 on Spring Security 7.
4. If on 6.5, evaluate opting into OpenSAML 5 before upgrading to 7.
5. All `org.opensaml` modules and supporting libs share the same major/compatible patch.
6. No legacy `opensaml-core:4.x` remains in an OpenSAML 5 runtime.
7. Dependency lock/BOM/corporate-approved repositories/SBOM are in place.
8. Actual runtime Java is ≥17 when using OpenSAML 5.
9. No legacy Servlet `javax.*` exists inside incompatible Jakarta components.
10. No custom `OpenSaml4...` imports/beans remain when targeting 5/7.
11. App compiles and runs tests against the packaged image, not only the IDE.
12. AuthnRequest builds for the right registration/ACS, signing key/algorithm.
13. Signed SAMLResponse passes; modified response fails.
14. Wrong issuer/audience/recipient/destination/time/replay are denied.
15. EncryptedAssertion/EncryptedAttribute decrypt in the right order and fail on wrong keys.
16. Custom response validators and NameID/Principal mapping work after Security 7 changes.
17. SLO, metadata, multi-IdP, and cert rotation are E2E tested.
18. Session/callback paths, browser POST, RelayState, and InResponseTo remain intact.
19. XML parser/resource limits continue to block XXE/DoS.
20. Spring/OpenSAML patches are checked against advisories near release time.
21. Canary, alarms/metrics, rollback/disable plan, and security review are in place.
22. Never log raw SAMLResponses, private keys, NameIDs, or browser cookies.
23. Security/IdP/ops team ownership and change evidence are clearly recorded.
24. Approvers confirm **no fail-open behavior** exists in security validators.

## 22. Self-Check Questions

1. **Which OpenSAML does Spring Security 6.5 use by default?** — OpenSAML 4 per 6.5 documentation.
2. **Can 6.5 use OpenSAML 5?** — Yes, by opting in via dependencies and compatible custom code.
3. **Does Spring Security 7.x support OpenSAML 4?** — No; Spring 7 removed it.
4. **Which Java version does OpenSAML 5 require?** — Java 17 or later per the Shibboleth platform.
5. **What is the exact SAML Service Provider dependency name?** — `spring-security-saml2-service-provider`.
6. **Does `OpenSaml4AuthenticationProvider` work on 7 automatically?** — No; port to OpenSaml5.
7. **Why inspect the dependency tree instead of only the POM?** — Runtime transitives/corporate overrides can pull mixed majors.
8. **How did OpenSAML 5 change the core module?** — From `opensaml-core` to `opensaml-core-api` and `opensaml-core-impl`.
9. **Why must API/impl share the same major?** — Avoid `ClassNotFound`/`NoSuchMethodError` and semantic mismatch.
10. **Should Spring Boot and Security be upgraded independently?** — Follow the supported BOM/migration path; do not force mismatched modules.
11. **Does OpenSAML 5 make valid SAML signatures optional?** — No; all checks remain mandatory.
12. **Why test SLO separately?** — Login and logout use different messages, keys, and validators.
13. **Which Maven repo do docs use for Shibboleth?** — `https://build.shibboleth.net/maven/releases/`.
14. **When seeing a `javax.servlet` `NoClassDefFoundError`, what should you check?** — Servlet/Jakarta compatibility, not guessing the Java version.
15. **After moving to 7, what must custom NameID conversion check?** — Default response validation order and converter responsibilities.
16. **Why does OpenSAML 4 EOL impact architecture?** — That major no longer receives security maintenance.
17. **Can you copy 5.1.2 from 6.5 docs without checking advisories?** — No.
18. **Does one `OpenSaml5` class present prove deployment is valid?** — No; dependency tree and runtime tests are still needed.
19. **How to reduce upgrade risk?** — 6.5 + OpenSAML 5 first, then Security 7, with tests and canary.
20. **What constitutes a real QA PASS?** — Right major/dependencies, Java/platform, cryptographic validation, SLO, negative tests, audit, and safe rollback.

## Official Reference Documentation

- [Spring Security 6.5 — OpenSAML Support: selecting OpenSAML 4/5 and dependency examples](https://docs.spring.io/spring-security/reference/6.5/servlet/saml2/opensaml.html)
- [Spring Security 6.5 — SAML2 Migration to Spring Security 7](https://docs.spring.io/spring-security/reference/6.5/migration-7/saml2.html)
- [Spring Security 7.0 — What's New (removed OpenSAML 4)](https://docs.spring.io/spring-security/reference/7.0/whats-new.html)
- [Spring Security 7 — SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html)
- [Spring Security 7 — Authenticating SAML Responses, validators and decryption](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html)
- [Spring Security — Migration Guide](https://docs.spring.io/spring-security/reference/migration/)
- [Shibboleth OpenSAML — project overview, Java 17 and end-of-life policy](https://shibboleth.atlassian.net/wiki/spaces/OSAML/overview)
- [Shibboleth Product Platforms — Java 17 platform for OpenSAML 5](https://shibboleth.atlassian.net/wiki/spaces/DEV/pages/1161266638/Product%2BPlatforms)
- [Shibboleth Releases Repository — OpenSAML BOM and releases](https://build.shibboleth.net/maven/releases/org/opensaml/opensaml-bom/)
- [OpenSAML Security Advisory — 13 May 2026 parser limits](https://shibboleth.net/pipermail/announce/2026-May/000384.html)
- [Spring Security Releases June 2026 — SAML-related CVEs](https://spring.io/blog/2026/06/09/spring-security-releases-2026-06/)
- [Spring Boot System Requirements — Java, Servlet, Framework compatibility](https://docs.spring.io/spring-boot/system-requirements.html)
- [Apache WSS4J — SAML/OpenSAML compatibility matrix](https://ws.apache.org/wss4j/)