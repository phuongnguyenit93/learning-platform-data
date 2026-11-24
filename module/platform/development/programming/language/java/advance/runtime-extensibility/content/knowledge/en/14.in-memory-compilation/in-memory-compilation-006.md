# Keying Results by Source Code, Options, and Dependencies to Manage Compilation Caches

## 1. Goals and Correctness Conditions of a Compilation Cache

When a Java application receives source code at runtime, it can use `javax.tools.JavaCompiler` and `JavaFileManager` to compile `.java` into `.class` in RAM. If the same request arrives repeatedly (rule engines, code playgrounds, scripting, plugin generators), recompiling from scratch increases CPU usage, memory allocation, and latency. A **compilation cache** retains successful compilation results and reuses them.

However, "unchanged source code" **is not enough** to permit a cache hit. The output can depend on `javac` options, discovered libraries/modules, annotation processors, auxiliary source files, the compiler implementation, and the JDK version. A cache key missing any input can return stale bytecode even though the request changed.

Two properties must be maintained:

- **No false hits:** two requests with the same key must be equivalent with respect to the outputs the cache promises to supply. A false hit can cause runtime crashes, wrong results, or data leaks.
- **Avoid unnecessary false misses:** two equivalent requests should share the same key. A false miss wastes resources, though it typically does not produce wrong results.

Example:

~~~text
Compile #1:
  source: Rule.java calls Api.LIMIT
  options: --release 17 -proc:none
  dependency: api.jar has LIMIT = 10
  → output A → cached under K1

Compile #2:
  source/options remain identical
  dependency: api.jar changes, LIMIT = 20
  → DO NOT reuse K1 if the dependency fingerprint reflects the changed bytes.

Compile #3:
  all source/options/dependencies/toolchain identical to #1
  → output A can be served from cache without invoking the compiler.
~~~

**Lesson goals:** build a key identifying source code, options, and dependencies; understand the structure of `JavaCompiler` outputs; implement fingerprinting/invalidation; control concurrent compilation; and separate bytecode caching from class loading.

## 2. Choose the Cache Unit Before Building the Key

A single source `Outer.java` can produce multiple `.class` files (nested/anonymous classes). A multi-source batch can have mutual dependencies; annotation processors can also emit sources/resources. Therefore, you should not assume the cached value is always a single `byte[]` for the main class.

| Cache scope | Inputs required in key | Stored results | When to choose |
| --- | --- | --- | --- |
| Single simple source | Logical name + source text + compile environment | **All** emitted class files | Standalone rule with no external source dependencies |
| Multi-source batch | All source units, options, dependencies | Class map and generated outputs of the batch | Sources referencing one another |
| JPMS module | Sources + `module-info.java` + module path + resolution config | Entire module output | Modular plugins |
| Incremental graph | Dependency/symbol graph and per-node fingerprints | Per-node/per-module results | Large build services with accurate tracking |

**Starting recommendation:** cache the **entire compilation request**; when any input in the request changes, recompile the whole request. Only move to per-class incremental compilation after verifying dependency closure, constant inlining, annotation processing, and classpath visibility.

Distinguish three concepts:

- `CompilationRequest`: everything the compiler actually consumes.
- `CompilationArtifact`: bytecode map, generated resources, and metadata needed for reuse.
- `RuntimeGeneration`: class loader/layer defining classes from the artifact. Two generations can use the same cached bytecode while defining distinct runtime `Class<?>` objects.

## 3. Safe Cache Key Formula

A general form:

~~~text
key = SHA-256(
    canonicalEncode(
        cacheSchemaVersion,
        compilerIdentity,
        platformIdentity,
        sourcesSortedByLogicalPath,
        effectiveOptionsInSemanticOrder,
        dependencyArtifactsInLookupOrder,
        annotationProcessorInputs,
        relevantEnvironment
    )
)
~~~

The key phrase is **canonicalEncode**: encoding with explicit field boundaries, versioning, and deterministic ordering. Never concatenate strings with `a + b + c` without length prefixes: the parts `"ab","c"` and `"a","bc"` yield the same string `"abc"`. You can use a binary encoding that writes field count + byte length + UTF-8 bytes, or canonical JSON normalized under strict rules.

### 3.1. Required Inputs to Consider

| Input | Impact | Suitable fingerprint |
| --- | --- | --- |
| Source unit name + source content | Package, declarations, symbols, diagnostics | Logical path/binary name + SHA-256 of exact content |
| Batch source set | Type resolution and generated classes | Sort by logical path, hash each content |
| `--release`, debug, `-parameters`, `-Xlint` | Bytecode target/metadata/diagnostics | Effective compiler option tokens |
| Classpath/module path | Classes, methods, constants, module visibility | Ordered entries: identity + content digest |
| Sourcepath/implicit sources | Compiler may implicitly read/compile other sources | Fingerprint all sources actually permitted to be read |
| Processor path and `-A` options | Generated sources/classes/resources | Processor artifacts/dependencies/config/deterministic inputs |
| Compiler provider/JDK build | Toolchain may emit different outputs | Compiler ID/vendor/exact version/schema |
| Influential environment | Charset, processor-read files/env/clock | Explicit configuration or **non-cacheable** |

