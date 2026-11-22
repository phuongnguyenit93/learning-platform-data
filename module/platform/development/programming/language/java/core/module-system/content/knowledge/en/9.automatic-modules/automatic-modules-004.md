# Automatic Modules Export All Packages

In the Java Platform Module System (JPMS), a legacy JAR library may not yet have a **module-info.class** file yet still be placed on the module path. Java then treats this JAR as an **automatic module**. The module has a name and can be declared by another named module using **requires**, while all of its packages are exported.

Exporting all packages helps legacy libraries join the module graph without immediately modifying source code or repackaging. However, it also reduces the ability to control API boundaries: packages containing internal implementation can still be accessed by other modules if they contain public types. This is an important characteristic to understand before using automatic modules long-term.

## 1. When Is an Automatic Module Formed?

An automatic module is a JAR without a module descriptor that is placed on the **module path**. Java creates a named module from the JAR so that named modules can depend on it.

Example legacy library:

~~~text
libs/
└── legacy-utils-2.4.jar
~~~

This JAR does not yet have **module-info.class**. When placed on the module path, Java can recognize it as an automatic module. If the JAR has a manifest declaring **Automatic-Module-Name**, that value is used as the module name. Otherwise, Java derives the name from the JAR file name according to module naming rules.

Example manifest:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: com.example.legacy
~~~

A stable module name keeps applications from depending on how the filename is derived. When the file name or artifact version changes, the name derived from the filename may change. The **Automatic-Module-Name** attribute helps prevent the module name from changing simply because the JAR was renamed.

## 2. What Does Exporting All Packages Mean?

A regular named module must explicitly declare each package it wants to make public:

~~~java
module com.example.library {
    exports com.example.library.api;
}
~~~

In this case, the API package is exported; other unexported packages remain internal to outside modules.

An automatic module has no **module-info.java** to list **exports** directives. Instead, Java treats all packages of the automatic module as exported. Named modules that have a readability relationship to the automatic module can access public types in those packages according to Java rules.

Suppose the JAR contains:

~~~text
legacy-utils.jar
├── com/example/legacy/api/LegacyClient.class
├── com/example/legacy/model/LegacyRequest.class
└── com/example/legacy/internal/SocketPool.class
~~~

All three packages are exported by the automatic module. Therefore, the application module can access public types in the **api**, **model**, and even **internal** packages, provided other Java access conditions are met.

The package name **internal** is merely a naming convention. It does not by itself create a protective boundary in JPMS. When the JAR is an automatic module, that package is still included in the set of exported packages.

This differs from a named module with an explicit descriptor, where the author can export only API packages and keep implementation packages unexported.

## 3. How Does a Named Module Use an Automatic Module?

A named module can declare a dependency on an automatic module using the module name published by the JAR.

Example:

~~~java
module com.example.app {
    requires com.example.legacy;
}
~~~

Application code can import public types in the library's packages:

~~~java
package com.example.app;

import com.example.legacy.api.LegacyClient;
import com.example.legacy.internal.SocketPool;

public class Main {
    public static void main(String[] args) {
        LegacyClient client = new LegacyClient();
        System.out.println(client.getClass().getName());
    }
}
~~~

The example importing **SocketPool** illustrates the consequence of exporting all packages: a package named internal is not protected from consuming modules solely by its package name. In real applications, avoid depending on internal classes even when the compiler permits access.

Placing a JAR on the module path and declaring **requires** are two separate steps:

- The module path helps Java locate the automatic module.
- **requires** establishes a readability relationship from the consuming named module to the automatic module.
- The automatic module's export of all packages allows the consuming module to access public types in those packages.

If you only add the JAR to the module path without the application module declaring the required dependency, the source may still fail to compile due to the missing readability relationship.

## 4. Automatic Modules Export All Packages Without Restriction

The biggest consequence is that automatic modules offer no way to selectively export packages.

Suppose a library has the structure:

~~~text
com.vendor.payment
├── api
├── model
├── internal
├── adapter
└── debug
~~~

If the JAR is used as an automatic module, all of the packages above are exported. Consuming modules can depend on public classes in **internal**, **adapter**, or **debug**, even if the library author never intended them to be stable API.

This creates several risks:

**Depending on implementation details**

Applications may directly import internal classes instead of calling public interfaces or abstractions. When the library changes its implementation, the application can break even though the intended API remains compatible.

**Hard to change package structure**

An internal package already used by another module becomes part of the actual dependency surface. Renaming, moving, or deleting classes in that package can cause compile-time or runtime errors.

**Broad API surface**

Public types across many packages become accessible across the module boundary. Inspecting the module descriptor does not help identify which packages are official API, because an automatic module has no author-declared exports list.

**Hard to control integration**

Frameworks or consuming modules can directly access many internal details. This increases coupling and makes library upgrades harder to predict.

Automatic modules are therefore suitable as a bridge for integrating legacy libraries, but they do not provide the selective encapsulation of a well-designed named module.

## 5. Checking Packages and Name of an Automatic Module

You can use the **jar --describe-module** command to see how Java recognizes a JAR:

~~~bash
jar --describe-module --file libs/legacy-utils-2.4.jar
~~~

For a JAR without a module descriptor, the output indicates the automatic module name and its automatic status. If the manifest has **Automatic-Module-Name**, that stable name is used; otherwise, the name is derived from the filename.

You can inspect the manifest using:

~~~bash
jar --describe-module --file libs/legacy-utils-2.4.jar
~~~

If you need to view the manifest contents, you can list or extract the **META-INF/MANIFEST.MF** file in the JAR. Always verify the actual module name before writing **requires**.

