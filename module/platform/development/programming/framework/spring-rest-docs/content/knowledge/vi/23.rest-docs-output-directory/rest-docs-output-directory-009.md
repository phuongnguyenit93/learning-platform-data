# Kiểm tra encoding và quyền ghi thư mục output

## 1. Vì sao encoding và quyền ghi ảnh hưởng đến snippet?

Spring REST Docs tạo snippet từ HTTP operation trong test. Ví dụ request có nội dung tiếng Việt:

```http
POST /api/products HTTP/1.1
Content-Type: application/json; charset=UTF-8

{
  "name": "Bàn phím cơ",
  "description": "Thiết bị dùng cho lập trình"
}
```

Nếu file snippet được ghi hoặc đọc bằng charset không phù hợp, nội dung có dấu có thể biến thành ký tự lỗi. Tài liệu Asciidoctor/Markdown sau đó hiển thị sai dù HTTP test vẫn pass.

Một vấn đề khác là tiến trình test không có quyền ghi vào output directory. Khi đó Spring REST Docs có thể thất bại lúc tạo snippet, hoặc lỗi chỉ xuất hiện ở CI/container dù chạy được trên máy developer.

Module **SPRING_REST_DOCS** tạo REST API documentation có thể kiểm chứng bằng HTTP tests với MockMvc, WebTestClient hoặc REST Assured. Test sinh snippet request, response, payload, parameter và header; sau đó biên soạn thành Asciidoctor/Markdown và đưa vào build/CI. Bài thuộc chương **Thư mục output**, hướng dẫn kiểm tra encoding và quyền ghi để quá trình tạo tài liệu ổn định trên các môi trường.

Sau bài học, bạn có thể:

1. Phân biệt charset của HTTP payload với encoding của file snippet.
2. Giữ nội dung tiếng Việt và Unicode nhất quán qua test, snippet và tài liệu render.
3. Kiểm tra output directory tồn tại, có thể ghi và có đủ dung lượng.
4. Xử lý khác biệt quyền truy cập giữa Windows, Linux, container và CI.
5. Chẩn đoán lỗi ghi file, file bị khóa và lỗi encoding.

## 2. Phân biệt HTTP charset và file encoding

| Lớp | Ví dụ | Điều khiển |
| --- | --- | --- |
| HTTP request body | Content-Type: application/json; charset=UTF-8 | Charset client/server dùng để diễn giải payload |
| HTTP response body | Content-Type: application/json; charset=UTF-8 | Charset response theo contract/framework |
| Java source file | UTF-8 | Compiler/IDE và cấu hình encoding source |
| Snippet file | request-body.adoc | Cách Spring REST Docs ghi file và công cụ đọc |
| Asciidoctor source/output | .adoc / HTML/PDF | Encoding source và renderer |

Một request có charset UTF-8 không tự bảo đảm mọi file sau đó được đọc bằng UTF-8. Ngược lại, snippet được lưu đúng UTF-8 cũng không sửa được payload đã bị giải mã sai trước khi REST Docs nhận operation.

### 2.1. UTF-8 cho nội dung đa ngôn ngữ

Với REST API hiện đại, UTF-8 là lựa chọn phổ biến cho JSON và tài liệu. Hãy thống nhất:

- Source Java/Kotlin và fixture JSON được lưu bằng UTF-8.
- Request/response test dùng nội dung Unicode thực tế.
- Build tool và renderer đọc source docs đúng encoding.
- Không chuyển file UTF-8 sang Windows-1252 hoặc charset mặc định của máy trong một bước trung gian.

JSON trao đổi qua HTTP thường dùng UTF-8. Không cần tự thêm BOM. Hãy để Content-Type và quy tắc của framework quyết định cách xử lý payload.

## 3. Kiểm tra encoding của fixture và test source

Tạo fixture JSON bằng UTF-8:

```json
{
  "name": "Bàn phím cơ",
  "description": "Bố cục tiếng Việt: có dấu, ký tự đặc biệt và emoji 🔧"
}
```

Test nên đọc fixture bằng charset được chỉ định rõ:

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

Files.readString(path, UTF_8) làm rõ cách đọc fixture. Nếu dùng new String(bytes) không truyền charset, kết quả phụ thuộc charset mặc định của JVM và có thể khác giữa developer workstation với CI.

