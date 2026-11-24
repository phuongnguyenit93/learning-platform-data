# Creating Heap Dumps and Verifying JVM-Compatible Formats

## 1. What Does a Heap Dump Tell You?

A **heap dump** is a snapshot of data on a JVM's heap memory at collection time. It lets you inspect objects, classes, and reference relationships to investigate why memory is being retained.

For example, a service has finished processing many requests, yet a shared list still holds data from all past requests. Logs may show when requests were processed; a heap dump helps identify which object is still retaining that data.

Evidence sources must be distinguished:

| Data source | Primary question |
| --- | --- |
| Logs | Which events occurred, and in what sequence? |
| Thread dump | Where are threads executing or waiting? |
| Object histogram | How many objects exist per class, and roughly how much memory do they occupy? |
| Heap dump | Which objects exist and how are they linked and retaining references to each other? |
| System/core dump | Memory and process state broader than the Java heap, depending on JVM/OS |

A single heap dump does not by itself prove a memory leak. A large but legitimate cache and a set of unexpectedly retained objects can look similar if you only look at total size. You must combine collection timestamp, system load, and reference relationships.

In Spring Boot 3.3, the `heapdump` endpoint provides a dump of **the JVM running the exact application receiving the request**, via `GET /actuator/heapdump`. The response is binary data and can be large; it must be saved to a file for analysis. [Heap Dump REST API — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/heapdump.html)

## 2. Format Depends on the JVM

Do not start with the assumption "a Java heap dump is always an `.hprof` file".

| Application JVM | Heap dump format provided by Actuator | What to verify |
| --- | --- | --- |
| HotSpot | HPROF | HPROF header and analyzer compatibility |
| Eclipse OpenJ9 | PHD — Portable Heap Dump | PHD header and OpenJ9/PHD reader support |
| Other JVM or custom runtime | Do not infer solely from Java version | Dump mechanism supported by the running JVM and Spring Boot version |

Spring Boot explicitly documents the difference between HPROF on HotSpot and PHD on OpenJ9. Two files can both be downloaded from `/actuator/heapdump` yet not share the same binary structure. [Heapdump format](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/heapdump.html)

**The filename does not determine the format.** If you save an OpenJ9 response as `heapdump.hprof`, the data is still PHD. Renaming the file does not convert PHD to HPROF.

Nor can you infer the VM from the JDK vendor name alone. When recording the environment, capture both the JVM name and the actual process version:

```java
System.out.println("java.vm.name=" + System.getProperty("java.vm.name"));
System.out.println("java.vm.version=" + System.getProperty("java.vm.version"));
System.out.println("java.vendor=" + System.getProperty("java.vendor"));
System.out.println("java.version=" + System.getProperty("java.version"));
```

This is a **snippet placed inside an application or diagnostic program**, not a standalone runnable Java class. Specific values vary by environment.

Running `java -version` in a terminal only reports the `java` executable selected by that terminal. The running application may use a different JDK or live inside a different container.

For a HotSpot process you have permission to diagnose, you can run:

```text
jcmd <ACTUAL_PID> VM.version
```

Replace `<ACTUAL_PID>` with the exact application PID. Use a matching JDK version and run in a context that can attach to the target process; do not infer the application's JVM details solely from the machine downloading the file. [JDK 21 diagnostic tools](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html)

## 3. Preparing the heapdump Endpoint in Spring Boot 3.3

### 3.1. Dependencies and Configuration

For a Spring MVC web application already using Spring Boot and dependency management, the Gradle declaration typically includes:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

This is an **addition to an existing build**, not a complete standalone project. WebFlux applications use the corresponding starter; you do not need to add both MVC and WebFlux to take a heap dump.

Illustrative configuration:

```properties
management.endpoint.heapdump.enabled=true
management.endpoints.web.exposure.include=health,heapdump
```

In the Spring Boot 3.3 line, enabling an endpoint and exposing it over HTTP are two separate conditions. By default only `health` is exposed over HTTP; if `heapdump` appears in the `exclude` list, exclusion takes precedence over `include`. [Enabling and Exposing Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.enabling)

