# definePackage, getDefinedPackage, and getDefinedPackages in Java ClassLoader

## 1. What do these three APIs solve?

When Java loads classes, a name such as **com.example.plugin.Widget** has two easily noticeable parts:

- **com.example.plugin** is the package name of the class.
- **Widget** is the class name inside that package.

However, a package at runtime **is not merely the prefix of the class name**. The JVM and Java API also associate the package with the **class loader that defined the class**, version information, vendor, package annotations, and **sealing** rules if present.

Three APIs of **java.lang.ClassLoader** help work with package metadata defined by a loader:

- **definePackage(...)**: declares a **java.lang.Package** object with a specific name and metadata in that loader.
- **getDefinedPackage(name)**: looks up a package **defined by this loader itself**, without searching the parent.
- **getDefinedPackages()**: lists the packages **defined by this loader itself**, without including packages from ancestors.

This is an important part when building a custom ClassLoader, a loader reading JARs/manifests, or a plugin runtime, especially when you need to keep metadata and package identity consistent.

**Core question:** Is “a package named p in loader A” the same as “package p in loader B”? The answer is **not necessarily**, because a runtime package is tied to both the **package name and the defining loader**.

## 2. Exact APIs and visibility

Relevant signatures in Java 17+:

~~~java
// Part of java.lang.ClassLoader:
protected Package definePackage(
        String name,
        String specTitle,
        String specVersion,
        String specVendor,
        String implTitle,
        String implVersion,
        String implVendor,
        java.net.URL sealBase);

public final Package getDefinedPackage(String name);

public final Package[] getDefinedPackages();
~~~

The snippets above are **illustrative API signatures**, not a standalone runnable class.

| API | Visibility | Result | Meaning |
| --- | --- | --- | --- |
| **definePackage(...)** | **protected** | Newly defined Package | Must be called from a ClassLoader subclass or a place with protected access. |
| **getDefinedPackage(name)** | **public final** | Package or null | Checks only package metadata already defined **on the invoked loader**. |
| **getDefinedPackages()** | **public final** | Package[] | Retrieves only packages **on the invoked loader**; empty array if no packages have been defined yet. |
| **getPackage(name)** | **protected, deprecated since Java 9** | Package or null | May search packages of the loader and its ancestors; easy to confuse ownership. |
| **getPackages()** | **protected** | Package[] | May include packages defined by the loader and its ancestors, even with duplicate names. |

**Note:** **final** on the getDefined... methods means a subclass cannot override them to skew the contract. **definePackage** is protected, so applications that want to set custom metadata typically create a subclass and call it through a wrapper.

### 2.1 What is the name string?

For **definePackage/getDefinedPackage**, the name argument is a **dot-separated package name**, for example:

~~~text
com.example.plugin
org.acme.services
io.sample.internal
~~~

Do not use a resource path **com/example/plugin**, do not append the **.class** suffix, and do not pass the full binary name of a class **com.example.plugin.Widget** when looking up the package **com.example.plugin**.

For these three methods, the package name must be understood separately from the **class binary name** accepted by **loadClass/defineClass**.

## 3. Java source package and runtime package are not completely identical

In source:

~~~java
package shop.billing;

public class Invoice {
}
~~~

The **package shop.billing** declaration helps the compiler organize namespaces and check access rules, but when the class is defined by the JVM, runtime information is also associated with the loader.

~~~text
Source:
  package shop.billing;

Binary class:
  shop.billing.Invoice

Runtime when defined:
  (package name = shop.billing, defining ClassLoader = LoaderA)
~~~

If another **LoaderB** defines another class also in **shop.billing**, the classes from the two loaders **are not automatically in the same runtime package** for package-private access checks.

According to the JVM Specification, a runtime package is identified by **the package name and the defining loader**. Therefore:

~~~text
("shop.billing", LoaderA) != ("shop.billing", LoaderB)
~~~

Even though the package name strings are the same, the Package metadata may differ: version, vendor, sealing base, and annotations.

**Do not infer that getDefinedPackage(name) will search the classpath or load every class in the package.** It only looks up packages already defined by the loader up to the time of the call.

## 4. When is a Package created?

There are two important paths.

### 4.1 Explicit definition via definePackage

