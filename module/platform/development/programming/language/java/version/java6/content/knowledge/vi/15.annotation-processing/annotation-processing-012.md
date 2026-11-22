# Kiểm thử annotation processor bằng Java Compiler API

## 1. Vì sao phải thử processor qua một lần biên dịch thật?

Annotation processor là mã Java chạy **trong tác vụ biên dịch**, thường để xác thực quy tắc annotation hoặc tạo source, class và resource mới. Kiểm thử một processor chỉ bằng cách gọi phương thức `process(...)` trực tiếp **không mô phỏng đầy đủ** môi trường mà `javac` cung cấp: `ProcessingEnvironment`, `RoundEnvironment`, `Element`, `TypeMirror`, `Filer` và `Messager` có các hợp đồng riêng.

**Java Compiler API** trong module `java.compiler` cho phép một chương trình Java tạo một tác vụ biên dịch ngay trong JVM kiểm thử. Ta có thể truyền source fixture, bật đúng annotation processor, thu diagnostics và kiểm tra những artifact do processor tạo ra. Đây là cách kiểm thử tích hợp ở mức **compiler invocation**, không phải cách gọi reflection lên lớp annotation tại runtime.

Một bài test processor đáng tin cần kiểm tra đủ ba lớp kết quả:

1. **Kết quả biên dịch:** `JavaCompiler.CompilationTask.call()` trả về `true` hay `false`?
2. **Chẩn đoán:** những `Diagnostic` nào được phát ra? Có `Diagnostic.Kind.ERROR` khi cấu hình annotation không hợp lệ không?
3. **Đầu ra của processor:** file `.java` được sinh đúng tên/nội dung không? Source sinh ra có tiếp tục biên dịch thành `.class` không?

Ngoài hai kịch bản thành công và thất bại, nên có một **đối chứng tắt processor** bằng `-proc:none`. Một lớp có annotation hợp lệ có thể compile thành công **ngay cả khi processor không chạy**. Do đó chỉ khẳng định `call() == true` chưa chứng minh rằng annotation processor được thực thi.

### Kết quả mong đợi trong bài thực hành

| Kịch bản | Đầu vào | Processor | `call()` | Diagnostics | Generated file |
| --- | --- | --- | --- | --- | --- |
| Annotation hợp lệ | `@RequiredId("alpha")` | Bật tường minh | `true` | Không có ERROR | Có `ValidCaseIdInfo.java` và `ValidCaseIdInfo.class` |
| Annotation sai | `@RequiredId("")` | Bật tường minh | `false` | Có ERROR từ `Messager` | Không sinh `InvalidCaseIdInfo.java` |
| Đối chứng không chạy processor | `@RequiredId("alpha")` | `-proc:none` | `true` | Không có ERROR | Không sinh `DisabledCaseIdInfo.java` |

Kịch bản thứ ba là **negative control** để phát hiện bài test hoặc cấu hình build đang vô tình dựa vào annotation processing mặc định.

## 2. Các API hiện hành cần hiểu

| API | Vai trò trong test |
| --- | --- |
| `ToolProvider.getSystemJavaCompiler()` | Lấy compiler triển khai trong môi trường JDK hiện tại; có thể trả `null` nếu runtime image không có compiler |
| `JavaCompiler` | Tạo compilation task |
| `JavaCompiler.CompilationTask` | Đại diện cho một lần compile; gọi `call()` để thực thi; một task chỉ dùng một lần |
| `StandardJavaFileManager` | Chuyển `Path` thành `JavaFileObject` và quản lý nguồn/đích của compiler |
| `JavaFileObject` | Đối tượng mô tả đơn vị source để compiler xử lý |
| `DiagnosticCollector<JavaFileObject>` | Thu chẩn đoán do compiler và processor phát |
| `Diagnostic.Kind.ERROR` | Nhận diện lỗi build có ý nghĩa |
| `AbstractProcessor` | Lớp nền cho processor được thử |
| `ProcessingEnvironment.getFiler()` | Tạo generated source |
| `ProcessingEnvironment.getMessager()` | Báo lỗi annotation gắn vào `Element` |
| `RoundEnvironment` | Liệt kê phần tử có annotation trong một processing round |

Luồng xử lý:

~~~text
Java fixture source (.java)
     |
     v
JavaCompiler + StandardJavaFileManager + compiler options
     |
     +--> processor path chứa lớp processor đã biên dịch
     |
     v
CompilationTask.call()
     |
     +--> javac gọi processor qua RoundEnvironment
     |       |
     |       +--> Messager phát ERROR nếu input sai
     |       +--> Filer tạo generated .java nếu input hợp lệ
     |
     +--> compiler xử lý generated source ở vòng kế tiếp
     |
     v
Kết quả Boolean + DiagnosticCollector + output directories
     |
     v
Assertions: compile status / errors / generated .java / generated .class / content
~~~

**Tách hai đường classpath:** `-classpath` là nơi compiler tìm các type mà source fixture dùng; `-processorpath` là nơi compiler tìm **code của processor** để chạy. Ở bài lab cả hai cùng trỏ tới một thư mục đã build để dễ thực hành, nhưng trong dự án thật chúng thường là hai dependency sets khác nhau.

## 3. Nguyên tắc bảo đảm test không tự báo đạt sai

Trước khi viết mã, chọn các điều kiện sau:

- Dùng **tác vụ compile thực sự** qua `JavaCompiler.getTask(...)` và `call()`, không chỉ khởi tạo `Processor` rồi gọi `process` bằng đối tượng giả.
- Mỗi test có thư mục source, classes và generated source **riêng**, tránh file sinh từ test trước ảnh hưởng test sau.
- **Bật tường minh processor** bằng `-processor demo.apt.RequiredIdProcessor` và cung cấp `-processorpath`. Kể từ JDK 23, `javac` không còn tự động kích hoạt processing chỉ vì có processor trên classpath nếu không có cấu hình annotation processing tường minh.
- Trong test đối chứng, dùng `-proc:none`. Nếu compiler vẫn tạo file tương ứng thì fixture bị lẫn artifact hoặc có code tạo file ngoài dự kiến.
- Mọi `StandardJavaFileManager` phải đóng sau compile để giải phóng tài nguyên, nhất là trên Windows.
- Khẳng định lỗi dựa trên **`Diagnostic.Kind.ERROR`**, không so sánh nguyên văn thông báo lỗi theo locale và phiên bản JDK.
- Kiểm tra **cả source và class file do processor sinh**. Chỉ có source chưa chứng minh generated source đã biên dịch được.
- Kiểm tra **nội dung có ý nghĩa**, ví dụ hằng `ID_LENGTH = 5` của `"alpha"`. Không chỉ kiểm tra một file rỗng tồn tại.
- Khi `call()` trả `false`, không nạp/thực thi artifact đầu ra như thể build thành công.

Ví dụ chọn `@Retention(SOURCE)`, vì processor xử lý annotation ở compile time; runtime reflection **không cần** đọc annotation ấy.

## 4. Cấu trúc dự án chạy được với JDK 17+

Tạo cấu trúc:

~~~text
processor-test/
└── src/
    ├── demo/
    │   └── apt/
    │       ├── RequiredId.java
    │       └── RequiredIdProcessor.java
    └── ProcessorTestHarness.java
~~~

Bài này không cần JUnit, Maven, Gradle hoặc thư viện bên ngoài để chạy. Kiểm thử dùng **Java standard library** và các assertion có chủ đích ném `AssertionError` khi kết quả không đúng.

### 4.1. Annotation của source fixture

Tệp `src/demo/apt/RequiredId.java`:

~~~java
package demo.apt;

import java.lang.annotation.*;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
public @interface RequiredId {
    String value();
}
~~~

`@RequiredId("alpha")` là input hợp lệ; `@RequiredId("")` là input không hợp lệ theo quy tắc nghiệp vụ **không được để mã định danh rỗng**.

Annotation retention `SOURCE` là có chủ đích: processor đọc annotation bằng `Element.getAnnotation(...)` **khi biên dịch**; annotation không cần xuất hiện trong bytecode ứng dụng. Việc dùng `SOURCE` không làm processor “không nhìn thấy” annotation.

### 4.2. Processor có cả nhánh thành công và nhánh lỗi

Tệp `src/demo/apt/RequiredIdProcessor.java`:

~~~java
package demo.apt;

import java.io.IOException;
import java.io.Writer;
import java.util.Set;
import javax.annotation.processing.*;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.*;
import javax.tools.Diagnostic;

@SupportedAnnotationTypes("demo.apt.RequiredId")
public final class RequiredIdProcessor extends AbstractProcessor {
    @Override
    public SourceVersion getSupportedSourceVersion() {
        return SourceVersion.latestSupported();
    }

    @Override
    public boolean process(Set<? extends TypeElement> annotations,
                           RoundEnvironment round) {
        if (round.processingOver()) return true;

        for (Element element : round.getElementsAnnotatedWith(RequiredId.class)) {
            if (!(element instanceof TypeElement type)) continue;
            String id = type.getAnnotation(RequiredId.class).value();
            if (id.isBlank()) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR, "RequiredId must not be blank", element);
                continue;
            }

            String pkg = processingEnv.getElementUtils()
                    .getPackageOf(type).getQualifiedName().toString();
            String simpleName = type.getSimpleName() + "IdInfo";
            try (Writer writer = processingEnv.getFiler()
                    .createSourceFile(pkg + "." + simpleName, type).openWriter()) {
                writer.write("package " + pkg + ";\n"
                        + "public final class " + simpleName + " {\n"
                        + "  private " + simpleName + "() {}\n"
                        + "  public static final int ID_LENGTH = " + id.length() + ";\n"
                        + "}\n");
            } catch (IOException e) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR, "Generation failed: " + e.getMessage(),
                        element);
            }
        }
        return true;
    }
}
~~~

**Đọc processor theo thứ tự:**

1. `@SupportedAnnotationTypes("demo.apt.RequiredId")` khai báo annotation type được hỗ trợ, không tự kích hoạt việc chạy processor.
2. `getSupportedSourceVersion()` công bố phiên bản source hỗ trợ. `SourceVersion.latestSupported()` là API chuẩn; lệnh build dưới đây kiểm tra kết quả theo `--release 17`.
3. `round.processingOver()` giúp processor không cố sinh file trong final round.
4. `round.getElementsAnnotatedWith(RequiredId.class)` lấy các `Element` annotate `@RequiredId` thuộc vòng xử lý hiện tại.
5. `element instanceof TypeElement` bảo đảm đang xét khai báo kiểu, đúng với `@Target(TYPE)`.
6. `type.getAnnotation(RequiredId.class)` trên **compiler model `Element`** đọc giá trị annotation; không phải `Class.getAnnotation` của runtime reflection.
7. `id.isBlank()` kiểm tra rỗng/khoảng trắng. Nếu sai, `Messager.printMessage(Diagnostic.Kind.ERROR, ..., element)` phát diagnostic có vị trí nguồn và **không sinh file** cho type ấy.
8. Nếu đúng, `Filer.createSourceFile(...)` tạo type `<TênClass>IdInfo` cùng package với type input. Writer được đóng trong `try-with-resources` để generated source được xét ở vòng sau.
9. Source sinh ra khai báo hằng `ID_LENGTH` bằng độ dài `id`. Với `"alpha"`, số đó là `5`.
10. `return true` chỉ có nghĩa processor **claim** annotation types mà nó hỗ trợ; nó **không** trực tiếp có nghĩa compile thành công.

