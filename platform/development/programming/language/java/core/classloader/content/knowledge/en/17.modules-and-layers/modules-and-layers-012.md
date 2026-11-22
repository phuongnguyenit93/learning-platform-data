# Distinguishing --add-reads, --add-exports, and --add-opens in the Java Module System

> **Java Core → ClassLoader → Modules and layers.** The three launcher options `--add-reads`, `--add-exports`, and `--add-opens` solve three **different** conditions in the Java Platform Module System (JPMS): which module reads which module, which package exposes public types/members to another module, and which package permits deep reflective access (*deep reflection*). They do **not** change the classpath, load additional JARs, modify bytecode, or turn a class loader into a sandbox. The article includes an example with two named modules, runnable Java 17+ commands, and tested observed results.

## 1. The Problem: Seeing a Class Does Not Mean You Can Access It

A type may reside in a JAR on `--module-path`, its module may already be resolved, and `Class.forName` may find the class, yet the program still cannot use that class. Let us distinguish:

1. **Discovery/resolution:** does the module exist and has it been included in the module configuration?
2. **Readability:** does module A have a *read edge* to module B?
3. **Exports:** does B export the package containing the public type to A?
4. **Opens:** does B open the package for code in A to use deep reflection?
5. **Ordinary Java access:** does the type/method have `public`, `private`, or another access modifier? Exporting a package does **not** make a private field become public.

An access check can fail even when the class's bytes are already in the JVM:

```text
Module path -> module resolved -> class found
                                   |
                                   v
                              Read edge?
                                   |
                                   v
                    Package exported to caller?
                                   |
                                   v
                         ordinary public access

Deep reflection into private field/method:
  module/package -> opens to caller -> setAccessible(true)
```

The three options only intervene on the appropriate arrows. When encountering `IllegalAccessError` or `InaccessibleObjectException`, fix **the right kind of boundary** instead of mechanically adding all flags.

## 2. --add-reads: Adding Module Readability

In the descriptor:

```java
module m.consumer {
    requires m.provider;
}
```

`requires m.provider;` creates the ability to *read* `m.provider` from `m.consumer`. When there is no appropriate `requires`, a compiler/launcher override is:

```bash
--add-reads m.consumer=m.provider
```

Exact meaning: **m.consumer reads m.provider**. The module before the `=` sign is the **consuming side**, and the module after the `=` sign is the **providing side**.

Things to note:

- A read edge only establishes an access prerequisite; the package on the provider side still must be **exported** for ordinary static access.
- `--add-reads` does not automatically add `requires` to the `module-info.java` file; the compile-time option and the runtime option are **two separate configurations**.
- The module must be **observable/resolved** in the module configuration; `--add-reads` does not automatically locate classes in an arbitrary JAR.
- `--add-reads m.consumer=ALL-UNNAMED` lets a named module read unnamed modules. This is a compatibility escape hatch, not a replacement for `--class-path`.
- It does not open private fields, does not grant permission for deep reflection, and does not replace package export boundaries.

When you control the source code, **prefer `requires`** in the module descriptor. Use the flag for compatibility with legacy libraries, experimentation, or when a module/legacy classpath setup cannot yet be declared directly in the standard model.

## 3. --add-exports: Granting Access to a Package's Public API

A named module has:

```java
module m.provider {
    exports p.api;
}
```

Code in modules that read `m.provider` can access the **public types and accessible members** of package `p.api`. If `m.provider` also has `p.internal` but does **not export** it, ordinary source code in `m.consumer` cannot `import p.internal.Secret;` to call a public member of this type solely via a read edge.

Override at compiler/launcher:

```bash
--add-exports m.provider/p.internal=m.consumer
```

Meaning: **m.provider exports package p.internal to m.consumer**. The source/owner module is on the **left**, and the target module is on the **right**.

If you have permission to edit the module descriptor, you can replace the workaround with:

```java
module m.provider {
    exports p.api;
    exports p.internal to m.consumer;
}
```

Important points:

- Exporting opens the **public API** of the package; it does not make `private`, `protected`, or package-private members public.
- When source code **directly imports or calls** an unexported public type/member, `--add-exports` is typically needed **at both compile time and runtime** if the descriptor has not been modified.
- `--add-exports` does **not** let `setAccessible(true)` freely read private members in an unopened package.
- If the caller does not read the provider, the read edge must also be handled; exporting does not replace `--add-reads`.
- This is an exception that weakens strong encapsulation; depending on JDK-internal APIs can break when upgrading the JDK.

