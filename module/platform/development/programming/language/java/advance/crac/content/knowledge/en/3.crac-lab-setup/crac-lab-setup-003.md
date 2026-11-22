# Checking CRaC Support of the Build in Use

Before designing or running an application with CRaC (Coordinated Restore at Checkpoint), it is necessary to determine exactly which JDK build is being used and to what extent that build supports it. A project may compile successfully with the CRaC API yet run on a regular JVM; a development machine may use a CRaC-enabled JDK while the Gradle daemon or deployment container uses a different JDK.

Therefore, the check results need to answer four questions:

1. Which JDK are the build tool and compiler using?
2. Does the JVM that actually runs the application recognize CRaC options?
3. Does the JVM control tool provide the checkpoint command?
4. Can the operating system, CRIU, and deployment environment perform an actual checkpoint/restore?

One should not conclude solely from the vendor name or Java version string. A JVM option check can confirm that the runtime is CRaC-aware, but only a successful checkpoint and restore in the target environment confirms the entire execution path.

## 1. Distinguishing the Layers to Check

CRaC involves multiple components. Each check only proves one part of the support capability.

| Layer | What to Determine | Appropriate Evidence |
| --- | --- | --- |
| Compile-time API | Whether the project can reference types such as `org.crac.Resource` | The build compiles successfully with the CRaC API dependency |
| Runtime JVM | Whether the JVM recognizes CRaC options and mechanisms | The `-XX:CRaCCheckpointTo` option is accepted; the JDK build is clearly identified |
| Control tool | Whether the JVM can be requested to checkpoint using the bundled tool | `jcmd` attaches to the right process and lists the `JDK.checkpoint` command |
| Operating system environment | Whether the checkpoint/restore mechanism works on the target machine or container | CRIU and kernel meet requirements; a checkpoint-then-restore test succeeds |
| Application | Whether application resources and state can pass through both checkpoint/restore points | Callbacks run properly, resources are reconnected, and the application reaches readiness |

These layers are related to each other but cannot substitute evidence for one another. Having the API dependency does not prove the JVM supports checkpointing. The JVM accepting the option also does not prove CRIU has sufficient permissions to dump the process image. A successfully created image still does not prove the application has properly reconnected external services.

## 2. Identifying the Exact JDK Being Used

First, record the path and information of the Java executable that the current command finds. Do not just record the version; it is necessary to know the exact directory the executable comes from.

### 2.1. Checking on Windows PowerShell

Run the following commands in the same terminal you use to build or run the application:

```powershell
# All java locations found on PATH
Get-Command java -All | Select-Object Source
where.exe java

# JDK that the current java command actually runs
java -version
java -XshowSettings:properties -version 2>&1 |
    Select-String 'java.home|java.vendor|java.runtime.version|os.name|os.arch'

# Environment variable, if configured
$env:JAVA_HOME

# Check tools bundled with the JDK
javac -version
jcmd -l
```

Information to save includes:

- The first `java.exe` path found on `PATH`.
- `java.home`, `java.vendor`, and `java.runtime.version`.
- `javac` version and the ability to invoke `jcmd`.
- Operating system and CPU architecture.

`JAVA_HOME` is only an environment variable. If `PATH` points to a different Java directory, the `java` command can still run a different executable than the directory declared in `JAVA_HOME`. Therefore, it is necessary to cross-check both the path and the runtime properties.

### 2.2. Checking on Linux

```bash
# Java path found by the shell
command -v java
which -a java
readlink -f "$(command -v java)"

# Runtime and environment information
java -version
java -XshowSettings:properties -version 2>&1 \
  | grep -E 'java.home|java.vendor|java.runtime.version|os.name|os.arch'

# Environment variable and JDK tools
echo "$JAVA_HOME"
javac -version
jcmd -l
```

If multiple JDKs are installed on the machine, run commands using absolute paths to avoid confusion:

```bash
"$JAVA_HOME/bin/java" -version
"$JAVA_HOME/bin/javac" -version
"$JAVA_HOME/bin/jcmd" -l
```

Absolute paths help confirm that the tools are taken from the same JDK. When inspecting a running process, it is also necessary to use `jcmd` corresponding to that process's JDK and an account with appropriate attach permissions.

### 2.3. Checking Gradle's JDK and the Application Runtime JDK

The `java -version` command in the terminal only tells you which Java the shell finds. It is not necessarily the Java that Gradle, the IDE, the container, or the deployment service is using.

For a Gradle project, run:

```bash
./gradlew --version
```

On Windows:

```powershell
.\gradlew.bat --version
```

Read the JVM section in the output to identify the JDK used for Gradle. If the project declares a Java Toolchain, the compiler may use a different JDK from the JVM running Gradle. When the project applies the Java plugin, you can view the toolchains Gradle detects with:

```bash
./gradlew javaToolchains
```

When you need to confirm the compiler selected for a specific task, inspect the compile task log in info mode:

```bash
./gradlew compileJava --info
```

The application runtime JDK must be checked separately. If the application runs in a container, execute `java -version` and check the Java path directly inside the running container. The JDK on the host machine does not prove the deployment image has the same runtime.

Distinguish at least three values:

| Location | Question to Answer |
| --- | --- |
| Gradle daemon or Maven process | Which JDK is the build tool running on? |
| Java compiler/toolchain | Which JDK is the source code compiled with? |
| Actual runtime | Which JVM is running the JAR or application in the target environment? |

If the values differ, test CRaC on the exact actual runtime. A good result from the JDK on a developer's machine cannot represent the JDK in a production container.

## 3. Checking the CRaC API at Compile Time

The CRaC API provides types for the application to register resources and receive callbacks before checkpoint and after restore. Commonly used types are in the `org.crac` package, for example:

```java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;
```

In a Gradle project, the API can be declared with the `org.crac:crac` dependency according to the version managed by the project:

```groovy
dependencies {
    implementation("org.crac:crac:$cracApiVersion")
}
```

`cracApiVersion` in the example is a value that must be declared in the project's version catalog, convention, or dependency configuration. Use a version compatible with the JDK and libraries being deployed.

After the dependency is configured, you can run the project's Java compile task to confirm the compiler finds the API:

```bash
./gradlew compileJava
```

If the source code references `org.crac` and the build compiles successfully, that proves the compile classpath has the required API. This result **does not prove the runtime JVM supports CRaC**. The API dependency can allow the source code to compile on a regular JDK; at runtime, the JVM may still not recognize checkpoint options.

Therefore, record two separate results: `API_COMPILE=PASS/FAIL` and `JVM_CRAC=PASS/FAIL`. Do not combine them into a single conclusion.

## 4. Checking Whether the JVM Recognizes CRaC Options

JDK builds with CRaC integration typically provide an option to specify the checkpoint directory and a restore option. Common names are:

- `-XX:CRaCCheckpointTo=<directory>`: specifies where to save the checkpoint when a checkpoint request is made.
- `-XX:CRaCRestoreFrom=<directory>`: launches the process by restoring from an existing checkpoint.

Option names and usage must be cross-checked against the documentation of the exact JDK distribution. The test below only checks whether the JVM recognizes the checkpoint option; it does not create a checkpoint and does not confirm that CRIU works.

### 4.1. Probing Option Recognition on Windows

```powershell
$checkpointDir = Join-Path $env:TEMP 'crac-flag-probe'
java "-XX:CRaCCheckpointTo=$checkpointDir" -version
$LASTEXITCODE
```

If the JVM recognizes the option, the command usually prints version information and returns exit code `0`. If the JVM reports `Unrecognized VM option` or a similar message, the executable being invoked does not recognize that option. Re-check the `java.exe` path, the JDK vendor, and the installed CRaC build.

### 4.2. Probing Option Recognition on Linux

```bash
java -XX:CRaCCheckpointTo=/tmp/crac-flag-probe -version
echo $?
```

Exit code `0` along with version information indicates that the JVM accepted the option in this test. If you need to eliminate ambiguity about `PATH`, replace `java` with the absolute path to the executable identified in the previous step.

Do not use the restore option with a directory that does not yet have a checkpoint to test recognition. The JVM may attempt to restore and report an error because the image does not exist yet; that result is not an appropriate test for option recognition.

### 4.3. Interpreting Results Correctly

| Result | What Can Be Concluded | What Cannot Be Concluded Yet |
| --- | --- | --- |
| JVM reports the option is unrecognized | The executable being tested does not provide that option | Not yet known whether another JDK on the machine supports it |
| JVM accepts the option and prints the version | That JVM build recognizes the checkpoint option | Not yet confirmed: actual checkpoint, CRIU, OS permissions, or application callbacks |
| JVM reports CRaC is not supported on the current platform | The current build or platform cannot execute the requested path | Does not rule out using that JDK in another compatible Linux environment |
| Test succeeds on the host | The runtime on the host recognizes the option | Does not prove the runtime inside the container or target machine is identical |

Do not infer solely from version strings such as `21.x`, `17.x`, or the vendor name. Some vendors have multiple different JDK variants; CRaC capability depends on the specific distribution, version, and platform.

## 5. Checking the Checkpoint Command in jcmd

`jcmd` is a diagnostic tool bundled with the JDK that can send management commands to a running JVM. For CRaC JDK builds that support this interface, the checkpoint command is usually named `JDK.checkpoint`.

First, launch a test Java process using the exact JDK to be checked. Then list the processes:

```bash
jcmd -l
```

