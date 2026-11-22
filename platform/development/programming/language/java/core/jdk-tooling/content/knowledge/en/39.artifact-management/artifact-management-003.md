# Runtime Image Artifacts in Java

A **runtime image artifact** is a pre-built Java runtime package designed to run an application without requiring a full JDK installation on the target machine. Instead of shipping a standalone JAR and requiring operators to install the right Java version themselves, a development team can create a runtime image containing only the required modules, the application, a launcher, and accompanying configuration.

In the Java Platform Module System, the **jlink** tool links application modules, JDK modules, and transitive dependencies into a custom runtime image. The **jpackage** tool can take the application along with that runtime image to create an application image or native installers such as MSI, EXE, DEB, RPM, PKG, and DMG.

A runtime image is a type of build artifact. It must be built from versioned source code and a clearly specified toolchain, tested on the target platform, stored with checksums and metadata, and then promoted across environments using the exact same tested binary.

## 1. Where Does a Runtime Image Fit in CI/CD?

~~~text
Source + build configuration + JDK toolchain
                    |
                    v
            Compile and test
                    |
                    v
        Analyze application modules
                    |
                    v
             Build with jlink
                    |
                    v
        Verify runtime and launch app
                    |
                    v
       Package with jpackage if needed
                    |
                    v
      Checksum + SBOM + provenance + sign
                    |
                    v
       Publish immutable runtime artifact
                    |
                    v
      Promote the same artifact to target
~~~

Common outputs:

| Output | Contents | Usage |
|---|---|---|
| JAR | Application classes and resources | Runs on an existing Java runtime |
| Custom runtime image | Selected Java runtime modules and launcher | Distributes a standalone runtime |
| jpackage application image | Launcher, application payload, and runtime | Runs the application on the target machine |
| Native installer | OS-specific installer package | Installs the application for end users |
| OCI/container image | Filesystem image, runtime, app, and container configuration | Runs in Docker/Kubernetes |

Do not conflate a custom runtime image with a JDK or an OCI image. A runtime image typically excludes the compiler, debugger, and many JDK development tools. An OCI image is a container packaging layer that can contain a runtime image, the application, a base OS, and deployment configuration.

## 2. JDK, JRE, and Custom Runtime Images

The JDK is a development kit that typically includes the Java runtime along with tools such as javac, jlink, jpackage, javadoc, and jcmd.

A runtime image created by jlink keeps only the required runtime components. It may contain:

- The java executable and native launchers.
- Selected JDK modules.
- Runtime libraries and configuration.
- Legal files and runtime metadata.
- A custom launcher if configured via jlink.

A runtime image typically does not include javac, jshell, javadoc, jcmd, man pages, header files, or source archives. This is why a runtime image is small and well-suited for deployment.

### Distinguishing Bytecode Target from Runtime Version

These two concepts are independent:

- javac --release 17 restricts the APIs and bytecode that the source is allowed to use for Java 17 compatibility.
- jlink pulls runtime modules from the JDK that is running the jlink command.

Therefore, if you compile an application with --release 17 but run jlink from JDK 26, the resulting runtime image is a JDK 26 runtime. To package a Java 17 runtime, use the corresponding JDK 17 to run jlink and build the image. You cannot use --release to turn a JDK 26 runtime into a JDK 17 runtime.

You should record the application version, Java release target, and the actual JDK vendor/version that produced the runtime image separately.

## 3. Structure of a Runtime Image

A runtime image created by jlink typically looks like this:

~~~text
runtime-image/
  bin/
    java
    keytool
    runtime-demo
  conf/
  include/
  legal/
  lib/
    modules
    security/
  release
~~~

The exact files depend on the JDK, modules, and build options. Some components can be stripped out using jlink plugins.

| Component | Role |
|---|---|
| bin/java | Java launcher |
| bin/keytool | Key/certificate management tool if retained |
| conf | Runtime configuration |
| legal | Module licenses and legal notices |
| lib/modules | Linked runtime modules |
| release | Metadata such as Java version, implementor, and module set |

Do not rely on a fixed file list to identify an image. Verify the runtime using the java executable, --list-modules, --version, and the actual application.

## 4. Module Graph and Determining Required Modules

jlink operates on the module graph. An application module declares its module dependencies in module-info.java:

~~~java
module com.acme.runtimeimage {
    requires java.logging;
}
~~~

