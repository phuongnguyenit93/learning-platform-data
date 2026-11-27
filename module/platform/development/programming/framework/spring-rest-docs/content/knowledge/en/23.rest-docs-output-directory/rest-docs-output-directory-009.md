# Checking Encoding and Write Permissions for the Output Directory

## 1. Why Do Encoding and Write Permissions Affect Snippets?

Spring REST Docs generates snippets from HTTP operations in tests. For example, a request with Vietnamese content:

```http
POST /api/products HTTP/1.1
Content-Type: application/json; charset=UTF-8

{
  "name": "Bàn phím cơ",
  "description": "Thiết bị dùng cho lập trình"
}
```

If snippet files are written or read using an incompatible charset, accented characters can turn into garbled characters. Asciidoctor/Markdown documentation will then render incorrectly even though the HTTP test still passes.

Another issue is when the test process lacks write permissions to the output directory. In that case, Spring REST Docs may fail when creating snippets, or the failure may appear only in CI/containers even though it passes on a developer machine.

The **SPRING_REST_DOCS** module produces verifiable REST API documentation using HTTP tests with MockMvc, WebTestClient, or REST Assured. Tests generate request, response, payload, parameter, and header snippets; these are then compiled into Asciidoctor/Markdown and integrated into build/CI. This lesson belongs to the **Output Directory** chapter and explains how to verify encoding and write permissions so documentation generation remains reliable across environments.

After this lesson, you will be able to:

1. Distinguish the HTTP payload charset from snippet file encoding.
2. Keep Vietnamese and Unicode content consistent across tests, snippets, and rendered documentation.
3. Verify that the output directory exists, is writable, and has sufficient disk space.
4. Handle permission differences across Windows, Linux, containers, and CI.
5. Diagnose file-write errors, locked files, and encoding issues.

## 2. Distinguishing HTTP Charset and File Encoding

| Layer | Example | Controlled By |
| --- | --- | --- |
| HTTP request body | `Content-Type: application/json; charset=UTF-8` | Charset used by client/server to interpret the payload |
| HTTP response body | `Content-Type: application/json; charset=UTF-8` | Response charset per contract/framework |
| Java source file | `UTF-8` | Compiler/IDE and source encoding configuration |
| Snippet file | `request-body.adoc` | How Spring REST Docs writes files and tools read them |
| Asciidoctor source/output | `.adoc` / HTML/PDF | Source and renderer encoding |

A request with a UTF-8 charset does not automatically guarantee that every downstream file is read as UTF-8. Conversely, a snippet saved properly as UTF-8 cannot fix a payload that was decoded incorrectly before REST Docs received the operation.

### 2.1. UTF-8 for Multilingual Content

For modern REST APIs, UTF-8 is the standard choice for JSON and documentation. Keep everything aligned:

- Java/Kotlin sources and JSON fixtures are saved as UTF-8.
- Request/response tests use realistic Unicode content.
- Build tools and renderers read documentation sources with the proper encoding.
- Do not convert UTF-8 files to Windows-1252 or the machine's default charset in an intermediate step.

JSON exchanged over HTTP normally uses UTF-8. There is no need to add a BOM manually. Let `Content-Type` and framework rules determine how payloads are handled.

## 3. Checking Encoding of Fixtures and Test Sources

Create the JSON fixture in UTF-8:

```json
{
  "name": "Bàn phím cơ",
  "description": "Bố cục tiếng Việt: có dấu, ký tự đặc biệt và emoji 🔧"
}
```

Tests should read fixtures with an explicitly specified charset:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

String requestBody = Files.readString(
        Path.of("src/test/resources/fixtures/product-create.json"),
        StandardCharsets.UTF_8);

mockMvc.perform(post("/api/products")
        .contentType(MediaType.APPLICATION_JSON)
        .characterEncoding(StandardCharsets.UTF_8.name())
        .content(requestBody))
    .andExpect(status().isCreated());
