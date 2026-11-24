# Metadata for Nested Types and `@NestedConfigurationProperty` in Spring Boot

## 1. Problem This Lesson Solves

Spring Boot supports binding structured configuration from `application.yaml`, `application.properties`, environment variables, and command-line arguments into Java objects via `@ConfigurationProperties`. A configuration group often has multiple levels:

```yaml
portal:
  title: "Metadata Lab"
  http:
    host: "127.0.0.1"
    port: 8088
  mail:
    host: "mail.example.test"
    port: 2525
```

The application can read both `portal.http.host` and `portal.mail.host`. However, if `http` uses a nested record declared **inside** the parent record, while `mail` uses a record in a **separate Java file**, the IDE sometimes suggests the `portal.http.*` group completely while missing `portal.mail.*`. The cause may lie in **compile-time generated configuration metadata**, not in the runtime binding process itself.

Spring Boot provides the annotation processor:

```text
org.springframework.boot:spring-boot-configuration-processor
```

to generate the metadata file:

```text
META-INF/spring-configuration-metadata.json
```

Metadata lets IDEs and development tools know property names, Java types, descriptions, defaults, deprecation, and value suggestions. The `@NestedConfigurationProperty` annotation tells the processor to recognize a property whose **child type resides outside the parent class/record** as a nested group to explore, rather than a scalar value.

After this lesson, you will be able to:

1. Clearly distinguish **runtime configuration** from **configuration metadata**.
2. Understand the `groups`, `properties`, and `hints` structure of JSON metadata.
3. Configure Gradle/Maven to run the annotation processor.
4. Write nested records/classes automatically recognized by the processor.
5. Use `@NestedConfigurationProperty` on record components or fields with standalone child types.
6. Explain why the annotation does not replace `@ConfigurationProperties`, constructor binding, or Bean Validation.
7. Know metadata limitations with `List`, `Map`, and dynamic keys/indices.
8. Recognize the effect of the annotation with Spring AOT and GraalVM native image.
9. Run a Java 21, Spring Boot 3.3, Gradle example and compare metadata against values created by the Binder.
10. Diagnose missing autocomplete, binding errors, or metadata build failures without mixing them up.

**Context:** Java 21 and Spring Boot 3.3.x. Hosts and labels in examples are simulated data. This lesson belongs to the **Configuration Metadata** group of the **Spring Boot Externalized Configuration** topic.

## 2. How Does Metadata Differ from Runtime Data?

Imagine a module has a record:

```java
@ConfigurationProperties(prefix = "portal")
public record PortalProperties(String title) {}
```

In the development environment:

```yaml
portal:
  title: "Development"
```

In production, an environment variable may provide another value. The runtime Binder uses `PropertySource` precedence order to pick the **effective value**. Metadata merely describes that `portal.title` is a supported configuration key of type `String`.

| Question | Runtime binding | Configuration metadata |
| --- | --- | --- |
| Which title is the app currently using? | `Environment`, Binder, runtime sources | Does not decide |
| Does the dev file override the base file? | Yes, by profile and precedence | Does not decide |
| What type does `title` have? | Based on Java component | Can describe `java.lang.String` |
| Does the IDE suggest `portal.title`? | Not directly | Metadata helps the IDE |
| Which keys are in group `portal.http`? | Binder can bind child objects | Processor can list group/properties |
| Is there a business default? | Code/runtime config decides | Metadata can describe a detected default |
| When is the file generated/evaluated? | Loads config at app startup | Generated at compile time |
| Does it contain real secrets? | Depends on runtime sources | Should not contain secrets; can leak defaults if code uses secrets as constants |

**Core point:** a metadata file is not another `application.yaml`. It does not inject `portal.mail.host` into `Environment`, does not open servers, does not register beans, and does not verify access permissions.

Because metadata is mainly a contract for tooling, a JVM application **can bind configuration properly even without metadata**. The GraalVM native image build case has an exception regarding AOT reflection hints, which is explained separately in section 17.

### 2.1. What Benefits Does Metadata Bring to Library Users?

A Spring Boot starter often has dozens of configuration properties. Users only need to type in the IDE:

```properties
my.starter.
```

and the IDE can suggest valid keys if the dependency JAR contains appropriate metadata. They do not have to read all of the starter's source code to guess field names.

Therefore, if your module is shared across multiple projects, complete metadata is an important part of the integration experience. It **supplements** reference documentation and integration tests rather than replacing them.

## 3. Format of `spring-configuration-metadata.json`

Spring Boot standardizes three main information groups:

```json
{
  "groups": [],
  "properties": [],
  "hints": []
}
```

- `groups`: namespaces/nested groups, such as `portal`, `portal.http`, `portal.mail`.
- `properties`: concrete properties with full names, such as `portal.http.port`.
- `hints`: value suggestions and providers for a property, used by input-assisting tools.

**Abbreviated illustrative** example (not a promise about every optional attribute emitted by the processor):

```json
{
  "groups": [
    {
      "name": "portal",
      "type": "dev.example.metadata.PortalProperties"
    },
    {
      "name": "portal.http",
      "type": "dev.example.metadata.PortalProperties$Http"
    },
    {
      "name": "portal.mail",
      "type": "dev.example.metadata.Mail"
    }
  ],
  "properties": [
    {
      "name": "portal.title",
      "type": "java.lang.String"
    },
    {
      "name": "portal.http.host",
      "type": "java.lang.String"
    },
    {
      "name": "portal.http.port",
      "type": "java.lang.Integer"
    },
    {
      "name": "portal.mail.host",
      "type": "java.lang.String"
    },
    {
      "name": "portal.mail.port",
      "type": "java.lang.Integer"
    }
  ],
  "hints": []
}
```