### 3.1. Kiểm tra source encoding của Java

Với Gradle Java plugin:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
```

Với Maven Compiler Plugin:

```xml
<properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <maven.compiler.encoding>UTF-8</maven.compiler.encoding>
</properties>
```

Các cấu hình này kiểm soát việc compiler đọc source. Chúng không tự cấu hình charset cho mọi HTTP client hoặc mọi file do plugin khác tạo.

## 4. Kiểm tra snippet sau khi được sinh

Sau khi chạy test, mở một snippet chứa tiếng Việt:

```text
build/generated-snippets/product-create/request-body.adoc
```

Kiểm tra ký tự có dấu hiển thị đúng, emoji hoặc ký tự ngoài ASCII không biến thành dấu hỏi, JSON giữ nguyên dấu ngoặc/dấu nháy/escape và không xuất hiện ký tự thay thế Unicode.

Ví dụ nội dung đúng:

```json
{
  "name": "Bàn phím cơ",
  "description": "Thiết bị dùng cho lập trình"
}
```

Nếu snippet sai, xác định lỗi bắt đầu ở đâu: fixture trên đĩa, chuỗi Java sau khi đọc, HTTP operation, snippet sinh ra hay bước Asciidoctor. Đừng chỉ sửa font hoặc renderer khi bytes trong snippet đã sai.

### 4.1. Kiểm tra bytes của file

Với PowerShell, đọc nội dung theo UTF-8:

```powershell
Get-Content -LiteralPath "build/generated-snippets/product-create/request-body.adoc" -Encoding UTF8
```

Kiểm tra bytes đầu file:

```powershell
$bytes = [System.IO.File]::ReadAllBytes(
    "build/generated-snippets/product-create/request-body.adoc")
$bytes[0..([Math]::Min(15, $bytes.Length - 1))]
```

UTF-8 BOM, nếu có, thường bắt đầu bằng EF BB BF. BOM không phải yêu cầu bắt buộc của UTF-8. Không tự thêm BOM nếu renderer/toolchain không yêu cầu.

Trên Linux/macOS:

```bash
file -bi build/generated-snippets/product-create/request-body.adoc
xxd -l 16 build/generated-snippets/product-create/request-body.adoc
```

Công cụ nhận diện charset từ bytes chỉ đưa ra gợi ý; UTF-8 không BOM không có marker riêng. Kiểm tra bằng cách đọc theo UTF-8 và xác nhận nội dung mong đợi.

## 5. Quyền ghi output directory

Tiến trình chạy test cần có quyền traverse các thư mục cha, tạo thư mục identifier con, tạo và ghi file snippet, ghi đè file khi sinh lại, và xóa output cũ nếu build task thực hiện clean.

Ví dụ:

```text
build/
  generated-snippets/
    product-create/
      http-request.adoc
      http-response.adoc
