# Log Paths in Java File Logging

## Objectives

A **log path** is the location that a file handler or file appender uses to create and write log files. In Java, configuring the path correctly is essential for an application to write logs reliably when running from an IDE, terminal, Windows Service, Linux server, Docker, or CI. A path that is valid on a developer's machine can be completely wrong when deployed.

This lesson belongs to the **File logging** group of **Java Core Logging**, focusing on **log paths**: how they are formed, configured, handled with Java 17, common errors, and security/operational factors. After this lesson, you will be able to:

- Distinguish between a **relative path** and an **absolute path**; identify the role of the **working directory**.
- Use **Path**, **Files**, and **FileHandler** to create directories, write files, close handlers, and verify the storage location.
- Distinguish the **active log file** path from **rotation/archive** patterns, as well as filename patterns from log content patterns.
- Configure paths with JUL, Logback, and recognize the corresponding characteristics in Log4j 2.
- Diagnose why files appear in the wrong directory, fail to be created, lack write permissions, get overwritten, or disappear after redeploy.
- Recognize path traversal, symlinks, access permissions, retention, and limitations when using file logging in containers.

## 1. What is a log path?

Example:

~~~text
my-service/
└── logs/
    └── application.log
~~~

**logs** is the containing directory; **application.log** is the filename; **logs/application.log** is the file path. The file content might be:

~~~text
INFO event=request.completed requestId=req-12 status=200
~~~

This is a simple text example. A **logging event** can contain a level, logger, timestamp, message, Throwable, and metadata. **The path is not a required property of the message**: the Logger emits the event, while the **Handler/Appender** decides where to output it. A system can simultaneously output logs to both the console and a file.

~~~mermaid
flowchart LR
    A["Java Logger"] --> B["Level / Filter"]
    B --> C["FileHandler or FileAppender"]
    C --> D["Filesystem path"]
    D --> E["Log file"]
~~~

If no file handler/appender is configured, calling **logger.info(...)** does not automatically create a file just because the logger has a name. If a record is filtered out by level/filter, even a properly configured file path does not guarantee any log lines will be written.

**A good path** must be explainable: which machine/container it resides on, whether it is absolute or relative, whether the process has permission to open the file, whether the file persists across restarts, and whether the collector can read it.

## 2. Relative path and absolute path

A **relative path** is resolved against a base directory, usually the working directory of the Java process:

~~~text
logs/app.log
target/logs/app.log
../logs/app.log
~~~

An **absolute path** specifies a location from the filesystem root or volume:

~~~text
/var/log/myapp/app.log
/srv/myapp/logs/app.log
C:\apps\myapp\logs\app.log
D:\service-logs\app.log
~~~

The examples above belong to different operating systems; you cannot assume all of them exist or have the same representation on a single machine.

| Property | Relative | Absolute |
| --- | --- | --- |
| Example | logs/app.log | /var/log/myapp/app.log |
| Depends on working directory | Yes | Not in the way a relative path does |
| Easy to use in local projects | Usually yes | Requires machine-specific configuration |
| May write to the wrong place when changing how it runs | Common | Less common, though mount/volume can still be wrong |
| Portable across Windows/Linux | Possible if using Path properly | Usually environment-dependent |
| Suitable for long-term deployment | Requires controlling the working directory | Requires proper permissions and mounts |

If an application runs from **/srv/myapp**, the relative path **logs/app.log** usually resolves to **/srv/myapp/logs/app.log**. If a task runner runs from **/opt/runner**, the same string may resolve to **/opt/runner/logs/app.log**. **A relative path is not relative to the directory containing the JAR or source files by default.**

An absolute path is more explicit, but it does not solve access permissions by itself. For example, a process running as a user without write permission to /var/log/myapp will fail even though the path is completely valid.

## 3. Working directory: why does it work in the IDE but fail on the server?

When calling Java:

~~~java
// Illustration, placed inside a Java method.
java.nio.file.Path file =
        java.nio.file.Path.of("logs", "app.log");
System.out.println(file.toAbsolutePath().normalize());
~~~

