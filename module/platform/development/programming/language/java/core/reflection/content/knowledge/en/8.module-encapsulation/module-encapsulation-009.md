# Limitations of `--illegal-access` in Modern Java

## 1. The Problem That `--illegal-access` Used to Solve

Before Java 9, many libraries used Reflection to open internal JDK fields, methods, and constructors—such as calling `setAccessible(true)` on non-public members in packages belonging to `java.base`. That approach relied on implementation details and broke easily on JDK upgrades. Starting in Java 9, the **Java Platform Module System (JPMS)** introduced *strong encapsulation* rules: each module decides which packages are `exports`-ed (public access) and which packages are `opens`-ed (allowing deep reflection).

`--illegal-access` was a JVM launch option introduced to assist migrating legacy applications that used **illegal reflective access to JDK packages that existed in Java 8**. It was never a switch disabling all Java access rules, did not grant arbitrary access across all application/modular libraries, and did not legitimize code using internal APIs.

**Essential takeaway for modern Java: since JDK 17, `--illegal-access=permit`, `warn`, `debug`, and `deny` all no longer grant access.** In current JDKs that still accept this syntax, the JVM merely warns that the option is obsolete/ignored. You cannot use `--illegal-access=permit` to fix `InaccessibleObjectException` on JDK 17+.

## 2. Timeline: Java 8 → 9–15 → 16 → 17+

| Version | JDK Encapsulation and `--illegal-access` Status | Practical Consequence |
| --- | --- | --- |
| Java 8 and earlier | Neither JPMS nor `--illegal-access` existed. | Reflection still underwent Java access checks and other limits; some libraries accessed internal JDK details. |
| JDK 9–15 | JPMS was introduced; default mode was equivalent to `--illegal-access=permit` for many JDK packages existing since Java 8. | Permitted some legacy Reflection accesses during the transition period; the first illegal access triggered a warning in permit mode. |
| JDK 16 | JEP 396 changed the default to `--illegal-access=deny`, enabling strong encapsulation by default. | `--illegal-access=permit` could still temporarily restore prior compatibility access within the option's supported scope. |
| JDK 17 and later | JEP 403 made `--illegal-access` an **obsolete/ignored** option. | `permit`/`warn`/`debug`/`deny` values neither loosen nor tighten permissions; deep reflection requires explicitly opening the appropriate package via JPMS mechanisms. |

During JDK 9–16, the historical modes were:

- `permit`: relaxed Reflection permissions within the legacy compatibility scope; warned once on first occurrence.
- `warn`: similar in allowing access, yet warned on every illegal access.
- `debug`: like `warn`, plus stack traces to locate the caller.
- `deny`: did not relax permissions; access could still be permitted by other explicit configurations such as `--add-opens`.

Those flags **did not apply universally to every developer-created module**. In particular, on JDK 17+, writing `--illegal-access=deny` is also not a way to lock down existing open permissions: the JVM ignores this option, and specific `--add-opens` flags still govern added access permissions.

## 3. Why Does `setAccessible(true)` No Longer Bypass Every Barrier?

Reflection can find a member without necessarily having permission to read or invoke that member. Distinguish:

1. `getDeclaredMethod()`, `getDeclaredField()`, `getDeclaredConstructor()`: **retrieves metadata** about members declared in a type, including private ones. Retrieving metadata does not grant permission to use them.
2. `setAccessible(true)`: requests bypassing part of normal access checks for the member, **succeeding only when JPMS permits it**. If the named module's package is not opened to the calling module and no other condition holds, it can throw `java.lang.reflect.InaccessibleObjectException`.
3. `trySetAccessible()`: convenient variant returning `false` when access cannot be enabled, instead of `InaccessibleObjectException` in permission-denied cases; related exceptions must still be handled if applicable.
4. `Method.invoke()`, `Field.get()`, or constructor invocation: actually uses the member. If not yet permitted, these APIs can throw `IllegalAccessException` (different from the exception when requesting to enable access).

Even a public class in an **`exports`-ed** package does not automatically open private members to another application. `exports` and `opens` have different effects:

| Configuration | Accessing Public Types/Members via Normal Java | Deep Reflection into Private Members from Another Module |
| --- | --- | --- |
| Package `exports`-ed to calling module | Permitted, if other Java access conditions also hold. | Not automatically permitted. |
| Package `opens`-ed to calling module | Does not automatically let other code compile references to public types when the package is not `exports`-ed. | Permitted to request `setAccessible(true)` under appropriate JPMS conditions. |
| Both `exports` and `opens` | Permits both normal public access and deep reflection within the granted scope. | Can work. |
| Package neither exported nor opened to caller | No normal access from caller. | Deep reflection is rejected. |

## 4. Java 17+ Example: Real Error and Properly Opening One Package

The example below uses a **custom module**, avoiding reliance on internal fields of `String` or JDK internal classes that may change. Module `demo.lib` lets external classes see `Greeter` via `exports demo.api`, yet does not yet permit deep reflection access to `private secret()`.

Create the directory layout:

~~~text
project/
├── src/
│   └── demo.lib/
│       ├── module-info.java
│       └── demo/
│           └── api/
│               └── Greeter.java
└── Main.java
~~~