```

`Files.readString(path, UTF_8)` makes fixture reading explicit. Using `new String(bytes)` without a charset depends on the JVM's default charset and can differ between a developer workstation and CI.

### 3.1. Checking Java Source Encoding

With the Gradle Java plugin:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
```

With the Maven Compiler Plugin:

```xml
<properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <maven.compiler.encoding>UTF-8</maven.compiler.encoding>
</properties>
```

These settings control how the compiler reads source files. They do not automatically configure the charset for every HTTP client or every file produced by other plugins.

## 4. Checking Snippets After Generation

After running tests, open a snippet containing Vietnamese text:

```text
build/generated-snippets/product-create/request-body.adoc
```

Verify that accented characters render properly, emojis or non-ASCII characters do not turn into question marks, JSON preserves brackets/quotes/escapes, and no Unicode replacement characters appear.

Example of valid content:

```json
{
  "name": "Bàn phím cơ",
  "description": "Thiết bị dùng cho lập trình"
}
```

If a snippet is corrupted, identify where the error starts: the fixture on disk, the Java string after reading, the HTTP operation, the generated snippet, or the Asciidoctor step. Do not just change fonts or renderer settings when the bytes in the snippet are already wrong.

### 4.1. Inspecting File Bytes

With PowerShell, read content as UTF-8:

```powershell
Get-Content -LiteralPath "build/generated-snippets/product-create/request-body.adoc" -Encoding UTF8
```

Inspect the leading bytes of the file:

```powershell
$bytes = [System.IO.File]::ReadAllBytes(
    "build/generated-snippets/product-create/request-body.adoc")
$bytes[0..([Math]::Min(15, $bytes.Length - 1))]
```

A UTF-8 BOM, if present, starts with `EF BB BF`. A BOM is not required by UTF-8. Do not add a BOM manually unless your renderer or toolchain requires it.

On Linux/macOS:

```bash
file -bi build/generated-snippets/product-create/request-body.adoc
xxd -l 16 build/generated-snippets/product-create/request-body.adoc
```

Tools that guess charsets from bytes only provide hints; UTF-8 without a BOM has no dedicated marker. Verify by reading the file as UTF-8 and confirming the expected text.

## 5. Output Directory Write Permissions

The test-running process needs permission to traverse parent directories, create identifier subdirectories, create and write snippet files, overwrite files on regeneration, and delete old outputs if the build task performs a clean.

For example:

```text
build/
  generated-snippets/
    product-create/
      http-request.adoc
      http-response.adoc
```

Write permission on the project root does not guarantee every subdirectory is writable. If a generated directory was previously created by another user or container, ownership/ACLs can prevent the current process from writing files.

### 5.1. Do Not Use Overly Broad Permissions as a Default Fix

On Linux, `chmod -R 777` may make the error disappear, but it grants permissions to all users. Instead, identify the user/group running Gradle or Maven and the owner of the output directory, and grant write permission to the proper user/group.

For example:

```bash
mkdir -p build/generated-snippets
chown -R "$(id -u):$(id -g)" build/generated-snippets
chmod -R u+rwX build/generated-snippets
```

Run `chown` only when the user has permission and the directory genuinely belongs to the build workspace. Do not change ownership of shared directories or folders outside the workspace to fix a local error.

## 6. Checking Permissions on Windows and Linux

### 6.1. Windows

PowerShell can inspect the directory:

```powershell
$outputDir = "build/generated-snippets"
Test-Path -LiteralPath $outputDir
Get-Acl -LiteralPath $outputDir | Format-List
```

If the directory does not exist yet:

```powershell
New-Item -ItemType Directory -Force -Path $outputDir
```

NTFS permissions are governed by ACLs and the process's user and group. Having write access in an interactive terminal does not mean a service runner or CI agent running under a different account also has write access.

### 6.2. Linux

Check owner, mode, and access permissions:

```bash
id
ls -ld build build/generated-snippets
test -w build/generated-snippets && echo "writable"
```

