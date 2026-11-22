# Re-verifying generated sources and classes when changing tool versions

In a Java project, not every `.java` or `.class` file is written directly by developers. Annotation processors generate mappers, builders, or metamodels; OpenAPI/Protobuf/JAXB tools generate clients and data models from schemas; bytecode enhancers modify classes after compilation; Mockito, ORMs, and AOP can generate proxies at runtime. When upgrading versions of these tools to support a newer JDK, **the generated artifacts may change even when business source code stays unchanged**.

The risk is not limited to failed builds. A generator can alter method signatures, annotations, constructors, visibility, null handling, enum conversion, or data formats without triggering a compile error in the current module. Already-released binary clients can hit `NoSuchMethodError`; integration tests can fail due to proxies or reflection; or serializers can emit different output so older consumers can no longer read it safely.

This lesson explains how to re-verify **generated sources, class files, the final JAR, and runtime behavior** when changing the JDK, compiler, generator, annotation processor, build plugin, or bytecode-generation/transformation tool. The focus is determining actual output, comparing cleanly in a controlled way, and testing consumer contracts.

## 1. Code generation spans multiple kinds and stages

~~~text
Source / annotations / schema / templates
                  |
     +------------+-------------+
     |                          |
Annotation processor      Schema generator
(MapStruct, QueryDSL)     (OpenAPI, XJC, protoc)
     |                          |
     +----------+---------------+
                |
                v
          Generated .java
                |
                v
           javac / compiler
                |
                v
             .class
                |
         +------+------+
         |             |
    Enhancer/agent   Packaging
         |             |
         +------+------+
                |
                v
         Artifact JAR/WAR
                |
                v
          JVM at runtime
                |
                v
       Proxy / class generation
~~~

| Code generation source | Examples | Outputs to inspect |
|---|---|---|
| Annotation processing | MapStruct, Dagger, QueryDSL, JPA metamodel | Generated `.java`, resources, compiled `.class` |
| Compiler/AST transforms | Lombok, compiler extensions | Compiled classes, public members, metadata |
| Schema-driven generation | Protobuf/gRPC, OpenAPI, JAXB/XJC, WSDL | API source, wire serialization, DTOs |
| Bytecode libraries | ASM, Byte Buddy, CGLIB | Bytecode, class hierarchy, runtime proxies |
| Post-compile enhancement | ORM enhancement, weaving, instrumentation | `.class` after enhancement |
| Packaging transforms | Shading, relocation, obfuscation | Class/package names and published JAR |
| Test runtime generation | Mockito inline/subclass mocks, agents | Runtime-generated classes and test behavior |

**Do not inspect only the generated-source directory.** Some tools do not emit `.java` files and instead generate or modify class files directly; others generate classes only inside the JVM while tests or the application run.

## 2. Why can changing tool versions alter application behavior?

A newer version may:

- Rename generated packages, classes, methods, fields, or constructors.
- Change parameter/return types, generic signatures, or method descriptors.
- Narrow visibility or add `final`, `static`, `synthetic`, or bridge methods.
- Emit bytecode targeting a newer JDK than the supported runtime.
- Change null handling, collection copying, enum mapping, or date/time conversion.
- Alter annotations/metadata relied upon by DI, ORM, serialization, or reflection.
- Change proxy/subclass generation strategies or Java agent attachment methods.
- Alter schema-to-Java mappings, such as field presence or unknown enum handling.
- Add runtime dependencies, helper classes, or class-loader requirements.
- Emit files with timestamps, absolute paths, or unstable ordering, causing reproducibility issues.

### 2.1. Example: unchanged API, changed mapper semantics

Old generated implementation:

~~~java
public ProductDto convert(Product product) {
    if (product == null) {
        return null;
    }
    ProductDto dto = new ProductDto();
    dto.setName(product.getName());
    return dto;
}
~~~

New generated implementation:

~~~java
public ProductDto convert(Product product) {
    ProductDto dto = new ProductDto();
    if (product != null) {
        dto.setName(product.getName());
    }
    return dto;
}
~~~

