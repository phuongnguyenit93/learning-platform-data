# Looking Up APIs and Reference Documentation for the Exact Spring Security Version

> **Module:** Spring Security – authentication. **Group:** Versions. This lesson is for learners using Java 17+, Spring Boot, and Spring Security on the Servlet stack (WebFlux notes are distinguished separately). The goal is to know **which exact version is running, read the matching Reference/Javadoc set, find the right package/module/signature, and verify sample code against resolved dependencies**, rather than copying examples from the “latest” page and discovering that an older project fails to compile or behaves differently during authentication. This document reflects official pages cross-checked on **November 6, 2026**; the “latest” status or patches under release must always be re-checked when applied.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **Spring Security version**, **Spring Boot version**, **Spring Framework version**, and individual Security modules: `spring-security-core`, `spring-security-web`, `spring-security-config`, `spring-security-oauth2-resource-server`, `spring-security-oauth2-jose`, `spring-security-test`.
2. Determine the version **resolved at build time**, **packaged inside the artifact**, and **running in the target environment**, even when `pom.xml`/`build.gradle` does not declare a version number on the dependency.
3. Understand the differences between **Reference Documentation**, **API/Javadoc**, **Migration Guide**, **Release Notes**, and **Security Advisories**, and choose the right source for the question.
4. Open documentation pinned to a version branch such as `/reference/6.5/` or `/reference/7.0/` instead of defaulting to `/reference/`.
5. Look up Javadoc for the exact class and package via `/reference/<major.minor>/api/java/...`; inspect constructors, methods, `@since`, deprecations, signatures, and inherited members.
6. Distinguish code for **Servlet** (`HttpSecurity`, `SecurityFilterChain`, `HttpServletRequest`) vs. **Reactive/WebFlux** (`ServerHttpSecurity`, `SecurityWebFilterChain`, `ServerWebExchange`).
7. Identify differences when reading examples for **Spring Security 6.5** compared to **7.x**: passkey/WebAuthn dependencies, MFA APIs, migration, and Spring Boot release lines.
8. Write a standalone Java 17 utility to construct branch-accurate documentation URLs from a determined version, with reproducible output.
9. Build a compile/behavior testing workflow, recording evidence of URL + version + commit + dependency graph, without claiming an API is supported merely because it appears in the “latest” Javadoc.
10. Read security advisories with version context; avoid treating a forum answer or an outdated GitHub snippet as the specification for the running application.

## 2. What Does “Exact Version” Mean?

A project typically has several different sources that speak about version:

```text
                 pom.xml / build.gradle(.kts)
                          |
             parent / dependencyManagement
                 Spring Boot BOM / platform
                          |
                  Resolve dependency graph
                 /          |           \
       spring-security  spring-framework  third-party
       -core/-web/...       libraries       modules
                  |
        runtimeClasspath / testRuntimeClasspath
                  |
            app.jar / container image
                  |
       production deployment image digest
                  |
              Read Reference + API of
           the actual running version
```

Example configuration:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

Not seeing a string like `6.5.x` or `7.x` **does not mean the project has no version**. The Spring Boot BOM/platform selects a concrete set of dependencies. If the author looks up the “latest” docs without checking the resolved runtime, they may read an API that does not yet exist in the project.

Conversely, a version written on a dependency is **intent**, not necessarily the version selected after BOM management, constraints, profiles, locking, transitive conflicts, or repackaging.

### 2.1. Five Layers of Evidence to Cross-Check

| Source | Question | When Is It Sufficient? |
|---|---|---|
| `pom.xml`/`build.gradle` | What does the project declare? | Only shows initial configuration |
| BOM / parent / version catalog | What manages module version numbers? | Explains dependency management intent |
| Maven dependency tree / Gradle runtimeClasspath | **Which JARs did the build tool select?** | Sufficient to look up APIs matching that local/CI build |
| `BOOT-INF/lib` / SBOM / image | Which JARs are actually packaged? | Sufficient to cross-check the artifact to be deployed |
| Deployment inventory/image digest/runtime diagnostics | Which artifact is the pod/server running? | Required to answer production incident questions |

**Rule:** for compile errors, prioritize **compileClasspath**; for runtime errors, prioritize **runtimeClasspath + artifact**; for production bugs, you must verify the **deployed image digest/actual JAR**, not the version on an open Git branch.

### 2.2. Spring Security Has Multiple Modules Sharing a Release Train

In an application you may encounter:

```text
org.springframework.security:spring-security-core
org.springframework.security:spring-security-config
org.springframework.security:spring-security-web
org.springframework.security:spring-security-crypto
org.springframework.security:spring-security-test
org.springframework.security:spring-security-oauth2-client
org.springframework.security:spring-security-oauth2-resource-server
org.springframework.security:spring-security-oauth2-jose
```

A class may live in the Web module while documentation examples use Config; a class in OAuth2 JOSE may require an additional starter. Do not see `spring-security-core:6.5.11` and assume every other module shares the same patch if the project has overrides; **list all resolved versions**.

If module versions diverge (for example Config 6.5.x while Web is 6.4.x due to an override), treat it as **dependency drift** and check compatibility, rather than choosing documentation that mixes two releases. Upgrading only a single JAR to fix a compiler error or CVE alert can cause `NoSuchMethodError`/`ClassNotFoundException`/behavior changes.

### 2.3. Spring Boot’s Version Is Not Spring Security’s Version

- Spring Boot provides the framework/autoconfiguration/BOM for the application.
- Spring Framework provides IoC/MVC/WebFlux, `@Configuration`, transactions, and HTTP infrastructure.
- Spring Security provides authentication/authorization/filter chains/OAuth2 support.
- Spring Authorization Server, Spring Session, and Spring LDAP are separate projects with their own documentation lifecycles.

A `docs.spring.io/spring-boot/...` URL does not replace the Javadoc of `AuthenticationManager`; and Spring Security’s Javadoc does not by default fully document the Spring Boot property `spring.security.oauth2.resourceserver.jwt.issuer-uri`. Always state the **product name and version** in your question.

## 3. Four Main Documentation Sources: They Answer Different Questions

| Document Type | Scope | When to Use | Do Not Use to Conclude |
|---|---|---|---|
| **Spring Security Reference** | Mechanisms, use cases, Java/Kotlin configuration, flows, and architecture | “How do I configure `SecurityFilterChain`?”, “How does JWT/OTT work?” | Does not guarantee every snippet compiles if you have not checked versions/dependencies |
| **Javadoc/API** | Packages, classes, interfaces, constructor/method signatures, `@since`, `@deprecated`, Java generics | “Does this method exist in 6.5?”, “What is the return type?” | Does not replace business threat models, deployment guides, or migration |
| **Migration Guide/Release Notes** | Changes between versions, removed/deprecated APIs, configuration transitions | “What must change from 6.x to 7.x?” | Does not replace the project’s actual dependency graph |
| **Security Advisories** | Vulnerabilities, affected/fixed versions, prerequisites, mitigations, support channels | “Which CVEs affect this version?” | Does not replace reachability tests or production image verification |

