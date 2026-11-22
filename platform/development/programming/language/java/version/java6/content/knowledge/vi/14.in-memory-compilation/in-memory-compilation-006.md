# Chẩn đoán lỗi theo tên tệp, dòng và cột khi biên dịch Java trong bộ nhớ

Khi ứng dụng tạo hoặc nhận mã nguồn Java dưới dạng `String`, ta vẫn có thể biên dịch và trả về lỗi theo dạng **tệp nguồn → dòng → cột**, giống công cụ phát triển hoặc hệ thống chấm bài. Java Compiler API (`javax.tools`) cung cấp cơ chế này qua `JavaFileObject`, `JavaCompiler`, `DiagnosticCollector` và `Diagnostic`. Các API chính có từ Java 6 và **vẫn còn phù hợp với Java 17+ và các JDK hiện hành**.

Vấn đề quan trọng nhất: **source nằm trong bộ nhớ vẫn cần một tên tệp logic/URI chính xác**. Nếu tạo `JavaFileObject` với URI hợp lý, mỗi `Diagnostic` có thể chỉ ra tệp ảo, dòng và cột của lỗi, cho dù hoàn toàn không có file `.java` trên ổ đĩa.

## 1. Mục tiêu

Sau bài học, bạn sẽ có thể:

1. Tạo các `JavaFileObject` từ `String` và gắn URI `string:///...` biểu diễn đúng tên file Java.
2. Chạy `JavaCompiler.CompilationTask` và thu lỗi qua `DiagnosticCollector<JavaFileObject>`.
3. Trích xuất an toàn `getSource()`, `getLineNumber()`, `getColumnNumber()`, `getKind()`, `getCode()` và `getMessage(Locale)`.
4. Phân biệt tọa độ **dòng/cột bắt đầu từ 1** với **offset ký tự bắt đầu từ 0**, xử lý `Diagnostic.NOPOS`.
5. Tạo báo cáo ổn định cho nhiều source trong bộ nhớ, gắn đúng lỗi cho đúng tên file, và chuyển vị trí sang tọa độ UI phù hợp.
6. Biết giới hạn của “biên dịch trong bộ nhớ”: **source in-memory không tự đồng nghĩa bytecode output cũng in-memory**.

## 2. Luồng từ source ảo đến lỗi theo vị trí

```text
Editor / API request / Java source String
          |
          v
JavaFileObject(URI="string:///demo/Alpha.java", Kind.SOURCE)
          |
          +---- JavaFileObject("string:///demo/Beta.java")
          |
          v
JavaCompiler.getTask(..., DiagnosticCollector, ..., compilationUnits)
          |
          v
CompilationTask.call()    ---> true / false (trạng thái biên dịch)
          |
          v
DiagnosticCollector.getDiagnostics()
          |
          +-- ERROR  demo/Alpha.java : 3 : 17
          +-- ERROR  demo/Beta.java  : 3 : 19
          |
          v
CLI / IDE / JSON API / trình chấm bài / CI
```

Bảng các API cần hiểu:

| API | Vai trò |
| --- | --- |
| `ToolProvider.getSystemJavaCompiler()` | Lấy compiler hệ thống; có thể trả `null` nếu runtime image không chứa compiler. |
| `JavaCompiler` | API chuẩn để tạo tác vụ biên dịch trong chương trình Java. |
| `JavaCompiler.CompilationTask.call()` | Thực thi biên dịch, trả `Boolean` thành công/thất bại. |
| `JavaFileObject` | Đại diện nguồn Java hoặc class output, không yêu cầu nguồn phải là file vật lý. |
| `SimpleJavaFileObject` | Base class đơn giản để biểu diễn source từ URI và nội dung chuỗi. |
| `DiagnosticCollector<JavaFileObject>` | `DiagnosticListener` có sẵn; lưu các diagnostic phát sinh để xử lý sau. |
| `Diagnostic<? extends JavaFileObject>` | Một lỗi/cảnh báo, bao gồm loại thông điệp, source, vị trí và message. |
| `StandardJavaFileManager` | Quản lý file/dependency/output cho compiler; cần quản lý vòng đời và đóng khi xong. |

