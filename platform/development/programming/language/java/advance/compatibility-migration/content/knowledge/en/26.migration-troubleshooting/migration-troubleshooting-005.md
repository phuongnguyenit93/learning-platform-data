# IllegalAccessError, IllegalAccessException, and InaccessibleObjectException

When upgrading the JDK, upgrading a framework version, or migrating an application to the Java Platform Module System (JPMS), one of the most confusing error groups is **access errors**. Three very similar names can appear in logs:

- `java.lang.IllegalAccessError`
- `java.lang.IllegalAccessException`
- `java.lang.reflect.InaccessibleObjectException`

All three relate to code attempting to access a class, field, method, or constructor that Java disallows in the current context. However, **they occur at different layers**, have different mechanisms of origin, and require different fixes. Adding `--add-opens` to a linkage error, or adding `--add-exports` to a deep reflection error, usually does not solve the problem.

This lesson belongs to the **Troubleshooting** chapter of the **Java Advance Compatibility Migration** module. The focus is on accurately identifying the exception/error, understanding Java access control rules and JPMS, creating reproducible examples, finding the root cause across compile/runtime/module paths, and fixing the issue sustainably instead of accumulating JVM flags.

## 1. Learning outcomes

After this lesson, you can:

1. Distinguish `Error`, checked `Exception`, and unchecked `RuntimeException` across the three access cases.
2. Explain the difference between **ordinary bytecode access**, **ordinary access-checked reflection**, and **deep reflection**.
3. Identify `IllegalAccessError` situations caused by binary incompatibility or unexported packages in JPMS.
4. Analyze `IllegalAccessException` when calling `Method.invoke`, `Field.get/set`, or `Constructor.newInstance`.
5. Analyze `InaccessibleObjectException` when `setAccessible(true)` is rejected by JPMS.
6. Choose the right `requires`, `exports`, `opens`, `--add-exports`, or `--add-opens`.
7. Reproduce the error using a self-managed module example, avoiding reliance on internal JDK APIs that may change.
8. Inspect the classpath, module path, actual loaded JARs, test JVMs, and production environment.
9. Build a diagnostic checklist and post-migration verification workflow.

## 2. Quick identification of the three errors

| Indicator | `IllegalAccessError` | `IllegalAccessException` | `InaccessibleObjectException` |
| --- | --- | --- | --- |
| Category | `Error` → `LinkageError` | Checked `Exception` → `ReflectiveOperationException` | Unchecked `RuntimeException` |
| Typical occurrence | JVM links or executes an invalid bytecode access | Reflection tries to access a member, but access checks disallow it | Reflection tries to **bypass** access checks via `setAccessible(true)`, which is disallowed |
| API/execution path | Ordinary method calls, field/class references; module access | `Method.invoke`, `Field.get`, `Field.set`, `Constructor.newInstance` | `AccessibleObject.setAccessible` or equivalent operation |
| Example cause | Method that was `public` in v1 becomes non-public in v2; module does not export package | Calling a `private` method via reflection without enabling access override | Target module does not open the package to the calling module |
| Catchable? | Technically yes, but should not be treated as a business exception | Must be caught or declared in `throws` | Can be caught like a runtime exception |
| Usually right fix | Restore binary/API compatibility, align JARs, fix `exports` or required runtime flags | Use public API or valid reflective access; if permitted, use `setAccessible` | Use public API, upgrade framework, add scoped `opens` or `--add-opens` |
| Present since | Early Java | Early Java | Java 9, with the introduction of JPMS |

**First rule:** read the **exact exception name and stack trace**. Do not lump everything together as "Java 17 disallows reflection". `IllegalAccessError` can occur completely unrelated to reflection; `IllegalAccessException` can occur on Java 8; `InaccessibleObjectException` relates directly to suppressing Java language access checks at runtime, typically seen in module encapsulation contexts.

## 3. Access layers in Java

### 3.1. Java language access rules

Java applies access levels:

- `public`: member/type is accessible within the valid scope under language and module system rules.
- `protected`: adds package and subclass conditions, with specific rules for the receiver and member.
- *package-private*: no modifier declared, within the package according to Java rules.
- `private`: access scope is restricted to the corresponding enclosing declaration structure.

Example:

```java
package com.example.model;

public final class Account {
    public String id() {
        return "A-100";
    }

    private String token() {
        return "secret";
    }
}
```

Code outside the class can call `id()` if the type is visible, but cannot directly call `token()`. Making the class `public` **does not automatically make every member inside it public**.

### 3.2. JPMS adds boundaries at the module and package levels

Since Java 9, named modules can declare descriptors:

```java
module com.example.library {
    exports com.example.library.api;
}
```

If another module wants to reference a `public` type in package `com.example.library.api` via ordinary access, consider:

1. **Readability:** can the calling module read the module containing the type? Usually expressed via `requires`.
2. **Exports:** is the package containing the type exported to the calling module?
3. **Java access control:** does the type/member have visibility permitting the specific call?

Mental diagram:

```text
Can caller module read target module?
         |
         +-- No --> readability / module graph
         |
         +-- Yes
              |
              v
Is package exported to caller?
         |
         +-- No --> JPMS package access
         |
         +-- Yes
              |
              v
Does class/member have suitable access level?
         |
         +-- No --> Java access checks
         |
         +-- Yes ---> valid ordinary access
```

**`requires` does not mean every package is visible. `exports` does not mean every `private` field/method becomes public.**

### 3.3. Ordinary reflection and deep reflection differ

Reflection allows looking up classes and members at runtime:

```java
Class<?> type = Class.forName("com.example.model.Account");
Method method = type.getDeclaredMethod("token");
```

`getDeclaredMethod` can find a non-public method. However, **discovering metadata** differs from **being permitted to invoke the method**.

When calling:

```java
method.invoke(account);
```

reflection checks access rights. If disallowed, `IllegalAccessException` typically occurs.

