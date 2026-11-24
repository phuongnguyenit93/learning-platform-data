# JAR release checklist: imports, metadata, dependencies, testing, and consumer application

## 1. Goal of a release

A custom Spring Boot starter can compile and pass tests inside its repository yet still fail when another application adds the dependency. The cause usually lies in the published artifact: missing auto-configuration registration file, unpackaged metadata, misdeclared optional dependencies, a POM that does not express the right runtime classpath, or tests that run only inside the producer module.

Therefore, releasing a starter requires checking three layers:

1. **JAR contents:** are classes, resources, imports, and metadata actually present inside the artifact?
2. **Dependency metadata:** does the Maven POM or Gradle Module Metadata deliver the right dependencies to consumers?
3. **Consumer application:** does an independent project declaring only the starter start up, discover auto-configuration, and use the feature?

This article uses Spring Boot 3.5.x, Java 17, and the hypothetical library com.acme:acme-client. The Acme artifact names, classes, and versions are examples; substitute your project's real library.

## 2. Distinguish the artifacts to publish

For an integration with optional dependencies, a two-module structure is usually easy to control:

~~~text
acme-spring-boot-autoconfigure/
    - @AutoConfiguration and nested configurations
    - @ConfigurationProperties
    - classpath/property/bean conditions
    - callbacks or Spring-facing APIs
    - metadata and AutoConfiguration.imports

acme-spring-boot-starter/
    - usually has no Java source
    - dependency on acme-spring-boot-autoconfigure
    - dependency on acme-client and libraries needed for the default experience
    - does not repackage dependencies inside the JAR

consumer-app/
    - declares only acme-spring-boot-starter
    - verifies auto-configuration is discovered from the published JAR
    - verifies runtime classpath and actual behavior
~~~

**The autoconfigure module** contains the integration logic. Other applications can use it directly to choose libraries themselves, so Acme library dependencies are often marked optional in Maven or compile-only in Gradle when needed only to compile the integration.

**The starter module** expresses the publisher's default dependency choice. If the default experience needs Acme Client, the starter declares Acme Client directly and non-optionally. When consumers add the starter, that dependency must reach the application's runtime classpath.

**The consumer application** is the critical test for published artifacts. Tests inside the autoconfigure module always see dependencies declared by that module; an independent consumer reveals whether POM/Gradle metadata and resources truly work outside the producer.

### 2.1. Starter JAR vs. executable Spring Boot JAR

| Artifact type | Typical contents | Purpose |
| --- | --- | --- |
| Autoconfigure library JAR | com/acme/...class, META-INF/spring/...imports, metadata | Added to classpath by other applications |
| Starter JAR | Usually only manifest and artifact metadata; dependencies declared in POM/module metadata | Dependency bundle, containing no copies of dependent JARs |
| Executable application JAR | BOOT-INF/classes, BOOT-INF/lib, Spring Boot loader and runnable manifest | Executed with java -jar |

Do not use Spring Boot Maven repackage to turn an autoconfigure or starter module into an executable JAR. That plugin is meant for applications launched with java -jar. Library JARs must keep standard Java JAR structure so consumers can load classes directly. The consuming application's executable JAR is where BOOT-INF/classes and BOOT-INF/lib belong.

## 3. Register auto-configuration via AutoConfiguration.imports

### 3.1. Correct path and contents

Spring Boot 3 looks for auto-configuration candidates in the following resource inside published JARs:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Example in the acme-spring-boot-autoconfigure module:

~~~text
com.acme.boot.autoconfigure.AcmeAutoConfiguration
com.acme.boot.autoconfigure.AcmeMetricsAutoConfiguration
~~~

Each class sits on its own line using its fully qualified class name. Comment lines starting with # can be included.

Common mistakes:

- Placing the file in src/main/java instead of src/main/resources.
- Wrong filename, wrong casing, or missing the META-INF/spring directory.
- Writing the package name while forgetting the class name.
- Using commas or listing multiple classes on one line.
- Creating the file properly in source yet failing to package the resource into the artifact.
- Registering only in test configuration so tests pass while consumers fail to discover it.

If an auto-configuration candidate is a nested class rather than a top-level class, the name in imports uses `$` to separate the enclosing and nested classes, e.g. com.acme.Outer$NestedAutoConfiguration. Normally, register top-level auto-configurations and let them use `@Import` or contain nested configurations as needed.

### 3.2. Boot 3 and spring.factories

