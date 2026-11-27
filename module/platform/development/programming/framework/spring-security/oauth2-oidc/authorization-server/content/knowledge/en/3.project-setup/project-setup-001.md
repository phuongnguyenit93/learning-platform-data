# Selecting a Compatible Version Stack of Java, Spring Boot, and Spring Security

> **Chapter:** Project Setup  
> **Learning Scope:** Designing, configuring, securing, testing, and operating an OAuth 2.0/OpenID Connect Authorization Server using Spring Security and Spring Authorization Server in a Spring Boot application.

## Learning Objectives

After this lesson, you will be able to:

1. Explain why **Java, Spring Boot, Spring Framework, Spring Security, and Authorization Server** must be chosen as a compatible stack.
2. Distinguish between the **Spring Authorization Server 1.x with Spring Security 6.x** model and the **Authorization Server integrated into Spring Security 7.x** generation.
3. Choose an appropriate version stack for a new project or a project under maintenance, taking support lifecycle and security patches into account.
4. Leverage Spring Boot's dependency version management mechanism instead of manually combining incompatible versions.
5. Verify the Java and dependency versions actually used when building, testing, and running the application.

This lesson focuses on **version decisions and build configuration**. Registering clients, generating signing keys, configuring filter chains, and implementing OAuth 2.0/OIDC endpoints will be covered in their respective topics.

## 1. Why Is an Authorization Server Sensitive to Versions?

An Authorization Server handles critical security components: authenticating users and clients, issuing authorization codes, access tokens, refresh tokens, and ID tokens, validating redirect URIs, enforcing PKCE, and managing consent and signing keys. A dependency change can affect configuration APIs, security filters, endpoints, or default behavior.

Viewed along the dependency hierarchy, the application typically has the following structure:

~~~mermaid
flowchart TB
    J["Java/JDK<br/>Compilation and runtime platform"]
    FW["Spring Framework<br/>Web, DI, ApplicationContext"]
    B["Spring Boot<br/>Auto-configuration, starter, BOM"]
    S["Spring Security<br/>Authentication, filter chain, OAuth2"]
    A["OAuth2/OIDC Authorization Server<br/>Endpoint, token, registered client"]
    P["Your Spring Boot application"]

    J --> FW
    FW --> B
    B --> S
    S --> A
    A --> P
~~~

The diagram illustrates the **layers of responsibility and compatibility**, not that Maven/Gradle source files necessarily declare dependencies in this exact shape. In practice, Spring Boot manages a set of versions via dependency management, and starters pull the required libraries into the project.

A version stack must simultaneously satisfy:

- **A compatible JDK** with the requirements of the Spring Boot branch and runtime environment.
- **Spring Boot from the same generation as the Spring Framework and Spring Security** versions it supports.
- **Authorization Server from the same generation as Spring Security**, because it relies heavily on Spring security APIs.
- **Additional libraries and build plugins** that work with that version stack.
- **A branch that is still supported under the project's policy** and has an upgrade path for security patches.

Seeing the application compile successfully is **not enough** to prove the system is secure or supported: some issues only surface at startup, during token exchange, or when the Resource Server verifies a token.

## 2. Understanding How Versions Relate to One Another

| Component | Role in the Problem | Selection Rule |
| --- | --- | --- |
| **Java / JDK** | Language, bytecode, JVM, TLS, and platform APIs | Choose a JDK version supported by the Spring Boot branch; align build, CI, container image, and production |
| **Spring Boot** | Starters, auto-configuration, dependency management, packaging | Choose a maintained release and pin the exact patch version in the build |
| **Spring Framework** | Dependency injection, web stack, lifecycle, HTTP | Usually let Spring Boot manage it; do not force a different Framework version manually |
| **Spring Security** | Filter chain, authentication, authorization, and OAuth 2.0/OIDC components | Prefer the version managed by the Spring Boot BOM |
| **Authorization Server** | OAuth 2.0/OIDC endpoints, token issuance, client/authorization/consent | Choose the API/library matching the **Spring Security generation** in use |
| **Maven/Gradle** | Dependency resolution, compilation, testing, packaging | Choose a tool version compatible with the JDK and Spring Boot; use the wrapper committed to the project |

### 2.1. What Do Java 17, Java 21, and Java 25 Mean?

Java 17, 21, and 25 are all Java **LTS** releases. However, "LTS" does not mean "immediately supported by every Spring Boot version" or "compatible with every library."

