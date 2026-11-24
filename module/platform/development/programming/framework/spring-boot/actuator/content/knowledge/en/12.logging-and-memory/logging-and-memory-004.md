# Using the Logfile Endpoint When an Application Has Configured a Log File

When investigating an issue on a running Spring Boot application, an operator may need to read messages already written to a log file. Actuator's `logfile` endpoint provides an HTTP path to read the contents of the log file identified by the application.

For it to work, three pieces must be in place: **the application actually writes to a file → Actuator can locate the file to read → the caller is permitted to access the endpoint**. Simply adding `logfile` to the exposure list does not automatically give a console-only application a log file.

This lesson uses **Java 21, Spring Boot 3.3.13, Spring MVC, and the starter's default Logback configuration**. HTTP calls read the whole file or a byte range; they do not create a continuous stream following new lines.

## 1. What Data Does This Endpoint Read?

With an application that already has a log file:

```text
Logger call
    ↓
File writer (file appender)
    ↓
Log file on the process's filesystem
    ↓
GET /actuator/logfile
    ↓
File contents sent in the HTTP response
```

The body is file data, typically log text. It is not a JSON object describing loggers or log levels.

Boundaries to remember:

| Need | Capability of `logfile` |
| --- | --- |
| Read the identified log file | Yes |
| Read a slice by byte position | Yes on this example's Spring MVC |
| Automatically turn every process's stdout into a file | No |
| Automatically find and merge logs from all app instances | No |
| Automatically concatenate all rotated and compressed files | No |
| Hold the connection open waiting for new log lines like `tail -f` | No |
| Pick an arbitrary file on the machine via a path parameter | Not part of the standard endpoint interface |

Messages must be written to the selected file to appear in the read data. A line printed directly to the console or sent to another destination might not be in that file.

Official HTTP specification: [Log File endpoint — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/logfile.html).

## 2. Log File Configuration and Exposure Configuration Are Two Separate Things

### 2.1. Choosing a File with Default Logging Configuration

Spring Boot logs to the console by default. To also write to a file using the default logging configuration, you can use one of two properties:

| Property | Meaning | Example |
| --- | --- | --- |
| `logging.file.name` | Specifies the filename or full path to the file | `logs/application.log` |
| `logging.file.path` | Specifies a directory; default filename is `spring.log` | `logs` |

Example specifying a file:

```yaml
logging:
  file:
    name: logs/application.log
```

Alternative example, specifying a directory:

```yaml
logging:
  file:
    path: logs
```

In the second case, the file is `logs/spring.log`. If both `logging.file.name` and `logging.file.path` are set, Spring Boot uses `name` and ignores `path`; it does not concatenate the two properties into a new path.

Relative paths are resolved from the **process's working directory**, not automatically from the directory containing the JAR or from the module directory in source code. An IDE, an OS service, and a container may launch the same JAR from different working directories.