Actual output may also include `sourceType`, `sourceMethod`, `description`, `defaultValue`, `deprecation`, and other fields. Entry ordering, type formatting, and optional fields depend on Java sources and the processor. When inspecting metadata, **compare the necessary property and group names** rather than relying on byte-for-byte sample JSON.

### 3.1. A Group Is Not Necessarily a Scalar Property

Group:

```text
portal.mail
```

indicates there is a group of properties underneath, such as:

```text
portal.mail.host
portal.mail.port
```

It does not inherently mean you can write:

```properties
portal.mail=mail.example.test:2525
```

and expect the Binder to automatically parse that string into a whole `Mail` object. To bind a special scalar string into a complex object, a suitable converter is required. Metadata groups and runtime converters are two separate mechanisms.

### 3.2. `description` and `defaultValue`

A property metadata entry may contain:

```json
{
  "name": "portal.http.port",
  "type": "java.lang.Integer",
  "description": "Port of the demonstration HTTP listener."
}
```

`description` helps the IDE explain the property's meaning. `defaultValue` is only generated when the processor recognizes a default from code or manual metadata sources; **having a metadata default alone does not mean the Binder reads this JSON to supply a runtime default**.

Therefore, actual defaults must be designed in base configuration, field initializers, constructor binding `@DefaultValue`, or another valid runtime mechanism, not created by metadata.

### 3.3. `hints` Is Not Validation

Example:

```json
{
  "hints": [
    {
      "name": "portal.mode",
      "values": [
        {"value": "simple"},
        {"value": "advanced"}
      ]
    }
  ]
}
```

This is a suggestion for tools. It does not automatically reject `"other"`. When runtime only permits `simple` or `advanced`, you need an enum, validation, or a corresponding converter.

## 4. Processor Auto-Discovery of Nested Classes and Nested Records

Consider a root record containing an `Http` type inside it:

```java
package dev.example.metadata;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "portal")
public record PortalProperties(
        String title,
        Http http
) {
    public record Http(String host, int port) {}
}
```

The annotation processor recognizes `Http` as a **nested type** declared inside the root and can generate the group:

```text
portal.http
```

and properties:

```text
portal.http.host
portal.http.port
```

`@NestedConfigurationProperty` is not needed for `http` in this situation.

YAML:

```yaml
portal:
  title: "Metadata Lab"
  http:
    host: "127.0.0.1"
    port: 8088
```

Corresponding Java:

```java
String bindHost = properties.http().host();
int bindPort = properties.http().port();
```

In Java, a nested record is a **Java type**; each `Http` is an object with its own data. It is not equivalent to a **static field** injected with configuration values. Avoiding `@Value` on static fields is a separate matter.

### 4.1. Nested JavaBean Classes

The same metadata mechanism can recognize a static nested class:

```java
@ConfigurationProperties(prefix = "legacy")
public class LegacyProperties {

    private Server server = new Server();

    public Server getServer() {
        return server;
    }

    public void setServer(Server server) {
        this.server = server;
    }

    public static class Server {
        private String host;
        private int port;

        public String getHost() { return host; }
        public void setHost(String host) { this.host = host; }

        public int getPort() { return port; }
        public void setPort(int port) { this.port = port; }
    }
}
```

The processor can discover `legacy.server.host` and `legacy.server.port`. Meanwhile, the runtime Binder requires the object to have appropriate instantiation and accessors. **Metadata discovery does not generate setters for your JavaBean.**

Prefer `static nested class` or nested record when possible, since non-static inner classes hold a reference to the outer instance and are more complicated for construction/binding.

## 5. Child Types Outside the Root: When the Annotation Is Needed

Suppose there is a separate `Mail` record in `Mail.java`:

```java
package dev.example.metadata;

public record Mail(
        String host,
        int port
) {}
```

The root uses:

```java
@ConfigurationProperties(prefix = "portal")
public record PortalProperties(
        String title,
        Mail mail
) {}
```

`Mail` **is not located inside** the root `PortalProperties`. When generating metadata, the processor does not expand every external class type into nested groups by default; they might be value objects converted from a scalar. Thus, the processor needs a signal about the role of the `mail` property.

Use:

```java
import org.springframework.boot.context.properties.NestedConfigurationProperty;

@ConfigurationProperties(prefix = "portal")
public record PortalProperties(
        String title,
        @NestedConfigurationProperty Mail mail
) {}
```

The annotation tells the processor to interpret:

```text
portal.mail
    |
    +-- portal.mail.host
    +-- portal.mail.port
```

rather than treating `mail` as a single `Mail` value unit without exploring its components.

### 5.1. Valid Placement Targets in Spring Boot 3.3

The 3.3 API of `@NestedConfigurationProperty` targets:

- `FIELD`.
- `RECORD_COMPONENT`.

Therefore:

**Correct for records:**

```java
public record PortalProperties(
        @NestedConfigurationProperty Mail mail
) {}
```

**Correct for POJO fields:**

```java
@NestedConfigurationProperty
private Mail mail;
```

**Not the intended placement when put on the `Mail` class** as a class-level annotation, because the annotation specifies that a **property in the root** is treated as a nested group.