In this example, the application requires the java.logging module. jlink resolves the root modules and their transitive dependencies.

If the module descriptor declares inaccurate requires directives, the runtime image may miss necessary modules or include unnecessary ones. Inspect the module graph before optimizing size.

### Using jdeps to Analyze Dependencies

For a modular application, jdeps can analyze modules and dependencies:

~~~bash
jdeps --module-path mods --module com.acme.runtimeimage --list-deps
~~~

For a JAR application running on the classpath with a lib directory containing dependencies:

~~~bash
jdeps --multi-release 17 --print-module-deps --class-path "lib/*" application.jar
~~~

The --print-module-deps option prints a comma-separated list of modules. The output can be used as the input list for jlink's --add-modules option.

jdeps analyzes dependencies that it can detect from bytecode and module metadata. Reflection, dynamically generated class names, ServiceLoader, JNI, native libraries, and resources loaded by name may require additional verification. Do not treat jdeps output as the sole proof that the runtime image is complete.

### Inspecting the Module Descriptor

You can inspect the module inside a JAR:

~~~bash
jar --describe-module --file application.jar
~~~

Inspect module dependencies:

~~~bash
jdeps --module-path mods --module com.acme.runtimeimage --check com.acme.runtimeimage
~~~

If the application uses non-modular libraries, check their automatic module names and compatibility when placing them on the module path. If the application still runs on the classpath, choose an appropriate packaging and dependency analysis approach rather than assuming every JAR is a named module.

## 5. Creating a Runtime Image with jlink

jlink takes a module path, a list of root modules, and an output directory:

~~~bash
jlink --module-path mods:$JAVA_HOME/jmods --add-modules com.acme.runtimeimage --output build/runtime-image
~~~

Where:

- --module-path specifies where to find application modules and JDK modules.
- --add-modules specifies the root modules to include in the image.
- --output specifies the output directory for the generated runtime image.
- jlink automatically adds required transitive dependencies.

If only standard JDK modules are used, jlink's default module path is the jmods directory inside JAVA_HOME. When passing a custom module path, make sure jlink can still locate the required JDK modules.

### Size Optimization

Plugins can be used to reduce image size:

~~~bash
jlink --module-path mods:$JAVA_HOME/jmods --add-modules com.acme.runtimeimage --output build/runtime-image --strip-debug --no-header-files --no-man-pages --compress=zip-6
~~~

| Option | Effect | Notes |
|---|---|---|
| --strip-debug | Strips debug information | Makes direct debugging from the runtime image harder |
| --no-header-files | Excludes C/C++ header files | Suitable for standard runtimes |
| --no-man-pages | Excludes man pages | Reduces unnecessary files on the target machine |
| --compress=zip-6 | Compresses resources in the image | Balances size and decompression overhead |
| --include-locales | Keeps only selected locale data | Requires the jdk.localedata module |
| --bind-services | Links service provider modules | Use when the application requires service binding |

In JDK 26, compression uses the form zip-0 through zip-9; zip-6 is the default. Legacy numeric values such as --compress=2 are deprecated; use the zip-6 syntax instead.

Do not enable every size-reduction option mechanically. If the application needs locales, fonts, timezone data, crypto providers, or native libraries, verify them inside the runtime image after optimization.

### Creating a Custom Launcher

You can create a launcher so operators do not need to type the module and main class:

~~~bash
jlink --module-path mods:$JAVA_HOME/jmods --add-modules com.acme.runtimeimage --launcher runtime-demo=com.acme.runtimeimage/com.acme.runtimeimage.Main --output build/runtime-image
~~~

The runtime-demo launcher invokes the module's main class. The launcher is created in the bin directory of the image. The module/main syntax is the module name followed by a slash and the fully qualified main class name.

## 6. Java 17+ Example: Creating a Runnable Runtime Image

The following example creates a small modular application that uses java.logging. It can be compiled with JDK 17 or later and packaged into a runtime image using jlink from the JDK you intend to distribute.

Source structure:

~~~text
runtime-image-demo/
  src/
    com.acme.runtimeimage/
      module-info.java
      com/
        acme/
          runtimeimage/
            Main.java
  mods/
  build/
~~~

File src/com.acme.runtimeimage/module-info.java:

~~~java
module com.acme.runtimeimage {
    requires java.logging;
}
~~~

