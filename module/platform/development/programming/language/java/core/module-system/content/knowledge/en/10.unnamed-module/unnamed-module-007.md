# Encapsulation limits of the classpath

In traditional Java, applications typically place classes and JARs on the **classpath**. When run this way, classes that do not belong to a named module are grouped into the **unnamed module** of the corresponding class loader. The unnamed module has very permissive access rules: it reads other modules, and its packages are considered exported and open to the module system.

This means the classpath lacks encapsulation boundaries at the module level. Java still applies access modifiers such as `private`, package-private, `protected`, and `public`, but there is no module descriptor to restrict which packages can be read by other modules or opened for reflection.

## 1. Classpath and the unnamed module

The classpath is the list of directories and JARs that Java uses to locate classes, resources, and certain other assets. For example:

    java -cp "app.jar;libs/*" com.example.app.Main

On Windows, the separator between classpath entries is typically a semicolon. On Linux and macOS, the separator is a colon.

When an application runs on the classpath, classes are loaded into the class loader's unnamed module. An unnamed module has no module name and no `module-info.java` file to declare:

- `requires`: modules that need to be read.
- `exports`: packages exposed to other modules.
- `opens`: packages opened for deep reflection.
- `uses` and `provides`: service consumption and provision relationships.

Each class loader has its own unnamed module. In a typical application, classes on the application classpath belong to the unnamed module of the application class loader. Because an unnamed module has no stable name, a module descriptor cannot write `requires` pointing to that unnamed module.

## 2. Why does the classpath have weak encapsulation boundaries?

In an unnamed module, packages are exported and open according to module system rules. Consequently, a named module can read packages of the unnamed module; at the same time, code on the classpath can read resolved named modules according to runtime rules.

With the classpath, there is no explicit export list such as:

    module com.example.billing {
        exports com.example.billing.api;
    }

All packages in an unnamed module are considered exported at the module level. This does not make every class `public`: Java language access rules still apply. A package-private class still cannot be arbitrarily imported and used from another package; a `private` field remains private when accessed directly in Java code.

The difference lies in **module boundaries**: the classpath has no module descriptor to restrict which packages another module can read, or which packages allow deep reflection.

## 3. Access modifiers still exist on the classpath

Encapsulation at the Java language level still works:

| Access modifier | Basic meaning |
|---|---|
| `private` | Accessible only within the enclosing class scope according to Java rules |
| package-private | Accessible within the same runtime package |
| `protected` | Accessible within the same package or through inheritance rules |
| `public` | Accessible from anywhere that can read and reference that type |

The classpath does not remove these rules. However, package-private can create a weaker boundary than many people expect: classes in the same runtime package and the same class loader can access each other's package-private members, even if they reside in different JARs.

For example, two JARs both contain classes in the package `com.example.internal`. If they are loaded by the application class loader into the same runtime package, those classes can interact via package-private members. A JAR boundary is not a package or module boundary.

A runtime package is identified by the package name and the class loader that defined the class. Therefore, two classes with the same package name defined by two different class loaders do not necessarily belong to the same runtime package.

## 4. Reflection on the classpath

Reflection allows a program to inspect class metadata and access members according to runtime rules. For classes belonging to an unnamed module, all packages are open for deep reflection. Therefore, a program on the classpath can typically enable deep access to private fields or methods of another class using `setAccessible(true)` or `trySetAccessible()`, provided it does not hit other Java runtime restrictions.

Example:

    package com.example.domain;

    public final class Account {
        private final String number = "ACC-001";
    }

Another class on the classpath can use reflection:

    package com.example.app;

    import com.example.domain.Account;
    import java.lang.reflect.Field;

    public class Main {
        public static void main(String[] args) throws Exception {
            Account account = new Account();

            Field number = Account.class.getDeclaredField("number");

            if (number.trySetAccessible()) {
                System.out.println(number.get(account));
            }
        }
    }

For classes belonging to an unnamed module, the package is already open at the module system level, so this deep reflection operation is typically permitted. That does not mean normal Java code is allowed to write `account.number`: direct access still violates `private`.

When a class moves into a named module, packages are not open to other modules by default. Frameworks relying on reflection may start encountering `InaccessibleObjectException`. At that point, you need to consider `opens` for the appropriate packages or `open module` if opening all packages is genuinely required.

## 5. Split packages on the classpath

Another limitation of the classpath is that multiple JARs can contribute classes to the same package. For example:

    legacy-a.jar
      com.example.shared.util.MoneyFormatter

    legacy-b.jar
      com.example.shared.util.DateFormatter

When both JARs are on the classpath, the classes can be loaded into the same unnamed module of the class loader. Thus, split packages could exist in legacy applications.

When converting the two JARs into two separate named modules on the module path, the package `com.example.shared.util` is split between two named modules. The module configuration may be rejected because a single package cannot have two named module owners in the same module configuration.

