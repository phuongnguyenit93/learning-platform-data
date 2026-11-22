# Manifest, JAR Signatures, and Service Metadata After Repackaging

When upgrading the JDK, changing Maven/Gradle plugins, or switching from multiple dependency JARs to a *fat JAR*, *uber JAR*, or *shaded JAR*, a Java application can compile cleanly yet fail upon deployment. One frequently overlooked cause is that **metadata inside the artifact** was overwritten, filtered out, or became inconsistent with the repackaged contents. Key components include `META-INF/MANIFEST.MF`, JAR signature files, and `META-INF/services` used by `ServiceLoader`.

For example: a JAR originally declared `Main-Class`, but the final packaging task strips that attribute; two libraries both register a provider for the same SPI, yet the packager keeps only one service file; or a signed dependency has its classes or manifest altered during shading while old signature blocks are still copied over. These failures surface in different ways: `no main manifest attribute`, `ServiceConfigurationError`, `SecurityException`, or business results missing functionality without any startup error.

This lesson explains the role of each piece of metadata, how to preserve contracts during repackaging, shading, and relocation, how to handle signatures in accordance with security policy, specifics of JPMS and multi-release JARs, and a process for verifying the **final artifact** during Java Advance Compatibility Migration.

## 1. A JAR contains more than `.class` files

A JAR is a ZIP-based archive. Beyond bytecode, it also holds resources and runtime contracts.

~~~text
payments-client.jar
├── META-INF/
│   ├── MANIFEST.MF
│   ├── services/
│   │   └── com.example.spi.PaymentProvider
│   ├── LICENSE
│   └── NOTICE
├── com/example/api/PaymentClient.class
├── com/example/impl/FastPaymentProvider.class
└── config/defaults.properties
~~~

A signed JAR may additionally include:

~~~text
META-INF/
├── MANIFEST.MF
├── RELEASE.SF
└── RELEASE.RSA
~~~

A multi-release JAR may include:

~~~text
META-INF/versions/
├── 11/com/example/runtime/PlatformSupport.class
└── 17/com/example/runtime/PlatformSupport.class
~~~

These paths govern how the Java launcher, class loader, module system, JAR verifier, and frameworks use the artifact. Do not treat files under `META-INF` as incidental resources that can be stripped to shrink archive size.

| Component | Function | Risk after repackaging |
|---|---|---|
| `META-INF/MANIFEST.MF` | Entry point, class path, archive info, multi-release flag, module name | Startup failure, missing classpath, lost MR-JAR behavior |
| `META-INF/*.SF` and signature blocks | Verification data for signed entries | Signature digest mismatch or lost provenance |
| `META-INF/services/*` | Provider registrations for Java SPI | Dropped provider, wrong provider name |
| `module-info.class` | Descriptor of an explicit Java module | Module resolution, access, or service binding errors |
| `META-INF/versions/*` | Class variants for newer JDKs | Wrong class chosen or lost optimization |
| Framework metadata | Registers auto-configuration, extensions, resources | Framework skips features |
| `LICENSE`/`NOTICE` | Distribution and licensing information | Violation of attribution/distribution requirements |

## 2. What operations can "repackaging" involve?

Builds typically perform one or more of the following:

- Creating a JAR from the project's classes.
- Merging all dependency classes into an uber JAR.
- **Relocation:** renaming library package names to avoid conflicts.
- **Resource transformation:** merging or rewriting resources that share the same path.
- **Minimization:** stripping classes or resources deemed unused.
- Creating an executable JAR with a custom launcher and nested dependencies.
- Modifying the manifest or adding build metadata.
- Signing the final artifact.

Not every packaging format produces the same structure. A flat shaded JAR differs from a Spring Boot executable JAR containing nested JARs. A modular JAR with `module-info.class` differs from an automatic module carrying only `Automatic-Module-Name` in its manifest.

Risk diagram:

~~~text
Source + dependency JARs
             |
             v
Compile/Test
             |       Unit tests may run from target/classes
             v
Package / Shade / Repackage
             |
             +--> MANIFEST is modified
             +--> signature files no longer match
             +--> META-INF/services is overwritten
             +--> classes/metadata are relocated
             +--> versioned entries are altered
             v
Final deployed artifact
             |
             v
java -jar / module launcher / ServiceLoader
             |
             v
Errors appear only at runtime
~~~

**BUILD SUCCESS does not prove the runtime artifact is valid.** Tests that run only before the packaging step may fail completely to catch metadata bugs.

## 3. Manifest: structure and meaning

The manifest typically resides at `META-INF/MANIFEST.MF`. It has a main section with global attributes and can also contain per-entry or per-package sections. Manifest formatting follows strict rules for character encoding, continuation lines, and blank lines separating sections; let `jar` or build plugins generate it rather than concatenating raw text arbitrarily.

Example:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.app.Main
Implementation-Title: Payment Service
Implementation-Version: 2.3.0
Automatic-Module-Name: com.example.payment
Multi-Release: true

~~~

The attributes above do not necessarily all appear together in every JAR. `Main-Class` is needed when launching the corresponding entry point with the standard `java -jar` launcher. `Automatic-Module-Name` is useful for automatic modules. `Multi-Release: true` is appropriate only when the artifact is built as an MR-JAR.

### 3.1. `Main-Class` and `java -jar`

Example manifest for a simple application:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.app.Main

~~~