```

Quyền ghi ở project root không bảo đảm mọi thư mục con đều có quyền ghi. Nếu generated directory được tạo trước bởi user hoặc container khác, owner/ACL có thể ngăn process hiện tại ghi file.

### 5.1. Không dùng quyền quá rộng làm cách sửa mặc định

Trên Linux, chmod -R 777 có thể khiến lỗi biến mất nhưng cấp quyền cho mọi user. Thay vào đó, xác định user/group chạy Gradle hoặc Maven, owner của output directory và cấp quyền ghi đúng user/group.

Ví dụ:

```bash
mkdir -p build/generated-snippets
chown -R "$(id -u):$(id -g)" build/generated-snippets
chmod -R u+rwX build/generated-snippets
```

Chỉ chạy chown khi user có quyền và thư mục này thực sự thuộc workspace của build. Không đổi owner của thư mục dùng chung hoặc ngoài workspace để xử lý lỗi cục bộ.

## 6. Kiểm tra quyền trên Windows và Linux

### 6.1. Windows

PowerShell có thể kiểm tra thư mục:

```powershell
$outputDir = "build/generated-snippets"
Test-Path -LiteralPath $outputDir
Get-Acl -LiteralPath $outputDir | Format-List
```

Nếu chưa có thư mục:

```powershell
New-Item -ItemType Directory -Force -Path $outputDir
```

Quyền NTFS được điều khiển bởi ACL, user và group của process. Một terminal có quyền ghi không có nghĩa service runner hoặc CI agent chạy bằng tài khoản khác cũng có quyền ghi.

### 6.2. Linux

Kiểm tra owner, mode và quyền truy cập:

```bash
id
ls -ld build build/generated-snippets
test -w build/generated-snippets && echo "writable"
```

Nếu thư mục chưa tồn tại, kiểm tra quyền ghi/traverse ở thư mục cha trước khi tạo. test -w là kiểm tra hữu ích nhưng không bảo đảm ghi chắc chắn thành công nếu filesystem read-only, quota hết hoặc quyền bị thay đổi giữa lúc kiểm tra và ghi.

## 7. Kiểm tra ghi file thực tế

Có thể tạo file tạm trong output directory, ghi và đọc lại bằng UTF-8 rồi xóa:

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

Chỉ dùng probe trong test support hoặc diagnostic task có chủ đích. Không chạy đồng thời với test khác nếu có thể đụng cùng file; file tạm nên có tên duy nhất.

Probe kiểm tra quyền tạo/ghi/đọc/xóa file tại thời điểm chạy. Nó không thay thế việc chạy REST Docs thật, vì snippet writer còn cần tạo thư mục identifier và nhiều file.

## 8. Nguyên nhân khiến CI không ghi được snippet

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| AccessDeniedException | User CI không có quyền ghi hoặc xóa output | Kiểm tra identity và ACL/owner |
| Permission denied trên Linux | Thiếu quyền traverse/write hoặc filesystem read-only | Kiểm tra id, ls -ld, mount options |
| FileAlreadyExistsException | Nhiều task/test cùng tạo path hoặc race | Phân vùng identifier và tuần tự hóa producer |
| NoSuchFileException | Parent directory chưa tồn tại hoặc path sai | Tạo output root và kiểm tra cấu hình |
| Read-only file system | Workspace hoặc mount read-only | Chọn workspace/output volume writable |
| No space left on device | Disk/quota/inode hết | Kiểm tra dung lượng và dọn đúng generated outputs |
| File bị khóa trên Windows | Process khác giữ handle hoặc antivirus/indexer can thiệp | Đóng process giữ file và kiểm tra runner |
| Snippet có ký tự lỗi | Fixture/source bị đọc bằng charset mặc định hoặc payload sai charset | Đọc UTF-8 tường minh và kiểm tra từng bước |
| Asciidoctor hiển thị sai dấu | Source/snippet bị giải mã sai hoặc renderer dùng encoding khác | Kiểm tra bytes và cấu hình encoding renderer |

## 9. Quyền ghi và parallel test

Nhiều test có thể chạy đồng thời. Nếu hai test cùng dùng document identifier, chúng có thể ghi vào cùng file snippet. Đây không chỉ là vấn đề quyền mà còn là race condition.

Identifier trùng:

```java
document("product-detail")
```

Nếu nhiều test cùng sinh identifier này với payload khác nhau, file cuối không ổn định. Hãy phân vùng theo class/method/step:

```java
document("{class-name}/{method-name}/{step}")
```

Phân vùng identifier giảm xung đột giữa test. Nếu nhiều Gradle test task hoặc CI job cùng ghi vào một output root, cần tách output directory theo task/job hoặc chạy producer theo thứ tự.

## 10. Cấu hình encoding và output trong build

### 10.1. Gradle

Ví dụ:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}

tasks.test {
    systemProperty 'file.encoding', 'UTF-8'
    outputs.dir(layout.buildDirectory.dir('generated-snippets'))
}
```

options.encoding cấu hình charset đọc Java source. file.encoding đặt charset mặc định của JVM cho process test; đây là biện pháp hỗ trợ code cũ còn dùng API dựa vào default charset. Code mới vẫn nên chỉ định charset rõ ràng khi đọc/ghi file.

### 10.2. Maven

```xml
<properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
    <maven.compiler.encoding>UTF-8</maven.compiler.encoding>
</properties>
```

Các property này giúp Maven plugin/compiler biết encoding cho source/report. Kiểm tra thêm cấu hình plugin Asciidoctor và môi trường JVM nếu tài liệu render vẫn sai.

## 11. CI: kiểm tra encoding và writable output

