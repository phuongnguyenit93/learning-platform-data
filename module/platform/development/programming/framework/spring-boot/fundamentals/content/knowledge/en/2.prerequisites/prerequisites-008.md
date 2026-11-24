# Reading Documentation for the Right Spring Boot Line and Spring Framework Version

While learning and developing Spring Boot applications, an easy mistake to make is **following a guide written for a different version than the one your project actually runs**. For instance, you might read an article using `javax.servlet.*` while your project's source only accepts `jakarta.servlet.*`; or see security configuration examples using `WebSecurityConfigurerAdapter` when that class no longer exists in the Spring Security release line your project uses. Sometimes copied code even compiles, yet default behaviors or configuration styles have changed.

To read documentation accurately, answer three questions in order:

1. **Which Spring Boot release line and patch version is the application using?**
2. **Which versions of Spring Framework and related Spring libraries are actually resolved?**
3. **Are the documentation page, API examples, and migration guides addressing that exact release line?**

This lesson presents how to identify versions, pick the right official documentation, verify resolved dependencies, spot outdated tutorials, and build a lookup workflow applicable to both Gradle and Maven projects.

## 1. First, Distinguish Spring Boot from Spring Framework

**Spring Framework** provides the core foundation of the Spring ecosystem: the IoC container, Dependency Injection, bean lifecycle, transactions, Spring MVC, Spring WebFlux, and many other APIs. **Spring Boot** builds on top of Spring Framework, providing application startup, starter dependencies, auto-configuration, dependency management, and operational tooling.

They have **independent version numbers**. Spring Boot version `3.3.5` does not mean the application runs Spring Framework `3.3.5`. For example, the **Spring Boot 3.3.x line** is built on the **Spring Framework 6.1.x line**; the exact Framework patch version depends on the Boot/BOM version and dependency resolution in the project.

~~~text
Application
  │
  ├── Spring Boot 3.3.x            ← Boot line used to pick Boot docs
  │     ├── spring-boot-autoconfigure
  │     ├── spring-boot-starter-*
  │     └── Spring Boot dependency management
  │
  ├── Spring Framework 6.1.x       ← Framework line used to pick API docs
  │     ├── spring-core / spring-context
  │     ├── spring-web / spring-webmvc
  │     └── spring-tx / ...
  │
  ├── Spring Data ...              ← separate release train, typically managed by Boot
  └── Spring Security ...          ← separate release train, typically managed by Boot
~~~

This diagram is an **example of version relationships**, not an exact patch lookup table. Spring Boot also manages many non-Spring libraries such as Jackson, Hibernate, Logback, and database drivers. You cannot deduce all component versions merely from Boot's numbering scheme.

### 1.1. What Is a Release Line?

Given a version number of the form `MAJOR.MINOR.PATCH`:

| Part | Example in `3.3.5` | Meaning When Looking Up Docs |
|---|---|---|
| Major | `3` | Can bring platform changes, Java requirements, and breaking API changes. |
| Minor | Second `3` | Identifies the feature line, configuration model, and bundled framework versions. |
| Patch | `5` | Primarily bug fixes and compatibility improvements; may still include behavior changes noted in release notes. |

In practice, identify **both the full version** in use (`3.3.5`) and the corresponding **documentation line** (`3.3.x`). If you are looking for an API or bug fix introduced in a specific patch, also check the documentation or changelog for that exact patch rather than only reading the general 3.3 overview.

Labels such as `SNAPSHOT`, `M1`, `RC1`, or final releases also matter: documentation for snapshot/milestone/release candidate builds may describe unstable APIs. Do not apply guidance from pre-release docs to a stable release without verifying.

### 1.2. Boot Manages Versions, but Not Every Project Is Identical

Spring Boot publishes the **`spring-boot-dependencies` BOM** (Bill of Materials) to specify a coordinated set of library versions for a given Boot release. Projects typically use this BOM directly or indirectly via plugins or a parent POM.

However, effective versions can differ from the default BOM if:

- The project explicitly declares its own version for a dependency.
- Another BOM or dependency platform participates in version resolution.
- Gradle/Maven applies version rules, constraints, forced versions, resolution strategies, or organizational overrides.
- Modules in a multi-module build have custom dependency configurations.

