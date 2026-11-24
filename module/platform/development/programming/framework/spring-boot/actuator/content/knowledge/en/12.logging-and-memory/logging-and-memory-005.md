# Reading Log File Slices with HTTP Range and Controlling Sensitive Data

## 1. Understanding Exactly What Is Being Read

A log file can grow to hundreds of MB while an operator only needs to inspect a few KB around an incident. Downloading the entire file every time makes diagnosis slower, generates extra traffic, and creates additional copies of data that must be protected.

HTTP Range allows a client to request a **byte** range of a resource. With Spring Boot Actuator, the resource here is the file served by the `logfile` endpoint. For example, `Range: bytes=0-1023` requests up to the first 1,024 bytes. This is not a command to fetch 1,024 lines, query by timestamp, or search by request ID.

Keep two questions separate during operations:

- **Which part is read?** Range determines which byte positions are transferred.
- **Who may read it, and what data is allowed to appear?** Security configuration and logging policy determine this.

Splitting a file containing passwords into multiple small responses still exposes the passwords. Range is a data transport mechanism, not a data masking mechanism.

This lesson uses Spring Boot **3.3.x**, Spring MVC, and Java 17 or later; JDK 21 is suitable for practice. Spring Boot has dedicated documentation for `GET /actuator/logfile`; Range reading **is not supported when using Jersey**. Do not generalize MVC experiment results to every HTTP handler. [Spring Boot 3.3 logfile documentation](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/logfile.html).

## 2. Reading Ranges by Byte Position

### 2.1. Zero-Based Start, Inclusive End

With `bytes=a-b`, bytes at both position `a` and position `b` are included in the requested slice. When the range lies within the file, the byte count is `b - a + 1`.

Use a sample file with this exact content, UTF-8 encoded, LF line endings, no BOM:

```text
alpha
beta
gamma
```

This file has **17 bytes**, including all three LF characters:

```text
Position: 0 1 2 3 4  5 6 7 8 9 10 11 12 13 14 15 16
Data:     a l p h a LF b e t a LF  g  a  m  m  a LF
```

| Request header | Meaning on the 17-byte file | Slice received when handled successfully |
| --- | --- | --- |
| `Range: bytes=0-4` | Bytes 0 through 4 | `alpha`, 5 bytes |
| `Range: bytes=6-9` | Bytes 6 through 9 | `beta`, 4 bytes |
| `Range: bytes=11-` | From byte 11 to the end | `gamma` and LF, 6 bytes |
| `Range: bytes=-6` | Last 6 bytes | `gamma` and LF, 6 bytes |
| `Range: bytes=0-99` | End exceeds end of file | Range is clamped to byte 16 |
| `Range: bytes=99-` | Start exceeds end of file | No satisfiable range; see `416` response |

A valid range whose end exceeds the end of the file is not an error: the server may clamp the end to the current length. A suffix longer than the file may span the entire file. Do not assume that "receiving the full content" must always return status `200`.