A custom loader can call **definePackage** before defining the first class in the package in order to attach metadata such as the specification version or code source seal base.

~~~text
Custom loader
    |
    +-- definePackage("shop.billing", spec/impl/seal metadata)
    |
    +-- findClass("shop.billing.Invoice")
           |
           +-- read bytes
           +-- defineClass(...)
~~~

**A Package can already exist in the loader even before the loader defines a class belonging to that package.** Defining a Package does not mean classes have been loaded or initialized.

### 4.2 Automatic definition during defineClass

The **ClassLoader.defineClass** Javadoc states that if the new class belongs to a package not yet defined by the loader, **defineClass** will define the corresponding package in that loader.

When a package is created automatically, its metadata is determined by the rules of **java.lang.Package**. For example, for a class in an **unnamed module**, an automatically created package is normally **not sealed** and the specification/implementation title, version, and vendor fields are **unspecified**, so the getters may return null.

Key points:

- If you want **custom metadata**, the loader should call **definePackage before defineClass** for the first class in the package.
- If the package has already been defined automatically, a definePackage call with the same name in the same loader **cannot be used to add or modify metadata**.
- Once the package has been created, Package metadata **cannot be redefined or modified** via definePackage.

### 4.3 A package does not appear automatically just because of a source line

A project may contain hundreds of **package shop.billing** files, yet a specific loader has not defined any class belonging to that package, nor called definePackage. In that case:

~~~java
loader.getDefinedPackage("shop.billing")
~~~

can return **null**, even if you see the class files in the JAR or IDE.

Conversely, **definePackage** can cause getDefinedPackage to return non-null even though no class in that package has been loaded yet.

## 5. definePackage: eight parameters not to be confused

Full signature:

~~~java
definePackage(
    name,
    specTitle,
    specVersion,
    specVendor,
    implTitle,
    implVersion,
    implVendor,
    sealBase
);
~~~

| Parameter | Role | Example |
| --- | --- | --- |
| **name** | Dot-separated package name. | **shop.billing** |
| **specTitle** | Name of the specification that the package implements. | **Billing API** |
| **specVersion** | Specification version. | **1.2.3** |
| **specVendor** | Organization that owns the specification. | **Acme Standards** |
| **implTitle** | Name of the specific implementation. | **Billing Engine** |
| **implVersion** | Implementation version. | **build-7** |
| **implVendor** | Organization providing the implementation. | **Acme Software** |
| **sealBase** | Code source URL against which the package is sealed; null means not sealed. | **file:/opt/plugins/a.jar** |

All of the specification/implementation attributes above are metadata. Values such as vendor/title can typically be null when not provided.

**specVersion and implVersion do not serve the same purpose:** a package may conform to specification **1.2** while the implementation is released under version **2026.10**. The **Package.isCompatibleWith(version)** API relates to the **specification version**, not the implementation version.

### 5.1 Getters on java.lang.Package

A defined Package supports:

~~~java
p.getName();
p.getSpecificationTitle();
p.getSpecificationVersion();
p.getSpecificationVendor();
p.getImplementationTitle();
p.getImplementationVersion();
p.getImplementationVendor();
p.isSealed();
p.isSealed(url);
p.isCompatibleWith("1.2");
~~~

These are illustrative statement excerpts, not valid standalone expression statements in a Java method. When running them, use them in a println/assignment or another method.

**isCompatibleWith** compares specification versions by dot-separated numeric components. If the specification version is not yet set or the string is invalid, a **NumberFormatException** may be thrown. Do not use a version like **build-7** to check this API if the format does not satisfy the requirement.

## 6. Java 17+ Example 1: manual definePackage, reading metadata, preventing duplicate definition

Create the file **PackageMetadataDemo.java**:

~~~java
import java.net.URI;
import java.net.URL;

public class PackageMetadataDemo {
    static final class DemoLoader extends ClassLoader {
        DemoLoader(ClassLoader parent) {
            super(parent);
        }

        Package register(String name, URL sealBase) {
            return definePackage(
                    name,
                    "Billing API", "1.2.3", "Acme Standards",
                    "Billing Engine", "build-7", "Acme Software",
                    sealBase);
        }
    }