Có hai “đường ra” khác nhau: `task.call()` cho **kết quả của tác vụ**, còn collector cho **danh sách thông tin để chẩn đoán**. Ví dụ, warning có thể xuất hiện dù `call()` trả `true`. Đừng thay trạng thái biên dịch bằng biểu thức `errorCount == 0`.

## 3. Gán tên file ảo đúng cho source trong bộ nhớ

Một class public `demo.Alpha` thường được biên dịch với tên file `Alpha.java` và nội dung `package demo;`. Khi không có file trên disk, ta vẫn cần URI biểu diễn đường dẫn logic đó.

```java
static final class Source extends SimpleJavaFileObject {
    private final String content;

    Source(String binaryName, String content) {
        super(URI.create("string:///" + binaryName.replace('.', '/')
                + Kind.SOURCE.extension), Kind.SOURCE);
        this.content = content;
    }

    @Override
    public CharSequence getCharContent(boolean ignoreEncodingErrors) {
        return content;
    }
}
```

Đây là **đoạn class thành phần**, dùng đầy đủ trong ví dụ mục 5. Constructor nhận binary name như `demo.Alpha` và tạo URI `string:///demo/Alpha.java`. `Kind.SOURCE.extension` là phần đuôi `.java`, giúp không viết cứng tên tệp.

**Vì sao URI quan trọng?**

- `JavaFileObject.toUri()` là danh tính logic cho source; `Diagnostic.getSource()` có thể trỏ về chính object này.
- Với `string:///demo/Alpha.java`, ta có thể ánh xạ về filename `demo/Alpha.java` trong giao diện.
- Đường dẫn file ảo cần khớp với **package và tên public class** để compiler không báo lỗi tên file/class không mong muốn.
- Nên dùng URI **ổn định và duy nhất theo từng source** trong cùng tác vụ; nếu tạo nhiều source với cùng tên, có thể gây xung đột hoặc khó ghép chẩn đoán.
- Scheme `string` là lựa chọn ví dụ để đánh dấu dữ liệu ảo; không phải một tệp có thật hay một đường dẫn phải tồn tại trên filesystem.
- Khi nhận tên class/filename từ người dùng, hãy **validate** và xây dựng URI có kiểm soát; tránh dùng trực tiếp chuỗi bất kỳ dẫn tới path giả, traversal, ký tự URI không hợp lệ hoặc đụng tên của source khác.

`SimpleJavaFileObject` mặc định không cung cấp nội dung nguồn trong chuỗi nên subclass cần override `getCharContent(...)`. Các API chuẩn này vẫn được dùng trên Java 17+. Với JDK 23+, `SimpleJavaFileObject.forSource(URI, String)` cũng có thể tạo source object trực tiếp; vì vậy không cần viết subclass nếu ứng dụng chỉ hỗ trợ JDK tương ứng. Để ví dụ chạy trên Java 17+, chúng ta chọn cách subclass.

### Tên của diagnostic không tự là đường dẫn vật lý

Nếu `source.toUri()` là `string:///demo/Alpha.java`, giá trị `source.getName()` hoặc đường dẫn suy ra từ URI là **tên logic của source ảo**. Không được thử đọc file `demo/Alpha.java` trên ổ đĩa chỉ vì diagnostic báo tên như vậy.

Nếu sản phẩm dùng tên file hiển thị riêng (ví dụ tab `Main.java` hoặc file upload), hãy lưu mapping từ **URI source** sang **tên client đã kiểm tra** trong suốt tác vụ. Tránh hiển thị URI nội bộ hoặc đường dẫn hệ thống ngoài ý muốn.

## 4. Các trường quan trọng của `Diagnostic`

