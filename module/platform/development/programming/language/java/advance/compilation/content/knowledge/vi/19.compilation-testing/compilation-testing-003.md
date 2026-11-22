# Kiểm tra vị trí và mức độ diagnostics qua Java Compiler API

> **Chủ đề:** Java Advance – compilation → Kiểm thử biên dịch. Bài này tập trung vào việc viết kiểm thử chủ động biên dịch Java source, thu thập `Diagnostic` và xác minh **mức độ** (`ERROR`, `WARNING`, v.v.) cùng **vị trí** (file, dòng, cột, offset). Cách làm phù hợp cho bài kiểm thử negative compilation, annotation processor, công cụ phân tích mã và pipeline chất lượng.

## 1. Tại sao chỉ kiểm tra “compile thành công/thất bại” là chưa đủ?

Một chương trình có thể biên dịch thất bại đúng như mong đợi nhưng vì **nguyên nhân khác hoàn toàn** với yêu cầu kiểm thử. Ví dụ bạn muốn phát hiện việc gán `String` cho `int` ở dòng 4; nếu mã mẫu mắc lỗi cú pháp ở dòng 1 thì khẳng định `task.call() == false` vẫn “pass” giả. Kiểm thử có giá trị phải kiểm tra thêm ít nhất:

1. **Kết quả toàn cục:** compilation task thành công hay thất bại.
2. **Mức độ diagnostic:** có ít nhất một `Diagnostic.Kind.ERROR` đúng với tình huống hay không.
3. **Vị trí:** diagnostic thuộc source nào, dòng/cột/range có tương ứng với mã bị lỗi hay không.
4. **Nội dung/loại vấn đề:** khi cần, kiểm tra nhóm lỗi bằng `getCode()` hoặc thông điệp đã chuẩn hóa, với nhận thức những giá trị này phụ thuộc compiler và phiên bản JDK.

Đối với warning, không thể chỉ nhìn `task.call()`: một biên dịch thành công vẫn có thể phát `WARNING` hoặc `MANDATORY_WARNING`. Nếu bật `-Werror`, các warning có thể khiến compilation thất bại. Vì vậy **success** và **diagnostics** là hai loại thông tin phải đánh giá riêng.

## 2. API nền tảng: `javax.tools`

Các lớp liên quan nằm trong module chuẩn `java.compiler`, package `javax.tools`. Cần có một triển khai compiler trong runtime; JDK thông thường cung cấp `javac` trong module `jdk.compiler`, nhưng Java runtime tùy biến có thể không kèm compiler.

| API | Vai trò trong kiểm thử |
| --- | --- |
| `ToolProvider.getSystemJavaCompiler()` | Lấy system Java compiler, có thể trả `null` nếu không có |
| `JavaCompiler` | Tạo và chạy compilation task |
| `JavaCompiler.CompilationTask` | Đại diện một lần biên dịch; `call()` trả kết quả |
| `JavaFileObject` / `SimpleJavaFileObject` | Biểu diễn source đầu vào dưới dạng file hoặc chuỗi trong bộ nhớ |
| `StandardJavaFileManager` | Quản lý source/classpath/output files và charset |
| `DiagnosticListener<JavaFileObject>` | Nhận từng diagnostic khi tool thông báo |
| `DiagnosticCollector<JavaFileObject>` | Cài sẵn listener gom diagnostics vào danh sách |
| `Diagnostic<? extends JavaFileObject>` | Một lỗi/cảnh báo/ghi chú với severity và location |

Luồng thực hiện:

```text
Source JavaFileObject(s)
         │
         ▼
JavaCompiler.getTask(options, fileManager, listener)
         │
         ▼
CompilationTask.call()
         │
         ├── boolean success/failure
         │
         └── DiagnosticCollector
                  ├── kind: ERROR, WARNING, ...
                  ├── source URI
                  ├── line / column
                  ├── start / position / end offset
                  └── code / localized message
```

Nên tạo **collector mới cho mỗi compilation task** để không lẫn diagnostics của lần trước. Đóng `StandardJavaFileManager` bằng `try-with-resources`. Compiler task chỉ nên `call()` một lần; nếu muốn so sánh hai phiên bản source, tạo hai task riêng.

### 2.1. Các mức độ trong `Diagnostic.Kind`

