# Compression, Strip Debug, and Reproducibility

## 1. Goals When Packaging a Runtime Image

When using **jlink** to create a runtime image for a modular application, you can adjust the image's contents and storage format to reduce distribution size, remove debug-only information, and make the build process reproducible.

These three goals are related but distinct:

- **Compression** reduces the size of certain resources in the runtime image, at the trade-off of potential decompression or processing overhead at runtime.
- **Strip debug** removes debug metadata from modules included in the image, making the image leaner.
- **Reproducibility** aims to produce the same output from the same set of inputs and build configuration, enabling reliable verification, comparison, and release.

Do not choose a configuration based solely on achieving the smallest size. The runtime image must still retain the modules, resources, and diagnostic capabilities needed for the deployment environment. Measure image size, startup time, and test functionality on the actual image.

## 2. Compression with jlink

The **--compress** option controls how jlink compresses resources in the image. Common levels:

| Option | Meaning |
|---|---|
| **--compress=0** | Disables jlink compression |
| **--compress=1** | Uses constant string sharing to reduce duplicate strings in class data |
| **--compress=2** | Compresses resources with ZIP |

Example creating an image with ZIP compression:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --compress=2 \
  --output runtime-image
~~~

**--compress=2** is often suitable when prioritizing smaller image size for distribution or storage. Compression can increase processing overhead when resources are accessed, so measure startup time and application behavior rather than assuming a smaller image always runs faster.

If you want to use constant string sharing:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --compress=1 \
  --output runtime-image
~~~

Level 1 performs sharing of repeated constant strings in class data. This is not ZIP compression and should not be compared directly with level 2 as two compression levels of the same algorithm.

You can disable compression to establish a baseline when measuring:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --compress=0 \
  --output runtime-image
~~~

Check **jlink --help** for the exact JDK you are using, as options and their interpretation may vary across releases. When comparing, keep input modules and all other options identical; only vary the compression level so measurements are meaningful.

## 3. Stripping Debug Info with --strip-debug

The **--strip-debug** option instructs jlink to remove debug information from modules included in the runtime image:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --strip-debug \
  --output runtime-image
~~~

Debug information in bytecode may include source line metadata, local variables, and information used by debuggers. Removing this metadata can reduce image size. In return, post-deployment debugging can be harder because debuggers or diagnostic tools lose part of the mapping back to source code.

Distinguish the scope of **jlink --strip-debug** from compiling the application:

- If application modules are included in the image via the module path, jlink processes those modules together with runtime modules according to the strip option.
- If the application is distributed separately as a JAR on the classpath outside the image, jlink does not modify that JAR's contents.
- For classes compiled by the project, **javac -g:none** can disable generating debug information right at the compile step.

Example:

~~~bash
javac -g:none -d out src/com/example/Main.java
~~~

If you need debugging in a staging environment or to support incident investigation, you can keep artifacts with debug metadata separately for diagnostics and build the release runtime image with **--strip-debug**. Ensure debug artifact storage aligns with release workflows and internal access policies.

Do not strip debug metadata before testing is complete if the development team still needs a debugger to pinpoint bugs. Decide based on operational requirements and the application's support policy.

## 4. Related Size-Reduction Options

In addition to compression and stripping debug info, jlink can exclude several components not needed at runtime:

- **--no-header-files** omits native header files.
- **--no-man-pages** omits manual pages.
- **--strip-debug** omits debug metadata in the module image.
- **--compress=2** compresses resources with ZIP.

Example:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --compress=2 \
  --strip-debug \
  --no-header-files \
  --no-man-pages \
  --output runtime-image
~~~

The two options **--no-header-files** and **--no-man-pages** are usually suitable for images intended solely to run the application. If the image is also used for development or compiling native code, verify whether header files must be kept.

Omitting man pages does not change application logic, but it may prevent operators from looking up local documentation inside the image. Ensure operational documentation is provided elsewhere if needed.

Furthermore, module selection via **--add-modules** often has a major impact on image size. Before optimizing compression, determine the root modules and dependencies truly needed. Do not drop a module just to save a few MB if application functionality still needs that module at runtime.

## 5. Example Release Runtime Image Configuration

Suppose the modular application is named **com.example.app**, compiled application modules are in **mods**, and the current JDK provides its modules in **$JAVA_HOME/jmods**.

You can create an optimized release image:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --compress=2 \
  --strip-debug \
  --no-header-files \
  --no-man-pages \
  --launcher app=com.example.app/com.example.app.Main \
  --output runtime-image