With Spring Boot 3, register auto-configurations using META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports. Do not rely on the EnableAutoConfiguration key in META-INF/spring.factories as older Boot starters did.

spring.factories may still be used for certain other Spring Boot extension mechanisms; what changes is the registration mechanism for the auto-configuration candidate list.

### 3.3. Auto-configuration must not be component scanned

Auto-configuration must be discovered through the imports file. Do not place auto-configuration classes inside application packages hoping component scan finds them automatically; also do not use @ComponentScan inside auto-configuration to scan additional components.

Use @Import for specific configurations that must be loaded. This limits scope, avoids accidentally creating beans from internal packages, and keeps starter behavior predictable.

### 3.4. Control conditions and ordering

A typical auto-configuration:

~~~java
@AutoConfiguration
@EnableConfigurationProperties(AcmeProperties.class)
public class AcmeAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.acme.client.AcmeClient")
    static class AcmeClientConfiguration {

        @Bean
        @ConditionalOnMissingBean
        AcmeOperations acmeOperations(AcmeProperties properties) {
            return new DefaultAcmeOperations(properties);
        }
    }
}
~~~

**@ConditionalOnClass** guards the integration when the optional library is absent. The nested configuration isolates references to optional classes; avoid placing method signatures containing optional types directly on the root configuration while relying only on a condition on the @Bean method.

**@ConditionalOnMissingBean** lets the application replace the default implementation. **@ConditionalOnProperty** can drive feature flags. Test all branches: class present, class absent, property enabled/disabled, and user bean override.

If a configuration depends on ordering with other auto-configurations, use before, after, @AutoConfigureBefore, @AutoConfigureAfter, or @AutoConfigureOrder intentionally. Do not rely on imports file line order in place of official ordering mechanisms.

### 3.5. When renaming or replacing an auto-configuration

If a published class moves packages or is replaced by another class, you may need the resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements
~~~

Contents map old class to new class:

~~~text
com.acme.boot.autoconfigure.OldAcmeAutoConfiguration=com.acme.boot.autoconfigure.core.AcmeAutoConfiguration
~~~

Then update AutoConfiguration.imports to contain only the replacement class. This handles old references in supported ordering and exclusions; never rename a published class while ignoring compatibility.

## 4. Two metadata types to distinguish

A starter can produce two different metadata files. They do not replace each other.

| Metadata | Generated by | Role |
| --- | --- | --- |
| META-INF/spring-configuration-metadata.json | spring-boot-configuration-processor | Describes properties, types, defaults, descriptions, and hints for IDE configuration support |
| META-INF/spring-autoconfigure-metadata.properties | spring-boot-autoconfigure-processor | Records condition metadata so Spring Boot can filter out non-matching auto-configurations early |

### 4.1. Configuration metadata for IDEs

If the module contains @ConfigurationProperties, add spring-boot-configuration-processor as an annotation processor. The processor scans classes/properties at compile time and generates META-INF/spring-configuration-metadata.json.

Example:

~~~java
@ConfigurationProperties(prefix = "acme.client")
public class AcmeProperties {

    /**
     * Whether the Acme integration is enabled.
     */
    private boolean enabled = true;

    /**
     * Timeout for establishing a connection to the Acme service.
     */
    private Duration connectTimeout = Duration.ofSeconds(3);

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }
}
~~~

Field Javadoc generates descriptions for IDEs. Best practices:

- Use a library-owned namespace, such as acme.client; avoid Spring Boot namespaces such as spring, server, or management.
- Use short, clear sentences.
- For booleans, start descriptions with "Whether" or "Enable".
- Use Duration instead of long when representing durations.
- Document the default unit if the property allows values without suffixes.
- Do not repeat the default value in the description when the processor can infer it from source.

Metadata helps IDEs suggest keys and values; it does not register beans, replace @EnableConfigurationProperties, or replace AutoConfiguration.imports.

### 4.2. Maven: configure annotation processors

In the autoconfigure module, example Maven Compiler Plugin 3.13.0+ configuration:

~~~xml
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
                        <artifactId>spring-boot-autoconfigure-processor</artifactId>
                        <version>${spring-boot.version}</version>
                    </path>
                    <path>
                        <groupId>org.springframework.boot</groupId>
                        <artifactId>spring-boot-configuration-processor</artifactId>
                        <version>${spring-boot.version}</version>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Define the version in the parent POM or dependency management so modules share the same Spring Boot version. If the project uses Lombok or other annotation processors, declare all required processors and verify execution order; specifying annotationProcessorPaths can cause processors omitted from the list to be skipped.