| Phương thức | Kết quả và quy ước |
| --- | --- |
| `getKind()` | `ERROR`, `WARNING`, `MANDATORY_WARNING`, `NOTE`, `OTHER`. |
| `getSource()` | Trả source object gắn với diagnostic, hoặc `null` nếu thông báo không gắn file. |
| `getLineNumber()` | Số dòng **1-based**; `Diagnostic.NOPOS` nếu không xác định. |
| `getColumnNumber()` | Số cột **1-based**; `Diagnostic.NOPOS` nếu không xác định. |
| `getPosition()` | Offset ký tự **0-based** của vị trí lỗi; `Diagnostic.NOPOS` nếu không có. |
| `getStartPosition()` | Offset bắt đầu của vùng liên quan; có thể là `NOPOS`. |
| `getEndPosition()` | Offset kết thúc của vùng liên quan; có thể là `NOPOS`. |
| `getCode()` | Mã diagnostic do compiler cung cấp; có thể `null` và phụ thuộc implementation. |
| `getMessage(Locale)` | Message dành cho người đọc; phụ thuộc compiler/JDK/locale. |

Vị trí dòng/cột bắt đầu từ **1**, còn offset source bắt đầu từ **0**. `Diagnostic.NOPOS` báo không có vị trí, thường có giá trị `-1`. `Diagnostic.getSource()` **có thể là `null`** với lỗi cấu hình, option hoặc vấn đề không gắn vào một source xác định.

Trong interface `Diagnostic`, nếu `getPosition() == NOPOS`, các phương thức line/column/start/end cũng trả `NOPOS`. Không đoán dòng 1/cột 1 khi không có vị trí.

### Tên file, dòng và cột: thứ tự xử lý an toàn

1. Đọc `Diagnostic.getSource()`. Nếu `null`, hiển thị nhóm “thông báo không gắn tệp”, không dereference source.
2. Nếu có source, lấy `toUri()` hoặc `getName()`. Chỉ chuyển URI thành tên hiển thị theo quy tắc của sản phẩm.
3. Kiểm tra `getLineNumber() == Diagnostic.NOPOS`; nếu có vị trí dòng, tiếp tục kiểm tra cột.
4. Khi xuất JSON, dùng `null` hoặc trường không có cho vị trí thiếu; không gửi `-1` như một dòng hợp lệ.
5. Dùng `getKind()` để phân loại severity và `getMessage(locale)` để giải thích cho người dùng.

## 5. Chương trình hoàn chỉnh: hai file source trong bộ nhớ, hai lỗi có vị trí

Ví dụ dưới đây cố tình tạo lỗi độc lập trong hai class `demo.Alpha` và `demo.Beta`. Chúng **không tồn tại trên disk**. Chương trình chứa cả hai source, gọi compiler và in **tên file ảo, dòng, cột** của mỗi `ERROR`.

Tạo tệp **`InMemoryLocationDemo.java`** (Java 17+):

```java
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import javax.tools.*;

public final class InMemoryLocationDemo {
    private static final class Source extends SimpleJavaFileObject {
        private final String content;

        Source(String binaryName, String content) {
            super(URI.create("string:///" + binaryName.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.content = content;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return content;
        }
    }

    private static String fileLabel(Diagnostic<? extends JavaFileObject> d) {
        if (d.getSource() == null) {
            return "<no-source>";
        }
        URI uri = d.getSource().toUri();
        String path = uri.getPath();
        if (path == null) {
            return d.getSource().getName();
        }
        return path.startsWith("/") ? path.substring(1) : path;
    }

    private static String locationNumber(long number) {
        return number == Diagnostic.NOPOS ? "?" : Long.toString(number);
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("A JDK compiler is required");
        }

        JavaFileObject alpha = new Source("demo.Alpha",
                "package demo;\n"
                + "public class Alpha {\n"
                + "    int count = \"wrong\";\n"
                + "}\n");
        JavaFileObject beta = new Source("demo.Beta",
                "package demo;\n"
                + "public class Beta {\n"
                + "    void test() { missing(); }\n"
                + "}\n");

        DiagnosticCollector<JavaFileObject> collector =
                new DiagnosticCollector<>();
        try (StandardJavaFileManager manager =
                     compiler.getStandardFileManager(
                             collector, Locale.ENGLISH, StandardCharsets.UTF_8)) {
            Boolean success = compiler.getTask(
                    null, manager, collector, List.of("-proc:none"),
                    null, List.of(alpha, beta)).call();

            var errors = collector.getDiagnostics().stream()
                    .filter(d -> d.getKind() == Diagnostic.Kind.ERROR)
                    .sorted(Comparator
                            .comparing((Diagnostic<? extends JavaFileObject> d)
                                    -> fileLabel(d))
                            .thenComparingLong(Diagnostic::getLineNumber)
                            .thenComparingLong(Diagnostic::getColumnNumber))
                    .toList();

            System.out.println("compiled=" + success);
            System.out.println("errors=" + errors.size());
            for (var d : errors) {
                System.out.println(d.getKind()
                        + " " + fileLabel(d)
                        + ":" + locationNumber(d.getLineNumber())
                        + ":" + locationNumber(d.getColumnNumber()));
            }
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac -encoding UTF-8 InMemoryLocationDemo.java
java InMemoryLocationDemo
```

