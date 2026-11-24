# Importing Multiple Configuration Trees and Choosing `String` vs. `byte[]` in Spring Boot

## 1. Lesson objectives

When running in containers or platforms such as Kubernetes, Spring Boot applications often do not receive all configuration as a single `application.yaml` file. The platform may mount multiple directories, each containing small files: the filename represents the configuration key, and the file content represents the value. Spring Boot calls this organization a **configuration tree**.

This lesson guides you through using `spring.config.import` with the `configtree:` prefix to import **multiple configuration trees**, using wildcards to discover multiple subdirectories, and choosing between **`String` and `byte[]`** when reading values. A single hands-on example lets you observe both text data and binary data mounted outside the application.

After studying this lesson, you will be able to:

- Distinguish importing a single `.properties`/`.yaml` file from importing a tree of configuration files.
- Explain how paths inside a tree turn into property names.
- Import multiple trees using `configtree:/path/*/` or by listing multiple explicit imports.
- Understand processing order when multiple trees supply the same key and how to actively control precedence.
- Read text values as `String` and binary data as `byte[]` via `Environment` or `@ConfigurationProperties`.
- Run a Spring Boot Java 21/Gradle program using files outside the JAR, experiment with changing trees, inspect results, and diagnose causes when configuration fails.
- Recognize security boundaries when configuration trees are used to mount Kubernetes Secrets, Docker secrets, or certificates.

**Context:** Spring Boot 3.3.x and the Config Data mechanism of Spring Boot 2.4+. Paths in the lab are simulated paths using non-sensitive values. The guide does not require a Kubernetes cluster to try out.

## 2. How do a configuration file and a configuration tree differ?

In the familiar approach, you might have a single file:

```yaml
# application.yaml
payment:
  host: payment.internal
  port: 8443
```

Spring Boot reads the YAML and converts it into properties such as `payment.host` and `payment.port`.

In a **configuration tree**, the same data can reside in two files:

```text
/etc/config/payment/
├── host      (content: payment.internal)
└── port      (content: 8443)
```

To read these files as properties, declare:

```properties
spring.config.import=optional:configtree:/etc/config/
```

Then the path relative to the imported root directory becomes the key:

```text
/etc/config/payment/host --> payment.host
/etc/config/payment/port --> payment.port
```

If you change the location to:

```properties
spring.config.import=optional:configtree:/etc/config/payment/
```

then `host` and `port` sit directly beneath the import root; the resulting property names are `host` and `port`.

Core points:

- **Single file:** one complete file containing many keys, using `file:` or a location matching the file format; e.g., `optional:file:/etc/config/application.yaml`.
- **Config tree:** one directory containing many files; **file paths/names** form keys and **file contents** form values; e.g., `optional:configtree:/etc/config/`.
- Files in a config tree **do not need** `.properties`, `.yaml`, or `.txt` extensions. A file named `payment.host` can also produce the property `payment.host`.
- Placing `configtree:` before the path tells Spring Boot to read the file tree under these rules; simply putting a directory beside the JAR does not make it a config tree.

A typical case is a Kubernetes ConfigMap/Secret mounted as one file per key; Docker secrets can also be mounted similarly. An application can also combine config trees with default configuration inside the JAR, environment variables, and CLI arguments.

## 3. How does `spring.config.import` import a config tree?

`spring.config.import` appears inside a configuration document already loaded by Spring Boot, such as `src/main/resources/application.yaml`:

```yaml
spring:
  config:
    import: "optional:configtree:/etc/config/"
```

Here:

- `spring.config.import` requests loading additional Config Data.
- `configtree:` is the source type, indicating the location is a **directory tree**.
- `/etc/config/` is the root of the file tree.
- `optional:` allows the application to continue starting if the location is absent; omit `optional:` when the configuration tree is a mandatory prerequisite.
- Imported values can override matching properties in the document declaring the import. When multiple sources participate, examine Config Data order and other `PropertySource` entries to determine effective values.

For example, if `application.yaml` has:

```yaml
spring:
  config:
    import: "optional:configtree:/etc/config/"
demo:
  title: packaged-default
```

and `/etc/config/demo/title` contains `mounted-title`, the value of `demo.title` read from `Environment` can be `mounted-title`. Non-colliding keys in `application.yaml` continue to be used.

