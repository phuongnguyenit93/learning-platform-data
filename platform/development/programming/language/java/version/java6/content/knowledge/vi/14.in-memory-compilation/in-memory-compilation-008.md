# Kiểm thử biên dịch thành công, thất bại và thiếu dependency

## Mục tiêu học tập

Trong chủ đề **Biên dịch trong bộ nhớ**, chương trình Java có thể gửi một `String` chứa mã nguồn cho `JavaCompiler`, nhận kết quả và diagnostics mà không phải ghi tệp nguồn `.java` ra đĩa. Bài này tập trung vào **kiểm thử hành vi biên dịch** thay vì chỉ gọi compiler một lần.

Sau bài này, bạn có thể:

- Viết các phép kiểm tra độc lập cho **source hợp lệ**, **source sai cú pháp** và **source thiếu dependency**.
- Thu kết quả từ `JavaCompiler.CompilationTask.call()` và lỗi từ `DiagnosticCollector<JavaFileObject>`, không phụ thuộc nguyên văn thông báo lỗi.
- Kiểm soát classpath, output và từng compilation task để tránh phép thử bị ảnh hưởng bởi file `.class` hay thư viện còn sót lại.
- Xác nhận lỗi thiếu dependency bằng phép đối chứng: giữ nguyên source consumer, cung cấp bytecode thư viện còn thiếu, rồi biên dịch lại thành công.
- Biết phân biệt lỗi mã nguồn với compiler không sẵn có, tham số sai, vấn đề I/O và rủi ro khi xử lý code của người dùng.

Các API dưới đây thuộc `javax.tools`, vẫn được hỗ trợ trong **Java hiện đại**. Ví dụ đầy đủ dùng Java 17+ và đã được kiểm tra trên JDK 24; không sử dụng cơ chế Java cũ đã lỗi thời.

## 1. Vì sao một bộ test biên dịch cần kiểm tra cả ca thất bại?

Một ứng dụng IDE, hệ thống chấm bài, công cụ sinh mã hoặc dịch vụ kiểm tra source cần xác định không chỉ khi nào compiler tạo ra bytecode, mà còn khi nào compiler **phải từ chối** một đơn vị nguồn.

```text
Source String
    |
    v
JavaFileObject (Kind.SOURCE, URI ảo)
    |
    v
JavaCompiler.getTask(...).call()
    |
    +-- true  --> không có lỗi nghiêm trọng --> output theo file manager
    |
    +-- false --> tra DiagnosticCollector --> lỗi source/dependency
```

Tuy nhiên, `false` chưa đủ để phân loại nguyên nhân. Một source sai cú pháp và một source đúng nhưng thiếu lớp thư viện đều có thể cho `call() == false` và một hoặc nhiều `Diagnostic.Kind.ERROR`. Cần cố ý tạo **fixture** và môi trường riêng cho từng ca.

| Ca kiểm thử | Nội dung | Classpath dành cho dependency ứng dụng | Kỳ vọng |
| --- | --- | --- | --- |
| Thành công | `demo.Hello` với phương thức trả `42` | Thư mục rỗng | `call() == true`, không `ERROR`, có `Hello.class` |
| Sai cú pháp | `demo.Broken` chứa `int x = ;` | Thư mục rỗng | `call() == false`, có `ERROR` |
| Thiếu dependency | `app.UseHelper` gọi `lib.Helper.say()` | Thư mục rỗng | `call() == false`, có `ERROR` |
| Khắc phục thiếu dependency | **Cùng source `app.UseHelper`** | Có `lib/Helper.class` | `call() == true`, không `ERROR`, có `UseHelper.class` |

Ca cuối là phép thử đối chứng quyết định: nếu source không đổi và chỉ cung cấp dependency đúng cách, sự chuyển đổi từ lỗi sang thành công chứng minh vấn đề về khả năng tìm dependency. Đừng chỉ nhận diện “missing dependency” bằng một đoạn text lỗi tiếng Anh.

## 2. Công cụ kiểm thử của Java Compiler API

