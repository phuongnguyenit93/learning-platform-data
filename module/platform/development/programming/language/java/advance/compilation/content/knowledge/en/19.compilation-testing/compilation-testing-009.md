# Distinguishing Stable Bytecode Output Testing from Volatile Implementation Details

## 1. The Problem: Does Changed Bytecode Mean the Program Is Wrong?

When compiling Java, `javac` turns source code into a class file containing JVM instructions, a constant pool, class/member descriptors, and additional attributes. After a small change to the source, JDK version, or compiler arguments, a `.class` file may differ byte-for-byte while **observable behavior and the public API remain correct**. Conversely, a class file differing by only a few bytes in a method name, descriptor, or access flag can break consumers.

Therefore, compilation tests need to answer the right question:

> **Which characteristics of bytecode output are a meaningful contract for consuming programs, and which characteristics are merely internal representation that can legitimately change?**

For example, a method returning a price after a 10% discount can be written in two equivalent ways for nonnegative integers:

~~~java
// Variant A: illustrative method body
return cents - cents / 10;
~~~

~~~java
// Variant B: illustrative method body
long tens = cents / 10;
return tens * 9 + cents % 10;
~~~

The two approaches can produce a different number of JVM instructions, instruction ordering, and local variable table. For `cents >= 0`, they compute the same result. A snapshot test requiring `javap -c` to match line by line may report false failures even though the actual contract has not changed. However, changing the return type from `long` to `int` or removing `public` breaks the API that consumers need.

The goal is to identify the **invariants** (what must hold) according to usage needs: types/visibility, binary compatibility, behavior, compilation constraints, and class file attributes actually used by downstream tools or the runtime. You should not assume by default that “every byte must be identical”.

## 2. What Groups of Information Does a Class File Contain?

A `.class` file has a structure defined by the JVM. Some parts directly affect linking/running the program; other parts serve compilation, debugging, reflection, instrumentation, or optimization.

| Component | Meaning | Should you compare byte-for-byte? |
|---|---|---|
| **Class name, superclass, interfaces** | Identify identity and type relationships | Check name/relationship contract; no need to compare the whole file |
| **Access flags** | `public`, `final`, `abstract`, `static`... | Check when they affect consumers |
| **Method/field name + JVM descriptor** | Constrains calls, parameter/return types at the JVM level | Crucial for ABI/binary compatibility |
| **Generic Signature, Exceptions, annotations** | Source/reflection/framework semantics when published | Check attributes that act as part of the contract |
| **Code attribute / instructions** | How a method is executed | Prefer behavioral testing; inspect instruction structure only when truly needed |
| **Constant pool** | Table referencing strings, classes, methods, fields, literals... | Indices and ordering are usually implementation details |
| **LineNumberTable, LocalVariableTable** | Support stack traces/debuggers | Usually not functional API; may change with debug flags/source |
| **StackMapTable** | Information used for type checking during bytecode verification | Test that the class can load/verify; avoid snapshotting raw frame layout |
| **Synthetic/bridge members** | Support generic erasure, lambdas, or compiler techniques | Can play an ABI role; examine impact on consumers, do not arbitrarily pin names/counts |
| **Class file major version** | Specifies the class file version supported by the JVM | Check when the product commits to running on a specific Java runtime |

In particular, the JVM `descriptor` of method `long afterTenPercent(long)` is `(J)J`: `J` represents type `long`, parentheses enclose the parameter list, and the `J` after the parentheses is the return type. If the descriptor changes, previously compiled consumer bytecode may encounter `NoSuchMethodError` when linking with the new library.

**Important note:** “Not comparing byte-for-byte” does not mean every non-API part is meaningless. Debug attributes can be a contract for a coverage analyzer; runtime annotations can be read by a framework via reflection; bridge methods can be needed to preserve binary compatibility. Decisions must follow actual consumers.

## 3. Stable Contract Levels Worth Testing

Instead of one golden snapshot for the entire `.class` file, split checks into levels with clear purposes:

| Testing level | Stability verified | Example check |
|---|---|---|
| **Source compatibility** | Does consumer source code still compile with the new API? | Compile consumer fixture alongside library/generated API |
| **Binary compatibility** | Do old consumer `.class` files still link/run with the new library? | Run pre-compiled client; watch for `NoSuchMethodError`/`IllegalAccessError` |
| **API / ABI structure** | Classes, members, descriptors, visibility, inheritance, key generic signatures | `javap -public -s` or an appropriate ABI tool |
| **Behavior contract** | Inputs/outputs, exceptions, side effects, business invariants | Unit/integration tests |
| **Runtime/JVM compatibility** | Class loads, verifies, and runs on the minimum supported Java version | `--release`, testing on the target JVM |
| **Tool-specific contract** | Annotations, metadata, or bytecode patterns used by a framework/agent | Inspect normalized metadata or run integration tests with the tool |
| **Binary reproducibility** | Artifact must be byte-for-byte identical under the same build conditions | Byte/JAR hash with controlled environment and timestamps |

The last two levels are justified exceptions: if a product requirement is a **reproducible build**, byte-for-byte identity itself becomes a contract. However, do not use that requirement by default to block harmless compiler changes in ordinary API tests.

Source compatibility and binary compatibility also differ. For instance, a generic signature change can cause consumer source compilation to fail even while the post-erasure JVM descriptor stays the same. Conversely, a previously compiled consumer needs the old member descriptor at link time; “compiling new source succeeds” does not guarantee old binaries still work.

## 4. Java 17 Example: Testing Contracts Instead of Instruction Snapshots

Create two standalone files in a `src` directory. The example demonstrates a library class and a consumer test. We check the **public method signature**, input conditions, results at boundary values, and exception message — the things consumers actually depend on.

### 4.1. Library Under Test

File `src/PriceRules.java`:

~~~java
public final class PriceRules {
    private PriceRules() {
    }

    public static long afterTenPercent(long cents) {
        if (cents < 0) {
            throw new IllegalArgumentException("cents must be nonnegative");
        }
        return cents - cents / 10;
    }
}
~~~

This API accepts a nonnegative monetary amount as an integer number of cents. It computes the remaining amount after subtracting `floor(cents / 10)`, avoiding floating-point numbers to prevent rounding issues. For negative numbers, the contract is to throw `IllegalArgumentException` with a specific message.

### 4.2. Consumer Checking Both Usable ABI and Behavior

File `src/ContractCheck.java`:

~~~java
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;

public final class ContractCheck {
    private static void equalsLong(long expected, long actual) {
        if (expected != actual) {
            throw new AssertionError(
                    "expected " + expected + ", got " + actual);
        }
    }

    public static void main(String[] args) throws Exception {
        Method method = PriceRules.class.getDeclaredMethod(
                "afterTenPercent", long.class);
        int flags = method.getModifiers();
        if (!Modifier.isPublic(flags)
                || !Modifier.isStatic(flags)
                || method.getReturnType() != long.class) {
            throw new AssertionError("Public static long API changed");
        }
        System.out.println("API: OK");

        equalsLong(0, PriceRules.afterTenPercent(0));
        equalsLong(1, PriceRules.afterTenPercent(1));
        equalsLong(9, PriceRules.afterTenPercent(10));
        equalsLong(18, PriceRules.afterTenPercent(19));
        equalsLong(90, PriceRules.afterTenPercent(100));

        try {
            PriceRules.afterTenPercent(-1);
            throw new AssertionError("Negative amount must fail");
        } catch (IllegalArgumentException expected) {
            if (!"cents must be nonnegative".equals(
                    expected.getMessage())) {
                throw new AssertionError("Exception contract changed");
            }
        }
        System.out.println("Behavior: OK");
    }
}
~~~

Run with JDK 17+ (Unix/macOS/Linux):

