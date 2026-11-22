# SimpleJavaFileObject và biểu diễn mã nguồn Java bằng chuỗi

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Hiểu tại sao `javax.tools.JavaFileObject` có thể đại diện cho mã nguồn Java nằm trong một `String`, không cần tồn tại tệp `.java` trên đĩa.
- Viết một lớp kế thừa `SimpleJavaFileObject`, chọn đúng `JavaFileObject.Kind.SOURCE`, xây URI ảo hợp lệ và override `getCharContent(boolean)`.
- Đưa nhiều nguồn lưu trong bộ nhớ cho `JavaCompiler.getTask(...)`, nhận lỗi qua `DiagnosticCollector` và hiểu ý nghĩa đường dẫn ảo trong diagnostics.
- Phân biệt **source ở bộ nhớ** với **bytecode `.class` ở bộ nhớ**: chỉ sử dụng `StringSource` chưa làm đầu ra tự động chuyển sang RAM.
- Biết lựa chọn mới `SimpleJavaFileObject.forSource(...)` dành cho JDK 23+, bên cạnh cách subclass chạy được từ JDK 17, và nhận diện các lỗi thường gặp về tên lớp, classpath, bộ nhớ và an toàn.

Đây là kiến thức **đang được hỗ trợ trong Java hiện đại**. Bài thực hành chính dùng JDK 17+ và API chuẩn; phần cú pháp chỉ có từ JDK 23 được ghi nhãn riêng.

## 1. Vấn đề: `javac` cần một “tệp nguồn” nhưng nguồn chỉ là chuỗi

Một trình soạn thảo, trình chấm bài Java hoặc công cụ sinh mã có thể đang giữ nội dung người dùng vừa nhập dưới dạng:

```java
String code = """
        package demo;
        public class Greeter {
            public static String message() {
                return "Hello";
            }
        }
        """;
```

Ta muốn hỏi compiler: “Mã này có hợp lệ không? Nếu hợp lệ, hãy biên dịch thành bytecode”. Nếu buộc phải tạo tệp vật lý ở mọi lần kiểm tra, ứng dụng còn phải quản lý đường dẫn, file tạm, ghi/xóa đĩa và các lần biên dịch đồng thời.

API Compiler trong JDK sử dụng trừu tượng `JavaFileObject` cho **đơn vị biên dịch** (compilation unit). Một implementation có thể đọc mã nguồn từ đĩa, từ chuỗi, từ cơ sở dữ liệu hay từ một nguồn khác. Compiler tương tác với hợp đồng của `JavaFileObject` thay vì tự suy đoán mã nguồn nhất thiết nằm ở đâu.

`SimpleJavaFileObject` là lớp nền giúp tạo các `JavaFileObject` tùy biến mà không cần viết lại tất cả các phương thức của giao diện.

```text
String chứa mã Java
   |
   v
StringSource extends SimpleJavaFileObject
   |  toUri()       -> string:///demo/Greeter.java
   |  getKind()     -> SOURCE
   |  getCharContent(...) -> nội dung String
   v
JavaCompiler.getTask(..., List.of(source))
   |
   | task.call()
   v
Java compiler  ------> Diagnostic nếu mã sai
   |
   +---------------> .class theo file manager / output options
```

Điểm quan trọng: **URI ảo được dùng để định danh nguồn**, không có nghĩa compiler tải mã Java qua HTTP hay thật sự đọc đường dẫn đó từ ổ đĩa.

## 2. `JavaFileObject`, `SimpleJavaFileObject` và `Kind.SOURCE`

Ba khái niệm liên quan:

| Thành phần | Ý nghĩa |
| --- | --- |
| `FileObject` | Hợp đồng về một đối tượng file trừu tượng: URI, tên, đọc ký tự hoặc stream, v.v. |
| `JavaFileObject` | Mở rộng `FileObject` với kiểu tệp Java (`Kind`), thông tin tên lớp và metadata liên quan. |
| `SimpleJavaFileObject` | Lớp nền triển khai các hành vi mặc định của `JavaFileObject`, cho phép override các phương thức thực sự cần. |

Đối với mã nguồn Java nằm trong chuỗi, ta thường cần:

1. **`URI`** đại diện cho tên tệp nguồn ảo, chẳng hạn `string:///demo/Greeter.java`.
2. **`Kind.SOURCE`** đánh dấu đây là đơn vị chứa source Java, không phải bytecode.
3. **`getCharContent(boolean ignoreEncodingErrors)`** trả nội dung Java dưới dạng `CharSequence`, thường là một `String`.