Trong code generation production, khi muốn đưa trực tiếp chuỗi chưa tin cậy vào Java source cần escape chuỗi đúng cách và xử lý tên type/package phức tạp. Ví dụ chỉ sinh một **số nguyên** từ độ dài annotation để tránh làm phân tâm khỏi mục tiêu test compiler.

## 5. Test harness: tạo fixture, gọi JavaCompiler và assert kết quả

Tệp `src/ProcessorTestHarness.java`:

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Stream;
import javax.tools.*;

public final class ProcessorTestHarness {
    private record Result(boolean success, long errors, Path source, Path generated,
                          Path generatedClass) {}

    private static Result compile(Path root, String name, String annotationValue,
                                  boolean enableProcessor, Path processorClasses)
            throws Exception {
        Path source = root.resolve("src/demo/app/" + name + ".java");
        Path classes = root.resolve("classes");
        Path generated = root.resolve("generated");
        Files.createDirectories(source.getParent());
        Files.createDirectories(classes);
        Files.createDirectories(generated);

        String code = "package demo.app;\n"
                + "import demo.apt.RequiredId;\n"
                + "@RequiredId(\"" + annotationValue + "\")\n"
                + "public final class " + name + " {}\n";
        Files.writeString(source, code, StandardCharsets.UTF_8);

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) throw new IllegalStateException("JDK compiler missing");
        DiagnosticCollector<JavaFileObject> diagnostics = new DiagnosticCollector<>();
        boolean success;
        try (StandardJavaFileManager manager = compiler.getStandardFileManager(
                diagnostics, null, StandardCharsets.UTF_8)) {
            List<String> options = new ArrayList<>(List.of(
                    "--release", "17",
                    "-encoding", "UTF-8",
                    "-classpath", processorClasses.toString(),
                    "-d", classes.toString(),
                    "-s", generated.toString()));

            if (enableProcessor) {
                options.addAll(List.of(
                        "-processorpath", processorClasses.toString(),
                        "-processor", "demo.apt.RequiredIdProcessor"));
            } else {
                options.add("-proc:none");
            }

            var compilationUnits =
                    manager.getJavaFileObjectsFromPaths(List.of(source));
            success = Boolean.TRUE.equals(
                    compiler.getTask(null, manager, diagnostics,
                            options, null, compilationUnits).call());
        }

        long errors = diagnostics.getDiagnostics().stream()
                .filter(d -> d.getKind() == Diagnostic.Kind.ERROR)
                .count();
        String generatedName = name + "IdInfo";
        return new Result(success, errors, source,
                generated.resolve("demo/app/" + generatedName + ".java"),
                classes.resolve("demo/app/" + generatedName + ".class"));
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) throw new IllegalArgumentException("processor classes path");
        Path processorClasses = Path.of(args[0]).toAbsolutePath();
        Path root = Files.createTempDirectory("processor-tests-");
        try {
            Result valid = compile(root.resolve("valid"),
                    "ValidCase", "alpha", true, processorClasses);
            require(valid.success && valid.errors == 0, "valid compile failed");
            require(Files.exists(valid.generated), "generated .java missing");
            require(Files.exists(valid.generatedClass), "generated .class missing");
            require(Files.readString(valid.generated).contains("ID_LENGTH = 5"),
                    "unexpected generated content");
            System.out.println("valid=PASS");
            System.out.println("generated-source=true");
            System.out.println("generated-class=true");

            Result invalid = compile(root.resolve("invalid"),
                    "InvalidCase", "", true, processorClasses);
            require(!invalid.success && invalid.errors > 0, "invalid case passed");
            require(!Files.exists(invalid.generated), "invalid generated a file");
            System.out.println("invalid=FAIL_EXPECTED");
            System.out.println("invalid-diagnostic=true");
            System.out.println("invalid-generated=false");

            Result disabled = compile(root.resolve("disabled"),
                    "DisabledCase", "alpha", false, processorClasses);
            require(disabled.success && disabled.errors == 0, "disabled compile failed");
            require(!Files.exists(disabled.generated), "processor ran when disabled");
            System.out.println("proc-none=PASS");
            System.out.println("proc-none-generated=false");
        } finally {
            try (Stream<Path> paths = Files.walk(root)) {
                for (Path p : paths.sorted(Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(p);
                }
            }
        }
    }
}
~~~

**Đây là một chương trình Java độc lập, chạy được**, không phải pseudocode. Các record, `var` và `String.isBlank` đều được hỗ trợ trong Java 17. Nó cần một JDK có compiler triển khai (thông thường `jdk.compiler`); một runtime image tối giản có thể không có `ToolProvider.getSystemJavaCompiler()`.

### 5.1. Vì sao harness tạo ba thư mục riêng?

- `valid`: có `src/demo/app/ValidCase.java`, `classes/` và `generated/` riêng.
- `invalid`: có `InvalidCase.java` và hai output directories riêng; file từ test hợp lệ **không thể** khiến test lỗi đạt sai.
- `disabled`: có `DisabledCase.java` và output riêng, dùng để chứng minh tác động của `-proc:none`.

