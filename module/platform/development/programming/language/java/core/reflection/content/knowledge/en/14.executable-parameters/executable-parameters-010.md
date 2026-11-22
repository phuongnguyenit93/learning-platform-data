# Do Not Use Reflection Parameter Names as a Stable Contract When Builds Do Not Guarantee Metadata

## 1. Problem: Names in Java Source May Not Exist at Runtime

Suppose a method is written in source code:

```java
public void send(String recipient, int retryCount) {
    // Data sending logic.
}
```

The two names `recipient` and `retryCount` help code authors understand the meaning of arguments. However, after compilation to `.class`, **Java Reflection does not always retrieve these two names**. That depends on whether the class file actually contains formal parameter name metadata.

If a framework automatically derives JSON keys, query parameters, CLI option names, or configuration field names from `Parameter.getName()`, the program may suddenly emit keys like `arg0`, `arg1` when using an artifact compiled with different options.

**Core principle:** *Do not use Java parameter names read via Reflection as a stable API contract if the build pipeline does not guarantee metadata; even when metadata is present, the mere presence of names does not automatically turn source names into a versioned contract.*

This lesson falls under **executable parameters**: `Method` and `Constructor` objects both inherit from `java.lang.reflect.Executable`; they provide `getParameters()`, returning `java.lang.reflect.Parameter` objects to read the name, type, and attributes of each formal parameter.

## 2. Separating Name Metadata from External Contracts

`Parameter.getName()` always returns a string, including synthesized names `arg0`, `arg1` when names are missing in `MethodParameters`. `Parameter.isNamePresent()` is what determines whether the class file supplies a name for **this parameter**.

`getType()` and `getParameterizedType()` read type descriptions from other metadata; JVM lookup signatures do not rely on formal parameter names. Even when `isNamePresent()` is `true`, renaming `recipient` to `target` can preserve the Java/JVM signature while changing the name inferred by a framework for requests.

Hence there are two independent checks: **is name metadata present in the artifact?** and **are those names published, governed, and tested as an external contract?**

## 3. Why Can Two Builds Have Different Contracts?

With `javac`, the `-parameters` compiler option writes formal parameter names into `MethodParameters`; the `-g` option serves debug information and does not replace this flag for Core Reflection. CI, dependency JARs, obfuscators, and bytecode transformers can produce artifacts retaining different metadata from an IDE run.

Inspect `javap -v -p` on **the actual published class file or JAR**, then verify `isNamePresent()` in tests. Metadata for generic types and runtime annotations uses separate mechanisms; do not take their presence as proof that parameter names were also preserved.

## 4. Java 17 Experiment: Source Names Change, External Names Stay Stable

A different approach from merely printing `argN`: let's test an annotation that defines contract names independently of Java variable names. Create the file `StableContractDemo.java`:

```java
import java.lang.annotation.*;
import java.lang.reflect.*;

public class StableContractDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.PARAMETER)
    @interface ExternalName {
        String value();
    }

    static class Endpoint {
        public void send(@ExternalName("recipient") String target,
                         @ExternalName("retryCount") int attempts) {}
    }

    public static void main(String[] args) throws Exception {
        Method method = Endpoint.class.getDeclaredMethod(
                "send", String.class, int.class);
        for (Parameter parameter : method.getParameters()) {
            ExternalName contract = parameter.getAnnotation(ExternalName.class);
            System.out.println("name=" + parameter.getName()
                    + ", present=" + parameter.isNamePresent()
                    + ", external=" + contract.value());
        }
    }
}
```

Compile and run two separate builds:

```bash
javac --release 17 -d plain StableContractDemo.java
javac --release 17 -parameters -d named StableContractDemo.java
java -cp plain StableContractDemo
java -cp named StableContractDemo
```

The `plain` build prints:

```text
name=arg0, present=false, external=recipient
name=arg1, present=false, external=retryCount
```

The `named` build prints:

```text
name=target, present=true, external=recipient
name=attempts, present=true, external=retryCount
```

The two builds differ in reflected names, yet `external` stays unchanged because the annotation has `@Retention(RUNTIME)` and carries the published name directly. The names `target`/`attempts` can be refactored while the `recipient`/`retryCount` contract remains intact as long as the annotation is unchanged. This illustrates design intent: custom annotations **do not perform binding themselves**; frameworks must explicitly read and use the declared names.

## 5. Why Is This a Risk to API Contracts?

