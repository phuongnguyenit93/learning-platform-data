# Thu thập lỗi, cảnh báo, vị trí nguồn và thông điệp bằng DiagnosticCollector

Khi một chương trình Java **biên dịch mã nguồn lúc chạy** bằng `javax.tools.JavaCompiler`, người dùng cần biết nhiều hơn một giá trị `true` hoặc `false`: **mã bị lỗi ở tệp nào, dòng/cột nào, thông điệp lỗi là gì, có cảnh báo nào dù biên dịch thành công hay không**. API `javax.tools.DiagnosticCollector` giúp thu thập những chẩn đoán đó dưới dạng dữ liệu có cấu trúc để hiển thị trong IDE, trình chỉnh sửa luật, trình tạo mã, công cụ học Java hoặc hệ thống plugin.

Điều cốt lõi là phân biệt:

- **Kết quả của tác vụ biên dịch**: `CompilationTask.call()` trả `Boolean.TRUE` khi compiler báo thành công, `Boolean.FALSE` khi báo thất bại; lỗi hạ tầng/khởi tạo tác vụ còn có thể xuất hiện qua exception.
- **Diagnostic**: mỗi lỗi, cảnh báo hoặc thông báo có loại (`kind`), nguồn (`source`), vị trí và thông điệp (`message`). Nhiều diagnostic có thể cùng xuất hiện trong một lượt biên dịch.
- **DiagnosticCollector**: implementation sẵn có của `DiagnosticListener`, giữ các diagnostic trong danh sách để ứng dụng đọc sau hoặc trong lúc compiler báo sự cố.

Một mã nguồn **biên dịch thành công vẫn có thể có WARNING**; ngược lại, không nên suy ra toàn bộ tác vụ thành công chỉ vì danh sách lỗi bạn đếm được bằng 0. Trạng thái `call()` mới là kết quả của tác vụ, còn diagnostics giải thích điều gì đã xảy ra.

## 1. Pipeline thu thập diagnostic

Luồng thông dụng với JDK 17+:

```text
Java source (.java hoặc JavaFileObject trong bộ nhớ)
                       |
                       v
            JavaCompiler.getTask(...)
             /          |           \
            /           |            \
StandardJavaFileManager  options    DiagnosticCollector
            \           |            /
             \          |           /
                 task.call()
                     |
       +-------------+-------------+
       |                           |
  boolean success          collector.getDiagnostics()
                                   |
                            Diagnostic<?>
                                   |
                kind / source / line / column /
                 position / code / message
                                   |
                  log / API / IDE / báo lỗi
```

Các loại API nằm trong module chuẩn `java.compiler`, package `javax.tools`:

| API | Vai trò |
|---|---|
| `ToolProvider.getSystemJavaCompiler()` | Lấy compiler Java đang có trong runtime; có thể trả `null` nếu image không có compiler |
| `JavaCompiler` | Tạo compilation task, làm việc với file manager và listener |
| `JavaCompiler.CompilationTask` | Tác vụ biên dịch cụ thể; `call()` thực hiện một lượt biên dịch |
| `StandardJavaFileManager` | Quản lý các `JavaFileObject` từ file, classpath/module path và output location |
| `JavaFileObject` | Đại diện nguồn/đầu ra Java mà compiler làm việc; có thể trỏ đến file hoặc được tạo trong bộ nhớ |
| `DiagnosticListener<S>` | Interface nhận diagnostic theo cơ chế callback `report(...)` |
| `DiagnosticCollector<S>` | Listener lưu diagnostic để lấy lại bằng `getDiagnostics()` |
| `Diagnostic<S>` | Một chẩn đoán và các thuộc tính phục vụ hiển thị/phân tích |

**Phân biệt với `compiler.run(...)`:** phương thức `run` thuận tiện như một lệnh biên dịch có các stream đầu vào/đầu ra và trả exit status. Khi cần **danh sách lỗi có cấu trúc**, hãy dùng `getTask(...)` với `DiagnosticCollector`; không nên parse thông báo console của `javac` bằng regex.

## 2. Khởi tạo collector và truyền đúng vào compiler

Mẫu thiết lập tối thiểu:

```java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    throw new IllegalStateException(
            "A JDK containing the Java compiler is required");
}

DiagnosticCollector<JavaFileObject> collector =
        new DiagnosticCollector<>();

try (StandardJavaFileManager manager =
        compiler.getStandardFileManager(
                collector, Locale.ROOT, StandardCharsets.UTF_8)) {

    Iterable<? extends JavaFileObject> units =
            manager.getJavaFileObjectsFromPaths(List.of(sourcePath));

    JavaCompiler.CompilationTask task = compiler.getTask(
            null,                         // writer cho thông điệp khác
            manager,                      // file manager
            collector,                    // listener nhận diagnostic
            List.of("--release", "17"),   // compiler options
            null,                         // classes cho annotation processing
            units);                       // source units

    boolean success = Boolean.TRUE.equals(task.call());
    List<Diagnostic<? extends JavaFileObject>> diagnostics =
            List.copyOf(collector.getDiagnostics());
}
```

Đây là **đoạn minh họa bên trong một phương thức**, giả định `sourcePath` là `Path` đã tồn tại và đã import các class ở `javax.tools`, `java.nio`, `java.util`. Phần ví dụ đầy đủ, biên dịch được, nằm ở mục 4.

Những chi tiết cần hiểu:

1. **Đúng kiểu generic.** Với compiler Java, `DiagnosticCollector<JavaFileObject>` khớp kiểu `JavaFileObject` của compilation units. `getDiagnostics()` trả danh sách `Diagnostic<? extends JavaFileObject>`.
2. **Truyền collector vào `getTask`.** Nếu không truyền listener, compiler có thể gửi chẩn đoán ra writer/luồng console; ứng dụng không có danh sách cấu trúc để phân tích.
3. **Truyền vào `getStandardFileManager` nếu muốn thu cả chẩn đoán từ file manager** khi đọc file hoặc xử lý location. Dùng cùng collector cho hai nơi giúp tập trung thông báo.
4. **Một task là một lượt biên dịch.** Không gọi `call()` nhiều lần trên cùng `CompilationTask`. Với hai lượt biên dịch độc lập, tạo task mới và tốt nhất là collector mới.
5. **Đóng file manager** bằng `try-with-resources`. Việc có DiagnosticCollector không thay thế quản lý tài nguyên file manager.
6. **Chụp snapshot** nếu cần giữ kết quả sau lượt chạy: `List.copyOf(collector.getDiagnostics())` tạo danh sách độc lập với list view của collector.

`getDiagnostics()` trả **list view** chứ không phải một định dạng file hay JSON. Có thể lặp qua và chuyển sang DTO riêng để gửi lên giao diện/API. Danh sách đó có thể chứa nhiều diagnostic cho một source và nhiều source trong một lượt biên dịch.

## 3. Những trường dữ liệu trong Diagnostic

Mỗi `Diagnostic<? extends JavaFileObject>` cung cấp thông tin để phân loại và chỉ vị trí.

| Phương thức | Ý nghĩa | Lưu ý |
|---|---|---|
| `getKind()` | `ERROR`, `WARNING`, `MANDATORY_WARNING`, `NOTE` hoặc `OTHER` | Không chỉ có ERROR/WARNING |
| `getSource()` | `JavaFileObject` liên quan đến diagnostic | **Có thể `null`** khi chẩn đoán mang tính toàn cục |
| `getLineNumber()` | Số dòng của vị trí vấn đề | Thường **1-based**; có thể `Diagnostic.NOPOS` |
| `getColumnNumber()` | Số cột của vị trí vấn đề | Thường **1-based**; có thể `Diagnostic.NOPOS` |
| `getPosition()` | Offset ký tự tính từ đầu source | **0-based**, không phải dòng/cột hay byte offset |
| `getStartPosition()` | Offset bắt đầu đoạn nguồn được compiler xác định là có vấn đề | Có thể không có vị trí |
| `getEndPosition()` | Offset kết thúc đoạn nguồn được compiler xác định | Không tự giả định mọi implementation đánh dấu cùng một token |
| `getCode()` | Mã chẩn đoán do implementation cung cấp | **Implementation-dependent**, có thể `null` |
| `getMessage(Locale)` | Thông điệp giải thích lỗi/cảnh báo theo locale | Câu chữ có thể đổi theo compiler/JDK/locale |