**Stdout đã chạy và kiểm chứng trên OpenJDK 24:**

```text
compiled=false
errors=2
ERROR demo/Alpha.java:3:17
ERROR demo/Beta.java:3:19
```

Giải thích:

- Hai source đều có `package demo;` ở dòng 1, class definition ở dòng 2 và lỗi ở dòng 3.
- `Alpha.java` gán `String` cho `int`; `Beta.java` gọi phương thức `missing()` không tồn tại.
- `getSource().toUri().getPath()` trả đường dẫn logic từ `string:///demo/...`; code bỏ dấu `/` đầu để hiển thị `demo/Alpha.java`.
- `getLineNumber()` và `getColumnNumber()` trả vị trí mà compiler chỉ ra. Trong kiểm chứng này, vị trí lần lượt là `3:17` và `3:19`. Vị trí chi tiết có thể thay đổi theo compiler/JDK hoặc cách trình bày source, vì vậy không nên dùng chuỗi này như một giao thức cam kết cho mọi môi trường.
- `Comparator` sắp xếp kết quả theo **tên file rồi dòng/cột** để đầu ra dễ dự đoán khi có nhiều compilation units. API không yêu cầu ứng dụng dựa vào một thứ tự bất biến của mọi nguồn diagnostic.
- `-proc:none` tắt annotation processing cho ví dụ, tránh các processor ngoài ý muốn thay đổi kết quả hoặc tạo thêm diagnostics.
- `compiled=false` là kết quả compile các source ảo có lỗi. Bản thân chương trình demo đã biên dịch và chạy thành công với lệnh `javac` ở shell.

**Phạm vi “trong bộ nhớ”:** `alpha` và `beta` được cấp vào compiler dưới dạng `JavaFileObject` từ `String`, không có các tệp `Alpha.java`/`Beta.java` trên đĩa. Điều đó **không tự bảo đảm mọi class file biên dịch thành công cũng ở trong bộ nhớ**; muốn bắt bytecode output vào `byte[]` cần xây dựng `JavaFileManager` phù hợp. Trong ví dụ này biên dịch thất bại, nên không có class file hợp lệ của hai source được sinh ra.

## 6. Tạo báo cáo lỗi cho người dùng hoặc API

Trong sản phẩm thật, có thể tách format text khỏi dữ liệu. Một payload hợp lý:

```json
{
  "compiled": false,
  "diagnostics": [
    {
      "kind": "ERROR",
      "filename": "demo/Alpha.java",
      "line": 3,
      "column": 17,
      "message": "Thông điệp do compiler tạo ra"
    },
    {
      "kind": "ERROR",
      "filename": "demo/Beta.java",
      "line": 3,
      "column": 19,
      "message": "Thông điệp do compiler tạo ra"
    }
  ]
}
```

Đây là **mô hình payload minh họa**. Trong ứng dụng thật, `message` phải được lấy từ `d.getMessage(locale)`; không dùng câu chữ ở JSON mẫu như output thực tế của compiler. Nếu thiếu vị trí, đổi `line`/`column` thành `null` hoặc bỏ trường theo hợp đồng API.

