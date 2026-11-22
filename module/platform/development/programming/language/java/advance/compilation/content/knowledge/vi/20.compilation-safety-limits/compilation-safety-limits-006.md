# Tránh lộ đường dẫn và dữ liệu nhạy cảm qua diagnostics khi biên dịch Java

> **Ngữ cảnh:** Java Advance – compilation → An toàn và giới hạn. Tài liệu dành cho người xây dựng hệ thống gọi `javac`, Java Compiler API, annotation processors hoặc pipeline CI. Mục tiêu là giữ được thông tin chẩn đoán **cần thiết để sửa lỗi** mà không vô tình công bố đường dẫn máy, tên người dùng, cấu trúc repository, nội dung source, thông tin khách hàng, token và bí mật trong log.

## 1. Vấn đề: lỗi biên dịch cũng là một kênh rò rỉ dữ liệu

Diagnostic là thông tin mà trình biên dịch phát ra trong quá trình đọc, phân tích và tạo mã. Nó thường gồm **mức độ**, **vị trí**, **mã/thông điệp lỗi** và **nguồn liên quan**. Thông tin đó hữu ích cho lập trình viên, nhưng nó có thể chứa hoặc khiến người đọc suy ra:

- Đường dẫn tuyệt đối: `/home/alice/projects/client-a/private/src/...`, `C:\Users\Alice\work\confidential\...`, thư mục tạm của CI, tên home directory và workspace.
- Tên package, class, method, annotation, ký hiệu Java hoặc giá trị cấu hình mang tên khách hàng/dự án nhạy cảm.
- Một phần **dòng mã nguồn lỗi** do `javac` command-line hoặc công cụ hiển thị log in ra; dòng đó có thể chứa string literal, endpoint nội bộ, token giả định được hardcode hoặc dữ liệu thử nghiệm.
- Thông tin trong message do **annotation processor**, compiler plugin, code generator hoặc file manager tự tạo, vốn có thể ghi bất kỳ chuỗi nào.
- Stack trace và exception message chứa URI, đường dẫn filesystem, compiler options, classpath/module path hoặc exception từ công cụ build.
- Metadata CI: tên branch, artifact path, tên runner, environment variable đã vô tình được nội suy vào command, log và báo cáo.

Ví dụ một dòng báo lỗi dạng text (minh họa, **không phải output chuẩn cố định**):

```text
/home/alice/projects/client-a/private/src/demo/Bad.java:4:
error: incompatible types: java.lang.String cannot be converted to int
    int number = "TRAINING_SECRET_MARKER";
                 ^
```

Chỉ một diagnostic copy nguyên văn lên web UI, Slack, issue tracker hoặc CI log đã có thể làm lộ cả **đường dẫn riêng tư** và **nội dung dòng source**. Chuỗi `TRAINING_SECRET_MARKER` ở đây là marker **hoàn toàn giả**, không phải credential thật. Cấm sử dụng secret thật để minh họa hoặc thử redaction.

**Rủi ro chính:** hệ thống chẩn đoán chạy với quyền truy cập source/build environment nhưng kết quả có thể được đưa vào **kênh ít tin cậy hơn** (log public, PR của fork, dashboard khách hàng, support ticket, telemetry bên thứ ba). Đây là luồng dữ liệu cần thiết kế theo nguyên tắc **least disclosure**.

## 2. Phân loại dữ liệu trước khi quyết định log gì

| Thành phần | Giá trị chẩn đoán | Rủi ro | Chiến lược hiển thị an toàn |
| --- | --- | --- | --- |
| `Diagnostic.Kind` | Phân biệt `ERROR`, `WARNING`, `NOTE` | Thường thấp | Cho phép enum thuộc tập cố định |
| `getLineNumber()`, `getColumnNumber()` | Khoanh vùng lỗi | Có thể suy ra cấu trúc source trong bối cảnh đặc biệt | Cho phép số nguyên hợp lệ, dùng `?` nếu không có vị trí |
| `getSource().toUri()` | Xác định file | Absolute path, tên user, tenant, workspace | **Ánh xạ URI thật → source ID được duyệt** |
| `getCode()` | Nhóm lỗi trình biên dịch | Implementation-dependent; có thể là dữ liệu không dự đoán ở công cụ bên thứ ba | Chỉ cho phép mã thuộc allowlist khi thật sự cần |
| `getMessage(Locale)` | Gợi ý sửa lỗi | Có thể chứa class/variable/value/paths do source hoặc tool cung cấp | Mặc định không xuất raw message ra kênh công khai |
| `Diagnostic.toString()` | Render nhanh diagnostic | Không kiểm soát được định dạng và nội dung | Không dùng làm bản ghi an toàn |
| Dòng source/caret/snippet | Nhìn rõ biểu thức gây lỗi | Có thể chứa source code, credential, thông tin kinh doanh | Chỉ hiện trong kênh riêng có quyền, sau kiểm tra và lọc |
| Exceptions/stack traces | Điều tra compiler crash | Đường dẫn, classpath, options và giá trị do plugin ghi | Thông điệp an toàn cho người xem; bằng chứng gốc ở kênh bảo vệ |
| Build stdout/stderr | Điều tra pipeline | Có thể là raw compiler output, `-verbose`, lệnh shell | Thu/kiểm soát trước khi public hoặc hạn chế quyền truy cập |