| Kind | Ý nghĩa | Kỳ vọng điển hình |
| --- | --- | --- |
| `ERROR` | Lỗi biên dịch | Thường phải có khi kiểm thử negative compile |
| `WARNING` | Cảnh báo thông thường | Có thể xuất hiện khi bật các `-Xlint` thích hợp |
| `MANDATORY_WARNING` | Cảnh báo mà tool có nghĩa vụ thông báo theo quy tắc liên quan | Nên tính cùng nhóm “warning” trong policy |
| `NOTE` | Thông tin/ghi chú | Không coi là lỗi trừ khi chính policy của bạn yêu cầu |
| `OTHER` | Thông báo không thuộc các loại trên | Lưu lại khi phân tích nhưng không tự suy ra severity |

Không được gộp mọi non-`ERROR` thành `WARNING`. Nên phân loại tường minh:

```java
static boolean isWarning(Diagnostic.Kind kind) {
    return kind == Diagnostic.Kind.WARNING
            || kind == Diagnostic.Kind.MANDATORY_WARNING;
}
```

Đoạn trên là **phương thức hỗ trợ**, dùng trong một class có import `javax.tools.Diagnostic`; không phải chương trình Java độc lập.

## 3. Diễn giải vị trí đúng: file, dòng, cột và offset

Một diagnostic không nhất thiết gắn với source hoặc vị trí. Đọc kỹ hợp đồng API:

| Phương thức | Định nghĩa |
| --- | --- |
| `getSource()` | `JavaFileObject` liên quan, có thể là `null` |
| `getLineNumber()` | Dòng bắt đầu từ **1**, hoặc `Diagnostic.NOPOS` |
| `getColumnNumber()` | Cột bắt đầu từ **1**, hoặc `Diagnostic.NOPOS` |
| `getPosition()` | Offset ký tự từ đầu source bắt đầu từ **0**, hoặc `NOPOS` |
| `getStartPosition()` | Offset của đầu vùng có vấn đề, hoặc `NOPOS` |
| `getEndPosition()` | Offset kết thúc vùng có vấn đề, hoặc `NOPOS` |
| `getCode()` | Mã diagnostic do implementation quy định, có thể `null` |
| `getMessage(Locale)` | Thông điệp có thể được địa phương hóa |

Khi có vị trí hợp lệ, API bảo đảm:

```text
getStartPosition() <= getPosition() <= getEndPosition()
```

**`Diagnostic.NOPOS` là giá trị đặc biệt** (bằng `-1`), **không phải dòng 0/cột 0**. Các phương thức vị trí báo `NOPOS` khi không có vị trí thích hợp. Không viết `source.getCharContent(...).charAt((int) d.getPosition())` mà chưa kiểm tra `getSource() != null` và `getPosition() != Diagnostic.NOPOS`, cũng như kích thước chuỗi.

**Offset ký tự khác offset byte UTF-8.** Khi source chứa tiếng Việt hoặc ký tự Unicode ngoài BMP, tuyệt đối không lấy `getPosition()` làm chỉ số vào mảng byte của file. Nếu bạn sử dụng `String.charAt()` / `substring()` cho source Java đã đọc, cần bảo đảm cùng đúng nội dung, newline và quy ước index của compiler. Vị trí cột là tọa độ trong source, không hẳn là “cột pixel” khi hiển thị tab hoặc ký tự Unicode; tính toán highlighting phải dựa trên dữ liệu source gốc.

Với fixtures để test **exact line/column**, khóa đầu vào:

- Mã nguồn cố định, UTF-8 và newline nhất quán (thường là LF), tránh template chèn tiền tố/bớt dòng.
- Có chủ đích về **text block indentation**: Java tự xử lý incidental whitespace trong text block; kiểm tra chuỗi thực tế trước khi khẳng định dòng/cột.
- Chọn compiler/JDK mục tiêu cho test; vị trí chọn highlight có thể đổi khi phiên bản compiler thay đổi, dù yêu cầu về loại lỗi vẫn đúng.
- Nếu test nhiều lỗi, phân biệt **lỗi gốc** và lỗi kéo theo. Đừng mặc định thứ tự hay số lượng diagnostics luôn giống nhau.

