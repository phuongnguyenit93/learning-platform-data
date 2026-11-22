# Collecting File Descriptor Creation Sites With jdk.crac.collect-fd-stacktraces

When creating a checkpoint, CRaC must bring the process to a state that can be safely restored. Part of that work is checking open file descriptors (FDs). A file descriptor is an OS-level handle used by a process to access files, sockets, pipes, and many other types of resources. If an application still holds an FD that cannot be carried across a checkpoint, the checkpoint operation may fail with CheckpointException.

An error usually indicates which FD remains open along with its path or resource type. However, that information does not answer the most important question: which piece of code opened this FD? The CRaC system property jdk.crac.collect-fd-stacktraces is designed to assist diagnostics when a file descriptor was created through a Java FileDescriptor. When enabled, the runtime records the stack trace at the time FileDescriptor is created and attaches that information to the exception when checkpoint detects an open FD.

This property helps trace back from a forgotten FD to the constructor or library that created it. It does not close the FD automatically, does not fix application lifecycle logic, and cannot capture stack traces for every FD opened directly from native code. This lesson explains how to enable the property, read the output, locate FD origins in Java, and switch to operating system tools when the opening source resides in native code.

## 1. What Is a File Descriptor?

On Unix/Linux, a file descriptor is a non-negative integer used by a process as an index into an entry in the process's file descriptor table. The kernel uses that entry to track an open file description or related resource.

An FD can represent many resource types:

- Regular files opened for reading or writing.
- TCP/UDP sockets.
- Pipes or FIFOs.
- Event descriptors and other kernel handles.
- Web server listening sockets.
- File locks or channels holding files.
- Certain resources created by native libraries.

In Java, classes such as FileInputStream, FileOutputStream, RandomAccessFile, and certain channels or streams can use FileDescriptor to represent the native-layer FD. Many other APIs can open resources directly via native code or system libraries without necessarily having a corresponding Java FileDescriptor object.

For example, when calling:

~~~java
FileInputStream input = new FileInputStream("/var/app/config.json");
~~~

the JVM opens the file in the OS and attaches the FD to the associated Java object. If input is not closed, the FD may still remain open when the application requests a checkpoint.

FDs 0, 1, and 2 normally correspond to standard input, standard output, and standard error. CRaC usually keeps these standard streams and certain FDs needed for the runtime or classpath. Other application FDs must be handled according to the rules of CRaC and the engine in use.

## 2. Why Can an Open FD Cause Checkpoint Failure?

A checkpoint saves process state for later restore. An open file descriptor can be tied to kernel state outside the process: a socket connected to a server, a locked file, a pipe connecting to another process, or a file mounted from a specific environment.

If that FD cannot be saved and restored properly, the process after restore could reference a resource that no longer exists or no longer belongs to the same environment. Therefore, CRaC requires the application to coordinate and close or handle unsuitable FDs before checkpoint.

An error typically looks like:

~~~text
Exception in thread "main" jdk.crac.CheckpointException
    at ... application code ...
    Suppressed: jdk.crac.impl.CheckpointOpenFileException:
        FileDescriptor 4 left open: /var/app/data/input.csv (regular)
        at java.base/java.io.FileDescriptor.beforeCheckpoint(...)
        at java.base/java.io.FileDescriptor$Resource.beforeCheckpoint(...)
        ...
~~~

This information tells you:

- CheckpointException is the aggregate error at the checkpoint level.
- CheckpointOpenFileException is a specific issue detected during resource checking.
- FileDescriptor 4 is the FD number inside the process at check time.
- The path indicates the open file if identifiable by the runtime.
- regular indicates the identified resource type.

CheckpointException can contain multiple suppressed exceptions, each describing an FD or resource failing checkpoint requirements. Therefore, read the entire stack trace rather than looking only at the first exception line.

The message shows the FD was open at checkpoint time; it does not by itself identify the code that created that FD. The jdk.crac.collect-fd-stacktraces property supplements origin information for FDs created via Java FileDescriptor.

## 3. What Does jdk.crac.collect-fd-stacktraces Do?

jdk.crac.collect-fd-stacktraces is a Java system property for CRaC. When enabled, the runtime records the stack trace at the time a Java FileDescriptor is created. If that FD remains open and is detected by CRaC at checkpoint time, the exception can include a cause pointing to the thread and call stack that created the descriptor.