The example illustrates two null-handling policies rather than a specific release. The public signature of `convert(Product)` did not change, yet the result on `null` input differs. No linkage error alerts you.

### 2.2. Example: generated class API changes

Suppose an older binary consumer invokes a method with descriptor:

~~~text
(Lcom/example/model/Order;)Lcom/example/model/OrderDto;
~~~

A newer generator adds a `MappingContext` parameter. Unrecompiled binary consumers still look for the old descriptor; if that old method is gone, the JVM can throw `NoSuchMethodError`.

Therefore distinguish two kinds of compatibility:

- **Binary/source compatibility:** do classes/members still exist so clients can compile/link?
- **Behavioral/data compatibility:** do the same calls still produce expected results, data, and side effects?

## 3. Recording all generator inputs completely

To trace where a change came from, identify every input:

~~~text
Generator / plugin version ---+
JDK and compiler version -----+
Annotations and source -------+
OpenAPI/XSD/proto schema -----+--> Generated output
Generator options/templates --+
Processor classpath ----------+
Locale/encoding/environment --+
Incremental/cache state ------+
~~~

| Group | What to record |
|---|---|
| JDK | Version, vendor, patch, compiler target/release |
| Build | Maven/Gradle version, plugin versions |
| Generator | CLI, library, annotation processor, template version |
| Input | Git commit, schema/IDL revision, source annotations |
| Config | Naming, null, enum, date/time, target language options |
| Processor dependencies | Processor path, transitive dependencies |
| Runtime constraints | Supported JDKs, module path, frameworks |
| Output | Generated source, resources, classes, final artifact |
| Pipeline | Code enhancement, shading, obfuscation, packaging |

Do not conclude "generator version X changed the classes" if the two builds also changed schemas, JDKs, compiler flags, or dependency graphs without isolating their effects.

## 4. Creating baseline and candidate via clean builds

Basic workflow:

~~~text
Same source/schema snapshot
          |
    +-----+------+
    |            |
    v            v
Old generator New generator
Old JDK/tool  Target JDK/tool
    |            |
Clean build   Clean build
    |            |
    v            v
Old source    New source
Old classes   New classes
Old JAR       New JAR
    |            |
    +-----+------+
          |
          v
Diff source + bytecode + API
          |
          v
Test consumers and runtime behavior
~~~

**Clean builds** matter greatly: incremental builds can retain files generated by the older version, tricking reviewers into thinking the newer version still generated them.

### 4.1. Maven

Illustrative commands to run in a test environment:

~~~bash
mvn -version
mvn clean compile
mvn clean package
~~~

Common output locations:

~~~text
target/generated-sources/annotations/
target/generated-sources/<generator>/
target/generated-test-sources/
target/classes/
target/test-classes/
target/*.jar
~~~

Depending on the plugin, generated sources may also be written to custom locations or a dedicated generated-code module.

### 4.2. Gradle

~~~bash
./gradlew --version
./gradlew clean classes
./gradlew clean build
~~~

To rule out caching or incremental logic hiding changes:

~~~bash
./gradlew clean classes --no-build-cache --rerun-tasks
~~~

Common directories:

~~~text
build/generated/sources/annotationProcessor/java/main/
build/generated/sources/annotationProcessor/java/test/
build/classes/java/main/
build/classes/java/test/
build/libs/
~~~

There is no need to disable caching permanently. The goal is producing a trustworthy baseline before inspecting the upgrade.

### 4.3. Separating two environments

Use independent worktrees/CI jobs so each build owns its own build directory. When comparing the same source across two generators, change only the versions under evaluation; if JDK and tool must be upgraded together, document this and expand the test matrix as needed.

## 5. Comparing generated sources by impact level

Start with **added, deleted, and renamed** files before inspecting line-by-line contents.

Example when comparing two snapshot directories:

~~~bash
git diff --no-index --stat snapshots/old/generated snapshots/new/generated
git diff --no-index snapshots/old/generated snapshots/new/generated
~~~

With `git diff --no-index`, a non-zero exit code can simply indicate differences were found rather than command failure.

Categorizing outputs:

| Diff type | What to check |
|---|---|
| Timestamp/header | Reproducibility; may just be noise |
| Imports/formatting | Does it alter compile behavior? |
| Removed file/class | Do clients/DI/frameworks still depend on it? |
| New constructor/method | API surface and overload resolution |
| Changed method parameters | Descriptors, existing binary consumers |
| Changed access modifiers | Compile/link visibility, JPMS |
| Changed annotations/metadata | ORM, DI, serialization, reflection |
| Changed mapping logic | Null, enum, collection, numeric conversions |
| Changed serialization template | Wire format, backward/forward compatibility |
| Changed generic types | Source/API compatibility, reflection |
| Changed package/namespace | Client imports and framework discovery |

A few-line change can matter far more than thousands of reformatting lines. Conversely, timestamps changing file hashes do not necessarily alter runtime results.

### 5.1. Do not edit generated sources to patch root bugs

Generated source is normally the output of schemas/annotations/options/templates. Hand-editing files inside `target/generated-sources` or `build/generated` will be overwritten on the next build. Fix the source of truth or generator config instead.

An exception is projects intentionally committing generated sources as managed code; even then, establish a regeneration workflow, diff review, and generator version synchronization.

## 6. Comparing class files after compilation and enhancement

Identical generated `.java` does not guarantee identical `.class` files. Compiler JDK, `--release`, bytecode weaving, instrumentation, and packaging can all change results.

### 6.1. Inspecting major versions

~~~bash
javap -verbose -classpath target/classes com.example.generated.OrderMapperImpl
~~~

Example class file major versions:

| Java | Major |
|---|---:|
| 8 | 52 |
| 11 | 55 |
| 17 | 61 |
| 21 | 65 |

If an artifact advertises Java 17 support yet ships a generated class with major 65, Java 17 can throw `UnsupportedClassVersionError` when loading that class.

**Inspect the final artifact**, not only hand-written classes. If a generator or dependency JAR targets a runtime higher than the target, passing `--release 17` to the main compiler does not automatically make that dependency Java 17-compatible.

### 6.2. Inspecting descriptors and modifiers

~~~bash
javap -classpath target/classes -p -s com.example.generated.OrderMapperImpl
javap -classpath target/classes -p -verbose com.example.generated.OrderMapperImpl
~~~

- `-s` displays JVM field/method descriptors.
- `-p` includes non-public members.
- `-verbose` shows constant pool and metadata.
- `-c` disassembles bytecode instructions when deeper logic analysis is required.

For binary compatibility, method names and descriptors are critical. A method keeping the same name while changing parameters or return type still triggers `NoSuchMethodError` in older binaries.

### 6.3. Inspecting the final JAR

~~~bash
jar --list --file target/application.jar
~~~

Check classes, resources, service provider metadata, and dependency relocations. With shaded/fat JARs, classes inside the released JAR can differ from `target/classes` because build plugins relocated or transformed them.

### 6.4. API diff tools

Tools such as Revapi or japicmp compare JARs at the API/ABI level and catch many binary-breaking changes. However, they cannot replace tests for null handling, serialization semantics, ORM state transitions, or runtime-generated proxies.

## 7. Maven: controlling annotation processors

Annotation processors must be declared and versioned explicitly with the build. Maven Compiler Plugin example:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.14.0</version>
    <configuration>
        <release>17</release>
        <annotationProcessorPaths>
            <path>
                <groupId>org.mapstruct</groupId>
                <artifactId>mapstruct-processor</artifactId>
                <version>1.6.3</version>
            </path>
        </annotationProcessorPaths>
    </configuration>
</plugin>
~~~

This is illustrative config; actual plugin/processor versions must fit your project. If source code uses annotations and interfaces from MapStruct, the corresponding API dependency must also be declared properly.

### 7.1. Why use a separate processor path?

An annotation processor is a **build-time** tool; it typically does not belong in runtime artifacts. Separating the processor path offers key benefits:

- Ensures processor versions are pinned explicitly.
- Prevents accidentally executing processors from compile dependencies.
- Reduces classpath conflict risk.
- Makes it easier to trace why generated code changed.
- Avoids bundling build tools into runtime deployments.

When changing JDKs/compilers, annotation processor discovery rules may change. Configure processing explicitly rather than assuming processors auto-run as on older compilers.

### 7.2. Generated test sources need checking too

If processors execute during `testCompile` or plugins generate test fixtures/helpers, also compare:

~~~text
target/generated-test-sources/
target/test-classes/
~~~

A newer test tool can emit different classes without touching the main artifact, yet still cause flaky or failing tests on a newer JDK.

## 8. Gradle: processor paths, toolchains, and incremental builds

Java Gradle project example:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.mapstruct:mapstruct:1.6.3'
    annotationProcessor 'org.mapstruct:mapstruct-processor:1.6.3'
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

Distinct concepts:

- `implementation`: libraries/APIs consumed by source code.
- `annotationProcessor`: processors executed during compilation.
- `java.toolchain`: JDK for toolchain-aware Java tasks.
- `options.release`: Java language/API/bytecode level for the compiler.

A processor with incomplete task input/output declarations can cause incremental builds to miss generated files after source changes. Therefore execute both a clean build and a representative incremental build before accepting a new configuration.

## 9. Schema-based generators: verifying generated code and wire data

### 9.1. Protobuf and gRPC

When upgrading `protoc` or the gRPC Java plugin, inspect:

- Generated packages, class names, and Java outer class names.
- Client/server stub method signatures.
- Field numbers and wire types.
- Optional/oneof and presence semantics.
- Unknown field preservation.
- Enum values, defaults, and unknown enum handling.
- Runtime Protobuf/gRPC library version.

Java code may change while the wire protocol stays compatible; conversely, a schema may change field meaning even when the Java API looks nearly identical. Source diffs alone are insufficient: test serialization fixtures across producer/consumer versions.

### 9.2. OpenAPI Generator

Check:

- Model classes, operation names, packages.
- HTTP paths, methods, header/query parameters.
- JSON field naming, serializer annotations.
- Nullability and required/optional behavior.
- Enums and validation.
- Date/time type mappings.
- Response error handling.
- Runtime HTTP client dependencies.

Run contract tests against realistic payloads, including missing/unknown fields, nulls, nested objects, and key HTTP status codes. Do not merely verify the client compiles.

### 9.3. JAXB/XJC/WSDL and namespace migration

When changing XML binding generators, verify `javax.*` vs. `jakarta.*` annotation namespaces, XML element names, adapters, date/time conversion, QNames, and marshal/unmarshal behavior.

A generated class carrying Jakarta annotations may fail with an older framework consumer supporting only Javax annotations; that is an API and runtime integration shift rather than a mere compiler issue.

### 9.4. JPA metamodels and ORM enhancement

When upgrading ORM annotation processors/enhancers, check generated metamodel attributes, reflective access, proxy subclasses, lazy loading, dirty tracking, serialization, and `equals`/`hashCode` behavior. Especially under JPMS, proxies/agents may also encounter `exports` or `opens` issues.

## 10. Bytecode transformers and test tools

Libraries like ASM/Byte Buddy, mocking frameworks, or coverage agents must understand class-file versions emitted by newer JDKs. Outdated tools may fail with:

~~~text
Unsupported class file major version ...
java.lang.VerifyError: ...
java.lang.ClassFormatError: ...
~~~

Not every error means invalid bytecode was generated; sometimes the class-reading tool lacks support for the new class-file version, or the test plugin attaches agents via a changed mechanism.

When upgrading tools for a newer JDK, verify:

- Can tests still mock final/static/constructors per contract?
- Are proxies defined in the right class loader/module?
- Must packages be opened for reflection under JPMS policy?
- Does instrumentation alter class methods, fields, or annotations?
- Does the agent still operate on the target runtime and under dynamic-attachment policies?
- Is final class bytecode valid and compatible with the target?

**Runtime-generated classes do not necessarily sit on disk.** Use integration tests or library-supported bytecode dump mechanisms when deep inspection is needed. Never guess dump flags or loosen JVM permissions in production just to "try it out".

## 11. Common errors and diagnosis

| Error / symptom | Possible causes | Investigation path |
|---|---|---|
| `cannot find symbol` | Generated class/method missing | Input annotations, source output, plugin config |
| `NoSuchMethodError` | Binary descriptor mismatches newly generated class | `javap -s -p`, ABI diff |
| `NoSuchFieldError` | Field removed/retyped | Field descriptors, consumers |
| `IllegalAccessError` | Modifiers or module exports changed | Access flags, packages, modules |
| `UnsupportedClassVersionError` | Bytecode targets newer JVM than runtime | Major version, toolchain, `--release` |
| `VerifyError` | Bytecode violates verifier | Transformer, stack frames, agent |
| `ClassFormatError` | Malformed class file or misparsed by tool | Generator/library, artifact |
| `NoClassDefFoundError` | Missing generated class/dependency or init failure | Packaging, runtime classpath, cause |
| `ClassCastException` | Proxy/loader/type hierarchy differs | Interfaces, class-loader identity |
| `InaccessibleObjectException` | Reflection blocked by JPMS | `opens`, framework version |
| `InvalidClassException` | Incompatible Java serialization form | Fields, `serialVersionUID` |
| JSON/XML/protocol mismatch | Generator altered serialized payload | Fixtures and contract tests |
| Mock tests fail on newer JDK | Incompatible bytecode agent/mock engine | Dependency versions, runtime, agent logs |

Do not lump every issue under "the new JDK has a bug". Identify the stage where failure begins: generation, compilation, packaging, loading, linking, or runtime behavior.

## 12. Testing source and binary consumers separately

### 12.1. Compiling source consumers against the new artifact

Create a sample module consuming public generated APIs. Recompiling exposes renamed classes, constructors, methods, or invalid generic signatures.

### 12.2. Running older binary consumers against the new artifact

When libraries serve pre-compiled clients:

~~~text
Library v1 + generator v1
            |
            v
Compile Client.class
            |
            v
Keep Client.class unchanged
            |
            v
Swap library to v2
            |
            v
Run old Client.class against library v2
~~~

Only this tests binary compatibility of existing artifacts. Recompiling the client catches errors at compile time instead of testing what production binaries experience.

### 12.3. Key behaviors to test

- Null, empty, and default values.
- Unrecognized enums and unknown fields.
- Collection ordering and nested object mappings.
- Currency/numeric precision, timezones, and locales.
- JSON/XML/Protobuf round-trips across versions.
- ORM proxies, lazy loading, and dirty tracking.
- Dependency injection discovery.
- Serialization/reflection/annotation metadata.
- Test agents and mocking behavior.

A generated class with an unchanged public API can still drop data or change authorization mappings; maintain contract tests covering essential business invariants.

## 13. Reproducible builds and output noise

Generated files may differ merely because of timestamps, absolute paths, or filesystem traversal order. Comparing raw hashes produces noisy false positives. Nevertheless, unstable output also harms caching and supply-chain verification.

Best practices:

1. Pin generator and compiler/build plugin versions.
2. Disable timestamps or volatile headers when tools allow.
3. Fix input ordering, encoding, and relevant flags.
4. Record JDK/vendor/build info and schema revision.
5. If normalizing output before diffing, strip only understood noise; never strip annotations or metadata affecting runtime.
6. Verify clean builds in a second environment.
7. Run a representative incremental build after a clean build.

**Valid clean build** and **valid incremental build** are separate conditions. A processor with incorrect cache keys can produce proper clean outputs yet leave stale files when sources change.

## 14. Practical workflow when upgrading generators or test tools

### Step 1: Inventory tools

List annotation processors, schema generators, bytecode transformers, agents, mocking/coverage frameworks, and packaging plugins. Record versions, output paths, input schemas, and consumer groups.

### Step 2: Save baseline

Pin the same source revision/schema and build with old tools in a clean directory. Archive generated sources, compiled classes, artifacts, API reports, and critical test fixtures.

### Step 3: Upgrade tools in a controlled step

Change only the target generator/plugin/dependency being tested. If also switching JDKs, document it to separate causes. Avoid changing schemas or business logic simultaneously when evaluating a generator upgrade.

### Step 4: Produce candidate via clean build

Ensure no stale files or unverified build caches interfere. Record compiler and tool metadata.

### Step 5: Diff generated sources

Check added/deleted/renamed files, code edits, metadata, null/enum mappings, and public APIs.

### Step 6: Diff class files and final artifacts

Inspect major versions, descriptors, modifiers, runtime annotations, transformed classes, and JAR contents. Use an API diff tool if external consumers exist.

### Step 7: Run cross-version tests

Compile new source consumers and run old binary consumers against the new artifact; run serialization/contract tests over v1/v2 fixtures. For bytecode agents/proxies, run directly on the target JDK.

### Step 8: Verify reproducibility and incrementality

Confirm output stability on a clean CI runner and ensure modifying inputs updates generated files properly. If noise appears, trace its cause before adding snapshot checks.

### Step 9: Update compatibility documentation

If APIs or wire formats changed, write migration instructions, release notes, consumer impacts, and new JDK requirements. Do not dismiss breaking changes as "just a plugin bump".

## 15. Common misconceptions

**"Business source didn't change, so the artifact didn't change."** False. Generators, compilers, and enhancers can emit different source and bytecode.

**"Checking generated .java is enough."** False if tools modify `.class` files directly or generate runtime proxies.

**"A passing build proves binary compatibility."** False. Pre-compiled clients may throw `NoSuchMethodError` against the new JAR.

**"Identical API means identical behavior."** False. Mappers and serializers may alter null, enum, and default semantics.

**"`--release 17` ensures every class in the JAR runs on 17."** False if dependencies or post-processors emit higher bytecode versions.

**"Processors in dependencies always run."** Do not assume so. Processor discovery rules, paths, and compiler versions matter critically.

**"A passing incremental build means generated output regenerated cleanly."** False when stale files or caching mask missing execution.

**"Checking JAR hashes alone suffices."** Different hashes do not explain how contracts shifted; matching hashes do not prove all runtime behaviors.

**"Upgrading Mockito/Byte Buddy affects tests only."** Test tools generate classes/agents on the new runtime; testing-infrastructure issues must be separated from business regressions.

## 16. Checklist when changing code-generation tool versions

- [ ] Identified involved tools and outputs: sources, classes, resources, proxies.
- [ ] Pinned Git revision, schemas, templates, and generator options.
- [ ] Recorded old and new JDK/compiler/build plugin/generator versions.
- [ ] Produced two clean builds without reusing stale generated outputs.
- [ ] Compared added/deleted/renamed generated files.
- [ ] Reviewed changes in generated sources, constructors, and methods.
- [ ] Verified class-file major versions in the final artifact.
- [ ] Compared public API/ABI, descriptors, visibility, and runtime annotations.
- [ ] Checked enhancement, shading, and runtime-generated proxies.
- [ ] Verified annotation processor paths and generated source directories.
- [ ] Executed both source consumer builds and binary consumer compatibility tests.
- [ ] Verified serialization/protocol fixtures and read–modify–write behavior.
- [ ] Executed unit/integration tests for nulls, enums, ORM, DI, and reflection.
- [ ] Tested on both minimum and target runtime JDKs.
- [ ] Handled timestamp/path noise appropriately without masking meaningful diffs.
- [ ] Verified reproducible and incremental builds.
- [ ] Archived diffs, test evidence, and migration notes as needed.

## 17. Conclusion

Changing versions of annotation processors, schema generators, compiler plugins, bytecode enhancers, or test tools changes **an input to artifact production**, not merely build formatting. It can alter generated Java sources, class files, public APIs, or serialization behavior with zero edits to business source code.

For Java Advance Compatibility Migration, always inspect **actual generated sources**, **class files/JARs after all transformation steps**, and **consumer runtime contracts**. Compare clean baseline and candidate builds, verify binaries with `javap` and API diffs, run data/serialization tests alongside pre-compiled binary clients, and validate proxies/agents on the target JDK. Only with evidence across these layers can upgrading code-generation tools be considered safe within the supported system scope.