If code proceeds with:

```java
method.setAccessible(true);
method.invoke(account);
```

it is requesting to **suppress Java language access checks**. Since Java 9, this request is governed by JPMS rules. If the target module does not open the package to the module performing reflection, `setAccessible(true)` can throw `InaccessibleObjectException`.

### 3.4. Nature of `exports` and `opens`

| Declaration/flag | Purpose |
| --- | --- |
| `requires m` | Allows the calling module to read module m under JPMS rules. |
| `exports p` | Allows modules with appropriate readability to access public types/members of package p via ordinary access. |
| `exports p to x` | Exports package p restricted to module x. |
| `opens p` | Opens package p for deep reflection from other modules. |
| `opens p to x` | Opens package p only for deep reflection from module x. |
| `--add-exports m/p=x` | Adds an export for a compile/run invocation via tooling options. |
| `--add-opens m/p=x` | Adds package open permission at runtime for deep reflection. |
| `--add-reads m=x` | Adds a readability relationship when necessary. |

`exports` primarily handles **ordinary access**. `opens` handles **deep reflection**. They are not synonyms.

## 4. `IllegalAccessError`: JVM rejects a bytecode reference

### 4.1. Belongs to the `LinkageError` family

`IllegalAccessError` sits under `IncompatibleClassChangeError` and `LinkageError`. It indicates that code was compiled, yet at runtime the JVM cannot execute an access reference because **access rules at linking/execution time are no longer satisfied**.

An example message looks like:

```text
java.lang.IllegalAccessError:
  class com.example.client.Main cannot access class
  com.example.internal.HiddenApi
  (in module com.example.core)
  because module com.example.core does not export
  com.example.internal to module com.example.client
```

This is an example of a named module package access error at runtime.

### 4.2. Another scenario: old API was public, new API restricts access

Suppose library v1 provides:

```java
package com.example.api;

public class AccountService {
    public void synchronize() {
        // Implementation v1
    }
}
```

Consumer compiled against v1:

```java
new AccountService().synchronize();
```

In library v2, the author changes:

```java
package com.example.api;

public class AccountService {
    void synchronize() {
        // Method was changed to package-private.
    }
}
```

If **recompiling the consumer** against v2, `javac` usually reports an error immediately because the method is not visible.

If the consumer is not recompiled and only the library JAR is swapped at runtime, the consumer bytecode still holds the reference compiled when the method was public. When the JVM executes the call with library v2, it can throw `IllegalAccessError`.

**Key point:** `IllegalAccessError` is often a symptom of **binary incompatibility** or a mismatch between compile and runtime environments, not merely "missing reflection permission".

### 4.3. Common causes

- A class/method/field that was once `public` or `protected` now has narrower access.
- The compile JAR differs from the JAR loaded at runtime, often due to a dependency conflict.
- A class resides in a package that is no longer exported after modularization.
- Compilation was allowed via `--add-exports`, while runtime lacks the corresponding export permission.
- The module descriptor changed between the library version the client compiled against and the version currently running.
- A class loader/application server introduces a different dependency version than expected.

### 4.4. Why should you not catch and ignore it?

At the language level, an `Error` can be caught. However, `IllegalAccessError` signals that a program linkage or access boundary has been violated. Catching and ignoring it does not fix the classpath, binary signature, or module graph.

Example to avoid:

```java
try {
    service.synchronize();
} catch (IllegalAccessError ignored) {
    // Ignore so the application continues.
}
```

A business path may contain many other incompatible references. Fix the artifact/configuration/API instead of using `catch` as a production workaround.

## 5. Reproducing `IllegalAccessError` with two named modules

To avoid depending on internal JDK classes, we create two modules ourselves. This example uses Java 9+.

### 5.1. Project structure

```text
demo-access/
├── src/
│   ├── com.example.core/
│   │   ├── module-info.java
│   │   └── com/example/internal/HiddenApi.java
│   └── com.example.client/
│       ├── module-info.java
│       └── com/example/client/DirectClient.java
└── mods/
```

Source module:

```java
// src/com.example.core/module-info.java
module com.example.core {
    // Intentionally do not export com.example.internal.
}
```

```java
// src/com.example.core/com/example/internal/HiddenApi.java
package com.example.internal;

public final class HiddenApi {
    private HiddenApi() {}

    public static String message() {
        return "Ordinary call";
    }

    private static String secret = "Hidden data";
}
```

Client module:

```java
// src/com.example.client/module-info.java
module com.example.client {
    requires com.example.core;
}
```

```java
// src/com.example.client/com/example/client/DirectClient.java
package com.example.client;

import com.example.internal.HiddenApi;

public final class DirectClient {
    public static void main(String[] args) {
        System.out.println(HiddenApi.message());
    }
}
```

### 5.2. Compile the source module

```bash
javac -d mods/com.example.core \
  src/com.example.core/module-info.java \
  src/com.example.core/com/example/internal/HiddenApi.java
```

If compiling the client **without** an appropriate export, the compiler reports that package `com.example.internal` is not exported to the client module.

### 5.3. Compile the client with an added qualified export

```bash
javac \
  --module-path mods \
  --add-exports com.example.core/com.example.internal=com.example.client \
  -d mods/com.example.client \
  src/com.example.client/module-info.java \
  src/com.example.client/com/example/client/DirectClient.java
```

The `--add-exports` flag lets the compiler accept calls to a public API inside a package not exported through its descriptor.

Note: this is a way to **intentionally create mismatched compile/runtime configurations to learn the error mechanism**, not a recommended architecture.

### 5.4. Run without the export at runtime

```bash
java --module-path mods \
  -m com.example.client/com.example.client.DirectClient
```

When the JVM executes the call, `IllegalAccessError` can occur because `com.example.core` has not exported the package to `com.example.client` at runtime.

### 5.5. Run with the appropriate runtime export

