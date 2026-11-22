# `open module` and opening all packages

In the Java Platform Module System (JPMS), a module can restrict which packages other modules can access. However, some libraries need frameworks or tools to use reflection to read non-public members, such as private fields, constructors, or methods declared in a class. The `open module` directive allows opening all packages of a named module for deep reflection at runtime.

Two mechanisms must be distinguished: **exports** allows other modules to access the public types of a package under normal Java rules; **opens** allows reflection to bypass access checks at runtime. Opening a package is not the same as exporting a package.

## 1. Syntax of open module

A module can declare:

    open module com.example.domain {
        requires java.logging;
        exports com.example.domain.api;
    }

The `open` keyword precedes `module`. When a module is declared this way, **all packages of the module are opened for deep reflection to other modules**.

In the module descriptor:

- Directives such as `requires`, `exports`, `uses`, and `provides` can be declared as usual.
- Additional `opens` directives must not be declared, because all packages are already opened by `open module`.
- `exports` is still required if you want other modules to access the public types of a package in ordinary Java code.

`open module` only applies to named modules with an explicit module descriptor. It does not automatically turn packages into public APIs.

## 2. What is deep reflection?

Reflection allows a program to inspect classes, constructors, fields, and methods at runtime. For example, the reflection API can retrieve a field by name:

    Field field = type.getDeclaredField("password");

Under normal access rules, a module cannot arbitrarily use reflection to access private members located in a package of another module. JPMS protects this encapsulation boundary even when the application already has the class on the module path.

Deep reflection is the case where a program asks reflection to bypass certain normal Java access checks, typically using `setAccessible(true)` or `trySetAccessible()`. This is only allowed when the module owning the package has opened that package to the module performing reflection.

With an `open module`, every package is opened, so other modules can request deep access to members of classes in those packages. `trySetAccessible()` returns `true` when access can be enabled; if not permitted, it returns `false`. `setAccessible(true)` can throw `InaccessibleObjectException` when the module does not open the required package.

## 3. Example: opening all packages for reflection

Suppose there are two modules:

    src/
    ├── com.example.domain/
    │   ├── module-info.java
    │   └── com/example/domain/
    │       ├── api/SecretFactory.java
    │       └── internal/Secret.java
    └── com.example.app/
        ├── module-info.java
        └── com/example/app/Main.java

### Domain module

File `src/com.example.domain/module-info.java`:

    open module com.example.domain {
        exports com.example.domain.api;
    }

The module opens all packages for deep reflection. Specifically, the package `com.example.domain.api` is exported so the application can call the public API in ordinary Java code.

File `src/com.example.domain/com/example/domain/api/SecretFactory.java`:

    package com.example.domain.api;

    import com.example.domain.internal.Secret;

    public final class SecretFactory {
        private SecretFactory() {
        }

        public static Object create() {
            return new Secret();
        }
    }

File `src/com.example.domain/com/example/domain/internal/Secret.java`:

    package com.example.domain.internal;

    public final class Secret {
        private final String code = "MODULE-PRIVATE";
    }

The package `com.example.domain.internal` is not exported. The application cannot import the `Secret` class directly in source code, but it can receive the object through a public API returning `Object`.

### Application module

File `src/com.example.app/module-info.java`:

    module com.example.app {
        requires com.example.domain;
    }

File `src/com.example.app/com/example/app/Main.java`:

    package com.example.app;

    import com.example.domain.api.SecretFactory;
    import java.lang.reflect.Field;

    public class Main {
        public static void main(String[] args) throws Exception {
            Object secret = SecretFactory.create();

            Field code = secret.getClass().getDeclaredField("code");

            if (!code.trySetAccessible()) {
                throw new IllegalStateException(
                        "The package containing Secret is not open for reflection"
                );
            }

            System.out.println(code.get(secret));
        }
    }

Compile and run from the directory containing `src`:

    javac --module-source-path src -d out -m com.example.domain,com.example.app

    java --module-path out -m com.example.app/com.example.app.Main

Output:

    MODULE-PRIVATE

The application does not import the internal `Secret` class. It only receives the object via a public API, then uses reflection to look up the `code` field. Because `com.example.domain` is an open module, the package `com.example.domain.internal` is opened to the application; `trySetAccessible()` can enable access to the private field.

## 4. open module is not the same as exports

The two directives serve two different purposes:

| Aspect | `exports` | `opens` / `open module` |
|---|---|---|
| Purpose | Allows access to public types of a package | Allows deep reflection into a package |
| Primary timing | Access checks at compile time and linking | Reflection access checks at runtime |
| Private members | Does not open private access | Can allow reflection deep access |
| Automatically makes package importable? | Yes, if the consuming module reads the module and the package is exported appropriately | No |
| Scope | The specified package | The specified package or all packages of the open module |

Example:

    module com.example.domain {
        exports com.example.domain.api;
    }

This directive allows modules reading `com.example.domain` to use the public types in the API package. It does not allow external frameworks to freely access private fields in that package.

Conversely:

    module com.example.domain {
        opens com.example.domain.internal;
    }

The `opens` directive opens the internal package for deep reflection at runtime, but it does not allow the application to write `import com.example.domain.internal.Secret;` to use that class directly. To allow normal access, the package still needs to be exported.

## 5. Opening one package or opening the entire module

`open module` is not always necessary. JPMS provides the `opens` directive to select a narrower scope.

### Opening a package to all modules

    module com.example.domain {
        exports com.example.domain.api;
        opens com.example.domain.internal;
    }

Only the package `com.example.domain.internal` is opened for deep reflection. The remaining packages stay protected according to the module descriptor.

### Opening a package to a specific module

    module com.example.domain {
        exports com.example.domain.api;
        opens com.example.domain.internal to com.example.orm;
    }

This is **qualified opens**. Only the module `com.example.orm` is granted deep reflection permission into the package `com.example.domain.internal`. Other modules do not receive this permission.

### Opening all packages

    open module com.example.domain {
        exports com.example.domain.api;
    }

This is the broadest option: all packages of `com.example.domain` are open for deep reflection. You cannot narrow the scope by adding `opens` inside an open module.

## 6. When should open module be used?

`open module` can be appropriate when a module is designed to work with frameworks that rely heavily on reflection and the framework needs to access many packages, for example:

- Object-relational mapping (ORM) frameworks that need to read fields or constructors.
- JSON converters that need to access properties or constructors according to custom rules.
- Dependency injection frameworks that need to analyze classes and instantiate instances.
- Testing or serialization tools that need to inspect the internal structure of objects.

However, consider the access scope. If the framework only needs reflection on a few packages, `opens package.name to framework.module;` usually expresses the intent more clearly and preserves encapsulation boundaries for the remaining packages.

You should not use `open module` merely to fix a single reflection error when you can open the exact package and the exact consuming module.

## 7. Adding opens from the command line

In some application execution or testing scenarios, you may need to open a package without modifying `module-info.java`. The JVM supports the option:

    --add-opens source.module/package=target.module

Example:

    java --module-path out --add-opens com.example.domain/com.example.domain.internal=com.example.app -m com.example.app/com.example.app.Main

This option opens the specified package of the source module to the target module for that run. It is useful for environment configuration, testing, or temporary compatibility, but it does not replace module descriptor design decisions in distributed libraries.

Do not confuse `--add-opens` with `--add-exports`: the first grants deep reflection permission; the second adds access to public types of a package via the export mechanism.

## 8. Common misconceptions

1. **Thinking open module exports all packages.** All packages are opened for reflection, but `exports` is still needed to use public types in the usual way.
2. **Thinking opening a package means public API.** A package that is not exported still cannot be imported directly from another module.
3. **Thinking `opens` and `exports` are interchangeable.** The two directives protect and grant permissions under two different mechanisms.
4. **Adding `opens` inside an open module.** This is an invalid declaration because an open module already opens all packages.
5. **Thinking reflection is always allowed just because a class was found.** Finding a class and being allowed to deeply access its members are two separate steps; the module owning the package must open the appropriate package.
6. **Opening the entire module for a single framework.** If only one package needs reflection, qualified opens usually has a more appropriate scope.
7. **Thinking `open module` is a security mechanism that allows arbitrary access.** It intentionally relaxes encapsulation boundaries; the application must still obey Java's remaining reflection and access rules.

## Key takeaways

- `exports`: allows other modules to use the public types of a package in the usual way.
- `opens`: allows deep reflection into a package at runtime.
- `open module`: opens all packages of a named module for deep reflection.
- `opens package to module`: opens the exact package to the specified consuming module.

When encountering `InaccessibleObjectException`, identify the module owning the class, the package containing the member to be accessed, and the module performing reflection. Then choose an `opens` directive with sufficient scope or `open module` if opening all packages is genuinely required.