### Chuyển `Diagnostic` sang object có cấu trúc

Đoạn code dưới đây là **thành phần để đặt trong chương trình đã có `Diagnostic`**, không phải chương trình độc lập:

```java
record Problem(
        String kind,
        String filename,
        Long line,
        Long column,
        String message) {}

static Problem toProblem(Diagnostic<? extends JavaFileObject> d) {
    String filename = (d.getSource() == null)
            ? null
            : d.getSource().toUri().toString();

    Long line = (d.getLineNumber() == Diagnostic.NOPOS)
            ? null : d.getLineNumber();
    Long column = (d.getColumnNumber() == Diagnostic.NOPOS)
            ? null : d.getColumnNumber();

    return new Problem(
            d.getKind().name(),
            filename,
            line,
            column,
            d.getMessage(Locale.ENGLISH));
}
```

Lưu ý: `filename` trong đoạn này là **URI**, như `string:///demo/Alpha.java`, chưa phải nhãn hiển thị. Phần ứng dụng cần mapping/chuẩn hóa tên file phù hợp trước khi công bố ra UI hoặc API công khai. Nếu nguồn là file thật, tránh làm lộ đường dẫn tuyệt đối nội bộ.

## 7. Quy đổi 1-based sang vị trí editor 0-based

Nhiều API của trình soạn thảo, bao gồm một số giao thức dành cho editor, dùng **dòng/cột bắt đầu từ 0**. `Diagnostic` dùng 1-based. Trong trường hợp nguồn và đơn vị đếm cột tương thích:

```java
// Đoạn code minh họa, d có kiểu Diagnostic<?>.
long line0 = d.getLineNumber() - 1;
long column0 = d.getColumnNumber() - 1;
```

**Chỉ thực hiện khi cả hai vị trí khác `Diagnostic.NOPOS`**. Không trừ 1 ở trạng thái không có vị trí. Nếu cần output cho Language Server Protocol (LSP), còn phải tuân thủ **đơn vị mã hóa vị trí** mà client/server thỏa thuận; nhiều triển khai mặc định dùng UTF-16 code units. Dòng/cột do công cụ báo có thể cần ánh xạ thêm khi source chứa ký tự Unicode bổ sung, tab hoặc cách xử lý newline khác nhau.

Các trường hợp dễ nhầm:

- **CRLF so với LF:** nên giữ nguyên đúng source mà compiler đã đọc; nếu bạn tự chuẩn hóa xuống dòng trước khi biên dịch, mapping sang editor ban đầu có thể lệch.
- **Tab:** cột được compiler báo không tự đồng nghĩa số pixel trong editor; tab có độ rộng hiển thị tùy cấu hình.
- **Ký tự ngoài Basic Multilingual Plane:** một ký tự có thể chiếm hai UTF-16 code units. Không mặc định cột do mọi tool và UI dùng cùng hệ đếm.
- **Source thay đổi trong lúc compile:** vị trí trả về phản ánh source tại thời điểm compiler xử lý, không nhất thiết còn đúng với văn bản hiện hành trong editor.
- **Vị trí vùng lỗi:** nếu cần highlight chính xác, nghiên cứu thêm `getStartPosition()`/`getEndPosition()` và mapping offsets; chỉ có dòng/cột giúp đưa con trỏ tới điểm lỗi, chưa chắc đại diện toàn vùng cần gạch chân.

Ở mức ứng dụng, nên liên kết diagnostics với **phiên bản source** hoặc request ID cụ thể; tránh dùng vị trí cũ để tô màu một phiên bản nội dung mới.

## 8. Lỗi, cảnh báo và vấn đề không có vị trí tệp

`Diagnostic.Kind` có các loại thường thấy:

| Loại | Khi nào xuất hiện |
| --- | --- |
| `ERROR` | Vi phạm cú pháp, kiểu dữ liệu, thiếu symbol... thường làm biên dịch thất bại. |
| `WARNING` | Vấn đề nên chú ý nhưng thường vẫn cho compile thành công. |
| `MANDATORY_WARNING` | Cảnh báo được công cụ yêu cầu báo ở các trường hợp do đặc tả xác định. |
| `NOTE` | Thông tin bổ sung, không nhất thiết mang ý nghĩa thất bại. |
| `OTHER` | Loại khác do công cụ xác định. |

Ví dụ `javac` có thể phát cảnh báo khi bật `-Xlint:unchecked`, `-Xlint:rawtypes`, `-Xlint:deprecation`. Có warning không đồng nghĩa compile thất bại; bật `-Werror` có thể khiến compile thất bại chỉ vì warning.

Một diagnostic có thể không gắn với source, đặc biệt trong trường hợp liên quan đến option, module path, annotation processing hoặc môi trường. Khi đó:

```text
kind=ERROR
filename=<no-source>
line=?
column=?
```

Đây là **dạng hiển thị mẫu cho tình huống thiếu source**; không khẳng định compiler luôn phát đúng nội dung mẫu. Trong code ví dụ mục 5, helper `fileLabel` và `locationNumber` đã hỗ trợ `getSource()==null` và `Diagnostic.NOPOS`, nên sẽ không ném `NullPointerException` khi cố in tọa độ thiếu.

Nếu phát hiện `Diagnostic.getCode()` khác `null`, có thể lưu nó để gỡ lỗi theo **compiler cụ thể**. Không coi mã hay `getMessage(Locale)` là khóa nghiệp vụ ổn định qua mọi phiên bản JDK.

## 9. Chẩn đoán nhiều tệp trong một lần biên dịch

Một compilation task có thể xử lý nhiều `JavaFileObject`. Khi các class tham chiếu lẫn nhau, cách này giúp compiler phân giải các class cùng tác vụ, đồng thời mỗi diagnostic giữ được tham chiếu tới source của nó khi có thể.

Các quy tắc để giảm lỗi ánh xạ:

1. **Tên đúng với source:** `public class Demo` trong package `com.example` nên có URI tương ứng `.../com/example/Demo.java`.
2. **Không trùng URI vô cớ:** hai editor tab có tên giống nhau phải được ánh xạ sang tên đầy đủ khác nhau hoặc được xử lý riêng, tránh lẫn kết quả.
3. **Giữ nguyên source:** không chỉnh content string sau khi dựng `JavaFileObject` nhưng trước khi xử lý diagnostics.
4. **Không dùng index của danh sách thay cho tên file:** diagnostic có thể được báo theo thứ tự khác thứ tự source được truyền vào.
5. **Không mặc định mọi lỗi có source:** cả collection nên hỗ trợ global diagnostics ngoài tệp.
6. **Nhớ dependencies:** code có thể lỗi `cannot find symbol` vì thiếu classpath/module path, không nhất thiết do source đang có typo.
7. **Giữ metadata tách biệt:** dùng URI hoặc ID nội bộ để map file; tên hiển thị, thời điểm và phiên bản source thuộc trách nhiệm ứng dụng.

`getDiagnostics()` trả một danh sách diagnostics nhận được trong collector. Với reporting chính xác theo lần biên dịch, tạo **collector riêng cho mỗi task**. Không tái sử dụng collector cũ rồi nhầm các diagnostic đã thu trước đó là lỗi của source hiện tại.

## 10. Biên dịch source ảo và lưu bytecode: hai bài toán khác nhau

Lệnh kiểu:

```java
JavaFileObject unit = new Source(
        "demo.Success",
        "package demo; public class Success {}");
```

chỉ thể hiện rằng **source** được cung cấp từ bộ nhớ. Nếu task biên dịch thành công mà không có file manager tùy biến, compiler có thể sử dụng **output trên filesystem** theo file manager và options được cấu hình. Nếu cần nhận `Success.class` thành `byte[]` mà không ghi file vật lý, phải sử dụng `JavaFileManager` tùy biến (thường kế thừa `ForwardingJavaFileManager`, override `getJavaFileForOutput`, dùng `JavaFileObject` cung cấp `OutputStream` ghi vào `ByteArrayOutputStream`).

