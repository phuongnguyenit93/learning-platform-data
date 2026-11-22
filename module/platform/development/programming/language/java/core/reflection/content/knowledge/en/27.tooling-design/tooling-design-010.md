# Classpath Scanning Differs from Introspecting a Known `Class` in Java Reflection

## 1. The foundational question: do we already know *which class*?

When building reflection tools, two tasks are often lumped together as "scanning classes", yet their inputs and scopes are completely different:

- **Introspection of a known `Class<?>`:** the program already holds a `Class` object, such as `Order.class`, `object.getClass()`, or the result of `Class.forName("com.example.Order")`. The job is reading **metadata of that exact type**: name, interfaces, constructors, methods, fields, annotations, superclass, and some generic type info.
- **Classpath scanning:** the program **does not yet have the full list of candidate class names**. It must traverse one or more class sources such as compiled directories, JARs, or other class-supplying mechanisms; from each resource/class found, determine which candidates meet criteria and then optionally use reflection for deeper inspection.

**Reflection does not automatically turn one `Class<?>` into a list of all classes in the application.** `Class.getDeclaredMethods()` only returns methods declared by the inspected type; `Class.getDeclaredClasses()` only returns member classes/interfaces declared directly inside that type, not every class in the same package. There is no standard method `Class.getAllClassesInPackage()` or `ClassLoader.listAllClasses()` for the entire classpath.

For example: if we know `PaymentService.class`, we can read `PaymentService`'s annotations immediately. If we want to find **all classes with `@Handler`** in the application without knowing their names, we must first identify candidate sources (via scanning, registry, build-time metadata, or plugin mechanism), and only then introspect each type.

## 2. Comparing inputs, outputs, and cost

| Aspect | Introspecting a known `Class` | Classpath scanning for candidate classes |
| --- | --- | --- |
| Input | One `Class<?>` object or specified type name | A set of roots: directories, JARs, package prefixes, class loaders, modules, or indexes |
| Goal | Ask "what does this class have?" | Ask "within the chosen scope, which classes match?" |
| Core APIs | `getDeclaredMethods`, `getMethods`, `getDeclaredFields`, `getAnnotations`, `getSuperclass` | `Files.walk`, JAR/resource iteration, module reader, index/framework scanner |
| Scope | One type, or types deliberately navigated from it | Potentially vast numbers of files/entries and types |
| Prerequisites | Type can be referenced or loaded under the appropriate loader | Knowing where to find bytecode/resources; handling each packaging format |
| Output | Metadata, `Method`/`Field`/`Constructor`, access checks | Set of *candidates*; classifying them usually requires reading metadata or loading classes |
| Cost | Typically proportional to the number of members inspected | I/O, entry traversal, filtering, class loader handling, and sometimes loading many classes |
| Typical errors | `NoSuchMethodException`, access permissions, dependency resolution errors | Missing JAR/loader, corrupt classes, duplicate names, misconfigured classpath, overly broad scans |

Classpath scanning **often leads to reflection**, yet the two phases are not equivalent. A good scanner should narrow down candidates before attempting to load classes; and once a class is already identified, operating on that exact `Class<?>` is enough—no rescanning needed.

## 3. How does introspecting a known `Class<?>` work?

Three common ways to obtain a `Class` object:

```java
Class<String> known = String.class;       // Type known at compile time.
Class<?> runtime = "abc".getClass();      // Object known, query runtime type.
Class<?> byName = Class.forName("java.lang.String"); // Binary name known.
```

These are **illustrative snippets** that belong inside a method; `Class.forName` requires handling or declaring `ClassNotFoundException`. The single-argument form also triggers class initialization; to defer initialization in suitable situations, use `Class.forName(name, false, loader)`.

Once you have `Class<?>`, you can inspect:

- `type.getDeclaredMethods()`: methods declared directly in that type, including non-public; excludes inherited methods.
- `type.getMethods()`: public methods visible per API rules, including inherited public methods.
- `type.getDeclaredFields()` and `getDeclaredConstructors()`: directly declared member metadata.
- `type.getAnnotations()` / `getDeclaredAnnotations()` / `isAnnotationPresent(...)`: inspect annotations with `RetentionPolicy.RUNTIME` per API inheritance rules.
- `type.getInterfaces()`, `getSuperclass()`, `isAssignableFrom(...)`: type relationships described by the JVM.