Create the archive using the JDK `jar` tool:

~~~bash
jar --create --file app.jar --manifest manifest.mf -C out/classes .
java -jar app.jar
~~~

This example assumes `out/classes` contains `com/example/app/Main.class` with an appropriate `main` method, and that dependencies are supplied properly.

If repackaging loses the entry point:

~~~text
no main manifest attribute, in app.jar
~~~

If the class name is wrong, the JVM can report that the main class could not be found. What matters is the **manifest inside the final artifact**, not the POM or Gradle configuration of an intermediate JAR.

### 3.2. `Class-Path` is not equivalent to nested JARs

A manifest can declare:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.app.Main
Class-Path: lib/common.jar lib/jdbc-driver.jar

~~~

Intended distribution layout:

~~~text
distribution/
├── app.jar
└── lib/
    ├── common.jar
    └── jdbc-driver.jar
~~~

Paths in the manifest are interpreted according to JAR Class-Path rules, generally relative to the directory holding the JAR. Moving `app.jar` without `lib` prevents the class loader from finding dependencies.

Keep these distinctions clear:

- `Class-Path` describes references to external artifacts; it does not embed their contents into the JAR.
- Placing `dependency.jar` as a raw entry inside a JAR usually **does not automatically** create a nested classpath with the standard Java launcher.
- With `java -jar`, application classpath resolution comes from the archive, manifest, and launcher mechanism; do not assume external `-cp` flags supplement it the way they do when launching a main class directly.
- Spring Boot and other frameworks can supply their **own launcher** to load nested JARs.

### 3.3. `Implementation-Version` and release metadata

Attributes such as:

~~~text
Implementation-Title: Payment Service
Implementation-Version: 2.3.0
Implementation-Vendor: Example Corp
Build-Jdk-Spec: 21
~~~

can aid release identification or `Package` APIs within a supporting class loader. However, they **do not prove** bytecode compatibility with the target JDK. A JAR claiming `Build-Jdk-Spec: 17` can still hold dependency classes compiled for Java 21 if the packaging pipeline is misconfigured.

Also store artifact checksums, dependency lockfiles, and build provenance instead of treating manifest text as runtime verification.

### 3.4. Package sealing in the manifest

A manifest can declare sealing to restrict how classes belonging to a package may be defined from different code sources.

Example sealing the entire archive:

~~~text
Manifest-Version: 1.0
Sealed: true

~~~

Or a section targeting a package:

~~~text
Name: com/example/internal/
Sealed: true

~~~

When shading dependencies or combining multiple JARs sharing a package, package sealing can raise `SecurityException`. Examine package definitions and class code sources; do not remove `Sealed` just to silence errors without understanding the library's guarantees.

## 4. `Automatic-Module-Name` and `module-info.class`

In Java 9 and later, a JAR on the module path can act as an explicit module if it contains `module-info.class`, or as an automatic module if it lacks a descriptor and is placed on the module path under JPMS rules.

### 4.1. Stable automatic module names

An automatic module name can be derived from the JAR filename. When a library changes from `library-1.0.jar` to `library-core-2.0.jar`, the derived name can change, breaking consumers with fixed `requires` directives.

The manifest can declare:

~~~text
Automatic-Module-Name: com.example.library.core
~~~

This gives a stable module name to libraries without an explicit descriptor. If repackaging drops that attribute, modular consumers may fail to find the expected module.

### 4.2. Do not equate a manifest name with an explicit descriptor

A JAR containing `module-info.class` is an explicit named module defined by its descriptor. `Automatic-Module-Name` does not replace declarations such as:

~~~java
module com.example.library {
    requires java.sql;
    exports com.example.library.api;
    uses com.example.spi.PaymentProvider;
}
~~~

Merging multiple JARs that carry descriptors via a shade step does not produce a single valid unified descriptor. If the final artifact is truly modular, intentionally author its requires/exports/opens/uses/provides clauses rather than keeping just one arbitrary `module-info.class`.

### 4.3. Inspecting the final descriptor

~~~bash
jar --describe-module --file library.jar
~~~

This command shows module identity and descriptor details as interpreted by `jar`. For an automatic module, output reports the derived module name and related details. When migrating from classpath to module path, run real runtime tests because class loaders, package access, and service discovery may differ.

## 5. Multi-release JARs and metadata

A multi-release JAR can ship base classes alongside variants compiled for newer JDKs.

~~~text
runtime-support.jar
├── META-INF/MANIFEST.MF
├── com/example/runtime/PlatformSupport.class
└── META-INF/versions/
    ├── 11/com/example/runtime/PlatformSupport.class
    └── 17/com/example/runtime/PlatformSupport.class
~~~

The manifest requires:

~~~text
Manifest-Version: 1.0
Multi-Release: true

~~~

On JDKs supporting MR-JARs, the runtime selects the appropriate optimized class version for the running release according to the JAR specification.

### 5.1. Losing the manifest attribute

If `META-INF/versions` survives repackaging while `Multi-Release: true` is overwritten, the artifact may stop being treated as a multi-release JAR. The outcome is not necessarily a crash: an installation on JDK 17 may silently fall back to the base implementation instead of the JDK 17 variant.

### 5.2. Merging versioned classes incorrectly

If a tool promotes classes from `META-INF/versions/17` to the base path, older runtimes can attempt to load newer bytecode and throw `UnsupportedClassVersionError`. If identically named entries overwrite one another, a JDK release can receive the wrong implementation.