Một số giá trị của `JavaFileObject.Kind`:

| Kind | Dùng cho | Phần mở rộng thường thấy |
| --- | --- | --- |
| `SOURCE` | Java source | `.java` |
| `CLASS` | Java bytecode | `.class` |
| `HTML` | Tài liệu HTML | `.html` |
| `OTHER` | Đối tượng file loại khác | Không có suffix cố định |

Compiler nhận **compilation units loại `SOURCE`**. Truyền đối tượng `Kind.CLASS` thay cho source vào danh sách compilation units của `getTask(...)` là sai hợp đồng, dù object có chứa những ký tự trông giống Java.

### Vì sao không dùng trực tiếp `SimpleJavaFileObject` mà phải override?

Constructor của lớp nền nhận `URI` và `Kind`. Tuy nhiên, triển khai mặc định của `getCharContent(...)` **ném `UnsupportedOperationException`**; một object chỉ có URI và Kind chưa tự có nội dung source.

Khi override `getCharContent(...)`, compiler có thể lấy trực tiếp ký tự từ chuỗi. `openReader(...)` mặc định của lớp nền dựa trên `getCharContent(...)`, nên trong trường hợp cơ bản không cần tự viết một `Reader`. Những phương thức dùng stream nhị phân có thể vẫn không được hỗ trợ nếu không override tương ứng.

## 3. Viết lớp `StringSource`: bốn dòng thiết kế quan trọng

Đây là phần cốt lõi để biến chuỗi thành mã nguồn được compiler hiểu:

```java
import java.net.URI;
import java.util.Objects;
import javax.tools.SimpleJavaFileObject;

public final class StringSource extends SimpleJavaFileObject {
    private final String code;

    public StringSource(String binaryName, String code) {
        super(URI.create("string:///" +
                binaryName.replace('.', '/') + Kind.SOURCE.extension),
                Kind.SOURCE);
        this.code = Objects.requireNonNull(code);
    }

    @Override
    public CharSequence getCharContent(boolean ignoreEncodingErrors) {
        return code;
    }
}
```

**Lưu ý chạy thử:** Đây là một **lớp độc lập** có thể lưu thành `StringSource.java` khi dùng cùng compiler. Ở ví dụ chạy hoàn chỉnh phía dưới, lớp tương tự được lồng trong `StringSourceDemo` để dễ biên dịch một tệp duy nhất.

Giải thích:

- `StringSource extends SimpleJavaFileObject`: kế thừa một implementation cơ bản của `JavaFileObject`.
- `String binaryName`: tên đầy đủ dạng Java của lớp nguồn, ví dụ `demo.Greeter`. Ở bài toán nhiều đơn vị, mỗi đơn vị cần tên tương ứng và nội dung riêng.
- `binaryName.replace('.', '/')`: biến `demo.Greeter` thành đường dẫn `demo/Greeter`; `Kind.SOURCE.extension` thêm `.java` một cách đúng nghĩa theo API.
- `URI.create("string:///" + ...)`: tạo định danh ảo có **scheme `string`**, đường dẫn tuyệt đối `/demo/Greeter.java`. Đây chỉ là định danh, không phải đường dẫn cần tồn tại.
- `Kind.SOURCE`: nói rõ object này đại diện cho mã nguồn.
- `code` là `String` bất biến; compiler đọc cùng nội dung cho cả lượt biên dịch.
- `getCharContent(...)`: trả source cho compiler. Vì nội dung đã là chuỗi ký tự trong JVM, tham số `ignoreEncodingErrors` không ảnh hưởng đến quá trình giải mã byte trong ví dụ này.

Nếu `StringSource` được dùng để đại diện cho mã nguồn chưa có trên đĩa, không tự thêm logic tạo `File` hay `Path` cho URI ảo. Việc tạo file thật là trách nhiệm riêng nếu ứng dụng có nhu cầu xuất source để lưu trữ.

## 4. Tên Java, package và URI ảo phải khớp

Với nguồn:

```java
package demo;
public class Greeter {
    public static String message() { return "Hello"; }
}
```

Hãy dùng:

```java
JavaFileObject source = new StringSource(
        "demo.Greeter",
        "package demo; public class Greeter {" +
        " public static String message() { return \"Hello\"; } }");
```

Khi đó `source.toUri()` là `string:///demo/Greeter.java`.