For example, instead of seeing only:

~~~text
Suppressed: jdk.crac.impl.CheckpointOpenFileException:
    FileDescriptor 4 left open: /etc/passwd (regular)
~~~

the output can include the cause section:

~~~text
Caused by: java.lang.Exception:
    This file descriptor was created by main at epoch:1684328308663
    at java.base/java.io.FileDescriptor$Resource.<init>(...)
    at java.base/java.io.FileDescriptor.<init>(...)
    at java.base/java.io.FileInputStream.<init>(...)
    at java.base/java.io.FileReader.<init>(...)
    at ... application code ...
~~~

This stack trace helps identify the constructor or call path that opened the file. The thread name also shows which thread created the FD. The epoch timestamp is recorded when creating the descriptor; some FDs created very early during VM initialization might not format to a human-readable time.

Understand its scope accurately:

- The property records where a Java FileDescriptor was created.
- It does not record every time the FD is used.
- It does not automatically identify which component currently owns the FD if ownership was transferred.
- It does not automatically close FDs or change how checkpoint handles FDs.
- It does not guarantee a stack trace for FDs opened directly from native code without going through Java FileDescriptor.
- It is a diagnostic tool; exact support and property names must be confirmed on your exact CRaC JDK distribution.

## 4. Enabling the Property at JVM Startup

Set the property with the -D option directly on the Java launch command:

~~~bash
java \
  -Djdk.crac.collect-fd-stacktraces=true \
  -XX:CRaCCheckpointTo=./checkpoint \
  -jar app.jar
~~~

In this example:

- -Djdk.crac.collect-fd-stacktraces=true enables stack trace collection.
- -XX:CRaCCheckpointTo specifies where to store the checkpoint per runtime support.
- -jar app.jar launches the application.

If the application invokes Core.checkpointRestore() itself, the property still needs to be set when the JVM starts:

~~~bash
java -Djdk.crac.collect-fd-stacktraces=true -jar app.jar
~~~

Do not wait until checkpoint begins to call System.setProperty(). The stack trace must be recorded when the FD is created. If an FD was already open before the property was enabled, the runtime cannot reliably reconstruct the call stack that created that FD.

The property can be set via the JAVA_TOOL_OPTIONS environment variable in diagnostic environments:

~~~bash
export JAVA_TOOL_OPTIONS="-Djdk.crac.collect-fd-stacktraces=true"
java -XX:CRaCCheckpointTo=./checkpoint -jar app.jar
~~~

Ensure the environment variable applies only to the exact process under investigation. When running in a container, you can pass the JVM option through the container entrypoint configuration or JAVA_TOOL_OPTIONS.

## 5. Default Property Value and JDK Compatibility

jdk.crac.collect-fd-stacktraces is a CRaC-implementation property, not a standard Java SE property. Do not assume every JDK vendor or every CRaC build supports it identically.

Azul's CRaC documentation lists this property among the system properties for Community Availability builds, used during the checkpoint phase, with a default value of false for the listed builds. Check the documentation for the exact vendor, JDK version, and build being deployed before relying on it.

Several notes:

- If the property is unsupported by the runtime, passing -D may merely set an ordinary system property without enabling diagnostic tracking.
- System.getProperty() returning true proves only that the property was set in Java system properties, not that the runtime used it.
- Different builds may exhibit different behaviors or output formats.
- Do not depend on internal classes such as jdk.crac.impl.CheckpointOpenFileException in application code.
- Use the exception stack trace for diagnostics, not internal implementation classes as stable APIs.

Inspect java.vendor, java.version, java.vm.name, and java.home to record the runtime. Then cross-check with the vendor's CRaC documentation.

## 6. Why Must It Be Enabled From the Start Instead of Right Before Checkpoint?

The stack trace is captured when a Java FileDescriptor is created. Creation time typically lies in the constructor or a native call invoked by the constructor. For example:

1. The application creates a FileReader.
2. FileReader creates a FileInputStream or related object.
3. FileDescriptor is initialized and bound to an OS FD.
4. The runtime records the stack trace if collection mode is enabled.
5. Later, the application forgets to close the reader.
6. At checkpoint, CRaC detects the open FD and can attach the recorded stack trace.

If you enable the property only right before step 6, FDs created in steps 1–3 already exist without origin stack traces. That is why it must be enabled from JVM startup in the run used to reproduce the issue.