If the module has no @ConfigurationProperties, the configuration processor is optional. If condition metadata is desired for early auto-configuration filtering, configure spring-boot-autoconfigure-processor in the module containing auto-configurations.

### 4.3. Gradle: configure annotationProcessor

With Gradle Kotlin DSL:

~~~kotlin
plugins {
    id("java-library")
}

dependencies {
    implementation("org.springframework.boot:spring-boot-autoconfigure")

    annotationProcessor(
        "org.springframework.boot:spring-boot-autoconfigure-processor"
    )
    annotationProcessor(
        "org.springframework.boot:spring-boot-configuration-processor"
    )

    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Both processors sit in the annotationProcessor configuration, never as runtime dependencies of consumers. If using an additional metadata file, ensure the compile task processes resources before the annotation processor needs to read it.

### 4.4. Author-supplied additional metadata

Processors cannot always infer default values, descriptions, or hints. You can add the file:

~~~text
META-INF/additional-spring-configuration-metadata.json
~~~

Example:

~~~json
{
  "properties": [
    {
      "name": "acme.client.retry-delays",
      "type": "java.util.List<java.time.Duration>",
      "description": "Delays used between connection attempts.",
      "defaultValue": ["1s", "3s", "5s"]
    }
  ],
  "hints": [
    {
      "name": "acme.client.mode",
      "values": [
        { "value": "sync", "description": "Use synchronous calls." },
        { "value": "async", "description": "Use asynchronous calls." }
      ]
    }
  ]
}
~~~

The sample format must match real data types and properties. Additional files are merged into the primary metadata by the processor. Do not create an empty file if there are no extra properties or hints.

### 4.5. Do not confuse metadata with imports

- AutoConfiguration.imports is the candidate list Boot uses to locate and load auto-configurations.
- spring-configuration-metadata.json helps IDEs understand properties.
- spring-autoconfigure-metadata.properties supports early condition filtering.

An artifact containing both metadata files yet lacking AutoConfiguration.imports will still go undiscovered. Conversely, auto-configurations can still run when condition-optimization metadata has not been generated; that file does not replace imports.

## 5. Verify dependency declarations and published metadata

### 5.1. Maven: autoconfigure module

Example dependencies in the POM of acme-spring-boot-autoconfigure:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-autoconfigure</artifactId>
    </dependency>

    <dependency>
        <groupId>com.acme</groupId>
        <artifactId>acme-client</artifactId>
        <version>${acme-client.version}</version>
        <optional>true</optional>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

The acme-client dependency remains on the compile/runtime classpath of the autoconfigure module itself, yet does not propagate automatically to consumers depending only on the autoconfigure module. This allows applications to opt into integrations themselves.

### 5.2. Maven: starter module

The starter declares dependencies required for the default experience:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>acme-spring-boot-autoconfigure</artifactId>
        <version>${project.version}</version>
    </dependency>

    <dependency>
        <groupId>com.acme</groupId>
        <artifactId>acme-client</artifactId>
        <version>${acme-client.version}</version>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
</dependencies>
~~~

acme-client in the starter is not optional if the starter promises to enable that integration by default. When a consumer adds only the starter, the dependency must appear on the runtime classpath.

The starter must reference spring-boot-starter directly or transitively; there is no need to declare it again if the starter already depends on another starter that brings in the core starter.

### 5.3. Gradle: distinguish compile and runtime

In the autoconfigure module:

~~~kotlin
plugins {
    id("java-library")
}

dependencies {
    implementation("org.springframework.boot:spring-boot-autoconfigure")
    compileOnly("com.acme:acme-client:4.2.0")

    annotationProcessor(
        "org.springframework.boot:spring-boot-autoconfigure-processor"
    )
    annotationProcessor(
        "org.springframework.boot:spring-boot-configuration-processor"
    )

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("com.acme:acme-client:4.2.0")
}
~~~

compileOnly lets autoconfigure code compile against the Acme API without automatically placing Acme onto the consumer's runtime classpath. Tests need the real library to exercise the integration branch, so testImplementation is included.

In the starter module:

~~~kotlin
plugins {
    id("java-library")
}

dependencies {
    api(project(":acme-spring-boot-autoconfigure"))
    implementation("com.acme:acme-client:4.2.0")
    implementation("org.springframework.boot:spring-boot-starter")
}
~~~

The example uses api(project(...)) because the consumer smoke test uses the public type AcmeOperations exposed by the autoconfigure module. If consumers only need the starter to activate beans without compiling against autoconfigure APIs, implementation(project(...)) can be used.

Choose api vs. implementation based on real public APIs. compileOnly in autoconfigure does not give runtime consumers Acme Client automatically; the starter must bring that dependency to runtime if the default feature requires it.

### 5.4. Manage versions consistently

With Maven, use the Spring Boot parent or import the spring-boot-dependencies BOM. With Gradle, use the Spring dependency management plugin or an appropriate platform/BOM.

Check:

- Autoconfigure and starter share the same release version.
- Spring Boot artifacts align on one supported release line.
- Third-party libraries are compatible with the target Spring Boot/Java versions.
- Different versions of the same library are not declared across two modules.
- Test dependencies are not leaked into the consumer's POM/runtime.
- Optional dependencies do not accidentally become required through another transitive path.

Do not rely on a dependency pulled in incidentally by another starter. If code uses a library directly, declare that dependency directly in the module that needs it.

### 5.5. Inspect POM and Gradle Module Metadata

Build file sources are not the metadata consumers read. After publishing, verify:

- Does the POM have the right groupId, artifactId, and version?
- Are compile/runtime/optional dependencies accurate?
- Are any test dependencies exposed to consumers?
- Are versions managed via dependency management still accurate?
- If using Gradle, does the .module file contain the expected variants and dependencies?

Gradle Module Metadata captures richer variant information than POMs. When publishing for multiple build tools, inspect both the POM and .module file; do not assume every consumer reads the same metadata format.

## 6. Test auto-configuration in the producer module

### 6.1. ApplicationContextRunner

Use ApplicationContextRunner to test conditions in lightweight contexts:

~~~java
private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(AcmeAutoConfiguration.class)
                );
