# Managing Compatible Version Sets with the Spring Boot BOM

## 1. Why Does an Authentication Application Need to Manage the Entire Version Set?

A Spring Security project does not run only a single `spring-security-core` JAR. Logging in with forms, HTTP Basic, JWT, OAuth2 Login, LDAP, SAML, or sessions typically pulls in multiple Spring Security modules, Spring Framework, Jakarta Servlet, Jackson, logging libraries, test libraries, and Spring Boot starters.

If each dependency is declared with an independent version, the application may compile in one place yet fail during startup or authentication in another:

- `NoSuchMethodError`: a module was built against an API different from the runtime version.
- `ClassNotFoundException` or `NoClassDefFoundError`: a class does not exist in the loaded version.
- `NoSuchBeanDefinitionException`: configuration or auto-configuration changed, possibly due to version drift.
- `IllegalArgumentException` or `BeanCreationException` in the security filter chain due to mismatched dependencies.
- Unit tests pass while login integration tests fail because `spring-security-test` is from a different generation than the runtime modules.
- A developer copies a Spring Security 7 API (for example `@EnableMultiFactorAuthentication`) into a project using Spring Security 6.5, causing the IDE to fail to find the class.

**Spring Boot BOM** helps manage a **set of versions selected and tested together by Spring Boot**, reducing manual pinning of individual libraries. Learners need to understand:

1. What a BOM is and how it differs from a starter, parent, or plugin.
2. How Maven uses `spring-boot-starter-parent` or imports `spring-boot-dependencies`.
3. How Gradle uses the dependency management plugin or native `platform(...)`.
4. How to confirm that Spring Security core/web/config/test resolve as a compatible set.
5. Why a BOM does not eliminate the need to check compatibility, security patches, and migration.
6. How to detect version drift via `dependency:tree`, `dependencyInsight`, CI, and smoke tests.

This lesson illustrates with **Spring Boot 3.5.16 / Spring Security 6.5.11 / Spring Framework 6.2.19 / Java 17+** — versions published by the official Spring Boot 3.5.16 managed-dependencies page. This is a **fixed example set**, not a claim that they are always the latest versions. When creating a production project, review currently supported releases, new patches, and system requirements at deployment time.

## 2. What Is a BOM?

A **BOM** (Bill of Materials) in the Java/Maven ecosystem is typically a POM with `packaging=pom` and a `dependencyManagement` section specifying versions for many artifacts.

Coordinates of the Spring Boot BOM:

~~~text
groupId:    org.springframework.boot
artifactId: spring-boot-dependencies
version:    3.5.16
type:       pom
scope:      import  (when Maven imports it into dependencyManagement)
~~~

Visualize it as:

~~~text
              spring-boot-dependencies:3.5.16
                         |
       +-----------------+-----------------+
       |                 |                 |
spring-security-*     spring-*          other libraries
   6.5.11              6.2.19           (Jackson, Tomcat,
                                        logging, testing...)
       |                 |                 |
       +-----------------+-----------------+
                         |
              Application dependency graph
~~~

In the illustrative configuration, the BOM manages `spring-security-core`, `spring-security-web`, `spring-security-config`, `spring-security-test`, `spring-security-oauth2-client`, `spring-security-oauth2-resource-server`, and more along the Security 6.5.11 line.

**A BOM does not automatically add dependencies to the classpath.** It **selects versions when an artifact is declared or pulled in transitively**. For example, importing the BOM without adding `spring-boot-starter-security` **does not enable Spring Security**, does not create a login page, and does not configure authentication.

### 2.1. BOM, Starter, Parent, and Build Plugin Are Not the Same

| Component | Example | Responsibility |
| --- | --- | --- |
| **BOM** | `spring-boot-dependencies` | Manages dependency versions |
| **Starter** | `spring-boot-starter-security` | Declares a group of dependencies needed for a feature |
| **Maven Parent** | `spring-boot-starter-parent` | Inherits BOM, dependency management, plugin management, and build defaults |
| **Maven Plugin** | `spring-boot-maven-plugin` | Runs/packages the application; not a BOM itself |
| **Gradle Plugin** | `org.springframework.boot` | Provides Boot build tasks/integration; dependency management needs an appropriate mechanism |
| **Gradle platform** | `platform("org.springframework.boot:spring-boot-dependencies:...")` | Imports the BOM into resolution configuration |
| **Spring Security BOM** | `spring-security-bom` | Manages Security modules specifically, often used when not using Boot BOM or under a special strategy |

Setting `spring-security-core` and `spring-security-web` as two dependencies with the same version is not equivalent to a BOM managing the **entire graph**. A graph can also include Spring Framework, Reactor, Jackson, Spring Data, test engines, and the servlet container.

### 2.2. “Managed” Does Not Mean “Forcing All Versions”

Especially with Gradle native `platform(...)`, a BOM provides **version constraints**; the actual version can still be upgraded by another constraint or dependency graph. With Maven, an explicit `<version>` and local `dependencyManagement` can change the outcome. Therefore, always **inspect the resolved dependency tree**, not just read versions in the POM/BOM.