API docs for newer Spring Boot versions may add other targets; when using Boot 3.3, follow the annotation targets of 3.3.

### 5.2. `@NestedConfigurationProperty` Does Not Register Beans

This annotation does not replace:

```java
@ConfigurationProperties(prefix = "portal")
```

and does not register the root bean in the context. The root must be registered by a valid mechanism, for example:

```java
@ConfigurationPropertiesScan
```

or:

```java
@EnableConfigurationProperties(PortalProperties.class)
```

The `Mail` object in the example is a **nested value object** constructed as a component of the root. There is no need to place `@Component` on `Mail` just to make it a nested object.

### 5.3. Does the Annotation Change JVM Binding?

Spring Boot 3.3 Javadoc explicitly notes that `@NestedConfigurationProperty` **has no direct impact on the binding process**. A `Mail` record outside the root can still be constructed properly by the JVM Binder from `portal.mail.host` and `portal.mail.port` if the Java types and configuration are valid.

Therefore:

- **Missing metadata** does not prove runtime binding will definitely fail.
- **Having metadata** does not prove the root bean has been successfully created.
- **Adding the annotation** does not alter source selection, switch profiles, generate runtime defaults, or open permissions.

There is one important exception for AOT/native images explained in section 17. It concerns **structure discovery to generate reflection hints**, not changing JVM binding rules.

## 6. Comparing Declaration Styles

| Java Type | Configuration Role | Annotation Needed for Metadata |
| --- | --- | --- |
| `PortalProperties.Http` nested record | Group `portal.http` | Usually inferred automatically |
| `PortalProperties.Http` static nested POJO | Group `portal.http` | Usually inferred automatically |
| `Mail` record in separate file | Group `portal.mail` | Should be added on the record component |
| `ExternalMail` POJO outside root | Child group belonging to root | Should be added on the field |
| `Duration timeout` | Converted scalar | No nested annotation needed |
| `URI baseUrl` | Converted scalar | No nested annotation needed |
| `List<Mail> providers` | Collection | Annotation does not enumerate each index |
| `Map<String,Mail> providers` | Map | Annotation does not enumerate each dynamic key |
| `String code` with external custom converter | Scalar | Do not turn into a group if contract is scalar |

Thus, the decision to use the annotation must be based on **the property's semantics**: does it represent a group of multiple child properties or a single value?

## 7. `List` and `Map` Do Not Automatically Generate Per-Element Metadata

A model:

```java
@ConfigurationProperties(prefix = "portal")
public record PortalProperties(
        List<Mail> providers,
        Map<String, Mail> mailboxes
) {}
```

can receive:

```yaml
portal:
  providers:
    - host: "first.example.test"
      port: 2525
    - host: "second.example.test"
      port: 2526
  mailboxes:
    support:
      host: "support.example.test"
      port: 2527
    alerts:
      host: "alerts.example.test"
      port: 2528
```

Runtime can resolve keys such as:

```text
portal.providers[0].host
portal.providers[1].port
portal.mailboxes.support.host
portal.mailboxes.alerts.port
```

However, metadata is a static model. The processor typically generates representative properties:

```text
portal.providers
portal.mailboxes
```

with generic types, rather than declaring every index `0`, `1`, `2`, ... or every possible map key.

Illustrative shape:

```json
{
  "name": "portal.providers",
  "type": "java.util.List<dev.example.metadata.Mail>"
}
```

`@NestedConfigurationProperty` **does not act on Collections and Maps to make them generate per-index/key metadata**: Spring Boot already recognizes these container types through the type system.

Therefore, do not add the annotation to `List<Mail>` expecting the JSON file to contain `portal.providers[0].host`. IDEs may inspect generic types themselves to offer richer suggestions, though that depends on the tool.

### 7.1. Special Map Keys Are a Different Binding Concern

For map keys containing slashes, you can use:

```yaml
portal:
  labels:
    "[/health/ready]": "internal"
```

Bracket notation preserves special characters in keys when the Binder processes property names. This is an issue of **runtime key path syntax**, not nested metadata annotations.

## 8. Configuring the Gradle Annotation Processor

The metadata processor must be on the annotation processing path when the Java compiler runs.

`settings.gradle`:

```groovy
rootProject.name = 'nested-metadata-lab'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'dev.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

The decisive line:

```groovy
annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
```

`implementation` is for runtime code, while `annotationProcessor` is the Java compilation configuration so the processor gets invoked. Do not merely add the processor to a dependency not participating in the annotation-processing path and expect the metadata file to appear.

Use the project's Gradle Wrapper (`gradlew`, `gradlew.bat`) generated by Spring Initializr. If the repository uses a version catalog or convention plugins, follow the repository's dependency management setup.

### 8.1. Maven Equivalent

In a Maven project using Spring Boot dependency management, you can declare:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
```

Depending on `maven-compiler-plugin` and JDK setup, annotation processor paths may be declared explicitly. What matters is that the processor **actually runs in the module containing the `@ConfigurationProperties` source**, rather than merely appearing as a dependency in another module.

## 9. Complete Lab Project

Structure:

```text
nested-metadata-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
└── src/
    ├── main/
    │   ├── java/dev/example/metadata/
    │   │   ├── MetadataApplication.java
    │   │   ├── PortalProperties.java
    │   │   └── Mail.java
    │   └── resources/
    │       └── application.yaml
    └── test/
        └── java/dev/example/metadata/
            ├── PortalPropertiesTest.java
            └── GeneratedMetadataTest.java
```

