# Classpath Resources Differ from Files External to the Binary

## 1. Why Is It Necessary to Distinguish Between the Two Resource Types?

Spring Boot applications often read many kinds of data: configuration files, email templates, JSON schemas, certificates, images, message bundles, and operator-provided files. Some resources reside on the application's classpath; others are mounted or placed on the filesystem at deployment time.

When running on the JVM, the classpath typically includes the classes directory and dependency JARs. The application can use a classloader to locate resources in these locations. When moving to **GraalVM Native Image**, the executable is created at build time. Native Image does not automatically carry the entire filesystem or every file on the build machine into the binary. **Required classpath resources** must be identified and included in the image; **files external to the binary** continue to be provided from the filesystem/runtime environment.

In the **SPRING_BOOT_NATIVE_IMAGE** module, distinguishing between these two groups helps avoid "works on JVM, not found in native" errors, while keeping configuration, secrets, and operational data changeable without having to rebuild the executable.

- **Classpath resource:** a resource belonging to the application or a dependency, accessed via the classloader/resource API and typically packaged with the artifact.
- **External file:** a file read via a filesystem path at runtime, such as `/etc/orders/application.yml`, `/var/lib/orders/rules.json`, or a file mounted into a container.

Paths that look similar do not determine the resource type. How the application accesses the resource and where the resource is provided are the deciding factors.

## 2. Classpath Resources on the JVM

A resource may reside in:

```text
src/main/resources/
├── application.properties
├── templates/
│   └── invoice.html
├── schemas/
│   └── invoice-v1.json
└── messages/
    └── messages.properties
```

Maven/Gradle typically copies the contents of `src/main/resources` into the classes output and executable JAR. Java can read it using a classloader:

```java
try (InputStream input =
        getClass().getResourceAsStream("/schemas/invoice-v1.json")) {
    if (input == null) {
        throw new IllegalStateException("Schema resource not found");
    }
    // Read input contents
}
```

Or use the Spring Resource abstraction:

```java
Resource resource =
        new ClassPathResource("schemas/invoice-v1.json");

try (InputStream input = resource.getInputStream()) {
    // Read resource
}
```

For classpath resources, the application should not assume there is always a physical file to retrieve with `new File(...)`. A resource inside a JAR or native image may not correspond to a regular filesystem path. Using `InputStream` or the Spring `Resource` API is usually safer.

## 3. External Files Read from the Filesystem at Runtime

A file external to the binary is typically specified via a configured path:

```java
Path rulesPath = Path.of(
        System.getProperty("orders.rules.path",
                "/etc/orders/rules.json"));

if (!Files.isRegularFile(rulesPath)) {
    throw new IllegalStateException(
            "Rules file does not exist: " + rulesPath);
}

try (InputStream input = Files.newInputStream(rulesPath)) {
    // Read rules from the filesystem
}
```

In a container, the file can be mounted from the host, a Kubernetes ConfigMap/Secret, or a volume:

```bash
docker run --rm \
  -v ./config/rules.json:/etc/orders/rules.json:ro \
  -e ORDERS_RULES_PATH=/etc/orders/rules.json \
  orders-service:1.0
```

The example needs to align the property name with how the application reads it; if using Spring Boot binding, `orders.rules.path` can be injected via `@ConfigurationProperties`. An external file does not need to be embedded into the Native Image, as long as it exists and the process has read permission at runtime.

This is the appropriate choice for environment-specific data, deployment configuration files, or operational data that should not be permanently packaged into the executable.

## 4. Comparison Table Between Classpath Resources and External Files

| Criterion | Classpath resource | External file |
|---|---|---|
| Source location | `src/main/resources`, dependency JARs, or library resources | Filesystem, volume, mount, or runtime path |
| Access method | ClassLoader, `Class.getResourceAsStream`, Spring `Resource` | `Path`, `Files`, `FileInputStream`, Spring `FileSystemResource` |
| Included in native binary? | Can be included in the image when configured/detected | Not automatic; typically exists outside the executable |
| Changing content | Usually requires rebuilding the artifact/image | Can be changed at deployment time if the application supports it |
| Needs resource hints? | May be needed when Native Image cannot infer the path | No classpath resource hint needed just for an external file |
| Secret management | Not suitable for embedding secrets in the artifact | Can be mounted from a secret store with appropriate permissions |
| Environment dependency | Low dependency on filesystem paths | Depends on path, mount, permissions, and filesystem capacity |

