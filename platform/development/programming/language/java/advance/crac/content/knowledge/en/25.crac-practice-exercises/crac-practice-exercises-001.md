# Creating a Minimal Java Program and Performing Checkpoint–Restore

This practice exercise creates a small Java program, registers CRaC callbacks, runs the program on a CRaC-enabled JDK, creates a checkpoint image, and then restarts the process from that image.

The program prints the PID and an incrementing counter. On checkpoint, the beforeCheckpoint() callback prints a message. On restore, the afterRestore() callback prints another message and the loop continues with the counter value from before the checkpoint.

This exercise uses jcmd so learners can clearly observe the three operations: running the application, creating a checkpoint, and restoring. The commands below are for a Linux environment with a CRaC JDK and the kernel/runtime prerequisites required by the distribution.

## 1. Expected Outcome

~~~text
Compile the program
       |
       v
Launch with a CRaC JDK
       |
       v
Application prints PID and incrementing ticks
       |
       v
jcmd <pid> JDK.checkpoint
       |
       v
beforeCheckpoint() is called
       |
       v
Runtime writes checkpoint image
       |
       v
Original process exits after successful checkpoint
       |
       v
java -XX:CRaCRestoreFrom=<image>
       |
       v
afterRestore() is called
       |
       v
Counter resumes from the checkpointed state
~~~

When practiced successfully, you will observe:

- A checkpoint image is created in the specified directory.
- beforeCheckpoint() runs before the runtime saves state.
- The process is restored from the image.
- afterRestore() runs in the restored process.
- The counter variable continues incrementing from its pre-checkpoint value instead of resetting to 0.

A checkpoint image saves process state according to the capabilities of the CRaC JDK and the underlying checkpoint/restore mechanism. It is not a backup of the entire machine or filesystem.

## 2. Preparing the Environment

You need:

- A JDK distribution with CRaC support.
- A JDK version compatible with the CRaC API used for compilation.
- Maven 3.x.
- A Linux environment meeting the kernel, CRIU, permission, and container configuration requirements of the JDK distribution.
- Permission to run jcmd as the same user that owns the JVM.
- A dedicated directory to store the checkpoint image.

CRaC requires support from the runtime and the OS environment. Simply adding the API library to a regular JDK does not turn that JDK into one capable of checkpoint/restore.

### Checking JDK and Maven

~~~bash
java -version
javac -version
jcmd -l
mvn -version
~~~

Confirm that java, javac, and jcmd come from the same CRaC JDK. If PATH points to multiple different JDKs, use the absolute path to the bin directory of the distribution you want to test.

CRIU, kernel, permission, and container requirements vary by distribution. Read the installation guide for the CRaC JDK you are using before running checkpoint. Do not assume every Linux container or every WSL environment meets those requirements.

## 3. Creating the Project Structure

Create a minimal Maven project:

~~~text
crac-minimal/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── cracdemo/
                        └── Main.java
~~~

You can create the directories via shell:

~~~bash
mkdir -p crac-minimal/src/main/java/com/example/cracdemo
cd crac-minimal
~~~

The checkpoint directory will sit outside Maven's target/. That way, running mvn clean does not accidentally delete the image used for restore.

## 4. Declaring the CRaC API in Maven

Create the pom.xml file:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>crac-minimal</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.crac</groupId>
            <artifactId>crac</artifactId>
            <version>1.4.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

org.crac:crac provides API types such as Core, Resource, and Context. Version 1.4.0 is an example version to pin the dependency and keep project compilation repeatable. When working with a specific CRaC JDK, choose the API version supported by that distribution.

maven.compiler.release sets the target Java language level. If your CRaC JDK uses Java 21, you can change the value to 21 after verifying compatible Maven compiler and API versions.

## 5. Writing the Minimal Java Program

Create src/main/java/com/example/cracdemo/Main.java:

~~~java
package com.example.cracdemo;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class Main {

    public static void main(String[] args) throws InterruptedException {
        Core.getGlobalContext().register(new DemoResource());

        long counter = 0;

        System.out.println(
            "[APP] started; pid=" + ProcessHandle.current().pid()
        );
        System.out.flush();

        while (true) {
            counter++;

            System.out.println("[APP] tick=" + counter);
            System.out.flush();

            Thread.sleep(1_000);
        }
    }

    private static final class DemoResource implements Resource {

        @Override
        public void beforeCheckpoint(
                Context<? extends Resource> context) {
            System.out.println("[CRAC] beforeCheckpoint");
            System.out.flush();
        }

        @Override
        public void afterRestore(
                Context<? extends Resource> context) {
            System.out.println("[CRAC] afterRestore");
            System.out.flush();
        }
    }
}
~~~

### Explaining the Program