The application runs as a console app without needing a database, HTTP server, or Kubernetes. It demonstrates a root record, an auto-discovered nested record, and an external record using the annotation.

### 9.1. `PortalProperties.java`

```java
package dev.example.metadata;

import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.NestedConfigurationProperty;

/**
 * Configuration for a small portal application.
 *
 * @param title public display title
 * @param http HTTP listener options
 * @param mail mail delivery options
 * @param regions configured region codes
 * @param labels non-sensitive labels
 */
@ConfigurationProperties(prefix = "portal")
public record PortalProperties(
        String title,
        Http http,
        @NestedConfigurationProperty Mail mail,
        List<String> regions,
        Map<String, String> labels
) {
    /**
     * HTTP options belonging to the portal configuration.
     *
     * @param host demonstration bind address
     * @param port demonstration listener port
     */
    public record Http(
            String host,
            int port
    ) {}
}
```

In actual code, the `*/` lines when rendered in a README are replaced with valid Javadoc closing syntax.

**Explanation:**

- Root is annotated with `@ConfigurationProperties(prefix="portal")`.
- `Http` resides inside the root so the processor auto-discovers the `portal.http` group.
- `Mail` is in a separate file so the `mail` component carries `@NestedConfigurationProperty`.
- `regions` and `labels` are a collection/map; no nested annotation is placed on them.
- The root record has camelCase Java components if multi-word; YAML uses canonical kebab-case names.
- For Java records, Javadoc on the record declaration uses `@param` so the processor can extract descriptions for each component.

### 9.2. `Mail.java`

```java
package dev.example.metadata;

/**
 * Mail settings for the training application.
 *
 * @param host host of the test mail service
 * @param port port of the test mail service
 */
public record Mail(
        String host,
        int port
) {}
```

The `Mail` record does not need to be a separate Spring bean. When the Binder creates `PortalProperties`, it can instantiate a `Mail` instance as a component inside the root.

If `Mail` resides in a precompiled dependency rather than sources currently being processed, the annotation processor may not have access to its Javadoc/source metadata. When additional descriptions are needed, consider manual metadata.

### 9.3. `MetadataApplication.java`

```java
package dev.example.metadata;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@ConfigurationPropertiesScan
public class MetadataApplication {

    public static void main(String[] args) {
        SpringApplication.run(MetadataApplication.class, args);
    }

    @Bean
    ApplicationRunner report(PortalProperties settings) {
        return args -> {
            System.out.println("=== NESTED METADATA LAB ===");
            System.out.println("title = " + settings.title());
            System.out.println("http.host = "
                    + settings.http().host());
            System.out.println("http.port = "
                    + settings.http().port());
            System.out.println("mail.host = "
                    + settings.mail().host());
            System.out.println("mail.port = "
                    + settings.mail().port());
            System.out.println("regions = " + settings.regions());
            System.out.println("labels = " + settings.labels());
        };
    }
}
```

`@ConfigurationPropertiesScan` registers the root record so the Binder constructs the configuration bean. It **differs** from `spring-boot-configuration-processor`: scanning operates during Spring application runtime; the processor runs during compile time and emits JSON.

Do not use a metadata file as proof that the Bean is registered; and do not use successful Bean injection as proof that the IDE received the JSON metadata.

### 9.4. `application.yaml`

```yaml
spring:
  main:
    web-application-type: none

portal:
  title: "Metadata Lab"
  http:
    host: "127.0.0.1"
    port: 8088
  mail:
    host: "mail.example.test"
    port: 2525
  regions:
    - ap-southeast-1
    - eu-west-1
  labels:
    team: education
    stage: sandbox
```

Meaningful property paths:

```text
portal.title
portal.http.host
portal.http.port
portal.mail.host
portal.mail.port
portal.regions
portal.labels
```

All values are solely for lesson purposes and establish no real connection to `mail.example.test`. Sample projects should never put secrets or credentials into metadata, logs, or repositories.

## 10. Trying Runtime Binding

macOS/Linux:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Lines to observe:

```text
=== NESTED METADATA LAB ===
title = Metadata Lab
http.host = 127.0.0.1
http.port = 8088
mail.host = mail.example.test
mail.port = 2525
regions = [ap-southeast-1, eu-west-1]
labels = {team=education, stage=sandbox}
```

Print order of `Map` entries may vary; what matters is the content of each key.

Run again with arguments:

```bash
./gradlew bootRun --args='--portal.mail.host=smtp.example.test --portal.mail.port=3025'
```

PowerShell:

```powershell
.\gradlew.bat bootRun --args="--portal.mail.host=smtp.example.test --portal.mail.port=3025"
```

Expected:

```text
mail.host = smtp.example.test
mail.port = 3025
```

CLI arguments can override YAML for those two keys in standard setups. Metadata does not change when you run with different CLI values, because metadata describes the **schema**, not a value snapshot.

## 11. Building and Inspecting Metadata JSON

Recompile with Gradle:

macOS/Linux:

```bash
./gradlew clean compileJava
```

Windows:

```powershell
.\gradlew.bat clean compileJava
```

In a standard Java/Gradle project, the annotation processor writes the file at:

```text
build/classes/java/main/META-INF/spring-configuration-metadata.json
```

If Gradle's class output directory is customized, the location may differ. In Maven, the location is typically:

```text
target/classes/META-INF/spring-configuration-metadata.json
```

Read the file:

Bash:

```bash
cat build/classes/java/main/META-INF/spring-configuration-metadata.json
```

PowerShell:

```powershell
Get-Content 'build/classes/java/main/META-INF/spring-configuration-metadata.json' -Raw
```

Look for group/property names:

```text
portal
portal.http
portal.mail
portal.title
portal.http.host
portal.http.port
portal.mail.host
portal.mail.port
portal.regions
portal.labels
```

Some names are groups; some are properties. `portal.regions` and `portal.labels` usually have collection/map type metadata rather than listing every runtime key/index.

Quick search with Bash:

```bash
grep -n '"name"' \
  build/classes/java/main/META-INF/spring-configuration-metadata.json
```

Or PowerShell:

```powershell
Select-String -Path 'build/classes/java/main/META-INF/spring-configuration-metadata.json' `
  -Pattern 'portal.http|portal.mail|portal.regions|portal.labels'
```

**Do not compare the full JSON using a literal string** without good reason: the processor may add `sourceType`, `description`, or order entries differently. Focus on the essential schema.

### 11.1. Metadata File Inside an Executable JAR

After:

```bash
./gradlew bootJar
```

application metadata usually resides in the executable JAR under:

```text
BOOT-INF/classes/META-INF/spring-configuration-metadata.json
```

Metadata of a regular dependency JAR sits at:

```text
META-INF/spring-configuration-metadata.json
```

Archive paths differ due to Spring Boot's executable JAR layout. IDEs typically use metadata in artifacts/dependencies once aware of the project classpath. If metadata is missing from the JAR, inspect build and packaging rather than only Java code.

## 12. Experiment A: Auto-Inferred Nested Record

In `PortalProperties`:

```java
Http http
```

has no nested annotation, yet because `Http` is declared **inside** the root, the processor can generate `portal.http` along with `portal.http.host`/`portal.http.port`.

What to observe is the **metadata JSON** after compilation. The runner printing `http.host` properly proves runtime binding succeeded, but it does not directly verify metadata entries.

If you refactor `Http` from a nested record into `HttpSettings.java` in a separate file, you should review the annotation on the `http` component. This is a common scenario where IDE suggestions disappear after splitting code, even though the Java application still runs.

## 13. Experiment B: External Record and Annotation

In the root:

```java
@NestedConfigurationProperty Mail mail
```

the annotation gives the processor a clear signal about the `portal.mail` group.

On **an experimental copy**, you can temporarily remove the annotation and run:

```bash
./gradlew clean compileJava
```

Observe the metadata. Per discovery rules, types outside the root may not be collected as nested groups when lacking the annotation.

Then run on the JVM via:

```bash
./gradlew bootRun
```

If runtime still binds `Mail` successfully, that result is not a contradiction: the annotation does not alter standard JVM binding algorithms.

Restore the annotation so metadata has a clear structure and AOT/native images have sufficient discovery info. Do not edit `build/classes/.../spring-configuration-metadata.json` manually; it is a generated file and will be overwritten on the next compile.

## 14. Experiment C: `List`, `Map`, and Finite Metadata

With:

```java
List<String> regions,
Map<String, String> labels
```

the processor can generate:

```text
portal.regions
portal.labels
```

without pre-generating:

```text
portal.regions[0]
portal.regions[1]
portal.labels.team
portal.labels.stage
```

Such keys/indices may exist at runtime, but the set of possible values is dynamic. The nested annotation does not force the processor to enumerate infinite indices or map keys.

Therefore, if the IDE does not explicitly suggest `portal.regions[2]`, do not jump to the conclusion that the collection type failed to bind or lacks an annotation. Check the metadata type of `portal.regions` and test runtime with a typed `List<String>` bean.

## 15. Javadoc for `description`

For JavaBean fields, Javadoc on the field can be used to generate `description`. For **Java records**, Spring Boot guides documenting record components with `@param` in the record declaration's Javadoc, since records do not have explicit fields like traditional JavaBeans.

Example:

```java
/**
 * Outgoing mail configuration.
 *
 * @param host DNS host name of the outbound mail service
 * @param port TCP port for the outbound mail service
 */