What sets this apart from `spring.config.location` or `spring.config.additional-location` is that `spring.config.import` declares an **additional source directly inside a loaded configuration document**, ideal when the application knows the directory to import. For a single extensionless YAML file mounted by the platform, that is still a **single file**, so use file import syntax with an appropriate extension hint; do not use `configtree:` merely because the filename has no extension.

## 4. Importing multiple trees under the same parent directory

Suppose the platform mounts two independent configuration groups:

```text
/etc/config/
├── dbconfig/
│   └── db/
│       ├── host
│       └── username
└── mqconfig/
    └── mq/
        ├── host
        └── username
```

Each file holds one value; for instance, `dbconfig/db/host` contains `db.internal` and `mqconfig/mq/host` contains `mq.internal`.

You can declare:

```properties
spring.config.import=optional:configtree:/etc/config/*/
```

Or in YAML:

```yaml
spring:
  config:
    import: "optional:configtree:/etc/config/*/"
```

The `*/` wildcard expands **immediate subdirectories** of `/etc/config/`. Spring Boot imports each subdirectory as a separate tree. Because the root of each import is `dbconfig/` or `mqconfig/`, the resulting keys are:

| Original file | Property in `Environment` | Sample value |
| --- | --- | --- |
| `dbconfig/db/host` | `db.host` | `db.internal` |
| `dbconfig/db/username` | `db.username` | `reader` |
| `mqconfig/mq/host` | `mq.host` | `mq.internal` |
| `mqconfig/mq/username` | `mq.username` | `consumer` |

**Difference to remember:** if you directly import `configtree:/etc/config/` without a wildcard, the `dbconfig` and `mqconfig` directories lie **below the tree root**, so key names can carry those extra path segments, such as `dbconfig.db.host`. With `configtree:/etc/config/*/`, each immediate subdirectory is a separate root, so properties are `db.host` and `mq.host`.

The wildcard does not recursively scan all subdirectories indefinitely to treat them as separate roots. It expands only one directory level immediately beneath the parent. However, once a config tree root is found, files located deeper **inside that tree** still generate properties according to their corresponding path segments. These are two distinct operations: **expanding the list of roots** and **reading files inside each root**.

### 4.1. Ordering when using wildcards

Directories expanded by a wildcard are sorted **alphabetically by absolute path**. Example:

```text
/etc/config/
├── 10-common/
├── 20-service/
└── 30-overrides/
```

If multiple trees declare the same key, import order can determine which source takes precedence; for imports processed later, colliding values can override earlier sources. Do not build critical logic relying on arbitrary directory names created by an external system.

The safest approach is to use separated namespaces such as `db.*`, `mq.*`, and `smtp.*` so trees do not compete over the same keys. If you intentionally want one tree to override another, declare explicit locations and test with mock data.

### 4.2. Listing multiple trees explicitly

When intentional ordering is needed, you can write:

```yaml
spring:
  config:
    import:
      - "optional:configtree:/etc/config/common/"
      - "optional:configtree:/etc/config/service/"
      - "optional:configtree:/etc/config/overrides/"
```

Imports in a list are processed in declaration order; **a later import has higher precedence than an earlier import** when both supply the same key under the same mechanism. By listing them explicitly, you control order without depending on wildcard directory names.

A source may be declared repeatedly, yet Config Data imports it only once under Spring Boot rules. Nor should you feed the same tree through both a wildcard and an explicit list without a clear reason; this study example picks one approach per run.

## 5. Why choose between `String` and `byte[]`?

In a configuration tree, file contents may be:

- **Text:** URLs, hostnames, mock usernames, environment labels, configuration strings, or values libraries expect as text.
- **Binary data:** bytes of a key, a certificate/key blob, binary files, or payloads that a consuming component expects as raw bytes untouched.

Spring Boot allows binding configuration tree values to both `String` and `byte[]`, depending on the data type you expect.

| Case | Recommended type | Reason |
| --- | --- | --- |
| Hostname `db.internal` | `String` | Value is text |
| Label `welcome-from-tree` | `String` | Application needs to display or compare strings |
| Payload `[0, 1, 127, 255]` | `byte[]` | Contains bytes that cannot be assumed to be valid UTF-8 characters |
| Encrypted data block or binary key | `byte[]` | Avoids charset conversion altering the data |
| PEM text needed by a string-reading library | `String` or `byte[]` per consumer API | Must clarify encoding, format, and data contract |