Therefore, distinguish the **expected version from the Spring Boot BOM** from the **actual version present in the dependency graph**. The latter determines which APIs the compiler and runtime actually see.

## 2. Picking the Right Category of Documentation

A single Spring question can span several different documentation sources:

| What You Need to Know | Primary Source | What Must Match |
|---|---|---|
| Which beans Boot auto-creates, which config properties exist, how starters behave | **Spring Boot Reference Documentation** | The application's Spring Boot release line |
| How `ApplicationContext`, `@Transactional`, Spring MVC, or WebFlux work | **Spring Framework Reference Documentation** | The resolved Spring Framework line |
| Signatures, overloads, annotations, deprecation status of a class/method | **Javadoc API** of that artifact | The exact API version, ideally the same patch |
| How Spring Data JPA/JDBC/R2DBC repositories behave | **Spring Data module reference** | The actual module and release train/version |
| `SecurityFilterChain`, OAuth2, request authorization, or reactive security | **Spring Security reference** | The actual Spring Security line |
| Breaking changes, new config, or altered behavior after an upgrade | **Release Notes / Migration Guide / Upgrade Notes** | The source → target version pair |
| Which transitive version was pulled into the project | **Dependency report / effective build configuration** | The running artifact and configuration |
| Which release fixed a specific bug | **Issues, changelogs, release notes** linked to releases | The fixed version and reproduction conditions |

Some official entry points to start from:

- Spring Boot: https://docs.spring.io/spring-boot/reference/
- Spring Framework: https://docs.spring.io/spring-framework/reference/
- Spring Security: https://docs.spring.io/spring-security/reference/
- Spring Data: https://spring.io/projects/spring-data
- Project catalog and documentation branches: https://spring.io/projects

**Note:** Root `/reference/` URLs generally point to the default published release at the time of access. If your project uses an older line, use the **Versions** switcher on the documentation page or branch-specific links. Do not assume the latest content is correct for your current app simply because it ranks first in search results.

Official documentation URL structures occasionally change across major releases. Verify the **version header displayed on the page itself** instead of guessing versions by manually constructing URLs. In particular, Javadoc links and archive paths may differ from reference documentation paths.

## 3. Identifying the Spring Boot Version Used in a Project

### 3.1. Gradle Projects: Check Plugin Versions and Dependency Setup

Example of a Spring Boot **3.3.5** application using Gradle Groovy DSL:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

In this example, `3.3.5` is the **Spring Boot plugin version**; when combined with the dependency-management plugin above, the corresponding BOM is applied to managed dependencies. `1.1.6` belongs to `io.spring.dependency-management`, **not Spring Framework**.

In real projects, the plugin version may live elsewhere, such as:

- `settings.gradle` / `settings.gradle.kts` via `pluginManagement`;
- `gradle/libs.versions.toml` via version catalogs and plugin aliases;
- `gradle.properties` or custom convention plugins;
- a BOM imported via `platform(...)` or `enforcedPlatform(...)`, not necessarily via the dependency-management plugin.

Thus, if `build.gradle` only says `alias(libs.plugins.spring.boot)`, inspect the alias definition to see the declared version. If a module declares dependencies without applying the Boot plugin, inspect that module's actual BOM/dependency management setup.

### 3.2. Maven Projects: Check the Parent or Imported BOM

A Maven application commonly inherits from Boot's parent:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
    <relativePath/>
</parent>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

When not using `spring-boot-starter-parent`, a project can import the BOM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.3.5</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

These two snippets illustrate **two different project setups**, not two blocks meant to appear together in the same POM. The parent also provides build/plugin defaults alongside dependency management; importing the BOM only brings in the BOM's dependency management rules.

### 3.3. Distinguishing Declared Versions from Effective Versions

Reading `pom.xml` or `build.gradle` shows **what the project intends to use**. Yet the **resolved dependency graph** reveals **which versions the compiler and runtime actually receive**. This matters especially in situations like:

~~~text
Application declares:
  Spring Boot plugin: 3.3.5

Another dependency or version management rule:
  requests spring-core at a custom version