If caching diagnostics as well, include inputs affecting error formatting (such as locale or source URI) and warning policies. If caching **only** bytecode, you may omit certain inputs that do not affect bytecode **if proven**; by default, a conservative fingerprint is safer.

### 3.2. Input Manifest

This is a **conceptual representation template**, not a JDK API, and the digests are placeholder values:

~~~json
{
  "schema": "java-inmem-compilation/v1",
  "compiler": {
    "implementation": "javac",
    "vendor": "recorded-vendor",
    "build": "recorded-exact-build"
  },
  "sources": [
    {"path": "com/example/Rule.java", "sha256": "digest-of-actual-source"}
  ],
  "options": ["--release", "17", "-proc:none", "-parameters"],
  "classpath": [
    {"order": 0, "id": "api.jar", "sha256": "digest-of-actual-jar"}
  ],
  "modulepath": [],
  "processors": [],
  "environment": {"policy": "controlled"}
}
~~~

In a real implementation, populate digests from the actual bytes used, fix how each field is represented, and **version the schema**. Storing the manifest alongside the key helps explain cache misses: which source, option, dependency, or JDK changed.

## 4. Source Code: Hash Exactly What the Compiler Reads

### 4.1. Sources as Strings or Bytes

With `SimpleJavaFileObject.getCharContent(...)` receiving a Java `String`, you can hash the UTF-8 content of the exact string the compiler uses. For files on disk, pick an explicit charset and hash **the content after any required preprocessing steps have occurred**.

Example pipeline:

~~~text
template + user input
     ↓ validate/normalize per published policy
generated source String
     ↓ compute key from exact String + template/transform config
JavaFileObject.getCharContent()
     ↓
JavaCompiler
~~~

If code has imports injected, packages rewritten, macros expanded, or source generated from a template, **hash the post-transform source** or hash both the transform version and its inputs. Hashing the original source while compiling the modified source invites false hits.

Do not arbitrarily `trim()`, strip comments, normalize line endings, or normalize Unicode merely to boost hit rates. Those changes can affect source positions, diagnostics, Unicode escapes, or annotation processing tools. Only hash normalized text if the compiler actually receives that normalized text.

### 4.2. Logical Source Name Is a Separate Input

The source `com.example.Rule` is commonly represented by the URI `string:///com/example/Rule.java`. The filename/URI can affect diagnostics, public top-level type rules, and source lookup. Thus a source fingerprint should be a pair:

~~~text
logicalPath = com/example/Rule.java
contentDigest = SHA-256(UTF-8 of exact source String)
~~~

Do not infer class names with regex alone on arbitrary source: comments, Unicode escapes, nested classes, and multiple top-level types can break regex. Require the caller to supply the logical unit name or use a consistent parser/contract.

### 4.3. Multi-File Batches Must Include the Whole Set

If the compiler receives `Policy.java` and `Rule.java`, editing `Policy.java` can change the output of `Rule.java` even if `Rule.java` itself is unchanged. The batch key must fingerprint both. Sort source units by logical path so `HashMap` iteration order does not cause false misses; reject duplicate logical paths as ambiguous. **Do not sort classpath/options this way**, because their order can carry meaning.

### 4.4. Which Hashes Are Unsuitable?

- `File.lastModified()`: files overwritten within the same timestamp granularity or preserving mtime.
- File size: different content can have the same length.
- `String.hashCode()`: a 32-bit hash is insufficient as a safe content-addressed key.
- JAR names, Maven coordinates, paths: do not guarantee identical bytes.
- SHA-256 of a **canonical manifest covering all inputs**: the practical choice.

Do not use a hash to conclude an artifact is "trusted": multi-tenant caches still need permission, namespace, integrity, and provenance checks.

## 5. Compiler Options: Use Effective Configuration, Not a Few UI Checkboxes

`JavaCompiler.getTask(...)` accepts a list of option tokens. To construct the key, capture the **final options the adapter passes to the compiler**, after applying all defaults, policies, and overrides. Groups easily missed:

- **Target and platform:** `--release 17`; or `-source/-target` combined with corresponding platform configuration. `--release` cannot be used together with `-source/-target`.
- **Bytecode metadata:** `-g`/`-g:none`, `-parameters`, source level; some warning options can affect diagnostics or pass/fail status when combined with `-Werror`.
- **Symbol resolution:** `--class-path`/`-cp`, `--module-path`, `--module-source-path`, `--source-path`, `--patch-module`, `--add-modules`, `--add-exports`, and related flags in valid modes.
- **Annotation processing:** `-proc:none`, `-processor`, `--processor-path`, `--processor-module-path`, `-Aname=value`.
- **Encoding:** `-encoding` for byte-based file sources; custom file managers may supply already-decoded char content.
- **Compiler plugins:** compiler extensions, file manager settings, and version adapters.