File src/com.acme.runtimeimage/com/acme/runtimeimage/Main.java:

~~~java
package com.acme.runtimeimage;

import java.util.logging.Logger;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        String loggerName = Logger.getLogger(Main.class.getName()).getName();
        System.out.println(
            "RUNTIME_IMAGE_OK module=" + Main.class.getModule().getName()
            + " logger=" + loggerName
        );
    }
}
~~~

### Compiling on Linux or macOS

From the project directory:

~~~bash
mkdir -p mods/com.acme.runtimeimage build
javac --release 17 -d mods/com.acme.runtimeimage src/com.acme.runtimeimage/module-info.java src/com.acme.runtimeimage/com/acme/runtimeimage/Main.java
~~~

### Compiling on Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force mods\com.acme.runtimeimage, build | Out-Null
javac --release 17 -d mods\com.acme.runtimeimage src\com.acme.runtimeimage\module-info.java src\com.acme.runtimeimage\com\acme\runtimeimage\Main.java
~~~

### Creating the Runtime Image on Linux or macOS

~~~bash
jlink --module-path "mods:$JAVA_HOME/jmods" --add-modules com.acme.runtimeimage --output build/runtime-image --strip-debug --no-header-files --no-man-pages --compress=zip-6 --launcher runtime-demo=com.acme.runtimeimage/com.acme.runtimeimage.Main
~~~

### Creating the Runtime Image on Windows PowerShell

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.acme.runtimeimage --output build\runtime-image --strip-debug --no-header-files --no-man-pages --compress=zip-6 --launcher runtime-demo=com.acme.runtimeimage/com.acme.runtimeimage.Main
~~~

Run using the newly created runtime image.

Linux/macOS:

~~~bash
build/runtime-image/bin/java -m com.acme.runtimeimage/com.acme.runtimeimage.Main
~~~

Windows PowerShell:

~~~powershell
.\build\runtime-image\bin\java.exe -m com.acme.runtimeimage/com.acme.runtimeimage.Main
~~~

Exact stdout:

~~~text
RUNTIME_IMAGE_OK module=com.acme.runtimeimage logger=com.acme.runtimeimage.Main
~~~

Test the custom launcher if needed:

~~~bash
build/runtime-image/bin/runtime-demo
~~~

On Windows, the launcher filename depends on the launcher format generated by the JDK; inspect the bin directory contents before invoking it. Using bin/java.exe -m ... is a consistent way to test module launching across platforms.

## 7. Verifying the Runtime Image After Creation

Do not treat a jlink exit code of 0 as sufficient proof on its own. Verify the image across multiple layers.

### Checking the Java Version

Linux/macOS:

~~~bash
build/runtime-image/bin/java --version
~~~

Windows:

~~~powershell
.\build\runtime-image\bin\java.exe --version
~~~

The displayed version must match the JDK used to build the runtime image and the release policy.

### Checking the Module List

~~~bash
build/runtime-image/bin/java --list-modules
~~~

Compare the actual modules against the module manifest or expected module set. In particular, check required modules such as java.logging, java.sql, java.xml, java.desktop, jdk.crypto.ec, and jdk.localedata when the application needs them.

### Checking Module Resolution

~~~bash
build/runtime-image/bin/java --validate-modules
~~~

This command helps detect conflicts or module resolution issues. It does not replace integration tests.

### Inspecting Image Contents

You can inspect the module image contents using:

~~~bash
jimage list build/runtime-image/lib/modules
~~~

You can view metadata in the release file at the root of the runtime image. This file helps trace the implementor, Java version, and module set.

### Smoke Tests and Integration Tests

Run the application using the java executable inside the runtime image, not the java installation on the build machine. Verify:

- The main class starts and exits with the expected exit code.
- Resources are loaded from the runtime image.
- TLS/HTTPS and certificate providers work properly.
- Locale, timezone, and encoding are appropriate.
- ServiceLoader discovers providers.
- JNI or native libraries load on the target machine.
- File system paths, permissions, and working directory are valid.
- Database, network, and required external service connections succeed.

A runtime image may start up successfully yet still miss a module or resource that is only used in a rarely executed code path. Use integration tests with coverage for those paths.

## 8. ServiceLoader and Service Binding

Some libraries locate implementations via Java ServiceLoader. Service providers may reside in a different module from the application module.

jlink provides the option:

