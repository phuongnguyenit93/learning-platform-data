# Reading Plugin-Specific Configuration Without Depending on the Working Directory

## 1. The Problem: The Same Plugin Reads the Wrong Configuration When Run from a Different Directory

In a Java system extensible via plugins, each plugin often needs its own configuration: processing mode, endpoints, limits, profile names, mappers, data filenames, or feature flags. A common mistake is reading configuration via a relative path such as:

```java
// Anti-pattern: depends on the current working directory (CWD).
Path file = Path.of("config", "greeting.properties");
Properties properties = new Properties();
try (Reader reader = Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
    properties.load(reader);
}
```

This is a **non-standalone illustrative snippet** (requiring imports, exception handling, and a configuration location). `Path.of("config", ...)` creates a **relative** path; `Files.newBufferedReader` resolves it against the process's working directory, typically represented by `System.getProperty("user.dir")`. When starting the application from a terminal in another directory, through an IDE, Windows Service, systemd, Docker, a scheduler, or a deployment script, that path may point elsewhere and cause missing configuration or, more dangerously, read the wrong file with the same name.

To read configuration **independently of the working directory**, clearly define the **source and path root**. Two common models are:

1. **Default configuration packaged inside the plugin's JAR**: read through the class/module resource API using `getResourceAsStream`, not via a relative file path.
2. **External configuration modifiable after deployment**: the host supplies an **absolute path to each plugin's configuration directory**, and the plugin uses `Path.resolve` to obtain child files.

Both approaches can be combined into one policy: **read defaults in the JAR → apply external overrides → validate → activate**. This model keeps the plugin behaving identically even when the process launch location changes.

> Distinction: "not depending on the CWD" does not mean "not depending on any path at all." External configuration still needs a defined root (CLI, managed environment variable, config root, volume mount, etc.), and the host should pass a validated root as an absolute path.

## 2. Three Easily Confused Location Types

| Concept | Example | Meaning and Risk |
| --- | --- | --- |
| **Current working directory** | `user.dir`, `Path.of(".")`, `new File("settings.yml")` | Location where the process was launched; varies with how it is run, not necessarily where the JAR lives |
| **Classpath/module resource** | `/plugins/greeting/default.properties` | Resource packaged or provided via class/module loading; may reside **inside a JAR** |
| **External configuration directory** | `/etc/myapp/plugins/greeting` or `C:\apps\myapp\config\greeting` | Configuration location decided by the deployer/host; read via NIO `Path` once an absolute root is given |

Several other locations should also be distinguished:

- **Directory containing the JAR**: the physical location of the deployed artifact, not automatically the CWD, and not by default a place where writable configuration should live.
- **`user.home`**: the home directory of the user running the process; unsuitable as an implicit convention across multiple services or multiple accounts.
- **`java.class.path`**: the set of classpath entries, not a configuration directory; it can contain multiple JARs/directories or be altered by a launcher.
- **Temporary directory**: `java.io.tmpdir` is meant for temporary files, not durable configuration sources.

For example, if the host runs from `C:\work` while the JAR is located at `C:\apps\host\lib\plugin.jar`, then `Path.of("config/plugin.properties")` does **not** automatically resolve to `C:\apps\host\lib\config`. It depends on the launch point unless resolved into an absolute path from another root.

## 3. Configuration Packaged Inside a Plugin JAR: Using the Resource API

### 3.1. Locating a Resource via the Plugin-Owning Class

Suppose the provider is at `com.example.plugins.greeting.GreetingPlugin` and the JAR has the layout:

```text
greeting-plugin.jar
├── com/example/plugins/greeting/GreetingPlugin.class
├── META-INF/services/com.example.api.Plugin
└── plugins/greeting/default.properties
```

The plugin reads its default configuration via:

```java
String resourceName = "/plugins/greeting/default.properties";
try (InputStream input =
         GreetingPlugin.class.getResourceAsStream(resourceName)) {
    if (input == null) {
        throw new IllegalStateException(
            "Missing resource in JAR: " + resourceName);
    }
    // Read input here.
}
```