| Dữ liệu | Giá trị hợp lệ trong ví dụ |
| --- | --- |
| Package trong `code` | `demo` |
| Public top-level class trong `code` | `Greeter` |
| Tên đầy đủ khi tạo `StringSource` | `demo.Greeter` |
| URI source | `string:///demo/Greeter.java` |
| Kind | `JavaFileObject.Kind.SOURCE` |
| Output thông thường (nếu `-d out`) | `out/demo/Greeter.class` |

Với class ở **default package**, tên là `Greeter` và URI tương ứng `string:///Greeter.java`.

Vì sao cần nhất quán? Compiler dùng tên đơn vị nguồn và URI cho các thao tác phù hợp tên lớp, thông báo lỗi, và trong một số tình huống tìm/biên dịch dependency. Nếu package hoặc public class không khớp, bạn có thể nhận lỗi kiểu “public class ... should be declared in a file named ...” hoặc gặp khó khăn khi tìm một loại phụ thuộc. **Đừng tạo URI tùy tiện như `string:///Snippet.txt` cho một compilation unit Java có public class `Greeter`.**

Không nên nối chuỗi input chưa kiểm soát trực tiếp thành URI nếu đầu vào có ký tự đặc biệt hoặc đường dẫn không hợp lệ. Ứng dụng nhận source từ bên ngoài nên chuẩn hóa/kiểm tra tên lớp, tên package và nguồn trước khi tạo identifier ảo.

## 5. Ví dụ đầy đủ Java 17+: biên dịch chuỗi mà không tạo file `.java`

Ví dụ sau chạy bằng **JDK 17+ có `jdk.compiler`**. Nó tạo một nguồn tốt và một nguồn cố ý sai cú pháp, gọi compiler bằng `getTask(...).call()`, xem file `.class` được ghi và đọc diagnostics. Không có `Greeter.java` hay `Broken.java` thật trên ổ đĩa.

Tạo **`StringSourceDemo.java`**:

```java
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class StringSourceDemo {
    static final class StringSource extends SimpleJavaFileObject {
        private final String code;

        StringSource(String binaryName, String code) {
            super(URI.create("string:///" +
                    binaryName.replace('.', '/') + Kind.SOURCE.extension),
                    Kind.SOURCE);
            this.code = Objects.requireNonNull(code);
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return code;
        }
    }

    static boolean compile(
            JavaCompiler compiler,
            StandardJavaFileManager manager,
            DiagnosticCollector<JavaFileObject> diagnostics,
            Path target,
            JavaFileObject unit) {
        List<String> options = List.of(
                "--release", "17", "-proc:none", "-d", target.toString());
        return Boolean.TRUE.equals(compiler.getTask(
                null, manager, diagnostics, options, null, List.of(unit)).call());
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK compiler is unavailable");
        }

        Path target = Files.createTempDirectory("java-string-source-");
        try (StandardJavaFileManager manager = compiler.getStandardFileManager(
                null, Locale.ROOT, StandardCharsets.UTF_8)) {

            JavaFileObject valid = new StringSource("demo.Greeter",
                    "package demo; public class Greeter {" +
                    " public static String message() { return \"Hello\"; } }");
            var validDiagnostics = new DiagnosticCollector<JavaFileObject>();
            System.out.println("Source URI: " + valid.toUri());
            System.out.println("Valid source: " +
                    compile(compiler, manager, validDiagnostics, target, valid));
            System.out.println("Class file exists: " +
                    Files.exists(target.resolve("demo/Greeter.class")));
            System.out.println("Valid errors: " +
                    validDiagnostics.getDiagnostics().stream()
                            .filter(d -> d.getKind() == Diagnostic.Kind.ERROR)
                            .count());

            JavaFileObject invalid = new StringSource("demo.Broken",
                    "package demo; public class Broken { int value = ; }");
            var invalidDiagnostics = new DiagnosticCollector<JavaFileObject>();
            System.out.println("Invalid source: " +
                    compile(compiler, manager, invalidDiagnostics, target, invalid));
            System.out.println("Invalid has error: " +
                    invalidDiagnostics.getDiagnostics().stream()
                            .anyMatch(d -> d.getKind() == Diagnostic.Kind.ERROR));
        } finally {
            try (var tree = Files.walk(target)) {
                for (Path path : tree.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(path);
                }
            }
        }
    }
}
```

### Biên dịch và chạy

Từ thư mục chứa `StringSourceDemo.java`:

```bash
javac StringSourceDemo.java
java StringSourceDemo
```

Kết quả đã chạy thử trên **JDK 24**:

```text
Source URI: string:///demo/Greeter.java
Valid source: true
Class file exists: true
Valid errors: 0
Invalid source: false
Invalid has error: true
```

### Đọc kết quả theo trình tự

1. `Source URI` in tên định danh nguồn ảo; **không tồn tại file `demo/Greeter.java` trên đĩa**.
2. `Valid source: true` nghĩa compilation task cho `demo.Greeter` thành công.
3. `Class file exists: true` chứng minh standard file manager **đã ghi `demo/Greeter.class` vào thư mục tạm**. Source nằm trong chuỗi, nhưng output vẫn là file vật lý.
4. `Valid errors: 0` cho thấy không có diagnostic loại `ERROR` trong lần biên dịch thành công.
5. `Invalid source: false` vì source `Broken` cố ý có biểu thức `int value = ;` sai cú pháp.
6. `Invalid has error: true` xác nhận compiler phát `Diagnostic.Kind.ERROR`; cách kiểm tra theo `Kind` tránh phụ thuộc ngôn ngữ thông báo cụ thể.

Chương trình tự xóa nội dung thư mục tạm bằng `Files.walk(...)` trong `finally`. Khi dùng trong sản phẩm, có thể lưu lại output nếu đây là artifact cần phát hành, nhưng phải chủ động quản lý tên và vòng đời output.

### Vì sao dùng từng API?

- `ToolProvider.getSystemJavaCompiler()` lấy compiler hệ thống, có thể `null` nếu runtime không chứa compiler phù hợp.
- `getStandardFileManager(..., Locale.ROOT, StandardCharsets.UTF_8)` chuẩn bị file manager cho các file input/output thông thường; ví dụ dùng `try-with-resources` để đóng.
- `DiagnosticCollector<JavaFileObject>` thu lỗi và cảnh báo thành cấu trúc để ứng dụng hiển thị hoặc phân tích.
- `getTask(null, manager, diagnostics, options, null, List.of(unit))` mô tả **một lần biên dịch** với một đơn vị nguồn lưu trong chuỗi.
- `call()` **mới thực thi compiler**; `Boolean.TRUE.equals(...)` diễn giải kết quả thành boolean.
- `--release 17` giới hạn ngôn ngữ/API/bytecode mục tiêu về Java 17 khi compiler hỗ trợ; `-proc:none` tắt annotation processing trong ví dụ; `-d` đặt output directory.

Trong thực tế, file manager có thể được tái sử dụng cho nhiều lượt biên dịch **tuần tự** để tránh khởi tạo lại không cần thiết. Tuy nhiên, mỗi lượt nên có collector/định danh công việc riêng, và không dùng đồng thời một file manager nếu chưa xác minh hỗ trợ thread safety.

## 6. Nhiều đơn vị nguồn: không gộp mọi public class vào một chuỗi

Một lượt `getTask(...)` nhận `Iterable<? extends JavaFileObject> compilationUnits`, vì vậy có thể truyền nhiều file object, mỗi object có binary name và nội dung riêng:

```java
// Đoạn bên trong phương thức đã có compiler, manager và target.
JavaFileObject api = new StringSource(
        "sample.api.Converter",
        "package sample.api; public interface Converter {" +
        " String convert(String value); }");

JavaFileObject impl = new StringSource(
        "sample.impl.UpperConverter",
        "package sample.impl; public class UpperConverter" +
        " implements sample.api.Converter {" +
        " public String convert(String value) { return value.toUpperCase(); } }");

var messages = new DiagnosticCollector<JavaFileObject>();
boolean success = Boolean.TRUE.equals(
        compiler.getTask(
                null,
                manager,
                messages,
                List.of("--release", "17", "-proc:none",
                        "-d", target.toString()),
                null,
                List.of(api, impl))
        .call());
```

Đây là **đoạn bổ sung**, sử dụng lại lớp `StringSource` đã giải thích; không phải chương trình `main` độc lập. Nó minh họa compiler có thể xử lý đồng thời những nguồn liên quan với nhau trong **một compilation task**, thay vì ghi tệp `.java` rồi compile riêng từng class.

Đừng lấy chuỗi chứa nhiều `public class` khác tên rồi gán một `URI` bất kỳ: quy tắc tên file và public top-level type của Java vẫn được áp dụng. Một compilation unit có thể chứa các top-level type không public theo ngữ nghĩa Java, nhưng phải tuân thủ yêu cầu tên và cấu trúc mã nguồn.

## 7. URI ảo giúp báo lỗi cho đúng tài liệu đang mở

