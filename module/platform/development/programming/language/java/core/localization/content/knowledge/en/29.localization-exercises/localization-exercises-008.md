# Packaging a JAR or Runtime Image and Verifying Translation Resources in Java

## 1. Practice Goals and Three Types of Deployment Artifacts

A Java application using `ResourceBundle` to display multilingual messages can run cleanly inside an IDE yet fail on deployment:

- `Texts_vi.properties` exists in `src/main/resources`, yet is missing from the JAR.
- The file exists inside the JAR at the wrong path, causing `ResourceBundle.getBundle(...)` to miss it.
- The program still loads the Vietnamese bundle, yet numbers/dates format differently on a **minimal runtime image** because JDK locale data is missing.
- The application works only with a full JDK on the developer's machine, while the distributed package lacks a runtime.
- A `jpackage` installer bundles the right runtime, yet the launcher uses the wrong JAR—or copies only the runtime directory while omitting application code/resources.

To solve this properly, distinguish **three artifacts**:

| Artifact | Tool | Contents | Typical Usage |
| --- | --- | --- | --- |
| **Application JAR** | `jar`, Maven, or Gradle | Application `.class` and `.properties` files; optional manifest | `java -jar app.jar`; requires an installed Java runtime |
| **Custom runtime image** | `jlink` | JVM and selected **Java modules** (e.g., `java.base`, `jdk.localedata`) | `runtime/bin/java -jar app.jar`; **does not automatically include the app JAR** |
| **Application image** | `jpackage --type app-image` | Launcher + application/JAR + compatible runtime image | Runs the OS-specific native launcher |

Key point: **`jlink` does not automatically package `Messages*.properties` or regular classpath applications into the runtime image.** It creates a runtime containing Java modules. To build a truly self-contained distribution with both app and runtime, ship the **app JAR alongside the runtime** or use `jpackage` (or another packaging mechanism).

This hands-on guide uses **Java 17+**, one `ResourceAudit` class, and three `.properties` files. Afterward, you will know how to:

1. Build an application supporting both English and Vietnamese.
2. Compile, package an executable JAR, and verify its actual entries.
3. Build a custom runtime image with `jlink` including appropriate locale data.
4. Run the app JAR on the newly built runtime and verify messages and formatting.
5. Optionally combine the JAR and runtime into an app image with `jpackage`.
6. Define packaging verification criteria to catch missing files, missing modules, wrong charsets, or wrong paths.

## 2. ResourceBundle Has Two Layers to Verify

`ResourceBundle` relies on:

- **Base name**: e.g., `com.example.i18n.Texts`.
- **Requested locale**: e.g., `Locale.forLanguageTag("vi-VN")`.
- **Runtime classpath/module path**: where `.properties` files or bundle classes reside.

With the example base name, the application resource layout on the classpath is:

```text
com/example/i18n/Texts.properties
com/example/i18n/Texts_en.properties
com/example/i18n/Texts_vi.properties
```

In Java, calling:

```java
ResourceBundle bundle = ResourceBundle.getBundle(
        "com.example.i18n.Texts",
        Locale.forLanguageTag("vi-VN"));
```

evaluates candidate locales (e.g., `vi_VN`, `vi`, and root) per `ResourceBundle`'s lookup algorithm. If `Texts_vi_VN.properties` is absent while `Texts_vi.properties` exists, the `vi` language bundle is selected.

You must test **two separate layers**:

1. **Application bundles** (`Texts_vi.properties`): does the file exist, sit at the right path, and load?
2. **JDK locale data** (`jdk.localedata`): is sufficient data present for Java APIs like `NumberFormat`, `DateTimeFormatter`, and `Collator`?

For example, without `jdk.localedata`, some runtime images can still load **application-translated strings** from `Texts_vi.properties`, since `PropertyResourceBundle` belongs to `java.base`. However, **JDK localization formatting rules** may fall back to available default data; never conclude "full Vietnamese support" merely because `getString("greeting")` returned the expected string.

**Conclusion:** verifying resource bundles and verifying runtime locale data are **two distinct checks**, both essential during packaging.

## 3. Sample Project Structure

This project has no third-party libraries; `ResourceAudit` lives in package `com.example.app` and resources live in namespace `com.example.i18n`:

```text
locale-packaging-demo/
├── src/
│   └── main/
│       ├── java/
│       │   └── com/
│       │       └── example/
│       │           └── app/
│       │               └── ResourceAudit.java
│       └── resources/
│           └── com/
│               └── example/
│                   └── i18n/
│                       ├── Texts.properties
│                       ├── Texts_en.properties
│                       └── Texts_vi.properties
└── build/                      # generated after running build commands
    ├── classes/
    ├── dist/
    ├── runtime/
    └── package/
```

The `build` directory is **not source data**; it is generated by `javac`, `jar`, `jlink`, and `jpackage` in the commands below. Never include `build` in the resource bundle base name.

The main class name is `com.example.app.ResourceAudit`. The base name is always `com.example.i18n.Texts`; Java does not require resources to share the main class's package, as long as they sit at the right path on the classpath/runtime.

### Rules for Mapping Logical Names to Paths

| Element | Value |
| --- | --- |
| Base name | `com.example.i18n.Texts` |
| Root filename | `Texts.properties` |
| Locale `en` | `Texts_en.properties` |
| Locale `vi-VN` when only `vi` exists | `Texts_vi.properties` |
| Required JAR entry | `com/example/i18n/Texts_vi.properties` |
| Source directory | `src/main/resources/com/example/i18n/` |
| Resource access via ClassLoader | `getResource("com/example/i18n/Texts_vi.properties")` |