For Authorization Server hands-on exercises, **Java 21** is a straightforward baseline: modern enough, has LTS support, and fits both Spring Boot 3.x and 4.x generations when using branches that support Java 21. If an organization is constrained to Java 17, you can choose a Spring Boot branch that supports Java 17 and its corresponding libraries. When wanting to use Java 25, you need to explicitly check the **release notes of the specific Spring Boot version selected**, Java toolchain, drivers, and container images.

Distinguish three values that are often confused:

1. **JDK running Maven/Gradle:** used to launch the build tool and plugins.
2. **Java toolchain / compiler release:** determines the JDK used to compile and the bytecode/API level of the application.
3. **Production JRE/JDK:** the JVM actually running the JAR file or container image.

For example, an application compiled with `--release 21` cannot run on JVM 17. In CI, changing only `JAVA_HOME` without checking the compiler toolchain can cause the build machine and container to target two different platforms.

### 2.2. Do Not Infer Compatibility from Version Numbers Alone

The three Spring products do not always share the same major version number:

- Spring Boot **3.x** runs on the Spring Framework **6.x** and Spring Security **6.x** generation.
- Spring Boot **4.x** belongs to the Spring Framework **7.x** and Spring Security **7.x** generation.
- With Spring Security **6.x**, Authorization Server is used via the **Spring Authorization Server 1.x** branch.
- Starting with the Spring Security **7.x** generation, Authorization Server functionality is integrated into Spring Security; you need to use the documentation and dependency declarations intended for the **7.x generation**.

Therefore, the right question is not "what is the latest Spring Security version I should install?", but rather "**which Spring Security version does my Spring Boot manage, and which generation's API does my Authorization Server use?**".

## 3. Two Main Selection Paths for Authorization Server

The table below is a **generation map** for orientation, not a list of the latest patch versions at deployment time. Verify the support policy and the versions managed by the Spring Boot BOM before finalizing a production release.

| Context | Java to Consider | Spring Boot | Spring Security | Authorization Server Component | Meaning |
| --- | --- | --- | --- | --- | --- |
| Application based on **Spring Authorization Server 1.x** APIs | Java 21; or Java 17 if requirements dictate | **3.5.x** | **6.5.x** | **Spring Authorization Server 1.5.x** | Versions from the same generation, convenient when learning or maintaining SAS 1.x codebases |
| Application based on Spring Boot 3.4 | Suitable Java 17/21 | **3.4.x** | **6.4.x** | **Spring Authorization Server 1.4.x** | Compatibility baseline for reading and maintaining older projects; verify support status before using |
| New application choosing the modern Spring generation | Java 21 is a reasonable starting baseline | **4.x** | **7.x** | **Authorization Server in the Spring Security 7.x ecosystem** | Choose starters and APIs per the Boot 4/Security 7 branch documentation; assess migration if SAS 1.x code exists |

**Important reading note:** the `x` placeholders denote minor branches. The **actual patch version** is determined by BOM/Gradle dependency resolution and must be verified with the build tool. The branch pairings in the table do not guarantee that every patch in a branch supports every future JDK or remains under support at the time you read this article.

### 3.1. Example Stack for Learning Spring Authorization Server 1.x APIs

If your goal is to learn Spring Authorization Server 1.x style configuration (such as `RegisteredClientRepository`, `OAuth2AuthorizationService`, and Spring Security 6 examples), a suitable learning baseline is:

~~~text
JDK                 = Java 21
Spring Boot         = 3.5.x
Spring Framework    = 6.2.x (managed by Spring Boot)
Spring Security     = 6.5.x (managed by Spring Boot)
Authorization Server= 1.5.x (managed by Spring Boot when using the appropriate starter/BOM)
Build tool          = Maven Wrapper or Gradle Wrapper
~~~

**Do not manually pin** patch numbers for Spring Security, Spring Framework, and Spring Authorization Server just to "match" the numbers in the table. Check the exact versions managed by a specific Spring Boot release, and prefer patch versions with bug/security fixes that are still within your organization's support policy.

This is a **learning and API reference baseline**, not an automatic recommendation to use Spring Boot 3.5 for every new production project at any given time. Production decisions also depend on whether the branch is still within or past its open-source/commercial support window.

### 3.2. Example Stack for New Projects Using Spring Security 7