## 4. --add-opens: Opening a Package for Deep Reflection at Runtime

Java reflection sometimes needs to access non-public fields/methods:

```java
java.lang.reflect.Method method =
        SomeClass.class.getDeclaredMethod("hidden");
method.setAccessible(true);
Object result = method.invoke(instance);
```

This is a **snippet**; `SomeClass` and `instance` must be supplied from context. Finding the `Method` does not guarantee that the `setAccessible(true)` step will be permitted by JPMS.

If `SomeClass` is in package `p.model` of `m.provider` while the reflective code is in `m.reflect`, the appropriate flag is:

```bash
--add-opens m.provider/p.model=m.reflect
```

Or in the module descriptor of a module you own:

```java
module m.provider {
    opens p.model to m.reflect;
}
```

An *opened package* permits reflective access to public **and** non-public members of types in that package from the target module, if permitted by the API and the relevant access rules. This is important for serialization, ORM, DI, and instrumentation.

**Do not interpret `--add-opens` as an alias for `--add-exports`:**

- `opens` is useful for reflection at **runtime**.
- It **does not allow the Java compiler to import an unexported package** to write ordinary direct method calls.
- For a public member invoked **via reflection**, `opens` may also suffice even if the package is not exported. Section 8 demonstrates this case.
- `--add-opens` is not needed at compile time for a program that only intends to use private reflection later; it only takes real effect when the launcher configures runtime module access.

When a framework still relies heavily on `--add-opens java.base/...`, prefer upgrading the framework or fixing the design to avoid JDK internals.

## 5. Precise Comparison in One Table

| Criterion | `--add-reads` | `--add-exports` | `--add-opens` |
| --- | --- | --- | --- |
| Primary effect | A **reads** B | B **exports the public API** of package p to A | B **opens** package p for reflection from A |
| Syntax | `--add-reads A=B` | `--add-exports B/p=A` | `--add-opens B/p=A` |
| Direct access condition for public class | Satisfies read edge | Satisfies export edge | **Does not replace export** for direct source/bytecode access |
| `setAccessible(true)` on a private member from another module | Not sufficient | Not sufficient | Usually the required flag, if remaining access conditions are met |
| Reflection on a public member in the package | May be needed depending on context | Allows reflective public access where appropriate | Opening is also sufficient for reflective access in the example |
| Compile-time Java source | May be needed | May be needed | Does not resolve missing exports in the compiler |
| Runtime JPMS | Yes | Yes | Yes |
| Automatically adds JAR/module, switches ClassLoader | No | No | No |
| Risk when used broadly | Dependency graph becomes hard to understand | Exposes additional public internal API | Deeply opens non-public internals to reflection |

**Simple rule:** missing module dependency → read; public package not visible → export; `setAccessible` blocked → open. When two or all three kinds of conditions arise, you may need to **combine** the exact flags.

## 6. Standard Syntax and ALL-UNNAMED

Launcher syntax:

```text
--add-reads  MODULE=TARGET[,TARGET...]
--add-exports MODULE/PACKAGE=TARGET[,TARGET...]
--add-opens   MODULE/PACKAGE=TARGET[,TARGET...]
```

`TARGET` can be the name of a named module, or specifically `ALL-UNNAMED` to designate **all unnamed modules**. An unnamed module typically contains classpath code, though there can be **multiple unnamed modules** associated with different class loaders.

Examples:

```bash
--add-reads m.consumer=ALL-UNNAMED
--add-exports m.provider/p.internal=ALL-UNNAMED
--add-opens java.base/java.lang=ALL-UNNAMED
```

These are **arguments**, not standalone shell commands with an executable. Replace `ALL-UNNAMED` with the exact named caller if known:

```bash
--add-opens m.app/com.example.model=m.serializer
```

Limit the use of `ALL-UNNAMED` when only a single framework named module needs permission. It grants a broader exception that can apply to unnamed modules created later via the API.

Do not confuse `ALL-UNNAMED` with a module declared by a developer in `module-info.java`. Do not write a slash `/` between the two module names of `--add-reads`; the slash is only used in the module/package syntax of exports/opens.

## 7. Java 17+ Demo: Two Named Modules and Three Access Types

### Project Structure

```text
src/
  m.provider/
    module-info.java
    p/api/Api.java
    p/internal/Secret.java
  m.consumer/
    module-info.java
    client/Main.java
mods/          (created by javac)
```