This is an illustrative snippet. `Class.getResourceAsStream("/...")` looks up a resource from the **root of the resource namespace**, according to the class/module loader attached to the class. It works when the plugin is packaged inside a JAR without needing to know which directory the JAR sits in or where the process was started from.

**Note the resource name forms:**

| API | Input Name | Interpretation |
| --- | --- | --- |
| `GreetingPlugin.class.getResourceAsStream("/plugins/greeting/default.properties")` | Leading `/` | Starts at the root of the resource namespace |
| `GreetingPlugin.class.getResourceAsStream("default.properties")` | No leading `/` | Relative to `GreetingPlugin`'s package |
| `GreetingPlugin.class.getClassLoader().getResourceAsStream("plugins/greeting/default.properties")` | No leading `/` | Starts at the root of the class-loader resource namespace |

With `ClassLoader.getResourceAsStream`, **do not put a leading `/`**; a value like `"/plugins/..."` usually will not match the standard resource name. With `Class.getResourceAsStream`, use a leading `/` if you want stability if the implementation's package changes later.

Resources should be placed in a **dedicated namespace per plugin ID**, such as `plugins/greeting/default.properties`, to avoid collisions on names like `config.properties` across JARs. Since a class loader can see resources from multiple JARs and parent delegation can affect the result, the resource name must be sufficiently specific; for complex host/plugin loaders, define an explicit resource resolution policy.

### 3.2. Do Not Mechanically Convert Resources Inside a JAR into a `Path`

A common mistake:

```java
// Anti-pattern: only works in certain packaging modes.
URL url = GreetingPlugin.class.getResource(
    "/plugins/greeting/default.properties");
Path file = Path.of(url.toURI());
```

If the resource sits in a directory on the filesystem, the URL may have a `file:` scheme and convert to a `Path`. When the resource resides **inside a JAR**, the URL may be `jar:file:...!/plugins/greeting/default.properties`. Converting directly via `Path.of(URI)` can throw `FileSystemNotFoundException` or fail if no suitable filesystem provider is mounted.

For **reading content**, `getResourceAsStream` is far cleaner and more appropriate. If you truly need a physical file because a downstream library only accepts a `Path`, consider an API accepting `InputStream` first; if unavoidable, copy the resource to a host-managed temporary location and clean it up after use. Never assume the JAR is unpacked or that the resource is writable.

### 3.3. Which Class Loader Is Looking Up the Resource?

In an SPI application, the host might use:

```java
ServiceLoader<Plugin> services =
    ServiceLoader.load(Plugin.class, pluginClassLoader);
```

`pluginClassLoader` is the loader chosen by the host for the plugin (this snippet is illustrative). If the plugin calls `GreetingPlugin.class.getResourceAsStream(...)`, it uses the **defining context of the implementation class**; this is clearer than arbitrarily grabbing the thread's context class loader.

Avoid unconditionally relying on:

```java
Thread.currentThread()
    .getContextClassLoader()
    .getResourceAsStream("plugins/greeting/default.properties");
```

The TCCL can vary by host, framework, thread pool, or executor, and may not even see the plugin's JAR. If changing the TCCL is required by a framework, the host must restore the old loader in a `finally` block after the operation finishes.

With **named modules (JPMS)**, resource visibility can be subject to module encapsulation rules; when inside the module that owns the resource, you can use `Class.getResourceAsStream` or `Module.getResourceAsStream` as appropriate. Do not rely on the assumption that an arbitrary class loader has permission to read every module resource.

### 3.4. What Role Should Configuration Inside the JAR Play?

It is well suited for **stable defaults**, schemas, small templates, default mapping files, or versioned data shipped alongside code. It is not suitable for real passwords, secret keys, environment-specific settings, or files that must be edited directly on the deployment machine.