For a newly initialized project on Spring Boot 4, start from a **maintained Spring Boot 4.x release**, keep Spring Security and Spring Framework aligned with that release's BOM, and use the Authorization Server starter/configuration **explicitly specified in that branch's documentation**.

~~~text
JDK                 = Java 21 (check the official requirements of the release)
Spring Boot         = Supported 4.x release, pinned to a specific patch
Spring Framework    = Corresponding 7.x (managed by Spring Boot)
Spring Security     = Corresponding 7.x (managed by Spring Boot)
Authorization Server= Components/configuration per Spring Security 7.x
Build tool          = Wrapper compatible with the Boot/JDK version
~~~

Avoid copying Spring Authorization Server 1.x dependency declarations or extension APIs verbatim into Boot 4 without reading the migration guide. Major changes can affect starter names, packages, configuration APIs, security defaults, or auto-configuration integration.

### 3.3. Decision Rule Between the Two Paths

~~~mermaid
flowchart TD
    A["Start selecting a version stack"]
    B{"Existing application or lessons using<br/>Spring Authorization Server 1.x APIs?"}
    C["Stay on Boot 3 / Security 6 generation<br/>and use the corresponding SAS 1.x"]
    D["Prioritize evaluating Spring Boot 4<br/>and Spring Security 7 branch"]
    E{"Does the chosen branch still fit<br/>the support policy?"}
    F["Lock in JDK and specific patch<br/>from release notes + BOM"]
    G["Plan upgrade/migration<br/>or pick a supported release"]

    A --> B
    B -->|"Yes"| C
    B -->|"No"| D
    C --> E
    D --> E
    E -->|"Yes"| F
    E -->|"No"| G
    G --> D
~~~

For multi-service projects, you must also consider library versions on the **OAuth2 Client** and **Resource Server**. They are **not required** to share the exact same Spring Boot version as the AS; what is required is interoperable protocol behavior and compatible metadata/tokens, verified with integration tests under your security policy.

## 4. What Problem Does the Spring Boot BOM Solve?

A BOM (Bill of Materials) is a curated set of managed dependency versions designed to produce a consistent set of libraries. Spring Boot provides dependency management so the versions of many Spring components and related libraries are determined centrally.

In a project using the Spring Boot parent (Maven) or the Spring Boot plugin/BOM (Gradle), dependencies are typically declared **without a version** so that dependency management selects the compatible version.

### 4.1. Maven Example with Spring Boot 3.5

Create a Maven project on Spring Initializr and **select the exact Boot 3.5 patch version approved by your organization**, with Java 21. The `pom.xml` generated by Initializr includes the Spring Boot parent, a pinned version, and plugin configuration. The snippet below illustrates **the required sections**:

~~~xml
<properties>
    <java.version>21</java.version>
</properties>

<dependencies>
    <!-- Authorization Server starter for the Spring Boot 3 generation -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-authorization-server</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

This snippet is **not a complete POM**: it is added to the file generated by Spring Initializr with `<parent>` and other sections. Omitting the version is intentional: Spring Boot manages the compatible dependency versions.

If you deliberately use the `org.springframework.security:spring-security-oauth2-authorization-server` dependency instead of the starter, check the BOM and documentation for the exact Spring Boot generation you are using. Do not add the "latest" `spring-security-core` version in an attempt to upgrade security independently.

### 4.2. Gradle Kotlin DSL Example with Spring Boot 3.5

Create a Gradle Kotlin DSL project from Spring Initializr, choosing Java 21 and an appropriate Boot 3.5 release. Once Initializr has generated `plugins { ... }` and dependency management, use this illustrative configuration:

~~~kotlin
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-oauth2-authorization-server")
    implementation("org.springframework.boot:spring-boot-starter-web")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

This is a **configuration snippet** for a `build.gradle.kts` file that already has the Spring Boot plugin and appropriate dependency management. Do not manually add `version("6.5.x")` to Spring Security inside `dependencies`. If using Gradle with a custom BOM platform setup, make sure the Spring Boot BOM is actually imported and dependency resolution is not overridden by another `enforcedPlatform` or constraint.

### 4.3. With Boot 4, Keep the Same Principle but Use the Generation-Appropriate Starter

The principle of **letting Spring Boot manage the corresponding versions** remains unchanged. However, obtain the dependency/starter names and Authorization Server configuration approach from the official documentation of the Boot 4/Security 7 version you are using, as major transitions can change both starter sets and integration APIs. **Do not treat the Maven/Gradle examples in Sections 4.1–4.2 as copy-paste-ready Boot 4 build templates.**

