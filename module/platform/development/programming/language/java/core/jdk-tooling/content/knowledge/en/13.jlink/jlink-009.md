# Optimizing Runtime Image Size with jlink

`jlink` creates a custom runtime image from resolved Java modules. Image size depends on the included modules, accompanying data, native libraries, and output-processing plugins. To reduce size safely, first identify which modules and resources the application actually needs, then apply compression or strip metadata not needed at runtime, and measure again.

There is no single option that always produces the smallest image for every application. Stronger compression can increase decompression or resource-reading overhead; stripping debug data can make troubleshooting harder; removing native commands can leave the image without a `java` command for normal launching. Therefore, each change should be evaluated by both size and testing on the final image.

## 1. Components That Determine Image Size

A runtime image typically has a structure similar to:

```text
app-image/
├── bin/
│   ├── java
│   └── app
├── conf/
├── include/
├── legal/
├── lib/
│   ├── modules
│   ├── security/
│   └── server/
└── release
```

The exact structure depends on the JDK, operating system, and link options. Components that can significantly affect size include:

- **Java modules:** each selected module has corresponding class files, resources, and metadata. Modules such as `java.sql`, `java.xml`, `java.desktop`, or `jdk.localedata` can add substantial content depending on the application.
- **Native libraries:** the JVM, security providers, and native libraries packaged for the target platform.
- **Native commands:** commands in the image, such as `java`, application launchers, or commands provided by modules.
- **Locale data:** language data, number/date formatting, collation, and other locale-specific data.
- **Debug information:** source line information, local variables, and debugging metadata.
- **Man pages and header files:** documentation and headers for native development, usually not needed in a typical runtime image.
- **Resources:** configuration files, data, and module resources.

In many images, the `lib/modules` file contains most of the linked module content. However, do not look at the size of a single file alone; measure the entire image directory because binaries, configuration files, legal notices, and auxiliary files also take up space.

## 2. Starting with a Baseline Image and Measuring Size

Assume the application module `com.example.app` is in the `mods` directory, and the JDK is installed at `JAVA_HOME`.

Create a baseline image on Linux/macOS:

```sh
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --output app-image
```

On Windows PowerShell:

```powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.app --output app-image
```

The output image requires a destination directory that does not exist yet or is empty. When measuring multiple configurations, use distinct directory names or clean the build directory properly before re-running.

Measure size on Linux/macOS:

```sh
du -sh app-image
du -ah app-image | sort -h | tail -20
```

The first command shows the total directory size as reported by the system. The second helps find the largest files/directories to see which parts take up the most space.

Measure with PowerShell:

```powershell
$bytes = (Get-ChildItem .\app-image -Recurse -File |
    Measure-Object -Property Length -Sum).Sum
"{0:N2} MB" -f ($bytes / 1MB)
```

You can inspect the largest files separately:

```powershell
Get-ChildItem .\app-image -Recurse -File |
    Sort-Object Length -Descending |
    Select-Object -First 20 FullName, Length
```

Record the baseline size before optimizing. When comparing, use the same JDK vendor/version, operating system, CPU architecture, module inputs, and measurement method. Changing multiple factors at once makes it hard to determine which change caused the difference.

## 3. Selecting the Right Root Modules

The biggest impact usually comes from selecting only the modules you actually need. The `--add-modules` option specifies the root modules; `jlink` automatically resolves the required modules they depend on.

Example:

```sh
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --output app-image
```

If the application needs JDBC APIs, XML, or AWT/Swing, the corresponding dependency modules will be included when proper module relationships exist. Do not add modules in bulk just to avoid an undiagnosed error.

You can use:

```text
--add-modules ALL-MODULE-PATH
```

to select all observable modules on the module path. This is convenient for experimentation but usually produces a larger image than necessary. When the goal is size optimization, select only the root modules actually needed.

### 3.1. Analyzing Dependencies with jdeps

For JARs or Java applications, `jdeps` helps analyze static module references:

```sh
jdeps --print-module-deps --class-path "lib/*" app.jar
```

The output is the list of Java modules that the tool determines the application needs. You can pass that list to `--add-modules`, then build the image and run tests.

Example:

```sh
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules java.base,java.logging,java.sql,com.example.app \
  --output app-image
```

The module list above is only an illustrative example; replace it with your actual analysis results and application dependencies.

