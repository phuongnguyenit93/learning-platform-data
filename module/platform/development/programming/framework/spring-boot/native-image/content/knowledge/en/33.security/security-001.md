# Data Read During Build Initialization Can Become Part of the Image Heap

GraalVM Native Image can execute a portion of code while creating an executable. If a class's static initializer runs at build time, the resulting static state can be stored in the **image heap** and travel with the binary to the deployment environment. This is useful when the data is a safe constant, but becomes a risk if the class initializer reads passwords, API tokens, private keys, build environment information, or data that should only be fetched when the application starts.

A native executable can therefore contain sensitive data even though the source code has no literal secrets. For example, a class that reads an environment variable in a static initializer and assigns it to a static field can bake values from the CI machine into the image if the class is initialized during the build.

This article explains the image heap, class initialization, the difference between Spring AOT and GraalVM build-time initialization, how to move sensitive classes to runtime initialization, how to load secrets safely for Spring Boot, and how to inspect artifacts before release.

## 1. Build time, runtime, and the image heap

Native Image does not merely compile bytecode. During analysis and executable creation, the builder can execute Java code. Those operations are called **build-time execution**. When a class is initialized at this stage, its static initializer runs on the JVM of the build process.

The image heap is the initial state region packaged inside the native executable. It can contain:

- Objects created during the build that remain reachable from application code.
- Static state of classes that were initialized at build time.
- Constant objects embedded in method code.
- Metadata and objects used by the runtime.

When the executable starts, the initial image heap is loaded into the runtime. Therefore, data can exist in the binary before the application receives any request or runtime configuration.

Not every temporary object created during the build is retained. An object only remains in the image if it is reachable from roots that Native Image preserves, such as static fields or embedded constants. However, if a static field holds a reference to a secret, the entire object graph reachable from that field can become part of the image.

### Data lifecycle diagram

~~~mermaid
flowchart TD
    A["CI build environment"] --> B["native-image builder"]
    B --> C["Class initializer runs at build time"]
    C --> D["Reads property, env, file, or other data"]
    D --> E["Assigned to static field / reachable object"]
    E --> F["Image heap"]
    F --> G["Native executable is released"]
    G --> H["Runtime on target machine"]
    H --> I["Build-time data still persists"]
    J["Runtime environment / secret store"] --> K["Runtime initialization"]
    K --> L["Application receives configuration for deployment environment"]
~~~

For example, if a static initializer reads System.getProperty("partner.token") during the build and the class is initialized at build time, that value can be stored in the image heap. When running the executable, passing a different system property does not necessarily change the static field that was already snapshotted.

## 2. When is a class initialized at build time?

In Java, a class is initialized when it is first used according to JVM rules. With Native Image, application classes are initialized at runtime by default, except for classes that Native Image proves are safe to initialize at build time. JDK classes and certain runtime classes have their own policies.

A class can be initialized at build time when:

- Explicitly specified with --initialize-at-build-time.
- Its static initializer is invoked by a class that is already initialized at build time.
- Native Image determines the initializer is safe according to compiler analysis.
- A framework or library contributes class-initialization configuration.

For example, the following configuration instructs the builder to initialize a specific class while creating the image:

~~~bash
native-image \
  --initialize-at-build-time=com.example.catalog.StaticCatalog \
  -cp target/classes \
  com.example.catalog.Application
~~~

When a class is initialized at build time, assigned static fields can become state inside the executable. If the initializer reads data from the build environment, the binary can carry that data with it.

### Do not confuse class loading with class initialization

The JVM can load a class without running its static initializer. A class appearing on the classpath or being referenced in bytecode does not automatically mean its static initializer ran at build time.

What needs to be investigated is the **class initialization policy** and when the initializer is actually executed. Use diagnostics to determine the cause instead of inferring solely from the class's presence in the image.

## 3. Example: a system property snapshotted into the image

Create a class with a static field that reads a system property:

~~~java
package com.example.security;

public final class BuildSnapshot {

    private static final String MARKER;

    static {
        MARKER = System.getProperty("demo.marker", "unset");
    }

    private BuildSnapshot() {
    }

    public static String marker() {
        return MARKER;
    }
}
~~~

The application prints the value:

~~~java
package com.example;

import com.example.security.BuildSnapshot;

public class Application {

    public static void main(String[] args) {
        System.out.println(BuildSnapshot.marker());
    }
}
~~~

Build the native image with an illustrative value, not a secret:

~~~bash
native-image \
  --initialize-at-build-time=com.example.security.BuildSnapshot \
  -Ddemo.marker=build-value \
  -cp target/classes \
  com.example.Application