~~~bash
--bind-services
~~~

This option links service provider modules and their dependencies into the runtime image. Inspect the required modules/providers before deciding to enable it.

An important change: starting in JDK 25, jpackage no longer automatically includes service bindings in the runtime image it creates. If an application relies on service providers discovered through binding, pass --bind-services inside --jlink-options.

Example:

~~~bash
jpackage --name RuntimeImageDemo --input app-input --main-jar app.jar --jlink-options "--strip-native-commands --strip-debug --no-man-pages --no-header-files --bind-services"
~~~

When specifying --jlink-options, re-list the default options you still want to retain. Do not assume a runtime image created by jpackage in JDK 25+ has the same module set as an image from JDK 24 or earlier.

## 9. Locales, Native Libraries, and Runtime Resources

### Locale Data

If the application needs locales beyond the runtime's default set, add jdk.localedata and select the locales:

~~~bash
jlink --add-modules com.acme.runtimeimage,jdk.localedata --include-locales=en,vi --output build/runtime-image
~~~

Locale names use BCP 47 language tags. Include only the locales the application actually needs to avoid adding unnecessary data.

### Crypto Providers and TLS

HTTPS or TLS applications may require providers such as SunEC or security-related modules. Do not remove modules just because jdeps does not detect direct call paths. Test server handshakes and certificate chains inside the runtime image.

### JNI and Native Libraries

jlink only resolves Java modules. JNI libraries and native dependencies must be distributed separately or placed appropriately in the application image. They typically depend on OS, CPU architecture, libc, or ABI.

Verify:

- Native library filenames and load paths.
- Target OS and architecture.
- Dynamic library dependencies.
- Execute and read file permissions.
- How java.library.path is configured if the application requires it.

## 10. jpackage: Packaging an Application Image with a Runtime

jpackage creates an application image or native installer. If no runtime image is provided, jpackage invokes jlink to build one automatically. If you already have a tested runtime image, pass it using --runtime-image.

Example with a modular application:

~~~bash
jpackage --type app-image --name RuntimeImageDemo --module-path mods --module com.acme.runtimeimage/com.acme.runtimeimage.Main --runtime-image build/runtime-image --dest build/packages
~~~

An application image typically contains:

- The application launcher.
- The application JAR or module payload.
- Launcher configuration files.
- The runtime image inside the package directory.
- Resources such as icons and metadata files if declared.

An application image can run without a separate Java installation, provided the runtime image and native dependencies match the target machine.

### Creating Native Installers

Common formats:

| Platform | Format |
|---|---|
| Windows | exe, msi |
| Linux | deb, rpm |
| macOS | pkg, dmg |

Example on Windows:

~~~powershell
jpackage --type msi --name RuntimeImageDemo --module-path mods --module com.acme.runtimeimage/com.acme.runtimeimage.Main --runtime-image build\runtime-image --dest build\installers
~~~

Example on Linux:

~~~bash
jpackage --type deb --name runtime-image-demo --module-path mods --module com.acme.runtimeimage/com.acme.runtimeimage.Main --runtime-image build/runtime-image --dest build/installers
~~~

jpackage builds native packages for the host platform. Cross-platform packaging is not supported; you need corresponding build agents for Windows, Linux, and macOS. Windows and macOS may require additional tools to build installers or sign packages.

### When to Use app-image vs. Installer?

- app-image is suitable for testing or distributing a runnable directory.
- An installer is suitable when you need installation flows, shortcuts, menu entries, file associations, or OS integration.
- A plain runtime image is suitable when the application is deployed by scripts, a service manager, or a container without needing a native installer.

## 11. Runtime Image Artifacts vs. Container Images

A runtime image and a container image are two different artifacts.

| Characteristic | Runtime image | Container image |
|---|---|---|
| Primary contents | Selected Java runtime modules | Root filesystem and app/runtime |
| OS userland | Not a complete OS image | Includes a base image and userland |
| Direct execution | On a compatible OS/architecture | Via a container runtime |
| Versioning | JDK vendor/version, module set, app version | Image tag and immutable digest |
| Storage | Artifact repository or archive store | Container registry |

A pipeline can build and test the runtime image first, then place the runtime image and application into an OCI image. When promoting the container, use the exact digest of the tested OCI image.

