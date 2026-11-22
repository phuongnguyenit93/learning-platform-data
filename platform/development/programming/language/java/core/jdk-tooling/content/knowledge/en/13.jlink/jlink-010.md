# Testing a Runtime Image Created with jlink

## Objectives

After this lesson, you will be able to plan tests for a custom runtime image created by jlink; verify that the image contains the correct modules and Java version; run the application using the packaged runtime itself; detect missing modules, service providers, locales, security providers, or native libraries; test the launcher and deployment environment; and integrate runtime image tests into CI before release.

## 1. What Is a Runtime Image?

A **runtime image** is a Java environment capable of running an application, packaged into a self-contained directory. With jlink, you select the required modules and the tool links them along with their transitive dependencies to build a custom image.

A runtime image typically contains:

- bin/java: the Java launcher.
- lib/modules: the repository containing the modules linked into the image.
- conf: runtime configuration.
- legal: license information for the packaged components.
- release: metadata for the runtime build.
- Other files depending on the operating system, JDK version, and build options.

The internal layout can vary by platform and version. When testing, invoke the public launcher in bin and verify application behavior rather than relying on every internal file.

A runtime image created by jlink is usually smaller than a full JDK because it only includes the selected modules and their required dependencies. It may not include development tools such as javac, jar, javadoc, jcmd, or jdeps. Those tools are normally used during the build/test phase; the delivered runtime image only needs the components required to run the application.

**Testing a runtime image** means verifying that the image can actually run the application on the target environment with the expected features, configuration, dependencies, and behavior. A successful jlink build only proves that the tool generated an image; it does not prove that the application runs correctly.

## 2. Why Does an Application Work on a Full JDK but Fail on a Runtime Image?

Common risks include:

- **Missing modules:** the application uses XML, logging, desktop, naming, crypto, or other APIs whose corresponding module was not included in the image.
- **Missing service providers:** the application uses ServiceLoader, a JDBC driver, a security provider, or an SPI, but the provider module was not linked.
- **Reflection and frameworks:** frameworks load classes by name, scan packages, or access members via reflection that static dependency analysis does not fully detect.
- **Resources and locales:** missing resource bundles, locale data, charsets, or configuration files.
- **TLS and security:** missing security providers, truststores, certificates, or algorithms used by the application.
- **Native libraries:** missing JNI/JNA libraries, wrong CPU architecture, wrong ABI, or missing operating system libraries.
- **Environment differences:** the runtime executes on a container/server whose libc, timezone, certificate store, file permissions, and environment variables differ from the build machine.
- **Incorrect launcher:** scripts use the wrong main class, module path, classpath, JVM options, or working directory.
- **Java version mismatch:** class files, APIs, or preview features are incompatible with the runtime image.

Tests must run using the Java executable inside the image itself. If a test command accidentally invokes Java from PATH or JAVA_HOME of a full JDK, the application may succeed even though the runtime image is missing modules.

## 3. Defining Test Scope and Baseline

Before testing, record the artifact details:

| Information | What to Confirm |
|---|---|
| JDK used to build the image | Vendor, full version, and update level |
| Java feature release | For example 17, 21, or 25 |
| Operating system | Windows, Linux, or macOS |
| CPU architecture | x64, AArch64/ARM64, or supported architecture |
| Application type | Modular application or classpath application |
| Module roots | Required application modules and JDK modules |
| Service providers | JDBC, logging, crypto, plugin, or SPI providers |
| jlink options | --bind-services, compression, locale, launcher, and plugins |
| Runtime target | Physical machine, VM, container, or installer package |
| Runtime configuration | JVM flags, system properties, environment variables, and configuration files |

An image built on Linux x64 is not a portable artifact that can be copied to Windows or macOS and executed. A runtime image contains native components and is built for a specific platform. Build and test the image on each OS and architecture that the product supports.

If the product releases multiple runtime variants, each variant is an artifact that must be tested independently. Save the module list and runtime properties as a baseline to compare across builds.

## 4. Analyzing Dependencies Before Building the Image

