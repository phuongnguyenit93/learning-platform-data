# Adding Provider Selection by Supported Capabilities and User Configuration

## 1. Exercise Objectives

In a Java application with a plugin architecture, **ServiceLoader** discovers multiple implementations of the same service interface. However, discovering providers **does not mean** you can arbitrarily pick the first one: one provider might output only HTML, another might support only plain text, and another might offer color features, while users have their own requirements and preferences.

This exercise builds a **ReportProvider** SPI. The host loads providers using **ServiceLoader**, then selects one based on:

1. **Required output format** from user configuration: text, markdown, or html.
2. **Required capabilities**: for example, unicode, heading, color. A provider is eligible only if it supports **all** requested capabilities.
3. **Preferred provider**: the user can request priority for a provider with a stable ID.
4. **Strict preference**: if enabled, the host must not silently use another provider when the chosen provider is not eligible.
5. **Controlled fallback**: if strict is disabled and the preferred provider is not eligible, select another eligible provider according to a clear policy.
6. **Deterministic ordering**: when multiple eligible options remain, use descending priority and ascending ID instead of depending on service discovery order.

By the end of the exercise, a Java 17 program will run with three independent providers packaged into a JAR and configured from the command line. We will also test cases with no matching provider, preference conflicting with capabilities, duplicate IDs, and configuration errors.

**Scope:** Provider selection, not modifying the ServiceLoader implementation. In this example, providers are already trusted and reside on the classpath. Later sections explain considerations when migrating to JPMS/module path or when providers come from external sources.

## 2. Why Not Just Use findFirst()?

This is a common approach when first learning SPI:

~~~java
// Illustrative snippet: insufficient for selecting based on user requirements.
ReportProvider provider = ServiceLoader.load(ReportProvider.class)
        .findFirst()
        .orElseThrow();
~~~

**findFirst()** picks the first provider according to ServiceLoader's discovery/caching rules. This order is not a business policy: the order across modules is not necessarily deterministic; resource order on the classpath can change when repackaging or changing class loaders. Nor is the first provider guaranteed to support the format, locale, data, or capabilities the user requested.

Instead, the architecture should be:

~~~text
User config
    |
    v
Normalize + validate syntax
    |
    v
ServiceLoader<ReportProvider>
    |
    v
Discovery -> validate ID -> fetch provider capabilities
    |
    v
Hard filter: format + requiredFeatures
    |
    +-- no eligible provider -> report clear error
    |
    v
Prefer preferredId if present in eligible set
    |
    +-- not eligible and strict=true -> report error, DO NOT fallback
    |
    +-- not eligible and strict=false -> controlled fallback
    |
    v
Sort: priority descending, ID ascending
    |
    v
Selected provider -> render
~~~

**Distinguishing hard constraints from soft preferences** is the core theme. Required format and capabilities must always be checked first. A preferred provider **must never override** hard constraints; in strict mode, an ineligible or missing preferred provider is an error rather than a reason to ignore requirements.

## 3. Designing the SPI Contract and Configuration

We design **ReportProvider** as a service interface. Each implementation declares metadata and produces output:

- **id():** a stable identifier for users to reference in configuration, e.g., plain, md, html.
- **formats():** the set of supported formats: text, markdown, or html.
- **features():** declared capabilities, e.g., unicode, heading, color.
- **priority():** default priority score. A higher value is chosen first when there is no eligible preferred provider.
- **supports(request):** checks hard constraints; in this exercise, a default implementation uses formats and features.
- **render(input, request):** executes the business logic once selected.

User configuration is an immutable **RenderRequest** containing **format**, **requiredFeatures**, **preferredId**, and **strict**.

| Property | Example | Meaning |
|---|---|---|
| **format** | markdown | Required output format |
| **requiredFeatures** | unicode,heading | Provider must support both capabilities |
| **preferredId** | plain | Prefer the provider with ID plain, if eligible |
| **strict** | true or false | Whether fallback is allowed when preferred is ineligible? |

**Important convention:** Only **requiredFeatures** is a mandatory condition set. We do not use "most capabilities" to automatically infer the best provider, because a provider with more features does not necessarily satisfy preferences around latency, cost, or explainability. Selection policy is expressed transparently via preference, priority, and a tie-breaker.

## 4. Expected Behavior Specification

In this example there are three providers:

| ID | Formats | Features | Priority |
|---|---|---|---:|
| **plain** | text | unicode | 10 |
| **md** | text, markdown | unicode, heading | 30 |
| **html** | html | unicode, heading, color | 20 |

From this table it follows that:

- User requests **format=text, requires=unicode, prefer=plain, strict=true** → selects plain, even though md has higher priority.
- User requests **format=markdown, requires=heading, prefer=plain, strict=false** → plain lacks capabilities, falls back to md.
- Request **format=html, requires=color, prefer=plain, strict=false** → selects html, because plain does not support html/color.
- Request **format=text, requires=unicode**, with no preferred → both plain and md are eligible; md wins with priority 30.
- Request **format=markdown, requires=heading, prefer=plain, strict=true** → reports error, does not auto-fallback.
- Request **format=pdf** → no provider meets the criteria, reports error.

**Determinism note:** In this example, if two providers have the same priority, we compare **id()** alphabetically so the result never depends on the order returned by ServiceLoader. If duplicate IDs exist, the program **rejects them** instead of randomly picking one implementation.

## 5. Java 17 Hands-On Project Structure