Các đường dẫn do chương trình tạo dưới một thư mục tạm từ `Files.createTempDirectory(...)` và được xóa trong `finally`. Dùng fixture mới mỗi lần chạy giúp tránh generated source/class file cũ từ lần biên dịch trước.

### 5.2. Hàm compile không “chạy Java class vừa biên dịch”

`compile(...)` chỉ tạo source, cấu hình compiler, gọi `CompilationTask.call()` rồi trả kết quả kiểm thử. Processor có thể thực thi code của **chính processor** trong môi trường compiler, nhưng chương trình không khởi chạy `ValidCase` hay `InvalidCase`. Điều đang thử là **pipeline compile + annotation processing**.

Đối với một test khác cần xác nhận runtime behavior của generated class, có thể tạo `ClassLoader` độc lập và nạp output `.class` sau khi compile thành công. Việc nạp/chạy là **giai đoạn bổ sung**, không nên nhập nhằng với kết quả `call()`.

### 5.3. Đọc các compiler options

| Option trong `getTask(...)` | Tác dụng |
| --- | --- |
| `--release 17` | Biên dịch theo API, source và bytecode Java 17, dù compiler đang chạy trên JDK mới |
| `-encoding UTF-8` | Đọc file source với UTF-8 |
| `-classpath <processorClasses>` | Cho compiler tìm thấy type `demo.apt.RequiredId` được source dùng |
| `-processorpath <processorClasses>` | Cho compiler tìm thấy implementation `RequiredIdProcessor` để chạy |
| `-processor demo.apt.RequiredIdProcessor` | Chỉ định **đúng** processor cần chạy, không phụ thuộc auto-discovery |
| `-d <classes>` | Ghi class files của source ban đầu và source được sinh |
| `-s <generated>` | Ghi `.java` do `Filer.createSourceFile` sinh |
| `-proc:none` | Biên dịch mà **không thực hiện** annotation processing |

Trong harness, `-processorpath` và `-processor` được thêm **chỉ với hai bài test bật processing**. Với đối chứng tắt processing, nguồn vẫn compile nhờ annotation type trên `-classpath`, nhưng processor không chạy và không có generated source.

**Chú ý:** compiler API nhận options dưới dạng **`List<String>` tách từng token**, không phải một chuỗi command line đã nối chung. Ví dụ đúng là `List.of("-d", output.toString())`, không phải `List.of("-d " + output)`.

### 5.4. Kiểm thử diagnostics

`DiagnosticCollector.getDiagnostics()` trả danh sách chẩn đoán từ compiler trong tác vụ này. Harness lọc `Diagnostic.Kind.ERROR`:

~~~java
long errors = diagnostics.getDiagnostics().stream()
        .filter(d -> d.getKind() == Diagnostic.Kind.ERROR)
        .count();
~~~

Đây là **đoạn trích** của chương trình ở mục 5. Trong negative test, processor thấy `@RequiredId("")` và phát ERROR bằng `Messager`, nên bài test đòi `!invalid.success && invalid.errors > 0`. Việc `invalid=FAIL_EXPECTED` **không phải lỗi của harness**; đó là dấu hiệu harness đã chứng minh compiler từ chối input sai theo thiết kế.

Không phụ thuộc nguyên văn `"RequiredId must not be blank"` trong assertion tích hợp nếu không thật sự cần contract về nội dung thông báo. Thông báo, cách trình bày source location, locale và các diagnostic phụ có thể thay đổi; hợp đồng bền vững hơn là **kind, source, line, và điều kiện business được mô tả**.

## 6. Biên dịch và chạy bài lab

Di chuyển terminal vào thư mục `processor-test` chứa `src`.

Trên Linux/macOS (Bash), tạo output cho annotation và processor:

~~~bash
mkdir -p classes
~~~

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force classes | Out-Null
~~~

**Bước 1 — build annotation và processor trước:**

~~~bash
javac -encoding UTF-8 --release 17 -proc:none -d classes src/demo/apt/RequiredId.java src/demo/apt/RequiredIdProcessor.java
~~~

`-proc:none` ở đây có chủ đích: đang biên dịch **chính processor** và không muốn processor vô tình kích hoạt ngay trong bước bootstrap.

**Bước 2 — biên dịch harness:**

~~~bash
javac -encoding UTF-8 --release 17 -proc:none -classpath classes -d classes src/ProcessorTestHarness.java
~~~

**Bước 3 — chạy test trong JVM:**

~~~bash
java -classpath classes ProcessorTestHarness classes
~~~

Toàn bộ thư mục tạm của ba case được harness tạo và xóa tự động. Không cần nhập tên `ValidCase.java` hoặc `InvalidCase.java` khi chạy lệnh: harness tự ghi file source fixture bằng `Files.writeString(...)`.

### Stdout đã kiểm chứng

~~~text
valid=PASS
generated-source=true
generated-class=true
invalid=FAIL_EXPECTED
invalid-diagnostic=true
invalid-generated=false
proc-none=PASS
proc-none-generated=false
~~~

Đã kiểm chứng lệnh và stdout trên **OpenJDK 24**, biên dịch với `--release 17`. Khi một assertion thất bại, `require(...)` ném `AssertionError`, chương trình kết thúc không thành công thay vì chỉ in kết quả có vẻ hợp lệ.

Lưu ý: `invalid=FAIL_EXPECTED` nghĩa là source lỗi **bị compiler từ chối đúng như kỳ vọng**. Toàn bộ harness chỉ đạt khi cả ba case qua assertion.

