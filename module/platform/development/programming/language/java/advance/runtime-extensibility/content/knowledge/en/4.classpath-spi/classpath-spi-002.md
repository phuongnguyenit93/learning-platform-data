# Naming the META-INF/services File Using the Binary Name of the Service Type

## 1. Why Does the File Name Determine Whether ServiceLoader Finds a Plugin?

When implementing a **Java SPI on the classpath**, a service provider class is not automatically registered just because it writes `implements` for an interface. With the file-based registration mechanism of `java.util.ServiceLoader`, the provider must be declared in a **resource file (provider-configuration file)** at the exact path:

```text
META-INF/services/<fully-qualified-binary-name-of-service-type>
```

The part after `META-INF/services/` is the **fully qualified binary name** of the **service type** requested by the host, typically an `interface` or abstract class. It is not the provider class name, not the module name, not the JAR name, and has no `.java`, `.class`, or `.txt` suffix.

For example, if the host calls:

```java
ServiceLoader.load(com.example.spi.TextFormatter.class);
```

then a provider registered on the classpath can be found through a resource with the exact name:

```text
META-INF/services/com.example.spi.TextFormatter
```

Why? `ServiceLoader` must know **which service it is looking up providers for** before knowing the implementation classes. The file name is the lookup key; **the lines inside the file** list the names of the provider classes to load. Using the wrong name can cause the system to find **0 providers** even though the JAR and implementation class are present.

## 2. How Does a Binary Name Differ from the Name Used in Java Source Code?

For a top-level type, the binary name usually matches the familiar fully qualified name `package.TypeName`. However, for a **nested member type**, the binary name uses `$` to join the enclosing class and the inner type; Java source code uses `.`.

| Declaration/type seen in Java code | Binary name recognized by the JVM | File name to place under `META-INF/services/` |
|---|---|---|
| `com.example.spi.TextFormatter` (top-level) | `com.example.spi.TextFormatter` | `com.example.spi.TextFormatter` |
| `com.example.spi.Contracts.Formatter` (nested type inside `Contracts`) | `com.example.spi.Contracts$Formatter` | `com.example.spi.Contracts$Formatter` |
| `com.example.spi.Outer.Middle.Processor` (multi-level nesting) | `com.example.spi.Outer$Middle$Processor` | `com.example.spi.Outer$Middle$Processor` |

**Exact rule:** obtain `serviceType.getName()` or `YourService.class.getName()` to get the name for the registration file. When the service type is an ordinary reference type, `Class.getName()` returns the binary name; do not manually replace all dots with `$`. **Dots between package components remain intact**; only the separator between nested type levels becomes `$`.

For example:

```java
// Nested type: written as Contracts.Formatter in source code
System.out.println(Contracts.Formatter.class.getName());
// com.example.spi.Contracts$Formatter

System.out.println(Contracts.Formatter.class.getCanonicalName());
// com.example.spi.Contracts.Formatter
```

The snippet above only illustrates the two methods and assumes `Contracts` is an already-declared class in package `com.example.spi`. This is **not a standalone program**; the next section has a full runnable example.

**Do not use `getCanonicalName()` as the file name** when the contract is a nested type. The canonical name is convenient for Java syntax, but does not match the resource name looked up by the classpath SPI. For local or anonymous classes, the JVM name also has auto-generated parts; they are not suitable as public, stable service contracts.

## 3. File Name and File Contents Serve Two Different Roles

Suppose:

- Service type: `com.example.spi.Contracts.Transformer`.
- Service binary name: `com.example.spi.Contracts$Transformer`.
- Implementation class: `com.example.plugin.UpperTransformer`.

Location and contents of the registration file:

```text
RESOURCE PATH IN JAR:
META-INF/services/com.example.spi.Contracts$Transformer

FILE CONTENTS (one line):
com.example.plugin.UpperTransformer
```

The first part describes the **file name/path**, and the second part describes the **actual contents**. Do not copy this entire illustration block into the file. The file should only contain provider class names.

A single service file can register **multiple providers** by writing each fully qualified binary name on its own line:

```text
# Providers of the same service type
com.example.plugin.UpperTransformer
com.example.plugin.LowerTransformer
```

The name `LowerTransformer` here only illustrates a second provider and requires a real implementation class when used. If the application has **two different service types**, each service type needs its own registration file carrying its corresponding binary name.

According to the `ServiceLoader` specification on the classpath:

- The file must be **UTF-8** text; to avoid issues with leading characters, save as **UTF-8 without BOM**.
- Blank lines and leading/trailing spaces or tabs around provider names are ignored.
- Everything from the first `#` to the end of the line is treated as a comment.
- Duplicate provider names are ignored.
- Provider names must also be the **fully qualified binary name** of the service provider class. In this example, the provider is a top-level class so its name uses normal dots.
- The registration file and provider class **do not have to be in the same JAR**, though both must be visible to the appropriate class loader; you should not assume a file anywhere on disk will be scanned.

Note that the file name uses **dots in the package**, for example `com.example.spi.Contracts$Transformer`. Do not turn it into a directory structure `com/example/spi/Contracts$Transformer` under `META-INF/services`: that would be a **different resource path**.

## 4. Complete Java 17+ Example: Nested Service Type

This example intentionally uses a nested type as the service to prove why the file name must contain `$`. The host and plugin use the same contract library, are compiled separately, and are wired by `ServiceLoader` at runtime.

### 4.1. Project Structure

```text
spi-demo/
├── api/
│   └── src/com/example/spi/Contracts.java
├── host/
│   └── src/com/example/host/Main.java
└── plugin/
    ├── src/com/example/plugin/UpperTransformer.java
    └── resources/
        └── META-INF/
            └── services/
                └── com.example.spi.Contracts$Transformer
```

The file under `services/` **has no file extension**. The `$` character is part of the real file name, not a placeholder symbol.

### 4.2. Contract — `api/src/com/example/spi/Contracts.java`

```java
package com.example.spi;

public final class Contracts {
    private Contracts() {
    }

    public interface Transformer {
        String transform(String input);
    }
}
```

`Transformer` is a `public` member interface; member interfaces in Java are implicitly `static`. Therefore the host class can use `Contracts.Transformer.class`, while the binary name is `com.example.spi.Contracts$Transformer`.

### 4.3. Provider — `plugin/src/com/example/plugin/UpperTransformer.java`

```java
package com.example.plugin;

import com.example.spi.Contracts.Transformer;
import java.util.Locale;

public final class UpperTransformer implements Transformer {
    public UpperTransformer() {
    }

    @Override
    public String transform(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}
```

The provider is a `public` class, implements the right service type, and has a `public` no-argument constructor. Those conditions match how `ServiceLoader` instantiates providers on the classpath. The example assumes `input` is not `null`; a real-world contract should specify this case explicitly.

### 4.4. Registration File — `plugin/resources/META-INF/services/com.example.spi.Contracts$Transformer`

**Entire file contents**:

```text
com.example.plugin.UpperTransformer
```

The file name must come from `Contracts.Transformer.class.getName()`, not from the provider name. In particular, **do not** save it as `com.example.spi.Contracts.Transformer`, because that is the canonical name, which violates the rule for nested services.

### 4.5. Host — `host/src/com/example/host/Main.java`

```java
package com.example.host;

import com.example.spi.Contracts.Transformer;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        Class<Transformer> type = Transformer.class;
        String resourceName = "META-INF/services/" + type.getName();

        System.out.println("binary=" + type.getName());
        System.out.println("canonical=" + type.getCanonicalName());
        System.out.println("resource=" + resourceName);

        int providers = 0;
        for (Transformer transformer : ServiceLoader.load(type)) {
            System.out.println("result=" + transformer.transform("Java SPI"));
            providers++;
        }
        System.out.println("providers=" + providers);
    }
}
```

The host knows only the `Transformer` service type, not the `UpperTransformer` class. Printing both the binary and canonical names is a direct way to verify the file name to create.

### 4.6. Compiling, Packaging, Running

From the `spi-demo` directory, with **Windows PowerShell** and **JDK 17+**:

```powershell
New-Item -ItemType Directory -Force -Path out\api,out\host,out\plugin | Out-Null

javac -d out\api api\src\com\example\spi\Contracts.java
javac -cp out\api -d out\plugin plugin\src\com\example\plugin\UpperTransformer.java
javac -cp out\api -d out\host host\src\com\example\host\Main.java

Copy-Item -Path plugin\resources\META-INF -Destination out\plugin -Recurse
jar --create --file out\plugin.jar -C out\plugin .

jar --list --file out\plugin.jar |
    Select-String -SimpleMatch 'META-INF/services/com.example.spi.Contracts$Transformer'

java -cp "out\api;out\host;out\plugin.jar" com.example.host.Main
```

The `jar --list` command filters out the exact line:

```text
META-INF/services/com.example.spi.Contracts$Transformer
```

The program prints:

```text
binary=com.example.spi.Contracts$Transformer
canonical=com.example.spi.Contracts.Transformer
resource=META-INF/services/com.example.spi.Contracts$Transformer
result=JAVA SPI
providers=1
```

On macOS/Linux, replace `;` in the classpath with `:` and use equivalent directory-creation/copy commands. **In PowerShell, when typing or checking a path containing `$Transformer`, put the path in single quotes**, like the argument to `Select-String` above; double quotes can cause PowerShell to interpret `$Transformer` as a variable and corrupt the name.

**Key takeaway:** `ServiceLoader.load(type)` takes the binary name of the service to locate the configuration file on the classpath, reads the provider name from the file, and then finds and instantiates the service provider class. The host code never needs to call `new UpperTransformer()`.

### 4.7. Trying an Incorrect File Name

In a practice copy of the project, rename the file to:

```text
META-INF/services/com.example.spi.Contracts.Transformer
```

while keeping the provider contents unchanged. After repackaging the plugin JAR from a clean directory, if no other valid configuration exists for this service, the program still runs but prints `providers=0` and has no `result=JAVA SPI` line. `ServiceLoader` does not guess that the last dot should have been `$`.

Conversely, keeping the **file name right** while writing a wrong provider class name, such as `com.example.plugin.DoesNotExist`, can trigger `ServiceConfigurationError` during provider iteration. The two scenarios differ: **no valid file found** versus **file found but declared provider cannot be loaded**.

## 5. Placing the File into the JAR at the Right Location

The full resource name is resolved **from the classpath/JAR root**, not from the source code directory. A valid JAR layout looks like:

```text
plugin.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── services/
│       └── com.example.spi.Contracts$Transformer
└── com/
    └── example/
        └── plugin/
            └── UpperTransformer.class
```

If using the standard Maven or Gradle layout, place the source file at:

```text
src/main/resources/META-INF/services/com.example.spi.Contracts$Transformer
```

The build system will normally package the **contents** of `src/main/resources` into the root of the JAR. If the JAR accidentally contains `resources/META-INF/services/...` or `src/main/resources/META-INF/services/...`, the final path **does not match** the resource name `ServiceLoader` looks for.

Watch out for the case where a plugin has the provider class but lacks the library containing the **shared contract** on the classpath: finding the resource is not enough. When loading, the JVM needs to see the service type and a compatible provider, usually via the same contract copy that the host uses.

## 6. Checking the Name via API Instead of Memorizing Manually

For a specific compiled service type, the formula:

```java
String expectedPath = "META-INF/services/" + Transformer.class.getName();
```

is the simplest way to construct the expected path. This snippet requires `Transformer` to be imported or declared in scope.

To verify whether the file is visible through the class loader, you can add diagnostic code to the host in the example:

```java
String path = "META-INF/services/" + Transformer.class.getName();
ClassLoader loader = Thread.currentThread().getContextClassLoader();
System.out.println(loader.getResource(path));
```

This is an **additional snippet** for use in `Main`, not a standalone Java program. If it returns `null`, the inspected class loader does not see a resource with that name. When run with a JAR like the example, the output is usually a URL `jar:file:...!/META-INF/services/com.example.spi.Contracts$Transformer`; the specific URL path varies by machine. When inspecting a multi-classloader plugin system, you must use the class loader corresponding to the `ServiceLoader.load(...)` call; checking the wrong loader can lead to false conclusions.