Files inside a JAR should be treated as *read-only* resources tied to the plugin version. If you want to update configuration frequently without rebuilding the artifact, add an external configuration layer.

## 4. External Configuration: Host Supplies an Absolute Path by Plugin ID

### 4.1. Creating a Configuration Root with Clear Ownership

Instead of letting plugins guess the CWD, the host determines a `configRoot` from the CLI/launcher or a managed configuration system:

```java
Path root = Path.of(configRootFromLauncher);
if (!root.isAbsolute()) {
    throw new IllegalArgumentException(
        "Config root must be an absolute path");
}
root = root.normalize();
```

This is an illustrative snippet; `configRootFromLauncher` must come from validated host configuration. **Merely calling `toAbsolutePath()` on a relative string still leaves the result dependent on the CWD.** The reliable way when requiring CWD independence is to **require the input path to already be absolute**, or establish another stable root convention at deployment time.

Example layout:

```text
config-root/
├── greeting/
│   └── greeting.properties
├── exporter/
│   └── exporter.properties
└── reporting/
    └── reporting.properties
```

The host selects `greeting` based on a validated plugin ID, then passes `configRoot.resolve("greeting")` to the plugin. The plugin knows only **its own configuration directory** and does not need to care which directory the host is running from or where other plugins' configurations live.

A contract may define:

```java
public interface Plugin {
    String id();
    void start(Path pluginConfigDir) throws IOException;
    void stop();
}
```

This is a condensed API example; business methods can be added depending on functionality. In larger applications, replacing `Path` with `PluginContext` or `ConfigSource` grants only the necessary access capabilities and makes testing easier.

### 4.2. Validating Identifiers and Paths

If `id()` is supplied by the plugin, do not use it directly to join paths without validation:

```java
String id = plugin.id();
if (!id.matches("[a-z][a-z0-9-]*")) {
    throw new IllegalArgumentException("Invalid plugin ID: " + id);
}
Path pluginDir = root.resolve(id).normalize();
if (!pluginDir.startsWith(root)) {
    throw new SecurityException("Plugin config path escapes config root");
}
```

By restricting the ID to simple characters, a plugin cannot supply values like `../../other-plugin` as a directory name. `normalize()` and `startsWith(root)` check the **lexical path**; they are **not sufficient to defend against symbolic links/junctions** pointing outside. If plugins or configuration sources are untrusted, the host needs additional policies controlling filesystem permissions, symlinks, directory ownership, and real-path checks where appropriate. Do not use a class loader as a security boundary.

If the configuration is read-only, grant **read-only** filesystem permissions to the process/plugin where deployable. Do not log raw secrets or sensitive paths in error messages.

### 4.3. Loading Configuration Files with NIO and UTF-8

Once `pluginConfigDir` is an absolute path, the plugin reads:

```java
Path file = pluginConfigDir.resolve("greeting.properties");
Properties properties = new Properties();
try (Reader reader =
         Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
    properties.load(reader);
}
```

This illustrative snippet requires importing `java.nio.file.*`, `java.io.*`, `java.nio.charset.StandardCharsets`, and `java.util.Properties`; the caller must handle `IOException`.

Because `pluginConfigDir` is already an absolute path, `resolve("greeting.properties")` also produces a CWD-independent path. `Files.newBufferedReader` opens the external file via its real path, unlike `getResourceAsStream` which searches resources in the classpath/JAR.

**Encoding matters greatly:** `Properties.load(InputStream)` specifies bytes in ISO-8859-1 with Unicode escapes; if the file contains UTF-8 Vietnamese text, use `Properties.load(Reader)` with `InputStreamReader(..., StandardCharsets.UTF_8)` or `Files.newBufferedReader(..., UTF_8)`. On Windows PowerShell 5.1, some UTF-8 saving methods can add a BOM; write UTF-8 files **without BOM** because a leading BOM can become part of the first key's name when processed by `Properties.load(Reader)`.

### 4.4. Missing File: Default or Error?

