# Environment compatibility: operating systems, architectures, and native libraries

During a Java application upgrade or migration, source code and bytecode can run across multiple platforms, yet the entire application may still depend on the underlying operating system, CPU architecture, and native libraries. An application running fine on Windows x86_64 might not run on Linux ARM64; the exact same JAR might work on a developer machine yet fail inside an Alpine container because a native library was compiled against glibc instead of musl.

This lesson explains how to identify those compatibility boundaries, how to organize dependencies and packaging, and how to test an application when changing environments.

## 1. Understanding compatibility layers properly

Java provides portability at the language and bytecode layers. A pure-Java .class file or JAR can usually run across multiple operating systems and architectures if the runtime provides the required Java version and APIs demanded by the application. However, that portability does not automatically cover every component bundled with the application.

| Layer | Components needing compatibility | Examples of migration failures |
|---|---|---|
| Java runtime | Java version, APIs, modules, JVM vendor, and launch options | Application compiled with new APIs yet running on an old JRE |
| Operating system | System APIs, paths, permissions, processes, environment variables, and filesystem behavior | Invoking bash commands on Windows or hardcoding Unix-style paths |
| CPU architecture | Instruction set, pointer size, and binary format | ARM64 JVM attempting to load an x86_64 DLL or SO library |
| ABI and native libraries | Library format, calling convention, libc, and transitive native dependencies | SO library linked against glibc fails to load on a musl-only environment |
| Packaging and deployment | JARs, native bundles, container images, library paths, and runtime config | JAR is present, yet required native files were omitted from the image |

When investigating failures, pinpoint which layer is incompatible. The error message may surface inside Java while its root cause lies in the operating system's dynamic linker or in a packaged native binary.

A helpful principle is separating three questions:

1. **Can the JVM run the application?** Check Java version, bytecode target, modules, and runtime options.
2. **Can the JVM interact with the environment?** Check filesystems, processes, permissions, encoding, and OS APIs.
3. **Can the native components load and execute?** Check OS, CPU architecture, ABI, and transitive native dependencies.

## 2. Operating system compatibility

### 2.1. Common differences

Operating systems provide different conventions and services. Although Java abstracts away many differences, applications can still stumble on the following points:

- **Paths:** Windows typically uses drive letters and \; Linux and macOS typically use /. Windows also supports UNC paths like \\\\server\\share.
- **Case sensitivity:** Filesystems on Linux normally distinguish Config.properties from config.properties. Some Windows and macOS configurations are case-insensitive; exact behavior can vary.
- **Access permissions:** Unix-like systems use owner/group permission models; Windows uses ACLs. Handling of symbolic links, file locks, and execute permissions also differs.
- **Processes and shells:** Executable names, shell syntax, argument quoting, and environment variables differ. bash, sh, cmd.exe, and PowerShell are not interchangeable.
- **Line endings and encoding:** Files may use LF or CRLF. Default encodings and locale settings can differ between developer machines, servers, and containers.
- **System services:** Service installation, signal delivery, process management, and startup configuration depend on the platform.

These differences rarely surface in unit tests run on a single machine. They appear when an application reads files created by another system, spawns external processes, writes data to the deployment directory, or runs under a service account with restricted privileges.

### 2.2. Using cross-platform Java APIs

Prefer standard Java APIs when interacting with the filesystem and processes.

Use Path and Files instead of concatenating path strings:

```java
import java.nio.file.Files;
import java.nio.file.Path;

Path configDirectory = Path.of("config");
Path configFile = configDirectory.resolve("application.properties");

if (Files.isRegularFile(configFile)) {
    String content = Files.readString(configFile);
    System.out.println(content);
}
```

Path.resolve handles separators matching the active filesystem. In applications needing to support Java older than Java 11, Files.readAllBytes or Files.newBufferedReader can be used instead of Files.readString.

Never assume the current working directory is the directory holding the JAR. The working directory depends on how users, service managers, IDEs, or containers launch the application. Specify configuration and data directories explicitly via startup arguments, environment variables, or deployment configuration.

If external programs must be launched, use ProcessBuilder with separate arguments:

```java
import java.io.IOException;
import java.util.List;

List<String> command = List.of(
    "git",
    "rev-parse",
    "--show-toplevel"
);

Process process = new ProcessBuilder(command)
    .redirectOutput(ProcessBuilder.Redirect.INHERIT)
    .redirectError(ProcessBuilder.Redirect.INHERIT)
    .start();

int exitCode;
try {
    exitCode = process.waitFor();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    throw new IOException("Interrupted while waiting for command", e);
}

if (exitCode != 0) {
    throw new IOException("External command failed: " + exitCode);
}
```