A useful fifth source is the **source code/tag matching the version** to verify detailed behavior. However, reading `main` or `master` of the repository for an application running 6.5.x can be wrong because source has moved to the 7.x branch. Always choose the **published release tag/commit** and cross-check artifact metadata.

### 3.1. How Does “Reference” Differ from “API/Javadoc”?

Reference explains **how to use**:

```java
http
    .authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated())
    .formLogin(Customizer.withDefaults());
```

The above is a **snippet** inside a `SecurityFilterChain` bean; it relies on `HttpSecurity`, `Customizer`, security configuration, and an appropriate user store/provider.

Javadoc states the **signature**: `HttpSecurity.formLogin(Customizer<FormLoginConfigurer<HttpSecurity>>)` or specific overloads per version, the structure of `AuthenticationEntryPoint.commence(...)`, and exceptions. When Reference contains a confusing example, **version-matched Javadoc** helps verify method/constructor names and availability conditions.

**Do not use Javadoc alone to infer the default behavior of an entire Spring Boot app**: bean autoconfiguration, filter chain ordering, and classpath dependencies also determine the outcome. Conversely, do not rely on a “latest” Reference example to claim a method exists in an older patch.

### 3.2. Combining Them in Order

1. Read the right **Reference section** for the feature to understand the flow.
2. Open the Javadoc for the classes appearing in the sample code.
3. Check `Since`, deprecated, constructor signatures, method overloads, and required modules.
4. Read the migration guide if the feature differs across versions or the compiler warns of deprecation.
5. Cross-check the dependency graph to confirm the class is on the classpath.
6. Write unit/integration tests for actual behavior, especially authentication/authorization/CSRF/session/token.

## 4. Navigating Branch-Pinned Spring Security Documentation URLs

Official index page:

- [Spring Security Reference](https://docs.spring.io/spring-security/reference/) – usually points to the **current documentation release**, which can change across releases.
- [Spring Security Reference 6.5](https://docs.spring.io/spring-security/reference/6.5/) – 6.5 branch documentation.
- [Spring Security Reference 7.0](https://docs.spring.io/spring-security/reference/7.0/) – 7.0 branch documentation.
- [Spring Security Reference 7.1](https://docs.spring.io/spring-security/reference/7.1/) – 7.1 branch documentation.

**Lookup snapshot November 6, 2026:** the index page lists stable `7.1.2`, `7.0.8`, and `6.5.11`, along with previews/snapshots of other branches. These are merely release numbers observed at the time of reading; **do not assume they are “latest” tomorrow** and do not blindly apply Security 7.1 to a project using Boot 3.x.

The URLs `/reference/6.5/` and `/reference/7.0/` are usually **by minor release line** and may be updated to the latest patch of that branch. They **do not automatically pin to a specific patch** (such as 6.5.3); therefore, when analyzing a very specific bug in an older patch, you must check the release tag/Javadoc artifact of that exact patch and historical release notes/advisories.

### 4.1. Verified Pinned URL Examples

| Purpose | Spring Security 6.5 | Spring Security 7.0 |
|---|---|---|
| Branch page | `https://docs.spring.io/spring-security/reference/6.5/` | `https://docs.spring.io/spring-security/reference/7.0/` |
| Servlet architecture | `https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html` | `https://docs.spring.io/spring-security/reference/7.0/servlet/architecture.html` |
| Servlet authentication architecture | `https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html` | `https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/architecture.html` |
| API `AuthenticationEntryPoint` | `https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/AuthenticationEntryPoint.html` | `https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/web/AuthenticationEntryPoint.html` |

The API/Javadoc path converts dots in the **package** `org.springframework.security.web` into `/` slashes, ending with `AuthenticationEntryPoint.html`. You must know the **fully qualified class name (FQCN)** and the artifact containing that class to find the exact documentation.

Some legacy URLs like `/spring-security/site/docs/6.5.x/api/...` still exist but may display a patch that is not the latest on the branch. For 6.5/7.0 Java APIs, prefer the **versioned Reference API** in the table above, then check the exact patch when the question requires it.

### 4.2. Do Not Guess Unverified Page URLs

Not every section has the same slug/path in every version. For example, headings like “Password Storage”, “Getting Spring Security”, “Passkeys”, or “Migration” may sit at different locations across branches. The right way to find them:

1. Open `/reference/6.5/` or `/reference/7.0/` matching the project.
2. Select **Servlet** or **Reactive**.
3. Use the sidebar/Search of the **selected version** to open the topic.
4. Verify the breadcrumb/URL path still contains `/6.5/` or `/7.0/`.
5. If a link returns 404, go back to that version’s sidebar; **do not** silently switch to `/reference/` latest.
6. Record the actual canonical URL you just opened in the ticket/PR/README, avoiding citing a guessed route.

### 4.3. The “latest” Page and Preview/Snapshot Channels

The documentation system may provide **Stable**, **Preview/RC**, and **Snapshot**. An API present in SNAPSHOT/RC **is not guaranteed to be included in the corresponding stable release** or have the same signature. If you are learning about a feature just announced on a blog, check the release tag/milestone:

```text
Blog/issue mentions feature X
        |
        +-- is it in 7.2.0-SNAPSHOT?
        +-- has it been released in 7.1.x stable?
        +-- which module provides it?
        +-- does it require a new Java/Boot/Framework baseline?
        +-- which binary was tested?
```

**Rule:** keep the same **release channel** across docs, artifacts, and tests. Do not take SNAPSHOT code, run it against a stable JAR, and conclude that Spring Security is missing an API.

## 5. Javadoc by Exact Package, Module, Class, and Patch

Suppose you want to inspect `AuthenticationEntryPoint.commence`. In Spring Security 6.5, the class is:

```text
FQCN    : org.springframework.security.web.AuthenticationEntryPoint
Artifact: org.springframework.security:spring-security-web
API URL : https://docs.spring.io/spring-security/reference/6.5/api/java/
          org/springframework/security/web/AuthenticationEntryPoint.html
```

Javadoc gives the method:

```java
void commence(
    HttpServletRequest request,
    HttpServletResponse response,
    AuthenticationException authException
) throws IOException, ServletException;
```

Here `HttpServletRequest` and `ServletException` belong to **jakarta.servlet** in Spring Security 6.x/7.x (unlike `javax.servlet` imports in many Spring Security 5.x projects). Looking only at the class name `AuthenticationEntryPoint` is not enough if the package/import or API baseline is wrong.

### 5.1. Sequence for Finding a Class Accurately

1. Identify the **FQCN**: via IDE Navigate Class, Java imports, or source/reference.
2. Identify the **module**: for example `AuthenticationEntryPoint` is in `spring-security-web`; `AuthenticationManager` is in `spring-security-core`; `HttpSecurity` is in `spring-security-config`.
3. Determine the **resolved version** of that module.
4. Open the API of the matching version branch; locate the package/class.
5. Check **Method Summary**, **Method Details**, **Constructor Summary**, generic types, visibility, exceptions, and `@since`.
6. Check whether the method is **inherited** from a parent/interface or only introduced in a newer release.
7. Check **Deprecated** and Javadoc replacement suggestions; do not silence warnings by downgrading dependencies.
8. If the API lives in another artifact, add the valid dependency and **synchronize the release train**; do not grab a package from a blog and add random JARs.

### 5.2. Distinguishing Classes with Similar Meaning Across Stacks

| Servlet | Reactive/WebFlux | What to Cross-Check |
|---|---|---|
| `HttpSecurity` | `ServerHttpSecurity` | Different DSLs and security filters |
| `SecurityFilterChain` | `SecurityWebFilterChain` | Servlet Filter vs. WebFilter |
| `AuthenticationEntryPoint` | `ServerAuthenticationEntryPoint` | Servlet response vs. `ServerWebExchange` |
| `AuthenticationManager` | `ReactiveAuthenticationManager` | Synchronous vs. reactive |
| `SecurityContextHolder` | `ReactiveSecurityContextHolder` | ThreadLocal vs. Reactor Context |
| `JwtDecoder` | `ReactiveJwtDecoder` | Decoding has different signatures/call contracts |
| `@EnableWebSecurity` | `@EnableWebFluxSecurity` | Completely different configuration |

**Do not copy WebFlux Java DSL into a Servlet application**, even though both use similar-sounding names like `authorizeExchange`/`authorizeHttpRequests`. For Spring MVC projects, prioritize `/servlet/...`; for WebFlux applications, choose `/reactive/...`. When a system has both starters, you must identify which stack Spring Boot actually selected and which filter chains are active.

### 5.3. Finding New or Removed Methods

When the IDE reports `Cannot resolve method`, ask:

- Is the method in the **latest** release but not in the project’s branch?
- Is the method a **Kotlin extension** rather than a Java API?
- Does the method belong to a **Spring Boot DSL**/different project?
- Is the method in an artifact not yet on the compile classpath?
- Are imports/overloads/generics different due to the Java baseline?
- Was the API deprecated and then removed in a new major release?
- Was the example written for WebFlux, test classpath, or XML config rather than Servlet Java DSL?

Choose the **version-matched Javadoc** and check type parameters before forcing the compiler with unsafe casts.

### 5.4. Patch-Level Javadoc When Absolute Precision Is Needed

The Reference `/6.5/api/java` page reflects the branch and may be updated to the current patch. If you are investigating `6.5.3` on production while the branch docs currently show `6.5.11`, a method fixed in 6.5.4 will mislead you.

How to handle it:

- Read the resolved artifact’s POM/manifest `Implementation-Version` or build info to know the actual patch.
- Find the **javadoc JAR** for the exact `group:artifact:version` on your artifact repository/Maven Central or the version on `javadoc.io` **if that artifact published Javadoc**.
- If no Javadoc exists for that patch, inspect the source JAR and matching release tag; check bytecode signatures with `javap`.
- Note in internal documentation: “Tested on Spring Security 6.5.3; online API /6.5 may reflect a newer patch”.
- Do not use `-SNAPSHOT` as a baseline to conclude an API appears in a released version.

**Do not assume Javadoc.io has every patch:** some versions may not have had Javadoc uploaded to that service. When absent, use the source JAR/release artifact as evidence.

## 6. Getting the Exact Version in Gradle

Use the repository’s Gradle Wrapper to avoid running a different build tool version locally than in CI.

### 6.1. Reading Dependency Graphs

```bash
./gradlew --version
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencies --configuration testRuntimeClasspath
```

`:app` is just an illustrative module. For a single-module project, omit `:app:`; if the module is named `:api`, use `:api:`. These commands only inspect graph/resolution; they do not modify dependencies.

- `compileClasspath`: which classes/methods/annotations are available at compile time?
- `runtimeClasspath`: which JARs will the application load at runtime?
- `testRuntimeClasspath`: are `spring-security-test`, Mockito, Testcontainers, and test-specific versions added?
- `dependencies` shows version selection due to conflicts/constraints with `->` and resolution notes.

### 6.2. Inspecting a Module with dependencyInsight

```bash
./gradlew :app:dependencyInsight \
    --dependency spring-security-web \
    --configuration runtimeClasspath

./gradlew :app:dependencyInsight \
    --dependency spring-security-config \
    --configuration compileClasspath

./gradlew :app:dependencyInsight \
    --dependency spring-security-oauth2-jose \
    --configuration runtimeClasspath

./gradlew :app:dependencyInsight \
    --dependency spring-security-test \
    --configuration testRuntimeClasspath
```

This command answers **why this version was selected**: Spring Boot BOM, direct dependency, transitive graph, constraints, forced version, resolution strategy, or lockfile. If a dependency does not appear, check the module/project path and configuration before adding a new one manually.

### 6.3. Why You Can Have a BOM and Still Get the Wrong Version

Some configurations can override the BOM:

```groovy
// Illustrates the mechanism; NOT recommended to manually override the release train.
configurations.all {
    resolutionStrategy.force(
        'org.springframework.security:spring-security-web:6.5.3'
    )
}
```

In CI, `dependencyInsight` helps detect `force`, telling you not to read Javadoc 6.5.11 as if runtime were 6.5.11. Do not copy the `force` snippet above into production; version selection must stay compatible across all Spring Security modules, Boot, and Framework.

Besides `force`, check:

- `gradle/libs.versions.toml` version catalogs;
- `platform("org.springframework.boot:spring-boot-dependencies:...")`;
- Gradle dependency locking and lockfiles;
- `resolutionStrategy.eachDependency`/`strictly`;
- the `io.spring.dependency-management` plugin if used;
- multi-project builds and composite builds;
- dynamic versions `6.+`, `latest.release`, or snapshot repositories.

After changing the BOM, **re-read the graph**. Do not trust it solely because `plugins { id 'org.springframework.boot' version '...' }` changed.

### 6.4. Inspecting Packaged JARs

An executable Spring Boot JAR normally stores dependencies in `BOOT-INF/lib`. On an actual built artifact:

```bash
jar tf path/to/actual-app.jar
```

Look for `BOOT-INF/lib/spring-security-*.jar` entries. `path/to/actual-app.jar` is an illustrative path and must be replaced with the actual generated artifact. For containers/Kubernetes, tie that artifact to the deployed image digest; `jar tf` on a laptop does not guarantee production runs that exact binary.

## 7. Getting the Exact Version in Maven

A project using `spring-boot-starter-parent` or `spring-boot-dependencies` in `dependencyManagement` may omit versions on individual dependencies:

```xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
  </dependency>
</dependencies>
```

This is an XML snippet, not a standalone `pom.xml`; the project’s parent/BOM must supply the versions.

### 7.1. Commands

```bash
./mvnw -version
./mvnw dependency:tree -Dincludes=org.springframework.security
./mvnw dependency:tree -Dincludes=org.springframework.security:spring-security-web
./mvnw help:effective-pom -Doutput=effective-pom.xml
```

On Windows use `mvnw.cmd`. If Maven does not support filtering as expected, run `dependency:tree` without includes and inspect the exact artifact/version. For multi-module builds, scope `-pl` and `-am` to the right service and profiles.

Read `effective-pom.xml` to see parent/BOM properties/overrides; read the dependency tree to see **resolved dependencies** rather than versions that are merely managed but never actually appear on the classpath.

### 7.2. When to Check runtimeScope and testScope

Maven has scopes such as `compile`, `provided`, `runtime`, and `test`. A class in `spring-security-test` only on the test classpath cannot be used in production main sources if the dependency is test-scoped. Conversely, a failure in a Boot app running on a container may involve a provided servlet API or transitives that differ from tests.

Use the same Maven profiles/properties as CI and production. For projects using Java toolchains, verify `maven-compiler-plugin`/`maven-toolchains-plugin` so you do not mistake JDK errors for Spring version compile errors.

### 7.3. Maven Property Overrides Are Not the First Resort

Spring Security documentation describes overriding versions via properties like `spring-security.version` in a Spring Boot-managed project. However, you should not **override just to make a web example compile**; first verify compatible release lines and modules. Security fixes may require updating Spring Framework or Boot as well.

## 8. Comparing APIs by Version: 6.5 vs. 7.x

### 8.1. WebAuthn/Passkeys: Even the Dependencies Differ

**Spring Security 6.5** Reference at `/reference/6.5/servlet/authentication/passkeys.html` instructs using `spring-security-web` together with `com.webauthn4j:webauthn4j-core`.

```groovy
// Gradle snippet for the 6.5 branch; versions must follow BOM/policy.
dependencies {
    implementation 'org.springframework.security:spring-security-web'
    implementation 'com.webauthn4j:webauthn4j-core'
}
```

**Note:** if WebAuthn4J is not managed by the BOM in your build, you must specify the **version guided/compatible in the 6.5 documentation** (the 6.5 page illustrated `0.29.7.RELEASE`), rather than omitting the version and expecting the build to guess. Avoid hardcoding into production without checking the release notes of your actual branch.

The newer **Spring Security 7.x** Reference at `/reference/servlet/authentication/passkeys.html` illustrates the separate artifact `org.springframework.security:spring-security-webauthn`.

```groovy
// Gradle snippet for the 7.x branch; do not copy into a 6.5 application.
dependencies {
    implementation 'org.springframework.security:spring-security-webauthn'
}
```

Therefore, when you see “`spring-security-webauthn` not found in 6.5”, do not just add repositories and retry; **read the versioned docs** and published module artifacts. Passkey support classes/interfaces may change packaging/integration between the two branches.

**Methodological takeaway:** the versioned Reference determines the minimum dependency list to **enable a feature**; Javadoc gives you the class APIs; the Gradle/Maven graph confirms the actual binaries.

### 8.2. MFA: Features May Belong to a Newer Branch

The current Spring Security MFA Reference page describes the concept of `FactorGrantedAuthority` and multi-factor authorization managers. Do not look at that code and assume it runs on **Spring Security 6.5**.

If a snippet such as:

```java
@EnableMultiFactorAuthentication
class SecurityConfiguration {
    // ... security configuration ...
}
```

comes from 7.x documentation, before using it you must:

- Open the **7.x branch docs** for full imports and annotations/options.
- Check the version-matched Javadoc of `EnableMultiFactorAuthentication` and `FactorGrantedAuthority`.
- Cross-check Boot/Framework/Java baselines and artifact dependencies.
- Verify which factors the use case requires, rather than just “enabling” an annotation and assuming MFA is sufficient.
- For 6.x projects, design a policy suited to the version or plan a migration, without forcing a 7.x class onto a 6.x classpath.

An **authentication mechanism** and an **MFA policy** are not the same thing: enabling both `formLogin` and `oneTimeTokenLogin` in the same project may offer **two alternative ways to log in**, without automatically requiring both.

### 8.3. JWT Resource Server: Keep the Right Packages and Boot Properties

Reference for 6.5 has `/reference/6.5/servlet/oauth2/resource-server/jwt.html`. A Spring Security Java DSL snippet:

```java
http
    .authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated())
    .oauth2ResourceServer(oauth2 -> oauth2
        .jwt(Customizer.withDefaults()));
```

This is a **snippet inside `SecurityFilterChain`**, not runnable standalone with `javac`. The related classes belong to:

- `org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationProvider` – resource-server authentication.
- `org.springframework.security.oauth2.jwt.JwtDecoder` – JWT decoding/verification in OAuth2 JOSE.
- `org.springframework.security.config.annotation.web.builders.HttpSecurity` – Servlet configuration.
- `org.springframework.security.web.SecurityFilterChain` – HTTP filter chain.

Spring Boot property:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org
          audiences: https://api.example.org
```

Check the **Spring Boot Reference** of the same branch to know which properties are supported in your Boot version; check Spring Security Reference/Javadoc for the corresponding decoders/validators. `issuer-uri` verifies the issuer and `audiences` verifies the audience; do not merely see `JwtDecoder` in Javadoc and conclude the app checks audience. You must test tokens with invalid `iss`/`aud`/`exp`.

### 8.4. Method Security and DSL

For Servlet:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {}
```

The presence of the API annotation does not mean every `@PreAuthorize` method is enforced: the class must be a proper Spring bean/proxy, the annotation must be enabled, and invocations must not bypass the AOP interceptor. The Method Security Reference section explains semantics; Javadoc only describes annotations/properties.

Do not mix `authorizeRequests`/`antMatchers` from old Spring Security 5.x articles with `authorizeHttpRequests`/`requestMatchers` from versions 6/7. Deprecated/removed APIs must be checked in Javadoc and the Migration Guide of the **matching branch** before mechanically substituting equivalents.

## 9. Standalone Java 17: Building Documentation Paths for the Right Release Line

The code below **compiles/runs on Java 17+**, without requiring Spring, Gradle, or Maven. It illustrates how to **select 6.5 or 7.0 documentation** once the exact version is known. The program does not access the Internet or read project dependencies, does not verify that URLs exist, and does not determine the “latest version”.

**Why is this useful?** When writing internal docs or reviewing PRs, you may receive a raw version like `6.5.11` from the dependency graph, parse it into `major.minor`, and construct **branch-matched** Reference/API links instead of inserting the default `/reference/`.

Save as `SpringSecurityDocsLocatorDemo.java`:

```java
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class SpringSecurityDocsLocatorDemo {

    record Version(int major, int minor, int patch) {

        private static final Pattern NUMERIC =
            Pattern.compile("^(\\d+)\\.(\\d+)\\.(\\d+)$");

        static Version parse(String value) {
            Matcher m = NUMERIC.matcher(value);
            if (!m.matches()) {
                throw new IllegalArgumentException(
                    "Expected numeric major.minor.patch");
            }
            return new Version(
                Integer.parseInt(m.group(1)),
                Integer.parseInt(m.group(2)),
                Integer.parseInt(m.group(3))
            );
        }

        String line() {
            return major + "." + minor;
        }

        String root() {
            return "https://docs.spring.io/spring-security/"
                + "reference/" + line() + "/";
        }

        String servletArchitecture() {
            return root() + "servlet/authentication/architecture.html";
        }

        String api(String fullyQualifiedName) {
            if (!fullyQualifiedName.matches(
                    "[A-Za-z_$][\\w$]*(\\.[A-Za-z_$][\\w$]*)+")) {
                throw new IllegalArgumentException("Invalid Java class name");
            }
            return root() + "api/java/"
                + fullyQualifiedName.replace('.', '/') + ".html";
        }
    }

    public static void main(String[] args) {
        Version six = Version.parse("6.5.11");
        Version seven = Version.parse("7.0.8");

        System.out.println("6.5 docs: " + six.root());
        System.out.println("6.5 architecture: "
            + six.servletArchitecture());
        System.out.println("6.5 API: " + six.api(
            "org.springframework.security.web.AuthenticationEntryPoint"));

        System.out.println("7.0 docs: " + seven.root());
        System.out.println("7.0 API: " + seven.api(
            "org.springframework.security.web.AuthenticationEntryPoint"));

        System.out.println("Same line? "
            + six.line().equals(seven.line()));
    }
}
```

Run:

```bash
javac SpringSecurityDocsLocatorDemo.java
java SpringSecurityDocsLocatorDemo
```

**Exact** stdout:

```text
6.5 docs: https://docs.spring.io/spring-security/reference/6.5/
6.5 architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
6.5 API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/AuthenticationEntryPoint.html
7.0 docs: https://docs.spring.io/spring-security/reference/7.0/
7.0 API: https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/web/AuthenticationEntryPoint.html
Same line? false
```

### 9.1. Intentional Limitations

- The utility only supports **3 numeric parts** `major.minor.patch`; it does not parse `7.2.0-RC1`, `6.5.12-SNAPSHOT`, or Enterprise versions with qualifiers/four parts.
- `root()` points to the **release line** page and does not guarantee **historical patch** accuracy; for patch-level precision, inspect the artifact/source tag/versioned Javadoc.
- A class may be removed, renamed, or moved to another module: a constructed URL does not mean the actual page exists. You must open and verify the link.
- Docs links are only **documentation** and say nothing about actual running dependencies. Read `dependencyInsight`/`dependency:tree` first.
- Do not use a link builder as a security scanner or to infer affected CVEs; a vulnerability requires the full advisory and configuration/runtime context.
- For the reactive stack, topic paths sit under `reactive/...`; do not hardcode Servlet architecture in a WebFlux application.

## 10. Spring Code Is on the Right Version but Still Fails to Compile: What to Check?

A Reference example may be only a **snippet** missing imports, beans, dependencies, or configuration. This is normal for conceptual docs. You must distinguish:

**A. Symbol not found at compile time**

```text
cannot find symbol
  symbol: method webAuthn(...)
```

Check whether the method exists in the version, the `spring-security-config` module, the WebAuthn dependency, Java vs. Kotlin DSL, overloads/imports, and Spring Framework/Java requirements.

**B. Symbol exists, but runtime ClassNotFoundException**

```text
java.lang.NoClassDefFoundError:
  org/springframework/security/.../SomeClass
```

Check `runtimeClasspath`, packaging, containers, test vs. production scopes, transitive dependencies/exclusions, and module version drift.

**C. Class exists, but runtime NoSuchMethodError**

```text
java.lang.NoSuchMethodError:
  ...someMethod(...)...
```

Often involves a **binary version mismatch**: code compiled against a newer API while runtime loads an older JAR. Inspect `compileClasspath` vs. `runtimeClasspath`, `BOOT-INF/lib`, and classloader resolution. Do not fix it by adding a random version override.

**D. Code runs, but behavior differs from docs**

For example `formLogin` redirects 302 unlike REST bearer 401, `SecurityContext` does not persist across requests, or `@PreAuthorize` does not block. Check filter configuration, Spring Security 6 explicit context save, `@EnableMethodSecurity`, CSRF, and chain matching. Version-matched Javadoc tells you the API, but **integration tests** prove behavior.

### 10.1. “Cannot resolve symbol” Is Not Always a Version Issue

- Mistyped package or selecting a Servlet class instead of Reactive.
- Stale IDE indexing/cache or unrefreshed Gradle/Maven.
- Missing `spring-security-oauth2-jose` module when calling `JwtDecoder`.
- Test code placed in `src/main/java` while `spring-security-test` is only in test scope.
- Using Java 8 to compile Java 17 code or Jakarta APIs in a Spring 5 project.
- Copying from XML/Kotlin DSL to Java without adapting syntax.
- Method with generic types requiring different imports or `Customizer.withDefaults()` in the wrong context.
- Boot autoconfiguration differing because a custom `SecurityFilterChain` was declared.
- New API documented in `7.1-SNAPSHOT` while the project is on `7.0` stable.

Before adding a dependency, **identify FQCN + artifact + version + stack + sample language**.

## 11. Cross-Checking Source Tags and Code History When Docs Are Not Enough

When you need to verify the behavior of a **specific** version, follow this sequence:

1. From `dependencyInsight`/`dependency:tree`, obtain the exact `org.springframework.security:artifact:version`.
2. Open the corresponding release/tag in the source repository or download `-sources.jar` of the same version from the artifact repository.
3. Inspect the implementation of the class in question (for example `ExceptionTranslationFilter`, `JwtAuthenticationProvider`, `DaoAuthenticationProvider`).
4. Inspect the accompanying tests on the **same tag** to understand behavior/internal contracts; do not read tests on `main`.
5. Compare patch-matched Javadoc and migration notes; check changes from patch A to patch B.
6. If there is a CVE, read the vendor’s security advisory to avoid basing analysis on a single commit alone.
7. Use the application’s own unit/integration tests to reproduce, rather than merely recounting logic read from source.

**Watch out:** `main` may already contain unreleased fixes; maintenance branches may contain different backports. Verify the commit/tag from the release artifact rather than inferring from line numbers in source.

### 11.1. Using javap When You Need the Real Signature

If you already have the exact version JAR, the JDK `javap` tool can inspect public members:

```bash
javap -classpath path/to/spring-security-web-6.5.11.jar \
    org.springframework.security.web.AuthenticationEntryPoint
```

The command is an example; you must use the real JAR path. With a Java 17 toolchain, `javap` shows signatures inside that **specific binary**. This is strong evidence when the docs website displays a newer patch or a class is missing. Still, `javap` does not fully describe semantics/security conditions; combine it with Reference/tests/advisories.

## 12. Migration: From the 6.x Branch to 7.x

Official references:

- [Preparing for 7.0 (Spring Security 6.5)](https://docs.spring.io/spring-security/reference/6.5/migration-7/index.html)
- [Migrating to 7.0](https://docs.spring.io/spring-security/reference/migration/)

The migration documentation states that **6.5 is the last branch of 6.x** and recommends preparing changes directly in the 6.5 application before moving to 7.0. It also guides updating to a compatible Spring Boot 4.0 release before completing the move to Spring Security 7.

Do not decide unilaterally by changing:

```groovy
// Wrong example if the system still uses the Spring Boot 3/Security 6 train:
implementation 'org.springframework.security:spring-security-config:7.0.8'
```

That wrong snippet is shown as a warning. **A single 7.0.x module** does not prove compatibility with older 6.x/Framework/Boot modules, especially around APIs, filters, JSON serialization, and WebAuthn.

### 12.1. Documentation-Driven Migration Process, Not Guesswork

```text
1. Inventory Spring Boot, Security, Framework, and JDK versions.
2. Read the 6.5 preparation guide + versioned Javadoc of current code.
3. Perform deprecation cleanup and migration flags per guidance.
4. Choose a Spring Boot 4.x + Security 7.x supported release train.
5. Read the target 7.x Reference/Javadoc and migration guide.
6. Update dependency management/BOM and all related modules.
7. Build, compile, and run unit/integration/security tests.
8. Test authentication, authorization, CSRF, session,
   JWT, OAuth2/OIDC, passkeys/WebAuthn/MFA, logout/revocation.
9. Inspect resolved versions, image digest, and canary behavior.
10. Record decisions, links, versions, and rollback plan.
```

Do not treat a major release as syntax-only: there may be changes in Servlet/Jakarta, JSON/Jackson versions, WebAuthn architecture, and method security defaults. Every change must be verified against target docs and production integration tests.

### 12.2. Do Not Confuse Migration Docs with Security Fixes

A security advisory may require **a specific patch** in 6.5/7.0 and carry OSS/Enterprise support conditions. Do not use the 7.0 migration guide as the sole source for CVE questions: read [Spring Security Advisories](https://spring.io/security/) to get affected/fixed ranges and release channels, then choose a compatible upgrade path.

A newer 7.x release **does not automatically mean every CVE is patched** without checking dates/conditions; newly released patches may include additional security notes. “Not affected” must also be based on the exact runtime and configuration.

## 13. Lookup Practice: Four Typical Scenarios

### Scenario A – Asking Which Module AuthenticationEntryPoint Belongs To

**Context:** Spring Security 6.5 project; need to customize 401/redirect.

Steps:

1. Gradle/Maven: confirm `spring-security-web` resolved to the exact 6.5 patch.
2. Open [Javadoc 6.5 AuthenticationEntryPoint](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/AuthenticationEntryPoint.html).
3. Read `commence(HttpServletRequest,HttpServletResponse,AuthenticationException)`, exceptions, and implementations.
4. Open [Servlet Authentication Architecture 6.5](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html) to understand where EntryPoint sits in the flow.
5. Test anonymous access to the endpoint: browser form returns a redirect per policy; Basic/Bearer includes `WWW-Authenticate` with the right scheme.
6. Distinguish `AccessDeniedHandler` 403 for authenticated users lacking permission; EntryPoint is not an authorization engine.

### Scenario B – Wanting to Use Passkeys on a 6.5 Project

1. Confirm Spring Security 6.5 patch/build JDK/Boot.
2. Open [Spring Security 6.5 Passkeys](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passkeys.html).
3. Read WebAuthn4J dependencies, repositories, and `HttpSecurity.webAuthn`.
4. Open Javadoc of the classes/DSL used to confirm methods.
5. Test registration/authentication with signed assertions, expected origin/RP ID, and UP/UV/challenge/session binding.
6. If you see `spring-security-webauthn` on the latest page, note that it belongs to the 7.x branch; do not add it to 6.5 without verification.

### Scenario C – Testing a JWT Resource Server

1. Check `spring-security-oauth2-resource-server` and `spring-security-oauth2-jose` at runtime.
2. Open [JWT Resource Server 6.5](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html).
3. Check `JwtDecoder` and `JwtAuthenticationProvider` in the branch-matched Javadoc.
4. Check Boot properties `issuer-uri`, `jwk-set-uri`, and `audiences` in the Boot Reference.
5. For unit authorization tests, `spring-security-test` `jwt()` can inject a mock principal; **it does not prove the JWT signature was verified**.
6. For integration tests, send a real signed JWT in `Authorization: Bearer ...` to test invalid signature, issuer, audience, expiry, scope, and HTTP 401/403.

### Scenario D – Encountering New MFA Code in a Blog Post

1. Identify the date/Spring Security version the blog post discusses.
2. Open the MFA docs **in the branch** of that feature and check whether `FactorGrantedAuthority` exists in your project’s specific API.
3. Check annotations/authorization managers/imports in the target Javadoc and module dependencies.
4. If the code is for 7.x while the app is on 6.5, read migration docs to decide whether to upgrade or keep a compatible custom policy.
5. Do not assign factor authorities from a user request/session flag, because the security model must verify real factors.
6. Test missing factor/step-up/recovery, not just the happy path after `@WithMockUser`.

## 14. Reading the Right Documentation to Evaluate Security Behavior

In Spring Security, **the right API signature** is not enough to prove security. An `authorizeHttpRequests` configuration can compile while private routes remain exposed due to matcher order. A `JwtDecoder` can exist in Javadoc while the production bean fails to check `aud`. A `@PreAuthorize` annotation can compile while method security is not enabled.

Always check all three layers:

| Layer | Question | Evidence |
|---|---|---|
| **API/binary** | Does the class/method actually exist in this version? | Version-matched Javadoc, `javap`, compiled tests |
| **Configuration/flow** | Does Spring Security actually activate the mechanism on the right routes? | Version-matched Reference, filter chain, integration tests |
| **Security policy** | Are evidence and permissions properly enforced? | Negative tests, threat model, account/tenant policy, advisories |

### 14.1. Tests Distinguish Mocks from Real Credentials

`@WithMockUser`, `user()`, or `jwt()` from Spring Security Test can construct a synthetic Authentication to test **authorization**, without proving passwords/JWT signatures. Tests using those fixtures are very useful, but they are **not** evidence of a secure credential verifier.

To verify real authentication:

- `httpBasic()`/`formLogin()` send credentials through the real `SecurityFilterChain`, `AuthenticationManager`, `UserDetailsService`, and `PasswordEncoder` (not mocked to always succeed).
- For JWT, send real signed tokens and use real decoders/validators, not just the `jwt()` fixture.
- For WebAuthn, use virtual/hardware authenticators or test signed assertions running the real verifier, not just a mock principal.
- For OTT, test token TTL, single-use consumption, session lifecycle, CSRF, and concurrency against a real token store.

Reference/Javadoc content serves as **technical guidance**; tests on the resolved version are the evidence of application behavior.

### 14.2. Avoid Mixing HTTP Semantics Across Versions and Stacks

With Servlet browser form login, an unauthenticated client may receive `302 /login`; with a Bearer Resource Server it receives `401 WWW-Authenticate: Bearer`; an authenticated user lacking a role typically receives `403`. Read the authentication, authorization, and exception handling sections of the **matching stack/version**, rather than extrapolating one app response to every protocol.

## 15. Recording Evidence in Tickets, PRs, and Internal Docs

A good technical note answering “Does this method run in our project?” should include:

```text
Project/service  : account-api
Git commit       : <commit SHA from repository>
Spring Boot      : <resolved version>
Spring Security  : <resolved group:artifact:version per module>
Spring Framework : <resolved version>
JDK              : Java 17 / 21 (actual toolchain)
Source           : src/main/java/.../SecurityConfig.java
Docs reference   : https://docs.spring.io/spring-security/reference/6.5/...
Docs API         : https://docs.spring.io/spring-security/reference/6.5/api/java/...
Docs release line: 6.5 (may move to latest patch of branch)
Actual artifact  : build ID / SHA / container digest
Behavior check   : test name + result + timestamp
Caveat           : Javadoc branch vs runtime exact patch
```

This is a **data template** for learners to fill in, not evidence from a real service. Record URLs, versions, check dates, and test outcomes; never record production passwords, OAuth tokens, private keys, or cookies in tickets.

### 15.1. Version Pinning When Sharing Links in a Team

Do not send a bare:

```text
https://docs.spring.io/spring-security/reference/
```

when reviewing a PR for a Spring Security 6.5 project. Send:

```text
https://docs.spring.io/spring-security/reference/6.5/
https://docs.spring.io/spring-security/reference/6.5/api/java/
    org/springframework/security/web/AuthenticationEntryPoint.html
```

The API path above is line-wrapped **solely for presentation in this document**; when opening it, join the URL into a single line. That way reviewers know the explanation is based on the 6.5 branch rather than current 7.1 docs.

### 15.2. When No Versioned Page Exists for the Topic

- Use the branch index and sidebar/search.
- Check source tags/release notes.
- Use that binary’s Javadoc from the artifact repository; `javap` when needed.
- Do not “substitute latest” without marking the difference.
- If the library is external to Spring (Nimbus JOSE, WebAuthn4J, Spring Authorization Server), find that library’s **own documentation** at the actual version.
- Where doc contents changed after a patch, note the snapshot/date and use tests to reproduce.

## 16. Documentation and Version Drift Verification Matrix

| Lookup Test Case | Evidence to Collect | Expected Outcome |
|---|---|---|
| Boot 3 project with unknown Security patch | `dependencyInsight`/`dependency:tree` | Identify exact `group:artifact:version` |
| Reading `/reference/` latest for a 6.5 project | URL showing latest vs. 6.5 | Do not copy 7.x APIs into 6.5 |
| Method exists in 7.1 but missing in 6.5 | Javadoc of both branches | Correctly report introduced/removed, check migration |
| 6.5 Javadoc URL class does not exist | FQCN and module | Check package/artifact, do not guess version |
| Java compiler reports missing method | compileClasspath + Javadoc API | Distinguish wrong code vs. older version |
| Runtime `NoSuchMethodError` | Compile/runtime JARs and artifact | Detect version drift/classloader issue |
| Snippet uses `javax.servlet` in Boot 3 app | Imports/Jakarta API | Distinguish Spring Security 5.x vs. 6.x |
| Reading WebFlux DSL for an MVC app | Application type + Reference path | Choose the right Servlet API |
| Copying WebAuthn dependency `spring-security-webauthn` into 6.5 | Versioned Passkeys Reference | Read 6.5’s WebAuthn4J dependency |
| Using MFA 7.x annotation in 6.x | API/Reference + migration | Do not promise compilation on 6.x |
| JWT tests only use `jwt()` | Test setup + real decoder test | Do not claim signature is verified |
| CVE alert in scanner | Exact runtime + Spring advisory | Record affected version/config/mitigation |
| BOM upgraded but lockfile still old | dependency graph + lockfile | Update graph before concluding patched |
| Branch API docs show newer patch than runtime | Release tag Javadoc/source JAR | Do not attribute newer patch behavior to older patch |
| Production image differs from CI build | digest/SBOM/manifest | Conclude only from actual deployed JAR |
| Looking up “migration” in latest 7.x for 6.5 project | 6.5 preparation guide | Follow the proper path and compatibility |

## 17. Common Mistakes and How to Fix Them

### Mistake 1 – Googling and Grabbing the First Snippet

The snippet may use `WebSecurityConfigurerAdapter` or `antMatchers` from Spring Security 5.x while the project uses 6/7. Fix: open docs with `/6.5/` or `/7.0/`, read the Java DSL, and verify Javadoc/migration.

### Mistake 2 – Assuming Latest Javadoc Is the API for Every Patch

Even within the same release line, patches can add or fix behavior. Fix: pin the exact runtime patch and check matching Javadoc/source tag/`javap` when needed.

### Mistake 3 – Knowing Only the Spring Boot Version

The Boot BOM selects Spring Security, but it may be overridden/locked or differ at runtime. Fix: inspect the resolved graph for `spring-security-core/web/config/...` and the production artifact.

### Mistake 4 – Adding a Random JAR on ClassNotFoundException

This can knock modules off the same release train and cause new errors. Fix: find the right artifact/module, BOM/constraints, and test the full graph.

### Mistake 5 – Reading Reactive Docs for Servlet

`SecurityWebFilterChain` is not `SecurityFilterChain`, and `ServerHttpSecurity` is not `HttpSecurity`. Fix: determine the stack before opening the sidebar.

### Mistake 6 – Confusing Sample Code with a Standalone App

A snippet showing `http` without imports/bean/context may only illustrate the DSL. Fix: label it “snippet”, create a `@Bean SecurityFilterChain` and required user store/decoder, then compile/test.

### Mistake 7 – Upgrading a Single Module from a Newer Branch into an Old Project

Spring Security 7 WebAuthn/MFA components are not automatically compatible with Spring Security 6 and Boot 3. Fix: read migration docs and upgrade the coordinated release train.

### Mistake 8 – Reading “MFA” and Thinking Enabling a Second Login Suffices

Multiple login mechanisms can be an **OR** choice, not an **AND** policy. Fix: read the version-matched MFA Reference, define factor assurance, and test missing factors.

### Mistake 9 – Testing Tokens/JWT via a Mock Principal and Claiming Signature Verification

`@WithMockUser`/`jwt()` bypasses the verifier. Fix: add integration tests with passwords/real signed JWTs and negative tests.

### Mistake 10 – Treating a Security Advisory Like General Release Notes

A CVE has its own affected range, feature prerequisites, fixes, and support channels. Fix: use [spring.io/security](https://spring.io/security/), resolved deployed version, and configuration evidence.

## 18. Operational Checklist for Your Next API Lookup

1. **Identify the application:** Spring Boot version, Security version, Framework version, Java/JDK toolchain, Servlet or WebFlux.
2. **Capture the real dependency graph:** Gradle/Maven compile/runtime/test and module coordinates.
3. **Select the release line:** e.g., 6.5 or 7.0, never defaulting to latest.
4. **Open Reference on the same line:** find the feature via sidebar, verify URL and stable/preview channel.
5. **Find the FQCN:** import/type/class, identify the module artifact.
6. **Open Javadoc on the same line:** method/constructor/`@since`/deprecated/generics.
7. **If exact patch precision is needed:** artifact Javadoc/source JAR/tag/`javap`; note if online branch docs reflect a newer patch.
8. **If upgrading:** open the source→target preparation/migration guide, Boot BOM compatibility, and required JDK.
9. **Verify configuration:** filters, matchers, CSRF, session, auth providers, JWT validators, passkey/MFA dependencies.
10. **Compile a test/feature slice:** never copy snippets directly into production.
11. **Test negative security cases:** unauthenticated, wrong password, invalid token, insufficient scope, wrong tenant, replay/expired credential.
12. **Cross-check runtime artifact:** bootJar/SBOM/image digest if the issue occurs in staging/production.
13. **When facing a CVE:** check the advisory and release fix matching exact source/version/configuration.
14. **Record evidence:** documentation URL, exact version, commit, test name, check timestamp, and applicability limits.

## 19. Self-Assessment Questions

**Q1.** A project declares `spring-boot-starter-security` with no version. How do you find out exactly which `AuthenticationEntryPoint` you have?  
**Answer:** Get the resolved `spring-security-web` version via Gradle `dependencyInsight` or Maven `dependency:tree`, open the API Javadoc of the matching branch, and verify the exact patch via JAR/source tag when needed.

**Q2.** You read `/reference/` and see a new MFA API; why can you not say it works on Spring Security 6.5?  
**Answer:** Unversioned pages typically track the current release. You must open `/6.5/` Reference/Javadoc and check availability; new MFA APIs may belong to 7.x.

**Q3.** Does “the class Javadoc has the method” prove the application runs that method?  
**Answer:** No. You also need the right compile/runtime dependencies, bean wiring, filters, and integration tests.

**Q4.** Why not just check the `AuthenticationEntryPoint` import in the IDE?  
**Answer:** The import identifies the FQCN, but does not determine the API version/method signature, module dependency, or HTTP behavior. You need version-matched Javadoc/Reference.

**Q5.** Do Spring Security 6.5 and 7.x guide adding the same WebAuthn dependency?  
**Answer:** No. 6.5 Reference illustrates `spring-security-web` + `webauthn4j-core`, whereas the newer 7.x page uses `spring-security-webauthn`.

**Q6.** Can `ServerHttpSecurity` code be used as-is in a Spring MVC/Servlet app?  
**Answer:** No. Servlet uses `HttpSecurity` and `SecurityFilterChain`; Reactive uses `ServerHttpSecurity` and `SecurityWebFilterChain`.

**Q7.** If you hit `NoSuchMethodError` after deployment, what should you do before editing code?  
**Answer:** Check compile/runtime dependency graphs, the actual JAR in the artifact/image, and the classloader; runtime may be loading a different version than compile time.

**Q8.** A `/6.5/` Javadoc link displays `6.5.11`, while production runs `6.5.3`. Can you treat all of those docs as the exact API for patch 6.5.3?  
**Answer:** No. Branch docs usually track the current patch; for exact patch precision you need the corresponding Javadoc/source/binary.

**Q9.** If a test using `jwt()` from `spring-security-test` passes, can you conclude the app verifies JWT signatures?  
**Answer:** No. It can inject a mock `JwtAuthenticationToken`; you must test with a real decoder and tokens signed by a test key.

**Q10.** When facing a CVE, should you trust the “latest” Reference section or the Advisory?  
**Answer:** Check the Spring security advisory for the exact CVE to get affected/fixed ranges, conditions, and support channels; inspect exact runtime/deploy/config, then use versioned docs and migration guides to pick a compatible patch.

## Official References

- [Spring Security Reference – version index/selector](https://docs.spring.io/spring-security/reference/) – observe Stable/Preview/Snapshot branches; do not use as a pinned link for older projects.
- [Spring Security Reference 6.5](https://docs.spring.io/spring-security/reference/6.5/) – documentation for the 6.5 branch.
- [Spring Security Reference 7.0](https://docs.spring.io/spring-security/reference/7.0/) – documentation for the 7.0 branch.
- [Spring Security Reference 7.1](https://docs.spring.io/spring-security/reference/7.1/) – documentation for the 7.1 branch.
- [Getting Spring Security 6.5](https://docs.spring.io/spring-security/reference/6.5/getting-spring-security.html) – release numbering, BOM, and dependency management.
- [Servlet Authentication Architecture 6.5](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html) – `SecurityContext`, providers, filters, entry point.
- [Javadoc 6.5 AuthenticationEntryPoint](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/AuthenticationEntryPoint.html) – branch-matched class/method signature.
- [Javadoc 7.0 AuthenticationEntryPoint](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/web/AuthenticationEntryPoint.html) – 7.0 branch API comparison.
- [Spring Security 6.5 Passkeys](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passkeys.html) – 6.5 WebAuthn dependencies & config.
- [Spring Security Passkeys 7.x](https://docs.spring.io/spring-security/reference/servlet/authentication/passkeys.html) – WebAuthn module of the current line.
- [Spring Security 6.5 JWT Resource Server](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html) – `JwtDecoder`, validators, and OAuth2 bearer.
- [Spring Security 6.5 Preparing for 7.0](https://docs.spring.io/spring-security/reference/6.5/migration-7/index.html) – pre-migration preparation.
- [Spring Security Migrating to 7.0](https://docs.spring.io/spring-security/reference/migration/) – post-transition changes.
- [Spring Boot Build Systems](https://docs.spring.io/spring-boot/reference/using/build-systems.html) – BOM, version management.
- [Gradle Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html) – `dependencies`/`dependencyInsight`.
- [Apache Maven Dependency Plugin](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html) – `dependency:tree`.
- [Spring Security Advisories](https://spring.io/security/) – affected/fixed versions and vulnerability conditions.