Ví dụ, diagnostic ở dòng 4, cột 25 nghĩa là **dòng thứ tư và cột thứ 25 trong source compiler nhìn thấy**; không liên quan vị trí của dòng đó trong file Java chứa đoạn text block.

## 4. Ví dụ Java 17+ hoàn chỉnh: bắt lỗi ở dòng 4

Mục tiêu: chương trình `DiagnosticAudit` tự gọi compiler để biên dịch một lớp `demo.Broken` có câu lệnh `int count = "wrong";`. Không cần tạo file `Broken.java` trên đĩa; source được đưa vào `SimpleJavaFileObject` dưới dạng string. Test kiểm tra:

- Compilation thất bại.
- Có ít nhất một diagnostic `ERROR`.
- Một `ERROR` xuất hiện **đúng dòng 4**, cột hợp lệ và thuộc đúng source URI.

**File `DiagnosticAudit.java`:**

```java
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Locale;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class DiagnosticAudit {
    static final class StringSource extends SimpleJavaFileObject {
        private final String contents;

        StringSource(String className, String contents) {
            super(URI.create("string:///" + className.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.contents = contents;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return contents;
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "Cần chạy bằng JDK có module jdk.compiler");
        }

        String program = """
                package demo;
                public class Broken {
                    public static void main(String[] args) {
                        int count = "wrong";
                    }
                }
                """;

        JavaFileObject source = new StringSource("demo.Broken", program);
        DiagnosticCollector<JavaFileObject> collector =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager files =
                 compiler.getStandardFileManager(
                         null, Locale.ROOT, StandardCharsets.UTF_8)) {

            JavaCompiler.CompilationTask task = compiler.getTask(
                    null,
                    files,
                    collector,
                    List.of("--release", "17",
                            "-encoding", "UTF-8", "-proc:none"),
                    null,
                    List.of(source));

            boolean ok = Boolean.TRUE.equals(task.call());

            long errorCount = collector.getDiagnostics().stream()
                    .filter(d -> d.getKind() == Diagnostic.Kind.ERROR)
                    .count();

            boolean hasLine4Error = collector.getDiagnostics().stream()
                    .anyMatch(d ->
                            d.getKind() == Diagnostic.Kind.ERROR
                            && d.getLineNumber() == 4
                            && d.getColumnNumber() >= 1
                            && d.getSource() != null
                            && d.getSource().toUri().toString()
                                    .endsWith("/demo/Broken.java"));

            System.out.println("Biên dịch thành công: " + ok);
            System.out.println("Số lỗi >= 1: " + (errorCount >= 1));
            System.out.println("Lỗi ERROR ở dòng 4: " + hasLine4Error);
        }
    }
}
```

**Chạy từ thư mục chứa file**, dùng JDK 17 trở lên:

```bash
javac --release 17 -encoding UTF-8 DiagnosticAudit.java
java DiagnosticAudit
```

**Stdout khi chạy với system `javac` chuẩn trên JDK 17+:**

```text
Biên dịch thành công: false
Số lỗi >= 1: true
Lỗi ERROR ở dòng 4: true
```

Ví dụ đã được kiểm tra bằng `javac`/`java` trên OpenJDK 24. Không assert nguyên văn lỗi do ngôn ngữ thông báo và cách diễn đạt phụ thuộc implementation. Nếu cần test có thể báo thất bại khi thuộc tính sai, thay các dòng in thành assertions hoặc ném `AssertionError` theo kết quả. Việc để `JavaFileObject` trong memory cũng tránh lỗi do tạo nhầm file nguồn bên ngoài, đồng thời URI vẫn cho phép kiểm tra file nào gây lỗi.

**Lưu ý khi ghi source trên Windows:** nguồn thực sự phải là UTF-8. Windows PowerShell 5.1 với `Set-Content -Encoding UTF8` thường thêm UTF-8 BOM; `javac` có thể báo ký tự `\ufeff` không hợp lệ ở đầu file. Dùng editor lưu UTF-8 không BOM hoặc API ghi UTF-8 không BOM. Sự cố này **khác** với diagnostic lỗi kiểu dữ liệu mà ví dụ muốn kiểm tra.

## 5. Giải thích chuỗi thao tác trong ví dụ