**Do not use `new String(bytes)` without a charset** to handle binary files. If data is confirmed to be UTF-8 text, decode explicitly with `new String(bytes, StandardCharsets.UTF_8)` when truly needed. If it is raw bytes, keep `byte[]` and do not attempt to display them as strings.

Another warning: shell `echo` usually appends a trailing newline to files. In a config tree, file content is the value, so an unintended newline can affect the string or bytes read. When testing binary data, use explicit byte-writing operations; when testing text, use commands that do not add trailing newlines.

Even though a security key can be bound as `String`, a `String` is immutable and sensitive bytes cannot be wiped from memory on demand. For APIs taking bytes and requiring data to stay intact, `byte[]` is the better choice. Data type selection does not replace controlling file read permissions, secret lifecycles, and no-secret-logging policies.

## 6. Sample application: Multi Config Tree Observer

We will create a Spring Boot console application to **observe multiple trees simultaneously**. The application receives two kinds of data:

1. `demo.welcome`: a text string printed to screen.
2. `demo.payload`: four test binary bytes; the program prints only the length, never the contents.
3. `db.host` and `mq.host`: strings from two different trees proving that wildcard imports create separate namespaces.

Project structure:

```text
multi-config-tree/
├── build.gradle
├── settings.gradle
├── gradlew
├── gradlew.bat
├── src/main/java/dev/example/tree/
│   ├── MultiConfigTreeApplication.java
│   └── DemoProperties.java
├── src/main/resources/
│   └── application.yaml
└── run/
    └── trees/
        ├── 10-app/
        │   └── demo/
        │       └── welcome
        ├── 20-binary/
        │   └── demo/
        │       └── payload
        ├── 30-db/
        │   └── db/
        │       └── host
        └── 40-mq/
            └── mq/
                └── host
```

The `run/trees` path sits outside `src/main/resources`, so these file values are not packaged into the JAR. It simulates an external container mount. Files named `welcome`, `payload`, and `host` **need no extension**.

### 6.1. Gradle and Java 21

`settings.gradle`:

```groovy
rootProject.name = 'multi-config-tree'
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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Use the Gradle Wrapper from an initialized Spring Boot Gradle project, or generate the matching skeleton via Spring Initializr. If working inside a repository with its own conventions and version catalog, preserve the repository's dependency conventions rather than introducing extra version-management mechanisms.

### 6.2. Declare the import

`src/main/resources/application.yaml`:

```yaml
spring:
  main:
    web-application-type: none
  config:
    import: "optional:configtree:./run/trees/*/"

demo:
  welcome: fallback-from-jar
```

The application runs without starting a web server. `demo.welcome` has a baseline value inside the JAR when the trees are not found. Configuring `optional:` allows running when the lab directory does not yet exist, convenient for comparing before and after creating the files.

In this experiment, we run from **the project root directory**, so the relative path `./run/trees/` points to the directory drawn in the diagram. If you switch working directories, recalculate the path; files in `./run/trees` do not automatically travel with the JAR's location.

### 6.3. Typed binding with `@ConfigurationProperties`

`src/main/java/dev/example/tree/DemoProperties.java`:

```java
package dev.example.tree;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        String welcome,
        byte[] payload
) {}
```

Property `demo.welcome` comes from `10-app/demo/welcome`; `demo.payload` comes from `20-binary/demo/payload`. The `demo` prefix binds to the Java record. The `byte[]` field preserves the expected data type of the binary payload.

### 6.4. Using `Environment` and the bound bean

`src/main/java/dev/example/tree/MultiConfigTreeApplication.java`:

```java
package dev.example.tree;

import java.util.Arrays;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

@SpringBootApplication
@ConfigurationPropertiesScan
public class MultiConfigTreeApplication {

    public static void main(String[] args) {
        SpringApplication.run(MultiConfigTreeApplication.class, args);
    }