When calling `ClassLoader.getResource`, do **not** prepend a leading `/`. By contrast, `SomeClass.class.getResource("/com/example/i18n/Texts_vi.properties")` uses a leading `/` to search from the classpath root. This small difference frequently trips up resource-audit checks.

## 4. Creating the Three UTF-8 Message Files

Save the following `.properties` files as **UTF-8** in the exact locations listed.

### 4.1. src/main/resources/com/example/i18n/Texts.properties

```properties
greeting=Hello, {0}!
count=Messages: {0,number,integer}
only.root=ROOT_OK
```

The root file serves as fallback if a key is missing in a specific translation. `only.root` is intentionally defined **only in the root** to demonstrate key inheritance.

### 4.2. src/main/resources/com/example/i18n/Texts_en.properties

```properties
greeting=Hello, {0}!
count=Messages: {0,number,integer}
```

### 4.3. src/main/resources/com/example/i18n/Texts_vi.properties

```properties
greeting=Xin chào, {0}!
count=Tin nhắn: {0,number,integer}
```

Each value is a **complete message sentence**, not fragments like `prefix`, `noun`, and `suffix`. With `{0}`, Java passes one argument and the translation decides where it appears. `{0,number,integer}` instructs `MessageFormat` to format the integer according to the `Locale`.

Starting in Java 9, `PropertyResourceBundle` reads UTF-8 by default with an ISO-8859-1 compatibility fallback for invalid UTF-8 byte sequences under JEP 226, unless configured otherwise. Do not confuse this with `Properties.load(InputStream)`, which follows its own ISO-8859-1 rules. To test source files cleanly, keep all files consistently UTF-8 and consider `java.util.PropertyResourceBundle.encoding=UTF-8` in environments requiring strict reading.

### Why Is There No Texts_vi_VN.properties?

The goal is to illustrate **fallback from region locale `vi-VN` to language bundle `vi`**. The program still requests `vi-VN`, while `bundle.getLocale().toLanguageTag()` is expected to return `vi`. This is normal behavior: the **requested locale** and the **resolved bundle's locale** do not always match.

## 5. Complete Java 17+ Program: ResourceAudit.java

Create **src/main/java/com/example/app/ResourceAudit.java**:

```java
package com.example.app;

import java.net.URL;
import java.text.MessageFormat;
import java.util.Locale;
import java.util.ResourceBundle;

public final class ResourceAudit {
    private static final String BASE =
            "com.example.i18n.Texts";

    public static void main(String[] args) {
        String code = args.length == 0 ? "en" : args[0];

        Locale locale;
        switch (code.toLowerCase(Locale.ROOT)) {
            case "en" -> locale = Locale.ENGLISH;
            case "vi" -> locale =
                    Locale.forLanguageTag("vi-VN");
            default -> {
                System.err.println("Use en or vi");
                System.exit(2);
                return;
            }
        }

        ResourceBundle bundle =
                ResourceBundle.getBundle(BASE, locale);

        ClassLoader loader =
                ResourceAudit.class.getClassLoader();
        String rootPath =
                "com/example/i18n/Texts.properties";
        String localizedPath = code.equalsIgnoreCase("vi")
                ? "com/example/i18n/Texts_vi.properties"
                : "com/example/i18n/Texts_en.properties";

        URL rootUrl = loader.getResource(rootPath);
        URL localizedUrl = loader.getResource(localizedPath);

        System.out.println("requested=" +
                locale.toLanguageTag());
        System.out.println("bundle-locale=" +
                bundle.getLocale().toLanguageTag());
        System.out.println("root-resource=" +
                (rootUrl != null));
        System.out.println("localized-resource=" +
                (localizedUrl != null));

        MessageFormat greeting = new MessageFormat(
                bundle.getString("greeting"), locale);
        MessageFormat count = new MessageFormat(
                bundle.getString("count"), locale);

        System.out.println("greeting=" +
                greeting.format(new Object[]{"Lan"}));
        System.out.println("count=" +
                count.format(new Object[]{1234}));
        System.out.println("fallback=" +
                bundle.getString("only.root"));
    }
}
```

**Code walkthrough:**

1. The program accepts `en` or `vi` as an argument; no JVM-wide `Locale.setDefault(...)` is modified.
2. `Locale.ENGLISH` requests English translations; `Locale.forLanguageTag("vi-VN")` requests Vietnamese in Vietnam.
3. `ResourceBundle.getBundle(BASE, locale)` locates the bundle on the classpath (since the example JAR has no `module-info.java`).
4. `getLocale()` reports the resolved bundle's locale; it can be `vi` even when `vi-VN` was requested.
5. `ClassLoader.getResource(...)` verifies that the **specific entry is present** at the exact path. This is not a replacement for `getBundle` across an application—just a diagnostic probe for this exercise.
6. `MessageFormat` is instantiated with the user's locale rather than the machine's default locale; thus `1234` formats with the region's thousands separator.
7. `only.root` resolves through the parent chain, proving the root resource is active.
8. Exit code `2` signals an unsupported language argument, helping CI scripts detect errors.

**Limits of the probe:** `ClassLoader.getResource(...) != null` proves only that the classloader sees a file at that path—**not that its contents are valid, all keys exist, or translations passed QA**. Always test `getString` and actual formatting outputs as well.

