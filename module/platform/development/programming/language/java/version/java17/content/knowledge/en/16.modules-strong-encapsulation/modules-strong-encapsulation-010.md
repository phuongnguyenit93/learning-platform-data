# Testing Reflection Libraries in a Real Module Environment

## 1. Why Test Reflection on the Module Path?

Since Java 9, the Java Platform Module System (JPMS) has enabled applications to package code into **named modules**, declare dependencies, and control which packages are exposed or opened for reflection. Java 17 enforces *strong encapsulation* at runtime.

A library may work normally when an application places all classes on the **classpath**, yet fail when moved to the **module path**. The cause is usually that the library needs to read/write private fields, call non-public constructors, or inspect metadata via reflection, while the module containing the class has not opened the corresponding package to the library module.

Common scenarios include JSON mappers, dependency injection, ORMs, bean mappers, validation frameworks, serializers, plugin frameworks, and test frameworks. If production runs named modules, integration tests must run in a **real module environment**. Running tests solely on the classpath can mask errors because the classpath belongs to the unnamed module and does not reflect `exports`/`opens` boundaries.

This lesson focuses on distinguishing `exports`/`opens`, verifying deep reflection, setting up two named modules, running tests on the module path, and diagnosing errors in real-world libraries.

## 2. JPMS Fundamentals to Know

### 2.1. Module descriptor

A named module typically has a `module-info.java` file at the source root:

```java
module com.acme.domain {
    exports com.acme.domain.api;
}
```

A module descriptor can declare:

- `requires`: module dependencies.
- `exports`: exposes packages to other modules' code.
- `opens`: allows deep reflection into packages at runtime.
- `uses` and `provides ... with ...`: the service provider mechanism.

Example:

```java
module com.acme.application {
    requires com.acme.domain;
    requires java.net.http;
}
```

When modules sit on the module path, the JVM builds the module graph and enforces readability, exports, and opens rules. These rules are not checked identically when all code runs in the unnamed module on the classpath.

### 2.2. Classpath and module path

| Execution mode | Code organization | Module boundaries |
|---|---|---|
| Classpath | Classes/JARs typically belong to the unnamed module | No per-module application exports/opens |
| Module path | Named modules and descriptors are read | Enforces readability, exports, and opens |
| Automatic module | JAR without a descriptor gets a derived module name | Has an automatic module name and participates in the module graph per automatic module rules |

Unix-style shell example:

```shell
java -cp app.jar:lib.jar com.acme.Main
java --module-path mods -m com.acme.application/com.acme.application.Main
```

On Windows, the classpath separator is typically `;`; on Linux/macOS it is typically `:`.

**Key point:** testing reflection solely on the classpath does not prove a library is compatible with strong encapsulation. If production uses the module path, integration tests must use the module path and module descriptors closely matching production.

## 3. exports and opens Solve Two Different Needs

### 3.1. exports: exposing APIs

`exports` exposes public types in a package:

```java
module com.acme.domain {
    exports com.acme.domain.api;
}
```

Consumers can import and call the public API:

```java
import com.acme.domain.api.Customer;
Customer customer = new Customer("C-100", "An");
System.out.println(customer.name());
```

`exports` does not mean private fields/methods in the package can be accessed via deep reflection. It primarily governs public API access under module rules and Java access control.

### 3.2. opens: allowing deep reflection

`opens` allows the target module to use reflection for deep access to members of a package, including non-public members, subject to `AccessibleObject` rules:

```java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.model to com.acme.jsonmapper;
}
```

Here, `com.acme.domain.api` is the public API; `com.acme.domain.model` is opened specifically to the mapper module. If a library only calls public accessors, `exports` alone may suffice. If it needs private fields or non-public constructors, the package must be opened to the exact module performing reflection.

### 3.3. Comparison table

