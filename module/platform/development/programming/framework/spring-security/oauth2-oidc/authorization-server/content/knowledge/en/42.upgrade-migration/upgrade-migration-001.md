# Identifying Baseline Versions and Dependency Compatibility Matrix

Before upgrading Spring Authorization Server, you need to know exactly which platform the application is running on and which components the target version can combine with. Looking only at the Spring Boot version in `pom.xml` or `build.gradle` is not enough: the Java runtime, Spring Framework, Spring Security, Spring Authorization Server, JOSE/JWT libraries, database driver, migration tool, observability, and test framework can all affect building, startup, and token issuance.

A baseline version is the verified set of versions currently running stably. A compatibility matrix records the relationships between the baseline, target versions, support conditions, and test evidence. This document guides you through taking an inventory, identifying a supportable baseline, managing dependencies with a BOM, detecting conflicts, and building a matrix clear enough to make upgrade decisions.

## 1. Objectives of Identifying the Baseline

A good baseline must answer:

- Which JDK is the application using to build, and which JRE is it using to run?
- Which versions of Spring Framework, Spring Security, Jackson, Micrometer, and underlying libraries is Spring Boot managing?
- Which release line does Spring Authorization Server belong to, and is it compatible with the Spring Security version in use?
- Are JOSE/JWT, database driver, JDBC, cache, migration, and test libraries overridden outside the BOM?
- Which versions are still supported by the vendor and receiving security patches?
- Which components must the target version change at the same time?
- Can you roll back to the old baseline after the schema or authorization data changes?

Do not conflate the following three concepts:

| Concept | Meaning |
|---|---|
| **Supported** | Version relationship confirmed by official documentation/support policy |
| **Resolved** | The build tool resolved the dependency graph without resolution errors |
| **Tested** | The combination has been built and run through the project's defined test suite |

A successful build only proves that the dependency graph can resolve and compile. It does not by itself prove that the combination is officially supported, free of runtime errors, or that OAuth 2.0/OIDC flows still work properly.

## 2. Collecting Inventory from the Project

Start from what the build actually uses, not just reading the directly declared versions. Parent POMs, BOMs, Gradle plugins, version catalogs, dependency constraints, and lock files can determine the final versions.

### 2.1. Build and Runtime Information

Record:

- The JDK used to run Maven/Gradle and the compiler toolchain.
- Java release/target bytecode.
- The JRE or container image running in production.
- Maven Wrapper or Gradle Wrapper and plugin versions.
- Spring Boot plugin/parent/BOM.
- Build profiles, internal repositories, and dependency management configuration.
- Dependency locks, checksums, or SBOMs if the project generates them.

Basic check commands:

```bash
java -version
./mvnw -version
./gradlew -version
```

Only run the commands corresponding to your project's build system. Maven/Gradle output shows the actual JVM that the build tool is using; this can differ from the Java toolchain used for compilation and from the JRE in the production container.

### 2.2. Dependencies to Include in the Inventory

| Group | Components to Record | Why It Matters |
|---|---|---|
| Platform | Java, Spring Boot, Spring Framework | Determines runtime, APIs, and dependency management |
| Security | Spring Security Core/Config/Web/OAuth2 | Determines filter chains, authentication, authorization, and decoders |
| Authorization Server | Spring Authorization Server | Provides protocol endpoints, client, authorization, and token services |
| JOSE/JWT | Nimbus JOSE + JWT and OAuth2 JOSE modules | Signing, verifying, parsing JWK/JWT, and token handling |
| JSON | Jackson core/databind/modules | Serializing metadata, claims, and integration data |
| Persistence | JDBC/JPA, connection pool, database driver | Storing Registered Clients, authorizations, and consents |
| Migration | Flyway or Liquibase | Controlled schema changes |
| Cache/coordination | Redis client or cache provider if present | Storing replay state, caching clients/JWKS, or shared data |
| Observability | Actuator, Micrometer, tracing registry | Metrics, health, traces, and logging |
| Testing | JUnit, Mockito, Spring Test, Testcontainers, WireMock | Verifying integration and real dependencies |
| Build | Maven/Gradle plugins, compiler plugin, image plugin | Producing consistent and reproducible artifacts |