What needs checking:
  which versions do spring-core, spring-context, spring-webmvc...
  actually resolve to?
~~~

Do not take the plugin version and guess a Spring Framework patch number. The Spring Boot BOM and resolved dependencies are concrete sources of truth.

## 4. Verifying Spring Framework via the Dependency Graph

In a Gradle project, you can run these commands **in your project development environment** to inspect actual dependencies. These commands are for reference; they do not need to be executed merely while reading this lesson:

~~~bash
# View overall runtime dependencies of the current module.
./gradlew dependencies --configuration runtimeClasspath

# Trace why the spring-core version was chosen.
./gradlew dependencyInsight \
  --dependency org.springframework:spring-core \
  --configuration runtimeClasspath

# Check a specific MVC artifact if the application uses MVC.
./gradlew dependencyInsight \
  --dependency org.springframework:spring-webmvc \
  --configuration runtimeClasspath
~~~

For a subproject in a multi-project build, specify the module's task path, e.g. `./gradlew :catalog-api:dependencyInsight --dependency spring-core --configuration runtimeClasspath`. On Windows, use `gradlew.bat` or the wrapper invocation appropriate for your terminal. Some modules use configurations other than `runtimeClasspath`; choose the configuration matching what you want to observe.

When using Maven, you can inspect:

~~~bash
# View the effective POM after parent/profile inheritance and interpolation.
./mvnw help:effective-pom

# Print dependencies belonging to Spring Framework.
./mvnw dependency:tree -Dincludes=org.springframework
~~~

Do not check only `spring-core`. To understand a feature, check the directly relevant artifacts:

| Feature | Artifacts to Watch |
|---|---|
| Container and beans | `spring-core`, `spring-beans`, `spring-context` |
| Spring MVC | `spring-web`, `spring-webmvc` |
| Spring WebFlux | `spring-web`, `spring-webflux` |
| Transactions | `spring-tx` |
| Spring Data JPA | `spring-data-jpa` plus the JPA provider |
| Spring Security | `spring-security-web`, `spring-security-config`, `spring-security-core` |

Most Spring Framework artifacts are typically managed consistently within one release line. If the dependency graph shows core modules drifting out of sync, investigate version management configuration before trusting docs or randomly patching an individual version.

In an IDE, you can also open **External Libraries / Maven Dependencies / Gradle Dependencies** to see the resolved JAR versions. This helps confirm which JAR an actual class comes from. If the IDE and command line show different versions, check build import/sync, profiles, Gradle settings, caches, and the active run classpath.

## 5. Picking the Right Documentation Page Once You Know the Versions

Suppose you have verified:

~~~text
Spring Boot           3.3.5
Spring Framework      6.1.x (verify exact patch via dependency graph)
Spring Data           version chosen by BOM/resolution
Spring Security       version chosen by BOM/resolution
~~~

Your lookup workflow should proceed as follows:

**Step 1 — Pick Boot docs matching the 3.3 line.** If you need `spring.mvc.*`, embedded server behavior, actuator, or auto-configuration, prioritize the **3.3** Spring Boot Reference. Do not default to whichever Boot version is currently marked "current".

**Step 2 — Pick Framework docs matching the 6.1 line.** When looking up `@Bean`, transactions, integrated validation, HTTP request mapping, or WebFlux, consult Spring Framework Reference/Javadoc **6.1**. For exact API signatures, prefer the Javadoc of the resolved Framework version.

**Step 3 — Pick subproject docs by their own versions.** If the question involves `SecurityFilterChain`, repository queries, or reactive database access, switch to Spring Security/Spring Data docs and match their version from the graph. Do not apply Boot's `3.3` version number to subprojects.

**Step 4 — Check release notes when discrepancies appear.** If an online guide mentions an API missing from your Javadoc, compare release notes or migration guides between the source and target lines. Also pay attention to `Since`, `Deprecated`, and `Removed APIs` notices in the docs.

**Step 5 — Verify against source and classpath.** Method signatures, annotations, dependencies, and imports must exist in the actual resolved version. You can use `Go to Declaration` in your IDE to confirm which artifact owns an API.

### A Useful Lookup Decision Tree