### Output with Complete Resources and Locale Data

Running with `en`:

```text
requested=en
bundle-locale=en
root-resource=true
localized-resource=true
greeting=Hello, Lan!
count=Messages: 1,234
fallback=ROOT_OK
```

Running with `vi` on a JDK with full `vi-VN` locale data:

```text
requested=vi-VN
bundle-locale=vi
root-resource=true
localized-resource=true
greeting=Xin chào, Lan!
count=Tin nhắn: 1.234
fallback=ROOT_OK
```

These example outputs reflect a modern JDK's number-formatting rules with matching locale data (`vi-VN` typically uses a dot as thousands separator). **Always verify on the actual released JDK/runtime image**, since locale data and providers can vary. Having the right bundle file does not guarantee numbers format like the snapshot above if you strip out `jdk.localedata`.

## 6. Compiling and Packaging the JAR with JDK 17+

Open a terminal at the **root of `locale-packaging-demo`**.

### Step 1 — Compile

```bash
javac -encoding UTF-8 -d build/classes src/main/java/com/example/app/ResourceAudit.java
```

This creates `build/classes/com/example/app/ResourceAudit.class`. `-encoding UTF-8` specifies the charset of the Java source file and is unrelated to how `PropertyResourceBundle` reads packaged properties later.

### Step 2 — Create the Distribution Directory

Linux/macOS:

```bash
mkdir -p build/dist
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path build/dist
```

### Step 3 — Build the Executable JAR

```bash
jar --create --file build/dist/localization-demo.jar \
    --main-class com.example.app.ResourceAudit \
    -C build/classes . -C src/main/resources .
```

In Bash, trailing `\` continues lines. On Windows PowerShell, run as a **single line**:

```powershell
jar --create --file build/dist/localization-demo.jar --main-class com.example.app.ResourceAudit -C build/classes . -C src/main/resources .
```

Key flags:

- `--main-class` writes `Main-Class` into the manifest so `java -jar` knows the entry point.
- `-C build/classes .` places the **contents of `build/classes`** at the JAR root.
- `-C src/main/resources .` places the **contents of the resource root** at the JAR root.
- `-C` is not part of the bundle name; it preserves entries such as `com/example/i18n/Texts_vi.properties`.

Never pass `jar ... src/main/resources` in a way that embeds the source prefix into the JAR; if the entry becomes `src/main/resources/com/example/i18n/Texts_vi.properties`, base name `com.example.i18n.Texts` will **not** find it from the normal classpath root.

### Step 4 — Inspect JAR Contents

```bash
jar tf build/dist/localization-demo.jar
```

The output must contain at least (this is an excerpt):

```text
META-INF/MANIFEST.MF
com/example/app/ResourceAudit.class
com/example/i18n/Texts.properties
com/example/i18n/Texts_en.properties
com/example/i18n/Texts_vi.properties
```

Inspect the manifest if needed:

```bash
unzip -p build/dist/localization-demo.jar META-INF/MANIFEST.MF
```

`unzip` depends on your environment and is not bundled with every JDK. If unavailable, use your OS's ZIP/JAR viewer or `jar --extract` inside a safe temporary directory. The manifest must list `Main-Class: com.example.app.ResourceAudit` when built with the command above.

### Step 5 — Run with a Standard JDK

```bash
java -jar build/dist/localization-demo.jar en
java -jar build/dist/localization-demo.jar vi
```

The expected output matches the two blocks in Section 5. This is a **real smoke test on the packaged JAR**. Succeeding with `java -cp build/classes:src/main/resources ...` proves only that the source resource directory works on the classpath—**not that the JAR is packaged properly**.

### Step 6 — Run from an Isolated Directory

Copy `localization-demo.jar` to a directory without `src/main/resources` and run `java -jar ...`. If resources are packaged properly, the program still locates both translations. This test catches code that accidentally reads resources via `new File("src/main/resources/...")`.

## 7. A JAR and a Runtime Image Are Not the Same Thing

An application JAR contains bytecode and properties, yet running:

```bash
java -jar build/dist/localization-demo.jar vi
```

still requires a compatible Java runtime installed on the OS. You can distribute the JAR alongside JRE/JDK installation instructions, or create a **custom runtime image** so you do not depend on preinstalled Java.

`jlink` is the standard JDK 9+ tool that links Java modules and their module dependencies into a self-contained runtime directory. It uses the JDK's `jmods` and can produce an image smaller than a full JDK.

**Distinction:**

```text
build/dist/localization-demo.jar
    └── app .class + Texts*.properties

build/runtime/
    ├── bin/java[.exe]
    ├── conf/...
    ├── lib/modules
    └── ...
        (Java runtime modules; does not automatically contain the app JAR)