Do not build a runtime image for one OS and expect it to run as-is on another OS. A runtime image contains native binaries and libraries specific to the platform on which it was built.

## 12. Versioning and Metadata for Runtime Images

A runtime image needs to be identified by more information than just the application version.

Recommended metadata:

- Application name and version.
- Git commit SHA or source revision.
- JDK vendor, full version, and build number.
- OS and CPU architecture.
- Java release target of the application.
- Actual module list.
- jlink/jpackage options.
- Native library inventory.
- Build pipeline ID and build timestamp.
- SHA-256 digest.
- SBOM and provenance references.

Example archive names:

~~~text
runtime-image-demo-1.2.0-jdk26-linux-x64.tar.gz
runtime-image-demo-1.2.0-jdk26-windows-x64.zip
runtime-image-demo-1.2.0-jdk26-macos-aarch64.tar.gz
~~~

Filenames help with quick identification; metadata and checksums are the authoritative verification basis. Never reuse the same release version for two images that have different module sets, JDK patches, or binaries.

The release file in the runtime image can be stored alongside a build manifest to verify against the expected version.

## 13. Reproducible Builds and Immutability

Two runtime images built from the same source are not guaranteed to have the same byte hash if the JDK patch, vendor, build options, or environment differ.

To improve reproducibility:

1. Pin the JDK distribution and exact version.
2. Pin application dependencies and the module set.
3. Record the full jlink/jpackage command or options file.
4. Standardize the build environment and OS image.
5. Avoid embedding dynamic timestamps into application resources unless necessary.
6. Record native dependencies and build tool versions.
7. Rebuild independently and compare archive checksums.
8. Once a release is published, never overwrite an artifact with the same version.

Reproducibility must be measured by rebuilding and comparing outputs. Do not assume jlink images always produce identical hashes across all vendors or JDK patches.

## 14. Checksums, SBOMs, and Signatures

If a runtime image is stored as a directory, archive it before computing the checksum. Compute the checksum after all modifications to the archive are complete.

Linux:

~~~bash
tar -czf runtime-image-demo.tar.gz runtime-image
sha256sum runtime-image-demo.tar.gz
~~~

Windows PowerShell:

~~~powershell
Compress-Archive -Path runtime-image -DestinationPath runtime-image-demo.zip
Get-FileHash runtime-image-demo.zip -Algorithm SHA256
~~~

Checksums help detect file modification during storage or transfer. To authenticate the publisher, combine checksums with digital signatures or trusted provenance.

An SBOM should describe application dependencies, runtime modules, and native libraries included in the artifact. Scan runtime components to detect CVEs and license issues. Do not scan only the JAR and conclude the runtime image is safe; the runtime image also carries JDK modules and native components.

Store checksums, signatures, SBOMs, and provenance alongside the artifact or in release metadata. Never place private keys, keystore passwords, or tokens inside the runtime image.

## 15. Publishing and Promoting Runtime Images in CI/CD

A runtime image can be stored in a generic artifact repository, release storage, or object storage with versioning and immutability policies. If the runtime image is placed into an OCI image, publish the OCI artifact to a container registry.

Recommended workflow:

1. Check out source at a specific commit.
2. Install the exact JDK vendor/version for the target OS and architecture.
3. Compile and run tests.
4. Run jdeps to analyze dependencies and review the module set.
5. Create the runtime image with jlink.
6. Verify the module list, runtime version, and application startup.
7. Run integration tests on the target platform.
8. Create a jpackage application image or installer if needed.
9. Scan runtime modules, dependencies, and native libraries.
10. Generate the SBOM, checksum, signature, and provenance.
11. Publish the artifact with an immutable version.
12. Deploy to staging using the published artifact.
13. Once staging passes, promote the exact same digest to production.
14. Store test results and metadata linked to the digest.

For multiple platforms, use a build matrix by OS and architecture. Each platform artifact has its own digest. Never rebuild a runtime image when promoting the same platform artifact from staging to production.

## 16. Maintaining Runtime Images and Security Updates

A custom runtime image does not update itself when a new JDK security patch is released. The development team is responsible for updating and releasing a new image.

When upgrading the JDK:

- Read the vendor's release notes and security advisories.
- Update the JDK toolchain and base build environment.
- Re-run jdeps and rebuild the runtime image.
- Compare the module list and image size.
- Run compatibility, TLS, locale, JNI, and ServiceLoader tests.
- Scan for CVEs and check licenses.
- Generate new checksums/SBOM/provenance.
- Release a new runtime image version and promote it through the pipeline.