If the directory does not exist yet, check write/traverse permissions on the parent directory before creating it. `test -w` is a useful check, but it does not guarantee writes will succeed if the filesystem is read-only, disk quota is exhausted, or permissions change between the check and the write.

## 7. Testing Actual File Writes

You can create a temporary file in the output directory, write and read it back as UTF-8, and delete it:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path outputDir = Path.of("build/generated-snippets");
Files.createDirectories(outputDir);

Path probe = Files.createTempFile(outputDir, "write-check-", ".tmp");
try {
    Files.writeString(probe, "Spring REST Docs UTF-8: tiếng Việt",
            StandardCharsets.UTF_8);
    String content = Files.readString(probe, StandardCharsets.UTF_8);
    if (!content.contains("tiếng Việt")) {
        throw new IllegalStateException("UTF-8 readback mismatch");
    }
} finally {
    Files.deleteIfExists(probe);
}
```

Use such a probe only in test support or an intentional diagnostic task. Do not run it concurrently with other tests if it could collide on the same file; temporary files should have unique names.

A probe verifies file creation, writing, reading, and deletion at runtime. It does not replace running REST Docs itself, since the snippet writer also needs to create identifier directories and multiple files.

## 8. Reasons Why CI Fails to Write Snippets

| Symptom | Common Cause | How to Address |
| --- | --- | --- |
| `AccessDeniedException` | CI user lacks permission to write or delete outputs | Check identity and ACL/owner |
| `Permission denied` on Linux | Missing traverse/write permission or read-only filesystem | Check `id`, `ls -ld`, mount options |
| `FileAlreadyExistsException` | Multiple tasks/tests create the same path or race condition | Partition identifiers and serialize producers |
| `NoSuchFileException` | Parent directory does not exist or wrong path | Create output root and check configuration |
| `Read-only file system` | Workspace or mount is read-only | Choose a writable workspace/output volume |
| `No space left on device` | Disk/quota/inodes exhausted | Check disk usage and clean generated outputs properly |
| Locked file on Windows | Another process holds a handle or antivirus/indexer interferes | Close the holding process and inspect the runner |
| Snippet has garbled characters | Fixture/source read with default charset or payload has wrong charset | Read UTF-8 explicitly and inspect each step |
| Asciidoctor renders corrupted accents | Source/snippet decoded wrongly or renderer uses a different encoding | Inspect raw bytes and renderer encoding configuration |

## 9. Write Permissions and Parallel Tests

Multiple tests can run concurrently. If two tests share the same document identifier, they can write to the same snippet file. This is not just a permission problem, but also a race condition.

Duplicate identifier:

```java
document("product-detail")
```

If multiple tests produce this identifier with different payloads, the final file becomes non-deterministic. Partition by class/method/step:

```java
document("{class-name}/{method-name}/{step}")
```

Partitioning identifiers reduces conflicts between tests. If multiple Gradle test tasks or CI jobs write to the same output root, separate output directories per task/job or run producers sequentially.

## 10. Configuring Encoding and Output in the Build

### 10.1. Gradle

Example:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}

tasks.test {
    systemProperty 'file.encoding', 'UTF-8'
    outputs.dir(layout.buildDirectory.dir('generated-snippets'))
}
```

`options.encoding` configures the charset for reading Java sources. `file.encoding` sets the JVM's default charset for the test process; this helps legacy code that still relies on default-charset APIs. New code should still specify the charset explicitly when reading or writing files.

### 10.2. Maven

```xml
<properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
    <maven.compiler.encoding>UTF-8</maven.compiler.encoding>
</properties>
```

These properties inform Maven plugins and the compiler of the encoding for sources and reports. Also check the Asciidoctor plugin configuration and JVM environment if rendered documentation still appears wrong.

## 11. CI: Checking Encoding and Writable Output

A pipeline can:

1. Identify the user running the job.
2. Create the output directory in the workspace.
3. Verify the ability to create and write files.
4. Run HTTP documentation tests.
5. Read a snippet containing Unicode as UTF-8 and compare against expected content.
6. Run the Asciidoctor/Markdown build.
7. Save artifacts and logs on failure.

