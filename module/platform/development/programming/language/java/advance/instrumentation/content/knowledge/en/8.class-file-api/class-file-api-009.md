# Generating Stack Maps and Resolving Inheritance with ClassHierarchyResolver

When generating or transforming Java bytecode that contains conditional branches, loops, and exception handlers, the JVM needs to know the **verification types** of values in the *local-variable array* and *operand stack* at key control-flow points. This information is typically encoded in each method's `StackMapTable` attribute. If this information is wrong, the bytecode may fail verification and throw a `VerifyError`, even if the syntax of each individual instruction looks valid.

With the standard **Class-File API** in `java.lang.classfile` (standard since **JDK 24**, per JEP 484), the class file builder can generate stack maps automatically. Computing frames sometimes requires knowing what common superclass two reference types share, whether a name is an interface, or which type is compatible with which. **`ClassHierarchyResolver`** provides class hierarchy data for stack map generation and class file verification.

This lesson addresses five practical questions:

1. What does `StackMapTable` record, and why do control-flow branches require frames?
2. Which options does the Class-File API provide to generate, reuse, or drop stack maps?
3. Where does `ClassHierarchyResolver` look up parent/child relationships without forcing class loading through the system class loader?
4. How do you choose a resolver in offline tools, multi-class-loader applications, and Java agents?
5. How do you verify the output with `javap`, `ClassFile.verify`, and a real JVM, rather than only seeing the build function return `byte[]`?

> **Version boundary:** `java.lang.classfile.ClassFile` and `java.lang.classfile.ClassHierarchyResolver` are standard APIs starting in **JDK 24**. The examples below that use these two APIs directly require **JDK 24+** (the testing instructions use **JDK 25**). Java 17–23 **do not have this same standard API**; you can still study/inspect `StackMapTable` using `javac`, `javap`, and the JVM, but you cannot compile `RebuildFrames.java` with `javac 17`. Do not confuse the standard JDK 24 API with earlier preview releases.

## 1. Stack maps are information for the verifier, not debug metadata

In the JVM, a method's `Code` attribute contains instructions, `max_stack`, `max_locals`, exception handlers, and optional attributes. `StackMapTable` is an attribute of `Code` used for **verification by type checking**; it does not contain runtime object values and is not a source-line table.

A frame describes the **type state** at a bytecode offset:

```text
Frame at bytecode offset X
  locals:
    slot 0 -> Integer
    slot 1 -> Object(java/lang/String)
    slot 2 -> Top / other type depending on state
  operand stack:
    entry 0 -> Object(java/lang/Number)
    ...
```

This is an illustrative model, not the exact output of a specific method. Verification types include `Integer`, `Float`, `Long`, `Double`, `Null`, `Object`, `Top`, `UninitializedThis`, and `Uninitialized`; distinguish these from local variable names/types in `LocalVariableTable`.

| Structure | Purpose | Needs class hierarchy? |
|---|---|---|
| `Code` instructions | Instructs the JVM what to execute | May need type understanding for verification/transformation |
| `StackMapTable` | Declares type state at verification points | **Yes**, when merging reference types from branches |
| `LocalVariableTable` | Variable name, descriptor, slot, and scope for debugging | Not used as the source of truth by the verifier |
| `LineNumberTable` | Maps bytecode offsets to source line numbers | Does not resolve inheritance relationships |
| `ClassHierarchyResolver` | Provides superclass/interface info to the Class-File API | The component itself that enables type relationship inference |

### 1.1. Important control-flow join points

```text
                 if (flag)
                 /      \
             branch A  branch B
             new Left  new Right
                  \      /
                   \    /
                    JOIN  <--- needs a verification type accepting both
                      |
                   continue
```

If `Left extends Base` and `Right extends Base`, the join point can use `Base` as the common reference type. To find this information, the tool must know:

```text
Left  -> superclass Base
Right -> superclass Base
Base  -> superclass java.lang.Object
```

If the resolver mistakenly thinks `Left` is a subclass of another type, the output may use an incompatible frame; the error often only surfaces when the JVM verifies the new class.

Not **every** instruction needs its own frame. The JVM Specification defines frame locations and compression encodings (such as `same_frame`, `append_frame`, `full_frame`). The initial frame is inferred from the method descriptor and entry conditions, without needing manual copying for every bytecode offset.

### 1.2. `offset_delta` and characteristics of StackMapTable

`StackMapTable` encodes frames in bytecode order, using `offset_delta` to compress offsets instead of repeating the full BCI. The specific frame type depends on the local/stack state and the encoding optimizations of the class file generation tool.