**Distinguish three places:**

~~~text
DECLARED VERSION        Value the developer writes in POM/build.gradle
MANAGED VERSION         Value provided by the BOM or dependency management
RESOLVED VERSION        Final JAR actually selected by the build tool
~~~

An application is considered to be “using Spring Security X” in execution terms when the **resolved runtime classpath** matches, not merely because a line in the README says X.

## 3. Compatible Spring Boot 3.5.16 Example Set

The **Spring Boot 3.5.16** managed dependency coordinates page gives concrete examples:

| Component | Version in Example BOM | Role |
| --- | --- | --- |
| Spring Boot starters | 3.5.16 | Auto-configuration and starter dependencies |
| Spring Security core/web/config | 6.5.11 | Authentication, authorization, filters, DSL |
| Spring Security test | 6.5.11 | MockMvc/security test helpers |
| Spring Security OAuth2 Client/Resource Server | 6.5.11 | OAuth2 login, JWT resource server |
| Spring Framework modules | 6.2.19 | Context, Beans, WebMVC, Servlet integration |
| Spring Boot Maven/Gradle plugin | Selected with Boot release when used | Build/run/package; not a runtime library |

**Do not assume** every artifact prefixed with `spring-security` carries version 6.5.11: some products have independent version lines, such as Spring Authorization Server and specialized integration modules. Always look up the managed coordinates table by **exact artifact ID**.

Spring Boot 4.0+ pairs with Spring Framework 7 / Spring Security 7 and has breaking changes compared to Boot 3.5 / Security 6.5. Do not change only Security core from 6.x to 7.x inside Boot 3.x and assume the stack remains compatible; that is a **major migration**, not a single patch JAR update.

## 4. Maven: The Simplest Approach Is spring-boot-starter-parent

Maven Parent is usually the lowest-configuration approach for a Boot application.

### 4.1. Standalone pom.xml with Full BOM and Dependencies