## 5. A Verifiable Process for Selecting and Pinning a Version Stack

We recommend following a six-step process:

### Step 1 — Lock Down Requirements and Constraints

Clearly document:

- Is this a new application or an upgrade from a running system?
- Is there existing code that depends on Spring Authorization Server 1.x APIs?
- Which JDKs does the organization support in development, CI, containers, and production?
- Will the planned Spring Boot branch remain maintained throughout the operational horizon?
- Does the system use JDBC, Redis, Redis session, database migrations, native image, a servlet container, or custom OAuth2 libraries?

Do not choose based on release date alone: a new major version may require unplanned migration work, whereas an older release may have stopped receiving free patches.

### Step 2 — Choose the Spring Generation, Then Choose Java

Choose **Spring Boot 3 + Security 6 + SAS 1.x** when you need to match APIs in documentation/applications of that generation and have an appropriate maintenance policy. Choose **Spring Boot 4 + Security 7** for the newer generation when the project accepts the corresponding APIs and configuration model. Then select a JDK supported by that specific release; Java 21 is used as the example throughout this lesson.

### Step 3 — Pick the Release and Patch from Official Sources

Before freezing the build:

1. Check the release notes and system requirements of the **Spring Boot** release you plan to use.
2. Check the release notes/API migration guides for **Spring Security** of the same generation.
3. For the 1.x branch, check the documentation/release notes of **Spring Authorization Server**.
4. Verify that the patch version is managed by the Spring Boot BOM, along with its support status and security advisories.
5. Check requirements of third-party libraries, Maven/Gradle plugins, and the OS/container.

Official reference sources:

- <https://spring.io/projects/spring-boot>
- <https://docs.spring.io/spring-boot/>
- <https://spring.io/projects/spring-security>
- <https://docs.spring.io/spring-security/reference/>
- <https://spring.io/projects/spring-authorization-server>
- <https://docs.spring.io/spring-authorization-server/reference/>

Project and documentation URLs can change structure across generations; when visiting them, always match the **version selector** to your project.

### Step 4 — Create a Project with Explicit Versions

Use <https://start.spring.io/> or a vetted internal template. Explicitly choose Java, the Spring Boot release, the build tool, and the corresponding dependencies. Pin the Spring Boot version in the parent/plugin; commit `mvnw`, `mvnw.cmd` or `gradlew`, `gradlew.bat` along with the required wrapper files.

Do not use dynamic labels like `LATEST` or `RELEASE` in deployed builds. Where tutorial text writes `3.5.x`, when creating the actual repository you must replace it with the **specific patch number** selected by your organization.

### Step 5 — Verify Resolved Dependencies

**With Maven** (in the directory containing `pom.xml`):

~~~bash
./mvnw -version
./mvnw dependency:tree
./mvnw verify
~~~

When you want to inspect only Spring Security dependencies:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework.security
~~~

**With Gradle** (in the directory containing `build.gradle.kts`):

~~~bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-config --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-oauth2-authorization-server --configuration runtimeClasspath
./gradlew test
~~~

On Windows PowerShell, you can use `.\mvnw.cmd` or `.\gradlew.bat` respectively.

Read the resolved output carefully, focusing on:

- `org.springframework.boot`: the Boot parent/plugin version.
- `org.springframework.security`: the actual Spring Security and Authorization Server modules.
- `org.springframework`: the Spring Framework modules.
- Signs that a dependency is being **forced up/down in version** by an override, constraint, direct dependency, or another BOM's dependency management.

The artifact names and dependency groups in the examples above apply to the Spring Boot 3/SAS 1.x generation. With Spring Security 7, look up the exact artifacts from the dependency graph of the generation in use.

### Step 6 — Run Protocol-Level Integration Tests

Only after the build and dependency graph are stable should you proceed to testing OAuth2/OIDC functionality:

- The authorization endpoint accepts valid `client_id`, `redirect_uri`, and `scope`; rejects unregistered redirect URIs.
- The token endpoint processes authorization codes and PKCE (`code_verifier`); rejects invalid verifiers or already-used codes.
- The AS issues JWTs with the designed issuer/claims and publishes matching verification keys.
- OIDC discovery, ID tokens, and required claims work when OIDC is enabled.
- The Resource Server accepts access tokens with valid issuer, audience, expiration, and scopes; rejects invalid tokens.
- Storage behavior for clients, authorizations, consents, signing keys, and key rotation matches environment configuration.