The example above illustrates passing the command and arguments separately while inheriting stdout/stderr onto the parent process so output buffers do not fill up while waiting. In real applications, verify the command is installed and present on the PATH of the account running the application.

Avoid assembling the full command into a single string passed through a shell such as sh -c or cmd /c unless shell syntax is genuinely required. Doing so introduces quoting, escaping, and injection discrepancies. If platform-specific tools must be invoked, encapsulate command selection inside a dedicated adapter and test that adapter on every supported OS.

### 2.3. Encoding and text content

Do not rely on the machine's default charset when reading or writing data exchanged across systems. Specify charsets explicitly:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

String text = Files.readString(
    Path.of("data.txt"),
    StandardCharsets.UTF_8
);

Files.writeString(
    Path.of("result.txt"),
    text,
    StandardCharsets.UTF_8
);
```

Java 18 and later default to UTF-8 for the default charset in standard environments, yet applications moving across Java versions should still declare charsets at I/O boundaries. Distinguish content charset from the OS line separator. When processing data formats with explicit newline rules, follow the format specification instead of automatically replacing lines with System.lineSeparator().

### 2.4. When is OS detection necessary?

When using standard Java APIs, branching by OS is rarely needed. Detect the OS only when the application genuinely must pick platform-specific binaries, commands, or configuration.

Environment details can be gathered via system properties:

```java
String osName = System.getProperty("os.name", "unknown");
String osVersion = System.getProperty("os.version", "unknown");
String architecture = System.getProperty("os.arch", "unknown");

System.out.println("OS: " + osName);
System.out.println("OS version: " + osVersion);
System.out.println("Architecture: " + architecture);
```

These values help diagnose issues and choose native packages, yet a naive string check should not drive all behavior. OS names vary across vendors and versions. If classification is required, normalize values in one central place, handle supported platforms explicitly, and fail with a clear message on unsupported platforms.

Never assume every system whose name contains Linux shares the same libc, package manager, or system libraries. The OS name alone is insufficient to conclude ABI compatibility.

## 3. CPU architecture compatibility

### 3.1. JVM and process architecture

A JVM is built for a specific CPU architecture. Pure Java code normally needs no separate compilation for x86_64 versus ARM64, whereas the JVM and native libraries require matching binaries.

Common architecture names include:

| Group | Possible reported names | Notes |
|---|---|---|
| x86 64-bit | amd64, x86_64, occasionally x64 | These names usually refer to the same architecture family |
| ARM 64-bit | aarch64, arm64 | Common on ARM servers and Apple Silicon machines |
| x86 32-bit | x86, i386, i686 | Has address-space limits and declining runtime support |
| ARM 32-bit | arm, armv7l | Requires verifying exact ABI and ARM variant |

The os.arch value reflects the architecture the JVM process is running as or reporting, not necessarily the host's physical CPU architecture. For example, an x86_64 JVM can run under emulation on an ARM64 machine. In that case, native libraries must match the JVM process, not merely the physical CPU.

Therefore, check architecture in the exact environment where the application executes: developer machines, CI runners, container images, and deployment hosts. Never infer architecture from hostnames or the build machine's architecture.

### 3.2. Why does architecture affect native code?

Native binaries contain machine code and obey platform ABI conventions. An x86_64 library cannot be loaded directly into an ARM64 JVM merely because both run the same OS. Likewise, 32-bit and 64-bit libraries generally cannot mix inside the same process.

Relevant differences include:

- CPU instruction sets and ISA extensions required by the binary.
- Pointer widths, platform-dependent data types, and alignment.
- Calling conventions and parameter-passing rules between Java and native code.
- Binary object formats and operating system dynamic loaders.
- ABIs of compilers, C/C++ runtimes, and linked system libraries.

Do not assume every ARM64 CPU is compatible with every ARM64 binary in every environment. Instruction set levels, ABI variants, OS versions, and dependent libraries must still align.

### 3.3. Normalizing architecture names

If you need to map architecture names to internal classifiers, normalize them in one place and handle unknown values explicitly:

```java
import java.util.Locale;