| API | Tác dụng |
| --- | --- |
| `ToolProvider.getSystemJavaCompiler()` | Lấy compiler hệ thống, có thể trả `null` nếu runtime không có compiler. |
| `JavaCompiler.getTask(...)` | Tạo nhiệm vụ biên dịch với các compilation units, options, file manager và diagnostics. |
| `CompilationTask.call()` | **Thực sự chạy biên dịch**, trả `Boolean` biểu diễn thành công/thất bại. |
| `SimpleJavaFileObject` | Lớp nền thuận tiện để đưa source đang nằm trong `String` cho compiler. |
| `JavaFileObject.Kind.SOURCE` | Đánh dấu đối tượng là mã nguồn Java, khác `Kind.CLASS` cho bytecode. |
| `getCharContent(boolean)` | Trả nội dung mã nguồn từ `String`. |
| `StandardJavaFileManager` | Quản lý các file/dependency/output theo cơ chế chuẩn. |
| `DiagnosticCollector<JavaFileObject>` | Nhận errors, warnings và notes dưới dạng đối tượng có cấu trúc. |
| `Diagnostic.Kind.ERROR` | Nhãn lỗi dùng để kiểm tra outcome mà không cần so khớp nguyên văn message. |

**Cần phân biệt:** thiếu compiler là lỗi **môi trường**, không phải source bị từ chối hợp lệ. Nếu `ToolProvider.getSystemJavaCompiler()` trả `null`, một số runtime image rút gọn có thể đã không chứa triển khai `jdk.compiler`. Phải báo lỗi cấu hình thay vì chấm mã nguồn là sai.

Một compilation task có thể ném exception khi cấu hình option sai hoặc file manager gặp lỗi. Trường hợp này không đồng nghĩa với kết quả compiler đã chạy và trả `false` vì source có lỗi.

## 3. Ví dụ Java 17+ chạy độc lập: bốn phép thử

Ví dụ tạo các `JavaFileObject` từ chuỗi, biên dịch nhiều lần với **classpath và output riêng**, thu diagnostics và dùng một hàm `check` để **thực sự fail** nếu kỳ vọng sai. `check` chủ động ném `AssertionError`, nên không phụ thuộc Java `assert` có được bật qua `-ea` hay không.

Tạo tệp **`CompileCasesDemo.java`** với toàn bộ nội dung:

```java
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class CompileCasesDemo {
    static final class StringSource extends SimpleJavaFileObject {
        private final String code;

        StringSource(String binaryName, String code) {
            super(URI.create("string:///" +
                    binaryName.replace('.', '/') + Kind.SOURCE.extension),
                    Kind.SOURCE);
            this.code = code;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return code;
        }
    }

    record Result(boolean success, boolean hasError) {}

    static Result compile(
            JavaCompiler compiler,
            Path classpath,
            Path output,
            JavaFileObject... sources) throws Exception {
        Files.createDirectories(output);
        var diagnostics = new DiagnosticCollector<JavaFileObject>();
        try (StandardJavaFileManager files = compiler.getStandardFileManager(
                null, Locale.ROOT, StandardCharsets.UTF_8)) {
            boolean success = Boolean.TRUE.equals(
                    compiler.getTask(
                            null,
                            files,
                            diagnostics,
                            List.of("--release", "17", "-proc:none",
                                    "-classpath", classpath.toString(),
                                    "-d", output.toString()),
                            null,
                            List.of(sources))
                    .call());
            boolean hasError = diagnostics.getDiagnostics().stream()
                    .anyMatch(d -> d.getKind() == Diagnostic.Kind.ERROR);
            return new Result(success, hasError);
        }
    }

    static void check(String label, boolean condition) {
        if (!condition) {
            throw new AssertionError(label);
        }
        System.out.println(label + ": true");
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Compiler not available");
        }

        Path root = Files.createTempDirectory("compiler-cases-");
        try {
            Path empty = Files.createDirectories(root.resolve("empty"));
            Path dependencies = Files.createDirectories(root.resolve("deps"));

            var valid = new StringSource("demo.Hello",
                    "package demo; public class Hello {" +
                    " public static int value() { return 42; } }");
            Result ok = compile(compiler, empty, root.resolve("valid"), valid);
            check("Success", ok.success() && !ok.hasError());
            check("Success class exists",
                    Files.exists(root.resolve("valid/demo/Hello.class")));

            var malformed = new StringSource("demo.Broken",
                    "package demo; public class Broken { int x = ; }");
            Result syntax = compile(compiler, empty, root.resolve("syntax"), malformed);
            check("Syntax failure", !syntax.success());
            check("Syntax ERROR diagnostic", syntax.hasError());

            var consumer = new StringSource("app.UseHelper",
                    "package app; public class UseHelper {" +
                    " public String message() { return lib.Helper.say(); } }");
            Result missing = compile(compiler, empty, root.resolve("missing"), consumer);
            check("Missing dependency fails", !missing.success());
            check("Missing dependency ERROR diagnostic", missing.hasError());

            var helper = new StringSource("lib.Helper",
                    "package lib; public class Helper {" +
                    " public static String say() { return \"ok\"; } }");
            Result lib = compile(compiler, empty, dependencies, helper);
            check("Helper compiled", lib.success() && !lib.hasError());

            Result fixed = compile(compiler, dependencies, root.resolve("fixed"), consumer);
            check("After classpath fix", fixed.success() && !fixed.hasError());
            check("Restored class exists",
                    Files.exists(root.resolve("fixed/app/UseHelper.class")));
        } finally {
            try (var tree = Files.walk(root)) {
                for (Path p : tree.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(p);
                }
            }
        }
    }
}
```