| Declaration | Public API to other modules | Deep reflection |
|---|---|---|
| Neither `exports` nor `opens` | Not exposed | No |
| `exports p` | Yes, to all modules reading the source module | Does not automatically grant deep access |
| `exports p to m` | Yes, only to module `m` | Does not automatically grant deep access |
| `opens p` | Does not make package a compile-time API | Yes at runtime |
| `opens p to m` | Does not make package a compile-time API | Yes for module `m` |
| `open module x { ... }` | Still requires `exports` to expose compile-time APIs | Opens all packages for runtime reflection |

### 3.4. Qualified opens and open module

Prefer targeted package opening:

```java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.model
            to com.acme.jsonmapper, com.acme.persistence;
}
```

Target module names must match the libraries' actual module names in the module graph. Do not guess names from JAR filenames; inspect descriptors or automatic module names.

`open module com.acme.domain { ... }` opens all packages for deep reflection at runtime. It does not turn all packages into public compile-time APIs. This is a broad configuration; use it only when the entire module is intentionally designed for deep reflection.

## 4. Reflection and Strong Encapsulation

### 4.1. Metadata discovery vs member access

Core reflection provides APIs:

- `Class.getFields()`, `getDeclaredFields()`.
- `Class.getMethods()`, `getDeclaredMethods()`.
- `Class.getConstructors()`, `getDeclaredConstructors()`.
- `Field`, `Method`, `Constructor`.
- `AccessibleObject.setAccessible`, `trySetAccessible`, `canAccess`.

Retrieving member metadata and being permitted to access a member are two different things. You can obtain a `Field` object describing a private field, yet reading the field remains blocked if the module/package denies access.

```java
Field field = Customer.class.getDeclaredField("email");
```

`getDeclaredField` locates a field declared directly on the class; it does not automatically grant permission to read the private value.

### 4.2. trySetAccessible and setAccessible

```java
boolean allowed = field.trySetAccessible();
```

- `trySetAccessible()` attempts to enable deep access; returns `true` if successful, `false` if it cannot be enabled.
- `setAccessible(true)` requests enabling access; if the module does not open the appropriate package, it can throw `InaccessibleObjectException`.
- If access suppression is not enabled, `Field.get`, `Field.set`, or `Method.invoke` can throw `IllegalAccessException`.

Example:

```java
Field field = Customer.class.getDeclaredField("email");
if (field.trySetAccessible()) {
    System.out.println(field.get(customer));
} else {
    System.out.println("Package is not opened to caller");
}
```

### 4.3. canAccess

`AccessibleObject.canAccess(Object obj)` checks whether the member is accessible from the current caller:

```java
Field instanceField = Customer.class.getDeclaredField("email");
boolean canRead = instanceField.canAccess(customer);
```

For instance fields/methods, pass the receiver object. For static members, pass `null`. An unsuitable receiver can throw `IllegalArgumentException`. `canAccess` does not open packages itself and does not replace `trySetAccessible`.

### 4.4. InaccessibleObjectException

Example:

```text
java.lang.reflect.InaccessibleObjectException:
Unable to make field private ... accessible:
module com.acme.domain does not "opens com.acme.domain.api"
to module com.acme.reflecttest
```

The message typically states the class's module, the member's package, and the caller module performing deep reflection. These three details identify the `opens` directive to evaluate. Do not open an entire module before identifying which library genuinely needs that access.

## 5. Example with Two Named Modules to Test Reflection

We create two modules: `com.acme.domain` containing a model and `com.acme.reflecttest` testing reflection. The goal is observing the exact same class under two configurations: when the package is exported but unopened, public APIs work and private reflection is blocked; when the package is opened to the test module, deep reflection succeeds.

### 5.1. Directory structure

```text
reflection-lab/
└── src/
    ├── com.acme.domain/
    │   ├── module-info.java
    │   └── com/acme/domain/api/Customer.java
    └── com.acme.reflecttest/
        ├── module-info.java
        └── com/acme/reflecttest/ReflectionProbe.java
```