- **BCI (bytecode index)** is the offset within the `code[]` array of the **current method**, not a source line number.
- For class file major version **50.0** or higher, if `StackMapTable` is absent, the JVMS defines an **implicit stack map** equivalent to a table with 0 entries. This does **not** mean a method with arbitrary branches/handlers will pass verification if required frames are missing.
- At most one `StackMapTable` attribute instance may appear in a `Code` attribute.
- When inserting/removing instructions, bytecode offsets, branch targets, exception ranges, and local/stack types can change; therefore, old stack maps may no longer be usable.

Conclusion: **Stack maps are type proofs for the verifier**, not debug traces or runtime values.

## 2. Baseline experiment with Java 17+: observing a type merge point

Create the **`MergeTarget.java`** file below. This section uses standard Java and compiles/runs on both **JDK 17** and **JDK 25**:

```java
class Base {
    String name() { return "base"; }
}

class Left extends Base {
    @Override String name() { return "left"; }
}

class Right extends Base {
    @Override String name() { return "right"; }
}

public final class MergeTarget {
    public static Base select(boolean left) {
        return left ? new Left() : new Right();
    }

    public static void main(String[] args) {
        System.out.println(select(true).name());
        System.out.println(select(false).name());
    }
}
```

In the directory containing the file:

```shell
javac MergeTarget.java
java -Xverify:all MergeTarget
javap -v -p MergeTarget
```

**Program stdout:**

```text
left
right
```

The `javap -v -p` output is quite long. Find the `select(boolean)` method and the `StackMapTable` section inside `Code`. On a typical OpenJDK/JDK 21 build, you may see something similar to:

```text
StackMapTable: number_of_entries = 2
  frame_type = 14 /* same */
  frame_type = 70 /* same_locals_1_stack_item */
    stack = [ class Base ]
```

The exact offsets and encoding are **dependent on the compiler/JDK**, not values guaranteed to be fixed across all JDKs. The key point is that the frame at the merge branch can represent **`Base`**, the superclass of `Left` and `Right`.

The `javap` command only **reads the generated class file**. It does not generate or rewrite stack maps. The `java -Xverify:all` option instructs the JVM to perform more thorough verification; this is a good runtime check after editing bytecode, but it **does not replace** testing application behavior for correctness.

### 2.1. Why can `Base` appear on the stack?

The conditional expression `left ? new Left() : new Right()` creates two paths. After the branch, the next instruction needs to see an acceptable type state regardless of which path ran. `Base` fits because both objects are instances of subclasses of `Base`.

Distinguish between:

- **Method source/target type:** `Base` in `public static Base select(...)`.
- **Verification type at the join point:** the type the verifier accepts on the operand stack, which may appear in `StackMapTable`.
- **Actual runtime type:** `Left` or `Right` depending on the value of `left`; the frame does not store which instance was created.

A simple debugging technique is to correlate object creation instructions, bytecode branches, and frames in `javap`, rather than looking only at Java source code.

## 3. Class-File API and the three StackMapsOption modes

When writing or transforming `.class` files with `ClassFile.of(...)`, you can choose a `ClassFile.StackMapsOption`:

| Option | Behavior | When to use |
|---|---|---|
| `STACK_MAPS_WHEN_REQUIRED` | **Default**: attempts to reuse old stack maps if code and exception handlers remain compatible; otherwise regenerates them | Routine transforms where you want to avoid unnecessary recomputation |
| `GENERATE_STACK_MAPS` | **Always runs stack map generation**, even if the old ones could be reused; reports errors early if generation fails | Testing resolvers, forcing new frame generation, changing control flow |
| `DROP_STACK_MAPS` | **Does not automatically generate** stack maps | Only when actively supplying a compatible `StackMapTableAttribute` or in verified special cases |

Configuration syntax:

```java
ClassFile defaultContext = ClassFile.of();

ClassFile forced = ClassFile.of(
        ClassFile.StackMapsOption.GENERATE_STACK_MAPS
);
```

`ClassFile.of()` is a configuration context for **reading/writing/generating** class files. `StackMapsOption` is not a `javac` option and is not an attribute in an agent manifest.

### 3.1. Why isn't `DROP_STACK_MAPS` a fix for VerifyError?

If the code has branches or exception handlers that require frames under the JVMS, dropping `StackMapTable` can cause the class file to fail verification. `DROP_STACK_MAPS` is only appropriate if you **manually supply a valid `StackMapTableAttribute` to `CodeBuilder`** or have a specific class-format reason. Do not use "drop it and let the JVM guess" as a general solution for modern class files.

`StackMapTableAttribute` is a **derived attribute** in the Class-File API: it does not appear as a normal element when traversing a `CodeModel`. The library usually manages it when writing the class file, unless you use the appropriate manual mode.

### 3.2. Frame generation can fail right at write time

Depending on the JVM/class version and bytecode, stack map generation may throw `IllegalArgumentException`, for example:

- **Unreachable code** appears after an unconditional jump in a way the generation algorithm does not accept.
- Bytecode uses `jsr`/`ret` (legacy jump subroutines), which are incompatible with standard stack-map generation.
- The resolver cannot obtain required hierarchy info or encounters a class that is not permitted to be queried.
- Invalid data/labels/code model, or unsatisfied class file construction constraints.

`ClassFile.DeadCodeOption` exists to handle certain dead-code cases; do not interpret that as meaning all dead code can automatically be turned into valid bytecode. The stack map generation library **does not prove business logic** or compliance with the redefine/retransform restrictions of a running JVM.

## 4. What information does `ClassHierarchyResolver` provide?

In `java.lang.classfile`, `ClassHierarchyResolver` is a **functional interface**; its core method is:

```java
ClassHierarchyResolver.ClassHierarchyInfo getClassInfo(
        java.lang.constant.ClassDesc classDesc);
```

The method takes a `ClassDesc` representing **a class or interface**, and returns:

- `ClassHierarchyInfo.ofClass(superClassDesc)` if it is a regular class, declaring its **direct superclass**; for `java.lang.Object`, the superclass may be `null`.
- `ClassHierarchyInfo.ofInterface()` if it is an interface.
- `null` if the resolver **does not know** that class name (giving another resolver a chance to answer in an `orElse` chain).
- `IllegalArgumentException` if the class **should not be queried**, for instance if it is inaccessible under the resolver's policy. This is **different** from `null` and can cause generation to fail.

The returned info is hierarchy metadata, **not** a `Class<?>` instance, not replacement bytecode, does not contain method bodies, and is not a class loader. It supports the Class-File API's type analysis.

### 4.1. Key factory methods to know

| Factory/method | Metadata source | Strengths | Risks/limitations |
|---|---|---|---|
| `ClassHierarchyResolver.defaultResolver()` | Core reflection via the **system class loader** | Convenient for classes already on the system loader | Can trigger class loading; **unsuitable** for many instrumentation contexts |
| `ofClassLoading(ClassLoader)` | Loads classes via the loader and uses reflection | Sees classes visible to that loader | Can trigger class loading when you only want to read metadata |
| `ofClassLoading(MethodHandles.Lookup)` | Reflection via a lookup with appropriate access rights | Clear accessibility constraints | Inaccessible classes may throw `IllegalArgumentException` |
| `ofResourceParsing(ClassLoader)` | Reads `.class` resources via the loader | Usually avoids loading classes just to learn hierarchy | Resources may be absent or not match classes defined at runtime |
| `ofResourceParsing(Function<ClassDesc, InputStream>)` | Application supplies class bytes from archives, repositories, in-memory maps, etc. | Great for offline/agent use; full control of byte source | Must supply accurate bytes/hierarchy, handle streams and I/O errors |
| `of(Collection<ClassDesc>, Map<ClassDesc, ClassDesc>)` | Collection of interfaces + class → superclass map | Compact, deterministic when metadata is known | Does not automatically discover missing names in the map |
| `resolver.orElse(other)` | Primary resolver, falling back when result is `null` | Combines metadata from multiple sources | Does not "rescue" an `IllegalArgumentException` from the primary resolver |
| `resolver.cached()` | Caches query results, including missing results per implementation | Reduces repeated lookup cost | Cache can go stale; default implementation is **not thread-safe** |

**Do not call `getClassInfo` yourself in application code to "test the resolver"** as a high-level API: the Javadoc states this is a method used by the Class-File API for querying; users normally configure a resolver via `ClassFile.ClassHierarchyResolverOption`. If you need diagnostics, test the class-file output and your own metadata source.

### 4.2. Why is the default resolver often insufficient for Java agents?

The Javadoc explicitly states that the default resolver uses reflection via the **system class loader**. During instrumentation:

1. A class may be defined by a **custom class loader** (web container, plugin framework, application server).
2. Inside `transform(...)`, the target class may **currently be in the process of being defined**. Attempting to load that class via reflection right inside the callback can cause reentrancy, class-loading cycles, deadlocks, or fetch the wrong version of the class.
3. Bytecode may reference newly generated classes that **do not yet exist in the JVM**.
4. A single class name is not enough to distinguish two classes with the same name defined by two different defining class loaders.
5. The system loader may not see resources inside nested JARs, modules, or custom resource stores.

Therefore, choose a resolver whose metadata **matches the exact class-loader view and exact byte version**. When a suitable `.class` source is available, `ofResourceParsing(...)` is usually a safer choice than actively loading classes during transformation.

### 4.3. Passing a resolver into a ClassFile context

```java
ClassHierarchyResolver resolver =
        ClassHierarchyResolver.ofResourceParsing(
                ClassLoader.getSystemClassLoader());

ClassFile context = ClassFile.of(
        ClassFile.ClassHierarchyResolverOption.of(resolver),
        ClassFile.StackMapsOption.GENERATE_STACK_MAPS
);
```