`m.provider` exports package `p.api` while keeping package `p.internal` unexported/unopened. `m.consumer` does not declare `requires m.provider`, so we can see the effect of `--add-reads`.

**`src/m.provider/module-info.java`:**

```java
module m.provider {
    exports p.api;
}
```

**`src/m.provider/p/api/Api.java`:**

```java
package p.api;

public class Api {
    public static String greet() {
        return "api-ok";
    }
}
```

**`src/m.provider/p/internal/Secret.java`:**

```java
package p.internal;

public class Secret {
    public static String publicHello() {
        return "public-ok";
    }

    private static String privateHello() {
        return "private-ok";
    }
}
```

**`src/m.consumer/module-info.java`:**

```java
module m.consumer { }
```

**`src/m.consumer/client/Main.java`:**

```java
package client;

import p.api.Api;
import java.lang.reflect.Method;
import java.lang.reflect.InaccessibleObjectException;

public class Main {
    public static void main(String[] args) throws Exception {
        System.out.println("api=" + Api.greet());

        Class<?> type = Class.forName("p.internal.Secret");

        try {
            System.out.println("public="
                    + type.getMethod("publicHello").invoke(null));
        } catch (IllegalAccessException ex) {
            System.out.println("public=DENIED");
        }

        Method privateMethod =
                type.getDeclaredMethod("privateHello");
        try {
            privateMethod.setAccessible(true);
            System.out.println("private="
                    + privateMethod.invoke(null));
        } catch (InaccessibleObjectException ex) {
            System.out.println("private=DENIED");
        }
    }
}
```

The program distinguishes between **direct invocation** `Api.greet()`, **public reflection** `publicHello()`, and **private reflection** with `setAccessible(true)`.

### Compiling with javac --release 17

From the directory containing `src`, Linux/macOS uses:

```bash
javac --release 17 --module-source-path src -d mods \
      --add-reads m.consumer=m.provider \
      -m m.provider,m.consumer
```

