# Automatic Module Name from Automatic-Module-Name

## 1. Context and Objectives

Since Java 9, the Java Platform Module System (JPMS) allows applications to organize code into **named modules**. While migrating legacy libraries to the module path, many JARs do not yet have `module-info.class`. When such a JAR is placed on the **module path**, Java can treat it as an **automatic module** so that explicitly declared modules can use that library.

The key takeaway of this lesson is that library authors can declare a **stable module name** using the `Automatic-Module-Name` attribute in the JAR's manifest. Library consumers will use that exact name in the `requires` statement of `module-info.java`.

After this lesson, you will be able to:
- Distinguish a module name obtained from the manifest from a name automatically derived from the JAR file name.
- Declare `Automatic-Module-Name` when packaging a JAR.
- Use the declared module name in `requires` and verify it with the `jar` tool.
- Recognize common errors when a library is placed on the module path.

## 2. How Does Java Determine the Automatic Module Name?

A JAR **without a module descriptor** `module-info.class` is treated as an automatic module when placed on the module path. Java determines its name in the following order:

1. If the main section of the manifest (`META-INF/MANIFEST.MF`) has a valid `Automatic-Module-Name` attribute, use **that attribute's value**.
2. If this attribute is absent, Java **derives the name from the JAR file name**, stripping the version part and normalizing separators according to JPMS rules.

For example, the file `example-util-1.0.jar` may be derived as `example.util`. If the manifest specifies `Automatic-Module-Name: com.example.util`, the module name is **`com.example.util`**, regardless of whatever version the JAR file name contains.

| Scenario | Module Name Used |
| --- | --- |
| JAR has `module-info.class` | Name in the `module ... { }` statement of the module descriptor |
| JAR has no descriptor, manifest has `Automatic-Module-Name` | Value of `Automatic-Module-Name` |
| JAR has no descriptor and lacks the attribute above | Name derived from the JAR file name |

**Note:** When a JAR already has a real module descriptor, the name in the descriptor takes effect; the manifest does not rename an explicit module. The `Automatic-Module-Name` attribute also does not turn a JAR into an explicit module.

## 3. Declaring Automatic-Module-Name in MANIFEST.MF

Suppose a library has classes in the package `com.example.util`, packaged as `example-util-1.0.jar`. We want applications to always refer to the library by the module name `com.example.util`.

The minimal manifest content can be:

```text
Manifest-Version: 1.0
Automatic-Module-Name: com.example.util

```

The attribute must be in the **main section** of `META-INF/MANIFEST.MF`. The trailing blank line terminates the section. When using JAR packaging tools, let the tool generate and normalize the manifest rather than arbitrarily editing files inside the JAR.

The module name `com.example.util` is a valid Java name, using dots for hierarchy. You should follow the reverse-domain naming convention just like package names. Names containing hyphens, spaces, or components that are not valid Java identifiers are unsuitable as module names.

This name is part of the **library's public contract**: once applications have written `requires com.example.util;`, changing the module name will force application code to be updated accordingly.

### Manual Packaging with jar

Suppose the `.class` files have been compiled into the `build/util-classes` directory, and the manifest content is in the file `manifest.mf`:

```bash
jar --create --file example-util-1.0.jar --manifest manifest.mf -C build/util-classes .
```

The resulting JAR must have the manifest declaring the name above and contain the library classes. Place that JAR on the module path so Java recognizes it as an automatic module.

### Maven Configuration

For a project with `jar` packaging, you can configure `maven-jar-plugin` in `pom.xml`:

```xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-jar-plugin</artifactId>
      <configuration>
        <archive>
          <manifestEntries>
            <Automatic-Module-Name>com.example.util</Automatic-Module-Name>
          </manifestEntries>
        </archive>
      </configuration>
    </plugin>
  </plugins>
</build>
```

After packaging, inspect the **final published JAR**. If your build pipeline includes steps to create a fat JAR, shading, or repackaging, make sure the manifest in the final artifact still preserves this attribute.

### Gradle Configuration (Groovy DSL)

In `build.gradle`:

```groovy
tasks.withType(Jar).configureEach {
    manifest {
        attributes('Automatic-Module-Name': 'com.example.util')
    }
}
```

If the project has multiple JAR-building tasks, inspect the manifest of the exact artifact that users download.

## 4. Using That Name from an Explicit Module

Suppose the library has the class:

```java
package com.example.util;

public final class Texts {
    private Texts() {}

    public static String trimToEmpty(String input) {
        return input == null ? "" : input.trim();
    }
}
```

The application has the module descriptor `src/app/module-info.java` as follows:

```java
module com.example.app {
    requires com.example.util;
}
```

The application's main class:

```java
package com.example.app;

import com.example.util.Texts;

public class Main {
    public static void main(String[] args) {
        System.out.println(Texts.trimToEmpty("  Hello JPMS  "));
    }
}
```

Here `requires com.example.util;` references the **module name in the manifest**, not the Maven artifact name, the full JAR file name, or the package name of any arbitrary class.

Example running on an environment with JDK 9 or later, when `libs/` contains `example-util-1.0.jar` and the source layout matches the paths above:

```bash
javac --module-path libs -d build/app-classes src/app/module-info.java src/app/com/example/app/Main.java
java --module-path "libs:build/app-classes" --module com.example.app/com.example.app.Main
```