### 5.2. Domain module descriptor

File `src/com.acme.domain/module-info.java`:

```java
module com.acme.domain {
    exports com.acme.domain.api;
}
```

The API package is exported without `opens`.

### 5.3. Class with private fields

File `src/com.acme.domain/com/acme/domain/api/Customer.java`:

```java
package com.acme.domain.api;

public final class Customer {
    private final String email;
    private final String name;

    public Customer(String email, String name) {
        this.email = email;
        this.name = name;
    }

    public String name() {
        return name;
    }
}
```

### 5.4. Test module descriptor

File `src/com.acme.reflecttest/module-info.java`:

```java
module com.acme.reflecttest {
    requires com.acme.domain;
}
```

### 5.5. Probe program

File `src/com.acme.reflecttest/com/acme/reflecttest/ReflectionProbe.java`:

```java
package com.acme.reflecttest;

import com.acme.domain.api.Customer;
import java.lang.reflect.Field;

public class ReflectionProbe {
    public static void main(String[] args) throws Exception {
        Customer customer = new Customer("an@example.test", "An");
        System.out.println("Public name: " + customer.name());

        Field email = Customer.class.getDeclaredField("email");
        System.out.println("Field found: " + email.getName());

        boolean opened = email.trySetAccessible();
        System.out.println("Deep reflection allowed: " + opened);

        if (opened) {
            System.out.println("Private email: " + email.get(customer));
        } else {
            try {
                email.get(customer);
                throw new AssertionError("Expected IllegalAccessException");
            } catch (IllegalAccessException expected) {
                System.out.println("Private field access was blocked");
            }
        }
    }
}
```

### 5.6. Compiling and running on the module path

From the `reflection-lab` directory:

```shell
javac --module-source-path src -d mods \
  -m com.acme.domain,com.acme.reflecttest

java --module-path mods \
  -m com.acme.reflecttest/com.acme.reflecttest.ReflectionProbe
```

Expected output:

```text
Public name: An
Field found: email
Deep reflection allowed: false
Private field access was blocked
```

This proves that `exports` suffices for public APIs yet does not grant permission to read private fields via deep reflection.

## 6. Opening the Package Selectively and Re-running the Test

### 6.1. Qualified opens in module-info.java

Update the domain module descriptor to:

```java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.api to com.acme.reflecttest;
}
```

The `opens` directive grants deep reflection permission on package `com.acme.domain.api` to module `com.acme.reflecttest`. It does not replace `exports`; `exports` is still required for the test module to import and call public APIs at compile time.

Recompile:

```shell
javac --module-source-path src -d mods \
  -m com.acme.domain,com.acme.reflecttest
```

Run:

```shell
java --module-path mods \
  -m com.acme.reflecttest/com.acme.reflecttest.ReflectionProbe
```

Expected output:

```text
Public name: An
Field found: email
Deep reflection allowed: true
Private email: an@example.test
```

### 6.2. Why is qualified opens better than open module?

The domain module grants deep access only to the specific test module. Other modules do not automatically receive that permission. This is the **least privilege** principle applied to module descriptors.

In production, replace `com.acme.reflecttest` with the actual module name of the library needing reflection. Do not open a package to a test module and assume production frameworks will also be permitted; different caller modules have different permissions.

### 6.3. Inspecting modules/packages at runtime

Java lets you inspect module status:

```java
Module domainModule = Customer.class.getModule();
Module callerModule = ReflectionProbe.class.getModule();

System.out.println(domainModule.getName());
System.out.println(callerModule.getName());

System.out.println(domainModule.isExported(
        "com.acme.domain.api", callerModule
));
System.out.println(domainModule.isOpen(
        "com.acme.domain.api", callerModule
));
```

These results report whether the package is exported/opened to the specific caller module. This information is helpful when diagnosing tests running in complex module graphs.

