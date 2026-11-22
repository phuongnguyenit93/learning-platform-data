# Updating a JAR with the JDK jar Tool

## Objectives

After this lesson, you will be able to update an existing JAR using the JDK `jar` tool; add new files or replace classes/resources at the exact internal path within the archive; update the manifest; understand why the update command does not delete old entries; handle signed JARs; and verify the artifact after updating.

## 1. What Is Updating a JAR?

A JAR (Java Archive) is a ZIP-based archive that typically contains class files, resources, metadata, and a manifest. A JAR can be used as a dependency on the classpath, as an executable JAR, or as a modular JAR.

Updating a JAR means modifying the contents of an existing archive, for example:

- Replacing a class file after recompiling.
- Adding or replacing resources such as properties, XML, JSON, image, or template files.
- Updating attributes in the manifest.
- Adding a module descriptor or module metadata when needed.

The `jar` tool included with the JDK supports update mode via the `-u` or `--update` option. This mode operates on an existing JAR. If the archive does not exist yet, create it with `--create` first.

It is important to understand the exact scope: `jar --update` adds new entries or replaces entries that have the same path name inside the archive. It does not compile source code, does not automatically update dependencies, does not run tests, and does not automatically synchronize file deletions from the source directory.

## 2. Basic Syntax

General syntax:

~~~bash
jar --update --file app.jar files...
~~~

Where:

- `--update` (or `-u`) selects update mode.
- `--file app.jar` (or `-f app.jar`) specifies the JAR to update.
- `files` are the files or directories to add to the archive.

Example of adding a resource:

~~~bash
jar --update --file app.jar config/app.properties
~~~

This command adds `app.properties` to the archive under the path resolved from the current working directory. If the archive already contains an entry with the same path, the entry's contents are replaced by the input file.

You can enable verbose output to see the entries being processed:

~~~bash
jar --update --verbose --file app.jar config/app.properties
~~~

Corresponding short-form options:

~~~bash
jar -uf app.jar config/app.properties
~~~

When just starting out, prefer the full option names for readability and to avoid confusing parameter order.

## 3. Paths Inside a JAR and the -C Option

An entry inside a JAR has an internal path name. This path name matters because the class loader, framework, or application looks up classes and resources by that exact path.

Suppose the file is located on disk at:

~~~text
build/classes/
└── com/
    └── example/
        └── Service.class
~~~

If you want the entry inside the JAR to be named:

~~~text
com/example/Service.class
~~~

Change the `jar` tool's working directory to `build/classes` before adding the file:

~~~bash
jar --update --file app.jar -C build/classes com/example/Service.class
~~~

The `-C DIR` option changes the root directory used for the files that follow it. The path recorded in the archive is the relative path beneath `DIR`.

If you omit `-C` and run from the project directory:

~~~bash
jar --update --file app.jar build/classes/com/example/Service.class
~~~

the entry may carry the `build/classes` prefix as well. In that case, the JVM will not find the class as `com.example.Service` on a standard classpath, because the internal path does not match the package.

You can use multiple `-C` pairs in a single command:

~~~bash
jar --update --file app.jar ^
  -C build/classes com/example/Service.class ^
  -C build/resources config/app.properties
~~~

The `^` character above is the line-continuation character in Windows Command Prompt. In PowerShell or Linux/macOS, line continuation differs; to avoid shell confusion, you can write the entire command on one line:

~~~bash
jar --update --file app.jar -C build/classes com/example/Service.class -C build/resources config/app.properties
~~~

This command updates the class and the resource from two different directories while preserving the correct relative paths inside the JAR.

## 4. Adding New Files and Replacing Old Entries

### Adding a new resource

Suppose the application needs to add `config/app.properties` to the JAR:

~~~bash
jar --update --file app.jar -C build/resources config/app.properties
~~~

After updating, list the archive contents:

~~~bash
jar --list --file app.jar
~~~

Look for the `config/app.properties` entry in the list. You can use `--verbose` to view more detailed information:

~~~bash
jar --list --verbose --file app.jar
~~~

### Replacing a compiled class

If you have modified `Service.java` and recompiled it to `Service.class`, update the exact entry:

~~~bash
javac -d build/classes src/com/example/Service.java
jar --update --file app.jar -C build/classes com/example/Service.class
~~~

The `com/example/Service.class` entry in the JAR will be replaced by the new class file with the same internal path.

Notes:

- You must compile the source before updating the JAR.
- Dependent classes or changed APIs may also need to be recompiled and updated together.
- Updating one class does not automatically update related classes.
- If you change package structure, class names, or public APIs, check every consumer of the JAR.

### Updating multiple files at once

You can pass multiple files in a single update:

~~~bash
jar --update --file app.jar -C build/classes . -C build/resources .
~~~

This command adds or replaces entries with matching names in the two directories. It does not remove old entries from the JAR just because those entries no longer exist in the input directory. This is an important difference between updating an archive and recreating an archive from a clean set of files.

## 5. Updating the Manifest

The manifest is a metadata file located at:

~~~text
META-INF/MANIFEST.MF
~~~

The manifest can contain attributes such as:

- `Main-Class`: the entry-point class of an executable JAR.
- `Implementation-Title`: the implementation name.
- `Implementation-Version`: the implementation version.
- `Specification-Title` and `Specification-Version`: specification information.
- `Class-Path`: additional dependent libraries following manifest syntax.

### Updating Main-Class

If the JAR already has an entry-point class or needs to change its main class:

~~~bash
jar --update --file app.jar --main-class com.example.Main
~~~

The `Main-Class` attribute must use the fully qualified class name without the `.class` extension. The corresponding class must actually exist in the archive or on the required classpath.

You can inspect the manifest by extracting it:

~~~bash
jar --extract --file app.jar META-INF/MANIFEST.MF
~~~

Then read the `META-INF/MANIFEST.MF` file in the current directory.

### Adding or updating manifest attributes

Create a `manifest-additions.mf` file:

~~~text
Implementation-Title: Example Application
Implementation-Version: 1.2.0
Build-Revision: abc123

~~~

A manifest must have a trailing blank line ending the attributes section. A final newline is required so the parser reads all attributes completely.

Update the archive:

~~~bash
jar --update --file app.jar --manifest manifest-additions.mf
~~~

The attributes in the input manifest file are merged into the JAR's manifest; attributes with the same name can be updated. After making changes, extract the manifest to confirm its actual contents.

Do not arbitrarily replace the entire manifest of a library or application built by another build system. The manifest may contain `Class-Path`, module metadata, package sealing, digests, or deployment information that the application depends on.

### Updating the manifest vs. adding a regular file

Do not put a manifest file into a JAR as an ordinary resource at an arbitrary path. Use `--manifest` or `--main-class` so the `jar` tool handles metadata in the proper location and format.

## 6. Updating a JAR Does Not Automatically Delete Entries

The `--update` mode supports adding and replacing entries, but it does not provide a delete operation for entries inside a JAR.

For example, the archive contains:

~~~text
config/old.properties
config/new.properties
~~~

After running:

~~~bash
jar --update --file app.jar -C build/resources config/new.properties
~~~

the `config/old.properties` entry still remains unless further action is taken. The `jar` tool does not treat the input directory as an authoritative mirror that automatically deletes any entry no longer present.

### When you need to delete an entry

The safest and most reproducible approach is to recreate the JAR from a curated set of inputs:

1. Obtain the canonical source/build outputs for the artifact.
2. Remove the no-longer-needed files from the input set.
3. Create a new JAR with the exact classes, resources, and manifest required.
4. Inspect the contents, run tests, and re-sign the JAR if required by your workflow.

If you must work from an existing archive, extract it into a staging directory, delete the unwanted files in staging, and then create a new archive from the remaining contents. Keep the manifest separate and verify it is included properly in the new JAR.

Example workflow:

~~~bash
jar --extract --file app.jar --dir staging
~~~

Then delete the unwanted files in the `staging` directory using OS tools, and repackage:

~~~bash
jar --create --file app-new.jar --manifest staging/META-INF/MANIFEST.MF -C staging .
~~~

Before using this workflow on a real artifact, inspect the staging structure, manifest, and signature files. If the archive was signed, do not copy the old signature files verbatim into the modified artifact; run the re-signing process according to your release policy.

Do not overwrite a production archive immediately. Create `app-new.jar`, verify and test it first, and only then replace the artifact through a controlled deployment process.

## 7. Signed JARs: Signatures Must Be Handled After Updating

A JAR can be signed with `jarsigner`. Signatures use digests of the entries and manifest metadata to detect content modifications.

When updating a signed JAR:

- If you modify the contents of a signed entry, its digest will no longer match and signature verification for that entry will fail.
- If you add a new entry after signing, the new entry will not have the original signer's signature.
- A JAR can end up containing both signed and unsigned entries; this is not equivalent to a fully signed artifact under release policies.
- Modifying the manifest can also affect digest/signature data.

The recommended workflow is to complete all changes first, and then sign the final artifact using an organization-approved key and signing process.

Verify signatures:

~~~bash
jarsigner --verify --verbose --certs app.jar
~~~

Read all warnings and results, especially unsigned entries, certificate chains, disabled algorithms, and timestamp status. If your release process requires severe warnings to fail verification, add the `--strict` option:

~~~bash
jarsigner --verify --strict --verbose --certs app.jar
~~~

Do not ignore warnings just because the command returns exit code 0. Verify the right certificate, signer, and trust policy for your deployment environment.

Never share private keys, keystore passwords, or tokens in command lines, scripts, logs, or documentation. Signing must use your organization's secure key-management process.

## 8. Updating Modular JARs and Multi-Release JARs

### Modular JAR

Since Java 9, a JAR can contain a module descriptor `module-info.class` at the root. You can inspect the module:

~~~bash
jar --describe-module --file library.jar
~~~

When you need to update the module descriptor or module metadata, ensure the descriptor matches the actual packages, dependencies, and exported/opened packages. Example of updating a compiled module descriptor:

~~~bash
jar --update --file library.jar -C build/module-classes module-info.class
~~~

If the module descriptor changes, recheck the module graph and test on the module path. A JAR with `module-info.class` cannot be treated like a plain classpath JAR in all cases; resolution depends on how the application uses it.

### Multi-release JAR

A multi-release JAR can contain different versions of a class by directory:

~~~text
com/example/Service.class
META-INF/versions/17/com/example/Service.class
META-INF/versions/21/com/example/Service.class
~~~

The JVM selects the entry version matching the runtime release according to multi-release JAR rules, provided the manifest marks `Multi-Release: true`.

When updating a Java 17-specific version, use the `--release` option:

~~~bash
jar --update --file library.jar --release 17 -C build/classes-17 com/example/Service.class
~~~

Ensure the root entry still provides an implementation compatible with the lowest baseline Java version supported by the library. Versioned variants should be tested together to avoid a release receiving a different API or missing a class.

## 9. Complete Hands-On Example

This example creates an executable JAR, runs it, updates a class, and runs it again.

### Step 1: create the source

Create `src/com/example/Main.java`:

~~~java
package com.example;

public class Main {
    public static void main(String[] args) {
        System.out.println("version=1");
    }
}
~~~

### Step 2: compile

~~~bash
javac -d build/classes src/com/example/Main.java
~~~

### Step 3: create the initial JAR

~~~bash
jar --create --file app.jar --main-class com.example.Main -C build/classes .
~~~

### Step 4: run and confirm initial output

~~~bash
java -jar app.jar
~~~

Output:

~~~text
version=1
~~~

### Step 5: edit the source and recompile

Change the body of `main` to:

~~~java
package com.example;

public class Main {
    public static void main(String[] args) {
        System.out.println("version=2");
    }
}
~~~

Recompile:

~~~bash
javac -d build/classes src/com/example/Main.java
~~~

### Step 6: update the class in the JAR

~~~bash
jar --update --file app.jar -C build/classes com/example/Main.class
~~~

### Step 7: run again

~~~bash
java -jar app.jar
~~~

Output:

~~~text
version=2
~~~

The class name and entry path did not change, so the manifest's `Main-Class` still points correctly to `com.example.Main`. In real-world projects, if dependencies, packages, modules, or the manifest change, you must update and verify those corresponding components as well.

## 10. Verifying the JAR After Updating

Do not assume success just because the `jar` command reported no errors. Verify the archive contents and usability.

### Check the entry list

~~~bash
jar --list --file app.jar
~~~

Confirm that the new classes/resources have the right internal paths and that unwanted old entries are gone (if rebuilt).

### Check the manifest

~~~bash
jar --extract --file app.jar META-INF/MANIFEST.MF
~~~

Read attributes such as `Main-Class`, `Implementation-Version`, `Class-Path`, and `Multi-Release`.

### Check classes and modules

Use `javap` to inspect a specific class:

~~~bash
javap -classpath app.jar -p com.example.Main
~~~

If the JAR is modular:

~~~bash
jar --describe-module --file app.jar
~~~

### Run a smoke test

For an executable JAR:

~~~bash
java -jar app.jar
~~~

For a library JAR, create or run a small test application that exercises the updated classes/resources. Not every JAR has a `Main-Class` or can be run directly with `-jar`.

### Check signatures

If the JAR is signed:

~~~bash
jarsigner --verify --verbose --certs app.jar
~~~

Confirm that every protected entry has the expected signer and that there are no warnings outside what your policy permits.

### Compare checksums

Once finished, you can compute a checksum to record the artifact:

Linux/macOS:

~~~bash
sha256sum app.jar
~~~

Windows PowerShell:

~~~powershell
Get-FileHash app.jar -Algorithm SHA256
~~~

Store the checksum alongside version/build metadata to uniquely identify the verified and released artifact.

## 11. Common Errors

### JAR does not exist

**Symptom:** `jar --update` reports that the archive cannot be opened.

**Cause:** wrong file path or the archive has not been created yet.

