# 3.5 Classpath, Module Path, Native Libraries, and Related Environment Configuration

A Java application may work on a developer machine yet fail at startup or break a single feature in production despite identical source code. The cause may lie outside business logic: the JVM was launched with a different JDK, a class was loaded from a different JAR, a module failed to resolve, a custom class loader loaded a different library version, a JNI library lacked an OS dependency, or configuration from environment variables and working directory differed from what operators expected.

This lesson focuses on **diagnosing a live running JVM process**: reconstructing the effective classpath and module graph, identifying the origin of a class/resource, inspecting native libraries and environment configuration, and tying them back to error messages. Looking solely at config files in the source repository or running `java -version` in another terminal is not enough.

**Learning outcomes:** distinguish classpath, module path, and native library path; read launch and class loader configurations; choose evidence by symptom; inspect Java 17+ using standard tools; recognize each measurement's limits; and accurately reproduce differences between two environments.

## 1. Four-Layer Model for Reconstructing the Runtime Environment

A JVM process has at least four layers affecting how code is located:

1. **Runtime and launch command:** actual executable path, vendor/JDK version, JVM flags, `-D` system properties, launcher mode (`-cp`, `-jar`, `-m`), agents, and option files.
2. **Class/module resolution:** classpath, module path, boot layer, module graph, class loaders (bootstrap, platform, application, custom), search order, and delegation rules.
3. **Native libraries and OS loader:** `java.library.path`, `System.loadLibrary`/`System.load`, `.so`/`.dylib`/`.dll` dependencies, architecture, ABI, libc, and OS search paths.
4. **Deployment environment:** process working directory, file mounts, environment variables, container image, Kubernetes Deployment/Pod, UID/read/execute permissions, shell scripts, application config, and secret injection.

When an incident occurs, trace **the path of a class or library from request to actual artifact**:

```text
Launcher / entrypoint / environment
                 |
                 v
  Java runtime + JVM options + cwd
                 |
       +---------+-----------+
       |                     |
       v                     v
  Classpath             Module path
  (unnamed module)      (named modules)
       |                     |
       +------> ClassLoader <-+
                    |
         Class / resource / ServiceLoader
                    |
          JNI / native bridge (if any)
                    |
      OS loader -> dependent native libraries
```

This diagram shows the investigation direction only. **A class is not necessarily loaded by the application class loader**: frameworks, application servers, plugin systems, custom layers, agents, and test runners can use their own loaders. For each failing class, the three essential facts are **class name + defining class loader + code/resource source**.

## 2. How Does the Classpath Actually Work?

### 2.1. Entries and Search Order

Classpath is passed via `--class-path`, `-classpath`, or `-cp`; it can include directories containing `.class` files, JARs, and ZIPs. The path separator is OS-dependent: **colon on Linux/macOS**, **semicolon on Windows**. Relative entries are resolved relative to the working directory and launcher.

Example on Linux/macOS:

```bash
java -cp 'classes:lib/api.jar:lib/*' com.example.Main
```

Corresponding example on Windows (PowerShell/cmd):

```powershell
java -cp "classes;lib/api.jar;lib/*" com.example.Main
```

`lib/*` is a special **Java launcher** wildcard to add JARs in that directory, not a recursive search. The order of JARs added by a wildcard **is not guaranteed**; do not rely on it to pick a preferred version. On Unix shells, quote the classpath so the shell does not expand `*` prematurely before the launcher sees it.

A class `com.example.Service` is searched at path `com/example/Service.class` within the appropriate entry. With traditional class loaders, entry order matters when **duplicate classes** exist, though delegation, module resolution, multi-release JARs, and custom loaders also determine the outcome. “This JAR appears earlier in the list” is only a hypothesis, not proof of which class was actually loaded.

### 2.2. `CLASSPATH`, `-cp`, and `java -jar` Are Not Equivalent

| Launch style | Selected classpath | Common mistake |
| --- | --- | --- |
| `java com.example.Main` | Uses `CLASSPATH` if configured in the environment; otherwise typically defaults to `.` | Current terminal differs from service environment |
| `java -cp 'classes:lib/*' com.example.Main` | `-cp` specifies classpath and overrides the launcher's `CLASSPATH` | Assuming `CLASSPATH` is still appended automatically |
| `java -jar app.jar` | `-jar` reads main class from manifest and ignores user classpath from `-cp` or `CLASSPATH` as used in direct class launch | Trying to add `-cp missing.jar` to `-jar` and expecting the library to load |
| `java -p mods -m app.module/com.example.Main` | Starts from a **named module** on the module path, following module resolution | Assuming all JARs on `-p` are automatically resolved |
| Framework executable/fat JAR | May use a custom launcher and class loader to load nested JARs | Looking only at `java.class.path` and thinking that is the full dependency tree |

A JAR manifest can declare `Class-Path` to specify dependent JARs, per the Java JAR specification. Many frameworks package libraries in special structures (such as nested JARs) and use custom loaders; this mechanism **differs** from the Java launcher's default classpath.

**Key point:** `System.getProperty("java.class.path")` reveals part of the classpath configuration used by the system loader. It **does not necessarily list** every JAR loaded by custom class loaders, the module path, nested JARs, or native libraries.

### 2.3. Classpath Conflicts and Binary Incompatibility