Range counts bytes, including line-ending bytes. In Vietnamese logs, a single character can occupy multiple UTF-8 bytes; with CRLF, each line break typically occupies two bytes. Do not calculate offsets by Java character count, screen column count, or line count. [RFC 9110, Section 14: Range Requests](https://www.rfc-editor.org/rfc/rfc9110.html#section-14).

### 2.2. Status Code and Response Headers Must Be Read

A single-range response may contain:

```http
HTTP/1.1 206 Partial Content
Accept-Ranges: bytes
Content-Range: bytes 6-9/17
Content-Length: 4
```

Meaning:

- `206`: the server is returning a partial resource.
- `Accept-Ranges: bytes`: the server advertises support for byte units.
- `Content-Range`: the actual slice is bytes 6 through 9; the total resource length at determination time is 17 bytes.
- `Content-Length`: the length of this response body, not the length of the entire file.

Do not use `Content-Length: 4` to conclude that the log file is only 4 bytes long.

If requesting `bytes=99-` on the sample file, the response to watch for is:

```http
HTTP/1.1 416 Requested Range Not Satisfiable
Content-Range: bytes */17
```

The reason phrase after the status number may vary across servers; what matters is **status 416** and the total length in `Content-Range`. Do not rely on the error body format to compute offsets.

HTTP allows a server to ignore Range and return `200`. Therefore, the client must inspect the response before appending data. If expecting a 4 KB slice and receiving `200`, do not treat that body as the next slice and append it to the downloaded file. [RFC 9110: 206](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.3.7), [416](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.5.17).

This lesson uses **one range per request**. Multiple ranges can produce a `multipart/byteranges` response, requiring a separate parser and resource limits; do not concatenate a multipart body as if it were a plain text slice.

## 3. Identifying the Exact File Served by Actuator

### 3.1. Log File Written by the Logging System

In an application using standard starters, to write logs to a file you can configure:

```yaml
logging:
  file:
    name: ./logs/application.log

management:
  endpoints:
    web:
      exposure:
        include: logfile
```

This is a **file-source configuration snippet**, not a complete security configuration for running over a network.

`logging.file.name` specifies the file name. If using `logging.file.path` instead, Boot's default configuration writes `spring.log` inside that directory. When both are set, `logging.file.name` takes precedence. Relative paths are resolved against the process working directory, not automatically against the source code directory. [Spring Boot 3.3: File Output](https://docs.spring.io/spring-boot/3.3/reference/features/logging.html#features.logging.file-output).

Having logs on the console does not prove that `logfile` has a file to return. For containers writing only to stdout/stderr, identify the actual log collection pipeline; do not create a duplicate log copy just to have this endpoint.

### 3.2. File Specified with external-file

Spring Boot 3.3 provides the property:

```yaml
management:
  endpoint:
    logfile:
      external-file: ./logs/range-demo.log
```

This property specifies the file that `logfile` reads, useful when logs are written via output redirection or another mechanism. **It does not configure a logger writer and does not create the file automatically.** In the experiment below, we use it to serve a fixed file so startup logs do not shift the offsets. [Property management.endpoint.logfile.external-file](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html#application-properties.actuator.management.endpoint.logfile.external-file).

The endpoint serves one configured file; it does not provide arbitrary path selection, directory listing, or browsing across all rotated log files. Do not add a user-controlled path parameter to turn it into a server file reader.

## 4. Experiment with Fixed Data and Authentication

### 4.1. Preparing the Application

Use a Spring Boot 3.3.x application with a `@SpringBootApplication` class and three dependencies managed by the same Spring Boot version:

```text
org.springframework.boot:spring-boot-starter-web
org.springframework.boot:spring-boot-starter-actuator
org.springframework.boot:spring-boot-starter-security
```

The Spring snippets below are code **added to this application**, not a standalone program runnable with `javac` without Spring dependencies.

Create `src/main/resources/application.yml` for the standalone practice application:

```yaml
server:
  address: 127.0.0.1
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: logfile
  endpoint:
    logfile:
      external-file: ./logs/range-demo.log

spring:
  security:
    user:
      name: log-reader
      password: "${LOG_READER_PASSWORD}"
      roles:
        - LOG_READER
```

Set the `LOG_READER_PASSWORD` environment variable to a dedicated test password before starting. Do not hardcode the password in YAML, as sample commands may be stored in shell history or log files. Do not leave the variable unset.

This application listens only on loopback for local testing. When deploying over a network, use HTTPS and access controls; Basic Authentication does not encrypt credentials by itself. Do not use certificate-verification bypass options to work around HTTPS errors.

### 4.2. Granting Access Only to the Log-Reader Role

Add `LogReadSecurity.java` in a package scanned by the application:

```java
package example.logrange;

import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class LogReadSecurity {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers(EndpointRequest.to("logfile"))
                    .hasRole("LOG_READER")
                .anyRequest().denyAll());
        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
```

In the practice application, this filter chain applies to all requests: only users with `ROLE_LOG_READER` can reach the `logfile` endpoint; other requests are denied. `hasRole("LOG_READER")` automatically applies the `ROLE_` prefix, matching `spring.security.user.roles` above.

This is a policy for a **log-only test application**. For an application with business APIs and an existing filter chain, integrate the log-reading rule into the existing policy; do not copy a deny-all rule and replace all business authorization.

When declaring your own `SecurityFilterChain`, the author is responsible for protecting relevant paths because Boot's auto-configured security backs off. `exposure.include` only makes the endpoint reachable over HTTP; it does not grant user authorization. There is no need to disable CSRF to perform the `GET` requests in this lesson. [Spring Boot 3.3: Actuator security](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.security).

Boot's single built-in user only keeps the experiment compact. Real systems should use individual identities or managed service accounts, with permission revocation and proper access logging.

### 4.3. Creating an Exact 17-Byte File with Java

Save the following standalone program as `LogFixture.java` in the experiment's working directory. The program **creates or overwrites only** `./logs/range-demo.log`; do not run it on operational log files.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class LogFixture {
    public static void main(String[] args) throws IOException {
        Path log = Path.of("logs", "range-demo.log");
        Files.createDirectories(log.getParent());
        Files.writeString(log, "alpha\nbeta\ngamma\n", StandardCharsets.UTF_8);
        System.out.println("bytes=" + Files.size(log));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac --release 17 -encoding UTF-8 LogFixture.java
java LogFixture
```

Exact stdout:

```text
bytes=17
```

Java writes the specified `\n` characters, so this file uses LF even on Windows. `StandardCharsets.UTF_8` in the write call above does not add a BOM.

Start the Spring Boot application from the **same working directory** after creating the file and setting the environment variable. Keep the sample file unchanged across the reads below. Do not simultaneously configure the logging system to write into `range-demo.log`.

### 4.4. Fetching Exactly the Four Bytes of the beta Line

The following commands use real `curl`. In Windows PowerShell, use **`curl.exe`** to avoid colliding with the `Invoke-WebRequest` alias. If your environment lacks Bash-style line continuation, put the command on one line.

```bash
curl --user log-reader --max-time 10 \
  -H 'Accept-Encoding: identity' \
  -H 'Range: bytes=6-9' \
  -D range.headers -o range.part \
  http://127.0.0.1:8080/actuator/logfile
```

`--user log-reader` prompts curl for the password on the terminal instead of putting the password directly in the command. `-D` saves headers separately; `-o` writes the body as raw bytes to a separate file. Do not mix headers into the content with `-i` when planning to concatenate downloaded slices.

With the configuration and sample file above, the key headers are:

```http
HTTP/1.1 206
Accept-Ranges: bytes
Content-Range: bytes 6-9/17
Content-Length: 4
```

This is an excerpt of the fields to check, not all headers or a fixed header order. The file `range.part` contains the exact four ASCII bytes of `beta`, **with no trailing LF**.

Verify with PowerShell:

```powershell
(Get-Item -LiteralPath './range.part').Length
[System.Text.Encoding]::UTF8.GetString(
    [System.IO.File]::ReadAllBytes((Join-Path (Get-Location) 'range.part'))
)
```

Displayed output:

```text
4
beta
```

### 4.5. Reading the Tail of the File and Testing an Out-of-Bounds Range

Fetch the last six bytes, saving separately so as not to overwrite the previous result:

```bash
curl --user log-reader --max-time 10 \
  -H 'Accept-Encoding: identity' \
  -H 'Range: bytes=-6' \
  -D suffix.headers -o suffix.part \
  http://127.0.0.1:8080/actuator/logfile
```

Expected result:

```http
HTTP/1.1 206
Content-Range: bytes 11-16/17
Content-Length: 6
```

The body is `gamma` followed by LF. **The last six bytes does not mean the last six lines**; this result happens to equal one line because of how the sample file was constructed.

Try a nonexistent start position:

```bash
curl --user log-reader --max-time 10 \
  -H 'Accept-Encoding: identity' \
  -H 'Range: bytes=99-' \
  -D invalid.headers -o invalid.body \
  http://127.0.0.1:8080/actuator/logfile
```

Expect `416` and `Content-Range: bytes */17`. The file `invalid.body` is the `416` response body if present; it is not the continuation of the log. Do not assume this body is always empty or always JSON: some handler paths may still carry file data. Protect it like log data and do not append it to successful downloads.

Standard curl can exit with code 0 even when HTTP is `416`. When writing automated tools, check the HTTP status code; you can use `--write-out '%{http_code}'` or `--fail-with-body` if your curl version supports it. Do not rely solely on the default exit code to conclude Range succeeded.

Finally, try the same request without credentials, and then with a valid identity that lacks the log-reader role in a multi-account environment. With the Basic policy above, the two cases should be blocked with `401` and `403` respectively; neither case may return log content.

## 5. Sequential Reading Without Corrupting Data

### 5.1. Updating the Offset from the Actual Response

Suppose you are reading a stable file:

1. Request `bytes=0-4095`.
2. Accept the data only after verifying status `206`, unit `bytes`, returned range, and actual received body size.
3. If `Content-Range` reports `bytes 0-4095/12000`, the next offset is **4096**.
4. Request `bytes=4096-8191` when the next slice is needed, then advance according to the actual returned end.

Do not take the next offset from "number of characters displayed". If the file is initially only 100 bytes long, the response may end at byte 99; you must continue from 100, not jump blindly to 4096.

With growing logs, data in the logger's buffer might not yet appear on disk. A Range request reads only what exists at processing time; it does not wait for future data or hold the connection open like `tail -f`. To monitor ongoing logs, send new requests at a bounded interval.

A production client also needs limits on total bytes received and stored, concurrent requests, timeouts, and polling frequency. If the server or proxy returns `200` for a Range request, the client must stop or handle it under an explicit full-file download policy; `--max-time` alone is not a size limit.

### 5.2. Rotation and Truncation Invalidate Old Offsets

Suppose you have read up to byte 50,000 of `application.log`. Then the file rotates: the old name now points to a new file that is only 2,000 bytes long. Requesting `bytes=50000-` may receive `416`.

However, `416` can also occur when the offset is right at the end of the file and no new bytes exist yet. Do not conclude "file rotated" from a `416` code alone.

Sensible handling flow:

- Re-read the total length if available, check for file-change indicators and rotation policy.
- If confirmed that a new file is active, start a new reading session; you can fetch a small suffix for orientation.
- Do not append bytes from two file versions into one copy and treat it as a single intact file.
- Do not retry the same rejected offset indefinitely.

Comparing size alone is also insufficient: the new file can be equal to or larger than the old file. Keeping the same path name does not prove the underlying resource stayed the same. The `logfile` endpoint does not provide an immutable snapshot mechanism across multiple requests.

HTTP has `If-Range` to bind a continuation request to an appropriate resource validator. Rely on that mechanism only when you have verified the endpoint and infrastructure actually issue and process a suitable validator; do not assume `logfile` always provides a strong ETag or safe resumption across rotation. When complete evidence is required, export a fixed log copy under access control instead of assuming an actively written file is immutable. [RFC 9110: If-Range](https://www.rfc-editor.org/rfc/rfc9110.html#section-13.1.5).

### 5.3. Preserve Bytes First, Decode and Split Lines Afterward

A Range can start in the middle of a UTF-8 character or in the middle of a line. If each slice is decoded independently into strings, Vietnamese characters at boundaries can be turned into replacement error characters.

When building a multi-slice reader:

- Concatenate bytes in order or use a stateful UTF-8 decoder.
- Carry over any incomplete trailing line fragment to join with the next slice.
- When fetching a suffix for a quick glance, recognize that the first line may be cut; drop that line only when the goal is displaying complete lines.
- If preserving evidence, keep the raw byte copy before generating a display version.

`Accept-Encoding: identity` in the experiment avoids content compression that complicates byte comparison. Do not casually add `--compressed` and then use the decompressed byte count as an offset for encoded data. When going through a proxy, inspect `Content-Encoding`, `Content-Range`, and content transformation policies.

## 6. Controlling Sensitive Information from Write Time to Read Time

### 6.1. Do Not Expect logfile to Automatically Redact Secrets

`logfile` returns the file's contents, including strings accidentally written into it. Settings like `management.endpoint.env.show-values=never` govern the `env` endpoint; they do not turn bytes inside a log file into redacted data. Likewise, configuration value-masking rules cannot be treated as a universal filter across all endpoints.

**Anyone permitted to read logfile must be considered permitted to read the entire served file**, even if their current tool only requests a small slice. They can send multiple Range requests or a request with no Range.

If the file contains data from multiple tenants, a "log reader" role does not automatically create per-tenant read isolation. Data separation or a query service with corresponding authorization checks is required; do not use byte ranges as an authorization boundary.

### 6.2. Prefer Never Logging Sensitive Data

Apply data policy where events are generated: log only selected fields, limit personal identifiers, exclude credentials, and sanitize untrusted input before writing. This is also core guidance in the [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html#data-to-exclude).

Synthetic event example containing no real data:

```text
Avoid:
login failed email=person@example.test password=demo-password token=demo-token

Prefer:
login_failed requestId=req-demo-42 reason=invalid_credentials
```

The second example retains correlation info for incident analysis without logging passwords or tokens. `requestId` also needs generation and validation rules; do not treat every client-supplied value as safe to log verbatim.

Frequently overlooked spots include full request/response loggers, interceptors, stack traces containing connection details, and library DEBUG logs. A filter at a single business layer does not guarantee every logging source complies.

Masking data after it has been written is only a secondary layer: regex patterns can miss new formats, and the sensitive original still sits on disk, backups, or log collectors. If a secret has been exposed, revoke or rotate the secret per incident procedure rather than merely changing display formatting.

### 6.3. Protecting Both Transport and Downloaded Copies

| Control layer | What to verify |
| --- | --- |
| Access point | Expose only needed endpoints; restrict network, identity, and read permissions |
| Transport | HTTPS with valid certificates; do not put credentials in URLs |
| Source file | Process account has only necessary file permissions; path managed by trusted config |
| Cache and proxy | Do not publicly cache log responses; check actual headers across the whole path |
| Local downloads | Protected directory; do not casually attach to tickets, Git, or shared folders |
| Access auditing | Record identity, timestamp, resource, and outcome as needed; do not log Authorization or full log bodies |
| Volume | Rate limits, request limits, and transfer budgets to avoid impacting the application |

Spring Security provides default cache-control headers. Verify the final response keeps an appropriate no-store policy, usually including `Cache-Control: no-store`; do not let a CDN or reverse proxy override it into public caching. That header also does not stop someone who downloaded the file from actively copying it. [Spring Security: Cache Control](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html#servlet-headers-cache-control).

Changing the management port, renaming paths, or restricting CORS does not replace authentication and authorization. In particular, CORS does not stop a client like curl from calling directly if network access and server-side permissions are open.

## 7. Diagnosing Common Outcomes

| Symptom | Check first |
| --- | --- |
| Endpoint not found or returns `404` | Right address/base path; endpoint enabled, exposed, and readable source file exists |
| `401` | Were credentials sent and accepted |
| `403` on GET | Does the authenticated identity have the right role and match the access policy |
| `200` despite sending Range | Did the header reach the app; does the handler support it; did a proxy alter request/response |
| `206` but garbled text at start/end | Did the range cut mid-UTF-8 character or mid-line |
| `416` | Is offset at/past end of file; was the file truncated, replaced, or rotated |
| Content is not the expected file | `external-file`, logging config, working directory, and target instance |
| New logs not appearing yet | Has the writer flushed to file; are you reading the right file/instance |

A single error code is not enough to pinpoint one unique cause. The security filter chain can block a request before Actuator processes it, and the application's error handling can change the final response.

In a multi-instance system behind a load balancer, two consecutive requests may read two different files. Do not carry an offset from instance A over to instance B and splice data; identify the log source or use a centralized platform with an appropriate query model.

## 8. Self-Check Practice Exercises

1. On the 17-byte file, send `Range: bytes=0-4`. Predict the status code, `Content-Range`, and byte count before running.
2. Change to `bytes=0-99`. Explain why an end beyond the file can still return valid data.
3. Read `bytes=-6`, then compare "last 6 bytes" with "last 6 lines".
4. Send a request with no password. Confirm that zero log bytes are returned.
5. On a separate test copy, change the file content after the first read. Explain why slices across two file versions must not be blindly concatenated.
6. Audit the application for anywhere that logs full headers or request bodies; determine how to prevent credentials from entering the file in the first place.

Cross-check against the sample file: item 1 is `206`, `bytes 0-4/17`, 5 bytes; item 2 can return `206`, `bytes 0-16/17`, 17 bytes on this lesson's MVC setup; item 3 returns `gamma` and LF. For every download, base conclusions on the HTTP status, headers, and actual received bytes.

Mastering this lesson means you can choose exact byte ranges, read responses accurately, keep offsets bound to the right file source, and explain why log-read permissions and data policies remain mandatory even when downloading only a small slice.