    public static void main(String[] args) throws Exception {
        DemoLoader loader = new DemoLoader(
                ClassLoader.getPlatformClassLoader());

        System.out.println("count before = "
                + loader.getDefinedPackages().length);

        URL jarA = URI.create("file:/opt/plugins/a.jar").toURL();
        URL jarB = URI.create("file:/opt/plugins/b.jar").toURL();

        Package p = loader.register("shop.billing", jarA);

        System.out.println("name = " + p.getName());
        System.out.println("spec version = "
                + p.getSpecificationVersion());
        System.out.println("implementation = "
                + p.getImplementationTitle());
        System.out.println("sealed = " + p.isSealed());
        System.out.println("sealed at jar A = " + p.isSealed(jarA));
        System.out.println("sealed at jar B = " + p.isSealed(jarB));
        System.out.println("compatible with 1.2 = "
                + p.isCompatibleWith("1.2"));
        System.out.println("same Package = "
                + (p == loader.getDefinedPackage("shop.billing")));
        System.out.println("missing Package = "
                + (loader.getDefinedPackage("shop.missing") == null));
        System.out.println("count after = "
                + loader.getDefinedPackages().length);

        try {
            loader.register("shop.billing", jarA);
            System.out.println("duplicate allowed");
        } catch (IllegalArgumentException expected) {
            System.out.println("duplicate = IllegalArgumentException");
        }
    }
}
~~~

Compile/run:

~~~bash
javac PackageMetadataDemo.java
java PackageMetadataDemo
~~~

Expected stdout on Java 17+:

~~~text
count before = 0
name = shop.billing
spec version = 1.2.3
implementation = Billing Engine
sealed = true
sealed at jar A = true
sealed at jar B = false
compatible with 1.2 = true
same Package = true
missing Package = true
count after = 1
duplicate = IllegalArgumentException
~~~

### 6.1 Explanation

**DemoLoader** is a new loader that has not defined any classes or packages itself. The class containing the DemoLoader code belongs to the calling program's loader, not defined by the newly created DemoLoader object. Therefore, before the first register call, **getDefinedPackages().length** on that loader is 0.

**register** calls protected definePackage from the subclass, allowing main code to add a package with metadata.

**isSealed** only checks the stored Package metadata. The URL object jarA is the seal base, so isSealed(jarA) is true; the different URL jarB is false.

**getDefinedPackage("shop.billing")** returns the exact Package object created earlier. Reading the getters does not cause the loader to load the Invoice class or automatically open a JAR.

**Calling register with the same name again** throws **IllegalArgumentException**, because a loader cannot definePackage with a duplicate name, regardless of whether the new metadata is the same or different. Trying to replace metadata in the same loader after the package has been created is too late.

### 6.2 Warning: sealing metadata does not automatically make a loader secure

The demo only calls **definePackage** and has not defined any classes from a JAR. **Package.isSealed() == true** indicates that the metadata says the package is sealed. It **does not prove that every custom ClassLoader will automatically check the JAR source URL** against sealBase across all defineClass paths. A loader implementing JAR/manifest reading and class definition must respect appropriate sealing checks. Standard JAR loaders have corresponding logic.

Do not use definePackage as a sandboxing tool against untrusted bytecode.

## 7. getDefinedPackage(name): only inspects packages of the loader itself

Signature:

~~~java
public final Package getDefinedPackage(String name);
~~~

Key characteristics:

- Returns the **Package** defined by **the invoked loader**.
- Returns **null** if this loader has not yet defined a package with the corresponding name.
- Passing **null** as name throws **NullPointerException**.
- **Does not** automatically load classes, search resources, or ask the parent to obtain a Package.
- Does not require the package to currently have any object instances or initialized classes.
- If the package was defined earlier, returns the existing metadata of the loader.

Example:

~~~java
Package own = childLoader.getDefinedPackage("api.common");
~~~

If the class **api.common.Service** was defined by the parent loader and the child only delegates to use that class, the method above can still return **null**: the package belongs to the **parent**, not to the child.

**Do not equate the initiating loader with the defining loader.** The child may call loadClass and receive a Class defined by the parent; that does not create a corresponding Package in the child.

## 8. getDefinedPackages(): accurately listing local definitions