### Biên dịch và thực thi

Từ thư mục chứa `CompileCasesDemo.java`, sử dụng **JDK 17+ có `javac`**:

```bash
javac CompileCasesDemo.java
java CompileCasesDemo
```

**Đầu ra đã kiểm tra trên JDK 24:**

```text
Success: true
Success class exists: true
Syntax failure: true
Syntax ERROR diagnostic: true
Missing dependency fails: true
Missing dependency ERROR diagnostic: true
Helper compiled: true
After classpath fix: true
Restored class exists: true
```

Đây không chỉ là các thông báo tham khảo. Mỗi dòng chỉ được in khi điều kiện của `check` thỏa mãn; nếu có điều kiện sai, `AssertionError` làm chương trình kiểm thử kết thúc với lỗi. Không cần thêm thư viện kiểm thử nào ngoài API chuẩn Java.

Ứng dụng tạo `root` tạm, các thư mục `empty`, `deps`, `valid`, `syntax`, `missing` và `fixed` rồi dọn trong `finally`. Source `Hello`, `Broken`, `UseHelper` và `Helper` chỉ tồn tại dưới dạng `String`; bytecode của các ca thành công được standard file manager ghi vào thư mục tạm.

## 4. Giải thích những lựa chọn thiết kế trong demo

### 4.1. Tại sao `StringSource` dùng URI ảo?

Một đơn vị Java source trong bộ nhớ cần được mô tả bằng `JavaFileObject`. `StringSource` kế thừa `SimpleJavaFileObject`, khởi tạo với:

```java
URI.create("string:///" +
        binaryName.replace('.', '/') + Kind.SOURCE.extension)
```

Với `app.UseHelper`, URI ảo là `string:///app/UseHelper.java`. Nó phản ánh tên package và public top-level class. `getCharContent(...)` trả source từ `String`; compiler không cần tệp `app/UseHelper.java` nằm trên đĩa.

URI chỉ là **định danh** để compiler và diagnostics gắn lỗi vào source; nó không có nghĩa Java đang gửi request network tới một URL `string` hay tự lưu source xuống filesystem. Không sử dụng `Kind.CLASS` cho compilation units đầu vào chứa source.

### 4.2. Tại sao có `record Result`?

`Result` giữ hai thông tin:

- `success` được suy ra từ `Boolean.TRUE.equals(task.call())`;
- `hasError` là kết quả duyệt `DiagnosticCollector.getDiagnostics()` để tìm `Diagnostic.Kind.ERROR`.

Một ca test **thành công** cần `success == true` và không có lỗi; một ca test **thất bại theo chủ đích** cần `success == false` và có lỗi. Trong ứng dụng thực, nên giữ danh sách diagnostics đầy đủ để hiển thị source, dòng/cột và giải thích lỗi. Demo thu gọn để stdout có thể kiểm tra lặp lại qua nhiều máy.

### 4.3. Tại sao mỗi phép thử tạo file manager mới?

`StandardJavaFileManager` quản lý đầu vào, dependency và output. Demo tạo instance trong `try-with-resources` ở mỗi lần gọi `compile(...)` rồi đóng lại. Cách này giúp vòng đời tài nguyên và phạm vi một test rõ ràng; thực tế API cho phép tái sử dụng standard file manager cho nhiều compilation tasks **tuần tự** khi được quản lý đúng.

**Không chạy lại `call()` trên cùng task** để thử nguồn/cấu hình khác. Tạo task mới cho từng trường hợp, đặc biệt khi muốn thay classpath. Đồng thời không dùng chung một file manager trong nhiều luồng nếu chưa xác minh rõ thread safety của cách triển khai.

### 4.4. Ý nghĩa các compiler options

```java
List.of(
    "--release", "17",
    "-proc:none",
    "-classpath", classpath.toString(),
    "-d", output.toString())
```

