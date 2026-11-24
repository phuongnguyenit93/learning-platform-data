# Declaring Provider Classes with UTF-8, Comment Lines, and Duplication Rules

When implementing a plugin mechanism on the **Java classpath**, a class implementing the right interface is not enough for the host application to find it. **java.util.ServiceLoader** relies on a service declaration resource at the path **META-INF/services/**. This file has specific rules regarding naming, UTF-8 encoding, blank lines, comments, and duplicate declarations; getting one detail wrong can prevent providers from being found or cause a ServiceConfigurationError when used.

This lesson focuses on the **provider-configuration file on the classpath**, applicable to ordinary JARs and classpath directories in Java 17+. For *named modules* in JPMS, publishing providers primarily uses the `provides` directive in `module-info.java` and consuming services uses the `uses` directive; that is a different form of registration.

## 1. Distinguishing Service, Provider, and Registration File

Suppose the host needs different text transformers. The contract is defined in a shared API:

**src/api/demo/spi/Formatter.java**

~~~java
package demo.spi;

public interface Formatter {
    String id();
    String format(String input);
}
~~~

A class `demo.plugins.Upper` implementing `Formatter` is a **provider**. For `ServiceLoader` to find it, the plugin JAR needs a resource at the **exact path**:

~~~text
META-INF/services/demo.spi.Formatter
~~~

The initial content is simply:

~~~text
demo.plugins.Upper
~~~

| Component | Specific Example | Role |
| --- | --- | --- |
| Service type | demo.spi.Formatter | Interface that the host knows and wants to find implementations for |
| Configuration file name | META-INF/services/demo.spi.Formatter | Identifies the registered service |
| One configuration line | demo.plugins.Upper | Fully qualified binary name of the provider class |
| Usage call | ServiceLoader.load(Formatter.class) | Creates a service loader to discover providers |

The file name uses the **fully qualified binary name of the service** with dots in the package; not the path `demo/spi/Formatter`, and with no `.class`, `.java`, `.txt`, or `.properties` extension. Inside the file, each provider is also written using its fully qualified binary name, typically `package.ClassName`.

This resource is **not Java source code**. Do not add `import`, `class`, `new` keywords, or Java statement terminators. `ServiceLoader` does not randomly scan all classes that implement `Formatter`; it reads published metadata.

One file can list multiple providers. Multiple JARs can have a resource with the **same name** for one service, because `ClassLoader.getResources` can find multiple matching resources. The mentioned class does not necessarily have to reside in the same JAR as the metadata, but that class must be loadable by the appropriate class loader and must be compatible with the service type.

## 2. UTF-8, Comment, Whitespace, and Blank Line Rules

Consider a valid provider-configuration file:

~~~text
# Text transformation providers

demo.plugins.Upper             # convert to uppercase
demo.plugins.Lower             # convert to lowercase

    demo.plugins.Upper         # second occurrence
~~~

`ServiceLoader` applies the syntax rules specified for the classpath:

1. **The file must be encoded in UTF-8.** Vietnamese text in comments is valid if saved properly as UTF-8. Passing the `-encoding UTF-8` flag to `javac` for `.java` sources does not automatically convert resource encoding.
2. **Each data line contains one provider class name.** The name must be a valid fully qualified Java binary name, such as `demo.plugins.Upper`. Do not write an expression like `new demo.plugins.Upper()`, a path like `demo/plugins/Upper.class`, or put a semicolon at the end.
3. **Spaces and tabs before/after the name are ignored.** An indented line still refers to the same provider. Whitespace inside the class name can make the line invalid.
4. **Blank lines are ignored.** Empty lines or lines containing only spaces/tabs do not increase the provider count.
5. **The `#` character starts a comment.** All characters from the first `#` on a line to the end of the line are ignored. Therefore both comment-only lines and comments after a class name are valid.
6. **Repeated class names are ignored.** If a provider class is declared twice in the same file, or appears in multiple configuration files for the same service, `ServiceLoader` ignores duplicate declarations during provider discovery.
7. **Invalid lines are not treated as comments.** A line with a wrong class name, invalid syntax, or leading to an unloadable class can cause `ServiceConfigurationError` when the iterator actually discovers providers.

The following lines only illustrate **invalid syntax**; do not put them into a real descriptor:

~~~text
demo/plugins/Upper.class
new demo.plugins.Upper()
demo.plugins.Upper;
demo.plugins. Upper
~~~

Do not assume that any characters after the provider name are ignored; only **spaces/tabs around the name** and **the part after `#`** are allowed to be ignored as stated.

## 3. Saving UTF-8 Files Properly

With Gradle or Maven following the standard Java layout, place the resource at:

~~~text
src/main/resources/META-INF/services/demo.spi.Formatter
~~~

After building, verify that the JAR contains the entry **META-INF/services/demo.spi.Formatter**. If the JAR instead contains **src/main/resources/META-INF/services/...** or **resources/META-INF/services/...**, the file is at the wrong location relative to the classpath root.

**Save as UTF-8 without BOM.** A UTF-8 byte-order mark at the beginning of the file can be treated as a character inside the first provider name, causing a format error even though the class name looks right in an editor. No BOM is needed to identify UTF-8.

On **Windows PowerShell 5.1**, `Set-Content -Encoding UTF8` usually writes a BOM. When needing to write the file via PowerShell, you can use .NET and explicitly specify UTF-8 without BOM (the parent directory must already exist):

~~~powershell
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$descriptorText = "# UTF-8 Provider" + [Environment]::NewLine +
                  "demo.plugins.Upper" + [Environment]::NewLine

[System.IO.File]::WriteAllText(
    'resources/upper/META-INF/services/demo.spi.Formatter',
    $descriptorText,
    $utf8NoBom
)
~~~

This snippet is an **illustration of writing a resource**; it is not mandatory to run the example in the next section if you have already created and saved the resource files using an editor. In CI systems, ensure the packaging step does not alter encoding or concatenate text files in a way that corrupts the resource.

## 4. Java 17 Example: Two Provider JARs, Same Configuration File Discovered Multiple Times

We create two different providers (`Upper` and `Lower`), intentionally declaring **`Upper` twice in the first file and once more in the second file**. The host will iterate over `ServiceLoader`, sort the results so stdout has a deterministic order, and print the number of discovered providers.

### 4.1. File Structure

~~~text
src/
  api/demo/spi/Formatter.java
  upper/demo/plugins/Upper.java
  lower/demo/plugins/Lower.java
  host/demo/app/Main.java
resources/
  upper/META-INF/services/demo.spi.Formatter
  lower/META-INF/services/demo.spi.Formatter
~~~

We already have the `Formatter.java` source in Section 1; create the exact three remaining Java files below.

### 4.2. Uppercase Provider Class

**src/upper/demo/plugins/Upper.java**

~~~java
package demo.plugins;

import demo.spi.Formatter;
import java.util.Locale;

public final class Upper implements Formatter {
    public String id() { return "upper"; }
    public String format(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}
~~~

**resources/upper/META-INF/services/demo.spi.Formatter** (UTF-8 without BOM):

~~~text
# UTF-8 comment: uppercase processor

demo.plugins.Upper      # valid provider name
demo.plugins.Upper      # duplicate in same file, ignored
~~~

Both data lines refer to the same `demo.plugins.Upper`. Java will not return two `Upper` providers just because of those two lines. Everything after `#` is a comment, not part of the class name.

### 4.3. Lowercase Provider Class

**src/lower/demo/plugins/Lower.java**

~~~java
package demo.plugins;

import demo.spi.Formatter;
import java.util.Locale;

public final class Lower implements Formatter {
    public String id() { return "lower"; }
    public String format(String input) {
        return input.toLowerCase(Locale.ROOT);
    }
}
~~~

**resources/lower/META-INF/services/demo.spi.Formatter** (UTF-8 without BOM):

~~~text
# Configuration from the second JAR
demo.plugins.Lower
demo.plugins.Upper # duplicate across files, ignored
~~~

The second file mentions the `Upper` class even though that class resides in `upper.jar`. This is valid when `upper.jar` is on the runtime classpath and the class loader can load that class. If `upper.jar` is removed while keeping the `demo.plugins.Upper` line in `lower.jar`'s configuration, a referenced provider can no longer be loaded, causing an error during discovery rather than simply being ignored as a duplicate line.

### 4.4. Host Iterating Over Providers

**src/host/demo/app/Main.java**

~~~java
package demo.app;

import demo.spi.Formatter;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        List<String> lines = new ArrayList<>();
        for (Formatter formatter : ServiceLoader.load(Formatter.class)) {
            lines.add(formatter.id() + "=" + formatter.format("HeLLo"));
        }
        Collections.sort(lines);
        lines.forEach(System.out::println);
        System.out.println("provider count=" + lines.size());
    }
}
~~~

The host imports only `Formatter`; it does not import `Upper` or `Lower`. `Collections.sort` keeps the displayed output independent of the order in which `ServiceLoader` finds the JARs/resources. `Locale.ROOT` in both plugins keeps case conversion independent of the machine's default locale.

### 4.5. Compile, Package, and Run Commands

Run from the directory containing `src` and `resources`, using **PowerShell on Windows**, with JDK 17 or newer. The descriptor files must already be created at the proper paths and saved as UTF-8 without BOM.

~~~powershell
New-Item -ItemType Directory -Force -Path out/api,out/upper,out/lower,out/host,dist | Out-Null

javac --release 17 -encoding UTF-8 -d out/api src/api/demo/spi/Formatter.java
jar --create --file dist/spi.jar -C out/api .

javac --release 17 -encoding UTF-8 -cp dist/spi.jar -d out/upper src/upper/demo/plugins/Upper.java
jar --create --file dist/upper.jar -C out/upper . -C resources/upper META-INF/services

javac --release 17 -encoding UTF-8 -cp dist/spi.jar -d out/lower src/lower/demo/plugins/Lower.java
jar --create --file dist/lower.jar -C out/lower . -C resources/lower META-INF/services

javac --release 17 -encoding UTF-8 -cp dist/spi.jar -d out/host src/host/demo/app/Main.java
jar --create --file dist/host.jar -C out/host .

java -cp "dist/spi.jar;dist/host.jar;dist/upper.jar;dist/lower.jar" demo.app.Main
~~~

For Linux/macOS, create directories with `mkdir -p out/api out/upper out/lower out/host dist` and change the classpath separator in the `java` command from a semicolon to a colon. The `javac` and `jar` commands with relative paths above still work.

**Program stdout:**

~~~text
lower=hello
upper=HELLO
provider count=2
~~~

Although there are three total lines referencing `Upper` across the two resources, `ServiceLoader` discovers only two **distinct provider class names**: `demo.plugins.Upper` and `demo.plugins.Lower`. Therefore the provider count equals 2. This example was compiled with `javac --release 17`, packaged into four JARs, and actually run with the result above.

Inspect the contents of `upper.jar` with:

~~~powershell
jar tf dist/upper.jar
~~~

You must see at least the following two entries in the output list:

~~~text
demo/plugins/Upper.class
META-INF/services/demo.spi.Formatter
~~~

These are the **two entries to look for**, not the entire output of `jar tf`; the actual command also lists directories and `META-INF/MANIFEST.MF`. If the service file does not appear in the JAR, fix the resource packaging step before inspecting Java code.

## 5. Understanding the Duplication Rules Accurately

`ServiceLoader` only deduplicates **identical binary names of provider classes within the same service discovery pass**; it does not resolve every kind of duplication in a plugin system.

| Scenario | Result | Explanation |
| --- | --- | --- |
| `Upper` listed twice in the same resource | No two `Upper` providers | Duplicate class names are ignored |
| `Upper` listed in resources of two JARs | No two `Upper` providers in the same discovery pass | Duplicate names across resources are also ignored |
| `Upper` and `Lower` are two different classes | Both can be loaded | Different class names even with the same interface |
| Two different classes both return `id()` as `"upper"` | Both are still loaded | `id()` is a business convention, not `ServiceLoader`'s deduplication key |
| Iterating over the same `ServiceLoader` again | Returns cached providers | Does not duplicate by re-iterating the iterator |
| Creating a new `ServiceLoader` or calling `reload()` | Can re-discover and re-instantiate providers | No guarantee of a JVM-wide singleton instance |
| Using different class loaders | Each loader has its own visible resource/type scope | Cannot infer system-wide deduplication |

If the host wants `id()` to be unique, it must implement a **conflict-detection policy**. For example, the following code snippet is used **inside a Java method**, after importing `java.util.Map` and `java.util.HashMap`:

~~~java
Map<String, Formatter> byId = new HashMap<>();
for (Formatter provider : ServiceLoader.load(Formatter.class)) {
    Formatter previous = byId.putIfAbsent(provider.id(), provider);
    if (previous != null) {
        throw new IllegalStateException("Duplicate provider id: " + provider.id());
    }
}
~~~

This snippet **illustrates alternative logic**, not a standalone Java program. It detects two different provider classes choosing the same business id, something `ServiceLoader` cannot guess on its own. In a larger plugin framework, you should explicitly decide the behavior on duplicate ids: reject, select by declared priority, or use controlled configuration.

Do not misunderstand the duplicate rule as an automatic quality-check mechanism. `ServiceLoader` only skips **declarations with the same name**; an invalid provider class can still cause discovery to fail. Nor should you deduce that the constructor runs three times and discards two instances: providers are loaded and instantiated **lazily**, and duplicate declarations are skipped during provider lookup.

## 6. When Two JARs Contribute the Same Resource

With two separate JARs, having both contain `META-INF/services/demo.spi.Formatter` is normal. When the host uses the classpath, those multiple resources can be seen together.

However, when building a **fat JAR/uber JAR** by merging dependencies, two entries with the same name can be overwritten or only one kept if the packaging tool does not merge service descriptors properly.

Initial example:

~~~text
upper.jar / META-INF/services/demo.spi.Formatter
  demo.plugins.Upper

lower.jar / META-INF/services/demo.spi.Formatter
  demo.plugins.Lower
~~~

If a JAR-merging tool only keeps `upper.jar`'s file, `Lower` can lose its registration even though `Lower.class` still exists. When creating a fat JAR, the final resource must contain all **distinct provider names**:

~~~text
demo.plugins.Upper
demo.plugins.Lower
~~~

Use the **merge META-INF/services** feature of the corresponding packaging tool; do not merely verify that `.class` bytecode exists in the JAR. Removing duplicate entries in the post-merge file is optional, but losing another class's entry is a bug. Inspect the final JAR using `jar tf` and read the actual resource contents if needed.

For projects using the standard Gradle Java plugin, place the resource under `src/main/resources` so it is included in the JAR. When using Shadow or Maven Shade, check the transformer/merger for service resources matching the exact version of the tool in use.

## 7. Why Might ServiceLoader Fail to See a Provider?

The call `ServiceLoader.load(Formatter.class)` **only creates a loader**; it does not guarantee every provider is loaded successfully. Lazy discovery/instantiation can throw `ServiceConfigurationError` when code iterates the iterator, `hasNext`/`next`, or a stream with an operation that forces provider loading.

Error categories worth checking in order:

- **Wrong resource path:** the file is named `Formatter.txt`, has wrong letter case, or lies under `resources/META-INF/services` inside the JAR. In that case the host may see 0 providers instead of raising a specific error.
- **Invalid file contents:** lines containing `import`, `new`, semicolons, slashes, invalid class names, a leading BOM character, or characters not properly encoded in UTF-8.
- **Missing class at runtime:** the resource is valid, but a listed provider is not on the classpath or is inaccessible to the class loader.
- **Provider does not conform to the SPI:** the class is not assignable to the actual `Formatter` the host is using, is not a concrete class, or lacks a public no-argument constructor required for classpath provider classes.
- **Error inside the provider constructor:** the class is found but instantiation fails; inspect the root cause in the error.
- **Class loader mismatch:** the same interface name is defined by different class loaders as two distinct types; identical spelling does not guarantee cast compatibility.
- **Lost registration file during packaging:** `.class` files are in the fat JAR, but one plugin's service resource was overwritten.

The order of returned providers on the classpath is tied to the order in which `ClassLoader.getResources` locates configuration files and the order of provider names within each file. You should not rely on that order as a business priority rule. If you need to select a preferred plugin, explicitly define id, priority, contract version, and conflict-resolution policy.

`ServiceConfigurationError` is a type of **Error**, so you should not catch all errors, ignore them, and continue with an incomplete plugin list without a policy. In a real system, the host must choose between fail-fast, placing the plugin in an error state, or a controlled recovery mechanism, accompanied by logging the service name, class, JAR, and cause.

## 8. Small Verification Tests for the Format

After running the complete example in Section 4, try each of the following in turn:

1. Keep `Upper` declared twice in the first file and once in the second file. The result still has `provider count=2`.
2. Remove **only the duplicate `Upper` lines** in both descriptors, keeping one line per provider. The result does not change: `lower=hello`, `upper=HELLO`, and `provider count=2`.
3. Add a line `# a UTF-8 comment` to one of the two resources and repackage the JAR. The result does not change.
4. Rename `META-INF/services/demo.spi.Formatter` in one JAR to a wrong name and repackage. The provider registered only via the misnamed resource may disappear; re-check the provider count and explain from the path rather than the implementation code.
5. Replace one provider name with a non-existent class name. When actually iterating over `ServiceLoader`, verify that a configuration error appears rather than being treated as a comment line or silently skipped.
6. Package both plugins into one fat JAR and verify that **both distinct provider names** remain present in a single merged resource.

These tests should be run with a controlled classpath, keeping originals of the configuration files to restore after each test. When changing resources or JARs, re-run the application/new process to avoid misjudging due to still-active class loaders and caches.

## 9. Takeaways and Standard Documentation

**What is each file named?** The fully qualified binary name of the *service* under `META-INF/services`. **What is each data line?** The fully qualified binary name of the *provider class*.

**Is UTF-8 required?** Yes. Use UTF-8 without BOM, especially when files are created via Windows PowerShell 5.1 or encoding conversion tools.

**What does `#` do?** It turns the rest of the line into a comment. Blank lines, spaces/tabs around names, and comments do not add providers.

**What are duplicates ignored by?** By **provider class name**, whether repeated in the same file or across files. That does not guarantee unique business ids, is not a JVM-wide singleton, and does not replace valid-class checks.

**What to check first in practice?** Inspect JAR contents with `jar tf`, confirm the resource sits at the right classpath root, verify encoding and declaration lines, and then ensure you iterate over `ServiceLoader` to trigger provider lookup and instantiation.

Foundational reference: Java SE 17 API Specification, **java.util.ServiceLoader**, section *Deploying service providers on the class path*: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html

A valid provider registration file is a **runtime resource contract**: right name, right location, right UTF-8, right line-by-line syntax. Understanding `#` and the scope of duplicate class-name skipping helps avoid confusing a metadata line with a provider instance or an independent business plugin.