The result depends on the **working directory of the running JVM process**. You can inspect it with:

~~~java
// Illustration.
System.out.println(System.getProperty("user.dir"));
System.out.println(java.nio.file.Path.of("")
        .toAbsolutePath().normalize());
~~~

These two values usually help diagnose where the JVM was started. **user.dir** typically reflects the working directory when the JVM started. Do not use **System.setProperty("user.dir", "...")** as a reliable solution to change the working directory mid-run: how libraries and the filesystem use the property versus the actual current directory can differ.

Factors that can determine the working directory:

1. The terminal directory when running the **java** command.
2. The **Working directory** setting in an IDE or test runner.
3. WorkingDirectory in Linux systemd or a Windows service wrapper.
4. **WORKDIR** in a Dockerfile or a container's workingDir.
5. The agent directory of a CI job, Maven/Gradle task, or startup script.
6. A process manager or launcher that spawns a child JVM with its own working directory.

**The sensible fix** is to determine the actual location and configure the path explicitly, or pin the working directory in the deployment environment. Do not rely on the assumption that files will sit next to the JAR.

## 4. Using java.nio.file.Path instead of string concatenation

In Java 17, **Path** and **Files** provide APIs for managing paths according to the filesystem:

| API | Purpose | Notes |
| --- | --- | --- |
| **Path.of("logs", "app.log")** | Represents a path | Does not create the file automatically |
| **path.isAbsolute()** | Checks whether the path is absolute | Filesystem-dependent |
| **path.toAbsolutePath()** | Converts to an absolute representation | Works even if the file does not exist yet |
| **path.normalize()** | Simplifies **.** and **..** segments syntactically | Does not check symlinks or permissions |
| **path.resolve("app.log")** | Appends a filename to a directory | If the resolved part is absolute, it may replace the base |
| **path.getParent()** | Gets the parent directory path | May return null |
| **Files.createDirectories(dir)** | Creates the directory along with any needed parent directories | May throw IOException |
| **Files.exists(path)** | Checks for existence | Does not prove write permission |
| **Files.isWritable(path)** | Checks write permission | May become stale afterward due to a race |
| **path.toRealPath()** | Gets the real path of an existing target | May follow symlinks depending on options |

Example:

~~~java
// Illustration, used inside a method declaring throws IOException.
java.nio.file.Path logDirectory =
        java.nio.file.Path.of("target", "logs")
                .toAbsolutePath().normalize();
java.nio.file.Files.createDirectories(logDirectory);
java.nio.file.Path logFile = logDirectory.resolve("app.log");
~~~

**Path.of** only creates a Path object. **Files.createDirectories** creates the directory, not the app.log file itself. **FileHandler/FileAppender** or a file output API is what opens or creates the file when writing.

For fixed paths determined by code, using **resolve** is better than string concatenation like **"target/" + name** because separators and path rules belong to the filesystem. If the path is user-supplied, additional security checks from section 12 are required.

## 5. Write permissions and parent directories

A path can be syntactically valid and still fail to write when:

- The parent directory does not exist and the backend does not create it automatically.
- The process lacks permission to create the directory/file.
- The mount is **read-only**, the disk is full, quota is exhausted, or file descriptors are limited.
- A path component points to a symlink or a file instead of a directory.
- Another process is locking or using the same file.
- The file is modified/deleted between checking and opening.
- The filesystem/network share is unavailable.
- A container mounts a different directory than the path in the config.

**Creating the directory beforehand** is an appropriate solution when the application owns that directory:

~~~java
// Illustration.
java.nio.file.Path dir =
        java.nio.file.Path.of("target", "logs")
                .toAbsolutePath().normalize();
java.nio.file.Files.createDirectories(dir);
~~~

However, on production machines, a directory like **/var/log/myapp** may need to be created by deployment/system administrators with appropriate ownership. Do not run the application as root just to make the log path writable.

**Files.isWritable** does not guarantee that a subsequent file open operation will succeed, because permissions and the filesystem can change. Handle IOException or the logging backend's error reporting path when actually opening/writing.

**Read permissions matter too:** log files can contain business data. Grant least privilege, and do not put tokens/passwords into messages or filenames.

