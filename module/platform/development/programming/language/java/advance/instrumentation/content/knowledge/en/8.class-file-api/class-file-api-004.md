# Class-File API: Immutable Models, Lazy Parsing, and Thread-Sharing Considerations

## 1. Core Problem

The standard **Class-File API** in `java.lang.classfile` allows reading, generating, and transforming `.class` file contents. The API was standardized in **JDK 24** (JEP 484); in JDK 22–23 it was a preview feature. This article examines three closely related properties:

1. **Immutable model:** `ClassModel`, `MethodModel`, `FieldModel`, `CodeModel`, and elements describe the class file in a form without direct mutation operations. To modify a class file, we use builders/transforms to generate new bytes.
2. **Lazy parsing/inflation:** after `ClassFile.of().parse(bytes)`, not all method bodies, attributes, instructions, and constant-pool entries are necessarily decoded. These parts may be created when an accessor is called.
3. **Thread safety must be considered separately:** even though the model interface is immutable, the Java 24 documentation explicitly states that **models may not be thread-safe due to laziness**. A read accessor may cause the library to initialize or cache internal structures.

Therefore, the statement “`ClassModel` is immutable, so it can definitely be shared across multiple threads without locking” is **incorrect according to the API contract**. A read-only model does not mean it has been fully materialized, nor does it mean there are synchronization guarantees for structures built on demand.

Official documentation: [java.lang.classfile — Reading classfiles, Models and elements](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/package-summary.html).

## 2. Tree Model: Reading Only What Is Needed

~~~text
byte[] containing class file
         |
         v
ClassFile.of().parse(bytes)
         |
         v
ClassModel
  |-- thisClass(), flags(), interfaces(), majorVersion()
  |-- fields()          -> FieldModel -> metadata/attributes
  |-- methods()         -> MethodModel -> methodName(), methodType()
  |                                       |
  |                                       +-- code() -> Optional<CodeModel>
  |                                                         |
  |                                                         +-- code elements
  |-- attributes()      -> class attributes
  +-- constantPool()    -> read-only constant pool / PoolEntry
~~~

A `MethodModel` can be accessed via `ClassModel.methods()` or appear as a `ClassElement` when traversing `ClassModel`. A `CodeModel` is a child model of a method and contains instructions, labels, and related metadata. The API provides both **random access** and `Iterable`/`elementStream()` traversal.

If you only list method names, accessing `methods()` and `methodName()` is sufficient; there is no need to descend into each `CodeModel`. Only if you analyze method calls, field accesses, or branches do you need to enter the code section.

~~~java
ClassModel model = ClassFile.of().parse(bytes);
for (MethodModel method : model.methods()) {
    System.out.println(method.methodName().stringValue());
}
~~~

This is a **JDK 24+ code snippet** in a program that has `byte[] bytes` and imports `ClassFile`, `ClassModel`, and `MethodModel`. It illustrates reading metadata; it is not a standalone program.

**`ClassModel` differs from `Class<?>`:** a model describes bytes in the JVM class file format; `java.lang.Class` represents a type already defined by a class loader in the JVM. `ClassFile.parse` is not equivalent to `Class.forName` and does not require running the static initializer of the class being read. This distinction is important when using the API in a Java agent because we often want to analyze class bytes without triggering new class loading.

## 3. What Does Immutability Mean?

A parsed model provides a *logical description* of a class file. There is no operation like `model.methods().get(0).setName("changed")` to mutate the original class; methods of that kind are not part of the API.

To change the content, the workflow is:

~~~text
original class bytes -> parse -> immutable ClassModel
                                      |
                                      v
                             ClassTransform/builder
                                      |
                                      v
                               new output byte[]
                                      |
                                      v
                              parse -> new model
~~~

Example illustrative code snippet, assuming `sourceBytes` already exists:

~~~java
ClassFile context = ClassFile.of();
ClassModel original = context.parse(sourceBytes);

byte[] rewritten = context.transformClass(
        original, (builder, element) -> builder.with(element));

ClassModel after = context.parse(rewritten);
~~~

`transformClass` produces output bytes, while `original` is not modified. The transform above only forwards elements to illustrate the processing flow; it does not promise that the output byte array is byte-for-byte identical to the input. Stateful builders used during byte emission **must not be assumed to be thread-safe**.

Immutability here does **not** automatically imply the following conclusions:

- **No internal work:** accessors may decode/allocate/cache new structures due to lazy parsing.
- **Input cannot be modified:** `byte[]` is still a Java array that can be written to by another caller; the owner must keep it unchanged or copy it.
- **All child objects are safe to share:** `MethodModel`/`CodeModel` may also be lazily inflated.
- **Builders can be shared:** builders serve the class file construction process; use a separate builder per task.

For example, a `List<MethodModel>` even when wrapped with `List.copyOf` still contains **lazy models**. The list prevents adding/removing elements, but the models inside do not thereby become thread-safe. To share results, extract `String`, integers, enums, or truly immutable DTOs.

## 4. What Does Lazy Parsing Save?

A class file can contain many method bodies, debug metadata, annotations, stack maps, bootstrap methods, and constant-pool entries. Not every tool needs to read all of them.

| Task | Level of information needed |
| --- | --- |
| Print class name, class file version | `thisClass()`, `majorVersion()` |
| List methods/fields | `methods()`, `fields()`, and name/descriptor accessors |
| Read annotations | Corresponding annotation attributes or elements |
| Analyze bytecode calling methods/reading fields | `method.code()` then iterate `CodeElement` |
| Rewrite class | Parse model, create builder/transform, emit bytes, and verify |
| Scan thousands of classes | Query only needed information first, analyze deeply on demand |

You should not assume the exact allocation level of an accessor; that is an implementation detail. The important contract is that **information can be parsed lazily**, so fast parsing does not prove the entire tree is ready.

The following snippet goes deeper, when reading code is actually needed:

~~~java
for (MethodModel method : model.methods()) {
    method.code().ifPresent(code -> {
        for (CodeElement element : code) {
            // Analyze only code elements relevant to the target.
        }
    });
}
~~~

This is also a **code snippet in a context that already has `model` and imports `CodeElement`**. `method.code()` returns `Optional<CodeModel>` because `abstract`/`native` methods may have no code section. Code elements can include both instructions and metadata/labels; you should not count every element as an instruction.

## 5. Lazy Parsing Changes Error Handling

According to the Javadoc, `ClassFile.parse(byte[])` may throw `IllegalArgumentException` for invalid bytes or an unsupported class-file version. **Due to on-demand parsing**, the same error can also appear **after `parse` has already returned a model**, as soon as an accessor is called on the model or a child model.

~~~text
parse(badBytes) may:
  A. detect error immediately -> IllegalArgumentException
  B. create ClassModel
        |
        +-- thisClass(): readable
        |
        +-- methods()/code()/attributes(): encounters invalid part
                                          |
                                          +-- IllegalArgumentException
~~~

These are possibilities described by the contract, not a claim that every malformed class file causes a late error.

**Catch errors around the entire required analysis**, instead of only around the `parse` call:

~~~java
try {
    ClassModel model = ClassFile.of().parse(classBytes);
    for (MethodModel method : model.methods()) {
        String name = method.methodName().stringValue();
        // Store name into analysis results.
    }
} catch (IllegalArgumentException malformed) {
    // Mark class file as invalid or unsupported.
}
~~~

This snippet is placed inside a method that has a `classBytes` variable; it is not a standalone program. If reading a file via `Path`, you must also handle `IOException`. Avoid catching `Throwable` and producing a “no methods” report because that hides the real error.

`ClassFile.verify(bytes)` provides class file verification and returns errors found by the verifier. Use it when additional input/output verification is needed, especially when transforming bytecode. It **has a cost** and **does not replace** catching errors at accessors, nor does it prove business logic is correct:

~~~java
var errors = ClassFile.of().verify(classBytes);
if (!errors.isEmpty()) {
    // Handle errors detected by the verifier.
}
~~~

Related APIs: [ClassFile.parse, verify, and transformClass — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassFile.html).

## 6. Multithreading: An Immutable API Does Not Guarantee Thread Safety

For Java objects in general, these two properties are distinct:

- **Immutable public state:** caller code has no mechanism to mutate the logical state.
- **Thread-safe implementation:** code can access it concurrently by contract without external synchronization.

Class-File API models have the first property, but the documentation warns they **may not have the second property** because they lazily inflate. A method that looks like a getter may create/cache child models. You should not claim a specific implementation will always have a data race; **the API not guaranteeing safety** is enough to avoid designs that depend on an unguaranteed property.

### 6.1. Sharing Approaches and Safety Levels