~~~

Run the executable with a different value:

~~~bash
./application -Ddemo.marker=runtime-value
~~~

If BuildSnapshot was initialized during the build, the program still prints build-value. The static field was created and snapshotted into the image heap; the runtime property does not re-run that initializer.

This is a pattern that can cause leaks if demo.marker is replaced with a database password, API token, encryption key, or identifying information about the build environment.

### How to fix a class that needs runtime data

Instruct the class to be initialized only when the executable runs:

~~~bash
native-image \
  --initialize-at-run-time=com.example.security.BuildSnapshot \
  -cp target/classes \
  com.example.Application
~~~

The initializer then runs at runtime and reads the native process's system property. This is a technical measure for a specific class; a better design is still to avoid holding secrets in static fields.

## 4. Data that should not be snapshotted

Review any data that can change between build and deployment, especially:

| Data | Why it should not be snapshotted |
| --- | --- |
| Database password | May be a build or staging environment credential, not production |
| API token, OAuth client secret | The binary can be copied and the token can be extracted |
| Private key, HMAC key, encryption key | Key exposure can allow signature forgery or data decryption |
| Secret manager response | May return secrets scoped to the build agent's identity |
| Random seed, nonce state | Can become fixed across multiple executables or replicas |
| Hostname, IP, region, tenant ID | Ties the binary to the build machine or build environment |
| License token | Can be distributed with the artifact and reused out of scope |
| Organization-private file paths or certificates | Can make the binary depend on build infrastructure or leak internal details |

Not every configuration value is a secret. Constants such as metric names, protocol formats, or public lookup tables are generally suitable for snapshotting if they do not contain environment-specific data.

Practical rule: if a value must differ across dev, staging, production, tenants, or replicas, read it at runtime rather than in a static initializer.

## 5. Distinguishing Spring AOT from GraalVM build-time initialization

Both mechanisms contain the words AOT/build time, yet they perform different tasks.

**Spring AOT** analyzes the ApplicationContext during the build, evaluates configurations and bean conditions, and generates Java source, bytecode, and RuntimeHints so the application starts more efficiently. Some bean graph decisions are fixed based on the classpath and Environment at build time.

**GraalVM Native Image build-time initialization** executes a class's static initializer while creating the native executable. Static state and reachable objects are retained in the image heap.

The two mechanisms can appear in the same pipeline, but they are not synonymous:

| Mechanism | Produced output | Risk to manage |
| --- | --- | --- |
| Spring AOT processing | Generated code, bytecode, hints, and bean graph decisions | Profiles/conditions depending on the build-time Environment |
| GraalVM class initialization | Static state and objects retained in the image heap | Secrets or build-environment state may be snapshotted |
| Native Image resource inclusion | Files/resources packaged into the executable | Configuration files or certificates not meant for distribution may be embedded |
| Build argument/system property | Values passed to the builder process | May appear in logs, process metadata, or be read by a static initializer |

You should not conclude that every Spring property read during processAot automatically becomes a secret in the image heap. Spring AOT generally generates bean structures and initialization code; the image heap is Native Image's object storage mechanism. However, if a callback, processor, or static initializer reads a secret during the build, or a value is written into generated source/resources, the data can still be packaged that way.

### What is fixed in Spring AOT?

Spring AOT evaluates conditions that affect the bean graph, such as @Profile and @ConditionalOnProperty, in the build environment. Beans selected during AOT processing may still be registered when running the executable, even if the runtime environment differs.

Therefore:

- Use runtime properties for endpoints, timeouts, passwords, and tokens of already-created beans.
- Do not use secret values as conditions deciding whether a bean exists.
- Select build-time profiles and feature conditions according to an explicit deployment design.
- Do not call a secret manager or database from an AOT callback just to construct the bean graph.

## 6. Designing Spring Boot to read secrets at runtime

Avoid the following declaration:

~~~java
public final class PartnerCredentials {

    public static final String API_TOKEN =
            System.getenv("PARTNER_API_TOKEN");

    private PartnerCredentials() {
    }
}
~~~

If this class is initialized at build time, the token can be held in the static field and packaged into the image.

Use configuration injected into beans instead:

~~~java
package com.example.partner;

import java.net.URI;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "partner")
public record PartnerProperties(
        URI endpoint,
        String apiToken
) {
}
~~~

Register the properties:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Inject into a service:

~~~java
@Service
public class PartnerClient {

    private final PartnerProperties properties;

    public PartnerClient(PartnerProperties properties) {
        this.properties = properties;
    }