Suppose at compile time `checkout` used `payments-api-2.jar` with method `charge(String, long)`; at deploy time a loader instead loads `payments-api-1.jar` lacking that method. The application may start up and then throw `NoSuchMethodError` when the code path calling that method runs. This is a **linkage/binary compatibility** issue: check runtime configuration or actual artifacts, not just the call stack.

For duplicate classes, distinguish:

- **Same FQCN across different loaders**: in the JVM, type identity includes both binary name **and defining class loader**. You can encounter `ClassCastException` even when the message prints two identical class names.
- **One loader finds two versions of a class**: search mechanism, classpath order, JAR manifest, and loader behavior decide which version is defined.
- **Compile-time differs from runtime**: `NoSuchMethodError`, `NoSuchFieldError`, or `AbstractMethodError` usually indicates bytecode expects a different API than the loaded code provides.
- **Class exists but its dependency is missing**: when the loader/linker tries to resolve another type, `NoClassDefFoundError` or a related error can occur. A class can also throw `NoClassDefFoundError` after an earlier initialization failure, so check the first `Caused by`.

The `jdeps` tool analyzes **static bytecode** dependencies, helping spot missing dependencies, but it **cannot** reliably find dependencies loaded via reflection, `ServiceLoader`, JNI, or dynamically constructed class names. Do not treat `jdeps` output as a mirror of the runtime class graph.

## 3. Module Path and the Java Platform Module System (JPMS)

### 3.1. Named and Unnamed Modules

Since Java 9, the module system organizes packages into modules with **readability** (`requires`), **exports** for normal Java access, and **opens** for deep reflection where appropriate. Bytecode on the classpath belongs to the corresponding loader's **unnamed module**; a modular JAR or exploded module on the module path can form a **named module** when resolved.

Example:

```java
module com.example.checkout {
    requires java.sql;
    requires com.example.contracts;
    exports com.example.checkout.api;
    opens com.example.checkout.internal to com.example.framework;
}
```

This is an **illustrative `module-info.java` snippet** and cannot compile standalone without the listed modules/packages. `requires` declares module dependencies; `exports` lets other modules access public types in the package; `opens` grants deep reflection access to the package within the declared scope. `exports` and `opens` do not share the same semantics.

### 3.2. Module Path Holds Modules; Resolution Chooses Which Modules Are Used

`--module-path` (`-p`) points to available modules. Resolution begins from root modules, reading `requires` and launcher options. **A JAR appearing on the module path does not mean it enters the boot layer**. The module path can include:

- **Explicit module:** contains `module-info.class`.
- **Automatic module:** a JAR without a formal descriptor placed on the module path and used as an automatic module per naming/metadata rules.
- **Exploded module:** an output directory containing `module-info.class` and class files.

Typical errors:

- `Module ... not found`: the required module name is not observable or lacks dependencies in the module path/runtime image.
- `FindException`/`ResolutionException`: modules fail to resolve due to package, naming, or relationship conflicts.
- `IllegalAccessError` and `InaccessibleObjectException`: API or reflection accesses a package without the corresponding permission.
- `ServiceConfigurationError`: a declared or loaded module/provider is invalid, or an implementation/dependency is broken.

**Do not fix by dumping every JAR onto the classpath.** Doing so can mask module errors, break service resolution, or change class-loading behavior.

### 3.3. `--add-exports`, `--add-opens`, and `--add-reads`

| Option | Adjustment | Common diagnostic use |
| --- | --- | --- |
| `--add-exports source.module/pkg=target.module` | Exports a package to the target module to allow appropriate Java access | Unexported public/internal type |
| `--add-opens source.module/pkg=target.module` | Opens a package for deep reflection by the target module | Framework blocked from reflecting fields/constructors |
| `--add-reads source.module=target.module` | Adds a readability edge between modules | A named module cannot read another module |

`ALL-UNNAMED` can serve as the target for applicable options when target code sits on the classpath. These flags **alter runtime encapsulation policy**; they do not fix missing JARs or mismatched bytecode versions. Prefer fixing dependencies/module descriptors or upgrading to a compatible framework; use targeted per-module/package workarounds with documented rationale and a removal plan. Do not scatter `ALL-UNNAMED` broadly just to silence errors without understanding why.

### 3.4. Module Inspection Commands

```bash
# View modules observable on the runtime invoking the command.
java --list-modules

# Inspect a specific module descriptor (e.g., a JDK module).
java --describe-module java.sql

# Check whether a JAR has explicit/automatic module metadata.
jar --describe-module --file lib/example.jar

# Read static dependencies of an artifact, given real JARs.
jdeps --missing-deps --class-path 'lib/*' app.jar

# Given a modularized application and complete configuration:
java --module-path mods --validate-modules
```

These commands are **inspection examples in a prepared environment**, and do not automatically reflect the production process's module graph if run with a different JDK, file tree, or working directory. `java --list-modules` lists *observable* modules for that invocation; do not confuse it with modules **resolved** in the target JVM. `--show-module-resolution` can be added to **the corresponding launch command** to observe resolution, though launching a separate test process is a new invocation requiring matching artifacts/configuration.

### 3.5. Standalone Module Example on JDK 17+

Create the three directories/paths below in a learning workspace (Linux/macOS shell commands shown):

```text
src/
  demo.paths/
    module-info.java
    demo/paths/Main.java
mods/
```

Contents of `src/demo.paths/module-info.java`:

