# Deriving the Automatic Module Name from the JAR File Name

A JAR without a module-info.class file can still be placed on the module path and used as an **automatic module**. In that case, JPMS needs a module name so other named modules can declare requires on it.

The automatic module name is determined in order of precedence: if the manifest has a valid **Automatic-Module-Name** attribute, Java uses that name; otherwise, Java derives the name from the JAR file name. Therefore, the artifact file name can directly affect the module name seen by the compiler and the JVM.

Understanding this rule helps avoid module not found errors, avoid duplicate module names, and keep the application's module descriptor stable when libraries are upgraded.

## 1. What Is an Automatic Module?

A regular JAR can contain classes and resources without having a module descriptor. When that JAR is placed on the **module path**, Java can treat it as an automatic module.

Example:

~~~text
libs/
└── commons-lang3-3.12.0.jar
~~~

The JAR above does not have module-info.class. When placed on the module path, it can be recognized as an automatic module with a name derived from the artifact.

A named module can declare a dependency on an automatic module:

~~~java
module com.example.app {
    requires commons.lang3;
}
~~~

This serves as an important bridge when an application begins using JPMS while some libraries have not yet released modular JARs.

The location of the JAR determines how Java treats it:

| JAR Location | How Java Treats the JAR |
| --- | --- |
| On the module path, with module-info.class | Named module with an explicit descriptor. |
| On the module path, without module-info.class | Automatic module, name taken from manifest or file name. |
| On the classpath | Contents belong to the unnamed module; no automatic module name to requires. |

Simply placing a JAR on the classpath does not create an automatic module. If a named module needs to declare requires on a library, the library must be included in the module path configuration and have a valid module name.

## 2. Precedence Order When Determining the Name

Java determines the module name in two cases:

1. **Automatic-Module-Name present in the manifest:** use the value of this attribute.
2. **Attribute absent:** derive the name from the JAR file name according to automatic module rules.

If the JAR already has module-info.class, the module name is declared in the explicit descriptor. Automatic-Module-Name does not override the name in module-info.class.

The manifest is located inside the JAR at:

~~~text
META-INF/MANIFEST.MF
~~~

Example manifest:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: org.example.payment
~~~

When this JAR is placed on the module path and lacks module-info.class, the module name is org.example.payment, regardless of what the artifact file name is.

The requires declaration must use the module name:

~~~java
module com.example.checkout {
    requires org.example.payment;
}
~~~

It does not use the groupId, Maven artifactId, or the full JAR file name unless those values happen to match the module name.

## 3. Rules for Deriving the Name from the JAR File Name

When the manifest does not provide Automatic-Module-Name, Java derives the name from the basename of the JAR file. You can picture the process in these steps:

1. Strip the .jar extension.
2. Detect and strip the trailing version suffix if that suffix matches a recognized version pattern, typically starting with a hyphen followed by digits.
3. Replace sequences of non-alphanumeric characters with dots.
4. Collapse consecutive dots into a single dot.
5. Strip leading and trailing dots from the name.

The result must be a valid module name. You should not write your own approximate algorithm and use its result instead of the module name the JDK actually recognizes; verify using the jar tool.

### 3.1. Common Name Examples

| JAR File Name | Commonly Derived Automatic Module Name |
| --- | --- |
| commons-lang3-3.12.0.jar | commons.lang3 |
| jackson-databind-2.17.2.jar | jackson.databind |
| my-library-1.2.0.jar | my.library |
| my_library-1.2.0.jar | my.library |
| my-library.jar | my.library |
| guava-33.0-jre.jar | guava |

Hyphens and underscores are converted into dots. Recognized version suffixes are stripped before normalizing separators.

The example names in the table illustrate typical derivations. For actual artifacts, use jar --describe-module to confirm the result recognized by the JDK.

### 3.2. Version Suffixes

A trailing version part in the file name usually does not become part of the module name.

Example:

~~~text
my-library-1.0.jar
my-library-1.2.3.jar
my-library-2.0-SNAPSHOT.jar
~~~

The names above usually derive the same module name:

~~~text
my.library
~~~

This allows upgrading from version 1.0 to 1.2.3 without modifying requires in module-info.java, provided the artifact continues following the naming convention and does not change an explicit module name.

However, not every version-like string is recognized the same way. For instance, a suffix that does not start with a recognized version pattern may be retained and normalized into part of the name. Do not rely on arbitrary naming conventions if the module name must remain stable.

### 3.3. Separator Characters Are Normalized

Separator characters such as hyphens, underscores, or repeated dots can be normalized into dots. Example:

~~~text
my-library.jar
my_library.jar
my..library.jar
~~~

These names can all lead to:

~~~text
my.library
~~~

As a result, two artifacts with different file names can still produce the same module name. When both appear together on the module path, the JVM may report duplicate modules.

