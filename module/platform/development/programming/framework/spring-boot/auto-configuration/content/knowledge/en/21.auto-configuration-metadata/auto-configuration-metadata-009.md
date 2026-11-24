# Inspecting Generated Metadata in the JAR and Supporting IDE Configuration Completion

**Topic:** Spring Boot Auto Configuration  
**Knowledge Area:** Metadata  
**Goal:** Generate configuration metadata for a Spring Boot library/starter, verify the metadata was generated at compile time and packaged into the JAR, and check that the IDE can suggest property names, types, descriptions, and valid values when users write `application.yml` or `application.properties`.

## 1. What Problem Does Configuration Metadata Solve?

Suppose the `acme-report-autoconfigure` library provides these settings:

```yaml
acme:
  report:
    enabled: true
    timeout: 2s
    max-attempts: 3
    output-format: json
```

Spring Boot can bind these values into a `@ConfigurationProperties` class. However, when users write YAML, the IDE does not automatically know for sure:

- Whether the `acme.report` prefix exists.
- That `enabled`, `timeout`, `max-attempts` are options supported by the library.
- The data type and unit of each value.
- Default values, meaning, or recommended values.
- Whether a property is deprecated and has a replacement key.

**Configuration metadata** is data describing properties so IDEs and development tools provide contextual assistance, such as autocomplete, documentation popups, value types, value suggestions, and deprecation warnings.

The standard metadata file resides in the JAR at:

```text
META-INF/spring-configuration-metadata.json
```

Most metadata is generated automatically at compile time by the `spring-boot-configuration-processor` annotation processor, based on `@ConfigurationProperties` classes/methods. For cases the processor cannot infer, the library can provide additional metadata.

Important point: metadata serves **development tooling**. It does not replace Binder, does not automatically register beans, does not make a property take effect at runtime, and does not automatically validate every value users enter. Runtime still needs code to bind/read and apply the corresponding property.

## 2. Three Components Not to Confuse

| Component | Role | Example |
| --- | --- | --- |
| `@ConfigurationProperties` | Declares configuration group and provides data for Spring Boot Binder | `ReportProperties` with prefix `acme.report` |
| `spring-boot-configuration-processor` | Reads source at compile time and generates metadata | Generates `META-INF/spring-configuration-metadata.json` |
| Spring Boot-capable IDE | Reads metadata to suggest and display documentation | Suggests `acme.report.max-attempts` in YAML |

Process:

```text
Java/Kotlin source with @ConfigurationProperties
                 |
                 v
spring-boot-configuration-processor
                 |
                 v
META-INF/spring-configuration-metadata.json
                 |
                 v
Packaged inside the library's JAR
                 |
                 v
Consuming application adds JAR as a dependency
                 |
                 v
IDE reads metadata and provides autocomplete
```

If the annotation processor does not run, Java classes can still compile and runtime Binder can still bind properties, but the JAR may lack metadata. Then the IDE may report “Cannot resolve configuration property” or fail to suggest the library's keys.

Conversely, a key appearing in metadata does not guarantee runtime code actually reads or binds it. Metadata describes the contract for tooling; the implementation must fulfill that contract.

## 3. What Information Groups Does Metadata Contain?

A `spring-configuration-metadata.json` file can have the following sections:

| Section | Meaning | Used for |
| --- | --- | --- |
| `groups` | Configuration group/prefix, typically tied to a type | Displaying namespace and context |
| `properties` | Name, type, description, source, and default of each key | Autocomplete and documentation |
| `hints` | Suggested values or providers supplying content | Suggestions for enum/string/class/bean/profile |
| `ignored` | Properties intentionally excluded from the metadata list | Preventing tools from advertising keys that should not be used |

Illustrative condensed example:

```json
{
  "groups": [
    {
      "name": "acme.report",
      "type": "com.acme.report.ReportProperties",
      "sourceType": "com.acme.report.ReportProperties"
    }
  ],
  "properties": [
    {
      "name": "acme.report.enabled",
      "type": "java.lang.Boolean",
      "description": "Enable or disable report integration.",
      "sourceType": "com.acme.report.ReportProperties",
      "defaultValue": false
    },
    {
      "name": "acme.report.timeout",
      "type": "java.time.Duration",
      "description": "Wait timeout for a single report call."
    }
  ],
  "hints": [
    {
      "name": "acme.report.output-format",
      "values": [
        { "value": "json" },
        { "value": "csv" }
      ]
    }
  ]
}
```

This is a condensed example to explain structure, not a verbatim output file. Real metadata can contain additional properties, source methods, defaults, deprecations, and other information.

Property names use the canonical lower-case dot-separated form: `acme.report.max-attempts`. IDEs may present keys in YAML or `.properties` syntax, but metadata stores the canonical name.

## 4. Generating Metadata Automatically with `@ConfigurationProperties`

The annotation processor detects classes and methods annotated with `@ConfigurationProperties`. For standard JavaBeans, the processor detects properties from getters/setters; for constructor binding or records, properties are determined from constructor parameters/record components per Spring Boot rules.

Java 17 example:

```java
package com.acme.report;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.report")
public class ReportProperties {

    /**
     * Enable or disable report integration.
     */
    private boolean enabled = false;

    /**
     * Maximum wait time for a single report call.
     */
    private Duration timeout = Duration.ofSeconds(2);

    /**
     * Total number of attempts, including the first attempt.
     */
    private int maxAttempts = 3;

    /**
     * Requested output format.
     */
    private String outputFormat = "json";

    /**
     * List of data regions to process.
     */
    private List<String> regions = new ArrayList<>();

    /**
     * Report processing strictness mode.
     */
    private Mode mode = Mode.STANDARD;

    public enum Mode {
        STANDARD,
        STRICT
    }

    public boolean isEnabled() {
        return this.enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public Duration getTimeout() {
        return this.timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }

    public int getMaxAttempts() {
        return this.maxAttempts;
    }

    public void setMaxAttempts(int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }

    public String getOutputFormat() {
        return this.outputFormat;
    }

    public void setOutputFormat(String outputFormat) {
        this.outputFormat = outputFormat;
    }

    public List<String> getRegions() {
        return this.regions;
    }

    public void setRegions(List<String> regions) {
        this.regions = regions;
    }

    public Mode getMode() {
        return this.mode;
    }

    public void setMode(Mode mode) {
        this.mode = mode;
    }
}
```

The processor can generate metadata for:

- Prefix/group `acme.report`.
- `acme.report.enabled` with type Boolean.
- `acme.report.timeout` with type Duration.
- `acme.report.max-attempts` with type Integer.
- `acme.report.output-format` with type String.
- `acme.report.regions` with type Collection.
- `acme.report.mode` with type enum.

Javadoc placed on fields is used as the property description. Write short, clear, configurator-focused descriptions: state meaning, unit, impact scope, or key limitations. Avoid putting implementation details such as private variable names, internal algorithms, or helper classes into documentation.

### 4.1. How Are Default Values Inferred?

The annotation processor uses heuristics to read defaults from the source model. Static defaults such as:

```java
private boolean enabled = false;
private int maxAttempts = 3;
```

can be included in metadata. Defaults are only inferred when the type's source is being compiled; if the type only exists as a compiled dependency, the processor lacks full source to read descriptions/defaults.

Cases that cannot be inferred automatically:

- Values computed dynamically by methods.
- Defaults taken from constants in another class.
- Defaults of `Collection`/`Map`.
- Certain complex initialization expressions.
- Types reused from another module whose metadata has not been published.

For `regions`, even though code initializes `new ArrayList<>()`, do not assume the processor will infer `[]`. If you want the IDE to display an accurate empty default, add manual metadata.

### 4.2. Nested Properties and Records

The processor automatically recognizes nested properties for inner classes. For an external class used as a nested property, you can annotate the field/getter with `@NestedConfigurationProperty` to describe the desired structure. This annotation is not needed for `Collection` and `Map`, as they are recognized by a separate mechanism.

