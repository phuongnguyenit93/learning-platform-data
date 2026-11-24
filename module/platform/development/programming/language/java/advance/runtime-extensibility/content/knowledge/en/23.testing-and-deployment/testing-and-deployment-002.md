# Running an Application from Real JARs and Module Path in a Separate Test Process

## 1. Goal of Artifact Integration Testing

In a Java plugin system, testing against `target/classes`, `build/classes`, or an IDE classpath does not fully reflect the shipped product. A distribution JAR may be missing `module-info.class`, `META-INF/services`, or dependencies, or it may contain conflicting packages. Module resolution and `ServiceLoader` can also behave differently when moving from the classpath to the module path. Therefore, you need to build the actual JARs, then invoke the Java launcher in a **new child process** with the exact `--module-path` used in production.

What needs to be verified: artifact contents, module descriptors, root/provider resolution, startup, exit code, stdout/stderr, timeouts, and scenarios where a module or provider is intentionally missing. A forked JVM reduces the influence of static state and the test runner's boot module layer; it is not by default a security sandbox for malicious code.

```text
Compile -> Package modular JARs -> dist/
                                   |
Test runner -- ProcessBuilder ---> java --module-path dist --module host/main
                                   |
                    exit code + stdout + stderr + timeout
                                   |
                         Assertions / diagnostics
```

## 2. Java 17+ Example: Modular API, Provider, and Host

Directory structure:

```text
demo/
  src/
    demo.api/
      module-info.java
      demo/api/Greeter.java
    demo.provider/
      module-info.java
      demo/provider/EnglishGreeter.java
    demo.host/
      module-info.java
      demo/host/Main.java
  dist/
```

`src/demo.api/module-info.java`:

```java
module demo.api {
    exports demo.api;
}
```

`src/demo.api/demo/api/Greeter.java`:

```java
package demo.api;
public interface Greeter {
    String greet(String name);
}
```

`src/demo.provider/module-info.java`:

```java
module demo.provider {
    requires demo.api;
    provides demo.api.Greeter with demo.provider.EnglishGreeter;
}
```

`src/demo.provider/demo/provider/EnglishGreeter.java`:

```java
package demo.provider;
import demo.api.Greeter;
public final class EnglishGreeter implements Greeter {
    public EnglishGreeter() {}
    @Override public String greet(String name) {
        return "Hello, " + name;
    }
}
```

`src/demo.host/module-info.java`:

```java
module demo.host {
    requires demo.api;
    uses demo.api.Greeter;
}
```

`src/demo.host/demo/host/Main.java`:

```java
package demo.host;
import demo.api.Greeter;
import java.util.List;
import java.util.ServiceLoader;
public final class Main {
    public static void main(String[] args) {
        List<Greeter> providers = ServiceLoader.load(Greeter.class)
                .stream().map(ServiceLoader.Provider::get).toList();
        if (providers.size() != 1) {
            System.err.println("Expected one Greeter, got "
                    + providers.size());
            System.exit(3);
        }
        System.out.println(providers.get(0).greet("Java"));
    }
}
```

The host only `requires demo.api` and `uses demo.api.Greeter`; the provider declares `provides` and does not need to export its implementation package for SPI. This is a small test, yet it covers module descriptor, service binding, and distribution risks.

## 3. Building the Exact Final Modular JARs

Inside the `demo` directory, run on JDK 17+:

```bash
mkdir -p mods dist
javac --module-source-path src -d mods --module demo.api,demo.provider,demo.host
jar --create --file dist/demo.api.jar -C mods/demo.api .
jar --create --file dist/demo.provider.jar -C mods/demo.provider .
jar --create --file dist/demo.host.jar -C mods/demo.host .
java --module-path dist --add-modules demo.provider --module demo.host/demo.host.Main
```

Program output:

```text
Hello, Java
```

Point the module path to the `dist` directory: do not use `mods` in the final run command. `--add-modules demo.provider` forces the provider to be resolved explicitly; other setups can rely on service binding, but this test intentionally guarantees the provider's presence.

Inspect descriptors after packaging:

```bash
jar --describe-module --file dist/demo.api.jar
jar --describe-module --file dist/demo.provider.jar
jar --describe-module --file dist/demo.host.jar
```

Confirm that `exports demo.api`, `provides demo.api.Greeter with demo.provider.EnglishGreeter`, `uses demo.api.Greeter`, and `requires demo.api` appear in the right modules. Compiling successfully from source does not guarantee that downstream tooling preserves `module-info.class`.

## 4. Forking the JVM with ProcessBuilder

Place `ForkedModuleTest.java` in the `demo` directory, outside the modular source structure:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.List;
import java.util.concurrent.TimeUnit;