    @Bean
    ApplicationRunner observe(
            ConfigurableEnvironment environment,
            DemoProperties demo) {
        return args -> {
            String welcome =
                    environment.getProperty("demo.welcome", String.class);
            byte[] payload =
                    environment.getProperty("demo.payload", byte[].class);

            System.out.println("=== MULTI CONFIG TREE ===");
            System.out.println("workingDir = "
                    + System.getProperty("user.dir"));
            System.out.println("activeProfiles = "
                    + Arrays.toString(environment.getActiveProfiles()));
            System.out.println("demo.welcome (String) = " + welcome);
            System.out.println("demo.welcome bound = " + demo.welcome());
            System.out.println("demo.payload (byte[]) length = "
                    + lengthOrMissing(payload));
            System.out.println("demo.payload bound length = "
                    + lengthOrMissing(demo.payload()));

            System.out.println("db.host = "
                    + environment.getProperty("db.host", "<missing>"));
            System.out.println("mq.host = "
                    + environment.getProperty("mq.host", "<missing>"));

            System.out.println("Sources containing demo.welcome:");
            for (PropertySource<?> source
                    : environment.getPropertySources()) {
                if ("configurationProperties".equals(source.getName())) {
                    continue;
                }
                if (source.getProperty("demo.welcome") != null) {
                    System.out.println(" - " + source.getName());
                }
            }
        };
    }

    private static String lengthOrMissing(byte[] bytes) {
        return bytes == null ? "<missing>"
                : Integer.toString(bytes.length);
    }
}
```

The program intentionally prints only the length of the bytes. In this lab the payload is dummy data, yet when applied to real secrets, never log raw bytes, hex, base64, or key contents.

`environment.getProperty("demo.welcome", String.class)` requests the value represented as text; `environment.getProperty("demo.payload", byte[].class)` requests a byte array. `@ConfigurationProperties` demonstrates binding the same key set into a structured Java type.

Note: printing `PropertySource` names is for observation in this lesson. Exact names can depend on how the app runs and the version; this snippet is not a complete provenance prover for every binding or placeholder pattern.

## 7. Preparing four data trees

### 7.1. On Linux or macOS using Bash

From the `multi-config-tree` root directory:

```bash
mkdir -p run/trees/10-app/demo
mkdir -p run/trees/20-binary/demo
mkdir -p run/trees/30-db/db
mkdir -p run/trees/40-mq/mq

printf '%s' 'welcome-from-tree' > run/trees/10-app/demo/welcome
printf '\x00\x01\x7f\xff' > run/trees/20-binary/demo/payload
printf '%s' 'db.lab.internal' > run/trees/30-db/db/host
printf '%s' 'mq.lab.internal' > run/trees/40-mq/mq/host
```

The example uses `printf` in Bash to create a payload of four bytes `00 01 7F FF`. `\x` escape handling depends on the shell, so the example specifies Bash; do not assume every `/bin/sh` interpreter handles it identically.

### 7.2. On Windows PowerShell

From the `multi-config-tree` root directory:

```powershell
New-Item -ItemType Directory -Force 'run/trees/10-app/demo' | Out-Null
New-Item -ItemType Directory -Force 'run/trees/20-binary/demo' | Out-Null
New-Item -ItemType Directory -Force 'run/trees/30-db/db' | Out-Null
New-Item -ItemType Directory -Force 'run/trees/40-mq/mq' | Out-Null

Set-Content -NoNewline -Encoding UTF8 'run/trees/10-app/demo/welcome' 'welcome-from-tree'
Set-Content -NoNewline -Encoding UTF8 'run/trees/30-db/db/host' 'db.lab.internal'
Set-Content -NoNewline -Encoding UTF8 'run/trees/40-mq/mq/host' 'mq.lab.internal'

$binaryPath = Join-Path (Get-Location) 'run/trees/20-binary/demo/payload'
[System.IO.File]::WriteAllBytes($binaryPath, [byte[]](0, 1, 127, 255))
```

`WriteAllBytes` writes the exact four bytes without depending on encoding or newline rules of text-writing commands.

For text files containing only ASCII in this lab, UTF-8 writing utilities are appropriate. When handling real-world data, verify the file's encoding before deciding between `String` and `byte[]`.

## 8. Running and observing

### 8.1. Running before creating the trees

To observe baseline values, temporarily rename `run/trees` or run in a working copy before creating the files in section 7.

macOS/Linux:

```bash
./gradlew bootRun
```

Windows:

```powershell
.\gradlew.bat bootRun
```

Expected main output:

```text
demo.welcome (String) = fallback-from-jar
demo.payload (byte[]) length = <missing>
db.host = <missing>
mq.host = <missing>
```

The application still starts because the import has `optional:`.

### 8.2. Running after creating the trees

After creating all four trees, run `bootRun` from the project root directory. Sample output:

```text
=== MULTI CONFIG TREE ===
workingDir = .../multi-config-tree
activeProfiles = []
demo.welcome (String) = welcome-from-tree
demo.welcome bound = welcome-from-tree
demo.payload (byte[]) length = 4
demo.payload bound length = 4
db.host = db.lab.internal
mq.host = mq.lab.internal
Sources containing demo.welcome:
 - ...10-app...
 - ...application.yaml...