~~~text
Question about the application
   │
   ├─ What does Spring Boot configure?
   │      → Boot Reference for the matching Boot line
   │
   ├─ How does a Spring Framework API behave?
   │      → Framework Reference for the matching line
   │      → Javadoc of the resolved artifact
   │
   ├─ Security / Data / other library?
   │      → Reference for the exact project and version
   │
   └─ Why does an old example fail or an upgrade break?
          → Migration Guide / Release Notes
          → dependency graph and actual source
~~~

## 6. Recognizing Outdated Guides Through Common Examples

### 6.1. `javax.*` vs. `jakarta.*`

Spring Boot 3.x is built on Spring Framework 6.x and the newer Jakarta EE ecosystem, where many Jakarta EE APIs moved namespaces from `javax.*` to `jakarta.*`. For example:

~~~java
// Example from the older ecosystem, not usable verbatim in Boot 3.x:
import javax.servlet.http.HttpServletRequest;
import javax.persistence.Entity;
import javax.validation.constraints.NotNull;

// Corresponding APIs in a Boot 3.x environment:
import jakarta.servlet.http.HttpServletRequest;
import jakarta.persistence.Entity;
import jakarta.validation.constraints.NotNull;
~~~

Do not assume **every** `javax.*` package must change to `jakarta.*`. Java SE packages like `javax.crypto` or `javax.net.ssl` remain `javax.*`. Check whether an API belongs to **Jakarta EE** or **Java SE**, and verify the corresponding dependency. Changing imports is only part of migrating; servers, persistence providers, validation providers, and integrated libraries must also support the new version.

### 6.2. Configuring Spring Security Using the Right Line's API

Many older articles still extend `WebSecurityConfigurerAdapter`. That class was removed in Spring Security 6; such examples cannot be applied verbatim to a Boot 3.x project running Spring Security 6.

In newer API lines, Servlet Security configuration typically defines a `SecurityFilterChain` bean:

~~~java
@Configuration
class SecurityConfiguration {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated());
        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
~~~

This snippet illustrates **Servlet Security**; CSRF, sessions, OAuth2/JWT, user details, and path rules must fit the real application. If you use WebFlux, consult **reactive security** documentation with `SecurityWebFilterChain` and `ServerHttpSecurity`, rather than copying the Servlet chain. Reading the right version is not enough: you must also read for the **right web stack**.

### 6.3. Copying an Annotation from Docs When the Project Lacks the Starter

If documentation uses `@Entity`, `JpaRepository`, or `@Valid` and your project reports unresolved symbols, the cause is not necessarily a wrong Boot version. You may be missing the JPA/Validation dependency or the IDE may not have imported the project cleanly.

For example, `spring-boot-starter-web` does not automatically include **Spring Data JPA**, a database driver, and a Bean Validation provider. Before trying to "fix imports" using random online tips, verify which starters you have and which artifact provides that class. Use Spring Initializr or the starter dependencies page of your Boot line to look up the required dependency.

### 6.4. A Configuration Property Was Renamed or Removed

Examples from old blog posts may use `server.*`, `management.*`, or `spring.*` properties that were renamed, changed defaults, or removed. In that case:

1. Read **Common Application Properties** for the exact Boot line.
2. Check **configuration metadata** / IDE autocompletion if available.
3. Inspect release notes/migration guides between the two lines.
4. Confirm the corresponding auto-configuration is present and its activation conditions are met.

A property "having no effect" sometimes happens because the application never loaded the corresponding module or auto-configuration, not solely because the property was renamed.

## 7. Do Not Confuse Different Layers of "Right Version"

The phrase **right version** spans several layers:

| Layer | Example Question | How to Verify |
|---|---|---|
| **Declared Boot version** | Which Spring Boot plugin/parent does the build specify? | Build script, version catalog, POM |
| **BOM-managed version** | Which library version does Boot intend to select? | Corresponding `spring-boot-dependencies` BOM |
| **Resolved version** | Which version of `spring-webmvc` actually loads at runtime? | Dependency graph, IDE classpath |
| **JDK / Build Tool version** | Do current JDK, Gradle, and Maven satisfy the Boot line's requirements? | Release notes/system requirements, `java -version`, and wrapper |
| **Documentation version** | Which version are the Reference/Javadoc pages showing? | Version badge on the docs page |
| **Example source version** | Which stack and release was the sample written for? | Repo metadata, commit/tag, imports, dependency declarations |
| **Runtime environment version** | Which build is actually deployed? | Build metadata, deployment/image tag, and startup info |