```java
module demo.paths {
}
```

Contents of `src/demo.paths/demo/paths/Main.java`:

```java
package demo.paths;

public class Main {
    public static void main(String[] args) {
        Module self = Main.class.getModule();
        System.out.println("module=" + self.getName());
        System.out.println("reads.java.base="
                + self.canRead(Object.class.getModule()));
    }
}
```

Compile and run:

```bash
mkdir -p mods/demo.paths
javac -d mods/demo.paths src/demo.paths/module-info.java src/demo.paths/demo/paths/Main.java
java --module-path mods -m demo.paths/demo.paths.Main
```

Stdout on JDK 17+:

```text
module=demo.paths
reads.java.base=true
```

`java.base` is read by all modules under module system rules, even though the example does not declare `requires java.base`. In real applications, `module-info.java` must declare appropriate relationships; this small example merely demonstrates module naming and default readability.

## 4. Class Loaders and Origins of Loaded Classes/Resources

### 4.1. Class Name Alone Is Not Enough to Identify Version

The familiar built-in loader hierarchy is **bootstrap → platform → application**; custom loaders can follow different models, such as child-first in some plugin containers. When a class is requested from a loader, delegation usually determines which loader actually defines it. Hence, a log saying “file `foo.jar` exists” is not enough to confirm `com.example.Foo` came from it.

Choose by symptom:

| What you need to know | How to get evidence | Limitations |
| --- | --- | --- |
| Does the class belong to a named module? | `SomeClass.class.getModule()` | Classes in the unnamed module still have a `Module` object |
| Which loader defined the class? | `SomeClass.class.getClassLoader()` | `null` can signify bootstrap, not a missing loader |
| Which artifact was the class loaded from? | `getProtectionDomain().getCodeSource()`; resource URL; class load log | `CodeSource` can be `null` or insufficient for generated/nested classes |
| Are there multiple copies of a resource? | `ClassLoader.getResources("...")` | Result set and order depend on the loader |
| What other loaders exist in the JVM? | `jcmd <pid> VM.classloaders` or `VM.classloader_stats` if supported | Does not show all package/version relationships in one command |
| Which classes loaded from where over time? | `-Xlog:class+load=info` | Must enable logging/recording; adds overhead and log volume |

When encountering `ClassCastException: com.example.Plugin cannot be cast to com.example.Plugin`, look for **two different class loaders** rather than rushing to change the cast. With `ServiceLoader`, the thread context class loader and module layer can also decide which provider is found.

### 4.2. Safe Observation Program with Deterministic Output

Save the file **`RuntimePathProbe.java`**:

```java
public class RuntimePathProbe {
    public static void main(String[] args) {
        Class<?> app = RuntimePathProbe.class;
        Class<?> core = java.util.ArrayList.class;

        System.out.println("app.named=" + app.getModule().isNamed());
        System.out.println("core.module=" + core.getModule().getName());
        System.out.println("core.bootstrap="
                + (core.getClassLoader() == null));
        System.out.println("app.resource.found="
                + (app.getResource("RuntimePathProbe.class") != null));
    }
}
```

Compile and run **in classpath mode** with JDK 17+:

```bash
javac RuntimePathProbe.java
java -cp . RuntimePathProbe
```

Exact stdout:

```text
app.named=false
core.module=java.base
core.bootstrap=true
app.resource.found=true
```

`RuntimePathProbe` runs from the classpath so it belongs to the unnamed module; `ArrayList` resides in `java.base` and is defined by the bootstrap loader. `getResource` returns the URL of the class file on the classpath. When moving to a different deployment, these probes must run **under the same launcher/class loader style as that application**; a simple test run does not prove a production framework loads dependencies identically.

### 4.3. Snippet for Tracing Class Origin

In diagnostic code, you can log minimal, sanitized details:

```java
Class<?> type = com.example.api.Contract.class;
ClassLoader loader = type.getClassLoader();
java.security.CodeSource source =
        type.getProtectionDomain().getCodeSource();

String sourceUrl = source == null
        ? "<unknown>"
        : String.valueOf(source.getLocation());

System.out.println("module=" + type.getModule().getName());
System.out.println("loader=" + loader);
System.out.println("codeSource=" + sourceUrl);
```

This is an **illustrative snippet** and cannot compile standalone because `com.example.api.Contract` must be replaced with an actual project class. `CodeSource` may be missing; a URL pointing to a nested JAR or shaded/relocated JAR must be interpreted according to the specific launcher. Do not log paths containing account names or sensitive data to public logs.

When suspecting duplicate resources, consider enumerating with `getResources(...)` on **the right class loader** (not just the system loader). Record count, loader identity, and sanitized URLs. If using reflection `Class.forName(name)`, by default it can trigger class initialization; when you only want to check class lookup, use the `Class.forName(name, false, loader)` overload and still note that class linkage can occur.

### 4.4. Class Loading Logging and Class Loader Statistics

A test run on Linux/macOS can enable:

```bash
java '-Xlog:class+load=info:file=classes.log:time,level,tags:filecount=3,filesize=20M' \
     -cp 'classes:lib/*' com.example.Main
```

`classes.log` records class loading per HotSpot/JDK configuration; volume grows with load and number of loaded classes. This is an **illustrative command** requiring real main class/args, intended for staging/canary or approved windows; do not enable this log level permanently across all instances by default. On a running JVM, `jcmd <pid> VM.classloaders` and `VM.classloader_stats` give a snapshot of loader structure/stats if supported. They do not map dependencies as precisely as inspecting the target class directly.