- `--release 17`: yêu cầu biên dịch theo ngôn ngữ, API nền và bytecode target phù hợp Java 17 khi JDK hiện hành hỗ trợ release đó. Không phải cơ chế tự cung cấp thư viện bên thứ ba.
- `-proc:none`: vô hiệu hóa annotation processing cho fixture; tránh các annotation processors không liên quan can thiệp kết quả. Không đồng nghĩa trình biên dịch trở thành sandbox an toàn.
- `-classpath <dir>`: chỉ ra root nơi compiler tìm lớp/thư viện **ứng dụng**. `root/empty` không có `lib.Helper`; `root/deps` có `lib/Helper.class`.
- `-d <dir>`: đặt nơi output `.class` được ghi. Package tương ứng với thư mục con, ví dụ `app.UseHelper` thành `app/UseHelper.class`.

Danh sách options gồm các phần tử riêng biệt, **không nối thành một chuỗi dòng lệnh**. Với classpath có nhiều entries, sử dụng `File.pathSeparator` phù hợp nền tảng thay vì hard-code dấu `;` hay `:`.

Một classpath ứng dụng rỗng **không loại bỏ `java.base`** và API nền của Java; source chỉ dùng Java chuẩn vẫn có thể biên dịch. Mục tiêu ở đây là giới hạn nơi compiler tìm các lớp **tự viết**.

## 5. Ca thành công: không chỉ nhìn `call() == true`

Source hợp lệ là:

```java
package demo;
public class Hello {
    public static int value() {
        return 42;
    }
}
```

Demo khẳng định:

```java
check("Success", ok.success() && !ok.hasError());
check("Success class exists",
        Files.exists(root.resolve("valid/demo/Hello.class")));
```

Kiểm tra `success` xác nhận compiler task hoàn tất theo contract. Kiểm tra `!hasError` xác nhận không có `ERROR`. Kiểm tra file `.class` giúp phát hiện trường hợp output đi sai nơi được cấu hình, hoặc file manager không sinh artifact như ứng dụng mong đợi.

**Đừng chỉ kiểm tra `Files.exists(...)` nếu dùng một output directory đã có từ lần chạy trước.** Bytecode cũ có thể làm phép thử dương tính giả dù task mới không thành công. Demo dùng thư mục output mới trong cây tạm duy nhất để tránh nhiễu.

Nếu dùng custom output manager ghi bytecode vào RAM, hãy thay điều kiện `Files.exists` bằng việc kiểm tra map bytecode có entry đúng tên lớp và dữ liệu hợp lệ. Đó là một hình thức full in-memory output khác với demo này.

## 6. Ca sai cú pháp: một test pass khi compiler trả thất bại

Source được cố ý làm sai:

```java
package demo;
public class Broken {
    int x = ;
}
```

`int x = ;` không chứa một biểu thức Java hợp lệ. Khi gọi `compile(...)`, compiler không thể tạo thành công compilation unit đó. Hai assertion:

```java
check("Syntax failure", !syntax.success());
check("Syntax ERROR diagnostic", syntax.hasError());
```

**Ý nghĩa:** một compilation failure trong ca kiểm thử âm tính không khiến **bộ test** thất bại. Ngược lại, nếu compiler bất ngờ chấp nhận source này, `check` mới ném `AssertionError`.

Không nên xác nhận bằng cách so sánh một câu thông báo như “illegal start of expression” nguyên văn. Thông báo lỗi, locale và compiler version có thể khác nhau. `Diagnostic.Kind.ERROR` cùng source fixture cố định là bằng chứng ổn định hơn.

Trong ứng dụng giao diện người dùng, vẫn có thể lấy toàn bộ `getMessage(Locale)` để hiển thị. Chỉ không nên dùng câu chữ tùy biến của compiler làm nền tảng logic kiểm thử độc lập với phiên bản JDK.

## 7. Ca thiếu dependency: kiểm soát đúng classpath

Source consumer:

```java
package app;
public class UseHelper {
    public String message() {
        return lib.Helper.say();
    }
}
```

Mã trên **đúng cú pháp**, nhưng dựa vào một lớp khác: `lib.Helper`. Lúc thử ca thiếu dependency, compiler chỉ nhận `consumer` và classpath trỏ tới thư mục `root/empty`.

Kết quả mong đợi:

```java
Result missing = compile(compiler, empty, root.resolve("missing"), consumer);
check("Missing dependency fails", !missing.success());
check("Missing dependency ERROR diagnostic", missing.hasError());
```

Vì sao `-classpath` phải **tường minh**?