Check in this order:

1. Use `Transformer.class.getName()` to obtain the true binary name.
2. Compare **character by character** against the file name in `META-INF/services`, including letter case and the `$` character.
3. Use `jar --list --file <jar-name>` to confirm the path exists in the packaged artifact.
4. Confirm the JAR is on the classpath passed to `java` and the class loader can see the resource.
5. If the resource is found but the provider fails to load, check each class name in the contents and verify instantiation requirements and compatibility with the service type.

## 7. Common Mistakes

| Symptom | What Is Wrong? | How to Resolve |
|---|---|---|
| `providers=0` despite provider class existing | File named after the provider instead of the service | File name must be `serviceType.getName()` |
| `providers=0` for a nested service | Used `Contracts.Transformer` instead of `Contracts$Transformer` | Use the binary name with `$` |
| Provider not seen from JAR | File at wrong root, missing `META-INF/services/`, or not copied into JAR | Inspect JAR structure and resource path |
| Provider not seen despite valid file | Plugin JAR is not on the classpath/class loader in use | Check run command and resource visibility |
| `ServiceConfigurationError` | Malformed file contents, non-existent class name, or invalid provider | Check UTF-8 without BOM, provider name, constructor, `implements` |
| Wrong name on Windows/PowerShell | `$` interpreted as a variable inside a double-quoted string | Use single-quoted paths when manipulating files |
| Mismatch after package/rename change | Registration file kept the old binary name | Update file name when changing service type; update contents when changing provider |
| File has `.txt` suffix from text editor | Name in JAR differs from what `ServiceLoader` looks for | Save with exact name, no extension |

Do not fix a `providers=0` error by adding `new Provider()` into the host if the goal is to learn SPI registration: doing so bypasses discovery and hides configuration bugs.

## 8. Distinguishing Registration on Classpath vs. Named Modules

This lesson focuses on **provider JARs on the classpath** (unnamed module), where the `META-INF/services/<binary-name>` file is the registration mechanism.

For a provider developed as a **named module** in JPMS, the primary registration method is declaring `provides ... with ...` in `module-info.java`, for example:

```java
provides com.example.spi.Contracts.Transformer
    with com.example.plugin.UpperTransformer;
```

This is a **declaration snippet inside `module-info.java`**, not a standalone Java file to run with the commands in Section 4. Do not treat the presence or absence of `META-INF/services` as the sole indicator for a plugin operating as a named module. In a real JPMS configuration, the service-consuming module typically also has to declare `uses`.

Whether on the classpath or module path, the general principle remains: **specify the exact service type and declare the corresponding provider**. The registration mechanisms may differ.

## 9. Self-Check Questions and Exercises

1. For `package vn.demo.spi; public interface Parser { }`, what should the file be named? — `META-INF/services/vn.demo.spi.Parser`.
2. For `public class Api { public interface Parser {} }` in package `vn.demo.spi`, what should the file be named? — `META-INF/services/vn.demo.spi.Api$Parser`, not `vn.demo.spi.Api.Parser`.
3. Should a registration file be named after the service or the provider? — **After the service**; the lines inside list providers.
4. If the registration file is right but the provider class does not exist, does it always return an empty list? — No; iterating over providers may throw `ServiceConfigurationError`.
5. Must the file name include `.class` or `.txt`? — No, adding a suffix changes the resource name being searched for.

**Practice:** copy the example in Section 4, use `Transformer.class.getName()` to verify the binary name, then deliberately change `$` to `.` in the registration file name, repackage a clean JAR, and observe the provider count. Rename it back to the exact value from `getName()` and re-run. This exercise distinguishes a **configuration file naming error** from an **implementation class coding error**.

## References

- Oracle Java SE 17, `java.util.ServiceLoader` — section *Deploying service providers on the class path*: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- Oracle Java SE 17, `java.lang.Class#getName()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getName()