File `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>boot-bom-auth-demo</artifactId>
    <version>1.0.0</version>
    <name>boot-bom-auth-demo</name>

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
~~~

**Key points:**

- Only **parent** pins Boot version `3.5.16`.
- Dependencies are managed by the BOM, so **there is no `<version>` on each dependency**.
- The parent supplies build defaults, dependency management, and suitable plugin management; hence `spring-boot-maven-plugin` does not need a separate version in the configuration above either.
- `<java.version>17</java.version>` specifies the project’s bytecode/toolchain, **not the Spring Security version**.
- `spring-security-test` is used for testing; the BOM manages it in sync with the other Spring Security modules.
- `spring-boot-starter-security` contains dependencies suitable for basic security; if you need OAuth2 Resource Server or SAML, you must **add the corresponding starter/module**, as the BOM does not enable them automatically.

### 4.2. How Does Parent Inherit the BOM?

Relationship:

~~~text
Project POM
    |
    +-- parent: spring-boot-starter-parent:3.5.16
              |
              +-- spring-boot-dependencies:3.5.16
                       |
                       +-- dependencyManagement
                       |      spring-security-core 6.5.11
                       |      spring-security-web  6.5.11
                       |      spring-security-test 6.5.11
                       |      spring-webmvc         6.2.19
                       |      ...
                       |
                       +-- properties for managed versions
~~~

When Maven encounters:

~~~xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

It uses the managed version, **not a random version**, and does not force developers to memorize which Spring Security version corresponds to Boot.

### 4.3. Why Is Using Parent More Convenient Than Importing the BOM?

The parent brings additional defaults that importing the BOM alone **does not** fully provide: Maven plugin configuration, compiler/encoding settings, resource filtering, and repackage tasks. If a corporate project allows inheriting the Boot parent, choosing the parent reduces build maintenance work.

If an enterprise **must use a custom parent POM**, you cannot declare two Maven parents at once. In that case, import the BOM as shown in the next section.

## 5. Maven: Importing the BOM When a Project Has Its Own Parent

For example, a project uses `com.example.build:company-parent` and cannot use `spring-boot-starter-parent` directly.

**This is a POM fragment** and must be placed inside a real POM with an appropriate corporate parent/build plugins:

~~~xml
<properties>
    <java.version>17</java.version>
    <maven.compiler.release>17</maven.compiler.release>
    <spring-boot.version>3.5.16</spring-boot.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>${spring-boot.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

**An easily missed difference:** importing `spring-boot-dependencies` **only** brings dependency management, not plugin management or all parent defaults. You must configure/coordinate compiler, Surefire, Spring Boot Maven plugin, and repackaging yourself as needed, aligned with your corporate parent.

Example build plugin when not using the Boot parent:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <version>${spring-boot.version}</version>
            <executions>
                <execution>
                    <goals>
                        <goal>repackage</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

This is also a **fragment**; cross-check the corporate parent’s plugin management to avoid duplicate declarations, especially if the parent already defines its own packaging workflow.

### 5.1. Property Overrides Differ Between Parent and Import

When using **Spring Boot parent**, you can adjust a managed version using the appropriate property, for example:

~~~xml
<!-- Example fragment to recognize how overrides work; NOT recommended arbitrarily. -->
<properties>
    <spring-security.version>6.5.11</spring-security.version>
</properties>
~~~

However, when **importing the BOM under `dependencyManagement`** without inheriting the Boot parent, declaring the `spring-security.version` property in the project POM **does not automatically replace the property already interpolated inside the imported BOM**. If an override is needed, you must use an explicit dependency management entry or a BOM/parent strategy supported by the build tool, and inspect the effective POM.

**Recommendation:** avoid overrides unless there is an official reason (security advisory/compatibility test), because changing a single module can desynchronize the graph.

### 5.2. When Multiple BOMs Are Present

An enterprise might import the Spring Cloud BOM, Spring Boot BOM, a corporate BOM, and another vendor’s BOM. Do not assume “the last imported BOM always wins” in every situation.

In Maven, **direct management/parent precedence and the declaration order of imported BOMs** can determine the selected version; specifically for overlapping coordinates across imported BOMs, import order follows specific rules. To avoid mistakes, **inspect the effective POM and dependency tree**, then add tests ensuring modules that must align do not drift.

If using **Spring Cloud**, you must pick the **release train confirmed by Spring Cloud docs as compatible with the Boot line in use**. Importing the Spring Cloud BOM is not a license to upgrade Boot arbitrarily.

## 6. Maven: Which Version Is Actually Being Used?

Even with a BOM, you still need to inspect the **effective model** and **resolved graph**.

### 6.1. Inspection Commands

In the directory containing `pom.xml`:

~~~bash
mvn -version
mvn help:effective-pom -Doutput=effective-pom.xml
mvn help:evaluate -Dexpression=spring-security.version -q -DforceStdout
mvn dependency:tree -Dincludes=org.springframework.security:*
mvn dependency:tree -Dincludes=org.springframework:*
mvn test
~~~

Explanation:

- `mvn -version`: Maven/JDK running the build; do not use this output to infer the Security version.
- `help:effective-pom`: the model after merging parent, properties, and dependency/plugin management.
- `help:evaluate`: with Boot parent, inspects the managed Spring Security property; when using a separate BOM import, the property in the current POM may not be exposed as you expect.
- `dependency:tree`: **this is crucial evidence** of resolved versions, transitive dependencies, and mediation; shows the `spring-security-*` modules actually on the classpath.
- `mvn test`: verifies the actual build+tests; insufficient if critical login/API security tests are missing.

In shells with special wildcard characters, you can quote `-Dincludes=org.springframework.security:*`. On Windows PowerShell, use appropriate quoting; the goal is not a filesystem glob, but the Maven dependency plugin filter.

**Do not commit a generated `effective-pom.xml`** if it contains secrets/build metadata or falls outside repository policy.

### 6.2. How to Read a Dependency Tree

**Illustrative** excerpt, not output from an executed build:

~~~text
demo:boot-bom-auth-demo:jar:1.0.0
+- org.springframework.boot:spring-boot-starter-security:jar:3.5.16:compile
|  +- org.springframework.security:spring-security-config:jar:6.5.11:compile
|  \- org.springframework.security:spring-security-web:jar:6.5.11:compile
\- org.springframework.security:spring-security-test:jar:6.5.11:test
~~~

Meanwhile `spring-security-core` usually appears as a transitive dependency. The exact structure of the tree depends on the specific version and dependencies, with no fixed line count or indentation.

If you see:

~~~text
spring-security-core:6.5.11
spring-security-web:6.4.3
spring-security-config:6.5.11
spring-security-test:6.5.11
~~~

that is a sign of **version skew** requiring investigation. Do not “fix” it by pinning `spring-security-core:6.4.3` to match web; identify **what forced web down to the wrong version** and restore unified BOM management.

### 6.3. Checking Build Plugins and the Runtime Artifact

A BOM manages **library versions**, but the runtime JAR is also affected by Maven plugins such as compiler, surefire, shade, and Spring Boot repackage. For POMs not using the Boot parent, verify those plugins are pinned and compatible.

Check:

~~~bash
mvn clean verify
mvn dependency:tree
mvn help:effective-pom
~~~

After packaging, run the application from the **deployed artifact** to catch duplicate/shaded JARs or differing classpaths in containers. The IDE showing the right dependency version alone does not prove the final image uses the right graph.

## 7. Gradle Has Two Ways to Manage a BOM

Gradle uses `build.gradle` (Groovy DSL) or `build.gradle.kts` (Kotlin DSL). With the Spring Boot Gradle plugin, there are two approaches:

1. **`io.spring.dependency-management` plugin:** when applied alongside the Boot plugin, it imports the corresponding BOM and supports property-based version overrides.
2. **Native Gradle `platform(...)`:** imports the BOM directly via Gradle constraints, typically simpler and faster; however, it **does not use BOM properties the way the dependency-management plugin does** for overrides.

Choose **one clear strategy** and avoid applying overlapping mechanisms unnecessarily.

### 7.1. Kotlin DSL with Gradle Native Platform

Complete `build.gradle.kts` for the same demo application:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.16"
}

group = "demo"
version = "1.0.0"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation(platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    ))
    testImplementation(platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    ))

    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-security")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}
~~~

**Meaning:**

- The Boot Gradle plugin has the same version `3.5.16`.
- `SpringBootPlugin.BOM_COORDINATES` supplies the coordinates matching the **current Boot plugin version**, avoiding copying two version strings that might diverge.
- `platform(...)` brings managed constraints into Gradle configurations. Here both `implementation` and `testImplementation` are declared to keep the test scope explicit.
- Managed dependencies **omit versions**.
- The Gradle Java toolchain uses JDK 17+ matching the baseline.
- There is no need to also apply `io.spring.dependency-management` in this example.

You can replace `SpringBootPlugin.BOM_COORDINATES` with explicit coordinates:

~~~kotlin
implementation(platform(
    "org.springframework.boot:spring-boot-dependencies:3.5.16"
))
~~~

However, if the plugin is upgraded to another 3.5.x and you forget to update that string, the graph can end up using **plugin version A, BOM version B**. Using the constant helps reduce drift.

### 7.2. Equivalent Groovy DSL (Fragment)

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )
    testImplementation platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )

    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

This is an **illustrative** configuration; declare the Java toolchain and JUnit Platform when using it in a real project. The Kotlin DSL above is the complete example for the demo project.

### 7.3. The io.spring.dependency-management Option

With this Gradle plugin, when used alongside the Spring Boot Gradle plugin, the BOM is automatically imported:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.16"
    id("io.spring.dependency-management") version "1.1.7"
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-web")
}
~~~

This is a **build fragment**; add the Java toolchain/test dependencies if turning it into a runnable project. **Do not** copy both BOM management blocks from section 7.1 and this section into one build without a deliberate design.

When using the dependency management plugin, properties published by the Spring Boot BOM such as `spring-security.version` can be customized per the Gradle plugin documentation. With native `platform(...)`, you must use Gradle constraints, a resolution strategy, or a suitable mechanism to change a managed version; simply setting a POM property will not take effect automatically.

### 7.4. platform vs. enforcedPlatform

| Approach | Nature | When to Use |
| --- | --- | --- |
| `platform("group:artifact:version")` | Versions in the BOM are **constraints/recommendations** | Reasonable default for most apps |
| `enforcedPlatform("group:artifact:version")` | Forces stronger constraints, capable of overriding other versions | When strict alignment is truly needed and impact has been analyzed |
| `io.spring.dependency-management` | Maven-like dependency management in Gradle | When you want to use managed-version properties |
| Pinning `implementation("...:6.5.11")` individually | Explicit version, can affect resolution | Only when justified and after testing the entire graph |

Per Gradle documentation, `enforcedPlatform` can also **export strict constraints along the dependency graph**, making things harder for other projects consuming your **library**; do not enable `enforcedPlatform` in shared libraries without understanding the consequences.

Native `platform` does not always force runtime to take 100% of the BOM versions if the graph contains other constraints/requests. **Inspecting the resolved graph** is mandatory.

## 8. Gradle: Inspecting Resolution Results Instead of Guessing

In a Kotlin/Groovy DSL project with the Gradle Wrapper, run:

~~~bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-web --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-config --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-test --configuration testRuntimeClasspath
./gradlew test
~~~

On Windows:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency spring-security-web --configuration runtimeClasspath
.\gradlew.bat test
~~~

**Interpretation:**

- `dependencies` displays resolved versions and the dependency graph.
- `dependencyInsight` explains why Gradle selected a version for a module, including selection/constraint reasons and what requested it.
- `testRuntimeClasspath` can differ from `runtimeClasspath`, so check `spring-security-test` in the right scope.
- `--version` only tells you Gradle/JVM, not the runtime Security version.
- After upgrading versions, re-check both `runtimeClasspath` and `testRuntimeClasspath`; Gradle may select a version upgraded by another constraint.

## 9. Runnable Java 17+ Example: Spring Security Authentication with BOM-Managed Dependencies

Use **`pom.xml` from section 4** or **`build.gradle.kts` from section 7.1**. The Java file below uses the exact Spring Security APIs available in the 6.5 branch managed by Boot 3.5.16.

Directory structure:

~~~text
boot-bom-auth-demo/
├── pom.xml                   (or build.gradle.kts + settings.gradle.kts)
└── src/
    ├── main/java/demo/bom/BomAuthDemoApplication.java
    └── test/java/demo/bom/BomAuthDemoTests.java
~~~

For Gradle also create `settings.gradle.kts`:

~~~kotlin
rootProject.name = "boot-bom-auth-demo"
~~~

### 9.1. BomAuthDemoApplication.java

~~~java
package demo.bom;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class BomAuthDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(BomAuthDemoApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("learner")
                .password(encoder.encode("lab-password"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @RestController
    static class Routes {

        @GetMapping("/health")
        String health() {
            return "ready";
        }

        @GetMapping("/me")
        String me(Authentication authentication) {
            return "hello:" + authentication.getName();
        }
    }
}
~~~

**Explanation:**

1. `SpringApplication` belongs to Spring Boot.
2. `HttpSecurity` and `SecurityFilterChain` belong to Spring Security config/web.
3. `UserDetailsService`, `User`, and `Authentication` belong to Spring Security core.
4. `BCryptPasswordEncoder` belongs to Spring Security crypto.
5. `httpBasic` requires the caller to provide user/password; `/me` must be authenticated and `/health` is public.
6. Those classes come from multiple JARs, yet **the Boot BOM selected coordinated versions**.
7. The lab uses an in-memory user with no database and does not expose plaintext passwords in HTTP responses; use only local HTTP, or HTTPS when testing externally.

Do not configure `@EnableMultiFactorAuthentication` in the Boot 3.5/Security 6.5 sample; this class belongs to Spring Security 7+ and is not in the example BOM.

### 9.2. BomAuthDemoTests.java — Integration Tests

~~~java
package demo.bom;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BomAuthDemoTests {

    @Autowired
    MockMvc mvc;

    @Test
    void healthIsPublic() throws Exception {
        mvc.perform(get("/health"))
            .andExpect(status().isOk())
            .andExpect(content().string("ready"));
    }

    @Test
    void meRequiresAuthentication() throws Exception {
        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void correctHttpBasicAuthenticates() throws Exception {
        mvc.perform(get("/me").with(httpBasic("learner", "lab-password")))
            .andExpect(status().isOk())
            .andExpect(content().string("hello:learner"));
    }

    @Test
    void badPasswordIsRejected() throws Exception {
        mvc.perform(get("/me").with(httpBasic("learner", "wrong")))
            .andExpect(status().isUnauthorized());
    }
}
~~~

**Note on static imports:** because a long import is needed, Java allows line breaks after the `import static` keyword, though that can be error-prone when copying; you can write it compactly on **one line** as follows instead of the two lines above:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
~~~

Do not keep both duplicate imports in a real file. In the code above, the long import is line-wrapped per Java syntax (whitespace is permitted between tokens), and remains a single import statement.

### 9.3. Running the Build

With Maven:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

With Gradle:

~~~bash
./gradlew clean test
./gradlew bootRun
~~~

When dependencies are right and Java 17+ is available, the **expected result** of the test suite is:

~~~text
Tests run: 4, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

This is an **expected output excerpt for Maven**, not output executed on the learner’s machine. Gradle uses a different reporting format, such as `BUILD SUCCESSFUL`.

Test local HTTP Basic:

~~~bash
curl -i http://localhost:8080/health
curl -i --user learner:lab-password http://localhost:8080/me
curl -i --user learner:wrong http://localhost:8080/me
~~~

Expected:

~~~text
GET /health                 -> HTTP 200, body: ready
GET /me with valid Basic    -> HTTP 200, body: hello:learner
GET /me with wrong Basic    -> HTTP 401
~~~

**Do not** use HTTP Basic or lab credentials over public networks without TLS; the command line can store secrets in shell history/process lists.

## 10. Standalone Java 17: Detecting Version Skew Across Modules

When reading a dependency tree, what matters is not only “Spring Security is present” but also that the modules belong to **the same managed set**. The demo below simulates that audit step. It does not read a real Maven/Gradle graph; the graph must be exported from the build tool.

Create `SecurityVersionAlignmentDemo.java`:

~~~java
import java.util.List;

public class SecurityVersionAlignmentDemo {

    record Module(String artifactId, String version) {}

    static boolean allSameVersion(List<Module> modules) {
        if (modules.isEmpty()) {
            return true;
        }
        String expected = modules.get(0).version();
        return modules.stream()
            .allMatch(m -> expected.equals(m.version()));
    }

    public static void main(String[] args) {
        List<Module> aligned = List.of(
            new Module("spring-security-core", "6.5.11"),
            new Module("spring-security-web", "6.5.11"),
            new Module("spring-security-config", "6.5.11"),
            new Module("spring-security-test", "6.5.11")
        );

        List<Module> skewed = List.of(
            new Module("spring-security-core", "6.5.11"),
            new Module("spring-security-web", "6.4.3"),
            new Module("spring-security-config", "6.5.11")
        );

        System.out.println("aligned=" + allSameVersion(aligned));
        System.out.println("mixed=" + allSameVersion(skewed));
        System.out.println("artifactCount=" + aligned.size());
    }
}
~~~

Run with JDK 17+:

~~~bash
javac --release 17 SecurityVersionAlignmentDemo.java
java SecurityVersionAlignmentDemo
~~~

**Exact stdout:**

~~~text
aligned=true
mixed=false
artifactCount=4
~~~

Note: this is only an **equality check** across the Spring Security modules in the example. In real life, many Spring artifacts belong to **different version lines by design**, such as Spring Framework 6.2.19 and Boot 3.5.16, so **do not** write a rule forcing all `org.springframework.*` artifacts to share the same version number.

Nor should you assume every artifact containing the word `security` must equal 6.5.11: select **the set of modules within one BOM family** that release notes/managed coordinates actually require to share a version.

## 11. Principles for Controlled Version Overrides

When a CVE or library bug is discovered, a common reflex is to pin:

~~~xml
<!-- ANTI-EXAMPLE: arbitrarily pinning one module from another line. -->
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-core</artifactId>
    <version>7.0.0</version>
</dependency>
~~~

**Do not** do this in a Boot 3.5/Security 6.5 project without planning a major stack upgrade. The result can be core 7.0 paired with config/web 6.5, or Security 7 expecting a newer Spring Framework 7/Jackson that Boot 3.5 does not provide.

Sensible handling order:

1. Find a **newer Boot patch within the same supported line** that already manages the fix.
2. Upgrade **the Boot parent/Boot plugin together with the BOM**, then verify the dependency tree, smoke tests, and security regression tests.
3. If an advisory requires upgrading a module immediately before a Boot patch is available, review Spring Security guidance and compatibility, and prefer overriding **the entire Security BOM train** (within the supported range), not core alone. Record the reason and expected removal date of the override.
4. For a major 3.x → 4.x upgrade, migrate step by step rather than pinning a single JAR.
5. Run tests for login, OAuth/OIDC, JWT, CSRF, password encoding, LDAP/SAML, and sessions across the mechanisms the project actually uses.
6. Inspect the deployment image, SBOM, dependency vulnerabilities, and build plugins, not just the POM.
7. Have rollback and post-deploy monitoring in place.

**Do not use `latest.release`, `+`, or uncontrolled dynamic versions** for security-critical production dependencies; builds must be reproducible. The BOM is pinned to a Boot release, and upgrades are reviewed/tested changes.

### 11.1. Overriding the Whole Train Still Requires Compatibility Checks

The existence of the Maven property `spring-security.version` does not mean **every future Spring Security release** runs well on an older Boot release. Spring Security 7 has breaking changes; Spring Framework, Jackson, the Servlet stack, and Boot auto-configuration may require corresponding upgrades.

“A version override can be declared” is a build tool capability; “it is compatible” is a **conclusion that must be proven with documentation and tests**.

### 11.2. Maven Precedence and Dependency Convergence

Maven has multiple version sources:

- Explicit version on a direct dependency.
- Local `dependencyManagement`.
- Parent inheritance.
- Imported BOMs, with precedence rules based on structure/declaration.
- Transitive dependency versions from upstream POMs.

For complex graphs, use Maven Enforcer rules per policy, such as `dependencyConvergence` or `requireUpperBoundDeps` (depending on the use case), but **do not enable them without review**: some libraries have multiple valid dependency paths and the rules can flag many conflicts to resolve.

Do not simply delete all `<version>` tags and assume everything is right; libraries **outside the BOM** still need deliberate versions, such as an uncommon vendor API.

## 12. Spring Boot BOM vs. Spring Security BOM

| Scenario | Consider | Why |
| --- | --- | --- |
| Normal Spring Boot application | **Spring Boot BOM** | Manages Boot, Security, Framework, and related libraries together |
| Application not using Spring Boot | Spring Security BOM + Spring Framework BOM as needed | Consistently manages Security modules |
| Existing corporate Maven parent | Import Spring Boot BOM | No need to drop the enterprise parent |
| Gradle with Spring Boot plugin | Dependency-management plugin or native platform | Version constraints for runtime/test dependencies |
| Multi-module build | One BOM version source at root/corporate convention | Prevents each module from picking its own stack |
| Project with Spring Cloud | Boot BOM + matching Spring Cloud BOM release train | Cloud components have their own compatibility policy |
| Migrating Boot 3 → 4 | Tested stack upgrade | Security 6 → 7 and Framework 6 → 7 have breaking changes |

**Do not mechanically import an extra Spring Security BOM into an application already using the Spring Boot BOM**. When an override strategy is needed, understand BOM precedence and audit the resolved graph so the Security train is not altered unintentionally.

## 13. When Upgrading the Spring Boot BOM, What Must Be Verified in Authentication?

A smoke test that only confirms application startup can miss a host of security bugs. Before and after an upgrade, check the flows actually in use:

### 13.1. Session-Based Form Login

- [ ] Anonymous GET to a protected resource redirects to the right login page.
- [ ] Login with right/wrong password follows the expected success/failure flow.
- [ ] CSRF token is still required for unsafe requests.
- [ ] Session fixation protection, logout, and session timeout match policy.
- [ ] `Secure`/`HttpOnly`/`SameSite` cookies are set properly on public HTTPS ingress.
- [ ] Remember-me or custom security context repositories do not exhibit unexpected behavior changes.

### 13.2. REST/JWT/Bearer

- [ ] JWT signature/algorithm/JWK, `iss`, `aud`, and `exp` are validated properly.
- [ ] Authorities/scopes mapping and authorization matchers have not changed.
- [ ] API returns 401/403 per contract, without unexpected form-login redirects.
- [ ] No raw tokens/sensitive claims are logged when new exceptions occur.
- [ ] CORS/CSRF are applied per the real threat model, without disabling CSRF due to an upgrade error.

### 13.3. OAuth2/OIDC/SAML/LDAP

- [ ] OAuth2 Login callback, redirect URI, state/nonce, and cookies still work.
- [ ] OIDC issuer/JWK/userinfo validation, scopes, and principal mapping are accurate.
- [ ] SAML signature, destination, relay state, and clocks are accurate.
- [ ] LDAP/AD TLS, bind, and role mapping have not changed behavior.
- [ ] Custom authentication providers support the right token types and exception mapping.

### 13.4. API/DSL Migration

If upgrading Security 6 → 7, read the migration guide, especially changed/removed APIs and serialization/trust boundary mechanisms. For example, `FactorGrantedAuthority`/`@EnableMultiFactorAuthentication` belong to Security 7.0+; do not assume they exist in 6.5.

Boot 4 moves to Spring Framework 7 and brings changes in Jackson, starters, API requirements, and auto-configuration; do not just bump a version string and skip compiler and integration tests.

## 14. CI/CD: Keeping Consistency When the Whole Team Develops Together

A minimal CI workflow:

~~~text
1. Checkout source + versioned Maven Wrapper / Gradle Wrapper
2. Verify JDK/toolchain and dependency repositories
3. Resolve graph from a single BOM/version
4. Check BOM precedence, dependency convergence/alignment
5. Build + unit tests + Spring Security integration tests
6. Scan vulnerabilities + generate SBOM (if policy requires)
7. Package artifact/container
8. Verify runtime artifact and startup smoke tests
9. Deploy staging; run login/session/JWT/CSRF/OIDC regressions
10. Review/approve production release, monitor, and rollback policy
~~~

Specific controls:

- **One source of truth:** parent/BOM version pinned in root POM or build convention and reviewed via pull requests.
- **Dependency lockfile/verification:** use Maven/Gradle wrappers and appropriate dependency locking/verification mechanisms.
- **Known-good graph:** store resolved dependency tree/SBOM results in protected build artifacts.
- **Security checks:** scan CVEs against the resolved SBOM, not only declared dependencies.
- **Automated tests:** verify both zero classpath drift and critical authentication/authorization behavior.
- **Review overrides:** every version override has a rationale, owner, advisory link, and removal deadline.
- **Repository safety:** do not use untrusted artifact repositories or uncontrolled dependency substitutions.
- **Build reproducibility:** do not let dynamic versions make today’s build differ from tomorrow’s when source is unchanged.

### 14.1. Example Patch Upgrade Workflow

Suppose you are on Boot `3.5.15` and want to move to `3.5.16`:

1. Change **one Boot parent/plugin version** in the primary management source.
2. Ensure the Gradle BOM constant/import follows the same Boot version if using `platform`.
3. Run `dependency:tree` or `dependencyInsight` to inspect Security core/web/config/test under the new graph.
4. Run unit/integration authentication tests.
5. Review vulnerability reports and release notes.
6. Package the artifact, run startup smoke tests, and run E2E login in staging.
7. Only then deploy; on regression, roll back the entire build without mixing old and new JARs.

This is an **example workflow**, not an implication that 3.5.16 is a required patch for every project.

## 15. Troubleshooting Common Issues When the BOM Behaves Unexpectedly

| Symptom | Possible Cause | Diagnosis / Fix |
| --- | --- | --- |
| `spring-security-core` 6.5 while `web` 6.4 | Individual pin, another BOM, or override | Dependency tree/insight, remove bad pin |
| Boot plugin 3.5.x while runtime uses Boot dependencies 3.4.x | Manual Gradle BOM import with wrong version | Use BOM_COORDINATES, check constraints |
| Maven parent right but JAR has different version | Direct `<version>` / local dependencyManagement | Check effective POM + tree |
| BOM imported but plugin versions unmanaged | BOM import does not replace Maven plugin management | Explicitly pin/configure plugins |
| `ClassNotFoundException` after copying Security 7 code | BOM still manages Security 6.5 | Use version-appropriate API or migrate to Boot 4/Security 7 |
| Runtime `NoSuchMethodError` | Classpath drift or differently shaded/packaged JAR | Print graph, inspect packaged artifact, check transitive conflicts |
| `spring-security-test` helpers do not compile | Test dependency not declared or version skew | Add test module without version, check testRuntimeClasspath |
| `Could not resolve version` | Missing BOM import or dependency outside BOM | Check plugin/platform/dependencyManagement |
| Gradle platform upgraded past BOM | Another version constraint wins | `dependencyInsight` identifies selection reason |
| Build succeeds but login fails | API/config/behavioral incompatibility | Integration tests against real filter chain |
| Spring Cloud breaks after Boot upgrade | Incompatible release train | Check compatibility matrix before upgrading |
| CVE scanner still flags old JAR | Image build cache/shaded artifact or old graph | Scan packaged artifact/SBOM |
| Maven property override has no effect on BOM import | Imported BOM does not use project property like parent inheritance | Intentional local managed entry, check effective POM |
| Two BOMs manage the same coordinates | Precedence and import order | Audit BOMs, reduce duplication, check resolved graph |
| Corporate parent conflicts with compiler/plugins | BOM import does not carry plugin defaults | Pin Maven plugins/toolchain per policy |

## 16. Practical Checklist

**Configuration**

- [ ] Project selects a clear, supported Spring Boot BOM version.
- [ ] Maven uses starter-parent or imports BOM appropriately, without two parents.
- [ ] Managed dependencies omit individual versions.
- [ ] Gradle has the dependency management plugin or platform import in the right scopes.
- [ ] Boot plugin/build plugins and dependencies match release policy.
- [ ] Java 17+ and toolchain/compiler options match the Boot version.
- [ ] Spring Security core/web/config/test resolve to the right train.

**Verification**

- [ ] Maven effective POM and dependency tree have been inspected.
- [ ] Gradle dependencyInsight for security modules and testRuntimeClasspath have been inspected.
- [ ] Tests cover authentication success/failure, authorization, CSRF, and session or JWT depending on app.
- [ ] Modules outside the BOM are pinned/tested separately.
- [ ] All overrides are audited with a removal plan.
- [ ] CI scans the SBOM of the final artifact and checks release notes.
- [ ] Runtime image does not mix multiple JARs of the same group with different versions.

**Upgrading**

- [ ] Prefer upgrading a tested Boot patch over pinning a single module.
- [ ] For major migrations, read the Spring Security/Boot migration guide.
- [ ] Do not enable Security 7 APIs inside a Security 6.x stack.
- [ ] Verify Spring Cloud release train compatibility.
- [ ] Have staging E2E login, logout, OAuth/OIDC/JWT/SAML/LDAP per use case.
- [ ] Have rollback and post-deploy monitoring ready.

## 17. Self-Check Questions

1. Does a BOM automatically add `spring-boot-starter-security` to the classpath?
2. What is the difference between `spring-boot-dependencies`, `spring-boot-starter-parent`, and `spring-boot-starter-security`?
3. Why do BOM-managed dependencies not need a `<version>` on each declaration?
4. Does an imported Maven BOM automatically configure compiler/Surefire/repackage plugins like the Boot parent?
5. Why can you not have two Maven parents? When you have a company parent, what should you do?
6. How does Maven `dependency:tree` differ from `help:effective-pom`?
7. How does Gradle `platform(...)` differ from `enforcedPlatform(...)`?
8. Why is an imported BOM’s version property not overridden the same way as an inherited parent’s?
9. Why must `spring-security-test` also be included in alignment checks?
10. If Security core is 6.5.11 and web is 6.4.3, what should you do first?
11. Why does Boot 3.5/Security 6.5 not include `@EnableMultiFactorAuthentication`?
12. Why does an unpatched CVE not automatically mean you should pin Security core from 6 to 7?
13. Can Maven/Gradle show the right managed version while the packaged JAR is wrong? Give one reason.
14. Does a BOM replace integration tests for JWT, CSRF, sessions, or SSO?
15. Why does the Spring Cloud BOM require a compatibility matrix with Spring Boot?
16. How do you use Gradle `dependencyInsight` to find out what upgraded a version outside the BOM?
17. When importing multiple BOMs, why must you inspect the effective graph?
18. What must be verified when upgrading a Boot patch before deploying to production?

**Conclusion:** The Spring Boot BOM is a **coordinated version-management source** for the entire stack, not a functional library and not a guarantee that every dependency stays compatible when overrides exist. For Spring Security authentication, the reliable workflow is **pick a supported Boot release → use starter-parent/BOM or Gradle platform → omit manual pins on managed dependencies → inspect the resolved graph → test login/authorization and the runtime artifact → upgrade synchronously under control**.

## 18. Official References

- [Spring Boot 3.5 — Maven Plugin: Using the Starter Parent or importing BOM](https://docs.spring.io/spring-boot/3.5/maven-plugin/using.html)
- [Spring Boot 3.5 — Gradle Plugin: Managing Dependencies](https://docs.spring.io/spring-boot/3.5/gradle-plugin/managing-dependencies.html)
- [Spring Boot 3.5 — Managed Dependency Coordinates](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html)
- [Spring Boot 3.5 — Managed Version Properties](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/properties.html)
- [Spring Security — Getting Spring Security](https://docs.spring.io/spring-security/reference/7.0/getting-spring-security.html)
- [Spring Security — Migration to 7.0](https://docs.spring.io/spring-security/reference/migration/)
- [Gradle — Platforms and BOM support](https://docs.gradle.org/current/userguide/platforms.html)
- [Maven — Introduction to Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html)