**Preserve the order of option tokens** initially so you do not discard the semantics of repeated options and path ordering. If you want to canonicalize `-cp` and `--class-path` into one form, prove that the specific compiler treats them identically, and fingerprint **the contents** of the artifacts referenced by those options.

Avoid implicit defaults from the current working directory or `CLASSPATH`: they can make a request "look identical" while the compiler sees different classes. Set classpath/modulepath explicitly, or fingerprint the actual defaults. `JDK_JAVAC_OPTIONS` affects the `javac` command launcher; do not assume the `JavaCompiler` API reads it in the same way automatically.

**Important point:** `--release 17` does not guarantee identical bytecode across every compiler/JDK build, even with the same API target. Include compiler/toolchain identity in the key.

## 6. Dependencies: Hash the Content of the Entire Compile-Visible Graph

### 6.1. A JAR Can Change While Its Path Stays the Same

~~~text
--class-path lib/api.jar

First run:  lib/api.jar contains Api.VERSION = 1
Next run:   same path, but JAR contains Api.VERSION = 2
~~~

If the key stores only `"lib/api.jar"`, the cache can return stale bytecode. The Java compiler can **inline** compile-time constants such as `public static final int`. Thus, even a change solely inside a classpath JAR with unchanged source code may require recompilation.

Hash the **actual JAR bytes**. If ZIP timestamps/metadata differ while classes are unchanged, whole-file digests cause a safe false miss. Move to ABI hashing only after building an accurate model of class ABIs, constants, annotations, and processors.

### 6.2. Classpath Order Cannot Be Arbitrarily Sorted

With two JARs both containing `com.example.Api`, the compiler picks the class according to classpath lookup behavior. Swapping the order:

~~~text
[api-v1.jar, api-v2.jar]
[api-v2.jar, api-v1.jar]
~~~

can yield different results. In the manifest, each entry should have a **logical artifact identity, lookup ordinal, and content digest**. Do not sort by JAR name to "canonicalize", as that can collapse two distinct inputs into the same key.

### 6.3. Direct and Transitive Dependencies

`JavaCompiler` can read superclasses, generic bounds, interface methods, annotations, module metadata, static constants, package classes, and auxiliary sources—not only classes listed in `import` statements. Hashing only "directly imported JARs" is therefore insufficient.

The sound starting point is fingerprinting **the entire effective classpath/modulepath/sourcepath accessible to the task**, including transitive JARs. This is a **safe superset**, though it may cause misses when unrelated libraries change. Incremental optimization based on a symbol dependency graph is an advanced problem; do not just scan `import` text.

### 6.4. Classpath Directories and In-Memory Dependencies

If a dependency is a directory like `build/classes`, hash the files inside by **relative path + content digest**; hashing the folder name or folder `lastModified` is insufficient. For modular code, also consider `module-info.class` and resolution configuration.

If the compiler reads dependency bytecode from a **MemoryFileManager** or in-memory class map, the key must hash the exact `byte[]` arrays the file manager supplies to the compiler. Use the same fingerprinting discipline for persisted JARs and in-memory dependencies, recording explicit identities and lookup order to avoid collisions across sources.

### 6.5. Processor Paths and External Inputs

Annotation processors can generate classes, sources, and resources based on:
- the processor's implementation JAR and its dependencies;
- `-A` options, annotations, resources, config files;
- the filesystem, env vars, clock, randomness, network.

If you cannot identify and snapshot every input a processor is allowed to read, mark the request **non-cacheable** or run the processor in a constrained/deterministic environment. Processors are code executed at compile time; running untrusted processors inside the host JVM itself requires safety evaluation.

In the runnable example below, `-proc:none` is used to exclude processors from the main flow.

## 7. JDK/Toolchain Identity and Reproducibility

A cache key should record a toolchain ID, for example:

~~~text
compiler implementation/provider: javax.tools JavaCompiler implementation
java.vendor
java.runtime.version
compile adapter schema/version
--release / platform configuration
processor plugins and their versions
~~~

Using exact version/build is **conservative but correct**; changing a JDK patch can cause a miss even if the resulting bytecode is identical. Avoid hashing every environment variable since many are irrelevant, lowering hit rates and potentially leaking secrets. Any external input actually read by a processor must be declared and fingerprinted, or caching must be disabled for that request.

`ToolProvider.getSystemJavaCompiler()` can return `null` if the runtime image does not provide a JDK compiler; production code must handle that case. If using the Eclipse compiler or another custom provider, do not share a key namespace with `javac` unless output compatibility is strongly verified.

If the cache includes formatted diagnostics, then locale, source URIs, and warning/error policies must be explicitly keyed. A successful compilation does not mean diagnostics can be unconditionally reused across different tenants.

## 8. Canonicalization, Lookup, and Cache Storage Flow

