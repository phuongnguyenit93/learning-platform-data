# Building a Document Processing Application with a Contract and Two SPI Providers

## 1. Exercise Objectives

This exercise builds a Java document-processing application using the **Service Provider Interface (SPI)**. The host does not directly import or instantiate any implementation. Instead, the host depends only on the **`DocumentProcessor` contract**, while two provider JARs register their implementations via `META-INF/services` and are discovered by `ServiceLoader` at runtime.

After completing this exercise, you will be able to:

- Design a stable API so plugins can return document-processing results.
- Package **two independent providers** with two distinct behaviors: word counting (`word-count`) and line counting (`line-count`).
- Use `ServiceLoader` to discover providers, select one by `id()`, and handle duplicate IDs, missing providers, and plugin errors.
- Compile, package, and run the project on **Java 17+** using `javac`, `jar`, and `java` without needing Maven/Gradle.
- Demonstrate extensibility: removing one provider JAR leaves the other provider working; adding a new JAR requires no recompilation of the host.

**Scope:** The input data is plain UTF-8 text, not a PDF/DOCX parser. Word and line counting use transparent rules so they can be tested easily; when other document formats are needed, a new provider adhering to the same contract can be added.

## 2. Architecture: host ↔ contract ↔ providers

```text
                      +--------------------------+
                      | DocumentApp (host)       |
                      | ServiceLoader.load(...)  |
                      +-------------+------------+
                                    |
                                    v
                      +--------------------------+
                      | DocumentProcessor (API)  |
                      | id(), process(String)   |
                      +-------------+------------+
                                    ^
                       implements  | implements
                  +-----------------+------------------+
                  |                                    |
       +----------+-----------+            +-----------+----------+
       | WordCountProcessor   |            | LineCountProcessor   |
       | provider-word.jar    |            | provider-line.jar    |
       +----------------------+            +----------------------+
```

**Class identity principle:** `DocumentProcessor` must be defined **once** and shared across the host and both providers. This example uses the class path: `api.jar` is a shared artifact; **do not package a copy of the contract class inside the two provider JARs**. If the contract is defined by multiple different class loaders, a provider may not be assignable to the interface used by the host.

## 3. Directory Structure

```text
document-spi/
├── api/
│   └── src/demo/api/
│       ├── DocumentProcessor.java
│       └── ProcessingResult.java
├── host/
│   └── src/demo/host/DocumentApp.java
├── provider-word/
│   ├── src/demo/word/WordCountProcessor.java
│   └── resources/META-INF/services/demo.api.DocumentProcessor
└── provider-line/
    ├── src/demo/line/LineCountProcessor.java
    └── resources/META-INF/services/demo.api.DocumentProcessor
```

The commands below run from the root `document-spi/` directory, using a POSIX shell (Linux/macOS/Git Bash) and JDK 17+. On Windows PowerShell/cmd, adjust the line continuation character and class path separator (`;` instead of `:`).

## 4. Designing the SPI Contract

A good contract should not depend on any specific provider class. Use a stable ID to select a capability, have the `process` method accept the document as a `String`, and represent the result with a `record` composed solely of standard Java types.

### 4.1. Interface

File `api/src/demo/api/DocumentProcessor.java`:

```java
package demo.api;

public interface DocumentProcessor {
    /** Unique, stable provider ID, e.g., word-count. */
    String id();

    /** Processes text content without writing files or printing to stdout. */
    ProcessingResult process(String document);
}
```

### 4.2. Shared Result Type

File `api/src/demo/api/ProcessingResult.java`:

```java
package demo.api;

import java.util.Objects;

public record ProcessingResult(String processorId, String description, long value) {
    public ProcessingResult {
        Objects.requireNonNull(processorId, "processorId");
        Objects.requireNonNull(description, "description");
        if (value < 0) throw new IllegalArgumentException("value must be >= 0");
    }
}
```

`record` is built into Java 17. Having the contract use a pure-data result type keeps the host from having to cast to an implementation. If you change the method signature or record format later, you will need API versioning and binary compatibility checks for plugin JARs.

## 5. Provider 1: Word Count