## 6. Java 17 example: building the path properly, writing logs, reading back

This standalone example uses the JDK's **java.util.logging.FileHandler**, with no Maven dependencies required. The program:
1. Reads the log directory from the **app.log.dir** property, defaulting to **target/logs**.
2. Computes the absolute path and creates the directory.
3. Resolves the filename **app.log**.
4. Writes two events and closes the Handler.
5. Reads back the UTF-8 file and prints the result to stdout.

Create the file **LogPathDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.logging.FileHandler;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class LogPathDemo {
    private static final Logger LOG =
            Logger.getLogger(LogPathDemo.class.getName());

    public static void main(String[] args) throws Exception {
        String setting = System.getProperty("app.log.dir", "target/logs");
        Path logDirectory = Path.of(setting).toAbsolutePath().normalize();
        Files.createDirectories(logDirectory);
        Path logFile = logDirectory.resolve("app.log");

        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        FileHandler handler = new FileHandler(logFile.toString(), false);
        handler.setLevel(Level.INFO);
        handler.setEncoding(StandardCharsets.UTF_8.name());
        handler.setFormatter(new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " | "
                        + formatMessage(record) + System.lineSeparator();
            }
        });
        LOG.addHandler(handler);

        try {
            LOG.info("event=job.started id=job-7");
            LOG.info("event=job.completed id=job-7 status=ok");
        } finally {
            LOG.removeHandler(handler);
            handler.close();
        }

        List<String> lines =
                Files.readAllLines(logFile, StandardCharsets.UTF_8);
        System.out.println("logDirAbsolute=" + logDirectory.isAbsolute());
        System.out.println("fileInConfiguredDir="
                + logFile.getParent().equals(logDirectory));
        System.out.println("recordCount=" + lines.size());
        for (String line : lines) {
            System.out.println(line);
        }
    }
}
~~~

### Run A: using the default directory

In the directory containing LogPathDemo.java:

~~~bash
javac LogPathDemo.java
java LogPathDemo
~~~

**Exact stdout when the file is written successfully:**

~~~text
logDirAbsolute=true
fileInConfiguredDir=true
recordCount=2
INFO | event=job.started id=job-7
INFO | event=job.completed id=job-7 status=ok
~~~

The file is created at **target/logs/app.log** relative to the current working directory, not by default where the Java libraries reside. The output does not print a specific absolute path so that the result is identical on Windows and Linux. The **program's console output** here is the result of reading the file after the handler has closed; the initial LOG.info calls wrote to the file.

### Run B: changing the log directory

~~~bash
java -Dapp.log.dir=target/custom-logs LogPathDemo
~~~

**Stdout remains identical to Run A**, but the file is written to **target/custom-logs/app.log**. The **-Dapp.log.dir=...** argument is a custom system property defined by this example, **not a special default configuration of JUL**.

On Windows/PowerShell, if the path contains spaces, wrap the entire argument in quotes:

~~~powershell
java "-Dapp.log.dir=C:\Work Logs\MyApp" LogPathDemo
~~~

An example of an absolute path on Linux:

~~~bash
java -Dapp.log.dir=/var/log/myapp LogPathDemo
~~~

The last command succeeds only if the application has permission to create/write the directory. Do not hardcode this path for every environment.

### Explanation

- **Path.of(setting).toAbsolutePath().normalize()** resolves the path and simplifies syntax; it does not handle all symlink risks.
- **Files.createDirectories** creates missing directories if permitted.
- **logDirectory.resolve("app.log")** separates directory configuration from the filename.
- **FileHandler(..., false)** opens the file with append=false so each run does not mix in old logs. For production where logs must be preserved, choose append/rotation intentionally.
- **setEncoding("UTF-8")** and a custom Formatter make the content and verification output clear; FileHandler defaults to XMLFormatter if unconfigured.
- **setUseParentHandlers(false)** prevents the same record from being forwarded to parent logger handlers; we attached FileHandler directly.
- **finally** closes the handler before reading the file; this releases the stream and file lock held by the Handler.
- **recordCount=2** is only the demo's result, not a guarantee of log delivery/durability in distributed systems.