Do not confuse an external file with a classpath resource just because the file is mounted into a directory with the same name as a package. A file at `/app/config/app.yml` read using filesystem APIs is an external file, even if it sits right next to the executable.

## 5. How Does Native Image Handle Classpath Resources?

Native Image performs static analysis and creates an image containing the detected or declared resources. If code accesses a resource using a constant path, the tool can automatically detect it in some cases. However, when a resource name is constructed from a property, dynamically generated, or located in a dependency loaded via non-static logic, the tool may not know which files to package.

For example:

```java
String schemaName = configuration.getProperty("schema.name");
String path = "schemas/" + schemaName + ".json";

try (InputStream input =
        getClass().getClassLoader().getResourceAsStream(path)) {
    // ...
}
```

Reachability analysis sees the classloader call but cannot always know the value of `schemaName` across all deployments. The corresponding resource may be omitted from the image. When that happens, the JVM build finds the file in the JAR, while the native executable receives `null`.

The solution is to declare resource patterns via Spring `RuntimeHints` or GraalVM reachability metadata. The pattern must match actual resources on the classpath at build time.

## 6. Registering Classpath Resources with RuntimeHints

Spring provides `RuntimeHints.resources()` to declare resources that need to be packaged:

```java
final class InvoiceResourceHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.resources().registerPattern(
                "schemas/invoice-*.json");
    }
}
```

Attach the registrar to a configuration class:

```java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(InvoiceResourceHints.class)
class InvoiceConfiguration {
}
```

The pattern `schemas/invoice-*.json` instructs that files matching the pattern be included in the resource metadata. If there is only a single file, you can register the specific name:

```java
hints.resources().registerPattern(
        "schemas/invoice-v1.json");
```

Resource paths in hints are typically declared relative to the classpath root, without a leading `/`. Check the API and pattern syntax according to the Spring Framework version the project is using.

`RuntimeHints` only helps Native Image recognize resources present in the build inputs. It cannot package external files that only exist on the production machine and are not on the classpath at build time.

## 7. Reading Classpath Resources with the Spring Resource API

Spring provides the `Resource` abstraction so code does not depend too tightly on the data source:

```java
@Component
class InvoiceSchemaLoader {

    private final ResourceLoader resourceLoader;

    InvoiceSchemaLoader(ResourceLoader resourceLoader) {
        this.resourceLoader = resourceLoader;
    }

    InputStream openSchema(String version) throws IOException {
        Resource resource = resourceLoader.getResource(
                "classpath:schemas/invoice-" + version + ".json");

        if (!resource.exists()) {
            throw new FileNotFoundException(
                    "Schema not found: " + version);
        }
        return resource.getInputStream();
    }
}
```

The example uses a dynamic resource name, so selectable files must be declared via hints. Import `ResourceLoader`, `Resource`, `InputStream`, and the appropriate exceptions.

If the path is always fixed, the code can use `ClassPathResource` directly. If the version selection comes from a runtime property, ensure the entire set of valid resources is packaged into the native image.

Do not use `resource.getFile()` by default. A resource inside a JAR or native image does not necessarily exist as a regular file; `getInputStream()` is more compatible across multiple sources.

## 8. Reading External Files with the Spring Resource API

Spring `ResourceLoader` supports prefixes such as `file:` to explicitly specify a filesystem source:

```java
Resource resource = resourceLoader.getResource(
        "file:/etc/orders/rules.json");

try (InputStream input = resource.getInputStream()) {
    // Read file external to the binary
}
```

For configurable paths, inject the path using `@ConfigurationProperties`:

```java
@ConfigurationProperties(prefix = "orders.rules")
public record RulesProperties(Path path) {
}
```

Example runtime configuration:

```yaml
orders:
  rules:
    path: /etc/orders/rules.json
```