Core.getGlobalContext() returns the global CRaC context. Call register() to register a Resource with the runtime.

Resource has two callbacks:

- beforeCheckpoint(): invoked when the runtime prepares to create a checkpoint. The application uses this callback to bring resources to a safe state.
- afterRestore(): invoked after the process is restored. The application uses this callback to reopen or verify necessary resources.

In this exercise, the callbacks only print messages for easy observation. The program holds no database connections, sockets, or external file handles, so no logic to close/reopen those resources is needed.

The counter variable is a local variable in main(). On checkpoint, thread and stack state of the process are saved according to runtime capabilities. After restore, the loop continues with the saved state. This is the observation point that distinguishes a restore from starting a fresh JVM from scratch.

ProcessHandle.current().pid() is only for displaying the process PID. Do not assume the PID before and after restore must be identical; that depends on the environment and how the runtime performs restore.

## 6. Compiling and Preparing Dependencies

From the project root directory:

~~~bash
mvn clean package
mvn dependency:copy-dependencies \
  -DincludeScope=runtime \
  -DoutputDirectory=target/dependency
~~~

Once complete, the files needed include:

~~~text
target/classes/com/example/cracdemo/Main.class
target/dependency/crac-<version>.jar
~~~

If Maven cannot download the dependency, check repository access and the declared org.crac:crac version. Do not switch to another JDK just to bypass compilation errors without confirming that runtime supports CRaC.

## 7. Launching the Program with a Checkpoint Directory

Use a new checkpoint directory with an explicit path. Linux example:

~~~bash
mkdir -p /tmp/crac-minimal-checkpoint
~~~

If the directory already contains an image from a previous attempt, choose another directory or clean up the old artifact after confirming no restore process is still using it. Avoid overwriting an image currently in use.

Launch the application:

~~~bash
java \
  -XX:CRaCCheckpointTo=/tmp/crac-minimal-checkpoint \
  -cp "target/classes:target/dependency/*" \
  com.example.cracdemo.Main
~~~

The application will print the PID and tick lines:

~~~text
[APP] started; pid=24180
[APP] tick=1
[APP] tick=2
[APP] tick=3
[APP] tick=4
~~~

Keep this terminal open to observe logs. Note the PID printed on the [APP] started line.

CRaCCheckpointTo specifies where the runtime writes the checkpoint image. Depending on the distribution, the runtime may require auxiliary files or specific filesystem conditions; use a dedicated directory for the attempt and do not edit the image contents manually.

## 8. Creating a Checkpoint with jcmd

Open a second Linux terminal, navigate to the project directory, and use the recorded PID:

~~~bash
jcmd 24180 JDK.checkpoint
~~~

Replace 24180 with the program's actual PID.

If needed, use the full path to jcmd from the same CRaC JDK running the application:

~~~bash
/path/to/crac-jdk/bin/jcmd 24180 JDK.checkpoint
~~~

When the callback is invoked, the terminal running the application will show:

~~~text
[CRAC] beforeCheckpoint
~~~

After a successful checkpoint, the runtime writes the process state into the checkpoint directory. With a checkpoint flow triggered by jcmd, the original process usually exits once the checkpoint completes; confirm the command result and runtime logs of the distribution in use.

Do not copy or restore the image while the checkpoint command is still running. Wait for the operation to finish and confirm the runtime reports success.

### Checking the Process and Image

You can check whether the JVM is still running:

~~~bash
jcmd -l
~~~

Check the image directory:

~~~bash
du -sh /tmp/crac-minimal-checkpoint
find /tmp/crac-minimal-checkpoint -maxdepth 2 -type f
~~~

The file structure inside the checkpoint directory is a runtime implementation detail. Do not rename, delete, or modify files inside for experimentation unless guided by your distribution.

## 9. Restoring from the Checkpoint Image

After a successful checkpoint, launch restore using the same compatible CRaC JDK:

~~~bash
java \
  -XX:CRaCRestoreFrom=/tmp/crac-minimal-checkpoint
~~~

CRaCRestoreFrom instructs the runtime to restore the process from the created image. The runtime uses the command and process state saved in the checkpoint; exact invocation details may depend on the distribution.

Expected output in the restored process:

~~~text
[CRAC] afterRestore
[APP] tick=5
[APP] tick=6
[APP] tick=7
~~~

The exact tick number depends on when you created the checkpoint. What to observe is that the counter continues from the saved value. The program does not re-execute main() from the beginning like a normal startup; the process is restored from the checkpoint state.

If afterRestore() does not appear, inspect runtime logs and restore errors. Do not treat the java command merely starting as proof that restore succeeded.

## 10. Understanding Callback Order in the Exercise

In the example, the observed order is:

~~~text
Launch JVM
    |
    v