The important order is: **declaration → management → dependency resolution → actual running code**. Discrepancies can arise at any layer if a build overrides versions, the runtime deploys an older artifact, or a different module gets packaged.

### 7.1. Java and Build Tools Must Also Be Compatible

Spring Boot documentation includes a **System Requirements** section for each release line. When upgrading or following a guide, check:

- **Minimum and supported Java versions** for that Boot line;
- **Supported Gradle/Maven versions** and the project wrapper version;
- **Servlet/Jakarta** requirements and whether the app runs on Tomcat, Jetty, or another runtime;
- baseline changes in Spring Framework and integrated libraries.

For example, Spring Boot 3.x requires **Java 17 or higher** as a baseline; other lines may have different system requirements. Do not apply JDK conclusions from one Boot branch across all Boot branches. When a project uses both toolchains and a JVM to run Gradle, distinguish the Java version used to **compile**, the version used to **run Gradle**, and the version used to **run the application**.

### 7.2. Even the Right Reference Can Mislead if Configuration Differs

An example in the Spring Boot Reference may assume you are using:

- Servlet MVC, whereas your application runs WebFlux;
- JPA, whereas your project uses JDBC, R2DBC, or MongoDB;
- an embedded web server, whereas your project packages a WAR;
- default auto-configuration, whereas your application already declared a custom bean;
- a standalone application, whereas you are working in a multi-module build.

Read the **applicability conditions** surrounding the example: annotations, required dependencies, web stack, created beans, and toggle properties. Do not match solely on a class name.

## 8. Reading Javadoc Without Overestimating What an API Supports

When you find a class in Spring Framework, inspect:

1. **Package and artifact**: is the class in `org.springframework.web.servlet.*`, `org.springframework.web.reactive.*`, or another package?
2. **Actual signatures**: constructors, parameters, return types, generics, and checked exceptions.
3. **`Since`**: from which version line did the class or method appear?
4. **`Deprecated`**: since when, and what replacement API do the docs recommend?
5. **Behavioral contract**: preconditions, nullability, callbacks, lifecycle, thread safety, execution timing.
6. **Related links**: interfaces/superclasses, implementations, and corresponding reference guide sections.

For example, if current Javadoc says a method was added **Since 6.2** yet your dependency graph has Spring Framework **6.1.x**, that method does not exist on your classpath even though the class name matches. Look for an API available in 6.1 or plan a coordinated upgrade across a compatible version set.

Likewise, an API marked **deprecated** is not necessarily deleted in the current version. Version-matched Javadoc helps distinguish "still present but advised to migrate" from "already removed".

## 9. When Upgrading: Read Docs for Both Old and New Versions

Suppose an application is moving from an older Spring Boot line to a newer line. Do not simply open the target version's reference docs and react to the first compiler errors. A better workflow:

1. **Record the current baseline**: Boot version, Framework version, Spring Security/Data, JDK, Gradle/Maven, web stack, and any dependency overrides.
2. **Read Upgrading/Release Notes/Migration Guides** of Boot for that transition; if crossing multiple minor/major lines, read the intermediate steps too.
3. **Check Framework and subproject changes** accordingly, especially security, persistence, and Spring Cloud if used.
4. **Bump versions together** via the appropriate BOM/parent/plugin before manually pinning individual Spring libraries.
5. **Look for breaking changes**: `javax`/`jakarta` packages, removed/deprecated APIs, property renames, auto-configuration conditions, changed defaults, and servlet/reactive behavior.
6. **Verify the dependency graph after upgrading** to ensure no older versions are pulled in unintentionally.
7. **Test application runtime behavior**: bean creation, HTTP mappings, security, transactions, persistence, serialization, startup, and integration tests.

In particular, **do not upgrade Spring Framework independently to another major line just to use one new API** while the rest of the system remains managed by an older Boot BOM, unless clear compatibility guidance exists and has been thoroughly evaluated. By default, letting Boot coordinate the libraries it manages is much safer.