Bash smoke check example:

```bash
set -eu
OUT="build/generated-snippets"
mkdir -p "$OUT"
PROBE="$OUT/.write-check-$$"
printf '%s' 'Spring REST Docs: tiếng Việt' > "$PROBE"
grep -q 'tiếng Việt' "$PROBE"
rm "$PROBE"
```

PowerShell example:

```powershell
$out = "build/generated-snippets"
New-Item -ItemType Directory -Force -Path $out | Out-Null
$probe = Join-Path $out ".write-check-$PID.txt"
try {
    [System.IO.File]::WriteAllText(
        $probe,
        "Spring REST Docs: tiếng Việt",
        [System.Text.UTF8Encoding]::new($false))
    $content = [System.IO.File]::ReadAllText(
        $probe,
        [System.Text.Encoding]::UTF8)
    if (-not $content.Contains("tiếng Việt")) {
        throw "UTF-8 readback mismatch"
    }
}
finally {
    Remove-Item -LiteralPath $probe -Force -ErrorAction SilentlyContinue
}
```

The probe must run under the same user and inside the same workspace as the test task. If the probe passes but tests still cannot write, inspect the actual output directory Spring REST Docs is using.

## 12. Common Errors and Diagnosis

| Symptom | First Check |
| --- | --- |
| Works for developer, fails in CI | User/service account, workspace mount, and ACLs |
| Root directory can be created, but identifier subdirectories fail | Traverse/write permissions on root and subdirectories |
| Snippet file has corrupted text right after tests | Fixture bytes, source encoding, how request body is read |
| Snippet is right, but HTML is corrupted | Asciidoctor source/renderer encoding or copy step |
| Re-running tests reports file in use | Parallel writers, IDE preview, antivirus, or leftover process |
| Passes on Windows, fails on Linux | Path case sensitivity, permission bits, filename characters |
| Passes on Linux, fails on Windows | ACLs, file locks, path length, or invalid filename characters |
| Error occurs only during `clean` | Build process lacks permission to delete old output files |

When investigating, record the absolute path of the output directory, the user running the tests, the full exception, and the task generating snippets. Avoid fixing it by opening permissions on the entire workspace or moving outputs into a system directory.

## 13. Practice Exercise

Create an endpoint accepting a product with a Vietnamese name:

```json
{
  "name": "Bàn phím cơ",
  "description": "Thiết bị dùng cho lập trình"
}
```

Steps:

1. Save the fixture in UTF-8 and read it with `StandardCharsets.UTF_8`.
2. Write a MockMvc test sending the JSON request and documenting request/response.
3. Verify that the generated snippets preserve all accented strings accurately.
4. Run the tests as a user with write permissions on the output directory; inspect owner/ACLs.
5. Test running against a read-only output directory in an isolated test environment to recognize permission errors.
6. Configure Gradle or Maven encoding explicitly.
7. Add a writable/UTF-8 smoke check to CI before the Asciidoctor step.

**Completion criteria:** Snippets preserve Unicode intact; tests write to the exact output root; CI catches permission/encoding issues with clear logs; documentation sources are unaffected by the clean or probe steps.

## 14. Key Takeaways

The encodings of HTTP payloads, Java sources, snippets, and rendered documentation are distinct layers. Use UTF-8 consistently, specify the charset explicitly when reading/writing fixtures, and inspect snippet contents after tests. The build process must be able to create directories, write, overwrite, and clean the output directory as needed. On Windows inspect ACLs; on Linux inspect user, owner, mode, and filesystem. Partition identifiers to avoid parallel writers, add a writable/UTF-8 smoke check in CI, and adjust permissions only on the generated output directory.

### References

- [Java — StandardCharsets](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/StandardCharsets.html)
- [Java — Files.readString and writeString](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html)
- [Gradle — CompileOptions.encoding](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.compile.CompileOptions.html)
- [Maven — POM encoding properties](https://maven.apache.org/pom.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/docs/current/reference/htmlsingle/)
