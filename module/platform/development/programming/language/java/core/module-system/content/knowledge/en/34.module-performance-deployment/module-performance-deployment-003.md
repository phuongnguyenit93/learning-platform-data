# jlink Images and Startup Time

## 1. Objectives

A modular Java application typically runs on a JDK or JRE that contains more modules than the application actually needs. At deployment time, you can build a **custom runtime image** containing only the required runtime modules along with the application and its dependencies. The `jlink` tool performs this linking.

A custom image helps package a consistent runtime with the application, reduces distribution size, and can reduce startup time in some environments. However, a smaller image does not automatically mean the application starts faster: startup time also depends on class loading, framework initialization, I/O, JIT, JVM configuration, and the work the application performs.

This lesson guides you through building an image with `jlink`, determining which modules to include, configuring a launcher, and evaluating the impact on startup through controlled measurements.

After this lesson, you will be able to:

- Explain custom runtime images and the role of `jlink`.
- Identify root modules and dependencies to package.
- Create an image with a dedicated launcher for the application.
- Choose size-reduction options and understand their trade-offs.
- Run the application using the runtime image without depending on a JDK installed on the target machine.
- Measure cold startup and warm startup to evaluate real-world results.

## 2. What Does jlink Produce?

`jlink` combines compiled modules into a standalone executable runtime image. The image typically has a structure similar to:

~~~text
app-image/
├── bin/
│   ├── java
│   └── app
├── conf/
├── legal/
├── lib/
└── release
~~~

The exact structure and files vary by operating system and JDK. The `bin` directory contains the runtime launcher and the application launcher if declared; the remaining directories contain configuration, runtime libraries, legal notices, and metadata.

The image can be transferred to a target machine with a compatible operating system and architecture. The target machine does not need a separate full JDK installed to run the application from this image.

Importantly, `jlink` works with **named modules**. Input modules must be resolvable from runtime modules and the module path. A library present only on the classpath or an automatic module cannot be placed directly into a linked image as a regular named module. You need to modularize, replace, or package that dependency according to an appropriate architecture before linking.

## 3. Preparing Modules for the Application

Suppose we have an application consisting of two modules:

- `com.example.app`: the module containing the main class.
- `com.example.greeting`: the module providing the API used by the app.

Directory structure after compilation:

~~~text
project/
├── mods/
│   ├── com.example.app.jar
│   └── com.example.greeting.jar
└── app-image/
~~~

Application module:

~~~java
module com.example.app {
    requires com.example.greeting;
}
~~~

Greeting module:

~~~java
module com.example.greeting {
    exports com.example.greeting;
}
~~~

Main class:

~~~java
package com.example.app;

import com.example.greeting.Greeting;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.message());
    }
}
~~~

Before linking, make sure all dependencies needed by the application can be located. If the app module uses JDBC, logging, XML, or other services, the corresponding modules must be in the dependency closure or added as roots according to actual requirements.

You can use `jar --describe-module --file` to inspect the descriptor of each modular JAR:

~~~bash
jar --describe-module --file mods/com.example.app.jar
~~~

Confirm that the module name, `requires`, `exports`, `uses`, and `provides` match the expected configuration.

## 4. Determining Modules to Link

The most important option is `--add-modules`. It specifies the root modules; `jlink` resolves the dependencies required by those roots.

Example:

~~~bash
jlink \
    --module-path "$JAVA_HOME/jmods:mods" \
    --add-modules com.example.app \
    --output app-image
~~~

Explanation:

- `--module-path`: where to find input modules. The example includes the JDK's `jmods` directory and the directory containing the application's modular JARs.
- `--add-modules com.example.app`: selects the app as the root module to link.
- `--output app-image`: target directory for the runtime image.

On Windows PowerShell, path-list uses semicolons:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.app --output app-image
~~~

On Linux/macOS, path-list normally uses colons:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --output app-image
~~~

The `$JAVA_HOME/jmods` path must belong to a JDK compatible with the `jlink` tool being executed. Do not mix runtime modules from different JDK releases.

### Finding Module Dependencies with jdeps

`jdeps` analyzes static dependencies of classes or modules and can suggest a list of required modules:

~~~bash
jdeps --print-module-deps --module-path mods --module com.example.app
~~~

The output is a list of module dependencies that can serve as input to review for `--add-modules`. Read and verify the list before linking.