    public void submit(Order order) {
        String endpoint = properties.endpoint().toString();
        String token = properties.apiToken();

        // Send request using a configured HTTP client.
        // Do not log the token or include the token in exception messages.
    }
}
~~~

Configure the non-sensitive endpoint in application.yml:

~~~yaml
partner:
  endpoint: https://partner.example.internal
~~~

Supply the token via an environment variable at runtime:

~~~bash
# The deployment platform injects PARTNER_API_TOKEN from its secret store
# when the native process starts. No literal token is stored in the image.
~~~

Spring Boot relaxed binding maps PARTNER_API_TOKEN to partner.api-token. The value is obtained from the native process's environment when the runtime bean configuration is bound.

### Using secrets mounted as files

In containers or Kubernetes, secrets can be mounted as files. Spring Boot supports config trees:

~~~properties
spring.config.import=optional:configtree:/run/secrets/
~~~

If the directory contains a file named partner.api-token, the file contents are mapped to the property partner.api-token. Mount the secret into the container at runtime so the same binary can use different credentials per environment.

Do not place secret files in the source tree, Docker build context, executable JAR, resource directory, or native-image builder container.

## 7. Moving sensitive classes to runtime initialization

If an existing library or class reads sensitive data in a static initializer, you can instruct GraalVM to defer initialization of that class.

### Native Image command line

~~~bash
native-image \
  --initialize-at-run-time=com.example.security.SecretBootstrap \
  -cp target/classes \
  com.example.Application
~~~

Multiple classes can be specified as a comma-separated list:

~~~bash
native-image \
  --initialize-at-run-time=com.example.security.SecretBootstrap,com.example.crypto.RuntimeKeyProvider \
  -cp target/classes \
  com.example.Application
~~~

Packages can be specified, but package rules affect more classes. Prefer specific classes to limit performance impact and avoid changing the initialization policy of unrelated components.

### Maven Native Build Tools

Add the argument to the configuration of the plugin in use:

~~~xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <configuration>
        <buildArgs>
            <buildArg>--initialize-at-run-time=com.example.security.SecretBootstrap</buildArg>
        </buildArgs>
    </configuration>
</plugin>
~~~

If the POM already has native-maven-plugin, add the argument to the existing configuration instead of declaring a duplicate plugin.

### Gradle Native Build Tools

Groovy DSL example:

~~~groovy
graalvmNative {
    binaries {
        named("main") {
            buildArgs.add(
                "--initialize-at-run-time=com.example.security.SecretBootstrap"
            )
        }
    }
}
~~~

Kotlin DSL example:

~~~kotlin
graalvmNative {
    binaries {
        named("main") {
            buildArgs.add(
                "--initialize-at-run-time=com.example.security.SecretBootstrap"
            )
        }
    }
}
~~~

Binary names and DSL may vary by plugin configuration/version. Confirm the option is actually passed to Native Image by checking the build log.

### Notes on class hierarchy

Class initialization policy is affected by superclasses, superinterfaces with default methods, and related subclasses. When moving a class to runtime initialization, related classes may also be affected according to Native Image rules.

In addition, instances of a runtime-initialized class must not already exist in the image heap. If the class was already initialized or an instance was created during the build, simply adding the runtime option can trigger an error. Find where the class is initialized early and remove that instance creation from the build-time path.

Do not add --initialize-at-build-time for entire packages or the entire application just to speed up builds. Only allow build-time initialization for classes verified not to read secrets, not to depend on the build machine, and not to create runtime state that needs refreshing.

## 8. TrustStore as a special case

GraalVM Native Image by default captures the build host's TrustStore and embeds its contents into the executable. If built on a machine with an internal root CA, the binary can carry that certificate bundle when released.

This can be useful if all deployments must use the same trust anchor. However, it can create issues:

- The binary is tied to the build machine's trust configuration.
- Updating root CAs on the runtime machine does not necessarily update the captured TrustStore.
- Internal certificates can disclose information about organizational infrastructure.
- Different environments may require different truststores.

You can select a TrustStore file at build time using the javax.net.ssl.trustStore system property. If you want to replace the TrustStore at runtime, configure the javax.net.ssl.trustStore* system properties and ensure the TrustStore file exists and is readable in the runtime filesystem.

When one of the runtime properties such as javax.net.ssl.trustStoreType, javax.net.ssl.trustStoreProvider, or javax.net.ssl.trustStorePassword is set, GraalVM also requires javax.net.ssl.trustStore to point to an accessible file. Otherwise, the runtime may throw UnsupportedFeatureError.

A TrustStore contains public certificates, which is not the same as a private key. Do not embed private keys or keystore passwords into the image. If mTLS is needed, supply the private key/keystore via a secret mount or secret manager at runtime.