This is a **valid API configuration snippet for JDK 24+**, though it does not yet include the parse/transform steps; a complete runnable example is in Section 5. `ClassFile.ClassHierarchyResolverOption.of(...)` is different from `ClassHierarchyResolver.of(...)`:

- `ClassHierarchyResolver.of(...)`: **creates a resolver from metadata**.
- `ClassFile.ClassHierarchyResolverOption.of(resolver)`: **attaches a resolver to the configuration** for parsing/building/transforming/verifying.

Confusing the two `of` methods is a common compilation error when first learning the API.

## 5. Runnable JDK 25 example: regenerating StackMapTable with custom hierarchy metadata

We use **`MergeTarget.java` from Section 2**, keeping `Base`, `Left`, `Right`, and the `select(boolean)` method unchanged. Add the **`RebuildFrames.java`** file below. Implementation steps:

- Parse the old class file into a `ClassModel`.
- Provide metadata directly for the example's local classes so we do not have to rely on reflection to resolve them.
- Use `ofResourceParsing` as a fallback for JDK classes if needed.
- Force **regeneration** of stack maps using `GENERATE_STACK_MAPS` and write the output to the `out` directory.
- Run `ClassFile.verify` with the same resolver to detect verification errors, then verify with the JVM.

### 5.1. `RebuildFrames.java`

```java
import java.lang.classfile.ClassFile;
import java.lang.classfile.ClassHierarchyResolver;
import java.lang.classfile.ClassTransform;
import java.lang.constant.ClassDesc;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.Set;

public final class RebuildFrames {
    public static void main(String[] args) throws Exception {
        ClassDesc object = ClassDesc.of("java.lang.Object");
        ClassDesc base   = ClassDesc.of("Base");

        // Known metadata: which class has which direct superclass?
        Map<ClassDesc, ClassDesc> parent = Map.of(
                base,                       object,
                ClassDesc.of("Left"),        base,
                ClassDesc.of("Right"),       base,
                ClassDesc.of("MergeTarget"), object
        );

        // No custom interfaces in this example.
        ClassHierarchyResolver local =
                ClassHierarchyResolver.of(Set.of(), parent);

        // Only query the fallback when local metadata lacks the requested class.
        ClassHierarchyResolver resolver = local.orElse(
                ClassHierarchyResolver.ofResourceParsing(
                        ClassLoader.getSystemClassLoader()));

        ClassFile cf = ClassFile.of(
                ClassFile.ClassHierarchyResolverOption.of(resolver),
                ClassFile.StackMapsOption.GENERATE_STACK_MAPS
        );

        byte[] original =
                Files.readAllBytes(Path.of("MergeTarget.class"));

        // Pass through ClassElements; force stack map regeneration
        // per the configured context without modifying method logic.
        byte[] rebuilt = cf.transformClass(
                cf.parse(original), ClassTransform.ACCEPT_ALL);

        Path output = Path.of("out", "MergeTarget.class");
        Files.createDirectories(output.getParent());
        Files.write(output, rebuilt);

        System.out.println("REBUILT");
        System.out.println("VERIFY_ERRORS=" + cf.verify(rebuilt).size());
    }
}
```

**Key lines:**

- `ClassDesc.of("Base")` is the **descriptor of a class in the default package**, not a string like `LBase;` and not `Base.class`.
- `Map<ClassDesc, ClassDesc>` describes **direct superclass** relationships, not the full graph of methods.
- `ClassHierarchyResolver.of(Set.of(), parent)` creates a resolver from metadata. An empty interface set is accurate for the **four classes defined by this experiment**, not a claim that the JDK has no interfaces.
- `local.orElse(...)` lets another resolver answer if local metadata is missing. The fallback is only tried when the primary resolver returns `null`.
- `ClassTransform.ACCEPT_ALL` forwards all class elements to the builder; the `GENERATE_STACK_MAPS` option ensures the builder does not merely copy the old frame table when generation is requested.
- `Files.write` to `out/MergeTarget.class` **does not overwrite** the input `MergeTarget.class`. The original `Base`/`Left`/`Right` classes remain in the current directory.
- `cf.verify(rebuilt)` returns the Class-File API's list of `VerifyError`s; `size()==0` is the expected result in a valid example, but you still need to test with a real JVM.

### 5.2. Compile and run commands

**Use JDK 25** for both `javac` and `java` in the Class-File API steps; check `java -version` and `javac -version` if multiple JDKs are installed.

```shell
javac MergeTarget.java RebuildFrames.java
java RebuildFrames
javap -v -p -classpath out MergeTarget
java -Xverify:all -cp out:. MergeTarget
```

`javac` places `MergeTarget.class`, `Base.class`, `Left.class`, `Right.class`, and `RebuildFrames.class` in the current directory. `java RebuildFrames` creates `out/MergeTarget.class`.

**Expected stdout when `RebuildFrames` completes and the resolver has complete metadata:**