## 7. Using --add-opens in Tests/Runtime

### 7.1. Adding open access via command line

In some cases, the module descriptor of the module containing the model cannot be modified, such as a module coming from a third-party dependency. You can test granting open access at runtime with:

```shell
java --module-path mods \
  --add-opens com.acme.domain/com.acme.domain.api=com.acme.reflecttest \
  -m com.acme.reflecttest/com.acme.reflecttest.ReflectionProbe
```

Syntax:

```text
--add-opens <source-module>/<package>=<target-module>
```

This command opens package `com.acme.domain.api` in source module `com.acme.domain` to target module `com.acme.reflecttest` at runtime.

This is useful to:

- Quickly verify whether a failure stems from an unopened package.
- Run tests against dependencies whose module descriptors cannot be edited.
- Provide temporary runtime configuration while planning a migration.

If this permission is a long-term production requirement, consider placing qualified `opens` in the package-owning module's descriptor, or using controlled launcher configuration per deployment policy.

### 7.2. ALL-UNNAMED is for code on the classpath

If a reflection library runs on the classpath, the caller belongs to the unnamed module. You can use:

```shell
java --module-path mods \
  --add-opens com.acme.domain/com.acme.domain.api=ALL-UNNAMED \
  -cp legacy-mapper.jar \
  com.acme.legacy.Main
```

`ALL-UNNAMED` opens the package to unnamed modules. This has a broader scope than a specific target module. Whenever possible, run the library as a named module and open the package only to that module.

Do not write `ALL-UNNAMED` in an `opens ... to ...` directive inside `module-info.java`; it is a special target for command-line options, not a Java module name in source descriptors.

### 7.3. --add-exports does not replace --add-opens

These two options:

```text
--add-exports source.module/package=target.module
--add-opens   source.module/package=target.module
```

are not equivalent:

- `--add-exports` allows accessing public types/members of a package not exported by its module descriptor, within the runtime/compile scope where the option applies.
- `--add-opens` allows deep reflection into a package at runtime.

If a library needs access to private fields, `--add-exports` alone is insufficient. If code needs to import a public class from an unexported package, `--add-opens` does not replace `exports` for compile-time APIs.

### 7.4. Do not rely on --illegal-access

Older guides sometimes recommended `--illegal-access=permit` to relax access into JDK internals. On Java 17, do not use this option as a module-opening workaround; strong encapsulation of JDK internals is enforced and the old option no longer restores the previous broad access behavior.

If a library needs internal JDK access, upgrade the library to a compatible version or switch to supported public APIs. Do not build new applications relying on access to JDK internals.

## 8. Testing Real-World Reflection Libraries

Writing two small modules helps illustrate the rules. When integrating a real library, determine **which module performs reflection** and which application packages are accessed.

### 8.1. Determining the dependency's module name

The JAR filename is not necessarily the module name. Inspect it:

```shell
jar --describe-module --file path/to/library.jar
```

For JARs with `module-info.class`, the command shows the module descriptor. For JARs without a descriptor, the JDK may show the automatic module name derived from metadata/JAR filename.

You can inspect the module graph at startup:

```shell
java --show-module-resolution \
  --module-path mods:lib \
  -m com.acme.application/com.acme.application.Main
```

If a dependency runs on the classpath, it belongs to the unnamed module; in that case, the target of `--add-opens` is typically `ALL-UNNAMED`.

### 8.2. Identifying which packages need opening

Do not open every domain package merely because a framework throws `InaccessibleObjectException`. Read the exception to find:

- The module containing the class/field/constructor.
- The package containing the member.
- The caller module performing `setAccessible`.
- The specific member the library needs to access.

Then decide:

1. Can the library use public constructors/accessors instead of private reflection?
2. Can the model be adapted to an API supported by the framework without exposing private state?
3. If deep reflection is truly needed, can only the exact package be opened to the exact module?

### 8.3. Separating public API packages from model packages