**Không đánh đồng tất cả logs.** Một log nội bộ có phân quyền mạnh, retention và audit access có thể chứa nhiều dữ liệu chẩn đoán hơn log dành cho người gửi source. Nhưng ngay cả log nội bộ cũng không nên chứa password/token/secret nếu có cách tránh; quyền đọc log thường rộng hơn quyền đọc secret/source.

Khuyến nghị đi theo thứ tự: **giảm dữ liệu ở nguồn → tạo sự kiện có cấu trúc từ trường an toàn → lọc/escape ở lớp xuất → giới hạn người đọc và thời hạn lưu**. Regex thay chuỗi sau khi đã public log là quá muộn.

## 3. Java Compiler API trả về những gì?

Java 17 cung cấp API trong `javax.tools` (module `java.compiler`):

- `ToolProvider.getSystemJavaCompiler()` trả một compiler hoặc `null` nếu runtime không có system Java compiler.
- `JavaCompiler.getTask(...)` tạo một compilation task; tham số `DiagnosticListener` giúp nhận diagnostics ở dạng cấu trúc.
- `DiagnosticCollector<JavaFileObject>` là listener có sẵn; gọi `getDiagnostics()` sau `task.call()`.
- `Diagnostic.getKind()` cho biết mức độ; `getSource()` có thể trả `null`; `getLineNumber()` và `getColumnNumber()` là tọa độ **1-based**, hoặc `Diagnostic.NOPOS` (giá trị -1) nếu không có vị trí.
- `getPosition()/getStartPosition()/getEndPosition()` là offset ký tự, **không phải offset byte UTF-8**. Nếu không có vị trí thì trả `NOPOS`.
- `getCode()` có thể `null` và phụ thuộc implementation; `getMessage(Locale)` là thông điệp được địa phương hóa, cũng phụ thuộc compiler.

Một API có kiểu dữ liệu rõ ràng **không có nghĩa mọi trường đều an toàn để xuất**. Đặc biệt:

```java
// DANGEROUS trong public build log: nguồn/message có thể nhạy cảm.
System.out.println(diagnostic);
System.out.println(diagnostic.getMessage(Locale.ROOT));
System.out.println(diagnostic.getSource().toUri());
```

Đây là **đoạn minh họa hành vi không nên áp dụng**, không phải chương trình độc lập. `Locale.ROOT` có thể giảm khác biệt ngôn ngữ nhưng **không xóa dữ liệu nhạy cảm** khỏi message. `toString()` không có hợp đồng bảo mật.

Lược đồ truyền dữ liệu an toàn:

```text
Source/Compiler/Processor
         │
         ▼
DiagnosticCollector (raw, trong vùng tin cậy)
         │
         ▼
Policy + source URI allowlist + chọn trường an toàn
         │
         ▼
Event có cấu trúc: kind / logicalSourceId / line / column / buildId
         │
         ├── Public CI / PR UI: event đã giới hạn
         │
         └── Debug bảo vệ: dữ liệu bổ sung nếu thật sự cần, có phân quyền
```

**Ranh giới quan trọng:** gọi `getMessage()` rồi dùng `replaceAll(...)` có thể để sót secret không khớp mẫu, đường dẫn đã URL-encoded, chuỗi Unicode, JSON escape hoặc nội dung do processor tùy ý viết. Với log public, dùng **allowlist** trường xuất phát từ dữ liệu có cấu trúc.

## 4. Bài thực hành Java 17+: xuất diagnostic an toàn

Ta cố ý tạo một source không hợp lệ, đặt nó dưới **URI mô phỏng đường dẫn riêng tư**, chứa một marker giả. Collector nhận `ERROR` nhưng bản ghi công khai chỉ gồm:

- Loại lỗi `ERROR`.
- Một **tên file logic đã duyệt**, độc lập đường dẫn vật lý.
- Số dòng của diagnostic.

Chương trình sẽ tự assert rằng bản ghi không chứa đường dẫn nhạy cảm giả lập và marker giả. **Không có secret thật** được dùng.

### 4.1. File `SafeCompilerDiagnostics.java` đầy đủ

