# DiagnosticCollector và thông tin lỗi, cảnh báo trong Java Compiler API

`javax.tools.DiagnosticCollector<S>` là một lớp chuẩn của Java Compiler API để **thu thập lỗi, cảnh báo và các thông báo chẩn đoán thành dữ liệu có cấu trúc**. API này xuất hiện từ Java 6 nhưng vẫn được hỗ trợ và sử dụng trên Java 17+.

Khi ứng dụng gọi compiler bằng `JavaCompiler`, kết quả không chỉ là một chuỗi log từ terminal. Mỗi `Diagnostic` có thể cung cấp loại thông báo (`ERROR`, `WARNING`...), vị trí dòng/cột, nguồn, mã diagnostic và message. Đây là cơ sở để làm IDE, trình chấm bài, công cụ kiểm tra Java source và báo cáo CI.

**Điểm cốt lõi:** `DiagnosticCollector` thu thông báo, còn `CompilationTask.call()` quyết định thành bại của lần biên dịch. Có warning chưa chắc compile thất bại; compile thất bại cũng có thể liên quan đến cấu hình hoặc output không được biểu diễn đầy đủ bằng một diagnostic ở dòng source.

## 1. Mục tiêu

Sau bài này, bạn cần biết:

1. Gắn `DiagnosticCollector<JavaFileObject>` vào `JavaCompiler.getTask(...)` và gọi `call()`.
2. Đọc `Diagnostic.Kind`, dòng/cột và message mà không giả định mọi diagnostic có vị trí source.
3. Phân biệt `ERROR`, `WARNING`, `MANDATORY_WARNING`, `NOTE` và `OTHER`.
4. Dùng `-Xlint` và `-Werror` đúng mục đích; giải thích tại sao kết quả biên dịch có thể khác số lượng lỗi.
5. Chuyển diagnostics thành dữ liệu dành cho giao diện hoặc CI một cách an toàn, không phụ thuộc vào câu chữ của message.
6. Sử dụng nguồn Java trên disk hoặc trong bộ nhớ, quản lý `StandardJavaFileManager` và compiler runtime.

## 2. Các thành phần tham gia

```text
JavaFileObject (source file hoặc source trong bộ nhớ)
            |
            v
JavaCompiler -> CompilationTask.call() -> Boolean success
            |
            | report(Diagnostic)
            v
DiagnosticCollector<JavaFileObject>
            |
            v
getDiagnostics() -> List<Diagnostic<? extends JavaFileObject>>
            |
            +-- kind, code, message
            +-- source, line, column, start/end/position
            |
            v
Log / UI / trình chấm bài / báo cáo CI
```

| Thành phần | Vai trò |
| --- | --- |
| `ToolProvider.getSystemJavaCompiler()` | Lấy compiler của Java runtime. Có thể trả `null` nếu runtime không cung cấp `jdk.compiler`. |
| `JavaCompiler` | API biên dịch source từ chương trình Java. |
| `JavaCompiler.CompilationTask` | Đại diện một tác vụ biên dịch; `call()` chạy task và trả Boolean kết quả. |
| `JavaFileObject` | Biểu diễn source/class file, có thể là file thật hoặc object chứa mã nguồn trong bộ nhớ. |
| `StandardJavaFileManager` | Đọc source, tìm dependencies và quản lý output; nên đóng bằng `try-with-resources`. |
| `DiagnosticListener<S>` | Interface nhận thông báo khi compiler gọi `report(Diagnostic<? extends S>)`. |
| `DiagnosticCollector<S>` | Listener có sẵn để thu diagnostic vào list rồi đọc lại. |
| `Diagnostic<S>` | Một thông báo lỗi/cảnh báo với dữ liệu có cấu trúc. |

Các interface Compiler API thuộc module chuẩn `java.compiler`. Compiler hệ thống được cung cấp qua module `jdk.compiler` trong bản JDK thông dụng. Nếu dùng runtime image tối giản, cần kiểm tra `getSystemJavaCompiler() != null` trước khi gọi các phương thức khác.