~~~text
CompileRequest
    │
    ├── Validate logical names, policy, options
    ├── Materialize exact source bytes/text
    ├── Resolve and snapshot real dependency artifacts
    ├── Build effective compiler options/toolchain fingerprint
    │
    ▼
Canonical manifest → SHA-256 → cache key
    │
    ├── HIT → verify schema/integrity → immutable CompilationArtifact
    │
    └── MISS → single-flight → JavaCompiler + MemoryFileManager
                   │
                success?
                 /    \
               no      yes
               │        │
       diagnostics,     snapshot ALL bytecode and generated outputs
       no success       validate → atomic publish
       cache record         │
                            ▼
                      CompilationArtifact
                            │
                  Runtime ClassLoader generation
~~~

**The snapshot must be consistent.** If one thread computes the SHA-256 of `api.jar` and then the file on disk is overwritten before the compiler reads it, the key describes bytes A while the output is compiled from bytes B. Prevent this with immutable content-addressed artifacts, copying a snapshot and compiling from that snapshot, or proper locking/versioning/integrity mechanisms. Avoid using the same mutable path for both steps without control.

### Things NOT to Put in the Key

- `createdAt` and `lastAccessAt`: used for eviction, not compilation inputs.
- Random request IDs that do not affect the compiler: causes every lookup to miss.
- Absolute temporary directory paths if invisible to the compiler and not part of the diagnostic contract.
- ClassLoader generation ID when **caching only compiled bytes**; the same bytes can be loaded into different generations.
- Raw secrets or unnecessary user data; if tenant isolation is needed, enforce namespaces/permissions at the storage layer.

## 9. Runnable Java 17+ Example: Keying and Caching Bytecode in RAM

The following example compiles a single source `demo.Hello` without external libraries; `-proc:none` disables annotation processing. `JavaCompiler` emits `.class` files in RAM via `ForwardingJavaFileManager`; a `Cache` retains byte arrays keyed by a length-prefixed SHA-256 fingerprint.

### 9.1. File CompileCacheDemo.java

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

import javax.tools.DiagnosticCollector;
import javax.tools.FileObject;
import javax.tools.ForwardingJavaFileManager;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileManager;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class CompileCacheDemo {
    static final class SourceUnit extends SimpleJavaFileObject {
        private final String content;

        SourceUnit(String binaryName, String content) {
            super(URI.create("string:///" + binaryName.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.content = content;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return content;
        }
    }

    static final class ClassBytes extends SimpleJavaFileObject {
        private final ByteArrayOutputStream output = new ByteArrayOutputStream();

        ClassBytes(String binaryName, Kind kind) {
            super(URI.create("mem:///" + binaryName.replace('.', '/')
                    + kind.extension), kind);
        }

        @Override
        public OutputStream openOutputStream() {
            return output;
        }

        byte[] snapshot() {
            return output.toByteArray();
        }
    }

    static final class MemoryFileManager
            extends ForwardingJavaFileManager<StandardJavaFileManager> {
        private final Map<String, ClassBytes> outputs = new LinkedHashMap<>();

        MemoryFileManager(StandardJavaFileManager delegate) {
            super(delegate);
        }

        @Override
        public JavaFileObject getJavaFileForOutput(
                JavaFileManager.Location location,
                String className,
                JavaFileObject.Kind kind,
                FileObject sibling) throws IOException {
            if (kind != JavaFileObject.Kind.CLASS) {
                return super.getJavaFileForOutput(
                        location, className, kind, sibling);
            }
            ClassBytes target = new ClassBytes(className, kind);
            outputs.put(className, target);
            return target;
        }

        Map<String, byte[]> classSnapshots() {
            Map<String, byte[]> result = new LinkedHashMap<>();
            outputs.forEach((name, file) -> result.put(name, file.snapshot()));
            return result;
        }
    }

    static Map<String, byte[]> deepCopy(Map<String, byte[]> data) {
        Map<String, byte[]> copy = new LinkedHashMap<>();
        data.forEach((name, bytes) -> copy.put(name, bytes.clone()));
        return copy;
    }

    static void field(DataOutputStream out, String text) throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        out.writeInt(bytes.length);
        out.write(bytes);
    }

    static String sha256(byte[] input) throws Exception {
        return HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(input));
    }

    static String key(String binaryName, String source,
                      List<String> options, List<String> dependencies)
            throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK compiler unavailable");
        }

        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(bytes)) {
            field(out, "java-inmem-compile-cache/v1");
            field(out, compiler.getClass().getName());
            field(out, System.getProperty("java.vendor"));
            field(out, System.getProperty("java.runtime.version"));
            field(out, binaryName);
            field(out, source);

            out.writeInt(options.size());
            for (String option : options) {
                field(out, option);
            }

            out.writeInt(dependencies.size());
            for (String dependency : dependencies) {
                field(out, dependency);
            }
        }
        return sha256(bytes.toByteArray());
    }

    static Map<String, byte[]> compileOnce(
            String binaryName, String source, List<String> options)
            throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK compiler unavailable");
        }

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (MemoryFileManager fileManager = new MemoryFileManager(
                compiler.getStandardFileManager(
                        diagnostics, Locale.ROOT, StandardCharsets.UTF_8))) {
            Boolean success = compiler.getTask(
                    null, fileManager, diagnostics, options, null,
                    List.of(new SourceUnit(binaryName, source))).call();

            if (!Boolean.TRUE.equals(success)) {
                throw new IllegalStateException(
                        "Compile failed: " + diagnostics.getDiagnostics());
            }
            return fileManager.classSnapshots();
        }
    }

    // Single-threaded example. Add concurrency/eviction for production.
    static final class Cache {
        private final Map<String, Map<String, byte[]>> entries = new HashMap<>();
        private int compilerCalls;

        Map<String, byte[]> compile(
                String binaryName, String source, List<String> options,
                List<String> dependencyFingerprints) throws Exception {
            String fingerprint = key(
                    binaryName, source, options, dependencyFingerprints);
            Map<String, byte[]> existing = entries.get(fingerprint);
            if (existing != null) {
                System.out.println("HIT");
                return deepCopy(existing);
            }

            Map<String, byte[]> generated =
                    compileOnce(binaryName, source, options);
            entries.put(fingerprint, deepCopy(generated));
            compilerCalls++;
            System.out.println("MISS");
            return deepCopy(generated);
        }
    }

    public static void main(String[] args) throws Exception {
        String source = "package demo; public class Hello { "
                + "public static int twice(int x) { return x * 2; } }";
        String changed = source.replace("x * 2", "x * 3");
        List<String> options = List.of("--release", "17", "-proc:none");
        List<String> withParameters = List.of(
                "--release", "17", "-proc:none", "-parameters");

        Cache cache = new Cache();
        Map<String, byte[]> first =
                cache.compile("demo.Hello", source, options, List.of());
        Map<String, byte[]> again =
                cache.compile("demo.Hello", source, options, List.of());
        cache.compile("demo.Hello", changed, options, List.of());
        cache.compile("demo.Hello", source, withParameters, List.of());

        System.out.println("same bytes=" + Arrays.equals(
                first.get("demo.Hello"), again.get("demo.Hello")));
        System.out.println("compiler calls=" + cache.compilerCalls);

        // Fingerprints below are ONLY a key-change illustration.
        // They are not real JAR digests and are not compilation inputs.
        String depA = sha256("api-v1".getBytes(StandardCharsets.UTF_8));
        String depB = sha256("api-v2".getBytes(StandardCharsets.UTF_8));
        boolean dependencyKeyChanged =
                !key("demo.Hello", source, options, List.of("api:" + depA))
                .equals(key("demo.Hello", source, options,
                        List.of("api:" + depB)));
        System.out.println("dependency key changed=" + dependencyKeyChanged);
    }
}
~~~