For Authorization Server, pay special attention to `spring-security-oauth2-authorization-server`, Spring Security OAuth2 JOSE, Nimbus JOSE + JWT, and the JDBC classes storing authorizations. A library upgraded individually can change how JWTs are parsed, JWKs are selected, token metadata is serialized, or client authentication is handled.

### 2.3. Getting the Actual Dependency Graph

With Maven:

```bash
./mvnw help:effective-pom
./mvnw dependency:tree -Dverbose
./mvnw dependency:tree -Dincludes=org.springframework.security
./mvnw dependency:tree -Dincludes=com.nimbusds
```

`effective-pom` shows versions inherited from the parent/BOM and final overrides. `dependency:tree` helps find which dependency pulls a version into the graph and detect multiple versions of the same artifact.

With Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-oauth2-authorization-server --configuration runtimeClasspath
./gradlew dependencyInsight --dependency nimbus-jose-jwt --configuration runtimeClasspath
```

Also run against `compileClasspath` or test configurations when needed. Gradle may select a higher version via conflict resolution; read the selection reason in `dependencyInsight`, do not just look at the declared version.

## 3. Identifying the Current Baseline Version

The baseline must reflect the running artifact, not just the working tree state. Collect at least the following evidence:

1. Deployed commit or release tag.
2. Running Java runtime version and image digest.
3. Spring Boot version and resolved dependency graph of the artifact.
4. Actual Spring Authorization Server and Spring Security versions.
5. Database engine/version, schema migration level, and driver.
6. Issuer, signing algorithm, `kid`, token format, and endpoint configuration.
7. Latest smoke test, integration test, and operational metrics results.

If the production artifact cannot be reproduced from the current commit, record that difference. Do not call a configuration a verified baseline if you do not know the exact binary/dependencies running.

### 3.1. Separating Declared Version and Resolved Version

For example, a project might declare Spring Security indirectly through the Spring Boot BOM, while another dependency pulls in a separate version. In that case, the version written in a build file may not be the version used at runtime.

The inventory should have two columns:

- `declared_version`: the directly declared version or version property.
- `resolved_version`: the actual version in the compile/runtime/test graph.

For dependencies managed by a BOM, record the BOM name and BOM version that determine the version. For overridden dependencies, record the reason, scope, and owner of that decision.

## 4. Determining the Spring Boot, Spring Security, and Spring Authorization Server Combination

This is the most critical compatibility axis of the module.

### 4.1. Spring Boot BOM Is the Platform Management Source

Spring Boot dependency management manages a set of Spring and integration library versions tested together by the release team within the same release line. When using the Spring Boot parent or BOM, let the BOM manage Spring Framework, Spring Security, Jackson, Micrometer, and foundational dependencies within the BOM's scope.

Do not set a different Spring Security version on your own just to use a new API. Upgrading `spring-security-core`, `spring-security-web`, `spring-security-config`, or `spring-security-oauth2-*` individually can create an inconsistent combination across modules.

### 4.2. Spring Authorization Server Must Be Compatible with Spring Security

Spring Authorization Server has its own release line and platform requirements. You must check the version documentation, release notes, and dependency metadata for the exact version you plan to use to confirm the minimum/maximum Spring Security version or supported release line.

Do not infer compatibility simply because artifacts can be downloaded from Maven Central or the build reports no errors. A newer Authorization Server release may require new Spring Security APIs; an older release may not be tested with a newer Spring Security release line.

Selection rules:

- Choose a Spring Boot release line that is still supported and matches the production JDK.
- Take Spring Framework and Spring Security from Boot's BOM, unless official compatibility documentation specifies otherwise.
- Choose a Spring Authorization Server release line confirmed compatible with the resolved Spring Security version.
- If Authorization Server is not managed by the current BOM, declare the version explicitly and record compatibility evidence.
- Do not override a single Spring Security module; if you must change release lines, evaluate the entire group of related modules.

### 4.3. Do Not Hardcode the Compatibility Matrix to a Single Example

Release lines change over time. Your project's matrix must pull data from the support documentation and metadata of the target version at the time of upgrade. You can use the following template:

| Component | Running Baseline | Target Version | Constraints to Verify |
|---|---|---|---|
| Java | `JDK_CURRENT` | `JDK_TARGET` | Boot and libraries must support the JDK; build/runtime mutually compatible |
| Spring Boot | `BOOT_CURRENT` | `BOOT_TARGET` | System requirements, support window, BOM |
| Spring Framework | `FRAMEWORK_RESOLVED` | `FRAMEWORK_TARGET` | Follows Boot's release line or official matrix |
| Spring Security | `SECURITY_RESOLVED` | `SECURITY_TARGET` | Aligned with Boot and Authorization Server |
| Spring Authorization Server | `AS_CURRENT` | `AS_TARGET` | Compatible with Spring Security, Java, and used APIs |
| Nimbus JOSE + JWT | `NIMBUS_RESOLVED` | `NIMBUS_TARGET` | Follows dependency management; no arbitrary overrides |
| Jackson | `JACKSON_RESOLVED` | `JACKSON_TARGET` | Keep Jackson modules and serializers synchronized |
| Database/driver | `DB_CURRENT` / `DRIVER_CURRENT` | `DB_TARGET` / `DRIVER_TARGET` | Driver supports database, JDK, and TLS/auth |
| Migration tool | `MIGRATION_CURRENT` | `MIGRATION_TARGET` | Supports database and migration syntax |
| Micrometer/Tracing | `OBSERVABILITY_RESOLVED` | `OBSERVABILITY_TARGET` | Follows BOM and backend registry |
| Testcontainers | `TESTCONTAINERS_CURRENT` | `TESTCONTAINERS_TARGET` | Compatible with JDK, Docker/runtime, and database image |

Placeholder values must be replaced with verified versions. Do not copy a version table from another project if that project uses a different JDK, Boot, servlet container, or database.

## 5. Assessing Compatibility Status

Assign a status to each version pair or group, not just to individual artifacts:

| Status | Usage Condition |
|---|---|
| `SUPPORTED` | Official documentation/policy confirms the combination is supported |
| `TESTED` | The project's test suite ran on that exact combination and met requirements |
| `CONDITIONAL` | Has documented conditions, limitations, or mandatory patches |
| `UNKNOWN` | Lacks reliable documentation or test evidence |
| `UNSUPPORTED` | Outside official requirements or known to be incompatible |

A combination can be `SUPPORTED` while not yet `TESTED`. For example, the vendor supports it, but the project has not run integration tests yet. Conversely, a combination `TESTED` in an internal environment might still not be supported by the vendor; do not use one successful test run to claim official support.

The matrix should store concrete evidence: release notes or system requirements URLs, test commits, build numbers, dependency tree logs, SBOMs, and test results. Record the verification date because support status can change.

## 6. Managing Versions with BOM and Dependency Management

### 6.1. Maven with Spring Boot Parent

Condensed Maven structure example:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>BOOT_VERSION</version>
    <relativePath/>
</parent>

<properties>
    <java.version>21</java.version>
    <spring-authorization-server.version>AS_VERSION</spring-authorization-server.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-oauth2-authorization-server</artifactId>
        <version>${spring-authorization-server.version}</version>
    </dependency>
</dependencies>
```