This property can increase FileDescriptor creation overhead because the runtime must capture and retain stack information. Enable it only during investigation or intentional test runs. Once the leak source is found and the lifecycle is fixed, run again with normal production configuration.

## 7. Reading the Stack Trace to Locate FD-Creation Code

When checkpoint fails, look for the suppressed exception containing FileDescriptor left open. Then read the Caused by section beneath that exception.

A stack trace may include JDK classes before reaching application code:

~~~text
Caused by: java.lang.Exception:
    This file descriptor was created by main at epoch:...
    at java.base/java.io.FileDescriptor$Resource.<init>(...)
    at java.base/java.io.FileDescriptor.<init>(...)
    at java.base/java.io.FileInputStream.<init>(...)
    at java.base/java.io.FileReader.<init>(...)
    at com.example.config.ConfigLoader.load(ConfigLoader.java:42)
    at com.example.Application.start(Application.java:27)
~~~

How to read it:

1. Frames belonging to java.base are usually the JDK implementation creating the FD.
2. Find the first frame belonging to an application or third-party library package.
3. Open that exact source line if source code or debug symbols are available.
4. Identify which stream/channel object is created at that location.
5. Trace where the object is closed and inspect all exception branches.
6. If the object is long-lived, determine its lifecycle owner and how to close it before checkpoint.

In the example above, ConfigLoader.load() at line 42 is the starting point for investigation. That line is not necessarily where the FD was forgotten; it is where the descriptor was created. Inspect the entire lifecycle of the stream created there.

If the stack contains only JDK frames, the descriptor may have been created during runtime or library initialization. Combine the thread name, timestamp, path, and startup logs to narrow it down.

## 8. Error Example: Opening a File Without Closing It

The following code creates an FD without guaranteeing closure:

~~~java
public final class ConfigLoader {
    public Properties load(Path path) throws IOException {
        FileInputStream input =
                new FileInputStream(path.toFile());

        Properties properties = new Properties();
        properties.load(input);
        return properties;
    }
}
~~~

If load() succeeds, input remains unclosed. If load() throws IOException, the FD can also be left open. When checkpoint occurs later, CRaC can detect the open FD.

With jdk.crac.collect-fd-stacktraces enabled, the stack trace can point straight to the FileInputStream constructor inside ConfigLoader.load(). Once you see this location, fix the code to close the stream on every branch.

## 9. Fixing With try-with-resources

For resources whose lifetime is scoped to a single operation, try-with-resources is the simplest fix:

~~~java
public final class ConfigLoader {
    public Properties load(Path path) throws IOException {
        Properties properties = new Properties();

        try (InputStream input = Files.newInputStream(path)) {
            properties.load(input);
        }

        return properties;
    }
}
~~~

Upon exiting the try block, Java calls close() even when an exception occurs. As a result, the FD is no longer held after the read operation finishes.

Apply the same principle to:

- FileInputStream and FileOutputStream.
- FileReader and FileWriter.
- RandomAccessFile.
- InputStream and OutputStream from libraries.
- JDBC Connection, Statement, and ResultSet according to ownership/transaction rules.
- Application-created sockets and channels.
- ZipFile, JarFile, and other closeable resources.

Do not close a resource that the current code does not own. If a method receives an InputStream from a caller, the API contract should specify who is responsible for closing the stream.

## 10. Long-Lived FDs Need Dedicated Lifecycles

Not every FD should be closed immediately after a single operation. A web server, message consumer, file watcher, or client may need to hold sockets/channels throughout its operating lifetime. For this kind of resource, try-with-resources does not apply if the resource must remain long-lived.

A clear owner and pre/post-checkpoint lifecycle are needed:

- Stop accepting new work.
- Drain in-flight requests or messages.
- Close sockets/channels/selectors per library API.
- Confirm FDs have been released.
- After restore, recreate resources or reconnect.
- Open ingress/workers only once new resources are ready.

Illustrative Resource example:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class FileWatcherCracResource implements Resource {
    private final FileWatcherLifecycle watcher;

    public FileWatcherCracResource(FileWatcherLifecycle watcher) {
        this.watcher = watcher;
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        watcher.stopWatching();
        watcher.awaitCallbacksToFinish();
        watcher.closeWatchService();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        watcher.recreateWatchService();
        watcher.startWatching();
    }

    public interface FileWatcherLifecycle {
        void stopWatching() throws Exception;
        void awaitCallbacksToFinish() throws Exception;
        void closeWatchService() throws Exception;
        void recreateWatchService() throws Exception;
        void startWatching() throws Exception;
    }
}
~~~