```

When distributing manually, users need **both**: `build/runtime` and `localization-demo.jar`. You cannot ship only the runtime directory and expect `com.example.app.ResourceAudit` to be inside it.

## 8. Building a Custom Runtime Image with jlink

### 8.1. Modules Required by the Sample App

`ResourceAudit` uses APIs from `java.base`:

- `java.util.Locale`, `ResourceBundle`;
- `java.text.MessageFormat`;
- `java.lang`;
- `java.net.URL`.

Therefore, **`java.base` is the mandatory foundation module**. However, to format numbers and dates across multiple locales in the JDK, you generally also need **`jdk.localedata`**, which supplies additional locale data beyond US English/ROOT in many JDK distributions.

In Oracle JDK 21, basic `en-US`/root data lives in `java.base`, while additional locale data resides in `jdk.localedata`. A runtime containing only `java.base` can still construct `Locale.forLanguageTag("vi-VN")` and load `Texts_vi.properties`, yet **`NumberFormat`** may fall back due to missing `vi-VN` formatting data.

### 8.2. jlink Command with Locale Data

With JDK 17+ providing `jlink`:

```bash
jlink --add-modules java.base,jdk.localedata \
      --include-locales=en,vi \
      --strip-debug --no-header-files --no-man-pages \
      --output build/runtime
```

Windows PowerShell (single line):

```powershell
jlink --add-modules java.base,jdk.localedata --include-locales=en,vi --strip-debug --no-header-files --no-man-pages --output build/runtime
```

**Run only when `build/runtime` does not yet exist** or has been intentionally cleaned for a fresh build: `jlink` does not arbitrarily overwrite an existing image. Always double-check the output path before deleting or replacing anything.

Option breakdown:

| Option | Effect |
| --- | --- |
| `--add-modules java.base,jdk.localedata` | Includes required modules in the image; `jdk.localedata` supplies extended locale data |
| `--include-locales=en,vi` | Retains locale data matching the specified BCP 47 filter; requires `jdk.localedata` |
| `--strip-debug` | Strips debug attributes from the image |
| `--no-header-files` | Excludes C header files for native development |
| `--no-man-pages` | Excludes man pages |
| `--output build/runtime` | Destination directory for the runtime image |

`--include-locales` is a `jlink` plugin. Per official documentation, using this option requires `jdk.localedata` in the module set. The `en,vi` value is a list of language tags, not filenames like `Messages_en.properties` or `Messages_vi.properties`.

**Warning about the locale filter:** the plugin matches using BCP 47/RFC 4647 filtering. Run real tests with `vi-VN` and `en` on the generated image rather than assuming "Vietnamese is included" solely because the flag says `vi`. If the app adds regions like `fr-FR` or `ja-JP`, update the image and test numbers, dates, currency, and collation for those locales as well.

### 8.3. Inspecting the Generated Image

Linux/macOS:

```bash
build/runtime/bin/java --version
build/runtime/bin/java --list-modules
```

Windows PowerShell:

```powershell
.\build\runtime\bin\java.exe --version
.\build\runtime\bin\java.exe --list-modules
```

`--list-modules` must include at least:

```text
java.base@<JDK_VERSION>
jdk.localedata@<JDK_VERSION>
```

The two lines above are an **output pattern**, where `<JDK_VERSION>` is an explanatory placeholder rather than literal fixed text. The actual version comes from the JDK used to run `jlink`. Additional modules may appear due to dependencies or configuration.

Run the application using the **Java binary inside the runtime image itself**, not `java` on your `PATH`:

Linux/macOS:

```bash
build/runtime/bin/java -jar build/dist/localization-demo.jar vi
build/runtime/bin/java -jar build/dist/localization-demo.jar en
```

Windows PowerShell:

```powershell
.\build\runtime\bin\java.exe -jar build/dist/localization-demo.jar vi
.\build\runtime\bin\java.exe -jar build/dist/localization-demo.jar en
```

When all resource files are in the JAR and `jdk.localedata` is properly retained, `root-resource`, `localized-resource`, `greeting`, `count`, and `fallback` should match execution on the full JDK.

**Never run bare `java -jar ...` without the `build/runtime/bin/java` path to test your image**: that can accidentally invoke the system JDK, invalidating the custom-runtime test.

## 9. Experiment Comparing Minimal vs. Full Locale Data Runtimes

This is a critical check because you can easily hit a state where **translations look right while numbers/dates format in the wrong locale**.

Build a minimal image containing only `java.base` in a **separate directory**:

```bash
jlink --add-modules java.base --output build/runtime-base
```

Then run the exact same JAR:

```bash
build/runtime-base/bin/java -jar build/dist/localization-demo.jar vi
```

On Windows, use `.\build\runtime-base\bin\java.exe` instead of `build/runtime-base/bin/java`.

Observe three output groups:

1. `localized-resource=true` still passes because `Texts_vi.properties` lives inside the **app JAR**, not inside `jdk.localedata`.
2. `greeting=Xin chào, Lan!` still passes because the translated string comes from the app bundle.
3. `count=Tin nhắn: ...` may format using the runtime's **fallback** locale data. On many `java.base`-only JDK builds, `vi-VN` thousands-grouping rules are unavailable, so output can differ from the full-locale image.

**Never hardcode a forced failure assertion like "every `java.base`-only image prints `1,234`".** JDKs and providers can vary across versions or builds. This exercise asks you to compare **the actual output** of both images in the same environment, recording `--list-modules` and observed values.

### Why Isn't Testing ResourceBundle.getString Enough?

`getString` tests only application-packaged translation strings. Other localization features depend on JDK data:

- `NumberFormat.getNumberInstance(locale)`;
- `DateTimeFormatter.ofLocalizedDate(...).withLocale(locale)`;
- `Collator.getInstance(locale)`, and `BreakIterator` where provider data applies;
- month/weekday names, date/time formats, and currency formatting per `Locale`.

These APIs can depend on multiple modules and providers. **`jdeps` analyzes static module dependencies**, and typically cannot infer runtime data needs selected dynamically via `Locale` or service providers. Therefore, testing directly on the trimmed runtime image is mandatory.

## 10. jdeps: Checking Module Dependencies Without Forgetting Locale Data

`jdeps` analyzes class/JAR dependencies. On the sample JAR:

```bash
jdeps --print-module-deps build/dist/localization-demo.jar
```

For the simple Java SE code in this lesson, the output is typically:

```text
java.base
```

This is accurate: every statically referenced class resides in `java.base`. However, **it does not mean the application needs only `java.base` data to format every locale**. `jdk.localedata` primarily supplies locale data accessed dynamically via locale providers rather than appearing as direct static class references in `ResourceAudit` bytecode.

Therefore, when selecting modules for `jlink`:

1. Use `jdeps` as a starting point to discover Java modules referenced by code.
2. Add modules required for locale data, providers, and runtime features proven necessary by tests.
3. Re-run `--list-modules` and real smoke tests.
4. Never blindly run `jlink --add-modules $(jdeps ...)` assuming all localization features will automatically work.
5. For external libraries, inspect non-modular dependencies, reflective access, JNI, `ServiceLoader`, and required modules before trimming an image.

Complex applications may also need `java.sql`, `java.desktop`, `java.logging`, or other modules. Never copy a bare `java.base,jdk.localedata` list from a demo into production without analyzing real dependencies.

## 11. jpackage: Combining the JAR and Runtime into an Application Image

`jlink` creates a **runtime image**, whereas `jpackage` can create an **app image** bundling a native launcher, application, and runtime.

Given the existing artifacts:

```text
build/dist/localization-demo.jar  (app JAR)
build/runtime/                    (custom runtime)
```

You can invoke `jpackage` from JDK 17+:

```bash
jpackage --type app-image \
         --name LocaleDemo \
         --input build/dist \
         --main-jar localization-demo.jar \
         --main-class com.example.app.ResourceAudit \
         --runtime-image build/runtime \
         --dest build/package