If using a Java record:

```java
@ConfigurationProperties("acme.report")
public record ReportProperties(
        boolean enabled,
        Duration timeout,
        int maxAttempts
) {
}
```

Descriptions for each component should be written using class-level `@param` Javadoc tags, because records do not have regular instance fields where field Javadoc can be placed:

```java
/**
 * Report integration settings.
 *
 * @param enabled enable/disable integration
 * @param timeout wait time for a single call
 * @param maxAttempts total number of attempts, including the first
 */
```

Do not just convert a class into a record expecting old field Javadoc to still be processed like a JavaBean. Inspect the generated metadata file to confirm actual descriptions.

## 5. Configuring the Annotation Processor in Maven

With Maven, the processor dependency should be declared as `optional` so the library's build tool uses it without propagating the processor to every consumer.

Complete POM example for an auto-configuration module:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.acme</groupId>
    <artifactId>acme-report-autoconfigure</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-configuration-processor</artifactId>
            <optional>true</optional>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                    <annotationProcessorPaths>
                        <path>
                            <groupId>org.springframework.boot</groupId>
                            <artifactId>spring-boot-configuration-processor</artifactId>
                            <version>3.3.13</version>
                        </path>
                    </annotationProcessorPaths>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-configuration-processor` is a compile-time tool. It is not a runtime dependency that applications need to bind `ReportProperties`. Setting `optional=true` prevents the processor dependency from propagating transitively to consumers.

`annotationProcessorPaths` registers the processor explicitly with Maven Compiler Plugin. This suits builds that want explicit processor path control; keep the processor version synchronized with the module's Spring Boot version.

Run:

```bash
mvn clean compile
```

After compiling, check the file in the output directory:

```text
target/classes/META-INF/spring-configuration-metadata.json
```

If the file does not appear, check Maven Compiler Plugin, processor dependency/path, annotations on the class, and whether the source is actually compiled in that module.

## 6. Configuring the Annotation Processor in Gradle

With Gradle, declare the processor using the `annotationProcessor` configuration; do not put it in `implementation` or `runtimeOnly`:

```groovy
plugins {
    id 'java'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-autoconfigure:3.3.13'

    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor:3.3.13'

    testImplementation 'org.springframework.boot:spring-boot-starter-test:3.3.13'
}
```

If the module has `additional-spring-configuration-metadata.json`, the `compileJava` task must know it depends on processed resources:

```groovy
tasks.named('compileJava') {
    inputs.files(tasks.named('processResources'))
}
```

This ensures the additional metadata file is present when the annotation processor runs. Without the dependency between the two tasks, the output might omit the manual metadata or incremental builds might not regenerate the file as expected.

After running:

```bash
./gradlew clean compileJava
```

verify:

```text
build/classes/java/main/META-INF/spring-configuration-metadata.json
```

### 6.1. Where Do Maven and Gradle Differ?

| Build tool | How to declare processor | Common output |
| --- | --- | --- |
| Maven | Optional dependency and/or `annotationProcessorPaths` of compiler plugin | `target/classes/META-INF/...` |
| Gradle | `annotationProcessor` configuration | `build/classes/java/main/META-INF/...` |

Do not include the processor in the application's runtime just so the IDE gets autocomplete. IDEs read the generated and packaged metadata file; the processor does not need to run in production applications.

## 7. Adding Manual Metadata When the Processor Lacks Sufficient Information

Not every property is declared using `@ConfigurationProperties`. Some keys are used directly in `@ConditionalOnProperty`, or their defaults/hints cannot be inferred automatically.

Spring Boot allows creating the file:

```text
src/main/resources/META-INF/additional-spring-configuration-metadata.json
```

Example:

```json
{
  "properties": [
    {
      "name": "acme.report.regions",
      "defaultValue": [],
      "description": "List of data regions to process. Empty means using the default region."
    }
  ],
  "hints": [
    {
      "name": "acme.report.output-format",
      "values": [
        {
          "value": "json",
          "description": "Structured JSON output."
        },
        {
          "value": "csv",
          "description": "CSV output suitable for spreadsheets."
        }
      ]
    }
  ]
}
```

The annotation processor automatically merges this file's contents into the main `spring-configuration-metadata.json`:

- If the property was already discovered automatically, manually declared `description`, `defaultValue`, and `deprecation` fields can override the corresponding information.
- If the property was not recognized by the processor in the current module, manual entries can add it.
- The `hints` section adds suggested values for the IDE.
- The additional file is optional; there is no need to create it if there is no special metadata.

**Manual metadata does not implement runtime binding.** If you declare `acme.report.output-format` in JSON without code binding or reading the property, the IDE can still suggest it, but the application will not automatically change the output format.

### 7.1. Value Hints and Providers

`hints` can declare a list of valid values or providers so IDEs find context-aware choices.

Value hint example:

```json
{
  "hints": [
    {
      "name": "acme.report.output-format",
      "values": [
        { "value": "json" },
        { "value": "csv" },
        { "value": "xml" }
      ]
    }
  ]
}
```

Some standard providers that IDEs may support:

| Provider | Purpose |
| --- | --- |
| `class-reference` | Suggests classes on the project classpath, optionally restricted by base type |
| `handle-as` | Asks the IDE to treat a property as a higher-level type, e.g., `Resource` |
| `logger-name` | Suggests logger names and logger groups |
| `spring-bean-reference` | Suggests bean names matching a type |
| `spring-profile-name` | Suggests existing Spring profiles |
| `any` | Allows additional values beyond the hint list |

Not every IDE supports every provider. The `values` list is tooling assistance; it does not replace enums, validation, or runtime business checks. If values truly belong to a fixed set, use a Java `enum` in `@ConfigurationProperties` when appropriate. If using `String` for flexibility, value hints help configurators discover recommended values.

### 7.2. Deprecation Metadata

When renaming a property, metadata can announce that the old key is deprecated:

```json
{
  "properties": [
    {
      "name": "acme.report.format",
      "type": "java.lang.String",
      "deprecation": {
        "level": "warning",
        "reason": "Renamed for consistency with output-format.",
        "replacement": "acme.report.output-format",
        "since": "2.1.0"
      }
    }
  ]
}
```

`warning` indicates the property is still supported during the transition period. `error` indicates the property is no longer managed/bound per the metadata contract. Metadata does not create aliases in code: if you want the old key to keep working, the implementation must actually accept and transfer the old value to the new key during the compatibility period.

For JavaBean `@ConfigurationProperties`, `@DeprecatedConfigurationProperty` can be placed on the getter of the deprecated property to generate deprecation information. This approach requires the getter/setter to still support reading/binding the old key. Deprecation metadata and runtime migration are two pieces that must be tested together.

## 8. Packaging Metadata into the JAR

Generating metadata in `target/classes` or `build/classes` is not enough. When publishing a library, the file must reside inside the JAR at the exact path:

```text
META-INF/spring-configuration-metadata.json
```

With Maven:

```bash
mvn clean verify
```

Example JAR:

```text
target/acme-report-autoconfigure-1.0.0.jar
```

List JAR contents:

```bash
jar tf target/acme-report-autoconfigure-1.0.0.jar
```

Filter the file name on Windows PowerShell:

```powershell
jar tf target/acme-report-autoconfigure-1.0.0.jar |
    Select-String 'META-INF/spring-configuration-metadata.json'