```java
import java.io.StringWriter;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class SafeCompilerDiagnostics {
    private static final String FAKE_MARKER = "TRAINING_SECRET_MARKER";
    private static final String PRIVATE_DIR = "/private-workspace/";
    private static final URI ORIGINAL_URI = URI.create(
            "string:///home/alice/private-workspace/demo/Broken.java");

    private static final class MemorySource extends SimpleJavaFileObject {
        private final String source;

        MemorySource(URI uri, String source) {
            super(uri, Kind.SOURCE);
            this.source = source;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return source;
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Requires a full JDK");
        }

        String sourceText = """
                package demo;
                class Broken {
                    void test() {
                        int number = "TRAINING_SECRET_MARKER";
                    }
                }
                """;
        JavaFileObject source = new MemorySource(ORIGINAL_URI, sourceText);
        Map<URI, String> aliases = Map.of(
                source.toUri(), "src/main/java/demo/Broken.java");
        DiagnosticCollector<JavaFileObject> collector =
                new DiagnosticCollector<>();
        StringWriter internalOutput = new StringWriter();

        boolean succeeded;
        try (StandardJavaFileManager manager =
                 compiler.getStandardFileManager(
                         null, Locale.ROOT, StandardCharsets.UTF_8)) {
            succeeded = Boolean.TRUE.equals(compiler.getTask(
                    internalOutput,
                    manager,
                    collector,
                    List.of("--release", "17",
                            "-encoding", "UTF-8", "-proc:none"),
                    null,
                    List.of(source)).call());
        }

        Diagnostic<? extends JavaFileObject> expected =
                collector.getDiagnostics().stream()
                        .filter(d -> d.getKind() == Diagnostic.Kind.ERROR)
                        .filter(d -> d.getLineNumber() == 4)
                        .filter(d -> d.getSource() != null)
                        .findFirst()
                        .orElseThrow(() -> new AssertionError(
                                "Expected ERROR at line 4"));
        if (succeeded) {
            throw new AssertionError("Invalid source compiled");
        }

        String sourceId = aliases.getOrDefault(
                expected.getSource().toUri(), "<unknown-source>");
        long line = expected.getLineNumber();
        String safeRecord = expected.getKind() + " " + sourceId
                + ":" + (line == Diagnostic.NOPOS ? "?" : line);

        boolean leaked = safeRecord.contains(FAKE_MARKER)
                || safeRecord.contains(PRIVATE_DIR)
                || safeRecord.contains("home/alice");
        if (leaked) {
            throw new AssertionError("Private data entered public log");
        }
        System.out.println("Compilation successful: " + succeeded);
        System.out.println("Diagnostic: " + safeRecord);
        System.out.println("Private data leaked: " + leaked);
    }
}
```

### 4.2. Biên dịch và chạy

Lưu file dưới encoding UTF-8 **không BOM**. Tại thư mục chứa file, dùng JDK 17+:

```bash
javac --release 17 -encoding UTF-8 -proc:none SafeCompilerDiagnostics.java
java SafeCompilerDiagnostics
```

**Stdout đã kiểm thử trên OpenJDK 24.0.2 với `--release 17`:**

```text
Compilation successful: false
Diagnostic: ERROR src/main/java/demo/Broken.java:4
Private data leaked: false
```

Đừng coi `Compilation successful: false` là failure của **test harness**: đây là kết quả **đúng mong đợi** của compilation task cho một source cố ý sai kiểu. Chương trình `SafeCompilerDiagnostics` kết thúc thành công nếu tất cả assertions đạt. Khi thay code source cho hợp lệ hoặc diagnostics không còn ở dòng 4, chương trình sẽ ném lỗi.

### 4.3. Những điểm thiết kế quan trọng

1. `MemorySource` có URI `string:///home/alice/private-workspace/demo/Broken.java`, chứa đường dẫn nhạy cảm **giả lập**. Mục đích là chứng minh rằng dù diagnostic tham chiếu URI đó, **public log không cần ghi URI thô**.
2. `aliases` là map từ **URI thuộc những source được hệ thống chủ động đăng ký** sang tên logic `src/main/java/demo/Broken.java`. Tên này do application kiểm soát; không lấy bừa từ đường dẫn gốc.
3. `getOrDefault(..., "<unknown-source>")` bảo đảm nếu compiler báo một source **không nằm trong map**, log không tự fallback sang đường dẫn thô. Đây là quyết định quan trọng trong các hệ thống có nhiều source/module.
4. `Diagnostic.Kind.ERROR` và `getLineNumber()` là dữ liệu dạng enum/số; chương trình không lấy `getMessage()`, `toString()`, code snippet hoặc `getSource().getCharContent()` để gửi vào public log.
5. `StringWriter internalOutput` hấp thụ thông tin không phải diagnostic mà compiler có thể viết vào `Writer` của `getTask(...)`; ví dụ **cố ý không in nội dung writer này**. Trong hệ thống thật phải kiểm soát toàn bộ stderr/stdout của process, plugin và build tool, không chỉ writer của JavaCompiler.
6. `-proc:none` vô hiệu hóa annotation processors cho fixture đơn giản. Đây **không** phải lời khuyên tắt processor trong dự án phụ thuộc Lombok/MapStruct hoặc đang kiểm thử chính processor.
7. `leaked` chỉ kiểm tra ba **marker giả định đã biết**. Nó là phép thử hồi quy cho ví dụ; **không chứng minh thuật toán tổng quát ngăn mọi secret hoặc path**. Kiểm thử hệ thống thực cần thêm cases và kiểm soát nhiều kênh log.
8. `getSystemJavaCompiler()` cần JDK với compiler; runtime image chỉ chứa Java runtime có thể trả `null`. Không nên đưa chi tiết exception vào log public nếu exception có chứa giá trị nhạy cảm.

**Vì sao dùng source in-memory?** Ta có thể tái tạo lỗi trên cùng một JDK, không phải tạo file source dưới đường dẫn nhạy cảm thật. Với nguồn từ file vật lý, `StandardJavaFileManager` tạo `JavaFileObject` có thể mang `file:///...`; khi đó đăng ký ánh xạ an toàn cho từng URI được phép, thay vì in trực tiếp `getName()` hoặc `toUri()`.

## 5. Ánh xạ đường dẫn an toàn khi compile file thật

Đối với build service nhận nhiều file Java, cách tốt là gán **logical ID** ngay lúc tạo compilation input, ví dụ:

```text
file:///tmp/ci-worker-28/customer-private/repo/src/main/java/app/Order.java
  └── src/main/java/app/Order.java

file:///C:/Users/Example/Private-Workspace/src/main/java/app/Worker.java
  └── src/main/java/app/Worker.java

file:///untrusted/external/Different.java
  └── <unknown-source>
```

Đây là **sơ đồ minh họa**, không phải output của Java. Chỉ tên logic cuối cùng được phép đi đến log công khai. Đường dẫn thực ở trái chỉ xuất hiện trong vùng tin cậy và tài liệu ví dụ giả lập.

### 5.1. Không dựa vào `Path.getFileName()` đơn thuần

Nếu hai thư mục khác nhau đều có `Config.java`, chỉ ghi `Config.java` có thể làm người dùng xác định nhầm file. Ngược lại, tự `relativize` một path không thuộc repository có thể tạo `../../secrets/...` rồi lộ cấu trúc thư mục. Hãy:

- Lấy **root repo/working directory được tin cậy** từ cấu hình hệ thống, không từ input tùy ý.
- Chuẩn hóa path và xác minh nguồn thuộc root đã duyệt; với filesystem có symlinks, cân nhắc `toRealPath()` khi có quyền truy cập và yêu cầu không vượt root qua symlink.
- Chuyển sang slash chuẩn và validate tên logic; **nếu không hợp lệ hoặc không thuộc root, trả ID vô danh**.
- Xử lý case-insensitive/case-sensitive, drive letters/UNC, URI percent encoding, Unicode và file trùng tên trên nhiều module.
- Phân quyền source ID theo tenant/project; một tenant không được đọc alias của tenant khác.
- Đừng đưa path root, các phần nhạy cảm, query string hoặc host credentials vào URL/tên logic.

Lưu ý `Path.normalize()` loại bỏ `.`/`..` ở mức cú pháp nhưng **không chứng minh** path nằm dưới root thật sau khi đi qua symbolic link. Đối với dịch vụ xử lý file từ người dùng, việc kiểm tra ranh giới filesystem phải được làm trước khi cấp phép đọc source.

### 5.2. Mẫu xử lý nhiều source

Thay vì suy đoán alias từ `getSource()` khi nhận diagnostic, hãy tạo bảng ánh xạ **ở lúc dựng compilation inputs**. Ví dụ snippet (nằm trong một phương thức đã có file manager, không phải chương trình độc lập):

```java
Map<URI, String> sourceAliases = new java.util.HashMap<>();
for (Path file : approvedFiles) {
    JavaFileObject source = fileManager
            .getJavaFileObjectsFromPaths(List.of(file))
            .iterator().next();
    String alias = approvedLogicalIds.get(file);
    if (alias == null) {
        throw new IllegalArgumentException("Unregistered input");
    }
    sourceAliases.put(source.toUri(), alias);
    // Đồng thời thêm source vào danh sách JavaFileObject để compile.
}
```

Snippet giả định `approvedFiles` và `approvedLogicalIds` được **xây bằng kiểm tra quyền** trước đó. Chỉ phản ánh cách giữ mapping, không có ý rằng việc map tự bảo vệ được đường dẫn input hoặc fileManager đã đủ an toàn. Alias phải được validate để tránh newline, control characters hoặc ký tự phá cấu trúc log.

## 6. Có nên hiển thị `getMessage(Locale.ROOT)`?

Tùy phạm vi chia sẻ. Trong một hệ thống web “compile code do người dùng upload”, người dùng có thể cần xem thông điệp javac để sửa lỗi. Vẫn phải kiểm soát **ngữ cảnh**:

- **Chỉ tác giả/nhóm có quyền đối với source** được xem thông điệp đầy đủ hơn; đừng broadcast nguyên diagnostic lên public CI/PR log.
- Nếu cần hiển thị message, dùng dữ liệu sau khi lọc, cắt độ dài và **escape đúng với HTML/JSON/terminal**, kèm giới hạn request/user. Escaping để tránh XSS/log injection **không tương đương** redaction bí mật.
- Tránh phát nguyên thông điệp về source của tenant khác, đường dẫn trong compiler options hoặc lỗi hệ thống; bảo vệ cả lỗi khi file manager/processor ném exception.
- Đảm bảo việc phân quyền xem diagnostic theo cùng project/tenant với source liên quan. Cùng một message có thể chứa tên file, symbol hoặc đoạn code của nhiều file.
- Trong chế độ production/public, chỉ xuất **mã lỗi đã được cho phép, severity, logical source ID, line/column** và thông điệp tổng quát. Chi tiết kỹ thuật có thể xuất trong trang debug có xác thực, phân quyền và retention rõ ràng.

**Không có phép redaction regex nào hoàn hảo.** Chẳng hạn “thay `/home/.*?`” sẽ bỏ sót Windows paths, UNC paths, ký tự escape, path được URL-encoded, không phân biệt chuỗi là URL thông thường hay secret; còn regex quá rộng sẽ che mất nội dung hợp lệ. Redaction theo mẫu chỉ là **phòng tuyến bổ sung**, không thay cho thiết kế dữ liệu theo allowlist.

Khi cần message hữu ích trong giao diện riêng, một mẫu thiết kế là lưu **semantic error category** được ánh xạ từ `getCode()` của compiler đã pin, rồi đưa “Type mismatch at line 4” theo template do ứng dụng kiểm soát. `getCode()` không được Java SE chuẩn hóa giữa mọi compiler; nếu không nhận dạng được code, fallback sang “Compilation failed at source location” thay vì chuyển nguyên message.