```

On Windows PowerShell, run on a single line:

```powershell
jpackage --type app-image --name LocaleDemo --input build/dist --main-jar localization-demo.jar --main-class com.example.app.ResourceAudit --runtime-image build/runtime --dest build/package --win-console
```

`--win-console` is a **Windows-only** option giving the launcher a console window suited for CLI apps. Omit it on Linux/macOS.

| Parameter | Effect |
| --- | --- |
| `--type app-image` | Creates an application image rather than a `.msi`/`.deb` installer |
| `--name LocaleDemo` | App and launcher name |
| `--input build/dist` | Directory containing the application JAR |
| `--main-jar localization-demo.jar` | JAR filename **relative to the input directory** |
| `--main-class com.example.app.ResourceAudit` | Main class of the application |
| `--runtime-image build/runtime` | Copies the prebuilt custom runtime |
| `--dest build/package` | Output destination for the app image |
| `--win-console` | Attaches a console launcher on Windows |

**Note:** `jpackage` can invoke `jlink` internally if `--runtime-image` is omitted. Here we supply the prebuilt image explicitly to control `jdk.localedata` and included locales. Never pass a JAR missing `Texts_vi.properties` expecting `jpackage` to locate source resources and fix your packaging bug.

### How to Run the App Image

After creation, the app image typically resides at `build/package/LocaleDemo`, though launcher layout varies by OS.

Linux (example):

```bash
build/package/LocaleDemo/bin/LocaleDemo vi
```

Windows PowerShell (example):

```powershell
.\build\package\LocaleDemo\LocaleDemo.exe vi
```

macOS creates a `LocaleDemo.app` bundle with the launcher inside `Contents/MacOS`; exact paths depend on packaging options. Always inspect the **actual layout produced by the tool** rather than hardcoding one launcher path across all platforms.

`jpackage` builds images/packages **for the host platform of the build machine**; it does not produce a single cross-platform executable running identically on Windows, Linux, and macOS. Maintain separate build pipelines per OS and CPU architecture.

### Verifying Translation Data Inside the App Image

An app image normally stores the JAR in an application directory alongside a private runtime. Verify that:

1. The packaged JAR is **the exact verified artifact**.
2. The JAR still contains `com/example/i18n/Texts*.properties` entries.
3. The copied runtime image still includes `java.base` and `jdk.localedata`.
4. The launcher runs cleanly with both `en` and `vi`.
5. `localized-resource=true`, messages, and accented characters render accurately.
6. The program runs on a test machine **with no system JDK/JRE installed** (matching OS/architecture).

Never treat successful generation of the `LocaleDemo` directory as proof that i18n works. The final test must invoke the actual launcher and inspect **output contents**.

## 12. Two Verification Layers for CI Pipelines

Deployment checks should be split into two layers.

### Layer A — Artifact Integrity: Are Translation Files Packaged Properly?

For a traditional JAR, verify invariants:

```text
com/example/app/ResourceAudit.class
com/example/i18n/Texts.properties
com/example/i18n/Texts_en.properties
com/example/i18n/Texts_vi.properties
```

Confirm entry paths are **exact**, with no leading `src/main/resources` or `build` directory. `jar tf` is the standard tool for listing entries.

If an app has multiple JARs or dependencies, resources might live inside a separate JAR; inspect the **actual runtime classpath**. In Spring Boot executable JARs, resources typically reside under `BOOT-INF/classes/com/example/i18n/...` and are resolved by Spring Boot's custom loader—do not blindly apply flat traditional-JAR root rules to every archive layout.

### Layer B — Runtime Behavior: Is the App Truly Localized?

Checks executed on **the actual distributed runtime**:

| Check | Input | What to Verify |
| --- | --- | --- |
| Main class | `java -jar ... en` | Launches cleanly |
| English bundle | `en` | `bundle-locale=en`, `greeting=Hello, Lan!` |
| Vietnamese bundle | `vi` | `bundle-locale=vi`, `greeting=Xin chào, Lan!` |
| Root fallback | `en` or `vi` | `fallback=ROOT_OK` |
| Classloader resource path | `en` or `vi` | `root-resource=true` and `localized-resource=true` |
| Number formatting | `en` | `count=Messages: 1,234` per expected locale data |
| Number formatting | `vi` | `count=Tin nhắn: 1.234` per target locale data |
| Unsupported locale | `fr` | Exit code `2`; not silently treated as supported via root fallback |
| JAR portability | Move JAR outside source tree | App still resolves bundles |
| Custom runtime | `runtime/bin/java -jar ... vi` | Does not accidentally invoke system Java |
| Module inventory | `runtime/bin/java --list-modules` | Required modules are genuinely present |
| App image | Launcher `LocaleDemo vi` | Runs without system JDK; messages match |
| Encoding | UTF-8 files and stdout | No mojibake or Unicode corruption |

CI can run a Bash/PowerShell script capturing stdout, asserting stable lines, checking exit codes, and verifying JAR entries. Avoid asserting identical number/date separators across arbitrary providers/JDKs unless runtime data or formatting policies are pinned.

### Do Not Validate by Filename Alone

Merely seeing `Texts_vi.properties` inside the JAR does not prove:

- The file **loads via the base name** properly.
- The `count` key exists and parses cleanly in `MessageFormat`.
- UTF-8 text is decoded properly.
- The runtime includes `jdk.localedata`.
- Vietnamese characters render properly in the terminal.
- Missing keys were caught before release.
- Translations are grammatically, contextually, and layout-accurate.

That is why this exercise deliberately combines **resource probe + `getBundle` + `getString` + `MessageFormat` + locale formatting** in a single program.

## 13. Distinguishing Bundle Fallback from Locale Data Fallback

These two kinds of fallback are easy to confuse.

### 13.1. ResourceBundle Fallback

If the application requests `vi-VN` and only has:

```text
Texts_vi.properties
Texts.properties
```

`ResourceBundle` selects `Texts_vi.properties`. If `only.root` is missing in `vi`, it resolves from the parent root bundle.

This happens strictly across **application-supplied resources**; it does not require the JDK to know Vietnamese vocabulary.

### 13.2. JDK Locale Provider Fallback

`NumberFormat` and `DateTimeFormatter` rely on Java locale providers' data. In a runtime image missing `jdk.localedata`, formatting data for some locales may be absent even though `Locale.forLanguageTag("vi-VN")` constructs without error.

**Never infer from `bundle.getLocale() == vi` that `NumberFormat` has complete `vi-VN` data.** Nor should `Locale.getAvailableLocales()` alone be treated as proof of complete data: test the actual APIs your application calls.

### Example Module Verification

```bash
build/runtime/bin/java --list-modules
```

Should include:

```text
java.base@...
jdk.localedata@...
```

Yet `--list-modules` proves only that the module is present—**it does not verify that the `--include-locales` filter kept the right languages/regions**. You still must run `ResourceAudit vi`, print formatted numbers, and test every product-supported locale.

## 14. Encoding in JARs and Runtime Images

`.properties` files do not become "normalized text" simply by being archived into a JAR. The `jar` tool packages file bytes as-is; it neither translates Vietnamese nor repairs broken charsets.

On Java 17+:

- Property resource bundles prefer UTF-8 by default per JEP 226 (Java 9+).
- When a file contains invalid UTF-8 byte sequences, an ISO-8859-1 fallback mechanism applies (depending on configuration).
- `java.util.PropertyResourceBundle.encoding` can control how `PropertyResourceBundle` decodes files.
- `System.out`/terminals can use different encodings and must be checked independently.

**A common source of confusion:**

```text
JAR entry has correct path
    ↓