~~~bash
mkdir -p out
javac --release 17 -d out src/PriceRules.java src/ContractCheck.java
java -cp out ContractCheck
~~~

On Windows PowerShell, you can use `New-Item -ItemType Directory -Force out` and then invoke the two `javac` and `java` commands as above. With correct source, **exact stdout**:

~~~text
API: OK
Behavior: OK
~~~

We have checked that the consumer can **compile** and **call** the API, while confirming the signature via reflection. In a library project, place consumer fixtures in an independent module so tests do not secretly rely on package-private members or internal library dependencies.

Note: reflection here does not replace a full ABI tool. It checks the specific member the fixture cares about; it does not automatically check the entire API surface, generic signatures, annotations, overloads, or binary compatibility of pre-built clients.

### 4.3. Inspecting the Class File with `javap`

~~~bash
javap -classpath out -public -s PriceRules
javap -classpath out -c -p PriceRules
javap -classpath out -v PriceRules
~~~

- `-public -s` displays the public API and JVM descriptors; for the example method, the descriptor is `(J)J`.
- `-c -p` disassembles instructions including non-public members, suited for **diagnosis** or optimization analysis, not as a default snapshot regression check.
- `-v` adds the constant pool, attributes, line numbers if present, class-file version, annotations, and related metadata. Constant-pool entry indices, offsets, line numbers, stack-map-frame layout, or compiler-generated member names may change when modifying source, compilers, or flags.

With `--release 17`, a normal class file is generated with **major version 61** (Java 17). That is a constraint worth checking if the application must run on Java 17. However, **“major version 61” does not guarantee complete runtime compatibility**: the class may still require a missing external dependency or cause errors at runtime. Combine compilation with testing on the target runtime.

## 5. Demonstrating a Harmless Change with Different Bytecode

Keep the file name, package, class, modifiers, method name, parameters, and return type unchanged. Replace only the body of method `afterTenPercent` with:

~~~java
// Replace only the return part in the method, after checking cents < 0.
long tens = cents / 10;
return tens * 9 + cents % 10;
~~~

This is a **replacement snippet within `PriceRules.java`**, not a standalone compilable class. When `cents >= 0`, writing `cents = 10q + r` with `0 <= r < 10` shows:

- Original variant: `cents - cents / 10 = (10q + r) - q = 9q + r`.
- Replacement variant: `(cents / 10) * 9 + cents % 10 = 9q + r`.

Both always produce the same result over the valid domain, including `Long.MAX_VALUE` since `q * 9` does not overflow `long`. Both variants keep the negative check and the same error message, so the contract test in section 4 must continue to pass.

Under `javap -c`, the bytecode **may** differ in division, multiplication, local variable store, and addition instructions; do not require hardcoded offsets or instruction ordering. Compiler-generated code shape can depend on compiler version and optimization options, while the API and behavior remain intact.

Therefore, a test of the form:

~~~text
EXPECTED: entire javap -c output of the .class file matches the old snapshot identically
~~~

is usually **too brittle** for the goal of ensuring API/behavior. Better assertions are “`ContractCheck` compiles and runs successfully”, “the method descriptor remains `(J)J`”, and attributes genuinely used by consumers stay valid.

Do not infer from a few test inputs that two implementations are equivalent for **all** inputs. In the example, we can prove it mathematically over the nonnegative domain; for more complex algorithms, add property-based tests, fuzzing, and boundary cases.

## 6. Volatile Implementation Details and Snapshot Traps

### 6.1. Constant Pool Indices and Table Ordering

Bytecode uses indices to point into the constant pool. When the compiler adds a literal or method reference, entry ordering can change; indices like `#12` or `#34` in `javap -v` are not API identity. If you want to verify that a class actually calls a particular API, compare resolved **symbolic references** (owner/name/descriptor) or use a class-file reader instead of pinning indices.

### 6.2. Instruction Offsets, Labels, and Local Variable Slots