This command displays the Java processes that the tool can detect. Take the PID of the process to check and request the list of commands supported by that JVM:

```bash
jcmd <pid> help
```

Look for `JDK.checkpoint` in the output. If present, the JVM provides the checkpoint control command via `jcmd`. If absent, verify:

- whether the PID belongs to the process launched with the intended CRaC JDK;
- whether `jcmd` comes from the same JDK as the process;
- whether the current account has permission to attach to the process;
- whether the process has disabled the attach mechanism or is running in a restricted environment.

You can view additional information about the target JVM with:

```bash
jcmd <pid> VM.version
jcmd <pid> VM.command_line
```

These two commands help identify the JVM build and startup arguments of the actual process. On Windows, use `jcmd.exe` in the `bin` directory of the JDK being checked and pass the PID in the same way.

Having `JDK.checkpoint` in `jcmd` is stronger evidence than merely recognizing a JVM flag, but it still does not prove the checkpoint operation will succeed. It must be tested in an environment with a compatible checkpoint/restore backend.

## 6. Checking CRIU and the Linux Environment

In the common CRaC implementation on Linux, CRIU (Checkpoint/Restore In Userspace) performs the OS-level dumping and restoring of process state. The JVM may recognize CRaC options yet checkpointing still fails if CRIU is missing, the kernel does not meet requirements, or the container lacks necessary permissions.

On the Linux machine or inside the target container, check:

```bash
criu --version
criu check
```

`criu --version` shows the tool version. `criu check` verifies several capabilities and environmental conditions required by CRIU. Read the full output and exit code; do not rely solely on the command existing.

If CRIU reports missing permissions or kernel features, check the run mode, kernel configuration, and container policies. Some container environments restrict capabilities, namespaces, or process operations, preventing CRIU from functioning. Required permissions depend on the CRIU version, kernel, and implementation; do not copy a fixed list of capabilities across every environment.

In addition to CRIU, confirm:

- The checkpoint directory exists or can be created by the application process.
- The process has write permission to the directory and sufficient disk space to store the image.
- The checkpoint path is accessible in the restore environment.
- The JDK, native libraries, CPU architecture, and OS configuration are compatible between image creation and restore.
- Security policies and the container runtime allow the operations required by CRIU.

CRaC and CRIU are typically deployed in Linux environments. If the development machine is Windows or macOS, the JVM accepting an option does not mean the host machine can perform a checkpoint. Test in the exact Linux VM, WSL, or container that will run the application; the final result must come from the actual deployment environment. WSL or containers must also satisfy CRIU's kernel and permission requirements and are not automatically supported just by having a Linux shell.

## 7. Performing a Checkpoint/Restore Smoke Test

After static checks, use a small test application to verify the entire execution path. Only perform this in an isolated environment, with test data and without connecting to real business services. The goal is to prove that the JVM can create a checkpoint, restore the process, and invoke application callbacks.

### 7.1. Creating a Test Resource

The following snippet registers a resource in the global context and logs at both lifecycle points:

```java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class CracProbe implements Resource {

    public CracProbe() {
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        System.out.println("CRAC_PROBE: beforeCheckpoint");
        System.out.flush();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        System.out.println("CRAC_PROBE: afterRestore");
        System.out.flush();
    }

    public static void main(String[] args) throws InterruptedException {
        new CracProbe();
        System.out.println("CRAC_PROBE: application started");
        System.out.flush();

        while (true) {
            Thread.sleep(1_000);
        }
    }
}
```

Ensure the runtime classpath includes the corresponding CRaC API if the JDK build does not provide that API out of the box. This snippet only serves to test callbacks; it does not represent how to manage connection pools, consumers, or real resources in an application.

### 7.2. Launching the Process and Creating a Checkpoint

On Linux, for example, launch the application with a dedicated checkpoint directory:

```bash
mkdir -p /tmp/crac-probe-image
java -XX:CRaCCheckpointTo=/tmp/crac-probe-image \
  -cp "<classpath>" CracProbe
```

Note the PID printed by the JVM or find the process using `jcmd -l`. In another terminal, use `jcmd` from the same JDK to request a checkpoint:

```bash
jcmd <pid> JDK.checkpoint
```

Observe the logs to confirm `CRAC_PROBE: beforeCheckpoint` appears and check the result of the checkpoint operation. If the command fails, save all messages from the JVM, `jcmd`, and CRIU to identify the failing layer.

### 7.3. Restoring from the Created Image

Once the checkpoint is created successfully, use the same JDK build and image directory to restore according to the syntax of the distribution in use. For JDK builds supporting the common option, the command takes the form:

```bash
java -XX:CRaCRestoreFrom=/tmp/crac-probe-image
```

The expected result is that the process is restored, the `CRAC_PROBE: afterRestore` log appears, and the application continues running. Syntax, classpath packaging, and process behavior may depend on the JDK distribution; always cross-check the documentation of the specific runtime.