ResourceBundle loads successfully
    ↓
Java String has valid Unicode
    ↓
System.out encodes to console charset
    ↓
Terminal decodes incorrectly or lacks font
    ↓
User sees garbled characters
```

In that situation, fixing the classpath will never fix the display bug. Inspect raw bytes or Unicode code points of the string before printing to the terminal. A quick diagnostic snippet prints code points:

```java
String sample = bundle.getString("greeting");
sample.codePoints().forEach(cp ->
        System.out.printf("U+%04X%n", cp));
```

This is just a **snippet** assuming `bundle` exists. If code points are correct while the terminal shows wrong glyphs, the issue lies in output encoding or font support. If code points are already corrupted, inspect source file bytes and build resource-filtering/charset steps.

Note that JEP 400 (JDK 18: UTF-8 by Default) adjusts the default charset of many APIs, yet **does not mean** `Properties.load(InputStream)`, `PropertyResourceBundle`, console I/O, and every protocol all follow one identical rule. Do not conflate JEP 226 and JEP 400 into a single change.

## 15. Common Errors and Fixes

| Error | Symptom | Fix |
| --- | --- | --- |
| `Texts_vi.properties` placed at wrong path in JAR | `MissingResourceException` or root fallback | Place entry under `com/example/i18n/` from JAR root |
| Files placed in `src/main/java` | CLI build omits resources | Move to `src/main/resources` |
| Passing `com/example/i18n/Texts.properties` to `getBundle` | Cannot locate bundle family | Pass base name `com.example.i18n.Texts` |
| Running `java -jar` without `Main-Class` in JAR | No main manifest attribute | Build JAR with `--main-class` |
| Running classes from directory without resources on classpath | Bundle not found | Add `src/main/resources` to classpath or package JAR |
| Using `new File("src/main/resources/...")` | Works in IDE, fails in deployment | Use `ResourceBundle`/`getResourceAsStream` |
| Running `jlink` and shipping only the runtime image | No application to run | Ship app JAR too or use `jpackage` |
| Using `jlink --add-modules java.base` for every app | Missing required modules | Check `jdeps` + test runtime features |
| Omitting `jdk.localedata` | Bundle loads but locale formatting falls back | Add module and test locale data |
| Including `jdk.localedata` with overly narrow `--include-locales` | Some locales dropped | Update filter and test in real runtime |
| Checking only `--list-modules` | Unsure whether JAR holds resources | Add `jar tf` and `getBundle/getString` tests |
| Checking only `jar tf` | Unsure whether runtime has locale data | Run JAR on the actual runtime image |
| `java` command invokes system JDK | Runtime image test is invalid | Invoke `build/runtime/bin/java` explicitly |
| `jpackage` creates a windowless launcher on Windows | CLI shows no output | Add `--win-console` on Windows |
| App image builds cleanly yet localization is wrong | Translations or locale data still broken | Execute launcher and verify output content |
| Editing source resources after build | Artifact still holds old copy | Rebuild JAR and app image |
| Garbled Vietnamese diacritics | Encoding or terminal font issue | Verify UTF-8 at every boundary |
| Missing key silently runs | Root fallback masks missing translation | Check per-locale translation coverage |
| Duplicate resource paths across dependencies | Classloader picks another dependency's file | Use unique namespaces; inspect runtime classpath |
| JAR works on desktop Java but fails on trimmed runtime | Missing `java.desktop` or other modules | Audit real dependencies and test `jlink` |
| Stale runtime after JDK security updates | Vulnerabilities or outdated locale data | Rebuild and redistribute the runtime image |

## 16. Advanced Verification: Checking Translation Completeness

`ResourceBundle.getString` can retrieve keys from parent bundles. While helpful for fallback, that can leave Vietnamese **incomplete** while the pipeline reports zero errors.

To audit **packaging quality** beyond minimal smoke tests:

1. Enumerate all required keys from the root catalog.
2. Verify every key is defined directly in each target translation file, not merely inherited from parent.
3. Verify `MessageFormat` patterns parse cleanly in every locale.
4. Verify placeholders across translations keep matching roles and types, allowing **reordering**.
5. Test edge-case arguments: `0`, `1`, `1234`, names containing Unicode, single quotes.
6. Verify plurals per linguistic rules; classic `MessageFormat` is not a full CLDR plural engine.
7. Check punctuation, translation length, and rendering in the target terminal/UI.
8. Run tests both from the source layout and from the **packaged JAR/app image**, comparing behavior.

Never treat `ResourceBundle.containsKey(key)` as proof that the child translation defines the key: `containsKey` sees inherited parent keys too. To audit individual files, inspect source/archived catalog entries directly.

### Testing Actual Supported Languages

An app might target `en-US`, `vi-VN`, and `ja-JP` while shipping bundles only for `en` and `vi`. Because `ResourceBundle` falls back, requesting `ja-JP` can silently render English without throwing. Supported languages must be **governed by an explicit list**, not inferred from whether `getBundle` returns a bundle.

Add tests for "unsupported language" requests to ensure the app displays a clear error or follows product fallback policy, rather than silently claiming it switched languages.

## 17. Distributing Runtime Images and Security Maintenance

A custom runtime image is a **snapshot of a specific JDK captured at build time**. It **does not auto-update** when the OS installs a newer Java release. Whenever JDK security patches or locale/timezone updates arrive, you must:

1. Update the JDK used to build the image.
2. Re-run `jlink` using the updated JDK.
3. Re-test the JAR against the new runtime.
4. Rebuild the `jpackage` `app-image` or other distribution package.
5. Redistribute the application artifact + runtime and record the version.

Never copy `lib/modules` from an older image and mix it with `bin/java` from another build; a runtime image is an integrated unit tied to a specific JDK build's module graph and native libraries.

### Portability

- A Java 17 JAR (using standard Java SE APIs) generally runs on compatible Java runtimes >= 17.
- A custom runtime image **depends on the OS and CPU architecture** on which it was built and its JDK native libraries; it is not "write once, run everywhere" like a bytecode JAR.
- `jpackage` produces OS-specific app images/installers, requiring separate build pipelines for Linux, Windows, and macOS when targeting multiple platforms.
- Do not bundle JDK development tools like `javac` or `jar` into production images expecting user machines to compile: minimal images need only what is required to run the app.

Accordingly, a pipeline can publish **one platform-neutral JAR** alongside **per-OS runtime/app images**, each verified for resource bundles and locale data.

## 18. Self-Practice Exercises

**Exercise 1.** Base name is `com.acme.i18n.Labels`, locale `vi-VN`. If only a generic Vietnamese file is provided, what is the exact JAR entry path?

**Answer:** `com/acme/i18n/Labels_vi.properties`. You can optionally add `Labels_vi_VN.properties` for Vietnam-specific overrides and `Labels.properties` as root fallback.

**Exercise 2.** `jar tf` shows `src/main/resources/com/example/i18n/Texts_vi.properties`, yet Java cannot find it. Why?

**Answer:** The file sits under the source prefix rather than the classpath root. Java looks for `com/example/i18n/Texts_vi.properties` matching the app's base name.

**Exercise 3.** A runtime image includes `java.base` without `jdk.localedata`. The app still loads `Texts_vi.properties`; can you conclude `vi-VN` numbers and dates format accurately?

**Answer:** No. The bundle supplies app-translated strings; JDK formatter locale data is a separate layer that must be tested via `NumberFormat`/`DateTimeFormatter` on that runtime image.

**Exercise 4.** Does `jlink --add-modules java.base,jdk.localedata --include-locales=en,vi` automatically copy `localization-demo.jar` into the image?

**Answer:** No. `jlink` builds a runtime module image. The app JAR must be distributed separately or bundled with `jpackage`.

**Exercise 5.** `jdeps --print-module-deps` outputs only `java.base`. Why should `jdk.localedata` still be added?

**Answer:** `jdeps` primarily detects static module dependencies from bytecode; extended locale data is resolved dynamically via locale providers and does not appear as direct class dependencies.

**Exercise 6.** `ResourceBundle.getBundle` returns bundle `vi` when `vi-VN` was requested. Is that a bug?

**Answer:** No, if `Texts_vi.properties` exists without a region-specific override. That is normal locale fallback. Check `getLocale()` to see which candidate was selected.

**Exercise 7.** Why must you still verify `jar tf` when using `jpackage --type app-image`?

**Answer:** An app image simply copies/packages the supplied artifacts. If the JAR is missing resources, `jpackage` will not rebuild translation files from source.

**Exercise 8.** Can a runtime image built on Windows be copied directly to Linux?

**Answer:** No. A runtime image contains OS- and CPU-specific native binaries and libraries; build separate images per target platform.

**Exercise 9.** How do you verify you are running the Java binary inside your custom image?

**Answer:** Invoke `build/runtime/bin/java --version`, `--list-modules`, and `build/runtime/bin/java -jar ...` using the explicit path instead of bare `java` on `PATH`.

**Exercise 10.** If the screen prints `Xin chÃ o`, does that necessarily mean the `ResourceBundle` path is wrong?

**Answer:** No. If `getString` and the classloader probe succeed, the bug may lie in source file bytes, build resource filtering, stdout encoding, or terminal decoding. Inspect each layer.

## 19. Pre-Release Checklist

| Item | Acceptance Criteria |
| --- | --- |
| JAR build | Succeeds with valid `Main-Class` |
| JAR entries | All `Texts*.properties` present directly under `com/example/i18n/` |
| UTF-8 | Source files and stdout show no mojibake |
| English locale | Messages and numbers match approved conventions |
| Vietnamese locale | Vietnamese messages and numbers/dates match target locale data |
| Root fallback | `only.root` key resolves properly |
| Missing keys | Translation coverage verified directly, not masked by fallback |
| Custom runtime | `--list-modules` shows required Java modules |
| Include locales | Locale filter covers needed languages/regions and passes smoke tests |
| Runtime selection | Explicitly executes `runtime/bin/java`, not system Java |
| App packaging | `jpackage` bundles JAR + runtime + launcher |
| CI | Tests `en`/`vi`, unsupported locales, and execution outside source tree |
| Multiplatform | Built and tested separately per OS/architecture |
| Security | JDK update and runtime-image rebuild process documented |

## 20. Summary

1. **JARs** must include both bytecode and translation files at the exact **classpath path**. For base name `com.example.i18n.Texts`, `com/example/i18n/Texts_vi.properties` is required for Vietnamese translations.
2. **`jlink`** creates a **custom Java runtime image**. It does not automatically bundle the app JAR, and `--include-locales` requires `jdk.localedata`.
3. **`jpackage`** combines **application + runtime + launcher** into an app image; contents still require verification.
4. **Bundle resources** differ from **JDK locale data**. When trimming runtime size, verify both translated strings and number/date formatting.
5. **`jar tf`, `jdeps`, `--list-modules`, and smoke tests against the final runtime/launcher** catch different classes of bugs; no single check replaces the others.
6. Tests must run **outside the IDE and source tree** on real artifacts and target operating systems, covering Unicode, fallback, key coverage, and charsets.
7. Whenever updating the JDK, **rebuild and redistribute the runtime image**; custom images do not inherit patches from system Java installations.

**Official References:**

- [Java SE 21 — ResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ResourceBundle.html)
- [Java SE 21 — PropertyResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/PropertyResourceBundle.html)
- [Java SE 21 — jlink](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jlink.html)
- [Java SE 21 — jpackage](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jpackage.html)
- [Java SE 21 — jar](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jar.html)
- [Java SE 21 — jdeps](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeps.html)
- [Oracle JDK 21 — Supported Locales and jdk.localedata](https://www.oracle.com/java/technologies/javase/jdk21-supported-locales.html)
- [OpenJDK JEP 226 — UTF-8 Property Resource Bundles](https://openjdk.org/jeps/226)