static String normalizedArchitecture() {
    String arch = System.getProperty("os.arch", "")
        .toLowerCase(Locale.ROOT);

    if ("amd64".equals(arch)
            || "x86_64".equals(arch)
            || "x64".equals(arch)) {
        return "x86_64";
    }

    if ("aarch64".equals(arch) || "arm64".equals(arch)) {
        return "aarch64";
    }

    if ("x86".equals(arch)
            || "i386".equals(arch)
            || "i486".equals(arch)
            || "i586".equals(arch)
            || "i686".equals(arch)) {
        return "x86";
    }

    throw new UnsupportedOperationException(
        "Unsupported CPU architecture: " + arch
    );
}
```

The alias list should match the JVMs and platforms your product commits to supporting. Never default an unknown architecture to x86_64 or ARM64; that can pick the wrong binary and fail at library loading time.

## 4. Native libraries and ABI

### 4.1. What is a native library?

A native library contains code compiled for a concrete operating system and architecture. Java typically encounters native code via:

- **JNI (Java Native Interface):** Allows Java to call native functions and native code to interact with the JVM.
- **JNA (Java Native Access):** Provides access to native libraries via function and data-type mappings.
- **Foreign Function & Memory API:** Provides Java APIs for working with native functions and off-heap memory; availability depends on the Java version your application targets.
- **Transitive dependencies:** A Java library may load its own internal native binary or depend on another native library that your application never calls directly.

Declaring a dependency in Maven or Gradle does not guarantee every needed binary is packaged properly. Check the Java artifact, platform-specific native artifacts, and any system libraries those native binaries further depend on.

### 4.2. Filenames and library loading mechanisms

Native library filenames follow OS conventions:

| Operating system | Common format | Example |
|---|---|---|
| Windows | DLL | engine.dll |
| Linux | ELF shared object | libengine.so |
| macOS | Mach-O dynamic library | libengine.dylib |

With JNI, System.loadLibrary("engine") asks the JVM to locate the library by logical name and platform convention. The JVM uses the runtime's native library search paths, including java.library.path; the OS dynamic loader must also locate all transitive native dependencies of that library.

System.load("/absolute/path/to/library") loads a library from an absolute path. This works well when an application manages extracting native resources itself. The path must point to a binary of the right format and architecture for the running JVM.

An error such as UnsatisfiedLinkError can have multiple causes:

- Library file not found.
- File exists yet targets the wrong OS or architecture.
- ABI or libc version mismatch.
- A transitive native dependency needed by the main library is missing.
- JVM fails to find a required symbol or function.
- File permissions or security policies block loading.

Thus, checking only whether a DLL, SO, or dylib file exists is insufficient.

### 4.3. ABI and system dependencies

An ABI (Application Binary Interface) defines how binaries interact with the operating system, compiler runtime, and other binaries. Two libraries sharing the same architecture and OS can still be ABI-incompatible.

Situations requiring attention:

- **Linux glibc vs. musl:** Most Linux distributions use glibc, whereas Alpine Linux normally uses musl. Native libraries dynamically linked against glibc will not run out of the box inside a musl-only image.
- **glibc version:** Binaries built on a newer distribution may require glibc symbols or symbol versions newer than the target environment provides.
- **Windows C/C++ runtime:** DLLs may depend on the Microsoft Visual C++ Runtime or other runtimes that must be properly installed or packaged.
- **macOS deployment target:** Binaries may require a macOS version newer than the host's. Universal binaries can bundle multiple architecture slices, yet still must satisfy deployment targets and dependencies.
- **Transitive native dependencies:** An SO library may start loading and fail when the loader cannot locate another SO it links against.

When migrating environments, check which platform built the binary, which compiler/runtime was used, and its minimum OS version requirement. Building on an older yet still-supported baseline environment can broaden compatibility, provided the build process is controlled and verified.

### 4.4. Packaging native dependencies per platform

Three common organizational patterns exist:

1. **Separate artifact per platform:** For instance, each OS and architecture combination gets a dedicated native artifact. Build or dependency resolution picks the matching artifact when assembling packages.
2. **Single artifact bundling multiple native binaries:** A JAR or bundle carries multiple libraries; the application's loader extracts and selects the resource matching OS and architecture.
3. **System-level native installation:** The deployment host or container image installs native dependencies outside the JAR. This requires strict alignment between deployment docs and runtime environments.

Illustrative artifact naming might follow:

```text
engine-native-windows-x86_64
engine-native-linux-x86_64
engine-native-linux-aarch64
engine-native-macos-aarch64
```

This is merely an illustrative naming convention, not an official Maven artifact naming standard. Projects should adopt a stable convention and map it accurately to binaries, ABIs, and library versions.

With Maven or Gradle, profiles, classifiers, variants, or separate module dependencies can select native artifacts. Selection should happen deterministically inside a reproducible build/package pipeline. If one deliverable must run across multiple platforms, bundle all required native resources and choose the matching resource at runtime.

Never rely solely on the build machine's host profile if products build on one OS and deploy to another. Otherwise builds can accidentally bundle the build host's binaries instead of the target environment's. Keep **build platform** and **target platform** clearly distinct.

### 4.5. Extracting native resources from a JAR

A resource inside a JAR does not always have a standard filesystem path. When native loading APIs require a real file, the application must read the resource stream and extract it to a filesystem location before calling System.load.

Illustrative example:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

static Path extractNativeLibrary(String resourceName, String fileName)
        throws IOException {
    Path directory = Files.createTempDirectory("myapp-native-");
    Path library = directory.resolve(fileName);

    try (InputStream input =
            NativeLoader.class.getResourceAsStream(resourceName)) {
        if (input == null) {
            throw new IOException(
                "Native resource not found: " + resourceName
            );
        }

        Files.copy(
            input,
            library,
            StandardCopyOption.REPLACE_EXISTING
        );
    }

    return library.toAbsolutePath();
}
```