### 5.1. Source in-memory là một Java file hợp lệ đối với compiler

`StringSource` tạo URI `string:///demo/Broken.java` với `Kind.SOURCE`. Phần `getCharContent()` trả đúng mã nguồn. Vì class public tên `Broken` và package `demo`, URI nên phản ánh đường dẫn `demo/Broken.java`; điều đó giúp diagnostic source ổn định. Nếu chuyển sang tập tin thật, dùng file manager thay vì tự dựng URI.

Khi snapshot lỗi, tên source nên lấy từ `d.getSource().toUri()`, nhưng cần canonicalize phần đường dẫn tuyệt đối để CI trên Windows và Linux không bị khác nhau vì workspace path. Với in-memory URI như trên, so sánh suffix `/demo/Broken.java` là đủ rõ cho fixture; hệ thống build nhiều file cần định danh source cẩn thận hơn để tránh hai file có suffix trùng.

### 5.2. Collector nhận diagnostics, `call()` trả trạng thái

Tham số thứ ba của `compiler.getTask(...)` là `DiagnosticListener`. `DiagnosticCollector` implement interface này và lưu các phần tử `Diagnostic` khi compiler báo. Sau `task.call()`, đọc `collector.getDiagnostics()` để xác minh kết quả; danh sách có thể bao gồm warnings và notes, không chỉ errors.

`Boolean.TRUE.equals(task.call())` tránh phụ thuộc vào unboxing một kết quả nullable. Một `false` không nói gì về **lý do**; vì thế test còn kiểm tra `ERROR` tại dòng 4.

### 5.3. Cờ biên dịch cố định môi trường kiểm thử

- `--release 17` cố định ngôn ngữ/API nền tảng đích Java 17 (khi compiler hỗ trợ).
- `-encoding UTF-8` kiểm soát charset khi compiler đọc file thực; đối với `StringSource` nội dung đã là Unicode trong bộ nhớ.
- `-proc:none` tắt annotation processing để ví dụ không bị ảnh hưởng bởi processor tình cờ trên classpath. **Nếu đang test annotation processor, tuyệt đối bỏ cờ này** và cấu hình processor path rõ ràng.
- File manager được đóng tự động trong `try-with-resources`; mỗi lượt nên tạo collector/task riêng.

Bài học quan trọng: **không lấy một đoạn compiler log từ stdout/stderr để parse dòng lỗi** khi đã có `Diagnostic` cấu trúc. Text log phụ thuộc locale, compiler, options, terminal width và cách hiển thị caret.

## 6. Xác minh severity: ERROR, WARNING và policy

### 6.1. Kiểm thử lỗi biên dịch

Dạng assertion tốt (đoạn dùng trong test, với `collector` và `ok` đã có):

```java
if (ok) {
    throw new AssertionError("Fixture phải biên dịch thất bại");
}

boolean rightError = collector.getDiagnostics().stream()
        .anyMatch(d -> d.getKind() == Diagnostic.Kind.ERROR
                && d.getLineNumber() == 4);
if (!rightError) {
    throw new AssertionError("Không tìm thấy ERROR ở dòng 4");
}
```

Đây là **snippet**, không phải chương trình độc lập; đưa vào sau `task.call()` trong một compilation fixture như phần 4.

Khi test compiler rejection, nên thêm `getSource()` và một đặc điểm nhận dạng lỗi nếu có thể, nhất là khi fixture có nhiều vấn đề. Không nên assert `getDiagnostics().size() == 1` trừ khi test thật sự muốn bảo đảm **không có bất cứ diagnostic nào khác**; notes và lỗi kéo theo thường có thể xuất hiện.

### 6.2. Kiểm thử warning: tạo một warning có chủ đích

Ví dụ source hợp lệ nhưng gọi phương thức được gắn `@Deprecated`:

```java
class Legacy {
    @Deprecated static void oldApi() {}
}

class Client {
    void run() {
        Legacy.oldApi();
    }
}
```

Khi biên dịch với compiler `javac` và bật `-Xlint:deprecation`, có thể thu được `WARNING` tại lời gọi `Legacy.oldApi()`. Trong test riêng, đặt đoạn source này vào `StringSource("Client", sourceText)`; dùng options như:

```java
List.of("--release", "17",
        "-encoding", "UTF-8",
        "-proc:none", "-Xlint:deprecation")
```

Sau `task.call()`, có thể xác minh:

```java
boolean hasWarning = collector.getDiagnostics().stream()
        .anyMatch(d ->
                d.getKind() == Diagnostic.Kind.WARNING
                || d.getKind() == Diagnostic.Kind.MANDATORY_WARNING);

if (!ok || !hasWarning) {
    throw new AssertionError(
            "Mong đợi biên dịch thành công nhưng có warning");
}
```

Các snippet `collector`/`ok` sử dụng biến của compilation task riêng, **không tái sử dụng collector của fixture bị lỗi trong phần 4**. Nếu muốn test mức độ warning tại dòng cụ thể, thêm kiểm tra `getLineNumber()` sau khi cố định đúng fixture và phiên bản toolchain.

Một warning có thể không xuất hiện nếu tùy chọn lint bị bỏ, source được `@SuppressWarnings`, compiler không phát cùng loại cảnh báo, hoặc đoạn mã không còn dùng API deprecated. Vì vậy test warning phải mô tả rõ **flag**, **compiler version** và **nguồn kích hoạt**.

### 6.3. `-Werror` không đổi bản chất của mọi diagnostic

Với `-Werror`, compiler có thể từ chối compilation vì warning. Điều này không có nghĩa các phần tử `WARNING` tự chuyển thành `ERROR` tại cùng vị trí; compiler có thể phát thêm một error tổng quát vì warnings được coi là errors. Test cần tách:

- Test “cảnh báo có tồn tại”: assert `WARNING` hoặc `MANDATORY_WARNING`.
- Test “policy không cho phép warning”: bật `-Werror` và assert compilation thất bại.
- Không giả định `-Werror` buộc `ERROR` có cùng line/column với warning gốc.

### 6.4. Đọc mã diagnostic khi thực sự cần

`d.getCode()` có thể hữu ích hơn `getMessage(Locale)` để phân biệt “incompatible types” với “cannot find symbol” trong cùng một JDK/toolchain. Tuy nhiên **Diagnostic API không chuẩn hóa code**: một compiler khác có thể chọn mã khác hoặc trả `null`. Nếu test phải chạy trên nhiều vendor/major JDK, ưu tiên assertion theo kind + source + vị trí, kết hợp fixture nhỏ và kiểm tra compilation outcome. Chỉ snapshot exact code khi dự án chủ động **pin compiler implementation/version**.

## 7. Đánh giá location một cách an toàn và chẩn đoán hữu ích

Diagnostic có thể xuất phát từ lỗi tùy chọn compiler, annotation processor, file manager hoặc ngữ cảnh không gắn trực tiếp với một source cụ thể. Đừng luôn ép `getLineNumber() > 0`.

Mẫu xử lý an toàn (snippet đặt trong method có `Diagnostic<? extends JavaFileObject> d`):

```java
String sourceName = d.getSource() == null
        ? "<no-source>"
        : d.getSource().toUri().toString();

String location = d.getLineNumber() == Diagnostic.NOPOS
        ? "<no-position>"
        : d.getLineNumber() + ":" + d.getColumnNumber();

String display = d.getKind() + " " + sourceName + ":" + location;
```

Nếu `getLineNumber() != NOPOS` thì trong hợp đồng chuẩn `Diagnostic`, `getColumnNumber()` cũng phải có vị trí. Một implementation khác có thể không thể xác định location cho lỗi mang tính global; trường hợp này cần test theo kind/kết quả và nội dung mô tả vấn đề ở mức thích hợp.

### 7.1. Tính vùng highlight từ offset

Khi muốn bôi đậm một đoạn source, dùng `getStartPosition()` và `getEndPosition()` **sau khi** kiểm tra điều kiện:

```java
long start = d.getStartPosition();
long end = d.getEndPosition();
String text = d.getSource() == null
        ? null
        : d.getSource().getCharContent(true).toString();

if (text != null
        && start != Diagnostic.NOPOS
        && end != Diagnostic.NOPOS
        && start >= 0
        && start <= end
        && end <= text.length()) {
    String highlighted = text.substring((int) start, (int) end);
    // Dùng highlighted để giải thích phạm vi compiler đánh dấu.
}
```