```

Output must contain:

```text
META-INF/spring-configuration-metadata.json
```

On Linux/macOS you can use:

```bash
jar tf target/acme-report-autoconfigure-1.0.0.jar |
    grep 'META-INF/spring-configuration-metadata.json'
```

To inspect metadata contents, use `unzip` if available:

```bash
unzip -p target/acme-report-autoconfigure-1.0.0.jar \
    META-INF/spring-configuration-metadata.json
```

Or use JDK `jar` to extract the exact file:

```bash
jar xf target/acme-report-autoconfigure-1.0.0.jar \
    META-INF/spring-configuration-metadata.json
```

Then open `META-INF/spring-configuration-metadata.json` with an editor or appropriate file-reading command.

Minimum cross-check:

- Group `acme.report` exists.
- All published properties exist: `enabled`, `timeout`, `max-attempts`, `output-format`, `regions`, `mode`.
- Property types are accurate.
- Descriptions are non-empty and accurately describe behavior.
- Defaults are recorded accurately, especially for collections or values that cannot be inferred automatically.
- Hints include `json` and `csv` values.
- Deprecation/replacement are accurate if the module has legacy keys.
- File resides in the JAR of the **module that consumers actually depend on**, not just in another source module.

If source metadata exists but the JAR lacks it, check packaging configuration, resource filtering, shade/relocation, or whether a build plugin excluded `META-INF` files. Do not solve this by copying an old metadata file into the JAR; fix the pipeline so the processor generates the right file on every build.

## 9. Smoke Test Confirming Metadata Was Generated

You can write a small test to detect if the processor stopped running or if additional metadata was not merged.

Create `src/test/java/com/acme/report/MetadataPackagingTest.java`:

```java
package com.acme.report;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class MetadataPackagingTest {

    @Test
    void generatedMetadataContainsPublicPropertiesAndHints()
            throws IOException {

        try (InputStream input = getClass().getClassLoader()
                .getResourceAsStream(
                        "META-INF/spring-configuration-metadata.json")) {

            assertThat(input).isNotNull();

            String json = new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8);

            String compact = json.replaceAll("\\s+", "");

            assertThat(compact)
                    .contains("\"name\":\"acme.report\"");
            assertThat(compact)
                    .contains("\"name\":\"acme.report.enabled\"");
            assertThat(compact)
                    .contains("\"name\":\"acme.report.timeout\"");
            assertThat(compact)
                    .contains("\"name\":\"acme.report.max-attempts\"");
            assertThat(compact)
                    .contains("\"name\":\"acme.report.output-format\"");
            assertThat(compact)
                    .contains("\"name\":\"acme.report.regions\"");
            assertThat(compact)
                    .contains("\"value\":\"json\"");
            assertThat(compact)
                    .contains("\"value\":\"csv\"");
        }
    }
}
```

Run:

```bash
mvn test
```

Expected output:

```text
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
```

This is a smoke test reading metadata on the test classpath after compile. It verifies the processor generated the file and manual hints were merged. It does not replace the `jar tf` step: you must inspect the final JAR to confirm the file was packaged.

You can increase rigor by parsing JSON and checking each object/field instead of substring matching. For a library with a large contract, verify the public property list, types, defaults, descriptions, and deprecations using structured tests to catch unintended changes.

## 10. Testing Autocomplete in a Consuming Application's IDE

Once metadata is inside the JAR:

1. Publish/install the artifact into the local Maven repository or an internal repository.
2. In the consuming application, declare a dependency on the exact artifact/version of the starter or autoconfigure module.
3. Reload Maven project or Refresh Gradle project so the IDE updates its dependency graph.
4. Rebuild the library and consumer modules so the IDE sees the new artifact.
5. Open `application.yml` and type the prefix:

```yaml
acme:
  report:
```

A supported IDE can suggest:

```yaml
acme:
  report:
    enabled:
    timeout:
    max-attempts:
    output-format:
    regions:
    mode:
```

When typing `output-format`, the IDE can suggest `json` and `csv` if it reads manual hints and supports value completion. When selecting a property, the documentation popup can show the description and default.

Consumer configuration example:

```yaml
acme:
  report:
    enabled: true
    timeout: 750ms
    max-attempts: 5
    output-format: csv
    regions:
      - ap-southeast-1
      - eu-west-1
    mode: STRICT
```

The library's metadata is used by the IDE while working with the consumer's sources. Users do not need to copy `spring-configuration-metadata.json` into the consumer project if the file is already inside the dependency JAR and the IDE can index that dependency.

The level of support for autocomplete, hint providers, and documentation popups depends on the IDE, Spring plugins, and indexing state. Valid metadata is a necessary condition; it does not guarantee every IDE presents every provider identically.

## 11. Diagnosing When the IDE Does Not Suggest Properties

### 11.1. File Was Not Generated

Check:

- Does the class have `@ConfigurationProperties` with the right package/import?
- Is the class/method in the source set being compiled?
- Is `spring-boot-configuration-processor` declared?
- Does the Maven compiler run annotation processors?
- Does Gradle declare `annotationProcessor` rather than only `implementation`?
- Is the IDE looking at the right module containing `ReportProperties`?

Run `mvn clean compile` or `./gradlew clean compileJava`, then look for the file in the output directory.

### 11.2. File Exists in classes but Not in JAR

This is a packaging error. Check:

- Does the JAR include resources from the output directory?
- Does a shade or custom packaging plugin exclude `META-INF/**`?
- Does any build step delete or overwrite `META-INF`?
- Are you inspecting the exact artifact and version used by the consumer?

Always inspect the final JAR, not only `target/classes`.

### 11.3. JAR Has Metadata but Consumer IDE Still Does Not Suggest

Check:

- Does the consumer have the right dependency and new version?
- Is the dependency on the compile/development classpath that the IDE indexes?
- Were Maven/Gradle reloaded after publishing the new version?
- Does the IDE have appropriate Spring Boot/YAML support plugins?
- Do IDE caches/indexes need refreshing?
- Is the JSON metadata valid and do keys use the right canonical prefix?

Try creating a small consumer project with only that dependency to isolate IDE issues from large application configurations.

### 11.4. IDE Suggests but Runtime Does Not Apply Property

Metadata does not execute binding. Check separately:

- Is the property bound by `@ConfigurationProperties`, `@Value`, or an appropriate condition?
- Is the properties class registered via `@EnableConfigurationProperties` or configuration properties scanning?
- Does the auto-configuration match?
- Which configuration source/profile is winning?
- Are there conversion or validation errors?

For example, `acme.report.output-format` exists in JSON without any code reading it; the IDE can still suggest it, while the application will not automatically change the output format.

## 12. Common Mistakes When Building Metadata

**Mistake 1 — Adding `spring-boot-configuration-processor` only to test scope.**  
The processor must run during compilation of the production module. Test scope does not generate metadata for the main artifact.

**Mistake 2 — Putting the processor into the starter's runtime dependencies.**  
This is a build tool, not a runtime API. Maven should mark it optional; Gradle uses `annotationProcessor`.

**Mistake 3 — Inspecting files only in the source tree.**  
The generated file may exist in `target/classes` yet be excluded during packaging. Always inspect JAR contents.

**Mistake 4 — Writing Javadoc on getters without checking output.**  
For JavaBeans, the processor uses Javadoc on fields to generate descriptions; for records, use class-level `@param`. Placing it in the wrong spot can leave descriptions empty.

**Mistake 5 — Expecting collection defaults to appear automatically.**  
The processor does not auto-detect defaults for Collections. Add `defaultValue` via manual metadata if it needs to be shown.

**Mistake 6 — Treating manual metadata as runtime implementation.**  
The JSON file only describes properties for tooling. For a property to take effect, code must bind/read and apply it.

**Mistake 7 — Declaring value hints and treating them as validation.**  
The IDE can suggest `json` and `csv`, but Binder does not use metadata hints as a runtime validator. Use an enum or validation if you want to genuinely restrict values.

**Mistake 8 — Forgetting Gradle task ordering.**  
If using `additional-spring-configuration-metadata.json`, ensure `compileJava` depends on `processResources` so the processor reads the supplemental file.

**Mistake 9 — Consumer using the wrong artifact.**  
Metadata in an `autoconfigure` module does not help the IDE if the application only has another core module lacking that file. Verify which module is actually published and added to the consumer.

**Mistake 10 — Changing properties without updating metadata.**  
Renames/removals/defaults/deprecations must update source, manual metadata, tests, migration guides, and artifacts. Stale metadata in dependency caches can cause the IDE to keep suggesting removed keys.

## 13. Pre-Release Review Workflow for Starters

| Check | Expected Result |
| --- | --- |
| Processor dependency | Maven optional or Gradle annotationProcessor |
| Source properties | `@ConfigurationProperties` with right prefix |
| Descriptions | Clear Javadoc in the right place |
| Defaults | Detected by processor or supplemented manually |
| Hints | Enum or manual values/providers when needed |
| Additional metadata | Valid JSON and merged at compile time |
| Generated output | Has `META-INF/spring-configuration-metadata.json` |
| Packaged artifact | JAR actually contains the exact metadata path |
| Consumer | Dependency on right artifact/version |
| IDE | Autocomplete and documentation appear after reload/index |
| Runtime | Binder/auto-configuration actually applies properties |
| Compatibility | Deprecation/replacement/default verified |

For modules with many properties, include metadata checks in CI. A successful build with missing metadata can still degrade the user experience; valid JSON without proper runtime binding is also a contract bug.

## 14. Self-Check Questions

**Question 1.** Where must the standard metadata file reside inside the JAR?  
**Answer:** `META-INF/spring-configuration-metadata.json`.

**Question 2.** Which annotation processor generates metadata from `@ConfigurationProperties`?  
**Answer:** `spring-boot-configuration-processor`, running during compile.

**Question 3.** How should Maven declare the processor so it is not propagated to consumers?  
**Answer:** Declare the `spring-boot-configuration-processor` dependency with `<optional>true</optional>`; you can also configure an explicit annotation processor path in Maven Compiler Plugin.

**Question 4.** In which configuration should Gradle place the processor?  
**Answer:** `annotationProcessor`, not `implementation` or `runtimeOnly`.

**Question 5.** Why might a collection with an empty default lack `defaultValue` in metadata?  
**Answer:** The processor does not auto-detect defaults for Collections; add `defaultValue` via `additional-spring-configuration-metadata.json`.

**Question 6.** Do `hints.values` force runtime to accept only those values?  
**Answer:** No. Hints assist IDEs; use enums or validation to constrain runtime values.

**Question 7.** Metadata exists in `target/classes` yet the consumer IDE still does not suggest it. What is the next step?  
**Answer:** Check metadata in the published JAR, the consumer's dependency/version, and whether the IDE has reloaded/indexed the new dependency.

**Question 8.** Metadata describes `acme.report.output-format`, but code neither binds nor reads the key. Can the IDE suggest it and will runtime change?  
**Answer:** The IDE can suggest it; runtime does not automatically change because metadata does not execute properties.

## 15. Principles to Remember

- `spring-configuration-metadata.json` helps IDEs and tooling understand properties supported by a library.
- `spring-boot-configuration-processor` runs at compile time; Maven uses optional dependencies and Gradle uses `annotationProcessor`.
- Javadoc, types, and defaults can be inferred from source; records use `@param` Javadoc tags, while Collections may need supplemental metadata.
- `additional-spring-configuration-metadata.json` supplements descriptions, defaults, deprecations, and hints.
- For autocomplete in consumers, metadata must reside inside the JAR that consumers actually depend on.
- Use `jar tf` and extract the JSON to verify the final artifact.
- IDE support may vary; refresh dependencies/indexes when metadata changes.
- Metadata does not replace Binder, auto-configuration, validation, or runtime behavior.

### Official Documentation

- [Spring Boot 3.3.13 — Configuration Metadata](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/index.html)
- [Spring Boot — Generating Metadata with the Annotation Processor](https://docs.spring.io/spring-boot/specification/configuration-metadata/annotation-processor.html)
- [Spring Boot — Metadata Format](https://docs.spring.io/spring-boot/specification/configuration-metadata/format.html)
- [Spring Boot — Providing Manual Hints](https://docs.spring.io/spring-boot/specification/configuration-metadata/manual-hints.html)
- [Spring Boot 3.3 — `@ConfigurationProperties`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html)