### 3.1. Phân loại: ERROR, WARNING và MANDATORY_WARNING

```java
Diagnostic.Kind kind = diagnostic.getKind();

boolean isError = kind == Diagnostic.Kind.ERROR;
boolean isWarning =
        kind == Diagnostic.Kind.WARNING
        || kind == Diagnostic.Kind.MANDATORY_WARNING;
```

Đoạn trên minh họa logic phân loại trong phạm vi có biến `diagnostic`. Nếu dashboard chỉ đếm `WARNING`, nó sẽ **bỏ sót `MANDATORY_WARNING`**, một loại rất dễ gặp khi javac báo unchecked operation. `NOTE` có thể chứa lời khuyên bổ sung; `OTHER` dành cho chẩn đoán ngoài những loại thông dụng.

**Warning không đồng nghĩa thất bại.** Compiler có thể hoàn thành nhưng vẫn có cảnh báo. Ngược lại, với tùy chọn như `-Werror`, chính sách compiler có thể biến một compilation có warning thành không thành công. Ứng dụng cần đọc **cả `success` lẫn danh sách diagnostic**, không thay đổi ý nghĩa của `call()`.

### 3.2. Khi không có nguồn hoặc vị trí

Một số diagnostic là lỗi mức dự án, module, option hoặc môi trường, không gắn được với một token cụ thể:

```java
String sourceName = diagnostic.getSource() == null
        ? "<global>"
        : diagnostic.getSource().getName();

long line = diagnostic.getLineNumber();
long column = diagnostic.getColumnNumber();

String location = (line == Diagnostic.NOPOS
        || column == Diagnostic.NOPOS)
        ? "unknown"
        : line + ":" + column;
```

Không được gọi `diagnostic.getSource().getName()` mà không kiểm tra `null`. Giá trị `Diagnostic.NOPOS` (thường là `-1`) báo **không có vị trí hợp lệ**; không hiển thị thành “dòng -1, cột -1” như một lỗi định vị thật.

### 3.3. Độ lệch ký tự và hiển thị trong editor

- `getLineNumber()` và `getColumnNumber()` là vị trí trình bày theo dòng/cột, thông thường bắt đầu từ 1.
- `getPosition()`/`getStartPosition()`/`getEndPosition()` là **offset ký tự** từ đầu `JavaFileObject`, không phải offset byte UTF-8. Với Java `String`/`CharSequence`, code UI thường cần chú ý đơn vị UTF-16, surrogate pairs, line endings và tab khi chuyển sang vị trí con trỏ.
- Vị trí và độ dài đoạn gạch chân do compiler chọn có thể khác nhau giữa các phiên bản. Không tự thêm/bớt 1 vào mọi trường.
- Khi đưa tới editor, hãy dùng một phiên bản source **khớp với phiên bản đã gửi để biên dịch**. Nếu người dùng sửa source trong lúc compile, vị trí diagnostic cũ có thể chỉ nhầm dòng.
- Khi source được tạo trong bộ nhớ, URI/name của `JavaFileObject` giúp gắn diagnostic với một “file ảo”; điều đó không ngụ ý file thật tồn tại trên đĩa.

## 4. Ví dụ Java 17 chạy được: thu thập lỗi và cảnh báo từ nguồn trong bộ nhớ

Ví dụ dùng `SimpleJavaFileObject` để đưa source code dạng chuỗi trực tiếp cho compiler. Không cần tạo trước `Broken.java` hay `Unchecked.java` trên ổ đĩa. Hai lượt biên dịch độc lập thể hiện:

- **ERROR** do gán `String` vào biến `int`.
- **Cảnh báo unchecked** do gọi `add` qua `List` raw type khi bật `-Xlint:unchecked`.

Trong ví dụ, compiler phát sinh class file tại một thư mục tạm. Class được biên dịch **không tự động được nạp hay thực thi**.

Lưu tệp **`DiagnosticCollectorDemo.java`**:

```java
import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class DiagnosticCollectorDemo {

    // Một JavaFileObject có mã nguồn trong bộ nhớ.
    private static final class Source extends SimpleJavaFileObject {
        private final String code;

        Source(String simpleName, String code) {
            super(URI.create("string:///" + simpleName + Kind.SOURCE.extension),
                    Kind.SOURCE);
            this.code = code;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return code;
        }
    }

    private record Result(
            boolean success,
            List<Diagnostic<? extends JavaFileObject>> diagnostics) {}

    private static Result compile(
            JavaCompiler compiler, JavaFileObject unit, Path outputDir)
            throws IOException {

        // Dùng collector mới cho từng compilation task.
        DiagnosticCollector<JavaFileObject> collector =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager manager =
                compiler.getStandardFileManager(
                        collector, Locale.ROOT, StandardCharsets.UTF_8)) {

            List<String> options = List.of(
                    "--release", "17",
                    "-proc:none",
                    "-Xlint:unchecked",
                    "-d", outputDir.toString());

            JavaCompiler.CompilationTask task = compiler.getTask(
                    null, manager, collector, options, null, List.of(unit));

            boolean success = Boolean.TRUE.equals(task.call());
            return new Result(
                    success,
                    List.copyOf(collector.getDiagnostics()));
        }
    }

    private static String position(long value) {
        return value == Diagnostic.NOPOS
                ? "unknown"
                : Long.toString(value);
    }

    private static void printResult(String label, Result result) {
        long errors = result.diagnostics().stream()
                .filter(d -> d.getKind() == Diagnostic.Kind.ERROR)
                .count();

        long warnings = result.diagnostics().stream()
                .filter(d ->
                        d.getKind() == Diagnostic.Kind.WARNING
                        || d.getKind() == Diagnostic.Kind.MANDATORY_WARNING)
                .count();

        System.out.println(label + " success=" + result.success()
                + " errors=" + errors + " warnings=" + warnings);

        for (Diagnostic<? extends JavaFileObject> d :
                result.diagnostics()) {

            String source = d.getSource() == null
                    ? "<global>"
                    : d.getSource().getName();

            System.out.println("  kind=" + d.getKind()
                    + " source=" + source
                    + " line=" + position(d.getLineNumber())
                    + " column=" + position(d.getColumnNumber()));

            // Locale.ROOT để yêu cầu thông điệp không theo locale của OS.
            System.out.println("  message=" + d.getMessage(Locale.ROOT));
        }
    }

    public static void main(String[] args) throws IOException {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();

        if (compiler == null) {
            throw new IllegalStateException(
                    "Java compiler is unavailable in this runtime");
        }

        JavaFileObject broken = new Source("Broken", """
                class Broken {
                    int number = "oops";
                }
                """);

        JavaFileObject unchecked = new Source("Unchecked", """
                import java.util.List;
                import java.util.ArrayList;
                class Unchecked {
                    void run() {
                        List raw = new ArrayList();
                        raw.add("hello");
                    }
                }
                """);

        Path outputDir = Files.createTempDirectory("java-diagnostics-");

        printResult("broken",
                compile(compiler, broken, outputDir));
        printResult("unchecked",
                compile(compiler, unchecked, outputDir));
    }
}
```

Biên dịch và chạy bằng **JDK 17 trở lên**:

```bash
javac -encoding UTF-8 DiagnosticCollectorDemo.java
java DiagnosticCollectorDemo
```

**Kết quả đáng chú ý:** trên javac thông dụng hỗ trợ `--release 17` và `-Xlint:unchecked`, hai dòng tóm tắt có dạng:

```text
broken success=false errors=1 warnings=0
unchecked success=true errors=0 warnings=1
```

Chương trình còn in các dòng diagnostic **ngay sau mỗi dòng tóm tắt**. Ví dụ chẩn đoán trong các lượt biên dịch với javac:

```text
  kind=ERROR source=/Broken.java line=2 column=18
  message=incompatible types: java.lang.String cannot be converted to int
```

và:

```text
  kind=MANDATORY_WARNING source=/Unchecked.java line=6 column=16
  message=unchecked call to add(E) as a member of the raw type java.util.List
```

**Các khối đầu ra ở trên là những phần được tách ra để giải thích, không phải một bản stdout liên tục.** Trong stdout thực tế, thông điệp lỗi của `broken` nằm trước dòng tóm tắt `unchecked`. Văn bản của `getMessage(Locale.ROOT)`, phân loại warning hoặc chi tiết vị trí có thể thay đổi theo implementation và phiên bản JDK; không dùng chuỗi thông điệp làm hợp đồng API bất biến.