Đây là snippet nằm trong phương thức có thể ném `IOException` hoặc xử lý ngoại lệ của `getCharContent()`; `StringSource` trong ví dụ đầu không ném lỗi. Khi chuyển sang source thực, cần xác nhận offset thuộc đúng **nội dung compiler đã đọc** (không lấy text đã normalize CRLF, chèn BOM hoặc sửa indentation). Có compiler chọn range lớn hoặc nhỏ khác nhau, nên snapshot từng ký tự highlight dễ vỡ khi nâng JDK.

### 7.2. Line và column chưa chắc là thứ UI muốn hiển thị

- `getLineNumber()` và `getColumnNumber()` là vị trí logic 1-based; UI editor đôi khi dùng chỉ số hàng/cột **0-based**. Chuyển đổi rõ ràng: `uiLine = line - 1`, `uiColumn = column - 1` khi có vị trí.
- Tab và ký tự Unicode có thể làm “cột hiển thị” khác “cột ký tự”; tuyệt đối không cộng cột với khoảng trắng cố định để vẽ dấu mũ một cách máy móc.
- Nếu kết quả gửi qua JSON/LSP, cần quy định encoding của vị trí; nhiều hệ thống editor dùng **UTF-16 code units**. Hãy đo đạc và chuyển đổi thay vì giả định byte index.
- Với multi-file compiler task, kiểm tra cả source URI, không chỉ số dòng: hai file khác nhau đều có thể có ERROR ở dòng 4.

## 8. Kiểm thử nhiều diagnostics có cùng kind hoặc nhiều file

Khi mã lỗi tạo cascade diagnostics, một chiến lược tốt là kiểm tra có tồn tại **tập con cần thiết** thay vì xác nhận nguyên cả danh sách.

Giả sử project có các file `A.java` và `B.java`, ta có thể yêu cầu:

1. Ít nhất một `ERROR` cho file `A.java` ở khu vực expected.
2. Không có `ERROR` nào cho file `B.java` (fixture hợp lệ).
3. Không có compiler crash hoặc lỗi config.
4. Các cảnh báo thêm được phân loại và báo ra để phân tích.

Nếu muốn kiểm tra “không warning” cho một bộ source hoàn toàn sạch, hãy bật các lint options có chủ đích rồi assert:

```java
boolean anyWarning = collector.getDiagnostics().stream()
        .anyMatch(d -> d.getKind() == Diagnostic.Kind.WARNING
                || d.getKind() == Diagnostic.Kind.MANDATORY_WARNING);
if (anyWarning) {
    throw new AssertionError("Build không được có warning");
}
```

Điểm cân bằng: kiểm thử **contract về loại lỗi và source location** đủ chặt để ngăn false positive, nhưng tránh khẳng định những chi tiết không được chuẩn API bảo đảm (exact text, diagnostic order, số lượng lỗi phụ nếu không cần).

## 9. Nguồn file thực, classpath và xử lý task

Ví dụ in-memory giúp học API nhưng project thật thường cần compile source trên disk. Khi đó:

```java
// Snippet bên trong method đã có JavaCompiler compiler.
try (StandardJavaFileManager files =
         compiler.getStandardFileManager(
                 null, Locale.ROOT, StandardCharsets.UTF_8)) {
    Iterable<? extends JavaFileObject> sources =
            files.getJavaFileObjectsFromPaths(
                    List.of(java.nio.file.Path.of("src/test/fixtures/Broken.java")));

    DiagnosticCollector<JavaFileObject> collector =
            new DiagnosticCollector<>();

    JavaCompiler.CompilationTask task = compiler.getTask(
            null, files, collector,
            List.of("--release", "17", "-encoding", "UTF-8",
                    "-proc:none", "-d", "target/compiler-fixtures"),
            null, sources);

    boolean succeeded = Boolean.TRUE.equals(task.call());
    // Kiểm tra collector.getDiagnostics() ở đây.
}
```