public record Mail(String host, int port) {}
```

Good descriptions should:

- Clearly state what the property is used for.
- State units when it is a size, duration, or port.
- Be concise and meaningful.
- Never contain tokens, passwords, or real secret values.
- Not simply repeat the variable name in similar words.
- Clearly distinguish a demo setting from a production setting.

If a record is in a precompiled dependency, the consuming module's annotation processor cannot see the Javadoc source. For a property needing public documentation, consider adding supplementary metadata instead of directly editing generated artifacts.

### 15.1. Why Don't Descriptions Appear Automatically?

A field named `timeout` does not indicate whether it is connect time, read time, or total wait time. The processor cannot deduce business contracts from property names. Javadoc supplies info that Java names/types lack.

However, a description is still not validation: if a timeout must be positive, a constraint or other runtime rule is needed.

## 16. Manual Metadata and Hints

When the processor cannot extract descriptions/defaults on its own or when value suggestions are needed for the IDE, Spring Boot supports the file:

```text
src/main/resources/META-INF/additional-spring-configuration-metadata.json
```

Example:

```json
{
  "properties": [
    {
      "name": "portal.mail.host",
      "description": "Host name for the outbound mail service."
    }
  ],
  "hints": [
    {
      "name": "portal.mode",
      "values": [
        {
          "value": "simple",
          "description": "Use the minimal configuration."
        },
        {
          "value": "advanced",
          "description": "Enable advanced configuration options."
        }
      ]
    }
  ]
}
```

These descriptions/hints assist the IDE as authors enter configuration. `portal.mode` is an illustrative key for an option that might be declared separately in the application; **hints do not create runtime properties or validation**.

If a property has already been discovered by the processor, certain additional info can override descriptions, defaults, or deprecation in auto-generated metadata. If the property does not exist in source types, manual metadata can add an entry describing a key handled by another mechanism.

### 16.1. Gradle: Relationship Between `compileJava` and `processResources`

If you use additional metadata JSON, ensure the resource file is present when the annotation processor runs. Per Spring Boot guidance, you can add:

```groovy
tasks.named('compileJava') {
    inputs.files(tasks.named('processResources'))
}
```

For labs **without an additional file**, this part is unnecessary. Do not add extra tasks arbitrarily if the existing build already handles resources and annotation processing properly.

After adding the manual file, re-run:

```bash
./gradlew clean compileJava
```

and inspect the generated metadata to confirm the contents merged.

### 16.2. Defaults in Metadata Do Not Create Runtime Defaults

Suppose you add:

```json
{
  "properties": [
    {
      "name": "portal.mail.port",
      "defaultValue": 2525
    }
  ]
}
```

This information describes the default for the IDE, but the Binder **does not read metadata JSON as a runtime property source**. To give `Mail.port` a default of 2525, design it in base configuration files, constructor defaults per Spring Boot mechanisms, or an explicit runtime binding approach.

Do not use metadata to store secrets or production endpoints that must stay hidden.

## 17. Spring AOT and GraalVM Native Image

This is an important detail to state accurately when saying the annotation does not change binding:

- On a standard JVM, `@NestedConfigurationProperty` does not directly control the Binder.
- Spring Boot AOT analyzes configuration types to generate reflection hints for native images.
- When a nested type **is not an inner/nested class**, Spring Boot 3.3 instructs using `@NestedConfigurationProperty` to help AOT discover the child type.
- Missing the annotation in this case can cause the nested property to fail to bind in a native image, even when a JVM test passes.

Example:

```java
@ConfigurationProperties(prefix = "portal")
public record PortalProperties(
        String title,
        @NestedConfigurationProperty Mail mail
) {}
```

The annotation is placed on the **record component**. For constructor-bound POJOs, place it on the appropriate field per the Spring Boot 3.3 API. When building a native image, inspect generated reflection hints and run actual startup/native tests.

**Do not claim** the annotation is "strictly for IDEs in all build modes." It is a structural signal, and the AOT path can depend on that signal.

On the other hand, the annotation does not replace runtime hints for arbitrary reflection in other libraries. It serves nested configuration properties discovery, not a general reflection permission mechanism.

## 18. Integration Test for Runtime Binding

Create `src/test/java/dev/example/metadata/PortalPropertiesTest.java`:

```java
package dev.example.metadata;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "portal.title=From Test",
        "portal.http.port=9088",
        "portal.mail.host=mail.test.example",
        "portal.mail.port=3025"
})
class PortalPropertiesTest {

    @Autowired
    PortalProperties properties;

    @Test
    void bindsNestedObjects() {
        assertEquals("From Test", properties.title());

        assertNotNull(properties.http());
        assertEquals("127.0.0.1", properties.http().host());
        assertEquals(9088, properties.http().port());

        assertNotNull(properties.mail());
        assertEquals("mail.test.example",
                properties.mail().host());
        assertEquals(3025, properties.mail().port());

        assertEquals("education",
                properties.labels().get("team"));
    }
}
```

Run:

```bash
./gradlew test
```

PowerShell:

```powershell
.\gradlew.bat test
```

The test shows that the Binder selected effective values from test properties and YAML to build `PortalProperties`. It **does not prove** the JSON metadata contains the required groups; a separate check is required.

### 18.1. Testing the Metadata File

Create `src/test/java/dev/example/metadata/GeneratedMetadataTest.java`:

```java
package dev.example.metadata;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;

class GeneratedMetadataTest {