The configuration above uses the default `/actuator/heapdump` URL. If you change the management port, context path, base path, or endpoint mapping, use the corresponding URL.

### 3.2. Access Permissions and File Creation Capability

Exposing the endpoint does not replace security rules. If the application uses Spring Security, use an account and permissions matching the current configuration. Do not fix 401/403 errors by opening heap dumps to everyone.

Beyond HTTP, the JVM must be able to generate the dump and have write permissions to the temporary directory on the application side. Free disk space on the client machine does not help if the application container's temp directory or volume is full.

A heap dump can contain sensitive application data; with HPROF, string values and object data can appear in the contents. Therefore, provide the endpoint only to those who need it for diagnosis and store files where access is controlled. Do not treat value-masking on another configuration endpoint as an automatic sanitizer for heap dumps.

### 3.3. Planning for Collection Impact

Creating a dump can pause the JVM and generate significant I/O. Duration and size depend on heap usage, object count, JVM, storage device, and collection method; there is no single fixed number applicable to every application.

Before taking a dump, determine the exact process/application instance, timing, and expected capacity on both the generation side and the download side. Do not put this operation into a polling loop or periodic health check.

If the service has multiple instances behind a load balancer, a request may land on any routed instance. Record the exact application instance that produced the dump; do not combine memory conclusions from one instance with metrics from another.

## 4. Downloading Valid Binary Data and Checking HTTP

### 4.1. Saving the File with curl

In PowerShell, use `curl.exe` to invoke the real curl binary, avoiding collisions with aliases in some environments:

```powershell
curl.exe --fail --show-error --dump-header heapdump.headers.txt --output heapdump.bin --write-out "HTTP_STATUS=%{http_code}\n" "http://localhost:8080/actuator/heapdump"
```

On Linux/macOS use the same options with `curl` instead of `curl.exe`:

```bash
curl --fail --show-error --dump-header heapdump.headers.txt --output heapdump.bin --write-out 'HTTP_STATUS=%{http_code}\n' 'http://localhost:8080/actuator/heapdump'
```

Two files are created on **the machine running curl**:

- `heapdump.headers.txt` holds HTTP headers for verification.
- `heapdump.bin` holds the downloaded body; use a neutral extension before determining the format.

Use a new filename for each collection to avoid overwriting earlier evidence. There is no need to print binary data to the terminal.

If the application uses Basic authentication, you can add `--user operator` so curl prompts interactively for the password, provided `operator` is an actually authorized account. If the system uses another mechanism, follow that mechanism instead of altering application security.

### 4.2. Verify the Result, Not Just File Existence

For a full dump request, look for HTTP 200 and error-free completion. `--fail` reports errors for HTTP responses 400 and above, yet does not replace checking redirects, content, or an interrupted transfer.

A login page returning HTTP 200 could also end up saved into `heapdump.bin`. A 302 redirect response must be handled through the system's authentication flow, not treated as a successful dump.

Check next:

1. Curl exit code and HTTP status.
2. File size is greater than 0.
3. Binary header matches the expected format.
4. The analysis tool can parse the document structure.

`Content-Type: application/octet-stream` only describes generic binary data; it does not distinguish HPROF from PHD. Do not use media type or filename extension alone as proof of format.

**Do not use `curl -I` or header-only requests as a substitute for downloading the dump.** The goal is to obtain and verify the full body; probing the endpoint repeatedly can also trigger multiple expensive collections.

### 4.3. Separating Server-Side and Client-Side File Locations

```text
Application JVM
    → creates dump file on the server side
    → streams body over HTTP
    → curl writes file on the client side
    → analysis tool reads the downloaded file
```

`--output heapdump.bin` only chooses the filename on the curl side. It does not tell the JVM to write the server-side file to that same path.

If using a JVM mechanism that writes directly to a file instead of downloading over HTTP, the path belongs to the machine hosting the JVM, not the laptop driving the diagnosis. This is a common point of confusion when working with containers and remote servers.

## 5. Inspecting Headers Before Opening in an Analysis Tool

### 5.1. Initial Identification Signatures