Signature:

~~~java
public final Package[] getDefinedPackages();
~~~

Contract:

- Returns **an array** of Package objects defined by this loader.
- **Does not** automatically merge packages of the parent or ancestors.
- There are no **two Packages with the same name** in the array returned by a single loader.
- Returns an **array of length 0** if the loader has not defined any packages yet.
- You should not rely on the **order** of elements because the API does not guarantee an ordering suitable for business sorting.

Example of handling the result:

~~~java
Package[] ownPackages = loader.getDefinedPackages();

for (Package p : ownPackages) {
    System.out.println(p.getName()
            + " : " + p.getSpecificationVersion());
}
~~~

This is a snippet placed inside a method that has a loader variable. If you need deterministic report output, **sort by getName()** before printing; do not infer that the returned order equals the load order or the JAR file order.

### 8.1 getDefinedPackages does not mean all packages existing in the JVM

A Java process can contain hundreds of loaders, modules, and different JARs. **getDefinedPackages on one loader is only a local view**, not a JVM-wide registry. To check which loader a class actually comes from, use **clazz.getClassLoader()** together with the appropriate Class metadata/package.

## 9. Comparison with legacy getPackage and getPackages

Two other APIs that can cause confusion:

~~~java
// In a ClassLoader subclass:
protected Package getPackage(String name);
protected Package[] getPackages();
~~~

**getPackage(name)** has been **deprecated since Java 9**. It looks in the loader itself and then searches ancestors if not yet found. In loaders that may define the same package name, returning a package from the parent can cause metadata/annotations not to reflect the package that the child would define.

**getPackages()** also retrieves packages defined by the loader and its ancestors. The returned array **may contain two Packages with the same name** if both the parent and child each define that name.

This differs from getDefinedPackages: the local array contains no duplicate names.

| API | Scope | Can see parent packages? | Notes |
| --- | --- | --- | --- |
| **getDefinedPackage("p")** | Current loader only | No | Public final; preferred when exact package ownership is needed. |
| **getDefinedPackages()** | Current loader only | No | Public final; no duplicate names within a single loader. |
| **getPackage("p")** | Loader and ancestors | Yes | Protected and deprecated since Java 9. |
| **getPackages()** | Loader and ancestors | Yes | Protected; may return multiple Packages with the same name but different owners. |

**Do not use getPackage to determine that “the package has already been defined by the child”.** It may only be detecting a package in the parent.

## 10. Java 17+ Example 2: same package name in parent and child

This example manually defines Package metadata in two different loaders, without needing to create class files, to demonstrate the scope of the APIs.

Create the file **PackageScopeDemo.java**:

~~~java
public class PackageScopeDemo {
    static final class PackageLoader extends ClassLoader {
        PackageLoader(ClassLoader parent) {
            super(parent);
        }

        Package add(String name, String version) {
            return definePackage(
                    name, "Shared API", version, "Acme",
                    "Runtime", "1", "Acme", null);
        }

        @SuppressWarnings("deprecation")
        Package legacyLookup(String name) {
            return getPackage(name);
        }

        int visiblePackageMatches(String name) {
            int count = 0;
            for (Package p : getPackages()) {
                if (name.equals(p.getName())) {
                    count++;
                }
            }
            return count;
        }
    }

    public static void main(String[] args) {
        PackageLoader parent = new PackageLoader(
                ClassLoader.getPlatformClassLoader());
        PackageLoader child = new PackageLoader(parent);

        Package parentPackage = parent.add("demo.shared", "1.0");

        System.out.println("child local before = "
                + (child.getDefinedPackage("demo.shared") == null));
        System.out.println("legacy found parent = "
                + (child.legacyLookup("demo.shared") == parentPackage));
        System.out.println("visible matches before = "
                + child.visiblePackageMatches("demo.shared"));

        Package childPackage = child.add("demo.shared", "2.0");

        System.out.println("child version = "
                + child.getDefinedPackage("demo.shared")
                        .getSpecificationVersion());
        System.out.println("same Package object = "
                + (childPackage == parentPackage));
        System.out.println("visible matches after = "
                + child.visiblePackageMatches("demo.shared"));
        System.out.println("child local count = "
                + child.getDefinedPackages().length);
    }
}
~~~