    @Test
    void containsExpectedNestedNames() throws Exception {
        try (InputStream stream = getClass().getClassLoader()
                .getResourceAsStream(
                        "META-INF/spring-configuration-metadata.json")) {
            assertNotNull(stream,
                    "Configuration metadata resource is missing");

            String json = new String(
                    stream.readAllBytes(), StandardCharsets.UTF_8);

            assertTrue(json.contains("portal.http.host"));
            assertTrue(json.contains("portal.http.port"));
            assertTrue(json.contains("portal.mail.host"));
            assertTrue(json.contains("portal.mail.port"));
        }
    }
}
```

This test only checks name presence; it does not assert exact `groups` and `properties` arrays. To validate schema details, parse the JSON into objects and assert against the corresponding arrays.

If the project has multiple dependencies providing a resource named `spring-configuration-metadata.json`, loading via the classloader may pick up the wrong artifact. In that case, point the test at **the module's specific output file** instead of relying on a single resource name.

## 19. Categorizing Common Errors

### 19.1. IDE Does Not Suggest External Nested Type

**Symptom:** `portal.http.host` is suggested, while `portal.mail.host` is not.

**Likely cause:** The processor auto-detected nested `Http`, while external `Mail` lacks `@NestedConfigurationProperty`, or the metadata processor did not run properly.

**Resolution:** place the annotation on the `mail` component, check `annotationProcessor` in Gradle, recompile, inspect the JSON, and reload the project in the IDE if needed.

### 19.2. Metadata File Missing

**Symptom:** `compileJava` succeeds, yet `spring-configuration-metadata.json` is absent.

**Likely cause:** Processor not declared on the annotation-processing path, annotation processing disabled, or inspecting the wrong module/output directory.

**Resolution:** check the `annotationProcessor` dependency, run `./gradlew clean compileJava`, and inspect the right module class output. The IDE may still suggest built-in Spring Boot properties from other dependencies; that does not prove this module's metadata exists.

### 19.3. Metadata Exists, but Bean Does Not Bind

**Symptom:** IDE knows `portal.mail.host`, yet the `PortalProperties` bean is missing or has null values.

**Likely cause:** Root unregistered, YAML not loaded, wrong prefix, profile inactive, higher-precedence property source overriding, unconvertible type, or missing constructor/accessors.

**Resolution:** inspect `@ConfigurationPropertiesScan`/`@EnableConfigurationProperties`, Binder error messages, and runtime sources. Do not expect `@NestedConfigurationProperty` to fix those issues.

### 19.4. Runs on JVM, Fails on Native Image

**Symptom:** JVM integration test is green, yet native executable fails to bind a child type outside root.

**Likely cause:** AOT failed to discover the nested type and missed reflection hints.

**Resolution:** place the annotation on the field/record component, rebuild native/AOT, and inspect config types and the native startup path. Do not blame YAML when the type already binds cleanly on the JVM.

### 19.5. Annotated `List`, but JSON Lacks Indices

This is not an error: collections/maps are described by type. Actual indices and keys supplied by operators are not a finite set for the processor to emit in advance.

### 19.6. Default in JSON Has No Effect

Metadata describes; it does not supply runtime values. Defaults must be in actual config/binding or an explicit mechanism.

### 19.7. Missing Description for a Record Component

For records, check `@param` Javadoc. For types in precompiled dependencies, the processor may not see the source. If needed, add `additional-spring-configuration-metadata.json`.

### 19.8. Additional File Not Merged

Check the resource path, valid JSON syntax, compile/resources relationship, and the module containing the file. Do not manually edit generated metadata in `build/classes`, as it will be recreated.

### 19.9. Property Name Has Wrong Dot Hierarchy

`portal.mail-host` and `portal.mail.host` describe two different structures. Dots separate namespaces; hyphens separate words within a name segment. Keep canonical naming consistent across YAML, Java models, and metadata.

### 19.10. Duplicate Name in Metadata

The format can contain duplicate name entries when multiple source types expose the same prefix. Inspect type/source context instead of just counting `"name"` lines. However, in a reusable library, keep prefix ownership clear so consumers do not receive conflicting suggestions.

## 20. Quick Decision Table

| Scenario | Suitable Design | What to Verify? |
| --- | --- | --- |
| Nested record inside root | Keep nested record | JSON has child group |
| POJO static nested class | Clear getters/setters and nested type | Metadata and runtime |
| External record used as child object | `@NestedConfigurationProperty` on component | JSON group + AOT |
| External POJO field | Annotation on field | JSON + Binder |
| Collection | Properly typed `List<T>`/`Map<K,V>` | Collection metadata and binding |
| Scalar `Duration` | Standard conversion | Do not mark nested |
| Scalar `URI` | Standard conversion | Do not mark nested |
| Config object in a dependency | Metadata in owning module or supplemented | JAR contains JSON |
| Manual description/hint | Additional JSON | Merged into output |
| Native image | Annotation + AOT hints + native test | Do not test JVM only |

Use this table to choose the **right level of annotation** rather than annotating every field with a complex type.

## 21. Nested Configuration Implementation Checklist

1. Choose a clear prefix, such as `portal`.
2. List the expected schema: `portal.http.host`, `portal.mail.port`.
3. Choose nested record/class types for groups with fixed keys.
4. For types declared inside the root, leverage auto-discovery.
5. For types outside the root, annotate with `@NestedConfigurationProperty` at the reference site.
6. Do not use nested annotations to solve map/list indexing questions.
7. Register the root configuration properties properly.
8. Add the configuration processor to the annotation-processing path.
9. Provide helpful Javadoc, using `@param` for record components.
10. Recompile and inspect the metadata JSON file in the right module.
11. Inspect `groups` and `properties` separately to avoid confusing namespaces with scalars.
12. Run runtime tests to confirm the object graph binds.
13. Check precedence if runtime values differ from expectations.
14. For library/starter projects, verify metadata is packaged inside the JAR.
15. For GraalVM native builds, check AOT discovery and native executables.
16. Never put secrets into defaults, hints, or Javadoc.
17. Do not use metadata as runtime validation.
18. When refactoring schemas, keep tests to catch lost autocomplete or key renames.

## 22. Self-Practice Exercises

### Exercise A — Auto-Generating Groups

Given:

```java
@ConfigurationProperties(prefix = "reports")
public record ReportProperties(
        String title,
        Export export
) {
    public record Export(String format, String directory) {}
}
```

Predict which `groups` and `properties` the processor can generate. Why is a nested annotation not needed on `export`?

### Exercise B — Extracting Type to an External File

If you move `Export` into `ExportSettings.java`, update the root declaration so metadata still describes the keys:

```text
reports.export.format
reports.export.directory
```

Should the annotation be placed on the `ExportSettings` type or on the component using that type?

### Exercise C — Javadoc for Records

Write `@param` Javadoc for `ExportSettings(format, directory)` to describe expected value types. Why might writing only class-level Javadoc be insufficient for tools to understand each property?

### Exercise D — List of Objects

Given:

```java
List<Endpoint> endpoints
```

Predict why the JSON can contain `gateway.endpoints` without containing `gateway.endpoints[0].host`, `[1].host`. Explain why metadata is a finite static model.

### Exercise E — Testing Two Responsibilities

Write an integration test verifying Binder receives `portal.mail.port=3025`, and another test verifying metadata contains `portal.mail.port`. Why does the outcome of one test not imply the outcome of the other?

### Exercise F — Native Image

A record outside the root binds successfully on the JVM yet lacks values when running as a native image. List items to check: annotation placement, AOT generated hints, Java types, artifacts, source properties, and integration tests.

### Exercise G — Additional Hints

Create `additional-spring-configuration-metadata.json` supplying `portal.mode=simple|advanced` hints. Test that the final metadata file includes the hints. Explain why runtime still needs to validate `portal.mode` if it is a mandatory constraint.

### Exercise H — Refactoring Without Changing Schema

You have a `PortalProperties.Http` nested record and want to extract it into a standalone `HttpSettings` for reuse across modules. Design the new root so `portal.http.host` remains unchanged. What else must you verify besides ensuring the application starts?

## 23. Self-Check Questions

**1.** When and by which tool is metadata generated?

**2.** Is metadata a PropertySource from which the Binder reads runtime values?

**3.** What are the three main arrays of a metadata JSON file?

**4.** Does a nested record inside the root usually require `@NestedConfigurationProperty`?

**5.** Where must the annotation be placed when a record in a separate file is used as a child group?

**6.** What are the annotation's targets in Boot 3.3?

**7.** Why can the JVM still bind without adding the annotation?

**8.** When building a native image, what can omitting the annotation affect?

**9.** Does the annotation expand `List<Mail>` into metadata for `[0]`, `[1]`?

**10.** Can metadata be used in place of `@ConfigurationPropertiesScan`?

**11.** Is adding the processor to `implementation` always sufficient for Gradle to run it?

**12.** After `compileJava`, which file should be inspected?

**13.** For records, what is used to create descriptions for components?

**14.** When is `additional-spring-configuration-metadata.json` used?

**15.** Does `defaultValue` in metadata make the Binder automatically supply a runtime default?

**16.** Does missing IDE suggestions mean runtime binding definitely fails?

**17.** Does a `Duration` type need to be marked nested?

**18.** Why are both runtime tests and metadata tests needed when refactoring?

### Suggested Answers

1. At compile time, by the Spring Boot configuration annotation processor.
2. No.
3. `groups`, `properties`, `hints`.
4. Usually no, because the processor auto-detects nested types.
5. On the field or record component referencing that type.
6. `FIELD` and `RECORD_COMPONENT` in 3.3.
7. Because the annotation does not alter standard JVM binding algorithms.
8. AOT may miss reflection hints for external nested types.
9. No, collections/maps are described on their own.
10. No, metadata does not register beans.
11. No; use `annotationProcessor` with the Gradle Java plugin.
12. `META-INF/spring-configuration-metadata.json` in the module's class output.
13. `@param` Javadoc on the record declaration.
14. To supplement descriptions/defaults/hints when auto-discovery is insufficient.
15. No.
16. No, runtime must be checked separately.
17. No, `Duration` is a scalar with standard conversion.
18. They verify two independent responsibilities.

## 24. Applying to Real Projects

Architectural mindset of this lesson:

```text
SCHEMA DESCRIPTION FOR IDE