When external config is **optional** (only overriding defaults in the JAR), ignore only the **file-does-not-exist** error, while letting unreadable errors surface:

```java
try (Reader reader = Files.newBufferedReader(
        overrideFile, StandardCharsets.UTF_8)) {
    properties.load(reader);
} catch (NoSuchFileException missing) {
    // Allow missing override file; use defaults read from JAR.
}
```

This is an illustrative snippet inside a method declaring `throws IOException`. `AccessDeniedException`, I/O errors, malformed content, or a path pointing to a directory should not be turned into "no override." Do not use `catch (Exception)` and silently ignore it; that hides configuration errors and causes hard-to-trace differences across environments.

If external config is **required**, let `IOException` propagate with a clear cause and do not activate the plugin. For optional config, the fallback conditions must be documented in the contract and logged at an appropriate level.

## 5. Configuration Precedence and Lifecycle

A predictable model:

```text
[plugin JAR]
    /plugins/greeting/default.properties
                    │
                    ▼
           Properties defaults
                    │
                    ▼
[external pluginConfigDir]/greeting.properties  (if present)
                    │
                    ▼
             Apply overrides
                    │
                    ▼
           Validate keys & values
                    │
                    ▼
             STARTED / ACTIVE
```

If both sources contain the key `prefix`, the external file wins per the host/plugin convention. If the external file does not exist and is optional, keep the default. If a critical key is missing or invalid, **fail at startup** with a clear message instead of waiting until the first request fails.

Rules that should be explicitly defined:

- **Precedence:** JAR defaults → external file → (if any) environment/CLI/secret store overrides; this rule must be published consistently.
- **Validation:** data types, value ranges, schema/version, required keys, unknown keys, valid subpaths, and valid endpoints. Do not guess defaults for required options.
- **Lifecycle:** read configuration during `start()`; create an immutable config snapshot after validation; accept requests only after readiness succeeds.
- **Reload:** if re-reading files is needed, the manager must design reload/swap with proper synchronization, avoiding mutating `Properties` while other requests are reading them. For most small plugins, restarting the plugin is simpler and safer.
- **Ownership:** the plugin is responsible for closing streams/watchers it opens; the host owns the config root, permission policy, and plugin ID → directory mapping.
- **Isolation:** each plugin knows only its own namespace and path; it must not accidentally read or write another plugin's config.

Note that **resources inside a JAR and external files serve different purposes**: resources travel with the *code version*, while external configs travel with the *environment and instance*. Do not try to locate a writable directory via `getResource(...)` and edit files inside a JAR.

## 6. Complete Java 17+ Example: JAR Defaults and Dedicated Override File

This example uses Java SPI to discover a `greeting` plugin. **The host takes an absolute path** to the config root and passes the plugin's subdirectory into `start`. The plugin reads `default.properties` packaged in its own JAR, then uses an external `greeting.properties` as an override if that file exists. Running Java from any directory produces the same result as long as the classpath and absolute config root remain the same.

No Maven/Gradle is needed; the commands below are for Windows PowerShell and JDK 17+.

### 6.1. Example Directory Structure

```text
demo/
├── src/
│   └── app/
│       ├── api/
│       │   └── Plugin.java
│       ├── host/
│       │   └── Main.java
│       └── plugin/
│           └── GreetingPlugin.java
├── resources/
│   ├── META-INF/
│   │   └── services/
│   │       └── app.api.Plugin
│   └── plugins/
│       └── greeting/
│           └── default.properties
└── build/                       # Created during compilation
```

### 6.2. Host-Provided Contract

**`src/app/api/Plugin.java`**

```java
package app.api;

import java.io.IOException;
import java.nio.file.Path;

public interface Plugin {
    String id();
    void start(Path pluginConfigDir) throws IOException;
    String greet(String person);
    void stop();
}
```

The API passes a `Path` decided by the host; providers do not use `Path.of("config/...")` or `user.dir` to find external config. The `start` interface is permitted to throw `IOException` to report configuration read errors before the plugin accepts requests.