### Luồng gọi cơ bản

```java
// Đoạn API minh họa, chưa phải chương trình độc lập:
// compiler, compilationUnits cần được khởi tạo/kiểm tra trước.
DiagnosticCollector<JavaFileObject> collector = new DiagnosticCollector<>();

try (StandardJavaFileManager manager =
             compiler.getStandardFileManager(collector, null, null)) {
    JavaCompiler.CompilationTask task = compiler.getTask(
            null,              // Writer nhận output khác (nếu có)
            manager,           // JavaFileManager
            collector,         // listener nhận diagnostic
            null,              // danh sách compiler options
            null,              // class names cho annotation processing
            compilationUnits); // các JavaFileObject cần biên dịch

    Boolean success = task.call();
    for (Diagnostic<? extends JavaFileObject> d
            : collector.getDiagnostics()) {
        // Chuyển d thành báo cáo.
    }
}
```

Có thể truyền cùng collector cho `getStandardFileManager` và `getTask`. Một số thông báo file manager và compiler sẽ được chuyển tới listener. **Không bảo đảm mọi vấn đề đều có Diagnostic:** một số thông báo vẫn có thể được ghi qua `Writer` hoặc output mặc định, và lỗi nghiêm trọng có thể phát sinh exception.

## 3. `Diagnostic.Kind`: lỗi, cảnh báo và ghi chú

| Kind | Ý nghĩa |
| --- | --- |
| `ERROR` | Lỗi ngăn compiler hoàn thành bình thường, chẳng hạn gán chuỗi cho biến `int`. |
| `WARNING` | Cảnh báo không nhất thiết ngăn biên dịch thành công. |
| `MANDATORY_WARNING` | Cảnh báo phải được công cụ báo trong những trường hợp đặc tả yêu cầu. |
| `NOTE` | Thông báo bổ sung, thường để giải thích hoặc cung cấp ngữ cảnh. |
| `OTHER` | Diagnostic không thuộc các nhóm kể trên. |

Cần xử lý cả hai nhóm warning khi thống kê:

```java
// Đoạn biểu thức minh họa, biến d có kiểu Diagnostic<?>.
boolean isWarning = d.getKind() == Diagnostic.Kind.WARNING
        || d.getKind() == Diagnostic.Kind.MANDATORY_WARNING;
```

`WARNING` thông thường cho phép compilation task hoàn thành, nên `success=true` vẫn có thể đi cùng warning. Nhưng tùy chọn `-Werror` của `javac` có thể khiến cảnh báo làm compile thất bại. Vì vậy không thay thế `task.call()` bằng phép tính `errorCount == 0`.

## 4. Trích xuất thông tin từ mỗi `Diagnostic`

| API | Ý nghĩa, giới hạn |
| --- | --- |
| `getKind()` | Phân loại diagnostic, dùng để quyết định severity. |
| `getSource()` | Source object, có thể `null` nếu thông báo không gắn với file. |
| `getLineNumber()` | Dòng **bắt đầu từ 1**, hoặc `Diagnostic.NOPOS` khi không có vị trí. |
| `getColumnNumber()` | Cột **bắt đầu từ 1**, hoặc `Diagnostic.NOPOS`. |
| `getPosition()` | Offset ký tự tính từ đầu source, **bắt đầu từ 0**; có thể `NOPOS`. |
| `getStartPosition()` | Offset đầu vùng liên quan đến lỗi; có thể `NOPOS`. |
| `getEndPosition()` | Offset cuối vùng liên quan đến lỗi; có thể `NOPOS`. |
| `getCode()` | Mã diagnostic phụ thuộc implementation; có thể `null`, không nên coi là định danh phổ quát. |
| `getMessage(Locale)` | Message theo locale được yêu cầu; nội dung phụ thuộc compiler/version/locale. |