Khi compiler phát sinh diagnostics, `Diagnostic<? extends JavaFileObject>` thường chứa nguồn có thể truy cập qua `getSource()`. Với `StringSource`, đó là object mang URI do ta đặt.

Ví dụ xử lý lỗi trong một phương thức đã có `DiagnosticCollector<JavaFileObject> messages`:

```java
for (Diagnostic<? extends JavaFileObject> diagnostic
        : messages.getDiagnostics()) {
    if (diagnostic.getKind() != Diagnostic.Kind.ERROR) {
        continue;
    }

    JavaFileObject source = diagnostic.getSource();
    String sourceId = source == null
            ? "<unknown>"
            : source.toUri().toString();

    System.out.printf(
            "%s:%d:%d: %s%n",
            sourceId,
            diagnostic.getLineNumber(),
            diagnostic.getColumnNumber(),
            diagnostic.getMessage(Locale.ROOT));
}
```

Đây là **đoạn minh họa có thể đặt trong phương thức**; để dùng phải có các import cần thiết như `javax.tools.Diagnostic`, `javax.tools.JavaFileObject` và `java.util.Locale`.

Một IDE hoặc công cụ chấm bài có thể ánh xạ `string:///demo/Greeter.java` đến tab mã nguồn tương ứng, rồi dùng dòng/cột để tô vị trí lỗi. `getLineNumber()` và `getColumnNumber()` có thể trả `Diagnostic.NOPOS` khi compiler không có tọa độ; `getSource()` cũng có thể `null`. Phải xử lý những trường hợp này.

**Không coi thông báo lỗi nguyên văn là giao thức ổn định:** wording và chi tiết có thể khác giữa phiên bản JDK hoặc compiler. Dùng `getKind()`, nguồn và vị trí để xử lý cấu trúc; `getMessage(Locale)` là phần mô tả cho người đọc.

Vì URI chỉ là tên ảo, nên không cần và không nên thử `Files.readString(Path.of(source.toUri()))` cho scheme `string`. Muốn đọc lại source thì gọi `getCharContent(...)` hoặc dùng bộ nhớ nội bộ do ứng dụng quản lý.

## 8. “Nguồn ở bộ nhớ” chưa đồng nghĩa “biên dịch hoàn toàn trong bộ nhớ”

Đây là điểm quan trọng nhất trong tên chủ đề.

| Phương án | Mã `.java` lưu ở đâu? | Bytecode `.class` lưu ở đâu? | Thành phần cần tùy biến |
| --- | --- | --- | --- |
| Biên dịch file thông thường | Ổ đĩa | Ổ đĩa | Dùng standard file manager |
| **Chuỗi nguồn + standard file manager** | **RAM dưới dạng `String`** | Thường là **ổ đĩa** khi cấu hình `-d` | `StringSource` / `SimpleJavaFileObject` cho input |
| Chuỗi nguồn + output file manager tùy biến | **RAM** | **RAM** (ví dụ `byte[]`) | Source `JavaFileObject` **và** output `JavaFileManager` |
| Chuỗi nguồn + output ở RAM + class loader | **RAM** | **RAM** | Thêm cơ chế nạp class riêng nếu thực sự cần chạy |

`SimpleJavaFileObject` dùng cho source chỉ làm nhiệm vụ “đưa mã nguồn từ `String` cho compiler”. Nó **không tự hứa** output nằm trong bộ nhớ. Ví dụ đầy đủ ở mục 5 chứng minh sự khác biệt này bằng `Files.exists(...Greeter.class)`.

Nếu cần lấy trực tiếp bytecode `byte[]` mà không tạo file `.class`, có thể:

1. Dùng `ForwardingJavaFileManager<StandardJavaFileManager>` để bọc standard file manager.
2. Override `getJavaFileForOutput(...)` và trả một `JavaFileObject` loại `Kind.CLASS`.
3. Ở object output đó, override `openOutputStream()` để ghi vào `ByteArrayOutputStream`.
4. Lưu các byte theo **binary name của class** vào map do ứng dụng quản lý; xử lý cả inner/anonymous classes khi xuất hiện.
5. Nếu cần chạy class vừa tạo, tạo class loader có chính sách riêng để `defineClass` từ bytecode đó. Bước này độc lập với JSR 199.

Không bắt buộc phải tự hiện thực output manager nếu bài toán chỉ cần kiểm tra tính hợp lệ mã nguồn, lưu kết quả biên dịch thành file hoặc dùng artifact build chuẩn.