Effective testing starts by identifying the modules the application requires.

### Using jdeps

jdeps analyzes application package/class dependencies and can print the list of required JDK modules:

~~~bash
jdeps --print-module-deps app.jar
~~~

If you need to select the version for a multi-release JAR:

~~~bash
jdeps --multi-release 17 --print-module-deps app.jar
~~~

If the application requires external libraries outside the main JAR, specify the corresponding classpath:

~~~bash
jdeps --class-path "lib/*" --print-module-deps app.jar
~~~

For a modular application, specify the module path and the module to analyze:

~~~bash
jdeps --module-path mods --print-module-deps --module com.example.app
~~~

The --print-module-deps output is a comma-separated list of module dependencies. Use this output to help determine --add-modules when building the image; application modules still need to be included in the root modules if it is a modular application.

### Limitations of Static Analysis

jdeps does not guarantee finding every dependency loaded at runtime. Perform a manual review if the application uses:

- Class.forName, reflection, or class names read from configuration.
- Frameworks that scan the classpath/module path.
- ServiceLoader, plugins, or dynamically registered providers.
- JDBC drivers loaded via SPI.
- JNI/JNA and native libraries.
- Resource bundles, charsets, locales, or resource files whose names are constructed at runtime.
- Java serialization or frameworks relying on metadata/reflection.

Do not use --ignore-missing-deps to hide dependency errors during final verification. If you use this option during initial analysis, investigate every missing dependency and prove that the application does not need it.

### Checking Service Providers

If the application needs a provider for a service, jlink can suggest modules that provide that service. For example, for the built-in JDK security provider:

~~~bash
jlink --suggest-providers java.security.Provider
~~~

For providers located in application libraries, include the module containing the provider on the module path when running the suggestion command. The service name must be the interface that the application actually uses.

When you need to link providers discovered through service binding, build the image with:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --bind-services --output image
~~~

--bind-services instructs jlink to link service provider modules and their dependencies. Without this option, the image may omit providers that the application looks up via ServiceLoader, even though the application compiles successfully.

## 5. Inspecting the Image Immediately After Creation

Run basic checks before executing business logic tests.

### Verify the Image Exists and Has a Launcher

Linux/macOS:

~~~bash
test -x image/bin/java
~~~

Windows PowerShell:

~~~powershell
Test-Path .\image\bin\java.exe
~~~

If the launcher does not exist or cannot execute, the image cannot yet be used as a runtime.

### Check the Java Version of the Image Itself

Linux/macOS:

~~~bash
./image/bin/java --version
~~~

Windows PowerShell:

~~~powershell
.\image\bin\java.exe --version
~~~

Compare the output against the JDK version used to build the image and the runtime version required by the product. Do not just run java --version, as that command may point to another JDK on PATH.

### Check the Module List

Linux/macOS:

~~~bash
./image/bin/java --list-modules
~~~

Windows PowerShell:

~~~powershell
.\image\bin\java.exe --list-modules
~~~

Confirm:

- The application modules are present if this is a modular runtime image.
- The JDK modules required by the application are present.
- Required provider modules are present if service binding is used.
- No unexpected modules are included if the goal is to minimize image size.

The module list does not have to match a full JDK. What matters is that it matches the reviewed and tested module baseline.

### Validate the Module Graph

Linux/macOS:

~~~bash
./image/bin/java --validate-modules
~~~

Windows PowerShell:

~~~powershell
.\image\bin\java.exe --validate-modules
~~~

This command instructs the launcher to validate the modules visible to the runtime and then exit. If any module conflicts or errors appear, resolve them before running application tests. Passing this command does not replace smoke tests or integration tests.

### Check Runtime Properties

Linux/macOS:

~~~bash
./image/bin/java -XshowSettings:properties -version
~~~

Read the properties java.home, java.version, java.vendor, os.name, and os.arch. java.home should point to the runtime image under test. This command starts a separate test JVM; it does not prove that the application itself can run.

## 6. Hands-On Example: Building and Testing a Runtime Image