A passing smoke test must confirm all of the following points:

1. The JVM can launch the application with the checkpoint option.
2. `jcmd` can send the `JDK.checkpoint` command to the right process.
3. CRIU completes dumping the image without reporting environment errors.
4. The JVM can restore the image using a compatible environment.
5. The `afterRestore` callback is invoked and the application continues operating.

If the real application has external resources, add separate tests for reconnection and readiness. A minimal smoke test only confirms the underlying mechanism, not that all resources of the real application are safe.

## 8. Reading Errors by the Right Layer

When a check fails, classify the error before changing the JDK or modifying application code.

| Symptom | Possible Cause | What to Check Next |
| --- | --- | --- |
| `Unrecognized VM option` for `CRaCCheckpointTo` | Using a JDK that does not support the option or invoking the wrong Java executable | Check `PATH`, `JAVA_HOME`, Gradle JVM, and runtime in the container |
| `org.crac` API not found at compile time | Missing API dependency or incorrect classpath configuration | Check dependency and compiler/toolchain configuration |
| Compilation succeeds but JVM does not recognize option | API is present on the classpath but runtime is not a suitable CRaC JDK | Check the JDK used to run the application |
| `jcmd` does not find the process | Wrong tool used, process not discovered, or different account/environment | Use `jcmd` from the same JDK, check PID and attach permissions |
| No `JDK.checkpoint` in command list | Process is not running on a suitable CRaC JVM or attach command targeted the wrong JVM | Check `VM.version`, `jcmd` path, and JDK documentation |
| `JDK.checkpoint` fails with CRIU error | Missing kernel support, permissions, namespaces, or environment configuration | Run `criu check` in the target environment itself and view full logs |
| Image created but restore fails | Restore environment differs from image creation environment or image is incompatible | Cross-check JDK, architecture, kernel, native libraries, paths, and launch arguments |
| Restore succeeds but application callbacks or connections fail | External resources or state not handled properly | Check callback order, closing/reopening of resources, and application logs |

An error in the checkpoint step should not be handled by disabling callbacks by default or ignoring resource errors. If a required resource is not yet in a safe state, the created image may not be usable reliably.

## 9. Documenting Check Results

So others can reproduce the results, clearly record the environment and evidence. A short report template may include:

| Field | Value to Record |
| --- | --- |
| OS and architecture | OS name, kernel version if Linux, CPU architecture |
| Java executable | Absolute path to `java` |
| JDK vendor/version | `java.vendor`, `java.runtime.version`, `java.home` |
| Gradle/Maven JVM | Output of `gradlew --version` or `mvn -version` |
| Java toolchain | JDK compiler selected for the build task |
| API compile | PASS/FAIL and API dependency used |
| CRaC JVM option | PASS/FAIL, command executed, and exit code |
| jcmd checkpoint command | Presence/absence of `JDK.checkpoint` on the right PID |
| CRIU | Version, `criu check` result, and execution environment |
| Checkpoint | PASS/FAIL, image path, and error messages if any |
| Restore | PASS/FAIL, JDK used for restore, and callback logs |
| Application | PASS/FAIL, reconnection results, and readiness if tested |

Do not record secrets, tokens, user data contents, or checkpoint files in the report. Only save configuration information necessary to identify the environment and reproduce the test.

## 10. Conclusion Criteria

Results can be classified according to the following levels:

- **API_READY:** source code compiles with the CRaC API. Confirms compilation capability only.
- **JVM_OPTION_READY:** the actual JVM recognizes the checkpoint option. Confirms the runtime is option-aware only.
- **JVM_CONTROL_READY:** `jcmd` attaches to the right JVM and has the `JDK.checkpoint` command.
- **PLATFORM_READY:** CRIU and the operating system environment meet checkpoint/restore requirements.
- **CRAC_SMOKE_TEST_PASS:** checkpoint creation, restore, and callbacks all succeed in a test environment.
- **APPLICATION_READY:** the real application has verified resources after restore, reconnected to services, and achieved readiness per operational requirements.

An application should only be declared ready to use CRaC when the required checks for the runtime and platform have passed, and the application's resources have been verified. If only the API or JVM options have been checked, report that exact level and clearly state the remaining steps.

## 11. Conclusion

Checking CRaC must start with identifying the exact JDK of the build tool, compiler, and runtime. Then confirm the compile-time API, JVM options, `JDK.checkpoint` command, CRIU, and operating system conditions. The final evidence is a smoke test that creates a checkpoint, restores the process, and invokes the post-restore callback.

Results are only valid for the exact JDK build, architecture, and environment tested. When changing the JDK, base image, kernel, or container configuration, re-test on the new environment before releasing an application using CRaC.