The result is metadata for **one type and the specific relationships queried**. Reading metadata does not imply permission to invoke private methods or access fields across Java Platform Module System (JPMS) boundaries. Furthermore, APIs like `getDeclaredMethods()` sometimes must resolve dependent types in signatures; linkage errors can arise even when you already hold `Class<?>`.

## 4. What does classpath scanning actually have to do?

### Step A — Define search scope

Define candidate sources clearly: a package prefix within application-owned JARs, a build output directory, a dedicated plugin folder, or module configuration. Never scan everything across the JDK, dependencies, application, and all custom loaders by default. A classpath can include multiple entries; **the module path is not identical to the classpath**, and custom class loaders may not expose where bytecode is stored.

### Step B — Enumerate class resources

In a classes directory, a scanner can use `Files.walk(root)` to find `.class` files and convert relative paths into binary names. In a JAR, it can iterate entries via `JarFile`; it must handle directories, `module-info.class`, `package-info.class`, and nested class names containing `$` as intended. For other packaging mechanisms (nested JARs, apps launched via custom launchers, Java modules, runtime images), corresponding adapters are required.

**`ClassLoader.getResources("package/path")` is not a wildcard scan of all classes.** That API finds resources matching **the specified name** from sources visible to the loader. Do not rely on listing package resource URLs to conclude you covered every loadable class. Likewise, `ClassLoader.getDefinedPackages()` does not return a list of all class names.

### Step C — Filter candidates

A scanner can filter paths/class names first, then choose one of two directions:

1. **Read bytecode metadata without loading each class**, via a classfile parsing library or prebuilt index. This approach reduces side effects and the number of loaded classes; you must still mind bytecode versions and supporting classes.
2. **Load classes to inspect via reflection**, e.g., `Class.forName(binaryName, false, chosenLoader)` followed by `isAnnotationPresent` or `isAssignableFrom`. `initialize=false` avoids requesting static initializers to run immediately, **does not guarantee zero effects from loading/linking**, and classes can still fail due to missing dependencies, binary mismatches, or the wrong loader.

Annotations used for runtime discovery must have `@Retention(RetentionPolicy.RUNTIME)` if the scanner filters via reflection. Annotations with `SOURCE` or `CLASS` retention will not necessarily appear via `Class.getAnnotation(...)` at runtime.

### Step D — Decide how to use the results

After selecting matching classes, the tool can store metadata, populate a registry, wire providers, or instantiate objects (if truly required). **Discovering a class does not mean you should instantiate it immediately**: the class may be abstract, lack a suitable constructor, be module-restricted, or have side effects on initialization. Define candidate lifecycle and validity conditions before instantiating.

## 5. Runnable Java 17+ example: introspection then scanning a directory

This example intentionally uses **one well-known output directory** to show the difference. It does not pretend to be a full JAR/module scanner.

Create a single file `ScanVsInspectDemo.java` with no `package` declaration:

```java
import java.io.IOException;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.annotation.ElementType;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.stream.Stream;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface ToolComponent {}

interface Tool {
    String run();
}

@ToolComponent
final class FormatterTool implements Tool {
    public String run() {
        return "format";
    }
}

@ToolComponent
final class ParserTool implements Tool {
    public String run() {
        return "parse";
    }
}

final class NotATool {}

public class ScanVsInspectDemo {
    static void inspectKnownClass() throws NoSuchMethodException {
        Class<FormatterTool> known = FormatterTool.class;
        System.out.println("Known: " + known.getSimpleName());
        System.out.println("Method: "
                + known.getDeclaredMethod("run").getName());
        System.out.println("Implements Tool: "
                + Tool.class.isAssignableFrom(known));
    }

    static void scanOwnedDirectory() throws IOException, ClassNotFoundException {
        Path root = Path.of("out");
        List<String> found = new ArrayList<>();

        try (Stream<Path> files = Files.list(root)) {
            for (Path file : files
                    .filter(Files::isRegularFile)
                    .filter(p -> p.getFileName().toString().endsWith(".class"))
                    .toList()) {
                String fileName = file.getFileName().toString();
                String binaryName =
                        fileName.substring(0, fileName.length() - 6);

                Class<?> candidate = Class.forName(
                        binaryName, false,
                        ScanVsInspectDemo.class.getClassLoader());

                if (candidate.isAnnotationPresent(ToolComponent.class)
                        && Tool.class.isAssignableFrom(candidate)
                        && !candidate.isInterface()) {
                    found.add(candidate.getSimpleName());
                }
            }
        }

        Collections.sort(found);
        System.out.println("Discovered: " + String.join(", ", found));
    }

    public static void main(String[] args) throws Exception {
        inspectKnownClass();
        scanOwnedDirectory();
    }
}
```