After extraction, it can be loaded with System.load(libraryPath.toString()). This snippet illustrates only the extraction step; a complete application must select resourceName and fileName by OS/architecture, handle loading errors, and manage file lifecycles.

When designing a loader, note:

- Resource names must accurately reflect OS, architecture, and ABI.
- The extraction directory must allow write and read permissions for the application account.
- Avoid fixed shared filenames across multiple versions or concurrent processes.
- When caching native libraries, cache keys should include library version and platform, and handle missing, corrupt, or incompatible cache entries.
- On Windows, loaded files are typically locked and difficult to delete immediately; on Unix-like systems, deleting an already-loaded file behaves differently. Never rely on a single cleanup flow across all OSes.
- Never extract untrusted data and load it as executable code. Native binaries must come from controlled, integrity-verified artifacts.

## 5. Environmental factors often overlooked in migrations

Even when OS, architecture, and native libraries match, applications can still behave differently due to runtime configuration.

### 5.1. Java version and distribution

Check the actual Java version via:

```shell
java -version
```

On machines with multiple JDKs, the java executable in PATH may differ from the JDK used by the build tool or service. Record JAVA_HOME, executable paths, and runtime vendor in startup logs.

Beyond language version, verify:

- Bytecode target and minimum APIs used by the application.
- Whether required modules exist in the runtime image.
- Whether JVM options remain valid on the new release.
- Whether native access restrictions, security policies, or native-loading flags changed between releases.
- Whether the JVM vendor and build ship the right architecture, TLS providers, and components.

### 5.2. Locale, timezone, and charset

Applications can emit different outputs if relying on machine default locales or timezones. For example, date formats, decimal separators, and case conversions can vary by locale.

When data requires stable formatting, specify Locale, ZoneId, and Charset explicitly:

```java
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

DateTimeFormatter formatter =
    DateTimeFormatter.ofPattern("uuuu-MM-dd", Locale.ROOT);

String date = formatter.format(
    java.time.LocalDate.now(ZoneId.of("UTC"))
);
```

Choose timezones according to business requirements. Never assume UTC suits every display output, though explicit timezones should be used for stored and exchanged data when system design calls for it.

### 5.3. Environment variables, temp directories, and permissions

Applications running under a service account may have different PATH, HOME, temp directories, and access rights than interactive users. Never assume the application can write into installation folders, root directories, or arbitrary filesystem locations.

Use java.io.tmpdir or standard APIs to resolve temporary storage; test actual write permissions where the app persists files. Sensitive config belongs in deployment secret-management mechanisms rather than hardcoded inside JARs or native bundles.

### 5.4. TLS, certificates, and networking

Trust stores, CA certificates, proxies, DNS resolution, and TLS policies can differ across developer workstations, containers, and servers. An HTTPS failure after migration can stem from trust stores or system certificates even when Java code stayed untouched.

Verify the exact trust store used by the JVM, proxy configuration, and DNS resolution inside the live runtime environment. Avoid disabling certificate verification as a workaround for environment setup issues.