This path can be supplied via an environment variable or a mounted config file. Spring Boot binding supports converting a string into a `Path` in standard configurations. Verify the property source, defaults, and validation to avoid errors when the file does not exist.

Do not declare a classpath resource hint for `/etc/orders/rules.json` if the file is actually mounted at runtime. Instead, check the filesystem, access permissions, and handle the missing-file case explicitly.

## 9. application.properties and Config Data

Spring Boot has its own rules for loading application configuration. Distinguish between:

- `application.properties` or `application.yml` on the classpath: typically packaged with the application.
- `application-prod.yml` on the classpath: a profile-specific resource belonging to the artifact if packaged.
- `/etc/orders/application.yml`: an external file supplied by the runtime environment.
- Environment variables/command-line arguments: runtime configuration sources, not classpath resources.

An external configuration can be specified via the config data mechanism, for example:

```bash
SPRING_CONFIG_ADDITIONAL_LOCATION=file:/etc/orders/
./application
```

This is a way to instruct Spring Boot to load an additional config location; exact behavior and property source precedence depend on the Spring Boot version and launch configuration. Ensure the file exists in the container and the process has read permission.

Native Image can still read external config data at runtime if the filesystem contains that file. There is no need to embed this file into the image just for Spring Boot to load it.

## 10. Secrets and Environment-Specific Data

Secrets should not be packaged into classpath resources or the native binary. If `application.properties` contains database passwords, tokens, or private keys, those values can be extracted from the artifact or image.

Appropriate practices:

- Keep non-sensitive default configuration on the classpath.
- Supply secrets via a secret manager, mounted secret files, or securely managed environment variables.
- Grant read permission on secret files only to the user running the process.
- Do not print secrets to logs or pass them into build arguments.
- Do not create resource hints for external secret files as if they were build-time resources.

Example of reading a secret from a mounted file:

```java
Path secretFile = Path.of("/run/secrets/payment-api-key");
String apiKey = Files.readString(secretFile).trim();
```

This snippet illustrates reading a file at runtime; in a real application, use an appropriate secret/config binding mechanism and do not log the value. When a secret is rotated, the application needs a reload or restart strategy depending on what it supports.

## 11. Resources in Dependency JARs

Classpath resources do not come only from the application's `src/main/resources`. Libraries may provide:

- Templates or message bundles.
- Schemas, rule files, and mapping metadata.
- Service provider configurations.
- Default configuration files or data bundled with the library.

For example, a library provides `META-INF/services/com.example.Plugin` for Java `ServiceLoader` to discover providers. If the application uses service discovery, check both the resource metadata and the corresponding provider registration mechanism. Resource hints only package the file; they do not automatically guarantee that provider classes and constructors are retained by reachability analysis.

For dependencies that already support Native Image, the library may provide pre-existing reachability metadata. Prefer the dependency's official metadata and avoid arbitrary duplicate registrations. If a library does not declare dynamic resources, the application can add a `RuntimeHintsRegistrar` for specific patterns.

## 12. Resource Patterns and Registration Scope

A pattern that is too broad can cause the native image to retain many unnecessary resources; a pattern that is too narrow causes some valid files to be missing. Identify the exact set of files the application actually reads.

| Example pattern | Intent |
|---|---|
| `schemas/invoice-v1.json` | A specific file |
| `schemas/invoice-*.json` | Versioned invoice schemas |
| `templates/mail/*.html` | HTML templates in the mail directory |
| `i18n/messages*.properties` | Locale-based message bundles |

Check supported pattern syntax and matching behavior against your Spring/GraalVM API version. Do not assume wildcards in `RuntimeHints` behave identically to shell glob syntax or regex.

For resources inside subdirectories, verify the exact classpath path, case sensitivity on Linux, and ensure Maven/Gradle copied the resources into the output. You can inspect JAR contents with:

```bash
jar tf target/orders-service.jar
```

With a Spring Boot executable JAR, application resources typically reside under `BOOT-INF/classes/`, while dependency resources reside in JARs under `BOOT-INF/lib/`. Specific locations depend on the packaging method.

## 13. Diagnosing Resource Errors in Native