`BOOT_VERSION` and `AS_VERSION` are placeholders: replace them with concrete verified versions before building. The parent POM uses a literal/CI-friendly version according to the project's Maven convention; do not assume a property declared in the same POM can be used in every model position. Check whether the Boot BOM manages the Authorization Server artifact in that release line. If it does, avoid declaring a separate version; if not, pin a compatible version explicitly.

### 6.2. Maven with Imported BOM

When not using the Boot parent, you can import the Boot BOM in `dependencyManagement`:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>BOOT_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Declare the concrete BOM version in the project; `BOOT_VERSION` is only a placeholder. Do not import multiple BOMs that manage the same Spring group without understanding precedence and override order. If there is a corporate BOM, document clearly which BOM is the final source for each dependency.

### 6.3. Gradle

With Gradle, use the Spring Boot plugin and dependency management plugin or native platform/BOM according to your project's convention. Example:

```kotlin
plugins {
    id("org.springframework.boot") version "BOOT_VERSION"
    id("io.spring.dependency-management") version "DEPENDENCY_MANAGEMENT_VERSION"
}

dependencies {
    implementation("org.springframework.security:spring-security-oauth2-authorization-server:AS_VERSION")
}
```

The `*_VERSION` strings are placeholders and must be replaced with verified versions. When using `io.spring.dependency-management` together with the Spring Boot plugin, the dependency management plugin automatically imports the Boot BOM matching the Boot plugin version. If the project uses a native Gradle platform instead of the dependency management plugin, remove the `io.spring.dependency-management` plugin and declare `implementation(platform("org.springframework.boot:spring-boot-dependencies:BOOT_VERSION"))` inside `dependencies`. You do not need to use both BOM management approaches at the same time. Do not declare Spring Security modules with different versions in individual dependencies. Use a version catalog or convention plugin to centralize versions and prevent drift across modules.