**File `src/demo.lib/module-info.java`:**

~~~java
module demo.lib {
    exports demo.api;
}
~~~

**File `src/demo.lib/demo/api/Greeter.java`:**

~~~java
package demo.api;

public class Greeter {
    private String secret() {
        return "hello";
    }
}
~~~

**File `Main.java`:** the program sits on the class path, belonging to the *unnamed module*.

~~~java
import demo.api.Greeter;
import java.lang.reflect.InaccessibleObjectException;
import java.lang.reflect.Method;

public class Main {
    public static void main(String[] args) throws Exception {
        Method method = Greeter.class.getDeclaredMethod("secret");

        try {
            method.setAccessible(true);
            System.out.println("result=" + method.invoke(new Greeter()));
        } catch (InaccessibleObjectException e) {
            System.out.println("blocked=" + e.getClass().getSimpleName());
        }
    }
}
~~~

From the `project` directory, compile with JDK 17+:

~~~bash
javac --release 17 -d mods --module-source-path src -m demo.lib
javac --release 17 --module-path mods --add-modules demo.lib -d classes Main.java
~~~

### Run 1: Without Opening the Package

~~~bash
java --module-path mods --add-modules demo.lib -cp classes Main
~~~

Stdout:

~~~text
blocked=InaccessibleObjectException
~~~

`getDeclaredMethod("secret")` found the method, yet `setAccessible(true)` lacked permission to open the private member. Hence `hello` is not printed.

### Run 2: Adding `--illegal-access=permit`

~~~bash
java --illegal-access=permit --module-path mods --add-modules demo.lib -cp classes Main
~~~

Stdout remains:

~~~text
blocked=InaccessibleObjectException
~~~

On OpenJDK 24, the JVM also emits a warning to stderr, such as:

~~~text
OpenJDK 64-Bit Server VM warning: Ignoring option --illegal-access=permit; support was removed in 17.0
~~~

The exact warning text, format, and whether future JVMs still accept the legacy syntax depend on the version. **The learning point is that the access outcome does not change.** At the same time, historical `--illegal-access` was never a mechanism to arbitrarily open application modules such as `demo.lib`.

### Run 3: Granting Permission to the Right Package and Right Caller

~~~bash
java --add-opens demo.lib/demo.api=ALL-UNNAMED --module-path mods --add-modules demo.lib -cp classes Main
~~~

Stdout:

~~~text
result=hello
~~~

`--add-opens demo.lib/demo.api=ALL-UNNAMED` opens package `demo.api` of module `demo.lib` to unnamed modules (typically code on the class path). Then `setAccessible(true)` succeeds.

**Conclusion from the example:** for deep reflection needs, permissions are added per **module/package/caller**, not via a global `--illegal-access` flag. All three commands and results above were verified with Java 17-compatible code.

## 5. Purpose-Built Replacement Configurations

### `--add-opens`: Permitting Deep Reflection

Runtime syntax:

~~~text
--add-opens <source-module>/<package>=<target-module>
~~~

Example for class path code accessing private members in `java.lang`:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -cp classes Main
~~~

This line only illustrates the **syntax for opening a JDK package**, not the command for running module `demo.lib` in section 4. Section 4's example needs `--add-opens demo.lib/demo.api=ALL-UNNAMED`. There is no justification for opening every package of `java.base` simply because a library threw an error on one specific package.

If the caller is a **named module**, replace `ALL-UNNAMED` with the calling module's name, e.g.:

~~~text
--add-opens demo.lib/demo.api=app.consumer
~~~

`--add-opens` is usually a temporary compatibility measure for legacy libraries; choose the package genuinely needing opening based on the error message and the library's documentation. This permission lets the caller bypass normal access checks for members in that package.

### `--add-exports`: Allowing Use of Public APIs in an Unexported Package

Syntax:

~~~text
--add-exports <source-module>/<package>=<target-module>
~~~

Use when a library/application needs **public types and public members** of an unexported package. The flag may be needed at both compile time and runtime. `--add-exports` is not equivalent to allowing deep reflection into private members; that case typically requires `--add-opens`.

### Official Declaration in `module-info.java`

If you **own** the library module and deliberately decide its API, you can declare:

~~~java
module demo.lib {
    exports demo.api;              // Allow external code to use the public API
    opens demo.api to app.consumer; // Allow deep reflection only for named module app.consumer
}
~~~

This is a configuration example for a situation **where module `app.consumer` exists**; do not paste it directly into section 4's class path project without that module. You can declare `opens demo.api;` to open the package to every module, yet prefer a narrow scope fitting your architecture. `open module ...` opens all packages of the module for reflection, which is usually broader than needed.

In applications using frameworks, it is best to configure `opens` (or `opens ... to ...`) in a module you control, following the framework's documentation. If the issue lies in **JDK** internals, developers cannot edit `java.base/module-info.java` to add `opens`; you must use public APIs, update the library, or supply a narrow runtime flag.

### `--add-reads` Does Not Replace `--add-opens`