```

`PropertySource` names are abbreviated for illustration. On your machine, use actual output to verify the locations.

From this output, you can see one text file read as `String`, one binary file bound as `byte[]`, and two other trees supplying two separate property groups. `fallback-from-jar` exists in YAML yet does not beat `welcome-from-tree` imported from external configuration.

### 8.3. Packaging the JAR

```bash
./gradlew bootJar
java -jar build/libs/multi-config-tree-0.0.1-SNAPSHOT.jar
```

On PowerShell:

```powershell
.\gradlew.bat bootJar
java -jar build\libs\multi-config-tree-0.0.1-SNAPSHOT.jar
```

Both run commands behave equivalently only when the working directory points to the project root and no other override sources differ. The JAR also works on a machine lacking the lab directory thanks to `optional:`, though without the trees values revert to defaults or are absent.

If you move the JAR to another directory, the relative path `./run/trees/` depends on the runtime directory used at launch. In containers, prefer stable absolute mount paths such as `/etc/config/`, while ensuring process read permissions.

## 9. Four extended experiments to understand precedence and data

### Experiment A — change text in one tree

Edit `run/trees/10-app/demo/welcome` to `second-value`, keeping the payload unchanged. Start a new application run:

```text
demo.welcome (String) = second-value
demo.payload (byte[]) length = 4
```

Changing text alone does not alter data in the binary tree. This illustrates that each file in a tree is an independent value source.

### Experiment B — two trees supplying the same key

Create an additional tree:

```text
run/trees/50-overrides/demo/welcome
```

Content:

```text
overridden-by-later-tree
```

The wildcard will also expand `50-overrides`. Here, subdirectories prefixed with `10-`, `20-`, `30-`, `40-`, `50-` are sorted alphabetically, and both `10-app` and `50-overrides` declare `demo.welcome`; colliding values in a later import can override earlier imports:

```text
demo.welcome (String) = overridden-by-later-tree
```

To prevent unpredictable outcomes if the system unexpectedly mounts additional directories, do not rely on this colliding-key structure as an operational default. When intentional overrides are needed, switch to an explicit `spring.config.import` list with predetermined order.

### Experiment C — change the tree root location

Change the import to:

```yaml
spring:
  main:
    web-application-type: none
  config:
    import: "optional:configtree:./run/trees/"