### 4.1. Vì sao dữ liệu xuất hiện?

1. `Source` mở rộng `SimpleJavaFileObject`, dùng URI `string:///Broken.java` và `string:///Unchecked.java`. Compiler có thể đọc nội dung source qua `getCharContent(...)`, nên `Diagnostic.getSource()` vẫn có đối tượng nguồn dù không có file `.java` trên đĩa.
2. `--release 17` yêu cầu javac biên dịch theo ngôn ngữ và API Java 17. Ví dụ dùng Java text block và record, đều được hỗ trợ từ Java 17.
3. `-Xlint:unchecked` yêu cầu compiler báo thao tác generic không được kiểm tra; `List raw` gọi `add` tạo cảnh báo. Với javac, loại cảnh báo đó có thể là `MANDATORY_WARNING`, vì vậy ví dụ đếm cả hai loại warning.
4. `-proc:none` tắt annotation processing trong lượt demo để không phát sinh xử lý phụ từ annotation processors.
5. Từng lượt biên dịch dùng **collector riêng**. Lỗi trong `Broken` không bị tính chung vào diagnostics của `Unchecked`.
6. `Result` chứa snapshot danh sách diagnostic trước khi file manager đóng. `printResult` chuyển từng diagnostic thành loại, nguồn, dòng, cột và thông điệp.
7. `outputDir` là nơi compiler có thể ghi class file. Ví dụ chỉ biên dịch và kiểm tra, không thực thi class vừa tạo. Trong ứng dụng thật cần quản lý vòng đời thư mục tạm và xóa output khi không dùng nữa.

### 4.2. Nếu muốn có vị trí chính xác hơn

Trong vòng lặp `for` ở `printResult` có thể lấy thêm:

```java
long position = d.getPosition();
long start = d.getStartPosition();
long end = d.getEndPosition();
String code = d.getCode();

System.out.printf(
        "offset=%d start=%d end=%d code=%s%n",
        position, start, end, code);
```

Đây là **đoạn bổ sung cho vòng lặp** ở chương trình trên, không phải chương trình độc lập. Dùng những offset này để đánh dấu token/range trong editor khi hợp lệ, nhưng vẫn cần xử lý `Diagnostic.NOPOS`. `getCode()` có ích cho máy phân tích hoặc telemetry trong một compiler cụ thể, song **không có bảo đảm tương thích mã lỗi giữa các compiler hoặc phiên bản**.

## 5. Trình bày vị trí nguồn và thông điệp cho người học

Một diagnostic nên được chuyển thành dữ liệu riêng thay vì chuyển toàn bộ đối tượng `Diagnostic` trực tiếp sang JSON. Ví dụ cấu trúc ý tưởng:

```json
{
  "severity": "ERROR",
  "source": "Broken.java",
  "line": 2,
  "column": 18,
  "startOffset": 31,
  "message": "incompatible types: java.lang.String cannot be converted to int",
  "compiler": "javac",
  "sourceRevision": "revision-of-submitted-source"
}
```

Đây là **ví dụ hình dạng DTO**, không phải JSON đầu ra của chương trình ở mục 4. `startOffset` trong sản phẩm thật phải lấy từ `getStartPosition()` ở compiler tương ứng, không tự suy từ `line`/`column`; giá trị số trong JSON chỉ minh họa. `sourceRevision` là định danh do **ứng dụng** bổ sung để UI khớp diagnostic với bản source đã gửi.

Với editor, một lỗi có thể hiển thị như:

```text
Broken.java:2:18 [ERROR]
    int number = "oops";
                 ^
incompatible types: java.lang.String cannot be converted to int
```

Dòng và cột cần tính từ chính source đã biên dịch; tab, CRLF và các ký tự Unicode có thể làm vị trí hiển thị khác với offset trong chuỗi, nên phải dùng quy tắc mapping của editor. Với source không có vị trí, hãy để thông điệp ở khu vực “lỗi dự án” thay vì gắn sai vào dòng 1.