- Khi không được chỉ định, compiler có thể dùng classpath mặc định của môi trường hoặc thư mục làm việc.
- Nếu một bản `lib.Helper.class` tình cờ nằm ở đó, ca thiếu dependency lại biên dịch thành công và test trở nên vô nghĩa.
- Nếu compiler thấy một source `Helper.java` ở source path khác, nó có thể phân giải và biên dịch phụ trợ, cũng làm nhiễu phép thử.

Fixture tốt phải **chủ động làm dependency vắng mặt**, không chỉ hy vọng máy test chưa từng có thư viện đó. Với project dùng modules, ngoài classpath còn phải kiểm soát `--module-path`, `--module-source-path` và `requires` khi thích hợp.

Một diagnostic “cannot find symbol” có thể do nhiều nguyên nhân: chưa thêm JAR, khai báo sai package, sai tên phương thức hoặc source viết nhầm. Muốn chứng minh thiếu dependency là nguyên nhân, hãy làm phép thử đối chứng ngay sau đây.

## 8. Thêm dependency, chạy lại đúng source ban đầu

Dependency hợp lệ:

```java
package lib;
public class Helper {
    public static String say() {
        return "ok";
    }
}
```

Demo tạo `new StringSource("lib.Helper", ...)` và biên dịch vào `root/deps`. Sau đó truyền **thư mục root `deps`** vào `-classpath` khi compile lại `consumer`:

```java
Result lib = compile(compiler, empty, dependencies, helper);
check("Helper compiled", lib.success() && !lib.hasError());

Result fixed = compile(compiler, dependencies, root.resolve("fixed"), consumer);
check("After classpath fix", fixed.success() && !fixed.hasError());
check("Restored class exists",
        Files.exists(root.resolve("fixed/app/UseHelper.class")));
```

Lưu ý **không thay đổi source `consumer`** giữa hai lần compile. Sự thay đổi có chủ đích là nơi tìm dependency. File `deps/lib/Helper.class` đáp ứng tham chiếu `lib.Helper.say()`. Compiler lấy được class trên classpath nên `UseHelper` trở thành hợp lệ về kiểu.

Classpath entry cho một class trong package là **thư mục gốc chứa package hierarchy**, tức `deps`, chứ không phải đường dẫn trực tiếp đến `deps/lib/Helper.class`. Nếu dependency được đóng trong JAR, classpath entry có thể là đường dẫn tới JAR.

**Đây là cách kiểm thử quan hệ nguyên nhân–kết quả:** ca thiếu library thất bại; library được cung cấp; cùng consumer thành công. Không thay nguồn consumer chỉ để khiến ca cuối xanh.

## 9. Đọc `DiagnosticCollector` trong test thực tế

Với IDE hoặc nền tảng chấm bài, một boolean `hasError` không đủ để chỉ ra file và dòng lỗi. Có thể giữ danh sách `Diagnostic` rồi trích các trường:

```java
// Đoạn minh họa bên trong phương thức có diagnostics collector.
for (Diagnostic<? extends JavaFileObject> d
        : diagnostics.getDiagnostics()) {
    String sourceId = d.getSource() == null
            ? "<unknown>"
            : d.getSource().toUri().toString();

    System.out.printf(
            "kind=%s, source=%s, line=%d, column=%d%n",
            d.getKind(),
            sourceId,
            d.getLineNumber(),
            d.getColumnNumber());
    System.out.println(d.getMessage(Locale.ROOT));
}
```

Đây là **đoạn sử dụng bổ sung**, không phải một chương trình `main` độc lập. Cần các import `javax.tools.Diagnostic`, `javax.tools.JavaFileObject` và `java.util.Locale` như ví dụ chính.

- `getKind()` có thể là `ERROR`, `WARNING`, `MANDATORY_WARNING`, `NOTE`...
- `getSource()` có thể `null` khi diagnostic không gắn với một đơn vị nguồn cụ thể.
- `getLineNumber()` và `getColumnNumber()` có thể bằng `Diagnostic.NOPOS` nếu không có tọa độ.
- `getCode()` có thể giúp phân tích sâu cho một compiler nhất định, nhưng đừng mặc định mã đó chuẩn hóa giống nhau giữa mọi compiler.
- `getMessage(Locale)` dành cho người đọc, nên có thể khác theo môi trường hoặc phiên bản.

`DiagnosticCollector` nhận những thông báo mà compiler phát qua diagnostic listener. Một số thông báo không thể biểu diễn thành `Diagnostic` có thể đi qua luồng văn bản riêng; nếu sản phẩm cần nhật ký đầy đủ, quản lý cả writer của task.

