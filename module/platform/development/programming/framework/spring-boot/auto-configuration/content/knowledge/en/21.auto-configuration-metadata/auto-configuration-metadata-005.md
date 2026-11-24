# Declaring the Appropriate Annotation Processor in Gradle or Maven for Spring Boot

## 1. What Does the Annotation Processor Generate?

When a library or Spring Boot application exposes configuration via `@ConfigurationProperties`, the IDE can suggest property names, data types, default values, and descriptions when users write `application.yml` or `application.properties`. To generate this supporting data, Spring Boot provides the artifact:

~~~text
org.springframework.boot:spring-boot-configuration-processor
~~~

The artifact contains a **Java annotation processor**. During source compilation, the processor reads metadata of classes/methods annotated with `@ConfigurationProperties` and generates the file:

~~~text
META-INF/spring-configuration-metadata.json
~~~

The metadata file describes configuration in Spring Boot's standard format so IDEs, documentation tools, and other tooling can provide completion/documentation.

Points to distinguish right away:
- `@ConfigurationProperties` defines the prefix and bindable data structure.
- `@EnableConfigurationProperties` or `@ConfigurationPropertiesScan` registers the properties bean in the Spring context.
- `spring-boot-configuration-processor` generates **metadata for tooling** at compile time.

The processor **does not register beans**, does not perform binding when the application runs, and does not replace `@EnableConfigurationProperties`. Missing the processor usually does not cause the application to lose the ability to read configuration; the most visible effect is that metadata is not generated, so the IDE lacks suggestions.

## 2. Choosing the Right Dependency and Scope

The artifact to declare is:

~~~text
org.springframework.boot:spring-boot-configuration-processor
~~~

Use a version from the same release line as the Spring Boot version the project runs, for example a Boot 3.3 project uses processor 3.3.x. If the project already applies the Spring Boot Gradle plugin or Spring Boot dependency management/BOM, the version is typically managed centrally. If not using dependency management, declare the version explicitly or import the right Boot BOM.

**This is a build-time dependency.** It belongs in the compiler's processor path, not as an application runtime dependency.

| Build tool | Recommended configuration | Meaning |
| --- | --- | --- |
| Gradle Java | `annotationProcessor` | Puts the processor on the compile task's processor path |
| Modern Maven compiler plugin | `annotationProcessorPaths` | Explicitly declares the compiler's processor path |
| Maven using traditional optional dependency config | Dependency with `optional=true` | Allows the compiler to discover the processor without propagating this dependency to consumers |

Do not use `implementation` or `compileOnly` as an arbitrary substitute for `annotationProcessor` in Gradle. `implementation` puts the library on the compile/runtime classpath; `compileOnly` only makes the dependency present on the compile classpath without explicitly specifying the processor path. Dedicated configuration helps the build determine which processors to run.

## 3. Gradle Groovy DSL: Standard Configuration

For Java projects using Gradle, add the dependency in `build.gradle`:

~~~groovy
dependencies {
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

If the project uses the Spring Boot Gradle plugin or dependency management plugin and the Boot BOM is applied, you may omit the version on the dependency line. If there is no BOM, specify a compatible version explicitly, for example:

~~~groovy
dependencies {
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor:3.3.13'
}
~~~

Do not declare the processor as `implementation` just so “the IDE sees it”. Annotation processors execute during the compile task, and the `annotationProcessor` dependency is kept in a dedicated configuration for this purpose.

### Gradle Kotlin DSL

If the build file is `build.gradle.kts`, the corresponding syntax is:

~~~kotlin
dependencies {
    annotationProcessor("org.springframework.boot:spring-boot-configuration-processor")
}
~~~

The Gradle Groovy and Kotlin snippets have the same meaning. Use the syntax matching your current build file type.

### Add Only to Modules Containing Properties Sources

In a multi-module build, place the processor in the module that **actually compiles the `@ConfigurationProperties` classes**. For example:

~~~text
root
├── app
├── acme-autoconfigure
└── acme-starter
~~~

If `AcmeProperties.java` is in the `acme-autoconfigure` module, add `annotationProcessor` to that module's build file. Adding it only to root or starter does not guarantee the processor runs in the module containing the source. Each Java module needs to generate metadata for the sources it compiles.

## 4. Maven: Declaring the Processor Path for the Compiler

With Maven Compiler Plugin 3.12.0 or higher, you can configure the processor explicitly via `annotationProcessorPaths`. Example for a Spring Boot 3.3.13, Java 17 project:

~~~xml
<properties>
    <java.version>17</java.version>
    <maven.compiler.release>17</maven.compiler.release>
</properties>

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
~~~

In the example, the processor version is pinned to the Spring Boot 3.3.13 line; when upgrading Spring Boot, upgrade the processor version accordingly. If using `spring-boot-starter-parent` or a BOM, you can organize version management to avoid repeating versions, but ensure Maven can resolve the version for the processor path.

`annotationProcessorPaths` is an isolated list: if the project uses multiple processors such as Lombok or MapStruct, add them to the same list. When declaring this list, do not assume other processors will automatically appear from regular dependencies on the classpath.

### Maven Optional Dependency Declaration per Spring Boot 3.3 Docs

The Spring Boot 3.3 documentation also describes declaring the processor as an optional dependency:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-configuration-processor</artifactId>
        <optional>true</optional>
    </dependency>
</dependencies>
~~~

This approach is typically used in Maven projects configuring annotation processors via the compiler's discovery mechanism. `optional=true` prevents the processor dependency from being propagated transitively like a normal dependency to consuming applications.

With modern Maven compiler plugin, **prefer an explicit processor path** when you want predictable builds on newer JDKs. Choose one configuration approach that fits your current compiler/plugin; avoid unnecessary duplication across both dependency discovery and processor path. If a project uses an older compiler per Boot 3.3 guidance, traditional optional dependency can be used while verifying that the processor actually runs during compile.

## 5. Properties Classes the Processor Can Read

JavaBean example:

~~~java
package com.acme.server;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.server")
public class ServerProperties {

    /**
     * Host name or IP address used by the server.
     */
    private String host = "127.0.0.1";

    /**
     * Port used by the embedded server.
     */
    private int port = 8080;

    public String getHost() {
        return host;
    }

    public void setHost(String host) {
        this.host = host;
    }

    public int getPort() {
        return port;
    }

    public void setPort(int port) {
        this.port = port;
    }
}
~~~

The processor reads the `acme.server` prefix, properties via getters/setters, and certain default values inferable from source. Metadata can describe:
- `acme.server.host` — type `java.lang.String`, default value `127.0.0.1`.
- `acme.server.port` — type `java.lang.Integer`, default value `8080`.
- Descriptions taken from Javadoc on the field when the field belongs to the source being compiled.

Property Javadoc should be plain text because the processor puts the content into JSON metadata; do not write HTML or Markdown syntax expecting it to be rendered.

### Records and Constructor Binding

The processor also supports immutable configuration using constructors/records. Example:

~~~java
package com.acme.server;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties("acme.server")
public record ServerProperties(String host, int port) {
}
~~~

With records, descriptions for each component should be placed using class-level `@param` Javadoc tags, for example:

~~~java
/**
 * Server connection settings.
 *
 * @param host Host name or IP address.
 * @param port Listening port.
 */
@ConfigurationProperties("acme.server")
public record ServerProperties(String host, int port) {
}
~~~

The processor extracts properties from constructor parameters according to Spring Boot rules. For classes with multiple constructors or using `@ConstructorBinding`, check the exact constructor the binder uses; the processor cannot arbitrarily guess every factory method.

## 6. Where Is Metadata Generated and How to Inspect It?

After compiling, the file typically appears in the module's output directory:

| Build | Common Path |
| --- | --- |
| Gradle Java | `build/classes/java/main/META-INF/spring-configuration-metadata.json` |
| Maven | `target/classes/META-INF/spring-configuration-metadata.json` |

The output path may differ if the project customizes source sets, compiler output, or the build directory. The important file is the `META-INF/spring-configuration-metadata.json` resource in the output/artifact.

Gradle:

~~~bash
./gradlew clean compileJava
~~~

Maven:

~~~bash
mvn clean compile
~~~

After compiling, inspect the file in the output directory. When packaging the JAR, check that the resource is included in the artifact:

~~~bash
jar tf build/libs/acme-autoconfigure-1.0.0.jar
~~~

Or with Maven:

~~~bash
jar tf target/acme-autoconfigure-1.0.0.jar
~~~

In the entry list, look for:

~~~text
META-INF/spring-configuration-metadata.json
~~~

The `jar tf` command only lists JAR entries; if you want to read the JSON contents, extract the file or open it with an archive tool. Do not rely solely on IDE autocomplete to conclude the processor ran: the IDE may hold cached old metadata.

### Example of Partially Generated Metadata

Field names and ordering may differ depending on source, but the structure is usually similar:

~~~json
{
  "groups": [
    {
      "name": "acme.server",
      "type": "com.acme.server.ServerProperties",
      "sourceType": "com.acme.server.ServerProperties"
    }
  ],
  "properties": [
    {
      "name": "acme.server.host",
      "type": "java.lang.String",
      "description": "Host name or IP address used by the server.",
      "sourceType": "com.acme.server.ServerProperties",
      "defaultValue": "127.0.0.1"
    },
    {
      "name": "acme.server.port",
      "type": "java.lang.Integer",
      "description": "Port used by the embedded server.",
      "sourceType": "com.acme.server.ServerProperties",
      "defaultValue": 8080
    }
  ],
  "hints": []
}
~~~

This is a condensed example to illustrate the schema, not a byte-for-byte output guarantee for every processor version.

## 7. Adding Manual Metadata When the Processor Cannot Infer Enough

Not every property originates directly from a `@ConfigurationProperties` class. You may need to describe properties read by other code, supply default values that cannot be statically inferred, add deprecations, or provide value hints.

Create the resource:

`src/main/resources/META-INF/additional-spring-configuration-metadata.json`

Example:

~~~json
{
  "properties": [
    {
      "name": "acme.server.mode",
      "type": "java.lang.String",
      "description": "Server operating mode.",
      "defaultValue": "standalone"
    }
  ],
  "hints": [
    {
      "name": "acme.server.mode",
      "values": [
        {
          "value": "standalone",
          "description": "Runs as a standalone server."
        },
        {
          "value": "cluster",
          "description": "Joins a server cluster."
        }
      ]
    }
  ]
}
~~~

The processor automatically merges the contents of the additional file into the main metadata when running. This file is optional; there is no need to create it if there are no extra properties/hints.

### Gradle: Ensuring Resources Are Present During Compile

With Gradle, when using `additional-spring-configuration-metadata.json`, configure `compileJava` to take `processResources` as an input so the resources task runs before the processor reads metadata:

~~~groovy
tasks.named('compileJava') {
    inputs.files(tasks.named('processResources'))
}
~~~

Kotlin DSL:

~~~kotlin
tasks.named("compileJava") {
    inputs.files(tasks.named("processResources"))
}
~~~

This configuration is especially important when manual metadata is processed in the same build. It is not needed if the project does not use an additional file.

### Manual Metadata Can Supplement or Override

If a manual entry matches an auto-generated property, certain fields such as description, default value, and deprecation can be overridden per the supplemental metadata. Entries that do not yet exist can be added. The `ignored.properties` section can exclude properties from the generated list.

Keep the JSON file valid, with accurate property names and data types. Wrong metadata can cause the IDE to suggest inappropriate values even though the runtime binder behaves differently.

## 8. What the Processor Auto-Detects and Limitations

The processor can read:
- Classes or methods annotated with `@ConfigurationProperties`.
- Properties via JavaBean getters/setters.
- Properties from constructors/records per binding rules.
- Nested properties; inner classes are usually recognized automatically.
- Collections and Maps as generic-typed properties.
- Certain common Lombok annotations such as `@Data`, `@Value`, `@Getter`, and `@Setter`.

Some limitations to remember:

1. **Default values must be inferable from the source being compiled.** Defaults taken from another class's constants or dynamic expressions may not be detected.
2. **Collection defaults are not fully inferred automatically.** If you need to display defaults for collections or enums, add manual metadata.
3. **Sources from compiled dependencies:** the processor lacks the source of those classes so it cannot extract full Javadoc/default values. You can provide manual metadata or the corresponding source metadata.
4. **External nested classes:** use `@NestedConfigurationProperty` on the field/getter when you want a regular class to be treated as a nested property; collections and maps already have special handling.
5. **Custom meta-annotations:** do not assume a custom annotation meta-annotated with `@ConfigurationProperties` will be understood by the processor like the original annotation.
6. **Javadoc:** plain text only; for records use `@param` tags for components.

Do not treat the processor as an analyzer for every Java expression. Metadata is a static model for tooling, not a dump of all runtime values.

## 9. Lombok, AspectJ, and Multiple Annotation Processors

A project can use multiple processors. In that case, ordering and run count matter.

### Lombok

If a properties class uses Lombok to generate getters/setters, Lombok's processor must run **before** `spring-boot-configuration-processor` so metadata can see the Lombok-generated structure.

Gradle:

~~~groovy
dependencies {
    annotationProcessor 'org.projectlombok:lombok'
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

Maven with a compiler plugin having an explicit processor list must order Lombok before the configuration processor and declare both in `annotationProcessorPaths`/`annotationProcessors` accordingly. Do not simply add Lombok to runtime dependencies expecting the processor to run in the right order automatically.

If using Lombok, the dependency/processor path configuration must match the project's Lombok and JDK versions.

### AspectJ

If AspectJ and the Maven compiler both trigger annotation processing, there is a risk the processor runs twice. Choose one place to perform annotation processing. If AspectJ already runs all processors, you can disable processing in the Maven compiler plugin with:

~~~xml
<configuration>
    <proc>none</proc>
</configuration>
~~~

Only use `proc=none` when another compiler/processor pipeline already performs the necessary work; if disabled everywhere, metadata will not be generated.

## 10. Multi-Module and Starters: Placing the Processor in the Right Place

Example:

~~~text
acme-library/
├── acme-core/
├── acme-autoconfigure/
│   └── src/main/java/com/acme/ServerProperties.java
└── acme-starter/
~~~

If `ServerProperties` is in `acme-autoconfigure`, the processor must be declared in the build file of the `acme-autoconfigure` module. The starter module only aggregates dependencies; if it contains no properties sources, it does not need a separate processor.

If a properties class uses a nested type from another module, metadata for the dependent type may be incomplete because the processor does not read sources of compiled dependencies. Spring Boot provides `@ConfigurationPropertiesSource` for source types needing reusable metadata; for external types outside your control, provide manual metadata if needed.

When building an individual module, check the compile task of that specific module:

~~~bash
./gradlew :acme-autoconfigure:clean :acme-autoconfigure:compileJava
~~~

Maven:

~~~bash
mvn -pl acme-autoconfigure -am clean compile
~~~

Do not only run compile at the root if the reactor/build configuration does not actually include the module containing properties in the lifecycle.

## 11. Common Issues and Troubleshooting

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Missing `spring-configuration-metadata.json` | Processor not declared or declared in wrong scope | Gradle uses `annotationProcessor`; Maven configures processor path/dependency discovery |
| File exists but IDE does not suggest keys | IDE has not reloaded project or metadata is not in the opened module | Reload Gradle/Maven, clean compile, check resources in module |
| Only some properties appear | Incompatible getter/setter/constructor or property is in a compiled dependency | Inspect source model; add manual metadata for what cannot be inferred |
| Collection defaults do not appear | Processor does not auto-detect full collection defaults | Declare `defaultValue` in additional metadata |
| Descriptions are missing | Missing Javadoc or class source was not compiled in the module | Write plain-text Javadoc on fields; for records use `@param` |
| Lombok properties not recognized | Lombok processor ran after or is missing from processor path | Add Lombok to processor path and order it before Boot processor |
| Manual metadata is ignored | Wrong file name or wrong resource location | Use exact `META-INF/additional-spring-configuration-metadata.json` |
| Gradle does not see manual metadata | `processResources` is not an input/dependency of `compileJava` | Configure `inputs.files(tasks.named('processResources'))` |
| Newer Maven/JDK does not run processor | Compiler does not auto-discover processors | Declare `annotationProcessorPaths` explicitly |
| Metadata generated twice | AspectJ and compiler both run the processor | Let only one pipeline process; configure `proc=none` in the other if appropriate |
| Processor packaged as a runtime dependency | Wrong scope declared | Move to processor path or optional Maven dependency |

### Quick Checklist

- [ ] Correct artifact `spring-boot-configuration-processor`.
- [ ] Version aligned with the Spring Boot line.
- [ ] Gradle: `annotationProcessor` in the right module.
- [ ] Maven: `annotationProcessorPaths` or optional dependency approach supported by the compiler.
- [ ] Lombok placed before the Boot processor if used.
- [ ] Clean compile and check `META-INF/spring-configuration-metadata.json`.
- [ ] Check that the published JAR contains the metadata.
- [ ] Do not confuse tooling metadata with bean registration/runtime binding.

## 12. Self-Check Knowledge

1. Which file does the processor generate? **`META-INF/spring-configuration-metadata.json`**.
2. In which configuration does Gradle Java declare the processor? **`annotationProcessor`**.
3. Where does modern Maven compiler plugin declare the processor path? **`annotationProcessorPaths`**.
4. Should the processor be declared as an application runtime dependency? **No**; this is a build/compiler dependency.
5. Does the processor create the `ServerProperties` bean in the Spring context? **No**; a separate properties bean registration mechanism is required.
6. Does the processor automatically generate descriptions from source field Javadoc? **Yes**, when the source is compiled and Javadoc is plain text.
7. Why might collection defaults be missing in metadata? The processor cannot fully infer collection values from the source model; add manual metadata.
8. What is the name of the supplemental metadata file? **`META-INF/additional-spring-configuration-metadata.json`**.
9. If Lombok generates getters/setters, what is the processor order? **Lombok before Spring Boot configuration processor**.
10. If properties sources are in the autoconfigure module, which module needs the processor? **The autoconfigure module**, where sources are compiled.

## Official References

- [Spring Boot 3.3 — Configuration Metadata](https://docs.spring.io/spring-boot/3.3/reference/configuration-metadata.html): metadata goals, annotation processor, Gradle/Maven config, supplemental metadata, and detection limits.
- [Spring Boot — Generating Your Own Metadata by Using the Annotation Processor](https://docs.spring.io/spring-boot/specification/configuration-metadata/annotation-processor.html): Maven processor path, Gradle `annotationProcessor`, Lombok/AspectJ, nested properties, and manual metadata.
- [Spring Boot 3.3 — `@ConfigurationProperties` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html): annotation defining a properties source.
- [Gradle — Java Plugin: Annotation Processor Path](https://docs.gradle.org/current/userguide/java_plugin.html): `annotationProcessor` configuration and compile task.
- [Apache Maven Compiler Plugin — Annotation Processor Paths](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html#annotationProcessorPaths): declaring processor paths for the Maven compiler.