Commands in the directory containing the file, on a machine with **JDK 17+**:

~~~powershell
javac --release 17 -encoding UTF-8 CompileCacheDemo.java
java CompileCacheDemo
~~~

Expected stdout for the program:

~~~text
MISS
HIT
MISS
MISS
same bytes=true
compiler calls=3
dependency key changed=true
~~~

**Why do four calls cause three compilations?**

1. First request: key does not exist yet → `MISS`; compiler is invoked.
2. Second request: identical source + options + toolchain + dependency list → `HIT`, returns copied bytecode from cache.
3. Third request: method body changed from `x * 2` to `x * 3` → different source → `MISS`.
4. Fourth request: original source, `-parameters` enabled → different options → `MISS`.
5. The two strings `api-v1`/`api-v2` **only illustrate that different dependency fingerprints produce different keys**; this example does not compile against an external JAR. In production, `dependencyFingerprints` must be computed from the **actual artifacts visible to `JavaCompiler`**.

The `javac` command creates `CompileCacheDemo.class` and nested classes of the **demo program** on disk. The `demo.Hello` source is compiled in RAM; `MemoryFileManager` holds `demo.Hello` bytecode in `Map<String,byte[]>` without writing `demo/Hello.class` to the filesystem.

### 9.2. Role of Each Class

- `SourceUnit`: uses `SimpleJavaFileObject` with a logical `.java` URI and supplies a `CharSequence` from `String`.
- `ClassBytes`: `SimpleJavaFileObject` representing `.class` output, receiving bytes via `openOutputStream()`.
- `MemoryFileManager`: `ForwardingJavaFileManager` preserving the standard manager's dependency lookup and overriding `getJavaFileForOutput` to capture outputs in RAM.
- `Cache`: key → complete class map; clones `byte[]` on store/return so callers cannot mutate cached data.
- `key`: length-prefixed encoding including compiler/JDK identity, source, ordered options, and dependency fingerprints, then hashed with `MessageDigest SHA-256`.
- `compileOnce`: invokes `JavaCompiler.getTask`, collects diagnostics, and returns the artifact only when `call()` succeeds.