**Locale và thông điệp:** `diagnostic.getMessage(Locale.ROOT)` yêu cầu một thông điệp theo locale gốc; API cũng cho phép truyền `Locale.forLanguageTag("vi")` hoặc `Locale.getDefault()`. Tuy nhiên, compiler **không bắt buộc phải có bản dịch tiếng Việt**. UI có thể tự dịch thông báo để hỗ trợ học tập, nhưng nên lưu phiên bản thông điệp gốc để đối chiếu. Không tách nghĩa từ một chuỗi thông điệp tiếng Anh nếu cần business logic.

## 6. Nhiều nguồn, nhiều lượt biên dịch và chiến lược tổng hợp

Trong công cụ biên dịch động thực tế, một tác vụ có thể nhận nhiều `JavaFileObject`:

```java
Iterable<? extends JavaFileObject> units =
        manager.getJavaFileObjectsFromPaths(
                List.of(pathA, pathB, pathC));

JavaCompiler.CompilationTask task = compiler.getTask(
        null, manager, collector, options, null, units);
Boolean success = task.call();
```

Đây là **đoạn minh họa** với `manager`, `collector`, `options`, `pathA`, `pathB`, `pathC` đã khai báo. Một diagnostic sẽ gắn với `JavaFileObject` tương ứng khi compiler xác định được nguồn. Không cho rằng nguồn của mọi lỗi đều là “file đầu tiên” hoặc “class chính”.

Một hệ thống nhận nguồn Java có thể cần các bước:

1. **Xác định snapshot source**: source ID, file name, nội dung/encoding và hash hoặc revision ở thời điểm nhận.
2. **Tạo task/collector cho một job**: không trộn hai lần `call()` vào cùng bộ kết quả nếu không có job ID.
3. **Biên dịch trong môi trường xác định**: `--release`, classpath/module path, compiler options và output location phải phù hợp.
4. **Đọc kết quả**: `success` và các diagnostic, cả `ERROR` lẫn `WARNING`, `MANDATORY_WARNING`, `NOTE` và `OTHER`.
5. **Chuẩn hóa dữ liệu hiển thị**: map tên nguồn, chuyển `NOPOS` sang vị trí “unknown”, giới hạn độ dài thông điệp, đính kèm compiler/version.
6. **Lưu trữ/đưa ra UI**: nếu cần sắp xếp, hãy định nghĩa rõ thứ tự (tệp, dòng, cột, severity) thay vì dựa vào thứ tự gửi thông báo như một tiêu chuẩn bất biến.
7. **Phân biệt lỗi compile với lỗi infrastructure**: sai compiler option, không mở được file manager, không ghi được class output hoặc compiler vắng mặt đều cần mã lỗi riêng.

### 6.1. Khi nào cần xử lý diagnostic theo thời gian thực?

`DiagnosticCollector` là listener đơn giản giúp lấy danh sách chẩn đoán. Nếu muốn **đẩy từng diagnostic ngay khi compiler báo**, bạn có thể tự cài `DiagnosticListener<JavaFileObject>` bằng `report(...)` rồi chuyển sang hàng đợi UI/log, hoặc vừa ghi nhận vừa báo tiến độ. Phải tránh cập nhật UI từ thread không phù hợp và tránh coi mỗi callback là kết luận cuối cùng về success.

Đoạn minh họa listener:

```java
DiagnosticListener<JavaFileObject> listener = diagnostic -> {
    // Thu thập/chuyển diagnostic theo hợp đồng ứng dụng.
    // Không coi một NOTE/WARNING là compilation failure.
    System.out.println(diagnostic.getKind() + ": "
            + diagnostic.getMessage(Locale.ROOT));
};
```

Đây là đoạn trong phương thức, cần import `javax.tools.DiagnosticListener`, `javax.tools.JavaFileObject` và `java.util.Locale`. Nếu dùng listener riêng thay collector, phải tự quyết định cơ chế lưu, thread-safety và định dạng lỗi. Với nhiệm vụ “thu thập để phân tích sau”, `DiagnosticCollector` thường đủ.

### 6.2. Không bắt lỗi API rồi biến nó thành diagnostic nguồn

Có khác biệt lớn giữa:

- **Lỗi mã nguồn**: ví dụ kiểu dữ liệu không hợp lệ, compiler thường đưa vào `Diagnostic.Kind.ERROR` và `call()` báo không thành công.
- **Cảnh báo chất lượng/kiểu**: ví dụ unchecked, nằm trong `WARNING` hoặc `MANDATORY_WARNING` nhưng compilation vẫn có thể thành công.
- **Lỗi cấu hình task**: option không hợp lệ có thể gây `IllegalArgumentException` khi tạo task; không mặc nhiên xuất hiện như một diagnostic ở dòng nguồn.
- **Thiếu compiler**: `ToolProvider.getSystemJavaCompiler() == null`, không có `CompilationTask` để chạy.
- **Lỗi I/O**: không tìm được source, không ghi được output, file manager hỏng; cần báo lỗi môi trường và ngữ cảnh, có thể xảy ra trước/khi compilation task chạy.
- **Lỗi thực thi class sau khi biên dịch**: `ClassNotFoundException`, `LinkageError` hay exception từ phương thức runtime thuộc **giai đoạn nạp/chạy**, không thuộc tập diagnostic của lần biên dịch.

Vì vậy, API biên dịch động nên có một kết quả chứa ít nhất: trạng thái job, `success` của compiler khi có, danh sách diagnostic, loại lỗi hạ tầng (nếu có), mã version source và compiler options đã được chấp thuận.

## 7. Tùy chọn compiler ảnh hưởng số lượng và loại thông điệp

Lượng diagnostics **không cố định với cùng source** nếu thay đổi tùy chọn hoặc phiên bản compiler.

| Tùy chọn | Ảnh hưởng |
|---|---|
| `--release 17` | Kiểm tra mức ngôn ngữ/API tương ứng bản Java 17 |
| `-Xlint:unchecked` | Yêu cầu diagnostic về generic unchecked operations |
| `-Xlint:deprecation` | Bật thêm cảnh báo dùng API deprecated theo chính sách lint |
| `-Werror` | Xem warning là lỗi biên dịch theo chính sách compiler, có thể khiến `success=false` |
| `-proc:none` | Không chạy annotation processors trong lượt biên dịch |
| `-d <dir>` | Chọn thư mục ghi class output |
| `-classpath` / `--module-path` | Ảnh hưởng cách tìm type/module và lỗi thiếu dependency |

Đừng mặc định một JDK nhận mọi option tương lai hoặc option đặc thù của compiler khác. Trong dịch vụ nhận code từ người dùng, **không cho phép người dùng tự do truyền mọi compiler flag**, đặc biệt những flag thay đổi đường dẫn classpath, module, output hay annotation processing. Tạo danh sách option được phép, xác thực và log bản cấu hình an toàn.

## 8. Kiểm thử DiagnosticCollector theo mục đích sử dụng

Bộ trường hợp thực tế nên bao phủ cả compiler status và thông tin chi tiết:

| Trường hợp | Điều cần xác minh |
|---|---|
| Mã Java đúng, không warning | `success=true`, không có `ERROR` |
| Gán sai kiểu hoặc thiếu ký tự cú pháp | `success=false` và có `ERROR` đúng source |
| Raw generic + `-Xlint:unchecked` | Có `WARNING` hoặc `MANDATORY_WARNING`, dù có thể `success=true` |
| Cùng source, tắt lint | Tập warning có thể ít hơn; không phụ thuộc chuỗi message |
| Biên dịch nhiều source | `getSource()` gắn đúng đơn vị nguồn khi có |
| Diagnostic toàn cục | `source=null` hoặc `position=NOPOS` được xử lý an toàn |
| Warning + `-Werror` | Không tự kết luận success từ việc đếm `ERROR` đơn giản |
| Text nhiều dòng có Unicode, tab, CRLF | Vị trí hiển thị được map đúng vào snapshot source |
| Compiler không hiện diện | Trả lỗi môi trường có nghĩa; không `NullPointerException` |
| Classpath/module path sai | Phân biệt lỗi nguồn, lỗi phụ thuộc và lỗi cấu hình task |
| Hai job liên tiếp | Collector riêng hoặc job ID riêng, không trộn dữ liệu |
| Source thay đổi trong lúc job chạy | Diagnostic hiển thị gắn đúng phiên bản source đã biên dịch |

**Đừng cố kiểm thử một thông điệp lỗi bằng so sánh nguyên văn với một chuỗi tiếng Anh dài.** Compiler/JDK có thể sửa câu chữ mà giữ nguyên ý nghĩa. Kiểm tra `kind`, trạng thái compile, tên nguồn, vị trí hợp lệ và những thuộc tính quan trọng đối với hợp đồng ứng dụng. Khi cần kiểm thử chính xác dòng/cột, cố định source và compiler version.