Register DemoResource
    |
    v
Tick loop runs
    |
    v
jcmd requests checkpoint
    |
    v
DemoResource.beforeCheckpoint()
    |
    v
Runtime creates checkpoint image
    |
    v
Launch restore
    |
    v
DemoResource.afterRestore()
    |
    v
Tick loop continues
~~~

beforeCheckpoint() is where resources are prepared before saving state. Real-world examples include stopping new requests, draining workers, flushing data, and closing sockets.

afterRestore() is where external resources are recreated or verified to still be usable. Real-world examples include fetching new credentials, creating database pools, opening file channels, and marking the application READY only after dependencies are operational.

Do not place all heavy work into constructors or assume @PostConstruct automatically re-runs after restore. Restore recovers process state; it does not create a new ApplicationContext by default.

## 11. Further Experiment: Closing and Reopening a File

After the basic exercise succeeds, you can extend the program to manage a file with Resource. The example below illustrates closing a FileChannel before checkpoint and reopening it after restore.

~~~java
package com.example.cracdemo;

import java.io.IOException;
import java.nio.channels.FileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class FileResource implements Resource {
    private final Path path;
    private FileChannel channel;

    public FileResource(Path path) throws IOException {
        this.path = path.toAbsolutePath().normalize();
        openChannel();
        Core.getGlobalContext().register(this);
    }

    private void openChannel() throws IOException {
        channel = FileChannel.open(
            path,
            StandardOpenOption.CREATE,
            StandardOpenOption.READ,
            StandardOpenOption.WRITE
        );
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        if (channel != null && channel.isOpen()) {
            channel.force(true);
            channel.close();
            channel = null;
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws Exception {
        openChannel();
    }

    public synchronized FileChannel channel() {
        if (channel == null || !channel.isOpen()) {
            throw new IllegalStateException("File channel is not open");
        }
        return channel;
    }
}
~~~

To use this class, create the file in a mounted data directory and pass the path to the constructor. Ensure that directory exists and has write permissions before launching.

This example only illustrates the lifecycle. Real applications need to flush writers before checkpoint, save committed offsets, verify file identity after restore, and handle errors if the file was replaced or truncated. If the checkpoint is aborted after the channel closed, the original process also needs to reopen the channel; afterRestore() is not a rollback callback for a failed checkpoint.

Do not open a file in the example and assume every filesystem, descriptor, or file lock is supported identically by CRaC. Test with the exact deployment filesystem and runtime.

## 12. Testing Checkpoint from Inside the Program

The CRaC API also provides Core.checkpointRestore() for the application to proactively request a checkpoint and restore. This differs from sending the jcmd command from an external terminal.

Call skeleton:

~~~java
try {
    Core.checkpointRestore();

    // The process has passed through checkpoint and restore successfully.
    System.out.println("[APP] checkpointRestore returned after restore");

} catch (org.crac.CheckpointException checkpointFailure) {
    // Checkpoint failed; the original process needs to recover resources
    // that beforeCheckpoint() closed or modified.
    throw checkpointFailure;

} catch (org.crac.RestoreException restoreFailure) {
    // Restore encountered an error; do not open traffic if resources are not ready.
    throw restoreFailure;
}
~~~

When using this API, the application can handle CheckpointException in the calling thread and recover resources of the original process. If the checkpoint is triggered via external jcmd, the application thread has no catch block wrapping that call.

Do not call Core.checkpointRestore() inside the per-second tick loop. Trigger it once under clear test conditions, because this operation alters the execution flow of the entire process.

## 13. Comparing with Normal JVM Startup

To see the difference, run the program without checkpoint options:

~~~bash
java \
  -cp "target/classes:target/dependency/*" \
  com.example.cracdemo.Main
~~~

This run starts counter from 0 and creates no checkpoint image. On a regular JDK, the CRaC API may allow compiling or running some application logic, but that does not prove the runtime has checkpoint/restore capability. Perform the checkpoint exercise only with a supported CRaC JDK.

When comparing performance, measure up to the same milestone, such as when the application is truly READY. Do not compare JVM resume time against cold startup time that includes opening database connections and warm-up.

## 14. Troubleshooting Common Errors

### JVM Does Not Recognize CRaC Options

Symptom: JVM reports unrecognized VM option or unsupported option.

Common cause: using a JDK without CRaC or PATH pointing to the wrong JDK.

Resolution:

- Check java -version.
- Use the absolute path to the CRaC JDK.
- Check that java, javac, and jcmd belong to the same distribution.
- Read the vendor's documentation on checkpoint/restore flags.

### jcmd Cannot Find Process

Symptom: jcmd -l does not list the PID or the attach command fails.

Check:

- Is the PID correct?
- Is the JVM still running?
- Does jcmd belong to the same JDK?
- Does the user running jcmd have permission to attach to the process?
- Does the JVM have Attach Listener disabled or attach restricted?

### Checkpoint Fails Due to Environment

Causes may include CRIU, kernel, permissions, container capabilities, mounts, or unsupported open resources.

Resolution:

- Read the full exception and runtime logs.
- Check the requirements of the CRaC JDK distribution.
- Try a minimal program without sockets or native resources.
- Verify the checkpoint directory and filesystem.
- Do not grant broad privileged permissions to the container just to mask errors; identify the exact capability required by the runtime.

### Restore Cannot Find Image

Check the CRaCRestoreFrom path, read permissions, and whether the checkpoint completed. Use an absolute path to avoid working directory confusion.

### Restore Fails Due to Different Runtime

Create and restore images with compatible JDK/CRaC versions. Do not assume images can be moved freely across vendors, builds, CPU architectures, or kernel environments.

### afterRestore() Does Not Run

If the runtime could not restore the process far enough to execute Java code, application callbacks cannot run. Inspect runtime logs before concluding a callback was skipped.

### Reopening Resource Fails

If a database, file, or client fails to open, keep the application in a not-ready state. Check mounts, permissions, DNS, networking, credentials, and dependencies before opening the request gate.

## 15. Practicing in Containers or Windows Environments

The command examples in this guide use Bash on Linux. CRaC typically relies on Linux checkpoint/restore features and CRIU; specific support depends on the JDK distribution, kernel, and container runtime.

If your development machine runs Windows:

- Do not assume java -XX:CRaCCheckpointTo=... works in PowerShell with a regular Windows JDK.
- Use a Linux VM or a Linux environment supported by the CRaC vendor.
- Use WSL2 only when the kernel, CRIU, permissions, and JDK distribution truly meet the requirements.
- If running in a container, check mounts, namespaces, capabilities, and required permissions per runtime documentation.
- Keep checkpoint images on a suitable filesystem with sufficient free space.

Do not copy a checkpoint image from Linux to another environment and assume it will restore. The image depends on the runtime and system state below Java bytecode level.

## 16. Cleaning Up the Environment After Practice

Once restore is complete and the program has stopped, you can delete the test checkpoint directory:

~~~bash
rm -rf -- /tmp/crac-minimal-checkpoint
~~~

Run the command above only after confirming the exact path dedicated to the exercise and that no restore operation is still using the image. Do not use broad wildcards like /tmp/* to clean up checkpoints.

If you want to keep it for repeated practice, save the image along with metadata about the JDK, CRaC runtime, kernel, and architecture that created it. Do not treat a practice image as a production-deployable artifact.

## 17. Extended Exercises

Once the minimal program works, you can try:

1. Add a second Resource and log the callback execution order.
2. Add a FileChannel and verify data flushed before checkpoint.
3. Intentionally throw an error in beforeCheckpoint() and observe the checkpoint failure.
4. Intentionally throw an error in afterRestore() and keep the request gate closed.
5. Add an HTTP or database dependency in a test environment and recreate the client after restore.
6. Measure the time from invoking jcmd to the afterRestore() callback.
7. Separately measure the time to reopen each resource.
8. Compare cold startup with restore at the same READY milestone.
9. Try restoring in an environment with a different filesystem or permissions and record the errors.
10. Create a new checkpoint after the application has already restored successfully.

Each exercise should use a separate checkpoint directory. Record the JDK build, runtime, kernel, and results for reproducibility.

## 18. Principles to Remember

- A supported CRaC JDK and OS environment are required; the API dependency alone does not provide checkpoint capability.
- Register a Resource using Core.getGlobalContext().register(...).
- beforeCheckpoint() prepares resources before the runtime saves state.
- afterRestore() reopens or verifies resources in the restored process.
- Use -XX:CRaCCheckpointTo to specify the checkpoint directory.
- Use jcmd <pid> JDK.checkpoint to request a checkpoint externally.
- Use -XX:CRaCRestoreFrom to restore the image.
- Wait for checkpoint completion before copying or restoring the image.
- Use a compatible JDK/CRaC and verify kernel, CRIU, mounts, and permissions.
- Observe application state and readiness; process existence alone does not prove it can serve requests.
- If callbacks closed resources and checkpoint fails, the original process needs a recovery path.
- If afterRestore() fails, keep the application not-ready.
- A checkpoint image is an environment-dependent artifact, not a portable JAR file.

This minimal exercise demonstrates that CRaC saves and restores the state of a running process. Once you have observed the pre-checkpoint callback, post-restore callback, and the counter continuing from its previous value, you have the foundation to expand to database pools, HTTP clients, file handles, and real application resources.