## 7. Các kênh rò rỉ khác ngoài `DiagnosticCollector`

### 7.1. `javac` command-line và shell

Một build script như:

```bash
javac -encoding UTF-8 --release 17 -d build/classes src/main/java/demo/App.java
```

không có collector riêng; compiler có thể in file path, line lỗi, source snippet, caret và message ra stderr. Nếu CI công khai **toàn bộ stdout/stderr**, bạn đã công bố diagnostic thô dù không hề gọi Java Compiler API.

Giải pháp tùy hệ thống:

1. Nếu tự xây compile service, cân nhắc gọi **Compiler API** để nhận `Diagnostic` có cấu trúc rồi chỉ xuất trường đã duyệt.
2. Nếu phải chạy `javac` trong process con, thu stdout/stderr vào kênh riêng có hạn mức, phân loại sau đó; tránh tự động đẩy raw stream lên public pipeline. Giữ exit code chính xác; không bỏ qua lỗi build.
3. Đừng bật quá nhiều cờ verbosity ở CI public (`-verbose`, detailed debug/trace), đặc biệt cờ in classpath, dependency paths hoặc details của compiler.
4. Review shell tracing `set -x`, các command được CI hiển thị tự động, và cách truyền `-J-D...`, `-A...` hoặc secrets qua argument/env. **Không đưa secret vào compiler option** chỉ để “dễ cấu hình”; shell/process-list/build log có thể lộ.
5. Với Gradle/Maven, việc dùng compiler plugin và logging level của build tool có thể tiếp tục in raw diagnostics. Kiểm tra log hiệu quả bằng fixture có marker giả, không giả định compiler listener đủ chặn mọi output.

### 7.2. Annotation processors và compiler plugins

Annotation processor có thể gọi `Messager.printMessage(...)` và tạo diagnostics với nội dung **tùy ý**, bao gồm annotation values, tên class, file path hoặc nguồn nội bộ. Một processor độc hại còn có thể tự ghi stdout, mở network connection, đọc biến môi trường hoặc ghi file; sanitize `DiagnosticCollector` **không cô lập** được các side effect này.

- Khai báo processors **tường minh**, pin phiên bản và dependency graph; tránh processor bất ngờ từ classpath.
- Chạy compiler/processors trong môi trường cô lập phù hợp: service account hạn chế, filesystem sandbox, network restrictions khi cần.
- Không đưa credential của deployment/production vào môi trường của untrusted compilation process.
- Kiểm tra các option `-A...`; annotation processor có thể phản chiếu giá trị option vào diagnostic.
- Log lỗi của plugin theo chính sách dữ liệu, không mặc định `logger.error("...", throwable)` với toàn bộ stack trace ra public.

**Điểm mấu chốt:** masking log là giảm tác động, nhưng mã bên thứ ba chạy trong compiler có thể truy cập chính dữ liệu bí mật; cần loại bỏ quyền/secret khỏi môi trường trước khi chạy công cụ không tin cậy.

### 7.3. IDE, test reports, build caches và artifacts

Diagnostics có thể xuất hiện trong file test report XML/HTML, IDE problem panel, SARIF, static analysis report, build scan, telemetry, build-cache metadata, artifact manifest, hay comment bot trên PR. Vì vậy chỉ lọc màn hình console **chưa đủ**. Kiểm kê mọi nơi lưu hoặc chuyển tiếp kết quả compile:

```text
javac / plugin
  ├── terminal stdout/stderr
  ├── CI job logs
  ├── test reports / JUnit XML
  ├── static-analysis reports / SARIF
  ├── artifacts / build scans
  ├── chat / issue / pull request bot
  └── observability collector / retention storage
```

Cùng một policy data classification cần được áp dụng tại các điểm xuất đó; các nền tảng có cơ chế che secret riêng nhưng **không thể dựa vào chúng để bảo đảm không lộ source hoặc path**.

## 8. Mẫu cấu trúc event cho log công khai

Một event giả định được phép xuất:

```json
{
  "event": "java_compilation_diagnostic",
  "severity": "ERROR",
  "sourceId": "src/main/java/demo/Broken.java",
  "line": 4,
  "column": null,
  "codeCategory": "TYPE_ERROR",
  "buildId": "build-42"
}
```

Đây là **schema minh họa**, không phải JSON được tạo bởi `SafeCompilerDiagnostics.java`. Trong bài lab, `getColumnNumber()` đã có nhưng ta cố ý chỉ công bố line; event mẫu để `column: null` biểu thị một chính sách không tiết lộ độ chi tiết cột. `TYPE_ERROR` là **nhãn do ứng dụng chọn**, không phải mã chuẩn từ `javac`.

Yêu cầu cho serializer:

- Không cho phép thêm trường kiểu `rawMessage`, `absolutePath`, `sourceText`, `stackTrace` vào event public.
- `severity` lấy từ enum đã kiểm soát, không nhận string tùy ý từ processor.
- `sourceId` lấy từ map đã duyệt, có kiểm soát ký tự/độ dài; `buildId` là định danh công khai vô hại, **không dùng session token**.
- Dòng/cột là số hoặc null nếu `NOPOS`, và kiểm tra giới hạn hợp lý trước khi serialize.
- Encoder JSON phải escape `\n`, `\r`, dấu ngoặc kép và ký tự đặc biệt. Với text log dùng một encoder đáng tin, không ghép chuỗi tự do từ input.
- Log có thể được truy cập theo tenant/source permission; **JSON đúng cú pháp không đồng nghĩa với an toàn thông tin**.