## 7. Hiểu chính xác ba kịch bản test

### 7.1. Positive test: processor có chạy và sinh Java hợp lệ

Với source:

~~~java
package demo.app;

import demo.apt.RequiredId;

@RequiredId("alpha")
public final class ValidCase {}
~~~

Processor tạo `demo.app.ValidCaseIdInfo` với một hằng:

~~~java
package demo.app;

public final class ValidCaseIdInfo {
  private ValidCaseIdInfo() {}
  public static final int ID_LENGTH = 5;
}
~~~

Đó là source **được sinh**, không cần tạo file thủ công. Test kiểm tra:

- `call() == true` và không có ERROR;
- `generated/demo/app/ValidCaseIdInfo.java` tồn tại;
- `classes/demo/app/ValidCaseIdInfo.class` tồn tại;
- Nội dung source có `ID_LENGTH = 5`.

Điều kiện file `.class` là bằng chứng compilation đã xử lý generated source ở round tiếp theo và tạo bytecode; không chỉ chạy processor rồi dừng.

### 7.2. Negative test: processor báo lỗi nghiệp vụ

Với source:

~~~java
package demo.app;

import demo.apt.RequiredId;

@RequiredId("")
public final class InvalidCase {}
~~~

Processor đọc annotation `SOURCE` từ compiler model, thấy chuỗi trống bằng `id.isBlank()` và phát `Diagnostic.Kind.ERROR` qua `Messager`. Nó không tạo `InvalidCaseIdInfo.java`.

Assertion yêu cầu **cả ba**:

- `call() == false`: full compilation không thành công.
- `errors > 0`: có diagnostic mức ERROR.
- `!Files.exists(generatedPath)`: nhánh sai không sinh file.

**Không suy ra rằng mọi compilation lỗi đều không tạo ra bất kỳ artifact nào.** Compiler có thể đã ghi một số file trước khi phát lỗi. Ta chỉ khẳng định không có **file cụ thể** mà processor bị cấm sinh trong nhánh invalid; và chỉ nạp/chạy artifact khi toàn bộ tác vụ được xác nhận thành công.

### 7.3. Negative control: annotation có nhưng processor tắt

Với source:

~~~java
package demo.app;

import demo.apt.RequiredId;

@RequiredId("alpha")
public final class DisabledCase {}
~~~

Source hoàn toàn hợp lệ theo cú pháp Java và annotation type vẫn nằm trên compile classpath. Nhưng compiler options có `-proc:none`. Kết quả **biên dịch thành công** mà **không có `DisabledCaseIdInfo.java`**.

Đây là lý do một test chỉ viết “processor compile test passed” dựa trên `call() == true` rất dễ báo đạt sai. Cần kiểm tra artifact hoặc diagnostic mà processor **thật sự chịu trách nhiệm** tạo ra.

## 8. Những điểm tinh tế của Java Compiler API

### 8.1. getTask(...) tạo task; call() mới thực hiện

`JavaCompiler.getTask(out, fileManager, diagnosticListener, options, classes, compilationUnits)` nhận một số thành phần tùy chọn. Trong lab:

- `out = null`: compiler dùng output writer mặc định cho thông tin bổ sung;
- `fileManager = manager`: quản lý các `JavaFileObject` và output locations;
- `diagnosticListener = diagnostics`: thu warnings/errors;
- `options = List<String>`: điều khiển compiler và annotation processing;
- `classes = null`: không yêu cầu xử lý thêm tên class nào;
- `compilationUnits`: source Java cần biên dịch.

`getTask(...)` trả một `CompilationTask`. Gọi `task.call()` chạy compile; một task **không thể gọi `call()` lần hai** để “thử lại”. Muốn thử kịch bản khác, tạo task mới, tốt nhất có fixture, diagnostics và file manager riêng.

`Boolean.TRUE.equals(task.call())` làm logic kiểm tra rõ ràng, tránh xử lý `Boolean` như primitive không chủ ý. Trong harness, task được tạo và gọi trong phạm vi `try-with-resources` của file manager.

### 8.2. File manager phải được đóng

`StandardJavaFileManager` triển khai `Closeable`. Với biên dịch lặp trong cùng JVM, tài nguyên/handle JAR và các file có thể được cache. Nên dùng:

~~~java
try (StandardJavaFileManager manager =
        compiler.getStandardFileManager(diagnostics, null, StandardCharsets.UTF_8)) {
    // Tạo JavaFileObject, lấy task và gọi task.call() ở đây.
}
~~~

Đây là **đoạn minh họa**, không phải chương trình độc lập; `compiler` và `diagnostics` là các biến đã tạo. Việc đóng file manager trước khi kiểm tra output và dọn temp directory giúp tránh các vấn đề khóa file trên Windows.

Đối với một build pipeline muốn tối ưu nhiều compilation liên tiếp, API cho phép **tái sử dụng file manager** có chủ đích; khi đó quản lý caching, isolation, dependency và đóng tài nguyên ở ranh giới vòng đời phù hợp. Bài test có ít case ưu tiên isolation hơn tối ưu tốc độ.

### 8.3. Diagnostic có source và vị trí nhưng đừng giả định luôn có đủ

`Diagnostic<? extends JavaFileObject>` có `getKind()`, `getCode()`, `getMessage(Locale)`, `getSource()`, `getLineNumber()`, `getColumnNumber()`. Một số diagnostic có thể không gắn được source hoặc vị trí cụ thể (ví dụ lỗi option/build), nên `getSource()` có thể `null` và line/column có thể là `Diagnostic.NOPOS`.