`Diagnostic.NOPOS` biểu diễn vị trí không xác định (thường có giá trị `-1`). Đừng dùng `line == 0` để phát hiện “không có dòng”: với API này dòng/cột hợp lệ bắt đầu từ **1**. Không biến offset source thành byte offset UTF-8 hoặc áp dụng vị trí lên source đã thay đổi kể từ lúc biên dịch.

### Helper định vị an toàn

Đây là **method minh họa**, có thể đặt vào một class sau khi import `javax.tools.Diagnostic` và `javax.tools.JavaFileObject`:

```java
static String location(Diagnostic<? extends JavaFileObject> d) {
    String sourceName = (d.getSource() == null)
            ? "<no-source>"
            : d.getSource().getName();

    if (d.getLineNumber() == Diagnostic.NOPOS) {
        return sourceName;
    }
    if (d.getColumnNumber() == Diagnostic.NOPOS) {
        return sourceName + ":" + d.getLineNumber();
    }
    return sourceName + ":" + d.getLineNumber()
            + ":" + d.getColumnNumber();
}
```

Không nên gọi `d.getSource().toUri()` trước khi kiểm tra `getSource()!=null`. Với lỗi cấu hình compiler hoặc cảnh báo không gắn file, hãy hiển thị thông báo toàn cục và bỏ thông tin vị trí thay vì tự điền một dòng giả.

## 5. Ví dụ hoàn chỉnh: thu thập ERROR từ source trong bộ nhớ

Ví dụ Java 17+ dưới đây biên dịch một class `Broken` *cố ý có lỗi kiểu dữ liệu*. Chương trình `CollectDiagnosticsDemo` itself hợp lệ và chạy bình thường; source được compiler xử lý trong chương trình mới bị lỗi.

Tạo tệp **`CollectDiagnosticsDemo.java`**:

```java
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Locale;
import javax.tools.*;

public final class CollectDiagnosticsDemo {
    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK compiler unavailable");
        }

        String source = "class Broken {\n"
                + "    int count = \"wrong\";\n"
                + "}\n";

        JavaFileObject unit = new SimpleJavaFileObject(
                URI.create("string:///Broken.java"),
                JavaFileObject.Kind.SOURCE) {
            @Override
            public CharSequence getCharContent(boolean ignoreEncodingErrors) {
                return source;
            }
        };

        DiagnosticCollector<JavaFileObject> collector =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager files =
                     compiler.getStandardFileManager(
                             collector, Locale.ENGLISH,
                             StandardCharsets.UTF_8)) {

            Boolean success = compiler.getTask(
                    null,
                    files,
                    collector,
                    List.of("-proc:none"),
                    null,
                    List.of(unit)).call();

            System.out.println("compiled=" + success);

            long errors = collector.getDiagnostics().stream()
                    .filter(d -> d.getKind() == Diagnostic.Kind.ERROR)
                    .count();
            System.out.println("errors=" + errors);

            for (Diagnostic<? extends JavaFileObject> d
                    : collector.getDiagnostics()) {
                System.out.println(d.getKind()
                        + " line=" + d.getLineNumber());
            }
        }
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 CollectDiagnosticsDemo.java
java CollectDiagnosticsDemo
```

**Stdout được kiểm chứng trên JDK 24:**

```text
compiled=false
errors=1
ERROR line=2
```

**Giải thích từng bước:**

1. `SimpleJavaFileObject` mô tả source dưới URI `string:///Broken.java` với `Kind.SOURCE`. Phương thức `getCharContent` trả chuỗi source cần kiểm tra.
2. `String source` có ba dòng, trong đó dòng 2 gán `"wrong"` cho `int count`; compiler phát hiện sai kiểu.
3. `DiagnosticCollector<JavaFileObject>` nhận lỗi qua `DiagnosticListener`.
4. `-proc:none` vô hiệu annotation processing trong lần compile thử này.
5. `call()` trả `false` và collector có một diagnostic `ERROR` tại dòng 2.
6. Chương trình in kind/line thay vì in nguyên văn `getMessage()` vì thông báo chi tiết không được bảo đảm giống nhau trên mọi phiên bản JDK.

