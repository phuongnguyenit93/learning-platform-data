# Multi-Release JARs and module-info in META-INF/versions

A Multi-Release JAR (MR-JAR) allows a library to package multiple versions of classes and resources inside the same JAR file. The JVM selects the version matching the runtime's major version, allowing the library to keep implementations compatible with older Java versions while still taking advantage of newer APIs on newer Java versions.

An important case is placing the module descriptor at `META-INF/versions/9/module-info.class`. This allows a JAR to have base classes compatible with Java 8 while becoming an explicit module when used on Java 9 or later.

## 1. Structure of a Multi-Release JAR

An MR-JAR is identified by a main attribute in the manifest:

~~~text
Manifest-Version: 1.0
Multi-Release: true
~~~

Java-version-specific files are placed under the directory:

~~~text
META-INF/versions/N/
~~~

`N` is the Java major version, starting from 9. For example:

~~~text
library.jar
|-- META-INF/
|   |-- MANIFEST.MF
|   |-- versions/
|       |-- 9/
|       |   |-- module-info.class
|       |   |-- com/example/RuntimeFeature.class
|       |-- 17/
|           |-- com/example/RuntimeFeature.class
|-- com/
    |-- example/
        |-- Library.class
        |-- RuntimeFeature.class
~~~

When running on Java N, the class loader searches for an entry at version N first, then successively at lower versions down to 9, and finally falls back to the entry in the root directory. Directories with versions higher than the current runtime are not selected.

For example, on a Java 17 runtime:

- If an entry exists in versions/17, use that entry.
- If versions/17 does not have it but versions/11 does, use the entry in versions/11.
- If no matching version exists, use the entry in the root directory.

On Java 8, the runtime does not support the multi-release mechanism and therefore uses the base entries in the root directory. The versioned directories are not treated as alternative versions.

`N` must be a valid major integer of 9 or greater. Use the exact form `META-INF/versions/9`; do not place the module descriptor at a deeper nested path such as `META-INF/versions/9/META-INF/module-info.class`.

## 2. Why Can module-info Reside in META-INF/versions/9?

A standard modular JAR has its module descriptor at the root:

~~~text
module-info.class
com/example/Library.class
~~~

However, a modular multi-release JAR can place the module descriptor at the root or directly inside a versioned directory. Therefore, a JAR can have the structure:

~~~text
library.jar
|-- META-INF/
|   |-- MANIFEST.MF
|   |-- versions/
|       |-- 9/
|           |-- module-info.class
|           |-- com/example/Java9Feature.class
|-- com/
    |-- example/
        |-- Library.class
~~~

In this example:

- The classes at the root form the base, which can be compiled to run on Java 8.
- `module-info.class` in versions/9 describes the module for Java 9 and later.
- On Java 9+, when the JAR is placed on the module path and the manifest enables Multi-Release, the JDK can recognize this JAR as an explicit module.
- On Java 8, there is no module system and the versioned module descriptor is not used; the base classes can still run as a normal JAR.

This is a way to convert a Java 8-compatible library into a modular JAR without forcing Java 8 users to upgrade immediately.

Note: `module-info.class` must reside directly inside `META-INF/versions/N`. A module descriptor is only recognized under modular multi-release JAR rules when the archive is marked `Multi-Release: true`.

## 3. Manifest and Version Selection Rules

The manifest must contain the `Multi-Release` attribute in the main section:

~~~text
Manifest-Version: 1.0
Multi-Release: true

~~~

This attribute applies to the entire JAR. Simply creating the `META-INF/versions/9` directory without the `Multi-Release: true` attribute is not enough for the runtime to process entries under the MR-JAR mechanism.

When running on a JDK that supports multi-release, the runtime picks the entry with the highest version not exceeding the current major version. Only then does it fall back to the root entry.

For example, with a class having three versions:

~~~text
com/example/RuntimeFeature.class
META-INF/versions/9/com/example/RuntimeFeature.class
META-INF/versions/17/com/example/RuntimeFeature.class
~~~

| Runtime | Selected Entry |
|---|---|
| Java 8 | Root |
| Java 9 | Version 9 |
| Java 11 | Version 9 |
| Java 17 | Version 17 |
| Java 21 | Version 17 |

Version selection happens per entry. One class may be loaded from the root while another class in the same JAR is loaded from versions/17.

## 4. Compatibility Rules for Versioned Module Descriptors

A module descriptor in a versioned area is handled much like a versioned class or resource, but with additional constraints so the module keeps a consistent structure across versions.

If a descriptor at a higher version replaces a descriptor at a lower version or at the root, the two descriptors must be identical, except for two permitted groups of differences:

1. Non-transitive `requires` directives for modules in the `java.*` or `jdk.*` namespaces may differ.
2. `uses` clauses may differ, even when the service type is defined outside `java.*` and `jdk.*` modules.

The remaining parts of the module descriptor—such as the module name, `exports`, `opens`, `provides`, and other `requires`—must remain consistent according to the JAR specification rules.

If the JAR only has `module-info.class` in versions/9, that descriptor is the first descriptor. If an additional descriptor exists in versions/17, the 17 descriptor must remain consistent with the 9 descriptor subject to the exceptions above.

For example, a module might add `uses` for a service that only exists starting in Java 17 inside `module-info` under versions/17. However, do not arbitrarily change `exports` or the provider list across versioned descriptors.

## 5. API Compatibility Rules for Versioned Classes

MR-JARs are designed to keep the public API consistent across Java versions. Therefore, a public or protected class in a versioned directory must normally have a corresponding class with the same fully qualified name and access modifier at the root or in a lower versioned directory that it overrides.

For modular MR-JARs, there is an exception: a public or protected class in a package that is not exported by the module descriptor is not required to have a corresponding class at the root.

For example:

~~~text
com/example/api/Client.class
META-INF/versions/17/com/example/api/Client.class
~~~

If the `com.example.api` package is exported, the Java 17 version of `Client` must maintain a public API matching the base version. The internal implementation may differ, but public/protected signatures need to remain consistent.

This ensures consumers compiled against one Java version can still use the library on another version without unexpected API changes.

## 6. Creating an MR-JAR with module-info in Version 9

Suppose a library supports Java 8 and has a module descriptor starting from Java 9. You can structure the build output as follows:

~~~text
build/
|-- base/
|   |-- com/example/api/Library.class
|   |-- com/example/api/RuntimeFeature.class
|-- v9/
    |-- module-info.class
    |-- com/example/api/RuntimeFeature.class
~~~

The base part contains Java 8-compatible classes. The v9 part contains the module descriptor and the Java 9 implementation. Example `module-info.java`:

~~~java
module com.example.library {
    exports com.example.api;
}
~~~

Compile the base part using JDK 9 or later targeting Java 8:

~~~bash
javac --release 8 -d build/base \
    src/base/com/example/api/Library.java \
    src/base/com/example/api/RuntimeFeature.java
~~~

Compile the module descriptor and version 9 classes:

~~~bash
javac --release 9 -d build/v9 \
    src/v9/module-info.java \
    src/v9/com/example/api/RuntimeFeature.java
~~~

Package both parts into the same JAR:

~~~bash
jar --create --file build/library.jar \
    -C build/base . \
    --release 9 -C build/v9 .
~~~

The `--release 9` option places subsequent files under `META-INF/versions/9`. When using the `jar` tool to add versioned entries, the manifest is automatically marked `Multi-Release: true`. If using Maven, Gradle, or another packaging tool, verify that the manifest is generated properly.

You can add multiple releases by repeating the `--release` option with the corresponding version:

~~~bash
jar --create --file build/library.jar \
    -C build/base . \
    --release 9 -C build/v9 . \
    --release 17 -C build/v17 .
~~~

Each versioned directory must contain classes compiled for no higher than that directory's major version. For example, classes in versions/17 must not have a class file version newer than Java 17.

## 7. Inspecting JAR Structure After Packaging

Do not rely solely on the build completing without errors. Inspect the archive structure and the module descriptor.

List the entries:

~~~bash
jar --list --file build/library.jar
~~~

The output should contain entries similar to:

~~~text
META-INF/MANIFEST.MF
com/example/api/Library.class
com/example/api/RuntimeFeature.class
META-INF/versions/9/module-info.class
META-INF/versions/9/com/example/api/RuntimeFeature.class
~~~

Inspect the manifest:

~~~bash
unzip -p build/library.jar META-INF/MANIFEST.MF
~~~

Confirm the main section contains:

~~~text
Multi-Release: true
~~~

On JDK 9 or later, you can ask the `jar` tool to describe the module:

~~~bash
jar --describe-module --file build/library.jar
~~~

If the JAR only has a module descriptor in versions/9, the command above should still recognize the module when run with a JDK that supports modular MR-JARs.

You can verify with `ModuleFinder` in Java:

~~~java
import java.lang.module.ModuleFinder;
import java.lang.module.ModuleReference;
import java.nio.file.Path;

ModuleReference reference = ModuleFinder.of(
        Path.of("build/library.jar"))
        .find("com.example.library")
        .orElseThrow(() ->
                new IllegalStateException("Module not found"));

System.out.println(reference.descriptor().name());
System.out.println(reference.descriptor().packages());
~~~