| Approach | Assessment |
| --- | --- |
| Each worker receives a copy of class bytes and calls `parse` itself | **Recommended**: the model and lazy accessors belong exclusively to the worker |
| One worker parses and extracts a record containing only `String`, `int`, and `List.copyOf(String)` | **Recommended**: share snapshot after proper publication |
| Multiple workers concurrently call `methods()`, `code()` on **the same `ClassModel`** without synchronization | **No thread-safety guarantee** |
| Call `model.methods()` once and assume the entire model is “warm” | Insufficient: code, attributes, and constant pool can still be lazy |
| Lock only the `parse` step, then allow unrestricted reads | Insufficient because parsing may continue when calling accessors |
| Share a single `ClassBuilder` or mutable transform state | No basis for safety guarantee; create separate builder/transform state per task |
| Use `ConcurrentHashMap<String, ClassModel>` | A thread-safe map **does not make the models inside thread-safe** |
| Must share a single model and all child models | Must synchronize **every access path** with an explicit contract; usually more complex than exporting immutable DTOs |

**Sharing a `MethodModel` can still mean sharing the same lazy tree.** Do not assume extracting a child model from `ClassModel` has copied all of its contents.

### 6.2. Byte Ownership

`byte[]` is not immutable. If one thread mutates the array while a parser on another thread is reading it, the result cannot be considered a stable snapshot. A simple approach:

~~~java
byte[] ownedCopy = sourceBytes.clone();
ClassModel localModel = ClassFile.of().parse(ownedCopy);
~~~

This snippet assumes `sourceBytes` already exists and **no thread is writing to it during the copy**. If data comes from a file/queue with clear ownership, the worker can read/copy it once. For large files, cloning bytes has a cost; measure before optimizing, and do not let many workers hold very large arrays indefinitely.

### 6.3. Publishing Data Snapshots

A result meant to be safely read concurrently can be:

~~~java
record Summary(String name, int major, List<String> methods) {}
~~~

A `record` has immutable fields after creation, but **whether a `record` is deeply immutable depends on its components**. In the full example below, the list is built with `List.copyOf` and contains only `String`, so it is safe to publish through standard synchronization channels. If an underlying `ArrayList` is still mutated by a worker, the record cannot change its reference field, but the data inside still mutates.

You can use `Future.get()` to receive worker results: the effects of computation before task completion are published according to Future's memory rules. Do not replace this with two threads writing/reading the same plain static field without a synchronization mechanism.

## 7. Standalone JDK 24+ Example: Two Workers Analyzing the Same File

**Why JDK 24?** Standard `java.lang.classfile` has existed since JDK 24, so this example intentionally **does not use `javac --release 17`**. On JDK 17–21, this standard package does not exist; Java 24 code cannot be promised to run on those JDKs. JDK 22–23 have a preview API with different conditions and versions.

The example has two files placed in the same directory. We compile `ExampleService` to bytecode, then two tasks analyze equivalent content, each with its own bytes/model.

### 7.1. `ExampleService.java`

~~~java
public final class ExampleService {
    public String status() {
        return "ready";
    }

    public int total(int base) {
        return base + 5;
    }
}
~~~

In addition to the two methods `status` and `total`, the compiler generates a default constructor `<init>`.

### 7.2. `ModelConcurrencyDemo.java`