### 6.3. Plugin Implementation: Two-Layer Configuration

**`src/app/plugin/GreetingPlugin.java`**

```java
package app.plugin;

import app.api.Plugin;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.util.Properties;

public final class GreetingPlugin implements Plugin {
    private static final String DEFAULT_RESOURCE =
        "/plugins/greeting/default.properties";

    private String prefix;

    @Override
    public String id() {
        return "greeting";
    }

    @Override
    public void start(Path pluginConfigDir) throws IOException {
        if (prefix != null) {
            throw new IllegalStateException("Plugin already started");
        }
        if (!pluginConfigDir.isAbsolute()) {
            throw new IllegalArgumentException(
                "pluginConfigDir must be absolute");
        }

        Properties settings = new Properties();

        // 1. Resource bundled inside this plugin's JAR.
        InputStream bundled =
            GreetingPlugin.class.getResourceAsStream(DEFAULT_RESOURCE);
        if (bundled == null) {
            throw new IOException(
                "Missing bundled config: " + DEFAULT_RESOURCE);
        }
        try (Reader reader = new InputStreamReader(
                bundled, StandardCharsets.UTF_8)) {
            settings.load(reader);
        }

        // 2. Optional external override under a host-supplied folder.
        Path external = pluginConfigDir.resolve("greeting.properties");
        try (Reader reader = Files.newBufferedReader(
                external, StandardCharsets.UTF_8)) {
            settings.load(reader); // Keys in override replace defaults.
        } catch (NoSuchFileException missing) {
            // Optional: no override, so keep bundled defaults.
        }

        // 3. Validate before publishing the active state.
        String configured = settings.getProperty("prefix");
        if (configured == null || configured.isBlank()) {
            throw new IllegalStateException(
                "Missing/blank config key: prefix");
        }

        this.prefix = configured;
    }

    @Override
    public String greet(String person) {
        if (prefix == null) {
            throw new IllegalStateException("Plugin not started");
        }
        return prefix + ", " + person + "!";
    }

    @Override
    public void stop() {
        prefix = null; // Simple cleanup for demo.
    }
}
```

Explanation:

- `GreetingPlugin.class.getResourceAsStream(...)` reads defaults from the JAR resource; **does not depend on CWD**.
- `pluginConfigDir.resolve("greeting.properties")` reads external config from the directory supplied by the host; **does not depend on CWD** because the directory is required to be absolute.
- `Properties.load(Reader)` uses UTF-8, so `prefix` can contain Vietnamese characters directly.
- Catches only `NoSuchFileException`: a missing override is valid; permission errors or I/O failures still fail `start`.
- `prefix` is assigned only after reading and validation succeed. `greet` refuses to run before `start`. `stop` is safe to call repeatedly.
- This code uses a single sequential instance; if serving multiple threads or hot reloading, you need synchronization and an immutable config snapshot rather than an unguarded `prefix` field as a production concurrency solution.

### 6.4. Host Selects Plugin and Passes Config Directory

**`src/app/host/Main.java`**

```java
package app.host;

import app.api.Plugin;
import java.nio.file.Path;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "Usage: Main <absolute-config-root>");
        }

        Path root = Path.of(args[0]);
        if (!root.isAbsolute()) {
            throw new IllegalArgumentException(
                "Config root must be absolute: " + root);
        }
        root = root.normalize();

        Plugin plugin = ServiceLoader.load(Plugin.class)
            .findFirst()
            .orElseThrow(() -> new IllegalStateException(
                "No Plugin provider found"));

        String pluginId = plugin.id();
        if (!pluginId.matches("[a-z][a-z0-9-]*")) {
            throw new IllegalArgumentException(
                "Invalid plugin ID: " + pluginId);
        }

        Path pluginDir = root.resolve(pluginId).normalize();
        if (!pluginDir.startsWith(root)) {
            throw new SecurityException(
                "Plugin config directory escapes root");
        }

        // Plugin lifecycle belongs to host, not ServiceLoader.
        try {
            plugin.start(pluginDir);
            System.out.println(plugin.greet("Java"));
        } finally {
            plugin.stop();
        }
    }
}
```