public final class ForkedModuleTest {
    public static void main(String[] args) throws Exception {
        String java = Path.of(System.getProperty("java.home"),
                "bin", "java").toString();
        Path dist = Path.of("dist").toAbsolutePath();
        List<String> command = List.of(
                java, "--module-path", dist.toString(),
                "--add-modules", "demo.provider",
                "--module", "demo.host/demo.host.Main");

        Process p = new ProcessBuilder(command)
                .redirectErrorStream(true)
                .start();
        boolean exited = p.waitFor(10, TimeUnit.SECONDS);
        if (!exited) {
            p.destroyForcibly();
            p.waitFor();
            throw new AssertionError("Forked JVM timed out");
        }
        String combined = new String(
                p.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
        if (p.exitValue() != 0) {
            throw new AssertionError("Exit=" + p.exitValue()
                    + "; output=" + combined);
        }
        if (!combined.strip().equals("Hello, Java")) {
            throw new AssertionError("Unexpected output=" + combined);
        }
        System.out.println("Forked module test PASS");
    }
}
```

Run:

```bash
javac --release 17 ForkedModuleTest.java
java ForkedModuleTest
```

Passing output:

```text
Forked module test PASS
```

**Limitation of this example:** calling `waitFor()` before draining stdout/stderr is only safe when output is small and bounded. If the child writes more than the pipe buffer, it can block on write and cause `waitFor` to time out even when the program has no bug. In a production test harness, drain stdout and stderr **concurrently while the process is running** using reader threads or redirect to size-bounded files. If a test needs to distinguish stderr, do not set `redirectErrorStream(true)`: capture the two streams separately. Every fork must have a timeout and child-process cleanup.

## 5. Negative Testing: Missing Provider

Create a folder containing only the host and API JARs, without the provider:

```bash
mkdir -p dist-no-provider
cp dist/demo.api.jar dist-no-provider/
cp dist/demo.host.jar dist-no-provider/
java --module-path dist-no-provider --module demo.host/demo.host.Main
```

On a Unix/macOS shell, the host prints to stderr:

```text
Expected one Greeter, got 0
```

The exit code is `3` as defined by the host program. On Windows, use `Copy-Item` instead of `cp`. This is an **intentional negative test**: the test must assert the exact expected failure and must not treat a nonzero exit as normal success.

Add another test with `demo.api.jar` missing: the launcher will report a missing-module error before `main`. Because the launcher's exit code depends on the environment/JDK, assert only **nonzero** and a message mentioning the missing module, rather than hard-coding an arbitrary exit code.

## 6. Common Packaging Failure Cases

| Symptom | Likely Cause | Check |
| --- | --- | --- |
| IDE sees provider but JAR does not | Service registration file lost/overwritten | JAR entries, `provides`, and module resolution |
| `FindException` at startup | Dependency not on module path | Descriptor, actual module path |
| `ResolutionException` | Graph has split package/readability conflict | JAR packages, module graph |
| `NoClassDefFoundError` at runtime | Missing dependent class, dependency only in compile scope | Artifact dependencies and actual path |
| `ClassCastException` between host/plugin | API loaded by two classloaders | API identity, parent delegation |
| Unexpected automatic module name | Non-modular JAR derives name from filename | `jar --describe-module` |
| Test passes locally but production fails | Different JDK/flags/OS/working dir | Log command, env, JDK version |

Test artifacts after shading/relocation, not just pre-transform JARs. If `META-INF/services` is present, service descriptors must be preserved/merged properly; JPMS explicit modules rely on `provides` inside `module-info.class`.

## 7. Integrating with Maven/Gradle and CI

In Maven, integration tests can run after `package` in the `verify` phase; Gradle can configure a task that depends on `jar`/distribution and runs `Exec` with a module path built from outputs. Tool-agnostic core principles:

1. A clean build creates fresh JARs and tests use those exact files, never stale artifacts.
2. Run the Java executable/version matching the target; if using a toolchain, specify the child JDK explicitly.
3. Do not inject IDE classpath entries into the child if production does not use them.
4. Log the command, exit code, and redacted stdout/stderr for debugging.
5. Enforce timeouts, output limits, and child process tree cleanup.
6. Include both happy paths and negative paths for missing provider/module, split package, and bad descriptors.

Module path entries are separated by `;` on Windows and `:` on Unix/macOS. When pointing to a single `dist` directory, the separator does not matter. In `ProcessBuilder`, pass each argument as a separate element, avoiding concatenating into a single shell string that causes quoting bugs.

## 8. Managing Reproducibility and Isolation

A forked JVM provides a fresh boot layer, static caches, and system properties for each test. If plugins use ports, file locks, or external services, tests can still interfere with one another; use distinct fixture names, temporary directories, and cleanup. Do not assume a forked JVM is a secure sandbox: running untrusted code requires an OS user/container with restricted privileges.

To reduce flakiness, control the working directory, locale, timezone, and encoding when output depends on them. Do not assert compiler/launcher messages verbatim across multiple JDKs if cross-platform compatibility is the goal; prefer asserting exception class, module name, and exit status.

## 9. Implementation Checklist

- [ ] Tests use the actual release JARs and `--module-path`, not classes directories.
- [ ] Post-packaging module descriptors have correct `requires`, `exports`, `uses`, `provides`.
- [ ] Providers are intentionally resolved into the runtime graph.
- [ ] Fork a new JVM using the Java executable of the target JDK.
- [ ] Assert exit code, stdout/stderr, timeout, and process cleanup.
- [ ] For large output, drain streams concurrently while the process runs.
- [ ] Include negative tests for missing provider, missing dependency, and split packages.
- [ ] Clean build; record the exact command line and environment.
- [ ] Do not confuse process isolation with a security sandbox.

**Conclusion:** testing with real modular JARs in a separate process catches packaging, module resolution, and SPI discovery bugs that tests inside an IDE can miss. Only consider a distribution ready when forked tests using the exact shipped artifacts and actual launcher all pass.