Convention: a **word** is a group of non-whitespace characters according to the Java regex `\S+`. On an empty or whitespace-only string, the result is 0. This is a simple tokenization rule, not full word segmentation for all languages.

File `provider-word/src/demo/word/WordCountProcessor.java`:

```java
package demo.word;

import demo.api.DocumentProcessor;
import demo.api.ProcessingResult;
import java.util.Objects;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class WordCountProcessor implements DocumentProcessor {
    private static final Pattern TOKEN = Pattern.compile("\\S+");

    public WordCountProcessor() {}

    @Override
    public String id() {
        return "word-count";
    }

    @Override
    public ProcessingResult process(String document) {
        Objects.requireNonNull(document, "document");
        long count = 0;
        Matcher matcher = TOKEN.matcher(document);
        while (matcher.find()) count++;
        return new ProcessingResult(id(), "Words", count);
    }
}
```

File **`provider-word/resources/META-INF/services/demo.api.DocumentProcessor`** must contain the exact binary name of the implementation:

```text
demo.word.WordCountProcessor
```

This is a mandatory configuration file for class-path SPI. The file name is the **fully qualified name of the service interface**, not the plugin ID or JAR name.

## 6. Provider 2: Line Count

Convention: an empty document has 0 lines; a non-empty string has `1 + number of '\n' characters`, except if it ends with a newline, the trailing newline only terminates the line and does not create a new empty line. That is, `"a\nb\n"` has 2 lines, and `"a\nb"` also has 2 lines. `\r\n` is treated as a line break because it contains `\n`.

File `provider-line/src/demo/line/LineCountProcessor.java`:

```java
package demo.line;

import demo.api.DocumentProcessor;
import demo.api.ProcessingResult;
import java.util.Objects;

public final class LineCountProcessor implements DocumentProcessor {
    public LineCountProcessor() {}

    @Override
    public String id() {
        return "line-count";
    }

    @Override
    public ProcessingResult process(String document) {
        Objects.requireNonNull(document, "document");
        if (document.isEmpty()) {
            return new ProcessingResult(id(), "Lines", 0);
        }

        long count = 1;
        for (int i = 0; i < document.length(); i++) {
            if (document.charAt(i) == '\n') count++;
        }
        if (document.charAt(document.length() - 1) == '\n') count--;
        return new ProcessingResult(id(), "Lines", count);
    }
}
```

File **`provider-line/resources/META-INF/services/demo.api.DocumentProcessor`**:

```text
demo.line.LineCountProcessor
```

In production, you must define how to handle standalone `\r`, Unicode line separators, blank lines, and encoding. This exercise uses a minimal convention to clearly illustrate how a provider implements logic independently of the host.

## 7. Host: Discovering and Selecting Providers

The host only imports `demo.api.*` and does not reference either implementation class. `ServiceLoader` loads the list of providers via SPI descriptors on the class path. Because discovery order should not be relied upon as business logic, the host stores providers in a `TreeMap` to list them deterministically by ID.

File `host/src/demo/host/DocumentApp.java`:

```java
package demo.host;

import demo.api.DocumentProcessor;
import demo.api.ProcessingResult;
import java.util.Map;
import java.util.ServiceLoader;
import java.util.TreeMap;

public final class DocumentApp {
    public static void main(String[] args) {
        Map<String, DocumentProcessor> providers = new TreeMap<>();

        for (DocumentProcessor provider :
                ServiceLoader.load(DocumentProcessor.class)) {
            String id = provider.id();
            if (id == null || id.isBlank()) {
                throw new IllegalStateException("Invalid provider ID");
            }
            if (providers.putIfAbsent(id, provider) != null) {
                throw new IllegalStateException("Duplicate provider ID: " + id);
            }
        }

        if (providers.isEmpty()) {
            System.err.println("No SPI provider found");
            System.exit(1);
        }

        String document = "Hello Java SPI\nDocument processing example in Java\n";
        System.out.println("Available providers: " + providers.keySet());
        for (DocumentProcessor processor : providers.values()) {
            ProcessingResult result = processor.process(document);
            System.out.println(result.processorId() + " => "
                    + result.description() + ": " + result.value());
        }

        if (args.length > 0) {
            DocumentProcessor selected = providers.get(args[0]);
            if (selected == null) {
                System.err.println("Unknown provider: " + args[0]);
                System.exit(2);
            }
            System.out.println("Selected: " + selected.id());
        }
    }
}
```