**Limitations of static analysis:** `jdeps` may not fully detect modules loaded via reflection, class names stored in configuration, plugins, `ServiceLoader`, JNI, or custom dynamic loading mechanisms. Those modules may need to be added explicitly. After reducing modules, run functional tests and verify initialization, plugins, logging, database, TLS, and resource handling flows.

### 3.2. Being Careful with --limit-modules

`--limit-modules` restricts the set of modules observable to the linker when resolving the module graph. It can help control resolution scope, but it is not a simple compression switch.

If a required module or needed provider is excluded from the observable set, linking will fail or the image will lack functionality. Use it only after understanding the dependency graph and testing thoroughly.

## 4. Compressing Resources with --compress

The `--compress` option controls resource compression in the runtime image:

| Value | Behavior |
|---:|---|
| `0` | No compression |
| `1` | Constant string sharing |
| `2` | ZIP resource compression |

Example using ZIP level:

```sh
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --compress=2 \
  --output app-image-compressed
```

Level 2 generally provides better size reduction for compressible resources, though effectiveness depends on the content. Data that is already compressed or has high entropy will shrink less. Compression can also increase the runtime cost of reading/decompressing resources.

Level 1 uses constant string sharing and has different characteristics from ZIP compression. Measure both configurations on your actual application if both size and startup time matter.

Do not assume `--compress=2` is always faster or always better. Compare:

- Total image size.
- Startup time.
- Load time for frequently used application resources.
- CPU and memory usage in critical flows.

## 5. Removing Debug Information with --strip-debug

Debug information can include source line numbers, local variable names and scopes, and debugger data. If a production image does not need this information, you can use:

```sh
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --strip-debug \
  --output app-image-no-debug
```

The `--strip-debug` option strips debug information from linked modules. It does not remove the application's executable bytecode.

Impacts to consider:

- Debuggers may not display local variable names or full source line mappings.
- Stack traces can still show classes and methods, but line numbers may be missing if line number metadata is stripped.
- Production incident analysis may become harder.

If operations teams need line numbers or deep debugging capabilities, consider keeping the necessary information. Do not strip debug metadata just for a small size saving if it removes data needed for troubleshooting.

## 6. Removing Header Files and Man Pages

Native header files and man pages are generally useful for development, native integration, or reading documentation. A runtime image used solely to run an application usually does not need them.

They can be excluded with:

```sh
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --no-header-files \
  --no-man-pages \
  --output app-image-runtime
```

- `--no-header-files`: excludes native header files from the image.
- `--no-man-pages`: excludes man pages from the image.

These two options are usually appropriate for runtime-only images. If the image is also used to compile native code or provide developer documentation, evaluate before removing them.

Do not manually delete files in the `legal` directory to save space. Legal notices and licenses may be part of the distribution obligations of the JDK or libraries. Keep the legal components required by your release process.

## 7. Limiting Locale Data

The `jdk.localedata` module provides additional locale data. If the application only supports a limited set of languages/regions, the `--include-locales` plugin can trim unneeded locale data.

Example for an image needing English and Vietnamese:

```sh
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app,jdk.localedata \
  --include-locales=en,vi \
  --output app-image-locales
```

You must include `jdk.localedata` in the module set so the plugin has data to process. Locale tags must match the list supported by the JDK; you can use language and region tags following Java's locale rules.

An application may still run while displaying different date, number, currency, collation, or message formatting when locale data is missing. Test:

- `Locale.getAvailableLocales()`.
- `NumberFormat` and `DateTimeFormatter` for all product-supported locales.
- Text sorting and comparison if using locale-sensitive collation.
- Screens or reports with multilingual content.

Restrict locales only when you know exactly which locales the product must support. If the application allows users to choose any locale, the image may need broader data.

## 8. Service Binding Can Increase Image Size

`--bind-services` instructs the linker to find service providers for services used by the selected modules and link those providers along with their required dependencies.

```sh
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --bind-services \
  --output app-image-services
```

If the application uses `ServiceLoader`, provider modules can be discovered through service binding. However, adding providers can also increase the module count and image size.

Enable service binding only when the application needs that mechanism. If providers are selected explicitly or the application has its own service configuration, check which modules are truly required. After linking, run tests to confirm that expected providers are still found and no unwanted providers are pulled in.