Một test xác nhận vị trí của lỗi từ `@RequiredId("")` có thể kiểm tra khi nguồn/line thực sự có mặt, nhưng không nên viết một utility tổng quát giả định mọi diagnostic đều có line > 0.

### 8.4. Kiểm tra generated source và generated class là hai điều kiện khác nhau

Processor dùng `Filer.createSourceFile` để viết `.java`. Khi thực hiện full compilation, javac có thể tiếp tục biên dịch generated source thành `.class`. Tùy chọn `-s` và `-d` điều khiển **hai nơi đầu ra khác nhau**.

Nếu thay cấu hình bằng `-proc:only`, compiler chỉ xử lý annotation mà **không thực hiện full compilation tiếp theo**. Khi ấy generated source có thể tồn tại nhưng không thể dùng sự có mặt của generated `.class` làm assertion chung. Bài lab cố ý chọn **full compile với `-processor`**, không dùng `-proc:only`.

### 8.5. Thêm processor trực tiếp qua API thay vì processor path

`JavaCompiler.CompilationTask` có phương thức `setProcessors(Iterable<? extends Processor>)` để truyền **instance processor** trực tiếp. Cách này hữu ích khi processor class đã được test harness load trong JVM. Ví dụ minh họa:

~~~java
JavaCompiler.CompilationTask task =
        compiler.getTask(null, manager, diagnostics, options, null, units);
task.setProcessors(List.of(new RequiredIdProcessor()));
boolean ok = Boolean.TRUE.equals(task.call());
~~~

**Đoạn trên không phải tệp chạy độc lập.** Nó giả định đã import `RequiredIdProcessor`, có các biến `compiler`, `manager`, `diagnostics`, `options` và `units`. Đây là một **cách cấu hình thay thế**, không phải lời khuyên dùng đồng thời cùng `-processor ...` cho một task. Trong demo chính, chúng ta kiểm tra luôn cơ chế tìm processor từ compiler options `-processorpath`/`-processor`, gần với thực tế khi processor nằm trong artifact build.

**Lưu ý về kiểm thử:** khi dùng `setProcessors`, test có thể bỏ qua một số lỗi đóng gói/khám phá processor do chạy cùng JVM. Nếu mục tiêu là bảo đảm artifact processor được build đúng và compiler có thể tìm thấy nó ở dependency path thực, dùng cách cấu hình qua `-processor`/`-processorpath` như bài lab.

### 8.6. JDK 23+ không tự chạy processor theo cách cũ

Từ **JDK 23**, `javac` yêu cầu một lựa chọn annotation processing tường minh; việc tình cờ có processor trên classpath **không đủ** để bảo đảm nó chạy. Những cách bật hiện hành bao gồm:

- `-processor demo.apt.RequiredIdProcessor` để nêu đích danh processor;
- `-processorpath <path>` hoặc `--processor-path <path>` để khai báo đường tìm processor;
- `--processor-module-path <path>` đối với processor modular;
- `-proc:full` để cho phép annotation processing kèm compilation (với cơ chế khám phá thích hợp);
- `-proc:only` để chỉ xử lý annotation;
- `-proc:none` để tắt processing, như negative control.

Bài lab không dựa vào default auto-discovery. Processor được chỉ định rõ tên, giảm nguy cơ chạy processor ngoài ý muốn trong dependencies.

Không dùng `-J...` trong `JavaCompiler.getTask(...)` như cách truyền option trực tiếp cho lệnh `javac`: `-J` là tùy chọn của launcher command-line cho JVM chạy javac, **không phải một compiler option chuẩn của `getTask`**. Nếu cần cấu hình JVM chứa compiler API, cấu hình chính JVM chạy harness.

## 9. Mở rộng test theo hướng có ý nghĩa

### 9.1. Test nhiều nguồn, nhiều rounds

Processor có thể tạo generated source chứa annotation được xử lý ở **round tiếp theo**. Với fixture phù hợp, test thêm:

- Source generated ở round 1 được compiler nhìn thấy ở round 2.
- `RoundEnvironment.processingOver()` được nhận ở final round.
- Processor không gọi `Filer.createSourceFile(...)` trùng tên nhiều lần trong một build.
- Không sinh file mới vô hạn vì code generation tự kích hoạt annotation tiếp.
- Nếu phát `Messager.printMessage(ERROR, ...)` ở một round, toàn tác vụ compile thất bại.

Dùng output sạch để phân biệt generated files từ build này với file tồn dư. Nếu muốn kiểm tra số vòng chính xác, hãy dựng fixture có số bước xác định và kiểm tra output observable, không dựa vào log nội bộ `javac` có thể đổi dạng trình bày.

### 9.2. Test generated code sai cú pháp

Một processor có thể chạy không lỗi nhưng **sinh source Java không hợp lệ**. Test quan trọng là: `Filer` đã tạo file, song `CompilationTask.call()` trả `false` và `DiagnosticCollector` chứa ERROR gắn với generated source.

Đừng coi `File.exists(generatedSource) == true` là điều kiện đủ của processor tốt. Nếu compile tiếp generated code là mục tiêu production, bắt buộc test kết quả compilation và nội dung quan trọng của file.

### 9.3. Test duplicate output và FilerException

Trong cùng một compilation, `Filer` không cho tạo lặp cùng file/path/type name. Nếu nhiều annotated inputs dẫn tới cùng generated fully-qualified name, processor phải báo diagnostic phù hợp hoặc test có thể nhận `FilerException`/lỗi task.