**Why can `ServiceLoader` see the providers?** `java` starts with both `provider-word.jar` and `provider-line.jar` on the class path, each containing the proper `META-INF/services/demo.api.DocumentProcessor`. The application class loader reads the service descriptors, loads the implementations, invokes their public no-arg constructors, and returns the instances to the host.

If a provider constructor or class loading fails, `ServiceLoader` can throw `ServiceConfigurationError` (an `Error`) during iteration. You should not `catch(Throwable)` to silently ignore serious errors. Production systems should distinguish between an invalid provider, an initialization failure, and a policy rejection.

## 8. Compiling and Packaging with JDK 17+

### 8.1. Create build directories

```bash
mkdir -p build/api build/host build/word build/line dist
```

### 8.2. Compile the contract

```bash
javac -encoding UTF-8 -d build/api \
  api/src/demo/api/DocumentProcessor.java \
  api/src/demo/api/ProcessingResult.java
jar --create --file dist/document-api.jar -C build/api .
```

### 8.3. Compile both providers

```bash
javac -encoding UTF-8 -cp dist/document-api.jar -d build/word \
  provider-word/src/demo/word/WordCountProcessor.java

javac -encoding UTF-8 -cp dist/document-api.jar -d build/line \
  provider-line/src/demo/line/LineCountProcessor.java
```

### 8.4. Package JARs and service descriptors

```bash
jar --create --file dist/provider-word.jar \
  -C build/word . \
  -C provider-word/resources META-INF

jar --create --file dist/provider-line.jar \
  -C build/line . \
  -C provider-line/resources META-INF
```

Inspect contents:

```bash
jar --list --file dist/provider-word.jar
jar --list --file dist/provider-line.jar
```

Both JARs must contain their corresponding `META-INF/services/demo.api.DocumentProcessor`. Do not package `demo/api/DocumentProcessor.class` inside either provider JAR.

### 8.5. Compile the host

```bash
javac -encoding UTF-8 -cp dist/document-api.jar -d build/host \
  host/src/demo/host/DocumentApp.java
jar --create --file dist/document-host.jar -C build/host .
```

### 8.6. Run with both providers

```bash
java -cp 'dist/document-api.jar:dist/document-host.jar:dist/provider-word.jar:dist/provider-line.jar' \
  demo.host.DocumentApp
```

Exact stdout:

```text
Available providers: [line-count, word-count]
line-count => Lines: 2
word-count => Words: 8
```

Counting explanation: the document consists of `Hello Java SPI` (3 tokens) and `Document processing example in Java` (5 tokens); there are 2 lines and the trailing newline does not create a third line. Provider order is stabilized by `TreeMap` rather than depending on ServiceLoader discovery order.

### 8.7. Select a provider by ID

```bash
java -cp 'dist/document-api.jar:dist/document-host.jar:dist/provider-word.jar:dist/provider-line.jar' \
  demo.host.DocumentApp word-count
```

Output adds one line:

```text
Selected: word-count
```

The host still runs both providers in the demo section before printing the selection. In a real application, filtering providers can occur before processing, and if **one** implementation needs to be chosen, only invoke `process` on the selected provider.

## 9. Testing Provider Independence

### 9.1. Install only one provider

Remove the line provider from the class path:

```bash
java -cp 'dist/document-api.jar:dist/document-host.jar:dist/provider-word.jar' \
  demo.host.DocumentApp
```

Stdout:

```text
Available providers: [word-count]
word-count => Words: 8
```

This proves that the host does not need to link directly to `LineCountProcessor` to operate. If both provider JARs are omitted, the host returns exit code 1 with the message `No SPI provider found` on stderr.

### 9.2. Non-existent provider ID

Run with both providers and pass the argument `missing`:

```bash
java -cp 'dist/document-api.jar:dist/document-host.jar:dist/provider-word.jar:dist/provider-line.jar' \
  demo.host.DocumentApp missing
```