## 9. Bảo mật và giới hạn vận hành

`DiagnosticCollector` giúp **quan sát kết quả biên dịch**; nó **không làm mã nguồn an toàn**. Mã chưa được tin cậy sau khi biên dịch thành công vẫn có thể đọc filesystem, kết nối mạng hoặc tạo tiến trình nếu được chạy với quyền của ứng dụng. Một số lưu ý:

- Chỉ chấp nhận mã nguồn theo policy, giới hạn kích thước source, số file, thời gian/CPU/bộ nhớ và số diagnostic được giữ hoặc trả về UI.
- Giới hạn compiler options và đường dẫn đọc/ghi; không biến classpath, annotation processors hay output directory thành đường dẫn do người dùng tùy ý chỉ định.
- Nếu source không đáng tin cậy, cân nhắc **biên dịch/chạy trong tiến trình hoặc container cô lập** với quyền hệ điều hành hạn chế. Class loader **không phải sandbox**.
- Không gửi đường dẫn tuyệt đối nhạy cảm, tên tài khoản hệ điều hành hoặc nội dung cấu hình bí mật qua `getSource().getName()` hoặc nguyên văn message nếu chúng chứa thông tin nội bộ; cần chuẩn hóa đường dẫn công bố.
- Sửa lỗi UI không nên tự động biên dịch lại trên từng phím gõ khi workload lớn; dùng debounce, hủy job theo vòng đời và lưu source revision.
- Sau khi lấy diagnostics, vẫn phải quyết định có cho phép nạp class vào runtime hay không bằng **chính sách nghiệp vụ, kiểm tra mã và ranh giới tin cậy** riêng.

## 10. Những hiểu nhầm thường gặp

1. **“`DiagnosticCollector` tự biên dịch source.”** Sai: nó nhận diagnostic; compiler và task mới thực hiện biên dịch.
2. **“`compiler.run` cho danh sách Java objects của lỗi.”** Không: `getTask` với listener mới là đường thu thập có cấu trúc.
3. **“Không có ERROR nghĩa là compile đã thành công.”** Chưa đủ: cần `CompilationTask.call()` và phải tính đến lỗi hạ tầng/`-Werror`.
4. **“WARNING luôn chỉ có `Diagnostic.Kind.WARNING`.”** Sai: còn `MANDATORY_WARNING`.
5. **“Mọi diagnostic có source và dòng/cột.”** Sai: có thể `source == null` hoặc `position == Diagnostic.NOPOS`.
6. **“Line/column là byte offset.”** Sai: line/column biểu diễn vị trí theo dòng/cột; offset ký tự được trả ở các phương thức khác.
7. **“`getMessage(Locale)` là mã lỗi ổn định.”** Sai: văn bản phụ thuộc compiler và locale; `getCode()` cũng mang tính implementation-dependent.
8. **“Chỉ cần một collector chung cho mọi request.”** Dễ trộn kết quả từ các lượt compile; nên gắn collector với từng job.
9. **“Biên dịch source thành công nghĩa là class đã được load/chạy.”** Sai: output class còn cần cơ chế class loading/runtime riêng.
10. **“Thu thập diagnostic đủ để sandbox mã động.”** Sai: bảo mật runtime và cô lập tài nguyên là vấn đề khác.

### Tài liệu Java SE 17

- [DiagnosticCollector — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/DiagnosticCollector.html)
- [Diagnostic — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/Diagnostic.html)
- [DiagnosticListener — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/DiagnosticListener.html)
- [JavaCompiler — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html)

**Ghi nhớ:** với mỗi lượt biên dịch động, tạo `DiagnosticCollector<JavaFileObject>`, truyền vào `JavaCompiler.getTask(...)`, gọi `call()`, sau đó đọc `getDiagnostics()` để lấy **loại, nguồn, dòng/cột, offset và thông điệp**. Luôn kiểm tra `null`/`Diagnostic.NOPOS`, phân biệt warning với error, giữ nguồn phiên bản đúng, và dùng `success` để phản ánh kết quả biên dịch thực sự.