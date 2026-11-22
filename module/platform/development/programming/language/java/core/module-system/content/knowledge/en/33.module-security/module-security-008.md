# Do Not Grant `--add-opens` More Broadly Than Needed

The Java Platform Module System (JPMS) allows modules to expose APIs via `exports` and open packages for deep reflection via `opens`. When a framework needs to read private fields or invoke non-public methods, an application sometimes has to add package-opening permissions via a module declaration or the `--add-opens` runtime option.

Package-opening permissions directly impact encapsulation. If an entire module is opened or `ALL-UNNAMED` is used when only one specific framework needs access, the granted scope of access exceeds actual requirements.

The principle to apply is **least privilege**: open only the exact package, to the exact module that needs it, in the exact environment, and for as long as necessary. `--add-opens` should be an exception with a documented reason, an owner, and a removal plan.

## 1. What Problem Does `--add-opens` Solve?

In JPMS, an `exports` declaration exposes public types of a package to other modules. An `opens` declaration allows designated modules to perform deep reflection into a package, including non-public members when remaining access conditions are met.

For example:

~~~java
module com.example.account {
    exports com.example.account.api;

    opens com.example.account.model
        to com.example.orm;
}
~~~

Here:

- `com.example.account.api` is the regular API that other modules can use if they have readability.
- `com.example.account.model` is opened to module `com.example.orm` so the ORM can perform deep reflection.
- Other packages of `com.example.account` remain closed per module rules.
- Opening `model` does not turn that package into a public API for consumers to import and use arbitrarily.

If the source module's descriptor cannot be modified, opening permissions can be added at JVM startup:

~~~shell
java \
  --module-path mods \
  --add-opens com.example.account/com.example.account.model=com.example.orm \
  --module com.example.app/com.example.app.Main
~~~

General syntax:

~~~text
--add-opens <source-module>/<package>=<target-module>(,<target-module>)*
~~~

Where:

- `source-module` is the module owning the package to open.
- `package` is the fully qualified package name, case-sensitive.
- `target-module` is the module allowed to perform deep reflection into that package.
- Multiple target modules can be specified, separated by commas.

This option is applied at runtime. It does not alter `module-info.java` inside the JAR and does not replace compile-time dependency configurations.

## 2. Distinguishing `exports`, `opens`, and `--add-opens`

These three mechanisms have different scopes:

| Mechanism | Permission Granted | Use Case |
| --- | --- | --- |
| `exports package` | Access to public types and members per Java rules | Exposing APIs for consumers |
| `opens package` | Deep reflection into the package from permitted modules | Frameworks needing to map non-public fields, constructors, or methods |
| `--add-opens` | Adds `opens` permission at JVM startup | Compatibility for legacy libraries or environments where module descriptors cannot yet be edited |

Example of an exported package:

~~~java
module com.example.account {
    exports com.example.account.api;
}
~~~

Consumers can use the public API in this package if the consumer module reads `com.example.account`. Exporting does not automatically permit accessing private fields via reflection.

Example of a restricted opened package:

~~~java
module com.example.account {
    opens com.example.account.persistence
        to com.example.orm;
}
~~~

Module `com.example.orm` can perform deep reflection into the `persistence` package per JPMS rules. Other modules do not gain this open access simply because the package was opened to the ORM.

The `--add-exports` option is not equivalent to `--add-opens`. `--add-exports` supports accessing a package's public API; `--add-opens` is for deep reflection. If the error is `InaccessibleObjectException` when a framework accesses a private member, adding `--add-exports` typically does not solve the root cause.

## 3. Choosing the Right Package and Target Module Scope

Suppose the ORM only needs to access the `model` of the `account` module. There are three configuration options with different scopes:

~~~java
// Open the exact package to the exact framework module.
opens com.example.account.model to com.example.orm;
~~~

~~~shell
# Runtime equivalent, without modifying module-info.java.
--add-opens com.example.account/com.example.account.model=com.example.orm
~~~

~~~java
// Broader scope: opens all packages in the module.
open module com.example.account {
}
~~~

If only one package needs reflection, `open module` is overly broad. Every package in the module becomes open for deep reflection under JPMS rules, allowing other internal details to be observed by frameworks or code in permitted modules.

Similarly, do not open multiple packages just because of an initial error. Identify the package actually containing the class or member the framework needs to access, then grant permission to the exact calling module.

If the framework consists of multiple separate modules, determine which module actually performs the reflection. Do not assume the facade module or application module is the caller. You can use a framework class at the call site to check:

~~~java
Module frameworkModule = OrmRuntime.class.getModule();
Module domainModule = Account.class.getModule();