~~~

Scenarios to include:

| Scenario | Result to verify |
| --- | --- |
| Dependency present, feature enabled by default | Default bean is created |
| Property disables feature | Default bean does not appear |
| Optional class absent | Context still starts; integration is skipped |
| User provides bean | Default bean backs off |
| Invalid property or configuration | Error/behavior matches documented contract |

To simulate a missing optional dependency:

~~~java
runner.withClassLoader(new FilteredClassLoader(AcmeClient.class))
        .run(context -> {
            assertThat(context).doesNotHaveBean("acmeOperations");
        });
~~~

This test is only meaningful if auto-configuration actually guards optional classes with class conditions and isolates required references.

### 6.2. Test property metadata

If the library has @ConfigurationProperties, verify the JSON file was generated and contains key entries:

- Does the prefix match the library's namespace?
- Are property names canonical kebab-case?
- Are descriptions clear and free of markup?
- Are default values accurate?
- Do types match Java fields/record components?
- Do hints for enums/lists reflect real choices?

Incorrect metadata can cause wrong IDE suggestions even when runtime binding still works. This is why inspecting the compiled artifact matters, not just reviewing source Javadoc.

### 6.3. Check the producer's actual classpath

In the autoconfigure module, run:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dincludes=com.acme:acme-client
~~~

In Gradle:

~~~bash
./gradlew :acme-spring-boot-autoconfigure:dependencies --configuration compileClasspath
./gradlew :acme-spring-boot-autoconfigure:dependencies --configuration runtimeClasspath
~~~

Confirm Acme Client is on the producer module's classpath for compiling/testing. Then verify a separate consumer in the next section; a passing producer does not prove optional dependencies propagate properly.

## 7. Inspect JAR contents after building

### 7.1. Clean artifact build

Maven:

~~~bash
mvn clean verify
~~~

Gradle:

~~~bash
./gradlew clean build
~~~

Do not run compile only. verify/build must execute tests and packaging steps.

### 7.2. List JAR contents

Use JDK jar:

~~~bash
jar tf acme-spring-boot-autoconfigure/target/acme-spring-boot-autoconfigure-1.0.0.jar
~~~

Look for the corresponding entries:

~~~text
com/acme/boot/autoconfigure/AcmeAutoConfiguration.class
com/acme/boot/autoconfigure/AcmeProperties.class
META-INF/MANIFEST.MF
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
META-INF/spring-autoconfigure-metadata.properties
META-INF/spring-configuration-metadata.json
~~~