### A Quick Self-Check Scenario

Your project declares:

~~~groovy
plugins {
    id 'org.springframework.boot' version '3.3.5'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

You open a search result stating "Spring Framework 6.2 has API X" and plan to call API X.

Verify step by step:

1. **Which Framework line does Boot 3.3.5 manage?** Do not guess from the word "Spring" in the framework name.
2. **Which version do `spring-webmvc` / `spring-core` resolve to?** Check the dependency graph.
3. **Does the Javadoc for the resolved version include API X?** If not, the search result describes a different version.
4. **Can the requirement be met with an already supported API?** If not, consider upgrading Boot following migration guides rather than forcing a single Framework artifact.

This check saves far more time than repeatedly tweaking imports or forcing dependency versions until the compiler stops complaining.

## 10. Practicing Lookup on a Common Error

**Scenario:** After reading an online tutorial, you write:

~~~java
import javax.servlet.http.HttpServletRequest;

@RestController
class TraceController {
    @GetMapping("/trace")
    String trace(HttpServletRequest request) {
        return request.getRequestURI();
    }
}
~~~

Your IDE reports that `javax.servlet.http.HttpServletRequest` cannot be found in a Spring Boot 3.x project.

**Version-aware investigation:**

1. Open the build file and confirm Boot 3.x and `spring-boot-starter-web` are present.
2. Check actual Spring Framework/Servlet dependencies and confirm the app uses Servlet MVC.
3. Consult Servlet/Jakarta documentation matching the Boot and Framework lines, instead of manually adding an old `javax.servlet` JAR just to make the import compile.
4. Switch to the Jakarta namespace import:

~~~java
import jakarta.servlet.http.HttpServletRequest;

@RestController
class TraceController {
    @GetMapping("/trace")
    String trace(HttpServletRequest request) {
        return request.getRequestURI();
    }
}
~~~

5. If errors persist, check the actual classpath and web stack: a WebFlux application uses different reactive request types, so replacing `javax` with `jakarta` does not turn a reactive design into MVC.

The takeaway is that **import errors can signal a version mismatch or web stack mismatch**, not necessarily a missing single dependency.

## 11. Version Note Template When Reading Documentation

Before applying an example, you can jot down a quick summary in your study notes or issue description:

~~~text
Topic under lookup: @Transactional + Spring Data JPA
Spring Boot: 3.3.5
Spring Framework: <resolved spring-tx/spring-core version>
Spring Data JPA: <resolved spring-data-jpa version>
JDK: <build/run Java version>
Build tool: Gradle or Maven <version>
Web stack: Spring MVC / WebFlux / no web
Documentation: <URL + displayed version label>
Related API: <package.class#method>
Notable changes: <release note/migration link if any>
~~~

A short version note like this clarifies which **release line** the answer came from, which **artifact** it applies to, and whether migration notes should be checked. When reporting bugs or asking questions, attaching the **relevant portion of the dependency graph** is far more helpful than merely saying "I'm using Spring Boot".

## 12. Rules to Remember

- **Spring Boot version and Spring Framework version are two different numbers.** The Spring Boot BOM determines the default library version set; the dependency graph confirms what was actually selected.
- **The "latest/current" page may not match your project.** Always check the version badge on reference docs, Javadoc, and examples.
- **Read documentation tailored to the question.** Boot for auto-configuration/starters; Framework for core/MVC/WebFlux/transactions; Data and Security per subproject version.
- **Release notes and migration guides are critical during upgrades.** An example working on a newer line may use APIs unavailable on an older line.
- **The right version must pair with the right stack.** MVC/Servlet examples cannot be copied verbatim to WebFlux; blocking JPA differs from reactive R2DBC.
- **Do not fix missing-API errors by randomly forcing library versions.** Diagnose from build setup, BOM, dependency graph, and compatibility first.

Whenever reading a Spring tutorial, build the habit of asking: **"Which Boot line was this article written for, which Framework version does it rely on, and do these APIs actually exist on my application's classpath?"** Answering those three questions forms the foundation for reading Spring Boot documentation accurately, learning effectively, and upgrading applications safely.