Phân biệt **event severity** và **classification**: một `ERROR` có thể là lỗi type mismatch, một `WARNING` có thể xuất phát từ deprecated method; cả hai vẫn có khả năng mang dữ liệu nhạy cảm ở raw message.

## 9. Phòng chống log injection khi diagnostic chứa input không tin cậy

Ngoài việc lộ secret, dữ liệu do người dùng điều khiển có thể chứa newline, tab, ANSI escape sequences hoặc dấu phân cách giả lập, làm log trông giống một sự kiện khác.

Ví dụ payload giả lập:

```text
Broken.java
[INFO] BUILD SUCCESS
```

Nếu một đường dẫn/file name có ký tự xuống dòng mà hệ thống ghép thẳng vào string log, một diagnostic có thể biến thành **hai dòng**, gây sai lệch dashboard hoặc đánh lừa người xử lý sự cố.

Biện pháp:

- Chỉ xuất alias được kiểm soát, giới hạn ký tự cho phép, ví dụ các chữ, số, `/`, `.`, `_` và `-`, không chứa newline/control characters.
- Encode dữ liệu đúng chuẩn theo định dạng log; tốt nhất dùng logging framework với structured JSON encoder.
- Giới hạn chiều dài của trường trước khi lưu; có tổng hạn mức của event và rate limit để tránh flooding log.
- Không cho phép log content từ compilation task dùng thay event name, severity hoặc correlation ID.
- Không tin rằng parameterized logging tự chặn CR/LF injection: vẫn cần encoder hoặc kiểm tra dữ liệu.

## 10. Thiết kế hai mức quyền xem diagnostics

Mức công khai và mức debug riêng có yêu cầu khác nhau.

| Chính sách | Public/PR/tenant thiếu quyền source | Debug đã xác thực, tối thiểu cần thiết |
| --- | --- | --- |
| Trạng thái build | Có | Có |
| Diagnostic kind | Có | Có |
| Alias file logic | Có khi thuộc quyền | Có trong phạm vi dự án được phép |
| Dòng/cột | Tùy độ nhạy | Có khi cần |
| Message compiler thô | **Không** | Chỉ sau duyệt/giới hạn và kiểm tra nội dung |
| Dòng source/đoạn code | **Không** | Chỉ cho người có quyền đọc source |
| Absolute path/username | **Không** | Thường vẫn không cần; thay bằng source mapping |
| Stack trace, classpath | **Không** | Kênh bảo vệ riêng, retention ngắn |
| Raw stdout/stderr | **Không** | Chỉ khi cần, phải có kiểm soát |
| Secret/token | **Không** | **Không**, kể cả debug |

Một số đội có công cụ lưu raw compiler diagnostics để điều tra sự cố nghiêm trọng. Khi đó phải áp dụng kiểm soát riêng: encryption at rest/in transit, quyền đọc tối thiểu, audit access, retention, scrub khi export, cơ chế xóa và báo cáo sự cố lộ dữ liệu. Không để raw logs vô thời hạn trong CI artifacts.

### 10.1. Thực tế quan trọng: diagnostics không phải security boundary

Một hệ thống xử lý source **không đáng tin** không thể bảo đảm bí mật chỉ bằng cách bỏ `getMessage()`. Processor/compiler có thể thực thi mã hoặc truy cập filesystem tùy ngữ cảnh. Cần tạo security boundary **trước compiler**:

- Container/VM với source và dependency cần thiết, không mount `~/.ssh`, credentials, home directory hoặc token của runner.
- Chỉ cấp quyền đọc/ghi cần thiết; hạn chế network egress nếu không bắt buộc.
- Tách quyền của nhiều tenant; không dùng chung workdir có thể đọc được.
- Cấp resource limits cho compilation process (CPU/memory/time/disk); tránh log flooding.
- Log collector ở ngoài process compile hoặc nằm trong ranh giới được tin cậy, không chuyển raw outputs lên public.

## 11. Bộ test chống rò rỉ với dữ liệu giả

Chương trình ở phần 4 kiểm tra marker tĩnh. Để nâng từ demo thành kiểm thử hồi quy cho pipeline thực, xây **bộ fixture mô phỏng** chứa các loại input sau, tuyệt đối không dùng dữ liệu thật:

| Fixture | Chuỗi giả lập | Kỳ vọng |
| --- | --- | --- |
| Linux absolute path | `/home/tester/private-project/src/Bad.java` | Không xuất đường dẫn thật |
| Windows absolute path | `C:\Users\Tester\SecretRepo\Bad.java` | Không xuất home/drive/workspace |
| UNC path | `\\fileserver\private-share\Bad.java` | Không lộ share/server nội bộ |
| URL encoded path | `file:///home/tester/private%20project/Bad.java` | Không lộ đường dẫn encode |
| Source literal | `"TRAINING_SECRET_MARKER"` | Marker không xuất qua public diagnostics |
| Source variable name nhạy cảm | `clientInternalIdentifier` | Không xuất raw code/message |
| Newline injection | `Bad.java\n[INFO] BUILD SUCCESS` | Không tạo dòng log giả |
| ANSI control sequences | `\u001b[31m` (chuỗi escape giả lập) | Không điều khiển terminal log |
| Unknown source | Diagnostic không nằm trong allowlist | `<unknown-source>` hoặc ID trung tính |
| Global diagnostic | `getSource() == null`, `NOPOS` | Không crash, dùng unknown location |
| Annotation processor | Processor tạo message chứa marker giả | Public log loại bỏ raw message |
| Throwing compiler/file manager | Exception có path trong `getMessage()` | Exception details được giữ ở kênh bảo vệ |