Offsets such as `0: aload_0`, `5: invokevirtual`, or local slot numbers are consequences of how the compiler implements a method. Adding a temporary variable, changing a loop representation, or changing optimizations can alter offsets without changing the result. Do not snapshot offsets unless the problem requires verifying exact bytecode layout (for instance, verifying a bytecode transformer with special constraints).

### 6.3. Debug Attributes and Compiler Flags

`LineNumberTable`, `LocalVariableTable`, and `SourceFile` can depend on `-g` and source contents. They are useful for debuggers, stack traces, and tooling, yet are not always a public contract of a library. If a product requires reliable source maps or coverage, check the attribute serving **that need**, such as the ability to map stack traces back to source, instead of comparing the entire raw table.

`-parameters` can cause the compiler to emit `MethodParameters` so reflection can read parameter names. For frameworks that rely on parameter names, this **can indeed be an actual contract**. Do not lump all metadata into an “allowed to change” group.

### 6.4. Synthetic Methods, Bridge Methods, Lambdas, and invokedynamic

The compiler may generate bridge methods to guarantee dispatch when using generics, or use `invokedynamic` and bootstrap metadata for lambdas/string concatenation. Do not pin every synthetic method name or bootstrap entry order merely because a snapshot saw them. However, for a library needing binary compatibility, missing or wrong bridge methods or bootstrap metadata can break clients. Include compatibility tests with real consumers and, when appropriate, a symbolic ABI/class-structure comparison tool.

### 6.5. JAR Timestamps, Entry Order, and Hashes

Even when `.class` contents do not change, two `.jar` files can differ byte-for-byte due to ZIP entry order or timestamps. If the goal is solely testing API/behavior, a JAR hash is not an appropriate oracle. If the goal is **reproducible artifacts**, you must verify hashes and normalize sources of nondeterminism: compiler/toolchain, dependencies, encoding, affecting timezone/paths, entry order, and timestamps during packaging. With Gradle, you can configure reproducible archive mechanisms on the relevant packaging task and test reproducibility separately.

## 7. When Should Bytecode Structure Be Checked?

Some tools consume **the bytecode itself**, not just the program's API/behavior:

| Need | Valuable check | Check to avoid |
|---|---|---|
| Code instrumentation / AOP | After transformation, the class verifies/loads/runs properly; advice is applied at intended join points | Entire `javap -v` must keep the exact old line order |
| Security policy restricting APIs/instructions | No remaining invocations to forbidden owner/name/descriptor; no opcodes forbidden by policy | Searching for coincidental text strings in the constant pool |
| Shared library ABI | Exported types/members/descriptors/visibility, necessary generic signatures and bridge methods | Comparing raw constant pool indices |
| Java agent / bytecode enhancer | Valid frames, specific methods/fields exist, before/after behavior is correct | Requiring invariant frame counts, labels, or instruction offsets |
| Annotation-driven framework | Annotation retention/target and runtime-visible metadata read by the framework | Pinning every attribute unused by the framework |
| Reproducible binary delivery | Identical SHA-256 hash across builds with locked environments | Using hashes in place of unit/API tests |

When you must inspect bytecode structurally, you can use a class-file parser library (such as ASM with a version supporting the class files being processed), then **normalize** the representation: select important classes/methods/fields, compare symbolic owner/name/descriptor, and keep only instruction patterns genuinely belonging to policy. Do not build brittle regex parsers over `javap` text when security or compatibility decisions depend on accuracy. Some checks should combine static structure inspection with execution on the JVM.

For verifier errors, run the class via `java` on the target runtime to detect `VerifyError` along required execution paths; merely being able to disassemble a class does not mean the JVM accepts it.

## 8. Choosing Tests by Type of Change

**Changing implementation while keeping the API:** run compiler fixtures, behavioral tests, and check public descriptors/members. You can keep `javap -c` as diagnostic documentation; do not use its output as the default pass/fail condition.