Ví dụ không tạo `Broken.class` vì compilation task của `Broken` thất bại. Lệnh `javac` chạy trước đó chỉ biên dịch chương trình demo hợp lệ.

## 6. Ví dụ hoàn chỉnh: thu thập WARNING dù compile thành công

Mã sau cố ý dùng một raw generic type để compiler phát cảnh báo khi bật `-Xlint:rawtypes`. Đây là **tình huống để phát hiện cách dùng cần cải tiến**, không phải khuyến nghị viết code raw generic.

Tạo tệp **`WarningDiagnosticsDemo.java`**:

```java
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import javax.tools.*;

public final class WarningDiagnosticsDemo {
    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK compiler unavailable");
        }

        String source = "import java.util.*;\n"
                + "public class RawExample {\n"
                + "    List names = new ArrayList<String>();\n"
                + "}\n";

        JavaFileObject unit = new SimpleJavaFileObject(
                URI.create("string:///RawExample.java"),
                JavaFileObject.Kind.SOURCE) {
            @Override
            public CharSequence getCharContent(boolean ignoreEncodingErrors) {
                return source;
            }
        };

        Path output = Files.createTempDirectory("diag-class-output-");
        try {
            DiagnosticCollector<JavaFileObject> collector =
                    new DiagnosticCollector<>();

            try (StandardJavaFileManager files =
                         compiler.getStandardFileManager(
                                 collector, Locale.ENGLISH,
                                 StandardCharsets.UTF_8)) {

                Boolean success = compiler.getTask(
                        null,
                        files,
                        collector,
                        List.of("-proc:none", "-Xlint:rawtypes",
                                "-d", output.toString()),
                        null,
                        List.of(unit)).call();

                boolean hasWarning = collector.getDiagnostics().stream()
                        .anyMatch(d ->
                                d.getKind() == Diagnostic.Kind.WARNING
                                || d.getKind() == Diagnostic.Kind.MANDATORY_WARNING);

                System.out.println("compiled=" + success);
                System.out.println("hasWarning=" + hasWarning);
            }
        } finally {
            try (var paths = Files.walk(output)) {
                for (Path p : paths.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(p);
                }
            }
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 WarningDiagnosticsDemo.java
java WarningDiagnosticsDemo
```

**Stdout được kiểm chứng trên JDK 24:**

```text
compiled=true
hasWarning=true
```

Lý do: source `RawExample` hợp lệ nên `call()` trả `true`, nhưng `List names` dùng raw type nên collector nhận warning khi bật `-Xlint:rawtypes`. Output class được tạo ở thư mục tạm rồi xóa trong `finally`. Ví dụ chủ động không assert exact warning count/message, vì nội dung và số lượng có thể thay đổi theo compiler.

## 7. Các tùy chọn hiện hành ảnh hưởng lỗi và cảnh báo

| Tùy chọn `javac` | Ý nghĩa |
| --- | --- |
| `-Xlint:rawtypes` | Cảnh báo sử dụng raw types. |
| `-Xlint:unchecked` | Cảnh báo thao tác generic không được kiểm tra đầy đủ. |
| `-Xlint:deprecation` | Cảnh báo truy cập các API đã đánh dấu deprecation. |
| `-Xlint:all` | Bật các nhóm lint theo triển khai compiler. |
| `-Werror` | Yêu cầu compiler coi warning là lý do thất bại. |
| `-Xdiags:verbose` | Yêu cầu javac cung cấp thông tin chẩn đoán chi tiết hơn. |
| `--release 17` | Biên dịch theo mức Java release được hỗ trợ cùng các public API của release mục tiêu. |
| `-proc:none` | Tắt annotation processing trong tác vụ biên dịch. |
| `-d <path>` | Chỉ định thư mục chứa class file đầu ra. |

Khi truyền vào `JavaCompiler.getTask`, options là một `Iterable<String>`, ví dụ:

```java
// Đoạn code minh họa trong một chương trình đã có outputDirectory:
List<String> options = List.of(
        "--release", "17",
        "-Xlint:unchecked",
        "-Xlint:deprecation",
        "-d", outputDirectory.toString());
```

Nếu bật `-Werror`, compilation task có thể trả `false` do warning, kể cả khi code không chứa lỗi cú pháp hay kiểu dữ liệu. Vì vậy logic kiểm tra build phải đọc kết quả từ `call()` và phân tích diagnostics riêng. Có thể khóa JDK toolchain trong CI để tránh biến động cảnh báo khi nâng cấp compiler.

Đừng cố parse text từ stdout/stderr để đếm ERROR/WARNING. Nội dung message tùy compiler/locale; `Kind` được API thiết kế cho việc phân loại đó.

## 8. Sử dụng danh sách diagnostics an toàn

`DiagnosticCollector.getDiagnostics()` trả **list view** các diagnostic đã thu thập. Để tạo snapshot danh sách sau khi compiler hoàn thành:

```java
// Đoạn tích hợp, giả định compiler/fileManager/options/units đã có.
DiagnosticCollector<JavaFileObject> collector = new DiagnosticCollector<>();
Boolean success = compiler.getTask(
        null, fileManager, collector, options, null, units).call();

List<Diagnostic<? extends JavaFileObject>> snapshot =
        List.copyOf(collector.getDiagnostics());
```

Đây không phải chương trình độc lập; nó minh họa ý tưởng chụp lại danh sách. Không tái sử dụng cùng collector vô hạn cho nhiều compilation task nếu không muốn thông báo cũ lẫn với thông báo mới. Mẫu dễ quản lý là **một collector cho một task**.

Nếu chỉ muốn xử lý mỗi thông báo ngay khi được phát hiện mà không cần lưu list, tự triển khai `DiagnosticListener<JavaFileObject>`:

```java
// Đoạn minh họa, cần import javax.tools.* và java.util.Locale.
DiagnosticListener<JavaFileObject> listener = diagnostic -> {
    if (diagnostic.getKind() == Diagnostic.Kind.ERROR) {
        System.err.println(diagnostic.getMessage(Locale.ENGLISH));
    }
};
```

`DiagnosticCollector` chính là một implementation của interface listener này. Lựa chọn tùy nhu cầu: collector tiện cho báo cáo sau task; listener tùy biến tiện để chuyển sự kiện trực tiếp vào logging hoặc pipeline khác.

### Không coi message là API ổn định

`getMessage(Locale.ENGLISH)` trả thông điệp dành cho người đọc, nhưng wording có thể thay đổi giữa các bản JDK. `getCode()` cũng phụ thuộc implementation và có thể null. Với UI hoặc JSON API, hãy lưu riêng các trường dạng:

```json
{
  "kind": "ERROR",
  "source": "Broken.java",
  "line": 2,
  "column": null,
  "code": null,
  "message": "Human-readable compiler explanation"
}
```

Đây là **mô hình payload**, không phải output thực tế đã kiểm chứng: cột/mã/message đã để dạng minh họa. Khi trả payload thật, dùng `getColumnNumber()` nếu có vị trí; thay `Diagnostic.NOPOS` bằng `null` hoặc biểu diễn thiếu vị trí nhất quán với API của bạn.

### Nguồn không phải lúc nào cũng là tệp trên disk

`JavaFileObject` có thể là file thật, một entry trong archive hoặc dữ liệu bộ nhớ. `getSource().toUri()` vì thế có thể có scheme khác `file`. Với đường dẫn cho UI, chuẩn hóa URI có kiểm soát, tránh giả định mọi source đều là một path của máy người dùng.

## 9. Biên dịch nguồn Java trên ổ đĩa

Với ứng dụng dùng source file thực, `StandardJavaFileManager` cung cấp cách tạo units từ `Path`. Đoạn sau là **mảnh code để đặt trong chương trình có manager**, không phải ví dụ độc lập:

```java
Iterable<? extends JavaFileObject> units =
        manager.getJavaFileObjectsFromPaths(
                List.of(Path.of("src", "Example.java")));
```

Truyền `units` vào `getTask(...)`. Hãy cấu hình classpath/module path, output directory, encoding và `--release` theo dự án. Với ứng dụng modular, compiler có thể cần `--module-path` hoặc `--module-source-path`. Không tự giả định công cụ sẽ hiểu dependencies của build system.

Khi xây IDE hoặc công cụ build, dùng `Diagnostic` để định vị vấn đề và `JavaCompiler` để xử lý task; `JavaFileManager` có thể được tùy biến qua forwarding wrappers nếu cần đọc source/output từ môi trường khác. Đối với tác vụ thông thường, `StandardJavaFileManager` là lựa chọn phù hợp và dễ duy trì.

## 10. Phân biệt diagnostics, exceptions và độ an toàn

- **Compile thất bại**: `call()` có thể trả `false`. Đọc các `ERROR` và thông báo bổ sung, nhưng không giả định tất cả nguyên nhân đều được biểu diễn dưới dạng diagnostic có dòng nguồn.
- **Tùy chọn không hợp lệ**: `JavaCompiler.getTask` có thể ném `IllegalArgumentException`. Đây là lỗi cấu hình API, cần bắt/đưa ra thông báo riêng, không thay thế bằng việc đếm diagnostics.
- **File manager hoặc plugin gặp lỗi**: có thể phát sinh exception. Kiểm tra stack trace/cause, đóng tài nguyên và đừng nuốt lỗi một cách im lặng.
- **Mã nguồn chưa tin cậy**: Compiler API không tự cung cấp sandbox. `-proc:none` tắt annotation processing, nhưng một môi trường biên dịch không tin cậy vẫn cần cách cô lập và giới hạn tài nguyên thích hợp.
- **Khả năng tái sử dụng**: mỗi `CompilationTask` là một lần biên dịch; để chạy lại, tạo task mới. Có thể tái dùng file manager cho các lần biên dịch tuần tự với vòng đời được quản lý, nhưng nên có collector riêng để tách báo cáo.
- **Dữ liệu Unicode**: offset ký tự của diagnostic không phải offset byte; source đã thay đổi cũng làm vị trí cũ mất nghĩa. Dùng đúng bản source mà compiler đã kiểm tra.

## 11. Các lỗi thường gặp

| Vấn đề | Nguyên nhân và cách sửa |
| --- | --- |
| `getSystemJavaCompiler()` trả `null` | Runtime thiếu system compiler. Sử dụng JDK hoặc runtime image chứa `jdk.compiler` và kiểm tra null trước khi dùng. |
| Không thấy lỗi trong collector | Quên truyền listener vào `getTask`, đang đọc sai collector hoặc vấn đề xuất hiện qua Writer/exception. |
| Gọi `getSource().toUri()` bị NPE | Diagnostic không gắn source; kiểm tra `getSource()!=null` trước khi lấy tên hoặc URI. |
| Dòng/cột có giá trị `-1` | Đây là `Diagnostic.NOPOS`; trình bày như vị trí không xác định. |
| Cảnh báo không hiện | Chưa bật nhóm `-Xlint` tương ứng, hoặc source không gây warning; kiểm tra compiler options. |
| Có warning nhưng `success=true` | Warning thường không ngăn task hoàn thành. Dùng chính sách `-Werror` nếu nhóm phát triển yêu cầu fail build do warning. |
| `success=false` nhưng không đếm thấy ERROR tương ứng | Xem options như `-Werror`, Writer, exceptions và lỗi môi trường; không suy ra success chỉ từ error count. |
| Test fail sau nâng cấp JDK | Assert nguyên văn `getMessage()` hoặc số lượng warning cố định; thay bằng kind, vị trí và kiểm tra kết quả trong môi trường kiểm soát. |
| Diagnostic của lần trước lẫn lần sau | Collector bị tái sử dụng; tạo mới theo task. |
| Compiler tạo file ở thư mục không mong muốn | Không cấu hình `-d`; chọn output directory rõ và dọn artifact sau test. |
| UI trỏ tới vị trí sai | Dùng byte offsets hoặc source mới hơn source được compile; giữ phiên bản source tương ứng và kiểm tra NOPOS. |