The host prints both results and then prints `Unknown provider: missing` to stderr, exiting with exit code 2. This handles a request to select a non-existent plugin, which is distinct from an SPI discovery error.

### 9.3. Duplicate ID

If a new provider also returns `id() == "word-count"`, the program rejects it when building the registry. Duplicate ID policy must be defined upfront: fail-fast is safer than arbitrarily picking the first provider.

### 9.4. Provider throws an error during processing

In production, `process` may throw an exception due to malformed document content, missing dependencies, I/O, or a plugin bug. The host should log the error along with the provider ID and decide whether fallback is permitted. **Do not automatically route data to another provider by default** if their semantics differ (for example, from word counting to line counting).

## 10. Extending to Dynamically Loaded Plugins

The current example uses the startup class path. In systems that need to install JARs while the JVM is running, you can use a new `URLClassLoader` and create `ServiceLoader.load(DocumentProcessor.class, pluginLoader)`. You must ensure the plugin loader sees the **same contract API class** that the host uses.

API sketch, **not yet a standalone program**:

```java
URL[] jars = { Path.of("plugins/provider-new.jar").toUri().toURL() };
URLClassLoader pluginLoader = new URLClassLoader(
        jars, DocumentProcessor.class.getClassLoader());

ServiceLoader<DocumentProcessor> loader =
        ServiceLoader.load(DocumentProcessor.class, pluginLoader);
for (DocumentProcessor processor : loader) {
    System.out.println(processor.id());
}
```

You need to import `java.net.URL`, `java.net.URLClassLoader`, `java.nio.file.Path`, and `java.util.ServiceLoader`. When no longer needed, stop the provider, release resources, clear registries/callbacks, and then close the loader. `URLClassLoader.close()` does not guarantee immediate class unloading.

If migrating to JPMS named modules, the contract can declare `module demo.api { exports demo.api; }`, the host can declare `uses demo.api.DocumentProcessor`, the providers can declare `provides demo.api.DocumentProcessor with ...`, and the runtime needs a properly resolved module path/layer. That is a different deployment variant from the class-path service descriptor approach built in this exercise.

## 11. Lifecycle, Security, and Reliability Design

In practice, providers may not only compute over a `String` but also access files, databases, or networks. Additional safeguards are needed:

1. **Versioned contract:** have an API compatibility policy and capability metadata to prevent plugins compiled against an incompatible contract version.
2. **Input validation:** limit document size, encoding, structural depth, paths, or allowed formats.
3. **Resources:** if a provider holds executors/connections, require `start/stop` or `AutoCloseable` and proper reverse-order rollback on startup failure.
4. **Trust boundary:** only load artifacts whose origin, signature/hash, and dependencies have been verified; a class loader is not a sandbox for untrusted code.
5. **Observability:** log provider ID, version, processing duration, errors, and resource usage; do not log sensitive document contents.
6. **Concurrency:** the contract must specify whether a provider is a thread-safe singleton, instance-per-request, or synchronized by the host.
7. **Fallback:** only switch providers automatically when they are confirmed to have the same semantics and data will not be processed twice.

## 12. Acceptance Checklist

- [ ] The contract interface and result record reside in a single `document-api.jar`.
- [ ] Both implementations have no dependency on each other, and each JAR has the exact SPI descriptor.
- [ ] The host only imports package `demo.api`, without importing `demo.word` or `demo.line`.
- [ ] Runs on Java 17+ and stdout matches the guide.
- [ ] When provider-line JAR is removed, provider-word is still discovered.
- [ ] When both providers are missing, the host reports an error and does not continue.
- [ ] When provider IDs collide, the host rejects the duplicate instead of choosing arbitrarily.
- [ ] Version policies, artifact verification, and lifecycle management are planned for real-world deployment.

**Conclusion:** With Java SPI, the host programs against an interface rather than implementations. Two independent providers are packaged and discovered via `ServiceLoader`, allowing the application to extend document-processing functionality without modifying host code. When advancing to dynamically loaded plugins or JPMS, the most important principle remains keeping the shared contract stable, clearly defining capabilities, and managing provider lifecycles.
