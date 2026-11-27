# Checking for Missing Resources and Avoiding Packaging Secret Data

## 1. Two Risks to Address Before Releasing a Native Image

In the **SPRING_BOOT_NATIVE_IMAGE** module, Spring AOT prepares code and metadata at build time, and then GraalVM Native Image analyzes inputs to produce an executable. When packaging an application, two mistakes are easy to overlook:

1. **Missing resources when running native:** templates, schemas, message bundles, or configurations present in the JAR/JVM are not included in the native executable, causing a business flow to fail upon access.
2. **Packaging secret data:** passwords, API tokens, private keys, credentials, or environment files end up inside the JAR, generated resources, native executable, or container image.

Both issues involve the classpath and resource metadata, yet their solutions differ. Required application resources must be declared so Native Image retains them; secret data must be supplied from the runtime environment and protected by secret management mechanisms.

**Principle:** verify which resources belong in the artifact, register resource hints only for the necessary scope, and keep credentials outside every built artifact.

## 2. Distinguishing Classpath Resources from External Files

Not every file an application reads is handled the same way.

| Data type | Common location | Access method | Packaged into native image? |
| --- | --- | --- | --- |
| Classpath resource | `src/main/resources/`, resources in dependency JARs | `ClassPathResource`, `ClassLoader.getResource`, `getResourceAsStream` | Can be packaged; requires resource metadata if not detected by static analysis |
| Resource bundle | `messages.properties`, translation files | `ResourceBundle`, message source | Must ensure the bundle is retained; can register a resource bundle hint |
| External configuration | File in a mounted directory or config path | Config Data, `FileSystemResource`, `Path` | Does not automatically become part of the binary; must exist at runtime |
| Secret file | Secret manager mount, config tree, read-only volume | Environment or file path supplied at runtime | Should be kept outside JAR/native image/container layers |
| Build output | `target/classes`, `build/resources/main`, generated resources | Task/build classpath | May be packaged if part of artifact inputs |

Example of a safe resource layout:

~~~text
src/main/resources/
  application.yml
  templates/
    invoice.html
  i18n/
    messages.properties
~~~

Template files and message bundles are packageable application data. Files like `application-prod.yml` containing real passwords, `service-account.json`, or `private-key.pem` should not reside in this resource directory.

### 2.1. Classpath Resources Differ from External Files

Classpath resources are looked up in the JAR/dependencies or on the application's classpath. Example:

~~~java
ClassPathResource template =
    new ClassPathResource("templates/invoice.html");
try (InputStream input = template.getInputStream()) {
    // Read template.
}
~~~

Conversely, an external file can be placed at a mount path:

~~~java
Path secretFile = Path.of("/run/secrets/storage-password");
String password = Files.readString(secretFile).trim();
~~~

A Native Image resource hint does not create files under `/run/secrets/` and does not grant filesystem read permissions. External files must be supplied in the runtime environment with the right path and access permissions.

## 3. Why Are Resources Present on the JVM Yet Missing in the Native Executable?

On the JVM, the classloader can look up resources in JARs when the application requests them. With GraalVM Native Image, the compiler uses reachability analysis and metadata to decide which resources to include in the executable.

A direct access path with a constant name may be detected automatically in some cases. However, if a resource name is constructed from properties, tenant names, locales, or runtime data, the analysis may not know which files will be requested:

~~~java
String templateName = environment.getProperty("app.invoice.template");
String path = "templates/" + templateName + ".html";

try (InputStream input =
         getClass().getClassLoader().getResourceAsStream(path)) {
    if (input == null) {
        throw new IllegalStateException("Template not found: " + path);
    }
    // Render invoice.
}
~~~

The JVM can read the corresponding file if it is on the classpath. Native Image needs to know the valid resource set in advance. Otherwise, `getResourceAsStream` may return `null` in the executable even though the file existed in the JAR.

Common causes:

- Resource name is generated dynamically and thus not recognized by reachability analysis.
- File exists only in `src/test/resources`, not in application resources.
- Resource lives in an optional dependency not present on the build classpath.
- Path differs in letter casing; Linux environments are case-sensitive.
- Resource filtering or copy tasks excluded/renamed the file.
- Native Image did not receive the appropriate resource hints.

**A hint cannot recover a file that is missing from the build inputs.** First confirm the resource exists in the Maven/Gradle output or JAR; only then configure metadata so Native Image packages it.

## 4. Registering Resource Hints with Spring AOT

Spring provides `RuntimeHintsRegistrar` to declare resources needed by the native executable.

Suppose the application reads all HTML templates in `templates/`. You can register a pattern:

~~~java
package com.example.invoice;

import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(InvoiceResourceHints.class)
class InvoiceResourceConfiguration {
}

class InvoiceResourceHints implements RuntimeHintsRegistrar {
    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.resources().registerPattern("templates/*.html");
    }
}
~~~

`@ImportRuntimeHints` enables Spring AOT to load the registrar. Patterns are written relative to the classpath root without a leading `/`. Only use `templates/*.html` if the application actually needs that group of files.

If reading only a single file, register that exact file:

~~~java
hints.resources().registerPattern("templates/invoice.html");
~~~

For message bundles, register the base name:

~~~java
hints.resources().registerResourceBundle("i18n.messages");
~~~

The bundle name must match the resource's package/path, for example `src/main/resources/i18n/messages.properties`.

### 4.1. Do Not Use Overly Broad Patterns

Avoid registering all resources if only a small group is needed:

~~~java
// Do not use as a default solution:
hints.resources().registerPattern("**/*");
~~~

Broad patterns can:

- pull unnecessary data into the executable;
- increase binary size and native compilation time;
- accidentally retain internal config files or data that should not be released;
- make it harder to audit the artifact and understand why a resource was packaged.

List resources by feature. For templates, schemas, and bundles, use narrow paths or patterns. If a resource belongs to a dependency, check whether the library already provides reachability metadata before adding duplicate hints.

### 4.2. Resources Generated During the Build

If a Maven/Gradle task generates files into a generated-resources directory, ensure that task runs before the packaging step and its output is added to the appropriate resource/classpath inputs. `RuntimeHintsRegistrar` only describes resources to keep; it does not replace file-generation or resource-copy tasks.

Verification workflow:

1. Confirm the file is in the resource output directory.
2. Confirm the file is in the JAR if the application builds an intermediate JAR.
3. Confirm the hint is included in AOT/native compilation inputs.
4. Run the native executable and read that exact resource.

## 5. Diagnosing Missing Resources Layer by Layer

When the JVM reads a file yet the native executable cannot, trace from build inputs to runtime.

### Step 1: Confirm the Resource Exists in Source

Expected file example:

~~~text
src/main/resources/templates/invoice.html
~~~

Verify the exact name, extension, letter casing, and path. Do not put files under `src/test/resources` if the production application requires them.

### Step 2: Confirm the Resource Is Processed into Build Output

With Maven:

~~~bash
./mvnw process-resources
~~~

Inspect files under `target/classes/templates/`.

With Gradle:

~~~bash
./gradlew processResources
~~~

Inspect files under `build/resources/main/templates/`.

### Step 3: Confirm the Resource Is Inside the JAR

~~~bash
jar tf target/application.jar | grep 'templates/invoice.html'
~~~

If the command does not find the file, the bug lies in resource processing/packaging or the artifact path being inspected. Do not touch Native Image hints yet.

### Step 4: Check Resource Metadata

Verify that the registrar is imported in the AOT `ApplicationContext`, the pattern matches the exact classpath path, and the resource actually exists in the dependency/application JAR. Avoid assuming an arbitrary JSON metadata file is recognized by GraalVM; if using JSON metadata, follow the exact schema and location supported by your Native Image version.

### Step 5: Re-run the Native Executable

After fixing hints or resource inputs, rebuild the native image. Exercise the exact file-reading flow; checking only a health endpoint is insufficient if that endpoint does not use the template.