A project that starts up successfully but has broken grant types, wrong claims, PKCE errors, or altered filter chain application cannot yet be called a fully verified version stack.

## 6. Selection Examples Based on Real-World Scenarios

### Scenario A — A Course with Spring Authorization Server 1.x Sample Code

A study team is following materials written for Spring Boot 3.5, Spring Security 6.5, and Spring Authorization Server 1.5. Choose **Java 21** together with the Boot 3.5/Security 6.5/SAS 1.5 branch, let Boot manage dependencies, and then verify the resolved versions. Do not force Spring Security 7 just to get a higher major number because configuration APIs may differ.

If using this for production rather than a lab, review the **support status at deployment time** and have an upgrade plan if that branch no longer receives patches under policy.

### Scenario B — Building a New Authorization Server with Few Legacy Constraints

The team chooses a **supported Boot 4.x release**, uses Security 7.x, and the Authorization Server components from that same generation. Choose Java 21 if it satisfies the release's requirements. Start from the Spring Security 7 documentation, especially the migration and configuration changes; do not take an SAS 1.5 example and merely change the Boot plugin to 4.x.

### Scenario C — Resource Server on Boot 3, Authorization Server on Boot 4

Two services can run on **two different Spring generations**. What must be verified is protocol interoperability: issuer, authorization server metadata, JWKS, token signature, audience, scope, endpoints, claim mapping, OIDC discovery, and token lifetimes. Upgrading Boot on the AS does not force an immediate Boot upgrade on the RS, provided APIs/protocols remain compatible and the system is tested.

### Scenario D — CI Uses Java 21 While Production Still Runs Java 17

If an application builds with `--release 21`, JVM 17 cannot run it. The fix is not changing a single Spring Security dependency; you must pick a **compatible Java target** or upgrade the production JVM, while also checking libraries and container images. This is a technical constraint that must be resolved before deployment.

## 7. Common Mistakes When Combining Versions

| Mistake | Possible Symptoms | How to Prevent It |
| --- | --- | --- |
| Combining Spring Boot 3.x with Spring Security 7.x | Binary/API compatibility errors, mismatched configuration | Use Security 6.x matching Boot 3, or upgrade the entire application on a Boot 4 plan |
| Combining Spring Boot 4.x with SAS 1.x libraries/config out of habit | Class/method errors, incompatible starters/config | Follow Spring Security 7 documentation and the appropriate migration guide |
| Hardcoding versions for every Spring module | Modules in the same ecosystem drift in minor/patch versions | Let the Spring Boot BOM manage versions; only override with clear justification and testing |
| Picking a newer Java version without checking support | Build plugin, toolchain, or runtime failures | Check system requirements and run tests on the target JVM |
| Picking an overly old patch within a chosen branch | Bugs already fixed in newer patches may remain | Apply a maintained patch version per support policy |
| Accidentally using `SNAPSHOT` or milestones in production | Shifting APIs or dependency graphs, different support terms from stable releases | Only use pre-releases in intentional experimentation |
| Upgrading Authorization Server alone without checking Boot/Security | `NoSuchMethodError`, `ClassNotFoundException`, startup and protocol errors | Upgrade together as a compatible generation and test the endpoints |
| Assuming `BUILD SUCCESSFUL` from Maven/Gradle is enough | Bugs surface only along actual OAuth 2.0/OIDC paths | Add tests for authorization, token, discovery, and resource validation flows |

### 7.1. Distinguishing Common Errors

**`UnsupportedClassVersionError`:** bytecode was compiled by a newer Java version than the JVM running it. Check runtime `java -version` and the toolchain/target release.

**`NoSuchMethodError` or `NoClassDefFoundError`:** may happen because Spring/Security modules are not from the same generation, or a library was compiled against a different API. Print the dependency tree and identify the actual loaded version.

**`BeanCreationException` when enabling security auto-configuration:** may result from incomplete configuration, duplicate beans, API changes, or configuration written for another version. Read the root cause of the stack trace; do not immediately assume "Spring Security is broken."

**Token endpoint returns errors after an upgrade:** the cause may be client registration, grant types, PKCE, redirect URI, client authentication method, or policy configuration changes. Inspect the request and server logs with secrets redacted.