The two processor metadata files appear only when the module configures those processors and has content to generate. Do not conclude a build is broken simply because an optional metadata file was omitted when the project didn't need it; however, imports must be present if the artifact registers auto-configurations.

Inspect imports contents by extracting the resource into a temp directory or using a ZIP reader:

~~~bash
unzip -p acme-spring-boot-autoconfigure/target/acme-spring-boot-autoconfigure-1.0.0.jar META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

The output must list the exact class names, one per line. Compare against the actual classes inside the JAR; a wrong package or class name prevents Boot from loading the configuration.

### 7.3. Inspect the starter JAR

A starter is normally an almost empty JAR. Verify:

- No copies of Acme or Spring dependencies are bundled inside the starter JAR.
- The starter's POM/Gradle metadata declares the required dependencies.
- The starter was not repackaged into an executable archive by the Spring Boot Maven Plugin.
- The artifact has the right coordinates and version.

If BOOT-INF/classes and BOOT-INF/lib appear inside the starter JAR, check whether the repackage plugin was mistakenly applied to the library module.

### 7.4. Inspect the consumer's executable JAR

A consumer application packaged with the Spring Boot Maven Plugin typically contains:

~~~text
BOOT-INF/classes/
BOOT-INF/lib/
org/springframework/boot/loader/
META-INF/MANIFEST.MF
~~~

The manifest has Main-Class pointing to the Boot loader and Start-Class pointing to the main application class. This is the structure of an executable application JAR, distinct from a starter library JAR.

Test running it:

~~~bash
java -jar consumer-app/target/consumer-app-1.0.0.jar
~~~

If the app runs from an IDE yet fails from the JAR, inspect resources and dependencies inside the packaged archive rather than only the IDE classpath.

### 7.5. Be careful when building shaded/uber JARs

If using the Maven Shade Plugin or another tool that builds a single uber-JAR by merging dependencies, resources at the same path can overwrite each other. Multiple libraries can contain AutoConfiguration.imports.

You must configure resource transformers to merge imports lists, while checking which metadata files must be preserved. With standard Spring Boot executable JARs, the Boot loader keeps dependencies as nested JARs under BOOT-INF/lib, avoiding the need to merge all resources into a single uber-JAR.

## 8. Test with an independent consumer application

This step proves the starter works after packaging and publishing.

### 8.1. Consumer declares only the starter

The consumer POM should declare the starter and test dependency. Do not declare acme-client directly if the goal is verifying the starter brings that dependency to runtime:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>acme-spring-boot-starter</artifactId>
        <version>1.0.0</version>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

If the consumer must add Acme Client directly just to start, review the starter POM or the optional dependency in the autoconfigure module.

### 8.2. Consumer application

~~~java
package example.consumer;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ConsumerApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConsumerApplication.class, args);
    }
}
~~~

Do not import AcmeAutoConfiguration directly and do not use @Import to rescue the test. The goal is proving Spring Boot discovers the auto-configuration automatically from resources in dependency JARs.

### 8.3. Consumer smoke test

Suppose the autoconfigure module exposes the public interface AcmeOperations:

~~~java
package example.consumer;

import example.acme.AcmeOperations;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class StarterSmokeTests {

    @Autowired
    private AcmeOperations operations;

    @Test
    void starterProvidesTheDefaultIntegration() {
        assertThat(operations).isNotNull();
        assertThat(operations.health()).isEqualTo("ready");
    }
}
~~~

The consumer uses only the public API of the starter/autoconfigure. It does not need to import internal types from the Acme library if the starter's API wraps that dependency.

If the library is designed for consumers to call AcmeClient directly, consumers must declare that dependency directly or the starter must expose it on the compile classpath per the published contract. Never leave consumers accidentally relying on transitive implementation details.

### 8.4. Test a consumer without the optional integration

If a user adds only the autoconfigure module without Acme Client, create a separate consumer scenario. The application must start up and the optional integration bean must not be created.

You can use a separate test project depending only on autoconfigure, or use FilteredClassLoader in auto-configuration tests. A standalone consumer project proves both dependency metadata and runtime startup.

### 8.5. Install artifacts into the local Maven repository before testing the consumer

A practical Maven workflow:

~~~bash
mvn -pl acme-spring-boot-autoconfigure,acme-spring-boot-starter -am clean install
mvn -f samples/consumer-app/pom.xml clean verify
~~~

The first command builds and installs the modules and internal dependencies into the local Maven repository. The second builds the independent consumer, resolving artifacts strictly by published coordinates.