## 9. Native Commands and Native Libraries

Native components can take up significant space, especially in applications using image processing, audio, database, or native computation libraries.

Related plugins and options:

- `--strip-native-commands`: removes native commands from the image.
- `--no-header-files`: removes header files.
- `--no-man-pages`: removes man pages.

Be especially careful with `--strip-native-commands`. This plugin can remove native commands such as `java`/`javaw` from the image. If users or scripts need to run the application via `app-image/bin/java`, do not enable this plugin. Use it only when your deployment model has another appropriate launch mechanism and has been tested.

Not all native libraries can be removed. The JVM and certain modules require native libraries to function. If a library or command is removed by mistake, the image may link successfully yet fail to start or miss functionality at runtime.

## 10. Common Optimization Configuration

A common production configuration strips debug metadata, headers, and man pages while compressing resources:

```sh
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --strip-debug \
  --no-header-files \
  --no-man-pages \
  --compress=2 \
  --output app-image-prod
```

This is a starting configuration for measurement, not a universal default suitable for every application. If the application needs locale data, service providers, or native commands, add the corresponding options and run tests.

Example adding locales:

```sh
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app,jdk.localedata \
  --include-locales=en,vi \
  --strip-debug \
  --no-header-files \
  --no-man-pages \
  --compress=2 \
  --output app-image-prod
```

Root modules must reflect actual dependencies. Do not copy example commands directly into production without verifying your application's modules and locales.

## 11. Measuring Before and After Comparably

A reliable comparison requires keeping conditions identical:

1. Same JDK version and vendor.
2. Same operating system and CPU architecture.
3. Same input modules and application.
4. Same size measurement method.
5. Changing only one group of options at a time.
6. Running the same test suite and workload.

Example results table:

| Configuration | Modules | Plugins | Image size | Startup | Test result |
|---|---|---|---|---|---|
| Baseline | By dependency | None | Actual measurement | Actual measurement | PASS/FAIL |
| Strip metadata | Same as baseline | `--strip-debug`, no headers/man pages | Actual measurement | Actual measurement | PASS/FAIL |
| Compressed | Same as baseline | `--compress=2` | Actual measurement | Actual measurement | PASS/FAIL |
| Minimal modules | Verified root modules | Appropriate plugins | Actual measurement | Actual measurement | PASS/FAIL |
| Locale limited | Per locale requirements | `--include-locales` | Actual measurement | Actual measurement | PASS/FAIL |

Do not fill the table with estimated numbers. Measure artifacts produced by the actual release pipeline. To calculate percentage reduction, use:

[
\text{Size reduction (\%)} =
\frac{\text{Initial size} - \text{New size}}
{\text{Initial size}} \times 100
]

For example, if the baseline is 120 MB and the new image is 90 MB, the reduction is 25%. This is only an illustrative calculation; actual savings depend on modules and resources.

## 12. Inspecting Image Contents After Optimization

Do not evaluate an image solely by its size in MB. Verify that required modules and commands are still present.

List modules:

```sh
./app-image-prod/bin/java --list-modules
```

Check runtime version:

```sh
./app-image-prod/bin/java -version
```

Inspect entries in the runtime image using `jimage`:

```sh
jimage list app-image-prod/lib/modules
```

This listing helps inspect the contents of the module image. You can use OS tools to check files in `bin`, `lib`, and other directories.

Run the application using the runtime image:

```sh
./app-image-prod/bin/java -m com.example.app/com.example.app.Main
```

If a launcher was created:

```sh
./app-image-prod/bin/app
```

Then test functionalities at risk of being affected:

- Startup, shutdown, and exception handling.
- Logging, JDBC/database, and drivers.
- TLS, security providers, and certificates.
- Locales, date/time, currency, and number formatting.
- Reflection, `ServiceLoader`, plugins, and dynamic class loading.
- Native libraries, JNI, and native commands.
- Resources, configuration, and external files.
- Operational tasks requiring command-line tools.

A smaller image that lacks required providers or resources is not a valid optimization result.

## 13. Additional Plugins and Notes

List plugins in the current JDK:

```sh
jlink --list-plugins
```

The plugin list may differ across JDK versions. Other useful plugins include:

- `--order-resources`: adjusts resource ordering in the image by pattern, which can help optimize access to frequently used resources.
- `--generate-cds-archive`: generates a CDS archive if supported by the JDK; can improve startup time in some cases, though it also changes image size.
- `--exclude-files` and `--exclude-resources`: excludes files/resources matching patterns supported by the plugin.

Do not use exclude patterns to remove files simply because their names look unnecessary. A seemingly secondary resource might be loaded at runtime by a module or the application. Check plugin behavior against the documentation for your JDK and test the image after every change.

## 14. Common Errors When Optimizing Size

| Symptom | Common Cause | Resolution |
|---|---|---|
| Image is nearly the size of a full JDK | Too many modules selected or `ALL-MODULE-PATH` used | Analyze dependencies and select minimal root modules |
| Missing classes at runtime | Dynamically loaded modules were not linked | Identify modules via configuration/reflection/services and add explicitly |
| `ServiceLoader` cannot find providers | Missing provider module or service binding not enabled | Check `uses`/`provides`, module path, and `--bind-services` |
| Wrong date/number formatting in a locale | Locales restricted without required data | Add supported locales and test `jdk.localedata` |
| Smaller image but hard to debug | Debug metadata was stripped | Keep needed debug info or build a separate diagnostic image |
| Cannot run `java` command in image | `--strip-native-commands` was enabled | Remove the plugin if a standard Java launcher is needed |
| Little compression gain or slower startup | Incompressible resources or high decompression cost | Measure levels 0/1/2 on a real workload |
| Image fails to link after using limit modules | A required module is outside the observable set | Adjust `--limit-modules` and check dependencies |
| Small image but missing native libraries | Native dependency omitted or not packaged | Check target native dependencies and include needed components |
| Cannot compare sizes across two builds | Different JDK, OS, architecture, or measurement method | Standardize the environment and re-measure under the same conditions |

If linking reports missing modules, resolve the module graph first. If linking succeeds but the application fails, check dynamic dependencies, service providers, locales, and native components. Do not keep removing modules just to hit a target size number.

## 15. Recommended Optimization Workflow

1. Create a baseline with the known minimal root modules and measure the full image.
2. Use `jdeps` together with module descriptors to identify static dependencies.
3. Check dynamically loaded modules, service providers, JNI, and runtime configuration.
4. Build an image with `--strip-debug`, `--no-header-files`, and `--no-man-pages`.
5. Compare `--compress=1` and `--compress=2` if resource size is significant.
6. Restrict locales with `--include-locales` when the product has a clear locale list.
7. Review service binding and native commands to avoid including unnecessary components.
8. Measure size, startup time, and workload performance after each change.
9. Run the full test suite on the final runtime image and the exact target deployment platform.
10. Save the `jlink` command, JDK version, module list, and measurement results for reproducible builds.

You can save link options with `--save-opts` to record a reusable configuration:

```sh
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --strip-debug \
  --no-header-files \
  --no-man-pages \
  --compress=2 \
  --save-opts jlink-options.txt \
  --output app-image
```

The options file helps save linker configuration, while your pipeline still needs to manage the JDK version, module inputs, and build platform.

## 16. Pre-Release Checklist

- [ ] Measured baseline of the entire runtime image.
- [ ] Identified root modules based on application dependencies.
- [ ] Verified dynamically loaded modules and service providers.
- [ ] Removed header files/man pages only when not needed.
- [ ] Decided whether to keep or strip debug metadata based on operational needs.
- [ ] Compared compression levels by both size and runtime performance.
- [ ] Restricted locale data according to product requirements.
- [ ] Did not remove native commands if the image needs `bin/java`.
- [ ] Kept required native libraries and system dependencies.
- [ ] Verified the module image with `java --list-modules` and `jimage list`.
- [ ] Ran the application and tests on the final image.
- [ ] Built separate images for the exact target OS/CPU.
- [ ] Saved build commands and measurement metrics for reproducibility.

## 17. References

- Oracle JDK Tool Reference — The `jlink` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jlink.html
- Oracle JDK Tool Reference — The `jdeps` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeps.html
- Java Platform Module System: https://docs.oracle.com/javase/specs/

Optimizing image size is a balancing act between footprint, compatibility, startup time, and operability. Choosing the right modules usually delivers the largest benefit; compression and metadata-stripping plugins provide further fine-tuning. An image is only satisfactory when it meets both size goals and runs reliably in the actual deployment environment.