A design can separate:

```text
com.acme.domain
├── com.acme.domain.api       (exports)
├── com.acme.domain.model     (opens to mapper)
└── com.acme.domain.internal  (not exported, not opened)
```

Module descriptor:

```java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.model to com.acme.jsonmapper;
}
```

Public APIs are used normally. The mapper is allowed deep reflection on the model package. Internal packages remain closed to other consumers.

This preserves intentional encapsulation: open what frameworks require, without opening the whole module.

### 8.4. Testing with the exact production module path

A valuable integration test matches production wherever module access is affected:

- Application module descriptors match or mirror production.
- Dependencies are on the module path if production uses the module path.
- Dependency module names are accurately determined.
- The test launcher passes the same `--add-opens`/`--add-exports` if production actually requires them.
- Tests do not accidentally place modules under test onto the classpath.
- The JDK runtime matches the deployment environment.

If production runs named modules yet the test runner puts all code on the classpath, tests may pass while production fails. Configure the test fork to run on the module path or build a dedicated integration test that launches a JVM with the real module graph.

## 9. Contract Testing: Public APIs, Deep Reflection, and Expected Failures

A good test does more than prove "reflection works." It verifies which access permissions are intended by design.

### 9.1. Test that public APIs still work when the package is only exported

```java
Customer customer = new Customer("a@example.test", "An");
assertEquals("An", customer.name());
```

This is a public contract. If only public APIs are needed, do not open the package just to make this test pass.

### 9.2. Test that deep reflection is blocked when the package is unopened

```java
Field field = Customer.class.getDeclaredField("email");
assertFalse(field.trySetAccessible());
```

If the design requires external modules not to access private state, this is a valuable test. You can further assert that `field.get(customer)` throws `IllegalAccessException`.

### 9.3. Test that deep reflection succeeds when the package is opened to the right module

```java
Field field = Customer.class.getDeclaredField("email");
assertTrue(field.trySetAccessible());
assertEquals("a@example.test", field.get(customer));
```

This test should run only in a module configuration with the corresponding `opens` directive or a JVM launched with `--add-opens` targeting the test module.

### 9.4. Test the library rather than just the reflection API

If the application uses a JSON mapper, invoke its actual serialization/deserialization API:

```java
// Pseudocode: replace with the API of the library in use.
String json = mapper.writeValueAsString(customer);
Customer copy = mapper.readValue(json, Customer.class);
assertEquals(customer.name(), copy.name());
```

Also test the patterns the framework needs to access:

- Public constructors/accessors.
- Non-public constructors if the framework is configured to use them.
- Private fields if the framework is configured for field access.
- Annotations and generic metadata.
- Inheritance or nested types if used by models.

Do not assume a library always needs `opens` simply because it uses reflection. Some libraries only inspect public metadata and call accessors; others may require deep reflection depending on mapping mode. Check the documentation and behavior of the exact version used.

## 10. JUnit and Test Frameworks in a Modular Environment

### 10.1. The test framework is also a caller module

When tests run inside a named module, the test framework may need to:

- Read the module containing tests.
- Discover test classes/methods.
- Invoke constructors or methods reflectively.
- Access packages holding fixtures or test support classes.

Therefore, when testing on the module path, identify the caller module performing reflection. The test framework may need test packages opened to the framework; meanwhile, a production library needs model packages opened to that production library's module.

~~~text
com.acme.domain
    opens com.acme.domain.model to com.acme.mapper;

com.acme.tests
    opens com.acme.tests to <test-framework-module>;
~~~

Obtain the framework module name from the JAR/module descriptor of the exact dependency version, not by guessing from the Maven artifact name.

### 10.2. Do not add opens for tests and forget production

Suppose JUnit tests pass because the test command includes:

```text
--add-opens com.acme.domain/com.acme.domain.model=ALL-UNNAMED
```