Với bài toán chỉ **kiểm tra mã và trả về lỗi/cảnh báo**, có thể chạy source chứa lỗi như mục 5, hoặc cấp một output directory tạm riêng rồi dọn nếu có code hợp lệ. Nếu công cụ nhận source không tin cậy, xem xét process isolation, resource limits và annotation processing. `-proc:none` chỉ tắt một phần cơ chế chạy code trong lúc compile, **không biến JavaCompiler thành sandbox**.

## 11. Quy trình kiểm thử diagnostics

Nên có các tình huống test cụ thể:

| Test case | Điều cần kiểm chứng |
| --- | --- |
| Source hợp lệ | `call()==true`, không có `ERROR`, kết quả source map đúng file. |
| Sai kiểu dữ liệu | `call()==false`, `getKind()==ERROR`, filename/dòng/cột trỏ tới dòng sai. |
| Hai file cùng lỗi | Phân biệt `Alpha.java` và `Beta.java`, không gán chéo diagnostic. |
| Cảnh báo với `-Xlint` | Có `WARNING`/`MANDATORY_WARNING` nhưng có thể `call()==true`. |
| Chạy với `-Werror` | Compilation result phản ánh chính sách fail do warning. |
| Global diagnostic | Formatter không ném lỗi nếu `getSource()==null` hoặc `NOPOS`. |
| Source CRLF/Unicode | Vị trí editor map đúng theo phiên bản/định dạng source thực tế. |
| Compiler không có | Code xử lý `getSystemJavaCompiler()==null` rõ ràng. |
| Không đủ classpath | Báo lỗi dependencies thiếu, không quy kết nhầm tất cả cho source. |

Với test portable qua nhiều JDK, nên assert **loại lỗi, đúng tệp, dòng và tình trạng có vị trí**, thay vì assert nguyên văn message của `javac`. Số cột hoặc offset có thể phụ thuộc compiler và token được báo; chỉ assert tọa độ chính xác khi đã khóa compiler/source/test fixture tương ứng.

### Checklist trước khi gửi về frontend

- [ ] Compiler system có sẵn, options và classpath/module path được xác định.
- [ ] Mỗi source trong bộ nhớ có URI logic hợp lệ và duy nhất.
- [ ] `DiagnosticCollector` được truyền vào `getTask` đúng tham số.
- [ ] Mỗi compilation task có report độc lập và file manager được đóng.
- [ ] `getSource()` được kiểm tra null; `line/column` được kiểm tra `NOPOS`.
- [ ] Kind và trạng thái `call()` được lưu riêng, không tính success từ số ERROR đơn thuần.
- [ ] Tên file/URI được ánh xạ an toàn sang tên client nhìn thấy.
- [ ] Dòng/cột/offset được quy đổi sang API UI theo đúng base và encoding.
- [ ] Version của source được giữ cùng diagnostics để tránh sai lệch sau khi editor đổi.
- [ ] Message được escape khi render HTML; không dựa vào exact text giữa các JDK.

## 12. Những lỗi phổ biến

**Lỗi 1 — chỉ có `String` source, không có tên file.** Compiler có thể không có URI hợp lý để gắn diagnostic hoặc gặp lỗi tên class/file. **Sửa:** tạo `JavaFileObject` với binary name và URI tương ứng file `.java`.

**Lỗi 2 — lấy line/column bằng cách parse stderr.** Chuỗi output có thể thay đổi theo locale và JDK. **Sửa:** dùng `Diagnostic.getLineNumber()` và `getColumnNumber()`.

**Lỗi 3 — luôn gọi `d.getSource().getName()`.** Có diagnostic không có source và ném NPE. **Sửa:** kiểm tra `getSource()==null` rồi dùng nhãn global diagnostic.

**Lỗi 4 — coi dòng/cột là 0-based.** Java Diagnostic quy định 1-based. **Sửa:** trừ 1 chỉ tại ranh giới API UI có 0-based và sau khi kiểm tra `NOPOS`.

