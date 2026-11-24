# Looking Up Reference Docs, API Javadoc, and Examples for Your Exact Version

> **Topic:** Spring Security fundamentals · **Versions and Next Steps**. This lesson builds a repeatable process to find **Reference documentation**, **API Javadoc**, **sample code, and tests** compatible with the Spring Security version **actually resolved/running in the project**. Hands-on examples use **Java 17, Maven, Spring Boot 3.3.5, Spring Security 6.3.4 default via BOM, Servlet/Spring MVC, JUnit 5, and MockMvc**. Do not blindly apply Spring Security 7 API signatures to a project running 6.x or vice versa.

## 1. Which Version Is “Currently in Use”?

When seeing a compilation error on a Spring Security API, learners often search for the class name in a search engine and grab the first snippet. That approach is risky because many things can differ:

- **Spring Boot version:** for example §3.3.5§, §3.5.x§, or §4.x§.
- **Spring Security version:** for example §6.3.4§, §6.5.x§, or §7.x§, managed by the BOM but potentially overridden.
- **Spring Framework version** and **Java version**, which have their own compatibility constraints.
- **Servlet or reactive runtime:** §HttpSecurity§/§SecurityFilterChain§ differs from §ServerHttpSecurity§/§SecurityWebFilterChain§.
- **Modules on the classpath:** §spring-security-web§, §spring-security-config§, §spring-security-test§, §spring-security-oauth2-resource-server§, §spring-security-oauth2-jose§...
- **Which release the documentation belongs to:** the §/spring-security/reference/§ page usually displays the current release, not necessarily the release your application uses by default.
- **Which tag/commit the example code belongs to:** the README on the §main§ branch or code on an old blog post does not automatically guarantee compilation with the current project.

**Order of precedence:** identify the *resolved* dependency and runtime artifact → select the right major/minor/patch and stack → read the Reference explaining behavior → check the exact Javadoc of the class/method → check samples for the exact tag and dependencies → compile/test in the real project.

### 1.1 Why Reading pom.xml Alone Is Not Enough?

For example, a Maven file contains:

§§§xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
§§§

This snippet **has no Spring Security version** because the Spring Boot parent/BOM manages the dependency. Readers should not assume “Boot 3 means the latest Security 6”. Even within Spring Boot 3, different minor/patch releases can manage different versions. Maven dependency management, §<spring-security.version>§, BOM imports, or directly declared dependencies can change the outcome.

Example verified against the BOM: **Spring Boot 3.3.5 manages Spring Security 6.3.4** in its default set, if the project does not override it. However, you must verify the dependency tree: do not claim that every Boot 3.3.5 application in practice still uses exactly 6.3.4.

### 1.2 Do Not Treat “Latest” as “Most Correct”

An official page updated in 2026 might use Spring Security 7.x. That page is accurate **for its release**, but examples in it might use new APIs, different signatures, namespaces, or default behaviors compared to 6.3.x.

| Illustrative application branch | Spring Security typically managed | How to use documentation |
| --- | --- | --- |
| Spring Boot 3.3.5 | Spring Security 6.3.4 by default if not overridden | View Javadoc 6.3.4; cross-check Reference 6.x and changelog |
| Spring Boot 3.5.x | Spring Security 6.5.x per the specific Boot release's BOM | Use Reference 6.5 and the actual patch Javadoc |
| Spring Boot 4.x | Spring Security 7.x per the corresponding BOM | Use Reference 7.x, Javadoc 7.x, and the migration guide |
| Not using Boot BOM | Chosen by the project | Inspect §dependency:tree§/§dependencyInsight§ before choosing docs |

The table is only a **way to identify generations**, not a complete compatibility matrix for every patch. When upgrading a framework, always check the compatibility matrix and dependency management of the chosen release.

## 2. Map of the Three Official Documentation Types

| Source | What question does it answer? | When to use it? | What to watch out for |
| --- | --- | --- | --- |
| **Spring Security Reference** | “How does this mechanism work, how to configure it properly, and what are example use cases?” | Learning authentication, authorization, CSRF, OAuth2, filter chain, testing | A newer version's page may describe different behavior/APIs |
| **API Javadoc** | “What are the class, interface, package, constructor, overloads, return type, deprecation, and since?” | When code fails to compile, or you need to implement a custom interface or pick an overload | Javadoc code fragments may use older APIs; read both §@Deprecated§ and §forRemoval§ |
| **Official samples/tests** | “How do you wire beans, configuration, and complete tests together in a project?” | When applying everything end-to-end from POM to MockMvc/WebTestClient | The §main§ branch changes continuously; check the tag/commit and build files |
| **Spring Boot documentation** | “Which starter, auto-configuration, BOM, properties, and dependency versions apply?” | When using §spring-boot-starter-security§ or test/Actuator | Boot's version does not equal Security's version |
| **Release notes + migration guide** | “What was added, deprecated, changed in defaults, or removed?” | Before upgrading minor/major versions and when old snippets report deprecation | Read guides for both source and target versions; not just the changelog |
| **Issues/Stack Overflow/blogs** | “Has anyone hit a similar issue?” | Generating hypotheses or viewing workarounds | Not an authoritative API spec; post date, version, and environment may differ |