The program above was compiled and tested with the JDK, using both default and custom paths; in both cases it created the file and read back the exact two records.

## 7. JUL's FileHandler: tokens in filename patterns

**java.util.logging.FileHandler** supports patterns for generating filenames and rotation. These tokens are **for filenames only**, not for record content formatters.

| Token | Meaning in FileHandler pattern |
| --- | --- |
| **%h** | Home directory of the user running the JVM |
| **%t** | System temporary directory |
| **%g** | Generation number of the file in rotation |
| **%u** | Unique number to resolve filename conflicts when needed |
| **%%** | Literal **%** character |

Example:

~~~java
// Illustration; the myapp subdirectory must be created beforehand with appropriate permissions.
java.util.logging.FileHandler handler =
        new java.util.logging.FileHandler(
                "%h/myapp/log-%u-%g.log",
                1024 * 1024,
                5,
                true);
~~~

Explanation: byte limit per file in the rotation mechanism, **5 generations**, append=true mode, and filename based on the home directory and tokens. The actual file may have suffixes for generation/unique numbers and file lock state; do not hardcode an assumption about a single exact filename.

**%h is not a token of standard Path.of.** It is processed internally by FileHandler in the **pattern string**. In an expression like **Path.of("%h", "app.log")**, Java NIO does not automatically expand %h to the home directory.

If using a pattern containing a directory like **%h/myapp**, ensure the myapp directory exists and has write permissions. **Do not assume FileHandler always creates all parent directories automatically.**

FileHandler may use lock files to coordinate file ownership. The **%u** token cannot replace a policy for managing multiple processes writing to the same file; when multiple instances write/rotate concurrently, review the architecture to avoid conflicts.

## 8. Configuring JUL with logging.properties

An example **logging.properties** file for another application using JUL with a myapp directory in the user's home:

~~~properties
.level = INFO
handlers = java.util.logging.FileHandler

java.util.logging.FileHandler.level = INFO
java.util.logging.FileHandler.pattern = %h/myapp/app-%u.%g.log
java.util.logging.FileHandler.limit = 1048576
java.util.logging.FileHandler.count = 3
java.util.logging.FileHandler.append = true
java.util.logging.FileHandler.formatter = java.util.logging.SimpleFormatter
~~~

Launch the compiled application with main class com.example.Main:

~~~bash
java -Djava.util.logging.config.file=logging.properties -cp out com.example.Main
~~~

This is an **illustrative command for an application configured with JUL**; it is not the command to run LogPathDemo from section 6, because that demo creates FileHandler in code. **java.util.logging.config.file** points to the JUL configuration file; the path to logging.properties itself can also be relative and affected by the working directory.

In properties:
- **FileHandler.pattern** selects the filename.
- **limit/count** configures basic rotation.
- **append** controls whether to append when opening the file.
- **formatter** formats the log content, not the path.
- **handlers** attaches the file handler in the root configuration.

Log levels and filters can still drop events before they reach the file. Do not conclude the path is wrong just because DEBUG/FINE lines are missing, especially when root or FileHandler only allows INFO and above.

## 9. Log paths in Logback

With **SLF4J + Logback**, the log path is usually in **logback.xml** and managed by **FileAppender** or **RollingFileAppender**, not JUL FileHandler.

Example **src/main/resources/logback.xml**:

~~~xml
<configuration>
  <appender name="FILE" class="ch.qos.logback.core.FileAppender">
    <file>logs/application.log</file>
    <append>true</append>
    <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
      <charset>UTF-8</charset>
      <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level %logger - %msg%n</pattern>
    </encoder>
  </appender>

  <root level="INFO">
    <appender-ref ref="FILE"/>
  </root>
</configuration>
~~~

**file** is the active file path. **logs/application.log** is a relative path, usually resolved from the JVM's working directory. **PatternLayoutEncoder** controls how messages are formatted; content patterns with **%d/%level/%msg** are different from filename patterns.

### Changing the directory per environment

Logback supports property substitution. Standalone configuration example:

~~~xml
<configuration>
  <appender name="FILE" class="ch.qos.logback.core.FileAppender">
    <file>${LOG_DIR:-logs}/application.log</file>
    <append>true</append>
    <encoder>
      <charset>UTF-8</charset>
      <pattern>%level | %msg%n</pattern>
    </encoder>
  </appender>
  <root level="INFO"><appender-ref ref="FILE"/></root>
</configuration>
~~~

The **${LOG_DIR:-logs}** syntax uses LOG_DIR if provided by configuration, or **logs** as a fallback according to Logback's property mechanism. The property source can be a system property, environment variable, or corresponding configuration scope. With a relative LOG_DIR, the file still depends on the working directory; with an absolute LOG_DIR, the process still needs write permissions and an existing mount.

**Do not copy Logback's substitution syntax into JUL properties or Log4j 2 and assume it behaves the same.** Each backend has its own mechanism.

### Active file vs. rotated filenames

RollingFileAppender typically has two path purposes:

~~~xml
<appender name="ROLLING" class="ch.qos.logback.core.rolling.RollingFileAppender">
  <file>logs/application.log</file>
  <rollingPolicy class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
    <fileNamePattern>logs/archive/application.%d{yyyy-MM-dd}.log</fileNamePattern>
    <maxHistory>7</maxHistory>
  </rollingPolicy>
  <encoder>
    <pattern>%level %msg%n</pattern>
  </encoder>
</appender>
~~~

This is a **fragment** that must be placed inside a configuration with an appropriate logger/root appender-ref. **file** specifies the active file being written to, while **fileNamePattern** determines the archive names during rotation. **%d** in fileNamePattern is the rolling policy's date token; **%d** in the encoder pattern is the timestamp of each log record. When changing the log directory, check **both the active file and the archive location**.

## 10. Paths when using Log4j 2 or frameworks

**Log4j 2** also has FileAppender/RollingFileAppender, but uses different configuration than Logback. Common attribute names are **fileName** for the active file and **filePattern** for archives in the RollingFile appender. Do not switch logging libraries while keeping all old XML files and expecting the output location to remain identical.

With **Spring Boot** or other frameworks, there are also framework-supported logging properties. Check the version, profile, config priority, and the backend actually in use. An SLF4J facade does not choose the output location itself; the provider/backend and final configuration files decide.

When an application has multiple configurations coexisting, verify **the effective configuration in the real JVM** before editing paths. For example, a logback.xml file in source might not be packaged onto the classpath if the build omits resources from the JAR.

## 11. Append, rotation, and retention

Choosing the right path is not enough if the file grows unboundedly or gets overwritten on every startup.

| Option | Effect | Risks/limitations |
| --- | --- | --- |
| **append=true** | Appends to the existing file | File grows over time; requires retention |
| **append=false** | Reopens without keeping old logs | Easy to overwrite logs that should be kept |
| Size-based rotation | Keeps the active file within a planned threshold | Must control archive count and total size |
| Date-based rotation | Splits archives by time | Must clarify timezone and cleanup schedule |
| File on persistent volume | Can survive restarts depending on storage config | Still needs backup/retention/permissions |
| File on temporary filesystem | Suitable for tests or short-lived caches | May be lost after job/redeploy |

Multiple processes sharing **logs/app.log** can lead to locks, interleaved content, or rotation conflicts. Do not assume every backend writes concurrently safely across all filesystems. Usually it is better to separate files per instance or use a shared collector via stdout/stderr.

Alongside filenames, you need **rules for who can read logs, how long to keep them, and which policy deletes them**. A path on a persistent volume without rotation can still fill up the disk and bring down the service.

## 12. Security: path traversal and symlinks

Do not let request input arbitrarily determine filenames or directories for a process writing with elevated privileges. Strings containing **..**, absolute paths, symlinks, or special tokens can redirect the target.

A **syntactic** check for a filename within a designated directory:

~~~java
// Illustration snippet: root is managed by the application, userFileName is a String.
java.nio.file.Path root =
        java.nio.file.Path.of("target", "trusted-logs")
                .toAbsolutePath().normalize();