```text
REBUILT
VERIFY_ERRORS=0
```

In the `javap` output, look for `select(boolean)` and `StackMapTable`; entry counts and encodings may differ across JDK versions/transform styles. Because `-classpath out` specifies the path to the rebuilt class, `javap` is reading the output, **not** mistakenly reading the input in the current directory.

Finally, `java -Xverify:all -cp out:. MergeTarget` **prioritizes the `out` directory** while still finding `Base`/`Left`/`Right` in `.`. Expected stdout:

```text
left
right
```

This is an important post-check: the JVM can load/verify the new class and the branching logic produces the same result as before.

**QA scope:** the example uses methods, options, and factories from the official **JDK 25** API. The exact `StackMapTable` output printed by `javap` depends on the compiled class file and JDK version, so do not test by verbatim matching of frame counts/BCIs. If run on JDK 17 or 21, `RebuildFrames.java` will not compile because `java.lang.classfile` does not exist in those versions.

### 5.3. What actually proves the resolver worked?

In the example, completing class generation and `cf.verify(...)` confirms **the hierarchy dataset was sufficient for this processing pass**. However, do not conclude that the API actually called `getClassInfo` on *every* name you put in the map; the algorithm may only query the types it needs.

If you need to measure the exact names looked up in an investigative agent, provide a custom `ClassHierarchyResolver` with safe logging/metrics and attach it via `ClassHierarchyResolverOption`. Avoid logging from inside a resolver using code that triggers additional class loading in production.

## 6. Deep dive into getClassInfo and ClassHierarchyInfo

### 6.1. "Unknown" is different from "query disallowed"

Two outcomes are often conflated:

```text
getClassInfo(classDesc) returns null
  -> resolver has no metadata
  -> resolver.orElse(...) can try the second source

getClassInfo(classDesc) throws IllegalArgumentException
  -> query rejected/invalid per the resolver contract
  -> do not assume orElse(...) will continue
```

When writing a custom resolver, only return `null` if it is genuinely **unknown**. If you know the query is disallowed or the metadata is definitely unreliable, you may explicitly report an error according to policy. Do not return fake parent info to "work around" errors.

### 6.2. Valid info types

```java
// Two illustrative API expressions (JDK 24+):
var declaredClass =
    ClassHierarchyResolver.ClassHierarchyInfo.ofClass(
        ClassDesc.of("java.lang.Object"));

var declaredInterface =
    ClassHierarchyResolver.ClassHierarchyInfo.ofInterface();
```

This **illustrative** snippet assumes imports of `java.lang.constant.ClassDesc` and `java.lang.classfile.ClassHierarchyResolver`. For a concrete subclass, `ofClass(...)` takes the descriptor of the **direct superclass**. For an interface, `ofInterface()` indicates it is an interface per the resolver contract; do not treat it as a class with an arbitrary superclass.

Do not automatically treat `null` from `ClassHierarchyInfo.ofClass(null)` as valid for **every** unknown class; a `null` superclass is only appropriate when there is no superclass by definition, typically `java.lang.Object`. For a normal class, fake metadata will lead to incorrect type-state analysis.

### 6.3. Does the resolver capture full interface relationships?

The API stores "this is an interface" and the superclass for classes; verification type analysis under the JVMS is **not the same** as building a complete graph of all interfaces/implementations/methods. When choosing metadata, follow the exact data `ClassHierarchyResolver` requires rather than assuming it is a full replacement for reflection/class graphs.

When `Left` and `Right` both inherit from `Base` as in the example, superclass info is the core piece. When bytecode uses interfaces, arrays, or multiple class loader layers, the resolver must also have sufficient information for **every reference type the generator needs to query**; do not guess a type from its package name or force `java.lang.Object` for everything.

### 6.4. Does a resolver miss a type only on tricky inputs?

A generator may only need hierarchy info when it encounters a branch with two different reference types. In a linear method, the tool might not need to query the resolver for a custom class at all. Thus, a resolver missing data can **hide bugs** until you transform:

- conditional expressions;
- loops with reference variables;
- `try/catch` and exceptional control-flow edges;
- branches calling methods that return different subtypes;
- methods with array/component reference types;
- injected code that changes operand stack height or types.

Do not use "successfully transformed one simple class" as proof that the resolver is sufficient for the entire application.

## 7. Resolvers in agents: why avoid loading classes during transform?

A Java agent via `java.lang.instrument.ClassFileTransformer` receives the byte array of a class being loaded or redefined/retransformed:

```java
@Override
public byte[] transform(
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain domain,
        byte[] classfileBuffer) {
    // Snippet illustrating the callback context, not a standalone agent.
    return null;
}
```

If the agent uses the Class-File API **inside** this callback, `ClassHierarchyResolver.defaultResolver()` may query through the system class loader and trigger new class loading. At a moment when the target class may not have finished being defined, doing this by default is unsafe.