**How to use them effectively:** Reference gives **meaning**, Javadoc gives the **exact Java contract**, samples show **how the parts fit together**, and tests/CI provide **evidence that it runs with the project's dependencies**. No single source replaces the entire workflow.

### 2.1 Guiding Starting Pages

- Current landing page: https://docs.spring.io/spring-security/reference/
- **Spring Security 6.5** Reference: https://docs.spring.io/spring-security/reference/6.5/
- **Spring Security 7.0** Reference: https://docs.spring.io/spring-security/reference/7.0/
- Boot 3.3 — Spring Security: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
- Getting Spring Security (Boot/starter/BOM): https://docs.spring.io/spring-security/reference/6.5/getting-spring-security.html
- Migration 6.5 → 7: https://docs.spring.io/spring-security/reference/migration/
- Spring Security Javadoc **6.3.4**, class §HttpSecurity§: https://docs.spring.io/spring-security/site/docs/6.3.4/api/org/springframework/security/config/annotation/web/builders/HttpSecurity.html
- Spring Security Javadoc **6.3.4**, interface §SecurityFilterChain§: https://docs.spring.io/spring-security/site/docs/6.3.4/api/org/springframework/security/web/SecurityFilterChain.html

**Do not guess and fabricate versioned URLs.** Not every older Reference path still retains a versioned URL structure like newer pages. If a §/reference/6.3/...§ link does not exist, use the exact 6.3.4 Javadoc, release notes, and archived reference/zip releases published by the vendor; cross-reference with existing 6.x sources while **explicitly noting when a snippet needs re-verification**.

## 3. Determining the Actual Version with Maven

### 3.1 From Parent/BOM to Resolved Artifacts

In a Maven project, first read the project's dependency configuration:

§§§bash
mvn -version
mvn help:effective-pom
§§§

§mvn -version§ shows the Maven and JDK in use, **not** the Spring Security dependency. §help:effective-pom§ shows the merged result of parent, profiles, and dependency management; the output can be very long, so there is no need to send the whole file to others.

To list the Spring Security modules actually selected:

§§§bash
mvn dependency:tree -Dincludes=org.springframework.security
§§§

In a real project, you might see artifacts like:

§§§text
org.springframework.security:spring-security-config:jar:6.3.4:compile
org.springframework.security:spring-security-web:jar:6.3.4:compile
org.springframework.security:spring-security-core:jar:6.3.4:compile
org.springframework.security:spring-security-test:jar:6.3.4:test
§§§

This is a **condensed example of output line format**, not the verbatim dependency tree from running the command on a real project. An actual dependency tree includes hierarchy symbols, other module counts, and non-Security artifacts.

**Reading the output module by module:** §spring-security-web§, §spring-security-config§, §spring-security-core§, and §spring-security-test§ should share the same compatible managed version set. If one module is at 6.3.x and another is at 6.5.x due to an override/transitive dependency, find the root cause before looking up Javadoc. Do not look only at §spring-boot-starter-security§: the starter's version is the Boot version, not the Security modules' version.

A targeted filter command when needed:

§§§bash
mvn dependency:tree -Dincludes=org.springframework.security:spring-security-web
mvn dependency:tree -Dincludes=org.springframework.security:spring-security-test
§§§

The §-Dincludes§ parameters filter which artifacts are displayed; plugins and shells may require specific quoting in some cases. When using a multi-module reactor, run against the actual application module or specify the module with §-pl§ and its required dependencies; do not look only at a parent POM that does not package the app.

### 3.2 Finding Intentional or Accidental Overrides

Check §pom.xml§ and the effective POM to see if there is:

§§§xml
<properties>
    <spring-security.version>6.3.4</spring-security.version>
</properties>
§§§

Or a directly pinned version:

§§§xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-core</artifactId>
    <version>6.3.4</version>
</dependency>
§§§

Both snippets are **configuration illustrations**, not an instruction to copy both. With Spring Boot, prefer letting the BOM manage Security unless there is a verified security/compatibility technical reason. Document the reason for any override; do not upgrade a single artifact alone while leaving the other modules on older versions.

When a conflict is detected, record: which module requests which version, which version gets selected, which BOM/profile decides it, and which tests verify the state after fixing. Maven §dependency:tree§ reflects the project's actual resolution, which is a much better basis than blog posts.

### 3.3 Inspecting Deployed Artifacts, Not Just Source Projects

If you already have a packaged Spring Boot JAR, you can inspect the library filenames inside the JAR:

§§§bash
jar tf target/my-app.jar | grep 'BOOT-INF/lib/spring-security'
§§§

This command is illustrative for a **Spring Boot executable JAR**, a Unix/Git Bash shell, and the exact build filename. In a fat JAR like this, you might see §BOOT-INF/lib/spring-security-web-6.3.4.jar§. If packaged as a WAR, native image, custom classloader, or container image, the paths and inspection methods differ. Runtime can also be affected by external classpaths and container environments; you must verify **the exact deployed artifact** when investigating production.