java.nio.file.Path file =
        root.resolve(userFileName).normalize();

if (!file.startsWith(root) || file.equals(root)) {
    throw new IllegalArgumentException("Path outside log directory");
}
~~~

**Important:** This is **not a complete security measure**. Path-level normalize and startsWith do not prevent symlinks inside root from pointing outside, nor do they prevent a directory from being swapped between check and open (TOCTOU). For untrusted scenarios, use a simple filename allowlist, do not follow untrusted symlinks, handle filesystem/permissions safely, and apply appropriate business policies.

Additional risks:
- FileHandler has a pattern syntax containing **%**; do not pass raw untrusted input directly into patterns.
- Unusually long filenames or a large number of files can exhaust storage.
- Log paths or messages can leak usernames or internal directories; do not include secrets in paths.
- Overly permissive file permissions allow unauthorized users to read or modify logs.

**The simplest design:** admin/deployment decides the directory; the application chooses controlled fixed filenames; only necessary processes have read/write permissions.

## 13. Docker, Kubernetes, and CI

### Containers

In Docker or Kubernetes, a path like **/app/logs/app.log** is a **path inside the container's filesystem**. It does not automatically correspond to a file on the host and does not automatically persist when the container is replaced.

For normal operational logs, **stdout/stderr with the platform's collector** is usually easier to manage. If file logging is required:
1. Mount an appropriate volume at the configured log directory.
2. Check the container's UID/GID and write permissions.
3. Verify that the collector/sidecar reads the exact mounted path.
4. Configure rolling/retention and monitor disk usage.
5. Test restart, redeploy, and shutdown to understand what data is retained.
6. Do not grant root privileges arbitrarily just to create files.

Dockerfile **WORKDIR** or a container's workingDir can also cause relative paths to point to a different location than locally.

### CI/test runners

CI usually runs in a temporary workspace, so files like **target/logs/app.log** may disappear after the job. When test logs need to be kept, configure them to upload as CI artifacts or capture console output.

When tests run in parallel, avoid multiple tests opening the same file with append=false. You can create a separate temporary directory using **Files.createTempDirectory** and clean it up after the handler has closed.

Do not assume production paths exist in CI; pass the log directory via property/test configuration.

## 14. Diagnosing when the log file does not appear

An ordered checklist:

1. **Identify the backend**: JUL FileHandler, Logback FileAppender, or Log4j 2. The SLF4J API does not decide the file itself.
2. **Verify the loaded configuration**: logback.xml, logging.properties, profiles, JVM arguments, and override order.
3. **Check relative/absolute**: if relative, get the running JVM's working directory.
4. **Distinguish file and directory**: did the config accidentally specify target/logs instead of target/logs/app.log?
5. **Does the parent directory exist?** Does the backend create it or must deployment create it beforehand?
6. **Does the service user have permission to open the file?** Check mounts, filesystem, locks, and quotas.
7. **Does the logger have valid events?** Levels/filters may mean no records have been written to the file yet.
8. **Has the file rotated?** Look for the active file, generation files, archives, and retention.
9. **Are multiple processes writing to the same path?** Check for name/lock/rotation conflicts.
10. **Is the file in the container or on the host?** Are volume mounts and collectors configured?
11. **Does the file have a different encoding/format?** FileHandler may write XMLFormatter; do not open it and assume it is broken just because it is not single-line text.
12. **Has the Handler/Appender flushed or closed?** Async queues and buffers may not have finished yet.
13. **Is the centralized collector/backend lagging?** The file existing does not mean the data has been ingested/indexed.

| Symptom | Common cause | How to check |
| --- | --- | --- |
| File exists in IDE, missing in service | Different CWD | Print absolute path or inspect property at startup |
| Cannot create file | Missing parent/lack of permissions | Files.createDirectories when permitted, inspect IOException |
| File appears in unexpected path | Relative path or config override | Verify effective config and working directory |
| File overwritten after restart | append=false | Change append/rolling policy if history must be kept |
| Seeing app.0.log, app.1.log | FileHandler rotation | Check %g/count/limit |
| File disappears after deploy | Ephemeral container or retention | Check volume/collector/cleanup |
| No logs while program is running | Level/filter/provider | Check Logger, Handler/Appender, backend |
| Right file but hard to parse | Different formatter or encoding | Check SimpleFormatter/XMLFormatter, UTF-8 |
| File is locked | Another process or unclosed Handler | Check file ownership and lifecycle |