Design strategies:

1. Identify the **target's loader** from the `loader` parameter (which may be `null` for the bootstrap loader). Do not apply a resolver from another app loader just because a class has the same binary name.
2. Prefer metadata from **bytes/class resources already safe to read** instead of triggering class loading to call `getSuperclass()`.
3. If the target class is currently being defined and has no accurate resource yet, supply metadata from the **class bytes currently being transformed** or a byte store captured from the exact build/loader; do not force the system loader to reload the target.
4. Choose `ofResourceParsing(loader)` when resource lookup accurately reflects the loader; for class loaders that call `defineClass(byte[])` from network/cache without exposing resources, use `ofResourceParsing(Function<ClassDesc,InputStream>)` and supply bytecode from the right source.
5. For JDK/boot classes, use a resolver configured to locate the right module/runtime metadata. Do not assume a `null` loader has the same resource behavior as the system loader.
6. Scope **caches by class loader + build/byte version** if metadata can change; `ClassDesc` alone does not represent the defining loader.

### 7.1. Attaching a resolver to the context inside a callback

Abbreviated configuration example:

```java
ClassHierarchyResolver resolver =
        ClassHierarchyResolver.ofResourceParsing(loader);

ClassFile cf = ClassFile.of(
        ClassFile.ClassHierarchyResolverOption.of(resolver),
        ClassFile.StackMapsOption.STACK_MAPS_WHEN_REQUIRED
);
```

This is an **architectural pattern**, not a complete callback: `loader` can be `null`; the class loader might not expose resources for the target currently being processed; and a transformer also needs filtering rules, error handling, bytecode generation, and to avoid recursing into the agent's own dependencies.

Do not mechanically call `ofResourceParsing(loader)` in every situation without considering loader design and class byte sources. For difficult cases, use a resolver that combines **high-confidence** metadata with an appropriate fallback.

### 7.2. Avoiding wrong global caches keyed by class name

Example of two plugin loaders:

```text
loader-A:
  com.example.PluginType extends com.example.BaseA

loader-B:
  com.example.PluginType extends com.example.BaseB
```

Same `ClassDesc.of("com.example.PluginType")`, but two different class definitions. If you cache `PluginType → BaseA` and reuse it to build frames for the class defined by `loader-B`, you have picked the wrong hierarchy. You can produce class bytes with wrong verification types even when the class name looks right.

Safe practices:

- Scope resolvers/caches to the appropriate loader and artifact/class version.
- Do not share a JVM-wide name → superclass map unless those names genuinely belong to the same managed class space.
- Do not retain caches indefinitely if class loaders can be unloaded; avoid holding unnecessary strong references to loaders.
- Use `cached()` consciously: the default is not thread-safe; `null` results are also cached per contract; subsequent data changes do not auto-refresh.
- If concurrency is needed, consider `cached(Supplier<Map<...>> cacheFactory)` with a carefully chosen thread-safe map while understanding the requirement to support `null` values. Do not arbitrarily use `ConcurrentHashMap` if the cache implementation needs to store `null`.

## 8. Comparing reflection and resource-parsing resolvers

| Question | `ofClassLoading(...)` | `ofResourceParsing(...)` |
|---|---|---|
| How does it look up hierarchy? | Via class loading and reflection | Reads class file resources or an application-supplied `InputStream` |
| Risk of triggering class loading? | **Yes**; especially notable in agents | Avoids loading classes just to inspect metadata, though resource lookup/I/O still has side effects |
| Depends on loader visibility? | Yes | Yes, or depends on the stream-providing function |
| Suitable for not-yet-defined classes? | Should not assume it can load safely | Can be suitable if accurate bytes are available from build/cache/transform context |
| Suitable for classes in JARs or modules? | When visible to the loader/lookup | When the resolver can locate the right class-file resource |
| Needs resource lifecycle management? | Handled by class loading/reflection | May need to manage streams and I/O errors in the function |
| Can data be stale? | Yes, if using the wrong loader/lookup | Yes, if the resource on disk differs from the loaded class version |

**Instrumentation priority:** do not let *stack map computation* accidentally trigger a wave of new class loading right while the system is loading classes. A byte-based resolver may be the better tool, though you still must account for performance, class loaders, and I/O limits.

## 9. When to generate stack maps, and when to reuse them?

### 9.1. Minor changes that do not affect instructions/control-flow

For example, changing an independent class attribute without modifying method `Code`. If the builder determines the old stack maps remain compatible, **`STACK_MAPS_WHEN_REQUIRED`** can reuse them. Using `GENERATE_STACK_MAPS` is still valid but adds overhead and may surface hierarchy issues that wouldn't be needed if reusing.

### 9.2. Injecting probes into a method body