## 5. Native Libraries: Java Searches by Name, the OS Must Load the File and Dependencies

### 5.1. Two Different Loading Paths

`System.loadLibrary("codec")` takes a **logical name** without prefix, extension, or path; platforms typically map it to `libcodec.so` on Linux, `libcodec.dylib` on macOS, or `codec.dll` on Windows. `System.mapLibraryName("codec")` shows the mapping on the live JVM. Library lookup depends on implementation, `java.library.path`, and the OS.

`System.load("/opt/app/native/libcodec.so")` uses an **absolute file path** (Linux example), bypassing `loadLibrary`'s logical-name search. Both ultimately rely on the OS dynamic loader and secondary libraries.

Illustrative example only—**will not run if the machine lacks the native artifact**:

```java
// Run only when the real, compatible JNI library is present.
System.loadLibrary("codec"); // Lookup by logical name.
System.load("/opt/app/native/libcodec.so"); // Absolute path.
```

Do not call both statements in one startup flow just to “try your luck”. Pick one loading approach matching your product; log the first error, identify the app library and its dependent libraries, and check version and architecture.

### 5.2. `java.library.path` Differs from OS Path Variables

| Property or variable | Typical effect | What to verify |
| --- | --- | --- |
| `-Djava.library.path=...` | Directories the JVM searches for native libraries by name | Runtime value, whether paths exist/are accessible; mutating the property after startup is not guaranteed to reconfigure library lookup |
| `LD_LIBRARY_PATH` (Linux) | Dynamic loader search path for shared objects subject to system rules | Startup environment, `RPATH`/`RUNPATH`, permissions, and security mechanisms |
| `DYLD_LIBRARY_PATH` (macOS) | One source of paths for the macOS dynamic loader | System Integrity Protection / code signing / policies may restrict its effect |
| `PATH` (Windows) | Can contribute to Windows DLL search behavior | Actual search order also depends on Windows loader flags, APIs, and app directory |
| `-agentpath` / `-agentlib` | Loads a native agent via JVM option | Agent version/ABI, options, permissions; agents alter JVM behavior |
| `java.home` / `JAVA_HOME` | Actual runtime path inside the JVM vs. variable often used by startup scripts | The two values do not have to match |

**Separate two questions:** “Did Java find the first-level library?” and “Could the OS loader resolve **all of its dependent libraries**?” Even if `/opt/app/native/libcodec.so` exists, loading can still fail because it needs `libssl.so`, `libstdc++.so`, or another library absent from the runtime image.

### 5.3. Common JNI/Native Error Categories

| Symptom | Investigation branch | Concrete evidence |
| --- | --- | --- |
| `no codec in java.library.path` | First-level library not found by logical name | `System.mapLibraryName`, `java.library.path`, file path, permissions |
| `cannot open shared object file` | Missing file or dependent library / wrong loader search path | Full error message, `readelf -d`, OS loader diagnostics |
| `wrong ELF class`, `bad CPU type`, DLL architecture mismatch | Wrong 32/64-bitness, CPU architecture, or ABI | `file`, `readelf -h`, `os.arch`, container image architecture |
| `undefined symbol` / incompatible version | Wrong native ABI, symbol, or dependency version | Dynamic symbols, `SONAME`, `RPATH`/`RUNPATH`, exact artifact build |
| `Native Library ... already loaded in another classloader` | Same native library loaded across different loaders | Class loader owning the JNI wrapper, plugin reload, lifecycle |
| `UnsatisfiedLinkError` when calling native method | JNI method lacks matching symbol/registration | JNI method signature, package/class name, `RegisterNatives`, compiled library |
| JVM crash with `SIGSEGV`/`EXCEPTION_ACCESS_VIOLATION` | JNI/FFI/agent or native runtime may have caused a memory fault | `hs_err_pid*.log`, native frames, core dump, dependency/ABI |

An `UnsatisfiedLinkError` **does not necessarily** mean a missing `.so` file: it can stem from a missing dependency of that file, an incompatible ABI, an unbound JNI method, or class loader ownership. Read **the original message along with causes and native loader diagnostics**.

### 5.4. Read-Only Tools for Inspecting Native Artifacts

On Linux, against **the exact deployed file**:

```bash
file /opt/app/native/libcodec.so
readelf -h /opt/app/native/libcodec.so
readelf -d /opt/app/native/libcodec.so
```

`readelf -h` shows ELF architecture/format; `readelf -d` can reveal `NEEDED`, `RPATH`, and `RUNPATH`. `ldd` is useful on **trusted binaries**, but do not run it on untrusted libraries because on some systems/configs it carries code-execution risks. On macOS there is `otool -L`; on Windows `dumpbin /DEPENDENTS` if appropriate tools are installed. These tools are not mandatory parts of a JDK and may be absent in distroless containers.

For a running JVM, `jcmd <pid> VM.dynlibs` (if supported by HotSpot) lists **already loaded** shared libraries. A library's absence from the list may mean it has not been requested yet or failed to load; it is not enough on its own to conclude. Cross-check with OS process memory mappings in the proper PID namespace and access permissions.

### 5.5. Containers, libc, and Architecture