Java types + @ConfigurationProperties
              |
              +-- nested type inside root
              |       -> auto-discovered
              |
              +-- external nested type
              |       -> @NestedConfigurationProperty
              |
              +-- List / Map
              |       -> collection description
              |
              v
 spring-boot-configuration-processor
              |
              v
 META-INF/spring-configuration-metadata.json
              |
              v
       IDE / metadata tooling
```

The runtime path is:

```text
application.yaml / environment / CLI
                 |
                 v
             Environment
                 |
                 v
     @ConfigurationProperties Binder
                 |
                 v
         PortalProperties
                 |
        +--------+--------+
        |                 |
      Http               Mail
        |                 |
        +--------+--------+
                 |
                 v
          ApplicationRunner
```

Both paths share the Java schema yet solve two different problems. When IDE suggestions are missing, check the processor, annotation placement, and metadata JSON. When beans receive wrong values, check prefixes, property sources, conversion, profiles, and validation. When native images fail, additionally check AOT reflection hints.

**Conclusion:** `@NestedConfigurationProperty` is a signal for a property with an **external nested type**, helping Spring Boot recognize the group in metadata and supporting AOT. Place the annotation on the right field/record component, do not confuse it with bean registration or runtime defaults, and always keep metadata verification separate from binding verification.

### References

- [Spring Boot 3.3 — Configuration Metadata](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/index.html).
- [Spring Boot 3.3 — Metadata Format](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/format.html).
- [Spring Boot 3.3 — Annotation Processor](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/annotation-processor.html).
- [Spring Boot 3.3 — `@NestedConfigurationProperty` API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/NestedConfigurationProperty.html).
- [Spring Boot 3.3 — Advanced Native Image Topics](https://docs.spring.io/spring-boot/3.3/reference/packaging/native-image/advanced-topics.html).