**Do not use chmod 777 or run the service with elevated privileges** as a default fix. Those measures can mask the root cause and introduce security risks.

## 15. Checklist for testing a file log path

Before deploying a new path, test:

- **Two different working directories**, verifying that relative paths change as expected.
- **An absolute path** granted permissions in an appropriate environment.
- **Non-existent directory**, checking whether it is created or reports a clear error.
- **No write permission**, verifying the application does not silently swallow errors.
- **Two restarts**, checking append/rotation/retention.
- **Filenames with Unicode**, using an appropriate charset and reading mechanism.
- **Multiple JVMs/processes**, verifying there are no unexpected overwrites/file locks.
- **Shutdown and AsyncAppender**, checking buffers/queues per the backend contract.
- **Container restart**, verifying mounts and that logs can be collected again.
- **Untrusted input**, testing names with ../, absolute paths, and symlinks in a test environment.
- **Nearly full disk**, observing quotas, rotation, and error reporting.
- **Collector**, verifying the source reads the right active path and archive policy.

Tests should use dummy data and test directories, without overwriting or overloading production files.

## 16. Self-check questions

**1. If you run the same JAR in two different working directories, does logs/app.log necessarily point to the same file?**  
No. Relative paths usually depend on the process working directory, not on the JAR name.

**2. Does Path.of("logs", "app.log") create the file automatically?**  
No. It only represents the path; an API must create/open the file. The parent directory must also exist or be created appropriately.

**3. Why does LogPathDemo use Files.createDirectories before FileHandler?**  
To create missing directories if permitted, reducing file open errors caused by missing parents.

**4. Does JUL FileHandler's %h work automatically in Path.of("%h", "app.log")?**  
No. %h is a token in FileHandler's pattern, not a general Path substitution.

**5. Do file and fileNamePattern in RollingFileAppender have the same role?**  
No. file is usually the active log file; fileNamePattern specifies archive names in the rotation policy.

**6. Does normalize() guarantee a path cannot escape root via a symlink?**  
No. normalize handles syntax; it does not eliminate all symlink or TOCTOU risks.

**7. Why might files in /app/logs be lost after a container redeploy?**  
Because the filesystem inside a container can be ephemeral without an appropriate volume or log collector.

**8. Why does append=false make demos easy to test but potentially dangerous in production?**  
Because demos need a clean file and predictable line counts; production usually needs to preserve data and manage rotation.

**9. Does Files.isWritable returning true guarantee FileHandler.open will succeed?**  
No. The file or permissions can change, or the filesystem can fail or be locked.

**10. Does having a log file mean every record is already durably stored by the collector?**  
Not yet. There are still buffers, flushes, networks, collectors, rotation/retention, and separate storage policies.

## 17. References

- [Java SE 17 — Path](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Path.html): resolve, normalize, toAbsolutePath, toRealPath.
- [Java SE 17 — Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): Files.createDirectories, file access, and I/O.
- [Java SE 17 — FileHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/FileHandler.html): %h/%t/%g/%u pattern syntax, limit, count, append.
- [Logback Manual — Appenders](https://logback.qos.ch/manual/appenders.html): FileAppender, RollingFileAppender, and fileNamePattern.
- [Logback Manual — Configuration](https://logback.qos.ch/manual/configuration.html): file configuration and property substitution.

## Key Takeaways

**Log paths must be determined according to the real runtime.** Always know where the application is running, whether the path is relative or absolute, which container or volume the file resides on, who has write permissions, and what the rotation/retention policy is. Use **Path/Files** to handle directories safely, use the right backend **Handler/Appender** to write, and never let untrusted input choose the storage location. Writing to a file does not mean all logs are already durably stored in the final backend.