A library compiled for Linux/glibc will not automatically run on a Linux/musl image; ARM64 binaries cannot run on x86_64; Linux `.so` files cannot be used as Windows `.dll` files. A build pipeline may ship the right Java JAR yet bundle native artifacts for a different architecture. Record **platform/CPU architecture of both JVM and library**, libc/native dependency closure, mounted paths, UID/GID, permissions, and container image digest. Never infer native loadability from filename alone.

## 6. Which Environment Configurations Actually Affect the JVM?

### 6.1. Launcher Commands, Option Injection, and System Properties

Factors causing startup differences include:

- **Actual Java executable:** scripts may invoke `$JAVA_HOME/bin/java` or pick via `PATH`; in containers it may be a custom JRE image.
- **Launcher parameters:** `-cp`, `-jar`, `--module-path`, `-m`, `--add-modules`, `--add-opens`, `-Dkey=value`, `-javaagent`, `-agentpath`; order and target matter.
- **`JDK_JAVA_OPTIONS`:** the Java launcher can prepend options from this variable before command-line options per JDK rules; other aspects depend on launcher/container scripts.
- **`JAVA_TOOL_OPTIONS`:** can inject JVM options under supported launch conditions.
- **`_JAVA_OPTIONS`:** seen in some HotSpot environments; do not treat it as a standard API available across all JVMs.
- **Application config:** framework environment variables, config files, arguments after main class/JAR, profiles, secret mounts; frameworks may enforce distinct precedence rules.

Example invocation:

```bash
java -Dapp.mode=prod -cp 'classes:lib/*' com.example.Main --port=8080
```

Here `-Dapp.mode=prod` is a **JVM system property**; `--port=8080` appears **after** the main class name so it is an **application argument**, not a Java launcher option. If a script builds the command line dynamically, read the *deployed version* of the script and actual launch result; never assume a framework's precedence order without checking its documentation.

**Security note:** `VM.command_line`, `VM.system_properties`, process arguments, environment variables, and app configs can contain tokens/passwords or sensitive paths. Collect only with authorized permissions, limit inspected fields, and redact before sharing; never dump raw `/proc/<pid>/environ` or `printenv` into public chats/issues/logs.

### 6.2. Working Directory and Relative Paths

The same command `java -cp 'lib/*' Main` can behave differently when `cwd=/opt/app` versus `cwd=/` because `lib/*` points to two different locations. Similarly, paths like `config/app.yml`, `./native`, or a relative keystore depend on the working directory or the framework's resolution mechanism.

In Java:

- `System.getProperty("user.dir")` reflects the runtime directory property; commonly used to resolve relative paths in Java APIs.
- The OS process current working directory is a process-level fact; on Linux you can inspect `/proc/<pid>/cwd` if permitted.
- `System.getProperty("java.home")` describes the running Java runtime; `JAVA_HOME` is merely an environment variable that startup scripts may use to pick an executable.

Do not “fix” issues by hardcoding an absolute path across all environments. First identify the expected path, where the file actually resides, permissions, and how the app constructs paths; then fix packaging/deployment/config reproducibly.

### 6.3. Environment at Process Start Differs from the Investigator's Shell

A terminal opened after an incident may have a different `PATH`, `JAVA_HOME`, timezone, or proxy than the systemd/Kubernetes service. Environment variables are **inherited when the process starts** (barring special in-process changes); editing variables in another shell does not automatically update a running JVM. Layered configuration sources may look like:

```text
Image / OS defaults
   -> systemd unit / container environment / launch script
   -> JVM options and -D properties
   -> application arguments and framework config sources
   -> effective behavior inside the running process
```

This diagram is an investigation flow, **not a universal override precedence** for every framework. In Spring Boot or apps with other config frameworks, per-property precedence is governed by that config system and must be verified per version.

### 6.4. File Mounts, Permissions, Case Sensitivity, and Paths with Spaces

- Linux typically uses case-sensitive filenames; Windows behaves differently. A JAR/resource path valid on one OS may fail on another.
- `-cp 'my libs/*'` must be quoted properly in the corresponding shell; if split into two args, the main class will be misparsed.
- A JAR may sit at the right path yet the Java user lacks read permission; a native library may require appropriate permissions/trust policy.
- Kubernetes ConfigMap/Secret mounts, symlinks, init containers, and immutable image digests can make deployed files differ from local build output.
- Fat JARs may store libraries at internal entries differing from the path operators expect; understand the launcher.

If config goes missing in production, verify **the resolved absolute path**, file existence, manifest/packaging, and process identity. Do not test `chmod 777` or broad filesystem edits just to see if the error disappears; that obscures root cause and introduces risk.

## 7. Diagnosing a Running JVM with Controlled Evidence Collection

### 7.1. Confirming the Right Process Before Reading Configuration

A read-only workflow usually starts with workload/pod/service info and PID, then uses the corresponding JDK tools. For example, on a system with JDK tools and attach permissions:

```bash
jcmd -l
jcmd 12345 VM.version
jcmd 12345 VM.command_line
jcmd 12345 VM.flags
jcmd 12345 help VM.classloaders
jcmd 12345 help VM.dynlibs
```