Compile and run:

~~~bash
javac PackageScopeDemo.java
java PackageScopeDemo
~~~

Expected stdout:

~~~text
child local before = true
legacy found parent = true
visible matches before = 1
child version = 2.0
same Package object = false
visible matches after = 2
child local count = 1
~~~

### 10.1 Why does the same package name not cause IllegalArgumentException?

The rule forbidding duplicate definePackage names applies **within the same loader**. The parent and child are **two different ClassLoader objects**, so each loader can define a Package with the same name **demo.shared**.

In the example:

~~~text
PackageLoader parent
    +-- demo.shared, specVersion 1.0

PackageLoader child (parent is the loader above)
    +-- demo.shared, specVersion 2.0
~~~

**child.getDefinedPackage("demo.shared")** is initially null even though the parent already has the package. **legacyLookup** searches up to the parent, so it finds the older Package. After the child defines its own, the local Package is returned, and getPackages can output both Packages with the same name.

**Important practical note:** the demo only defines Package metadata and has not defined any classes under those two packages. The fact that Java allows two loaders to hold a Package with the same name **does not mean you should split a shared interface/DTO across two defining loaders**. Runtime package identity and class identity can become problematic when code needs to interact across a loader boundary.

## 11. Java 17+ Example 3: defineClass automatically creates a Package when not yet defined

Now observe a package appearing **automatically**, without manually calling definePackage.

Structure:

~~~text
project/
├── AutoPackageDemo.java
└── plugin-src/
    └── lab/
        └── auto/
            └── Marker.java
~~~

**plugin-src/lab/auto/Marker.java**:

~~~java
package lab.auto;

public class Marker {
    public String value() {
        return "ready";
    }
}
~~~