```bash
java --module-path mods \
  --add-exports com.example.core/com.example.internal=com.example.client \
  -m com.example.client/com.example.client.DirectClient
```

The call to `HiddenApi.message()` can succeed.

**Takeaway:** `javac` options are not automatically saved as export permissions for future runs. If a project relies on flags, configure and verify **both compile and runtime environments**; if you own the target module source, it is better to design a clear public API and declare appropriate `exports`.

## 6. `IllegalAccessException`: reflection is not permitted to access a member

### 6.1. This is a checked exception

`java.lang.IllegalAccessException` extends `ReflectiveOperationException`. Reflection APIs such as `Method.invoke`, `Field.get`, `Field.set`, and `Constructor.newInstance` can throw this exception when the caller lacks access rights to the member under ordinary rules while access checks have not been validly suppressed.

Example:

```java
import java.lang.reflect.Method;

final class SecretBox {
    private String readSecret() {
        return "42";
    }
}

public class ReflectionDemo {
    public static void main(String[] args) throws Exception {
        SecretBox box = new SecretBox();
        Method method =
                SecretBox.class.getDeclaredMethod("readSecret");

        // Method is private; caller is outside SecretBox.
        Object result = method.invoke(box);
        System.out.println(result);
    }
}
```

Without a valid access override, `method.invoke(box)` will throw `IllegalAccessException`.

Here, the code does not even need to use JPMS. An ordinary classpath program can encounter this error as well.

### 6.2. Finding a method does not mean being able to call the method

Two different APIs:

- `getMethod(name, ...)` looks up a public method according to reflection rules.
- `getDeclaredMethod(name, ...)` looks up a method declared directly on the class, including non-public methods.

After obtaining the `Method`, calling `invoke` still requires appropriate access rights.

Similarly:

- `Class.getDeclaredField` can locate a private field.
- `Field.get` can refuse to read the field if not yet allowed.
- `Class.getDeclaredConstructor` can locate a private constructor.
- `Constructor.newInstance` can throw `IllegalAccessException` if access rights are invalid.

**Metadata discovery**, **access checks**, and **method execution** are three distinct steps.

### 6.3. `setAccessible(true)` can be valid in some cases

If code runs in a configuration where Java allows suppressing checks, for example when the class and caller are in an unnamed module/classpath with no additional security restrictions, you can use:

```java
Method method =
        SecretBox.class.getDeclaredMethod("readSecret");

method.setAccessible(true);
Object result = method.invoke(new SecretBox());
```

This does not mean `setAccessible(true)` **always** works. When the member belongs to a package of another named module not opened to the caller, calling `setAccessible(true)` itself can throw `InaccessibleObjectException`.

### 6.4. Do not equate with `InvocationTargetException`

If `Method.invoke` **is permitted to invoke** the method, yet the method itself throws an exception, reflection typically wraps the throwable thrown by the target inside `InvocationTargetException`.

Example:

```java
public void fail() {
    throw new IllegalStateException("Business failure");
}
```

Calling this method via reflection may yield `InvocationTargetException` with `getCause()` being `IllegalStateException`.

This is **not** a reflection access error. When investigating, read the full cause chain to avoid confusing business logic errors with `IllegalAccessException`.

### 6.5. Common causes

- Non-public method/field/constructor; framework attempts to call it without enabling access override.
- Declaring class is not visible from the caller's context.
- Caller and target are in different modules/packages with unsatisfied access checks.
- An old framework selects a reflection API incompatible with current visibility.
- A class loader/proxy alters the actual type being operated on, while code assumes the member is public.

Preferred fix: use a supported public API, appropriate constructor/factory method, or replace the framework with a version that understands the target JDK's access rules.

## 7. `InaccessibleObjectException`: deep reflection cannot be enabled

### 7.1. Exception introduced in Java 9

`java.lang.reflect.InaccessibleObjectException` was added in Java 9 alongside JPMS. It is an unchecked exception, usually thrown when code requests:

```java
accessibleObject.setAccessible(true);
```

but Java does not permit suppressing language access checks on that member.

Typical message:

```text
java.lang.reflect.InaccessibleObjectException:
  Unable to make private ... accessible:
  module java.base does not "opens java.lang" to unnamed module ...
```

The crucial phrase in the message is **`does not "opens"`**, because it points to a deep reflection boundary between the module containing the member and the module performing reflection.

### 7.2. Brief example with a JDK class

On JDKs containing the corresponding internal field, code like the following may hit an error:

```java
import java.lang.reflect.Field;

public class JdkReflectionDemo {
    public static void main(String[] args) throws Exception {
        Field field = String.class.getDeclaredField("value");
        field.setAccessible(true); // May be denied.
    }
}
```

On Java 17+ under common default configurations, package `java.lang` of module `java.base` is not open for deep reflection to classpath code, so `setAccessible(true)` can throw `InaccessibleObjectException`.

This example **is only to illustrate the error type**. Internal fields of `String` are not APIs guaranteed by Java SE to remain unchanged across versions. In real projects, do not read or modify internal fields of `String` to solve business work.

### 7.3. Why does `--add-exports` usually fail to fix this?

Suppose a framework wants to read a `private` field via reflection. Exporting the package so external code sees public types **is not sufficient** to allow accessing private members.

Example:

```bash
java --add-exports java.base/java.lang=ALL-UNNAMED \
  JdkReflectionDemo
```

The flag above **does not replace** open permission for deep reflection. When the root cause is `setAccessible(true)` into an unopened package, inspect `opens` or `--add-opens`.

This is not a recommendation to open `java.lang` in production; it is only an example showing the difference in mechanism.

### 7.4. `trySetAccessible()` and `canAccess()`

Since Java 9, the reflection API provides:

- `trySetAccessible()`: attempts to enable access override; may return `false` if it cannot be enabled due to access/module restrictions.
- `canAccess(receiver)`: checks whether in the current context the caller can access the member with the given receiver.

Example:

```java
import java.lang.reflect.Field;

public final class ReflectionProbe {
    public static void main(String[] args) throws Exception {
        Field field = String.class.getDeclaredField("value");

        if (!field.trySetAccessible()) {
            System.out.println("Không thể mở deep reflection");
            return;
        }

        // Must not depend on String implementation details.
        System.out.println("Accessible override đã được bật");
    }
}
```

`trySetAccessible()` helps react in a controlled way instead of always throwing `InaccessibleObjectException`. However, it **grants no new permissions**, and security checks or other conditions can still raise an appropriate exception.

If a framework requires internal access, the sustainable path is updating the library or API design. Do not use `trySetAccessible()` as a way to circumvent JPMS policy.

## 8. Reproducing `InaccessibleObjectException` with the project's own module

This example uses the `com.example.core` module from the previous section. Inside class `HiddenApi`, there is a private static field `secret`.

### 8.1. Reflection client does not import the hidden package

Add another class to the client module:

```java
// src/com.example.client/com/example/client/ReflectionClient.java
package com.example.client;

import java.lang.reflect.Field;

public final class ReflectionClient {
    public static void main(String[] args) throws Exception {
        Class<?> type = Class.forName(
                "com.example.internal.HiddenApi");

        Field field = type.getDeclaredField("secret");
        field.setAccessible(true);

        System.out.println(field.get(null));
    }
}
```

Because the code does not import `HiddenApi` at the source level, the compiler can compile `ReflectionClient` without needing the internal package exported. The client module already `requires com.example.core`, making the core module present in the module graph.

### 8.2. Compile the reflection client

```bash
javac --module-path mods \
  -d mods/com.example.client \
  src/com.example.client/module-info.java \
  src/com.example.client/com/example/client/ReflectionClient.java
```

This is an example independent of `DirectClient`. If sharing an output directory in a lab exercise, ensure the core module is already built and select sources to compile consistently.

### 8.3. Run without open

```bash
java --module-path mods \
  -m com.example.client/com.example.client.ReflectionClient
```

`Class.forName` can find the class and `getDeclaredField` can find the field. Yet when calling `setAccessible(true)`, the JVM refuses because package `com.example.internal` **is not open** to `com.example.client`.

The typical result is `InaccessibleObjectException` with a message stating the module does not open the package.

### 8.4. Run with qualified open

```bash
java --module-path mods \
  --add-opens com.example.core/com.example.internal=com.example.client \
  -m com.example.client/com.example.client.ReflectionClient
```

Now deep reflection can read the `secret` field.

**Takeaway:** in this example, `--add-opens` is the permission needed for deep reflection. It does not turn package `com.example.internal` into a public API that `DirectClient` can import without a corresponding export.

### 8.5. Fix at the module source if you own it

If the valid intent is to allow a specific framework to use reflection, it can be declared in the descriptor:

```java
module com.example.core {
    opens com.example.internal to com.example.client;
}
```

If ordinary access to a public API is needed, use `exports` for the appropriate API package:

```java
module com.example.core {
    exports com.example.api;
    opens com.example.model to com.example.serializer;
}
```

This approach defines the contract more clearly than adding JVM flags across many environments. Do not open an internal package merely for an error that could be resolved using a public API.

## 9. When can the same codebase exhibit all three error types?

Imagine a system with two execution paths:

1. A service calls directly into a dependency class via bytecode.
2. A serializer framework reads private fields of the same dependency via reflection.

After an upgrade:

- The direct call can raise `IllegalAccessError` because the class belongs to an unexported package at runtime.
- A reflection path calling `Method.invoke` on a non-public member without overriding access can raise `IllegalAccessException`.
- The serializer attempting `Field.setAccessible(true)` on a private member inside an unopened named-module package can raise `InaccessibleObjectException`.

Some errors may appear only during startup scanning, while others appear only on the first request using that feature.

**Do not infer from the first error that every other access error shares the same root cause.** After fixing one boundary, subsequent boundaries can finally execute and surface.

## 10. Diagnostic workflow by error type

### 10.1. Step 1: copy the exact exception class

Read the full stack trace, especially:

- The deepest meaningful `Caused by` line.
- Class/module of the caller.
- Class/module and package of the target member.
- Method/field/constructor being accessed.
- API being called when the error occurs.
- JDK and JAR versions involved.

A stack trace may contain wrappers like `BeanCreationException` or `ExceptionInInitializerError`; the wrapper name is not necessarily the root cause. Trace down to the root cause instead of modifying the framework where the wrapper was created.

### 10.2. Step 2: branch

```text
What is the error?
    |
    +-- IllegalAccessError
    |      |
    |      +--> Ordinary bytecode / linkage access?
    |                |
    |                +--> JAR v1 compile, JAR v2 runtime?
    |                +--> Member visibility changed?
    |                +--> Module does not export package?
    |
    +-- IllegalAccessException
    |      |
    |      +--> Reflection invoke/get/set/newInstance?
    |                |
    |                +--> Member private/protected/package-private?
    |                +--> Does caller have valid access?
    |                +--> Can public API or valid override be used?
    |
    +-- InaccessibleObjectException
           |
           +--> setAccessible(true) denied?
                     |
                     +--> Which source module and package?
                     +--> Is calling module named or unnamed?
                     +--> Is there an appropriate opens/--add-opens?
                     +--> Does framework have a newer version avoiding deep reflection?
```

This is an initial diagnostic tree. Real-world cases also involve class-loader conflicts and other class-loading errors that must be examined together.

### 10.3. Step 3: find where access actually occurs

For `IllegalAccessError`, the caller is usually the class containing bytecode referencing the API. That class may come from a transitive dependency rather than application source.

For `IllegalAccessException` or `InaccessibleObjectException`, the caller may be a serializer, ORM, dependency injection container, bytecode agent, or test framework. You must identify **the module of the actual code performing reflection**, not just the module containing the `main` method.