`12345` is an example PID; in containers account for the right PID namespace and authorized user. `jcmd -l` may omit JVMs in another container; cross-check with the appropriate process/container runtime. `VM.command_line` shows that JVM's launch arguments; `VM.flags` shows listed HotSpot flags; `VM.version` shows the actual runtime. `jcmd <pid> help`/`help <command>` is the authoritative way to verify command availability and impact on a specific JVM. When the problem involves paths, native libs, or class loaders, invoke only the needed commands instead of dumping all JVM data.

You can check `VM.system_properties` if you need to inspect `java.class.path`, `java.library.path`, `java.home`, or `user.dir`, but output can contain secrets, so **read in a controlled channel and export only sanitized excerpts**. Even `jcmd` command lines alone can carry secrets inside `-D...`. For sensitive cases, prefer an internal probe with allowlisted fields.

### 7.2. Minimal Evidence Set by Question

| Question | Collect first | When insufficient |
| --- | --- | --- |
| “Which JDK does prod use?” | `VM.version`, process executable, image digest | Cross-check build metadata, libc/OS architecture |
| “Why is a class missing?” | Exception chain, runtime launch mode, classpath/module path | Class source via loader/`CodeSource`, `jar tf`, `jdeps` |
| “Why does the class have a different method?” | `NoSuchMethodError` signature, JAR versions and hashes | Verify class origin by loader, `javap` actual API |
| “Why won't the module resolve?” | Module name, `module-info`, `--module-path`, and root set | `--show-module-resolution`, `--validate-modules` with matching launch config |
| “Why is reflection blocked?” | Exception package/module/target, module descriptor | Check exports/opens, framework version; narrow workaround if needed |
| “Why won't JNI load?” | Exact `UnsatisfiedLinkError` + system/native paths | OS dynamic dependencies, ABI/arch, `VM.dynlibs` |
| “Why does it fail only in a container?” | Image digest, command/args, cwd, mounts, UID, arch, env keys | Diff against a healthy instance and reproduce in an equivalent image |

**The goal is to find provable differences**, not generate massive logs/dumps. Most `jcmd` commands here are short queries, yet they still carry cost and permission requirements, especially with large numbers of class loaders; limit invocation frequency.

### 7.3. Inspecting Artifacts Offline Without Running the Application

On an analysis machine holding the exact JAR artifacts:

```bash
jar tf app.jar
jar --describe-module --file app.jar
jdeps --missing-deps --class-path 'lib/*' app.jar

# Example checking compiled public methods in an identified library build.
javap -classpath lib/payments-api.jar -public com.example.payment.Api
```

`jar tf` lists archive entries, `jar --describe-module` parses module metadata, `jdeps` inspects bytecode dependencies, and `javap` inspects API signatures. These commands **do not by themselves prove the runtime loaded that JAR**; cross-check the hash/path on the exact instance. Classes generated via reflection or runtime codegen may not appear in static reports.

Record artifact version from manifest or build metadata, resolved path, and checksum/hash if supported by workflow. Do not rely solely on filename `payments-api.jar`, as identically named files can hold different bytecode.

### 7.4. Enabling Class Loading Diagnostics When Needed

If current evidence has not revealed where a class loaded from, a controlled run can use `-Xlog:class+load=info` as in Section 4.4 to log class-loading timestamps/sources. Choose a short window, configure rotation and size caps, and account for overhead. On a running JVM, HotSpot `VM.log` may allow adjusting unified logging if permissions/syntax match, though that is a **runtime state change**; prepare a rollback plan and measure impact. Never turn on verbose logging across an entire cluster indiscriminately.

## 8. Classifying Errors by Failure Point

| Symptom / error pattern | First suspect area | What to prove before fixing |
| --- | --- | --- |
| `Could not find or load main class` | Main class, `-cp`, FQCN/package, cwd | Launcher mode, class file path inside JAR/dir |
| `ClassNotFoundException` | Dynamic `loadClass`/reflection, loader and path | Active loader, class origin, dependency |
| `NoClassDefFoundError` | Missing transitive class or failed initialization | First root cause, static initializer, parent/linking |
| `NoSuchMethodError` / `NoSuchFieldError` | Binary version mismatch | Bytecode signature, actually loaded class version |
| `ClassCastException` with two identical names | Duplicate classes from different loaders | Identities of both `ClassLoader`s and artifacts |
| `Module ... not found` | Module path/root resolution | Actual module name, descriptor, module search roots |
| `InaccessibleObjectException` | Reflection blocked by JPMS | Which module/package needs `opens`, why framework accesses it |
| `ServiceConfigurationError` | ServiceLoader provider module/JAR metadata | `uses`/`provides` or `META-INF/services` and provider class |
| `UnsatisfiedLinkError` | JNI load/search/dependent libs/ABI/method binding | Full native loader error, symbol, library path, architecture |
| `UnsupportedClassVersionError` | Class compiled for newer JDK than runtime | Class file version and process JDK |
| Fails only on prod/container | Config precedence, cwd, mounts, JDK, CPU/libc | Evidence-backed diff between healthy and failing environment |

**Causal relationships are not always one-to-one.** For example, `NoClassDefFoundError` can result from an earlier `ExceptionInInitializerError`; `UnsatisfiedLinkError` can stem from a missing native method symbol even though the file loaded. Always walk the error chain back to the first failure and note timestamps.

## 9. Incident Troubleshooting Workflow: From Symptom to Reproducible Fix

### Step 1 — Narrow the Question and Lock Down Identity