## 6. Building a compatibility matrix before migrating

Before modifying dependencies or pipelines, draft a matrix of environments the product must support. You do not need to test every conceivable combination; document committed combinations and explicitly excluded ones.

Illustrative matrix:

| OS | Architecture | Java runtime | Native variant | Verification status required |
|---|---|---|---|---|
| Windows Server | x86_64 | Product-supported Java version | Windows x86_64 | Build, load, and integration tests |
| glibc-based Linux | x86_64 | Product-supported Java version | Linux x86_64 / glibc | Verify glibc version and dependencies |
| glibc-based Linux | aarch64 | Product-supported Java version | Linux aarch64 / glibc | Verify ARM64 binary |
| Alpine Linux | x86_64 or aarch64 | Java version matching image | musl-compatible binary or alternative | Verify actual ABI |
| macOS | aarch64 | Product-supported Java version | macOS ARM64 or universal | Verify deployment target |

These rows are planning examples, not confirmation that any specific product supports those platforms. Mark support only after dependencies, packaging, and tests are verified.

The matrix should also note minimum OS versions, minimum Java versions, libc or C/C++ runtimes if relevant, container image types, and native binary sources. When a combination is unsupported, deployment documentation should state so explicitly instead of letting failures occur unpredictably in production.

## 7. Controlled migration workflow

### Step 1: Inventory dependencies and environment touchpoints

Search for signs of platform coupling:

- Calls to System.load or System.loadLibrary.
- JNI/JNA/FFM dependencies or libraries with native components.
- DLL, SO, or dylib files in the repository, JARs, or deployment directories.
- Hardcoded paths, OS-specific command names, and shell invocations.
- Code inspecting os.name, os.arch, or file.separator.
- Container configurations, Dockerfiles, and startup scripts.

For each native dependency, record vendor, version, artifact URL or source, supported OS/architectures, ABI, and system dependencies. Inspect transitive dependencies rather than only direct entries in build files.

### Step 2: Define target environments

Lock down target environments and minimum versions. Clarify whether the application runs directly on hosts, inside containers, under a service manager, or in emulation. Identify the JVM process architecture and actual image libc.

When building and deploying across different platforms, declare the target platform explicitly inside pipelines and packaging configs. Never let outputs depend implicitly on the runner host.

### Step 3: Fix OS-specific assumptions

Replace raw filesystem manipulation with cross-platform Java APIs. Standardize charsets and timezones at data boundaries. Wrap OS-specific commands behind a small adapter layer with support validation and clear errors.

If OS-specific APIs are truly required, isolate them behind an interface so business logic does not accumulate platform conditional branches.

### Step 4: Select and package native binaries

Pick a packaging strategy: separate per-platform artifacts, multi-resource bundles, or system-level dependencies. Ensure artifacts match target OS, architecture, and ABI. Verify binary versions, checksums, or signatures per your project release process.

For containers, images must include both the Java runtime and required native system dependencies. Distinguish the base image used to compile native code from the runtime base image; both images must be ABI-compatible.

### Step 5: Test inside target environments

Execute tests on machines or containers matching the target OS and architecture. Verify startup, library loading, live native calls, and business workflows exercising native code. A smoke test confirming only that the JVM boots does not prove native libraries work.

Where physical hardware for an architecture is unavailable, matching runners or controlled emulation can serve for preliminary checks. However, emulated runs do not fully replace testing on real target hardware and OSes.

### Step 6: Record diagnostics and release

Startup logs should report Java version, os.name, os.version, os.arch, the chosen native variant, and native dependency versions. Never write secrets or sensitive data to logs.

If native loading fails, error messages should identify the chosen resource/variant and root cause where determinable. Preserve rollback capability to known-good artifacts and configs, rolling out per environment to isolate issues quickly.

## 8. Testing and diagnostics

### 8.1. Test layers to include

| Test type | Purpose | Example |
|---|---|---|
| Build/package test | Confirm right native artifacts enter package | Inspect JAR or distribution folder contents |
| Startup smoke test | Confirm JVM and startup config are valid | Launch application in target image |
| Native loading test | Confirm loader finds and loads binary | Invoke a minimal native call |
| Integration test | Confirm real native behavior | Encryption, image processing, DB drivers, or hardware I/O |
| Environment test | Confirm filesystem, permissions, commands, encoding | Run under exact service account |
| Regression test | Ensure legacy business behavior holds | Run suite across each target platform |