One note: **Automatic-Module-Name** only stabilizes the module name. It does not create a full module descriptor, does not restrict the list of exported packages, and does not turn internal packages into encapsulated packages.

## 6. Example: Compiling and Running with an Automatic Module

Suppose the legacy library is in **libs/legacy-utils.jar** and publishes the module name **com.example.legacy**. Application sources:

~~~text
src/
└── com.example.app/
    ├── module-info.java
    └── com/example/app/Main.java
~~~

Application module descriptor:

~~~java
module com.example.app {
    requires com.example.legacy;
}
~~~

Code using the library:

~~~java
package com.example.app;

import com.example.legacy.api.LegacyClient;

public class Main {
    public static void main(String[] args) {
        LegacyClient client = new LegacyClient();
        client.execute();
    }
}
~~~

Compile:

~~~bash
javac --module-path libs \
      --module-source-path src \
      -d out \
      -m com.example.app
~~~

Run:

~~~bash
java --module-path "out:libs" \
     --module com.example.app/com.example.app.Main
~~~

Here, the **libs** directory holds the legacy JAR and Java recognizes it as an automatic module. The application module declares **requires com.example.legacy** to use public types in the library's exported packages.

On Windows, the separator between module path entries is a semicolon (**;**); on Linux and macOS, it is a colon (**:**).

## 7. Automatic Modules vs. Regular Modules

Comparing an automatic module with a named module that has a descriptor:

| Characteristic | Automatic Module | Named Module with module-info.java |
|---|---|---|
| Has a module name | Yes | Yes |
| Has an author-declared module descriptor | No | Yes |
| Can be used in requires | Yes | Yes |
| Exported packages | All packages | According to exports directives |
| Can target specific modules for exports | No via automatic module descriptor | Can use qualified exports |
| Dependencies explicitly declared in descriptor | No | Yes |
| API control level | Broad, convenient for transition | Intentional and selective |

An automatic module also has the ability to read other modules in the module configuration. This is convenient for legacy libraries, but makes its dependency graph less explicit than a module designed with specific **requires** directives.

Do not confuse an automatic module exporting all packages with all classes or members becoming accessible. Java's access rules still apply: types or members must satisfy the corresponding modifiers and access conditions. Exporting a package permits access to public types across the module boundary; it does not turn private into public.

## 8. When Should You Keep an Automatic Module?

Automatic modules are useful in several cases:

- A third-party library does not yet provide a module descriptor, but the application needs to place it on the module path.
- The application is migrating incrementally from the classpath to JPMS and cannot modularize every dependency yet.
- The library is repackaged with a stable module name via **Automatic-Module-Name**.
- Compatibility needs to be preserved during the transition period before the library author or application team adds a module descriptor.

When using one, inspect the packages provided by the library and avoid importing implementation packages directly. Just because code can access a class does not mean the author commits to that class as a stable API.

## 9. When Should You Create an Explicit Module Descriptor?

If you own the library or can contribute changes to it, consider creating **module-info.java** to control which packages are exported.

Example:

~~~java
module com.example.legacy {
    exports com.example.legacy.api;
}
~~~

When this module descriptor is packaged into the JAR, the module becomes a regular named module. Only the **com.example.legacy.api** package is exported; packages such as **internal**, **adapter**, or **debug** are not exposed across the module boundary.

Benefits:

- Clearly defines the API contract.
- Keeps implementation packages inside the module.
- Reduces the chance of consuming modules depending on internal classes.
- Declares dependencies via **requires** instead of relying on the broad readability of an automatic module.
- Allows using **qualified exports** to expose packages only to specific target modules.

If you cannot modify a third-party JAR, look for a library version that already supports JPMS or a compatible packaging published by the vendor. Do not fabricate a descriptor that does not match the library's actual package structure and dependencies.

## 10. Common Errors

**Module not found even though the JAR exists**

Check whether the JAR is actually on the module path or only on the classpath. Then check the module name with **jar --describe-module** and compare it with **requires**.

**Cannot import a package from the JAR**

If the JAR is an automatic module on the module path, its packages are exported. If it is still inaccessible, check the **requires** relationship, module name, whether the class is public, and whether the JAR is actually an automatic module.

**Application depends on the library's internal package**

Automatic modules allow access to public types in every package. Switch to the official API if possible; if you own the library, create an explicit descriptor to export only API packages.

**Renaming the JAR breaks requires**

Names derived from filenames can change. Use a stable **Automatic-Module-Name** manifest attribute or an explicit module descriptor, and update dependencies to match the actual module name.

**Multiple versions of a library declare the same module name**

Remove redundant versions and keep a single consistent module source. Do not leave multiple JARs with the same module name on the module path because resolution will no longer be unambiguous.

**Confusing automatic modules with the unnamed module**

A JAR on the module path without a descriptor can become a named automatic module. A JAR on the classpath belongs to the unnamed module. The two have different dependency behaviors and ways of being referenced.

## 11. Key Takeaways

- An automatic module is formed when a JAR without **module-info.class** is placed on the module path.
- An automatic module has a name and can be referenced by other named modules via **requires**.
- All packages of an automatic module are exported, including packages containing implementation.
- Exporting packages does not make all members public; Java's access rules still apply.
- **Automatic-Module-Name** stabilizes the module name but does not restrict exported packages.
- Automatic modules are suited for step-by-step migration; explicit module descriptors are suited when API and dependency control is needed.
- Use **jar --describe-module** to verify the module name and type before configuring **requires**.

When integrating a legacy library, treat automatic modules as a quick way to bring the library into the module graph. When you need to protect implementation packages and maintain a long-term API contract, migrate the library to a named module with a descriptor and export only the packages that truly need to be public.