### 10.4. Step 4: verify the compiler and runtime environments

Record at minimum:

```bash
java -version
javac -version
```

With Maven:

```bash
mvn -version
mvn dependency:tree
```

With Gradle:

```bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
```

Do not treat these commands as complete proof for the production JVM. Container images, application servers, test forks, or Maven/Gradle toolchains may use different JDKs. Measure **the exact process throwing the error**.

### 10.5. Step 5: verify where the class is loaded from

If multiple JARs contain the same FQCN, runtime may load a different version than the compiler saw.

In suitable diagnostic code:

```java
static void showOrigin(Class<?> type) {
    System.out.println("Class: " + type.getName());
    System.out.println("Module: " + type.getModule());
    System.out.println("ClassLoader: " + type.getClassLoader());

    var domain = type.getProtectionDomain();
    var source = domain == null ? null : domain.getCodeSource();

    System.out.println("CodeSource: " +
            (source == null ? "unknown" : source.getLocation()));
}
```

`CodeSource` information may be absent in certain loaders or dynamically generated classes. It is only supporting evidence.

Additionally, in an appropriate environment, class loading logging can be used to see class origins, though it should be enabled selectively since logs can become large.

### 10.6. Step 6: inspect public API and bytecode

```bash
javap -classpath path/to/library.jar \
  -p -s com.example.api.AccountService
```

`javap -p` helps inspect private/public declarations; `-s` helps inspect JVM descriptors. Compare output between library v1 and v2 to find signature/visibility changes.

Note: `javap` does not by itself describe all module `exports`/`opens` permissions at runtime. Descriptors and the module graph must be inspected separately.

## 11. Inspecting JPMS with JDK tools

### 11.1. Inspecting the module descriptor

For a JAR:

```bash
jar --describe-module --file path/to/library.jar
```

For a JDK-provided module:

```bash
java --describe-module java.base
```

The output helps identify module name, exports, opens, requires, and uses/provides within what the tool reports.

If a JAR is an automatic module, its module name and export mechanics can differ from an explicit named module. Do not assume the module name equals the Maven artifactId.

### 11.2. Inspecting module resolution

Example:

```bash
java --show-module-resolution \
  --module-path mods \
  -m com.example.client/com.example.client.DirectClient
```

Used to see which modules are resolved in a specific run. A module present on the module path yet **not resolved** can cause certain `Class.forName`/service loading operations to behave unexpectedly.

### 11.3. Checking the caller and target modules

At runtime you can print:

```java
Module source = targetClass.getModule();
Module caller = callerClass.getModule();

System.out.println("Target module: " + source.getName());
System.out.println("Caller module: " + caller.getName());
```

An unnamed module typically has `getName() == null`. Distinguish between:

- Named module from the module path.
- Automatic module.
- Unnamed module of a class loader.
- Custom module layers created by the application.

The value `ALL-UNNAMED` in a JVM flag targets unnamed modules; it is not the name of a specific named module.

### 11.4. `jdeps` for finding dependencies on internal APIs

Example:

```bash
jdeps --jdk-internals path/to/application.jar
```

`jdeps` can detect some static dependencies on JDK internal APIs. It **does not** guarantee detecting reflection using class names loaded from configuration, `ServiceLoader`, or dynamically loaded plugins.

A negative result does not prove the application needs no changes when moving to a newer JDK.

### 11.5. Inspecting actual JVM arguments

A flag set in an IDE might be absent in production. A flag placed on the Maven Compiler Plugin might not be passed to Surefire. A flag in unit tests might not reach integration tests.

For a Java process you have permission to diagnose, commands such as:

```bash
jcmd <pid> VM.command_line
```

can help show the process command line. Availability depends on JDK, process permissions, and system configuration. Cross-check against actual startup scripts/containers.

## 12. `--add-exports` and `--add-opens`: choosing the right tool

### 12.1. `--add-exports` for ordinary access

Syntax:

```text
--add-exports <source-module>/<package>=<target-module>
```

Example:

```bash
java \
  --add-exports com.example.core/com.example.internal=com.example.client \
  --module-path mods \
  -m com.example.client/com.example.client.DirectClient
```

For code in an unnamed module on the classpath, the target can be:

```text
ALL-UNNAMED
```

**Do not assume exporting a package permits accessing private fields via reflection.** It serves access to public types/members under ordinary rules.

### 12.2. `--add-opens` for deep reflection

Syntax:

```text
--add-opens <source-module>/<package>=<target-module>
```

Example:

```bash
java \
  --add-opens com.example.core/com.example.internal=com.example.client \
  --module-path mods \
  -m com.example.client/com.example.client.ReflectionClient
```

If the target performing reflection is on the classpath:

```bash
java --add-opens java.base/java.lang=ALL-UNNAMED \
  -jar legacy-app.jar
```

The `java.lang` example only illustrates syntax, **it is not recommended as a default configuration for every application**. Base configurations on actual errors and documentation of the library performing deep reflection.

### 12.3. Do not invert source and target

In:

```text
--add-opens java.base/java.lang=ALL-UNNAMED
```

- `java.base` is **the module owning the package**.
- `java.lang` is **the package being opened**.
- `ALL-UNNAMED` is **the module group granted reflective access**, typically including code running on the classpath.

If a framework runs inside named module `com.example.orm`, check whether it must be opened for **that framework module**, rather than opening it to the application module merely because the application is the entry point.

### 12.4. Named module vs automatic module vs unnamed module

A legacy JAR on the classpath usually belongs to an unnamed module. Yet if the same JAR is moved to the module path, it can become an automatic module and acquire a module name.

Therefore, an `--add-opens ...=ALL-UNNAMED` flag that used to work when the framework was on the classpath may no longer target the framework once moved to the module path.

Use:

```bash
jar --describe-module --file path/to/framework.jar
```

and runtime `Class.getModule()` info to identify the proper target.

### 12.5. `--add-reads` is a different concern