## 9. Building in an environment without production secrets

GraalVM recommends running the Native Image builder in a dedicated build environment, such as a container, that does not contain sensitive data in the first place.

A secure pipeline should:

1. Use a dedicated runner/build container for native builds.
2. Not put production API tokens, database passwords, or private keys into the build job's environment.
3. If credentials are needed to download dependencies, provide them only during the dependency-fetch step and revoke them from the environment before running Native Image.
4. Not pass secrets via -D arguments or the command line if tooling might record arguments in logs.
5. Not place secrets in packaged properties files, resource folders, or the Docker build context.
6. Not upload build logs, heap reports, or intermediate files that might contain secrets to public locations.
7. Use artifact repositories and release storage with restricted access permissions.

A builder container is not automatically safe if it receives the entire CI environment or mounts a directory containing secrets. What matters is that the Native Image process cannot see production secrets during the build.

### Separating build credentials from runtime credentials

Credentials used to download artifacts from a Maven repository are build credentials. Tokens used to call a payment service or database are runtime credentials. These two types require different scopes, lifetimes, and permissions.

If the builder needs access to a private dependency repository, use a short-lived, package-read-only token that only exists during the dependency download step. Do not reuse that token as an application credential.

## 10. Detecting early-initialized classes and inspecting the image heap

### Printing the class initialization report

GraalVM provides a diagnostic option to trace class initialization:

~~~bash
native-image \
  -H:+PrintClassInitialization \
  -cp target/classes \
  com.example.Application
~~~

The report helps identify which classes are initialized at build time or runtime and the associated reasons/policies. Use it to spot sensitive classes appearing in the build-time initialized group.

This is a diagnostic for class initialization, not an automated tool to detect every secret in a binary. Combine it with source code review, build environment review, and runtime testing.

### Native Image Build Report

On GraalVM editions that support Build Report, you can add:

~~~bash
native-image \
  --emit build-report \
  -H:+PrintClassInitialization \
  -cp target/classes \
  com.example.Application
~~~

Build Report has an Image Heap section that lets you view object types, counts, and sizes; you can search for specific classes to check whether instances are in the image heap. The Resources section helps inspect which files were embedded. Build Report does not display the contents of every field, so it does not prove a binary contains no secrets.

Build Report is not available in GraalVM Community Edition. For editions that do not support the report, use class initialization diagnostics, build output, and separate testing procedures.

### Inspecting binary contents

Do not rely on a single strings command to conclude an artifact is clean. Secrets can be encoded, split, compressed, or stored in another object representation. Conversely, a string appearing in the binary is not necessarily an active credential.

String searching can be used as a secondary check with dummy marker values in a lab environment, but controlling data sources and class initialization remains the primary safeguard.

## 11. Audit workflow for a native build

When reviewing an artifact at risk of containing build-time data, proceed in order:

| Step | What to verify | Evidence |
| --- | --- | --- |
| 1. Review source | Do static initializers, static fields, and build-time callbacks read secrets? | Code review, grepping APIs that access environment/files/network |
| 2. Review build environment | Can the Native Image process see production secrets? | CI environment allowlist, container mounts, job permissions |
| 3. Review class initialization | Are sensitive classes initialized at build time? | -H:+PrintClassInitialization |
| 4. Review image heap | Are there instances of classes containing sensitive data? | Build Report Image Heap if supported by edition |
| 5. Review resources | Which secret files, private configs, or truststores are embedded? | Build Report Resources, embedded resource metadata |
| 6. Runtime test | Are runtime secrets loaded according to the deployment environment? | Test with two different marker values |
| 7. Artifact review | Are artifacts, logs, and intermediates public or overly shared? | Access policy, checksum, retention, and provenance |

If a real credential is discovered in an image, treat that credential as compromised. Revoke/rotate the credential, rebuild the binary from a clean environment, and assess any distributed artifacts/logs.

## 12. Common pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Native binary still uses CI token after deployment | Static field was snapshotted at build time | Move secret to runtime configuration and runtime initialization |
| Changing environment variable at runtime does not change value | Class was initialized early and static field is already in the image heap | Check class initialization report and use --initialize-at-run-time for the appropriate class |
| Native build fails when moving class to runtime initialization | Class instance is still created on a build-time path or hierarchy conflicts | Find the initializer/callback creating the instance; adjust class policy and dependencies |
| Production profile does not enable expected beans | Spring AOT evaluated profiles/conditions at build time | Select profiles during AOT processing and design the bean graph appropriately |
| Runtime TrustStore differs from expected | Native Image captured the build host's TrustStore | Configure runtime TrustStore and mount the corresponding file |
| Runtime throws UnsupportedFeatureError when setting truststore properties | Missing runtime TrustStore file or inaccessible path | Set javax.net.ssl.trustStore pointing to an existing file |
| Secret not found in build output | Secret was compressed/encoded or not stored in an easily searchable string form | Do not rely on strings; check source, class initialization, and build environment |
| Build report lacks Image Heap tab | Edition does not support Build Report | Use diagnostics and tools appropriate for the GraalVM edition |