**Intentional limitations:** the program is single-threaded, one source per request, with no annotation processors, external dependencies, disk cache, or class loading. To support multiple sources, pass a list of `JavaFileObject`, hash all sources with their logical paths, and retain all generated outputs. If annotation processing is enabled, capture any additional output kinds produced by processors (including `getFileForOutput` for resources). Use this code only as a learning foundation; do not claim complete classpath caching while the dependency list remains empty.

## 10. Properly Hashing JARs and Directory Outputs

### 10.1. Illustrative Snippet for Hashing a JAR (Not Standalone Runnable)

~~~java
static String digestJar(java.nio.file.Path jar) throws Exception {
    java.security.MessageDigest digest =
            java.security.MessageDigest.getInstance("SHA-256");
    try (java.io.InputStream in = java.nio.file.Files.newInputStream(jar)) {
        byte[] buffer = new byte[8192];
        int count;
        while ((count = in.read(buffer)) != -1) {
            digest.update(buffer, 0, count);
        }
    }
    return java.util.HexFormat.of().formatHex(digest.digest());
}
~~~

If `--class-path` is a list of JARs, record entries in exact lookup order:

~~~text
ClasspathEntry(kind=JAR, order=0, logicalId=api.jar, sha256=...)
ClasspathEntry(kind=JAR, order=1, logicalId=util.jar, sha256=...)
...
~~~

For directories containing classfiles, build a manifest of **relative path + SHA-256 of file content** for every entry readable by the compiler; sort by relative path and hash the manifest. Never use directory modification time as a fingerprint. When using symlinks or mounts, establish explicit resolution/snapshot rules; if the classpath mutates concurrently, hashing and compilation can become inconsistent.

### 10.2. Path Changes vs. Content Changes

A JAR with identical bytes placed in a new temporary path can share the same content fingerprint. However, if the path is written into outputs/diagnostics, affects resource/package lookup, or is read by a processor, the path remains an input to manage. **Do not discard paths unconditionally**; record a logical ID and path policy sufficient for the compiler to read the right sources and the system to decide which requests are equivalent.

### 10.3. Compile-Time ABI and Constants

Hashing only public method signatures is sometimes not enough. For example:

~~~java
// API dependency v1
public static final int MAX = 10;

// API dependency v2
public static final int MAX = 20;
~~~

These two snippets are **illustrative, not two standalone Java files**. If a caller compiles `return Api.MAX;`, the compiler can inline the constant value into bytecode. Even though the field signature is identical, the output depends on the value. Advanced ABI hashing must account for constants, generic signatures, annotations, visibility, hierarchy, modules, and anything observable by processors. **Hashing the entire JAR** is usually simpler and safer.

## 11. Invalidation: Which Input Changes Cause a Cache Miss?

| Event | Result under conservative key | Why |
| --- | --- | --- |
| Source text changes | **MISS** | Compiler receives new content |
| Source mtime changes, bytes unchanged | HIT if mtime has no effect | Do not hash pure filesystem metadata |
| Source added/removed in batch | **MISS** | Symbol table/output changes |
| Source collection order shuffled meaninglessly | HIT if canonically sorted | Logical units are unchanged |
| `--release 17` changed to `--release 21` | **MISS** | Language/platform/target changed |
| `-parameters` enabled or debug flags changed | **MISS** | Classfile metadata differs |
| JDK/compiler provider/version changed | **MISS** under conservative policy | Toolchain may produce different output |
| JAR at same path has new bytes | **MISS** | Classes/methods/constants changed |
| Effective classpath order swapped | **MISS** | Class resolution may differ |
| Unrelated JAR changed on full path | MISS under whole-path model | Safe false miss; optimize later |
| Processor JAR/options/auxiliary inputs changed | **MISS** or non-cacheable | Generated classes/resources change |
| Process restarts, inputs/toolchain unchanged | Can HIT in persistent cache | Only if schema and integrity are valid |
| New loader generation, old bytecode inputs | Compile cache can HIT | Runtime `Class` needs a new loader |
| Cache TTL expires | Recompile once entry is evicted | TTL manages storage, not fingerprints |

You must distinguish **content-based cache invalidation** from **time/capacity-based eviction**. A TTL does not fix a key missing a dependency; a live entry within TTL can still be stale if a JAR changed without being reflected in the key.

## 12. Cache Values, Integrity, and Negative Caching

A sufficient success entry:

~~~text
CompilationArtifact
  key and schema version
  compiler/platform identity
  source/option/dependency manifest for debugging
  status = SUCCESS
  classes: Map<binaryName, immutable byte[]>
  generatedSources/generatedResources (if required by contract)
  diagnostics (if keyed and safe to reuse)
  artifact/blob digest for integrity
  createdAt, lastAccessAt, sizeBytes (eviction metadata)
~~~