If you insert new instructions at the start/middle of a method, changing offsets, locals, operand stack, or exception handlers, the old stack maps may no longer fit. The Class-File API can regenerate frames as needed, provided it has a sufficiently accurate hierarchy to resolve merges. Do not manually copy the old `StackMapTable` over to the output just because two methods share the same name.

### 9.3. Rebuilding an entire method with new control-flow

For new code, especially with branches/handlers, new **generation** is usually required. Enabling `GENERATE_STACK_MAPS` is the direct way to exercise the frame generation path and resolver. Even so, you must still ensure valid bytecode **stack discipline**, return types, branch targets, handler ranges, and class-file version limits.

### 9.4. Manual frame creation

Rare cases that require per-frame control can construct `StackMapTableAttribute` using the advanced API and use `DROP_STACK_MAPS` to prevent the generator from overwriting it. This task requires understanding `StackMapFrameInfo`, labels, and offsets; a missing frame at a branch or handler usually leads to `VerifyError`. Unless you have a very clear reason, use automatic generation and a proper resolver.

## 10. Common errors: causes and diagnostics

| Symptom | Possible cause | What to do |
|---|---|---|
| `javac` reports `java.lang.classfile` not found | Using JDK 17–23 instead of JDK 24+ | Check `javac -version`; use JDK 25 for the examples |
| `transformClass` throws `IllegalArgumentException` while generating stack maps | Missing hierarchy info, rejected query, dead code, legacy `jsr/ret`, or class-file inconsistency | Log the cause, identify the class/loader, inspect bytes/options/resolver |
| `VerifyError: Inconsistent stackmap frames` | Local/operand stack frame incompatible with bytecode at branch/handler | Use `javap -v` to inspect BCI/frames; try generation with accurate hierarchy; run `-Xverify:all` |
| `NoClassDefFoundError` when resolver attempts to load a class | Class not yet available/wrong loader/circular loading dependency | Avoid reflection-based loaders in callbacks; use proper resources/class bytes |
| Generation "succeeds" but the JVM rejects the class | Resolver returned fake hierarchy, violated version/method constraints, or final bytecode is invalid | Test with a real JVM, compare bytes/class version and loader |
| Using `defaultResolver()` in a custom-loader app | System loader does not know types from plugin loaders | Use a loader-scoped resolver or plugin repository/bytes |
| Cache returns wrong results between two deployments | Metadata changed but resolver is cached | Scope cache by build/loader, invalidate per lifecycle |
| `DROP_STACK_MAPS` to "fix" a stack map error | Missing frames needed by the verifier | Use valid generation/frames; do not drop them to bypass errors |
| `StackMapTable` does not appear when traversing `CodeModel` | Attribute is a derived property, not delivered as a normal element | Check `StackMapTableAttribute`, `javap -v`, and map generation options |
| `cf.verify(bytes).size()==0` but app has logic bugs | Verifier checks type/class-file constraints, **not** business logic | Write more tests and run real code |
| Agent deadlocks/reenters during transform | Resolver uses class loading/reflection or heavy logging inside callback | Switch to offline/resource metadata; reduce dependencies in callback |
| Output runs the old class version | Wrong classpath priority, mixed build artifacts | Check `-cp out:.`, `javap` path, and class byte hashes/versions |

### Ordered debugging workflow

1. Record the **tool's JDK version**, input `.class` major version, loader, and source of class bytes.
2. Confirm the actual `ClassFile.StackMapsOption` in use: default or forced regeneration.
3. Inspect the **exact** output bytes with `javap -v` to see stack frames and branch targets.
4. When generation fails, verify the resolver knows all key types at merge branches, superclasses/interfaces, and array components.
5. For runtime agents, ensure resolver data matches the target's **defining loader**, not just the system loader.
6. Use `ClassFile.verify` to get a list of errors, then run the JVM with `-Xverify:all` and behavioral tests.
7. Report success only when **the class bytes are accepted by the JVM and the intended functionality still runs**.

## 11. Misconceptions to avoid

1. **"If `StackMapTable` already exists, inheritance hierarchy isn't needed."** False when transformed code invalidates the compatibility of old frames; the generator needs an accurate hierarchy.
2. **"`ClassHierarchyResolver` automatically loads every class properly."** False. It depends on the resolver factory, loader, resources, and visibility; the default uses the system loader via reflection.
3. **"`ClassDesc` always represents the defining class loader."** False. It describes a type symbol, not distinguishing two definitions with the same binary name in different loaders.
4. **"`ofResourceParsing` is guaranteed to see classes defined by a custom loader."** False if the loader does not expose the corresponding resources.
5. **"Whenever a superclass is missing, just return `java.lang.Object`."** This can produce incorrect results; do not fake the hierarchy to force the generator to run.
6. **"Enabling `GENERATE_STACK_MAPS` automatically makes bytecode valid."** False. It can throw errors; the code must also satisfy all other verifier rules.
7. **"`DROP_STACK_MAPS` is equivalent to letting the JVM re-infer types."** False as a general strategy for modern class files.
8. **"`StackMapTable` is a local variable debug table."** False; the two attributes solve different problems.
9. **"`cached()` is always thread-safe."** False; the default factory uses a non-thread-safe map.
10. **"Successfully building one class proves the resolver has enough data for all branches."** False; only types actually queried by the generator expose missing data.
11. **"Stack maps are pointers to live objects."** False; they carry verification types, not runtime values.
12. **"JDK 17 includes the same standard `Class-File API`."** False; the classes in the `RebuildFrames` example require JDK 24+.