Một bộ test nên **capture toàn bộ output sau cùng** tại đúng nơi người dùng xem: CI job text, report HTML/XML/JSON, PR comment, downloaded artifact. Assert không chứa marker giả, path hoặc chuỗi nhạy cảm thuộc các fixture. Kiểm tra `safeRecord` trong Java là cần thiết nhưng **chưa đủ** nếu build shell vẫn in source path hoặc exception message.

### 11.1. Positive và negative assertions

Negative test bảo đảm output **không chứa** marker/đường dẫn; positive test bảo đảm vẫn có thông tin có ích:

```text
PASS: public event has severity=ERROR
PASS: public event has approved sourceId
PASS: public event has line=4
PASS: public event excludes private path
PASS: public event excludes training marker
PASS: stdout/stderr/report exports obey same policy
```

Đây là **checklist kỳ vọng**, không phải stdout chính xác của ví dụ phần 4. Điều này tránh xây sanitizer “an toàn” bằng cách xóa sạch mọi diagnostic, khiến developer không thể xác định lỗi. Trường không cho phép phải bị loại; trường được cho phép phải đúng.

### 11.2. Mutation tests cho chính cơ chế bảo vệ

Tạo biến thể mã cố ý **gọi `System.out.println(d.getMessage(Locale.ROOT))`** trong kênh public và chắc chắn test chống lộ nhận ra marker giả (có thể cần fixture compiler/processor có message chứa marker). Tạo biến thể khác **fallback sang `d.getSource().toUri()`** khi alias không tồn tại; bảo đảm test phát hiện đường dẫn. Nếu test vẫn xanh với hai biến thể nguy hiểm thì kiểm thử chưa quan sát đúng kênh rò.

Đừng dùng exact message string như một giả định portable. Compiler và JDK có thể thay đổi message; chủ động tạo fixture với processor hoặc stub `Diagnostic` có chứa marker để kiểm tra formatter riêng, rồi kiểm thử integration với compiler thật.

## 12. Lỗi triển khai thường gặp

### 12.1. Chỉ thay `/home/user` bằng `***`

Việc thay một prefix quen thuộc sẽ bỏ sót Windows/UNC, symlink-resolved path, đường dẫn trong URI encoding, root Docker, artifact metadata và tên riêng trong source. Giải pháp: **không phát raw path**, thay bằng alias hợp lệ từ registry.

### 12.2. Cho rằng `Locale.ROOT` khiến message an toàn

`getMessage(Locale.ROOT)` chỉ chọn locale phục vụ diễn đạt thông điệp. Nó vẫn có thể chứa dữ liệu từ symbols, source, options hoặc processor. Giải pháp: tách localizable UI message do application kiểm soát khỏi raw compiler message.

### 12.3. Đưa raw exception vào logger

Ví dụ **không nên dùng ở kênh public**:

```java
// Không sử dụng khi throwable có thể chứa path/source/secrets.
logger.error("Compilation failed", exception);
```

Đoạn minh họa dùng logger giả định trong project, không phải Java class độc lập. Framework có thể in stack trace và `exception.getMessage()` gồm đường dẫn. Dùng public error ID/category, lưu incident detail ở hệ thống có quyền phù hợp và không lưu secret không cần thiết.

### 12.4. Tin tưởng nguồn ghi diagnostic là compiler chuẩn

JDK compiler có contract nhất định, nhưng processor/plugin có thể tự sinh warning/error message. Khi chọn `-proc:full` hoặc cấu hình processor, đó còn là **chạy mã bên thứ ba**. Đánh giá dependency supply chain, sandbox và quyền trước khi xử lý output.

### 12.5. Chỉ che trên UI nhưng để raw trong artifact

Một dashboard hiển thị `<redacted>` có thể vẫn upload file log thô lên storage có quyền rộng. Phải kiểm tra chính **bản đã ghi/đã upload/được chia sẻ**, không chỉ component render.

### 12.6. Bỏ qua diagnostic không có source/line

Một lỗi command option hoặc compiler internal error có thể không gắn `JavaFileObject`. Không ép `getSource().toUri()` khi `getSource() == null`, không biến `NOPOS=-1` thành số dòng thật. Dùng `<unknown-source>`, không cần in full exception để “bù” vị trí thiếu.

### 12.7. Chia sẻ nguyên command-line để debug

Lệnh chạy có thể chứa `-classpath` trỏ vào private repository, `-Apassword=...` hoặc tên thư mục/tenant. Thay vì log toàn lệnh, log **các cờ được cho phép** (ví dụ `--release=17`) và ID toolchain; không dump mọi environment variable.

## 13. Checklist áp dụng trong Java build pipeline