**AutoPackageDemo.java**:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class AutoPackageDemo {
    static final class ByteLoader extends ClassLoader {
        private final Path root;

        ByteLoader(Path root) {
            super(ClassLoader.getPlatformClassLoader());
            this.root = root;
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            try {
                byte[] bytes = Files.readAllBytes(
                        root.resolve(name.replace('.', '/') + ".class"));
                return defineClass(name, bytes, 0, bytes.length);
            } catch (IOException ex) {
                throw new ClassNotFoundException(name, ex);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        ByteLoader loader = new ByteLoader(Path.of("plugin-out"));

        System.out.println("before = "
                + (loader.getDefinedPackage("lab.auto") == null));

        Class<?> type = loader.loadClass("lab.auto.Marker");
        Package p = loader.getDefinedPackage("lab.auto");

        System.out.println("after name = " + p.getName());
        System.out.println("spec version null = "
                + (p.getSpecificationVersion() == null));
        System.out.println("sealed = " + p.isSealed());
        System.out.println("defined by loader = "
                + (type.getClassLoader() == loader));
        System.out.println("defined count = "
                + loader.getDefinedPackages().length);

        Class<?> base = loader.loadClass("java.lang.String");
        System.out.println("bootstrap class = "
                + (base.getClassLoader() == null));
        System.out.println("java.lang locally defined = "
                + (loader.getDefinedPackage("java.lang") != null));
    }
}
~~~

Compile from the **project** directory:

~~~bash
javac -d plugin-out plugin-src/lab/auto/Marker.java
javac AutoPackageDemo.java
java AutoPackageDemo
~~~

Expected stdout with this classpath and loader setup:

~~~text
before = true
after name = lab.auto
spec version null = true
sealed = false
defined by loader = true
defined count = 1
bootstrap class = true
java.lang locally defined = false
~~~

### 11.1 Analysis

- Initially ByteLoader has not defined any class or the lab.auto package, so getDefinedPackage returns null.
- The parent (platform loader) does not see lab.auto.Marker in plugin-out; the custom loader calls findClass, reads the bytes, and then calls defineClass.
- Because there is no lab.auto package in the loader yet, **defineClass automatically creates a Package** with default metadata for an unnamed module.
- **getDefinedPackages().length == 1** reflects the newly created local package.
- The loader can initiate loading of the java.lang.String class via delegation, yet it **does not define** the java.lang package. Therefore, getDefinedPackage("java.lang") remains null.

**Environment note:** Do not place plugin-out on a classpath where the parent in the example can see lab.auto.Marker; otherwise, the class may be defined by the parent and the output will differ.

### 11.2 Can metadata be modified after automatic definition?

If after **loader.loadClass("lab.auto.Marker")** you call **definePackage("lab.auto", ...)** through the subclass, the operation will throw IllegalArgumentException because the local package already exists.

If you want to set version/seal metadata for a package in a custom loader, do so before the first class in that package is defined. If loading from a standard JAR, use a manifest-aware loader instead of manually getting the metadata wrong.

## 12. What is package sealing?

**Package sealing** is a rule by which a package/JAR can restrict the code source for classes belonging to the same package. When a package is sealed with a code source URL, classes loaded into that package by the loader must comply with the matching source according to the loader/JAR contract.

~~~text
Package demo.internal
    sealed with URL: file:/plugins/a.jar
            |
            +-- class from a.jar: compliant
            |
            +-- class from b.jar: sealing violation if enforced by the loader
~~~

A JAR Manifest may contain:

~~~text
Manifest-Version: 1.0
Sealed: true
~~~

Or override sealing for a package via a manifest entry, for example:

~~~text
Name: demo/internal/
Sealed: true
~~~

**Package.isSealed()** indicates whether the package metadata is sealed; **Package.isSealed(URL)** checks whether it is sealed with respect to the passed code source URL.

### 12.1 Distinguishing package sealing from Java 17 sealed classes

These are two different mechanisms:

| Package sealing | Sealed class/interface |
| --- | --- |
| Belongs to packages/JARs and code sources, represented in Package metadata. | Belongs to the Java type system, using **sealed**, **permits**, and subclass restrictions. |
| Tied to the source defining the classes in the package. | Controls which classes are permitted to extend/implement a class/interface. |
| Typically involves a loader reading a JAR manifest. | Checked by the compiler/JVM via type definitions. |
| Typical API: Package.isSealed(). | sealed class syntax, Class.isSealed(), Class.getPermittedSubclasses(). |

A sealed package does not mean every class inside it is a sealed class; a sealed class can reside in an unsealed package.

### 12.2 Warning when building a custom loader

**definePackage** attaches sealing metadata, but **enforcing sealing across multiple code sources** requires the JAR-loading loader to apply the proper checks. **URLClassLoader/standard JAR class loaders** contain logic to read manifests and check sealing. Do not simply call definePackage and conclude that all byte sources have been verified.

If you read bytes yourself and call defineClass, you need to consider the code source, protection domain, certificates, package rules, and appropriate sealing checks. Do not catch SecurityException and treat it as ClassNotFoundException.

## 13. Manifest metadata and class loading order

In a JAR, package metadata is typically read from **META-INF/MANIFEST.MF**. Attributes such as Specification-Title, Specification-Version, Implementation-Version, and Sealed may appear in main attributes or in per-package sections.

Example manifest description:

~~~text
Manifest-Version: 1.0
Implementation-Title: Billing Engine
Implementation-Version: 3.4.1

Name: shop/billing/
Specification-Title: Billing API
Specification-Version: 1.2.3
Sealed: true
~~~

If multiple JARs contain classes in the same package defined by a single loader, **the order in which the class/package is defined first** can affect the recorded package metadata. That is why plugins should avoid unintended split packages and should not rely on getDefinedPackage as a merged metadata table across multiple JARs.

**Package metadata is not automatically updated** when a second class in the same package comes from another JAR. If metadata was already created earlier, the loader must respect the existing package state and perform appropriate sealing checks.

### 13.1 Do not infer from Package the exact JAR containing every class

Package is metadata for the runtime package, **not a map for individual class files** or a JAR scanning command. To investigate where a Class was defined from, check the defining loader, **ProtectionDomain/CodeSource** when available, and appropriate logging/JAR listing tools.

## 14. Do named modules differ from unnamed modules?

Since Java 9, the module system affects how packages are created:

- For **classes in an unnamed module**, an automatically defined Package is normally not sealed and has no specification/implementation metadata unless the loader sets it explicitly.
- For **classes in a named module**, Package has its own automatic rules; the package may be sealed to the module location if known, and specification/implementation title/version/vendor metadata are usually unspecified.
- The Javadoc **strongly recommends not calling definePackage manually for packages of named modules**, and instead letting defineClass create the package according to module rules.
- If there is still a genuine reason to define it manually, you must ensure that the Package objects in the module have properties consistent with the Package rules; for example, you must not assign an incorrect seal base.

**Do not treat the module name as a replacement for the defining loader in every concept.** Module membership also affects exports/opens/readability, whereas runtime package identity remains tied to the loader, and the Package API describes metadata according to the rules of the corresponding class/module.

## 15. Should Package.getPackage and Package.getPackages be used?

Some older documentation still mentions static methods on java.lang.Package:

~~~java
Package.getPackage("shop.billing");
Package.getPackages();
~~~

These legacy APIs have semantics based on the caller's loader and can cause confusion in multi-loader environments. Since Java 9, they have been **deprecated** in favor of APIs that reflect ownership more clearly.

When you already know the loader you are inspecting, prefer:

~~~java
ClassLoader loader = SomeClass.class.getClassLoader();
Package p = loader.getDefinedPackage("shop.billing");
Package[] own = loader.getDefinedPackages();
~~~

This is a snippet; a concrete SomeClass is needed, and note that **Class.getClassLoader() can return null** for bootstrap-defined classes, so null must be handled before calling loader methods.

When you have a specific Class, you can also use **SomeClass.class.getPackage()** to obtain the Package associated with that class. This approach is often closer to your intent when asking “what metadata does this class's own runtime package have?”, rather than asking “has loader A defined a package with this name yet?”.

## 16. Troubleshooting workflow

### 16.1 getDefinedPackage(name) returns null even though the source has the package

Check:

1. Are you calling on the class's actual **defining loader**?
2. Has the package already been defined by this loader via definePackage or defineClass?
3. Was the class defined by the parent due to parent-first delegation?
4. Does the package name string use dots and the exact case?
5. Is the code mistaking getDefinedPackage for a command that searches for a package on the classpath?

If the class was defined by the parent, getDefinedPackage on the child does not automatically see the parent's package.

### 16.2 definePackage throws IllegalArgumentException

A package with the same name **has already been defined in that loader itself**. Either an earlier defineClass automatically created the package, or the code already called definePackage manually.

**How to fix:** move metadata registration before defineClass, check getDefinedPackage if needed, and synchronize the lifecycle when multiple threads load classes. Do not retry indefinitely with new metadata because a package cannot be redefined.

### 16.3 SecurityException related to sealing/certificates

Check the code source, JAR manifest, sealBase, and previously defined package. A loader reading multiple JARs that contain a sealed split package may encounter a sealing violation. In addition, ClassLoader.defineClass enforces certificate set constraints across classes in the same package.

Do not handle all these errors merely as ClassNotFoundException; package integrity errors must be investigated separately.

### 16.4 Package metadata differs from the manifest you just inspected

The loader may have defined the package from an earlier JAR or class. A Package does not overwrite its metadata each time a new class is loaded.

Check the classpath/JAR order, parent delegation, named/unnamed module, and the loader that actually defines the class. Do not assume Manifest-Version is the specification version: those are two separate concepts.

### 16.5 ClassCastException or IllegalAccessError across loaders

If two loaders define a class with the same name or a package with the same name, they may not be the same runtime type/package. To check:

~~~java
System.out.println(a.getName().equals(b.getName()));
System.out.println(a == b);
System.out.println(a.getClassLoader());
System.out.println(b.getClassLoader());
~~~

The snippet above assumes two existing Class objects a and b. Having the same string name but different Class objects can explain a cast failure. Package-private access is also governed by runtime package identity, not only the source package statement.

## 17. Misconceptions to avoid

- **“definePackage creates every class in the package.”** False: it creates Package metadata; defineClass is what creates a runtime class.
- **“getDefinedPackages scans the entire classpath.”** False: it only returns packages that this loader has already defined.
- **“Child.getDefinedPackage sees the parent's package.”** False: there is no delegation in this API.
- **“getPackage and getDefinedPackage are the same.”** False: the legacy getPackage can search ancestors.
- **“Two loaders with the same package name must share one Package.”** False: each defining loader can define its own separate package with the same name.
- **“Having a Package object means some class has been initialized.”** False: definePackage can be called before any class exists.
- **“Package metadata can be modified by calling definePackage again.”** False: a duplicate name in the same loader throws IllegalArgumentException.
- **“isSealed=true always makes a custom loader block every other bytecode source.”** Insufficient: the loader must enforce integrity/sealing rules properly.
- **“A sealed package is a sealed class.”** False: two independent mechanisms.
- **“Another JAR loaded later updates the Package's version.”** No: once established, metadata is not automatically overwritten.
- **“Package ownership is only the package name.”** False: a runtime package is also bound to the defining loader.
- **“Named modules should always call definePackage manually.”** False: the Javadoc advises letting it be defined automatically.

## 18. Self-check exercises

**Question 1.** A custom loader has not defined any classes yet; does calling definePackage("app.core", ...) make getDefinedPackage("app.core") return non-null?

**Answer:** Yes. definePackage creates the loader's own Package metadata prior to defineClass.

**Question 2.** After defineClass automatically creates the app.core package, can you call definePackage with the same name to add a version?

**Answer:** No. The package has already been defined; calling definePackage with a duplicate name in the same loader throws IllegalArgumentException.

**Question 3.** A child loader delegates loadClass("api.Service") to its parent and receives the parent's Class. Must Child.getDefinedPackage("api") be non-null?

**Answer:** No. The child only initiates loading of the class via delegation, while the parent defines the class/package.

**Question 4.** How do getDefinedPackages and getPackages differ in a loader that has a parent?

**Answer:** getDefinedPackages lists only packages defined by the current loader; getPackages can also list packages of ancestors and duplicate names.

**Question 5.** Two loaders A and B both call definePackage("p.q", ...). Is this invalid behavior solely because the names match?

**Answer:** No. The uniqueness rule applies within each loader. Two runtime packages can have the same name with different owners.

**Question 6.** What does isSealed(url) returning true mean?

**Answer:** Package metadata records that the package is sealed with the corresponding sealBase URL; the loader enforcing sealing when loading code sources must follow the implementation's contract.

**Question 7.** How does Package.getSpecificationVersion() differ from getImplementationVersion()?

**Answer:** One records the version of the specification, while the other records the version of the specific implementation.

**Question 8.** Does getDefinedPackages guarantee an order matching the JAR classpath?

**Answer:** No. If you want deterministic output, sort by getName.

**Question 9.** Why does the Javadoc discourage calling definePackage manually in named modules?

**Answer:** Modules have their own automatic Package definition rules, including sealing base/metadata; setting them manually can produce inconsistent information.

**Question 10.** Can definePackage be used to fix package-private access between two ClassLoaders that share the same package name?

**Answer:** No. Runtime package identity also depends on the defining loader; metadata does not turn two runtime packages into one.

## 19. Key takeaways

~~~text
ClassLoader L
    |
    +-- definePackage("p.q", metadata)
    |      -> creates local Package, before defineClass
    |
    +-- defineClass("p.q.Foo", bytes)
    |      -> automatically defines local Package if not yet present
    |
    +-- getDefinedPackage("p.q")
    |      -> retrieves only the Package defined by L
    |
    +-- getDefinedPackages()
           -> all local Packages of L

Parent packages are NOT automatically included in getDefinedPackages(L).
Runtime package identity is also bound to the defining loader.
~~~

**Most important principle:** use **definePackage** to set metadata before the first class in the package is defined; use **getDefinedPackage/getDefinedPackages** to verify the loader's exact local ownership. Do not use these APIs as a classpath scanner, do not equate a package name with runtime package identity, and pay attention to sealing/metadata/modules when designing a JAR-reading class loader.

### Official references

- **ClassLoader API, Java SE 21** — definePackage/getDefinedPackage/getDefinedPackages/getPackage/getPackages: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html
- **Package API, Java SE 21** — metadata, sealing, versioning, and module behavior: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Package.html
- **JAR File Specification, Java SE 21 — Package Sealing:** https://docs.oracle.com/en/java/javase/21/docs/specs/jar/jar.html
- **JVMS §5.3, Creation and Loading:** https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3