Một pipeline có thể:

1. Xác định user chạy job.
2. Tạo output directory trong workspace.
3. Kiểm tra khả năng tạo và ghi file.
4. Chạy HTTP documentation tests.
5. Đọc một snippet có Unicode theo UTF-8 và so sánh nội dung mong đợi.
6. Chạy Asciidoctor/Markdown build.
7. Lưu artifact và log khi có lỗi.

Ví dụ bash smoke check:

```bash
set -eu
OUT="build/generated-snippets"
mkdir -p "$OUT"
PROBE="$OUT/.write-check-$$"
printf '%s' 'Spring REST Docs: tiếng Việt' > "$PROBE"
grep -q 'tiếng Việt' "$PROBE"
rm "$PROBE"
```

Ví dụ PowerShell:

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

Probe phải chạy dưới cùng user và trong cùng workspace với test task. Nếu probe pass nhưng test vẫn không ghi được, kiểm tra output directory thực tế Spring REST Docs đang sử dụng.

## 12. Lỗi thường gặp và cách chẩn đoán

| Dấu hiệu | Kiểm tra đầu tiên |
| --- | --- |
| Developer ghi được, CI không ghi được | User/service account, workspace mount và ACL |
| Tạo được root nhưng không tạo được identifier con | Quyền traverse/write trên root và thư mục con |
| File snippet có nội dung sai ngay sau test | Fixture bytes, source encoding, cách đọc request body |
| Snippet đúng nhưng HTML sai | Encoding Asciidoctor source/renderer hoặc bước copy |
| Test chạy lại báo file đang được dùng | Parallel writer, IDE preview, antivirus hoặc process cũ |
| Windows pass nhưng Linux fail | Phân biệt hoa/thường của path, permission bit, ký tự tên file |
| Linux pass nhưng Windows fail | ACL, file lock, path length hoặc tên file không hợp lệ |
| Lỗi chỉ xuất hiện khi clean | Build process không có quyền xóa file output cũ |

Khi điều tra, ghi nhận path tuyệt đối của output directory, user chạy test, exception đầy đủ và task đang tạo snippet. Tránh khắc phục bằng cách cấp quyền toàn bộ workspace hoặc chuyển output vào thư mục hệ thống.

## 13. Bài tập thực hành

Tạo endpoint nhận sản phẩm có tên tiếng Việt:

```json
{
  "name": "Bàn phím cơ",
  "description": "Thiết bị dùng cho lập trình"
}
```

Thực hiện:

1. Lưu fixture bằng UTF-8 và đọc bằng StandardCharsets.UTF_8.
2. Viết MockMvc test gửi request JSON, document request/response.
3. Kiểm tra snippet chứa đúng các chuỗi có dấu.
4. Chạy test bằng user có quyền ghi output directory; kiểm tra owner/ACL.
5. Thử chạy với output directory read-only trong môi trường test riêng để nhận diện lỗi permission.
6. Cấu hình Gradle hoặc Maven encoding rõ ràng.
7. Thêm smoke check writable/UTF-8 vào CI trước bước Asciidoctor.

**Tiêu chí hoàn thành:** Snippet giữ nguyên Unicode; test ghi được vào đúng output root; CI phát hiện permission/encoding problem với log đủ rõ; source docs không bị sửa bởi bước clean hoặc probe.

## 14. Ghi nhớ

Encoding của HTTP payload, Java source, snippet và tài liệu render là các lớp riêng. Dùng UTF-8 nhất quán, chỉ định charset khi đọc/ghi fixture và kiểm tra nội dung snippet sau test. Output directory phải được process chạy build tạo thư mục, ghi, ghi đè và clean khi cần. Trên Windows kiểm tra ACL; trên Linux kiểm tra user, owner, mode và filesystem. Phân vùng identifier để tránh parallel writer, thêm smoke check writable/UTF-8 vào CI và chỉ thay đổi quyền ở đúng generated output directory.

### Tài liệu tham khảo

- [Java — StandardCharsets](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/StandardCharsets.html)
- [Java — Files.readString and writeString](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html)
- [Gradle — CompileOptions.encoding](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.compile.CompileOptions.html)
- [Maven — POM encoding properties](https://maven.apache.org/pom.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/docs/current/reference/htmlsingle/)