**Lỗi 5 — nhầm offset ký tự với byte.** `getPosition()` không phải byte index UTF-8. **Sửa:** giữ nguyên source version và quy đổi đúng theo đơn vị vị trí của editor.

**Lỗi 6 — tên file ảo trùng nhau.** Báo cáo có thể gán sai lỗi giữa nhiều file. **Sửa:** đặt URI duy nhất và dùng mapping URI → editor file ID.

**Lỗi 7 — thấy `compiled=false`, đếm `ERROR==0` rồi kết luận compiler sai.** Các lỗi không nhất thiết đều có diagnostic ở source và `-Werror` có thể fail do warning. **Sửa:** đọc task result, diagnostics, writer output và exception riêng.

**Lỗi 8 — cho rằng “in-memory source” nghĩa “in-memory class output”.** Với standard file manager, output có thể ghi file. **Sửa:** dùng file manager chuyên biệt khi thật sự cần bytecode in-memory, hoặc output directory tạm nếu chỉ cần kiểm tra.

**Lỗi 9 — hiển thị nguyên văn internal path hoặc URI do client đưa.** Có thể làm lộ thông tin môi trường hoặc tạo link nguy hiểm. **Sửa:** xác thực input, chuẩn hóa tên file và escape dữ liệu khi hiển thị.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Source `String` chứa `package demo; public class Alpha`. Vì sao nên tạo URI `string:///demo/Alpha.java`?

**Đáp án:** vì đó là tên file logic khớp package/public class, giúp compiler xác định compilation unit và cho phép diagnostics gắn đúng tệp ảo.

**Câu 2.** `d.getLineNumber()==3` và `d.getColumnNumber()==17` nghĩa là gì?

**Đáp án:** lỗi được báo ở dòng thứ 3, cột thứ 17, tính từ 1. Nếu UI dùng 0-based cùng đơn vị mã hóa, tọa độ tương ứng sẽ là dòng 2/cột 16.

**Câu 3.** Nếu `d.getSource()==null` hoặc `getLineNumber()==Diagnostic.NOPOS`?

**Đáp án:** hiển thị một thông báo không có đường dẫn hoặc tọa độ đầy đủ, không tự điền tệp/dòng/cột và không dereference source null.

**Câu 4.** Vì sao `task.call()==true` không nhất thiết đồng nghĩa `collector.getDiagnostics().isEmpty()`?

**Đáp án:** compiler có thể báo warning hoặc note trong một lần biên dịch thành công.

**Câu 5.** Đưa source từ bộ nhớ vào compiler có tự động trả bytecode dưới dạng `byte[]` không?

**Đáp án:** không. Muốn thu class output ở bộ nhớ phải triển khai file manager/output `JavaFileObject` thích hợp; `SimpleJavaFileObject` dùng làm input chưa giải quyết bài toán output.

## Tài liệu Java hiện hành

- [Diagnostic — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/Diagnostic.html) — hợp đồng `getSource()`, `NOPOS`, line/column và character offsets.
- [DiagnosticCollector — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/DiagnosticCollector.html) — listener lưu các thông báo và trả danh sách.
- [SimpleJavaFileObject — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/SimpleJavaFileObject.html) — tạo source ảo và tiện ích `forSource` từ JDK 23.
- [JavaCompiler — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/JavaCompiler.html) — tạo `CompilationTask` và file manager.
- [JavaFileObject — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/JavaFileObject.html) — source và output abstraction.
- [ToolProvider — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/ToolProvider.html) — tìm system compiler.

**Ghi nhớ:** để chẩn đoán chính xác theo **tên tệp, dòng và cột** khi compile source trong bộ nhớ, hãy đặt URI logic đúng cho mỗi `JavaFileObject`, truyền `DiagnosticCollector` vào compiler, đọc dữ liệu `Diagnostic` theo hợp đồng 1-based/`NOPOS` và giữ mapping giữa source URI với tên file/phiên bản mà người dùng thấy.