Never patch an already-released runtime image directly. Build a new artifact from a traceable build process.

## 17. Troubleshooting Runtime Images

| Symptom | Possible Cause | Resolution |
|---|---|---|
| jlink reports module not found | Module path is missing application or JDK modules | Check --module-path and the corresponding JDK/JMODs |
| jlink reports java.base cannot be resolved | Module path does not contain required JDK modules | Add the correct JDK jmods directory |
| Application throws ClassNotFoundException | Missing dependency or module | Run jdeps and check classpath/module path |
| NoClassDefFoundError only appears in production | Runtime code path requires an untested module/resource | Add integration tests running on the runtime image |
| ServiceLoader cannot find provider | Service binding is missing | Check providers and use --bind-services when needed |
| TLS handshake fails | Missing crypto provider or native support | Check security modules and test handshakes on the image |
| Locale displays incorrectly | Missing jdk.localedata or locale was stripped | Add the module and appropriate --include-locales |
| JNI UnsatisfiedLinkError | Native library is missing or wrong architecture | Check native dependencies, paths, and OS/CPU |
| Runtime image is larger than expected | Extra modules, locales, or resources | Inspect --list-modules and jimage list |
| App image runs but installer fails | Native package needs platform tools or options | Build on the target OS and check prerequisites |
| Image does not run on another machine | Different OS, architecture, ABI, or JDK runtime | Build separate artifacts for each target |
| jpackage image misses providers after JDK upgrade | JDK 25+ does not include service bindings by default | Pass --bind-services via --jlink-options |
| Runtime lacks security patches | Custom image does not auto-update | Rebuild from a patched JDK and release a new artifact |
| Checksum changes between builds | Different toolchain or build environment | Pin JDK, options, platform, and compare provenance |

## 18. Runtime Image Release Checklist

Before publishing, confirm:

- [ ] JDK vendor, full version, and target OS/architecture are pinned.
- [ ] Java compile release is distinguished from JDK runtime version.
- [ ] Module set is identified and reviewed.
- [ ] Dynamic dependencies, ServiceLoader, and JNI have been verified.
- [ ] jlink creates the image successfully.
- [ ] java --version and java --list-modules match expectations.
- [ ] java --validate-modules reports no errors.
- [ ] Application runs using the java executable inside the runtime image.
- [ ] Integration tests run in a production-like environment.
- [ ] Locales, TLS, native libraries, and resources have been verified.
- [ ] jpackage app-image or installer is tested if applicable.
- [ ] SBOM, checksum, signature, and provenance are stored.
- [ ] Artifact has an immutable version and digest.
- [ ] Staging and production use the same artifact digest.
- [ ] A rebuild plan is in place for JDK security updates.

## 19. Key Takeaways

- A runtime image is a Java runtime containing only the selected modules and dependencies needed to run an application.
- jlink creates a custom runtime image from the module graph and JDK modules.
- jpackage creates an application image or installer and can use a provided runtime image.
- A runtime image is not a full JDK and lacks development tools such as javac.
- javac --release 17 does not force jlink to produce a Java 17 runtime; the runtime version depends on the JDK running jlink.
- jdeps helps analyze dependencies but may miss reflection, ServiceLoader, JNI, and dynamic loading.
- jlink provides options such as strip-debug, no-header-files, no-man-pages, compress, include-locales, and bind-services.
- Starting in JDK 25, jpackage does not automatically include service bindings; use --bind-services when the application needs them.
- Runtime images are tied to OS and architecture; a build matrix must produce an image for each target.
- Test using the runtime image itself and the application inside it.
- Record the module list, JDK version, checksums, SBOM, and provenance.
- Runtime images do not receive security updates automatically; you must rebuild and release a new artifact.
- Build once per target, test it, and promote the same digest across environments.

## Official References

- [The jlink Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html)
- [The jdeps Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html)
- [The jpackage Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html)
- [Packaging Overview — JDK 26](https://docs.oracle.com/en/java/javase/26/jpackage/packaging-overview.html)
- [Packaging Tool User's Guide — JDK 26](https://docs.oracle.com/en/java/javase/26/jpackage/index.html)
- [The java Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [JAR File Specification — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/jar/jar.html)