If the caller module cannot yet read the target module, a `requires` relationship in the descriptor or an `--add-reads` configuration in a transitional scenario may be needed.

Do not use `--add-opens` expecting it to automatically create the `requires` relationship needed for ordinary Java source imports. Readability, exports, and opens are separate boundaries.

### 12.6. An error should not be solved unconditionally with JVM flags

Sometimes `IllegalAccessError` occurs because a method changed from `public` to package-private within **the same unnamed-module classpath**; there is no package export to open to fix that method's visibility.

Sometimes `IllegalAccessException` happens simply because the caller tries to invoke a private method; the proper solution is using the public API or handling reflection per contract, not opening `java.base`.

Sometimes `InaccessibleObjectException` happens because an old framework uses deep reflection into JDK internals; upgrading the framework should come before choosing a workaround.

## 13. Differences between Java 8, Java 9–16, and Java 17+

### 13.1. Java 8: no JPMS yet

Java 8 has no `module-info.java`, `--add-opens`, or `InaccessibleObjectException`. However, `IllegalAccessError` and `IllegalAccessException` can still occur from Java access/linkage rules and reflection.

If an application running on Java 8 uses reflection on private JDK fields, upgrading the JDK can cause those operations to be blocked by the new boundaries.

### 13.2. Java 9–15: transitional mechanism for some JDK internals

Java 9 introduced JPMS and strong encapsulation. Certain JDK packages existing since Java 8 were handled under **relaxed strong encapsulation** during a transition period, potentially emitting "illegal reflective access" warnings.

The `--illegal-access` option used to affect this transitional mechanism. Yet it did not open every internal API, and it is not a long-term compatibility solution.

### 13.3. Java 16: stricter default strong encapsulation

Java 16 shifted the default toward stronger encapsulation. Some older code that used to run with warnings on earlier JDKs may fail without an appropriate solution.

### 13.4. Java 17+: JEP 403 enforces strong encapsulation

Starting in Java 17, JEP 403 reinforces strong encapsulation for JDK internals. The old `--illegal-access` option no longer functions as the permission-opening mechanism many applications previously relied on.

If deep reflection into a specific package is truly required, targeted `--add-opens` can be used; if ordinary access to an unexported package is required, appropriate `--add-exports` can be used. Still, the sustainable solution remains using public APIs and upgrading libraries/JDK tooling.

**Do not assume every package named `sun.*` or `com.sun.*` behaves the same.** Some APIs have distinct compatibility statuses, such as those provided via `jdk.unsupported`; check the target JDK's module descriptors and documentation.

### 13.5. Do not rely on old warnings to predict newer JDKs

If an app runs on JDK 11 and prints illegal reflective access warnings, that is a signal to investigate **before** upgrading to JDK 17/21. The fact that a warning did not break the app on an older JDK does not prove the app will keep running once encapsulation policies tighten.

## 14. Distinguishing similar errors with different causes

| Error | Common meaning | Why does it differ from the three main errors? |
| --- | --- | --- |
| `ClassNotFoundException` | The class loader cannot find the requested class name. | A class lookup problem, not necessarily an access issue. |
| `NoClassDefFoundError` | The JVM cannot find/define a required class at runtime, or prior class initialization failed. | Requires investigating dependencies/loading/init, not just module exports. |
| `NoSuchMethodError` | Binary references a method signature missing at runtime. | Binary mismatch, not access to a method that still exists. |
| `NoSuchFieldError` | Binary references a field missing at runtime. | Missing field, not visibility. |
| `IncompatibleClassChangeError` | Incompatible class/interface change or bytecode linkage. | Larger category; `IllegalAccessError` belongs to this branch. |
| `NoSuchMethodException` | Reflection cannot find the requested method. | Lookup fails before invoke access checks. |
| `InvocationTargetException` | Method/constructor invoked via reflection throws an exception. | Failure from the target itself, not necessarily access rights. |
| `SecurityException` | Access denied by a relevant security mechanism. | Must identify the mechanism/permission, do not assume JPMS. |
| `ExceptionInInitializerError` | A static initializer failed. | May wrap a deeper cause; read the cause. |

In particular, an exception containing the word "access" does not mean `--add-opens` is the right fix. Classify according to **the API performing the action** and **which access condition was violated**.

## 15. Where do frameworks, ORMs, serializers, and test tools commonly fail?

### 15.1. Dependency injection containers

A container may use reflection to call constructors or inject fields. After upgrading the JDK or moving JARs to named modules, it may lose access to private members if packages are not open.

If the stack trace points to `setAccessible` inside the framework, prioritize checking framework versions supporting the target JDK and module configuration, rather than modifying `@Autowired`/`@Inject` arbitrarily.

### 15.2. ORMs and entity reflection

An ORM may read entity fields, instantiate via constructors, or create proxies. Sensitive cases typically include:

- Entities residing in a named module.
- Entity packages not `opens` to the ORM module.
- An older ORM version using JDK internals or bytecode enhancement not yet supporting the target JDK.

If you own the entity module, a qualified `opens` for the ORM module can be cleaner than opening the entire module.

Example **for architectural illustration only**:

```java
module com.example.domain {
    requires jakarta.persistence;

    opens com.example.domain.entity to org.hibernate.orm.core;
}
```

The actual module name depends on the exact Hibernate/JPA version in use. Do not copy this configuration without verifying the module name in your project's dependencies.

### 15.3. JSON/XML serializers

A serializer framework may read private fields or construct objects via non-public constructors. If deep reflection is disallowed, `InaccessibleObjectException` can appear.

A sustainable fix can be using public accessors/constructors, record support, or a newer serializer version, rather than having to open whole packages.

### 15.4. Mocking and test instrumentation

Mockito, Byte Buddy, JUnit extensions, or coverage agents can trigger reflection/instrumentation errors on newer JDKs.

Factors to distinguish:

- `InaccessibleObjectException` due to an unopened module package.
- Unsupported class-file version due to outdated Byte Buddy/ASM.
- Agent attach issue or provider/test engine error.
- `IllegalAccessError` when a generated class or proxy attempts invalid package/member access.

Adding `--add-opens` does not solve unsupported class-file version errors. Upgrading the right dependencies and test tooling is a prerequisite for migration.

### 15.5. Java agents and class loaders

An agent can transform bytecode or define classes at runtime. A class generated in another loader/module may be blocked from accessing an API that source compilation previously allowed.

For this type of error, identify:

- Generated class FQCN.
- ClassLoader/module of the generated class.
- Target package/member.
- Bytecode transformation/version.
- Exports/opens mechanism the agent is permitted to use.

Do not assume the error belongs to application source merely because the stack trace starts from a request handler.

## 16. Maven and Gradle: placing options in the right phase

### 16.1. Compile-time exports in Maven

If source **intentionally imports** a public type in an unexported package, Maven Compiler Plugin may need corresponding compiler arguments.

Conceptual configuration example:

```xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-compiler-plugin</artifactId>
  <configuration>
    <compilerArgs>
      <arg>--add-exports</arg>
      <arg>com.example.core/com.example.internal=com.example.client</arg>
    </compilerArgs>
  </configuration>
</plugin>
```

Select an appropriate plugin version in the real POM. When using `--release`, the compiler has rules restricting certain combinations of `--add-exports` with system modules; the long-term solution is removing dependencies on internal JDK APIs.

**Important:** compiler flags do not guarantee the same export at runtime.

### 16.2. Runtime opens in Maven Surefire/Failsafe

If the test JVM runs reflection frameworks and needs a package opened temporarily:

```xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-surefire-plugin</artifactId>
  <configuration>
    <argLine>
      --add-opens java.base/java.lang=ALL-UNNAMED
    </argLine>
  </configuration>
</plugin>
```

This example illustrates how to pass a JVM argument to the forked test JVM; **it is not a recommendation to open `java.lang` in every project**.

If the project uses JaCoCo or other agents via `argLine`, arguments must be merged rather than overwritten. For integration tests via Failsafe, check the **Failsafe JVM** configuration instead of assuming Surefire options apply automatically.

### 16.3. Gradle `JavaCompile` and `Test`

Gradle Groovy DSL example:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += [
        '--add-exports',
        'com.example.core/com.example.internal=com.example.client'
    ]
}

tasks.withType(Test).configureEach {
    jvmArgs(
        '--add-opens',
        'com.example.core/com.example.internal=com.example.client'
    )
}
```

This is an example of **where to configure**, not an indication that both flags are needed for every application. Set the right target module, right task, and right issue.

If the app runs via `JavaExec` or inside a container/app server, JVM arguments from `Test` **do not automatically carry over**. Verify the actual startup command of each environment.

### 16.4. Placing flags on the real runtime

Some environments involve multiple distinct JVMs:

```text
Developer IDE
      |
      +-- Build JVM (Maven/Gradle)
      +-- Compiler/annotation processor
      +-- Unit-test JVM
      +-- Integration-test JVM
      +-- App JVM
      +-- Production container JVM
      +-- Agent/tool JVM