The following example creates a small modular application, links a runtime image, and runs the application using the Java executable inside the image.

### Source Structure

~~~text
project/
└── src/
    └── com.example.runtimecheck/
        ├── module-info.java
        └── com/example/runtimecheck/Main.java
~~~

File src/com.example.runtimecheck/module-info.java:

~~~java
module com.example.runtimecheck {
}
~~~

File src/com.example.runtimecheck/com/example/runtimecheck/Main.java:

~~~java
package com.example.runtimecheck;

public class Main {
    public static void main(String[] args) {
        System.out.println("runtime-image-ok");
        System.out.println("args=" + String.join(",", args));
    }
}
~~~

The application only uses java.base, the foundational module always present in a Java runtime.

### Compile the Module

Open a terminal in the project directory:

~~~bash
javac --module-source-path src -d mods -m com.example.runtimecheck
~~~

After this command, the compiled module is located in:

~~~text
mods/
└── com.example.runtimecheck/
    ├── module-info.class
    └── com/example/runtimecheck/Main.class
~~~

### Create the Runtime Image on Linux/macOS

Assuming JAVA_HOME points to JDK 17 or later:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.runtimecheck \
  --launcher check=com.example.runtimecheck/com.example.runtimecheck.Main \
  --output image
~~~

In PowerShell on Windows, the module path separator is a semicolon:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.runtimecheck --launcher check=com.example.runtimecheck/com.example.runtimecheck.Main --output image
~~~

The --launcher option creates a custom launcher named check for the module and main class. The launcher filename on disk depends on the operating system.

### Inspect the Runtime Image

Linux/macOS:

~~~bash
./image/bin/java --version
./image/bin/java --list-modules
./image/bin/java --validate-modules
~~~

Windows PowerShell:

~~~powershell
.\image\bin\java.exe --version
.\image\bin\java.exe --list-modules
.\image\bin\java.exe --validate-modules
~~~

Confirm that the module list contains com.example.runtimecheck and java.base. --validate-modules completes without errors.

### Run the Application Using Java Inside the Image

Linux/macOS:

~~~bash
./image/bin/java -m com.example.runtimecheck/com.example.runtimecheck.Main one two
~~~

Windows PowerShell:

~~~powershell
.\image\bin\java.exe -m com.example.runtimecheck/com.example.runtimecheck.Main one two
~~~

Exact output:

~~~text
runtime-image-ok
args=one,two
~~~

This is an essential smoke test: the program is executed by the newly created runtime image, not the full JDK installed on the machine.

### Test the Custom Launcher

Linux/macOS:

~~~bash
./image/bin/check one two
~~~

Windows PowerShell:

~~~powershell
.\image\bin\check.exe one two
~~~

The output remains:

~~~text
runtime-image-ok
args=one,two
~~~

If the custom launcher fails to run while java -m succeeds, check the module/main class in the --launcher option, the launcher name, configuration files, and file execute permissions on the OS.

## 7. Testing by Application Functionality

A smoke test confirms that the runtime can start a basic flow. Afterward, run tests covering the features actually used in production.

| Test Area | Scenarios to Verify | Signs of Missing Dependencies |
|---|---|---|
| Class loading | Load main classes, secondary classes, and dynamically named classes | ClassNotFoundException, NoClassDefFoundError |
| Resource | Read properties, JSON, XML, templates, images, or resources in JARs | Null resource URL, file not found |
| Logging | Initialize logging backend/provider and write logs | Missing provider, logging fallback |
| ServiceLoader | Discover and instantiate all required providers | ServiceConfigurationError or no providers found |
| JDBC | Locate driver, open connection, execute query, and close resources | No suitable driver, provider not found |
| TLS/crypto | Create SSLContext, validate certificates, and connect over HTTPS | NoSuchAlgorithmException, provider/certificate error |
| Locale | Format numbers/dates, ResourceBundle, and required languages | Incomplete locale data or bundle |
| Charset | Read/write charsets used by the application | UnsupportedCharsetException or encoding errors |
| XML | Parse/transform XML if used by the application | Missing XML factory/provider or module |
| Desktop/image | Create fonts, render images, clipboard, or AWT/Swing if needed | HeadlessException, missing desktop module |
| JNI/JNA | Load and invoke native libraries | UnsatisfiedLinkError |
| Process/file | Read config, write files, create directories, and spawn external processes | AccessDeniedException, file not found |
| Network/DNS | Connect to hosts, resolve DNS, and handle timeouts | UnknownHostException, ConnectException |
| Timezone | Convert time zones and calendars as required | Timezone data or environment configuration mismatch |