`ModuleFinder.of()` uses module path rules to locate module descriptors, including descriptors in the versioned area of a valid MR-JAR. This is a good check to confirm the JAR is recognized as an explicit module on the current JDK.

With newer JDKs that support it, `jar --validate --file build/library.jar` can check the integrity and API consistency of an MR-JAR. If using an older JDK that does not support this option, use the structure, manifest, and `ModuleFinder` checks above.

## 8. Testing Behavior Across JDKs

A useful test should verify both the archive structure and how the runtime selects versions.

### Testing the Descriptor on Java 9+

~~~java
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ModularJarTest {

    @Test
    void recognizesVersionedModuleDescriptor() {
        var reference = ModuleFinder.of(Path.of("build/library.jar"))
                .find("com.example.library")
                .orElseThrow();

        assertEquals(
                "com.example.library",
                reference.descriptor().name());
    }
}
~~~

This test should run on JDK 9 or later. On Java 8 there is no `ModuleFinder` and no concept of named modules to test.

### Testing the Entry Selected by Runtime Version

You can use `JarFile` with `Runtime.Version` to read the corresponding multi-release view:

~~~java
import java.io.IOException;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;
import java.util.zip.ZipFile;
import java.nio.file.Path;

try (JarFile jar = new JarFile(
        Path.of("build/library.jar").toFile(),
        true,
        ZipFile.OPEN_READ,
        Runtime.version())) {

    JarEntry entry = jar.getJarEntry(
            "com/example/api/RuntimeFeature.class");

    if (entry == null) {
        throw new IllegalStateException("RuntimeFeature not found");
    }

    System.out.println(entry.getRealName());
}
~~~

`getRealName()` reveals the actual entry name in the archive selected for that logical entry. For instance, on Java 17 if a version 17 copy exists, the actual name could be `META-INF/versions/17/com/example/api/RuntimeFeature.class`.

### Running Tests Across Multiple Runtimes

You should have a minimal test matrix:

| Runtime | What to Verify |
|---|---|
| Java 8 | Base classes at root run properly; the versioned module descriptor does not affect runtime |
| Java 9 | Recognizes `module-info` in versions/9 and selects version 9 classes |
| Java 11 | Selects the highest version not exceeding 11, e.g., version 9 |
| Java 17 | Selects version 17 if the archive has a matching entry |
| Newer Java | Continues falling back to the highest available version not exceeding the runtime |

Java 8 only checks classpath compatibility and the base classes. Tests for `ModuleFinder`, `ModuleDescriptor`, and the module path must run on JDK 9 or later.

## 9. Common Mistakes

- **Forgetting Multi-Release: true:** entries in `META-INF/versions` are not processed as alternative versions.
- **Wrong path for the module descriptor:** use `META-INF/versions/9/module-info.class`; do not nest `module-info` inside another subdirectory.
- **Assuming the JAR automatically becomes a module just by having a versions/9 directory:** there must be a valid `module-info.class` and the manifest must enable multi-release.
- **Compiling versioned classes with too new a target:** class files in versions/N must be compatible with major version N.
- **Changing the public API across releases:** keep the public API consistent according to MR-JAR rules.
- **Changing the module descriptor arbitrarily:** versioned descriptors must be identical, with only specific exceptions for non-transitive `requires` of `java.*`/`jdk.*` and `uses`.
- **Placing service configurations in META-INF/versions:** resources under `META-INF` such as `META-INF/services` are not versioned by this mechanism. For named modules, declare `uses`/`provides` in the module descriptor.
- **Testing only on a newer JDK:** this can miss compatibility issues in the base classes. Run tests on the oldest runtime the library commits to supporting as well.
- **Placing a modular JAR on the classpath and expecting it to be a named module:** the module descriptor only matters when the JAR is used on the module path; on the classpath it behaves like a non-modular JAR.

## 10. Key Takeaways

A Multi-Release JAR uses the `Multi-Release: true` manifest attribute and `META-INF/versions/N` directories to provide classes/resources per major version. The module descriptor can reside at the root or directly inside a versioned directory, such as `META-INF/versions/9/module-info.class`. This allows a single JAR to keep base classes compatible with Java 8 while being recognized as an explicit module on Java 9 and later.

When releasing, inspect the manifest, the `module-info` path, the descriptor via `ModuleFinder`, and the actual selected classes/resources via `JarFile`. Run tests on target JDKs to confirm both backward compatibility and modular behavior on newer runtimes.

## References

- JAR File Specification — Multi-release JAR and Modular multi-release JAR: https://docs.oracle.com/en/java/javase/26/docs/specs/jar/jar.html
- The jar Command — `--release`, `--describe-module`, and `--validate` options: https://docs.oracle.com/en/java/javase/25/docs/specs/man/jar.html