Static analysis cannot always detect dependencies loaded via reflection, class names configured in files, JNI, or dynamically discovered plugins. If your application uses these mechanisms, check the actual configuration and add the needed modules via `--add-modules`.

## 5. Adding Service Providers When Needed

If the application uses `ServiceLoader`, provider modules must be included in the runtime image so the application finds implementations at runtime.

You can use:

~~~bash
jlink \
    --module-path "$JAVA_HOME/jmods:mods" \
    --add-modules com.example.app \
    --bind-services \
    --output app-image
~~~

`--bind-services` instructs the linker to link service provider modules matching the services used by the selected modules, along with their required dependencies. This option is useful when providers are not direct `requires` dependencies of the app.

Not every application needs `--bind-services`. If service binding is not used or providers are already pulled into the graph another way, choose options based on your application's structure. After linking, run functional tests for each service to confirm the providers are actually present.

## 6. Creating a Dedicated Application Launcher

You can generate a launcher named after your application directly inside the image:

~~~bash
jlink \
    --module-path "$JAVA_HOME/jmods:mods" \
    --add-modules com.example.app \
    --launcher app=com.example.app/com.example.app.Main \
    --output app-image
~~~

Syntax:

~~~text
--launcher <launcher-name>=<module-name>/<main-class>
~~~

After creating the image, you can run the launcher:

On Linux/macOS:

~~~bash
./app-image/bin/app
~~~

On Windows:

~~~powershell
.\app-image\bin\app.bat
~~~

The launcher is generated from the specified module and main class. You can pass additional application arguments after the launcher name:

~~~bash
./app-image/bin/app --config config/app.yml
~~~

This lets operators run the application with a clear command without needing to remember the module name and main class.

## 7. Reducing Runtime Image Size

`jlink` provides several options to reduce image size. Example:

~~~bash
jlink \
    --module-path "$JAVA_HOME/jmods:mods" \
    --add-modules com.example.app \
    --strip-debug \
    --no-header-files \
    --no-man-pages \
    --compress=2 \
    --output app-image
~~~

Options:

| Option | Effect | Trade-off to Consider |
| --- | --- | --- |
| `--strip-debug` | Strips debug information from class files. | Can make debugging, stack trace analysis, and tools requiring metadata less convenient. |
| `--no-header-files` | Omits header files used for native development. | Unsuitable if the image must provide headers for native compilation workflows. |
| `--no-man-pages` | Omits runtime man pages. | Operators will not have man page documentation inside the image. |
| `--compress=2` | Compresses resources in the image at a higher level. | Can increase decompression/resource-reading cost and does not necessarily improve startup. |

Supported compression values and exact behavior depend on the JDK version. Check `jlink --help` of the exact JDK used to build before choosing a compression level.

Do not enable all size-reduction options out of habit. Determine whether the image needs headers, man pages, debug metadata, or frequently accessed resources. Image size is a deployment metric; it is not a direct measure of application performance.

## 8. Running and Verifying the Runtime Image

After linking completes, use the runtime inside the image itself to run:

~~~bash
./app-image/bin/java --list-modules
~~~

On Windows:

~~~powershell
.\app-image\bin\java.exe --list-modules
~~~

This list shows the modules present in the custom runtime image. You can test the app launcher:

~~~bash
./app-image/bin/app
~~~

If the image fails to run due to a missing module or service, re-check module roots, dependencies, input module path, and the `--bind-services` option. Do not assume a successful link command proves all execution paths work.

Run tests in a clean environment similar to the target machine, without relying on JARs or JDK modules already present on the development machine. This helps catch cases where the application accidentally depends on the build environment.

## 9. How Does jlink Affect Startup Time?

A custom runtime image can affect startup in several ways:

- **Fewer modules and resources:** can reduce the amount of runtime data to distribute and some initialization work associated with unpackaged modules.
- **Fewer files:** can reduce I/O or lookup overhead in some deployment environments.
- **Resource compression:** reduces image size but can add decompression cost when resources are read.
- **Application initialization:** time spent creating a Spring context, connecting to a database, loading configuration, scanning the classpath/module path, and running startup code often accounts for a significant portion. `jlink` does not eliminate this work on its own.
- **JIT and warm-up:** the first run can differ from subsequent runs because the JVM compiles hot code and the OS has caches.

Therefore, results depend on workload and environment. A smaller image can help download and initialize the environment faster, yet the time from invoking the command until the application is ready may remain nearly unchanged if most of the time is spent in application initialization or external connections.