## 9. Shortcut hiện đại: `SimpleJavaFileObject.forSource(...)` trên JDK 23+

**Từ Java 23**, `SimpleJavaFileObject` có thêm static factory method:

```java
JavaFileObject source = SimpleJavaFileObject.forSource(
        URI.create("string:///demo/Greeter.java"),
        "package demo; public class Greeter {}");
```

Đây là một **đoạn API dành riêng cho JDK 23+**, không đưa vào ví dụ Java 17 phía trên. Để dùng, import `java.net.URI`, `javax.tools.JavaFileObject` và `javax.tools.SimpleJavaFileObject`.

Factory này tạo `JavaFileObject` dạng `Kind.SOURCE` với `URI` và nội dung `String` bạn truyền vào. Nó giải quyết trường hợp phổ biến cần biểu diễn mã nguồn bằng chuỗi **mà không phải tự viết subclass chỉ để override `getCharContent(...)`**.

So sánh:

| Tiêu chí | Tự viết `StringSource extends SimpleJavaFileObject` | `SimpleJavaFileObject.forSource(...)` |
| --- | --- | --- |
| Mục tiêu | Biểu diễn mã nguồn dưới dạng `JavaFileObject` | Cùng mục tiêu |
| JDK | Chạy với JDK 17+ và những JDK trước có `SimpleJavaFileObject` | **Chỉ JDK 23+** |
| Cách cung cấp nội dung | Override `getCharContent(...)` | Truyền `String content` vào factory |
| Tùy biến thêm hành vi | Có thể override phương thức bổ sung khi thật sự cần | Phù hợp với nguồn chuỗi đơn giản |
| Có tự ghi `.class` vào bộ nhớ không? | Không | Không |

Cả hai cách đều **còn giá trị hiện nay**. Nếu chạy trên JDK 23+ và chỉ cần một source chứa chuỗi, `forSource(...)` là cách gọn, phù hợp API mới. Nếu ứng dụng giữ baseline Java 17/21 hoặc cần đặc tính riêng, subclass `SimpleJavaFileObject` vẫn là cách đúng, được tài liệu Java Compiler API mô tả.

**Không dùng `forSource(...)` trong mã cần biên dịch trên JDK 17/21:** phương thức chưa tồn tại ở các bản đó, nên sẽ báo lỗi biên dịch.

## 10. Character encoding, tính bất biến và vòng đời dữ liệu

### 10.1. Vì sao `getCharContent(boolean)` gần như luôn trả thẳng `String`?

`String` đã là chuỗi ký tự Java. Khi compiler lấy `CharSequence`, không có bước giải mã bytes từ tệp nguồn; tham số `ignoreEncodingErrors` trong phương thức này không buộc bạn tự mô phỏng lỗi UTF-8 nếu không hề nhận bytes.

Nếu source đến từ file tải lên hoặc network, **bước chuyển bytes → String** diễn ra trước khi tạo `StringSource`. Ở bước đó, ứng dụng phải chủ động chọn charset và xử lý invalid encoding. Chuyển bytes sai thành String rồi đưa cho compiler không thể được sửa chỉ bằng `getCharContent(...)`.

### 10.2. Không thay đổi source trong lúc biên dịch

Khi giữ `private final String code`, một compilation unit đọc cùng nội dung giữa các lần compiler gọi `getCharContent(...)`. Đừng dùng `StringBuilder` chia sẻ có thể bị sửa từ luồng khác để trả `CharSequence`: nội dung thay đổi giữa chừng làm lỗi khó tái hiện.

Nếu người dùng sửa tài liệu trong IDE, tạo một `StringSource` mới cho snapshot mới. Một compilation task thực hiện trên bộ source snapshot đã xác định; không dựa vào việc “cập nhật String bên trong” giữa quá trình compile.

### 10.3. URI không phải quyền truy cập tệp

`string:///demo/Greeter.java` không cấp quyền filesystem. URI này chủ yếu là định danh và gợi ý tên, dùng trong diagnostics và tương thích tên lớp. Nếu ứng dụng dùng nhiều tab/tài liệu có cùng tên class, cần quản lý mapping theo request hoặc context; không suy đoán rằng URI duy nhất toàn hệ thống.

### 10.4. Quản lý giới hạn bộ nhớ