FileWatcherLifecycle is an illustrative application-defined interface, not a CRaC or JDK API. For real libraries, use the supported lifecycle API and check whether the library already provides CRaC integration. Do not register an extra Resource to close an FD already managed by another integration.

## 11. An FD Can Be Handed Off Between Objects

The property's stack trace shows where the FileDescriptor was created. It is not proof that the object creating the FD is still the owner at checkpoint time.

For example:

1. A factory creates a FileInputStream.
2. The factory hands the stream off to another component.
3. The receiving component forgets to close it.
4. The factory finishes and no longer retains a reference.
5. Checkpoint detects the FD is still open.

The stack trace still points to the factory, yet the lifecycle bug resides in the component receiving the stream. Therefore, after locating the FD creation site, follow the ownership flow rather than editing only the constructor line.

API design should clarify:

- Who creates the resource?
- Who owns the resource once returned?
- Who must call close()?
- Is the resource shared across multiple components?
- Can it be closed while another thread is using it?
- Who coordinates closing before checkpoint and reopening after restore?

Abstractions such as AutoCloseable, try-with-resources, and an explicit lifecycle manager help reduce ambiguous ownership.

## 12. When the Property Does Not Provide a Stack Trace

If a checkpoint exception reports an open FD without a Caused by section pointing to the creation site, several possibilities exist:

- The property was not enabled when the FD was created.
- The JDK build does not support the property.
- The FD was created before the runtime could collect stack traces.
- The FD was opened from native code without going through Java FileDescriptor.
- A library or native component created the FD along a path without a corresponding Java creation stack.

Do not conclude the runtime failed to detect the FD. The exception can still report the descriptor number, type, and path even without a source stack trace.

Check in order:

1. Confirm the property is on the JVM command line when the process starts.
2. Confirm the exact JDK vendor, version, and build.
3. Restart the application with the property enabled from the start.
4. Reproduce the exact workload creating the FD.
5. Request a checkpoint and inspect all suppressed exceptions.
6. If a stack trace is still absent, investigate whether the FD originates from native code.

Do not call System.setProperty() after the application has started as a substitute for the JVM startup option.

## 13. Distinguishing Java-Opened FDs From Native-Opened FDs

CRaC documentation distinguishes FDs created through Java FileDescriptor from cases where native code opens an FD directly.

### FDs via Java FileDescriptor

An exception typically takes the form:

~~~text
Suppressed: jdk.crac.impl.CheckpointOpenFileException:
    FileDescriptor 4 left open: /etc/passwd (regular)
Caused by: java.lang.Exception:
    This file descriptor was created by main at epoch:...
    at java.base/java.io.FileDescriptor...
    at java.base/java.io.FileInputStream...
    at ... application code ...
~~~

In this case, jdk.crac.collect-fd-stacktraces can reveal the Java call path that created the descriptor.

### FDs from native code

An exception may take the form:

~~~text
Suppressed: jdk.crac.impl.CheckpointOpenResourceException:
    FD fd=4 type=fifo path=pipe:[8953321]
~~~

The runtime still detects the FD, yet there is no Java FileDescriptor creation stack. You must investigate the syscall creating the descriptor in native code.

Commonly involved syscalls include open/openat, socket/socketpair, pipe/pipe2, dup/dup2, accept/accept4, and similar APIs. Not every FD comes from opening a file; a pipe or socket is also an FD.

## 14. Using strace When the FD Origin Lies in Native Code

On Linux, strace can record syscalls for a process and its threads. The -f option follows forks/threads, while -o writes output to a file:

~~~bash
strace -f -o /tmp/crac-strace.log java -jar app.jar
~~~

To focus on FD-creating syscalls, filter syscalls and request native stack traces if your strace build supports it:

~~~bash
strace -f -o /tmp/crac-open-fd.log \
  -e trace=openat,open,dup,dup2,pipe2,socket,socketpair,accept,accept4 \
  -k java -jar app.jar
~~~

Syscall filter syntax and stack-printing support depend on strace version. CRaC documentation also shows filtering a specific syscall such as pipe2:

~~~bash
strace -f -o /tmp/crac-pipe.log -e pipe2 -k java -jar app.jar
~~~

In the log, search for the FD number matching the checkpoint error. For instance, if the exception reports fd=4 and the log shows:

~~~text
1204483 pipe2([4, 5], 0) = 0
~~~

then the pipe2 syscall created the FD pair 4 and 5. Read subsequent lines to see where they are configured, duplicated, or closed.

If strace prints native stacks, they may point to libraries such as libnio or a third-party library. If binaries have symbols stripped, stacks may show only addresses. Debug symbols or symbol-enabled builds are then required to map addresses to functions.

Do not run strace as a permanent production solution. Syscall tracing adds significant overhead and logs can grow huge. Use it in test environments or controlled single reproductions.

## 15. Step-by-Step Investigation Workflow

A practical workflow can proceed as follows.

### Step 1: Reproduce the Initial Failure

Run the application with the exact workload and checkpoint configuration causing the error. Save full stdout, stderr, and checkpoint logs. Record the FD number, path, or resource type from suppressed exceptions.

### Step 2: Enable Stack Trace Collection

Restart the JVM with:

~~~bash
-Djdk.crac.collect-fd-stacktraces=true
~~~

Ensure the property is present from process startup, before the workload creates the FDs under investigation.

### Step 3: Reproduce the Same Workload

Re-run the same startup flow or requests. Do not change multiple factors simultaneously, as that makes comparing results difficult. When checkpoint fails, save the full stack trace.

### Step 4: Locate the Suppressed Exception

Search for FileDescriptor left open or CheckpointOpenFileException. Read the Caused by section to find the thread, timestamp, and call path.

### Step 5: Identify Owner and Lifecycle

From application or library frames, locate where the resource is created, transferred, used, and closed. Check exception, timeout, cancellation, and shutdown branches.

### Step 6: Fix the Lifecycle

For short-lived resources, use try-with-resources or close in finally. For long-lived resources, add pre-checkpoint lifecycle handling and post-restore recovery using supported APIs.

### Step 7: If No Java Stack Exists, Switch to Native Tracing

Use strace to record FD-creating syscalls. Filter by FD number and relevant syscalls, then map back to the library or native function.

### Step 8: Re-run Checkpointing

After fixing, re-run the workload and checkpoint. A successful checkpoint is strong evidence, yet restore and post-restore application functionality must still be tested.

## 16. Example Catching and Printing CheckpointException

If an application invokes checkpoint directly, log the full exception so suppressed exceptions are not lost:

~~~java
import org.crac.Core;
import org.crac.CheckpointException;

public final class CheckpointRunner {
    public static void checkpoint() throws CheckpointException {
        try {
            Core.checkpointRestore();
        } catch (CheckpointException exception) {
            exception.printStackTrace(System.err);

            for (Throwable suppressed : exception.getSuppressed()) {
                System.err.println("Suppressed problem:");
                suppressed.printStackTrace(System.err);
            }

            throw exception;
        }
    }
}
~~~

Package names and method signatures should match the CRaC API used by the project. The example illustrates preserving the exception and printing suppressed errors; do not depend on implementation classes in the internal jdk.crac.impl package.

In many cases, the runtime or framework already prints exceptions to stderr. It is critical that log collectors preserve multiline stack traces, including Suppressed and Caused by sections. If the system keeps only the first line, FD origin details can be lost.

## 17. Do Not Confuse This Property With File Descriptor Policies

CRaC can provide policy mechanisms to handle certain file descriptors or files permitted to exist under specific rules. Those policies serve a different purpose than jdk.crac.collect-fd-stacktraces.

- collect-fd-stacktraces: records Java FileDescriptor creation stack traces to assist in finding bug origins.
- resource policies: describe how CRaC handles certain resources/FDs according to supported policies.
- CRaCAllowedOpenFilePrefixes: in certain implementations, used for prefixes of files opened from native code within documented scopes.

Do not use policies to mask errors before knowing which component owns the FD. If a file descriptor must be retained or handled specially, understand its impact on checkpoint/restore and confirm policy support in the exact JDK build.

For application FDs that can be closed normally, fixing the lifecycle is usually cleaner and safer than adding exceptions to a policy. The stack trace collection property helps locate the source; it is not a way to allow FDs to stay open.

## 18. Limitations and Caveats