There is exactly **one** provider in this demo, so `findFirst()` gives an easy-to-follow selection. In a system with multiple providers, the host must select explicitly by ID/capability/version rather than relying on `ServiceLoader` order.

The host requires an **absolute config root path**. It does not use `Path.of(".")`, `user.dir`, or `toAbsolutePath()` on a relative path to guess the root directory. When deploying under a service manager, the launcher/container supplies the environment-appropriate absolute path argument.

Note that `startsWith(root)` is a lexical check; paths through symlinks/junctions and filesystem permissions need additional safeguards when plugins or config roots are untrusted.

### 6.5. Resources Bundled with the JAR

**`resources/META-INF/services/app.api.Plugin`**

```text
app.plugin.GreetingPlugin
```

This is the service descriptor enabling `ServiceLoader` to discover the provider. Its content is the exact fully qualified name of the implementation class.

**`resources/plugins/greeting/default.properties`**

```properties
prefix=Xin chào
```

Save the file as UTF-8 **without BOM**. Because the code uses `Properties.load(Reader)`, the Vietnamese value is read properly. Both files will be packaged alongside the implementation class into the **plugin's JAR**, not inside the host's build output.

### 6.6. Compiling and Packaging in PowerShell

In the `demo` directory, with JDK 17+ on `PATH`:

```powershell
New-Item -ItemType Directory -Force build/host, build/provider | Out-Null

# Host contains only API and Main.
javac -encoding UTF-8 -d build/host src/app/api/Plugin.java src/app/host/Main.java

# Plugin is compiled separately while referencing the host's API.
javac -encoding UTF-8 -cp build/host -d build/provider src/app/plugin/GreetingPlugin.java

# Package implementation, META-INF/services, and default resources into a single JAR.
jar --create --file build/greeting-plugin.jar -C build/provider . -C resources .

# Construct absolute paths before running.
$projectRoot = (Get-Location).Path
$hostClasses = Join-Path $projectRoot "build/host"
$providerJar = Join-Path $projectRoot "build/greeting-plugin.jar"
$configRoot = Join-Path $projectRoot "config"

# External override not created yet. Plugin uses defaults inside the JAR.
java -cp "$hostClasses;$providerJar" app.host.Main "$configRoot"
```

**Exact stdout of the final run command:**

```text
Xin chào, Java!
```

Not having the `config/greeting` directory is still valid: the override is optional. Default configuration was found via the resource inside the JAR.

You can verify that the resource was packaged into the JAR using:

```powershell
jar --list --file build/greeting-plugin.jar
```

The listing must contain at least:

```text
app/plugin/GreetingPlugin.class
META-INF/services/app.api.Plugin
plugins/greeting/default.properties
```

These are the **paths that must appear in the listing**, not the entire stdout of `jar --list`, as the JAR may include additional manifest/directory entries and vary in listing order.

### 6.7. Adding External Configuration for That Plugin

Create `config/greeting/greeting.properties`. Use .NET APIs to write UTF-8 **without BOM** consistently even on Windows PowerShell 5.1:

```powershell
$pluginConfigDir = Join-Path $configRoot "greeting"
New-Item -ItemType Directory -Force $pluginConfigDir | Out-Null

$overrideFile = Join-Path $pluginConfigDir "greeting.properties"
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText(
    $overrideFile, "prefix=Chào từ cấu hình ngoài", $utf8NoBom)

java -cp "$hostClasses;$providerJar" app.host.Main "$configRoot"
```

**Exact stdout:**

```text
Chào từ cấu hình ngoài, Java!
```

Because the second `settings.load(reader)` overwrites the `prefix` key, the external config replaces the default value inside the JAR.