### Quick Diagnostic Table

| Observation | Likely cause | Resolution |
| --- | --- | --- |
| File missing in `target/classes`/`build/resources/main` | Incorrect resource processing or source path | Fix Maven/Gradle config; inspect copy/filter tasks |
| Present in build output, missing in JAR | Packaging excluded it or inspecting wrong artifact | Check Spring Boot Maven/Gradle packaging and JAR name |
| Present in JAR, unreadable in native | Missing resource hint or different runtime path | Register narrow pattern; check path/casing |
| Fails only on Linux | Case-sensitivity or file permission differences | Normalize filenames; check permissions and mounts |
| External filesystem resource missing | Volume not mounted or wrong path | Check container config and read permissions |
| Resource contains a secret | Sensitive data leaked into source/build artifact | Remove from resources, rotate secret, and release a new artifact |

## 6. Why Must Secrets Never Be Packaged into Resources?

JARs and native executables are artifacts that can be downloaded, cached, pushed to registries, or distributed across environments. Once a credential enters resources, generated files, code constants, or container layers, anyone with read access to the artifact can attempt to extract it.

Data that must not be placed in `src/main/resources` or generated directories for packaging:

- database, Redis, or message broker passwords;
- API keys, OAuth client secrets, access tokens, refresh tokens;
- private keys, keystore/truststore files containing private keys and passwords;
- cloud service account JSON, access keys/secret keys;
- certificate bundles or configuration files containing private credentials;
- `.env` files with real values, data dumps, or backups containing sensitive information.

Public certificates, public CA bundles, or truststores without private keys can be valid application resources. However, inspect their contents before putting them in an artifact; do not rely solely on filenames.

### 6.1. How Can Secrets Leak into an Artifact?

| Risk source | Example | Prevention |
| --- | --- | --- |
| Source resources | `application-prod.yml` containing real passwords | Keep only placeholders in resources; supply values at runtime |
| Local files copied in | `.env`, `credentials.json`, `*.pem` | Keep outside resource source sets, exclude from packaging, manage via secret store |
| Resource filtering | Maven filtering or Gradle `expand(...)` substituting placeholders with secrets | Do not filter secrets into resources; restrict filtering to non-sensitive files |
| AOT/build-time configuration | Secret values present in environment during AOT or custom code generation | Do not provide secrets in build jobs; do not generate code containing credentials |
| Native compiler arguments | Passing passwords/tokens via `-D`, build arguments, or command line | Avoid secrets in command lines and compiler arguments |
| Container builds | Docker `ARG`, `ENV`, copying secrets into layers or build context | Use builder/CI secret mounts; never store secrets in the image |
| Build logs/caches | Printing the full `Environment`, Maven debug logs, or generated files | Mask secrets, restrict log/cache access, and never dump sensitive configs |

**Excluding a resource from Native Image does not remove a secret already embedded in bytecode.** If a secret entered a Java constant, generated AOT code, build argument, or another layer, merely deleting a resource hint does not eliminate the secret.

## 7. Providing Configuration and Secrets at Runtime

### 7.1. Putting Placeholders in application.yml

You can keep property names and placeholders in resources:

~~~yaml
spring:
  datasource:
    url: ${DB_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
~~~

This file contains no real credentials. When running the native executable, the environment supplies the variables:

~~~bash
DB_URL='jdbc:postgresql://db.internal:5432/billing' \
DB_USERNAME='billing_app' \
DB_PASSWORD='value-from-secret-store' \
./target/billing-service
~~~

In CI/CD, real values must be injected from the platform's secret store and masked from logs. Never commit real `.env` files or pass secrets as Maven/Gradle parameters.

### 7.2. Using Mounted Secret Files

With Spring Boot Config Data, you can load a config tree from a mounted directory:

~~~yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
~~~

Example runtime mount:

~~~text
/run/secrets/
  spring.datasource.username
  spring.datasource.password
~~~

Filenames in the config tree become property keys; file contents become values. Thus `spring.datasource.password` is read from the secret file when the application runs, rather than residing inside the JAR/native executable.

If using custom file paths, the application can read them with `Files.readString(Path.of(...))`; verify file existence, encoding, read permissions, and newline handling. Never log secret contents or include them in exception messages.

### 7.3. Docker and Kubernetes

In containers, use the platform's native secret mechanisms:

- inject environment variables from secret references;
- mount secrets as files with read-only permissions and least-privilege access;
- use workload identity/managed identity when supported by the target service, avoiding long-lived access keys.

Docker example illustrating mounting a secret directory from the host:

~~~bash
docker run --rm \
  --mount type=bind,src=/secure/runtime-secrets,dst=/run/secrets,readonly \
  -p 8080:8080 \
  billing-service:native
~~~

The `src` path is an example; replace it with a secret mount managed by the operational environment. Do not include the secret directory in the Docker build context and do not use `COPY` to package it.

## 8. Protecting Secrets in AOT, Maven/Gradle, and Buildpacks

Spring AOT runs the `ApplicationContext` at build time to prepare the application structure. Therefore, build jobs should use configuration containing no real credentials. If custom bean initialization or code generation reads a secret during AOT, that value could appear in generated output or logs depending on how the application handles it.

### Maven

- Do not pass passwords via `-Ddb.password=...` or write secret properties in `pom.xml`.
- Do not enable resource filtering on files that could receive secrets from Maven properties.
- Do not store secrets in generated resources or the `target/` directory.
- Use secret stores/CI credential bindings for steps that truly need authentication; prefer isolating them from AOT/native compilation.

### Gradle

- Do not place secrets in `build.gradle`, version catalogs, or committed properties files.
- Avoid `processResources { expand(...) }` or `filter(...)` with credential values.
- Do not log `System.getenv()` or all Gradle project properties.
- Keep secrets out of `src/main/resources` and out of generated outputs.

### Buildpacks and Container Builds

- `BP_NATIVE_IMAGE=true` is a buildpack control variable, not a place to pass application passwords.
- Do not pass secrets via `pack --env`, builder environment, or build variables where they could be saved into the image.
- Do not copy credential files into the build context.
- If a build step genuinely needs credentials to fetch private dependencies, use secret mechanisms supported by your CI/builder and ensure values never enter image layers, build metadata, or logs.

### AOT Conditions Are Not a Secret Store

Properties determining the bean graph may be evaluated during AOT. Supply only non-sensitive structural values to the build environment. Passwords, tokens, and private keys must be read at runtime via a secret store or mount path. Do not use `@ConditionalOnProperty` with secret values to decide application structure.

## 9. Inspecting Artifacts to Detect Unintended Resources and Secrets

Pre-release checks should inspect both **filenames** and **file contents**.

### 9.1. Listing the JAR

~~~bash
jar tf target/billing-service.jar
~~~

Search for suspicious names:

~~~bash
jar tf target/billing-service.jar | grep -Ei '(^|/)(\.env|.*secret.*|.*credential.*|.*private.*key.*|.*keystore.*|.*password.*)$'
~~~

This command only filters by filename. Secrets can hide inside `application.yml`, normally named JSON files, or bytecode, so **finding no suspicious filenames does not mean the artifact is clean**.

### 9.2. Scanning JAR Contents and Generated Output

Extract into a temporary directory in the CI workspace, then run an organization-approved secret scanner. Never print detected values to logs:

~~~bash
mkdir -p target/artifact-inspection
cd target/artifact-inspection
jar -xf ../billing-service.jar

# Search only for suspicious keys/property names; do not dump full file contents.
grep -RIlE 'password|secret|api[_-]?key|private[_-]?key|access[_-]?token' .
~~~

This is a preliminary keyword scan that can produce false positives and will not catch every encoded format. Supplement it with a secret scanner checking entropy/patterns across source, JARs, generated files, container images, and CI artifact history. When a secret is detected, never copy its value into tickets or logs as an example.

### 9.3. Inspecting Native Executables and Container Images

For native executables, `strings` can serve as a preliminary probe:

~~~bash
strings target/billing-service | grep -Ei 'password|secret|api[_-]?key|token'
~~~

`strings` is not a complete secret scanner: secrets may be encoded, compressed, split, or stored in non-printable forms. Conversely, a keyword match might just be a legitimate property name.

For container images:

~~~bash
docker history --no-trunc billing-service:native
~~~

Also inspect image filesystems/layers with an appropriate scanner tool. `docker history` can reveal build commands or metadata, but does not prove every layer is clean. If a secret was copied into one layer and deleted in a later layer, the data can still exist in the earlier layer.

### 9.4. If a Secret Is Found Packaged

1. **Revoke/rotate the secret immediately** in the issuing system; do not just delete the file from source.
2. Identify which artifacts, image tags, registries, caches, and environments received the data.
3. Rebuild from clean source without passing secrets into build/AOT.
4. Delete/revoke old artifacts per your organization's registry and CI policies.
5. Audit logs, caches, and access records to determine exposure scope.

Removing a secret from a JAR or building a new image does not invalidate an exposed credential; the exposed credential must be rotated.

## 10. End-to-End Example: Packaged Template, Runtime Password

Suppose an invoicing service requires an HTML template and a database connection.

**Packaged resources:**

~~~text
src/main/resources/
  templates/invoice.html
  application.yml
~~~

`application.yml` contains only placeholders:

~~~yaml
spring:
  datasource:
    url: ${DB_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
~~~

Register the template:

~~~java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(InvoiceResourceHints.class)
class InvoiceConfiguration {
}

class InvoiceResourceHints implements RuntimeHintsRegistrar {
    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.resources().registerPattern("templates/invoice.html");
    }
}
~~~

Build the application with Maven or Gradle after configuring Spring AOT and Native Image. Verify the JAR contains `templates/invoice.html`; verify resource hints are processed by AOT; build the native executable.

When running the container:

~~~bash
docker run --rm \
  -e DB_URL='jdbc:postgresql://db.internal:5432/billing' \
  -e DB_USERNAME='billing_app' \
  -e DB_PASSWORD='injected-at-runtime' \
  -p 8080:8080 \
  billing-service:native
~~~

In a real environment, `DB_PASSWORD` must be injected from a secret store, never written literally into deployment docs, shell history, Dockerfiles, or CI logs. The example above uses an illustrative value to demonstrate the mechanism.

Verify two behaviors independently:

- The invoice-generation endpoint reads `templates/invoice.html` inside the native executable.
- The database connection receives credentials from the runtime environment/secret mount; inspecting the JAR, generated resources, native binary, and image reveals no real password.

## 11. Pre-Release Checklist

- [ ] Every production classpath resource has a clear path and purpose.
- [ ] Dynamically read files have appropriate resource hints.
- [ ] No resource pattern is broader than necessary.
- [ ] Resources exist in the build output/JAR before building native.
- [ ] The native executable has been run through critical flows reading templates, bundles, schemas, and resources.
- [ ] No `.env`, credential JSON, private keys, or secret files exist in the resource source set.
- [ ] Maven/Gradle resource filtering does not inject secrets into generated outputs.
- [ ] Build-time/AOT environments contain no real credentials.
- [ ] Secrets are supplied from runtime environments, secret managers, or read-only mounts.
- [ ] JARs, generated outputs, native binaries, and container images have been scanned with appropriate tools.
- [ ] Secret values are never printed to logs, exceptions, command lines, or CI reports.
- [ ] If any packaged secret was detected, credentials were rotated and old artifacts handled.

**Remember:** resource hints solve keeping files the application needs to read in Native Image; they do not replace generating/copying files into build outputs. Secrets must stay outside JARs, generated code, native executables, and container layers; supply them only when the application runs. Verify both the presence of required resources and the absence of secret data before releasing.