| Leading file signature | Initial assessment |
| --- | --- |
| String `JAVA PROFILE ` | Has an HPROF header |
| UTF string `portable heap dump` in PHD layout | Has a PHD header |
| Two bytes `1F 8B` | GZIP wrapper; decompress or use a reader supporting compression, then check inner contents |
| JSON, HTML, empty file, or other header | Not confirmed as a valid heap dump; check source and HTTP |

PHD has a header containing an identifying UTF string, version, and format flags; it is not plain text just because part of it is readable ASCII. [OpenJ9 Heap Dump Format](https://eclipse.dev/openj9/docs/dump_heapdump/)

A file with a valid header can still be truncated or corrupted later in the file. Header inspection is a screening step, not a full integrity confirmation.

### 5.2. Preliminary Java 17+ Header Check Program

Save as `DumpHeaderCheck.java`. The program reads at most the first 64 bytes so it never loads an entire large heap dump into its own memory.

```java
import java.io.ByteArrayInputStream;
import java.io.DataInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class DumpHeaderCheck {
    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            throw new IllegalArgumentException("Usage: java DumpHeaderCheck <file>");
        }

        byte[] prefix;
        try (InputStream input = Files.newInputStream(Path.of(args[0]))) {
            prefix = input.readNBytes(64);
        }

        String format = "UNKNOWN";
        String text = new String(prefix, StandardCharsets.ISO_8859_1);

        if (text.startsWith("JAVA PROFILE ")) {
            format = "HPROF_HEADER";
        } else if (prefix.length >= 2
                && (prefix[0] & 0xff) == 0x1f
                && (prefix[1] & 0xff) == 0x8b) {
            format = "GZIP_CONTAINER";
        } else {
            try (DataInputStream input = new DataInputStream(
                    new ByteArrayInputStream(prefix))) {
                if ("portable heap dump".equals(input.readUTF())) {
                    format = "PHD_HEADER";
                }
            } catch (IOException ignored) {
                // Prefix does not contain a complete PHD UTF header.
            }
        }

        System.out.println(format);
    }
}
```

Compile and run with JDK 21:

```text
javac --release 21 -encoding UTF-8 DumpHeaderCheck.java
java DumpHeaderCheck heapdump.bin
```

For an uncompressed HPROF file with a matching header, stdout is:

```text
HPROF_HEADER
```

For a typical JSON or HTML error file, the result is `UNKNOWN`. For a PHD with a recognized header, the result is `PHD_HEADER`. `GZIP_CONTAINER` only confirms the compression wrapper, not that the inner payload is a heap dump.

This program does not validate every HPROF/PHD record, convert formats, or replace an analysis tool. After identification, you may rename the file to `.hprof` or `.phd` for reader convenience; renaming does not alter any bytes inside.

## 6. Standalone HotSpot Practice with Java 21

The following example creates a small dump of **the demo JVM itself**, without pulling data from another application process and without trying to trigger `OutOfMemoryError`. It lets you verify the HPROF creation path independently of HTTP configuration.

### 6.1. Complete Program

Save as `HeapDumpLab.java`:

```java
import com.sun.management.HotSpotDiagnosticMXBean;
import java.io.InputStream;
import java.lang.management.ManagementFactory;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public class HeapDumpLab {
    private static final List<byte[]> PAYLOAD = new ArrayList<>();

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Usage: java HeapDumpLab <new-file.hprof>");
        }

        Path output = Path.of(args[0]).toAbsolutePath().normalize();
        if (!output.toString().endsWith(".hprof")) {
            throw new IllegalArgumentException("Output must end with .hprof");
        }
        if (Files.exists(output)) {
            throw new IllegalArgumentException("Output already exists");
        }
        Files.createDirectories(output.getParent());

        for (int i = 0; i < 8; i++) {
            PAYLOAD.add(new byte[256 * 1024]);
        }

        HotSpotDiagnosticMXBean bean = ManagementFactory.getPlatformMXBean(
                HotSpotDiagnosticMXBean.class);
        if (bean == null) {
            throw new UnsupportedOperationException("HotSpot diagnostic MBean unavailable");
        }
        bean.dumpHeap(output.toString(), true);

        byte[] prefix;
        try (InputStream input = Files.newInputStream(output)) {
            prefix = input.readNBytes(32);
        }
        String header = new String(prefix, StandardCharsets.ISO_8859_1);

        System.out.println("DUMP_CREATED=" + Files.isRegularFile(output));
        System.out.println("HEADER_IS_HPROF=" + header.startsWith("JAVA PROFILE "));
        System.out.println("FILE_NONEMPTY=" + (Files.size(output) > 0));
    }
}
```

`PAYLOAD` holds eight arrays totaling 2 MiB of elements, providing deliberate live referenced demo data. This is intentional data, not an experiment concluding a memory leak on its own.

`HotSpotDiagnosticMXBean.dumpHeap(..., true)` requests collecting only live objects—objects reachable through reference chains per JVM mechanics. The API requires the filename to end with `.hprof` and fails if the file already exists or cannot be written. This is a HotSpot-specific diagnostic API, not a universal heap dump API across all JVMs. [HotSpotDiagnosticMXBean — JDK 21](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.management/com/sun/management/HotSpotDiagnosticMXBean.html)

### 6.2. Run Commands and stdout

In a separate practice directory, make sure `demo.hprof` does not already exist:

```text
javac --release 21 -encoding UTF-8 HeapDumpLab.java
java -Xms32m -Xmx64m HeapDumpLab demo.hprof
```

On a HotSpot JVM supporting the API and with write permission, program stdout is:

```text
DUMP_CREATED=true
HEADER_IS_HPROF=true
FILE_NONEMPTY=true
```

File size is not fixed at exactly the 2 MiB of demo data: the dump also contains runtime objects and other JVM objects.

Run the header check program from earlier next:

```text
java DumpHeaderCheck demo.hprof
```

Expected result:

```text
HPROF_HEADER
```

If you re-run `HeapDumpLab` with the same filename, the program refuses to overwrite. Use a new filename for the next collection.

On OpenJ9, do not use this HotSpot program as a criterion to conclude whether the JVM supports heap dumps. Other JVMs have different diagnostic APIs/mechanisms.

## 7. Other Collection Paths and Their Scope

### 7.1. Creating a HotSpot Dump with jcmd

With an identified PID and appropriate attach permissions:

```text
jcmd <ACTUAL_PID> help GC.heap_dump
jcmd <ACTUAL_PID> GC.heap_dump <NEW_FILE_PATH.hprof>
```

Items inside `<...>` are placeholders to replace with actual values; do not type the angle brackets literally into the shell.

On HotSpot JDK 21, `GC.heap_dump` creates HPROF. The `-all` option can include unreachable objects as well; per documentation, the command requests a full garbage collection (full GC) unless `-all` is used. This is a high-impact operation depending on heap content/size. [jcmd — JDK 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html#gc-heap-dump)

The path belongs to the machine hosting the JVM. Inside containers, PID and path must be interpreted in the exact process/container context, with required write permissions.

Options of a diagnostic command can vary by JVM/version. Read `help` on the target process itself before applying variants from another environment.

### 7.2. Collecting When HotSpot Encounters OutOfMemoryError

This can be configured at startup, for example with a Linux path:

```bash
java -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/var/dumps/app-oom.hprof -jar app.jar
```

This mechanism differs from an active Actuator request: the JVM is configured to generate a dump when a qualifying error occurs. The directory must exist, be writable, and have enough space; do not try to induce an OOM error on a real service just to test the flag. [Java 21 serviceability options](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html#advanced-serviceability-options-for-java)

Do not confuse `-XX:HeapDumpPath` with the path given to `curl --output`. One is where the JVM writes when the OOM hook fires; the other is where the client saves the HTTP response.

### 7.3. OpenJ9 and PHD

OpenJ9 has its own dump mechanisms, including `-Xdump` configuration and OpenJ9 diagnostic APIs. When pulling a dump from Actuator on OpenJ9 under the Spring Boot contract, be prepared to read PHD rather than forcing an HPROF-only tool.

PHD is not equivalent to HPROF in every data field. For instance, primitive values and certain detailed analysis info may not be present as in HPROF; retain the corresponding `javacore` from the same time if available for extra context. Do not promise that an analysis query designed for HPROF will return the same information on PHD.

Eclipse Memory Analyzer documentation describes reading IBM/OpenJ9 dumps via the DTFJ reader and the differences among PHD, HPROF, and system dumps. [Acquiring Heap Dumps — Eclipse MAT](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/tasks/acquiringheapdump.html)

## 8. Choosing the Right Analysis Tool and Verifying Readability

After downloading and identifying the format:

1. Choose a tool/reader supporting the exact HPROF or OpenJ9/PHD format and relevant version.
2. With Eclipse Memory Analyzer (MAT), open `File → Open Heap Dump`.
3. If reading PHD, install the DTFJ reader/plug-in per tool documentation; an `.hprof` filename cannot substitute for a PHD reader.
4. Let the tool finish parsing and indexing.
5. Only after parsing succeeds should you start interpreting histograms, dominator trees, and reference paths to GC roots.

OpenJ9 documents using MAT or IBM Memory Analyzer with the DTFJ plug-in to analyze PHD. [Analyzing OpenJ9 Heap Dumps](https://eclipse.dev/openj9/docs/dump_heapdump/#analyzing-dumps)

Distinguish three levels of evidence:

```text
Successful HTTP download
    ≠ confirmed correct format
    ≠ confirmed complete file and readable by tool
```

A tool failing to open a file may be due to a missing reader, insufficient analysis memory, or file corruption. Do not immediately conclude the application produced a bad dump.

When verifying file transfers between machines, you can compare SHA-256 on both ends. Matching hashes prove only that both copies have the same bytes; they do not prove the original file is a complete dump or describes the exact application instance needing diagnosis.

Once parsed, prioritize specific questions: which class grew the most, which object retains the data, and which reference path leads back to GC roots? A single dump shows state at one moment; comparing multiple timestamps under equivalent conditions is what reveals trends.

## 9. Common Errors

| Symptom | Possibilities to distinguish | How to check |
| --- | --- | --- |
| HTTP 404 | Wrong path, management port, endpoint disabled or not exposed | Actual URL, `enabled`, exposure, and routing config |
| HTTP 401/403 | Authentication/authorization not satisfied | Account, roles, and current security config |
| File is only a few hundred bytes, containing JSON/HTML | Saved an error message or login page | HTTP status, redirects, headers, and leading bytes |
| File has `.hprof` extension, yet tool reports invalid format | May be PHD or another misnamed file | Actual JVM and binary header |
| Header is valid, yet tool reports unexpected EOF | Incomplete download or truncated file | Curl exit code, transfer errors, disk space, source file if present |
| PHD does not appear in file picker or fails to parse | May lack the proper reader | Tool's PHD/DTFJ support |
| Tool runs out of memory while parsing | Heap dump is large relative to analyzer memory | Tool's JVM config, working storage, and parse logs |
| Application fails while creating dump | May lack disk space/write permission or unsupported dump mechanism | App logs, JVM/runtime, temp directory, and server-side resources |
| Dump size differs from configured heap size | Dump is a snapshot representation, not an exact `-Xmx` copy | Collected object set, format, compression, and capture time |

Do not use "renaming extension to .hprof" as a format fix, or repeatedly trigger dumps to see if the next one opens. Identify the error class before collecting again.

## 10. Verification Exercises

1. Run `HeapDumpLab` on HotSpot JDK 21 and verify the three stdout lines.
2. Use `DumpHeaderCheck` to inspect `demo.hprof`; the result must be `HPROF_HEADER`.
3. Create a small text file containing `{"status":403,"error":"Forbidden"}` and inspect it; the result must be `UNKNOWN`. Renaming an error file to `.hprof` does not turn it into a heap dump.
4. On a practice Spring Boot application with an authorized endpoint, download the dump via curl, recording HTTP status, actual JVM, and collection timestamp.
5. Choose a format-appropriate reader and confirm parsing succeeds. If the environment uses OpenJ9, note PHD and DTFJ support instead of mechanically applying HotSpot expectations.

The desired outcome is a clear chain of evidence: **exact JVM/instance → collection completed → format identified → appropriate reader parses it → memory retention relationships analyzed**.
