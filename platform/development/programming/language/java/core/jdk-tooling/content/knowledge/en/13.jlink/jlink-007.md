# The jlink --strip-debug Option

When creating a custom runtime image for a Java application, the **jlink** tool can remove debug information from the image using the **--strip-debug** option. Debug information supports debuggers and code analysis tools; it is generally not required for the JVM to execute the program. Stripping it can reduce the runtime image size, but it also reduces the data available when investigating issues at the source or native code level.

--strip-debug is a jlink plugin. It is applied during the runtime image linking step, after modules have been compiled and selected for inclusion in the image. This option does not replace javac and does not determine which modules are included in the runtime.

## 1. What is debug information?

**Debug information** is metadata generated alongside compiled code or stored in native components to support debuggers, profilers, and error analysis tools.

In a Java class file, some debug attributes may include:

- **LineNumberTable:** maps bytecode offsets to line numbers in the source code. The JVM and debugging tools can use this information to display error locations.
- **LocalVariableTable:** names and scopes of local variables in methods, if the compiler generates this metadata.
- **LocalVariableTypeTable:** generic type information for local variables, if generated.
- **SourceFile:** the source file name associated with the class file.

Which specific attributes are present depends on the compiler, compilation options, and JDK build. They are not part of the program's business logic. Bytecode can still execute when some debug metadata is removed.

For native libraries, debug symbols can help debuggers map machine addresses back to function names, source files, and native code lines. The scope of native debug symbol handling depends on the JDK, platform, and provided plugins.

## 2. What does --strip-debug do?

The option:

~~~bash
jlink --strip-debug ...
~~~

instructs jlink to remove debug information from the **output runtime image**.

The main goals:

1. Reduce unnecessary debug metadata in the runtime image.
2. Potentially reduce the image size for distribution or storage.
3. Keep the selected modules and runtime capabilities so the application continues to run.
4. Reduce source-level or native-level data available to certain diagnostic tools.

According to the jlink documentation, the strip-debug plugin strips debug information from the output image. The impact on each type of metadata and native symbol depends on the JDK version and platform. Do not assume that every JDK build processes the exact same set of data.

### Impact on the program

For a properly linked application that does not depend on debug metadata, stripping debug information does not change the execution semantics of the bytecode. The JVM still loads modules, invokes methods, and processes data as before.

The most noticeable impact is on diagnostics:

- Debuggers may lack the information needed to display local variable names.
- Line-based breakpoints may be less accurate or fail to work as expected if line metadata has been removed.
- Stack traces may lack source line numbers.
- Native debuggers may lack symbols if native debug symbols have been stripped.

The extent of the impact depends on which data is removed and which tools are used.

## 3. Comparing jlink --strip-debug and javac -g

The two tools operate at different stages:

| Option | Tool | Stage | Scope |
|---|---|---|---|
| -g | javac | Compilation | Generates full debug information in class files |
| -g:none | javac | Compilation | Generates no debug information for compiled class files |
| -g:lines,vars,source | javac | Compilation | Selects which groups of debug information to generate |
| --strip-debug | jlink | Runtime image linking | Strips debug information from the output image |

javac -g:none affects the class files produced by that compilation run. jlink --strip-debug processes the runtime image after modules have been compiled and selected for linking. Therefore, jlink can process metadata across modules in the image, including JDK-provided modules, according to the plugin's capabilities.

If you only want to control debug metadata for your application source code, consider javac options. If the goal is to optimize the final runtime image, evaluate --strip-debug and inspect the image after creation.

Do not use javac -g:none as proof that the runtime image has been stripped of all debug information; other modules in the image may have been pre-compiled with different settings.

## 4. JDK versions and debug-stripping plugins

The plugin's behavior has evolved across Java releases and can differ by vendor or platform.

- Current jlink documentation describes --strip-debug as an option that strips debug information from the output image.
- According to a technical article by the Inside Java team, prior to JDK 13, strip-debug only stripped Java debug attributes. Starting in JDK 13, stripping was extended to also remove native debug symbols on supported platforms.
- Native symbol stripping depends on the platform and system tools. The Inside Java article describes using objcopy on Linux.
- Some JDKs provide separate plugins such as --strip-java-debug-attributes. Available plugin names and sets may vary by distribution.