**Resolution:** check the current directory and filename. If the archive does not exist yet, use `--create` to create the JAR.

### Entry has the wrong package path

**Symptom:** the JAR contains the class file, but the JVM throws `ClassNotFoundException` or `NoClassDefFoundError`.

**Cause:** the file was added with an unwanted build-directory prefix or wrong package path.

**Resolution:** use `-C` to set the root directory, then run `jar --list` to confirm the entry looks like `com/example/Main.class`.

### Updated a directory, but old files remain

**Symptom:** entries deleted from the build directory still appear in the JAR.

**Cause:** `--update` only adds/replaces entries; it does not delete entries absent from the input.

**Resolution:** recreate the JAR from a clean set of files, or extract to staging, delete the unwanted files, and package a new archive.

### Manifest did not change as expected

**Symptom:** `java -jar` still runs the old main class or the version attribute did not update.

**Cause:** the manifest file was not passed via `--manifest`, the attribute name is wrong, the trailing blank line is missing, or you are inspecting the wrong JAR.

**Resolution:** use `--main-class` or `--manifest`, extract `META-INF/MANIFEST.MF`, and read its contents after updating.

### JAR signature is no longer valid

**Symptom:** `jarsigner` verify reports a digest error or unsigned entries.

**Cause:** a signed entry was modified or a new entry was added after signing.

**Resolution:** complete all updates first, then re-sign the final artifact and verify the signature.

### Running application still uses the old class

**Symptom:** the JAR file on disk is updated, but the application still produces old output.

**Cause:** the class loader has already loaded the class into the JVM; changing the JAR file on disk does not automatically replace classes already loaded in a running process.

**Resolution:** deploy the new artifact through the application's deployment process and restart/redeploy the process as needed. Do not treat replacing a file on disk as hot reload.

### Updated a class but forgot related dependencies

**Symptom:** `NoSuchMethodError`, `NoSuchFieldError`, or linkage errors after updating.

**Cause:** the new class was compiled against a different API than the remaining classes/dependencies in the JAR or at runtime.

**Resolution:** rebuild the entire artifact from version-locked sources/dependencies, run integration tests, and avoid patching a single class when an API change has cascading effects.

## 12. Safe Update Workflow

1. Identify the exact JAR and current version.
2. Back up the artifact or create a working copy.
3. Identify the entries to add/replace and their desired internal paths.
4. Recompile classes/resources from canonical sources.
5. Update on a copy or staging artifact.
6. Inspect the entry list and manifest.
7. Run appropriate unit/integration/smoke tests.
8. If the JAR is signed, re-sign the final artifact and verify it.
9. Compute the checksum and record version/build metadata.
10. Release or deploy using a process that supports rollback.

For products built automatically with Gradle or Maven, edit the source and rebuild the JAR through the pipeline rather than patching a released artifact directly. Using `jar --update` is suited for learning, testing, controlled resource fixes, or handling special artifacts when you clearly understand their structure and provenance.

## 13. Quick-Reference Checklist

- [ ] Use `--update` to update an existing archive.
- [ ] Understand that entries are identified by their internal path inside the JAR.
- [ ] Use `-C` to avoid adding extra root directories to the entry path.
- [ ] Compile classes before updating class files.
- [ ] Confirm that entries with matching names are replaced with the right contents.
- [ ] Do not assume `--update` automatically deletes old entries.
- [ ] Use `--manifest` or `--main-class` to update metadata.
- [ ] Check `module-info.class` and multi-release entries when the JAR has modules or versioned classes.
- [ ] Handle signatures after modifying JAR contents.
- [ ] Use `jar --list`, `javap`, `jarsigner`, and smoke tests to verify.
- [ ] Do not expect a running JVM process to reload classes automatically when the JAR file changes.
- [ ] Store checksums and preserve rollback capability.

## 14. Official References

- [The jar Command — Java SE 27 Tool Specification](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jar.html) — create/update/list/extract modes, `-C`, manifest, main class, modules, and multi-release JARs.
- [The jar Command — Java SE 24 Tool Specification](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jar.html) — syntax and examples for updating a JAR with `--update`.
- [The jarsigner Command — Java SE 26 Tool Specification](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jarsigner.html) — signature structure, digests, verification, and warnings for signed JARs.
- [JAR File Specification](https://docs.oracle.com/en/java/javase/26/docs/specs/jar/jar.html) — manifest format, entries, and JAR signing.
- [The javap Command — Java SE 26 Tool Specification](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javap.html) — inspecting class file contents inside a JAR.

Updating a JAR is a direct operation on the archive. Specify the exact entry path, understand the limits of `--update`, verify the manifest/signatures, and test the new artifact before deploying.