Use a dedicated test version or controlled SNAPSHOT version to avoid accidentally testing stale artifacts from the local repository. Consumer tests must point to the exact groupId/artifactId/version just built.

### 8.6. Inspect the consumer's dependency tree

~~~bash
mvn -f samples/consumer-app/pom.xml dependency:tree
mvn -f samples/consumer-app/pom.xml dependency:tree -Dincludes=com.acme:acme-client
~~~

Expected result when using the standard starter:

- Consumer receives acme-spring-boot-autoconfigure.
- Consumer receives acme-client via the starter's direct declaration.
- Consumer receives spring-boot-starter directly or via another starter.
- Dependency scopes/versions match runtime goals.
- No unexpected Acme version is pulled in by another transitive branch.

If the consumer depends only on the autoconfigure module, optional Acme Client does not appear automatically through that module. This is an important check confirming optional dependencies work properly.

## 9. Verify publishing with Gradle

When publishing with Gradle, use java-library for library modules and maven-publish to create publications:

~~~kotlin
plugins {
    id("java-library")
    id("maven-publish")
}

group = "com.example"
version = "1.0.0"

publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            from(components["java"])
        }
    }
}
~~~

Install artifacts into the local Maven repository:

~~~bash
./gradlew :acme-spring-boot-autoconfigure:publishToMavenLocal
./gradlew :acme-spring-boot-starter:publishToMavenLocal
~~~

Then use an independent Maven consumer or Gradle consumer to resolve the published coordinates.

Check publications:

- JAR contains AutoConfiguration.imports.
- POM reflects accurate dependencies and scopes.
- .module file has expected compile/runtime variants.
- Annotation processors are not published as runtime dependencies.
- compileOnly does not accidentally become a consumer runtime dependency.
- api is used only when consumers genuinely need that dependency/type on the compile classpath.

With Gradle, you can inspect:

~~~bash
./gradlew :consumer-app:dependencies --configuration compileClasspath
./gradlew :consumer-app:dependencies --configuration runtimeClasspath
./gradlew :consumer-app:dependencyInsight --dependency acme-client --configuration runtimeClasspath
~~~

When using a Maven consumer to read Gradle publications, inspect the generated POM. When using a Gradle consumer, inspect Gradle Module Metadata as well because it captures more variant details than a POM.

## 10. Stage-by-stage release checklist

### 10.1. Before building

- [ ] Finalize groupId, artifactId, version, and module names with a dedicated namespace.
- [ ] Finalize minimum Java version and supported Spring Boot release line.
- [ ] Clearly separate autoconfigure module, starter module, and consumer sample.
- [ ] Identify which dependencies are required vs. optional.
- [ ] Identify which APIs are published to consumers vs. implementation details.
- [ ] Manage Spring Boot and third-party versions via BOM/parent/version catalog.
- [ ] Ensure no SNAPSHOT versions remain in official releases.

### 10.2. Auto-configuration imports

- [ ] META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports exists in the autoconfigure module.
- [ ] Each candidate is a fully qualified class name on its own line.
- [ ] Class names match compiled packages and classes.
- [ ] Classes are not registered via component scanning.
- [ ] @Import is used for required supporting configurations.
- [ ] Appropriate conditions guard classpath, properties, and user beans.
- [ ] Optional types are isolated inside nested configurations when needed.
- [ ] Ordering uses @AutoConfigureBefore, @AutoConfigureAfter, or corresponding attributes with clear justification.
- [ ] If published classes were renamed, imports and replacements files are updated accordingly.
- [ ] Do not rely on legacy EnableAutoConfiguration keys in spring.factories.

### 10.3. Metadata

- [ ] spring-boot-configuration-processor is configured if the module has @ConfigurationProperties.
- [ ] spring-boot-autoconfigure-processor is configured if condition metadata is needed for early filtering.
- [ ] Processors are declared in annotationProcessor paths/configurations.
- [ ] Property Javadoc has clear descriptions using a dedicated namespace.
- [ ] META-INF/spring-configuration-metadata.json is generated when needed.
- [ ] META-INF/spring-autoconfigure-metadata.properties is generated if autoconfigure processor is used.
- [ ] Manual metadata resides in META-INF/additional-spring-configuration-metadata.json.
- [ ] Metadata reflects accurate types, defaults, deprecations, and hints.
- [ ] Metadata was inspected inside the packaged JAR, not only in target/classes or build/classes.