| Symptom | Possible cause | Resolution |
|---|---|---|
| `getResourceAsStream` returns null | Resource not packaged or wrong path | Check JAR/build output and resource hints |
| Works on JVM, fails in native | Resource name generated dynamically or missing metadata | Register the pattern and rebuild |
| External file does not exist | Volume not mounted or wrong path | Check container mounts and runtime config |
| Permission denied | User/container lacks read permission | Adjust ownership/mode or mount permissions |
| Resource in JAR but missing in native | Metadata/resource pattern not picked up by Native Image | Check AOT hints and native build log |
| Reading file with `getFile()` fails | Resource is not a filesystem file | Use `getInputStream()` |
| Fails only on Linux | Case-sensitivity or path separator differences | Normalize resource paths and check casing |
| Secret does not update | Secret embedded at build time or app does not reload | Switch to an external runtime source and define a reload strategy |

When investigating, first determine whether the resource is classpath or external. Do not add resource hints to fix a mis-mounted external file; likewise, do not mount a file into a container to replace packaging a classpath resource that belongs inside the executable.

## 14. Testing Classpath and External Files

A test suite should verify both mechanisms separately.

Classpath resource test:

```java
@Test
void invoiceSchemaIsAvailable() throws IOException {
    Resource resource =
            new ClassPathResource("schemas/invoice-v1.json");

    assertThat(resource.exists()).isTrue();

    try (InputStream input = resource.getInputStream()) {
        assertThat(input.read()).isNotEqualTo(-1);
    }
}
```

External file tests should create temporary files or mount fixtures in the integration environment, pass the path via runtime configuration, and verify the application reads them. Do not use hardcoded developer machine paths in CI tests.

With Native Image:

1. Run `RuntimeHints` tests to confirm the registrar registers the pattern.
2. Build the native executable.
3. Run the endpoint/service that actually reads the classpath resource.
4. Run the same executable with the external file mounted at the test path.
5. Test missing files, wrong permissions, and non-existent resource paths to verify error messages.
6. Run in the actual runtime container, because the build host may have resources or files that the container does not.

JVM unit tests are not sufficient proof that classpath resources were included in the Native Image. Native integration tests or running the actual binary are required.

## 15. Hands-On Exercise: One Classpath Schema and One External Rules File

**Context:** a Spring Boot service processing invoices. A fixed JSON schema is packaged in the application; a business rules set varies per deployment.

**Step 1 — Create the classpath resource.** Place `schemas/invoice-v1.json` in `src/main/resources` and read it via `ClassPathResource`.

**Step 2 — Register RuntimeHints.** Create a registrar declaring `schemas/invoice-v1.json` or the actual pattern, and attach it via `@ImportRuntimeHints`.

**Step 3 — Create the external rules file.** Read `/etc/orders/rules.json` using `Path` or `FileSystemResource`, receiving the path from runtime configuration.

**Step 4 — Test on the JVM.** Verify both the schema and rules are read properly, including the case where the external file is missing.

**Step 5 — Build native.** Run Spring AOT and GraalVM Native Image; verify the classpath schema can still be read.

**Step 6 — Run in a container.** Mount the rules file at the right path, run the executable as the production user, and verify both resource sources.

**Step 7 — Replace the rules file.** Update the external file and restart/reload the process according to what the application supports; the classpath schema does not change without rebuilding.

Completion criteria: the classpath resource is present in the native image, the external file is supplied from the runtime filesystem, secrets are not packaged, and the application handles missing-resource cases clearly.

## 16. Conclusion

Classpath resources and external files have different lifecycles. **Classpath resources** belong to the application/dependencies and must be identified and packaged by Native Image through analysis or `RuntimeHints` when needed. **External files** are supplied from the filesystem at runtime, depending on mounts, paths, and permissions; they are not automatically placed inside the binary.

With Spring Boot Native Image, use the `Resource`/`ClassLoader` API for the classpath, `Files`/`Path` or Spring `file:` `Resource` for external files, register accurate resource patterns, and keep secrets/environment-specific data outside the executable. Test both types on the native executable in the target container to avoid discrepancies between the JVM, the build machine, and production.