Another issue is that two JARs may contain the same binary class name, such as both having `com.example.shared.util.Helper`. With the standard application class loader, classpath order can determine which version of the class is found first. This easily causes unpredictable behavior when dependency order changes.

Therefore, the fact that an application runs on the classpath does not prove that its package structure is ready to move to the module path.

## 6. Comparing classpath and named modules

| Aspect | Classpath / unnamed module | Named module |
|---|---|---|
| Module descriptor | No `module-info.java` needed | Has a module name and descriptor |
| Dependency declaration | Relies on classpath and build tool | Declares `requires` |
| Package readability | Unnamed module reads other modules; its packages are broadly exported | Depends on readability relationships |
| Package exports | All packages of the unnamed module are exported at the module level | Only exported packages are exposed to other modules |
| Deep reflection | Packages of the unnamed module are open | Requires `opens` or `open module` for needed packages |
| Split packages | Can occur across JARs on the classpath | Cannot be split across named modules in the same configuration |
| Service declaration | Typically uses `META-INF/services` | Can use `uses` and `provides` in the descriptor |

Named modules allow authors to explicitly define public APIs, dependencies, and reflection permissions. The classpath is more flexible for assembling JARs, but does not provide the same level of module-level control.

## 7. What happens when mixing classpath and module path?

An application can run with both the classpath and module path simultaneously. Modules on the module path are resolved by the module system; classes on the classpath belong to the class loader's unnamed module.

The unnamed module reads all resolved named modules. However, a named module cannot declare `requires` to an unnamed module because an unnamed module has no name. If code in a named module needs a classpath library, that is usually a sign that the library should be moved to the module path, made into an appropriate automatic module, or addressed through architectural adjustments.

When classpath code accesses an unexported package of a named module, the operation is blocked by the module system. You can use the JVM option `--add-exports` to grant public type access for a specific package, or `--add-opens` if deep reflection is needed. These two options serve two different purposes.

Example:

    java --module-path mods
         --add-exports com.example.internal/com.example.internal.api=ALL-UNNAMED
         -cp app.jar com.example.app.Main

The option above allows the unnamed module to access public types in the specified package of module `com.example.internal`. It does not open private members for reflection; that case requires `--add-opens`.

## 8. An automatic module is not the same as an unnamed module

A JAR without `module-info.class`, when placed on the module path, can become an automatic module. It still has a module name (derived from the JAR filename or `Automatic-Module-Name`) and participates in module resolution.

An automatic module differs from an unnamed module:

- **Unnamed module:** classpath, has no module name, cannot be referenced by `requires`.
- **Automatic module:** JAR on the module path, has a module name, and can be requested by another module using `requires`.
- An automatic module reads other modules and broadly exports its packages, yet it is still a named module and is subject to the package uniqueness rules of the module configuration.

Automatic modules are often useful as a transitional step when modularizing legacy libraries, though they do not replace explicit module descriptor design in the long term.

## 9. How to reduce risk when migrating from classpath to JPMS

Before migrating a large application to named modules:

1. List all JARs and the packages each JAR contains.
2. Find split packages, especially `.internal`, `.common`, or `.util` packages contributed by multiple artifacts.
3. Identify which packages are public APIs and which are strictly internal.
4. Consolidate shared packages into a module with clear responsibility, or separate packages by business domain.
5. Add `module-info.java` with appropriate `requires`, `exports`, `opens`, `uses`, and `provides` directives.
6. Check automatic modules and unmodularized libraries.
7. Compile, resolve, and run the application on the module path; re-test frameworks that use reflection.

Do not add `module-info.java` en masse before checking package ownership. Doing so can turn dependencies that used to run on the classpath into an invalid module graph.

## 10. Common misconceptions

- **Thinking package uniqueness means the whole application can only have one package name.** The rule applies to named modules within the same module configuration; unnamed modules and class loaders have their own rules.
- **Thinking two modules without identically named classes cannot form a split package.** Simply declaring the same package, even with differently named classes, can still conflict.
- **Thinking a subpackage collides with a parent package.** `com.example.api` and `com.example.api.internal` are two separate packages.
- **Thinking exports creates package ownership.** A module owns a package based on module contents; exports only controls accessibility.
- **Thinking classpath and module path have the same encapsulation rules.** The classpath groups classes into an unnamed module; named modules have descriptors and stricter package ownership.
- **Thinking an automatic module is an unnamed module.** An automatic module has a name and is resolved as a named module.
- **Thinking adding `--add-exports` fixes a split package.** That option adjusts access permissions; it does not merge packages or change module ownership.

## Takeaways

The classpath groups JARs into an unnamed module, so multiple artifacts can contribute classes to the same package. When migrating to named modules, a package must have a clear owner in the module configuration; split packages across named modules will cause conflicts.

If multiple modules need to share a package, move that package into a shared module. If the classes belong to separate responsibilities, separate the packages by module. Auditing package ownership is an important step before migrating a legacy system from the classpath to the module path.