For Windows PowerShell:

§§§powershell
jar tf target\my-app.jar | Select-String "BOOT-INF/lib/spring-security"
§§§

If the JAR file does not exist yet, run a build first; do not infer the runtime version solely from expected artifact names.

## 4. Determining the Version with Gradle

Gradle typically uses the Spring Boot plugin and the dependency-management plugin or native Gradle platform/BOM support. The configuration can look like:

§§§groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
§§§

This is a **Groovy §build.gradle§ fragment**, not a complete Gradle project. In real environments, plugin versions may be supplied by a version catalog or §settings.gradle§. Do not guess the Spring Security version just because Gradle does not show a version number in the dependency declaration.

Recommended commands:

§§§bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-web --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-config --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-test --configuration testRuntimeClasspath
§§§

On Windows you can use §gradlew.bat§ instead of §./gradlew§. §dependencyInsight§ shows the version selection path, resolution/constraint reasons, or conflicts. Run it inside the **module that actually builds the application**, not only the root project in a multi-project build.

To look up docs for the right release, take the **resolved** version from §runtimeClasspath§/§testRuntimeClasspath§; a version shown in a version catalog that has not been selected is not proof. The test module should match the runtime security version.

## 5. Reading the Reference for the Right Stack and Use Case

Spring Security has two major web models:

| Servlet / MVC | Reactive / WebFlux | Do not mix |
| --- | --- | --- |
| §HttpSecurity§ | §ServerHttpSecurity§ | Different security configuration builders |
| §SecurityFilterChain§ | §SecurityWebFilterChain§ | Different bean types |
| §Filter§/§OncePerRequestFilter§ | §WebFilter§ | Servlet filter vs Reactor pipeline |
| §AuthenticationManager§ | §ReactiveAuthenticationManager§ | Synchronous methods vs §Mono<Authentication>§ |
| §UserDetailsService§ | §ReactiveUserDetailsService§ | Sync vs reactive user loading |
| §SecurityContextHolder§ | §ReactiveSecurityContextHolder§ | ThreadLocal vs Reactor Context |
| §MockMvc§ + §spring-security-test§ | §WebTestClient§ + reactive test tools | Different HTTP test environments |
| §AccessDeniedHandler§ | §ServerAccessDeniedHandler§ | Different handlers and return types |

**How to choose:** if the project uses §spring-boot-starter-web§ and a servlet web app, look under Reference → Servlet. If it only uses §spring-boot-starter-webflux§ to serve reactive endpoints, look under Reference → Reactive. Having §WebClient§ in a project **does not automatically turn an MVC server into WebFlux**; WebClient can also be used in Servlet apps.

Do not copy a §ServerHttpSecurity§ snippet from the reactive reference into a method accepting §HttpSecurity§ and tweak the return type to force compilation. Those are two different contracts.

### 5.1 Read by Specific Problem Instead of Searching Only “security”

For example, for the error “authenticated user gets 403 on §/admin§”:

1. Reference **Servlet → Authorization → Authorize HTTP Requests** to understand matchers and authorities.
2. Javadoc for §HttpSecurity#authorizeHttpRequests(Customizer)§ and §SecurityFilterChain§ of the resolved version.
3. Verify §hasRole("ADMIN")§ vs §hasAuthority("ROLE_ADMIN")§ according to the default role prefix.
4. Consult official test examples of the **same generation**.
5. Run negative tests: anonymous, user without sufficient privileges, user with the role.
6. If only POST gets 403, also check the **CSRF Reference** rather than concluding the role is wrong.

For example, for the error “OAuth2 callback differs from docs”, open the OAuth2 Client section, check the §spring-security-oauth2-client§ module in the dependency tree, and check the Javadoc of the converter/handler class being overridden. Do not replace a class with another class of the same name from a different package without knowing whether the interface changed.

## 6. Javadoc: Verifying an API Down to the Method Level

Reference explains **what you should do**; Javadoc answers **which exact methods you can call**.

Suppose you need to configure rules for a servlet app using 6.3.4. Open the corresponding Javadoc:

https://docs.spring.io/spring-security/site/docs/6.3.4/api/org/springframework/security/config/annotation/web/builders/HttpSecurity.html

In the §HttpSecurity§ class, look up §authorizeHttpRequests§. Javadoc 6.3.4 lists the overload taking §Customizer<...>§ and the **no-argument** overload marked deprecated/for removal in a future generation.

Recommended pattern suitable for 6.3.4:

§§§java
@Bean
SecurityFilterChain web(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/admin").hasRole("ADMIN")
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
§§§

This is a **fragment**: to compile, you need to import §@Bean§, §SecurityFilterChain§, §HttpSecurity§, and §Customizer§ inside a Spring configuration class; a complete project example is in section 8.

Older patterns you might find in Javadoc or a blog post:

§§§java
// Counter-example of the old DSL style: may be deprecated or removed in newer releases.
http.authorizeHttpRequests()
    .requestMatchers("/admin").hasRole("ADMIN")
    .and()
    .httpBasic();
§§§

Do not copy an old snippet just because it still appears on a Javadoc page. **Overload signatures**, the §Deprecated§ tag, the §Since§ field, §See Also§, and §forRemoval§ warnings matter more than whether the snippet looks familiar.

### 6.1 Sections You Must Read in Javadoc

1. **Exact package and import:** §org.springframework.security.config.annotation.web.builders.HttpSecurity§, not the reactive package.
2. **Class or interface:** can it be instantiated directly or is the bean created by Spring?
3. **Parameter types:** §Customizer<T>§, §Supplier<Authentication>§, §ServerWebExchange§, §HttpServletRequest§...
4. **Return type:** §SecurityFilterChain§, §AuthorizationDecision§, §Mono<Void>§...
5. **Checked exceptions:** for example, a method building the chain may declare §throws Exception§.
6. **Overloads:** older overloads may be deprecated while newer overloads require a lambda.
7. **Since/Deprecated/forRemoval:** evaluate support for both source and target versions.
8. **Semantics:** what does Javadoc say §null§, §empty§, exceptions, or defaults mean?
9. **Inheritance/interfaces:** sometimes a method is declared on a superinterface rather than on the class you are viewing.
10. **API artifact:** does the symbol belong to §spring-security-web§, §-config§, §-core§, or an additional OAuth2 module?

**Do not see “Since: 6.4” and try to use it on 6.3.4.** APIs added in a newer minor version do not automatically exist in an older patch. Conversely, an API present in 6.3.4 may be deprecated/removed in 7.x.

### 6.2 Reading Source Code When Javadoc Is Not Enough

If the contract is still unclear, proceed to the source code for the exact **release tag**, module tests, and migration notes. For internal APIs or behavior that depends on builder logic, reading the exact version's source code can clarify defaults or ordering. However, distinguish between:

- **Public API Javadoc**: the foundation of integration code.
- **Reference**: the recommended usage.
- **Internal implementation/tests**: helpful for understanding, but subject to change without backward compatibility guarantees.

Do not treat an internal implementation as a public extension point just because it is a §public class§; check the Javadoc, configuration paths, and support policy.

## 7. Finding and Evaluating Version-Matched Sample Code

A common path is going from the **Reference** to official sample code or the §spring-security-samples§ repository. When using GitHub, do not simply open the §main§ branch and paste code:

1. Identify the **official** repository and sample path from the reference page of the matching release.
2. Check the specific tag/commit; the sample repository may evolve alongside the latest Spring Security.
3. Read the **sample's** §settings.gradle§, §build.gradle§, §pom.xml§, or version catalog to determine its actual dependencies.
4. Determine whether the sample is **Servlet or reactive**, **HTTP Basic, form login, OAuth2 client, or resource server**.
5. Check the Java/Jakarta version; Spring Security 6 uses §jakarta.servlet§, not old §javax.servlet§ snippets from Servlet 5.x and earlier.
6. Check whether the sample configures demo values such as §{noop}§, hardcoded users/passwords, disabled CSRF, or assumed TLS.
7. Inspect the accompanying tests, especially negative paths; do not learn only from a happy-path controller.
8. If the sample is for a different version, treat it as an **idea**, cross-check the Javadoc, and compile it against your project before using it.

Example format for recording source provenance alongside learned code:

§§§text
Source type: Official Spring Security sample / Reference
Source version: checked release/tag/commit (record concrete ID)
Project: Spring Boot 3.3.5; Spring Security resolved 6.3.4
Web stack: Servlet / Spring MVC
Feature: authorizeHttpRequests + HTTP Basic + CSRF defaults
API checked: HttpSecurity#authorizeHttpRequests(Customizer)
Verification: mvn test + HTTP 200/401/403 assertions
Known limitations: demo-only in-memory user, local password
§§§

The goal is **technical traceability**, not filling in fields just for the sake of it. If the repo or tag cannot be confirmed, write “unverified” instead of making up a commit ID.

### 7.1 Rules for Selecting Examples

Prioritize in order:

- Official sample/test of the same major/minor version and stack.
- Official sample from a different patch whose Javadoc and behavior have been verified.
- Reference from another minor within the same major, after checking that the method exists and behavior is compatible.
- Community sample whose dependencies and negative tests have been verified.
- Unversioned blog/snippet: **for conceptual reference only**, never use as production code without verification.

A snippet from a “Spring Security 5 + WebSecurityConfigurerAdapter” blog post will very likely differ from Spring Security 6 configuration. Never use any copy just because the IDE can auto-import it.

## 8. Spring Boot 3.3.5 Project: Coding and Testing with Javadoc-Verified APIs

The example below uses a **fixed-version** baseline so learners can run it themselves: Boot §3.3.5§ manages Spring Security §6.3.4§ under the default BOM, provided there is no override. The code uses §SecurityFilterChain§, §HttpSecurity#authorizeHttpRequests(Customizer)§, §Customizer.withDefaults()§, and MockMvc tests. **Do not manually pin §spring-security-web§/§-config§/§-test§**, so the BOM manages all modules consistently.

### 8.1 Structure

§§§text
version-aware-security/
├── pom.xml
└── src/
    ├── main/java/com/example/versiondocs/
    │   └── VersionAwareSecurityApplication.java
    └── test/java/com/example/versiondocs/
        └── VersionAwareSecurityApplicationTest.java
§§§

### 8.2 pom.xml

§§§xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>version-aware-security</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
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
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
§§§

### 8.3 Complete Java Application

Create §src/main/java/com/example/versiondocs/VersionAwareSecurityApplication.java§:

§§§java
package com.example.versiondocs;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class VersionAwareSecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(VersionAwareSecurityApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-demo-123"))
            .roles("READER")
            .build();
        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-demo-456"))
            .roles("ADMIN")
            .build();
        return new InMemoryUserDetailsManager(reader, admin);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable)
            .build();
    }

    @RestController
    static class Api {
        @GetMapping("/public")
        String publicPage() {
            return "public ok";
        }

        @GetMapping("/me")
        String currentUser(Authentication authentication) {
            return "hello " + authentication.getName();
        }

        @GetMapping("/admin")
        String admin() {
            return "admin ok";
        }

        @PostMapping("/notes")
        String postNote() {
            return "note saved";
        }
    }
}
§§§