If the goal is low startup latency, measure the actual application and determine whether time is dominated by the runtime or by application initialization logic.

## 10. Measuring Cold Startup and Warm Startup

A meaningful measurement must clearly define its start point and end point.

For example, for a CLI application that exits immediately after printing output, you can measure process time:

On Linux/macOS:

~~~bash
time ./app-image/bin/app
~~~

On Windows PowerShell:

~~~powershell
Measure-Command { & ".\app-image\bin\app.bat" }
~~~

For a server, process start time is not when the server is ready. Measure from launch until the health endpoint returns a ready status or the log emits a meaningful readiness signal.

To compare a full JDK and a custom image:

1. Build the same application version, same configuration, and same dependencies.
2. Use the same JDK release, JVM flags, machine, CPU quota, memory limit, and environmental conditions.
3. Define an identical readiness milestone for both runs.
4. Run multiple times, record each result, and compare the median along with appropriate percentiles.
5. Separate cold process runs from warm process runs; if measuring cold OS cache, control the cache and environment separately.
6. Keep external services such as databases, DNS, and network unchanged to avoid comparing two different conditions.
7. Measure image size, download/distribution time, and startup latency together.

Do not use a single run as a conclusion. Results can be skewed by antivirus, filesystem cache, CPU scheduling, container startup, network, and machine state.

For a server, record timestamps at least at two milestones: process start and application ready. If deeper analysis is needed, add milestones after main modules/classes are loaded, after the framework context initializes, and after external dependency connections complete.

## 11. When Startup Is Still Slow

If the custom image is already small yet the application still starts slowly, investigate the actual work on the startup path:

- Reduce unnecessary package/class scanning and avoid loading unused plugins.
- Defer initialization of components used only on certain requests.
- Reduce the number of synchronous connections or queries performed before readiness.
- Avoid network calls or reading large files inside static initializers.
- Measure initialization time of the framework and each key bean/service.
- Inspect logging, DNS, TLS handshake, and database connection pools.
- Consider Class Data Sharing (CDS) if suitable for your JDK, platform, and packaging. CDS is a separate mechanism requiring separate configuration and measurement; it is not enabled automatically just by using `jlink`.

Do not optimize by removing modules the application still needs. A small image missing a module will not run properly; an image with all required modules that still starts slowly needs profiling at the application layer.

## 12. Recommended Deployment Workflow

1. Build named modules and dependencies into artifacts with valid descriptors.
2. Use `jdeps` to suggest static dependencies; also review reflection, JNI, plugins, and service loading.
3. Select root modules with `--add-modules`; add `--bind-services` if providers need to be linked.
4. Run `jlink` with a module path containing JDK modules and application modules.
5. Add a launcher with `--launcher` and enable only appropriate size-reduction options.
6. Inspect the image's module list and run tests in a clean environment.
7. Measure startup against a readiness marker, repeat multiple times, and compare with the baseline.
8. Archive the link command, JDK version, module roots, image checksum, and benchmark results alongside the release artifacts.

Consolidated example command:

~~~bash
jlink \
    --module-path "$JAVA_HOME/jmods:mods" \
    --add-modules com.example.app \
    --bind-services \
    --strip-debug \
    --no-header-files \
    --no-man-pages \
    --compress=2 \
    --launcher app=com.example.app/com.example.app.Main \
    --output app-image
~~~

This is an illustrative configuration. Choose modules, service binding, and compression options according to your application's actual dependencies and requirements.

## 13. Takeaways

- `jlink` creates a custom runtime image from named modules and resolved dependencies.
- `--module-path` specifies where to find JDK modules and application modules; `--add-modules` selects root modules.
- `--bind-services` helps include matching service providers in the image when the application uses ServiceLoader.
- `--launcher` creates a command inside the image to run the application.
- `--strip-debug`, `--no-header-files`, `--no-man-pages`, and `--compress` can reduce size but carry trade-offs.
- A smaller image does not guarantee faster startup; you must measure cold/warm startup and application ready time.
- If startup remains slow, profiling application initialization, I/O, network, and frameworks usually reveals more specific causes.
- Test the image in a clean environment similar to production before releasing.

Use `jlink` to create a lean and reproducible runtime, then use benchmarks on your actual application to decide which configuration genuinely improves deployment and startup time.