## 8. Pinning Versions While Still Receiving Security Updates

There are two seemingly conflicting needs: **reproducible builds** and **applying patches**. The solution is to pin the **specific version of the release in use**, then perform controlled upgrades.

~~~mermaid
flowchart LR
    A["Pick a supported Boot patch"]
    B["Pin in parent/plugin and wrapper"]
    C["Resolve, inspect dependency tree"]
    D["Run OAuth2/OIDC + regression tests"]
    E["Build image and deploy"]
    F["Monitor advisories / release notes"]
    G["Bump patch, re-verify"]

    A --> B --> C --> D --> E --> F --> G
    G --> C
~~~

Operational notes:

- Use Maven/Gradle Wrapper to avoid build tool version skew between developer machines and CI.
- Record the JDK version, Spring Boot version, dependency graph, and image digest for each release when the system requires traceability.
- When a vulnerability is disclosed, review the advisory and fixes across the **entire Spring Boot/Security/Framework line**. Do not randomly bump a single artifact and skip test results.
- Prefer regular patch updates within a supported minor branch; plan major upgrades separately with migration testing.
- Consider storing an SBOM to enable dependency auditing for released builds.
- Verify that staging and production environments use the exact tested image, JDK, and issuer/key management configuration.

## 9. Checklist Before Starting the Lesson Exercises

Check off after verifying on your local machine and actual repository:

- [ ] Selected the Spring Boot 3/Security 6/SAS 1.x generation **or** Boot 4/Security 7 matching your codebase.
- [ ] Have a specific Spring Boot patch version that fits the support and security update policy.
- [ ] Know the Java requirements of the release; build JDK, toolchain, and production JVM are compatible.
- [ ] Maven/Gradle Wrapper has been committed to the repository.
- [ ] Spring Framework/Security/Authorization Server dependencies are not overridden to the wrong generation.
- [ ] Dependency tree/insight commands confirm the right library versions are resolved.
- [ ] Build and unit tests succeed.
- [ ] Authorization code/token issuance, PKCE, OIDC, and RS token validation flows are tested according to application needs.
- [ ] Have a plan for tracking patches and migrating when the branch reaches end of support.

## 10. Review Questions

**Question 1.** Why can't you simply pick the latest Spring Security 7.x for a Spring Boot 3.5 project?  
**Answer:** Boot 3.x and Security 6.x belong to the same API/dependency generation. Pushing Security 7 into Boot 3 can mismatch Spring Framework, configuration APIs, and auto-configuration. To use Security 7, you need to plan an upgrade to the corresponding Boot generation.

**Question 2.** A Maven POM uses the Spring Boot parent, which already manages dependencies. Do you need to declare `<version>` for `spring-boot-starter-oauth2-authorization-server`?  
**Answer:** Normally no. Let the parent/BOM manage the version; only customize it with clear justification and after verifying the dependency graph.

**Question 3.** You already selected Java 21 as the toolchain—why do you still need to check Java inside the Docker image?  
**Answer:** The generated bytecode may require JVM 21; if the image runs Java 17, the application will fail to start. The compilation JDK and runtime must be compatible.

**Question 4.** Can a Spring Boot 4 Authorization Server issue tokens for a Spring Boot 3 Resource Server?  
**Answer:** Yes, provided the protocol, issuer, signatures/JWKS, token audience/claims, policies, and client integration are compatible; practical testing is required.

**Question 5.** If a project builds successfully with a new version stack, is it ready to go straight to production?  
**Answer:** Not yet. You must verify dependency resolution, support policy, OAuth 2.0/OIDC endpoints, token/key management, and integration tests with clients/resource servers.

## 11. Design Decision Summary

**Start with Spring Boot, let the BOM manage Spring Security/Spring Framework, and choose the Authorization Server from the same generation.** For SAS 1.x sample code, Java 21 + Boot 3.5.x + Security 6.5.x + SAS 1.5.x is an API-consistent reference baseline. For projects following the newer Spring line, choose a supported Boot 4.x release along with Security 7.x and the corresponding Authorization Server documentation.

In both cases, the `x` notation denotes a **branch**, not a deployable version. The specific patch must be chosen and pinned explicitly, cross-checked against official documentation, the dependency tree, test results, and the support lifecycle. This provides a reliable foundation for building, testing, and operating the Authorization Server configuration steps that follow.
