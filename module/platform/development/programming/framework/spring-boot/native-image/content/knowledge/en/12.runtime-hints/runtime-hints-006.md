# ResourceHints for Files, Path Patterns, and Resource Bundles

## 1. Why Does Native Image Need Resource Hints?

Spring Boot applications frequently read resources outside of bytecode: JSON/YAML files, HTML templates, schemas, default configuration files, images, certificates, message bundles, and data shipped with libraries. When running on the JVM, the application can locate them on the classpath or filesystem at runtime. However, **GraalVM Native Image analyzes reachability at build time**; a file selected by a dynamic string or pattern may not be included in the executable if the analyzer does not recognize that access path.

Spring AOT and Runtime Hints provide a way to describe the resources an application needs. Within the hints API, **ResourceHints** lets you declare:

- One or more **classpath resources** that must be present in the native executable.
- **Path patterns** to include a group of resources selected by rule.
- **Resource bundles** containing localized message strings by language/locale.

This lesson belongs to the **Runtime hints** chapter of the **SPRING_BOOT_NATIVE_IMAGE** module. The goal is to identify the right resource type, register hints in the right place, test metadata, and verify that the application reads the resources on the native executable itself.

> Resource hints apply to resources packaged inside the classpath/image. They do not automatically copy external configuration files, volume-mounted files, or runtime data into a container.

## 2. Distinguishing Classpath Resources from Filesystem Files

The two resource types have different lifecycles and require different handling.

| Type | Example | Common access method | How to ensure data is available at runtime |
| --- | --- | --- | --- |
| Application classpath resource | `src/main/resources/rules/pricing.json` | `ClassPathResource`, `ClassLoader.getResourceAsStream` | Package into JAR and register a resource hint if Native Image needs it |
| Dependency classpath resource | `META-INF/library/defaults.json` | Library reads via classloader | Check dependency metadata; add hint if missing |
| Resource bundle | `messages.properties`, `messages_vi.properties` | `ResourceBundle`, `MessageSource` | Register the bundle by base name and test locales |
| External container file | `/etc/myapp/application.yml` | `Files`, `FileSystemResource`, `file:` | Mount/copy file into the runtime filesystem and grant read permissions |
| Platform secret/config | Kubernetes Secret/ConfigMap, secret store | Environment, volume, platform API | Supply at runtime per operational policy |

Example of classpath resources:

```text
src/main/resources/
  rules/
    pricing.json
  templates/
    invoice.html
  i18n/
    messages.properties
    messages_vi.properties
    messages_en.properties
```

After building the JAR, resources under `src/main/resources` are typically packaged at the corresponding paths inside the JAR. Native Image has its own analysis and packaging process; **do not assume that a resource present in the JAR can automatically be read from the native executable**.

### 2.1. Reading a classpath resource

With Spring, you can use `ClassPathResource`:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.ClassPathResource;

public class PricingRuleReader {

    public String readRules() throws IOException {
        var resource = new ClassPathResource("rules/pricing.json");

        try (InputStream input = resource.getInputStream()) {
            return new String(input.readAllBytes(), StandardCharsets.UTF_8);
        }
    }
}
```

Or using a classloader:

```java
try (InputStream input = getClass()
        .getClassLoader()
        .getResourceAsStream("rules/pricing.json")) {

    if (input == null) {
        throw new IllegalStateException("Missing classpath resource");
    }

    // Read resource contents.
}
```

Resource names passed to a classloader are typically relative paths from the classpath root, using `/`, without a `classpath:` prefix and without a leading `/`. With `ClassPathResource`, paths are also written relative to the classpath. Preserve exact letter casing: Linux environments distinguish `Pricing.json` from `pricing.json`.

### 2.2. Reading an external file

If an application reads a file from a volume or an operationally provided path, for example:

```java
import java.nio.file.Files;
import java.nio.file.Path;