- [ ] Liệt kê mọi đường ra diagnostics: API listener, writer, stdout/stderr, build plugins, reports, CI, PR bots, telemetry.
- [ ] Public logs chỉ chứa event/schema với các trường allowlist; không dùng `Diagnostic.toString()`/raw `getMessage()`.
- [ ] Source URI được ánh xạ sang logical ID có kiểm soát quyền và ký tự; unknown source luôn fallback trung tính.
- [ ] Dòng/cột xử lý `NOPOS`; chỉ xuất vị trí phù hợp với mức quyền xem.
- [ ] Không log raw source snippets, secrets, environment, classpath, absolute path và exception stack trace ra nơi rộng quyền.
- [ ] Compiler/processors chỉ nhận quyền tối thiểu, không có production credentials hoặc private home directory trong sandbox.
- [ ] Trường xuất được encode đúng định dạng JSON/text và có giới hạn kích thước để chống CR/LF injection/log flooding.
- [ ] Test với fake marker/path trên Linux, Windows, UNC, URI-encoded và Unicode; rà cả build artifacts và reporting endpoints.
- [ ] CI job thất bại khi policy bị vi phạm; có mutation test để chứng minh bộ test thấy được lỗ hổng.
- [ ] Hệ thống giữ raw diagnostic phục vụ debug, nếu có, phải hạn chế người đọc, ghi audit, mã hóa/retention và có cơ chế xóa.
- [ ] Sự cố lộ dữ liệu được xử lý theo quy trình bảo mật; không sao chép raw diagnostic sang ticket/chat công khai.

## 14. Tình huống thực tế: nền tảng kiểm thử code đa người dùng

Giả sử nền tảng cho học viên upload Java source rồi trả kết quả compile. Source có tên người dùng hoặc nội dung bài tập; runner có thư mục `/runner/work/tenant-123/...`. Khi compile thất bại:

1. **Input gateway** xác thực người dùng và quyền trên bài nộp, gán `submissionId` nội bộ và logical paths (ví dụ `Submission.java`). Không nhúng tên người dùng hoặc tenant ID riêng tư vào source alias public.
2. **Compiler worker** xử lý source trong sandbox không có secret; processor bị tắt nếu bài tập không cần. Compiler API gửi diagnostic events có cấu trúc về service tin cậy.
3. **Formatter** chỉ chọn `kind`, logical source ID, line/cột và category được duyệt. Unknown source cho kết quả generic; không tự điền path.
4. **API response** chỉ trả events của đúng submission mà người dùng được phép xem; nếu cần snippet do chính người dùng upload, API phải kiểm tra quyền nguồn và giới hạn dữ liệu trước khi gửi.
5. **Public CI/monitoring** chỉ lưu số lượng lỗi/cảnh báo, build status, thời gian chạy và event ID vô hại; không tự động lưu raw messages.
6. **Incident debug** khi compiler crash chỉ cung cấp mã incident trên UI; dữ liệu điều tra nằm ở hệ thống giới hạn người xem, có retention và scrub trước khi export.

Cấu trúc trên vẫn cho người học biết “ERROR tại `Submission.java:4`” để sửa lỗi, trong khi người khác không thấy path của runner hoặc đoạn source.

## 15. Câu hỏi tự đánh giá

1. Vì sao `Diagnostic.Kind.ERROR` thường an toàn hơn `Diagnostic.getMessage(Locale.ROOT)`? Có trường hợp nào kind/line cũng phải hạn chế?
2. Vì sao `getSource().toUri().getPath()` không thể được đưa thẳng vào log chỉ bằng cách bỏ prefix `/tmp/`?
3. Trong ví dụ Java, vì sao `aliases.getOrDefault(..., "<unknown-source>")` là lựa chọn quan trọng khi compiler trả về source không đăng ký?
4. Nếu một annotation processor tự gọi `System.err.println("...")`, `DiagnosticCollector` có ngăn được log hay không? Cần thay đổi security boundary ở đâu?
5. Vì sao unit test `safeRecord.contains(FAKE_MARKER) == false` không chứng minh toàn bộ CI log an toàn? Phải kiểm thử thêm những điểm xuất nào?
6. Nếu muốn hiển thị raw message cho người viết source, bạn sẽ gắn quyền theo source/tenant, escape output và quản lý retention thế nào?
7. Làm thế nào để vừa giữ severity/location đủ dùng cho developer, vừa tránh lộ source text, absolute path và log injection?

**Kết quả học tập:** có khả năng xác định dữ liệu nhạy cảm trong compiler diagnostics, thiết kế formatter có allowlist, tự kiểm thử với marker giả và bao phủ các kênh ghi log/CI liên quan, đồng thời phân biệt **lọc thông tin công bố** với **cô lập compiler/processor chạy mã**.

## Tài liệu tham khảo

- Oracle Java SE 17 – `javax.tools.Diagnostic`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/Diagnostic.html
- Oracle Java SE 17 – `JavaCompiler`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html
- Oracle Java SE 17 – `DiagnosticCollector`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/DiagnosticCollector.html
- Oracle Java SE 17 – `ToolProvider`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ToolProvider.html
- Oracle Java SE 17 – `javac`: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
- OWASP – Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- MITRE CWE-532 – Insertion of Sensitive Information into Log File: https://cwe.mitre.org/data/definitions/532.html
- OWASP – Implement Security Logging and Monitoring: https://devguide.owasp.org/en/04-design/02-web-app-checklist/09-logging-monitoring/