**Do not store only the main class.** If compilation produces `Outer$Nested.class`, missing it can make the class loader throw `NoClassDefFoundError` when the program uses the nested class. Generated resources from annotation processors can also affect runtime plugins.

**Do not rely on `Map.copyOf` to make `byte[]` immutable:** the map forbids adds/removes, but the arrays inside remain mutable. Use defensive copies, immutable blob storage, or a policy that never hands mutable byte arrays directly to plugins.

**Do not record a compilation failure as a success entry.** Failures can stem from invalid source, temporarily missing dependencies, file manager/I/O issues, or timeouts. If negative caching is desired, cache only genuinely deterministic errors under the full key with a short TTL, separated from transient errors. Isolate diagnostics per tenant to avoid exposing another user's source information.

**Integrity when reading persistent/distributed caches:** verify schema, namespace/permissions, output blob digests, and manifests. Content digests reduce corruption risk, though an attacker could replace both manifest and blob without access controls; signatures or trusted provenance remain necessary per security policy.

## 13. Concurrency: Avoiding Duplicate Compiles and Incomplete Publishes

If two requests arrive with the same key while the cache has no entry, both might compile the same source independently. That is not incorrect, but it wastes resources. Use **per-key single-flight**, such as a `ConcurrentHashMap<Key, CompletableFuture<CompilationArtifact>>` or a cache library with clear compute-once semantics.

~~~text
Request A ----\
               +--- fingerprint K --- inFlight[K] --- single compilation task
Request B ----/                               |
                                          completed artifact
                                          /             \
                                        A receives     B receives
~~~

This is a **design diagram**, not standalone runnable Java. Ensure that:

1. Locking/in-flight tracking is **per exact key** and does not force two different keys to share a compile.
2. Completion is published only after `JavaCompiler` finishes and all outputs are snapshotted.
3. Failures/cancellations propagate; remove failed futures per policy so exceptions are not cached forever.
4. Concurrent compiles, CPU, heap, and execution time are bounded.
5. One mutable `JavaFileManager` is never shared across concurrent tasks by default; each task has its own state or proper synchronization.
6. One waiter timing out does not necessarily cancel a task serving another waiter.
7. Before storing the artifact, re-verify consistency if inputs could mutate between fingerprinting and compilation.

A `HashMap` as in the demo is **sequential-only**. In production, a concurrent cache, per-key coordination, and immutable artifacts are mandatory design elements.

## 14. A Bytecode Cache Is Not a ClassLoader Cache

A loader that has already defined binary name `demo.Rule` from v1 bytes cannot simply call `defineClass` again on that name with v2 bytes to create a new class identity. The JVM binds a runtime class to **(binary name, defining loader)**.

To swap in a newly compiled plugin/rule:

~~~text
source/options/dependency input → compile key → bytecode map
                                                |
                        ┌───────────────────────┴───────────────────┐
                        ▼                                           ▼
                generation loader A                         generation loader B
                  Rule.class v1                                Rule.class v2
                        │                                           │
                   old requests                                new requests
                        └────────── drain/stop/release ─────────────┘
~~~

Bytecode for the same key can be used in **two different new loaders**, though that does not mean the `Class<?>` objects share identity. Do not cache `Class<?>` or `ClassLoader` together with bytecode without a well-defined generation lifecycle: such caches can retain strong references to old class loaders, leaking Metaspace and retaining threads/resources.

`URLClassLoader.close()` (if used) releases loader resources without forcing immediate class unloading. `ServiceLoader.reload()` clears the service loader's provider cache, and likewise **does not** recompile source bytecode or alter already-loaded classes.

## 15. Testing and QA Workflow

| Test | Setup | Expected result |
| --- | --- | --- |
| Identical repeated input | Compile twice with identical source/options/deps/toolchain | HIT on second run, compiler calls = 1 |
| Source changes one literal | Change `x * 2` to `x * 3` | MISS; corresponding bytecode |
| Same source length | Change content while keeping character count identical | MISS; length is not used as key |
| Mtime preserved, JAR changed | Replace API JAR with different bytes | MISS |
| Classpath order swapped | Two JARs containing the same class name | MISS, accurate resolution |
| Transitive dependency changed | Change constant/method in an indirect library | MISS |
| Compiler options changed | `--release`, `-parameters`, or processor flags changed | MISS |
| Annotation processor reads auxiliary input | Change processor config/resource | MISS or non-cacheable |
| Compiler/toolchain upgraded | JDK patch/build/vendor changes | MISS per policy |
| Source batch adds nested class | Compiler emits multiple class outputs | Cache retains all `.class` files |
| Missing dependency | Remove a required classpath JAR | Never returns stale success; compile error reflects new input |
| Concurrent same key | 20 simultaneous requests | Only one compilation, same intact artifact |
| Compile error | Source has syntax errors | No success entry created |
| Cache blob corruption | Mutate cached bytes | Integrity check rejects, recompiles |
| Eviction | Evict cache entry by quota/TTL | Subsequent request recompiles cleanly |
| New runtime generation | Same binary name v1 then v2 | New loader; never redefined in old loader |