Record service, pod/container ID, PID, JVM start/uptime if needed, image digest, JDK vendor/version, command line, cwd, and error timestamp. For example: “On pod B, why does `com.example.Parser` run an implementation from an old JAR even though the pipeline just deployed a new version?” is far better than “Fix classpath”.

### Step 2 — Verify the Actual Runtime

Cross-check `VM.version`, `VM.command_line`, JVM flags, **filtered** runtime properties, process executable, and start script/image/manifest. Ensure the debug terminal is not accidentally using a different JDK. Separate JVM launch arguments, app args, and framework settings.

### Step 3 — Classify the Loading Path

- Normal class on classpath → check entries, ordering/duplicate JARs, resource URLs, loader.
- Named module → check module descriptors, module path, resolution roots, exports/opens.
- Custom loader/nested JAR/plugin → use the loader's own diagnostics/API, framework packaging, code source.
- JNI/native → check `java.library.path`, main file, OS dependent libraries, architecture/ABI.

Do not change multiple variables at once: if you alter classpath, swap JDKs, and add `--add-opens` together, you cannot know the true cause.

### Step 4 — Prove Which File and Loader Are Used

Locate class origin via in-process probe or class-loading logs, verifying JAR hashes and dependency graphs. For native code, use OS loader diagnostics and `VM.dynlibs` if available. For configuration, inspect effective values in-process (redacted) alongside where they were loaded.

### Step 5 — Build a “Healthy vs. Failing” Comparison Table

| Attribute | Healthy instance | Failing instance | What to conclude |
| --- | --- | --- | --- |
| JDK/Java executable | JDK 17, image A | JDK 17, image B | Same major yet different vendor/build or image? |
| Launcher mode/args | `-cp` and explicit JAR | `-jar` | Are dependencies loaded via the same mechanism? |
| Artifact hash | Hash X | Hash Y | Which build contains the expected method/resource? |
| Class loader/source | System loader/JAR A | Custom loader/JAR B | Which version did the runtime actually pick? |
| Module graph | Required module resolved | Missing module | How do module path/root set/descriptor differ? |
| Native dependencies | Matching glibc build | musl image | Is ABI/libc mismatch the actual cause? |
| cwd/mount/env keys | Has `config/app.yml` | Mounted elsewhere | Does the file exist and get read at the right path? |

Values in the table are **hypothetical examples**, not records from a specific environment. The more precise the comparison of artifact digests, loaders, and cwd, the easier it is to pinpoint build/deploy discrepancies to fix.

### Step 6 — Make the Minimal Fix and Verify

- Missing JAR → fix dependency packaging or launcher classpath in the right place.
- Duplicate/conflicting JAR → standardize the dependency graph, deduplicate via build tools, and verify code origin.
- JPMS access → adjust module descriptor or upgrade framework version; use a narrowly scoped package-opening workaround if needed.
- Native dependency/ABI → build/package the artifact matching OS/CPU/libc, bundle all required libraries, and set loader paths properly.
- Config/cwd/secret mount → fix the deployment contract, launch script, or source config appropriately.

Re-test using **the same startup mode and image** that failed, then inspect load sources, logs, and health endpoints. For production, roll out/canary per procedure while preserving rollback capability; do not tweak runtime flags ad hoc across all instances.

### Step 7 — Save a “Runtime Evidence Record”

A brief record should include: process/container identity; launch mode; JDK version; `java.class.path` or module roots; classloader + code source for the failing class; relevant native libs + ABI; cwd/config keys; artifact hashes; evidence-backed root cause; fix and verification results. Never store secret values, credentials, or full env dumps in broadly shared documents.

## 10. Three Illustrative Case Studies

### Case A — `NoSuchMethodError` Appears Only After Deployment

**Symptom:** service starts up cleanly, then the payment endpoint fails calling `Api.charge(String,long)`. Local tests pass.

**Hypothesis:** the `payments-api` version at runtime differs from the version used by the compiler.

**Measurement points:** exact method descriptor in stack/error; `javap -public` on the JAR inside the failing pod; class origin of `Api.class` from the right loader; check hashes/versions of all suspect JARs, classpath, and custom loaders.

**Interpretation:** if `Api.class` is defined from a JAR lacking the method, the bug is a binary mismatch. Do not work around it by casting, catching `NoSuchMethodError`, and retrying; resolve dependency resolution/packaging. If the JAR has the right method, check secondary class loaders, relocation/shading, and actual signature differences behind identical method names.

### Case B — `InaccessibleObjectException` After Migrating to JPMS

**Symptom:** a framework uses reflection on `com.example.model.internal` and is blocked.

**Hypothesis:** the named module does not open the package to the module containing the framework.

**Measurement points:** source module name, package, and target module in the exception; actual `module-info.java` of the artifact; module resolution and framework version. Check whether the framework uses `setAccessible(true)`/deep reflection or plain Java access.

**Interpretation:** `exports` grants public API access but does not grant deep reflection on private members; `opens` is usually more appropriate for controlled reflection. Use targeted `--add-opens` per package/target as a temporary diagnostic step if permitted, then fix the descriptor or upgrade to a compatible framework.

### Case C — `UnsatisfiedLinkError` Only on Linux Containers

**Symptom:** `System.loadLibrary("codec")` works on a laptop yet fails on a Linux pod.

**Hypothesis:** missing `libcodec.so`, missing dependent `.so`, ABI/musl-glibc mismatch, or container running on a different CPU architecture.