### Có nên phân loại syntax error và missing dependency bằng `getMessage`?

Chỉ nên dùng thông báo như dữ liệu **để hiển thị hoặc hỗ trợ chẩn đoán**, không phải cách duy nhất khẳng định nguyên nhân trong bộ test. Source bị sai cú pháp được tạo rõ ràng; source thiếu dependency là source cố định mà kết quả thay đổi theo classpath. Đây là hai phép thử độc lập có ý nghĩa ngay cả khi compiler thay đổi wording lỗi.

## 10. Phân biệt lỗi source với lỗi hạ tầng

Một thiết kế bộ test đáng tin nên phân loại:

| Trạng thái | Ví dụ | Có được kết luận source sai không? |
| --- | --- | --- |
| Không có compiler | `getSystemJavaCompiler() == null` | Không. Đây là vấn đề runtime/toolchain. |
| Option không được hỗ trợ | Compiler từ chối tham số `--release` hoặc option khác | Không. Đây là cấu hình compiler. |
| File manager lỗi | Không thể tạo output, thiếu quyền I/O, dependency path không truy cập được | Chưa thể. Cần sửa môi trường và thử lại. |
| Task chạy và báo `ERROR` cho source sai | `int x = ;` | Có căn cứ cho lỗi syntax fixture. |
| Task chạy và báo `ERROR` vì không tìm thấy thư viện | `lib.Helper` vắng trên classpath đã kiểm soát | Có căn cứ cho thiếu dependency. |
| Cùng consumer thành công khi thư viện được thêm | `UseHelper` compile được với `deps` | Củng cố kết luận thiếu dependency trước đó. |

`JavaCompiler.getTask(...)` tạo task; `call()` mới thực hiện biên dịch. Không gọi lại cùng một task với kỳ vọng nó tự chạy lại theo classpath mới; tạo task mới.

Nếu compiler hoặc một file manager do ứng dụng cung cấp gặp lỗi nghiêm trọng, API có thể ném exception. Không nên catch mọi exception rồi đổi thành `Result(false, true)`, vì điều đó làm sai ý nghĩa diagnostic và che giấu sự cố thật.

## 11. Tính cô lập của phép thử biên dịch trong bộ nhớ

Các biện pháp dưới đây làm test tái lập tốt hơn:

1. **Tạo thư mục tạm mới cho mỗi bộ test.** Khi fixture khác dùng chung nơi chứa class, bytecode cũ có thể bị compiler nhận nhầm là dependency có sẵn.
2. **Dùng output riêng cho từng lần biên dịch.** Điều này giúp kiểm tra artifact mới mà không dính `.class` của lần trước.
3. **Truyền classpath tường minh.** Không dựa vào `CLASSPATH` môi trường hoặc cấu hình IDE một cách tình cờ.
4. **Kiểm soát source path.** Khi có tệp `.java` trên đĩa, compiler có thể tìm thêm source tùy cách cấu hình; với bộ test của bài này, mọi source mục tiêu nằm trong các `StringSource` rõ ràng.
5. **Dùng collector mới cho từng task.** Không gộp lỗi của ca syntax vào ca dependency vì cùng một collector còn dữ liệu.
6. **Đóng file manager.** `try-with-resources` giữ tài nguyên rõ ràng; về lâu dài có thể tối ưu bằng tái sử dụng manager cho các tác vụ tuần tự nếu phù hợp.
7. **Giữ nguyên source ở phép đối chứng.** Nếu thay nội dung cùng lúc với classpath thì không còn chứng minh dependency là nguyên nhân.
8. **Không parse message theo một ngôn ngữ duy nhất.** Hãy dựa vào `Kind`, source, vị trí và fixture.
9. **Cấu hình release rõ ràng.** Ví dụ chọn `--release 17`; runtime JDK dùng để chạy compiler phải hỗ trợ target đó.
10. **Dọn artifact trong `finally`.** Tránh bồi thêm file trên máy chạy CI sau nhiều lần test.

Với unit test đa luồng, không dùng chung một đường output hoặc classpath động đang bị luồng khác ghi. Hạn chế việc biên dịch nhiều request không kiểm soát tài nguyên, đặc biệt với mã nguồn do người dùng cung cấp.

## 12. Source trong RAM không đồng nghĩa output cũng trong RAM

Trong chương trình chạy đầy đủ:

- Các source Java là `String`.
- `StringSource` tạo `JavaFileObject.Kind.SOURCE` với URI ảo.
- `JavaCompiler` nhận các units này và thực hiện task.
- `StandardJavaFileManager` ghi `.class` ra thư mục được chỉ định qua `-d`.