```

Then try accessing:

```text
10-app.demo.welcome
20-binary.demo.payload
30-db.db.host
40-mq.mq.host
```

Because the import root is `run/trees/`, directory segments `10-app`, `20-binary`, etc., become part of the key. `demo.welcome` will no longer map from `10-app` the way it did with the wildcard import. With sample code expecting `demo.welcome`, it can now revert to `fallback-from-jar`.

This experiment explains why choosing to import **one parent tree** vs. **multiple child trees** changes the property namespace. When changing the import, update property names or directory layout accordingly rather than changing only a single path string.

### Experiment D — change the binary payload size

Overwrite the payload file with bytes `[10, 20, 30, 40, 50]` using a byte write and restart:

```text
demo.payload (byte[]) length = 5
demo.payload bound length = 5
```

This exercise requires no inspection of secret values. It proves the file is loaded as bytes and the application receives the exact expected data length.

**Lifecycle note:** configuration tree import is part of Spring Boot's startup configuration loading. Changing mounted file contents does not automatically update `@ConfigurationProperties` beans inside a running process; dynamic refresh mechanisms must be designed, configured, and tested separately. In this lab, always start a fresh process after each change.

## 10. When to use wildcards vs. an explicit list?

| Scenario | Sensible approach | Limitation to consider |
| --- | --- | --- |
| Multiple independent mounts, non-overlapping namespaces | `optional:configtree:/etc/config/*/` | Wildcard expands only immediate subdirectories |
| One volume containing full namespaces under one root | `optional:configtree:/etc/config/` | Subdirectory names below the root become part of property names |
| Multiple trees intentionally overriding the same key | List `configtree:` imports in explicit order | Later order can win among imports of the same type |
| One complete YAML mounted as a file | `optional:file:/etc/config/application.yaml` | This is a file, not a tree |
| One YAML file missing an extension | File import with extension hint like `file:/etc/config/myconfig[.yaml]` | Do not use `configtree:` for a single YAML file |
| Missing mount is a critical configuration error | Import without `optional:` | Application may fail to start when location is absent |
| Binary file needing raw bytes preserved | Bind `byte[]` | Do not log; do not accidentally decode with default charset |
| Text file consumed as string | Bind `String` | Encoding and newline conventions must be established |

Good operational practice typically uses wildcards when **trees are independent with distinct key names**, and explicit lists when **override order is an operational contract**. Both still require stable mount paths and appropriate read permissions.

## 11. Kubernetes and Docker: deployment implications

On Kubernetes, ConfigMaps and Secrets can be mounted as volumes. Typically each key in the data source appears as a file at the mount path. Spring Boot does not need to know whether the data originally came from a ConfigMap or a Secret: with `configtree:` it reads the existing file structure inside the container.

Example with two volume mounts:

```text
/etc/config/
├── configmap/
│   └── service/
│       └── region
└── secret/
    └── service/
        └── token
```

Declaring:

```yaml
spring:
  config:
    import: "configtree:/etc/config/*/"