You do not need to test every category above for every application. Choose based on the dependencies and features the product supports, and test the high-risk flows of your specific application.

### Testing TLS and Security Providers

An application using HTTPS may require specific security provider modules. Run tests that make real connections to a test endpoint and verify:

- DNS and TCP connections work.
- The certificate chain is trusted.
- The TLS protocol and cipher suite are appropriate.
- Providers for the required algorithms are available.
- The truststore and certificate configuration are packaged or supplied properly.

Do not just test SSLContext.getDefault() or instantiate a crypto class and conclude that production TLS works. Perform a real handshake and certificate verification in a production-like environment.

### Testing Locales and Charsets

If the application supports multiple languages, test the actual locales. When using jlink --include-locales, you must include the jdk.localedata module in the image and specify the module path containing the application:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app,jdk.localedata --include-locales=en,vi,ja --output image
~~~

The locale list must match product requirements. Test date/time, number, and currency formatting as well as ResourceBundle loading using the runtime image, because a full JDK may contain data that a minimal image lacks.

## 8. Testing Service Binding and Providers

For applications using ServiceLoader, tests must confirm that providers are discovered and functional, not merely that the application module exists.

A test can:

1. Call ServiceLoader.load(ServiceType.class).
2. Count the discovered providers.
3. Verify the expected provider types or metadata.
4. Invoke an actual method on each required provider.
5. Verify the results and any initialization errors.

If a provider module is not linked, you may need to build the image with --bind-services. Do not add provider modules by guesswork; determine the required service types and providers from the application architecture.

**Note on jpackage starting in JDK 25:** runtime images automatically created by jpackage no longer include service bindings by default. If the application needs linked providers, pass --bind-services to jlink via --jlink-options. For example:

~~~bash
jpackage --name ExampleApp --input input --main-jar app.jar --jlink-options --strip-native-commands --strip-debug --no-man-pages --no-header-files --bind-services
~~~

When specifying --jlink-options, keep the default options you still need; otherwise, the generated image may differ from the intended configuration. You can also create the runtime separately with jlink and pass that image to jpackage --runtime-image.

## 9. Testing in the Actual Deployment Environment

A runtime image may work on the build machine yet fail on the target machine due to operating system environment differences.

### Container Testing

Run integration tests inside the actual container image that will be released. Verify:

- The runtime image is copied to the expected path.
- The entrypoint invokes the correct launcher.
- The container user has read/execute permissions on the runtime and write permissions to required data directories.
- CA certificates, timezone data, and OS native libraries are present.
- DNS, network policies, proxies, and secret/config mounts work.
- Container memory/CPU limits do not alter behavior in unexpected ways.

A minimal runtime image does not automatically supply every OS-level dependency. For example, native libraries required by JNI must still exist on the OS/container.

### Architecture and Native Library Checks

Verify os.name, os.arch, and native dependencies on the target environment. Check:

- x64 versus ARM64.
- glibc versus musl on Linux.
- System library versions required by native libraries.
- Native library search paths.
- Execute and file access permissions.

An image built for one platform cannot be treated as a binary portable to another platform. Build and test for each supported target platform.

### Testing Windows Services or Linux Services

If the application runs as a service, test the exact command/launcher invoked by the service manager. Verify the working directory, environment variables, file permissions, log paths, restart policy, and shutdown behavior.

A command succeeding in an interactive terminal does not prove that the service will run successfully under a system account with a different environment.

## 10. Testing the Launcher and JVM Configuration