Nếu muốn cả bytecode `.class` ở RAM:

1. Dùng một output `JavaFileObject` loại `CLASS` chứa buffer ghi bytes.
2. Dùng `ForwardingJavaFileManager` hoặc file manager tương đương để override `getJavaFileForOutput(...)`.
3. Thu thập bytes theo tên lớp thay vì kiểm tra `Files.exists(...)`.
4. Khi kiểm thử thiếu dependency, cung cấp bytecode đó cho file manager/classpath theo cách có kiểm soát.
5. Nếu có yêu cầu chạy class đã tạo, cần bước class loading/execution riêng. `JavaCompiler` không tự thực thi `main` của class được biên dịch.

Test logic success/failure/dependency vẫn giữ nguyên. Chỉ cách **kiểm chứng và cung cấp output** thay đổi.

## 13. Những tình huống mở rộng nên kiểm tra trong sản phẩm

| Nhóm | Gợi ý phép thử |
| --- | --- |
| Nhiều source trong cùng một task | `List.of(apiSource, implSource)` để compiler phân giải type giữa các compilation units. |
| Dependency đóng trong JAR | Đưa JAR vào classpath và xác nhận consumer compile thành công. |
| Dependency đúng tên nhưng sai phiên bản | Lớp tồn tại nhưng thiếu method/signature: đó là lỗi khác hoàn toàn với thiếu class. |
| Sai package hoặc public class name | Xác nhận URI nguồn phải tương thích tên lớp; không nhầm lỗi tên file với lỗi dependency. |
| Named modules | Dùng `--module-path`, `requires` và `module-info.java` nếu project thực sự sử dụng JPMS. |
| Compiler không khả dụng | Tách lỗi runtime, không quy thành lỗi bài học viên. |
| Tạo nhiều diagnostics | Kiểm tra ứng dụng lưu được kind/source/line/column cho từng lỗi thay vì một boolean tổng. |
| Nguồn Unicode | Đảm bảo quá trình bytes → String có charset đúng trước khi tạo `StringSource`. |
| Build đồng thời | Không dùng chung output root hoặc file manager thiếu kiểm soát; kiểm tra cleanup. |
| Annotation processing | Nếu không cần thì `-proc:none`; nếu cần thì chọn processor và đường dẫn đáng tin. |

Không nhất thiết dùng JUnit để hiểu bài: helper `check` là một phép kiểm thử tự động tối thiểu. Khi chuyển vào một dự án có framework test, thay nó bằng assertion framework tương ứng và giữ nguyên cách thiết lập fixture, classpath, diagnostics cùng output.

## 14. Các sai lầm thường gặp

**Sai lầm 1 — Chỉ nhìn `call() == false`.** Lỗi có thể do syntax, thiếu class, compiler option, hoặc file manager. Kiểm tra diagnostics và môi trường rõ ràng.

**Sai lầm 2 — Không tạo classpath rỗng thật sự.** Compiler có thể tình cờ thấy dependency từ máy chạy test và trả thành công. Truyền `-classpath` trỏ một thư mục rỗng riêng.

**Sai lầm 3 — Dùng lại output cũ.** `Files.exists(...class)` có thể đúng vì artifact trước đó. Tạo output theo request và dọn sau test.

**Sai lầm 4 — Thay cả source lẫn dependency.** Ca sửa classpath không còn chứng minh nguyên nhân. Dùng lại chính `consumer` đã thất bại.

**Sai lầm 5 — Hard-code câu lỗi.** Message có thể khác giữa các JDK/locale. Dùng `Diagnostic.Kind.ERROR` và hoàn cảnh fixture, chỉ dùng message cho người đọc.

**Sai lầm 6 — Dùng Java `assert` mà quên `-ea`.** Assertions trong Java có thể không được bật. Dùng framework assertion hoặc tự ném `AssertionError` như `check(...)`.

**Sai lầm 7 — Nghĩ mã nguồn ở RAM nghĩa là không hề ghi đĩa.** `StringSource` chỉ làm source ở RAM; standard file manager vẫn có thể ghi bytecode theo `-d`.

**Sai lầm 8 — Nghĩ `-proc:none` hoặc `--release` là sandbox.** Các lựa chọn này phục vụ điều khiển compilation và phiên bản; không thay thế cơ chế cô lập mã không đáng tin cậy.

## 15. An toàn và giới hạn khi kiểm thử mã không đáng tin cậy