```

lets the two files provide `service.region` and `service.token`. `service.region` is normally consumed as text; `service.token` can be read as `String` or `byte[]` depending on the consuming library's interface.

Do not expose token file contents in diagnostic endpoints or logs. Actuator endpoints such as `/actuator/env` and `/actuator/configprops` require access controls and appropriate value-masking policies. Kubernetes Secrets are a mechanism for distributing sensitive data, not a guarantee of absolute secrecy if cluster, mount, log, or process-memory access is compromised.

With Docker Swarm secrets, a secret named `db.password` can be mounted as a file:

```text
/run/secrets/db.password
```

It can then be imported with:

```properties
spring.config.import=optional:configtree:/run/secrets/
```

and accessed via the `db.password` property.

Sensitive files in real environments must be created and managed by proper deployment mechanisms; never commit real secrets or keys to a repository. If secret rotation is required in a running process, design reload or restart behavior synchronized with how the platform updates volumes. Do not assume Spring Boot refreshes automatically whenever a file changes.

## 12. Common errors and how to handle them

**Mounted an entire directory yet see no properties.** Check whether `spring.config.import` uses `configtree:` instead of `file:`, whether the path points right at the tree, and whether the process has read permissions on the files. For unexpected names, review the import tree root and key-forming directory segments.

**Wildcard import fails to find a child tree.** The `*/` wildcard expands only immediate subdirectories beneath the parent directory. If data sits deeper, use a matching parent path or list locations explicitly.

**Property names acquire an unexpected extra prefix.** If you import `configtree:/etc/config/`, a `mysql/` directory beneath the root appears in key names like `mysql.username`. If you import `configtree:/etc/config/*/`, `mysql/` is its own root and keys inside can be `username`. Choose the root based on the desired namespace.

**Values from a tree are unexpectedly overridden.** Check other trees with the same key, wildcard sort order, import lists, profiles, environment variables, Java system properties, CLI, and other sources. Draw conclusions from final values and actual configuration, not solely from the file you just edited.

**Application fails to start when a tree is missing.** If the location is optional, prepend `optional:` before `configtree:`. If it is a mandatory volume, keep the startup failure to catch missing deployment mounts early.

**Reading bytes yields strange characters or decoding errors.** Check whether you are treating a binary payload as text. `byte[]` is for raw data; if you must convert bytes to a string, do so only for data known to have valid encoding and specify the charset explicitly.

**Binary data length is larger than expected.** Check whether the file has a BOM, newline, line terminator, or encoding added by the writing tool. Avoid `echo` when exact bytes matter. Use `WriteAllBytes` or an appropriate binary writer.

**Binding `DemoProperties` receives `null`.** Verify the import actually loaded the file, the key name is `demo.payload`, and `@ConfigurationPropertiesScan` scans the package containing the record. If the application started before the mount existed, restart after creating the mount.

**Edited a file in the volume yet the running application keeps the old value.** Config Data is normally loaded at startup. Check whether the process restarted, and if using a refresh mechanism, verify that mechanism's behavior separately.

**Cannot see data in Actuator.** The endpoint may not be exposed, the user may lack permissions, or values are intentionally masked. Do not disable security to read secrets; in the lab, observing dummy keys and payload lengths suffices.

## 13. Step-by-step practice checklist

1. Create the Spring Boot project, declare the wildcard import, and run before creating trees to observe baseline values.
2. Create `10-app` with text, restart, and observe `demo.welcome`.
3. Create `20-binary` with a four-byte payload, restart, and observe both byte lengths.
4. Create `30-db` and `40-mq` to see `db.host` and `mq.host` from two namespaces.
5. Add `50-overrides`, predict, and confirm colliding key precedence with multiple trees.
6. Try switching the import from `*/` to a parent tree and note differences in property names.
7. Compare optional import vs. mandatory import when the path does not exist.
8. Restore the initial lab configuration and use only dummy data, avoiding creating sensitive files in the project.

Result tracking table:

| Run | Import/tree changed | Expectation | Local result |
| --- | --- | --- | --- |
| 1 | No trees, with `optional:` | `fallback-from-jar` | Record yourself |
| 2 | Add text tree | `welcome-from-tree` | Record yourself |
| 3 | Add four-byte payload | Length = 4 | Record yourself |
| 4 | Add DB and MQ trees | Two independent hosts | Record yourself |
| 5 | Add override tree | Override tree value wins | Record yourself |
| 6 | Change import root | Property names change | Record yourself |
| 7 | Missing mandatory tree | Location loading error | Record yourself |

## 14. Self-check questions

**1. Why is `configtree:` needed when mounting one file per key?** Because Spring Boot needs to read an entire directory tree, taking relative paths as property names and each file's content as the value; single-YAML-file syntax does not describe this data layout.

**2. Do `configtree:/etc/config/` and `configtree:/etc/config/*/` always produce the same property names?** No. The first sets `config` as the root; the second sets each immediate subdirectory as a root, so directory name segments can appear or disappear in keys.

**3. Can multiple trees be imported without using a wildcard?** Yes. Use a `spring.config.import` list with explicit `configtree:` locations, especially when you want to control override order.

**4. If a payload contains the byte `FF`, should you use `String` or `byte[]`?** For a binary payload needing exact byte preservation, use `byte[]`. Do not assume byte `FF` is a valid UTF-8 character.

**5. Why shouldn't you use `System.out.println(Arrays.toString(secretBytes))` to debug production?** Because it can leak full sensitive data into logs. Length or presence/absence checks using test data are usually enough to confirm imports work.

**6. If a secret file's content changes while the app is running, do configuration beans update immediately?** Not by default. Initial loading occurs at startup; dynamic refresh is a separate design that must be evaluated.

**7. When multiple trees contain the same key, which factors should you inspect?** Import order, wildcard order, location groups if any, profiles, and higher-precedence configuration sources. For predictable results, minimize key collisions or list locations explicitly.

**8. What if a mandatory tree volume is not mounted in production?** Do not use `optional:` to hide its absence. Let the application fail and fix deployment configuration rather than silently running with unexpected values.

## 15. Applying to real-world projects

Configuration trees shine when a deployment platform distributes **multiple property groups via the filesystem**, especially when each application consumes several distinct ConfigMaps or Secrets. Choose `configtree:` over YAML file paths when one file corresponds to one key; choose wildcards when importing independent child trees, and use explicit import ordering when override rules are designed upfront.

Keep business keys clearly namespaced, match Java types to file contents, control encoding and newlines, never output secrets to logs, and never assume dynamic refresh exists by default. For configuration incidents, start from the actual mount path, import root, generated property names, tree ordering, and target value types. Once each factor is observed individually, combining multiple Spring Boot configuration sources becomes predictable and controllable.

### References

- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html), especially *Importing Additional Data* and *Using Configuration Trees*.