Test nên dựng **hai input cùng gây trùng tên**, rồi assert build không thành công với báo lỗi có ngữ cảnh. Không bắt `IOException` rồi lặng lẽ coi là thành công như thể output đã được tạo.

### 9.4. Kiểm thử bản processor đã đóng gói

Bài lab dùng các `.class` đã build trong `classes`. Khi phát hành processor theo JAR, bổ sung integration test:

1. Build JAR processor chứa `RequiredIdProcessor.class` và dependency thích hợp.
2. Đặt JAR trên processor path.
3. Dùng JavaCompiler API compile fixture với `-processor` cụ thể.
4. Kiểm tra diagnostics, source/class được sinh và mã dùng được từ artifact cuối.
5. Nếu dùng service discovery, kiểm tra resource `META-INF/services/javax.annotation.processing.Processor` **thật sự tồn tại trong JAR**; đừng chỉ kiểm tra ở source resources.

Processor viết bằng Java code chạy trong compiler process. Chỉ dùng processor đáng tin cậy và hạn chế đường tìm kiếm; JavaCompiler API **không tạo sandbox** để compile code hoặc processor không tin cậy.

### 9.5. Đối chiếu với thư viện test bên ngoài

Các thư viện compile-testing của hệ sinh thái Java có thể làm fixture/diagnostic/generated-source assertions tiện hơn, nhưng **không phải một phần của JDK**. Với mục tiêu hiểu Compiler API gốc, harness ở đây đầy đủ mà không cần dependency ngoài.

JUnit Jupiter có thể bọc các kịch bản dưới dạng test method và dùng `assertTrue`, `assertFalse`, `assertEquals`, nhưng test vẫn cần chạy **compiler thật**. Không viết mock `RoundEnvironment` trừ khi muốn unit-test một thuật toán rất nhỏ tách biệt khỏi vòng đời JSR 269.

## 10. Các lỗi thường gặp khi viết test processor

| Hiện tượng | Nguyên nhân cần xem xét | Cách kiểm tra |
| --- | --- | --- |
| `ToolProvider.getSystemJavaCompiler() == null` | JDK runtime image không có implementation của system compiler | Chạy test trên JDK có module `jdk.compiler`; kiểm tra runtime modules |
| `Cannot find symbol RequiredId` | Source fixture không thấy annotation type trên compile classpath | Soát `-classpath`/module path, package, output |
| `Annotation processor not found` | Sai tên đầy đủ, processor chưa compile, sai processor path | Kiểm tra `-processor` và `-processorpath` |
| `call() == true` nhưng generated file không có | Processor chưa bật, không thấy annotation, nhầm output directory | Kiểm tra explicit processing options và `-s` |
| Compiler báo ERROR cho valid source | Processor sinh mã lỗi hoặc validation quá chặt, dependency sai | Xem `DiagnosticCollector`, cả source input và generated source |
| Negative test `call() == false` nhưng không có ERROR | Compilation failure kiểu khác, assertion/test harness sai | Thu cả diagnostics và kiểm tra nguyên nhân thực tế |
| Negative test có file đã sinh dù logic sai | Output cũ hoặc generator sinh trước khi phát hiện lỗi | Cách ly thư mục theo test, kiểm tra thứ tự validation/generation |
| `FilerException` | Tạo trùng name/path trong một task hoặc đụng input type | Theo dõi FQN đã sinh, không tạo hai lần |
| `getTask(...)` ném lỗi option | Option truyền sai dạng hoặc không được hỗ trợ | Truyền từng token trong `List<String>`, kiểm tra compiler version |
| Output test khác nhau giữa các JDK | Dựa vào message/diagnostic ordering không được bảo đảm | Khẳng định `Kind.ERROR`, paths, generated content và trạng thái compile |
| File manager gây khóa JAR/temp dir | Chưa đóng `StandardJavaFileManager` hoặc class loader | Đóng tài nguyên trong `try-with-resources` |
| Test đạt dù processor không chạy | Chỉ kiểm tra compile success hoặc dùng output đã tạo trước | Thêm negative control `-proc:none` và assert artifact cụ thể |

**Không kiểm thử processor bằng runtime reflection trên annotation type `SOURCE`**: nó không tồn tại để JVM đọc bằng `Class.getAnnotation(...)`. Test compiler phải dùng mô hình annotation đang được compiler xử lý và xác minh artifact/diagnostic tương ứng.

## 11. Thiết kế bộ test cho CI và production

Các nguyên tắc thực tế:

1. **Ghim toolchain/source release:** dùng một JDK được hỗ trợ cho processor và `--release` phù hợp với source ứng dụng; nhớ rằng processor **chạy trên JDK thực tế của compiler**, trong khi source input có thể target release thấp hơn.
2. **Cấu hình processor công khai:** dùng processor path/plugin dependency riêng và liệt kê processor cần chạy; từ JDK 23 đừng dựa vào implicit activation.
3. **Đầu vào test tách biệt:** mỗi test có source/output riêng hoặc ít nhất dọn sạch thư mục trước mỗi run.
4. **Kiểm tra generated artifact ổn định:** tên type, package, nội dung contract, compiler diagnostics và class output; tránh assertion phụ thuộc thứ tự log hoặc warning không liên quan.
5. **Phát lỗi qua Messager:** processor nên dùng `Diagnostic.Kind.ERROR` khi annotation vi phạm quy tắc, không `System.out.println` rồi tiếp tục báo thành công.
6. **Giữ file manager sạch:** đóng ngay sau test và không giữ references tới compilation units/output ngoài phạm vi cần thiết.
7. **Test lỗi âm tính có nghĩa:** không chỉ assert happy path; thêm input sai, processor tắt, dependency vắng mặt và generated source lỗi.
8. **Không chạy generated code vô tình:** annotation processors có thể thực thi trong compile; runtime loading/invocation là bước test độc lập có chủ đích.
9. **Không thực thi mã không tin cậy trong JVM chính:** compiler in-process và processor path đều có quyền của tiến trình kiểm thử. Nếu phải test source/processor từ bên ngoài, dùng process isolation và hạn mức/kiểm soát thích hợp.