System.out.println(
    "Framework reads domain: "
        + frameworkModule.canRead(domainModule)
);

System.out.println(
    "Domain opens model to framework: "
        + domainModule.isOpen(
            "com.example.account.model",
            frameworkModule
        )
);
~~~

`canRead` checks the readability relationship from the framework module to the domain module. `isOpen` is called on the module owning the package and takes the framework module as an argument. Readability and `opens` are two separate conditions; having one does not automatically satisfy the other.

## 4. Be Careful with `ALL-UNNAMED`

Some legacy frameworks run on the classpath and belong to the unnamed module. In that case, the target can be `ALL-UNNAMED`:

~~~shell
java \
  --module-path mods \
  --class-path libs/legacy-orm.jar \
  --add-opens com.example.account/com.example.account.model=ALL-UNNAMED \
  --module com.example.app/com.example.app.Main
~~~

`ALL-UNNAMED` is a special selector representing all unnamed modules, including unnamed modules created in the future. It does not represent just a single JAR or a single class loader.

Therefore:

- If the framework is a named module, specify its exact module name.
- Only use `ALL-UNNAMED` when the caller truly belongs to an unnamed module.
- Inspect libraries on the classpath because they can all receive package-opening access together.
- Avoid using `ALL-UNNAMED` as a blanket fix for every reflection error.

The following example opens the entire `java.lang` package of the JDK to all unnamed modules:

~~~shell
--add-opens java.base/java.lang=ALL-UNNAMED
~~~

This scope is far broader than opening an application package to a specific framework. Use it only when there is a clearly identified compatibility requirement and its impact has been evaluated.

## 5. Identifying Which Package Actually Needs to Be Opened

Do not add `--add-opens` merely because a library reports a generic error. Extract the class, package, and module from the stack trace or error message.

A common error:

~~~text
java.lang.reflect.InaccessibleObjectException:
Unable to make field private ... accessible:
module com.example.account does not "opens
com.example.account.model" to module com.example.orm
~~~

This message provides three key pieces of information:

1. Source module: `com.example.account`.
2. Package needing to be opened: `com.example.account.model`.
3. Target module requesting permission: `com.example.orm`.

From that, you can configure the exact single package and single target:

~~~shell
--add-opens com.example.account/com.example.account.model=com.example.orm
~~~

If the message states the package is not opened to the unnamed module, verify whether the framework is running from the classpath before using `ALL-UNNAMED`.

For code you control, you can inspect module state without opening permissions:

~~~java
Module source = Account.class.getModule();
Module target = OrmRuntime.class.getModule();

boolean readable = target.canRead(source);
boolean open = source.isOpen(
    "com.example.account.model",
    target
);

System.out.println("Readable: " + readable);
System.out.println("Open: " + open);
~~~

This check only observes the current state. It does not modify the module graph and does not open the package.

## 6. Distinguishing Checking Access from Enabling Reflection Access

The Reflection API has several methods that are easy to confuse:

- `canAccess(target)` checks whether the current caller can access the member under current state.
- `trySetAccessible()` attempts to enable the override flag. If successful, the access state of the `AccessibleObject` changes.
- `setAccessible(true)` requests enabling the override flag and can throw `InaccessibleObjectException` if the module does not permit it.

Example checking a field:

~~~java
Field field = Account.class.getDeclaredField("secret");
Account account = new Account();

boolean accessibleNow = field.canAccess(account);
System.out.println("Accessible now: " + accessibleNow);
~~~

`canAccess` is suitable when you only want to observe current accessibility. If an integration test needs to confirm a framework can enable deep reflection, `trySetAccessible()` can be called in a controlled fixture:

~~~java
boolean enabled = field.trySetAccessible();

if (!enabled) {
    throw new IllegalStateException(
        "The package is not open to this module"
    );
}
~~~

Note that `trySetAccessible()` is not a pure check: when it returns `true`, it has already enabled access for that `Field` object. Use it only in tests or flows that genuinely need to access the member. Do not use `setAccessible(true)` as a default diagnostic step.

## 7. Prefer Configuring Module Descriptors for Long-Term Design

If you own the source module, consider declaring qualified `opens` instead of relying on runtime flags:

~~~java
module com.example.account {
    exports com.example.account.api;

    opens com.example.account.persistence
        to com.example.orm;
}
~~~

Advantages:

- Opening permissions are recorded alongside the module owning the package.
- Reviewers can see which packages are opened and to which modules.
- Configuration travels with the artifact, reducing dependence on startup scripts.
- Permission scope can be governed as part of module design.