Reference: [Spring Boot Logging — File Output](https://docs.spring.io/spring-boot/3.3/reference/features/logging.html#features.logging.file-output).

### 2.2. Allowing Endpoint Access over HTTP

Add the endpoint to the allowed list:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,logfile
```

With Spring Boot 3.3, if application policy disables endpoints by default or specifically disables `logfile`, re-enable it deliberately:

```properties
management.endpoint.logfile.enabled=true
```

Enabling and exposure still do not replace access control. The caller must also reach the right port, the right path, and have read permission if the application is secured.

If `management.endpoints.web.exposure.exclude` is set, check that list too because `exclude` wins over `include`.

### 2.3. The File Must Exist and Be Readable

At the time the endpoint is called, verify:

- The process has actually created or opened the expected file.
- The account running the application has read permission for that path.
- The file resides on a filesystem or volume visible to the process.
- A custom logging configuration is not routing messages to a different file.

Successfully configuring the endpoint does not guarantee file contents always exist at every moment. Log rotation, volume changes, or permission changes can cause a later read to produce a different result than an earlier one.

## 3. Standalone Example

Create a separate project:

```text
actuator-logfile-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── learning/
        │       └── actuator/
        │           └── LogfileDemoApplication.java
        └── resources/
            └── application.yml
```

JDK 21 and Maven 3.6.3 or later are required. The first build needs Maven repository access to download dependencies.

### 3.1. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>learning</groupId>
    <artifactId>actuator-logfile-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 3.2. `src/main/java/learning/actuator/LogfileDemoApplication.java`

```java
package learning.actuator;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class LogfileDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(LogfileDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner writeExampleMessages() {
        return args -> {
            Logger logger = LoggerFactory.getLogger("demo.filelog");
            logger.info("FILE_DEMO started");
            logger.warn("FILE_DEMO completed");
        };
    }
}
```

The runner creates two messages using a logger named `demo.filelog`. This is a complete program; no business controller is needed to use the built-in Actuator endpoint.

### 3.3. `src/main/resources/application.yml`

```yaml
server:
  address: 127.0.0.1
  port: 18083

spring:
  main:
    banner-mode: "off"

management:
  endpoints:
    web:
      exposure:
        include: health,logfile

logging:
  file:
    name: logs/application.log
  level:
    root: WARN
    demo.filelog: INFO
  pattern:
    console: "%msg%n"
    file: "%msg%n"
```

In the experiment:

- The log file is `logs/application.log` under the working directory.
- The demo logger is enabled from `INFO`; the root logger is at `WARN` to reduce unrelated startup logs.
- The pattern keeps only the message text, making it easy to compare the file and the HTTP body.
- The server listens on loopback at `127.0.0.1:18083`.

The example omits Spring Security to focus on local-machine operations. In real deployments, the log-file reading endpoint must go through network controls, authentication, and proper read permissions.

### 3.4. Packaging and Running

In the directory containing `pom.xml`:

```shell
mvn clean package
java -jar target/actuator-logfile-demo-1.0.0.jar
```

If port `18083` is already in use, choose another port via `--server.port` and update the check URLs.

Make sure no external configuration, environment variables, or other arguments override `logging.file.name`, log levels, or exposure for the experiment.

The two messages written by the runner are:

```text
FILE_DEMO started
FILE_DEMO completed
```

On the first run in a clean working directory, with no extra environment warnings, that is also the demonstration content inside the log file. On subsequent runs, append mode may retain lines from previous runs; do not expect the file to truncate automatically when starting the JAR.

The minimal pattern is only for verification. In real operations, you usually need timestamps, log levels, logger names, and appropriate correlation details for tracing.

## 4. Reading or Downloading File Contents

Open a second terminal while the application is running:

```shell
curl -i "http://127.0.0.1:18083/actuator/logfile"
```

On Windows PowerShell, use `curl.exe` if `curl` is aliased to a PowerShell command.

A successful full-file read returns `200 OK`. In the example, the body is log text; the response has content type `text/plain` and supports byte ranges via `Accept-Ranges: bytes`.

Headers such as date and length depend on the run. Line-ending characters can also differ across operating systems, so do not use visible character count to infer every `Content-Length` value.

### Saving the Body to a Local File

```shell
curl --fail --output downloaded-application.log "http://127.0.0.1:18083/actuator/logfile"
```

The file `downloaded-application.log` is created on the HTTP client machine. It is the downloaded result; the source file on the server remains `logs/application.log`.

If you want to save headers and body separately:

```shell
curl --fail --dump-header logfile-response.headers --output downloaded-application.log "http://127.0.0.1:18083/actuator/logfile"
```

Do not add `-i` when you need a clean body in the downloaded file, because that option writes headers into the output stream as well. Check both the tool exit code and the response status code before considering a download successful.

A client that always expects JSON must be adjusted for this plain-text response. Avoid feeding log contents through a JSON parser.

## 5. Reading Part of a File with HTTP Range

Production log files can be large. When only a slice is needed, send a `Range` header to limit the byte region fetched instead of repeatedly downloading the entire file.

### 5.1. Fetching the First Nine Bytes for Verification

```shell
curl -i -H "Range: bytes=0-8" "http://127.0.0.1:18083/actuator/logfile"
```

Positions start at `0`, and both endpoints are inclusive: `0-8` is **9 bytes**.

With the demo file starting with `FILE_DEMO started`, the body is the ASCII string `FILE_DEMO`. A successful range response returns `206 Partial Content`.

Headers to read:

| Header | Meaning |
| --- | --- |
| `Accept-Ranges: bytes` | The resource supports byte-range requests |
| `Content-Range` | The byte range returned and the reported total size |
| `Content-Length` | Number of bytes in the body sent for that response |

Do not read `Content-Length` of a `206` response as the size of the entire file. The total size is expressed in `Content-Range` when available.

### 5.2. Fetching a Leading Block or Trailing Block

Fetch up to the first 1024 bytes:

```shell
curl -i -H "Range: bytes=0-1023" "http://127.0.0.1:18083/actuator/logfile"
```

Fetch up to the last 4096 bytes:

```shell
curl -i -H "Range: bytes=-4096" "http://127.0.0.1:18083/actuator/logfile"
```

Another form fetches from an offset to the end:

```text
Range: bytes=1024-
```

This form is valid only when the starting position fits the resource. With the very small demo file, offset `1024` is already past the end of the file; do not use it expecting data to always be returned.

If the file is shorter than the trailing byte count requested, do not assume the body still contains exactly 4096 bytes. Inspect the headers and actual byte count.

### 5.3. Range Is Not Line Count

`bytes=-4096` means fetching a trailing slice in **bytes**, not 4096 lines, 4096 characters, or all messages within a time window.

A cut point can land:

- In the middle of a log line.
- Between bytes of a UTF-8 character.
- In the middle of a multi-line stack trace.

Therefore, the beginning of the body may be an incomplete line or a byte fragment that cannot decode standalone. When processing text, account for encoding boundaries and line boundaries; do not treat an arbitrary byte chunk as a set of complete log records.

In the ASCII experiment, `bytes=0-8` is easy to verify because each character of `FILE_DEMO` is one byte. That rule does not hold generally for Vietnamese text.

### 5.4. Unsatisfiable Range

Try an offset far past the end of the small example file:

```shell
curl -i -H "Range: bytes=999999999-" "http://127.0.0.1:18083/actuator/logfile"
```

With the experiment's Spring MVC, the response is `416 Range Not Satisfiable`; `Content-Range` reports the unsatisfiable range along with the resource size.

That is a byte-range selection error, not an indication that the application stopped writing logs. Re-read the size or request an appropriate range. If the file rotated or shrank, an offset obtained from an earlier call may no longer be valid.

Inspect the actual response status code: an intermediate proxy can alter forwarding or `Range` handling. Do not treat a full-file body returned with `200` as if it were guaranteed to be the next chunk after a prior download.

Spring Boot documentation also notes that partial file reading via this mechanism is not supported when using Jersey. This lesson's example uses Spring MVC, not Jersey.

## 6. When the File Is Created Outside Default Logging Configuration

An application may write logs via custom backend configuration or have its output redirected to a file by the OS. When Actuator cannot locate the file via `logging.file.name` or `logging.file.path`, Spring Boot 3.3 provides the property:

```yaml
management:
  endpoint:
    logfile:
      external-file: /var/log/my-service/service.log
```

This is an additional configuration example for a system that already has a file at that path. Proper exposure, HTTP access permissions, and filesystem read permissions must still be in place.

`external-file` specifies **the file that the endpoint reads**. It does not create a file appender, redirect stdout to a file, or change the output target of any logger. The file-writing mechanism must be configured separately and actively running.

When both `external-file` and `logging.file.name` are present, the endpoint uses the specified external file. As a result, the application could be writing to one file while the endpoint reads another if deployment configuration is inconsistent.

In the standalone example, `external-file` is unnecessary: `logging.file.name=logs/application.log` is enough for Actuator to locate the file.

Property reference: [Common Application Properties — management.endpoint.logfile.external-file](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html#application-properties.actuator.management.endpoint.logfile.external-file).

### The Endpoint Is Not a Filesystem Browser

The path read is determined by server-side configuration. The standard API does not define selecting an arbitrary file via URL such as:

```text
/actuator/logfile?file=some-other.log
```

Do not build operational tools assuming this parameter switches the source file. In the experiment's Spring MVC, that undefined parameter does not change the resource being read.

If you need to inspect another archived file, use tools and access controls designed for that job; do not turn the endpoint into an interface accepting arbitrary paths from callers.

## 7. Interpreting Data Properly When Logs Continue Growing or Rotate

### 7.1. Each Call Is One File Read

After a request finishes, the connection does not continue streaming new lines written afterward. To observe again, make another request or use a dedicated log-monitoring system.

An actively written file can change between or during reads. A sequence of Range requests does not automatically produce an immutable snapshot of the same file version.

When stable evidence is needed for an incident timestamp, use an appropriate copy or snapshot procedure on the source system, and record the timestamp, application instance, and file source.

### 7.2. Rotation Changes the Observed Resource

When the logging backend rotates files, the active file may be renamed, moved to an archive file, or replaced with a new file at the same path.

The endpoint reads the configured resource; it does not automatically merge `application.log`, older dated files, and `.gz` files into one seamless history.

Therefore:

- The current byte count is not guaranteed to be larger than the previous one.
- A previously used offset may point to different content or fall outside the new file.
- A fetched tail segment may belong to the new active file and lack errors that occurred before rotation.
- Blindly stitching chunks downloaded at different times can create duplicated or missing data.

Design log retrieval around the system's rotation policy. The endpoint is convenient for reading the active file, while searching history across multiple files is usually better suited to a centralized log store or authorized archive tools.

## 8. Production Usage

Log files may contain tokens, personal data, connection strings, request payloads, stack traces, or internal data logged unintentionally. When granting file read access, consider **all content that may have been written**, not just the latest messages.

Value-masking policies on `env` or `configprops` do not automatically sanitize `logfile` text content. Setting `show-values=never` on those endpoints does not turn the log file into sanitized data.

Proper operational practice should define:

- Which roles or accounts may read logs, over which network channels.
- Whether the endpoint is exposed permanently or only during an investigation task.
- How much data should be read per call; whether Range can limit download scope.
- Who may retain downloaded copies, where, and for how long.
- How access is audited and revoked once the task is complete.

For applications with Spring Security, secure the actual endpoint and security filter chain properly. The exposure list only controls publication capability; it does not provide a complete authorization model.

Repeatedly downloading an entire large file can consume I/O, bandwidth, and client resources. Range reduces transferred data when supported; it does not replace capacity limits and read authorization policies.

Reference on enabling, exposure, and securing endpoints: [Actuator Endpoints — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

### Containers That Write Only to stdout

If the deployment architecture intentionally writes only to stdout and the platform already collects logs, use the platform's log reader or centralized store. There is no need to create an extra file just to have this endpoint.

When the system chooses file logging, verify volume paths, process account permissions, and storage lifecycle. A file inside a container may not be at the same path as on the host and may be lost when the container is replaced if not persisted by design.

### Multiple Application Instances

Each instance may have its own local file. Two calls to the same URL through a load balancer may read logs from two different instances.

To correlate with an incident, record the instance source and timestamp. Do not conclude "there is no error in the system" just because one instance's file does not contain the line you are searching for.

## 9. Diagnosing When the Expected File Cannot Be Read

| Symptom | What to check |
| --- | --- |
| Logs appear only on console; endpoint has no data | Was file logging configured or a valid `external-file` selected? |
| `404` when calling `logfile` | Check HTTP path, enabled state, exposure, file configuration, and resource existence |
| `401` or `403` | Check account, roles, and access policy |
| `416` when sending Range | Check offset, current size, and rotation |
| Response has a body, but new messages are missing | Check right file, right instance, log level, output target, and flush delay if any |
| Body shows stale content or differs from the file viewed locally | Check working directory, `external-file`, volumes, and overriding config |
| Partial data has garbled characters or missing line start | Check byte boundaries, UTF-8, and line boundaries |
| Read error or server error returned | Check filesystem permissions, I/O errors, mounts, and operational logs via another channel |
| Client tool reports JSON parse error | Endpoint returns file content; choose appropriate text or byte handling |

With the configuration verified in the example, adding exposure alone without selecting a log file does not make an endpoint with readable data appear. When `external-file` points to a nonexistent resource, read requests return `404`.

Do not rely on a single `404` status code alone to conclude the exact cause. A wrong URL, a disabled/unexposed endpoint, and a nonexistent file resource may require different checks.

A useful verification order is: **right process and URL → endpoint enabled/exposed → HTTP permissions → right source path → file exists/readable → content and byte range**.

## 10. Practice Exercises

Perform on the demo project:

1. Run the application for the first time in a clean working directory and locate `logs/application.log`.
2. Call `GET /actuator/logfile`; find both `FILE_DEMO` messages in the body.
3. Download the body to `downloaded-application.log` and distinguish the downloaded file from the source file on the machine running the app.
4. Call `Range: bytes=0-8`; explain why the body is `FILE_DEMO` and 9 bytes long.
5. Call a range beyond the small file; explain the `416` status code.
6. Try fetching a trailing slice using a suffix range; explain why byte count is not equal to line count.
7. Stop and restart the application, then check whether the contents append to the old data.

Also answer three scenarios on your own:

- Switch to `logging.file.path=logs` and remove `logging.file.name`: the default file will be `logs/spring.log`.
- Set both `logging.file.name=logs/custom.log` and `logging.file.path=other-logs`: with Spring Boot's default config, the file chosen follows `name`, without combining them into `other-logs/logs/custom.log`.
- Two messages are read from instance A but missing from instance B: verify each instance's file source and execution flow before concluding data was lost.

Proper use of the endpoint must clearly identify **which source file, belonging to which process, which slice of data was read, and who is permitted to receive that copy**.