If jlink creates a custom launcher, verify:

- The module and main class are specified correctly.
- Command-line arguments are passed through intact.
- JVM options are applied.
- System properties have the expected values.
- Configuration files and resources are found from the actual working directory.
- Exit codes are returned properly to scripts/services.

You can inspect the runtime version and home directly from inside the application:

~~~java
System.out.println("java.version=" + System.getProperty("java.version"));
System.out.println("java.home=" + System.getProperty("java.home"));
System.out.println("os.name=" + System.getProperty("os.name"));
System.out.println("os.arch=" + System.getProperty("os.arch"));
~~~

In tests, compare java.home with the expected runtime image location. This helps detect tests that are accidentally running on a different JDK.

If the runtime image does not contain jcmd, jstack, or jfr, use the corresponding tools from a compatible full JDK for diagnostics in accordance with environment permissions and policies. Do not assume every diagnostic tool is available in a minimal image.

## 11. Testing Size, Startup, and Performance

A common goal of jlink is reducing runtime size. Measure before/after metrics under identical conditions:

- Total runtime image size.
- Compressed artifact size.
- Application startup time.
- Completion time for a representative workload.
- Memory footprint and peak memory.
- Number of modules and native dependencies.
- Benchmark results across multiple runs.

Do not conclude an image is better just because the directory is smaller. Compression options can reduce disk size without necessarily improving startup time or throughput.

If using --generate-cds-archive, verify that the image actually starts with the corresponding archive and re-measure startup. A CDS archive can depend on the module graph and runtime options; when configuration changes, check logs and archive usability.

Performance tests should run in a stable environment with identical CPU/RAM, OS, container limits, input data, and JVM options. Separate benchmarks from smoke tests to avoid turning performance results into flaky pass/fail gates.

## 12. Testing Updates and Security

A custom runtime image is not automatically updated when the base JDK releases patches. The development team is responsible for rebuilding the image from the updated JDK and releasing a new artifact.

On every JDK or jlink option update, you should:

1. Record the new vendor, version, and update level.
2. Rebuild the runtime image from the approved JDK.
3. Compare the module list and runtime properties against the baseline.
4. Re-run smoke, integration, and security-sensitive tests.
5. Verify certificates, TLS, crypto providers, and native libraries.
6. Check image size, startup, and memory if those are release metrics.
7. Generate checksums and store build metadata.
8. Release the new artifact and preserve rollback capability.

Do not treat removing modules with jlink as a complete sandbox or security boundary. A smaller runtime image reduces the packaged components, but file, network, process, secret, and OS resource access must still be enforced by platform security mechanisms.

## 13. Recommended CI Testing Workflow

A runtime image verification pipeline can be organized as follows:

~~~text
Compile application
       |
       v
Analyze dependencies (jdeps + manual review)
       |
       v
Create runtime image (jlink)
       |
       v
Inspect image and module list
       |
       v
Validate modules and launcher
       |
       v
Smoke test using image/bin/java
       |
       v
Integration tests on target OS/container
       |
       v
Security and native dependency tests
       |
       v
Size/startup regression checks
       |
       v
Publish image + checksum + build metadata
~~~

Each OS/architecture needs an appropriate build/test job. If the product supports Linux x64, Linux ARM64, and Windows x64, do not build a single image and reuse the same artifact for all three targets.

Archive the following:

- JDK vendor/version used for the build.
- jlink command and module roots.
- java --list-modules output.
- Smoke/integration test results.
- Runtime properties from the image.
- OS/architecture of the build target.
- Image/package checksums.
- Source and dependency versions.
- Security scan results and runtime update date.

## 14. Common Issues When Testing Runtime Images

### Accidentally Running Java from PATH

**Symptom:** the application runs fine in the terminal but fails when deployed.

**Cause:** tests used java from a full JDK instead of image/bin/java.

**Resolution:** invoke the executable via its path inside the image; check java.home and java.version in the application.

### Missing JDK Module

**Symptom:** NoClassDefFoundError, ClassNotFoundException, NoSuchMethodError, or factory/provider errors at runtime.