yet production runs on the module path without that flag. Passing tests do not prove production works.

Decide which module needs which package opened and ensure production has matching permissions if the framework truly needs them. If only the test framework requires access, do not widen model package permissions unnecessarily.

### 10.3. Integrating with build tools

Maven and Gradle may run tests on the classpath or module path depending on configuration and plugin versions. Do not assume that merely having `module-info.java` in a project means the test runner executes as a named module.

When configuring tests:

1. Inspect the actual JVM command used by the build tool.
2. Verify whether dependencies sit on the module path or classpath.
3. Verify whether the test module is named or running in the unnamed module.
4. Inspect any `--add-opens`/`--add-exports` flags passed.
5. Add a separate forked integration test if the build tool's default runner does not execute the target module graph.

A test spawning a child JVM with `ProcessBuilder` and `--module-path` can also verify the real setup, provided class/module artifacts match production.

## 11. MethodHandles and Other Reflection Mechanisms

### 11.1. MethodHandles are not a way to bypass JPMS

Java offers `MethodHandles` and `MethodHandles.Lookup` to access methods/fields via handles. They are useful for high-performance frameworks or APIs representing operations as objects.

`MethodHandles.privateLookupIn(targetClass, lookup)` also obeys module rules. The module containing the package must be opened to the appropriate caller module; otherwise acquiring a private lookup fails.

```java
MethodHandles.Lookup privateLookup =
        MethodHandles.privateLookupIn(
                Customer.class,
                MethodHandles.lookup()
        );
```

Do not treat `MethodHandles` as a workaround to avoid `opens`. If a library needs private access, the module boundary must permit it.

### 11.2. Reflection and serialization

Serialization frameworks can employ several strategies:

- Public constructors or factories.
- Accessors.
- Special constructors.
- Field reflection.
- MethodHandles.
- Compile-time generated code.

Different strategies yield different module requirements. Read the library's module documentation and test under the exact configuration. If a framework supports code generation or public constructors, you can reduce deep reflection requirements.

### 11.3. Reflection on JDK internals

Java 17 applies strong encapsulation to JDK internals. Applications should not access internal classes/packages like `sun.*` or `jdk.internal.*` via reflection.

Modern practices:

- Use public APIs supported by Java SE.
- Upgrade dependencies that access JDK internals.
- Replace obsolete libraries.
- Verify supported APIs and module/provider policies before deployment.

Do not use `--illegal-access=permit` as a general workaround on Java 17.

## 12. Tools for Inspecting Modules and Dependencies

### 12.1. jar --describe-module

```shell
jar --describe-module --file path/to/library.jar
```

Displays module name, module descriptor, exported packages, and declared dependencies. For JARs without a descriptor, the JDK can show the automatic module name.

### 12.2. java --show-module-resolution

```shell
java --show-module-resolution \
  --module-path mods:lib \
  -m com.acme.application/com.acme.application.Main
```

This option shows how the JVM resolves modules and dependencies at startup. It helps when modules are missing, module names are misspelled, or the module graph differs from expectations.

### 12.3. jdeps

`jdeps` analyzes dependencies at the class/package/module level:

```shell
jdeps --module-path lib --print-module-deps application.jar
jdeps --jdk-internals application.jar
```

`jdeps` does not replace runtime reflection tests. A library may reference class/field names via strings in reflection, so those dependencies do not always appear completely in static bytecode analysis.

### 12.4. Runtime Module inspection

```java
Module module = Customer.class.getModule();
Module target = ReflectionProbe.class.getModule();

System.out.println("Name: " + module.getName());
System.out.println("Named: " + module.isNamed());
System.out.println(module.isExported("com.acme.domain.api", target));
System.out.println(module.isOpen("com.acme.domain.api", target));
```

This checks module configuration at runtime; it does not replace testing the library's actual behavior.

## 13. Diagnostic Workflow When a Reflection Library Fails on Java 17