Run from the directory containing the source file. Create the output directory and compile (Linux/macOS):

```bash
mkdir -p out
javac -encoding UTF-8 -d out ScanVsInspectDemo.java
java -cp out ScanVsInspectDemo
```

PowerShell (Windows):

```powershell
New-Item -ItemType Directory -Force out | Out-Null
javac -encoding UTF-8 -d out ScanVsInspectDemo.java
java -cp out ScanVsInspectDemo
```

Expected output:

```text
Known: FormatterTool
Method: run
Implements Tool: true
Discovered: FormatterTool, ParserTool
```

**Step-by-step explanation:**

1. `FormatterTool.class` gives us the known `Class` object straight from source; `getDeclaredMethod("run")` locates the exact method on that type. No step needed to list all `.class` files.
2. `Files.list(Path.of("out"))` **lists only direct entries** of an output directory; the code filters `.class` filenames and strips the suffix to form class names because the example sits in the **default package**. With real packages, you must walk subdirectories and convert relative paths into full binary names.
3. `Class.forName(binaryName, false, loader)` retrieves `Class<?>` for each candidate via the application class loader without triggering initializers immediately. For this example's classes, class names match basic filenames because no special layouts or formats are used.
4. `isAnnotationPresent(ToolComponent.class)` drops classes unmarked by `@ToolComponent`; `Tool.class.isAssignableFrom(candidate)` accepts only types implementing the `Tool` contract; `!candidate.isInterface()` excludes interfaces from the candidate set.
5. `Collections.sort(found)` ensures stable output independent of filesystem order. The two discovered classes are `FormatterTool` and `ParserTool`. `NotATool` is neither annotated nor implements `Tool`.

**Intentional limitations:** the example does not scan JARs, nested packages, module paths, other class loaders, or multi-release JARs, and does not handle corrupt classes. It simply illustrates the pipeline `list files → derive names → obtain Class → introspection → filter`. In real tools, pick an appropriate scanner/library and design error handling per source.

## 6. Designing real-world scanners: hard limitations

### Classpath is not a single directory

An application can load classes from many directories and JARs. `java.class.path` only reflects part of the configuration in many environments, and does not fully describe custom class loaders, module layers, or nested JARs. Classes may come from the runtime image (`jrt:`), module path, dynamic sources, or container/framework mechanisms. There is no universal reflection API to "list every class the JVM might ever load".

### Same name does not guarantee same runtime type

Two class loaders can define two classes with the same binary name yet different runtime identities. Checking `candidate.getName()` equality is insufficient to conclude `candidateA == candidateB`. When a scanner loads candidates, it must use the loader matching the plugin/framework boundary; never arbitrarily use the system class loader for every kind of application.

### Metadata, bytecode, and annotations

If you only want to build a **class-name index**, reading bytecode without calling `Class.forName` can be more appropriate. If you need to check subtype relationships or runtime annotations, reflection is useful after filtering names. For annotation metadata, consider `RetentionPolicy`, `@Inherited` (which only applies per rules to annotations on class superclasses), and cases where annotations on an interface do not automatically become annotations on implementing classes.

### Ordering, errors, and reliability

- A corrupt JAR, class compiled with a newer JDK, missing superclass, or unlinkable class can cause `Class.forName` to fail. Record candidate context, loader, and cause; do not silently assume a scan is complete when errors occurred.
- Scans need allowed package/JAR scopes, resource limits, and path-traversal protection outside roots; a directory/JAR supplied by an untrusted party must not be treated as a plugin source authorized to run code.
- Sort results deterministically and define a duplicate-name/classloader policy. Avoid relying on `Files.walk` or JAR entry order to determine provider precedence.
- If the classpath is static, cache indexes or use build-time metadata; do not rescan every JAR on every request. Startup scanning can be slow and I/O-heavy, especially in large applications.
- Do not automatically `newInstance` every discovered class. Select constructors, manage lifecycle, access rights, class visibility, and initialization errors under an explicit contract.