Qualified `opens` also clarifies integration relationships: the `account` module intentionally allows the ORM module deep access to the persistence model.

However, not every internal package should be opened. Only open packages with a real need, such as packages containing entities or DTOs that a framework must map.

If a framework does not require deep reflection, use constructors, accessors, public APIs, or an explicitly designed mapping mechanism. This reduces coupling to internal field structures and keeps implementations easier to change.

## 8. Using `--add-opens` as a Time-Bound Compatibility Solution

In legacy applications, it may not be possible to modify module descriptors or upgrade frameworks immediately. In such cases, `--add-opens` is a runtime compatibility workaround.

Manage it through the following steps:

1. Record the original error and the package needing to be opened.
2. Identify the exact module invoking reflection.
3. Add a single source module/package and target module pair.
4. Run integration tests to confirm the framework works.
5. Document the reason and which dependency requires opening permission.
6. Create a task to upgrade the framework or switch to an API that does not require deep reflection.
7. Remove the flag once the dependency is fixed or the module descriptor declares appropriate `opens`.

Do not place permission-broadening flags in shared environment variables used across all applications if only one service needs them. Put them in the startup configuration of that exact process and environment.

Example documented configuration:

~~~shell
# Temporary compatibility for legacy ORM.
# Remove after upgrading ORM to a version that does not
# require deep reflection into the persistence package.
--add-opens com.example.account/com.example.account.persistence=com.example.orm
~~~

Runtime flags should be reviewed like an access permission change. Once no longer needed, delete them instead of leaving them indefinitely.

## 9. Notes on JDK Internals

Since JDK 17, JEP 403 has enforced strong encapsulation for JDK internal APIs. Some older frameworks may attempt to access JDK internal packages via reflection and encounter access errors.

Example of a flag opening a specific package:

~~~shell
--add-opens java.base/java.lang=com.example.legacy
~~~

This grants permission to open package `java.lang` in module `java.base` to module `com.example.legacy`. It is not a license to arbitrarily access all JDK internal APIs.

Do not open all JDK packages or grant `ALL-UNNAMED` just to silence error messages. Prioritize:

- Upgrading frameworks to versions supporting the target JDK.
- Using public JDK APIs.
- Removing dependencies on JDK internal implementations.
- If unable to upgrade immediately, open only the exact package to the exact module and record a removal deadline.

The `--illegal-access` option was used during the JPMS transition period, but it is no longer a way to restore access on JDK 17 and above. Do not rely on it to handle current encapsulation errors.

## 10. Checking Configuration Before Release

Before deploying an application with `--add-opens`, check:

1. Is the opened package the exact package from the error message?
2. Is the source module the exact module owning the class?
3. Is the target module the exact module performing reflection?
4. Can qualified `opens` in `module-info.java` be used instead of a runtime flag?
5. Can reflection be replaced with public APIs, constructors, or accessors?
6. If `ALL-UNNAMED` is used, is opening to all unnamed modules genuinely necessary?
7. Is the flag applied outside the intended process or environment?
8. Are there tests confirming the feature works with the minimal permission scope?
9. Is the dependency and flag removal plan documented?

You can check actual JVM arguments at runtime by inspecting launch script configurations, container entrypoints, or runtime arguments in diagnostic tools. Do not inspect only config files in the repository if the deployment environment can inject JVM arguments from elsewhere.

## 11. Common Misconceptions

1. **`exports` is sufficient for private reflection:** `exports` only exposes APIs per Java rules; deep reflection requires appropriate `opens`.
2. **Opening a package to one module allows all modules to access it:** qualified `opens` grants permission only to the specified target modules.
3. **`ALL-UNNAMED` is just a single library:** it includes all unnamed modules, including modules created later.
4. **`open module` is a convenient fix for a small error:** it opens every package in the module and typically exceeds what is needed.
5. **`trySetAccessible` only checks:** when it succeeds, it has already enabled the override flag on the reflection object.
6. **`--add-opens` fixes every runtime error:** it does not fix `NoSuchMethodError`, missing classes, or dependency version mismatches.
7. **On seeing `InaccessibleObjectException`, open all of `java.base`:** identify the exact package and caller first.
8. **Compatibility flags can stay forever:** runtime open permissions must be tracked and removed once dependencies no longer require them.

## Conclusion

`--add-opens` is a tool for granting deep reflection permissions across module boundaries, yet each use reduces encapsulation for the opened package. Identify the exact source module, package, and target module; prefer qualified `opens`; restrict `ALL-UNNAMED` and `open module`; document why runtime flags are used and remove them when no longer needed. Least-privilege configuration lets frameworks function while keeping most internal implementations sealed.