Đoạn trên là **snippet minh họa**, yêu cầu file fixture và thư mục đầu ra `target/compiler-fixtures` đã được tạo (hoặc tạo trước khi chạy); tùy compiler, đường dẫn đầu ra không tồn tại có thể gây lỗi tùy chọn thay vì diagnostic lỗi Java mong muốn. Đối với build trên Windows, macOS, Linux, dùng `Path`/file manager để tránh tự ghép separator. Khi fixture có dependency, truyền `-classpath` với đường dẫn cụ thể và `File.pathSeparator` hoặc cấu hình StandardJavaFileManager locations; đừng để classpath mặc định của test runner vô tình ảnh hưởng kết quả.

Lưu ý phân biệt các lỗi:

| Tình huống | Triệu chứng | Cách xử lý trong test |
| --- | --- | --- |
| Java source sai kiểu/cú pháp | `ERROR` có source/location phù hợp | Test negative compile theo kind + source + line |
| Thiếu dependency classpath | `cannot find symbol`/`package ... does not exist` | Cố định classpath và fixture |
| `-d` không hợp lệ, option sai | Task có thể ném `IllegalArgumentException` hoặc báo lỗi setup | Xử lý như lỗi **hạ tầng test**, không coi pass |
| Runtime không có system compiler | `getSystemJavaCompiler() == null` | Fail-fast với thông báo cần JDK |
| Processor thiếu hoặc chạy sai | Diagnostics từ processor hoặc class sinh bị thiếu | Khai báo processor path và test riêng |
| Compilation thành công kèm warning | `ok == true`, danh sách có `WARNING` | Kiểm tra severity riêng với chính sách |
| Không có vị trí nguồn | `source == null` hoặc `NOPOS` | Ghi nhận global diagnostic, tránh dùng line/cột bừa |

Nếu bạn dùng annotation processor trong bộ kiểm thử, phải cho phép `-proc:full` hoặc khai báo processor theo cách tương thích JDK, rồi kiểm tra diagnostics từ processor. Đối với bài kiểm thử compiler core thuần, `-proc:none` giúp loại nhiễu.

## 10. Thiết kế assertion ổn định cho CI

Một bộ test compilation tốt có hai lớp:

**Lớp 1 – API contract ổn định:**

- Task outcome (true/false) với JDK được lựa chọn.
- `Diagnostic.Kind` là loại enum cần tìm.
- `getSource()` trỏ đúng file fixture; line/range được xác minh khi đó là phần contract.
- `Diagnostic.NOPOS` được xử lý rõ cho global diagnostics.
- Diagnostic xuất hiện ít nhất một lần; không giả định thứ tự danh sách không được đảm bảo bởi use case.

**Lớp 2 – Chi tiết compiler cụ thể:**

- `getCode()` theo `javac` bản đã pin.
- `getMessage(Locale.ROOT)` hoặc bản tiếng Anh để hiển thị/log.
- Exact column/highlight/caret và thứ tự nhiều diagnostics.
- Số lượng warnings khi bật `-Xlint`, processor hoặc `-Werror`.

Chỉ snapshot lớp 2 nếu cần test chính **hành vi cụ thể của compiler** hoặc toolchain đã pin. Nếu mục tiêu của sản phẩm là “hệ thống báo lỗi đúng chỗ”, assertion lớp 1 kết hợp fixture tối giản là lựa chọn bền vững hơn.

### 10.1. Báo lỗi assertion có đủ thông tin

Khi không tìm được diagnostic mong đợi, failure report nên in danh sách đã thu được theo dạng có cấu trúc:

```text
Expected:
  ERROR, source=demo/Broken.java, line=4
Observed:
  kind, source URI, line, column, code, message (debug-only)
Build environment:
  JDK version, compiler options, source fixture hash
```

Đây là **định dạng report đề xuất**, không phải stdout cố định từ Java. Cần escape newline trong `getMessage()` nếu in mỗi diagnostic trên một dòng. Không dùng một bản dịch message cụ thể làm golden output khi CI chạy trên JDK/locales khác.

### 10.2. Ngăn “pass giả” trong negative compilation

Nếu chỉ assert “có ít nhất một ERROR ở dòng 4”, một file phức tạp có thể có hai lỗi khác nhau cùng dòng. Khi test có yêu cầu nghiêm ngặt, thu hẹp fixture về **một phép gán sai kiểu** như ví dụ chính, xác minh URI và thêm code hoặc message fragment **sau khi đã pin compiler**. Không viết assertion chung kiểu “có lỗi bất kỳ”.