~~~java
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassModel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class ModelConcurrencyDemo {
    record Summary(String internalName, int majorVersion,
                   List<String> methodNames) {}

    private static Summary inspect(byte[] ownedBytes) {
        // The model is accessed only within a single task.
        ClassModel model = ClassFile.of().parse(ownedBytes);

        List<String> names = model.methods().stream()
                .map(method -> method.methodName().stringValue())
                .sorted()
                .toList();

        return new Summary(
                model.thisClass().asInternalName(),
                model.majorVersion(),
                List.copyOf(names));
    }

    public static void main(String[] args) throws Exception {
        byte[] source = Files.readAllBytes(
                Path.of("ExampleService.class"));

        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            // Each worker receives a copy of the bytes and creates its own model.
            Future<Summary> first = pool.submit(
                    () -> inspect(source.clone()));
            Future<Summary> second = pool.submit(
                    () -> inspect(source.clone()));

            Summary left = first.get();
            Summary right = second.get();

            System.out.println("name=" + left.internalName());
            System.out.println("major=" + left.majorVersion());
            System.out.println("methods="
                    + String.join(",", left.methodNames()));
            System.out.println("equalSnapshots="
                    + left.equals(right));
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Because the model is created **inside `inspect`** and never returned outside, no other thread accesses the same lazy tree. The main thread only receives a `Summary` record containing `String`, `int`, and an immutable list of strings. `equals` compares the **values** of the two records, not the identity of the two models.

`source.clone()` is performed when creating each task, and `source` is not modified. When the number of classes is large, you must bound the number of workers and the amount of queued data. `shutdown()` stops accepting new tasks; in production code you may need `awaitTermination`/timeouts/task cancellation according to policy.

### 7.3. Compilation and Output

Use **JDK 24 or later**, with the working directory where the two files reside:

~~~bash
javac --release 24 ExampleService.java ModelConcurrencyDemo.java
java ModelConcurrencyDemo
~~~

**Expected stdout** when `ExampleService.class` is compiled properly with `--release 24`:

~~~text
name=ExampleService
major=68
methods=<init>,status,total
equalSnapshots=true
~~~

The class-file major version for Java 24 is **68**. `sorted()` orders `<init>`, `status`, and `total` deterministically, so the output does not depend on worker completion order. Equality proves the two analysis passes produce the same *logical snapshot*; **it does not prove the same `ClassModel` can be shared concurrently**.

## 8. What If You Must Use a Single Shared Model?

The default approach remains **model-per-task** or exporting DTOs. When specific measurements require keeping only one model, you must control **every access to the tree**: `ClassModel`, `MethodModel`/`CodeModel` instances, and the constant pool/attributes related to them. Synchronizing only the `parse` call does not help if subsequent accessor calls actually perform inflation.

“Prewarming” with `model.methods()` and then publishing still does not prove safety because a method may still have unread code or attributes. Nor is there any reason to treat stateful builder/transform callbacks as safe just because the input model is immutable.

If caching, **caching result snapshots** is a more manageable design than caching models. The cache key may need (class name, bytes hash/version, source/loader/module), because multiple class loaders or builds can supply different bytes for **the same class name**. A `ConcurrentHashMap<String, ClassModel>` cache only synchronizes operations on the map; it does not add guarantees for the model's contents.

### Performance Trade-offs

Parsing per task may allocate additional models and byte arrays, whereas parsing once and exporting immutable DTOs is often more economical if many threads need **the same data**. Measure with a representative workload:

- Number of class files and average size.
- Proportion of accesses needing only metadata, attributes, or deep bytecode.
- Memory allocation/GC, throughput, latency, and number of concurrent tasks.
- Rate of invalid class files and potential pipeline failure impact.

One way to reduce work is to **traverse only to the needed level**: if you only need the method count, do not enter `CodeModel`; if only a few classes need instruction inspection, filter by metadata first. That is the real advantage of lazy parsing.

## 9. Applying to Java Agents and `ClassFileTransformer`

In an agent, the JVM may invoke `transform` on multiple threads as multiple classes are loaded. Each callback receives `classfileBuffer` for a single definition/transformation. If using the Class-File API, create the model within **the callback scope** and avoid storing the model in a static variable for other threads to traverse.

~~~java
@Override
public byte[] transform(
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain domain,
        byte[] classfileBuffer) {

    // Filter scope early to avoid instrumenting agent/JDK/logger.
    if (className == null || !className.startsWith("example/app/")) {
        return null;
    }

    ClassModel model = ClassFile.of().parse(classfileBuffer);
    // Read needed parts directly within the current callback.
    // Do not export the model to another thread for lock-free access.
    return null; // This transformer does not modify class bytes.
}
~~~

This is a **code snippet in a class implementing `ClassFileTransformer`**, requiring `ClassFile`/`ClassModel` imports and an agent registering the transformer; it is not a standalone program.

Practical considerations:

1. **Do not mutate `classfileBuffer`** provided by the JVM. To modify a class, use a builder/transform to create a new `byte[]`.
2. **Do not retain `ClassModel` across multiple callbacks for concurrent reading**; other callbacks may run on different threads.
3. **Do not analyze every class unnecessarily**; filter name/loader/module appropriately as early as possible, avoiding recursion caused by the agent itself and logging libraries.
4. **If you actually need to modify the class during loading, you must return the transformed bytes in the callback**. Offloading work to the background and returning `null` does not modify the current class.
5. **Watch out for late errors:** `parse` may return a model and then an accessor detects invalid bytes. Handle according to the callback contract and agent policy.
6. **Separate analysis capability from application authority**: the Class-File API reads/generates bytes; `Instrumentation` and the JVM decide whether a class is being loaded or can be retransformed/redefined.

If you only want offline analysis, a pipeline outside the JVM/agent avoids many classloading restrictions and impact on the running application.

## 10. Common Mistakes

| Misconception | Why Is It Wrong? | Right Approach |
| --- | --- | --- |
| “Immutable = thread-safe.” | Lazy inflation may mutate internal state on read | Per-worker model or export immutable DTOs |
| “`parse` finishing means everything is parsed.” | Accessing `code`/attributes may parse lazily | Check needed data level and catch errors at accessors |
| “Catching exceptions around `parse` alone is enough.” | `IllegalArgumentException` may appear later | Wrap the entire query/analysis block |
| “Sharing a copied `List<MethodModel>` is safe.” | Elements are still lazy models | Extract names/descriptors as `String` and copy |
| “No one can modify `byte[]`.” | Java arrays are mutable | Maintain ownership or clone |
| “Calling `methods()` once warms all code.” | Method bodies may still not be inflated | Do not treat warm-up as a thread-safety guarantee |
| “Synchronizing `parse` lets threads read the shared model.” | Lazy activity happens after parse | Synchronize all read paths or avoid sharing |
| “`ConcurrentHashMap` protects `ClassModel`.” | Only map operations have synchronization guarantees | Cache truly immutable DTOs |
| “Builders are also immutable because models are immutable.” | Builders serve output creation and are stateful | Use a separate builder per task/output |
| “Java 17 has standard `java.lang.classfile`.” | Standard API exists from JDK 24 | Run with JDK 24+ |
| “Parsing `.class` is equivalent to class loading.” | `ClassModel` is a byte representation, not `Class<?>` | Keep the two conceptual models separate |
| “Bytes can be modified after the callback returns `null`.” | That callback already signaled no transformation | Transform and return bytes immediately per contract |

## 11. Safe Pipeline Design Workflow

~~~text
Input .class -> identify source/version/hash
            -> bound worker count
            -> copy/read worker-owned bytes
            -> separate ClassFile.of().parse
            -> read only needed metadata/code
            -> catch parse as well as accessor errors
            -> immutable Summary/DTO
            -> publish via synchronized Future/queue
            -> cache results and output report
~~~

Technical checklist:

- [ ] Using a JDK that supports the Class-File API.
- [ ] Byte array is not mutated during analysis.
- [ ] Do not share `ClassModel`/child models without full synchronization.
- [ ] Results crossing thread boundaries contain extracted, deeply immutable data.
- [ ] Access only the parts of the class file actually needed.
- [ ] Handle `IllegalArgumentException` from `parse` **and** accessors.
- [ ] Task pool/cache is bounded, with proper ownership and cache keys.
- [ ] Tested with malformed inputs, large classes, different class loaders/versions, and concurrency contention.

### Self-Check

1. Why is `ClassModel` immutable yet not guaranteed to be thread-safe by default?
2. Does `model.methods().size()` necessarily decode all bytecode?
3. Why can a class-file error be thrown at `method.code()` after a successful `parse`?
4. In the two-worker example, why are `source.clone()` and `Summary` used together?
5. Why should `List.copyOf(model.methods())` not be used as a shared snapshot?
6. If caching by class name, how can different class loaders or builds cause incorrect results?
7. Why should a background thread not access a `ClassModel` obtained in a transformer callback?
8. When bytecode needs to be modified, why do builders/transforms return new bytes instead of mutating the model?
9. Why does the sample code require JDK 24 even though many common Java examples run on Java 17?

**Key takeaway:** The Class-File API has an **immutable logical representation** and **on-demand parsing**. These two properties make reading and transforming bytecode efficient, but due to lazy inflation, the documentation **does not guarantee model thread safety**. Keep models scoped to a single task or synchronize every access path; the easiest approach to test is returning **immutable value snapshots** to other threads.

### Official Documentation

- [Java 24 — java.lang.classfile: immutable models, lazy parsing, thread-safety](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/package-summary.html)
- [Java 24 — ClassFile: parse, transformClass, verify](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassFile.html)
- [Java 24 — ClassModel](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/ClassModel.html)
- [Java 24 — MethodModel](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/classfile/MethodModel.html)
- [JEP 484 — Class-File API](https://openjdk.org/jeps/484)