### 6.4. Avoiding Overrides of Foundational Dependencies

Only override a BOM-managed version when there is a clear technical reason, such as a mandatory security patch or a confirmed bug. Every override must record:

- The dependency and the version selected by the BOM.
- The override version and reason.
- Impact scope (compile, runtime, test).
- Related dependency combinations that need testing.
- Expected removal date for the override and owner.

Do not use `force`, `resolutionStrategy`, or blanket exclusions just to make the build green without understanding which dependency needs that version. These measures can mask binary conflicts or runtime failures.

## 7. Authorization Server–Specific Compatibility Points

When comparing the baseline and candidate, check both APIs and the following runtime behaviors:

### 7.1. SecurityFilterChain and Endpoints

- Order of `SecurityFilterChain` and `securityMatcher`.
- Configuration of the authorization endpoint, token endpoint, JWK Set endpoint, introspection, revocation, and OIDC endpoints.
- Default security headers, CSRF, CORS, session, and exception handling.
- Builder/customizer APIs and converters for authorization requests, token requests, and client authentication.
- Behavior of custom `AuthenticationProvider` and `AuthenticationConverter` implementations.

A Spring Security change can alter APIs or filter ordering; an Authorization Server change can alter extension points or default behavior. Checking compilation is not enough: you must test real requests to each endpoint.

### 7.2. Client, Authorization, and Token Persistence

- `RegisteredClientRepository` and serialization of `ClientSettings`/`TokenSettings`.
- `OAuth2AuthorizationService` and `OAuth2AuthorizationConsentService`.
- JDBC schema, indexes, column types, and migrations.
- Serialization of authorization attributes, principal names, and token metadata.
- Refresh token rotation, reuse detection, revocation, and consent lookup.

If upgrading the serializer or schema, the new version must be able to read records created by the old version during rollout. If compatibility cannot be maintained, plan an offline migration or forced re-authentication.

### 7.3. JOSE, JWK, and Token Customization

- `JwtEncoder`, `JwtDecoder`, `JWKSource`, and key selection.
- `kid`, `alg`, `kty`, JWK use/key operations, and JWKS cache.
- `OAuth2TokenCustomizer` and claim mapping.
- JWT headers/claims, issuer, audience, token type, and serialization.
- ID token signing, UserInfo, and discovery metadata.