Dùng chuỗi tránh các tệp source tạm, nhưng compiler vẫn tiêu tốn bộ nhớ cho parse tree, symbol table và bytecode. Nhiều source lớn, nhiều request đồng thời hoặc giữ `DiagnosticCollector`/`JavaFileObject` quá lâu có thể gây áp lực lên heap. Giới hạn kích thước source, số lượng compilation unit và concurrency theo yêu cầu sản phẩm.

## 11. Thiết kế integration để bảo trì lâu dài

Một phương án đóng gói trong backend hoặc IDE:

```text
CompileRequest
  - sourceUnits: [{binaryName, content}]
  - targetRelease: 17
  - dependencies: danh sách classpath/module-path được chấp thuận

CompileService
  - kiểm tra compiler runtime
  - tạo JavaFileObject từ mỗi source String
  - chọn file manager, output và options
  - gọi compilation task
  - chuẩn hóa diagnostics

CompileResult
  - success
  - diagnostics: [{sourceId, line, column, kind, message}]
  - artifacts hoặc thông tin vị trí output
```

Đây là thiết kế **minh họa của ứng dụng**, không phải các class có sẵn trong Java Compiler API.

Một lần biên dịch có thể bao gồm nhiều đơn vị nguồn; hãy truyền `List<JavaFileObject>` vào một task khi chúng cần được kiểm tra cùng nhau. Không dùng một URI ảo như “Source.java” cho mọi tệp rồi mong diagnostics chỉ ra chính xác tài liệu nào sai.

Với nhiều phiên làm việc, mỗi request nên có tên nguồn và output riêng, collector riêng và cơ chế quản lý file manager rõ ràng. Nếu source phụ thuộc thư viện ngoài, cấu hình `--class-path`/`--module-path` thay vì mặc định compiler luôn nhìn thấy toàn bộ dependency đang chạy trong service host.

Khi dùng Java Module System, API nằm trong module chuẩn `java.compiler`, còn compiler hệ thống thường được cung cấp bởi `jdk.compiler`. Ứng dụng named module có thể cần `requires java.compiler;`; runtime image cắt gọn có thể không chứa compiler, khi đó `ToolProvider.getSystemJavaCompiler()` trả `null`.

## 12. An toàn khi nhận source từ người dùng

**Biên dịch không tự chạy `main()`**, nhưng không vì thế mà có thể xem quá trình compile mã tùy ý là hoàn toàn an toàn.

- `-proc:none` trong ví dụ chủ động vô hiệu hóa annotation processing không cần thiết. Nếu bật annotation processor/plugin tùy ý, một số mã có thể **chạy trong quá trình compile**.
- Mã nguồn lớn hoặc được tạo có chủ ý gây tải có thể dùng nhiều CPU, RAM hoặc không gian lưu trữ. Cần giới hạn tài nguyên và số lượng request.
- Không nhận tùy ý các compiler options, processor path, classpath hoặc đường dẫn output từ người dùng rồi đưa thẳng vào task trong môi trường có quyền cao.
- Nếu cần **thực thi** bytecode do người dùng cung cấp, hãy dùng tiến trình/container tách biệt với quyền hạn và giới hạn phù hợp. **Nạp class tùy ý vào JVM của server** chỉ vì compile thành công là thiết kế rủi ro.
- Dùng output tạm cô lập theo request và xóa đúng phạm vi sở hữu. Nếu một luồng ghi output file trùng với luồng khác, kết quả và diagnostics khó tin cậy.
- Chọn `--release` tương thích với JDK compiler được triển khai. Đừng nhầm biên dịch cho target Java 17 với việc runtime host đang chạy Java 17.

`SimpleJavaFileObject` giúp biểu diễn input; nó **không cung cấp sandbox** và không chịu trách nhiệm bảo vệ runtime.