**Upgrading the JDK or compiler options:** pin `--release` to the minimum supported JVM, run fixtures and tests on the target runtime. Check class-file major version if it is a contract. Accept differing bytecode when the API and runtime requirements hold; investigate any behavioral differences.

**Changing a library's API:** check source compatibility and binary compatibility against older consumers. A method may keep the same name and look similar at the source level while changing its return descriptor or static/instance semantics, causing pre-built consumers to fail. Combine an ABI diff tool with running previously compiled clients, rather than blindly trusting unit tests that recompile everything.

**Changing a code generator / annotation processor:** use real consumer fixtures to compile generated sources; verify packages, public signatures, generics/annotations, and entry points. If a generated method changes name due to implementation refactoring without consumers depending on it directly, do not pin internal names. If generated source is published as an API, it becomes a public contract to preserve.

**Changing a bytecode transformer:** verify transformations across varied method structures, stack frames, control flow, and bridge/synthetic members where relevant; load and execute the classes. Alongside semantic tests, check patterns/opcodes if those are explicit requirements of the transformer.

**Requiring bit-for-bit reproducibility:** run two clean builds with the same pinned inputs/toolchain in controlled-environment workspaces/machines and compare SHA-256 hashes. When they differ, find the source of nondeterminism across `.class` files, metadata, JAR ordering, and timestamps. This is an additional problem with its own criteria.

## 9. Common Interpretation Mistakes

**“The `.class` hash changed, so it is a compiler regression.”** Insufficient evidence. A different hash only proves the bytes differ. Look for API/behavior/JVM-compatibility differences first, or confirm a reproducibility requirement.

**“`javap -c` has a few more instructions, meaning the program is slower.”** Bytecode instruction count cannot be inferred directly as runtime cost because of JIT optimization, inlining, profiling, and escape analysis. Use a proper benchmarking methodology when evaluating performance.

**“The public method still has the same name, so it is binary compatible.”** Insufficient. JVM linkage depends on descriptors, declaring location, visibility, and static/instance semantics; generic/source compatibility and bridge methods also create subtle cases.

**“Debug metadata is not code, so it can all be removed.”** Untrue for systems relying on parameter names, runtime annotations, coverage, serialization metadata, or instrumentation. Classify metadata by consumer.

**“Source recompiles cleanly, so old clients definitely still run.”** Source compatibility of current source does not automatically guarantee binary compatibility for previously compiled classes. Old binaries must be tested against the new library.

**“The stricter the golden bytecode snapshot, the better.”** Snapshots that are strict at the wrong abstraction level cause false test failures, randomly lock down the compiler/toolchain, and block healthy refactoring. Only pin byte-level output when it is genuinely the delivery specification.

## 10. Checklist for Designing a Stable Bytecode Test Suite

- [ ] Clearly state consumers and real constraints: source, binary, behavioral, runtime, tool-specific, or reproducible binary.
- [ ] Use compiler fixtures or real clients to check public APIs instead of merely checking that `.class` files exist.
- [ ] Check classes/members/descriptors/visibility and generics/annotations when they are part of the contract.
- [ ] Test behavior, errors, exceptions, and data boundaries with executable tests; do not substitute instruction counts.
- [ ] Verify `--release`/class-file version/actual JVM when claiming support for a Java version.
- [ ] For binary compatibility, test previously compiled clients against the new library.
- [ ] For bytecode tooling, inspect symbolic structure and run appropriate load/verify/instrumentation tests.
- [ ] Do not snapshot raw constant-pool indices, local variable slots, instruction offsets, and debug line numbers without a specific technical reason.
- [ ] Separate artifact reproducibility/hash checks from ordinary correctness tests.
- [ ] Maintain one example that changes the implementation while keeping tests green, and one example that intentionally breaks the API to make tests red.

**Takeaway to remember:** bytecode is an executable format, yet **not every byte inside it is a contract**. Verify the properties that consumers/JVMs/tools depend on and test behavior with real programs; allow valid implementation details to change. Require byte-for-byte identical output only when binary reproducibility is a clearly stated goal.