Nimbus or JOSE library updates can change APIs, algorithm validation, key selection, or JWK parsing. Test tokens issued with old keys and new tokens; verify that real Resource Servers can read both during the transition period.

### 7.4. Java, Servlet Container, and Runtime

Check JDK bytecode, Java toolchain, servlet API/container, and runtime image. Do not build with a newer JDK and then run on a JRE lower than the bytecode target or runtime requirement. Check the TLS provider, trust store, entropy, timezone, locale, and container memory limits.

### 7.5. Database and Driver

Check database version, driver, TLS/authentication mode, connection pool, transaction isolation, and SQL dialect. The migration tool must support the exact database. Test schemas on the real database engine; H2 cannot replace integration tests with PostgreSQL, MySQL, or Oracle if production uses those systems.

## 8. Checking the Dependency Graph and Conflict Risks

Signs that require investigation:

- Multiple versions of the same Spring Security module in the runtime graph.
- Spring Framework or Security modules not on the same release line.
- Nimbus JOSE + JWT pulled at a different version from the one tested by Spring Security/Authorization Server.
- Unsynchronized Jackson modules.
- Duplicate or conflicting logging facades/providers.
- Driver or pool versions that do not support the production JDK/database.
- Test dependencies accidentally included in runtime, or runtime dependencies missing from the image.
- Dependencies excluded from the BOM without a compatible replacement.

Not every dependency tree with multiple versions is an error: the build tool may pick one version according to resolution rules. However, you need to understand which module requires which version and whether binary/API compatibility holds.

After resolving the graph, generate an SBOM for the artifact and scan for vulnerabilities according to organizational policy. Record both direct and transitive dependencies, licenses, CVEs, download sources, and checksums/signatures if the pipeline supports them. Do not upgrade a library solely to clear a scanner warning without confirming that the version is compatible with the framework and does not introduce new vulnerabilities.

## 9. Building the Project's Compatibility Matrix

A useful matrix needs versions, conditions, and evidence. Example structure:

| Component/Relationship | Baseline | Candidate | Status | Evidence | Risks/Notes |
|---|---|---|---|---|---|
| JDK ↔ Boot | `JDK_A / BOOT_A` | `JDK_B / BOOT_B` | `SUPPORTED` | System requirements link | Runtime image needs same JDK line |
| Boot ↔ Framework/Security | BOM A | BOM B | `SUPPORTED` | Effective POM/dependency report | Do not override single modules |
| Security ↔ Authorization Server | `SECURITY_A / AS_A` | `SECURITY_B / AS_B` | `CONDITIONAL` | Release notes + integration test | Verify custom provider API |
| AS ↔ JDBC schema | Schema A | Schema B | `TESTED` | Migration test report | Expand-and-contract |
| JOSE/JWK ↔ Resource Server | Nimbus A | Nimbus B | `UNKNOWN` | No rotation test yet | Need key overlap test |
| Database ↔ Driver | DB A / Driver A | DB B / Driver B | `SUPPORTED` | Vendor matrix | Test TLS and transaction |
| Micrometer ↔ Registry | Metrics A | Metrics B | `TESTED` | Scrape/metric test | Check names and histograms |

The rows above only illustrate how to record entries. Do not mark `SUPPORTED` or `TESTED` before having evidence. Add `owner`, `verified_at`, `test_run`, and `artifact_digest` columns if the matrix is used in the release process.

### 9.1. Matrix by Environment

If development, staging, and production run different configurations, record each environment separately:

| Field | Development | Staging | Production |
|---|---|---|---|
| Java runtime | ... | ... | ... |
| Container/image | ... | ... | ... |
| Spring Boot/Security/AS | ... | ... | ... |
| Database/driver | ... | ... | ... |
| Key provider | Local test key | Staging KMS | Production KMS/HSM |
| Token format/alg | ... | ... | ... |
| Resource Server version | ... | ... | ... |