### JPMS, special packaging, and native image

Under JPMS, modules resolved in layers carry their own metadata; `ModuleReader` has an API to list resources inside a module within open scope, yet that is not equivalent to scanning the entire classpath. `exports`/`opens` affect access permissions; finding a class name does not mean deep reflection is allowed.

Spring Boot executable JARs or other frameworks may bundle libraries inside nested JARs. A scanner understanding only `Files.walk` or `file:` URLs will miss those classes. For native-image/closed-world runtimes, reachable types and reflective metadata may need registration or declaration at build time; dynamic JVM-style scanning is generally not guaranteed to work out of the box.

## 7. When to scan vs. when to choose another approach?

| Real need | Appropriate approach |
| --- | --- |
| Read methods/fields/annotations of a known type | Obtain `Class<?>` and use reflection; do not scan classpath |
| Implementations are known at development time | Explicit registry/factory/DI configuration, optionally generated via compile-time annotation processor |
| Discover plugin implementations registered under Java SPI | `ServiceLoader<ServiceType>`; providers declared via `META-INF/services` or module `provides ... with` |
| Build a framework finding all annotated classes by package | Scoped scanner supporting target packaging/class loaders and metadata; consider build-time indexing |
| List existing classes inside a self-managed JAR | Enumerate JAR entries or classfiles; apply filtering criteria; avoid loading every class by default |
| Observe classes already loaded by the JVM | Use appropriate diagnostics/runtime instrumentation; **different** from finding all loadable classes on the classpath |

`ServiceLoader` can perform plugin discovery without scanning every `.class` file manually, though **it only discovers providers registered under the SPI contract**. Dependency injection frameworks have their own component scanning/metadata/indexing mechanisms; do not confuse those mechanisms with raw `Class` reflection APIs.

## 8. How to decide and self-check

Ask in order:

1. **Does the input already provide a `Class<?>` or concrete object?** If so, query that exact type's metadata first.
2. **Do we need to discover previously unknown class names?** If so, define permitted sources and discovery mechanism (SPI, registry, build index, scanner).
3. **Must we support directories, JARs, nested JARs, or modules?** Pick a mechanism suited to the deployment environment; do not treat a `Files.list` example as a universal solution.
4. **Do classes need to be loaded/initialized while scanning?** Prefer filtering metadata first; if using `Class.forName`, consider `initialize=false` and error-handling policy.
5. **How will results be used?** Reading metadata, registering handlers, or creating instances? Each step has different requirements for constructors, access rights, lifecycle, and safety.

**Question 1.** You have `UserService.class` and only want its list of `public` methods. Do you need classpath scanning?

**Answer:** No. Use `UserService.class.getMethods()`; if you only want directly declared methods, use `getDeclaredMethods()`.

**Question 2.** Does calling `MyType.class.getDeclaredClasses()` find every class in package `com.example`?

**Answer:** No. It describes member types declared directly inside `MyType`, without traversing packages or the classpath.

**Question 3.** Code calls `ClassLoader.getResources("com/example")` and gets two URLs. Can we conclude all classes in that package were found?

**Answer:** No. The API looks up resources matching the requested name; loaders and packaging determine enumerability. Two URLs do not prove coverage of classes inside nested JARs, custom loaders, or other modules.

**Question 4.** To discover implementations published as SPI providers, must you manually walk all `.class` files?

**Answer:** No. `ServiceLoader` leverages Java's standard provider registration. Only when you must find unregistered classes matching custom criteria should you consider an appropriate scanner.

**Question 5.** Does `Class.forName(name, false, loader)` strictly guarantee zero errors and zero runtime effects?

**Answer:** No. It avoids requesting class initialization during that call, yet class loading/linking and resolution can still raise errors; later on the class may still have to be initialized.

**Conclusion:** **Introspection answers "what does this type have?"**, whereas **classpath scanning answers "which candidate types exist in the chosen sources?"**. Reflection is the tool for inspecting metadata once you have `Class<?>`; scanners/registries/SPI are the mechanisms for identifying which types to inspect. Choosing the right layer keeps tools fast, scoped, and reliable across Java packaging formats.