A simple native-loading test proves only that the library loads. It does not prove every native function, code path, or transitive dependency works.

### 8.2. Collecting environment diagnostics

A small Java utility can print runtime details for diagnostics:

```java
public final class EnvironmentReport {
    public static void main(String[] args) {
        System.out.println("java.version="
            + System.getProperty("java.version"));
        System.out.println("java.vendor="
            + System.getProperty("java.vendor"));
        System.out.println("java.vm.name="
            + System.getProperty("java.vm.name"));
        System.out.println("os.name="
            + System.getProperty("os.name"));
        System.out.println("os.version="
            + System.getProperty("os.version"));
        System.out.println("os.arch="
            + System.getProperty("os.arch"));
        System.out.println("file.encoding="
            + System.getProperty("file.encoding"));
        System.out.println("java.io.tmpdir="
            + System.getProperty("java.io.tmpdir"));
        System.out.println("user.dir="
            + System.getProperty("user.dir"));
    }
}
```

This output helps compare two environments. When troubleshooting native issues, also log the selected variant and library path. Because paths can expose system layout, log them at a level compliant with application logging policies.

### 8.3. Operating system tools

When inspecting binaries, use tools appropriate to the platform and permissions:

- Linux: file to inspect format/architecture; ldd to check dynamic dependencies on trusted binaries; readelf to inspect ELF headers and symbols/versions.
- macOS: file and otool -L to inspect Mach-O architectures and dependencies.
- Windows: dumpbin /DEPENDENTS or corresponding PE/DLL inspection tools to inspect dependencies.
- Java: java -version, system properties, and application logs to confirm active runtime details.

Only run dependency inspection tools against binaries you trust. Some tools resolve dependencies using the host environment, so reconcile findings against the target image or host.

## 9. Design mistakes to avoid

**Assuming JARs are cross-platform, so all dependencies must be cross-platform too.** Pure-Java JARs are generally portable, yet native components depend heavily on OS, architecture, and ABI. Inventory every dependency.

**Using unnormalized OS or architecture names across multiple files.** Aliases like amd64 and x86_64 may refer to the same family. Centralize mapping logic in one module and handle unsupported platforms explicitly.

**Selecting native binaries from the build host instead of the target machine.** A pipeline on Linux x86_64 can accidentally package an x86_64 native library for an app targeting ARM64. Wire target platform into build/packaging steps.

**Checking only whether the native file exists.** The file may have the wrong format, wrong architecture, wrong ABI, or missing transitive dependencies. Load and invoke native code inside the target environment.

**Hardcoding paths and shell commands.** Unix paths, bash commands, or shell quoting fail on Windows. Use standard Java APIs and platform adapters when genuinely needed.

**Relying on default charsets or timezones for exchanged data.** Results vary across environments. Specify charsets, locales, and timezones explicitly per business needs.

**Building native libraries on modern hosts without bounding minimum ABI.** Binaries may demand newer glibc or C/C++ runtime versions than target servers offer. Pin minimum targets and test on them.

**Ignoring the service execution account.** Apps succeeding in an IDE under user permissions may fail under a service account lacking write access to temp folders, file read rights, or command execution rights.

## 10. Pre-completion migration checklist

- [ ] Identified minimum Java version and actual runtime per environment.
- [ ] Listed committed OSes and architectures.
- [ ] Inventoried direct and transitive native dependencies.
- [ ] Identified ABI, libc, and system runtime requirements of native binaries.
- [ ] Separated build platform from target platform.
- [ ] Configured native artifact selection by target OS/architecture/ABI.
- [ ] Handled paths, filesystem permissions, commands, and encodings appropriately.
- [ ] Verified container images include required native system dependencies.
- [ ] Executed smoke tests, native loading tests, and integration tests on target environments.
- [ ] Logged runtime information and chosen native variants for diagnostics.
- [ ] Documented unsupported platforms and prepared a rollback plan.

## Conclusion

Environment compatibility in Java migration combines JVM execution capability, OS behavior, process architecture, and native library ABIs. Java bytecode is shareable, whereas native binaries and system dependencies must be selected, packaged, and tested per target environment.

A reliable migration process starts with building a platform matrix, inventorying native dependencies, decoupling build platform from target platform, and verifying the application on the exact supported OS/architecture/ABI. Once environmental assumptions are documented and automated in tests, upgrading Java or switching servers becomes predictable and straightforward to diagnose.