```

If an error occurs only during integration tests, fixing the unit-test JVM will not resolve it.

Likewise, whether a flag exists in `JAVA_TOOL_OPTIONS` or some startup script must be verified; do not assume every Java process reads the same configuration.

## 17. Handling workflow in Java compatibility migration

### Step 1: classify the symptom instead of rushing to add a flag

Save the stack trace and environment. Identify `IllegalAccessError`, `IllegalAccessException`, or `InaccessibleObjectException`; record the API where the error occurred.

### Step 2: identify caller, target, class loader, and module

For JPMS, read the phrase "module X does not export/open package Y to Z". For binary mismatch, identify the JAR the caller compiled against and the JAR loaded at runtime.

### Step 3: build a minimal experiment

Create a reproducer with the exact class/member and exact JDK/module path. Avoid pulling in an entire framework if two small modules can reproduce it.

### Step 4: inspect dependencies and API diffs

If `IllegalAccessError`, compare visibility/JVM descriptors between before/after libraries. Check dependency mediation, BOMs, shaded JARs, and container-provided JARs.

If a reflection error, check the framework version and the reflection API being used.

### Step 5: prioritize fixing via public API or supported versions

Usually appropriate priorities:

1. Upgrade the framework/library to a version supporting the target JDK.
2. Replace internal APIs with public APIs.
3. If owning the module, declare minimal `exports`/`opens` per contract.
4. If a transition is required, add `--add-exports`/`--add-opens` for the exact module/package/target and record a removal plan.

Do not use flags to sustain code relying on JDK implementation details long-term once a replacement API exists.

### Step 6: test compile and runtime separately

If ordinary access is needed, verify compile and runtime share the same contract. If reflection is needed, exercise the exact code path calling `setAccessible`, not merely startup checks.

### Step 7: run compatibility tests on the target JDK

Tests should include:

- Recompiling consumer source against candidate libraries.
- Running old consumer binaries if binary compatibility is committed.
- Unit/integration tests on the new JDK.
- Real business flows exercising reflection/serialization/ORM.
- Both classpath and module-path variants if both are supported.
- Test JVM, application JVM, and container runtime per deployment configuration.

### Step 8: review temporary open permissions

Document:

| Field | Content |
| --- | --- |
| Flag | Verbatim flag string. |
| Why needed | Root error and stack trace. |
| Source module/package | Module and package being accessed. |
| Target module | Named module or `ALL-UNNAMED`. |
| Dependent component | Library/framework and version. |
| Target JVM | Compiler/test/app/production. |
| Risk | Internal API, deep reflection, and permission scope. |
| Owner | Responsible team. |
| Flag removal milestone | Dependency/JDK version or planned migration release. |
| Evidence | Before/after tests and runtime logs. |

## 18. Common mental traps

### 18.1. "Whenever there's IllegalAccess, enable `--add-opens`"

False. `IllegalAccessError` often happens in ordinary access/linkage. `IllegalAccessException` can simply result from a private member during ordinary reflection. `InaccessibleObjectException` is the typical sign of a deep reflection request rejected at `setAccessible`.

### 18.2. "`--add-exports` opens private fields"

False. Exporting does not change Java access modifiers. If deep reflection must be permitted, look at opening the package, though reducing reliance on private fields is better.

### 18.3. "`--add-opens` lets source import an internal package"

False. `--add-opens` primarily controls deep reflection at runtime; it does not replace exports for `javac` to allow ordinary source access.

### 18.4. "Having `requires` makes every package in the module visible"

False. Readability and exports are two separate conditions.

### 18.5. "`setAccessible(true)` on newer Java always throws"

False. It can succeed when the caller is in the same module, when the package is appropriately opened, or in situations permitted by the reflection API. What matters is the **specific context**.

### 18.6. "Adding a flag only to tests automatically applies in production"

False. Test JVMs and production JVMs usually have separate processes/configurations.

### 18.7. "Fixing one access error makes all exceptions vanish"

False. A flow can use both ordinary access and deep reflection. After fixing the first boundary, the next error may surface.

### 18.8. "A stack trace showing a framework means the framework definitely has a bug"

Not necessarily. It may be an old framework version, JDK policy change, application module descriptor missing `opens`, wrong dependency mediation, or an agent causing a class-loader mismatch. Establish root cause via module/classpath evidence.

### 18.9. "Compatibility flags are a permanent solution"

Do not assume so. An internal package can change in a newer JDK; opening permissions does not keep classes/methods present or stable. Every workaround must be inventoried and scheduled for removal.

## 19. Error classification practice

### Scenario A: compiled in one place, run in another

A consumer is compiled against library v1 which has `public void sync()`. Production accidentally loads library v2 where the method changed to package-private.

**Question:** which error is likely when consumer bytecode calls the method?

**Guidance:** `IllegalAccessError`; inspect runtime JARs and binary compatibility. Do not use `--add-opens` to alter a method's access modifier.

### Scenario B: reflection on a private method

A test class executes:

```java
Method m = Demo.class.getDeclaredMethod("privateAction");
m.invoke(new Demo());
```

`privateAction` is private and the test class lacks access rights.

**Question:** which exception typically occurs?

**Guidance:** `IllegalAccessException` at `invoke`. Review test design, public API, and whether suppressing access checks is valid.

### Scenario C: serializer calls `setAccessible(true)`

A serializer framework in an unnamed module on the classpath attempts to access a private field inside an unopened package of named module `com.example.domain`.

**Question:** which exception typically occurs, and why?

**Guidance:** `InaccessibleObjectException` at `setAccessible(true)`. Identify the target package and check `opens` or upgrade the framework/switch to public accessors.

### Scenario D: added a flag yet still fails

The application has:

```text
--add-exports com.example.domain/com.example.model=ALL-UNNAMED
```

Yet the framework uses deep reflection on a private field and reports the package is not open.

**Question:** why is the export insufficient?

**Guidance:** ordinary access and deep reflection require different permissions. If no public API alternative exists, open the right package to the module performing reflection per contract rather than adding random exports.

### Scenario E: warning on Java 11, error on Java 17

An old framework reads a private field of a JDK class. On Java 11 it runs with an illegal reflective access warning; on Java 17 `InaccessibleObjectException` appears.

**Question:** in what order should you diagnose?

**Guidance:** inspect JDK/framework versions, module/package/caller, locate a framework version supporting Java 17, replace internal API usage; consider scoped `--add-opens` only when a transitional step is needed.

## 20. Checklist before concluding resolution

- [ ] Accurately distinguished `IllegalAccessError`, `IllegalAccessException`, and `InaccessibleObjectException`.
- [ ] Read the root cause and relevant `Caused by` lines, not just wrapper exceptions.
- [ ] Determined whether it is ordinary bytecode access, reflection invoke, or `setAccessible`.
- [ ] Identified the class/member, caller, source module, target module, and package.
- [ ] Verified the class/JAR loaded by runtime, not just the version in the POM.
- [ ] Compared public API/visibility and bytecode if binary incompatibility is suspected.
- [ ] Checked `requires`/module readability, `exports`, and `opens` separately.
- [ ] Distinguished named/automatic/unnamed modules and classpath/module path.
- [ ] Checked Java versions of compiler, unit tests, integration tests, and production.
- [ ] Prioritized public APIs or dependencies/frameworks supporting the target JDK.
- [ ] If using a JVM flag, selected the right flag type, source/package, target, and JVM process.
- [ ] Re-ran the business path triggering reflection, not just startup tests.
- [ ] Ran consumer recompile/binary/regression tests suited to the migration scope.
- [ ] Documented temporary workarounds, owners, and removal milestones.
- [ ] Verified the real deployed artifact and confirmed no remaining dependency conflicts.

## 21. Conclusion

Three similar names reflect three distinct problems. **`IllegalAccessError`** usually states that bytecode or module access at runtime no longer satisfies linking/access conditions. **`IllegalAccessException`** indicates that a reflection call is rejected by Java access checks. **`InaccessibleObjectException`** indicates that runtime does not permit enabling deep reflection via `setAccessible(true)`, usually because a named module's package has not been opened to the caller.

When diagnosing in Java Advance Compatibility Migration, start from **the error type and actual access operation**, then cross-check visibility, JPMS module graph, runtime JARs, and JDK version. Choose `exports` for ordinary access, `opens` for deep reflection when truly necessary, while prioritizing public APIs and supported libraries. A solution is considered complete when the exact code path has executed on the target JDK, the outcome is verified by tests, and any temporary open permissions are managed rather than becoming open-ended technical debt.