Before using the option in CI or build scripts, check:

~~~bash
jlink --version
jlink --list-plugins
~~~

Use the exact option listed by the target JDK. If you build on one JDK vendor but deploy with a runtime image from another vendor, verify behavior and compatibility.

References:

- [Oracle: The jlink Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jlink.html)
- [Inside Java: Stripping debug info from jlink runtime images](https://inside.java/2019/10/02/strippingdebug-jlink/)

## 5. Complete example: building two runtime images for comparison

The following example builds the same modular Java 17 application into two runtime images:

- runtime-base: an image built without --strip-debug.
- runtime-stripped: an image built with --strip-debug.

Both jlink commands keep the same modules, launcher, and module path so the impact of the option can be compared.

### Project structure

~~~text
strip-debug-demo/
└── src/
    └── com.acme.demo/
        ├── module-info.java
        └── com/
            └── acme/
                └── demo/
                    └── Main.java
~~~

File src/com.acme.demo/module-info.java:

~~~java
module com.acme.demo {
}
~~~

File src/com.acme.demo/com/acme/demo/Main.java:

~~~java
package com.acme.demo;

public class Main {
    public static void main(String[] args) {
        String target = args.length == 0 ? "Java" : args[0];
        System.out.println("Hello from " + target + "!");
    }
}
~~~

### Step 1: Compile the module

Using JDK 17 or later, from the project root directory:

~~~bash
javac --release 17 --module-source-path src -d mods -m com.acme.demo
~~~

The result is an exploded module:

~~~text
mods/
└── com.acme.demo/
    ├── module-info.class
    └── com/
        └── acme/
            └── demo/
                └── Main.class
~~~

### Step 2: Create the baseline runtime image

On Linux/macOS, assuming JAVA_HOME points to the JDK in use:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.acme.demo \
  --launcher demo=com.acme.demo/com.acme.demo.Main \
  --output runtime-base
~~~

### Step 3: Create the stripped runtime image

Using the same module path and selected modules, add --strip-debug:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.acme.demo \
  --launcher demo=com.acme.demo/com.acme.demo.Main \
  --strip-debug \
  --output runtime-stripped
~~~

On Windows PowerShell, the module path can be written as:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.acme.demo --launcher demo=com.acme.demo/com.acme.demo.Main --output runtime-base

jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.acme.demo --launcher demo=com.acme.demo/com.acme.demo.Main --strip-debug --output runtime-stripped
~~~

Both output directories must not already exist when running jlink. If an older image exists, choose a new directory name or handle the old image according to your project's build workflow.

### Step 4: Run both images

On Linux/macOS:

~~~bash
./runtime-base/bin/demo
./runtime-stripped/bin/demo
~~~

Both runs produce the output:

~~~text
Hello from Java!
~~~

Passing an argument:

~~~bash
./runtime-stripped/bin/demo "JDK tooling"
~~~

Output:

~~~text
Hello from JDK tooling!
~~~

On Windows, you can invoke the launcher in runtime-stripped/bin or run runtime-stripped/bin/java.exe with the corresponding module and main class.

### Step 5: Inspect modules and size

List the modules included in the runtime image:

~~~bash
runtime-stripped/bin/java --list-modules
~~~

Compare sizes on Linux/macOS:

~~~bash
du -sh runtime-base runtime-stripped
~~~

Size results depend on the JDK vendor, platform, modules, build method, and initial debug data. There is no fixed reduction ratio. If the image does not shrink significantly, the JDK distribution may already strip some metadata by default, or the selected modules may not contain much debug information.

This example compares the runtime behavior and disk size of the two images. To confirm exactly which metadata was removed, inspect the class/native artifacts using tools appropriate for the image format and JDK in use.

## 6. When should you use --strip-debug?

Appropriate when:

- Building production runtime images or container images where size optimization is needed.
- The application has already been tested on the corresponding runtime image.
- Other observability mechanisms are in place, such as logs, metrics, tracing, and crash reporting.
- Operations teams have ways to obtain additional diagnostic information when needed.
- A full source-level debugger is not needed inside the production image.

Consider keeping debug information when:

- Developing or debugging hard-to-reproduce issues.
- Line-level breakpoints or inspecting local variables in a debugger are needed.
- Analyzing native crashes or needing symbols to map stack frames.
- Using profiling or diagnostic tools that rely on metadata that would be stripped.
- Building images for testing, staging, or incident investigation.

You can maintain two image variants in your pipeline: a debug image for testing/diagnostics and an optimized production image. Both should be built from the same source revision and module configuration so that comparisons remain meaningful.

## 7. Combining with other jlink options

--strip-debug can be combined with other runtime image optimization options, provided the current JDK supports them:

- **--add-modules:** selects the root modules to link.
- **--module-path:** supplies JMODs, modular JARs, or exploded modules.
- **--compress:** compresses resources in the image.
- **--no-header-files:** excludes header files.
- **--no-man-pages:** excludes man pages.
- **--launcher:** creates a convenient launcher command for a module and main class.
- **--output:** specifies the output image directory.

Example combining debug stripping with resource compression:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.acme.demo \
  --compress=zip-6 \
  --strip-debug \
  --output runtime-production
~~~

When comparing sizes, keep all other options identical between two builds and change only --strip-debug. If you simultaneously change modules, compression, or locales, it becomes difficult to determine which factor caused the size reduction.

## 8. Common errors

### Unknown option or plugin not found

The current JDK may not support the option or plugin being used. Check jlink --version and jlink --list-plugins; choose options supported by the target toolchain.

### Missing native symbol stripping tool

Some native debug symbol stripping methods require system tools such as objcopy on Linux. If the plugin reports a missing tool, check the JDK/vendor requirements and install or specify the tool as documented for the platform. Do not assume native stripping options are available on every OS.

### Runtime image runs, but the debugger lacks information

This may be the expected result when debug metadata has been stripped. Use an unstripped debug image or retain debug artifacts according to your release workflow for investigation.

### Image size does not decrease

The JDK vendor may have already stripped some metadata; the selected modules may contain little debug data; or the image size may be dominated by native libraries and resources. Measure before/after sizes with the same configuration and inspect the actual plugins in use.

### jlink reports module not found

This is a module path or dependency issue, not a strip-debug error. Check the JDK JMODs, application exploded modules, module names, and requires clauses in the module descriptor.

### Output directory already exists

jlink requires a clean output location to create the image. Use a new output directory for each build or have the pipeline clean up old images according to your project's artifact policy.

### Stripped image behaves differently from a regular build

Check the module graph, launcher, resources, and configuration of both jlink commands. If both commands differ only by --strip-debug and application behavior changes, reproduce the issue with the unstripped image and file a bug report with the JDK vendor/version, OS, module list, and full build commands.

## 9. Checklist before stripping debug info

- Check the version and vendor of the JDK used for linking.
- Run jlink --list-plugins to confirm available plugins.
- Clarify whether the goal is to reduce Java debug attributes, native symbols, or both.
- Keep module path and --add-modules identical between comparison builds.
- Build debug and production images from the same source revision when needed.
- Run smoke tests on the stripped image.
- Verify logs, stack traces, metrics, and crash reporting in the deployment environment.
- Assess whether debuggers and profilers require any metadata that would be removed.
- Measure actual image sizes; do not assume a fixed reduction.
- Record the JDK vendor/version, OS, plugins, and jlink options in the build log.
- Retain appropriate debug artifacts or images for incident investigation if the production image is minimized.

## 10. Key terminology

| Term | Meaning |
|---|---|
| jlink | Tool for linking modules and dependencies into a custom runtime image |
| --strip-debug | jlink plugin that strips debug information from the output image |
| Debug information | Metadata supporting debuggers and analysis tools |
| LineNumberTable | Maps bytecode offsets to source line numbers |
| LocalVariableTable | Metadata for local variable names and scopes |
| SourceFile | Metadata for the source file name in a class file |
| Native debug symbols | Symbols supporting debugging and analysis of native code |
| javac -g | Instructs the compiler to generate debug information |
| javac -g:none | Generates no debug information in compiled class files |
| Runtime image | Runtime environment linked from selected modules |
| jlink plugin | Extension that processes or optimizes an image during linking |

--strip-debug is an optimization step during the runtime image creation stage. Verify the plugin on the right JDK, compare images with identical configurations, test functionality after stripping, and retain sufficient diagnostic artifacts so operations teams can investigate issues when needed.