**Step 1 — Identify the root exception.** Look for `InaccessibleObjectException`, `IllegalAccessException`, `IllegalAccessError`, or a specific reflection error. Read the full module/package/member in the message.

**Step 2 — Identify the caller module.** The caller may be test code, a framework, a mapper, or a dependency. The package must be opened to the module performing deep reflection, not necessarily the application module.

**Step 3 — Inspect module descriptors.** Use `jar --describe-module` on dependencies and inspect the application's `module-info.java`.

**Step 4 — Distinguish public access from deep reflection.** If only public APIs are needed, check `exports`. If private fields/constructors are needed, check `opens`.

**Step 5 — Test minimal open access.** Use `--add-opens source/package=target` in a controlled test run. If the error disappears, you have isolated the relevant module boundary.

**Step 6 — Move the proper configuration into the module descriptor or launcher.** Prefer qualified `opens` in the package-owning module if the framework stably needs that access.

**Step 7 — Re-run integration tests without extra permissions.** Confirm other packages remain closed and public APIs are unaffected.

**Step 8 — Verify on the target runtime.** Test on JDK 17 with the module path configuration matching deployment.

## 14. Common Mistakes

| Mistake | Cause | Fix |
|---|---|---|
| Tests run on classpath and hide errors | Classpath does not reproduce named module boundaries | Run integration tests on the module path |
| `exports` is present yet private fields cannot be read | `exports` does not grant deep reflection | Add qualified `opens` if genuinely needed |
| Added `opens` yet code importing classes still fails to compile | `opens` does not replace `exports` | Export API packages needed at compile time |
| Package opened to application yet framework still fails | The actual caller is the framework's module | Open the package to the exact caller module |
| Using JAR filename as `opens` target | JAR filename is not necessarily the module name | Use `jar --describe-module` |
| Using `--add-exports` to access private fields | `exports` only exposes public APIs | Use `opens` with appropriate scope |
| Broad `--add-opens ...=ALL-UNNAMED` in production | Grants permission to all unnamed modules | Move dependency to named module or restrict permissions |
| Using `open module` to fix one package | Opens every package too broadly | Use qualified `opens` |
| Calling `setAccessible(true)` without handling exceptions | Module may deny access | Use `trySetAccessible` or handle exceptions |
| Calling `getDeclaredField` and assuming read permission | Metadata discovery differs from access checks | Check `canAccess`/`trySetAccessible` |
| Tests have `--add-opens`, production does not | Test and production module graphs differ | Align configurations or test both modes |
| Library requires access to JDK internals | Dependency relies on unsupported APIs | Upgrade/replace library and use public APIs |

## 15. Intentional Production and Test Configuration Example

Suppose an application uses module `com.acme.jsonmapper` to map models. Descriptor:

```java
module com.acme.domain {
    exports com.acme.domain.api;
    opens com.acme.domain.model to com.acme.jsonmapper;
}
```

Application module:

```java
module com.acme.application {
    requires com.acme.domain;
    requires com.acme.jsonmapper;
}
```

In a test environment, if test code directly inspects private fields of domain, the test module may need to be added to qualified `opens` in a **test-specific descriptor/configuration**, or tests can run with a separate `--add-opens`. Do not add test modules into the production descriptor by default if production has no such need.

A clear testing strategy:

| Test | Module configuration | Expectation |
|---|---|---|
| Public API contract | Only `exports` | Public constructors/accessors work |
| Private access blocked | Package not opened to test probe | `trySetAccessible()` returns false |
| Framework integration | Model package opened to mapper module | Mapper works in configured mode |
| Production launch | Same module graph and opens as production | Startup and mapping match production |
| Encapsulation regression | Internal packages left unopened | Out-of-scope reflection is blocked |

This tests both **functionality** and **strong encapsulation boundaries**.

## 16. Practice Exercises

### Exercise 1 — Create two modules