~~~

On Windows PowerShell, the separator between elements in the module path is a semicolon:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.app --compress=2 --strip-debug --no-header-files --no-man-pages --launcher app=com.example.app/com.example.app.Main --output runtime-image
~~~

Replace the module name and main class with your project's values. The output directory must not already exist or must be cleaned under a controlled build process before running the command.

If the application uses service providers, decide whether **--bind-services** is needed. When using this option, providers may be linked into the image according to service metadata. Pin the module path and input providers so subsequent builds do not accidentally pick up new modules.

You can save the jlink options used to a file:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --compress=2 \
  --strip-debug \
  --no-header-files \
  --no-man-pages \
  --save-opts jlink-options.txt \
  --output runtime-image
~~~

The **jlink-options.txt** file helps record command-line configuration for review and reuse. This file does not by itself lock the JDK version, input modules, or OS environment; that information must still be managed separately.

## 6. What Is Reproducibility?

A build is reproducible when, given the same set of inputs and configuration, the process produces a verifiable equivalent result. Two levels are commonly considered:

- **Functional reproducibility:** the runtime image has the same modules, configuration, and application behavior as the reference build.
- **Bit-for-bit reproducibility:** every output file has the exact same bytes and hash across builds.

These two levels are not identical. Two runtime images can run identically yet differ in hash due to metadata, timestamps, or toolchain differences. If release requirements demand exact hash comparison, test in practice on the same environment and do not assume jlink guarantees bit-for-bit reproducibility in every scenario.

Reproducibility is a property of the entire pipeline, including application artifacts, JDK, input modules, jlink options, build environment, and how the output is packaged. Saving a single jlink command alone is not enough to reproduce the entire image.

## 7. Pinning Inputs and the Build Environment

To make builds comparable, control the following factors:

1. **JDK:** use the same vendor, version, patch level, and build number. Record the output of **java --version** and **jlink --version**.
2. **Platform:** build the image for the exact target operating system and architecture. Runtime images are typically platform-dependent, so a Linux image cannot be assumed to substitute for a Windows or macOS image.
3. **Input modules:** use the exact JAR/module versions with verified hashes. Avoid mutating module path directory contents between builds.
4. **Module graph:** pin the **--add-modules** list, usage of **--bind-services**, and which provider modules are allowed to participate.
5. **Packaging options:** keep compression, strip debug, header/man pages, launcher, and other options consistent.
6. **Application artifacts:** configure JAR builds reproducibly, including entry ordering and archive metadata if the pipeline requires hash comparison.
7. **Environment:** record the operating system, architecture, locale, and build-related environment variables.
8. **Paths and outputs:** use a clean build directory, fixed input paths, and do not overwrite an already released image.

If the module path pulls contents from multiple directories, record the exact directories and module versions. Upgrading a library or introducing a new provider can alter the module graph and the resulting image.

## 8. Recording Evidence for Each Build

A build manifest can record the following information:

~~~text
Application: com.example.app
JDK vendor: <vendor>
JDK version: <version and build>
Operating system: <OS and version>
Architecture: <architecture>
Module roots: com.example.app
Module path inputs: <immutable artifact list>
Compression: 2
Strip debug: true
No header files: true
No man pages: true
Bind services: false
Launcher: app=com.example.app/com.example.app.Main
Output: runtime-image
~~~

Values inside angle brackets are placeholders for actual data. Do not treat this sample manifest as proof that an image was built with that configuration; it must be generated or saved alongside the actual build.

You should also store:

- The full jlink command or **--save-opts** file.
- The hash of each input JAR/module.
- The hash of the image or of each file in the image.
- Build logs and test results.
- The list of modules present in the image.

That way, when an issue occurs or two releases need comparison, you can identify whether the change came from the JDK, input modules, packaging options, or the application.

## 9. Verifying the Runtime Image

After creating the image, check the Java version and modules inside the image:

~~~bash
runtime-image/bin/java --version
runtime-image/bin/java --list-modules
~~~

You can list the module image contents using the **jimage** tool from the JDK:

~~~bash
jimage list runtime-image/lib/modules
~~~

Test the launcher:

~~~bash
runtime-image/bin/app
~~~

If no custom launcher was created, run the module directly:

~~~bash
runtime-image/bin/java -m com.example.app/com.example.app.Main
~~~

To measure size on Linux/macOS:

~~~bash
du -sh runtime-image
~~~

On PowerShell:

~~~powershell
$bytes = (Get-ChildItem -LiteralPath runtime-image -Recurse -File | Measure-Object -Property Length -Sum).Sum
"{0:N2} MB" -f ($bytes / 1MB)
~~~

When comparing compression, build separate images with **--compress=0**, **--compress=1**, and **--compress=2**, keeping all other factors identical. Record size, startup time, and representative workload results.

Do not rely on a single measurement. Startup time can be affected by OS caching, JIT, disk load, and the runtime environment. Use the same machine, the same workload, multiple runs, and document the methodology so results are comparable.

## 10. Checking Reproducibility Between Two Builds

A basic verification workflow:

1. Build the image the first time in a clean directory.
2. Save the manifest, logs, module list, and input hashes.
3. Rebuild a second time from the same artifact set, same JDK, and same options in another clean directory.
4. Compare the directory tree, sizes, and file hashes.
5. If hashes differ, identify which files differ and check metadata, timestamps, module contents, or toolchain differences.
6. Run smoke tests and functional tests on both images.
7. Store comparison results alongside the manifest as release evidence.

Example computing the hash for a file on Linux:

~~~bash
sha256sum runtime-image/lib/modules
~~~

On PowerShell:

~~~powershell
Get-FileHash -Algorithm SHA256 runtime-image\lib\modules
~~~

You can compare hashes of individual files rather than only comparing a single large file. For an image containing many files, a script or build tool is needed to produce a deterministically ordered list of paths and hashes.

If bit-for-bit reproducibility is required, metadata and packaging differences must also be addressed. If only functionally equivalent behavior is required, verify the module graph, config files, resources, and runtime tests. Clearly state the criteria your pipeline verifies.

## 11. Common Pitfalls When Optimizing

**Smaller image but slower startup**

Compression can reduce stored data size while increasing processing cost on access. Measure in the actual deployment environment and pick the level that fits your goals.

**Loss of debugging ability after stripping**

**--strip-debug** removes debug metadata from modules in the image. If troubleshooting is needed, keep separate artifacts with debug info or build diagnostic images for appropriate environments.

**Application libraries still contain debug metadata**

If application JARs are distributed separately on the classpath, **jlink --strip-debug** does not process those JARs. Configure the compiler such as **javac -g:none** or the corresponding build tool option if you genuinely want to omit metadata from the compile step.

**Image changes despite the same jlink command**

Check the JDK build, OS/architecture, input module hashes, discovered providers, module path, and artifact metadata. The same command does not guarantee the same output if the environment or inputs changed.

**New modules appear in the image**

If using **--bind-services**, a new provider on the module path may be linked into the image. Pin the input module set and inspect the module list after building.

**Build is not reproducible on another machine**

Runtime images are usually tied to a specific platform and JDK. Build separate images per OS/architecture using version-pinned toolchains; save the manifest and input artifacts for each platform.

## 12. Recommended Packaging Workflow

1. Identify root modules and dependencies required in the runtime image.
2. Pin JDK vendor/version/build and target platform.
3. Build module artifacts from source with a reproducible build configuration.
4. Record hashes and manifests of input modules.
5. Choose **--compress** according to size and runtime performance goals.
6. Choose **--strip-debug** according to diagnostic and support needs.
7. Enable **--no-header-files** and **--no-man-pages** only when the image does not need those components.
8. Save jlink configuration with **--save-opts** and record the actual options used.
9. Build the image in a clean directory, inspect the module list, and run smoke tests.
10. Measure size, startup, and representative workloads.
11. Build a second time from the same inputs to verify reproducibility against the project's criteria.
12. Store hashes, logs, manifests, and test results alongside the release.

## 13. Key Takeaways

- **--compress=0** disables compression; **--compress=1** uses constant string sharing; **--compress=2** uses ZIP compression on JDKs supporting these levels.
- **--strip-debug** removes debug metadata from modules packaged into the image.
- **javac -g:none** controls debug metadata at the application class compilation step.
- **--no-header-files** and **--no-man-pages** omit components unnecessary for many runtime deployments.
- **--save-opts** saves jlink options for inspection and reuse, but does not lock the JDK or input modules.
- Reproducibility requires pinning the toolchain, modules, artifacts, configuration, and environment.
- Compare hashes to check byte-for-byte equivalence; run tests to confirm runtime behavior.
- Always measure compression and test the image on the exact platform where it will be deployed.

A good runtime image satisfies size, diagnosability, and release process reproducibility. Choose compression and debug stripping based on measured metrics, and retain complete records of the JDK, input modules, jlink command, and verification results so the image can be recreated and inspected later.