Ideally, the same artifact digest runs across all environments and only runtime/secret configuration differs. If production uses a different artifact, document the reason and test separately.

## 10. Turning the Matrix into an Upgrade Plan

Once the baseline is clear, select candidates in a controllable order:

1. Select a Java JDK and Spring Boot release line that are still supported.
2. Pull Spring Framework/Security from the corresponding BOM.
3. Select a Spring Authorization Server version compatible with that Spring Security version.
4. Check database driver, migration tool, JOSE/JWT, observability, and test dependencies.
5. Flag dependencies with API breaking changes or schema impact.
6. Split the upgrade into groups that can be built/tested independently if needed.
7. Create a candidate branch or commit, saving the dependency graph and SBOM.
8. Run compile, unit, integration, security regression, and migration tests.
9. Only lock in the candidate once the combination has support evidence and passing test results.

You do not necessarily have to upgrade every dependency to the latest version. Choose versions that are supported, compatible, and operable; document the reason if an upgrade is deferred.

## 11. Pre-Finalization Checklist for Baseline/Candidate

| Check | Evidence to Keep |
|---|---|
| JDK build and runtime compatible | Version output, toolchain config, image digest |
| Spring Boot release line supported | System requirements/release policy |
| Framework/Security consistently from BOM | Effective POM or Gradle dependency report |
| Authorization Server compatible with Security | Version documentation and dependency metadata |
| No unexplained overrides | Dependency tree and exception list |
| JOSE/JWK/JWT working | Signing, verification, JWKS, and rotation tests |
| Persistence compatible | Schema diff, migration test, serialization test |
| Database driver supports database/JDK | Vendor compatibility documentation and integration test |
| Actuator/Micrometer working | Metric scrape, health, and tracing tests |
| Client flows have no regression | Authorization code + PKCE, client credentials, refresh, revoke/introspection if used |
| Reproducible build | Wrapper, lock/versions, SBOM, and artifact digest |
| Dependency security | CVE/license scan and remediation decisions |

## 12. Common Mistakes

| Mistake | Consequence | Mitigation |
|---|---|---|
| Looking only at versions in `pom.xml` | Misses versions decided by BOM/transitive dependencies | Check effective POM and dependency tree |
| Upgrading individual Spring Security modules | Modules drift across release lines, runtime errors or binary incompatibility | Use Boot BOM or a supported version set |
| Choosing Authorization Server just because it is the latest | May be incompatible with current Spring Security | Verify release line and dependency metadata |
| Treating a successful build as compatibility | Misses protocol, persistence, and key rotation bugs | Run integration/security regression tests |
| Checking only `compileClasspath` | Runtime missing or conflicting dependencies | Check runtime/test graph and final image |
| Using H2 instead of production database for all tests | Misses SQL, transaction, and driver differences | Test on the corresponding database engine |
| Overriding Nimbus/Jackson without evidence | Hard-to-diagnose JWT/JWK or serialization errors | Follow BOM; justify and separately test overrides |
| Not saving baseline artifact | Cannot reproduce pre-upgrade environment | Save commit, digest, dependency report, and SBOM |
| Upgrading framework alongside breaking schema changes | Rollback cannot read old authorizations | Use expand-and-contract and compatibility tests |

## Conclusion

Identifying the baseline and compatibility matrix is the first step to upgrading Authorization Server in a controlled manner. Pull resolved versions from actual artifacts, use the Spring Boot BOM as the platform management source, verify Spring Authorization Server compatibility with Spring Security, and separately evaluate dependencies affecting JWT, persistence, database, and observability. A matrix with status, evidence, verification date, and test results clearly distinguishes supported combinations from combinations that merely build or remain unverified. Once the baseline is reproducible and the candidate is tested across all OAuth 2.0/OIDC flows, the team has a reliable foundation for planning the upgrade and rollback.