## 13. Hands-on lab: proving build-time data differs from runtime data

The goal is to create a demo class that reads a system property in a static initializer, then observe the difference between build-time initialization and runtime initialization. Use only a dummy marker, never a real credential.

### Part A — create the demo class

Use the BuildSnapshot class from section 3. Build the class with Maven or Gradle so the class file is in the output directory.

### Part B — build with build-time initialization

~~~bash
native-image \
  --initialize-at-build-time=com.example.security.BuildSnapshot \
  -Ddemo.marker=build-value \
  -cp target/classes \
  com.example.Application
~~~

Run:

~~~bash
./application -Ddemo.marker=runtime-value
~~~

Record the output. The value remains build-value because the static field was created at build time.

### Part C — build with runtime initialization

Delete the old executable or use a different output name, then rebuild:

~~~bash
native-image \
  --initialize-at-run-time=com.example.security.BuildSnapshot \
  -cp target/classes \
  com.example.Application
~~~

Run with the runtime value:

~~~bash
./application -Ddemo.marker=runtime-value
~~~

This time the output is runtime-value, because the class initializer runs when the executable uses the class at runtime.

### Part D — apply to Spring Boot

1. Create a ConfigurationProperties record containing an endpoint and an API token.
2. Inject the properties into a service via constructor.
3. Supply the token via an environment variable or config tree at runtime.
4. Confirm no static field reads the token.
5. Create a separate demo class with a static initializer reading a marker to test class initialization diagnostics.
6. Build native with -H:+PrintClassInitialization.
7. If the GraalVM edition supports it, add --emit build-report and review Image Heap/Resources.
8. Run the same binary in two environments with two different markers and confirm runtime configuration is loaded per environment.
9. Review the CI job to ensure production secrets are not present in the native-image process.

### Self-check questions

1. What kinds of objects does the image heap contain?
2. Why can a static field assigned in a build-time initializer end up in the executable?
3. How does loading a class differ from initializing a class?
4. What data can --initialize-at-build-time expose?
5. Why are not all temporary objects created during the build kept in the image heap?
6. How does Spring AOT differ from GraalVM build-time class initialization?
7. Why do properties affecting @ConditionalOnProperty need to be decided at build time?
8. When should --initialize-at-run-time be used?
9. Why should you avoid static final fields containing API tokens read from the environment?
10. How is the build host's TrustStore handled in Native Image?
11. What do -H:+PrintClassInitialization and Build Report help investigate?
12. Why cannot strings be used to prove a native binary contains no secrets?

**Pass criteria:** able to explain how Native Image executes static initializers and stores state in the image heap; distinguish Spring AOT from GraalVM class initialization; identify secrets or environment-specific data at risk of being snapshotted; move sensitive classes to runtime initialization when needed; load secrets via runtime configuration/secret mounts; inspect class initialization, image heap, and resources; and build a native build workflow that has no exposure to production secrets.

## Official documentation

- GraalVM — Security Considerations in Native Image: https://www.graalvm.org/latest/security-guide/native-image/
- GraalVM — Native Image Basics: https://www.graalvm.org/latest/reference-manual/native-image/basics/
- GraalVM — Specify Class Initialization Explicitly: https://www.graalvm.org/latest/reference-manual/native-image/guides/specify-class-initialization/
- GraalVM — Class Initialization in Native Image: https://www.graalvm.org/latest/reference-manual/native-image/optimizations-and-performance/ClassInitialization/
- GraalVM — Certificate Management in Native Image: https://www.graalvm.org/latest/reference-manual/native-image/dynamic-features/CertificateManagement/
- GraalVM — Native Image Build Report: https://www.graalvm.org/latest/reference-manual/native-image/overview/build-report/
- Spring Boot — Ahead-of-Time Processing With the JVM: https://docs.spring.io/spring-boot/reference/packaging/aot.html
- Spring Boot — Ahead-of-Time Processing: https://docs.spring.io/spring-boot/how-to/aot.html
- Spring Framework — Ahead-of-Time Optimizations: https://docs.spring.io/spring-framework/reference/core/aot.html