`--add-reads` changes **readability** relationships between modules; it does not open private members of a package. When debugging `InaccessibleObjectException`, adding `--add-reads` does not resolve missing deep reflection permission.

## 6. Diagnosing Errors When Upgrading from Java 8/11 to Java 17+

Typical message:

~~~text
java.lang.reflect.InaccessibleObjectException:
Unable to make ... accessible: module java.base
does not "opens java.lang" to unnamed module ...
~~~

Exact wording can vary across JDKs and members. The items to identify are:

1. **Source module:** e.g., `java.base`.
2. **Closed package:** e.g., `java.lang`.
3. **Caller needing permission:** e.g., `unnamed module` for the class path, or the name of a named module.
4. **Access operation:** deep reflection into non-public members, or normal reference to a public API in an unexported package?

If deep reflection is truly necessary and migrating to an officially supported API is not yet possible, a narrowly scoped test option is:

~~~text
--add-opens java.base/java.lang=ALL-UNNAMED
~~~

This is an **example inferred from the hypothetical message above**, not advice to add that flag to every project.

Sound troubleshooting workflow:

- **Identify the library invoking Reflection:** inspect the stack trace and relevant dependencies. A serialization, dependency injection, ORM, bytecode proxy, mocking, or testing library itself may be accessing JDK internals.
- **Prioritize updating dependencies:** newer releases often already use supported Java APIs or JPMS-compliant mechanisms. Avoid maintaining a long list of `--add-opens` when an API-level fix exists.
- **If you authored the module:** update `module-info.java` with the exact required `exports` or `opens` scope.
- **If forced to open a package at runtime:** add only each `--add-opens` proven necessary, placing it in the JVM config running the program and real test environment. Configuration for one `java` process does not automatically apply to another JVM process spawned by a build tool.
- **Retest on the exact target deployment JDK version:** additional errors may surface when code reaches other packages. Never conclude from a single stack trace that one flag suffices for all environments.

Quick way to check the running Java runtime:

~~~bash
java -version
~~~

If test/IDE/production commands use a different JDK from your terminal, verify the JVM **actually launching the application**. Do not rely on `javac -version` in one terminal to assume the whole system uses the same runtime.

## 7. Important Misconceptions

| Wrong Assumption | Correction |
| --- | --- |
| "Adding `--illegal-access=permit` is enough when upgrading to JDK 17+." | The flag is obsolete and ignored starting in JDK 17. |
| "`--illegal-access=deny` is still blocking permissions on modern JDKs." | Permission state on JDK 17+ is not governed by this flag; other specific options still take effect. |
| "`setAccessible(true)` always bypasses private regardless of modules." | JPMS can reject it with `InaccessibleObjectException`. |
| "`getDeclaredField()` finding a field means it can be read." | Visibility of metadata differs from permission to access values. |
| "`--add-exports` and `--add-opens` are the same." | `exports` governs public API access; `opens` supports deep reflection. |
| "`ALL-UNNAMED` grants permission to a single named module." | `ALL-UNNAMED` targets code in unnamed modules, typically on the class path. |
| "Opening all JDK internals is a sustainable fix." | Use official APIs, compatible libraries, and open only specific packages when needed. |
| "Every `IllegalAccessException` is caused by `--illegal-access`." | It can involve Java visibility, module readability, package export/open, caller, or call path; read the exception and stack trace. |

**Historical exception to understand accurately:** JEP 403 still allowed certain key internal APIs such as `sun.misc.Unsafe` to remain under special mechanisms. That does not mean all JDK internals are open, nor does it turn non-standard APIs into stable contracts.

## 8. Self-Check

1. On JDK 17+, run the three commands in section 4. Explain why `Greeter.class.getDeclaredMethod("secret")` succeeds while `method.setAccessible(true)` is rejected before opening the package.
2. Replace `setAccessible(true)` with `System.out.println(method.trySetAccessible());`. Predict `false` when permission is missing and `true` when `--add-opens` is present; remember to remove or guard the `invoke` line if you only want to test opening capability.
3. Why does `exports demo.api` not allow accessing a private method? If the caller becomes named module `app.consumer`, what should replace `ALL-UNNAMED`?
4. If a library only needs public types of an unexported package, should you evaluate `--add-exports` or `--add-opens` first? Which should you choose if deep reflection into private fields is required?
5. On JDK 17+, if a legacy application runs with `--illegal-access=warn`, do the old warnings still act as a per-access detection tool? Why?

## Official Documentation

- [JEP 261 — Module System](https://openjdk.org/jeps/261)
- [JEP 396 — Strongly Encapsulate JDK Internals by Default (JDK 16)](https://openjdk.org/jeps/396)
- [JEP 403 — Strongly Encapsulate JDK Internals (JDK 17)](https://openjdk.org/jeps/403)
- [Oracle JDK 24 Migration Guide — Strong Encapsulation in the JDK](https://docs.oracle.com/en/java/javase/24/migrate/migrating-jdk-8-later-jdk-releases.html)
- [Oracle Java Launcher Reference — `--add-opens`, `--add-exports`, obsolete options](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html)
- [Java SE 17 API — `AccessibleObject`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