Path configPath = Path.of("/etc/myapp/pricing.json");
String json = Files.readString(configPath);
```

then this resource is **not a classpath resource**. Declaring `registerPattern("etc/myapp/pricing.json")` does not mount or copy the file into the container. You must bake the file into the image or mount a volume/ConfigMap/secret at that path, then ensure the container user has read permission. Do not embed passwords, tokens, or private keys into native executable resources merely to avoid runtime configuration.

## 3. ResourceHints and registerPattern

Spring provides the `RuntimeHints.resources()` API for registering resources. Commonly used methods are:

- `registerPattern(String)`: registers a classpath resource path or pattern.
- `registerResourceBundle(String)`: registers a resource bundle by base name.

Example with two known files:

```java
hints.resources().registerPattern("rules/pricing.json");
hints.resources().registerPattern("templates/invoice.html");
```

For a group of templates sharing a naming convention, you can use a pattern matching the syntax supported by your project's Spring Framework/GraalVM version:

```java
hints.resources().registerPattern("templates/*.html");
```

Patterns are processed when converting Runtime Hints into metadata for Native Image. In Spring Framework 6, the special `*` character matches resources by path and can cover subdirectories across multiple levels; for example, `templates/*.html` covers HTML files in `templates/` and its subdirectories. This is Spring `ResourcePatternHint` pattern syntax, not a shell glob. Check the documentation for your exact Spring/GraalVM version and inspect the generated metadata. For critical resources, **prefer registering exact paths**; only widen patterns when the application genuinely reads multiple files in that group.

### 3.1. Resource paths must match the code

Suppose the code reads:

```java
new ClassPathResource("rules/pricing.json");
```

then the hint must describe the resource under the classpath root:

```java
hints.resources().registerPattern("rules/pricing.json");
```

Common mistakes:

- Registering `src/main/resources/rules/pricing.json`: this is a source tree path, not the resource name on the classpath.
- Registering `classpath:rules/pricing.json` in an API expecting a resource pattern: this prefix is not part of the classpath resource name.
- Using `\` instead of `/` in the resource path.
- Starting the pattern with `/` even though the resource is under the classpath root; patterns should normally be relative paths from the root.
- Wrong casing or wrong file extension.
- Registering only one default file when the code also reads files by tenant/locale.
- Using an overly broad pattern that accidentally pulls many unnecessary resources into the executable.

When unsure, inspect the resource name inside the JAR or dependency, then compare it against the string passed to `ClassPathResource`, `ClassLoader`, or the corresponding Spring API.

## 4. Registering ResourceHints with RuntimeHintsRegistrar

In a Spring Boot application, you can contribute resource hints through a `RuntimeHintsRegistrar` and link the registrar to configuration with `@ImportRuntimeHints`.

Complete example:

```java
package com.example.demo;

import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(PricingResourceHints.class)
class NativeResourceConfiguration {
}

final class PricingResourceHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints, ClassLoader classLoader) {

        hints.resources().registerPattern("rules/pricing.json");
        hints.resources().registerPattern("templates/invoice.html");
    }
}
```

Explanation:

1. `PricingResourceHints` implements `RuntimeHintsRegistrar`.
2. Spring calls `registerHints` during AOT preparation.
3. `hints.resources()` accesses the resource hints group.
4. `registerPattern` describes the resources the application needs at runtime.
5. `@ImportRuntimeHints` links the registrar to a discovered Spring configuration class.

`NativeResourceConfiguration` must be discovered by Spring via component scanning or imported from another configuration. If the configuration/registrar class sits outside the scanned packages and is not imported, hints may not be registered even though the code compiles cleanly.

Do not invoke a registrar manually at runtime expecting it to modify the native executable. Runtime Hints are **build-time inputs** for metadata generation and native analysis.

### 4.1. Organizing hints by module/feature

In large applications, grouping hints by feature makes it clear which component owns which resources:

```java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints({
    PricingResourceHints.class,
    InvoiceTemplateHints.class
})
class NativeResourceConfiguration {
}
```

A registrar for invoice templates:

```java
final class InvoiceTemplateHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints, ClassLoader classLoader) {

        hints.resources().registerPattern("templates/invoice.html");
        hints.resources().registerPattern("templates/invoice-footer.html");
    }
}
```

Each registrar should declare only the resources that feature actually uses. If a third-party library already provides compatible Spring Runtime Hints or GraalVM reachability metadata, avoid duplicate registrations and maintaining a list that can go stale after dependency upgrades.

## 5. Using ResourceHints for Pattern-Matched File Groups

Some applications select resources from runtime configuration, such as a template name by invoice type:

```java
String templateName = "templates/" + invoiceType + ".html";
var resource = new ClassPathResource(templateName);
```

If `invoiceType` can be `standard`, `vat`, or `credit-note`, the corresponding resources must be present in the image. There are two options:

**Option 1: register each known file**

```java
hints.resources().registerPattern("templates/standard.html");
hints.resources().registerPattern("templates/vat.html");
hints.resources().registerPattern("templates/credit-note.html");
```

This is explicit and limits resource scope.

**Option 2: register a pattern for the template group**

```java
hints.resources().registerPattern("templates/*.html");
```

This is convenient when the set of files changes frequently and every file in the group is a valid application resource. In Spring Framework 6, `*` can match resources in subdirectories across multiple levels; still verify against your framework version and output metadata to ensure the scope matches your project.

### 5.1. What is the cost of broad patterns?

An overly broad pattern can include unnecessary files in the image, increasing artifact size, expanding data distributed to the runtime environment, and making metadata auditing harder. For example, registering all resources on the classpath can pull in schemas, templates, documentation, or data from dependencies that the application never uses.

Selection guidelines:

| Case | Registration approach |
| --- | --- |
| Single default configuration file | Exact path |
| A few fixed templates | Register each resource individually |
| Template group with a stable convention | Pattern scoped to directory/file extension |
| Files chosen from a controlled configuration list | Register all valid files or a narrow pattern |
| Files uploaded by users after deployment | Store on filesystem/object storage, do not use classpath hints |
| Secret files or environment-specific files | Supply via secret/config/volume at runtime |

Do not use ResourceHints as a way to bake user data or environment-specific data into the binary.

## 6. Resource Bundles and Multi-Language Support

A resource bundle is a group of resources containing localized messages. Java `ResourceBundle` typically looks up files by base name and locale. For example:

```text
src/main/resources/
  i18n/
    messages.properties
    messages_vi.properties
    messages_vi_VN.properties
    messages_en.properties
    messages_ja.properties
```

The base name in this example is `i18n.messages` when calling `ResourceBundle.getBundle("i18n.messages", locale)`. **The base name does not include the locale suffix or the `.properties` extension.**

Register the bundle with:

```java
hints.resources().registerResourceBundle("i18n.messages");
```

Usage example:

```java
import java.util.Locale;
import java.util.ResourceBundle;

public class MessageProvider {

    public String title(Locale locale) {
        ResourceBundle bundle =
            ResourceBundle.getBundle("i18n.messages", locale);

        return bundle.getString("invoice.title");
    }
}
```

With the `vi-VN` locale, Java can consider corresponding candidates such as `i18n/messages_vi_VN.properties`, `i18n/messages_vi.properties`, and then the default bundle `i18n/messages.properties` according to `ResourceBundle` lookup and fallback rules. Provide the required files for all locales your product commits to supporting.

### 6.1. Base name and filename are two different representations

| Element | Example | Rule |
| --- | --- | --- |
| Java base name | `i18n.messages` | Uses dots to separate package/path segments |
| Resource path | `i18n/messages.properties` | Uses `/`, includes file extension |
| Locale suffix | `_vi`, `_vi_VN` | Suffix appended per locale |
| Resource bundle hint | `registerResourceBundle("i18n.messages")` | Register the base name, without `.properties` |

A common mistake is calling `registerResourceBundle("i18n/messages.properties")`. That is a resource path, not a bundle base name. If you are registering a single properties file read via `ClassPathResource`, use `registerPattern` with the path; if read via `ResourceBundle`, use `registerResourceBundle` with the base name.

### 6.2. Spring MessageSource

Spring applications can use `MessageSource` instead of calling `ResourceBundle` directly. For instance, Spring Boot can configure the basename via properties:

```properties
spring.messages.basename=i18n/messages
spring.messages.encoding=UTF-8
```

If the `MessageSource` mechanism uses Java resource bundles, register the corresponding base name when metadata is not automatically provided by the framework/dependency. If the configuration uses an implementation reading properties files via Spring's Resource abstraction, verify whether it reads **classpath resources** or external files and register the appropriate resource paths. Do not assume every `MessageSource` loads resources in the exact same way.

Test at least the default locale, the Vietnamese locale, and one secondary locale if supported by the product. Also test fallback behavior when a key translation is missing, as failures can surface only on less-used locales.

## 7. Resources in Dependencies and META-INF Directories

Resources can live inside a library JAR, not only in the application's `src/main/resources`. For example, a library might ship default files in `META-INF/vendor/`, templates, or schemas. When troubleshooting errors, verify:

- Whether the resource actually exists inside the dependency JAR.
- Whether the library already supplies Spring Runtime Hints or GraalVM reachability metadata.
- Whether the metadata version is compatible with your GraalVM/Spring Boot version.
- Which classloader reads the resource and what the exact path name is.

Special resources may reside in `META-INF`, such as service provider descriptors in `META-INF/services`. `ServiceLoader` mechanisms and GraalVM/Spring support metadata may handle certain cases specially; do not register all of `META-INF/*` out of habit. Verify the dependency and actual access path before adding patterns.

If your organization owns the library, contribute the metadata inside the library itself so every consuming application receives compatible configuration. If it is only an application-specific resource, registering it in an application registrar is appropriate.

## 8. Testing Runtime Hints Before Building Native

You can test hint registration using `RuntimeHintsPredicates`. For example:

```java
import org.junit.jupiter.api.Test;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

import static org.junit.jupiter.api.Assertions.assertTrue;

class PricingResourceHintsTests {

    @Test
    void registersPricingResource() {
        RuntimeHints hints = new RuntimeHints();

        new PricingResourceHints().registerHints(
            hints, getClass().getClassLoader()
        );

        assertTrue(
            RuntimeHintsPredicates.resource()
                .forResource("rules/pricing.json")
                .test(hints)
        );
    }
}
```

For resource bundles, check the registered base name:

```java
assertTrue(
    RuntimeHintsPredicates.resource()
        .forBundle("i18n.messages")
        .test(hints)
);
```

These tests confirm that the registrar contributed hints to `RuntimeHints`. They **do not prove** that the file exists in the source tree, that a pattern matches the intended resources, or that the native binary can actually read the file. You must test both resources in the JAR/classpath and the native executable.

### 8.1. Checking that resources exist in the JAR

With Maven, after building the JAR:

```bash
jar tf target/hello-native-0.0.1-SNAPSHOT.jar
```

Look for paths like `BOOT-INF/classes/rules/pricing.json` or resources inside dependencies. With Gradle, you can run `jar tf build/libs/<artifact>.jar`. Paths in a Spring Boot executable JAR can reside under `BOOT-INF/classes` or inside nested dependency JARs; verify the exact location and classloader behavior.

### 8.2. Testing on the native executable

After running the native build:

1. Start the executable in a compatible environment.
2. Call the endpoint or job that actually reads the classpath resource.
3. Verify contents, encoding, parsed data, and business results.
4. Exercise every branch that selects resources by dynamic name.
5. Test all locales supported by the application and verify fallback behavior.
6. Log/throw errors when a resource is missing; avoid silently returning empty results that mask failures.

With only `RuntimeHintsPredicates` tests and without running the binary, you cannot conclude that native compatibility has been achieved.

## 9. Complete Example: Reading Templates and Localized Messages

Suppose an application has this structure:

```text
src/main/resources/
  templates/
    invoice.html
    invoice-footer.html
  i18n/
    messages.properties
    messages_vi.properties
    messages_en.properties
```

Register hints:

```java
final class InvoiceResourceHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints, ClassLoader classLoader) {

        hints.resources().registerPattern("templates/invoice.html");
        hints.resources().registerPattern("templates/invoice-footer.html");
        hints.resources().registerResourceBundle("i18n.messages");
    }
}
```

Wire the registrar:

```java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(InvoiceResourceHints.class)
class InvoiceConfiguration {
}
```

Read the template via Spring's Resource abstraction:

```java
var template = new ClassPathResource("templates/invoice.html");

try (var input = template.getInputStream()) {
    String html = new String(
        input.readAllBytes(), StandardCharsets.UTF_8
    );
}
```

Read localized messages:

```java
ResourceBundle bundle =
    ResourceBundle.getBundle("i18n.messages", Locale.forLanguageTag("vi-VN"));

String title = bundle.getString("invoice.title");
```

When building natively, confirm that Spring discovers the registrar, the hints appear in AOT/metadata outputs, and both resource-reading paths work. If templates are loaded by user-supplied names, never pass arbitrary user strings directly into `ClassPathResource`; validate against an allowlist of templates and register only the known set of resources.

## 10. Common Errors and Troubleshooting

| Symptom | Cause to check | How to resolve |
| --- | --- | --- |
| `getResourceAsStream` returns `null` in native | Resource missing from image, wrong path, or casing mismatch | Check path in JAR and register the exact resource hint |
| `ClassPathResource` fails to open file | Confusing classpath with filesystem or path has invalid prefix | Identify resource type, use the right API and classpath-relative name |
| Resource fails only for one tenant/template type | Code builds dynamic path, but only one file was registered | Register all valid files or a narrow pattern |
| `MissingResourceException` | Wrong bundle base name or missing locale file | Register exact base name, add locale files, and test fallback |
| Default bundle works, yet Vietnamese fails | Missing `messages_vi.properties` or wrong bundle name | Check resource path and `registerResourceBundle` |
| File exists in `src/main/resources`, yet native cannot read it | Not packaged or metadata missed dynamic access | Check JAR, `RuntimeHints`, and native executable |
| Pattern misses nested subdirectory files | Pattern syntax does not match actual structure | Check pattern semantics for your Spring/GraalVM version; register exact paths to verify |
| Dependency resource missing | Dependency lacks native metadata or metadata is incompatible | Upgrade/contribute metadata or register hints in the application |
| External config file not found | Assuming resource hints copy files into the container | Mount/copy file into runtime filesystem and grant read permission |
| Native build succeeds, yet fails on request | Resource-reading branch or rare locale not tested | Add integration tests running against the native binary |

Do not resolve issues by registering every resource on the classpath without knowing the root cause. Overly broad patterns inflate packaged data and can pull unnecessary files into the image.

## 11. Hands-on Exercise: Registering Resources and a Resource Bundle

**Context:** A Spring Boot API generates invoice content. It reads `templates/invoice.html` and retrieves titles from the `i18n.messages` resource bundle.

**Steps:**

1. Create `templates/invoice.html`, `i18n/messages.properties`, and `i18n/messages_vi.properties` under `src/main/resources`.
2. Write a service that reads the template with `ClassPathResource` and reads the title with `ResourceBundle`.
3. Create a `RuntimeHintsRegistrar` registering `templates/invoice.html` and base name `i18n.messages`.
4. Use `@ImportRuntimeHints` so Spring AOT discovers the registrar.
5. Write unit tests with `RuntimeHintsPredicates` for both the resource and the bundle.
6. Build the JAR, verify resources are inside the artifact, and run the endpoint on the JVM.
7. Build the GraalVM Native Image and call the same endpoint on the native executable.
8. Test the `vi-VN` locale, default locale, and another locale if supported; verify fallback behavior.
9. Temporarily change a resource name with wrong casing to observe how the failure appears, then restore the correct path.
10. Record the native build results, resource tests, responses, and any exceptions.

**Passing criteria:**

- Resource hint registers the exact classpath path.
- Resource bundle hint uses the base name, not the `.properties` filename.
- Registrar is imported and executed during AOT processing.
- Unit tests verify hints are present in `RuntimeHints`.
- Native executable reads the template and messages accurately.
- Locales/fallbacks match the product's supported scope.
- External container files are handled via volumes/configuration, never confused with classpath hints.

## 12. Summary

`ResourceHints` helps Spring AOT inform GraalVM Native Image about resources to retain when an application reads resources dynamically. Use `registerPattern` for classpath files or path groups; use `registerResourceBundle` for Java resource bundles by base name. Place declarations in a `RuntimeHintsRegistrar`, wire them via `@ImportRuntimeHints`, and verify with `RuntimeHintsPredicates` as well as on the native executable.

Always distinguish **classpath resources** from **external filesystem files**. Hints do not mount volumes, grant file permissions, or supply secrets. A reliable resource configuration requires exact paths, narrowly scoped patterns, tested locales, and proof that the native binary actually reads the resources in the deployment environment.