### 6.8. Changing CWD and Running Again

Keep the **absolute paths** for host classes, provider JAR, and config root created above, then switch into `build` before invoking Java:

```powershell
Push-Location (Join-Path $projectRoot "build")
try {
    java -cp "$hostClasses;$providerJar" app.host.Main "$configRoot"
} finally {
    Pop-Location
}
```

**Stdout is still:**

```text
Chào từ cấu hình ngoài, Java!
```

In this run, the CWD changed, yet the host still used `$configRoot` as an **absolute path**, while the plugin looked up its default resource from the JAR and external override from the directory passed by the host. Had `Path.of("config/greeting/greeting.properties")` been used inside the plugin, the path would have resolved relative to `build` and could no longer find the file.

To verify the no-override case afterward, delete just `config/greeting/greeting.properties` or switch to another absolute config root without an override: the program prints `Xin chào, Java!` again. No JAR rebuild is needed.

### 6.9. What the Example Demonstrates and What It Omits

The example demonstrates **three core principles**: the resource API for packaged configuration, a host-supplied absolute external path, and defaults → override precedence. It is a classpath SPI example with a single instance and no concurrent contention.

When deploying into a full dynamic plugin system, you will need dedicated class loaders/module layers where appropriate, provider selection policies, config read permissions, versioning/schemas, dependency resolution, a lifecycle state machine, failure monitoring, and safe reload mechanisms. If per-tenant or per-plugin-instance configuration is needed, the host can provide a namespace per instance rather than only per plugin ID.

## 7. Configuration, Secrets, and Namespaces in Real Applications

### 7.1. Environment-Based Configuration

A source policy might look like:

```text
default config in plugin.jar
          │
          ▼
external config directory per plugin
          │
          ▼
explicit overrides via host/environment (if supported)
          │
          ▼
secret provider / injected credentials (if needed)
          │
          ▼
validated immutable Config snapshot
```

Distinguish **default values**, **deployment configuration**, **secrets**, and **runtime state**:

- Defaults in the JAR are easy to track alongside code versions and fit infrequently changing values.
- External config is managed separately per environment, possibly on a volume mount or a centralized permissioned location.
- Secrets should be obtained via a secret manager or secure credential injection mechanism; never embed passwords/tokens in JARs or logs.
- After validation, the plugin should retain a **strongly typed configuration snapshot** instead of repeatedly reading files on every request.

### 7.2. Handling Paths Specified Inside Configuration Files

Configuration might contain a secondary path, such as `cachePath=data/cache`. You must document **which root it is relative to**. If you intend it to be relative to the plugin directory, make that explicit:

```java
Path cache = pluginConfigDir.resolve(
    properties.getProperty("cachePath", "data/cache")).normalize();
```

This is an illustrative snippet. If allowing arbitrary user-supplied keys, you must verify `cache.startsWith(pluginConfigDir)`, access permissions, symlinks/junctions, and real filesystem boundaries when security is required. An **absolute** path inside the config file can cause `resolve` to return a path outside the root; do not skip validation.

Do **not** resolve secondary paths implicitly relative to the CWD. If a path is meant to reside outside the configuration directory, there must be an explicit rule, allowlist, or dedicated permission granted by the host.

### 7.3. Testable Without Changing the CWD

Good design allows testing the provider through an isolated configuration directory:

```java
Path isolatedConfig = tempDirectory.resolve("greeting");
plugin.start(isolatedConfig);
```

This is an illustrative snippet in a test where `tempDirectory` is created by `@TempDir` or `Files.createTempDirectory`; test code must create the override file beforehand if testing precedence. You should also verify:

- Defaults present, no override → uses values from the JAR.
- Valid override present → overrides the right keys.
- Override contains UTF-8 → Vietnamese characters are intact.
- Override file has invalid syntax/keys or is unreadable → reports a meaningful error.
- Running from different CWDs with the same absolute config root → identical results.
- Two plugins with different config dirs → do not accidentally read each other's namespace.
- Paths containing `..`, absolute overrides, or symlinks → adhere to access policy.
- Reading resources when the plugin is packaged **inside a JAR**, not only when the IDE runs classes from a directory.