A **stable contract** is what external callers are entitled to expect across releases, such as the query parameter name `recipient`, JSON key `retryCount`, command-line option name, configuration field, or field bound by a framework from a request.

Variable names in Java source do not automatically form such a contract:

- **Different build environments:** developer machines, CI, sub-modules, or consumer projects may configure `javac` differently. One class build has `MethodParameters`, while another does not.
- **External dependencies:** you do not control compile options of third-party libraries; `isNamePresent()` may return `false`.
- **Post-compile tools:** obfuscators, bytecode transformers, minifiers, or packaging steps can alter, strip, or regenerate metadata.
- **Java-valid refactoring:** renaming a formal parameter from `recipient` to `destination` usually **does not change the JVM method descriptor**; Java calls based on position and types remain valid, yet a framework deriving API keys from `getName()` may silently change external keys.
- **Synthesized names look valid:** `arg0`, `arg1` are non-empty strings, making it easy for a framework to mistakenly use them as real keys if `isNamePresent()` is not checked.
- **Positional info differs from semantic meaning:** parameter index is part of the execution signature, but does not by itself state what business role the parameter plays. Changing parameter order/count also alters the contract your adapter must manage.

Example of a framework automatically populating map keys:

```java
for (Parameter parameter : method.getParameters()) {
    String externalKey = parameter.getName();
    // Risk: externalKey may be arg0/arg1.
}
```

This is an illustrative code snippet, assuming `Method method` exists and `Parameter` is imported. In builds lacking metadata, an API intended to expose `recipient` and `retryCount` can suddenly expose `arg0` and `arg1` — breaking the external contract without any Java logic change.

**Even when `isNamePresent() == true`, those names can still change between two class builds**. Treat them as an external interface only when the project **explicitly publishes** name stability, builds are controlled, and compatibility tests are in place. Metadata is only a necessary condition for observing names, not automatic proof of business invariance.

## 6. Safer Design Strategies

### A. Explicitly Declare External Interface Names

For endpoints, message consumers, CLIs, serializers, or dependency injection, define external keys via configuration/schema or annotations **with explicit values**, rather than implicitly deriving them from Java variable names.

Hypothetical example of a framework providing an annotation to hold external names:

```java
void send(
        @RequestKey("recipient") String target,
        @RequestKey("retryCount") int attempts
) {
    // The two external names do not depend on target/attempts in source.
}
```

This is **illustrative code, not standalone**; `@RequestKey` is an example annotation and must be defined or replaced with the actual annotation of the framework in use. The key point is that external names `recipient` and `retryCount` are declared **directly**, no longer inferred from `target` or `attempts`.

If building your own framework, the annotation must have appropriate retention to be readable at runtime, such as `@Retention(RetentionPolicy.RUNTIME)` on the parameter annotation. An annotation without runtime retention will not become valid runtime metadata merely because `-parameters` is present.

Equivalent alternatives:

- JSON/OpenAPI/protobuf schemas or contract files defining keys at the interface layer.
- An explicit mapping between **formal parameter position/type** and external names that is maintained/tested.
- A runtime annotation with a fixed external name, versioning, and validation.
- Interfaces/DTOs with public properties governed by a versioned contract instead of relying on local variable names.

### B. If the Application Truly Wants to Infer Names, Check and Fail Explicitly

Some libraries intentionally treat Java parameter names as a convenience — such as internal frameworks binding arguments by name. In that case, treat metadata presence as a **mandatory precondition** and verify it at startup instead of silently accepting synthesized names:

```java
static String[] requireParameterNames(Executable executable) {
    Parameter[] parameters = executable.getParameters();
    String[] names = new String[parameters.length];

    for (int i = 0; i < parameters.length; i++) {
        if (!parameters[i].isNamePresent()) {
            throw new IllegalStateException(
                    "Missing parameter name metadata for "
                    + executable + " parameter #" + i
                    + ". Compile with -parameters."
            );
        }
        names[i] = parameters[i].getName();
    }
    return names;
}
```

The snippet above is an **illustrative method**, assuming `Executable` and `Parameter` are imported; place it inside an appropriate Java class to use. It only solves **missing metadata**, and **does not guarantee** that present names remain stable across source/build changes. Add tests and versioning conventions if names become API.

Checking for name presence must be done **per `Parameter`**, not by inspecting one element and assuming all have valid data. For special executables or class files from different tools, take extra care regarding the origin of each parameter.

### C. When You Only Need to Invoke a Method, Do Not Ask for Parameter Names

If the goal is finding and invoking a method with Reflection, use:

```java
Method method = type.getDeclaredMethod(
        "send", String.class, int.class
);
method.invoke(receiver, "alice", 3);
```

This is illustrative code, assuming compatible `type`, `receiver`, and `Method` imported; callers must handle Reflection exceptions. **Lookup and invocation rely on parameter order and types**, regardless of whether `recipient`/`retryCount` names are stored.

For tools needing generic types, there are `getGenericParameterTypes()` and `Parameter.getParameterizedType()`; for parameter annotations there are `getParameterAnnotations()` or `Parameter.getAnnotation()`. Those metadata kinds have their own contracts and should not be conflated with names.

## 7. Build Rules and Contract Testing

If a system actively uses formal parameter names as an API, enable `-parameters` on **every module defining executables whose names must be read**, verify artifacts after optimization/packaging, and test the exposed names. Enabling the flag in the calling application does not add metadata to precompiled dependency JARs.

A good test needs two kinds of assertions: `isNamePresent()` for parameters the framework relies on, and **the expected external names** of endpoints/schemas across versions. Checking metadata presence alone will not catch contract changes from source name refactoring. If external names live in annotations/schemas, tests must assert those annotation/schema values and actual binding behavior.

## 8. Be Careful with Special Executables

Constructors of non-static inner classes or enums, as well as compiler-generated executables, may contain implicit/synthetic parameters beyond the source code. When building a general binder, inspect `getParameters()`, `getParameterTypes()`, `isImplicit()`, and `isSynthetic()` on the artifact instead of assuming index 0 is always a business parameter. These flags help describe parameter origin; they **do not guarantee** stable published names.

## 9. Common Design Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `getName()` directly as an HTTP/JSON key | Missing metadata can expose `argN` | Use naming annotations/schemas or fail fast when names are missing |
| Treating `isNamePresent=true` as a stability guarantee | Source renames still break the contract | Test public API names and manage version changes |
| Enabling `-parameters` only in the consumer module | Prebuilt dependencies do not gain metadata | Configure the compiler in modules declaring the executables |
| Silently falling back to `argN` | Hard-to-detect binding bugs | Report configuration errors with method and parameter index |
| Reading name annotations yet binder ignores them | API still binds by Java names | Write/test mapping code based on annotation values |

## 10. Self-Check Questions

1. A source parameter is named `recipient`, but the class file lacks `MethodParameters`. Is `getName()` guaranteed to return `recipient`? **No.** It may be `arg0`; `isNamePresent()` is `false`.
2. If `getName()` returns `arg0`, should you conclude metadata is definitely missing solely from the string? **No.** Use `isNamePresent()`, rather than checking name patterns.
3. Which option do you enable in `javac` to store formal parameter names? **`-parameters`**.
4. Does `javac -g` guarantee `Parameter.isNamePresent() == true`? **No.** Debug information and `MethodParameters` are separate concepts.
5. Why is a framework generating API keys from `getName()` risky? **Missing/altered metadata, obfuscation, or refactoring** can change the keys.
6. If `isNamePresent()` is `true`, have the names become a stable public API? **Not yet.** Names and compatibility must be governed at the design/version level.
7. Does `Executable.getParameters()` work for both methods and constructors? **Yes.** Both `Method` and `Constructor` inherit from `Executable`.
8. Does `getDeclaredMethod("send", String.class, int.class)` require storing the names `recipient` and `retryCount`? **No.** Lookup uses the method name and formal parameter types.

## 11. Official Documentation

- [Oracle Java SE 21 — `java.lang.reflect.Parameter`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Parameter.html): contract of `getName()`, `isNamePresent()`, `isImplicit()`, `isSynthetic()`.
- [Oracle Java SE 21 — `java.lang.reflect.Executable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Executable.html): querying `getParameters()`, parameter count, types, and annotations of methods/constructors.
- [Oracle Java SE 21 — `javac` tool](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): meaning of `-parameters` and debug options.
- [The Java Virtual Machine Specification SE 21 — §4.7.24 `MethodParameters`](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.7.24): class file structure for formal parameter metadata.
- [Dev.java — Invoking Methods](https://dev.java/learn/reflection/methods/): official examples and notes on Reflection, formal parameter names, and compiler options.

**Remember:** `getName()` may return `arg0`/`arg1` if metadata is missing; `isNamePresent()` confirms **names exist in the class file**, not that **those names are a stable contract**. To publish names externally, use explicit schemas/annotations or enforce `-parameters` builds together with tests and compatibility policies.