Một hệ thống nhận Java source bên ngoài phải phân biệt **biên dịch** và **chạy bytecode**. Dù `CompilationTask.call()` không tự gọi `main` của output, quá trình compile vẫn tiêu thụ CPU, bộ nhớ và I/O, có thể gặp source rất lớn hoặc dependency graph khó kiểm soát.

- Đặt giới hạn kích thước source, số lượng compilation units, thời gian, bộ nhớ, tài nguyên đĩa và mức concurrency.
- Không cho người dùng tùy ý thiết lập processor path, classpath hoặc output directory của JVM có quyền cao.
- Trong fixture này dùng `-proc:none` để loại annotation processing; nếu chủ động kích hoạt processors/plugins, cần hiểu chúng có thể chạy mã trong giai đoạn compile.
- Cân nhắc thực hiện compile trong tiến trình/container được cô lập khi input không đáng tin và có nguy cơ ảnh hưởng dịch vụ.
- Không trực tiếp chạy hoặc nạp class vừa sinh vào JVM phục vụ request người dùng. Chạy code là một bài toán riêng với yêu cầu bảo vệ nghiêm ngặt.
- Đừng coi việc compiler trả `true` là chứng minh đoạn mã vừa biên dịch an toàn hay không có lỗi runtime.

## 16. Câu hỏi tự kiểm tra

**1. Source `demo.Hello` hợp lệ; chỉ cần kiểm tra file `Hello.class` là đủ để test pass?**

Không. File có thể còn từ lượt trước. Hãy kiểm tra đồng thời `call() == true`, diagnostics phù hợp và artifact trong output đã được cô lập.

**2. Compiler từ chối source `int x = ;`. Đây là một test fail?**

Không. Nếu bạn chủ động kiểm tra compiler phải từ chối mã sai cú pháp, `call() == false` cùng `ERROR` chính là kết quả kiểm thử **thành công**.

**3. Làm thế nào chứng minh một source thiếu dependency thay vì sai cú pháp?**

Đưa một source hợp lệ về cú pháp nhưng tham chiếu lớp đã biết, compile với classpath không chứa lớp đó, rồi compile lại **cùng source** sau khi thêm đúng dependency; kỳ vọng thất bại rồi thành công.

**4. Tại sao phải truyền root `deps` vào classpath, không phải file `deps/lib/Helper.class`?**

Classpath chứa các thư mục root của package hierarchy hoặc các JAR. Compiler tự tra `lib/Helper.class` dưới một root.

**5. Vì sao `Diagnostic.Kind.ERROR` thường phù hợp hơn việc so sánh message lỗi nguyên văn?**

`Kind` là một phần của API chuẩn; lời văn message có thể thay đổi theo compiler/JDK/locale. Còn nguyên nhân kiểm thử phải được củng cố bằng source fixture và thay đổi classpath có kiểm soát.

**6. `--release 17` có tự cung cấp `lib.Helper` không?**

Không. Nó giới hạn target ngôn ngữ, bytecode và API nền Java. Dependency ứng dụng vẫn phải được cung cấp bằng compilation units hoặc classpath/module path phù hợp.

**7. Nếu `getSystemJavaCompiler() == null`, có nên trả lỗi “source bị sai” không?**

Không. Đây là lỗi môi trường/khả năng compiler. Cần xử lý và báo cấu hình JDK hoặc runtime image thiếu `jdk.compiler`.

## Tài liệu chính thức còn hiệu lực

- [Java SE 26 — `JavaCompiler`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/JavaCompiler.html): gọi `getTask`, `call`, diagnostics và standard file manager.
- [Java SE 26 — `SimpleJavaFileObject`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/SimpleJavaFileObject.html): nguồn mã Java dưới dạng String và URI ảo.
- [Java SE 26 — `DiagnosticCollector`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/DiagnosticCollector.html): thu thập thông báo có cấu trúc.
- [Java SE 26 — `StandardJavaFileManager`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html): quản lý dependency và output.
- [Java SE 26 — `javac`](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html): `--class-path`, `-d`, `--release`, `-proc:none` và cách tìm các lớp phụ thuộc.

**Ghi nhớ:** Kiểm thử biên dịch trong bộ nhớ phải kiểm soát **source, classpath, diagnostics và output**. Ba ca cốt lõi là **thành công**, **thất bại vì source sai** và **thất bại vì thiếu dependency**; để khẳng định ca cuối, hãy thêm dependency rồi biên dịch lại **chính source ban đầu**. Test âm tính vẫn pass khi compiler từ chối input theo đúng kỳ vọng.