**Cause:** a required module was not added to the image or a dynamic dependency was not detected.

**Resolution:** re-analyze with jdeps, review reflection/service/resource usage, and add the required module to --add-modules. Re-run the full test suite on the new image.

### ServiceLoader Cannot Find Provider

**Symptom:** empty provider list or ServiceConfigurationError.

**Cause:** missing provider module, missing service binding, or the consumer module did not declare uses.

**Resolution:** check the module descriptor and module path; use jlink --bind-services when needed; run ServiceLoader tests on the real runtime image.

### Missing Locale or Charset

**Symptom:** different date/number formatting results, missing ResourceBundle, or unsupported charset.

**Cause:** the image does not include jdk.localedata or the required charset module.

**Resolution:** add the necessary locale modules/data, verify the --include-locales option, and test actual locales.

### TLS or Certificate Errors

**Symptom:** handshake failure, algorithm/provider not found, or untrusted certificate.

**Cause:** missing security provider/module, wrong truststore, missing CA certificates in the container, or different network environment.

**Resolution:** test a real handshake, inspect providers and truststore, and verify the certificate chain in the target environment.

### UnsatisfiedLinkError

**Symptom:** the JVM cannot load a native library.

**Cause:** missing native file, wrong architecture, wrong ABI, or missing system library.

**Resolution:** build/copy the right native binary for the target OS/CPU; check dependencies with OS tools and run tests in the target container/host.

### Launcher Runs with Wrong Configuration

**Symptom:** java -m works, but the custom launcher fails.

**Cause:** --launcher points to the wrong module/main class, or launcher/JVM options are misconfigured.

**Resolution:** compare the actual launcher command with the working java -m command; inspect the launcher file and run tests using the exact launcher to be released.

### Image Does Not Receive New JDK Patches

**Symptom:** the application continues to report an old version/update even though the build machine updated its JDK.

**Cause:** an old image was copied from an artifact cache or the pipeline did not regenerate the runtime.

**Resolution:** rebuild the image from the patched JDK, verify the version inside the image, and re-run tests before release.

## 15. Runtime Image Testing Checklist

- [ ] Record the JDK vendor, version, OS, and architecture of the image.
- [ ] Confirm the image has an executable Java launcher.
- [ ] Check java --version using the launcher inside the image.
- [ ] Inspect the module list and module graph with --list-modules / --validate-modules.
- [ ] Cross-check module roots against jdeps output and reviewed dynamic dependencies.
- [ ] Verify provider/service binding if the application uses ServiceLoader, JDBC, or SPI.
- [ ] Run the main class/JAR/module using the runtime image itself.
- [ ] Run the custom launcher if the image includes one.
- [ ] Verify args, JVM options, system properties, and working directory.
- [ ] Test resources, logging, locales, charsets, XML, and databases according to application features.
- [ ] Test TLS, certificates, and crypto providers if the application uses network security.
- [ ] Test JNI/JNA and native libraries on the exact target OS/CPU.
- [ ] Run integration tests in the actual container or service environment.
- [ ] Measure size/startup/memory when those are release criteria.
- [ ] Rebuild and re-test after every JDK security update.
- [ ] Store checksums, the module list, and metadata for the tested artifact.

## 16. Official References

- [The jlink Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html) — module roots, dependency closure, --bind-services, launcher, locale plugin, and runtime image structure.
- [The jdeps Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html) — dependency analysis and --print-module-deps to support creating runtime images.
- [The java Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html) — --version, --list-modules, --validate-modules, module launcher, and runtime options.
- [The jpackage Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html) — packaging applications with a runtime image and passing options to jlink.
- [Java SE 26 Packaging Tool User's Guide — Runtime Requirements](https://docs.oracle.com/en/java/javase/26/jpackage/packaging-overview.html) — application image structure, runtime requirements, and jpackage service binding changes starting in JDK 25.

A runtime image is only trustworthy once the application has been executed and tested using that exact image on the target platforms. Verify modules, services, resources, native dependencies, and deployment configuration before release.