Run regression tests across all runtimes the artifact claims to support, not merely the newest JDK.

### 5.3. Verification

~~~bash
jar --list --file runtime-support.jar
jar --describe-module --file runtime-support.jar
jdeps --multi-release 17 --summary runtime-support.jar
~~~

`jdeps` analyzes static dependencies of the selected class variant; it does not replace runtime execution and resource-lookup tests.

## 6. JAR signatures: manifest digests, `.SF`, and signature blocks

A signed JAR can contain:

~~~text
META-INF/MANIFEST.MF
META-INF/RELEASE.SF
META-INF/RELEASE.RSA
~~~

Depending on the cryptographic algorithm, signature blocks may use `.DSA`, `.EC`, or another format supported by the corresponding JDK documentation. Do not hard-code the assumption that signed JARs always have `.RSA`.

### 6.1. Manifest digests

A signed JAR manifest can contain per-entry sections:

~~~text
Manifest-Version: 1.0

Name: com/example/api/PaymentClient.class
SHA-256-Digest: <illustrative base64 digest>

~~~

The digest line above shows structure only, not a valid hash. During actual signing, `jarsigner` generates digests matching the signed entries.

### 6.2. Signature files and signature blocks

`*.SF` stores digest data tied to the manifest or manifest sections. A signature block such as `*.RSA` carries the cryptographic signature and typically certificate information under JAR signing rules. Together they enable verification of signed contents and signer identity according to trust policy.

This does **not** automatically guarantee that:

- A dependency contains no security vulnerabilities.
- The certificate chain is trusted under enterprise policy.
- Certificates are unexpired or all algorithms remain permitted.
- Class files run on every JDK version.
- The artifact has no missing library dependencies.

A valid signature is one layer of supply-chain integrity, not a blanket certification of software quality.

### 6.3. Verifying with `jarsigner`

~~~bash
jarsigner -verify -verbose -certs library.jar
~~~

When policy requires strict handling of warnings:

~~~bash
jarsigner -verify -strict -verbose -certs library.jar
~~~

Read the complete output: cryptographic signature verification status plus warnings on certificates, trust chains, timestamps, and algorithms. Depending on the JDK, `-strict` can affect the exit status when severe warnings are present.

### 6.4. Verification happens when entries are read

Under JAR verification, some checks occur lazily when a signed class or resource is read or loaded. Thus successful application startup does not prove every signed entry was verified.

For instance, a provider loaded only when a rare workflow runs can trigger a signature failure later in production. Verify the artifact directly and run integration tests that actually load critical components.

### 6.5. CRC does not replace signatures

ZIP CRC detects data corruption, not signer identity or tampering by an untrusted party. File hashes provide checksum integrity, not full JAR signing and trust chains. Never treat a succeeding `jar --list` as evidence that JAR signatures remain valid.

## 7. Why shading or repackaging invalidates source signatures

Suppose a signed dependency JAR holds classes and corresponding digests:

~~~text
vendor-lib.jar
  |- META-INF/MANIFEST.MF
  |- META-INF/VENDOR.SF
  |- META-INF/VENDOR.RSA
  |- org/vendor/Parser.class
~~~

A shade build performs relocation:

~~~text
org.vendor.Parser
    ->
com.example.shadow.vendor.Parser
~~~

Because classes, resources, and manifest metadata change, signature files copied from the source JAR no longer describe the new artifact accurately.

If the tool copies old signature files into the shaded JAR, the runtime or verifier can fail with:

~~~text
java.lang.SecurityException:
    Invalid signature file digest for Manifest main attributes
~~~

Or:

~~~text
java.lang.SecurityException:
    SHA-256 digest error for org/vendor/Parser.class
~~~

Exact wording depends on JDK and artifact; the underlying cause is that signed content or manifest no longer matches signature metadata.

### 7.1. Do not "merge" signature blocks across multiple JARs

Two separately signed dependencies cannot simply have all their `META-INF/*.SF` and `*.RSA` files copied into an uber JAR to make the uber JAR "signed by both vendors." Signature files bind specifically to the manifest and entries under the source artifact's signing layout.

Once contents and archive structure change, treat the output as a **new artifact** governed by its own signing and provenance policy.

### 7.2. Signer mismatch errors

When classes in the same package are loaded from signed and unsigned sources—or sources with different signers—the runtime can raise:

~~~text
java.lang.SecurityException:
  class "com.example.shared.Helper"'s signer information
  does not match signer information of other classes
  in the same package
~~~

This differs from a digest mismatch. Check for split packages, code sources, signer identities, and classpath ordering. Never fix it by blindly deleting every signature file without understanding why signing was present.

### 7.3. Do not delete signatures arbitrarily

Some Shade tutorials suggest excluding:

~~~text
META-INF/*.SF
META-INF/*.RSA
META-INF/*.DSA
META-INF/*.EC
~~~

This is acceptable only when **the organization is authorized to publish a new artifact**, does not claim original vendor signatures remain intact, and maintains proper provenance and re-signing steps where needed. Stripping signatures removes the ability to verify the original source signer in the repackaged JAR format.

Never modify a signed vendor artifact and distribute it as though it were still the unmodified vendor-signed binary. If policy mandates preserving vendor signatures, the right option may be **not shading that library** and shipping it as a separate JAR instead.

## 8. Signing the new artifact after all transformations

A controlled pipeline:

~~~text
Compile + dependencies
         |
         v
Shade / relocate / package
         |
         v
Merge manifest and service metadata
         |
         v
Finalize artifact
         |
         v
Sign with an authorized release key
         |
         v
jarsigner -verify
         |
         v
Publish immutable artifact + provenance
~~~

Re-signing creates a **fresh signature over the final artifact**; it does not restore lost vendor signatures.

### 8.1. `jarsigner` example

~~~bash
jarsigner \
  -keystore release-keystore.p12 \
  -storetype PKCS12 \
  -signedjar app-signed.jar \
  app-unsigned.jar \
  release-signer
~~~

This syntax is illustrative; an authorized keystore and alias are required. In production, signing keys and passwords must live in a secure secret store, signing service, or hardened pipeline rather than source repositories or unguarded CLI history.

Afterward:

~~~bash
jarsigner -verify -strict -verbose -certs app-signed.jar
~~~

If the artifact is modified after signing, re-sign through the proper workflow. Never treat `jarsigner -verify` as a substitute for vulnerability scanning, provenance tracking, or certificate policy enforcement.

### 8.2. Reproducible builds and signing

Factors such as timestamps, entry ordering, and build metadata can alter archive checksums even from nearly identical source. Where reproducible builds are required, configure archive determinism and signing appropriately while recording versions and checksums. Even then, **reproducibility** is distinct from **authenticity**: a reproducible build alone does not prove the artifact originated from a trusted publisher.

## 9. `META-INF/services` and `ServiceLoader`

Java SPI lets a client discover implementations without importing concrete classes directly. Example interface:

~~~java
package com.example.spi;

public interface Compressor {
    String name();
    byte[] compress(byte[] data);
}
~~~

One provider:

~~~java
package com.example.impl;

import com.example.spi.Compressor;

public final class FastCompressor implements Compressor {
    public FastCompressor() {}

    @Override
    public String name() {
        return "fast";
    }

    @Override
    public byte[] compress(byte[] data) {
        return data; // Illustrative example, data not yet compressed
    }
}
~~~

Another provider might live in `org.vendor.impl.CompactCompressor`.

### 9.1. Service configuration files

The filename must match the service interface:

~~~text
META-INF/services/com.example.spi.Compressor
~~~

First provider JAR:

~~~text
com.example.impl.FastCompressor
~~~

Second provider JAR uses the identical path with content:

~~~text
org.vendor.impl.CompactCompressor
~~~

### 9.2. Discovering providers from a client

~~~java
package com.example.app;

import com.example.spi.Compressor;
import java.util.ServiceLoader;

public class DiscoverCompressors {
    public static void main(String[] args) {
        for (Compressor provider :
                ServiceLoader.load(Compressor.class)) {
            System.out.println(provider.name());
        }
    }
}
~~~

When both provider JARs sit on the classpath, the client discovers two providers. `META-INF/services` files support `#` comments and multiple lines of class names, and are not Java source files.

### 9.3. When identically named files overwrite each other

If an uber-JAR task keeps only the first dependency's service file, the final artifact still holds:

~~~text
META-INF/services/com.example.spi.Compressor
  com.example.impl.FastCompressor
~~~

but `CompactCompressor` vanishes. No exception may be thrown at all; one provider is simply missing. That is a functional regression.

**Provider declarations must be merged**, rather than keeping one colliding file by an arbitrary strategy.

### 9.4. Merged contents

~~~text
META-INF/services/com.example.spi.Compressor
  com.example.impl.FastCompressor
  org.vendor.impl.CompactCompressor
~~~

In real files, lines contain plain class names without the indentation shown in the diagram above. If raw byte concatenation occurs when the first file lacks a trailing newline, two provider names can run together onto one line and trigger `ServiceConfigurationError`.

### 9.5. Providers can fail even when the file exists

`ServiceLoader` can fail if:

- The named provider class no longer exists.
- The provider does not implement the required interface.
- Its constructor or `provider()` method does not match supported conventions.
- The class loader cannot see a dependency.
- A static initializer or constructor throws an exception.
- A provider module was not resolved or its descriptor is invalid.
- A JAR minimizer deleted classes referenced only dynamically.

Testing must therefore instantiate providers and invoke a safe method rather than merely verifying the file exists.

## 10. How relocation and minimization affect metadata

### 10.1. Class names inside service files must be relocated

If shading rewrites:

~~~text
org.vendor.impl.CompactCompressor
   ->
com.example.shadow.vendor.CompactCompressor
~~~

then service file entries must be updated accordingly. Retaining the old name causes `ServiceLoader` to look for a class no longer at that location:

~~~text
java.util.ServiceConfigurationError:
  com.example.spi.Compressor:
  Provider org.vendor.impl.CompactCompressor not found
~~~

If the service interface itself is relocated, the filename `META-INF/services/<interface>` must likewise match the relocated interface name. A proper transformer must synchronize class renames with service metadata.

### 10.2. Minimization can strip providers

Client code may contain static references only to `Compressor.class`, while `CompactCompressor` appears solely as text inside a service file. An optimizer scanning only bytecode references may prune the provider class as unreachable.

Flow diagram:

~~~text
ServiceLoader.load(Compressor.class)
          |
          v
META-INF/services/com.example.spi.Compressor
          |
          v
org.vendor.impl.CompactCompressor
          |
          v
Class removed by minimizer -> runtime error
~~~

When enabling `minimizeJar` or tree-shaking, inventory reflection targets, SPI providers, framework metadata, configured class names, and plugin entry points. Never conclude a dependency is unused solely because `jdeps` or a static analyzer finds no direct type reference.

### 10.3. Framework providers

Beyond standard Java SPI, many frameworks rely on resources such as:

~~~text
META-INF/spring.factories
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
META-INF/native-image/...
META-INF/LICENSE
META-INF/NOTICE
~~~

`ServicesResourceTransformer` handles standard Java service descriptors, not every framework-specific metadata format. Configure transformers appropriate to each format and framework version, and do not strip required license or notice text when merging files.

## 11. Named modules: `uses` and `provides`

In JPMS, explicit named modules declare services inside their module descriptors.

Service API module:

~~~java
module com.example.spi.api {
    exports com.example.spi;
}
~~~

Provider module:

~~~java
module com.example.codec.fast {
    requires com.example.spi.api;
    provides com.example.spi.Compressor
        with com.example.impl.FastCompressor;
}
~~~

Consumer module:

~~~java
module com.example.app {
    requires com.example.spi.api;
    uses com.example.spi.Compressor;
}
~~~

### 11.1. Classpath SPI does not replace explicit module descriptors

With explicit named modules, `provides ... with ...` and `uses` form the authoritative module contract. You cannot simply copy a `META-INF/services` file from a classpath JAR and assume it behaves identically to module descriptor declarations.

Automatic modules follow separate legacy service-configuration rules, which must still be verified in the actual module graph.

### 11.2. Module resolution and class loaders

A provider module can exist on disk without being resolved into the runtime module graph. In that case `ServiceLoader` will not automatically find it.

Launch using the intended module setup:

~~~bash
java --module-path mods \
  --module com.example.app/com.example.app.Main
~~~

And inspect the provider:

~~~bash
jar --describe-module --file provider.jar
~~~

With custom `ModuleLayer`s or class loaders, choose the matching `ServiceLoader.load`/`load(layer, service)` overload. Tests executed on the classpath are insufficient to prove JPMS service binding.

## 12. Maven Shade Plugin: merging resources by type

`maven-shade-plugin` provides *resource transformers*. Commonly used transformers include:

- `ManifestResourceTransformer`: sets main manifest attributes such as `Main-Class`.
- `ServicesResourceTransformer`: merges service provider files and handles provider name updates during relocation.

Example:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-shade-plugin</artifactId>
    <version>3.6.1</version>
    <executions>
        <execution>
            <phase>package</phase>
            <goals><goal>shade</goal></goals>
            <configuration>
                <transformers>
                    <transformer implementation=
                      "org.apache.maven.plugins.shade.resource.ManifestResourceTransformer">
                        <mainClass>com.example.app.Main</mainClass>
                    </transformer>
                    <transformer implementation=
                      "org.apache.maven.plugins.shade.resource.ServicesResourceTransformer" />
                </transformers>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

When adapting examples to a project, pin an appropriate plugin version and check Maven/Java compatibility. Add further transformers or filters as required by actual metadata.

### 12.1. The manifest transformer does not merge services

Configuring `mainClass` sets only the entry point; it does not preserve providers across dependencies. Conversely, the services transformer does not select a main class. Configure each requirement explicitly.

### 12.2. Signature filters require clear policy

A common configuration pattern for shaded JARs:

~~~xml
<filters>
    <filter>
        <artifact>*:*</artifact>
        <excludes>
            <exclude>META-INF/*.SF</exclude>
            <exclude>META-INF/*.RSA</exclude>
            <exclude>META-INF/*.DSA</exclude>
            <exclude>META-INF/*.EC</exclude>
        </excludes>
    </filter>
</filters>
~~~

This pattern is valid only **when creating a new artifact is authorized and policy allows omitting source signatures**, or when the final artifact will be newly signed by the release pipeline. Never use it merely to "bypass signature errors" where preserving vendor signatures or provenance is mandatory.

### 12.3. Watch `minimizeJar` and dependency-reduced POMs

If minimization is enabled, classes loaded solely via `ServiceLoader` or reflection may be pruned. Generating a dependency-reduced POM also alters published dependency metadata. Inspect both the runtime artifact and repository distribution metadata.

### 12.4. Testing the shaded artifact

Unit tests often run directly against `target/classes`, bypassing shading. Execute the actual shaded artifact after `package` with the real launcher, verifying providers and runtime features.

## 13. Gradle Shadow Plugin

With the Gradle Shadow Plugin, `mergeServiceFiles()` merges service descriptors and `manifest` sets the entry point.

Illustrative Groovy DSL example:

~~~groovy
plugins {
    id 'java'
    id 'com.gradleup.shadow' version '8.3.9'
}

tasks.named('shadowJar') {
    mergeServiceFiles()

    manifest {
        attributes('Main-Class': 'com.example.app.Main')
    }
}
~~~

Syntax and plugin IDs/versions can vary across Gradle and Shadow branches. Consult documentation for the exact version in use rather than treating this snippet as a universal project template.

### 13.1. `duplicatesStrategy` affects service merging

If duplicate handling drops colliding entries **before the transformer sees them**, service providers can silently disappear. When providers are missing, verify:

- Does `mergeServiceFiles()` actually execute?
- Where is `duplicatesStrategy` configured?
- Is any resource `exclude` dropping service files?
- Did relocation omit updating provider names?
- Did `minimize()` strip dynamically loaded classes?

Inspect `META-INF/services` inside the output JAR directly rather than relying solely on build logs.

### 13.2. Reproducible builds

Repackaging can change entry order, timestamps, and compression metadata, altering archive checksums. Configure reproducible archive settings if required by the project, while still verifying signatures, provenance, and service correctness independently.

## 14. Spring Boot executable JAR: nested dependencies and launcher

A Spring Boot executable JAR differs structurally from a flat shaded JAR:

~~~text
app.jar
├── META-INF/MANIFEST.MF
├── BOOT-INF/
│   ├── classes/
│   │   ├── com/example/app/Application.class
│   │   └── META-INF/services/...
│   └── lib/
│       ├── framework.jar
│       └── driver.jar
└── org/springframework/boot/loader/...
~~~

Spring Boot's bootstrap launcher loads nested dependencies. The manifest sets `Main-Class` to the Boot launcher while keeping the application entry point in `Start-Class`.

Conceptual example:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.app.Application
~~~

The launcher class name can change across Spring Boot releases. Replacing `Main-Class` directly with the application class without a compatible nested loader prevents the standard Java launcher from finding dependencies inside `BOOT-INF/lib`.

### 14.1. Signed nested JARs do not mean the outer JAR is signed

When a signed dependency is embedded **byte-for-byte** as a nested JAR, its internal signature is not altered simply by packaging the outer archive. Even so, that dependency signature does not make the outer `app.jar` signed or trusted as a whole.

If a build unpacks, relocates, and merges dependencies instead, the same signature invalidation rules as shaded JARs apply.

### 14.2. Test the real launch path

~~~bash
java -jar app.jar
~~~

This is the path to test whenever production runs the Spring Boot executable archive. Running `java -cp target/classes:...` uses a different class loader and resource layout and may miss packaging regressions.

## 15. Common post-repackaging failure table

| Symptom | Where to check |
|---|---|
| `no main manifest attribute` | `MANIFEST.MF` in final artifact is missing `Main-Class` |
| `Could not find or load main class` | Entry-point class, launcher, archive layout, and JAR entries |
| `NoClassDefFoundError` after `java -jar` | Manifest `Class-Path`, dependency locations, nested loader |
| `Invalid signature file digest` | Manifest or signed entries changed while stale signature metadata remained |
| `SHA-256 digest error` | Signed entry no longer matches its digest |
| `signer information does not match` | Classes in the same package carry differing signer identities |
| `ServiceConfigurationError: Provider ... not found` | Wrong provider name after relocation or class pruned by minimizer |
| `ServiceConfigurationError: ... not a subtype` | Wrong SPI implementation, duplicate class loaders, or API version mismatch |
| Only one provider remains | `META-INF/services` files overwritten instead of merged |
| Module not found | Lost `Automatic-Module-Name`, broken `module-info.class`, or module path mismatch |
| Empty `ServiceLoader` on module path | `uses`/`provides`, module graph, class loader/layer |
| MR-JAR misses JDK-specific implementation | Lost `Multi-Release: true` or misplaced versioned classes |
| Framework feature fails to activate | Framework-specific resource metadata overwritten or excluded |
| Tests pass locally yet production fails | Unit tests did not execute the packaged artifact |

### 15.1. Failures can surface late

A provider may be loaded only when a user enables a rarely used module, and a signed resource may only be verified when that feature is accessed. A green healthcheck alone is therefore insufficient to declare the artifact healthy.

### 15.2. Do not diagnose from exception class alone

`ClassNotFoundException` can stem from the manifest, relocation, module resolution, or minimization. `SecurityException` can involve signatures, package sealing, or signer mismatch. Read the underlying cause and inspect the packaged artifact rather than guessing from a superficial pattern.

## 16. Commands to inspect a JAR after packaging

### 16.1. List entries

~~~bash
jar --list --file app.jar
~~~

Look for:

~~~text
META-INF/MANIFEST.MF
META-INF/services/
META-INF/*.SF
META-INF/*.RSA
META-INF/*.DSA
META-INF/*.EC
module-info.class
META-INF/versions/
~~~

On Unix shells you can filter with `grep`; on Windows PowerShell use `Select-String`. Listing confirms paths exist, not that file contents are correct.

### 16.2. Inspect the manifest

If `unzip` is installed:

~~~bash
unzip -p app.jar META-INF/MANIFEST.MF
~~~

Otherwise, extract into a **separate temporary** directory using `jar --extract` and read the manifest:

~~~bash
mkdir inspect-jar
cd inspect-jar
jar --extract --file ../app.jar META-INF/MANIFEST.MF
~~~

These examples show Unix shell paths. Only extract trusted artifacts into isolated locations; never unpack untrusted archives into directories holding sensitive data.

### 16.3. Verify signatures

~~~bash
jarsigner -verify -strict -verbose -certs app.jar
~~~

Read the verification summary and warnings regarding signers, certificate chains, and disabled algorithms. If policy leaves the artifact unsigned, document that explicitly rather than assuming vendor signatures survived shading.

### 16.4. Inspect service files

~~~bash
unzip -p app.jar META-INF/services/com.example.spi.Compressor
~~~

Compare contents against expected providers. If classes were relocated, the file must contain the relocated names.

### 16.5. Inspect module descriptors and multi-release entries

~~~bash
jar --describe-module --file app.jar
jdeps --multi-release 17 --summary app.jar
~~~

These commands provide supporting static evidence; they do not replace running integration tests against the artifact.

### 16.6. Launch the final artifact

~~~bash
java -jar app.jar
~~~

For named modules:

~~~bash
java --module-path mods \
     --module com.example.app/com.example.app.Main
~~~

Choose the exact launcher used in production. A Spring Boot application relying on its nested loader cannot be equivalently validated by launching an arbitrary main classpath.

## 17. Testing `ServiceLoader` on the final artifact

A smoke test should verify that providers can actually be instantiated and invoked.

~~~java
import com.example.spi.Compressor;
import java.util.HashSet;
import java.util.ServiceLoader;
import java.util.Set;

public final class ServiceSmokeTest {
    public static void main(String[] args) {
        Set<String> names = new HashSet<>();

        for (Compressor provider :
                ServiceLoader.load(Compressor.class)) {
            names.add(provider.name());
            byte[] output = provider.compress(new byte[] {1, 2, 3});

            if (output == null) {
                throw new AssertionError(
                    "Null result from " + provider.getClass());
            }
        }

        if (!names.contains("fast") ||
            !names.contains("compact")) {
            throw new AssertionError(
                "Missing provider(s): " + names);
        }

        System.out.println("Providers: " + names);
    }
}
~~~

This test assumes the deployment **must provide** both providers. In production code, tailor expected providers to the specific artifact or profile. Never validate only text metadata; execute real class loading and method invocation.

A helpful matrix:

| Environment | What to test |
|---|---|
| Java classpath, separate dependencies | Provider discovery before repackaging |
| Flat shaded JAR | Provider discovery after merging/relocation |
| Spring Boot executable JAR | Discovery via nested JAR launcher |
| JPMS module path | `uses`/`provides` and module resolution |
| Minimum supported JDK | Bytecode compatibility, MR-JAR base, providers |
| Newer JDK | MR-JAR variants and API behavior |

If a provider fails to appear, pinpoint whether it is absent from the service file, missing its class file, omitted by module resolution, or hidden by class-loader hierarchy.

## 18. CI pipelines and signing policy

A reliable pipeline separates stages cleanly:

~~~text
Compile/test
      |
      v
Package/shade/repackage
      |
      v
Inspect artifact:
    manifest / module-info / MR-JAR
    META-INF/services / framework metadata
    signatures / licenses
      |
      v
Sign final artifact (if required)
      |
      v
Verify signing + trust policy
      |
      v
Run black-box launch test
      |
      v
Run ServiceLoader/framework integration tests
      |
      v
Publish immutable artifact + checksum/SBOM
~~~

### 18.1. Separate unit tests from packaging tests

Unit tests usually run against Maven or Gradle's test runtime classpath. Packaging tests must verify the actual deliverable binary. With Maven Shade there may be both `original-...jar` and the shaded JAR; with the Spring Boot plugin the repackaged artifact differs from the plain JAR. Target the true final artifact explicitly.

### 18.2. Control provenance

When consuming signed dependencies, track their origins, versions, checksums, and licenses. When building a new combined artifact, never claim upstream dependency signatures vouch for the entire shaded JAR. An SBOM or lockfile records constituent inputs, though it does not replace artifact signing or runtime checks.

### 18.3. Do not modify an artifact after signing

A late "inject configuration" step modifying a signed JAR invalidates its signature. Externalize environment configuration or complete every archive transformation **before signing**. If policy requires modifying a signed entry, re-sign through the release workflow and publish updated hashes.

### 18.4. Packaging rollback still has prerequisites

If a new release changes archive layout, launcher, JPMS name, or plugin discovery, rolling back to the previous binary requires compatible runtime settings, configuration, and data produced by the newer release. Rolling back a JAR does not automatically undo database, event schema, or external service metadata changes.

## 19. Watchouts when upgrading the JDK

### 19.1. Newer JDKs may tighten signature and algorithm policies

JARs signed with weak algorithms can raise warnings or behave differently on newer JDKs under updated security policies. Review target JDK notes alongside real signers and certificates. Never weaken global security policies merely to keep an obsolete dependency; prefer updated artifacts from trusted publishers.

### 19.2. Java 9+ changed the modularization model

A JAR running cleanly on the classpath does not automatically preserve behavior on the module path. Service provider declarations, `exports`/`opens`, and module resolution form strict contracts. If repackaging drops a module name or descriptor, the bug is not in `ServiceLoader` source code.

### 19.3. Build tool upgrades can change duplicate handling

Upgrading Gradle or Maven plugins in the same migration can shift default resource merging, timestamps, or exclusions. If service providers vanish, diff the before/after JARs and run the identical artifact on both JDKs if possible to isolate whether the regression stems from **artifact transformation** or **runtime JDK behavior**.

### 19.4. Compiler target does not govern the whole artifact

A JAR whose main class targets Java 17 can still embed a provider class compiled for Java 21. If that provider loads only on a rare branch under Java 17, failures arrive late. Verify bytecode versions across **all runtime dependencies and variants**, not just main classes.

### 19.5. Native-image metadata is a distinct contract

With GraalVM Native Image, reflection, services, and resources impose specific build-time requirements. A JAR running smoothly on HotSpot may still lack sufficient metadata for native-image compilation. When enabling native-image plugins, check configuration guidelines for the exact framework and GraalVM release.

## 20. Common misconceptions

**"A JAR is just a ZIP containing class files."** Incomplete. Manifest, signatures, module descriptors, and service metadata can dictate runtime behavior.

**"Having `Main-Class` in the POM guarantees the final artifact has `Main-Class`."** Not guaranteed; the final repackaging or shading task may write a different manifest.

**"Manifest `Class-Path` handles nested JARs automatically."** False. Nested libraries require a custom class loader or launcher built for that archive layout.

**"`Automatic-Module-Name` fully replaces `module-info.class`."** False. It primarily fixes an automatic module name; an explicit module descriptor defines far broader contracts.

**"Keeping `META-INF/versions` is enough for an MR-JAR."** False; `Multi-Release: true` and compliant class layout are also required.

**"Source JAR signatures stay valid after relocation."** False whenever signed contents or manifest digests are altered.

**"Just deleting `*.SF` and `*.RSA` fixes everything."** False. Removing signatures alters integrity and provenance, and is valid only under authorized policy for publishing a newly created artifact.

**"A passing `jarsigner -verify` means no security issues exist."** False. Signing confirms integrity and signer authenticity under a trust model, not vulnerability scanning.

**"A service interface only ever has one provider."** False. Multiple JARs can register providers, so colliding service files must be merged properly.

**"If the service file exists, the provider will always work."** False. The provider class may be pruned, relocated incorrectly, missing a proper constructor, or blocked by module/class-loader rules.

**"Maven Shade `ServicesResourceTransformer` handles every Spring resource."** False. Framework-specific metadata requires framework-aware transformers or merge rules.

**"Passing unit tests from `target/classes` proves the shaded JAR runs."** False. Always test the final packaged artifact using the real launcher.

## 21. Release checklist

- [ ] Identified the exact artifact to deploy, along with checksums and plugin versions.
- [ ] Listed final JAR entries using `jar --list`.
- [ ] Read the actual `META-INF/MANIFEST.MF` and confirmed `Main-Class`/launcher settings.
- [ ] Checked `Class-Path` and how external dependencies are distributed.
- [ ] Reviewed `Automatic-Module-Name`, `module-info.class`, and module path strategy.
- [ ] If MR-JAR is used, confirmed `Multi-Release: true` is preserved and tested across supported JDKs.
- [ ] Checked sealing and digest sections in the manifest if present.
- [ ] Identified any signed dependencies and provenance policy.
- [ ] Ensured stale signatures were not carried over after modifying signed entries.
- [ ] If the final artifact requires signing, signed **after** packaging/shading and verified it.
- [ ] Merged colliding `META-INF/services` files properly.
- [ ] Updated provider and service names after relocation.
- [ ] Verified minimization did not prune dynamically loaded classes.
- [ ] Preserved required framework metadata, license files, and notice files.
- [ ] Executed black-box `java -jar`/`java --module` runs against the final artifact.
- [ ] Executed integration tests covering `ServiceLoader` and provider behavior.
- [ ] Checked class-file versions of all providers and dependencies against the minimum supported JDK.
- [ ] Added CI gates for manifest, signing, module, and service metadata.
- [ ] Archived checksums, SBOM/provenance, and release notes.
- [ ] Defined a rollback strategy if archive layout, modules, or launcher changed.

## 22. Technical references

- [JAR File Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/jar/jar.html): manifest, JAR signing, and multi-release JARs.
- [`jar` command reference](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jar.html): creating, extracting, listing, and describing JAR modules.
- [`jarsigner` command reference](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jarsigner.html): signing and verifying artifacts.
- [`ServiceLoader` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html): service provider configuration and named modules.
- [Maven Shade Plugin – Resource Transformers](https://maven.apache.org/plugins/maven-shade-plugin/examples/resource-transformers.html): manifest and service resource transformers.
- [Gradle Shadow – Merging Service Descriptor Files](https://gradleup.com/shadow/configuration/merging/#merging-service-descriptor-files): merging provider metadata.
- [Spring Boot Maven Plugin](https://docs.spring.io/spring-boot/maven-plugin/packaging.html): executable archives and nested JAR launcher.
- [JEP 238 – Multi-Release JAR Files](https://openjdk.org/jeps/238): goals and MR-JAR specification rules.

Always check the documentation for the **exact JDK, plugin, and framework versions** used by your project. Launcher class paths, Gradle DSL syntax, default merge behavior, and permitted signature algorithms can change across releases.

## 23. Conclusion

**Repackaging a JAR modifies runtime contracts**, not merely bytecode compression. `MANIFEST.MF` governs launcher, module, and MR-JAR metadata; JAR signatures bind to signed entries and cannot be treated as valid once the artifact is altered; `META-INF/services` governs which providers `ServiceLoader` can discover. Each kind of metadata must be handled according to its rules and security policy.

For safe Java Advance Compatibility Migration, build artifacts with a clear layout, merge service registrations when shading, preserve required manifest attributes, avoid pretending upstream vendor signatures remain valid after content modifications, and sign the final artifact if policy requires it. **Validating source compilation alone is insufficient: inspect and execute the exact deliverable JAR on the target JDK**, verifying signatures, module/service metadata, and dynamically loaded resource behavior.