Mức độ kiểm thử có thể phân tầng: unit-test logic tạo tên/validation thuần Java, compile-test với JavaCompiler cho JSR 269 behavior, rồi integration-test artifact processor cuối cùng trong Maven/Gradle/CI. **Không** thay compile-test bằng một unit-test mock đơn thuần khi mục tiêu là bảo đảm tích hợp compiler.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Khi một source Java có `@RequiredId("alpha")` compile thành công, có chắc processor đã chạy không?

**Đáp án:** Không. Annotation type hợp lệ vẫn được compiler chấp nhận khi `-proc:none`. Phải kiểm tra generated files hoặc diagnostics mà processor tạo, như kịch bản đối chứng.

**Câu 2.** `process(...)` của `AbstractProcessor` trả `true` có nghĩa `CompilationTask.call()` cũng trả `true` không?

**Đáp án:** Không. `process(...)` trả `true` để claim các annotation types; lỗi source/processor/generated code vẫn có thể khiến toàn tác vụ compile thất bại.

**Câu 3.** Processor dùng `Messager.printMessage(ERROR, ...)`. Test nên khẳng định gì?

**Đáp án:** `call() == false` và `DiagnosticCollector` chứa ít nhất một diagnostic có `getKind() == Diagnostic.Kind.ERROR`; thêm assertion về source/line hoặc nội dung lỗi khi cần contract cụ thể.

**Câu 4.** Vì sao phải kiểm tra generated `.class`, không chỉ generated `.java`?

**Đáp án:** Để chứng minh compiler đã biên dịch source do processor tạo ra trong full compile. `.java` có thể tồn tại dù source sinh lỗi cú pháp hoặc task dừng ở `-proc:only`.

**Câu 5.** Bài test chạy với JDK 24 và `--release 17`. Processor đang chạy trên JVM nào, bytecode target là gì?

**Đáp án:** Processor chạy trong JVM của JDK 24 đang thực hiện compiler; source và class của đối tượng được biên dịch target Java 17 theo `--release 17`. Hai bối cảnh không đồng nhất.

**Câu 6.** `StandardJavaFileManager` có thể để mở đến hết JVM không?

**Đáp án:** Không nên. Nó quản lý tài nguyên I/O và có thể giữ cache/handle; dùng `try-with-resources` và đóng sau lần compile.

**Câu 7.** Trên JDK 23+, chỉ để JAR processor trên classpath thông thường có đủ bảo đảm annotation processing chạy không?

**Đáp án:** Không. Cấu hình processing rõ ràng, như `-processor`, processor path/module path hoặc `-proc:full` theo cơ chế được tài liệu hỗ trợ.

**Bài tập.** Mở rộng `RequiredIdProcessor` để từ chối ID chứa khoảng trắng và phát ERROR gắn với `Element`. Thêm vào `ProcessorTestHarness` ba test:
- `@RequiredId("a b")` phải bị từ chối;
- `@RequiredId("xyz")` phải sinh `ID_LENGTH = 3`;
- Processor tắt `-proc:none` phải không sinh file dù source hợp lệ.

Mỗi test cần có output riêng và kiểm tra cùng lúc compilation status, diagnostics và generated output.

## 13. Tài liệu Java chính thức còn được hỗ trợ

- [Java SE 26 — JavaCompiler](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/JavaCompiler.html): `getTask`, file manager, diagnostics, compilation lifecycle.
- [Java SE 26 — JavaCompiler.CompilationTask](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/JavaCompiler.CompilationTask.html): `call`, `setProcessors`.
- [Java SE 26 — ToolProvider](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/ToolProvider.html): `getSystemJavaCompiler`.
- [Java SE 26 — DiagnosticCollector](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/DiagnosticCollector.html): thu diagnostics.
- [Java SE 26 — StandardJavaFileManager](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html): tạo compilation units và quản lý I/O.
- [Java SE 26 — AbstractProcessor](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/AbstractProcessor.html): lifecycle của processor.
- [Java SE 26 — Filer](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/Filer.html): sinh source và các vòng xử lý tiếp theo.
- [Java SE 26 — Messager](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/annotation/processing/Messager.html): báo lỗi gắn vào compiler model.
- [Java SE 26 — javac command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html): `-processor`, `-processorpath`, `-proc:none`, `-proc:only`, `-proc:full`.
- [Oracle JDK 23 release notes](https://www.oracle.com/java/technologies/javase/23-relnote-issues.html): annotation processing được tắt theo mặc định khi không có lựa chọn kích hoạt rõ ràng.

**Ghi nhớ:** để kiểm thử annotation processor, hãy **cho nó chạy qua một tác vụ `JavaCompiler` thực sự**. Một test tốt không dừng ở `call() == true`: nó xác nhận `Diagnostic`, generated `.java`, generated `.class`, nội dung output và cả trường hợp processor **không chạy**.