Đối với test warning, nên có một “positive control”: compile lại với `-Xlint:deprecation` tắt hoặc sử dụng source đã sửa, để bảo đảm warning biến mất đúng nguyên nhân. Tương tự, sửa `int count = "wrong";` thành `int count = 1;` và xác minh compilation thành công có thể phát hiện bug của harness.

## 11. Troubleshooting nhanh

| Vấn đề | Nguyên nhân điển hình | Hành động |
| --- | --- | --- |
| `compiler == null` | Runtime image thiếu `jdk.compiler`, chạy trên môi trường chỉ có JRE | Chạy bằng JDK đầy đủ hoặc cung cấp compiler rõ ràng |
| Biên dịch thất bại nhưng collector trống | Tool lỗi trước khi nhận task, options invalid, exception/setup | Phân biệt exception, kiểm tra output writer và options |
| Kỳ vọng dòng 4 nhưng nhận dòng khác | Text block indentation, newline, source khác fixture | In lại source thực với số dòng; cố định LF |
| Cột khác giữa IDE và javac | IDE dùng compiler hoặc rule khác, tab/Unicode khác | Pin compiler, chuẩn hóa source, ưu tiên line khi cần portability |
| Có warning nhưng task vẫn true | Warning không mặc định là lỗi | Assert `Kind` hoặc bật `-Werror` theo policy |
| `getSource()` null | Diagnostic toàn cục, không gắn file | Xử lý `NOPOS` và fail rõ nếu test cần source |
| Không thấy warning deprecated | Chưa bật `-Xlint:deprecation`, source không còn gọi API cũ | Kiểm tra flags/source/annotations |
| Thông điệp khác CI | JDK/vendor/locale thay đổi | Dùng `Locale.ROOT` để log và không assert nguyên câu |
| Test lỗi vì thiếu class bên thứ ba | Classpath task không đúng | Cấp explicit classpath/module path, version và file manager |
| Diagnostic order thay đổi | Compiler phase và lỗi kéo theo khác nhau | Filter/map theo kind + source + line, không index `[0]` |
| Java test source bị ký tự BOM | Encoding lúc lưu file | Lưu UTF-8 không BOM và đọc nguồn bằng charset rõ ràng |

## 12. Bài tập tự kiểm tra

1. Đổi phép gán ở dòng 4 từ `"wrong"` sang `1`. Xác minh `ok == true`, `errorCount == 0` và `hasLine4Error == false`. Chạy bài kiểm thử hai lần, dùng collector mới cho mỗi lần.
2. Thêm một câu lệnh lỗi trên dòng khác. Lọc ra hai `ERROR` theo line, không phụ thuộc thứ tự; quan sát compiler có thể phát thêm lỗi kéo theo.
3. Chạy fixture deprecated ở phần 6 với và không có `-Xlint:deprecation`; so sánh `Kind` và vị trí, rồi bật `-Werror` để xem kết quả task.
4. Viết helper trả danh sách các bản ghi `(kind, sourceUri, line, column, code)`; xử lý `null`/`NOPOS` và sắp xếp trước khi so snapshot.
5. Thử một diagnostic không có location (ví dụ lỗi cấu hình thực tế); xác minh formatter của bạn không ném `NullPointerException` hoặc `StringIndexOutOfBoundsException`.
6. Thử file source có ký tự tiếng Việt hoặc emoji trước dòng lỗi; phân biệt byte offset UTF-8 với offset ký tự và tránh cắt hỏng surrogate pairs.

**Tiêu chí đạt:** một lỗi/warning được bắt theo đúng mức độ và vị trí trong fixture, hành vi khi không có vị trí được xử lý an toàn, và test không phụ thuộc vào thông điệp ngôn ngữ tự nhiên nếu không cần thiết.

## Tài liệu API chính thức

- Java SE 17 – `javax.tools.Diagnostic`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/Diagnostic.html
- Java SE 17 – `javax.tools.JavaCompiler`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html
- Java SE 17 – `javax.tools.DiagnosticCollector`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/DiagnosticCollector.html
- Java SE 17 – `javax.tools` package: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/package-summary.html
- Java SE 17 – `ToolProvider`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ToolProvider.html
- Java SE 17 – `javac` options: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html