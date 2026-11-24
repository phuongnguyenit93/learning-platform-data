# Distinguishing Runtime Placeholder Substitution from Build-Time Resource Filtering

## 1. Two Different Moments for Value Substitution

In **Spring Boot Externalized Configuration**, two techniques look quite similar at first glance: placing a token in a configuration file and expecting it to be replaced with a value. However, they happen at **two completely different phases**:

1. **Runtime property placeholder resolution**: Spring Boot reads configuration, using **Environment** and **PropertySources** to resolve expressions like **${remote.url:https://api.example.invalid}** when a value is used.
2. **Build-time resource filtering/expansion**: Maven or Gradle reads resource files, replaces selected tokens with build-system values, and copies **the substituted content** into outputs like **target/classes** or **build/resources/main** for packaging.

The crucial question is not "is there a placeholder syntax?", but **who substitutes**, **at which stage**, and **where the value ends up**.

| Criterion | Spring runtime placeholder | Build-time resource filtering |
| --- | --- | --- |
| Processing tool | Spring **Environment** and property resolver | Maven Resources Plugin, Gradle **processResources**, or resource filtering task |
| Timing | When the application runs and accesses the property | During the resource processing step at build time |
| Typical syntax | **${name}**, **${name:default}** | Maven uses **@project.version@**; Gradle **expand** often uses **${buildVersion}** |
| Input values | Config Data files, environment variables, system properties, command-line, other PropertySources | Project/build properties, variables/values supplied by the build script |
| Outcome | Values resolved inside **Environment** for that run | Output resource bytes are modified before packaging |
| Need rebuild to change environment? | Not necessarily: supply new config at startup with the same artifact | Yes, if you want to change values baked into the build via filtering |
| Used for | Endpoints, timeouts, feature flags, environment parameters | Version, build timestamp, artifact info, or immutable metadata |
| Security note | Secrets should come from protected runtime sources | Build-time secrets easily get hardcoded into JARs, image layers, or stored artifacts |

Short example:

~~~properties
app.version=@project.version@
app.endpoint=${remote.url:https://sandbox.example.invalid}
~~~

In a Maven project inheriting **spring-boot-starter-parent** with standard resource filtering:

- Maven replaces **@project.version@** with the project version during the build.
- Maven **leaves untouched** the **${remote.url:...}** expression.
- At runtime, Spring Boot resolves **${remote.url:...}** based on the target environment's configuration.

That is the **"build once, run in many environments"** model.

## 2. Lifecycle of Resources and Placeholders

Visualize the flow:

~~~text
Git repository
  ├─ pom.xml / build.gradle
  └─ src/main/resources/application.properties
         |
         | Maven process-resources / Gradle processResources
         v
  target/classes/application.properties
  or build/resources/main/application.properties
         |
         | Package JAR
         v
  app.jar (BOOT-INF/classes/application.properties)
         |
         | Start: java -jar app.jar
         v
  Spring Boot creates Environment, loads Config Data and PropertySources
         |
         | @Value, @ConfigurationProperties, Environment.getProperty
         v
  Final values used in the application
~~~

**Build time** works primarily with **file contents before packaging**. **Runtime** works with **the properties and configuration sources of the running process**.

A value already replaced by Maven/Gradle with a plain string does not turn into a new runtime environment variable. Conversely, a Spring expression preserved in the packaged file can still pick up values from the target host's environment.

### 2.1. A Two-Environment Example

At build time, the project has version **1.8.0**. Source file:

~~~properties
app.build-version=@project.version@
app.remote-url=${remote.url:https://default.example.invalid}
~~~

After Maven filtering:

~~~properties
app.build-version=1.8.0
app.remote-url=${remote.url:https://default.example.invalid}
~~~

**Staging run:**

~~~bash
REMOTE_URL=https://staging.example.invalid java -jar app.jar
~~~

The application can receive:

~~~text
app.build-version = 1.8.0
app.remote-url    = https://staging.example.invalid
~~~

**Production run:**

~~~bash
REMOTE_URL=https://production.example.invalid java -jar app.jar
~~~

The exact same JAR can receive:

~~~text
app.build-version = 1.8.0
app.remote-url    = https://production.example.invalid
~~~

The invariant is **the packaged version**; the variable part is **the runtime property**.

## 3. Spring Boot Runtime Placeholders

Spring Boot allows using **${...}** inside **application.properties** and **application.yml** values. When the application accesses a property, its value can be resolved through **Environment**.

Example:

~~~properties
spring.application.name=orders-service
app.display-name=${spring.application.name}
app.remote-url=${remote.url:https://sandbox.example.invalid}
app.request-timeout=${remote.timeout:5s}
~~~

Meaning:

- **${spring.application.name}** uses the value of another property in Environment.
- **${remote.url:https://sandbox.example.invalid}** looks up **remote.url**; if absent, uses the default URL.
- **${remote.timeout:5s}** uses timeout from runtime sources if present; otherwise uses **5s**.

**The colon** separates the property name from the default value. Do not treat every colon inside a string as YAML syntax or resource-filtering syntax. In **application.yml**, put expressions containing colons inside quotes where appropriate for clarity.

### 3.1. YAML Example

~~~yaml
spring:
  application:
    name: orders-service

app:
  display-name: "${spring.application.name}"
  remote-url: "${remote.url:https://sandbox.example.invalid}"
  request-timeout: "${remote.timeout:5s}"
~~~

These expressions do not require the build tool to substitute them. Spring Boot can read the file containing literal **${...}** and resolve them from runtime sources.

### 3.2. Choosing Canonical Property Names

Spring Boot recommends **lowercase kebab-case** names in placeholders to leverage relaxed binding. For instance, write:

~~~properties
app.total-price=${pricing.total-price:0}
~~~

instead of relying on **${pricing.totalPrice}**. Canonical form helps Spring Boot match corresponding property name variants in sources like environment variables.

For example, the environment variable for **pricing.total-price** under relaxed binding rules is **PRICING_TOTALPRICE**: dots become underscores and hyphens are removed.

### 3.3. Runtime Does Not Mean Continuous Auto-Updates

The phrase "substituted at runtime" **does not mean** Spring Boot automatically detects a new environment variable after the process has started.

Typically **@Value** is injected when the bean is created, and **@ConfigurationProperties** is bound during the ApplicationContext lifecycle. If you change an environment variable in another terminal, a running Java process does not automatically re-read the value just because a placeholder exists. Restart the application or use an explicitly designed refresh mechanism.

## 4. Reading Values via @Value, Environment, and @ConfigurationProperties

Suppose a Spring Boot 3.3, Java 21 project with **spring-boot-starter-web** has:

~~~properties
app.remote-url=${remote.url:https://default.example.invalid}
app.timeout=${remote.timeout:5s}
~~~

You can read via **Environment**:

~~~java
package com.example.config;

import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class RuntimeSettings {
    private final Environment environment;

    public RuntimeSettings(Environment environment) {
        this.environment = environment;
    }

    public String remoteUrl() {
        return environment.getProperty("app.remote-url");
    }

    public String timeout() {
        return environment.getProperty("app.timeout");
    }
}
~~~

Or via **@Value**:

~~~java
package com.example.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class HttpEndpoint {

    private final String url;

    public HttpEndpoint(
            @Value("${app.remote-url}") String url) {
        this.url = url;
    }

    public String url() {
        return url;
    }
}
~~~

In the example above, **@Value("${app.remote-url}")** looks up **app.remote-url**, whose value may contain a placeholder referencing **remote.url**. Spring resolves the reference string before passing it as a constructor argument.

When there are multiple structured parameters, **@ConfigurationProperties** is usually easier to maintain:

~~~java
package com.example.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppOptions(
        String remoteUrl,
        Duration timeout) {
}
~~~

The application needs to register scanning:

~~~java
package com.example.config;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConfigApplication.class, args);
    }
}
~~~

The Binder receives the resolved value and converts **5s** into a **Duration**. This is Spring Boot runtime work, not Maven or Gradle resource filtering.

## 5. Runtime Placeholders and Configuration Source Precedence

When resolving **${remote.url:default}**, Spring Boot searches for **remote.url** across PropertySources. Multiple sources may provide values simultaneously:

~~~text
application.properties: remote.url=https://from-file.example.invalid
environment:            REMOTE_URL=https://from-env.example.invalid
command line:           --remote.url=https://from-cli.example.invalid
~~~

In standard Spring Boot configuration, environment variables take precedence over Config Data files, and command-line arguments take precedence over environment variables. Thus, if all three are present and no higher-precedence source exists, the placeholder uses the command-line value.

Example:

~~~bash
java -jar app.jar \
  --remote.url=https://from-cli.example.invalid
~~~

This is a way to **change configuration at runtime** without rebuilding the JAR.

**The default value after the colon** is used when the referenced key is not supplied under property resolution rules. It is not a new "global configuration source," nor does it replace precedence rules among PropertySources.

### 5.1. No Default Value

~~~properties
app.needed-url=${remote.required-url}
~~~

If **remote.required-url** is absent, resolving at the point of use can fail with an unresolved placeholder error, depending on the access mechanism and resolver configuration. For required keys, validate proactively at startup instead of silently falling back to a dummy endpoint.

### 5.2. Avoid Circular References

~~~properties
app.first=${app.second}
app.second=${app.first}
~~~

This is a circular dependency with no sensible terminating value. Design property chains in one direction and clearly designate where root values live.

## 6. What Is Maven Resource Filtering?

**Maven resource filtering** belongs to the build phase. The resources plugin reads files marked for filtering, finds tokens matching configured delimiters, and writes substituted content to the output directory.

When using **spring-boot-starter-parent**, Spring Boot configures convenient defaults for application configuration files, letting you reference **Maven project properties** using tokens such as:

~~~text
@project.version@
@project.artifactId@
@project.build.sourceEncoding@
@java.version@
~~~

Example **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>orders-service</artifactId>
    <version>1.8.0</version>
    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

**src/main/resources/application.properties**:

~~~properties
spring.application.name=@project.artifactId@
app.build-version=@project.version@
app.java-target=@java.version@
app.remote-url=${remote.url:https://default.example.invalid}
~~~

When running:

~~~bash
./mvnw clean package
~~~

Maven processes resources and packages those build metadata values. The processed file in **target/classes/application.properties** will resemble:

~~~properties
spring.application.name=orders-service
app.build-version=1.8.0
app.java-target=21
app.remote-url=${remote.url:https://default.example.invalid}
~~~

Here **@...@** was processed at build time; **${...}** was preserved for Spring Boot at runtime.

**Note on example versions:** **3.3.13** is an example version from the Spring Boot 3.3 line; in a real project, pick the version approved by your organization and available in your repository. **1.8.0** is an example application version, not a Spring Boot version.

### 6.1. Why Does Maven Prefer @...@ for Spring Boot Configuration?

The Maven Resources Plugin can accept different delimiters, including **${...}** if default delimiters are enabled. However, Spring also uses **${...}** for runtime placeholders. If both the build tool and Spring try to process **${...}**, problems can arise:

- Maven replaces an expression meant to wait until runtime.
- The build fails because the token has no matching variable in the build context.
- Environment values or passwords get baked permanently into the artifact.
- Two developers get different build outputs simply because their build properties differ.

Configuring **spring-boot-starter-parent** to use **@...@** delimiters for filtering clearly separates:

~~~text
@project.version@       -> processed by Maven at build time
${remote.url:default}   -> processed by Spring Boot at runtime
~~~

Avoiding collisions is the technical reason behind this convention, not merely aesthetic preference.

### 6.2. When Not Using spring-boot-starter-parent

If you do not inherit from the starter parent, Maven does not automatically apply the same resource filtering rules. To filter application config files, you must configure **maven-resources-plugin** and resource filtering explicitly.

Example snippet for **build** in **pom.xml**:

~~~xml
<build>
    <resources>
        <resource>
            <directory>src/main/resources</directory>
            <filtering>true</filtering>
        </resource>
    </resources>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-resources-plugin</artifactId>
            <configuration>
                <delimiters>
                    <delimiter>@</delimiter>
                </delimiters>
                <useDefaultDelimiters>false</useDefaultDelimiters>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

**useDefaultDelimiters=false** is essential so the build tool does not accidentally process **${...}** placeholders meant for Spring.

When configuring general resource filtering, do not filter binary files. Keep images, fonts, certificates, or binary assets in an unfiltered resource group to avoid corrupting bytes.

### 6.3. Scope of Maven Filtering

Spring Boot documentation describes the parent configuration for **production resources**. **src/test/resources** is not automatically filtered in the same way. If a test reads an **@project.version@** token inside a separate test file, do not assume Maven replaced it just because **src/main/resources/application.properties** is filtered.

Additionally, some ways of running directly from **src/main/resources**—such as hot-reload setups that optionally add source resources directly onto the classpath—may bypass the Maven-filtered **target/classes** copy. When verifying, test the packaged artifact rather than relying solely on IDE run behavior.

## 7. Gradle Resource Expansion

Gradle can also substitute build-time values, yet **do not assume** Spring Boot configuration files are automatically processed like Maven's starter parent. You must configure the **processResources** task if expansion is wanted.

Example **build.gradle** using Groovy DSL:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.8.0'

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}

tasks.named('processResources') {
    filesMatching('application.properties') {
        expand(buildVersion: project.version.toString())
    }
}
~~~

In **src/main/resources/application.properties**:

~~~properties
app.build-version=${buildVersion}
app.remote-url=\${remote.url:https://default.example.invalid}
~~~

When running:

~~~bash
./gradlew clean bootJar
~~~

Gradle **processResources** replaces **${buildVersion}** with **1.8.0**. In the template file, the runtime expression **${remote.url:...}** has a leading **\** escape so **Gradle SimpleTemplateEngine** does not try to evaluate it.

The processed output file is expected to look like:

~~~properties
app.build-version=1.8.0
app.remote-url=${remote.url:https://default.example.invalid}
~~~

Then Spring Boot uses **remote.url** from the runtime environment to resolve the remaining placeholder.

### 7.1. Why Is Gradle More Prone to Conflicts?

Per Spring Boot documentation, **Gradle expand** uses Groovy's **SimpleTemplateEngine** and processes **${...}** tokens—the same syntax Spring Boot uses at runtime. So if you declare:

~~~groovy
tasks.named('processResources') {
    expand(project.properties)
}
~~~

to filter all resources, Spring placeholders in **application.properties** or **application.yml** can be misinterpreted by Gradle as build-time expressions.

Source example:

~~~properties
app.remote-url=${remote.url:https://runtime.example.invalid}
~~~

This expression is valid for Spring, not as a simple Gradle variable; you cannot assume the build tool will always leave it intact. Safe strategies include:

1. Restrict **filesMatching** strictly to templates that actually need expansion.
2. Escape Spring tokens **\${...}** in files filtered by Gradle.
3. Or design a dedicated build-metadata file while excluding **application.yml** from filtering.

### 7.2. When to Use expand(project.properties)?

Using **expand(project.properties)** lets Gradle read project properties like **name**, **version**, and **description**. Yet because the key scope is broad, the chance of colliding with runtime placeholders also increases.

If you only need to embed the version into the artifact, explicitly configure **expand(buildVersion: project.version.toString())** and limit target files so readers see exactly what is allowed to transform.

**Note:** the Gradle example above uses Groovy DSL (**build.gradle**). For Kotlin DSL (**build.gradle.kts**), convert task configuration and map parameters to Kotlin syntax accordingly.

## 8. Least-Conflict Approach with Gradle: Filter Only a Separate Metadata File

A maintainable design is **not filtering application.properties at all**. Instead, create **build-meta.properties** holding build-known data, and import it into Spring Boot via Config Data.

Structure:

~~~text
src/main/resources/
├── application.properties
└── build-meta.properties
~~~

**application.properties**: uses only runtime placeholders and is not expanded by Gradle:

~~~properties
spring.application.name=orders-service
spring.config.import=classpath:build-meta.properties

app.remote-url=${remote.url:https://default.example.invalid}
app.timeout=${remote.timeout:5s}
~~~

**build-meta.properties**: uses only build placeholders:

~~~properties
app.build-version=${buildVersion}
~~~

**build.gradle**:

~~~groovy
version = '1.8.0'

tasks.named('processResources') {
    filesMatching('build-meta.properties') {
        expand(buildVersion: project.version.toString())
    }
}
~~~

At build time, **build-meta.properties** becomes:

~~~properties
app.build-version=1.8.0
~~~

While **application.properties** remains untouched:

~~~properties
spring.application.name=orders-service
spring.config.import=classpath:build-meta.properties
app.remote-url=${remote.url:https://default.example.invalid}
app.timeout=${remote.timeout:5s}
~~~

This separates responsibilities:

- **build-meta.properties** holds information tied to the build.
- **application.properties** holds per-startup configuration.
- **spring.config.import** lets Spring Boot read the metadata file as an additional configuration source.
- Maven/Gradle never have to deal with runtime placeholders.

Some projects also use **spring-boot:build-info** (Maven) or the **bootBuildInfo** task (Gradle) to generate standard Spring Boot build metadata and read it from **BuildProperties** when needed. This fits well if the goal is solely exposing build info without injecting version into **application.properties**.

## 9. Hands-On Comparison Before and After Build

One of the clearest ways to learn is inspecting **three versions of the same file**:

1. The source file in the repository.
2. The resource file after Maven/Gradle processing.
3. The values Spring Boot provides when the application runs.

### 9.1. Before Build

Maven example **src/main/resources/application.properties**:

~~~properties
app.build-version=@project.version@
app.remote-url=${remote.url:https://sandbox.example.invalid}
~~~

In this state, both tokens are literal.

### 9.2. After Build

Run:

~~~bash
./mvnw clean package
~~~

Open **target/classes/application.properties**. If Maven filtering is configured properly, the file will resemble:

~~~properties
app.build-version=1.8.0
app.remote-url=${remote.url:https://sandbox.example.invalid}
~~~

**1.8.0** has been baked into the package. **${remote.url:...}** remains in the resource waiting for Spring to process.

With Gradle, inspect **build/resources/main/application.properties** or the corresponding dedicated metadata file. Do not just look at **src/main/resources** and conclude filtering did or did not run.

### 9.3. At Runtime

Create an endpoint observing two non-sensitive values:

~~~java
package com.example.config;

import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ConfigDemoController {

    private final Environment environment;

    public ConfigDemoController(Environment environment) {
        this.environment = environment;
    }

    @GetMapping("/config-demo")
    public Map<String, String> show() {
        Map<String, String> result = new LinkedHashMap<>();
        result.put("buildVersion",
                environment.getProperty("app.build-version", "unknown"));
        result.put("remoteUrl",
                environment.getProperty("app.remote-url", "unknown"));
        return result;
    }
}
~~~

Start:

~~~bash
REMOTE_URL=https://staging.example.invalid java -jar app.jar
~~~

Call:

~~~bash
curl http://localhost:8080/config-demo
~~~

Illustrative response:

~~~json
{
  "buildVersion": "1.8.0",
  "remoteUrl": "https://staging.example.invalid"
}
~~~

Stop the application and run **the same artifact** with a different variable:

~~~bash
REMOTE_URL=https://production.example.invalid java -jar app.jar
~~~

Response:

~~~json
{
  "buildVersion": "1.8.0",
  "remoteUrl": "https://production.example.invalid"
}
~~~

This is visual proof that **version was fixed at build time**, while **remoteUrl is decided at runtime**.

When inspecting the JAR directly, Spring Boot executable JAR resources usually sit under **BOOT-INF/classes/**. Tools like **jar tf** list contents; how you extract or view file contents depends on your OS and available tools. What matters is checking the packaged copy, not just the source copy.

## 10. Practical Configuration Scope and Use Cases

### 10.1. Values That Should Be Defined at Build Time

Examples:

- Module or artifact version, e.g., **1.8.0**.
- Artifact/build name.
- Git commit SHA, **if** the pipeline has a clear mechanism supplying it.
- Build timestamp, **if** the build process needs this metadata.
- Compatibility metadata for the released package.

That information describes **the built artifact**, so it typically does not change when promoting the JAR across staging, UAT, and production.

Do not use resource filtering to "package" deployment passwords or tokens. Even if the source file only contains placeholders, the filtered file will hold real values and may persist in artifact repositories, CI caches, container image layers, or backups.

### 10.2. Values That Should Be Supplied at Runtime

Examples:

- Database URLs and connection pools.
- External API endpoints.
- Environment-specific timeouts/circuit breakers and retry thresholds.
- Feature flags configured at deploy time.
- Ports, log levels, namespaces, or account settings.
- Credentials/secrets from controlled runtime secret providers.

Those parameters describe **a specific run**. Keeping them out of the build lets you properly follow the **build once, deploy many** principle.

### 10.3. Cases Needing Both

For instance, an API sends a header containing the build version while calling an environment-dependent endpoint:

~~~properties
app.build-version=@project.version@
app.partner-url=${partner.url:https://sandbox-partner.example.invalid}
~~~

Runtime knows both values, yet their origins differ. This is completely normal as long as the team has a clear convention and build filtering does not touch runtime placeholders.

## 11. Do Not Confuse Maven POM Interpolation with Spring Placeholders

In **pom.xml**, Maven uses syntax like:

~~~xml
<version>${revision}</version>
~~~

This is Maven model/property interpolation when processing the POM, **not** Spring Environment property resolution of the application.

In an **application.properties** file filtered by Maven resources, the Spring Boot recommended syntax with **spring-boot-starter-parent** is:

~~~properties
app.version=@project.version@
~~~

Do not infer that because Maven understands **${project.version}** inside **pom.xml**, it should also process every **${...}** inside **application.yml**. Two files, two placeholder systems, and two different purposes.

An unreplaced **@project.version@** in post-build resources usually means **filtering was not applied properly** or the token lacked matching build data; Spring Boot does not inherently know **@project.version@** is Maven syntax.

## 12. When to Use Profiles vs. Build Filtering?

Spring Boot supports **application-dev.yml**, **application-prod.yml**, and other profiles. These files are evaluated when the application runs based on active profiles:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

**Profiles** are part of runtime Config Data. If you package both **application-dev.yml** and **application-prod.yml** in the same JAR, selecting profile files happens at runtime, **not** because Maven/Gradle "compiled" those two profiles into one value.

Comparison:

~~~text
Build filtering:
src/main/resources -> substitute build tokens -> artifact

Spring profile:
artifact + spring.profiles.active -> select runtime Config Data
~~~

Thus, an **application-prod.yml** file can contain runtime placeholders like:

~~~yaml
app:
  endpoint: "${partner.prod-url:https://default.example.invalid}"
~~~

and the value of **partner.prod-url** can still come from environment variables or external config when production runs.

Avoid building a separate JAR per environment just to bake endpoints into configuration files at build time. That makes it harder to prove all environments are running **the exact same tested artifact**.

## 13. Resource Filtering in CI/CD and Reproducibility

A pipeline typically has steps:

~~~text
Source code
  |
  v
Build + unit tests
  |
  v
Artifact registry (app.jar / Docker image)
  |
  +----------------+
  |                |
  v                v
Staging          Production
  |                |
  v                v
Runtime env      Runtime env
  |                |
  v                v
Spring resolves placeholders independently
~~~

If version **1.8.0** and commit SHA are embedded at build time, they should stay identical between staging and production for the same artifact.

Conversely, if the pipeline rebuilds the JAR before every deployment just to swap **db.url** or **partner.url** via Maven filtering, you have created **different artifacts**, even from the same source commit.

This distinction matters for:

- **Traceability:** identical artifact hashes across environments.
- **Rollback workflows:** redeploying an older artifact with the right configuration set.
- **Change management:** updating configuration does not require modifying source or rebuilding.
- **Security:** runtime secrets stay out of published artifacts.
- **Reproducibility:** immutable build metadata can be verified on the packaged output.

### 13.1. Be Careful with Caches and Build Logs

If a build script reads a secret and expands it into a resource, that secret can end up in:

- **target/classes** or **build/resources/main**.
- JAR or WAR archives.
- Docker image layers.
- Build caches or artifact caches.
- Plugin or CI/CD logs if accidentally printed.

Do not consider "not committing secrets to Git" sufficient if build filtering still embeds secrets into artifacts. Use environment variables, a Secret Manager, or runtime secret mounts.

## 14. Common Errors and How to Handle Them

### 14.1. Maven Leaves @project.version@ Untouched

**Symptom:**

~~~properties
app.build-version=@project.version@
~~~

appears literally in **target/classes/application.properties**.

**Common cause:** not inheriting from starter parent, resource filtering not enabled, or custom plugin config dropped the **@** delimiter.

**Resolution:** check resources and `maven-resources-plugin` configuration. If not using starter parent, explicitly set **filtering=true**, delimiter **@**, and **useDefaultDelimiters=false**, then rebuild.

### 14.2. Gradle Fails When Encountering Runtime Placeholders

**Symptom:** **processResources** fails while trying to evaluate **${remote.url:...}**.

**Cause:** Gradle's **expand(...)** processes **${...}** tokens via the Groovy template engine, whereas those tokens were meant for Spring.

**Resolution:** escape runtime placeholders in filtered files (**\${...}**) or filter a separate metadata file instead of filtering all application resources.

### 14.3. Changed Environment Variable Value Yet Nothing Updated

**Symptom:** changed **REMOTE_URL** after Java started, yet the endpoint value did not change.

**Cause:** the running process does not automatically pick up external environment changes, and beans may already have been bound when ApplicationContext initialized.

**Resolution:** restart the application with the new environment variable, or use an official refresh mechanism if dynamic runtime updates are required.

### 14.4. IDE Run Differs from Packaged Artifact Run

**Symptom:** **java -jar** shows the right version, yet running directly from source/resources shows **@project.version@**.

**Cause:** the IDE or run mode bypassed resource processing or is loading source resources instead of filtered output.

**Resolution:** check classpath and build steps for each run mode. For build metadata values, verify using the packaged artifact.

### 14.5. Treating Runtime Placeholders as Text Replacement in Source Files

**Symptom:** checking **src/main/resources** or inside the JAR still shows **${remote.url:...}**, leading to the conclusion Spring did not work.

**Cause:** Spring does not rewrite files; it resolves **the value when read** through Environment.

**Resolution:** inspect **Environment.getProperty(...)** or **@ConfigurationProperties** at runtime rather than checking only source file text.

### 14.6. Mixing Up @...@ and ${...} Syntax

**Symptom:** property returns literal **@project.version@** or **${buildVersion}**.

**Cause:** the token was meant for a different processor or lacked a matching value source.

**Resolution:** determine whether the token should be processed at build time or runtime. If build time, check output files after processResources; if runtime, check PropertySources and key names.

### 14.7. Using Build Filtering to Hide Secrets

**Symptom:** source only has **@db.password@**, yet after build **application.properties** contains the real password.

**Cause:** filtering substituted the real value and packaged it into the artifact.

**Resolution:** move secrets to a runtime provider; revoke exposed credentials, replace affected artifacts/caches, and audit the pipeline per security policy.

### 14.8. Accidentally Filtering Binary Files

**Symptom:** resources like images, certificates, or compressed archives are corrupted after build.

**Cause:** filtering operates on bytes/text with assumptions unsuitable for binary resources.

**Resolution:** filter only selected text files; separate binary assets into an unfiltered resource set.

## 15. Practice: Identifying Who Substitutes Placeholders

### Exercise A — Runtime Placeholders Without Rebuilding

1. Create **application.properties** containing **app.remote-url=${remote.url:https://default.example.invalid}**.
2. Write a bean reading **Environment.getProperty("app.remote-url")**.
3. Build the JAR.
4. Run once with **REMOTE_URL=https://staging.example.invalid**.
5. Stop and run a second time with **REMOTE_URL=https://production.example.invalid**.

**Observation target:** the exact same JAR receives different URLs across the two runs.

### Exercise B — Maven Filtering Injecting Build Version

1. Use a Maven project with **spring-boot-starter-parent** and version **1.8.0**.
2. Add **app.build-version=@project.version@** to the config file.
3. Run **./mvnw clean package**.
4. Inspect **target/classes/application.properties**.
5. Read the property value when running the JAR.

**Observation target:** the **@project.version@** token became **1.8.0** in the post-build file; changing typical environment variables does not alter the JAR bytes.

### Exercise C — Gradle Filtering Metadata Only

1. Create **build-meta.properties** with **app.build-version=${buildVersion}**.
2. Use **filesMatching('build-meta.properties') { expand(buildVersion: project.version.toString()) }**.
3. Keep runtime placeholders in **application.properties** and import **classpath:build-meta.properties**.
4. Build with **./gradlew bootJar**.
5. Check **build/resources/main/** and run the app with environment variables.

**Observation target:** build metadata is injected before packaging, while Spring placeholders stay intact until runtime.

### Exercise D — Identifying Conflicts

1. On an experimental branch, enable Gradle **expand(project.properties)** on an **application.properties** containing **${remote.url:...}**.
2. Observe the build failing or behaving unexpectedly.
3. Switch to filtering a separate metadata file or escaping runtime tokens.
4. Rebuild and compare resource outputs.

**Observation target:** two placeholder systems sharing syntax can compete to process tokens; clear boundary conventions are required.

### Exercise E — Classifying Configuration Data

For the following keys, decide whether they belong at build time or runtime:

| Key | Recommended classification | Reason |
| --- | --- | --- |
| **app.build-version** | Build-time | Describes the artifact |
| **app.git-commit** | Build-time, if supplied by pipeline | Describes the artifact's source |
| **spring.datasource.url** | Runtime | Varies by deployment environment |
| **spring.datasource.password** | Runtime, with secret controls | Secrets should not be packaged |
| **app.partner-url** | Runtime | Depends on where the app runs |
| **app.request-timeout** | Runtime | Tunable per environment |
| **app.build-timestamp** | Build-time, if needed | Belongs to build info |

## 16. Key Takeaways

- **Spring placeholders ${...}** resolve through **Environment** at runtime; they do not modify packaged files.
- **Maven/Gradle resource filtering** modifies resource contents during the build phase; substituted values live inside the output/artifact.
- With **spring-boot-starter-parent**, **@project.version@** tokens keep build metadata distinct from runtime **${...}** placeholders.
- With **Gradle expand**, watch for **${...}** syntax collisions; escape Spring tokens in filtered files or use a separate metadata file.
- Values **invariant per artifact** belong at build time; values **varying by environment** belong at runtime.
- Changing an environment variable while a process is running usually does not update already-bound beans.
- Never filter real secrets into JARs or container images.
- To check **which stage substituted a value**, inspect files in **target/classes** or **build/resources/main**, then check runtime values from **Environment**.

**Official references:**

- Spring Boot 3.3 — Externalized Configuration, *Property Placeholders* section: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot — *How-to: Properties and Configuration*, *Automatically Expand Properties at Build Time* section: https://docs.spring.io/spring-boot/how-to/properties-and-configuration.html
- Maven Resources Plugin — Filtering: https://maven.apache.org/plugins/maven-resources-plugin/examples/filter.html
- Gradle User Manual — Process resources and copy/expand: https://docs.gradle.org/current/dsl/org.gradle.api.tasks.Copy.html