## 13. Lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân hay gặp | Cách khắc phục |
| --- | --- | --- |
| `getCharContent(...)` ném `UnsupportedOperationException` | Tạo `SimpleJavaFileObject` nhưng chưa override nội dung nguồn. | Subclass và override `getCharContent(...)` hoặc trên JDK 23+ dùng `forSource(...)`. |
| Compiler báo sai tên file/class | URI `.java` không khớp với public top-level type. | Đặt đúng binary name, package, URI và `Kind.SOURCE`. |
| `getTask(...)` từ chối compilation units | Đưa `Kind.CLASS`/loại khác vào danh sách source. | Mỗi unit đại diện cho source Java phải có `Kind.SOURCE`. |
| Compiler không thấy dependency của source | Classpath/module path hoặc các compilation units thiếu. | Truyền đủ nguồn, `--class-path`/`--module-path` thích hợp. |
| `getSystemJavaCompiler()` là `null` | Runtime image không có compiler. | Dùng JDK image có `jdk.compiler` hoặc triển khai compiler phù hợp. |
| Mã compile được nhưng `Greeter.class` không nằm trên disk dự kiến | File manager/output options khác kỳ vọng. | Kiểm tra `-d` và vị trí output; có thể output đang ở RAM nếu custom file manager. |
| Tưởng dùng `StringSource` nghĩa là output chắc chắn trong RAM | Mới chỉ thay thế **source Java input**. | Thêm output file manager nếu cần `byte[]` ở bộ nhớ. |
| Diagnostic không trỏ đúng tab mã nguồn | Dùng URI trùng nhau hoặc gán source id thiếu nhất quán. | Gắn URI/identity theo tên đầy đủ và context của request. |
| `forSource(...)` không biên dịch trên JDK 17/21 | Đây là API thêm từ JDK 23. | Dùng subclass như ví dụ chính trên JDK 17/21. |
| Kết quả phụ thuộc ngôn ngữ thông báo | Parse text `getMessage()` theo một ngôn ngữ cụ thể. | Ưu tiên `Kind`, source, dòng/cột; coi message là mô tả. |

## 14. Câu hỏi tự kiểm tra

**Câu 1.** `SimpleJavaFileObject` đã có constructor nhận URI và `Kind.SOURCE`. Có đủ để compiler đọc source String chưa?

**Đáp:** Chưa. Với subclass tự viết cần override `getCharContent(...)` để trả nội dung. Triển khai mặc định của lớp nền ném `UnsupportedOperationException`.

**Câu 2.** Tạo `new StringSource("demo.Greeter", code)` có tạo tệp `demo/Greeter.java` trong thư mục dự án không?

**Đáp:** Không. `string:///demo/Greeter.java` là URI định danh ảo. Source nằm trong biến `String` được trả qua `getCharContent(...)`.

**Câu 3.** Nếu compile thành công, có nghĩa `.class` cũng đã ở RAM?

**Đáp:** Không. Phải xem `JavaFileManager` và tùy chọn output. Standard file manager với `-d` ghi file `.class` ra thư mục; lưu class trong RAM cần file manager output tùy biến.

**Câu 4.** Đâu là thời điểm thực sự biên dịch?

**Đáp:** `compiler.getTask(...)` tạo `CompilationTask`; gọi `task.call()` mới chạy task.

**Câu 5.** Vì sao URI và package/public class nên nhất quán?

**Đáp:** Compiler dùng tên compilation unit để kiểm tra quy tắc tên file/class và hỗ trợ diagnostics. Sự không nhất quán có thể gây lỗi hoặc làm sai ánh xạ lỗi về tài liệu nguồn.

**Câu 6.** Muốn tạo `JavaFileObject` từ `String` trên JDK 24 mà không cần subclass, nên dùng gì?

**Đáp:** `SimpleJavaFileObject.forSource(URI, String)`, được bổ sung từ JDK 23. Nếu phải chạy trên JDK 17/21, sử dụng lớp `StringSource` như bài thực hành.

## Tài liệu chuẩn đang áp dụng

- [Java SE 26 — `SimpleJavaFileObject`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/SimpleJavaFileObject.html): constructor, `getCharContent(...)`, `isNameCompatible(...)` và `forSource(...)` (từ Java 23).
- [Java SE 26 — `JavaCompiler`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/JavaCompiler.html): ví dụ chính thức biểu diễn source trong String, `getTask(...)`, diagnostics và file manager.
- [Java SE 26 — `JavaFileObject`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/JavaFileObject.html): contract của `Kind` và compilation unit.
- [Java SE 26 — `ToolProvider`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/ToolProvider.html): compiler hệ thống.
- [Java SE 26 — `ForwardingJavaFileManager`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/ForwardingJavaFileManager.html): nền tảng mở rộng output manager khi cần bytecode lưu trong RAM.

**Ghi nhớ:** Khi mã Java chỉ tồn tại trong một chuỗi, hãy biến nó thành `JavaFileObject` loại `SOURCE` với URI ảo và `getCharContent(...)`. `SimpleJavaFileObject` là lớp nền gọn và hiện hành; `forSource(...)` là đường tắt từ JDK 23. Với bài toán **biên dịch hoàn toàn trong RAM**, còn phải kiểm soát **nơi compiler ghi `.class`**, vì source ở bộ nhớ **không tự đồng nghĩa output ở bộ nhớ**.