Windows PowerShell uses **a single line** (without Bash's `\` line continuation):

```powershell
javac --release 17 --module-source-path src -d mods --add-reads m.consumer=m.provider -m m.provider,m.consumer
```

The command compiled successfully using OpenJDK 24 with `--release 17` mode. The compiler needs the read edge because `client.Main` imports `p.api.Api`, yet `m.consumer` has not declared `requires m.provider`. Package `p.api` is already exported; `p.internal` is only looked up by string name via reflection and not directly imported, so **compiler `--add-exports` is not needed** for this case.

### Run 1 — Adding Only the Read Edge

```bash
java --module-path mods --add-modules m.provider \
     --add-reads m.consumer=m.provider \
     -m m.consumer/client.Main
```

**Exact** output:

```text
api=api-ok
public=DENIED
private=DENIED
```

The public API call from package `p.api` succeeds because m.consumer **reads m.provider** and `p.api` is exported. However, `p.internal` is not exported/opened: the reflective call of the public method hits `IllegalAccessException`; private `setAccessible(true)` hits `InaccessibleObjectException`. The code catches both exceptions and prints `DENIED`.

### Run 2 — Adding --add-exports for the Internal Package

```bash
java --module-path mods --add-modules m.provider \
     --add-reads m.consumer=m.provider \
     --add-exports m.provider/p.internal=m.consumer \
     -m m.consumer/client.Main
```

**Exact** output:

```text
api=api-ok
public=public-ok
private=DENIED
```

Additionally exporting `p.internal` to the consumer allows **public reflection** to succeed. However, the package is not opened yet, so `setAccessible(true)` with the private member continues to fail.

### Run 3 — Opening the Package for Deep Reflection

```bash
java --module-path mods --add-modules m.provider \
     --add-reads m.consumer=m.provider \
     --add-exports m.provider/p.internal=m.consumer \
     --add-opens m.provider/p.internal=m.consumer \
     -m m.consumer/client.Main
```

**Exact** output:

```text
api=api-ok
public=public-ok
private=private-ok
```

Private reflective invocation now succeeds because the package has been opened to the exact named caller. You should **not** infer that the private method becomes callable from ordinary Java source code; the access approach here is reflection.

### Run 4 — Only --add-opens for the Internal Package

```bash
java --module-path mods --add-modules m.provider \
     --add-reads m.consumer=m.provider \
     --add-opens m.provider/p.internal=m.consumer \
     -m m.consumer/client.Main
```

**Exact** output:

```text
api=api-ok
public=public-ok
private=private-ok
```

**Subtle point:** Opening is sufficient for reflective access to **both public and non-public members** in package `p.internal` from that caller, even though the package is not exported. However, `--add-opens` does not allow the compiler to `import p.internal.Secret;` to perform ordinary direct invocation if the package is not exported.

### Run 5 — Omitting the Read Edge at Runtime (Intentional Error)

```bash
java --module-path mods --add-modules m.provider \
     -m m.consumer/client.Main
```

Because `m.consumer` does not have `requires m.provider` and the runtime does not have `--add-reads`, when `client.Main` calls `Api.greet()`, the JVM throws **`IllegalAccessError`** with the core message:

```text
class client.Main (in module m.consumer) cannot access class p.api.Api
(in module m.provider) because module m.consumer does not read module m.provider
```

This is a **paraphrase of the stderr message**, not exact stdout or a full stack trace (file paths and line numbers may vary). Compile flags **do not persist automatically** in a new JVM run. The `--add-modules m.provider` option is still used to ensure the provider module is resolved; having a module in the configuration **does not mean** every consumer automatically reads it.

### Conclusions from the Demo

| Runtime flags | Direct `Api.greet()` | Reflective public `Secret.publicHello()` | Private `setAccessible` |
| --- | --- | --- | --- |
| No read edge | `IllegalAccessError` | Does not reach this step | Does not reach this step |
| `--add-reads` | Success | Denied | Denied |
| `--add-reads` + `--add-exports` | Success | Success | Denied |
| `--add-reads` + `--add-exports` + `--add-opens` | Success | Success | Success |
| `--add-reads` + `--add-opens` | Success | Success via reflection | Success via reflection |

The four successful run configurations above have been verified with OpenJDK 24, using Java 17-compatible code.

## 8. Static Access Differs from Reflection: Do Not Pick Flags Mechanically by Exception Name

There are three distinct operations:

```java
// Static use of the public API (must compile against the module graph):
String s = p.api.Api.greet();

// Reflection to look up the method (only obtains a Method object):
Method m = Class.forName("p.internal.Secret")
        .getDeclaredMethod("privateHello");

// Reflection requesting to bypass access checks at runtime:
m.setAccessible(true);
```

This is a **snippet** (requiring an import declaration for `Method` and appropriate context), not a standalone Java file.

- For **static use**, the compiler/linker needs a read edge and package export.
- For **metadata lookup**, a class/method can be found even if the package is not exported/opened, according to loader/module semantics and lookup operations.
- For **public reflection**, a package that is exported or opened to the caller can suffice depending on the operation.
- For **deep reflection**, `setAccessible(true)` also depends on the package being open, the caller module, and other reflective access rules; exporting the public API does not automatically open private data.

`Class.forName` succeeding does **not** prove the consumer has permission to access all members. `getDeclaredMethod` finding a private method does **not** mean `Method.invoke` is allowed to call it.

## 9. Compile Time and Runtime May Require Different Configurations

`javac` and `java` are **two separate steps**. If the source of `m.consumer` directly imports a public type in an **unexported** package, the compiler may need:

```text
javac options:
    --add-reads m.consumer=m.provider
    --add-exports m.provider/p.internal=m.consumer

java runtime options (if that direct linkage is still used):
    --add-reads m.consumer=m.provider
    --add-exports m.provider/p.internal=m.consumer
```

These are illustrative option lists; to compile/run, you must add the corresponding module source path, output, module path, and entry point. `--add-opens` is only useful when the program actually uses reflection at runtime; it cannot be used to replace an export for the Java source compiler.

Example direct-import source (illustrative code that **does not run standalone** unless placed in a module and provided with imports/flags):

```java
import p.internal.Secret;
String value = Secret.publicHello();
```

With `p.internal` unexported, a program of this form is not permitted merely because runtime `--add-opens` is set.

**Deployment reality:** IDE, Gradle/Maven compiler settings, test runner JVM args, and the production launcher must distinguish their configurations separately. A common pitfall is unit tests passing because the IDE adds flags while production `java -m` does not have them.

## 10. A More Sustainable Solution: module-info.java

When you control the source module and the consumer module, you should explicitly declare requirements using descriptors.

Read edge:

```java
module m.consumer {
    requires m.provider;
}
```

Qualified export:

```java
module m.provider {
    exports p.api;
    exports p.internal to m.consumer;
}
```

Qualified open:

```java
module m.provider {
    exports p.api;
    opens p.model to m.framework;
}
```

These are **three different `module-info.java` variants**; do not place all three `module m.provider` declarations into one file simultaneously. With `opens p.model`, module `m.framework` can use reflective access according to the applicable rules; this does **not** turn package `p.model` into a public API for any module to import directly.

Using launcher flags is a deployment override; using the module descriptor is a clearer **part of the module contract** when you have permission to edit the source.

## 11. Connection to Module Resolution, ModuleLayer, and ClassLoader

In JPMS, distinguish between:

- **Module path**: where the module finder locates module artifacts.
- **Observable module**: a module known to the system that can be resolved.
- **Resolved module**: included in the running configuration/layer.
- **Readable module**: has a read edge from the caller module.
- **Exported package**: permitted for external use of its public API according to the rules.
- **Opened package**: permitted for deep reflection from the target module.
- **Defining loader**: the loader the JVM uses to define a `Class<?>`. The class identity of an ordinary class/interface is `(binary name, defining loader)`.

Visualization:

```text
--module-path / module finder
           |
           v
module resolution -> module configuration
           |
           v
boot ModuleLayer / custom ModuleLayer
           |
           +-- requires and added read edges
           +-- exports qualified/unqualified
           '-- opens qualified/unqualified
           |
           v
class loader(s) assigned to locate/define classes
```

In the demo, because the consumer does not `requires` the provider, the launcher includes `--add-modules m.provider` to select it into the configuration. `--add-reads` then supplements the edge; it does **not** solve the same problem.

When an application creates another `ModuleLayer` via `ModuleLayer.defineModulesWithOneLoader`/`defineModulesWithManyLoaders`, the configuration, module descriptors, and loader mapping may differ from the boot layer. Do not assume launcher flags apply to every package in **all subsequently created layers**. The `Module.addReads`, `Module.addExports`, and `Module.addOpens` APIs exist, but they are subject to caller/authority rules; frameworks that create layers must manage graph changes in context rather than arbitrarily opening all modules.

Even after module code has been found by a loader, the JVM can still throw a JPMS access error. Conversely, adding an export/open/read does not turn a nonexistent class into a loadable class.

## 12. Diagnosing Common Errors

| Symptom | Cause distinction | Resolution |
| --- | --- | --- |
| `module A does not read module B` | Missing read edge. | Add `requires B;` or `--add-reads A=B` and ensure B is resolved. |
| `package p.internal is not visible` at the compiler | Source directly uses a type from an unexported package. | Qualified `exports` or `javac --add-exports B/p.internal=A`; add reads if missing. |
| `IllegalAccessError` at runtime | Compile time granted access, but runtime lacks read/export. | Repeat the necessary options on the launcher. |
| `IllegalAccessException` when reflection calls a public member | Package is not exported/opened to the caller. | Export the public API, or open if broader reflective access is needed. |
| `InaccessibleObjectException` at `setAccessible(true)` | Caller lacks deep reflection permission for the package. | `opens`/`--add-opens B/p=A` in the right direction. |
| `ClassNotFoundException` | Module not resolved, loader cannot find class, or wrong binary name. | Check module path/`--add-modules`/loader; add-opens does not create classes. |
| `NoClassDefFoundError` | Missing dependency or context-specific linking/initialization failure. | Analyze the cause/stack, module graph, and actual classpath. |
| `LayerInstantiationException` | Module/package conflict, resolver/layer constraints. | Fix the configuration; do not treat all three flags as a universal fix. |
| “Unknown module … specified to …” | Wrong module name or module not observable/resolved at the stage the option is applied. | `java --list-modules`, `jar --describe-module`, module path. |
| Reflection finds the Method but invoke fails | Metadata lookup and access check are separate. | Check `getMethod`/`getDeclaredMethod`, `invoke`, `setAccessible`, and the caller module. |

Inspection tools:

```bash
java --list-modules
jar --describe-module --file provider.jar
java --show-module-resolution --module-path mods --add-modules m.provider -m m.consumer/client.Main
```

The `jar` command requires an actual JAR file (for example, `provider.jar` is only an illustrative name); `java --show-module-resolution` helps view resolution but does not replace the stack trace of an access error. If the error comes from reflection in a test runner, identify the **module of the reflective caller code** rather than assuming it is the test target's module.

## 13. What the Three Flags Do Not Do

These options do **not**:

1. Add new JARs to the classpath or module path.
2. Force the JVM to load/initialize all classes in a package.
3. Change parent delegation or class-loader identity.
4. Redefine a class already loaded by the same defining loader.
5. Allow ordinary Java source code to directly access private members.
6. Resolve all `ClassNotFoundException`/`NoClassDefFoundError` errors.
7. Replace signature checks, dependency versions, or OS access permissions.
8. Create a security sandbox for untrusted plugins.

`--add-exports` and `--add-opens` **reduce encapsulation**. Using them for legacy/JDK-internal packages risks breakage when upgrading Java. If all three flags are needed across dozens of modules just to run a framework, check for framework updates and review the module design before continuing to expand exceptions.

`ALL-UNNAMED` grants broader access to classpath code than a specific named module. Scope permissions narrowly to the exact package and exact consumer to reduce accidental exposure.

## 14. Workflow for Choosing Flags by Problem

**Case A — Direct public API call, but consumer does not read provider**

```text
Error: module A does not read module B
Fix:   requires B; or --add-reads A=B
Check: Is B resolved? Is the package exported?
```

**Case B — Direct code uses a public type in an unexported package**

```text
Error: package B/p is not exported to A
Fix:   exports p to A; or --add-exports B/p=A
       (while ensuring A reads B)
Check: both javac and java have the same required permissions
```

**Case C — Reflection on a private field/method fails**

```text
Error: InaccessibleObjectException at setAccessible
Fix:   opens p to A; or --add-opens B/p=A
Check: Is A a named module or ALL-UNNAMED?
```

**Case D — Public reflection on an internal package**

```text
Can use: exports B/p=A or opens B/p=A as appropriate
If only public access is required: prefer exporting the API instead of deep opening
If private access is required: open the exact package to the exact caller
```

**Case E — Class still cannot be found**

```text
Check: module path / jar layout / module resolution / defining loader
Do not: blindly switch from --add-reads to --add-opens
```

## 15. Self-Check Questions and Answers

1. **Does `--add-reads A=B` allow A to access every public class in B's unexported packages?** No. Exports must also be considered.
2. **Does `--add-exports B/p=A` allow A to call a private method directly?** No. Java access modifiers are not altered.
3. **When does `--add-opens B/p=A` help `setAccessible(true)`?** When caller A needs deep reflection into B's p and the other conditions are satisfied.
4. **Does opens help the compiler import an unexported `B/p.Secret`?** No. Static source access requires an export.
5. **Why did the test with `--add-opens` and without `--add-exports` still print `public=public-ok`?** Opening also grants reflective access to public members, and the test invokes it via reflection.
6. **Is `ALL-UNNAMED` a real named module on the module path?** No. It is a special target for all unnamed modules.
7. **If the compiler is given `--add-reads`, does the runtime automatically inherit that permission?** No. You must use the launcher flag if the descriptor does not yet have `requires`.
8. **Does `--add-reads` automatically resolve every provider module?** No. You may need `--add-modules` or an appropriate requires graph.
9. **Can two modules in the same class loader bypass package exports?** No; module access is still enforced.
10. **Does `Class.forName` succeeding mean `setAccessible(true)` is guaranteed to succeed?** No; reflective access is a separate step.
11. **When you own the module source, should you prefer flags or the descriptor?** Prefer `module-info.java` with explicit `requires`, qualified `exports`, and `opens`.
12. **Do the three flags prevent a malicious plugin from accessing the filesystem?** No; JPMS is not a process/OS sandbox.

## 16. References

- [Oracle Java SE 21 — java launcher](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): `--add-reads`, `--add-exports`, `--add-opens`, `--add-modules`, and the module path.
- [Oracle Java SE 21 — javac](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): read/export overrides at compile time.
- [Oracle Java SE 21 Migration Guide — Strong Encapsulation](https://docs.oracle.com/en/java/javase/21/migrate/migrating-jdk-8-later-jdk-releases.html): choosing exports/opens when upgrading the JDK.
- [dev.java — Strong Encapsulation](https://dev.java/learn/modules/strong-encapsulation/): static vs reflective access.
- [dev.java — Add Exports and Opens](https://dev.java/learn/organizing/modules/add-exports-opens/): qualified exceptions and recommendations to limit overuse.
- [Java SE 21 — java.lang.Module](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html): `canRead`, `isExported`, `isOpen`, dynamic module access.
- [Java SE 21 — ModuleLayer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html): module configuration/layer and loaders.
- [JLS `7.7 — Module Declarations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.7): `requires`, `exports`, `opens`.
- [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): rationale for strong encapsulation in JDK 17+.