### 10.4. Dependencies and publication

- [ ] Acme dependency in autoconfigure is optional/compile-only when required by design.
- [ ] Starter directly declares dependencies required for the default experience.
- [ ] Starter includes spring-boot-starter directly or transitively.
- [ ] Test dependencies are not exposed to consumers.
- [ ] api is used only when public APIs require compile dependencies.
- [ ] implementation is used for implementation details.
- [ ] POM or Gradle Module Metadata has accurate dependencies/scopes/variants.
- [ ] No unexpected version conflicts exist.
- [ ] Boot repackage is not used on library/starter modules.

### 10.5. Testing

- [ ] Unit test conditions with ApplicationContextRunner.
- [ ] Test defaults, property overrides, and disabled feature state.
- [ ] Test user beans causing default bean back-off.
- [ ] Test missing optional dependencies with FilteredClassLoader.
- [ ] Test property binding and metadata of @ConfigurationProperties.
- [ ] Test the consumer's classpath, not only the producer's.
- [ ] Consumer smoke test exists without importing auto-configuration directly.
- [ ] Consumer scenario omitting optional dependency exists when proving optionality.
- [ ] Tests pass on published supported Java/Spring Boot versions.

### 10.6. Artifact verification and release

- [ ] mvn clean verify or ./gradlew clean build succeeds.
- [ ] JAR contains required classes and resources.
- [ ] Imports file has exact expected contents.
- [ ] Metadata is packaged.
- [ ] Starter JAR was not repackaged into an executable archive.
- [ ] POM/.module inspected after publishing.
- [ ] Independent consumer resolves the exact version from local/staging repository.
- [ ] Consumer starts up and feature tests pass.
- [ ] Consumer executable JAR runs via java -jar.
- [ ] Release notes, sources, Javadoc, license, checksums, or signatures included per repository policy.

## 11. Common mistakes when releasing a starter

1. **Imports file at the wrong path.** Source contains auto-configuration yet Boot fails to discover it in consumers. Verify the exact resource path in the JAR.
2. **Testing only with AutoConfigurations.of(...).** That test loads classes directly, so it does not prove the imports file was packaged. Add a consumer smoke test.
3. **Using spring.factories per old Boot 2 guides.** Boot 3 uses AutoConfiguration.imports for auto-configuration candidates.
4. **Auto-configuration gets component scanned.** Beans may appear twice or depend on application packages. Register strictly via imports.
5. **Missing class condition for optional library.** Consumers not using the feature can still hit class-loading errors.
6. **Optional dependency in autoconfigure not re-added in starter.** Consumers add the starter yet lack required runtime libraries.
7. **Marking required dependencies optional.** Applications adding only the starter may miss classes at runtime.
8. **Confusing the two metadata processors.** Configuration metadata assists IDEs; autoconfigure metadata speeds condition filtering. Neither replaces the imports file.
9. **Putting processors as runtime dependencies.** Processors are compile-time only; declare them in annotationProcessor paths.
10. **Metadata lacking accurate descriptions or defaults.** IDEs show wrong or missing hints; inspect JSON after compiling.
11. **Starter pulls in too many optional integrations.** Runtime classpath bloats and invites version conflicts; split starters by feature.
12. **Using api for every dependency.** Consumer compile classpath exposes implementation details and increases coupling.
13. **Using implementation when public APIs require the dependency type.** Consumers fail to compile when calling APIs exposing that type.
14. **Inspecting only the producer's dependency tree.** Published consumer POM/Gradle metadata may differ from expectations; inspect from a consuming project.
15. **Accidentally repackaging the starter JAR.** The library turns into a nested executable archive and ceases to be a normal dependency JAR.
16. **Consumer tests import auto-configuration directly.** That masks broken imports files. Let Spring Boot auto-discover via classpath.
17. **Running tests only inside the reactor.** Consumers can accidentally resolve internal project dependencies instead of published artifacts. Test an independent project against installed/published versions.
18. **Shade JAR overwrites imports resources.** Multiple files at the same path can get lost during archive merging; merge resources properly.
19. **Renaming auto-configurations while forgetting replacements/ordering/excludes.** Can break downstream configurations.
20. **Not running the executable JAR.** IDEs or spring-boot:run may use a different classpath from the final artifact; test java -jar on the consumer.

## 12. Repeatable sample release workflow

With multi-module Maven, a release pipeline can run:

~~~bash
# 1. Build and test all modules
mvn clean verify

# 2. Install artifacts into the local repository for an independent consumer
mvn -pl acme-spring-boot-autoconfigure,acme-spring-boot-starter -am clean install

# 3. Test an independent consumer depending only on the starter
mvn -f samples/consumer-app/pom.xml clean verify

# 4. Inspect the consumer's dependency tree
mvn -f samples/consumer-app/pom.xml dependency:tree

# 5. Build the consumer's executable JAR
mvn -f samples/consumer-app/pom.xml package

# 6. Run the executable JAR
java -jar samples/consumer-app/target/consumer-app-1.0.0.jar
~~~

After building, inspect the autoconfigure JAR with jar tf and read the imports file directly. If the consumer passes in the IDE yet fails from the executable JAR, compare BOOT-INF/lib contents, imports resources, and the manifest of the packaged JAR.

In CI, run the pipeline with a clean repository or controlled cache so consumers never accidentally resolve stale artifacts from local Maven.

## 13. Self-check questions

**Question 1.** In which file does Spring Boot 3 look for auto-configuration candidates?  
**Answer:** META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports inside published JARs.

**Question 2.** What format does each line in the imports file use?  
**Answer:** The fully qualified class name of one auto-configuration class; one class per line, optionally with comments starting with #.

**Question 3.** Is spring.factories still the Boot 2 way to register auto-configurations?  
**Answer:** No. Boot 3 uses AutoConfiguration.imports for auto-configuration candidates; spring.factories remains for other extension points.

**Question 4.** Which file does spring-boot-configuration-processor generate?  
**Answer:** META-INF/spring-configuration-metadata.json, providing metadata and IDE assistance for @ConfigurationProperties.

**Question 5.** Which file does spring-boot-autoconfigure-processor generate?  
**Answer:** META-INF/spring-autoconfigure-metadata.properties, helping Spring Boot filter auto-configurations early by conditions.

**Question 6.** Why are external library dependencies often optional in the autoconfigure module?  
**Answer:** So consumers using only autoconfigure can choose whether to bring that library onto the classpath; the standard starter declares required dependencies directly.

**Question 7.** Why shouldn't repackage be used on a starter JAR?  
**Answer:** A starter is a library/dependency bundle, not an executable application. Repackage creates a nested JAR layout with BOOT-INF meant for applications launched with java -jar.

**Question 8.** Are ApplicationContextRunner tests alone enough to prove the imports file is correct?  
**Answer:** No, if tests pass classes directly via AutoConfigurations.of(...). You must inspect the artifact and run an independent consumer to prove Boot discovers it from the JAR.

**Question 9.** Why must POM or Gradle Module Metadata be inspected?  
**Answer:** Because consumers resolve dependencies from published metadata, not from the producer's build scripts.

**Question 10.** If a consumer adds only the starter yet lacks Acme Client at runtime, what must be checked?  
**Answer:** Check whether the starter POM/Gradle metadata declares Acme Client directly and non-optionally, and whether the consumer's runtime dependency tree contains it.

## Official references

- Spring Boot 3.5 Reference — Creating Your Own Auto-configuration, imports file, conditions, testing, and custom starters: https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
- Spring Boot 3.5 Reference — Configuration Metadata: https://docs.spring.io/spring-boot/3.5/specification/configuration-metadata/index.html
- Spring Boot — Generating Your Own Metadata by Using the Annotation Processor: https://docs.spring.io/spring-boot/3.5/specification/configuration-metadata/annotation-processor.html
- Spring Boot 3.5 Maven Plugin — Packaging Executable Archives: https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html
- Spring Boot 3.5 — Executable Jar Format: https://docs.spring.io/spring-boot/3.5/specification/executable-jar/index.html
- Gradle — The Java Library Plugin: https://docs.gradle.org/current/userguide/java_library_plugin.html
- Gradle — The Maven Publish Plugin: https://docs.gradle.org/current/userguide/publishing_maven.html
- Gradle — Gradle Module Metadata: https://docs.gradle.org/current/userguide/publishing_gradle_module_metadata.html

**Takeaway:** A starter is ready for release only when the autoconfigure JAR contains the exact AutoConfiguration.imports, property/condition metadata is generated and packaged, dependency metadata reflects accurate compile/runtime/optional scopes, condition tests pass, and an independent consumer declaring only the starter starts up cleanly. Always inspect published artifacts rather than relying solely on a passing producer build.