## 12. Checklist khi tích hợp Compiler API vào hệ thống

1. **Môi trường:** xác nhận compiler hiện diện và JDK phiên bản phù hợp.
2. **Nguồn:** chuẩn bị `JavaFileObject` với content, URI, encoding đúng.
3. **Listener:** cấp `DiagnosticCollector<JavaFileObject>` cho tác vụ và file manager khi phù hợp.
4. **Options:** đặt `-Xlint`, `--release`, `-d` và classpath/module path phù hợp với mục tiêu.
5. **Thực thi:** gọi `CompilationTask.call()` đúng một lần cho task.
6. **Báo cáo:** lấy diagnostics; đếm ERROR và hai nhóm WARNING, đồng thời giữ riêng giá trị `success`.
7. **Vị trí:** kiểm tra `getSource()==null` và `Diagnostic.NOPOS` trước khi tạo liên kết tới mã nguồn.
8. **Thông điệp:** dùng `getMessage(Locale)` cho người đọc; tránh phụ thuộc vào exact text/code.
9. **Vòng đời:** đóng file manager, phân tách collector giữa các lần compile, dọn output tạm.
10. **QA:** kiểm thử tình huống source hợp lệ, source có error, source có warning và runtime không có compiler nếu sản phẩm cần hỗ trợ.

## 13. Tự kiểm tra kiến thức

**Câu 1.** `DiagnosticCollector` có tự chạy compiler không?

**Đáp án:** Không. Nó triển khai `DiagnosticListener` để lưu thông báo. Ứng dụng phải tạo `JavaCompiler.CompilationTask` và gọi `call()`.

**Câu 2.** Vì sao `compiled=true` vẫn có thể đi cùng warning?

**Đáp án:** WARNING và MANDATORY_WARNING thường không làm compilation task thất bại. Chính sách của compiler, như `-Werror`, có thể thay đổi kết quả.

**Câu 3.** Cần kiểm tra gì trước khi lấy tên file và số dòng?

**Đáp án:** `getSource()` có thể null; `getLineNumber()` và `getColumnNumber()` có thể bằng `Diagnostic.NOPOS`. Không tạo vị trí giả nếu thiếu dữ liệu.

**Câu 4.** Vì sao không dùng chuỗi `getMessage(Locale)` làm khóa cố định cho bài test?

**Đáp án:** Message phụ thuộc compiler, JDK và locale. `Diagnostic.Kind` và kết quả `call()` là đầu vào có cấu trúc thích hợp hơn.

**Câu 5.** Khi nào tự viết `DiagnosticListener`?

**Đáp án:** Khi cần xử lý từng diagnostic theo thời gian thực, ví dụ gửi đến pipeline log; nếu cần list để đọc sau khi compile, `DiagnosticCollector` tiện hơn.

## Nguồn chính thức còn phù hợp

- [DiagnosticCollector — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/DiagnosticCollector.html)
- [Diagnostic — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/Diagnostic.html)
- [JavaCompiler — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/JavaCompiler.html)
- [ToolProvider — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/ToolProvider.html)
- [javac Command — Java SE 25 Tool Reference](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html)

**Ghi nhớ:** `DiagnosticCollector` thu thập thông báo biên dịch thành dữ liệu có cấu trúc; `CompilationTask.call()` cung cấp kết quả task. Muốn báo cáo chính xác, hãy xử lý `Kind`, source, line/column và `NOPOS`, đồng thời không phụ thuộc vào văn bản diagnostic thay đổi theo compiler.