## 4. Automatic-Module-Name in the Manifest

For libraries that are released regularly, you should set Automatic-Module-Name in the manifest to publish a stable name.

Example:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: org.example.customer
~~~

Suppose the artifact is released under the names:

~~~text
customer-1.0.0.jar
customer-1.1.0.jar
customer-2.0.0.jar
~~~

If the manifest of each version declares:

~~~text
Automatic-Module-Name: org.example.customer
~~~

then the module name remains org.example.customer when the file name changes.

The consuming module only needs:

~~~java
module com.example.app {
    requires org.example.customer;
}
~~~

This is better than forcing every user to rely on the artifact name to guess the module name. It also allows publishers to change the artifactId, add classifiers, or adjust file naming conventions without necessarily changing the module name.

### 4.1. Creating the Manifest When Packaging a JAR

You can create a manifest file:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: org.example.customer

~~~

When using the jar tool:

~~~bash
jar --create --file customer.jar --manifest MANIFEST.MF -C classes .
~~~

With Gradle, you can set the manifest attribute for the JAR packaging task:

~~~groovy
tasks.named('jar') {
    manifest {
        attributes(
            'Automatic-Module-Name': 'org.example.customer'
        )
    }
}
~~~

If the project uses a different build configuration, set the attribute in the manifest of the exact artifact that is published. Inspect the output JAR after building, not just the source configuration.

## 5. Why Can Derived Names Be Surprising?

The derived name depends on the basename of the JAR. Therefore, changes in how the artifact is packaged can alter the module name or create conflicts.

### 5.1. Renaming the Artifact

Suppose you initially have:

~~~text
customer-client.jar
~~~

Derived name:

~~~text
customer.client
~~~

Later the artifact is renamed to:

~~~text
customer-sdk.jar
~~~

The derived name may become:

~~~text
customer.sdk
~~~

If the module descriptor still declares:

~~~java
requires customer.client;
~~~

the compiler or JVM will not find the old module name if no artifact still provides that name.

Renaming a file might look like a distribution-only operation, but for an automatic module without Automatic-Module-Name, it can become a module-level compatibility break.

### 5.2. Two Versions Appearing Together

Example:

~~~text
libs/
├── customer-client-1.0.jar
└── customer-client-2.0.jar
~~~

Both can derive the same name customer.client. The module path is not a place to put multiple versions of the same automatic module simultaneously and expect the JVM to pick the right version per consumer.

Choose one version for the module configuration and remove the duplicate artifact. Use Gradle or Maven dependency management to resolve versions before running.

### 5.3. Classifiers Can Affect the Name

Example:

~~~text
customer-client-tests-1.0.jar
customer-client-1.0-tests.jar
~~~

The position of the classifier and version in the file name can produce different derived results. With the first name, the tests part may become a component of the module name; with the second name, the version suffix may cause the trailing part to be stripped along with the version.

You should not assume secondary artifacts such as tests, sources, javadoc, or all have the same module name as the main JAR. Inspect each JAR individually if they are placed on the module path.

### 5.4. Invalid or Unexpected Derived Names

A file name may contain leading/trailing separators, digits, or unusual character sequences. After normalization, the result might not be a valid module name or might not match the name you expected.

If the JDK cannot construct an automatic module descriptor from the file name, module discovery or resolution may fail. Prefer a clear file name or declare a stable Automatic-Module-Name in the manifest if you maintain the library.

## 6. Inspecting the Module Name the JDK Actually Uses

Do not just look at the file name. Use the JDK tool:

~~~bash
jar --describe-module --file libs/customer-client-1.0.jar
~~~

For a JAR without a descriptor and without Automatic-Module-Name, the output usually indicates that it is a derived automatic module and displays the derived name.

For a JAR with Automatic-Module-Name, the output displays the module name declared in the manifest.

You can inspect the entries inside the JAR with:

~~~bash
jar --list --file libs/customer-client-1.0.jar
~~~

The command above lists entries in the JAR, including the META-INF/MANIFEST.MF path. To read the manifest contents, you can extract that entry separately into a temporary directory or use an appropriate ZIP inspection tool; avoid overwriting files in the current workspace.

When you need to see the observable modules in the runtime environment:

~~~bash
java --module-path libs --list-modules
~~~

And to observe module resolution when launching the application:

~~~bash
java --show-module-resolution --module-path libs:mods \
    -m com.example.app/com.example.app.Main
~~~

On Windows, the separator between module path entries is a semicolon. Always run commands under the exact JDK and configuration that the application uses in deployment.

## 7. Using the Module Name in module-info.java

Suppose the JAR commons-lang3-3.12.0.jar is recognized with the name commons.lang3. A named module can declare:

~~~java
module com.example.text {
    requires commons.lang3;
}
~~~

The name after requires must be the module name, not the file name:

~~~java
// Do not use the file name:
requires commons-lang3-3.12.0;

// Use the verified module name:
requires commons.lang3;
~~~

The example above only illustrates syntax; the actual name must be verified with jar --describe-module on the exact artifact being used.

An automatic module generally reads other modules in the configuration and exports all of its packages. Therefore, it makes legacy libraries easy to use from named modules, but it does not create strict API boundaries like a named module with a well-designed module-info.java.

## 8. How Does an Automatic Module Differ from an Explicit Named Module?

| Characteristic | Automatic Module | Named Module with module-info.java |
| --- | --- | --- |
| Source of name | Manifest or JAR file name | module directive in module-info.java |
| Dependencies | Broad readability of other modules | Declared via requires |
| API packages | Exports all packages | Exports only selected packages |
| Reflection | Packages are opened for deep reflection | Only opens necessary packages |
| Typical role | Bridge for legacy libraries | Module design with explicit boundaries |

Automatic modules are useful during the transition phase, but they should not be treated as the final packaging configuration for every library. Whenever possible, publishers should add a real module descriptor to control dependencies, API packages, and reflection.

## 9. Common Errors When Deriving Names

| Symptom | Possible Cause | How to Fix |
| --- | --- | --- |
| module not found | requires uses a different name from the one derived by the JDK | Run jar --describe-module and fix requires. |
| Duplicate module or duplicate module error | Two JARs derive the same module name | Remove the duplicate artifact/version from the module path. |
| Version change breaks the build | Artifact name changed, changing the module name | Use a stable Automatic-Module-Name or keep a consistent naming convention. |
| JAR runs on classpath but cannot be used with requires | On the classpath it belongs to the unnamed module | Move the JAR to the module path and verify the automatic module name. |
| Classifier JAR produces an unexpected module name | Classifier and version are in different positions | Inspect each JAR individually with the jar tool. |
| Invalid derived name | Basename produces an invalid module name | Change the artifact naming convention or set Automatic-Module-Name. |

## 10. Diagnostic and Resolution Workflow

When a named module reports a missing dependency or the module name changes after a library upgrade:

1. Locate the exact JAR file that the build or runtime is using.
2. Run jar --describe-module --file path/to/library.jar.
3. Determine whether the JAR has module-info.class, Automatic-Module-Name, or has its name derived from the file.
4. Compare the resulting module name with the name after requires in module-info.java.
5. Check whether the module path contains multiple versions or classifier artifacts with the same module name.
6. If you maintain the library, consider publishing a stable Automatic-Module-Name or moving to an explicit module descriptor.
7. Re-run compile and runtime using the exact deployment configuration.

If the module name only changed because of the file name, you can update requires to match the new name. However, for publicly released libraries, it is better to stabilize the name via manifest or descriptor so consumers do not have to change source code on every artifact rename.

## 11. Principles for Stable Naming

- Prefer a meaningful and stable module name, typically following reverse-domain naming.
- If you publish an unmodularized library and want to support the module path, declare Automatic-Module-Name in the manifest.
- Do not include version numbers in Automatic-Module-Name.
- Do not rely on classifiers or temporary file names to determine module names.
- Verify the module name of every JAR placed on the module path.
- Avoid placing two versions with the same module name in a single module configuration.
- When possible, migrate from an automatic module to a named module with an explicit descriptor to control requires, exports, and opens.

## 12. Self-Check

**Scenario 1:** A JAR named commons-lang3-3.12.0.jar has no module-info.class and its manifest has no Automatic-Module-Name. What do you need to do to know the module name?

Answer: use jar --describe-module --file commons-lang3-3.12.0.jar to see the automatic module name actually derived by the JDK. Do not guess the name solely from artifactId.

**Scenario 2:** You rename the file from customer-client.jar to customer-sdk.jar, and then requires customer.client reports module not found. Why?

Answer: without Automatic-Module-Name, the module name is derived from the file name. The derived name may have changed to customer.sdk. Declaring a stable Automatic-Module-Name avoids depending on the file name.

**Scenario 3:** Two versions library-1.0.jar and library-2.0.jar are both on the module path. Why might an error occur?

Answer: both may derive the same module name library. A module configuration cannot treat them as two independent modules merely because their file names differ. Choose a single version.

**Scenario 4:** A library works when placed on the classpath, yet a named module cannot declare requires on it. Why?

Answer: on the classpath, the JAR belongs to the unnamed module and has no module name for requires. Move the JAR to the module path so Java recognizes it as an automatic module, or add an appropriate module descriptor.

**Scenario 5:** A JAR has Automatic-Module-Name and its file name is changed. Does the module name necessarily change?

Answer: no. If the JAR still has no module-info.class and the manifest preserves the valid Automatic-Module-Name, the automatic module name continues to come from the manifest. Verify with the jar tool after packaging.