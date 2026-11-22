# Manifest in JAR

**Manifest** is a metadata file located inside a JAR package at the path `META-INF/MANIFEST.MF`. It describes information about the archive and its internal components, such as the entry-point class, dependency classpath, product version, vendor, package attributes, module information, or digests used for JAR signing.

The manifest is part of the JAR format, not Java code, and not a standalone JVM configuration file. Tools such as `jar`, `java`, `jarsigner`, and the `java.util.jar` API use the manifest according to different rules.

## 1. Location and Role of MANIFEST.MF

A JAR has a ZIP structure. The standard manifest is located at:

```text
META-INF/MANIFEST.MF
```

Example structure of a packaged application:

```text
app.jar
├── META-INF/
│   └── MANIFEST.MF
└── com/
    └── example/
        ├── Main.class
        └── Greeting.class
```

The manifest can provide information such as:

- The manifest format version via `Manifest-Version`.
- The class containing the program entry point via `Main-Class`.
- Dependent JARs/directories via `Class-Path`.
- Product information such as `Implementation-Title`, `Implementation-Version`, and `Implementation-Vendor`.
- The automatic module name via `Automatic-Module-Name`.
- How packages or multi-version archives are handled via `Sealed` and `Multi-Release`.
- Digest information for entries in the JAR signing process.

The manifest does not itself contain all dependencies, nor does it replace source code, bytecode, build configuration, or application security mechanisms. It is metadata interpreted by tools and the runtime by convention.

## 2. Basic Manifest Structure

A manifest is a text file consisting of headers in the form:

```text
Attribute-Name: Attribute-Value
```

Example:

```text
Manifest-Version: 1.0
Main-Class: com.example.Main
Implementation-Title: Java Tooling Demo
Implementation-Version: 1.0.0

```

Some important rules:

- A header consists of an attribute name, a colon, a single space, and a value.
- Attribute names are case-insensitive.
- Attribute values are preserved as written; you should not assume values are case-insensitive as well.
- Headers in the main section are terminated by a blank line.
- A manifest can have multiple sections, with each section starting with a `Name` header specifying the entry to which the section applies.
- If `Manifest-Version` appears, it must be the first header in the main section.
- Lines in a manifest are limited in length by bytes; when a line is too long, it must be wrapped according to the continuation rule.

Manifests are typically written in UTF-8. The maximum length of a line is 72 bytes, excluding line-ending characters. If a value is longer, continue on the next line with a single leading space. The leading space on the continuation line is not part of the value's content; when read, the parts are concatenated.

Example of a wrapped long value:

```text
Implementation-Title: Java Core JDK Tooling Learning Application
Implementation-Version: 1.0.0
```

For values longer than 72 bytes, the manifest-generating tool should handle line wrapping automatically. If writing a manifest by hand, make sure the continuation is properly formatted, especially when Vietnamese characters are present because a single Unicode character can occupy multiple UTF-8 bytes.

## 3. Main Section and Per-Entry Sections

A manifest has two main scopes.

### 3.1. Main section

The main section sits at the top of the file and contains attributes that apply globally to the archive. Example:

```text
Manifest-Version: 1.0
Main-Class: com.example.Main
Implementation-Title: Example Application
Implementation-Version: 2.4.0
Implementation-Vendor: Example Team

```

Attributes such as `Main-Class`, `Class-Path`, and `Multi-Release` usually reside in the main section.

### 3.2. Per-entry sections

After the blank line terminating the main section, a manifest may contain sections dedicated to individual entries in the JAR. Each section starts with a `Name` header:

```text
Manifest-Version: 1.0
Implementation-Title: Example Application

Name: com/example/Main.class
SHA-256-Digest: <digest-value>

Name: com/example/
Sealed: true

```

The first section in the example above is associated with the entry `com/example/Main.class`; the second section can be used to set attributes for the `com.example` package.

When an attribute appears in both the main section and a specific section, the value in the specific section takes precedence for the corresponding entry. This organization is useful for package attributes, sealing, and entry-level digests.

Entry names use internal JAR paths with forward slashes `/`, not operating system paths. For example, `com/example/Main.class` is a valid entry name; `com\example\Main.class` is not standard in a manifest.

## 4. Creating an Executable JAR with Main-Class

The `Main-Class` attribute specifies the class containing the entry-point method that the `java -jar` command will invoke. The value is the fully qualified class name (binary name), including the package, without the `.class` extension.

Example:

```text
Main-Class: com.example.Main
```

That class needs an entry point compatible with the target Java version, for example:

```java
package com.example;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from executable JAR");
    }
}
```

Suppose the class file is in the `out` directory:

```text
out/
└── com/
    └── example/
        └── Main.class
```

You can create the JAR and set `Main-Class` directly with the `jar` tool:

```sh
jar --create --file app.jar --main-class com.example.Main -C out .
```

Or create a `manifest.mf` file:

```text
Manifest-Version: 1.0
Main-Class: com.example.Main

```

Then use the manifest file when packaging:

```sh
jar --create --file app.jar --manifest manifest.mf -C out .
```

Check the entry list:

```sh
jar --list --file app.jar
```

Run the application:

```sh
java -jar app.jar
```

Output:

```text
Hello from executable JAR
```

If the manifest does not have `Main-Class`, `java -jar app.jar` typically reports an error indicating there is no main manifest attribute. If the class name is wrong or the class file is not packaged, the JVM will be unable to load the startup class.

`Main-Class` only declares the entry point. It does not turn the JAR into a native executable, nor does it automatically include external dependencies inside the JAR.

## 5. Class-Path: Declaring Dependent Libraries

The `Class-Path` attribute in the main section lists the URLs that the class loader uses to locate additional classes when running an executable JAR. Entries are separated by spaces.

Example structure:

```text
dist/
├── app.jar
└── lib/
    ├── commons.jar
    └── logging.jar
```

Manifest in `app.jar`:

```text
Manifest-Version: 1.0
Main-Class: com.example.Main
Class-Path: lib/commons.jar lib/logging.jar

```

When running:

```sh
java -jar dist/app.jar
```

Relative URLs in `Class-Path` are resolved against the URL/location of the JAR containing the manifest. Therefore, `lib/commons.jar` in the example above is resolved relative to the directory containing `app.jar`.

Important notes:

- `Class-Path` only references external dependencies; it does not copy or package those JARs into the archive.
- Entries are separated by spaces, not colons or semicolons like the `CLASSPATH` environment variable.
- Paths containing spaces must be properly URL-encoded, for example using `%20`, instead of writing a literal space that causes the parser to treat it as two separate entries.
- Relative paths will break if you move the JAR without moving the dependency directory in the same structure.
- Dependencies must actually be present and readable at runtime.
- When using `java -jar`, external classpath options such as `-cp` are not used as the application classpath in place of the `-jar` mode configuration; declare dependencies using an appropriate packaging approach.

You can inspect dependencies and the actual classpath at runtime using `-verbose:class`:

```sh
java -verbose:class -jar app.jar
```

The logs will show which source each class is loaded from, which is useful when investigating missing or conflicting dependencies.

## 6. Commonly Used Manifest Attributes

Some common attributes in the main section:

| Attribute | Meaning |
|---|---|
| `Manifest-Version` | Manifest format version; usually `1.0` |
| `Main-Class` | Name of the class containing the entry point when running with `java -jar` |
| `Class-Path` | List of additional dependency URLs |
| `Created-By` | Tool that created the archive/manifest |
| `Build-Jdk-Spec` | Java specification version of the JDK used to build |
| `Implementation-Title` | Name of the product or implementation |
| `Implementation-Version` | Version of the implementation |
| `Implementation-Vendor` | Vendor of the implementation |
| `Specification-Title` | Name of the specification that the JAR implements |
| `Specification-Version` | Specification version |
| `Specification-Vendor` | Specification vendor |
| `Automatic-Module-Name` | Stable module name for the JAR when used on the module path without an explicit module descriptor |
| `Multi-Release` | Marks the JAR as containing content for multiple Java versions |
| `Sealed` | Sets default package sealing for packages in the archive |

You can add application-specific attributes, but you should use clear names and avoid colliding with standard names. Custom attributes have no built-in meaning to the JVM; the application or tool must actively read and interpret them.

## 7. Reading a Manifest in Java

Java provides an API in the `java.util.jar` package to read a manifest without manually extracting or parsing text.

Example:

```java
import java.io.IOException;
import java.util.jar.Attributes;
import java.util.jar.JarFile;
import java.util.jar.Manifest;

public class ReadManifest {
    public static void main(String[] args) throws IOException {
        try (JarFile jar = new JarFile("app.jar")) {
            Manifest manifest = jar.getManifest();

            if (manifest == null) {
                System.out.println("No manifest");
                return;
            }

            Attributes attributes = manifest.getMainAttributes();

            System.out.println(
                attributes.getValue(Attributes.Name.MAIN_CLASS)
            );
            System.out.println(
                attributes.getValue("Implementation-Version")
            );
        }
    }
}
```

If the manifest contains:

```text
Manifest-Version: 1.0
Main-Class: com.example.Main
Implementation-Version: 2.4.0

```

Output:

```text
com.example.Main
2.4.0
```

`JarFile.getManifest()` returns a `Manifest` object, or `null` if the archive has no manifest. `getMainAttributes()` retrieves the main attributes. To read the section for a specific entry, use:

```java
Attributes entryAttributes =
    manifest.getAttributes("com/example/Main.class");
```

The entry name passed in must match the internal path inside the JAR. The returned value may be `null` if there is no section for that entry.

## 8. Creating a Manifest with Maven

With Maven, configure `maven-jar-plugin` to add `Main-Class` and other attributes:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-jar-plugin</artifactId>
            <version>3.4.2</version>
            <configuration>
                <archive>
                    <manifest>
                        <mainClass>com.example.Main</mainClass>
                    </manifest>
                    <manifestEntries>
                        <Implementation-Title>Java Tooling Demo</Implementation-Title>
                        <Implementation-Version>1.0.0</Implementation-Version>
                        <Implementation-Vendor>Example Team</Implementation-Vendor>
                    </manifestEntries>
                </archive>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Build:

```sh
mvn clean package
```

The JAR is created in the `target` directory with the manifest configured by the plugin. The file name is usually based on the Maven project's `artifactId` and `version`.

The Maven JAR Plugin packages the project's classes/resources as configured; configuring `Main-Class` does not automatically include all runtime dependencies inside the JAR. If you want to distribute a JAR containing dependencies, you need an appropriate packaging approach such as a shaded/uber JAR, or distribute dependencies alongside it and configure the classpath.

## 9. Creating a Manifest with Gradle

With the Gradle Groovy DSL, you can set attributes on the `jar` task:

```groovy
tasks.jar {
    manifest {
        attributes(
            'Main-Class': 'com.example.Main',
            'Implementation-Title': 'Java Tooling Demo',
            'Implementation-Version': '1.0.0',
            'Implementation-Vendor': 'Example Team'
        )
    }
}
```

Run:

```sh
./gradlew clean jar
```

On Windows:

```powershell
gradlew.bat clean jar
```

The JAR is usually located in `build/libs`. Inspect the manifest:

```sh
jar --extract --file build/libs/app.jar META-INF/MANIFEST.MF
```

After extracting the manifest entry, read the `META-INF/MANIFEST.MF` file. The actual JAR name depends on the project configuration.

Configuring `Main-Class` only specifies the entry point. If the project has runtime dependencies, you need an appropriate distribution approach: place the dependency JARs alongside the application and declare `Class-Path`, build a fat JAR using a plugin, or use your framework's packaging mechanism. Do not assume the default `jar` task packages dependencies automatically.

## 10. Multi-Release JAR

A multi-release JAR allows a single archive to contain different versions of classes/resources for different Java releases. The manifest needs:

```text
Manifest-Version: 1.0
Multi-Release: true

```

Version-specific classes are placed under:

```text
META-INF/versions/<N>/
```

Example:

```text
library.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── versions/
│       ├── 9/
│       │   └── com/example/PlatformHelper.class
│       └── 17/
│           └── com/example/PlatformHelper.class
└── com/
    └── example/
        └── PlatformHelper.class
```

When running on a Java release that supports multi-release JARs, the runtime selects the highest matching versioned entry that does not exceed the running Java version; if no matching entry exists, it falls back to the version at the root of the archive. The JAR must have `Multi-Release: true`; if it is missing or not `true`, the versioned directories are not treated as alternative classes under the multi-release mechanism.

This mechanism is useful when a library wants to optimize for newer APIs while still keeping a baseline implementation compatible with older Java versions. Class versions in versioned directories must follow the compatibility rules of the JAR specification and must not alter the public API in a way that surprises users.

## 11. Package Sealing

Package sealing is a mechanism for declaring that classes belonging to a package must be loaded from the same JAR/code source according to class loader rules. It helps prevent mixing classes of the same package from different archives in cases where package integrity needs to be protected.

To seal all packages in a JAR, put this in the main section:

```text
Manifest-Version: 1.0
Sealed: true

```

To seal only one package, use a per-package section:

```text
Manifest-Version: 1.0

Name: com/example/
Sealed: true

```

The `Sealed` attribute in a specific section can override the default value in the main section for that package. If a class in the same package is loaded from another source after the package has been sealed, the class loader may throw a `SecurityException` with a sealing violation message.

Sealing does not replace digital signatures, access control, or sandboxing. It is a rule about the origin of classes within a package, enforced by the class loader when defining the package.

## 12. Manifest and JAR Signing

The JAR signing process uses the manifest together with signature files in `META-INF`. Typically, there are:

```text
META-INF/
├── MANIFEST.MF
├── SIGNER.SF
└── SIGNER.RSA
```

The name and extension of the signature block depend on the algorithm/certificate, such as `.RSA`, `.DSA`, or `.EC`.

The manifest can contain digests for individual entries. The `.SF` signature file contains digests related to the manifest or sections of the manifest; the signature block contains the cryptographic signature of the signature file. Verification tools use this data to detect modifications to signed content.

You can verify a JAR with:

```sh
jarsigner -verify -verbose -certs app.jar
```

Notes:

- Simply adding `Main-Class` or `Implementation-Version` does not mean the JAR is signed.
- The manifest does not by itself guarantee the authenticity of the archive.
- Modifying or repackaging a signed JAR can invalidate digests/signatures.
- Finalize the contents, manifest, and dependencies first, and only sign afterward.
- Do not treat a successful verify command as a complete assessment of the publisher's trustworthiness; check the certificate, trust chain, and deployment policy.

Do not modify the manifest of a signed JAR and continue distributing it as if the old signature were still intact. If you change the archive contents, re-run the signing process with a valid key and certificate.

## 13. Inspecting the Manifest in a JAR

You can use the `jar` tool to list and extract the manifest:

```sh
jar --list --file app.jar
jar --extract --file app.jar META-INF/MANIFEST.MF
```

The first command lists the entries in the JAR. The second extracts the manifest to `META-INF/MANIFEST.MF` under the current directory. If the destination path already exists, be careful not to overwrite a file you need to keep.

You can read the manifest contents without extracting the entire JAR using a ZIP utility such as `unzip -p` if available:

```sh
unzip -p app.jar META-INF/MANIFEST.MF
```

Or use the Java `JarFile` API as shown earlier.

When inspecting a JAR generated automatically by Maven/Gradle, do not look only at the configuration in the build file. Inspect the actual manifest in the produced artifact, because plugins, other tasks, or the packaging pipeline may add or override attributes.

## 14. Common Errors

| Symptom | Common Cause | How to Fix |
|---|---|---|
| `no main manifest attribute` | The JAR does not have `Main-Class` in the main section | Add `Main-Class` and rebuild the JAR |
| `Could not find or load main class` | Incorrect `Main-Class` name or the class file is not inside the archive | Check the fully qualified name and list the JAR with `jar --list` |
| `ClassNotFoundException` for a dependency | Missing JAR in `Class-Path` or incorrect relative URL | Check the dependency location relative to the JAR and the manifest contents |
| Runs with `java -cp` but fails with `java -jar` | `-jar` mode uses its own manifest/entry point; an external classpath does not replace the manifest | Set `Main-Class` and dependencies properly in the manifest or package dependencies |
| Manifest attribute has no effect | Placed in the wrong section, misspelled header name, or reading the wrong artifact | Check the attribute location, entry name, and actual manifest |
| Manifest rejected by parser | Malformed line, missing space after colon, or improper line wrapping | Follow header and continuation syntax; prefer manifest-generating tools |
| Dependencies not found after moving the application | `Class-Path` uses relative paths to the old location | Move the entire dependency directory with the same structure or package differently |
| `SecurityException: sealing violation` | A class in the same package was loaded from a different source than the sealed package | Check manifest sealing and how packages are split across JARs |
| JAR signature invalid | Contents/manifest were modified after signing or digests do not match | Finish packaging completely, then re-sign and verify |
| Newer class version in multi-release JAR not selected | Missing `Multi-Release: true`, wrong version directory, or unsupported runtime | Check the manifest, `META-INF/versions/N` path, and JVM version |

## 15. Checklist When Creating a JAR with a Manifest

- [ ] The JAR contains `META-INF/MANIFEST.MF`.
- [ ] The main section has `Manifest-Version: 1.0` when needed.
- [ ] `Main-Class` is a fully qualified class name and that class has a valid entry point.
- [ ] Required dependencies are packaged or declared via `Class-Path` properly.
- [ ] Relative URLs in `Class-Path` remain valid after deployment.
- [ ] Custom attributes have clear names and are placed in the right section.
- [ ] Long lines respect the byte limit and continuation format.
- [ ] `Multi-Release` and `Sealed` are only enabled when the archive is structured accordingly.
- [ ] The manifest is verified in the final artifact, not just in the configuration file.
- [ ] If digitally signing, only sign after finalizing the archive and re-verify the signature.

The manifest is an important metadata layer of a JAR. Understanding the main section, per-entry sections, `Main-Class`, `Class-Path`, package attributes, and the signing mechanism helps you build artifacts that are easy to run, easy to inspect, and deployable consistently across development, testing, and production environments.