## 8. Common Errors and How to Diagnose Them

| Symptom | Common Cause | How to Fix |
| --- | --- | --- |
| Runs in IDE, service cannot find file | Code uses `Path.of("config/...")` relying on CWD | Pass an absolute config root from launcher/host |
| Resource exists in source tree, but `getResourceAsStream` returns `null` | Resource not copied into JAR/classpath, wrong path, or wrong case | Check JAR contents and resource name |
| `Class.getResourceAsStream("...")` fails, but with `/` it works | Without `/` the path is package-relative | Use root path `"/plugins/id/..."` |
| `ClassLoader.getResourceAsStream("/...")` returns `null` | ClassLoader API takes resource names without a leading slash | Omit `/` with `ClassLoader` |
| Running from JAR fails when casting URL to `Path` | Resource has a `jar:` URI, not an ordinary file | Read using `InputStream` |
| Changing CWD changes the output | One config layer or secondary path still uses a relative path | Audit all paths, including includes, caches, logs, templates |
| Vietnamese file has garbled accents or key not found | Using `Properties.load(InputStream)` for UTF-8, or file has a BOM | Use a UTF-8 Reader and save without BOM |
| Plugin A reads Plugin B's configuration | Shared generic resource name/path, or wrong TCCL | Namespace by plugin ID; host supplies dedicated directories |
| Override file missing and plugin fails to start | Contract treats external file as required | Clarify required vs optional; if optional, catch only `NoSuchFileException` |
| File has permission error yet plugin silently uses defaults | Catching overly broad exceptions and falling back | Never swallow `AccessDeniedException`/`IOException` |
| After editing file, plugin still uses old configuration | Config loaded only at `start`, no reload | Restart or design synchronized reload and snapshots |
| Old resource still seen after hot reload | Old class loader or provider instance still retained | Create new loader, swap instance, stop old one, clear references |

When encountering `null` from `getResourceAsStream`, check the **actual packaged artifact contents** first; running from an IDE with `src/main/resources` can make things "accidentally work" while the released JAR is missing resources. When external config fails to work, verify the **absolute path passed by the host**, read permissions, and filesystem state rather than merely printing `System.getProperty("user.dir")`.

## 9. Pre-Release Checklist for Plugins

- [ ] Default resources reside in the right location within the plugin artifact, have their own namespace, and are read via `Class.getResourceAsStream`/appropriate module API.
- [ ] Do not use `new File("config/...")` or `Path.of("config/...")` as the primary mechanism to locate plugin configuration.
- [ ] Host supplies an environment-specific absolute config root; each plugin receives its own directory for its validated ID.
- [ ] Precedence among defaults, external overrides, environment, and secrets is clearly defined.
- [ ] Use a UTF-8 Reader for properties files containing Unicode; manage BOM and escapes properly.
- [ ] Missing required resources raise an error; optional external configs fall back only when the **file truly does not exist**.
- [ ] Validate keys/types/ranges before the plugin becomes ACTIVE; avoid printing secret values in logs.
- [ ] Validate subpaths, filesystem permissions, symlinks, and namespace boundaries when input sources are not fully trusted.
- [ ] Close all readers/streams with `try-with-resources`; define clear policies for reload and thread safety.
- [ ] Test the real packaged JAR, running from at least two different CWDs with the same absolute config root, with consistent results.

**Java Documentation References:** [`Class.getResourceAsStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getResourceAsStream(java.lang.String)), [`ClassLoader.getResourceAsStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html#getResourceAsStream(java.lang.String)), [`Files.newBufferedReader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html#newBufferedReader(java.nio.file.Path,java.nio.charset.Charset)), [`Properties.load(Reader)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Properties.html#load(java.io.Reader)), [`ServiceLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html).