When enabling stack trace collection, keep in mind:

- **Overhead at FD creation time:** The runtime must capture and retain stack information. This can increase resource-opening latency and memory usage.
- **Not a general-purpose profiler:** It does not log every read/write operation, nor does it measure how long an FD is used.
- **Does not directly show where close was forgotten:** It shows where the descriptor was created; ownership must be traced to find the missing lifecycle handling.
- **Does not cover native FDs:** FDs opened directly from native code require tools such as strace or native debuggers.
- **CRaC-implementation dependent:** The property is not a standard Java SE API; verify for your exact vendor/build.
- **Must be enabled before FD creation:** Enabling after the application has started cannot reconstruct historical stacks.
- **Output can contain internal details:** Paths, package names, and stack traces can reveal application structure; protect logs per policy.

Enable only during investigation runs or intentional test runs, then remove the property when no longer needed.

## 19. Common Mistakes

**Enabling the property after FDs are already open.** The runtime has no historical stack trace to attach. Restart the JVM with the property from the start.

**Reading only the outermost exception.** FD issues usually reside inside suppressed exceptions. Print and retain the entire stack trace.

**Assuming the property closes FDs automatically.** The property only collects origin info. The application must still close or manage resources via the proper lifecycle.

**Searching only by FD number without checking path and call stack.** FD numbers can be recycled after closure. Inspect the full descriptor type, path, thread, and creation stack.

**Fixing the resource creation line without checking ownership.** The resource may be transferred to another component. Identify who is responsible for closing before changing code.

**Using the property to diagnose native FDs.** Native code might not create a Java FileDescriptor. Use strace or native tracing tools.

**Swallowing CheckpointException.** Logs retain only a generic message and lose suppressed details. Preserve the exception or print the full stack trace.

**Adding FDs to an allowlist too early.** This can mask lifecycle bugs and tie checkpoints to external resources. Use policies only after understanding and verifying restore behavior.

**Keeping the property in production without assessing overhead.** Collecting stacks on every FD creation can increase overhead. Disable after investigation.

## 20. Checklist for Diagnosing FDs With CRaC

- [ ] Have you recorded the JDK vendor, version, build, and CRaC engine?
- [ ] Have CheckpointException and all suppressed exceptions been saved?
- [ ] Have you identified the FD number, path, and resource type?
- [ ] Was jdk.crac.collect-fd-stacktraces=true passed at JVM startup?
- [ ] Does the running runtime support this property?
- [ ] Have you reproduced the exact same workload after enabling the property?
- [ ] Have you inspected the Caused by section to locate the Java creation stack?
- [ ] Have you identified the owner of the stream/channel/socket or corresponding resource?
- [ ] Have you verified all exception, cancellation, and shutdown branches close the resource?
- [ ] Do short-lived resources use try-with-resources or an appropriate finally block?
- [ ] Do long-lived resources have a beforeCheckpoint/afterRestore lifecycle?
- [ ] If no Java stack exists, have you evaluated whether the FD was opened from native code?
- [ ] Have you used strace or native tracing to find FD-creating syscalls when needed?
- [ ] Have you avoided depending on internal jdk.crac.impl classes in application code?
- [ ] Have you re-run checkpoint and restore after fixing the lifecycle?
- [ ] Have you disabled the diagnostic property once investigation finished?

## Conclusion

jdk.crac.collect-fd-stacktraces helps locate the origin of open Java FileDescriptors that cause checkpoint failures. By enabling the property at JVM startup, CRaC can capture stack traces when descriptors are created and attach thread/call-path details to suppressed exceptions when open FDs are detected.

This information lets you trace from an FD number and path to the constructor or library that opened the resource. You must then inspect ownership and fix the lifecycle: close short-lived resources with try-with-resources, or stop and recover long-lived resources through the CRaC lifecycle. If an FD is created directly from native code and lacks a Java creation stack, use strace to find syscalls such as openat, pipe2, dup, or socket. The property is a diagnostic tool with a specific scope; it does not resolve open FDs on its own and does not replace checkpoint/restore testing after fixes.

## References

- Azul CRaC, CRaC Command-Line Options and System Properties: https://docs.azul.com/crac/usage/vm-options
- Azul CRaC, Debugging CRaC Failures — File Descriptors in Java Code and File Descriptors in Native Code: https://docs.azul.com/crac/usage/debugging.html