Expected output:

```text
Hello JPMS
```

In the `java` command, `:` separates multiple module path entries on Linux/macOS; on Windows, replace it with `;`. The automatic module name participates in JPMS only when the JAR is on the **module path**. When the same JAR is on the **classpath**, the JVM handles it via the traditional classpath mechanism and does not require `requires` for that JAR.

## 5. Verifying the Actual Module Name

You should not guess the module name from the file name or published library name. Use the tool included with the JDK:

```bash
jar --describe-module --file example-util-1.0.jar
```

For a JAR that has no `module-info.class` yet has a manifest declaring the name, the tool will describe an **automatic module** named `com.example.util`. The exact formatting of the output lines may vary between JDK versions; the information to verify is the **module name** and the **automatic status**.

You can view the manifest directly with a JAR/ZIP extraction tool to confirm that the `META-INF/MANIFEST.MF` entry contains the line:

```text
Automatic-Module-Name: com.example.util
```

Verify this on the **actual JAR placed on the module path**, especially when the project has `sources` or `tests` packages, renamed distributions, or a multi-step packaging process.

## 6. What Automatic-Module-Name Does and Does Not Do

- **Stabilizes the name to depend on:** instead of writing `requires example.util;` based on a derived filename, applications can use `requires com.example.util;` consistently across JAR versions.
- **Supports migration to JPMS:** a library without a descriptor can still be used by modular applications during the transition phase.
- **Does not define the library's dependencies:** merely having a name in the manifest does not create `requires`, `exports`, or `opens` clauses as an explicit module would.
- **Does not automatically modularize the library:** JPMS treats an automatic module permissively, such as reading other modules and exporting its own packages, for compatibility with legacy code. That mechanism differs from intentionally declaring readability, exported packages, and opened packages in `module-info.java`.
- **Does not merge package names and module names into one:** a module name is often close to the library's namespace, but it is a separate identity. A single module can contain multiple packages.

When the library transitions to an explicit module in a later release, you should keep the exact name `com.example.util` in the descriptor:

```java
module com.example.util {
    exports com.example.util;
}
```

As a result, applications that already wrote `requires com.example.util;` can keep the dependency name unchanged. However, migrating to an explicit module can still change package accessibility and dependency requirements, so compatibility impacts must be evaluated separately.

## 7. Common Errors and How to Identify the Cause

### Error: module not found: com.example.util

Common causes:
- The JAR was not properly placed on the module path during compilation/execution.
- The manifest of the final artifact does not contain `Automatic-Module-Name` as expected.
- The name in `requires` differs from the JAR's actual name (for example, using `example.util` while the manifest specifies `com.example.util`).

How to fix: run `jar --describe-module --file ...` on the exact JAR, then compare the name with `module-info.java` and the `--module-path` option.

### Error Due to Duplicate Module Names

Two different JARs declaring the same `Automatic-Module-Name: com.example.util` cannot represent two separate modules with the same name in a resolved module configuration. Ensure each library has a unique module identity; audit JAR versions placed on the same module path.

### Error Due to an Invalid Name

A value such as `example-util` contains a hyphen and is therefore not a valid Java module name. Choose a name like `com.example.util`, repackage, and verify the result with `jar --describe-module`.

### Errors from Split Packages or Incompatible Dependencies

Creating a stable module name does not resolve all module path conflicts. If two modules provide the same package or a legacy library depends on code not properly arranged on the classpath/module path, resolution or compilation can still fail. In that case, inspect the **package structure and dependency graph**, rather than only fixing the manifest name.

## 8. When Should You Declare This Attribute?

Authors of **JAR libraries without a module descriptor** should consider declaring `Automatic-Module-Name` early, especially when the library has users migrating their applications to JPMS. A clear, stable name reduces the risk of the derived name changing when `artifactId`, file naming, or release processes change.

Recommended workflow:

1. Choose a module name under a stable namespace, such as `com.example.util`.
2. Add `Automatic-Module-Name` to the manifest of the distributed JAR.
3. Package the release and confirm the name with `jar --describe-module`.
4. Use that exact name in `requires` within modular applications.
5. When adding `module-info.java` to the library, continue using the previous name and explicitly review the `requires`, `exports`, and `opens` directives needed.

## 9. Practice Exercises

**Exercise 1.** You have a file `client-tools-2.3.jar` without a descriptor, whose manifest specifies `Automatic-Module-Name: vn.example.client.tools`. What does the application need to declare?

```java
module vn.example.app {
    requires vn.example.client.tools;
}
```

**Exercise 2.** A team renames `client-tools-2.3.jar` to `client-tools-2.4.jar` while keeping the manifest from Exercise 1. Does the module name change?

**No.** As long as the JAR remains an automatic module, the name from the manifest is still `vn.example.client.tools`.

**Exercise 3.** If `Automatic-Module-Name` is removed and the JAR is kept on the module path, is the name still guaranteed to be `vn.example.client.tools`?

**No.** Java will derive the name from the JAR file name according to JPMS rules; this name may differ from the name already used in `requires` statements.

## Key Takeaways

`Automatic-Module-Name` is an attribute in the **manifest of a non-modularized JAR** that publishes a **stable automatic module name**. Java prioritizes this name over the name derived from the JAR file when the library is placed on the **module path**. Use `jar --describe-module` to verify and reference the exact name in `requires`.