Create `com.acme.domain` and `com.acme.reflecttest` following the example. Compile with `javac --module-source-path` and run with `java --module-path -m`. Observe the difference between public accessors and private fields.

### Exercise 2 — Add qualified opens

Add:

```java
opens com.acme.domain.api to com.acme.reflecttest;
```

Recompile and re-run. Explain why `trySetAccessible()` changes from false to true and why `exports` must still remain.

### Exercise 3 — Use --add-opens

Keep the module descriptor without `opens` and run with:

```shell
java --module-path mods \
  --add-opens com.acme.domain/com.acme.domain.api=com.acme.reflecttest \
  -m com.acme.reflecttest/com.acme.reflecttest.ReflectionProbe
```

Compare the output with qualified `opens` in the descriptor. Identify pros and cons of runtime configuration.

### Exercise 4 — Try --add-exports

Remove `exports` from the domain descriptor and try accessing the public class from the test module. Then use `--add-exports` and observe the public API. Try reading the private field and explain why `exports` does not replace `opens`.

### Exercise 5 — Test a library on the classpath

Place the test probe or a reflection library on the classpath and run it with the domain module. Use `--add-opens ...=ALL-UNNAMED`, then move the library to the module path if supported. Compare caller modules and permission scope.

### Exercise 6 — Inspect dependency module names

Use `jar --describe-module` to find the module name of a dependency that uses reflection. Configure qualified `opens` to that exact module name. Do not guess from the artifact name.

### Exercise 7 — Write contract tests

Write three tests: public accessors always work; deep reflection is blocked when the package is unopened; deep reflection works when the package is opened to the right module. Then call a real library's API instead of only `Field.get`. Document the test module path and JVM arguments.

## 17. Self-Check Questions

1. Why is testing reflection on the classpath insufficient to verify an application runs cleanly on the module path?
2. How do `exports` and `opens` differ?
3. Can a package be exported yet still disallow reading private fields via reflection?
4. Does `getDeclaredField` succeeding mean `Field.get` will succeed?
5. Under what circumstances does `trySetAccessible()` return false?
6. Which exception can `setAccessible(true)` throw when a module has not opened a package?
7. Which module should be named as the target of qualified `opens`: the application or the library invoking reflection?
8. Why does opening a package to a test module not prove production frameworks are allowed access?
9. How do `--add-opens` and `--add-exports` differ?
10. When is `ALL-UNNAMED` used and why does it have a broad scope?
11. How does `open module` affect all packages?
12. How do you find the exact module name of a dependency?
13. Why are `MethodHandles` not a way to bypass JPMS?
14. How might a test framework require separate `opens` for test packages?
15. Why should tests run in a JVM/module graph matching production?

## 18. References

- [Java SE 17 API — Module](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): checking module names, exports, and opens at runtime.
- [Java SE 17 API — AccessibleObject](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html): `setAccessible`, `trySetAccessible`, `canAccess`, and module restrictions.
- [Java SE 17 API — InaccessibleObjectException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InaccessibleObjectException.html): error when deep access cannot be enabled.
- [Java Language Specification — Module Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7): syntax and rules for module declarations.
- [Java Platform Module System — JEP 261](https://openjdk.org/jeps/261): design of the module system, module path, exports, and opens.
- [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403): strong encapsulation of JDK internals in modern releases.
- [Java SE 17 Tools Reference — jar](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html): `jar --describe-module`.
- [Java SE 17 Tools Reference — java](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `--module-path`, `--add-opens`, `--add-exports`, and module launching.
- [Java SE 17 Tools Reference — jdeps](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html): dependency analysis and JDK internals.

When testing reflection libraries, run inside **named modules on the module path** mirroring the deployment environment. Use `exports` for public APIs, `opens` for deep reflection, and open packages only to the module actually performing reflection. Testing both permitted and denied cases confirms the library works properly while preserving Java 17's strong encapsulation boundaries.