**Measurement points:** full error; filtered `java.library.path`; actual paths and permissions; `file`/`readelf -h`; `readelf -d` for `NEEDED`/`RUNPATH`; OS loader diagnostics; image architecture; `VM.dynlibs` if any library loaded.

**Interpretation:** having the main file is not enough; dependent libs or ABI may be wrong. Do not blindly set a global `LD_LIBRARY_PATH` as it may pick incompatible native builds for unrelated libraries. Fix image/native packaging at build time and re-run in an equivalent environment.

## 11. Thinking Pitfalls to Avoid

1. **Using shell `java -version` to conclude what production JVM runs.** Query the exact PID or executable/image.
2. **Reading `java.class.path` and treating it as the entire runtime dependency set.** Custom loaders, module paths, nested JARs, and dynamic loading lie outside one property.
3. **Relying on JAR filename without checking contents/hash.** Two files with the same name can hold different bytecode.
4. **Assuming every module on `--module-path` is resolved.** Check roots and `requires`.
5. **Assuming `--add-opens` fixes classpath or binary version mismatches.** It addresses reflection permissions, not missing classes/methods.
6. **Confusing `java.library.path` with `LD_LIBRARY_PATH`, or thinking the main JNI file existing is sufficient.** The OS loader depends on transitive libraries too.
7. **Searching types by name alone while ignoring classloader identity.** Two classes with the same name in different loaders are distinct types.
8. **Ignoring cwd, permissions, and path quoting.** Relative paths change meaning across IDE, systemd, and containers.
9. **Changing a system property at runtime and expecting JVM/OS library search to reload automatically.** Already initialized/cached mechanisms are not guaranteed to refresh.
10. **Ignoring the `Caused by` of the first failure.** Subsequent exceptions after class initialization failure are often mere consequences.
11. **Dumping full args, environment, and properties into an issue.** This easily leaks credentials.
12. **Leaving class-loading debug enabled long-term across all instances.** It adds overhead and large logs; control duration/frequency and volume.
13. **Hotfixing by copying JARs or running `chmod 777` manually on a pod.** The fix is unreproducible in build/deploy and creates security risks.
14. **Changing multiple components simultaneously.** You cannot isolate root cause if you alter JDK, module flags, dependencies, and native search paths at once.

## 12. Collection and Verification Checklist

- [ ] Right PID/container/JVM start, at the right time of the failure?
- [ ] Verified actual Java executable, vendor, JDK version, and image/artifact digest?
- [ ] Distinguished `-cp` / `-jar` / `-m` launch mode and application arguments?
- [ ] Checked `JDK_JAVA_OPTIONS`, `JAVA_TOOL_OPTIONS`, `-D`, and config precedence at source level?
- [ ] Failing class belongs to named or unnamed module, which defining loader, which code source/resource URL?
- [ ] Are classpath entries and module path correct, with no duplicate/conflicting JARs or module resolution errors?
- [ ] Distinguished `ClassNotFoundException`, `NoClassDefFoundError`, `NoSuchMethodError`, and module access errors?
- [ ] For `ServiceLoader`/plugins, checked the right context loader and provider metadata?
- [ ] For JNI, checked logical library name, `java.library.path`, OS dependencies, ABI/CPU/libc, and permissions?
- [ ] Checked cwd, relative paths, case sensitivity, mounts, and process user permissions?
- [ ] Compared failing and healthy instances using exact artifact hashes/loaders/env **after redacting secrets**?
- [ ] Verified the fix on the same mode/image, with evidence the right class/library loaded?

**Practice exercise:** a service packaged as `app.jar` runs via `java -jar app.jar`; an operator adds `-cp lib/new-api.jar`, yet the endpoint still throws `NoSuchMethodError`. Lay out the inspection sequence: why `-cp` does not work as expected with `-jar`, how dependencies are packaged/manifested/loaded by custom loaders, which loader actually loaded class `Api` from which file, whether the method signature matches bytecode, and how to fix packaging so all instances ship the same artifact. A strong answer states **evidence collected before making changes** along with post-deploy verification.

## References

- Oracle Java SE 17, [`java` launcher reference](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-cp`, `-jar`, `-m`, `--module-path`, `JDK_JAVA_OPTIONS`, `-Xlog`.
- Oracle Java SE 17, [`jcmd` reference](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `VM.command_line`, `VM.flags`, `VM.system_properties`, `VM.classloaders`, `VM.dynlibs`.
- Oracle Java SE 17, [`ClassLoader` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): system loader, classpath, delegated loading, and resources.
- Oracle Java SE 17, [Module system resolution](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/module/package-summary.html): observable/root modules, readability, and resolution.
- Oracle Java SE 17, [`System` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html): `java.class.path`, `java.library.path`, `System.load`, and `System.loadLibrary`.
- Oracle Java SE 17, [`jdeps` reference](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html), [`jar` reference](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html), [`javap` reference](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): inspecting artifacts, dependencies, and bytecode.
- Oracle, [Java Native Interface Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/index.html): native method binding, JNI library, and interface with native code.

To diagnose a Java runtime environment reliably, always pair **actual launcher configuration + actual module/classloader + actual artifact + actual native dependencies + OS/container context**. Only when these layers are verified on the same instance and timestamp can you separate code defects from packaging or environment issues.