## 12. Self-check questions

1. **What does `StackMapTable` serve?** It provides type states for the JVM verifier at key control-flow points.
2. **Suppose `Left extends Base` and `Right extends Base`. When two branches merge, why is hierarchy needed?** Because the generator needs a verification type compatible with values coming from both branches, typically `Base`.
3. **How does `GENERATE_STACK_MAPS` differ from `STACK_MAPS_WHEN_REQUIRED`?** One forces regeneration, while the other can reuse old stack maps if they remain compatible.
4. **Does `DROP_STACK_MAPS` automatically resolve branches missing frames?** No. If the code needs frames, the author must supply valid frames.
5. **What source does `ClassHierarchyResolver.defaultResolver()` use?** Reflection via the system class loader; it carries class-loading risks and cannot see custom-loader types.
6. **Does `ClassHierarchyResolver.ofResourceParsing(...)` call `Class.forName` for each name?** There is no such contract; it obtains hierarchy from class-file resources/streams rather than actively using reflection-based class loading.
7. **Is `getClassInfo(...)` returning `null` different from throwing `IllegalArgumentException`?** Yes. `null` means unknown, whereas the exception can signal a disallowed query and halt generation.
8. **Why shouldn't a `ClassDesc`-keyed map be shared across all class loaders?** Because the same type name can have different superclasses depending on the defining loader.
9. **Is `ClassFile.verify(rebuilt).size()==0` enough to declare business logic correct?** No. JVM verification and behavioral tests are needed.
10. **Why shouldn't a reflection resolver be used inside a transformer for a class currently being defined?** There is a risk of triggering class loading, reentrancy, or dependency cycles right in the middle of loading.
11. **Why does `javap -v` still work well on Java 17 even though the standard Class-File API requires JDK 24+?** `javap` is a class-file inspection tool, whereas `java.lang.classfile` is a programmatic API standardized later.
12. **If an old `StackMapTable` is kept but instruction offsets change, what can happen?** Frames no longer match BCIs/type states and may be rejected by the verifier with `VerifyError`.
13. **When is a custom resolver like `of(Collection, Map)` appropriate?** When reliable metadata is already available (e.g., a build index or module class bytes) and you want to avoid class loading to look up parent/interface relationships.
14. **If the resolver lacks metadata for a newly generated class in the pipeline, what should you do?** Supply the real hierarchy from the generated bytes/repository, or report a clear error; do not fabricate a superclass.

## 13. Official references

- [OpenJDK JEP 484 — Class-File API](https://openjdk.org/jeps/484): standard API from JDK 24; context for replacing internal bytecode APIs.
- [Java SE 25 — Class-File API package](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/package-summary.html): how to read, generate, and transform class files; models, transforms, attributes.
- [Java SE 25 — ClassHierarchyResolver](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/ClassHierarchyResolver.html): `getClassInfo`, `defaultResolver`, `ofResourceParsing`, `ofClassLoading`, `orElse`, and `cached`.
- [Java SE 25 — ClassFile.ClassHierarchyResolverOption](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/ClassFile.ClassHierarchyResolverOption.html): attaching a resolver to a context when generating/verifying.
- [Java SE 25 — ClassFile.StackMapsOption](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/ClassFile.StackMapsOption.html): `STACK_MAPS_WHEN_REQUIRED`, `GENERATE_STACK_MAPS`, `DROP_STACK_MAPS`.
- [Java SE 25 — StackMapTableAttribute](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/attribute/StackMapTableAttribute.html): derived attribute, how to generate or supply manually.
- [Java SE 25 — ClassTransform](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/classfile/ClassTransform.html): `ACCEPT_ALL` and how to forward class elements during transformation.
- [Java SE 25 JVM Specification, `4.7.4 and `4.10.1](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html): definition of `StackMapTable`, frame offsets, and the verification type system.

**Key takeaway:** `StackMapTable` is type-state verification data, while `ClassHierarchyResolver` is the metadata source the Class-File API uses to infer inheritance relationships when generating/checking frames. In an agent, choose a resolver that sees the right **class bytes, class loader, and build version**, avoiding unnecessary class loading; after generation, always verify **both the class file and actual JVM behavior**.