Create the **provider-selection-lab** directory with the following files:

~~~text
provider-selection-lab/
├── api/
│   └── src/demo/spi/
│       ├── RenderRequest.java
│       └── ReportProvider.java
├── providers/
│   ├── src/demo/providers/
│   │   ├── PlainProvider.java
│   │   ├── MarkdownProvider.java
│   │   └── HtmlProvider.java
│   └── resources/META-INF/services/
│       └── demo.spi.ReportProvider
├── app/
│   └── src/demo/app/Main.java
└── build/             # created by compilation commands
~~~

In this structure:

- **api/** publishes the service contract and shared configuration type.
- **providers/** contains three implementations; typically they are packaged in separate JARs.
- **app/** is the host that depends only on the API and does not directly import provider classes.
- **META-INF/services/demo.spi.ReportProvider** is the provider registration file in the classpath model.

Package names and source directory paths must match. The service descriptor file has **no .java extension**, and its name is the **fully qualified binary name** of the service interface.

## 6. Writing the Two API Files

### 6.1. Immutable Configuration RenderRequest

**api/src/demo/spi/RenderRequest.java**

~~~java
package demo.spi;

import java.util.Locale;
import java.util.Objects;
import java.util.Set;

public record RenderRequest(
        String format,
        Set<String> requiredFeatures,
        String preferredId,
        boolean strict) {

    public RenderRequest {
        format = Objects.requireNonNull(format, "format")
                .trim().toLowerCase(Locale.ROOT);

        if (format.isEmpty()) {
            throw new IllegalArgumentException("empty format");
        }

        requiredFeatures = Set.copyOf(
                Objects.requireNonNull(requiredFeatures, "requiredFeatures"));

        preferredId = preferredId == null
                ? ""
                : preferredId.trim().toLowerCase(Locale.ROOT);

        if (strict && preferredId.isEmpty()) {
            throw new IllegalArgumentException(
                    "strict requires --prefer");
        }
    }
}
~~~

**Explanation:**

1. A Java **record** fits immutable configuration data well.
2. Format and preferred ID are normalized to lowercase using **Locale.ROOT**, avoiding variations across machine locales.
3. **Set.copyOf** captures an unmodifiable copy of the set after the request is created.
4. If strict=true without a preferred ID, the configuration makes no sense, so it fails immediately.
5. The example intentionally permits a new format or feature not yet declared by any provider: the selector result will be **no eligible provider**, rather than silently dropping that requirement.

In a real system, add validation for length, allowed character sets, null elements, and configuration-source quotas. Feature names must follow a consistent convention; here the CLI lowercases features before constructing the record.

### 6.2. The ReportProvider Contract

**api/src/demo/spi/ReportProvider.java**

~~~java
package demo.spi;

import java.util.Set;

public interface ReportProvider {

    String id();

    Set<String> formats();

    Set<String> features();

    int priority();

    String render(String input, RenderRequest request);

    default boolean supports(RenderRequest request) {
        return formats().contains(request.format())
                && features().containsAll(request.requiredFeatures());
    }
}
~~~

**Why use supports(request)?**

In a simple example, format + capabilities suffice to determine eligibility. But with real-world providers, support may depend on the data, model version, size limits, user permissions, or content type. In such cases, a provider can override **supports(request)** while keeping the selection contract consistent.

**However:** Because supports is called repeatedly during selection, it should ideally be **fast, deterministic, and side-effect-free**. Avoid having supports silently make costly network requests, mutate databases, or open unclosed resources. If capability checks are expensive, use a time-bounded metadata/health cache and a clear fallback policy.

## 7. Writing the Three Providers

### 7.1. PlainProvider: simple text

**providers/src/demo/providers/PlainProvider.java**

~~~java
package demo.providers;

import demo.spi.RenderRequest;
import demo.spi.ReportProvider;
import java.util.Set;

public final class PlainProvider implements ReportProvider {

    public PlainProvider() { }

    @Override
    public String id() {
        return "plain";
    }

    @Override
    public Set<String> formats() {
        return Set.of("text");
    }

    @Override
    public Set<String> features() {
        return Set.of("unicode");
    }

    @Override
    public int priority() {
        return 10;
    }

    @Override
    public String render(String input, RenderRequest request) {
        return "TEXT: " + input;
    }
}
~~~

PlainProvider only provides text and unicode; it **does not** claim heading or color support. This is not a "low-quality provider" but an implementation with a well-defined scope. If a user chooses plain yet requests html, the selector must reject plain.

### 7.2. MarkdownProvider: text or Markdown with heading

**providers/src/demo/providers/MarkdownProvider.java**

~~~java
package demo.providers;

import demo.spi.RenderRequest;
import demo.spi.ReportProvider;
import java.util.Set;

public final class MarkdownProvider implements ReportProvider {

    public MarkdownProvider() { }

    @Override
    public String id() {
        return "md";
    }

    @Override
    public Set<String> formats() {
        return Set.of("text", "markdown");
    }

    @Override
    public Set<String> features() {
        return Set.of("unicode", "heading");
    }

    @Override
    public int priority() {
        return 30;
    }

    @Override
    public String render(String input, RenderRequest request) {
        if ("markdown".equals(request.format())) {
            return "# " + input;
        }
        return "MD-TEXT: " + input;
    }
}
~~~

This provider supports **two formats**, and its output varies based on configuration. It has a higher priority than plain, so it will be chosen by default for text when no preferred ID is specified. This is an **application-defined policy**, not a fixed property of ServiceLoader.

### 7.3. HtmlProvider: HTML with heading and color

**providers/src/demo/providers/HtmlProvider.java**

~~~java
package demo.providers;

import demo.spi.RenderRequest;
import demo.spi.ReportProvider;
import java.util.Set;

public final class HtmlProvider implements ReportProvider {

    public HtmlProvider() { }

    @Override
    public String id() {
        return "html";
    }

    @Override
    public Set<String> formats() {
        return Set.of("html");
    }

    @Override
    public Set<String> features() {
        return Set.of("unicode", "heading", "color");
    }

    @Override
    public int priority() {
        return 20;
    }

    @Override
    public String render(String input, RenderRequest request) {
        String safe = input
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\"", "&quot;");

        return "<h1 style=\"color:navy\">" + safe + "</h1>";
    }
}
~~~

The exercise uses the input string **Hello <Java>** to show HTML output escaping: **<** and **>** are converted to entities. Escaping illustrates that format-specific output must be implemented properly inside each provider; the selector does not automatically convert plain text into safe HTML.

**Practical limitation:** The escape function above suffices for the **text node content** placed inside h1 in this example. If inserting data into a URL, JavaScript, CSS, or an HTML attribute in other contexts, you need an encoder tailored to **each context** rather than reusing this arbitrarily.

## 8. Registering Providers for ServiceLoader Discovery

Create the file:

**providers/resources/META-INF/services/demo.spi.ReportProvider**

~~~text
demo.providers.PlainProvider
demo.providers.MarkdownProvider
demo.providers.HtmlProvider
~~~

Each line is the full binary name of a **provider class**. The file uses UTF-8 and may contain blank lines or comments starting with **#**; this example keeps three simple lines.

**Requirements for classpath service providers:**

- The provider class is a **public concrete class** and implements **ReportProvider**.
- It has a **public no-arg constructor**, used by ServiceLoader to instantiate it.
- The class and its dependencies are visible to the class loader.
- The resource must reside inside the JAR at **META-INF/services/demo.spi.ReportProvider**; it must not be omitted during packaging.

Do not put class names in a package-less **META-INF/services/ReportProvider** file, and do not put **demo.spi.RenderRequest** there: that is not the service interface being looked up. Both API types must be shared between host and providers to prevent class identity errors when multiple class loaders are used.

In this example, the three providers are packaged into a single JAR to keep project setup brief. In a real application, each provider can live in its own JAR as long as service discovery is configured appropriately.

## 9. Host Main: Parsing Config, Filtering Capabilities, and Selecting Providers

**app/src/demo/app/Main.java**

~~~java
package demo.app;

import demo.spi.RenderRequest;
import demo.spi.ReportProvider;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.Optional;
import java.util.ServiceLoader;
import java.util.Set;

public final class Main {

    private static RenderRequest parse(String[] args) {
        Map<String, String> values = new LinkedHashMap<>();
        Set<String> allowed =
                Set.of("format", "requires", "prefer", "strict");

        for (String arg : args) {
            if (!arg.startsWith("--") || !arg.contains("=")) {
                throw new IllegalArgumentException(
                        "use --key=value");
            }

            String[] pair = arg.substring(2).split("=", 2);
            String key = pair[0];

            if (!allowed.contains(key)) {
                throw new IllegalArgumentException(
                        "unknown option: " + key);
            }

            if (values.putIfAbsent(key, pair[1]) != null) {
                throw new IllegalArgumentException(
                        "duplicate option: " + key);
            }
        }

        Set<String> required = new LinkedHashSet<>();
        String raw = values.getOrDefault("requires", "");

        if (!raw.isBlank()) {
            for (String piece : raw.split(",")) {
                String feature = piece.trim()
                        .toLowerCase(Locale.ROOT);

                if (feature.isEmpty()) {
                    throw new IllegalArgumentException(
                            "empty required feature");
                }
                required.add(feature);
            }
        }

        String strictText =
                values.getOrDefault("strict", "false");

        if (!strictText.equalsIgnoreCase("true")
                && !strictText.equalsIgnoreCase("false")) {
            throw new IllegalArgumentException(
                    "strict must be true or false");
        }

        return new RenderRequest(
                values.getOrDefault("format", "text"),
                required,
                values.getOrDefault("prefer", ""),
                Boolean.parseBoolean(strictText));
    }

    private static ReportProvider select(
            RenderRequest request) {

        ServiceLoader<ReportProvider> loader =
                ServiceLoader.load(ReportProvider.class);

        // get() instantiates the provider so supports() can
        // inspect the instance's actual capabilities.
        List<ReportProvider> discovered = loader.stream()
                .map(ServiceLoader.Provider::get)
                .toList();

        Set<String> ids = new HashSet<>();
        for (ReportProvider provider : discovered) {
            if (provider.id() == null
                    || provider.id().isBlank()
                    || !ids.add(provider.id())) {
                throw new IllegalStateException(
                        "duplicate or blank provider id");
            }
        }

        // Hard filter always runs BEFORE preference.
        List<ReportProvider> eligible = discovered.stream()
                .filter(p -> p.supports(request))
                .sorted(
                    Comparator.comparingInt(
                            ReportProvider::priority)
                        .reversed()
                        .thenComparing(ReportProvider::id))
                .toList();

        if (!request.preferredId().isEmpty()) {
            Optional<ReportProvider> preferred = eligible.stream()
                    .filter(p -> p.id()
                            .equals(request.preferredId()))
                    .findFirst();

            if (preferred.isPresent()) {
                return preferred.get();
            }

            if (request.strict()) {
                throw new NoSuchElementException(
                    "preferred provider not eligible: "
                        + request.preferredId());
            }
        }

        if (eligible.isEmpty()) {
            throw new NoSuchElementException(
                    "no eligible provider");
        }

        return eligible.get(0);
    }

    public static void main(String[] args) {
        try {
            RenderRequest request = parse(args);
            ReportProvider provider = select(request);

            System.out.println(
                    "selected=" + provider.id());
            System.out.println(
                    "rendered=" + provider.render(
                        "Hello <Java>", request));

        } catch (IllegalArgumentException
                | NoSuchElementException e) {
            System.out.println("ERROR=" + e.getMessage());
        }
    }
}
~~~

**Note on the source:** Main has unused imports **ArrayList** and **HashMap**; the Java compiler allows unused imports, though you can remove them for a cleaner project. The remaining imports match the code structure. **No provider implementation class is directly imported by Main**: the host uses only the service type, while provider implementations are discovered at runtime.

### 9.1. Why not select immediately via ServiceLoader.findFirst()?

The host collects discovered providers into a **discovered** list, then filters them using **supports(request)**. This ensures the decision is based on **actual capabilities** and configuration.

### 9.2. Why instantiate before checking supports?

**ServiceLoader.stream()** produces a stream of **ServiceLoader.Provider<ReportProvider>**. **Provider.type()** can allow inspecting class metadata without instantiating the service. However, in this exercise, capabilities are declared by **instance methods formats()/features()/supports()**, so **Provider.get()** must be called before querying support.

This comes with a cost: **all providers may be instantiated** even though only one is ultimately selected. If constructors are expensive or have side effects, move metadata earlier into a lightweight **factory-as-service**, a suitable annotation, or a trusted manifest/registry, and instantiate heavy resources only after a provider is chosen. Do not assume **Provider.type()** is always the implementation class in all cases: with an explicit named JPMS module using a public static provider() factory, **type() is the declared return type of the provider method**.

### 9.3. Why filter hard constraints first?

We only allow a provider into the eligible list when:

~~~java
provider.formats().contains(request.format())
        && provider.features().containsAll(
                request.requiredFeatures())
~~~

If the user requires HTML + color, plain is ineligible even if they pass **--prefer=plain**. This is the principle of *never relaxing mandatory requirements just to satisfy a preference*.

**Note:** In the example code, supports is already a default method on the interface, so Main calls **p.supports(request)** instead of duplicating logic; providers can later override it to check additional runtime conditions.

### 9.4. Why sort after filtering?

If there is no valid preferred provider and strict=false, the selector chooses from the **eligible** set by:

1. **priority descending**.
2. If priorities tie, **id ascending**.

As a result, adding a JAR or changing the order of entries in the service file does not automatically change the selected provider **as long as the actual set of providers/priorities/IDs stays unchanged**. If a new provider with a higher priority is added, the selection may change according to policy; log this decision to explain why.

### 9.5. Why must strict fail?

Strict expresses the intent "**use only this provider ID**". When the preferred provider does not exist or fails to meet format/features, silently switching to another provider would violate the configuration contract. The code therefore throws **NoSuchElementException** with a message containing the rejected ID; Main turns it into an ERROR line.

In production systems, this situation is usually modeled as a domain error type such as **ProviderSelectionException** with a reason code, rather than relying on exception message text.

## 10. Compiling and Packaging on Java 17

From the **provider-selection-lab** directory, run with JDK 17 or newer.

### 10.1. Linux/macOS (bash)

~~~bash
mkdir -p build/api build/providers build/app
mkdir -p build/providers/META-INF/services

javac --release 17 -encoding UTF-8 -d build/api \
  api/src/demo/spi/RenderRequest.java \
  api/src/demo/spi/ReportProvider.java

javac --release 17 -encoding UTF-8 -cp build/api \
  -d build/providers \
  providers/src/demo/providers/PlainProvider.java \
  providers/src/demo/providers/MarkdownProvider.java \
  providers/src/demo/providers/HtmlProvider.java

cp providers/resources/META-INF/services/demo.spi.ReportProvider \
  build/providers/META-INF/services/

jar --create --file build/providers.jar -C build/providers .

javac --release 17 -encoding UTF-8 -cp build/api \
  -d build/app app/src/demo/app/Main.java
~~~

### 10.2. Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force build/api, build/providers, build/app, build/providers/META-INF/services | Out-Null

javac --release 17 -encoding UTF-8 -d build/api api/src/demo/spi/RenderRequest.java api/src/demo/spi/ReportProvider.java

javac --release 17 -encoding UTF-8 -cp build/api -d build/providers providers/src/demo/providers/PlainProvider.java providers/src/demo/providers/MarkdownProvider.java providers/src/demo/providers/HtmlProvider.java

Copy-Item -Force providers/resources/META-INF/services/demo.spi.ReportProvider build/providers/META-INF/services/

jar --create --file build/providers.jar -C build/providers .

javac --release 17 -encoding UTF-8 -cp build/api -d build/app app/src/demo/app/Main.java
~~~

The JAR must contain the provider classes and resource:

~~~text
META-INF/services/demo.spi.ReportProvider
demo/providers/PlainProvider.class
demo/providers/MarkdownProvider.class
demo/providers/HtmlProvider.class
~~~

Inspect with:

~~~bash
jar --list --file build/providers.jar
~~~

The JAR listing may also include **META-INF/MANIFEST.MF** and directory entries; what matters is that the service descriptor and the three classes exist at the exact paths.

**Do not package a duplicate copy of the API inside providers.jar** when the host already has the same API version. Both sides must reference the same **demo.spi.ReportProvider** type by class identity; identical binary names across different class loaders do not constitute the same Java Class.

## 11. Running User Configurations and Comparing Results

The program accepts the options:

~~~text
--format=text|markdown|html
--requires=unicode,heading,color
--prefer=plain|md|html
--strict=true|false
~~~

**The syntax is --key=value**, with no spaces around the equals sign. Do not type **|** in actual commands; it merely denotes choices in the documentation. Options can be omitted to use defaults: format=text, requiredFeatures empty, preferredId empty, strict=false.

### 11.1. Prefer plain when it meets all requirements

Linux/macOS:

~~~bash
java -cp build/api:build/app:build/providers.jar demo.app.Main \
  --format=text --requires=unicode --prefer=plain --strict=true
~~~

Windows PowerShell:

~~~powershell
java -cp "build/api;build/app;build/providers.jar" demo.app.Main --format=text --requires=unicode --prefer=plain --strict=true
~~~

**Stdout:**

~~~text
selected=plain
rendered=TEXT: Hello <Java>
~~~

Even though md has priority 30, **preferred plain** wins because it passed the hard filter. This honors user preference without violating mandatory constraints.

### 11.2. Preferred does not support Markdown, strict=false allows fallback

Linux/macOS:

~~~bash
java -cp build/api:build/app:build/providers.jar demo.app.Main \
  --format=markdown --requires=heading --prefer=plain
~~~

Windows PowerShell:

~~~powershell
java -cp "build/api;build/app;build/providers.jar" demo.app.Main --format=markdown --requires=heading --prefer=plain
~~~

**Stdout:**

~~~text
selected=md
rendered=# Hello <Java>
~~~

Plain lacks the markdown format and heading feature; it is excluded from the eligible list. Because strict=false by default, the host selects md as an eligible provider.

### 11.3. Requesting HTML with color

Linux/macOS:

~~~bash
java -cp build/api:build/app:build/providers.jar demo.app.Main \
  --format=html --requires=color --prefer=plain
~~~

Windows PowerShell:

~~~powershell
java -cp "build/api;build/app;build/providers.jar" demo.app.Main --format=html --requires=color --prefer=plain
~~~

**Stdout:**

~~~text
selected=html
rendered=<h1 style="color:navy">Hello &lt;Java&gt;</h1>
~~~

HtmlProvider is the only provider declaring both the html format and color feature. Here the user's preference is **evaluated**, then rejected for failing hard constraints. The HTML provider also escapes input before generating HTML output.

### 11.4. No preferred provider: select by priority

Linux/macOS:

~~~bash
java -cp build/api:build/app:build/providers.jar demo.app.Main \
  --format=text --requires=unicode
~~~

Windows PowerShell:

~~~powershell
java -cp "build/api;build/app;build/providers.jar" demo.app.Main --format=text --requires=unicode
~~~

**Stdout:**

~~~text
selected=md
rendered=MD-TEXT: Hello <Java>
~~~

Plain and md are both eligible, but md has priority 30 compared to 10. If the user wants plain, they can set **--prefer=plain**.

### 11.5. Ineligible strict preference must report an error

Linux/macOS:

~~~bash
java -cp build/api:build/app:build/providers.jar demo.app.Main \
  --format=markdown --requires=heading \
  --prefer=plain --strict=true
~~~

Windows PowerShell:

~~~powershell
java -cp "build/api;build/app;build/providers.jar" demo.app.Main --format=markdown --requires=heading --prefer=plain --strict=true
~~~

**Stdout:**

~~~text
ERROR=preferred provider not eligible: plain
~~~

This is the **correct** behavior of strict mode: no selected line, no render call, and no automatic fallback to md even though md is eligible.

### 11.6. No provider satisfies the format

Linux/macOS:

~~~bash
java -cp build/api:build/app:build/providers.jar demo.app.Main \
  --format=pdf --requires=unicode
~~~

Windows PowerShell:

~~~powershell
java -cp "build/api;build/app;build/providers.jar" demo.app.Main --format=pdf --requires=unicode
~~~

**Stdout:**

~~~text
ERROR=no eligible provider
~~~

The filter does not silently drop format=pdf. If a mandatory requirement is unsupported, the right outcome is "no eligible provider".

### 11.7. Strict=true without choosing a preferred provider

Linux/macOS:

~~~bash
java -cp build/api:build/app:build/providers.jar demo.app.Main \
  --strict=true
~~~

Windows PowerShell:

~~~powershell
java -cp "build/api;build/app;build/providers.jar" demo.app.Main --strict=true
~~~

**Stdout:**

~~~text
ERROR=strict requires --prefer
~~~

This is a configuration error detected **before service discovery**. Invalid input must be distinguished from errors caused by missing providers.

## 12. Capability-Based Provider Selection: Designing Conditions Properly

### 12.1. AND model across required features

The ReportProvider code uses:

~~~java
// Illustrative snippet inside ReportProvider.
return formats().contains(request.format())
        && features().containsAll(request.requiredFeatures());
~~~

This means **requires=unicode,heading** demands both unicode and heading, not "either one". If business rules require OR, NOT, or complex grouped conditions, model the criteria explicitly rather than assuming Set.containsAll handles everything.

### 12.2. Distinguishing capability from preference

**Capability** tells whether *a provider can fulfill the request*. **Preference** tells *which eligible provider the user prefers*. **Priority** is the host's fallback policy when no eligible preferred provider exists.

These concepts must not be mixed. Even a provider with a very high priority is eliminated if it lacks **format** or **requiredFeatures**.

### 12.3. Dynamic request-dependent capabilities

In the example, capabilities are fixed Sets. In real extensions, you can add:

~~~java
// Illustrative snippet: adding a policy inside a provider.
@Override
public boolean supports(RenderRequest request) {
    return ReportProvider.super.supports(request)
            && quotaService.hasCapacity();
}
~~~

**The snippet above does not run standalone** because quotaService is an application dependency. It only shows the override pattern. If quota changes over time, the result of supports may change between selection and rendering; you need a reservation/transaction mechanism or a re-check during execution. Never treat a supports answer as a permanent guarantee when external state is involved.

### 12.4. Configuration should be validated at the boundary

Main handles unknown keys, duplicate options, strict values other than true/false, empty format, and empty required features. In real applications, CLI may be replaced by JSON, YAML, environment variables, or a UI. Regardless of the source, normalize keys/IDs, validate required features, and **never silently ignore unrecognized configuration**.

For example, suppose a user types **--requires=colr** instead of color. The selector must return no eligible provider; it must not drop colr and pick an arbitrary renderer.

## 13. When to Use Provider.type() Before Provider.get()?

**ServiceLoader.stream()** returns a stream of **ServiceLoader.Provider<S>**, unlike **ServiceLoader.iterator()**, which directly yields service instances.

- **Provider.type()** returns a Class describing the provider type. On the classpath constructor route, this is typically the implementation class. You can inspect annotations on the type without instantiating it.
- **Provider.get()** creates/retrieves the service instance for calling methods such as supports, id, and render. It may incur configuration errors or constructor overhead.
- **ServiceLoader.iterator()** generally instantiates providers during iteration and can be used when instance metadata is needed right away.

Example snippet filtering by annotation:

~~~java
// Illustrative snippet, assuming @PreferredBackend annotation exists.
ServiceLoader<ReportProvider> loader =
        ServiceLoader.load(ReportProvider.class);

var candidates = loader.stream()
        .filter(p -> p.type()
                .isAnnotationPresent(PreferredBackend.class))
        .map(ServiceLoader.Provider::get)
        .toList();
~~~

**This is not a standalone program**: PreferredBackend must be defined. And there is an important JPMS caveat: if an explicit named module uses **public static provider()** as a provider factory, **Provider.type() returns the declared return type of the provider method**, not necessarily the provider class written in the module descriptor. Do not build a provider selection policy assuming type() always points to the concrete implementation class.

For **user preference + dynamic capabilities**, choosing a lightweight **factory service** to read metadata and only then creating expensive renderers/resources is a stronger design. This example intentionally instantiates all three providers because their constructors are cheap, keeping the focus on selection logic.

## 14. Handling ServiceConfigurationError Properly

In the demo, selection errors are usually **IllegalArgumentException** or **NoSuchElementException**. However, **ServiceLoader** can throw **ServiceConfigurationError** when:

- The **META-INF/services** resource is malformed or points to a non-existent class.
- The provider does not properly implement the service or lacks a public no-arg constructor on the classpath.
- A constructor or provider factory throws an error.
- An I/O or class loading failure occurs while ServiceLoader discovers providers.

**ServiceConfigurationError is an Error**, so it is not caught by the example's IllegalArgumentException | NoSuchElementException catch block. This is **intentional**: a broken deployment configuration is not disguised as a user error like "no eligible provider".

In production systems with plugin management boundaries, you can catch it at the bootstrap/plugin-manager layer to log full details and isolate the faulty plugin, but you should not silently ignore it and fall back to another provider without an explicit policy. If providers are installed by third parties, decide between fail-fast or isolate-one-provider and maintain audit information.

**Avoid handling it like this:**

~~~java
// Illustrative anti-pattern, not standalone code.
try {
    return ServiceLoader.load(ReportProvider.class)
            .findFirst().orElse(null);
} catch (Throwable ignore) {
    return null;
}
~~~

The snippet above swallows programming/deployment errors and makes debugging extremely difficult. Distinguish between:

- No provider found: discovered list is empty.
- Providers exist but none meet requirements: eligible is empty.
- User selected a specific provider and strict failed: preferred not eligible.
- Broken SPI configuration: ServiceConfigurationError.
- Selected provider fails during render: business execution or provider deployment error, handled separately.

## 15. Adapting the Design to JPMS or Module Path

The main example uses the classpath and **META-INF/services**. When moving to explicit named modules, the service mechanism remains ServiceLoader, but provider declarations change.

**API module** (illustrative snippet):

~~~java
module report.api {
    exports demo.spi;
}
~~~

**Provider module** (illustrative snippet):

~~~java
module report.plugins {
    requires report.api;
    provides demo.spi.ReportProvider
        with demo.providers.PlainProvider,
             demo.providers.MarkdownProvider,
             demo.providers.HtmlProvider;
}
~~~

**Host module** (illustrative snippet):

~~~java
module report.host {
    requires report.api;
    uses demo.spi.ReportProvider;
}
~~~

These are **illustrative module-info.java snippets**, not a requirement to automatically convert the classpath example into modules. In a real JPMS deployment, you must compile a proper module layout, resolve provider modules, and ensure all modules can read the API contract.

With an **automatic module** (a legacy JAR without module-info.class on the module path), ServiceLoader can use service metadata derived from META-INF/services, but an automatic-module provider must have a **public no-arg constructor**. Static provider factory methods are not supported in automatic modules.

With an explicit named module, you can use **provides ... with ...** and, when properly declared, a no-arg **public static provider()** method invoked by ServiceLoader; in that case **Provider.type()** can be the return type of that method. This is another reason to base capability selection on a stable service contract rather than relying on implementation class names unnecessarily.

**Do not use ServiceLoader.findFirst() to determine priority order across modules**, because provider order across modules in the same layer is not generally guaranteed. Keep the priority + ID sorting algorithm shown in this exercise.

## 16. Configuration, Security, and Provider Lifecycle Considerations

### 16.1. Configuration sources must be explicit

Configuration may come from CLI, properties files, environment variables, or a UI. Define precedence among them (e.g., CLI overrides file), validate each source, and log the final choice. Never infer a preferred provider from file order inside a JAR.

### 16.2. IDs are a user-facing contract

Once a user saves **--prefer=md**, **id()** becomes a public configuration contract. Do not rename IDs arbitrarily when refactoring class names. If an ID changes, provide an alias or migration path. If two JARs declare the same ID, the selector must reject the collision or apply an explicit namespacing policy.

### 16.3. Provider metadata is not security

**features()** and **supports()** are merely self-reported declarations by a provider. An untrusted provider can lie, and constructors/renderers can execute arbitrary code inside the JVM. Never use a capability filter as a security sandbox. When running untrusted plugins, use process/container isolation or proper security controls along with supply-chain verification.

### 16.4. Selection is not full lifecycle management

The demo instantiates every provider once to inspect metadata. In real systems, providers may open connections, thread pools, or file handles. If a service allocates resources, define an explicit lifecycle contract (such as Closeable, or a factory that creates and closes sessions), or lazily initialize resources after selection. Avoid unexpected expensive work inside provider constructors.

### 16.5. Concurrency and caching

ServiceLoader caches providers and offers **reload()** to rediscover them, though modifying the module path/classpath does not always cause all class loaders to pick up new JARs automatically. Request configurations can vary per call; avoid caching a selection keyed only by format when requiredFeatures, preferred ID, or strict policy may differ. Selection based on external health/quota also requires invalidation.

**ServiceLoader is not a thread-safe shared structure for arbitrary concurrent operations**; manage provider lookup and usage in concurrent runtimes according to its documentation and class loader rules. Avoid calling **reload()** while iterating another stream or iterator of the same ServiceLoader.

### 16.6. Selection stability

Sorting by priority then ID keeps selection stable when the provider set is unchanged. If a new provider with higher priority is added, automatic selection can change. Recording **providerId**, **format**, **requiredFeatures**, **policy version**, and fallback reasons in logs makes changes traceable.

## 17. Systematic Testing of Provider Selection

Separate selection logic from System.out and CLI before moving to production. Write unit tests covering:

| Test | Input | Expected |
|---|---|---|
| Preferred eligible | text, unicode, plain, strict=true | **plain** |
| Preferred lacks capability, fallback | markdown, heading, plain, strict=false | **md** |
| Preferred lacks capability, strict | markdown, heading, plain, strict=true | **error** |
| No preferred, two eligible providers | text, unicode | **md** by priority |
| Single eligible provider | html, color | **html** |
| No provider for format | pdf | **no eligible provider** |
| Missing feature | text, ocr | **no eligible provider** |
| Unknown CLI key | --unknown=x | **configuration error** |
| Strict missing preferred | --strict=true | **configuration error** |
| Two providers with equal priority | two eligible providers | **ascending ID** |
| Two providers with duplicate ID | non-unique IDs | **fail-fast** |
| Broken provider class | invalid service descriptor | **ServiceConfigurationError** |

**Real provider testing** should also cover special inputs: Unicode, HTML metacharacters, empty data, maximum length, locales, and resource limits. Advertised capabilities must be backed by behavioral tests, not just Set.contains() checks.

### Exercise 1: Add CsvProvider

Create a new provider class with ID **csv**, format **csv**, feature **unicode**, and priority 15, register it in META-INF/services, and run **--format=csv**. Verify the new provider appears without modifying imports or switch-case statements in the host.

Business hint: properly quote and escape CSV cells containing commas, quotes, or newlines; do not treat joining strings with commas as a complete CSV parser/serializer.

### Exercise 2: Add a max-size capability

Extend RenderRequest with expected input size; let providers override supports to reject requests exceeding their limit. Test that a preferred provider **cannot** bypass the hard limit and strict=true returns an error.

### Exercise 3: Change fallback policy

Allow the user to specify a prioritized list of IDs, e.g., md then html then plain. Select only from the eligible set in preference order; if none of the preferred IDs are eligible, fall back to priority + ID. Clearly specify whether "strict" applies to the **entire preferred list** or only the first entry before coding.

### Exercise 4: Separate factory from heavy renderer

Replace the ReportProvider service instance with a **ReportProviderFactory** having lightweight metadata and **create(request)**. ServiceLoader selects a valid factory first, then instantiates the renderer resource. Verify that constructors of unselected renderers never run.

## 18. Common Mistakes and Fixes

**Mistake 1: Picking the first provider.** Using findFirst() for business decisions lets discovery order dictate outcomes. **Fix:** hard filter + preferred + priority + tie-breaker.

**Mistake 2: Treating preferred as mandatory even when strict=false.** This blocks fallback even when the user allows it. **Fix:** try preferred within the eligible set; if absent, fall back only when strict=false.

**Mistake 3: Letting preferred bypass the capability filter.** The user prefers plain yet requests html; if the host still selects plain, requirements are violated. **Fix:** filter format/features first.

**Mistake 4: Forgetting to copy META-INF/services into the JAR.** ServiceLoader may return an empty list even when classes compile. **Fix:** inspect with **jar --list** and verify the exact service file name.

**Mistake 5: Missing public no-arg constructor.** A classpath provider cannot be instantiated by ServiceLoader. **Fix:** implement a public no-arg constructor and valid contract, or switch to an explicit JPMS provider method where appropriate.

**Mistake 6: Prioritizing by JAR order.** Classpath/module resolution order can change and is not a stable policy. **Fix:** use an explicit comparator.

**Mistake 7: Calling get() too early in costly systems.** Instantiating every backend just to inspect capabilities causes slowdowns/side effects. **Fix:** use a lightweight factory or metadata prefilter, then lazily create actual resources.

**Mistake 8: Swallowing ServiceConfigurationError.** A broken JAR configuration gets reported as "no eligible provider". **Fix:** distinguish broken deployments from unsupported requests and log the full cause.

**Mistake 9: Caching results while forgetting preferences.** A selection made for user A gets reused for user B despite different configs. **Fix:** include format/features/preferred/strict/policy in the cache key and handle stale cache invalidation.

**Mistake 10: Treating capabilities as access permissions.** A plugin declaring "secure" in features() does not make it trustworthy. **Fix:** authorization and isolation belong to a separate layer.

## 19. Self-Assessment Questions

**Question 1.** Why shouldn't you choose ServiceLoader.findFirst() when users supply configuration?

**Answer:** Discovery order is not a selection policy. The first provider may fail to satisfy format, requiredFeatures, or preference; across modules, order is not generally guaranteed either.

**Question 2.** The user sets **prefer=plain**, **format=markdown**, **strict=false**. What is selected?

**Answer:** Plain fails the hard constraints. Fallback selects md because it supports markdown. No error is raised when another eligible provider exists.

**Question 3.** Same configuration as above, but strict=true?

**Answer:** Reports preferred provider not eligible error, without automatically falling back to md.

**Question 4.** Two providers both support text/unicode; which rule selects one when no preferred provider is set?

**Answer:** Sort by priority descending, then ID ascending. With the exercise table, md has priority 30 and beats plain at 10.

**Question 5.** If a provider has priority=100 but lacks color, will it be selected for requires=color?

**Answer:** No. Priority only applies after a provider satisfies all hard constraints.

**Question 6.** Why isn't ServiceLoader.Provider.type() always the concrete implementation class?

**Answer:** In an explicit named module using a static provider() factory, type() can return the declared return type of the provider method rather than the factory class.

**Question 7.** Why is it necessary to detect duplicate provider IDs?

**Answer:** PreferredId is a public configuration identifier. If two implementations share an ID and the host picks arbitrarily, behavior becomes unpredictable and hard to audit.

**Question 8.** How does having no provider supporting the format differ from a corrupted META-INF/services?

**Answer:** Having no eligible candidate is a normal outcome of capability filtering; a corrupted descriptor or provider can throw ServiceConfigurationError, signaling a deployment issue that requires separate handling.

## 20. Exercise Completion Checklist

1. The API defines **ReportProvider**, **RenderRequest**, capabilities, and preference options.
2. There are at least two independent providers with distinct formats/features; this example has three.
3. **ServiceLoader** locates providers from the proper **META-INF/services** on the classpath.
4. The host **does not import implementation classes** and avoids if/else chains on class names.
5. User configuration is parsed, normalized, and validated explicitly.
6. The selector chooses only among **eligible providers** meeting all hard constraints.
7. **Preferred** gets priority within eligible providers, never bypassing hard constraints.
8. **Strict=true** returns an error when preferred is ineligible; strict=false allows fallback.
9. Fallback selects by descending priority, then ascending ID; duplicate IDs are blocked.
10. Tests exist for unknown formats, unsupported features, invalid CLI options, and broken SPI descriptors.
11. Discovery errors such as ServiceConfigurationError are never swallowed; metadata is not treated as a sandbox.
12. Final selection is logged and providers/resources follow a sound lifecycle.

**Conclusion:** ServiceLoader provides **discovery and instantiation**, while the application must define its own **selection policy**. A safe and testable policy is **filter by mandatory capabilities → evaluate user preference → strict or fallback → deterministic tie-breaker**. This makes it easy to add plugins without losing control over per-request outcomes.

### Java SE 17 Documentation

- ServiceLoader: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- ServiceLoader.Provider: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.Provider.html
- Java Service Provider framework, ServiceLoader configuration files, and JPMS providers: see the Developing/Deploying service providers section on the ServiceLoader page above.
- Set.copyOf and unmodifiable collections: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection)
- Java record classes, Java Language Specification §8.10: https://docs.oracle.com/en/java/javase/17/docs/specs/jls/se17/html/jls-8.html#jls-8.10