**Explanation based on looked-up APIs:**

- §@Bean SecurityFilterChain§ replaces subclassing §WebSecurityConfigurerAdapter§ from older examples; §http.build()§ finishes the configuration.
- §authorizeHttpRequests(auth -> ...)§ is the overload accepting §Customizer§, present in Javadoc 6.3.4; do not use the no-argument variant marked deprecated.
- §requestMatchers§ are ordered: §/public§ is open, §/admin§ requires the role, and every other request must be authenticated.
- §hasRole("ADMIN")§ checks §ROLE_ADMIN§ under the default role prefix; when using §hasAuthority§ you must pass the exact authority string.
- §httpBasic(Customizer.withDefaults())§ provides real authentication for the demo; §formLogin(...disable)§ returns 401 instead of redirecting to a login page in these cases.
- CSRF remains **enabled** by default. §POST /notes§ without a token typically returns 403 even with the right password; tests need §csrf()§.
- §UserDetailsService§ and BCrypt use two demo users, not a production account store. Never write real passwords or tokens to logs.

### 8.4 JUnit 5/MockMvc Tests to Verify Behavior for the Right API Generation

Create §src/test/java/com/example/versiondocs/VersionAwareSecurityApplicationTest.java§:

§§§java
package com.example.versiondocs;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class VersionAwareSecurityApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointIsOpen() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public ok"));
    }

    @Test
    void anonymousUserCannotReadMe() throws Exception {
        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongCredentialIsRejected() throws Exception {
        mvc.perform(get("/me")
                .with(httpBasic("reader", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void realBasicAuthenticationReturnsPrincipalName() throws Exception {
        mvc.perform(get("/me")
                .with(httpBasic("reader", "reader-demo-123")))
            .andExpect(status().isOk())
            .andExpect(content().string("hello reader"));
    }

    @Test
    void readerCannotEnterAdminPage() throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("reader", "reader-demo-123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanEnterAdminPage() throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("admin", "admin-demo-456")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin ok"));
    }

    @Test
    void missingCsrfStillBlocksPost() throws Exception {
        mvc.perform(post("/notes")
                .with(httpBasic("reader", "reader-demo-123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void validCsrfAndCredentialAllowPost() throws Exception {
        mvc.perform(post("/notes")
                .with(httpBasic("reader", "reader-demo-123"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("note saved"));
    }
}
§§§

**Eight tests** verify 200/401/403, valid/invalid credentials, and valid/missing CSRF. The tests perform Basic authentication through the demo's real filter/provider rather than using §@WithMockUser§ to bypass password verification.

### 8.5 Steps to Run and Verify the Version Before Running Tests

Requires Java 17+ and Maven. From the directory containing §pom.xml§:

§§§bash
mvn -version
mvn dependency:tree -Dincludes=org.springframework.security
mvn test
mvn spring-boot:run
§§§

Open another terminal:

§§§bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u reader:reader-demo-123 http://localhost:8080/me
curl -i -u reader:reader-demo-123 http://localhost:8080/admin
curl -i -u admin:admin-demo-456 http://localhost:8080/admin
§§§

| Request | Expected status | Stable body |
| --- | --- | --- |
| GET §/public§ anonymous | 200 | §public ok§ |
| GET §/me§ anonymous | 401 | Basic challenge |
| GET §/me§ with reader and valid password | 200 | §hello reader§ |
| GET §/admin§ with reader | 403 | Controller not invoked |
| GET §/admin§ with admin | 200 | §admin ok§ |

These are **expected results based on the example code**, not a claim that Maven was already run on the learner's machine. When tests fail to compile, go back to §dependency:tree§ and that version's Javadoc—do not “fix” it by copying 7.x code into a 3.3.x POM.

## 9. Distinguishing Wrong-Version Documentation Errors from Real Logic Errors

| Symptom | Cause to check | How to look it up |
| --- | --- | --- |
| §Cannot resolve symbol SecurityFilterChain§ | Missing module/config/dependency or wrong import | Is §spring-security-web§ in the tree? Is the Javadoc package right? |
| §Cannot resolve method ...§ | API is newer than the resolved version; different overload | Javadoc for the exact patch → Method Summary → Since |
| A method is deprecated | Old code still exists but will be removed | Javadoc §Deprecated§, migration guide, replacement overload |
| §javax.servlet§ not found | Snippet from Spring Security 5/old Java EE | Spring Security 6 is based on §jakarta.servlet§ |
| Class §HttpSecurity§ cannot be used in WebFlux | Mixing Servlet and reactive | Reactive Reference and §ServerHttpSecurity§ |
| §NoClassDefFoundError§ at runtime | Mixing Security/framework module versions | Runtime dependency tree and packaged JAR |
| Test compiles but auth does not run | Test lacks Spring Security integration/filter | §@AutoConfigureMockMvc§ / §springSecurity()§ |
| CSRF 403 on POST despite valid user | CSRF is still enabled by default | CSRF Reference and test §with(csrf())§ |
| §@WithMockUser§ returns 200 while real password is wrong | Mock bypasses authentication provider | Test real §httpBasic§/JWT |
| §hasRole("ADMIN")§ returns 403 despite having §ADMIN§ | Authority needs §ROLE_ADMIN§ per prefix | Reference + role/authority Javadoc |
| 6.3 code compiles but fails to compile on 7.x | Deprecated API was removed or types changed | Migration 6.5 → 7, Javadoc 7.x |
| 7.x code compiles but behaves differently | Defaults/contract/schema/stack changed | Release notes + regression tests |

**Do not conclude an error is version-related without checking:** 401/403 can also come from password, session, wrong role, CSRF, CORS, tenant, token issuer, or filter order. Versioned docs help determine *what contract can be used*, while tests determine *how the actual configuration behaves at runtime*.

### 9.1 How to Check an API's Actual “Since” Version

Suppose an online post uses a method §foo(Bar)§ that the compiler reports does not exist. Process:

1. Identify the **fully qualified class** containing the method; do not search generically by §foo§.
2. Get the resolved version of the **artifact containing the class**, e.g., §spring-security-config:6.3.4§.
3. Open the 6.3.4 Javadoc for that class and look for the §foo(Bar)§ overload.
4. If it is **absent**, compare the Javadoc of the release that has the method and check its “Since” note to see when it appeared.
5. If the method exists but the parameter type differs, check generic types/imports/dependencies; IDE auto-import might have picked the wrong §Authentication§/§RequestMatcher§.
6. If the method is deprecated or marked for removal, read the replacement guidance **for the right major version**.
7. Choose a solution that compiles against the real baseline; write tests after each step instead of changing dependencies wholesale just to make one snippet work.

### 9.2 Common Pitfalls Between Spring Security 6.3 and 7.x

In the §HttpSecurity§ 6.3.4 Javadoc, lambda-style overloads like §authorizeHttpRequests(Customizer)§ are the right choice; the no-argument overload is marked for removal in 7.0. Therefore, an old blog snippet using §.authorizeHttpRequests().and()§ may compile with a warning in 6.3, but it should not be your starting point when aiming to upgrade to 7.

On the other hand, 7.x documentation may use APIs or modules that do not exist in 6.3. Do not apply Boot 4 bean structures, packages, and Gradle dependencies to Boot 3.3 just because the feature name is the same. For a major upgrade, use 6.5 as a preparatory step following the Spring Security migration guide, then upgrade Boot/framework/security as **one compatible combination**.

## 10. Distinguishing Dependency Version, Javadoc Version, and Runtime Version

In a “code following docs does not run” ticket, state three facts clearly:

1. **Build resolution:** which Spring Security modules and versions §mvn dependency:tree§/Gradle §dependencyInsight§ selects.
2. **Runtime artifact:** which libraries the running JAR/WAR/container image actually contains (if not a native image), and whether it differs from the source/CI build.
3. **Docs consulted:** Reference URL, exact-patch Javadoc URL, sample tag/commit, and date accessed.

Example of a good investigation note:

§§§text
Project: api-service
Build: Maven, Java 17, Spring Boot 3.3.5 parent
Resolved: spring-security-core/config/web/test 6.3.4
Runtime: executable JAR verified containing spring-security-web-6.3.4.jar
Stack: Servlet / Spring MVC
Symptom: authorization DSL found in online sample does not compile
Reference: Spring Security 6.x Servlet authorization
Javadoc: HttpSecurity 6.3.4, overload authorizeHttpRequests(Customizer)
Change: replace no-arg deprecated DSL with lambda overload
Evidence: mvn test, anonymous 401 / reader 403 / admin 200
§§§

This is a **simulated record illustrating the process**, not a user's real build state. For production, the source of truth is the actually deployed artifact; a POM on the main branch might not match the running image.

### 10.1 Version Drift Between Dev, CI, and Production

Common causes:

- CI uses a different JDK than local, or builds with a different Maven profile.
- Dependency conflicts from added libraries alter the classpath.
- The production image has not been deployed after merging.
- Artifact caches or container registries point to a mutable image tag.
- The Spring Boot BOM is overridden by another dependency management configuration.
- Tests use a §spring-security-test§ version different from runtime Security; errors only surface when tests run.
- Multi-module apps share a common security config while the web module has different dependency management.

**Countermeasures:** lock/test versions via dependency management processes, use immutable image digests, generate SBOMs when appropriate, and save §dependency:tree§/§dependencyInsight§ in CI artifacts during investigations. Never hardcode mismatched versions for §security-core§/§-web§/§-config§ as a quick fix.

## 11. Reading the Migration Guide Before Upgrading Versions

### 11.1 How Patch, Minor, and Major Differ

Spring Security uses MAJOR.MINOR.PATCH. A patch typically fixes bugs/security issues; a minor release may add APIs; a major release can change or remove APIs. The safe rule is to **read the changelog and run regression tests for every upgrade**, especially for security-sensitive behavior.

For a Boot 3.3.5 + Security 6.3.4 project, upgrading directly to Boot 4/Security 7 is not just editing a version string. You must review:

- Java baseline, Spring Framework, and Jakarta Servlet API.
- Removed APIs, changed DSLs, deprecated annotations, and config classes.
- Security filter order, request matchers, and authorization behavior.
- OAuth2/OIDC/JWT decoders, sessions, CSRF, CORS, headers, and method security.
- Test frameworks and Boot auto-configuration (especially with test slices).
- JSON/Jackson schemas when using OAuth/serialization and converters.
- Rollback/rollout with existing active clients/sessions.

Official migration documentation recommends using **Spring Security 6.5 to prepare for 7.0**, then upgrading Boot/Security along compatible releases. This does not mean **arbitrarily upgrading Spring Security alone to 6.5 on any Boot 3.3 project**: you still need BOM/framework compatibility and testing.

### 11.2 Testing Matrix When Upgrading Versions

| Area | Minimum test cases |
| --- | --- |
| Authentication | Valid/invalid credentials, disabled/locked, MFA/OIDC if applicable |
| Authorization | Anonymous, insufficient privileges, sufficient privileges, method security, tenant |
| CSRF | POST with missing/invalid/valid token; cookie/session |
| CORS | Valid preflight, invalid origin/method/header, credentialed response |
| Headers | HSTS HTTPS, CSP/frame policy, cache-control, nosniff |
| OAuth2/JWT | Invalid signature/issuer/audience/expiry, revoked/rotated key |
| Error handling | 401, 403, 5xx dependency outage; no secret leakage |
| Servlet/Reactive | Correct filter/web chain, context propagation |
| Testing APIs | Synchronized §spring-security-test§ version, MockMvc/WebTestClient |
| Observability | Logs/audits/metrics and privacy after upgrade |
| Runtime | Java, servlet container, Actuator exposure, proxy/gateway |

**Goal:** ensure “the same intended behavior” when moving to the new version, not necessarily ensuring every internal error body/header matches byte-for-byte if the framework changed. Focus on verifying the security contract defined in the app.

## 12. How to Keep Learning a New API Without Getting Overwhelmed

When encountering a new name such as §AuthorizationManager§, follow a six-step sequence:

1. **Describe the requirement in one sentence:** “I want to block every account without the ADMIN role at §GET /admin§”.
2. **Identify stack/module/version:** Servlet/Security §6.3.4§/§spring-security-config§ + §spring-security-web§.
3. **Open the exact Reference section:** Servlet → Authorization → Authorize HTTP Requests.
4. **Check Javadoc:** §HttpSecurity#authorizeHttpRequests(Customizer)§, §AuthorizationManager§, and related types of the resolved version.
5. **Review a sample + run a minimal setup:** one §SecurityFilterChain§ bean, one controller, and 401/403/200 tests.
6. **Explain it in your own words:** explain matcher precedence, role prefixes, CSRF, and what the code does not prove; save the docs URL/version in your study notes.

Once you understand one use case, expand to method security, OAuth2 resource server, multi-chain, or WebFlux. Do not learn 6.3 Servlet + 7.x reactive + 5.8 §WebSecurityConfigurerAdapter§ simultaneously when solving a current error.

## 13. Checklist for Reviewing a Snippet Before Adding It to an Application

| Question | Required evidence |
| --- | --- |
| Do you know the resolved version? | Maven dependency tree or Gradle dependencyInsight |
| Have you verified the runtime artifact? | Packaged JAR/WAR/image or actual running classpath |
| Does it match the web stack? | Servlet vs WebFlux from starters and application type |
| Are the right modules present? | §spring-security-config/web/core/test/oauth2-*§ on classpath |
| Is the Reference for the right release? | URL/version or note when using 6.5 to cross-check 6.3 |
| Is the Javadoc for the right patch? | Method Summary, overloads, return type, Since/Deprecated |
| Does the sample have a tag/commit? | Clear build file and branch/tag |
| Is there dangerous demo code? | §{noop}§, hardcoded passwords, disabled CSRF/headers, wildcard CORS |
| Does it compile? | §mvn test§ or Gradle §test§ succeeds |
| Are deny cases tested? | Anonymous and missing-role/invalid-credential requests are blocked |
| Does runtime behavior match? | 200/401/403, CSRF, and headers match configuration |
| Were migration notes checked? | Especially when changing major/minor versions |
| Is provenance recorded? | Doc URL, module, version, commit/test evidence |

A snippet with a **valid API** does not necessarily enforce a **correct security policy**. For example, §permitAll()§ compiles in many releases, yet placing it on §/admin/**§ exposes the resource. You must examine the Java contract, the use case, and security test results together.

## 14. Common Documentation Research Mistakes

1. **Googling lands on the latest page while the app runs an older release.** Verify the version and pin Javadoc/reference right from the start.
2. **Reading the Spring Boot version as the Spring Security version.** Boot §3.3.5§ does not have Security §3.3.5§; the default BOM manages §6.3.4§.
3. **Reading Javadoc snippets without checking deprecation.** Prefer the new overload recommended for the release you are using.
4. **Copying code from §main§ without checking build files.** Samples may have moved to Boot 4/Security 7.
5. **Mixing §HttpSecurity§ with §ServerHttpSecurity§.** Servlet and reactive are two different contracts.
6. **Mixing §javax.servlet§ with §jakarta.servlet§.** This commonly happens when using snippets from before Spring Security 6.
7. **Adding only starter-security while forgetting test/OAuth2 modules.** When you need §spring-security-test§ or jose/resource-server, verify the corresponding dependencies.
8. **Upgrading §security-web§ alone to get a new API.** Incompatible modules can cause runtime errors.
9. **Trusting IDE auto-imports blindly.** Check the fully qualified class and exact-version Javadoc.
10. **Testing only 200, not 401/403.** Code can compile while leaving endpoints open.
11. **Not checking CSRF.** POST with a valid user but missing token usually gets 403 due to default protection.
12. **Assuming §@WithMockUser§ tests passwords.** It creates a mock SecurityContext and does not verify real HTTP Basic/JWT authentication.
13. **Not reading the migration guide.** API deprecations and defaults can differ when upgrading majors.
14. **Relying only on source on the main branch.** Runtime may be running a different artifact.
15. **Saving doc links without noting the version.** Months later, someone else may open completely different content.
16. **Ignoring security advisories.** When choosing a patch or older platform, evaluate support status and security updates per vendor guidance instead of using historical examples as new deployment configurations.

## 15. Conclusion

- **The “right” version is the resolved dependency and running artifact**, not a version number guessed from a starter or a blog post title.
- **Reference explains mechanisms; Javadoc verifies the API contract; samples/tests prove how to apply them.** Each source plays a distinct role.
- For the Boot §3.3.5§ example, the default set manages Security §6.3.4§; pin the §6.3.4§ Javadoc and cross-check 6.x Reference docs. For Boot 4/Security 7, you must pick the new docs and migration guides.
- **Check overloads, packages, return types, deprecations, and Since** before copying code.
- **Positive/negative test suites** are the final requirement: the compiler accepting an API does not mean authorization/CSRF/authentication is secure.
- Record **documentation URLs, versions, sample tags/commits, and test results** in notes or PRs so the next person can reproduce your research.

## Official Documentation and Verification Sources

1. Current Spring Security Reference: https://docs.spring.io/spring-security/reference/
2. Spring Security 6.5 Reference: https://docs.spring.io/spring-security/reference/6.5/
3. Spring Security 7.0 Reference: https://docs.spring.io/spring-security/reference/7.0/
4. Spring Security Reference — Getting Spring Security, BOM: https://docs.spring.io/spring-security/reference/6.5/getting-spring-security.html
5. Spring Security 6.3.4 Javadoc — HttpSecurity: https://docs.spring.io/spring-security/site/docs/6.3.4/api/org/springframework/security/config/annotation/web/builders/HttpSecurity.html
6. Spring Security 6.3.4 Javadoc — SecurityFilterChain: https://docs.spring.io/spring-security/site/docs/6.3.4/api/org/springframework/security/web/SecurityFilterChain.html
7. Spring Security 6.5 — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
8. Spring Security — Migration to 7: https://docs.spring.io/spring-security/reference/migration/
9. Spring Boot 3.3 — Security Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
10. Maven Central — Spring Boot Starter OAuth2 Client 3.3.5, resolved Security 6.3.4: https://central.sonatype.com/artifact/org.springframework.boot/spring-boot-starter-oauth2-client/3.3.5
11. Maven Repository — Spring Boot 3.3.5 managed dependencies (Security BOM 6.3.4): https://mvnrepository.com/artifact/org.springframework.boot/spring-boot-parent/3.3.5/dependencies
12. Spring Security Test Reference: https://docs.spring.io/spring-security/reference/6.5/servlet/test/index.html