**Extended Lab A — Unchanged dependency path:** compile `return Api.LIMIT;` against a dependency containing `public static final int LIMIT = 10`; replace the JAR at the same path with a version having `LIMIT = 20`. Compare a path-only cache against a JAR-bytes cache to observe the stale constant risk.

**Extended Lab B — Single batch:** compile `Policy.java` and `Rule.java` together; modify only `Policy.java` and confirm the batch key changes even though `Rule.java` text is unchanged.

**Extended Lab C — Determinism:** shuffle the source collection order randomly while sorting the canonical source manifest by logical path; verify the key stays unchanged. Swap **classpath order** and confirm the key changes.

**Extended Lab D — Benchmarking:** run N requests with K unique fingerprints, measuring hit rate = hits / lookups, compiler calls, p95/p99 compile latency, cached bytes, heap/Metaspace, and evictions. Never "optimize" hit rate by dropping dependency inputs.

## 16. Mistakes to Avoid

### 16.1. Hashing Only Source Code

Identical source with different compiler versions, options, JAR/module paths, or processors can yield different outputs. The key must reflect all inputs capable of influencing output.

### 16.2. Hashing Only JAR Path, mtime, or Size

A JAR can be redeployed with the same path, timestamp, and size. Hash the actual bytes used by the compiler; ensure the compiler reads the **exact snapshot** that was hashed to prevent TOCTOU issues.

### 16.3. Using `String.hashCode()`

A 32-bit hash is insufficient as a content key. Use SHA-256 over a canonical length-prefixed encoding with namespace/schema versioning.

### 16.4. Sorting the Classpath to Make Keys "Clean"

Classpath lookup order can change which class version is chosen. Preserve meaningful ordering; only sort logical set-like collections when order truly cannot affect compilation.

### 16.5. Omitting Transitive Dependencies and Generated Sources

Compilation can depend on superclasses, annotations, generic types, constants, and sources found on the sourcepath. Annotation processors also emit new outputs. Whole-path/batch fingerprinting is a reliable starting choice.

### 16.6. Reusing Bytecode Objects When Compiler Output Is Incomplete

A successful compilation must snapshot **all** class files; do not publish a map while an `OutputStream` is still writing to it. Do not use `Map.copyOf` and assume the byte arrays cannot be mutated.

### 16.7. Caching Errors Permanently or Replacing Invalidation with TTL

Transient errors must have a retry path. TTL only expires entries by time; a key missing a dependency can still produce false hits while within its TTL.

### 16.8. Treating ClassLoader as a Compiler Cache

`ClassLoader` manages runtime class definitions; a compilation cache manages reusable bytecode. A new runtime version requires a new generation/loader. Holding `Class<?>` from an old loader can prevent unloading.

### 16.9. Running Untrusted Processors or Sources in the Host Without Isolation

Annotation processors are Java code executed during compilation; user-written bytecode can affect resources when executed. Neither `ClassLoader` nor JPMS is a sandbox. For untrusted code, consider separate compilation/execution processes, OS resource limits, timeouts, and permission controls.

## 17. Practical System Design Checklist

1. **Define CompilationRequest:** single source, batch, or module; validate sources and logical names.
2. **Pin compiler profile:** version/toolchain, `--release`, file manager locations, processor policy.
3. **Snapshot inputs:** all sources and compile-visible artifacts, preventing JAR mutation between fingerprinting and task execution.
4. **Canonical manifest:** sort sources by logical path; keep meaningful order for options/classpath; hash contents and namespace version.
5. **SHA-256 key:** encoding with field boundaries, never merging non-equivalent inputs.
6. **Compile:** `JavaCompiler.getTask` with an appropriate `JavaFileManager`; capture diagnostics and all outputs.
7. **Cache successes:** cloned bytecode maps/immutable blobs, schema/integrity checks, atomic publish; separate failure handling.
8. **Concurrency:** per-key single-flight, bounded task resources, and timeouts/eviction.
9. **Runtime loading:** use classloader generations; never redefine identically named classes in an old loader.
10. **Verify:** changes to source/options/dependencies/toolchain cause proper misses; identical inputs hit; test corruption, version drift, and concurrency.

**Guiding principle:** a cache key must represent **the entire compilation environment capable of affecting output**, not just source text. For `JavaCompiler` running in memory, a stable manifest covering sources + effective options + dependency contents + compiler identity, hashed with SHA-256 against immutable input snapshots, is the foundation for correct and scalable bytecode caching.

## 18. Java SE 17 References

- JavaCompiler: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html
- JavaFileManager: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaFileManager.html
- ForwardingJavaFileManager: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ForwardingJavaFileManager.html
- ToolProvider: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ToolProvider.html
- SimpleJavaFileObject: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/SimpleJavaFileObject.html
- StandardJavaFileManager: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html
- javac options, processor paths, and --release: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
- MessageDigest: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html
- ClassLoader: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html